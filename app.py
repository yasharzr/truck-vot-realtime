"""
Truck VOT Real-Time Dashboard
FastAPI application serving the API and dashboard.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TORONTO_TZ = ZoneInfo("America/Toronto")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

import config
import db
import data_collector
import traffic_client
import toll_calculator
import vot_model
import incidents

_DIR = Path(__file__).resolve().parent

# ── In-memory cache of latest collector snapshot per direction ─────────────
# The collector writes here every 3 min (alternating east/west).
# /api/current reads from cache → ZERO extra Google API calls from the frontend.
_cache: dict[str, dict | None] = {'east': None, 'west': None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_collection_loop())
    yield
    task.cancel()


app = FastAPI(title="Truck VOT Real-Time", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(_DIR / "static")), name="static")


async def _collection_loop():
    """Background data collection every COLLECT_INTERVAL_MINUTES."""
    await asyncio.sleep(2)
    while True:
        try:
            snapshot = await data_collector.collect_snapshot()
            direction = snapshot.get("direction", "east")
            _cache[direction] = snapshot          # ← cache for /api/current
            src = snapshot["source"]
            vot = snapshot["vot"]
            print(
                f"[collector] {snapshot['fetched_at']} | {direction} | "
                f"401={snapshot['route_401']['tt_minutes']}m "
                f"407={snapshot['route_407']['tt_minutes']}m "
                f"toll=${snapshot['toll']['total']} "
                f"market_vot=${vot['market_vot']}/hr "
                f"P(toll)={vot['choice_probability_toll_simulated']}% "
                f"({src})"
            )
        except Exception as e:
            print(f"[collector] error: {e}")
        await asyncio.sleep(config.COLLECT_INTERVAL_MINUTES * 60)


def _build_current_response(snapshot: dict, direction: str) -> dict:
    """Build /api/current-style response from a cached collector snapshot."""
    now = datetime.now(tz=TORONTO_TZ)
    toll = toll_calculator.calculate_toll(now)   # recalc — toll period may have changed
    r401 = snapshot["route_401"]
    r407 = snapshot["route_407"]
    vot = vot_model.compute_vot_snapshot(
        tt_401=r401["tt_minutes"],
        tt_407=r407["tt_minutes"],
        delay_401=r401["delay_minutes"],
        delay_407=r407["delay_minutes"],
        toll_cost=toll["total"],
        distance_401_km=r401["distance_km"],
        distance_407_km=r407["distance_km"],
    )
    origin      = config.ORIGIN      if direction == "east" else config.DESTINATION
    destination = config.DESTINATION if direction == "east" else config.ORIGIN
    return {
        "timestamp": snapshot["fetched_at"],
        "source": snapshot["source"],
        "direction": direction,
        "route_401": r401,
        "route_407": r407,
        "toll": toll,
        "vot": vot,
        "route_info": {"origin": origin, "destination": destination},
    }


@app.get("/")
async def dashboard():
    return FileResponse(str(_DIR / "static" / "index.html"))


@app.get("/api/current")
async def get_current(direction: str = "east"):
    """Current conditions from the collector cache.  Zero extra API calls.

    Falls back to a live Google API call only on first startup (cache empty).
    """
    if direction not in ("east", "west"):
        direction = "east"

    cached = _cache.get(direction)
    if cached:
        return _build_current_response(cached, direction)

    # Cache empty (first startup) — make one live call
    now = datetime.now(tz=TORONTO_TZ)
    traffic = await traffic_client.fetch_both_routes(direction=direction)
    toll = toll_calculator.calculate_toll(now)
    r401 = traffic["route_401"]
    r407 = traffic["route_407"]
    vot = vot_model.compute_vot_snapshot(
        tt_401=r401["tt_minutes"],
        tt_407=r407["tt_minutes"],
        delay_401=r401["delay_minutes"],
        delay_407=r407["delay_minutes"],
        toll_cost=toll["total"],
        distance_401_km=r401["distance_km"],
        distance_407_km=r407["distance_km"],
    )
    origin      = config.ORIGIN      if direction == "east" else config.DESTINATION
    destination = config.DESTINATION if direction == "east" else config.ORIGIN
    return {
        "timestamp": now.isoformat(),
        "source": traffic["source"],
        "direction": direction,
        "route_401": r401,
        "route_407": r407,
        "toll": toll,
        "vot": vot,
        "route_info": {"origin": origin, "destination": destination},
    }


@app.get("/api/current-both")
async def get_current_both():
    """Both directions from collector cache. Zero API cost.

    Returns {east: {...}, west: {...}} — either may be null if the
    collector hasn't fetched that direction yet.
    """
    result = {}
    for d in ("east", "west"):
        cached = _cache.get(d)
        result[d] = _build_current_response(cached, d) if cached else None
    return result


@app.get("/api/projection")
async def get_projection(direction: str = "east"):
    """
    24-hour timeline for today.

    Each 30-min slot is filled with REAL collected data (averaged) when
    available in the DB, and falls back to estimated patterns only for
    slots we haven't reached / haven't collected yet.

    Every point carries  is_real: true/false  so the frontend can render
    real segments as solid lines and projected segments as dashed.
    """
    if direction not in ("east", "west"):
        direction = "east"
    now = datetime.now(tz=TORONTO_TZ)

    # ── 1. Scaffold: 3-min slots across 24 hours (480 slots) ──────────────
    #   Each direction collects every 6 min (alternating), so ~240 real
    #   data points per direction per day.  3-min resolution shows all of
    #   them at their actual granularity instead of averaging into 30-min
    #   buckets.
    travel_times_est = traffic_client.get_24h_travel_times(now, interval_minutes=3)
    tolls_24h        = toll_calculator.toll_for_24h(now, interval_minutes=3)
    est_slots        = vot_model.compute_24h_vot_projection(travel_times_est, tolls_24h)

    # ── 2. Real snapshots from the DB (last 24 h) ───────────────────────────
    real_snaps = db.get_recent(hours=24, direction=direction)

    # Build lookup  (toronto_hour, 3-min-bucket) → list[snapshot]
    # Timestamps may be naive-UTC (old data from Railway) or tz-aware Toronto (new data).
    # Always convert to Toronto before extracting hour so slots align with chart labels.
    _UTC = ZoneInfo("UTC")
    real_by_slot: dict = {}
    for snap in real_snaps:
        try:
            ts = datetime.fromisoformat(snap["timestamp"])
            if ts.tzinfo is None:
                # Naive → assume UTC (Railway default) → convert to Toronto
                ts = ts.replace(tzinfo=_UTC).astimezone(TORONTO_TZ)
            else:
                ts = ts.astimezone(TORONTO_TZ)
            key = (ts.hour, (ts.minute // 3) * 3)
            real_by_slot.setdefault(key, []).append(snap)
        except Exception:
            pass

    # ── 3. Build result — real data where collected, null where not ──────────
    result = []
    for est in est_slots:
        key = (est["hour"], est["minute"])
        snaps = real_by_slot.get(key, [])

        if snaps:
            def _avg(field, _snaps=snaps):
                vals = [s[field] for s in _snaps if s.get(field) is not None]
                return round(sum(vals) / len(vals), 1) if vals else None

            result.append({
                "time_label": est["time_label"],
                "hour":       est["hour"],
                "minute":     est["minute"],
                "tt_401":     _avg("tt_401"),
                "tt_407":     _avg("tt_407"),
                "toll_cost":  _avg("toll_cost"),
                "time_saved": _avg("time_saved"),
                "market_vot": _avg("market_vot"),
                "is_real":    True,
            })
        else:
            # No real data for this slot — return nulls (not fake estimates)
            result.append({
                "time_label": est["time_label"],
                "hour":       est["hour"],
                "minute":     est["minute"],
                "tt_401":     None,
                "tt_407":     None,
                "toll_cost":  None,
                "time_saved": None,
                "market_vot": None,
                "is_real":    False,
            })

    real_count = sum(1 for r in result if r["is_real"])

    return {
        "date":            now.date().isoformat(),
        "is_weekday":      now.weekday() < 5,
        "day_name":        now.strftime("%A"),
        "thesis_vot_mean": config.MODEL["vot_mean"],
        "real_count":      real_count,
        "total_slots":     len(result),
        "data":            result,
    }


@app.get("/api/history")
async def get_history(hours: int = 24, direction: str = "east"):
    """Get historical snapshots."""
    return {
        "hours": hours,
        "data": db.get_recent(hours, direction=direction),
        "total_snapshots": db.get_snapshot_count(),
    }


@app.get("/api/averages")
async def get_averages(weekday: bool = True):
    """Get hourly averages from historical data."""
    return {
        "weekday": weekday,
        "data": db.get_hourly_averages(weekday),
    }


@app.get("/api/toll-breakdown")
async def get_toll_breakdown():
    """Get detailed toll breakdown for current time."""
    return toll_calculator.calculate_toll()


@app.get("/api/history/range")
async def get_history_range(range: str = "24h", direction: str = "east"):
    """Get historical data for different time ranges: 24h, 7d, 30d, 365d."""
    if range not in ("24h", "7d", "30d", "365d"):
        range = "24h"
    data = db.get_history_range(range, direction)
    return {
        "range": range,
        "count": len(data),
        "data": data,
    }


@app.post("/api/survey")
async def submit_survey(request: Request):
    """Submit a driver survey response."""
    body = await request.json()
    db.save_survey_response(body)
    return {"status": "ok", "message": "Response recorded. Thank you!"}


@app.get("/api/survey/stats")
async def survey_stats():
    """Get aggregate survey statistics for driver insights."""
    return db.get_survey_stats()


@app.get("/api/incidents")
async def get_incidents():
    """Real-time road incidents (accidents, construction, closures) on 401/407 corridor.
    Data from Ontario 511 — free, no API key needed."""
    return await incidents.fetch_corridor_incidents()


@app.get("/health")
async def health():
    """Health check for deployment monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(tz=TORONTO_TZ).isoformat(),
        "has_api_key": bool(config.GOOGLE_MAPS_API_KEY),
        "snapshots_collected": db.get_snapshot_count(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

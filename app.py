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

_DIR = Path(__file__).resolve().parent


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
            src = snapshot["source"]
            vot = snapshot["vot"]
            print(
                f"[collector] {snapshot['fetched_at']} | "
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


@app.get("/")
async def dashboard():
    return FileResponse(str(_DIR / "static" / "index.html"))


@app.get("/api/current")
async def get_current(direction: str = "east"):
    """Get current real-time conditions and VOT analysis.

    direction: 'east' (Hornby → Bowmanville) or 'west' (Bowmanville → Hornby)
    """
    if direction not in ("east", "west"):
        direction = "east"

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
        "route_info": {
            "origin": origin,
            "destination": destination,
        },
    }


@app.get("/api/projection")
async def get_projection():
    """Get 24-hour VOT projection using typical patterns + toll schedule."""
    now = datetime.now(tz=TORONTO_TZ)

    travel_times = traffic_client.get_24h_travel_times(now, interval_minutes=30)
    tolls = toll_calculator.toll_for_24h(now, interval_minutes=30)

    projection = vot_model.compute_24h_vot_projection(travel_times, tolls)

    return {
        "date": now.date().isoformat(),
        "is_weekday": now.weekday() < 5,
        "day_name": now.strftime("%A"),
        "thesis_vot_mean": config.MODEL["vot_mean"],
        "data": projection,
    }


@app.get("/api/history")
async def get_history(hours: int = 24):
    """Get historical snapshots."""
    return {
        "hours": hours,
        "data": db.get_recent(hours),
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
async def get_history_range(range: str = "24h"):
    """Get historical data for different time ranges: 24h, 7d, 30d, 365d."""
    if range not in ("24h", "7d", "30d", "365d"):
        range = "24h"
    data = db.get_history_range(range)
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

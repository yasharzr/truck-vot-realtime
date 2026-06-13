"""
Real-time traffic data client using Google Maps Directions API.
Fetches travel time for both the 401 (free) and 407 (toll) routes.
Falls back to historical estimates when API is unavailable.

ROUTING STRATEGY
────────────────
Instead of guessing via: lat/lng coordinates on a highway (which snap to
the nearest road and cause detours when the point is near a ramp), we use
alternatives=true to ask Google for multiple routes and then IDENTIFY which
returned route is 401 and which is 407 by reading the route summary string
(e.g. "ON-401" vs "ON-407").

Fallback: if alternatives doesn't return both routes (e.g. off-peak when
Google only sees 401 as viable), we fall back to a single forced call:
  401 → avoid=tolls  (guaranteed toll-free, always correct)
  407 → avoid=tolls on a SECOND call, then invert logic is n/a —
         we keep the alternatives result or fall back to estimates.
"""

import httpx
import config
from datetime import datetime
from zoneinfo import ZoneInfo

_TORONTO = ZoneInfo("America/Toronto")

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


def _parse_route_obj(route: dict) -> dict:
    """Parse a single route object from the Directions API response."""
    legs = route["legs"]
    total_traffic_sec = sum(leg["duration_in_traffic"]["value"] for leg in legs)
    total_freeflow_sec = sum(leg["duration"]["value"] for leg in legs)
    total_distance_m   = sum(leg["distance"]["value"] for leg in legs)
    return {
        "duration_traffic_sec": total_traffic_sec,
        "duration_freeflow_sec": total_freeflow_sec,
        "distance_m": total_distance_m,
        "summary": route.get("summary", ""),
        "polyline": route["overview_polyline"]["points"],
    }


async def _fetch_alternatives(
    origin: dict,
    destination: dict,
    client: httpx.AsyncClient,
) -> tuple[dict | None, dict | None]:
    """
    Ask Google for up to 3 route alternatives, then identify 401 vs 407
    by their summary strings.  Returns (raw_401, raw_407) — either may be
    None if that highway wasn't among the alternatives.
    """
    if not config.GOOGLE_MAPS_API_KEY:
        return None, None

    params = {
        "origin": f"{origin['lat']},{origin['lng']}",
        "destination": f"{destination['lat']},{destination['lng']}",
        "alternatives": "true",
        "departure_time": "now",
        "traffic_model": "best_guess",
        "key": config.GOOGLE_MAPS_API_KEY,
    }

    try:
        resp = await client.get(GOOGLE_DIRECTIONS_URL, params=params, timeout=15)
        data = resp.json()

        if data["status"] != "OK" or not data.get("routes"):
            return None, None

        # Classify by toll vs free — NOT by highway name.
        # 407 ETR is the ONLY toll road in our corridor; any route without "ETR"
        # in the summary is toll-free (could be 401, 401+407 East bypass, etc.)
        raw_free, raw_toll = None, None
        for route in data["routes"]:
            summary = route.get("summary", "")
            is_toll = "ETR" in summary.upper()
            if is_toll:
                if raw_toll is None:
                    raw_toll = route
            else:
                if raw_free is None:
                    raw_free = route

        # Time-based fallback when no ETR-named route found
        # (very off-peak: Google may describe toll route differently)
        if raw_free is None and raw_toll is None and len(data["routes"]) >= 2:
            routes_by_time = sorted(
                data["routes"],
                key=lambda r: sum(
                    leg["duration_in_traffic"]["value"] for leg in r["legs"]
                ),
            )
            raw_toll = routes_by_time[0]   # fastest = likely toll bypass
            raw_free = routes_by_time[-1]  # slowest = likely free route

        # Return (free_route, toll_route) — maps to (route_401, route_407) in caller
        return (
            _parse_route_obj(raw_free) if raw_free else None,
            _parse_route_obj(raw_toll) if raw_toll else None,
        )

    except Exception:
        return None, None


async def _fetch_forced(
    origin: dict,
    destination: dict,
    client: httpx.AsyncClient,
    avoid: str | None = None,
) -> dict | None:
    """
    Fallback: single forced route call.
    avoid='tolls'  → guaranteed 401 (toll-free).
    No avoid       → Google's best route (used when alternatives fails for 407).
    """
    if not config.GOOGLE_MAPS_API_KEY:
        return None

    params = {
        "origin": f"{origin['lat']},{origin['lng']}",
        "destination": f"{destination['lat']},{destination['lng']}",
        "departure_time": "now",
        "traffic_model": "best_guess",
        "key": config.GOOGLE_MAPS_API_KEY,
    }
    if avoid:
        params["avoid"] = avoid

    try:
        resp = await client.get(GOOGLE_DIRECTIONS_URL, params=params, timeout=15)
        data = resp.json()
        if data["status"] != "OK" or not data.get("routes"):
            return None
        return _parse_route_obj(data["routes"][0])
    except Exception:
        return None


async def fetch_both_routes(direction: str = "east") -> dict:
    """
    Fetch real-time travel data for both the 401 and 407 routes.

    direction: "east" (Hornby → Bowmanville) or "west" (Bowmanville → Hornby)

    Strategy:
    1. Ask Google for alternatives — identify routes by summary ("ON-401", "ON-407")
    2. If alternatives gives us both → done, clean routes, no guessed waypoints
    3. If 401 missing → fallback forced call with avoid=tolls
    4. If 407 still missing → use estimates

    Returns dict with route_401, route_407, source, fetched_at, direction.
    """
    if direction == "west":
        origin      = config.DESTINATION
        destination = config.ORIGIN
    else:
        origin      = config.ORIGIN
        destination = config.DESTINATION

    now = datetime.now(tz=_TORONTO)   # always Toronto time

    async with httpx.AsyncClient() as client:
        # One call only — alternatives returns both free and toll routes.
        # ETR-based classification (not name-matching) catches 401, bypass routes, etc.
        # NO avoid=tolls fallback — that second call was doubling API usage (~$90/mo).
        # If alternatives doesn't surface both routes, we fall back to estimates below.
        r_free_raw, r_toll_raw = await _fetch_alternatives(origin, destination, client)

    if r_free_raw and r_toll_raw:
        return {
            "route_401": _parse_route(r_free_raw),   # best free route (401 or bypass)
            "route_407": _parse_route(r_toll_raw),   # best toll route (407 ETR)
            "source": "google_maps",
            "fetched_at": now.isoformat(),
            "direction": direction,
        }

    result = _estimated_travel_times(now)
    result["direction"] = direction
    return result


def _classify_route(summary: str) -> tuple[str, bool]:
    """
    Return (human_label, uses_bypass) from a Google Maps summary string.

    uses_bypass=True means the *free* route is using 407 East (no toll)
    rather than straight 401 — Google is routing around a congested/incident-
    affected 401 segment via the free Hwy 412 or 418 connectors.

    Examples:
      "ON-401"                  → ("Hwy 401", False)
      "ON-407 ETR, ON-407 E"   → ("407 ETR + 407 East", False)
      "ON-407 E, ON-412"       → ("401 + 407 East (free via 412)", True)
      "ON-401, ON-407 E"       → ("401 + 407 East (free)", True)
    """
    upper = summary.upper()
    has_etr = "ETR" in upper
    # Strip the ETR suffix so "407 E" in the remainder means 407 East (free)
    without_etr = upper.replace("ETR", "---")
    has_407_east = "407 E" in without_etr or "407E" in without_etr.replace(" ", "")
    has_412 = "412" in upper
    has_418 = "418" in upper

    if has_etr:
        if has_407_east:
            return "407 ETR + 407 East", False
        return "407 ETR", False

    if has_412:
        return "401 + 407 East (free via 412)", True
    if has_418:
        return "401 + 407 East (free via 418)", True
    if has_407_east:
        return "401 + 407 East (free)", True
    return "Hwy 401", False


def _parse_route(raw: dict) -> dict:
    tt = raw["duration_traffic_sec"] / 60
    ff = raw["duration_freeflow_sec"] / 60
    summary = raw.get("summary", "")
    route_label, uses_bypass = _classify_route(summary)
    return {
        "tt_minutes": round(tt, 1),
        "freeflow_minutes": round(ff, 1),
        "delay_minutes": round(max(0, tt - ff), 1),
        "distance_km": round(raw["distance_m"] / 1000, 1),
        "polyline": raw.get("polyline"),
        "summary": summary,
        "route_label": route_label,
        "uses_bypass": uses_bypass,
    }


def _estimated_travel_times(now: datetime) -> dict:
    """
    Estimate travel times using typical daily patterns from thesis Chapter 3.
    401 peaks heavily during AM/PM rush; 407 is more stable.
    """
    hour = now.hour
    weekday = now.weekday() < 5

    if weekday:
        tt_401 = _weekday_401_pattern(hour)
        tt_407 = _weekday_407_pattern(hour)
    else:
        tt_401 = _weekend_401_pattern(hour)
        tt_407 = _weekend_407_pattern(hour)

    return {
        "route_401": {
            "tt_minutes": round(tt_401, 1),
            "freeflow_minutes": config.FREEFLOW_401,
            "delay_minutes": round(max(0, tt_401 - config.FREEFLOW_401), 1),
            "distance_km": config.DISTANCE_401_KM,
            "polyline": None,
        },
        "route_407": {
            "tt_minutes": round(tt_407, 1),
            "freeflow_minutes": config.FREEFLOW_407,
            "delay_minutes": round(max(0, tt_407 - config.FREEFLOW_407), 1),
            "distance_km": config.DISTANCE_407_KM,
            "polyline": None,
        },
        "source": "estimated",
        "fetched_at": now.isoformat(),
    }


def _weekday_401_pattern(hour: int) -> float:
    """Typical weekday 401 — full Cambridge → Newcastle corridor (~170 km).
    Freeflow ~95 min. Peak adds 50-90 min of Toronto congestion."""
    patterns = {
        0: 97,  1: 95,  2: 95,  3: 95,  4: 97,  5: 103,
        6: 125, 7: 155, 8: 180, 9: 160, 10: 130, 11: 122,
        12: 125, 13: 128, 14: 135, 15: 160, 16: 185, 17: 188,
        18: 160, 19: 128, 20: 115, 21: 108, 22: 103, 23: 99,
    }
    return patterns.get(hour, 130)


def _weekday_407_pattern(hour: int) -> float:
    """Typical weekday 407 — full Cambridge → Newcastle via 407 ETR + 407 East (~180 km).
    407 stays smooth; freeflow ~90 min."""
    patterns = {
        0: 91,  1: 90,  2: 90,  3: 90,  4: 90,  5: 92,
        6: 96,  7: 100, 8: 104, 9: 100, 10: 96,  11: 94,
        12: 96,  13: 97,  14: 99,  15: 102, 16: 106, 17: 106,
        18: 102, 19: 96,  20: 93,  21: 91,  22: 90,  23: 90,
    }
    return patterns.get(hour, 96)


def _weekend_401_pattern(hour: int) -> float:
    """Weekend 401 — full Cambridge → Newcastle corridor."""
    patterns = {
        0: 96,  1: 95,  2: 95,  3: 95,  4: 95,  5: 97,
        6: 100, 7: 106, 8: 114, 9: 120, 10: 126, 11: 130,
        12: 133, 13: 133, 14: 130, 15: 130, 16: 126, 17: 122,
        18: 115, 19: 110, 20: 106, 21: 102, 22: 99,  23: 97,
    }
    return patterns.get(hour, 115)


def _weekend_407_pattern(hour: int) -> float:
    """Weekend 407 — full Cambridge → Newcastle via 407 ETR + 407 East."""
    patterns = {
        0: 90,  1: 90,  2: 90,  3: 90,  4: 90,  5: 90,
        6: 91,  7: 92,  8: 93,  9: 94,  10: 95,  11: 95,
        12: 96,  13: 96,  14: 95,  15: 95,  16: 94,  17: 93,
        18: 92,  19: 91,  20: 91,  21: 90,  22: 90,  23: 90,
    }
    return patterns.get(hour, 93)


def get_24h_travel_times(base_dt: datetime | None = None, interval_minutes: int = 30) -> list[dict]:
    """Generate estimated travel times for every interval across 24 hours."""
    if base_dt is None:
        base_dt = datetime.now()

    weekday = base_dt.weekday() < 5
    results = []

    for minutes_offset in range(0, 24 * 60, interval_minutes):
        h, m = divmod(minutes_offset, 60)

        if weekday:
            tt_401 = _weekday_401_pattern(h)
            tt_407 = _weekday_407_pattern(h)
        else:
            tt_401 = _weekend_401_pattern(h)
            tt_407 = _weekend_407_pattern(h)

        results.append({
            "hour": h,
            "minute": m,
            "time_label": f"{h:02d}:{m:02d}",
            "tt_401": tt_401,
            "tt_407": tt_407,
            "time_saved": round(tt_401 - tt_407, 1),
        })

    return results

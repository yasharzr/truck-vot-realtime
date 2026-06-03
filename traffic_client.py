"""
Real-time traffic data client using Google Maps Directions API.
Fetches travel time for both the 401 (free) and 407 (toll) routes.
Falls back to historical estimates when API is unavailable.
"""

import httpx
import config
from datetime import datetime

GOOGLE_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


async def _fetch_route(
    origin: dict,
    destination: dict,
    waypoints: list[dict],
    client: httpx.AsyncClient,
) -> dict | None:
    """Fetch a single route from Google Maps Directions API.

    ``waypoints`` is a list of dicts with lat/lng.  Each is sent as a
    ``via:`` point so Google routes *through* them without stopping.
    Multiple via-points may produce multiple legs, so we sum them.
    """
    if not config.GOOGLE_MAPS_API_KEY:
        return None

    wp_str = "|".join(f"via:{wp['lat']},{wp['lng']}" for wp in waypoints)

    params = {
        "origin": f"{origin['lat']},{origin['lng']}",
        "destination": f"{destination['lat']},{destination['lng']}",
        "waypoints": wp_str,
        "departure_time": "now",
        "traffic_model": "best_guess",
        "key": config.GOOGLE_MAPS_API_KEY,
    }

    try:
        resp = await client.get(GOOGLE_DIRECTIONS_URL, params=params, timeout=15)
        data = resp.json()

        if data["status"] != "OK" or not data.get("routes"):
            return None

        route = data["routes"][0]
        legs = route["legs"]

        # Sum across all legs (via-waypoints may split the route)
        total_traffic_sec = sum(
            leg["duration_in_traffic"]["value"] for leg in legs
        )
        total_freeflow_sec = sum(leg["duration"]["value"] for leg in legs)
        total_distance_m = sum(leg["distance"]["value"] for leg in legs)

        return {
            "duration_traffic_sec": total_traffic_sec,
            "duration_freeflow_sec": total_freeflow_sec,
            "distance_m": total_distance_m,
            "summary": route.get("summary", ""),
            "polyline": route["overview_polyline"]["points"],
        }
    except Exception:
        return None


async def fetch_both_routes() -> dict:
    """
    Fetch real-time travel data for both the 401 and 407 routes.

    Returns dict with:
        route_401: {tt_minutes, freeflow_minutes, delay_minutes, distance_km, polyline}
        route_407: {tt_minutes, freeflow_minutes, delay_minutes, distance_km, polyline}
        source: "google_maps" | "estimated"
        fetched_at: ISO datetime
    """
    async with httpx.AsyncClient() as client:
        r401 = await _fetch_route(
            config.ORIGIN, config.DESTINATION, config.WAYPOINTS_401, client
        )
        r407 = await _fetch_route(
            config.ORIGIN, config.DESTINATION, config.WAYPOINTS_407, client
        )

    now = datetime.now()

    if r401 and r407:
        return {
            "route_401": _parse_route(r401),
            "route_407": _parse_route(r407),
            "source": "google_maps",
            "fetched_at": now.isoformat(),
        }

    return _estimated_travel_times(now)


def _parse_route(raw: dict) -> dict:
    tt = raw["duration_traffic_sec"] / 60
    ff = raw["duration_freeflow_sec"] / 60
    return {
        "tt_minutes": round(tt, 1),
        "freeflow_minutes": round(ff, 1),
        "delay_minutes": round(max(0, tt - ff), 1),
        "distance_km": round(raw["distance_m"] / 1000, 1),
        "polyline": raw.get("polyline"),
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
    """Typical weekday 401 through Toronto — decision segment only.
    Hwy 403 (Milton) → Hwy 412 (Whitby), ~120 km.
    Freeflow ~65 min, peak 100-130 min (Toronto congestion)."""
    patterns = {
        0: 66, 1: 65, 2: 65, 3: 65, 4: 66, 5: 70,
        6: 85, 7: 110, 8: 128, 9: 110, 10: 85, 11: 80,
        12: 82, 13: 85, 14: 92, 15: 112, 16: 130, 17: 130,
        18: 110, 19: 85, 20: 75, 21: 70, 22: 68, 23: 67,
    }
    return patterns.get(hour, 85)


def _weekday_407_pattern(hour: int) -> float:
    """Typical weekday 407 bypass — decision segment only.
    403 → 407 → 412 → 401, ~100 km.  407 stays smooth; freeflow ~55 min."""
    patterns = {
        0: 55, 1: 55, 2: 55, 3: 55, 4: 55, 5: 56,
        6: 58, 7: 60, 8: 62, 9: 60, 10: 58, 11: 57,
        12: 58, 13: 58, 14: 59, 15: 61, 16: 63, 17: 63,
        18: 61, 19: 58, 20: 56, 21: 56, 22: 55, 23: 55,
    }
    return patterns.get(hour, 58)


def _weekend_401_pattern(hour: int) -> float:
    """Weekend 401 through Toronto — decision segment only."""
    patterns = {
        0: 65, 1: 65, 2: 65, 3: 65, 4: 65, 5: 66,
        6: 68, 7: 72, 8: 78, 9: 82, 10: 85, 11: 88,
        12: 90, 13: 90, 14: 88, 15: 88, 16: 85, 17: 82,
        18: 78, 19: 74, 20: 70, 21: 68, 22: 66, 23: 66,
    }
    return patterns.get(hour, 78)


def _weekend_407_pattern(hour: int) -> float:
    """Weekend 407 bypass — decision segment only."""
    patterns = {
        0: 55, 1: 55, 2: 55, 3: 55, 4: 55, 5: 55,
        6: 55, 7: 56, 8: 56, 9: 57, 10: 57, 11: 57,
        12: 58, 13: 58, 14: 57, 15: 57, 16: 57, 17: 56,
        18: 56, 19: 56, 20: 55, 21: 55, 22: 55, 23: 55,
    }
    return patterns.get(hour, 56)


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

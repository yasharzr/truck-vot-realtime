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
    waypoint: dict,
    client: httpx.AsyncClient,
) -> dict | None:
    """Fetch a single route from Google Maps Directions API."""
    if not config.GOOGLE_MAPS_API_KEY:
        return None

    params = {
        "origin": f"{origin['lat']},{origin['lng']}",
        "destination": f"{destination['lat']},{destination['lng']}",
        "waypoints": f"via:{waypoint['lat']},{waypoint['lng']}",
        "departure_time": "now",
        "traffic_model": "best_guess",
        "key": config.GOOGLE_MAPS_API_KEY,
    }

    try:
        resp = await client.get(GOOGLE_DIRECTIONS_URL, params=params, timeout=15)
        data = resp.json()

        if data["status"] != "OK" or not data.get("routes"):
            return None

        leg = data["routes"][0]["legs"][0]
        return {
            "duration_traffic_sec": leg["duration_in_traffic"]["value"],
            "duration_freeflow_sec": leg["duration"]["value"],
            "distance_m": leg["distance"]["value"],
            "summary": data["routes"][0].get("summary", ""),
            "polyline": data["routes"][0]["overview_polyline"]["points"],
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
            config.ORIGIN, config.DESTINATION, config.WAYPOINT_401, client
        )
        r407 = await _fetch_route(
            config.ORIGIN, config.DESTINATION, config.WAYPOINT_407, client
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
    """Typical weekday 401 travel time through Toronto (minutes). From thesis Fig 3.5."""
    patterns = {
        0: 55, 1: 53, 2: 52, 3: 52, 4: 53, 5: 58,
        6: 72, 7: 95, 8: 110, 9: 95, 10: 78, 11: 75,
        12: 78, 13: 80, 14: 85, 15: 100, 16: 115, 17: 120,
        18: 100, 19: 82, 20: 70, 21: 65, 22: 60, 23: 57,
    }
    return patterns.get(hour, 70)


def _weekday_407_pattern(hour: int) -> float:
    """Typical weekday 407 travel time (minutes). Much more stable."""
    patterns = {
        0: 48, 1: 48, 2: 48, 3: 48, 4: 48, 5: 49,
        6: 52, 7: 55, 8: 58, 9: 55, 10: 52, 11: 51,
        12: 52, 13: 53, 14: 54, 15: 56, 16: 58, 17: 58,
        18: 55, 19: 52, 20: 50, 21: 49, 22: 48, 23: 48,
    }
    return patterns.get(hour, 52)


def _weekend_401_pattern(hour: int) -> float:
    patterns = {
        0: 53, 1: 52, 2: 52, 3: 52, 4: 52, 5: 53,
        6: 55, 7: 58, 8: 62, 9: 68, 10: 72, 11: 75,
        12: 78, 13: 78, 14: 75, 15: 75, 16: 72, 17: 70,
        18: 65, 19: 62, 20: 58, 21: 56, 22: 55, 23: 54,
    }
    return patterns.get(hour, 62)


def _weekend_407_pattern(hour: int) -> float:
    patterns = {
        0: 48, 1: 48, 2: 48, 3: 48, 4: 48, 5: 48,
        6: 49, 7: 49, 8: 50, 9: 51, 10: 52, 11: 52,
        12: 53, 13: 53, 14: 52, 15: 52, 16: 51, 17: 51,
        18: 50, 19: 50, 20: 49, 21: 49, 22: 48, 23: 48,
    }
    return patterns.get(hour, 50)


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

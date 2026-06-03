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
    """Typical weekday 401 Cambridge→Newcastle through Toronto (minutes).
    Longer route (~170km) so freeflow ~80min, peaks add Toronto congestion."""
    patterns = {
        0: 82, 1: 80, 2: 80, 3: 80, 4: 82, 5: 88,
        6: 110, 7: 140, 8: 165, 9: 145, 10: 115, 11: 110,
        12: 115, 13: 118, 14: 125, 15: 148, 16: 170, 17: 175,
        18: 148, 19: 118, 20: 100, 21: 92, 22: 87, 23: 84,
    }
    return patterns.get(hour, 110)


def _weekday_407_pattern(hour: int) -> float:
    """Typical weekday 407 Cambridge→Newcastle bypass (minutes).
    Longer route (~180km) but 407 stays smooth. Freeflow ~75min."""
    patterns = {
        0: 76, 1: 76, 2: 76, 3: 76, 4: 76, 5: 78,
        6: 82, 7: 86, 8: 90, 9: 86, 10: 82, 11: 80,
        12: 82, 13: 83, 14: 85, 15: 88, 16: 92, 17: 92,
        18: 88, 19: 82, 20: 79, 21: 77, 22: 76, 23: 76,
    }
    return patterns.get(hour, 82)


def _weekend_401_pattern(hour: int) -> float:
    patterns = {
        0: 80, 1: 80, 2: 80, 3: 80, 4: 80, 5: 82,
        6: 84, 7: 88, 8: 95, 9: 102, 10: 108, 11: 112,
        12: 115, 13: 115, 14: 112, 15: 112, 16: 108, 17: 105,
        18: 98, 19: 92, 20: 88, 21: 85, 22: 82, 23: 81,
    }
    return patterns.get(hour, 95)


def _weekend_407_pattern(hour: int) -> float:
    patterns = {
        0: 76, 1: 76, 2: 76, 3: 76, 4: 76, 5: 76,
        6: 77, 7: 78, 8: 79, 9: 80, 10: 81, 11: 82,
        12: 83, 13: 83, 14: 82, 15: 82, 16: 81, 17: 80,
        18: 79, 19: 78, 20: 77, 21: 77, 22: 76, 23: 76,
    }
    return patterns.get(hour, 79)


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

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
    avoid: str | None = None,
) -> dict | None:
    """Fetch a single route from Google Maps Directions API.

    ``waypoints`` is a list of dicts with lat/lng.  Each is sent as a
    ``via:`` point so Google routes *through* them without stopping.
    ``avoid`` can be e.g. "tolls" to guarantee a toll-free route.
    Multiple via-points may produce multiple legs, so we sum them.
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
    if waypoints:
        params["waypoints"] = "|".join(f"via:{wp['lat']},{wp['lng']}" for wp in waypoints)
    if avoid:
        params["avoid"] = avoid

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


async def fetch_both_routes(direction: str = "east") -> dict:
    """
    Fetch real-time travel data for both the 401 and 407 routes.

    direction: "east" (Hornby → Bowmanville) or "west" (Bowmanville → Hornby)

    Returns dict with:
        route_401: {tt_minutes, freeflow_minutes, delay_minutes, distance_km, polyline}
        route_407: {tt_minutes, freeflow_minutes, delay_minutes, distance_km, polyline}
        source: "google_maps" | "estimated"
        fetched_at: ISO datetime
        direction: "east" | "west"
    """
    if direction == "west":
        origin      = config.DESTINATION   # Bowmanville is origin when westbound
        destination = config.ORIGIN        # Hornby is destination when westbound
        wp401       = config.WAYPOINTS_401_WEST
        wp407       = config.WAYPOINTS_407_WEST
    else:
        origin      = config.ORIGIN
        destination = config.DESTINATION
        wp401       = config.WAYPOINTS_401_EAST
        wp407       = config.WAYPOINTS_407_EAST

    async with httpx.AsyncClient() as client:
        # 401: avoid=tolls guarantees a completely toll-free path
        r401 = await _fetch_route(origin, destination, wp401, client, avoid="tolls")
        # 407: waypoints bracket the full ETR corridor; Google picks fastest tolled route
        r407 = await _fetch_route(origin, destination, wp407, client)

    now = datetime.now()

    if r401 and r407:
        return {
            "route_401": _parse_route(r401),
            "route_407": _parse_route(r407),
            "source": "google_maps",
            "fetched_at": now.isoformat(),
            "direction": direction,
        }

    result = _estimated_travel_times(now)
    result["direction"] = direction
    return result


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

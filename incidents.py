"""
Ontario 511 incident data for 401/407 corridor.

Fetches real-time road events (accidents, construction, closures) from
the Ontario 511 API and filters to our PetroPoint West ↔ East corridor.

Free API — no key needed.  https://511on.ca/api/v2/get/event
"""

import httpx
from datetime import datetime
from zoneinfo import ZoneInfo

_TORONTO = ZoneInfo("America/Toronto")

ON511_URL = "https://511on.ca/api/v2/get/event"

# Our corridor bounding box (PetroPoint West to East)
# Lat: 43.40 – 44.00   Lon: -79.90 – -78.60
_LAT_MIN, _LAT_MAX = 43.40, 44.00
_LON_MIN, _LON_MAX = -79.90, -78.60

# Highway name patterns we care about
_HIGHWAYS = ("401", "407")


def _in_corridor(lat, lon) -> bool:
    """Check if a coordinate is within our 401/407 corridor."""
    try:
        lat, lon = float(lat), float(lon)
        return _LAT_MIN <= lat <= _LAT_MAX and _LON_MIN <= lon <= _LON_MAX
    except (TypeError, ValueError):
        return False


def _classify_severity(event: dict) -> str:
    """Classify event impact: critical / major / minor / info."""
    desc = (event.get("Description") or "").lower()
    lanes = (event.get("LanesAffected") or "").lower()
    is_closure = event.get("IsFullClosure", False)
    etype = event.get("EventType", "")

    if is_closure or "all lanes closed" in lanes:
        return "critical"
    if etype == "accidentsAndIncidents":
        if "serious" in desc or "fatal" in desc or "multi" in desc:
            return "critical"
        return "major"
    if "2" in lanes or "3" in lanes or "multiple" in lanes:
        return "major"
    return "minor"


def _icon_for_type(etype: str, severity: str) -> str:
    """Map marker icon for event type."""
    if etype == "accidentsAndIncidents":
        return "🚨" if severity == "critical" else "⚠️"
    if etype == "roadwork":
        return "🚧"
    if etype == "closures":
        return "🚫"
    return "ℹ️"


async def fetch_corridor_incidents() -> dict:
    """
    Fetch current incidents in our 401/407 corridor from Ontario 511.

    Returns {
      "fetched_at": "...",
      "total": N,
      "by_highway": {"401": [...], "407": [...]},
      "events": [
        {
          "id", "type", "severity", "icon", "highway", "direction",
          "description", "lanes_affected", "is_full_closure",
          "lat", "lng", "lat2", "lng2",
          "reported", "last_updated", "planned_end",
          "encoded_polyline",
        }, ...
      ],
      "summary": {
        "total_401": N, "total_407": N,
        "accidents": N, "closures": N, "roadwork": N,
        "critical": N, "major": N,
      }
    }
    """
    now = datetime.now(tz=_TORONTO)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(ON511_URL, timeout=10)
            all_events = resp.json()
    except Exception as e:
        return {
            "fetched_at": now.isoformat(),
            "total": 0,
            "events": [],
            "by_highway": {"401": [], "407": []},
            "summary": {},
            "error": str(e),
        }

    events = []
    for raw in all_events:
        road = str(raw.get("RoadwayName", ""))

        # Must be on 401 or 407
        hwy = None
        for h in _HIGHWAYS:
            if h in road:
                hwy = h
                break
        if not hwy:
            continue

        lat = raw.get("Latitude")
        lon = raw.get("Longitude")
        if not _in_corridor(lat, lon):
            continue

        severity = _classify_severity(raw)
        etype = raw.get("EventType", "unknown")

        # Convert epoch timestamps to ISO
        def _epoch_to_iso(val):
            if val and isinstance(val, (int, float)):
                return datetime.fromtimestamp(val, tz=_TORONTO).isoformat()
            return None

        events.append({
            "id": raw.get("ID"),
            "type": etype,
            "sub_type": raw.get("EventSubType"),
            "severity": severity,
            "icon": _icon_for_type(etype, severity),
            "highway": hwy,
            "direction": raw.get("DirectionOfTravel", ""),
            "description": raw.get("Description", ""),
            "lanes_affected": raw.get("LanesAffected", ""),
            "is_full_closure": bool(raw.get("IsFullClosure")),
            "lat": float(lat) if lat else None,
            "lng": float(lon) if lon else None,
            "lat2": float(raw["LatitudeSecondary"]) if raw.get("LatitudeSecondary") else None,
            "lng2": float(raw["LongitudeSecondary"]) if raw.get("LongitudeSecondary") else None,
            "reported": _epoch_to_iso(raw.get("Reported")),
            "last_updated": _epoch_to_iso(raw.get("LastUpdated")),
            "planned_end": _epoch_to_iso(raw.get("PlannedEndDate")),
            "encoded_polyline": raw.get("EncodedPolyline"),
        })

    # Sort: accidents first, then by severity
    severity_order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    events.sort(key=lambda e: (0 if e["type"] == "accidentsAndIncidents" else 1, severity_order.get(e["severity"], 9)))

    by_highway = {"401": [], "407": []}
    for e in events:
        by_highway[e["highway"]].append(e)

    summary = {
        "total_401": len(by_highway["401"]),
        "total_407": len(by_highway["407"]),
        "accidents": sum(1 for e in events if e["type"] == "accidentsAndIncidents"),
        "closures": sum(1 for e in events if e["is_full_closure"]),
        "roadwork": sum(1 for e in events if e["type"] == "roadwork"),
        "critical": sum(1 for e in events if e["severity"] == "critical"),
        "major": sum(1 for e in events if e["severity"] == "major"),
    }

    return {
        "fetched_at": now.isoformat(),
        "total": len(events),
        "events": events,
        "by_highway": by_highway,
        "summary": summary,
    }

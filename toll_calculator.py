"""
407 ETR toll calculator for heavy vehicles (3+ axles).
Computes toll cost based on entry/exit zone, time of day, and day of week.
"""

import json
import os
from datetime import datetime, time

_RATES_PATH = os.path.join(os.path.dirname(__file__), "toll_rates.json")

with open(_RATES_PATH) as f:
    _RATES = json.load(f)


def _time_in_range(t: time, start_str: str, end_str: str) -> bool:
    start = time.fromisoformat(start_str)
    end = time.fromisoformat(end_str)
    if end == time(23, 59):
        end = time(23, 59, 59)
    return start <= t <= end


def get_time_period(dt: datetime) -> str:
    weekday = dt.weekday() < 5
    t = dt.time()

    if not weekday:
        return "off_peak"

    periods = _RATES["time_periods"]["weekday"]
    for period_name, period_def in periods.items():
        for start_str, end_str in period_def["ranges"]:
            if _time_in_range(t, start_str, end_str):
                return period_name

    return "off_peak"


def calculate_toll(dt: datetime | None = None, has_transponder: bool = True) -> dict:
    """
    Calculate the full 407 toll for a heavy vehicle traversing Hwy 403 to Hwy 412.

    Returns dict with:
        total: total toll in CAD
        per_km_avg: average per-km rate
        segments: breakdown by segment
        time_period: peak/mid/off_peak
        distance_km: total distance
    """
    if dt is None:
        dt = datetime.now()

    period = get_time_period(dt)
    segments = _RATES["segments"]
    total_toll = 0.0
    total_distance = 0.0
    segment_details = []

    for seg in segments:
        rate = seg["rates_per_km"].get(period, seg["rates_per_km"]["off_peak"])
        dist = seg["distance_km"]
        cost = rate * dist

        if not has_transponder:
            cost += _RATES["camera_surcharge_per_km"]["video_only"] * dist

        segment_details.append({
            "id": seg["id"],
            "from": seg["from"],
            "to": seg["to"],
            "distance_km": dist,
            "rate_per_km": rate,
            "cost": round(cost, 2),
        })
        total_toll += cost
        total_distance += dist

    trip_charge = (
        _RATES["trip_charge"]["transponder"]
        if has_transponder
        else _RATES["trip_charge"]["video"]
    )
    total_toll += trip_charge

    return {
        "total": round(total_toll, 2),
        "per_km_avg": round((total_toll - trip_charge) / total_distance, 4) if total_distance else 0,
        "trip_charge": trip_charge,
        "segments": segment_details,
        "time_period": period,
        "distance_km": total_distance,
        "datetime": dt.isoformat(),
        "has_transponder": has_transponder,
    }


def toll_for_24h(base_dt: datetime | None = None, interval_minutes: int = 30) -> list[dict]:
    """Generate toll cost for every interval across 24 hours starting from base_dt's date."""
    if base_dt is None:
        base_dt = datetime.now()

    base_date = base_dt.date()
    results = []
    for minutes_offset in range(0, 24 * 60, interval_minutes):
        h, m = divmod(minutes_offset, 60)
        dt = datetime.combine(base_date, time(h, m))
        toll = calculate_toll(dt)
        results.append({
            "hour": h,
            "minute": m,
            "time_label": f"{h:02d}:{m:02d}",
            "toll_total": toll["total"],
            "time_period": toll["time_period"],
        })
    return results

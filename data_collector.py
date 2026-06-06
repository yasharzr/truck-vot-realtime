"""
Background data collector that runs on a schedule.
Fetches real-time traffic data and toll rates, computes VOT, and stores snapshots.
Can be run standalone or imported by the app for scheduled collection.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import traffic_client
import toll_calculator
import vot_model
import db
import config

_TORONTO = ZoneInfo("America/Toronto")


async def collect_snapshot() -> dict:
    """Fetch current conditions, compute VOT, store, and return the full snapshot."""
    now = datetime.now(tz=_TORONTO)   # always Toronto — correct toll period + timestamps

    traffic = await traffic_client.fetch_both_routes()
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

    snapshot = {
        "fetched_at": traffic["fetched_at"],
        "source": traffic["source"],
        "route_401": r401,
        "route_407": r407,
        "toll": toll,
        "vot": vot,
    }

    db.save_snapshot(snapshot)
    return snapshot


async def collect_loop():
    """Run collection in a loop (for standalone use)."""
    print(f"Starting data collector (every {config.COLLECT_INTERVAL_MINUTES} min)")
    while True:
        try:
            snapshot = await collect_snapshot()
            vot = snapshot["vot"]
            print(
                f"[{snapshot['fetched_at']}] "
                f"401={snapshot['route_401']['tt_minutes']}min "
                f"407={snapshot['route_407']['tt_minutes']}min "
                f"toll=${snapshot['toll']['total']} "
                f"saved={vot['time_saved_minutes']}min "
                f"market_vot=${vot['market_vot']}/hr "
                f"P(toll)={vot['choice_probability_toll_simulated']}% "
                f"[{snapshot['source']}]"
            )
        except Exception as e:
            print(f"Collection error: {e}")

        await asyncio.sleep(config.COLLECT_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    asyncio.run(collect_loop())

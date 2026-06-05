import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Route definition ---
# Survey sites / trip endpoints:
#   WEST (origin)  : PetroPoint West — Petro-Canada & Petro-Pass Truck Stop, Hornby
#   EAST (dest)    : PetroPoint East — Petro-Pass Truck Stop, Bowmanville
#
# Full corridor: ~170 km via 401, ~180 km via 407.
# The 407 route uses:
#   TOLL section : 407 ETR (Hwy 403 → Hwy 412, private concession)
#   FREE section : 407 East (Hwy 412 → Hwy 418, Ontario-built, no toll)

ORIGIN = {
    "lat": float(os.getenv("ORIGIN_LAT", "43.5665")),
    "lng": float(os.getenv("ORIGIN_LNG", "-79.8228")),
    "label": "PetroPoint West — Hornby",
    "address": "7443 Trafalgar Rd, Hornby, ON L0P 1E0",
}
DESTINATION = {
    "lat": float(os.getenv("DEST_LAT", "43.8919")),
    "lng": float(os.getenv("DEST_LNG", "-78.6918")),
    "label": "PetroPoint East — Bowmanville",
    "address": "2475 Energy Dr, Bowmanville, ON L1C 6Z9",
}

# ── Direction-aware waypoints ──────────────────────────────────────────────
#
# The corridor is driven in BOTH directions:
#   EAST: PetroPoint West (Hornby) → PetroPoint East (Bowmanville)
#   WEST: PetroPoint East (Bowmanville) → PetroPoint West (Hornby)
#
# 401 (no-toll): avoid=tolls alone is sufficient — Google picks the correct
#   toll-free 401 corridor naturally.  Adding via-waypoints whose coordinates
#   are not precisely ON the highway causes surface-road detours, so we use
#   NO via points here.
#
# 407 (toll): one confirmed via-point on 407 ETR @ Hwy 400 interchange
#   (Vaughan, 43.820, -79.540).  This coordinate sits on the toll highway
#   and forces Google to commit to the 407 ETR corridor.  A second western
#   waypoint is NOT added because guessed coordinates off 407 ETR caused a
#   Brampton surface-road detour in testing.
#
# For westbound the same Vaughan point works as a via — it sits between
# Bowmanville and Hornby along the 407 ETR corridor regardless of direction.

# EASTBOUND (Hornby → Bowmanville)
WAYPOINTS_401_EAST = []   # avoid=tolls handles it — no via needed
WAYPOINTS_407_EAST = [
    # 407 ETR mainline ~2 km east of Hwy 400 interchange, clean freeway section.
    # Avoids the Hwy 400 ramp geometry that caused the Vaughan U-shape detour.
    {"lat": 43.817, "lng": -79.510, "label": "407 ETR east of Hwy 400 (Vaughan)"},
]

# WESTBOUND (Bowmanville → Hornby) — same mid-corridor point works both ways
WAYPOINTS_401_WEST = []   # avoid=tolls handles it
WAYPOINTS_407_WEST = [
    {"lat": 43.817, "lng": -79.510, "label": "407 ETR east of Hwy 400 (Vaughan)"},
]

# Aliases used by background data collector (eastbound is primary)
WAYPOINTS_401 = WAYPOINTS_401_EAST
WAYPOINTS_407 = WAYPOINTS_407_EAST

# Free-flow travel times (minutes) — full Cambridge → Newcastle corridor
FREEFLOW_401 = 95.0   # ~170 km via 401, no congestion
FREEFLOW_407 = 90.0   # ~180 km via 407 ETR + 407 East, faster speed limit

# Route distances (km) — overridden by Google Maps API when available
DISTANCE_401_KM = 170.0
DISTANCE_407_KM = 180.0

# --- Thesis model parameters (MXL6 Panel) ---
MODEL = {
    "beta_tt": -0.068,       # travel time (per minute)
    "beta_tt_sd": 0.028,     # random parameter std dev
    "beta_ttv": -0.064,      # delay / travel time variability (per minute)
    "beta_tc": -0.049,       # toll cost (per dollar)
    "beta_tc_sd": 0.019,     # random parameter std dev
    "beta_dist": -0.044,     # extra distance (per km)
    "vot_mean": 81.01,       # $/hr from thesis
    "vot_sd": 10.09,         # $/hr
    "vor_mean": 58.18,       # $/hr (value of reliability)
    "vor_sd": 5.84,          # $/hr
}

# --- Data collector settings ---
# 3 minutes = ~29k Google Maps API calls/month (within $200 free tier)
# 1 minute would be ~86k calls/month = $432 cost, so 3 min is the practical max
COLLECT_INTERVAL_MINUTES = 3

# DB_PATH: override with env var to use a Railway persistent volume.
# Railway setup: add Volume mounted at /data, then set DB_PATH=/data/history.db
# Without env var, defaults to local ./data/history.db for development.
DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "history.db"),
)

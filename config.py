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

# ── Routing strategy ──────────────────────────────────────────────────────
#
# We no longer use via: lat/lng waypoints. Guessed coordinates snap to the
# nearest road (ramps, service roads) and cause detours.
#
# Instead, traffic_client.py requests alternatives=true and identifies each
# route by its summary string ("ON-401" vs "ON-407"). Google returns clean
# routes without any coordinate hints needed.
#
# These empty lists kept for backward compatibility only.
WAYPOINTS_401_EAST = []
WAYPOINTS_407_EAST = []
WAYPOINTS_401_WEST = []
WAYPOINTS_407_WEST = []
WAYPOINTS_401 = []
WAYPOINTS_407 = []

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

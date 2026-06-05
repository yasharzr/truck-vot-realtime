import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Route definition ---
# Origin : ONroute Cambridge North (truck stop west of 401/407 split, on 401)
# Dest   : ONroute Newcastle Westbound, 17188 Vivian Dr, Newcastle ON
#          (truck stop east of 401/407 merge, on 401)
#
# Full corridor: ~170 km via 401, ~180 km via 407.
# The 407 route uses:
#   TOLL section : 407 ETR (Hwy 403 → Hwy 412, private concession)
#   FREE section : 407 East (Hwy 412 → Hwy 418, Ontario-built, no toll)
# Both are real ONroute stops suitable for in-person iPad surveys.

ORIGIN = {
    "lat": float(os.getenv("ORIGIN_LAT", "43.5665")),
    "lng": float(os.getenv("ORIGIN_LNG", "-79.8228")),
    "label": "Petro-Canada & Petro-Pass Truck Stop — Hornby",
    "address": "7443 Trafalgar Rd, Hornby, ON L0P 1E0",
}
DESTINATION = {
    "lat": float(os.getenv("DEST_LAT", "43.8919")),
    "lng": float(os.getenv("DEST_LNG", "-78.6918")),
    "label": "Petro-Pass Truck Stop — Bowmanville",
    "address": "2475 Energy Dr, Bowmanville, ON L1C 6Z9",
}

# Waypoints to force Google Maps onto the correct corridor.
#
# 401 (no-toll route): avoid=tolls parameter handles this — no waypoint needed.
#   Google will return the fully toll-free 401 through Toronto.
#   Empty list → Google picks the best toll-free path from Hornby → Bowmanville.
#
# 407 (toll route): one waypoint on 407 ETR forces the toll bypass.
#   407 ETR @ Hwy 400 interchange (Vaughan) is well inside the toll zone
#   and forces Google to commit to 407 ETR rather than any 401 shortcut.
#   The free 407 East extension (Hwy 412 → Hwy 418) will be included naturally.
WAYPOINTS_401 = []   # avoid=tolls in API call guarantees toll-free 401 route
WAYPOINTS_407 = [
    {"lat": 43.8200, "lng": -79.5400, "label": "407 ETR @ Hwy 400 (Vaughan)"},
]

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
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "history.db")

import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Route definition ---
# West: Truck parking lot, Halton Hills (near 401/407 divergence at Hwy 403)
# East: 570 Rundle Rd, Bowmanville (near 401/407 convergence at Hwy 418)
# These are the real survey sites where iPad data collection happens.
#
# The 407 route has TWO sections:
#   TOLL: 407 ETR from Hwy 403 → Hwy 412 (private concession)
#   FREE: 407 East from Hwy 412 → Hwy 418 (Ontario-built, no toll)
# The east-side decision point is Hwy 418, NOT Hwy 412.

ORIGIN = {
    "lat": float(os.getenv("ORIGIN_LAT", "43.5732")),
    "lng": float(os.getenv("ORIGIN_LNG", "-79.8310")),
    "label": "Truck Stop — Halton Hills",
}
DESTINATION = {
    "lat": float(os.getenv("DEST_LAT", "43.8837")),
    "lng": float(os.getenv("DEST_LNG", "-78.7342")),
    "label": "570 Rundle Rd — Bowmanville",
}

# Waypoints to force Google Maps onto the correct corridor.
# 401 — straight through Toronto core
# 407 — toll 407 ETR (via Hwy 404) + free 407 East (via Hwy 418)
WAYPOINTS_401 = [
    {"lat": 43.7610, "lng": -79.4110, "label": "401 @ Yonge St (Toronto)"},
]
WAYPOINTS_407 = [
    {"lat": 43.8360, "lng": -79.3960, "label": "407 ETR @ Hwy 404 (toll section)"},
    {"lat": 43.9170, "lng": -78.7550, "label": "407 East @ Hwy 418 (free section)"},
]

# Free-flow travel times (minutes) — decision segment only (~120km via 401, ~100km via 407)
FREEFLOW_401 = 65.0
FREEFLOW_407 = 55.0

# Route distances (km) — decision segment only, overridden by API when available
DISTANCE_401_KM = 120.0
DISTANCE_407_KM = 100.0

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

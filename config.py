import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Route definition ---
# DECISION SEGMENT ONLY — the part where 401 and 407 diverge and reconverge.
#
# Origin  = 401 at Hwy 403 junction (Milton) — last exit to take 407
# Dest    = 401 at Hwy 412 junction (Whitby) — where 407 traffic rejoins 401
#
# Everything west of the origin and east of the destination is the SAME
# road for both choices, so it's excluded from the comparison.
#
# Survey iPads are at ONroute Cambridge (west) and ONroute Newcastle (east).

ORIGIN = {
    "lat": float(os.getenv("ORIGIN_LAT", "43.5250")),
    "lng": float(os.getenv("ORIGIN_LNG", "-79.7150")),
    "label": "401 @ Hwy 403 (Milton)",
}
DESTINATION = {
    "lat": float(os.getenv("DEST_LAT", "43.8650")),
    "lng": float(os.getenv("DEST_LNG", "-79.0200")),
    "label": "401 @ Hwy 412 (Whitby)",
}

# Survey locations (truck stops where iPads would be placed)
SURVEY_WEST = {"lat": 43.4353, "lng": -80.2459, "label": "ONroute Cambridge North"}
SURVEY_EAST = {"lat": 43.9214, "lng": -78.5409, "label": "ONroute Newcastle"}

# Waypoints to force Google Maps onto the correct corridor.
# One point per route at the point of maximum north–south separation.
# 401 — through Toronto core
# 407 — bypass north of Toronto
WAYPOINTS_401 = [
    {"lat": 43.7610, "lng": -79.4110, "label": "401 @ Yonge St (Toronto)"},
]
WAYPOINTS_407 = [
    {"lat": 43.8360, "lng": -79.3960, "label": "407 @ Hwy 404 (Richmond Hill)"},
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

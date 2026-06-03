import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Route definition ---
# Western endpoint: ONroute Cambridge North (truck stop on 401, Cambridge ON)
# Eastern endpoint: Newcastle Travel Plaza (ONroute on 401, Newcastle ON)
# These are real truck stops where drivers can be surveyed in person.
# The 401-vs-407 decision happens between the Hwy 403 and Hwy 412 junctions.

ORIGIN = {
    "lat": float(os.getenv("ORIGIN_LAT", "43.4353")),
    "lng": float(os.getenv("ORIGIN_LNG", "-80.2459")),
    "label": "ONroute Cambridge North",
}
DESTINATION = {
    "lat": float(os.getenv("DEST_LAT", "43.9214")),
    "lng": float(os.getenv("DEST_LNG", "-78.5409")),
    "label": "ONroute Newcastle",
}

# Waypoints to force the correct route through the corridor
WAYPOINT_401 = {"lat": 43.6550, "lng": -79.3830, "label": "401 @ DVP (Toronto)"}
WAYPOINT_407 = {"lat": 43.8200, "lng": -79.5400, "label": "407 @ Hwy 400 (Vaughan)"}

# Free-flow travel times (minutes) -- used when API is unavailable and as baseline
# Cambridge to Newcastle is ~170km via 401, ~180km via 407
FREEFLOW_401 = 80.0
FREEFLOW_407 = 75.0

# Route distances (km) -- approximate, overridden by API when available
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

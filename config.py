import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# --- Route definition ---
# Western decision point: Hwy 401 at Hwy 403 junction (Milton/Burlington)
# Eastern decision point: Hwy 401 at Hwy 412 junction (Whitby)
# These are where a pass-through truck decides 401-through-Toronto vs 407-bypass.

ORIGIN = {
    "lat": float(os.getenv("ORIGIN_LAT", "43.5100")),
    "lng": float(os.getenv("ORIGIN_LNG", "-79.8900")),
    "label": "Hwy 401 @ Hwy 403 (Milton)",
}
DESTINATION = {
    "lat": float(os.getenv("DEST_LAT", "43.8700")),
    "lng": float(os.getenv("DEST_LNG", "-78.9400")),
    "label": "Hwy 401 @ Hwy 412 (Whitby)",
}

# Waypoints to force the correct route
WAYPOINT_401 = {"lat": 43.6550, "lng": -79.3830, "label": "401 @ DVP (Toronto)"}
WAYPOINT_407 = {"lat": 43.8200, "lng": -79.5400, "label": "407 @ Hwy 400 (Vaughan)"}

# Free-flow travel times (minutes) -- used when API is unavailable and as baseline
FREEFLOW_401 = 55.0
FREEFLOW_407 = 50.0

# Route distances (km) -- approximate, overridden by API when available
DISTANCE_401_KM = 72.0
DISTANCE_407_KM = 82.0

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
COLLECT_INTERVAL_MINUTES = 5
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "history.db")

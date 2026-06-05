"""
SQLite / Turso storage for historical traffic + VOT snapshots.

Connection strategy
───────────────────
  TURSO_DATABASE_URL + TURSO_AUTH_TOKEN set  →  Turso (hosted libSQL, survives Railway deploys)
  Otherwise                                  →  local SQLite file at DB_PATH (dev / testing)
"""

import os
import json
from datetime import datetime, timedelta
import config

# ── Backend selection ─────────────────────────────────────────────────────────
_USE_TURSO = bool(os.getenv("TURSO_DATABASE_URL") and os.getenv("TURSO_AUTH_TOKEN"))

if _USE_TURSO:
    import libsql_experimental as libsql  # type: ignore

    def _conn():
        return libsql.connect(
            os.getenv("TURSO_DATABASE_URL"),
            auth_token=os.getenv("TURSO_AUTH_TOKEN"),
        )

else:
    import sqlite3

    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

    def _conn():
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


# ── Row helpers ───────────────────────────────────────────────────────────────
# sqlite3.Row supports dict() and .keys(); libsql rows are plain tuples.
# These helpers normalise both so the rest of the code is backend-agnostic.

def _rows(cursor) -> list[dict]:
    """Return fetchall() as list[dict] for both backends."""
    data = cursor.fetchall()
    if not data:
        return []
    if hasattr(data[0], "keys"):          # sqlite3.Row
        return [dict(r) for r in data]
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in data]


def _one(cursor) -> dict | None:
    """Return fetchone() as dict (or None) for both backends."""
    row = cursor.fetchone()
    if row is None:
        return None
    if hasattr(row, "keys"):              # sqlite3.Row
        return dict(row)
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


# ── Schema init ───────────────────────────────────────────────────────────────

def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                hour INTEGER NOT NULL,
                minute INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                is_weekday INTEGER NOT NULL,
                source TEXT NOT NULL,
                tt_401 REAL,
                tt_407 REAL,
                delay_401 REAL,
                delay_407 REAL,
                distance_401_km REAL,
                distance_407_km REAL,
                toll_cost REAL,
                toll_period TEXT,
                time_saved REAL,
                market_vot REAL,
                choice_prob_toll REAL,
                pct_willing REAL,
                raw_json TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_ts   ON snapshots(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_hour ON snapshots(hour, is_weekday)")


def save_snapshot(data: dict):
    with _conn() as conn:
        now = datetime.fromisoformat(data["fetched_at"]) if "fetched_at" in data else datetime.now()
        r401 = data.get("route_401", {})
        r407 = data.get("route_407", {})
        toll = data.get("toll", {})
        vot  = data.get("vot", {})

        conn.execute("""
            INSERT INTO snapshots (
                timestamp, hour, minute, day_of_week, is_weekday, source,
                tt_401, tt_407, delay_401, delay_407,
                distance_401_km, distance_407_km,
                toll_cost, toll_period,
                time_saved, market_vot, choice_prob_toll, pct_willing,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now.isoformat(),
            now.hour,
            now.minute,
            now.weekday(),
            1 if now.weekday() < 5 else 0,
            data.get("source", "unknown"),
            r401.get("tt_minutes"),
            r407.get("tt_minutes"),
            r401.get("delay_minutes"),
            r407.get("delay_minutes"),
            r401.get("distance_km"),
            r407.get("distance_km"),
            toll.get("total"),
            toll.get("time_period"),
            vot.get("time_saved_minutes"),
            vot.get("market_vot"),
            vot.get("choice_probability_toll"),
            vot.get("pct_willing"),
            json.dumps(data),
        ))


def get_recent(hours: int = 24) -> list[dict]:
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with _conn() as conn:
        cur = conn.execute("""
            SELECT timestamp, tt_401, tt_407, delay_401, delay_407,
                   toll_cost, toll_period, time_saved, market_vot,
                   choice_prob_toll, pct_willing, source
            FROM snapshots
            WHERE timestamp > ?
            ORDER BY timestamp ASC
        """, (cutoff,))
        return _rows(cur)


def get_hourly_averages(weekday: bool = True) -> list[dict]:
    """Average conditions by hour of day — used for the 24h projection overlay."""
    is_wd = 1 if weekday else 0
    with _conn() as conn:
        cur = conn.execute("""
            SELECT hour,
                   AVG(tt_401)           as avg_tt_401,
                   AVG(tt_407)           as avg_tt_407,
                   AVG(delay_401)        as avg_delay_401,
                   AVG(delay_407)        as avg_delay_407,
                   AVG(toll_cost)        as avg_toll,
                   AVG(time_saved)       as avg_time_saved,
                   AVG(market_vot)       as avg_market_vot,
                   AVG(choice_prob_toll) as avg_choice_prob,
                   AVG(pct_willing)      as avg_pct_willing,
                   COUNT(*)              as n_observations
            FROM snapshots
            WHERE is_weekday = ?
            GROUP BY hour
            ORDER BY hour
        """, (is_wd,))
        return _rows(cur)


def get_snapshot_count() -> int:
    with _conn() as conn:
        cur = conn.execute("SELECT COUNT(*) as cnt FROM snapshots")
        row = _one(cur)
    return row["cnt"] if row else 0


def get_history_range(range_key: str) -> list[dict]:
    """
    Historical data aggregated by time range.
    '24h'  → raw 3-min snapshots from last 24 h
    '7d'   → hourly averages from last 7 days
    '30d'  → 4-hourly averages from last 30 days
    '365d' → daily averages from last 365 days
    """
    now = datetime.now()

    if range_key == "24h":
        cutoff = (now - timedelta(hours=24)).isoformat()
        with _conn() as conn:
            cur = conn.execute("""
                SELECT timestamp as time_label,
                       tt_401, tt_407, toll_cost, time_saved,
                       market_vot, choice_prob_toll, source
                FROM snapshots WHERE timestamp > ?
                ORDER BY timestamp ASC
            """, (cutoff,))
            return _rows(cur)

    elif range_key == "7d":
        cutoff = (now - timedelta(days=7)).isoformat()
        with _conn() as conn:
            cur = conn.execute("""
                SELECT
                    substr(timestamp, 1, 13) || ':00' as time_label,
                    AVG(tt_401) as tt_401, AVG(tt_407) as tt_407,
                    AVG(toll_cost) as toll_cost, AVG(time_saved) as time_saved,
                    AVG(market_vot) as market_vot, AVG(choice_prob_toll) as choice_prob_toll,
                    'aggregated' as source, COUNT(*) as n
                FROM snapshots WHERE timestamp > ?
                GROUP BY substr(timestamp, 1, 13)
                ORDER BY time_label ASC
            """, (cutoff,))
            return _rows(cur)

    elif range_key == "30d":
        cutoff = (now - timedelta(days=30)).isoformat()
        with _conn() as conn:
            cur = conn.execute("""
                SELECT
                    substr(timestamp, 1, 10) || ' ' ||
                    printf('%02d', (hour / 4) * 4) || ':00' as time_label,
                    AVG(tt_401) as tt_401, AVG(tt_407) as tt_407,
                    AVG(toll_cost) as toll_cost, AVG(time_saved) as time_saved,
                    AVG(market_vot) as market_vot, AVG(choice_prob_toll) as choice_prob_toll,
                    'aggregated' as source, COUNT(*) as n
                FROM snapshots WHERE timestamp > ?
                GROUP BY substr(timestamp, 1, 10), (hour / 4)
                ORDER BY time_label ASC
            """, (cutoff,))
            return _rows(cur)

    else:  # 365d
        cutoff = (now - timedelta(days=365)).isoformat()
        with _conn() as conn:
            cur = conn.execute("""
                SELECT
                    substr(timestamp, 1, 10) as time_label,
                    AVG(tt_401) as tt_401, AVG(tt_407) as tt_407,
                    AVG(toll_cost) as toll_cost, AVG(time_saved) as time_saved,
                    AVG(market_vot) as market_vot, AVG(choice_prob_toll) as choice_prob_toll,
                    'aggregated' as source, COUNT(*) as n
                FROM snapshots WHERE timestamp > ?
                GROUP BY substr(timestamp, 1, 10)
                ORDER BY time_label ASC
            """, (cutoff,))
            return _rows(cur)


# ── Survey responses ──────────────────────────────────────────────────────────

def init_survey_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS survey_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                lat REAL,
                lng REAL,
                location_name TEXT,
                direction TEXT DEFAULT 'east',
                tt_401 REAL,
                tt_407 REAL,
                toll_cost REAL,
                time_saved REAL,
                market_vot REAL,
                time_period TEXT,
                vehicle_type TEXT,
                trip_type TEXT,
                frequency TEXT,
                choice_if_company_pays TEXT,
                choice_if_self_pays TEXT,
                user_agent TEXT
            )
        """)
        # Migration: add direction column to older DBs (no-op if already present)
        try:
            conn.execute("ALTER TABLE survey_responses ADD COLUMN direction TEXT DEFAULT 'east'")
        except Exception:
            pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_survey_ts ON survey_responses(timestamp)")


def save_survey_response(data: dict):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO survey_responses (
                timestamp, lat, lng, location_name, direction,
                tt_401, tt_407, toll_cost, time_saved, market_vot, time_period,
                vehicle_type, trip_type, frequency,
                choice_if_company_pays, choice_if_self_pays,
                user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            data.get("lat"),
            data.get("lng"),
            data.get("location_name"),
            data.get("direction", "east"),
            data.get("tt_401"),
            data.get("tt_407"),
            data.get("toll_cost"),
            data.get("time_saved"),
            data.get("market_vot"),
            data.get("time_period"),
            data.get("vehicle_type"),
            data.get("trip_type"),
            data.get("frequency"),
            data.get("choice_if_company_pays"),
            data.get("choice_if_self_pays"),
            data.get("user_agent"),
        ))


def get_survey_stats() -> dict:
    with _conn() as conn:
        total_row = _one(conn.execute("SELECT COUNT(*) as cnt FROM survey_responses"))
        total = total_row["cnt"] if total_row else 0

        if total == 0:
            return {
                "total_responses": 0,
                "company_pays_yes_pct": 0,
                "self_pays_yes_pct": 0,
                "by_vehicle_type": {},
                "by_trip_type": {},
                "by_time_period": {},
            }

        company_yes = _one(conn.execute(
            "SELECT COUNT(*) as cnt FROM survey_responses WHERE choice_if_company_pays = 'yes'"
        ))["cnt"]
        self_yes = _one(conn.execute(
            "SELECT COUNT(*) as cnt FROM survey_responses WHERE choice_if_self_pays = 'yes'"
        ))["cnt"]

        vt_rows = _rows(conn.execute("""
            SELECT vehicle_type,
                   COUNT(*) as n,
                   SUM(CASE WHEN choice_if_company_pays = 'yes' THEN 1 ELSE 0 END) as company_yes,
                   SUM(CASE WHEN choice_if_self_pays    = 'yes' THEN 1 ELSE 0 END) as self_yes
            FROM survey_responses
            GROUP BY vehicle_type
        """))

        tp_rows = _rows(conn.execute("""
            SELECT time_period,
                   COUNT(*) as n,
                   SUM(CASE WHEN choice_if_company_pays = 'yes' THEN 1 ELSE 0 END) as company_yes
            FROM survey_responses
            GROUP BY time_period
        """))

        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        recent_row = _one(conn.execute(
            "SELECT COUNT(*) as cnt FROM survey_responses WHERE timestamp > ?", (cutoff,)
        ))
        recent = recent_row["cnt"] if recent_row else 0

    return {
        "total_responses": total,
        "responses_24h": recent,
        "company_pays_yes_pct": round(company_yes / total * 100, 1) if total else 0,
        "self_pays_yes_pct":    round(self_yes    / total * 100, 1) if total else 0,
        "by_vehicle_type": {
            r["vehicle_type"]: {
                "n": r["n"],
                "company_yes_pct": round(r["company_yes"] / r["n"] * 100, 1) if r["n"] else 0,
            }
            for r in vt_rows if r["vehicle_type"]
        },
        "by_time_period": {
            r["time_period"]: {
                "n": r["n"],
                "company_yes_pct": round(r["company_yes"] / r["n"] * 100, 1) if r["n"] else 0,
            }
            for r in tp_rows if r["time_period"]
        },
    }


# ── Auto-init on import ───────────────────────────────────────────────────────
init_db()
init_survey_db()

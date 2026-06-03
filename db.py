"""SQLite storage for historical traffic + VOT snapshots."""

import sqlite3
import os
import json
from datetime import datetime, timedelta
import config

os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)


def _conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


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
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_hour ON snapshots(hour, is_weekday)
        """)


def save_snapshot(data: dict):
    with _conn() as conn:
        now = datetime.fromisoformat(data["fetched_at"]) if "fetched_at" in data else datetime.now()
        r401 = data.get("route_401", {})
        r407 = data.get("route_407", {})
        toll = data.get("toll", {})
        vot = data.get("vot", {})

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
        rows = conn.execute("""
            SELECT timestamp, tt_401, tt_407, delay_401, delay_407,
                   toll_cost, toll_period, time_saved, market_vot,
                   choice_prob_toll, pct_willing, source
            FROM snapshots
            WHERE timestamp > ?
            ORDER BY timestamp ASC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def get_hourly_averages(weekday: bool = True) -> list[dict]:
    """Get average conditions by hour from historical data, for the 24h projection overlay."""
    is_wd = 1 if weekday else 0
    with _conn() as conn:
        rows = conn.execute("""
            SELECT hour,
                   AVG(tt_401) as avg_tt_401,
                   AVG(tt_407) as avg_tt_407,
                   AVG(delay_401) as avg_delay_401,
                   AVG(delay_407) as avg_delay_407,
                   AVG(toll_cost) as avg_toll,
                   AVG(time_saved) as avg_time_saved,
                   AVG(market_vot) as avg_market_vot,
                   AVG(choice_prob_toll) as avg_choice_prob,
                   AVG(pct_willing) as avg_pct_willing,
                   COUNT(*) as n_observations
            FROM snapshots
            WHERE is_weekday = ?
            GROUP BY hour
            ORDER BY hour
        """, (is_wd,)).fetchall()
    return [dict(r) for r in rows]


def get_snapshot_count() -> int:
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM snapshots").fetchone()
    return row["cnt"]


init_db()

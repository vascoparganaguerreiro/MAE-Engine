"""
Local SQLite persistence for the single-user Apex Engine build.
Handles database migrations, daily metrics storage, workouts, biomarkers, and settings.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "apex_data.db"
DB_PATH = Path(os.environ.get("APEX_DB_PATH", str(DEFAULT_DB))).expanduser()

DAILY_FIELDS = [
    "hrv", "rhr", "sleep_score", "sleep_hours", "sleep_target_hours",
    "soreness", "stress", "mood", "vendor_readiness",
    "hrv_source", "rhr_source", "sleep_score_source", "sleep_hours_source", "vendor_readiness_source"
]


def get_connection() -> sqlite3.Connection:
    if DB_PATH.parent != BASE_DIR:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabela diária de métricas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                date TEXT PRIMARY KEY,
                hrv REAL,
                rhr REAL,
                sleep_score REAL,
                sleep_hours REAL,
                sleep_target_hours REAL,
                soreness INTEGER,
                stress INTEGER,
                mood INTEGER,
                vendor_readiness REAL,
                hrv_source TEXT,
                rhr_source TEXT,
                sleep_score_source TEXT,
                sleep_hours_source TEXT,
                vendor_readiness_source TEXT,
                updated_at TEXT
            );
        """)

        # Migração automática de schema
        cursor.execute("PRAGMA table_info(daily_metrics);")
        columns = [row["name"] for row in cursor.fetchall()]
        if "sleep_target_hours" not in columns:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN sleep_target_hours REAL;")
        if "vendor_readiness_source" not in columns:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN vendor_readiness_source TEXT;")

        # Tabela de carga de treino diária
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_days (
                date TEXT PRIMARY KEY,
                daily_load REAL,
                source TEXT,
                notes TEXT,
                updated_at TEXT
            );
        """)

        # Tabela de treinos individuais (sRPE)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                title TEXT,
                duration_min REAL,
                rpe REAL,
                load_ua REAL,
                created_at TEXT
            );
        """)

        # Definções do utilizador
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # Biomarcadores de saúde e longevidade
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS biomarkers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                key TEXT,
                value REAL,
                unit TEXT,
                ref_low REAL,
                ref_high REAL,
                note TEXT
            );
        """)

        # Provas e eventos (Race Hub)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                race_date TEXT,
                dist_km REAL,
                priority TEXT,
                event_type TEXT
            );
        """)

        # Sapatilhas e equipamento
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT,
                max_km REAL,
                km_used REAL DEFAULT 0.0
            );
        """)
        conn.commit()


def get_setting(key: str, default: Any = None) -> Any:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row and row["value"]:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default


def set_setting(key: str, value: Any):
    val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value;
        """, (key, val_str))
        conn.commit()


def fetch_daily_metrics(start_date: date, end_date: date) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM daily_metrics WHERE date >= ? AND date <= ? ORDER BY date ASC",
            conn,
            params=(start_date.isoformat(), end_date.isoformat())
        )


def upsert_daily_metrics(target_date: date, metrics: Dict[str, Any], source: str = "manual"):
    now_str = datetime.now().isoformat(timespec="seconds")
    d_str = target_date.isoformat()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (d_str,))
        existing = cursor.fetchone()
        
        data: Dict[str, Any] = dict(existing) if existing else {"date": d_str}
        
        for k, v in metrics.items():
            if k in DAILY_FIELDS:
                # Preserva valores existentes se a nova métrica for nula / N/A
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    data[k] = v
                    if source:
                        data[f"{k}_source"] = source
                    
        data["updated_at"] = now_str
        
        cols = list(data.keys())
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "date"])
        
        sql = f"""
            INSERT INTO daily_metrics ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {updates};
        """
        cursor.execute(sql, list(data.values()))
        conn.commit()


def bulk_insert_garmin_history(records: List[Dict[str, Any]]) -> int:
    count = 0
    now_str = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cursor = conn.cursor()
        for r in records:
            d_str = r.get("date")
            if not d_str:
                continue
            cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (d_str,))
            existing = cursor.fetchone()
            data: Dict[str, Any] = dict(existing) if existing else {"date": d_str}
            
            for k in ["hrv", "rhr", "sleep_score", "sleep_hours", "sleep_target_hours", "vendor_readiness"]:
                if r.get(k) is not None:
                    data[k] = r[k]
                    data[f"{k}_source"] = "garmin_import"
            data["updated_at"] = now_str
            
            cols = list(data.keys())
            placeholders = ", ".join(["?"] * len(cols))
            updates = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "date"])
            
            sql = f"""
                INSERT INTO daily_metrics ({", ".join(cols)})
                VALUES ({placeholders})
                ON CONFLICT(date) DO UPDATE SET {updates};
            """
            cursor.execute(sql, list(data.values()))
            count += 1
        conn.commit()
    return count


def fetch_training_days(start_date: date, end_date: date) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM training_days WHERE date >= ? AND date <= ? ORDER BY date ASC",
            conn,
            params=(start_date.isoformat(), end_date.isoformat())
        )


def set_training_day(target_date: date, load_val: float, source: str = "manual", notes: str = ""):
    now_str = datetime.now().isoformat(timespec="seconds")
    d_str = target_date.isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO training_days (date, daily_load, source, notes, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET daily_load=excluded.daily_load, source=excluded.source, notes=excluded.notes, updated_at=excluded.updated_at;
        """, (d_str, load_val, source, notes, now_str))
        conn.commit()


def mark_rest_day(target_date: date):
    set_training_day(target_date, 0.0, source="manual", notes="Descanso confirmado")


def log_workout(target_date: date, title: str, duration_min: float, rpe: float) -> Dict[str, Any]:
    now_str = datetime.now().isoformat(timespec="seconds")
    d_str = target_date.isoformat()
    session_load = float(duration_min) * float(rpe)
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO workouts (date, title, duration_min, rpe, load_ua, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (d_str, title, duration_min, rpe, session_load, now_str))
        
        cursor.execute("SELECT SUM(load_ua) as total FROM workouts WHERE date = ?", (d_str,))
        row = cursor.fetchone()
        daily_total = float(row["total"]) if row and row["total"] is not None else session_load
        
        cursor.execute("""
            INSERT INTO training_days (date, daily_load, source, notes, updated_at)
            VALUES (?, ?, 'srpe', 'Calculado via sessões sRPE', ?)
            ON CONFLICT(date) DO UPDATE SET daily_load=?, source='srpe', updated_at=?;
        """, (d_str, daily_total, now_str, daily_total, now_str))
        
        conn.commit()
        return {"session_load": session_load, "daily_total": daily_total}


def fetch_workouts(start_date: date, end_date: date) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM workouts WHERE date >= ? AND date <= ? ORDER BY date DESC",
            conn,
            params=(start_date.isoformat(), end_date.isoformat())
        )


def add_biomarker(b_date: date, key: str, val: float, unit: str, low: Optional[float], high: Optional[float], note: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO biomarkers (date, key, value, unit, ref_low, ref_high, note)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (b_date.isoformat(), key, val, unit, low, high, note))
        conn.commit()


def fetch_biomarkers() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM biomarkers ORDER BY date DESC", conn)


def add_race(name: str, r_date: date, dist_km: float, priority: str, event_type: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO races (name, race_date, dist_km, priority, event_type)
            VALUES (?, ?, ?, ?, ?);
        """, (name, r_date.isoformat(), dist_km, priority, event_type))
        conn.commit()


def fetch_races() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM races ORDER BY race_date ASC", conn)


def add_shoe(model: str, max_km: float):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO shoes (model, max_km, km_used) VALUES (?, ?, 0.0);", (model, max_km))
        conn.commit()


def increment_shoe_km(shoe_id: int, added_km: float):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE shoes SET km_used = km_used + ? WHERE id = ?;", (added_km, shoe_id))
        conn.commit()


def fetch_shoes() -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM shoes ORDER BY id ASC", conn)

"""Local SQLite persistence for the single-user Apex build.

Set APEX_DB_PATH to place the database on a persistent local volume.
Do not expose this shared database to multiple public users without authentication
and per-user data isolation.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "apex_data" / "apex.db"
DB_PATH = Path(os.environ.get("APEX_DB_PATH", str(DEFAULT_DB))).expanduser()

DAILY_FIELDS = {
    "hrv": (0, 300),
    "rhr": (25, 220),
    "sleep_score": (0, 100),
    "sleep_hours": (0, 24),
    "soreness": (1, 5),
    "stress": (1, 5),
    "mood": (1, 5),
    "vendor_readiness": (0, 100),
}


def _iso_day(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    parsed = date.fromisoformat(str(value))
    return parsed.isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_metrics (
                date TEXT PRIMARY KEY,
                hrv REAL, hrv_source TEXT,
                rhr REAL, rhr_source TEXT,
                sleep_score REAL, sleep_score_source TEXT,
                sleep_hours REAL, sleep_hours_source TEXT,
                soreness INTEGER, soreness_source TEXT,
                stress INTEGER, stress_source TEXT,
                mood INTEGER, mood_source TEXT,
                vendor_readiness REAL, vendor_readiness_source TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS training_days (
                date TEXT PRIMARY KEY,
                daily_load REAL NOT NULL CHECK(daily_load >= 0),
                source TEXT NOT NULL,
                notes TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS workout_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                duration_min REAL NOT NULL CHECK(duration_min > 0),
                rpe REAL NOT NULL CHECK(rpe >= 1 AND rpe <= 10),
                load_ua REAL NOT NULL CHECK(load_ua >= 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS biomarkers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                key TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                ref_low REAL,
                ref_high REAL,
                note TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                race_date TEXT NOT NULL,
                dist_km REAL NOT NULL CHECK(dist_km > 0),
                priority TEXT NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                km_used REAL NOT NULL DEFAULT 0 CHECK(km_used >= 0),
                max_km REAL NOT NULL CHECK(max_km > 0),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def upsert_daily_metrics(day: Any, metrics: Dict[str, Any], source: str = "manual") -> None:
    iso = _iso_day(day)
    valid: Dict[str, Any] = {}
    for field, value in metrics.items():
        if field not in DAILY_FIELDS or value is None or str(value).strip() == "":
            continue
        low, high = DAILY_FIELDS[field]
        numeric = float(value)
        if not low <= numeric <= high:
            continue
        valid[field] = int(numeric) if field in {"soreness", "stress", "mood"} else numeric
    if not valid:
        return

    now = datetime.now().isoformat(timespec="seconds")
    columns = ["date"]
    values: list[Any] = [iso]
    updates = []
    for field, value in valid.items():
        columns.extend([field, f"{field}_source"])
        values.extend([value, source])
        updates.extend([
            f"{field}=excluded.{field}",
            f"{field}_source=excluded.{field}_source",
        ])
    columns.append("updated_at")
    values.append(now)
    sql = (
        f"INSERT INTO daily_metrics ({','.join(columns)}) VALUES ({','.join(['?'] * len(columns))}) "
        f"ON CONFLICT(date) DO UPDATE SET {','.join(updates)}, updated_at=excluded.updated_at"
    )
    with _connect() as conn:
        conn.execute(sql, values)


def get_last_logged_date() -> Optional[date]:
    """Retorna a data mais recente registada no SQLite."""
    with _connect() as conn:
        row = conn.execute("SELECT MAX(date) AS max_date FROM daily_metrics").fetchone()
        if row and row["max_date"]:
            try:
                return date.fromisoformat(row["max_date"])
            except ValueError:
                return None
    return None


def bulk_insert_garmin_history(records: List[Dict[str, Any]], source: str = "garmin_import") -> int:
    """Insere em lote registos lidos de um ficheiro exportado da Garmin."""
    if not records:
        return 0

    now = datetime.now().isoformat(timespec="seconds")
    inserted_count = 0

    with _connect() as conn:
        for rec in records:
            day_str = rec.get("date")
            if not day_str:
                continue
            try:
                iso = _iso_day(day_str)
            except ValueError:
                continue

            valid: Dict[str, Any] = {}
            for field, (low, high) in DAILY_FIELDS.items():
                val = rec.get(field)
                if val is not None and str(val).strip() != "":
                    try:
                        num = float(val)
                        if low <= num <= high:
                            valid[field] = int(num) if field in {"soreness", "stress", "mood"} else num
                    except (TypeError, ValueError):
                        pass

            if not valid:
                continue

            columns = ["date"]
            values: List[Any] = [iso]
            updates = []
            for f_name, f_val in valid.items():
                columns.extend([f_name, f"{f_name}_source"])
                values.extend([f_val, source])
                updates.extend([
                    f"{f_name}=excluded.{f_name}",
                    f"{f_name}_source=excluded.{f_name}_source",
                ])
            columns.append("updated_at")
            values.append(now)

            sql = (
                f"INSERT INTO daily_metrics ({','.join(columns)}) VALUES ({','.join(['?'] * len(columns))}) "
                f"ON CONFLICT(date) DO UPDATE SET {','.join(updates)}, updated_at=excluded.updated_at"
            )
            conn.execute(sql, values)
            inserted_count += 1

    return inserted_count


def fetch_daily_metrics(start: Any, end: Any) -> pd.DataFrame:
    start_iso, end_iso = _iso_day(start), _iso_day(end)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_metrics WHERE date BETWEEN ? AND ? ORDER BY date",
            (start_iso, end_iso),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_setting(key: str, default: Any = None) -> Any:
    with _connect() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value_json"])
    except (TypeError, json.JSONDecodeError):
        return default


def set_setting(key: str, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, default=str)
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
            (key, payload, now),
        )


def set_training_day(day: Any, load: float, source: str = "manual", notes: str = "") -> None:
    iso = _iso_day(day)
    load = float(load)
    if load < 0:
        raise ValueError("Daily load cannot be negative")
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        existing = conn.execute("SELECT source FROM training_days WHERE date=?", (iso,)).fetchone()
        if existing and existing["source"] != source:
            raise ValueError(
                f"Já existe carga para {iso} com origem '{existing['source']}'. "
                "Não mistures carga diária manual com sRPE no mesmo dia."
            )
        conn.execute(
            "INSERT INTO training_days(date,daily_load,source,notes,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET daily_load=excluded.daily_load,source=excluded.source,"
            "notes=excluded.notes,updated_at=excluded.updated_at",
            (iso, load, source, notes, now),
        )


def mark_rest_day(day: Any) -> None:
    set_training_day(day, 0.0, source="manual_rest", notes="Dia de descanso confirmado pelo utilizador")


def fetch_training_days(start: Any, end: Any) -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date,daily_load,source,notes FROM training_days WHERE date BETWEEN ? AND ? ORDER BY date",
            (_iso_day(start), _iso_day(end)),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def log_workout(day: Any, title: str, duration_min: float, rpe: float) -> Dict[str, float]:
    iso = _iso_day(day)
    title = str(title).strip() or "Sessão de treino"
    duration_min, rpe = float(duration_min), float(rpe)
    if duration_min <= 0 or not 1 <= rpe <= 10:
        raise ValueError("Duration must be positive and RPE must be between 1 and 10")
    load = round(duration_min * rpe, 1)
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        existing = conn.execute("SELECT source FROM training_days WHERE date=?", (iso,)).fetchone()
        if existing and existing["source"] not in ("session_rpe",):
            raise ValueError(
                f"Já existe carga diária para {iso} com origem '{existing['source']}'. "
                "Para evitar dupla contagem, não podes adicionar sRPE a esse dia."
            )
        conn.execute(
            "INSERT INTO workout_sessions(date,title,duration_min,rpe,load_ua,created_at) VALUES(?,?,?,?,?,?)",
            (iso, title, duration_min, rpe, load, now),
        )
        total = conn.execute(
            "SELECT SUM(load_ua) AS total FROM workout_sessions WHERE date=?", (iso,)
        ).fetchone()["total"]
        conn.execute(
            "INSERT INTO training_days(date,daily_load,source,notes,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET daily_load=excluded.daily_load,updated_at=excluded.updated_at",
            (iso, float(total or 0), "session_rpe", "Carga agregada de sessões sRPE", now),
        )
    return {"session_load": load, "daily_total": round(float(total or 0), 1)}


def fetch_workouts(start: Any, end: Any) -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id,date,title,duration_min,rpe,load_ua FROM workout_sessions "
            "WHERE date BETWEEN ? AND ? ORDER BY date,id",
            (_iso_day(start), _iso_day(end)),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def add_biomarker(day: Any, key: str, value: float, unit: str,
                  ref_low: Optional[float] = None, ref_high: Optional[float] = None,
                  note: str = "") -> None:
    if ref_low is not None and ref_high is not None and float(ref_low) >= float(ref_high):
        raise ValueError("Lower reference limit must be below upper reference limit")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO biomarkers(date,key,value,unit,ref_low,ref_high,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (_iso_day(day), str(key), float(value), str(unit), ref_low, ref_high, str(note),
             datetime.now().isoformat(timespec="seconds")),
        )


def fetch_biomarkers() -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM biomarkers ORDER BY date DESC,id DESC").fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def add_race(name: str, race_day: Any, dist_km: float, priority: str, event_type: str) -> None:
    if not str(name).strip() or float(dist_km) <= 0:
        raise ValueError("Race name and positive distance are required")
    if priority not in {"A", "B", "C"}:
        raise ValueError("Priority must be A, B or C")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO races(name,race_date,dist_km,priority,event_type,created_at) VALUES(?,?,?,?,?,?)",
            (str(name).strip(), _iso_day(race_day), float(dist_km), priority, str(event_type),
             datetime.now().isoformat(timespec="seconds")),
        )


def fetch_races() -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM races ORDER BY race_date,priority").fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def add_shoe(model: str, max_km: float) -> None:
    if not str(model).strip() or float(max_km) <= 0:
        raise ValueError("Model and positive kilometre limit are required")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO shoes(model,km_used,max_km,created_at) VALUES(?,?,?,?)",
            (str(model).strip(), 0.0, float(max_km), datetime.now().isoformat(timespec="seconds")),
        )


def fetch_shoes() -> pd.DataFrame:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM shoes ORDER BY model").fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def increment_shoe_km(shoe_id: int, km: float) -> None:
    km = float(km)
    if km <= 0:
        raise ValueError("Distance must be positive")
    with _connect() as conn:
        cursor = conn.execute("UPDATE shoes SET km_used=km_used+? WHERE id=?", (km, int(shoe_id)))
        if cursor.rowcount != 1:
            raise ValueError("Shoe not found")

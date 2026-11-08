"""Per-user persistence on Supabase (tables: daily_telemetry, training_sessions).

Security model
* Every browser session gets its OWN client, authenticated with the logged-in user's JWT, so Postgres
  Row Level Security (auth.uid() = user_id) is enforced by the database, not just by this code.
* Errors are reported to the user once per session instead of being swallowed.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

try:
    import streamlit as st
except ImportError:
    class _StreamlitFallback:
        session_state: Dict[str, Any] = {}
        @staticmethod
        def warning(message: str) -> None:
            logger.warning(message)
    st = _StreamlitFallback()

try:
    from supabase import Client, create_client
except ImportError:
    class Client:  # type: ignore[no-redef]
        pass
    def create_client(*args: Any, **kwargs: Any):
        raise RuntimeError("Install the supabase dependency before using cloud persistence.")

from services.config import get_secret

logger = logging.getLogger(__name__)

SUPABASE_URL = str(get_secret("SUPABASE_URL", "https://quoafwluowkhjqqncnki.supabase.co"))
SUPABASE_KEY = str(get_secret("SUPABASE_KEY", ""))

TELEMETRY_TABLE = "daily_telemetry"
TRAINING_TABLE = "training_sessions"
CONFLICT_KEY = "user_id,date"
HISTORY_FIELDS = (
    "hrv", "hrv_weekly_avg", "rhr", "rhr_weekly_avg", "heart_rate_min", "heart_rate_max",
    "sleep_score", "sleep_hours", "sleep_target_hours", "sleep_deep_minutes",
    "sleep_light_minutes", "sleep_rem_minutes", "sleep_awake_minutes",
    "sleep_start", "sleep_end", "sleep_record_date", "respiration_sleep_avg",
    "respiration_wake_avg", "spo2_avg", "spo2_min", "stress_avg", "stress_max",
    "body_battery", "body_battery_low", "body_battery_high", "body_battery_charged",
    "body_battery_drained", "steps", "steps_goal", "distance_m", "floors_ascended",
    "intensity_minutes_moderate", "intensity_minutes_vigorous", "active_calories",
    "resting_calories", "total_calories", "vendor_readiness", "readiness_sleep_score",
    "readiness_hrv_score", "readiness_load_score", "readiness_recovery_hours",
    "vo2max_running", "vo2max_cycling", "ftp_w", "lactate_threshold_hr",
    "lactate_threshold_speed", "running_economy", "endurance_score",
    "low_aerobic_load", "high_aerobic_load", "anaerobic_load", "acute_training_load",
    "hydration_intake_ml", "hydration_goal_ml", "sweat_loss_ml", "training_status",
    "daily_training_load", "training_load_coverage",
    "garmin_sync_at", "illness_symptoms", "local_pain",
)


def _current_user() -> Optional[Any]:
    return st.session_state.get("user")


def _get_supabase() -> Client:
    """Client bound to THIS browser session and THIS user's access token."""
    user = _current_user()
    token = getattr(user, "access_token", "") or ""
    client = st.session_state.get("_sb_client")
    if client is None or st.session_state.get("_sb_token") != token:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        if token:
            client.postgrest.auth(token)
        st.session_state["_sb_client"] = client
        st.session_state["_sb_token"] = token
    return client


def _report(context: str, exc: Exception) -> None:
    logger.warning("%s: %s", context, exc)
    seen = st.session_state.setdefault("_store_errors", set())
    key = f"{context}:{type(exc).__name__}"
    if key not in seen:
        seen.add(key)
        st.warning(f"⚠️ {context}: {str(exc)[:200]}")


def init_db() -> None:
    """Tables are managed in the Supabase SQL editor."""


def _fetch(table: str, start_date: date, end_date: date, context: str) -> pd.DataFrame:
    user = _current_user()
    if not user:
        return pd.DataFrame()
    try:
        response = (
            _get_supabase().table(table).select("*").eq("user_id", user.id)
            .gte("date", start_date.isoformat()).lte("date", end_date.isoformat()).execute()
        )
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as exc:
        _report(context, exc)
        return pd.DataFrame()


def fetch_daily_metrics(start_date: date, end_date: date) -> pd.DataFrame:
    return _fetch(TELEMETRY_TABLE, start_date, end_date, "Não consegui ler as métricas diárias")


def fetch_training_days(start_date: date, end_date: date) -> pd.DataFrame:
    return _fetch(TRAINING_TABLE, start_date, end_date, "Não consegui ler as sessões de treino")


def _clean_payload(metrics: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        out[key] = value
    return out


def upsert_daily_metrics(metric_date: date, metrics: Dict[str, Any], source: str = "garmin") -> bool:
    user = _current_user()
    if not user:
        return False

    safe_metrics = metrics.copy()
    safe_metrics.pop("_mfa_required", None)
    safe_metrics.pop("_mfa_client_state", None)
    
    # Extrai sessões de treino para não quebrar a tabela daily_telemetry
    sessions = safe_metrics.pop("_training_sessions", [])

    safe_metrics["date"] = metric_date.isoformat()[:10]
    safe_metrics["user_id"] = user.id
    safe_metrics["source"] = source

    float_fields = [
        "hrv", "hrv_weekly_avg", "rhr", "rhr_weekly_avg", "heart_rate_min", "heart_rate_max",
        "sleep_score", "sleep_hours", "sleep_target_hours", "sleep_deep_minutes", "sleep_light_minutes",
        "sleep_rem_minutes", "sleep_awake_minutes", "respiration_sleep_avg", "respiration_wake_avg",
        "spo2_avg", "spo2_min", "stress_avg", "stress_max", "body_battery", "body_battery_low",
        "body_battery_high", "body_battery_charged", "body_battery_drained", "distance_m",
        "floors_ascended", "intensity_minutes_moderate", "intensity_minutes_vigorous", "active_calories",
        "resting_calories", "total_calories", "vendor_readiness", "readiness_sleep_score",
        "readiness_hrv_score", "readiness_load_score", "readiness_recovery_hours", "vo2max_running",
        "vo2max_cycling", "ftp_w", "lactate_threshold_hr", "lactate_threshold_speed", "running_economy",
        "endurance_score", "low_aerobic_load", "high_aerobic_load", "anaerobic_load", "acute_training_load",
        "hydration_intake_ml", "hydration_goal_ml", "sweat_loss_ml", "daily_training_load"
    ]

    for field in float_fields:
        if field in safe_metrics and safe_metrics[field] is not None:
            try:
                safe_metrics[field] = float(safe_metrics[field])
            except (ValueError, TypeError):
                safe_metrics.pop(field)

    int_fields = ["steps", "steps_goal"]
    for field in int_fields:
        if field in safe_metrics and safe_metrics[field] is not None:
            try:
                safe_metrics[field] = int(float(safe_metrics[field]))
            except (ValueError, TypeError):
                safe_metrics.pop(field)

    cleaned = _clean_payload(safe_metrics)

    try:
        response = _get_supabase().table(TELEMETRY_TABLE).upsert(cleaned, on_conflict=CONFLICT_KEY).execute()
        if sessions:
            bulk_upsert_training_sessions(sessions, source=source)
        return True
    except Exception as exc:
        _report("Erro ao guardar métricas diárias", exc)
        return False


def bulk_insert_garmin_history(records: Iterable[Dict[str, Any]], source: str = "garmin") -> int:
    user = _current_user()
    if not user:
        return 0
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for rec in records:
        day = rec.get("date")
        if not day:
            continue
        values = _clean_payload({k: rec.get(k) for k in HISTORY_FIELDS})
        if not values:
            continue
        row = {"user_id": user.id, "date": str(day)[:10], "source": source, **values}
        groups.setdefault(tuple(sorted(row)), []).append(row)
    written = 0
    for rows in groups.values():
        try:
            _get_supabase().table(TELEMETRY_TABLE).upsert(rows, on_conflict=CONFLICT_KEY).execute()
            written += len(rows)
        except Exception as exc:
            _report("Erro ao guardar o histórico Garmin", exc)
    return written


TRAINING_FIELDS = (
    "activity_id", "activity_name", "sport", "duration_seconds", "distance_m",
    "training_load", "average_hr", "max_hr", "average_power", "calories",
    "avg_cadence", "max_cadence", "ground_contact_time_ms", "ground_contact_balance_pct",
    "vertical_oscillation_cm", "vertical_ratio_pct", "stride_length_m",
    "aerobic_training_effect", "anaerobic_training_effect", "performance_condition",
    "normalized_power", "average_speed_mps", "elevation_gain_m", "average_respiration", "max_respiration",
)


def bulk_upsert_training_sessions(records: Iterable[Dict[str, Any]], source: str = "garmin") -> int:
    user = _current_user()
    if not user:
        return 0
    rows: List[Dict[str, Any]] = []
    for record in records:
        if not record.get("activity_id") or not record.get("date"):
            continue
        values = _clean_payload({key: record.get(key) for key in TRAINING_FIELDS})
        rows.append({
            "user_id": user.id,
            "date": str(record["date"])[:10],
            "source": source,
            **values,
        })
    if not rows:
        return 0
    try:
        _get_supabase().table(TRAINING_TABLE).upsert(
            rows, on_conflict="user_id,activity_id"
        ).execute()
        return len(rows)
    except Exception as exc:
        _report("Erro ao guardar atividades Garmin", exc)
        return 0


def get_setting(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"setting_{key}", default)


def save_setting(key: str, value: Any) -> None:
    st.session_state[f"setting_{key}"] = value


set_setting = save_setting

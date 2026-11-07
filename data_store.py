"""Per-user persistence on Supabase (tables: daily_telemetry, training_sessions).

Security model
* Every browser session gets its OWN client, authenticated with the logged-in user's JWT, so Postgres
  Row Level Security (auth.uid() = user_id) is enforced by the database, not just by this code.
  (The previous version shared one anonymous client between all visitors.)
* Errors are reported to the user once per session instead of being swallowed.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from services.config import get_secret

logger = logging.getLogger(__name__)

SUPABASE_URL = str(get_secret("SUPABASE_URL", "https://quoafwluowkhjqqncnki.supabase.co"))
SUPABASE_KEY = str(get_secret("SUPABASE_KEY", ""))

TELEMETRY_TABLE = "daily_telemetry"
TRAINING_TABLE = "training_sessions"
CONFLICT_KEY = "user_id,date"
HISTORY_FIELDS = ("hrv", "rhr", "sleep_score", "sleep_hours")


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
    """Log always; show the user each distinct problem once per session."""
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
    except Exception as exc:  # noqa: BLE001 - network / RLS / schema problems must not crash the page
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
    payload = {"user_id": user.id, "date": metric_date.isoformat(), "source": source, **_clean_payload(metrics)}
    try:
        _get_supabase().table(TELEMETRY_TABLE).upsert(payload, on_conflict=CONFLICT_KEY).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        _report("Erro ao guardar métricas", exc)
        return False


def bulk_insert_garmin_history(records: Iterable[Dict[str, Any]], source: str = "garmin") -> int:
    """Save several past days. Returns how many rows were written.

    Records are grouped by which fields they contain, so a day that only has HRV can never
    overwrite that day's resting heart rate with NULL (a mixed bulk upsert would).
    """
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
        except Exception as exc:  # noqa: BLE001
            _report("Erro ao guardar o histórico Garmin", exc)
    return written


# Settings live in the browser session (they reset on refresh). Persisting them needs a user_settings table.
def get_setting(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"setting_{key}", default)


def save_setting(key: str, value: Any) -> None:
    st.session_state[f"setting_{key}"] = value


set_setting = save_setting   # the UI calls both names

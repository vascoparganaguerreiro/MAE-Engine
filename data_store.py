from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = "https://quoafwluowkhjqqncnki.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def _get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    """Tabelas geridas via Supabase SQL Editor."""
    pass

def fetch_daily_metrics(start_date: date, end_date: date) -> pd.DataFrame:
    user = st.session_state.get("user")
    if not user:
        return pd.DataFrame()
    
    try:
        supabase = _get_supabase()
        response = (
            supabase.table("daily_telemetry")
            .select("*")
            .eq("user_id", user.id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
        )
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def fetch_training_days(start_date: date, end_date: date) -> pd.DataFrame:
    user = st.session_state.get("user")
    if not user:
        return pd.DataFrame()
    
    try:
        supabase = _get_supabase()
        response = (
            supabase.table("training_sessions")
            .select("*")
            .eq("user_id", user.id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .execute()
        )
        data = response.data
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def upsert_daily_metrics(metric_date: date, metrics: Dict[str, Any], source: str = "garmin"):
    user = st.session_state.get("user")
    if not user:
        return
    
    try:
        supabase = _get_supabase()
        payload = {"user_id": user.id, "date": metric_date.isoformat(), "source": source}
        for k, v in metrics.items():
            if v is not None and not pd.isna(v):
                payload[k] = v
                
        supabase.table("daily_telemetry").upsert(payload, on_conflict="user_id, date").execute()
    except Exception as e:
        st.error(f"Erro ao guardar métricas: {e}")

def get_setting(key: str, default: Any = None) -> Any:
    return st.session_state.get(f"setting_{key}", default)

def save_setting(key: str, value: Any):
    st.session_state[f"setting_{key}"] = value

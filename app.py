from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st

import data_store as store
import engine_core as core
import services.auth as auth
from integrations.garmin import fetch_daily_metrics as fetch_garmin_metrics
from ui.today import render_today_page


# Configuração Global Streamlit — Single Page Layout
st.set_page_config(
    page_title="Apex Engine | Personal Performance & Longevity",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
store.init_db()

# 🔐 Autenticação de Utilizador & Gestão de Sessão (Supabase EU com captura OAuth integrada)
user = auth.render_login_component()

if user is None:
    st.info("🔒 Por favor inicia sessão ou cria uma conta para aceder ao APEX Engine.")
    st.stop()

# Estilos CSS Globais — Paleta Semântica Restrita
st.markdown(
    """
    <style>
      .stApp { background: #0b0f17; color: #e2e8f0; }
      [data-testid="stHeader"] { background: rgba(11, 15, 23, 0.8); }
      [data-testid="stSidebar"] { display: none; }
      .muted { color:#94a3b8; font-size:.88rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _clean_number(value: Any) -> Optional[float]:
    try:
        v = float(value)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _run_garmin_sync() -> bool:
    import os
    email = os.environ.get("GARMIN_EMAIL") or st.secrets.get("GARMIN_EMAIL", None) or str(st.session_state.get("garmin_email_input", "")).strip()
    password = os.environ.get("GARMIN_PASSWORD") or st.secrets.get("GARMIN_PASSWORD", None) or str(st.session_state.get("garmin_password_input", ""))
    
    if not email or not password:
        st.session_state["garmin_sync_result"] = {
            "ok": False,
            "message": "Insere as credenciais da Garmin.",
            "warnings": [],
        }
        return False

    try:
        metrics, history_recs, warnings = fetch_garmin_metrics(email, password, date.today(), fetch_history=True, history_days=30)
        
        if history_recs:
            try:
                store.bulk_insert_garmin_history(history_recs)
            except Exception:
                pass

        prof_ext = metrics.pop("profile_extracted", None)
        if prof_ext:
            from services.data_import import update_profile_if_missing
            update_profile_if_missing(prof_ext)

        if metrics:
            store.upsert_daily_metrics(date.today(), metrics, source="garmin")
            store.set_setting("garmin_last_sync", datetime.now().isoformat(timespec="seconds"))
            st.session_state["garmin_sync_result"] = {
                "ok": True,
                "message": "Sincronização efetuada com sucesso!",
                "warnings": warnings,
            }
            return True
        else:
            return False
    except Exception:
        return False


# Pipeline de Dados APEX
today = date.today()
start_day = today - timedelta(days=60)
dates = pd.date_range(start=start_day, end=today, freq="D")

raw_daily = store.fetch_daily_metrics(start_day, today)
raw_training = store.fetch_training_days(start_day, today)

base_df = pd.DataFrame({"Date": dates})

# 1. Fusão de Fisiologia Diária (Recovery / HRV / Sono)
if not raw_daily.empty:
    raw_daily["Date"] = pd.to_datetime(raw_daily["date"])
    base_df = base_df.merge(raw_daily, on="Date", how="left")
else:
    for col in ["hrv", "rhr", "sleep_score", "sleep_hours", "sleep_target_hours", "hrv_weekly_avg", "soreness", "stress", "mood", "vendor_readiness"]:
        base_df[col] = np.nan

for col in ["hrv", "rhr", "sleep_score", "sleep_hours", "sleep_target_hours", "hrv_weekly_avg", "soreness", "stress", "mood", "vendor_readiness"]:
    if col not in base_df:
        base_df[col] = np.nan
    base_df[col] = pd.to_numeric(base_df[col], errors="coerce")

base_df = base_df.rename(columns={
    "hrv": "HRV", "rhr": "RHR", "sleep_score": "SleepScore", "sleep_hours": "SleepHours",
    "sleep_target_hours": "SleepTargetHours", "soreness": "Soreness", "stress": "Stress",
    "mood": "Mood", "vendor_readiness": "GarminReadiness",
})

# 2. Fusão de Carga de Treino Real
if not raw_training.empty and "date" in raw_training.columns:
    raw_training["Date"] = pd.to_datetime(raw_training["date"])
    
    daily_load_agg = raw_training.groupby("Date")["training_load"].sum().reset_index()
    daily_load_agg = daily_load_agg.rename(columns={"training_load": "DailyLoad"})
    
    base_df = base_df.merge(daily_load_agg, on="Date", how="left")
else:
    base_df["DailyLoad"] = np.nan

base_df["DailyLoad"] = base_df["DailyLoad"].fillna(0.0)

# 3. Cálculo Determinístico do Pipeline de Carga (CTL 42d / ATL 7d / TSB)
ctl_list = []
atl_list = []
ctl = 0.0
atl = 0.0

for load in base_df["DailyLoad"]:
    ctl = ctl + (load - ctl) / 42.0
    atl = atl + (load - atl) / 7.0
    ctl_list.append(ctl)
    atl_list.append(atl)

base_df["CTL"] = ctl_list
base_df["ATL"] = atl_list
base_df["TSB"] = base_df["CTL"] - base_df["ATL"]

# Extração das Métricas para a UI
hrv_curr = _clean_number(base_df["HRV"].iloc[-1])
rhr_curr = _clean_number(base_df["RHR"].iloc[-1])
sleep_curr = _clean_number(base_df["SleepScore"].iloc[-1])
sleep_hours_curr = _clean_number(base_df["SleepHours"].iloc[-1])
sleep_target_curr = _clean_number(base_df["SleepTargetHours"].iloc[-1]) if pd.notna(base_df["SleepTargetHours"].iloc[-1]) else None
garmin_readiness_curr = _clean_number(base_df["GarminReadiness"].iloc[-1]) if pd.notna(base_df["GarminReadiness"].iloc[-1]) else None

base_hrv = core.compute_baseline(base_df["HRV"], min_n=14, exclude_last=True)
base_rhr = core.compute_baseline(base_df["RHR"], min_n=14, exclude_last=True)
hrv_mean = base_hrv.mean if base_hrv else None
rhr_mean = base_rhr.mean if base_rhr else None
hrv_valid_days = int(base_df["HRV"].iloc[:-1].notna().sum())

zs_today = core.zscores_for_day(base_df, -1)
mode = store.get_setting("mode", "performance")
readiness_data = core.compute_readiness(zs_today, mode=mode)

score = int(garmin_readiness_curr) if garmin_readiness_curr is not None else readiness_data["score"]
decision = core.decision_for(score) if score is not None else {"cap": "full", "headline": "Sem prontidão", "tone": "amber"}
hrv_context = core.get_hrv_context(hrv_curr, hrv_mean, base_hrv.sd if base_hrv else None)

effective_target = sleep_target_curr if sleep_target_curr is not None else 8.0
diff_minutes = (effective_target - sleep_hours_curr) * 60.0 if sleep_hours_curr is not None else None

# Renderizar Dashboard Único do APEX Engine
render_today_page(
    base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
    hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
    sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
    garmin_readiness_curr=garmin_readiness_curr, score=score,
    decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
    hrv_valid_days=hrv_valid_days, sync_callback=_run_garmin_sync
)

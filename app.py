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

# Configuração Global Streamlit — Single Page Executive Layout
st.set_page_config(
    page_title="APEX ENGINE | Executive Physiology & Performance",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
store.init_db()

# 🔐 Autenticação de Utilizador & Gestão de Sessão
user = auth.render_login_component()

if user is None:
    st.info("🔒 Por favor inicia sessão ou cria uma conta para aceder ao APEX Engine.")
    st.stop()

# Estilos CSS Globais — Ultra-Premium Executive Obsidian Theme
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,700;1,400&family=Inter:wght@300;400;500;600;700&display=swap');

      /* Reset & Global Canvas */
      html, body, .stApp {
          background-color: #05070a !important;
          color: #f1f5f9 !important;
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
          letter-spacing: -0.01em;
      }

      [data-testid="stHeader"] {
          background: rgba(5, 7, 10, 0.75) !important;
          backdrop-filter: blur(12px) !important;
          border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      }

      [data-testid="stSidebar"] { display: none !important; }

      /* Frosted Glass Container Base */
      .apex-card {
          background: rgba(15, 23, 42, 0.55);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 12px;
          padding: 20px;
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
          margin-bottom: 16px;
          transition: transform 0.2s ease, border-color 0.2s ease;
      }
      .apex-card:hover {
          border-color: rgba(255, 255, 255, 0.18);
      }

      /* Monospace Metrics Styling */
      .mono-val {
          font-family: 'JetBrains Mono', monospace !important;
          font-weight: 700;
          letter-spacing: -0.03em;
      }
      .mono-sub {
          font-family: 'JetBrains Mono', monospace !important;
          font-size: 0.75rem;
          color: #94a3b8;
      }

      /* Buttons & Custom Controls */
      .stButton > button {
          background: rgba(255, 255, 255, 0.05) !important;
          color: #f8fafc !important;
          border: 1px solid rgba(255, 255, 255, 0.12) !important;
          border-radius: 8px !important;
          font-family: 'JetBrains Mono', monospace !important;
          font-size: 0.8rem !important;
          text-transform: uppercase !important;
          letter-spacing: 0.05em !important;
          transition: all 0.2s ease !important;
      }
      .stButton > button:hover {
          background: rgba(255, 255, 255, 0.12) !important;
          border-color: rgba(255, 255, 255, 0.3) !important;
          box-shadow: 0 0 15px rgba(255, 255, 255, 0.1);
      }

      /* Native Selectboxes & Inputs Override */
      div[data-baseweb="select"] > div {
          background-color: rgba(15, 23, 42, 0.7) !important;
          border-color: rgba(255, 255, 255, 0.1) !important;
          color: #f8fafc !important;
          border-radius: 8px !important;
      }

      .muted { color: #64748b; font-size: 0.82rem; }
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
    from services.config import get_secret

    def _result(ok: bool, message: str, warnings=None) -> bool:
        st.session_state["garmin_sync_result"] = {"ok": ok, "message": message, "warnings": warnings or []}
        return ok

    email = str(get_secret("GARMIN_EMAIL", "") or st.session_state.get("garmin_email_input", "")).strip()
    password = str(get_secret("GARMIN_PASSWORD", "") or st.session_state.get("garmin_password_input", ""))
    if not email or not password:
        return _result(False, "Insere as credenciais da Garmin nas definições.")

    try:
        metrics, history_recs, warnings = fetch_garmin_metrics(email, password, date.today(), fetch_history=True, history_days=30)
    except Exception as exc:
        return _result(False, f"Falha na ligação Garmin ({type(exc).__name__}). Confirma as credenciais.")

    saved_history = store.bulk_insert_garmin_history(history_recs) if history_recs else 0

    prof_ext = metrics.pop("profile_extracted", None)
    if prof_ext:
        from services.data_import import update_profile_if_missing
        update_profile_if_missing(prof_ext)

    saved_today = store.upsert_daily_metrics(date.today(), metrics, source="garmin") if metrics else False
    if saved_today or saved_history:
        store.set_setting("garmin_last_sync", datetime.now().isoformat(timespec="seconds"))
        return _result(True, "Sincronização Garmin efetuada com sucesso!", warnings)
    return _result(False, "Sem métricas novas devolvidas pela Garmin.", warnings)


_sync_notice = st.session_state.pop("garmin_sync_result", None)
if _sync_notice and not _sync_notice.get("ok"):
    st.warning(_sync_notice.get("message", "Falha na sincronização."))

# Pipeline Fisiológico APEX
today = date.today()
start_day = today - timedelta(days=60)
dates = pd.date_range(start=start_day, end=today, freq="D")

raw_daily = store.fetch_daily_metrics(start_day, today)
raw_training = store.fetch_training_days(start_day, today)

base_df = pd.DataFrame({"Date": dates})

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

if not raw_training.empty and "date" in raw_training.columns:
    raw_training["Date"] = pd.to_datetime(raw_training["date"])
    daily_load_agg = raw_training.groupby("Date")["training_load"].sum().reset_index()
    daily_load_agg = daily_load_agg.rename(columns={"training_load": "DailyLoad"})
    base_df = base_df.merge(daily_load_agg, on="Date", how="left")
else:
    base_df["DailyLoad"] = np.nan

base_df["DailyLoad"] = base_df["DailyLoad"].fillna(0.0)

ctl_list, atl_list = [], []
ctl, atl = 0.0, 0.0

for load in base_df["DailyLoad"]:
    ctl += (load - ctl) / 42.0
    atl += (load - atl) / 7.0
    ctl_list.append(ctl)
    atl_list.append(atl)

base_df["CTL"] = ctl_list
base_df["ATL"] = atl_list
base_df["TSB"] = base_df["CTL"] - base_df["ATL"]

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

# Renderizar Cockpit Executivo
render_today_page(
    base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
    hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
    sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
    garmin_readiness_curr=garmin_readiness_curr, score=score,
    decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
    hrv_valid_days=hrv_valid_days, sync_callback=_run_garmin_sync
)

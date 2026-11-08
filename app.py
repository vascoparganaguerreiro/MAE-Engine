from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

import data_store as store
import engine_core as core
import services.auth as auth
from integrations.garmin import fetch_daily_metrics as fetch_garmin_metrics
from services.config import get_secret
from ui.today import render_today_page

logger = logging.getLogger(__name__)
APP_TZ = ZoneInfo("Europe/Prague")
APP_TODAY = datetime.now(APP_TZ).date()

st.set_page_config(
    page_title="Apex Engine | Performance & Health",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
store.init_db()

# A stable session-scoped authentication layer protects each user's data.
user = auth.render_login_component()
if user is None:
    st.info("Inicia sessão ou cria uma conta para aceder ao Apex Engine.")
    st.stop()

# ── Premium graphite theme: quiet typography, restrained colour, no neon/glass effects.
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
      :root {
        --apex-bg: #151a1c;
        --apex-panel: #202729;
        --apex-panel-2: #293235;
        --apex-border: #3b4846;
        --apex-text: #edf0f2;
        --apex-muted: #9aa5af;
        --apex-accent: #a9b9a9;
        --apex-gold: #c7b48e;
      }
      html, body, .stApp {
        background: var(--apex-bg) !important;
        color: var(--apex-text) !important;
        font-family: 'DM Sans', sans-serif !important;
      }
      [data-testid="stHeader"] { background: rgba(16,20,25,.94) !important; }
      [data-testid="stSidebar"] { display: none !important; }
      .block-container { max-width: 1380px; padding-top: 2.2rem; padding-bottom: 3.5rem; }
      h1, h2, h3, h4 { font-family: 'Manrope', sans-serif !important; letter-spacing: -.02em; color: #f1f2ef !important; }
      h1 { font-weight: 800 !important; }
      p, label, [data-testid="stMarkdownContainer"] { color: var(--apex-text); }
      [data-testid="stCaptionContainer"], .stCaption { color: var(--apex-muted) !important; }
      .apex-card {
        background: var(--apex-panel) !important;
        border: 1px solid var(--apex-border) !important;
        border-radius: 14px !important;
        padding: 18px 20px !important;
        box-shadow: 0 3px 12px rgba(0,0,0,.10) !important;
        margin-bottom: 14px;
      }
      .mono-val { font-family: 'Manrope', sans-serif !important; font-weight: 700; letter-spacing: -.025em; }
      .mono-sub { font-family: 'DM Sans', sans-serif !important; font-size: .78rem; color: var(--apex-muted); }
      button[data-baseweb="tab"] {
        color: #aeb7bf !important; font-family: 'DM Sans', sans-serif !important;
        font-size: .88rem !important; font-weight: 600 !important;
        border-bottom: 2px solid transparent !important; padding: 13px 16px !important;
      }
      button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--apex-accent) !important; border-bottom-color: var(--apex-accent) !important;
        background: rgba(155,185,173,.06) !important;
      }
      .stButton > button, .stLinkButton > a {
        border-radius: 9px !important; border: 1px solid #3a4550 !important;
        background: #202831 !important; color: #edf0f2 !important;
        font-family: 'DM Sans', sans-serif !important; font-weight: 600 !important;
        text-transform: none !important; transition: border-color .15s ease, background .15s ease;
      }
      .stButton > button:hover, .stLinkButton > a:hover {
        background: #29343e !important; border-color: #71877f !important;
      }
      .stButton > button[kind="primary"],
      [data-testid="stBaseButton-primary"] {
        background: #a9b9a9 !important; color: #18201c !important;
        border: 1px solid #c3d0c2 !important; font-weight: 700 !important;
      }
      .stButton > button[kind="primary"]:hover,
      [data-testid="stBaseButton-primary"]:hover {
        background: #bdcbbc !important; border-color: #d6dfd4 !important;
      }
      [data-testid="stMetric"] {
        background: var(--apex-panel) !important; border: 1px solid var(--apex-border) !important;
        border-radius: 12px !important; padding: 14px 16px !important;
      }
      [data-testid="stMetricLabel"] { color: var(--apex-muted) !important; }
      [data-testid="stMetricValue"] { font-family: 'Manrope', sans-serif !important; }
      [data-testid="stExpander"] { border: 1px solid var(--apex-border) !important; border-radius: 10px !important; }
      div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
      div[data-baseweb="textarea"] > div { background: #202831 !important; border-color: #3a4550 !important; }
      hr { border-color: var(--apex-border) !important; }
      .apex-eyebrow { color: var(--apex-gold); font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
      .apex-muted { color: var(--apex-muted); }
      @media (max-width: 900px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def _clean_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _user_token_store() -> str:
    """Separate Garmin token cache per Apex user; path is outside the repository."""
    user_id = str(getattr(user, "id", "unknown-user"))
    suffix = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    return str(Path.home() / ".cache" / "apex-engine" / "garmin" / suffix)


def _run_garmin_sync() -> bool:
    email = str(get_secret("GARMIN_EMAIL", "") or st.session_state.get("garmin_email_input", "")).strip()
    password = str(get_secret("GARMIN_PASSWORD", "") or st.session_state.get("garmin_password_input", ""))
    mfa_state = st.session_state.get("garmin_mfa_client_state")
    mfa_code = str(st.session_state.get("garmin_mfa_code", "")).strip()
    if not mfa_state and (not email or not password):
        st.session_state["garmin_sync_result"] = {
            "ok": False, "message": "Adiciona as credenciais Garmin nas definições antes de sincronizar.", "warnings": []
        }
        return False
    if mfa_state and not mfa_code:
        st.session_state["garmin_sync_result"] = {
            "ok": False, "message": "Introduz o código MFA enviado pela Garmin e volta a sincronizar.", "warnings": []
        }
        return False

    try:
        metrics, history_records, warnings = fetch_garmin_metrics(
            email, password, APP_TODAY, fetch_history=True,
            history_days=60, token_store=_user_token_store(),
            mfa_client_state=mfa_state, mfa_code=mfa_code or None,
        )
    except Exception as exc:
        logger.exception("Garmin sync failed")
        st.session_state["garmin_sync_result"] = {
            "ok": False,
            "message": f"Não foi possível concluir a sincronização ({type(exc).__name__}): {str(exc)[:220]}",
            "warnings": [],
        }
        # Never retain the entered password beyond the attempted sync.
        st.session_state.pop("garmin_password_input", None)
        st.session_state.pop("garmin_mfa_code", None)
        return False

    if metrics.pop("_mfa_required", False):
        st.session_state["garmin_mfa_client_state"] = metrics.get("_mfa_client_state")
        st.session_state.pop("garmin_password_input", None)
        st.session_state["garmin_sync_result"] = {
            "ok": False,
            "message": "A Garmin exige verificação em dois passos. Introduz o código MFA nas definições Garmin e sincroniza novamente.",
            "warnings": warnings,
        }
        return False

    st.session_state.pop("garmin_mfa_client_state", None)
    st.session_state.pop("garmin_mfa_code", None)
    activities = metrics.pop("_training_sessions", [])
    metrics.pop("date", None)
    saved_history = store.bulk_insert_garmin_history(history_records) if history_records else 0
    saved_activities = store.bulk_upsert_training_sessions(activities) if activities else 0
    metric_count = sum(value is not None for value in metrics.values())
    if metric_count:
        metrics["garmin_sync_at"] = datetime.now(APP_TZ).isoformat(timespec="seconds")
    saved_today = store.upsert_daily_metrics(APP_TODAY, metrics, source="garmin") if metric_count else False

    st.session_state.pop("garmin_password_input", None)
    if saved_today or saved_history or saved_activities:
        store.set_setting("garmin_last_sync", datetime.now().astimezone().isoformat(timespec="seconds"))
        st.session_state["garmin_sync_result"] = {
            "ok": True,
            "message": (
                f"Sincronização concluída: {metric_count} métricas de hoje, "
                f"{saved_history} dias históricos e {saved_activities} atividades guardadas."
            ),
            "warnings": warnings,
        }
        return True

    st.session_state["garmin_sync_result"] = {
        "ok": False,
        "message": "A Garmin respondeu, mas não foi possível guardar métricas novas. Os valores antigos não foram apresentados como dados de hoje.",
        "warnings": warnings,
    }
    return False


# Show a result once after a sync-triggered rerun.
sync_notice = st.session_state.pop("garmin_sync_result", None)
if sync_notice:
    (st.success if sync_notice.get("ok") else st.warning)(sync_notice.get("message", "Resultado da sincronização"))
    if sync_notice.get("warnings"):
        with st.expander(f"Diagnóstico Garmin — {len(sync_notice['warnings'])} avisos"):
            st.caption("A autenticação pode funcionar mesmo quando um ou mais endpoints não devolvem dados. Cada aviso identifica o endpoint que falhou.")
            for warning in sync_notice["warnings"][:40]:
                st.code(warning, language=None)
    if sync_notice.get("ok"):
        st.caption("Próximo passo: confirma as datas dos registos e compara os valores com Garmin Connect. Dados ausentes continuam a ser apresentados como indisponíveis, nunca como zero.")

# ── Build a date-complete display frame while preserving missingness.
today = APP_TODAY
start_day = today - timedelta(days=60)
dates = pd.date_range(start=start_day, end=today, freq="D")
base_df = pd.DataFrame({"Date": dates})
raw_daily = store.fetch_daily_metrics(start_day, today)
raw_training = store.fetch_training_days(start_day, today)

if not raw_daily.empty and "date" in raw_daily.columns:
    raw_daily = raw_daily.copy()
    raw_daily["Date"] = pd.to_datetime(raw_daily["date"], errors="coerce").dt.normalize()
    base_df = base_df.merge(raw_daily.drop(columns=["date"], errors="ignore"), on="Date", how="left")

# Daily Garmin fields are numeric unless explicitly timestamps/coverage flags.
metric_columns = [
    "hrv", "hrv_weekly_avg", "rhr", "rhr_weekly_avg", "heart_rate_min", "heart_rate_max",
    "sleep_score", "sleep_hours", "sleep_target_hours", "sleep_deep_minutes",
    "sleep_light_minutes", "sleep_rem_minutes", "sleep_awake_minutes",
    "respiration_sleep_avg", "respiration_wake_avg", "spo2_avg", "spo2_min",
    "stress_avg", "stress_max", "body_battery", "body_battery_low", "body_battery_high",
    "body_battery_charged", "body_battery_drained", "steps", "steps_goal", "distance_m",
    "floors_ascended", "intensity_minutes_moderate", "intensity_minutes_vigorous",
    "active_calories", "resting_calories", "total_calories", "vendor_readiness",
    "readiness_sleep_score", "readiness_hrv_score", "readiness_load_score",
    "readiness_recovery_hours", "vo2max_running", "vo2max_cycling", "ftp_w",
    "lactate_threshold_hr", "lactate_threshold_speed", "running_economy", "endurance_score",
    "low_aerobic_load", "high_aerobic_load", "anaerobic_load", "acute_training_load",
    "hydration_intake_ml", "hydration_goal_ml", "sweat_loss_ml", "daily_training_load",
    "soreness", "stress", "mood", "fatigue", "motivation",
]
for column in metric_columns:
    if column not in base_df.columns:
        base_df[column] = np.nan
    base_df[column] = pd.to_numeric(base_df[column], errors="coerce")

if "training_load_coverage" not in base_df:
    base_df["training_load_coverage"] = False
base_df["training_load_coverage"] = base_df["training_load_coverage"].map(
    lambda value: value if isinstance(value, bool) else str(value).strip().lower() in {"true", "t", "1", "yes"}
).fillna(False).astype(bool)

# Activity rows are an additional source, not a reason to fill every unknown day with zero.
base_df["DailyLoad"] = np.nan
covered = base_df["training_load_coverage"]
base_df.loc[covered, "DailyLoad"] = base_df.loc[covered, "daily_training_load"].fillna(0.0)
if not raw_training.empty and {"date", "training_load"}.issubset(raw_training.columns):
    activity_copy = raw_training.copy()
    activity_copy["Date"] = pd.to_datetime(activity_copy["date"], errors="coerce").dt.normalize()
    activity_copy["training_load"] = pd.to_numeric(activity_copy["training_load"], errors="coerce")
    activity_daily = activity_copy.groupby("Date")["training_load"].sum(min_count=1)
    for idx, row in base_df.iterrows():
        if pd.isna(row["DailyLoad"]) and row["Date"] in activity_daily.index:
            base_df.at[idx, "DailyLoad"] = activity_daily.loc[row["Date"]]

# CTL/ATL/TSB are only shown once a complete 42-day load history is available.
base_df["CTL"] = np.nan
base_df["ATL"] = np.nan
base_df["TSB"] = np.nan
valid_load = base_df["DailyLoad"].notna().to_numpy()
missing_indices = np.where(~valid_load)[0]
segment_start = int(missing_indices[-1] + 1) if len(missing_indices) else 0
load_segment = base_df.loc[segment_start:, "DailyLoad"]
if len(load_segment) >= 42 and load_segment.notna().all():
    load_model = core.compute_banister(load_segment.tolist(), ctl_tc=42.0, atl_tc=7.0)
    base_df.loc[segment_start:, "CTL"] = load_model["ctl"]
    base_df.loc[segment_start:, "ATL"] = load_model["atl"]
    base_df.loc[segment_start:, "TSB"] = load_model["tsb"]

# Expose the naming convention expected by the calculation engine and pillar views.
base_df = base_df.rename(columns={
    "hrv": "HRV", "rhr": "RHR", "sleep_score": "SleepScore",
    "sleep_hours": "SleepHours", "sleep_target_hours": "SleepTargetHours",
    "vendor_readiness": "GarminReadiness", "sleep_deep_minutes": "sleep_deep_minutes",
    "sleep_light_minutes": "sleep_light_minutes", "sleep_rem_minutes": "sleep_rem_minutes",
})
base_df["SubjectiveScore"] = [
    core.subjective_score(
        int(row.soreness) if pd.notna(row.soreness) else None,
        int(row.stress) if pd.notna(row.stress) else None,
        int(row.mood) if pd.notna(row.mood) else None,
    )
    for row in base_df.itertuples()
]

hrv_curr = _clean_number(base_df["HRV"].iloc[-1])
rhr_curr = _clean_number(base_df["RHR"].iloc[-1])
sleep_curr = _clean_number(base_df["SleepScore"].iloc[-1])
sleep_hours_curr = _clean_number(base_df["SleepHours"].iloc[-1])
sleep_target_curr = _clean_number(base_df["SleepTargetHours"].iloc[-1])
garmin_readiness_curr = _clean_number(base_df["GarminReadiness"].iloc[-1])

base_hrv = core.compute_baseline(base_df["HRV"], min_n=14, exclude_last=True)
base_rhr = core.compute_baseline(base_df["RHR"], min_n=14, exclude_last=True)
hrv_mean = base_hrv.mean if base_hrv else None
rhr_mean = base_rhr.mean if base_rhr else None
hrv_valid_days = int(base_df["HRV"].iloc[:-1].notna().sum())
sleep_7d = base_df["SleepHours"].tail(7).dropna()
sleep_7d_avg = float(sleep_7d.mean()) if len(sleep_7d) >= 3 else None

mode = store.get_setting("mode", "performance")
zs_today = core.zscores_for_day(base_df, -1)
readiness_data = core.compute_readiness(zs_today, mode=mode)
# Garmin Training Readiness is a vendor metric and must not be substituted for Apex readiness.
apex_score = readiness_data["score"]
decision = core.decision_for(apex_score)
hrv_context = core.get_hrv_context(hrv_curr, hrv_mean, base_hrv.sd if base_hrv else None)
diff_minutes = ((sleep_target_curr - sleep_hours_curr) * 60.0
                if sleep_target_curr is not None and sleep_hours_curr is not None else None)

render_today_page(
    base_df=base_df,
    training_sessions=raw_training,
    hrv_mean=hrv_mean,
    rhr_mean=rhr_mean,
    hrv_curr=hrv_curr,
    rhr_curr=rhr_curr,
    sleep_curr=sleep_curr,
    sleep_hours_curr=sleep_hours_curr,
    sleep_target_curr=sleep_target_curr,
    garmin_readiness_curr=garmin_readiness_curr,
    score=apex_score,
    decision=decision,
    hrv_context=hrv_context,
    diff_minutes=diff_minutes,
    hrv_valid_days=hrv_valid_days,
    sync_callback=_run_garmin_sync,
    sleep_7d_avg=sleep_7d_avg,
    lang=store.get_setting("language", "PT"),
    mode=mode,
    readiness_data=readiness_data,
)

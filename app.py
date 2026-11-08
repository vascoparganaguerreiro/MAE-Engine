"""Main entrypoint for APEX Engine Streamlit dashboard."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict

import streamlit as st

from data_store import (
    fetch_daily_metrics as store_fetch_daily,
    upsert_daily_metrics,
)
from integrations.garmin import fetch_daily_metrics as garmin_fetch

# Tenta importar a função de renderização da página Hoje
try:
    from ui.today import render_today_page
except ImportError:
    render_today_page = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apex_engine")

st.set_page_config(
    page_title="APEX ENGINE",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Estado de Sessão de Utilizador
if "user" not in st.session_state:
    class SingleUser:
        id = "00000000-0000-0000-0000-000000000000"
        email = "vascoparganaguerreiro@gmail.com"
        access_token = "apex_personal_session"
    st.session_state["user"] = SingleUser()

if "daily_metrics" not in st.session_state:
    st.session_state["daily_metrics"] = {}

def sync_garmin_now(email: str, passw: str) -> None:
    target_date = date.today()
    with st.spinner("A sincronizar dados do Garmin Connect..."):
        metrics, history, warnings = garmin_fetch(
            email=email,
            password=passw,
            target_date=target_date,
            fetch_history=True,
            history_days=14,
        )
        
        if metrics and any(k != "date" for k in metrics if not k.startswith("_")):
            st.session_state["daily_metrics"] = metrics
            st.session_state["last_sync_time"] = datetime.now().strftime("%H:%M:%S")
            
            try:
                upsert_daily_metrics(target_date, metrics)
            except Exception as exc:
                logger.warning("Erro ao guardar no Supabase: %s", exc)
            st.rerun()
        else:
            st.warning("⚠️ Ligação estabelecida, mas a Garmin não devolveu métricas novas para hoje.")

# Barra Superior de Sessão
user = st.session_state.get("user")
st.markdown(
    f"<div style='text-align: right; color: #888; font-size: 0.85rem;'>"
    f"Sessão Ativa: <b>{getattr(user, 'email', 'vascoparganaguerreiro@gmail.com')}</b> | "
    f"Última Sync: <b>{st.session_state.get('last_sync_time', 'Hoje')}</b>"
    f"</div>",
    unsafe_allow_html=True,
)

st.title("⚡ APEX ENGINE")
st.caption("PERFORMANCE · RECOVERY · LONGEVITY")

# Painel Garmin
with st.expander("⚙️ Perfil, idioma e ligação Garmin", expanded=not bool(st.session_state.get("daily_metrics"))):
    c1, c2 = st.columns(2)
    with c1:
        email = st.text_input("Garmin email", value="vascoparganaguerreiro@gmail.com")
    with c2:
        passw = st.text_input("Garmin password", type="password")
        
    if st.button("↻ Sync Garmin"):
        if email and passw:
            sync_garmin_now(email, passw)
        else:
            st.error("Por favor insere a palavra-passe da Garmin.")

# Extração das métricas ativas
m = st.session_state.get("daily_metrics", {})

# Mapeamento dos 14 argumentos exatos esperados por ui.today.render_today_page
hrv_mean = m.get("hrv_weekly_avg")
rhr_mean = m.get("rhr_weekly_avg")
hrv_curr = m.get("hrv")
rhr_curr = m.get("rhr")
sleep_curr = m.get("sleep_score")
sleep_hours_curr = m.get("sleep_hours")
sleep_target_curr = m.get("sleep_target_hours", 8.0)
garmin_readiness_curr = m.get("vendor_readiness")
score = m.get("vendor_readiness")
decision = "Prontidão calculada com base na VRC e recuperação de sono."
hrv_context = "Linha de base estável."
diff_minutes = 0
hrv_valid_days = 7 if hrv_curr else 0

def dummy_callback():
    pass

# Renderização do Dashboard
if render_today_page is not None and m:
    try:
        render_today_page(
            hrv_mean,
            rhr_mean,
            hrv_curr,
            rhr_curr,
            sleep_curr,
            sleep_hours_curr,
            sleep_target_curr,
            garmin_readiness_curr,
            score,
            decision,
            hrv_context,
            diff_minutes,
            hrv_valid_days,
            dummy_callback
        )
    except Exception as exc:
        logger.warning("Falha ao invocar ui.today: %s", exc)
        render_today_page = None

if render_today_page is None or not m:
    st.subheader("Cinco métricas principais")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("VRC Noturna", f"{m.get('hrv', '--')} ms", delta=f"{round(m.get('hrv', 0) - m.get('hrv_weekly_avg', 0), 1)} ms vs média" if m.get('hrv') and m.get('hrv_weekly_avg') else None)
    c2.metric("FC Repouso", f"{m.get('rhr', '--')} bpm")
    c3.metric("Duração do Sono", f"{m.get('sleep_hours', '--')} h")
    c4.metric("Carga Diária", f"{m.get('daily_training_load', 0.0)} net")
    c5.metric("Prontidão Garmin", f"{m.get('vendor_readiness', '--')}/100")

    st.subheader("Outros Sinais Biométricos")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sleep Score", f"{m.get('sleep_score', '--')}/100")
    c2.metric("Body Battery", f"{m.get('body_battery', '--')}")
    c3.metric("Stress Médio", f"{m.get('stress_avg', '--')}")
    c4.metric("SpO₂ Médio", f"{m.get('spo2_avg', '--')}%")
    c5.metric("VO₂ Max Corrida", f"{m.get('vo2max_running', '--')}")

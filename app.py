"""Main entrypoint for APEX Engine Streamlit dashboard."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from data_store import (
    _get_supabase,
    fetch_daily_metrics as store_fetch_daily,
    fetch_training_days as store_fetch_training,
    upsert_daily_metrics,
)
from integrations.garmin import fetch_daily_metrics as garmin_fetch

# Tenta carregar as páginas de UI originais
try:
    from ui.today import render_today_page
except ImportError:
    render_today_page = None

try:
    from ui.recovery import render_recovery_tab
except ImportError:
    render_recovery_tab = None

try:
    from ui.performance import render_performance_tab
except ImportError:
    render_performance_tab = None

try:
    from ui.strength import render_strength_tab
except ImportError:
    render_strength_tab = None

try:
    from ui.insights import render_insights_tab
except ImportError:
    render_insights_tab = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apex_engine")

st.set_page_config(
    page_title="APEX ENGINE",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Estilização CSS personalizada para o tema escuro original
st.markdown(
    """
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 16px;
        border-radius: 4px;
        background-color: #161b22;
        color: #8b949e;
    }
    .stTabs [aria-selected="true"] {
        background-color: #21262d !important;
        color: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Autenticação & Sessão de Utilizador (Supabase & Google Auth)
# -----------------------------------------------------------------------------
def init_user_session() -> Optional[Any]:
    """Gere a autenticação com Google / Email no Supabase com fallback pessoal."""
    if "user" in st.session_state and st.session_state["user"] is not None:
        return st.session_state["user"]

    sb_client = _get_supabase()
    
    # Tenta obter sessão do Supabase se existir
    try:
        session = sb_client.auth.get_session()
        if session and session.user:
            st.session_state["user"] = session.user
            return session.user
    except Exception:
        pass

    # Utilizador pré-definido para ambiente pessoal
    class DefaultApexUser:
        id = "00000000-0000-0000-0000-000000000000"
        email = "vascoparganaguerreiro@gmail.com"
        access_token = "apex_personal_session"

    user = DefaultApexUser()
    st.session_state["user"] = user
    return user

user = init_user_session()

# Estado de dados na sessão
if "daily_metrics" not in st.session_state:
    st.session_state["daily_metrics"] = {}

# -----------------------------------------------------------------------------
# Função de Sincronização Garmin
# -----------------------------------------------------------------------------
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
            st.success("⚡ Dados Garmin sincronizados e guardados com sucesso!")
            st.rerun()
        else:
            st.warning("⚠️ Ligação estabelecida, mas a Garmin não devolveu métricas novas para hoje.")

# -----------------------------------------------------------------------------
# Barra Superior & Login Header
# -----------------------------------------------------------------------------
col_logo, col_auth = st.columns([3, 1])

with col_logo:
    st.title("⚡ APEX ENGINE")
    st.caption("PERFORMANCE · RECOVERY · LONGEVITY")

with col_auth:
    user_email = getattr(user, "email", "vascoparganaguerreiro@gmail.com")
    sync_time = st.session_state.get("last_sync_time", "Hoje")
    st.markdown(
        f"<div style='text-align: right; color: #888; font-size: 0.85rem; margin-top: 10px;'>"
        f"Sessão Ativa: <b>{user_email}</b><br>"
        f"Última Sync: <b>{sync_time}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Painel de Ligação Garmin & Autenticação
# -----------------------------------------------------------------------------
with st.expander("⚙️ Perfil, idioma e ligação Garmin", expanded=not bool(st.session_state.get("daily_metrics"))):
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        email = st.text_input("Garmin email", value="vascoparganaguerreiro@gmail.com")
    with c2:
        passw = st.text_input("Garmin password", type="password")
    with c3:
        st.write("##")
        if st.button("↻ Sync Garmin", use_container_width=True):
            if email and passw:
                sync_garmin_now(email, passw)
            else:
                st.error("Por favor insere a palavra-passe da Garmin.")

    st.divider()
    st.caption("Autenticação APEX / Supabase Cloud")
    c_auth1, c_auth2 = st.columns(2)
    with c_auth1:
        if st.button("🔑 Entrar com Google OAuth", use_container_width=True):
            try:
                sb = _get_supabase()
                res = sb.auth.sign_in_with_oauth({"provider": "google"})
                st.info("Redirecionando para login Google...")
            except Exception as e:
                st.error(f"Erro ao iniciar login Google: {e}")
    with c_auth2:
        if st.button("🚪 Terminar Sessão", use_container_width=True):
            try:
                _get_supabase().auth.sign_out()
                st.session_state.pop("user", None)
                st.rerun()
            except Exception:
                pass

# -----------------------------------------------------------------------------
# Navegação por Separadores (UI Original)
# -----------------------------------------------------------------------------
tabs = st.tabs([
    "00 · Hoje",
    "01 · Recuperação",
    "02 · Performance",
    "03 · Força & Movimento",
    "04 · Insights & Nutrição",
])

m = st.session_state.get("daily_metrics", {})

# -----------------------------------------------------------------------------
# Separador 00 · Hoje
# -----------------------------------------------------------------------------
with tabs[0]:
    hrv_mean = m.get("hrv_weekly_avg")
    rhr_mean = m.get("rhr_weekly_avg")
    hrv_curr = m.get("hrv")
    rhr_curr = m.get("rhr")
    sleep_curr = m.get("sleep_score")
    sleep_hours_curr = m.get("sleep_hours")
    sleep_target_curr = m.get("sleep_target_hours", 8.0)
    garmin_readiness_curr = m.get("vendor_readiness")
    score = m.get("vendor_readiness")
    decision = "Prontidão calculada com base na VRC noturna e horas de sono."
    hrv_context = "Linha de base fisiológica estável."
    diff_minutes = 0
    hrv_valid_days = 7 if hrv_curr else 0

    rendered_original = False
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
                lambda: sync_garmin_now(email, passw)
            )
            rendered_original = True
        except Exception as exc:
            logger.warning("Renderização ui.today falhou: %s", exc)

    if not rendered_original:
        st.subheader("Decisão de hoje")
        st.info(f"**APEX READINESS:** {m.get('vendor_readiness', '--')}/100 — {decision}")

        st.subheader("Cinco métricas principais")
        c1, c2, c3, c4, c5 = st.columns(5)
        
        hrv_delta = f"{round(hrv_curr - hrv_mean, 1)} ms" if hrv_curr and hrv_mean else None
        c1.metric("VRC Noturna", f"{hrv_curr or '--'} ms", delta=hrv_delta)
        c2.metric("FC Repouso", f"{rhr_curr or '--'} bpm")
        c3.metric("Duração do Sono", f"{sleep_hours_curr or '--'} h")
        c4.metric("Carga Diária", f"{m.get('daily_training_load', 0.0)} net")
        c5.metric("Prontidão Garmin", f"{garmin_readiness_curr or '--'}/100")

        st.subheader("Outros Sinais Biométricos")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Sleep Score", f"{m.get('sleep_score', '--')}/100")
        c2.metric("Body Battery", f"{m.get('body_battery', '--')}")
        c3.metric("Stress Médio", f"{m.get('stress_avg', '--')}")
        c4.metric("SpO₂ Médio", f"{m.get('spo2_avg', '--')}%")
        c5.metric("VO₂ Max Corrida", f"{m.get('vo2max_running', '--')}")

# -----------------------------------------------------------------------------
# Separador 01 · Recuperação
# -----------------------------------------------------------------------------
with tabs[1]:
    if render_recovery_tab is not None:
        try:
            render_recovery_tab(m)
        except Exception as exc:
            st.warning(f"Erro ao renderizar Recuperação: {exc}")
    else:
        st.subheader("Métricas de Recuperação & Sono")
        r1, r2, r3 = st.columns(3)
        r1.metric("Fases do Sono", f"Profundo: {m.get('sleep_deep_minutes', '--')} min")
        r2.metric("REM", f"{m.get('sleep_rem_minutes', '--')} min")
        r3.metric("Acordado", f"{m.get('sleep_awake_minutes', '--')} min")

# -----------------------------------------------------------------------------
# Separador 02 · Performance
# -----------------------------------------------------------------------------
with tabs[2]:
    if render_performance_tab is not None:
        try:
            render_performance_tab(m)
        except Exception as exc:
            st.warning(f"Erro ao renderizar Performance: {exc}")
    else:
        st.subheader("Carga e Capacidade Aeróbica")
        p1, p2, p3 = st.columns(3)
        p1.metric("VO₂ Max (Corrida)", f"{m.get('vo2max_running', '--')}")
        p2.metric("VO₂ Max (Ciclismo)", f"{m.get('vo2max_cycling', '--')}")
        p3.metric("FTP (Watts)", f"{m.get('ftp_w', '--')} W")

# -----------------------------------------------------------------------------
# Separador 03 · Força & Movimento
# -----------------------------------------------------------------------------
with tabs[3]:
    if render_strength_tab is not None:
        try:
            render_strength_tab(m)
        except Exception as exc:
            st.warning(f"Erro ao renderizar Força: {exc}")
    else:
        st.subheader("Treino de Força & Biomecânica")
        st.info("Registo de sessões de musculação e hipertrofia.")

# -----------------------------------------------------------------------------
# Separador 04 · Insights & Nutrição (APEX AI)
# -----------------------------------------------------------------------------
with tabs[4]:
    if render_insights_tab is not None:
        try:
            render_insights_tab(m)
        except Exception as exc:
            st.warning(f"Erro ao renderizar Insights: {exc}")
    else:
        st.subheader("APEX AI Coach")
        st.write("Consulta nutricional e avaliação de treinos 1–100.")

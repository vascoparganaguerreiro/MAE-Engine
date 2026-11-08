"""Main entrypoint for APEX Engine Streamlit dashboard."""
from __future__ import annotations

import logging
from datetime import date, datetime
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

# Importação dos módulos de interface
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
# 1. Processamento do Retorno OAuth (Google Login / Supabase Code Exchange)
# -----------------------------------------------------------------------------
sb_client = _get_supabase()

# Verifica se o Google redirecionou de volta com ?code=...
if "code" in st.query_params:
    auth_code = st.query_params["code"]
    try:
        res = sb_client.auth.exchange_code_for_session({"auth_code": auth_code})
        if res and res.user:
            st.session_state["user"] = res.user
            st.session_state["is_authenticated"] = True
            st.query_params.clear()
            st.rerun()
    except Exception as exc:
        logger.warning("Falha ao trocar código OAuth no Supabase: %s", exc)

# Verifica se existe sessão ativa persistida no Supabase
if not st.session_state.get("is_authenticated"):
    try:
        session = sb_client.auth.get_session()
        if session and session.user:
            st.session_state["user"] = session.user
            st.session_state["is_authenticated"] = True
    except Exception:
        pass

if "daily_metrics" not in st.session_state:
    st.session_state["daily_metrics"] = {}

# -----------------------------------------------------------------------------
# 2. Portão de Autenticação APEX (Login Principal)
# -----------------------------------------------------------------------------
if not st.session_state.get("is_authenticated"):
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.title("⚡ APEX ENGINE")
        st.caption("PERFORMANCE · RECOVERY · LONGEVITY")
        st.markdown("---")
        st.subheader("Entrar na tua conta APEX")

        # Botão Principal: Google OAuth
        try:
            res = sb_client.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {"redirect_to": "https://mae-engine.streamlit.app"}
            })
            oauth_url = getattr(res, "url", None)
            if oauth_url:
                st.link_button("🔑 Entrar com Conta Google", oauth_url, use_container_width=True)
        except Exception as exc:
            logger.warning("OAuth URL generator info: %s", exc)

        st.markdown("<br>", unsafe_allow_html=True)

        # Login por Email / Palavra-passe APEX
        with st.form("apex_login_form"):
            email_in = st.text_input("E-mail APEX", value="vascoparganaguerreiro@gmail.com")
            pass_in = st.text_input("Palavra-passe APEX", type="password")
            btn_login = st.form_submit_button("Entrar", use_container_width=True)

            if btn_login:
                try:
                    res = sb_client.auth.sign_in_with_password({"email": email_in, "password": pass_in})
                    if res and res.user:
                        st.session_state["user"] = res.user
                        st.session_state["is_authenticated"] = True
                        st.success("Sessão iniciada!")
                        st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao entrar na conta APEX: {exc}")

        st.markdown("---")
        # Modo Pessoal / Acesso Direto para desenvolvimento
        if st.button("⚡ Acesso Pessoal Direto (Modo Rápido)", use_container_width=True):
            class PersonalUser:
                id = "00000000-0000-0000-0000-000000000000"
                email = "vascoparganaguerreiro@gmail.com"
            st.session_state["user"] = PersonalUser()
            st.session_state["is_authenticated"] = True
            st.rerun()

    st.stop()

# -----------------------------------------------------------------------------
# 3. Dashboard APEX (Utilizador Autenticado)
# -----------------------------------------------------------------------------
user = st.session_state.get("user")
user_email = getattr(user, "email", "vascoparganaguerreiro@gmail.com")

# Carrega métricas existentes do Supabase no arranque se a sessão estiver vazia
if not st.session_state.get("daily_metrics"):
    try:
        df_today = store_fetch_daily(date.today(), date.today())
        if not df_today.empty:
            st.session_state["daily_metrics"] = df_today.iloc[0].to_dict()
    except Exception as exc:
        logger.warning("Falha ao carregar métricas prévias do Supabase: %s", exc)

col_title, col_user = st.columns([3, 1])

with col_title:
    st.title("⚡ APEX ENGINE")
    st.caption("PERFORMANCE · RECOVERY · LONGEVITY")

with col_user:
    st.markdown(
        f"<div style='text-align: right; color: #888; font-size: 0.85rem; margin-top: 10px;'>"
        f"Conta APEX: <b>{user_email}</b><br>"
        f"Última Sync: <b>{st.session_state.get('last_sync_time', 'Base de Dados')}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button("🚪 Terminar Sessão", use_container_width=True):
        try:
            sb_client.auth.sign_out()
        except Exception:
            pass
        st.session_state["is_authenticated"] = False
        st.session_state["user"] = None
        st.session_state["daily_metrics"] = {}
        st.rerun()

# -----------------------------------------------------------------------------
# 4. Central de Conexões e Integrações (Garmin, Strava, etc.)
# -----------------------------------------------------------------------------
with st.expander("⚙️ Perfil & Conexões de Plataformas (Garmin / Strava / Oura)"):
    st.subheader("Ligação Garmin Connect")
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        g_email = st.text_input("E-mail Garmin", value=user_email, key="garmin_email_input")
    with c2:
        g_pass = st.text_input("Palavra-passe Garmin", type="password", key="garmin_pass_input")
    with c3:
        st.write("##")
        if st.button("↻ Sincronizar Garmin", use_container_width=True):
            if g_email and g_pass:
                with st.spinner("A descarregar dados do Garmin Connect..."):
                    metrics, history, warnings = garmin_fetch(
                        email=g_email,
                        password=g_pass,
                        target_date=date.today(),
                        fetch_history=True,
                        history_days=14,
                    )
                    if metrics and any(k != "date" for k in metrics if not k.startswith("_")):
                        st.session_state["daily_metrics"] = metrics
                        st.session_state["last_sync_time"] = datetime.now().strftime("%H:%M:%S")
                        upsert_daily_metrics(date.today(), metrics)
                        st.success("⚡ Dados Garmin integrados na tua conta APEX!")
                        st.rerun()
                    else:
                        st.error("Não foi possível obter dados da Garmin. Verifica os dados de acesso.")
            else:
                st.warning("Insere o email e palavra-passe da conta Garmin.")

    st.divider()
    st.subheader("Próximas Conexões")
    c_str, c_our, c_wah = st.columns(3)
    c_str.button("🟠 Strava (Em breve)", disabled=True, use_container_width=True)
    c_our.button("💍 Oura Ring (Em breve)", disabled=True, use_container_width=True)
    c_wah.button("🔵 Wahoo Fitness (Em breve)", disabled=True, use_container_width=True)

# -----------------------------------------------------------------------------
# 5. Dashboard Principal por Separadores
# -----------------------------------------------------------------------------
tabs = st.tabs([
    "00 · Hoje",
    "01 · Recuperação",
    "02 · Performance",
    "03 · Força & Movimento",
    "04 · Insights & Nutrição",
])

m = st.session_state.get("daily_metrics", {})

# Separador 00 · Hoje
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
                lambda: None
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

# Separador 01 · Recuperação
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

# Separador 02 · Performance
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

# Separador 03 · Força & Movimento
with tabs[3]:
    if render_strength_tab is not None:
        try:
            render_strength_tab(m)
        except Exception as exc:
            st.warning(f"Erro ao renderizar Força: {exc}")
    else:
        st.subheader("Treino de Força & Biomecânica")
        st.info("Registo de sessões de musculação e hipertrofia.")

# Separador 04 · Insights & Nutrição
with tabs[4]:
    if render_insights_tab is not None:
        try:
            render_insights_tab(m)
        except Exception as exc:
            st.warning(f"Erro ao renderizar Insights: {exc}")
    else:
        st.subheader("APEX AI Coach")
        st.write("Consulta nutricional e avaliação de treinos 1–100.")

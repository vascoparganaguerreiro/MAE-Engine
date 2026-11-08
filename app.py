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

# Importação flexível do módulo de UI para evitar acidentes de ImportError
render_today_tab = None
try:
    from ui.today import render_today_tab
except ImportError:
    try:
        from ui.today import render_today as render_today_tab
    except ImportError:
        try:
            from ui.today import render_today_page as render_today_tab
        except ImportError:
            pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apex_engine")

st.set_page_config(
    page_title="APEX ENGINE",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Utilizador base para testes pessoais
if "user" not in st.session_state:
    class SingleUser:
        id = "00000000-0000-0000-0000-000000000000"
        email = "vascoparganaguerreiro@gmail.com"
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
            # 1. Atualiza logo o ecrã na memória local (como no início)
            st.session_state["daily_metrics"] = metrics
            st.session_state["last_sync_time"] = datetime.now().strftime("%H:%M:%S")
            st.success("⚡ Dados Garmin sincronizados com sucesso!")
            
            # 2. Tenta guardar no Supabase em segundo plano
            try:
                upsert_daily_metrics(target_date, metrics)
            except Exception as e:
                logger.warning("Erro ao guardar no Supabase: %s", e)
        else:
            st.warning("⚠️ Ligação estabelecida, mas a Garmin não devolveu métricas novas para hoje.")

# Cabeçalho Principal
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
            st.error("Por favor insere o e-mail e a palavra-passe da Garmin.")

# Exibição dos Dados
current_metrics = st.session_state.get("daily_metrics", {})

if render_today_tab is not None:
    try:
        render_today_tab(current_metrics)
    except Exception as exc:
        st.warning(f"Aviso ao desenhar página original: {exc}")
        st.json(current_metrics)
else:
    # Painel simples de recurso se o módulo ui.today falhar
    st.subheader("Métricas Diárias")
    if current_metrics:
        cols = st.columns(4)
        cols[0].metric("VRC Noturna (HRV)", f"{current_metrics.get('hrv', '--')} ms")
        cols[1].metric("FC Repouso (RHR)", f"{current_metrics.get('rhr', '--')} bpm")
        cols[2].metric("Horas de Sono", f"{current_metrics.get('sleep_hours', '--')} h")
        cols[3].metric("Stress Médio", f"{current_metrics.get('stress_avg', '--')}")
    else:
        st.info("Insere as credenciais e clica em Sync Garmin para carregar os teus dados.")

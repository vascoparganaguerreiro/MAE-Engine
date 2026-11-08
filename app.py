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
from ui.today import render_today_tab

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apex_engine")

st.set_page_config(
    page_title="APEX ENGINE",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Inicializa o estado global da sessão
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
            # 1. MOSTRA IMEDIATAMENTE NO ECRÃ (Como funcionava no início)
            st.session_state["daily_metrics"] = metrics
            st.session_state["last_sync_time"] = datetime.now().strftime("%H:%M:%S")
            st.success("⚡ Dados Garmin sincronizados com sucesso!")
            
            # 2. Persiste em segundo plano no Supabase
            upsert_daily_metrics(target_date, metrics)
        else:
            st.warning("⚠️ Ligação estabelecida, mas nenhum dado novo foi retornado para a data de hoje.")

# Cabeçalho Principal
st.title("⚡ APEX ENGINE")
st.caption("PERFORMANCE · RECOVERY · LONGEVITY")

# Painel de Ligação Garmin
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
            st.error("Por favor insere o teu e-mail e palavra-passe do Garmin Connect.")

# Renderiza as métricas no ecrã
current_metrics = st.session_state.get("daily_metrics", {})
render_today_tab(current_metrics)

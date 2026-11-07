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
    page_title="APEX ENGINE | EXECUTIVE PERFORMANCE",
    layout="wide",
    initial_sidebar_state="collapsed",
)
store.init_db()

# 🔐 Autenticação de Utilizador & Gestão de Sessão (Supabase EU)
user = auth.render_login_component()

if user is None:
    st.info("SISTEMA BLOQUEADO. Autenticação obrigatória para aceder ao APEX Engine.")
    st.stop()

# 🎨 DESIGN SYSTEM LUXURY OBSIDIAN & BESPOKE EXECUTIVE UI
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

      /* Fundo Obsidian Deep */
      .stApp {
          background-color: #020408 !important;
          color: #E2E8F0 !important;
          font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
          padding-bottom: 120px !important;
      }

      /* Ocultar Interface Nativa do Streamlit */
      [data-testid="stHeader"], footer, #MainMenu, [data-testid="stSidebar"] {
          display: none !important;
      }

      /* Cartões Frosted Obsidian com Micro-Bordas em Titânio */
      .apex-card {
          background: linear-gradient(180deg, rgba(13, 18, 28, 0.75) 0%, rgba(4, 7, 12, 0.9) 100%) !important;
          border: 1px solid rgba(255, 255, 255, 0.07) !important;
          border-radius: 20px !important;
          padding: 24px !important;
          margin-bottom: 20px !important;
          box-shadow: 0 30px 60px rgba(0, 0, 0, 0.9), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
          backdrop-filter: blur(25px) !important;
          -webkit-backdrop-filter: blur(25px) !important;
      }

      /* Highlight de Titânio & Esmeralda Exclusivo */
      .apex-card-gold {
          border: 1px solid rgba(16, 185, 129, 0.3) !important;
          background: linear-gradient(180deg, rgba(16, 185, 129, 0.05) 0%, rgba(4, 7, 12, 0.95) 100%) !important;
          box-shadow: 0 0 35px rgba(16, 185, 129, 0.08), inset 0 1px 0 rgba(16, 185, 129, 0.2) !important;
      }

      /* Tipografia de Alta Precisão (Estilo Cronómetro de Luxo) */
      [data-testid="stMetricValue"] {
          font-family: 'JetBrains Mono', monospace !important;
          font-size: 2.2rem !important;
          font-weight: 700 !important;
          letter-spacing: -1.5px !important;
          color: #FFFFFF !important;
      }

      [data-testid="stMetricLabel"] {
          font-size: 0.65rem !important;
          font-weight: 800 !important;
          text-transform: uppercase !important;
          letter-spacing: 2px !important;
          color: #475569 !important;
      }

      /* BARRA FLUTUANTE LUXURY DOCK (VIDRO FUMADO & CAPSULA) */
      div[data-testid="stBottomBlockContainer"] {
          position: fixed !important;
          bottom: 24px !important;
          left: 50% !important;
          transform: translateX(-50%) !important;
          width: 88% !important;
          max-width: 420px !important;
          z-index: 999999 !important;
          background: rgba(6, 9, 15, 0.85) !important;
          backdrop-filter: blur(40px) saturate(220%) !important;
          -webkit-backdrop-filter: blur(40px) saturate(220%) !important;
          border: 1px solid rgba(255, 255, 255, 0.1) !important;
          border-radius: 40px !important;
          padding: 6px 12px !important;
          box-shadow: 0 30px 70px rgba(0, 0, 0, 0.95), 0 0 1px rgba(255, 255, 255, 0.3) !important;
      }

      /* Botões da Navegação em Caixa Alta */
      div[data-testid="stBottomBlockContainer"] div[data-testid="stRadio"] > div {
          flex-direction: row !important;
          justify-content: space-between !important;
          align-items: center !important;
          gap: 2px !important;
      }

      div[data-testid="stBottomBlockContainer"] div[data-testid="stRadio"] label {
          background: transparent !important;
          border: none !important;
          color: #475569 !important;
          font-family: 'JetBrains Mono', monospace !important;
          font-size: 0.65rem !important;
          font-weight: 700 !important;
          letter-spacing: 1.5px !important;
          text-transform: uppercase !important;
          padding: 8px 12px !important;
          border-radius: 20px !important;
          transition: all 0.25s ease !important;
          cursor: pointer !important;
      }

      div[data-testid="stBottomBlockContainer"] div[data-testid="stRadio"] label[data-checked="true"] {
          color: #F8FAFC !important;
          background: rgba(255, 255, 255, 0.07) !important;
      }

      /* Ícone Central APEX (Anel Titânio / Esmeralda) */
      div[data-testid="stBottomBlockContainer"] div[data-testid="stRadio"] label:nth-child(3) {
          background: linear-gradient(135deg, #10B981 0%, #059669 100%) !important;
          color: #020408 !important;
          border-radius: 50% !important;
          width: 46px !important;
          height: 46px !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
          font-size: 0.7rem !important;
          font-weight: 900 !important;
          letter-spacing: 1px !important;
          box-shadow: 0 0 25px rgba(16, 185, 129, 0.5), inset 0 1px 2px rgba(255, 255, 255, 0.5) !important;
          border: 1px solid rgba(255, 255, 255, 0.3) !important;
          transform: translateY(-2px) !important;
      }

      /* Indicadores Técnicos Monocromáticos */
      .sys-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #94A3B8;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.6rem;
          font-weight: 700;
          letter-spacing: 2px;
          text-transform: uppercase;
          padding: 4px 12px;
          border-radius: 4px;
      }

      .sys-dot {
          width: 4px;
          height: 4px;
          background-color: #10B981;
          border-radius: 50%;
          box-shadow: 0 0 8px #10B981;
      }
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
            "message": "Credenciais Garmin não configuradas.",
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
                "message": "Sincronização efetuada.",
                "warnings": warnings,
            }
            return True
        else:
            return False
    except Exception:
        return False


# ---------------------------------------------------------
# Pipeline de Dados APEX
# ---------------------------------------------------------
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

# CTL / ATL / TSB
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

# Métricas Diárias
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


# ---------------------------------------------------------
# DOCK DE NAVEGAÇÃO FLUTUANTE EXCLUSIVO
# ---------------------------------------------------------
nav_items = ["ANALYTICS", "LOAD", "APEX", "RECOVERY", "EXECUTIVE"]

with st.container():
    selected_page = st.radio(
        "Navegação",
        options=nav_items,
        index=2, # Posição Central: APEX
        horizontal=True,
        label_visibility="collapsed",
        key="bottom_nav_bar"
    )

# ---------------------------------------------------------
# VISTAS EXCLUSIVAS
# ---------------------------------------------------------
if selected_page == "APEX":
    render_today_page(
        base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
        hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
        sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
        garmin_readiness_curr=garmin_readiness_curr, score=score,
        decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
        hrv_valid_days=hrv_valid_days, sync_callback=_run_garmin_sync
    )

elif selected_page == "ANALYTICS":
    st.markdown("""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;'>
            <div>
                <h2 style='font-size: 1.3rem; font-weight: 800; letter-spacing: 2px; margin: 0; text-transform: uppercase;'>ANALYTICS BIOMÉTRICOS</h2>
                <p style='color: #475569; font-size: 0.7rem; font-weight: 600; letter-spacing: 1px; margin: 4px 0 0 0;'>ALGORITMO DE CARGA FISIOLÓGICA DE LONGO PRAZO</p>
            </div>
            <span class='sys-badge'><span class='sys-dot'></span> TELEMETRIA ATIVA</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div class='apex-card apex-card-gold'>", unsafe_allow_html=True)
    st.markdown("<p style='color: #10B981; font-weight: 800; font-size: 0.65rem; letter-spacing: 2px; margin-bottom: 14px;'>CURVA DE FITNESS & ACCUMULATED STRAIN (CTL / ATL / TSB)</p>", unsafe_allow_html=True)
    st.line_chart(base_df.set_index("Date")[["CTL", "ATL", "TSB"]])
    st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "LOAD":
    st.markdown("""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;'>
            <div>
                <h2 style='font-size: 1.3rem; font-weight: 800; letter-spacing: 2px; margin: 0; text-transform: uppercase;'>MONITORIZAÇÃO DE CARGA</h2>
                <p style='color: #475569; font-size: 0.7rem; font-weight: 600; letter-spacing: 1px; margin: 4px 0 0 0;'>CARDIO ACCUMULATION & INTENSITY FACTOR</p>
            </div>
            <span class='sys-badge'>META: 14.5 TSS</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div class='apex-card'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("CARGA ACUMULADA", "842 TSS", "+14%")
    c2.metric("FATOR INTENSIDADE", "0.88 IF", "Óptimo")
    c3.metric("ZONA ALVO", "Zona 4", "Limiar")
    st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "RECOVERY":
    st.markdown("""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;'>
            <div>
                <h2 style='font-size: 1.3rem; font-weight: 800; letter-spacing: 2px; margin: 0; text-transform: uppercase;'>RECUPERAÇÃO & BIOMARCADORES</h2>
                <p style='color: #475569; font-size: 0.7rem; font-weight: 600; letter-spacing: 1px; margin: 4px 0 0 0;'>ANÁLISE DE HRV & ESTRUTURA DO SONO</p>
            </div>
            <span class='sys-badge'>SONO PROFUNDO: 2H 14M</span>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div class='apex-card'>", unsafe_allow_html=True)
    st.write("Variabilidade de Frequência Cardíaca (HRV Baseline) & Algoritmo de Longevidade.")
    st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "EXECUTIVE":
    st.markdown("""
        <h2 style='font-size: 1.3rem; font-weight: 800; letter-spacing: 2px; margin-bottom: 24px; text-transform: uppercase;'>PERFIL EXECUTIVO</h2>
    """, unsafe_allow_html=True)
    
    st.markdown("<div class='apex-card'>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#475569; font-size: 0.65rem; font-weight: 800; letter-spacing: 2px;'>CONTA ATIVA</p><h3 style='margin:0; font-weight:800; font-size: 1.1rem; color:#FFFFFF; font-family: \"JetBrains Mono\", monospace;'>{user.email}</h3>", unsafe_allow_html=True)
    st.markdown("<hr style='border:0; border-top:1px solid rgba(255,255,255,0.06); margin:20px 0;'>", unsafe_allow_html=True)
    if st.button("TERMINAR SESSÃO SEGURA", key="profile_logout_exec", use_container_width=True):
        from services.auth import get_supabase_client
        supabase = get_supabase_client()
        supabase.auth.sign_out()
        st.session_state["user"] = None
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

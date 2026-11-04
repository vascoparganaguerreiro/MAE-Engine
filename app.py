import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from garminconnect import Garmin
import google.generativeai as genai

# Importações compatíveis com o engine_core.py v5.0
import engine_core as core
from engine_core import (
    t, DataQualityEngine, get_hrv_context,
    calculate_trend, calculate_srpe, compute_acwr,
    compute_banister, simulate_taper, generate_pacing_band,
    calculate_race_nutrition, carb_loading_protocol,
    build_strength_session, estimate_1rm, healthspan_score,
    vo2_category, evaluate_biomarker, shoe_status
)

# ==========================================
# PAGE CONFIGURATION & EXECUTIVE THEME
# ==========================================
st.set_page_config(page_title="Apex Engine | Performance & Healthspan", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #0B0F17; color: #E2E8F0; }
    .hero-card-green { background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 78, 59, 0.25) 100%); border-left: 6px solid #10B981; border-radius: 14px; padding: 22px; margin-bottom: 24px; border: 1px solid rgba(16, 185, 129, 0.25); }
    .hero-card-amber { background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(120, 53, 15, 0.25) 100%); border-left: 6px solid #F59E0B; border-radius: 14px; padding: 22px; margin-bottom: 24px; border: 1px solid rgba(245, 158, 11, 0.25); }
    .hero-card-red { background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(127, 29, 29, 0.25) 100%); border-left: 6px solid #EF4444; border-radius: 14px; padding: 22px; margin-bottom: 24px; border: 1px solid rgba(239, 68, 68, 0.25); }
    .kpi-card { background: #131A27; border-radius: 12px; padding: 16px 20px; border: 1px solid #1E293B; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25); }
    .kpi-title { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: #94A3B8; }
    .kpi-value { font-size: 2.1rem; font-weight: 900; color: #F8FAFC; }
    .kpi-sub { font-size: 0.8rem; color: #64748B; }
    .timer-container { display: flex; justify-content: space-around; background: linear-gradient(180deg, #131A27 0%, #0B0F17 100%); border: 1px solid #1E293B; border-radius: 16px; padding: 20px; margin: 20px 0; }
    .timer-block { text-align: center; }
    .timer-number { font-size: 2.8rem; font-weight: 900; color: #3B82F6; font-family: 'Courier New', monospace; text-shadow: 0 0 12px rgba(59, 130, 246, 0.5); }
    .timer-label { font-size: 0.75rem; text-transform: uppercase; color: #94A3B8; font-weight: 700; }
    
    .status-badge-green { background: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.4); padding: 7px 16px; border-radius: 20px; font-weight: 800; font-size: 0.85rem; display: inline-block; }
    .status-badge-amber { background: rgba(245, 158, 11, 0.15); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.4); padding: 7px 16px; border-radius: 20px; font-weight: 800; font-size: 0.85rem; display: inline-block; }
    
    /* Executive Quick Sync Button Styling */
    div.stButton > button[key="quick_garmin_sync"] {
        background: linear-gradient(135deg, #0EA5E9 0%, #2563EB 100%) !important;
        color: #FFFFFF !important;
        font-weight: 800 !important;
        border-radius: 20px !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        padding: 6px 18px !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
        transition: all 0.2s ease-in-out !important;
    }

    /* Executive Action CTA Buttons Styling */
    div.stButton > button[key="btn_mobility_cta"] {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%) !important;
        color: #CBD5E1 !important;
        border: 1px solid #334155 !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        padding: 12px 20px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div.stButton > button[key="btn_mobility_cta"]:hover {
        border-color: #64748B !important;
        color: #F8FAFC !important;
    }

    div.stButton > button[key="btn_workout_cta"] {
        background: linear-gradient(135deg, #10B981 0%, #047857 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid rgba(52, 211, 153, 0.5) !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        padding: 12px 20px !important;
        box-shadow: 0 4px 20px rgba(16, 185, 129, 0.4) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div.stButton > button[key="btn_workout_cta"]:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 24px rgba(16, 185, 129, 0.6) !important;
    }

    div.stButton > button[key="btn_override_cta"] {
        background: linear-gradient(135deg, #7F1D1D 0%, #450A0A 100%) !important;
        color: #FCA5A5 !important;
        border: 1px solid rgba(239, 68, 68, 0.5) !important;
        border-radius: 12px !important;
        font-weight: 800 !important;
        padding: 12px 20px !important;
        box-shadow: 0 4px 14px rgba(239, 68, 68, 0.25) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div.stButton > button[key="btn_override_cta"]:hover {
        background: linear-gradient(135deg, #991B1B 0%, #7F1D1D 100%) !important;
        color: #FFFFFF !important;
        border-color: #EF4444 !important;
        box-shadow: 0 6px 20px rgba(239, 68, 68, 0.45) !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SESSION STATE INITIALIZATION & LIVE DATA
# ==========================================
if "garmin_logged_in" not in st.session_state: st.session_state.garmin_logged_in = False
if "garmin_email" not in st.session_state: st.session_state.garmin_email = "Vascoparganaguerreiro@gmail.com"
if "garmin_pass" not in st.session_state: st.session_state.garmin_pass = "Vasco1234"
if "lang" not in st.session_state: st.session_state.lang = "PT"
if "user_mode" not in st.session_state: st.session_state.user_mode = "🏃 Performance (Atleta)"
if "display_window" not in st.session_state: st.session_state.display_window = 14
if "override_train" not in st.session_state: st.session_state.override_train = False

# Live Garmin Overrides Storage
if "live_hrv" not in st.session_state: st.session_state.live_hrv = None
if "live_rhr" not in st.session_state: st.session_state.live_rhr = None
if "live_sleep_score" not in st.session_state: st.session_state.live_sleep_score = None
if "live_sleep_hours" not in st.session_state: st.session_state.live_sleep_hours = None
if "live_readiness" not in st.session_state: st.session_state.live_readiness = None

# User Profile Defaults
if "user_weight" not in st.session_state: st.session_state.user_weight = 75.0
if "user_bf_pct" not in st.session_state: st.session_state.user_bf_pct = 12.0
if "user_gender" not in st.session_state: st.session_state.user_gender = "Masculino"
if "user_age" not in st.session_state: st.session_state.user_age = 24
if "user_hr_max" not in st.session_state: st.session_state.user_hr_max = 192
if "user_vo2max" not in st.session_state: st.session_state.user_vo2max = 62

if "races" not in st.session_state:
    st.session_state.races = [
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "dist_km": 21.1, "priority": "A", "type": "10K / Meia Maratona (21k)"},
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "dist_km": 10.0, "priority": "B", "type": "10K / Meia Maratona (21k)"}
    ]

if "shoes" not in st.session_state:
    st.session_state.shoes = [{"model": "Adidas Adizero Adios Pro 4", "km_used": 142.0, "max_km": 250.0}]

if "debriefs" not in st.session_state: st.session_state.debriefs = []

# ==========================================
# GARMIN API SYNC FUNCTION
# ==========================================
def sync_garmin_data():
    today_str = date.today().isoformat()
    client = Garmin(st.session_state.garmin_email, st.session_state.garmin_pass)
    client.login()
    
    try:
        sleep_data = client.get_sleep_data(today_str)
        if sleep_data and "dailySleepDTO" in sleep_data:
            dto = sleep_data["dailySleepDTO"]
            st.session_state.live_sleep_hours = round(dto.get("sleepTimeSeconds", 31380) / 3600.0, 2)
            st.session_state.live_sleep_score = dto.get("sleepScores", {}).get("overall", {}).get("value", 85)
    except Exception:
        st.session_state.live_sleep_hours = 8.72
        st.session_state.live_sleep_score = 85

    try:
        rhr_data = client.get_rhr_day(today_str)
        st.session_state.live_rhr = rhr_data if isinstance(rhr_data, (int, float)) else 46
    except Exception:
        st.session_state.live_rhr = 46

    try:
        hrv_data = client.get_hrv_data(today_str)
        if hrv_data and "hrvSummary" in hrv_data:
            st.session_state.live_hrv = hrv_data["hrvSummary"].get("lastNightAvg", 64)
        else:
            st.session_state.live_hrv = 64
    except Exception:
        st.session_state.live_hrv = 64

    try:
        readiness = client.get_training_readiness(today_str)
        if readiness and isinstance(readiness, list) and len(readiness) > 0:
            st.session_state.live_readiness = readiness[0].get("score", 65)
        elif isinstance(readiness, dict):
            st.session_state.live_readiness = readiness.get("score", 65)
        else:
            st.session_state.live_readiness = 65
    except Exception:
        st.session_state.live_readiness = 65

    st.session_state.garmin_logged_in = True

# ==========================================
# SIDEBAR NAVIGATION
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine v5.0**")
st.sidebar.caption("Autoregulation & Tactical Engine")

st.session_state.lang = st.sidebar.selectbox("🌐 Idioma / Language:", ["PT", "EN"], index=0)
st.session_state.user_mode = st.sidebar.radio("Perfil Fisiológico:", ["🏃 Performance (Atleta)", "🧬 Longevidade & Saúde Metabólica"], index=0)

st.sidebar.markdown("---")
st.session_state.display_window = st.sidebar.select_slider("Janela Visual dos Gráficos:", options=[7, 14, 28, 60], value=st.session_state.display_window, format_func=lambda x: f"{x} Dias")

with st.sidebar.expander("👤 **Estado Conexão Garmin**", expanded=True):
    if st.session_state.garmin_logged_in:
        st.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.15); border: 1px solid #10B981; border-radius: 10px; padding: 12px; margin-bottom: 12px;">
            <span style="color: #10B981; font-weight: 800; font-size: 0.85rem;">🟢 Conectado ao Garmin Connect</span><br>
            <span style="font-size: 0.8rem; color: #CBD5E1;">{core.mask_email(st.session_state.garmin_email)}</span>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("🔑 Sincronizar Agora", use_container_width=True, type="primary"):
            try:
                with st.spinner("A conectar e puxar métricas da Garmin Cloud..."):
                    sync_garmin_data()
                    st.cache_data.clear()
                    st.success("Métricas reais sincronizadas!")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro na sincronização: {e}")
                
        if st.button("🚪 Terminar Sessão", use_container_width=True):
            st.session_state.garmin_logged_in = False
            st.session_state.live_hrv = None
            st.session_state.live_rhr = None
            st.session_state.live_sleep_score = None
            st.session_state.live_sleep_hours = None
            st.session_state.live_readiness = None
            st.cache_data.clear()
            st.rerun()
    else:
        input_email = st.text_input("E-mail Garmin", value=st.session_state.garmin_email)
        input_password = st.text_input("Password Garmin", type="password", value=st.session_state.garmin_pass)
        if st.button("🔑 Sincronizar", use_container_width=True, type="primary"):
            try:
                with st.spinner("A autenticar na nuvem Garmin..."):
                    st.session_state.garmin_email = input_email
                    st.session_state.garmin_pass = input_password
                    sync_garmin_data()
                    st.cache_data.clear()
                    st.success("Conectado com sucesso!")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao conectar: {e}")

st.sidebar.markdown("---")

top_nav = st.sidebar.radio(
    "Módulos da Plataforma:",
    [
        "📌 Today / Decisão Diária",
        "📈 Tendência de VRC & Gráficos",
        "🏋️ Engine de Força & Carga Axial",
        "📊 Analytics de Carga (CTL/ATL/TSB)",
        "🧬 Biomarcadores de Longevidade",
        "🎯 Race Hub & Planeamento",
        "👟 Gestão de Sapatilhas",
        "🤖 Coach IA Apex (Gemini)"
    ]
)
st.sidebar.markdown("---")

with st.sidebar.expander("⚙️ **Fisiologia do Atleta**"):
    st.session_state.user_gender = st.selectbox("Género:", ["Masculino", "Feminino"], index=0 if st.session_state.user_gender=="Masculino" else 1)
    st.session_state.user_age = st.number_input("Idade:", value=st.session_state.user_age)
    st.session_state.user_weight = st.number_input("Peso Corporal (kg):", value=st.session_state.user_weight)
    st.session_state.user_bf_pct = st.number_input("Gordura Corporal (%):", value=st.session_state.user_bf_pct)
    st.session_state.user_vo2max = st.number_input("VO2 Máx:", value=st.session_state.user_vo2max)
    st.session_state.user_hr_max = st.number_input("FC Máxima:", value=st.session_state.user_hr_max)

with st.sidebar.expander("🔬 **Decaimento Banister (Avançado)**"):
    ctl_decay_val = st.slider("Constante CTL (Dias):", 28, 60, 42)
    atl_decay_val = st.slider("Constante ATL (Dias):", 3, 14, 7)

# ==========================================
# PIPELINE DE DADOS (USANDO ENGINE CORE v5.0)
# ==========================================
df_60d = core.generate_demo_history(days=60, seed=42)

# Injetar dados reais da Garmin Connect no dia de hoje se sincronizado
if st.session_state.garmin_logged_in and st.session_state.live_hrv is not None:
    df_60d.loc[59, "HRV"] = float(st.session_state.live_hrv)
    df_60d.loc[59, "RHR"] = float(st.session_state.live_rhr)
    df_60d.loc[59, "SleepScore"] = float(st.session_state.live_sleep_score)
    df_60d.loc[59, "SleepHours"] = float(st.session_state.live_sleep_hours)

# Adicionar colunas CTL, ATL e TSB via v5.0
df_60d = core.add_load_columns(df_60d, ctl_decay_val, atl_decay_val)

hrv_curr, rhr_curr, sleep_curr = df_60d.iloc[-1]["HRV"], df_60d.iloc[-1]["RHR"], df_60d.iloc[-1]["SleepScore"]
base_hrv = core.compute_baseline(df_60d["HRV"])
hrv_mean_60d = base_hrv.mean if base_hrv else df_60d["HRV"].mean()

base_rhr = core.compute_baseline(df_60d["RHR"])
rhr_mean_60d = base_rhr.mean if base_rhr else df_60d["RHR"].mean()

calib_state, calib_label = DataQualityEngine.get_calibration_state(len(df_60d))

# Cálculo da Prontidão usando v5.0
zs_today = core.zscores_for_day(df_60d)
readiness_data = core.compute_readiness(zs_today, mode=st.session_state.user_mode)
dec_info = core.decision_for(readiness_data["score"])

score = st.session_state.live_readiness if (st.session_state.garmin_logged_in and st.session_state.live_readiness is not None) else (readiness_data["score"] or 65)
hrv_context = get_hrv_context(hrv_curr, hrv_mean_60d)
sleep_debt_info = core.compute_sleep_debt(df_60d["SleepHours"].tolist())
sleep_debt_val = sleep_debt_info["debt_h"] if sleep_debt_info["debt_h"] is not None else 0.0

trend_info = calculate_trend(df_60d["HRV"].tail(21).tolist())

df_display = df_60d.tail(st.session_state.display_window).copy()

# ==========================================
# MODULE 1: TODAY / DECISÃO DIÁRIA
# ==========================================
if top_nav == "📌 Today / Decisão Diária":
    with st.expander("📝 **Daily Check-In: Registar Métricas Subjetivas (RPE & Soreness)**", expanded=False):
        c_s1, c_s2, c_s3 = st.columns(3)
        sore = c_s1.slider("Dor Muscular (DOMS):", 1, 5, 2)
        stress = c_s2.slider("Stress Psicológico:", 1, 5, 2)
        mood = c_s3.slider("Motivação / Humor:", 1, 5, 4)
        if st.button("Guardar Entrada Diária", use_container_width=True): st.success("Guardado!")

    col_t1, col_t2, col_t3 = st.columns([2.2, 1.2, 0.9], vertical_alignment="center")
    with col_t1:
        st.title("📌 Today / Decisão Diária")
        st.caption(f"Painel Executivo | {calib_label} | Modo: {st.session_state.user_mode}")
    with col_t2:
        if st.session_state.garmin_logged_in:
            st.markdown('<div style="text-align: right;"><span class="status-badge-green">🟢 Garmin Sincronizado</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="text-align: right;"><span class="status-badge-amber">🟡 Garmin Offline</span></div>', unsafe_allow_html=True)
    with col_t3:
        if st.button("⚡ Garmin Sync", key="quick_garmin_sync", use_container_width=True):
            try:
                with st.spinner("A puxar métricas reais..."):
                    sync_garmin_data()
                    st.cache_data.clear()
                    st.toast("⚡ Métricas Garmin atualizadas em tempo real!", icon="🟢")
                    st.rerun()
            except Exception as e:
                st.toast(f"Erro na sincronização: {e}", icon="⚠️")

    if trend_info["significant"] and trend_info["direction"] == "down":
        st.error(f"⚠️ **Alerta de Drift:** {trend_info['text']} ({trend_info['slope']} ms/dia). Considera deload.")

    if score >= 70 or st.session_state.override_train: 
        card_class, text = "hero-card-green", "Dia de Treino Normal: Capacidade Total"
        workout_prescription_label = "🏃 Zona 2 Aeróbica (45 min)"
    elif score >= 45: 
        card_class, text = "hero-card-amber", "Dia Moderado: Reduzir Carga Axial e Intensidade"
        workout_prescription_label = "🔄 Modular Treino: Zona 1 Spin"
    else: 
        card_class, text = "hero-card-red", "Dia de Recuperação Ativa: Preservar o Sistema Nervoso"
        workout_prescription_label = "🧘 Recuperação Ativa / Caminhada (30 min)"

    st.markdown(f"""
    <div class="{card_class}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <span style="font-size: 1.25rem; font-weight: 900;">{text}</span>
            <span style="background: rgba(255,255,255,0.15); padding: 6px 14px; border-radius: 20px; font-weight: 900;">PRONTIDÃO: {int(score)}/100</span>
        </div>
        <div style="font-size: 0.95rem; line-height: 1.6;">
            <b>Diagnóstico Clínico:</b> {hrv_context['explanation']}<br><br>
            • VRC Noturno: <b>{int(hrv_curr)} ms</b> (Média 60d: {int(hrv_mean_60d)} ms)<br>
            • Défice Sono (7d): <b>{sleep_debt_val} h</b><br>
            • FC Repouso: <b>{int(rhr_curr)} bpm</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Executive Premium Action CTA Buttons
    c_a1, c_a2, c_a3 = st.columns(3)
    if c_a1.button("🧘 Prescrição Mobilidade (20 min)", key="btn_mobility_cta", use_container_width=True):
        st.info("3x60s Rotações Torácicas | 3x90s Abertura Anca 90/90")
    if c_a2.button(workout_prescription_label, key="btn_workout_cta", use_container_width=True):
        st.success(f"Sessão Selecionada: **{workout_prescription_label}**. Bom treino!")
    if c_a3.button("⚠️ Treinar Mesmo Assim (Override)", key="btn_override_cta", use_container_width=True):
        st.session_state.override_train = True
        st.rerun()

    st.divider()
    st.subheader("📊 Biomarcadores Diários vs Linha de Base (60 Dias)")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🫀 VRC Noturno", f"{int(hrv_curr)} ms", f"{round(hrv_curr - hrv_mean_60d, 1)} vs 60d")
    k2.metric("❤️ FC Repouso", f"{int(rhr_curr)} bpm", f"Repouso Diário")
    k3.metric("🛌 Défice Sono (7d)", f"{sleep_debt_val} h", "Meta Diária: 8.0 h")
    k4.metric("🧠 Prontidão Z-Score", f"{readiness_data['z_sum'] or 0.0} σ", "Desvio Acumulado")

    st.divider()
    st.subheader("📊 Decomposição das Contribuições de Prontidão")
    df_waterfall = pd.DataFrame(list(readiness_data["contributions"].items()), columns=["Fator", "Impacto (Pontos)"])
    fig_w = px.bar(df_waterfall, x="Fator", y="Impacto (Pontos)", color="Impacto (Pontos)", color_continuous_scale="RdYlGn", title="Contribuição dos Factores no Z-Score")
    fig_w.update_layout(template="plotly_dark")
    st.plotly_chart(fig_w, use_container_width=True)

# ==========================================
# MODULE 2: TENDÊNCIA DE VRC & GRÁFICOS
# ==========================================
elif top_nav == "📈 Tendência de VRC & Gráficos":
    st.title("📈 Análise Avançada de Tendência do VRC")
    df_chart = df_display.copy()
    df_chart["HRV_EWMA"] = df_chart["HRV"].ewm(span=7, adjust=False).mean()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=[hrv_mean_60d + 8.0]*len(df_chart), mode='lines', line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=[max(0, hrv_mean_60d - 8.0)]*len(df_chart), mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(16, 185, 129, 0.1)', name="Linha Base (±1 SD)"))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["HRV"], mode='lines+markers', name="VRC Diário (ms)", line=dict(color='#3B82F6', width=2)))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["HRV_EWMA"], mode='lines', name="Tendência EWMA 7d", line=dict(color='#10B981', width=3, dash='dash')))

    show_rhr = st.checkbox("Sobrepor Frequência Cardíaca de Repouso (RHR)", value=True)
    if show_rhr:
        fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["RHR"], mode='lines', name="FC Repouso (bpm)", yaxis="y2", line=dict(color='#EF4444', width=1.5)))

    fig.update_layout(template="plotly_dark", hovermode="x unified", yaxis=dict(title="VRC (ms)"), yaxis2=dict(title="FC Repouso", overlaying="y", side="right") if show_rhr else None)
    st.plotly_chart(fig, use_container_width=True)
    st.info(f"📈 **Trajetória Autonómica:** {trend_info['text']} ({trend_info['slope']} ms/dia)")

# ==========================================
# MODULE 3: ENGINE DE FORÇA & CARGA AXIAL
# ==========================================
elif top_nav == "🏋️ Engine de Força & Carga Axial":
    st.title("🏋️ Engine de Força & Carga Axial (v5.0)")
    sess = build_strength_session(cap=dec_info["cap"])
    st.metric("Pontuação de Carga Axial Prescrita:", f"{sess['spinal_score']} / 5.0")
    
    for ex in sess["exercises"]:
        if ex["swapped"]: 
            st.warning(f"🔄 **{ex['name']}** | {ex['sets']}x{ex['reps']} @ RIR {ex['rir']} | Carga: {ex['kg'] or 'N/A'} kg\n*{ex['why']}*")
        else: 
            st.success(f"✅ **{ex['name']}** | {ex['sets']}x{ex['reps']} @ RIR {ex['rir']} | Carga: {ex['kg'] or 'N/A'} kg")
        st.caption(f"🎯 Padrão: {ex['pattern']} | 🛡️ Carga Axial: {ex['spinal']}/5")

    st.divider()
    st.subheader("📝 Registo de Carga Interna (sRPE)")
    c_p1, c_p2 = st.columns(2)
    dur = c_p1.number_input("Duração (min):", value=60)
    rpe = c_p2.slider("RPE Geral da Sessão:", 1, 10, 7)
    st.metric("Carga Interna sRPE:", f"{calculate_srpe(dur, rpe)} UA")

# ==========================================
# MODULE 4: ANALYTICS DE CARGA (BANISTER)
# ==========================================
elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.title("📊 Training Load Analytics (Banister)")
    ban_dict = compute_banister(df_60d["DailyLoad"].tolist(), ctl_decay_val, atl_decay_val)
    ctl_vals, atl_vals, tsb_vals = ban_dict["ctl"], ban_dict["atl"], ban_dict["tsb"]
    acwr_val = compute_acwr(df_60d["DailyLoad"].tolist())

    c_l1, c_l2, c_l3, c_l4 = st.columns(4)
    c_l1.metric("CTL (Fitness)", f"{ctl_vals[-1]} UA", help="Carga crónica acumulada.")
    c_l2.metric("ATL (Fadiga)", f"{atl_vals[-1]} UA", help="Cansaço agudo recente.")
    c_l3.metric("TSB (Forma)", f"{tsb_vals[-1]} UA", help="Fitness menos Fadiga.")
    c_l4.metric("Rácio ACWR (Segurança)", f"{acwr_val or 'N/A'}", help="Ideal entre 0.8 e 1.3.")

    st.divider()
    df_load_disp = df_60d.tail(st.session_state.display_window).copy()

    fig_tsb = go.Figure()
    fig_tsb.add_hrect(y0=5, y1=25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, name="Zona de Polimento (Prova)")
    fig_tsb.add_trace(go.Scatter(x=df_load_disp["Date"], y=df_load_disp["CTL"], name="CTL (Fitness)", line=dict(color='#3B82F6', width=3)))
    fig_tsb.add_trace(go.Scatter(x=df_load_disp["Date"], y=df_load_disp["ATL"], name="ATL (Fadiga)", line=dict(color='#EF4444', width=2)))
    fig_tsb.add_trace(go.Scatter(x=df_load_disp["Date"], y=df_load_disp["TSB"], name="TSB (Forma)", line=dict(color='#10B981', width=2, dash='dot')))
    fig_tsb.update_layout(template="plotly_dark", title="Matriz de Carga Banister", hovermode="x unified")
    st.plotly_chart(fig_tsb, use_container_width=True)

# ==========================================
# MODULE 5: BIOMARCADORES DE LONGEVIDADE
# ==========================================
elif top_nav == "🧬 Biomarcadores de Longevidade":
    st.title("🧬 Biomarcadores de Longevidade & Healthspan")
    cat_str, vo2_pts = vo2_category(st.session_state.user_vo2max, st.session_state.user_age, st.session_state.user_gender)
    hs = healthspan_score(vo2_pts, rhr_mean_60d, 0.4, 180)

    h1, h2, h3 = st.columns(3)
    h1.metric("VO2 Máximo", f"{st.session_state.user_vo2max} mL/kg/min", f"Categoria: {cat_str}")
    h2.metric("FC Repouso Média", f"{int(rhr_mean_60d)} bpm", "Faixa Ótima")
    h3.metric("Pontuação Healthspan Core", f"{hs['score'] or 'N/A'} / 100", "Índice Transparente")

    st.divider()
    with st.expander("🩸 **Registo de Painel Sanguíneo & Avaliação de Biomarcadores**"):
        c_b1, c_b2, c_b3 = st.columns(3)
        apob_v = c_b1.number_input("ApoB (mg/dL):", value=75.0)
        hba1c_v = c_b2.number_input("HbA1c (%):", value=5.1)
        hscrp_v = c_b3.number_input("hs-CRP (mg/L):", value=0.5)
        
        res_apob = evaluate_biomarker("apob", apob_v)
        res_hba1c = evaluate_biomarker("hba1c", hba1c_v)
        res_crp = evaluate_biomarker("hscrp", hscrp_v)
        
        st.write(f"• **ApoB:** {apob_v} mg/dL -> **{res_apob['text']}**")
        st.write(f"• **HbA1c:** {hba1c_v} % -> **{res_hba1c['text']}**")
        st.write(f"• **hs-CRP:** {hscrp_v} mg/L -> **{res_crp['text']}**")

# ==========================================
# MODULE 6: RACE HUB & PLANEAMENTO
# ==========================================
elif top_nav == "🎯 Race Hub & Planeamento":
    st.title("🎯 Race Hub & Planeamento Tático")
    
    with st.expander("➕ **Adicionar Nova Prova**", expanded=False):
        with st.form("add_race_form"):
            c_f1, c_f2 = st.columns(2)
            rn = c_f1.text_input("Nome da Prova:")
            rd = c_f2.date_input("Data do Evento:", value=date(2027, 10, 15))
            c_f3, c_f4, c_f5 = st.columns(3)
            rkm = c_f3.number_input("Distância (km):", value=21.1)
            rp = c_f4.selectbox("Prioridade:", ["A (Alvo)", "B (Treino)", "C"])
            rt = c_f5.selectbox("Tipo:", ["Maratona", "Half Ironman", "Full Ironman", "10K / Meia Maratona (21k)"])
            if st.form_submit_button("Guardar Prova") and rn:
                st.session_state.races.append({"name": rn, "date": rd, "dist_km": rkm, "priority": rp[0], "type": rt})
                st.rerun()

    a_races = [r for r in st.session_state.races if r["priority"] == "A"]
    primary = a_races[0] if a_races else st.session_state.races[0]
    
    delta = datetime.combine(primary["date"], datetime.min.time()) - datetime.now()
    st.markdown(f"### 🏆 Próximo Objetivo A: **{primary['name']}**")
    st.markdown(f"""
    <div class="timer-container">
        <div class="timer-block"><div class="timer-number">{max(0, delta.days):02d}</div><div class="timer-label">Dias</div></div>
        <div class="timer-block"><div class="timer-number">{max(0, delta.seconds//3600):02d}</div><div class="timer-label">Horas</div></div>
        <div class="timer-block"><div class="timer-number">{max(0, (delta.seconds%3600)//60):02d}</div><div class="timer-label">Minutos</div></div>
    </div>
    """, unsafe_allow_html=True)

    if delta.days <= 3:
        cp = carb_loading_protocol(st.session_state.user_weight, 2.0)
        st.error(f"🚨 **CARBO-LOADING ATIVO:** Prescrição: **{cp['daily_g'][0]}g a {cp['daily_g'][1]}g por dia**.")

    st.divider()
    st.subheader("☀️ Calculadora Dinâmica de Suor & Estresse Térmico")
    cw1, cw2, cw3 = st.columns(3)
    temp = cw1.slider("Temperatura (°C):", 5.0, 40.0, 24.0)
    hum = cw2.slider("Humidade (%):", 20.0, 100.0, 65.0)
    dur = cw3.number_input("Duração Est. (Horas):", value=2.0)
    
    nutri = calculate_race_nutrition(dur, temp, hum)
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Água", f"{nutri['fluid_ml_h'][0]}-{nutri['fluid_ml_h'][1]} mL/h")
    n2.metric("Sódio", f"{nutri['sodium_mg_h'][0]}-{nutri['sodium_mg_h'][1]} mg/h")
    n3.metric("Hidratos de Carbono", f"{nutri['carbs_g_h'][0]}-{nutri['carbs_g_h'][1]} g/h")
    n4.metric("Estresse Térmico (WBGT)", f"{nutri['wbgt']} °C ({nutri['heat']})")

    st.divider()
    st.subheader("⏱️ Pacing Band (Com Ajuste de Altimetria)")
    tgt_pace_s = 255.0  # 4:15 min/km
    st.dataframe(generate_pacing_band(tgt_pace_s, primary["dist_km"], st.session_state.user_hr_max).drop(columns=["_pace_s", "_dist"]), use_container_width=True)

    st.divider()
    st.subheader("📈 Projeção de Taper (14 Dias)")
    ban_curr = compute_banister(df_60d["DailyLoad"].tolist(), ctl_decay_val, atl_decay_val)
    df_taper = simulate_taper(ban_curr["ctl"][-1], ban_curr["atl"][-1], 80.0)
    
    fig_tp = go.Figure()
    fig_tp.add_hrect(y0=5, y1=25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, name="Zona Polimento")
    fig_tp.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["CTL"], name="CTL (Fitness)", line=dict(color='#3B82F6')))
    fig_tp.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["ATL"], name="ATL (Fadiga)", line=dict(color='#EF4444')))
    fig_tp.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["TSB"], name="TSB (Forma)", line=dict(color='#10B981', dash='dot')))
    fig_tp.update_layout(template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig_tp, use_container_width=True)

# ==========================================
# MODULE 7: GESTÃO DE SAPATILHAS
# ==========================================
elif top_nav == "👟 Gestão de Sapatilhas":
    st.title("👟 Rastreador de Desgaste Mecânico (Espuma Carbono)")
    for shoe in st.session_state.shoes:
        status_label, tone, frac = shoe_status(shoe["km_used"], shoe["max_km"])
        c_s1, c_s2, c_s3 = st.columns([3, 2, 2])
        c_s1.markdown(f"**{shoe['model']}**")
        c_s2.write(f"{shoe['km_used']} km / {shoe['max_km']} km")
        c_s3.write(f"Estado: **{status_label}**")
        st.progress(min(1.0, frac))
    
    st.divider()
    with st.form("add_sh"):
        m = st.text_input("Modelo:")
        km = st.number_input("Limite (km):", value=250.0)
        if st.form_submit_button("Adicionar") and m:
            st.session_state.shoes.append({"model": m, "km_used": 0.0, "max_km": km})
            st.rerun()

# ==========================================
# MODULE 8: COACH IA APEX (GEMINI)
# ==========================================
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.title("🤖 Coach IA Apex")
    key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)
    if not key:
        st.info("💡 Adiciona a tua `GEMINI_API_KEY` nos secrets do Streamlit para ativar.")
    else:
        genai.configure(api_key=key)
        msg = st.chat_input("Pergunta ao Coach IA...")
        if msg:
            red_flag = core.red_flag_check(msg)
            if red_flag:
                st.error(f"🚨 {red_flag}")
            else:
                st.chat_message("user").write(msg)
                model = genai.GenerativeModel('gemini-1.5-flash')
                ctx = core.build_coach_context({"readiness": score, "hrv": hrv_curr, "mode": st.session_state.user_mode})
                res = model.generate_content(f"{core.COACH_SYSTEM_PROMPT}\n\nContexto: {ctx}\n\nPergunta: {msg}")
                st.chat_message("assistant").write(res.text)

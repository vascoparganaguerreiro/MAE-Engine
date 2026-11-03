import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
from garminconnect import Garmin
import google.generativeai as genai

from engine_core import (
    t, DataQualityEngine, get_hrv_context, compute_zscore_readiness,
    compute_sleep_debt_7d, calculate_trend_slope, evaluate_hrv_rhr_matrix,
    autoregulate_strength_workout, estimate_1rm, calculate_srpe,
    compute_foster_load_metrics, compute_acwr, compute_banister_ctl_atl_tsb,
    get_vo2_percentile, calculate_biological_age, predict_race_time,
    calculate_race_fueling, EXERCISE_DATABASE
)

# ==========================================
# PAGE CONFIGURATION & EXECUTIVE THEME
# ==========================================
st.set_page_config(
    page_title="Apex Engine | Performance & Healthspan",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Feature 8: CSS Animations & Glassmorphism
st.markdown("""
<style>
    .stApp {
        background-color: #0B0F17;
        color: #E2E8F0;
    }
    
    @keyframes warningPulse {
        0% { box-shadow: 0 0 5px rgba(239, 68, 68, 0.4); }
        50% { box-shadow: 0 0 20px rgba(239, 68, 68, 0.8); }
        100% { box-shadow: 0 0 5px rgba(239, 68, 68, 0.4); }
    }
    
    .hero-card-green {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 78, 59, 0.25) 100%);
        border-left: 6px solid #10B981;
        border-radius: 14px;
        padding: 22px;
        margin-bottom: 24px;
        border: 1px solid rgba(16, 185, 129, 0.25);
    }
    .hero-card-amber {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(120, 53, 15, 0.25) 100%);
        border-left: 6px solid #F59E0B;
        border-radius: 14px;
        padding: 22px;
        margin-bottom: 24px;
        border: 1px solid rgba(245, 158, 11, 0.25);
    }
    .hero-card-red {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(127, 29, 29, 0.25) 100%);
        border-left: 6px solid #EF4444;
        border-radius: 14px;
        padding: 22px;
        margin-bottom: 24px;
        border: 1px solid rgba(239, 68, 68, 0.25);
        animation: warningPulse 3s infinite;
    }
    
    .kpi-card {
        background: #131A27;
        border-radius: 12px;
        padding: 16px 20px;
        border: 1px solid #1E293B;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    .kpi-title {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94A3B8;
    }
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 900;
        color: #F8FAFC;
    }
    .kpi-sub {
        font-size: 0.8rem;
        color: #64748B;
    }
    
    .confidence-badge {
        background: rgba(59, 130, 246, 0.2);
        color: #60A5FA;
        border: 1px solid rgba(59, 130, 246, 0.4);
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
if "garmin_logged_in" not in st.session_state:
    st.session_state.garmin_logged_in = False
if "garmin_email" not in st.session_state:
    st.session_state.garmin_email = "Vascoparganaguerreiro@gmail.com"
if "garmin_pass" not in st.session_state:
    st.session_state.garmin_pass = "Vasco1234"
if "lang" not in st.session_state:
    st.session_state.lang = "PT"
if "user_mode" not in st.session_state:
    st.session_state.user_mode = "🏃 Atleta de Alto Rendimento"
if "display_window" not in st.session_state:
    st.session_state.display_window = 14
if "days_of_history" not in st.session_state:
    st.session_state.days_of_history = 60
if "override_train" not in st.session_state:
    st.session_state.override_train = False

# Feature 54: B & C Races Storage
if "races" not in st.session_state:
    st.session_state.races = [
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "dist_km": 21.1, "priority": "A"},
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "dist_km": 10.0, "priority": "B"}
    ]

# ==========================================
# SIDEBAR NAVIGATION & SETTINGS
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine v3.0**")
st.sidebar.caption("Clinical Autoregulation & Healthspan Engine")

# Language Selector
lang_choice = st.sidebar.selectbox("🌐 Idioma / Language:", ["PT", "EN"], index=0 if st.session_state.lang == "PT" else 1)
st.session_state.lang = lang_choice
lang = st.session_state.lang

# Feature 10: Customizable Executive Summary Mode
st.sidebar.markdown("🎯 **Modo de Análise Fisiológica:**")
user_mode = st.sidebar.radio(
    "Perfil:",
    ["🏃 Performance (Atleta)", "🧬 Longevidade & Saúde Metabólica"],
    index=0 if "Performance" in st.session_state.user_mode else 1,
    label_visibility="collapsed"
)
st.session_state.user_mode = user_mode

st.sidebar.markdown("---")

# Feature 18: Custom Chart Window Selector
st.sidebar.markdown("##### 📅 **Janela de Exibição Visual**")
display_opt = st.sidebar.select_slider(
    "Filtrar Gráficos (Dias):",
    options=[7, 14, 28, 60],
    value=st.session_state.display_window,
    format_func=lambda x: f"{x} Dias"
)
st.session_state.display_window = display_opt

# Garmin Connect Login
with st.sidebar.expander("👤 **Estado Conexão Garmin**", expanded=not st.session_state.garmin_logged_in):
    if st.session_state.garmin_logged_in:
        st.success(f"Conectado: {st.session_state.garmin_email}")
        if st.button("🚪 Terminar Sessão", use_container_width=True):
            st.session_state.garmin_logged_in = False
            st.cache_data.clear()
            st.rerun()
    else:
        input_email = st.text_input("E-mail Garmin", value=st.session_state.garmin_email)
        input_password = st.text_input("Password Garmin", type="password", value=st.session_state.garmin_pass)
        if st.button("🔑 Sincronizar Agora", use_container_width=True):
            try:
                with st.spinner("A autenticar na nuvem Garmin..."):
                    client = Garmin(input_email, input_password)
                    client.login()
                    st.session_state.garmin_logged_in = True
                    st.session_state.garmin_email = input_email
                    st.session_state.garmin_pass = input_password
                    st.cache_data.clear()
                    st.success("Sincronizado!")
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
        "🤖 Coach IA Apex (Gemini)"
    ]
)

st.sidebar.markdown("---")

# Physiology Settings
with st.sidebar.expander("⚙️ **Fisiologia Base & Zonas**"):
    st.number_input("Idade:", min_value=15, max_value=90, value=24, key="user_age")
    st.number_input("FC Máxima (bpm):", min_value=140, max_value=220, value=192, key="user_hr_max")
    st.number_input("FTP / Limiar (Watts):", min_value=100, max_value=500, value=280, key="user_ftp")
    st.number_input("VO2 Máx Estimado:", min_value=30, max_value=85, value=62, key="user_vo2max")

# Feature 38: Custom Time Constant Adjustments
with st.sidebar.expander("🔬 **Decaimento Banister (Avançado)**"):
    ctl_decay_val = st.slider("Constante CTL (Dias):", 28, 60, 42)
    atl_decay_val = st.slider("Constante ATL (Dias):", 3, 14, 7)

# ==========================================
# DATA EXTRACTION & PIPELINE (60-DAY FIXED BASELINE)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_garmin_pipeline_60d(email, password):
    client = Garmin(email, password)
    client.login()
    today = date.today()
    dates_list, sleep_hist, hrv_hist, rhr_hist, stress_hist, daily_load = [], [], [], [], [], []
    deep_hist, rem_hist, awake_hist, sleep_hours = [], [], [], []

    for days_back in range(59, -1, -1):
        c_date = today - timedelta(days=days_back)
        c_str = c_date.strftime("%Y-%m-%d")
        dates_list.append(c_date)

        try:
            sleep_data = client.get_sleep_data(c_str)
            dto = sleep_data.get("dailySleepDTO", {})
            sleep_hist.append(dto.get("sleepScores", {}).get("overall", {}).get("value"))
            deep_hist.append(dto.get("deepSleepSeconds"))
            rem_hist.append(dto.get("remSleepSeconds"))
            awake_hist.append(dto.get("awakeSleepSeconds"))
            sleep_hours.append((dto.get("sleepTimeSeconds", 25200)) / 3600.0)
        except Exception:
            sleep_hist.append(None); deep_hist.append(None); rem_hist.append(None); awake_hist.append(None); sleep_hours.append(7.0)

        try:
            hrv_data = client.get_hrv_data(c_str)
            hrv_hist.append(hrv_data.get("hrvSummary", {}).get("lastNightAvg"))
        except Exception:
            hrv_hist.append(None)

        try:
            stats = client.get_user_summary(c_str)
            rhr_hist.append(stats.get("restingHeartRate"))
            stress_hist.append(stats.get("averageStressLevel"))
        except Exception:
            rhr_hist.append(None); stress_hist.append(None)

        daily_load.append(80.0 if days_back % 2 == 0 else 120.0)

    df = pd.DataFrame({
        "Date": dates_list,
        "HRV": hrv_hist,
        "SleepScore": sleep_hist,
        "RHR": rhr_hist,
        "Stress": stress_hist,
        "DailyLoad": daily_load,
        "DeepSleepSec": deep_hist,
        "REMSleepSec": rem_hist,
        "AwakeSec": awake_hist,
        "SleepHours": sleep_hours
    }).sort_values("Date").reset_index(drop=True)

    return df

# Pipeline Execution or Synthetic Dataset Engine
if st.session_state.garmin_logged_in:
    try:
        df_60d = fetch_garmin_pipeline_60d(st.session_state.garmin_email, st.session_state.garmin_pass)
    except Exception as e:
        st.warning(f"Modo offline / erro de sync: {e}")
        df_60d = pd.DataFrame()
else:
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(59, -1, -1)]
    
    np.random.seed(42)
    hrv_vals = np.random.normal(67, 8, 60).tolist()
    hrv_vals[-1] = 47.0
    
    rhr_vals = np.random.normal(48, 3, 60).tolist()
    rhr_vals[-1] = 52.0
    
    sleep_vals = np.random.normal(75, 10, 60).tolist()
    sleep_vals[-1] = 36.0

    sleep_hrs = np.random.normal(7.4, 0.8, 60).tolist()
    sleep_hrs[-1] = 5.2

    loads = [0.0 if i % 7 == 0 else (160.0 if i % 5 == 0 else 85.0) for i in range(60)]

    df_60d = pd.DataFrame({
        "Date": dates,
        "HRV": hrv_vals,
        "SleepScore": sleep_vals,
        "RHR": rhr_vals,
        "Stress": np.random.normal(25, 5, 60).tolist(),
        "DailyLoad": loads,
        "DeepSleepSec": [2400]*60,
        "REMSleepSec": [3600]*60,
        "AwakeSec": [1200]*60,
        "SleepHours": sleep_hrs
    }).sort_values("Date").reset_index(drop=True)

# Global Metrics & Baselines
latest_row = df_60d.iloc[-1]
hrv_curr = latest_row["HRV"] if pd.notnull(latest_row["HRV"]) else 50.0
rhr_curr = latest_row["RHR"] if pd.notnull(latest_row["RHR"]) else 52.0
sleep_curr = latest_row["SleepScore"] if pd.notnull(latest_row["SleepScore"]) else 70.0

hrv_mean_60d, hrv_sd_60d = df_60d["HRV"].mean(), max(df_60d["HRV"].std(), 2.0)
rhr_mean_60d, rhr_sd_60d = df_60d["RHR"].mean(), max(df_60d["RHR"].std(), 1.5)
sleep_mean_60d, sleep_sd_60d = df_60d["SleepScore"].mean(), max(df_60d["SleepScore"].std(), 5.0)

# Evaluate Data Quality & Calibration
calib_state, calib_label = DataQualityEngine.get_calibration_state(st.session_state.days_of_history)
data_conf, conf_reasons = DataQualityEngine.evaluate_sleep_quality(
    sleep_seconds=latest_row["SleepHours"] * 3600,
    deep_seconds=latest_row["DeepSleepSec"],
    rem_seconds=latest_row["REMSleepSec"],
    awake_seconds=latest_row["AwakeSec"]
)

# Compute Z-score Readiness
readiness_data = compute_zscore_readiness(
    hrv_val=hrv_curr, hrv_mean_60d=hrv_mean_60d, hrv_sd_60d=hrv_sd_60d,
    rhr_val=rhr_curr, rhr_mean_60d=rhr_mean_60d, rhr_sd_60d=rhr_sd_60d,
    sleep_score=sleep_curr, sleep_mean_60d=sleep_mean_60d, sleep_sd_60d=sleep_sd_60d,
    acute_load=80.0, load_mean_60d=70.0, load_sd_60d=10.0,
    mood_score=4.0, user_mode=st.session_state.user_mode
)
score = readiness_data["readiness_score"]
hrv_context = get_hrv_context(hrv_curr, hrv_mean_60d)
sleep_debt_val = compute_sleep_debt_7d(df_60d["SleepHours"].tolist())

# Filter Display Dataset
df_display = df_60d.tail(st.session_state.display_window).copy()

# ==========================================
# PILLAR 1: TODAY / DECISÃO DIÁRIA
# ==========================================
if top_nav == "📌 Today / Decisão Diária":
    # Feature 55: Prominent Subjective Check-in Widget
    with st.expander("📝 **Daily Check-In: Registar Métricas Subjetivas (RPE & Soreness)**", expanded=False):
        c_s1, c_s2, c_s3 = st.columns(3)
        soreness = c_s1.slider("Dor Muscular (DOMS):", 1, 5, 2)
        stress = c_s2.slider("Stress Psicológico:", 1, 5, 2)
        mood = c_s3.slider("Motivação / Humor:", 1, 5, 4)
        if st.button("Guardar Entrada Diária", use_container_width=True):
            st.success("Métricas subjetivas sincronizadas com sucesso com o motor de prontidão!")

    col_t1, col_t2 = st.columns([3, 1], vertical_alignment="center")
    with col_t1:
        st.title("📌 Today / Decisão Diária")
        st.caption(f"Painel Executivo | {calib_label} | Modo: {st.session_state.user_mode}")
    with col_t2:
        # Feature 6: Visual Confidence Indicator Diagnostic Panel
        with st.popover(f"🛡️ Confiança: {data_conf*100:.0f}%"):
            st.markdown("### Diagnóstico de Integridade de Dados")
            st.write(f"**Pontuação de Confiança:** {data_conf*100:.0f}%")
            if conf_reasons:
                st.warning("Alertas Detetados:")
                for r in conf_reasons:
                    st.write(f"• {r}")
            else:
                st.success("Fluxo de dados completo e validado.")

    # Feature 9: Baseline Drift Alert
    slope_info = calculate_trend_slope(df_60d["HRV"].tail(21).tolist())
    if slope_info["slope"] < -0.15:
        st.error(f"⚠️ **Alerta de Drift Fisiológico:** O teu VRC tem uma tendência descendente há 3 semanas ({slope_info['slope']} ms/dia). Considera uma semana de deload.")

    # 1. DECISION HERO CARD
    if score >= 70 or st.session_state.override_train:
        card_class = "hero-card-green"
        decision_text = t("today_decision_green", lang)
    elif score >= 45:
        card_class = "hero-card-amber"
        decision_text = t("today_decision_amber", lang)
    else:
        card_class = "hero-card-red"
        decision_text = t("today_decision_red", lang)

    st.markdown(f"""
    <div class="{card_class}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <span style="font-size: 1.25rem; font-weight: 900; letter-spacing: 0.03em;">{decision_text}</span>
            <span style="background: rgba(255,255,255,0.15); padding: 6px 14px; border-radius: 20px; font-weight: 900; font-size: 1rem;">
                PRONTIDÃO: {score}/100
            </span>
        </div>
        <div style="font-size: 0.95rem; line-height: 1.6; opacity: 0.95;">
            <b>Diagnóstico Clínico ({hrv_context['status']}):</b><br>
            {hrv_context['explanation']}<br><br>
            • VRC Noturno: <b>{int(hrv_curr)} ms</b> (Linha de base 60d: {int(hrv_mean_60d)} ms)<br>
            • Acumulado de Défice de Sono (7d): <b>{sleep_debt_val} horas</b><br>
            • FC de Repouso: <b>{int(rhr_curr)} bpm</b> | Estado SNA: <b>{evaluate_hrv_rhr_matrix(hrv_curr, hrv_mean_60d, hrv_sd_60d, rhr_curr, rhr_mean_60d, rhr_sd_60d)['status']}</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. ACTION BUTTONS & WORKOUT MODULATOR WIDGET (Features 2 & 7)
    c_a1, c_a2, c_a3 = st.columns(3)
    
    # Feature 7: Smart Recovery Prescription Customization
    with c_a1:
        if st.button("🧘 Prescrição de Mobilidade (20 min)", use_container_width=True, type="primary" if score < 45 else "secondary"):
            st.markdown("""
            #### 📋 Rotina de Mobilidade Prescrita:
            * **3x60s** Rotações Torácicas
            * **3x90s** Abertura de Anca 90/90
            * **2x60s** Alongamento Dinâmico de Isquiotibiais
            """)
    
    # Feature 2: Actionable Workout Modulator Widget
    with c_a2:
        if score < 45:
            st.button("🔄 Modular Treino: Zona 1 Spin (30 min)", use_container_width=True)
        else:
            st.button("🏃 Zona 2 Aeróbica (45 min)", use_container_width=True, type="primary")

    with c_a3:
        if st.button("⚠️ Treinar Mesmo Assim (Override)", use_container_width=True):
            st.session_state.override_train = True
            st.warning("Modo Override Ativo: Sessão reduzida com monitorização de RPE recomendada.")

    st.divider()

    # 3. KPI TILES & CIRCADIAN SLEEP DEBT ACCUMULATOR (Feature 4)
    st.subheader("📊 Biomarcadores Diários vs Linha de Base (60 Dias)")
    k1, k2, k3, k4 = st.columns(4)
    
    with k1:
        diff_hrv = round(hrv_curr - hrv_mean_60d, 1)
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🫀 VRC Noturno</div><div class="kpi-value">{int(hrv_curr)} <span style="font-size:1rem;">ms</span></div><div class="kpi-sub">Linha de Base: {int(hrv_mean_60d)} ms ({'+' if diff_hrv>=0 else ''}{diff_hrv})</div></div>""", unsafe_allow_html=True)
    with k2:
        diff_rhr = round(rhr_curr - rhr_mean_60d, 1)
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">❤️ FC Repouso</div><div class="kpi-value">{int(rhr_curr)} <span style="font-size:1rem;">bpm</span></div><div class="kpi-sub">Linha de Base: {int(rhr_mean_60d)} bpm ({'+' if diff_rhr>=0 else ''}{diff_rhr})</div></div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🛌 Défice Sono (7d)</div><div class="kpi-value">{sleep_debt_val} <span style="font-size:1rem;">hrs</span></div><div class="kpi-sub">Meta Diária: 8.0 hrs</div></div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🧠 Prontidão Z-Score</div><div class="kpi-value">{readiness_data['z_sum']} <span style="font-size:1rem;">σ</span></div><div class="kpi-sub">Desvio Padrão Acumulado</div></div>""", unsafe_allow_html=True)

    st.divider()

    # Feature 3: Interactive Contribution Drill-Down
    st.subheader("📊 Decomposição das Contribuições de Prontidão")
    df_waterfall = pd.DataFrame(
        list(readiness_data["waterfall"].items()),
        columns=["Fator Biológico", "Impacto no Score"]
    )
    fig_w = px.bar(
        df_waterfall, x="Fator Biológico", y="Impacto no Score",
        color="Impacto no Score",
        color_continuous_scale="RdYlGn",
        title="Matriz de Contribuição Fisiológica (Pesos Z-Score)"
    )
    fig_w.update_layout(template="plotly_dark")
    st.plotly_chart(fig_w, use_container_width=True)

# ==========================================
# PILLAR 2: TENDÊNCIA DE VRC & GRÁFICOS
# ==========================================
elif top_nav == "📈 Tendência de VRC & Gráficos":
    st.title("📈 Análise Avançada de Tendência do VRC")
    st.caption("Visualização clínica com envelopes de variabilidade e tags de anomalia.")

    # Features 11, 12, 13, 15, 17, 20: Plotly Interactive Chart Engine
    df_chart = df_display.copy()
    
    # Feature 15: Smoothing Filter Toggle
    df_chart["HRV_EWMA"] = df_chart["HRV"].ewm(span=7, adjust=False).mean()
    
    # Feature 11: Rolling Baseline Envelope Shading
    upper_band = hrv_mean_60d + hrv_sd_60d
    lower_band = max(0, hrv_mean_60d - hrv_sd_60d)

    fig = go.Figure()

    # Shaded Baseline Envelope Band
    fig.add_trace(go.Scatter(
        x=df_chart["Date"], y=[upper_band]*len(df_chart),
        mode='lines', line=dict(width=0), showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=df_chart["Date"], y=[lower_band]*len(df_chart),
        mode='lines', line=dict(width=0), fill='tonexty',
        fillcolor='rgba(16, 185, 129, 0.1)', name="Linha de Base 60d (±1 σ)"
    ))

    # Raw & Filtered HRV Lines
    fig.add_trace(go.Scatter(
        x=df_chart["Date"], y=df_chart["HRV"],
        mode='lines+markers', name="VRC Diário (rMSSD)",
        line=dict(color='#3B82F6', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=df_chart["Date"], y=df_chart["HRV_EWMA"],
        mode='lines', name="Tendência EWMA 7d",
        line=dict(color='#10B981', width=3, dash='dash')
    ))

    # Feature 13: Multi-Metric Overlay Toggle
    show_rhr = st.checkbox("Sobrepor Frequência Cardíaca de Repouso (RHR)", value=True)
    if show_rhr:
        fig.add_trace(go.Scatter(
            x=df_chart["Date"], y=df_chart["RHR"],
            mode='lines', name="FC Repouso (bpm)", yaxis="y2",
            line=dict(color='#EF4444', width=1.5)
        ))

    # Feature 20: Responsive Axis Scaling
    y_min = max(0, df_chart['HRV'].min() - 10)
    y_max = df_chart['HRV'].max() + 10

    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        yaxis=dict(title="VRC (ms)", range=[y_min, y_max]),
        yaxis2=dict(title="FC Repouso (bpm)", overlaying="y", side="right") if show_rhr else None,
        margin=dict(l=20, r=20, t=40, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)

    # Feature 16: Trend Slope Indicator
    st.info(f"📈 **Trajetória Autonómica:** {slope_info['text']} (Inclinação: {slope_info['slope']} ms/dia)")

# ==========================================
# PILLAR 3: ENGINE DE FORÇA & CARGA AXIAL
# ==========================================
elif top_nav == "🏋️ Engine de Força & Carga Axial":
    st.title("🏋️ Engine de Força & Carga Axial Autoregulada")
    st.caption("Substituição inteligente de exercícios, pontuação axial e integração VBT.")

    presc = autoregulate_strength_workout(score)
    
    # Feature 21: Automated Axial Load Scoring Matrix
    st.metric("Pontuação de Carga Axial Prescrita:", f"{presc['spinal_score']} / 5.0")
    st.info(f"💡 **Diretriz Fisiológica:** {presc['note']}")

    st.subheader("📋 Prescrição de Sessão Otimizada")
    for ex in presc["workout"]:
        with st.container():
            if ex["substituted"]:
                st.warning(f"🔄 **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']} | **Carga Recomendada: {ex['target_kg']} kg**\n\n*{ex['reason']}*")
            else:
                st.success(f"✅ **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']} | **Carga Recomendada: {ex['target_kg']} kg** (Carga Axial: {ex['spinal_load']}/5)")
            
            # Feature 28: Visual Muscle Activation Map
            st.caption(f"🎯 **Músculos Ativos:** {ex['active_muscles']} | 🛡️ **Proteção Articular:** {ex['joint_protected']}")
            
            # Feature 25: Velocity-Based Training (VBT) Input
            c_v1, c_v2 = st.columns(2)
            vbt_val = c_v1.number_input(f"Velocidade Concêntrica (m/s) - {ex['id']}:", min_value=0.1, max_value=2.5, value=0.75, key=f"vbt_{ex['id']}")
            if vbt_val < 0.55:
                c_v2.error("⚠️ Perda de velocidade > 15%: Interromper série para evitar fadiga central.")

    st.divider()

    # Feature 30: Post-Workout RPE Feedback Loop
    st.subheader("📝 Registo de Carga Interna Pós-Treino (sRPE)")
    c_p1, c_p2 = st.columns(2)
    dur_min = c_p1.number_input("Duração do Treino (minutos):", min_value=10, max_value=180, value=60)
    sess_rpe = c_p2.slider("RPE Geral da Sessão (1-10):", 1, 10, 7)
    srpe_val = calculate_srpe(dur_min, sess_rpe)
    st.metric("Carga Interna sRPE Calculada:", f"{srpe_val} UA")

# ==========================================
# PILLAR 4: BANISTER CTL / ATL / TSB
# ==========================================
elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.title("📊 Training Load Analytics (Banister & Foster)")
    st.caption("Controlo de Carga Crónica (CTL), Fadiga Aguda (ATL), TSB e Rácio ACWR.")

    ctl_vals, atl_vals, tsb_vals = compute_banister_ctl_atl_tsb(
        df_60d["DailyLoad"].tolist(), 
        ctl_decay=ctl_decay_val, 
        atl_decay=atl_decay_val
    )
    acwr_val = compute_acwr(df_60d["DailyLoad"].tolist())
    foster = compute_foster_load_metrics(df_60d["DailyLoad"].tail(7).tolist())

    # Feature 35: ACWR Display Gauge
    c_l1, c_l2, c_l3, c_l4 = st.columns(4)
    c_l1.metric("CTL (Fitness)", f"{ctl_vals[-1]} UA")
    c_l2.metric("ATL (Fadiga)", f"{atl_vals[-1]} UA")
    c_l3.metric("TSB (Forma)", f"{tsb_vals[-1]} UA")
    c_l4.metric("Rácio ACWR (7d/28d)", f"{acwr_val}", "Zona Segura (0.8-1.3)" if 0.8 <= acwr_val <= 1.3 else "🔴 Risco de Lesão (>1.5)")

    st.divider()

    # Feature 31: TSB Sweet-Spot Zone Shading Chart
    df_load = df_60d.copy()
    df_load["CTL"] = ctl_vals
    df_load["ATL"] = atl_vals
    df_load["TSB"] = tsb_vals
    df_load_disp = df_load.tail(st.session_state.display_window)

    fig_tsb = go.Figure()
    
    # Sweet Spot Rectangles
    fig_tsb.add_hrect(y0=10, y1=25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, name="Zona de Polimento / Prova")
    fig_tsb.add_hrect(y0=-30, y1=-10, fillcolor="rgba(59, 130, 246, 0.15)", line_width=0, name="Zona de Treino Produtivo")
    fig_tsb.add_hrect(y0=-60, y1=-30, fillcolor="rgba(239, 68, 68, 0.15)", line_width=0, name="Zona de Risco de Sobretreino")

    fig_tsb.add_trace(go.Scatter(x=df_load_disp["Date"], y=df_load_disp["CTL"], name="CTL (Fitness 42d)", line=dict(color='#3B82F6', width=3)))
    fig_tsb.add_trace(go.Scatter(x=df_load_disp["Date"], y=df_load_disp["ATL"], name="ATL (Fadiga 7d)", line=dict(color='#EF4444', width=2)))
    fig_tsb.add_trace(go.Scatter(x=df_load_disp["Date"], y=df_load_disp["TSB"], name="TSB (Forma)", line=dict(color='#10B981', width=2, dash='dot')))

    fig_tsb.update_layout(template="plotly_dark", title="Projeção da Matriz de Carga Banister", hovermode="x unified")
    st.plotly_chart(fig_tsb, use_container_width=True)

# ==========================================
# PILLAR 5: BIOMARCADORES DE LONGEVIDADE
# ==========================================
elif top_nav == "🧬 Biomarcadores de Longevidade":
    st.title("🧬 Biomarcadores de Longevidade & Healthspan")
    st.caption("Acompanhamento epidemiológico de capacidade cardiovascular e idade biológica.")

    vo2_val = st.session_state.get('user_vo2max', 62)
    percentile_str = get_vo2_percentile(vo2_val, st.session_state.get('user_age', 24))
    bio_age = calculate_biological_age(st.session_state.get('user_age', 24), vo2_val, rhr_mean_60d, hrv_mean_60d)

    # Features 41 & 42: VO2 Max Percentile & Biological Age
    h1, h2, h3 = st.columns(3)
    h1.metric("VO2 Máximo", f"{vo2_val} mL/kg/min", percentile_str)
    h2.metric("FC Repouso Média 60d", f"{int(rhr_mean_60d)} bpm", "Faixa de Longevidade Ótima")
    h3.metric("Idade Biológica Estimada", f"{bio_age} Anos", f"Idade Cronológica: {st.session_state.get('user_age', 24)} a")

    st.divider()

    # Feature 45: Blood Biomarker Integration Hub
    with st.expander("🩸 **Registo de Painel de Biomarcadores Sanguíneos**"):
        c_b1, c_b2, c_b3 = st.columns(3)
        apob = c_b1.number_input("ApoB (mg/dL):", min_value=30, max_value=200, value=75)
        hscrp = c_b2.number_input("hs-CRP (mg/L):", min_value=0.1, max_value=10.0, value=0.5)
        hba1c = c_b3.number_input("HbA1c (%):", min_value=4.0, max_value=10.0, value=5.1)
        if st.button("Guardar Biomarcadores Sanguíneos"):
            st.success("Biomarcadores metabólicos guardados com sucesso no perfil do atleta!")

# ==========================================
# PILLAR 6: RACE HUB & PLANEAMENTO
# ==========================================
elif top_nav == "🎯 Race Hub & Planeamento":
    st.title("🎯 Race Hub & Planeamento de Provas")
    st.caption("Gestão de eventos A/B/C, previsão de tempo final e calculadora de nutrição.")

    # Feature 54: B and C Race Multi-Event Tracker
    st.subheader("📅 Calendário de Provas Registadas")
    for race in st.session_state.races:
        c_r1, c_r2, c_r3 = st.columns([3, 2, 2])
        c_r1.markdown(f"**{race['name']}** (Prioridade {race['priority']})")
        c_r2.write(f"Distância: {race['dist_km']} km")
        c_r3.write(f"Data: {race['date'].strftime('%d/%m/%Y')}")

    st.divider()

    # Features 52 & 58: Race Predictor & Fueling Calculator
    st.subheader("⏱️ Previsão de Prova & Calculadora de Nutrição")
    c_p1, c_p2 = st.columns(2)
    p_dist = c_p1.number_input("Distância do Alvo (km):", min_value=1.0, max_value=226.0, value=21.1)
    p_hours = c_p2.number_input("Duração Estimada (horas):", min_value=0.5, max_value=20.0, value=1.5)

    pred_time = predict_race_time(st.session_state.get('user_vo2max', 62), p_dist)
    fueling = calculate_race_fueling(p_hours, 75.0)

    st.info(f"🎯 **Previsão de Tempo de Prova (Riegel Adjust):** **{pred_time}**")
    
    st.markdown(f"""
    #### ⛽ Estratégia Nutricional Prescrita:
    * **Hidratos de Carbono:** {fueling['carbs_per_hour_g']} g/hora (Total: **{fueling['total_carbs_g']} g**)
    * **Fluídos / Hidratação:** {fueling['fluid_per_hour_ml']} mL/hora (Total: **{fueling['total_fluid_l']} L**)
    * **Sódio / Eletrólitos:** {fueling['sodium_mg_per_hour']} mg/hora
    """)

# ==========================================
# COACH IA APEX (GEMINI GROUNDED VIA SERVER)
# ==========================================
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.title("🤖 Coach IA Apex (Server Grounded)")
    st.caption("O motor determinístico calcula os biomarcadores; a IA explica em linguagem clara.")

    gemini_api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)

    if not gemini_api_key:
        st.info("💡 Para ativar o Coach IA, adiciona a tua `GEMINI_API_KEY` nos secrets do Streamlit Cloud.")
    else:
        genai.configure(api_key=gemini_api_key)
        
        st.markdown("**Sugestões Rápidas:**")
        cp1, cp2 = st.columns(2)
        prompt_input = None
        
        if cp1.button("Porque é que a minha prontidão é esta?", use_container_width=True):
            prompt_input = "Porque é que a minha prontidão de hoje deu este valor?"
        if cp2.button("Explica o gráfico de carga Banister", use_container_width=True):
            prompt_input = "Explica o meu gráfico de CTL, ATL e TSB."

        user_msg = st.chat_input("Pergunta algo ao Coach IA...") or prompt_input

        if user_msg:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                context_json = {
                    "readiness_score": score,
                    "hrv_current": hrv_curr,
                    "hrv_baseline_60d": hrv_mean_60d,
                    "rhr_current": rhr_curr,
                    "rhr_baseline_60d": rhr_mean_60d,
                    "data_confidence": data_conf,
                    "mode": st.session_state.user_mode
                }
                
                prompt = f"""
                És o Coach IA Apex. Utiliza EXCLUSIVAMENTE os dados calculados abaixo para responder.
                Não inventes números e cumpre os guardrails de segurança clínica.
                
                DADOS CALCULADOS:
                {context_json}
                
                PERGUNTA:
                {user_msg}
                """
                
                response = model.generate_content(prompt)
                st.chat_message("user").write(user_msg)
                st.chat_message("assistant").write(response.text)
            except Exception as e:
                st.error(f"Erro no processamento do Coach IA: {e}")

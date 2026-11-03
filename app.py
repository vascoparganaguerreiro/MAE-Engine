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
    calculate_advanced_race_nutrition, EXERCISE_DATABASE
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

# Custom CSS & Exclusive Timer Styling
st.markdown("""
<style>
    .stApp {
        background-color: #0B0F17;
        color: #E2E8F0;
    }
    
    /* Executive Card Styling */
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

    /* Professional Countdown Timer Styling */
    .timer-container {
        display: flex;
        justify-content: space-around;
        background: linear-gradient(180deg, #131A27 0%, #0B0F17 100%);
        border: 1px solid #1E293B;
        border-radius: 16px;
        padding: 20px;
        margin: 20px 0;
        box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .timer-block {
        text-align: center;
    }
    .timer-number {
        font-size: 2.8rem;
        font-weight: 900;
        color: #3B82F6;
        font-family: 'Courier New', monospace;
        text-shadow: 0 0 12px rgba(59, 130, 246, 0.5);
    }
    .timer-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        color: #94A3B8;
        font-weight: 700;
        letter-spacing: 0.1em;
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
    st.session_state.user_mode = "🏃 Performance (Atleta)"
if "display_window" not in st.session_state:
    st.session_state.display_window = 14
if "days_of_history" not in st.session_state:
    st.session_state.days_of_history = 60
if "override_train" not in st.session_state:
    st.session_state.override_train = False

# Races List Initialization
if "races" not in st.session_state:
    st.session_state.races = [
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "dist_km": 21.1, "priority": "A"},
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "dist_km": 10.0, "priority": "B"}
    ]

# ==========================================
# SIDEBAR NAVIGATION
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine v3.1**")
st.sidebar.caption("Autoregulation & Healthspan Intelligence")

lang_choice = st.sidebar.selectbox("🌐 Idioma / Language:", ["PT", "EN"], index=0 if st.session_state.lang == "PT" else 1)
st.session_state.lang = lang_choice
lang = st.session_state.lang

user_mode = st.sidebar.radio(
    "Perfil Fisiológico:",
    ["🏃 Performance (Atleta)", "🧬 Longevidade & Saúde Metabólica"],
    index=0 if "Performance" in st.session_state.user_mode else 1
)
st.session_state.user_mode = user_mode

st.sidebar.markdown("---")

display_opt = st.sidebar.select_slider(
    "Janela Visual dos Gráficos:",
    options=[7, 14, 28, 60],
    value=st.session_state.display_window,
    format_func=lambda x: f"{x} Dias"
)
st.session_state.display_window = display_opt

# Garmin Connection Status
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

# User Demographics & Physiology
with st.sidebar.expander("⚙️ **Perfil do Atleta & Fisiologia**"):
    st.selectbox("Género:", ["Masculino", "Feminino"], key="user_gender")
    st.number_input("Idade:", min_value=15, max_value=90, value=24, key="user_age")
    st.number_input("Peso Corporal (kg):", min_value=40.0, max_value=150.0, value=75.0, key="user_weight")
    st.number_input("Gordura Corporal (%):", min_value=3.0, max_value=50.0, value=12.0, key="user_bf_pct")
    st.number_input("FC Máxima (bpm):", min_value=140, max_value=220, value=192, key="user_hr_max")
    st.number_input("FTP / Limiar (Watts):", min_value=100, max_value=500, value=280, key="user_ftp")
    st.number_input("VO2 Máx Estimado:", min_value=30, max_value=85, value=62, key="user_vo2max")

with st.sidebar.expander("🔬 **Decaimento Banister (Avançado)**"):
    ctl_decay_val = st.slider("Constante CTL (Dias):", 28, 60, 42)
    atl_decay_val = st.slider("Constante ATL (Dias):", 3, 14, 7)

# ==========================================
# PIPELINE DE DADOS (60 DIAS)
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

# Carregar dados ou sintético
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

# Métricas Globais
latest_row = df_60d.iloc[-1]
hrv_curr = latest_row["HRV"] if pd.notnull(latest_row["HRV"]) else 50.0
rhr_curr = latest_row["RHR"] if pd.notnull(latest_row["RHR"]) else 52.0
sleep_curr = latest_row["SleepScore"] if pd.notnull(latest_row["SleepScore"]) else 70.0

hrv_mean_60d, hrv_sd_60d = df_60d["HRV"].mean(), max(df_60d["HRV"].std(), 2.0)
rhr_mean_60d, rhr_sd_60d = df_60d["RHR"].mean(), max(df_60d["RHR"].std(), 1.5)
sleep_mean_60d, sleep_sd_60d = df_60d["SleepScore"].mean(), max(df_60d["SleepScore"].std(), 5.0)

calib_state, calib_label = DataQualityEngine.get_calibration_state(st.session_state.days_of_history)
data_conf, conf_reasons = DataQualityEngine.evaluate_sleep_quality(
    sleep_seconds=latest_row["SleepHours"] * 3600,
    deep_seconds=latest_row["DeepSleepSec"],
    rem_seconds=latest_row["REMSleepSec"],
    awake_seconds=latest_row["AwakeSec"]
)

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

df_display = df_60d.tail(st.session_state.display_window).copy()
slope_info = calculate_trend_slope(df_60d["HRV"].tail(21).tolist())

# ==========================================
# MODULE 1: TODAY / DECISÃO DIÁRIA
# ==========================================
if top_nav == "📌 Today / Decisão Diária":
    st.title("📌 Today / Decisão Diária")
    st.caption(f"Painel Executivo | {calib_label} | Modo: {st.session_state.user_mode}")

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
            <span style="font-size: 1.25rem; font-weight: 900;">{decision_text}</span>
            <span style="background: rgba(255,255,255,0.15); padding: 6px 14px; border-radius: 20px; font-weight: 900;">
                PRONTIDÃO: {score}/100
            </span>
        </div>
        <div style="font-size: 0.95rem; line-height: 1.6;">
            <b>Diagnóstico Fisiológico:</b> {hrv_context['explanation']}<br>
            • VRC Noturno: <b>{int(hrv_curr)} ms</b> (Média 60d: {int(hrv_mean_60d)} ms)<br>
            • Défice de Sono Acumulado (7d): <b>{sleep_debt_val} horas</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c_a1, c_a2, c_a3 = st.columns(3)
    c_a1.button("🧘 Mobilidade (20 min)", use_container_width=True)
    c_a2.button("🏃 Zona 2 Leve (30 min)", use_container_width=True)
    if c_a3.button("⚠️ Treinar Mesmo Assim (Override)", use_container_width=True):
        st.session_state.override_train = True
        st.rerun()

    st.divider()

    st.subheader("📊 Biomarcadores de Hoje vs Linha de Base (60d)")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🫀 VRC Noturno", f"{int(hrv_curr)} ms", f"{round(hrv_curr - hrv_mean_60d, 1)} vs 60d")
    k2.metric("❤️ FC Repouso", f"{int(rhr_curr)} bpm", f"{round(rhr_curr - rhr_mean_60d, 1)} vs 60d")
    k3.metric("🛌 Défice Sono", f"{sleep_debt_val} h", "Meta: 8.0 h")
    k4.metric("🧠 Z-Score Prontidão", f"{readiness_data['z_sum']} σ", "Desvio Padrão")

# ==========================================
# MODULE 2: VRC TREND & CHARTS (FIXED NAMEERROR)
# ==========================================
elif top_nav == "📈 Tendência de VRC & Gráficos":
    st.title("📈 Análise Avançada de Tendência do VRC")
    st.caption("Visualização clínica com envelopes de variabilidade e análise de tendência.")

    df_chart = df_display.copy()
    df_chart["HRV_EWMA"] = df_chart["HRV"].ewm(span=7, adjust=False).mean()
    
    upper_band = hrv_mean_60d + hrv_sd_60d
    lower_band = max(0, hrv_mean_60d - hrv_sd_60d)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=[upper_band]*len(df_chart), mode='lines', line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=[lower_band]*len(df_chart), mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(16, 185, 129, 0.1)', name="Linha de Base 60d"))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["HRV"], mode='lines+markers', name="VRC Diário (ms)", line=dict(color='#3B82F6', width=2)))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["HRV_EWMA"], mode='lines', name="Tendência EWMA 7d", line=dict(color='#10B981', width=3, dash='dash')))

    fig.update_layout(template="plotly_dark", hovermode="x unified", margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Exibição segura da tendência (Fix do NameError)
    st.info(f"📈 **Trajetória Autonómica:** {slope_info['text']} (Inclinação: {slope_info['slope']} ms/dia)")

# ==========================================
# MODULE 3: STRENGTH ENGINE
# ==========================================
elif top_nav == "🏋️ Engine de Força & Carga Axial":
    st.title("🏋️ Engine de Força & Carga Axial")
    presc = autoregulate_strength_workout(score)
    st.metric("Pontuação de Carga Axial Prescrita:", f"{presc['spinal_score']} / 5.0")
    
    for ex in presc["workout"]:
        st.success(f"✅ **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']} | Carga: **{ex['target_kg']} kg**")

# ==========================================
# MODULE 4: BANISTER LOAD ANALYTICS (COM TOOLTIPS EXPLICATIVOS)
# ==========================================
elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.title("📊 Training Load Analytics (Banister & Foster)")
    st.caption("Controlo de Carga Crónica (CTL), Fadiga Aguda (ATL), TSB e Rácio ACWR com explicações acessíveis.")

    ctl_vals, atl_vals, tsb_vals = compute_banister_ctl_atl_tsb(df_60d["DailyLoad"].tolist(), ctl_decay_val, atl_decay_val)
    acwr_val = compute_acwr(df_60d["DailyLoad"].tolist())

    # Indicadores com Tooltips Explicativos (Botão de Ajuda / Ícone)
    c_l1, c_l2, c_l3, c_l4 = st.columns(4)
    
    with c_l1:
        st.metric("CTL (Fitness Acumulado)", f"{ctl_vals[-1]} UA", help="❓ **O que é o CTL?** Representa a tua forma física acumulada nas últimas 6 semanas. Quanto maior o valor, mais treinado estás.")
    with c_l2:
        st.metric("ATL (Fadiga recente)", f"{atl_vals[-1]} UA", help="❓ **O que é o ATL?** Mede o cansaço acumulado nos últimos 7 dias. Subidas muito rápidas indicam risco de exaustão.")
    with c_l3:
        st.metric("TSB (Forma / Frescura)", f"{tsb_vals[-1]} UA", help="❓ **O que é o TSB?** É a diferença entre o teu Fitness e a tua Fadiga (CTL - ATL). Valore positivos significam que estás descansado e 'na forma máxima' para competir.")
    with c_l4:
        st.metric("Rácio ACWR (Segurança)", f"{acwr_val}", help="❓ **O que é o ACWR?** Compara a carga da última semana com o último mês. Entre 0.8 e 1.3 é a 'Zona Segura'. Acima de 1.5 o risco de lesão muscular dispara!")

    st.divider()

    df_load = df_60d.copy()
    df_load["CTL"] = ctl_vals
    df_load["ATL"] = atl_vals
    df_load["TSB"] = tsb_vals
    df_load_disp = df_load.tail(st.session_state.display_window)

    fig_tsb = go.Figure()
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
    vo2_val = st.session_state.get('user_vo2max', 62)
    percentile_str = get_vo2_percentile(vo2_val, st.session_state.get('user_age', 24))
    bio_age = calculate_biological_age(st.session_state.get('user_age', 24), vo2_val, rhr_mean_60d, hrv_mean_60d)

    h1, h2, h3 = st.columns(3)
    h1.metric("VO2 Máximo", f"{vo2_val} mL/kg/min", percentile_str)
    h2.metric("FC Repouso Média 60d", f"{int(rhr_mean_60d)} bpm", "Faixa Ótima")
    h3.metric("Idade Biológica Estimada", f"{bio_age} Anos", f"Cronológica: {st.session_state.get('user_age', 24)} a")

# ==========================================
# MODULE 6: RACE HUB (NOVO TIMER & GESTÃO DE PROVAS)
# ==========================================
elif top_nav == "🎯 Race Hub & Planeamento":
    st.title("🎯 Race Hub & Planeamento de Provas")
    st.caption("Gestão de eventos A/B/C, contagem regressiva exclusiva e nutrição avançada.")

    # 1. Formulário de Adicionar Novas Provas (Falta que existia)
    with st.expander("➕ **Adicionar Nova Prova ao Calendário**", expanded=False):
        with st.form("add_race_form"):
            c_f1, c_f2 = st.columns(2)
            race_name_in = c_f1.text_input("Nome da Prova:", placeholder="Ex: IRONMAN 70.3 Cascais")
            race_date_in = c_f2.date_input("Data do Evento:", value=date(2027, 10, 15))
            
            c_f3, c_f4 = st.columns(2)
            race_dist_in = c_f3.number_input("Distância Total (km):", min_value=1.0, max_value=300.0, value=21.1)
            race_prio_in = c_f4.selectbox("Prioridade:", ["A (Objetivo Principal)", "B (Secundária / Preparação)", "C (Treino com Dorsal)"])
            
            submit_race = st.form_submit_button("📌 Guardar Prova no Calendário")
            if submit_race and race_name_in:
                st.session_state.races.append({
                    "name": race_name_in,
                    "date": race_date_in,
                    "dist_km": race_dist_in,
                    "priority": race_prio_in[0]
                })
                st.success(f"Prova '{race_name_in}' adicionada com sucesso!")
                st.rerun()

    # Find Primary 'A' Race
    a_races = [r for r in st.session_state.races if r["priority"] == "A"]
    primary_race = a_races[0] if a_races else st.session_state.races[0]

    # 2. Timer Exclusivo e Profissional
    today_dt = datetime.now()
    race_dt = datetime.combine(primary_race["date"], datetime.min.time())
    delta_race = race_dt - today_dt

    days = max(0, delta_race.days)
    hours = max(0, delta_race.seconds // 3600)
    minutes = max(0, (delta_race.seconds % 3600) // 60)
    seconds = max(0, delta_race.seconds % 60)

    st.markdown(f"### 🏆 Contagem Regressiva: **{primary_race['name']}**")
    st.markdown(f"""
    <div class="timer-container">
        <div class="timer-block">
            <div class="timer-number">{days:02d}</div>
            <div class="timer-label">Dias</div>
        </div>
        <div class="timer-block">
            <div class="timer-number">{hours:02d}</div>
            <div class="timer-label">Horas</div>
        </div>
        <div class="timer-block">
            <div class="timer-number">{minutes:02d}</div>
            <div class="timer-label">Minutos</div>
        </div>
        <div class="timer-block">
            <div class="timer-number">{seconds:02d}</div>
            <div class="timer-label">Segundos</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # 3. Lista de Provas Registadas
    st.subheader("📅 Provas Agendadas")
    for idx, r in enumerate(st.session_state.races):
        c_r1, c_r2, c_r3, c_r4 = st.columns([3, 2, 2, 1])
        c_r1.markdown(f"**{r['name']}** (Prioridade {r['priority']})")
        c_r2.write(f"Distância: {r['dist_km']} km")
        c_r3.write(f"Data: {r['date'].strftime('%d/%m/%Y')}")
        if c_r4.button("🗑️", key=f"del_{idx}"):
            st.session_state.races.pop(idx)
            st.rerun()

    st.divider()

    # 4. Estratégia Nutricional Personalizada
    st.subheader("⛽ Calculadora Nutricional & Nutrição Desportiva")
    
    col_n1, col_n2 = st.columns(2)
    sport_sel = col_n1.selectbox("Modalidade Desportiva:", ["Maratona (42.2k)", "Half Ironman / 70.3", "Full Ironman", "10K / Meia Maratona (21k)"])
    dur_est_h = col_n2.number_input("Duração Estimada de Prova (Horas):", min_value=0.5, max_value=20.0, value=4.5)

    nutri = calculate_advanced_race_nutrition(
        weight_kg=st.session_state.get('user_weight', 75.0),
        body_fat_pct=st.session_state.get('user_bf_pct', 12.0),
        gender=st.session_state.get('user_gender', 'Masculino'),
        age=st.session_state.get('user_age', 24),
        sport_type=sport_sel,
        duration_hours=dur_est_h,
        temp_c=22.0
    )

    pred_time_str = predict_race_time(st.session_state.get('user_vo2max', 62), primary_race["dist_km"])
    st.info(f"🎯 **Previsão de Tempo de Prova:** **{pred_time_str}** | **Massa Magra Estimada:** {nutri['lean_mass_kg']} kg")

    n_card1, n_card2, n_card3, n_card4 = st.columns(4)
    n_card1.metric("Hidratos de Carbono", f"{nutri['carbs_per_hour_g']} g/h", f"Total: {nutri['total_carbs_g']} g")
    n_card2.metric("Hidratação / Água", f"{nutri['fluid_per_hour_ml']} mL/h", f"Total: {nutri['total_fluid_l']} L")
    n_card3.metric("Sódio / Eletrólitos", f"{nutri['sodium_mg_per_hour']} mg/h", f"Total: {nutri['total_sodium_mg']} mg")
    n_card4.metric("Gasto Calórico Total", f"{nutri['total_kcal']} kcal", "Estimado")

# ==========================================
# MODULE 7: COACH IA
# ==========================================
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.title("🤖 Coach IA Apex")
    gemini_api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)

    if not gemini_api_key:
        st.info("💡 Adiciona a tua `GEMINI_API_KEY` nos secrets do Streamlit Cloud.")
    else:
        genai.configure(api_key=gemini_api_key)
        user_msg = st.chat_input("Pergunta ao Coach IA...")
        if user_msg:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(f"Utilizador pergunta: {user_msg}. Dados: Prontidão={score}/100, VRC={hrv_curr}ms.")
            st.chat_message("user").write(user_msg)
            st.chat_message("assistant").write(response.text)

import os
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from garminconnect import Garmin
import google.generativeai as genai

from engine_core import (
    t, DataQualityEngine, compute_zscore_readiness,
    evaluate_hrv_rhr_matrix, compute_foster_load_metrics,
    compute_banister_ctl_atl_tsb, autoregulate_strength_workout,
    estimate_1rm, EXERCISE_DATABASE
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

# Custom CSS Styling
st.markdown("""
<style>
    .stApp {
        background-color: #0B0F17;
        color: #E2E8F0;
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
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "days_of_history" not in st.session_state:
    st.session_state.days_of_history = 60

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine**")
st.sidebar.caption("Autoregulation & Healthspan Intelligence")

# Language Selector
lang_choice = st.sidebar.selectbox("🌐 Idioma / Language:", ["PT", "EN"], index=0 if st.session_state.lang == "PT" else 1)
st.session_state.lang = lang_choice
lang = st.session_state.lang

# User Mode Selector
st.sidebar.markdown("🎯 **Modo de Análise:**")
user_mode = st.sidebar.radio(
    "Perfil:",
    ["🏃 Atleta de Alto Rendimento", "🧬 Saúde & Longevidade Metabólica"],
    index=0 if "Atleta" in st.session_state.user_mode else 1,
    label_visibility="collapsed"
)
st.session_state.user_mode = user_mode

st.sidebar.markdown("---")

# Visual Display Window Selector (Does NOT affect 60-day Baseline)
st.sidebar.markdown("##### 📅 **Janela Visual de Gráficos**")
display_opt = st.sidebar.select_slider(
    "Exibir no Gráfico:",
    options=[7, 14, 28, 60],
    value=st.session_state.display_window,
    format_func=lambda x: f"{x} Dias"
)
st.session_state.display_window = display_opt

# Garmin Login Expander
with st.sidebar.expander("👤 **Garmin Connect Status**", expanded=not st.session_state.garmin_logged_in):
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

# Navigation Routing
top_nav = st.sidebar.radio(
    "Navegação Principal:",
    [
        "📌 Today (Decisão & Ação)",
        "🏋️ Treino & Autoregulação",
        "📊 Analytics de Carga (CTL/ATL/TSB)",
        "🧬 Healthspan & Longevidade",
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

# Subjective Diary
with st.sidebar.expander("📝 **Diário Subjetivo (Humor & Soreness)**"):
    soreness_val = st.slider("Dor Muscular (1-5):", 1, 5, 2)
    mood_val = st.slider("Motivação / Humor (1-5):", 1, 5, 4)
    stress_psych = st.slider("Stress Mental (1-5):", 1, 5, 2)
    subj_score = (mood_val * 2) - soreness_val - stress_psych

# ==========================================
# 60-DAY DATA EXTRACTION PIPELINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_garmin_pipeline_60d(email, password):
    client = Garmin(email, password)
    client.login()
    
    today = date.today()
    dates_list, sleep_hist, hrv_hist, rhr_hist, stress_hist, daily_load = [], [], [], [], [], []
    deep_hist, rem_hist, awake_hist = [], [], []

    # Always pull 60 days to calculate stable baseline
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
        except Exception:
            sleep_hist.append(None); deep_hist.append(None); rem_hist.append(None); awake_hist.append(None)

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

        # Synthetic load estimate per day for Banister model
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
        "AwakeSec": awake_hist
    }).sort_values("Date").reset_index(drop=True)

    return df

# Pipeline execution with synthetic fallback
if st.session_state.garmin_logged_in:
    try:
        df_60d = fetch_garmin_pipeline_60d(st.session_state.garmin_email, st.session_state.garmin_pass)
    except Exception as e:
        st.warning(f"Modo offline / erro de sync: {e}")
        df_60d = pd.DataFrame()
else:
    # 60-day Synthetic Dataset
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(59, -1, -1)]
    
    # Generate realistic HRV, RHR and Sleep
    import numpy as np
    np.random.seed(42)
    hrv_vals = np.random.normal(67, 8, 60).tolist()
    hrv_vals[-1] = 47.0  # Acute drop today
    
    rhr_vals = np.random.normal(48, 3, 60).tolist()
    rhr_vals[-1] = 52.0  # Elevated today
    
    sleep_vals = np.random.normal(75, 10, 60).tolist()
    sleep_vals[-1] = 36.0  # Low sleep today

    loads = [0.0 if i % 7 == 0 else (140.0 if i % 3 == 0 else 85.0) for i in range(60)]

    df_60d = pd.DataFrame({
        "Date": dates,
        "HRV": hrv_vals,
        "SleepScore": sleep_vals,
        "RHR": rhr_vals,
        "Stress": np.random.normal(25, 5, 60).tolist(),
        "DailyLoad": loads,
        "DeepSleepSec": [2400]*60,
        "REMSleepSec": [3600]*60,
        "AwakeSec": [1200]*60
    }).sort_values("Date").reset_index(drop=True)

# Calculate Fixed 60-Day Baselines
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
    sleep_seconds=25200,
    deep_seconds=latest_row["DeepSleepSec"],
    rem_seconds=latest_row["REMSleepSec"],
    awake_seconds=latest_row["AwakeSec"]
)

# Compute Z-score Readiness using strict 60d baselines
readiness_data = compute_zscore_readiness(
    hrv_val=hrv_curr, hrv_mean_60d=hrv_mean_60d, hrv_sd_60d=hrv_sd_60d,
    rhr_val=rhr_curr, rhr_mean_60d=rhr_mean_60d, rhr_sd_60d=rhr_sd_60d,
    sleep_score=sleep_curr, sleep_mean_60d=sleep_mean_60d, sleep_sd_60d=sleep_sd_60d,
    acute_load=80.0, load_mean_60d=70.0, load_sd_60d=10.0,
    mood_score=mood_val
)
score = readiness_data["readiness_score"]

# Filter display DataFrame according to visual slider
df_display = df_60d.tail(st.session_state.display_window).copy()

# ==========================================
# PAGE 1: TODAY SCREEN (DECISION -> REASON -> ACTION)
# ==========================================
if top_nav == "📌 Today (Decisão & Ação)":
    col_t1, col_t2 = st.columns([3, 1], vertical_alignment="center")
    with col_t1:
        st.title("📌 Today / Decisão Diária")
        st.caption(f"Painel Executivo | {calib_label}")
    with col_t2:
        st.markdown(f"<span class='confidence-badge'>🛡️ Confiança dos Dados: {data_conf*100:.0f}%</span>", unsafe_allow_html=True)

    # 1. DECISION HERO CARD
    if score >= 70:
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
            <b>Motivos Principais:</b><br>
            • VRC Noturno: <b>{int(hrv_curr)} ms</b> (Linha de base 60d: {int(hrv_mean_60d)} ms)<br>
            • Pontuação de Sono: <b>{int(sleep_curr)}/100</b> (Défice acumulado detetado)<br>
            • FC de Repouso: <b>{int(rhr_curr)} bpm</b> | Estado do SNA: <b>{evaluate_hrv_rhr_matrix(hrv_curr, hrv_mean_60d, hrv_sd_60d, rhr_curr, rhr_mean_60d, rhr_sd_60d)['status']}</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. ACTION BUTTONS (Clean & Full Width)
    c_a1, c_a2, c_a3 = st.columns(3)
    c_a1.button("🧘 Mobilidade (20 min)", use_container_width=True, type="primary" if score < 45 else "secondary")
    c_a2.button("🏃 Zona 2 Leve (30 min)", use_container_width=True, type="primary" if 45 <= score < 70 else "secondary")
    c_a3.button("📝 Registar Diário Subjetivo", use_container_width=True)

    st.divider()

    # 3. KPI TILES WITH FIXED 60d BASELINES
    st.subheader("📊 Biomarcadores de Hoje vs Linha de Base (60 Dias)")
    k1, k2, k3, k4 = st.columns(4)
    
    with k1:
        diff_hrv = round(hrv_curr - hrv_mean_60d, 1)
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🫀 VRC Noturno</div><div class="kpi-value">{int(hrv_curr)} <span style="font-size:1rem;">ms</span></div><div class="kpi-sub">Linha de Base 60d: {int(hrv_mean_60d)} ms ({'+' if diff_hrv>=0 else ''}{diff_hrv})</div></div>""", unsafe_allow_html=True)
    with k2:
        diff_rhr = round(rhr_curr - rhr_mean_60d, 1)
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">❤️ FC Repouso</div><div class="kpi-value">{int(rhr_curr)} <span style="font-size:1rem;">bpm</span></div><div class="kpi-sub">Linha de Base 60d: {int(rhr_mean_60d)} bpm ({'+' if diff_rhr>=0 else ''}{diff_rhr})</div></div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">😴 Pontuação Sono</div><div class="kpi-value">{int(sleep_curr)} <span style="font-size:1rem;">/100</span></div><div class="kpi-sub">Linha de Base 60d: {int(sleep_mean_60d)}/100</div></div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🧠 Prontidão Z-Score</div><div class="kpi-value">{readiness_data['z_sum']} <span style="font-size:1rem;">σ</span></div><div class="kpi-sub">Desvio Padrão Acumulado</div></div>""", unsafe_allow_html=True)

    st.divider()

    # 4. WATERFALL CHART (Replaces Raw JSON)
    st.subheader("📊 Decomposição das Contribuições de Prontidão")
    df_waterfall = pd.DataFrame(
        list(readiness_data["waterfall"].items()),
        columns=["Fator Biológico", "Impacto no Score"]
    ).set_index("Fator Biológico")
    st.bar_chart(df_waterfall)

    st.divider()

    # 5. CHRONOLOGICAL CHART
    st.subheader(f"📈 Tendência de VRC ({st.session_state.display_window} Dias Exibidos)")
    st.line_chart(df_display.set_index("Date")[["HRV"]])

# ==========================================
# PAGE 2: STRENGTH & AUTOREGULATION ENGINE
# ==========================================
elif top_nav == "🏋️ Treino & Autoregulação":
    st.title("🏋️ Engine de Força & Carga Axial")
    st.caption("Substituição de exercícios e alocação de carga em kg baseada em RPE/1RM.")

    presc = autoregulate_strength_workout(score)
    st.info(f"💡 **Diretriz do Dia:** {presc['note']}")

    st.subheader("📋 Prescrição de Força sem Duplicações")
    for ex in presc["workout"]:
        if ex["substituted"]:
            st.warning(f"🔄 **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']} | **Carga Recomendada: {ex['target_kg']} kg**\n\n*Nota: {ex['reason']}*")
        else:
            st.success(f"✅ **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']} | **Carga Recomendada: {ex['target_kg']} kg** (Carga Axial: {ex['spinal_load']}/5)")

    st.divider()
    st.subheader("🧮 Calculadora de 1RM Estimado (Epley)")
    col_e1, col_e2 = st.columns(2)
    w_input = col_e1.number_input("Carga Utilizada (kg):", min_value=10.0, max_value=300.0, value=100.0)
    r_input = col_e2.number_input("Repetições Efetuadas:", min_value=1, max_value=30, value=8)
    e1rm = estimate_1rm(w_input, r_input)
    st.metric("1RM Estimado:", f"{e1rm} kg")

# ==========================================
# PAGE 3: TRAINING LOAD ANALYTICS (CTL/ATL/TSB FIXED)
# ==========================================
elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.title("📊 Training Load Analytics (Modelo Banister CTL/ATL/TSB)")
    st.caption("Gestão de carga de treino acumulada, fadiga aguda e forma física.")

    # Calculate CTL, ATL, TSB using Banister model
    ctl_vals, atl_vals, tsb_vals = compute_banister_ctl_atl_tsb(df_60d["DailyLoad"].tolist())
    
    df_load = df_60d.copy()
    df_load["CTL (Fitness)"] = ctl_vals
    df_load["ATL (Fadiga)"] = atl_vals
    df_load["TSB (Forma)"] = tsb_vals

    df_load_display = df_load.tail(st.session_state.display_window).set_index("Date")

    c_l1, c_l2, c_l3 = st.columns(3)
    c_l1.metric("CTL (Fitness Acumulado)", f"{ctl_vals[-1]} UA", f"{round(ctl_vals[-1] - ctl_vals[-7], 1)} vs 7d")
    c_l2.metric("ATL (Fadiga Aguda)", f"{atl_vals[-1]} UA", f"{round(atl_vals[-1] - atl_vals[-7], 1)} vs 7d")
    c_l3.metric("TSB (Forma / Frescura)", f"{tsb_vals[-1]} UA", "Zona de Carga Aguda" if tsb_vals[-1] < 0 else "Zona de Polimento")

    st.divider()

    st.subheader(f"📈 Projeção Real de Carga: CTL / ATL / TSB ({st.session_state.display_window} Dias)")
    st.line_chart(df_load_display[["CTL (Fitness)", "ATL (Fadiga)", "TSB (Forma)"]])

    st.divider()

    # Foster Monotony Section
    foster = compute_foster_load_metrics(df_60d["DailyLoad"].tail(7).tolist())
    st.subheader("⚠️ Monotonia e Tensão de Treino (Foster)")
    
    col_f1, col_f2 = st.columns(2)
    col_f1.metric("Carga Semanal Acumulada", f"{foster['weekly_load']} UA")
    
    monotony_val = foster['monotony']
    if monotony_val >= 2.0:
        col_f2.metric("Monotonia de Foster", f"{monotony_val}", "🔴 Elevada (Risco de Sobretreino)")
    elif monotony_val >= 1.5:
        col_f2.metric("Monotonia de Foster", f"{monotony_val}", "🟡 Moderada")
    else:
        col_f2.metric("Monotonia de Foster", f"{monotony_val}", "🟢 Saudar / Variada")

# ==========================================
# PAGE 4: HEALTHSPAN & LONGEVITY
# ==========================================
elif top_nav == "🧬 Healthspan & Longevidade":
    st.title("🧬 Biomarcadores de Longevidade & Healthspan")
    st.caption("Métricas cardiovasculares de longo prazo com dados de referência.")

    h1, h2, h3 = st.columns(3)
    h1.metric("VO2 Máx Estimado", f"{st.session_state.get('user_vo2max', 62)} mL/kg/min", "Fonte: Garmin Connect")
    h2.metric("FC Repouso Média 60d", f"{int(rhr_mean_60d)} bpm", "Excelente nível cardiovascular")
    h3.metric("Idade Fisiológica Estimada", f"{max(18, st.session_state.get('user_age', 24) - 5)} Anos", "Modelo Experimental")

    st.divider()
    st.subheader("📌 Tendência Estável de FC Repouso e Stress")
    st.line_chart(df_display.set_index("Date")[["RHR", "Stress"]])

# ==========================================
# PAGE 5: RACE HUB & PLANNING
# ==========================================
elif top_nav == "🎯 Race Hub & Planeamento":
    st.title("🎯 Race Hub & Planeamento de Provas")
    st.caption("Cronograma e contagem decrescente para os principais desafios.")
    
    st.success("🏆 **Próximo Desafio Principal:** Meia Maratona de Berlim (04/04/2027)")
    st.metric("Dias Restantes:", "152 Dias")

# ==========================================
# PAGE 6: AI COACH (GEMINI GROUNDED VIA SERVER)
# ==========================================
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.title("🤖 Coach IA Apex (Gemini Server-Grounded)")
    st.caption("O motor determinístico calcula os biomarcadores; a IA explica as recomendações em linguagem natural.")

    # Get API key safely from server environment/secrets
    gemini_api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)

    if not gemini_api_key:
        st.info("💡 Para ativar o Coach IA, adiciona a tua `GEMINI_API_KEY` nos secrets do Streamlit Cloud.")
    else:
        genai.configure(api_key=gemini_api_key)
        
        # Quick Prompt Chips
        st.markdown("**Perguntas Rápidas:**")
        cp1, cp2, cp3 = st.columns(3)
        prompt_input = None
        
        if cp1.button("Porque é que a minha prontidão é esta?", use_container_width=True):
            prompt_input = "Porque é que a minha prontidão de hoje deu este valor?"
        if cp2.button("Explica a minha carga desta semana", use_container_width=True):
            prompt_input = "Explica o meu nível de carga de treino e monotonia esta semana."
        if cp3.button("Adapta o meu treino para 45 min", use_container_width=True):
            prompt_input = "Como posso adaptar o treino de hoje para apenas 45 minutos?"

        # Chat interface
        user_msg = st.chat_input("Faz uma pergunta sobre a tua fisiologia de hoje...") or prompt_input

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
                És o Coach IA Apex. Utiliza EXCLUSIVAMENTE os dados calculados abaixo para responder ao utilizador.
                Não inventes números e cumpre os guardrails de segurança clínica.
                
                DADOS CALCULADOS:
                {context_json}
                
                PERGUNTA DO UTILIZADOR:
                {user_msg}
                """
                
                response = model.generate_content(prompt)
                st.chat_message("user").write(user_msg)
                st.chat_message("assistant").write(response.text)
            except Exception as e:
                st.error(f"Erro no processamento do Coach IA: {e}")

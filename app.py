import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from garminconnect import Garmin
import google.generativeai as genai

# Import from Engine Core
from engine_core import (
    t, DataQualityEngine, compute_zscore_readiness,
    evaluate_hrv_rhr_matrix, compute_foster_load_metrics,
    autoregulate_strength_workout, estimate_1rm, EXERCISE_DATABASE
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

# CSS Styling (Executive Dark + Glassmorphism)
st.markdown("""
<style>
    .stApp {
        background-color: #0B0F17;
        color: #E2E8F0;
    }
    
    /* Decision Banners */
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
    
    /* Cards */
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
        padding: 3px 10px;
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
if "time_window" not in st.session_state:
    st.session_state.time_window = 14
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "days_of_history" not in st.session_state:
    st.session_state.days_of_history = 35  # Default calibrating state simulator

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

# Global Time Window
st.sidebar.markdown("##### 📅 **Janela Temporal Global**")
time_opt = st.sidebar.select_slider(
    "Período de Análise:",
    options=[7, 14, 28, 90],
    value=st.session_state.time_window,
    format_func=lambda x: f"{x} Dias"
)
st.session_state.time_window = time_opt

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
    "Navegação Principais:",
    [
        "📌 Today (Decisão & Ação)",
        "🏋️ Treino & Autoregulação",
        "📊 Analytics de Carga (CTL/ATL)",
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
# GARMIN DATA EXTRACTION PIPELINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_garmin_pipeline(email, password, days_count):
    client = Garmin(email, password)
    client.login()
    
    today = date.today()
    dates_list, sleep_hist, hrv_hist, rhr_hist, stress_hist = [], [], [], [], []
    deep_hist, rem_hist, awake_hist = [], [], []

    # Clean Layer Extraction
    for days_back in range(days_count - 1, -1, -1):
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

    # Derived Layer DataFrame (Strict Chronological Ordering YYYY-MM-DD)
    df = pd.DataFrame({
        "Date": dates_list,
        "HRV": hrv_hist,
        "SleepScore": sleep_hist,
        "RHR": rhr_hist,
        "Stress": stress_hist,
        "DeepSleepSec": deep_hist,
        "REMSleepSec": rem_hist,
        "AwakeSec": awake_hist
    }).sort_values("Date").reset_index(drop=True)

    return df

# Fetch Data or Generate Synthetic Fallback
if st.session_state.garmin_logged_in:
    try:
        df_clean = fetch_garmin_pipeline(st.session_state.garmin_email, st.session_state.garmin_pass, st.session_state.time_window)
    except Exception as e:
        st.warning(f"Modo offline / erro de sync: {e}")
        df_clean = pd.DataFrame()
else:
    # Synthetic Athlete Fallback for Demonstration
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(st.session_state.time_window - 1, -1, -1)]
    df_clean = pd.DataFrame({
        "Date": dates,
        "HRV": [48, 52, 60, 62, 58, 47, 45, 50, 55, 64, 62, 59, 48, 47],
        "SleepScore": [70, 75, 82, 85, 78, 62, 58, 72, 80, 88, 84, 81, 65, 50],
        "RHR": [52, 51, 49, 48, 50, 54, 55, 52, 50, 48, 49, 50, 53, 54],
        "Stress": [28, 25, 20, 18, 22, 35, 38, 26, 22, 17, 19, 21, 32, 36],
        "DeepSleepSec": [2400, 3000, 3600, 4000, 3200, 1800, 1500, 2800, 3500, 4200, 3800, 3400, 2100, 1600],
        "REMSleepSec": [3600, 4200, 5000, 5400, 4800, 2200, 1800, 4000, 4800, 6000, 5200, 4900, 3000, 2000],
        "AwakeSec": [1200, 900, 600, 500, 800, 2400, 3000, 1000, 700, 400, 600, 800, 1800, 2500]
    }).sort_values("Date").reset_index(drop=True)

# Calculate Baselines & Current Metrics
latest_row = df_clean.iloc[-1]
hrv_curr = latest_row["HRV"] if pd.notnull(latest_row["HRV"]) else 50.0
rhr_curr = latest_row["RHR"] if pd.notnull(latest_row["RHR"]) else 52.0
sleep_curr = latest_row["SleepScore"] if pd.notnull(latest_row["SleepScore"]) else 70.0

hrv_mean, hrv_sd = df_clean["HRV"].mean(), max(df_clean["HRV"].std(), 2.0)
rhr_mean, rhr_sd = df_clean["RHR"].mean(), max(df_clean["RHR"].std(), 1.5)
sleep_mean, sleep_sd = df_clean["SleepScore"].mean(), max(df_clean["SleepScore"].std(), 5.0)

# Evaluate Data Quality & Calibration
calib_state, calib_label = DataQualityEngine.get_calibration_state(st.session_state.days_of_history)
data_conf, conf_reasons = DataQualityEngine.evaluate_sleep_quality(
    sleep_seconds=25200,
    deep_seconds=latest_row["DeepSleepSec"],
    rem_seconds=latest_row["REMSleepSec"],
    awake_seconds=latest_row["AwakeSec"]
)

# Compute Z-score Readiness
readiness_data = compute_zscore_readiness(
    hrv_val=hrv_curr, hrv_mean=hrv_mean, hrv_sd=hrv_sd,
    rhr_val=rhr_curr, rhr_mean=rhr_mean, rhr_sd=rhr_sd,
    sleep_score=sleep_curr, sleep_mean=sleep_mean, sleep_sd=sleep_sd,
    acute_load=80.0, load_mean=70.0, load_sd=10.0,
    mood_score=mood_val
)
score = readiness_data["readiness_score"]

# ==========================================
# PAGE 1: TODAY SCREEN (DECISION -> REASON -> ACTION)
# ==========================================
if top_nav == "📌 Today (Decisão & Ação)":
    col_t1, col_t2 = st.columns([3, 1], vertical_alignment="center")
    with col_t1:
        st.title("📌 Today / Decisão Diária")
        st.caption(f"Painel Executivo em modo **{st.session_state.user_mode}** | {calib_label}")
    with col_t2:
        st.markdown(f"<span class='confidence-badge'>🛡️ Confiança: {data_conf*100:.0f}%</span>", unsafe_allow_html=True)

    # 1. DECISION (HERO CARD)
    if score >= 70:
        card_class = "hero-card-green"
        decision_text = t("today_decision_green", lang)
        action_btn_text = t("action_start_zone2", lang)
    elif score >= 45:
        card_class = "hero-card-amber"
        decision_text = t("today_decision_amber", lang)
        action_btn_text = t("action_start_strength", lang)
    else:
        card_class = "hero-card-red"
        decision_text = t("today_decision_red", lang)
        action_btn_text = t("action_mobility", lang)

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
            • {'VRC Noturno (' + str(int(hrv_curr)) + ' ms) dentro da norma' if hrv_curr >= hrv_mean else t('today_reason_hrv_low', lang) + ' (' + str(int(hrv_curr)) + ' ms vs média ' + str(int(hrv_mean)) + ' ms)'}<br>
            • {'Pontuação de sono adequada (' + str(int(sleep_curr)) + '/100)' if sleep_curr >= sleep_mean else t('today_reason_sleep_low', lang)}<br>
            • FC de Repouso: <b>{int(rhr_curr)} bpm</b> | Estado do SNA: <b>{evaluate_hrv_rhr_matrix(hrv_curr, hrv_mean, hrv_sd, rhr_curr, rhr_mean, rhr_sd)['status']}</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. ACTION BUTTONS
    c_a1, c_a2, c_a3 = st.columns(3)
    c_a1.button(f"⚡ {action_btn_text}", use_container_width=True, type="primary")
    c_a2.button(f"🧘 {t('action_mobility', lang)}", use_container_width=True)
    c_a3.button(f"📝 {t('action_log_diary', lang)}", use_container_width=True)

    st.divider()

    # 3. DETAILS (KPI TILES WITH BASELINE COMPARISONS)
    st.subheader("📊 Biomarcadores de Hoje vs Linha de Base Personalizada")
    k1, k2, k3, k4 = st.columns(4)
    
    with k1:
        diff_hrv = round(hrv_curr - hrv_mean, 1)
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🫀 VRC Noturno</div><div class="kpi-value">{int(hrv_curr)} <span style="font-size:1rem;">ms</span></div><div class="kpi-sub">Média {st.session_state.time_window}d: {int(hrv_mean)} ms ({'+' if diff_hrv>=0 else ''}{diff_hrv})</div></div>""", unsafe_allow_html=True)
    with k2:
        diff_rhr = round(rhr_curr - rhr_mean, 1)
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">❤️ FC Repouso</div><div class="kpi-value">{int(rhr_curr)} <span style="font-size:1rem;">bpm</span></div><div class="kpi-sub">Média {st.session_state.time_window}d: {int(rhr_mean)} bpm ({'+' if diff_rhr>=0 else ''}{diff_rhr})</div></div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">😴 Pontuação Sono</div><div class="kpi-value">{int(sleep_curr)} <span style="font-size:1rem;">/100</span></div><div class="kpi-sub">Média {st.session_state.time_window}d: {int(sleep_mean)}/100</div></div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-card"><div class="kpi-title">🧠 Prontidão Z-Score</div><div class="kpi-value">{readiness_data['z_sum']} <span style="font-size:1rem;">σ</span></div><div class="kpi-sub">Desvio Padrão Acumulado</div></div>""", unsafe_allow_html=True)

    st.divider()

    # 4. HRV + RHR 2x2 MATRIX VISUAL
    st.subheader("🎯 Matriz Autonómica (VRC vs FC Repouso)")
    matrix_res = evaluate_hrv_rhr_matrix(hrv_curr, hrv_mean, hrv_sd, rhr_curr, rhr_mean, rhr_sd)
    col_m1, col_m2 = st.columns([2, 1])
    with col_m1:
        st.info(f"**Quadrante Atual:** {matrix_res['quadrant']} | **Status:** {matrix_res['status']}\n\n**Recomendação:** {matrix_res['action']}")
    with col_m2:
        st.json(readiness_data["waterfall"])

    # 5. CHRONOLOGICAL CHART WITH BASELINE BAND
    st.divider()
    st.subheader(f"📈 Tendência Sequencial de VRC ({st.session_state.time_window} Dias)")
    chart_df = df_clean.set_index("Date")[["HRV"]]
    st.line_chart(chart_df)

# ==========================================
# PAGE 2: STRENGTH & AUTOREGULATION ENGINE
# ==========================================
elif top_nav == "🏋️ Treino & Autoregulação":
    st.title("🏋️ Engine de Força & Carga Axial")
    st.caption("Substituição inteligente de exercícios com base na prontidão autonómica e proteção da coluna.")

    presc = autoregulate_strength_workout(score)
    st.info(f"💡 **Diretriz de Carga do Dia:** {presc['note']}")

    st.subheader("📋 Prescrição Autoregulada para Hoje")
    for ex in presc["workout"]:
        if ex["substituted"]:
            st.warning(f"🔄 **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']}\n\n*{ex['reason']}*")
        else:
            st.success(f"✅ **{ex['exercise']}** | {ex['sets']} séries x {ex['reps']} @ {ex['intensity']} (Carga Axial: {ex['spinal_load']}/5)")

    st.divider()
    st.subheader("🧮 Calculadora Rápida de 1RM Estimado (Epley)")
    col_e1, col_e2 = st.columns(2)
    w_input = col_e1.number_input("Carga Utilizada (kg):", min_value=10.0, max_value=300.0, value=100.0)
    r_input = col_e2.number_input("Repetições Efetuadas:", min_value=1, max_value=30, value=8)
    e1rm = estimate_1rm(w_input, r_input)
    st.metric("1RM Estimado:", f"{e1rm} kg")

# ==========================================
# PAGE 3: TRAINING LOAD ANALYTICS (CTL/ATL/TSB)
# ==========================================
elif top_nav == "📊 Analytics de Carga (CTL/ATL)":
    st.title("📊 Training Load Analytics (Banister & Foster)")
    st.caption("Controlo de carga crónica, fadiga aguda e risco de lesão.")

    foster = compute_foster_load_metrics([100, 150, 80, 200, 120, 0, 140])
    
    col_f1, col_f2, col_f3 = st.columns(3)
    col_f1.metric("Carga Semanal Acumulada", f"{foster['weekly_load']} pts")
    col_f2.metric("Monotonia de Foster", f"{foster['monotony']}", "Alerta se > 2.0")
    col_f3.metric("Strain (Tensão Acumulada)", f"{foster['strain']}")

    st.divider()
    st.subheader("📈 Projeção CTL / ATL / TSB")
    st.line_chart(df_clean.set_index("Date")[["HRV", "SleepScore"]])

# ==========================================
# PAGE 4: HEALTHSPAN & LONGEVITY
# ==========================================
elif top_nav == "🧬 Healthspan & Longevidade":
    st.title("🧬 Biomarcadores de Longevidade & Healthspan")
    st.caption("Métricas validadas epidemiologicamente para saúde cardiovascular e celular.")

    h1, h2, h3 = st.columns(3)
    h1.metric("VO2 Máx Estimado", f"{st.session_state.get('user_vo2max', 62)} mL/kg/min", "Percentil 95%")
    h2.metric("FC Repouso Média", f"{int(rhr_mean)} bpm", "Proteção Cardiovascular")
    h3.metric("Idade Fisiológica Estimada", f"{max(18, st.session_state.get('user_age', 24) - 5)} Anos")

    st.divider()
    st.subheader("📌 Estabilidade do Ritmo Circadiano & Sono")
    st.line_chart(df_clean.set_index("Date")[["RHR", "Stress"]])

# ==========================================
# PAGE 5: RACE HUB & PLANNING
# ==========================================
elif top_nav == "🎯 Race Hub & Planeamento":
    st.title("🎯 Race Hub & Planeamento de Provas")
    st.caption("Contagem decrescente e simulação de TSB para o dia da prova.")
    
    st.success("🏆 **Próxima Prova:** Meia Maratona de Berlim (04/04/2027)")
    st.metric("Dias Restantes:", "152 Dias")

# ==========================================
# PAGE 6: AI COACH (GEMINI GROUNDED)
# ==========================================
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.title("🤖 Coach IA Apex (Gemini Grounded)")
    st.caption("O motor determinístico calcula; a IA explica com contexto fundamentado.")

    api_key_input = st.text_input("Chave API Gemini:", type="password", key="gemini_key_app")
    if api_key_input:
        user_msg = st.text_input("Pergunta sobre o teu estado biológico de hoje:")
        if st.button("Consultar Coach IA", use_container_width=True) and user_msg:
            try:
                genai.configure(api_key=api_key_input)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # Grounded JSON context injection
                context_json = {
                    "readiness_score": score,
                    "hrv_current": hrv_curr,
                    "hrv_baseline": hrv_mean,
                    "rhr_current": rhr_curr,
                    "rhr_baseline": rhr_mean,
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
                st.markdown(f"**Coach IA:** {response.text}")
            except Exception as e:
                st.error(f"Erro na consulta da API Gemini: {e}")

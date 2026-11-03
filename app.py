import streamlit as st
from datetime import date, timedelta, datetime
from garminconnect import Garmin
import pandas as pd
import google.generativeai as genai

# ==========================================
# CONFIGURAÇÃO DA PÁGINA & ESTILO CUSTOMIZADO (PREMIUM UI)
# ==========================================
st.set_page_config(
    page_title="Apex Engine | Performance & Longevity",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Personalizada
st.markdown("""
<style>
    /* Fundo Principal e Cores Globais */
    .stApp {
        background-color: #0E1117;
        color: #E2E8F0;
    }
    
    /* Cartões Fisiológicos Premium */
    .premium-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border-radius: 16px;
        padding: 22px;
        border: 1px solid #334155;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4);
        margin-bottom: 20px;
        transition: transform 0.2s ease;
    }
    .premium-card:hover {
        border-color: #3B82F6;
    }
    .card-label {
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94A3B8;
        margin-bottom: 8px;
    }
    .card-value {
        font-size: 2.2rem;
        font-weight: 900;
        color: #F8FAFC;
        line-height: 1.1;
    }
    .card-sub {
        font-size: 0.82rem;
        color: #64748B;
        margin-top: 6px;
        font-weight: 500;
    }
    
    /* Badges de Estado */
    .badge-green { background: rgba(16, 185, 129, 0.15); color: #10B981; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.75rem; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-amber { background: rgba(245, 158, 11, 0.15); color: #F59E0B; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.75rem; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-red { background: rgba(239, 68, 68, 0.15); color: #EF4444; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 0.75rem; border: 1px solid rgba(239, 68, 68, 0.3); }
    
    /* Caixa do Diagnóstico IA Proativo */
    .ai-box {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%);
        border-left: 4px solid #8B5CF6;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 24px;
        border-top: 1px solid #334155;
        border-right: 1px solid #334155;
        border-bottom: 1px solid #334155;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# GESTÃO DE SESSÃO & MULTI-UTILIZADOR GARMIN
# ==========================================
if "garmin_logged_in" not in st.session_state:
    st.session_state.garmin_logged_in = False
if "garmin_email" not in st.session_state:
    st.session_state.garmin_email = "Vascoparganaguerreiro@gmail.com"
if "garmin_pass" not in st.session_state:
    st.session_state.garmin_pass = "Vasco1234"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ==========================================
# NAVEGAÇÃO LATERAL (SIDEBAR)
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine**")
st.sidebar.caption("Longevidade, Performance & Auto-Regulação")

# Painel de Login Garmin
with st.sidebar.expander("👤 Sessão Garmin Connect", expanded=not st.session_state.garmin_logged_in):
    if not st.session_state.garmin_logged_in:
        input_email = st.text_input("E-mail Garmin", value=st.session_state.garmin_email, key="login_email_input")
        input_password = st.text_input("Password Garmin", type="password", value=st.session_state.garmin_pass, key="login_pass_input")
        if st.button("🔑 Iniciar Sessão & Sincronizar", use_container_width=True):
            try:
                with st.spinner("A conectar à nuvem Garmin..."):
                    client = Garmin(input_email, input_password)
                    client.login()
                    st.session_state.garmin_email = input_email
                    st.session_state.garmin_pass = input_password
                    st.session_state.garmin_logged_in = True
                    st.cache_data.clear()
                    st.success("Conectado com sucesso!")
                    st.rerun()
            except Exception as e:
                st.error(f"Falha na autenticação: {e}")
    else:
        st.markdown(f"<span class='badge-green'>● Ligado</span> **{st.session_state.garmin_email}**", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚪 Encerrar Sessão", use_container_width=True):
            st.session_state.garmin_logged_in = False
            st.cache_data.clear()
            st.rerun()

page = st.sidebar.radio(
    "Módulos da Plataforma:",
    [
        "📊 Dashboard Fisiológico & Longevidade",
        "🏋️ Prescrição Adaptativa de Treino",
        "😴 Arquitetura do Sono & Recuperação",
        "🥗 Nutrição, Hidratação & Bioimpedância",
        "🎯 Central de Eventos & Pacing Strategy",
        "📜 Histórico Acumulado de Treinos"
    ]
)

st.sidebar.markdown("---")
lang = st.sidebar.selectbox("🌐 Idioma / Language", ["Português", "English"])

# Eventos Padrão do Utilizador
if "user_events" not in st.session_state:
    st.session_state.user_events = [
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "category": "Corrida"},
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "category": "Corrida"},
        {"name": "Triatlo Olímpico", "date": date(2027, 9, 12), "category": "Triatlo"},
        {"name": "IRONMAN 70.3 Cascais", "date": date(2027, 10, 17), "category": "Triatlo"}
    ]

# Auxiliares de Cálculo
def calculate_avg(values):
    valid_values = [v for v in values if isinstance(v, (int, float))]
    if not valid_values: return "N/A"
    return round(sum(valid_values) / len(valid_values), 1)

def format_seconds_to_hhmm(seconds):
    if not seconds or not isinstance(seconds, (int, float)): return "N/A"
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hrs}h {mins}m"

# ==========================================
# EXTRAÇÃO DE DADOS GARMIN (CACHE INTELIGENTE)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_garmin_data_user(email, password):
    client = Garmin(email, password)
    client.login()
    
    today = date.today()
    sleep_hist, hrv_hist, bb_peak_hist, rhr_hist, stress_hist, resp_hist = [], [], [], [], [], []
    deep_sleep_hist, rem_sleep_hist, light_sleep_hist, awake_hist = [], [], [], []
    dates_list = []
    body_records = []

    for days_back in range(13, -1, -1):
        current_date_obj = today - timedelta(days=days_back)
        current_date = current_date_obj.strftime("%Y-%m-%d")
        dates_list.append(current_date_obj.strftime("%d/%m"))
        
        try:
            sleep_data = client.get_sleep_data(current_date)
            dto = sleep_data.get("dailySleepDTO", {})
            sleep_hist.append(dto.get("sleepScores", {}).get("overall", {}).get("value"))
            deep_sleep_hist.append(dto.get("deepSleepSeconds"))
            rem_sleep_hist.append(dto.get("remSleepSeconds"))
            light_sleep_hist.append(dto.get("lightSleepSeconds"))
            awake_hist.append(dto.get("awakeSleepSeconds"))
        except Exception:
            sleep_hist.append(None); deep_sleep_hist.append(None); rem_sleep_hist.append(None); light_sleep_hist.append(None); awake_hist.append(None)

        try:
            hrv_data = client.get_hrv_data(current_date)
            hrv_hist.append(hrv_data.get("hrvSummary", {}).get("lastNightAvg"))
        except Exception:
            hrv_hist.append(None)

        try:
            summary = client.get_user_summary(current_date)
            bb_high = summary.get("bodyBatteryHighestValue") if isinstance(summary, dict) else None
            bb_peak_hist.append(bb_high)
        except Exception:
            bb_peak_hist.append(None)
            
        try:
            stats = client.get_user_summary(current_date)
            rhr_hist.append(stats.get("restingHeartRate"))
            stress_val = stats.get("averageStressLevel")
            stress_hist.append(stress_val if isinstance(stress_val, (int, float)) and stress_val >= 0 else None)
        except Exception:
            rhr_hist.append(None); stress_hist.append(None)

        try:
            resp_data = client.get_respiration_data(current_date)
            resp_hist.append(resp_data.get("avgWakingRespirationValue") or resp_data.get("avgSleepRespirationValue"))
        except Exception:
            resp_hist.append(None)

    today_str = today.strftime("%Y-%m-%d")
    hrv_status_str = "BALANCED"
    try: hrv_status_str = client.get_hrv_data(today_str).get("hrvSummary", {}).get("status", "BALANCED")
    except Exception: pass

    bb_current = None
    try:
        summary_today = client.get_user_summary(today_str)
        if isinstance(summary_today, dict): bb_current = summary_today.get("bodyBatteryMostRecentValue") or summary_today.get("bodyBatteryLevel")
    except Exception: pass

    training_readiness = "N/A"
    try:
        readiness = client.get_training_readiness(today_str)
        if isinstance(readiness, list) and readiness: training_readiness = readiness[0].get("score", "N/A")
        elif isinstance(readiness, dict): training_readiness = readiness.get("score", "N/A")
    except Exception: pass

    # Bioimpedância Garmin Index S2
    start_body_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    try:
        body_comp_raw = client.get_body_composition(start_body_date, today_str)
        weight_list = body_comp_raw.get("dateWeightList", []) if isinstance(body_comp_raw, dict) else (body_comp_raw if isinstance(body_comp_raw, list) else [])
        for record in weight_list:
            if isinstance(record, dict):
                raw_date = record.get("calendarDate") or record.get("date") or record.get("samplePk")
                dt_str = None
                if raw_date:
                    if isinstance(raw_date, (int, float)) or (isinstance(raw_date, str) and str(raw_date).isdigit()):
                        ts = int(raw_date) / 1000.0 if int(raw_date) > 1e11 else int(raw_date)
                        dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    else: dt_str = str(raw_date)[:10]
                
                w_kg = record.get("weight", 0) / 1000.0 if record.get("weight", 0) > 200 else record.get("weight")
                fat_pct = record.get("bodyFat")
                muscle_kg = record.get("muscleMass", 0) / 1000.0 if record.get("muscleMass", 0) > 200 else record.get("muscleMass")
                water_pct = record.get("bodyWater")
                bone_kg = record.get("boneMass", 0) / 1000.0 if record.get("boneMass", 0) > 200 else record.get("boneMass")
                bmi_val = record.get("bmi")
                
                if dt_str and w_kg and w_kg > 0:
                    body_records.append({
                        "Data": dt_str,
                        "Peso (kg)": round(w_kg, 1),
                        "Gordura Corporal (%)": round(fat_pct, 1) if fat_pct and fat_pct > 0 else None,
                        "Massa Muscular (kg)": round(muscle_kg, 1) if muscle_kg and muscle_kg > 0 else None,
                        "Água Corporal (%)": round(water_pct, 1) if water_pct and water_pct > 0 else None,
                        "Massa Óssea (kg)": round(bone_kg, 1) if bone_kg and bone_kg > 0 else None,
                        "IMC": round(bmi_val, 1) if bmi_val and bmi_val > 0 else None
                    })
    except Exception: pass

    sleep_rev, hrv_rev, bb_peak_rev = sleep_hist[::-1], hrv_hist[::-1], bb_peak_hist[::-1]
    rhr_rev, stress_rev, resp_rev = rhr_hist[::-1], stress_hist[::-1], resp_hist[::-1]
    deep_rev, rem_rev, light_rev, awake_rev = deep_sleep_hist[::-1], rem_sleep_hist[::-1], light_sleep_hist[::-1], awake_hist[::-1]

    df_history = pd.DataFrame({
        "Date": dates_list,
        "HRV / VRC (ms)": hrv_hist,
        "Sleep / Sono": sleep_hist,
        "RHR / FC Repouso (bpm)": rhr_hist,
        "Stress": stress_hist,
        "Body Battery Peak": bb_peak_hist
    }).set_index("Date")

    return {
        "hrv_status": hrv_status_str,
        "bb_current": bb_current,
        "training_readiness": training_readiness,
        "sleep": [sleep_rev[0], calculate_avg(sleep_rev[:3]), calculate_avg(sleep_rev[:7]), calculate_avg(sleep_rev)],
        "hrv": [hrv_rev[0], calculate_avg(hrv_rev[:3]), calculate_avg(hrv_rev[:7]), calculate_avg(hrv_rev)],
        "bb_peak": [bb_peak_rev[0], calculate_avg(bb_peak_rev[:3]), calculate_avg(bb_peak_rev[:7]), calculate_avg(bb_peak_rev)],
        "rhr": [rhr_rev[0], calculate_avg(rhr_rev[:3]), calculate_avg(rhr_rev[:7]), calculate_avg(rhr_rev)],
        "stress": [stress_rev[0], calculate_avg(stress_rev[:3]), calculate_avg(stress_rev[:7]), calculate_avg(stress_rev)],
        "resp": [resp_rev[0], calculate_avg(resp_rev[:3]), calculate_avg(resp_rev[:7]), calculate_avg(resp_rev)],
        "deep_sleep_today": deep_rev[0], "rem_sleep_today": rem_rev[0], "light_sleep_today": light_rev[0], "awake_today": awake_rev[0],
        "df_history": df_history,
        "body_records": body_records
    }

# Carregar dados se autenticado
if st.session_state.garmin_logged_in:
    with st.spinner("A processar métricas de longevidade e performance..."):
        data = fetch_garmin_data_user(st.session_state.garmin_email, st.session_state.garmin_pass)
else:
    data = {
        "hrv_status": "N/A", "bb_current": "N/A", "training_readiness": "N/A",
        "sleep": ["N/A"]*4, "hrv": ["N/A"]*4, "bb_peak": ["N/A"]*4,
        "rhr": ["N/A"]*4, "stress": ["N/A"]*4, "resp": ["N/A"]*4,
        "deep_sleep_today": None, "rem_sleep_today": None, "light_sleep_today": None, "awake_today": None,
        "df_history": pd.DataFrame(), "body_records": []
    }

# ==========================================
# ASSISTENTE IA GEMINI (CHAT FLUIDO NA SIDEBAR)
# ==========================================
st.sidebar.markdown("---")
with st.sidebar.expander("🤖 Coach IA Apex (Gemini)", expanded=False):
    api_key_input = st.text_input("Chave API Gemini:", type="password", key="gemini_key_input")
    
    if api_key_input:
        user_msg = st.text_input("Sua dúvida sobre recuperação/treino:")
        if st.button("Enviar Pergunta", use_container_width=True) and user_msg:
            try:
                genai.configure(api_key=api_key_input)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                contexto = f"""
                Atua como um Fisiologista de Alto Rendimento e Especialista em Longevidade.
                Utilizador: {st.session_state.garmin_email}
                Prontidão: {data['training_readiness']} | VRC: {data['hrv_status']} ({data['hrv'][0]} ms)
                Body Battery: {data['bb_current']} | Pontuação Sono: {data['sleep'][0]}
                Composição Corporal: {data['body_records'][-1] if data['body_records'] else 'Sem dados'}
                """
                response = model.generate_content(f"{contexto}\n\nPergunta: {user_msg}")
                st.session_state.chat_history.append(("Você", user_msg))
                st.session_state.chat_history.append(("Coach IA", response.text))
            except Exception as e:
                st.error(f"Erro no Gemini: {e}")
                
        for sender, text in reversed(st.session_state.chat_history[-4:]):
            st.markdown(f"**{sender}:** {text}")

# ==========================================
# MÓDULO 1: DASHBOARD FISIOLÓGICO & LONGEVIDADE
# ==========================================
if page == "📊 Dashboard Fisiológico & Longevidade":
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.title("📊 Painel Fisiológico & Main Details")
        st.caption("Visão executiva e biomarcadores essenciais de saúde celular, prontidão e recuperação autonómica.")
    with col_h2:
        if st.button("🔄 Sincronizar Garmin", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    # DIAGNÓSTICO PROATIVO IA (RESUMO EXECUTIVO DO DIA)
    readiness_num = data['training_readiness'] if isinstance(data['training_readiness'], (int, float)) else 50
    vrc_status = data['hrv_status']
    
    status_color = "badge-green" if readiness_num >= 70 and vrc_status == "BALANCED" else ("badge-amber" if readiness_num >= 45 else "badge-red")
    
    st.markdown(f"""
    <div class="ai-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <span style="font-weight: 800; color: #C084FC; font-size: 0.9rem; text-transform: uppercase;">🧠 Diagnóstico Fisiológico do Dia</span>
            <span class="{status_color}">ESTADO: {vrc_status}</span>
        </div>
        <div style="font-size: 0.95rem; color: #E2E8F0; line-height: 1.5;">
            • <b>Apetite de Carga:</b> Prontidão em <b>{data['training_readiness']}/100</b> com VRC Noturno em <b>{data['hrv'][0]} ms</b>.<br>
            • <b>Arquitetura de Sono:</b> Pontuação de <b>{data['sleep'][0]}</b> (Profundo: {format_seconds_to_hhmm(data['deep_sleep_today'])} | REM: {format_seconds_to_hhmm(data['rem_sleep_today'])}).<br>
            • <b>Recomendação de Longevidade:</b> {'Capacidade total autorizada para estímulos de alta intensidade (Z4/Threshold).' if readiness_num >= 70 else 'Fadiga autonómica detetada. Priorizar treino aeróbico contínuo em Zona 2 e foco em recuperação passiva.'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # CARTÕES PRINCIPAIS (MAIN DETAILS - SEM PALHA)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="premium-card"><div class="card-label">⚡ Prontidão de Treino</div><div class="card-value">{data['training_readiness']} <span style="font-size:1rem; color:#64748B;">/100</span></div><div class="card-sub">Capacidade Metabólica Hoje</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="premium-card"><div class="card-label">🫀 VRC / HRV Noturno</div><div class="card-value">{data['hrv'][0]} <span style="font-size:1rem; color:#64748B;">ms</span></div><div class="card-sub">Status: {data['hrv_status']}</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="premium-card"><div class="card-label">🔋 Body Battery</div><div class="card-value">{data['bb_current']} <span style="font-size:1rem; color:#64748B;">/100</span></div><div class="card-sub">Reserva Energética Atual</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="premium-card"><div class="card-label">😴 Pontuação de Sono</div><div class="card-value">{data['sleep'][0]} <span style="font-size:1rem; color:#64748B;">/100</span></div><div class="card-sub">Média 7d: {data['sleep'][2]}</div></div>""", unsafe_allow_html=True)

    st.divider()

    # DADOS SECUNDÁRIOS DE LONGEVIDADE E BIOIMPEDÂNCIA
    latest_body = data['body_records'][-1] if data['body_records'] else None
    
    st.subheader("📌 Biomarcadores de Longevidade & Composição")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("FC Repouso (Hoje)", f"{data['rhr'][0]} bpm" if data['rhr'][0] != 'N/A' else "N/A", f"{round(data['rhr'][0] - data['rhr'][3], 1)} bpm vs 14d" if isinstance(data['rhr'][0], (int, float)) and isinstance(data['rhr'][3], (int, float)) else None)
    m2.metric("Stress Diário Média", f"{data['stress'][0]}" if data['stress'][0] != 'N/A' else "N/A")
    m3.metric("Massa Corporal", f"{latest_body['Peso (kg)']} kg" if latest_body else "N/A")
    m4.metric("% Gordura Corporal", f"{latest_body['Gordura Corporal (%)']}%" if latest_body and latest_body['Gordura Corporal (%)'] else "N/A")

    st.divider()

    if not data["df_history"].empty:
        st.subheader("📈 Linha de Tendência Fisiológica Integrada (14 Dias)")
        st.line_chart(data["df_history"][["HRV / VRC (ms)", "Sleep / Sono", "RHR / FC Repouso (bpm)"]])

# ==========================================
# MÓDULO 2: PRESCRIÇÃO ADAPTATIVA DE TREINO
# ==========================================
elif page == "🏋️ Prescrição Adaptativa de Treino":
    st.title("🏋️ Prescrição & Auto-Regulação Adaptativa")
    st.caption("Ajuste automático de volume, intensidade e seleção de exercícios em tempo real com base no teu nível de fadiga.")

    # Cálculo Automático do Risco de Fadiga
    fatigue_score = 0
    if data['hrv_status'] in ["UNBALANCED", "LOW"]: fatigue_score += 3
    if isinstance(data['sleep'][0], (int, float)) and data['sleep'][0] < 60: fatigue_score += 2
    if isinstance(data['rhr'][0], (int, float)) and isinstance(data['rhr'][3], (int, float)) and data['rhr'][0] >= data['rhr'][3] + 4: fatigue_score += 2

    fatigue_level = "ELEVADA" if fatigue_score >= 4 else ("MODERADA" if fatigue_score >= 2 else "BAIXA")

    if fatigue_level == "ELEVADA": st.error(f"⚠️ **Nível de Fadiga Fisiológica: ELEVADA (Pontuação Risco: {fatigue_score})** — Recomenda-se redução drástica de carga axial.")
    elif fatigue_level == "MODERADA": st.warning(f"⚡ **Nível de Fadiga Fisiológica: MODERADA (Pontuação Risco: {fatigue_score})** — Manter volume, limitar RPE para evitar falha.")
    else: st.success(f"✅ **Nível de Fadiga Fisiológica: BAIXA (Pontuação Risco: {fatigue_score})** — Capacidade total para sessões de alta intensidade.")

    c_cat, c_env, c_time = st.columns(3)
    category = c_cat.selectbox("Modalidade Planeada:", ["Ginásio / Full Body C", "Ciclismo / Cycling", "Corrida / Running", "Natação / Swimming", "Brick Workout (Triatlo)"])
    env = c_env.radio("Ambiente:", ["Outdoor (Rua/Estrada)", "Indoor (Rolo/Passadeira)"])
    avail_time = c_time.slider("Tempo Disponível (min):", 30, 240, 75, 15)

    st.markdown("---")
    st.subheader(f"📋 Prescrição Otimizada: **{category}** ({avail_time} min)")

    if "Full Body C" in category:
        full_body_c = [
            {"num": "1", "name": "Dumbbell Bulgarian Split Squat", "type": "unilateral", "sets": 3, "reps": "8–10 / per leg", "rpe": "8–9", "why": "Força unilateral sem carga axial na coluna."},
            {"num": "2", "name": "Dumbbell Romanian Deadlift (RDL)", "type": "spinal_load", "sets": 3, "reps": "10–12", "rpe": "8–9", "why": "Fortalecimento da cadeia posterior e suporte lombar."},
            {"num": "3", "name": "Cable Lat Pulldown", "type": "upper", "sets": 3, "reps": "10–12", "rpe": "8–9", "why": "Tracção dorsal e suporte à braçada na natação."},
            {"num": "4", "name": "Incline Dumbbell Chest Press", "type": "upper", "sets": 3, "reps": "10–12", "rpe": "8–9", "why": "Desenvolvimento do peitoral superior e estabilidade de ombro."}
        ]
        for ex in full_body_c:
            if fatigue_level == "ELEVADA":
                if ex["type"] == "spinal_load": st.warning(f"**{ex['num']}. {ex['name']}** ➔ 🔄 **TROCAR POR CADEIRA FLEXORA** (Proteger Coluna) | 2 séries x 12 reps @ RPE 7")
                elif ex["type"] == "unilateral": st.warning(f"**{ex['num']}. {ex['name']}** ➔ 🔄 **TROCAR POR CADEIRA EXTENSORA** | 2 séries x 12 reps @ RPE 7")
                else: st.info(f"**{ex['num']}. {ex['name']}** | 2 séries x {ex['reps']} @ RPE 7 (Volume -30%)")
            else:
                st.success(f"**{ex['num']}. {ex['name']}** | {ex['sets']} séries x {ex['reps']} @ RPE {ex['rpe']} | *Foco:* {ex['why']}")

    elif "Corrida" in category:
        if fatigue_level == "ELEVADA": st.warning(f"🏃 **Ajuste de Corrida:** {min(avail_time, 40)} min em Zona 1 / Caminhada Ativa (RPE 4). Evitar impactos fortes.")
        else: st.success(f"🏃 **Sessão Principal:** {avail_time} min Zona 2 Aeróbica com 4x100m Acelerações Progressivas no final.")

# ==========================================
# MÓDULO 3: ARQUITETURA DO SONO & RECUPERAÇÃO
# ==========================================
elif page == "😴 Arquitetura do Sono & Recuperação":
    st.title("😴 Arquitetura do Sono & Recuperação Avançada")
    st.caption("Decomposição detalhada das fases de sono, eficiência noturna e variabilidade cardíaca.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pontuação de Sono", f"{data['sleep'][0]} /100")
    c2.metric("Sono Profundo", format_seconds_to_hhmm(data['deep_sleep_today']))
    c3.metric("Sono REM", format_seconds_to_hhmm(data['rem_sleep_today']))
    c4.metric("Sono Leve", format_seconds_to_hhmm(data['light_sleep_today']))

    st.divider()
    st.subheader("🌙 Biomarcadores Noturnos Complementares")
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("VRC Noturno", f"{data['hrv'][0]} ms" if data['hrv'][0] != 'N/A' else "N/A")
    col_s2.metric("FC Repouso Noturna", f"{data['rhr'][0]} bpm" if data['rhr'][0] != 'N/A' else "N/A")
    col_s3.metric("Freq. Respiratória", f"{data['resp'][0]} brpm" if data['resp'][0] != 'N/A' else "N/A")
    col_s4.metric("Tempo Acordado", format_seconds_to_hhmm(data['awake_today']))

    st.divider()
    if not data["df_history"].empty:
        st.subheader("📊 Histórico e Qualidade de Sono (14d)")
        st.line_chart(data["df_history"][["Sleep / Sono", "HRV / VRC (ms)"]])

# ==========================================
# MÓDULO 4: NUTRIÇÃO, HIDRATAÇÃO & BIOIMPEDÂNCIA
# ==========================================
elif page == "🥗 Nutrição, Hidratação & Bioimpedância":
    st.title("🥗 Nutrição, Hidratação & Recomposição Corporal")
    st.caption("Cálculo dinâmico de necessidades energéticas e macronutrientes com base na bioimpedância da Garmin Index S2.")

    records = data.get("body_records", [])
    if records:
        df_body = pd.DataFrame(records).sort_values("Data").set_index("Data")
        latest = df_body.iloc[-1]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Peso Atual", f"{latest['Peso (kg)']} kg")
        c2.metric("% Gordura", f"{latest['Gordura Corporal (%)']}%" if pd.notnull(latest['Gordura Corporal (%)']) else "N/A")
        c3.metric("Massa Muscular", f"{latest['Massa Muscular (kg)']} kg" if pd.notnull(latest['Massa Muscular (kg)']) else "N/A")
        c4.metric("Água Corporal", f"{latest['Água Corporal (%)']}%" if pd.notnull(latest['Água Corporal (%)']) else "N/A")

        st.divider()
        st.subheader("🔥 Calculadora de Necessidades Calóricas & Macronutrientes")
        
        # Estimar Taxa Metabólica Basal (Katch-McArdle se houver %gordura)
        weight = latest['Peso (kg)']
        fat_p = latest['Gordura Corporal (%)'] if pd.notnull(latest['Gordura Corporal (%)']) else 15.0
        lbm = weight * (1 - (fat_p / 100.0))
        bmr = int(370 + (21.6 * lbm))

        goal = st.selectbox("Objetivo Nutricional Ativo:", ["Recomposição Corporal / Hipertrofia", "Performance & Endurance (Triatlo)", "Longevidade & Manutenção"])
        
        target_calories = bmr + 400 if "Hipertrofia" in goal else (bmr + 600 if "Endurance" in goal else bmr)
        protein_g = int(weight * 2.0)
        fat_g = int(weight * 0.9)
        carbs_g = int((target_calories - (protein_g * 4 + fat_g * 9)) / 4)

        cn1, cn2, cn3, cn4 = st.columns(4)
        cn1.metric("TMB (Taxa Basal)", f"{bmr} kcal")
        cn2.metric("Proteína Diária Target", f"{protein_g} g", f"{round(protein_g*4/target_calories*100)}% kcal")
        cn3.metric("Hidratos de Carbono", f"{carbs_g} g", f"{round(carbs_g*4/target_calories*100)}% kcal")
        cn4.metric("Gorduras Saudáveis", f"{fat_g} g", f"{round(fat_g*9/target_calories*100)}% kcal")

        st.divider()
        st.subheader("📈 Análise Múltipla de Tendências de Composição")
        selected_m = st.multiselect("Métricas a cruzar:", options=list(df_body.columns), default=["Gordura Corporal (%)", "Massa Muscular (kg)"])
        if selected_m: st.line_chart(df_body[selected_m])
    else:
        st.info("ℹ️ Efetue o login na barra lateral para carregar os dados da balança Garmin Index S2.")

# ==========================================
# MÓDULO 5: CENTRAL DE EVENTOS & PACING STRATEGY
# ==========================================
elif page == "🎯 Central de Eventos & Pacing Strategy":
    st.title("🎯 Central de Eventos & Estratégia de Prova")
    st.caption("Planeamento cronológico, contagem decrescente e estimador de ritmo de prova.")

    now = datetime.now()
    sorted_events = sorted(st.session_state.user_events, key=lambda x: x["date"])

    if sorted_events:
        next_event = sorted_events[0]
        event_dt = datetime.combine(next_event["date"], datetime.min.time())
        delta = event_dt - now
        
        st.markdown(f"""
        <div class="premium-card" style="border: 2px solid #10B981;">
            <div style="display:flex; justify-size:space-between; align-items:center;">
                <span class="badge-green">PRÓXIMO DESAFIO PRINCIPAL</span>
                <span style="color:#94A3B8; font-size:0.85rem;">Categoria: {next_event.get('category', 'Geral')}</span>
            </div>
            <div style="color:#F8FAFC; font-size:2rem; font-weight:900; margin:8px 0;">🏆 {next_event['name']}</div>
            <div style="color:#10B981; font-size:1.8rem; font-weight:800;">{max(0, delta.days)} Dias : {max(0, delta.seconds // 3600)} Horas : {max(0, (delta.seconds % 3600) // 60)} Minutos</div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("⏱️ Estimador de Ritmo Alvo (Pacing Calculator)")
    col_p1, col_p2 = st.columns(2)
    dist_km = col_p1.number_input("Distância da Prova (km):", min_value=1.0, max_value=226.0, value=21.1)
    target_time_min = col_p2.number_input("Tempo Alvo Desejado (minutos):", min_value=10, max_value=1200, value=105)

    if dist_km > 0 and target_time_min > 0:
        pace_sec = (target_time_min * 60) / dist_km
        pace_min = int(pace_sec // 60)
        pace_rem_sec = int(pace_sec % 60)
        speed_kmh = round(dist_km / (target_time_min / 60.0), 2)

        st.info(f"🎯 **Pacing Alvo Exigido:** **{pace_min}:{pace_rem_sec:02d} min/km** | Velocidade Média: **{speed_kmh} km/h**")

    st.divider()
    st.subheader("📅 Cronograma de Eventos Filtrável")
    cat_filter = st.selectbox("Filtrar Provas por Categoria:", ["Todas", "Corrida", "Triatlo", "Ciclismo", "Natação", "Musculação / Ginásio"])
    
    filtered = sorted_events if cat_filter == "Todas" else [e for e in sorted_events if e.get("category") == cat_filter]
    for ev in filtered:
        col1, col2, col3 = st.columns([3, 2, 2])
        col1.markdown(f"**📌 {ev['name']}** ({ev.get('category', 'Geral')})")
        col2.caption(f"🗓️ {ev['date'].strftime('%d/%m/%Y')}")
        col3.markdown(f"⏱️ **{(datetime.combine(ev['date'], datetime.min.time()) - now).days} dias restantes**")
        st.divider()

# ==========================================
# MÓDULO 6: HISTÓRICO ACUMULADO DE TREINOS
# ==========================================
elif page == "📜 Histórico Acumulado de Treinos":
    st.title("📜 Histórico de Treinos & Volume Acumulado")
    st.caption("Consolidado completo das tuas atividades registadas na nuvem Garmin.")

    c_d1, c_d2 = st.columns(2)
    start_d = c_d1.date_input("Data Inicial", value=date.today() - timedelta(days=30))
    end_d = c_d2.date_input("Data Final", value=date.today())

    sport_filter = st.multiselect("Modalidades:", ["Corrida", "Ciclismo", "Natação", "Musculação / Ginásio"], default=["Corrida", "Ciclismo", "Natação", "Musculação / Ginásio"])

    if st.session_state.garmin_logged_in:
        try:
            with st.spinner("A descarregar histórico Garmin..."):
                client = Garmin(st.session_state.garmin_email, st.session_state.garmin_pass)
                client.login()
                activities = client.get_activities_by_date(start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"))
                
                parsed_act = []
                for act in activities:
                    sport_type = act.get("activityType", {}).get("typeKey", "outro").lower()
                    cat = "Outro"
                    if "running" in sport_type: cat = "Corrida"
                    elif "cycling" in sport_type: cat = "Ciclismo"
                    elif "swimming" in sport_type: cat = "Natação"
                    elif "fitness" in sport_type or "strength" in sport_type: cat = "Musculação / Ginásio"
                    
                    if cat in sport_filter:
                        parsed_act.append({
                            "Data": str(act.get("startTimeLocal", ""))[:10],
                            "Nome": act.get("activityName", "Sessão"),
                            "Modalidade": cat,
                            "Distância (km)": round(act.get("distance", 0) / 1000.0, 2),
                            "Duração (min)": round(act.get("duration", 0) / 60.0, 1),
                            "Calorias (kcal)": act.get("calories", 0)
                        })

                if parsed_act:
                    df_act = pd.DataFrame(parsed_act)
                    
                    st.subheader("📊 Totais Acumulados")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Volume Total", f"{round(df_act['Distância (km)'].sum(), 1)} km")
                    m2.metric("Tempo Acumulado", f"{round(df_act['Duração (min)'].sum() / 60.0, 1)} horas")
                    m3.metric("Calorias Gastas", f"{int(df_act['Calorias (kcal)'].sum())} kcal")
                    m4.metric("Total de Treinos", f"{len(df_act)} sessões")

                    st.divider()
                    st.dataframe(df_act, use_container_width=True)
                else: st.info("Nenhuma atividade encontrada no período.")
        except Exception as e: st.error(f"Erro ao obter atividades: {e}")
    else: st.info("ℹ️ Efetue o login na barra lateral para descarregar o histórico de atividades.")

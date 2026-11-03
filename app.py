import streamlit as st
from datetime import date, timedelta, datetime
from garminconnect import Garmin
import pandas as pd
import google.generativeai as genai

# ==========================================
# CONFIGURAÇÃO DA PÁGINA & ESTILO EXECUTIVE DARK
# ==========================================
st.set_page_config(
    page_title="Apex Engine | Performance & Longevity",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Personalizada Executiva
st.markdown("""
<style>
    .stApp {
        background-color: #0B0F17;
        color: #E2E8F0;
    }
    
    /* Header Dinâmico Semáforo */
    .status-banner-green {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 78, 59, 0.25) 100%);
        border-left: 5px solid #10B981;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 24px;
        border: 1px solid rgba(16, 185, 129, 0.2);
    }
    .status-banner-amber {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(120, 53, 15, 0.25) 100%);
        border-left: 5px solid #F59E0B;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 24px;
        border: 1px solid rgba(245, 158, 11, 0.2);
    }
    .status-banner-red {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(127, 29, 29, 0.25) 100%);
        border-left: 5px solid #EF4444;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 24px;
        border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    /* Cartões Executivos */
    .metric-card-exec {
        background: #131A27;
        border-radius: 14px;
        padding: 18px 20px;
        border: 1px solid #1E293B;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        margin-bottom: 16px;
    }
    .metric-label-exec {
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #94A3B8;
        margin-bottom: 6px;
    }
    .metric-value-exec {
        font-size: 2.1rem;
        font-weight: 900;
        color: #F8FAFC;
        line-height: 1.1;
    }
    .metric-sub-exec {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 6px;
    }
    
    /* Status Live Sync */
    .sync-pill {
        background: rgba(16, 185, 129, 0.15);
        color: #10B981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 12px;
    }
    .badge-status {
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# GESTÃO DE SESSÃO & DADOS GLOBAIS
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
    st.session_state.user_mode = "Atleta de Alto Rendimento"
if "time_window" not in st.session_state:
    st.session_state.time_window = 14
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "last_sync_time" not in st.session_state:
    st.session_state.last_sync_time = "N/A"

# Eventos Padrão na Sessão
if "user_events" not in st.session_state:
    st.session_state.user_events = [
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "category": "Corrida"},
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "category": "Corrida"},
        {"name": "Triatlo Olímpico", "date": date(2027, 9, 12), "category": "Triatlo"},
        {"name": "IRONMAN 70.3 Cascais", "date": date(2027, 10, 17), "category": "Triatlo"}
    ]

# ==========================================
# BARRA LATERAL REDESENHADA (SIDEBAR PREMIUM)
# ==========================================

# 14. Header Discreto com Alternador de Idioma (PT | EN)
sb_head_left, sb_head_right = st.sidebar.columns([3, 2])
with sb_head_left:
    st.markdown("### ⚡ **Apex Engine**")
with sb_head_right:
    c_pt, c_en = st.columns(2)
    if c_pt.button("PT", use_container_width=True, type="primary" if st.session_state.lang == "PT" else "secondary"):
        st.session_state.lang = "PT"; st.rerun()
    if c_en.button("EN", use_container_width=True, type="primary" if st.session_state.lang == "EN" else "secondary"):
        st.session_state.lang = "EN"; st.rerun()

st.sidebar.caption("Longevidade, Performance & Auto-Regulação")
st.sidebar.markdown("---")

# 5. Seletor de Janela Temporal Global
st.sidebar.markdown("##### 📅 **Janela Temporal Global**")
time_opt = st.sidebar.select_slider(
    "Período de Análise:",
    options=[7, 14, 28, 90],
    value=st.session_state.time_window,
    format_func=lambda x: f"{x} Dias"
)
st.session_state.time_window = time_opt

# 3. Widget de Estado de Conexão Live Garmin (Garmin Sync Status)
with st.sidebar.expander("👤 **Garmin Connect Status**", expanded=not st.session_state.garmin_logged_in):
    if st.session_state.garmin_logged_in:
        st.markdown(f"<div class='sync-pill'>● Live Sync Ativo</div>", unsafe_allow_html=True)
        st.caption(f"Conta: **{st.session_state.garmin_email}**")
        st.caption(f"Última Sincronização: **{st.session_state.last_sync_time}**")
        if st.button("🚪 Terminar Sessão", use_container_width=True):
            st.session_state.garmin_logged_in = False
            st.cache_data.clear()
            st.rerun()
    else:
        input_email = st.text_input("E-mail Garmin", value=st.session_state.garmin_email)
        input_password = st.text_input("Password Garmin", type="password", value=st.session_state.garmin_pass)
        if st.button("🔑 Iniciar Sessão & Sincronizar", use_container_width=True):
            try:
                with st.spinner("A conectar à nuvem Garmin..."):
                    client = Garmin(input_email, input_password)
                    client.login()
                    st.session_state.garmin_email = input_email
                    st.session_state.garmin_pass = input_password
                    st.session_state.garmin_logged_in = True
                    st.session_state.last_sync_time = datetime.now().strftime("%H:%M:%S")
                    st.cache_data.clear()
                    st.success("Conectado com sucesso!")
                    st.rerun()
            except Exception as e:
                st.error(f"Falha na autenticação: {e}")

st.sidebar.markdown("---")

# 1 & 2. Navegação Estruturada por Pilares Temáticos (Categorias Expansíveis)
st.sidebar.markdown("##### 🧭 **Navegação de Módulos**")

module_category = st.sidebar.radio(
    "Selecionar Pilar:",
    [
        "📊 Performance & Fisiologia",
        "🧬 Longevidade & Recomposição",
        "🎯 Planeamento & Competição"
    ]
)

if module_category == "📊 Performance & Fisiologia":
    page = st.sidebar.radio(
        "Módulo:",
        [
            "⚡ Command Center (Visão Geral)",
            "🏋️ Auto-Regulation Engine (Prescrição)",
            "📊 Training Load Analytics (Matriz CTL/ATL)"
        ]
    )
elif module_category == "🧬 Longevidade & Recomposição":
    page = st.sidebar.radio(
        "Módulo:",
        [
            "😴 Sleep Architecture & Recovery",
            "🥗 Metabolic Health & Composition",
            "🧬 Biomarcadores de Longevidade (VO2/RHR)",
            "🧱 Engine de Força & Carga Axial"
        ]
    )
else:
    page = st.sidebar.radio(
        "Módulo:",
        [
            "🎯 Race Hub & Pacing Matrix",
            "📜 Histórico Acumulado de Treinos"
        ]
    )

st.sidebar.markdown("---")

# 4. Perfil de Atleta & Configurações de Fisiologia Base
with st.sidebar.expander("⚙️ **Fisiologia Base & Zonas**"):
    st.number_input("Idade:", min_value=15, max_value=90, value=24, key="user_age")
    st.number_input("FC Máxima (bpm):", min_value=140, max_value=220, value=192, key="user_hr_max")
    st.number_input("FTP / Limiar (Watts):", min_value=100, max_value=500, value=280, key="user_ftp")
    st.number_input("VO2 Máx Estimado (mL/kg/min):", min_value=30, max_value=85, value=62, key="user_vo2max")

# 10. Mini-Calculadora Rápida de Ritmos e Zonas (Quick Widget)
with st.sidebar.expander("⏱️ **Quick Pacing & Zone Calculator**"):
    calc_pace_min = st.number_input("Min/km:", min_value=2.0, max_value=10.0, value=4.25, step=0.05)
    calc_speed = round(60.0 / calc_pace_min, 2)
    st.caption(f"Velocidade: **{calc_speed} km/h**")
    st.caption(f"Estimativa 10K: **{int(calc_pace_min*10)} min {int((calc_pace_min*10%1)*60):02d}s**")

# 13. Módulo de Registo de Sintomas Biológicos & Subjetivos (RPE / Humor)
with st.sidebar.expander("📝 **Diário Subjetivo (Humor & Soreness)**"):
    soreness_val = st.slider("Dor Muscular (Soreness):", 1, 5, 2, help="1 = Sem dor, 5 = Dor extrema")
    mood_val = st.slider("Motivação / Humor:", 1, 5, 4, help="1 = Sem motivação, 5 = Excelente")
    stress_psych = st.slider("Stress Mental Fora do Treino:", 1, 5, 2)
    st.session_state.subjetive_score = (mood_val * 2) - soreness_val - stress_psych

# 8. Coach IA Apex (Gemini) na Sidebar
with st.sidebar.expander("🤖 **Coach IA Apex (Gemini)**"):
    api_key_input = st.text_input("Chave API Gemini:", type="password", key="gemini_key_input")
    if api_key_input:
        user_msg = st.text_input("Dúvida de Fisiologia/Treino:")
        if st.button("Enviar Pergunta", use_container_width=True) and user_msg:
            try:
                genai.configure(api_key=api_key_input)
                model = genai.GenerativeModel('gemini-1.5-flash')
                contexto = f"Utilizador: {st.session_state.garmin_email} | Janela: {st.session_state.time_window}d | Subjetivo: {st.session_state.get('subjetive_score', 0)}"
                response = model.generate_content(f"{contexto}\n\nPergunta: {user_msg}")
                st.session_state.chat_history.append(("Você", user_msg))
                st.session_state.chat_history.append(("Coach IA", response.text))
            except Exception as e: st.error(f"Erro: {e}")
        for sender, text in reversed(st.session_state.chat_history[-4:]):
            st.markdown(f"**{sender}:** {text}")

# ==========================================
# FUNÇÕES AUXILIARES & EXTRAÇÃO GARMIN
# ==========================================
def calculate_avg(values):
    valid_values = [v for v in values if isinstance(v, (int, float))]
    if not valid_values: return "N/A"
    return round(sum(valid_values) / len(valid_values), 1)

def format_seconds_to_hhmm(seconds):
    if not seconds or not isinstance(seconds, (int, float)): return "N/A"
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hrs}h {mins}m"

@st.cache_data(ttl=3600)
def fetch_garmin_data_user(email, password, days_count):
    client = Garmin(email, password)
    client.login()
    
    today = date.today()
    sleep_hist, hrv_hist, bb_peak_hist, rhr_hist, stress_hist, resp_hist = [], [], [], [], [], []
    deep_sleep_hist, rem_sleep_hist, light_sleep_hist, awake_hist = [], [], [], []
    dates_list = []
    body_records = []

    # Extração Cronológica com Janela Temporal Dinâmica
    for days_back in range(days_count - 1, -1, -1):
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
        "VRC Noturno (ms)": hrv_hist,
        "Pontuação Sono": sleep_hist,
        "FC Repouso (bpm)": rhr_hist,
        "Nível Stress": stress_hist,
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

# Carregar dados dinâmicos com a janela temporal selecionada na Sidebar
if st.session_state.garmin_logged_in:
    with st.spinner(f"A sincronizar biomarcadores ({st.session_state.time_window} Dias)..."):
        data = fetch_garmin_data_user(st.session_state.garmin_email, st.session_state.garmin_pass, st.session_state.time_window)
else:
    data = {
        "hrv_status": "N/A", "bb_current": "N/A", "training_readiness": "N/A",
        "sleep": ["N/A"]*4, "hrv": ["N/A"]*4, "bb_peak": ["N/A"]*4,
        "rhr": ["N/A"]*4, "stress": ["N/A"]*4, "resp": ["N/A"]*4,
        "deep_sleep_today": None, "rem_sleep_today": None, "light_sleep_today": None, "awake_today": None,
        "df_history": pd.DataFrame(), "body_records": []
    }

# ==========================================
# MÓDULO 1: COMMAND CENTER (VISÃO GERAL)
# ==========================================
if page == "⚡ Command Center (Visão Geral)":
    col_h1, col_h2 = st.columns([3, 1], vertical_alignment="center")
    with col_h1:
        st.title("⚡ Command Center")
        st.caption(f"Visão executiva e biomarcadores essenciais (Janela Ativa: {st.session_state.time_window} Dias).")
    with col_h2:
        if st.button("🔄 Sincronizar Garmin", use_container_width=True):
            st.cache_data.clear(); st.rerun()

    readiness_val = data['training_readiness'] if isinstance(data['training_readiness'], (int, float)) else 50
    vrc_status = data['hrv_status']
    
    # 9. Readiness Badge Visual
    readiness_badge_color = "#10B981" if readiness_val >= 70 else ("#F59E0B" if readiness_val >= 45 else "#EF4444")

    banner_class = "status-banner-green" if readiness_val >= 70 and vrc_status == "BALANCED" else ("status-banner-amber" if readiness_val >= 45 else "status-banner-red")
    banner_title = "ESTADO FISIOLÓGICO: ÓTIMO (PRONTO PARA CARGA)" if readiness_val >= 70 else ("ESTADO FISIOLÓGICO: ATENÇÃO (CARGA MODERADA)" if readiness_val >= 45 else "ESTADO FISIOLÓGICO: FADIGA CRÍTICA (RECUPERAÇÃO)")

    st.markdown(f"""
    <div class="{banner_class}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-weight: 900; font-size: 1.05rem; letter-spacing: 0.04em;">{banner_title}</span>
            <span style="background: {readiness_badge_color}; color: #000; padding: 4px 12px; border-radius: 12px; font-weight: 800; font-size: 0.85rem;">PRONTIDÃO: {readiness_val}/100</span>
        </div>
        <div style="font-size: 0.92rem; line-height: 1.5; color: #E2E8F0;">
            • <b>Apetite de Carga:</b> VRC Noturno em <b>{data['hrv'][0]} ms</b> (Status: {vrc_status}).<br>
            • <b>Arquitetura de Sono:</b> Pontuação de <b>{data['sleep'][0]}/100</b> (Profundo: {format_seconds_to_hhmm(data['deep_sleep_today'])} | REM: {format_seconds_to_hhmm(data['rem_sleep_today'])}).<br>
            • <b>Fator Subjetivo (Diário):</b> Score de Prontidão Mental em <b>{st.session_state.get('subjetive_score', 0)} pts</b>.<br>
            • <b>Recomendação Adaptativa:</b> {'Estímulo autorizado para VO2 Max ou Limiar de Lactato (Z4/Z5).' if readiness_val >= 70 else 'Priorizar acumulação aeróbica em Zona 2 ou treino de força funcional sem carga na coluna.'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Cartões Principais (Main Details)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="metric-card-exec"><div class="metric-label-exec">⚡ Prontidão de Treino</div><div class="metric-value-exec">{data['training_readiness']} <span style="font-size:1rem; color:#64748B;">/100</span></div><div class="metric-sub-exec">Capacidade Metabólica</div></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="metric-card-exec"><div class="metric-label-exec">🫀 VRC Noturno (HRV)</div><div class="metric-value-exec">{data['hrv'][0]} <span style="font-size:1rem; color:#64748B;">ms</span></div><div class="metric-sub-exec">Status: {data['hrv_status']}</div></div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="metric-card-exec"><div class="metric-label-exec">🔋 Body Battery</div><div class="metric-value-exec">{data['bb_current']} <span style="font-size:1rem; color:#64748B;">/100</span></div><div class="metric-sub-exec">Reserva Energética</div></div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="metric-card-exec"><div class="metric-label-exec">😴 Pontuação de Sono</div><div class="metric-value-exec">{data['sleep'][0]} <span style="font-size:1rem; color:#64748B;">/100</span></div><div class="metric-sub-exec">Média {st.session_state.time_window}d: {data['sleep'][3]}</div></div>""", unsafe_allow_html=True)

    st.divider()

    # Biomarcadores de Longevidade
    latest_body = data['body_records'][-1] if data['body_records'] else None
    st.subheader("📌 Biomarcadores de Longevidade & Saúde Metabólica")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("FC Repouso (Hoje)", f"{data['rhr'][0]} bpm" if data['rhr'][0] != 'N/A' else "N/A", f"{round(data['rhr'][0] - data['rhr'][3], 1)} bpm vs {st.session_state.time_window}d" if isinstance(data['rhr'][0], (int, float)) and isinstance(data['rhr'][3], (int, float)) else None)
    m2.metric("Nível de Stress Média", f"{data['stress'][0]}" if data['stress'][0] != 'N/A' else "N/A")
    m3.metric("Massa Corporal", f"{latest_body['Peso (kg)']} kg" if latest_body else "N/A")
    m4.metric("% Gordura Corporal", f"{latest_body['Gordura Corporal (%)']}%" if latest_body and latest_body['Gordura Corporal (%)'] else "N/A")

    st.divider()

    # Gráfico Histórico com Eixos Específicos
    if not data["df_history"].empty:
        st.subheader(f"📈 Curvas Fisiológicas ({st.session_state.time_window} Dias - Cronológico)")
        tab_vrc, tab_sleep, tab_rhr = st.tabs(["🫀 VRC Noturno (ms)", "😴 Pontuação de Sono", "❤️ FC Repouso (bpm)"])
        with tab_vrc: st.line_chart(data["df_history"][["VRC Noturno (ms)"]])
        with tab_sleep: st.line_chart(data["df_history"][["Pontuação Sono"]])
        with tab_rhr: st.line_chart(data["df_history"][["FC Repouso (bpm)"]])

# ==========================================
# MÓDULO 2: AUTO-REGULATION ENGINE (PRESCRIÇÃO)
# ==========================================
elif page == "🏋️ Auto-Regulation Engine (Prescrição)":
    st.title("🏋️ Auto-Regulation Engine")
    st.caption("Ajuste automático de volume, intensidade e seleção de exercícios.")

    fatigue_score = 0
    if data['hrv_status'] in ["UNBALANCED", "LOW"]: fatigue_score += 3
    if isinstance(data['sleep'][0], (int, float)) and data['sleep'][0] < 60: fatigue_score += 2
    if isinstance(data['rhr'][0], (int, float)) and isinstance(data['rhr'][3], (int, float)) and data['rhr'][0] >= data['rhr'][3] + 4: fatigue_score += 2

    fatigue_level = "ELEVADA" if fatigue_score >= 4 else ("MODERADA" if fatigue_score >= 2 else "BAIXA")

    if fatigue_level == "ELEVADA": st.error(f"⚠️ **Fadiga Fisiológica ELEVADA** — Redução de carga axial recomendada.")
    elif fatigue_level == "MODERADA": st.warning(f"⚡ **Fadiga Fisiológica MODERADA** — Manter volume, limitar RPE.")
    else: st.success(f"✅ **Fadiga Fisiológica BAIXA** — Capacidade total para alta intensidade.")

    c_cat, c_env, c_time = st.columns(3)
    category = c_cat.selectbox("Modalidade Planeada:", ["Musculação / Full Body C", "Ciclismo / Cycling", "Corrida / Running", "Natação / Swimming", "Triatlo / Brick Workout"])
    env = c_env.radio("Ambiente:", ["Outdoor (Rua/Estrada)", "Indoor (Rolo/Passadeira)"])
    avail_time = c_time.slider("Tempo Disponível (min):", 30, 240, 75, 15)

    st.markdown("---")
    st.subheader(f"📋 Prescrição Otimizada: **{category}** ({avail_time} min)")

    if "Full Body C" in category:
        full_body_c = [
            {"num": "1", "name": "Dumbbell Bulgarian Split Squat", "type": "unilateral", "sets": 3, "reps": "8–10 / leg", "rpe": "8–9"},
            {"num": "2", "name": "Dumbbell Romanian Deadlift (RDL)", "type": "spinal_load", "sets": 3, "reps": "10–12", "rpe": "8–9"},
            {"num": "3", "name": "Cable Lat Pulldown", "type": "upper", "sets": 3, "reps": "10–12", "rpe": "8–9"},
            {"num": "4", "name": "Incline Dumbbell Chest Press", "type": "upper", "sets": 3, "reps": "10–12", "rpe": "8–9"}
        ]
        for ex in full_body_c:
            if fatigue_level == "ELEVADA":
                if ex["type"] == "spinal_load": st.warning(f"**{ex['num']}. {ex['name']}** ➔ 🔄 **TROCAR POR CADEIRA FLEXORA** (Proteger Coluna)")
                elif ex["type"] == "unilateral": st.warning(f"**{ex['num']}. {ex['name']}** ➔ 🔄 **TROCAR POR CADEIRA EXTENSORA**")
                else: st.info(f"**{ex['num']}. {ex['name']}** | 2 séries x {ex['reps']} @ RPE 7")
            else: st.success(f"**{ex['num']}. {ex['name']}** | {ex['sets']} séries x {ex['reps']} @ RPE {ex['rpe']}")

    elif "Corrida" in category:
        if fatigue_level == "ELEVADA": st.warning(f"🏃 **Ajuste de Corrida:** {min(avail_time, 40)} min em Zona 1 / Caminhada Ativa.")
        else: st.success(f"🏃 **Sessão Principal:** {avail_time} min Zona 2 Aeróbica com 4x100m Acelerações Progressivas.")

# ==========================================
# MÓDULO 3: TRAINING LOAD ANALYTICS (CTL/ATL)
# ==========================================
elif page == "📊 Training Load Analytics (Matriz CTL/ATL)":
    st.title("📊 Training Load Analytics (CTL / ATL / TSB)")
    st.caption("Gestão de carga de treino acumulada (Modelo Banister / Impulse-Response).")

    st.subheader("💡 Estado de Forma & Tapering (TSB)")
    col_t1, col_t2, col_t3 = st.columns(3)
    col_t1.metric("CTL (Fitness Acumulado)", "68 pts", "+2.4 esta semana")
    col_t2.metric("ATL (Fadiga Aguda)", "82 pts", "+5.1 esta semana")
    col_t3.metric("TSB (Forma / Frescura)", "-14 pts", "Zona de Acumulação")

    st.divider()
    if not data["df_history"].empty:
        st.subheader("📈 Estimativa da Matriz de Carga")
        st.line_chart(data["df_history"][["VRC Noturno (ms)", "Body Battery Peak"]])

# ==========================================
# MÓDULO 4: SLEEP ARCHITECTURE & RECOVERY
# ==========================================
elif page == "😴 Sleep Architecture & Recovery":
    st.title("😴 Sleep Architecture & Recovery")
    st.caption("Decomposição das fases de sono e métricas noturnas.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pontuação de Sono", f"{data['sleep'][0]} /100")
    c2.metric("Sono Profundo", format_seconds_to_hhmm(data['deep_sleep_today']))
    c3.metric("Sono REM", format_seconds_to_hhmm(data['rem_sleep_today']))
    c4.metric("Sono Leve", format_seconds_to_hhmm(data['light_sleep_today']))

    st.divider()
    st.subheader("🌙 Biomarcadores Fisiológicos Noturnos")
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("VRC Noturno", f"{data['hrv'][0]} ms" if data['hrv'][0] != 'N/A' else "N/A")
    col_s2.metric("FC Repouso Noturna", f"{data['rhr'][0]} bpm" if data['rhr'][0] != 'N/A' else "N/A")
    col_s3.metric("Freq. Respiratória", f"{data['resp'][0]} brpm" if data['resp'][0] != 'N/A' else "N/A")
    col_s4.metric("Tempo Acordado", format_seconds_to_hhmm(data['awake_today']))

    st.divider()
    if not data["df_history"].empty:
        st.line_chart(data["df_history"][["Pontuação Sono", "VRC Noturno (ms)"]])

# ==========================================
# MÓDULO 5: METABOLIC HEALTH & COMPOSITION
# ==========================================
elif page == "🥗 Metabolic Health & Composition":
    st.title("🥗 Metabolic Health & Composition")
    st.caption("Bioimpedância Garmin Index S2 e cálculo de macronutrientes.")

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
        st.subheader("🔥 Calculadora de Macronutrientes Adaptativa")
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
        cn2.metric("Proteína Target", f"{protein_g} g")
        cn3.metric("Hidratos de Carbono", f"{carbs_g} g")
        cn4.metric("Gorduras Saudáveis", f"{fat_g} g")

        st.divider()
        selected_m = st.multiselect("Métricas a cruzar:", options=list(df_body.columns), default=["Gordura Corporal (%)", "Massa Muscular (kg)"])
        if selected_m: st.line_chart(df_body[selected_m])
    else: st.info("ℹ️ Efetue o login para consultar o histórico da balança Garmin Index S2.")

# ==========================================
# MÓDULO 6: BIOMARCADORES DE LONGEVIDADE (VO2/RHR)
# ==========================================
elif page == "🧬 Biomarcadores de Longevidade (VO2/RHR)":
    st.title("🧬 Biomarcadores de Longevidade & Healthspan")
    st.caption("Acompanhamento das métricas associadas à saúde cardiovascular de longo prazo.")

    l1, l2, l3 = st.columns(3)
    l1.metric("VO2 Máximo Estimado", f"{st.session_state.get('user_vo2max', 62)} mL/kg/min", "+1.2 no ano")
    l2.metric("Frequência Cardíaca de Repouso", f"{data['rhr'][0]} bpm" if data['rhr'][0] != 'N/A' else "N/A")
    l3.metric("Idade Fisiológica Estimada", f"{max(18, st.session_state.get('user_age', 24) - 5)} Anos", "-5 vs Cronológica")

    st.divider()
    st.subheader("📌 Indicadores de Saúde Cardiovascular (Evolução)")
    if not data["df_history"].empty:
        st.line_chart(data["df_history"][["FC Repouso (bpm)", "VRC Noturno (ms)"]])

# ==========================================
# MÓDULO 7: ENGINE DE FORÇA & CARGA AXIAL
# ==========================================
elif page == "🧱 Engine de Força & Carga Axial":
    st.title("🧱 Engine de Força & Carga Axial")
    st.caption("Monitorização de sobrecarga progressiva e preservação de densidade óssea/muscular.")

    st.subheader("🏋️ Cargas Máximas Registadas (Exercícios Base)")
    f1, f2, f3 = st.columns(3)
    f1.metric("Agachamento / Leg Press", "140 kg", "3x8 reps")
    f2.metric("Romanian Deadlift (RDL)", "110 kg", "3x10 reps")
    f3.metric("Bulgarian Split Squat", "28 kg / leg", "3x8 reps")

# ==========================================
# MÓDULO 8: RACE HUB & PACING MATRIX
# ==========================================
elif page == "🎯 Race Hub & Pacing Matrix":
    st.title("🎯 Race Hub & Pacing Matrix")
    st.caption("Estratégia de prova, pacing por quilómetro e contagem decrescente.")

    now = datetime.now()
    sorted_events = sorted(st.session_state.user_events, key=lambda x: x["date"])

    if sorted_events:
        next_event = sorted_events[0]
        event_dt = datetime.combine(next_event["date"], datetime.min.time())
        delta = event_dt - now
        
        st.markdown(f"""
        <div class="metric-card-exec" style="border: 2px solid #10B981;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="badge-status" style="background:rgba(16,185,129,0.2); color:#10B981;">PRÓXIMO DESAFIO PRINCIPAL</span>
                <span style="color:#94A3B8; font-size:0.85rem;">Categoria: {next_event.get('category', 'Geral')}</span>
            </div>
            <div style="color:#F8FAFC; font-size:2rem; font-weight:900; margin:8px 0;">🏆 {next_event['name']}</div>
            <div style="color:#10B981; font-size:1.8rem; font-weight:800;">{max(0, delta.days)} Dias : {max(0, delta.seconds // 3600)} Horas : {max(0, (delta.seconds % 3600) // 60)} Minutos</div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("⏱️ Pacing Calculator (Estimador de Ritmo Alvo)")
    col_p1, col_p2 = st.columns(2)
    dist_km = col_p1.number_input("Distância da Prova (km):", min_value=1.0, max_value=226.0, value=21.1)
    target_time_min = col_p2.number_input("Tempo Alvo (minutos):", min_value=10, max_value=1200, value=105)

    if dist_km > 0 and target_time_min > 0:
        pace_sec = (target_time_min * 60) / dist_km
        pace_min = int(pace_sec // 60)
        pace_rem_sec = int(pace_sec % 60)
        speed_kmh = round(dist_km / (target_time_min / 60.0), 2)
        st.info(f"🎯 **Pacing Alvo Exigido:** **{pace_min}:{pace_rem_sec:02d} min/km** | Velocidade Média: **{speed_kmh} km/h**")

    st.divider()
    st.subheader("📅 Cronograma Completo de Provas")
    for ev in sorted_events:
        col1, col2, col3 = st.columns([3, 2, 2])
        col1.markdown(f"**📌 {ev['name']}** ({ev.get('category', 'Geral')})")
        col2.caption(f"🗓️ {ev['date'].strftime('%d/%m/%Y')}")
        col3.markdown(f"⏱️ **{(datetime.combine(ev['date'], datetime.min.time()) - now).days} dias restantes**")
        st.divider()

# ==========================================
# MÓDULO 9: HISTÓRICO ACUMULADO DE TREINOS
# ==========================================
elif page == "📜 Histórico Acumulado de Treinos":
    st.title("📜 Histórico Acumulado de Treinos")
    st.caption("Consolidado de atividades registadas na nuvem Garmin.")

    c_d1, c_d2 = st.columns(2)
    start_d = c_d1.date_input("Data Inicial", value=date.today() - timedelta(days=30))
    end_d = c_d2.date_input("Data Final", value=date.today())

    sport_filter = st.multiselect("Modalidades:", ["Corrida", "Ciclismo", "Natação", "Musculação / Ginásio"], default=["Corrida", "Ciclismo", "Natação", "Musculação / Ginásio"])

    if st.session_state.garmin_logged_in:
        try:
            with st.spinner("A consultar histórico de atividades..."):
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
                else: st.info("Nenhuma atividade encontrada para os filtros selecionados.")
        except Exception as e: st.error(f"Erro ao obter atividades: {e}")
    else: st.info("ℹ️ Efetue o login na barra lateral para carregar o histórico de atividades.")

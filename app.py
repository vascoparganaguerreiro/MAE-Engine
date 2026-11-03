import streamlit as st
from datetime import date, timedelta, datetime
from garminconnect import Garmin
import pandas as pd
import google.generativeai as genai

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(page_title="Garmin Auto-Regulation Engine", layout="wide", initial_sidebar_state="expanded")

# ==========================================
# SESSÃO & AUTENTICAÇÃO GARMIN MULTI-UTILIZADOR
# ==========================================
if "garmin_logged_in" not in st.session_state:
    st.session_state.garmin_logged_in = False
if "garmin_email" not in st.session_state:
    st.session_state.garmin_email = "Vascoparganaguerreiro@gmail.com"
if "garmin_pass" not in st.session_state:
    st.session_state.garmin_pass = "Vasco1234"

# ==========================================
# NAVEGAÇÃO & BARRA LATERAL
# ==========================================
st.sidebar.title("📌 Navegação")

# Painel de Login / Conta Garmin
with st.sidebar.expander("👤 Sessão Garmin (Login)", expanded=not st.session_state.garmin_logged_in):
    if not st.session_state.garmin_logged_in:
        input_email = st.text_input("E-mail Garmin", value=st.session_state.garmin_email, key="login_email_input")
        input_password = st.text_input("Password Garmin", type="password", value=st.session_state.garmin_pass, key="login_pass_input")
        if st.button("🔑 Entrar / Sincronizar", use_container_width=True):
            try:
                with st.spinner("A autenticar na nuvem Garmin..."):
                    client = Garmin(input_email, input_password)
                    client.login()
                    st.session_state.garmin_email = input_email
                    st.session_state.garmin_pass = input_password
                    st.session_state.garmin_logged_in = True
                    st.cache_data.clear()
                    st.success("Sessão iniciada com sucesso!")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro ao autenticar: {e}")
    else:
        st.success(f"Conectado como:\n**{st.session_state.garmin_email}**")
        if st.button("🚪 Terminar Sessão", use_container_width=True):
            st.session_state.garmin_logged_in = False
            st.cache_data.clear()
            st.rerun()

page = st.sidebar.radio(
    "Ir para:",
    [
        "📊 Dashboard Fisiológico",
        "🎯 Goals & Eventos",
        "😴 Sono & Recuperação Avançada",
        "⚖️ Composição Corporal & Peso",
        "📜 Histórico de Treinos & Análise"
    ]
)

st.sidebar.markdown("---")
lang = st.sidebar.selectbox("🌐 Idioma / Language", ["Português", "English"])

# Inicialização dos eventos padrão na sessão
if "user_events" not in st.session_state:
    st.session_state.user_events = [
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15)},
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4)},
        {"name": "Triatlo Olímpico", "date": date(2027, 9, 12)},
        {"name": "IRONMAN 70.3 Cascais", "date": date(2027, 10, 17)}
    ]

TEXTS = {
    "Português": {
        "title": "📊 Painel Fisiológico & Main Details",
        "subtitle": "Visão geral multivariável resumida com os principais indicadores de prontidão, recuperação e composição.",
        "sync_btn": "🔄 Sincronizar Dados",
        "fetching": "A consultar a nuvem Garmin e a processar biomarcadores...",
        "training_readiness": "Prontidão de Treino",
        "hrv_status": "Estado do VRC (HRV)",
        "bb_current": "Body Battery Atual",
        "table_title": "📋 Resumo Comparativo de Recuperação (14d)",
        "metrics": ["Pontuação de Sono", "VRC Noturno (ms)", "Body Battery (Pico)", "FC Repouso (bpm)", "Stress Diário", "Frequência Respiratória (brpm)"],
        "cols": ["Métrica", "Hoje", "Média 3d", "Média 7d", "Média 14d"],
        "charts_title": "📈 Tendências Históricas Fisiológicas (14 Dias)",
        "tabs": ["VRC (HRV) & Sono", "FC Repouso & Stress", "Body Battery (Pico)"],
        "presc_title": "🏋️ Prescrição Adaptativa Rápida"
    },
    "English": {
        "title": "📊 Physiological Dashboard & Main Details",
        "subtitle": "Summarized multivariable overview featuring key readiness, recovery, and composition metrics.",
        "sync_btn": "🔄 Synchronize Data",
        "fetching": "Fetching Garmin Cloud data and processing biomarkers...",
        "training_readiness": "Training Readiness",
        "hrv_status": "HRV Status",
        "bb_current": "Current Body Battery",
        "table_title": "📋 Recovery Comparison Summary (14d)",
        "metrics": ["Sleep Score", "Overnight HRV (ms)", "Body Battery (Peak)", "Resting HR (bpm)", "Daily Stress", "Respiration Rate (brpm)"],
        "cols": ["Metric", "Today", "3-Day Avg", "7-Day Avg", "14-Day Avg"],
        "charts_title": "📈 Physiological Trend Curves (Last 14 Days)",
        "tabs": ["HRV & Sleep", "Resting HR & Stress", "Body Battery (Peak)"],
        "presc_title": "🏋️ Quick Adaptive Prescription"
    }
}
t = TEXTS[lang]

def calculate_avg(values):
    valid_values = [v for v in values if isinstance(v, (int, float))]
    if not valid_values:
        return "N/A"
    return round(sum(valid_values) / len(valid_values), 1)

# ==========================================
# FUNÇÃO CENTRAL DE EXTRAÇÃO GARMIN (CACHE)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_garmin_data_user(email, password):
    client = Garmin(email, password)
    client.login()
    
    today = date.today()
    sleep_hist, hrv_hist, bb_peak_hist, rhr_hist, stress_hist, resp_hist = [], [], [], [], [], []
    dates_list = []
    body_records = []

    # 1. Indicadores Fisiológicos dos Últimos 14 Dias
    for days_back in range(13, -1, -1):
        current_date_obj = today - timedelta(days=days_back)
        current_date = current_date_obj.strftime("%Y-%m-%d")
        dates_list.append(current_date_obj.strftime("%d/%m"))
        
        try:
            sleep_data = client.get_sleep_data(current_date)
            sleep_hist.append(sleep_data.get("dailySleepDTO", {}).get("sleepScores", {}).get("overall", {}).get("value"))
        except Exception:
            sleep_hist.append(None)

        try:
            hrv_data = client.get_hrv_data(current_date)
            hrv_hist.append(hrv_data.get("hrvSummary", {}).get("lastNightAvg"))
        except Exception:
            hrv_hist.append(None)

        try:
            summary = client.get_user_summary(current_date)
            bb_high = summary.get("bodyBatteryHighestValue") if isinstance(summary, dict) else None
            if bb_high is None:
                bb_data = client.get_body_battery(current_date)
                vals = []
                if isinstance(bb_data, list):
                    for entry in bb_data:
                        if isinstance(entry, dict):
                            arr = entry.get("bodyBatteryValuesArray") or entry.get("bodyBatteryValues") or []
                            if isinstance(arr, list):
                                for pt in arr:
                                    val = pt[1] if isinstance(pt, (list, tuple)) and len(pt) > 1 else (pt.get("value") if isinstance(pt, dict) else None)
                                    if val is not None and isinstance(val, (int, float)):
                                        vals.append(val)
                            else:
                                val = entry.get("bodyBatteryLevel") or entry.get("bodyBatteryValue") or entry.get("value")
                                if val is not None and isinstance(val, (int, float)):
                                    vals.append(val)
                bb_high = max(vals) if vals else None
            bb_peak_hist.append(bb_high)
        except Exception:
            bb_peak_hist.append(None)
            
        try:
            stats = client.get_user_summary(current_date)
            rhr_hist.append(stats.get("restingHeartRate"))
        except Exception:
            rhr_hist.append(None)

        try:
            stats = client.get_user_summary(current_date)
            stress_val = stats.get("averageStressLevel")
            if stress_val is None or stress_val == -1:
                stress_data = client.get_stress_data(current_date)
                stress_val = stress_data.get("averageStressLevel")
            stress_hist.append(stress_val if isinstance(stress_val, (int, float)) and stress_val >= 0 else None)
        except Exception:
            stress_hist.append(None)

        try:
            resp_data = client.get_respiration_data(current_date)
            resp_val = resp_data.get("avgWakingRespirationValue") or resp_data.get("avgSleepRespirationValue")
            if resp_val is None:
                sleep_raw = client.get_sleep_data(current_date)
                resp_val = sleep_raw.get("dailySleepDTO", {}).get("averageRespirationValue")
            resp_hist.append(resp_val)
        except Exception:
            resp_hist.append(None)

    today_str = today.strftime("%Y-%m-%d")
    hrv_status_str = "BALANCED"
    try:
        hrv_status_str = client.get_hrv_data(today_str).get("hrvSummary", {}).get("status", "BALANCED")
    except Exception:
        pass

    bb_current = None
    try:
        summary_today = client.get_user_summary(today_str)
        if isinstance(summary_today, dict):
            bb_current = summary_today.get("bodyBatteryMostRecentValue") or summary_today.get("bodyBatteryLevel")
    except Exception:
        pass

    training_readiness = "N/A"
    try:
        readiness = client.get_training_readiness(today_str)
        if isinstance(readiness, list) and readiness:
            item = readiness[0] if isinstance(readiness[0], dict) else readiness[-1]
            training_readiness = item.get("score") or item.get("scoreValue") or item.get("value", "N/A")
        elif isinstance(readiness, dict):
            training_readiness = readiness.get("score") or readiness.get("scoreValue") or readiness.get("value", "N/A")
    except Exception:
        pass

    # 2. Histórico da Balança Index S2
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
                    else:
                        dt_str = str(raw_date)[:10]
                
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
    except Exception:
        pass

    sleep_rev, hrv_rev, bb_peak_rev = sleep_hist[::-1], hrv_hist[::-1], bb_peak_hist[::-1]
    rhr_rev, stress_rev, resp_rev = rhr_hist[::-1], stress_hist[::-1], resp_hist[::-1]

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
        "df_history": df_history,
        "body_records": body_records
    }

# Execução do carregamento dinâmico
if st.session_state.garmin_logged_in:
    with st.spinner(t["fetching"]):
        data = fetch_garmin_data_user(st.session_state.garmin_email, st.session_state.garmin_pass)
else:
    data = {
        "hrv_status": "N/A", "bb_current": "N/A", "training_readiness": "N/A",
        "sleep": ["N/A"]*4, "hrv": ["N/A"]*4, "bb_peak": ["N/A"]*4,
        "rhr": ["N/A"]*4, "stress": ["N/A"]*4, "resp": ["N/A"]*4,
        "df_history": pd.DataFrame(), "body_records": []
    }

# ==========================================
# ASSISTENTE IA GEMINI (LATERAL)
# ==========================================
st.sidebar.markdown("---")
with st.sidebar.expander("🤖 Assistente IA Gemini", expanded=False):
    st.caption("Consulte a IA sobre a sua recuperação e treinos.")
    api_key_input = st.text_input("Chave API Gemini:", type="password", help="Chave API do Google AI Studio.")
    user_query = st.text_area("A sua pergunta:", placeholder="Ex: Devo treinar forte hoje com base nos meus biomarcadores?")
    
    if st.button("💬 Perguntar ao Gemini", use_container_width=True):
        if not api_key_input:
            st.error("Por favor introduza a chave API Gemini.")
        elif not user_query:
            st.warning("Escreva a sua dúvida.")
        else:
            try:
                genai.configure(api_key=api_key_input)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                contexto = f"""
                Atua como um Fisiologista Desportivo e Treinador.
                Utilizador: {st.session_state.garmin_email}
                Prontidão de Treino: {data['training_readiness']}
                Estado VRC: {data['hrv_status']}
                Body Battery: {data['bb_current']}
                Sono Hoje: {data['sleep'][0]}
                Composição Corporal Recente: {data['body_records'][-1] if data['body_records'] else 'Sem registo'}
                """
                prompt = f"{contexto}\n\nPergunta: {user_query}"
                
                with st.spinner("A consultar Gemini..."):
                    response = model.generate_content(prompt)
                    st.markdown("### 💡 Resposta IA:")
                    st.write(response.text)
            except Exception as e:
                st.error(f"Erro: {e}")

# ==========================================
# PÁGINA 2: GOALS & EVENTOS
# ==========================================
if page == "🎯 Goals & Eventos":
    st.title("🎯 Central de Eventos & Objetivos")
    st.markdown("Gestão cronológica de provas alvo com contagem decrescente em tempo real.")
    
    body_goal_options = [
        "Hipertrofia Estética (V-Taper & Densidade)",
        "Força Pura & Potência Relativa",
        "Manutenção / Recomposição Corporal",
        "Performance Puro Endurecimento (Triatlo)"
    ]
    
    if "body_goal" not in st.session_state:
        st.session_state.body_goal = body_goal_options[0]
        
    st.session_state.body_goal = st.selectbox(
        "💪 Objetivo Corporal Principal:",
        options=body_goal_options,
        index=body_goal_options.index(st.session_state.body_goal) if st.session_state.body_goal in body_goal_options else 0
    )
    
    st.markdown("---")
    now = datetime.now()
    sorted_events = sorted(st.session_state.user_events, key=lambda x: x["date"])

    if sorted_events:
        next_event = sorted_events[0]
        event_dt = datetime.combine(next_event["date"], datetime.min.time())
        delta = event_dt - now
        days_left = max(0, delta.days)
        hours_left = max(0, delta.seconds // 3600)
        minutes_left = max(0, (delta.seconds % 3600) // 60)

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1E222B 0%, #111827 100%); border-radius: 16px; padding: 26px; border: 2px solid #10B981; margin-bottom: 24px;">
            <div style="color: #10B981; font-size: 0.85rem; font-weight: 800; text-transform: uppercase;">PRÓXIMO DESAFIO PRINCIPAL</div>
            <div style="color: #FFFFFF; font-size: 2.2rem; font-weight: 900; margin: 6px 0;">🏆 {next_event['name']}</div>
            <div style="color: #9CA3AF; font-size: 0.95rem; margin-bottom: 18px;">📅 {next_event['date'].strftime('%d/%m/%Y')}</div>
            <div style="display: flex; gap: 16px;">
                <div style="background-color: rgba(16, 185, 129, 0.15); padding: 10px 22px; border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <span style="color: #10B981; font-size: 1.8rem; font-weight: 900;">{days_left}</span>
                    <span style="color: #9CA3AF; font-size: 0.85rem; margin-left: 4px;">Dias</span>
                </div>
                <div style="background-color: rgba(16, 185, 129, 0.15); padding: 10px 22px; border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <span style="color: #10B981; font-size: 1.8rem; font-weight: 900;">{hours_left}</span>
                    <span style="color: #9CA3AF; font-size: 0.85rem; margin-left: 4px;">Horas</span>
                </div>
                <div style="background-color: rgba(16, 185, 129, 0.15); padding: 10px 22px; border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <span style="color: #10B981; font-size: 1.8rem; font-weight: 900;">{minutes_left}</span>
                    <span style="color: #9CA3AF; font-size: 0.85rem; margin-left: 4px;">Minutos</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("📅 Cronograma Completo de Provas")
    for ev in sorted_events:
        event_dt = datetime.combine(ev["date"], datetime.min.time())
        delta_ev = event_dt - now
        d_left = max(0, delta_ev.days)
        h_left = max(0, delta_ev.seconds // 3600)
        m_left = max(0, (delta_ev.seconds % 3600) // 60)
        
        col_n, col_d, col_t = st.columns([3, 2, 2])
        col_n.markdown(f"**📌 {ev['name']}**")
        col_d.caption(f"🗓️ {ev['date'].strftime('%d/%m/%Y')}")
        col_t.markdown(f"⏱️ **{d_left}d {h_left}h {m_left}m restantes**")
        st.divider()

    with st.expander("⚙️ Gerir Lista de Eventos (Adicionar / Eliminar)"):
        if len(st.session_state.user_events) < 15:
            if st.button("➕ Adicionar Novo Evento", use_container_width=True):
                st.session_state.user_events.append({"name": f"Novo Evento {len(st.session_state.user_events)+1}", "date": date.today() + timedelta(days=90)})
                st.rerun()

        events_to_remove = []
        for idx, ev in enumerate(st.session_state.user_events):
            c1, c2, c3 = st.columns([3, 2, 1])
            st.session_state.user_events[idx]["name"] = c1.text_input(f"Nome #{idx+1}", value=ev["name"], key=f"g_name_{idx}")
            st.session_state.user_events[idx]["date"] = c2.date_input(f"Data #{idx+1}", value=ev["date"], key=f"g_date_{idx}")
            if c3.button("🗑️", key=f"g_del_{idx}"):
                events_to_remove.append(idx)
        
        if events_to_remove:
            for idx in sorted(events_to_remove, reverse=True):
                st.session_state.user_events.pop(idx)
            st.rerun()
    st.stop()

# ==========================================
# PÁGINA 3: SONO & RECUPERAÇÃO AVANÇADA
# ==========================================
if page == "😴 Sono & Recuperação Avançada":
    st.title("😴 Sono & Recuperação Avançada")
    st.markdown("Análise da arquitetura do sono e métricas noturnas da Garmin.")
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sono Total (Hoje)", f"{data['sleep'][0] if data['sleep'][0] != 'N/A' else '--'} /100")
    c2.metric("Média 3 Dias", f"{data['sleep'][1]}")
    c3.metric("Média 7 Dias", f"{data['sleep'][2]}")
    c4.metric("Média 14 Dias", f"{data['sleep'][3]}")
    
    st.info("💡 A integração detalhada das fases individuais de sono via Garmin Connect será renderizada aqui.")
    st.stop()

# ==========================================
# PÁGINA 4: COMPOSIÇÃO CORPORAL & PESO
# ==========================================
if page == "⚖️ Composição Corporal & Peso":
    st.title("⚖️ Composição Corporal & Peso (Garmin Index S2)")
    st.markdown("Acompanhamento interativo da bioimpedância e tendências de composição corporal.")
    
    records = data.get("body_records", [])
    
    if records:
        df_body = pd.DataFrame(records).sort_values("Data").set_index("Data")
        latest = df_body.iloc[-1]
        prev = df_body.iloc[-2] if len(df_body) > 1 else latest

        c1, c2, c3, c4 = st.columns(4)
        w_delta = round(latest['Peso (kg)'] - prev['Peso (kg)'], 1) if len(df_body) > 1 else None
        c1.metric("Peso Atual", f"{latest['Peso (kg)']} kg", f"{w_delta} kg" if w_delta is not None else None)
        
        fat_val = f"{latest['Gordura Corporal (%)']}%" if pd.notnull(latest['Gordura Corporal (%)']) else "N/A"
        fat_delta = f"{round(latest['Gordura Corporal (%)'] - prev['Gordura Corporal (%)'], 1)}%" if len(df_body) > 1 and pd.notnull(latest['Gordura Corporal (%)']) else None
        c2.metric("% Gordura", fat_val, fat_delta)
        
        musc_val = f"{latest['Massa Muscular (kg)']} kg" if pd.notnull(latest['Massa Muscular (kg)']) else "N/A"
        musc_delta = f"{round(latest['Massa Muscular (kg)'] - prev['Massa Muscular (kg)'], 1)} kg" if len(df_body) > 1 and pd.notnull(latest['Massa Muscular (kg)']) else None
        c3.metric("Massa Muscular", musc_val, musc_delta)
        
        water_val = f"{latest['Água Corporal (%)']}%" if pd.notnull(latest['Água Corporal (%)']) else "N/A"
        c4.metric("Água Corporal", water_val)

        st.divider()
        st.subheader("📈 Análise de Tendências Personalizada")
        st.caption("Seleciona os parâmetros que pretendes comparar em simultâneo.")

        available_metrics = list(df_body.columns)
        selected_metrics = st.multiselect(
            "Métricas a exibir no gráfico:",
            options=available_metrics,
            default=["Gordura Corporal (%)", "Massa Muscular (kg)"] if "Gordura Corporal (%)" in available_metrics else available_metrics[:2]
        )

        if selected_metrics:
            st.line_chart(df_body[selected_metrics])
        else:
            st.warning("Selecione pelo menos uma métrica para exibir o gráfico.")

        st.divider()
        st.subheader("📋 Histórico Registado da Balança Index S2")
        st.dataframe(df_body, use_container_width=True)
    else:
        st.info("ℹ️ Efetue o login na barra lateral para consultar o histórico da balança Garmin Index S2.")
    st.stop()

# ==========================================
# PÁGINA 5: HISTÓRICO DE TREINOS & ANÁLISE
# ==========================================
if page == "📜 Histórico de Treinos & Análise":
    st.title("📜 Histórico de Treinos & Análise Acumulada")
    st.markdown("Filtre as suas sessões passadas da Garmin por datas e consulte volumes acumulados por modalidade.")
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_d = st.date_input("Data Inicial", value=date.today() - timedelta(days=30))
    with col_d2:
        end_d = st.date_input("Data Final", value=date.today())
        
    sport_filter = st.multiselect(
        "Filtrar por Modalidade:",
        ["Corrida", "Ciclismo", "Natação", "Musculação / Ginásio"],
        default=["Corrida", "Ciclismo", "Natação", "Musculação / Ginásio"]
    )
    
    if st.session_state.garmin_logged_in:
        try:
            with st.spinner("A consultar histórico de atividades na nuvem Garmin..."):
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
                        dist_km = round(act.get("distance", 0) / 1000.0, 2)
                        duration_min = round(act.get("duration", 0) / 60.0, 1)
                        calories = act.get("calories", 0)
                        act_date = str(act.get("startTimeLocal", ""))[:10]
                        act_name = act.get("activityName", "Sessão")
                        
                        parsed_act.append({
                            "Data": act_date,
                            "Nome": act_name,
                            "Modalidade": cat,
                            "Distância (km)": dist_km,
                            "Duração (min)": duration_min,
                            "Calorias (kcal)": calories
                        })
                
                if parsed_act:
                    df_act = pd.DataFrame(parsed_act)
                    
                    total_dist = round(df_act["Distância (km)"].sum(), 1)
                    total_time_h = round(df_act["Duração (min)"].sum() / 60.0, 1)
                    total_cal = int(df_act["Calorias (kcal)"].sum())
                    total_count = len(df_act)
                    
                    st.subheader("📊 Totais Acumulados no Período Selecionado")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Volume Total", f"{total_dist} km")
                    m2.metric("Tempo Acumulado", f"{total_time_h} horas")
                    m3.metric("Calorias Gastas", f"{total_cal} kcal")
                    m4.metric("Total de Treinos", f"{total_count} sessões")
                    
                    st.divider()
                    st.subheader("📋 Lista de Atividades Filtradas")
                    st.dataframe(df_act, use_container_width=True)
                else:
                    st.info("ℹ️ Nenhuma atividade encontrada para os filtros e datas selecionadas.")
        except Exception as e:
            st.error(f"Erro ao obter atividades da Garmin: {e}")
    else:
        st.info("ℹ️ Efetue o login na barra lateral para carregar o seu histórico completo de treinos da Garmin.")
    st.stop()

# ==========================================
# PÁGINA 1: DASHBOARD FISIOLÓGICO DA GARMIN (PADRÃO)
# ==========================================
st.markdown("""
<style>
.header-title-container { display: flex; flex-direction: column; }
.header-title { font-size: 1.8rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.02em; margin: 0; display: flex; align-items: center; gap: 10px; }
.header-subtitle { font-size: 0.88rem; color: #9CA3AF; margin-top: 4px; font-weight: 400; margin-bottom: 12px; }
.status-badge { background-color: rgba(16, 185, 129, 0.15); color: #10B981; font-size: 0.72rem; font-weight: 600; padding: 3px 10px; border-radius: 20px; border: 1px solid rgba(16, 185, 129, 0.3); letter-spacing: 0.04em; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

col_header_left, col_header_right = st.columns([3, 1], vertical_alignment="center")

with col_header_left:
    st.markdown(f"""
    <div class="header-title-container">
        <div class="header-title">
            Painel Fisiológico & Main Details
            <span class="status-badge">● Garmin Sync</span>
        </div>
        <div class="header-subtitle">{t['subtitle']}</div>
    </div>
    """, unsafe_allow_html=True)

with col_header_right:
    if st.button(t["sync_btn"], use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("""
<style>
.metric-card { background-color: #1E222B; border-radius: 12px; padding: 18px 20px; border-left: 4px solid #3B82F6; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); margin-bottom: 20px; }
.metric-card.readiness { border-left-color: #10B981; }
.metric-card.hrv { border-left-color: #8B5CF6; }
.metric-card.battery { border-left-color: #06B6D4; }
.metric-label { font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #9CA3AF; margin-bottom: 6px; }
.metric-value { font-size: 2.1rem; font-weight: 700; color: #FFFFFF; line-height: 1.1; }
.metric-sub { font-size: 0.78rem; color: #6B7280; margin-top: 4px; }
</style>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"""
    <div class="metric-card readiness">
        <div class="metric-label">⚡ {t['training_readiness']}</div>
        <div class="metric-value">{data['training_readiness']} <span style="font-size: 1.1rem; color: #6B7280;">/100</span></div>
        <div class="metric-sub">Capacidade de Carga Hoje</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card hrv">
        <div class="metric-label">🫀 {t['hrv_status']}</div>
        <div class="metric-value" style="font-size: 1.7rem;">{data['hrv_status']}</div>
        <div class="metric-sub">Equilíbrio Autonómico</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card battery">
        <div class="metric-label">🔋 {t['bb_current']}</div>
        <div class="metric-value">{data['bb_current']} <span style="font-size: 1.1rem; color: #6B7280;">/100</span></div>
        <div class="metric-sub">Reserva de Energia em Tempo Real</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

if not data["df_history"].empty:
    st.subheader(t["table_title"])
    df_metrics = pd.DataFrame({
        t["cols"][0]: t["metrics"],
        t["cols"][1]: [data['sleep'][0], data['hrv'][0], data['bb_peak'][0], data['rhr'][0], data['stress'][0], data['resp'][0]],
        t["cols"][2]: [data['sleep'][1], data['hrv'][1], data['bb_peak'][1], data['rhr'][1], data['stress'][1], data['resp'][1]],
        t["cols"][3]: [data['sleep'][2], data['hrv'][2], data['bb_peak'][2], data['rhr'][2], data['stress'][2], data['resp'][2]],
        t["cols"][4]: [data['sleep'][3], data['hrv'][3], data['bb_peak'][3], data['rhr'][3], data['stress'][3], data['resp'][3]],
    })
    st.dataframe(df_metrics, use_container_width=True, hide_index=True)

    st.subheader(t["charts_title"])
    tab1, tab2, tab3 = st.tabs(t["tabs"])
    with tab1:
        st.line_chart(data["df_history"][["HRV / VRC (ms)", "Sleep / Sono"]])
    with tab2:
        st.line_chart(data["df_history"][["RHR / FC Repouso (bpm)", "Stress"]])
    with tab3:
        st.line_chart(data["df_history"][["Body Battery Peak"]])
else:
    st.info("ℹ️ Efetue a sincronização na barra lateral para visualizar as curvas fisiológicas.")

import streamlit as st
from datetime import date, timedelta, datetime
from garminconnect import Garmin
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Garmin Auto-Regulation Engine", layout="wide")

# ==========================================
# NAVEGAÇÃO & IDIOMA (BARRA LATERAL)
# ==========================================
st.sidebar.title("📌 Navegação")
page = st.sidebar.radio("Ir para:", ["📊 Dashboard Fisiológico", "🎯 Goals & Eventos"])

st.sidebar.markdown("---")
lang = st.sidebar.selectbox("🌐 Select Language / Selecionar Língua", ["Português", "English"])

# Inicialização dos 4 eventos padrão na sessão
if "user_events" not in st.session_state:
    st.session_state.user_events = [
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15)},
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4)},
        {"name": "Triatlo Olímpico", "date": date(2027, 9, 12)},
        {"name": "IRONMAN 70.3 Cascais", "date": date(2027, 10, 17)}
    ]

# Seletor do Objetivo Corporal
st.sidebar.markdown("---")
body_goal = st.sidebar.selectbox(
    "Objetivo Corporal Principal:",
    [
        "Hipertrofia Estética (V-Taper & Densidade)",
        "Força Pura & Potência Relativa",
        "Manutenção / Recomposição Corporal",
        "Performance Puro Endurecimento (Triatlo)"
    ]
)

TEXTS = {
    "Português": {
        "title": "📊 Painel Fisiológico & Auto-Regulação de Treino",
        "subtitle": "Análise multivariável em tempo real cruzando a recuperação atual com linhas de tendência de 3d, 7d e 14d.",
        "sync_btn": "🔄 Synchronize Garmin",
        "fetching": "A consultar a nuvem Garmin e a processar tendências de 14 dias...",
        "training_readiness": "Prontidão de Treino",
        "hrv_status": "Estado do VRC (HRV)",
        "bb_current": "Body Battery Atual",
        "table_title": "📋 Tabela Comparativa de Recuperação & Tendência",
        "metrics": ["Pontuação de Sono", "VRC Noturno (ms)", "Body Battery (Pico)", "FC Repouso (bpm)", "Stress Diário", "Frequência Respiratória (brpm)"],
        "cols": ["Métrica", "Hoje", "Média 3 Dias", "Média 7 Dias", "Média 14 Dias"],
        "charts_title": "📈 Curvas de Tendência Histórica (Últimos 14 Dias)",
        "tabs": ["VRC (HRV) & Sono", "FC Repouso & Stress", "Body Battery (Pico)"],
        "presc_title": "🏋️ Prescrição & Auto-Regulação Adaptativa",
        "fatigue_high": "⚠️ **Nível de Fadiga: ELEVADA**",
        "fatigue_mod": "⚡ **Nível de Fadiga: MODERADA**",
        "fatigue_low": "✅ **Nível de Fadiga: BAIXA**",
        "risk_score": "Pontuação de Risco",
        "factors": "Fatores detetados",
        "workout_type": "Tipo de Modalidade:",
        "environment": "Ambiente / Clima:",
        "indoor": "Indoor (Rolo / Passadeira / Mau Tempo)",
        "outdoor": "Outdoor (Rua / Estrada)",
        "time_avail": "Tempo Disponível Hoje (minutos):",
        "presc_for": "Sessão Adaptada",
        "reasons_map": {
            "hrv_unbalanced": "VRC desequilibrado/baixo",
            "hrv_drop": "VRC em queda aguda (3d vs 14d > 10%)",
            "sleep_deficit": "Défice acumulado de sono (Média 3d < 65)",
            "rhr_high": "FC de Repouso elevada (≥4 bpm vs linha de base 14d)",
            "bb_low": "Body Battery em nível crítico"
        }
    },
    "English": {
        "title": "📊 Physiological Dashboard & Workout Auto-Regulation",
        "subtitle": "Real-time multivariable analysis crossing current recovery with 3d, 7d, and 14d trendlines.",
        "sync_btn": "🔄 Synchronize Garmin",
        "fetching": "Fetching Garmin Cloud data and processing 14-day trends...",
        "training_readiness": "Training Readiness",
        "hrv_status": "HRV Status",
        "bb_current": "Current Body Battery",
        "table_title": "📋 Recovery & Trend Comparison Table",
        "metrics": ["Sleep Score", "Overnight HRV (ms)", "Body Battery (Peak)", "Resting HR (bpm)", "Daily Stress", "Respiration Rate (brpm)"],
        "cols": ["Metric", "Today", "3-Day Avg", "7-Day Avg", "14-Day Avg"],
        "charts_title": "📈 Historical Trend Curves (Last 14 Days)",
        "tabs": ["HRV & Sleep", "Resting HR & Stress", "Body Battery (Peak)"],
        "presc_title": "🏋️ Adaptive Prescription & Auto-Regulation",
        "fatigue_high": "⚠️ **Fatigue Level: HIGH**",
        "fatigue_mod": "⚡ **Fatigue Level: MODERATE**",
        "fatigue_low": "✅ **Fatigue Level: LOW**",
        "risk_score": "Risk Score",
        "factors": "Detected factors",
        "workout_type": "Workout Type:",
        "environment": "Environment / Weather:",
        "indoor": "Indoor (Trainer / Treadmill / Bad Weather)",
        "outdoor": "Outdoor (Road / Outside)",
        "time_avail": "Time Available Today (minutes):",
        "presc_for": "Adapted Session",
        "reasons_map": {
            "hrv_unbalanced": "HRV unbalanced/low",
            "hrv_drop": "Acute HRV drop (3d vs 14d > 10%)",
            "sleep_deficit": "Accumulated sleep deficit (3d Avg < 65)",
            "rhr_high": "Elevated Resting HR (≥4 bpm vs 14d baseline)",
            "bb_low": "Body Battery at critical level"
        }
    }
}

t = TEXTS[lang]
# ==========================================
# PÁGINA 2: GOALS & EVENTOS DEDICADA
# ==========================================
if page == "🎯 Goals & Eventos":
    st.title("🎯 Central de Eventos & Objetivos")
    st.markdown("Gestão cronológica de provas alvo com contagem decrescente em tempo real.")
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

        # Cartão Destaque Gigante do Próximo Evento (com Minutos)
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1E222B 0%, #111827 100%); border-radius: 16px; padding: 26px; border: 2px solid #10B981; margin-bottom: 24px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3);">
            <div style="color: #10B981; font-size: 0.85rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.08em;">PRÓXIMO DESAFIO PRINCIPAL</div>
            <div style="color: #FFFFFF; font-size: 2.2rem; font-weight: 900; margin: 6px 0;">🏆 {next_event['name']}</div>
            <div style="color: #9CA3AF; font-size: 0.95rem; margin-bottom: 18px;">📅 {next_event['date'].strftime('%d/%m/%Y')}</div>
            <div style="display: flex; gap: 16px;">
                <div style="background-color: rgba(16, 185, 129, 0.15); padding: 10px 22px; border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <span style="color: #10B981; font-size: 1.8rem; font-weight: 900;">{days_left}</span>
                    <span style="color: #9CA3AF; font-size: 0.85rem; font-weight: 600; margin-left: 4px;">Dias</span>
                </div>
                <div style="background-color: rgba(16, 185, 129, 0.15); padding: 10px 22px; border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <span style="color: #10B981; font-size: 1.8rem; font-weight: 900;">{hours_left}</span>
                    <span style="color: #9CA3AF; font-size: 0.85rem; font-weight: 600; margin-left: 4px;">Horas</span>
                </div>
                <div style="background-color: rgba(16, 185, 129, 0.15); padding: 10px 22px; border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3);">
                    <span style="color: #10B981; font-size: 1.8rem; font-weight: 900;">{minutes_left}</span>
                    <span style="color: #9CA3AF; font-size: 0.85rem; font-weight: 600; margin-left: 4px;">Minutos</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Lista Cronológica de Eventos Futuros (com Dias, Horas e Minutos)
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
    # Painel para Adicionar/Editar Eventos (Até 15)
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


# --- CABEÇALHO PREMIUM ---
st.markdown("""
<style>
.header-title-container {
    display: flex;
    flex-direction: column;
}
.header-title {
    font-size: 1.8rem;
    font-weight: 800;
    color: #FFFFFF;
    letter-spacing: -0.02em;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 10px;
}
.header-subtitle {
    font-size: 0.88rem;
    color: #9CA3AF;
    margin-top: 4px;
    font-weight: 400;
    margin-bottom: 12px;
}
.status-badge {
    background-color: rgba(16, 185, 129, 0.15);
    color: #10B981;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    border: 1px solid rgba(16, 185, 129, 0.3);
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
</style>
""", unsafe_allow_html=True)

col_header_left, col_header_right = st.columns([3, 1], vertical_alignment="center")

with col_header_left:
    st.markdown(f"""
    <div class="header-title-container">
        <div class="header-title">
            Painel Fisiológico & Auto-Regulação
            <span class="status-badge">● Garmin Sync</span>
        </div>
        <div class="header-subtitle">{t['subtitle']}</div>
    </div>
    """, unsafe_allow_html=True)

with col_header_right:
    sync_pressed = st.button(t["sync_btn"], use_container_width=True)

EMAIL = "Vascoparganaguerreiro@gmail.com"
PASSWORD = "Vasco1234"

def calculate_avg(values):
    valid_values = [v for v in values if isinstance(v, (int, float))]
    if not valid_values:
        return "N/A"
    return round(sum(valid_values) / len(valid_values), 1)

@st.cache_data(ttl=3600)
def fetch_garmin_data():
    client = Garmin(EMAIL, PASSWORD)
    client.login()
    
    today = date.today()
    sleep_hist, hrv_hist, bb_peak_hist, rhr_hist, stress_hist, resp_hist = [], [], [], [], [], []
    dates_list = []

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
           # 1. Tenta extrair o pico direto do resumo diário da Garmin
            summary = client.get_user_summary(current_date)
            bb_high = summary.get("bodyBatteryHighestValue") if isinstance(summary, dict) else None
        
            # 2. Se não encontrou no summary, varre os arrays do dia
            if bb_high is None:
                bb_data = client.get_body_battery(current_date)
                vals = []
                if isinstance(bb_data, list):
                    for entry in bb_data:
                        if isinstance(entry, dict):
                            # A Garmin costuma aninhar os pontos dentro de bodyBatteryValuesArray
                            arr = entry.get("bodyBatteryValuesArray") or entry.get("bodyBatteryValues") or []
                            if isinstance(arr, list):
                                for pt in arr:
                                    # pt costuma ser [timestamp, val] ou um dict com o valor
                                    val = pt[1] if isinstance(pt, (list, tuple)) and len(pt) > 1 else (pt.get("value") if isinstance(pt, dict) else None)
                                    if val is not None and isinstance(val, (int, float)):
                                        vals.append(val)
                            else:
                                # Caso os pontos estejam na raiz do dicionário
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
        "df_history": df_history
    }

if sync_pressed:
    st.cache_data.clear()

with st.spinner(t["fetching"]):
    data = fetch_garmin_data()

# --- CARTOES DE TOPO ESTILIZADOS ---
st.markdown("""
<style>
.metric-card {
    background-color: #1E222B;
    border-radius: 12px;
    padding: 18px 20px;
    border-left: 4px solid #3B82F6;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
    margin-bottom: 20px;
}
.metric-card.readiness {
    border-left-color: #10B981;
}
.metric-card.hrv {
    border-left-color: #8B5CF6;
}
.metric-card.battery {
    border-left-color: #06B6D4;
}
.metric-label {
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9CA3AF;
    margin-bottom: 6px;
}
.metric-value {
    font-size: 2.1rem;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.1;
}
.metric-sub {
    font-size: 0.78rem;
    color: #6B7280;
    margin-top: 4px;
}
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

st.subheader(t["table_title"])
df_metrics = pd.DataFrame({
    t["cols"][0]: t["metrics"],
    t["cols"][1]: [data['sleep'][0], data['hrv'][0], data['bb_peak'][0], data['rhr'][0], data['stress'][0], data['resp'][0]],
    t["cols"][2]: [data['sleep'][1], data['hrv'][1], data['bb_peak'][1], data['rhr'][1], data['stress'][1], data['resp'][1]],
    t["cols"][3]: [data['sleep'][2], data['hrv'][2], data['bb_peak'][2], data['rhr'][2], data['stress'][2], data['resp'][2]],
    t["cols"][4]: [data['sleep'][3], data['hrv'][3], data['bb_peak'][3], data['rhr'][3], data['stress'][3], data['resp'][3]],
})
st.dataframe(df_metrics, use_container_width=True)

st.subheader(t["charts_title"])
tab1, tab2, tab3 = st.tabs(t["tabs"])
with tab1:
    st.line_chart(data["df_history"][["HRV / VRC (ms)", "Sleep / Sono"]])
with tab2:
    st.line_chart(data["df_history"][["RHR / FC Repouso (bpm)", "Stress"]])
with tab3:
    st.line_chart(data["df_history"][["Body Battery Peak"]])

st.divider()

# Lógica de Fadiga
fatigue_points = 0
reasons_keys = []

if data['hrv_status'] in ["UNBALANCED", "LOW"]:
    fatigue_points += 3
    reasons_keys.append("hrv_unbalanced")
elif isinstance(data['hrv'][1], (int, float)) and isinstance(data['hrv'][3], (int, float)) and data['hrv'][1] < data['hrv'][3] * 0.90:
    fatigue_points += 2
    reasons_keys.append("hrv_drop")

if isinstance(data['sleep'][1], (int, float)) and data['sleep'][1] < 65:
    fatigue_points += 2
    reasons_keys.append("sleep_deficit")

if isinstance(data['rhr'][0], (int, float)) and isinstance(data['rhr'][3], (int, float)) and data['rhr'][0] >= data['rhr'][3] + 4:
    fatigue_points += 2
    reasons_keys.append("rhr_high")

if data['bb_current'] < 35:
    fatigue_points += 2
    reasons_keys.append("bb_low")

fatigue_level = "ELEVADA" if fatigue_points >= 5 else ("MODERADA" if fatigue_points >= 2 else "BAIXA")

st.subheader(t["presc_title"])

if fatigue_level == "ELEVADA":
    st.error(f"{t['fatigue_high']} ({t['risk_score']}: {fatigue_points})")
elif fatigue_level == "MODERADA":
    st.warning(f"{t['fatigue_mod']} ({t['risk_score']}: {fatigue_points})")
else:
    st.success(f"{t['fatigue_low']} ({t['risk_score']}: {fatigue_points})")

if reasons_keys:
    mapped_reasons = [t["reasons_map"][k] for k in reasons_keys]
    st.caption(f"{t['factors']}: " + " | ".join(mapped_reasons))

col_cat, col_env, col_time = st.columns(3)

with col_cat:
    category = st.selectbox(
        t["workout_type"],
        ["Ginásio / Full Body C (Coach Plan)", "Ciclismo / Cycling", "Corrida / Running", "Natação / Swimming", "Brick Workout (Triatlo)"]
    )

with col_env:
    env = st.radio(t["environment"], [t["indoor"], t["outdoor"]])

with col_time:
    avail_time = st.slider(t["time_avail"], min_value=30, max_value=300, value=75, step=15)

st.markdown("---")

st.write(f"### 📋 {t['presc_for']}: **{category}** ({avail_time} min)")

if "Full Body C" in category:
    st.info("🏋️ **Full Body C (Hypertrophy & Tri Performance)**")
    st.caption("🎯 *Foco:* Hipertrofia Estética (V-Taper/Dorsais, Ombros, Braços) + Potência Posterior e Estabilidade Unilateral para Ciclismo/Corrida.")
    
    full_body_c = [
        {
            "num": "1",
            "name_pt": "Dumbbell Bulgarian Split Squat",
            "name_en": "Dumbbell Bulgarian Split Squat",
            "type": "unilateral",
            "sets": 3,
            "reps": "8–10 / per leg",
            "rest": "90s",
            "rpe_target": "8–9",
            "why_pt": "Força unilateral sem carga axial na coluna; corrige assimetrias da bike.",
            "why_en": "Unilateral strength without axial spinal load; fixes cycling imbalances."
        },
        {
            "num": "2",
            "name_pt": "Dumbbell Roman Chair / Romanian Deadlift (RDL)",
            "name_en": "Dumbbell Romanian Deadlift (RDL)",
            "type": "spinal_load",
            "sets": 3,
            "reps": "10–12",
            "rest": "2 min",
            "rpe_target": "8–9",
            "why_pt": "Cadeia posterior (isquiotibiais/glúteos) para potência no sprint e suporte lombar na posição aero (TT).",
            "why_en": "Posterior chain (hamstrings/glutes) for sprint power and aero TT lower back support."
        },
        {
            "num": "3",
            "name_pt": "Cable Lat Pulldown (Neutral / Wide Grip)",
            "name_en": "Cable Lat Pulldown (Neutral / Wide Grip)",
            "type": "upper",
            "sets": 3,
            "reps": "10–12",
            "rest": "90s",
            "rpe_target": "8–9",
            "why_pt": "Motor primário da puxada na natação (1.9km) + estético V-Taper.",
            "why_en": "Primary swim catch-and-pull engine + aesthetic V-Taper."
        },
        {
            "num": "4",
            "name_pt": "Incline Dumbbell Chest Press (30° Incline)",
            "name_en": "Incline Dumbbell Chest Press (30° Incline)",
            "type": "upper",
            "sets": 3,
            "reps": "10–12",
            "rest": "90s",
            "rpe_target": "8–9",
            "why_pt": "Preenchimento do peitoral superior; protege ombros para natação.",
            "why_en": "Upper chest fill; protects shoulders for swimming."
        },
        {
            "num": "5",
            "name_pt": "Standing Dumbbell Lateral Raise",
            "name_en": "Standing Dumbbell Lateral Raise",
            "type": "upper",
            "sets": 4,
            "reps": "12–15",
            "rest": "60s",
            "rpe_target": "8–9",
            "why_pt": "Largura de ombros + suporte do tronco na posição aerodinâmica (TT).",
            "why_en": "Shoulder width + upper body support in TT position."
        },
        {
            "num": "6",
            "name_pt": "Superset Braços: Cable Rope Overhead Triceps Ext. + DB Incline Biceps Curl",
            "name_en": "Arm Superset: Cable Rope Overhead Triceps Ext. + DB Incline Biceps Curl",
            "type": "arms",
            "sets": 3,
            "reps": "12–15 / 10–12",
            "rest": "60s pós-par",
            "rpe_target": "8–9",
            "why_pt": "Hipertrofia de braços + saúde dos tendões do cotovelo para natação.",
            "why_en": "Arm hypertrophy + elbow tendon health for swimming."
        }
    ]

    for ex in full_body_c:
        name = ex["name_pt"] if lang == "Português" else ex["name_en"]
        why = ex["why_pt"] if lang == "Português" else ex["why_en"]
        
        if fatigue_level == "ELEVADA":
            adj_sets = max(2, ex["sets"] - 1)
            if ex["type"] == "spinal_load":
                st.warning(f"**{ex['num']}. {name}** ➔ 🔄 **TROCAR POR MÁQUINA (Leg Press / Cadeira Flexora)**\n"
                           f"• Prescrição Adaptada: **{adj_sets} séries x {ex['reps']} reps @ RPE 7** (Proteger Coluna e SNC)\n"
                           f"• *Objetivo:* {why}")
            elif ex["type"] == "unilateral":
                st.warning(f"**{ex['num']}. {name}** ➔ 🔄 **TROCAR POR CADEIRA EXTENSORA**\n"
                           f"• Prescrição Adaptada: **{adj_sets} séries x 12 reps @ RPE 7**\n"
                           f"• *Objetivo:* {why}")
            else:
                st.info(f"**{ex['num']}. {name}**\n"
                        f"• Prescrição Adaptada: **{adj_sets} séries x {ex['reps']} reps @ RPE 7** (Volume -25%, RPE reduzido)\n"
                        f"• *Objetivo:* {why}")
        elif fatigue_level == "MODERADA":
            st.info(f"**{ex['num']}. {name}**\n"
                    f"• Prescrição Adaptada: **{ex['sets']} séries x {ex['reps']} reps @ RPE 7.5** (Manter volume, limitar RPE para evitar falha)\n"
                    f"• Rest: {ex['rest']} | *Objetivo:* {why}")
        else:
            st.success(f"**{ex['num']}. {name}**\n"
                       f"• Prescrição Original do Treinador: **{ex['sets']} séries x {ex['reps']} reps @ RPE {ex['rpe_target']}**\n"
                       f"• Rest: {ex['rest']} | *Objetivo:* {why}")

    st.markdown("---")
    st.caption("🥤 **Nutrição Pós-Treino Recomendada:** Consumir batido/refeição sólida até 45 min pós-treino com **35–45g de Proteína** + **60–80g de Hidratos de Carbono rápidos**.")

elif "Ciclismo" in category:
    if "Indoor" in env:
        st.info("🚴 **Sessão no Smart Trainer / Rolo (Tacx)**")
        if fatigue_level == "ELEVADA":
            st.warning(f"• **Volume Adaptado:** {min(avail_time, 60)} min em Zona 1 / Recuperação Ativa (RPE 4).")
        elif fatigue_level == "MODERADA":
            st.info(f"• **Volume Adaptado:** {min(avail_time, 75)} min em Zona 2 Aeróbica (RPE 5.5 - 6).")
        else:
            st.success(f"• **Volume Completo:** {avail_time} min (Z2 com 3x10 min SST / Tempo @ RPE 7.5).")
    else:
        st.info("🚴‍♂️ **Sessão de Ciclismo Outdoor / Estrada**")
        st.success(f"• **Volume Prescrito:** {avail_time} min em Estrada (Zona 2 / RPE 6).")

elif "Corrida" in category:
    st.info("🏃 **Sessão de Corrida**")
    if fatigue_level == "ELEVADA":
        st.warning(f"• **Adaptação:** {min(avail_time, 40)} min Corrida Z1 / Caminhada Ativa (RPE 4 - 5).")
    elif fatigue_level == "MODERADA":
        st.info(f"• **Adaptação:** {min(avail_time, 50)} min Zona 2 Contínua (RPE 6).")
    else:
        st.success(f"• **Sessão Principal:** {avail_time} min (Séries Z4 ou Tempo Run conforme plano).")

elif "Natação" in category:
    st.info("🏊 **Sessão de Natação em Piscina**")
    if fatigue_level == "ELEVADA":
        st.warning(f"• **Adaptação:** Max {min(avail_time, 45)} min (1500m Z1 leve, técnica e soltura).")
    else:
        st.success(f"• **Sessão Principal:** {avail_time} min (Bloco técnico + Séries de ritmo Z2/Z3).")

elif "Brick" in category:
    st.info("🧱 **Sessão Transição (Ciclismo + Corrida)**")
    bike_t = int(avail_time * 0.7)
    run_t = int(avail_time * 0.3)
    st.success(f"• **Sessão:** {bike_t} min Ciclismo Z2/Z3 ➔ Transição (T2) ➔ {run_t} min Corrida Z2.")

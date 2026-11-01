import streamlit as st
from datetime import date, timedelta
from garminconnect import Garmin
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Garmin Auto-Regulation Engine", layout="wide")

# ==========================================
# SELETOR DE IDIOMA (BARRA LATERAL)
# ==========================================
lang = st.sidebar.selectbox("🌐 Select Language / Selecionar Língua", ["Português", "English"])

TEXTS = {
    "Português": {
        "title": "📊 Painel Fisiológico & Auto-Regulação de Treino",
        "subtitle": "Análise multivariável em tempo real cruzando a recuperação atual com linhas de tendência de 3d, 7d e 14d.",
        "sync_btn": "🔄 Sincronizar Fisiologia com Garmin Connect",
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
        "sync_btn": "🔄 Sync Physiology with Garmin Connect",
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
st.title(t["title"])
st.markdown(t["subtitle"])

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
            bb_data = client.get_body_battery(current_date)
            vals = [item.get("bodyBatteryValue", item.get("value", item.get("bodyBatteryLevel", 0))) for item in (bb_data or []) if isinstance(item, dict)]
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
            resp_hist.append(resp_data.get("avgWakingRespirationValue"))
        except Exception:
            resp_hist.append(None)

    today_str = today.strftime("%Y-%m-%d")
    hrv_status_str = "BALANCED"
    try:
        hrv_status_str = client.get_hrv_data(today_str).get("hrvSummary", {}).get("status", "BALANCED")
    except Exception:
        pass

    bb_current = 50
    try:
        bb_today = client.get_body_battery(today_str)
        if bb_today:
            bb_current = bb_today[-1].get("charged", 50)
    except Exception:
        pass

    training_readiness = "N/A"
    try:
        readiness = client.get_training_readiness(today_str)
        training_readiness = readiness[-1].get("score", "N/A") if isinstance(readiness, list) and readiness else readiness.get("score", "N/A")
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

if st.button(t["sync_btn"]):
    st.cache_data.clear()

with st.spinner(t["fetching"]):
    data = fetch_garmin_data()

col1, col2, col3 = st.columns(3)
col1.metric(t["training_readiness"], f"{data['training_readiness']}/100")
col2.metric(t["hrv_status"], data['hrv_status'])
col3.metric(t["bb_current"], f"{data['bb_current']}/100")

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

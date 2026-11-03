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
    DataQualityEngine, compute_zscore_readiness, compute_sleep_debt_7d,
    calculate_trend_slope, compute_banister_ctl_atl_tsb, simulate_taper_projection,
    calculate_dynamic_sweat_nutrition, generate_pacing_band, calculate_carb_loading_protocol
)

# ==========================================
# PAGE CONFIG & EXECUTIVE DARK THEME
# ==========================================
st.set_page_config(
    page_title="Apex Engine | Race Hub Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp {
        background-color: #0B0F17;
        color: #E2E8F0;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Executive Card Elements */
    .hero-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid #1E293B;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
    }
    
    .metric-card {
        background: #131A27;
        border-radius: 12px;
        padding: 18px 22px;
        border: 1px solid #1E293B;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    .metric-title {
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94A3B8;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 900;
        color: #F8FAFC;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: #64748B;
        margin-top: 2px;
    }

    /* Professional Countdown Timer Display */
    .timer-container {
        display: flex;
        justify-content: space-around;
        background: linear-gradient(180deg, #131A27 0%, #0B0F17 100%);
        border: 1px solid #1E293B;
        border-radius: 16px;
        padding: 22px;
        margin: 20px 0;
        box-shadow: inset 0 2px 4px rgba(255,255,255,0.02);
    }
    .timer-block {
        text-align: center;
    }
    .timer-number {
        font-size: 3.0rem;
        font-weight: 900;
        color: #3B82F6;
        font-family: 'SF Pro Display', -apple-system, monospace;
        text-shadow: 0 0 16px rgba(59, 130, 246, 0.4);
    }
    .timer-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        color: #64748B;
        font-weight: 800;
        letter-spacing: 0.12em;
    }
    
    .badge-a { background: rgba(239, 68, 68, 0.2); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.4); padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 0.75rem; }
    .badge-b { background: rgba(245, 158, 11, 0.2); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.4); padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 0.75rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SESSION STATE & DEFAULT DATA
# ==========================================
if "user_weight" not in st.session_state: st.session_state.user_weight = 75.0
if "user_bf_pct" not in st.session_state: st.session_state.user_bf_pct = 12.0
if "user_gender" not in st.session_state: st.session_state.user_gender = "Masculino"
if "user_hr_max" not in st.session_state: st.session_state.user_hr_max = 192

if "races" not in st.session_state:
    st.session_state.races = [
        {"id": "r1", "name": "IRONMAN 70.3 Cascais", "date": date(2027, 10, 17), "dist_km": 113.0, "priority": "A", "type": "Half Ironman / 70.3", "temp_c": 24.0, "hum_pct": 65.0, "target_pace": 4.45},
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "dist_km": 21.1, "priority": "A", "type": "10K / Meia Maratona (21k)", "temp_c": 11.0, "hum_pct": 50.0, "target_pace": 4.15},
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "dist_km": 10.0, "priority": "B", "type": "10K / Meia Maratona (21k)", "temp_c": 14.0, "hum_pct": 70.0, "target_pace": 3.55}
    ]

# Shoe mileage tracking storage
if "shoes" not in st.session_state:
    st.session_state.shoes = [
        {"model": "Adidas Adizero Adios Pro 4", "km_used": 142.0, "max_km": 250.0, "status": "Excelente 🟢"},
        {"model": "ASICS Superblast 2", "km_used": 380.0, "max_km": 600.0, "status": "Bom 🟢"},
        {"model": "Nike Vaporfly Next% 2", "km_used": 265.0, "max_km": 250.0, "status": "Degradação de Espuma ⚠️"}
    ]

# Post race debrief storage
if "debriefs" not in st.session_state:
    st.session_state.debriefs = []

# Generate 60-Day Banister Dataset
np.random.seed(42)
today = date.today()
dates = [today - timedelta(days=i) for i in range(59, -1, -1)]
loads = [0.0 if i % 7 == 0 else (160.0 if i % 5 == 0 else 90.0) for i in range(60)]
ctl_vals, atl_vals, tsb_vals = compute_banister_ctl_atl_tsb(loads)

# ==========================================
# SIDEBAR CONTROL
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine v4.0**")
st.sidebar.caption("Tactical Race Hub & Execution Engine")

top_nav = st.sidebar.radio(
    "Módulos Principais:",
    [
        "🎯 Race Hub & Coaching Ativo",
        "📊 Banister TSB & Taper Plan",
        "👟 Gestão de Sapatilhas & Equipamento",
        "📌 Dashboard de Prontidão (Today)"
    ]
)

st.sidebar.markdown("---")

with st.sidebar.expander("⚙️ **Fisiologia do Atleta**"):
    st.session_state.user_gender = st.selectbox("Género:", ["Masculino", "Feminino"], index=0)
    st.session_state.user_weight = st.number_input("Peso (kg):", value=75.0, min_value=40.0, max_value=150.0)
    st.session_state.user_bf_pct = st.number_input("Gordura Corporal (%):", value=12.0, min_value=3.0, max_value=40.0)
    st.session_state.user_hr_max = st.number_input("FC Máxima (bpm):", value=192, min_value=140, max_value=220)

# ==========================================
# MODULE 1: RACE HUB & ACTIVE COACHING
# ==========================================
if top_nav == "🎯 Race Hub & Coaching Ativo":
    st.title("🎯 Race Hub & Tactical Coaching Engine")
    st.caption("Planeamento tático de prova, previsão de hidratação por clima e pacing de precisão.")

    # Primary 'A' Race Selection
    a_races = [r for r in st.session_state.races if r["priority"] == "A"]
    primary_race = a_races[0] if a_races else st.session_state.races[0]

    # Countdown Calculation
    today_dt = datetime.now()
    race_dt = datetime.combine(primary_race["date"], datetime.min.time())
    delta_race = race_dt - today_dt

    days = max(0, delta_race.days)
    hours = max(0, delta_race.seconds // 3600)
    minutes = max(0, (delta_race.seconds % 3600) // 60)
    seconds = max(0, delta_race.seconds % 60)

    # 1. Countdown Hero Section
    st.markdown(f"### 🏆 Próximo Objetivo A: **{primary_race['name']}**")
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

    # Feature 3: Carb Loading Protocol Alert (< 72 hours)
    if days <= 3:
        carb_protocol = calculate_carb_loading_protocol(st.session_state.user_weight)
        st.error(f"🚨 **PROTOCOLO DE CARBO-LOADING (72H PRE-PROVA ATIVO):** Prescrição obrigatória de **{carb_protocol['daily_target_g']} de Hidratos de Carbono/dia** para saturação de glicogénio muscular.")
        with st.expander("📋 Distribuição das Refeições do Carbo-Loading"):
            st.write(f"• **Pequeno-Almoço:** {carb_protocol['breakfast']}")
            st.write(f"• **Almoço:** {carb_protocol['lunch']}")
            st.write(f"• **Lanche:** {carb_protocol['snack']}")
            st.write(f"• **Jantar:** {carb_protocol['dinner']}")

    st.divider()

    # 2. Dynamic Sweat Rate & Weather Calculator
    st.subheader("☀️ Calculadora Dinâmica de Suor & Estresse Térmico")
    
    col_w1, col_w2, col_w3 = st.columns(3)
    race_temp = col_w1.slider("Temperatura Prevista (°C):", min_value=5.0, max_value=40.0, value=float(primary_race["temp_c"]))
    race_hum = col_w2.slider("Humidade Relativa (%):", min_value=20.0, max_value=100.0, value=float(primary_race["hum_pct"]))
    est_duration = col_w3.number_input("Duração Estimada (Horas):", min_value=0.5, max_value=17.0, value=4.5)

    nutri = calculate_dynamic_sweat_nutrition(
        weight_kg=st.session_state.user_weight,
        body_fat_pct=st.session_state.user_bf_pct,
        gender=st.session_state.user_gender,
        sport_type=primary_race["type"],
        duration_hours=est_duration,
        temp_c=race_temp,
        humidity_pct=race_hum
    )

    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Hidratação / Água", f"{nutri['fluid_hr_ml']} mL/h", f"Total: {nutri['total_fluid_l']} L")
    n2.metric("Sódio / Eletrólitos", f"{nutri['sodium_hr_mg']} mg/h", f"Total: {nutri['total_sodium_mg']} mg")
    n3.metric("Hidratos de Carbono", f"{nutri['carbs_hr_g']} g/h", f"Total: {nutri['total_carbs_g']} g")
    n4.metric("Estresse Térmico", nutri['thermal_stress_level'], f"Massa Magra: {nutri['lean_mass_kg']} kg")

    st.divider()

    # 3. Pacing Band Generator with GAP
    st.subheader("⏱️ Gerador de Pacing Band & Splits de Terreno (GAP)")
    target_pace_in = st.number_input("Ritmo Alvo Médio (min/km):", min_value=3.0, max_value=8.0, value=float(primary_race["target_pace"]))
    
    pacing_df = generate_pacing_band(target_pace_in, primary_race["dist_km"], st.session_state.user_hr_max)
    st.dataframe(pacing_df.head(10), use_container_width=True)

    st.divider()

    # 4. Coach IA Tactical Race Briefing (Gemini API)
    st.subheader("🤖 Briefing Tático do Coach IA Apex")
    gemini_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)

    if st.button("🎙️ Gerar Briefing Tático de Prova", type="primary", use_container_width=True):
        if not gemini_key:
            st.warning("Adiciona a tua `GEMINI_API_KEY` nos secrets do Streamlit Cloud para gerar o briefing.")
        else:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            És o Coach IA Tático de Medicina Desportiva e de Competição do Apex Engine.
            Gera um briefing tático executivo e direto de no máximo 4 parágrafos para o atleta com os seguintes dados:
            - Prova: {primary_race['name']} ({primary_race['dist_km']} km)
            - Clima: {race_temp}°C, {race_hum}% humidade (Estresse Térmico: {nutri['thermal_stress_level']})
            - Meta Nutricional: {nutri['fluid_hr_ml']} mL/h de água e {nutri['carbs_hr_g']} g/h de HC.
            - Estratégia de Ritmo: Ritmo Alvo {target_pace_in} min/km.
            Gera instruções de prova rígidas e clínicas para início, meio e final do percurso.
            """
            
            with st.spinner("A sintetizar briefing tático com IA..."):
                res = model.generate_content(prompt)
                st.info(res.text)

    st.divider()

    # 5. Post-Race Execution Debrief Form
    with st.expander("📝 **Formulário de Debrief Pós-Prova (Loop de Feedback Fechado)**"):
        with st.form("debrief_form"):
            st.markdown("##### Registo de Execução Real vs Prescrita")
            c_d1, c_d2 = st.columns(2)
            actual_time_str = c_d1.text_input("Tempo Final Real (ex: 4h 22m):")
            actual_carbs_g = c_d2.number_input("Ingestão Real de Hidratos (g/h):", value=65.0)
            
            sub_rpe = st.slider("Perceção Geral de Esforço (RPE 1-10):", 1, 10, 8)
            debrief_notes = st.text_area("Notas de Execução e Sensações:")
            
            if st.form_submit_button("Guadar Debrief Pós-Prova"):
                st.session_state.debriefs.append({
                    "race": primary_race["name"],
                    "time": actual_time_str,
                    "carbs": actual_carbs_g,
                    "rpe": sub_rpe,
                    "notes": debrief_notes
                })
                st.success("Debrief registado com sucesso! Os dados alimentaram a matriz do motor.")

# ==========================================
# MODULE 2: BANISTER TSB & TAPER PLAN
# ==========================================
elif top_nav == "📊 Banister TSB & Taper Plan":
    st.title("📊 Banister TSB & Taper Visualizer")
    st.caption("Projeção do polimento e automação de provas de Prioridade B.")

    # Taper Simulation
    st.subheader("📈 Projeção do Tapering de 14 Dias (Simulação de Polimento)")
    df_taper = simulate_taper_projection(ctl_vals[-1], atl_vals[-1])

    fig_taper = go.Figure()
    fig_taper.add_hrect(y0=10, y1=25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, name="Zona de Polimento Ideal (+10 a +25 TSB)")
    fig_taper.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["CTL_Proj"], name="CTL (Fitness)", line=dict(color='#3B82F6', width=3)))
    fig_taper.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["ATL_Proj"], name="ATL (Fadiga)", line=dict(color='#EF4444', width=2)))
    fig_taper.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["TSB_Proj"], name="TSB (Forma / Frescura)", line=dict(color='#10B981', width=3, dash='dot')))

    fig_taper.update_layout(template="plotly_dark", title="Projeção da Forma Fisiológica até à Manhã da Prova", hovermode="x unified")
    st.plotly_chart(fig_taper, use_container_width=True)

    # Pre-Race Readiness Forecaster
    expected_tsb_race_day = df_taper["TSB_Proj"].iloc[-1]
    expected_readiness = int(min(100, max(0, 50 + (expected_tsb_race_day * 1.5))))
    
    st.metric("Prontidão Prevista na Manhã da Prova:", f"{expected_readiness} / 100", f"Forma (TSB) Estimada: +{expected_tsb_race_day} UA")

    st.divider()

    # B-Race Automations
    st.subheader("📅 Gestão Automática de Provas B / C (Train Through)")
    for r in st.session_state.races:
        if r["priority"] != "A":
            st.warning(f"⚡ **{r['name']}** (Prioridade {r['priority']}) | Status: **Train Through Ativo** — Sem polimento longo. Integrado como treino de limiar/brick de alta qualidade.")

# ==========================================
# MODULE 3: SHOE & GEAR MILEAGE TRACKER
# ==========================================
elif top_nav == "👟 Gestão de Sapatilhas & Equipamento":
    st.title("👟 Rastreador de Desgaste de Sapatilhas de Competição")
    st.caption("Monitorização da resiliência mecânica da espuma de carbono para dia de prova.")

    for shoe in st.session_state.shoes:
        c_s1, c_s2, c_s3 = st.columns([3, 2, 2])
        c_s1.markdown(f"**{shoe['model']}**")
        c_s2.write(f"Quilometragem: **{shoe['km_used']} km** / {shoe['max_km']} km")
        c_s3.write(f"Estado da Espuma: **{shoe['status']}**")
        st.progress(min(1.0, shoe["km_used"] / shoe["max_km"]))

    st.divider()

    with st.form("add_shoe"):
        st.markdown("##### Adicionar Novo Par de Sapatilhas")
        c_in1, c_in2 = st.columns(2)
        sh_model = c_in1.text_input("Modelo da Sapatilha:")
        sh_max = c_in2.number_input("Limite Recomendado (km):", value=250.0)
        if st.form_submit_button("Adicionar Sapatilha"):
            st.session_state.shoes.append({"model": sh_model, "km_used": 0.0, "max_km": sh_max, "status": "Nova 🟢"})
            st.rerun()

# ==========================================
# MODULE 4: TODAY DASHBOARD
# ==========================================
elif top_nav == "📌 Dashboard de Prontidão (Today)":
    st.title("📌 Today / Decisão Diária")
    st.caption("Painel de Controlo Fisiológico Diário")
    st.success("Tudo operacional. Consulta o Race Hub para o teu plano tático completo.")

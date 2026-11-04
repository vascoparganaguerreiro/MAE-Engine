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
    compute_sleep_debt_7d, calculate_trend_slope, autoregulate_strength_workout,
    estimate_1rm, calculate_srpe, compute_foster_load_metrics, compute_acwr,
    compute_banister_ctl_atl_tsb, simulate_taper_projection, get_vo2_percentile,
    calculate_biological_age, predict_race_time, calculate_dynamic_sweat_nutrition,
    generate_pacing_band, calculate_carb_loading_protocol
)

# ==========================================
# PAGE CONFIGURATION & EXECUTIVE THEME
# ==========================================
st.set_page_config(page_title="Apex Engine | Performance & Healthspan", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #0B0F17; color: #E2E8F0; }
    .hero-card-green { background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(6, 78, 59, 0.25) 100%); border-left: 6px solid #10B981; border-radius: 14px; padding: 22px; margin-bottom: 24px; border: 1px solid rgba(16, 185, 129, 0.25); }
    .hero-card-amber { background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(120, 53, 15, 0.25) 100%); border-left: 6px solid #F59E0B; border-radius: 14px; padding: 22px; margin-bottom: 24px; border: 1px solid rgba(245, 158, 11, 0.25); }
    .hero-card-red { background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(127, 29, 29, 0.25) 100%); border-left: 6px solid #EF4444; border-radius: 14px; padding: 22px; margin-bottom: 24px; border: 1px solid rgba(239, 68, 68, 0.25); }
    .kpi-card { background: #131A27; border-radius: 12px; padding: 16px 20px; border: 1px solid #1E293B; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25); }
    .kpi-title { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; color: #94A3B8; }
    .kpi-value { font-size: 2.1rem; font-weight: 900; color: #F8FAFC; }
    .kpi-sub { font-size: 0.8rem; color: #64748B; }
    .timer-container { display: flex; justify-content: space-around; background: linear-gradient(180deg, #131A27 0%, #0B0F17 100%); border: 1px solid #1E293B; border-radius: 16px; padding: 20px; margin: 20px 0; }
    .timer-block { text-align: center; }
    .timer-number { font-size: 2.8rem; font-weight: 900; color: #3B82F6; font-family: 'Courier New', monospace; text-shadow: 0 0 12px rgba(59, 130, 246, 0.5); }
    .timer-label { font-size: 0.75rem; text-transform: uppercase; color: #94A3B8; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
if "garmin_logged_in" not in st.session_state: st.session_state.garmin_logged_in = False
if "garmin_email" not in st.session_state: st.session_state.garmin_email = "Vascoparganaguerreiro@gmail.com"
if "garmin_pass" not in st.session_state: st.session_state.garmin_pass = "Vasco1234"
if "lang" not in st.session_state: st.session_state.lang = "PT"
if "user_mode" not in st.session_state: st.session_state.user_mode = "🏃 Performance (Atleta)"
if "display_window" not in st.session_state: st.session_state.display_window = 14
if "override_train" not in st.session_state: st.session_state.override_train = False

# Profiles
if "user_weight" not in st.session_state: st.session_state.user_weight = 75.0
if "user_bf_pct" not in st.session_state: st.session_state.user_bf_pct = 12.0
if "user_gender" not in st.session_state: st.session_state.user_gender = "Masculino"
if "user_age" not in st.session_state: st.session_state.user_age = 24
if "user_hr_max" not in st.session_state: st.session_state.user_hr_max = 192
if "user_vo2max" not in st.session_state: st.session_state.user_vo2max = 62

if "races" not in st.session_state:
    st.session_state.races = [
        {"name": "Meia Maratona de Berlim", "date": date(2027, 4, 4), "dist_km": 21.1, "priority": "A", "type": "10K / Meia Maratona (21k)"},
        {"name": "10K Prova de Dezembro", "date": date(2026, 12, 15), "dist_km": 10.0, "priority": "B", "type": "10K / Meia Maratona (21k)"}
    ]

if "shoes" not in st.session_state:
    st.session_state.shoes = [{"model": "Adidas Adizero Adios Pro 4", "km_used": 142.0, "max_km": 250.0, "status": "Excelente 🟢"}]

if "debriefs" not in st.session_state: st.session_state.debriefs = []

# ==========================================
# SIDEBAR NAVIGATION
# ==========================================
st.sidebar.markdown("### ⚡ **Apex Engine v4.1**")
st.sidebar.caption("Autoregulation & Tactical Engine")

st.session_state.lang = st.sidebar.selectbox("🌐 Idioma / Language:", ["PT", "EN"], index=0)
st.session_state.user_mode = st.sidebar.radio("Perfil Fisiológico:", ["🏃 Performance (Atleta)", "🧬 Longevidade & Saúde Metabólica"], index=0)

st.sidebar.markdown("---")
st.session_state.display_window = st.sidebar.select_slider("Janela Visual dos Gráficos:", options=[7, 14, 28, 60], value=st.session_state.display_window, format_func=lambda x: f"{x} Dias")

# ==========================================
# GARMIN CONNECTION SIDEBAR BOX
# ==========================================
with st.sidebar.expander("👤 **Estado Conexão Garmin**", expanded=True):
    if st.session_state.garmin_logged_in:
        st.success(f"**Conectado:**\n\n{st.session_state.garmin_email}")
        if st.button("🔑 Sincronizar Agora", use_container_width=True, type="primary"):
            try:
                with st.spinner("A sincronizar dados Garmin..."):
                    client = Garmin(st.session_state.garmin_email, st.session_state.garmin_pass)
                    client.login()
                    st.cache_data.clear()
                    st.success("Dados sincronizados com sucesso!")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro na sincronização: {e}")
        if st.button("🚪 Terminar Sessão", use_container_width=True):
            st.session_state.garmin_logged_in = False
            st.cache_data.clear()
            st.rerun()
    else:
        input_email = st.text_input("E-mail Garmin", value=st.session_state.garmin_email)
        input_password = st.text_input("Password Garmin", type="password", value=st.session_state.garmin_pass)
        if st.button("🔑 Sincronizar", use_container_width=True, type="primary"):
            try:
                with st.spinner("A autenticar na nuvem Garmin..."):
                    client = Garmin(input_email, input_password)
                    client.login()
                    st.session_state.garmin_logged_in = True
                    st.session_state.garmin_email = input_email
                    st.session_state.garmin_pass = input_password
                    st.cache_data.clear()
                    st.success("Conectado!")
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
        "👟 Gestão de Sapatilhas",
        "🤖 Coach IA Apex (Gemini)"
    ]
)
st.sidebar.markdown("---")

with st.sidebar.expander("⚙️ **Fisiologia do Atleta**"):
    st.session_state.user_gender = st.selectbox("Género:", ["Masculino", "Feminino"], index=0 if st.session_state.user_gender=="Masculino" else 1)
    st.session_state.user_age = st.number_input("Idade:", value=st.session_state.user_age)
    st.session_state.user_weight = st.number_input("Peso Corporal (kg):", value=st.session_state.user_weight)
    st.session_state.user_bf_pct = st.number_input("Gordura Corporal (%):", value=st.session_state.user_bf_pct)
    st.session_state.user_vo2max = st.number_input("VO2 Máx:", value=st.session_state.user_vo2max)
    st.session_state.user_hr_max = st.number_input("FC Máxima:", value=st.session_state.user_hr_max)

with st.sidebar.expander("🔬 **Decaimento Banister (Avançado)**"):
    ctl_decay_val = st.slider("Constante CTL (Dias):", 28, 60, 42)
    atl_decay_val = st.slider("Constante ATL (Dias):", 3, 14, 7)

# ==========================================
# PIPELINE DE DADOS (60 DIAS SINTÉTICO/REAL)
# ==========================================
np.random.seed(42)
dates = [date.today() - timedelta(days=i) for i in range(59, -1, -1)]
loads = [0.0 if i % 7 == 0 else (160.0 if i % 5 == 0 else 85.0) for i in range(60)]
df_60d = pd.DataFrame({
    "Date": dates,
    "HRV": np.random.normal(67, 8, 60).tolist(),
    "SleepScore": np.random.normal(75, 10, 60).tolist(),
    "RHR": np.random.normal(48, 3, 60).tolist(),
    "DailyLoad": loads,
    "SleepHours": np.random.normal(7.4, 0.8, 60).tolist()
})

df_60d.loc[59, "HRV"] = 47.0
df_60d.loc[59, "RHR"] = 52.0
df_60d.loc[59, "SleepScore"] = 36.0
df_60d.loc[59, "SleepHours"] = 5.2

hrv_curr, rhr_curr, sleep_curr = df_60d.iloc[-1]["HRV"], df_60d.iloc[-1]["RHR"], df_60d.iloc[-1]["SleepScore"]
hrv_mean_60d, hrv_sd_60d = df_60d["HRV"].mean(), max(df_60d["HRV"].std(), 2.0)
rhr_mean_60d, rhr_sd_60d = df_60d["RHR"].mean(), max(df_60d["RHR"].std(), 1.5)
sleep_mean_60d, sleep_sd_60d = df_60d["SleepScore"].mean(), max(df_60d["SleepScore"].std(), 5.0)

calib_state, calib_label = DataQualityEngine.get_calibration_state(60)
data_conf, conf_reasons = DataQualityEngine.evaluate_sleep_quality(df_60d.iloc[-1]["SleepHours"]*3600, 2400, 3600, 1200)

readiness_data = compute_zscore_readiness(
    hrv_curr, hrv_mean_60d, hrv_sd_60d, rhr_curr, rhr_mean_60d, rhr_sd_60d,
    sleep_curr, sleep_mean_60d, sleep_sd_60d, 80.0, 70.0, 10.0, 4.0, user_mode=st.session_state.user_mode
)
score = readiness_data["readiness_score"]
hrv_context = get_hrv_context(hrv_curr, hrv_mean_60d)
sleep_debt_val = compute_sleep_debt_7d(df_60d["SleepHours"].tolist())
slope_info = calculate_trend_slope(df_60d["HRV"].tail(21).tolist())

df_display = df_60d.tail(st.session_state.display_window).copy()

# ==========================================
# MODULE 1: TODAY / DECISÃO DIÁRIA
# ==========================================
if top_nav == "📌 Today / Decisão Diária":
    with st.expander("📝 **Daily Check-In: Registar Métricas Subjetivas (RPE & Soreness)**", expanded=False):
        c_s1, c_s2, c_s3 = st.columns(3)
        c_s1.slider("Dor Muscular (DOMS):", 1, 5, 2)
        c_s2.slider("Stress Psicológico:", 1, 5, 2)
        c_s3.slider("Motivação / Humor:", 1, 5, 4)
        if st.button("Guardar Entrada Diária", use_container_width=True): st.success("Guardado!")

    col_t1, col_t2 = st.columns([3, 1], vertical_alignment="center")
    with col_t1:
        st.title("📌 Today / Decisão Diária")
        st.caption(f"Painel Executivo | {calib_label} | Modo: {st.session_state.user_mode}")
    with col_t2:
        with st.popover(f"🛡️ Confiança: {data_conf*100:.0f}%"):
            st.write(f"**Confiança:** {data_conf*100:.0f}%")
            if conf_reasons:
                for r in conf_reasons: st.warning(f"• {r}")
            else: st.success("Dados completos.")

    if slope_info["slope"] < -0.15:
        st.error(f"⚠️ **Alerta de Drift:** Tendência descendente no VRC há 3 semanas ({slope_info['slope']} ms/dia). Considera deload.")

    if score >= 70 or st.session_state.override_train: 
        card_class, text = "hero-card-green", "Dia de Treino Normal: Capacidade Total"
    elif score >= 45: 
        card_class, text = "hero-card-amber", "Dia Moderado: Reduzir Carga Axial e Intensidade"
    else: 
        card_class, text = "hero-card-red", "Dia de Recuperação Ativa: Preservar o Sistema Nervoso"

    st.markdown(f"""
    <div class="{card_class}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <span style="font-size: 1.25rem; font-weight: 900;">{text}</span>
            <span style="background: rgba(255,255,255,0.15); padding: 6px 14px; border-radius: 20px; font-weight: 900;">PRONTIDÃO: {score}/100</span>
        </div>
        <div style="font-size: 0.95rem; line-height: 1.6;">
            <b>Diagnóstico Clínico:</b> {hrv_context['explanation']}<br><br>
            • VRC Noturno: <b>{int(hrv_curr)} ms</b> (Média 60d: {int(hrv_mean_60d)} ms)<br>
            • Défice Sono (7d): <b>{sleep_debt_val} h</b><br>
            • FC Repouso: <b>{int(rhr_curr)} bpm</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c_a1, c_a2, c_a3 = st.columns(3)
    if c_a1.button("🧘 Prescrição Mobilidade (20 min)", use_container_width=True, type="primary" if score < 45 else "secondary"):
        st.info("3x60s Rotações Torácicas | 3x90s Abertura Anca 90/90")
    if score < 45:
        c_a2.button("🔄 Modular Treino: Zona 1 Spin", use_container_width=True)
    else:
        c_a2.button("🏃 Zona 2 Aeróbica (45 min)", use_container_width=True, type="primary")
    if c_a3.button("⚠️ Treinar Mesmo Assim (Override)", use_container_width=True):
        st.session_state.override_train = True
        st.rerun()

    st.divider()
    st.subheader("📊 Biomarcadores Diários vs Linha de Base (60 Dias)")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🫀 VRC Noturno", f"{int(hrv_curr)} ms", f"{round(hrv_curr - hrv_mean_60d, 1)} vs 60d")
    k2.metric("❤️ FC Repouso", f"{int(rhr_curr)} bpm", f"{round(rhr_curr - rhr_mean_60d, 1)} vs 60d")
    k3.metric("🛌 Défice Sono (7d)", f"{sleep_debt_val} h", "Meta Diária: 8.0 h")
    k4.metric("🧠 Prontidão Z-Score", f"{readiness_data['z_sum']} σ", "Desvio Acumulado")

    st.divider()
    st.subheader("📊 Decomposição das Contribuições de Prontidão")
    df_waterfall = pd.DataFrame(list(readiness_data["waterfall"].items()), columns=["Fator", "Impacto"])
    fig_w = px.bar(df_waterfall, x="Fator", y="Impacto", color="Impacto", color_continuous_scale="RdYlGn", title="Pesos Z-Score")
    fig_w.update_layout(template="plotly_dark")
    st.plotly_chart(fig_w, use_container_width=True)

# ==========================================
# MODULE 2: TENDÊNCIA DE VRC & GRÁFICOS
# ==========================================
elif top_nav == "📈 Tendência de VRC & Gráficos":
    st.title("📈 Análise Avançada de Tendência do VRC")
    df_chart = df_display.copy()
    df_chart["HRV_EWMA"] = df_chart["HRV"].ewm(span=7, adjust=False).mean()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=[hrv_mean_60d + hrv_sd_60d]*len(df_chart), mode='lines', line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=[max(0, hrv_mean_60d - hrv_sd_60d)]*len(df_chart), mode='lines', line=dict(width=0), fill='tonexty', fillcolor='rgba(16, 185, 129, 0.1)', name="Linha Base (±1 σ)"))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["HRV"], mode='lines+markers', name="VRC Diário (ms)", line=dict(color='#3B82F6', width=2)))
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["HRV_EWMA"], mode='lines', name="Tendência EWMA 7d", line=dict(color='#10B981', width=3, dash='dash')))

    show_rhr = st.checkbox("Sobrepor Frequência Cardíaca de Repouso (RHR)", value=True)
    if show_rhr:
        fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["RHR"], mode='lines', name="FC Repouso (bpm)", yaxis="y2", line=dict(color='#EF4444', width=1.5)))

    fig.update_layout(template="plotly_dark", hovermode="x unified", yaxis=dict(title="VRC (ms)"), yaxis2=dict(title="FC Repouso", overlaying="y", side="right") if show_rhr else None)
    st.plotly_chart(fig, use_container_width=True)
    st.info(f"📈 **Trajetória Autonómica:** {slope_info['text']} ({slope_info['slope']} ms/dia)")

# ==========================================
# MODULE 3: ENGINE DE FORÇA & CARGA AXIAL
# ==========================================
elif top_nav == "🏋️ Engine de Força & Carga Axial":
    st.title("🏋️ Engine de Força & Carga Axial")
    presc = autoregulate_strength_workout(score)
    st.metric("Pontuação de Carga Axial Prescrita:", f"{presc['spinal_score']} / 5.0")
    st.info(f"💡 {presc['note']}")
    
    for ex in presc["workout"]:
        if ex["substituted"]: st.warning(f"🔄 **{ex['exercise']}** | {ex['sets']}x{ex['reps']} @ {ex['intensity']} | Carga: {ex['target_kg']} kg\n*{ex['reason']}*")
        else: st.success(f"✅ **{ex['exercise']}** | {ex['sets']}x{ex['reps']} @ {ex['intensity']} | Carga: {ex['target_kg']} kg")
        st.caption(f"🎯 Músculos: {ex['active_muscles']} | 🛡️ Protege: {ex['joint_protected']}")

    st.divider()
    st.subheader("📝 Registo de Carga Interna (sRPE)")
    c_p1, c_p2 = st.columns(2)
    dur = c_p1.number_input("Duração (min):", value=60)
    rpe = c_p2.slider("RPE Geral da Sessão:", 1, 10, 7)
    st.metric("Carga Interna sRPE:", f"{calculate_srpe(dur, rpe)} UA")

# ==========================================
# MODULE 4: ANALYTICS DE CARGA (BANISTER)
# ==========================================
elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.title("📊 Training Load Analytics (Banister)")
    ctl_vals, atl_vals, tsb_vals = compute_banister_ctl_atl_tsb(df_60d["DailyLoad"].tolist(), ctl_decay_val, atl_decay_val)
    acwr_val = compute_acwr(df_60d["DailyLoad"].tolist())

    c_l1, c_l2, c_l3, c_l4 = st.columns(4)
    c_l1.metric("CTL (Fitness)", f"{ctl_vals[-1]} UA", help="Carga crónica acumulada nas últimas 6 semanas.")
    c_l2.metric("ATL (Fadiga)", f"{atl_vals[-1]} UA", help="Cansaço agudo dos últimos 7 dias.")
    c_l3.metric("TSB (Forma)", f"{tsb_vals[-1]} UA", help="Fitness menos Fadiga. Se positivo, estás fresco.")
    c_l4.metric("Rácio ACWR (Segurança)", f"{acwr_val}", help="Ideal entre 0.8 e 1.3. Acima de 1.5 é risco de lesão.")

    st.divider()
    df_load_disp = df_60d.tail(st.session_state.display_window).copy()
    df_load_disp["CTL"], df_load_disp["ATL"], df_load_disp["TSB"] = ctl_vals[-st.session_state.display_window:], atl_vals[-st.session_state.display_window:], tsb_vals[-st.session_state.display_window:]

    fig_tsb = go.Figure()
    fig_tsb.add_hrect(y0=10, y1=25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, name="Zona de Polimento (Prova)")
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
    pct_str = get_vo2_percentile(st.session_state.user_vo2max, st.session_state.user_age)
    bio_age = calculate_biological_age(st.session_state.user_age, st.session_state.user_vo2max, rhr_mean_60d, hrv_mean_60d)

    h1, h2, h3 = st.columns(3)
    h1.metric("VO2 Máximo", f"{st.session_state.user_vo2max} mL/kg/min", pct_str)
    h2.metric("FC Repouso Média", f"{int(rhr_mean_60d)} bpm", "Faixa Ótima")
    h3.metric("Idade Biológica Estimada", f"{bio_age} Anos", f"Cronológica: {st.session_state.user_age} a")

    st.divider()
    with st.expander("🩸 **Registo de Painel Sanguíneo**"):
        c_b1, c_b2, c_b3 = st.columns(3)
        c_b1.number_input("ApoB (mg/dL):", value=75)
        c_b2.number_input("hs-CRP (mg/L):", value=0.5)
        c_b3.number_input("HbA1c (%):", value=5.1)
        if st.button("Guardar Biomarcadores"): st.success("Guardado!")

# ==========================================
# MODULE 6: RACE HUB & PLANEAMENTO
# ==========================================
elif top_nav == "🎯 Race Hub & Planeamento":
    st.title("🎯 Race Hub & Planeamento Tático")
    
    with st.expander("➕ **Adicionar Nova Prova**", expanded=False):
        with st.form("add_race_form"):
            c_f1, c_f2 = st.columns(2)
            rn = c_f1.text_input("Nome da Prova:")
            rd = c_f2.date_input("Data do Evento:", value=date(2027, 10, 15))
            c_f3, c_f4, c_f5 = st.columns(3)
            rkm = c_f3.number_input("Distância (km):", value=21.1)
            rp = c_f4.selectbox("Prioridade:", ["A (Alvo)", "B (Treino)", "C"])
            rt = c_f5.selectbox("Tipo:", ["Maratona", "Half Ironman", "Full Ironman", "10K / Meia Maratona (21k)"])
            if st.form_submit_button("Guardar Prova") and rn:
                st.session_state.races.append({"name": rn, "date": rd, "dist_km": rkm, "priority": rp[0], "type": rt})
                st.rerun()

    a_races = [r for r in st.session_state.races if r["priority"] == "A"]
    primary = a_races[0] if a_races else st.session_state.races[0]
    
    delta = datetime.combine(primary["date"], datetime.min.time()) - datetime.now()
    st.markdown(f"### 🏆 Próximo Objetivo A: **{primary['name']}**")
    st.markdown(f"""
    <div class="timer-container">
        <div class="timer-block"><div class="timer-number">{max(0, delta.days):02d}</div><div class="timer-label">Dias</div></div>
        <div class="timer-block"><div class="timer-number">{max(0, delta.seconds//3600):02d}</div><div class="timer-label">Horas</div></div>
        <div class="timer-block"><div class="timer-number">{max(0, (delta.seconds%3600)//60):02d}</div><div class="timer-label">Minutos</div></div>
    </div>
    """, unsafe_allow_html=True)

    if delta.days <= 3:
        cp = calculate_carb_loading_protocol(st.session_state.user_weight)
        st.error(f"🚨 **CARBO-LOADING ATIVO (72H):** Prescrição: **{cp['daily_target_g']} /dia**.")

    st.divider()
    st.subheader("☀️ Calculadora Dinâmica de Suor & Estresse Térmico")
    cw1, cw2, cw3 = st.columns(3)
    temp = cw1.slider("Temperatura (°C):", 5.0, 40.0, 24.0)
    hum = cw2.slider("Humidade (%):", 20.0, 100.0, 65.0)
    dur = cw3.number_input("Duração Est. (Horas):", value=4.5)
    
    nutri = calculate_dynamic_sweat_nutrition(st.session_state.user_weight, st.session_state.user_bf_pct, st.session_state.user_gender, primary.get("type", "10K / Meia Maratona (21k)"), dur, temp, hum)
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Água", f"{nutri['fluid_hr_ml']} mL/h", f"Total: {nutri['total_fluid_l']} L")
    n2.metric("Sódio", f"{nutri['sodium_hr_mg']} mg/h", f"Total: {nutri['total_sodium_mg']} mg")
    n3.metric("HC", f"{nutri['carbs_hr_g']} g/h", f"Total: {nutri['total_carbs_g']} g")
    n4.metric("Estresse Térmico", nutri['thermal_stress_level'])

    st.divider()
    st.subheader("⏱️ Pacing Band (Com GAP para Altimetria)")
    tgt_pace = st.number_input("Ritmo Alvo (min/km):", value=4.15)
    st.dataframe(generate_pacing_band(tgt_pace, primary["dist_km"], st.session_state.user_hr_max).head(10), use_container_width=True)

    st.divider()
    st.subheader("📈 Visualizador de Taper (14 Dias)")
    ctl_vals, atl_vals, tsb_vals = compute_banister_ctl_atl_tsb(df_60d["DailyLoad"].tolist(), 42.0, 7.0)
    df_taper = simulate_taper_projection(ctl_vals[-1], atl_vals[-1])
    fig_tp = go.Figure()
    fig_tp.add_hrect(y0=10, y1=25, fillcolor="rgba(16, 185, 129, 0.15)", line_width=0, name="Zona Polimento")
    fig_tp.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["CTL_Proj"], name="CTL (Fitness)", line=dict(color='#3B82F6')))
    fig_tp.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["ATL_Proj"], name="ATL (Fadiga)", line=dict(color='#EF4444')))
    fig_tp.add_trace(go.Scatter(x=df_taper["Date"], y=df_taper["TSB_Proj"], name="TSB (Forma)", line=dict(color='#10B981', dash='dot')))
    fig_tp.update_layout(template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig_tp, use_container_width=True)

    with st.expander("📝 **Debrief Pós-Prova**"):
        with st.form("debrief_form"):
            st.text_input("Tempo Final Real:")
            st.number_input("HC Consumidos (g/h):", value=65.0)
            st.slider("RPE (1-10):", 1, 10, 8)
            st.text_area("Notas:")
            if st.form_submit_button("Guadar Debrief"): st.success("Registado!")

# ==========================================
# MODULE 7: GESTÃO DE SAPATILHAS
# ==========================================
elif top_nav == "👟 Gestão de Sapatilhas":
    st.title("👟 Rastreador de Desgaste Mecânico (Espuma Carbono)")
    for idx, shoe in enumerate(st.session_state.shoes):
        c_s1, c_s2, c_s3 = st.columns([3, 2, 2])
        c_s1.markdown(f"**{shoe['model']}**")
        c_s2.write(f"{shoe['km_used']} km / {shoe['max_km']} km")
        c_s3.write(f"Estado: **{shoe['status']}**")
        st.progress(min(1.0, shoe["km_used"] / shoe["max_km"]))
    
    st.divider()
    with st.form("add_sh"):
        m = st.text_input("Modelo:")
        km = st.number_input("Limite (km):", value=250.0)
        if st.form_submit_button("Adicionar") and m:
            st.session_state.shoes.append({"model": m, "km_used": 0.0, "max_km": km, "status": "Nova 🟢"})
            st.rerun()

# ==========================================
# MODULE 8: COACH IA APEX (GEMINI)
# ==========================================
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.title("🤖 Coach IA Apex")
    key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)
    if not key:
        st.info("💡 Adiciona a tua `GEMINI_API_KEY` nos secrets para ativar.")
    else:
        genai.configure(api_key=key)
        msg = st.chat_input("Pergunta ao Coach IA...")
        if msg:
            st.chat_message("user").write(msg)
            model = genai.GenerativeModel('gemini-1.5-flash')
            res = model.generate_content(f"Utilizador diz: {msg}. Prontidão={score}, VRC={hrv_curr}ms.")
            st.chat_message("assistant").write(res.text)

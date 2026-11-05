from __future__ import annotations

import zipfile
from datetime import date, datetime, timedelta
from html import escape
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data_store as store
import engine_core as core
from integrations.garmin import fetch_daily_metrics as fetch_garmin_metrics, fetch_historical_metrics
from services.data_import import parse_garmin_file_content
from ui.today import render_today_page


# -----------------------------------------------------------------------------
# Configuration and setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Apex | Performance & Healthspan",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
store.init_db()

st.markdown(
    """
    <style>
      .stApp { background: #0b0f17; color: #e2e8f0; }
      [data-testid="stMetric"] { background:#131a27; border:1px solid #263244; padding:14px; border-radius:12px; }
      .apex-note { background:#131a27; border:1px solid #334155; border-radius:12px; padding:14px 16px; }
      .apex-good { border-left:5px solid #10b981; }
      .apex-warn { border-left:5px solid #f59e0b; }
      .apex-alert { border-left:5px solid #ef4444; }
      .muted { color:#94a3b8; font-size:.88rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _secret(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name) if "os" in globals() else None
    if value:
        return value
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def _optional_float(raw: Any, label: str, minimum: Optional[float] = None,
                    maximum: Optional[float] = None) -> Optional[float]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(str(raw).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label}: introduz um número válido ou deixa em branco.")
    if not np.isfinite(value):
        raise ValueError(f"{label}: o valor tem de ser finito.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}: o valor mínimo é {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}: o valor máximo é {maximum}.")
    return value


def _fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}{suffix}"


def _clean_number(value: Any) -> Optional[float]:
    try:
        v = float(value)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _run_garmin_sync() -> bool:
    import os
    email = os.environ.get("GARMIN_EMAIL") or st.secrets.get("GARMIN_EMAIL", None) or str(st.session_state.get("garmin_email_input", "")).strip()
    password = os.environ.get("GARMIN_PASSWORD") or st.secrets.get("GARMIN_PASSWORD", None) or str(st.session_state.get("garmin_password_input", ""))
    
    if not email or not password:
        st.session_state["garmin_sync_result"] = {
            "ok": False,
            "message": "Insere as credenciais da Garmin ou configura-as nos Secrets do Streamlit.",
            "warnings": [],
        }
        return False

    try:
        metrics, warnings = fetch_garmin_metrics(email, password, date.today())
        if metrics:
            prof_ext = metrics.pop("profile_extracted", None)
            if prof_ext:
                from services.data_import import update_profile_if_missing
                update_profile_if_missing(prof_ext)

            store.upsert_daily_metrics(date.today(), metrics, source="garmin")
            store.set_setting("garmin_last_sync", datetime.now().isoformat(timespec="seconds"))
            st.session_state["garmin_sync_result"] = {
                "ok": True,
                "message": "Sincronização efetuada com sucesso! Métricas atualizadas no SQLite.",
                "warnings": warnings,
            }
            return True
        else:
            st.session_state["garmin_sync_result"] = {
                "ok": False,
                "message": "Sem dados novos retornados da Garmin para o dia de hoje.",
                "warnings": warnings,
            }
            return False
    except Exception as exc:
        st.session_state["garmin_sync_result"] = {
            "ok": False,
            "message": f"Erro na sincronização ({type(exc).__name__}). Confirma o e-mail e palavra-passe.",
            "warnings": [],
        }
        return False


# -----------------------------------------------------------------------------
# Sidebar: Navigation and Integrations
# -----------------------------------------------------------------------------
settings = store.get_setting("profile", {}) or {}
saved_mode = store.get_setting("mode", "performance")
mode_options = [
    "🏃 Performance (Atleta)",
    "🧘‍♂️ Health & Wellness",
    "🧬 Longevidade & Saúde Metabólica"
]
default_idx = 1 if saved_mode == "wellness" else 2 if saved_mode == "longevity" else 0
mode_label = st.sidebar.radio("Objetivo principal", mode_options, index=default_idx)
mode = "wellness" if mode_label.startswith("🧘") else "longevity" if mode_label.startswith("🧬") else "performance"
store.set_setting("mode", mode)

window = st.sidebar.select_slider(
    "Janela dos gráficos",
    options=[7, 14, 28, 60],
    value=int(store.get_setting("display_window", 14)),
    format_func=lambda x: f"{x} dias",
)
store.set_setting("display_window", window)

with st.sidebar.expander("👤 Perfil", expanded=False):
    gender = st.selectbox(
        "Sexo usado nas tabelas de referência de VO2max",
        ["Não indicado", "Masculino", "Feminino"],
        index=["Não indicado", "Masculino", "Feminino"].index(settings.get("gender", "Não indicado"))
        if settings.get("gender", "Não indicado") in ["Não indicado", "Masculino", "Feminino"] else 0,
    )
    age_raw = st.text_input("Idade (anos)", value=str(settings.get("age") or ""))
    weight_raw = st.text_input("Peso (kg)", value=str(settings.get("weight_kg") or ""))
    vo2_raw = st.text_input("VO2max (mL/kg/min)", value=str(settings.get("vo2max") or ""))
    hrmax_raw = st.text_input("FC máxima medida (bpm)", value=str(settings.get("hr_max") or ""))
    if st.button("Guardar perfil", use_container_width=True):
        try:
            profile = {
                "gender": gender,
                "age": _optional_float(age_raw, "Idade", 1, 120),
                "weight_kg": _optional_float(weight_raw, "Peso", 1, 400),
                "vo2max": _optional_float(vo2_raw, "VO2max", 1, 120),
                "hr_max": _optional_float(hrmax_raw, "FC máxima", 50, 250),
            }
            store.set_setting("profile", profile)
            st.success("Perfil guardado.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

with st.sidebar.expander("⚙️ Parâmetros CTL / ATL", expanded=False):
    ctl_tc = st.slider("Constante CTL (dias)", 28, 60, int(store.get_setting("ctl_tc", 42)))
    atl_tc = st.slider("Constante ATL (dias)", 3, 14, int(store.get_setting("atl_tc", 7)))
    store.set_setting("ctl_tc", ctl_tc)
    store.set_setting("atl_tc", atl_tc)

with st.sidebar.expander("📂 Importar Histórico (1 clique)", expanded=False):
    st.caption("Carrega o ficheiro CSV, JSON ou ZIP exportado do Garmin Connect para povoar o histórico de uma só vez.")
    uploaded_file = st.file_uploader("Ficheiro Garmin (CSV/JSON/ZIP)", type=["csv", "json", "zip"])
    if uploaded_file is not None:
        try:
            all_records: List[Dict[str, Any]] = []
            if uploaded_file.name.lower().endswith(".zip"):
                with zipfile.ZipFile(uploaded_file) as z:
                    for filename in z.namelist():
                        if filename.lower().endswith(".csv") or filename.lower().endswith(".json"):
                            with z.open(filename) as f:
                                all_records.extend(parse_garmin_file_content(filename, f.read()))
            else:
                all_records.extend(parse_garmin_file_content(uploaded_file.name, uploaded_file.getvalue()))

            if all_records:
                inserted = store.bulk_insert_garmin_history(all_records)
                st.success(f"Histórico importado com sucesso! {inserted} registos guardados no SQLite.")
                st.rerun()
            else:
                st.error("Não foram encontradas colunas de métricas reconhecidas no ficheiro.")
        except Exception as exc:
            st.error(f"Erro ao processar ficheiro: {exc}")

with st.sidebar.expander("⌚ Sincronização Garmin", expanded=False):
    st.caption("As credenciais são usadas apenas durante esta sincronização e não são guardadas na base de dados.")
    with st.form("garmin_sync_form", clear_on_submit=True):
        st.text_input("E-mail Garmin", key="garmin_email_input")
        st.text_input("Palavra-passe Garmin", type="password", key="garmin_password_input")
        if st.form_submit_button("Sincronizar dados disponíveis", use_container_width=True):
            _run_garmin_sync()
            st.rerun()
            
    result = st.session_state.get("garmin_sync_result")
    if result:
        (st.success if result.get("ok") else st.error)(result.get("message", ""))
        for warning in result.get("warnings", []):
            st.caption(f"• {warning}")
    last_sync = store.get_setting("garmin_last_sync")
    if last_sync:
        st.caption(f"Última sincronização: {last_sync}")

st.sidebar.divider()
if mode == "performance":
    nav_items = [
        "📌 Today / Decisão Diária",
        "📈 Tendência de VRC & Gráficos",
        "🏋️ Engine de Força & Carga Axial",
        "📊 Analytics de Carga (CTL/ATL/TSB)",
        "🧬 Biomarcadores & Healthspan",
        "🎯 Race Hub & Planeamento",
        "👟 Gestão de Sapatilhas",
        "🤖 Coach IA Apex (Gemini)",
    ]
elif mode == "wellness":
    nav_items = [
        "📌 Today / Decisão Diária",
        "📈 Tendência de VRC & Gráficos",
        "🧬 Biomarcadores & Healthspan",
        "🤖 Coach IA Apex (Gemini)",
    ]
else:
    nav_items = [
        "📌 Today / Decisão Diária",
        "📈 Tendência de VRC & Gráficos",
        "🏋️ Engine de Força & Carga Axial",
        "🧬 Biomarcadores & Healthspan",
        "🤖 Coach IA Apex (Gemini)",
    ]
top_nav = st.sidebar.radio("Módulos", nav_items)
st.sidebar.divider()
st.sidebar.caption("Apex local · dados pessoais armazenados em SQLite")

# -----------------------------------------------------------------------------
# Data pipeline & Data state calculation
# -----------------------------------------------------------------------------
today = date.today()
start_day = today - timedelta(days=60)
dates = pd.date_range(start=start_day, end=today, freq="D")
raw_daily = store.fetch_daily_metrics(start_day, today)
raw_training = store.fetch_training_days(start_day, today)

base_df = pd.DataFrame({"Date": dates})
if not raw_daily.empty:
    raw_daily["Date"] = pd.to_datetime(raw_daily["date"])
    base_df = base_df.merge(raw_daily, on="Date", how="left")
else:
    for col in ["hrv", "rhr", "sleep_score", "sleep_hours", "sleep_target_hours", "soreness", "stress", "mood",
                "vendor_readiness", "hrv_source", "rhr_source", "sleep_score_source", "sleep_hours_source"]:
        base_df[col] = np.nan

for col in ["hrv", "rhr", "sleep_score", "sleep_hours", "sleep_target_hours", "soreness", "stress", "mood", "vendor_readiness"]:
    if col not in base_df:
        base_df[col] = np.nan
    base_df[col] = pd.to_numeric(base_df[col], errors="coerce")

base_df = base_df.rename(columns={
    "hrv": "HRV", "rhr": "RHR", "sleep_score": "SleepScore", "sleep_hours": "SleepHours",
    "sleep_target_hours": "SleepTargetHours", "soreness": "Soreness", "stress": "Stress",
    "mood": "Mood", "vendor_readiness": "GarminReadiness",
})
base_df["SubjectiveScore"] = [
    core.subjective_score(int(r.Soreness), int(r.Stress), int(r.Mood))
    if pd.notna(r.Soreness) and pd.notna(r.Stress) and pd.notna(r.Mood) else np.nan
    for r in base_df.itertuples()
]

base_df["DailyLoad"] = np.nan
if not raw_training.empty:
    raw_training["Date"] = pd.to_datetime(raw_training["date"])
    base_df = base_df.merge(raw_training[["Date", "daily_load", "source"]], on="Date", how="left")
    base_df["DailyLoad"] = pd.to_numeric(base_df["daily_load"], errors="coerce")
else:
    base_df["source"] = np.nan

LOAD_WINDOW = 42
last42_loads = base_df["DailyLoad"].tail(LOAD_WINDOW)
load_complete_42 = len(last42_loads) == LOAD_WINDOW and last42_loads.notna().all()
base_df["CTL"] = np.nan
base_df["ATL"] = np.nan
base_df["TSB"] = np.nan
if load_complete_42:
    load_result = core.compute_banister(last42_loads.tolist(), ctl_tc, atl_tc)
    base_df.loc[base_df.index[-LOAD_WINDOW:], "CTL"] = load_result["ctl"]
    base_df.loc[base_df.index[-LOAD_WINDOW:], "ATL"] = load_result["atl"]
    base_df.loc[base_df.index[-LOAD_WINDOW:], "TSB"] = load_result["tsb"]

hrv_curr = _clean_number(base_df["HRV"].iloc[-1])
rhr_curr = _clean_number(base_df["RHR"].iloc[-1])
sleep_curr = _clean_number(base_df["SleepScore"].iloc[-1])
sleep_hours_curr = _clean_number(base_df["SleepHours"].iloc[-1])
sleep_target_curr = _clean_number(base_df["SleepTargetHours"].dropna().iloc[-1]) if not base_df["SleepTargetHours"].dropna().empty else 8.0
garmin_readiness_curr = _clean_number(base_df["GarminReadiness"].dropna().iloc[-1]) if not base_df["GarminReadiness"].dropna().empty else None

base_hrv = core.compute_baseline(base_df["HRV"], min_n=14, exclude_last=True)
base_rhr = core.compute_baseline(base_df["RHR"], min_n=14, exclude_last=True)
hrv_mean = base_hrv.mean if base_hrv else None
rhr_mean = base_rhr.mean if base_rhr else None
hrv_valid_days = int(base_df["HRV"].iloc[:-1].notna().sum())
calib_state, calib_label = core.DataQualityEngine.get_calibration_state(hrv_valid_days)

zs_today = core.zscores_for_day(base_df, -1)
readiness_data = core.compute_readiness(zs_today, mode=mode)

score = int(garmin_readiness_curr) if garmin_readiness_curr is not None else readiness_data["score"]
decision = core.decision_for(score) if score is not None else {"cap": "full", "headline": "Sem prontidão", "tone": "amber"}
hrv_context = core.get_hrv_context(hrv_curr, hrv_mean, base_hrv.sd if base_hrv else None)

diff_minutes = (sleep_target_curr - sleep_hours_curr) * 60.0 if sleep_hours_curr is not None else None
trend_info = core.calculate_trend(base_df["HRV"].tail(21).tolist())
df_display = base_df.tail(window).copy()

profile = store.get_setting("profile", {}) or {}
user_age = _clean_number(profile.get("age"))
user_weight = _clean_number(profile.get("weight_kg"))
user_vo2 = _clean_number(profile.get("vo2max"))
user_hrmax = _clean_number(profile.get("hr_max"))
user_gender = profile.get("gender", "Não indicado")

st.title("⚡ Apex Engine")
st.caption(f"Performance, saúde e longevidade · {mode_label} · {calib_label}")
st.info(
    "O Apex é uma ferramenta de acompanhamento e educação, não um dispositivo médico. "
    "A prontidão, ACWR, score Healthspan e prescrições de força são heurísticas; sintomas e contexto clínico prevalecem."
)

# -----------------------------------------------------------------------------
# Module Routing
# -----------------------------------------------------------------------------
if top_nav == "📌 Today / Decisão Diária":
    render_today_page(
        base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
        hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
        sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
        garmin_readiness_curr=garmin_readiness_curr, score=score,
        decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
        hrv_valid_days=hrv_valid_days, sync_callback=_run_garmin_sync
    )

elif top_nav == "📈 Tendência de VRC & Gráficos":
    st.subheader("📈 Tendência da variabilidade da frequência cardíaca")
    if st.button("📥 Descarregar Histórico Recente (VRC e FC de Repouso)", use_container_width=True):
        import os
        email = os.environ.get("GARMIN_EMAIL") or st.secrets.get("GARMIN_EMAIL", None)
        password = os.environ.get("GARMIN_PASSWORD") or st.secrets.get("GARMIN_PASSWORD", None)
        if email and password:
            with st.spinner("A transferir dados históricos dos últimos 30 dias..."):
                try:
                    recs = fetch_historical_metrics(email, password, days=30)
                    if recs:
                        inserted = store.bulk_insert_garmin_history(recs)
                        st.success(f"{inserted} registos históricos guardados com sucesso!")
                        st.rerun()
                    else:
                        st.warning("A Garmin não retornou novos dados para o período solicitado.")
                except Exception as exc:
                    st.error(f"Erro ao descarregar histórico: {exc}")
        else:
            st.error("Configura as credenciais nos Secrets do Streamlit para descarregar o histórico.")

    chart_df = df_display.copy()
    overlay_rhr = st.checkbox("Sobrepor FC de repouso", value=True)
    
    if chart_df["HRV"].dropna().empty and chart_df["RHR"].dropna().empty:
        st.info("Ainda não existem registos no período selecionado. Importa o histórico ou clica no botão de descarregar histórico acima.")
    else:
        chart_df["HRV_EWMA"] = chart_df["HRV"].ewm(span=7, adjust=False, min_periods=2).mean()
        fig = go.Figure()
        
        if base_hrv:
            fig.add_hrect(y0=base_hrv.mean - base_hrv.sd, y1=base_hrv.mean + base_hrv.sd,
                          fillcolor="rgba(16,185,129,0.12)", line_width=0,
                          annotation_text="±1 DP da base pessoal", annotation_position="top left")
            fig.add_hline(y=base_hrv.mean, line_dash="dot", line_color="#10B981", name="Média pessoal")
            
        vrc_data = chart_df.dropna(subset=["HRV"])
        if not vrc_data.empty:
            fig.add_trace(go.Scatter(x=vrc_data["Date"], y=vrc_data["HRV"], mode="lines+markers",
                                     name="VRC diária (ms)", line=dict(color="#3B82F6", width=2)))
            fig.add_trace(go.Scatter(x=chart_df["Date"], y=chart_df["HRV_EWMA"], mode="lines",
                                     name="Média móvel exponencial 7d", line=dict(color="#10B981", width=3, dash="dash")))
        
        if overlay_rhr:
            rhr_df = chart_df.dropna(subset=["RHR"])
            if not rhr_df.empty:
                fig.add_trace(go.Scatter(x=rhr_df["Date"], y=rhr_df["RHR"], mode="lines+markers",
                                         name="FC repouso (bpm)", yaxis="y2", line=dict(color="#EF4444", width=1.5)))
                fig.update_layout(yaxis2=dict(title="FC repouso (bpm)", overlaying="y", side="right"))
                
        fig.update_layout(template="plotly_dark", hovermode="x unified", yaxis_title="VRC (ms)",
                          title=f"Últimos {window} dias com dados reais")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Tendência estatística")
    if trend_info["n"] < 7:
        st.info(f"{trend_info['text']} — {trend_info['n']} observações válidas de VRC; clica no botão de descarregar histórico acima para preencher os dias em falta.")
    else:
        st.write(f"{trend_info['text']}. Inclinação estimada: **{trend_info['slope']:.2f} ms/dia**; IC aproximado 95%: {trend_info['ci_low']:.2f} a {trend_info['ci_high']:.2f}; n={trend_info['n']}.")

elif top_nav == "🏋️ Engine de Força & Carga Axial":
    st.subheader("🏋️ Planeador de força")
    duration_cap = st.slider("Tempo disponível (minutos)", 20, 120, 60)
    session = core.build_strength_session(decision["cap"], one_rm=store.get_setting("one_rm", {}) or {}, time_min=duration_cap)
    st.metric("Índice heurístico de carga axial média", f"{session['spinal_score']}/5")
    for exercise in session["exercises"]:
        load_text = f" · carga orientadora: {exercise['kg']} kg" if exercise["kg"] is not None else " · carga não estimada"
        st.markdown(f"**{exercise['name']}** — {exercise['sets']} × {exercise['reps']} · RIR {exercise['rir']}{load_text} · carga axial {exercise['spinal']}/5")

elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.subheader("📊 Training Load Analytics")
    if not load_complete_42:
        st.info("CTL/ATL/TSB ainda não calculados. São necessários 42 dias consecutivos com carga registada.")
    else:
        current_ctl = float(base_df["CTL"].iloc[-1])
        current_atl = float(base_df["ATL"].iloc[-1])
        current_tsb = float(base_df["TSB"].iloc[-1])
        acwr = core.compute_acwr(base_df["DailyLoad"].tail(28).tolist())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CTL", f"{current_ctl:.1f} UA")
        c2.metric("ATL", f"{current_atl:.1f} UA")
        c3.metric("TSB", f"{current_tsb:.1f} UA")
        c4.metric("ACWR", _fmt(acwr, 2))

elif top_nav == "🧬 Biomarcadores & Healthspan":
    st.subheader("🧬 Capacidade funcional e Healthspan")
    st.caption("Módulo de gestão de biomarcadores laboratoriais e longevidade.")

elif top_nav == "🎯 Race Hub & Planeamento":
    st.subheader("🎯 Race Hub & Planeamento")
    st.caption("Planeamento de provas e estratégias de pacing.")

elif top_nav == "👟 Gestão de Sapatilhas":
    st.subheader("👟 Gestão de sapatilhas")
    st.caption("Controlo de desgaste e quilometragem de sapatilhas.")

elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.subheader("🤖 Coach IA Apex")
    st.caption("Assistente virtual treinado nos teus dados biométricos.")

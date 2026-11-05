from __future__ import annotations

import io
import json
import os
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
from garmin_adapter import fetch_daily_metrics as fetch_garmin_metrics, fetch_historical_metrics


# -----------------------------------------------------------------------------
# Configuration and small helpers
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
    value = os.environ.get(name)
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
    """Executa a sincronização direta com os servidores Garmin Connect."""
    email = _secret("GARMIN_EMAIL") or str(st.session_state.get("garmin_email_input", "")).strip()
    password = _secret("GARMIN_PASSWORD") or str(st.session_state.get("garmin_password_input", ""))
    
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


def _parse_garmin_file_content(file_name: str, content: bytes) -> List[Dict[str, Any]]:
    """Parser abrangente para relatórios exportados do Garmin Connect (CSV e JSON GDPR)."""
    records: List[Dict[str, Any]] = []
    fname_lower = file_name.lower()

    if fname_lower.endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(content))
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

            date_col = next((c for c in df.columns if any(k in c for k in ["data", "date", "day", "calendar"])), None)
            if not date_col:
                return records

            hrv_col = next((c for c in df.columns if any(k in c for k in ["hrv", "vrc", "sdnn", "lastnightavg", "weeklyavg"])), None)
            rhr_col = next((c for c in df.columns if any(k in c for k in ["rhr", "repouso", "resting", "restingheartrate"])), None)
            sleep_score_col = next((c for c in df.columns if "sleep" in c and "score" in c or "pontuação" in c), None)
            sleep_hours_col = next((c for c in df.columns if any(k in c for k in ["sleep_time", "horas_de_sono", "duration", "total_sleep"])), None)
            readiness_col = next((c for c in df.columns if any(k in c for k in ["readiness", "prontidão", "training_readiness"])), None)

            for _, row in df.iterrows():
                try:
                    d_val = pd.to_datetime(row[date_col]).date().isoformat()
                except Exception:
                    continue

                rec: Dict[str, Any] = {"date": d_val}
                if hrv_col and pd.notna(row[hrv_col]):
                    rec["hrv"] = _clean_number(row[hrv_col])
                if rhr_col and pd.notna(row[rhr_col]):
                    rec["rhr"] = _clean_number(row[rhr_col])
                if sleep_score_col and pd.notna(row[sleep_score_col]):
                    rec["sleep_score"] = _clean_number(row[sleep_score_col])
                if sleep_hours_col and pd.notna(row[sleep_hours_col]):
                    h_val = _clean_number(row[sleep_hours_col])
                    rec["sleep_hours"] = round(h_val / 3600.0, 2) if h_val and h_val > 24 else h_val
                if readiness_col and pd.notna(row[readiness_col]):
                    rec["vendor_readiness"] = _clean_number(row[readiness_col])

                if len(rec) > 1:
                    records.append(rec)
        except Exception:
            pass

    elif fname_lower.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8", errors="ignore"))
            if isinstance(data, dict):
                data = [data]

            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue

                    raw_date = (
                        item.get("calendarDate")
                        or item.get("date")
                        or item.get("day")
                        or item.get("userDailySleepDTO", {}).get("calendarDate")
                    )
                    if not raw_date:
                        continue

                    try:
                        d_str = pd.to_datetime(raw_date).date().isoformat()
                    except Exception:
                        continue

                    rec: Dict[str, Any] = {"date": d_str}

                    rhr_val = item.get("restingHeartRate") or item.get("rhr")
                    if rhr_val is not None:
                        rec["rhr"] = _clean_number(rhr_val)

                    hrv_val = (
                        item.get("lastNightAvg")
                        or item.get("hrvSummary", {}).get("lastNightAvg")
                        or item.get("weeklyAvg")
                        or item.get("lastNight5MinHigh")
                    )
                    if hrv_val is not None:
                        rec["hrv"] = _clean_number(hrv_val)

                    readiness_val = (
                        item.get("score")
                        or item.get("trainingReadinessScore")
                        or item.get("scoreValue")
                        or item.get("userDailyTrainingReadinessDTO", {}).get("score")
                    )
                    if readiness_val is not None:
                        rec["vendor_readiness"] = _clean_number(readiness_val)

                    sleep_dto = item.get("userDailySleepDTO") or item
                    sleep_sec = (
                        sleep_dto.get("sleepTimeSeconds")
                        or sleep_dto.get("totalSleepHours")
                        or sleep_dto.get("unmeasurableSleepSeconds")
                        or item.get("sleepTimeSeconds")
                        or item.get("totalSleepSeconds")
                    )
                    if sleep_sec is not None:
                        sec_num = _clean_number(sleep_sec)
                        if sec_num and sec_num > 0:
                            rec["sleep_hours"] = round(sec_num / 3600.0, 2) if sec_num > 24 else round(sec_num, 2)

                    sleep_score = (
                        sleep_dto.get("sleepScores", {}).get("overall", {}).get("value")
                        or sleep_dto.get("overallScore")
                        or item.get("overallScore")
                    )
                    if sleep_score is not None:
                        rec["sleep_score"] = _clean_number(sleep_score)

                    if len(rec) > 1:
                        records.append(rec)
        except Exception:
            pass

    return records


# -----------------------------------------------------------------------------
# Sidebar: navigation, profile and integrations
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
                                all_records.extend(_parse_garmin_file_content(filename, f.read()))
            else:
                all_records.extend(_parse_garmin_file_content(uploaded_file.name, uploaded_file.getvalue()))

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
    st.caption("A integração usa a biblioteca Garmin Connect. Dias em falta são automaticamente recuperados.")

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
# Data pipeline: actual records only. Missing dates remain NaN.
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
    for col in ["hrv", "rhr", "sleep_score", "sleep_hours", "soreness", "stress", "mood",
                "vendor_readiness", "hrv_source", "rhr_source", "sleep_score_source", "sleep_hours_source"]:
        base_df[col] = np.nan

for col in ["hrv", "rhr", "sleep_score", "sleep_hours", "soreness", "stress", "mood", "vendor_readiness"]:
    if col not in base_df:
        base_df[col] = np.nan
    base_df[col] = pd.to_numeric(base_df[col], errors="coerce")

base_df = base_df.rename(columns={
    "hrv": "HRV", "rhr": "RHR", "sleep_score": "SleepScore", "sleep_hours": "SleepHours",
    "soreness": "Soreness", "stress": "Stress", "mood": "Mood",
    "vendor_readiness": "GarminReadiness",
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
sleep_debt = core.compute_sleep_debt(base_df["SleepHours"].tolist(), target=8.0, nights=7)
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
# MODULE 1 — Today
# -----------------------------------------------------------------------------
if top_nav == "📌 Today / Decisão Diária":
    head_col1, head_col2 = st.columns([3, 1])
    with head_col1:
        st.subheader("📝 Daily Check-In")
    with head_col2:
        if st.button("⚡ SYNC DATA", key="sync_data_top_btn", type="primary"):
            with st.spinner("Sincronizando Garmin..."):
                ok = _run_garmin_sync()
                if ok:
                    st.toast("Garmin sincronizada com sucesso!", icon="⚡")
                st.rerun()

    with st.expander("Registar métricas de hoje ou corrigir um dia anterior", expanded=False):
        with st.form("daily_checkin_form"):
            check_day = st.date_input("Data do registo", value=today, max_value=today)
            c1, c2, c3, c4 = st.columns(4)
            hrv_input = c1.text_input("VRC noturna (ms)", placeholder="Em branco = sem dado")
            rhr_input = c2.text_input("FC repouso (bpm)", placeholder="Em branco = sem dado")
            sleep_score_input = c3.text_input("Sleep score (0-100)", placeholder="Em branco = sem dado")
            sleep_hours_input = c4.text_input("Sono (horas)", placeholder="Em branco = sem dado")
            st.caption("Diário subjetivo: 1 = baixo/mínimo; 5 = alto/máximo. Para stress e DOMS, 5 representa pior estado.")
            s1, s2, s3 = st.columns(3)
            soreness_input = s1.slider("Dor muscular / DOMS", 1, 5, 3)
            stress_input = s2.slider("Stress", 1, 5, 3)
            mood_input = s3.slider("Humor / motivação", 1, 5, 3)
            save_checkin = st.form_submit_button("Guardar check-in", use_container_width=True)
        if save_checkin:
            try:
                metrics = {
                    "hrv": _optional_float(hrv_input, "VRC", 0, 300),
                    "rhr": _optional_float(rhr_input, "FC repouso", 25, 220),
                    "sleep_score": _optional_float(sleep_score_input, "Sleep score", 0, 100),
                    "sleep_hours": _optional_float(sleep_hours_input, "Horas de sono", 0, 24),
                    "soreness": soreness_input, "stress": stress_input, "mood": mood_input,
                }
                store.upsert_daily_metrics(check_day, metrics, source="manual")
                st.success("Check-in guardado na base de dados local.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    latest = base_df.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("VRC noturna", _fmt(hrv_curr, 0, " ms"),
              f"Base pessoal: {_fmt(hrv_mean, 1, ' ms')}" if hrv_mean is not None else "Base ainda indisponível")
    c2.metric("FC repouso", _fmt(rhr_curr, 0, " bpm"),
              f"Base pessoal: {_fmt(rhr_mean, 1, ' bpm')}" if rhr_mean is not None else "Base ainda indisponível")
    c3.metric("Sono", _fmt(sleep_hours_curr, 1, " h"),
              f"Score: {_fmt(sleep_curr, 0)}" if sleep_curr is not None else "Score não registado")
    c4.metric("Défice vs 8 h", _fmt(sleep_debt["debt_h"], 1, " h"),
              f"{sleep_debt['nights']} noites registadas" if sleep_debt["nights"] else "Sem noites registadas")

    st.divider()

    # Bloco de Prontidão Principal
    if garmin_readiness_curr is not None:
        g_score = int(garmin_readiness_curr)
        g_decision = core.decision_for(g_score)
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(g_decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}"><b>{escape(g_decision["headline"])}</b><br>'
            f'<span style="font-size:1.5rem;font-weight:800">Garmin Training Readiness: {g_score}/100</span><br>'
            f'<span class="muted">Métrica oficial sincronizada diretamente da Garmin Connect</span></div>',
            unsafe_allow_html=True,
        )
    elif score is not None:
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}"><b>{escape(decision["headline"])}</b><br>'
            f'<span style="font-size:1.5rem;font-weight:800">Prontidão estimada: {score}/100</span><br>'
            f'<span class="muted">Calculada com base na linha de base local</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="apex-note apex-warn"><b>Prontidão não disponível</b><br>'
            'Clica no botão <b>⚡ SYNC DATA</b> no topo para sincronizar os dados mais recentes do teu relógio.</div>',
            unsafe_allow_html=True,
        )

    st.subheader("Interpretação dos sinais")
    st.write(f"**VRC:** {hrv_context['status']}. {hrv_context['explanation']}")
    if sleep_debt["avg_h"] is not None:
        st.write(f"Sono médio das noites registadas: **{sleep_debt['avg_h']:.1f} h** ({sleep_debt['nights']} noites disponíveis). O défice abaixo de 8 h é uma referência configurável, não uma necessidade individual determinada.")

    st.subheader("Qualidade e origem dos dados")
    st.write(f"Dias válidos de VRC antes de hoje: **{hrv_valid_days}**.")
    source_cols = [("VRC", "hrv_source"), ("FC repouso", "rhr_source"),
                   ("Sono", "sleep_hours_source"), ("Score sono", "sleep_score_source")]
    st.table(pd.DataFrame([{"Métrica": name,
                            "Origem hoje": str(latest.get(col)) if pd.notna(latest.get(col)) else "Sem dado"}
                           for name, col in source_cols]))

# -----------------------------------------------------------------------------
# MODULE 2 — HRV trend
# -----------------------------------------------------------------------------
elif top_nav == "📈 Tendência de VRC & Gráficos":
    st.subheader("📈 Tendência da variabilidade da frequência cardíaca")
    
    # Exibe botão para puxar histórico completo da Garmin se houver pouca VRC
    if hrv_valid_days < 7:
        if st.button("📥 Descarregar Histórico de VRC de 60 Dias da Garmin Connect", use_container_width=True):
            email = _secret("GARMIN_EMAIL")
            password = _secret("GARMIN_PASSWORD")
            if email and password:
                with st.spinner("A transferir histórico de VRC e FC de repouso dos últimos 60 dias..."):
                    recs = fetch_historical_metrics(email, password, days=60)
                    if recs:
                        store.bulk_insert_garmin_history(recs)
                        st.success(f"{len(recs)} dias de histórico importados com sucesso!")
                        st.rerun()
                    else:
                        st.error("Não foi possível recuperar o histórico de VRC.")
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
            
        # Linha de VRC (liga os pontos válidos)
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
        st.info(f"{trend_info['text']} — {trend_info['n']} observações válidas de VRC; clica no botão de importar histórico acima para preencher os dias em falta.")
    else:
        st.write(f"{trend_info['text']}. Inclinação estimada: **{trend_info['slope']:.2f} ms/dia**; IC aproximado 95%: {trend_info['ci_low']:.2f} a {trend_info['ci_high']:.2f}; n={trend_info['n']}.")
        st.caption("Uma tendência estatística não identifica a causa e não determina, isoladamente, a prontidão para treinar.")

# -----------------------------------------------------------------------------
# MODULE 3 — Strength and sRPE
# -----------------------------------------------------------------------------
elif top_nav == "🏋️ Engine de Força & Carga Axial":
    st.subheader("🏋️ Planeador de força")
    if score is None:
        st.warning("Sem prontidão estimada. O motor apresenta apenas um modelo conservador/moderado genérico; não o interpretes como avaliação individual.")
    elif decision["cap"] != "full":
        st.warning("O nível de carga sugerido é uma heurística. Ajusta-o à experiência, técnica, dor, lesões prévias e plano do treinador.")

    with st.expander("Introduzir estimativas de 1RM para calcular cargas (opcional)", expanded=False):
        rm_keys = {"back_squat": "Agachamento", "rdl": "Peso morto romeno", "bench": "Supino",
                   "row": "Remada", "leg_press": "Prensa", "leg_curl": "Flexão de pernas"}
        saved_rms = store.get_setting("one_rm", {}) or {}
        rm_inputs = {}
        cols = st.columns(3)
        for idx, (key, label) in enumerate(rm_keys.items()):
            raw = cols[idx % 3].text_input(f"{label} 1RM (kg)", value=str(saved_rms.get(key) or ""), key=f"rm_{key}")
            try:
                parsed = _optional_float(raw, label, 1, 600)
                if parsed is not None:
                    rm_inputs[key] = parsed
            except ValueError as exc:
                st.error(str(exc))
        if st.button("Guardar 1RM", key="save_1rm"):
            store.set_setting("one_rm", rm_inputs)
            st.success("Estimativas de 1RM guardadas.")
            st.rerun()

    duration_cap = st.slider("Tempo disponível (minutos)", 20, 120, 60)
    session = core.build_strength_session(decision["cap"], one_rm=store.get_setting("one_rm", {}) or {}, time_min=duration_cap)
    st.metric("Índice heurístico de carga axial média", f"{session['spinal_score']}/5")
    st.caption("A escala de carga axial é uma classificação qualitativa do catálogo de exercícios, não uma medição biomecânica nem um rastreio de lesão.")
    for exercise in session["exercises"]:
        load_text = f" · carga orientadora: {exercise['kg']} kg" if exercise["kg"] is not None else " · carga não estimada (1RM não introduzido)"
        st.markdown(
            f"**{exercise['name']}** — {exercise['sets']} × {exercise['reps']} · RIR {exercise['rir']}"
            f"{load_text} · carga axial {exercise['spinal']}/5"
        )
    if session["trimmed"]:
        st.caption("Exercícios retirados para respeitar o tempo: " + ", ".join(session["trimmed"]))

    st.divider()
    st.subheader("Registar sessão (sRPE)")
    with st.form("workout_log_form"):
        workout_day = st.date_input("Data da sessão", value=today, max_value=today)
        workout_title = st.text_input("Sessão / modalidade", value="Treino de força")
        c1, c2 = st.columns(2)
        duration = c1.number_input("Duração (min)", min_value=1, max_value=600, value=60)
        rpe = c2.slider("RPE global da sessão", 1, 10, 6)
        save_workout = st.form_submit_button("Guardar sessão e carga sRPE", use_container_width=True)
    if save_workout:
        try:
            result = store.log_workout(workout_day, workout_title, duration, rpe)
            st.success(f"Sessão guardada. Carga sRPE: {result['session_load']:.1f} UA; total diário: {result['daily_total']:.1f} UA.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    workouts_today = store.fetch_workouts(today, today)
    if not workouts_today.empty:
        st.dataframe(workouts_today[["title", "duration_min", "rpe", "load_ua"]], use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# MODULE 4 — Training load analytics
# -----------------------------------------------------------------------------
elif top_nav == "📊 Analytics de Carga (CTL/ATL/TSB)":
    st.subheader("📊 Training Load Analytics")
    st.caption("Regista diariamente a carga total ou confirma 0 UA num dia de descanso. Dias em branco são desconhecidos, não descanso.")
    with st.form("manual_load_form"):
        load_day = st.date_input("Data", value=today, max_value=today)
        load_raw = st.text_input("Carga diária total (UA)", placeholder="Ex.: 450 · 0 significa descanso confirmado")
        note = st.text_input("Nota (opcional)")
        save_load = st.form_submit_button("Guardar carga diária", use_container_width=True)
    if save_load:
        try:
            load_value = _optional_float(load_raw, "Carga diária", 0, 100000)
            if load_value is None:
                raise ValueError("Introduz a carga em UA; usa 0 para confirmar descanso.")
            store.set_training_day(load_day, load_value, source="manual", notes=note)
            st.success("Carga diária guardada.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    if st.button("Marcar hoje como descanso confirmado", use_container_width=False):
        try:
            store.mark_rest_day(today)
            st.success("Hoje foi registado como 0 UA (descanso confirmado).")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    training_coverage_42 = int(base_df["DailyLoad"].tail(42).notna().sum())
    training_coverage_28 = int(base_df["DailyLoad"].tail(28).notna().sum())
    m1, m2, m3 = st.columns(3)
    m1.metric("Dias registados / 42", f"{training_coverage_42}/42")
    m2.metric("Dias registados / 28", f"{training_coverage_28}/28")
    m3.metric("Fonte dos dados", "sRPE / manual")

    if not load_complete_42:
        st.info("CTL/ATL/TSB ainda não calculados. São necessários 42 dias consecutivos com carga registada; confirma explicitamente os dias de descanso com 0 UA.")
    else:
        current_ctl = float(base_df["CTL"].iloc[-1])
        current_atl = float(base_df["ATL"].iloc[-1])
        current_tsb = float(base_df["TSB"].iloc[-1])
        acwr = core.compute_acwr(base_df["DailyLoad"].tail(28).tolist())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CTL · carga crónica", f"{current_ctl:.1f} UA")
        c2.metric("ATL · carga aguda", f"{current_atl:.1f} UA")
        c3.metric("TSB · CTL − ATL", f"{current_tsb:.1f} UA")
        c4.metric("ACWR (7:28)", _fmt(acwr, 2))
        acwr_text, _ = core.acwr_zone(acwr)
        st.write(f"**Contexto ACWR:** {acwr_text}.")
        st.caption("ACWR e TSB são descritores de carga, não calculadoras de risco de lesão nem limites universais de segurança.")
        chart_load = base_df.tail(42)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_load["Date"], y=chart_load["CTL"], name="CTL", line=dict(color="#3B82F6", width=3)))
        fig.add_trace(go.Scatter(x=chart_load["Date"], y=chart_load["ATL"], name="ATL", line=dict(color="#EF4444", width=2)))
        fig.add_trace(go.Scatter(x=chart_load["Date"], y=chart_load["TSB"], name="TSB", line=dict(color="#10B981", width=2, dash="dot")))
        fig.update_layout(template="plotly_dark", title="Carga ao longo dos últimos 42 dias", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

    logged = store.fetch_training_days(today - timedelta(days=13), today)
    if not logged.empty:
        st.caption("Registos recentes de carga diária")
        st.dataframe(logged[["date", "daily_load", "source", "notes"]], use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# MODULE 5 — Healthspan and biomarkers
# -----------------------------------------------------------------------------
elif top_nav == "🧬 Biomarcadores & Healthspan":
    st.subheader("🧬 Capacidade funcional e Healthspan")
    vo2_points = None
    if user_vo2 is not None and user_age is not None and user_gender in ("Masculino", "Feminino"):
        category, vo2_points = core.vo2_category(user_vo2, int(user_age), user_gender)
        st.metric("VO2max introduzido", f"{user_vo2:.1f} mL/kg/min", category)
    else:
        st.info("Para categorizar VO2max, completa idade, sexo de referência e VO2max no Perfil.")

    rhr_recent = base_df["RHR"].tail(14).dropna()
    rhr_mean_recent = float(rhr_recent.mean()) if len(rhr_recent) >= 1 else None
    sleep_recent = base_df["SleepHours"].tail(7).dropna()
    sleep_sd = float(sleep_recent.std(ddof=1)) if len(sleep_recent) >= 2 else (0.0 if len(sleep_recent) == 1 else None)
    workouts_7 = store.fetch_workouts(today - timedelta(days=6), today)
    active_min = float(workouts_7["duration_min"].sum()) if not workouts_7.empty else None
    hs = core.healthspan_score(vo2_points, rhr_mean_recent, sleep_sd, active_min)
    h1, h2, h3 = st.columns(3)
    h1.metric("FC repouso · média registada", _fmt(rhr_mean_recent, 1, " bpm"))
    h2.metric("Variabilidade da duração do sono", _fmt(sleep_sd, 2, " h") if sleep_sd is not None else "Acumular >1 noite")
    h3.metric("Minutos de treino registados · 7d", _fmt(active_min, 0, " min"))
    st.metric("Índice composto experimental", f"{hs['score']}/100" if hs["score"] is not None else "—")
    st.caption("Índice heurístico transparente e incompleto quando faltam dados. Não é uma idade biológica, score clínico, prognóstico ou medida validada de longevidade.")
    if hs["parts"]:
        hs_table = pd.DataFrame([{"Componente": key, "Pontos": values[0], "Máximo": values[1]}
                                 for key, values in hs["parts"].items()])
        st.dataframe(hs_table, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Registo de biomarcadores laboratoriais")
    with st.form("biomarker_form"):
        biomarker_keys = list(core.BIOMARKERS.keys())
        selected_key = st.selectbox("Biomarcador", biomarker_keys,
                                    format_func=lambda k: f"{core.BIOMARKERS[k]['label']} ({core.BIOMARKERS[k]['unit']})")
        c1, c2 = st.columns(2)
        biomarker_value_raw = c1.text_input("Resultado", placeholder="Valor numérico")
        biomarker_date = c2.date_input("Data da análise", value=today, max_value=today)
        c3, c4 = st.columns(2)
        low_raw = c3.text_input("Limite inferior do laboratório (opcional)")
        high_raw = c4.text_input("Limite superior do laboratório (opcional)")
        biomarker_note = st.text_input("Nota / laboratório / contexto (opcional)")
        save_biomarker = st.form_submit_button("Guardar resultado", use_container_width=True)
    if save_biomarker:
        try:
            val = _optional_float(biomarker_value_raw, "Resultado")
            if val is None:
                raise ValueError("Introduz um resultado numérico.")
            low = _optional_float(low_raw, "Limite inferior")
            high = _optional_float(high_raw, "Limite superior")
            result = core.evaluate_biomarker(selected_key, val, low, high)
            store.add_biomarker(biomarker_date, selected_key, val, core.BIOMARKERS[selected_key]["unit"], low, high, biomarker_note)
            st.success(f"Resultado guardado: {result['text']}.")
            if low is None and high is None:
                st.warning("A classificação usa apenas intervalos genéricos do Apex quando existem. Confirma sempre os intervalos do teu laboratório e o contexto clínico.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    biomarker_history = store.fetch_biomarkers()
    if not biomarker_history.empty:
        st.subheader("Histórico laboratorial")
        biomarker_history["Biomarcador"] = biomarker_history["key"].map(lambda k: core.BIOMARKERS.get(k, {}).get("label", k))
        st.dataframe(biomarker_history[["date", "Biomarcador", "value", "unit", "ref_low", "ref_high", "note"]],
                     use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# MODULE 6 — Race hub
# -----------------------------------------------------------------------------
elif top_nav == "🎯 Race Hub & Planeamento":
    st.subheader("🎯 Race Hub & Planeamento")
    with st.expander("Adicionar prova", expanded=False):
        with st.form("add_race_form"):
            race_name = st.text_input("Nome da prova")
            race_date = st.date_input("Data", value=today + timedelta(days=90), min_value=today)
            c1, c2, c3 = st.columns(3)
            race_dist = c1.number_input("Distância (km)", min_value=0.1, max_value=500.0, value=21.1)
            race_priority = c2.selectbox("Prioridade", ["A", "B", "C"])
            race_type = c3.selectbox("Tipo", ["Corrida", "10K", "Meia maratona", "Maratona", "Half Ironman", "Full Ironman", "Outro"])
            submit_race = st.form_submit_button("Guardar prova", use_container_width=True)
        if submit_race:
            try:
                store.add_race(race_name, race_date, race_dist, race_priority, race_type)
                st.success("Prova guardada.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    races = store.fetch_races()
    primary = None
    if races.empty:
        st.info("Ainda não existem provas registadas.")
    else:
        races["race_date_dt"] = pd.to_datetime(races["race_date"]).dt.date
        upcoming_a = races[(races["priority"] == "A") & (races["race_date_dt"] >= today)]
        upcoming = races[races["race_date_dt"] >= today]
        chosen = upcoming_a if not upcoming_a.empty else upcoming
        if chosen.empty:
            st.info("Todas as provas registadas estão no passado.")
        else:
            primary = chosen.sort_values("race_date").iloc[0]
            days_left = (primary["race_date_dt"] - today).days
            st.markdown(f"### Próximo objetivo: {escape(str(primary['name']))}")
            st.metric("Dias até à prova", days_left, f"{primary['dist_km']:.1f} km · prioridade {primary['priority']}")
        st.dataframe(races[["name", "race_date", "dist_km", "priority", "event_type"]], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Nutrição e calor — estimativas gerais")
    c1, c2, c3 = st.columns(3)
    duration_h = c1.number_input("Duração estimada (h)", min_value=0.25, max_value=24.0, value=2.0, step=0.25)
    temp = c2.slider("Temperatura (°C)", -5.0, 45.0, 24.0)
    humidity = c3.slider("Humidade (%)", 0.0, 100.0, 60.0)
    salty = st.checkbox("Suor visivelmente salgado / perdas elevadas de sódio", value=False)
    nutrition = core.calculate_race_nutrition(duration_h, temp, humidity, salty_sweater=salty)
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Hidratos", f"{nutrition['carbs_g_h'][0]}–{nutrition['carbs_g_h'][1]} g/h")
    n2.metric("Líquidos", f"{nutrition['fluid_ml_h'][0]}–{nutrition['fluid_ml_h'][1]} mL/h")
    n3.metric("Sódio", f"{nutrition['sodium_mg_h'][0]}–{nutrition['sodium_mg_h'][1]} mg/h")
    n4.metric("Indicador térmico aproximado", f"{nutrition['wbgt']} °C · {nutrition['heat']}")
    for warning in nutrition["warnings"]:
        st.caption(f"• {warning}")

    if user_weight is not None:
        with st.expander("Calculadora de sobrecarga de hidratos", expanded=False):
            carb_duration = st.number_input("Duração do evento (h)", min_value=0.25, max_value=48.0, value=2.0)
            protocol = core.carb_loading_protocol(user_weight, carb_duration)
            st.write(f"Referência geral: {protocol['g_per_kg'][0]:.0f}–{protocol['g_per_kg'][1]:.0f} g/kg/dia → {protocol['daily_g'][0]}–{protocol['daily_g'][1]} g/dia.")
            st.caption(protocol["note"])
    else:
        st.caption("Introduz o peso no Perfil para desbloquear o cálculo ilustrativo de hidratos.")

    st.divider()
    st.subheader("Pacing band")
    pace_raw = st.text_input("Ritmo-alvo (min:seg por km)", value="", placeholder="Ex.: 4:45")
    fallback_dist = float(primary["dist_km"]) if primary is not None else 10.0
    pace_dist = st.number_input("Distância para a tabela (km)", min_value=0.1, max_value=500.0, value=fallback_dist)
    pace_seconds = core.parse_pace(pace_raw) if pace_raw else None
    if pace_raw and pace_seconds is None:
        st.error("Formato inválido. Usa min:seg, por exemplo 4:45.")
    elif pace_seconds is not None:
        pacing = core.generate_pacing_band(pace_seconds, pace_dist, user_hrmax)
        st.dataframe(pacing, use_container_width=True, hide_index=True)
        st.caption("Os limites de FC são tetos ilustrativos, não zonas individuais validadas. A banda não inclui um perfil real de altimetria.")

    st.divider()
    st.subheader("Simulação de taper — 14 dias")
    if not load_complete_42:
        st.info("A simulação de taper só fica disponível quando existirem 42 dias consecutivos de carga registada.")
    else:
        current = core.compute_banister(last42_loads.tolist(), ctl_tc, atl_tc)
        normal_load = float(np.mean(last42_loads))
        taper = core.simulate_taper(current["ctl"][-1], current["atl"][-1], normal_load,
                                    days=14, ctl_tc=ctl_tc, atl_tc=atl_tc)
        fig = px.line(taper, x="Date", y=["CTL", "ATL", "TSB"], title="Projeção matemática de taper")
        fig.update_layout(template="plotly_dark", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Cenário matemático simplificado com base na carga recente, não um plano de taper individualizado.")

# -----------------------------------------------------------------------------
# MODULE 7 — Shoes
# -----------------------------------------------------------------------------
elif top_nav == "👟 Gestão de Sapatilhas":
    st.subheader("👟 Gestão de sapatilhas")
    with st.form("add_shoe_form"):
        model = st.text_input("Modelo da sapatilha")
        limit_km = st.number_input("Limite pessoal de referência (km)", min_value=50.0, max_value=2000.0, value=600.0)
        add_shoe_submit = st.form_submit_button("Adicionar sapatilha", use_container_width=True)
    if add_shoe_submit:
        try:
            store.add_shoe(model, limit_km)
            st.success("Sapatilha adicionada.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    shoes = store.fetch_shoes()
    if shoes.empty:
        st.info("Ainda não existem sapatilhas registadas.")
    else:
        for shoe in shoes.itertuples():
            status, tone, fraction = core.shoe_status(shoe.km_used, shoe.max_km)
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.write(f"**{shoe.model}**")
            c2.write(f"{shoe.km_used:.1f} / {shoe.max_km:.0f} km")
            c3.write(status)
            st.progress(float(np.clip(fraction, 0, 1)))
        st.divider()
        shoe_options = {f"{row.model} · {row.km_used:.0f}/{row.max_km:.0f} km": int(row.id) for row in shoes.itertuples()}
        with st.form("shoe_km_form"):
            selected_shoe_label = st.selectbox("Sapatilha usada", list(shoe_options.keys()))
            km_run = st.number_input("Distância a adicionar (km)", min_value=0.1, max_value=300.0, value=5.0)
            add_km_submit = st.form_submit_button("Registar quilómetros", use_container_width=True)
        if add_km_submit:
            try:
                store.increment_shoe_km(shoe_options[selected_shoe_label], km_run)
                st.success("Quilómetros adicionados.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.caption("O limite de quilometragem é pessoal e aproximado. Não existe um ponto universal em que uma sapatilha se torne insegura; considera conforto, integridade e sintomas.")

# -----------------------------------------------------------------------------
# MODULE 8 — Gemini AI coach
# -----------------------------------------------------------------------------
elif top_nav == "🤖 Coach IA Apex (Gemini)":
    st.subheader("🤖 Coach IA Apex")
    api_key = _secret("GEMINI_API_KEY")
    model_name = _secret("GEMINI_MODEL", "gemini-3.8-flash")
    if not api_key:
        st.info("Para ativar o coach, configura GEMINI_API_KEY nas variáveis de ambiente ou em .streamlit/secrets.toml.")
    else:
        if "coach_history" not in st.session_state:
            st.session_state.coach_history = []
        for message in st.session_state.coach_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        prompt = st.chat_input("Pergunta ao Coach Apex…")
        if prompt:
            st.session_state.coach_history.append({"role": "user", "content": prompt})
            recent_user_text = " ".join(
                m["content"] for m in st.session_state.coach_history[-8:] if m["role"] == "user"
            )
            red_flag = core.red_flag_check(recent_user_text)
            if red_flag:
                answer = red_flag
            else:
                facts = {
                    "data": today.isoformat(),
                    "mode": mode,
                    "readiness_apex_experimental": score,
                    "readiness_missing_factors": readiness_data["missing"],
                    "hrv_ms": hrv_curr,
                    "hrv_baseline_ms": hrv_mean,
                    "rhr_bpm": rhr_curr,
                    "rhr_baseline_bpm": rhr_mean,
                    "sleep_hours": sleep_hours_curr,
                    "sleep_score": sleep_curr,
                    "sleep_debt_vs_8h_last_7_logged_nights": sleep_debt["debt_h"],
                    "load_model_available": bool(load_complete_42),
                    "ctl": _clean_number(base_df["CTL"].iloc[-1]),
                    "atl": _clean_number(base_df["ATL"].iloc[-1]),
                    "tsb": _clean_number(base_df["TSB"].iloc[-1]),
                    "profile": {"age": user_age, "weight_kg": user_weight, "vo2max": user_vo2},
                    "important_limit": "Missing values are unknown, not zero. Do not diagnose or override symptoms.",
                }
                context = core.build_coach_context(facts)
                history_text = "\n".join(
                    f"{m['role']}: {m['content']}" for m in st.session_state.coach_history[-8:]
                )
                full_prompt = f"{core.COACH_SYSTEM_PROMPT}\n\nDados disponíveis:\n{context}\n\nConversa recente:\n{history_text}"
                try:
                    from google import genai
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(model=model_name, contents=full_prompt)
                    answer = response.text or "Não foi recebida uma resposta em texto."
                except Exception as exc:
                    answer = f"Não foi possível obter resposta do Gemini ({type(exc).__name__}). Verifica a chave, o modelo configurado e a ligação."
            st.session_state.coach_history.append({"role": "assistant", "content": answer})
            st.rerun()
        if st.button("Limpar conversa", use_container_width=False):
            st.session_state.coach_history = []
            st.rerun()
    st.caption("A IA pode errar. Não envies informação identificável nem uses respostas para diagnosticar sintomas ou alterar medicação.")

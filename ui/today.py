from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Dict, Optional
import pandas as pd
import streamlit as st

import data_store as store
import engine_core as core


def _fmt(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}{suffix}"


def _fmt_hours_to_hm(hours_val: Optional[float]) -> str:
    if hours_val is None or pd.isna(hours_val) or hours_val <= 0:
        return "—"
    total_minutes = int(round(float(hours_val) * 60))
    h = total_minutes // 60
    m = total_minutes % 60
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    elif h > 0:
        return f"{h}h"
    return f"{m}m"


def _fmt_minutes_diff(diff_min: Optional[float]) -> str:
    if diff_min is None or pd.isna(diff_min):
        return "—"
    diff_val = int(round(float(diff_min)))
    if diff_val > 0:
        return f"{diff_val} min"
    elif diff_val < 0:
        return f"+{abs(diff_val)} min"
    return "0 min"


def _optional_float(raw: Any, label: str, minimum: Optional[float] = None,
                    maximum: Optional[float] = None) -> Optional[float]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(str(raw).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label}: introduz um número válido ou deixa em branco.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}: o valor mínimo é {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}: o valor máximo é {maximum}.")
    return value


def render_today_page(base_df: pd.DataFrame, hrv_mean: Optional[float], rhr_mean: Optional[float],
                      hrv_curr: Optional[float], rhr_curr: Optional[float], sleep_curr: Optional[float],
                      sleep_hours_curr: Optional[float], sleep_target_curr: float,
                      garmin_readiness_curr: Optional[float], score: Optional[int],
                      decision: Dict[str, Any], hrv_context: Dict[str, Any], diff_minutes: Optional[float],
                      hrv_valid_days: int, sync_callback):

    head_col1, head_col2 = st.columns([3, 1])
    with head_col1:
        st.subheader("📝 Daily Check-In")
    with head_col2:
        if st.button("⚡ SYNC DATA", key="sync_data_top_btn", type="primary"):
            with st.spinner("Sincronizando Garmin..."):
                ok = sync_callback()
                if ok:
                    st.toast("Garmin sincronizada com sucesso!", icon="⚡")
                st.rerun()

    with st.expander("Registar métricas de hoje ou corrigir um dia anterior", expanded=False):
        with st.form("daily_checkin_form"):
            check_day = st.date_input("Data do registo", value=date.today(), max_value=date.today())
            c1, c2, c3, c4 = st.columns(4)
            hrv_input = c1.text_input("VRC noturna (ms)", placeholder="Em branco = sem dado")
            rhr_input = c2.text_input("FC repouso (bpm)", placeholder="Em branco = sem dado")
            sleep_score_input = c3.text_input("Sleep score (0-100)", placeholder="Em branco = sem dado")
            sleep_hours_input = c4.text_input("Sono (horas)", placeholder="Em branco = sem dado")
            st.caption("Diário subjetivo: 1 = baixo/mínimo; 5 = alto/máximo.")
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
    c3.metric("Sono", _fmt_hours_to_hm(sleep_hours_curr),
              f"Score: {_fmt(sleep_curr, 0)}" if sleep_curr is not None else "Score não registado")
    
    target_str = _fmt_hours_to_hm(sleep_target_curr)
    c4.metric("Défice de sono", _fmt_minutes_diff(diff_minutes),
              f"Meta Garmin recomendada: {target_str}" if sleep_target_curr else "Meta padrão 8h")

    st.divider()

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
    if sleep_hours_curr is not None:
        dur_str = _fmt_hours_to_hm(sleep_hours_curr)
        tgt_str = _fmt_hours_to_hm(sleep_target_curr)
        diff_str = _fmt_minutes_diff(diff_minutes)
        st.write(f"Duração do sono da última noite: **{dur_str}** vs Meta recomendada Garmin: **{tgt_str}** (Défice/Excedente: **{diff_str}**).")

    st.subheader("Qualidade e origem dos dados")
    st.write(f"Dias válidos de VRC antes de hoje: **{hrv_valid_days}**.")
    source_cols = [("VRC", "hrv_source"), ("FC repouso", "rhr_source"),
                   ("Sono", "sleep_hours_source"), ("Score sono", "sleep_score_source")]
    st.table(pd.DataFrame([{"Métrica": name,
                            "Origem hoje": str(latest.get(col)) if pd.notna(latest.get(col)) else "Sem dado"}
                           for name, col in source_cols]))

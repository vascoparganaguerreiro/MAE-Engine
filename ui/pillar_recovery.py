from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import streamlit as st

import data_store as store
import engine_core as core
from models.telemetry_schema import MetricValue
from ui.components import render_metric_field


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
    return f"{h}h {m}m" if h > 0 and m > 0 else f"{h}h" if h > 0 else f"{m}m"


def render_pillar_recovery(base_df: pd.DataFrame, hrv_mean: Optional[float], rhr_mean: Optional[float],
                           hrv_curr: Optional[float], rhr_curr: Optional[float], sleep_curr: Optional[float],
                           sleep_hours_curr: Optional[float], sleep_target_curr: Optional[float],
                           garmin_readiness_curr: Optional[float], score: Optional[int],
                           decision: Dict[str, Any], hrv_context: Dict[str, Any], diff_minutes: Optional[float],
                           hrv_valid_days: int, lang: str = "EN"):

    latest = base_df.iloc[-1]
    
    is_pt = (lang == "PT")
    
    # Textos i18n
    sec_title = "01 — Recuperação & Prontidão" if is_pt else "01 — Recovery & Readiness"
    sec_sub = "Fisiologia Autónoma · Qualidade do Sono · Prontidão Subjetiva · Interpretação" if is_pt else "Autonomic Physiology · Sleep Quality · Subjective Readiness · Interpretation"
    
    st.markdown(f"## {sec_title}")
    st.caption(sec_sub)

    # A. AUTONOMIC AND CARDIOVASCULAR RECOVERY
    st.markdown("### A. Autonomic & Cardiovascular Recovery" if not is_pt else "### A. Recuperação Autónoma & Cardiovascular")
    
    garmin_weekly_avg = latest.get("hrv_weekly_avg") if pd.notna(latest.get("hrv_weekly_avg")) else None
    effective_vrc_base = garmin_weekly_avg if garmin_weekly_avg is not None else hrv_mean
    hrv_sd = base_df["HRV"].tail(30).std(ddof=1) if len(base_df["HRV"].tail(30).dropna()) >= 7 else None
    if hrv_sd is not None and (pd.isna(hrv_sd) or hrv_sd <= 0):
        hrv_sd = None
    z_vrc = ((hrv_curr - effective_vrc_base) / hrv_sd
             if hrv_curr is not None and effective_vrc_base is not None and hrv_sd is not None else None)
    hrv_status = hrv_context.get("status", "Sem dados")
    rhr_trend = core.calculate_trend(base_df["RHR"].tail(7).tolist()) if "RHR" in base_df else {"text": "Dados insuficientes"}

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f"""
            <div style="background:#1b2229; border:1px solid #35414b; padding:16px; border-radius:12px;">
                <span style="color:#a3adb3; font-size:0.85rem; font-weight:600;">{'VRC NOTURNA (HRV)' if is_pt else 'NIGHTLY HRV'}</span><br>
                <span style="font-size:2.1rem; font-weight:800; color:#f5f5f0;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
                <hr style="border-color:#35414b; margin:8px 0;">
                <span style="font-size:0.82rem; color:#d1d6d4;">{'Média 7d:' if is_pt else '7-Day Avg:'} <b>{_fmt(effective_vrc_base, 0, ' ms')}</b></span><br>
                <span style="font-size:0.82rem; color:#d1d6d4;">{'Baseline Pessoal:' if is_pt else 'Personal Baseline:'} <b>{_fmt(hrv_mean, 1, ' ms')}</b></span><br>
                <span style="font-size:0.82rem; color:#d1d6d4;">{'Desvio Z-Score:' if is_pt else 'Z-Score Deviation:'} <b>{_fmt(z_vrc, 1, ' σ')}</b></span><br>
                <span style="font-size:0.8rem; color:#9aa5af; font-weight:600;">{'Estado:' if is_pt else 'Status:'} {escape(str(hrv_status))}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        rhr_diff = (rhr_curr - rhr_mean) if (rhr_curr is not None and rhr_mean is not None) else None
        rhr_status_color = "#9aa5af" if rhr_diff is None else ("#a9c0b4" if rhr_diff <= 0 else "#c8b28f" if rhr_diff <= 2.0 else "#b97871")
        rhr_trend_text = rhr_trend.get("text", "Dados insuficientes")
        st.markdown(
            f"""
            <div style="background:#1b2229; border:1px solid #35414b; padding:16px; border-radius:12px;">
                <span style="color:#a3adb3; font-size:0.85rem; font-weight:600;">{'FC REPOUSO (RHR)' if is_pt else 'RESTING HEART RATE'}</span><br>
                <span style="font-size:2.1rem; font-weight:800; color:#f5f5f0;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
                <hr style="border-color:#35414b; margin:8px 0;">
                <span style="font-size:0.82rem; color:#d1d6d4;">{'Baseline Pessoal:' if is_pt else 'Personal Baseline:'} <b>{_fmt(rhr_mean, 1, ' bpm')}</b></span><br>
                <span style="font-size:0.82rem; color:#d1d6d4;">{'Variação vs Base:' if is_pt else 'Diff vs Base:'} <b style="color:{rhr_status_color};">{_fmt(rhr_diff, 1, ' bpm')}</b></span><br>
                <span style="font-size:0.82rem; color:#d1d6d4;">{'Tendência 7d:' if is_pt else '7-Day Trend:'} <b>{escape(str(rhr_trend_text))}</b></span><br>
                <span style="font-size:0.8rem; color:{rhr_status_color}; font-weight:600;">{'Análise: Desvio monitorizado' if is_pt else 'Analysis: Monitored deviation'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        # Dynamic extraction from telemetry dataframe instead of fixed hardcoded integers
        bb_val = latest.get("body_battery") if pd.notna(latest.get("body_battery")) else None
        bb_recharge = latest.get("body_battery_charged") if pd.notna(latest.get("body_battery_charged")) else None
        stress_val = latest.get("stress_avg") if pd.notna(latest.get("stress_avg")) else None
        resp_val = latest.get("respiration_sleep_avg") if pd.notna(latest.get("respiration_sleep_avg")) else None

        bb_str = f"{int(bb_val)} / 100" if bb_val is not None else "—"
        recharge_str = f"+{int(bb_recharge)} pts" if bb_recharge is not None else "—"
        stress_str = f"{int(stress_val)}" if stress_val is not None else "—"
        resp_str = f"{_fmt(resp_val, 1)} brpm" if resp_val is not None else "—"

        st.markdown(
            f"""
            <div style="background:#1b2229; border:1px solid #35414b; padding:16px; border-radius:12px;">
                <span style="color:#a3adb3; font-size:0.85rem; font-weight:600;">{'MÉTRICAS SECUNDÁRIAS' if is_pt else 'SECONDARY METRICS'}</span><br>
                <span style="font-size:1.1rem; font-weight:700; color:#edf0ee;">Body Battery: <b>{bb_str}</b></span><br>
                <span style="font-size:0.82rem; color:#a9c0b4;">{'Recarga noturna:' if is_pt else 'Night Recharge:'} {recharge_str}</span><br>
                <hr style="border-color:#35414b; margin:8px 0;">
                <span style="font-size:0.85rem; color:#d1d6d4;">{'Stress Diurno:' if is_pt else 'Daytime Stress:'} <b>{stress_str}</b></span><br>
                <span style="font-size:0.85rem; color:#d1d6d4;">{'Respiração Noturna:' if is_pt else 'Overnight Respiration:'} <b>{resp_str}</b></span><br>
                <span style="font-size:0.75rem; color:#87939a;">{'Sinais Garmin Connect' if is_pt else 'Garmin Connect Telemetry'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # B. SLEEP AND OVERNIGHT RECOVERY
    st.markdown("### B. Sleep & Overnight Recovery" if not is_pt else "### B. Sono & Recuperação Noturna")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Duração do Sono" if is_pt else "Total Sleep Duration", _fmt_hours_to_hm(sleep_hours_curr))
    s2.metric("Garmin Sleep Score", _fmt(sleep_curr, 0))
    s3.metric("Défice de Sono" if is_pt else "Sleep Deficit / Surplus", f"{int(diff_minutes)} min deficit" if diff_minutes is not None and diff_minutes > 0 else f"{abs(int(diff_minutes))} min surplus" if diff_minutes is not None else "—")
    sleep_recent = pd.to_numeric(base_df["SleepHours"].tail(7), errors="coerce").dropna() if "SleepHours" in base_df else pd.Series(dtype=float)
    sleep_sd = float(sleep_recent.std(ddof=1)) if len(sleep_recent) >= 4 else None
    s4.metric("Consistência" if is_pt else "Sleep consistency", f"SD {_fmt(sleep_sd, 2)} h" if sleep_sd is not None else ("Dados insuficientes" if is_pt else "Insufficient data"))

    st.markdown("#### Sleep Stage Timeline (Wearable Estimate)" if not is_pt else "#### Fases do Sono (Estimativa Wearable)")
    
    # Dynamic calculations of sleep stages from latest entry
    deep_m = latest.get("sleep_deep_minutes") if pd.notna(latest.get("sleep_deep_minutes")) else None
    rem_m = latest.get("sleep_rem_minutes") if pd.notna(latest.get("sleep_rem_minutes")) else None
    light_m = latest.get("sleep_light_minutes") if pd.notna(latest.get("sleep_light_minutes")) else None
    awake_m = latest.get("sleep_awake_minutes") if pd.notna(latest.get("sleep_awake_minutes")) else None

    if all(v is not None for v in [deep_m, rem_m, light_m, awake_m]) and (deep_m + rem_m + light_m + awake_m) > 0:
        total_m = deep_m + rem_m + light_m + awake_m
        p_deep = int(round((deep_m / total_m) * 100))
        p_rem = int(round((rem_m / total_m) * 100))
        p_light = int(round((light_m / total_m) * 100))
        p_awake = int(round((awake_m / total_m) * 100))

        st.markdown(
            f"""
            <div style="display:flex; height:24px; border-radius:8px; overflow:hidden; margin-bottom:8px;">
                <div style="width:{p_deep}%; background:#536c80; text-align:center; color:#d8e0e4; font-size:0.75rem; line-height:24px;">{'Profundo' if is_pt else 'Deep'} ({p_deep}%)</div>
                <div style="width:{p_rem}%; background:#748b9b; text-align:center; color:#f5f5f0; font-size:0.75rem; line-height:24px;">REM ({p_rem}%)</div>
                <div style="width:{p_light}%; background:#71899a; text-align:center; color:#d8e0e4; font-size:0.75rem; line-height:24px;">{'Leve' if is_pt else 'Light'} ({p_light}%)</div>
                <div style="width:{p_awake}%; background:#b97871; text-align:center; color:#f5f5f0; font-size:0.75rem; line-height:24px;">{'Acordado' if is_pt else 'Awake'} ({p_awake}%)</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info("⚠️ **Sleep Stages Unavailable:** No detailed sleep stage breakdown recorded by Garmin for this date." if not is_pt else "⚠️ **Fases do Sono Indisponíveis:** Sem registo detalhado de fases do sono Garmin para esta data.")

    st.caption(
        "⚠️ **APEX Scientific Note:** Sleep stages are estimates derived from actigraphy and optical pulse rate variability, "
        "not direct brain activity measurements (Polysomnography / EEG). APEX prioritizes total sleep duration, regularity, and longitudinal trends over absolute stage precision."
        if not is_pt else
        "⚠️ **Nota Científica APEX:** As fases do sono são estimativas derivadas de actigrafia e variabilidade de pulso, "
        "não medindo atividade cerebral direta (Polissonografia / EEG). O APEX prioriza a duração total, regularidade e tendências longitudinais."
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # C. SUBJECTIVE RECOVERY
    st.markdown("### C. Subjective Recovery (Daily Check-In)" if not is_pt else "### C. Recuperação Subjetiva (Check-In Diário)")
    st.caption("Athlete perception is a primary biomarker. Log your daily subjective metrics to recalibrate APEX recommendations." if not is_pt else "A perceção do atleta é o biomarcador primário. Preenche os dados subjetivos para recalibrar as recomendações.")

    with st.form("subjective_checkin_form"):
        st.markdown("##### Subjective Metrics Log (Scale 1 to 5)" if not is_pt else "##### Registo de Métricas Subjetivas (Escala 1 a 5)")
        col_sub1, col_sub2, col_sub3, col_sub4, col_sub5 = st.columns(5)
        
        soreness = col_sub1.slider("Muscle Soreness (DOMS)" if not is_pt else "Dor Muscular (DOMS)", 1, 5, 3)
        fatigue = col_sub2.slider("General Fatigue" if not is_pt else "Fadiga Geral", 1, 5, 3)
        psych_stress = col_sub3.slider("Psychological Stress" if not is_pt else "Stress Psicológico", 1, 5, 3)
        mood = col_sub4.slider("Mood" if not is_pt else "Humor", 1, 5, 3)
        motivation = col_sub5.slider("Motivation to Train" if not is_pt else "Motivação p/ Treinar", 1, 5, 3)

        col_clin1, col_clin2 = st.columns(2)
        has_illness = col_clin1.checkbox("Illness symptoms (sore throat, fever)" if not is_pt else "Sintomas de doença (garganta, febre)")
        local_pain = col_clin2.text_input("Localized Pain / Injury" if not is_pt else "Dor Localizada / Lesão", placeholder="e.g. Achilles Tendon" if not is_pt else "ex: Tendão de Aquiles")

        btn_save_sub = st.form_submit_button("Save Subjective Check-In" if not is_pt else "Guardar Check-In Subjetivo", use_container_width=True)

        if btn_save_sub:
            sub_metrics = {
                "soreness": soreness,
                "stress": psych_stress,
                "mood": mood,
                "fatigue": fatigue,
                "motivation": motivation,
                "illness_symptoms": has_illness,
                "local_pain": local_pain.strip() or None,
            }
            store.upsert_daily_metrics(datetime.now(ZoneInfo("Europe/Prague")).date(), sub_metrics, source="manual")
            st.success("Subjective logs saved successfully!" if not is_pt else "Check-in guardado com sucesso!")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # D. DAILY RECOVERY INTERPRETATION
    st.markdown("### D. Daily Recovery Interpretation" if not is_pt else "### D. Interpretação Diária da Recuperação")
    
    latest_soreness = int(latest.get("soreness")) if pd.notna(latest.get("soreness")) else None
    illness_reported = bool(latest.get("illness_symptoms")) if pd.notna(latest.get("illness_symptoms")) else False
    local_pain_reported = str(latest.get("local_pain")) if pd.notna(latest.get("local_pain")) and str(latest.get("local_pain")).strip() else None

    st.markdown("#### Transparent Score Comparison" if not is_pt else "#### Comparação Transparente de Scores")
    rc1, rc2 = st.columns(2)

    with rc1:
        st.metric("Garmin Training Readiness (native)" if not is_pt else "Garmin Training Readiness (Garmin)",
                  _fmt(garmin_readiness_curr, 0, " / 100"))
        st.caption("Garmin's own score. Not used as an Apex input." if not is_pt else "Score próprio da Garmin. Não substitui o cálculo Apex.")
    with rc2:
        st.metric("Apex Readiness" if not is_pt else "Prontidão Apex", _fmt(score, 0, " / 100"))
        st.caption("Independent calculation; unavailable if data coverage is insufficient." if not is_pt else "Cálculo independente; indisponível se os dados forem insuficientes.")

    if illness_reported:
        interpretation_text = (
            "You reported illness symptoms. Wearable scores cannot rule out illness. Avoid using readiness scores as clearance to train; consider rest and seek medical advice based on symptom severity."
            if not is_pt else
            "Assinalaste sintomas de doença. Os scores do relógio não excluem doença nem autorizam treino. Considera repouso e procura avaliação clínica de acordo com a gravidade dos sintomas."
        )
        alert_tone = "border-left:4px solid #b97871;"
    elif latest_soreness is not None and latest_soreness >= 4:
        interpretation_text = (
            "You logged high muscle soreness. Consider how it changes during the warm-up and adjust the session if it affects movement or performance."
            if not is_pt else
            "Registaste dor muscular elevada. Reavalia durante o aquecimento e ajusta a sessão se afetar o movimento ou desempenho."
        )
        alert_tone = "border-left:4px solid #c8b28f;"
    elif hrv_curr is None and rhr_curr is None and sleep_hours_curr is None:
        interpretation_text = (
            "Not enough current recovery data is available to interpret today's status. Sync Garmin or add a manual check-in."
            if not is_pt else
            "Não existem dados atuais suficientes para interpretar a recuperação de hoje. Sincroniza a Garmin ou regista um check-in manual."
        )
        alert_tone = "border-left:4px solid #9aa5af;"
    else:
        pieces = []
        if hrv_context.get("status") and hrv_context.get("status") != "Sem dados":
            pieces.append(f"HRV: {hrv_context.get('status')}.")
        elif hrv_curr is not None:
            pieces.append("HRV: personal baseline not yet available.")
        if rhr_curr is not None and rhr_mean is not None:
            pieces.append(f"Resting HR is {rhr_curr - rhr_mean:+.1f} bpm vs personal baseline.")
        if sleep_hours_curr is not None:
            if diff_minutes is None:
                pieces.append("Sleep target is not available, so deficit/surplus was not calculated.")
            else:
                pieces.append(f"Sleep was {abs(int(diff_minutes))} minutes {'below' if diff_minutes > 0 else 'above'} the recorded target.")
        if local_pain_reported:
            pieces.append(f"Reported localised pain: {local_pain_reported}.")
        interpretation_text = " ".join(pieces) if pieces else ("No interpretable current signals." if not is_pt else "Sem sinais atuais interpretáveis.")
        alert_tone = "border-left:4px solid #a9c0b4;"

    st.markdown(
        f"""
        <div style="background:#1b2229; border:1px solid #39454a; border-radius:12px; padding:16px; {alert_tone}">
            <b style="font-size:1.05rem; color:#f5f5f0;">{'APEX Recovery Interpretation:' if not is_pt else 'Interpretação de Recuperação APEX:'}</b><br>
            <span style="font-size:0.95rem; color:#edf0ee; line-height:1.5;">{interpretation_text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

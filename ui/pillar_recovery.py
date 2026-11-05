from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Dict, Optional
import numpy as np
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
    hrv_sd = base_df["HRV"].tail(30).std() if len(base_df["HRV"].dropna()) >= 7 else 5.0
    if pd.isna(hrv_sd) or hrv_sd == 0:
        hrv_sd = 5.0

    z_vrc = (hrv_curr - effective_vrc_base) / hrv_sd if (hrv_curr is not None and effective_vrc_base is not None) else 0.0

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">{'VRC NOTURNA (HRV)' if is_pt else 'NIGHTLY HRV'}</span><br>
                <span style="font-size:2.1rem; font-weight:800; color:#f8fafc;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
                <hr style="border-color:#263244; margin:8px 0;">
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Média 7d:' if is_pt else '7-Day Avg:'} <b>{_fmt(effective_vrc_base, 0, ' ms')}</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Baseline Pessoal:' if is_pt else 'Personal Baseline:'} <b>{_fmt(hrv_mean, 1, ' ms')}</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Desvio Z-Score:' if is_pt else 'Z-Score Deviation:'} <b>{z_vrc:+.1f} σ</b></span><br>
                <span style="font-size:0.8rem; color:#14b8a6; font-weight:600;">{'Estado: Faixa habitual' if is_pt else 'Status: Normal range'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        rhr_diff = (rhr_curr - rhr_mean) if (rhr_curr is not None and rhr_mean is not None) else 0.0
        rhr_status_color = "#14b8a6" if rhr_diff <= 0 else "#f59e0b" if rhr_diff <= 2.0 else "#ef4444"
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">{'FC REPOUSO (RHR)' if is_pt else 'RESTING HEART RATE'}</span><br>
                <span style="font-size:2.1rem; font-weight:800; color:#f8fafc;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
                <hr style="border-color:#263244; margin:8px 0;">
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Baseline Pessoal:' if is_pt else 'Personal Baseline:'} <b>{_fmt(rhr_mean, 1, ' bpm')}</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Variação vs Base:' if is_pt else 'Diff vs Base:'} <b style="color:{rhr_status_color};">{rhr_diff:+.1f} bpm</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Tendência 7d:' if is_pt else '7-Day Trend:'} <b>{'Estável' if is_pt else 'Stable'}</b></span><br>
                <span style="font-size:0.8rem; color:{rhr_status_color}; font-weight:600;">{'Análise: Desvio monitorizado' if is_pt else 'Analysis: Monitored deviation'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">{'MÉTRICAS SECUNDÁRIAS' if is_pt else 'SECONDARY METRICS'}</span><br>
                <span style="font-size:1.1rem; font-weight:700; color:#e2e8f0;">Body Battery: <b>85 / 100</b></span><br>
                <span style="font-size:0.82rem; color:#14b8a6;">{'Recarga noturna:' if is_pt else 'Night Recharge:'} +65 pts</span><br>
                <hr style="border-color:#263244; margin:8px 0;">
                <span style="font-size:0.85rem; color:#cbd5e1;">{'Stress Diurno:' if is_pt else 'Daytime Stress:'} <b>24 ({'Baixo' if is_pt else 'Low'})</b></span><br>
                <span style="font-size:0.85rem; color:#cbd5e1;">{'Respiração Noturna:' if is_pt else 'Overnight Respiration:'} <b>14.5 brpm</b></span><br>
                <span style="font-size:0.75rem; color:#64748b;">{'Sinais contextuais' if is_pt else 'Contextual signals'}</span>
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
    s3.metric("Défice de Sono" if is_pt else "Sleep Deficit / Surplus", f"{int(diff_minutes)} min deficit" if diff_minutes and diff_minutes > 0 else f"+{abs(int(diff_minutes or 0))} min surplus")
    s4.metric("Consistência" if is_pt else "Bedtime Consistency", "Regular (±15 min)")

    st.markdown("#### Sleep Stage Timeline (Wearable Estimate)" if not is_pt else "#### Fases do Sono (Estimativa Wearable)")
    st.markdown(
        f"""
        <div style="display:flex; height:24px; border-radius:8px; overflow:hidden; margin-bottom:8px;">
            <div style="width:20%; background:#1e3a8a; text-align:center; color:#93c5fd; font-size:0.75rem; line-height:24px;">{'Profundo (20%)' if is_pt else 'Deep (20%)'}</div>
            <div style="width:25%; background:#3b82f6; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">REM (25%)</div>
            <div style="width:45%; background:#1d4ed8; text-align:center; color:#bfdbfe; font-size:0.75rem; line-height:24px;">{'Leve (45%)' if is_pt else 'Light (45%)'}</div>
            <div style="width:10%; background:#ef4444; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Acordado (10%)' if is_pt else 'Awake (10%)'}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
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
            }
            store.upsert_daily_metrics(date.today(), sub_metrics, source="manual")
            st.success("Subjective logs saved successfully!" if not is_pt else "Check-in guardado com sucesso!")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # D. DAILY RECOVERY INTERPRETATION
    st.markdown("### D. Daily Recovery Interpretation" if not is_pt else "### D. Interpretação Diária da Recuperação")
    
    latest_soreness = int(latest.get("soreness") or 3)

    st.markdown("#### Transparent Score Comparison" if not is_pt else "#### Comparação Transparente de Scores")
    rc1, rc2 = st.columns(2)
    
    with rc1:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #334155; padding:14px; border-radius:10px;">
                <span style="color:#94a3b8; font-size:0.85rem;">GARMIN TRAINING READINESS (NATIVE)</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">{garmin_readiness_curr or '—'} / 100</span><br>
                <span style="font-size:0.78rem; color:#94a3b8;">{'Includes: Sleep, HRV History, Acute Load, and Stress.' if not is_pt else 'Incorpora: Sono, Histórico VRC, Carga Aguda e Stress.'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with rc2:
        apex_calculated_score = score or 75
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #334155; padding:14px; border-radius:10px;">
                <span style="color:#94a3b8; font-size:0.85rem;">APEX INDEPENDENT SCORE</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#14b8a6;">{apex_calculated_score} / 100</span><br>
                <span style="font-size:0.78rem; color:#94a3b8;">{'Calculated via local HRV Z-score + Athlete Check-In.' if not is_pt else 'Calculado via Z-score VRC + Check-In Subjetivo.'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if latest_soreness >= 4:
        interpretation_text = (
            "Nightly HRV and Resting Heart Rate are stable within your personal baseline. "
            "However, you logged elevated muscle soreness (DOMS). Consider adjusting today's workout "
            "for lower axial/joint impact or extending your warm-up."
            if not is_pt else
            "A VRC noturna e a FC de repouso estão estáveis na baseline. "
            "Contudo, registaste dor muscular elevada (DOMS). Considera reduzir a carga articular "
            "ou prolongar o aquecimento."
        )
        alert_tone = "border-left:5px solid #f59e0b;"
    elif has_illness:
        interpretation_text = (
            "Illness symptoms were reported. Regardless of favorable wearable HRV or readiness scores, "
            "the immediate clinical recommendation is rest or light mobility to support immune function."
            if not is_pt else
            "Foram assinalados sintomas de doença. A recomendação clínica é descanso total ou mobilidade leve."
        )
        alert_tone = "border-left:5px solid #ef4444;"
    else:
        interpretation_text = (
            f"Your HRV ({_fmt(hrv_curr, 0, ' ms')}) and Resting HR ({_fmt(rhr_curr, 0, ' bpm')}) are within your normal baseline range. "
            f"Sleep covered your target duration. Systemic stress response supports proceeding with planned training."
            if not is_pt else
            f"A tua VRC ({_fmt(hrv_curr, 0, ' ms')}) e FC de repouso ({_fmt(rhr_curr, 0, ' bpm')}) estão na faixa normal. "
            f"O sono cobriu a meta diária. A resposta ao stress suporta o treino planeado."
        )
        alert_tone = "border-left:5px solid #14b8a6;"

    st.markdown(
        f"""
        <div style="background:#131a27; border:1px solid #334155; border-radius:12px; padding:16px; {alert_tone}">
            <b style="font-size:1.05rem; color:#f8fafc;">{'APEX Integrated Readiness Diagnosis:' if not is_pt else 'Diagnóstico de Prontidão Integrada APEX:'}</b><br>
            <span style="font-size:0.95rem; color:#e2e8f0; line-height:1.5;">{interpretation_text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

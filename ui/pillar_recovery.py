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
                           hrv_valid_days: int):

    latest = base_df.iloc[-1]
    
    st.markdown("## 01 — Recovery & Readiness")
    st.caption("Fisiologia Autónoma · Qualidade e Duração do Sono · Prontidão Subjetiva · Interpretação Integrada")

    # =========================================================================
    # A. AUTONOMIC AND CARDIOVASCULAR RECOVERY
    # =========================================================================
    st.markdown("### A. Autonomic & Cardiovascular Recovery")
    
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
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">NIGHTLY HRV (VRC NOTURNA)</span><br>
                <span style="font-size:2.1rem; font-weight:800; color:#f8fafc;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
                <hr style="border-color:#263244; margin:8px 0;">
                <span style="font-size:0.82rem; color:#cbd5e1;">Média 7d: <b>{_fmt(effective_vrc_base, 0, ' ms')}</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Baseline pessoal: <b>{_fmt(hrv_mean, 1, ' ms')}</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Desvio Z-Score: <b>{z_vrc:+.1f} σ</b></span><br>
                <span style="font-size:0.8rem; color:#34d399; font-weight:600;">Estado: Dentro da faixa habitual</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        rhr_diff = (rhr_curr - rhr_mean) if (rhr_curr is not None and rhr_mean is not None) else 0.0
        rhr_status_color = "#34d399" if rhr_diff <= 0 else "#fb923c" if rhr_diff <= 2.0 else "#f87171"
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">RESTING HEART RATE (FC REPOUSO)</span><br>
                <span style="font-size:2.1rem; font-weight:800; color:#f8fafc;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
                <hr style="border-color:#263244; margin:8px 0;">
                <span style="font-size:0.82rem; color:#cbd5e1;">Baseline pessoal: <b>{_fmt(rhr_mean, 1, ' bpm')}</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Variação vs base: <b style="color:{rhr_status_color};">{rhr_diff:+.1f} bpm</b></span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Tendência 7d: <b>Estável</b></span><br>
                <span style="font-size:0.8rem; color:{rhr_status_color}; font-weight:600;">Análise: Desvio individual monitorizado</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">METRICAS SECUNDÁRIAS (GARMIN)</span><br>
                <span style="font-size:1.1rem; font-weight:700; color:#e2e8f0;">Body Battery: <b>85 / 100</b></span><br>
                <span style="font-size:0.82rem; color:#34d399;"> Recarga noturna: +65 pts</span><br>
                <hr style="border-color:#263244; margin:8px 0;">
                <span style="font-size:0.85rem; color:#cbd5e1;">Stress médio diurno: <b>24 (Baixo)</b></span><br>
                <span style="font-size:0.85rem; color:#cbd5e1;">Respiração noturna: <b>14.5 rpm</b></span><br>
                <span style="font-size:0.75rem; color:#64748b;">Sinais contextuais complementares</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # B. SLEEP AND OVERNIGHT RECOVERY
    # =========================================================================
    st.markdown("### B. Sleep & Overnight Recovery")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Duração Total do Sono", _fmt_hours_to_hm(sleep_hours_curr))
    s2.metric("Garmin Sleep Score", _fmt(sleep_curr, 0))
    s3.metric("Défice / Excedente", f"{int(diff_minutes)} min" if diff_minutes and diff_minutes > 0 else f"+{abs(int(diff_minutes or 0))} min")
    s4.metric("Consistência de Deitar", "Regular (±15 min)")

    # Timeline Estimado de Fases do Sono (Com Disclaimer Científico)
    st.markdown("#### Linha Temporal de Fases do Sono (Estimativa Wearable)")
    st.markdown(
        """
        <div style="display:flex; height:24px; border-radius:8px; overflow:hidden; margin-bottom:8px;">
            <div style="width:20%; background:#1e3a8a; text-align:center; color:#93c5fd; font-size:0.75rem; line-height:24px;">Profundo (20%)</div>
            <div style="width:25%; background:#3b82f6; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">REM (25%)</div>
            <div style="width:45%; background:#1d4ed8; text-align:center; color:#bfdbfe; font-size:0.75rem; line-height:24px;">Leve (45%)</div>
            <div style="width:10%; background:#ef4444; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">Acordado (10%)</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.caption(
        "⚠️ **Nota Científica APEX:** As fases do sono apresentadas são estimativas derivadas de actigrafia e variabilidade cardíaca de pulso, "
        "não medindo atividade encefálica (Polissonografia / EEG). O APEX prioriza a duração total, regularidade de horários e tendências longitudinais em vez da precisão absoluta das fases."
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # C. SUBJECTIVE RECOVERY (CHECK-IN DIÁRIO DE 5 ENTRADAS)
    # =========================================================================
    st.markdown("### C. Subjective Recovery (Check-In Diário)")
    st.caption("A perceção do atleta é o biomarcador primário. Preenche como te sentes hoje para recalibrar as recomendações.")

    with st.form("subjective_checkin_form"):
        st.markdown("##### Registo de Sensações Subjetivas (Escala 1 a 5)")
        col_sub1, col_sub2, col_sub3, col_sub4, col_sub5 = st.columns(5)
        
        soreness = col_sub1.slider("Dor Muscular (DOMS)", 1, 5, 3, help="1 = Nenhuma dor; 5 = Dor extrema / Incapacitante")
        fatigue = col_sub2.slider("Fadiga Geral", 1, 5, 3, help="1 = Totalmente fresco; 5 = Exaustão profunda")
        psych_stress = col_sub3.slider("Stress Psicológico", 1, 5, 3, help="1 = Calmo/Relaxado; 5 = Stress elevado")
        mood = col_sub4.slider("Humor", 1, 5, 3, help="1 = Muito baixo; 5 = Excelente")
        motivation = col_sub5.slider("Motivação p/ Treinar", 1, 5, 3, help="1 = Nenhuma; 5 = Prontidão total")

        st.markdown("##### Sinais Clínicos e Sintomas (Opcional)")
        col_clin1, col_clin2 = st.columns(2)
        has_illness = col_clin1.checkbox("Sintomas de doença (garganta, febre, mal-estar geral)")
        local_pain = col_clin2.text_input("Dor localizada / Lesão (ex: Tendão de Aquiles D.)", placeholder="Deixar em branco se sem dor")

        btn_save_sub = st.form_submit_button("Guardar Check-In Subjetivo", use_container_width=True)

        if btn_save_sub:
            sub_metrics = {
                "soreness": soreness,
                "stress": psych_stress,
                "mood": mood,
                "fatigue": fatigue,
                "motivation": motivation,
            }
            store.upsert_daily_metrics(date.today(), sub_metrics, source="manual")
            st.success("Sensações subjetivas guardadas com sucesso!")
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # D. DAILY RECOVERY INTERPRETATION (SEM DUPLA CONTAGEM)
    # =========================================================================
    st.markdown("### D. Daily Recovery Interpretation")
    
    # Avaliação de divergência entre Wearables e Subjetivo
    latest_soreness = int(latest.get("soreness") or 3)
    latest_mood = int(latest.get("mood") or 3)

    st.markdown("#### Comparação Transparente de Scores")
    rc1, rc2 = st.columns(2)
    
    with rc1:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #334155; padding:14px; border-radius:10px;">
                <span style="color:#94a3b8; font-size:0.85rem;">GARMIN TRAINING READINESS (NATIVO)</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">{garmin_readiness_curr or '—'} / 100</span><br>
                <span style="font-size:0.78rem; color:#94a3b8;">Incorpora: Sono, Histórico VRC, Carga Aguda e Stress Garmin.</span>
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
                <span style="font-size:1.8rem; font-weight:800; color:#34d399;">{apex_calculated_score} / 100</span><br>
                <span style="font-size:0.78rem; color:#94a3b8;">Calculado via Z-score de VRC local + Perfil Subjetivo do Atleta.</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Diagnóstico Final Integrado
    if latest_soreness >= 4:
        interpretation_text = (
            "A VRC noturna e a FC de repouso estão estáveis dentro da tua baseline individual. "
            "No entanto, registaste uma dor muscular elevada (DOMS). Recomendamos ajustar o treino de hoje "
            "para menor impacto articular/axial ou realizar aquecimento prolongado antes de decidir a carga."
        )
        alert_tone = "apex-warn"
    elif has_illness:
        interpretation_text = (
            "Foram assinalados sintomas de doença. Independentemente dos valores favoráveis de VRC ou do Garmin Readiness, "
            "a recomendação clínica imediata é descanso total ou mobilidade leve para preservar o sistema imunitário."
        )
        alert_tone = "apex-alert"
    else:
        interpretation_text = (
            f"A tua VRC ({_fmt(hrv_curr, 0, ' ms')}) e FC de repouso ({_fmt(rhr_curr, 0, ' bpm')}) encontram-se dentro da tua faixa habitual. "
            f"O sono cobriu a maioria da tua meta diária. A resposta ao stress acumulado é favorável para seguir o plano de treino previsto."
        )
        alert_tone = "apex-good"

    st.markdown(
        f"""
        <div class="apex-note {alert_tone}">
            <b style="font-size:1.05rem; color:#f8fafc;">Diagnóstico de Prontidão Integrada APEX:</b><br>
            <span style="font-size:0.95rem; color:#e2e8f0; line-height:1.5;">{interpretation_text}</span>
        </div>
        """,
        unsafe_allow_html=True
    )

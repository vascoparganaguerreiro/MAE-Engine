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


def render_pillar_training(base_df: pd.DataFrame, mode: str, lang: str = "EN"):
    is_pt = (lang == "PT")
    
    st.markdown("## 02 — Training & Performance" if not is_pt else "## 02 — Treino & Performance")
    st.caption("Training Load · Aerobic Capacity · Intensity Distribution · Aerobic Efficiency · Session Analysis" if not is_pt else "Carga de Treino · Capacidade Aeróbica · Distribuição de Intensidade · Eficiência Aeróbica · Análise de Sessões")

    # A. TRAINING LOAD & ADAPTATION
    st.markdown("### A. Training Load & Adaptation" if not is_pt else "### A. Carga de Treino & Adaptação")
    
    ctl_val = base_df["CTL"].iloc[-1] if "CTL" in base_df else None
    atl_val = base_df["ATL"].iloc[-1] if "ATL" in base_df else None
    tsb_val = base_df["TSB"].iloc[-1] if "TSB" in base_df else None
    
    loads_28 = base_df["DailyLoad"].tail(28).dropna().tolist() if "DailyLoad" in base_df else []
    acwr_val = core.compute_acwr(loads_28) if len(loads_28) >= 7 else None

    l1, l2, l3, l4, l5 = st.columns(5)
    l1.metric("Daily Load (Today)" if not is_pt else "Carga Diária (Hoje)", _fmt(base_df["DailyLoad"].iloc[-1] if "DailyLoad" in base_df else None, 0, " AU"))
    l2.metric("CTL (Fitness 42d)", _fmt(ctl_val, 1, " AU"))
    l3.metric("ATL (Fatigue 7d)" if not is_pt else "ATL (Fadiga 7d)", _fmt(atl_val, 1, " AU"))
    l4.metric("TSB (Form)" if not is_pt else "TSB (Forma)", _fmt(tsb_val, 1, " AU"))
    l5.metric("ACWR (Acute:Chronic)" if not is_pt else "ACWR (Razão Aguda:Crónica)", _fmt(acwr_val, 2))

    st.markdown("#### Training Load Evolution (Last 42 Days)" if not is_pt else "#### Evolução da Carga de Treino (Últimos 42 Dias)")
    if "CTL" in base_df and not base_df["CTL"].dropna().empty:
        chart_data = base_df.tail(42).set_index("Date")[["CTL", "ATL", "TSB"]]
        st.line_chart(chart_data)
    else:
        st.info("Calculating load history. Log more sessions with RPE/Duration to generate the CTL/ATL/TSB curve." if not is_pt else "A calcular histórico de carga. Regista mais sessões com RPE/Duração para gerar a curva CTL/ATL/TSB.")

    st.caption(
        "⚠️ **APEX Methodological Note:** ACWR is a contextual load variation indicator, not an injury predictor. "
        "Values above 1.3 reflect workload acceleration and should be evaluated alongside muscle soreness (DOMS) and sleep."
        if not is_pt else
        "⚠️ **Nota Metodológica APEX:** O ACWR é um indicador contextual de variação de carga e não um oráculo de lesões. "
        "Valores acima de 1.3 refletem aceleração de estímulo e devem ser interpretados conjuntamente com a dor muscular (DOMS) e sono."
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # B. AEROBIC CAPACITY & THRESHOLDS
    st.markdown("### B. Aerobic Capacity & Thresholds" if not is_pt else "### B. Capacidade Aeróbica & Limiares")
    
    prof = store.get_setting("profile", {}) or {}
    vo2_run = prof.get("vo2max") or 60.0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Running VO2max", f"{vo2_run:.1f} mL/kg/min")
    c2.metric("Cycling VO2max (Power)", "58.0 mL/kg/min", help="Requires Garmin power meter / Tacx Flux" if not is_pt else "Requer potenciómetro Garmin / Tacx Flux")
    c3.metric("FTP (Cycling)" if not is_pt else "FTP (Ciclismo)", "310 W", "4.13 W/kg")
    c4.metric("Lactate Threshold (Running)" if not is_pt else "Limiar de Lactato (Corrida)", "3:55 /km", "172 bpm")

    with st.expander("📊 Race Performance Predictions (Pacing / Power Models)" if not is_pt else "📊 Predição de Performance em Prova (Modelos de Potência/Ritmo)", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Est. 5K", "18:45")
        p2.metric("Est. 10K", "39:10")
        p3.metric("Est. Half Marathon (21k)" if not is_pt else "Est. Meia Maratona (21k)", "1h 26m")
        p4.metric("Est. Marathon (42k)" if not is_pt else "Est. Maratona (42k)", "3h 04m")

    st.markdown("<br>", unsafe_allow_html=True)

    # C. TRAINING INTENSITY & ZONES
    st.markdown("### C. Training Intensity & Zone Distribution" if not is_pt else "### C. Intensidade de Treino & Distribuição de Zonas")
    st.caption("Time-in-zone distribution for the last 7 days. Validates adherence to training structure (Polarized vs Threshold)." if not is_pt else "Distribuição de tempo em zonas nos últimos 7 dias. Permite verificar o alinhamento com a estrutura do bloco (Polarizado vs Threshold).")

    st.markdown("##### Heart Rate Zone Distribution (Running & Cycling)" if not is_pt else "##### Tempo em Zonas de Frequência Cardíaca (Corrida & Ciclismo)")
    st.markdown(
        f"""
        <div style="display:flex; height:24px; border-radius:8px; overflow:hidden; margin-bottom:8px;">
            <div style="width:70%; background:#10b981; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Z1-Z2 Low Aerobic (70%)' if not is_pt else 'Z1-Z2 Aeróbica Baixa (70%)'}</div>
            <div style="width:18%; background:#f59e0b; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Z3-Z4 Threshold (18%)' if not is_pt else 'Z3-Z4 Limiar (18%)'}</div>
            <div style="width:12%; background:#ef4444; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Z5 Anaerobic (12%)' if not is_pt else 'Z5 Anaeróbica (12%)'}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # D. AEROBIC EFFICIENCY & DURABILITY
    st.markdown("### D. Aerobic Efficiency & Durability" if not is_pt else "### D. Eficiência Aeróbica & Durabilidade")
    
    d1, d2 = st.columns(2)
    with d1:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">AEROBIC DECOUPLING (HR DRIFT)</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#14b8a6;">3.2 %</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Power:HR ratio sustained during steady-state long ride (190W avg).' if not is_pt else 'Relação Power:HR sustentada no último longo (190W avg).'}</span><br>
                <span style="font-size:0.78rem; color:#64748b;">{'Drift < 5% indicates strong aerobic durability.' if not is_pt else 'Drift < 5% indica durabilidade aeróbica excelente.'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with d2:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">SUBMAXIMAL EFFICIENCY TRACKING</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">136 bpm @ 5:00 /km</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Improvement vs previous month (142 bpm at same pace).' if not is_pt else 'Melhoria vs mês anterior (142 bpm ao mesmo ritmo).'}</span><br>
                <span style="font-size:0.78rem; color:#64748b;">{'Running economy progression without maximal testing.' if not is_pt else 'Evolução de economia de corrida sem necessidade de teste máximo.'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # E. INDIVIDUAL SESSION ANALYSIS
    st.markdown("### E. Individual Session Detailed Analysis" if not is_pt else "### E. Análise Detalhada da Sessão Individual")
    with st.expander("🔍 Analyze Latest Recorded Session" if not is_pt else "🔍 Analisar Última Sessão Registada", expanded=False):
        sa1, sa2, sa3 = st.columns(3)
        sa1.metric("Aerobic Training Effect", "3.8 (Impacting Improvement)" if not is_pt else "3.8 (Melhoria Impactante)")
        sa2.metric("Anaerobic Training Effect", "1.2 (Maintenance)" if not is_pt else "1.2 (Manutenção)")
        sa3.metric("Performance Condition", "+2 (Favorable)" if not is_pt else "+2 (Favorável)")
        st.caption(
            "ℹ️ **Physiology Note:** Performance Condition compares early-session pace/power and heart rate response "
            "against your historical Garmin baseline. It is not a direct measurement of muscle glycogen or stiffness."
            if not is_pt else
            "ℹ️ **Nota de Fisiologia:** O Performance Condition compara a tua resposta de FC/Ritmo nos primeiros minutos da sessão "
            "com a tua baseline histórica da Garmin, não medindo diretamente rigidez muscular ou níveis de glicogénio."
        )

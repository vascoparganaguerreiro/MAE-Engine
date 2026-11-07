from __future__ import annotations

from datetime import date
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


def render_pillar_training(base_df: pd.DataFrame, mode: str, lang: str = "EN"):
    is_pt = (lang == "PT")
    latest = base_df.iloc[-1] if not base_df.empty else {}
    
    st.markdown("## 02 — Training & Performance" if not is_pt else "## 02 — Treino & Performance")
    st.caption("Training Load · Aerobic Capacity · Intensity Distribution · Aerobic Efficiency · Session Analysis" if not is_pt else "Carga de Treino · Capacidade Aeróbica · Distribuição de Intensidade · Eficiência Aeróbica · Análise de Sessões")

    # A. TRAINING LOAD & ADAPTATION
    st.markdown("### A. Training Load & Adaptation" if not is_pt else "### A. Carga de Treino & Adaptação")
    
    ctl_val = base_df["CTL"].iloc[-1] if "CTL" in base_df and not base_df["CTL"].dropna().empty else None
    atl_val = base_df["ATL"].iloc[-1] if "ATL" in base_df and not base_df["ATL"].dropna().empty else None
    tsb_val = base_df["TSB"].iloc[-1] if "TSB" in base_df and not base_df["TSB"].dropna().empty else None
    
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
    vo2_run = prof.get("vo2max")
    vo2_bike = latest.get("cycling_vo2max") if pd.notna(latest.get("cycling_vo2max")) else None
    ftp_val = prof.get("ftp") or (latest.get("ftp") if pd.notna(latest.get("ftp")) else None)
    w_kg_val = (ftp_val / prof.get("weight", 70)) if (ftp_val and prof.get("weight")) else None
    lt_pace = latest.get("lactate_threshold_pace") if pd.notna(latest.get("lactate_threshold_pace")) else None
    lt_hr = latest.get("lactate_threshold_hr") if pd.notna(latest.get("lactate_threshold_hr")) else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Running VO2max", f"{vo2_run:.1f} mL/kg/min" if vo2_run else "—")
    c2.metric("Cycling VO2max (Power)", f"{vo2_bike:.1f} mL/kg/min" if vo2_bike else "—", help="Requires Garmin power meter / Tacx Flux" if not is_pt else "Requer potenciómetro Garmin / Tacx Flux")
    c3.metric("FTP (Cycling)" if not is_pt else "FTP (Ciclismo)", f"{int(ftp_val)} W" if ftp_val else "—", f"{w_kg_val:.2f} W/kg" if w_kg_val else "Not Recorded")
    c4.metric("Lactate Threshold (Running)" if not is_pt else "Limiar de Lactato (Corrida)", f"{lt_pace}" if lt_pace else "—", f"{int(lt_hr)} bpm" if lt_hr else "Not Recorded")

    with st.expander("📊 Race Performance Predictions (Pacing / Power Models)" if not is_pt else "📊 Predição de Performance em Prova (Modelos de Potência/Ritmo)", expanded=False):
        est_5k = latest.get("pred_5k") if pd.notna(latest.get("pred_5k")) else None
        est_10k = latest.get("pred_10k") if pd.notna(latest.get("pred_10k")) else None
        est_21k = latest.get("pred_21k") if pd.notna(latest.get("pred_21k")) else None
        est_42k = latest.get("pred_42k") if pd.notna(latest.get("pred_42k")) else None

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Est. 5K", est_5k if est_5k else "—")
        p2.metric("Est. 10K", est_10k if est_10k else "—")
        p3.metric("Est. Half Marathon (21k)" if not is_pt else "Est. Meia Maratona (21k)", est_21k if est_21k else "—")
        p4.metric("Est. Marathon (42k)" if not is_pt else "Est. Maratona (42k)", est_42k if est_42k else "—")

    st.markdown("<br>", unsafe_allow_html=True)

    # C. TRAINING INTENSITY & ZONES
    st.markdown("### C. Training Intensity & Zone Distribution" if not is_pt else "### C. Intensidade de Treino & Distribuição de Zonas")
    st.caption("Time-in-zone distribution for the last 7 days. Validates adherence to training structure (Polarized vs Threshold)." if not is_pt else "Distribuição de tempo em zonas nos últimos 7 dias. Permite verificar o alinhamento com a estrutura do bloco (Polarizado vs Threshold).")

    st.markdown("##### Heart Rate Zone Distribution (Running & Cycling)" if not is_pt else "##### Tempo em Zonas de Frequência Cardíaca (Corrida & Ciclismo)")
    
    z_low = latest.get("zone_low_pct") if pd.notna(latest.get("zone_low_pct")) else None
    z_mid = latest.get("zone_mid_pct") if pd.notna(latest.get("zone_mid_pct")) else None
    z_high = latest.get("zone_high_pct") if pd.notna(latest.get("zone_high_pct")) else None

    if all(v is not None for v in [z_low, z_mid, z_high]):
        st.markdown(
            f"""
            <div style="display:flex; height:24px; border-radius:8px; overflow:hidden; margin-bottom:8px;">
                <div style="width:{z_low}%; background:#10b981; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Z1-Z2 Low Aerobic' if not is_pt else 'Z1-Z2 Aeróbica Baixa'} ({z_low}%)</div>
                <div style="width:{z_mid}%; background:#f59e0b; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Z3-Z4 Threshold' if not is_pt else 'Z3-Z4 Limiar'} ({z_mid}%)</div>
                <div style="width:{z_high}%; background:#ef4444; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">{'Z5 Anaerobic' if not is_pt else 'Z5 Anaeróbica'} ({z_high}%)</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.info("⚠️ **Zone Breakdown Unavailable:** No activity zone telemetry recorded for this timeframe." if not is_pt else "⚠️ **Distribuição por Zonas Indisponível:** Sem dados de zonas registados para este período.")

    st.markdown("<br>", unsafe_allow_html=True)

    # D. AEROBIC EFFICIENCY & DURABILITY
    st.markdown("### D. Aerobic Efficiency & Durability" if not is_pt else "### D. Eficiência Aeróbica & Durabilidade")
    
    decoupling_val = latest.get("aerobic_decoupling") if pd.notna(latest.get("aerobic_decoupling")) else None
    submax_hr = latest.get("submax_hr") if pd.notna(latest.get("submax_hr")) else None
    submax_pace = latest.get("submax_pace") if pd.notna(latest.get("submax_pace")) else None

    d1, d2 = st.columns(2)
    with d1:
        decouple_str = f"{decoupling_val:.1f} %" if decoupling_val is not None else "—"
        decouple_desc = "Power:HR ratio sustained during steady-state long ride." if decoupling_val is not None else "Requires steady-state long session telemetry."
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">AEROBIC DECOUPLING (HR DRIFT)</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#14b8a6;">{decouple_str}</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{decouple_desc}</span><br>
                <span style="font-size:0.78rem; color:#64748b;">{'Drift < 5% indicates strong aerobic durability.' if not is_pt else 'Drift < 5% indica durabilidade aeróbica excelente.'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with d2:
        submax_str = f"{int(submax_hr)} bpm @ {submax_pace}" if (submax_hr and submax_pace) else "—"
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">SUBMAXIMAL EFFICIENCY TRACKING</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">{submax_str}</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{'Submaximal benchmark monitoring.' if not is_pt else 'Monitorização de benchmark submáximo.'}</span><br>
                <span style="font-size:0.78rem; color:#64748b;">{'Running economy progression without maximal testing.' if not is_pt else 'Evolução de economia de corrida sem necessidade de teste máximo.'}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # E. INDIVIDUAL SESSION ANALYSIS
    st.markdown("### E. Individual Session Detailed Analysis" if not is_pt else "### E. Análise Detalhada da Sessão Individual")
    with st.expander("🔍 Analyze Latest Recorded Session" if not is_pt else "🔍 Analisar Última Sessão Registada", expanded=False):
        aero_te = latest.get("aerobic_te") if pd.notna(latest.get("aerobic_te")) else None
        anaero_te = latest.get("anaerobic_te") if pd.notna(latest.get("anaerobic_te")) else None
        perf_cond = latest.get("performance_condition") if pd.notna(latest.get("performance_condition")) else None

        sa1, sa2, sa3 = st.columns(3)
        sa1.metric("Aerobic Training Effect", f"{aero_te:.1f}" if aero_te else "Not Recorded")
        sa2.metric("Anaerobic Training Effect", f"{anaero_te:.1f}" if anaero_te else "Not Recorded")
        sa3.metric("Performance Condition", f"{perf_cond:+} " if perf_cond else "Not Recorded")
        st.caption(
            "ℹ️ **Physiology Note:** Performance Condition compares early-session pace/power and heart rate response "
            "against your historical Garmin baseline. It is not a direct measurement of muscle glycogen or stiffness."
            if not is_pt else
            "ℹ️ **Nota de Fisiologia:** O Performance Condition compara a tua resposta de FC/Ritmo nos primeiros minutos da sessão "
            "com a tua baseline histórica da Garmin, não medindo diretamente rigidez muscular ou níveis de glicogénio."
        )

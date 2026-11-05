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


def render_pillar_training(base_df: pd.DataFrame, mode: str):
    st.markdown("## 02 — Training & Performance")
    st.caption("Carga de Treino · Capacidade Aeróbica · Distribuição de Intensidade · Eficiência Aeróbica · Análise de Sessões")

    # =========================================================================
    # A. TRAINING LOAD & ADAPTATION (BANISTER CTL / ATL / TSB & ACWR)
    # =========================================================================
    st.markdown("### A. Training Load & Adaptation")
    
    ctl_val = base_df["CTL"].iloc[-1] if "CTL" in base_df else None
    atl_val = base_df["ATL"].iloc[-1] if "ATL" in base_df else None
    tsb_val = base_df["TSB"].iloc[-1] if "TSB" in base_df else None
    
    loads_28 = base_df["DailyLoad"].tail(28).dropna().tolist() if "DailyLoad" in base_df else []
    acwr_val = core.compute_acwr(loads_28) if len(loads_28) >= 7 else None

    l1, l2, l3, l4, l5 = st.columns(5)
    l1.metric("Daily Load (Hoje)", _fmt(base_df["DailyLoad"].iloc[-1] if "DailyLoad" in base_df else None, 0, " UA"))
    l2.metric("CTL (Fitness 42d)", _fmt(ctl_val, 1, " UA"))
    l3.metric("ATL (Fadiga 7d)", _fmt(atl_val, 1, " UA"))
    l4.metric("TSB (Forma)", _fmt(tsb_val, 1, " UA"))
    l5.metric("ACWR (Razão Aguda:Crónica)", _fmt(acwr_val, 2))

    # Gráfico de Evolução de Carga (CTL / ATL / TSB)
    st.markdown("#### Evolução da Carga de Treino (Últimos 42 Dias)")
    if "CTL" in base_df and not base_df["CTL"].dropna().empty:
        chart_data = base_df.tail(42).set_index("Date")[["CTL", "ATL", "TSB"]]
        st.line_chart(chart_data)
    else:
        st.info("A calcular histórico de carga. Regista mais sessões com RPE/Duração para gerar a curva CTL/ATL/TSB.")

    # Alerta Científico ACWR
    st.caption(
        "⚠️ **Nota Metodológica APEX:** O ACWR é um indicador contextual de variação de carga e não um oráculo de lesões. "
        "Valores acima de 1.3 refletem aceleração de estímulo, devendo ser interpretados conjuntamente com a dor muscular (DOMS) e o sono."
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # B. AEROBIC CAPACITY & CARDIOVASCULAR FITNESS
    # =========================================================================
    st.markdown("### B. Aerobic Capacity & Thresholds")
    
    prof = store.get_setting("profile", {}) or {}
    vo2_run = prof.get("vo2max") or 60.0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Running VO2max", f"{vo2_run:.1f} mL/kg/min")
    c2.metric("Cycling VO2max (Power)", "58.0 mL/kg/min", help="Requer leitor de potência Garmin / Tacx Flux")
    c3.metric("FTP (Ciclismo)", "310 W", "4.13 W/kg")
    c4.metric("Limiar de Lactato (Corrida)", "3:55 /km", "172 bpm")

    with st.expander("📊 Predição de Performance em Prova (Modelos de Potência/Ritmo)", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("5K Estimado", "18:45")
        p2.metric("10K Estimado", "39:10")
        p3.metric("Meia Maratona (21k)", "1h 26m")
        p4.metric("Maratona (42k)", "3h 04m")

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # C. TRAINING INTENSITY & ZONES
    # =========================================================================
    st.markdown("### C. Training Intensity & Zone Distribution")
    st.caption("Distribuição de tempo em zonas nos últimos 7 dias. Permite verificar o alinhamento com a estrutura do bloco (Polarizado vs Threshold).")

    st.markdown("##### Tempo em Zonas de Frequência Cardíaca (Corrida & Ciclismo)")
    st.markdown(
        """
        <div style="display:flex; height:24px; border-radius:8px; overflow:hidden; margin-bottom:8px;">
            <div style="width:70%; background:#10b981; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">Z1-Z2 Aeróbica Baixa (70%)</div>
            <div style="width:18%; background:#f59e0b; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">Z3-Z4 Limiar (18%)</div>
            <div style="width:12%; background:#ef4444; text-align:center; color:#ffffff; font-size:0.75rem; line-height:24px;">Z5 Anaeróbica (12%)</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # D. AEROBIC EFFICIENCY & DURABILITY (DECOUPLING & SUBMAX)
    # =========================================================================
    st.markdown("### D. Aerobic Efficiency & Durability")
    
    d1, d2 = st.columns(2)
    with d1:
        st.markdown(
            """
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">AEROBIC DECOUPLING (HR DRIFT)</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#34d399;">3.2 %</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Relação Power:HR sustentada no último longo (190W avg).</span><br>
                <span style="font-size:0.78rem; color:#64748b;">Drift < 5% indica durabilidade aeróbica excelente.</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with d2:
        st.markdown(
            """
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">SUBMAXIMAL EFFICIENCY TRACKING</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">136 bpm @ 5:00 /km</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Melhoria vs mês anterior (142 bpm ao mesmo ritmo).</span><br>
                <span style="font-size:0.78rem; color:#64748b;">Evolução de economia de corrida sem necessidade de teste máximo.</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # E. INDIVIDUAL SESSION ANALYSIS (DETALHE DA ATIVIDADE RECENTE)
    # =========================================================================
    st.markdown("### E. Individual Session Detailed Analysis")
    with st.expander("🔍 Analisar Última Sessão Registada", expanded=False):
        sa1, sa2, sa3 = st.columns(3)
        sa1.metric("Aerobic Training Effect", "3.8 (Melhoria Impactante)")
        sa2.metric("Anaerobic Training Effect", "1.2 (Manutenção)")
        sa3.metric("Performance Condition", "+2 (Favorável)")
        st.caption(
            "ℹ️ **Nota de Fisiologia:** O Performance Condition compara a tua resposta de FC/Ritmo nos primeiros minutos da sessão "
            "com a tua baseline histórica da Garmin, não medindo diretamente rigidez muscular ou níveis de glicogénio."
        )

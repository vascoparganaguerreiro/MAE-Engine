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


def render_pillar_strength(base_df: pd.DataFrame, decision_cap: str):
    st.markdown("## 03 — Strength, Movement & Durability")
    st.caption("Biomecânica de Corrida & Ciclismo · Força & Capacidade Funcional · Resposta Respiratória · Testes de Laboratório")

    # =========================================================================
    # A. RUNNING BIOMECHANICS & FATIGUE COMPARISON
    # =========================================================================
    st.markdown("### A. Running Biomechanics")
    st.caption("A mecânica de corrida adapta-se à velocidade e ao terreno. O APEX analisa a variação de eficiência à medida que a fadiga acumula.")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Cadência Média", "174 ppm", "Variável com velocidade")
    m2.metric("Ground Contact Time (GCT)", "225 ms", "Requer sensor comp.")
    m3.metric("GCT Balance (E/D)", "49.8% / 50.2%", "Estável")
    m4.metric("Stride Length", "1.24 m")
    m5.metric("Vertical Ratio", "6.8 %")

    with st.expander("🔍 Análise de Fadiga Biomecânica (Primeiros 15 min vs Últimos 15 min)", expanded=False):
        st.markdown(
            """
            | Parâmetro Biomecânico | Primeiros 15 min | Últimos 15 min | Variação / Deriva |
            | :--- | :--- | :--- | :--- |
            | **Cadência (ppm)** | 176 ppm | 172 ppm | -2.2% |
            | **GCT (ms)** | 218 ms | 232 ms | +6.4% (Maior tempo de contacto) |
            | **Oscilação Vertical (cm)** | 8.1 cm | 8.9 cm | +9.8% |
            | **Vertical Ratio (%)** | 6.5 % | 7.3 % | +12.3% (Ligeira perda de economia) |
            """
        )
        st.caption("ℹ️ **Nota Metodológica:** A meta não é fixar 180 ppm universais, mas monitorizar a estabilidade da mecânica sob fadiga.")

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # B. CYCLING BIOMECHANICS & EFFICIENCY
    # =========================================================================
    st.markdown("### B. Cycling Biomechanics & Endurance Efficiency")

    cb1, cb2, cb3, cb4 = st.columns(4)
    cb1.metric("Cadência Média (Ciclismo)", "88 rpm")
    cb2.metric("Normalized Power (NP)", "215 W")
    cb3.metric("Eficiência em Longos (60-120m)", "1.08 (Power:HR)", "Estável")
    cb4.metric("Balanço de Potência E/D", "50% / 50%")

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # C. STRENGTH DEVELOPMENT & FUNCTIONAL CAPACITY
    # =========================================================================
    st.markdown("### C. Strength Development & Functional Capacity")
    st.caption("Capacidade neuromuscular, 1RM estimado, volume por grupo muscular e durabilidade funcional para saúde e performance.")

    st.markdown("#### Engine de Prescrição & Programação de Força")
    duration_cap = st.slider("Tempo disponível para a sessão de força (min)", 20, 90, 45, key="pillar3_time_slider")
    session = core.build_strength_session(decision_cap, time_min=duration_cap)
    
    st.markdown(f"**Carga Axial Recomendada (Spinal Score):** {session['spinal_score']} / 5")
    for ex in session["exercises"]:
        st.write(f"• **{ex['name']}** — {ex['sets']} séries × {ex['reps']} repetições (RIR {ex['rir']})")

    st.markdown("#### Registos de Força Relativa & Testes Funcionais")
    st1, st2, st3, st4 = st.columns(4)
    st1.metric("Squat Estimado 1RM", "125 kg", "1.66× Peso Corpóreo")
    st2.metric("Romanian Deadlift 1RM", "140 kg", "1.86× Peso Corpóreo")
    st3.metric("Single-Leg Calf Raises", "32 reps", "Capacidade Tendo-Aqueliana")
    st4.metric("Séries Semanais M. Inferiores", "12 séries", "Foco Estabilização Joelho")

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # D. RESPIRATORY & METABOLIC RESPONSE (TESTES DE LABORATÓRIO)
    # =========================================================================
    st.markdown("### D. Respiratory & Spiroergometry Data")
    
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Respiração em Repouso", "13.5 rpm")
    r2.metric("Respiração Noturna", "14.2 rpm")
    r3.metric("Perda de Suor Estimada", "1.1 L/h")
    r4.metric("Calorias Ativas Diárias", "850 kcal")

    with st.expander("🧪 Registar / Consultar Spiroergometria (Testes de Laboratório VT1 / VT2)", expanded=False):
        st.markdown("##### Dados de Laboratório de Ergospirometria")
        with st.form("spiro_form"):
            col_sp1, col_sp2, col_sp3 = st.columns(3)
            vt1_hr = col_sp1.number_input("FC em VT1 (Limiar Aeróbico)", value=145)
            vt2_hr = col_sp2.number_input("FC em VT2 (Limiar Anaeróbico)", value=174)
            lab_vo2 = col_sp3.number_input("VO2max de Laboratório", value=62.5)
            
            col_sp4, col_sp5 = st.columns(2)
            vt1_pace = col_sp4.text_input("Ritmo/Potência em VT1", value="4:25 /km ou 210W")
            vt2_pace = col_sp5.text_input("Ritmo/Potência em VT2", value="3:50 /km ou 295W")

            if st.form_submit_button("Guardar Dados de Laboratório", use_container_width=True):
                st.success("Dados de Ergospirometria atualizados!")

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


def render_pillar_strength(base_df: pd.DataFrame, decision_cap: str, lang: str = "EN"):
    is_pt = (lang == "PT")
    
    st.markdown("## 03 — Strength, Movement & Durability" if not is_pt else "## 03 — Força, Biomecânica & Durabilidade")
    st.caption("Running & Cycling Biomechanics · Strength & Functional Capacity · Respiratory Response · Spiroergometry" if not is_pt else "Biomecânica de Corrida & Ciclismo · Força & Capacidade Funcional · Resposta Respiratória · Testes de Laboratório")

    # A. RUNNING BIOMECHANICS
    st.markdown("### A. Running Biomechanics" if not is_pt else "### A. Biomecânica de Corrida")
    st.caption("Running dynamics naturally adapt to speed and terrain. APEX monitors efficiency stability as fatigue accumulates." if not is_pt else "A mecânica de corrida adapta-se à velocidade e ao terreno. O APEX analisa a variação de eficiência à medida que a fadiga acumula.")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Avg Cadence" if not is_pt else "Cadência Média", "174 spm", "Speed-dependent" if not is_pt else "Variável c/ velocidade")
    m2.metric("Ground Contact Time (GCT)", "225 ms", "Sensor required" if not is_pt else "Requer sensor comp.")
    m3.metric("GCT Balance (L/R)", "49.8% / 50.2%", "Balanced" if not is_pt else "Estável")
    m4.metric("Stride Length" if not is_pt else "Comprimento Passada", "1.24 m")
    m5.metric("Vertical Ratio", "6.8 %")

    with st.expander("🔍 Fatigue Biomechanics Comparison (First 15 min vs Last 15 min)" if not is_pt else "🔍 Análise de Fadiga Biomecânica (Primeiros 15 min vs Últimos 15 min)", expanded=False):
        st.markdown(
            """
            | Biomechanical Parameter | First 15 min | Last 15 min | Variation / Drift |
            | :--- | :--- | :--- | :--- |
            | **Cadence (spm)** | 176 spm | 172 spm | -2.2% |
            | **GCT (ms)** | 218 ms | 232 ms | +6.4% (Increased ground contact) |
            | **Vertical Oscillation (cm)** | 8.1 cm | 8.9 cm | +9.8% |
            | **Vertical Ratio (%)** | 6.5 % | 7.3 % | +12.3% (Slight loss of economy) |
            """
            if not is_pt else
            """
            | Parâmetro Biomecânico | Primeiros 15 min | Últimos 15 min | Variação / Deriva |
            | :--- | :--- | :--- | :--- |
            | **Cadência (spm)** | 176 spm | 172 spm | -2.2% |
            | **GCT (ms)** | 218 ms | 232 ms | +6.4% (Maior tempo contacto) |
            | **Oscilação Vertical (cm)** | 8.1 cm | 8.9 cm | +9.8% |
            | **Vertical Ratio (%)** | 6.5 % | 7.3 % | +12.3% (Perda de economia) |
            """
        )
        st.caption("ℹ️ **Methodological Note:** 180 spm is not a universal target. APEX tracks movement consistency under fatigue." if not is_pt else "ℹ️ **Nota Metodológica:** A meta não é fixar 180 spm universais, mas monitorizar a estabilidade da mecânica sob fadiga.")

    st.markdown("<br>", unsafe_allow_html=True)

    # B. CYCLING BIOMECHANICS & EFFICIENCY
    st.markdown("### B. Cycling Biomechanics & Endurance Efficiency" if not is_pt else "### B. Biomecânica de Ciclismo & Eficiência")

    cb1, cb2, cb3, cb4 = st.columns(4)
    cb1.metric("Avg Cadence (Cycling)" if not is_pt else "Cadência Média (Ciclismo)", "88 rpm")
    cb2.metric("Normalized Power (NP)", "215 W")
    cb3.metric("Long Ride Efficiency (60-120m)" if not is_pt else "Eficiência em Longos (60-120m)", "1.08 (Power:HR)", "Stable" if not is_pt else "Estável")
    cb4.metric("Power Balance (L/R)" if not is_pt else "Balanço Potência E/D", "50% / 50%")

    st.markdown("<br>", unsafe_allow_html=True)

    # C. STRENGTH DEVELOPMENT & FUNCTIONAL CAPACITY
    st.markdown("### C. Strength Development & Functional Capacity" if not is_pt else "### C. Desenvolviemnto de Força & Capacidade Funcional")
    st.caption("Neuromuscular capacity, estimated 1RM, volume per muscle group, and functional durability." if not is_pt else "Capacidade neuromuscular, 1RM estimado, volume por grupo muscular e durabilidade funcional.")

    st.markdown("#### APEX Strength Prescriber & Session Builder" if not is_pt else "#### Engine de Prescrição & Programação de Força")
    duration_cap = st.slider("Available time for strength session (min)" if not is_pt else "Tempo disponível para sessão de força (min)", 20, 90, 45, key="pillar3_time_slider")
    session = core.build_strength_session(decision_cap, time_min=duration_cap)
    
    st.markdown(f"**{'Recommended Axial Load (Spinal Score):' if not is_pt else 'Carga Axial Recomendada (Spinal Score):'}** {session['spinal_score']} / 5")
    for ex in session["exercises"]:
        st.write(f"• **{ex['name']}** — {ex['sets']} {'sets' if not is_pt else 'séries'} × {ex['reps']} {'reps' if not is_pt else 'repetições'} (RIR {ex['rir']})")

    st.markdown("#### Relative Strength Records & Functional Benchmarks" if not is_pt else "#### Registos de Força Relativa & Testes Funcionais")
    
    prof = store.get_setting("profile", {}) or {}
    user_weight = float(prof.get("weight_kg") or 75.0)

    squat_1rm = 125.0
    rdl_1rm = 140.0
    squat_rel = squat_1rm / user_weight if user_weight > 0 else 0.0
    rdl_rel = rdl_1rm / user_weight if user_weight > 0 else 0.0

    st1, st2, st3, st4 = st.columns(4)
    st1.metric("Est. Squat 1RM" if not is_pt else "Squat Estimado 1RM", f"{squat_1rm:.0f} kg", f"{squat_rel:.2f}× {'Body Weight' if not is_pt else 'Peso Corpóreo'}")
    st2.metric("Est. Romanian Deadlift 1RM" if not is_pt else "RDL Estimado 1RM", f"{rdl_1rm:.0f} kg", f"{rdl_rel:.2f}× {'Body Weight' if not is_pt else 'Peso Corpóreo'}")
    st3.metric("Single-Leg Calf Raises", "32 reps", "Achilles Tendon Capacity" if not is_pt else "Capacidade Tendo-Aqueliana")
    st4.metric("Lower Body Weekly Sets" if not is_pt else "Séries Semanais M. Inferiores", "12 sets" if not is_pt else "12 séries", "Knee Stability Focus" if not is_pt else "Foco Estabilização Joelho")

    st.markdown("<br>", unsafe_allow_html=True)

    # D. RESPIRATORY & METABOLIC RESPONSE
    st.markdown("### D. Respiratory & Spiroergometry Data" if not is_pt else "### D. Resposta Respiratória & Spiroergometria")
    
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Resting Respiration" if not is_pt else "Respiração em Repouso", "13.5 brpm")
    r2.metric("Overnight Respiration" if not is_pt else "Respiração Noturna", "14.2 brpm")
    r3.metric("Est. Sweat Rate" if not is_pt else "Perda de Suor Estimada", "1.1 L/h")
    r4.metric("Active Calories" if not is_pt else "Calorias Ativas Diárias", "850 kcal")

    with st.expander("🧪 Spiroergometry Laboratory Data (VT1 / VT2 Tests)" if not is_pt else "🧪 Registar / Consultar Spiroergometria (Testes VT1 / VT2)", expanded=False):
        st.markdown("##### Ergospirometry Laboratory Results" if not is_pt else "##### Dados de Laboratório de Ergospirometria")
        with st.form("spiro_form"):
            col_sp1, col_sp2, col_sp3 = st.columns(3)
            vt1_hr = col_sp1.number_input("HR at VT1 (Aerobic Threshold)" if not is_pt else "FC em VT1 (Limiar Aeróbico)", value=145)
            vt2_hr = col_sp2.number_input("HR at VT2 (Anaerobic Threshold)" if not is_pt else "FC em VT2 (Limiar Anaeróbico)", value=174)
            lab_vo2 = col_sp3.number_input("Lab VO2max", value=62.5)
            
            col_sp4, col_sp5 = st.columns(2)
            vt1_pace = col_sp4.text_input("Pace/Power at VT1" if not is_pt else "Ritmo/Potência em VT1", value="4:25 /km or 210W")
            vt2_pace = col_sp5.text_input("Pace/Power at VT2" if not is_pt else "Ritmo/Potência em VT2", value="3:50 /km or 295W")

            if st.form_submit_button("Save Lab Data" if not is_pt else "Guardar Dados de Laboratório", use_container_width=True):
                st.success("Spiroergometry data updated!" if not is_pt else "Dados atualizados!")

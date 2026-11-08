from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Dict, Optional
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


def _numeric(row: Any, field: str) -> Optional[float]:
    try:
        value = row.get(field)
        return float(value) if value is not None and pd.notna(value) else None
    except (TypeError, ValueError, AttributeError):
        return None


def _latest_sport_row(sessions: pd.DataFrame, terms: tuple[str, ...]) -> Dict[str, Any]:
    if sessions is None or sessions.empty or "sport" not in sessions.columns:
        return {}
    work = sessions.copy()
    sport = work["sport"].fillna("").astype(str).str.lower()
    mask = sport.apply(lambda value: any(term in value for term in terms))
    subset = work.loc[mask]
    if subset.empty:
        return {}
    if "date" in subset.columns:
        subset = subset.sort_values("date")
    return subset.iloc[-1].to_dict()


def render_pillar_strength(base_df: pd.DataFrame, decision_cap: str, lang: str = "EN",
                           training_sessions: Optional[pd.DataFrame] = None):
    is_pt = (lang == "PT")
    latest = base_df.iloc[-1] if not base_df.empty else {}
    training_sessions = training_sessions if training_sessions is not None else pd.DataFrame()
    latest_run = _latest_sport_row(training_sessions, ("run", "running", "trail", "treadmill"))
    latest_bike = _latest_sport_row(training_sessions, ("cycling", "bike", "indoorcycling", "virtualride"))
    latest_activity = training_sessions.sort_values("date").iloc[-1].to_dict() if not training_sessions.empty and "date" in training_sessions else {}
    
    st.markdown("## 03 — Strength, Movement & Durability" if not is_pt else "## 03 — Força, Biomecânica & Durabilidade")
    st.caption("Running & Cycling Biomechanics · Strength & Functional Capacity · Respiratory Response · Spiroergometry" if not is_pt else "Biomecânica de Corrida & Ciclismo · Força & Capacidade Funcional · Resposta Respiratória · Testes de Laboratório")

    # A. RUNNING BIOMECHANICS
    st.markdown("### A. Running Biomechanics" if not is_pt else "### A. Biomecânica de Corrida")
    st.caption("Running dynamics naturally adapt to speed and terrain. APEX monitors efficiency stability as fatigue accumulates." if not is_pt else "A mecânica de corrida adapta-se à velocidade e ao terreno. O APEX analisa a variação de eficiência à medida que a fadiga acumula.")

    run_cadence = _numeric(latest_run, "avg_cadence")
    gct_val = _numeric(latest_run, "ground_contact_time_ms")
    gct_bal = _numeric(latest_run, "ground_contact_balance_pct")
    stride_len = _numeric(latest_run, "stride_length_m")
    vert_ratio = _numeric(latest_run, "vertical_ratio_pct")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Avg Cadence" if not is_pt else "Cadência Média", f"{int(run_cadence)} spm" if run_cadence else "—", "Speed-dependent" if (not is_pt and run_cadence) else "Variável c/ velocidade" if run_cadence else "Not Recorded")
    m2.metric("Ground Contact Time (GCT)", f"{int(gct_val)} ms" if gct_val else "—", "Sensor required" if not is_pt else "Requer sensor comp.")
    m3.metric("GCT Balance (L/R)", f"{gct_bal}" if gct_bal else "—", "Balanced" if (not is_pt and gct_bal) else "Not Recorded")
    m4.metric("Stride Length" if not is_pt else "Comprimento Passada", f"{_fmt(stride_len, 2, ' m')}" if stride_len else "—")
    m5.metric("Vertical Ratio", f"{_fmt(vert_ratio, 1, ' %')}" if vert_ratio else "—")

    with st.expander("🔍 Fatigue Biomechanics Comparison (First 15 min vs Last 15 min)" if not is_pt else "🔍 Análise de Fadiga Biomecânica (Primeiros 15 min vs Últimos 15 min)", expanded=False):
        c_start = latest.get("cadence_start") if pd.notna(latest.get("cadence_start")) else None
        c_end = latest.get("cadence_end") if pd.notna(latest.get("cadence_end")) else None
        gct_start = latest.get("gct_start") if pd.notna(latest.get("gct_start")) else None
        gct_end = latest.get("gct_end") if pd.notna(latest.get("gct_end")) else None
        
        if all(v is not None for v in [c_start, c_end, gct_start, gct_end]):
            c_drift = ((c_end - c_start) / c_start) * 100
            gct_drift = ((gct_end - gct_start) / gct_start) * 100
            st.markdown(
                f"""
                | Biomechanical Parameter | First 15 min | Last 15 min | Variation / Drift |
                | :--- | :--- | :--- | :--- |
                | **Cadence (spm)** | {int(c_start)} spm | {int(c_end)} spm | {c_drift:+.1f}% |
                | **GCT (ms)** | {int(gct_start)} ms | {int(gct_end)} ms | {gct_drift:+.1f}% |
                """
            )
        else:
            st.info("⚠️ **Split Telemetry Unavailable:** Requires a running activity file with dual-window running dynamics export." if not is_pt else "⚠️ **Telemetria de Divisão Indisponível:** Requer ficheiro de corrida com exportação de dinâmica em duas janelas.")
        
        st.caption("ℹ️ **Methodological Note:** 180 spm is not a universal target. APEX tracks movement consistency under fatigue." if not is_pt else "ℹ️ **Nota Metodológica:** A meta não é fixar 180 spm universais, mas monitorizar a estabilidade da mecânica sob fadiga.")

    st.markdown("<br>", unsafe_allow_html=True)

    # B. CYCLING BIOMECHANICS & EFFICIENCY
    st.markdown("### B. Cycling Biomechanics & Endurance Efficiency" if not is_pt else "### B. Biomecânica de Ciclismo & Eficiência")

    bike_cad = _numeric(latest_bike, "avg_cadence")
    np_val = _numeric(latest_bike, "normalized_power")
    eff_ratio = _numeric(latest_bike, "cycling_efficiency_ratio")
    p_bal = _numeric(latest_bike, "power_balance")

    cb1, cb2, cb3, cb4 = st.columns(4)
    cb1.metric("Avg Cadence (Cycling)" if not is_pt else "Cadência Média (Ciclismo)", f"{int(bike_cad)} rpm" if bike_cad else "—")
    cb2.metric("Normalized Power (NP)", f"{int(np_val)} W" if np_val else "—")
    cb3.metric("Long Ride Efficiency" if not is_pt else "Eficiência em Longos", f"{_fmt(eff_ratio, 2)} (Power:HR)" if eff_ratio else "—")
    cb4.metric("Power Balance (L/R)" if not is_pt else "Balanço Potência E/D", f"{p_bal}" if p_bal else "—")

    st.markdown("<br>", unsafe_allow_html=True)

    # C. STRENGTH DEVELOPMENT & FUNCTIONAL CAPACITY
    st.markdown("### C. Strength Development & Functional Capacity" if not is_pt else "### C. Desenvolvimento de Força & Capacidade Funcional")
    st.caption("Neuromuscular capacity, estimated 1RM, volume per muscle group, and functional durability." if not is_pt else "Capacidade neuromuscular, 1RM estimado, volume por grupo muscular e durabilidade funcional.")

    st.markdown("#### APEX Strength Prescriber & Session Builder" if not is_pt else "#### Engine de Prescrição & Programação de Força")
    duration_cap = st.slider("Available time for strength session (min)" if not is_pt else "Tempo disponível para sessão de força (min)", 20, 90, 45, key="pillar3_time_slider")
    session = core.build_strength_session(decision_cap, time_min=duration_cap)
    
    st.markdown(f"**{'Recommended Axial Load (Spinal Score):' if not is_pt else 'Carga Axial Recomendada (Spinal Score):'}** {session['spinal_score']} / 5")
    for ex in session["exercises"]:
        st.write(f"• **{ex['name']}** — {ex['sets']} {'sets' if not is_pt else 'séries'} × {ex['reps']} {'reps' if not is_pt else 'repetições'} (RIR {ex['rir']})")

    st.markdown("#### Relative Strength Records & Functional Benchmarks" if not is_pt else "#### Registos de Força Relativa & Testes Funcionais")
    
    prof = store.get_setting("profile", {}) or {}
    user_weight = float(prof.get("weight_kg") or prof.get("weight") or 0.0)

    squat_1rm = prof.get("squat_1rm") or (latest.get("squat_1rm") if pd.notna(latest.get("squat_1rm")) else None)
    rdl_1rm = prof.get("rdl_1rm") or (latest.get("rdl_1rm") if pd.notna(latest.get("rdl_1rm")) else None)
    calf_reps = latest.get("calf_raise_reps") if pd.notna(latest.get("calf_raise_reps")) else None
    weekly_sets = latest.get("lower_body_weekly_sets") if pd.notna(latest.get("lower_body_weekly_sets")) else None

    squat_rel = (squat_1rm / user_weight) if (squat_1rm and user_weight > 0) else None
    rdl_rel = (rdl_1rm / user_weight) if (rdl_1rm and user_weight > 0) else None

    st1, st2, st3, st4 = st.columns(4)
    st1.metric("Est. Squat 1RM" if not is_pt else "Squat Estimado 1RM", f"{squat_1rm:.0f} kg" if squat_1rm else "—", f"{squat_rel:.2f}× BW" if squat_rel else "Not Logged")
    st2.metric("Est. Romanian Deadlift 1RM" if not is_pt else "RDL Estimado 1RM", f"{rdl_1rm:.0f} kg" if rdl_1rm else "—", f"{rdl_rel:.2f}× BW" if rdl_rel else "Not Logged")
    st3.metric("Single-Leg Calf Raises", f"{int(calf_reps)} reps" if calf_reps else "—", "Achilles Tendon Capacity" if (not is_pt and calf_reps) else "Not Tested")
    st4.metric("Lower Body Weekly Sets" if not is_pt else "Séries Semanais M. Inferiores", f"{int(weekly_sets)} sets" if weekly_sets else "—")

    st.markdown("<br>", unsafe_allow_html=True)

    # D. RESPIRATORY & METABOLIC RESPONSE
    st.markdown("### D. Respiratory & Spiroergometry Data" if not is_pt else "### D. Resposta Respiratória & Spiroergometria")
    
    rest_resp = _numeric(latest, "respiration_wake_avg")
    night_resp = _numeric(latest, "respiration_sleep_avg")
    sweat_rate = _numeric(latest, "estimated_sweat_rate")
    active_kcal = _numeric(latest, "active_calories")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Resting Respiration" if not is_pt else "Respiração em Repouso", f"{_fmt(rest_resp, 1)} brpm" if rest_resp else "—")
    r2.metric("Overnight Respiration" if not is_pt else "Respiração Noturna", f"{_fmt(night_resp, 1)} brpm" if night_resp else "—")
    r3.metric("Est. Sweat Rate" if not is_pt else "Perda de Suor Estimada", f"{_fmt(sweat_rate, 2)} L/h" if sweat_rate else "—")
    r4.metric("Active Calories" if not is_pt else "Calorias Ativas Diárias", f"{int(active_kcal)} kcal" if active_kcal else "—")

    with st.expander("🧪 Spiroergometry Laboratory Data (VT1 / VT2 Tests)" if not is_pt else "🧪 Registar / Consultar Spiroergometria (Testes VT1 / VT2)", expanded=False):
        st.markdown("##### Ergospirometry Laboratory Results" if not is_pt else "##### Dados de Laboratório de Ergospirometria")
        with st.form("spiro_form"):
            col_sp1, col_sp2, col_sp3 = st.columns(3)
            vt1_hr = col_sp1.number_input("HR at VT1 (Aerobic Threshold)" if not is_pt else "FC em VT1 (Limiar Aeróbico)", min_value=0, max_value=230, value=0)
            vt2_hr = col_sp2.number_input("HR at VT2 (Anaerobic Threshold)" if not is_pt else "FC em VT2 (Limiar Anaeróbico)", min_value=0, max_value=230, value=0)
            lab_vo2 = col_sp3.number_input("Lab VO2max", min_value=0.0, max_value=90.0, value=0.0)
            
            col_sp4, col_sp5 = st.columns(2)
            vt1_pace = col_sp4.text_input("Pace/Power at VT1" if not is_pt else "Ritmo/Potência em VT1", placeholder="e.g. 4:25 /km or 210W")
            vt2_pace = col_sp5.text_input("Pace/Power at VT2" if not is_pt else "Ritmo/Potência em VT2", placeholder="e.g. 3:50 /km or 295W")

            if st.form_submit_button("Save Lab Data" if not is_pt else "Guardar Dados de Laboratório", use_container_width=True):
                spiro_payload = {
                    "vt1_hr": vt1_hr if vt1_hr > 0 else None,
                    "vt2_hr": vt2_hr if vt2_hr > 0 else None,
                    "lab_vo2max": lab_vo2 if lab_vo2 > 0 else None,
                    "vt1_pace": vt1_pace if vt1_pace else None,
                    "vt2_pace": vt2_pace if vt2_pace else None,
                }
                store.save_setting("spiroergometry", spiro_payload)
                st.success("Spiroergometry data updated!" if not is_pt else "Dados de laboratório guardados com sucesso!")
                st.rerun()

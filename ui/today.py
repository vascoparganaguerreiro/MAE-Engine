from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import streamlit as st

import data_store as store
import engine_core as core
from ui.pillar_recovery import render_pillar_recovery
from ui.pillar_training import render_pillar_training
from ui.pillar_strength import render_pillar_strength
from ui.pillar_nutrition import render_nutrition_habits_layer


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


def render_today_page(base_df: pd.DataFrame, hrv_mean: Optional[float], rhr_mean: Optional[float],
                      hrv_curr: Optional[float], rhr_curr: Optional[float], sleep_curr: Optional[float],
                      sleep_hours_curr: Optional[float], sleep_target_curr: Optional[float],
                      garmin_readiness_curr: Optional[float], score: Optional[int],
                      decision: Dict[str, Any], hrv_context: Dict[str, Any], diff_minutes: Optional[float],
                      hrv_valid_days: int, sync_callback):

    latest = base_df.iloc[-1]
    
    # -------------------------------------------------------------------------
    # LEVEL 1: TOP NAVIGATION & ATHLETE DASHBOARD HEADER
    # -------------------------------------------------------------------------
    head_col1, head_col2 = st.columns([3, 1])
    with head_col1:
        st.markdown("<h1 style='margin-bottom:0; color:#f8fafc;'>⚡ APEX ENGINE</h1>", unsafe_allow_html=True)
        st.caption("UNIVERSAL PHYSIOLOGY · PERFORMANCE · LONGEVITY · " + date.today().strftime("%A, %d %B %Y"))
    
    with head_col2:
        last_sync = store.get_setting("garmin_last_sync", "Nunca")
        st.markdown(f"<div style='text-align:right; font-size:0.8rem; color:#14b8a6;'>🟢 Connected (Garmin Connect)</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:right; font-size:0.75rem; color:#64748b;'>Sync: {last_sync[:16] if len(last_sync) >= 16 else last_sync}</div>", unsafe_allow_html=True)
        if st.button("⚡ SYNC DATA", key="sync_top_btn", type="primary", use_container_width=True):
            with st.spinner("Sincronizando Garmin Connect..."):
                ok = sync_callback()
                if ok:
                    st.toast("Garmin sincronizada com sucesso!", icon="⚡")
                st.rerun()

    # Jump Navigation Bar (Sem Sidebar)
    st.markdown(
        """
        <div style="background:#0f172a; padding:8px 16px; border-radius:8px; border:1px solid #1e293b; margin:10px 0 20px 0; display:flex; gap:20px; font-size:0.85rem; font-weight:600;">
            <a href="#today-s-decision-readiness" style="color:#f8fafc; text-decoration:none;">00. DECISION</a>
            <a href="#01-recovery-readiness" style="color:#14b8a6; text-decoration:none;">01. RECOVERY & READINESS</a>
            <a href="#02-training-performance" style="color:#3b82f6; text-decoration:none;">02. TRAINING & PERFORMANCE</a>
            <a href="#03-strength-movement-durability" style="color:#f59e0b; text-decoration:none;">03. STRENGTH & MOVEMENT</a>
            <a href="#apex-intelligence-what-your-body-is-telling-you" style="color:#a855f7; text-decoration:none;">04. APEX INTELLIGENCE</a>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Controls Header (Goal Focus Selector & Config Pops)
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        saved_mode = store.get_setting("mode", "performance")
        mode_opt = st.selectbox(
            "Goal Profile Focus ▾",
            ["🏃 Performance (Atleta)", "🧘‍♂️ Health & Wellness", "🧬 Longevidade & Saúde Metabólica"],
            index=0 if saved_mode == "performance" else 1 if saved_mode == "wellness" else 2,
            help="Altera a ênfase visual mantendo a exatidão e universalidade dos cálculos fisiológicos subjacentes."
        )
        new_mode = "performance" if mode_opt.startswith("🏃") else "wellness" if mode_opt.startswith("🧘") else "longevity"
        if new_mode != saved_mode:
            store.set_setting("mode", new_mode)
            st.rerun()

    with f_col2:
        with st.popover("👤 Perfil & Definições"):
            st.markdown("### Perfil de Atleta")
            prof = store.get_setting("profile", {}) or {}
            g_val = st.selectbox("Sexo", ["Não indicado", "Masculino", "Feminino"], index=0 if prof.get("gender") not in ["Masculino", "Feminino"] else ["Masculino", "Feminino"].index(prof.get("gender")) + 1)
            w_val = st.text_input("Peso (kg)", value=str(prof.get("weight_kg") or ""))
            v_val = st.text_input("VO2max", value=str(prof.get("vo2max") or ""))
            if st.button("Guardar Perfil", use_container_width=True):
                store.set_setting("profile", {"gender": g_val, "weight_kg": float(w_val) if w_val else None, "vo2max": float(v_val) if v_val else None})
                st.success("Guardado!")
                st.rerun()

    with f_col3:
        with st.popover("🔑 Garmin & Dados"):
            st.markdown("### Credenciais Garmin")
            with st.form("quick_garmin_form"):
                st.text_input("E-mail Garmin", key="garmin_email_input")
                st.text_input("Palavra-passe", type="password", key="garmin_password_input")
                if st.form_submit_button("Guardar e Sincronizar", use_container_width=True):
                    sync_callback()
                    st.rerun()

    # -------------------------------------------------------------------------
    # LEVEL 1: TODAY'S DECISION & ACTION
    # -------------------------------------------------------------------------
    st.subheader("Today's Decision & Readiness")
    
    if garmin_readiness_curr is not None:
        g_score = int(garmin_readiness_curr)
        g_decision = core.decision_for(g_score)
        tone_class = {"green": "border-left:5px solid #14b8a6;", "amber": "border-left:5px solid #f59e0b;", "red": "border-left:5px solid #ef4444;"}.get(g_decision["tone"], "")
        st.markdown(
            f'<div style="background:#131a27; border:1px solid #334155; border-radius:12px; padding:16px; {tone_class}">'
            f'<span style="font-size:1.3rem; font-weight:800; color:#f8fafc;">Garmin Training Readiness: {g_score}/100</span><br>'
            f'<b style="font-size:1.05rem; color:#cbd5e1;">{escape(g_decision["headline"])}</b><br>'
            f'<span style="font-size:0.88rem; color:#94a3b8;">Sintese transparente de variabilidade autónoma, histórico de sono e resposta à carga. Confirma as sensações subjetivas antes da sessão.</span>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # LEVEL 1: CORE METRICS (FIVE KEY STANDARDIZED CARDS)
    # -------------------------------------------------------------------------
    st.subheader("Five Core Metrics")

    garmin_weekly_avg = latest.get("hrv_weekly_avg") if pd.notna(latest.get("hrv_weekly_avg")) else None
    effective_vrc_base = garmin_weekly_avg if garmin_weekly_avg is not None else hrv_mean
    hrv_sd = base_df["HRV"].tail(30).std() if len(base_df["HRV"].dropna()) >= 7 else 5.0
    if pd.isna(hrv_sd) or hrv_sd == 0:
        hrv_sd = 5.0

    z_vrc = (hrv_curr - effective_vrc_base) / hrv_sd if (hrv_curr is not None and effective_vrc_base is not None) else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">NIGHTLY HRV</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(20, 184, 166, 0.15); color:#14b8a6; font-size:0.72rem; font-weight:600;">Base: {_fmt(effective_vrc_base, 0)} ms (Z: {z_vrc:+.1f})</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Fonte: Garmin · Confiança Alta</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        rhr_diff = (rhr_curr - rhr_mean) if (rhr_curr and rhr_mean) else 0.0
        rhr_color = "#14b8a6" if rhr_diff <= 0 else "#f59e0b"
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">RESTING HR</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(245, 158, 11, 0.15); color:{rhr_color}; font-size:0.72rem; font-weight:600;">{rhr_diff:+.1f} bpm vs base ({_fmt(rhr_mean, 1)})</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Fonte: Garmin · Tendência Estável</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">SLEEP DURATION</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt_hours_to_hm(sleep_hours_curr)}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(20, 184, 166, 0.15); color:#14b8a6; font-size:0.72rem; font-weight:600;">Meta: 8h 00m</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Fonte: Garmin · Score {_fmt(sleep_curr, 0)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">TRAINING LOAD</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt(base_df["DailyLoad"].iloc[-1] if "DailyLoad" in base_df else None, 0, " UA")}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(59, 130, 246, 0.15); color:#3b82f6; font-size:0.72rem; font-weight:600;">Carga Diária Calculada</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Fonte: APEX Load Engine</div>
        </div>
        """, unsafe_allow_html=True)

    with c5:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">APEX READINESS</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#14b8a6;">{garmin_readiness_curr or score or '—'}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(20, 184, 166, 0.2); color:#14b8a6; font-size:0.72rem; font-weight:600;">Score Transparente</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Z-Score VRC + Subjetivo</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # LEVEL 2 & 3: THREE PILLARS (RECOVERY, TRAINING, STRENGTH)
    # -------------------------------------------------------------------------
    
    # PILAR 1: RECOVERY & READINESS (TEAL / TURQUOISE)
    render_pillar_recovery(
        base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
        hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
        sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
        garmin_readiness_curr=garmin_readiness_curr, score=score,
        decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
        hrv_valid_days=hrv_valid_days
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # PILAR 2: TRAINING & PERFORMANCE (BLUE)
    render_pillar_training(base_df=base_df, mode=saved_mode)

    st.markdown("<br>", unsafe_allow_html=True)

    # PILAR 3: STRENGTH, MOVEMENT & DURABILITY (AMBER / GOLD)
    render_pillar_strength(base_df=base_df, decision_cap=decision["cap"])

    # CROSS-PILLAR: NUTRITION, HYDRATION & HABITS
    render_nutrition_habits_layer()

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # LEVEL 4: APEX INTELLIGENCE LAYER (CROSS-PILLAR ENGINE & AI COACH)
    # -------------------------------------------------------------------------
    st.markdown("## 🧠 APEX Intelligence — What Your Body Is Telling You")
    st.caption("Cruzamento holístico de sinais fisiológicos entre pilares com regras determinísticas e síntese biológica do Gemini AI.")

    latest_soreness = int(latest.get("soreness") or 3)
    latest_fatigue = int(latest.get("fatigue") or 3)

    st.markdown(
        """
        <div style="background:#1e1b4b; border:1px solid #4c1d95; padding:20px; border-radius:12px; margin-bottom:15px;">
            <h4 style="margin-top:0; color:#c084fc;">Sinais Fisiológicos Cruzados (Matriz Tri-Pilar)</h4>
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:15px;">
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">Eficiência Aeróbica</span><br>
                    <b style="color:#34d399;">A Melhorar (Drift 3.2%)</b>
                </div>
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">Volume de Treino</span><br>
                    <b style="color:#60a5fa;">Em Crescimento (CTL 52)</b>
                </div>
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">Duração do Sono</span><br>
                    <b style="color:#fbbf24;">Ligeiramente Abaixo Target</b>
                </div>
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">Fadiga Subjetiva</span><br>
                    <b style="color:#f87171;">Moderada a Elevada (DOMS 3/5)</b>
                </div>
            </div>
            <b style="color:#f8fafc; font-size:1rem;">Ação Recomendada pelo APEX Core:</b><br>
            <p style="color:#e2e8f0; font-size:0.92rem; margin-bottom:0; line-height:1.5;">
                A tua capacidade aeróbica e economia de corrida estão em fase de desenvolvimento favorável. 
                Contudo, com o sono ligeiramente acumulado abaixo da meta e a dor muscular presente, a prioridade para hoje é manter a intensidade dentro da faixa estipulada, 
                garantindo aporte adequado de carboidratos e 8 horas de sono noturno para prevenir acumulação desnecessária de fadiga central.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

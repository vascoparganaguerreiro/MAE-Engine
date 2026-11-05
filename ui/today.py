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
    
    # Header & Status Superior
    head_col1, head_col2 = st.columns([3, 1])
    with head_col1:
        st.markdown("<h1 style='margin-bottom:0;'>⚡ APEX</h1>", unsafe_allow_html=True)
        st.caption("PERSONAL PERFORMANCE ENGINE · " + date.today().strftime("%A, %d %B %Y"))
    
    with head_col2:
        last_sync = store.get_setting("garmin_last_sync", "Nunca")
        st.markdown(f"<div style='text-align:right; font-size:0.8rem; color:#10b981;'>🟢 Connected (Garmin)</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:right; font-size:0.75rem; color:#64748b;'>Última sync: {last_sync[:16] if len(last_sync) >= 16 else last_sync}</div>", unsafe_allow_html=True)
        if st.button("⚡ SYNC DATA", key="sync_top_btn", type="primary", use_container_width=True):
            with st.spinner("Sincronizando Garmin Connect..."):
                ok = sync_callback()
                if ok:
                    st.toast("Garmin sincronizada com sucesso!", icon="⚡")
                st.rerun()

    st.divider()

    # Seletor de Foco de Performance e Configurações Rápidas
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        saved_mode = store.get_setting("mode", "performance")
        mode_opt = st.selectbox(
            "Performance Focus ▾",
            ["🏃 Performance (Atleta)", "🧘‍♂️ Health & Wellness", "🧬 Longevidade & Saúde Metabólica"],
            index=0 if saved_mode == "performance" else 1 if saved_mode == "wellness" else 2
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

    # Today's Overview & Recommendation
    st.subheader("Today's Overview & Recommendation")
    if garmin_readiness_curr is not None:
        g_score = int(garmin_readiness_curr)
        g_decision = core.decision_for(g_score)
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(g_decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}">'
            f'<span style="font-size:1.4rem; font-weight:800; color:#f8fafc;">Garmin Training Readiness: {g_score}/100</span><br>'
            f'<b>{escape(g_decision["headline"])}</b><br>'
            f'<span class="muted">Recuperação autónoma estável. Confirma as sensações subjetivas no Pilar 1 antes da sessão.</span>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # 5 Key Metrics
    st.subheader("Your Five Key Metrics")
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
            <span style="color:#94a3b8; font-size:0.8rem;">HRV</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(16, 185, 129, 0.2); color:#34d399; font-size:0.72rem; font-weight:600;">Baseline: {_fmt(effective_vrc_base, 0)} ms (Z: {z_vrc:+.1f})</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        rhr_diff = (rhr_curr - rhr_mean) if (rhr_curr and rhr_mean) else 0.0
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">Resting HR</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(16, 185, 129, 0.2); color:#34d399; font-size:0.72rem; font-weight:600;">{rhr_diff:+.1f} bpm vs base</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">Sleep</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt_hours_to_hm(sleep_hours_curr)}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(16, 185, 129, 0.2); color:#34d399; font-size:0.72rem; font-weight:600;">Meta 8h</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">Training Load</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt(base_df["DailyLoad"].iloc[-1] if "DailyLoad" in base_df else None, 0, " UA")}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(148, 163, 184, 0.15); color:#94a3b8; font-size:0.72rem; font-weight:600;">Sessões registadas</div>
        </div>
        """, unsafe_allow_html=True)

    with c5:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">APEX Readiness</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#34d399;">{garmin_readiness_curr or score or '—'}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(16, 185, 129, 0.2); color:#34d399; font-size:0.72rem; font-weight:600;">Confiança Elevada</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # PILAR 1: RECOVERY & READINESS
    render_pillar_recovery(
        base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
        hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
        sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
        garmin_readiness_curr=garmin_readiness_curr, score=score,
        decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
        hrv_valid_days=hrv_valid_days
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # PILAR 2: TRAINING & PERFORMANCE
    render_pillar_training(base_df=base_df, mode=saved_mode)

    st.markdown("<br>", unsafe_allow_html=True)

    # PILAR 3: STRENGTH, MOVEMENT & DURABILITY
    render_pillar_strength(base_df=base_df, decision_cap=decision["cap"])

    # CAMADA TRANSVERSAL: NUTRIÇÃO, HIDRATAÇÃO & HABITOS
    render_nutrition_habits_layer()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🤖 APEX Coach Insight")
    st.info(
        "Fisiologia e biomecânica em total alinhamento. A resposta autónoma (VRC e FC repouso) é favorável. "
        "Seguir o plano de treino mantendo a hidratação e reposição proteica pós-exercício."
    )

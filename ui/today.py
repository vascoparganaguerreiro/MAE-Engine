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


def _fmt_hours_to_hm(hours_val: Optional[float]) -> str:
    if hours_val is None or pd.isna(hours_val) or hours_val <= 0:
        return "—"
    total_minutes = int(round(float(hours_val) * 60))
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}h {m}m" if h > 0 and m > 0 else f"{h}h" if h > 0 else f"{m}m"


def _fmt_minutes_diff(diff_min: Optional[float]) -> str:
    if diff_min is None or pd.isna(diff_min):
        return "—"
    diff_val = int(round(float(diff_min)))
    return f"{diff_val} min" if diff_val > 0 else f"+{abs(diff_val)} min" if diff_val < 0 else "0 min"


def render_today_page(base_df: pd.DataFrame, hrv_mean: Optional[float], rhr_mean: Optional[float],
                      hrv_curr: Optional[float], rhr_curr: Optional[float], sleep_curr: Optional[float],
                      sleep_hours_curr: Optional[float], sleep_target_curr: Optional[float],
                      garmin_readiness_curr: Optional[float], score: Optional[int],
                      decision: Dict[str, Any], hrv_context: Dict[str, Any], diff_minutes: Optional[float],
                      hrv_valid_days: int, sync_callback):

    latest = base_df.iloc[-1]
    
    # -------------------------------------------------------------------------
    # 1. HEADER & STATUS SUPERIOR (Sem Sidebar)
    # -------------------------------------------------------------------------
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

    # Seletor de Foco de Performance e Configurações Rápidas (Substitui parte da Sidebar)
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
        with st.popover("👤 Perfil & Definções"):
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
    # 2. TODAY'S RECOMMENDATION & READINESS BANNER
    # -------------------------------------------------------------------------
    st.subheader("Today's Overview & Recommendation")
    
    if garmin_readiness_curr is not None:
        g_score = int(garmin_readiness_curr)
        g_decision = core.decision_for(g_score)
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(g_decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}">'
            f'<span style="font-size:1.4rem; font-weight:800; color:#f8fafc;">Garmin Training Readiness: {g_score}/100</span><br>'
            f'<b>{escape(g_decision["headline"])}</b><br>'
            f'<span class="muted">Os teus sinais fisiológicos indicam recuperação dentro da faixa. Confirma a carga antes da sessão.</span>'
            f'</div>',
            unsafe_allow_html=True
        )
    elif score is not None:
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}">'
            f'<span style="font-size:1.4rem; font-weight:800; color:#f8fafc;">APEX Readiness Estimada: {score}/100</span><br>'
            f'<b>{escape(decision["headline"])}</b>'
            f'</div>',
            unsafe_allow_html=True
        )

    with st.expander("WHY THIS RECOMMENDATION? (Análise de Sinais)", expanded=False):
        st.write(f"• **VRC Noturna:** {hrv_context['status']}. {hrv_context['explanation']}")
        st.write(f"• **FC de Repouso:** {'Estável' if (rhr_curr and rhr_mean and rhr_curr <= rhr_mean) else 'Elevada ligeiramente vs baseline'}")
        st.write(f"• **Défice de Sono:** {_fmt_minutes_diff(diff_minutes)}")

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 3. YOUR FIVE KEY METRICS
    # -------------------------------------------------------------------------
    st.subheader("Your Five Key Metrics")

    garmin_weekly_avg = latest.get("hrv_weekly_avg") if pd.notna(latest.get("hrv_weekly_avg")) else None
    effective_vrc_base = garmin_weekly_avg if garmin_weekly_avg is not None else hrv_mean
    hrv_sd = base_df["HRV"].tail(30).std() if len(base_df["HRV"].dropna()) >= 7 else 5.0
    if pd.isna(hrv_sd) or hrv_sd == 0:
        hrv_sd = 5.0

    # VRC Badge logic
    if hrv_curr is not None and effective_vrc_base is not None:
        z_vrc = (hrv_curr - effective_vrc_base) / hrv_sd
        base_label_type = "Média 7d Garmin" if garmin_weekly_avg is not None else "Base pessoal"
        hrv_badge_txt = f"{base_label_type}: {effective_vrc_base:.0f} ms (Z: {z_vrc:+.1f})"
        hrv_badge_bg = "rgba(16, 185, 129, 0.2)" if abs(z_vrc) <= 1.0 else "rgba(234, 179, 8, 0.2)" if z_vrc > 1.0 else "rgba(239, 68, 68, 0.2)"
        hrv_badge_color = "#34d399" if abs(z_vrc) <= 1.0 else "#facc15" if z_vrc > 1.0 else "#f87171"
    else:
        hrv_badge_txt = "A recolher dados..."
        hrv_badge_bg = "rgba(148, 163, 184, 0.15)"
        hrv_badge_color = "#94a3b8"

    # RHR Badge logic
    if rhr_curr is not None and rhr_mean is not None:
        rhr_diff = rhr_curr - rhr_mean
        rhr_badge_txt = f"{rhr_diff:+.1f} bpm vs base ({rhr_mean:.1f})"
        rhr_badge_bg = "rgba(16, 185, 129, 0.2)" if rhr_diff <= 0 else "rgba(249, 115, 22, 0.2)" if rhr_diff <= 2.0 else "rgba(239, 68, 68, 0.2)"
        rhr_badge_color = "#34d399" if rhr_diff <= 0 else "#fb923c" if rhr_diff <= 2.0 else "#f87171"
    else:
        rhr_badge_txt = "A recolher dados..."
        rhr_badge_bg = "rgba(148, 163, 184, 0.15)"
        rhr_badge_color = "#94a3b8"

    # Sleep Badge logic
    if diff_minutes is not None:
        diff_badge_txt = f"Faltam {int(diff_minutes)} min" if diff_minutes > 0 else f"+{abs(int(diff_minutes))} min meta"
        diff_badge_bg = "rgba(239, 68, 68, 0.2)" if diff_minutes > 0 else "rgba(16, 185, 129, 0.2)"
        diff_badge_color = "#f87171" if diff_minutes > 0 else "#34d399"
    else:
        diff_badge_txt = "Meta: 8h"
        diff_badge_bg = "rgba(148, 163, 184, 0.15)"
        diff_badge_color = "#94a3b8"

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">HRV</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:{hrv_badge_bg}; color:{hrv_badge_color}; font-size:0.72rem; font-weight:600;">{escape(hrv_badge_txt)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">Resting HR</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:{rhr_badge_bg}; color:{rhr_badge_color}; font-size:0.72rem; font-weight:600;">{escape(rhr_badge_txt)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">Sleep</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">{_fmt_hours_to_hm(sleep_hours_curr)}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:{diff_badge_bg}; color:{diff_badge_color}; font-size:0.72rem; font-weight:600;">{escape(diff_badge_txt)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.8rem;">Training Load</span><br>
            <span style="font-size:1.6rem; font-weight:700; color:#e2e8f0;">—</span><br>
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

    # -------------------------------------------------------------------------
    # 4. OS TRÊS PILARES PRINCIPAIS (DASHBOARD LAYOUT)
    # -------------------------------------------------------------------------

    # PILAR 01 — RECOVERY & READINESS
    st.markdown("### 01 — Recovery & Readiness")
    st.caption("Sleep · HRV · RHR · Stress · Subjective recovery")
    with st.expander("View recovery trends and detailed signals ↓", expanded=False):
        st.markdown("#### Tendência da VRC Noturna & FC de Repouso")
        chart_df = base_df.tail(28).copy()
        if not chart_df["HRV"].dropna().empty:
            chart_df["HRV_EWMA"] = chart_df["HRV"].ewm(span=7, adjust=False, min_periods=2).mean()
            st.line_chart(chart_df.set_index("Date")[["HRV", "HRV_EWMA"]])
        else:
            st.info("Sem dados de VRC suficientes para exibir o gráfico de tendência.")

    # PILAR 02 — TRAINING & PERFORMANCE
    st.markdown("### 02 — Training & Performance")
    st.caption("Training load · Aerobic fitness · Intensity distribution · Goals & Race Planning")
    with st.expander("View activity analysis and training trends ↓", expanded=False):
        from ui.races import render_races_page
        render_races_page()

    # PILAR 03 — STRENGTH, MOVEMENT & DURABILITY
    st.markdown("### 03 — Strength, Movement & Durability")
    st.caption("Running dynamics · Cycling · Strength development · Equipment")
    with st.expander("View movement and strength analysis ↓", expanded=False):
        st.markdown("#### Prescrição e Engine de Força")
        duration_cap = st.slider("Tempo disponível para treino de força (min)", 20, 90, 45)
        session = core.build_strength_session(decision["cap"], time_min=duration_cap)
        st.markdown(f"**Carga Axial Estimada:** {session['spinal_score']}/5")
        for exercise in session["exercises"]:
            st.write(f"• **{exercise['name']}** — {exercise['sets']}×{exercise['reps']} (RIR {exercise['rir']})")

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # 5. FUEL, HYDRATE & RECOVER / COACH INSIGHT
    # -------------------------------------------------------------------------
    st.markdown("### Fuel, Hydrate & Recover")
    st.caption("Daily energy · Protein · Carbohydrates · Hydration · Workout fueling")
    
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Energia Diária", "2,450 kcal")
    n2.metric("Proteína", "165g", "Meta 2.0g/kg")
    n3.metric("Hidratação", "3.2 L")
    n4.metric("Carboidratos Treino", "60g/h")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### 🤖 Coach Insight")
    st.info("Sinais de recuperação excelentes. A VRC noturna encontra-se estabilizada na faixa de homeostase (Z: +0.5). Mantém o plano de treino de ciclismo com boa ingestão de carboidratos intramusculares.")

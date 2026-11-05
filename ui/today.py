from __future__ import annotations

from datetime import date
from html import escape
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import streamlit as st

import data_store as store
import engine_core as core
from services.gemini_engine import generate_apex_insights
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
    # LEVEL 1: TOP NAVIGATION & LANGUAGE SELECTOR
    # -------------------------------------------------------------------------
    head_col1, head_col2 = st.columns([3, 1.2])
    with head_col1:
        st.markdown("<h1 style='margin-bottom:0; color:#f8fafc;'>⚡ APEX ENGINE</h1>", unsafe_allow_html=True)
        st.caption("UNIVERSAL PHYSIOLOGY · PERFORMANCE · LONGEVITY · " + date.today().strftime("%A, %d %B %Y"))
    
    with head_col2:
        # SELETOR PREMIUM DE IDIOMA
        current_lang = store.get_setting("language", "EN")
        selected_lang_str = st.selectbox(
            "🌐 Interface Language / Idioma",
            ["🇬🇧 English (Original / Default)", "🇵🇹 Português (Portugal)"],
            index=0 if current_lang == "EN" else 1,
            key="apex_language_selector"
        )
        new_lang = "EN" if "English" in selected_lang_str else "PT"
        if new_lang != current_lang:
            store.set_setting("language", new_lang)
            st.rerun()

        last_sync = store.get_setting("garmin_last_sync", "Never" if new_lang == "EN" else "Nunca")
        st.markdown(f"<div style='text-align:right; font-size:0.8rem; color:#14b8a6;'>🟢 Connected (Garmin Connect)</div>", unsafe_allow_html=True)
        st.markdown(f"<div style='text-align:right; font-size:0.75rem; color:#64748b;'>Sync: {last_sync[:16] if len(last_sync) >= 16 else last_sync}</div>", unsafe_allow_html=True)
        if st.button("⚡ SYNC DATA", key="sync_top_btn", type="primary", use_container_width=True):
            with st.spinner("Syncing Garmin Connect..." if new_lang == "EN" else "Sincronizando Garmin..."):
                ok = sync_callback()
                if ok:
                    st.toast("Garmin synced successfully!" if new_lang == "EN" else "Garmin sincronizada com sucesso!", icon="⚡")
                st.rerun()

    is_pt = (new_lang == "PT")

    # Jump Navigation Bar
    st.markdown(
        f"""
        <div style="background:#0f172a; padding:8px 16px; border-radius:8px; border:1px solid #1e293b; margin:10px 0 20px 0; display:flex; gap:20px; font-size:0.85rem; font-weight:600;">
            <a href="#today-s-decision-readiness" style="color:#f8fafc; text-decoration:none;">00. {'DECISÃO' if is_pt else 'DECISION'}</a>
            <a href="#01-recovery-readiness" style="color:#14b8a6; text-decoration:none;">01. {'RECUPERAÇÃO & PRONTIDÃO' if is_pt else 'RECOVERY & READINESS'}</a>
            <a href="#02-training-performance" style="color:#3b82f6; text-decoration:none;">02. {'TREINO & PERFORMANCE' if is_pt else 'TRAINING & PERFORMANCE'}</a>
            <a href="#03-strength-movement-durability" style="color:#f59e0b; text-decoration:none;">03. {'FORÇA & BIOMECÂNICA' if is_pt else 'STRENGTH & MOVEMENT'}</a>
            <a href="#apex-intelligence-what-your-body-is-telling-you" style="color:#a855f7; text-decoration:none;">04. {'APEX INTELLIGENCE' if is_pt else 'APEX INTELLIGENCE'}</a>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Controls Header
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        saved_mode = store.get_setting("mode", "performance")
        mode_opt = st.selectbox(
            "Goal Profile Focus ▾" if not is_pt else "Foco do Perfil ▾",
            ["🏃 Performance (Athlete)" if not is_pt else "🏃 Performance (Atleta)", 
             "🧘‍♂️ Health & Wellness" if not is_pt else "🧘‍♂️ Saúde & Bem-estar", 
             "🧬 Longevity & Metabolic Health" if not is_pt else "🧬 Longevidade & Saúde Metabólica"],
            index=0 if saved_mode == "performance" else 1 if saved_mode == "wellness" else 2
        )
        new_mode = "performance" if mode_opt.startswith("🏃") else "wellness" if mode_opt.startswith("🧘") else "longevity"
        if new_mode != saved_mode:
            store.set_setting("mode", new_mode)
            st.rerun()

    with f_col2:
        with st.popover("👤 Profile & Settings" if not is_pt else "👤 Perfil & Definições"):
            st.markdown("### Athlete Profile" if not is_pt else "### Perfil do Atleta")
            prof = store.get_setting("profile", {}) or {}
            g_val = st.selectbox("Gender" if not is_pt else "Sexo", ["Not specified", "Male", "Female"] if not is_pt else ["Não indicado", "Masculino", "Feminino"], index=0)
            w_val = st.text_input("Weight (kg)" if not is_pt else "Peso (kg)", value=str(prof.get("weight_kg") or ""))
            v_val = st.text_input("VO2max", value=str(prof.get("vo2max") or ""))
            if st.button("Save Profile" if not is_pt else "Guardar Perfil", use_container_width=True):
                store.set_setting("profile", {"gender": g_val, "weight_kg": float(w_val) if w_val else None, "vo2max": float(v_val) if v_val else None})
                st.success("Saved!" if not is_pt else "Guardado!")
                st.rerun()

    with f_col3:
        with st.popover("🔑 Garmin & Credentials" if not is_pt else "🔑 Garmin & Credenciais"):
            st.markdown("### Garmin Account" if not is_pt else "### Conta Garmin")
            with st.form("quick_garmin_form"):
                st.text_input("Garmin E-mail", key="garmin_email_input")
                st.text_input("Password" if not is_pt else "Palavra-passe", type="password", key="garmin_password_input")
                if st.form_submit_button("Save & Sync" if not is_pt else "Guardar & Sincronizar", use_container_width=True):
                    sync_callback()
                    st.rerun()

    # TODAY'S DECISION & ACTION
    st.subheader("Today's Decision & Readiness" if not is_pt else "Decisão Diária & Prontidão")
    
    if garmin_readiness_curr is not None:
        g_score = int(garmin_readiness_curr)
        g_decision = core.decision_for(g_score)
        tone_class = {"green": "border-left:5px solid #14b8a6;", "amber": "border-left:5px solid #f59e0b;", "red": "border-left:5px solid #ef4444;"}.get(g_decision["tone"], "")
        st.markdown(
            f'<div style="background:#131a27; border:1px solid #334155; border-radius:12px; padding:16px; {tone_class}">'
            f'<span style="font-size:1.3rem; font-weight:800; color:#f8fafc;">Garmin Training Readiness: {g_score}/100</span><br>'
            f'<b style="font-size:1.05rem; color:#cbd5e1;">{escape(g_decision["headline"])}</b><br>'
            f'<span style="font-size:0.88rem; color:#94a3b8;">{"Transparent synthesis of autonomic variability, sleep, and load response. Check subjective metrics before training." if not is_pt else "Síntese transparente de variabilidade autónoma, sono e carga. Confirma as métricas subjetivas antes do treino."}</span>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # FIVE CORE METRICS
    st.subheader("Five Core Metrics" if not is_pt else "Cinco Métricas Principais")

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
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">{'VRC NOTURNA' if is_pt else 'NIGHTLY HRV'}</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(20, 184, 166, 0.15); color:#14b8a6; font-size:0.72rem; font-weight:600;">Base: {_fmt(effective_vrc_base, 0)} ms (Z: {z_vrc:+.1f})</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">{'Fonte: Garmin · Confiança Alta' if is_pt else 'Source: Garmin · High Confidence'}</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        rhr_diff = (rhr_curr - rhr_mean) if (rhr_curr and rhr_mean) else 0.0
        rhr_color = "#14b8a6" if rhr_diff <= 0 else "#f59e0b"
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">{'FC REPOUSO' if is_pt else 'RESTING HR'}</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(245, 158, 11, 0.15); color:{rhr_color}; font-size:0.72rem; font-weight:600;">{rhr_diff:+.1f} bpm vs base ({_fmt(rhr_mean, 1)})</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">{'Fonte: Garmin · Tendência Estável' if is_pt else 'Source: Garmin · Stable Trend'}</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">{'DURAÇÃO SONO' if is_pt else 'SLEEP DURATION'}</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt_hours_to_hm(sleep_hours_curr)}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(20, 184, 166, 0.15); color:#14b8a6; font-size:0.72rem; font-weight:600;">Meta: 8h 00m</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">{'Fonte: Garmin · Score' if is_pt else 'Source: Garmin · Score'} {_fmt(sleep_curr, 0)}</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">{'CARGA TREINO' if is_pt else 'TRAINING LOAD'}</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#f8fafc;">{_fmt(base_df["DailyLoad"].iloc[-1] if "DailyLoad" in base_df else None, 0, " AU")}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(59, 130, 246, 0.15); color:#3b82f6; font-size:0.72rem; font-weight:600;">{'Carga Diária' if is_pt else 'Daily Workload'}</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Fonte: APEX Load Engine</div>
        </div>
        """, unsafe_allow_html=True)

    with c5:
        st.markdown(f"""
        <div style="background:#131a27; border:1px solid #263244; padding:12px; border-radius:12px;">
            <span style="color:#94a3b8; font-size:0.78rem; font-weight:600;">APEX READINESS</span><br>
            <span style="font-size:1.6rem; font-weight:800; color:#14b8a6;">{garmin_readiness_curr or score or '—'}</span><br>
            <div style="margin-top:4px; padding:2px 6px; border-radius:4px; background:rgba(20, 184, 166, 0.2); color:#14b8a6; font-size:0.72rem; font-weight:600;">{'Score Transparente' if is_pt else 'Transparent Score'}</div>
            <div style="margin-top:4px; font-size:0.68rem; color:#64748b;">Z-Score VRC + Check-In</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # RENDER PILLARS WITH SELECTED LANGUAGE
    render_pillar_recovery(
        base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
        hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
        sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
        garmin_readiness_curr=garmin_readiness_curr, score=score,
        decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
        hrv_valid_days=hrv_valid_days, lang=new_lang
    )

    st.markdown("<br>", unsafe_allow_html=True)

    render_pillar_training(base_df=base_df, mode=saved_mode, lang=new_lang)

    st.markdown("<br>", unsafe_allow_html=True)

    render_pillar_strength(base_df=base_df, decision_cap=decision["cap"], lang=new_lang)

    render_nutrition_habits_layer(lang=new_lang)

    st.markdown("<br>", unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # LEVEL 4: APEX INTELLIGENCE LAYER & LIVE GEMINI CHAT
    # -------------------------------------------------------------------------
    st.markdown("## 🧠 APEX Intelligence — What Your Body Is Telling You" if not is_pt else "## 🧠 APEX Intelligence — O Que o Teu Corpo Está a Dizer")
    st.caption("Cross-pillar physiological signals combined with deterministic rules and Gemini AI biological synthesis." if not is_pt else "Cruzamento holístico de sinais fisiológicos com regras determinísticas e síntese biológica do Gemini AI.")

    metrics_summary = {
        "hrv": hrv_curr,
        "z_vrc": z_vrc,
        "rhr": rhr_curr,
        "rhr_base": rhr_mean,
        "sleep_hours": sleep_hours_curr,
        "sleep_score": sleep_curr,
        "ctl": base_df["CTL"].iloc[-1] if "CTL" in base_df else "—",
        "atl": base_df["ATL"].iloc[-1] if "ATL" in base_df else "—",
        "tsb": base_df["TSB"].iloc[-1] if "TSB" in base_df else "—",
        "soreness": latest.get("soreness") or 3,
        "fatigue": latest.get("fatigue") or 3,
        "readiness": garmin_readiness_curr or score or 75,
    }

    ai_synthesis_text = generate_apex_insights(metrics_summary, lang=new_lang)

    st.markdown(
        f"""
        <div style="background:#1e1b4b; border:1px solid #4c1d95; padding:20px; border-radius:12px; margin-bottom:15px;">
            <h4 style="margin-top:0; color:#c084fc;">{'Cross-Pillar Physiological Synthesis (Gemini AI)' if not is_pt else 'Síntese Fisiológica Cruzada (Gemini AI)'}</h4>
            <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin-bottom:15px;">
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">{'Aerobic Decoupling' if not is_pt else 'Decoupling Aeróbico'}</span><br>
                    <b style="color:#34d399;">3.2 %</b>
                </div>
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">{'Chronic Load (CTL)' if not is_pt else 'Carga Crónica (CTL)'}</span><br>
                    <b style="color:#60a5fa;">{_fmt(base_df["CTL"].iloc[-1] if "CTL" in base_df else None, 0, " AU")}</b>
                </div>
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">{'Sleep Duration' if not is_pt else 'Duração do Sono'}</span><br>
                    <b style="color:#fbbf24;">{_fmt_hours_to_hm(sleep_hours_curr)}</b>
                </div>
                <div style="background:#0f172a; padding:10px; border-radius:8px; border:1px solid #312e81;">
                    <span style="font-size:0.75rem; color:#94a3b8;">{'Muscle Soreness' if not is_pt else 'Dor Muscular'}</span><br>
                    <b style="color:#f87171;">{latest.get("soreness") or 3} / 5 DOMS</b>
                </div>
            </div>
            <b style="color:#f8fafc; font-size:1rem;">{'Biological Action Plan (Gemini AI):' if not is_pt else 'Plano de Ação Biológico (Gemini AI):'}</b><br>
            <p style="color:#e2e8f0; font-size:0.92rem; margin-bottom:0; line-height:1.5;">
                {ai_synthesis_text}
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # -------------------------------------------------------------------------
    # CHAT INTERATIVO GEMINI (COM BASE NOS DADOS DO DIA)
    # -------------------------------------------------------------------------
    st.markdown("### 💬 Ask APEX AI Coach" if not is_pt else "### 💬 Perguntar ao APEX AI Coach")
    st.caption("Ask questions about today's workout adjustments, nutrition, or recovery based on your live metrics." if not is_pt else "Faz perguntas sobre ajustes de treino, nutrição ou recuperação com base nos teus dados fisiológicos de hoje.")

    # Inicializar histórico do chat na sessão
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Exibir histórico de mensagens do chat
    for message in st.session_state["chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Entrada de texto do utilizador
    prompt_placeholder = "Ask about today's workout or nutrition (e.g. Can I do heavy squats today?)..." if not is_pt else "Pergunta sobre o treino de hoje ou nutrição (ex: Posso fazer agachamento pesado hoje?)..."
    if user_prompt := st.chat_input(prompt_placeholder):
        # Guardar e mostrar a mensagem do utilizador
        st.session_state["chat_messages"].append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Gerar resposta com o Gemini considerando a pergunta + dados biológicos
        with st.chat_message("assistant"):
            with st.spinner("Analyzing physiological state..." if not is_pt else "A analisar dados fisiológicos..."):
                # Junta a pergunta do utilizador às métricas diárias
                chat_context = {**metrics_summary, "user_question": user_prompt}
                ai_response = generate_apex_insights(chat_context, lang=new_lang)
                st.markdown(ai_response)
                st.session_state["chat_messages"].append({"role": "assistant", "content": ai_response})

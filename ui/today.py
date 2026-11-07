from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, Optional

import pandas as pd
import streamlit as st

import data_store as store
import services.auth as auth
from gemini_engine import generate_apex_insights


def render_today_page(
    base_df: pd.DataFrame,
    hrv_mean: Optional[float],
    rhr_mean: Optional[float],
    hrv_curr: Optional[float],
    rhr_curr: Optional[float],
    sleep_curr: Optional[float],
    sleep_hours_curr: Optional[float],
    sleep_target_curr: Optional[float],
    garmin_readiness_curr: Optional[float],
    score: Optional[int],
    decision: Dict[str, str],
    hrv_context: Dict[str, Any],
    diff_minutes: Optional[float],
    hrv_valid_days: int,
    sync_callback: Callable[[], bool],
) -> None:
    # Gestão de Navegação por Separador na Session State
    if "active_nav_tab" not in st.session_state:
        st.session_state["active_nav_tab"] = "decision"

    # --- TOP EXECUTIVE HEADER ---
    st.markdown(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0 24px 0; border-bottom: 1px solid rgba(255,255,255,0.08);">
            <div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 10px; height: 10px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 10px #38bdf8;"></div>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 1.3rem; font-weight: 700; letter-spacing: 0.05em; color: #f8fafc;">APEX ENGINE</span>
                    <span style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">Executive v3.8</span>
                </div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748b; margin-top: 4px;">
                    UNIVERSAL PHYSIOLOGY &bull; PERFORMANCE &bull; LONGEVITY &bull; {date.today().strftime('%A, %d %B %Y').upper()}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- BARRA DE ACÇÕES RÁPIDAS & PERFIL ---
    col_user, col_actions = st.columns([2, 1.2])

    with col_user:
        current_email = getattr(st.session_state.get("user"), "email", "")
        st.markdown(
            f"""
            <div style="padding-top: 10px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #94a3b8;">
                <span style="color: #64748b;">Sessão Ativa:</span> <span style="color: #38bdf8;">{current_email}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_actions:
        c_sync, c_prof, c_logout = st.columns([1.1, 1, 1])
        with c_sync:
            if st.button("⚡ Sync Garmin", use_container_width=True):
                with st.spinner("Sincronizando..."):
                    sync_callback()
                    st.rerun()
        with c_prof:
            if st.button("⚙️ Perfil", use_container_width=True):
                st.session_state["show_settings_modal"] = not st.session_state.get("show_settings_modal", False)
        with c_logout:
            if st.button("Sair", use_container_width=True):
                auth.logout()
                st.rerun()

    # Modal de Definições / Perfil
    if st.session_state.get("show_settings_modal", False):
        with st.expander("⚙️ Painel de Configurações Executivas & Garmin Credentials", expanded=True):
            st.markdown("<div style='font-family: JetBrains Mono; font-size: 0.85rem; color: #38bdf8; margin-bottom: 10px;'>CONFIGURAÇÃO DE CREDENCIAIS GARMIN CONNECT</div>", unsafe_allow_html=True)
            g_email = st.text_input("Garmin Email", value=st.session_state.get("garmin_email_input", ""), key="garmin_email_input")
            g_pass = st.text_input("Garmin Password", type="password", value=st.session_state.get("garmin_password_input", ""), key="garmin_password_input")
            
            st.markdown("<div style='font-family: JetBrains Mono; font-size: 0.85rem; color: #38bdf8; margin-top: 15px; margin-bottom: 10px;'>MODO DE ALOCAÇÃO FISIOLÓGICA</div>", unsafe_allow_html=True)
            curr_mode = store.get_setting("mode", "performance")
            new_mode = st.selectbox("Modo APEX", options=["performance", "longevity"], index=0 if curr_mode == "performance" else 1)
            if new_mode != curr_mode:
                store.save_setting("mode", new_mode)
                st.rerun()

    st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)

    # --- COMPONENTE PRINCIPAL SEGUNDO O SEPARADOR ATIVO ---
    current_tab = st.session_state["active_nav_tab"]

    if current_tab == "decision":
        # 1. BANNER DE PRONTIDÃO EXEC & CAPACIDADE
        tone_color = "#10b981" if decision["tone"] == "green" else "#f59e0b" if decision["tone"] == "amber" else "#ef4444"
        score_display = f"{score}" if score is not None else "--"

        st.markdown(
            f"""
            <div class="apex-card" style="border-left: 4px solid {tone_color};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 15px;">
                    <div>
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.1em;">Directriz do Dia &bull; Readiness Index</div>
                        <div style="font-size: 1.4rem; font-weight: 700; color: #f8fafc; margin-top: 4px;">{decision['headline']}</div>
                        <div style="font-size: 0.88rem; color: #94a3b8; margin-top: 6px;">{hrv_context.get('explanation', '')}</div>
                    </div>
                    <div style="text-align: right; background: rgba(0,0,0,0.3); padding: 12px 24px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #64748b; text-transform: uppercase;">APEX Readiness</div>
                        <div class="mono-val" style="font-size: 2.4rem; color: {tone_color}; line-height: 1.1;">{score_display}<span style="font-size: 1rem; color: #64748b;">/100</span></div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 2. CARDS DE TELEMETRIA EXEC (5 CORE METRICS)
        st.markdown("<div style='font-family: JetBrains Mono; font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin: 20px 0 10px 0;'>Fisiologia & Carga Biológica</div>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)

        with m1:
            val = f"{int(hrv_curr)} ms" if hrv_curr is not None else "--"
            sub = f"Base: {int(hrv_mean)} ms" if hrv_mean is not None else "Sem histórico"
            st.markdown(
                f"""
                <div class="apex-card" style="padding: 16px;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">VRC Noturna (HRV)</div>
                    <div class="mono-val" style="font-size: 1.5rem; color: #f8fafc; margin: 6px 0;">{val}</div>
                    <div class="mono-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m2:
            val = f"{int(rhr_curr)} bpm" if rhr_curr is not None else "--"
            sub = f"Base: {int(rhr_mean)} bpm" if rhr_mean is not None else "Sem histórico"
            st.markdown(
                f"""
                <div class="apex-card" style="padding: 16px;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">FC Repouso (RHR)</div>
                    <div class="mono-val" style="font-size: 1.5rem; color: #f8fafc; margin: 6px 0;">{val}</div>
                    <div class="mono-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m3:
            val = f"{sleep_hours_curr:.1f} h" if sleep_hours_curr is not None else "--"
            sub = f"Score: {int(sleep_curr)}" if sleep_curr is not None else "Meta: 8.0 h"
            st.markdown(
                f"""
                <div class="apex-card" style="padding: 16px;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">Duração do Sono</div>
                    <div class="mono-val" style="font-size: 1.5rem; color: #f8fafc; margin: 6px 0;">{val}</div>
                    <div class="mono-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m4:
            load_val = base_df["DailyLoad"].iloc[-1] if not base_df.empty and "DailyLoad" in base_df else 0.0
            val = f"{int(load_val)} AU"
            ctl_val = base_df["CTL"].iloc[-1] if not base_df.empty and "CTL" in base_df else 0.0
            sub = f"Fitness (CTL): {int(ctl_val)}"
            st.markdown(
                f"""
                <div class="apex-card" style="padding: 16px;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">Carga Diária (AU)</div>
                    <div class="mono-val" style="font-size: 1.5rem; color: #38bdf8; margin: 6px 0;">{val}</div>
                    <div class="mono-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m5:
            garmin_val = f"{int(garmin_readiness_curr)}" if garmin_readiness_curr is not None else "--"
            st.markdown(
                f"""
                <div class="apex-card" style="padding: 16px;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: #94a3b8; text-transform: uppercase;">Prontidão Garmin</div>
                    <div class="mono-val" style="font-size: 1.5rem; color: #f8fafc; margin: 6px 0;">{garmin_val}<span style="font-size: 0.9rem; color: #64748b;">/100</span></div>
                    <div class="mono-sub">Garmin Connect Metric</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 3. APEX INTELLIGENCE INSIGHTS (GEMINI INTEGRATION)
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        summary_payload = {
            "hrv": hrv_curr,
            "sleep_hours": sleep_hours_curr,
            "readiness": score,
        }
        insight_text = generate_apex_insights(summary_payload, lang="PT")

        st.markdown(
            f"""
            <div class="apex-card" style="background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(56, 189, 248, 0.2);">
                <div style="display: flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #38bdf8; text-transform: uppercase; margin-bottom: 8px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                    APEX Intelligence Synthesis
                </div>
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.5;">{insight_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    elif current_tab == "recovery":
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>01. Recuperação & Análise de VRC</h3><p style='color: #94a3b8; font-size: 0.9rem;'>Histórico detalhado da variabilidade da frequência cardíaca e arquitetura do sono.</p></div>", unsafe_allow_html=True)
        if not base_df.empty:
            st.line_chart(base_df.set_index("Date")[["HRV", "RHR"]].dropna())

    elif current_tab == "training":
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>02. Treino & Gestão de Carga Banister</h3><p style='color: #94a3b8; font-size: 0.9rem;'>Modelos de Fitness (CTL), Fadiga (ATL) e Prontidão de Desempenho (TSB).</p></div>", unsafe_allow_html=True)
        if not base_df.empty and "CTL" in base_df:
            st.line_chart(base_df.set_index("Date")[["CTL", "ATL", "TSB"]].dropna())

    elif current_tab == "strength":
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>03. Força & Prescrição Mecânica</h3><p style='color: #94a3b8; font-size: 0.9rem;'>Autoregulação de sessões de força em função da carga espinal e RIR.</p></div>", unsafe_allow_html=True)

    elif current_tab == "intelligence":
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>04. APEX Intelligence & AI Consultation</h3><p style='color: #94a3b8; font-size: 0.9rem;'>Consultoria fisiológica direta com o modelo Gemini APEX Engine.</p></div>", unsafe_allow_html=True)
        prompt_in = st.text_input("Questão Fisiológica / Consultoria de Treino:")
        if prompt_in:
            with st.spinner("Analisando biométricas..."):
                resp = generate_apex_insights({"hrv": hrv_curr, "sleep_hours": sleep_hours_curr, "readiness": score, "user_question": prompt_in}, lang="PT")
                st.write(resp)

    # Margem para o Dock não tapar o conteúdo
    st.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)

    # --- FLOATING BOTTOM EXECUTIVE NAVIGATION DOCK ---
    st.markdown(
        """
        <style>
          .dock-container {
              position: fixed;
              bottom: 20px;
              left: 50%;
              transform: translateX(-50%);
              background: rgba(11, 15, 23, 0.85);
              backdrop-filter: blur(20px);
              -webkit-backdrop-filter: blur(20px);
              border: 1px solid rgba(255, 255, 255, 0.12);
              border-radius: 40px;
              padding: 6px 14px;
              display: flex;
              align-items: center;
              gap: 8px;
              box-shadow: 0 20px 50px rgba(0,0,0,0.6);
              z-index: 999999;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Streamlit Navigation Trigger Buttons em Grid Flutuante
    dock_cols = st.columns([1, 1, 1, 1, 1])
    
    with dock_cols[0]:
        if st.button("00. DECISION", use_container_width=True, key="btn_nav_decision"):
            st.session_state["active_nav_tab"] = "decision"
            st.rerun()
    with dock_cols[1]:
        if st.button("01. RECOVERY", use_container_width=True, key="btn_nav_recovery"):
            st.session_state["active_nav_tab"] = "recovery"
            st.rerun()
    with dock_cols[2]:
        if st.button("02. TRAINING", use_container_width=True, key="btn_nav_training"):
            st.session_state["active_nav_tab"] = "training"
            st.rerun()
    with dock_cols[3]:
        if st.button("03. STRENGTH", use_container_width=True, key="btn_nav_strength"):
            st.session_state["active_nav_tab"] = "strength"
            st.rerun()
    with dock_cols[4]:
        if st.button("04. AI APEX", use_container_width=True, key="btn_nav_intel"):
            st.session_state["active_nav_tab"] = "intelligence"
            st.rerun()

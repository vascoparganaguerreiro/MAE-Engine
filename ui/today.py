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

    # --- TOP EXECUTIVE HEADER ---
    st.markdown(
        f"""
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0 20px 0; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 20px;">
            <div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="width: 10px; height: 10px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 12px #38bdf8;"></div>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 700; letter-spacing: 0.05em; color: #f8fafc;">APEX ENGINE</span>
                    <span style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">Executive v3.8</span>
                </div>
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748b; margin-top: 4px;">
                    UNIVERSAL PHYSIOLOGY &bull; PERFORMANCE &bull; LONGEVITY &bull; {date.today().strftime('%A, %d %B %Y').upper()}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- CONTROL BAR ---
    col_info, col_btns = st.columns([2, 1.3])
    with col_info:
        current_email = getattr(st.session_state.get("user"), "email", "")
        last_sync = store.get_setting("garmin_last_sync", "Nunca")
        st.markdown(
            f"""
            <div style="padding-top: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #94a3b8;">
                <span style="color: #64748b;">Sessão Ativa:</span> <span style="color: #38bdf8;">{current_email}</span>
                <span style="color: #475569; margin: 0 8px;">|</span>
                <span style="color: #64748b;">Última Sync:</span> <span style="color: #cbd5e1;">{last_sync}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_btns:
        c_sync, c_prof, c_out = st.columns([1.2, 1, 1])
        with c_sync:
            if st.button("⚡ Sync Garmin", use_container_width=True):
                with st.spinner("Conectando à Garmin..."):
                    sync_callback()
                    st.rerun()
        with c_prof:
            if st.button("⚙️ Perfil", use_container_width=True):
                st.session_state["show_settings_modal"] = not st.session_state.get("show_settings_modal", False)
        with c_out:
            if st.button("Sair", use_container_width=True):
                auth.logout()
                st.rerun()

    # Modal de Definições com Verificador de Ligação
    if st.session_state.get("show_settings_modal", False):
        with st.expander("⚙️ Painel de Diagnóstico & Credenciais Garmin", expanded=True):
            st.markdown("<div style='font-family: JetBrains Mono; font-size: 0.82rem; color: #38bdf8; margin-bottom: 8px;'>CREDENCIAIS GARMIN CONNECT</div>", unsafe_allow_html=True)
            g_email = st.text_input("Garmin Email", value=st.session_state.get("garmin_email_input", ""), key="garmin_email_input")
            g_pass = st.text_input("Garmin Password", type="password", value=st.session_state.get("garmin_password_input", ""), key="garmin_password_input")
            
            # Badge de Estado da API
            has_creds = bool(g_email and g_pass) or bool(st.secrets.get("GARMIN_EMAIL"))
            status_color = "#10b981" if has_creds else "#f59e0b"
            status_text = "CREDENCIAIS CONFIGURADAS" if has_creds else "CREDENCIAIS EM FALTA"
            
            st.markdown(
                f"""
                <div style="background: rgba(15, 23, 42, 0.6); padding: 10px 14px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08); margin: 10px 0;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: {status_color}; text-transform: uppercase;">● {status_text}</span>
                    <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 4px;">Dica: Sincroniza a aplicação oficial Garmin Connect no telemóvel antes de clicar em ⚡ Sync Garmin.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            curr_mode = store.get_setting("mode", "performance")
            new_mode = st.selectbox("Modo de Alocação Fisiológica", options=["performance", "longevity"], index=0 if curr_mode == "performance" else 1)
            if new_mode != curr_mode:
                store.save_setting("mode", new_mode)
                st.rerun()

    st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

    # --- SEPARADORES ---
    t0, t1, t2, t3, t4 = st.tabs([
        "00. DECISION",
        "01. RECOVERY & READINESS",
        "02. TRAINING & PERFORMANCE",
        "03. STRENGTH & MOVEMENT",
        "04. APEX INTELLIGENCE",
    ])

    with t0:
        tone_color = "#10b981" if decision["tone"] == "green" else "#f59e0b" if decision["tone"] == "amber" else "#ef4444"
        score_display = f"{score}" if score is not None else "--"

        st.markdown(
            f"""
            <div class="apex-card" style="border-left: 4px solid {tone_color};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 15px;">
                    <div>
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.1em;">Directriz do Dia &bull; Readiness Index</div>
                        <div style="font-size: 1.35rem; font-weight: 700; color: #f8fafc; margin-top: 4px;">{decision['headline']}</div>
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

        st.markdown("<div style='font-family: JetBrains Mono; font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin: 20px 0 10px 0;'>Fisiologia & Carga Biológica</div>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)

        with m1:
            val = f"{int(hrv_curr)} ms" if hrv_curr is not None else "--"
            sub = f"Base: {int(hrv_mean)} ms" if hrv_mean is not None else "Sem histórico"
            st.markdown(
                f"""
                <div class="apex-card" style="padding: 16px;">
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">VRC Noturna (HRV)</div>
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
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">FC Repouso (RHR)</div>
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
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">Duração do Sono</div>
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
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">Carga Diária (AU)</div>
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
                    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.68rem; color: #94a3b8; text-transform: uppercase;">Prontidão Garmin</div>
                    <div class="mono-val" style="font-size: 1.5rem; color: #f8fafc; margin: 6px 0;">{garmin_val}<span style="font-size: 0.9rem; color: #64748b;">/100</span></div>
                    <div class="mono-sub">Garmin Connect Metric</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        summary_payload = {"hrv": hrv_curr, "sleep_hours": sleep_hours_curr, "readiness": score}
        insight_text = generate_apex_insights(summary_payload, lang="PT")

        st.markdown(
            f"""
            <div class="apex-card" style="background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(56, 189, 248, 0.25);">
                <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #38bdf8; text-transform: uppercase; margin-bottom: 8px;">
                    ⚡ APEX Intelligence Synthesis (Gemini AI)
                </div>
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.5;">{insight_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t1:
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>01. Fisiologia Noturna & Tendência de VRC</h3><p style='color: #94a3b8; font-size: 0.88rem;'>Compara a Variabilidade da Frequência Cardíaca (HRV) e RHR contra a tua linha de base de 60 dias.</p></div>", unsafe_allow_html=True)
        if not base_df.empty:
            st.line_chart(base_df.set_index("Date")[["HRV", "RHR"]].dropna())

    with t2:
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>02. Modelo de Carga Fisiológica Banister</h3><p style='color: #94a3b8; font-size: 0.88rem;'>Monitorização de Fitness (CTL 42d), Fadiga (ATL 7d) e Equilíbrio de Carga (TSB).</p></div>", unsafe_allow_html=True)
        if not base_df.empty and "CTL" in base_df:
            st.line_chart(base_df.set_index("Date")[["CTL", "ATL", "TSB"]].dropna())

    with t3:
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>03. Prescrição Mecânica & Carga Espinal</h3><p style='color: #94a3b8; font-size: 0.88rem;'>Algoritmo de seleção de exercícios de força adaptado à prontidão do dia.</p></div>", unsafe_allow_html=True)

    with t4:
        st.markdown("<div class='apex-card'><h3 style='font-family: JetBrains Mono; font-size: 1.1rem; color: #f8fafc;'>04. Consultoria Fisiológica Gemini APEX</h3><p style='color: #94a3b8; font-size: 0.88rem;'>Faz perguntas diretas sobre os teus dados fisiológicos, recuperação e estratégia de prova.</p></div>", unsafe_allow_html=True)
        user_q = st.text_input("Escreve a tua questão para o Coach IA APEX:")
        if user_q:
            with st.spinner("Analisando dados fisiológicos..."):
                resp = generate_apex_insights({"hrv": hrv_curr, "sleep_hours": sleep_hours_curr, "readiness": score, "user_question": user_q}, lang="PT")
                st.markdown(
                    f"""
                    <div class="apex-card" style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(56, 189, 248, 0.3); margin-top: 15px;">
                        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #38bdf8; text-transform: uppercase; margin-bottom: 8px;">Resposta do APEX Coach:</div>
                        <div style="font-size: 0.95rem; color: #f8fafc; line-height: 1.6;">{resp}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

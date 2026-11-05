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
    if h > 0 and m > 0:
        return f"{h}h {m}m"
    elif h > 0:
        return f"{h}h"
    return f"{m}m"


def _fmt_minutes_diff(diff_min: Optional[float]) -> str:
    if diff_min is None or pd.isna(diff_min):
        return "—"
    diff_val = int(round(float(diff_min)))
    if diff_val > 0:
        return f"{diff_val} min"
    elif diff_val < 0:
        return f"+{abs(diff_val)} min"
    return "0 min"


def _optional_float(raw: Any, label: str, minimum: Optional[float] = None,
                    maximum: Optional[float] = None) -> Optional[float]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(str(raw).replace(",", ".").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label}: introduz um número válido ou deixa em branco.")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}: o valor mínimo é {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}: o valor máximo é {maximum}.")
    return value


def render_today_page(base_df: pd.DataFrame, hrv_mean: Optional[float], rhr_mean: Optional[float],
                      hrv_curr: Optional[float], rhr_curr: Optional[float], sleep_curr: Optional[float],
                      sleep_hours_curr: Optional[float], sleep_target_curr: Optional[float],
                      garmin_readiness_curr: Optional[float], score: Optional[int],
                      decision: Dict[str, Any], hrv_context: Dict[str, Any], diff_minutes: Optional[float],
                      hrv_valid_days: int, sync_callback):

    latest = base_df.iloc[-1]

    head_col1, head_col2 = st.columns([3, 1])
    with head_col1:
        st.subheader("📝 Daily Check-In")
    with head_col2:
        if st.button("⚡ SYNC DATA", key="sync_data_top_btn", type="primary"):
            with st.spinner("Sincronizando Garmin..."):
                ok = sync_callback()
                if ok:
                    st.toast("Garmin sincronizada com sucesso!", icon="⚡")
                st.rerun()

    with st.expander("Registar métricas de hoje ou corrigir um dia anterior", expanded=False):
        with st.form("daily_checkin_form"):
            check_day = st.date_input("Data do registo", value=date.today(), max_value=date.today())
            c1, c2, c3, c4 = st.columns(4)
            hrv_input = c1.text_input("VRC noturna (ms)", placeholder="Em branco = sem dado")
            rhr_input = c2.text_input("FC repouso (bpm)", placeholder="Em branco = sem dado")
            sleep_score_input = c3.text_input("Sleep score (0-100)", placeholder="Em branco = sem dado")
            sleep_hours_input = c4.text_input("Sono (horas)", placeholder="Em branco = sem dado")
            st.caption("Diário subjetivo: 1 = baixo/mínimo; 5 = alto/máximo.")
            s1, s2, s3 = st.columns(3)
            soreness_input = s1.slider("Dor muscular / DOMS", 1, 5, 3)
            stress_input = s2.slider("Stress", 1, 5, 3)
            mood_input = s3.slider("Humor / motivação", 1, 5, 3)
            save_checkin = st.form_submit_button("Guardar check-in", use_container_width=True)
        if save_checkin:
            try:
                metrics = {
                    "hrv": _optional_float(hrv_input, "VRC", 0, 300),
                    "rhr": _optional_float(rhr_input, "FC repouso", 25, 220),
                    "sleep_score": _optional_float(sleep_score_input, "Sleep score", 0, 100),
                    "sleep_hours": _optional_float(sleep_hours_input, "Horas de sono", 0, 24),
                    "soreness": soreness_input, "stress": stress_input, "mood": mood_input,
                }
                store.upsert_daily_metrics(check_day, metrics, source="manual")
                st.success("Check-in guardado na base de dados local.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    # Fontes dos dados
    hrv_src = str(latest.get("hrv_source")) if pd.notna(latest.get("hrv_source")) else "Sem dado"
    rhr_src = str(latest.get("rhr_source")) if pd.notna(latest.get("rhr_source")) else "Sem dado"
    sleep_src = str(latest.get("sleep_hours_source")) if pd.notna(latest.get("sleep_hours_source")) else "Sem dado"

    # --- CÁLCULO DE CORES FISIOLÓGICAS ---
    
    # 1. VRC (Prioriza Média de 7d da Garmin Connect se disponível)
    garmin_weekly_avg = latest.get("hrv_weekly_avg") if pd.notna(latest.get("hrv_weekly_avg")) else None
    effective_vrc_base = garmin_weekly_avg if garmin_weekly_avg is not None else hrv_mean
    
    hrv_sd = base_df["HRV"].tail(30).std() if len(base_df["HRV"].dropna()) >= 7 else 5.0
    if pd.isna(hrv_sd) or hrv_sd == 0:
        hrv_sd = 5.0

    if hrv_curr is not None and effective_vrc_base is not None:
        z_vrc = (hrv_curr - effective_vrc_base) / hrv_sd
        base_label_type = "Média 7d Garmin" if garmin_weekly_avg is not None else "Base pessoal"
        hrv_badge_txt = f"{base_label_type}: {effective_vrc_base:.0f} ms (Z: {z_vrc:+.1f})"
        
        if abs(z_vrc) <= 1.0:
            hrv_badge_bg = "rgba(16, 185, 129, 0.2)"   # Verde (Normal)
            hrv_badge_color = "#34d399"
        elif 1.0 < z_vrc <= 1.5:
            hrv_badge_bg = "rgba(234, 179, 8, 0.2)"    # Amarelo
            hrv_badge_color = "#facc15"
        elif -1.5 <= z_vrc < -1.0:
            hrv_badge_bg = "rgba(249, 115, 22, 0.2)"   # Laranja
            hrv_badge_color = "#fb923c"
        else:
            hrv_badge_bg = "rgba(239, 68, 68, 0.2)"    # Vermelho
            hrv_badge_color = "#f87171"
    else:
        hrv_badge_txt = f"Base: {_fmt(hrv_mean, 1, ' ms')}" if hrv_mean is not None else f"[{hrv_src}]"
        hrv_badge_bg = "rgba(148, 163, 184, 0.15)"
        hrv_badge_color = "#94a3b8"

    # 2. FC de Repouso (Subida acima da base = Laranja/Vermelho)
    if rhr_curr is not None and rhr_mean is not None:
        rhr_diff = rhr_curr - rhr_mean
        rhr_badge_txt = f"{rhr_diff:+.1f} bpm vs base ({rhr_mean:.1f})"
        if rhr_diff <= 0:
            rhr_badge_bg = "rgba(16, 185, 129, 0.2)"   # Verde (Excelente)
            rhr_badge_color = "#34d399"
        elif 0 < rhr_diff <= 2.0:
            rhr_badge_bg = "rgba(249, 115, 22, 0.2)"   # Laranja (Subida ligeira)
            rhr_badge_color = "#fb923c"
        else:
            rhr_badge_bg = "rgba(239, 68, 68, 0.2)"    # Vermelho (Subida acentuada)
            rhr_badge_color = "#f87171"
    else:
        rhr_badge_txt = f"Base: {_fmt(rhr_mean, 1, ' bpm')}" if rhr_mean is not None else f"[{rhr_src}]"
        rhr_badge_bg = "rgba(148, 163, 184, 0.15)"
        rhr_badge_color = "#94a3b8"

    # 3. Sono Score
    sleep_badge_txt = f"Score: {_fmt(sleep_curr, 0)}" if sleep_curr is not None else f"[{sleep_src}]"
    sleep_badge_bg = "rgba(16, 185, 129, 0.2)" if (sleep_curr or 0) >= 75 else "rgba(234, 179, 8, 0.2)"
    sleep_badge_color = "#34d399" if (sleep_curr or 0) >= 75 else "#facc15"

    # 4. Défice de Sono
    if diff_minutes is not None:
        if diff_minutes > 0:
            diff_badge_txt = f"Faltam {int(diff_minutes)} min para a meta"
            diff_badge_bg = "rgba(239, 68, 68, 0.2)"    # Vermelho/Alerta
            diff_badge_color = "#f87171"
        else:
            diff_badge_txt = f"+{abs(int(diff_minutes))} min acima da meta"
            diff_badge_bg = "rgba(16, 185, 129, 0.2)"   # Verde/Excelente
            diff_badge_color = "#34d399"
    else:
        diff_badge_txt = f"Meta Garmin: {_fmt_hours_to_hm(sleep_target_curr)}" if sleep_target_curr else "Meta: 8h"
        diff_badge_bg = "rgba(148, 163, 184, 0.15)"
        diff_badge_color = "#94a3b8"

    # --- RENDERIZAÇÃO DOS CARTÕES ---
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:14px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem;">VRC noturna</span><br>
                <span style="font-size:1.8rem; font-weight:700; color:#e2e8f0;">{_fmt(hrv_curr, 0, ' ms')}</span><br>
                <div style="margin-top:6px; display:inline-block; padding:3px 8px; border-radius:6px; background:{hrv_badge_bg}; color:{hrv_badge_color}; font-size:0.78rem; font-weight:600;">
                    ↑ {escape(hrv_badge_txt)}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c2:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:14px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem;">FC repouso</span><br>
                <span style="font-size:1.8rem; font-weight:700; color:#e2e8f0;">{_fmt(rhr_curr, 0, ' bpm')}</span><br>
                <div style="margin-top:6px; display:inline-block; padding:3px 8px; border-radius:6px; background:{rhr_badge_bg}; color:{rhr_badge_color}; font-size:0.78rem; font-weight:600;">
                    ↑ {escape(rhr_badge_txt)}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c3:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:14px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem;">Sono</span><br>
                <span style="font-size:1.8rem; font-weight:700; color:#e2e8f0;">{_fmt_hours_to_hm(sleep_hours_curr)}</span><br>
                <div style="margin-top:6px; display:inline-block; padding:3px 8px; border-radius:6px; background:{sleep_badge_bg}; color:{sleep_badge_color}; font-size:0.78rem; font-weight:600;">
                    ↑ {escape(sleep_badge_txt)}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with c4:
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:14px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem;">Défice de sono</span><br>
                <span style="font-size:1.8rem; font-weight:700; color:#e2e8f0;">{_fmt_minutes_diff(diff_minutes)}</span><br>
                <div style="margin-top:6px; display:inline-block; padding:3px 8px; border-radius:6px; background:{diff_badge_bg}; color:{diff_badge_color}; font-size:0.78rem; font-weight:600;">
                    ↑ {escape(diff_badge_txt)}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    if garmin_readiness_curr is not None:
        g_score = int(garmin_readiness_curr)
        g_decision = core.decision_for(g_score)
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(g_decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}"><b>{escape(g_decision["headline"])}</b><br>'
            f'<span style="font-size:1.5rem;font-weight:800">Garmin Training Readiness: {g_score}/100</span><br>'
            f'<span class="muted">Métrica oficial sincronizada diretamente da Garmin Connect</span></div>',
            unsafe_allow_html=True,
        )
    elif score is not None:
        tone_class = {"green": "apex-good", "amber": "apex-warn", "red": "apex-alert"}.get(decision["tone"], "")
        st.markdown(
            f'<div class="apex-note {tone_class}"><b>{escape(decision["headline"])}</b><br>'
            f'<span style="font-size:1.5rem;font-weight:800">Prontidão estimada APEX: {score}/100</span><br>'
            f'<span class="muted">Calculada com base na linha de base local</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="apex-note apex-warn"><b>Prontidão não disponível</b><br>'
            'Clica no botão <b>⚡ SYNC DATA</b> no topo para sincronizar os dados mais recentes do teu relógio.</div>',
            unsafe_allow_html=True,
        )

    st.subheader("Interpretação dos sinais")
    st.write(f"**VRC:** {hrv_context['status']}. {hrv_context['explanation']}")
    if sleep_hours_curr is not None:
        dur_str = _fmt_hours_to_hm(sleep_hours_curr)
        tgt_str = _fmt_hours_to_hm(sleep_target_curr) if sleep_target_curr else "8h (padrão)"
        diff_str = _fmt_minutes_diff(diff_minutes)
        st.write(f"Duração do sono da última noite: **{dur_str}** vs Meta recomendada: **{tgt_str}** (Défice/Excedente: **{diff_str}**).")

    st.subheader("Qualidade e origem dos dados")
    st.write(f"Dias válidos de VRC antes de hoje: **{hrv_valid_days}**.")
    source_cols = [("VRC", "hrv_source"), ("FC repouso", "rhr_source"),
                   ("Sono", "sleep_hours_source"), ("Score sono", "sleep_score_source"),
                   ("Prontidão Garmin", "vendor_readiness_source")]
    st.table(pd.DataFrame([{"Métrica": name,
                            "Origem hoje": str(latest.get(col)) if pd.notna(latest.get(col)) else "Sem dado"}
                           for name, col in source_cols]))

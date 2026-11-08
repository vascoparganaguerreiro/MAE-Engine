from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape
from typing import Any, Callable, Dict, Optional

import pandas as pd
import streamlit as st

import services.auth as auth
import data_store as store
from gemini_engine import generate_apex_insights
from ui.pillar_nutrition import render_nutrition_habits_layer
from ui.pillar_recovery import render_pillar_recovery
from ui.pillar_strength import render_pillar_strength
from ui.pillar_training import render_pillar_training


def _fmt(value: Optional[float], digits: int = 1, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.{digits}f}{suffix}"


def _fmt_hours(value: Optional[float]) -> str:
    if value is None or pd.isna(value):
        return "—"
    minutes = round(float(value) * 60)
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def _last_number(frame: pd.DataFrame, column: str) -> Optional[float]:
    """Latest known value across history, used only when labelled as latest recorded."""
    if frame.empty or column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.iloc[-1]) if not values.empty else None


def _today_number(frame: pd.DataFrame, column: str) -> Optional[float]:
    """Today's value only; never relabel an older measurement as today's metric."""
    if frame.empty or column not in frame:
        return None
    value = pd.to_numeric(pd.Series([frame[column].iloc[-1]]), errors="coerce").iloc[0]
    return float(value) if pd.notna(value) else None


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
    training_sessions: Optional[pd.DataFrame] = None,
    sleep_7d_avg: Optional[float] = None,
    lang: str = "PT",
    mode: str = "performance",
    readiness_data: Optional[Dict[str, Any]] = None,
) -> None:
    is_pt = lang.upper().startswith("PT")
    readiness_data = readiness_data or {}
    training_sessions = training_sessions if training_sessions is not None else pd.DataFrame()
    current_user = st.session_state.get("user")
    email = getattr(current_user, "email", "") if current_user else ""
    masked_email = ""
    if email and "@" in email:
        name, domain = email.split("@", 1)
        masked_email = f"{name[:1]}•••@{domain}"
    last_sync = store.get_setting("garmin_last_sync", "Ainda não sincronizado")

    # Premium editorial-style header: more whitespace, ordinary typography, restrained accent.
    st.markdown(
        f"""
        <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:18px;flex-wrap:wrap;
                    padding:8px 0 18px 0;border-bottom:1px solid #35414b;margin-bottom:18px;">
          <div>
            <div style="display:flex;align-items:center;gap:10px;">
              <span style="font-size:1.75rem;color:#c8b28f;line-height:1;">◆</span>
              <span style="font-family:Manrope,sans-serif;font-size:1.65rem;font-weight:800;letter-spacing:-.04em;color:#f1f3f4;">APEX ENGINE</span>
              <span style="border:1px solid #53616a;border-radius:20px;padding:3px 9px;color:#c4cbc9;font-size:.68rem;font-weight:600;">PERSONAL HEALTH</span>
            </div>
            <div style="margin-top:7px;color:#9aa5af;font-size:.78rem;letter-spacing:.06em;">
              PERFORMANCE · RECOVERY · LONGEVITY · {datetime.now(ZoneInfo("Europe/Prague")).date().strftime('%A, %d %B %Y').upper()}
            </div>
          </div>
          <div style="color:#9aa5af;font-size:.78rem;text-align:right;">
            <div>{escape(masked_email) if masked_email else 'Personal dashboard'}</div>
            <div style="margin-top:4px;">{escape(str(last_sync))}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    control_left, control_right = st.columns([3, 1.2])
    with control_left:
        st.caption("A clear view of today's physiology, training response and physical capacity." if not is_pt
                   else "Uma visão integrada da fisiologia, resposta ao treino e capacidade física de hoje.")
    with control_right:
        if st.button("↻  Sync Garmin", use_container_width=True, type="primary"):
            with st.spinner("A sincronizar os dados disponíveis no Garmin Connect…" if is_pt else "Syncing available Garmin Connect data…"):
                sync_callback()
            st.rerun()

    with st.expander("⚙️ Perfil, idioma e ligação Garmin" if is_pt else "⚙️ Profile, language and Garmin connection", expanded=False):
        p1, p2, p3 = st.columns(3)
        with p1:
            new_mode = st.selectbox(
                "Foco principal" if is_pt else "Primary focus",
                options=["performance", "wellness", "longevity"],
                format_func=lambda x: {"performance": "Performance", "wellness": "Health & Wellness", "longevity": "Longevity"}[x],
                index={"performance": 0, "wellness": 1, "longevity": 2}.get(mode, 0),
                key="apex_mode_select",
            )
            if new_mode != mode:
                store.set_setting("mode", new_mode)
                st.rerun()
        with p2:
            language_options = {"Português", "English"}
            selected_lang = st.selectbox("Idioma / Language", ["Português", "English"], index=0 if is_pt else 1)
            store.set_setting("language", "PT" if selected_lang == "Português" else "EN")
        with p3:
            st.write("**Garmin Connect**")
            st.caption("Credenciais lidas dos Secrets quando configuradas; a palavra-passe não é guardada após a tentativa de sincronização." if is_pt else "Credentials are read from Secrets when configured; the password is cleared after a sync attempt.")
        g_email = st.text_input("Garmin email", value=st.session_state.get("garmin_email_input", ""), key="garmin_email_input")
        g_password = st.text_input("Garmin password", type="password", key="garmin_password_input")
        if g_email and g_password:
            st.caption("Credenciais introduzidas nesta sessão; não serão exibidas no ecrã." if is_pt else "Credentials entered for this session; they will not be displayed.")
        if st.session_state.get("garmin_mfa_client_state"):
            st.info("A Garmin pediu um código de verificação. Introduz o código temporário abaixo e carrega em Sync Garmin." if is_pt else "Garmin requested a verification code. Enter the one-time code below, then select Sync Garmin.")
            st.text_input("Código MFA Garmin" if is_pt else "Garmin MFA code", type="password", key="garmin_mfa_code")

    # 00 — Daily decision and the five most useful metrics.
    tabs = st.tabs([
        "00 · Today" if not is_pt else "00 · Hoje",
        "01 · Recovery" if not is_pt else "01 · Recuperação",
        "02 · Performance" if not is_pt else "02 · Performance",
        "03 · Strength & Movement" if not is_pt else "03 · Força & Movimento",
        "04 · Insights & Fuel" if not is_pt else "04 · Insights & Nutrição",
    ])

    with tabs[0]:
        st.markdown("### Today's decision" if not is_pt else "### Decisão de hoje")
        if score is None:
            headline = "Readiness ainda não calculada" if is_pt else "Readiness not yet calculated"
            explanation = (
                "Ainda não existem pelo menos dois sinais com linha de base pessoal suficiente. Consulta os dados e volta a sincronizar após mais dias de registo."
                if is_pt else
                "There are not yet at least two signals with a sufficient personal baseline. Review your data and sync again after more days of recording."
            )
            tone = "#9aa5af"
        else:
            headline = decision.get("headline", "")
            explanation = hrv_context.get("explanation", "")
            tone = {"green": "#a9c0b4", "amber": "#c8b28f", "red": "#b97871"}.get(decision.get("tone"), "#9aa5af")

        readiness_display = f"{score}/100" if score is not None else "—"
        coverage = readiness_data.get("coverage")
        coverage_text = f"{round(float(coverage) * 100)}% dos pesos disponíveis" if coverage is not None else "Cobertura indisponível"
        st.markdown(
            f"""
            <div class="apex-card" style="border-left:4px solid {tone};display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap;">
              <div style="flex:1;min-width:240px;">
                <div class="apex-eyebrow">APEX DAILY DECISION</div>
                <div style="font-family:Manrope,sans-serif;font-size:1.28rem;font-weight:700;margin-top:7px;color:#f1f3f4;">{escape(headline)}</div>
                <div style="font-size:.91rem;color:#c4cbc9;margin-top:7px;line-height:1.5;">{escape(explanation)}</div>
                <div style="font-size:.76rem;color:#9aa5af;margin-top:10px;">{escape(coverage_text)} · {hrv_valid_days} dias válidos de HRV antes de hoje</div>
              </div>
              <div style="text-align:right;min-width:110px;background:#242d35;border:1px solid #3b474f;border-radius:12px;padding:13px 18px;">
                <div style="font-size:.68rem;color:#9aa5af;text-transform:uppercase;letter-spacing:.08em;">Apex Readiness</div>
                <div style="font-family:Manrope,sans-serif;font-size:2.1rem;font-weight:800;color:{tone};line-height:1.25;">{readiness_display}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if garmin_readiness_curr is not None:
            st.caption((f"Garmin Training Readiness: **{garmin_readiness_curr:.0f}/100** · métrica oficial Garmin, separada do cálculo Apex."
                        if is_pt else
                        f"Garmin Training Readiness: **{garmin_readiness_curr:.0f}/100** · Garmin's vendor metric, separate from the Apex calculation."))
        else:
            st.caption("Garmin Training Readiness não foi devolvida para esta data/dispositivo." if is_pt else "Garmin Training Readiness was not returned for this date/device.")

        st.markdown("### Five core metrics" if not is_pt else "### Cinco métricas principais")
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            delta = f"{hrv_curr - hrv_mean:+.1f} ms vs base" if hrv_curr is not None and hrv_mean is not None else None
            st.metric("Nightly HRV" if not is_pt else "VRC noturna", _fmt(hrv_curr, 0, " ms"), delta)
            st.caption("Garmin · last night" if not is_pt else "Garmin · última noite")
        with m2:
            delta = f"{rhr_curr - rhr_mean:+.1f} bpm vs base" if rhr_curr is not None and rhr_mean is not None else None
            st.metric("Resting HR" if not is_pt else "FC repouso", _fmt(rhr_curr, 0, " bpm"), delta)
            st.caption("Garmin Connect" if not is_pt else "Garmin Connect")
        with m3:
            st.metric("Sleep duration" if not is_pt else "Duração do sono", _fmt_hours(sleep_hours_curr),
                      f"{_fmt(sleep_7d_avg, 1, ' h')} 7-day avg" if sleep_7d_avg is not None else None)
            sleep_record_date = base_df["sleep_record_date"].iloc[-1] if "sleep_record_date" in base_df else None
            if sleep_record_date is not None and pd.notna(sleep_record_date):
                sleep_caption = f"Night of {str(sleep_record_date)[:10]}"
            else:
                sleep_caption = "Latest completed night"
            target_caption = f"Target: {_fmt(sleep_target_curr, 1, ' h')}" if sleep_target_curr is not None else ("Target not available" if not is_pt else "Meta não disponível")
            st.caption(f"Garmin · {sleep_caption} · {target_caption}")
        with m4:
            daily_load = _today_number(base_df, "DailyLoad")
            st.metric("Daily training load" if not is_pt else "Carga diária", _fmt(daily_load, 0, " AU"))
            st.caption("Garmin activity load" if daily_load is not None else ("No confirmed load data" if not is_pt else "Sem dados confirmados de carga"))
        with m5:
            st.metric("Garmin Training Readiness" if not is_pt else "Prontidão Garmin",
                      _fmt(garmin_readiness_curr, 0, "/100"))
            st.caption("Garmin-native score" if not is_pt else "Score nativo Garmin")

        st.markdown("### More signals" if not is_pt else "### Outros sinais")
        extra_fields = [
            ("Sleep score", "SleepScore", " /100"),
            ("Body Battery", "body_battery", " /100"),
            ("Stress average", "stress_avg", ""),
            ("Respiration during sleep", "respiration_sleep_avg", " brpm"),
            ("SpO₂ average", "spo2_avg", "%"),
            ("Steps", "steps", ""),
            ("Active calories", "active_calories", " kcal"),
            ("Intensity minutes", "intensity_minutes_moderate", " min moderate"),
            ("Running VO₂max", "vo2max_running", " ml/kg/min"),
            ("Cycling VO₂max", "vo2max_cycling", " ml/kg/min"),
            ("Distance", "distance_m", " m"),
            ("Floors", "floors_ascended", ""),
            ("Total calories", "total_calories", " kcal"),
            ("Moderate intensity", "intensity_minutes_moderate", " min"),
            ("Vigorous intensity", "intensity_minutes_vigorous", " min"),
            ("SpO₂ minimum", "spo2_min", "%"),
            ("Sleep deep", "sleep_deep_minutes", " min"),
            ("Sleep REM", "sleep_rem_minutes", " min"),
            ("Sleep light", "sleep_light_minutes", " min"),
            ("Sleep awake", "sleep_awake_minutes", " min"),
            ("Respiration waking", "respiration_wake_avg", " brpm"),
            ("Body Battery charged", "body_battery_charged", " pts"),
            ("Body Battery drained", "body_battery_drained", " pts"),
            ("HR minimum", "heart_rate_min", " bpm"),
            ("HR maximum", "heart_rate_max", " bpm"),
            ("Readiness sleep factor", "readiness_sleep_score", ""),
            ("Readiness HRV factor", "readiness_hrv_score", ""),
            ("Readiness load factor", "readiness_load_score", ""),
            ("Recovery time", "readiness_recovery_hours", " h"),
        ]
        cols = st.columns(5)
        for index, (label, field, suffix) in enumerate(extra_fields):
            value = _today_number(base_df, field)
            cols[index % 5].metric(label, _fmt(value, 0 if suffix in ("", " /100", " kcal", " min moderate") else 1, suffix))

        sleep_hist = pd.to_numeric(base_df.get("SleepHours", pd.Series(dtype=float)), errors="coerce")
        sleep_28 = sleep_hist.tail(28).dropna()
        avg_28 = float(sleep_28.mean()) if len(sleep_28) >= 7 else None
        avg_row1, avg_row2, avg_row3 = st.columns(3)
        avg_row1.metric("7-night average sleep" if not is_pt else "Média de sono · 7 noites",
                        _fmt_hours(sleep_7d_avg))
        avg_row2.metric("28-day average sleep" if not is_pt else "Média de sono · 28 dias",
                        _fmt_hours(avg_28))
        avg_row3.metric("Valid nights · last 28d" if not is_pt else "Noites válidas · 28 dias",
                        f"{len(sleep_28)}/28")

        with st.expander("All available Garmin metrics / Todas as métricas disponíveis", expanded=False):
            metric_catalogue = [
                ("HRV nightly", "HRV", "ms"), ("HRV weekly average", "hrv_weekly_avg", "ms"),
                ("Resting HR", "RHR", "bpm"), ("7-day average RHR", "rhr_weekly_avg", "bpm"), ("Minimum HR", "heart_rate_min", "bpm"),
                ("Maximum HR", "heart_rate_max", "bpm"), ("Sleep score", "SleepScore", "/100"),
                ("Sleep duration", "SleepHours", "h"), ("Sleep target", "SleepTargetHours", "h"),
                ("Deep sleep", "sleep_deep_minutes", "min"), ("Light sleep", "sleep_light_minutes", "min"),
                ("REM sleep", "sleep_rem_minutes", "min"), ("Awake time", "sleep_awake_minutes", "min"),
                ("Sleep respiration", "respiration_sleep_avg", "brpm"),
                ("Waking respiration", "respiration_wake_avg", "brpm"),
                ("SpO₂ average", "spo2_avg", "%"), ("SpO₂ minimum", "spo2_min", "%"),
                ("Stress average", "stress_avg", ""), ("Stress maximum", "stress_max", ""),
                ("Body Battery", "body_battery", "/100"), ("Body Battery low", "body_battery_low", ""),
                ("Body Battery high", "body_battery_high", ""), ("Body Battery charged", "body_battery_charged", "pts"),
                ("Body Battery drained", "body_battery_drained", "pts"), ("Steps", "steps", ""),
                ("Steps goal", "steps_goal", ""), ("Distance", "distance_m", "m"),
                ("Floors ascended", "floors_ascended", ""), ("Active calories", "active_calories", "kcal"),
                ("Resting calories", "resting_calories", "kcal"), ("Total calories", "total_calories", "kcal"),
                ("Moderate intensity minutes", "intensity_minutes_moderate", "min"),
                ("Vigorous intensity minutes", "intensity_minutes_vigorous", "min"),
                ("Garmin Training Readiness", "GarminReadiness", "/100"),
                ("Running VO₂max", "vo2max_running", "ml/kg/min"),
                ("Cycling VO₂max", "vo2max_cycling", "ml/kg/min"), ("FTP", "ftp_w", "W"),
                ("Lactate threshold HR", "lactate_threshold_hr", "bpm"),
                ("Lactate threshold speed", "lactate_threshold_speed", "m/s"),
                ("Running economy", "running_economy", "Garmin score"),
                ("Endurance score", "endurance_score", ""),
                ("Low aerobic load focus", "low_aerobic_load", "AU"),
                ("High aerobic load focus", "high_aerobic_load", "AU"),
                ("Anaerobic load focus", "anaerobic_load", "AU"),
                ("Acute training load (Garmin)", "acute_training_load", "AU"),
                ("Hydration intake", "hydration_intake_ml", "ml"),
                ("Hydration goal", "hydration_goal_ml", "ml"),
                ("Estimated sweat loss", "sweat_loss_ml", "ml"),
                ("Training status", "training_status", ""),
                ("Training load", "daily_training_load", "AU"),
            ]
            catalogue_rows = []
            for label, field, unit in metric_catalogue:
                value = _today_number(base_df, field)
                catalogue_rows.append({"Metric": label, "Value": _fmt(value, 2), "Unit": unit,
                                       "Status": "Available today" if value is not None else "Not returned / not recorded today"})
            st.dataframe(pd.DataFrame(catalogue_rows), use_container_width=True, hide_index=True)
            if "training_status" in base_df.columns:
                training_status = base_df["training_status"].iloc[-1]
                st.metric("Garmin Training Status", str(training_status) if pd.notna(training_status) else "—")
            st.caption("A missing metric may mean the device/account did not produce it, the API did not return it, or the current sync could not retrieve it. This table does not imply all metrics are available on every Garmin device.")

        with st.expander("Recent Garmin activities" if not is_pt else "Atividades Garmin recentes", expanded=False):
            if not training_sessions.empty:
                display_cols = [c for c in ["date", "activity_name", "sport", "duration_seconds", "distance_m", "training_load", "average_hr", "average_power"] if c in training_sessions.columns]
                st.dataframe(training_sessions.sort_values("date", ascending=False)[display_cols].head(15), use_container_width=True, hide_index=True)
            else:
                st.info("No activity records returned in the selected sync window." if not is_pt else "Sem atividades devolvidas no período sincronizado.")

        with st.expander("Daily check-in" if not is_pt else "Registo subjetivo diário", expanded=False):
            with st.form("apex_daily_checkin"):
                c1, c2, c3 = st.columns(3)
                soreness = c1.slider("Muscle soreness (1–5)" if not is_pt else "Dor muscular (1–5)", 1, 5, 2)
                subjective_stress = c2.slider("Psychological stress (1–5)" if not is_pt else "Stress psicológico (1–5)", 1, 5, 2)
                mood = c3.slider("Mood (1–5)" if not is_pt else "Humor (1–5)", 1, 5, 3)
                fatigue = st.slider("General fatigue (1–5)" if not is_pt else "Fadiga geral (1–5)", 1, 5, 2)
                motivation = st.slider("Motivation to train (1–5)" if not is_pt else "Motivação para treinar (1–5)", 1, 5, 3)
                illness = st.checkbox("Illness symptoms today" if not is_pt else "Sintomas de doença hoje")
                local_pain = st.text_input("Localised pain (optional)" if not is_pt else "Dor localizada (opcional)")
                if st.form_submit_button("Save check-in" if not is_pt else "Guardar registo"):
                    ok = store.upsert_daily_metrics(datetime.now(ZoneInfo("Europe/Prague")).date(), {
                        "soreness": soreness, "stress": subjective_stress, "mood": mood,
                        "fatigue": fatigue, "motivation": motivation,
                        "illness_symptoms": illness, "local_pain": local_pain.strip() or None,
                    }, source="manual")
                    if ok:
                        st.success("Check-in saved." if not is_pt else "Registo guardado.")
                        st.rerun()

        with st.expander("Data quality and measurement availability" if not is_pt else "Qualidade e disponibilidade dos dados"):
            st.write({
                "HRV valid days before today": hrv_valid_days,
                "Apex readiness missing inputs": readiness_data.get("missing", []),
                "Readiness data coverage": readiness_data.get("coverage", 0),
                "Latest Garmin record date": str(base_df["Date"].iloc[-1].date()) if not base_df.empty else "—",
            })

    # 01 — full recovery panel, now actually wired to the dashboard.
    with tabs[1]:
        render_pillar_recovery(
            base_df=base_df, hrv_mean=hrv_mean, rhr_mean=rhr_mean,
            hrv_curr=hrv_curr, rhr_curr=rhr_curr, sleep_curr=sleep_curr,
            sleep_hours_curr=sleep_hours_curr, sleep_target_curr=sleep_target_curr,
            garmin_readiness_curr=garmin_readiness_curr, score=score,
            decision=decision, hrv_context=hrv_context, diff_minutes=diff_minutes,
            hrv_valid_days=hrv_valid_days, lang=lang,
        )

    # 02 — performance panel uses imported daily/activity data.
    with tabs[2]:
        render_pillar_training(base_df=base_df, training_sessions=training_sessions, mode=mode, lang=lang)

    # 03 — movement and strength panel; unknown readiness is explicitly not a full-load cap.
    with tabs[3]:
        render_pillar_strength(base_df=base_df, decision_cap=decision.get("cap", "unknown"),
                               lang=lang, training_sessions=training_sessions)

    # 04 — nutrition and AI are cross-pillar tools, not fake background analytics.
    with tabs[4]:
        render_nutrition_habits_layer(lang=lang)
        st.divider()
        st.markdown("## Apex Intelligence" if not is_pt else "## Apex Intelligence")
        st.caption("AI explains recorded data; it does not create missing measurements or override the deterministic engine." if not is_pt else "A IA explica dados registados; não inventa medições em falta nem substitui o motor determinístico.")
        with st.form("apex_coach_question"):
            user_question = st.text_area(
                "Ask Apex about your training, recovery or nutrition" if not is_pt else "Pergunta ao Apex sobre treino, recuperação ou nutrição",
                placeholder="e.g. How should I adapt tomorrow's threshold session?" if not is_pt else "Ex.: Como devo adaptar o treino de limiar de amanhã?",
                height=90,
            )
            submitted = st.form_submit_button("Generate insight" if not is_pt else "Gerar análise")
        if submitted and user_question.strip():
            summary = {
                "hrv_ms": hrv_curr,
                "hrv_baseline_ms": hrv_mean,
                "rhr_bpm": rhr_curr,
                "rhr_baseline_bpm": rhr_mean,
                "sleep_hours": sleep_hours_curr,
                "sleep_7d_average_hours": sleep_7d_avg,
                "garmin_readiness": garmin_readiness_curr,
                "apex_readiness": score,
                "daily_training_load_au": _last_number(base_df, "DailyLoad"),
                "ctl_au": _last_number(base_df, "CTL"),
                "atl_au": _last_number(base_df, "ATL"),
                "user_question": user_question.strip(),
                "missing_metrics_are_null": True,
            }
            with st.spinner("A preparar a análise…" if is_pt else "Generating the insight…"):
                answer = generate_apex_insights(summary, lang=lang)
            st.markdown("### Apex Coach" if not is_pt else "### Apex Coach")
            st.write(answer)

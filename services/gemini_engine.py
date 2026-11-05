from __future__ import annotations

import os
from typing import Dict, Any
import google.generativeai as genai
import streamlit as st


def generate_apex_insights(metrics_summary: Dict[str, Any], lang: str = "EN") -> str:
    """
    Generates cross-pillar biological coaching using Gemini.
    Enforces deterministic safety: Gemini interprets data, never invents metrics.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)
    
    if not api_key:
        if lang == "PT":
            return (
                "⚠️ Key do Gemini não detetada. Configura `GEMINI_API_KEY` "
                "nos Secrets do Streamlit para ativar a síntese biológica de IA."
            )
        return (
            "⚠️ Gemini API Key not detected. Configure `GEMINI_API_KEY` "
            "in Streamlit Secrets to enable dynamic AI biological synthesis."
        )

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        system_instruction = (
            "You are APEX AI Engine, an elite sports scientist and endurance coach for high-performance athletes. "
            "Your job is to analyze cross-pillar physiological data (HRV, RHR, Sleep, Load, DOMS, Respiration) "
            "and provide concise, actionable, evidence-based biological interpretations. "
            "STRICT RULE: Never invent measurements, never overrule raw data, and never provide medical diagnoses."
        )

        language_context = "Respond strictly in Portuguese (Portugal)." if lang == "PT" else "Respond strictly in English."

        prompt = f"""
        {system_instruction}
        {language_context}

        ATHLETE PHYSIOLOGICAL STATE:
        - Nightly HRV: {metrics_summary.get('hrv')} ms (Z-Score: {metrics_summary.get('z_vrc', 0):+.1f} σ)
        - Resting HR: {metrics_summary.get('rhr')} bpm (Baseline: {metrics_summary.get('rhr_base')} bpm)
        - Sleep Duration: {metrics_summary.get('sleep_hours')} hours (Score: {metrics_summary.get('sleep_score')}/100)
        - Daily Workload (CTL / ATL / TSB): {metrics_summary.get('ctl')} / {metrics_summary.get('atl')} / {metrics_summary.get('tsb')}
        - Subjective Muscle Soreness (DOMS): {metrics_summary.get('soreness')}/5
        - Subjective Fatigue: {metrics_summary.get('fatigue')}/5
        - Garmin Training Readiness: {metrics_summary.get('readiness')}/100

        Deliver a 3-sentence executive analysis:
        1. Autonomic & recovery readiness status.
        2. Adaptative response to acute/chronic load.
        3. Clear recommendation for today's training execution.
        """

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        return f"APEX Intelligence Engine Error: {str(e)}"

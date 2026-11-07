from __future__ import annotations

import os
from typing import Dict, Any
from google import genai
import streamlit as st


def generate_apex_insights(metrics_summary: Dict[str, Any], lang: str = "EN") -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or (st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else None)
    
    if not api_key:
        if lang == "PT":
            return "⚠️ API Key do Gemini não detetada nos Secrets do Streamlit."
        return "⚠️ Gemini API Key not detected in Streamlit Secrets."

    system_instruction = (
        "You are APEX AI Engine, an elite sports scientist and endurance coach for high-performance athletes. "
        "Your job is to analyze cross-pillar physiological data and provide concise, actionable biological interpretations."
    )

    language_context = "Respond strictly in Portuguese (Portugal)." if lang == "PT" else "Respond strictly in English."

    user_question = metrics_summary.get("user_question")
    if user_question:
        prompt = f"{system_instruction}\n{language_context}\n\nATHLETE PHYSIOLOGICAL CONTEXT TODAY:\n- HRV: {metrics_summary.get('hrv')}ms\n- Sleep: {metrics_summary.get('sleep_hours')}h\n- Readiness: {metrics_summary.get('readiness')}/100\n\nATHLETE QUESTION:\n\"{user_question}\""
    else:
        prompt = f"{system_instruction}\n{language_context}\n\nDeliver a 3-sentence executive analysis of the athlete's recovery, load, and training recommendation."

    try:
        client = genai.Client(api_key=api_key)
        
        # Usar os novos códigos de modelo visíveis na tua consola do AI Studio
        models_to_try = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
        last_error = ""

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as sub_e:
                last_error = str(sub_e)
                continue

        return f"APEX Intelligence Engine Error: Todos os modelos falharam. Último erro -> {last_error}"

    except Exception as e:
        return f"APEX Intelligence Engine Error: {str(e)}"

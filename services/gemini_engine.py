from __future__ import annotations

import os
from typing import Dict, Any
import google.generativeai as genai
import streamlit as st


def generate_apex_insights(metrics_summary: Dict[str, Any], lang: str = "EN") -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or (st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else None)
    
    if not api_key:
        return "⚠️ API Key do Gemini não detetada nos Secrets do Streamlit."

    try:
        genai.configure(api_key=api_key)
        
        # Usar o SDK oficial com o modelo universal suportado
        model = genai.GenerativeModel('gemini-1.5-flash')

        system_instruction = (
            "You are APEX AI Engine, an elite sports scientist and endurance coach for high-performance athletes. "
            "Your job is to analyze cross-pillar physiological data and provide concise, actionable biological interpretations."
        )

        language_context = "Respond strictly in Portuguese (Portugal)." if lang == "PT" else "Respond strictly in English."

        user_question = metrics_summary.get("user_question")
        if user_question:
            prompt = f"{system_instruction}\n{language_context}\n\nATHLETE QUESTION: \"{user_question}\""
        else:
            prompt = f"{system_instruction}\n{language_context}\n\nDeliver a 3-sentence executive analysis of the athlete's recovery, load, and training recommendation."

        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        return f"APEX Intelligence Engine Error: {str(e)}"

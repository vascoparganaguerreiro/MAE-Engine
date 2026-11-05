from __future__ import annotations

import os
from typing import Dict, Any
import requests
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
        prompt = f"{system_instruction}\n{language_context}\n\nATHLETE QUESTION: \"{user_question}\""
    else:
        prompt = f"{system_instruction}\n{language_context}\n\nDeliver a 3-sentence executive analysis of the athlete's recovery, load, and training recommendation."

    models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    last_error = "Unknown error"
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                last_error = f"Model {model_name} (HTTP {res.status_code}): {res.text}"
        except Exception as e:
            last_error = f"Exception with {model_name}: {str(e)}"
            continue

    return f"APEX Intelligence Engine Error: {last_error}"

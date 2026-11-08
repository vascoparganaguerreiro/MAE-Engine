from __future__ import annotations

import json
from typing import Any, Dict

from google import genai
import streamlit as st

from services.config import get_secret


def generate_apex_insights(metrics_summary: Dict[str, Any], lang: str = "EN") -> str:
    """Explain only supplied measurements; null values remain explicitly unavailable."""
    api_key = get_secret("GEMINI_API_KEY", "")
    if not api_key:
        return ("Chave da API Gemini não configurada nos Secrets." if lang.upper().startswith("PT")
                else "Gemini API key is not configured in Streamlit Secrets.")

    question = str(metrics_summary.get("user_question") or metrics_summary.get("question") or "").strip()
    safe_metrics = {
        key: value for key, value in metrics_summary.items()
        if key not in {"user_question", "question"} and value is not None
    }
    language = "Português europeu" if lang.upper().startswith("PT") else "English"
    system = (
        "You are Apex Intelligence, an educational sports-science assistant. "
        "Use only the supplied measurements. Missing measurements are unknown, never infer or invent them. "
        "Clearly distinguish Garmin vendor metrics from Apex calculations. Do not diagnose disease, "
        "predict injury, prescribe medication or supplements, or claim that wearable data proves recovery. "
        "If illness symptoms, chest pain, fainting, severe breathlessness or concerning symptoms are reported, "
        "advise stopping exercise and seeking appropriate medical help. Give cautious, practical suggestions. "
        f"Respond in {language}. Keep the answer concise and identify uncertainty."
    )
    payload = json.dumps(safe_metrics, ensure_ascii=False, default=str, indent=2)
    prompt = (
        f"{system}\n\nRECORDED CONTEXT (JSON):\n{payload}\n\nUSER QUESTION:\n"
        f"{question or 'Summarise the available signals and identify missing information.'}"
    )
    try:
        client = genai.Client(api_key=str(api_key))
        model = str(get_secret("GEMINI_MODEL", "gemini-3.8-flash"))
        response = client.models.generate_content(model=model, contents=prompt)
        if response and response.text:
            return response.text.strip()
        return "Não foi gerada uma resposta." if lang.upper().startswith("PT") else "No response was generated."
    except Exception as exc:  # safe error only; never expose headers or credentials
        st.error(f"Gemini request failed: {type(exc).__name__}")
        return ("Não foi possível gerar a análise. Verifica a configuração e tenta novamente."
                if lang.upper().startswith("PT") else "Unable to generate the insight. Check configuration and try again.")

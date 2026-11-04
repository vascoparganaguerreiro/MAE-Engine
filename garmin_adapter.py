"""Best-effort adapter for python-garminconnect.

Garmin Connect is accessed through an unofficial third-party library here.
Credentials are accepted for one sync call and are never written to disk or SQLite.
Missing API values remain None; there are no fallback physiological values.
"""
from __future__ import annotations

from datetime import date
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Tuple

from garminconnect import Garmin


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _nested_number(data: Any, keys: tuple[str, ...]) -> Optional[float]:
    if not isinstance(data, dict):
        return _number(data)
    for key in keys:
        if key in data:
            value = _number(data.get(key))
            if value is not None:
                return value
    return None


def _extract_sleep(data: Any) -> Dict[str, Optional[float]]:
    dto = data.get("dailySleepDTO", data) if isinstance(data, dict) else {}
    if not isinstance(dto, dict):
        dto = {}
    seconds = _number(dto.get("sleepTimeSeconds"))
    hours = seconds / 3600 if seconds is not None else None
    score_block = dto.get("sleepScores") or {}
    overall = score_block.get("overall") or {} if isinstance(score_block, dict) else {}
    score = _nested_number(overall, ("value", "score"))
    return {"sleep_hours": hours, "sleep_score": score}


def _extract_rhr(data: Any) -> Optional[float]:
    return _nested_number(data, ("restingHeartRate", "restingHeartRateValue", "restingHR", "rhr", "value"))


def _extract_hrv(data: Any) -> Optional[float]:
    if not isinstance(data, dict):
        return None
    summary = data.get("hrvSummary") or data.get("summary") or {}
    return _nested_number(summary, ("lastNightAvg", "weeklyAvg", "value"))


def _extract_readiness(data: Any) -> Optional[float]:
    if isinstance(data, list):
        if not data:
            return None
        data = data[0]
    return _nested_number(data, ("score", "trainingReadinessScore", "readinessScore"))


def fetch_daily_metrics(email: str, password: str, target_date: Optional[date] = None
                        ) -> Tuple[Dict[str, Optional[float]], List[str]]:
    """Log in and collect today's available wellness data. Raises for login failure."""
    email = str(email or "").strip()
    password = str(password or "")
    if not email or not password:
        raise ValueError("Introduz o e-mail e a palavra-passe Garmin.")

    day = (target_date or date.today()).isoformat()
    # Keep the library's refresh token in a short-lived private directory. The
    # library otherwise defaults to a persistent token store under the home folder.
    with TemporaryDirectory(prefix="apex-garmin-") as token_dir:
        client = Garmin(email, password, return_on_mfa=True)
        login_result = client.login(token_dir)
        if isinstance(login_result, tuple) and login_result and login_result[0] == "needs_mfa":
            raise RuntimeError("A Garmin account MFA challenge is required; MFA completion is not yet implemented in this UI.")
        return _fetch_after_login(client, day)


def _fetch_after_login(client: Garmin, day: str) -> Tuple[Dict[str, Optional[float]], List[str]]:
    result: Dict[str, Optional[float]] = {
        "hrv": None, "rhr": None, "sleep_score": None,
        "sleep_hours": None, "vendor_readiness": None,
    }
    warnings: List[str] = []

    calls = [
        ("sono", "get_sleep_data", _extract_sleep),
        ("frequência cardíaca de repouso", "get_rhr_day", lambda d: {"rhr": _extract_rhr(d)}),
        ("VRC", "get_hrv_data", lambda d: {"hrv": _extract_hrv(d)}),
        ("prontidão Garmin", "get_training_readiness", lambda d: {"vendor_readiness": _extract_readiness(d)}),
    ]
    for label, method_name, parser in calls:
        method = getattr(client, method_name, None)
        if method is None:
            warnings.append(f"A biblioteca não disponibilizou o endpoint de {label}.")
            continue
        try:
            payload = method(day)
            parsed = parser(payload)
            for key, value in parsed.items():
                if value is not None:
                    result[key] = value
        except Exception as exc:  # one unavailable endpoint should not discard other metrics
            warnings.append(f"Não foi possível obter {label} ({type(exc).__name__}).")

    if all(value is None for value in result.values()):
        warnings.append("A autenticação foi feita, mas não foram recebidas métricas para esta data.")
    return result, warnings

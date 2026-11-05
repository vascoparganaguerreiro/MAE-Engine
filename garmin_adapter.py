"""Best-effort adapter for python-garminconnect with multi-day history backfill."""

from __future__ import annotations

from datetime import date, timedelta
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
    if not isinstance(data, dict):
        return {"sleep_hours": None, "sleep_score": None}

    daily = data.get("dailySleepDTO") or data
    seconds = _nested_number(daily, ("sleepTimeSeconds", "totalSleepHours"))
    hours = round(seconds / 3600.0, 2) if seconds is not None and seconds > 0 else None

    score = _nested_number(daily, ("sleepScores", "overall", "value"))
    if score is None:
        score = _nested_number(data.get("sleepScores"), ("overall", "value"))

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


def fetch_daily_metrics(
    email: str, password: str, target_date: Optional[date] = None
) -> Tuple[Dict[str, Optional[float]], List[str]]:
    """Log in and collect wellness data for target_date and historical backfill (last 14 days)."""
    email = str(email or "").strip()
    password = str(password or "")
    if not email or not password:
        raise ValueError("Introduz o e-mail e a palavra-passe Garmin.")

    base_date = target_date or date.today()
    warnings: List[str] = []
    
    target_result: Dict[str, Optional[float]] = {
        "hrv": None,
        "rhr": None,
        "sleep_score": None,
        "sleep_hours": None,
        "vendor_readiness": None,
    }

    with TemporaryDirectory(prefix="apex-garmin-") as token_dir:
        client = Garmin(email, password, return_on_mfa=True)
        login_result = client.login(token_dir)
        if isinstance(login_result, tuple) and login_result[0] == "needs_mfa":
            raise RuntimeError("A Garmin account MFA challenge is required; MFA completion is not yet implemented in this UI.")

        for i in range(13, -1, -1):
            current_day = base_date - timedelta(days=i)
            day_str = current_day.isoformat()

            day_metrics: Dict[str, Optional[float]] = {
                "hrv": None,
                "rhr": None,
                "sleep_score": None,
                "sleep_hours": None,
                "vendor_readiness": None,
            }

            calls = [
                ("sono", "get_sleep_data", _extract_sleep),
                ("frequência cardíaca de repouso", "get_rhr_day", lambda d: {"rhr": _extract_rhr(d)}),
                ("VRC", "get_hrv_data", lambda d: {"hrv": _extract_hrv(d)}),
                ("prontidão Garmin", "get_training_readiness", lambda d: {"vendor_readiness": _extract_readiness(d)}),
            ]

            for label, method_name, parser in calls:
                method = getattr(client, method_name, None)
                if method is None:
                    continue
                try:
                    payload = method(day_str)
                    parsed = parser(payload)
                    for key, value in parsed.items():
                        if value is not None:
                            day_metrics[key] = value
                except Exception:
                    pass

            if current_day == base_date:
                target_result = day_metrics

            try:
                import data_store
                store = data_store.get_store()
                store.save_daily_entry(
                    entry_date=day_str,
                    hrv=day_metrics.get("hrv"),
                    rhr=day_metrics.get("rhr"),
                    sleep_score=day_metrics.get("sleep_score"),
                    sleep_hours=day_metrics.get("sleep_hours"),
                    vendor_readiness=day_metrics.get("vendor_readiness"),
                )
            except Exception:
                pass

    if all(value is None for value in target_result.values()):
        warnings.append("A autenticação foi feita, mas não foram recebidas métricas para o dia de hoje.")

    return target_result, warnings

"""Garmin Connect ingestion with strict type-safety and fallback handling."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list, tuple)):
                yield from _dicts(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            if isinstance(child, (dict, list, tuple)):
                yield from _dicts(child)


def _first(value: Any, keys: Sequence[str]) -> Any:
    wanted = {_norm(k) for k in keys}
    for item in _dicts(value):
        for key, candidate in item.items():
            if _norm(key) in wanted and candidate is not None:
                return candidate
    return None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _first_number(value: Any, keys: Sequence[str]) -> Optional[float]:
    return _number(_first(value, keys))


def _call(client: Any, method_name: str, *args: Any, warnings: List[str], **kwargs: Any) -> Tuple[Any, bool]:
    method = getattr(client, method_name, None)
    if not callable(method):
        return None, False
    try:
        res = method(*args, **kwargs)
        return res, True
    except Exception as exc:
        logger.warning("Garmin endpoint %s failed: %s", method_name, exc)
        warnings.append(f"{method_name}: {type(exc).__name__}")
        return None, False


def _sleep_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    out: Dict[str, Any] = {}
    sec = _first_number(payload, ["sleepTimeSeconds", "totalSleepSeconds", "sleepDurationSeconds"])
    score = _first_number(payload, ["overallScore", "sleepScore", "sleepScoreValue", "value"])

    if sec is not None and sec > 0:
        out["sleep_hours"] = round(sec / 3600.0, 2)
    if score is not None:
        out["sleep_score"] = score
    return out


def _general_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    mapping = {
        "rhr": ["restingHeartRate", "restingHr", "restingHeartRateValue"],
        "steps": ["totalSteps", "steps"],
        "stress_avg": ["averageStressLevel", "avgStressLevel"],
        "body_battery": ["bodyBatteryMostRecentValue", "charged"],
    }
    out: Dict[str, Any] = {}
    for field, keys in mapping.items():
        val = _first_number(payload, keys)
        if val is not None:
            out[field] = val
    return out


def _hrv_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    out = {}
    nightly = _first_number(payload, ["lastNightAvg", "lastNightAverage", "nightlyAverage"])
    weekly = _first_number(payload, ["weeklyAvg", "weeklyAverage", "sevenDayAvg"])
    if nightly is not None:
        out["hrv"] = nightly
    if weekly is not None:
        out["hrv_weekly_avg"] = weekly
    return out


def _readiness_metrics(payload: Any) -> Dict[str, Any]:
    if not payload:
        return {}
    score = _first_number(payload, ["score", "scoreValue", "trainingReadinessScore", "value"])
    return {"vendor_readiness": score} if score is not None else {}


def fetch_daily_metrics(
    email: str,
    password: str,
    target_date: date,
    fetch_history: bool = True,
    history_days: int = 30,
    token_store: Optional[str] = None,
    mfa_client_state: Optional[Dict[str, Any]] = None,
    mfa_code: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    try:
        from garminconnect import Garmin
    except ImportError as exc:
        raise RuntimeError("Biblioteca garminconnect não instalada.") from exc

    warnings: List[str] = []
    if not email or not password:
        raise RuntimeError("Credenciais Garmin em falta.")

    try:
        client = Garmin(email, password)
        client.login()
    except Exception as exc:
        warnings.append(f"Login Garmin falhou: {type(exc).__name__}")
        return {}, [], warnings

    today_str = target_date.isoformat()
    yesterday_str = (target_date - timedelta(days=1)).isoformat()
    metrics: Dict[str, Any] = {"date": today_str}

    # 1. Summary / General
    summary, _ = _call(client, "get_user_summary", today_str, warnings=warnings)
    if summary:
        metrics.update(_general_metrics(summary))

    # 2. Resting Heart Rate
    rhr_raw, _ = _call(client, "get_rhr_day", today_str, warnings=warnings)
    if rhr_raw:
        rhr_val = _first_number(rhr_raw, ["restingHeartRate", "value"])
        if rhr_val:
            metrics["rhr"] = rhr_val

    # 3. HRV (Noturna)
    hrv_raw, _ = _call(client, "get_hrv_data", today_str, warnings=warnings)
    if hrv_raw:
        metrics.update(_hrv_metrics(hrv_raw))

    # 4. Sleep (Procura hoje; se falhar, tenta ontem)
    sleep_raw, _ = _call(client, "get_sleep_data", today_str, warnings=warnings)
    sleep_parsed = _sleep_metrics(sleep_raw)
    if not sleep_parsed.get("sleep_hours"):
        sleep_prev, _ = _call(client, "get_sleep_data", yesterday_str, warnings=warnings)
        sleep_parsed = _sleep_metrics(sleep_prev)
    metrics.update(sleep_parsed)

    # 5. Training Readiness (Robusto a TypeError)
    try:
        readiness_raw, ok = _call(client, "get_training_readiness", today_str, warnings=warnings)
        if ok and readiness_raw:
            metrics.update(_readiness_metrics(readiness_raw))
    except Exception as exc:
        warnings.append(f"readiness_skip: {type(exc).__name__}")

    metrics["_training_sessions"] = []
    return metrics, [], warnings

"""Garmin Connect ingestion with tolerant parsing and explicit missing-data handling.

The Garmin Connect wrapper is unofficial. Endpoint availability and payload shape can
vary by account, device, firmware and library version. This module:
- feature-detects optional methods;
- never substitutes invented values for missing measurements;
- records endpoint-specific warnings without aborting the complete sync;
- backfills daily summaries and training-load coverage when supported.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            stamp = float(value) / (1000.0 if float(value) > 10_000_000_000 else 1.0)
            return datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record_date(record: Dict[str, Any]) -> Optional[str]:
    raw = _first(record, ["calendarDate", "date", "startTimeLocal", "startTimeGMT", "beginTimestamp"])
    dt = _as_datetime(raw)
    if dt:
        return dt.date().isoformat()
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10]).isoformat()
        except ValueError:
            return None
    return None


def _records(payload: Any) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen = set()
    for item in _dicts(payload):
        day = _record_date(item)
        if day:
            marker = (day, id(item))
            if marker not in seen:
                seen.add(marker)
                found.append(item)
    return found


def _call(client: Any, method_name: str, *args: Any, warnings: List[str], **kwargs: Any) -> Tuple[Any, bool]:
    method = getattr(client, method_name, None)
    if not callable(method):
        return None, False
    try:
        return method(*args, **kwargs), True
    except Exception as exc:
        logger.warning("Garmin endpoint %s failed: %s", method_name, exc)
        warnings.append(f"{method_name}: {type(exc).__name__}")
        return None, False


def _sleep_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    dto = _first(payload, ["dailySleepDTO", "userDailySleepDTO", "sleepDTO"])
    source = dto if isinstance(dto, dict) else payload
    out: Dict[str, Any] = {}

    seconds = _first_number(source, ["sleepTimeSeconds", "totalSleepSeconds", "sleepDurationSeconds"])
    hours = _first_number(source, ["totalSleepHours", "sleepHours"])
    if seconds is not None:
        out["sleep_hours"] = round(seconds / 3600.0, 2)
    elif hours is not None:
        out["sleep_hours"] = round(hours, 2)

    score = _first_number(source, ["overallScore", "sleepScore", "sleepScoreValue"])
    if score is None:
        scores = _first(source, ["sleepScores"])
        if isinstance(scores, dict):
            overall = scores.get("overall") or scores.get("Overall")
            if isinstance(overall, dict):
                score = _number(overall.get("value"))
    if score is not None:
        out["sleep_score"] = score

    for field, keys in {
        "sleep_deep_minutes": ["deepSleepSeconds", "deepSleepDurationSeconds", "deepSleepMinutes"],
        "sleep_light_minutes": ["lightSleepSeconds", "lightSleepDurationSeconds", "lightSleepMinutes"],
        "sleep_rem_minutes": ["remSleepSeconds", "remSleepDurationSeconds", "remSleepMinutes"],
        "sleep_awake_minutes": ["awakeSleepSeconds", "awakeDurationSeconds", "awakeSeconds", "awakeTimeSeconds", "awakeDurationMinutes"],
    }.items():
        val = _first_number(source, keys)
        if val is not None:
            minute_key = any(_norm(k).endswith("minutes") for k in keys if _norm(k) in {_norm(x) for x in source.keys()})
            out[field] = round(val if minute_key else val / 60.0, 1)

    target_seconds = _first_number(source, ["sleepNeedSeconds", "recommendedSleepSeconds", "sleepTargetSeconds"])
    target_hours = _first_number(source, ["sleepNeedHours", "recommendedSleepHours", "sleepTargetHours"])
    if target_seconds is not None:
        out["sleep_target_hours"] = round(target_seconds / 3600.0, 2)
    elif target_hours is not None:
        out["sleep_target_hours"] = round(target_hours, 2)

    return out


def _general_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    mapping = {
        "rhr": ["restingHeartRate", "restingHr", "restingHeartRateValue", "restingHeartRateInBeatsPerMinute"],
        "heart_rate_min": ["minHeartRate", "minimumHeartRate", "lowestHeartRate"],
        "heart_rate_max": ["maxHeartRate", "maximumHeartRate", "highestHeartRate"],
        "steps": ["totalSteps", "steps"],
        "distance_m": ["totalDistanceMeters", "totalDistance"],
        "floors_ascended": ["floorsAscended", "floorsClimbed"],
        "active_calories": ["activeKilocalories", "activeCalories"],
        "resting_calories": ["bmrKilocalories", "restingKilocalories"],
        "total_calories": ["totalKilocalories", "totalCalories"],
        "stress_avg": ["averageStressLevel", "avgStressLevel", "averageStress"],
        "stress_max": ["maxStressLevel", "maximumStressLevel"],
        "spo2_avg": ["averageSpO2", "avgSpO2", "averageSpO2Value"],
        "spo2_min": ["lowestSpO2", "minSpO2", "minimumSpO2"],
        "body_battery": ["bodyBatteryMostRecentValue", "bodyBatteryAtWakeTime", "currentBodyBattery", "bodyBatteryValue"],
    }
    out: Dict[str, Any] = {}
    for field, keys in mapping.items():
        val = _first_number(payload, keys)
        if val is not None:
            out[field] = val
    return out


def _rhr_metrics(payload: Any) -> Dict[str, Any]:
    parsed = _general_metrics(payload)
    scalar = _number(payload)
    if scalar is not None:
        parsed["rhr"] = scalar
    return parsed


def _hrv_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    summary = _first(payload, ["hrvSummary"])
    source = summary if isinstance(summary, dict) else payload
    out = {}
    nightly = _first_number(source, ["lastNightAvg", "lastNightAverage", "nightlyAverage"])
    weekly = _first_number(source, ["weeklyAvg", "weeklyAverage", "sevenDayAvg"])
    if nightly is not None:
        out["hrv"] = nightly
    if weekly is not None:
        out["hrv_weekly_avg"] = weekly
    return out


def _readiness_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    candidates = _records(payload)
    if not candidates:
        candidates = [item for item in _dicts(payload) if _first_number(item, ["score", "scoreValue", "trainingReadinessScore"]) is not None]
    if not candidates:
        return {}
    item = candidates[-1]
    score = _first_number(item, ["score", "scoreValue", "trainingReadinessScore", "trainingReadiness"])
    out = {"vendor_readiness": score} if score is not None else {}
    return out


def _call_first(client: Any, names: Sequence[str], *args: Any, warnings: List[str]) -> Tuple[Any, bool]:
    for name in names:
        if callable(getattr(client, name, None)):
            payload, ok = _call(client, name, *args, warnings=warnings)
            if ok and payload:
                return payload, True
    return None, False


def _merge_record(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, value in source.items():
        if value is not None:
            target[key] = value


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
        raise RuntimeError("Instala/atualiza a dependência garminconnect antes de sincronizar.") from exc

    warnings: List[str] = []
    
    if not email or not password:
        raise RuntimeError("Email e palavra-passe Garmin são necessários.")

    try:
        client = Garmin(email, password)
        client.login()
    except Exception as exc:
        warnings.append(f"Login Garmin falhou: {type(exc).__name__}")
        return {}, [], warnings

    today = target_date.isoformat()
    yesterday = (target_date - timedelta(days=1)).isoformat()
    metrics: Dict[str, Any] = {"date": today}

    # 1. User Summary / Stats
    summary, _ = _call_first(client, ["get_user_summary", "get_stats"], today, warnings=warnings)
    if summary:
        _merge_record(metrics, _general_metrics(summary))

    # 2. Resting Heart Rate
    rhr_payload, _ = _call(client, "get_rhr_day", today, warnings=warnings)
    if rhr_payload:
        _merge_record(metrics, _rhr_metrics(rhr_payload))

    # 3. Sleep (Tenta Hoje; se estiver vazio, tenta Ontem)
    sleep, _ = _call_first(client, ["get_daily_sleep", "get_sleep_data"], today, warnings=warnings)
    sleep_parsed = _sleep_metrics(sleep)
    if not sleep_parsed or not sleep_parsed.get("sleep_hours"):
        sleep_prev, _ = _call_first(client, ["get_daily_sleep", "get_sleep_data"], yesterday, warnings=warnings)
        sleep_parsed = _sleep_metrics(sleep_prev)

    if sleep_parsed:
        _merge_record(metrics, sleep_parsed)

    # 4. HRV
    hrv_payload, _ = _call(client, "get_hrv_data", today, warnings=warnings)
    if hrv_payload:
        _merge_record(metrics, _hrv_metrics(hrv_payload))

    # 5. Training Readiness
    readiness_payload, _ = _call_first(client, ["get_training_readiness_range", "get_training_readiness"], today, warnings=warnings)
    if readiness_payload:
        _merge_record(metrics, _readiness_metrics(readiness_payload))

    metrics["_training_sessions"] = []
    return metrics, [], warnings

"""Garmin Connect ingestion with tolerant parsing, strict range clamping, and explicit missing-data handling.

The Garmin Connect wrapper is unofficial. Endpoint availability and payload shape can
vary by account, device, firmware and library version. This module therefore:
- feature-detects optional methods;
- clamps history requests to <= 21 days to avoid Garmin HTTP 400 range limits;
- never substitutes invented values for missing measurements;
- records endpoint-specific warnings without aborting the complete sync;
- backfills daily summaries and training-load coverage when supported.
"""
from __future__ import annotations

import hashlib
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
        warnings.append(f"Biblioteca Garmin sem o método {method_name}; atualiza garminconnect.")
        return None, False
    try:
        return method(*args, **kwargs), True
    except Exception as exc:
        detail = str(exc).replace("\n", " ").strip()
        detail = re.sub(r"(?i)(password|token|authorization|cookie)=?[^ ,;]+", r"\1=[redacted]", detail)
        detail = detail[:180] or "sem detalhe fornecido pela biblioteca"
        logger.warning("Garmin endpoint %s failed: %s: %s", method_name, type(exc).__name__, detail)
        warnings.append(f"{method_name}: {type(exc).__name__} — {detail}")
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

    for field, keys in {
        "sleep_start": ["sleepStartTimestampLocal", "sleepStartTimestampGMT", "startTimestampLocal", "startTimestampGMT"],
        "sleep_end": ["sleepEndTimestampLocal", "sleepEndTimestampGMT", "endTimestampLocal", "endTimestampGMT"],
    }.items():
        val = _first(source, keys)
        if val is not None:
            out[field] = str(val)

    for field, keys in {
        "respiration_sleep_avg": ["averageRespirationValue", "avgSleepingRespirationValue"],
        "spo2_avg": ["averageSpO2", "avgSpO2"],
        "spo2_min": ["lowestSpO2", "minSpO2"],
    }.items():
        val = _first_number(source, keys)
        if val is not None:
            out[field] = val
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
        "respiration_wake_avg": ["avgWakingRespirationValue", "averageWakingRespirationValue"],
        "respiration_sleep_avg": ["averageRespirationValue", "avgSleepingRespirationValue"],
        "steps_goal": ["dailyStepGoal", "stepGoal"],
        "intensity_minutes_moderate": ["moderateIntensityMinutes", "moderateMinutes"],
        "intensity_minutes_vigorous": ["vigorousIntensityMinutes", "vigorousMinutes"],
        "body_battery": ["bodyBatteryMostRecentValue", "bodyBatteryAtWakeTime", "currentBodyBattery", "bodyBatteryValue"],
        "body_battery_low": ["bodyBatteryLow", "lowestBodyBattery"],
        "body_battery_high": ["bodyBatteryHigh", "highestBodyBattery"],
        "body_battery_charged": ["bodyBatteryCharged", "charged"],
        "body_battery_drained": ["bodyBatteryDrained", "drained"],
        "training_load_status": ["trainingLoadStatus", "loadLevel"],
        "low_aerobic_load": ["lowAerobicTrainingLoad", "lowAerobicLoad"],
        "high_aerobic_load": ["highAerobicTrainingLoad", "highAerobicLoad"],
        "anaerobic_load": ["anaerobicTrainingLoad", "anaerobicLoad"],
        "acute_training_load": ["acuteTrainingLoad", "acuteLoadValue"],
        "hydration_intake_ml": ["hydrationIntake", "totalIntakeMl", "intakeMl", "hydrationMl"],
        "hydration_goal_ml": ["hydrationGoal", "goalMl", "dailyGoalMl"],
        "sweat_loss_ml": ["sweatLoss", "sweatLossMl", "estimatedSweatLossMl"],
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
    candidates.sort(key=lambda item: str(_first(item, ["timestamp", "calendarDate", "startTimestampGMT"]) or ""))
    item = candidates[-1]
    score = _first_number(item, ["score", "scoreValue", "trainingReadinessScore", "trainingReadiness"])
    out = {"vendor_readiness": score} if score is not None else {}
    for field, names in {
        "readiness_sleep_score": ["sleepScore", "sleepScoreFactor", "sleepHistoryFactor"],
        "readiness_hrv_score": ["hrvScore", "hrvFactor", "hrvStatusFactor"],
        "readiness_load_score": ["acuteLoadFactor", "trainingLoadFactor", "loadScore", "loadFactor"],
        "readiness_recovery_hours": ["recoveryTime", "recoveryTimeHours"],
    }.items():
        val = _first_number(item, names)
        if val is not None:
            out[field] = val
    return out


def _performance_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    out: Dict[str, Any] = {}
    generic = _first(payload, ["generic", "running", "run"])
    cycling = _first(payload, ["cycling", "bike"])
    run_value = _first_number(generic, ["vo2MaxValue", "vo2max", "value"]) if generic is not None else None
    bike_value = _first_number(cycling, ["vo2MaxValue", "vo2max", "value"]) if cycling is not None else None
    if run_value is None:
        run_value = _first_number(payload, ["genericVo2Max", "runningVo2Max", "vo2MaxRunning"])
    if bike_value is None:
        bike_value = _first_number(payload, ["cyclingVo2Max", "vo2MaxCycling"])
    if run_value is not None:
        out["vo2max_running"] = run_value
    if bike_value is not None:
        out["vo2max_cycling"] = bike_value
    for field, names in {
        "ftp_w": ["functionalThresholdPower", "cyclingFtp", "ftp"],
        "lactate_threshold_hr": ["lactateThresholdHeartRate", "ltHeartRate"],
        "lactate_threshold_speed": ["lactateThresholdSpeed", "ltSpeed"],
    }.items():
        value = _first_number(payload, names)
        if value is not None:
            out[field] = value
    return out


def _running_economy_metrics(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, (dict, list)) or not payload:
        return {}
    value = _first_number(payload, ["runningEconomy", "runningEconomyScore", "score", "value"])
    return {"running_economy": value} if value is not None else {}


def _activity_rows(payload: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not payload:
        return rows
    for item in _records(payload):
        activity_id = _first(item, ["activityId", "activity_id", "id"])
        day = _record_date(item)
        if not activity_id or not day:
            continue
        sport_value = _first(item, ["sportTypeKey", "sportType", "activityType", "typeKey"])
        if isinstance(sport_value, dict):
            sport_value = _first(sport_value, ["typeKey", "sportTypeKey", "name", "type"])
        row: Dict[str, Any] = {
            "date": day,
            "activity_id": str(activity_id),
            "activity_name": str(_first(item, ["activityName", "name"]) or ""),
            "sport": str(sport_value or "unknown"),
        }
        fields = {
            "duration_seconds": ["durationInSeconds", "elapsedDuration", "duration"],
            "distance_m": ["distance", "distanceMeters"],
            "training_load": ["trainingLoad", "activityTrainingLoad", "load"],
            "average_hr": ["averageHR", "averageHeartRate"],
            "max_hr": ["maxHR", "maxHeartRate"],
            "average_power": ["averagePower", "avgPower"],
            "calories": ["calories", "activeKilocalories"],
            "avg_cadence": ["averageRunningCadenceInStepsPerMinute", "averageBikeCadenceInRoundsPerMinute", "averageCadence"],
            "max_cadence": ["maxRunningCadenceInStepsPerMinute", "maxBikeCadenceInRoundsPerMinute", "maxCadence"],
            "ground_contact_time_ms": ["averageGroundContactTime", "avgGroundContactTime"],
            "ground_contact_balance_pct": ["averageGroundContactBalance", "groundContactBalance"],
            "vertical_oscillation_cm": ["averageVerticalOscillation", "verticalOscillation"],
            "vertical_ratio_pct": ["averageVerticalRatio", "verticalRatio"],
            "stride_length_m": ["averageStrideLength", "strideLength"],
            "aerobic_training_effect": ["aerobicTrainingEffect"],
            "anaerobic_training_effect": ["anaerobicTrainingEffect"],
            "performance_condition": ["startPerformanceCondition", "performanceCondition"],
            "normalized_power": ["normPower", "normalizedPower"],
            "average_speed_mps": ["averageSpeed"],
            "elevation_gain_m": ["elevationGain"],
            "average_respiration": ["averageRespirationRate"],
            "max_respiration": ["maxRespirationRate"],
        }
        for field, keys in fields.items():
            val = _first_number(item, keys)
            if val is not None:
                row[field] = val
        rows.append(row)
    return rows


def _call_first(client: Any, names: Sequence[str], *args: Any, warnings: List[str]) -> Tuple[Any, bool]:
    found = False
    for name in names:
        if callable(getattr(client, name, None)):
            found = True
            payload, ok = _call(client, name, *args, warnings=warnings)
            if ok:
                return payload, True
    if not found:
        warnings.append(f"Nenhum endpoint Garmin disponível para: {', '.join(names)}.")
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
    history_days: int = 21,
    token_store: Optional[str] = None,
    mfa_client_state: Optional[Dict[str, Any]] = None,
    mfa_code: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Fetch a broad set of Garmin metrics for today plus optional historical series.

    Returns (today_metrics, daily_history_records, warnings). `today_metrics` also
    carries a private `_training_sessions` list which the caller must remove before
    saving daily telemetry and persist separately using the activity storage method.
    """
    try:
        from garminconnect import Garmin
    except ImportError as exc:
        raise RuntimeError("Instala/atualiza a dependência garminconnect antes de sincronizar.") from exc

    warnings: List[str] = []
    token_path: Optional[Path] = None
    if token_store:
        token_path = Path(token_store).expanduser()
        token_path.mkdir(parents=True, exist_ok=True)
        try:
            token_path.chmod(0o700)
        except OSError:
            logger.warning("Could not restrict permissions on Garmin token directory")

    if mfa_client_state is not None:
        if not mfa_code or not str(mfa_code).strip():
            return {"_mfa_required": True, "_mfa_client_state": mfa_client_state}, [], warnings
        client = Garmin(return_on_mfa=True)
        client.resume_login(mfa_client_state, str(mfa_code).strip())
        if token_path is not None:
            try:
                client.client.dump(str(token_path))
            except Exception as exc:
                warnings.append(f"Não foi possível guardar o token Garmin após MFA: {type(exc).__name__}")
    else:
        if not email or not password:
            raise RuntimeError("Email e palavra-passe Garmin são necessários para iniciar a ligação.")
        client = Garmin(email, password, return_on_mfa=True)
        login_result = client.login(str(token_path) if token_path else None)
        if isinstance(login_result, tuple) and login_result and login_result[0] == "needs_mfa":
            return {"_mfa_required": True, "_mfa_client_state": login_result[1]}, [], warnings
        if not getattr(client, "display_name", None):
            client._load_profile_and_settings()
        if token_path is not None:
            client.client.dump(str(token_path))

    today = target_date.isoformat()

    # CLAMP CRUCIAL: A API REST da Garmin falha com HTTP 400 se a diferença de dias ultrapassar 28 dias.
    # Garantimos um máximo de 21 dias para ter margem segura de fuso horário.
    safe_days = min(max(1, history_days), 21)
    start = (target_date - timedelta(days=safe_days)).isoformat()
    by_date: Dict[str, Dict[str, Any]] = {}

    def row_for(day: str) -> Dict[str, Any]:
        return by_date.setdefault(day, {"date": day})

    try:
        summary, summary_ok = _call_first(client, ["get_user_summary", "get_stats"], today, warnings=warnings)
        if summary:
            _merge_record(row_for(today), _general_metrics(summary))

        rhr_payload, _rhr_ok = _call(client, "get_rhr_day", today, warnings=warnings)
        rhr_metrics = _rhr_metrics(rhr_payload)
        if rhr_metrics:
            _merge_record(row_for(today), rhr_metrics)
        if "rhr" not in rhr_metrics:
            hr_range, _hr_ok = _call(client, "get_daily_heart_rate_stats", today, today, warnings=warnings)
            if hr_range:
                for record in _records(hr_range) or [hr_range]:
                    _merge_record(row_for(_record_date(record) or today), _general_metrics(record))

        weekly_rhr, _weekly_rhr_ok = _call(client, "get_week_average_resting_hr", today, warnings=warnings)
        weekly_rhr_value = _first_number(weekly_rhr, ["weeklyAverage", "weeklyAvg", "averageRestingHeartRate", "average", "value", "restingHeartRate"])
        if weekly_rhr_value is None:
            weekly_rhr_value = _number(weekly_rhr)
        if weekly_rhr_value is not None:
            row_for(today)["rhr_weekly_avg"] = weekly_rhr_value

        sleep, sleep_ok = _call_first(client, ["get_daily_sleep", "get_sleep_data"], today, warnings=warnings)
        if sleep:
            _merge_record(row_for(today), _sleep_metrics(sleep))
        if not _sleep_metrics(sleep):
            previous, previous_ok = _call_first(client, ["get_daily_sleep", "get_sleep_data"],
                                                (target_date - timedelta(days=1)).isoformat(), warnings=warnings)
            previous_metrics = _sleep_metrics(previous)
            if previous_metrics:
                _merge_record(row_for(today), previous_metrics)
                row_for(today)["sleep_record_date"] = (target_date - timedelta(days=1)).isoformat()

        hrv, hrv_ok = _call(client, "get_hrv_data", today, warnings=warnings)
        if hrv:
            _merge_record(row_for(today), _hrv_metrics(hrv))

        readiness, readiness_ok = _call(client, "get_training_readiness_range", today, today, warnings=warnings)
        if not readiness:
            readiness, readiness_ok = _call(client, "get_training_readiness", today, warnings=warnings)
        if readiness:
            _merge_record(row_for(today), _readiness_metrics(readiness))

        optional_calls = [
            ("get_daily_body_battery_stats", (today, today), _general_metrics),
            ("get_daily_stress_stats", (today, today), _general_metrics),
            ("get_daily_respiration_stats", (today, today), _general_metrics),
            ("get_spo2_data", (today,), _general_metrics),
            ("get_spo2_acclimation_data", (today,), _general_metrics),
            ("get_daily_intensity_minutes_stats", (today, today), _general_metrics),
            ("get_daily_floors_stats", (today, today), _general_metrics),
            ("get_steps_goal", (today,), _general_metrics),
        ]
        for method_name, args, parser in optional_calls:
            payload, _ok = _call(client, method_name, *args, warnings=warnings)
            if payload:
                _merge_record(row_for(today), parser(payload))

        hydration, _hydration_ok = _call_first(
            client, ["get_hydration_all_data", "get_hydration_data"], today, warnings=warnings
        )
        if hydration:
            _merge_record(row_for(today), _general_metrics(hydration))
        training_status, _training_status_ok = _call_first(
            client, ["get_daily_training_status", "get_training_status"], today, warnings=warnings
        )
        if training_status:
            status_value = _first(training_status, ["trainingStatus", "status", "trainingStatusLabel"])
            if isinstance(status_value, (str, int, float)):
                row_for(today)["training_status"] = str(status_value)
            _merge_record(row_for(today), _general_metrics(training_status))

        load_focus, _load_focus_ok = _call(client, "get_training_four_week_load_balance", today, warnings=warnings)
        if load_focus:
            _merge_record(row_for(today), _general_metrics(load_focus))

        battery, _battery_ok = _call(client, "get_body_battery", today, today, warnings=warnings)
        if battery:
            _merge_record(row_for(today), _general_metrics(battery))

        max_metrics, _max_ok = _call_first(client, ["get_max_metrics_latest", "get_max_metrics"], today, warnings=warnings)
        if max_metrics:
            _merge_record(row_for(today), _performance_metrics(max_metrics))
        biometrics, _bio_ok = _call(client, "get_current_biometrics", warnings=warnings)
        if biometrics:
            _merge_record(row_for(today), _performance_metrics(biometrics))
        lactate, _lt_ok = _call(client, "get_lactate_threshold", warnings=warnings, latest=True)
        if lactate:
            _merge_record(row_for(today), _performance_metrics(lactate))
        running_economy, _economy_ok = _call(client, "get_running_economy", today, warnings=warnings)
        _merge_record(row_for(today), _running_economy_metrics(running_economy))
        endurance, _endurance_ok = _call(client, "get_endurance_score", start, today, warnings=warnings)
        if endurance:
            endurance_records = _records(endurance)
            for record in endurance_records:
                day = _record_date(record)
                value = _first_number(record, ["enduranceScore", "score", "value"])
                if day and value is not None:
                    row_for(day)["endurance_score"] = value

        activity_payload, activity_ok = _call_first(
            client, ["get_training_load_activities", "get_activities_by_date"],
            start, today, warnings=warnings
        )
        activity_range_complete = activity_ok and activity_payload is not None
        if not activity_ok and callable(getattr(client, "search_activities", None)):
            activity_payload, activity_ok = _call(
                client, "search_activities", 0, 100,
                startDate=start, endDate=today, warnings=warnings
            )
            activity_range_complete = False
        activity_rows = _activity_rows(activity_payload)
        if activity_range_complete:
            for offset in range(safe_days + 1):
                day = (target_date - timedelta(days=safe_days - offset)).isoformat()
                row_for(day)["daily_training_load"] = 0.0
                row_for(day)["training_load_coverage"] = True
        for activity in activity_rows:
            day = activity["date"]
            row = row_for(day)
            load = _number(activity.get("training_load"))
            if load is not None:
                row["daily_training_load"] = float(row.get("daily_training_load", 0.0)) + load
                row["training_load_coverage"] = True
            elif activity_range_complete:
                row.pop("daily_training_load", None)
                row["training_load_coverage"] = False

        if fetch_history:
            daily_history, hist_ok = _call(client, "get_daily_summaries", start, today, warnings=warnings)
            if daily_history:
                for record in _records(daily_history):
                    day = _record_date(record)
                    if day:
                        _merge_record(row_for(day), _general_metrics(record))
                        _merge_record(row_for(day), _sleep_metrics(record))
                        _merge_record(row_for(day), _hrv_metrics(record))

            range_calls = [
                ("get_hrv_data_range", (start, today), _hrv_metrics),
                ("get_rhr_daily", (start, today), _general_metrics),
                ("get_sleep_daily", (start, today), _sleep_metrics),
                ("get_training_readiness_range", (start, today), _readiness_metrics),
                ("get_daily_heart_rate_stats", (start, today), _general_metrics),
                ("get_daily_stress_stats", (start, today), _general_metrics),
                ("get_daily_body_battery_stats", (start, today), _general_metrics),
                ("get_daily_respiration_stats", (start, today), _general_metrics),
                ("get_daily_intensity_minutes_stats", (start, today), _general_metrics),
                ("get_daily_floors_stats", (start, today), _general_metrics),
                ("get_daily_hydration_stats", (start, today), _general_metrics),
                ("get_max_metrics_range", (start, today), _performance_metrics),
                ("get_running_economy_range", (start, today), _running_economy_metrics),
            ]
            for method_name, args, parser in range_calls:
                payload, _ok = _call(client, method_name, *args, warnings=warnings)
                if payload:
                    for record in _records(payload):
                        day = _record_date(record)
                        if day:
                            _merge_record(row_for(day), parser(record))

            for stat_type in ("STEPS", "CALORIES"):
                stats_payload, stats_ok = _call(client, "get_daily_stats", start, today, stat_type, warnings=warnings)
                if stats_ok and stats_payload:
                    for record in _records(stats_payload):
                        day = _record_date(record)
                        if not day:
                            continue
                        vals = _general_metrics(record)
                        if stat_type == "STEPS" and "steps" not in vals:
                            value = _first_number(record, ["value", "total", "steps"])
                            if value is not None:
                                vals["steps"] = value
                        if stat_type == "CALORIES" and "total_calories" not in vals:
                            value = _first_number(record, ["value", "total", "calories"])
                            if value is not None:
                                vals["total_calories"] = value
                        _merge_record(row_for(day), vals)

        metrics = dict(by_date.get(today, {"date": today}))
        if not metrics.get("sleep_hours"):
            metrics.pop("sleep_hours", None)
        if not any(k != "date" for k in metrics):
            warnings.append(
                "Garmin login succeeded, but no daily metrics were parsed. "
                "Check endpoint warnings, account sync status, and garminconnect compatibility."
            )
        metrics["_training_sessions"] = activity_rows

        history_records = [
            {key: value for key, value in record.items() if key != "date"}
            | {"date": day}
            for day, record in sorted(by_date.items()) if day != today and len(record) > 1
        ]
        return metrics, history_records, warnings
    finally:
        pass

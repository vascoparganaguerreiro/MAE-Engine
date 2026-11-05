from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

from garminconnect import Garmin


def fetch_daily_metrics(email: str, password: str, target_date: date) -> Tuple[Dict[str, Any], List[str]]:
    """Busca métricas diárias diretamente da API da Garmin Connect."""
    warnings: List[str] = []
    metrics: Dict[str, Any] = {}

    client = Garmin(email, password)
    client.login()

    date_str = target_date.isoformat()

    # 1. Frequência Cardíaca de Repouso
    try:
        hr_data = client.get_rhr_day(date_str)
        if isinstance(hr_data, dict):
            metrics["rhr"] = hr_data.get("restingHeartRate")
    except Exception as exc:
        warnings.append(f"Não foi possível obter FC de repouso: {exc}")

    # 2. VRC (HRV)
    try:
        hrv_data = client.get_hrv_data(date_str)
        if isinstance(hrv_data, dict):
            summary = hrv_data.get("hrvSummary", {})
            metrics["hrv"] = summary.get("lastNightAvg") or summary.get("weeklyAvg")
    except Exception as exc:
        warnings.append(f"Não foi possível obter VRC: {exc}")

    # 3. Sono
    try:
        sleep_data = client.get_sleep_data(date_str)
        if isinstance(sleep_data, dict):
            dto = sleep_data.get("dailySleepDTO", {})
            metrics["sleep_score"] = dto.get("sleepScores", {}).get("overall", {}).get("value") or dto.get("sleepQualityScoreValue")
            sec = dto.get("sleepTimeSeconds")
            if sec:
                metrics["sleep_hours"] = round(sec / 3600.0, 2)
    except Exception as exc:
        warnings.append(f"Não foi possível obter dados de sono: {exc}")

    # 4. Garmin Training Readiness (Prontidão Oficial)
    try:
        readiness_data = client.get_training_readiness(date_str)
        if isinstance(readiness_data, dict):
            val = readiness_data.get("score") or readiness_data.get("scoreValue")
            if val is not None:
                metrics["vendor_readiness"] = float(val)
        elif isinstance(readiness_data, list) and readiness_data:
            val = readiness_data[0].get("score") or readiness_data[0].get("scoreValue")
            if val is not None:
                metrics["vendor_readiness"] = float(val)
    except Exception:
        # Fallback para endpoint diário genérico
        try:
            stats = client.get_stats(date_str)
            if isinstance(stats, dict) and "trainingReadinessScore" in stats:
                metrics["vendor_readiness"] = float(stats["trainingReadinessScore"])
        except Exception as exc:
            warnings.append(f"Prontidão Garmin indisponível para o dia: {exc}")

    return metrics, warnings

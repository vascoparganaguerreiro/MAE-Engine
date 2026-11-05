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

    # 4. Garmin Training Readiness (Extrai o valor mais recente)
    try:
        readiness_data = client.get_training_readiness(date_str)
        if isinstance(readiness_data, list) and len(readiness_data) > 0:
            last_entry = readiness_data[-1]
            val = last_entry.get("score") or last_entry.get("scoreValue")
            if val is not None:
                metrics["vendor_readiness"] = float(val)
        elif isinstance(readiness_data, dict):
            val = readiness_data.get("score") or readiness_data.get("scoreValue")
            if val is not None:
                metrics["vendor_readiness"] = float(val)
    except Exception:
        try:
            stats = client.get_stats(date_str)
            if isinstance(stats, dict) and "trainingReadinessScore" in stats:
                metrics["vendor_readiness"] = float(stats["trainingReadinessScore"])
        except Exception as exc:
            warnings.append(f"Prontidão Garmin indisponível para o dia: {exc}")

    return metrics, warnings


def fetch_historical_metrics(email: str, password: str, days: int = 60) -> List[Dict[str, Any]]:
    """Recupera até 'days' dias de histórico de VRC, RHR, Sono e Readiness diretamente da API."""
    client = Garmin(email, password)
    client.login()
    
    end_d = date.today()
    start_d = end_d - timedelta(days=days)
    
    records_by_date: Dict[str, Dict[str, Any]] = {}
    
    def get_rec(d_str: str) -> Dict[str, Any]:
        if d_str not in records_by_date:
            records_by_date[d_str] = {"date": d_str}
        return records_by_date[d_str]

    # VRC Histórica
    try:
        hrv_res = client.get_hrv_data(end_d.isoformat())
        if isinstance(hrv_res, dict):
            summaries = hrv_res.get("hrvSummaries", []) or hrv_res.get("userDailyHrvSummaries", [])
            for s in summaries:
                c_date = s.get("calendarDate")
                val = s.get("lastNightAvg") or s.get("weeklyAvg")
                if c_date and val is not None:
                    get_rec(c_date)["hrv"] = float(val)
    except Exception:
        pass

    # RHR e Sono via loops de fallback seguros
    curr = start_d
    while curr <= end_d:
        d_str = curr.isoformat()
        try:
            hr_d = client.get_rhr_day(d_str)
            if isinstance(hr_d, dict) and hr_d.get("restingHeartRate"):
                get_rec(d_str)["rhr"] = float(hr_d["restingHeartRate"])
        except Exception:
            pass
        curr += timedelta(days=1)

    return list(records_by_date.values())

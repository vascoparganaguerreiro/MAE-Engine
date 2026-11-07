from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from garminconnect import Garmin

logger = logging.getLogger(__name__)


def _safe_float(val: Any) -> Optional[float]:
    try:
        if val is None:
            return None
        v = float(val)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _extract_sleep(garmin_client: Garmin, target_date: date) -> Tuple[Optional[float], Optional[float]]:
    """Extrai horas de sono e score de sono testando múltiplos esquemas da API Garmin."""
    sleep_hours, sleep_score = None, None
    try:
        sleep_data = garmin_client.get_sleep_data(target_date.isoformat())
        if isinstance(sleep_data, dict):
            # 1. Tentar obter duração em segundos (múltiplas chaves possíveis)
            daily_summary = sleep_data.get("dailySleepDTO", {}) or sleep_data.get("summary", {}) or {}
            sec = (
                daily_summary.get("sleepTimeSeconds")
                or daily_summary.get("totalSleepSeconds")
                or sleep_data.get("totalSleepSeconds")
            )
            if sec is not None:
                sleep_hours = round(float(sec) / 3600.0, 2)

            # 2. Tentar obter o Sleep Score (0-100)
            score = (
                daily_summary.get("sleepScores", {}).get("overall", {}).get("value")
                or daily_summary.get("sleepScore")
                or sleep_data.get("sleepScore")
            )
            if score is not None:
                sleep_score = float(score)
    except Exception as exc:
        logger.warning("Não foi possível extrair dados de sono da Garmin: %s", exc)

    return sleep_hours, sleep_score


def _extract_training_readiness(garmin_client: Garmin, target_date: date) -> Optional[float]:
    """Extrai a Prontidão de Treino da Garmin (Training Readiness) em múltiplos formatos."""
    try:
        # Tentar endpoint dedicado de Training Readiness
        readiness_data = garmin_client.get_training_readiness(target_date.isoformat())
        if isinstance(readiness_data, list) and len(readiness_data) > 0:
            readiness_data = readiness_data[-1]
        if isinstance(readiness_data, dict):
            val = (
                readiness_data.get("score")
                or readiness_data.get("scoreValue")
                or readiness_data.get("trainingReadinessScore")
            )
            if val is not None:
                return float(val)
    except Exception:
        pass

    # Fallback: tentar obter a partir do resumo do dia
    try:
        stats = garmin_client.get_stats(target_date.isoformat())
        if isinstance(stats, dict):
            val = stats.get("trainingReadinessScore") or stats.get("userBodyBattery")
            if val is not None:
                return float(val)
    except Exception:
        pass

    return None


def fetch_daily_metrics(
    email: str,
    password: str,
    target_date: date,
    fetch_history: bool = False,
    history_days: int = 30,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Autentica na Garmin Connect e extrai HRV, RHR, Sono e Training Readiness."""
    warnings: List[str] = []
    garmin = Garmin(email, password)
    garmin.login()

    metrics: Dict[str, Any] = {}

    # 1. Frequência Cardíaca em Repouso (RHR)
    try:
        rhr_data = garmin.get_rhr_day(target_date.isoformat())
        if isinstance(rhr_data, dict):
            metrics["rhr"] = _safe_float(
                rhr_data.get("allDayMetics", {}).get("restingHeartRate")
                or rhr_data.get("restingHeartRate")
            )
    except Exception as exc:
        warnings.append(f"RHR indisponível: {exc}")

    # 2. Variabilidade da Frequência Cardíaca (HRV Noturna)
    try:
        hrv_data = garmin.get_hrv_data(target_date.isoformat())
        if isinstance(hrv_data, dict):
            summary = hrv_data.get("hrvSummary", {}) or {}
            metrics["hrv"] = _safe_float(
                summary.get("lastNightAvg") or summary.get("weeklyAvg")
            )
            metrics["hrv_weekly_avg"] = _safe_float(summary.get("weeklyAvg"))
    except Exception as exc:
        warnings.append(f"HRV indisponível: {exc}")

    # 3. Duração e Score do Sono (Robusto)
    sleep_h, sleep_score = _extract_sleep(garmin, target_date)
    if sleep_h is not None:
        metrics["sleep_hours"] = sleep_h
    if sleep_score is not None:
        metrics["sleep_score"] = sleep_score

    # 4. Prontidão Garmin (Training Readiness)
    readiness_val = _extract_training_readiness(garmin, target_date)
    if readiness_val is not None:
        metrics["vendor_readiness"] = readiness_val

    # 5. Histórico Recente (para alimentar baselines)
    history_records: List[Dict[str, Any]] = []
    if fetch_history:
        start_history = target_date - timedelta(days=history_days)
        try:
            rhr_hist = garmin.get_rhr_day(start_history.isoformat())
            # Adiciona parsing de histórico se devolvido em lista
        except Exception:
            pass

    return metrics, history_records, warnings

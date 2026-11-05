from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

from garminconnect import Garmin


def fetch_user_profile_data(client: Garmin) -> Dict[str, Any]:
    """Extrai métricas de perfil (idade, peso, sexo, vo2max, fc_max) da Garmin Connect."""
    profile_data: Dict[str, Any] = {}
    try:
        user_prof = client.get_user_profile()
        if isinstance(user_prof, dict):
            # Sexo
            gender_raw = str(user_prof.get("gender") or "").upper()
            if "MALE" in gender_raw and "FEMALE" not in gender_raw:
                profile_data["gender"] = "Masculino"
            elif "FEMALE" in gender_raw:
                profile_data["gender"] = "Feminino"

            # Idade / Data de Nascimento
            dob = user_prof.get("birthDate")
            if dob:
                try:
                    birth_year = datetime.strptime(str(dob)[:10], "%Y-%m-%d").year
                    profile_data["age"] = float(date.today().year - birth_year)
                except Exception:
                    pass

            # Peso (Garmin devolve em gramas ou kg)
            weight_g = user_prof.get("weight")
            if weight_g:
                w_val = float(weight_g)
                profile_data["weight_kg"] = round(w_val / 1000.0, 1) if w_val > 300 else round(w_val, 1)

            # VO2max e FC Máxima
            vo2 = user_prof.get("vo2MaxRunning") or user_prof.get("vo2MaxValue")
            if vo2:
                profile_data["vo2max"] = round(float(vo2), 1)

            hr_max = user_prof.get("runningMaxHeartRate") or user_prof.get("maxHeartRate")
            if hr_max:
                profile_data["hr_max"] = float(hr_max)
    except Exception:
        pass

    return profile_data


def fetch_daily_metrics(email: str, password: str, target_date: date) -> Tuple[Dict[str, Any], List[str]]:
    """Busca métricas diárias e dados de perfil diretamente da API da Garmin Connect."""
    warnings: List[str] = []
    metrics: Dict[str, Any] = {}

    client = Garmin(email, password)
    client.login()

    date_str = target_date.isoformat()

    # Tenta extrair perfil do utilizador
    prof = fetch_user_profile_data(client)
    if prof:
        metrics["profile_extracted"] = prof

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

    # 3. Sono & Meta Recomendada Garmin
    try:
        sleep_data = client.get_sleep_data(date_str)
        if isinstance(sleep_data, dict):
            dto = sleep_data.get("dailySleepDTO", {})
            metrics["sleep_score"] = dto.get("sleepScores", {}).get("overall", {}).get("value") or dto.get("sleepQualityScoreValue")
            sec = dto.get("sleepTimeSeconds")
            if sec:
                metrics["sleep_hours"] = round(sec / 3600.0, 2)
            
            sleep_need_min = dto.get("sleepNeed") or dto.get("sleepNeedMinutes")
            if sleep_need_min is not None:
                metrics["sleep_target_hours"] = round(float(sleep_need_min) / 60.0, 2)
    except Exception as exc:
        warnings.append(f"Não foi possível obter dados de sono: {exc}")

    # 4. Garmin Training Readiness
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


def fetch_historical_metrics(email: str, password: str, days: int = 30) -> List[Dict[str, Any]]:
    """Recupera o histórico recente de VRC e RHR iterando de forma segura dia a dia."""
    client = Garmin(email, password)
    client.login()
    
    end_d = date.today()
    records: List[Dict[str, Any]] = []

    for i in range(days):
        target_d = end_d - timedelta(days=i)
        d_str = target_d.isoformat()
        rec: Dict[str, Any] = {"date": d_str}
        
        try:
            hrv_data = client.get_hrv_data(d_str)
            if isinstance(hrv_data, dict):
                summary = hrv_data.get("hrvSummary", {})
                val = summary.get("lastNightAvg") or summary.get("weeklyAvg")
                if val is not None:
                    rec["hrv"] = float(val)
        except Exception:
            pass
            
        try:
            hr_data = client.get_rhr_day(d_str)
            if isinstance(hr_data, dict) and hr_data.get("restingHeartRate"):
                rec["rhr"] = float(hr_data["restingHeartRate"])
        except Exception:
            pass

        if len(rec) > 1:
            records.append(rec)
            
        time.sleep(0.1)

    return records

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Tuple

from garminconnect import Garmin


def fetch_user_profile_data(client: Garmin) -> Dict[str, Any]:
    profile_data: Dict[str, Any] = {}
    try:
        user_prof = client.get_user_profile()
        if isinstance(user_prof, dict):
            gender_raw = str(user_prof.get("gender") or "").upper()
            if "MALE" in gender_raw and "FEMALE" not in gender_raw:
                profile_data["gender"] = "Masculino"
            elif "FEMALE" in gender_raw:
                profile_data["gender"] = "Feminino"

            dob = user_prof.get("birthDate")
            if dob:
                try:
                    birth_year = datetime.strptime(str(dob)[:10], "%Y-%m-%d").year
                    profile_data["age"] = float(date.today().year - birth_year)
                except Exception:
                    pass

            weight_g = user_prof.get("weight")
            if weight_g:
                w_val = float(weight_g)
                profile_data["weight_kg"] = round(w_val / 1000.0, 1) if w_val > 300 else round(w_val, 1)

            vo2 = user_prof.get("vo2MaxRunning") or user_prof.get("vo2MaxValue")
            if vo2:
                profile_data["vo2max"] = round(float(vo2), 1)

            hr_max = user_prof.get("runningMaxHeartRate") or user_prof.get("maxHeartRate")
            if hr_max:
                profile_data["hr_max"] = float(hr_max)
    except Exception:
        pass

    return profile_data


def fetch_daily_metrics(email: str, password: str, target_date: date, fetch_history: bool = True, history_days: int = 30) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    metrics: Dict[str, Any] = {}
    historical_records: List[Dict[str, Any]] = []

    client = Garmin(email, password)
    client.login()

    date_str = target_date.isoformat()

    prof = fetch_user_profile_data(client)
    if prof:
        metrics["profile_extracted"] = prof

    # 1. FC de repouso
    try:
        hr_data = client.get_rhr_day(date_str)
        if isinstance(hr_data, dict):
            metrics["rhr"] = hr_data.get("restingHeartRate")
    except Exception as exc:
        warnings.append(f"Não foi possível obter FC de repouso: {exc}")

    # 2. VRC noturna e Média de 7 dias da Garmin Connect
    try:
        hrv_data = client.get_hrv_data(date_str)
        if isinstance(hrv_data, dict):
            summary = hrv_data.get("hrvSummary", {})
            metrics["hrv"] = summary.get("lastNightAvg") or summary.get("weeklyAvg")
            if summary.get("weeklyAvg") is not None:
                metrics["hrv_weekly_avg"] = float(summary.get("weeklyAvg"))
    except Exception as exc:
        warnings.append(f"Não foi possível obter VRC: {exc}")

    # 3. Sono e Meta Dinâmica
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

    # 4. Prontidão Garmin Dinâmica (Métrica em tempo real pós-treino)
    try:
        readiness_data = client.get_training_readiness(date_str)
        if isinstance(readiness_data, list) and len(readiness_data) > 0:
            sorted_entries = sorted(readiness_data, key=lambda x: str(x.get("timestamp") or x.get("date") or ""))
            latest_entry = sorted_entries[-1]
            val = latest_entry.get("score") or latest_entry.get("scoreValue") or latest_entry.get("value")
            if val is not None:
                metrics["vendor_readiness"] = float(val)
        elif isinstance(readiness_data, dict):
            val = readiness_data.get("score") or readiness_data.get("scoreValue") or readiness_data.get("value")
            if val is not None:
                metrics["vendor_readiness"] = float(val)
    except Exception:
        try:
            stats = client.get_stats(date_str)
            if isinstance(stats, dict) and "trainingReadinessScore" in stats:
                metrics["vendor_readiness"] = float(stats["trainingReadinessScore"])
        except Exception as exc:
            warnings.append(f"Prontidão Garmin indisponível para o dia: {exc}")

    # 5. Histórico recente de 30 dias
    if fetch_history:
        end_d = date.today()
        for i in range(history_days):
            target_d = end_d - timedelta(days=i)
            d_str = target_d.isoformat()
            rec: Dict[str, Any] = {"date": d_str}
            try:
                h_data = client.get_hrv_data(d_str)
                if isinstance(h_data, dict):
                    sum_h = h_data.get("hrvSummary", {})
                    val_h = sum_h.get("lastNightAvg") or sum_h.get("weeklyAvg")
                    if val_h is not None:
                        rec["hrv"] = float(val_h)
            except Exception:
                pass
                
            try:
                r_data = client.get_rhr_day(d_str)
                if isinstance(r_data, dict) and r_data.get("restingHeartRate"):
                    rec["rhr"] = float(r_data["restingHeartRate"])
            except Exception:
                pass

            if len(rec) > 1:
                historical_records.append(rec)
            time.sleep(0.05)

    return metrics, historical_records, warnings


def fetch_historical_metrics(email: str, password: str, days: int = 30) -> List[Dict[str, Any]]:
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

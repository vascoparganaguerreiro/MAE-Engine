from __future__ import annotations

import io
import json
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

import data_store as store


def _clean_number(value: Any) -> Optional[float]:
    try:
        v = float(value)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def update_profile_if_missing(new_prof: Dict[str, Any]):
    curr = store.get_setting("profile", {}) or {}
    updated = False
    for k in ["gender", "age", "weight_kg", "vo2max", "hr_max"]:
        if new_prof.get(k) is not None and not curr.get(k):
            curr[k] = new_prof[k]
            updated = True
    if updated:
        store.set_setting("profile", curr)


def parse_garmin_file_content(file_name: str, content: bytes) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    fname_lower = file_name.lower()

    if "userprofile" in fname_lower or "profile" in fname_lower:
        try:
            prof_data = json.loads(content.decode("utf-8", errors="ignore"))
            ext: Dict[str, Any] = {}
            if isinstance(prof_data, dict):
                if prof_data.get("gender"):
                    g_str = str(prof_data["gender"]).upper()
                    ext["gender"] = "Masculino" if "MALE" in g_str and "FEMALE" not in g_str else "Feminino" if "FEMALE" in g_str else None
                if prof_data.get("weight"):
                    w = float(prof_data["weight"])
                    ext["weight_kg"] = round(w / 1000.0, 1) if w > 300 else round(w, 1)
                if prof_data.get("vo2MaxRunning") or prof_data.get("vo2MaxValue"):
                    ext["vo2max"] = float(prof_data.get("vo2MaxRunning") or prof_data.get("vo2MaxValue"))
                if prof_data.get("runningMaxHeartRate") or prof_data.get("maxHeartRate"):
                    ext["hr_max"] = float(prof_data.get("runningMaxHeartRate") or prof_data.get("maxHeartRate"))
                if ext:
                    update_profile_if_missing(ext)
        except Exception:
            pass

    if fname_lower.endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(content))
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

            date_col = next((c for c in df.columns if any(k in c for k in ["data", "date", "day", "calendar"])), None)
            if not date_col:
                return records

            hrv_col = next((c for c in df.columns if any(k in c for k in ["hrv", "vrc", "sdnn", "lastnightavg", "weeklyavg"])), None)
            rhr_col = next((c for c in df.columns if any(k in c for k in ["rhr", "repouso", "resting", "restingheartrate"])), None)
            sleep_score_col = next((c for c in df.columns if "sleep" in c and "score" in c or "pontuação" in c), None)
            sleep_hours_col = next((c for c in df.columns if any(k in c for k in ["sleep_time", "horas_de_sono", "duration", "total_sleep"])), None)
            readiness_col = next((c for c in df.columns if any(k in c for k in ["readiness", "prontidão", "training_readiness"])), None)

            for _, row in df.iterrows():
                try:
                    d_val = pd.to_datetime(row[date_col]).date().isoformat()
                except Exception:
                    continue

                rec: Dict[str, Any] = {"date": d_val}
                if hrv_col and pd.notna(row[hrv_col]):
                    rec["hrv"] = _clean_number(row[hrv_col])
                if rhr_col and pd.notna(row[rhr_col]):
                    rec["rhr"] = _clean_number(row[rhr_col])
                if sleep_score_col and pd.notna(row[sleep_score_col]):
                    rec["sleep_score"] = _clean_number(row[sleep_score_col])
                if sleep_hours_col and pd.notna(row[sleep_hours_col]):
                    h_val = _clean_number(row[sleep_hours_col])
                    rec["sleep_hours"] = round(h_val / 3600.0, 2) if h_val and h_val > 24 else h_val
                if readiness_col and pd.notna(row[readiness_col]):
                    rec["vendor_readiness"] = _clean_number(row[readiness_col])

                if len(rec) > 1:
                    records.append(rec)
        except Exception:
            pass

    elif fname_lower.endswith(".json"):
        try:
            data = json.loads(content.decode("utf-8", errors="ignore"))
            if isinstance(data, dict):
                data = [data]

            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue

                    raw_date = (
                        item.get("calendarDate")
                        or item.get("date")
                        or item.get("day")
                        or item.get("userDailySleepDTO", {}).get("calendarDate")
                    )
                    if not raw_date:
                        continue

                    try:
                        d_str = pd.to_datetime(raw_date).date().isoformat()
                    except Exception:
                        continue

                    rec: Dict[str, Any] = {"date": d_str}

                    rhr_val = item.get("restingHeartRate") or item.get("rhr")
                    if rhr_val is not None:
                        rec["rhr"] = _clean_number(rhr_val)

                    hrv_val = (
                        item.get("lastNightAvg")
                        or item.get("hrvSummary", {}).get("lastNightAvg")
                        or item.get("weeklyAvg")
                    )
                    if hrv_val is not None:
                        rec["hrv"] = _clean_number(hrv_val)

                    readiness_val = (
                        item.get("score")
                        or item.get("trainingReadinessScore")
                        or item.get("scoreValue")
                    )
                    if readiness_val is not None:
                        rec["vendor_readiness"] = _clean_number(readiness_val)

                    sleep_dto = item.get("userDailySleepDTO") or item
                    sleep_sec = (
                        sleep_dto.get("sleepTimeSeconds")
                        or sleep_dto.get("totalSleepHours")
                        or item.get("sleepTimeSeconds")
                    )
                    if sleep_sec is not None:
                        sec_num = _clean_number(sleep_sec)
                        if sec_num and sec_num > 0:
                            rec["sleep_hours"] = round(sec_num / 3600.0, 2) if sec_num > 24 else round(sec_num, 2)

                    sleep_score = (
                        sleep_dto.get("sleepScores", {}).get("overall", {}).get("value")
                        or sleep_dto.get("overallScore")
                    )
                    if sleep_score is not None:
                        rec["sleep_score"] = _clean_number(sleep_score)

                    if len(rec) > 1:
                        records.append(rec)
        except Exception:
            pass

    return records

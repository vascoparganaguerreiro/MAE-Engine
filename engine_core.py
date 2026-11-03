"""
Apex Engine Core (v3.1 - Clinical & Sports Science Engine with Advanced Nutrition)
"""

import math
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple


# ==========================================
# TRANSLATION DICTIONARY
# ==========================================
TRANSLATIONS = {
    "PT": {
        "today_decision_green": "Dia de Treino Normal: Capacidade Total",
        "today_decision_amber": "Dia Moderado: Reduzir Carga Axial e Intensidade",
        "today_decision_red": "Dia de Recuperação Ativa: Preservar o Sistema Nervoso",
    },
    "EN": {
        "today_decision_green": "Full Training Day: High Readiness",
        "today_decision_amber": "Moderate Day: Lower Axial Load & Intensity",
        "today_decision_red": "Recovery Day: Protect Nervous System",
    }
}

def t(key: str, lang: str = "PT", **kwargs) -> str:
    text = TRANSLATIONS.get(lang, TRANSLATIONS["PT"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ==========================================
# DATA QUALITY & CALIBRATION
# ==========================================
class DataQualityEngine:
    @staticmethod
    def evaluate_sleep_quality(sleep_seconds: float, deep_seconds: Optional[float], 
                               rem_seconds: Optional[float], awake_seconds: Optional[float]) -> Tuple[float, List[str]]:
        reasons = []
        confidence = 1.0

        if not sleep_seconds or sleep_seconds < 18000:
            confidence -= 0.3
            reasons.append("Duração de sono inferior a 5h")

        if sleep_seconds and deep_seconds:
            deep_pct = (deep_seconds / sleep_seconds) * 100
            if deep_pct < 3.0:
                confidence -= 0.2
                reasons.append("Sono Profundo < 3%")

        if sleep_seconds and rem_seconds:
            rem_pct = (rem_seconds / sleep_seconds) * 100
            if rem_pct < 5.0:
                confidence -= 0.2
                reasons.append("Sono REM < 5%")

        return max(0.1, round(confidence, 2)), reasons

    @staticmethod
    def get_calibration_state(days_of_history: int) -> Tuple[str, str]:
        if days_of_history < 28:
            return "calibrating", f"Calibração: Dia {days_of_history}/28"
        elif days_of_history < 60:
            return "provisional", f"Linha de Base Provisória ({days_of_history}/60 dias)"
        return "personalized", "Linha de Base Sólida (60 Dias)"


def get_hrv_context(current_rmssd: float, baseline_rmssd: float) -> Dict[str, str]:
    if baseline_rmssd <= 0:
        return {"status": "Sem Dados", "explanation": "A recolher dados para definir linha de base."}
    
    delta_pct = ((current_rmssd - baseline_rmssd) / baseline_rmssd) * 100
    if delta_pct < -25:
        return {
            "status": "Sympathetic Stress Overdrive",
            "explanation": f"O teu VRC noturno caiu {abs(delta_pct):.1f}% abaixo da média de 60 dias. "
                           "Reflete supressão parassimpática expressiva. Evitar treinos de alta intensidade hoje."
        }
    elif delta_pct < -10:
        return {
            "status": "Fadiga Autonómica Moderada",
            "explanation": f"O teu VRC noturno está {abs(delta_pct):.1f}% abaixo da linha de base. "
                           "Recomenda-se treino aeróbico em Z1/Z2 ou mobilidade."
        }
    elif delta_pct > 15:
        return {
            "status": "Hiper-Adaptação / Prontidão Alta",
            "explanation": f"VRC noturno {delta_pct:.1f}% acima da média. Sistema em excelente recuperação."
        }
    else:
        return {
            "status": "Homeostase Fisiológica",
            "explanation": "VRC dentro da faixa normal. Seguir plano de treino habitual."
        }


def zscore(val: float, mean: float, sd: float) -> float:
    return (val - mean) / max(sd, 1e-4)


def compute_zscore_readiness(
    hrv_val: float, hrv_mean_60d: float, hrv_sd_60d: float,
    rhr_val: float, rhr_mean_60d: float, rhr_sd_60d: float,
    sleep_score: float, sleep_mean_60d: float, sleep_sd_60d: float,
    acute_load: float, load_mean_60d: float, load_sd_60d: float,
    mood_score: float, mood_mean: float = 3.0, mood_sd: float = 1.0,
    user_mode: str = "Performance"
) -> Dict[str, Any]:
    hrv_z = zscore(hrv_val, hrv_mean_60d, hrv_sd_60d)
    rhr_z = -zscore(rhr_val, rhr_mean_60d, rhr_sd_60d)
    sleep_z = zscore(sleep_score, sleep_mean_60d, sleep_sd_60d)
    load_z = -zscore(acute_load, load_mean_60d, load_sd_60d)
    mood_z = zscore(mood_score, mood_mean, mood_sd)

    if "Longevidade" in user_mode:
        w_hrv, w_rhr, w_sleep, w_load, w_mood = 0.35, 0.20, 0.25, 0.10, 0.10
    else:
        w_hrv, w_rhr, w_sleep, w_load, w_mood = 0.30, 0.15, 0.20, 0.20, 0.15

    raw_z_sum = (w_hrv * hrv_z) + (w_rhr * rhr_z) + (w_sleep * sleep_z) + (w_load * load_z) + (w_mood * mood_z)
    norm_score = int(min(100, max(0, round(50 + (raw_z_sum * 16.6)))))

    waterfall = {
        "VRC Noturno": round(w_hrv * hrv_z * 16.6, 1),
        "FC Repouso": round(w_rhr * rhr_z * 16.6, 1),
        "Qualidade Sono": round(w_sleep * sleep_z * 16.6, 1),
        "Carga Aguda": round(w_load * load_z * 16.6, 1),
        "Humor / Diário": round(w_mood * mood_z * 16.6, 1),
    }

    return {
        "readiness_score": norm_score,
        "z_sum": round(raw_z_sum, 2),
        "waterfall": waterfall,
    }


def compute_sleep_debt_7d(sleep_hours_series: List[float], target_sleep_hours: float = 8.0) -> float:
    if not sleep_hours_series:
        return 0.0
    last_7 = sleep_hours_series[-7:]
    debt = sum([max(0.0, target_sleep_hours - h) for h in last_7])
    return round(debt, 1)


def calculate_trend_slope(series: List[float]) -> Dict[str, Any]:
    if not series or len(series) < 3:
        return {"slope": 0.0, "text": "Dados insuficientes para tendência"}
    
    clean_series = [x for x in series if x is not None and not np.isnan(x)]
    if len(clean_series) < 3:
        return {"slope": 0.0, "text": "Dados insuficientes"}
        
    y = np.array(clean_series)
    x = np.arange(len(y))
    slope, _ = np.polyfit(x, y, 1)
    
    if slope > 0.3:
        status = "Adaptação Positiva Exponencial"
    elif slope > 0.05:
        status = "Adaptação Ligeira / Estável"
    elif slope > -0.3:
        status = "Fadiga Acumulada Ligeira"
    else:
        status = "Supressão Autonómica Crítica"
        
    return {"slope": round(float(slope), 2), "text": status}


def evaluate_hrv_rhr_matrix(hrv_val: float, hrv_mean: float, hrv_sd: float,
                            rhr_val: float, rhr_mean: float, rhr_sd: float) -> Dict[str, str]:
    hrv_z = zscore(hrv_val, hrv_mean, hrv_sd)
    rhr_z = zscore(rhr_val, rhr_mean, rhr_sd)

    if abs(hrv_z) <= 1.0 and abs(rhr_z) <= 1.0:
        return {"quadrant": "Normal", "status": "Homeostase", "action": "Treino normal."}
    elif hrv_z < -1.0 and rhr_z > 1.0:
        return {"quadrant": "Fadiga Aguda", "status": "Sympathetic Stress", "action": "Reduzir intensidade."}
    elif hrv_z > 1.0 and rhr_z < -1.0:
        return {"quadrant": "Prontidão Alta", "status": "Parasympathetic High", "action": "Excelente capacidade."}
    else:
        return {"quadrant": "Desvio Ligeiro", "status": "Moderado", "action": "Ajustar volume."}


# ==========================================
# STRENGTH & AXIAL LOAD DATABASE
# ==========================================
EXERCISE_DATABASE = [
    {
        "id": "sq_back", "name": "Agachamento com Barra (Back Squat)", "pattern": "Squat",
        "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_press", "base_pct_1rm": 0.75,
        "active_muscles": "Quadríceps, Glúteo Máximo", "joint_protected": "Coluna Lombar"
    },
    {
        "id": "leg_press", "name": "Prensa de Pernas (Leg Press)", "pattern": "Squat",
        "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.70,
        "active_muscles": "Quadríceps", "joint_protected": "Coluna Isenta"
    },
    {
        "id": "rdl_bb", "name": "Peso Morto Romeno (RDL com Barra)", "pattern": "Hinge",
        "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_curl", "base_pct_1rm": 0.70,
        "active_muscles": "Isquiotibiais, Glúteos", "joint_protected": "Eretores da Espinha"
    },
    {
        "id": "leg_curl", "name": "Flexão de Pernas Deitado (Leg Curl)", "pattern": "Hinge",
        "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.65,
        "active_muscles": "Isquiotibiais", "joint_protected": "Lombar Isenta"
    }
]


def calculate_spinal_load_score(workout_exercises: List[Dict[str, Any]]) -> float:
    if not workout_exercises:
        return 0.0
    scores = [ex.get("spinal_load", 1) for ex in workout_exercises]
    return round(float(np.mean(scores)), 1)


def autoregulate_strength_workout(readiness_score: int, user_1rm_dict: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    if user_1rm_dict is None:
        user_1rm_dict = {"sq_back": 140.0, "rdl_bb": 120.0, "leg_press": 200.0, "leg_curl": 70.0}

    workout = []
    high_fatigue = readiness_score < 45

    for idx in [0, 2]:
        ex = EXERCISE_DATABASE[idx]
        chosen_ex = ex
        substituted = False
        reason = ""

        if high_fatigue and ex["spinal_load"] >= 4:
            alt_id = ex["alt_low_axial"]
            if alt_id:
                alt_ex = next((e for e in EXERCISE_DATABASE if e["id"] == alt_id), None)
                if alt_ex:
                    chosen_ex = alt_ex
                    substituted = True
                    reason = f"Substituído {ex['name']} por {alt_ex['name']} para proteger a coluna."

        est_1rm = user_1rm_dict.get(chosen_ex["id"], 100.0)
        recommended_weight = round(est_1rm * chosen_ex["base_pct_1rm"], 1)

        workout.append({
            "id": chosen_ex["id"],
            "exercise": chosen_ex["name"],
            "pattern": chosen_ex["pattern"],
            "sets": 2 if high_fatigue else 3,
            "reps": "8–10",
            "intensity": "RPE 6-7" if high_fatigue else "RPE 8",
            "target_kg": recommended_weight,
            "substituted": substituted,
            "reason": reason,
            "spinal_load": chosen_ex["spinal_load"],
            "active_muscles": chosen_ex["active_muscles"],
            "joint_protected": chosen_ex["joint_protected"]
        })

    return {
        "workout": workout,
        "note": "Sessão adaptada ao teu nível de fadiga atual.",
        "readiness_score": readiness_score,
        "spinal_score": calculate_spinal_load_score(workout)
    }


def estimate_1rm(weight: float, reps: int) -> float:
    if reps == 1:
        return weight
    return round(weight * (1.0 + (reps / 30.0)), 1)


def calculate_srpe(duration_min: float, rpe: float) -> float:
    return round(duration_min * rpe, 1)


# ==========================================
# BANISTER & FOSTER LOAD ENGINE
# ==========================================
def compute_foster_load_metrics(daily_loads_7d: List[float]) -> Dict[str, float]:
    if not daily_loads_7d or len(daily_loads_7d) < 7:
        return {"weekly_load": 0.0, "monotony": 1.0, "strain": 0.0}

    weekly_load = sum(daily_loads_7d)
    mean_load = weekly_load / 7.0
    sd_load = float(np.std(daily_loads_7d))

    monotony = round(mean_load / max(sd_load, 1.0), 2)
    strain = round(weekly_load * monotony, 1)

    return {"weekly_load": round(weekly_load, 1), "monotony": monotony, "strain": strain}


def compute_acwr(daily_loads_history: List[float]) -> float:
    if len(daily_loads_history) < 28:
        return 1.0
    acute_7d = float(np.mean(daily_loads_history[-7:]))
    chronic_28d = float(np.mean(daily_loads_history[-28:]))
    if chronic_28d == 0:
        return 1.0
    return round(acute_7d / chronic_28d, 2)


def compute_banister_ctl_atl_tsb(
    daily_loads_history: List[float], 
    ctl_decay: float = 42.0, 
    atl_decay: float = 7.0
) -> Tuple[List[float], List[float], List[float]]:
    ctl_list, atl_list, tsb_list = [], [], []
    ctl, atl = 0.0, 0.0

    for load in daily_loads_history:
        ctl = ctl + (load - ctl) * (1.0 / ctl_decay)
        atl = atl + (load - atl) * (1.0 / atl_decay)
        tsb = ctl - atl

        ctl_list.append(round(ctl, 1))
        atl_list.append(round(atl, 1))
        tsb_list.append(round(tsb, 1))

    return ctl_list, atl_list, tsb_list


# ==========================================
# LONGEVITY & HEALTHSPAN
# ==========================================
def get_vo2_percentile(vo2_max: float, age: int) -> str:
    if vo2_max >= 58:
        return "Top 2% (Superior / Elite)"
    elif vo2_max >= 50:
        return "Top 10% (Excelente)"
    elif vo2_max >= 42:
        return "Top 25% (Acima da Média)"
    else:
        return "Média Populacional"


def calculate_biological_age(chronological_age: int, vo2_max: float, rhr: float, hrv: float) -> int:
    bio_age = float(chronological_age)
    bio_age -= (vo2_max - 45) * 0.25
    bio_age += (rhr - 50) * 0.20
    bio_age -= (hrv - 50) * 0.10
    return max(18, int(round(bio_age)))


# ==========================================
# RACE HUB & ADVANCED NUTRITION ENGINE
# ==========================================
def predict_race_time(vo2_max: float, distance_km: float) -> str:
    base_10k_sec = (45.0 / max(vo2_max, 25.0)) * 2500.0
    t2 = base_10k_sec * ((distance_km / 10.0) ** 1.06)
    
    hrs = int(t2 // 3600)
    mins = int((t2 % 3600) // 60)
    secs = int(t2 % 60)
    
    if hrs > 0:
        return f"{hrs}h {mins:02d}m {secs:02d}s"
    return f"{mins:02d}m {secs:02d}s"


def calculate_advanced_race_nutrition(
    weight_kg: float,
    body_fat_pct: float,
    gender: str,
    age: int,
    sport_type: str,
    duration_hours: float,
    temp_c: float = 22.0
) -> Dict[str, Any]:
    """
    Calcula a estratégia de nutrição e hidratação personalizada com base na
    massa magra (FFM), género, idade, tipo de desporto e clima.
    """
    # 1. Estimativa de Massa Magra
    lean_mass_kg = weight_kg * (1.0 - (body_fat_pct / 100.0))

    # 2. Taxa de Hidratos de Carbono por hora (g/h)
    if "Ironman (Full)" in sport_type:
        base_carbs_per_hr = 85.0
    elif "Half Ironman" in sport_type or "70.3" in sport_type:
        base_carbs_per_hr = 75.0
    elif "Maratona" in sport_type:
        base_carbs_per_hr = 65.0
    else:  # 10K / Meia Maratona
        base_carbs_per_hr = 50.0

    # Ajuste por Massa Magra e Género
    gender_factor = 1.0 if gender == "Masculino" else 0.90
    mass_factor = lean_mass_kg / 65.0  # Normalizado a 65kg de massa magra
    
    final_carbs_g_hr = min(110.0, max(40.0, base_carbs_per_hr * mass_factor * gender_factor))
    total_carbs_g = final_carbs_g_hr * duration_hours

    # 3. Taxa de Hidratação (mL/h) com base no clima e peso
    base_fluid_ml_hr = weight_kg * 8.5
    if temp_c > 25:
        base_fluid_ml_hr *= 1.25
    elif temp_c > 20:
        base_fluid_ml_hr *= 1.10

    total_fluid_l = (base_fluid_ml_hr * duration_hours) / 1000.0

    # 4. Sódio e Eletrólitos (mg/h)
    sodium_mg_hr = 600.0 if temp_c < 22 else 900.0
    total_sodium_mg = sodium_mg_hr * duration_hours

    # 5. Calorias Totais de Esforço
    total_kcal = (total_carbs_g * 4.0) + (duration_hours * weight_kg * 8.0 * 0.4)

    return {
        "lean_mass_kg": round(lean_mass_kg, 1),
        "carbs_per_hour_g": round(final_carbs_g_hr, 0),
        "total_carbs_g": round(total_carbs_g, 0),
        "fluid_per_hour_ml": round(base_fluid_ml_hr, 0),
        "total_fluid_l": round(total_fluid_l, 2),
        "sodium_mg_per_hour": round(sodium_mg_hr, 0),
        "total_sodium_mg": round(total_sodium_mg, 0),
        "total_kcal": round(total_kcal, 0)
    }

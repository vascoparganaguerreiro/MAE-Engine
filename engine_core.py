"""
Apex Engine Core (v3.0 - Comprehensive Clinical & Sports Science Engine)
Contains deterministic models, Z-score readiness, Banister CTL/ATL/TSB, ACWR,
Foster Monotony/Strain, Autoregulated Strength Engine, and Healthspan Analytics.
"""

import math
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple


# ==========================================
# TRANSLATION DICTIONARY (i18n PT-PT / EN)
# ==========================================
TRANSLATIONS = {
    "PT": {
        "today_decision_green": "Dia de Treino Normal: Capacidade Total",
        "today_decision_amber": "Dia Moderado: Reduzir Carga Axial e Intensidade",
        "today_decision_red": "Dia de Recuperação Ativa: Preservar o Sistema Nervoso",
        "today_reason_hrv_low": "VRC Noturno abaixo da tua linha de base de 60 dias",
        "today_reason_hrv_ok": "VRC Noturno dentro da tua faixa normal",
        "today_reason_sleep_low": "Défice de sono acumulado detetado",
        "today_reason_sleep_ok": "Duração e arquitetura de sono adequadas",
        "today_reason_rhr_high": "FC de Repouso elevada (sinal de stress/fadiga)",
        "today_reason_rhr_ok": "FC de Repouso estável",
        "action_start_zone2": "Zona 2 Leve (30 min)",
        "action_start_strength": "Força Adaptativa",
        "action_mobility": "Mobilidade (20 min)",
        "action_log_diary": "Registar Diário",
        "calibrating": "Em Calibração (Dia {day}/28)",
        "provisional": "Linha de Base Provisória (28-59 dias)",
        "personalized": "Linha de Base Sólida (60 dias)",
        "confidence_high": "Confiança Elevada dos Dados",
        "confidence_med": "Confiança Média (Dados Parciais)",
        "confidence_low": "Confiança Baixa (Sensor / Falha)",
    },
    "EN": {
        "today_decision_green": "Full Training Day: High Readiness",
        "today_decision_amber": "Moderate Day: Lower Axial Load & Intensity",
        "today_decision_red": "Recovery Day: Protect Nervous System",
        "today_reason_hrv_low": "Overnight HRV below your 60-day baseline",
        "today_reason_hrv_ok": "Overnight HRV within normal range",
        "today_reason_sleep_low": "Accumulated sleep deficit detected",
        "today_reason_sleep_ok": "Sleep duration and architecture adequate",
        "today_reason_rhr_high": "Elevated Resting HR (stress/fatigue signal)",
        "today_reason_rhr_ok": "Resting HR stable",
        "action_start_zone2": "Light Zone 2 (30 min)",
        "action_start_strength": "Adaptive Strength",
        "action_mobility": "Mobility (20 min)",
        "action_log_diary": "Log Diary",
        "calibrating": "Calibrating (Day {day}/28)",
        "provisional": "Provisional Baseline (28-59 days)",
        "personalized": "Solid 60-Day Baseline",
        "confidence_high": "High Data Confidence",
        "confidence_med": "Medium Data Confidence",
        "confidence_low": "Low Data Confidence",
    }
}


def t(key: str, lang: str = "PT", **kwargs) -> str:
    text = TRANSLATIONS.get(lang, TRANSLATIONS["PT"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ==========================================
# PILLAR 1: TODAY / DECISÃO DIÁRIA ENGINE
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

        if sleep_seconds and awake_seconds:
            awake_pct = (awake_seconds / sleep_seconds) * 100
            if awake_pct > 20.0:
                confidence -= 0.2
                reasons.append("Tempo acordado elevado (> 20%)")

        return max(0.1, round(confidence, 2)), reasons

    @staticmethod
    def get_calibration_state(days_of_history: int) -> Tuple[str, str]:
        if days_of_history < 28:
            return "calibrating", f"Calibração: Dia {days_of_history}/28"
        elif days_of_history < 60:
            return "provisional", f"Linha de Base Provisória ({days_of_history}/60 dias)"
        return "personalized", "Linha de Base Sólida (60 Dias)"


def get_hrv_context(current_rmssd: float, baseline_rmssd: float) -> Dict[str, str]:
    """Feature 1: Dynamic Physiological Contextualization."""
    if baseline_rmssd <= 0:
        return {"status": "Sem Dados", "explanation": "A recolher dados para definir linha de base."}
    
    delta_pct = ((current_rmssd - baseline_rmssd) / baseline_rmssd) * 100
    if delta_pct < -25:
        return {
            "status": "Sympathetic Stress Overdrive",
            "explanation": f"O teu VRC noturno caiu {abs(delta_pct):.1f}% abaixo da média de 60 dias. "
                           "Reflete supressão parassimpática expressiva por carga aguda elevada, má continuidade de sono "
                           "ou stress sistémico. Esforços de alta intensidade hoje transportam risco acrescido de sobretreino."
        }
    elif delta_pct < -10:
        return {
            "status": "Fadiga Autonómica Moderada",
            "explanation": f"O teu VRC noturno está {abs(delta_pct):.1f}% abaixo da linha de base. "
                           "Fadiga acumulada ligeira. Recomenda-se treino aeróbico em Z1/Z2 ou musculação com carga axial reduzida."
        }
    elif delta_pct > 15:
        return {
            "status": "Hiper-Adaptação / Recuperação Elevada",
            "explanation": f"VRC noturno {delta_pct:.1f}% acima da média. "
                           "Sistema nervoso em homeostase ideal. Capacidade total para sessões de alta intensidade ou teste de carga."
        }
    else:
        return {
            "status": "Homeostase Fisiológica",
            "explanation": "VRC dentro da faixa normal de flutuação (+/- 10%). Seguir plano de treino habitual."
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
        "hrv_z": round(hrv_z, 2),
        "rhr_z": round(rhr_z, 2)
    }


def compute_sleep_debt_7d(sleep_hours_series: List[float], target_sleep_hours: float = 8.0) -> float:
    """Feature 4: Circadian Sleep Debt Accumulator."""
    if not sleep_hours_series:
        return 0.0
    last_7 = sleep_hours_series[-7:]
    debt = sum([max(0.0, target_sleep_hours - h) for h in last_7])
    return round(debt, 1)


# ==========================================
# PILLAR 2: VRC & TREND ENGINE
# ==========================================
def calculate_trend_slope(series: List[float]) -> Dict[str, Any]:
    """Feature 16: Trend Slope Indicator."""
    if len(series) < 3:
        return {"slope": 0.0, "text": "Dados insuficientes"}
    y = np.array(series)
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
        return {"quadrant": "Normal / Equilibrado", "status": "Homeostase", "action": "Treino normal dentro do plano previsto."}
    elif hrv_z < -1.0 and rhr_z > 1.0:
        return {"quadrant": "Fadiga Aguda / Stress", "status": "Sympathetic Stress", "action": "Sinal de sobrecarga ou início de infeção. Reduzir intensidade."}
    elif hrv_z > 1.0 and rhr_z < -1.0:
        return {"quadrant": "Prontidão Elevada", "status": "Parasympathetic High", "action": "Excelente capacidade de adaptação. Estímulo de qualidade autorizado."}
    elif hrv_z > 1.5 and rhr_z > 1.0:
        return {"quadrant": "Atípico / Desregulação", "status": "Autonomic Disruption", "action": "Sinal atípico (exaustão central). Priorizar descanso e hidratação."}
    else:
        return {"quadrant": "Desvio Ligeiro", "status": "Moderado", "action": "Ajustar volume de treino com prudência."}


# ==========================================
# PILLAR 3: FORÇA & CARGA AXIAL ENGINE
# ==========================================
EXERCISE_DATABASE = [
    {
        "id": "sq_back", "name": "Agachamento com Barra (Back Squat)", "pattern": "Squat",
        "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_press", "base_pct_1rm": 0.75,
        "active_muscles": "Quadríceps, Glúteo Máximo", "joint_protected": "Coluna Lombar (evitar axial)"
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
    },
    {
        "id": "split_squat", "name": "Agachamento Búlgaro (Split Squat)", "pattern": "Unilateral",
        "spinal_load": 3, "equip": "Dumbbells", "alt_low_axial": "leg_ext", "base_pct_1rm": 0.65,
        "active_muscles": "Quadríceps, Estabilizadores", "joint_protected": "Papeis Unilaterais"
    },
    {
        "id": "leg_ext", "name": "Extensão de Pernas (Leg Extension)", "pattern": "Isolation",
        "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.60,
        "active_muscles": "Quadríceps Isolado", "joint_protected": "Joelho (RPE Moderado)"
    }
]


def calculate_spinal_load_score(workout_exercises: List[Dict[str, Any]]) -> float:
    """Feature 21: Automated Axial Load Scoring Matrix."""
    if not workout_exercises:
        return 0.0
    scores = [ex.get("spinal_load", 1) for ex in workout_exercises]
    return round(float(np.mean(scores)), 1)


def autoregulate_strength_workout(readiness_score: int, user_1rm_dict: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    if user_1rm_dict is None:
        user_1rm_dict = {"sq_back": 140.0, "rdl_bb": 120.0, "leg_press": 200.0, "leg_curl": 70.0}

    workout = []
    
    if readiness_score >= 70:
        intensity_target = "RPE 8-9 (1-2 RIR)"
        set_multiplier = 1.0
        reduction_note = "Capacidade total: Exercícios base com carga axial autorizados."
        high_fatigue = False
    elif readiness_score >= 45:
        intensity_target = "RPE 7-8 (2-3 RIR)"
        set_multiplier = 0.8
        reduction_note = "Fadiga moderada: Manter volume mas limitar RPE."
        high_fatigue = False
    else:
        intensity_target = "RPE 6-7 (3-4 RIR)"
        set_multiplier = 0.6
        reduction_note = "Sessão Leve Opcional: Exercícios com carga na coluna substituídos por máquinas."
        high_fatigue = True

    base_indices = [0, 2]

    for idx in base_indices:
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
                    reason = f"Substituído {ex['name']} (Carga axial {ex['spinal_load']}/5) por {alt_ex['name']} para proteger a coluna."

        base_sets = 3
        final_sets = max(2, int(round(base_sets * set_multiplier)))
        
        est_1rm = user_1rm_dict.get(chosen_ex["id"], 100.0)
        recommended_weight = round(est_1rm * chosen_ex["base_pct_1rm"], 1)

        workout.append({
            "id": chosen_ex["id"],
            "exercise": chosen_ex["name"],
            "pattern": chosen_ex["pattern"],
            "sets": final_sets,
            "reps": "8–10",
            "intensity": intensity_target,
            "target_kg": recommended_weight,
            "substituted": substituted,
            "original_name": ex["name"] if substituted else None,
            "reason": reason,
            "spinal_load": chosen_ex["spinal_load"],
            "active_muscles": chosen_ex["active_muscles"],
            "joint_protected": chosen_ex["joint_protected"]
        })

    return {
        "workout": workout,
        "note": reduction_note,
        "readiness_score": readiness_score,
        "spinal_score": calculate_spinal_load_score(workout)
    }


def estimate_1rm(weight: float, reps: int) -> float:
    if reps == 1:
        return weight
    return round(weight * (1.0 + (reps / 30.0)), 1)


def calculate_srpe(duration_min: float, rpe: float) -> float:
    """Feature 30: Post-Workout RPE Feedback Loop."""
    return round(duration_min * rpe, 1)


# ==========================================
# PILLAR 4: BANISTER & CARGA ENGINE
# ==========================================
def compute_foster_load_metrics(daily_loads_7d: List[float]) -> Dict[str, float]:
    if not daily_loads_7d or len(daily_loads_7d) < 7:
        return {"weekly_load": 0.0, "monotony": 1.0, "strain": 0.0}

    weekly_load = sum(daily_loads_7d)
    mean_load = weekly_load / 7.0
    variance = sum((x - mean_load) ** 2 for x in daily_loads_7d) / 7.0
    sd_load = math.sqrt(variance)

    monotony = round(mean_load / max(sd_load, 1.0), 2)
    strain = round(weekly_load * monotony, 1)

    return {
        "weekly_load": round(weekly_load, 1),
        "mean_daily_load": round(mean_load, 1),
        "monotony": monotony,
        "strain": strain
    }


def compute_acwr(daily_loads_history: List[float]) -> float:
    """Feature 35: Acute-to-Chronic Workload Ratio (ACWR)."""
    if len(daily_loads_history) < 28:
        return 1.0
    acute_7d = np.mean(daily_loads_history[-7:])
    chronic_28d = np.mean(daily_loads_history[-28:])
    if chronic_28d == 0:
        return 1.0
    return round(float(acute_7d / chronic_28d), 2)


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
# PILLAR 5: LONGEVIDADE & HEALTHSPAN ENGINE
# ==========================================
def get_vo2_percentile(vo2_max: float, age: int, gender: str = "Male") -> str:
    """Feature 41: VO2 Max Percentile Ranking."""
    if vo2_max >= 58:
        return "Top 2% (Categoria Superior / Elite)"
    elif vo2_max >= 50:
        return "Top 10% (Excelente)"
    elif vo2_max >= 42:
        return "Top 25% (Acima da Média)"
    elif vo2_max >= 35:
        return "Top 50% (Média Populacional)"
    else:
        return "Abaixo da Média (Necessita Intervenção Aeróbica)"


def calculate_biological_age(chronological_age: int, vo2_max: float, rhr: float, hrv: float) -> int:
    """Feature 42: Biological Age Algorithm Breakdown."""
    bio_age = float(chronological_age)
    bio_age -= (vo2_max - 45) * 0.25
    bio_age += (rhr - 50) * 0.20
    bio_age -= (hrv - 50) * 0.10
    return max(18, int(round(bio_age)))


# ==========================================
# PILLAR 6: RACE HUB ENGINE
# ==========================================
def predict_race_time(vo2_max: float, distance_km: float) -> str:
    """Feature 52: A-Race Goal Predictor (Riegel Adjusted)."""
    base_10k_sec = (45.0 / max(vo2_max, 25.0)) * 2500.0
    t2 = base_10k_sec * ((distance_km / 10.0) ** 1.06)
    
    hrs = int(t2 // 3600)
    mins = int((t2 % 3600) // 60)
    secs = int(t2 % 60)
    
    if hrs > 0:
        return f"{hrs}h {mins:02d}m {secs:02d}s"
    return f"{mins:02d}m {secs:02d}s"


def calculate_race_fueling(duration_hours: float, weight_kg: float, temp_c: float = 20.0) -> Dict[str, Any]:
    """Feature 58: Hydration and Fueling Calculator."""
    carbs_per_hour = 60 if duration_hours < 2.0 else 90
    fluid_per_hour_ml = 500 if temp_c < 20 else (750 if temp_c < 28 else 1000)
    sodium_mg_per_hour = 600 if temp_c < 25 else 900

    return {
        "total_carbs_g": int(carbs_per_hour * duration_hours),
        "carbs_per_hour_g": carbs_per_hour,
        "fluid_per_hour_ml": fluid_per_hour_ml,
        "total_fluid_l": round((fluid_per_hour_ml * duration_hours) / 1000.0, 2),
        "sodium_mg_per_hour": sodium_mg_per_hour
    }

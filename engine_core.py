"""
Apex Engine Core (v2.1 - Clean Baseline & Sports Science Fixes)
Deterministic Sports Science Engine with Independent 60-Day Baselines.
"""

import math
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
    """Helper for localized text string lookup."""
    text = TRANSLATIONS.get(lang, TRANSLATIONS["PT"]).get(key, key)
    return text.format(**kwargs) if kwargs else text


# ==========================================
# DATA QUALITY & CALIBRATION ENGINE
# ==========================================
class DataQualityEngine:
    @staticmethod
    def evaluate_sleep_quality(sleep_seconds: float, deep_seconds: Optional[float], 
                               rem_seconds: Optional[float], awake_seconds: Optional[float]) -> Tuple[float, List[str]]:
        reasons = []
        confidence = 1.0

        if not sleep_seconds or sleep_seconds < 18000:  # < 5h
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


# ==========================================
# SPORTS SCIENCE & Z-SCORE ENGINE
# ==========================================
def zscore(val: float, mean: float, sd: float) -> float:
    return (val - mean) / max(sd, 1e-4)


def compute_zscore_readiness(
    hrv_val: float, hrv_mean_60d: float, hrv_sd_60d: float,
    rhr_val: float, rhr_mean_60d: float, rhr_sd_60d: float,
    sleep_score: float, sleep_mean_60d: float, sleep_sd_60d: float,
    acute_load: float, load_mean_60d: float, load_sd_60d: float,
    mood_score: float, mood_mean: float = 3.0, mood_sd: float = 1.0
) -> Dict[str, Any]:
    """
    Calculates readiness ALWAYS using the 60-day baseline parameters,
    ignoring the user's visual chart slider.
    """
    hrv_z = zscore(hrv_val, hrv_mean_60d, hrv_sd_60d)
    rhr_z = -zscore(rhr_val, rhr_mean_60d, rhr_sd_60d)
    sleep_z = zscore(sleep_score, sleep_mean_60d, sleep_sd_60d)
    load_z = -zscore(acute_load, load_mean_60d, load_sd_60d)
    mood_z = zscore(mood_score, mood_mean, mood_sd)

    raw_z_sum = (0.30 * hrv_z) + (0.15 * rhr_z) + (0.20 * sleep_z) + (0.20 * load_z) + (0.15 * mood_z)
    norm_score = int(min(100, max(0, round(50 + (raw_z_sum * 16.6)))))

    waterfall = {
        "VRC Noturno": round(0.30 * hrv_z * 16.6, 1),
        "FC Repouso": round(0.15 * rhr_z * 16.6, 1),
        "Qualidade Sono": round(0.20 * sleep_z * 16.6, 1),
        "Carga Aguda": round(0.20 * load_z * 16.6, 1),
        "Humor / Diário": round(0.15 * mood_z * 16.6, 1),
    }

    return {
        "readiness_score": norm_score,
        "z_sum": round(raw_z_sum, 2),
        "waterfall": waterfall,
        "hrv_z": round(hrv_z, 2),
        "rhr_z": round(rhr_z, 2)
    }


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


def compute_banister_ctl_atl_tsb(daily_loads_history: List[float]) -> Tuple[List[float], List[float], List[float]]:
    """Calculates Banister Impulse-Response Model (CTL 42-day, ATL 7-day, TSB)."""
    ctl_list, atl_list, tsb_list = [], [], []
    ctl, atl = 0.0, 0.0
    
    time_const_ctl = 42.0
    time_const_atl = 7.0

    for load in daily_loads_history:
        ctl = ctl + (load - ctl) * (1.0 / time_const_ctl)
        atl = atl + (load - atl) * (1.0 / time_const_atl)
        tsb = ctl - atl

        ctl_list.append(round(ctl, 1))
        atl_list.append(round(atl, 1))
        tsb_list.append(round(tsb, 1))

    return ctl_list, atl_list, tsb_list


# ==========================================
# STRENGTH ENGINE & EXERCISE DATABASE
# ==========================================
EXERCISE_DATABASE = [
    {
        "id": "sq_back", "name": "Agachamento com Barra (Back Squat)", "pattern": "Squat",
        "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_press", "base_pct_1rm": 0.75
    },
    {
        "id": "leg_press", "name": "Prensa de Pernas (Leg Press)", "pattern": "Squat",
        "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.70
    },
    {
        "id": "rdl_bb", "name": "Peso Morto Romeno (RDL com Barra)", "pattern": "Hinge",
        "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_curl", "base_pct_1rm": 0.70
    },
    {
        "id": "leg_curl", "name": "Flexão de Pernas deitado (Leg Curl)", "pattern": "Hinge",
        "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.65
    },
    {
        "id": "split_squat", "name": "Agachamento Búlgaro (Bulgarian Split Squat)", "pattern": "Unilateral",
        "spinal_load": 3, "equip": "Dumbbells", "alt_low_axial": "leg_ext", "base_pct_1rm": 0.65
    },
    {
        "id": "leg_ext", "name": "Extensão de Pernas (Leg Extension)", "pattern": "Isolation",
        "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.60
    }
]


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

    # Build unique non-duplicated exercise cards
    base_indices = [0, 2] if high_fatigue else [0, 2]

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
        
        # Calculate target weight in kg based on 1RM
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
            "spinal_load": chosen_ex["spinal_load"]
        })

    return {
        "workout": workout,
        "note": reduction_note,
        "readiness_score": readiness_score
    }


def estimate_1rm(weight: float, reps: int) -> float:
    if reps == 1:
        return weight
    return round(weight * (1.0 + (reps / 30.0)), 1)

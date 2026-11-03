"""
Apex Engine Core (v2.0)
Deterministic Sports Science, Data Pipeline, Quality Engine & Autoregulation.
"""

import math
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple


# ==========================================
# TRANSLATION DICTIONARY (i18n)
# ==========================================
TRANSLATIONS = {
    "PT": {
        "today_decision_green": "Dia de Treino Normal: Capacidade Total",
        "today_decision_amber": "Dia Moderado: Reduzir Carga Axial e Intensidade",
        "today_decision_red": "Dia de Recuperação Ativa: Preservar o Sistema Nervoso",
        "today_reason_hrv_low": "VRC Noturno abaixo da tua faixa normal",
        "today_reason_hrv_ok": "VRC Noturno equilibrado dentro da linha de base",
        "today_reason_sleep_low": "Défice de sono acumulado detectado",
        "today_reason_sleep_ok": "Duração e arquitetura de sono adequadas",
        "today_reason_rhr_high": "FC de Repouso elevada (sinal de stress/fadiga)",
        "today_reason_rhr_ok": "FC de Repouso estável",
        "action_start_zone2": "Iniciar Treino Aeróbico Zona 2 (45 min)",
        "action_start_strength": "Iniciar Treino de Força Adaptativo",
        "action_mobility": "Sessão de Mobilidade & Recuperação (20 min)",
        "action_log_diary": "Registar Diário Subjetivo (RPE / Soreness)",
        "calibrating": "Em Calibração (Dia {day}/14)",
        "provisional": "Linha de Base Provisória",
        "personalized": "Modelo Fisiológico Personalizado",
        "confidence_high": "Confiança Elevada dos Dados",
        "confidence_med": "Confiança Média (Dados Parciais)",
        "confidence_low": "Confiança Baixa (Sensor / Falha)",
    },
    "EN": {
        "today_decision_green": "Full Training Day: High Readiness",
        "today_decision_amber": "Moderate Day: Lower Axial Load & Intensity",
        "today_decision_red": "Recovery Day: Protect Nervous System",
        "today_reason_hrv_low": "Overnight HRV below your personal baseline",
        "today_reason_hrv_ok": "Overnight HRV within normal range",
        "today_reason_sleep_low": "Accumulated sleep deficit detected",
        "today_reason_sleep_ok": "Sleep duration and architecture adequate",
        "today_reason_rhr_high": "Elevated Resting HR (stress/fatigue signal)",
        "today_reason_rhr_ok": "Resting HR stable",
        "action_start_zone2": "Start Zone 2 Aerobic Session (45 min)",
        "action_start_strength": "Start Autoregulated Strength Session",
        "action_mobility": "Mobility & Down-regulation Session (20 min)",
        "action_log_diary": "Log Daily Subjective Metrics",
        "calibrating": "Calibrating (Day {day}/14)",
        "provisional": "Provisional Baseline",
        "personalized": "Fully Personalized Model",
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
# PILLAR 1: DATA PIPELINE & QUALITY ENGINE
# ==========================================
class DataQualityEngine:
    """Evaluates sensor telemetry integrity and assigns confidence weights."""

    @staticmethod
    def evaluate_sleep_quality(sleep_seconds: float, deep_seconds: Optional[float], 
                               rem_seconds: Optional[float], awake_seconds: Optional[float]) -> Tuple[float, List[str]]:
        reasons = []
        confidence = 1.0

        if not sleep_seconds or sleep_seconds < 18000:  # < 5 hours
            confidence -= 0.3
            reasons.append("Duracao de sono inferior a 5h")

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
        if days_of_history < 14:
            return "calibrating", f"Calibração: Dia {days_of_history}/14"
        elif days_of_history < 30:
            return "provisional", "Linha de Base Provisória"
        return "personalized", "Modelo Personalizado Ativo"


# ==========================================
# PILLAR 2: SPORTS SCIENCE & AUTOREGULATION
# ==========================================
def zscore(val: float, mean: float, sd: float) -> float:
    """Calculates Z-score deviation safely avoiding division by zero."""
    return (val - mean) / max(sd, 1e-4)


def compute_zscore_readiness(
    hrv_val: float, hrv_mean: float, hrv_sd: float,
    rhr_val: float, rhr_mean: float, rhr_sd: float,
    sleep_score: float, sleep_mean: float, sleep_sd: float,
    acute_load: float, load_mean: float, load_sd: float,
    mood_score: float, mood_mean: float = 3.0, mood_sd: float = 1.0
) -> Dict[str, Any]:
    """
    Computes a defensible, multi-variable readiness score using Z-score deviations
    from the user's personal baseline.
    """
    hrv_z = zscore(hrv_val, hrv_mean, hrv_sd)
    rhr_z = -zscore(rhr_val, rhr_mean, rhr_sd)  # Lower RHR is better
    sleep_z = zscore(sleep_score, sleep_mean, sleep_sd)
    load_z = -zscore(acute_load, load_mean, load_sd)  # Lower acute fatigue is better
    mood_z = zscore(mood_score, mood_mean, mood_sd)

    # Weighted Z-score sum
    raw_z_sum = (0.30 * hrv_z) + (0.15 * rhr_z) + (0.20 * sleep_z) + (0.20 * load_z) + (0.15 * mood_z)

    # Map Z-score (typically -3.0 to +3.0) into 0-100 scale
    norm_score = int(min(100, max(0, round(50 + (raw_z_sum * 16.6)))))

    waterfall = {
        "HRV Contribution": round(0.30 * hrv_z * 16.6, 1),
        "RHR Contribution": round(0.15 * rhr_z * 16.6, 1),
        "Sleep Contribution": round(0.20 * sleep_z * 16.6, 1),
        "Load Contribution": round(0.20 * load_z * 16.6, 1),
        "Mood Contribution": round(0.15 * mood_z * 16.6, 1),
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
    """2x2 Matrix mapping HRV and Resting HR pair signals."""
    hrv_z = zscore(hrv_val, hrv_mean, hrv_sd)
    rhr_z = zscore(rhr_val, rhr_mean, rhr_sd)

    if abs(hrv_z) <= 1.0 and abs(rhr_z) <= 1.0:
        return {"quadrant": "Normal", "status": "Homeostase", "action": "Treino normal dentro do plano."}
    elif hrv_z < -1.0 and rhr_z > 1.0:
        return {"quadrant": "Fadiga / Infeção", "status": "Sympathetic Stress", "action": "Fadiga aguda ou doença. Reduzir carga."}
    elif hrv_z > 1.0 and rhr_z < -1.0:
        return {"quadrant": "Adaptação Ótima", "status": "Parasympathetic High", "action": "Pronto para estímulo de alta intensidade."}
    elif hrv_z > 1.5 and rhr_z > 1.0:
        return {"quadrant": "Atípico / Sobretreino", "status": "Autonomic Disruption", "action": "Sinal atípico (exaustão). Priorizar descanso."}
    elif hrv_z < -1.0 and rhr_z < -1.0:
        return {"quadrant": "Fadiga Parassimpática", "status": "Parasympathetic Saturation", "action": "Fadiga profunda acumulada."}
    else:
        return {"quadrant": "Ligeiro Desvio", "status": "Moderado", "action": "Ajustar volume de treino com prudência."}


def compute_foster_load_metrics(daily_loads_7d: List[float]) -> Dict[str, float]:
    """Computes Foster Monotony and Strain metrics."""
    if not daily_loads_7d or len(daily_loads_7d) < 7:
        return {"weekly_load": 0.0, "monotony": 1.0, "strain": 0.0}

    weekly_load = sum(daily_loads_7d)
    mean_load = weekly_load / 7.0
    
    # Calculate Standard Deviation
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


# ==========================================
# STRENGTH ENGINE & EXERCISE DATABASE
# ==========================================
EXERCISE_DATABASE = [
    {
        "id": "sq_back", "name": "Barbell Back Squat", "pattern": "Squat",
        "spinal_load": 5, "knee_stress": True, "shoulder_stress": False,
        "equip": "Barbell", "alt_low_axial": "leg_press"
    },
    {
        "id": "leg_press", "name": "Sled Leg Press", "pattern": "Squat",
        "spinal_load": 1, "knee_stress": True, "shoulder_stress": False,
        "equip": "Machine", "alt_low_axial": None
    },
    {
        "id": "rdl_bb", "name": "Barbell Romanian Deadlift (RDL)", "pattern": "Hinge",
        "spinal_load": 5, "knee_stress": False, "shoulder_stress": False,
        "equip": "Barbell", "alt_low_axial": "leg_curl"
    },
    {
        "id": "leg_curl", "name": "Lying Leg Curl", "pattern": "Hinge",
        "spinal_load": 1, "knee_stress": False, "shoulder_stress": False,
        "equip": "Machine", "alt_low_axial": None
    },
    {
        "id": "split_squat", "name": "Dumbbell Bulgarian Split Squat", "pattern": "Squat Unilateral",
        "spinal_load": 3, "knee_stress": True, "shoulder_stress": False,
        "equip": "Dumbbells", "alt_low_axial": "leg_ext"
    },
    {
        "id": "leg_ext", "name": "Leg Extension Machine", "pattern": "Squat Isolation",
        "spinal_load": 1, "knee_stress": True, "shoulder_stress": False,
        "equip": "Machine", "alt_low_axial": None
    }
]


def autoregulate_strength_workout(readiness_score: int) -> Dict[str, Any]:
    """
    Substitutes high axial spinal load exercises and adjusts RIR/volume
    based on the daily readiness score.
    """
    workout = []
    reduction_note = ""

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
        reduction_note = "Fadiga elevada: Exercícios de carga na coluna substituídos por máquinas."
        high_fatigue = True

    for ex in EXERCISE_DATABASE[:4]:
        chosen_ex = ex
        substituted = False
        reason = ""

        if high_fatigue and ex["spinal_load"] >= 4:
            # Substitute with lower axial load alternative
            alt_id = ex["alt_low_axial"]
            if alt_id:
                alt_ex = next((e for e in EXERCISE_DATABASE if e["id"] == alt_id), None)
                if alt_ex:
                    chosen_ex = alt_ex
                    substituted = True
                    reason = f"Substituído {ex['name']} (Carga axial {ex['spinal_load']}/5) por {alt_ex['name']} devido a baixa prontidão ({readiness_score}/100)."

        base_sets = 3
        final_sets = max(2, int(round(base_sets * set_multiplier)))

        workout.append({
            "exercise": chosen_ex["name"],
            "pattern": chosen_ex["pattern"],
            "sets": final_sets,
            "reps": "8–10",
            "intensity": intensity_target,
            "substituted": substituted,
            "reason": reason,
            "spinal_load": chosen_ex["spinal_load"]
        })

    return {
        "workout": workout,
        "note": reduction_note,
        "readiness_score": readiness_score
    }


def estimate_1rm(weight: float, reps: int) -> float:
    """Epley formula for 1RM estimation."""
    if reps == 1:
        return weight
    return round(weight * (1.0 + (reps / 30.0)), 1)

"""
Apex Engine Core (v4.1 - Full Features Restored)
"""

import math
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

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

class DataQualityEngine:
    @staticmethod
    def evaluate_sleep_quality(sleep_seconds: float, deep_seconds: Optional[float], 
                               rem_seconds: Optional[float], awake_seconds: Optional[float]) -> Tuple[float, List[str]]:
        reasons = []
        confidence = 1.0
        if not sleep_seconds or sleep_seconds < 18000:
            confidence -= 0.3
            reasons.append("Duração de sono inferior a 5h")
        if sleep_seconds and deep_seconds and (deep_seconds / sleep_seconds) * 100 < 3.0:
            confidence -= 0.2
            reasons.append("Sono Profundo < 3%")
        if sleep_seconds and rem_seconds and (rem_seconds / sleep_seconds) * 100 < 5.0:
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
        return {"status": "Sympathetic Stress", "explanation": f"VRC caiu {abs(delta_pct):.1f}% abaixo da média. Supressão parassimpática expressiva."}
    elif delta_pct < -10:
        return {"status": "Fadiga Moderada", "explanation": f"VRC {abs(delta_pct):.1f}% abaixo da linha de base. Recomenda-se treino aeróbico."}
    elif delta_pct > 15:
        return {"status": "Hiper-Adaptação", "explanation": f"VRC {delta_pct:.1f}% acima da média. Excelente recuperação."}
    else:
        return {"status": "Homeostase", "explanation": "VRC dentro da faixa normal. Seguir plano habitual."}

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

    w_hrv, w_rhr, w_sleep, w_load, w_mood = (0.35, 0.20, 0.25, 0.10, 0.10) if "Longevidade" in user_mode else (0.30, 0.15, 0.20, 0.20, 0.15)
    raw_z_sum = (w_hrv * hrv_z) + (w_rhr * rhr_z) + (w_sleep * sleep_z) + (w_load * load_z) + (w_mood * mood_z)
    norm_score = int(min(100, max(0, round(50 + (raw_z_sum * 16.6)))))

    waterfall = {
        "VRC Noturno": round(w_hrv * hrv_z * 16.6, 1),
        "FC Repouso": round(w_rhr * rhr_z * 16.6, 1),
        "Qualidade Sono": round(w_sleep * sleep_z * 16.6, 1),
        "Carga Aguda": round(w_load * load_z * 16.6, 1),
        "Humor / Diário": round(w_mood * mood_z * 16.6, 1),
    }
    return {"readiness_score": norm_score, "z_sum": round(raw_z_sum, 2), "waterfall": waterfall}

def compute_sleep_debt_7d(sleep_hours_series: List[float], target_sleep_hours: float = 8.0) -> float:
    if not sleep_hours_series: return 0.0
    return round(sum([max(0.0, target_sleep_hours - h) for h in sleep_hours_series[-7:]]), 1)

def calculate_trend_slope(series: List[float]) -> Dict[str, Any]:
    clean_series = [x for x in series if pd.notnull(x)]
    if len(clean_series) < 3: return {"slope": 0.0, "text": "Dados insuficientes"}
    y = np.array(clean_series)
    slope, _ = np.polyfit(np.arange(len(y)), y, 1)
    if slope > 0.3: status = "Adaptação Positiva Exponencial"
    elif slope > 0.05: status = "Adaptação Ligeira / Estável"
    elif slope > -0.3: status = "Fadiga Acumulada Ligeira"
    else: status = "Supressão Autonómica Crítica"
    return {"slope": round(float(slope), 2), "text": status}

EXERCISE_DATABASE = [
    {"id": "sq_back", "name": "Agachamento com Barra (Back Squat)", "pattern": "Squat", "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_press", "base_pct_1rm": 0.75, "active_muscles": "Quadríceps, Glúteo Máximo", "joint_protected": "Coluna Lombar"},
    {"id": "leg_press", "name": "Prensa de Pernas (Leg Press)", "pattern": "Squat", "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.70, "active_muscles": "Quadríceps", "joint_protected": "Coluna Isenta"},
    {"id": "rdl_bb", "name": "Peso Morto Romeno (RDL com Barra)", "pattern": "Hinge", "spinal_load": 5, "equip": "Barbell", "alt_low_axial": "leg_curl", "base_pct_1rm": 0.70, "active_muscles": "Isquiotibiais, Glúteos", "joint_protected": "Eretores da Espinha"},
    {"id": "leg_curl", "name": "Flexão de Pernas Deitado (Leg Curl)", "pattern": "Hinge", "spinal_load": 1, "equip": "Machine", "alt_low_axial": None, "base_pct_1rm": 0.65, "active_muscles": "Isquiotibiais", "joint_protected": "Lombar Isenta"}
]

def calculate_spinal_load_score(workout_exercises: List[Dict[str, Any]]) -> float:
    return round(float(np.mean([ex.get("spinal_load", 1) for ex in workout_exercises])), 1) if workout_exercises else 0.0

def autoregulate_strength_workout(readiness_score: int, user_1rm_dict: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    if user_1rm_dict is None: user_1rm_dict = {"sq_back": 140.0, "rdl_bb": 120.0, "leg_press": 200.0, "leg_curl": 70.0}
    workout = []
    high_fatigue = readiness_score < 45
    for idx in [0, 2]:
        ex = EXERCISE_DATABASE[idx]
        chosen_ex = ex
        substituted, reason = False, ""
        if high_fatigue and ex["spinal_load"] >= 4:
            alt_ex = next((e for e in EXERCISE_DATABASE if e["id"] == ex["alt_low_axial"]), None)
            if alt_ex: chosen_ex, substituted, reason = alt_ex, True, f"Substituído {ex['name']} para proteger a coluna."
        workout.append({
            "id": chosen_ex["id"], "exercise": chosen_ex["name"], "pattern": chosen_ex["pattern"],
            "sets": 2 if high_fatigue else 3, "reps": "8–10", "intensity": "RPE 6-7" if high_fatigue else "RPE 8",
            "target_kg": round(user_1rm_dict.get(chosen_ex["id"], 100.0) * chosen_ex["base_pct_1rm"], 1),
            "substituted": substituted, "reason": reason, "spinal_load": chosen_ex["spinal_load"],
            "active_muscles": chosen_ex["active_muscles"], "joint_protected": chosen_ex["joint_protected"]
        })
    return {"workout": workout, "note": "Sessão adaptada ao teu nível de fadiga atual.", "readiness_score": readiness_score, "spinal_score": calculate_spinal_load_score(workout)}

def estimate_1rm(weight: float, reps: int) -> float: return weight if reps == 1 else round(weight * (1.0 + (reps / 30.0)), 1)
def calculate_srpe(duration_min: float, rpe: float) -> float: return round(duration_min * rpe, 1)

def compute_foster_load_metrics(daily_loads_7d: List[float]) -> Dict[str, float]:
    if not daily_loads_7d or len(daily_loads_7d) < 7: return {"weekly_load": 0.0, "monotony": 1.0, "strain": 0.0}
    wl = sum(daily_loads_7d)
    monotony = round((wl / 7.0) / max(float(np.std(daily_loads_7d)), 1.0), 2)
    return {"weekly_load": round(wl, 1), "monotony": monotony, "strain": round(wl * monotony, 1)}

def compute_acwr(daily_loads_history: List[float]) -> float:
    if len(daily_loads_history) < 28: return 1.0
    return round(float(np.mean(daily_loads_history[-7:])) / max(float(np.mean(daily_loads_history[-28:])), 1.0), 2)

def compute_banister_ctl_atl_tsb(daily_loads_history: List[float], ctl_decay: float = 42.0, atl_decay: float = 7.0) -> Tuple[List[float], List[float], List[float]]:
    ctl_list, atl_list, tsb_list = [], [], []
    ctl, atl = 0.0, 0.0
    for load in daily_loads_history:
        ctl += (load - ctl) * (1.0 / ctl_decay)
        atl += (load - atl) * (1.0 / atl_decay)
        ctl_list.append(round(ctl, 1)); atl_list.append(round(atl, 1)); tsb_list.append(round(ctl - atl, 1))
    return ctl_list, atl_list, tsb_list

def simulate_taper_projection(current_ctl: float, current_atl: float, days_to_race: int = 14, volume_reduction_pct: float = 0.5) -> pd.DataFrame:
    dates = [date.today() + timedelta(days=i) for i in range(days_to_race + 1)]
    ctl, atl, ctl_proj, atl_proj, tsb_proj = current_ctl, current_atl, [], [], []
    maintenance_load = (current_ctl * 0.8) * (1.0 - volume_reduction_pct)
    for i in range(days_to_race + 1):
        daily_load = maintenance_load if i < days_to_race - 2 else 15.0
        ctl += (daily_load - ctl) * (1.0 / 42.0)
        atl += (daily_load - atl) * (1.0 / 7.0)
        ctl_proj.append(round(ctl, 1)); atl_proj.append(round(atl, 1)); tsb_proj.append(round(ctl - atl, 1))
    return pd.DataFrame({"Date": dates, "CTL_Proj": ctl_proj, "ATL_Proj": atl_proj, "TSB_Proj": tsb_proj})

def get_vo2_percentile(vo2_max: float, age: int) -> str:
    if vo2_max >= 58: return "Top 2% (Superior / Elite)"
    elif vo2_max >= 50: return "Top 10% (Excelente)"
    elif vo2_max >= 42: return "Top 25% (Acima da Média)"
    return "Média Populacional"

def calculate_biological_age(chronological_age: int, vo2_max: float, rhr: float, hrv: float) -> int:
    return max(18, int(round(chronological_age - (vo2_max - 45) * 0.25 + (rhr - 50) * 0.20 - (hrv - 50) * 0.10)))

def predict_race_time(vo2_max: float, distance_km: float) -> str:
    t2 = ((45.0 / max(vo2_max, 25.0)) * 2500.0) * ((distance_km / 10.0) ** 1.06)
    return f"{int(t2//3600)}h {int((t2%3600)//60):02d}m {int(t2%60):02d}s" if int(t2//3600) > 0 else f"{int((t2%3600)//60):02d}m {int(t2%60):02d}s"

def calculate_dynamic_sweat_nutrition(weight_kg: float, body_fat_pct: float, gender: str, sport_type: str, duration_hours: float, temp_c: float, humidity_pct: float) -> Dict[str, Any]:
    lean_mass_kg = weight_kg * (1.0 - (body_fat_pct / 100.0))
    base_carbs_hr = 85.0 if "Full Ironman" in sport_type else (75.0 if "Half" in sport_type or "70.3" in sport_type else (65.0 if "Maratona" in sport_type else 50.0))
    final_carbs_hr = min(110.0, max(40.0, base_carbs_hr * (lean_mass_kg / 65.0) * (1.0 if gender == "Masculino" else 0.90)))
    
    thermal_index = temp_c + (0.1 * humidity_pct)
    fluid_multiplier, sodium_mg_hr = (1.4, 1000.0) if thermal_index > 30 else ((1.2, 800.0) if thermal_index > 24 else ((0.85, 500.0) if thermal_index < 12 else (1.0, 650.0)))
    final_fluid_ml_hr = round((weight_kg * 8.0) * fluid_multiplier, 0)
    
    return {
        "lean_mass_kg": round(lean_mass_kg, 1),
        "carbs_hr_g": round(final_carbs_hr, 0),
        "total_carbs_g": round(final_carbs_hr * duration_hours, 0),
        "fluid_hr_ml": final_fluid_ml_hr,
        "total_fluid_l": round((final_fluid_ml_hr * duration_hours) / 1000.0, 2),
        "sodium_hr_mg": sodium_mg_hr,
        "total_sodium_mg": round(sodium_mg_hr * duration_hours, 0),
        "thermal_stress_level": "Elevado ⚠️" if thermal_index > 26 else ("Moderado 🟡" if thermal_index > 18 else "Ideal 🟢")
    }

def generate_pacing_band(target_pace_min_km: float, total_distance_km: float, hr_max: int) -> pd.DataFrame:
    splits = []
    for km in range(1, int(total_distance_km) + 1):
        if km % 5 == 0: gradient, adj, terrain, hr = (3.5, 1.12, "Subida 📈", int(hr_max * 0.88))
        elif km % 7 == 0: gradient, adj, terrain, hr = (-3.0, 0.92, "Descida 📉", int(hr_max * 0.82))
        else: gradient, adj, terrain, hr = (0.0, 1.0, "Plano ➖", int(hr_max * 0.85))
        
        split_pace_sec = (target_pace_min_km * 60.0) * adj
        splits.append({"KM": km, "Terreno": terrain, "Gradiente (%)": gradient, "Ritmo Alvo (Min/KM)": f"{int(split_pace_sec)//60}:{int(split_pace_sec)%60:02d}", "Teto FC (bpm)": hr})
    return pd.DataFrame(splits)

def calculate_carb_loading_protocol(weight_kg: float) -> Dict[str, Any]:
    return {
        "daily_target_g": f"{int(weight_kg * 8.0)}g – {int(weight_kg * 10.0)}g",
        "breakfast": f"{int((weight_kg * 8.0) * 0.30)}g HC (Aveia, Mel, Bananas)",
        "lunch": f"{int((weight_kg * 8.0) * 0.35)}g HC (Arroz, Batata Doce)",
        "snack": f"{int((weight_kg * 8.0) * 0.15)}g HC (Pão, Sumo de Maçã)",
        "dinner": f"{int((weight_kg * 8.0) * 0.20)}g HC (Massa)"
    }

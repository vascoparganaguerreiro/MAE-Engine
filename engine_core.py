"""
Apex Engine Core (v4.0 - Advanced Race Hub & Clinical Autoregulation Engine)
"""

import math
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple


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

        return max(0.1, round(confidence, 2)), reasons

    @staticmethod
    def get_calibration_state(days_of_history: int) -> Tuple[str, str]:
        if days_of_history < 28:
            return "calibrating", f"Calibração: Dia {days_of_history}/28"
        elif days_of_history < 60:
            return "provisional", f"Linha de Base Provisória ({days_of_history}/60 dias)"
        return "personalized", "Linha de Base Sólida (60 Dias)"


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

    return {
        "readiness_score": norm_score,
        "z_sum": round(raw_z_sum, 2)
    }


def compute_sleep_debt_7d(sleep_hours_series: List[float], target_sleep_hours: float = 8.0) -> float:
    if not sleep_hours_series:
        return 0.0
    last_7 = sleep_hours_series[-7:]
    debt = sum([max(0.0, target_sleep_hours - h) for h in last_7])
    return round(debt, 1)


def calculate_trend_slope(series: List[float]) -> Dict[str, Any]:
    if not series or len(series) < 3:
        return {"slope": 0.0, "text": "Dados insuficientes"}
    clean_series = [x for x in series if x is not None and not np.isnan(x)]
    if len(clean_series) < 3:
        return {"slope": 0.0, "text": "Dados insuficientes"}
        
    y = np.array(clean_series)
    x = np.arange(len(y))
    slope, _ = np.polyfit(x, y, 1)
    
    if slope > 0.3:
        status = "Adaptação Positiva Exponencial"
    elif slope > -0.3:
        status = "Adaptação Estável / Controlada"
    else:
        status = "Supressão Autonómica Crítica"
        
    return {"slope": round(float(slope), 2), "text": status}


# ==========================================
# BANISTER LOAD & TAPER ENGINE
# ==========================================
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


def simulate_taper_projection(
    current_ctl: float, 
    current_atl: float, 
    days_to_race: int = 14,
    volume_reduction_pct: float = 0.5
) -> pd.DataFrame:
    """Projeta a subida da Forma (TSB) nos 14 dias anteriores à prova."""
    dates = [date.today() + timedelta(days=i) for i in range(days_to_race + 1)]
    ctl, atl = current_ctl, current_atl
    
    ctl_proj, atl_proj, tsb_proj = [], [], []
    maintenance_load = (current_ctl * 0.8) * (1.0 - volume_reduction_pct)

    for i in range(days_to_race + 1):
        # Redução progressiva até ao dia da prova
        daily_load = maintenance_load if i < days_to_race - 2 else 15.0
        ctl = ctl + (daily_load - ctl) * (1.0 / 42.0)
        atl = atl + (daily_load - atl) * (1.0 / 7.0)
        tsb = ctl - atl

        ctl_proj.append(round(ctl, 1))
        atl_proj.append(round(atl, 1))
        tsb_proj.append(round(tsb, 1))

    return pd.DataFrame({
        "Date": dates,
        "CTL_Proj": ctl_proj,
        "ATL_Proj": atl_proj,
        "TSB_Proj": tsb_proj
    })


# ==========================================
# ADVANCED RACE HUB ENGINES
# ==========================================
def calculate_dynamic_sweat_nutrition(
    weight_kg: float,
    body_fat_pct: float,
    gender: str,
    sport_type: str,
    duration_hours: float,
    temp_c: float,
    humidity_pct: float
) -> Dict[str, Any]:
    """1. Calculadora Dinâmica de Suor & Estresse Térmico."""
    lean_mass_kg = weight_kg * (1.0 - (body_fat_pct / 100.0))

    # Base por Modalidade
    if "Full Ironman" in sport_type:
        base_carbs_hr = 85.0
    elif "Half Ironman" in sport_type or "70.3" in sport_type:
        base_carbs_hr = 75.0
    elif "Maratona" in sport_type:
        base_carbs_hr = 65.0
    else:
        base_carbs_hr = 50.0

    # Ajuste Térmico e Fisiológico
    gender_factor = 1.0 if gender == "Masculino" else 0.90
    mass_factor = lean_mass_kg / 65.0
    
    # Hidratos por hora
    final_carbs_hr = min(110.0, max(40.0, base_carbs_hr * mass_factor * gender_factor))
    
    # Taxa de Suor e Hidratação (mL/h)
    base_fluid_ml_hr = weight_kg * 8.0
    thermal_index = temp_c + (0.1 * humidity_pct)
    
    if thermal_index > 30:  # Calor Intenso
        fluid_multiplier = 1.40
        sodium_mg_hr = 1000.0
    elif thermal_index > 24: # Moderado
        fluid_multiplier = 1.20
        sodium_mg_hr = 800.0
    elif thermal_index < 12: # Frio
        fluid_multiplier = 0.85
        sodium_mg_hr = 500.0
    else:
        fluid_multiplier = 1.0
        sodium_mg_hr = 650.0

    final_fluid_ml_hr = round(base_fluid_ml_hr * fluid_multiplier, 0)
    
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
    """2. Gerador de Pacing Band com GAP por Altimetria."""
    splits = []
    pace_sec = target_pace_min_km * 60.0

    # Terrenos sintéticos de prova
    for km in range(1, int(total_distance_km) + 1):
        if km % 5 == 0:  # Subida
            gradient = 3.5
            adj_factor = 1.12
            terrain = "Subida 📈"
            hr_target = int(hr_max * 0.88)
        elif km % 7 == 0: # Descida
            gradient = -3.0
            adj_factor = 0.92
            terrain = "Descida 📉"
            hr_target = int(hr_max * 0.82)
        else: # Plano
            gradient = 0.0
            adj_factor = 1.0
            terrain = "Plano ➖"
            hr_target = int(hr_max * 0.85)

        split_pace_sec = pace_sec * adj_factor
        m, s = divmod(int(split_pace_sec), 60)
        gap_m, gap_s = divmod(int(pace_sec), 60)

        splits.append({
            "KM": km,
            "Terreno": terrain,
            "Gradiente (%)": gradient,
            "Ritmo Alvo (Min/KM)": f"{m}:{s:02d}",
            "GAP Ajustado": f"{gap_m}:{gap_s:02d}",
            "Teto FC (bpm)": hr_target
        })

    return pd.DataFrame(splits)


def calculate_carb_loading_protocol(weight_kg: float) -> Dict[str, Any]:
    """3. Protocolo de Carbo-Loading de 72h."""
    carbs_daily_min = round(weight_kg * 8.0, 0)
    carbs_daily_max = round(weight_kg * 10.0, 0)

    return {
        "daily_target_g": f"{int(carbs_daily_min)}g – {int(carbs_daily_max)}g",
        "breakfast": f"{int(carbs_daily_min * 0.30)}g HC (Aveia, Mel, Bananas)",
        "lunch": f"{int(carbs_daily_min * 0.35)}g HC (Arroz Branco, Batata Doce)",
        "snack": f"{int(carbs_daily_min * 0.15)}g HC (Pão com Geleia, Sumo de Maçã)",
        "dinner": f"{int(carbs_daily_min * 0.20)}g HC (Massa com Molho de Tomate)"
    }

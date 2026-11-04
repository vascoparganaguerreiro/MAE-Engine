"""Apex Engine calculation layer.

Pure calculations only: no Streamlit, network calls, credentials or persistence.
Missing measurements stay missing; this module never fabricates physiological data.
All scores are coaching heuristics, not validated clinical decision rules.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

Z_TO_POINTS = 16.6
Z_CLIP = 3.0
READINESS_CUTOFFS = (45, 70)

TEXT = {
    "decision_full": "Dia de treino normal: sinais dentro/acima da linha de base",
    "decision_moderate": "Dia moderado: considerar reduzir volume ou intensidade",
    "decision_recovery": "Sinais desfavoráveis: privilegiar recuperação e reavaliar sintomas",
    "decision_unknown": "Dados insuficientes para estimar a prontidão",
}


def t(key: str, **kwargs) -> str:
    value = TEXT.get(key, key)
    return value.format(**kwargs) if kwargs else value


def _series(values: Iterable) -> pd.Series:
    return pd.Series(list(values), dtype="float64")


def _finite(value: Any) -> bool:
    try:
        return value is not None and np.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def zscore(value: float, mean: float, sd: float, sd_floor: float = 1e-3) -> float:
    return (float(value) - float(mean)) / max(float(sd), sd_floor)


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return ""
    user, domain = email.split("@", 1)
    return f"{user[:1]}***@{domain}"


@dataclass(frozen=True)
class Baseline:
    mean: float
    sd: float
    n: int


def compute_baseline(values, window: int = 60, min_n: int = 14, sd_floor: float = 1e-3,
                     exclude_last: bool = True) -> Optional[Baseline]:
    s = _series(values)
    if exclude_last and not s.empty:
        s = s.iloc[:-1]
    s = s.tail(window).dropna()
    if len(s) < min_n:
        return None
    return Baseline(float(s.mean()), float(max(s.std(ddof=1), sd_floor)), int(len(s)))


class DataQualityEngine:
    @staticmethod
    def evaluate_sleep_quality(sleep_seconds: Optional[float], deep_seconds: Optional[float] = None,
                               rem_seconds: Optional[float] = None,
                               awake_seconds: Optional[float] = None) -> Tuple[float, List[str]]:
        reasons: List[str] = []
        conf = 1.0
        if not _finite(sleep_seconds) or float(sleep_seconds) < 5 * 3600:
            conf -= 0.3
            reasons.append("Duração de sono inferior a 5 h ou ausente")
        if _finite(sleep_seconds) and float(sleep_seconds) > 0:
            sleep_seconds = float(sleep_seconds)
            if _finite(deep_seconds) and float(deep_seconds) / sleep_seconds < 0.03:
                conf -= 0.2
                reasons.append("Proporção de sono profundo muito baixa; confirmar sensor")
            if _finite(rem_seconds) and float(rem_seconds) / sleep_seconds < 0.05:
                conf -= 0.2
                reasons.append("Proporção de sono REM muito baixa; confirmar sensor")
            if _finite(awake_seconds) and float(awake_seconds) / (sleep_seconds + float(awake_seconds)) > 0.20:
                conf -= 0.1
                reasons.append("Mais de 20 % da noite registada como acordado")
        return max(0.1, round(conf, 2)), reasons

    @staticmethod
    def get_calibration_state(valid_days: int) -> Tuple[str, str]:
        if valid_days < 14:
            return "insufficient", f"A recolher linha de base: {valid_days}/14 dias válidos"
        if valid_days < 28:
            return "calibrating", f"Linha de base inicial: {valid_days}/28 dias válidos"
        if valid_days < 60:
            return "provisional", f"Linha de base provisória: {valid_days}/60 dias válidos"
        return "personalized", "Linha de base pessoal: 60 dias válidos"

    @staticmethod
    def overall_confidence(baseline_days: int, night_confidence: float,
                           recent_completeness: float, hours_since_sync: Optional[float] = None,
                           is_demo: bool = False) -> Dict[str, Any]:
        score = 0.40 * min(1.0, max(0, baseline_days) / 60.0)
        score += 0.30 * float(np.clip(night_confidence, 0, 1))
        score += 0.30 * float(np.clip(recent_completeness, 0, 1))
        factors = [
            ("Linha de base", f"{baseline_days}/60 dias", baseline_days >= 28),
            ("Qualidade da última noite", f"{round(night_confidence * 100)} %", night_confidence >= 0.8),
            ("Dados recentes", f"{round(recent_completeness * 100)} %", recent_completeness >= 0.7),
        ]
        if hours_since_sync is not None and hours_since_sync > 24:
            score -= 0.10
            factors.append(("Última sincronização", f"há {hours_since_sync:.0f} h", False))
        if is_demo:
            score = min(score, 0.30)
            factors.append(("Origem dos dados", "demonstração", False))
        return {"score": int(round(np.clip(score, 0, 1) * 100)), "factors": factors}


READINESS_WEIGHTS = {
    "performance": {"hrv": 0.30, "rhr": 0.15, "sleep": 0.20, "load": 0.20, "mood": 0.15},
    "longevity": {"hrv": 0.35, "rhr": 0.20, "sleep": 0.25, "load": 0.10, "mood": 0.10},
}
_FLOORS = {"HRV": 0.05, "RHR": 1.0, "SleepScore": 3.0, "ATL": 3.0, "SubjectiveScore": 0.1}


def subjective_score(soreness: Optional[int], stress: Optional[int], mood: Optional[int]) -> Optional[float]:
    """Composite from 1-5 diary scales; higher is better. Returns None if any input is absent."""
    if any(v is None for v in (soreness, stress, mood)):
        return None
    if any(int(v) not in range(1, 6) for v in (soreness, stress, mood)):
        raise ValueError("DOMS, stress and mood must each be between 1 and 5")
    return float((int(mood) + (6 - int(soreness)) + (6 - int(stress))) / 3.0 - 3.0)


def _column_z(df: pd.DataFrame, col: str, i: int, log: bool = False,
              invert: bool = False) -> Optional[float]:
    if col not in df.columns or i < 0 or i >= len(df):
        return None
    s = pd.to_numeric(df[col], errors="coerce").astype("float64")
    if log:
        s = np.log(s.where(s > 0))
    cur = s.iloc[i]
    if pd.isna(cur):
        return None
    base = compute_baseline(s.iloc[:i + 1], window=60, min_n=14,
                            sd_floor=_FLOORS.get(col, 1e-3), exclude_last=True)
    if base is None:
        return None
    val = zscore(float(cur), base.mean, base.sd, _FLOORS.get(col, 1e-3))
    return float(np.clip(-val if invert else val, -Z_CLIP, Z_CLIP))


def zscores_for_day(df: pd.DataFrame, i: int = -1,
                    mood_z: Optional[float] = None) -> Dict[str, Optional[float]]:
    n = len(df)
    if n == 0:
        return {k: None for k in ("hrv", "rhr", "sleep", "load", "mood")}
    i = i if i >= 0 else n + i
    if i < 0 or i >= n:
        raise IndexError("day index outside dataframe")
    return {
        "hrv": _column_z(df, "HRV", i, log=True),
        "rhr": _column_z(df, "RHR", i, invert=True),
        "sleep": _column_z(df, "SleepScore", i),
        "load": _column_z(df, "ATL", i, invert=True),
        "mood": mood_z if mood_z is not None else _column_z(df, "SubjectiveScore", i),
    }


def compute_readiness(zs: Dict[str, Optional[float]], mode: str = "performance") -> Dict[str, Any]:
    weights = READINESS_WEIGHTS["longevity" if "longev" in str(mode).lower() else "performance"]
    available = {k: float(v) for k, v in zs.items() if k in weights and _finite(v)}
    missing = [k for k in weights if k not in available]
    if len(available) < 2:
        return {"score": None, "z_sum": None, "contributions": {k: 0.0 for k in weights},
                "total_points": None, "missing": missing, "coverage": round(sum(weights[k] for k in available), 2)}
    weight_sum = sum(weights[k] for k in available)
    contributions = {k: weights[k] / weight_sum * available[k] * Z_TO_POINTS for k in available}
    total = sum(contributions.values())
    score = int(round(float(np.clip(50.0 + total, 0, 100))))
    return {"score": score, "z_sum": round(total / Z_TO_POINTS, 2),
            "contributions": {k: round(contributions.get(k, 0.0), 1) for k in weights},
            "total_points": round(total, 1), "missing": missing,
            "coverage": round(weight_sum, 2)}


def decision_for(score: Optional[int]) -> Dict[str, str]:
    if score is None:
        return {"tone": "neutral", "cap": "unknown", "headline": t("decision_unknown")}
    low, high = READINESS_CUTOFFS
    if score >= high:
        return {"tone": "green", "cap": "full", "headline": t("decision_full")}
    if score >= low:
        return {"tone": "amber", "cap": "moderate", "headline": t("decision_moderate")}
    return {"tone": "red", "cap": "recovery", "headline": t("decision_recovery")}


def get_hrv_context(current: Optional[float], baseline_mean: Optional[float],
                    baseline_sd: Optional[float] = None) -> Dict[str, Any]:
    if not _finite(current) or not _finite(baseline_mean) or float(baseline_mean) <= 0:
        return {"status": "Sem dados", "delta_pct": None, "delta_ms": None,
                "explanation": "Ainda não há dados suficientes para comparar a VRC com a tua linha de base."}
    delta = float(current) - float(baseline_mean)
    pct = delta / float(baseline_mean) * 100
    if pct < -25:
        status, explanation = "Muito abaixo da linha de base", f"VRC {abs(pct):.0f} % abaixo do normal pessoal. Confirma sono, stress, doença e tendência."
    elif pct < -10:
        status, explanation = "Abaixo da linha de base", f"VRC {abs(pct):.0f} % abaixo do normal pessoal; interpreta em conjunto com outros sinais."
    elif pct > 15:
        status, explanation = "Acima da linha de base", f"VRC {pct:.0f} % acima do normal pessoal; uma VRC alta isolada não prova recuperação."
    else:
        status, explanation = "Dentro da faixa habitual", "VRC dentro da faixa habitual; considera também sintomas e sensação subjetiva."
    return {"status": status, "delta_pct": round(pct, 1), "delta_ms": round(delta, 1),
            "explanation": explanation}


def calculate_trend(series, min_points: int = 7) -> Dict[str, Any]:
    s = _series(series)
    mask = s.notna().to_numpy()
    y = s.to_numpy()[mask]
    x = np.arange(len(s), dtype=float)[mask]
    n = len(y)
    if n < min_points:
        return {"slope": None, "ci_low": None, "ci_high": None, "significant": False,
                "n": n, "total_change": None, "pct_change": None, "direction": "none",
                "text": "Dados insuficientes para avaliar tendência"}
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    dof = n - 2
    sxx = float(((x - x.mean()) ** 2).sum())
    se = math.sqrt(float(resid @ resid) / dof / sxx) if sxx > 0 and dof > 0 else float("inf")
    # Conservative approximation to a 95% t critical value.
    tcrit = 2.0 + 2.5 / max(dof, 1)
    lo, hi = float(slope - tcrit * se), float(slope + tcrit * se)
    significant = bool(lo > 0 or hi < 0)
    total = float(slope * (x[-1] - x[0]))
    mean = float(np.mean(y)) or 1.0
    direction = "down" if slope < 0 else "up"
    if not significant:
        direction, text = "flat", "Sem tendência clara; a variação pode corresponder ao ruído diário"
    elif direction == "down":
        text = "Tendência descendente estatisticamente compatível com declínio"
    else:
        text = "Tendência ascendente estatisticamente compatível com aumento"
    return {"slope": round(float(slope), 2), "ci_low": round(lo, 2), "ci_high": round(hi, 2),
            "significant": significant, "n": int(n), "total_change": round(total, 1),
            "pct_change": round(total / mean * 100, 1), "direction": direction, "text": text}


def drift_alert(trend: Dict[str, Any], series_sd: Optional[float]) -> bool:
    if not _finite(series_sd) or not _finite(trend.get("total_change")):
        return False
    return bool(trend.get("significant") and trend.get("direction") == "down"
                and abs(float(trend["total_change"])) >= 0.5 * max(float(series_sd), 1e-6))


def compute_sleep_debt(hours: Sequence[Optional[float]], target: float = 8.0,
                       nights: int = 7) -> Dict[str, Any]:
    s = _series(hours).tail(nights).dropna()
    if s.empty:
        return {"debt_h": None, "avg_h": None, "nights": 0}
    return {"debt_h": round(float(np.maximum(0.0, target - s).sum()), 1),
            "avg_h": round(float(s.mean()), 1), "nights": int(len(s))}


def calculate_srpe(duration_min: float, rpe: float) -> float:
    if not _finite(duration_min) or not _finite(rpe) or float(duration_min) <= 0 or not 1 <= float(rpe) <= 10:
        raise ValueError("Duration must be positive and session RPE must be 1-10")
    return round(float(duration_min) * float(rpe), 1)


def trimp(duration_min: float, avg_hr: float, hr_rest: float, hr_max: float,
          sex: str = "Masculino") -> float:
    if duration_min <= 0 or hr_max <= hr_rest:
        return 0.0
    x = float(np.clip((avg_hr - hr_rest) / (hr_max - hr_rest), 0, 1))
    k, b = (0.64, 1.92) if sex != "Feminino" else (0.86, 1.67)
    return float(duration_min) * x * k * math.exp(b * x)


def compute_banister(loads: Iterable[float], ctl_tc: float = 42.0, atl_tc: float = 7.0,
                     warmup_days: int = 14) -> Dict[str, List[float]]:
    x = np.asarray(list(loads), dtype=float)
    if x.size == 0:
        return {"ctl": [], "atl": [], "tsb": []}
    if not np.isfinite(x).all():
        raise ValueError("Training load contains missing values; confirm rest days as 0 before calculating")
    if ctl_tc <= 0 or atl_tc <= 0:
        raise ValueError("Time constants must be positive")
    seed = float(np.mean(x[: min(warmup_days, x.size)]))
    a_ctl, a_atl = 1 - math.exp(-1 / ctl_tc), 1 - math.exp(-1 / atl_tc)
    ctl = atl = seed
    ctl_list, atl_list, tsb_list = [], [], []
    for load in x:
        ctl += (load - ctl) * a_ctl
        atl += (load - atl) * a_atl
        ctl_list.append(round(ctl, 1))
        atl_list.append(round(atl, 1))
        tsb_list.append(round(ctl - atl, 1))
    return {"ctl": ctl_list, "atl": atl_list, "tsb": tsb_list}


def add_load_columns(df: pd.DataFrame, ctl_tc: float = 42.0,
                     atl_tc: float = 7.0) -> pd.DataFrame:
    if "DailyLoad" not in df:
        raise ValueError("DailyLoad column is required")
    out = df.copy()
    result = compute_banister(out["DailyLoad"].tolist(), ctl_tc, atl_tc)
    out["CTL"], out["ATL"], out["TSB"] = result["ctl"], result["atl"], result["tsb"]
    return out


def compute_acwr(loads: Sequence[float]) -> Optional[float]:
    x = np.asarray(list(loads), dtype=float)
    if x.size < 28 or not np.isfinite(x[-28:]).all():
        return None
    chronic = float(np.mean(x[-28:]))
    return round(float(np.mean(x[-7:])) / chronic, 2) if chronic > 0 else None


def simulate_taper(ctl: float, atl: float, normal_daily_load: float, days: int = 14,
                   volume_reduction: float = 0.5, start: Optional[date] = None,
                   ctl_tc: float = 42.0, atl_tc: float = 7.0) -> pd.DataFrame:
    """Simple Banister taper scenario; final row represents race morning before race load."""
    if days < 1 or not 0 <= volume_reduction <= 1 or ctl_tc <= 0 or atl_tc <= 0:
        raise ValueError("Invalid taper parameters")
    if min(float(ctl), float(atl), float(normal_daily_load)) < 0:
        raise ValueError("Training load values cannot be negative")
    start = start or date.today()
    a_ctl, a_atl = 1 - math.exp(-1 / ctl_tc), 1 - math.exp(-1 / atl_tc)
    rows = [{"Date": pd.Timestamp(start), "CTL": round(float(ctl), 1),
             "ATL": round(float(atl), 1), "TSB": round(float(ctl - atl), 1)}]
    c, a = float(ctl), float(atl)
    for i in range(days):
        load = normal_daily_load * (0.3 if i == days - 1 else (1.0 - volume_reduction))
        c += (load - c) * a_ctl
        a += (load - a) * a_atl
        rows.append({"Date": pd.Timestamp(start + timedelta(days=i + 1)),
                     "CTL": round(c, 1), "ATL": round(a, 1), "TSB": round(c - a, 1)})
    return pd.DataFrame(rows)


def acwr_zone(value: Optional[float]) -> Tuple[str, str]:
    if value is None:
        return "Sem dados completos (28 dias consecutivos necessários)", "neutral"
    if value < 0.8:
        return "Carga recente inferior à média", "blue"
    if value <= 1.3:
        return "Sem grande diferença entre carga aguda e crónica", "green"
    if value <= 1.5:
        return "Aumento relativo recente: rever contexto", "amber"
    return "Aumento relativo acentuado: rever contexto", "red"


def tsb_zone(tsb: float) -> Tuple[str, str]:
    if tsb > 25:
        return "Transição / carga recente baixa", "amber"
    if tsb >= 5:
        return "TSB positivo", "green"
    if tsb >= -10:
        return "Próximo do equilíbrio", "neutral"
    if tsb >= -30:
        return "TSB negativo", "gold"
    return "TSB muito negativo", "red"


# Strength prescriptions are templates. Exercise selection and spinal stress are heuristics,
# not injury screening or an assessment of an individual's spine.
EXERCISES = [
    dict(id="back_squat", name="Agachamento com barra", pattern="squat", rank=1, spinal=5, rm="back_squat", pct=0.75, groups=["quadriceps", "gluteos"]),
    dict(id="goblet_squat", name="Agachamento goblet", pattern="squat", rank=2, spinal=2, rm=None, pct=None, groups=["quadriceps", "gluteos"]),
    dict(id="leg_press", name="Prensa de pernas", pattern="squat", rank=3, spinal=1, rm="leg_press", pct=0.70, groups=["quadriceps", "gluteos"]),
    dict(id="rdl", name="Peso morto romeno", pattern="hinge", rank=1, spinal=5, rm="rdl", pct=0.70, groups=["isquiotibiais", "gluteos"]),
    dict(id="hip_thrust", name="Hip thrust", pattern="hinge", rank=2, spinal=2, rm=None, pct=None, groups=["gluteos", "isquiotibiais"]),
    dict(id="pull_through", name="Pull-through no cabo", pattern="hinge", rank=3, spinal=2, rm=None, pct=None, groups=["gluteos", "isquiotibiais"]),
    dict(id="leg_curl", name="Flexão de pernas", pattern="hinge", rank=4, spinal=1, rm="leg_curl", pct=0.65, groups=["isquiotibiais"]),
    dict(id="bench", name="Supino com barra", pattern="push", rank=1, spinal=1, rm="bench", pct=0.72, groups=["peito", "ombros", "triceps"]),
    dict(id="db_press", name="Supino com halteres", pattern="push", rank=2, spinal=1, rm=None, pct=None, groups=["peito", "ombros", "triceps"]),
    dict(id="machine_press", name="Press de peito em máquina", pattern="push", rank=3, spinal=1, rm=None, pct=None, groups=["peito", "triceps"]),
    dict(id="bb_row", name="Remada com barra", pattern="pull", rank=1, spinal=4, rm="row", pct=0.70, groups=["costas", "biceps"]),
    dict(id="cs_row", name="Remada apoiada no peito", pattern="pull", rank=2, spinal=1, rm=None, pct=None, groups=["costas", "biceps"]),
    dict(id="pulldown", name="Puxada na polia alta", pattern="pull", rank=3, spinal=1, rm=None, pct=None, groups=["costas", "biceps"]),
    dict(id="pallof", name="Pallof press", pattern="core", rank=1, spinal=1, rm=None, pct=None, groups=["core"]),
]
TIERS = {
    "full": dict(patterns=["squat", "hinge", "push", "pull", "core"], max_spinal=5, sets=3, rir=2, pct_delta=0.0),
    "moderate": dict(patterns=["squat", "hinge", "push", "pull", "core"], max_spinal=3, sets=3, rir=3, pct_delta=-0.05),
    "recovery": dict(patterns=["squat", "hinge", "pull", "core"], max_spinal=2, sets=2, rir=4, pct_delta=-0.10),
}


def strength_candidates(cap: str, flags: Sequence[str] = ()) -> Dict[str, List[Dict[str, Any]]]:
    tier = TIERS.get(cap, TIERS["moderate"])
    stress_keys = set(flags)
    return {
        pattern: sorted([e for e in EXERCISES if e["pattern"] == pattern and e["spinal"] <= tier["max_spinal"]
                         and not stress_keys.intersection(e.get("stress", {}))], key=lambda e: e["rank"])
        for pattern in tier["patterns"]
        if any(e["pattern"] == pattern and e["spinal"] <= tier["max_spinal"] for e in EXERCISES)
    }


def build_strength_session(cap: str, one_rm: Optional[Dict[str, float]] = None,
                           flags: Sequence[str] = (), choices: Optional[Dict[str, str]] = None,
                           time_min: Optional[float] = None) -> Dict[str, Any]:
    cap = cap if cap in TIERS else "moderate"
    tier = TIERS[cap]
    one_rm = one_rm or {}
    choices = choices or {}
    candidates = strength_candidates(cap, flags)
    full = strength_candidates("full", flags)
    exercises = []
    for pattern, pool in candidates.items():
        if not pool:
            continue
        chosen = next((e for e in pool if e["id"] == choices.get(pattern)), pool[0])
        primary = full.get(pattern, [chosen])[0]
        max_value = one_rm.get(chosen["rm"]) if chosen.get("rm") else None
        kg = round(float(max_value) * (float(chosen["pct"]) + tier["pct_delta"]) / 2.5) * 2.5 if _finite(max_value) and chosen.get("pct") else None
        exercises.append({"id": chosen["id"], "name": chosen["name"], "pattern": pattern,
                          "sets": tier["sets"], "reps": "8-10" if pattern != "core" else "10-12",
                          "rir": tier["rir"], "kg": kg, "spinal": chosen["spinal"],
                          "groups": chosen["groups"], "swapped": chosen["id"] != primary["id"],
                          "alternatives": [e["id"] for e in pool if e["id"] != chosen["id"]]})
    def duration(exs):
        return 8 + sum(1 + e["sets"] * 2.75 for e in exs)
    trimmed = []
    if time_min and time_min > 0:
        while len(exercises) > 2 and duration(exercises) > time_min:
            trimmed.append(exercises.pop()["name"])
    spinal = round(float(np.mean([e["spinal"] for e in exercises])), 1) if exercises else 0.0
    return {"cap": cap, "exercises": exercises, "duration_min": round(duration(exercises)),
            "spinal_score": spinal, "trimmed": trimmed}


def estimate_1rm(weight: float, reps: int) -> float:
    if weight <= 0 or reps <= 0 or reps > 12:
        raise ValueError("Weight must be positive and repetitions must be between 1 and 12")
    return round(float(weight), 1) if reps == 1 else round(float(weight) * (1 + reps / 30), 1)


def progression_suggestion(last_kg: float, avg_rir: float, target_rir: float) -> float:
    gap = float(avg_rir) - float(target_rir)
    pct = 0.05 if gap >= 2 else 0.025 if gap >= 1 else -0.05 if gap <= -2 else -0.025 if gap <= -1 else 0.0
    return round(float(last_kg) * (1 + pct) / 2.5) * 2.5


# Approximate population categories only; not a validated clinical or age-prediction model.
def vo2_category(vo2: float, age: int, sex: str = "Masculino") -> Tuple[str, int]:
    if vo2 <= 0 or age <= 0:
        raise ValueError("VO2max and age must be positive")
    bands = {"Masculino": [(29, 55), (39, 53), (49, 50), (59, 46), (200, 42)],
             "Feminino": [(29, 49), (39, 47), (49, 44), (59, 40), (200, 36)]}
    thresholds = bands.get(sex, bands["Masculino"])
    superior = next(v for age_limit, v in thresholds if age <= age_limit)
    if vo2 >= superior:
        return "Superior (estimativa)", 40
    if vo2 >= superior - 5:
        return "Excelente (estimativa)", 32
    if vo2 >= superior - 10:
        return "Bom (estimativa)", 24
    if vo2 >= superior - 15:
        return "Razoável (estimativa)", 14
    return "Baixo (estimativa)", 6


def healthspan_score(vo2_points: Optional[int], rhr: Optional[float], sleep_sd_h: Optional[float],
                     weekly_active_min: Optional[float]) -> Dict[str, Any]:
    """Experimental transparent composite; do not interpret as biological age or disease risk."""
    parts: Dict[str, Tuple[float, float]] = {}
    if vo2_points is not None:
        parts["Capacidade aeróbica (VO2max)"] = (float(vo2_points), 40.0)
    if rhr is not None and _finite(rhr):
        pts = 20 if rhr <= 50 else 15 if rhr <= 60 else 8 if rhr <= 70 else 3
        parts["FC de repouso"] = (float(pts), 20.0)
    if sleep_sd_h is not None and _finite(sleep_sd_h):
        pts = 20 if sleep_sd_h <= 0.5 else 14 if sleep_sd_h <= 1.0 else 8 if sleep_sd_h <= 1.5 else 3
        parts["Regularidade do sono"] = (float(pts), 20.0)
    if weekly_active_min is not None and _finite(weekly_active_min):
        parts["Atividade registada"] = (min(1.0, max(0.0, weekly_active_min) / 150.0) * 20.0, 20.0)
    if not parts:
        return {"score": None, "parts": {}}
    total = sum(p for p, _ in parts.values()) / sum(m for _, m in parts.values()) * 100
    return {"score": int(round(total)), "parts": {k: (round(p, 1), m) for k, (p, m) in parts.items()}}


BIOMARKERS = {
    "apob": dict(label="ApoB", unit="mg/dL", low=None, high=90.0),
    "ldl": dict(label="LDL-C", unit="mg/dL", low=None, high=115.0),
    "hba1c": dict(label="HbA1c", unit="%", low=None, high=5.7),
    "glucose": dict(label="Glicose em jejum", unit="mg/dL", low=70.0, high=99.0),
    "hscrp": dict(label="hs-CRP", unit="mg/L", low=None, high=3.0),
    "ferritin": dict(label="Ferritina", unit="ng/mL", low=30.0, high=300.0),
    "vitd": dict(label="Vitamina D (25-OH)", unit="ng/mL", low=30.0, high=100.0),
    "tsh": dict(label="TSH", unit="mIU/L", low=0.4, high=4.0),
}


def evaluate_biomarker(key: str, value: float, low: Optional[float] = None,
                       high: Optional[float] = None) -> Dict[str, str]:
    if key not in BIOMARKERS:
        raise KeyError(f"Unknown biomarker: {key}")
    if not _finite(value):
        raise ValueError("Biomarker value must be numeric")
    ref = BIOMARKERS[key]
    lo = ref["low"] if low is None else low
    hi = ref["high"] if high is None else high
    if lo is not None and value < lo:
        return {"status": "low", "tone": "amber", "text": "Abaixo do limite de comparação configurado"}
    if hi is not None and value > hi:
        return {"status": "high", "tone": "amber", "text": "Acima do limite de comparação configurado"}
    return {"status": "ok", "tone": "green", "text": "Dentro dos limites de comparação configurados"}


def parse_hms(text: str) -> Optional[float]:
    try:
        parts = [float(p) for p in str(text).strip().split(":")]
    except ValueError:
        return None
    if not 1 <= len(parts) <= 3 or any(p < 0 for p in parts):
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds if seconds > 0 else None


def format_hms(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def parse_pace(text: str) -> Optional[float]:
    if ":" not in str(text):
        return None
    value = parse_hms(text)
    return value if value is not None and 120 <= value <= 1200 else None


def generate_pacing_band(target_pace_s: float, distance_km: float, hr_max: Optional[float] = None,
                         gradients: Optional[Sequence[float]] = None,
                         progressive_finish: bool = True) -> pd.DataFrame:
    if target_pace_s <= 0 or distance_km <= 0:
        raise ValueError("Pace and distance must be positive")
    n = int(math.ceil(distance_km))
    distances = [1.0] * (n - 1) + [distance_km - (n - 1)]
    factors = []
    for i in range(n):
        factor = 1.03 if i == 0 else 1.0
        if progressive_finish and n >= 6 and i >= n - 2:
            factor *= 0.98
        grade = gradients[i] if gradients is not None and i < len(gradients) else 0.0
        factor *= (1 + 0.03 * grade) if grade > 0 else (1 + 0.018 * grade)
        factors.append(factor)
    mean_factor = sum(f * d for f, d in zip(factors, distances)) / sum(distances)
    rows, cumulative = [], 0.0
    for i, (factor, dist) in enumerate(zip(factors, distances)):
        pace = target_pace_s * factor / mean_factor
        cumulative += pace * dist
        row = {"Km": i + 1 if dist == 1.0 else round(distance_km, 2),
               "Ritmo previsto": format_hms(pace), "Tempo acumulado": format_hms(cumulative)}
        if hr_max is not None and hr_max > 0:
            fraction = 0.82 if (i + 1) / n <= 0.25 else 0.88 if (i + 1) / n <= 0.8 else 0.92
            row["Teto FC ilustrativo (bpm)"] = int(hr_max * fraction)
        rows.append(row)
    return pd.DataFrame(rows)


def estimate_wbgt(temp_c: float, humidity_pct: float) -> float:
    """Approximate outdoor heat index proxy; not a measured WBGT value."""
    e = humidity_pct / 100.0 * 6.105 * math.exp(17.27 * temp_c / (237.7 + temp_c))
    return 0.567 * temp_c + 0.393 * e + 3.94


def heat_category(wbgt: float) -> Tuple[str, str]:
    if wbgt < 18:
        return "Baixo", "green"
    if wbgt < 23:
        return "Moderado", "amber"
    if wbgt < 28:
        return "Alto", "red"
    return "Muito alto", "red"


def calculate_race_nutrition(duration_h: float, temp_c: float, humidity_pct: float,
                             sweat_rate_ml_h: Optional[float] = None,
                             salty_sweater: bool = False) -> Dict[str, Any]:
    if duration_h <= 0 or not 0 <= humidity_pct <= 100:
        raise ValueError("Duration must be positive and humidity must be 0-100 %")
    wbgt = estimate_wbgt(temp_c, humidity_pct)
    category, tone = heat_category(wbgt)
    carbs = (0, 0) if duration_h < 0.75 else (0, 30) if duration_h < 1 else (30, 60) if duration_h <= 2.5 else (60, 90)
    if sweat_rate_ml_h and sweat_rate_ml_h > 0:
        fluid = (int(np.clip(0.5 * sweat_rate_ml_h, 250, 800)), int(np.clip(0.8 * sweat_rate_ml_h, 250, 800)))
    else:
        fluid = {"Baixo": (300, 500), "Moderado": (400, 650), "Alto": (500, 750), "Muito alto": (500, 800)}[category]
    sodium = (500, 900) if salty_sweater else (300, 600)
    if duration_h < 1:
        fluid, sodium = (0, 0), (0, 0)
    warnings = [
        "Valores gerais, não uma prescrição individual. Personaliza a estratégia em treino e considera a taxa de suor.",
        "Evita beber acima das perdas; o excesso de líquidos pode causar hiponatremia.",
        "O cálculo de calor é apenas aproximado e não substitui WBGT medido nem orientações locais.",
    ]
    if category in ("Alto", "Muito alto"):
        warnings.append("Calor elevado: considera reduzir o ritmo/exposição e interrompe perante sintomas de doença pelo calor.")
    return {"duration_h": duration_h, "wbgt": round(wbgt, 1), "heat": category, "tone": tone,
            "carbs_g_h": carbs, "fluid_ml_h": fluid, "sodium_mg_h": sodium, "warnings": warnings}


def carb_loading_protocol(weight_kg: float, event_duration_h: float) -> Dict[str, Any]:
    if weight_kg <= 0 or event_duration_h <= 0:
        raise ValueError("Weight and event duration must be positive")
    needed = event_duration_h >= 1.5
    lo, hi = (8.0, 12.0) if needed else (6.0, 8.0)
    return {"needed": needed, "g_per_kg": (lo, hi),
            "daily_g": (round(weight_kg * lo), round(weight_kg * hi)),
            "note": "Estratégia geral; ensaiar previamente e individualizar tolerância gastrointestinal." if needed
                    else "Para esforços curtos não é geralmente necessário um protocolo de sobrecarga."}


def shoe_status(km_used: float, max_km: float) -> Tuple[str, str, float]:
    if max_km <= 0 or km_used < 0:
        raise ValueError("Shoe kilometres must be non-negative and limit must be positive")
    fraction = km_used / max_km
    if fraction < 0.5:
        return "Uso baixo", "green", fraction
    if fraction < 0.8:
        return "Uso intermédio", "green", fraction
    if fraction < 1.0:
        return "Perto do limite definido", "amber", fraction
    return "Limite definido atingido/excedido", "red", fraction


RED_FLAGS = [
    r"dor (no|de) peito", r"dor tor[aá]cica", r"chest pain", r"desmai", r"perda de consci[eê]ncia",
    r"faint", r"falta de ar (s[uú]bita|intensa|grave)", r"shortness of breath", r"palpita[cç][oõ]es.{0,30}(desmai|dor|falta de ar)",
    r"suic[ií]d", r"quero morrer", r"automutila", r"self[- ]harm", r"fraqueza s[uú]bita", r"face desca[ií]da",
]
RED_FLAG_MESSAGE = (
    "O que descreves pode exigir avaliação urgente. Interrompe o exercício. Se houver dor torácica, desmaio, "
    "falta de ar intensa, sinais neurológicos súbitos ou perigo imediato, liga 112. O Apex não consegue avaliar sintomas."
)
COACH_SYSTEM_PROMPT = (
    "És o Coach IA do Apex: assistente de treino e bem-estar, não um profissional de saúde. Responde em português europeu, "
    "de forma concreta e prudente. Usa apenas os dados presentes no contexto; identifica valores ausentes e a origem dos dados. "
    "Não diagnostiques, não prescrevas medicamentos nem suplementos terapêuticos, não recomendes treino através de dor ou sintomas. "
    "Não trates prontidão, ACWR, healthspan score ou estimativas de relógio como decisões clínicas ou previsões de lesão. "
    "Se a pergunta mencionar sintomas de alarme, aconselha a parar o exercício e procurar ajuda apropriada."
)


def red_flag_check(text: str) -> Optional[str]:
    low = str(text).lower()
    return RED_FLAG_MESSAGE if any(re.search(pattern, low) for pattern in RED_FLAGS) else None


def build_coach_context(facts: Dict[str, Any]) -> str:
    return json.dumps(facts, ensure_ascii=False, default=str, indent=2)

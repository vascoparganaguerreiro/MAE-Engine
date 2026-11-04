"""
Apex Engine Core v5.0
=====================
Pure calculation layer: no Streamlit, no network, no hidden randomness
(the only random function is the explicit demo-data generator).
Everything in this file is covered by test_engine.py.

Conventions
-----------
* Series are lists / pandas Series ordered oldest -> newest; the last item is "today".
* Missing values are None / NaN and are never invented.
* "UA" = arbitrary units of training load (Garmin load, TRIMP or session-RPE).
* Wellness information only. Nothing here is a medical diagnosis.
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

# ════════════════════════════════════════════════════════════════
# 0. Shared helpers
# ════════════════════════════════════════════════════════════════
Z_TO_POINTS = 16.6          # 1 weighted z-score point = 16.6 readiness points
Z_CLIP = 3.0                # outliers cannot dominate the score
READINESS_CUTOFFS = (45, 70)  # <45 recovery | 45-69 moderate | >=70 full

TEXT = {
    "decision_full": "Dia de treino normal: capacidade total",
    "decision_moderate": "Dia moderado: reduzir carga axial e intensidade",
    "decision_recovery": "Dia de recuperação ativa: preservar o sistema nervoso",
    "decision_unknown": "Dados insuficientes para uma decisão fiável",
}


def t(key: str, **kwargs) -> str:
    text = TEXT.get(key, key)
    return text.format(**kwargs) if kwargs else text


def _series(values: Iterable) -> pd.Series:
    return pd.Series(list(values), dtype="float64")


def zscore(value: float, mean: float, sd: float, sd_floor: float = 1e-3) -> float:
    return (value - mean) / max(sd, sd_floor)


def mask_email(email: str) -> str:
    """v***@gmail.com - safe to show in the UI."""
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
    """Personal baseline. Today is excluded so a value is never compared with itself.
    Returns None until at least `min_n` valid days exist (no fake baselines)."""
    s = _series(values)
    if exclude_last and len(s) > 0:
        s = s.iloc[:-1]
    s = s.tail(window).dropna()
    if len(s) < min_n:
        return None
    return Baseline(float(s.mean()), float(max(s.std(ddof=1), sd_floor)), int(len(s)))


# ════════════════════════════════════════════════════════════════
# 1. Data quality & calibration
# ════════════════════════════════════════════════════════════════
class DataQualityEngine:
    @staticmethod
    def evaluate_sleep_quality(sleep_seconds: Optional[float], deep_seconds: Optional[float] = None,
                               rem_seconds: Optional[float] = None,
                               awake_seconds: Optional[float] = None) -> Tuple[float, List[str]]:
        """Confidence 0.1-1.0 that a night of sleep data is trustworthy, plus reasons."""
        reasons: List[str] = []
        conf = 1.0
        if not sleep_seconds or sleep_seconds < 5 * 3600:
            conf -= 0.3
            reasons.append("Duração de sono inferior a 5 h (relógio possivelmente tirado a meio da noite)")
        if sleep_seconds:
            if deep_seconds is not None and deep_seconds / sleep_seconds < 0.03:
                conf -= 0.2
                reasons.append("Sono profundo < 3 % (verifica o sensor)")
            if rem_seconds is not None and rem_seconds / sleep_seconds < 0.05:
                conf -= 0.2
                reasons.append("Sono REM < 5 % (possível erro do sensor)")
            if awake_seconds is not None and awake_seconds / (sleep_seconds + awake_seconds) > 0.20:
                conf -= 0.1
                reasons.append("Mais de 20 % da noite acordado")
        return max(0.1, round(conf, 2)), reasons

    @staticmethod
    def get_calibration_state(days_of_history: int) -> Tuple[str, str]:
        if days_of_history < 28:
            return "calibrating", f"A calibrar: dia {days_of_history}/28"
        if days_of_history < 60:
            return "provisional", f"Linha de base provisória ({days_of_history}/60 dias)"
        return "personalized", "Linha de base sólida (60 dias)"

    @staticmethod
    def overall_confidence(baseline_days: int, night_confidence: float, recent_completeness: float,
                           hours_since_sync: Optional[float] = None, is_demo: bool = False) -> Dict[str, Any]:
        """Single 0-100 confidence figure with the factors behind it (shown in the UI popover)."""
        base = min(1.0, baseline_days / 60.0)
        score = 0.40 * base + 0.30 * night_confidence + 0.30 * recent_completeness
        factors = [
            ("Linha de base", f"{baseline_days}/60 dias", baseline_days >= 28),
            ("Qualidade da última noite", f"{round(night_confidence * 100)} %", night_confidence >= 0.8),
            ("Dados dos últimos 7 dias", f"{round(recent_completeness * 100)} %", recent_completeness >= 0.7),
        ]
        if hours_since_sync is not None:
            stale = hours_since_sync > 24
            if stale:
                score -= 0.10
            factors.append(("Última sincronização", f"há {hours_since_sync:.0f} h", not stale))
        if is_demo:
            score = min(score, 0.30)
            factors.append(("Origem dos dados", "demonstração", False))
        return {"score": int(round(max(0.0, min(1.0, score)) * 100)), "factors": factors}


# ════════════════════════════════════════════════════════════════
# 2. Readiness (z-scores against YOUR baseline) and the daily decision
# ════════════════════════════════════════════════════════════════
READINESS_WEIGHTS = {
    "performance": {"hrv": 0.30, "rhr": 0.15, "sleep": 0.20, "load": 0.20, "mood": 0.15},
    "longevity": {"hrv": 0.35, "rhr": 0.20, "sleep": 0.25, "load": 0.10, "mood": 0.10},
}
FACTOR_LABELS = {"hrv": "VRC noturno", "rhr": "FC repouso", "sleep": "Qualidade do sono",
                 "load": "Carga aguda", "mood": "Humor e diário"}
_FLOORS = {"HRV": 0.05, "RHR": 1.0, "SleepScore": 3.0, "ATL": 3.0}


def subjective_z(soreness: int, stress: int, mood: int) -> float:
    """Daily check-in (1-5 each). Higher soreness/stress is worse, higher mood is better."""
    composite = (mood + (6 - soreness) + (6 - stress)) / 3.0
    return float(np.clip(composite - 3.0, -Z_CLIP, Z_CLIP))


def zscores_for_day(df: pd.DataFrame, i: int = -1, mood_z: Optional[float] = None) -> Dict[str, Optional[float]]:
    """z-scores for row i using ONLY earlier rows as baseline (60 d, min 14 valid days).
    Sign convention: positive = better than your normal, for every factor."""
    n = len(df)
    i = i if i >= 0 else n + i
    sub = df.iloc[: i + 1]

    def z(col: str, log: bool, invert: bool) -> Optional[float]:
        if col not in sub:
            return None
        s = sub[col].astype("float64")
        if log:
            s = np.log(s.where(s > 0))
        cur = s.iloc[-1]
        if pd.isna(cur):
            return None
        floor = _FLOORS[col]
        base = compute_baseline(s, 60, 14, floor, exclude_last=True)
        if base is None:
            return None
        val = zscore(float(cur), base.mean, base.sd, floor)
        val = -val if invert else val
        return float(np.clip(val, -Z_CLIP, Z_CLIP))

    return {"hrv": z("HRV", True, False), "rhr": z("RHR", False, True),
            "sleep": z("SleepScore", False, False), "load": z("ATL", False, True),
            "mood": mood_z}


def compute_readiness(zs: Dict[str, Optional[float]], mode: str = "performance") -> Dict[str, Any]:
    """Readiness 0-100. Missing inputs are excluded and the remaining weights re-normalised,
    so absent data never silently pulls the score up or down. Needs >= 2 inputs."""
    w = READINESS_WEIGHTS["longevity" if "longev" in mode.lower() else "performance"]
    avail = {k: float(v) for k, v in zs.items() if k in w and v is not None}
    missing = [k for k in w if k not in avail]
    if len(avail) < 2:
        return {"score": None, "z_sum": None, "contributions": {k: 0.0 for k in w},
                "total_points": 0.0, "missing": list(w), "coverage": 0.0}
    wsum = sum(w[k] for k in avail)
    contrib = {k: (w[k] / wsum) * avail[k] * Z_TO_POINTS for k in avail}
    total = sum(contrib.values())
    score = int(round(min(100.0, max(0.0, 50.0 + total))))
    return {"score": score, "z_sum": round(total / Z_TO_POINTS, 2),
            "contributions": {k: round(contrib.get(k, 0.0), 1) for k in w},
            "total_points": round(total, 1), "missing": missing, "coverage": round(wsum, 2)}


def decision_for(score: Optional[int]) -> Dict[str, str]:
    """ONE source of truth for the daily tier. The strength engine and Today both read this."""
    if score is None:
        return {"tone": "neutral", "cap": "unknown", "headline": t("decision_unknown")}
    low, high = READINESS_CUTOFFS
    if score >= high:
        return {"tone": "green", "cap": "full", "headline": t("decision_full")}
    if score >= low:
        return {"tone": "amber", "cap": "moderate", "headline": t("decision_moderate")}
    return {"tone": "red", "cap": "recovery", "headline": t("decision_recovery")}


def readiness_history(df: pd.DataFrame, days: int = 7, mode: str = "performance") -> List[Dict[str, Any]]:
    out = []
    for k in range(days, 0, -1):
        i = len(df) - k
        if i < 0:
            continue
        r = compute_readiness(zscores_for_day(df, i), mode)
        out.append({"Date": df["Date"].iloc[i], "score": r["score"]})
    return out


def get_hrv_context(current: float, baseline_mean: float, baseline_sd: Optional[float] = None) -> Dict[str, Any]:
    if baseline_mean is None or baseline_mean <= 0 or current is None or pd.isna(current):
        return {"status": "Sem dados", "delta_pct": None, "delta_ms": None,
                "explanation": "A recolher dados para definir a tua linha de base."}
    delta_ms = current - baseline_mean
    pct = delta_ms / baseline_mean * 100
    if pct < -25:
        status, txt = "Stress fisiológico elevado", f"VRC {abs(pct):.0f} % abaixo do teu normal: recuperação claramente incompleta."
    elif pct < -10:
        status, txt = "Fadiga moderada", f"VRC {abs(pct):.0f} % abaixo da tua linha de base: prefere trabalho aeróbico leve."
    elif pct > 15:
        status, txt = "Recuperação acima do normal", f"VRC {pct:.0f} % acima da tua média."
    else:
        status, txt = "Dentro do normal", "VRC dentro da tua faixa habitual."
    return {"status": status, "delta_pct": round(pct, 1), "delta_ms": round(delta_ms, 1), "explanation": txt}


def autonomic_quadrant(hrv_z: Optional[float], rhr_z: Optional[float], dead_zone: float = 0.5) -> Dict[str, str]:
    """Read HRV and resting HR as a pair. Both z-scores use 'positive = better' (RHR already inverted)."""
    if hrv_z is None or rhr_z is None:
        return {"label": "Sem dados", "tone": "neutral", "text": "Faltam dados de VRC ou FC de repouso."}
    h_low, h_high = hrv_z <= -dead_zone, hrv_z >= dead_zone
    r_bad, r_good = rhr_z <= -dead_zone, rhr_z >= dead_zone
    if h_low and r_bad:
        return {"label": "Fadiga", "tone": "red",
                "text": "VRC em baixo e FC de repouso em cima: padrão típico de recuperação incompleta ou doença a surgir."}
    if h_high and r_good:
        return {"label": "Adaptação", "tone": "green", "text": "VRC em alta e FC de repouso em baixo: boa recuperação."}
    if h_low and r_good:
        return {"label": "Ambíguo", "tone": "amber",
                "text": "VRC em baixo com FC de repouso baixa: observa a tendência e o teu diário antes de decidir."}
    if h_high and r_bad:
        return {"label": "Misto", "tone": "amber", "text": "VRC em alta mas FC de repouso elevada: confirma o sono e o stress."}
    return {"label": "Normal", "tone": "neutral", "text": "Ambos os sinais dentro da tua faixa habitual."}


# ════════════════════════════════════════════════════════════════
# 3. Trends (with statistical significance) and sleep debt
# ════════════════════════════════════════════════════════════════
def calculate_trend(series, min_points: int = 7) -> Dict[str, Any]:
    """OLS slope per day with a 95 % confidence interval. A trend is only called real when the
    interval excludes zero, otherwise it is normal day-to-day noise."""
    s = _series(series)
    mask = s.notna().to_numpy()
    y = s.to_numpy()[mask]
    x = np.arange(len(s), dtype=float)[mask]
    n = len(y)
    if n < min_points:
        return {"slope": 0.0, "ci_low": 0.0, "ci_high": 0.0, "significant": False, "n": n,
                "total_change": 0.0, "pct_change": 0.0, "direction": "none", "text": "Dados insuficientes"}
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    dof = n - 2
    sxx = float(((x - x.mean()) ** 2).sum())
    se = math.sqrt(float(resid @ resid) / dof / sxx) if sxx > 0 and dof > 0 else float("inf")
    tcrit = 1.96 + 2.4 / dof                      # close to the t-distribution for dof >= 5
    lo, hi = float(slope - tcrit * se), float(slope + tcrit * se)
    significant = lo > 0 or hi < 0
    total = float(slope * (x[-1] - x[0]))
    mean = float(np.mean(y)) or 1.0
    direction = "down" if slope < 0 else "up"
    if not significant:
        text, direction = "Sem tendência clara (dentro do ruído normal)", "flat"
    elif direction == "down":
        text = "Tendência descendente significativa"
    else:
        text = "Tendência ascendente significativa"
    return {"slope": round(float(slope), 2), "ci_low": round(lo, 2), "ci_high": round(hi, 2),
            "significant": bool(significant), "n": int(n), "total_change": round(total, 1),
            "pct_change": round(total / mean * 100, 1), "direction": direction, "text": text}


def drift_alert(trend: Dict[str, Any], series_sd: float) -> bool:
    """Alert only for a significant decline that is also practically relevant (>= 0.5 SD overall)."""
    return bool(trend["significant"] and trend["direction"] == "down"
                and abs(trend["total_change"]) >= 0.5 * max(series_sd, 1e-6))


def compute_sleep_debt(hours: Sequence[Optional[float]], target: float = 8.0, nights: int = 7) -> Dict[str, Any]:
    s = _series(hours).tail(nights).dropna()
    if s.empty:
        return {"debt_h": None, "avg_h": None, "nights": 0}
    return {"debt_h": round(float(np.maximum(0.0, target - s).sum()), 1),
            "avg_h": round(float(s.mean()), 1), "nights": int(len(s))}


# ════════════════════════════════════════════════════════════════
# 4. Training load: sources, Banister, ACWR, Foster
# ════════════════════════════════════════════════════════════════
def trimp(duration_min: float, avg_hr: float, hr_rest: float, hr_max: float, sex: str = "Masculino") -> float:
    """Banister TRIMP (heart-rate based load)."""
    if hr_max <= hr_rest or duration_min <= 0:
        return 0.0
    x = float(np.clip((avg_hr - hr_rest) / (hr_max - hr_rest), 0.0, 1.0))
    k, b = (0.64, 1.92) if sex != "Feminino" else (0.86, 1.67)
    return duration_min * x * k * math.exp(b * x)


def calculate_srpe(duration_min: float, rpe: float) -> float:
    return round(float(duration_min) * float(rpe), 1)


def daily_load_from_activities(activities: Sequence[Dict[str, Any]], hr_rest: float = 50.0,
                               hr_max: float = 190.0, sex: str = "Masculino") -> pd.DataFrame:
    """Aggregate activities into daily load (UA) and active minutes.
    Priority per activity: device training load -> TRIMP from average HR -> none."""
    rows: Dict[pd.Timestamp, List[float]] = {}
    for a in activities:
        d = pd.Timestamp(a["date"]).normalize()
        dur = float(a.get("duration_min") or 0.0)
        if a.get("training_load"):
            load = float(a["training_load"])
        elif a.get("avg_hr"):
            load = trimp(dur, float(a["avg_hr"]), hr_rest, hr_max, sex)
        else:
            load = 0.0
        acc = rows.setdefault(d, [0.0, 0.0])
        acc[0] += load
        acc[1] += dur
    if not rows:
        return pd.DataFrame({"Date": pd.to_datetime([]), "DailyLoad": [], "Minutes": []})
    out = pd.DataFrame([{"Date": d, "DailyLoad": round(v[0], 1), "Minutes": round(v[1], 1)} for d, v in rows.items()])
    return out.sort_values("Date").reset_index(drop=True)


def attach_activity_loads(df: pd.DataFrame, loads: pd.DataFrame) -> pd.DataFrame:
    out = df.drop(columns=[c for c in ("DailyLoad", "Minutes") if c in df], errors="ignore").copy()
    out = out.merge(loads, on="Date", how="left")
    out["DailyLoad"] = out["DailyLoad"].fillna(0.0)
    out["Minutes"] = out["Minutes"].fillna(0.0)
    return out


def merge_manual_loads(df: pd.DataFrame, manual: Dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    if "DailyLoad" not in out:
        out["DailyLoad"] = 0.0
    keys = out["Date"].dt.strftime("%Y-%m-%d")
    for iso, ua in manual.items():
        out.loc[keys == iso, "DailyLoad"] = out.loc[keys == iso, "DailyLoad"].fillna(0.0) + float(ua)
    return out


def compute_banister(loads: Iterable[float], ctl_tc: float = 42.0, atl_tc: float = 7.0,
                     warmup_days: int = 14) -> Dict[str, List[float]]:
    """CTL/ATL/TSB with exponential weighting. The model is seeded with the mean of the first
    `warmup_days` instead of 0 so a short history does not under-estimate fitness.
    Missing days count as rest. TSB = CTL - ATL (same day)."""
    x = np.nan_to_num(np.asarray(list(loads), dtype=float), nan=0.0)
    if x.size == 0:
        return {"ctl": [], "atl": [], "tsb": []}
    seed = float(np.mean(x[: min(warmup_days, x.size)]))
    a_c, a_a = 1 - math.exp(-1 / ctl_tc), 1 - math.exp(-1 / atl_tc)
    ctl = atl = seed
    c_l, a_l, t_l = [], [], []
    for load in x:
        ctl += (load - ctl) * a_c
        atl += (load - atl) * a_a
        c_l.append(round(ctl, 1))
        a_l.append(round(atl, 1))
        t_l.append(round(ctl - atl, 1))
    return {"ctl": c_l, "atl": a_l, "tsb": t_l}


def add_load_columns(df: pd.DataFrame, ctl_tc: float = 42.0, atl_tc: float = 7.0) -> pd.DataFrame:
    out = df.copy()
    b = compute_banister(out["DailyLoad"].tolist(), ctl_tc, atl_tc)
    out["CTL"], out["ATL"], out["TSB"] = b["ctl"], b["atl"], b["tsb"]
    return out


def tsb_zone(tsb: float) -> Tuple[str, str]:
    if tsb > 25:
        return "Transição (a perder forma)", "amber"
    if tsb >= 5:
        return "Fresco (polimento)", "green"
    if tsb >= -10:
        return "Neutro", "neutral"
    if tsb >= -30:
        return "Carga produtiva", "gold"
    return "Sobrecarga elevada", "red"


def compute_acwr(loads: Sequence[float]) -> Optional[float]:
    """Rolling 7-day mean / 28-day mean. None when fewer than 28 days (never a fake 1.0).
    Context signal only: the evidence for predicting injury from this ratio is debated."""
    x = np.nan_to_num(np.asarray(list(loads), dtype=float), nan=0.0)
    if x.size < 28:
        return None
    chronic = float(np.mean(x[-28:]))
    return round(float(np.mean(x[-7:])) / chronic, 2) if chronic > 0 else None


def acwr_zone(v: Optional[float]) -> Tuple[str, str]:
    if v is None:
        return "Sem dados (precisa de 28 dias)", "neutral"
    if v < 0.8:
        return "Carga recente baixa", "blue"
    if v <= 1.3:
        return "Zona estável", "green"
    if v <= 1.5:
        return "Subida rápida: atenção", "amber"
    return "Subida muito rápida", "red"


def compute_foster_metrics(last7: Sequence[float]) -> Optional[Dict[str, float]]:
    x = np.nan_to_num(np.asarray(list(last7), dtype=float), nan=0.0)
    if x.size < 7:
        return None
    x = x[-7:]
    wl, sd = float(x.sum()), float(np.std(x))
    mono = 0.0 if wl == 0 else min(10.0, (wl / 7.0) / max(sd, 1e-6))
    return {"weekly_load": round(wl, 1), "monotony": round(mono, 2), "strain": round(wl * mono, 1)}


def monotony_zone(m: float) -> Tuple[str, str]:
    if m >= 2.0:
        return "Semana demasiado uniforme", "red"
    if m >= 1.5:
        return "Variar mais os dias", "amber"
    return "Boa variação", "green"


def ramp_rate(ctl: Sequence[float], days: int = 7) -> Optional[float]:
    return round(ctl[-1] - ctl[-1 - days], 1) if len(ctl) > days else None


# ════════════════════════════════════════════════════════════════
# 5. Strength engine
# ════════════════════════════════════════════════════════════════
# stress = heuristic 0-5 joint stress. It is a planning aid, not a clinical assessment.
EXERCISES: List[Dict[str, Any]] = [
    dict(id="back_squat", name="Agachamento com barra", pattern="squat", rank=1, spinal=5, rm="back_squat", pct=0.75,
         groups=["quadriceps", "gluteos"], stress=dict(knee=3, low_back=4, shoulder=1)),
    dict(id="goblet_squat", name="Agachamento goblet", pattern="squat", rank=2, spinal=2, rm=None, pct=None,
         groups=["quadriceps", "gluteos"], stress=dict(knee=3, low_back=2, shoulder=0)),
    dict(id="leg_press", name="Prensa de pernas", pattern="squat", rank=3, spinal=1, rm="leg_press", pct=0.70,
         groups=["quadriceps", "gluteos"], stress=dict(knee=3, low_back=1, shoulder=0)),
    dict(id="rdl", name="Peso morto romeno com barra", pattern="hinge", rank=1, spinal=5, rm="rdl", pct=0.70,
         groups=["isquiotibiais", "gluteos"], stress=dict(knee=1, low_back=4, shoulder=0)),
    dict(id="hip_thrust", name="Elevação de anca (hip thrust)", pattern="hinge", rank=2, spinal=2, rm=None, pct=None,
         groups=["gluteos", "isquiotibiais"], stress=dict(knee=1, low_back=1, shoulder=0)),
    dict(id="pull_through", name="Pull-through no cabo", pattern="hinge", rank=3, spinal=2, rm=None, pct=None,
         groups=["gluteos", "isquiotibiais"], stress=dict(knee=0, low_back=1, shoulder=0)),
    dict(id="leg_curl", name="Flexão de pernas deitado", pattern="hinge", rank=4, spinal=1, rm="leg_curl", pct=0.65,
         groups=["isquiotibiais"], stress=dict(knee=1, low_back=0, shoulder=0)),
    dict(id="bench", name="Supino com barra", pattern="push", rank=1, spinal=1, rm="bench", pct=0.72,
         groups=["peito", "ombros", "triceps"], stress=dict(knee=0, low_back=0, shoulder=3)),
    dict(id="db_press", name="Supino com halteres", pattern="push", rank=2, spinal=1, rm=None, pct=None,
         groups=["peito", "ombros", "triceps"], stress=dict(knee=0, low_back=0, shoulder=2)),
    dict(id="machine_press", name="Press de peito em máquina", pattern="push", rank=3, spinal=1, rm=None, pct=None,
         groups=["peito", "triceps"], stress=dict(knee=0, low_back=0, shoulder=1)),
    dict(id="bb_row", name="Remada com barra", pattern="pull", rank=1, spinal=4, rm="row", pct=0.70,
         groups=["costas", "biceps"], stress=dict(knee=0, low_back=3, shoulder=1)),
    dict(id="cs_row", name="Remada apoiada no peito", pattern="pull", rank=2, spinal=1, rm=None, pct=None,
         groups=["costas", "biceps"], stress=dict(knee=0, low_back=0, shoulder=1)),
    dict(id="pulldown", name="Puxada na polia alta", pattern="pull", rank=3, spinal=1, rm=None, pct=None,
         groups=["costas", "biceps"], stress=dict(knee=0, low_back=0, shoulder=1)),
    dict(id="pallof", name="Pallof press", pattern="core", rank=1, spinal=1, rm=None, pct=None,
         groups=["core"], stress=dict(knee=0, low_back=0, shoulder=0)),
]
PATTERN_LABELS = {"squat": "Agachamento", "hinge": "Dobradiça da anca", "push": "Empurrar",
                  "pull": "Puxar", "core": "Core"}
MUSCLE_LABELS = {"quadriceps": "Quadríceps", "gluteos": "Glúteos", "isquiotibiais": "Isquiotibiais",
                 "peito": "Peito", "ombros": "Ombros", "triceps": "Tríceps", "costas": "Costas",
                 "biceps": "Bíceps", "core": "Core"}
TIERS = {  # cap -> template
    "full": dict(patterns=["squat", "hinge", "push", "pull", "core"], max_spinal=5, sets=3, rir=2, pct_delta=0.0),
    "moderate": dict(patterns=["squat", "hinge", "push", "pull", "core"], max_spinal=3, sets=3, rir=3, pct_delta=-0.05),
    "recovery": dict(patterns=["squat", "hinge", "pull"], max_spinal=2, sets=2, rir=4, pct_delta=-0.10),
}
DEFAULT_ONE_RM = {"back_squat": 140.0, "rdl": 120.0, "leg_press": 200.0, "leg_curl": 70.0, "bench": 100.0, "row": 90.0}
WEEKLY_SET_TARGET = (10, 20)


def _round_to(x: float, step: float = 2.5) -> float:
    return round(round(x / step) * step, 2)


def strength_candidates(cap: str, flags: Sequence[str] = ()) -> Dict[str, List[Dict[str, Any]]]:
    """Ranked exercises per movement pattern that respect the tier's spinal-load cap and injury flags."""
    tier = TIERS["moderate" if cap == "unknown" else cap]
    out: Dict[str, List[Dict[str, Any]]] = {}
    for pat in tier["patterns"]:
        pool = [e for e in EXERCISES if e["pattern"] == pat and e["spinal"] <= tier["max_spinal"]
                and all(e["stress"].get(f, 0) < 3 for f in flags)]
        pool.sort(key=lambda e: e["rank"])
        if pool:
            out[pat] = pool
    return out


def build_strength_session(cap: str, one_rm: Optional[Dict[str, float]] = None, flags: Sequence[str] = (),
                           choices: Optional[Dict[str, str]] = None, time_min: Optional[float] = None) -> Dict[str, Any]:
    one_rm = {**DEFAULT_ONE_RM, **(one_rm or {})}
    choices = choices or {}
    cap = "moderate" if cap == "unknown" else cap
    tier = TIERS[cap]
    cands = strength_candidates(cap, flags)
    full_cands = strength_candidates("full", flags)
    exercises: List[Dict[str, Any]] = []
    for pat, pool in cands.items():
        chosen = next((e for e in pool if e["id"] == choices.get(pat)), pool[0])
        primary = full_cands.get(pat, [chosen])[0]
        rm = one_rm.get(chosen["rm"]) if chosen["rm"] else None
        kg = _round_to(rm * (chosen["pct"] + tier["pct_delta"])) if rm and chosen["pct"] else None
        swapped = chosen["id"] != primary["id"]
        why = (f"Substituído {primary['name'].lower()} (carga axial {primary['spinal']}/5) por {chosen['name'].lower()} "
               f"({chosen['spinal']}/5): mesmo padrão de movimento, menos carga na coluna."
               if swapped else "Exercício principal do padrão.")
        exercises.append({"id": chosen["id"], "name": chosen["name"], "pattern": pat, "sets": tier["sets"],
                          "reps": "8-10" if pat != "core" else "10-12", "rir": tier["rir"], "rpe": 10 - tier["rir"],
                          "kg": kg, "spinal": chosen["spinal"], "groups": chosen["groups"], "swapped": swapped,
                          "why": why, "alternatives": [e["id"] for e in pool if e["id"] != chosen["id"]]})

    def duration(exs):
        return 8 + sum(1 + e["sets"] * 2.75 for e in exs)

    trimmed: List[str] = []
    if time_min:
        while len(exercises) > 2 and duration(exercises) > time_min:
            trimmed.append(exercises.pop()["name"])
    spinal = round(float(np.mean([e["spinal"] for e in exercises])), 1) if exercises else 0.0
    return {"cap": cap, "exercises": exercises, "duration_min": round(duration(exercises)), "spinal_score": spinal,
            "trimmed": trimmed}


def estimate_1rm(weight: float, reps: int) -> float:
    """Epley. Most reliable up to ~10 reps."""
    if reps <= 0:
        raise ValueError("reps must be positive")
    return round(float(weight), 1) if reps == 1 else round(weight * (1.0 + reps / 30.0), 1)


def progression_suggestion(last_kg: float, avg_rir: float, target_rir: float) -> float:
    """Next-session load from how hard the last one really was (reps in reserve vs target)."""
    gap = avg_rir - target_rir
    if gap >= 2:
        pct = 0.05
    elif gap >= 1:
        pct = 0.025
    elif gap <= -2:
        pct = -0.05
    elif gap <= -1:
        pct = -0.025
    else:
        pct = 0.0
    return _round_to(last_kg * (1 + pct))


def weekly_set_volume(log: Sequence[Dict[str, Any]], today: date, days: int = 7) -> Dict[str, int]:
    start = today - timedelta(days=days - 1)
    vol: Dict[str, int] = {}
    for entry in log:
        d = date.fromisoformat(entry["date"])
        if start <= d <= today:
            for ex in entry.get("exercises", []):
                for g in ex.get("groups", []):
                    vol[g] = vol.get(g, 0) + int(ex.get("sets_done", 0))
    return vol


def e1rm_history(log: Sequence[Dict[str, Any]], exercise_id: str) -> List[Tuple[str, float]]:
    pts = []
    for entry in log:
        for ex in entry.get("exercises", []):
            if ex["id"] == exercise_id and ex.get("best_e1rm"):
                pts.append((entry["date"], float(ex["best_e1rm"])))
    return sorted(pts)


# ════════════════════════════════════════════════════════════════
# 6. Healthspan (transparent score, no "biological age")
# ════════════════════════════════════════════════════════════════
def vo2_category(vo2: float, age: int, sex: str = "Masculino") -> Tuple[str, int]:
    """APPROXIMATE age/sex bands. Replace with a validated table (e.g. FRIEND registry) before launch."""
    sup = {"Masculino": [(29, 55), (39, 53), (49, 50), (59, 46), (200, 42)],
           "Feminino": [(29, 49), (39, 47), (49, 44), (59, 40), (200, 36)]}[sex if sex in ("Masculino", "Feminino") else "Masculino"]
    sup_min = next(v for a, v in sup if age <= a)
    if vo2 >= sup_min:
        return "Superior", 40
    if vo2 >= sup_min - 5:
        return "Excelente", 32
    if vo2 >= sup_min - 10:
        return "Bom", 24
    if vo2 >= sup_min - 15:
        return "Razoável", 14
    return "Baixo", 6


def healthspan_score(vo2_points: Optional[int], rhr: Optional[float], sleep_sd_h: Optional[float],
                     weekly_active_min: Optional[float]) -> Dict[str, Any]:
    parts: Dict[str, Tuple[float, float]] = {}   # name -> (points, max)
    if vo2_points is not None:
        parts["Capacidade aeróbica (VO2máx)"] = (float(vo2_points), 40.0)
    if rhr is not None:
        pts = 20 if rhr <= 50 else 15 if rhr <= 60 else 8 if rhr <= 70 else 3
        parts["FC de repouso"] = (float(pts), 20.0)
    if sleep_sd_h is not None:
        pts = 20 if sleep_sd_h <= 0.5 else 14 if sleep_sd_h <= 1.0 else 8 if sleep_sd_h <= 1.5 else 3
        parts["Regularidade do sono"] = (float(pts), 20.0)
    if weekly_active_min is not None:
        parts["Atividade semanal (meta OMS 150 min)"] = (min(1.0, weekly_active_min / 150.0) * 20.0, 20.0)
    if not parts:
        return {"score": None, "parts": {}}
    total = sum(p for p, _ in parts.values()) / sum(m for _, m in parts.values()) * 100
    return {"score": int(round(total)), "parts": {k: (round(p, 1), m) for k, (p, m) in parts.items()}}


BIOMARKERS: Dict[str, Dict[str, Any]] = {
    "apob": dict(label="ApoB", unit="mg/dL", low=None, high=90.0),
    "ldl": dict(label="LDL-C", unit="mg/dL", low=None, high=115.0),
    "hba1c": dict(label="HbA1c", unit="%", low=None, high=5.7),
    "glucose": dict(label="Glicose em jejum", unit="mg/dL", low=70.0, high=99.0),
    "hscrp": dict(label="hs-CRP", unit="mg/L", low=None, high=3.0),
    "ferritin": dict(label="Ferritina", unit="ng/mL", low=30.0, high=300.0),
    "vitd": dict(label="Vitamina D (25-OH)", unit="ng/mL", low=30.0, high=100.0),
    "tsh": dict(label="TSH", unit="mIU/L", low=0.4, high=4.0),
}


def evaluate_biomarker(key: str, value: float, low: Optional[float] = None, high: Optional[float] = None) -> Dict[str, str]:
    """Compare to a reference interval (generic defaults; labs differ, so the user can override)."""
    ref = BIOMARKERS[key]
    lo = ref["low"] if low is None else low
    hi = ref["high"] if high is None else high
    if lo is not None and value < lo:
        return {"status": "low", "tone": "amber", "text": "Abaixo do intervalo de referência"}
    if hi is not None and value > hi:
        return {"status": "high", "tone": "amber", "text": "Acima do intervalo de referência"}
    return {"status": "ok", "tone": "green", "text": "Dentro do intervalo de referência"}


# ════════════════════════════════════════════════════════════════
# 7. Race planning: prediction, phases, taper, pacing
# ════════════════════════════════════════════════════════════════
def parse_hms(text: str) -> Optional[float]:
    """'1:28:15' | '28:15' | '40' -> seconds."""
    try:
        parts = [float(p) for p in str(text).strip().split(":")]
    except ValueError:
        return None
    if not parts or len(parts) > 3 or any(p < 0 for p in parts):
        return None
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec if sec > 0 else None


def format_hms(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def parse_pace(text: str) -> Optional[float]:
    """'4:15' -> 255 s/km. Rejects decimals-as-minutes confusion by requiring m:ss."""
    if ":" not in str(text):
        return None
    sec = parse_hms(text)
    return sec if sec and 120 <= sec <= 1200 else None


def _vdot_cost(v_m_min: float) -> float:
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min ** 2


def _vdot_fraction(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_performance(distance_m: float, time_s: float) -> float:
    """Daniels/Gilbert VDOT from a recent race or hard time trial."""
    t_min = time_s / 60.0
    return _vdot_cost(distance_m / t_min) / _vdot_fraction(t_min)


def predict_time_from_vdot(vdot: float, distance_m: float) -> float:
    lo, hi = distance_m / 8.0, distance_m / 1.0   # seconds (8 m/s ... 1 m/s)
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot_from_performance(distance_m, mid) > vdot:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def predict_time_riegel(known_km: float, known_s: float, target_km: float, exponent: float = 1.06) -> float:
    return known_s * (target_km / known_km) ** exponent


def training_phases(weeks_to_race: int) -> List[Dict[str, Any]]:
    w = max(0, int(weeks_to_race))
    if w == 0:
        return [{"phase": "Semana da prova", "weeks": 0}]
    taper = 2 if w >= 4 else 1 if w >= 2 else 0
    peak = 3 if w >= 12 else 2 if w >= 8 else 0
    rest = w - taper - peak
    build = round(rest * 0.4)
    base = rest - build
    plan = [("Base", base), ("Construção", build), ("Pico", peak), ("Taper", taper)]
    return [{"phase": n, "weeks": k} for n, k in plan if k > 0]


def simulate_taper(ctl: float, atl: float, normal_daily_load: float, days: int = 14,
                   volume_reduction: float = 0.5, start: Optional[date] = None,
                   ctl_tc: float = 42.0, atl_tc: float = 7.0) -> pd.DataFrame:
    """Predicted CTL/ATL/TSB through a taper. The last row is race MORNING (race load excluded)."""
    start = start or date.today()
    a_c, a_a = 1 - math.exp(-1 / ctl_tc), 1 - math.exp(-1 / atl_tc)
    rows = []
    c, a = ctl, atl
    rows.append({"Date": pd.Timestamp(start), "CTL": round(c, 1), "ATL": round(a, 1), "TSB": round(c - a, 1)})
    for i in range(days):
        load = normal_daily_load * (0.3 if i == days - 1 else (1.0 - volume_reduction))
        c += (load - c) * a_c
        a += (load - a) * a_a
        rows.append({"Date": pd.Timestamp(start + timedelta(days=i + 1)), "CTL": round(c, 1),
                     "ATL": round(a, 1), "TSB": round(c - a, 1)})
    return pd.DataFrame(rows)


def taper_scenarios(ctl: float, atl: float, normal_daily_load: float, days: int = 14,
                    reductions: Sequence[float] = (0.3, 0.4, 0.5, 0.6)) -> pd.DataFrame:
    out = []
    for r in reductions:
        tsb = float(simulate_taper(ctl, atl, normal_daily_load, days, r)["TSB"].iloc[-1])
        out.append({"reduction": r, "race_tsb": round(tsb, 1), "in_target": 5 <= tsb <= 25})
    return pd.DataFrame(out)


def generate_pacing_band(target_pace_s: float, distance_km: float, hr_max: float,
                         gradients: Optional[Sequence[float]] = None, progressive_finish: bool = True) -> pd.DataFrame:
    """Per-km splits whose total time equals target pace x distance exactly.
    Slightly conservative first km, optional faster final 2 km, optional per-km gradients (%).
    Gradient adjustment is an approximation (~3 % per +1 % grade uphill, ~1.8 % per -1 % downhill)."""
    n = int(math.ceil(distance_km))
    dists = [1.0] * (n - 1) + [distance_km - (n - 1)]
    factors = []
    for i in range(n):
        f = 1.0
        if i == 0:
            f *= 1.03
        if progressive_finish and n >= 6 and i >= n - 2:
            f *= 0.98
        g = (gradients[i] if gradients is not None and i < len(gradients) else 0.0)
        f *= (1 + 0.03 * g) if g > 0 else (1 + 0.018 * g)
        factors.append(f)
    mean_f = sum(f * d for f, d in zip(factors, dists)) / sum(dists)
    rows, cum = [], 0.0
    for i, (f, d) in enumerate(zip(factors, dists)):
        pace = target_pace_s * f / mean_f
        cum += pace * d
        frac = (i + 1) / n
        ceiling = 0.82 if frac <= 0.25 else 0.88 if frac <= 0.8 else 0.92
        rows.append({"Km": i + 1 if d == 1.0 else f"{distance_km:.1f}", "Ritmo": format_hms(pace),
                     "Tempo acumulado": format_hms(cum), "Teto FC (bpm)": int(hr_max * ceiling),
                     "_pace_s": pace, "_dist": d})
    return pd.DataFrame(rows)


# ── heat, hydration, fuelling ──
def estimate_wbgt(temp_c: float, humidity_pct: float) -> float:
    """Approximate WBGT (Australian BoM formula, assumes moderate sun and light wind)."""
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


def calculate_sweat_rate(pre_kg: float, post_kg: float, fluid_ml: float, minutes: float) -> Optional[float]:
    """mL/h from a nude-weight test: ((pre - post) x 1000 + fluid drunk) / hours."""
    if minutes <= 0:
        return None
    return round(((pre_kg - post_kg) * 1000.0 + fluid_ml) / (minutes / 60.0), 0)


def calculate_race_nutrition(duration_h: float, temp_c: float, humidity_pct: float,
                             sweat_rate_ml_h: Optional[float] = None, salty_sweater: bool = False) -> Dict[str, Any]:
    """Ranges, not single numbers. General guidance only; individual needs vary."""
    wbgt = estimate_wbgt(temp_c, humidity_pct)
    cat, tone = heat_category(wbgt)
    if duration_h < 0.75:
        carbs = (0, 0)
    elif duration_h < 1.0:
        carbs = (0, 30)
    elif duration_h <= 2.5:
        carbs = (30, 60)
    else:
        carbs = (60, 90)
    if sweat_rate_ml_h and sweat_rate_ml_h > 0:
        fluid = (int(np.clip(0.5 * sweat_rate_ml_h, 250, 800)), int(np.clip(0.8 * sweat_rate_ml_h, 250, 800)))
    else:
        fluid = {"Baixo": (300, 500), "Moderado": (400, 650), "Alto": (500, 750), "Muito alto": (500, 800)}[cat]
    if duration_h < 1.0:
        fluid, sodium = (0, 0), (0, 0)
    else:
        sodium = (500, 900) if salty_sweater else (300, 600)
    warnings = ["Bebe de acordo com a sede e nunca acima da tua taxa de suor: beber em excesso aumenta o risco de hiponatremia.",
                "Se tens hipertensão ou tomas medicação, fala com o teu médico antes de aumentar o sódio."]
    if cat in ("Alto", "Muito alto"):
        warnings.append("Calor elevado: ajusta o ritmo, protege-te do sol e evita estreias de estratégia no dia da prova.")
    return {"duration_h": duration_h, "wbgt": round(wbgt, 1), "heat": cat, "tone": tone,
            "carbs_g_h": carbs, "fluid_ml_h": fluid, "sodium_mg_h": sodium,
            "total_carbs_g": (round(carbs[0] * duration_h), round(carbs[1] * duration_h)),
            "total_fluid_l": (round(fluid[0] * duration_h / 1000, 1), round(fluid[1] * duration_h / 1000, 1)),
            "total_sodium_mg": (round(sodium[0] * duration_h), round(sodium[1] * duration_h)),
            "warnings": warnings}


def carb_loading_protocol(weight_kg: float, event_duration_h: float) -> Dict[str, Any]:
    """Carbohydrate loading only makes sense for efforts longer than ~90 min."""
    needed = event_duration_h >= 1.5
    lo, hi = (8.0, 12.0) if needed else (6.0, 8.0)
    daily = weight_kg * lo
    return {"needed": needed, "g_per_kg": (lo, hi),
            "daily_g": (round(weight_kg * lo), round(weight_kg * hi)),
            "meals": {"Pequeno-almoço": round(daily * 0.30), "Almoço": round(daily * 0.35),
                      "Lanche": round(daily * 0.15), "Jantar": round(daily * 0.20)},
            "note": ("Sobrecarga de HC nas 24-48 h antes da prova." if needed
                     else "Prova curta: não é preciso protocolo de sobrecarga, basta uma alimentação rica em hidratos.")}


def shoe_status(km_used: float, max_km: float) -> Tuple[str, str, float]:
    frac = km_used / max_km if max_km > 0 else 1.0
    if frac < 0.5:
        return "Excelente", "green", frac
    if frac < 0.8:
        return "Bom", "green", frac
    if frac < 1.0:
        return "Atenção: perto do limite", "amber", frac
    return "Substituir", "red", frac


# ════════════════════════════════════════════════════════════════
# 8. AI coach safety layer
# ════════════════════════════════════════════════════════════════
RED_FLAGS = [r"dor (no|de) peito", r"dor tor[aá]cica", r"chest pain", r"desmai", r"perda de consci[eê]ncia",
             r"faint", r"falta de ar (s[uú]bita|intensa)", r"shortness of breath", r"palpita[cç][oõ]es",
             r"suic[ií]d", r"quero morrer", r"automutila", r"self[- ]harm", r"vis[aã]o turva"]
RED_FLAG_MESSAGE = ("Isto pode ser um sinal de alerta de saúde. Para o treino e procura ajuda médica de imediato; "
                    "em caso de perigo imediato liga 112. Eu não consigo avaliar sintomas.")
COACH_SYSTEM_PROMPT = (
    "És o Coach IA do Apex Engine: um assistente de treino e bem-estar. Responde em português europeu, de forma "
    "curta, calma e concreta. Usa APENAS os números do contexto JSON fornecido; se um número não existir, di-lo. "
    "Nunca faças diagnósticos, nunca sugiras medicação ou suplementos terapêuticos, nunca prescrevas dietas extremas "
    "nem treino por dor. Perante sintomas (dor no peito, desmaio, falta de ar, tonturas fortes) manda parar e procurar "
    "um profissional de saúde. O motor determinístico decide a prontidão; tu explicas e adaptas, sem a contradizer."
)


def red_flag_check(text: str) -> Optional[str]:
    low = text.lower()
    return RED_FLAG_MESSAGE if any(re.search(p, low) for p in RED_FLAGS) else None


def find_unsupported_numbers(response: str, allowed: Iterable[float], tol: float = 0.51) -> List[float]:
    """Numbers (> 10) in an AI answer that do not appear in the facts it was given."""
    allowed = [float(a) for a in allowed if a is not None]
    found = []
    for m in re.findall(r"\d+(?:[.,]\d+)?", response):
        v = float(m.replace(",", "."))
        if v > 10 and not any(abs(v - a) <= tol for a in allowed):
            found.append(v)
    return found


def facts_numbers(facts: Dict[str, Any]) -> List[float]:
    nums: List[float] = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            nums.append(float(x))
    walk(facts)
    return nums


def build_coach_context(facts: Dict[str, Any]) -> str:
    return json.dumps(facts, ensure_ascii=False, default=str, indent=1)


# ════════════════════════════════════════════════════════════════
# 9. Demo data (clearly labelled as demo in the UI)
# ════════════════════════════════════════════════════════════════
def generate_demo_history(days: int = 90, seed: int = 7, end: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end).normalize() if end is not None else pd.Timestamp.today().normalize()
    dates = pd.date_range(end=end, periods=days)
    week_load = [0, 85, 130, 70, 115, 165, 60]            # Mon..Sun
    load = np.array([week_load[d.weekday()] for d in dates], dtype=float) * rng.uniform(0.9, 1.1, days)
    prev = np.roll(load, 1)
    hrv = 68 + rng.normal(0, 5.5, days) - 0.02 * (prev - 90)
    rhr = 49 + rng.normal(0, 1.4, days) + 0.01 * (prev - 90)
    sleep_h = np.clip(7.5 + rng.normal(0, 0.55, days), 5.0, 9.5)
    score = np.clip(76 + rng.normal(0, 7, days) + (sleep_h - 7.5) * 8, 30, 98)
    hrv[-2:] -= [9, 19]
    rhr[-2:] += [1.5, 3.5]
    sleep_h[-2:] -= [0.5, 1.1]
    score[-2:] -= [6, 14]
    hrv[rng.choice(np.arange(5, days - 3), size=3, replace=False)] = np.nan   # realistic gaps
    return pd.DataFrame({"Date": dates, "HRV": hrv.round(1), "RHR": rhr.round(1), "SleepScore": score.round(0),
                         "SleepHours": sleep_h.round(2), "DailyLoad": load.round(1),
                         "Minutes": (load * 0.55).round(0)})

# ==========================================
# RETROCOMPATIBILIDADE (ALIASES PARA O APP.PY)
# ==========================================
def compute_banister_ctl_atl_tsb(loads: Iterable[float], ctl_tc: float = 42.0, atl_tc: float = 7.0):
    res = compute_banister(loads, ctl_tc, atl_tc)
    return res["ctl"], res["atl"], res["tsb"]

def compute_acwr_legacy(loads: Sequence[float]) -> float:
    val = compute_acwr(loads)
    return val if val is not None else 1.0

def calculate_trend_slope(series):
    res = calculate_trend(series)
    return {"slope": res["slope"], "text": res["text"]}

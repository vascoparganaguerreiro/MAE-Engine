"""
Pytest Test Suite for Apex Engine Synthetic Athletes.
Asserts deterministic outcomes for different physiological states.
"""

import pytest
from engine_core import compute_zscore_readiness, autoregulate_strength_workout


def test_overreaching_athlete():
    """An overreaching athlete with low HRV and high RHR must get low readiness."""
    res = compute_zscore_readiness(
        hrv_val=30.0, hrv_mean=60.0, hrv_sd=5.0,  # -6 SD
        rhr_val=62.0, rhr_mean=50.0, rhr_sd=2.0,  # +6 SD
        sleep_score=40.0, sleep_mean=80.0, sleep_sd=5.0,
        acute_load=120.0, load_mean=70.0, load_sd=10.0,
        mood_score=1.0
    )
    assert res["readiness_score"] < 45, "Overreaching athlete should trigger recovery mode"


def test_high_readiness_athlete():
    """A fully recovered athlete must get a green readiness score."""
    res = compute_zscore_readiness(
        hrv_val=70.0, hrv_mean=60.0, hrv_sd=5.0,
        rhr_val=46.0, rhr_mean=50.0, rhr_sd=2.0,
        sleep_score=90.0, sleep_mean=80.0, sleep_sd=5.0,
        acute_load=50.0, load_mean=70.0, load_sd=10.0,
        mood_score=5.0
    )
    assert res["readiness_score"] >= 70, "Recovered athlete should trigger high readiness"


def test_strength_axial_load_substitution():
    """Low readiness score must substitute high axial spinal load exercises."""
    presc = autoregulate_strength_workout(readiness_score=30)
    workout = presc["workout"]
    
    # Check that no remaining exercise has spinal_load >= 4
    for ex in workout:
        if ex["substituted"]:
            assert ex["spinal_load"] < 4, "Substituted exercise must have low spinal load"

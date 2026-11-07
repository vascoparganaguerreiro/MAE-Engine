import math

import numpy as np
import pandas as pd
import pytest

import engine_core as core


def test_baseline_excludes_current_value():
    baseline = core.compute_baseline([1] * 14 + [100], min_n=14)
    assert baseline is not None
    assert baseline.n == 14
    assert baseline.mean == 1


def test_readiness_requires_two_valid_inputs():
    result = core.compute_readiness({"hrv": 1.0, "rhr": None, "sleep": None, "load": None, "mood": None})
    assert result["score"] is None
    result = core.compute_readiness({"hrv": 1.0, "rhr": -1.0, "sleep": None, "load": None, "mood": None})
    assert result["score"] is not None
    assert 0 <= result["score"] <= 100


def test_acwr_returns_none_for_incomplete_daily_series():
    values = [10.0] * 28
    values[-1] = np.nan
    assert core.compute_acwr(values) is None
    assert core.compute_acwr([10.0] * 27) is None
    assert core.compute_acwr([10.0] * 28) == 1.0


def test_banister_refuses_to_treat_missing_as_rest():
    with pytest.raises(ValueError):
        core.compute_banister([10.0, np.nan, 20.0])


def test_srpe_is_duration_times_rpe():
    assert core.calculate_srpe(60, 7) == 420.0
    with pytest.raises(ValueError):
        core.calculate_srpe(0, 7)


def test_subjective_score_requires_complete_checkin():
    assert core.subjective_score(2, 2, 4) is not None
    assert core.subjective_score(2, None, 4) is None


def test_trend_reports_insufficient_data_without_fake_slope():
    result = core.calculate_trend([60, np.nan, 62])
    assert result["slope"] is None
    assert result["n"] == 2


def test_pacing_band_has_rows_and_valid_cumulative_time():
    df = core.generate_pacing_band(300, 10.0, 190)
    assert len(df) == 10
    assert df.iloc[-1]["Tempo acumulado"] != ""
    assert "Teto FC ilustrativo (bpm)" in df.columns


def test_custom_biomarker_range_is_respected():
    result = core.evaluate_biomarker("apob", 105, low=40, high=80)
    assert result["status"] == "high"


def test_healthspan_is_missing_when_all_inputs_missing():
    result = core.healthspan_score(None, None, None, None)
    assert result["score"] is None
    assert result["parts"] == {}


def test_strength_load_is_not_invented_without_user_1rm():
    result = core.build_strength_session("moderate")
    assert result["exercises"]
    assert all(ex["kg"] is None for ex in result["exercises"])


def test_shoe_status_rejects_invalid_limit():
    with pytest.raises(ValueError):
        core.shoe_status(100, 0)



def test_taper_returns_initial_and_projected_days():
    result = core.simulate_taper(50, 60, 70, days=14, start=__import__("datetime").date(2026, 1, 1))
    assert len(result) == 15
    assert result.iloc[0]["CTL"] == 50
    assert result.iloc[-1]["Date"].date().isoformat() == "2026-01-15"


# --- moved from the old root test_engine.py, updated to the current engine behaviour ---
def test_subjective_score_is_centred_on_three():
    assert core.subjective_score(1, 1, 5) == 2.0
    assert core.subjective_score(5, 5, 1) == -2.0


def test_decision_tiers():
    assert core.decision_for(85)["cap"] == "full"
    assert core.decision_for(30)["cap"] == "recovery"


def test_banister_lengths():
    res = core.compute_banister([100.0] * 42, ctl_tc=42, atl_tc=7)
    assert len(res["ctl"]) == len(res["atl"]) == len(res["tsb"]) == 42


def test_parse_pace():
    assert core.parse_pace("4:30") == 270
    assert core.parse_pace("invalid") is None

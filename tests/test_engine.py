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


def test_set_training_day_and_sRPE_do_not_double_count(tmp_path, monkeypatch):
    import data_store as store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "apex_test.db")
    store.init_db()
    from datetime import date
    d = date(2026, 1, 2)
    store.set_training_day(d, 300, source="manual")
    with pytest.raises(ValueError):
        store.log_workout(d, "Strength", 60, 7)
    rows = store.fetch_training_days(d, d)
    assert float(rows.iloc[0]["daily_load"]) == 300


def test_sRPE_sessions_aggregate_for_one_day(tmp_path, monkeypatch):
    import data_store as store
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "apex_test.db")
    store.init_db()
    from datetime import date
    d = date(2026, 1, 3)
    first = store.log_workout(d, "Run", 40, 6)
    second = store.log_workout(d, "Gym", 30, 7)
    assert first["daily_total"] == 240
    assert second["daily_total"] == 450

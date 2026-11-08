from integrations.garmin import (
    _activity_rows, _general_metrics, _hrv_metrics, _readiness_metrics, _rhr_metrics,
    _running_economy_metrics, _sleep_metrics
)


def test_sleep_data_extracts_last_night_duration_score_stages_and_target():
    payload = {
        "dailySleepDTO": {
            "calendarDate": "2026-11-07",
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 1800,
            "sleepNeedSeconds": 30000,
            "sleepScores": {"overall": {"value": 82}},
        }
    }
    result = _sleep_metrics(payload)
    assert result["sleep_hours"] == 8.0
    assert result["sleep_score"] == 82
    assert result["sleep_deep_minutes"] == 90
    assert result["sleep_target_hours"] == round(30000 / 3600, 2)


def test_sleep_parser_preserves_zero_values():
    assert _sleep_metrics({"sleepTimeSeconds": 0, "sleepScore": 0}).get("sleep_score") == 0


def test_readiness_is_not_body_battery_and_parses_nested_history():
    payload = {"trainingReadinessList": [
        {"calendarDate": "2026-11-06", "score": 48},
        {"calendarDate": "2026-11-07", "score": 72, "sleepScore": 80},
    ]}
    result = _readiness_metrics(payload)
    assert result["vendor_readiness"] == 72
    assert result["readiness_sleep_score"] == 80


def test_general_metrics_extracts_daily_wellness_values():
    payload = {"calendarDate": "2026-11-07", "restingHeartRate": 49, "totalSteps": 9000,
               "averageStressLevel": 28, "bodyBatteryMostRecentValue": 76,
               "averageRespirationValue": 14.2, "averageSpO2": 97}
    result = _general_metrics(payload)
    assert result["rhr"] == 49
    assert result["steps"] == 9000
    assert result["stress_avg"] == 28
    assert result["body_battery"] == 76
    assert result["respiration_sleep_avg"] == 14.2
    assert result["spo2_avg"] == 97


def test_activity_parser_extracts_load_and_running_dynamics_when_present():
    payload = [{"activityId": 123, "startTimeLocal": "2026-11-07 07:00:00",
                "activityName": "Morning Run", "trainingLoad": 85,
                "averageRunningCadenceInStepsPerMinute": 174,
                "averageGroundContactTime": 225}]
    rows = _activity_rows(payload)
    assert len(rows) == 1
    assert rows[0]["training_load"] == 85
    assert rows[0]["avg_cadence"] == 174
    assert rows[0]["ground_contact_time_ms"] == 225


def test_rhr_parser_accepts_scalar_and_object_payloads():
    assert _rhr_metrics(53) == {"rhr": 53.0}
    assert _rhr_metrics({"restingHeartRate": 49})["rhr"] == 49


def test_general_parser_extracts_hydration_metrics_without_fabricating_values():
    result = _general_metrics({"hydrationIntake": 1850, "hydrationGoal": 2500, "sweatLossMl": 430})
    assert result == {"hydration_intake_ml": 1850, "hydration_goal_ml": 2500, "sweat_loss_ml": 430}


def test_running_economy_metric_parser():
    assert _running_economy_metrics({"runningEconomyScore": 103}) == {"running_economy": 103.0}

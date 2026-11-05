import pytest
from datetime import date
import pandas as pd
import numpy as np

import engine_core as core

def test_subjective_score():
    assert core.subjective_score(1, 1, 5) == 5.0
    assert core.subjective_score(5, 5, 1) == 1.0

def test_decision_for():
    d_high = core.decision_for(85)
    assert d_high["cap"] == "full"
    
    d_low = core.decision_for(30)
    assert d_low["cap"] == "light"

def test_banister_computation():
    loads = [100.0] * 42
    res = core.compute_banister(loads, ctl_tc=42, atl_tc=7)
    assert len(res["ctl"]) == 42
    assert len(res["atl"]) == 42
    assert len(res["tsb"]) == 42
    assert res["ctl"][-1] > 0
    assert res["atl"][-1] > 0

def test_parse_pace():
    assert core.parse_pace("4:30") == 270
    assert core.parse_pace("5:00") == 300
    assert core.parse_pace("invalid") is None

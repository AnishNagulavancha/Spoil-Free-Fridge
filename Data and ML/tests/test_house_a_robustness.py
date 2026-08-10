import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiment_config import load_experiment_config
from house_a_robustness import (
    _environment_frame,
    _event_from_active,
    _offline_mean_shift,
    _wilson_interval,
    calibrate_core,
    rebaseline_features,
    score_core,
)


CONFIG_PATH = Path(__file__).parents[1] / "configs" / "house_a_v1.json"
CANDIDATE_CONFIG_PATH = (
    Path(__file__).parents[1] / "configs" / "house_a_v2_candidate.json"
)


def _raw_session(session_id: str, offset: float = 0.0) -> pd.DataFrame:
    elapsed = np.arange(0, 1201, 300, dtype=float)
    return pd.DataFrame(
        {
            "session_id": session_id,
            "elapsed_s": elapsed,
            "v_NH3": 1.0 + offset + np.array([0, 0, 0.01, 0.02, 0.04]),
            "v_H2S": 1.2 + offset + np.array([0, 0.01, 0, 0.03, 0.05]),
            "v_CH4": 1.4 + offset + np.array([0, 0, 0.02, 0.01, 0.03]),
            "bme_gas_ohms": 10000 + 100 * offset - np.array([0, 10, 20, 35, 60]),
            "temp_C": 30 + np.array([0, 0.1, 0.2, 0.2, 0.3]),
            "humidity_pct": 60 + np.array([0, 0.2, 0.4, 0.5, 0.7]),
        }
    )


def test_rebaseline_features_recomputes_all_four_deltas():
    frame = _raw_session("S1")
    result = rebaseline_features(frame, baseline_minutes=10)

    expected_nh3 = frame["v_NH3"] / frame.loc[:2, "v_NH3"].mean() - 1
    assert result["v_NH3_delta_pct"].to_numpy() == pytest.approx(expected_nh3)
    expected_bme = np.log(
        frame.loc[:2, "bme_gas_ohms"].mean() / frame["bme_gas_ohms"]
    )
    assert result["bme_delta_log_inverted"].to_numpy() == pytest.approx(expected_bme)


def test_core_crossfit_calibration_and_scoring_run_without_auxiliary_models():
    config = copy.deepcopy(load_experiment_config(CONFIG_PATH))
    config["baseline_minutes"] = 10
    config["primary_auc_hours"] = 20 / 60
    config["fixed_reporting_hours"] = [10 / 60, 20 / 60]
    config["control"]["drift_smoothing_bins"] = 1
    config["cusum"]["h_candidates"] = [1000]
    controls = rebaseline_features(
        pd.concat([_raw_session("C1", 0.0), _raw_session("C2", 0.03)]), 10
    )
    calibration = calibrate_core(controls, config)
    target = rebaseline_features(_raw_session("T1", 0.01), 10)

    scored, summary = score_core(target, calibration, config)

    assert set(calibration["sessions"]) == {"C1", "C2"}
    assert all(value > 0 for value in calibration["scales"].values())
    assert len(scored) == 5
    assert summary["auc_valid"] is True


def test_event_rules_are_explicit_and_do_not_require_bme_for_protein_only():
    data = pd.DataFrame(
        {
            "cusum_active_NH3": [False, True],
            "cusum_active_H2S": [False, False],
            "cusum_active_CH4": [False, False],
            "cusum_active_BME": [False, False],
        }
    )

    assert _event_from_active(data, "full").tolist() == [False, False]
    assert _event_from_active(data, "protein_only").tolist() == [False, True]


def test_environment_predictors_are_centered_to_each_session_baseline():
    frame = rebaseline_features(_raw_session("S1"), 10)
    result = _environment_frame(frame, minutes=5)
    baseline = result.loc[result["session_minute"] <= 30]

    assert baseline["delta_RH"].mean() == pytest.approx(0.0)
    assert baseline["delta_T"].mean() == pytest.approx(0.0)


def test_offline_mean_shift_finds_large_step_and_wilson_bounds_rate():
    split, gain = _offline_mean_shift(np.r_[np.zeros(10), np.ones(10) * 20], 5)
    low, high = _wilson_interval(25, 2000)

    assert split == 10
    assert gain == pytest.approx(1.0)
    assert low < 25 / 2000 < high


def test_v2_candidate_is_locked_as_unvalidated_and_uses_h2s_bme_rule():
    config = load_experiment_config(CANDIDATE_CONFIG_PATH)

    assert config["analysis_status"] == "frozen_candidate_awaiting_prospective_validation"
    assert config["parameters_frozen"] is True
    assert config["cusum"]["primary_rule"] == "h2s_and_bme_voc"
    assert config["environmental_compensation"]["enabled"] is False

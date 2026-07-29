import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiment_config import load_experiment_config
from model_data import load_sessions
from run_models import (
    _calibration_identity,
    _require_matching_identity,
    _validate_protocol_metadata,
)
from unsupervised_models import (
    SENSOR_COLUMNS,
    _cusum_values,
    calibrate_controls,
    prepare_five_minute_sessions,
    score_session,
)


PROJECT_CONFIG = Path(__file__).parents[1] / "experiment_config.json"


class IdentityScaler:
    def transform(self, values):
        return np.asarray(values, dtype=float)


class FirstTwoPCA:
    def transform(self, values):
        return np.asarray(values, dtype=float)[:, :2]


class NeverAnomaly:
    def decision_function(self, values):
        return np.zeros(len(values), dtype=float)

    def predict(self, values):
        return np.ones(len(values), dtype=int)


def _small_scoring_config() -> dict:
    config = copy.deepcopy(load_experiment_config(PROJECT_CONFIG))
    config["protocol_version"] = "test-v1"
    config["primary_auc_hours"] = 10 / 60
    config["fixed_reporting_hours"] = [5 / 60, 10 / 60]
    config["control"]["bootstrap_sessions"] = 10
    return config


def _dummy_calibration(config: dict) -> dict:
    bins = np.array([0, 1, 2])
    return {
        "protocol_version": config["protocol_version"],
        "aggregation_minutes": config["aggregation_minutes"],
        "sensor_direction": dict(config["sensor_direction"]),
        "drift": {
            sensor: {"time_bin": bins, "value": np.zeros(3)}
            for sensor in SENSOR_COLUMNS
        },
        "scales": {sensor: 1.0 for sensor in SENSOR_COLUMNS},
        "cusum_h": 1000.0,
        "scaler": IdentityScaler(),
        "pca": FirstTwoPCA(),
        "isolation_forest": NeverAnomaly(),
    }


def _session_frame(value: float = 20.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_id": ["target"] * 3,
            "elapsed_s": [0.0, 300.0, 600.0],
            **{
                column: [value, value, value]
                for column in SENSOR_COLUMNS.values()
            },
        }
    )


def test_load_sessions_resamples_and_preserves_session_identity(tmp_path):
    session = tmp_path / "S001"
    analysis = session / "analysis"
    analysis.mkdir(parents=True)
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=4, freq="2min"),
            "elapsed_s": [0, 120, 240, 360],
            "v_NH3_delta_pct": [0.0, 0.2, 0.4, 0.6],
        }
    ).to_csv(analysis / "features.csv", index=False)

    result = load_sessions([session], resample_minutes=5)

    assert set(result["session_id"]) == {"S001"}
    assert len(result) == 2
    assert result["v_NH3_delta_pct"].iloc[0] == pytest.approx(0.2)


def test_load_sessions_requires_at_least_one_session():
    with pytest.raises(ValueError, match="At least one"):
        load_sessions([])


def test_prepare_five_minute_sessions_uses_insertion_relative_bins():
    frame = pd.DataFrame(
        {
            "session_id": ["A", "A", "A"],
            "elapsed_s": [100.0, 400.0, 700.0],
            "v_NH3_delta_pct": [1.0, 2.0, 3.0],
        }
    )

    result = prepare_five_minute_sessions(frame, minutes=5)

    assert result["time_bin"].tolist() == [0, 1, 2]
    assert result["session_time_h"].tolist() == pytest.approx([0, 1 / 12, 1 / 6])


def test_cusum_requires_configured_persistence_after_crossing_limit():
    score, active = _cusum_values(
        np.array([2.0, 2.0, 2.0, 2.0]), k=0.5, h=3.0, persistence=2
    )

    assert score.tolist() == pytest.approx([1.5, 3.0, 4.5, 6.0])
    assert active.tolist() == [False, False, False, True]


def test_score_session_maps_20_z_to_50_on_the_40_z_scale():
    config = _small_scoring_config()

    scored, summary = score_session(
        _session_frame(20.0), _dummy_calibration(config), config
    )

    assert np.allclose(scored["change_index"], 50.0)
    assert all(
        scored[f"channel_index_{sensor}"].eq(0.5).all()
        for sensor in SENSOR_COLUMNS
    )
    assert summary["maximum_change_index"] == pytest.approx(50.0)
    assert summary["auc_valid"] is True
    assert summary["auc_change_index_hours"] == pytest.approx(50 * 10 / 60)


def test_score_session_clips_negative_change_to_zero():
    config = _small_scoring_config()

    scored, summary = score_session(
        _session_frame(-20.0), _dummy_calibration(config), config
    )

    assert scored["change_index"].eq(0.0).all()
    assert summary["maximum_change_index"] == 0.0


def test_score_session_rejects_protocol_mismatch():
    config = _small_scoring_config()
    calibration = _dummy_calibration(config)
    calibration["protocol_version"] = "different"

    with pytest.raises(ValueError, match="protocol versions do not match"):
        score_session(_session_frame(), calibration, config)


def test_control_calibration_runs_leave_one_control_out_pipeline():
    config = _small_scoring_config()
    config["primary_auc_hours"] = 0.25
    config["control"].update(
        {
            "minimum_sessions": 3,
            "drift_smoothing_bins": 1,
            "bootstrap_sessions": 10,
            "bootstrap_block_bins": 2,
            "target_false_session_rate": 0.5,
        }
    )
    config["cusum"].update({"h_candidates": [2, 3], "persistence_bins": 2})
    rows = []
    for session_number, session_id in enumerate(("C1", "C2", "C3")):
        for time_bin, elapsed_s in enumerate((0, 300, 600, 900)):
            row = {
                "session_id": session_id,
                "elapsed_s": float(elapsed_s),
            }
            for sensor_number, column in enumerate(SENSOR_COLUMNS.values(), start=1):
                row[column] = (
                    session_number * 0.02 * sensor_number
                    + time_bin * 0.005 * sensor_number
                )
            rows.append(row)

    calibration = calibrate_controls(
        pd.DataFrame(rows), config, random_state=1
    )

    assert set(calibration["control_sessions"]) == {"C1", "C2", "C3"}
    assert calibration["cusum_h"] in {2.0, 3.0}
    assert all(scale > 0 for scale in calibration["scales"].values())
    assert len(calibration["loo_residuals"]) == 12


def test_control_identity_requires_matching_hardware_and_site():
    records = {
        "C1": {
            "site_id": "home-a",
            "pcb_design_id": "pcb-1",
            "device_id": "dev-1",
            "container_id": "box-1",
        },
        "C2": {
            "site_id": "home-a",
            "pcb_design_id": "pcb-1",
            "device_id": "dev-1",
            "container_id": "box-1",
        },
    }

    identity = _calibration_identity(records)
    assert identity["site_id"] == "home-a"

    records["C2"]["site_id"] = "home-b"
    with pytest.raises(ValueError, match="must share site_id"):
        _calibration_identity(records)


def test_target_identity_must_match_its_control_calibration():
    identity = {
        "site_id": "home-a",
        "pcb_design_id": "pcb-1",
        "device_id": "dev-1",
        "container_id": "box-1",
    }

    _require_matching_identity(identity, identity, "target")
    mismatched = {**identity, "device_id": "dev-2"}
    with pytest.raises(ValueError, match="does not match"):
        _require_matching_identity(mismatched, identity, "target")


def test_protocol_metadata_requires_matching_duration():
    config = _small_scoring_config()
    config["baseline_minutes"] = 30
    record = {
        "protocol_version": "test-v1",
        "log_minutes": 10,
        "food_baseline_minutes": 30,
    }

    _validate_protocol_metadata({"S1": record}, config)

    record["log_minutes"] = 9
    with pytest.raises(ValueError, match="log_minutes must be 10"):
        _validate_protocol_metadata({"S1": record}, config)

import copy
import json
from pathlib import Path

import pytest

from experiment_config import SENSORS, load_experiment_config


PROJECT_CONFIG = (
    Path(__file__).parents[1] / "configs" / "house_a_v2_candidate.json"
)


def _write_config(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "experiment_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_repository_config_loads_with_calibrated_full_scale():
    config = load_experiment_config(PROJECT_CONFIG)

    assert config["index"]["full_scale_z"] == 40.0
    assert config["index"]["interpretation"] == (
        "engineered_change_scale_not_spoilage_percentage"
    )
    assert set(config["sensor_direction"]) == set(SENSORS)


def test_missing_required_section_is_rejected(tmp_path):
    config = json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
    del config["camera"]

    with pytest.raises(ValueError, match="missing: camera"):
        load_experiment_config(_write_config(tmp_path, config))


@pytest.mark.parametrize("invalid_value", [0, -1])
def test_nonpositive_full_scale_is_rejected(tmp_path, invalid_value):
    config = json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
    config["index"]["full_scale_z"] = invalid_value

    with pytest.raises(ValueError, match="full_scale_z must be positive"):
        load_experiment_config(_write_config(tmp_path, config))


def test_invalid_sensor_direction_is_rejected(tmp_path):
    config = json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
    config["sensor_direction"]["NH3"] = 0

    with pytest.raises(ValueError, match="sensor_direction"):
        load_experiment_config(_write_config(tmp_path, config))


def test_reporting_hours_must_be_unique_and_increasing(tmp_path):
    config = copy.deepcopy(
        json.loads(PROJECT_CONFIG.read_text(encoding="utf-8"))
    )
    config["fixed_reporting_hours"] = [1, 3, 2]

    with pytest.raises(ValueError, match="unique and increasing"):
        load_experiment_config(_write_config(tmp_path, config))

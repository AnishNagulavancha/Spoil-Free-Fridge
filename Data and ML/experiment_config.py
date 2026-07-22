"""Load and validate the frozen experimental analysis configuration."""

from __future__ import annotations

import json
from pathlib import Path


SENSORS = ("NH3", "H2S", "CH4", "BME")


def load_experiment_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {"baseline_minutes", "aggregation_minutes", "primary_auc_hours",
                "control", "cusum", "index", "sensor_direction", "camera"}
    missing = required.difference(config)
    if missing:
        raise ValueError(f"Experiment config is missing: {', '.join(sorted(missing))}")
    directions = config["sensor_direction"]
    if set(directions) != set(SENSORS) or any(directions[s] not in (-1, 1) for s in SENSORS):
        raise ValueError("sensor_direction must contain NH3/H2S/CH4/BME with values -1 or 1")
    weights = config["index"]["weights"]
    if set(weights) != set(SENSORS) or sum(float(weights[s]) for s in SENSORS) <= 0:
        raise ValueError("index.weights must contain positive-total NH3/H2S/CH4/BME weights")
    if config["index"]["full_scale_z"] <= 0:
        raise ValueError("index.full_scale_z must be positive")
    if config["cusum"]["persistence_bins"] < 1:
        raise ValueError("cusum.persistence_bins must be at least one")
    return config

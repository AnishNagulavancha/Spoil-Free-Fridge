"""Load and validate the frozen experimental analysis configuration."""

from __future__ import annotations

import json
from pathlib import Path


SENSORS = ("NH3", "H2S", "CH4", "BME")
PRIMARY_RULES = ("protein_gas_and_bme_voc", "h2s_and_bme_voc")


def load_experiment_config(path: Path) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "baseline_minutes", "aggregation_minutes", "primary_auc_hours",
        "fixed_reporting_hours", "control", "cusum", "index",
        "sensor_direction", "camera",
    }
    missing = required.difference(config)
    if missing:
        raise ValueError(f"Experiment config is missing: {', '.join(sorted(missing))}")
    directions = config["sensor_direction"]
    if set(directions) != set(SENSORS) or any(directions[s] not in (-1, 1) for s in SENSORS):
        raise ValueError("sensor_direction must contain NH3/H2S/CH4/BME with values -1 or 1")
    weights = config["index"]["weights"]
    if set(weights) != set(SENSORS):
        raise ValueError("index.weights must contain NH3/H2S/CH4/BME")
    numeric_weights = [float(weights[sensor]) for sensor in SENSORS]
    if any(value < 0 for value in numeric_weights) or sum(numeric_weights) <= 0:
        raise ValueError("index.weights must be nonnegative with a positive total")
    if config["index"]["full_scale_z"] <= 0:
        raise ValueError("index.full_scale_z must be positive")
    if config["index"].get("negative_values") != "clip_to_zero":
        raise ValueError("This protocol requires index.negative_values=clip_to_zero")
    if config["cusum"]["persistence_bins"] < 1:
        raise ValueError("cusum.persistence_bins must be at least one")
    if config["cusum"].get("primary_rule") not in PRIMARY_RULES:
        raise ValueError(
            "cusum.primary_rule must be one of: " + ", ".join(PRIMARY_RULES)
        )
    hours = [float(value) for value in config["fixed_reporting_hours"]]
    if not hours or any(value <= 0 for value in hours):
        raise ValueError("fixed_reporting_hours must contain positive values")
    if hours != sorted(set(hours)):
        raise ValueError("fixed_reporting_hours must be unique and increasing")
    if hours[-1] > float(config["primary_auc_hours"]):
        raise ValueError("fixed_reporting_hours cannot exceed primary_auc_hours")
    return config

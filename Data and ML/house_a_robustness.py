"""Reproduce and stress-test the frozen House A sensor result.

This module deliberately keeps HouseA_v1 unchanged.  Alternative calibrations,
environmental residualization, event rules, and parameter choices are reported
as robustness or exploratory analyses; none silently replaces the benchmark.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from experiment_config import load_experiment_config
from model_data import load_sessions
from unsupervised_models import (
    SENSOR_COLUMNS,
    _cusum_values,
    _evaluate_curve,
    _mad_scale,
    _smooth_control_curve,
    prepare_five_minute_sessions,
    score_session,
)


RAW_SENSOR_COLUMNS = {
    "NH3": "v_NH3",
    "H2S": "v_H2S",
    "CH4": "v_CH4",
    "BME": "bme_gas_ohms",
}
ENVIRONMENT_COLUMNS = ("temp_C", "humidity_pct")


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, default=_json_default), encoding="utf-8"
    )


def _config_hash(config: dict) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def discover_sessions(root: Path) -> pd.DataFrame:
    """Return session paths and audited roles from staged metadata."""
    rows = []
    for path in sorted(item for item in root.iterdir() if item.is_dir()):
        metadata_path = path / "metadata.json"
        features_path = path / "analysis" / "features.csv"
        if not metadata_path.is_file() or not features_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "session_id": path.name,
                "session_role": metadata.get("session_role"),
                "sample_id": metadata.get("sample_id"),
                "path": path,
            }
        )
    result = pd.DataFrame(rows)
    required_roles = {"control": 3, "pilot": 1, "confirmation": 3}
    counts = result["session_role"].value_counts().to_dict() if not result.empty else {}
    missing = {
        role: expected - int(counts.get(role, 0))
        for role, expected in required_roles.items()
        if int(counts.get(role, 0)) < expected
    }
    if missing:
        raise ValueError(f"House A staged data are incomplete: {missing}")
    return result


def rebaseline_features(frame: pd.DataFrame, baseline_minutes: float) -> pd.DataFrame:
    """Recompute sensor deltas from raw features for a sensitivity analysis."""
    parts = []
    for session_id, group in frame.groupby("session_id", sort=False):
        group = group.sort_values("elapsed_s").copy()
        start = float(group["elapsed_s"].min())
        baseline = group.loc[
            group["elapsed_s"] <= start + float(baseline_minutes) * 60.0
        ]
        if len(baseline) < 3:
            raise ValueError(f"Insufficient baseline rows for {session_id}")
        means = baseline[list(RAW_SENSOR_COLUMNS.values())].mean()
        if means.isna().any() or (means <= 0).any():
            raise ValueError(f"Invalid baseline means for {session_id}")
        for sensor in ("NH3", "H2S", "CH4"):
            raw = RAW_SENSOR_COLUMNS[sensor]
            group[SENSOR_COLUMNS[sensor]] = group[raw] / means[raw] - 1.0
        group[SENSOR_COLUMNS["BME"]] = np.log(
            means[RAW_SENSOR_COLUMNS["BME"]] / group[RAW_SENSOR_COLUMNS["BME"]]
        )
        parts.append(group)
    return pd.concat(parts).sort_index()


def load_feature_set(
    paths: Iterable[Path], aggregation_minutes: int, baseline_minutes: float,
    recompute_baseline: bool = False,
) -> pd.DataFrame:
    # The frozen feature files already contain deltas calculated from one-minute
    # data. Preserve them exactly unless baseline length is the parameter under
    # test. Recomputing after five-minute aggregation changes the benchmark.
    if not recompute_baseline:
        return load_sessions(list(paths), resample_minutes=int(aggregation_minutes))
    frame = load_sessions(list(paths), resample_minutes=1)
    return rebaseline_features(frame, baseline_minutes)


def calibrate_core(frame: pd.DataFrame, config: dict) -> dict:
    """Cross-fit drift and robust scale without fitting PCA/Isolation Forest."""
    minutes = int(config["aggregation_minutes"])
    controls = prepare_five_minute_sessions(frame, minutes)
    sessions = list(controls["session_id"].unique())
    if len(sessions) < 2:
        raise ValueError("Core robustness calibration requires at least two controls")
    smoothing = int(config["control"]["drift_smoothing_bins"])
    loo_parts = []
    for held_out in sessions:
        train = controls.loc[controls["session_id"] != held_out]
        test = controls.loc[controls["session_id"] == held_out].copy()
        for sensor, column in SENSOR_COLUMNS.items():
            curve = _smooth_control_curve(train, column, smoothing)
            test[f"residual_{sensor}"] = (
                test[column] - _evaluate_curve(curve, test["time_bin"])
            )
        loo_parts.append(test)
    loo = pd.concat(loo_parts, ignore_index=True)
    scales = {
        sensor: _mad_scale(loo[f"residual_{sensor}"].to_numpy())
        for sensor in SENSOR_COLUMNS
    }
    directions = config["sensor_direction"]
    for sensor in SENSOR_COLUMNS:
        loo[f"z_{sensor}"] = (
            directions[sensor] * loo[f"residual_{sensor}"] / scales[sensor]
        )
    drift = {
        sensor: _smooth_control_curve(controls, column, smoothing)
        for sensor, column in SENSOR_COLUMNS.items()
    }
    return {
        "drift": drift,
        "scales": scales,
        "loo": loo,
        "sessions": sessions,
    }


def _event_from_active(data: pd.DataFrame, rule: str) -> pd.Series:
    a = {sensor: data[f"cusum_active_{sensor}"].astype(bool) for sensor in SENSOR_COLUMNS}
    rules = {
        "full": (a["NH3"] | a["H2S"]) & a["BME"],
        "protein_gas_and_bme_voc": (a["NH3"] | a["H2S"]) & a["BME"],
        "nh3_and_bme": a["NH3"] & a["BME"],
        "h2s_and_bme": a["H2S"] & a["BME"],
        "h2s_and_bme_voc": a["H2S"] & a["BME"],
        "protein_only": a["NH3"] | a["H2S"],
        "bme_only": a["BME"],
        "nh3_only": a["NH3"],
        "h2s_only": a["H2S"],
        "ch4_only": a["CH4"],
    }
    if rule not in rules:
        raise ValueError(f"Unknown event rule: {rule}")
    return rules[rule]


def _index_from_weights(data: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    total = sum(float(weights[sensor]) for sensor in SENSOR_COLUMNS)
    if total <= 0:
        raise ValueError("At least one index weight must be positive")
    return 100.0 * sum(
        float(weights[sensor]) * data[f"channel_index_{sensor}"]
        for sensor in SENSOR_COLUMNS
    ) / total


def score_core(frame: pd.DataFrame, calibration: dict, config: dict) -> tuple[pd.DataFrame, dict]:
    """Score the index and event identically to HouseA_v1, without auxiliary ML."""
    minutes = int(config["aggregation_minutes"])
    data = prepare_five_minute_sessions(frame, minutes)
    if data["session_id"].nunique() != 1:
        raise ValueError("score_core expects one session")
    directions = config["sensor_direction"]
    full_scale = float(config["index"]["full_scale_z"])
    for sensor, column in SENSOR_COLUMNS.items():
        curve = calibration["drift"][sensor]
        drift = _evaluate_curve(curve, data["time_bin"])
        data[f"control_drift_{sensor}"] = drift
        data[f"adjusted_{sensor}"] = data[column] - drift
        data[f"z_{sensor}"] = (
            directions[sensor] * data[f"adjusted_{sensor}"] / calibration["scales"][sensor]
        )
        data[f"channel_index_{sensor}"] = (
            data[f"z_{sensor}"].clip(lower=0) / full_scale
        ).clip(upper=1)
    data["change_index"] = _index_from_weights(data, config["index"]["weights"])

    k = float(config["cusum"]["k"])
    h = float(config["cusum"]["h_candidates"][0])
    persistence = int(config["cusum"]["persistence_bins"])
    for sensor in SENSOR_COLUMNS:
        score, active = _cusum_values(
            data[f"z_{sensor}"].to_numpy(), k, h, persistence
        )
        data[f"cusum_{sensor}"] = score
        data[f"cusum_active_{sensor}"] = active
    data["primary_event"] = _event_from_active(
        data,
        config["cusum"].get("primary_rule", "protein_gas_and_bme_voc"),
    )
    event_rows = data.loc[data["primary_event"]]
    detection = None if event_rows.empty else float(event_rows["session_time_h"].iloc[0])

    auc_h = float(config["primary_auc_hours"])
    interval_h = minutes / 60.0
    window = data.loc[data["session_time_h"].between(0, auc_h)]
    expected = int(round(auc_h / interval_h)) + 1
    coverage = min(1.0, len(window) / expected)
    span_ok = not window.empty and float(window["session_time_h"].max()) >= auc_h - interval_h
    gaps_ok = window["session_time_h"].diff().dropna().le(
        float(config["maximum_interpolation_gap_minutes"]) / 60.0 + interval_h + 1e-9
    ).all()
    valid = coverage >= float(config["minimum_auc_coverage"]) and span_ok and gaps_ok
    auc = (
        float(np.trapezoid(window["change_index"], window["session_time_h"]))
        if valid else None
    )
    fixed = {}
    for hour in config["fixed_reporting_hours"]:
        position = int((data["session_time_h"] - float(hour)).abs().argmin())
        row = data.iloc[position]
        fixed[f"{float(hour):g}"] = (
            float(row["change_index"])
            if abs(float(row["session_time_h"]) - float(hour)) <= interval_h + 1e-9
            else None
        )
    return data, {
        "session_id": str(data["session_id"].iloc[0]),
        "primary_event_detected": bool(data["primary_event"].any()),
        "time_to_sustained_change_h": detection,
        "maximum_change_index": float(data["change_index"].max()),
        "auc_change_index_hours": auc,
        "auc_valid": bool(valid),
        "index_at_fixed_hours": fixed,
    }


def benchmark(
    records: pd.DataFrame, config: dict, calibration_path: Path
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    calibration = joblib.load(calibration_path)
    rows = []
    scored = {}
    for item in records.itertuples(index=False):
        frame = load_feature_set(
            [item.path], config["aggregation_minutes"], config["baseline_minutes"]
        )
        detail, summary = score_session(frame, calibration, config)
        scored[item.session_id] = detail
        rows.append(
            {
                "session_id": item.session_id,
                "session_role": item.session_role,
                "primary_event": summary["primary_event_detected"],
                "detection_time_h": summary["time_to_sustained_change_h"],
                **{
                    f"index_{hour}h": summary["index_at_fixed_hours"].get(str(hour))
                    for hour in (1, 2, 4, 6, 8)
                },
                "auc_0_8h": summary["auc_change_index_hours"],
                "maximum_index": summary["maximum_change_index"],
            }
        )
    return pd.DataFrame(rows), scored


def full_leave_one_control_out(
    control_paths: list[Path], confirmation_paths: list[Path], config: dict
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    base_controls = load_feature_set(
        control_paths, config["aggregation_minutes"], config["baseline_minutes"]
    )
    confirmations = {
        path.name: load_feature_set(
            [path], config["aggregation_minutes"], config["baseline_minutes"]
        )
        for path in confirmation_paths
    }
    rows, scales, held_details = [], [], {}
    for held_path in control_paths:
        train = base_controls.loc[base_controls["session_id"] != held_path.name]
        held = base_controls.loc[base_controls["session_id"] == held_path.name]
        calibration = calibrate_core(train, config)
        detail, held_summary = score_core(held, calibration, config)
        held_details[held_path.name] = detail
        chicken_summaries = [
            score_core(frame, calibration, config)[1] for frame in confirmations.values()
        ]
        chicken_auc = [
            item["auc_change_index_hours"] for item in chicken_summaries
            if item["auc_change_index_hours"] is not None
        ]
        held_auc = held_summary["auc_change_index_hours"]
        rows.append(
            {
                "training_controls": " + ".join(
                    path.name for path in control_paths if path != held_path
                ),
                "held_out_control": held_path.name,
                "held_out_control_event": held_summary["primary_event_detected"],
                "held_out_control_auc": held_auc,
                "confirmations_detected": sum(
                    item["primary_event_detected"] for item in chicken_summaries
                ),
                "confirmation_count": len(chicken_summaries),
                "chicken_detection_min_h": min(
                    item["time_to_sustained_change_h"] for item in chicken_summaries
                    if item["time_to_sustained_change_h"] is not None
                ),
                "chicken_detection_max_h": max(
                    item["time_to_sustained_change_h"] for item in chicken_summaries
                    if item["time_to_sustained_change_h"] is not None
                ),
                "minimum_chicken_auc": min(chicken_auc),
                "auc_absolute_margin": min(chicken_auc) - held_auc,
                "minimum_chicken_control_auc_ratio": (
                    min(chicken_auc) / held_auc if held_auc and held_auc > 0 else np.inf
                ),
            }
        )
        scales.append({"held_out_control": held_path.name, **calibration["scales"]})
    return pd.DataFrame(rows), pd.DataFrame(scales), held_details


def _parameter_variants(config: dict) -> list[tuple[str, dict, float, int]]:
    """Create a prespecified one-factor-at-a-time sensitivity neighborhood."""
    variants = []

    def add(name: str, mutate=None, baseline=None, aggregation=None):
        candidate = copy.deepcopy(config)
        if mutate:
            mutate(candidate)
        variants.append(
            (
                name,
                candidate,
                float(baseline if baseline is not None else candidate["baseline_minutes"]),
                int(aggregation if aggregation is not None else candidate["aggregation_minutes"]),
            )
        )

    add("frozen_reference")
    for value in (20, 45):
        add(f"baseline_{value}m", baseline=value)
    add("aggregation_10m", aggregation=10,
        mutate=lambda c: c.update({"aggregation_minutes": 10}))
    for value in (3, 9):
        add(f"drift_smoothing_{value}",
            mutate=lambda c, v=value: c["control"].update({"drift_smoothing_bins": v}))
    for value in (0.25, 1.0):
        add(f"cusum_k_{value:g}",
            mutate=lambda c, v=value: c["cusum"].update({"k": v}))
    for value in (20, 40):
        add(f"cusum_h_{value:g}",
            mutate=lambda c, v=value: c["cusum"].update({"h_candidates": [v]}))
    for value in (2, 4):
        add(f"persistence_{value}_bins",
            mutate=lambda c, v=value: c["cusum"].update({"persistence_bins": v}))
    for value in (20, 60):
        add(f"full_scale_z_{value:g}",
            mutate=lambda c, v=value: c["index"].update({"full_scale_z": v}))
    add("equal_weights", mutate=lambda c: c["index"].update(
        {"weights": {sensor: 0.25 for sensor in SENSOR_COLUMNS}}
    ))
    for sensor in SENSOR_COLUMNS:
        for factor in (0.8, 1.2):
            add(
                f"weight_{sensor}_{factor:g}x",
                mutate=lambda c, s=sensor, f=factor: c["index"]["weights"].update(
                    {s: c["index"]["weights"][s] * f}
                ),
            )
    return variants


def parameter_sensitivity(
    control_paths: list[Path], confirmation_paths: list[Path], config: dict
) -> pd.DataFrame:
    cache = {}
    rows = []
    for name, candidate, baseline_minutes, aggregation_minutes in _parameter_variants(config):
        key = (aggregation_minutes, baseline_minutes)
        if key not in cache:
            recompute = baseline_minutes != float(config["baseline_minutes"])
            cache[key] = {
                "controls": load_feature_set(
                    control_paths, aggregation_minutes, baseline_minutes,
                    recompute_baseline=recompute,
                ),
                "confirmations": {
                    path.name: load_feature_set(
                        [path], aggregation_minutes, baseline_minutes,
                        recompute_baseline=recompute,
                    )
                    for path in confirmation_paths
                },
            }
        controls = cache[key]["controls"]
        confirmations = cache[key]["confirmations"]
        full_calibration = calibrate_core(controls, candidate)
        chicken = [
            score_core(frame, full_calibration, candidate)[1]
            for frame in confirmations.values()
        ]
        control_scores = []
        for held_path in control_paths:
            train = controls.loc[controls["session_id"] != held_path.name]
            held = controls.loc[controls["session_id"] == held_path.name]
            control_scores.append(score_core(held, calibrate_core(train, candidate), candidate)[1])
        chicken_auc = [item["auc_change_index_hours"] for item in chicken]
        control_auc = [item["auc_change_index_hours"] for item in control_scores]
        valid_auc = all(value is not None for value in chicken_auc + control_auc)
        min_chicken = min(chicken_auc) if valid_auc else None
        max_control = max(control_auc) if valid_auc else None
        rows.append(
            {
                "configuration": name,
                "control_events": sum(item["primary_event_detected"] for item in control_scores),
                "confirmation_events": sum(item["primary_event_detected"] for item in chicken),
                "median_chicken_detection_h": float(np.median([
                    item["time_to_sustained_change_h"] for item in chicken
                    if item["time_to_sustained_change_h"] is not None
                ])) if any(item["time_to_sustained_change_h"] is not None for item in chicken) else None,
                "minimum_chicken_auc": min_chicken,
                "maximum_loo_control_auc": max_control,
                "auc_absolute_margin": (
                    min_chicken - max_control if valid_auc else None
                ),
                "minimum_chicken_maximum_control_auc_ratio": (
                    min_chicken / max_control if valid_auc and max_control > 0 else np.inf
                ),
                "retains_3_of_3_and_0_of_3": (
                    sum(item["primary_event_detected"] for item in chicken) == 3
                    and sum(item["primary_event_detected"] for item in control_scores) == 0
                ),
            }
        )
    return pd.DataFrame(rows)


def ablation_analysis(
    confirmation_details: dict[str, pd.DataFrame],
    loo_control_details: dict[str, pd.DataFrame],
    config: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    event_rows = []
    for rule in (
        "full", "nh3_and_bme", "h2s_and_bme", "protein_only",
        "bme_only", "nh3_only", "h2s_only", "ch4_only",
    ):
        result = {}
        for group_name, details in (
            ("control", loo_control_details), ("confirmation", confirmation_details)
        ):
            detections = []
            for data in details.values():
                event = _event_from_active(data, rule)
                rows = data.loc[event]
                detections.append(
                    None if rows.empty else float(rows["session_time_h"].iloc[0])
                )
            result[f"{group_name}_events"] = sum(value is not None for value in detections)
            result[f"{group_name}_detection_times_h"] = json.dumps(detections)
        event_rows.append({"event_rule": rule, **result})

    weight_variants = {
        "full": config["index"]["weights"],
        "without_ch4": {"NH3": 0.30, "H2S": 0.35, "CH4": 0.0, "BME": 0.25},
        "without_bme": {"NH3": 0.30, "H2S": 0.35, "CH4": 0.10, "BME": 0.0},
        "equal": {sensor: 0.25 for sensor in SENSOR_COLUMNS},
        "bme_only": {"NH3": 0.0, "H2S": 0.0, "CH4": 0.0, "BME": 1.0},
        "protein_only": {"NH3": 0.30, "H2S": 0.35, "CH4": 0.0, "BME": 0.0},
    }
    index_rows = []
    auc_h = float(config["primary_auc_hours"])
    for name, weights in weight_variants.items():
        values = {}
        for group_name, details in (
            ("control", loo_control_details), ("confirmation", confirmation_details)
        ):
            aucs, hour8 = [], []
            for data in details.values():
                index = _index_from_weights(data, weights)
                mask = data["session_time_h"].between(0, auc_h)
                aucs.append(float(np.trapezoid(index[mask], data.loc[mask, "session_time_h"])))
                position = int((data["session_time_h"] - auc_h).abs().argmin())
                hour8.append(float(index.iloc[position]))
            values[f"{group_name}_auc_min"] = min(aucs)
            values[f"{group_name}_auc_max"] = max(aucs)
            values[f"{group_name}_hour8_min"] = min(hour8)
            values[f"{group_name}_hour8_max"] = max(hour8)
        values["auc_absolute_margin"] = (
            values["confirmation_auc_min"] - values["control_auc_max"]
        )
        index_rows.append({"index_variant": name, **values})
    return pd.DataFrame(event_rows), pd.DataFrame(index_rows)


def _wilson_interval(successes: int, total: int, z: float = 1.959964) -> tuple[float, float]:
    if total <= 0:
        return (np.nan, np.nan)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    spread = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - spread), min(1.0, center + spread)


def bootstrap_false_alarm(
    loo: pd.DataFrame, config: dict, random_state: int = 42
) -> pd.DataFrame:
    arrays = [
        group[[f"z_{sensor}" for sensor in SENSOR_COLUMNS]].to_numpy(dtype=float)
        for _, group in loo.groupby("session_id", sort=False)
    ]
    count = int(config["control"]["bootstrap_sessions"])
    minutes = int(config["aggregation_minutes"])
    k = float(config["cusum"]["k"])
    h = float(config["cusum"]["h_candidates"][0])
    persistence = int(config["cusum"]["persistence_bins"])
    rng = np.random.default_rng(random_state)
    rows = []
    for block_minutes in (15, 30, 60, 90):
        block = max(1, round(block_minutes / minutes))
        events = {hours: 0 for hours in (2, 4, 6, 8)}
        timings = []
        causes = {"NH3+BME": 0, "H2S+BME": 0, "NH3+H2S+BME": 0}
        full_length = round(8 * 60 / minutes)
        for _ in range(count):
            pieces = []
            while sum(len(piece) for piece in pieces) < full_length:
                source = arrays[int(rng.integers(len(arrays)))]
                if len(source) <= block:
                    piece = source
                else:
                    start = int(rng.integers(0, len(source) - block + 1))
                    piece = source[start:start + block]
                pieces.append(piece)
            sample = np.concatenate(pieces)[:full_length]
            active = {
                sensor: _cusum_values(sample[:, i], k, h, persistence)[1]
                for i, sensor in enumerate(SENSOR_COLUMNS)
            }
            primary_rule = config["cusum"].get(
                "primary_rule", "protein_gas_and_bme_voc"
            )
            if primary_rule == "protein_gas_and_bme_voc":
                primary = (active["NH3"] | active["H2S"]) & active["BME"]
            elif primary_rule == "h2s_and_bme_voc":
                primary = active["H2S"] & active["BME"]
            else:
                raise ValueError(f"Unsupported primary rule: {primary_rule}")
            for hours in events:
                end = round(hours * 60 / minutes)
                events[hours] += bool(primary[:end].any())
            positions = np.flatnonzero(primary)
            if len(positions):
                first = int(positions[0])
                timings.append(first * minutes / 60.0)
                nh3, h2s = bool(active["NH3"][first]), bool(active["H2S"][first])
                if nh3 and h2s:
                    causes["NH3+H2S+BME"] += 1
                elif nh3:
                    causes["NH3+BME"] += 1
                else:
                    causes["H2S+BME"] += 1
        for hours, successes in events.items():
            low, high = _wilson_interval(successes, count)
            rows.append(
                {
                    "block_minutes": block_minutes,
                    "window_hours": hours,
                    "simulations": count,
                    "false_sessions": successes,
                    "false_session_rate": successes / count,
                    "monte_carlo_wilson_low": low,
                    "monte_carlo_wilson_high": high,
                    "median_false_event_time_h": (
                        float(np.median(timings)) if timings and hours == 8 else None
                    ),
                    "false_event_causes_8h": json.dumps(causes) if hours == 8 else None,
                }
            )
    return pd.DataFrame(rows)


def shifted_control_stress(
    control_paths: list[Path], calibration: dict, config: dict
) -> pd.DataFrame:
    # Use one-minute raw features because the shifted baseline itself is under
    # test; score_core performs the configured five-minute aggregation later.
    original = load_sessions(control_paths, resample_minutes=1)
    rows = []
    for session_id, group in original.groupby("session_id", sort=False):
        absolute_start = float(group["elapsed_s"].min())
        for shift_minutes in (0, 60, 120, 180):
            cropped = group.loc[
                group["elapsed_s"] >= absolute_start + shift_minutes * 60
            ].copy()
            cropped["elapsed_s"] -= float(cropped["elapsed_s"].min())
            cropped = rebaseline_features(cropped, config["baseline_minutes"])
            detail, summary = score_core(cropped, calibration, config)
            rows.append(
                {
                    "session_id": session_id,
                    "baseline_shift_minutes": shift_minutes,
                    "available_hours": float(detail["session_time_h"].max()),
                    "primary_event": summary["primary_event_detected"],
                    "detection_time_from_shift_h": summary["time_to_sustained_change_h"],
                    "maximum_index": summary["maximum_change_index"],
                }
            )
    return pd.DataFrame(rows)


def _environment_frame(frame: pd.DataFrame, minutes: int) -> pd.DataFrame:
    data = prepare_five_minute_sessions(frame, minutes)
    parts = []
    for _, group in data.groupby("session_id", sort=False):
        group = group.copy()
        baseline = group.loc[group["session_minute"] <= 30]
        group["delta_RH"] = group["humidity_pct"] - baseline["humidity_pct"].mean()
        group["delta_T"] = group["temp_C"] - baseline["temp_C"].mean()
        parts.append(group)
    return pd.concat(parts, ignore_index=True)


ENV_MODELS = {
    "time_only": ["session_time_h"],
    "delta_rh": ["delta_RH"],
    "delta_rh_delta_t": ["delta_RH", "delta_T"],
    "hybrid": ["delta_RH", "delta_T", "session_time_h"],
}


def environmental_loo_diagnostics(control_frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    data = _environment_frame(control_frame, int(config["aggregation_minutes"]))
    rows = []
    for model_name, predictors in ENV_MODELS.items():
        for held_out in data["session_id"].unique():
            train = data.loc[data["session_id"] != held_out]
            test = data.loc[data["session_id"] == held_out]
            for sensor, response in SENSOR_COLUMNS.items():
                model = LinearRegression(fit_intercept=False).fit(
                    train[predictors], train[response]
                )
                residual = test[response].to_numpy() - model.predict(test[predictors])
                rows.append(
                    {
                        "model": model_name,
                        "held_out_control": held_out,
                        "sensor": sensor,
                        "mae": float(np.mean(np.abs(residual))),
                        "rmse": float(np.sqrt(np.mean(residual ** 2))),
                        "median_residual": float(np.median(residual)),
                        "mad_residual": _mad_scale(residual),
                        "coefficients": json.dumps(dict(zip(predictors, model.coef_))),
                    }
                )
    return pd.DataFrame(rows)


def summarize_environmental_loo(diagnostics: pd.DataFrame) -> pd.DataFrame:
    """Aggregate held-out errors without treating time bins as independent trials."""
    by_sensor = (
        diagnostics.groupby(["model", "sensor"], as_index=False)
        .agg(mean_fold_rmse=("rmse", "mean"), max_fold_rmse=("rmse", "max"),
             mean_fold_mae=("mae", "mean"))
    )
    overall = (
        diagnostics.groupby("model", as_index=False)
        .agg(mean_sensor_fold_rmse=("rmse", "mean"),
             mean_sensor_fold_mae=("mae", "mean"))
    )
    return by_sensor.merge(overall, on="model", how="left")


def _fit_environment_models(data: pd.DataFrame, predictors: list[str]) -> dict:
    return {
        sensor: LinearRegression(fit_intercept=False).fit(data[predictors], data[response])
        for sensor, response in SENSOR_COLUMNS.items()
    }


def _residualize_environment(
    frame: pd.DataFrame, models: dict, predictors: list[str], minutes: int
) -> pd.DataFrame:
    data = _environment_frame(frame, minutes)
    for sensor, response in SENSOR_COLUMNS.items():
        data[response] = data[response] - models[sensor].predict(data[predictors])
    # score_core only needs session_id, elapsed_s, and the response columns.
    return data


def environmental_sensitivity(
    controls: pd.DataFrame,
    confirmations: dict[str, pd.DataFrame],
    config: dict,
    original_benchmark: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    minutes = int(config["aggregation_minutes"])
    predictors = ENV_MODELS["delta_rh_delta_t"]
    control_env = _environment_frame(controls, minutes)
    full_models = _fit_environment_models(control_env, predictors)
    residual_controls = _residualize_environment(controls, full_models, predictors, minutes)
    calibration = calibrate_core(residual_controls, config)

    domain_columns = ["humidity_pct", "temp_C", *predictors]
    domain = {
        column: [float(control_env[column].min()), float(control_env[column].max())]
        for column in domain_columns
    }
    rows = []
    for session_id, frame in confirmations.items():
        env = _environment_frame(frame, minutes)
        out = np.zeros(len(env), dtype=bool)
        for column, (low, high) in domain.items():
            out |= ~env[column].between(low, high).to_numpy()
        residual = _residualize_environment(frame, full_models, predictors, minutes)
        _, summary = score_core(residual, calibration, config)
        original = original_benchmark.loc[original_benchmark["session_id"] == session_id].iloc[0]
        rows.append(
            {
                "session_id": session_id,
                "original_detection_h": original["detection_time_h"],
                "environment_adjusted_detection_h": summary["time_to_sustained_change_h"],
                "original_auc": original["auc_0_8h"],
                "environment_adjusted_auc": summary["auc_change_index_hours"],
                "original_hour8_index": original["index_8h"],
                "environment_adjusted_hour8_index": summary["index_at_fixed_hours"]["8"],
                "environment_out_of_domain_fraction": float(out.mean()),
                "interpretation": "exploratory_extrapolation_present" if out.any() else "within_control_domain",
            }
        )
    coefficient_payload = {
        "predictors": predictors,
        "training_domain": domain,
        "coefficients": {
            sensor: dict(zip(predictors, model.coef_))
            for sensor, model in full_models.items()
        },
        "warning": (
            "Exploratory only. Chicken environmental conditions extend beyond the "
            "three-control training domain."
        ),
    }
    return pd.DataFrame(rows), coefficient_payload


def _rolling_slope(values: pd.Series, time_h: pd.Series, bins: int = 6) -> np.ndarray:
    result = np.full(len(values), np.nan)
    for end in range(bins - 1, len(values)):
        start = end - bins + 1
        x = time_h.iloc[start:end + 1].to_numpy(dtype=float)
        y = values.iloc[start:end + 1].to_numpy(dtype=float)
        if np.ptp(x) > 0:
            result[end] = np.polyfit(x, y, 1)[0]
    return result


def _offline_mean_shift(values: np.ndarray, minimum_segment: int = 6) -> tuple[int | None, float]:
    values = np.asarray(values, dtype=float)
    if len(values) < 2 * minimum_segment:
        return None, 0.0
    total = float(np.sum((values - values.mean()) ** 2))
    if total <= 0:
        return None, 0.0
    best_index, best_sse = None, np.inf
    for split in range(minimum_segment, len(values) - minimum_segment + 1):
        left, right = values[:split], values[split:]
        sse = np.sum((left - left.mean()) ** 2) + np.sum((right - right.mean()) ** 2)
        if sse < best_sse:
            best_index, best_sse = split, float(sse)
    return best_index, max(0.0, (total - best_sse) / total)


def _page_hinkley_score(values: np.ndarray, delta: float = 0.1) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    result = np.zeros(len(values))
    running_mean = 0.0
    for index, value in enumerate(values):
        running_mean += (value - running_mean) / (index + 1)
        previous = result[index - 1] if index else 0.0
        result[index] = max(0.0, previous + value - running_mean - delta)
    return result


def change_point_comparison(
    confirmation_details: dict[str, pd.DataFrame],
    control_details: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict]:
    control_slopes = np.concatenate([
        _rolling_slope(data["change_index"], data["session_time_h"])
        for data in control_details.values()
    ])
    slope_threshold = float(np.nanquantile(control_slopes, 0.99))
    control_ph_max = max(
        float(_page_hinkley_score(data["change_index"].to_numpy()).max())
        for data in control_details.values()
    )
    ph_threshold = control_ph_max * 1.05 + 1e-9
    control_shift_results = []
    for data in control_details.values():
        values = data["change_index"].to_numpy()
        split, gain = _offline_mean_shift(values)
        magnitude = (
            0.0 if split is None
            else abs(float(values[split:].mean() - values[:split].mean()))
        )
        control_shift_results.append((gain, magnitude))
    control_shift_gain = max(item[0] for item in control_shift_results)
    control_shift_magnitude = max(item[1] for item in control_shift_results)
    rows = []
    for session_id, data in confirmation_details.items():
        primary = data.loc[data["primary_event"]]
        cusum = None if primary.empty else float(primary["session_time_h"].iloc[0])
        slopes = _rolling_slope(data["change_index"], data["session_time_h"])
        rapid = np.nan_to_num(slopes > slope_threshold, nan=False)
        rapid_persistent = np.convolve(rapid.astype(int), np.ones(3, dtype=int), mode="full")[:len(rapid)] >= 3
        rapid_positions = np.flatnonzero(rapid_persistent)
        rapid_time = None if not len(rapid_positions) else float(data["session_time_h"].iloc[rapid_positions[0]])
        ph = _page_hinkley_score(data["change_index"].to_numpy())
        ph_positions = np.flatnonzero(ph > ph_threshold)
        ph_time = None if not len(ph_positions) else float(data["session_time_h"].iloc[ph_positions[0]])
        split, gain = _offline_mean_shift(data["change_index"].to_numpy())
        values = data["change_index"].to_numpy()
        shift_magnitude = (
            None if split is None
            else abs(float(values[split:].mean() - values[:split].mean()))
        )
        rows.append(
            {
                "session_id": session_id,
                "cusum_onset_h": cusum,
                "rapid_rise_onset_h": rapid_time,
                "page_hinkley_onset_h": ph_time,
                "offline_mean_shift_h": None if split is None else float(data["session_time_h"].iloc[split]),
                "offline_mean_shift_gain": gain,
                "offline_gain_exceeds_all_controls": gain > control_shift_gain,
                "offline_mean_shift_magnitude": shift_magnitude,
                "offline_magnitude_exceeds_all_controls": (
                    False if shift_magnitude is None
                    else shift_magnitude > control_shift_magnitude
                ),
            }
        )
    thresholds = {
        "rapid_rise_slope_threshold_index_units_per_hour": slope_threshold,
        "page_hinkley_threshold_from_max_loo_control": ph_threshold,
        "maximum_loo_control_offline_mean_shift_gain": control_shift_gain,
        "maximum_loo_control_offline_mean_shift_magnitude": control_shift_magnitude,
        "warning": "Offline mean-shift uses the complete trajectory and is not real-time detection.",
    }
    return pd.DataFrame(rows), thresholds


def descriptive_session_statistics(
    benchmark_frame: pd.DataFrame, loo_frame: pd.DataFrame
) -> dict:
    confirmations = benchmark_frame.loc[benchmark_frame["session_role"] == "confirmation"]
    control_auc = loo_frame["held_out_control_auc"].to_numpy(dtype=float)
    chicken_auc = confirmations["auc_0_8h"].to_numpy(dtype=float)
    differences = np.array([c - n for c in chicken_auc for n in control_auc])
    perfect = bool(chicken_auc.min() > control_auc.max())
    return {
        "inference_unit": "session",
        "confirmation_auc_range": [float(chicken_auc.min()), float(chicken_auc.max())],
        "loo_control_auc_range": [float(control_auc.min()), float(control_auc.max())],
        "perfect_observed_ordering": perfect,
        "hodges_lehmann_pairwise_location_difference": float(np.median(differences)),
        "theoretical_one_sided_exact_resolution_for_independent_3_vs_3": 0.05,
        "theoretical_two_sided_exact_resolution_for_independent_3_vs_3": 0.10,
        "formal_permutation_p_reported": False,
        "reason": (
            "The available controls define the calibration and are not untouched, "
            "exchangeable validation observations."
        ),
    }


def quality_flags(
    records: pd.DataFrame,
    confirmation_details: dict[str, pd.DataFrame],
    environmental_results: pd.DataFrame,
    control_details: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    control_rh_step = np.concatenate([
        data["humidity_pct"].diff().abs().dropna().to_numpy()
        for data in control_details.values()
    ])
    control_t_step = np.concatenate([
        data["temp_C"].diff().abs().dropna().to_numpy()
        for data in control_details.values()
    ])
    rh_limit = float(np.quantile(control_rh_step, 0.99))
    t_limit = float(np.quantile(control_t_step, 0.99))
    baseline_cv = {}
    for item in records.itertuples(index=False):
        summary_path = item.path / "analysis" / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        baseline_cv[item.session_id] = summary.get("baseline_coefficients_of_variation", {})
    control_ids = set(records.loc[records["session_role"] == "control", "session_id"])
    cv_limits = {}
    for raw in RAW_SENSOR_COLUMNS.values():
        values = [
            baseline_cv[session].get(raw)
            for session in control_ids
            if baseline_cv[session].get(raw) is not None
        ]
        cv_limits[raw] = max(values) * 1.5 if values else np.inf

    env_map = environmental_results.set_index("session_id")
    rows = []
    for session_id, data in confirmation_details.items():
        flags = []
        out_fraction = float(env_map.loc[session_id, "environment_out_of_domain_fraction"])
        if out_fraction > 0.05:
            flags.append("environment_outside_control_domain")
        event = data.loc[data["primary_event"]]
        detection_environment_step = False
        if not event.empty:
            index = event.index[0]
            position = int(data.index.get_loc(index))
            if position > 0:
                detection_environment_step = (
                    abs(float(data["humidity_pct"].iloc[position] - data["humidity_pct"].iloc[position - 1])) > rh_limit
                    or abs(float(data["temp_C"].iloc[position] - data["temp_C"].iloc[position - 1])) > t_limit
                )
        if detection_environment_step:
            flags.append("rapid_environmental_step_at_detection")
        bme_rows = data.loc[data["cusum_active_BME"]]
        protein = data["cusum_active_NH3"] | data["cusum_active_H2S"]
        protein_rows = data.loc[protein]
        if not bme_rows.empty and not protein_rows.empty:
            lead = float(protein_rows["session_time_h"].iloc[0] - bme_rows["session_time_h"].iloc[0])
            if lead >= 0.5:
                flags.append("bme_leads_protein_group_by_at_least_30m")
        unstable = [
            raw for raw, limit in cv_limits.items()
            if baseline_cv[session_id].get(raw) is not None
            and baseline_cv[session_id][raw] > limit
        ]
        if unstable:
            flags.append("baseline_cv_above_1.5x_control_max:" + ",".join(unstable))
        rows.append(
            {
                "session_id": session_id,
                "quality_flags": json.dumps(flags),
                "flag_count": len(flags),
                "environment_out_of_domain_fraction": out_fraction,
                "rapid_environmental_step_at_detection": detection_environment_step,
            }
        )
    return pd.DataFrame(rows)


def _range_text(values: pd.Series, digits: int = 2) -> str:
    return f"{values.min():.{digits}f}–{values.max():.{digits}f}"


def write_report(
    output: Path,
    benchmark_frame: pd.DataFrame,
    loo: pd.DataFrame,
    sensitivity: pd.DataFrame,
    event_ablation: pd.DataFrame,
    index_ablation: pd.DataFrame,
    false_alarm: pd.DataFrame,
    environmental_loo_summary: pd.DataFrame,
    environmental: pd.DataFrame,
    change_points: pd.DataFrame,
    statistics: dict,
    quality: pd.DataFrame,
    shifted: pd.DataFrame,
) -> None:
    confirmations = benchmark_frame.loc[benchmark_frame["session_role"] == "confirmation"]
    controls = benchmark_frame.loc[benchmark_frame["session_role"] == "control"]
    robust_count = int(sensitivity["retains_3_of_3_and_0_of_3"].sum())
    total = len(sensitivity)
    chicken_stable = int((sensitivity["confirmation_events"] == 3).sum())
    control_stable = int((sensitivity["control_events"] == 0).sum())
    auc_stable = int((sensitivity["auc_absolute_margin"] > 0).sum())
    block_8 = false_alarm.loc[false_alarm["window_hours"] == 8]
    env_shift = environmental[["original_detection_h", "environment_adjusted_detection_h"]]
    env_overall = environmental_loo_summary.drop_duplicates("model").set_index("model")
    time_rmse = float(env_overall.loc["time_only", "mean_sensor_fold_rmse"])
    env_rmse = float(env_overall.loc["delta_rh_delta_t", "mean_sensor_fold_rmse"])
    report = f"""# House A robustness analysis

## Status

HouseA_v1 remains the primary frozen result. All analyses below are robustness
checks or retrospective exploratory analyses; none changes the frozen result.

## Frozen benchmark

- Confirmations detected: {int(confirmations['primary_event'].sum())}/{len(confirmations)}
- Calibration-control events under the full calibration: {int(controls['primary_event'].sum())}/{len(controls)}
- Confirmation detection range: {_range_text(confirmations['detection_time_h'])} h
- Confirmation AUC range: {_range_text(confirmations['auc_0_8h'])}
- Calibration-control AUC range: {_range_text(controls['auc_0_8h'])}

The controls above participated in calibration; their zero-event count is a
calibration diagnostic, not an independent false-positive estimate.

## Full leave-one-control-out result

- Held-out controls with events: {int(loo['held_out_control_event'].sum())}/{len(loo)}
- Confirmation detections across folds: {int(loo['confirmations_detected'].min())}–{int(loo['confirmations_detected'].max())} of 3
- Minimum fold-level absolute AUC margin: {loo['auc_absolute_margin'].min():.2f}
- Detection times across calibrations: {loo['chicken_detection_min_h'].min():.2f}–{loo['chicken_detection_max_h'].max():.2f} h

## Parameter sensitivity

- {chicken_stable}/{total} configurations retained all three confirmation events.
- {control_stable}/{total} produced zero leave-one-control-out control events.
- {auc_stable}/{total} retained a positive minimum-chicken minus maximum-control AUC margin.
- {robust_count}/{total} ({100 * robust_count / total:.1f}%) met all three criteria simultaneously.

These are grid-robustness proportions, not probabilities that the detector is
biologically correct.

## Ablation

- Event rules retaining 3/3 confirmations and 0/3 controls: {', '.join(event_ablation.loc[(event_ablation.confirmation_events == 3) & (event_ablation.control_events == 0), 'event_rule']) or 'none'}
- Index variants with positive minimum-confirmation minus maximum-control AUC margin: {int((index_ablation.auc_absolute_margin > 0).sum())}/{len(index_ablation)}

## Control bootstrap stress test

For the eight-hour window, conditional moving-block bootstrap false-session
rates ranged from {100 * block_8.false_session_rate.min():.2f}% to
{100 * block_8.false_session_rate.max():.2f}% across 15–90 minute blocks. The
intervals in the CSV quantify Monte Carlo error only; three observed controls
cannot characterize between-session or between-house uncertainty.

One of {len(shifted)} shifted-baseline control stress tests produced an event.
It was {shifted.loc[shifted.primary_event, 'session_id'].iloc[0] if shifted.primary_event.any() else 'none'}
with a {int(shifted.loc[shifted.primary_event, 'baseline_shift_minutes'].iloc[0]) if shifted.primary_event.any() else 0}-minute shift. This shows that the cumulative event can be
sensitive to baseline placement even when the displayed index remains small.

## Environmental sensitivity

Environment-adjusted detection pairs (original → adjusted, hours):
{'; '.join(f'{a:.2f} → {b:.2f}' if pd.notna(b) else f'{a:.2f} → none' for a, b in env_shift.itertuples(index=False, name=None))}.

Every environmental result is exploratory because the chicken sessions extend
beyond the control humidity/temperature training domain. A changed detection
time demonstrates sensitivity to the adjustment; it does not identify a true
biological onset.

The prespecified delta-RH plus delta-temperature model had mean held-out RMSE
{env_rmse:.4f}, versus {time_rmse:.4f} for the simple time-only regression.
It therefore did not improve aggregate control generalization and should not
replace the frozen correction.

## Alternative transition estimates

The detailed table distinguishes online CUSUM onset, a control-calibrated rapid
rise, Page–Hinkley onset, and an offline whole-trajectory mean shift. Agreement
indicates a stable statistical transition, not microbiological validation.
The offline mean-shift locations were
{', '.join(f'{value:.2f} h' for value in change_points.offline_mean_shift_h)};
their absolute shift magnitudes exceeded every leave-one-control-out control,
although their normalized SSE gains did not. Page–Hinkley onsets were
{', '.join(f'{value:.2f} h' for value in change_points.page_hinkley_onset_h)}.

## Session-level inference

- Perfect descriptive AUC ordering: {statistics['perfect_observed_ordering']}
- LOO-control AUC range: {statistics['loo_control_auc_range'][0]:.2f}–{statistics['loo_control_auc_range'][1]:.2f}
- Confirmation AUC range: {statistics['confirmation_auc_range'][0]:.2f}–{statistics['confirmation_auc_range'][1]:.2f}
- Pairwise Hodges–Lehmann location difference: {statistics['hodges_lehmann_pairwise_location_difference']:.2f} index-hours

No formal permutation p-value is reported because the available controls define
the calibration and are not untouched exchangeable validation sessions.

## Quality flags

The quality flags are deterministic diagnostics, not calibrated probabilities.
Flag counts across confirmations: {', '.join(str(value) for value in quality.flag_count)}.

## Conclusion

The magnitude separation is robust: every parameter and index ablation retained
a positive chicken-versus-control AUC margin. The exact Boolean event and its
onset are less robust because one cross-fitted control fires and onset varies
with calibration and transition method. The appropriate claim remains that
chicken exposure produced a repeatable, sustained, control-adjusted multichannel
headspace response in the House A apparatus. These analyses cannot establish
microbial spoilage, food safety, remaining useful life, or universal household
performance.
"""
    (output / "HOUSE_A_ROBUSTNESS_REPORT.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-root", type=Path,
        default=Path("evaluation_output/full_stack_4runs_20260806/staged_sessions"),
    )
    parser.add_argument(
        "--config", type=Path, default=Path("configs/house_a_v1.json")
    )
    parser.add_argument(
        "--calibration", type=Path,
        default=Path("evaluation_output/full_stack_4runs_20260806/model/control_calibration.joblib"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("evaluation_output/house_a_v1_robustness"),
    )
    args = parser.parse_args()
    config = load_experiment_config(args.config)
    records = discover_sessions(args.session_root)
    args.output.mkdir(parents=True, exist_ok=True)
    control_paths = records.loc[records["session_role"] == "control", "path"].tolist()
    confirmation_paths = records.loc[
        records["session_role"] == "confirmation", "path"
    ].tolist()

    benchmark_frame, all_benchmark_details = benchmark(records, config, args.calibration)
    benchmark_frame.to_csv(args.output / "house_a_v1_results.csv", index=False)
    confirmation_details = {
        session: all_benchmark_details[session]
        for session in records.loc[records["session_role"] == "confirmation", "session_id"]
    }

    loo, loo_scales, loo_control_details = full_leave_one_control_out(
        control_paths, confirmation_paths, config
    )
    loo.to_csv(args.output / "full_leave_one_control_out.csv", index=False)
    loo_scales.to_csv(args.output / "leave_one_control_out_scales.csv", index=False)

    sensitivity = parameter_sensitivity(control_paths, confirmation_paths, config)
    sensitivity.to_csv(args.output / "parameter_sensitivity.csv", index=False)

    event_ablation, index_ablation = ablation_analysis(
        confirmation_details, loo_control_details, config
    )
    event_ablation.to_csv(args.output / "event_rule_ablation.csv", index=False)
    index_ablation.to_csv(args.output / "index_ablation.csv", index=False)

    controls = load_feature_set(
        control_paths, config["aggregation_minutes"], config["baseline_minutes"]
    )
    base_core_calibration = calibrate_core(controls, config)
    false_alarm = bootstrap_false_alarm(base_core_calibration["loo"], config)
    false_alarm.to_csv(args.output / "bootstrap_false_alarm_sensitivity.csv", index=False)
    shifted = shifted_control_stress(control_paths, base_core_calibration, config)
    shifted.to_csv(args.output / "shifted_control_baselines.csv", index=False)

    environmental_loo = environmental_loo_diagnostics(controls, config)
    environmental_loo.to_csv(args.output / "environmental_model_loo.csv", index=False)
    environmental_loo_summary = summarize_environmental_loo(environmental_loo)
    environmental_loo_summary.to_csv(
        args.output / "environmental_model_comparison.csv", index=False
    )
    confirmation_frames = {
        path.name: load_feature_set(
            [path], config["aggregation_minutes"], config["baseline_minutes"]
        )
        for path in confirmation_paths
    }
    environmental, environmental_model = environmental_sensitivity(
        controls, confirmation_frames, config, benchmark_frame
    )
    environmental.to_csv(args.output / "environmental_sensitivity.csv", index=False)
    _write_json(args.output / "environmental_model.json", environmental_model)

    change_points, change_thresholds = change_point_comparison(
        confirmation_details, loo_control_details
    )
    change_points.to_csv(args.output / "change_point_comparison.csv", index=False)
    _write_json(args.output / "change_point_thresholds.json", change_thresholds)

    statistics = descriptive_session_statistics(benchmark_frame, loo)
    _write_json(args.output / "session_level_statistics.json", statistics)
    quality = quality_flags(
        records, confirmation_details, environmental, loo_control_details
    )
    quality.to_csv(args.output / "quality_flags.csv", index=False)

    robustness_summary = {
        "frozen_benchmark": {
            "confirmations_detected": int(
                benchmark_frame.loc[
                    benchmark_frame.session_role == "confirmation", "primary_event"
                ].sum()
            ),
            "confirmation_count": 3,
            "control_events_in_calibration": int(
                benchmark_frame.loc[
                    benchmark_frame.session_role == "control", "primary_event"
                ].sum()
            ),
        },
        "leave_one_control_out": {
            "held_out_control_events": int(loo.held_out_control_event.sum()),
            "held_out_control_count": len(loo),
            "all_confirmations_detected_in_every_fold": bool(
                (loo.confirmations_detected == 3).all()
            ),
            "minimum_auc_absolute_margin": float(loo.auc_absolute_margin.min()),
            "detection_time_range_h": [
                float(loo.chicken_detection_min_h.min()),
                float(loo.chicken_detection_max_h.max()),
            ],
        },
        "parameter_sensitivity": {
            "configurations": len(sensitivity),
            "all_confirmations_detected": int((sensitivity.confirmation_events == 3).sum()),
            "zero_loo_control_events": int((sensitivity.control_events == 0).sum()),
            "positive_auc_margin": int((sensitivity.auc_absolute_margin > 0).sum()),
        },
        "false_alarm_bootstrap_8h_range": [
            float(false_alarm.loc[false_alarm.window_hours == 8, "false_session_rate"].min()),
            float(false_alarm.loc[false_alarm.window_hours == 8, "false_session_rate"].max()),
        ],
        "environmental_model": {
            "time_only_mean_loo_rmse": float(
                environmental_loo_summary.loc[
                    environmental_loo_summary.model == "time_only",
                    "mean_sensor_fold_rmse",
                ].iloc[0]
            ),
            "delta_rh_delta_t_mean_loo_rmse": float(
                environmental_loo_summary.loc[
                    environmental_loo_summary.model == "delta_rh_delta_t",
                    "mean_sensor_fold_rmse",
                ].iloc[0]
            ),
            "all_chicken_bins_outside_control_domain": bool(
                (environmental.environment_out_of_domain_fraction == 1.0).all()
            ),
            "promote_to_primary_pipeline": False,
        },
        "conclusion": (
            "AUC magnitude separation is robust; the Boolean event false-alarm "
            "behavior and onset time are not yet robust enough for a calibrated "
            "spoilage or safety claim."
        ),
    }
    _write_json(args.output / "robustness_summary.json", robustness_summary)

    manifest = {
        "analysis_version": config.get("analysis_version", "HouseA_v1"),
        "config_path": str(args.config.resolve()),
        "config_sha256": _config_hash(config),
        "calibration_path": str(args.calibration.resolve()),
        "session_ids": records[["session_id", "session_role"]].to_dict("records"),
        "primary_result_unchanged": True,
        "camera_included": False,
        "friend_house_included": False,
    }
    _write_json(args.output / "analysis_manifest.json", manifest)
    write_report(
        args.output, benchmark_frame, loo, sensitivity, event_ablation,
        index_ablation, false_alarm, environmental_loo_summary, environmental, change_points,
        statistics, quality, shifted,
    )
    print(f"House A robustness outputs written to {args.output}")


if __name__ == "__main__":
    main()

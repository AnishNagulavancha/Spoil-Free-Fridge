"""Control-calibrated, label-free sensor change detection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler


SENSOR_COLUMNS = {
    "NH3": "v_NH3_delta_pct",
    "H2S": "v_H2S_delta_pct",
    "CH4": "v_CH4_delta_pct",
    "BME": "bme_delta_log_inverted",
}


def _mad_scale(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return 1.0
    median = np.median(values)
    scale = 1.4826 * np.median(np.abs(values - median))
    return max(float(scale), 1e-9)


def prepare_five_minute_sessions(frame: pd.DataFrame, minutes: int = 5) -> pd.DataFrame:
    """Create insertion-relative, equally spaced robust summaries per session."""
    parts = []
    for session_id, group in frame.groupby("session_id", sort=False):
        group = group.sort_values("elapsed_s").copy()
        start = float(group["elapsed_s"].min())
        group["session_minute"] = (group["elapsed_s"] - start) / 60.0
        group["time_bin"] = np.rint(group["session_minute"] / minutes).astype(int)
        numeric = group.select_dtypes(include=[np.number]).groupby(group["time_bin"]).median()
        numeric["session_id"] = session_id
        numeric["time_bin"] = numeric.index.astype(int)
        numeric["session_minute"] = numeric["time_bin"] * minutes
        numeric["session_time_h"] = numeric["session_minute"] / 60.0
        parts.append(numeric.reset_index(drop=True))
    return pd.concat(parts, ignore_index=True)


def _smooth_control_curve(training: pd.DataFrame, column: str,
                          smoothing_bins: int) -> pd.Series:
    curve = training.pivot_table(index="time_bin", columns="session_id",
                                 values=column, aggfunc="median").mean(axis=1)
    full_index = np.arange(int(curve.index.min()), int(curve.index.max()) + 1)
    curve = curve.reindex(full_index).interpolate(limit_direction="both")
    return curve.rolling(smoothing_bins, center=True, min_periods=1).mean()


def _evaluate_curve(curve: pd.Series, bins: pd.Series) -> np.ndarray:
    return np.interp(bins.to_numpy(dtype=float), curve.index.to_numpy(dtype=float),
                     curve.to_numpy(dtype=float), left=float(curve.iloc[0]),
                     right=float(curve.iloc[-1]))


def _cusum_values(z: np.ndarray, k: float, h: float,
                  persistence: int) -> tuple[np.ndarray, np.ndarray]:
    score = np.zeros(len(z), dtype=float)
    active = np.zeros(len(z), dtype=bool)
    streak = 0
    for i, value in enumerate(np.nan_to_num(z, nan=0.0)):
        score[i] = max(0.0, (score[i - 1] if i else 0.0) + value - k)
        streak = streak + 1 if score[i] > h else 0
        active[i] = streak >= persistence
    return score, active


def _primary_event(active: dict[str, np.ndarray]) -> np.ndarray:
    protein = active["NH3"] | active["H2S"]
    return protein & active["BME"]


def _bootstrap_h(loo: pd.DataFrame, candidates: list[float], config: dict,
                 random_state: int) -> tuple[float, dict[str, float]]:
    rng = np.random.default_rng(random_state)
    count = int(config["control"]["bootstrap_sessions"])
    length = round(config["primary_auc_hours"] * 60 / config["aggregation_minutes"])
    block = int(config["control"]["bootstrap_block_bins"])
    k = float(config["cusum"]["k"])
    persistence = int(config["cusum"]["persistence_bins"])
    arrays = [g[[f"z_{s}" for s in SENSOR_COLUMNS]].to_numpy(dtype=float)
              for _, g in loo.groupby("session_id", sort=False)]
    event_counts = {float(h): 0 for h in candidates}
    for _ in range(count):
        blocks = []
        while sum(len(item) for item in blocks) < length:
            source = arrays[int(rng.integers(len(arrays)))]
            if len(source) <= block:
                piece = source
            else:
                start = int(rng.integers(0, len(source) - block + 1))
                piece = source[start:start + block]
            blocks.append(piece)
        sample = np.concatenate(blocks)[:length]
        for h in candidates:
            active = {sensor: _cusum_values(sample[:, i], k, h, persistence)[1]
                      for i, sensor in enumerate(SENSOR_COLUMNS)}
            event_counts[float(h)] += bool(_primary_event(active).any())
    rates = {str(h): event_counts[float(h)] / count for h in candidates}
    target = float(config["control"]["target_false_session_rate"])
    valid = [float(h) for h in candidates if rates[str(h)] <= target]
    chosen = min(valid) if valid else max(float(h) for h in candidates)
    return chosen, rates


def calibrate_controls(frame: pd.DataFrame, config: dict,
                       random_state: int = 42) -> dict:
    """Fit drift, LOO null scale, CUSUM h, PCA and Isolation Forest on controls."""
    controls = prepare_five_minute_sessions(frame, int(config["aggregation_minutes"]))
    sessions = list(controls["session_id"].unique())
    minimum = int(config["control"]["minimum_sessions"])
    if len(sessions) < minimum:
        raise ValueError(f"Control calibration requires at least {minimum} sessions")
    missing = [column for column in SENSOR_COLUMNS.values() if column not in controls]
    if missing:
        raise ValueError(f"Missing sensor delta features: {', '.join(missing)}")

    smoothing = int(config["control"]["drift_smoothing_bins"])
    loo_parts = []
    for held_out in sessions:
        train = controls[controls.session_id != held_out]
        test = controls[controls.session_id == held_out].copy()
        for sensor, column in SENSOR_COLUMNS.items():
            curve = _smooth_control_curve(train, column, smoothing)
            test[f"residual_{sensor}"] = test[column] - _evaluate_curve(curve, test["time_bin"])
        loo_parts.append(test)
    loo = pd.concat(loo_parts, ignore_index=True)
    scales = {sensor: _mad_scale(loo[f"residual_{sensor}"].to_numpy())
              for sensor in SENSOR_COLUMNS}
    directions = config["sensor_direction"]
    for sensor in SENSOR_COLUMNS:
        loo[f"z_{sensor}"] = directions[sensor] * loo[f"residual_{sensor}"] / scales[sensor]

    candidates = [float(value) for value in config["cusum"]["h_candidates"]]
    chosen_h, false_rates = _bootstrap_h(loo, candidates, config, random_state)
    drift = {sensor: _smooth_control_curve(controls, column, smoothing)
             for sensor, column in SENSOR_COLUMNS.items()}
    z_columns = [f"z_{sensor}" for sensor in SENSOR_COLUMNS]
    scaler = RobustScaler().fit(loo[z_columns])
    null_x = scaler.transform(loo[z_columns])
    pca = PCA(n_components=2, random_state=random_state).fit(null_x)
    isolation = IsolationForest(n_estimators=500, contamination="auto",
                                random_state=random_state).fit(null_x)
    return {
        "protocol_version": config.get("protocol_version"),
        "aggregation_minutes": int(config["aggregation_minutes"]),
        "sensor_direction": dict(config["sensor_direction"]),
        "drift": {sensor: {"time_bin": curve.index.to_numpy(), "value": curve.to_numpy()}
                  for sensor, curve in drift.items()},
        "scales": scales,
        "cusum_h": chosen_h,
        "bootstrap_false_session_rates": false_rates,
        "scaler": scaler,
        "pca": pca,
        "isolation_forest": isolation,
        "null_z_columns": z_columns,
        "control_sessions": sessions,
        "loo_residuals": loo,
    }


def _stored_curve(calibration: dict, sensor: str) -> pd.Series:
    item = calibration["drift"][sensor]
    return pd.Series(item["value"], index=item["time_bin"], dtype=float)


def score_session(frame: pd.DataFrame, calibration: dict, config: dict) -> tuple[pd.DataFrame, dict]:
    """Apply frozen control calibration and return per-bin change metrics."""
    if calibration.get("protocol_version") != config.get("protocol_version"):
        raise ValueError("Calibration and experiment config protocol versions do not match")
    if calibration.get("aggregation_minutes") != int(config["aggregation_minutes"]):
        raise ValueError("Calibration and experiment config aggregation intervals do not match")
    if calibration.get("sensor_direction") != config["sensor_direction"]:
        raise ValueError("Sensor directions changed after calibration; recalibrate controls")
    data = prepare_five_minute_sessions(frame, int(config["aggregation_minutes"]))
    if data.session_id.nunique() != 1:
        raise ValueError("score_session expects exactly one session")
    directions = config["sensor_direction"]
    for sensor, column in SENSOR_COLUMNS.items():
        drift = _evaluate_curve(_stored_curve(calibration, sensor), data["time_bin"])
        data[f"control_drift_{sensor}"] = drift
        data[f"adjusted_{sensor}"] = data[column] - drift
        data[f"z_{sensor}"] = directions[sensor] * data[f"adjusted_{sensor}"] / calibration["scales"][sensor]
        data[f"channel_index_{sensor}"] = (
            data[f"z_{sensor}"].clip(lower=0) / float(config["index"]["full_scale_z"])
        ).clip(upper=1)

    weights = config["index"]["weights"]
    total = sum(float(weights[s]) for s in SENSOR_COLUMNS)
    data["change_index"] = 100 * sum(
        float(weights[s]) * data[f"channel_index_{s}"] for s in SENSOR_COLUMNS
    ) / total

    k = float(config["cusum"]["k"])
    h = float(calibration["cusum_h"])
    persistence = int(config["cusum"]["persistence_bins"])
    active = {}
    for sensor in SENSOR_COLUMNS:
        score, active[sensor] = _cusum_values(data[f"z_{sensor}"].to_numpy(), k, h, persistence)
        data[f"cusum_{sensor}"] = score
        data[f"cusum_active_{sensor}"] = active[sensor]
    data["protein_gas_active"] = active["NH3"] | active["H2S"]
    data["primary_event"] = _primary_event(active)
    data["supporting_channel_count"] = np.column_stack(list(active.values())).sum(axis=1)

    z_columns = [f"z_{sensor}" for sensor in SENSOR_COLUMNS]
    x = calibration["scaler"].transform(data[z_columns])
    components = calibration["pca"].transform(x)
    data["pca_1"] = components[:, 0]
    data["pca_2"] = components[:, 1]
    data["anomaly_score"] = -calibration["isolation_forest"].decision_function(x)
    data["is_anomaly"] = calibration["isolation_forest"].predict(x) == -1

    event_rows = data.loc[data["primary_event"]]
    detection_h = None if event_rows.empty else float(event_rows["session_time_h"].iloc[0])
    auc_h = float(config["primary_auc_hours"])
    interval_h = float(config["aggregation_minutes"]) / 60.0
    expected = int(round(auc_h / interval_h)) + 1
    window = data.loc[data["session_time_h"].between(0, auc_h)].copy()
    coverage = min(1.0, len(window) / expected)
    max_gap_h = float(config["maximum_interpolation_gap_minutes"]) / 60.0
    gaps_ok = window["session_time_h"].diff().dropna().le(max_gap_h + interval_h + 1e-9).all()
    span_ok = not window.empty and float(window["session_time_h"].max()) >= auc_h - interval_h
    auc_valid = coverage >= float(config["minimum_auc_coverage"]) and gaps_ok and span_ok
    auc_value = float(np.trapezoid(window["change_index"], window["session_time_h"])) if auc_valid else None
    summary = {
        "session_id": str(data["session_id"].iloc[0]),
        "cusum_h": h,
        "time_to_sustained_change_h": detection_h,
        "maximum_change_index": float(data["change_index"].max()),
        "index_at_fixed_hours": {},
        "auc_window_h": [0, auc_h],
        "auc_coverage": coverage,
        "auc_valid": bool(auc_valid),
        "auc_change_index_hours": auc_value,
        "primary_event_detected": bool(data["primary_event"].any()),
        "adjusted_sensor_correlation": (
            data[[f"adjusted_{sensor}" for sensor in SENSOR_COLUMNS]].corr().to_dict()
        ),
        "supporting_channels_are_not_assumed_independent": True,
    }
    for hour in range(2, int(auc_h) + 1, 2):
        position = int((data["session_time_h"] - hour).abs().argmin())
        nearest = data.iloc[position]
        summary["index_at_fixed_hours"][str(hour)] = (
            float(nearest["change_index"])
            if abs(float(nearest["session_time_h"]) - hour) <= interval_h + 1e-9
            else None
        )
    return data, summary

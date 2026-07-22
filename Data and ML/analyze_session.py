"""Clean one logger session and create baseline-relative sensor features.

This stage deliberately does not combine sensors into a deterioration score.
The control-calibrated Change Index and event detection are produced later by
run_models.py using the single frozen weight set in experiment_config.json.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from experiment_config import load_experiment_config


GAS_COLUMNS = ("v_NH3", "v_H2S", "v_CH4")
NUMERIC_COLUMNS = (
    "elapsed_s", "adc_NH3", "v_NH3", "adc_CH4", "v_CH4", "adc_H2S",
    "v_H2S", "temp_C", "pressure_Pa", "humidity_pct", "bme_gas_ohms",
)


@dataclass(frozen=True)
class AnalysisConfig:
    expected_protocol_version: str | None = None
    baseline_minutes: float = 30.0
    feature_resample_seconds: int = 60
    slope_windows_minutes: tuple[int, ...] = (5, 15, 30)
    min_window_points: int = 5


def load_and_clean(session_dir: Path) -> tuple[pd.DataFrame, dict, dict]:
    """Read a session, discard warmup/corrupt rows, and index by timestamp."""
    csv_path = session_dir / "sensor_log.csv"
    metadata_path = session_dir / "metadata.json"
    if not csv_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError(
            f"Expected sensor_log.csv and metadata.json in {session_dir}"
        )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw = pd.read_csv(csv_path)
    required = {"timestamp_iso", "phase", *NUMERIC_COLUMNS}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise ValueError(f"sensor_log.csv is missing columns: {', '.join(missing)}")

    report = {"rows_read": int(len(raw))}
    raw["timestamp_iso"] = pd.to_datetime(raw["timestamp_iso"], errors="coerce")
    for column in NUMERIC_COLUMNS:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw.replace([np.inf, -np.inf], np.nan, inplace=True)

    logging = raw.loc[raw["phase"].astype(str).str.casefold() != "warmup"].copy()
    report["warmup_rows_discarded"] = int(len(raw) - len(logging))

    essential = ["timestamp_iso", "elapsed_s", *GAS_COLUMNS, "temp_C", "bme_gas_ohms"]
    valid = logging[essential].notna().all(axis=1)
    valid &= logging["elapsed_s"].ge(0)
    valid &= logging["temp_C"].between(-20, 80)
    valid &= logging["humidity_pct"].between(0, 100) | logging["humidity_pct"].isna()
    valid &= logging[list(GAS_COLUMNS)].ge(0).all(axis=1)
    valid &= logging[list(GAS_COLUMNS)].le(5.5).all(axis=1)
    valid &= logging["bme_gas_ohms"].gt(0)
    clean = logging.loc[valid].sort_values(["timestamp_iso", "elapsed_s"]).copy()
    clean = clean.drop_duplicates(subset=["timestamp_iso", "elapsed_s"], keep="first")

    report["corrupt_or_invalid_rows_discarded"] = int(len(logging) - len(clean))
    report["rows_kept"] = int(len(clean))
    if clean.empty:
        raise ValueError("No valid logging rows remain after cleaning")

    clean.set_index("timestamp_iso", inplace=True, drop=True)
    clean.index.name = "timestamp"
    return clean, metadata, report


def _rolling_slope(
    elapsed_s: np.ndarray,
    values: np.ndarray,
    window_minutes: float,
    min_points: int,
) -> np.ndarray:
    """Least-squares rolling slope, expressed as feature units per hour."""
    result = np.full(len(values), np.nan)
    window_s = window_minutes * 60.0
    for end in range(len(values)):
        start = int(np.searchsorted(elapsed_s, elapsed_s[end] - window_s, side="left"))
        x = elapsed_s[start:end + 1]
        y = values[start:end + 1]
        good = np.isfinite(x) & np.isfinite(y)
        if good.sum() < min_points or np.ptp(x[good]) <= 0:
            continue
        x_hours = (x[good] - x[good][0]) / 3600.0
        result[end] = np.polyfit(x_hours, y[good], 1)[0]
    return result


def build_features(
    clean: pd.DataFrame, config: AnalysisConfig
) -> tuple[pd.DataFrame, dict]:
    numeric = clean.select_dtypes(include=[np.number]).resample(
        f"{config.feature_resample_seconds}s"
    ).median()
    nonnumeric = clean.select_dtypes(exclude=[np.number]).resample(
        f"{config.feature_resample_seconds}s"
    ).first()
    data = numeric.join(nonnumeric, how="left").dropna(
        subset=["elapsed_s", *GAS_COLUMNS, "temp_C", "bme_gas_ohms"]
    )
    logging_start_s = float(data["elapsed_s"].min())
    baseline_end_s = logging_start_s + config.baseline_minutes * 60.0
    baseline_mask = data["elapsed_s"].le(baseline_end_s)
    baseline = data.loc[baseline_mask]
    if len(baseline) < config.min_window_points:
        raise ValueError(
            f"Only {len(baseline)} baseline rows found; need at least "
            f"{config.min_window_points}"
        )
    if float(baseline["elapsed_s"].max() - logging_start_s) < config.baseline_minutes * 60 * 0.8:
        raise ValueError("Session does not cover at least 80% of the requested baseline")

    baseline_columns = (*GAS_COLUMNS, "bme_gas_ohms")
    means = baseline[list(baseline_columns)].mean()
    if (means <= 0).any():
        raise ValueError("Baseline means must be positive")

    for column in GAS_COLUMNS:
        data[f"{column}_delta_pct"] = (data[column] / means[column]) - 1.0
    data["bme_delta_log_inverted"] = np.log(means["bme_gas_ohms"] / data["bme_gas_ohms"])

    elapsed = data["elapsed_s"].to_numpy(dtype=float)
    trend_sources = (*GAS_COLUMNS, "bme_delta_log_inverted")
    for source in trend_sources:
        values = data[source].to_numpy(dtype=float)
        for minutes in config.slope_windows_minutes:
            slope_name = f"{source}_slope_{minutes}m"
            data[slope_name] = _rolling_slope(
                elapsed, values, minutes, config.min_window_points
            )
            data[f"{source}_accel_{minutes}m"] = _rolling_slope(
                elapsed,
                data[slope_name].to_numpy(dtype=float),
                minutes,
                config.min_window_points,
            )
            data[f"{source}_volatility_{minutes}m"] = (
                data[source]
                .rolling(f"{minutes}min", min_periods=config.min_window_points)
                .std()
            )

    dt_hours = data["elapsed_s"].diff().clip(lower=0).fillna(0) / 3600.0
    q10_factor = np.power(2.0, (data["temp_C"] - 4.0) / 10.0)
    # Trapezoidal integration is less sensitive to sampling interval changes.
    data["q10_factor"] = q10_factor
    data["biological_age_h"] = (
        ((q10_factor + q10_factor.shift(1)) / 2).fillna(q10_factor) * dt_hours
    ).cumsum()

    data["is_baseline"] = baseline_mask

    baseline_cv = (baseline[list(baseline_columns)].std() / means).replace(
        [np.inf, -np.inf], np.nan
    )
    summary = {
        "baseline_start_elapsed_s": logging_start_s,
        "baseline_end_elapsed_s": baseline_end_s,
        "baseline_rows": int(len(baseline)),
        "feature_rows": int(len(data)),
        "feature_resample_seconds": config.feature_resample_seconds,
        "baseline_means": {key: float(value) for key, value in means.items()},
        "baseline_coefficients_of_variation": {
            key: (None if pd.isna(value) else float(value))
            for key, value in baseline_cv.items()
        },
        "latest_biological_age_h": float(data["biological_age_h"].iloc[-1]),
    }
    return data, summary


def analyze(session_dir: Path, output_dir: Path | None, config: AnalysisConfig) -> None:
    clean, metadata, cleaning_report = load_and_clean(session_dir)
    if (
        config.expected_protocol_version is not None
        and metadata.get("protocol_version") != config.expected_protocol_version
    ):
        raise ValueError(
            f"Session protocol_version={metadata.get('protocol_version')!r}; "
            f"expected {config.expected_protocol_version!r}"
        )
    features, summary = build_features(clean, config)
    destination = output_dir or session_dir / "analysis"
    destination.mkdir(parents=True, exist_ok=True)
    features.to_csv(destination / "features.csv", index=True)
    payload = {
        "protocol_version": metadata.get("protocol_version"),
        "session_id": metadata.get("session_id"),
        "session_role": metadata.get("session_role"),
        "site_id": metadata.get("site_id"),
        "pcb_design_id": metadata.get("pcb_design_id"),
        "device_id": metadata.get("device_id"),
        "container_id": metadata.get("container_id"),
        "food_name": metadata.get("food_name"),
        "status": "prototype_features_only_not_a_food_safety_assessment",
        "cleaning": cleaning_report,
        "config": asdict(config),
        **summary,
    }
    (destination / "summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(f"Wrote {destination / 'features.csv'}")
    print(f"Wrote {destination / 'summary.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path, help="Folder containing session files")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--config", type=Path, default=Path("experiment_config.json"))
    args = parser.parse_args()
    experiment = load_experiment_config(args.config)
    analyze(
        args.session_dir,
        args.output_dir,
        AnalysisConfig(
            expected_protocol_version=experiment["protocol_version"],
            baseline_minutes=float(experiment["baseline_minutes"]),
        ),
    )


if __name__ == "__main__":
    main()

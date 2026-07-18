"""Calibrate empty controls and score pilot/confirmation sensor sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np

from experiment_config import load_experiment_config
from model_data import load_sessions
from unsupervised_models import calibrate_controls, score_session


def _roles(session_dirs: list[Path]) -> dict[str, str | None]:
    roles = {}
    for path in session_dirs:
        metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        roles[path.name] = metadata.get("session_role")
    return roles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--controls", nargs="+", type=Path,
                        help="Calibrate a new artifact from empty-control sessions")
    source.add_argument("--calibration", type=Path,
                        help="Reuse an existing frozen control_calibration.joblib")
    parser.add_argument("--targets", nargs="*", default=[], type=Path)
    parser.add_argument("--config", type=Path, default=Path("experiment_config.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("model_output"))
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    config = load_experiment_config(args.config)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.controls:
        if config.get("sensor_direction_source") not in {
            "datasheet_and_independent_response_test", "excluded_chicken_pilot"
        }:
            raise ValueError(
                "Control calibration requires verified sensor_direction and a documented "
                "sensor_direction_source before one-sided CUSUM calibration"
            )
        control_roles = _roles(args.controls)
        invalid = {name: role for name, role in control_roles.items()
                   if role != "control"}
        if invalid:
            raise ValueError(f"Control folders have non-control session_role values: {invalid}")
        controls = load_sessions(args.controls, labelled=False,
                                 resample_minutes=int(config["aggregation_minutes"]))
        calibration = calibrate_controls(controls, config, args.random_state)
        loo = calibration.pop("loo_residuals")
        loo.to_csv(args.output_dir / "control_loo_residuals.csv", index=False)
        joblib.dump(calibration, args.output_dir / "control_calibration.joblib")
        calibration_summary = {
            "protocol_version": config.get("protocol_version"),
            "control_sessions": calibration["control_sessions"],
            "loo_scales": calibration["scales"],
            "selected_cusum_h": calibration["cusum_h"],
            "bootstrap_false_session_rates": calibration["bootstrap_false_session_rates"],
            "control_null_channel_correlation": (
                loo[[f"z_{sensor}" for sensor in ("NH3", "H2S", "CH4", "BME")]]
                .corr().to_dict()
            ),
            "warning": "Engineering calibration, not a food-safety assessment.",
        }
        (args.output_dir / "control_calibration.json").write_text(
            json.dumps(calibration_summary, indent=2), encoding="utf-8")
    else:
        calibration = joblib.load(args.calibration)

    (args.output_dir / "config_used.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8")

    summaries = []
    target_roles = {}
    for target in args.targets:
        role = _roles([target])[target.name]
        if role not in {"pilot", "confirmation"}:
            raise ValueError(
                f"Target {target.name} must have session_role pilot or confirmation; got {role!r}"
            )
        target_roles[target.name] = role
        if role == "confirmation" and not config.get("parameters_frozen", False):
            raise ValueError(
                "Confirmation scoring refused: set parameters_frozen=true only after "
                "the excluded pilot has fixed full_scale_z and all thresholds"
            )
        if role == "confirmation" and config.get("sensor_direction_source") not in {
            "datasheet_and_independent_response_test", "excluded_chicken_pilot"
        }:
            raise ValueError(
                "Confirmation scoring refused: sensor_direction_source must document "
                "datasheet/independent testing or the excluded pilot"
            )
        session = load_sessions([target], labelled=False,
                                resample_minutes=int(config["aggregation_minutes"]))
        scored, summary = score_session(session, calibration, config)
        destination = args.output_dir / target.name
        destination.mkdir(parents=True, exist_ok=True)
        scored.to_csv(destination / "sensor_change_metrics.csv", index=False)
        (destination / "sensor_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8")
        summaries.append(summary)
    confirmations = [item for item in summaries
                     if target_roles.get(item["session_id"]) == "confirmation"]
    detection = [item["time_to_sustained_change_h"] for item in confirmations
                 if item["time_to_sustained_change_h"] is not None]
    fixed_hours = {}
    if confirmations:
        for hour in confirmations[0]["index_at_fixed_hours"]:
            values = [item["index_at_fixed_hours"][hour] for item in confirmations
                      if item["index_at_fixed_hours"][hour] is not None]
            fixed_hours[hour] = None if not values else {
                "mean": float(np.mean(values)),
                "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
                "range": [float(min(values)), float(max(values))],
            }
    experiment_summary = {
        "sessions": summaries,
        "confirmation_metrics": {
            "confirmation_runs": len(confirmations),
            "detections": len(detection),
            "detection_latency_h": None if not detection else {
                "mean": float(np.mean(detection)),
                "sd": float(np.std(detection, ddof=1)) if len(detection) > 1 else None,
                "range": [float(min(detection)), float(max(detection))],
            },
            "change_index_at_fixed_hours": fixed_hours,
            "raw_trajectory_correlation_reported": False,
        },
    }
    (args.output_dir / "experiment_summary.json").write_text(
        json.dumps(experiment_summary, indent=2), encoding="utf-8")
    print(f"Sensor analysis for {len(args.targets)} target session(s) written to {args.output_dir}")


if __name__ == "__main__":
    main()

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


CALIBRATION_IDENTITY_FIELDS = (
    "site_id", "pcb_design_id", "device_id", "container_id"
)


def _metadata(session_dirs: list[Path]) -> dict[str, dict]:
    records = {}
    for path in session_dirs:
        metadata_path = path / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Missing session metadata: {metadata_path}")
        records[path.name] = json.loads(metadata_path.read_text(encoding="utf-8"))
    return records


def _calibration_identity(records: dict[str, dict]) -> dict[str, str]:
    identity = {}
    for field in CALIBRATION_IDENTITY_FIELDS:
        values = {str(item.get(field, "")).strip() for item in records.values()}
        if "" in values:
            raise ValueError(f"Every control metadata.json must define {field}")
        if len(values) != 1:
            raise ValueError(
                f"Controls used in one calibration must share {field}; got {sorted(values)}"
            )
        identity[field] = values.pop()
    return identity


def _validate_protocol_metadata(records: dict[str, dict], config: dict) -> None:
    expected_version = config.get("protocol_version")
    expected_minutes = float(config["primary_auc_hours"]) * 60.0
    expected_baseline = float(config["baseline_minutes"])
    for name, item in records.items():
        if item.get("protocol_version") != expected_version:
            raise ValueError(
                f"{name} protocol_version={item.get('protocol_version')!r}; "
                f"expected {expected_version!r}"
            )
        try:
            log_minutes = float(item.get("log_minutes", -1))
            baseline_minutes = float(item.get("food_baseline_minutes", -1))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} has invalid duration metadata") from exc
        if log_minutes < expected_minutes:
            raise ValueError(
                f"{name} log_minutes must be at least {expected_minutes:g} "
                "for this reporting window"
            )
        if baseline_minutes != expected_baseline:
            raise ValueError(
                f"{name} food_baseline_minutes must be {expected_baseline:g}"
            )


def _require_matching_identity(metadata: dict, calibration: dict, session_name: str) -> None:
    mismatch = {
        field: {"target": metadata.get(field), "calibration": calibration.get(field)}
        for field in CALIBRATION_IDENTITY_FIELDS
        if str(metadata.get(field, "")).strip()
        != str(calibration.get(field, "")).strip()
    }
    if mismatch:
        raise ValueError(
            f"Target {session_name} does not match its local control calibration: {mismatch}. "
            "Calibrate each site/PCB/device/container from its own three empty controls."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--controls", nargs="+", type=Path,
                        help="Calibrate a new artifact from empty-control sessions")
    source.add_argument("--calibration", type=Path,
                        help="Reuse an existing frozen control_calibration.joblib")
    parser.add_argument("--targets", nargs="*", default=[], type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/house_a_v2_candidate.json")
    )
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
        control_metadata = _metadata(args.controls)
        _validate_protocol_metadata(control_metadata, config)
        invalid = {
            name: item.get("session_role")
            for name, item in control_metadata.items()
            if item.get("session_role") != "control"
        }
        if invalid:
            raise ValueError(f"Control folders have non-control session_role values: {invalid}")
        identity = _calibration_identity(control_metadata)
        controls = load_sessions(
            args.controls, resample_minutes=int(config["aggregation_minutes"])
        )
        calibration = calibrate_controls(controls, config, args.random_state)
        calibration.update(identity)
        loo = calibration.pop("loo_residuals")
        loo.to_csv(args.output_dir / "control_loo_residuals.csv", index=False)
        joblib.dump(calibration, args.output_dir / "control_calibration.joblib")
        calibration_summary = {
            "protocol_version": config.get("protocol_version"),
            **identity,
            "operators": sorted({
                str(item.get("operator_id", "unknown"))
                for item in control_metadata.values()
            }),
            "control_sessions": calibration["control_sessions"],
            "loo_scales": calibration["scales"],
            "selected_cusum_h": calibration["cusum_h"],
            "bootstrap_false_session_rates": calibration["bootstrap_false_session_rates"],
            "index_weights": config["index"]["weights"],
            "index_weights_source": config["index"].get("weights_source"),
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
        metadata = _metadata([target])[target.name]
        _validate_protocol_metadata({target.name: metadata}, config)
        role = metadata.get("session_role")
        if role not in {"pilot", "confirmation"}:
            raise ValueError(
                f"Target {target.name} must have session_role pilot or confirmation; got {role!r}"
            )
        _require_matching_identity(metadata, calibration, target.name)
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
        session = load_sessions(
            [target], resample_minutes=int(config["aggregation_minutes"])
        )
        scored, summary = score_session(session, calibration, config)
        summary.update({
            "protocol_version": config.get("protocol_version"),
            "parameters_frozen": bool(config.get("parameters_frozen", False)),
            "recorded_session_id": metadata.get("session_id"),
            "session_role": role,
            "site_id": metadata.get("site_id"),
            "pcb_design_id": metadata.get("pcb_design_id"),
            "device_id": metadata.get("device_id"),
            "container_id": metadata.get("container_id"),
            "operator_id": metadata.get("operator_id"),
            "sample_id": metadata.get("sample_id"),
            "sample_cut": metadata.get("sample_cut"),
            "sample_mass_g": metadata.get("sample_mass_g"),
            "source_batch_id": metadata.get("source_batch_id"),
            "index_weights": config["index"]["weights"],
            "index_weights_source": config["index"].get("weights_source"),
            "index_interpretation": config["index"].get("interpretation"),
        })
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

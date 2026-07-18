"""Extract image features and run baseline-relative camera anomaly detection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from camera_models import fit_camera_unsupervised
from experiment_config import load_experiment_config
from image_data import load_image_log
from image_features import extract_image_features


def parse_roi(value: str | None):
    if value is None:
        return None
    parts = tuple(float(item) for item in value.split(","))
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("ROI must be x1,y1,x2,y2")
    return parts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--roi", type=parse_roi,
                        help="Normalized chicken crop: x1,y1,x2,y2 (for example .1,.2,.9,.9)")
    parser.add_argument("--background-roi", type=parse_roi,
                        help="Fixed background crop used to detect chamber/lens fog")
    parser.add_argument("--config", type=Path, default=Path("experiment_config.json"))
    args = parser.parse_args()

    log = load_image_log(args.session)
    config = load_experiment_config(args.config)
    role = log["session_role"].iloc[0]
    if role == "confirmation" and not config.get("parameters_frozen", False):
        raise ValueError("Confirmation camera scoring requires parameters_frozen=true")
    if role == "confirmation" and args.background_roi is None:
        raise ValueError("Confirmation camera scoring requires --background-roi for fog detection")
    features = extract_image_features(
        log["image_path_resolved"], roi=args.roi, background_roi=args.background_roi
    )
    combined = pd.concat([log.reset_index(drop=True), features], axis=1)
    artifacts, predictions = fit_camera_unsupervised(combined, config)
    artifacts["roi"] = args.roi
    artifacts["background_roi"] = args.background_roi
    artifacts["protocol_version"] = config.get("protocol_version")
    combined = pd.concat([combined, predictions], axis=1)

    output = args.output_dir or args.session / "camera_analysis"
    output.mkdir(parents=True, exist_ok=True)
    combined.drop(columns=["image_path_resolved"], errors="ignore").to_csv(
        output / "camera_features.csv", index=False)
    joblib.dump(artifacts, output / "camera_models.joblib")
    hourly = combined.assign(
        hour=combined["minutes_since_insertion"].floordiv(60).astype(int)
    ).groupby("hour").agg(
        frames=("camera_reliable", "size"),
        reliable_fraction=("camera_reliable", "mean"),
        fog_fraction=("fog_suspected", "mean"),
        sustained_change=("camera_sustained_change", "max"),
    ).reset_index()
    hourly.to_csv(output / "camera_reliability_by_hour.csv", index=False)
    summary = {
        "overall_reliable_fraction": float(combined["camera_reliable"].mean()),
        "fogged_frames": int(combined["fog_suspected"].sum()),
        "sustained_change_detected": bool(combined["camera_sustained_change"].any()),
        "background_roi_supplied": args.background_roi is not None,
        "session_role": role,
        "warning": "Camera output describes visible change, not food safety.",
    }
    (output / "camera_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output / "config_used.json").write_text(
        json.dumps(config, indent=2), encoding="utf-8"
    )
    print(f"Wrote {output / 'camera_features.csv'}")
    print(f"Wrote {output / 'camera_models.joblib'}")
    print(f"Wrote {output / 'camera_reliability_by_hour.csv'}")


if __name__ == "__main__":
    main()

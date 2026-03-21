#!/usr/bin/env python3
"""
FoodSense CLI: build features, train models, run inference.
Usage:
  python run_pipeline.py features [--raw-dir DIR] [--processed-dir DIR]
  python run_pipeline.py train [--processed-dir DIR] [--model-dir DIR]
  python run_pipeline.py predict [--model-dir DIR] [--data PATH or inline row]
  python run_pipeline.py all   # features then train
"""

import argparse
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="FoodSense ML pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # features
    p_feat = sub.add_parser("features", help="Build features from raw sensor CSVs")
    p_feat.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw", help="Directory with sensor_log_*.csv")
    p_feat.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    p_feat.add_argument("--no-exclude-warmup", action="store_true", help="Include Warmup rows in training data")

    # train
    p_train = sub.add_parser("train", help="Train RF, MLP, LR and save models")
    p_train.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    p_train.add_argument("--model-dir", type=Path, default=ROOT / "models")

    # predict
    p_pred = sub.add_parser("predict", help="Run spoilage risk inference")
    p_pred.add_argument("--data", type=Path, default=None, help="CSV path or leave empty for demo row")
    p_pred.add_argument("--model-dir", type=Path, default=ROOT / "models")
    p_pred.add_argument("--processed-dir", type=Path, default=ROOT / "data" / "processed")
    p_pred.add_argument("--model", type=str, default=None, help="Override: random_forest, mlp, logistic_regression")

    # all
    sub.add_parser("all", help="Run features then train")

    args = parser.parse_args()

    if args.command == "features":
        from ml.features import build_features
        build_features(
            raw_dir=args.raw_dir,
            processed_dir=args.processed_dir,
            exclude_warmup=not args.no_exclude_warmup,
        )
        print("Features saved to", args.processed_dir)

    elif args.command == "train":
        from ml.train import train_models
        metrics = train_models(processed_dir=args.processed_dir, model_dir=args.model_dir)
        for name, res in metrics.items():
            if "test" in res:
                print(name, "— test F1 (spoiled):", res["test"].get("f1_spoiled"), "accuracy:", res["test"].get("accuracy"))
        print("Models saved to", args.model_dir)

    elif args.command == "predict":
        from ml.predict import run_inference
        data = args.data
        if data is None:
            # Demo: one synthetic row (must match feature_names after scaling; for real use pass CSV)
            data = Path(args.processed_dir) / "features_test.csv"
            if not data.exists():
                print("No --data provided and no features_test.csv found. Run 'python run_pipeline.py features' then 'train' first.", file=sys.stderr)
                sys.exit(1)
        out = run_inference(data=data, model_dir=args.model_dir, processed_dir=args.processed_dir, model_name=args.model)
        print(out)

    elif args.command == "all":
        from ml.features import build_features
        from ml.train import train_models
        raw_dir = ROOT / "data" / "raw"
        processed_dir = ROOT / "data" / "processed"
        model_dir = ROOT / "models"
        build_features(raw_dir=raw_dir, processed_dir=processed_dir)
        train_models(processed_dir=processed_dir, model_dir=model_dir)
        print("Pipeline complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

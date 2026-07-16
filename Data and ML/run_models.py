"""Run prototype unsupervised and supervised models across session folders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import joblib

from model_data import load_sessions
from sequence_models import fit_hmm
from supervised_models import leave_one_session_out
from unsupervised_models import cusum_change, fit_unsupervised


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sessions", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("model_output"))
    parser.add_argument("--unsupervised-only", action="store_true",
                        help="Run CUSUM/PCA/Isolation Forest without observations.csv")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    unlabelled = load_sessions(args.sessions, labelled=False)
    unsupervised, unsupervised_output = fit_unsupervised(unlabelled)
    cusum_parts = []
    for _, group in unlabelled.groupby("session_id", sort=False):
        cusum_parts.append(cusum_change(group["gas_state"], group["is_baseline"].astype(bool)))
    cusum_output = __import__("pandas").concat(cusum_parts)
    unsupervised_output["cusum"] = cusum_output["cusum"].to_numpy()
    unsupervised_output["change_detected"] = cusum_output["change_detected"].to_numpy()
    unsupervised_output["session_id"] = unlabelled["session_id"].to_numpy()
    unsupervised_output.to_csv(args.output_dir / "unsupervised_predictions.csv")
    joblib.dump(unsupervised, args.output_dir / "unsupervised_models.joblib")

    if args.unsupervised_only:
        print(f"Unsupervised artifacts written to {args.output_dir}")
        return

    labelled = load_sessions(args.sessions, labelled=True)
    fitted, metrics = leave_one_session_out(labelled)
    joblib.dump(fitted, args.output_dir / "classifiers.joblib")
    (args.output_dir / "validation_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8")
    hmm, stages = fit_hmm(labelled)
    joblib.dump(hmm, args.output_dir / "hmm.joblib")
    stages.to_csv(args.output_dir / "hmm_stages.csv")
    print(f"Model artifacts written to {args.output_dir}")


if __name__ == "__main__":
    main()

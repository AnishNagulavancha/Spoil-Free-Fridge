"""Combine locally calibrated confirmation summaries across independent sites."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np


def _resolve_summary(path: Path) -> Path:
    return path / "sensor_summary.json" if path.is_dir() else path


def _stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {
        "n": len(values),
        "mean": float(np.mean(values)),
        "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
        "range": [float(min(values)), float(max(values))],
    }


def aggregate(paths: list[Path]) -> dict:
    sessions = []
    for input_path in paths:
        path = _resolve_summary(input_path)
        if not path.is_file():
            raise FileNotFoundError(f"Missing sensor summary: {path}")
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("session_role") != "confirmation":
            raise ValueError(f"Only confirmation summaries can be aggregated: {path}")
        if not item.get("parameters_frozen", False):
            raise ValueError(f"Confirmation was not scored with frozen parameters: {path}")
        for field in (
            "protocol_version", "site_id", "pcb_design_id", "device_id", "container_id"
        ):
            if not item.get(field):
                raise ValueError(f"{path} is missing {field}")
        sessions.append(item)

    if not sessions:
        raise ValueError("At least one confirmation summary is required")
    versions = {item["protocol_version"] for item in sessions}
    pcb_designs = {item["pcb_design_id"] for item in sessions}
    weights = {json.dumps(item.get("index_weights"), sort_keys=True) for item in sessions}
    if len(versions) != 1 or len(pcb_designs) != 1 or len(weights) != 1:
        raise ValueError(
            "Cross-site confirmations must use one protocol version, PCB design, "
            "and weight set"
        )

    by_site: dict[str, list[dict]] = defaultdict(list)
    for item in sessions:
        by_site[str(item["site_id"])].append(item)

    def summarize(items: list[dict]) -> dict:
        detections = [
            float(item["time_to_sustained_change_h"])
            for item in items
            if item.get("time_to_sustained_change_h") is not None
        ]
        valid_auc = [
            float(item["auc_change_index_hours"])
            for item in items
            if item.get("auc_valid") and item.get("auc_change_index_hours") is not None
        ]
        hours = sorted(
            {hour for item in items for hour in item.get("index_at_fixed_hours", {})},
            key=float,
        )
        fixed = {}
        for hour in hours:
            values = [
                float(item["index_at_fixed_hours"][hour])
                for item in items
                if item.get("index_at_fixed_hours", {}).get(hour) is not None
            ]
            fixed[hour] = _stats(values)
        return {
            "confirmation_runs": len(items),
            "primary_events_detected": sum(
                bool(item.get("primary_event_detected")) for item in items
            ),
            "detection_latency_h": _stats(detections),
            "valid_auc_runs": len(valid_auc),
            "auc_0_4h": _stats(valid_auc),
            "change_index_at_fixed_hours": fixed,
        }

    return {
        "protocol_version": sessions[0]["protocol_version"],
        "pcb_design_id": sessions[0]["pcb_design_id"],
        "index_weights": sessions[0].get("index_weights"),
        "index_interpretation": sessions[0].get("index_interpretation"),
        "sites": sorted(by_site),
        "devices": sorted({str(item["device_id"]) for item in sessions}),
        "overall": summarize(sessions),
        "by_site": {site: summarize(items) for site, items in sorted(by_site.items())},
        "claim_limit": (
            "Descriptive cross-site confirmation only; this does not establish "
            "food safety or universal operation in every house."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", nargs="+", type=Path,
        help="Confirmation sensor_summary.json files or their containing directories",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("cross_site_summary.json")
    )
    args = parser.parse_args()
    result = aggregate(args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

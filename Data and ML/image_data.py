"""Load valid session images and identify the insertion/baseline period."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_image_log(session_dir: Path) -> pd.DataFrame:
    log_path = session_dir / "image_log.csv"
    metadata_path = session_dir / "metadata.json"
    if not log_path.is_file() or not metadata_path.is_file():
        raise FileNotFoundError("Session needs image_log.csv and metadata.json")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    log = pd.read_csv(log_path)
    required = {"timestamp_iso", "image_filename", "status"}
    missing = required.difference(log.columns)
    if missing:
        raise ValueError(f"image_log.csv is missing: {', '.join(sorted(missing))}")
    log["timestamp"] = pd.to_datetime(log["timestamp_iso"], errors="coerce")
    log = log.loc[log["status"].eq("success") & log["timestamp"].notna()].copy()
    log.sort_values("timestamp", inplace=True)

    def resolve_image(row: pd.Series) -> Path:
        recorded = str(row.get("image_path", "")).strip()
        if recorded and recorded.casefold() != "nan" and Path(recorded).is_file():
            return Path(recorded)
        return session_dir / "images" / str(row["image_filename"])

    log["image_path_resolved"] = log.apply(resolve_image, axis=1)
    log = log.loc[log["image_path_resolved"].map(Path.is_file)].copy()
    if log.empty:
        raise ValueError("No successful image files were found")

    inserted_raw = metadata.get("post_prompt_start_time") or metadata.get("food_inserted_time")
    inserted_time = pd.to_datetime(inserted_raw, errors="coerce") if inserted_raw else pd.NaT
    if pd.isna(inserted_time):
        if len(log) < 2:
            raise ValueError("Cannot identify insertion image without metadata or two images")
        inserted_time = log["timestamp"].iloc[1]

    # The initial empty reference is before insertion and is excluded from food ML.
    food = log.loc[log["timestamp"].ge(inserted_time)].copy()
    if food.empty:
        raise ValueError("No chicken images exist at or after food_inserted_time")
    food["minutes_since_insertion"] = (
        food["timestamp"] - food["timestamp"].iloc[0]
    ).dt.total_seconds() / 60.0
    baseline_minutes = float(metadata.get("food_baseline_minutes", 30))
    food["is_image_baseline"] = food["minutes_since_insertion"].le(baseline_minutes)
    food["session_id"] = metadata.get("session_id", session_dir.name)
    food["session_role"] = metadata.get("session_role")
    food["site_id"] = metadata.get("site_id")
    food["pcb_design_id"] = metadata.get("pcb_design_id")
    food["device_id"] = metadata.get("device_id")
    food["container_id"] = metadata.get("container_id")
    food["operator_id"] = metadata.get("operator_id")
    food["protocol_version"] = metadata.get("protocol_version")
    return food.reset_index(drop=True)

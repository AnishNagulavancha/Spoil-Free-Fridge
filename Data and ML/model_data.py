"""Shared feature selection, observation alignment, and session-aware datasets."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


LABEL_ORDER = {"fresh": 0, "deteriorating": 1, "spoiled": 2}


def feature_columns(frame: pd.DataFrame) -> list[str]:
    endings = ("_delta_pct", "_log_inverted", "_slope_5m", "_slope_15m",
               "_slope_30m", "_volatility_5m", "_volatility_15m",
               "_volatility_30m", "_accel_5m", "_accel_15m", "_accel_30m")
    exact = {"temp_C", "humidity_pct", "q10_factor", "biological_age_h", "gas_state"}
    return [c for c in frame.columns if c in exact or c.endswith(endings)]


def attach_observations(features: pd.DataFrame, observations_path: Path,
                        tolerance_minutes: float = 40) -> pd.DataFrame:
    """Attach the nearest manual stage to rows; observations must not be interpolated."""
    observations = pd.read_csv(observations_path)
    if "timestamp_iso" not in observations or "stage" not in observations:
        raise ValueError("observations.csv needs timestamp_iso and stage columns")
    observations["timestamp"] = pd.to_datetime(observations["timestamp_iso"], errors="coerce")
    observations["stage"] = observations["stage"].astype(str).str.strip().str.casefold()
    unknown = sorted(set(observations["stage"].dropna()) - set(LABEL_ORDER))
    if unknown:
        raise ValueError(f"Unknown stages: {unknown}; use fresh/deteriorating/spoiled")
    left = features.reset_index().sort_values("timestamp")
    right = observations.dropna(subset=["timestamp"]).sort_values("timestamp")
    merged = pd.merge_asof(left, right[["timestamp", "stage"]], on="timestamp",
                           direction="nearest",
                           tolerance=pd.Timedelta(minutes=tolerance_minutes))
    merged["target"] = merged["stage"].map(LABEL_ORDER)
    return merged.set_index("timestamp")


def load_sessions(session_dirs: list[Path], labelled: bool = True,
                  resample_minutes: int = 5) -> pd.DataFrame:
    sessions = []
    for session_dir in session_dirs:
        path = session_dir / "analysis" / "features.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Run analyze_session.py first: {path}")
        frame = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
        if labelled:
            frame = attach_observations(frame, session_dir / "observations.csv")
            frame = frame.dropna(subset=["target"])
            frame["target"] = frame["target"].astype(int)
        frame["session_id"] = session_dir.name
        # Reduce adjacent-row pseudoreplication while preserving time order.
        numeric = frame.select_dtypes(include=[np.number]).resample(f"{resample_minutes}min").median()
        nonnumeric = frame.select_dtypes(exclude=[np.number]).resample(f"{resample_minutes}min").first()
        frame = numeric.join(nonnumeric, how="left").dropna(how="all")
        if labelled:
            frame["target"] = frame["target"].round().astype("Int64")
        frame["session_id"] = session_dir.name
        sessions.append(frame)
    if not sessions:
        raise ValueError("At least one session directory is required")
    # Keep each session contiguous: HMM sequence lengths rely on this ordering.
    return pd.concat(sessions)

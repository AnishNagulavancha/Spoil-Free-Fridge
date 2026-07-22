"""Load analyzed sessions while preserving independent session identities."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path


def load_sessions(session_dirs: list[Path], resample_minutes: int = 5) -> pd.DataFrame:
    """Load feature files and reduce adjacent-row pseudoreplication per session."""
    sessions = []
    for session_dir in session_dirs:
        path = session_dir / "analysis" / "features.csv"
        if not path.is_file():
            raise FileNotFoundError(f"Run analyze_session.py first: {path}")
        frame = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
        frame["session_id"] = session_dir.name
        numeric = frame.select_dtypes(include=[np.number]).resample(f"{resample_minutes}min").median()
        nonnumeric = frame.select_dtypes(exclude=[np.number]).resample(f"{resample_minutes}min").first()
        frame = numeric.join(nonnumeric, how="left").dropna(how="all")
        frame["session_id"] = session_dir.name
        sessions.append(frame)
    if not sessions:
        raise ValueError("At least one session directory is required")
    return pd.concat(sessions)

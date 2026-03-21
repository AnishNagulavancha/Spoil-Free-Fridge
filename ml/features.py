"""
Feature extraction and preprocessing for multi-source sensor time series.
Transforms raw sensor streams into spoilage indicators for ML.
"""

import warnings
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from .config import (
    DEFAULT_RAW_DATA_DIR,
    DEFAULT_PROCESSED_DIR,
    LABEL_TO_BINARY,
    ROLLING_WINDOWS,
    SENSOR_COLUMNS,
    RAW_COLUMNS,
)


def load_raw_logs(
    raw_dir: Optional[Path] = None,
    glob: str = "*.csv",
    exclude_labels: Sequence[str] = ("Warmup",),
) -> pd.DataFrame:
    """Load and concatenate all sensor log CSVs from a directory."""
    raw_dir = raw_dir or DEFAULT_RAW_DATA_DIR
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return pd.DataFrame()

    frames = []
    for path in sorted(raw_dir.glob(glob)):
        try:
            df = pd.read_csv(path)
            # Normalize column names
            df.columns = df.columns.str.strip()
            if "Label" not in df.columns and "label" in df.columns:
                df["Label"] = df["label"]
            # Ensure expected columns exist
            for c in ["NH3_raw", "NH3_V", "CH4_raw", "CH4_V", "H2S_raw", "H2S_V", "Temp_C", "Humidity_pct", "GasRes"]:
                if c not in df.columns:
                    continue
            df["_source_file"] = path.name
            frames.append(df)
        except Exception as e:
            warnings.warn(f"Skip {path}: {e}")
            continue

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)

    # Drop rows with invalid label if we exclude some
    if exclude_labels and "Label" in out.columns:
        out = out[~out["Label"].astype(str).str.strip().str.lower().isin([x.lower() for x in exclude_labels])].copy()

    return out


def to_numeric_clean(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce sensor columns to numeric and drop rows with missing/invalid values."""
    use = [c for c in SENSOR_COLUMNS if c in df.columns]
    if not use:
        return df.copy()

    out = df.copy()
    for c in use:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=use)
    return out


def add_derived_features(df: pd.DataFrame, windows: Sequence[int] = ROLLING_WINDOWS) -> pd.DataFrame:
    """Add rolling stats and gas ratios as derived features."""
    out = df.copy()
    volts = [c for c in ["NH3_V", "CH4_V", "H2S_V"] if c in out.columns]
    if not volts:
        return out

    for w in windows:
        for c in volts:
            out[f"{c}_roll_mean_{w}"] = out[c].rolling(window=w, min_periods=1).mean()
            out[f"{c}_roll_std_{w}"] = out[c].rolling(window=w, min_periods=1).std().fillna(0)
        if len(volts) >= 2:
            out[f"NH3_CH4_ratio_roll_{w}"] = (out["NH3_V"].rolling(w, min_periods=1).mean() /
                                              (out["CH4_V"].rolling(w, min_periods=1).mean().replace(0, np.nan))).fillna(0)
    if "GasRes" in out.columns:
        for w in windows:
            out[f"GasRes_roll_mean_{w}"] = out["GasRes"].rolling(window=w, min_periods=1).mean()
    return out


def get_feature_columns(df: pd.DataFrame) -> list:
    """List of numeric columns suitable as model features (exclude Timestamp, Label, _source_file)."""
    exclude = {"Timestamp", "Label", "label", "_source_file"}
    return [c for c in df.select_dtypes(include=[np.number]).columns if c not in exclude]


def build_features(
    raw_dir: Optional[Path] = None,
    processed_dir: Optional[Path] = None,
    exclude_warmup: bool = True,
    test_size: float = 0.2,
    val_size: float = 0.15,
    random_state: int = 42,
    save: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, StandardScaler, list]:
    """
    Load raw logs, clean, add derived features, normalize, and split into train/val/test.
    Returns (X_train, X_val, X_test), scaler, and feature_names.
    y is stored in processed CSVs; train.py will load and use it.
    """
    raw_dir = Path(raw_dir or DEFAULT_RAW_DATA_DIR)
    processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
    processed_dir.mkdir(parents=True, exist_ok=True)

    exclude = ("Warmup",) if exclude_warmup else ()
    df = load_raw_logs(raw_dir=raw_dir, exclude_labels=exclude)
    if df.empty:
        raise FileNotFoundError(f"No CSV logs found in {raw_dir}. Run Data LoggingScript.py and place CSVs there.")

    df = to_numeric_clean(df)
    if "Label" in df.columns:
        df["y"] = df["Label"].astype(str).str.strip().map(lambda x: LABEL_TO_BINARY.get(x, np.nan))
        df = df.dropna(subset=["y"])
        df["y"] = df["y"].astype(int)
    else:
        df["y"] = np.nan

    df = add_derived_features(df)
    feature_cols = get_feature_columns(df)
    X = df[feature_cols].copy()
    y = df["y"].values if "y" in df.columns else None

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X = pd.DataFrame(X_scaled, columns=feature_cols, index=df.index)

    if y is not None:
        try:
            train_idx, test_idx = train_test_split(np.arange(len(df)), test_size=test_size, random_state=random_state, stratify=y)
        except ValueError:
            train_idx, test_idx = train_test_split(np.arange(len(df)), test_size=test_size, random_state=random_state)
        try:
            train_idx, val_idx = train_test_split(train_idx, test_size=val_size / (1 - test_size), random_state=random_state, stratify=y[train_idx])
        except ValueError:
            train_idx, val_idx = train_test_split(train_idx, test_size=val_size / (1 - test_size), random_state=random_state)
        X_train = X.iloc[train_idx].copy()
        X_val = X.iloc[val_idx].copy()
        X_test = X.iloc[test_idx].copy()
        for name, idx in [("train", train_idx), ("val", val_idx), ("test", test_idx)]:
            subset = df.iloc[idx].copy()
            subset[feature_cols] = X.iloc[idx].values
            if save:
                subset.to_csv(processed_dir / f"features_{name}.csv", index=False)
    else:
        X_train = X_val = X_test = X
        if save:
            X.to_csv(processed_dir / "features_all.csv", index=False)

    if save:
        pd.Series(feature_cols).to_csv(processed_dir / "feature_names.csv", index=False, header=False)
        import joblib
        joblib.dump(scaler, processed_dir / "scaler.joblib")

    return X_train, X_val, X_test, scaler, feature_cols


def load_processed_splits(processed_dir: Optional[Path] = None) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Load train/val/test feature CSVs and return (X_train, y_train, X_val, y_val, X_test, y_test)."""
    processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
    feature_names = pd.read_csv(processed_dir / "feature_names.csv", header=None).iloc[:, 0].tolist()

    def load_split(name: str):
        path = processed_dir / f"features_{name}.csv"
        if not path.exists():
            return None, None
        df = pd.read_csv(path)
        use = [c for c in feature_names if c in df.columns]
        X = df[use]
        y = df["y"] if "y" in df.columns else None
        return X, y

    X_train, y_train = load_split("train")
    X_val, y_val = load_split("val")
    X_test, y_test = load_split("test")
    if X_train is None:
        raise FileNotFoundError(f"No features_train.csv in {processed_dir}. Run build_features first.")
    return X_train, y_train, X_val, y_val, X_test, y_test

"""
Spoilage risk inference for deployment and low-latency alerting.
Loads trained model and scaler; accepts single sample or batch.
"""

from pathlib import Path
from typing import Optional, Union

import joblib
import numpy as np
import pandas as pd

from .config import DEFAULT_MODEL_DIR, DEFAULT_PROCESSED_DIR
from .features import add_derived_features, get_feature_columns, to_numeric_clean


def load_pipeline(model_dir: Optional[Path] = None, processed_dir: Optional[Path] = None):
    """Load scaler and best model (or specified model)."""
    model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
    processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)

    scaler_path = processed_dir / "scaler.joblib"
    if not scaler_path.exists():
        raise FileNotFoundError(f"Scaler not found: {scaler_path}. Run build_features first.")
    scaler = joblib.load(scaler_path)

    best_name_path = model_dir / "best_model_name.txt"
    if best_name_path.exists():
        model_name = best_name_path.read_text().strip()
    else:
        model_name = "logistic_regression"  # default small model
    model_path = model_dir / f"{model_name}.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}. Run train_models first.")
    model = joblib.load(model_path)

    feature_names_path = processed_dir / "feature_names.csv"
    if feature_names_path.exists():
        feature_names = pd.read_csv(feature_names_path, header=None).iloc[:, 0].tolist()
    else:
        feature_names = None

    return scaler, model, feature_names


def _row_to_features(row: Union[dict, pd.Series], feature_names: list, rolling_df: Optional[pd.DataFrame] = None) -> np.ndarray:
    """Turn one row (and optional history for rolling) into feature vector matching training."""
    if rolling_df is not None:
        df = pd.concat([rolling_df, pd.DataFrame([row])], ignore_index=True)
        df = add_derived_features(df)
        vec = df.iloc[-1][feature_names].values.reshape(1, -1)
    else:
        df = pd.DataFrame([row])
        df = to_numeric_clean(df)
        df = add_derived_features(df)
        use = [c for c in feature_names if c in df.columns]
        if len(use) != len(feature_names):
            # Missing derived cols: fill 0 for rolling stats if no history
            vec = np.zeros((1, len(feature_names)))
            for i, c in enumerate(feature_names):
                if c in df.columns:
                    vec[0, i] = df[c].iloc[0]
        else:
            vec = df[feature_names].values
    return vec


def run_inference(
    data: Optional[Union[str, Path, pd.DataFrame, dict, np.ndarray]] = None,
    model_dir: Optional[Path] = None,
    processed_dir: Optional[Path] = None,
    model_name: Optional[str] = None,
) -> Union[dict, pd.DataFrame]:
    """
    Run spoilage risk inference.

    - data: path to CSV, DataFrame, single row dict/Series, or 2D array (samples x features).
    - model_name: optional override (random_forest, mlp, logistic_regression).

    Returns dict with keys: spoilage_probability, spoilage_class (0/1), [and per-sample if batch].
    For batch input, returns DataFrame with columns spoilage_probability, spoilage_class.
    """
    processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
    model_dir = Path(model_dir or DEFAULT_MODEL_DIR)

    scaler, model, feature_names = load_pipeline(model_dir=model_dir, processed_dir=processed_dir)
    if model_name:
        model_path = model_dir / f"{model_name}.joblib"
        if model_path.exists():
            model = joblib.load(model_path)

    if data is None:
        raise ValueError("Provide data: CSV path, DataFrame, single row dict, or feature array.")

    # Single row (dict or Series)
    if isinstance(data, (dict, pd.Series)):
        row = dict(data) if isinstance(data, pd.Series) else data
        X = _row_to_features(row, feature_names)
        X = scaler.transform(X)
        prob = float(model.predict_proba(X)[0, 1]) if hasattr(model, "predict_proba") else float(model.predict(X)[0])
        pred = int(model.predict(X)[0])
        return {"spoilage_probability": prob, "spoilage_class": pred}

    # Path to CSV
    if isinstance(data, (str, Path)):
        data = pd.read_csv(data)

    # DataFrame or array
    if isinstance(data, pd.DataFrame):
        # Assume same columns as training or raw sensor columns
        data = to_numeric_clean(data)
        data = add_derived_features(data)
        use = [c for c in feature_names if c in data.columns]
        if len(use) != len(feature_names):
            X = np.zeros((len(data), len(feature_names)))
            for i, c in enumerate(feature_names):
                if c in data.columns:
                    X[:, i] = data[c].values
        else:
            X = data[use].values
    else:
        X = np.asarray(data)
        if X.ndim == 1:
            X = X.reshape(1, -1)

    X = scaler.transform(X)
    probs = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else model.predict(X).astype(float)
    preds = model.predict(X)

    out = pd.DataFrame({"spoilage_probability": probs, "spoilage_class": preds.astype(int)})
    if len(out) == 1:
        return {"spoilage_probability": float(out["spoilage_probability"].iloc[0]), "spoilage_class": int(out["spoilage_class"].iloc[0])}
    return out

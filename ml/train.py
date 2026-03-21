"""
Train and evaluate spoilage classifiers: Random Forest, MLP, Logistic Regression.
Saves models and metrics for deployment and alerting.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.neural_network import MLPClassifier

from .config import DEFAULT_MODEL_DIR, DEFAULT_PROCESSED_DIR
from .features import load_processed_splits


def _eval(y_true: np.ndarray, y_pred: np.ndarray, y_prob: Optional[np.ndarray] = None) -> Dict[str, Any]:
    out = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1_spoiled": float(f1_score(y_true, y_pred, pos_label=1, average="binary", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }
    if y_prob is not None and len(np.unique(y_true)) == 2:
        out["roc_auc"] = float(roc_auc_score(y_true, y_prob))
    return out


def train_models(
    processed_dir: Optional[Path] = None,
    model_dir: Optional[Path] = None,
    random_state: int = 42,
    save_artifacts: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Load processed train/val/test, train RF / MLP / LR, evaluate on val and test.
    Saves best model (by val F1), all metrics, and scaler path reference.
    """
    processed_dir = Path(processed_dir or DEFAULT_PROCESSED_DIR)
    model_dir = Path(model_dir or DEFAULT_MODEL_DIR)
    model_dir.mkdir(parents=True, exist_ok=True)

    X_train, y_train, X_val, y_val, X_test, y_test = load_processed_splits(processed_dir)
    y_train = np.asarray(y_train)
    y_val = np.asarray(y_val)
    y_test = np.asarray(y_test)

    feature_names = list(X_train.columns)
    results = {}

    # --- Random Forest ---
    rf = RandomForestClassifier(n_estimators=100, max_depth=12, random_state=random_state)
    rf.fit(X_train, y_train)
    y_val_pred = rf.predict(X_val)
    y_val_prob = rf.predict_proba(X_val)[:, 1] if hasattr(rf, "predict_proba") else None
    y_test_pred = rf.predict(X_test)
    y_test_prob = rf.predict_proba(X_test)[:, 1] if hasattr(rf, "predict_proba") else None
    results["random_forest"] = {
        "val": _eval(y_val, y_val_pred, y_val_prob),
        "test": _eval(y_test, y_test_pred, y_test_prob),
        "classification_report_test": classification_report(y_test, y_test_pred, zero_division=0),
    }
    if save_artifacts:
        joblib.dump(rf, model_dir / "random_forest.joblib")

    # --- MLP ---
    mlp = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500, random_state=random_state)
    mlp.fit(X_train, y_train)
    y_val_pred = mlp.predict(X_val)
    y_val_prob = mlp.predict_proba(X_val)[:, 1]
    y_test_pred = mlp.predict(X_test)
    y_test_prob = mlp.predict_proba(X_test)[:, 1]
    results["mlp"] = {
        "val": _eval(y_val, y_val_pred, y_val_prob),
        "test": _eval(y_test, y_test_pred, y_test_prob),
        "classification_report_test": classification_report(y_test, y_test_pred, zero_division=0),
    }
    if save_artifacts:
        joblib.dump(mlp, model_dir / "mlp.joblib")

    # --- Logistic Regression ---
    lr = LogisticRegression(max_iter=500, random_state=random_state)
    lr.fit(X_train, y_train)
    y_val_pred = lr.predict(X_val)
    y_val_prob = lr.predict_proba(X_val)[:, 1]
    y_test_pred = lr.predict(X_test)
    y_test_prob = lr.predict_proba(X_test)[:, 1]
    results["logistic_regression"] = {
        "val": _eval(y_val, y_val_pred, y_val_prob),
        "test": _eval(y_test, y_test_pred, y_test_prob),
        "classification_report_test": classification_report(y_test, y_test_pred, zero_division=0),
    }
    if save_artifacts:
        joblib.dump(lr, model_dir / "logistic_regression.joblib")

    # Best by val F1 (spoiled class)
    best_name = max(results, key=lambda k: results[k]["val"].get("f1_spoiled", 0))
    if save_artifacts:
        with open(model_dir / "metrics.json", "w") as f:
            json.dump({**results, "best_model": best_name, "feature_names": feature_names}, f, indent=2)
        (model_dir / "best_model_name.txt").write_text(best_name)

    return results

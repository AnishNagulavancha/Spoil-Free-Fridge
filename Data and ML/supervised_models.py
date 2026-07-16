"""Session-aware comparison of interpretable and nonlinear classifiers."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, classification_report
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.svm import SVC

from model_data import feature_columns


def model_candidates(random_state: int = 42):
    scaled = lambda model: make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), model)
    return {
        "logistic_regression": scaled(LogisticRegression(max_iter=3000, class_weight="balanced")),
        "random_forest": make_pipeline(SimpleImputer(strategy="median"),
            RandomForestClassifier(n_estimators=500, min_samples_leaf=3,
                                   class_weight="balanced", random_state=random_state)),
        "gradient_boosting": make_pipeline(SimpleImputer(strategy="median"),
            GradientBoostingClassifier(n_estimators=150, max_depth=2,
                                       learning_rate=0.04, random_state=random_state)),
        "svm": scaled(CalibratedClassifierCV(
            SVC(C=1.0, kernel="rbf", class_weight="balanced", random_state=random_state),
            method="sigmoid", cv=3,
        )),
    }


def leave_one_session_out(frame: pd.DataFrame) -> tuple[dict, dict]:
    columns = feature_columns(frame)
    results: dict[str, list[dict]] = {name: [] for name in model_candidates()}
    sessions = frame["session_id"].unique()
    if len(sessions) < 2:
        raise ValueError("Session-level validation needs at least two sessions")
    for held_out in sessions:
        train, test = frame[frame.session_id != held_out], frame[frame.session_id == held_out]
        if train.target.nunique() < 2:
            continue
        for name, model in model_candidates().items():
            model.fit(train[columns], train["target"])
            prediction = model.predict(test[columns])
            results[name].append({
                "held_out_session": str(held_out),
                "balanced_accuracy": float(balanced_accuracy_score(test.target, prediction)),
                "report": classification_report(test.target, prediction, zero_division=0,
                                                output_dict=True),
            })
    fitted = {}
    if frame.target.nunique() >= 2:
        for name, model in model_candidates().items():
            fitted[name] = model.fit(frame[columns], frame["target"])
    return fitted, results

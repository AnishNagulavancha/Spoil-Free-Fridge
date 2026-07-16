"""Guarded direct RUL regressors for use after enough complete sessions exist."""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler
from sklearn.svm import SVR

from model_data import feature_columns


def fit_rul_regressors(frame: pd.DataFrame, random_state: int = 42):
    """Fit remaining-hour models; requires session_id and remaining_h columns."""
    required = {"session_id", "remaining_h"}
    if not required.issubset(frame):
        raise ValueError("RUL data needs session_id and remaining_h columns")
    if frame["session_id"].nunique() < 10:
        raise ValueError("Direct RUL fitting disabled: need at least 10 complete sessions")
    columns = feature_columns(frame)
    scaled_svr = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(),
                               SVR(C=3.0, epsilon=0.5, kernel="rbf"))
    candidates = {
        "random_forest_rul": make_pipeline(SimpleImputer(strategy="median"),
            RandomForestRegressor(n_estimators=500, min_samples_leaf=3,
                                  random_state=random_state)),
        "gradient_boosting_rul": make_pipeline(SimpleImputer(strategy="median"),
            GradientBoostingRegressor(n_estimators=150, max_depth=2,
                                      learning_rate=0.04, loss="huber",
                                      random_state=random_state)),
        "svr_rul": scaled_svr,
    }
    return {name: model.fit(frame[columns], frame["remaining_h"])
            for name, model in candidates.items()}

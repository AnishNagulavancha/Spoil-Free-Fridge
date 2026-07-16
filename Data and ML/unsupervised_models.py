"""Label-free baseline departure methods: CUSUM, PCA, and Isolation Forest."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler

from model_data import feature_columns


def cusum_change(series: pd.Series, baseline_mask: pd.Series,
                 drift_sigma: float = 0.5, threshold_sigma: float = 5.0) -> pd.DataFrame:
    baseline = series[baseline_mask].dropna()
    center, sigma = baseline.mean(), baseline.std(ddof=1)
    sigma = max(float(sigma), 1e-9)
    z = (series - center) / sigma
    positive = np.zeros(len(series))
    for i in range(1, len(series)):
        positive[i] = max(0.0, positive[i - 1] + float(np.nan_to_num(z.iloc[i])) - drift_sigma)
    return pd.DataFrame({"cusum": positive, "change_detected": positive >= threshold_sigma},
                        index=series.index)


def fit_unsupervised(frame: pd.DataFrame, random_state: int = 42):
    columns = feature_columns(frame)
    if len(columns) < 2:
        raise ValueError("Not enough engineered feature columns")
    pca = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), PCA(n_components=2))
    components = pca.fit_transform(frame[columns])
    forest = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(),
                           IsolationForest(n_estimators=300, contamination="auto",
                                           random_state=random_state))
    anomaly = forest.fit_predict(frame[columns])
    output = pd.DataFrame({"pca_1": components[:, 0], "pca_2": components[:, 1],
                           "is_anomaly": anomaly == -1}, index=frame.index)
    return {"pca": pca, "isolation_forest": forest}, output

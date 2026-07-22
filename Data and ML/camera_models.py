"""Baseline-trained unsupervised camera models for the first experiments."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler


NON_FEATURES = {
    "timestamp", "timestamp_iso", "image_filename", "image_path", "status",
    "image_path_resolved", "session_id", "is_image_baseline", "image_number",
    "content_type", "http_status",
}


def camera_feature_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.select_dtypes(include=[np.number]).columns
            if column not in NON_FEATURES and column not in {"elapsed_s", "minutes_since_insertion"}]


def fit_camera_unsupervised(frame: pd.DataFrame, config: dict,
                            random_state: int = 42):
    camera_config = config["camera"]
    rolling_images = int(camera_config["persistence_frames"])
    required_anomalies = rolling_images
    columns = camera_feature_columns(frame)
    baseline = frame["is_image_baseline"].astype(bool)
    if baseline.sum() < 3:
        raise ValueError("Need at least three chicken baseline images")
    if required_anomalies > rolling_images:
        raise ValueError("required_anomalies cannot exceed rolling_images")

    imputer = SimpleImputer(strategy="median").fit(frame.loc[baseline, columns])
    scaler = RobustScaler().fit(imputer.transform(frame.loc[baseline, columns]))
    all_x = scaler.transform(imputer.transform(frame[columns]))
    baseline_x = all_x[baseline.to_numpy()]

    isolation = IsolationForest(n_estimators=400, contamination="auto",
                                random_state=random_state).fit(baseline_x)
    decision = isolation.decision_function(all_x)
    anomaly = isolation.predict(all_x) == -1
    fog = (
        frame["laplacian_ratio"].lt(float(camera_config["laplacian_ratio_minimum"]))
        & frame["background_laplacian_ratio"].lt(
            float(camera_config["background_laplacian_ratio_minimum"])
        )
    )
    reliable = ~fog
    reliable_anomaly = anomaly & reliable.to_numpy()

    # PCA is fitted on all images for trajectory visualization, never classification.
    pca = PCA(n_components=min(2, len(columns), len(frame))).fit(all_x)
    components = pca.transform(all_x)
    output = pd.DataFrame(index=frame.index)
    output["camera_pca_1"] = components[:, 0]
    output["camera_pca_2"] = components[:, 1] if components.shape[1] > 1 else 0.0
    output["camera_anomaly_score"] = -decision  # Higher means further from baseline.
    output["fog_suspected"] = fog.to_numpy()
    output["camera_reliable"] = reliable.to_numpy()
    output["camera_is_anomaly_raw"] = anomaly
    output["camera_is_anomaly"] = reliable_anomaly
    output["camera_anomaly_count_window"] = (
        pd.Series(reliable_anomaly, index=frame.index)
        .rolling(rolling_images, min_periods=rolling_images).sum()
    )
    output["camera_sustained_change"] = (
        output["camera_anomaly_count_window"] >= required_anomalies
    ) & pd.Series(reliable, index=frame.index).rolling(
        rolling_images, min_periods=rolling_images
    ).sum().eq(rolling_images) & ~frame["is_image_baseline"].astype(bool)
    artifacts = {"imputer": imputer, "scaler": scaler, "isolation_forest": isolation,
                 "pca": pca, "features": columns}
    return artifacts, output

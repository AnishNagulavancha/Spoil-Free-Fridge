"""Three-state Gaussian HMM for temporally smoothed freshness stages."""

from __future__ import annotations

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler

from model_data import feature_columns


def fit_hmm(frame: pd.DataFrame, random_state: int = 42):
    columns = feature_columns(frame)
    imputer, scaler = SimpleImputer(strategy="median"), RobustScaler()
    x = scaler.fit_transform(imputer.fit_transform(frame[columns]))
    lengths = frame.groupby("session_id", sort=False).size().tolist() if "session_id" in frame else None
    model = GaussianHMM(n_components=3, covariance_type="diag", n_iter=300,
                        random_state=random_state)
    model.fit(x, lengths=lengths)
    states = model.predict(x, lengths=lengths)
    # HMM state numbers are arbitrary; order them by mean GasState.
    state_means = {s: frame.loc[states == s, "gas_state"].mean() for s in range(3)}
    ordered = {state: rank for rank, state in enumerate(sorted(state_means, key=state_means.get))}
    stages = pd.Series([ordered[s] for s in states], index=frame.index, name="hmm_stage")
    return {"model": model, "imputer": imputer, "scaler": scaler,
            "state_order": ordered, "features": columns}, stages

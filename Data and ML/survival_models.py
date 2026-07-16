"""Experimental RUL models; only valid after substantially more endpoint runs."""

from __future__ import annotations

import pandas as pd
from lifelines import CoxPHFitter, WeibullAFTFitter


def fit_session_survival(session_table: pd.DataFrame):
    """Fit Cox and Weibull AFT models to one row per independent session.

    Required columns: duration_h, event, plus numeric session-level covariates.
    """
    required = {"duration_h", "event"}
    if not required.issubset(session_table):
        raise ValueError("session table needs duration_h and event columns")
    if len(session_table) < 10 or int(session_table["event"].sum()) < 5:
        raise ValueError("Survival fitting disabled: need >=10 sessions and >=5 endpoints")
    data = session_table.select_dtypes("number").dropna()
    cox = CoxPHFitter(penalizer=0.1).fit(data, duration_col="duration_h", event_col="event")
    aft = WeibullAFTFitter(penalizer=0.1).fit(data, duration_col="duration_h", event_col="event")
    return {"cox": cox, "weibull_aft": aft}

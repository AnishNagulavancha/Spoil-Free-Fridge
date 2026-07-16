# Spoilage modeling workflow

Run feature engineering once for each session:

```powershell
python analyze_session.py "C:\path\to\session"
```

Before manual labels exist, run the label-free methods:

```powershell
python run_models.py "C:\path\to\session1" --unsupervised-only
```

For supervised modeling, copy `observations_template.csv` into every session as
`observations.csv`, replace the example, and use the stages `fresh`,
`deteriorating`, or `spoiled`. Then run all three sessions together:

```powershell
python run_models.py "C:\path\to\run1" "C:\path\to\run2" "C:\path\to\run3"
```

The runner produces PCA coordinates, Isolation Forest anomalies, CUSUM change
detection, Logistic Regression, Random Forest, Gradient Boosting, SVM, and HMM
outputs. Supervised validation always holds out a complete session.

`survival_models.py` provides Cox and Weibull AFT models. `rul_models.py`
provides Random Forest, Gradient Boosting, and SVR regressors. Both deliberately
refuse to fit before 10 independent complete sessions are available. Three runs
are useful for prototype classification, but do not identify a dependable RUL
distribution.

These models estimate observed deterioration and are not a food-safety test.

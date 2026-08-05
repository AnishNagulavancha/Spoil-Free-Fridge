# Full non-camera stack result

## Execution

The complete completed-data sensor workflow was rerun from the raw logs:

1. `analyze_session.py` cleaned and feature-engineered three empty controls and
   three chicken sessions.
2. `run_models.py` recalibrated the three local controls and scored the excluded
   pilot plus both confirmations with the frozen eight-hour configuration.
3. `aggregate_site_results.py` aggregated only the two confirmation summaries.
4. The test suite completed with 31 passing tests.

Camera scripts were intentionally excluded. `Datalog_pcb.py` was not executed
because it is the hardware acquisition program and would begin a new session.
`model_data.py`, `experiment_config.py`, and `unsupervised_models.py` are library
modules exercised by the runners and tests rather than standalone commands.

Raw logs were not changed. S012 Chicken 2's documented role correction was
applied in staged analysis metadata: recorded role `pilot`, corrected analysis
role `confirmation`.

## Control calibration

- Empty controls: S005, S006, and S007
- Reporting window: 0–8 hours
- Aggregation: five-minute medians
- Selected/frozen CUSUM threshold: `h=30`
- Block-bootstrap null false-session estimate: 1.25%
- Index scale: `full_scale_z=40`
- Frozen weights: NH3 0.30, H2S 0.35, CH4 0.10, BME 0.25

The controls contained 7, 2, and 0 discarded invalid post-warmup rows,
respectively, out of approximately 15,000 raw rows per session. All three
provided complete eight-hour coverage.

## Chicken sessions

| Metric | S010 excluded pilot | Confirmation 1 | Confirmation 2 |
|---|---:|---:|---:|
| Primary event | Detected | Detected | Detected |
| Detection latency | 4.08 h | 3.75 h | 1.75 h |
| Index at 1 h | 3.50 | 1.01 | 3.46 |
| Index at 2 h | 3.83 | 3.94 | 16.12 |
| Index at 3 h | 4.56 | 2.35 | 13.37 |
| Index at 4 h | 19.16 | 17.22 | 21.30 |
| Index at 6 h | 80.45 | 53.38 | 76.84 |
| Index at 8 h | 79.47 | 89.53 | 80.18 |
| AUC, 0–8 h | 292.03 | 264.62 | 313.96 |

The two confirmation runs have:

- detection latency mean 2.75 h, SD 1.41 h, range 1.75–3.75 h;
- mean Change Index 19.26 at hour 4;
- mean Change Index 65.11 at hour 6;
- mean Change Index 84.85 at hour 8; and
- mean 0–8 h AUC 289.29 index-hours, SD 34.89.

Both confirmations pass the frozen protein-gas-plus-BME primary rule. The
earlier event in Confirmation 2 represents accumulated sustained evidence, not
a single spike. All three trajectories show a similar major rise around hours
4–6 despite different early-session timing.

## PCA and Isolation Forest

The control-null bins have an Isolation Forest anomaly fraction of 22.1%. The
three chicken sessions have overall anomaly fractions of 88.7–97.9%, and every
five-minute bin from hours 4–8 is anomalous in all three chicken sessions.

Median absolute PC1 magnitude is 0.69 for control-null data. During hours 4–8
it is 32.33 for the excluded pilot, 14.53 for Confirmation 1, and 32.06 for
Confirmation 2. These results support strong multivariate separation from the
control state. They are supporting unsupervised diagnostics, not calibrated
spoilage probabilities.

## Interpretation

The full sensor stack consistently distinguishes these chicken sessions from
the local empty-control behavior and reproduces a strong multi-sensor rise in
both confirmation runs. This is meaningful proof-of-concept evidence for a
repeatable deterioration-associated headspace response in House A with this
PCB and chamber.

The current evidence does not calibrate the 0–100 index to percentage spoiled,
establish an edibility or safety threshold, prove microbiological spoilage, or
demonstrate operation in other houses. Trend, acceleration, volatility, and Q10
biological-age features are generated during feature engineering, but the
frozen primary event and displayed index currently use the four
control-adjusted delta channels; the extra features are not silently treated as
independent evidence.

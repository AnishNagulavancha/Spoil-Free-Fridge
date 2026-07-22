# Prototype 1 control-calibrated workflow

This pipeline measures chicken-associated gas and visible change relative to
local empty controls and an early post-insertion reference. It does not
determine microbiological safety, report a percentage spoiled, or estimate the
exact time chicken becomes unsafe.

## Final four-hour protocol

Every session contains:

```text
30-minute empty-chamber warmup
4-hour post-prompt recording
  first 30 minutes: post-prompt baseline
  remaining 3.5 hours: detection period
images every 5 minutes
```

The four-hour window is a practical proof-of-concept choice. A sustained event
within four hours supports sensor responsiveness. No event is inconclusive
rather than proof that the sensors cannot work, because the measurable response
may develop later. Every chicken sample is experimental waste and must not be
eaten or re-refrigerated.

For one development site, collect sessions in this order:

```text
C1 empty control
C2 empty control
C3 empty control
P1 excluded chicken pilot
freeze every global parameter
P2 chicken confirmation
P3 chicken confirmation
```

`LOG_MINUTES` is 240 and is measured after the insertion/control prompt, so
each complete session takes about 4.5 hours including warmup. Controls use the
same prompt handling: open and close the chamber without adding food.

Run feature engineering after every session:

```powershell
python analyze_session.py "C:\path\to\session"
```

## Multiple houses and PCBs

Set `PCB_DESIGN_ID` to the shared hardware design and assign unique `SITE_ID`,
`DEVICE_ID`, `OPERATOR_ID`, `CONTAINER_ID`, and `SESSION_ID` values in
`Datalog_pcb.py`. The same PCB design does not make two physical boards or
houses identical. Record sample ID, cut, measured mass, and source batch for
each chicken run.

Each site/PCB/device/container combination needs its own three four-hour empty
controls and its own `control_calibration.joblib`. Local calibration estimates
that setup's drift and noise. The global configuration—sensor directions,
CUSUM rule, persistence, weights, scale mapping, and reporting times—must remain
identical across houses.

Do not merge raw voltages from different houses. Compare or combine only
session-level, locally standardized results such as detection latency,
`AUC_0_4h`, and index values at 1, 2, 3, and 4 hours. If Houses A and B are used
to develop the common rules, test the frozen procedure at an untouched House C
before claiming external generalization. Evidence from two houses supports
cross-site feasibility, not operation in every possible house.

An efficient two-house confirmation layout is:

```text
House A: 3 local controls + 1 excluded pilot + 1 confirmation
House B: 3 local controls + 1 confirmation using the same frozen global rules
```

Those two chicken confirmations count as independent cross-site replications.
They provide less evidence about repeatability within either one house than two
confirmations per house would.

## Frozen configuration and weights

`experiment_config.json` is the single source of truth for five-minute
aggregation, the four-hour AUC window, reporting times, control smoothing,
leave-one-control-out scale estimation, CUSUM candidates, persistence, sensor
directions, index mapping, channel weights, and camera quality thresholds.

`analyze_session.py` creates individual sensor features only. It intentionally
does not create a weighted `gas_state`. The only weighted score is the final
0–100 Deterioration-Associated Change Index created by
`unsupervised_models.py`.

The current NH3/H2S/CH4/BME weights are a pre-registered protein-food
engineering heuristic, not fitted coefficients. They affect the displayed
index but do not determine the primary event. The primary event independently
requires:

```text
(NH3 or H2S protein-gas evidence) AND BME688 broad-VOC evidence
```

CH4 remains supporting evidence. Zero means little control-adjusted movement;
100 means the engineered channels reached the frozen full-scale response. It
does not mean 0% or 100% spoiled.

Before confirmation scoring:

1. Verify `sensor_direction` independently of confirmation data.
2. Record the direction source as
   `datasheet_and_independent_response_test` or `excluded_chicken_pilot`.
3. Use only the excluded pilot to select `index.full_scale_z`.
4. Check the heuristic weights and document them before confirmation.
5. Set `parameters_frozen` to `true`.
6. Do not edit parameters after seeing confirmation results.

If a confirmation result causes a parameter change, that session becomes
development data and a new untouched confirmation is required.

## Local control calibration

After three controls from one site/device/container have
`analysis/features.csv`, run:

```powershell
python run_models.py `
  --controls "C:\data\house_A\C1" "C:\data\house_A\C2" "C:\data\house_A\C3" `
  --output-dir "house_A_model"
```

The runner refuses to mix controls with different site, PCB design, device, or
container IDs. Calibration performs:

- five-minute median aggregation;
- a pooled, smoothed local-control drift curve;
- leave-one-control-out correction and robust MAD residual scale;
- block-bootstrap selection of the smallest CUSUM `h` meeting the configured
  end-to-end false-session target;
- PCA fitted only on local control-null standardized channels; and
- Isolation Forest fitted only on local control-null standardized channels.

## Pilot and confirmation scoring

Score the excluded pilot with the matching local artifact:

```powershell
python run_models.py `
  --calibration "house_A_model\control_calibration.joblib" `
  --targets "C:\data\house_A\P1" `
  --output-dir "house_A_pilot"
```

After freezing the configuration, score untouched confirmations without
recalibrating or changing parameters:

```powershell
python run_models.py `
  --calibration "house_A_model\control_calibration.joblib" `
  --targets "C:\data\house_A\P2" "C:\data\house_A\P3" `
  --output-dir "house_A_confirmation"
```

The artifact can only score the same site/PCB/device/container identity as its
controls. A second house follows the same commands with its own three controls
and local artifact but the same frozen `experiment_config.json`.

Outputs include individual control-adjusted z-scores, clipped channel indices,
the engineered 0–100 Change Index, per-channel CUSUM, the primary event,
supporting-channel count, shared PCA coordinates, Isolation Forest anomaly
score, detection latency, indices at 1–4 hours, and fixed-window `AUC_0_4h`.
AUC is invalidated when coverage or gap rules fail. Raw monotone trajectory
correlation is intentionally not reported.

After separately scoring frozen confirmations at multiple houses, combine only
their session summaries:

```powershell
python aggregate_site_results.py `
  "house_A_confirmation\P2" `
  "house_B_confirmation\P2" `
  --output "cross_site_summary.json"
```

The aggregator rejects pilots, unfrozen runs, protocol mismatches, and weight
mismatches. It reports both overall and per-site descriptive metrics without
pooling adjacent raw sensor rows.

The current algorithm detects a sustained response after it appears. It does
not yet forecast future deterioration. A suitable confirmation conclusion is:

> The frozen model detected the expected deterioration-associated multi-sensor
> pattern in an independent chicken session.

## Camera analysis and observations

Run each chicken session with one fixed chicken ROI and one stationary
background ROI:

```powershell
python run_camera_models.py "C:\path\to\session" `
  --roi .1,.2,.9,.9 `
  --background-roi 0,0,1,.15
```

The camera uses baseline-relative color, histogram, texture, edge, and pixel
difference features. A per-session Isolation Forest is initialized from the
first 30 post-prompt minutes. Fog is suspected only when both the subject and
stationary background Laplacian-variance ratios fall below their frozen
thresholds. Unreliable frames cannot build a sustained event, and reliability
is reported by hour.

Manual records use `observations_template.csv` and describe only appearance
visible through the closed chamber. Do not assign guessed `fresh`,
`deteriorating`, or `spoiled` ground truth, and do not repeatedly open the
chamber for smell or texture checks.

## Future supervised prediction

Supervised classification, survival, and direct RUL models are intentionally
not included. The present algorithm performs control-calibrated detection.
Predicting future state requires many independent sessions plus matched ground
truth such as APC/TVC, TVB-N, and pH. Any future train/test split must be by
complete session and site, never by adjacent sensor rows.

## Installation and learning

```powershell
python -m pip install -r requirements.txt
```

See `LEARNING_RESOURCES.md` for the theory, implementation references, and an
accelerated two-week study plan.

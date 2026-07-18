# Prototype 1 control-calibrated workflow

This pipeline measures chicken-associated gas and visible change relative to an
early post-insertion reference. It does not determine microbiological safety or
report a percentage spoiled.

## Experimental roles

Collect sessions in this order where practical:

```text
C1 empty control
C2 empty control
P1 excluded chicken pilot
C3 empty control
freeze every parameter
P2 chicken confirmation
P3 chicken confirmation
```

Set `SESSION_ROLE` in `Datalog_pcb.py` to `control`, `pilot`, or
`confirmation`. Every session uses a 30-minute empty warmup, a prompt event, a
30-minute post-prompt baseline, five-minute images, and a 12-hour post-prompt
duration. For controls, open and close the chamber without inserting food.

Run feature engineering for every sensor session:

```powershell
python analyze_session.py "C:\path\to\session"
```

## Frozen configuration

`experiment_config.json` contains every analysis choice: five-minute
aggregation, control smoothing, leave-one-control-out scale estimation, CUSUM
candidate limits, persistence, channel directions, 0–100 mapping, fixed AUC
window, missing-data rules, and camera quality thresholds.

Before control calibration and confirmation scoring:

1. Verify `sensor_direction` independently of confirmation data. Benign mixed
   odors may demonstrate responsiveness but do not identify analyte-specific
   direction.
2. Record the direction source in `sensor_direction_source` as
   `datasheet_and_independent_response_test` or `excluded_chicken_pilot`.
3. Use the excluded pilot to select `index.full_scale_z`.
4. Re-run control calibration if a direction changes after an exploratory run.
5. Set `parameters_frozen` to `true` before confirmation scoring.
6. Do not edit the configuration after seeing confirmation results.

## Control calibration

After all three controls have `analysis/features.csv`, run:

```powershell
python run_models.py `
  --controls "C:\data\C1" "C:\data\C2" "C:\data\C3" `
  --output-dir "model_output"
```

Calibration performs the following for NH3, H2S, CH4, and inverted BME688
resistance:

- five-minute median aggregation;
- a pooled, smoothed control drift curve;
- leave-one-control-out correction and robust MAD null scale;
- block-bootstrap selection of the smallest CUSUM `h` meeting the configured
  end-to-end false-session target;
- PCA fitted only on control-null standardized channels;
- Isolation Forest fitted only on control-null standardized channels.

The primary trigger is deliberately stringent:

```text
(NH3 or H2S protein-gas evidence) AND BME688 broad-VOC evidence
```

CH4 is supporting evidence. Supporting channels are not described as
independent; control and target correlation matrices are saved.

## Pilot and confirmation scoring

Score the excluded pilot with the saved control artifact:

```powershell
python run_models.py `
  --calibration "model_output\control_calibration.joblib" `
  --targets "C:\data\P1" `
  --output-dir "pilot_output"
```

After freezing the config, score confirmations without recalibrating:

```powershell
python run_models.py `
  --calibration "model_output\control_calibration.joblib" `
  --targets "C:\data\P2" "C:\data\P3" `
  --output-dir "confirmation_output"
```

Outputs include per-channel control-adjusted z-scores, explicit clipped channel
indices, the 0–100 Deterioration-Associated Change Index, per-channel CUSUM,
the protein/BME primary event, supporting-channel count, shared PCA coordinates,
Isolation Forest anomaly score, fixed-time indices, detection latency, and
fixed-window `AUC_0_12h`. AUC is invalidated when configured coverage or gap
rules are not met; truncated runs are never compared as if they were 12 hours.
Raw monotone trajectory correlation is intentionally not reported.

## Camera analysis

Run each session with one fixed chicken ROI and one stationary background ROI:

```powershell
python run_camera_models.py "C:\path\to\session" `
  --roi .1,.2,.9,.9 `
  --background-roi 0,0,1,.15
```

The camera extracts baseline-relative color, histogram, texture, edge, and
pixel-difference features. Isolation Forest is trained on the first 30 minutes
of post-prompt images. Fog is suspected only when both the subject and fixed
background Laplacian-variance ratios fall below their frozen thresholds.
Unreliable frames cannot contribute to a sustained event. Sustained camera
change requires five consecutive reliable anomalous frames. Reliability is
reported by hour, not only as one aggregate percentage. Confirmation camera
analysis refuses to run without a background ROI.

Manual records use `observations_template.csv` and describe visible appearance
only (`no_visible_change`, `minor_visible_change`, or `major_visible_change`).
Do not use guessed `fresh` or `spoiled` labels, and do not open room-temperature
chicken repeatedly for odor or texture checks.

## Future supervised and RUL work

Supervised classification, sequence, survival, and direct RUL prototypes are
intentionally not included in this repository. Three chicken runs without
independent reference measurements are not enough to train or validate those
models. Add them only after collecting many independent sessions with ground
truth such as APC/TVC, TVB-N, and pH, while splitting train and test data by
session rather than by row.

## Installation and learning

Install the dependencies used by the active pipeline:

```powershell
python -m pip install -r requirements.txt
```

See `LEARNING_RESOURCES.md` for a module-by-module reading path, theory links,
and small implementation exercises.

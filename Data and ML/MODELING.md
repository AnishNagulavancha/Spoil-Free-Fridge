# Sensor and camera modeling workflow

This prototype detects control-adjusted headspace change. It does not measure
microbial counts, determine food safety, report a percentage spoiled, or provide
a validated remaining-useful-life estimate.

## Active analysis versions

- `configs/house_a_v1.json` reproduces the completed House A analysis. Its
  primary event is `(NH3 OR H2S) AND BME`.
- `configs/house_a_v2_candidate.json` is frozen for the next prospective test.
  Its primary event is `H2S AND BME`, selected from the excluded pilot and
  cross-fitted controls. It is not yet prospectively validated.

The acquisition metadata retains the historical protocol identifier
`prototype_1_control_calibrated_4h_v2` for compatibility. The active analysis
window is eight hours.

## Acquisition and feature generation

`Datalog_pcb.py` records sensors, images, metadata, a 30-minute empty-chamber
warmup, and the post-prompt session. A prospective session used for the frozen
analysis must contain at least eight post-prompt hours.

After acquisition, create the one-minute features:

```powershell
python analyze_session.py "C:\path\to\session"
```

The default is the v2 candidate configuration. Use `--config` explicitly when
reproducing v1.

## Local control calibration

Each site/device/container requires its own controls. Do not pool raw voltages
across houses.

```powershell
python run_models.py `
  --controls "C:\data\C1" "C:\data\C2" "C:\data\C3" `
  --config configs\house_a_v2_candidate.json `
  --output-dir "house_A_v2_model"
```

Calibration estimates smoothed drift, leave-one-control-out MAD scales, the
control-null CUSUM behavior, PCA, Isolation Forest, and the environmental range
represented by the controls.

## Prospective scoring

Do not change the v2 candidate before scoring the next untouched session:

```powershell
python run_models.py `
  --calibration "evaluation_output\house_a_v2_candidate\control_calibration_candidate.joblib" `
  --targets "C:\data\new_session" `
  --config configs\house_a_v2_candidate.json `
  --output-dir "prospective_v2_result"
```

Interpret the outputs as follows:

- The 0–100 Change Index is an engineered response magnitude, not a spoilage
  percentage.
- The Boolean event is sustained multichannel departure from the control model,
  not the moment food becomes unsafe.
- `environment_domain_warning=true` means the session left the temperature or
  humidity range represented by the controls; the event remains visible but
  requires caution.
- AUC is always evaluated over the fixed 0–8-hour window.

## Reproduction and robustness

Rebuild the completed v1 robustness outputs with:

```powershell
python house_a_robustness.py
```

Rebuild the frozen v2 candidate selection and diagnostics with:

```powershell
python run_house_a_v2_candidate.py
```

Canonical generated results are kept in:

- `evaluation_output/full_stack_4runs_20260806` — processed House A sessions
  and the original v1 calibration;
- `evaluation_output/house_a_v1_robustness` — v1 robustness findings;
- `evaluation_output/house_a_v2_candidate` — frozen v2 candidate artifact and
  retrospective diagnostics.

## Camera analysis

Camera analysis is optional and separate from the present sensor conclusion:

```powershell
python run_camera_models.py "C:\path\to\session" `
  --roi .1,.2,.9,.9 `
  --background-roi 0,0,1,.15
```

Fogged or unreliable frames are flagged and cannot establish food safety.

## Cross-site results

Score every site with its own local calibration but the same frozen global
configuration. Combine only confirmation-level summaries:

```powershell
python aggregate_site_results.py `
  "house_A_result\sensor_summary.json" `
  "house_B_result\sensor_summary.json" `
  --output cross_site_summary.json
```

Generalization requires prospective sessions from additional devices, houses,
environmental ranges, and ultimately independent biological ground truth.

## Installation and tests

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

See `LEARNING_RESOURCES.md` for theory and implementation references.

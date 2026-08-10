# House A robustness analysis

## Status

HouseA_v1 remains the primary frozen result. All analyses below are robustness
checks or retrospective exploratory analyses; none changes the frozen result.

## Frozen benchmark

- Confirmations detected: 3/3
- Calibration-control events under the full calibration: 0/3
- Confirmation detection range: 1.75–3.75 h
- Confirmation AUC range: 206.48–313.48
- Calibration-control AUC range: 0.47–10.92

The controls above participated in calibration; their zero-event count is a
calibration diagnostic, not an independent false-positive estimate.

## Full leave-one-control-out result

- Held-out controls with events: 1/3
- Confirmation detections across folds: 3–3 of 3
- Minimum fold-level absolute AUC margin: 118.83
- Detection times across calibrations: 1.25–4.25 h

## Parameter sensitivity

- 23/23 configurations retained all three confirmation events.
- 0/23 produced zero leave-one-control-out control events.
- 23/23 retained a positive minimum-chicken minus maximum-control AUC margin.
- 0/23 (0.0%) met all three criteria simultaneously.

These are grid-robustness proportions, not probabilities that the detector is
biologically correct.

## Ablation

- Event rules retaining 3/3 confirmations and 0/3 controls: h2s_and_bme
- Index variants with positive minimum-confirmation minus maximum-control AUC margin: 6/6

## Control bootstrap stress test

For the eight-hour window, conditional moving-block bootstrap false-session
rates ranged from 0.00% to
16.35% across 15–90 minute blocks. The
intervals in the CSV quantify Monte Carlo error only; three observed controls
cannot characterize between-session or between-house uncertainty.

One of 12 shifted-baseline control stress tests produced an event.
It was house_A_pcb_A_S005_Anish_control_empty_20260724_125849
with a 120-minute shift. This shows that the cumulative event can be
sensitive to baseline placement even when the displayed index remains small.

## Environmental sensitivity

Environment-adjusted detection pairs (original → adjusted, hours):
3.75 → 5.92; 1.75 → 5.50; 2.00 → 8.75.

Every environmental result is exploratory because the chicken sessions extend
beyond the control humidity/temperature training domain. A changed detection
time demonstrates sensitivity to the adjustment; it does not identify a true
biological onset.

The prespecified delta-RH plus delta-temperature model had mean held-out RMSE
0.0800, versus 0.0705 for the simple time-only regression.
It therefore did not improve aggregate control generalization and should not
replace the frozen correction.

## Alternative transition estimates

The detailed table distinguishes online CUSUM onset, a control-calibrated rapid
rise, Page–Hinkley onset, and an offline whole-trajectory mean shift. Agreement
indicates a stable statistical transition, not microbiological validation.
The offline mean-shift locations were
4.75 h, 4.75 h, 6.67 h;
their absolute shift magnitudes exceeded every leave-one-control-out control,
although their normalized SSE gains did not. Page–Hinkley onsets were
4.92 h, 4.67 h, 6.33 h.

## Session-level inference

- Perfect descriptive AUC ordering: True
- LOO-control AUC range: 0.31–54.18
- Confirmation AUC range: 206.48–313.48
- Pairwise Hodges–Lehmann location difference: 238.20 index-hours

No formal permutation p-value is reported because the available controls define
the calibration and are not untouched exchangeable validation sessions.

## Quality flags

The quality flags are deterministic diagnostics, not calibrated probabilities.
Flag counts across confirmations: 3, 3, 3.

## Conclusion

The magnitude separation is robust: every parameter and index ablation retained
a positive chicken-versus-control AUC margin. The exact Boolean event and its
onset are less robust because one cross-fitted control fires and onset varies
with calibration and transition method. The appropriate claim remains that
chicken exposure produced a repeatable, sustained, control-adjusted multichannel
headspace response in the House A apparatus. These analyses cannot establish
microbial spoilage, food safety, remaining useful life, or universal household
performance.

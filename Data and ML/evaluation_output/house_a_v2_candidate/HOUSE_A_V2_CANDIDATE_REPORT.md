# HouseA_v2 candidate report

## Status

Frozen development candidate awaiting prospective validation. It must not
replace HouseA_v1 for claims about the completed confirmation experiments.

## Development-only rule selection

Candidate rules were evaluated using only the excluded pilot and three
leave-one-control-out controls. Confirmation outcomes were not inputs to the
selection calculation.

The analysts had already inspected the confirmation results before this
calculation was created, so this is not equivalent to blinded model selection.
That is why a new prospective experiment remains mandatory.

- Eligible multichannel rules: h2s_and_bme
- Selected rule: H2S AND BME
- Pilot detection: 4.17 h
- Leave-one-control-out events: 0/3

## Retrospective confirmation check

- Confirmations detected: 3/3
- Detection times: 4.00 h, 2.83 h, 2.00 h
- Full-calibration control events: 0/3
- Minimum leave-one-control-out chicken/control AUC margin: 118.83

The continuous index and weights are unchanged from HouseA_v1. Only the Boolean
event rule changed, so AUC and displayed index values remain directly
comparable.

## Conditional false-alarm stress test

Eight-hour moving-block bootstrap rates range from
0.00% to
5.35% across the tested block lengths.
These are conditional simulations based on three controls, not a household
false-alarm guarantee.

## Candidate parameter sensitivity

23/23 prespecified one-factor configurations retained all
three retrospective confirmation events and zero leave-one-control-out control
events. AUC separation remained positive in
23/23 configurations.
This is retrospective robustness, not prospective validation.

## Environmental handling

Environmental compensation remains disabled. The previously tested RH/T model
did not improve held-out-control RMSE and all chicken trajectories left the
control environmental domain. HouseA_v2 therefore retains the original drift
correction and reports environmental-domain violations as diagnostic flags.

## Decision

The H2S-and-BME candidate removes the observed S005 cross-fitted event while
retaining the pilot and all three retrospective confirmations. Its parameters
are now frozen for the next prospective control and chicken sessions, but the
existing confirmation data cannot validate a rule developed after their
analysis.

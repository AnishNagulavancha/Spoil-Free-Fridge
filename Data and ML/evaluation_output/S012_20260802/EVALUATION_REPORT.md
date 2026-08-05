# S012 first chicken confirmation evaluation

## Scope

- Target: `S012_Anish_chicken2` (confirmation; operator-corrected after acquisition)
- Comparison chicken pilot: `S010_Anish_chickenreal1`
- Local controls: `S005_Anish`, `S006_Anish`, and `S007_Anish`
- Matched primary window: 0–8 hours
- Aggregation: 5-minute medians
- Change Index scale: `full_scale_z = 40`; existing sensor weights unchanged
- Interpretation: engineered control-adjusted change, not a spoilage percentage or safety assessment

S012 recorded approximately 10.8 hours. Only the first eight hours are used for the matched primary comparison because the controls cover eight hours.

The logger metadata recorded `session_role=pilot`, but the operator confirmed after acquisition that this was an entry mistake and that S012 was intended as the first confirmation run. The original metadata is retained unchanged for auditability; `role_correction.json` records the correction. There is also a documented protocol deviation: the eight-hour analysis window and control-only `h=30` calibration were not committed to the main configuration before acquisition.

## Data quality

- Sensor rows read: 20,336
- Valid post-warmup rows retained: 19,435
- Invalid post-warmup rows: 0
- One-minute feature rows: 649
- Successful images: 131 of 131 attempts
- Baseline feature rows: 31

The S012 baseline was numerically stable, but its starting H2S voltage (0.019 V) and BME resistance (about 145 kOhm) were lower than the earlier controls and S010. Relative normalization reduces the effect of this offset, but the shift should be monitored as possible sensor recovery, chamber carryover, or ordinary device drift.

## Control-only CUSUM calibration

The original candidate range (`h = 5–8`) failed the configured null target. At `h = 8`, the block-bootstrap false-session estimate was 66%, and one observed control fired.

An expanded threshold scan used only the empty controls. The minimum threshold satisfying both a bootstrap false-session rate at or below 5% and zero primary events in the three observed controls was:

- Selected `h`: 30
- Estimated bootstrap false-session rate: 1.25%
- Primary control events: 0 of 3

This change was not selected using either chicken trajectory.

## Sensor comparison

| Metric | Control range | S010 pilot | S012 confirmation |
|---|---:|---:|---:|
| Sustained-change detection | None at `h=30` | 4.08 h | 3.75 h |
| Index at 1 h | 0.02–1.61 | 3.50 | 1.01 |
| Index at 2 h | 0.04–1.39 | 3.83 | 3.94 |
| Index at 3 h | 0.01–1.39 | 4.56 | 2.35 |
| Index at 4 h | 0.00–1.44 | 19.16 | 17.22 |
| Index at 6 h | 0.05–2.07 | 80.45 | 53.38 |
| Index at 8 h | 0.00–3.35 | 79.47 | 89.53 |
| Maximum index | 0.39–4.60 | 91.40 | 91.17 |
| AUC, 0–8 h | 0.48–10.92 | 292.03 | 264.62 |

At four hours, the per-channel 0–100 contributions were:

| Channel | S010 | S012 |
|---|---:|---:|
| NH3 | 27.31 | 19.23 |
| H2S | 17.57 | 17.76 |
| CH4 | 6.97 | 5.08 |
| BME inverted resistance | 16.48 | 18.91 |

The primary rule is therefore supported in both the excluded pilot and first confirmation: a protein-gas channel and BME are active, with both NH3 and H2S contributing. The maximum indices agree closely, and the eight-hour AUC differs by about 9.4%. The six-hour values differ more substantially, demonstrating real session-to-session timing variation.

## Environmental coupling

S012 contains broad cycles in which all gas channels, BME resistance, humidity, and temperature move together. For five-minute first differences over 0–8 hours, correlation with humidity ranged from about 0.26 to 0.75 across the four adjusted sensor channels. This common-mode behavior means the channels cannot be treated as four independent biological measurements.

The sustained four-hour-to-eight-hour envelope remains much larger than the controls, but temperature/humidity compensation or a confidence penalty is needed before deployment.

The BME temperature was near 30–31 C in controls and chicken runs, producing approximately 51 biological-age hours during eight elapsed hours. This is probably chamber/PCB-adjacent temperature rather than chicken core temperature, so Q10 biological age should remain supporting metadata rather than ground truth.

## Camera result

- S010 first sustained visual anomaly: approximately 70 minutes
- S012 first sustained visual anomaly: approximately 45 minutes
- S012 reliable-frame fraction: 83.7%
- S012 frames rejected as fogged/unreliable: 21
- S012 reliability falls to 41.7% in hour 8 and 12.5% in hour 10

The S012 images become dramatically darker, and the visual model fires soon after its 30-minute baseline. The camera result cannot currently distinguish chicken appearance from illumination/exposure change and is not counted as independent deterioration evidence.

## Conclusion

S012 provides meaningful preliminary confirmation of the gas result. The excluded pilot and first confirmation separate strongly from the local controls, produce the required protein-gas-plus-BME agreement, reach similar maximum indices, and detect sustained change within 20 minutes of each other using the control-only `h = 30` threshold.

This supports repeatable control-adjusted headspace change in this device and household. It does not establish microbiological spoilage, absolute freshness, food safety, or transfer to another household.

Before confirmation runs 2 and 3, commit the eight-hour protocol and `h = 30` to the main configuration, retain `full_scale_z = 40`, document sensor directions, correct or gate environmental common-mode effects, and stabilize camera illumination/exposure. S010 remains the excluded pilot. S012 is retained as confirmation run 1 with the role correction and configuration-timing deviation disclosed.

# Chicken 3 / Confirmation Run 2 evaluation

## Frozen analysis

- Session folder: `house_A_pcb_A_S012_Anish_chicken3_confirmation_chicken_20260804_182348`
- Role: confirmation run 2 (third usable chicken trajectory including the excluded pilot)
- Local controls: S005, S006, and S007
- Matched window: 0–8 hours after insertion
- Aggregation: 5-minute medians
- CUSUM: `k=0.5`, `h=30`, 3-bin persistence
- Change Index: `full_scale_z=40` with the existing frozen sensor weights
- No parameters were selected or changed using this run

The logger was configured for up to 24 hours and was stopped after approximately
15 hours. Only hours 0–8 are used here so the run remains directly comparable to
the three eight-hour empty controls and the earlier chicken trajectories.

## Data quality

- Sensor rows read: 27,826
- Warmup rows discarded: 901
- Valid post-warmup rows: 26,925
- Corrupt or invalid post-warmup rows: 0
- One-minute feature rows: 899
- Baseline feature rows: 31
- Images captured successfully: 181 of 181 attempts

The food baseline was usable, although BME resistance and gas-channel starting
levels differ from the previous confirmation run. This is consistent with
session-to-session sensor state, sample condition, chamber carryover, or a
combination of these factors.

## Sensor result

| Metric | Empty-control range | S010 excluded pilot | Confirmation 1 | Confirmation 2 |
|---|---:|---:|---:|---:|
| Sustained detection | None | 4.08 h | 3.75 h | **1.75 h** |
| Index at 1 h | 0.02–1.61 | 3.50 | 1.01 | **3.46** |
| Index at 2 h | 0.04–1.39 | 3.83 | 3.94 | **16.12** |
| Index at 3 h | 0.01–1.39 | 4.56 | 2.35 | **13.37** |
| Index at 4 h | 0.00–1.44 | 19.16 | 17.22 | **21.30** |
| Index at 6 h | 0.05–2.07 | 80.45 | 53.38 | **76.84** |
| Index at 8 h | 0.00–3.35 | 79.47 | 89.53 | **80.18** |
| AUC, 0–8 h | 0.48–10.92 | 292.03 | 264.62 | **313.96** |

Confirmation 2's primary event is not a one-bin spike. It begins at 1.75 hours
and remains active for all 76 subsequent five-minute bins through hour 8. NH3
activates at 1.58 hours, BME at 1.75 hours, H2S at 2.83 hours, and CH4 at 4.58
hours. At hour 4 the channel indices are NH3 29.57, H2S 24.49, CH4 3.45, and
BME 14.05. At hour 8 they are NH3 100, H2S 100, CH4 11.28, and BME 56.19.

The early detection should not be interpreted as an independently verified
spoilage time. The curve has an early moderate plateau, followed by the same
large acceleration around 3.5–5.5 hours seen in the earlier chicken runs. The
different latency could reflect starting sample condition, headspace buildup,
sensor recovery, or chamber carryover.

Five-minute first-difference correlations with humidity and temperature are
small to moderate in this run (largest absolute value approximately 0.36), so
the major trajectory is not explained by a simple temperature/humidity change.
The adjusted gas channels are nevertheless highly correlated with one another
(`r` approximately 0.88–0.98), and therefore cannot be counted as four
independent biological measurements.

## Camera result

The automated camera output reports 100% reliable frames, no fog detections,
and sustained visual change beginning at approximately 55 minutes. Visual
inspection shows that the camera/chamber viewpoint shifts sharply at about 65
minutes. Brightness also changes substantially. The current fog gate detects
blur and condensation but does not detect camera displacement. Consequently,
the camera anomaly is invalid as deterioration evidence for this run and must
be excluded from the multimodal result.

## Conclusion

The sensor result is positive and meaningfully strengthens repeatability. All
three chicken trajectories separate strongly from the three empty controls and
show a similar large rise by hours 4–6. Both confirmation runs pass the frozen
protein-gas-plus-BME CUSUM rule. This supports repeatable, control-adjusted
chicken headspace deterioration-related change in this device and chamber.

It does not calibrate the 0–100 scale to a percentage spoiled, establish an
edibility threshold, prove microbiological spoilage, or demonstrate transfer to
another house. The next analysis priority is the remaining confirmation run,
followed by a held-out evaluation summary and a camera displacement/registration
gate before camera evidence is used.

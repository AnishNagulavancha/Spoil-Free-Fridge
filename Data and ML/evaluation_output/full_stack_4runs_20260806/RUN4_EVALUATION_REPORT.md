# Chicken 4 / Confirmation Run 3 evaluation

## Scope and data quality

- Completed session: `house_A_pcb_A_S012_Anish_chicken4_confirmation_chicken_20260805_225737`
- The similarly named `...225726` folder is an initialization-only folder with
  no sensor log and was excluded.
- Frozen analysis: 0–8 hours, five-minute medians, CUSUM `k=0.5`, `h=30`,
  `full_scale_z=40`, and the existing sensor weights.
- The three empty controls were reprocessed and recalibrated consistently; no
  parameter was selected using Run 4.

The logger produced 22,512 rows. Of these, 899 warmup rows were removed, zero
post-warmup rows contained corrupt sensor values, seven exact duplicate records
were removed, and 21,606 valid post-warmup measurements were retained.

The first cleaning pass appeared to reject 3,449 rows because serial backlog
can assign the same rounded host timestamp and elapsed value to multiple
different buffered sensor readings. Deduplication was corrected to remove only
exactly duplicated measurement records. All controls and chicken sessions were
then reprocessed. This changed earlier numerical scores only slightly and did
not change any detection decision.

Run 4's baseline was more variable than the earlier chicken baselines. The
baseline coefficients of variation were 2.36% for NH3, 5.67% for H2S, 3.05%
for CH4, and 8.77% for BME resistance. This reduces confidence in interpreting
the early-session timing precisely.

## Run 4 result

- Frozen primary event: detected at 2.00 hours
- Event persistence: continuously active from 2.00 through 8.00 hours
- Index at 1 hour: 9.38
- Index at 2 hours: 11.98
- Index at 3 hours: 12.96
- Index at 4 hours: 13.61
- Index at 6 hours: 27.96
- Index at 8 hours: 87.28
- AUC, 0–8 hours: 206.48 index-hours
- Maximum over the complete recorded session: 91.71

Channel CUSUM activation occurred at 1.00 hour for BME, 2.00 hours for H2S,
2.33 hours for NH3, and 3.33 hours for CH4. At hour 8 the channel indices were
NH3 100, H2S 100, CH4 9.10, and BME 85.47.

BME first-difference response has moderate correlation with humidity (0.49)
and temperature (0.46), so the early BME contribution is not cleanly
independent of chamber warming and moisture. The later hour-8 state includes
strong NH3 and H2S contributions as well as BME.

Isolation Forest marks 99.0% of Run 4's eight-hour bins anomalous relative to
the control-null state, and every bin from hours 4–8 is anomalous. This is
supporting separation evidence rather than a probability of spoilage.

## Comparison with earlier chicken runs

| Metric | Excluded pilot | Confirmation 1 | Confirmation 2 | Confirmation 3 |
|---|---:|---:|---:|---:|
| CUSUM detection | 4.08 h | 3.75 h | 1.75 h | **2.00 h** |
| Index at 4 h | 19.12 | 17.17 | 21.26 | **13.61** |
| Index at 6 h | 80.31 | 53.30 | 76.73 | **27.96** |
| Index at 8 h | 79.31 | 89.32 | 80.04 | **87.28** |
| AUC, 0–8 h | 291.45 | 264.13 | 313.48 | **206.48** |

As a descriptive secondary comparison—not a new frozen decision threshold—the
first three chicken trajectories remain above index 50 for three consecutive
bins by 4.92–5.00 hours. Run 4 does not do so until 6.83 hours. Thus its major
response is approximately 1.8–1.9 hours later, even though the cumulative
CUSUM detects its smaller early departure at 2.00 hours.

This delayed large rise is consistent with the colder/refrigerated starting
condition, but one differently stored sample cannot establish refrigeration as
the cause. Starting biological age, sensor baseline state, humidity, and
chamber carryover are competing explanations.

## Three-confirmation aggregate

All three confirmation runs detect the frozen primary event. Across them:

- detection latency mean 2.50 h, SD 1.09 h, range 1.75–3.75 h;
- mean index at hour 4: 17.35, SD 3.83;
- mean index at hour 6: 52.67, SD 24.39;
- mean index at hour 8: 85.54, SD 4.88; and
- mean 0–8-hour AUC: 261.36 index-hours, SD 53.55.

The hour-6 variation is large, showing that deterioration trajectories differ
substantially in timing. The hour-8 index is much more repeatable. These results
support a robust eventual chicken-associated headspace response in this local
setup, not an absolute spoilage percentage or food-safety threshold.

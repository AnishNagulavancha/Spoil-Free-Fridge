# Learning guide for the control-calibrated prototype

This guide explains what the active files do, the theory behind them, and a
practical order for learning the implementation. The pipeline estimates
**deterioration-associated sensor and image change**. It does not measure food
safety or microbiological spoilage unless it is validated against laboratory
ground truth.

## 1. Read the project in this order

1. `Datalog_pcb.py` — serial acquisition, warmup/prompt phases, metadata,
   images, and session roles.
2. `analyze_session.py` — parsing, cleaning, timestamp indexing, one-minute
   aggregation, baselines, deltas, rolling slopes, volatility, and biological
   age.
3. `experiment_config.json` and `experiment_config.py` — frozen experimental
   choices and validation.
4. `model_data.py` — loading and resampling complete sessions without treating
   adjacent rows as independent experiments.
5. `unsupervised_models.py` — control drift correction, leave-one-control-out
   scale estimation, CUSUM calibration, PCA, Isolation Forest, and the change
   index.
6. `run_models.py` — command-line orchestration and safeguards separating
   controls, pilot data, and confirmation data.
7. `aggregate_site_results.py` — session-level cross-house summaries without
   pooling autocorrelated raw sensor rows.
8. `image_data.py` and `image_features.py` — image timestamps, ROIs, color,
   histogram, texture, edge, blur, and baseline-relative features.
9. `camera_models.py` and `run_camera_models.py` — camera baseline model,
   condensation gate, anomaly persistence, and reliability by hour.

Before reading the project, work through the
[Python tutorial](https://docs.python.org/3/tutorial/index.html),
[NumPy quickstart](https://numpy.org/doc/stable/user/quickstart.html), and
[pandas time-series guide](https://pandas.pydata.org/docs/user_guide/timeseries.html).
The [pySerial introduction](https://pyserial.readthedocs.io/en/stable/shortintro.html)
matches the serial-port concepts used by the logger.

## 2. Cleaning, resampling, and feature engineering

The raw samples are autocorrelated and much faster than the biological changes
of interest. Median aggregation reduces isolated spikes without pretending that
every two-second sample is an independent experiment. Learn pandas
[`resample`](https://pandas.pydata.org/docs/user_guide/timeseries.html#resampling)
and [`rolling`](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.rolling.html),
then review NIST's
[least-squares regression](https://www.itl.nist.gov/div898/handbook/pmd/section1/pmd141.htm).
The rolling slope is simply the fitted coefficient of time over a moving
window; acceleration is a slope of those slopes.

The biological-age feature uses the explicit engineering assumption

```text
Q10 factor = 2 ** ((temperature_C - 4) / 10)
biological hours += Q10 factor * elapsed_clock_hours
```

Q10 describes how a deterioration rate changes for a 10 degrees C temperature
change. It is a model assumption, not a sensor measurement and not proof of
shelf life. A useful food-cold-chain introduction is the
[FAO discussion of Q10](https://openknowledge.fao.org/3/i8017en/I8017EN.pdf).

Practice:

1. Create a noisy synthetic signal with a few spikes and compare one-minute
   means with medians.
2. Implement a rolling five-point slope by hand, then compare it with the
   project output.
3. Calculate biological age for constant 4, 14, and 24 degrees C data and
   explain why the factors are 1, 2, and 4.

## 3. Controls, robust scale, and drift correction

An empty control measures environmental and instrument behavior when chicken is
absent. The code pools controls to estimate smooth expected drift. It then uses
leave-one-control-out residuals: fit the correction without one control, apply
it to that held-out control, and measure the remaining null variation. This
tests the complete correction process instead of only the baseline noise.

The residual scale uses median absolute deviation (MAD), a robust alternative
to standard deviation. Read the
[SciPy MAD definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.median_abs_deviation.html)
and NIST's
[LOESS overview](https://www.itl.nist.gov/div898/handbook/pmd/section1/pmd144.htm)
for the reasoning behind robust scale and smooth drift estimation. The project
uses its own deterministic smoothing implementation, so focus on the ideas
rather than expecting identical library calls.

The block bootstrap resamples consecutive blocks instead of individual rows so
short-range time dependence is retained. The original reference is Kunsch,
[The Jackknife and the Bootstrap for General Stationary Observations](https://doi.org/10.1214/aos/1176347265).

Practice:

1. Implement `MAD = 1.4826 * median(abs(x - median(x)))` and test it after
   adding one extreme outlier.
2. Hold out each of three synthetic controls, fit drift on the other two, and
   plot the held-out residuals.
3. Compare an ordinary row bootstrap with a block bootstrap on a slowly varying
   signal.

## 4. CUSUM and the primary event rule

CUSUM accumulates small deviations that persist in one direction. For a
standardized response `z`, the one-sided update is conceptually

```text
C_t = max(0, C_(t-1) + z_t - k)
signal when C_t > h
```

`k` ignores small movement and `h` controls how much accumulated evidence is
required. Study NIST's
[CUSUM control-chart explanation](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)
and [average run length](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc3131.htm).
This project chooses `h` using only empty controls and then freezes it before
confirmation runs. Its primary event is `(NH3 or H2S) AND BME688`; CH4 is
supporting evidence. This is evidence agreement, not proof that the channels
are independent.

Practice: implement the recurrence above in ten lines, feed it zero-mean noise,
then add a small sustained shift. Compare how detection changes for different
`k` and `h` values.

## 5. PCA, Isolation Forest, and the change index

PCA rotates correlated standardized channels into orthogonal directions that
capture decreasing amounts of variance. It is a visualization and compression
tool, not a spoilage detector. Read the scikit-learn
[PCA documentation](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html).
Always inspect component loadings and compare control and chicken trajectories;
otherwise PC1 may simply describe drift or elapsed time.

Isolation Forest isolates unusual observations through random feature splits;
points requiring fewer splits are more anomalous. Start with the
[original paper](https://doi.org/10.1109/ICDM.2008.17), then read the
[scikit-learn implementation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).
The model is fitted to corrected control-null data, so its question is
"unusual relative to empty controls?" rather than "spoiled?".

The 0-100 change index is a transparent engineered metric: each directed,
control-corrected z-score is clipped to 0-1 using the frozen `full_scale_z`,
then the channels are combined with the one weight set in
`experiment_config.json`. Those weights are a documented protein-food
heuristic, not learned coefficients. They affect the index but not the primary
CUSUM agreement event. AUC is integrated only over the fixed 0-4 hour window
and is invalidated when coverage rules fail. This keeps it comparable across
complete sessions, but the index remains a prototype effect-size scale rather
than a probability or percentage spoiled.

Practice:

1. Fit PCA to two correlated synthetic sensors and reproduce the transformed
   coordinates from the component matrix.
2. Fit Isolation Forest to a cloud of normal points plus five distant points;
   inspect scores rather than only binary labels.
3. Recalculate one row of the project change index by hand from its four
   corrected z-scores and the JSON weights.

## 6. Camera theory

The camera pipeline uses fixed regions of interest and interpretable features,
not a CNN. With only a few sessions, a CNN would mostly learn lighting,
container position, and condensation. Begin with the
[Pillow tutorial](https://pillow.readthedocs.io/en/stable/handbook/tutorial.html)
for loading, cropping, and transforming images. For edges and the blur gate,
read OpenCV's explanation of
[image gradients and the Laplacian](https://docs.opencv.org/master/d5/d0f/tutorial_py_gradients.html).

Laplacian variance falls when sharp edges disappear. The code requires both the
chicken ROI and a stationary background ROI to become blurry before treating a
frame as likely fogged. Rejected frames cannot build a persistent anomaly, and
reliability is reported over time so late-session condensation is visible.

Practice:

1. Crop the same ROI from a sharp image and a blurred copy; calculate
   Laplacian variance for both.
2. Change image brightness without changing the object and observe which color
   and histogram features move.
3. Cover only the chicken ROI, then blur the whole image, and verify why the
   background ROI distinguishes occlusion/change from global fogging.

## 7. Experimental validity and ground truth

The most important modeling rule is to keep confirmation sessions and sites
untouched while choosing directions, thresholds, weights, and scales. Read scikit-learn's
[data-leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)
and the OSF
[registration guide](https://help.osf.io/article/330-welcome-to-registrations)
to understand why the pilot is excluded and the configuration is frozen.

The exact sensor directions and limitations must come from the manufacturers'
datasheets and independent response checks. For the BME688, use Bosch's
[product documentation and datasheet](https://www.bosch-sensortec.com/en/products/environmental-sensors/gas-sensors/bme688/).
Do not improvise concentrated toxic-gas sources.

Visible observations are useful supporting annotations, but defensible
spoilage ground truth needs independent measurements. The FDA's
[Bacteriological Analytical Manual](https://www.fda.gov/food/laboratory-methods-food/bacteriological-analytical-manual-bam)
and [Aerobic Plate Count chapter](https://www.fda.gov/food/laboratory-methods-food/bam-chapter-3-aerobic-plate-count)
show what a microbiological reference method looks like. Until those data
exist, report detection latency, control-adjusted index, fixed-window AUC,
sensor agreement, camera reliability, and repeatability across independent
sessions—not accuracy, sensitivity, specificity, freshness probability, or
remaining shelf life.

## 8. Cross-house generalization

The portable design separates local calibration from global logic. Each
site/device/container estimates its own baseline, drift, and residual noise;
the sensor directions, CUSUM rule, persistence, index weights, and scale remain
globally frozen. Never average raw voltages across houses. Compare standardized
session-level metrics instead.

If two houses influence model choices, both are development sites. Test the
frozen procedure at an untouched third house to evaluate external transfer.
Later, use leave-one-house-out validation: develop on every site except one and
evaluate the complete calibration-and-detection procedure at the held-out site.

## 9. Accelerated two-week study plan

- Days 1–2: Python, NumPy, pandas, and serial logging; trace one row from serial
  input to `sensor_log.csv`.
- Days 3–4: resampling, baselines, deltas, rolling statistics, MAD, and Q10;
  reproduce one feature column in a scratch script.
- Days 5–6: implement CUSUM from scratch and understand the primary agreement
  rule.
- Days 7–8: PCA and Isolation Forest on synthetic data, then empty controls.
- Days 9–10: image ROIs, color features, Laplacian variance, condensation, and
  anomaly persistence.
- Days 11–12: run a short practice session through every command and inspect
  each output.
- Days 13–14: explain the design, assumptions, failure modes, and claims
  without relying on the code.

This is roughly 25–35 focused hours. You are not expected to reproduce every
file from memory; you should be able to explain the major decisions, follow one
reading through the pipeline, run it, interpret it, and make small documented
changes.

For every algorithm, use the same loop: derive the smallest formula, implement
it on synthetic data, plot failure cases, then read the corresponding project
function. That will teach you more than trying to understand the entire
pipeline in one pass.

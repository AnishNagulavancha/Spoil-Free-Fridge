import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analyze_session import (
    AnalysisConfig,
    NUMERIC_COLUMNS,
    _rolling_slope,
    analyze,
    build_features,
    load_and_clean,
)


def _sensor_row(timestamp: str, phase: str, elapsed_s: object, **overrides) -> dict:
    row = {
        "timestamp_iso": timestamp,
        "phase": phase,
        "elapsed_s": elapsed_s,
        "adc_NH3": 1000,
        "v_NH3": 1.0,
        "adc_CH4": 1100,
        "v_CH4": 1.2,
        "adc_H2S": 1200,
        "v_H2S": 0.8,
        "temp_C": 4.0,
        "pressure_Pa": 101325.0,
        "humidity_pct": 50.0,
        "bme_gas_ohms": 100000.0,
    }
    row.update(overrides)
    return row


def _feature_input(minutes: int = 40) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=minutes + 1, freq="1min")
    elapsed = np.arange(minutes + 1, dtype=float) * 60
    after_baseline = elapsed > 30 * 60
    return pd.DataFrame(
        {
            "elapsed_s": elapsed,
            "v_NH3": np.where(after_baseline, 1.2, 1.0),
            "v_H2S": np.where(after_baseline, 1.0, 0.8),
            "v_CH4": np.where(after_baseline, 1.3, 1.2),
            "temp_C": np.full(minutes + 1, 4.0),
            "pressure_Pa": np.full(minutes + 1, 101325.0),
            "humidity_pct": np.full(minutes + 1, 50.0),
            "bme_gas_ohms": np.where(after_baseline, 80000.0, 100000.0),
        },
        index=index,
    ).rename_axis("timestamp")


def test_load_and_clean_discards_warmup_corruption_and_duplicates(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    rows = [
        _sensor_row("2026-01-01T00:00:00", "warmup", 0),
        _sensor_row("2026-01-01T00:01:00", "logging", 0),
        _sensor_row("2026-01-01T00:01:00", "logging", 0),
        _sensor_row(
            "2026-01-01T00:02:00",
            "logging",
            60,
            bme_gas_ohms="corrupt",
        ),
    ]
    pd.DataFrame(rows).to_csv(session / "sensor_log.csv", index=False)
    (session / "metadata.json").write_text(
        json.dumps({"session_id": "S-test"}), encoding="utf-8"
    )

    clean, metadata, report = load_and_clean(session)

    assert metadata["session_id"] == "S-test"
    assert clean.index.name == "timestamp"
    assert len(clean) == 1
    assert report == {
        "rows_read": 4,
        "warmup_rows_discarded": 1,
        "corrupt_or_invalid_rows_discarded": 1,
        "exact_duplicate_rows_discarded": 1,
        "rows_kept": 1,
    }


def test_load_and_clean_preserves_buffered_measurements_with_same_host_time(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    rows = [
        _sensor_row("2026-01-01T00:01:00", "logging", 0, bme_gas_ohms=100000),
        _sensor_row("2026-01-01T00:01:00", "logging", 0, bme_gas_ohms=101000),
    ]
    pd.DataFrame(rows).to_csv(session / "sensor_log.csv", index=False)
    (session / "metadata.json").write_text(
        json.dumps({"session_id": "S-buffered"}), encoding="utf-8"
    )

    clean, _, report = load_and_clean(session)

    assert len(clean) == 2
    assert report["corrupt_or_invalid_rows_discarded"] == 0
    assert report["exact_duplicate_rows_discarded"] == 0


def test_load_and_clean_requires_all_logger_columns(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    pd.DataFrame(
        [{"timestamp_iso": "2026-01-01", "phase": "logging"}]
    ).to_csv(session / "sensor_log.csv", index=False)
    (session / "metadata.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="missing columns"):
        load_and_clean(session)


def test_build_features_computes_deltas_trends_and_q10_age():
    features, summary = build_features(
        _feature_input(),
        AnalysisConfig(
            baseline_minutes=30,
            feature_resample_seconds=60,
            slope_windows_minutes=(5,),
            min_window_points=3,
        ),
    )

    assert summary["baseline_rows"] == 31
    assert summary["baseline_means"]["v_NH3"] == pytest.approx(1.0)
    assert features["v_NH3_delta_pct"].iloc[-1] == pytest.approx(0.2)
    assert features["bme_delta_log_inverted"].iloc[-1] == pytest.approx(
        np.log(1.25)
    )
    assert features["q10_factor"].eq(1.0).all()
    assert features["biological_age_h"].iloc[-1] == pytest.approx(40 / 60)
    assert bool(features["is_baseline"].iloc[-1]) is False
    assert np.isfinite(features["v_NH3_slope_5m"].iloc[-1])


def test_build_features_rejects_a_session_shorter_than_baseline():
    with pytest.raises(ValueError, match="80%"):
        build_features(
            _feature_input(minutes=10),
            AnalysisConfig(
                baseline_minutes=30,
                feature_resample_seconds=60,
                min_window_points=3,
            ),
        )


def test_rolling_slope_is_expressed_per_hour():
    elapsed_s = np.arange(7, dtype=float) * 60
    values = 2.0 * elapsed_s / 3600.0 + 5.0

    slopes = _rolling_slope(elapsed_s, values, window_minutes=5, min_points=3)

    assert slopes[-1] == pytest.approx(2.0)


def test_analyze_writes_features_and_summary(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    frame = _feature_input()
    raw = pd.DataFrame(
        [
            _sensor_row(
                timestamp.isoformat(),
                "logging",
                values["elapsed_s"],
                **{
                    column: values[column]
                    for column in (
                        "v_NH3",
                        "v_CH4",
                        "v_H2S",
                        "temp_C",
                        "pressure_Pa",
                        "humidity_pct",
                        "bme_gas_ohms",
                    )
                },
            )
            for timestamp, values in frame.iterrows()
        ]
    )
    assert set(NUMERIC_COLUMNS).issubset(raw.columns)
    raw.to_csv(session / "sensor_log.csv", index=False)
    (session / "metadata.json").write_text(
        json.dumps(
            {
                "session_id": "S-end-to-end",
                "protocol_version": "test-v1",
                "session_role": "pilot",
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"

    analyze(
        session,
        output,
        AnalysisConfig(
            expected_protocol_version="test-v1",
            baseline_minutes=30,
            feature_resample_seconds=60,
            slope_windows_minutes=(5,),
            min_window_points=3,
        ),
    )

    assert (output / "features.csv").is_file()
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["session_id"] == "S-end-to-end"
    assert summary["cleaning"]["rows_kept"] == 41
    assert summary["status"] == "prototype_features_only_not_a_food_safety_assessment"

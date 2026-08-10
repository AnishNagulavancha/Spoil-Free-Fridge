import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from camera_models import camera_feature_columns, fit_camera_unsupervised
from image_data import load_image_log
from image_features import extract_image_features


def _save_pattern(path: Path, offset: int = 0) -> None:
    y, x = np.indices((32, 32))
    checker = (((x // 4 + y // 4) % 2) * 180 + 30 + offset).clip(0, 255)
    rgb = np.stack(
        [checker, np.roll(checker, 1, axis=0), np.roll(checker, 1, axis=1)],
        axis=2,
    ).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(path)


def test_extract_image_features_uses_first_image_as_reference(tmp_path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    _save_pattern(first)
    _save_pattern(second, offset=20)

    features = extract_image_features([first, second])

    assert len(features) == 2
    assert features["baseline_mae"].iloc[0] == pytest.approx(0.0)
    assert features["previous_mae"].iloc[0] == pytest.approx(0.0)
    assert features["baseline_mae"].iloc[1] > 0
    assert np.isfinite(features.to_numpy()).all()


def test_extract_image_features_opens_each_image_once(tmp_path, monkeypatch):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    _save_pattern(first)
    _save_pattern(second, offset=20)
    original_open = Image.open
    opened = []

    def counted_open(*args, **kwargs):
        opened.append(args[0])
        return original_open(*args, **kwargs)

    monkeypatch.setattr("image_features.Image.open", counted_open)

    extract_image_features([first, second])

    assert opened == [first, second]


def test_extract_image_features_rejects_invalid_roi(tmp_path):
    image = tmp_path / "image.jpg"
    _save_pattern(image)

    with pytest.raises(ValueError, match="ROI values"):
        extract_image_features([image], roi=(0.8, 0.1, 0.2, 0.9))


def test_load_image_log_excludes_empty_reference_and_failed_images(tmp_path):
    session = tmp_path / "session"
    images = session / "images"
    images.mkdir(parents=True)
    for name in ("empty.jpg", "food0.jpg", "food30.jpg"):
        _save_pattern(images / name)
    pd.DataFrame(
        {
            "timestamp_iso": [
                "2026-01-01T00:00:00",
                "2026-01-01T00:30:00",
                "2026-01-01T01:00:00",
                "2026-01-01T01:30:00",
            ],
            "image_filename": [
                "empty.jpg",
                "food0.jpg",
                "food30.jpg",
                "missing.jpg",
            ],
            "status": ["success", "success", "success", "failed"],
        }
    ).to_csv(session / "image_log.csv", index=False)
    (session / "metadata.json").write_text(
        json.dumps(
            {
                "session_id": "S-camera",
                "food_inserted_time": "2026-01-01T00:30:00",
                "food_baseline_minutes": 30,
            }
        ),
        encoding="utf-8",
    )

    result = load_image_log(session)

    assert result["image_filename"].tolist() == ["food0.jpg", "food30.jpg"]
    assert result["minutes_since_insertion"].tolist() == [0.0, 30.0]
    assert result["is_image_baseline"].tolist() == [True, True]
    assert set(result["session_id"]) == {"S-camera"}


def test_camera_feature_columns_exclude_identifiers_and_time():
    frame = pd.DataFrame(
        {
            "elapsed_s": [0],
            "image_number": [1],
            "minutes_since_insertion": [0],
            "rgb_mean_r": [0.5],
            "laplacian_ratio": [1.0],
        }
    )

    assert camera_feature_columns(frame) == ["rgb_mean_r", "laplacian_ratio"]


def test_camera_model_rejects_fogged_frames(tmp_path):
    frame = pd.DataFrame(
        {
            "is_image_baseline": [True, True, True, False, False, False],
            "minutes_since_insertion": [0, 10, 20, 30, 40, 50],
            "rgb_mean_r": [0.50, 0.51, 0.49, 0.8, 0.9, 0.9],
            "edge_strength": [0.2, 0.21, 0.19, 0.3, 0.05, 0.05],
            "laplacian_ratio": [1.0, 1.1, 0.9, 1.0, 0.2, 0.2],
            "background_laplacian_ratio": [1.0, 1.0, 0.9, 1.0, 0.2, 0.2],
        }
    )
    config = {
        "camera": {
            "persistence_frames": 2,
            "laplacian_ratio_minimum": 0.5,
            "background_laplacian_ratio_minimum": 0.5,
        }
    }

    artifacts, output = fit_camera_unsupervised(frame, config, random_state=1)

    assert artifacts["features"]
    assert output["fog_suspected"].iloc[-2:].all()
    assert not output["camera_reliable"].iloc[-2:].any()
    assert not output["camera_is_anomaly"].iloc[-2:].any()
    assert not output["camera_sustained_change"].iloc[-2:].any()


def test_camera_model_requires_three_baseline_images():
    frame = pd.DataFrame(
        {
            "is_image_baseline": [True, True, False],
            "rgb_mean_r": [0.5, 0.5, 0.6],
            "laplacian_ratio": [1.0, 1.0, 1.0],
            "background_laplacian_ratio": [1.0, 1.0, 1.0],
        }
    )
    config = {
        "camera": {
            "persistence_frames": 2,
            "laplacian_ratio_minimum": 0.5,
            "background_laplacian_ratio_minimum": 0.5,
        }
    }

    with pytest.raises(ValueError, match="at least three"):
        fit_camera_unsupervised(frame, config)

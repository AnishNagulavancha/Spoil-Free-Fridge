"""Interpretable color, texture, and baseline-difference image features."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from PIL import Image


ROI = tuple[float, float, float, float]


def _crop_array(image: Image.Image, roi: ROI | None, size: int = 224) -> np.ndarray:
    if roi is not None:
        x1, y1, x2, y2 = roi
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("ROI values must be normalized and ordered within 0..1")
        width, height = image.size
        image = image.crop((round(x1 * width), round(y1 * height),
                            round(x2 * width), round(y2 * height)))
    image = image.resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(image, dtype=np.float32) / 255.0


def _load_rgb(path: Path, roi: ROI | None, size: int = 224) -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert("RGB")
        return _crop_array(image, roi, size)


def _laplacian_variance(gray: np.ndarray) -> float:
    center = gray[1:-1, 1:-1]
    laplacian = (
        gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * center
    )
    return float(laplacian.var())


def _entropy(gray: np.ndarray) -> float:
    counts, _ = np.histogram(gray, bins=64, range=(0, 1))
    probability = counts[counts > 0] / counts.sum()
    return float(-(probability * np.log2(probability)).sum())


def _histogram(array: np.ndarray) -> np.ndarray:
    parts = [np.histogram(array[..., channel], bins=32, range=(0, 1), density=True)[0]
             for channel in range(3)]
    result = np.concatenate(parts).astype(float)
    return result / max(result.sum(), 1e-12)


def extract_image_features(paths: Iterable[Path], roi: ROI | None = None,
                           background_roi: ROI | None = None) -> pd.DataFrame:
    arrays = [_load_rgb(Path(path), roi) for path in paths]
    quality_arrays = [_load_rgb(Path(path), background_roi) for path in paths]
    if not arrays:
        raise ValueError("At least one image is required")
    reference = arrays[0]
    reference_gray = reference.mean(axis=2)
    reference_hist = _histogram(reference)
    rows = []
    previous = reference
    reference_quality_gray = quality_arrays[0].mean(axis=2)
    reference_laplacian = max(_laplacian_variance(reference_gray), 1e-12)
    reference_background_laplacian = max(
        _laplacian_variance(reference_quality_gray), 1e-12
    )
    for image, quality_image in zip(arrays, quality_arrays):
        gray = image.mean(axis=2)
        quality_gray = quality_image.mean(axis=2)
        hsv = np.asarray(Image.fromarray((image * 255).astype(np.uint8), "RGB").convert("HSV"),
                         dtype=np.float32) / 255.0
        gradient_y, gradient_x = np.gradient(gray)
        baseline_difference = image - reference
        previous_difference = image - previous
        histogram_distance = np.abs(_histogram(image) - reference_hist).sum() / 2
        correlation = np.corrcoef(reference_gray.ravel(), gray.ravel())[0, 1]
        row = {
            **{f"rgb_mean_{name}": float(image[..., i].mean())
               for i, name in enumerate(("r", "g", "b"))},
            **{f"rgb_std_{name}": float(image[..., i].std())
               for i, name in enumerate(("r", "g", "b"))},
            **{f"hsv_mean_{name}": float(hsv[..., i].mean())
               for i, name in enumerate(("h", "s", "v"))},
            "gray_entropy": _entropy(gray),
            "edge_strength": float(np.hypot(gradient_x, gradient_y).mean()),
            "sharpness": float(gray.var()),
            "laplacian_variance": _laplacian_variance(gray),
            "laplacian_ratio": _laplacian_variance(gray) / reference_laplacian,
            "background_laplacian_variance": _laplacian_variance(quality_gray),
            "background_laplacian_ratio": (
                _laplacian_variance(quality_gray) / reference_background_laplacian
            ),
            "background_contrast_ratio": float(
                quality_gray.std() / max(reference_quality_gray.std(), 1e-12)
            ),
            "baseline_mae": float(np.abs(baseline_difference).mean()),
            "baseline_rmse": float(np.sqrt(np.square(baseline_difference).mean())),
            "baseline_hist_distance": float(histogram_distance),
            "baseline_correlation": float(np.nan_to_num(correlation, nan=0.0)),
            "previous_mae": float(np.abs(previous_difference).mean()),
        }
        rows.append(row)
        previous = image
    return pd.DataFrame(rows)

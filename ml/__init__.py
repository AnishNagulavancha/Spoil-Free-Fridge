"""
FoodSense ML pipeline: feature extraction, training, and spoilage risk inference.
"""

from pathlib import Path

__all__ = [
    "build_features",
    "train_models",
    "run_inference",
]

# Lazy imports in pipeline functions to keep CLI fast
def build_features(raw_dir=None, processed_dir=None, **kwargs):
    from .features import build_features as _build
    return _build(raw_dir=raw_dir, processed_dir=processed_dir, **kwargs)

def train_models(processed_dir=None, model_dir=None, **kwargs):
    from .train import train_models as _train
    return _train(processed_dir=processed_dir, model_dir=model_dir, **kwargs)

def run_inference(model_dir=None, data=None, **kwargs):
    from .predict import run_inference as _predict
    return _predict(model_dir=model_dir, data=data, **kwargs)

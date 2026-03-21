"""
FoodSense / Spoil-Free Fridge — ML pipeline config and data schema.
Matches firmware output and Data LoggingScript.py CSV format.
"""

from pathlib import Path

# CSV columns produced by Data LoggingScript.py (fridge1.0.ino stream)
RAW_COLUMNS = [
    "Timestamp",
    "NH3_raw", "NH3_V",
    "CH4_raw", "CH4_V",
    "H2S_raw", "H2S_V",
    "Temp_C", "Pressure_Pa", "Humidity_pct", "GasRes",
    "Label",
]

# Numeric sensor columns (exclude Timestamp, Label)
SENSOR_COLUMNS = [
    "NH3_raw", "NH3_V", "CH4_raw", "CH4_V", "H2S_raw", "H2S_V",
    "Temp_C", "Pressure_Pa", "Humidity_pct", "GasRes",
]

# Binary spoilage: map labels to 0 (fresh) / 1 (spoiled or spoiling)
LABEL_TO_BINARY = {
    "Fresh": 0,
    "fresh": 0,
    "Warmup": 0,  # optional: exclude warmup from training
    "Spoiled": 1,
    "spoiled": 1,
    "Spoiling": 1,
    "spoiling": 1,
}

# Multi-class (for future: food type + freshness)
SPOILAGE_CLASSES = ["Fresh", "Spoiling", "Spoiled"]

# Paths (override via env or CLI)
DEFAULT_RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "models"

# Feature engineering
ROLLING_WINDOWS = [5, 15, 30]  # number of samples for rolling stats (e.g. 5/15/30 sec at 1 Hz)

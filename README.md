# Spoil-Free-Fridge
This project is a battery-powered, sensor-based system designed to detect early signs of food spoilage in refrigerators by monitoring the release of specific gases. It uses dedicated gas sensors (specifically, hydrogen sulfide, ammonia, and methane) along with an environmental sensor (BME688) to track changes in air composition over time.

The collected data is transmitted to a PC over Wi-Fi using an ESP32-WROOM microcontroller. A machine learning model, trained on labeled gas profiles of different food states, will follow a multi-classification approach by being able to recongize food type, food item, and finally the freshness level as fresh, spoiling, or spoiled.

The system is optimized for low power consumption, designed to operate off batteries, and intended for eventual deployment inside consumer refrigerators as a compact, standalone freshness detection unit.

Currently, the prototype of the system has been built on a breadboard. Initially, we will see if the prototype is accurate enough to work in normal conditions before moving to a fridge

The inspiration of this projetc came out my own laziness of postponing when I would cook my own meals leading to food spoiling in the fridge.

---

## ML pipeline (FoodSense)

Machine learning pipeline for spoilage risk from multi-source sensor time series (NH3, CH4, H2S, BME688 env + gas resistance).

### Setup

```bash
pip install -r requirements.txt
```

### Data collection (rice / whole-foods trials)

1. **Fresh run:** Place sample (e.g. cooked rice in closed container), run logger with label `Fresh`:
   ```bash
   python "Data LoggingScript.py" Fresh
   ```
   Or set `FRESHNESS_LABEL=Spoiled` (or `Spoiling`) for a spoiled sample run.
2. Save CSVs into `data/raw/` (or set `SENSOR_LOG_DIR` to that path). You need both Fresh and Spoiled (and optionally Spoiling) logs to train.

### Pipeline commands

| Step | Command | Description |
|------|---------|-------------|
| Features | `python run_pipeline.py features` | Load CSVs from `data/raw/`, clean, add rolling features, normalize, split train/val/test → `data/processed/` |
| Train | `python run_pipeline.py train` | Train Random Forest, MLP, Logistic Regression; save models and metrics to `models/` |
| Predict | `python run_pipeline.py predict --data path/to.csv` | Spoilage probability and class for deployment/alerting |
| All | `python run_pipeline.py all` | Run features then train |

Models and scaler are saved under `models/`; the pipeline picks the best model by validation F1 (spoiled class) for inference.

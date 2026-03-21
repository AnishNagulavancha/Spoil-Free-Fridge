"""
Log sensor data from ESP32 (fridge1.0.ino) to CSV for ML pipeline.
Configure COM port, save folder, and label for each run (e.g. Fresh vs Spoiled for rice trials).
"""

import csv
import os
import sys
import time

# -------- Config (edit or set env vars) --------
COM_PORT = os.environ.get("COM_PORT", "COM3")          # macOS/Linux: e.g. "/dev/cu.usbserial-*"
BAUD_RATE = 9600
PREHEAT_MINUTES = 30
LOG_MINUTES = 60
# Label for this run: "Fresh", "Spoiled", "Spoiling", etc. (used in ML as target)
FRESHNESS_LABEL = os.environ.get("FRESHNESS_LABEL", "Fresh")

# Where to save CSVs (used by ML pipeline if you point data/raw here or copy logs)
SAVE_FOLDER = os.environ.get("SENSOR_LOG_DIR", r"C:\Users\anish\Documents\SensorLogs")

# Optional: pass label and/or port from command line
#   python "Data LoggingScript.py" Spoiled
#   python "Data LoggingScript.py" Fresh COM5
if len(sys.argv) >= 2:
    FRESHNESS_LABEL = sys.argv[1]
if len(sys.argv) >= 3:
    COM_PORT = sys.argv[2]


def main():
    os.makedirs(SAVE_FOLDER, exist_ok=True)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(SAVE_FOLDER, f"sensor_log_{timestamp_str}.csv")

    try:
        import serial
    except ImportError:
        print("Install pyserial: pip install pyserial")
        sys.exit(1)

    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", "NH3_raw", "NH3_V", "CH4_raw", "CH4_V", "H2S_raw", "H2S_V",
            "Temp_C", "Pressure_Pa", "Humidity_pct", "GasRes", "Label",
        ])
        print(f"Saving to: {csv_path}")
        print(f"Label for this run: {FRESHNESS_LABEL}")
        print(f"Preheating {PREHEAT_MINUTES} min...")
        start_time = time.time()

        # PREHEAT
        while time.time() - start_time < PREHEAT_MINUTES * 60:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line and line.count(",") >= 7:
                row = line.split(",")
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                writer.writerow([timestamp] + row + ["Warmup"])
                print("[WARMUP] " + line)

        print("Logging started...")
        log_start = time.time()

        # LOGGING
        while time.time() - log_start < LOG_MINUTES * 60:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line and line.count(",") >= 7:
                row = line.split(",")
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                writer.writerow([timestamp] + row + [FRESHNESS_LABEL])
                print(line)

    print(f"Done. Data saved to {csv_path}")
    ser.close()


if __name__ == "__main__":
    main()

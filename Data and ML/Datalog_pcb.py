import serial
import time
import csv
import json
from pathlib import Path
from datetime import datetime

# ================= USER SETTINGS =================
COM_PORT = "COM4"          # Change this to your ESP32 port
BAUD_RATE = 115200         # Must match Serial.begin(115200)

SAVE_ROOT = Path(r"C:\Users\anish\Documents\GitHub\Spoil-Free-Fridge\Data logs\pcb_data")

SESSION_ID = "S0001"
CONTAINER_ID = "board_A"

FOOD_CATEGORY = "unknown"  # protein, fruit, bread, leftovers, etc.
FOOD_NAME = "unknown"      # chicken, rice, apple, etc.
LABEL = "Unlabeled"        # Fresh, Warmup, Test, etc.

PREHEAT_MINUTES = 30       # logged as Warmup
LOG_MINUTES = None         # None = log until Ctrl+C

EXPECTED_FIELDS = 10
# Expected ESP32 CSV:
# adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms

# ================= SESSION SETUP =================
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
session_name = f"{SESSION_ID}_{FOOD_NAME}_{timestamp_str}"

session_dir = SAVE_ROOT / session_name
images_dir = session_dir / "images"
session_dir.mkdir(parents=True, exist_ok=True)
images_dir.mkdir(parents=True, exist_ok=True)

csv_path = session_dir / "sensor_log.csv"
metadata_path = session_dir / "metadata.json"

metadata = {
    "session_id": SESSION_ID,
    "container_id": CONTAINER_ID,
    "food_category": FOOD_CATEGORY,
    "food_name": FOOD_NAME,
    "label": LABEL,
    "preheat_minutes": PREHEAT_MINUTES,
    "log_minutes": LOG_MINUTES,
    "baud_rate": BAUD_RATE,
    "com_port": COM_PORT,
    "start_time": datetime.now().isoformat(),
    "notes": "Prototype 1 laptop sensor logging. Camera image sync not enabled yet."
}

with open(metadata_path, "w") as f:
    json.dump(metadata, f, indent=4)

print(f"Session folder: {session_dir}")
print(f"CSV file: {csv_path}")
print(f"Metadata file: {metadata_path}")

# ================= SERIAL SETUP =================
ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
time.sleep(2)

start_time = time.time()

def parse_sensor_line(line):
    parts = line.split(",")

    if len(parts) != EXPECTED_FIELDS:
        return None

    try:
        values = [float(x) for x in parts]
        return values
    except ValueError:
        return None

# ================= LOGGING =================
try:
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "timestamp_iso",
            "elapsed_s",
            "session_id",
            "food_category",
            "food_name",
            "phase",
            "adc_NH3",
            "v_NH3",
            "adc_CH4",
            "v_CH4",
            "adc_H2S",
            "v_H2S",
            "temp_C",
            "pressure_Pa",
            "humidity_pct",
            "bme_gas_ohms",
            "image_filename"
        ])

        print("\nLogging started. Press Ctrl+C to stop.\n")

        while True:
            elapsed_s = time.time() - start_time

            if elapsed_s < PREHEAT_MINUTES * 60:
                phase = "Warmup"
            else:
                phase = LABEL

            if LOG_MINUTES is not None:
                if elapsed_s > (PREHEAT_MINUTES + LOG_MINUTES) * 60:
                    break

            raw_line = ser.readline().decode("utf-8", errors="ignore").strip()

            if not raw_line:
                continue

            values = parse_sensor_line(raw_line)

            if values is None:
                print(f"[SKIP] {raw_line}")
                continue

            [
                adc_NH3,
                v_NH3,
                adc_CH4,
                v_CH4,
                adc_H2S,
                v_H2S,
                temp_C,
                pressure_Pa,
                humidity_pct,
                bme_gas_ohms
            ] = values

            timestamp_iso = datetime.now().isoformat(timespec="seconds")
            image_filename = "none"

            writer.writerow([
                timestamp_iso,
                round(elapsed_s, 2),
                SESSION_ID,
                FOOD_CATEGORY,
                FOOD_NAME,
                phase,
                int(adc_NH3),
                v_NH3,
                int(adc_CH4),
                v_CH4,
                int(adc_H2S),
                v_H2S,
                temp_C,
                pressure_Pa,
                humidity_pct,
                bme_gas_ohms,
                image_filename
            ])

            f.flush()

            print(
                f"[{phase}] "
                f"t={elapsed_s:.1f}s, "
                f"NH3={v_NH3:.3f}V, "
                f"CH4={v_CH4:.3f}V, "
                f"H2S={v_H2S:.3f}V, "
                f"T={temp_C:.2f}C, "
                f"RH={humidity_pct:.2f}%"
            )

except KeyboardInterrupt:
    print("\nLogging stopped by user.")

finally:
    ser.close()
    print(f"Data saved to: {csv_path}")
import serial
import time
import csv
import json
import requests
from pathlib import Path
from datetime import datetime

# ============================================================
# COMBINED ESP32 DATA LOGGER
# Same ESP32 does:
#   1. Sensor CSV over USB Serial
#   2. Camera capture over Wi-Fi /capture
#   3. LEDs ON/OFF inside Arduino capture handler
# ============================================================

# ================= USER SETTINGS =================
COM_PORT = "COM4"
BAUD_RATE = 115200

SAVE_ROOT = Path(
    r"C:\Users\anish\Documents\GitHub\Spoil-Free-Fridge\Data logs\pcb_data"
)

SESSION_ID = "S0001"
CONTAINER_ID = "board_A"

FOOD_CATEGORY = "unknown"
FOOD_NAME = "unknown"
LABEL = "Unlabeled"

PREHEAT_MINUTES = 30
FOOD_BASELINE_MINUTES = 30
LOG_MINUTES = 300          # None = run until Ctrl+C

EXPECTED_FIELDS = 10

# Expected ESP32 CSV:
# adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms

# ================= CAMERA SETTINGS =================
CAMERA_ENABLED = True

# Use the IP printed by the combined ESP32 Serial Monitor
CAMERA_CAPTURE_URL = "http://192.168.1.102/capture"

# After chicken insertion, capture every 5 minutes.
IMAGE_INTERVAL_SEC = 300

# Empty-chamber reference image. Opening Serial resets the ESP32, so allow the
# camera time to become available before requesting this first image.
FIRST_IMAGE_DELAY_SEC = 25

CAMERA_TIMEOUT_SEC = 20

# ================= SESSION SETUP =================
timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
session_name = f"{SESSION_ID}_{FOOD_NAME}_{timestamp_str}"

session_dir = SAVE_ROOT / session_name
images_dir = session_dir / "images"

session_dir.mkdir(parents=True, exist_ok=True)
images_dir.mkdir(parents=True, exist_ok=True)

csv_path = session_dir / "sensor_log.csv"
image_log_path = session_dir / "image_log.csv"
metadata_path = session_dir / "metadata.json"

metadata = {
    "session_id": SESSION_ID,
    "container_id": CONTAINER_ID,
    "food_category": FOOD_CATEGORY,
    "food_name": FOOD_NAME,
    "label": LABEL,
    "preheat_minutes": PREHEAT_MINUTES,
    "food_baseline_minutes": FOOD_BASELINE_MINUTES,
    "log_minutes": LOG_MINUTES,
    "baud_rate": BAUD_RATE,
    "com_port": COM_PORT,
    "expected_fields": EXPECTED_FIELDS,
    "camera_enabled": CAMERA_ENABLED,
    "camera_capture_url": CAMERA_CAPTURE_URL,
    "image_interval_sec": IMAGE_INTERVAL_SEC,
    "first_image_delay_sec": FIRST_IMAGE_DELAY_SEC,
    "camera_timeout_sec": CAMERA_TIMEOUT_SEC,
    "start_time": datetime.now().isoformat(),
    "notes": (
        "Combined ESP32 logger. Sensor data over USB serial. "
        "Camera images captured over Wi-Fi /capture. "
        "Arduino handles LED ON -> capture -> LED OFF."
    )
}

with open(metadata_path, "w") as f:
    json.dump(metadata, f, indent=4)

print("================================")
print("DATA LOGGER STARTING")
print("================================")
print(f"Session folder: {session_dir}")
print(f"Sensor CSV:     {csv_path}")
print(f"Image log CSV:  {image_log_path}")
print(f"Metadata file:  {metadata_path}")
print(f"Images folder:  {images_dir}")
print(f"Camera URL:     {CAMERA_CAPTURE_URL}")
print(f"Image interval: {IMAGE_INTERVAL_SEC} sec")
print("================================")


# ================= HELPER FUNCTIONS =================
def parse_sensor_line(line):
    parts = line.split(",")

    if len(parts) != EXPECTED_FIELDS:
        return None

    try:
        values = [float(x) for x in parts]
        return values
    except ValueError:
        return None


def capture_image(image_number, elapsed_s):
    image_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_filename = f"img_{image_number:06d}_{image_timestamp}.jpg"
    image_path = images_dir / image_filename

    try:
        response = requests.get(
            CAMERA_CAPTURE_URL,
            timeout=CAMERA_TIMEOUT_SEC
        )

        content_type = response.headers.get("Content-Type", "")

        if response.status_code == 200 and content_type.startswith("image"):
            with open(image_path, "wb") as img_file:
                img_file.write(response.content)

            print(f"[IMAGE] Saved {image_filename}")

            return {
                "status": "success",
                "filename": image_filename,
                "path": str(image_path),
                "http_status": response.status_code,
                "content_type": content_type,
                "elapsed_s": elapsed_s,
                "timestamp_iso": datetime.now().isoformat(timespec="seconds")
            }

        else:
            print(
                f"[IMAGE ERROR] Bad response: "
                f"status={response.status_code}, content_type={content_type}"
            )

            return {
                "status": "bad_response",
                "filename": "capture_failed",
                "path": "",
                "http_status": response.status_code,
                "content_type": content_type,
                "elapsed_s": elapsed_s,
                "timestamp_iso": datetime.now().isoformat(timespec="seconds")
            }

    except Exception as e:
        print(f"[IMAGE ERROR] {e}")

        return {
            "status": f"error: {e}",
            "filename": "capture_failed",
            "path": "",
            "http_status": "",
            "content_type": "",
            "elapsed_s": elapsed_s,
            "timestamp_iso": datetime.now().isoformat(timespec="seconds")
        }


def capture_and_record(image_writer, image_file, image_number, elapsed_s):
    """Capture one image, append its result to image_log.csv, and flush it."""
    print(f"[IMAGE] Requesting capture #{image_number} at t={elapsed_s:.1f}s")
    result = capture_image(image_number, elapsed_s)
    image_writer.writerow([
        result["timestamp_iso"],
        round(result["elapsed_s"], 2),
        image_number,
        result["filename"],
        result["status"],
        result["http_status"],
        result["content_type"],
        result["path"]
    ])
    image_file.flush()
    return result["filename"]


# ================= SERIAL SETUP =================
print("\nOpening serial port...")

try:
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
except Exception as e:
    print(f"\n[SERIAL ERROR] Could not open {COM_PORT}: {e}")
    print("Check COM port and close Arduino Serial Monitor.")
    raise

# Opening serial usually resets the ESP32
print("Waiting for ESP32 reset/startup...")
time.sleep(5)

try:
    ser.reset_input_buffer()
except Exception:
    pass

start_time = time.time()

next_image_time = None
image_count = 0
pending_image_filename = "none"
empty_reference_captured = False
food_inserted = False
food_inserted_time = None

last_no_data_print = -999

# ================= LOGGING =================
try:
    with open(csv_path, "w", newline="") as sensor_file, open(image_log_path, "w", newline="") as image_file:
        sensor_writer = csv.writer(sensor_file)
        image_writer = csv.writer(image_file)

        sensor_writer.writerow([
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

        image_writer.writerow([
            "timestamp_iso",
            "elapsed_s",
            "image_number",
            "image_filename",
            "status",
            "http_status",
            "content_type",
            "image_path"
        ])

        sensor_file.flush()
        image_file.flush()

        print("\nLogging started. Press Ctrl+C to stop.\n")

        while True:
            elapsed_s = time.time() - start_time

            if not food_inserted:
                phase = "Warmup"
            else:
                logging_elapsed_s = time.time() - food_inserted_time
                if logging_elapsed_s < FOOD_BASELINE_MINUTES * 60:
                    phase = "Baseline"
                else:
                    phase = LABEL

            if food_inserted and LOG_MINUTES is not None:
                if logging_elapsed_s > LOG_MINUTES * 60:
                    print("Reached scheduled logging duration.")
                    break

            # ================= CAMERA CAPTURE =================
            # Take one empty reference during warmup.
            if (
                CAMERA_ENABLED
                and not empty_reference_captured
                and elapsed_s >= FIRST_IMAGE_DELAY_SEC
            ):
                image_count += 1
                pending_image_filename = capture_and_record(
                    image_writer, image_file, image_count, elapsed_s
                )
                empty_reference_captured = True

            # Warmup ends with an explicit insertion event. Waiting for Enter
            # prevents the baseline image from being taken while the chamber is
            # still open or the chicken is being positioned.
            if not food_inserted and elapsed_s >= PREHEAT_MINUTES * 60:
                print("\n================================")
                print("SENSOR WARMUP COMPLETE")
                print("Insert the chicken and close the chamber.")
                input("Press Enter when the chicken is positioned: ")
                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass
                food_inserted = True
                food_inserted_time = time.time()
                elapsed_s = food_inserted_time - start_time
                phase = "Baseline"
                metadata["food_inserted_time"] = datetime.now().isoformat()
                metadata["actual_warmup_elapsed_s"] = round(elapsed_s, 2)
                with open(metadata_path, "w") as metadata_file:
                    json.dump(metadata, metadata_file, indent=4)
                if CAMERA_ENABLED:
                    image_count += 1
                    pending_image_filename = capture_and_record(
                        image_writer, image_file, image_count, elapsed_s
                    )
                    next_image_time = food_inserted_time + IMAGE_INTERVAL_SEC
                print("Food baseline logging started.\n")

            # Continue at five-minute intervals relative to insertion.
            if (
                CAMERA_ENABLED
                and food_inserted
                and next_image_time is not None
                and time.time() >= next_image_time
            ):
                elapsed_s = time.time() - start_time
                image_count += 1
                pending_image_filename = capture_and_record(
                    image_writer, image_file, image_count, elapsed_s
                )
                next_image_time += IMAGE_INTERVAL_SEC
                if next_image_time < time.time():
                    next_image_time = time.time() + IMAGE_INTERVAL_SEC

            # ================= SENSOR SERIAL READ =================
            raw_line = ser.readline().decode("utf-8", errors="ignore").strip()

            if not raw_line:
                if elapsed_s - last_no_data_print > 5:
                    print(
                        f"[NO SERIAL DATA] t={elapsed_s:.1f}s "
                        f"- check COM port / Arduino Serial Monitor closed"
                    )
                    last_no_data_print = elapsed_s
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

            sensor_writer.writerow([
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
                pending_image_filename
            ])

            sensor_file.flush()

            print(
                f"[{phase}] "
                f"t={elapsed_s:.1f}s, "
                f"NH3={v_NH3:.3f}V, "
                f"CH4={v_CH4:.3f}V, "
                f"H2S={v_H2S:.3f}V, "
                f"BME={bme_gas_ohms}, "
                f"T={temp_C:.2f}C, "
                f"RH={humidity_pct:.2f}%, "
                f"IMG={pending_image_filename}"
            )

            pending_image_filename = "none"

except KeyboardInterrupt:
    print("\nLogging stopped by user.")

finally:
    ser.close()

    print("\n================================")
    print("DATA LOGGER STOPPED")
    print("================================")
    print(f"Sensor data saved to: {csv_path}")
    print(f"Image log saved to:   {image_log_path}")
    print(f"Images saved to:      {images_dir}")

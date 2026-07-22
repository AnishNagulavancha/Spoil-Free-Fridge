"""Combined sensor and camera logger for the chicken proof-of-concept trial.

BEFORE EACH RUN
1. Treat this as a controlled room-temperature deterioration experiment. The
   chicken is experimental waste and must never be cooked, tasted, or eaten.
2. Clean the chamber, install an empty sample tray, and keep the chicken
   refrigerated until the insertion prompt appears.
3. Set COM_PORT and CAMERA_CAPTURE_URL below. Close Arduino Serial Monitor so
   this script can open the serial port.
4. Set a unique SESSION_ID and the correct SITE_ID, PCB_DESIGN_ID, DEVICE_ID,
   OPERATOR_ID, and CONTAINER_ID. Identical PCB designs still need distinct
   DEVICE_ID values. Record the sample ID, cut, mass, and source batch for every
   chicken run.
   For this trial use:
       SESSION_ROLE = "control", "pilot", or "confirmation"
       FOOD_CATEGORY = "poultry"
       FOOD_NAME = "chicken"
       LABEL = "Unlabeled"
       LOG_MINUTES = 240
5. Confirm that SAVE_ROOT has enough space and that the camera, LEDs, sensors,
   and ESP32 are powered. Do not move the camera or change lighting during a run.

RUN PROCEDURE
1. Start this script with the chamber empty. Opening serial resets the ESP32.
2. The script captures one empty-chamber reference image after the camera startup
   delay, while sensor rows are recorded with phase="Warmup".
3. Wait for the complete 30-minute warmup. Do not insert chicken early.
4. For chicken runs, insert and position the chicken, close the chamber, and
   only then press Enter. For controls, open the chamber for the same handling
   time, close it without food, and press Enter.
5. The script records the insertion time, captures the initial chicken image,
   and begins a 30-minute phase="Baseline" period.
6. After baseline, rows use LABEL as their phase. Images are captured every five
   minutes relative to insertion. Leave the chamber closed for the entire run.
7. Let LOG_MINUTES stop the experiment or press Ctrl+C once if an early stop is
   necessary. Do not close the terminal or disconnect the ESP32 abruptly.

AFTER THE RUN
1. Verify sensor_log.csv, image_log.csv, metadata.json, and the images folder in
   the new session directory.
2. Discard the chicken without tasting or re-refrigerating it. Keep it sealed
   during handling and clean potentially contaminated surfaces appropriately.
3. Run: python analyze_session.py "<session folder>"
4. Keep any manual records limited to appearance visible through the closed
   chamber. Use observations_template.csv as supporting annotation, not as
   guessed fresh/spoiled ground truth.

Timing is relative to chicken insertion for LOG_MINUTES and image scheduling.
Warmup data is retained for diagnostics but excluded by analyze_session.py.
Four hours at room temperature exceeds the normal consumer handling window.
The sample remains experimental waste regardless of the model output. This
prototype estimates deterioration-associated change; it is not a food-safety
test.
"""

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

SESSION_ID = "S0003_Anish"
SITE_ID = "house_A"
PCB_DESIGN_ID = "spoil_free_pcb_v1"
DEVICE_ID = "pcb_A"
OPERATOR_ID = "operator_A"
CONTAINER_ID = "chamber_A"
SESSION_ROLE = "control"  # control, pilot, or confirmation

FOOD_CATEGORY = "poultry"
FOOD_NAME = "chicken"
SAMPLE_ID = "sample_001"
SAMPLE_CUT = "breast"
SAMPLE_MASS_G = 0     # replace with measured mass for chicken runs
SOURCE_BATCH_ID = "batch_A"
LABEL = "Unlabeled"

PREHEAT_MINUTES = 30
FOOD_BASELINE_MINUTES = 30
LOG_MINUTES = 240          # 4 hours after the insertion/control prompt
PROTOCOL_VERSION = "prototype_1_control_calibrated_4h_v2"

EXPECTED_FIELDS = 10

# Expected ESP32 CSV:
# adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms

# ================= CAMERA SETTINGS =================
CAMERA_ENABLED = True

# Use the IP printed by the combined ESP32 Serial Monitor
CAMERA_CAPTURE_URL = "http://192.168.1.3/capture"

# After chicken insertion, capture every 5 minutes.
IMAGE_INTERVAL_SEC = 300

# Empty-chamber reference image. Opening Serial resets the ESP32, so allow the
# camera time to become available before requesting this first image.
FIRST_IMAGE_DELAY_SEC = 25

CAMERA_TIMEOUT_SEC = 20

# Failed empty-reference captures retry throughout warmup. Post-prompt and
# scheduled captures receive this many additional attempts without changing the
# five-minute schedule.
IMAGE_RETRY_DELAY_SEC = 10
MAX_IMAGE_RETRIES = 3

# ================= SESSION SETUP =================
if SESSION_ROLE not in {"control", "pilot", "confirmation"}:
    raise ValueError("SESSION_ROLE must be control, pilot, or confirmation")
for field_name, field_value in {
    "SESSION_ID": SESSION_ID,
    "SITE_ID": SITE_ID,
    "PCB_DESIGN_ID": PCB_DESIGN_ID,
    "DEVICE_ID": DEVICE_ID,
    "OPERATOR_ID": OPERATOR_ID,
    "CONTAINER_ID": CONTAINER_ID,
}.items():
    if not str(field_value).strip():
        raise ValueError(f"{field_name} must not be blank")
if SESSION_ROLE != "control":
    if SAMPLE_MASS_G is None or float(SAMPLE_MASS_G) <= 0:
        raise ValueError("Set SAMPLE_MASS_G to the measured chicken mass before this run")
    if not all(str(value).strip() for value in (SAMPLE_ID, SAMPLE_CUT, SOURCE_BATCH_ID)):
        raise ValueError("Set SAMPLE_ID, SAMPLE_CUT, and SOURCE_BATCH_ID before this run")

LOGGED_FOOD_CATEGORY = "none" if SESSION_ROLE == "control" else FOOD_CATEGORY
LOGGED_FOOD_NAME = "empty" if SESSION_ROLE == "control" else FOOD_NAME

timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
session_name = (
    f"{SITE_ID}_{DEVICE_ID}_{SESSION_ID}_{SESSION_ROLE}_{LOGGED_FOOD_NAME}_{timestamp_str}"
)

session_dir = SAVE_ROOT / session_name
images_dir = session_dir / "images"

session_dir.mkdir(parents=True, exist_ok=True)
images_dir.mkdir(parents=True, exist_ok=True)

csv_path = session_dir / "sensor_log.csv"
image_log_path = session_dir / "image_log.csv"
metadata_path = session_dir / "metadata.json"

metadata = {
    "protocol_version": PROTOCOL_VERSION,
    "session_id": SESSION_ID,
    "site_id": SITE_ID,
    "pcb_design_id": PCB_DESIGN_ID,
    "device_id": DEVICE_ID,
    "operator_id": OPERATOR_ID,
    "container_id": CONTAINER_ID,
    "session_role": SESSION_ROLE,
    "food_category": LOGGED_FOOD_CATEGORY,
    "food_name": LOGGED_FOOD_NAME,
    "target_food_category": FOOD_CATEGORY,
    "target_food_name": FOOD_NAME,
    "sample_id": None if SESSION_ROLE == "control" else SAMPLE_ID,
    "sample_cut": None if SESSION_ROLE == "control" else SAMPLE_CUT,
    "sample_mass_g": None if SESSION_ROLE == "control" else SAMPLE_MASS_G,
    "source_batch_id": None if SESSION_ROLE == "control" else SOURCE_BATCH_ID,
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
    "image_retry_delay_sec": IMAGE_RETRY_DELAY_SEC,
    "max_image_retries": MAX_IMAGE_RETRIES,
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
print(f"Site/device:    {SITE_ID} / {DEVICE_ID}")
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
    return result


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
next_reference_attempt_s = FIRST_IMAGE_DELAY_SEC
food_inserted = False
food_inserted_time = None
image_retry_due = None
image_retry_count = 0
image_retry_reason = None

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
            "site_id",
            "pcb_design_id",
            "device_id",
            "container_id",
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
                and not food_inserted
                and elapsed_s >= next_reference_attempt_s
            ):
                image_count += 1
                result = capture_and_record(
                    image_writer, image_file, image_count, elapsed_s
                )
                pending_image_filename = result["filename"]
                if result["status"] == "success":
                    empty_reference_captured = True
                else:
                    next_reference_attempt_s = (
                        time.time() - start_time + IMAGE_RETRY_DELAY_SEC
                    )
                    print(
                        f"[IMAGE RETRY] Empty reference will retry in "
                        f"{IMAGE_RETRY_DELAY_SEC}s"
                    )

            # Warmup ends with an explicit insertion event. Waiting for Enter
            # prevents the baseline image from being taken while the chamber is
            # still open or the chicken is being positioned.
            if not food_inserted and elapsed_s >= PREHEAT_MINUTES * 60:
                print("\n================================")
                print("SENSOR WARMUP COMPLETE")
                if SESSION_ROLE == "control":
                    print("CONTROL: open and close the chamber without adding food.")
                    input("Press Enter when the empty chamber is closed: ")
                else:
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
                prompt_time = datetime.now().isoformat()
                metadata["post_prompt_start_time"] = prompt_time
                if SESSION_ROLE == "control":
                    metadata["control_prompt_time"] = prompt_time
                else:
                    metadata["food_inserted_time"] = prompt_time
                metadata["actual_warmup_elapsed_s"] = round(elapsed_s, 2)
                metadata["empty_reference_captured"] = empty_reference_captured
                with open(metadata_path, "w") as metadata_file:
                    json.dump(metadata, metadata_file, indent=4)
                if CAMERA_ENABLED and not empty_reference_captured:
                    print(
                        "[IMAGE WARNING] No empty reference was captured during warmup. "
                        "Sensor logging will continue, but camera analysis may be unavailable."
                    )
                if CAMERA_ENABLED:
                    image_count += 1
                    result = capture_and_record(
                        image_writer, image_file, image_count, elapsed_s
                    )
                    pending_image_filename = result["filename"]
                    if result["status"] != "success":
                        image_retry_due = time.time() + IMAGE_RETRY_DELAY_SEC
                        image_retry_count = 0
                        image_retry_reason = "post-prompt baseline image"
                    next_image_time = food_inserted_time + IMAGE_INTERVAL_SEC
                print(f"{SESSION_ROLE.capitalize()} baseline logging started.\n")

            # Retry a failed post-prompt or scheduled capture between regular
            # five-minute image times. Each retry is recorded in image_log.csv.
            if (
                CAMERA_ENABLED
                and food_inserted
                and image_retry_due is not None
                and time.time() >= image_retry_due
            ):
                image_retry_count += 1
                elapsed_s = time.time() - start_time
                image_count += 1
                print(
                    f"[IMAGE RETRY] {image_retry_reason}: attempt "
                    f"{image_retry_count}/{MAX_IMAGE_RETRIES}"
                )
                result = capture_and_record(
                    image_writer, image_file, image_count, elapsed_s
                )
                pending_image_filename = result["filename"]
                if result["status"] == "success":
                    image_retry_due = None
                    image_retry_count = 0
                    image_retry_reason = None
                elif image_retry_count < MAX_IMAGE_RETRIES:
                    image_retry_due = time.time() + IMAGE_RETRY_DELAY_SEC
                else:
                    print(
                        f"[IMAGE ERROR] Giving up on {image_retry_reason} after "
                        f"{MAX_IMAGE_RETRIES} retries; the next scheduled capture will continue."
                    )
                    image_retry_due = None
                    image_retry_count = 0
                    image_retry_reason = None

            # Continue at five-minute intervals relative to insertion.
            if (
                CAMERA_ENABLED
                and food_inserted
                and next_image_time is not None
                and image_retry_due is None
                and time.time() >= next_image_time
            ):
                elapsed_s = time.time() - start_time
                image_count += 1
                result = capture_and_record(
                    image_writer, image_file, image_count, elapsed_s
                )
                pending_image_filename = result["filename"]
                if result["status"] != "success":
                    image_retry_due = time.time() + IMAGE_RETRY_DELAY_SEC
                    image_retry_count = 0
                    image_retry_reason = "scheduled image"
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
                SITE_ID,
                PCB_DESIGN_ID,
                DEVICE_ID,
                CONTAINER_ID,
                LOGGED_FOOD_CATEGORY,
                LOGGED_FOOD_NAME,
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

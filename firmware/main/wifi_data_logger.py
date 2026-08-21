"""Log ESP32 sensor batches and camera images entirely over Wi-Fi.

The ESP32 is expected to expose:
    GET /sensor-data  newline-separated ten-field CSV records
    GET /capture      one JPEG image

Connection failures are normal while the ESP32 is in light sleep.
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import requests


FIELDS = [
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
]


def parse_batch(text: str) -> list[list[float]]:
    records: list[list[float]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != len(FIELDS):
            raise ValueError(f"expected 10 fields, received {len(parts)}: {line!r}")
        records.append([float(part) for part in parts])
    return records


def download_sensor_batch(session: requests.Session, base_url: str, timeout: float):
    response = session.get(f"{base_url}/sensor-data", timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if not content_type.lower().startswith("text/csv"):
        raise ValueError(f"unexpected sensor Content-Type: {content_type!r}")
    return parse_batch(response.text)


def download_image(
    session: requests.Session,
    base_url: str,
    timeout: float,
    images_dir: Path,
    image_number: int,
) -> Path:
    response = session.get(f"{base_url}/capture", timeout=timeout)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if not content_type.lower().startswith("image/jpeg"):
        raise ValueError(f"unexpected image Content-Type: {content_type!r}")
    if not (response.content.startswith(b"\xff\xd8") and
            response.content.endswith(b"\xff\xd9")):
        raise ValueError("capture response is not a complete JPEG")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = images_dir / f"img_{image_number:06d}_{timestamp}.jpg"
    path.write_bytes(response.content)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Wi-Fi ESP32 sensor/camera logger")
    parser.add_argument("--base-url", default="http://192.168.1.11")
    parser.add_argument("--output", type=Path, default=Path("wifi_logs"))
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--image-interval", type=float, default=300.0)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument(
        "--duration-minutes",
        type=float,
        default=None,
        help="Stop after this duration; omit to run until Ctrl+C",
    )
    args = parser.parse_args()

    started_at = datetime.now()
    session_dir = args.output / started_at.strftime("%Y%m%d_%H%M%S")
    images_dir = session_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    sensor_path = session_dir / "sensor_log.csv"
    image_path = session_dir / "image_log.csv"

    started = time.monotonic()
    next_image = started
    image_number = 0
    last_offline_notice = float("-inf")

    print(f"ESP32:       {args.base_url}")
    print(f"Sensor log:  {sensor_path.resolve()}")
    print(f"Image log:   {image_path.resolve()}")
    print("Connection failures are expected while the ESP32 is asleep.")

    session = requests.Session()
    try:
        with sensor_path.open("w", newline="") as sensor_file, image_path.open(
            "w", newline=""
        ) as image_file:
            sensor_writer = csv.writer(sensor_file)
            image_writer = csv.writer(image_file)
            sensor_writer.writerow(["received_timestamp_iso", *FIELDS])
            image_writer.writerow(
                ["timestamp_iso", "image_number", "filename", "status", "error"]
            )

            while True:
                now = time.monotonic()
                if (args.duration_minutes is not None and
                        now - started >= args.duration_minutes * 60):
                    break

                try:
                    records = download_sensor_batch(
                        session, args.base_url.rstrip("/"), args.timeout
                    )
                    received_at = datetime.now().isoformat(timespec="seconds")
                    for values in records:
                        sensor_writer.writerow([received_at, *values])
                    if records:
                        sensor_file.flush()
                        print(f"[DATA] Saved {len(records)} records")
                except (requests.RequestException, ValueError) as exc:
                    if now - last_offline_notice >= 10:
                        print(f"[ASLEEP/OFFLINE] {exc}")
                        last_offline_notice = now

                if args.image_interval > 0 and now >= next_image:
                    try:
                        image_number += 1
                        saved_image = download_image(
                            session,
                            args.base_url.rstrip("/"),
                            args.timeout,
                            images_dir,
                            image_number,
                        )
                        image_writer.writerow(
                            [
                                datetime.now().isoformat(timespec="seconds"),
                                image_number,
                                saved_image.name,
                                "success",
                                "",
                            ]
                        )
                        image_file.flush()
                        print(f"[IMAGE] Saved {saved_image.name}")
                        next_image = now + args.image_interval
                    except (requests.RequestException, ValueError) as exc:
                        image_number -= 1
                        # Leave next_image due so capture retries on the next poll.
                        if now - last_offline_notice >= 10:
                            print(f"[IMAGE RETRY] {exc}")
                            last_offline_notice = now

                time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        session.close()

    print(f"Saved session to {session_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

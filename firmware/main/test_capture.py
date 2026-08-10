"""Quick test for the ESP32-S3 /capture endpoint and capture LEDs.

Expected physical behavior for every request:
    LEDs off while idle -> LEDs on briefly during capture -> LEDs off again.

The script also checks that the response is a non-empty JPEG and saves it.
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import requests


JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"


def capture_once(url: str, timeout: float, output_dir: Path, number: int) -> bool:
    print(f"\nCapture {number}: watch the LEDs now...")
    started = time.perf_counter()

    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        elapsed = time.perf_counter() - started
        print(f"FAIL: request failed after {elapsed:.2f}s: {exc}")
        print("The LEDs should be OFF because of the firmware safety timer.")
        return False

    elapsed = time.perf_counter() - started
    content_type = response.headers.get("Content-Type", "")
    is_jpeg = (
        response.content.startswith(JPEG_START)
        and response.content.endswith(JPEG_END)
    )

    if response.status_code != 200:
        print(f"FAIL: HTTP status was {response.status_code}, expected 200")
        return False

    if not content_type.lower().startswith("image/jpeg"):
        print(f"FAIL: Content-Type was {content_type!r}, expected image/jpeg")
        return False

    if not is_jpeg:
        print("FAIL: response does not contain a complete JPEG file")
        return False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = output_dir / f"capture_test_{number}_{timestamp}.jpg"
    image_path.write_bytes(response.content)

    print(
        f"PASS: received {len(response.content)} bytes in {elapsed:.2f}s\n"
        f"Saved: {image_path.resolve()}"
    )
    print("Confirm that the LEDs are OFF again.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the ESP32 JPEG endpoint")
    parser.add_argument(
        "--url",
        default="http://192.168.1.3/capture",
        help="ESP32 capture URL",
    )
    parser.add_argument("--count", type=int, default=3, help="Number of captures")
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Idle seconds between captures",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("capture_test_output"),
        help="Directory for downloaded JPEG files",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.interval < 0 or args.timeout <= 0:
        parser.error("--interval must be non-negative and --timeout must be positive")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Testing: {args.url}")
    print("Before the first request, confirm that the LEDs are OFF.")
    print("Starting in 3 seconds...")
    time.sleep(3)

    passed = 0
    for number in range(1, args.count + 1):
        if capture_once(args.url, args.timeout, args.output_dir, number):
            passed += 1

        if number < args.count:
            print(f"Idle test for {args.interval:.1f}s: LEDs must remain OFF.")
            time.sleep(args.interval)

    print(f"\nResult: {passed}/{args.count} HTTP/JPEG tests passed.")
    print("Physical LED behavior must be confirmed visually.")
    return 0 if passed == args.count else 1


if __name__ == "__main__":
    raise SystemExit(main())

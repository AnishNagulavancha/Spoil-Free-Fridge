import requests
import csv
import os
from datetime import datetime
from PIL import Image
from io import BytesIO


# ================= SETTINGS =================

IMAGE_FOLDER = "captures"
CSV_FILE = "captures.csv"


# ================= CREATE FOLDER =================

if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)


# ================= CAPTURE IMAGE =================

def capture_image(url):

    print("\nCapturing image...")

    try:
        response = requests.get(url, timeout=10)

    except Exception as e:
        print("Connection failed:")
        print(e)
        return


    if response.status_code != 200:
        print("Camera capture failed")
        return


    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = f"image_{timestamp}.jpg"
    filepath = os.path.join(IMAGE_FOLDER, filename)


    # Save image
    with open(filepath, "wb") as file:
        file.write(response.content)


    print("Saved:", filepath)


    # Get image dimensions
    image = Image.open(BytesIO(response.content))

    width, height = image.size


    # Save CSV data
    file_exists = os.path.isfile(CSV_FILE)

    with open(CSV_FILE, "a", newline="") as csvfile:

        writer = csv.writer(csvfile)

        if not file_exists:
            writer.writerow([
                "filename",
                "timestamp",
                "width",
                "height",
                "source"
            ])

        writer.writerow([
            filename,
            timestamp,
            width,
            height,
            url
        ])


    print("CSV updated")
    print("------------------------")


# ================= MAIN =================

if __name__ == "__main__":

    esp_url = input(
        "Paste ESP32 capture URL (example: http://192.168.4.1/capture):\n> "
    )

    capture_image(esp_url)
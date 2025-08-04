import serial
import time
import csv

# ==== SETTINGS ====
COM_PORT = "COM3"        # Replace with your COM port
BAUD_RATE = 9600
PREHEAT_MINUTES = 15     
LOG_MINUTES = 30         
FRESHNESS_LABEL = "Fresh"  

# ==== FOLDER TO SAVE ====
SAVE_FOLDER = r"C:\Users\anish\Documents\SensorLogs"  # Change as needed

# File name with timestamp (no os module needed)
timestamp_str = time.strftime("%Y%m%d_%H%M%S")
CSV_FILENAME = f"{SAVE_FOLDER}\\sensor_log_{timestamp_str}.csv"

# ==== SERIAL SETUP ====
ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
time.sleep(2)

with open(CSV_FILENAME, "w", newline="") as f:
    writer = csv.writer(f)
    # CSV header: timestamp first, label last
    writer.writerow([
        "Timestamp","NH3_raw","NH3_V","CH4_raw","CH4_V","H2S_raw","H2S_V","Temp_C","Pressure_Pa","Humidity_pct","GasRes","Label"
    ])

    print(f"Saving data to: {CSV_FILENAME}")
    print(f"Preheating {PREHEAT_MINUTES} min...")

    start_time = time.time()

    # ---- PREHEAT PHASE ----
    while time.time() - start_time < PREHEAT_MINUTES * 60:
        line = ser.readline().decode('utf-8').strip()
        if line and line.count(",") >= 7:
            row = line.split(",")
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            writer.writerow([timestamp] + row + ["Warmup"])
            print("[WARMUP] " + line)

    print("Logging started...")
    log_start = time.time()

    # ---- LOGGING PHASE ----
    while time.time() - log_start < LOG_MINUTES * 60:
        line = ser.readline().decode('utf-8').strip()
        if line and line.count(",") >= 7:
            row = line.split(",")
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            writer.writerow([timestamp] + row + [FRESHNESS_LABEL])
            print(line)

print(f"Logging complete. Data saved to {CSV_FILENAME}")

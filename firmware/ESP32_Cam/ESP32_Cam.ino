#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_BME680.h>

<<<<<<< HEAD
Adafruit_ADS1115 ads;
Adafruit_BME680 bme;
=======
// ================= YOUR WIFI =================
// ESP32 connects to your normal Wi-Fi.
// Laptop stays on the same Wi-Fi.
const char* wifi_ssid = "Airtel_Sridhar_EXT";
const char* wifi_password = "air12345";

// ================= LED PIN =================
// Your PCB: D0 / GPIO1 controls LED MOSFET, active HIGH
#define LED_PWR_PIN 1
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d

const uint8_t ADS_ADDRESS = 0x48;
const uint8_t BME_ADDRESS = 0x76;

// Change D0 to the actual GPIO number if your board does not define D0
const int CONTROL_PIN = D0;

const unsigned long RETRY_DELAY_MS = 5000;
const unsigned long READ_DELAY_MS = 1000;

bool adsConnected = false;
bool bmeConnected = false;

unsigned long previousReadTime = 0;

<<<<<<< HEAD
// Check whether an I2C address responds
bool isI2CDeviceConnected(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool connectADS1115() {
  Serial.println("Trying to connect to ADS1115 at 0x48...");

  if (!isI2CDeviceConnected(ADS_ADDRESS)) {
    Serial.println("ADS1115 not found.");
=======
// ================= LED HELPERS =================
void ledsOn() {
  digitalWrite(LED_PWR_PIN, HIGH);
}

void ledsOff() {
  digitalWrite(LED_PWR_PIN, LOW);
}

// ================= HTML =================
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<title>ESP32 Camera</title>
<style>
body{
    font-family:Arial;
    text-align:center;
    background:#f0f0f0;
}
button{
    padding:12px 24px;
    font-size:18px;
    cursor:pointer;
    margin:10px;
}
img{
    margin-top:20px;
    border:2px solid black;
    width:800px;
    max-width:95%;
}
#status{
    margin-top:10px;
    font-weight:bold;
}
</style>
</head>

<body>

<h2>XIAO ESP32-S3 Camera</h2>

<button onclick="capture()">Capture Image</button>

<div id="status">Ready</div>

<br>

<img id="photo">

<script>
async function capture(){
    const status = document.getElementById("status");
    const img = document.getElementById("photo");

    status.innerText = "Capturing...";

    try {
        const response = await fetch("/capture?t=" + Date.now(), {
            cache: "no-store"
        });

        if (!response.ok) {
            status.innerText = "Capture failed: " + response.status;
            return;
        }

        const blob = await response.blob();

        if (img.src) {
            URL.revokeObjectURL(img.src);
        }

        img.src = URL.createObjectURL(blob);
        status.innerText = "Captured at " + new Date().toLocaleTimeString();
    } catch (err) {
        status.innerText = "Error: " + err;
    }
}

window.onload = capture;
</script>

</body>
</html>
)rawliteral";

// ================= ROOT PAGE =================
void handleRoot() {
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "text/html", index_html);
}

// ================= CAPTURE =================
void handleCapture() {
  Serial.println("Capture request received");

  // Turn LEDs ON only during capture
  ledsOn();

  // Let LEDs and auto-exposure settle
  delay(30);

  // Discard first frame
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) esp_camera_fb_return(fb);
  delay(100);

  // Discard second frame
  fb = esp_camera_fb_get();
  if (fb) esp_camera_fb_return(fb);
  delay(100);

  // Real capture
  fb = esp_camera_fb_get();

  if (!fb) {
    ledsOff();
    Serial.println("Camera capture failed");
    server.send(500, "text/plain", "Camera Capture Failed");
    return;
  }

  server.sendHeader("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  server.sendHeader("Pragma", "no-cache");
  server.sendHeader("Expires", "0");
  server.setContentLength(fb->len);

  server.send(200, "image/jpeg", "");

  WiFiClient client = server.client();
  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);

  ledsOff();

  Serial.println("Capture complete, LEDs OFF");
}

// ================= CAMERA INIT =================
bool initCamera() {
  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Good starting quality for ML images
  config.frame_size = FRAMESIZE_SVGA;   // 800x600
  config.jpeg_quality = 8;              // lower number = better quality

  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d
    return false;
  }

  if (!ads.begin(ADS_ADDRESS, &Wire)) {
    Serial.println("ADS1115 initialization failed.");
    return false;
  }

<<<<<<< HEAD
  ads.setGain(GAIN_ONE);
=======
  s->set_brightness(s, -1);
  s->set_contrast(s, 1);
  s->set_saturation(s, 0);

  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d

  Serial.println("ADS1115 connected.");
  return true;
}

<<<<<<< HEAD
bool connectBME680() {
  Serial.println("Trying to connect to BME680 at 0x76...");

  if (!isI2CDeviceConnected(BME_ADDRESS)) {
    Serial.println("BME680 not found.");
    return false;
  }

  if (!bme.begin(BME_ADDRESS, &Wire)) {
    Serial.println("BME680 initialization failed.");
    return false;
  }

  bme.setTemperatureOversampling(BME680_OS_8X);
  bme.setHumidityOversampling(BME680_OS_2X);
  bme.setPressureOversampling(BME680_OS_4X);
  bme.setIIRFilterSize(BME680_FILTER_SIZE_3);

  // Gas heater: 320°C for 150 ms
  bme.setGasHeater(320, 150);

  Serial.println("BME680 connected.");
  return true;
}

void reconnectSensors() {
  while (!adsConnected || !bmeConnected) {
    // Still allow on/off commands while waiting for sensors
    handleSerialCommands();

    if (!adsConnected) {
      adsConnected = connectADS1115();
    }

    if (!bmeConnected) {
      bmeConnected = connectBME680();
    }

    if (!adsConnected || !bmeConnected) {
      Serial.println("One or more sensors are unavailable.");
      Serial.println("Trying again in 5 seconds...");
      Serial.println();

      unsigned long retryStart = millis();

      // Wait five seconds without blocking serial commands
      while (millis() - retryStart < RETRY_DELAY_MS) {
        handleSerialCommands();
        delay(10);
      }
    }
  }

  Serial.println("Both sensors are connected.");
  Serial.println();
}

// Read commands typed into the Serial Monitor
void handleSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');

    command.trim();
    command.toLowerCase();

    if (command == "on") {
      digitalWrite(CONTROL_PIN, HIGH);
      Serial.println("D0 turned ON.");
    }
    else if (command == "off") {
      digitalWrite(CONTROL_PIN, LOW);
      Serial.println("D0 turned OFF.");
    }
    else if (command.length() > 0) {
      Serial.print("Unknown command: ");
      Serial.println(command);
      Serial.println("Type 'on' or 'off'.");
    }
  }
}

void printSensorValues() {
  // Check that both devices still respond
  if (!isI2CDeviceConnected(ADS_ADDRESS)) {
    Serial.println("ADS1115 connection lost.");
    adsConnected = false;
  }

  if (!isI2CDeviceConnected(BME_ADDRESS)) {
    Serial.println("BME680 connection lost.");
    bmeConnected = false;
  }

  if (!adsConnected || !bmeConnected) {
    reconnectSensors();
    return;
=======
// ================= WIFI STATION =================
void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setSleep(WIFI_PS_NONE);

  Serial.println();
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(wifi_ssid);

  WiFi.begin(wifi_ssid, wifi_password);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED && attempts < 60) {
    delay(500);
    Serial.print(".");
    attempts++;
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d
  }

  // Read ADS1115 channels A1, A2, and A3
  int16_t gas1Raw = ads.readADC_SingleEnded(1);
  int16_t gas2Raw = ads.readADC_SingleEnded(2);
  int16_t gas3Raw = ads.readADC_SingleEnded(3);

  float gas1Voltage = ads.computeVolts(gas1Raw);
  float gas2Voltage = ads.computeVolts(gas2Raw);
  float gas3Voltage = ads.computeVolts(gas3Raw);

  // Read BME680
  if (!bme.performReading()) {
    Serial.println("Failed to read BME680.");
    bmeConnected = false;
    return;
  }

  float temperatureC = bme.temperature;
  float humidityPercent = bme.humidity;
  float pressureHpa = bme.pressure / 100.0F;
  float gasResistanceKOhms = bme.gas_resistance / 1000.0F;

  Serial.println("========== SENSOR VALUES ==========");

  Serial.println("ADS1115 MEMS Gas Sensors:");

  Serial.print("Gas Sensor 1 - A1: ");
  Serial.print(gas1Raw);
  Serial.print(" raw, ");
  Serial.print(gas1Voltage, 4);
  Serial.println(" V");

  Serial.print("Gas Sensor 2 - A2: ");
  Serial.print(gas2Raw);
  Serial.print(" raw, ");
  Serial.print(gas2Voltage, 4);
  Serial.println(" V");

  Serial.print("Gas Sensor 3 - A3: ");
  Serial.print(gas3Raw);
  Serial.print(" raw, ");
  Serial.print(gas3Voltage, 4);
  Serial.println(" V");

  Serial.println();

  Serial.println("BME680:");

  Serial.print("Temperature: ");
  Serial.print(temperatureC, 2);
  Serial.println(" °C");

  Serial.print("Humidity: ");
  Serial.print(humidityPercent, 2);
  Serial.println(" %");

  Serial.print("Pressure: ");
  Serial.print(pressureHpa, 2);
  Serial.println(" hPa");

  Serial.print("Gas resistance: ");
  Serial.print(gasResistanceKOhms, 2);
  Serial.println(" kOhms");

  Serial.println("===================================");
  Serial.println();
<<<<<<< HEAD
}

=======

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi connection failed.");
    Serial.println("Check SSID/password and make sure it is 2.4 GHz.");
    return;
  }

  Serial.println("================================");
  Serial.println("ESP32 Camera Connected to Wi-Fi");
  Serial.print("Open browser: http://");
  Serial.println(WiFi.localIP());
  Serial.print("Capture URL: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/capture");
  Serial.println("================================");
}

// ================= SETUP =================
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d
void setup() {
  Serial.begin(115200);
  delay(1000);

<<<<<<< HEAD
  pinMode(CONTROL_PIN, OUTPUT);

  // Start with D0 turned off
  digitalWrite(CONTROL_PIN, LOW);
=======
  Serial.println("Booting camera board...");

  pinMode(LED_PWR_PIN, OUTPUT);
  ledsOff();

  if (!initCamera()) {
    Serial.println("Camera failed. Restarting in 5 seconds...");
    delay(5000);
    ESP.restart();
  }
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d

  Wire.begin();

<<<<<<< HEAD
  Serial.println("Starting ADS1115 and BME680...");
  Serial.println("Type 'on' to turn D0 on.");
  Serial.println("Type 'off' to turn D0 off.");
  Serial.println();

  reconnectSensors();
}

void loop() {
  // Check for on/off commands continuously
  handleSerialCommands();

  // Print sensor values once every second
  if (millis() - previousReadTime >= READ_DELAY_MS) {
    previousReadTime = millis();
    printSensorValues();
  }
=======
  connectToWiFi();

  server.on("/", handleRoot);
  server.on("/capture", handleCapture);

  server.begin();

  Serial.println("HTTP Server Started");
}

// ================= LOOP =================
void loop() {
  server.handleClient();
>>>>>>> a62f21f9428228b3dc41fc2a64fe3e862e649a7d
}
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"
#include <Adafruit_ADS1X15.h>
#include "DFRobot_BME68x.h"

// =======================================================
// XIAO ESP32-S3 Sense Combined Firmware
// Sensors over Serial CSV + Camera over Wi-Fi
// LEDs turn ON only during image capture
// =======================================================

// ================= WIFI SETTINGS =================
const char* wifi_ssid = "Airtel_Sridhar_EXT";
const char* wifi_password = "air12345";

// ================= PCB PIN DEFINITIONS =================
// XIAO ESP32-S3 GPIO numbers
#define LED_PWR_PIN   1   // D0 / GPIO1, LEDs active HIGH
#define GAS_PWR_PIN   2   // D1 / GPIO2, gas sensors active LOW
#define BME_PWR_PIN   3   // D2 / GPIO3, BME688 active LOW

#define I2C_SDA       5   // D4 / GPIO5
#define I2C_SCL       6   // D5 / GPIO6

// ================= CAMERA PINS =================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10

#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39

#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15

#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

// ================= SETTINGS =================
#define SERIAL_BAUD 115200
#define I2C_FREQ    100000

// Sensor row interval
#define SENSOR_INTERVAL_MS 2000

// ================= OBJECTS =================
Adafruit_ADS1115 ads;
DFRobot_BME68x_I2C bme(0x76);
WebServer server(80);

bool adsOK = false;
bool bmeOK = false;
bool cameraOK = false;

unsigned long lastSensorRead = 0;

// ================= POWER HELPERS =================
void ledsOn()  { digitalWrite(LED_PWR_PIN, HIGH); }
void ledsOff() { digitalWrite(LED_PWR_PIN, LOW); }

void gasOn()   { digitalWrite(GAS_PWR_PIN, LOW); }
void gasOff()  { digitalWrite(GAS_PWR_PIN, HIGH); }

void bmeOn()   { digitalWrite(BME_PWR_PIN, LOW); }
void bmeOff()  { digitalWrite(BME_PWR_PIN, HIGH); }

// ================= HTML PAGE =================
const char index_html[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<title>ESP32 Food Camera</title>
<style>
body {
  font-family: Arial;
  text-align: center;
  background: #f0f0f0;
}
button {
  padding: 12px 24px;
  font-size: 18px;
  cursor: pointer;
  margin: 10px;
}
img {
  margin-top: 20px;
  border: 2px solid black;
  width: 640px;
  max-width: 95%;
}
#status {
  margin-top: 10px;
  font-weight: bold;
}
</style>
</head>

<body>
<h2>XIAO ESP32-S3 Food Camera</h2>
<button onclick="capture()">Capture Image</button>
<div id="status">Ready</div>
<br>
<img id="photo">

<script>
async function capture() {
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
</script>
</body>
</html>
)rawliteral";

// ================= ADS INIT =================
bool initADS1115() {
  uint8_t addresses[] = {0x48, 0x49, 0x4A, 0x4B};

  for (int i = 0; i < 4; i++) {
    if (ads.begin(addresses[i])) {
      ads.setGain(GAIN_ONE);
      Serial.print("# ADS1115 initialized at 0x");
      Serial.println(addresses[i], HEX);
      return true;
    }
  }

  Serial.println("# ERROR: ADS1115 not found");
  return false;
}

// ================= BME INIT =================
bool initBME688() {
  for (int attempt = 1; attempt <= 5; attempt++) {
    uint8_t rslt = bme.begin();

    if (rslt == 0) {
      Serial.println("# BME688 initialized");

      bool heaterStatus = bme.setGasHeater(360, 100);
      if (heaterStatus) {
        Serial.println("# BME688 gas heater set");
      } else {
        Serial.println("# WARNING: BME688 gas heater failed");
      }

      return true;
    }

    Serial.println("# BME688 init failed, retrying...");
    delay(1000);
  }

  Serial.println("# ERROR: BME688 not initialized");
  return false;
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

  // Use stable settings first. Increase later if stable.
  config.frame_size = FRAMESIZE_VGA;   // 640x480
  config.jpeg_quality = 10;            // lower = better quality

  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("# ERROR: Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();

  s->set_brightness(s, -1);
  s->set_contrast(s, 1);
  s->set_saturation(s, 0);

  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);

  Serial.println("# Camera initialized");
  return true;
}

// ================= WIFI =================
void connectToWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.persistent(false);
  WiFi.setSleep(WIFI_PS_NONE);

  Serial.print("# Connecting to Wi-Fi: ");
  Serial.println(wifi_ssid);

  WiFi.begin(wifi_ssid, wifi_password);

  int attempts = 0;

  while (WiFi.status() != WL_CONNECTED && attempts < 60) {
    delay(500);
    Serial.print("# .\n");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("# Wi-Fi connected");
    Serial.print("# Open browser: http://");
    Serial.println(WiFi.localIP());
    Serial.print("# Capture URL: http://");
    Serial.print(WiFi.localIP());
    Serial.println("/capture");
  } else {
    Serial.println("# Wi-Fi failed. Starting fallback AP mode.");

    WiFi.mode(WIFI_AP);
    WiFi.softAP("ESP32-CAMERA", "12345678");

    Serial.print("# AP IP: http://");
    Serial.println(WiFi.softAPIP());
    Serial.println("# AP SSID: ESP32-CAMERA");
    Serial.println("# AP Password: 12345678");
  }
}

// ================= WEB HANDLERS =================
void handleRoot() {
  server.sendHeader("Cache-Control", "no-store");
  server.send(200, "text/html", index_html);
}

void handleCapture() {
  if (!cameraOK) {
    server.send(500, "text/plain", "Camera not initialized");
    return;
  }

  Serial.println("# Capture request received");

  ledsOn();
  delay(300);

  // Discard one frame to let exposure adjust
  camera_fb_t *fb = esp_camera_fb_get();
  if (fb) {
    esp_camera_fb_return(fb);
  }

  delay(100);

  // Real frame
  fb = esp_camera_fb_get();

  // Turn LEDs off immediately after frame is acquired
  ledsOff();

  if (!fb) {
    Serial.println("# ERROR: Camera capture failed");
    server.send(500, "text/plain", "Camera Capture Failed");
    return;
  }

  server.sendHeader("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  server.sendHeader("Pragma", "no-cache");
  server.sendHeader("Expires", "0");

  server.send_P(
    200,
    "image/jpeg",
    (const char*)fb->buf,
    fb->len
  );

  esp_camera_fb_return(fb);

  Serial.println("# Capture complete, LEDs OFF");
}

// ================= SENSOR READ + CSV =================
void printSensorRow() {
  int16_t adc_NH3 = -999;
  int16_t adc_CH4 = -999;
  int16_t adc_H2S = -999;

  float v_NH3 = -999.0;
  float v_CH4 = -999.0;
  float v_H2S = -999.0;

  float temperature = -999.0;
  float pressure = -999.0;
  float humidity = -999.0;
  float gasRes = -999.0;

  if (adsOK) {
    // PCB mapping:
    // A1 = NH3
    // A2 = CH4
    // A3 = H2S
    adc_NH3 = ads.readADC_SingleEnded(1);
    adc_CH4 = ads.readADC_SingleEnded(2);
    adc_H2S = ads.readADC_SingleEnded(3);

    v_NH3 = ads.computeVolts(adc_NH3);
    v_CH4 = ads.computeVolts(adc_CH4);
    v_H2S = ads.computeVolts(adc_H2S);
  }

  if (bmeOK) {
    bme.startConvert();
    delay(1000);
    bme.update();

    temperature = bme.readTemperature() / 100.0;
    pressure = bme.readPressure();
    humidity = bme.readHumidity() / 1000.0;
    gasRes = bme.readGasResistance();
  }

  // EXACT 10-field numeric CSV:
  // adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms

  Serial.print(adc_NH3);
  Serial.print(",");
  Serial.print(v_NH3, 3);
  Serial.print(",");

  Serial.print(adc_CH4);
  Serial.print(",");
  Serial.print(v_CH4, 3);
  Serial.print(",");

  Serial.print(adc_H2S);
  Serial.print(",");
  Serial.print(v_H2S, 3);
  Serial.print(",");

  Serial.print(temperature, 2);
  Serial.print(",");
  Serial.print(pressure, 2);
  Serial.print(",");

  Serial.print(humidity, 2);
  Serial.print(",");
  Serial.println(gasRes, 2);
}

// ================= SETUP =================
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(2000);

  Serial.println("# Combined sensor + camera firmware start");

  pinMode(LED_PWR_PIN, OUTPUT);
  pinMode(GAS_PWR_PIN, OUTPUT);
  pinMode(BME_PWR_PIN, OUTPUT);

  ledsOff();

  gasOn();
  bmeOn();

  delay(3000);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(I2C_FREQ);

  adsOK = initADS1115();
  bmeOK = initBME688();

  cameraOK = initCamera();

  connectToWiFi();

  server.on("/", handleRoot);
  server.on("/capture", handleCapture);
  server.begin();

  Serial.println("# HTTP server started");

  Serial.print("# ADS1115: ");
  Serial.println(adsOK ? "PASS" : "FAIL");

  Serial.print("# BME688: ");
  Serial.println(bmeOK ? "PASS" : "FAIL");

  Serial.print("# Camera: ");
  Serial.println(cameraOK ? "PASS" : "FAIL");

  Serial.println("# CSV header:");
  Serial.println("adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms");

  lastSensorRead = millis();
}

// ================= LOOP =================
void loop() {
  server.handleClient();

  unsigned long now = millis();

  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;

    gasOn();
    bmeOn();

    printSensorRow();
  }
}
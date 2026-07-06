#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

// ================= YOUR WIFI =================
// ESP32 connects to your normal Wi-Fi.
// Laptop stays on the same Wi-Fi.
const char* wifi_ssid = "Airtel_Sridhar_EXT";
const char* wifi_password = "air12345";

// ================= LED PIN =================
// Your PCB: D0 / GPIO1 controls LED MOSFET, active HIGH
#define LED_PWR_PIN 1

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

WebServer server(80);

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

  return true;
}

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
  }

  Serial.println();

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
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Booting camera board...");

  pinMode(LED_PWR_PIN, OUTPUT);
  ledsOff();

  if (!initCamera()) {
    Serial.println("Camera failed. Restarting in 5 seconds...");
    delay(5000);
    ESP.restart();
  }

  Serial.println("Camera OK");

  connectToWiFi();

  server.on("/", handleRoot);
  server.on("/capture", handleCapture);

  server.begin();

  Serial.println("HTTP Server Started");
}

// ================= LOOP =================
void loop() {
  server.handleClient();
}
#include <WiFi.h>
#include <WebServer.h>
#include "esp_camera.h"

// ================= ACCESS POINT =================
const char* ap_ssid = "ESP32-CAMERA";
const char* ap_password = "12345678";

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
}
img{
    margin-top:20px;
    border:2px solid black;
    width:640px;
    max-width:95%;
}
</style>
</head>

<body>

<h2>XIAO ESP32-S3 Camera</h2>

<button onclick="capture()">Capture Image</button>

<br><br>

<img id="photo" src="/capture">

<script>
function capture(){
    document.getElementById("photo").src="/capture?t="+new Date().getTime();
}
</script>

</body>
</html>
)rawliteral";

// ================= ROOT PAGE =================
void handleRoot() {
  server.send(200, "text/html", index_html);
}

// ================= CAPTURE =================
void handleCapture() {

  camera_fb_t *fb = esp_camera_fb_get();

  if (!fb) {
    server.send(500, "text/plain", "Camera Capture Failed");
    return;
  }

  server.sendHeader("Cache-Control","no-cache");
  server.send_P(200,
                "image/jpeg",
                (const char*)fb->buf,
                fb->len);

  esp_camera_fb_return(fb);
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

  config.frame_size = FRAMESIZE_VGA;     // 640x480
  config.jpeg_quality = 12;

  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);

  if(err != ESP_OK){
    Serial.printf("Camera init failed: 0x%x\n",err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();

  s->set_brightness(s,0);
  s->set_contrast(s,0);
  s->set_saturation(s,0);

  return true;
}

// ================= WIFI AP =================
void startAccessPoint(){

  WiFi.mode(WIFI_AP);

  if(!WiFi.softAP(ap_ssid,ap_password)){
    Serial.println("AP Failed");
    return;
  }

  Serial.println();
  Serial.println("================================");
  Serial.println("ESP32 Camera Access Point Ready");
  Serial.print("SSID: ");
  Serial.println(ap_ssid);
  Serial.print("Password: ");
  Serial.println(ap_password);
  Serial.print("Open browser: http://");
  Serial.println(WiFi.softAPIP());
  Serial.println("================================");
}

// ================= SETUP =================
void setup(){

  Serial.begin(115200);
  delay(1000);

  Serial.println("Booting...");

  if(!initCamera()){
    return;
  }

  Serial.println("Camera OK");

  startAccessPoint();

  server.on("/",handleRoot);
  server.on("/capture",handleCapture);

  server.begin();

  Serial.println("HTTP Server Started");
}

// ================= LOOP =================
void loop(){

  server.handleClient();

}
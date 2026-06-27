#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include "DFRobot_BME68x.h"

// =======================================================
// XIAO ESP32-S3 PCB DATA LOGGER
// Sensor-only firmware for laptop CSV logging
// =======================================================

// ---------------- PCB PIN DEFINITIONS ----------------
// XIAO ESP32-S3 GPIO numbers
#define LED_PWR_PIN   1   // D0 / GPIO1, LEDs active HIGH
#define GAS_PWR_PIN   2   // D1 / GPIO2, gas sensors active LOW
#define BME_PWR_PIN   3   // D2 / GPIO3, BME688 active LOW

#define I2C_SDA       5   // D4 / GPIO5
#define I2C_SCL       6   // D5 / GPIO6

// ---------------- SETTINGS ----------------
#define SERIAL_BAUD   115200
#define I2C_FREQ      100000

// Approx row interval:
// BME conversion delay + loop delay = around 2 seconds
#define BME_CONVERT_DELAY_MS 1000
#define LOOP_DELAY_MS        1000

// Print a header once at startup.
// Python logger will skip it because it is not numeric.
#define PRINT_CSV_HEADER true

// ---------------- OBJECTS ----------------
Adafruit_ADS1115 ads;
DFRobot_BME68x_I2C bme(0x76);

bool adsOK = false;
bool bmeOK = false;

// ---------------- POWER CONTROL ----------------
void ledsOn()  { digitalWrite(LED_PWR_PIN, HIGH); }
void ledsOff() { digitalWrite(LED_PWR_PIN, LOW);  }

void gasOn()   { digitalWrite(GAS_PWR_PIN, LOW);  }  // P-MOS active LOW
void gasOff()  { digitalWrite(GAS_PWR_PIN, HIGH); }

void bmeOn()   { digitalWrite(BME_PWR_PIN, LOW);  }  // P-MOS active LOW
void bmeOff()  { digitalWrite(BME_PWR_PIN, HIGH); }

// ---------------- ADS INIT ----------------
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

// ---------------- BME INIT ----------------
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

// ---------------- SETUP ----------------
void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(2000);

  Serial.println("# PCB DATA LOGGER START");

  pinMode(LED_PWR_PIN, OUTPUT);
  pinMode(GAS_PWR_PIN, OUTPUT);
  pinMode(BME_PWR_PIN, OUTPUT);

  // For sensor logging, LEDs stay OFF.
  ledsOff();

  // Keep gas sensors and BME688 ON for stable continuous logging.
  gasOn();
  bmeOn();

  delay(3000);  // allow powered sensor boards to settle before I2C init

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(I2C_FREQ);

  adsOK = initADS1115();
  bmeOK = initBME688();

  Serial.print("# ADS1115: ");
  Serial.println(adsOK ? "PASS" : "FAIL");

  Serial.print("# BME688: ");
  Serial.println(bmeOK ? "PASS" : "FAIL");

  if (PRINT_CSV_HEADER) {
    Serial.println("adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms");
  }
}

// ---------------- LOOP ----------------
void loop() {
  // Keep rails ON continuously.
  gasOn();
  bmeOn();

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

  // ADS1115 readings
  // PCB mapping:
  // A1 = NH3
  // A2 = CH4
  // A3 = H2S
  if (adsOK) {
    adc_NH3 = ads.readADC_SingleEnded(1);
    adc_CH4 = ads.readADC_SingleEnded(2);
    adc_H2S = ads.readADC_SingleEnded(3);

    v_NH3 = ads.computeVolts(adc_NH3);
    v_CH4 = ads.computeVolts(adc_CH4);
    v_H2S = ads.computeVolts(adc_H2S);
  }

  // BME688 readings
  if (bmeOK) {
    bme.startConvert();
    delay(BME_CONVERT_DELAY_MS);
    bme.update();

    temperature = bme.readTemperature() / 100.0;
    pressure = bme.readPressure();
    humidity = bme.readHumidity() / 1000.0;
    gasRes = bme.readGasResistance();
  }

  // Exact 10-field CSV format:
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

  delay(LOOP_DELAY_MS);
}
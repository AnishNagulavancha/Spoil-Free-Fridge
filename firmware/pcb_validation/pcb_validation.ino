#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include "DFRobot_BME68x.h"

// XIAO ESP32-S3 GPIO numbers
#define LED_PWR_PIN   1   // D0 / GPIO1, LEDs active HIGH
#define GAS_PWR_PIN   2   // D1 / GPIO2, Gas sensors active LOW
#define BME_PWR_PIN   3   // D2 / GPIO3, BME688 active LOW

#define I2C_SDA       5   // D4 / GPIO5
#define I2C_SCL       6   // D5 / GPIO6

Adafruit_ADS1115 ads;
DFRobot_BME68x_I2C bme(0x76);

bool adsOK = false;
bool bmeOK = false;

void ledsOn()  { digitalWrite(LED_PWR_PIN, HIGH); }
void ledsOff() { digitalWrite(LED_PWR_PIN, LOW); }

void gasOn()   { digitalWrite(GAS_PWR_PIN, LOW); }
void gasOff()  { digitalWrite(GAS_PWR_PIN, HIGH); }

void bmeOn()   { digitalWrite(BME_PWR_PIN, LOW); }
void bmeOff()  { digitalWrite(BME_PWR_PIN, HIGH); }

void scanI2C() {
  Serial.println("\n===== I2C SCAN =====");
  int count = 0;

  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    byte error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Found I2C device at 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
      count++;
    }
  }

  Serial.print("Total devices found: ");
  Serial.println(count);
}

bool initADS1115() {
  Serial.println("\n===== ADS1115 INIT =====");

  uint8_t addresses[] = {0x48, 0x49, 0x4A, 0x4B};

  for (int i = 0; i < 4; i++) {
    Serial.print("Trying ADS1115 at 0x");
    Serial.println(addresses[i], HEX);

    if (ads.begin(addresses[i])) {
      ads.setGain(GAIN_ONE);
      Serial.print("PASS: ADS1115 initialized at 0x");
      Serial.println(addresses[i], HEX);
      return true;
    }
  }

  Serial.println("FAIL: ADS1115 not found at 0x48/0x49/0x4A/0x4B");
  return false;
}

bool initBME688() {
  Serial.println("\n===== BME688 INIT =====");

  for (int attempt = 1; attempt <= 5; attempt++) {
    Serial.print("BME688 init attempt ");
    Serial.println(attempt);

    uint8_t rslt = bme.begin();

    if (rslt == 0) {
      Serial.println("PASS: BME688 initialized");

      bool heaterStatus = bme.setGasHeater(360, 100);
      if (heaterStatus) Serial.println("PASS: BME688 gas heater set");
      else Serial.println("FAIL: BME688 gas heater failed");

      return true;
    }

    Serial.println("BME688 begin failed, retrying...");
    delay(2000);
  }

  Serial.println("FAIL: BME688 not initialized");
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(2000);

  Serial.println("\n==============================");
  Serial.println("PCB VALIDATION FIRMWARE START");
  Serial.println("==============================");

  pinMode(LED_PWR_PIN, OUTPUT);
  pinMode(GAS_PWR_PIN, OUTPUT);
  pinMode(BME_PWR_PIN, OUTPUT);

  ledsOff();
  gasOff();
  bmeOff();

  Serial.println("Initial state: all power rails OFF");

  Serial.println("\n===== LED MOSFET TEST =====");
  Serial.println("LEDs ON for 2 seconds");
  ledsOn();
  delay(2000);
  Serial.println("LEDs OFF for 2 seconds");
  ledsOff();
  delay(2000);

  Serial.println("\n===== GAS SENSOR MOSFET TEST =====");
  Serial.println("Gas sensors ON");
  gasOn();
  delay(3000);

  Serial.println("\n===== BME688 MOSFET TEST =====");
  Serial.println("BME688 ON");
  bmeOn();
  delay(3000);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);

  scanI2C();

  adsOK = initADS1115();
  bmeOK = initBME688();

  Serial.println("\n==============================");
  Serial.println("VALIDATION SUMMARY");
  Serial.println("==============================");
  Serial.print("ADS1115: ");
  Serial.println(adsOK ? "PASS" : "FAIL");
  Serial.print("BME688: ");
  Serial.println(bmeOK ? "PASS" : "FAIL");
  Serial.println("==============================");

  Serial.println("\n===== LIVE CSV OUTPUT =====");
  Serial.println("adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms");
}

void loop() {
  gasOn();
  bmeOn();

  if (adsOK) {
    int16_t adc_NH3 = ads.readADC_SingleEnded(1);
    int16_t adc_CH4 = ads.readADC_SingleEnded(2);
    int16_t adc_H2S = ads.readADC_SingleEnded(3);

    float v_NH3 = ads.computeVolts(adc_NH3);
    float v_CH4 = ads.computeVolts(adc_CH4);
    float v_H2S = ads.computeVolts(adc_H2S);

    Serial.print(adc_NH3); Serial.print(",");
    Serial.print(v_NH3, 3); Serial.print(",");
    Serial.print(adc_CH4); Serial.print(",");
    Serial.print(v_CH4, 3); Serial.print(",");
    Serial.print(adc_H2S); Serial.print(",");
    Serial.print(v_H2S, 3); Serial.print(",");
  } else {
    Serial.print("ADS_FAIL,ADS_FAIL,ADS_FAIL,ADS_FAIL,ADS_FAIL,ADS_FAIL,");
  }

  if (bmeOK) {
    bme.startConvert();
    delay(1000);
    bme.update();

    float temperature = bme.readTemperature() / 100.0;
    float pressure = bme.readPressure();
    float humidity = bme.readHumidity() / 1000.0;
    float gasRes = bme.readGasResistance();

    Serial.print(temperature, 2); Serial.print(",");
    Serial.print(pressure, 2); Serial.print(",");
    Serial.print(humidity, 2); Serial.print(",");
    Serial.print(gasRes, 2);
  } else {
    Serial.print("BME_FAIL,BME_FAIL,BME_FAIL,BME_FAIL");
  }

  Serial.println();
  delay(1000);
}
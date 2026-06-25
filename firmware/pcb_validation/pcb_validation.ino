#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include "DFRobot_BME68x.h"

// ================= PCB PIN MAP =================
#define LED_PWR_PIN   D0   // LEDs: active HIGH
#define GAS_PWR_PIN   D1   // Gas sensors: active LOW
#define BME_PWR_PIN   D2   // BME688: active LOW

#define I2C_SDA       D4
#define I2C_SCL       D5

// ================= OBJECTS =================
Adafruit_ADS1115 ads;
DFRobot_BME68x_I2C bme(0x76);

// ================= POWER HELPERS =================
void ledsOn()  { digitalWrite(LED_PWR_PIN, HIGH); }
void ledsOff() { digitalWrite(LED_PWR_PIN, LOW); }

void gasOn()   { digitalWrite(GAS_PWR_PIN, LOW); }
void gasOff()  { digitalWrite(GAS_PWR_PIN, HIGH); }

void bmeOn()   { digitalWrite(BME_PWR_PIN, LOW); }
void bmeOff()  { digitalWrite(BME_PWR_PIN, HIGH); }

// ================= I2C SCAN =================
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

  if (count == 0) {
    Serial.println("No I2C devices found.");
  }

  Serial.print("Total devices found: ");
  Serial.println(count);
}

// ================= POWER RAIL TESTS =================
void testLEDs() {
  Serial.println("\n===== LED MOSFET TEST =====");

  Serial.println("LEDs ON for 2 seconds");
  ledsOn();
  delay(2000);

  Serial.println("LEDs OFF for 2 seconds");
  ledsOff();
  delay(2000);

  Serial.println("LED test complete");
}

void testGasPower() {
  Serial.println("\n===== GAS SENSOR MOSFET TEST =====");

  Serial.println("Gas sensors ON for 5 seconds");
  gasOn();
  delay(5000);

  Serial.println("Gas sensors OFF for 5 seconds");
  gasOff();
  delay(5000);

  Serial.println("Gas sensors ON again for readings");
  gasOn();
  delay(3000);

  Serial.println("Gas power test complete");
}

void testBMEPower() {
  Serial.println("\n===== BME688 MOSFET TEST =====");

  Serial.println("BME688 ON for 3 seconds");
  bmeOn();
  delay(3000);

  Serial.println("BME688 OFF for 3 seconds");
  bmeOff();
  delay(3000);

  Serial.println("BME688 ON again for initialization");
  bmeOn();
  delay(3000);

  Serial.println("BME688 power test complete");
}

// ================= SENSOR INIT =================
bool initADS1115() {
  Serial.println("\n===== ADS1115 INIT =====");

  if (!ads.begin(0x48)) {
    Serial.println("FAIL: ADS1115 not found at 0x48");
    return false;
  }

  ads.setGain(GAIN_ONE); // +/-4.096V range
  Serial.println("PASS: ADS1115 initialized");
  return true;
}

bool initBME688() {
  Serial.println("\n===== BME688 INIT =====");

  uint8_t rslt = 1;

  for (int attempt = 1; attempt <= 5; attempt++) {
    Serial.print("BME688 init attempt ");
    Serial.println(attempt);

    rslt = bme.begin();

    if (rslt == 0) {
      Serial.println("PASS: BME688 initialized");

      bool heaterStatus = bme.setGasHeater(360, 100);

      if (heaterStatus) {
        Serial.println("PASS: BME688 gas heater set");
      } else {
        Serial.println("FAIL: BME688 gas heater failed");
      }

      return true;
    }

    Serial.println("BME688 begin failed, retrying...");
    delay(2000);
  }

  Serial.println("FAIL: BME688 not initialized");
  return false;
}

// ================= SENSOR READINGS =================
void readADS1115() {
  int16_t adc_NH3 = ads.readADC_SingleEnded(0);
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
}

void readBME688() {
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
}

void printCSVHeader() {
  Serial.println("\n===== LIVE CSV OUTPUT =====");
  Serial.println("adc_NH3,v_NH3,adc_CH4,v_CH4,adc_H2S,v_H2S,temp_C,pressure_Pa,humidity_pct,bme_gas_ohms");
}

// ================= SETUP =================
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
  delay(1000);

  testLEDs();
  testGasPower();
  testBMEPower();

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);

  scanI2C();

  bool adsOK = initADS1115();
  bool bmeOK = initBME688();

  Serial.println("\n==============================");
  Serial.println("VALIDATION SUMMARY");
  Serial.println("==============================");

  if (adsOK) Serial.println("ADS1115: PASS");
  else       Serial.println("ADS1115: FAIL");

  if (bmeOK) Serial.println("BME688: PASS");
  else       Serial.println("BME688: FAIL");

  Serial.println("==============================");

  printCSVHeader();
}

// ================= LOOP =================
void loop() {
  gasOn();
  bmeOn();

  readADS1115();
  readBME688();

  Serial.println();

  delay(1000);
}
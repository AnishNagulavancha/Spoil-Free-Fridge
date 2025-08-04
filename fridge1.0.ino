#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include "DFRobot_BME68x.h"

Adafruit_ADS1115 ads;  // 16-bit version
DFRobot_BME68x_I2C bme(0x76);

float seaLevel; 

void setup(void) {
  uint8_t rslt = 1;
  Serial.begin(9600);
  Wire.begin(21, 22);
  if (!ads.begin()) {
    Serial.println("Failed to initialize ADS1115.");
    while (1);
  }

  while(!Serial);
  delay(1000);

  while(rslt != 0) {
    rslt = bme.begin();
    if(rslt != 0) {
      Serial.println("bme begin failure");
      delay(2000);
    }
  }
  Serial.println("bme begin successful");

  // Optional: calibrate pressure if needed
  #ifdef CALIBRATE_PRESSURE
  bme.startConvert();
  delay(1000);
  bme.update();
  seaLevel = bme.readSeaLevel(525.0); // Example altitude
  Serial.print("seaLevel :");
  Serial.println(seaLevel);
  #endif

  // Configure BME68x gas heater
  bool res = bme.setGasHeater(360, 100);
  if(res) Serial.println("Gas heater set successful!");
  else Serial.println("Gas heater set failure!");

  
}

void loop(void) {
  // --- ADS1115 gas sensor readings ---
  int16_t adc_NH3 = ads.readADC_SingleEnded(0);
  int16_t adc_CH4 = ads.readADC_SingleEnded(2);
  int16_t adc_H2S = ads.readADC_SingleEnded(3);

  float v_NH3 = ads.computeVolts(adc_NH3);
  float v_CH4 = ads.computeVolts(adc_CH4);
  float v_H2S = ads.computeVolts(adc_H2S);

  // --- BME688 readings ---
  bme.startConvert();
  delay(1000);
  bme.update();

  float temperature = bme.readTemperature() / 100.0;
  float pressure = bme.readPressure();
  float humidity = bme.readHumidity() / 1000.0;
  float gasRes = bme.readGasResistance();

  // --- CSV Output (one line per reading) ---
  Serial.print(adc_NH3); Serial.print(",");
  Serial.print(v_NH3, 3); Serial.print(",");
  Serial.print(adc_CH4); Serial.print(",");
  Serial.print(v_CH4, 3); Serial.print(",");
  Serial.print(adc_H2S); Serial.print(",");
  Serial.print(v_H2S, 3); Serial.print(",");
  Serial.print(temperature, 2); Serial.print(",");
  Serial.print(pressure, 2); Serial.print(",");
  Serial.print(humidity, 2); Serial.print(",");
  Serial.print(gasRes, 2);
  Serial.println();

  delay(1000); // 1-second interval
}

#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_BME680.h>

Adafruit_ADS1115 ads;
Adafruit_BME680 bme;

const uint8_t ADS_ADDRESS = 0x48;
const uint8_t BME_ADDRESS = 0x76;

// Change D0 to the actual GPIO number if your board does not define D0
const int CONTROL_PIN = D0;

const unsigned long RETRY_DELAY_MS = 5000;
const unsigned long READ_DELAY_MS = 1000;

bool adsConnected = false;
bool bmeConnected = false;

unsigned long previousReadTime = 0;

// Check whether an I2C address responds
bool isI2CDeviceConnected(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

bool connectADS1115() {
  Serial.println("Trying to connect to ADS1115 at 0x48...");

  if (!isI2CDeviceConnected(ADS_ADDRESS)) {
    Serial.println("ADS1115 not found.");
    return false;
  }

  if (!ads.begin(ADS_ADDRESS, &Wire)) {
    Serial.println("ADS1115 initialization failed.");
    return false;
  }

  ads.setGain(GAIN_ONE);

  Serial.println("ADS1115 connected.");
  return true;
}

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
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(CONTROL_PIN, OUTPUT);

  // Start with D0 turned off
  digitalWrite(CONTROL_PIN, LOW);

  Wire.begin();

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
}
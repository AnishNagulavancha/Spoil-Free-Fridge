#pragma once

#include "esp_err.h"
#include "driver/i2c_master.h"
#include "bme68x_defs.h"


#define MY_BME_ADDRESS 0x76
#define MY_BME_I2C_SPEED_HZ 100000
#define BME_INTERVAL_MS 10U

#define SAMPLE_COUNT UINT16_C(360)


esp_err_t bme688_init(void);
esp_err_t bme688_deinit(void);
esp_err_t bme688_read(struct bme68x_data *data);
esp_err_t bme688_power_init(void);
esp_err_t bme688_power_on(void);
esp_err_t bme688_power_off(void);

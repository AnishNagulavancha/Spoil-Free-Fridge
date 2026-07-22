#pragma once

#include "esp_err.h"
#include "driver/i2c_master.h"

#define MY_ADS1115_ADDRESS 0x48
#define MY_ADS1115_I2C_SPEED_HZ 100000
#define ADS_INTERVAL_MS 10U

esp_err_t ads_init(void);
esp_err_t ads_transmit(uint8_t channel);
esp_err_t ads_poll_config(uint16_t *config_value);
esp_err_t ads_read_raw(int16_t *ain0_value);
float ads_convert_raw(int16_t result);

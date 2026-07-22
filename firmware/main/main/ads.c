#include <driver/i2c_master.h>
#include "i2c_bus.h"
#include "ads.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

static i2c_master_dev_handle_t ads1115_handle = NULL;

static const uint8_t conversion_reg = 0x00;
static const uint8_t config_reg = 0x01;
//static const uint16_t config_reg_reset = 0x8583;

static uint8_t buffer[2];

static const uint8_t ain1[3] = {0x01, 0xD3, 0x83};
static const uint8_t ain2[3] = {0x01, 0xE3, 0x83};
static const uint8_t ain3[3] = {0x01, 0xF3, 0x83};

esp_err_t ads_init(void) 
{
    i2c_master_bus_handle_t bus_handle = i2c_bus_get_handle();

    if (bus_handle == NULL) {
    return ESP_ERR_INVALID_STATE;
    }

    if (ads1115_handle != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    i2c_device_config_t dev_cfg = {
    .dev_addr_length = I2C_ADDR_BIT_LEN_7,
    .device_address = MY_ADS1115_ADDRESS,
    .scl_speed_hz = MY_ADS1115_I2C_SPEED_HZ,
};

    
return i2c_master_bus_add_device(bus_handle, &dev_cfg, &ads1115_handle);  

}

esp_err_t ads_transmit(uint8_t channel) {

    if (ads1115_handle == NULL) {
    return ESP_ERR_INVALID_ARG;
    }

    if (channel == 1) {
        return i2c_master_transmit(ads1115_handle, ain1, sizeof(ain1), -1);
    }
    if (channel == 2) {
        return i2c_master_transmit(ads1115_handle, ain2, sizeof(ain2), -1);
    }
    if (channel == 3) {
        return i2c_master_transmit(ads1115_handle, ain3, sizeof(ain3), -1);
    }

    return ESP_ERR_INVALID_ARG;
}

esp_err_t ads_poll_config(uint16_t *config_value) {

    if (ads1115_handle == NULL || config_value == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    for (uint16_t i = 0; i < 10; i++) {
        esp_err_t result = i2c_master_transmit_receive(ads1115_handle, &config_reg, sizeof(config_reg), buffer, sizeof(buffer), -1);
        if (result != ESP_OK) {
            return result;
        }

        *config_value = ((uint16_t)buffer[0] << 8) | buffer[1];
        if ((*config_value >> 15) == 1) {
            return ESP_OK;
        }

        vTaskDelay(pdMS_TO_TICKS(ADS_INTERVAL_MS));
    }

    return ESP_ERR_TIMEOUT;
}

esp_err_t ads_read_raw(int16_t *ain1_value) {
    
    if (ads1115_handle == NULL || ain1_value == NULL) {
    return ESP_ERR_INVALID_ARG;
    }
    esp_err_t result = i2c_master_transmit_receive(ads1115_handle, &conversion_reg, sizeof(conversion_reg), buffer, sizeof(buffer), -1);
        if (result != ESP_OK) {
        return result;
    }
    *ain1_value = ((int16_t)buffer[0] << 8 | buffer[1]);
    return ESP_OK;
}

float ads_convert_raw(int16_t result) {
    
    float volt = result * 0.000125;

    return volt;
}

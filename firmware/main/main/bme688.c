#include <stdio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include <driver/gpio.h>
#include <driver/i2c_master.h>
#include "i2c_bus.h"
#include "bme688.h"

void bme688_init(void) {
    i2c_master_bus_handle_t bus = i2c_bus_get_handle();

    if (bus == NULL) {
    ESP_LOGE("BME688", "I2C bus is not initialized");
    return;
    }

}
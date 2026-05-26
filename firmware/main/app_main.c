#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/i2c_master.h"

static const char *TAG = "I2C_SCAN";

#define I2C_SDA_IO 21
#define I2C_SCL_IO 22
#define I2C_FREQ_HZ 100000

static i2c_master_bus_handle_t bus_handle;

static void i2c_init(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = I2C_SDA_IO,
        .scl_io_num = I2C_SCL_IO,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true, // external pullups preferred
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &bus_handle));
}

void app_main(void)
{
    ESP_LOGI(TAG, "Starting I2C scan on SDA=%d SCL=%d", I2C_SDA_IO, I2C_SCL_IO);

    i2c_init();

    while (1) {
        int found = 0;
        for (int addr = 1; addr < 127; addr++) {
            esp_err_t err = i2c_master_probe(bus_handle, addr, 50 / portTICK_PERIOD_MS);
            if (err == ESP_OK) {
                ESP_LOGI(TAG, "Found device at 0x%02X", addr);
                found++;
            }
        }
        if (!found) {
            ESP_LOGW(TAG, "No I2C devices found. Check wiring/pullups/power.");
        }
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}
#include <stdint.h>
#include <stdbool.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include "led.h"
#include "mems.h"
#include "ads.h"
#include "i2c_bus.h"
#include "bme688.h"
#include "camera.h"
#include "esp_camera.h"
#include "wifi.h"
#include "http.h"

#define ADS_CHANNEL_COUNT 3U
#define READ_INTERVAL_MS 1000U
#define READ_INTERVAL_MS_2 3000U
#define LOOP_DELAY_MS 5000U
#define SENSOR_POWER_STABILIZE_MS 3000U

static const char *TAG = "spoil_free_fridge";

static int16_t raw[ADS_CHANNEL_COUNT];
static float volt[ADS_CHANNEL_COUNT];

static struct bme68x_data data;
static uint16_t config_value;

void app_main(void)
{
    ESP_LOGI(TAG, "Application started");

    led_init();
    led_off();

    mems_init();
    ESP_ERROR_CHECK(bme688_power_init());

    mems_on();
    ESP_ERROR_CHECK(bme688_power_on());

    vTaskDelay(pdMS_TO_TICKS(SENSOR_POWER_STABILIZE_MS));

    ESP_ERROR_CHECK(i2c_master_init());
    ESP_ERROR_CHECK(ads_init());
    ESP_ERROR_CHECK(bme688_init());

    ESP_ERROR_CHECK(wifi_init());

#if ESP_CAMERA_SUPPORTED
    esp_err_t camera_result = init_camera();
    if (camera_result != ESP_OK) {
        ESP_LOGE(TAG, "Camera initialization failed: %s",
                 esp_err_to_name(camera_result));
        return;
    }

    httpd_handle_t server = start_webserver();
    if (server == NULL) {
        ESP_LOGE(TAG, "HTTP server failed to start");
        return;
    }

    while (1) {
        led_on();
        vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS));

        led_off();
        vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS));

        for (uint16_t i = 0; i < ADS_CHANNEL_COUNT; i++) {
            ESP_ERROR_CHECK(ads_transmit(i + 1));
            ESP_ERROR_CHECK(ads_poll_config(&config_value));
            ESP_ERROR_CHECK(ads_read_raw(&raw[i]));
            volt[i] = ads_convert_raw(raw[i]);


        }

        ESP_LOGI(TAG,
                 "ADS: NH3 raw=%d, %.3f V; CH4 raw=%d, %.3f V; H2S raw=%d, %.3f V",
                 raw[0], volt[0],
                 raw[1], volt[1],
                 raw[2], volt[2]);

        vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS_2));



        esp_err_t bme_result = bme688_read(&data);
        if (bme_result == ESP_OK) {
            bool gas_valid =
                (data.status & BME68X_GASM_VALID_MSK) != 0;
            bool heater_stable =
                (data.status & BME68X_HEAT_STAB_MSK) != 0;

            ESP_LOGI(TAG,
                     "BME688: temp=%.2f C, humidity=%.2f %%, pressure=%.2f Pa, "
                     "gas=%.0f ohm, valid=%d, heater_stable=%d",
                     data.temperature,
                     data.humidity,
                     data.pressure,
                     data.gas_resistance,
                     gas_valid,
                     heater_stable);
        } else {
            ESP_LOGE(TAG, "BME688 read failed: %s",
                     esp_err_to_name(bme_result));
        }
    }
#else
    ESP_LOGE(TAG, "Camera is not supported for this target");
#endif
}

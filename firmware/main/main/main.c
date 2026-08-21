#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
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
#include "esp_sleep.h"
#include "sensor_data.h"

#define ADS_CHANNEL_COUNT 3U
#define CYCLE_DURATION_MS          (15U * 60U * 1000U)
#define MEASUREMENT_WINDOW_MS      (3U * 60U * 1000U)
#define READ_INTERVAL_MS           2000U
#define SENSOR_POWER_STABILIZE_MS  3000U
#define GAS_INITIAL_WARMUP_MS      (3U * 60U * 1000U)

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

    ESP_ERROR_CHECK(i2c_master_init());
    ESP_ERROR_CHECK(ads_init());

    vTaskDelay(pdMS_TO_TICKS(SENSOR_POWER_STABILIZE_MS));
    ESP_ERROR_CHECK(bme688_init());
    ESP_ERROR_CHECK(sensor_data_init());

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

    vTaskDelay(pdMS_TO_TICKS(GAS_INITIAL_WARMUP_MS));

    while (1) {
        TickType_t cycle_start = xTaskGetTickCount();
        TickType_t last_read_time = xTaskGetTickCount();

        while ((xTaskGetTickCount() - cycle_start) <
               pdMS_TO_TICKS(MEASUREMENT_WINDOW_MS)) {
            for (uint16_t i = 0; i < ADS_CHANNEL_COUNT; i++) {
                ESP_ERROR_CHECK(ads_transmit(i + 1));
                ESP_ERROR_CHECK(ads_poll_config(&config_value));
                ESP_ERROR_CHECK(ads_read_raw(&raw[i]));
                volt[i] = ads_convert_raw(raw[i]);
            }

            ESP_LOGI(TAG,
                     "ADS: NH3 raw=%d, %.3f V; CH4 raw=%d, %.3f V; H2S raw=%d, %.3f V",
                     raw[0], volt[0], raw[1], volt[1], raw[2], volt[2]);

            esp_err_t bme_result = bme688_read(&data);
            if (bme_result == ESP_OK) {
                bool gas_valid =
                    (data.status & BME68X_GASM_VALID_MSK) != 0;
                bool heater_stable =
                    (data.status & BME68X_HEAT_STAB_MSK) != 0;

                ESP_LOGI(TAG,
                         "BME688: temp=%.2f C, humidity=%.2f %%, pressure=%.2f Pa, "
                         "gas=%.0f ohm, valid=%d, heater_stable=%d",
                         data.temperature, data.humidity, data.pressure,
                         data.gas_resistance, gas_valid, heater_stable);

                printf("%d,%.6f,%d,%.6f,%d,%.6f,%.2f,%.2f,%.2f,%.0f\n",
                       raw[0], volt[0], raw[1], volt[1], raw[2], volt[2],
                       data.temperature, data.pressure, data.humidity,
                       data.gas_resistance);
                fflush(stdout);

                if (gas_valid && heater_stable) {
                    sensor_record_t record = {
                        .adc_nh3 = raw[0],
                        .v_nh3 = volt[0],
                        .adc_ch4 = raw[1],
                        .v_ch4 = volt[1],
                        .adc_h2s = raw[2],
                        .v_h2s = volt[2],
                        .temperature_c = data.temperature,
                        .pressure_pa = data.pressure,
                        .humidity_pct = data.humidity,
                        .bme_gas_ohms = data.gas_resistance,
                    };
                    esp_err_t buffer_result = sensor_data_append(&record);
                    if (buffer_result != ESP_OK) {
                        ESP_LOGE(TAG, "Failed to buffer sensor record: %s",
                                 esp_err_to_name(buffer_result));
                    }
                } else {
                    ESP_LOGW(TAG,
                             "BME688 record rejected: valid=%d, heater_stable=%d",
                             gas_valid, heater_stable);
                }
            } else {
                ESP_LOGE(TAG, "BME688 read failed: %s",
                         esp_err_to_name(bme_result));
            }

            vTaskDelayUntil(&last_read_time,
                            pdMS_TO_TICKS(READ_INTERVAL_MS));
        }

        TickType_t transfer_start = xTaskGetTickCount();
        while (sensor_data_count() > 0 &&
               (xTaskGetTickCount() - transfer_start) <
                   pdMS_TO_TICKS(CONFIG_SENSOR_TRANSFER_GRACE_MS)) {
            vTaskDelay(pdMS_TO_TICKS(100));
        }
        if (sensor_data_count() > 0) {
            ESP_LOGW(TAG, "%u sensor records remain buffered for the next wake",
                     (unsigned int)sensor_data_count());
        }

        bool services_stopped = false;
        esp_err_t result = stop_webserver(server);
        if (result != ESP_OK) {
            ESP_LOGE(TAG, "HTTP server failed to stop: %s",
                     esp_err_to_name(result));
        } else {
            server = NULL;
            led_off();

            result = deinit_camera();
            if (result != ESP_OK) {
                ESP_LOGE(TAG, "Camera failed to stop: %s",
                         esp_err_to_name(result));
                return;
            }

            result = wifi_stop();
            if (result != ESP_OK) {
                ESP_LOGE(TAG, "Wi-Fi failed to stop: %s",
                         esp_err_to_name(result));
                return;
            }
            services_stopped = true;
        }

        TickType_t elapsed_ticks = xTaskGetTickCount() - cycle_start;
        TickType_t cycle_ticks = pdMS_TO_TICKS(CYCLE_DURATION_MS);

        if (elapsed_ticks < cycle_ticks) {
            TickType_t remaining_ticks = cycle_ticks - elapsed_ticks;

            if (services_stopped) {
#if CONFIG_SPOIL_FREE_ENABLE_LIGHT_SLEEP
                uint64_t remaining_us =
                    ((uint64_t)remaining_ticks * 1000000ULL) /
                    configTICK_RATE_HZ;
                result = esp_sleep_enable_timer_wakeup(remaining_us);
                if (result != ESP_OK) {
                    ESP_LOGE(TAG, "Failed to configure timer wake-up: %s",
                             esp_err_to_name(result));
                    vTaskDelay(remaining_ticks);
                } else {
                    ESP_LOGI(TAG, "Entering light sleep for %llu ms",
                             (unsigned long long)(remaining_us / 1000ULL));
                    fflush(stdout);

                    result = esp_light_sleep_start();
                    if (result != ESP_OK) {
                        ESP_LOGE(TAG, "Light sleep failed: %s",
                                 esp_err_to_name(result));
                        vTaskDelay(remaining_ticks);
                    } else {
                        ESP_LOGI(TAG, "Woke from light sleep");
                    }
                }
#else
                ESP_LOGI(TAG, "Light sleep disabled; using awake delay");
                vTaskDelay(remaining_ticks);
#endif
            } else {
                vTaskDelay(remaining_ticks);
            }
        }

        if (services_stopped) {
            result = wifi_start();
            if (result != ESP_OK) {
                ESP_LOGE(TAG, "Wi-Fi restart failed: %s",
                         esp_err_to_name(result));
                return;
            }

            result = init_camera();
            if (result != ESP_OK) {
                ESP_LOGE(TAG, "Camera restart failed: %s",
                         esp_err_to_name(result));
                return;
            }

            server = start_webserver();
            if (server == NULL) {
                ESP_LOGE(TAG, "HTTP server failed to restart");
                return;
            }
        }
    }
#else
    ESP_LOGE(TAG, "Camera is not supported for this target");
#endif
}

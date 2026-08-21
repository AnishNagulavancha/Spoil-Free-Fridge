#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <esp_log.h>
#include <nvs_flash.h>
#include <sys/param.h>
#include "esp_netif.h"
#include "esp_http_server.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_check.h"
#include <time.h>
#include <sys/time.h>
#if !CONFIG_IDF_TARGET_LINUX
#include <esp_wifi.h>
#include <esp_system.h>
#include "nvs_flash.h"
#include "led.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/timers.h"
#endif  // !CONFIG_IDF_TARGET_LINUX

#define EXAMPLE_HTTP_QUERY_KEY_MAX_LEN  (64)
#define LED_SETTLE_TIME_MS 300U
#define FRAME_SETTLE_TIME_MS 100U
#define LED_FAILSAFE_TIME_MS 2000U

#include "esp_system.h"
#include "http.h"
#include "esp_camera.h"
#include "sensor_data.h"

static const char *TAG = "HTTP_SERVER";
static TimerHandle_t led_failsafe_timer;

static void led_failsafe_callback(TimerHandle_t timer)
{
    (void)timer;
    led_off();
    ESP_LOGW(TAG, "LED safety timer switched the LEDs off");
}

static void stop_capture_leds(void)
{
    led_off();
    if (led_failsafe_timer != NULL) {
        (void)xTimerStop(led_failsafe_timer, 0);
    }
}

static esp_err_t capture_get_handler(httpd_req_t *req)
{
    ESP_LOGI(TAG, "Capture request received");
    led_on();
    if (led_failsafe_timer == NULL ||
        xTimerReset(led_failsafe_timer, 0) != pdPASS) {
        led_off();
        ESP_LOGE(TAG, "Could not start LED safety timer");
        return httpd_resp_send_500(req);
    }

    /* Let the scene and camera exposure adjust to the LEDs. */
    vTaskDelay(pdMS_TO_TICKS(LED_SETTLE_TIME_MS));

    /* Discard the first frame because it may still use the old exposure. */
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == NULL) {
        stop_capture_leds();
        ESP_LOGE(TAG, "Discard frame capture failed");
        return httpd_resp_send_500(req);
    }
    esp_camera_fb_return(fb);
    ESP_LOGI(TAG, "Discard frame returned");

    /* The camera fills its single frame buffer while the LEDs remain on. */
    vTaskDelay(pdMS_TO_TICKS(FRAME_SETTLE_TIME_MS));

    /*
     * The illuminated frame is now buffered. Switch the LEDs off before
     * obtaining it so they cannot remain on if the camera driver stalls.
     */
    stop_capture_leds();
    fb = esp_camera_fb_get();

    if (fb == NULL) {
        ESP_LOGE(TAG, "Camera capture failed");
        return httpd_resp_send_500(req);
    }
    ESP_LOGI(TAG, "JPEG frame acquired: %u bytes", (unsigned int)fb->len);

    esp_err_t result = httpd_resp_set_type(req, "image/jpeg");

    if (result == ESP_OK) {
        result = httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    }

    if (result != ESP_OK) {
        esp_camera_fb_return(fb);
        return result;
    }

    result = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);

    if (result != ESP_OK) {
        ESP_LOGE(TAG, "JPEG response failed: %s", esp_err_to_name(result));
    }

    return result;
}

static const httpd_uri_t capture = {
    .uri = "/capture",
    .method = HTTP_GET,
    .handler = capture_get_handler,
};

static esp_err_t sensor_data_get_handler(httpd_req_t *req)
{
    size_t count = sensor_data_count();
    char count_header[16];
    snprintf(count_header, sizeof(count_header), "%u", (unsigned int)count);

    esp_err_t result = httpd_resp_set_type(req, "text/csv");
    if (result == ESP_OK) {
        result = httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    }
    if (result == ESP_OK) {
        result = httpd_resp_set_hdr(req, "X-Record-Count", count_header);
    }
    if (result != ESP_OK) {
        return result;
    }

    for (size_t i = 0; i < count; i++) {
        sensor_record_t record;
        result = sensor_data_get(i, &record);
        if (result != ESP_OK) {
            return result;
        }

        char line[192];
        int length = snprintf(
            line,
            sizeof(line),
            "%d,%.6f,%d,%.6f,%d,%.6f,%.2f,%.2f,%.2f,%.0f\n",
            record.adc_nh3, record.v_nh3,
            record.adc_ch4, record.v_ch4,
            record.adc_h2s, record.v_h2s,
            record.temperature_c, record.pressure_pa,
            record.humidity_pct, record.bme_gas_ohms);

        if (length < 0 || (size_t)length >= sizeof(line)) {
            return ESP_ERR_INVALID_SIZE;
        }

        result = httpd_resp_send_chunk(req, line, (size_t)length);
        if (result != ESP_OK) {
            ESP_LOGE(TAG, "Sensor-data response failed: %s",
                     esp_err_to_name(result));
            return result;
        }
    }

    result = httpd_resp_send_chunk(req, NULL, 0);
    if (result == ESP_OK && count > 0) {
        result = sensor_data_discard(count);
        if (result == ESP_OK) {
            ESP_LOGI(TAG, "Transferred %u sensor records",
                     (unsigned int)count);
        }
    }
    return result;
}

static const httpd_uri_t sensor_data_uri = {
    .uri = "/sensor-data",
    .method = HTTP_GET,
    .handler = sensor_data_get_handler,
};


httpd_handle_t start_webserver(void)
{
    httpd_handle_t server = NULL;
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();

    if (led_failsafe_timer == NULL) {
        led_failsafe_timer = xTimerCreate(
            "capture_led_off",
            pdMS_TO_TICKS(LED_FAILSAFE_TIME_MS),
            pdFALSE,
            NULL,
            led_failsafe_callback);
        if (led_failsafe_timer == NULL) {
            ESP_LOGE(TAG, "Failed to create LED safety timer");
            return NULL;
        }
    }
#if CONFIG_IDF_TARGET_LINUX
    // Setting port as 8001 when building for Linux. Port 80 can be used only by a privileged user in linux.
    // So when a unprivileged user tries to run the application, it throws bind error and the server is not started.
    // Port 8001 can be used by an unprivileged user as well. So the application will not throw bind error and the
    // server will be started.
    config.server_port = 8001;
#endif // !CONFIG_IDF_TARGET_LINUX
    config.lru_purge_enable = true;

    // Start the httpd server
    ESP_LOGI(TAG, "Starting server on port: '%d'", config.server_port);
    if (httpd_start(&server, &config) == ESP_OK) {
        // Set URI handlers
        ESP_LOGI(TAG, "Registering URI handlers");
        if (httpd_register_uri_handler(server, &capture) != ESP_OK ||
            httpd_register_uri_handler(server, &sensor_data_uri) != ESP_OK) {
            ESP_LOGE(TAG, "Failed to register URI handlers");
            httpd_stop(server);
            return NULL;
        }
        return server;
    }


    ESP_LOGI(TAG, "Error starting server!");
    return NULL;
}

esp_err_t stop_webserver(httpd_handle_t server) {
    if (server == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t result = httpd_stop(server);

    if (result != ESP_OK) {
        return result;
    }

    ESP_LOGI(TAG, "Successfully Stopped");

    return ESP_OK;
}

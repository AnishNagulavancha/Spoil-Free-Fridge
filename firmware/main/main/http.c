#include <string.h>
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
        httpd_register_uri_handler(server, &capture);
        return server;
    }

    ESP_LOGI(TAG, "Error starting server!");
    return NULL;
}

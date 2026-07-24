#include <stdint.h>
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

// #define ADS_CHANNEL_COUNT 3U
// #define I2C_FREQUENCY_HZ 400000U
 #define READ_INTERVAL_MS 1000U

static const char *TAG = "spoil_free_fridge";
// static ads1115_t ads = {0};

static int16_t raw[3];
static float volt[3];

static struct bme68x_data data;

static uint16_t config_value;

#ifndef portTICK_RATE_MS
#define portTICK_RATE_MS portTICK_PERIOD_MS
#endif


void app_main(void)
{
	ESP_LOGI(TAG, "Application started");
	led_init();
	led_off();
	// mems_init();

	ESP_ERROR_CHECK(i2c_master_init());

	ESP_ERROR_CHECK(ads_init());

	ESP_ERROR_CHECK(bme688_init());

	#if ESP_CAMERA_SUPPORTED
    if(ESP_OK != init_camera()) {
        return;
    }

	while (1) {
		led_on();
		vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS));

		led_off();
		vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS));

		for (uint16_t i = 0; i < 3; i++) {
			ESP_ERROR_CHECK(ads_transmit(i + 1));
			ESP_ERROR_CHECK(ads_poll_config(&config_value));
			ESP_ERROR_CHECK(ads_read_raw(&raw[i]));
			volt[i] = ads_convert_raw(raw[i]);
	
		}

		bme688_read(&data);

		ESP_LOGI(TAG, "Taking picture...");
        camera_fb_t *pic = esp_camera_fb_get();

		if (pic == NULL) {
			ESP_LOGE(TAG, "Camera Capture Failed");
			led_off();
			continue;
		}

        // use pic->buf to access the image
        ESP_LOGI(TAG, "Picture taken! Its size was: %zu bytes", pic->len);
        esp_camera_fb_return(pic);

        vTaskDelay(pdMS_TO_TICKS(5000));
		
	}

#endif
}

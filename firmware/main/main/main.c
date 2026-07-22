#include <stdint.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include "led.h"
#include "mems.h"
#include "ads.h"
#include "i2c_bus.h"

// #define ADS_CHANNEL_COUNT 3U
// #define I2C_FREQUENCY_HZ 400000U
 #define READ_INTERVAL_MS 1000U

static const char *TAG = "spoil_free_fridge";
// static ads1115_t ads = {0};

static int16_t raw[3];
static float volt[3];

static uint16_t config_value;

void app_main(void)
{
	ESP_LOGI(TAG, "Application started");
	led_init();
	led_off();
	// mems_init();

	ESP_ERROR_CHECK(i2c_master_init());

	ESP_ERROR_CHECK(ads_init());



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
		
	}
}

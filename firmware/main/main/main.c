#include <stdint.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include "led.h"
#include "mems.h"
#include "ads1115.h"
#include "i2c_bus.h"

// #define ADS_CHANNEL_COUNT 3U
// #define I2C_FREQUENCY_HZ 400000U
 #define READ_INTERVAL_MS 1000U

static const char *TAG = "spoil_free_fridge";
// static ads1115_t ads = {0};

void app_main(void)
{
	ESP_LOGI(TAG, "Application started");
	led_init();
	led_off();
	// mems_init();

	// i2c_master_init();

	// i2c_master_bus_handle_t bus = i2c_bus_get_handle();

	// if (ads1115_init(&ads, &bus, ADS_I2C_ADDR_GND, I2C_FREQUENCY_HZ) != ESP_OK) {
	// 	ESP_LOGE(TAG, "ADS1115 init failed!");
	// 	return;
	// }

	// ads1115_set_gain(&ads, ADS_FSR_4_096V);
	// ads1115_set_sps(&ads, ADS_SPS_128);

	while (1) {
		led_on();
		vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS));

		led_off();
		vTaskDelay(pdMS_TO_TICKS(READ_INTERVAL_MS));
		
		// mems_on();
		// for (uint8_t channel = 0; channel < ADS_CHANNEL_COUNT; channel++) {
		// 	uint16_t raw = ads1115_get_raw(&ads, channel);
		// 	float voltage = ads1115_raw_to_voltage(&ads, (int16_t)raw);

		// 	ESP_LOGI(TAG, "Channel %u: Raw: %u | Voltage: %.4f V",
		// 		 (unsigned int)channel, (unsigned int)raw, voltage);
		// }

		
	}
}

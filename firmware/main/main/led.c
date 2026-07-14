#include <stdio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include <driver/gpio.h>
#include "led.h"

void led_init(void) 
{
    const gpio_config_t LED_conf = {
        .pin_bit_mask = (1ULL << LED_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    gpio_config(&LED_conf);
}

void led_on(void)
{
    gpio_set_level(LED_PIN, 0);
}

void led_off(void)
{
    gpio_set_level(LED_PIN, 1);
}
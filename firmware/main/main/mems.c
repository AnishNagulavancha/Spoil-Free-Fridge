#include <stdio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include <driver/gpio.h>
#include "mems.h"

void mems_init(void) 
{
    const gpio_config_t MEMS_conf = {
        .pin_bit_mask = (1ULL << MEMS_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };

    gpio_config(&MEMS_conf);
    mems_off();
}

void mems_on(void)
{
    gpio_set_level(MEMS_PIN, 0);
}

void mems_off(void)
{
    gpio_set_level(MEMS_PIN, 1);
}

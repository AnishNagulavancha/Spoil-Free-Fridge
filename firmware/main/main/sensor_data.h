#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define SENSOR_DATA_CAPACITY 384U

typedef struct {
    int16_t adc_nh3;
    float v_nh3;
    int16_t adc_ch4;
    float v_ch4;
    int16_t adc_h2s;
    float v_h2s;
    float temperature_c;
    float pressure_pa;
    float humidity_pct;
    float bme_gas_ohms;
} sensor_record_t;

esp_err_t sensor_data_init(void);
esp_err_t sensor_data_append(const sensor_record_t *record);
esp_err_t sensor_data_get(size_t index, sensor_record_t *record);
esp_err_t sensor_data_discard(size_t count);
size_t sensor_data_count(void);

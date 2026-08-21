#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "sensor_data.h"

static sensor_record_t records[SENSOR_DATA_CAPACITY];
static size_t record_count;
static SemaphoreHandle_t records_mutex;

esp_err_t sensor_data_init(void)
{
    if (records_mutex != NULL) {
        return ESP_OK;
    }

    records_mutex = xSemaphoreCreateMutex();
    return records_mutex != NULL ? ESP_OK : ESP_ERR_NO_MEM;
}

esp_err_t sensor_data_append(const sensor_record_t *record)
{
    if (record == NULL || records_mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    xSemaphoreTake(records_mutex, portMAX_DELAY);
    if (record_count >= SENSOR_DATA_CAPACITY) {
        xSemaphoreGive(records_mutex);
        return ESP_ERR_NO_MEM;
    }

    records[record_count++] = *record;
    xSemaphoreGive(records_mutex);
    return ESP_OK;
}

esp_err_t sensor_data_get(size_t index, sensor_record_t *record)
{
    if (record == NULL || records_mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    xSemaphoreTake(records_mutex, portMAX_DELAY);
    if (index >= record_count) {
        xSemaphoreGive(records_mutex);
        return ESP_ERR_NOT_FOUND;
    }

    *record = records[index];
    xSemaphoreGive(records_mutex);
    return ESP_OK;
}

esp_err_t sensor_data_discard(size_t count)
{
    if (records_mutex == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    xSemaphoreTake(records_mutex, portMAX_DELAY);
    if (count > record_count) {
        xSemaphoreGive(records_mutex);
        return ESP_ERR_INVALID_ARG;
    }

    size_t remaining = record_count - count;
    if (remaining > 0) {
        memmove(records, &records[count], remaining * sizeof(records[0]));
    }
    record_count = remaining;
    xSemaphoreGive(records_mutex);
    return ESP_OK;
}

size_t sensor_data_count(void)
{
    if (records_mutex == NULL) {
        return 0;
    }

    xSemaphoreTake(records_mutex, portMAX_DELAY);
    size_t count = record_count;
    xSemaphoreGive(records_mutex);
    return count;
}

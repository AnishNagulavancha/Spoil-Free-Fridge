#include <stdio.h>
#include <esp_log.h>
#include <esp_rom_sys.h>
#include <driver/gpio.h>
#include <driver/i2c_master.h>
#include "i2c_bus.h"
#include "bme688.h"
#include "bme68x.h"
#include "bme68x_defs.h"

static i2c_master_dev_handle_t bme688_handle = NULL;
static struct bme68x_dev bme;
static struct bme68x_conf conf;
static struct bme68x_heatr_conf heater_conf;
static const char *TAG = "BME688";

#define BME688_POWER_PIN GPIO_NUM_3

esp_err_t bme688_power_init(void) {
    const gpio_config_t power_config = {
        .pin_bit_mask = (1ULL << BME688_POWER_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    esp_err_t result = gpio_config(&power_config);
    if (result != ESP_OK) {
        return result;
    }

    return bme688_power_off();
}

esp_err_t bme688_power_on(void) {
    return gpio_set_level(BME688_POWER_PIN, 0);
}

esp_err_t bme688_power_off(void) {
    return gpio_set_level(BME688_POWER_PIN, 1);
}

static int8_t bme_read(uint8_t reg_addr, uint8_t *reg_data, uint32_t length, void *intf_ptr) {
    i2c_master_dev_handle_t handle = (i2c_master_dev_handle_t)intf_ptr;

    if (handle == NULL || reg_data == NULL) {
        return INT8_C(-1);
    }

    esp_err_t result = i2c_master_transmit_receive(
        handle,
        &reg_addr,
        sizeof(reg_addr),
        reg_data,
        length,
        -1);

    if (result != ESP_OK) {
        return INT8_C(-1);
    }

    return BME68X_INTF_RET_SUCCESS;


}

static int8_t bme_write(uint8_t reg_addr, const uint8_t *reg_data, uint32_t length, void *intf_ptr) {
    i2c_master_dev_handle_t handle = (i2c_master_dev_handle_t)intf_ptr;

    if (handle == NULL || reg_data == NULL ||
        length > (BME68X_LEN_INTERLEAVE_BUFF - 1)) {
        return INT8_C(-1);
    }

    uint8_t buffer[BME68X_LEN_INTERLEAVE_BUFF];
    buffer[0] = reg_addr;

    for (uint32_t i = 0; i < length; i++) {
        buffer[i + 1] = reg_data[i];
    }

    esp_err_t result = i2c_master_transmit(
        handle,
        buffer,
        length + 1,
        -1);

    if (result != ESP_OK) {
        return INT8_C(-1);
    }

    return BME68X_INTF_RET_SUCCESS;
}

static void bme_delay_us(uint32_t period, void *intf_ptr) {
    (void)intf_ptr;
    esp_rom_delay_us(period);
}

esp_err_t bme688_init(void) {
    i2c_master_bus_handle_t bus_handle = i2c_bus_get_handle();

    if (bus_handle == NULL || bme688_handle != NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = MY_BME_ADDRESS,
        .scl_speed_hz = MY_BME_I2C_SPEED_HZ,
    };

    esp_err_t result =
        i2c_master_bus_add_device(bus_handle, &dev_cfg, &bme688_handle);
    if (result != ESP_OK) {
        return result;
    }

    bme = (struct bme68x_dev){ 0 };
    bme.read = bme_read;
    bme.write = bme_write;
    bme.delay_us = bme_delay_us;
    bme.intf = BME68X_I2C_INTF;
    bme.intf_ptr = bme688_handle;
    bme.amb_temp = 25;

    int8_t bme_result = bme68x_init(&bme);
    if (bme_result != BME68X_OK) {
        ESP_LOGE(TAG, "Bosch initialization failed: %d", bme_result);
        (void)i2c_master_bus_rm_device(bme688_handle);
        bme688_handle = NULL;
        return ESP_FAIL;
    }

    conf = (struct bme68x_conf) { 0 };

    conf.filter = BME68X_FILTER_OFF;
    conf.odr = BME68X_ODR_NONE;
    conf.os_hum = BME68X_OS_16X;
    conf.os_pres = BME68X_OS_1X;
    conf.os_temp = BME68X_OS_2X;

    bme_result = bme68x_set_conf(&conf, &bme);
    if (bme_result != BME68X_OK) {
        ESP_LOGE(TAG, "Bosch sensor configuration failed: %d", bme_result);
        (void)i2c_master_bus_rm_device(bme688_handle);
        bme688_handle = NULL;
        return ESP_FAIL;
    }


    heater_conf = (struct bme68x_heatr_conf) { 0 };

    heater_conf.enable = BME68X_ENABLE;
    heater_conf.heatr_temp = 360;
    heater_conf.heatr_dur = 100;

    bme_result = bme68x_set_heatr_conf(BME68X_FORCED_MODE, &heater_conf, &bme);
    if (bme_result != BME68X_OK) {
        ESP_LOGE(TAG, "Bosch heater configuration failed: %d", bme_result);
        (void)i2c_master_bus_rm_device(bme688_handle);
        bme688_handle = NULL;
        return ESP_FAIL;
    }

    
    return ESP_OK;
}

esp_err_t bme688_deinit(void) {
    if (bme688_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t result = i2c_master_bus_rm_device(bme688_handle);
    if (result != ESP_OK) {
        return result;
    }

    bme688_handle = NULL;
    bme = (struct bme68x_dev){ 0 };
    conf = (struct bme68x_conf){ 0 };
    heater_conf = (struct bme68x_heatr_conf){ 0 };

    return ESP_OK;
}

esp_err_t bme688_read(struct bme68x_data *data) {
    if (bme688_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    if (data == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    int8_t bme688_result = bme68x_set_op_mode(BME68X_FORCED_MODE, &bme);
    if (bme688_result != BME68X_OK) {
        ESP_LOGE(TAG, "Bosch forced-mode start failed: %d", bme688_result);
        return ESP_FAIL;
    }

    uint32_t period = bme68x_get_meas_dur(BME68X_FORCED_MODE, &conf, &bme) + (heater_conf.heatr_dur * 1000);
    bme.delay_us(period, bme.intf_ptr);

    *data = (struct bme68x_data){ 0 };
    uint8_t n_fields = 0;

    bme688_result = bme68x_get_data(BME68X_FORCED_MODE, data, &n_fields, &bme);

    if (bme688_result != BME68X_OK) {
        ESP_LOGE(TAG, "Bosch data retrieval failed: %d", bme688_result);
        return ESP_FAIL;
    }

    if (n_fields == 0) {
        ESP_LOGW(TAG, "No BME688 measurement returned");
        return ESP_FAIL;
    }

    return ESP_OK;
}

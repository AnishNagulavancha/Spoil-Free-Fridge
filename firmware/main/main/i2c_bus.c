#include <stdio.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_log.h>
#include <driver/gpio.h>
#include <driver/i2c_master.h>
#include "i2c_bus.h"

static i2c_master_bus_handle_t bus_handle = NULL;

void i2c_master_init(void) 
{
    i2c_master_bus_config_t i2c_mst_config = {
    .clk_source = I2C_CLK_SRC_DEFAULT,
    .i2c_port = I2C_MASTER_PORT,
    .scl_io_num = I2C_MASTER_SCL_IO,
    .sda_io_num = I2C_MASTER_SDA_IO,
    .glitch_ignore_cnt = 7,
    .flags.enable_internal_pullup = true,
};

ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config, &bus_handle));

}

i2c_master_bus_handle_t i2c_bus_get_handle(void)
{
    return bus_handle;
}
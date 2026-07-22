#pragma once

#include <driver/i2c_master.h>
#define I2C_MASTER_PORT I2C_NUM_0
#define I2C_MASTER_SDA_IO GPIO_NUM_5
#define I2C_MASTER_SCL_IO GPIO_NUM_6

void i2c_master_init(void);
i2c_master_bus_handle_t i2c_bus_get_handle(void);
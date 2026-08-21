#pragma once

#include "esp_err.h"

esp_err_t wifi_init(void);
esp_err_t wifi_start(void);
esp_err_t wifi_stop(void);
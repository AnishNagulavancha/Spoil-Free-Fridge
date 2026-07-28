idf_component_register(SRCS "http.c" "camera.c" "ads.c" "i2c_bus.c" "main.c" "led.c" "mems.c" "bme688.c" "wifi.c"
                       INCLUDE_DIRS "." 
                       REQUIRES esp_driver_gpio esp_driver_i2c bme68x esp_rom nvs_flash esp_psram esp_wifi esp_netif esp_event esp-tls esp_http_server
                       )

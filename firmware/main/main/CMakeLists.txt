idf_component_register(SRCS "camera.c" "ads.c" "i2c_bus.c" "main.c" "led.c" "mems.c" "bme688.c"
                       INCLUDE_DIRS "." 
                       REQUIRES esp_driver_gpio esp_driver_i2c bme68x esp_rom nvs_flash esp_psram
                       )

# Spoil-Free-Fridge
This project is a battery-powered, sensor-based system designed to detect early signs of food spoilage in refrigerators by monitoring the release of specific gases. It uses dedicated gas sensors (specifically, hydrogen sulfide, ammonia, and methane) along with an environmental sensor (BME688) to track changes in air composition over time.

The collected data is transmitted to a PC over Wi-Fi using an ESP32-WROOM microcontroller. A machine learning model, trained on labeled gas profiles of different food states, will follow a multi-classification approach by being able to recongize food type, food item, and finally the freshness level as fresh, spoiling, or spoiled.

The system is optimized for low power consumption, designed to operate off batteries, and intended for eventual deployment inside consumer refrigerators as a compact, standalone freshness detection unit.

Currently, the prototype of the system has been built on a breadboard. Initially, we will see if the prototype is accurate enough to work in normal conditions before moving to a fridge

The inspiration of this projetc came out my own laziness of postponing when I would cook my own meals leading to food spoiling in the fridge.

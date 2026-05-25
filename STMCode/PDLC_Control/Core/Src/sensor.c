/*
 * sensor.c
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */

#include "sensor.h"

#define BH1750_ADDR 0x46

volatile float current_lux = 0.0f;
uint32_t last_lux_read_tick = 0;

void BH1750_Init(I2C_HandleTypeDef *hi2c)
{
    uint8_t init_cmd = 0x10;
    HAL_I2C_Master_Transmit(hi2c, BH1750_ADDR, &init_cmd, 1, 100);
}

// Returns 1 if a new reading was processed, 0 if still waiting
uint8_t BH1750_Read_NonBlocking(I2C_HandleTypeDef *hi2c)
{
    uint32_t current_tick = HAL_GetTick();

    if (current_tick - last_lux_read_tick >= 200)
    {
        last_lux_read_tick = current_tick;
        uint8_t data_buffer[2];

        if (HAL_I2C_Master_Receive(hi2c, BH1750_ADDR, data_buffer, 2, 10) == HAL_OK)
        {
            uint16_t raw_light = (data_buffer[0] << 8) | data_buffer[1];
            float new_lux_reading = (float)raw_light / 1.2f;

            if (current_lux == 0.0f) {
                current_lux = new_lux_reading;
            } else {
                current_lux = (current_lux * 0.8f) + (new_lux_reading * 0.2f);
            }
        }
        else
        {
            current_lux = -1.0f; // SENSOR ERROR
        }
        return 1; // True: New data is ready
    }
    return 0; // False: Waiting for timer
}

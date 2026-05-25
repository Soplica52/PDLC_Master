/*
 * sensor.h
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */

#ifndef SENSOR_H
#define SENSOR_H

#include "main.h"

#define BH1750_ADDR 0x46

// Expose the current lux reading to the rest of the program
extern volatile float current_lux;

void BH1750_Init(I2C_HandleTypeDef *hi2c);
uint8_t BH1750_Read_NonBlocking(I2C_HandleTypeDef *hi2c);

#endif // SENSOR_H

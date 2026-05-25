/*
 * control_algos.h
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */

#ifndef INC_CONTROL_ALGOS_H_
#define INC_CONTROL_ALGOS_H_

#include "main.h"

// --- Variables accessed by main.c (UART & Printf) ---
extern volatile uint8_t system_mode;
extern volatile float target_lux;
extern volatile float target_led_brightness;
extern float master_integral;

// --- Function Prototypes ---
void Calculate_Master_PI_Controller(void);
void Update_LED_Brightness(void);

#endif // CONTROL_ALGOS_H

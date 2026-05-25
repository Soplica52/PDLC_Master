/*
 * control_algos.c
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */
#include "control_algos.h"
#include "sensor.h"       // Gives access to current_lux
#include "pdlc_foil.h"    // Gives access to target_rms_voltage & PDLC map
#include <math.h>         // Gives access to fabs()

// Give this file access to htim2 from main.c so we don't have to change your function signature!
extern TIM_HandleTypeDef htim2;

// --- SYSTEM MODE ---
volatile uint8_t system_mode = 1; // 1 = AUTO, 0 = MANUAL

// --- LED STRIP (0-10V PWM) VARIABLES ---
volatile float target_led_brightness = 0.0f;

// --- MASTER PI CONTROLLER VARIABLES (FOIL + LED) ---
volatile float target_lux = 1000.0f; // The exact value you want to achieve
float led_spike_buffer = 150.0f;    // How many "extra" Lux to ignore to prevent LED oscillation
float Kp_master = 0.05f;
float Ki_master = 0.005f;
float master_integral = 0.0f;

// THE NEW "CONDITIONAL DEADBAND" PI CONTROLLER
void Calculate_Master_PI_Controller(void)
{
    if (system_mode == 0) return;

    float error = target_lux - current_lux;

    // --------------------------------------------------------
    // STRICT DEADBAND ONLY
    // --------------------------------------------------------
    // Both the Foil and the LED must now hit the target within +/- 5 Lux.
    // WARNING: This will cause massive LED oscillation due to the physical 10% jump!
    if (fabs(error) < 5.0f) {
        error = 0.0f;
    }

    master_integral += error * Ki_master;
    if (master_integral > 200.0f) master_integral = 200.0f;
    if (master_integral < 0.0f) master_integral = 0.0f;

    float P = error * Kp_master;
    float control_effort = P + master_integral;

    if (control_effort > 200.0f) control_effort = 200.0f;
    if (control_effort < 0.0f) control_effort = 0.0f;

    if (control_effort <= 100.0f)
    {
        int index = (int)(control_effort / 10.0f);

        if (index >= 10) {
            target_rms_voltage = PDLC_VOLTAGE_MAP[10];
        } else {
            float remainder = (control_effort - (index * 10.0f)) / 10.0f;
            target_rms_voltage = PDLC_VOLTAGE_MAP[index] + remainder * (PDLC_VOLTAGE_MAP[index+1] - PDLC_VOLTAGE_MAP[index]);
        }
        target_led_brightness = 0.0f;
    }
    else
    {
        target_rms_voltage = 10.0f;
        target_led_brightness = 10.0f + ((control_effort - 100.0f) * 0.9f);
    }
}

void Update_LED_Brightness(void)
{
    // Simple safety bounds
    if (target_led_brightness > 100.0f) target_led_brightness = 100.0f;
    if (target_led_brightness < 0.0f) target_led_brightness = 0.0f;

    // Convert percentage to 0-1000 Timer format
    uint32_t pwm_register_value = (uint32_t)(target_led_brightness * 10.0f);
    __HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, pwm_register_value);
}


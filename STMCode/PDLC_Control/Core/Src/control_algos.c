/*
 * control_algos.c
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */
#include "control_algos.h"
#include "sensor.h"       // Gives access to current_lux
#include "pdlc_foil.h"    // Gives access to target_rms_voltage & PDLC map
#include "main.h"
#include <math.h>         // Gives access to fabs()

// Give this file access to htim2 from main.c so we don't have to change your function signature!
extern TIM_HandleTypeDef htim2;

// --- SYSTEM MODE ---
volatile uint8_t system_mode = 1; // 1 = AUTO, 0 = MANUAL

// --- LED STRIP (0-10V PWM) VARIABLES ---
volatile float target_led_brightness = 0.0f;

// --- MASTER PI CONTROLLER VARIABLES (FOIL + LED) ---
volatile float target_lux = 500.0f; // The exact value you want to achieve
float led_spike_buffer = 150.0f;    // How many "extra" Lux to ignore to prevent LED oscillation
float Kp_master = 0.05f;
float Ki_master = 0.005f;
float master_integral = 0.0f;

// --- NEW: DWELL TIME VARIABLES ---
uint32_t last_switch_tick = 0;
uint8_t led_was_on = 0;
uint32_t switch_delay_ms = 10000; // 10 SECONDS (Adjust this to whatever you want!)

void Calculate_Master_PI_Controller(void)
{
    if (system_mode == 0) return;

    float error = target_lux - current_lux;

    // --------------------------------------------------------
    // 1. THE DWELL TIME TRACKER
    // --------------------------------------------------------
    // Check if the LED just turned on, or just turned off.
    uint8_t led_is_on = (target_led_brightness > 0.0f) ? 1 : 0;
    if (led_is_on != led_was_on)
    {
        last_switch_tick = HAL_GetTick(); // Record the exact millisecond it switched
        led_was_on = led_is_on;
    }

    // Check if we are still inside the 10-second "Lockout" window
    uint8_t lockout_active = (HAL_GetTick() - last_switch_tick < switch_delay_ms) ? 1 : 0;

    // --------------------------------------------------------
    // 2. THE "HANDOVER" HYSTERESIS (Lux Lock + Time Lock)
    // --------------------------------------------------------
    if (master_integral >= 95.0f || target_led_brightness > 0.0f)
        {
            if (target_led_brightness == 0.0f)
            {
                // CONDITION 1: Foil is maxed, trying to turn LEDs ON.
                // YES! The 150 Lux boundary is still right here.
                if ((error > 0.0f && error <= 150.0f) || (lockout_active == 1 && error > 0.0f)) {
                    error = 0.0f; // Freeze.
                }
            }
            else if (target_led_brightness > 0.0f && target_led_brightness <= 25.0f)
            {
                // CONDITION 2: LEDs are ON, trying to shut them OFF.
                // WIDENED NET (25%): Catches the P-term punch.
                // YES! The -150 Lux boundary is still right here.
                if ((error < 0.0f && error >= -150.0f) || (lockout_active == 1 && error < 0.0f)) {
                    error = 0.0f; // Freeze.
                }
            }
        }
        else
        {
            // Foil Modulation Zone
            if (fabs(error) < 5.0f) {
                error = 0.0f;
            }
        }

    // --------------------------------------------------------
    // 3. MATH & ROUTING
    // --------------------------------------------------------
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


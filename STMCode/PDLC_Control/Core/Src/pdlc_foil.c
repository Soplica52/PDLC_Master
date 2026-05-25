/*
 * pdlc_foil.c
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */

#include "pdlc_foil.h"

volatile uint8_t phase_degrees = 175; // Starts safely OFF
volatile uint8_t missed_zc_count = 0; // Tracks how many times we predicted the wave

// SHADOW VARIABLE FIX: Safely stores the timer delay until the zero-cross happens
volatile uint32_t active_delay_us = 9500;

// --- OPEN-LOOP LOOKUP TABLE VARIABLES (AC DIMMER) ---
volatile float target_rms_voltage = 12.0f;

const uint8_t LUT_ANGLES[LUT_SIZE] = {5, 45, 90, 120, 135, 145, 155, 160, 165, 170, 175};
const float LUT_VOLTAGES[LUT_SIZE] = {
    22.8f, 20.0f, 17.0f, 11.3f, 7.68f, 5.5f, 3.5f, 2.7f, 1.9f, 1.25f, 1.0f
};

// --- PDLC FOIL LINEARIZATION MAP ---
// Maps 0-100% Control Effort to the exact voltage needed for a linear visual transition.
// Derived from MATLAB data: 0%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%, 100% clear
const float PDLC_VOLTAGE_MAP[11] = {0.0f, 2.4f, 3.1f, 3.5f, 3.9f, 4.2f, 4.6f, 5.0f, 5.4f, 6.5f, 10.0f};

// ALLOWS MANUAL FOIL CONTROL USING YOUR MATLAB MAP
void Set_Manual_Foil_Pct(float pct)
{
    if (pct > 100.0f) pct = 100.0f;
    if (pct < 0.0f) pct = 0.0f;

    int index = (int)(pct / 10.0f);

    if (index >= 10) {
        target_rms_voltage = PDLC_VOLTAGE_MAP[10];
    } else {
        float remainder = (pct - (index * 10.0f)) / 10.0f;
        target_rms_voltage = PDLC_VOLTAGE_MAP[index] + remainder * (PDLC_VOLTAGE_MAP[index+1] - PDLC_VOLTAGE_MAP[index]);
    }
}

void Update_Angle_From_LUT(void)
{
    if (target_rms_voltage >= LUT_VOLTAGES[0]) {
        phase_degrees = LUT_ANGLES[0];
    }
    else if (target_rms_voltage <= LUT_VOLTAGES[LUT_SIZE - 1]) {
        phase_degrees = 180;
    }
    else
    {
        for (int i = 0; i < LUT_SIZE - 1; i++)
        {
            if (target_rms_voltage <= LUT_VOLTAGES[i] && target_rms_voltage >= LUT_VOLTAGES[i+1])
            {
                float v_high = LUT_VOLTAGES[i];
                float v_low = LUT_VOLTAGES[i+1];
                float a_low_val = (float)LUT_ANGLES[i];
                float a_high_val = (float)LUT_ANGLES[i+1];

                float ratio = (v_high - target_rms_voltage) / (v_high - v_low);
                float calculated_angle = a_low_val + (ratio * (a_high_val - a_low_val));

                phase_degrees = (uint8_t)calculated_angle;
                break; // Exit loop once found
            }
        }
    }

    // --- UPDATE THE METRONOME TRIPWIRE ---
    // (50Hz Grid = 10,000us half-wave)
    uint32_t delay_us = ((uint32_t)phase_degrees * 10000) / 180;
    if(delay_us < 500) delay_us = 500;
    if(delay_us > 9500) delay_us = 9500;

    if(phase_degrees >= 180) { delay_us = 10001; }

    // TIMING FIX: Save to shadow variable, do NOT update timer asynchronously!
    active_delay_us = delay_us;
}

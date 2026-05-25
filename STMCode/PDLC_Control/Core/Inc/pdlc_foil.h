/*
 * pdlc_foil.h
 *
 *  Created on: May 25, 2026
 *      Author: Konrad
 */

#ifndef INC_PDLC_FOIL_H_
#define INC_PDLC_FOIL_H_



#include "main.h"

#define LUT_SIZE 11

// --- Variables accessed by main.c Interrupts & Control Algos ---
extern volatile uint8_t phase_degrees;
extern volatile uint8_t missed_zc_count;
extern volatile uint32_t active_delay_us;
extern volatile float target_rms_voltage;

// --- Expose the voltage map so the PI controller can use it ---
extern const float PDLC_VOLTAGE_MAP[11];

// --- Function Prototypes ---
void Set_Manual_Foil_Pct(float pct);
void Update_Angle_From_LUT(void);

#endif // PDLC_FOIL_H

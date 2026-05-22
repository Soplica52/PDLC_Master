/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <math.h>
#include <stdio.h>
#include <string.h> // Added for UART string parsing (strncmp)
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define LUT_SIZE 11
#define BH1750_ADDR 0x46
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;

UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
volatile uint8_t phase_degrees = 175; // Starts safely OFF
volatile uint8_t missed_zc_count = 0; // Tracks how many times we predicted the wave

// SHADOW VARIABLE FIX: Safely stores the timer delay until the zero-cross happens
volatile uint32_t active_delay_us = 9500;

// --- SYSTEM MODE ---
volatile uint8_t system_mode = 1; // 1 = AUTO, 0 = MANUAL

// --- OPEN-LOOP LOOKUP TABLE VARIABLES (AC DIMMER) ---
volatile float target_rms_voltage = 12.0f;
float last_target_rms = -1.0f;

const uint8_t LUT_ANGLES[LUT_SIZE] = {5, 45, 90, 120, 135, 145, 155, 160, 165, 170, 175};
const float LUT_VOLTAGES[LUT_SIZE] = {
    22.8f, 20.0f, 17.0f, 11.3f, 7.68f, 5.5f, 3.5f, 2.7f, 1.9f, 1.25f, 1.0f
};

// --- PDLC FOIL LINEARIZATION MAP ---
// Maps 0-100% Control Effort to the exact voltage needed for a linear visual transition.
// Derived from MATLAB data: 0%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%, 100% clear
const float PDLC_VOLTAGE_MAP[11] = {0.0f, 2.4f, 3.1f, 3.5f, 3.9f, 4.2f, 4.6f, 5.0f, 5.4f, 6.5f, 10.0f};

// --- AMBIENT LIGHT SENSOR (BH1750) VARIABLES ---
volatile float current_lux = 0.0f;
uint32_t last_lux_read_tick = 0;

// --- LED STRIP (0-10V PWM) VARIABLES ---
volatile float target_led_brightness = 0.0f;
float last_led_brightness = -1.0f;

// --- MASTER PI CONTROLLER VARIABLES (FOIL + LED) ---
volatile float target_lux = 500.0f;
float Kp_master = 0.05f;  // Reacts gently to sudden shadows.
float Ki_master = 0.005f; // Builds up very slowly over time.
float master_integral = 0.0f;

// --- UART RECEIVE VARIABLES ---
uint8_t rx_byte;        // Holds the single incoming character
char rx_buffer[20];     // Builds the full message string
uint8_t rx_index = 0;   // Tracks our position in the buffer
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM3_Init(void);
static void MX_TIM2_Init(void);
static void MX_I2C1_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
int _write(int file, char *ptr, int len)
{
    HAL_UART_Transmit(&huart2, (uint8_t*)ptr, len, HAL_MAX_DELAY);
    return len;
}

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

// THE NEW SPLIT-RANGE PI CONTROLLER (WITH STATE MACHINE & FOIL LINEARIZATION)
void Calculate_Master_PI_Controller(void)
{
    // If we are in manual mode, bypass the automatic control entirely!
    if (system_mode == 0) {
        return;
    }

    float error = target_lux - current_lux;
    master_integral += error * Ki_master;

    if (master_integral > 200.0f) master_integral = 200.0f;
    if (master_integral < 0.0f) master_integral = 0.0f;

    float P = error * Kp_master;
    float control_effort = P + master_integral;

    if (control_effort > 200.0f) control_effort = 200.0f;
    if (control_effort < 0.0f) control_effort = 0.0f;

    // --------------------------------------------------------
    // 5. SPLIT-RANGE ROUTING & LINEARIZATION
    // --------------------------------------------------------
    if (control_effort <= 100.0f)
        {
            // STAGE 1 (0-100): Modulate the PDLC Foil using the exact MATLAB curve
            int index = (int)(control_effort / 10.0f);

            if (index >= 10) {
                target_rms_voltage = PDLC_VOLTAGE_MAP[10];
            } else {
                float remainder = (control_effort - (index * 10.0f)) / 10.0f;
                target_rms_voltage = PDLC_VOLTAGE_MAP[index] + remainder * (PDLC_VOLTAGE_MAP[index+1] - PDLC_VOLTAGE_MAP[index]);
            }

            target_led_brightness = 0.0f; // LEDs strictly OFF
        }
        else
        {
            // STAGE 2 (100-200): Foil is locked at Max Transparency.
            target_rms_voltage = 10.0f;

            // --- NEW: LED LINEARIZATION ---
            // We map the 100-200 effort range to the physical 10-100% LED range.
            // This completely skips the dead 1-9% zone!
            target_led_brightness = 10.0f + ((control_effort - 100.0f) * 0.9f);
    }
}

void BH1750_Init(void)
{
    // Command 0x10 = Continuously H-Resolution Mode
    // Resolution: 1 lux. Measurement time: ~120ms.
    uint8_t init_cmd = 0x10;
    HAL_I2C_Master_Transmit(&hi2c1, BH1750_ADDR, &init_cmd, 1, 100);
}

void BH1750_Read_NonBlocking(void)
{
    uint32_t current_tick = HAL_GetTick();

    if (current_tick - last_lux_read_tick >= 200)
    {
        last_lux_read_tick = current_tick;
        uint8_t data_buffer[2];

        // 1. Try to read the sensor
        if (HAL_I2C_Master_Receive(&hi2c1, BH1750_ADDR, data_buffer, 2, 10) == HAL_OK)
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
            // SENSOR ERROR: Set to -1 so we can see the hardware failure on the UI!
            current_lux = -1.0f;
        }

        // 2. ALWAYS run the controller and print JSON, even if sensor fails
        Calculate_Master_PI_Controller();

        int total_tenths = (int)roundf(target_rms_voltage * 10.0f);
        int foil_whole = total_tenths / 10;
        int foil_decimal = total_tenths % 10;

        printf("{\"lux\": %d, \"target\": %d, \"effort\": %d, \"foil_v\": %d.%d, \"led_pct\": %d}\n",
              (int)current_lux,
              (int)target_lux,
              (int)master_integral,
              foil_whole, foil_decimal,
              (int)target_led_brightness);

        // Force the STM32 to flush the UART buffer immediately
        fflush(stdout);
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

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* MCU Configuration--------------------------------------------------------*/
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_TIM3_Init();
  MX_TIM2_Init();
  MX_I2C1_Init();
  MX_USART2_UART_Init();

  /* USER CODE BEGIN 2 */
  htim3.Instance->PSC = (SystemCoreClock / 1000000) - 1;

  HAL_TIM_Base_Start_IT(&htim3);
  HAL_TIM_OC_Start_IT(&htim3, TIM_CHANNEL_1);

  HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1);
  BH1750_Init();

  HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
      if (target_rms_voltage != last_target_rms)
      {
          Update_Angle_From_LUT();
          last_target_rms = target_rms_voltage;
      }

      if (target_led_brightness != last_led_brightness)
      {
          Update_LED_Brightness();
          last_led_brightness = target_led_brightness;
      }

      // Check the sensor (and run the master controller) every 200ms
      BH1750_Read_NonBlocking();

    /* USER CODE END WHILE */
  }
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSIDiv = RCC_HSI_DIV1;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{
  hi2c1.Instance = I2C1;
  hi2c1.Init.Timing = 0x00503D58;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.OwnAddress2Masks = I2C_OA2_NOMASK;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Analogue filter
  */
  if (HAL_I2CEx_ConfigAnalogFilter(&hi2c1, I2C_ANALOGFILTER_ENABLE) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Digital filter
  */
  if (HAL_I2CEx_ConfigDigitalFilter(&hi2c1, 0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{
  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 0;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 1000;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  HAL_TIM_MspPostInit(&htim2);
}

/**
  * @brief TIM3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{
  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 0;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 65535;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  huart2.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  huart2.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  huart2.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetTxFifoThreshold(&huart2, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetRxFifoThreshold(&huart2, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_DisableFifoMode(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, LED_GREEN_Pin|GPIO_PIN_9, GPIO_PIN_RESET);

  /*Configure GPIO pins : LED_GREEN_Pin PA9 */
  GPIO_InitStruct.Pin = LED_GREEN_Pin|GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pin : Zero_Cross_Detector_Pin */
  GPIO_InitStruct.Pin = Zero_Cross_Detector_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(Zero_Cross_Detector_GPIO_Port, &GPIO_InitStruct);

  /* EXTI interrupt init*/
  HAL_NVIC_SetPriority(EXTI4_15_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(EXTI4_15_IRQn);
}

/* USER CODE BEGIN 4 */

void HAL_GPIO_EXTI_Rising_Callback(uint16_t GPIO_Pin)
{
    if(GPIO_Pin == Zero_Cross_Detector_Pin)
    {
        // We got a real zero-cross! Sync the timer to reality.
        __HAL_TIM_SET_COUNTER(&htim3, 0);

        // TIMING FIX: Update the compare register ONLY at zero-cross
        __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, active_delay_us);

        missed_zc_count = 0; // Reset our safety counter
    }
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if(htim->Instance == TIM3)
    {
        // If the timer rolls over naturally, it means the hardware ZCD missed the pulse.
        // We just "predicted" a zero cross!
        missed_zc_count++;

        // Safety cutoff: If we miss more than 3 real zero-crossings in a row,
        // the AC grid power might actually be off.
        if(missed_zc_count > 3)
        {
            missed_zc_count = 4; // Prevent variable overflow
        }
    }
}

void HAL_TIM_OC_DelayElapsedCallback(TIM_HandleTypeDef *htim)
{
    if(htim->Instance == TIM3 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1)
    {
        // Only fire if the angle is valid AND we haven't lost grid power (missed <= 3)
        if(phase_degrees < 180 && missed_zc_count <= 3)
        {
            // Execute the 3-pulse train to guarantee latching
            for(int p = 0; p < 3; p++)
            {
                HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_SET);
                // INTERRUPT FIX: Shrunk from 500 to 50 iterations so UART isn't choked
                for(volatile int i=0; i<50; i++);

                HAL_GPIO_WritePin(GPIOA, GPIO_PIN_9, GPIO_PIN_RESET);
                for(volatile int i=0; i<50; i++);
            }
        }
    }
}

// ORE (OVERRUN ERROR) RECOVERY FIX:
// Automatically restart the UART receiver if bytes crash into each other
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        __HAL_UART_CLEAR_OREFLAG(huart);
        __HAL_UART_CLEAR_NEFLAG(huart);
        __HAL_UART_CLEAR_FEFLAG(huart);
        HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
    }
}

// --- FULL UART COMMAND PARSER ---
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2)
    {
        // If we received an "Enter" key (newline or carriage return)
        if (rx_byte == '\n' || rx_byte == '\r')
        {
            rx_buffer[rx_index] = '\0'; // Cap off the end of the string

            // 1. AUTO MODE COMMAND
            if (strstr(rx_buffer, "AUTO") != NULL) {
                system_mode = 1;
            }
            // 2. MANUAL MODE COMMAND
            else if (strstr(rx_buffer, "MANUAL") != NULL) {
                system_mode = 0;
            }
            // 3. TARGET LUX COMMAND (Forgiving Parser)
            else if (rx_buffer[0] == 'T' || rx_buffer[0] == 't') {
                char *colon = strchr(rx_buffer, ':'); // Find where the colon is
                if (colon != NULL) {
                    int new_target = 0;
                    sscanf(colon + 1, "%d", &new_target); // Read the number after the colon

                    if (new_target >= 0 && new_target <= 2000) {
                        target_lux = (float)new_target;
                    }
                }
            }
            // 4. MANUAL LED COMMAND
            else if (strstr(rx_buffer, "LED") != NULL) {
                if (system_mode == 0) {
                    char *colon = strchr(rx_buffer, ':');
                    if (colon != NULL) {
                        int led_val = 0;
                        sscanf(colon + 1, "%d", &led_val);
                        if (led_val >= 0 && led_val <= 100) target_led_brightness = (float)led_val;
                    }
                }
            }
            // 5. MANUAL FOIL COMMAND
            else if (strstr(rx_buffer, "FOIL") != NULL) {
                if (system_mode == 0) {
                    char *colon = strchr(rx_buffer, ':');
                    if (colon != NULL) {
                        int foil_val = 0;
                        sscanf(colon + 1, "%d", &foil_val);
                        if (foil_val >= 0 && foil_val <= 100) Set_Manual_Foil_Pct((float)foil_val);
                    }
                }
            }

            rx_index = 0; // Reset the buffer for the next message
        }
        else
        {
            // If it's a normal character, add it to our string buffer
            if (rx_index < 19)
            {
                rx_buffer[rx_index++] = rx_byte;
            }
            else
            {
                // BUFFER LOCKOUT FIX: Clear the buffer safely if no \n was received
                rx_index = 0;
                memset(rx_buffer, 0, sizeof(rx_buffer));
            }
        }

        // Very Important: Restart the interrupt to listen for the next character!
        HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
    }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  * where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */

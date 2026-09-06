/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/

#ifndef __BOARD_H
#define __BOARD_H

#include "stm32f722xx.h"


#define   RDC2_0064_ID                     5


//USB HS
#define   USB_HS_GPIO_1                    GPIOA
#define   USB_HS_D0_PIN                    3
#define   USB_HS_CK_PIN                    5
#define   USB_HS_GPIO_2                    GPIOB
#define   USB_HS_D1_PIN                    0
#define   USB_HS_D2_PIN                    1
#define   USB_HS_D3_PIN                    10
#define   USB_HS_D4_PIN                    11
#define   USB_HS_D5_PIN                    12
#define   USB_HS_D6_PIN                    13
#define   USB_HS_D7_PIN                    5
#define   USB_HS_GPIO_3                    GPIOC
#define   USB_HS_STP_PIN                   0
#define   USB_HS_DIR_PIN                   2
#define   USB_HS_NXT_PIN                   3
#define   USB_HS_PINS_AF                   10

//Logic Analyzer
#define   LOGIG_ANALYZER_DMA_ENR           AHB1ENR
#define   LOGIG_ANALYZER_DMA_CLK_EN        RCC_AHB1ENR_DMA2EN

#define   CHNL_0_15_GPIO_REG               (GPIOE->IDR)
#define   CHNL_0_15_TIMER                  TIM1
#define   CHNL_0_15_TIMER_ENR              APB2ENR
#define   CHNL_0_15_TIMER_CLK_EN           RCC_APB2ENR_TIM1EN
#define   CHNL_0_15_TIM_CCR1               ((uint32_t)&(CHNL_0_15_TIMER->CCR1))
#define   CHNL_0_15_TIM_CCR2               ((uint32_t)&(CHNL_0_15_TIMER->CCR2))
#define   CHNL_0_15_TIM_CCR3               ((uint32_t)&(CHNL_0_15_TIMER->CCR3))
#define   CHNL_0_15_TIM_CCR4               ((uint32_t)&(CHNL_0_15_TIMER->CCR4))

#define   CHNL_0_15_TIM_CCR1_DMA           DMA2_Stream3 //TIM_CCR1
#define   CHNL_0_15_TIM_CCR2_DMA           DMA2_Stream2 //TIM_CCR2
#define   CHNL_0_15_TIM_CCR3_DMA           DMA2_Stream6 //TIM_CCR3
#define   CHNL_0_15_TIM_CCR4_DMA           DMA2_Stream4 //TIM_CCR4
#define   CHNL_0_15_TIM_UPD_DMA            DMA2_Stream5 //TIM_UPD
#define   CHNL_0_15_TIM_UPD_DMA_IRQ        DMA2_Stream5_IRQn
#define   CHNL_0_15_TIM_IRQ_PRIORITY       0
#define   CHNL_0_15_DMA_CHNL               6

#define   CHNL_16_31_GPIO_REG              (GPIOD->IDR)
#define   CHNL_16_31_TIMER                 TIM8
#define   CHNL_16_31_TIMER_ENR             APB2ENR
#define   CHNL_16_31_TIMER_CLK_EN          RCC_APB2ENR_TIM8EN
#define   CHNL_16_31_TIM_CCR4              ((uint32_t)&(CHNL_16_31_TIMER->CCR4))

#define   CHNL_16_31_TIM_CCR4_DMA          DMA2_Stream7 //TIM_CCR4
#define   CHNL_16_31_TIM_UPD_DMA           DMA2_Stream1 //TIM_UPD
#define   CHNL_16_31_DMA_CHNL              7

#define   CHNL_COMMON_GPIO                 GPIOA
#define   CHNL_COMMON_CLK_PIN              0
#define   CHNL_COMMON_EDGE_PIN             1
#define   CHNL_COMMON_TIMER                TIM2
#define   CHNL_COMMON_TIMER_ENR            APB1ENR
#define   CHNL_COMMON_TIMER_CLK_EN         RCC_APB1ENR_TIM2EN
#define   CHNL_COMMON_AF                   1
#define   CHNL_COMMON_TIMER_IRQ            TIM2_IRQn
#define   CHNL_COMMON_TIMER_IRQ_PRIORITY   0

#define   GPIO_EXTI_IRQ_PRIORITY           0
#define   LOGIG_ANALYZER_CHNLS_COUNT       32

//LED
#define   LED_GPIO                         GPIOA
#define   LED_PIN                          6
#define   LED_TIMER                        TIM13
#define   LED_TIMER_ENR                    APB1ENR
#define   LED_TIMER_CLK_EN                 RCC_APB1ENR_TIM13EN
#define   LED_TIMER_AF                     9

//PWM1
#define   PWM_1_GPIO                       GPIOC
#define   PWM_1_PIN_1                      8 //board M15
#define   PWM_1_PIN_2                      7 //board M16
#define   PWM_1_PIN_3                      6 //board M17
#define   PWM_1_TIMER                      TIM3
#define   PWM_1_TIMER_ENR                  APB1ENR
#define   PWM_1_TIMER_CLK_EN               RCC_APB1ENR_TIM3EN
#define   PWM_1_CHANNEL_1                  (PWM_1_TIMER->CCR3)
#define   PWM_1_CHANNEL_2                  (PWM_1_TIMER->CCR2)
#define   PWM_1_CHANNEL_3                  (PWM_1_TIMER->CCR1)
#define   PWM_1_TIMER_AF                   2

//PWM2
#define   PWM_2_GPIO                       GPIOB
#define   PWM_2_PIN_1                      15 //board M18
#define   PWM_2_PIN_2                      14 //board M19
#define   PWM_2_TIMER                      TIM12
#define   PWM_2_TIMER_ENR                  APB1ENR
#define   PWM_2_TIMER_CLK_EN               RCC_APB1ENR_TIM12EN
#define   PWM_2_CHANNEL_1                  (PWM_2_TIMER->CCR2)
#define   PWM_2_CHANNEL_2                  (PWM_2_TIMER->CCR1)
#define   PWM_2_TIMER_AF                   9

//PWM Input
#define   PWM_INPUT_GPIO                   GPIOA
#define   PWM_INPUT_PIN                    2 //board M20
#define   PWM_INPUT_TIMER                  TIM9
#define   PWM_INPUT_TIMER_ENR              APB2ENR
#define   PWM_INPUT_TIMER_CLK_EN           RCC_APB2ENR_TIM9EN
#define   PWM_INPUT_TIMER_AF               3
#define   PWM_INPUT_TIMER_IRQ              TIM1_BRK_TIM9_IRQn
#define   PWM_INPUT_TIMER_IRQ_PRIORITY     0


#define   FIRMWARE_VERSION_BYTE_1          0x00
#define   FIRMWARE_VERSION_BYTE_2          0x02
#define   FIRMWARE_VERSION_BYTE_3          0x00
#define   FIRMWARE_VERSION_BYTE_4          0x00

#define   HARDWARE_VERSION                 0x01


void RDC2_0064Init();

uint32_t JoinBytesIntoValue(uint8_t *Data, uint8_t Size);


#endif //__BOARD_H





/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


#ifndef __LOGIC_ANALYZER_H
#define __LOGIC_ANALYZER_H


#include "Board.h"


#define   LA_DATA_BUF_SIZE                 ((uint32_t) 240640) //512 * 470


#define   DMA_CONFIG                       (DMA_SxCR_PL_1 | DMA_SxCR_PL_0 | DMA_SxCR_MINC)
#define   DMA_ACCESS_16BIT                 (DMA_SxCR_MSIZE_0 | DMA_SxCR_PSIZE_0)
#define   DMA_ACCESS_8BIT                  0

#define   SLAVE_TRIGGER_COMMON_MASTER      (TIM_SMCR_SMS_1 | TIM_SMCR_SMS_2 | TIM_SMCR_TS_0)
#define   SLAVE_GATED_COMMON_MASTER        (TIM_SMCR_SMS_0 | TIM_SMCR_SMS_2 | TIM_SMCR_TS_0)
#define   COMMON_MASTER_ENABLE             TIM_CR2_MMS_0
#define   COMMON_SLAVE_EDGE_GATED          (TIM_SMCR_SMS_0 | TIM_SMCR_SMS_2 | TIM_SMCR_TS_1 | TIM_SMCR_TS_2)
#define   COMMON_SLAVE_EDGE_TRIGGER        (TIM_SMCR_SMS_1 | TIM_SMCR_SMS_2 | TIM_SMCR_TS_1 | TIM_SMCR_TS_2)
#define   EDGE_ACTIVE_RISING               0
#define   EDGE_ACTIVE_FALLING              TIM_CCER_CC2P
#define   EDGE_ACTIVE_ANY                  (TIM_CCER_CC2P | TIM_CCER_CC2NP)

#define   BUFFER_MODE_SAMPLE_COUNT         LA_DATA_BUF_SIZE
#define   STREAM_MODE_SAMPLE_COUNT         16384//512 * 32
#define   STREAM_MODE_BUFFER_SIZE          ((uint32_t) 229376) //512 * 448

#define   START_FROM_COMMON_TIMER          1


enum LAChnls
{
  LA_CHNLS_8 = 8,
  LA_CHNLS_16 = 16,
  LA_CHNLS_24 = 24,
  LA_CHNLS_32 = 32,  
};



void LA_USBRequest(uint8_t *Request);

void LA_ConfigAndStart(uint8_t *Request);

void DMA2_Stream5_IRQHandler(void);

void LA_Init();

void LA_StartSampling();

void LA_StopSampling();

void TIM2_IRQHandler(void);

uint8_t* LA_GetDataBuf();


#endif //__LOGIC_ANALYZER_H




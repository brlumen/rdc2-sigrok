/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


#ifndef __LA_TRIGGERS_H
#define __LA_TRIGGERS_H


#include "Board.h"


#define   GPIO_INTERRUPT_MASK              0xFFFF



void Triggers_Config(uint8_t *Request);

void Triggers_Init(void (*TriggersCallBack)(void));

void GPIOs_IRQ_Handler(void);

void EXTI0_IRQHandler(void);

void EXTI1_IRQHandler(void);

void EXTI2_IRQHandler(void);

void EXTI3_IRQHandler(void);

void EXTI4_IRQHandler(void);

void EXTI9_5_IRQHandler(void);

void EXTI15_10_IRQHandler(void);


#endif //__LA_TRIGGERS_H

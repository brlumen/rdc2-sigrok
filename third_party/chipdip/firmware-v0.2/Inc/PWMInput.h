/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/

#ifndef __PWM_INPUT_H
#define __PWM_INPUT_H


#include "Board.h"


#define   PWM_INPUT_TIMER_ARR              0xFFFF




void PWMInput_USBRequest(uint8_t *Request);

void PWMInput_Init();

void PWMInput_ConfigAndStart(uint8_t *Request);

void PWMInput_Stop();



#endif //__PWM_INPUT_H





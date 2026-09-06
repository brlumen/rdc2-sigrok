/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/

#ifndef __LED_H
#define __LED_H


#include "Board.h"


#define   LED_TIM_ARR                      5999
#define   LED_TIM_CCR                      3000

#define   TRIGGER_AWAITING_FREQ            LED_4Hz
#define   SAMPLING_ACTIVE_FREQ             LED_05Hz


enum LED_FREQs
{ 
  LED_05Hz = 0,
  LED_4Hz,
};




void LED_Init();

void LED_ON();

void LED_BlinkAt(uint8_t Freq);


#endif //__LED_H





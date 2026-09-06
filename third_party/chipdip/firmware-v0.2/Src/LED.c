/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2020
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/



#include "LED.h"


const uint16_t LED_TIM_PSC[] = { 35999, 4499, };



void LED_Init()
{
  LED_GPIO->ODR |= 1 << LED_PIN;
  LED_GPIO->AFR[0] = (LED_TIMER_AF << (4 * LED_PIN));
  RCC->LED_TIMER_ENR |= LED_TIMER_CLK_EN;
  LED_TIMER->CCMR1 = TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1 | TIM_CCMR1_OC1PE | TIM_CCMR1_OC1FE;
  LED_TIMER->CCER = TIM_CCER_CC1E;
  LED_TIMER->ARR = LED_TIM_ARR;
  LED_TIMER->CCR1 = LED_TIM_CCR;
}
//------------------------------------------------------------------------------
void LED_ON()
{
  LED_TIMER->CR1 = 0;
  LED_GPIO->MODER &=~ (3 << (2 * LED_PIN));
  LED_GPIO->MODER |= 1 << (2 * LED_PIN);
}
//------------------------------------------------------------------------------
void LED_BlinkAt(uint8_t Freq)
{
  LED_GPIO->MODER &=~ (3 << (2 * LED_PIN));
  LED_GPIO->MODER |= 2 << (2 * LED_PIN);
  LED_TIMER->CR1 = 0;
  LED_TIMER->CNT = 0;
  LED_TIMER->SR = 0;
  LED_TIMER->PSC = LED_TIM_PSC[Freq];
  LED_TIMER->CR1 = TIM_CR1_CEN;
}





/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2020
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/




#include "PWM.h"
#include "USBPtorocol.h"


void PWM_Init()
{
  //PWM_1
  PWM_1_GPIO->MODER |= (2 << (2 * PWM_1_PIN_1)) | (2 << (2 * PWM_1_PIN_2)) | (2 << (2 * PWM_1_PIN_3));
  PWM_1_GPIO->AFR[0] |= (PWM_1_TIMER_AF << (4 * PWM_1_PIN_2)) | (PWM_1_TIMER_AF << (4 * PWM_1_PIN_3));
  PWM_1_GPIO->AFR[1] |= (PWM_1_TIMER_AF << (4 * (PWM_1_PIN_1 - 8)));
  PWM_1_GPIO->OSPEEDR |= (3 << (2 * PWM_1_PIN_1)) | (3 << (2 * PWM_1_PIN_2)) | (3 << (2 * PWM_1_PIN_3));
  
  RCC->PWM_1_TIMER_ENR |= PWM_1_TIMER_CLK_EN;
  
  PWM_1_TIMER->CCMR1 = TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1 | TIM_CCMR1_OC1PE | TIM_CCMR1_OC1FE |\
                       TIM_CCMR1_OC2M_2 | TIM_CCMR1_OC2M_1 | TIM_CCMR1_OC2PE | TIM_CCMR1_OC2FE;
  
  PWM_1_TIMER->CCMR2 = TIM_CCMR2_OC3M_2 | TIM_CCMR2_OC3M_1 | TIM_CCMR2_OC3PE | TIM_CCMR2_OC3FE;
  PWM_1_TIMER->CCER = TIM_CCER_CC1E | TIM_CCER_CC2E | TIM_CCER_CC3E;
  
  //PWM_2
  PWM_2_GPIO->MODER |= (2 << (2 * PWM_2_PIN_1)) | (2 << (2 * PWM_2_PIN_2));
  PWM_2_GPIO->AFR[1] |= (PWM_2_TIMER_AF << (4 * (PWM_2_PIN_1 - 8))) | (PWM_2_TIMER_AF << (4 * (PWM_2_PIN_2 - 8)));
  PWM_2_GPIO->OSPEEDR |= (3 << (2 * PWM_2_PIN_1)) | (3 << (2 * PWM_2_PIN_2));
  
  RCC->PWM_2_TIMER_ENR |= PWM_2_TIMER_CLK_EN;
  
  PWM_2_TIMER->CCMR1 = TIM_CCMR1_OC1M_2 | TIM_CCMR1_OC1M_1 | TIM_CCMR1_OC1PE | TIM_CCMR1_OC1FE |\
                       TIM_CCMR1_OC2M_2 | TIM_CCMR1_OC2M_1 | TIM_CCMR1_OC2PE | TIM_CCMR1_OC2FE;
  
  PWM_2_TIMER->CCER = TIM_CCER_CC1E | TIM_CCER_CC2E;
}
//------------------------------------------------------------------------------
void PWM_USBRequest(uint8_t *Request)
{
  PWM_1_TIMER->CR1 = 0;
  if (Request[PWM_1_CHNLS_MASK_OFFSET] != 0)
  {
    PWM_1_TIMER->PSC = (uint16_t)JoinBytesIntoValue(&Request[PWM_1_TIM_PSC_OFFSET], PWM_1_TIM_PSC_SIZE);
    PWM_1_TIMER->ARR = (uint16_t)JoinBytesIntoValue(&Request[PWM_1_TIM_ARR_OFFSET], PWM_1_TIM_ARR_SIZE);
    PWM_1_CHANNEL_1 = (uint16_t)JoinBytesIntoValue(&Request[PWM_1_CCR_M15_OFFSET], PWM_1_CCR_M15_SIZE);
    PWM_1_CHANNEL_2 = (uint16_t)JoinBytesIntoValue(&Request[PWM_1_CCR_M16_OFFSET], PWM_1_CCR_M16_SIZE);
    PWM_1_CHANNEL_3 = (uint16_t)JoinBytesIntoValue(&Request[PWM_1_CCR_M17_OFFSET], PWM_1_CCR_M17_SIZE);
    
    PWM_1_TIMER->EGR = TIM_EGR_UG;
    PWM_1_TIMER->SR = 0;
    PWM_1_TIMER->CR1 = TIM_CR1_CEN;
  }
  
  PWM_2_TIMER->CR1 = 0;
  if (Request[PWM_2_CHNLS_MASK_OFFSET] != 0)
  {
    PWM_2_TIMER->PSC = (uint16_t)JoinBytesIntoValue(&Request[PWM_2_TIM_PSC_OFFSET], PWM_2_TIM_PSC_SIZE);
    PWM_2_TIMER->ARR = (uint16_t)JoinBytesIntoValue(&Request[PWM_2_TIM_ARR_OFFSET], PWM_2_TIM_ARR_SIZE);
    PWM_2_CHANNEL_1 = (uint16_t)JoinBytesIntoValue(&Request[PWM_2_CCR_M18_OFFSET], PWM_2_CCR_M18_SIZE);
    PWM_2_CHANNEL_2 = (uint16_t)JoinBytesIntoValue(&Request[PWM_2_CCR_M19_OFFSET], PWM_2_CCR_M19_SIZE);
        
    PWM_2_TIMER->EGR = TIM_EGR_UG;
    PWM_2_TIMER->SR = 0;
    PWM_2_TIMER->CR1 = TIM_CR1_CEN;
  }
}




/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/



#include "PWMInput.h"
#include "stm32f7xx_hal_cortex.h"
#include "USBPtorocol.h"
#include "USBPort.h"
#include "LogicAnalyzer.h"



void PWMInput_USBRequest(uint8_t *Request)
{
  switch(*(Request + USB_CMD_INDEX))
  {
    case PWM_INPUT_CMD_CONFIG:
      PWMInput_ConfigAndStart(Request);
    break;
    
    case PWM_INPUT_CMD_GET_DATA:
    {
      uint16_t Period = 0;
      uint16_t DutyCycle = 0;
      
      if ((PWM_INPUT_TIMER->SR & (TIM_SR_CC1IF | TIM_SR_CC2IF)) == (TIM_SR_CC1IF | TIM_SR_CC2IF))
      {
        Period = PWM_INPUT_TIMER->CCR1;
        DutyCycle = PWM_INPUT_TIMER->CCR2;
      }
      
      uint8_t *BufferToSend = LA_GetDataBuf();
      BufferToSend[PWM_INPUT_PERIOD_OFFSET] = Period;
      BufferToSend[PWM_INPUT_PERIOD_OFFSET + 1] = Period >> 8;
      BufferToSend[PWM_INPUT_DUTY_CYCLE_OFFSET] = DutyCycle;
      BufferToSend[PWM_INPUT_DUTY_CYCLE_OFFSET + 1] = DutyCycle >> 8;
      USBPort_SetBufAndSend(BufferToSend, USB_Tx_LENGTH);
    }
    break;
    
    case PWM_INPUT_CMD_STOP:
      PWMInput_Stop();
    break;
    
    default:
    break;
  }
}
//------------------------------------------------------------------------------
void PWMInput_Init()
{
  PWM_INPUT_GPIO->MODER |= (2 << (2 * PWM_INPUT_PIN));  
  PWM_INPUT_GPIO->AFR[0] |= (PWM_INPUT_TIMER_AF << (4 * PWM_INPUT_PIN));

  RCC->PWM_INPUT_TIMER_ENR |= PWM_INPUT_TIMER_CLK_EN;
  PWM_INPUT_TIMER->ARR = PWM_INPUT_TIMER_ARR;
  PWM_INPUT_TIMER->CCMR1 = TIM_CCMR1_CC1S_0 | TIM_CCMR1_CC2S_1;
  PWM_INPUT_TIMER->CCER |= TIM_CCER_CC1E | TIM_CCER_CC2E | TIM_CCER_CC2P;
}
//------------------------------------------------------------------------------
void PWMInput_ConfigAndStart(uint8_t *Request)
{
  PWMInput_Stop();
  
  PWM_INPUT_TIMER->PSC = (uint16_t)JoinBytesIntoValue(&Request[PWM_INPUT_TIM_PSC_OFFSET], PWM_INPUT_TIM_PSC_SIZE);
  PWM_INPUT_TIMER->SMCR = TIM_SMCR_TS_2 | TIM_SMCR_TS_0 | TIM_SMCR_SMS_2;
  PWM_INPUT_TIMER->CR1 = TIM_CR1_CEN;
}
//------------------------------------------------------------------------------
void PWMInput_Stop()
{
  PWM_INPUT_TIMER->CR1 = 0;
  PWM_INPUT_TIMER->SMCR = 0;
  PWM_INPUT_TIMER->SR = 0;
}



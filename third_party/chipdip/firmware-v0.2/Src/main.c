/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/



#include "stm32f7xx_hal.h"
#include "Board.h"
#include "USBPort.h"
#include "USBPtorocol.h"
#include "LogicAnalyzer.h"
#include "LED.h"
#include "PWM.h"
#include "PWMInput.h"


int main(void)
{
  RDC2_0064Init();
  
  for (;;)
  {
    __WFI();
    
    if ((*USBPort_GetStatus()) != USB_PORT_IDLE)
    {
      uint8_t *Request = (uint8_t *)USBPort_GetPacket();
      
      if (((*USBPort_GetStatus()) & USB_PORT_MODULE_REQUEST) == USB_PORT_MODULE_REQUEST)
      {
        USBPort_ClearStatus(USB_PORT_MODULE_REQUEST);
        
        switch(*(Request + USB_MODULE_ID_INDEX))
        {
          case MODULE_LA:
            LA_USBRequest(Request);
          break;
          
          case MODULE_PWM:
            PWM_USBRequest(Request);
          break;
          
          case MODULE_PWM_INPUT:
            PWMInput_USBRequest(Request);
          break;
    
          default:
          break;
        }
      }
    }
  }
}
//------------------------------------------------------------------------------
void RDC2_0064Init()
{
  SCB_EnableICache();
  HAL_Init();
  
  RCC->CR |= RCC_CR_HSEON;
  while((RCC->CR & RCC_CR_HSERDY) == 0);

  //(2 << 28) - reset value, reserved
  RCC->PLLCFGR = (2 << 28) | RCC_PLLCFGR_PLLSRC | RCC_PLLCFGR_PLLN_8 | RCC_PLLCFGR_PLLN_7 | \
                 RCC_PLLCFGR_PLLN_5 | RCC_PLLCFGR_PLLN_4 | RCC_PLLCFGR_PLLM_3;

  RCC->APB1ENR |= RCC_APB1ENR_PWREN;
  PWR->CR1 |= PWR_CR1_ODEN;
  while((PWR->CSR1 & PWR_CSR1_ODRDY) == 0);
  
  PWR->CR1 |= PWR_CR1_ODSWEN;
  while((PWR->CSR1 & PWR_CSR1_ODSWRDY) == 0);
  
  FLASH->ACR |= FLASH_ACR_LATENCY_7WS;
  
  RCC->CFGR = RCC_CFGR_PPRE2_DIV2 | RCC_CFGR_PPRE1_DIV4;
  
  RCC->CR |= RCC_CR_PLLON;
  while((RCC->CR & RCC_CR_PLLRDY) == 0);
  
  RCC->CFGR |= RCC_CFGR_SW_PLL;
  while ((RCC->CFGR & (uint32_t)RCC_CFGR_SWS) != (uint32_t)RCC_CFGR_SWS_PLL);
  
  RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIOBEN | RCC_AHB1ENR_GPIOCEN | \
                  RCC_AHB1ENR_GPIODEN | RCC_AHB1ENR_GPIOEEN;
    
  LED_Init();
  LA_Init();
  PWM_Init();
  PWMInput_Init();
  USBPort_Init();
}
//------------------------------------------------------------------------------
uint32_t JoinBytesIntoValue(uint8_t *Data, uint8_t Size)
{
  uint32_t Result = 0;
  
  for (uint8_t i = 0; i < Size; i++)
    Result |= (*(Data + i)) << (i * 8);
  
  return Result;
}




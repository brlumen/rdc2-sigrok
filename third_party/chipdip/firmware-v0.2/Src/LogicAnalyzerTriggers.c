/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/



#include "LogicAnalyzerTriggers.h"
#include "stm32f7xx_hal_cortex.h"
#include "USBPtorocol.h"


static void (*Triggers_StateMatched)(void) = 0;
static uint16_t LevelTrigValue0_15 = 0;
static uint16_t LevelTrigChnls0_15 = 0;
static uint16_t LevelTrigValue16_31 = 0;
static uint16_t LevelTrigChnls16_31 = 0;
static uint16_t EdgeTrigChnls = 0;



void Triggers_Config(uint8_t *Request)
{
  EXTI->RTSR &= ~GPIO_INTERRUPT_MASK;
  EXTI->FTSR &= ~GPIO_INTERRUPT_MASK;
  LevelTrigValue0_15 = 0;
  LevelTrigChnls0_15 = 0;
  LevelTrigValue16_31 = 0;
  LevelTrigChnls16_31 = 0;
  
  uint8_t OnlyLevelTrigger = 1;
  for (uint8_t i = 0; i < (LOGIG_ANALYZER_CHNLS_COUNT / 2); i++)
  {
    uint8_t ChnlTrigger = Request[LA_CHNL_TRIG_SET_OFFSET + i];
    
    switch(ChnlTrigger)
    {
      default:
      case TRIGGER_NONE:
      break;
      
      case TRIGGER_LOW_LEVEL:
        LevelTrigChnls0_15 |= 1 << i;
      break;
                          
      case TRIGGER_HIGH_LEVEL:
        LevelTrigValue0_15 |= 1 << i;
        LevelTrigChnls0_15 |= 1 << i;
      break;
                          
      case TRIGGER_RISING_EDGE:
        EXTI->RTSR |= 1 << i;
        OnlyLevelTrigger = 0;
      break;
                          
      case TRIGGER_FALLING_EDGE:
        EXTI->FTSR |= 1 << i;
        OnlyLevelTrigger = 0;
      break;
                          
      case TRIGGER_ANY_EDGE:
        EXTI->RTSR |= 1 << i;
        EXTI->FTSR |= 1 << i;
        OnlyLevelTrigger = 0;
      break;
    }
  }
  
  for (uint8_t i = 0; i < (LOGIG_ANALYZER_CHNLS_COUNT / 2); i++)
  {
    uint8_t ChnlTrigger = Request[LA_CHNL_TRIG_SET_OFFSET + LOGIG_ANALYZER_CHNLS_COUNT / 2 + i];
    
    switch(ChnlTrigger)
    {
      default:
      case TRIGGER_NONE:
      break;
      
      case TRIGGER_LOW_LEVEL:
        LevelTrigChnls16_31 |= 1 << i;
      break;
                          
      case TRIGGER_HIGH_LEVEL:
        LevelTrigValue16_31 |= 1 << i;
        LevelTrigChnls16_31 |= 1 << i;
      break;
    }
  }
  
  if (OnlyLevelTrigger == 1)
  {
    while (((CHNL_0_15_GPIO_REG & LevelTrigChnls0_15) != LevelTrigValue0_15)
        || ((CHNL_16_31_GPIO_REG & LevelTrigChnls16_31) != LevelTrigValue16_31));
    
    if (Triggers_StateMatched != 0)
      Triggers_StateMatched();
  }
  else
  {
    EdgeTrigChnls = EXTI->RTSR;
    EdgeTrigChnls = (EdgeTrigChnls | EXTI->FTSR);
    EXTI->IMR |= EdgeTrigChnls;
  }
}
//------------------------------------------------------------------------------
void Triggers_Init(void (*TriggersCallBack)(void))
{
  RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;
  //EXTI on PE port
  SYSCFG->EXTICR[0] = (4 << (4 * 3)) | (4 << (4 * 2)) | (4 << (4 * 1)) | (4 << (4 * 0));
  SYSCFG->EXTICR[1] = (4 << (4 * 3)) | (4 << (4 * 2)) | (4 << (4 * 1)) | (4 << (4 * 0));
  SYSCFG->EXTICR[2] = (4 << (4 * 3)) | (4 << (4 * 2)) | (4 << (4 * 1)) | (4 << (4 * 0));
  SYSCFG->EXTICR[3] = (4 << (4 * 3)) | (4 << (4 * 2)) | (4 << (4 * 1)) | (4 << (4 * 0));
  
  HAL_NVIC_SetPriority(EXTI0_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);
  HAL_NVIC_SetPriority(EXTI1_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI1_IRQn);
  HAL_NVIC_SetPriority(EXTI2_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI2_IRQn);
  HAL_NVIC_SetPriority(EXTI3_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI3_IRQn);
  HAL_NVIC_SetPriority(EXTI4_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI4_IRQn);
  HAL_NVIC_SetPriority(EXTI9_5_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, GPIO_EXTI_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
  
  Triggers_StateMatched = TriggersCallBack;
}
//------------------------------------------------------------------------------
void GPIOs_IRQ_Handler(void)
{
  if (((EXTI->PR & EdgeTrigChnls) == EdgeTrigChnls)
   && ((CHNL_0_15_GPIO_REG & LevelTrigChnls0_15) == LevelTrigValue0_15)
   && ((CHNL_16_31_GPIO_REG & LevelTrigChnls16_31) == LevelTrigValue16_31))
  {
    EXTI->IMR &= ~EdgeTrigChnls;
    
    if (Triggers_StateMatched != 0)
      Triggers_StateMatched();
  }
  
  EXTI->PR |= EdgeTrigChnls;
}
//------------------------------------------------------------------------------
void EXTI0_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}
//------------------------------------------------------------------------------
void EXTI1_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}
//------------------------------------------------------------------------------
void EXTI2_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}
//------------------------------------------------------------------------------
void EXTI3_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}
//------------------------------------------------------------------------------
void EXTI4_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}
//------------------------------------------------------------------------------
void EXTI9_5_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}
//------------------------------------------------------------------------------
void EXTI15_10_IRQHandler(void)
{ 
  GPIOs_IRQ_Handler();
}



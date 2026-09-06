/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


#include "LogicAnalyzer.h"
#include "USBPtorocol.h"
#include "stm32f7xx_hal_cortex.h"
#include "USBPort.h"
#include "LogicAnalyzerTriggers.h"
#include "LED.h"



static uint8_t DataBuffer[LA_DATA_BUF_SIZE];
static uint8_t DMAStreamsCount = 1;
static DMA_Stream_TypeDef *DMAStreams0_15[] = {0,0,0,0,0,};
static uint8_t ActiveChnls = LA_CHNLS_8;
static uint8_t SamplingMode = LA_BUFFER_MODE;
static volatile uint32_t StreamM0AR;
static volatile uint32_t StreamM1AR;
static uint32_t StreamModeReadAdr;
static volatile uint8_t StreamPackReady = 0;
static volatile uint32_t StreamPackCnt = 0;
static volatile uint8_t StreamOversample = 0;
static uint8_t StartType = 0;
static uint16_t CommonTimSlaveMode = 0;
static uint16_t CommonTimEnValue = 0;


void LA_USBRequest(uint8_t *Request)
{ 
  switch(*(Request + USB_CMD_INDEX))
  {
    case LA_CMD_CONFIG:
      USBPort_ClearSystemStatus(LA_SAMPLING_CMP);
      LA_ConfigAndStart(Request);
    break;
    
    case LA_CMD_GET_SAMPLES:
      if (SamplingMode == LA_BUFFER_MODE)
        USBPort_SetBufAndSend((uint8_t*)DataBuffer, BUFFER_MODE_SAMPLE_COUNT);
      else //if (SamplingMode == LA_STREAM_MODE)
      {
        while(StreamPackReady == 0);
        
        USBPort_SetBufAndSend((uint8_t*)StreamModeReadAdr, STREAM_MODE_SAMPLE_COUNT);
        StreamModeReadAdr += STREAM_MODE_SAMPLE_COUNT;
        if (StreamModeReadAdr >= ((uint32_t)(&DataBuffer[0]) + STREAM_MODE_BUFFER_SIZE))
          StreamModeReadAdr = (uint32_t)(&DataBuffer[0]);
        
        StreamPackReady = 0;
      }
    break;
    
    case LA_CMD_SAMPLE_STOP:
      LA_StopSampling();
      
      DataBuffer[0] = StreamOversample;
      DataBuffer[1] = StreamPackCnt;
      DataBuffer[2] = StreamPackCnt >> 8;
      DataBuffer[3] = StreamPackCnt >> 16;
      DataBuffer[4] = StreamPackCnt >> 24;
      USBPort_SetBufAndSend((uint8_t*)DataBuffer, USB_Tx_LENGTH);
    break;
    
    default:
    break;
  }
}
//------------------------------------------------------------------------------
void LA_ConfigAndStart(uint8_t *Request)
{
  for (uint8_t i = 0; i < 64; i++)
    DataBuffer[i] = Request[i];
 
  CHNL_0_15_TIMER->SMCR = 0;
  CHNL_16_31_TIMER->SMCR = 0;
  CHNL_COMMON_TIMER->SMCR = 0;
  CHNL_COMMON_TIMER->CCER = EDGE_ACTIVE_RISING;
  CHNL_COMMON_TIMER->CR2 = 0;
  
  uint32_t Chnls0_15DMAConf = (CHNL_0_15_DMA_CHNL << DMA_SxCR_CHSEL_Pos) | DMA_CONFIG;
  uint32_t Chnls16_31DMAConf = (CHNL_16_31_DMA_CHNL << DMA_SxCR_CHSEL_Pos) | DMA_CONFIG;
  uint32_t SampleCount = JoinBytesIntoValue(&DataBuffer[LA_SAMPLE_COUNT_OFFSET], LA_SAMPLE_COUNT_SIZE);
  uint32_t TimerCCRs0_15[] = {0,0,0,0,};
  uint8_t BytesPerSample = 1;
  ActiveChnls = DataBuffer[LA_CHNL_COUNT_OFFSET];
  SamplingMode = DataBuffer[LA_SAMPLING_MODE_OFFSET];
  
  switch(ActiveChnls)
  {
    case LA_CHNLS_8:
    default:
      Chnls0_15DMAConf |= DMA_ACCESS_8BIT;
    break;
    
    case LA_CHNLS_16:
      Chnls0_15DMAConf |= DMA_ACCESS_16BIT;
      BytesPerSample = 2;
    break;
    
    case LA_CHNLS_32:
      Chnls0_15DMAConf  |= DMA_ACCESS_16BIT;
      Chnls16_31DMAConf |= DMA_ACCESS_16BIT;
      BytesPerSample = 2;
    break;
  }
  
  DMAStreamsCount = DataBuffer[LA_DMA_STREAMS_COUNT_OFFSET];
  
  switch(DMAStreamsCount)
  {
    case 1:
    default:
      DMAStreams0_15[0] = CHNL_0_15_TIM_UPD_DMA;
    break;
   
    case 4:
      DMAStreams0_15[0] = CHNL_0_15_TIM_CCR1_DMA;
      DMAStreams0_15[1] = CHNL_0_15_TIM_CCR2_DMA;
      DMAStreams0_15[2] = CHNL_0_15_TIM_CCR3_DMA;
      DMAStreams0_15[3] = CHNL_0_15_TIM_UPD_DMA;
      
      TimerCCRs0_15[0] = CHNL_0_15_TIM_CCR1;
      TimerCCRs0_15[1] = CHNL_0_15_TIM_CCR2;
      TimerCCRs0_15[2] = CHNL_0_15_TIM_CCR3;
    break;
    
    case 5:
      DMAStreams0_15[0] = CHNL_0_15_TIM_CCR1_DMA;
      DMAStreams0_15[1] = CHNL_0_15_TIM_CCR2_DMA;
      DMAStreams0_15[2] = CHNL_0_15_TIM_CCR3_DMA;
      DMAStreams0_15[3] = CHNL_0_15_TIM_CCR4_DMA;
      DMAStreams0_15[4] = CHNL_0_15_TIM_UPD_DMA;
      
      TimerCCRs0_15[0] = CHNL_0_15_TIM_CCR1;
      TimerCCRs0_15[1] = CHNL_0_15_TIM_CCR2;
      TimerCCRs0_15[2] = CHNL_0_15_TIM_CCR3;
      TimerCCRs0_15[3] = CHNL_0_15_TIM_CCR4;
    break;
  }
  
  SampleCount /= DMAStreamsCount;
  if (SamplingMode == LA_STREAM_MODE)
  {
    if (ActiveChnls == LA_CHNLS_32)
      BytesPerSample = 4;
    
    SampleCount = STREAM_MODE_SAMPLE_COUNT / BytesPerSample;
    StreamModeReadAdr = (uint32_t)(&DataBuffer[0]);
    StreamPackReady = 0;
    StreamPackCnt = 0;
    StreamOversample = 0;
  }
  
  uint16_t TimARR_1Chnl = (uint16_t)JoinBytesIntoValue(&DataBuffer[LA_SAMPLE_TIM_ARR_OFFSET], LA_SAMPLE_TIM_ARR_SIZE);
  uint32_t DmaMarOffset = SampleCount * BytesPerSample;
  
  for (uint8_t i = 0; i < DMAStreamsCount; i++)
  {
    DMAStreams0_15[i]->CR = Chnls0_15DMAConf;
    DMAStreams0_15[i]->PAR = (uint32_t)(&CHNL_0_15_GPIO_REG);
    DMAStreams0_15[i]->NDTR = SampleCount;
    DMAStreams0_15[i]->M0AR = (uint32_t)(&DataBuffer[i * DmaMarOffset]);
    
    if (SamplingMode == LA_STREAM_MODE)
    {
      DMAStreams0_15[i]->CR |= DMA_SxCR_DBM;
      DMAStreams0_15[i]->M1AR = (uint32_t)(&DataBuffer[1 * DmaMarOffset]);
      StreamM0AR = (uint32_t)(&DataBuffer[2 * DmaMarOffset]);
      StreamM1AR = (uint32_t)(&DataBuffer[3 * DmaMarOffset]);
    }
        
    DMAStreams0_15[i]->CR |= DMA_SxCR_EN;
    
    if (i < (DMAStreamsCount - 1))
      (*(__IO uint16_t *)((TimerCCRs0_15[i]))) = TimARR_1Chnl * (i + 1);
  }
  
  if (ActiveChnls >= LA_CHNLS_24)
  {
    CHNL_16_31_TIM_UPD_DMA->CR = Chnls16_31DMAConf;
    CHNL_16_31_TIM_UPD_DMA->PAR = (uint32_t)(&CHNL_16_31_GPIO_REG);
    CHNL_16_31_TIM_UPD_DMA->NDTR = SampleCount;
    CHNL_16_31_TIM_UPD_DMA->M0AR = (uint32_t)(&DataBuffer[DMAStreamsCount * DmaMarOffset]);
    
    if (SamplingMode == LA_STREAM_MODE)
    {
      CHNL_16_31_TIM_UPD_DMA->CR |= DMA_SxCR_DBM;
      CHNL_16_31_TIM_UPD_DMA->M0AR = (uint32_t)(&DataBuffer[STREAM_MODE_SAMPLE_COUNT / 2]);
      CHNL_16_31_TIM_UPD_DMA->M1AR = (uint32_t)(&DataBuffer[(STREAM_MODE_SAMPLE_COUNT / 2) + STREAM_MODE_SAMPLE_COUNT]);
    }
    
    CHNL_16_31_TIM_UPD_DMA->CR |= DMA_SxCR_EN;
  }
  
  CommonTimSlaveMode = 0;
  CommonTimEnValue = 0;
  StartType = 0;
  uint16_t TimSlaveMode = 0;
  uint16_t TimEnValue = 0;
  if (DataBuffer[LA_EDGE_TRIG_SET_OFFSET] != TRIGGER_NONE)
  {
    TimSlaveMode = SLAVE_TRIGGER_COMMON_MASTER;
    CHNL_COMMON_TIMER->CR2 = COMMON_MASTER_ENABLE;
    CHNL_COMMON_TIMER->DIER = TIM_DIER_TIE;
    CommonTimSlaveMode = COMMON_SLAVE_EDGE_TRIGGER;
    StartType = START_FROM_COMMON_TIMER;
    
    switch(DataBuffer[LA_EDGE_TRIG_SET_OFFSET])
    {
      case TRIGGER_LOW_LEVEL:
      case TRIGGER_HIGH_LEVEL:
        TimSlaveMode = SLAVE_GATED_COMMON_MASTER;
        TimEnValue = TIM_CR1_CEN;
        CommonTimSlaveMode = COMMON_SLAVE_EDGE_GATED;
        CommonTimEnValue = TIM_CR1_CEN;
                
        if (DataBuffer[LA_EDGE_TRIG_SET_OFFSET] == TRIGGER_LOW_LEVEL)
          CHNL_COMMON_TIMER->CCER = EDGE_ACTIVE_FALLING;
      break;

      case TRIGGER_RISING_EDGE:
        
      break;
                          
      case TRIGGER_FALLING_EDGE:
        CHNL_COMMON_TIMER->CCER = EDGE_ACTIVE_FALLING;
      break;
                          
      case TRIGGER_ANY_EDGE:
        CHNL_COMMON_TIMER->CCER = EDGE_ACTIVE_ANY;
      break;
    }
  }
  else if (ActiveChnls >= LA_CHNLS_24)
  {
    TimSlaveMode = SLAVE_TRIGGER_COMMON_MASTER;
    CHNL_COMMON_TIMER->CR2 = COMMON_MASTER_ENABLE;
    CommonTimEnValue = TIM_CR1_CEN;
    StartType = START_FROM_COMMON_TIMER;
  }
  
  uint16_t TimPSC = (uint16_t)JoinBytesIntoValue(&DataBuffer[LA_SAMPLE_TIM_PSC_OFFSET], LA_SAMPLE_TIM_PSC_SIZE);
  uint16_t TimARR = TimARR_1Chnl * DMAStreamsCount - 1;
  CHNL_0_15_TIMER->PSC = TimPSC;
  CHNL_0_15_TIMER->ARR = TimARR;  
  CHNL_0_15_TIMER->EGR = TIM_EGR_UG;
  CHNL_0_15_TIMER->SR = 0;
  CHNL_0_15_TIMER->SMCR = TimSlaveMode;
  CHNL_0_15_TIMER->CR1 = TimEnValue;
  
  if (ActiveChnls >= LA_CHNLS_24)
  {
    CHNL_16_31_TIMER->PSC = TimPSC;
    CHNL_16_31_TIMER->ARR = TimARR;
    CHNL_16_31_TIMER->EGR = TIM_EGR_UG;
    CHNL_16_31_TIMER->SR = 0;
    CHNL_16_31_TIMER->SMCR = TimSlaveMode;
    CHNL_16_31_TIMER->CR1 = TimEnValue;
  }
  
  switch(DMAStreamsCount)
  {
    case 1:
    default:
      CHNL_0_15_TIMER->DIER = TIM_DIER_UDE;
      if (ActiveChnls >= LA_CHNLS_24)
        CHNL_16_31_TIMER->DIER = TIM_DIER_UDE;
    break;

    case 4:
      CHNL_0_15_TIMER->DIER = TIM_DIER_UDE | TIM_DIER_CC1DE | TIM_DIER_CC2DE | TIM_DIER_CC3DE;
    break;
    
    case 5:
      CHNL_0_15_TIMER->DIER = TIM_DIER_UDE | TIM_DIER_CC1DE | TIM_DIER_CC2DE | TIM_DIER_CC3DE | TIM_DIER_CC4DE;
    break;
  }
  
  CHNL_0_15_TIM_UPD_DMA->CR |= DMA_SxCR_TCIE;
  
  if (DataBuffer[LA_CHNL_TRIG_ACTIVE_OFFSET] == LA_TRIG_ACTIVE)
  {
    LED_BlinkAt(TRIGGER_AWAITING_FREQ);
    Triggers_Config(DataBuffer);
  }
  else
    LA_StartSampling();
}
//------------------------------------------------------------------------------
void DMA2_Stream5_IRQHandler(void)
{  
  if ((DMA2->HISR & DMA_HISR_TCIF5) == DMA_HISR_TCIF5)
  {
    if (SamplingMode == LA_BUFFER_MODE)
    {
      LA_StopSampling();
      USBPort_SetSystemStatus(LA_SAMPLING_CMP);
    }
    else //if (SamplingMode == LA_STREAM_MODE)
    {
      DMA2->HIFCR |= DMA_HIFCR_CTCIF5 | DMA_HIFCR_CHTIF5 | DMA_HIFCR_CFEIF5;
      if (ActiveChnls == LA_CHNLS_32)
        DMA2->LIFCR |= DMA_LIFCR_CTCIF1 | DMA_LIFCR_CHTIF1 | DMA_LIFCR_CFEIF1;
      
      if ((CHNL_0_15_TIM_UPD_DMA->CR & DMA_SxCR_CT) == DMA_SxCR_CT)
      {
        CHNL_0_15_TIM_UPD_DMA->M0AR = StreamM0AR;
        if (ActiveChnls == LA_CHNLS_32)
          CHNL_16_31_TIM_UPD_DMA->M0AR = StreamM0AR + (STREAM_MODE_SAMPLE_COUNT / 2);
        
        StreamM0AR += 2 * STREAM_MODE_SAMPLE_COUNT;
        if (StreamM0AR >= ((uint32_t)(&DataBuffer[0]) + STREAM_MODE_BUFFER_SIZE))
          StreamM0AR = (uint32_t)(&DataBuffer[0]);
        
        if (StreamM0AR == StreamModeReadAdr)
          StreamOversample = 1;
      }
      else
      {
        CHNL_0_15_TIM_UPD_DMA->M1AR = StreamM1AR;
        if (ActiveChnls == LA_CHNLS_32)
          CHNL_16_31_TIM_UPD_DMA->M1AR = StreamM1AR + (STREAM_MODE_SAMPLE_COUNT / 2);
        
        StreamM1AR += 2 * STREAM_MODE_SAMPLE_COUNT;
        if (StreamM1AR >= ((uint32_t)(&DataBuffer[0]) + STREAM_MODE_BUFFER_SIZE))
          StreamM1AR = (uint32_t)(&DataBuffer[STREAM_MODE_SAMPLE_COUNT]);
        
        if (StreamM1AR == StreamModeReadAdr)
          StreamOversample = 1;
      }
      
      StreamPackReady = 1;
      
      if (StreamOversample == 0)
        StreamPackCnt++;
    }
  }
}
//------------------------------------------------------------------------------
void LA_Init()
{
  HAL_NVIC_SetPriority(CHNL_0_15_TIM_UPD_DMA_IRQ, CHNL_0_15_TIM_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(CHNL_0_15_TIM_UPD_DMA_IRQ);
  
  HAL_NVIC_SetPriority(CHNL_COMMON_TIMER_IRQ, CHNL_COMMON_TIMER_IRQ_PRIORITY, 0);
  HAL_NVIC_EnableIRQ(CHNL_COMMON_TIMER_IRQ);
  
  RCC->CHNL_0_15_TIMER_ENR |= CHNL_0_15_TIMER_CLK_EN;
  RCC->CHNL_16_31_TIMER_ENR |= CHNL_16_31_TIMER_CLK_EN;
  RCC->CHNL_COMMON_TIMER_ENR |= CHNL_COMMON_TIMER_CLK_EN;
  RCC->LOGIG_ANALYZER_DMA_ENR |= LOGIG_ANALYZER_DMA_CLK_EN;
  
  CHNL_COMMON_GPIO->MODER |= (2 << (2 * CHNL_COMMON_EDGE_PIN));  
  CHNL_COMMON_GPIO->AFR[0] |= (CHNL_COMMON_AF << (4 * CHNL_COMMON_EDGE_PIN));
  
  Triggers_Init(LA_StartSampling);
}
//------------------------------------------------------------------------------
void LA_StartSampling()
{
  if (StartType != START_FROM_COMMON_TIMER)
  {
    CHNL_0_15_TIMER->CR1 = TIM_CR1_CEN;
    LED_BlinkAt(SAMPLING_ACTIVE_FREQ);
  }
  else
  {
    CHNL_COMMON_TIMER->SMCR = CommonTimSlaveMode;    
    CHNL_COMMON_TIMER->CR1 = CommonTimEnValue;
    
    if (CommonTimSlaveMode == 0)
      LED_BlinkAt(SAMPLING_ACTIVE_FREQ);
    else if ((CHNL_COMMON_TIMER->DIER & TIM_DIER_TIE) == TIM_DIER_TIE)
      LED_BlinkAt(TRIGGER_AWAITING_FREQ);
  }
}
//------------------------------------------------------------------------------
void LA_StopSampling()
{
  EXTI->IMR &= ~GPIO_INTERRUPT_MASK;
  EXTI->PR |= GPIO_INTERRUPT_MASK;
  
  CHNL_COMMON_TIMER->CR1 = 0;
  CHNL_0_15_TIMER->CR1 = 0;
  CHNL_16_31_TIMER->CR1 = 0;
  CHNL_COMMON_TIMER->SR = 0;
  CHNL_0_15_TIMER->DIER = 0;
  CHNL_0_15_TIMER->SR = 0;
  CHNL_16_31_TIMER->DIER = 0;
  CHNL_16_31_TIMER->SR = 0;
  
  for (uint8_t i = 0; i < DMAStreamsCount; i++)
  {
    while(DMAStreams0_15[i]->CR != 0)
      DMAStreams0_15[i]->CR = 0;
  }
  
  while(CHNL_16_31_TIM_UPD_DMA->CR != 0)
    CHNL_16_31_TIM_UPD_DMA->CR = 0;
  
  DMA2->LIFCR |= DMA_LIFCR_CTCIF1 | DMA_LIFCR_CHTIF1 | DMA_LIFCR_CFEIF1 | \
                 DMA_LIFCR_CTCIF2 | DMA_LIFCR_CHTIF2 | DMA_LIFCR_CFEIF2 | \
                 DMA_LIFCR_CTCIF3 | DMA_LIFCR_CHTIF3 | DMA_LIFCR_CFEIF3;
  DMA2->HIFCR |= DMA_HIFCR_CTCIF4 | DMA_HIFCR_CHTIF4 | DMA_HIFCR_CFEIF4 | \
                 DMA_HIFCR_CTCIF5 | DMA_HIFCR_CHTIF5 | DMA_HIFCR_CFEIF5 | \
                 DMA_HIFCR_CTCIF6 | DMA_HIFCR_CHTIF6 | DMA_HIFCR_CFEIF6 | \
                 DMA_HIFCR_CTCIF7 | DMA_HIFCR_CHTIF7 | DMA_HIFCR_CFEIF7;
  
  LED_ON();
}
//------------------------------------------------------------------------------
void TIM2_IRQHandler(void)
{
  LED_BlinkAt(SAMPLING_ACTIVE_FREQ);
  CHNL_COMMON_TIMER->DIER = 0;
  CHNL_COMMON_TIMER->SR = 0;
}
//------------------------------------------------------------------------------
uint8_t* LA_GetDataBuf()
{
  return DataBuffer;
}


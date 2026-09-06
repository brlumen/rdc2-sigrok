/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


#ifndef __USB_PROTOCOL_H
#define __USB_PROTOCOL_H

//CMD Header
#define   USB_MODULE_ID_INDEX              0x00
#define   USB_CMD_INDEX                    0x01 
#define   USB_SUBCMD_INDEX                 0x02
#define   USB_DATA_INDEX                   0x03

//LA Request CONFIG
#define   LA_SAMPLING_MODE_OFFSET          USB_DATA_INDEX
#define   LA_SAMPLING_MODE_SIZE            1
#define   LA_CHNL_COUNT_OFFSET             (LA_SAMPLING_MODE_OFFSET + LA_SAMPLING_MODE_SIZE)
#define   LA_CHNL_COUNT_SIZE               1
#define   LA_SAMPLE_COUNT_OFFSET           (LA_CHNL_COUNT_OFFSET + LA_CHNL_COUNT_SIZE)
#define   LA_SAMPLE_COUNT_SIZE             4
#define   LA_SAMPLE_FREQ_SRC_OFFSET        (LA_SAMPLE_COUNT_OFFSET + LA_SAMPLE_COUNT_SIZE)
#define   LA_SAMPLE_FREQ_SRC_SIZE          1
#define   LA_SAMPLE_FREQ_CONF_OFFSET       (LA_SAMPLE_FREQ_SRC_OFFSET + LA_SAMPLE_FREQ_SRC_SIZE)
#define   LA_SAMPLE_FREQ_CONF_SIZE         9
#define   LA_DMA_STREAMS_COUNT_OFFSET      (LA_SAMPLE_FREQ_CONF_OFFSET + LA_SAMPLE_FREQ_CONF_SIZE)
#define   LA_DMA_STREAMS_COUNT_SIZE        1
#define   LA_CHNL_TRIG_ACTIVE_OFFSET       (LA_DMA_STREAMS_COUNT_OFFSET + LA_DMA_STREAMS_COUNT_SIZE)
#define   LA_CHNL_TRIG_ACTIVE_SIZE         1
#define   LA_CHNL_TRIG_TIM_PSC_OFFSET      (LA_CHNL_TRIG_ACTIVE_OFFSET + LA_CHNL_TRIG_ACTIVE_SIZE)
#define   LA_CHNL_TRIG_TIM_PSC_SIZE        2
#define   LA_CHNL_TRIG_TIM_ARR_OFFSET      (LA_CHNL_TRIG_TIM_PSC_OFFSET + LA_CHNL_TRIG_TIM_PSC_SIZE)
#define   LA_CHNL_TRIG_TIM_ARR_SIZE        2
#define   LA_CHNL_TRIG_SET_OFFSET          (LA_CHNL_TRIG_TIM_ARR_OFFSET + LA_CHNL_TRIG_TIM_ARR_SIZE)
#define   LA_CHNL_TRIG_SET_SIZE            32
#define   LA_EDGE_TRIG_SET_OFFSET          (LA_CHNL_TRIG_SET_OFFSET + LA_CHNL_TRIG_SET_SIZE)
#define   LA_EDGE_TRIG_SET_SIZE            1

//LA Request CONFIG Internal Frequency
#define   LA_PLL_RECONFIG_OFFSET           LA_SAMPLE_FREQ_CONF_OFFSET
#define   LA_PLL_RECONFIG_SIZE             1
#define   LA_PLL_M_VALUE_OFFSET            (LA_PLL_RECONFIG_OFFSET + LA_PLL_RECONFIG_SIZE)
#define   LA_PLL_M_VALUE_SIZE              1
#define   LA_PLL_N_VALUE_OFFSET            (LA_PLL_M_VALUE_OFFSET + LA_PLL_M_VALUE_SIZE)
#define   LA_PLL_N_VALUE_SIZE              2
#define   LA_PLL_P_VALUE_OFFSET            (LA_PLL_N_VALUE_OFFSET + LA_PLL_N_VALUE_SIZE)
#define   LA_PLL_P_VALUE_SIZE              1
#define   LA_SAMPLE_TIM_PSC_OFFSET         (LA_PLL_P_VALUE_OFFSET + LA_PLL_P_VALUE_SIZE)
#define   LA_SAMPLE_TIM_PSC_SIZE           2
#define   LA_SAMPLE_TIM_ARR_OFFSET         (LA_SAMPLE_TIM_PSC_OFFSET + LA_SAMPLE_TIM_PSC_SIZE)
#define   LA_SAMPLE_TIM_ARR_SIZE           2

//LA Request CONFIG External EDGE
#define   LA_EXT_EDGE_ACTIVE_EDGE_OFFSET   LA_SAMPLE_FREQ_CONF_OFFSET
#define   LA_EXT_EDGE_ACTIVE_EDGE_SIZE     1
#define   LA_EXT_EDGE_RESERVE_OFFSET       (LA_EXT_EDGE_ACTIVE_EDGE_OFFSET + LA_EXT_EDGE_ACTIVE_EDGE_SIZE)
#define   LA_EXT_EDGE_RESERVE_SIZE         8

//LA Request CONFIG External CLK
#define   LA_EXT_CLK_DIVIDER_OFFSET        LA_SAMPLE_FREQ_CONF_OFFSET
#define   LA_EXT_CLK_DIVIDER_SIZE          1
#define   LA_EXT_CLK_ACTIVE_PULSE_OFFSET   (LA_EXT_CLK_DIVIDER_OFFSET + LA_EXT_CLK_DIVIDER_SIZE)
#define   LA_EXT_CLK_ACTIVE_PULSE_SIZE     1
#define   LA_EXT_CLK_RESERVE_OFFSET        (LA_EXT_CLK_ACTIVE_PULSE_OFFSET + LA_EXT_CLK_ACTIVE_PULSE_SIZE)
#define   LA_EXT_CLK_RESERVE_SIZE          7

//PWM Output Request
#define   PWM_1_CHNLS_MASK_OFFSET          USB_DATA_INDEX
#define   PWM_1_CHNLS_MASK_SIZE            1
#define   PWM_1_TIM_PSC_OFFSET             (PWM_1_CHNLS_MASK_OFFSET + PWM_1_CHNLS_MASK_SIZE)
#define   PWM_1_TIM_PSC_SIZE               2
#define   PWM_1_TIM_ARR_OFFSET             (PWM_1_TIM_PSC_OFFSET + PWM_1_TIM_PSC_SIZE)
#define   PWM_1_TIM_ARR_SIZE               2
#define   PWM_1_CCR_M15_OFFSET             (PWM_1_TIM_ARR_OFFSET + PWM_1_TIM_ARR_SIZE)
#define   PWM_1_CCR_M15_SIZE               2
#define   PWM_1_CCR_M16_OFFSET             (PWM_1_CCR_M15_OFFSET + PWM_1_CCR_M15_SIZE)
#define   PWM_1_CCR_M16_SIZE               2
#define   PWM_1_CCR_M17_OFFSET             (PWM_1_CCR_M16_OFFSET + PWM_1_CCR_M16_SIZE)
#define   PWM_1_CCR_M17_SIZE               2
#define   PWM_2_CHNLS_MASK_OFFSET          (PWM_1_CCR_M17_OFFSET + PWM_1_CCR_M17_SIZE)
#define   PWM_2_CHNLS_MASK_SIZE            1
#define   PWM_2_TIM_PSC_OFFSET             (PWM_2_CHNLS_MASK_OFFSET + PWM_2_CHNLS_MASK_SIZE)
#define   PWM_2_TIM_PSC_SIZE               2
#define   PWM_2_TIM_ARR_OFFSET             (PWM_2_TIM_PSC_OFFSET + PWM_2_TIM_PSC_SIZE)
#define   PWM_2_TIM_ARR_SIZE               2
#define   PWM_2_CCR_M18_OFFSET             (PWM_2_TIM_ARR_OFFSET + PWM_2_TIM_ARR_SIZE)
#define   PWM_2_CCR_M18_SIZE               2
#define   PWM_2_CCR_M19_OFFSET             (PWM_2_CCR_M18_OFFSET + PWM_2_CCR_M18_SIZE)
#define   PWM_2_CCR_M19_SIZE               2

//PWM Input Request (Pulse measurement)
#define   PWM_INPUT_TIM_PSC_OFFSET         USB_DATA_INDEX
#define   PWM_INPUT_TIM_PSC_SIZE           2

//PWM Input Get Data
#define   PWM_INPUT_PERIOD_OFFSET          0
#define   PWM_INPUT_PERIOD_SIZE            2
#define   PWM_INPUT_DUTY_CYCLE_OFFSET      (PWM_INPUT_PERIOD_OFFSET + PWM_INPUT_PERIOD_SIZE)
#define   PWM_INPUT_DUTY_CYCLE_SIZE        2


#define   USB_DATA_CONTROLLER_ID_INDEX     USB_DATA_INDEX
#define   USB_DATA_FIRMWARE_INDEX          (USB_DATA_CONTROLLER_ID_INDEX + 1)
#define   USB_DATA_MEMORY_SIZE_INDEX       (USB_DATA_FIRMWARE_INDEX + 4)
#define   USB_DATA_HARDWARE_INDEX          (USB_DATA_MEMORY_SIZE_INDEX + 2)

#define   USB_DATA_DMA_CNT_REMAIN_INDEX    (USB_DATA_INDEX + 1)
#define   USB_DATA_DMA_CNT_REMAIN_SIZE     2


enum CMDTypes
{ 
  MODULE_SYSTEM = 0,
  MODULE_LA,
  MODULE_PWM,
  MODULE_PWM_INPUT,
};

enum SYS_CMDs
{
  SYS_CMD_GET_ID = 4,
  SYS_CMD_GET_STATUS,
};

enum SYS_STATEs
{
  LA_TRIGGER_AWAIT = (1 << 0),
  LA_SAMPLING_CMP = (1 << 1),
};

enum LA_CMDs
{ 
  LA_CMD_CONFIG = 0,
  LA_CMD_GET_SAMPLES,
  LA_CMD_SAMPLE_STOP,
};

enum LA_SAMPLING_MODES
{
  LA_BUFFER_MODE = 0,
  LA_STREAM_MODE,
};

enum LA_TRIGActivity
{ 
  LA_TRIG_NOT_ACTIVE = 0,
  LA_TRIG_ACTIVE,
};

enum LA_TRIGGERS
{ 
  TRIGGER_NONE = 0,
  TRIGGER_LOW_LEVEL,
  TRIGGER_HIGH_LEVEL,
  TRIGGER_RISING_EDGE,
  TRIGGER_FALLING_EDGE,
  TRIGGER_ANY_EDGE,
};

enum PWM_INPUT_CMDs
{ 
  PWM_INPUT_CMD_CONFIG = 0,
  PWM_INPUT_CMD_GET_DATA,
  PWM_INPUT_CMD_STOP,
};



#endif //__USB_PROTOCOL_H




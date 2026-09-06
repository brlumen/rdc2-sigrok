/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


#include "USBPort.h"
#include "usbd_desc.h"
#include "USBPtorocol.h"
#include "LED.h"


volatile uint8_t PrevXferDone = 1;
USBD_HandleTypeDef USBD_Device;
extern USBD_CDC_ItfTypeDef  USBD_CDC_fops;
static volatile uint8_t USBStatus = USB_PORT_IDLE;
static volatile uint8_t SystemStatus = 0;
static volatile uint8_t USBDataBuf[USB_Tx_LENGTH];


void USBPort_Init()
{
  USBD_Init(&USBD_Device, &VCP_Desc, 0);
  USBD_RegisterClass(&USBD_Device, USBD_CDC_CLASS);
  USBD_CDC_RegisterInterface(&USBD_Device, &USBD_CDC_fops);
  USBD_Start(&USBD_Device);
}
//------------------------------------------------------------------------------
void USBPort_RecPacket(uint8_t *Packet)
{
  for (uint8_t i = 0; i < USB_Rx_LENGTH; i++)
    USBDataBuf[i] = *(Packet + i);
  
  if ((*(USBDataBuf + USB_MODULE_ID_INDEX)) == MODULE_SYSTEM)
  {
    switch(*(USBDataBuf + USB_CMD_INDEX))
    {
      case SYS_CMD_GET_ID:
        USBDataBuf[USB_DATA_CONTROLLER_ID_INDEX] = RDC2_0064_ID;
        USBDataBuf[USB_DATA_FIRMWARE_INDEX] = FIRMWARE_VERSION_BYTE_1;
        USBDataBuf[USB_DATA_FIRMWARE_INDEX + 1] = FIRMWARE_VERSION_BYTE_2;
        USBDataBuf[USB_DATA_FIRMWARE_INDEX + 2] = FIRMWARE_VERSION_BYTE_3;
        USBDataBuf[USB_DATA_FIRMWARE_INDEX + 3] = FIRMWARE_VERSION_BYTE_4;
        USBDataBuf[USB_DATA_HARDWARE_INDEX] = HARDWARE_VERSION;
        LED_ON();
      break;
      
      case SYS_CMD_GET_STATUS:
        USBDataBuf[USB_DATA_INDEX] = SystemStatus;
        uint16_t DMACntRemain = CHNL_0_15_TIM_UPD_DMA->NDTR;
        USBDataBuf[USB_DATA_DMA_CNT_REMAIN_INDEX] = DMACntRemain;
        USBDataBuf[USB_DATA_DMA_CNT_REMAIN_INDEX + 1] = DMACntRemain >> 8;
      break;
    }
    
    USBPort_SetBufAndSend((uint8_t *)USBDataBuf, USB_Tx_LENGTH);
  }
  else
    USBStatus |= USB_PORT_MODULE_REQUEST;
}
//------------------------------------------------------------------------------
void USBPort_SetBufAndSend(uint8_t *Data, uint32_t Length)
{  
  while(PrevXferDone != 1);
  USBD_CDC_SetTxBuffer(&USBD_Device, Data, Length);
  USBD_CDC_TransmitPacket(&USBD_Device);
  PrevXferDone = 0;
}
//------------------------------------------------------------------------------
volatile uint8_t* USBPort_GetStatus()
{
  return &USBStatus;
}
//------------------------------------------------------------------------------
void USBPort_ClearStatus(uint8_t StatusFlag)
{
  USBStatus &= ~StatusFlag;
}
//------------------------------------------------------------------------------
void USBPort_SetStatus(uint8_t StatusFlag)
{
  USBStatus |= StatusFlag;
}
//------------------------------------------------------------------------------
void USBPort_ClearSystemStatus(uint8_t StatusFlag)
{
  SystemStatus &= ~StatusFlag;
}
//------------------------------------------------------------------------------
void USBPort_SetSystemStatus(uint8_t StatusFlag)
{
  SystemStatus |= StatusFlag;
}
//------------------------------------------------------------------------------
volatile uint8_t* USBPort_GetPacket()
{
  return USBDataBuf;
}
//------------------------------------------------------------------------------
void USBPort_WhileNotReadyToSend()
{
  while(PrevXferDone != 1);
}




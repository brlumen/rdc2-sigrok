/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2020
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


#ifndef __USBPORT_H
#define __USBPORT_H



#include "Board.h"
#include "usbd_cdc.h"



#define   USB_Rx_LENGTH                    0x40
#define   USB_Tx_LENGTH                    0x200


//Status
#define   USB_PORT_IDLE                    0
#define   USB_PORT_MODULE_REQUEST          (1 << 1)





void USBPort_Init();

void USBPort_RecPacket(uint8_t *Packet);

void USBPort_SetBufAndSend(uint8_t *Data, uint32_t Length);

volatile uint8_t* USBPort_GetStatus();

void USBPort_ClearStatus(uint8_t StatusFlag);

void USBPort_SetStatus(uint8_t StatusFlag);

void USBPort_ClearSystemStatus(uint8_t StatusFlag);

void USBPort_SetSystemStatus(uint8_t StatusFlag);

volatile uint8_t* USBPort_GetPacket();

void USBPort_WhileNotReadyToSend();


#endif //__USBPORT_H

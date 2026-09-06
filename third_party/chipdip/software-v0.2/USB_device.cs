/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2017
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using LibUsbDotNet;
using LibUsbDotNet.Main;
using System.Windows;

namespace RDC2_0064
{
    class USB_device
    {
        private const Int32 DEV_VID = 0x0483;
        private const Int32 DEV_PID = 0xA210;
        private const Int32 USBWriteTimeOut = 5000;
        private const Int32 USBReadTimeOut = 5000;
        
        static UsbDevice USBDev;
        static UsbEndpointWriter USBDevWriter;
        static UsbEndpointReader USBDevReader;


        //--------------------------------------------------------------------------------------------------------
        public static Boolean Open()
        {
            UsbDeviceFinder ChipDipUSBDevice = new UsbDeviceFinder(DEV_VID, DEV_PID);

            USBDev = UsbDevice.OpenUsbDevice(ChipDipUSBDevice);

            if (USBDev == null)
                return false;
            
            IUsbDevice wholeUsbDevice = USBDev as IUsbDevice;
            if (!ReferenceEquals(wholeUsbDevice, null))
            {
                wholeUsbDevice.SetConfiguration(1);
                wholeUsbDevice.ClaimInterface(1);
                //wholeUsbDevice.ClaimInterface(0);
            }

            USBDevReader = USBDev.OpenEndpointReader(ReadEndpointID.Ep01, 470 * 512, EndpointType.Bulk);
            USBDevWriter = USBDev.OpenEndpointWriter(WriteEndpointID.Ep01, EndpointType.Bulk);

            return true;
        }
        //--------------------------------------------------------------------------------------------------------
        public static void Close()
        {
            if (USBDev != null)
            {
                if (USBDev.IsOpen)
                {
                    IUsbDevice wholeUsbDevice = USBDev as IUsbDevice;
                    if (!ReferenceEquals(wholeUsbDevice, null))
                    {
                        wholeUsbDevice.ReleaseInterface(0);
                    }

                    USBDev.Close();
                }

                USBDev = null;

                UsbDevice.Exit();
            }
        }
        //--------------------------------------------------------------------------------------------------------
        public static Boolean Write(byte[] Buffer)
        {
            ErrorCode USB_Error = ErrorCode.None;
            Int32 BytesWritten = 0;

            if (USBDevWriter == null)
                return false;

            USB_Error = USBDevWriter.Write(Buffer, USBWriteTimeOut, out BytesWritten);

            if ((USB_Error != ErrorCode.None) || (BytesWritten != Buffer.Length))
                return false;

            return true;
        }
        //--------------------------------------------------------------------------------------------------------
        public static Boolean Read(byte[] Buffer)
        {
            ErrorCode USB_Error = ErrorCode.None;
            Int32 BytesRead = 0;

            if (USBDevReader == null)
                return false;

            USB_Error = USBDevReader.Read(Buffer, USBReadTimeOut, out BytesRead);

            if ((USB_Error != ErrorCode.None) || (BytesRead != Buffer.Length))
            {
                if (Buffer.Length != 1)
                    return false;
            }

            return true;
        }
    }
}

/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;

namespace RDC2_0064
{
    public class USBDriver
    {
        private const byte RDC2_0064_ID = 5;

        private const int USB_OUT_PACKET_SIZE = 64;
        private const int USB_IN_PACKET_SIZE = 512;
        private const int USB_ZERO_PACKET_SIZE = 1;

        //CMD Header
        private const byte USB_MODULE_ID_INDEX = 0x00;
        private const byte USB_CMD_INDEX = 0x01;
        private const byte USB_SUBCMD_INDEX = 0x02;
        private const byte USB_DATA_INDEX = 0x03;

        //LA Request CONFIG
        private const byte LA_SAMPLING_MODE_OFFSET = USB_DATA_INDEX;
        private const byte LA_SAMPLING_MODE_SIZE = 1;
        private const byte LA_CHNL_COUNT_OFFSET = (LA_SAMPLING_MODE_OFFSET + LA_SAMPLING_MODE_SIZE);
        private const byte LA_CHNL_COUNT_SIZE = 1;
        private const byte LA_SAMPLE_COUNT_OFFSET = (LA_CHNL_COUNT_OFFSET + LA_CHNL_COUNT_SIZE);
        private const byte LA_SAMPLE_COUNT_SIZE = 4;
        private const byte LA_SAMPLE_FREQ_SRC_OFFSET = (LA_SAMPLE_COUNT_OFFSET + LA_SAMPLE_COUNT_SIZE);
        private const byte LA_SAMPLE_FREQ_SRC_SIZE = 1;
        private const byte LA_SAMPLE_FREQ_CONF_OFFSET = (LA_SAMPLE_FREQ_SRC_OFFSET + LA_SAMPLE_FREQ_SRC_SIZE);
        private const byte LA_SAMPLE_FREQ_CONF_SIZE = 9;
        private const byte LA_DMA_STREAMS_COUNT_OFFSET = (LA_SAMPLE_FREQ_CONF_OFFSET + LA_SAMPLE_FREQ_CONF_SIZE);
        private const byte LA_DMA_STREAMS_COUNT_SIZE = 1;
        private const byte LA_CHNL_TRIG_ACTIVE_OFFSET = (LA_DMA_STREAMS_COUNT_OFFSET + LA_DMA_STREAMS_COUNT_SIZE);
        private const byte LA_CHNL_TRIG_ACTIVE_SIZE = 1;
        private const byte LA_CHNL_TRIG_TIM_PSC_OFFSET = (LA_CHNL_TRIG_ACTIVE_OFFSET + LA_CHNL_TRIG_ACTIVE_SIZE);
        private const byte LA_CHNL_TRIG_TIM_PSC_SIZE = 2;
        private const byte LA_CHNL_TRIG_TIM_ARR_OFFSET = (LA_CHNL_TRIG_TIM_PSC_OFFSET + LA_CHNL_TRIG_TIM_PSC_SIZE);
        private const byte LA_CHNL_TRIG_TIM_ARR_SIZE = 2;
        private const byte LA_CHNL_TRIG_SET_OFFSET = (LA_CHNL_TRIG_TIM_ARR_OFFSET + LA_CHNL_TRIG_TIM_ARR_SIZE);
        private const byte LA_CHNL_TRIG_SET_SIZE = 32;
        private const byte LA_EDGE_TRIG_SET_OFFSET = (LA_CHNL_TRIG_SET_OFFSET + LA_CHNL_TRIG_SET_SIZE);
        private const byte LA_EDGE_TRIG_SET_SIZE = 1;
        
        //LA Request CONFIG Internal Frequency
        private const byte LA_PLL_RECONFIG_OFFSET = LA_SAMPLE_FREQ_CONF_OFFSET;
        private const byte LA_PLL_RECONFIG_SIZE = 1;
        private const byte LA_PLL_M_VALUE_OFFSET = (LA_PLL_RECONFIG_OFFSET + LA_PLL_RECONFIG_SIZE);
        private const byte LA_PLL_M_VALUE_SIZE = 1;
        private const byte LA_PLL_N_VALUE_OFFSET = (LA_PLL_M_VALUE_OFFSET + LA_PLL_M_VALUE_SIZE);
        private const byte LA_PLL_N_VALUE_SIZE = 2;
        private const byte LA_PLL_P_VALUE_OFFSET = (LA_PLL_N_VALUE_OFFSET + LA_PLL_N_VALUE_SIZE);
        private const byte LA_PLL_P_VALUE_SIZE = 1;
        private const byte LA_SAMPLE_TIM_PSC_OFFSET = (LA_PLL_P_VALUE_OFFSET + LA_PLL_P_VALUE_SIZE);
        private const byte LA_SAMPLE_TIM_PSC_SIZE = 2;
        private const byte LA_SAMPLE_TIM_ARR_OFFSET = (LA_SAMPLE_TIM_PSC_OFFSET + LA_SAMPLE_TIM_PSC_SIZE);
        private const byte LA_SAMPLE_TIM_ARR_SIZE = 2;

        //LA Request CONFIG External EDGE
        private const byte LA_EXT_EDGE_ACTIVE_EDGE_OFFSET = LA_SAMPLE_FREQ_CONF_OFFSET;
        private const byte LA_EXT_EDGE_ACTIVE_EDGE_SIZE = 1;
        private const byte LA_EXT_EDGE_RESERVE_OFFSET = (LA_EXT_EDGE_ACTIVE_EDGE_OFFSET + LA_EXT_EDGE_ACTIVE_EDGE_SIZE);
        private const byte LA_EXT_EDGE_RESERVE_SIZE = 8;

        //LA Request CONFIG External CLK
        private const byte LA_EXT_CLK_DIVIDER_OFFSET = LA_SAMPLE_FREQ_CONF_OFFSET;
        private const byte LA_EXT_CLK_DIVIDER_SIZE = 1;
        private const byte LA_EXT_CLK_ACTIVE_PULSE_OFFSET = (LA_EXT_CLK_DIVIDER_OFFSET + LA_EXT_CLK_DIVIDER_SIZE);
        private const byte LA_EXT_CLK_ACTIVE_PULSE_SIZE = 1;
        private const byte LA_EXT_CLK_RESERVE_OFFSET = (LA_EXT_CLK_ACTIVE_PULSE_OFFSET + LA_EXT_CLK_ACTIVE_PULSE_SIZE);
        private const byte LA_EXT_CLK_RESERVE_SIZE = 7;

        //PWM Request
        private const byte PWM_1_CHNLS_MASK_OFFSET = USB_DATA_INDEX;
        private const byte PWM_1_CHNLS_MASK_SIZE = 1;
        private const byte PWM_1_TIM_PSC_OFFSET = (PWM_1_CHNLS_MASK_OFFSET + PWM_1_CHNLS_MASK_SIZE);
        private const byte PWM_1_TIM_PSC_SIZE = 2;
        private const byte PWM_1_TIM_ARR_OFFSET = (PWM_1_TIM_PSC_OFFSET + PWM_1_TIM_PSC_SIZE);
        private const byte PWM_1_TIM_ARR_SIZE = 2;
        private const byte PWM_1_CCR_M15_OFFSET = (PWM_1_TIM_ARR_OFFSET + PWM_1_TIM_ARR_SIZE);
        private const byte PWM_1_CCR_M15_SIZE = 2;
        private const byte PWM_1_CCR_M16_OFFSET = (PWM_1_CCR_M15_OFFSET + PWM_1_CCR_M15_SIZE);
        private const byte PWM_1_CCR_M16_SIZE = 2;
        private const byte PWM_1_CCR_M17_OFFSET = (PWM_1_CCR_M16_OFFSET + PWM_1_CCR_M16_SIZE);
        private const byte PWM_1_CCR_M17_SIZE = 2;
        private const byte PWM_2_CHNLS_MASK_OFFSET = (PWM_1_CCR_M17_OFFSET + PWM_1_CCR_M17_SIZE);
        private const byte PWM_2_CHNLS_MASK_SIZE = 1;
        private const byte PWM_2_TIM_PSC_OFFSET = (PWM_2_CHNLS_MASK_OFFSET + PWM_2_CHNLS_MASK_SIZE);
        private const byte PWM_2_TIM_PSC_SIZE = 2;
        private const byte PWM_2_TIM_ARR_OFFSET = (PWM_2_TIM_PSC_OFFSET + PWM_2_TIM_PSC_SIZE);
        private const byte PWM_2_TIM_ARR_SIZE = 2;
        private const byte PWM_2_CCR_M18_OFFSET = (PWM_2_TIM_ARR_OFFSET + PWM_2_TIM_ARR_SIZE);
        private const byte PWM_2_CCR_M18_SIZE = 2;
        private const byte PWM_2_CCR_M19_OFFSET = (PWM_2_CCR_M18_OFFSET + PWM_2_CCR_M18_SIZE);
        private const byte PWM_2_CCR_M19_SIZE = 2;

        //PWM Input Request (Pulse measurement)
        private const byte PWM_INPUT_TIM_PSC_OFFSET = USB_DATA_INDEX;
        private const byte PWM_INPUT_TIM_PSC_SIZE = 2;

        //PWM Input Get Data
        private const byte PWM_INPUT_PERIOD_OFFSET = 0;
        private const byte PWM_INPUT_PERIOD_SIZE = 2;
        private const byte PWM_INPUT_DUTY_CYCLE_OFFSET = (PWM_INPUT_PERIOD_OFFSET + PWM_INPUT_PERIOD_SIZE);
        private const byte PWM_INPUT_DUTY_CYCLE_SIZE = 2;


        private const byte LA_STREAM_OVERSAMPLE_OFFSET = 0;
        private const byte LA_STREAM_OVERSAMPLE_SIZE = 1;
        private const byte LA_STREAM_VALID_PACKETS_OFFSET = (LA_STREAM_OVERSAMPLE_OFFSET + LA_STREAM_OVERSAMPLE_SIZE);
        private const byte LA_STREAM_VALID_PACKETS_SIZE = 4;

        private const byte USB_DATA_CONTROLLER_ID_INDEX = USB_DATA_INDEX;
        private const byte USB_DATA_FIRMWARE_INDEX = (USB_DATA_CONTROLLER_ID_INDEX + 1);
        private const byte USB_DATA_MEMORY_SIZE_INDEX = (USB_DATA_FIRMWARE_INDEX + 4);
        private const byte USB_DATA_HARDWARE_INDEX = (USB_DATA_MEMORY_SIZE_INDEX + 2);

        private const byte USB_DATA_DMA_CNT_REMAIN_INDEX = (USB_DATA_INDEX + 1);
        private const byte USB_DATA_DMA_CNT_REMAIN_SIZE = 2;

        //CMDTypes
        private const byte MODULE_SYSTEM = 0;
        private const byte MODULE_LA = 1;
        private const byte MODULE_PWM = 2;
        private const byte MODULE_PWM_INPUT = 3;

        //SYS_CMDs
        private const byte SYS_CMD_GET_ID = 4;
        private const byte SYS_CMD_GET_STATUS = 5;

        //LA_CMDs
        private const byte LA_CMD_CONFIG = 0;
        private const byte LA_CMD_GET_SAMPLES = 1;
        private const byte LA_CMD_SAMPLE_STOP = 2;

        //SYS_STATEs
        private const byte LA_TRIGGER_AWAIT = (1 << 0);
        private const byte LA_SAMPLING_CMP = (1 << 1);

        private const byte LA_TRIG_NOT_ACTIVE = 0;
        private const byte LA_TRIG_ACTIVE = 1;

        //LA_SAMPLING_MODES
        private const byte LA_BUFFER_MODE = 0;
        private const byte LA_STREAM_MODE = 1;

        //PWM_INPUT_CMDs
        private const byte PWM_INPUT_CMD_CONFIG = 0;
        private const byte PWM_INPUT_CMD_GET_DATA = 1;
        private const byte PWM_INPUT_CMD_STOP = 2;

        private const byte LA_STREAM_OVERSAMPLE = 1;

        private const int LA_BUFFER_MODE_SAMPLES = 470 * 512;
        private const int LA_STREAM_MODE_SAMPLES = 32 * 512;
        private const int LA_STREAM_MODE_BUFFER_PACKETS = 8192;


        private static readonly string USBMonitorFilter = "VID_0483&PID_A210";
        private const byte USBMonitorCheckPeriod = 2; //second
        

        private USBPlugEvents USBMonitor = new USBPlugEvents(USBMonitorFilter, USBMonitorCheckPeriod);
        private USBDeviceInfo Device = new USBDeviceInfo();
        private DispatcherTimer LATransferTimer = new DispatcherTimer();
        private DispatcherTimer PWMInputTimer = new DispatcherTimer();
        private BackgroundWorker LATransferBackground = new BackgroundWorker();
        private BackgroundWorker LAFileWriteBackground = new BackgroundWorker();
        private byte LACMDPending = 0;
        private long LAStreamSampleCount = 0;
        private long LAStreamPackets = 0;
        private int LAStreamValueBytes = 1;
        private byte[][] LAData;
        private byte[] USBCmdPacket = new byte[USB_OUT_PACKET_SIZE];
        private bool IsCmdPending = false;
        private bool IsDeviceLost = true;
        private bool FirstTimeAfterStop = false;
        private int StreamBufferPacket = 0;
        private bool StreamBufferOverflow = false;
        private bool StreamFileWriteFinished = false;
        private bool IsStreamCancelledByUser = false;
        private string StreamFile;


        private Action<string> ConnectEvent;
        private Action RemoveEvent;
        public event Action<byte[][], long> LA_DataRx_Complete;
        public event Action<UInt16> LA_DataRx_Progress;
        public event Action<ImpulseData> PWMInput_Data;
        public event Action LA_Stream_Complete;


        public USBDriver(Action<string> ConnectCallBack, Action RemoveCallBack)
        {
            LATransferBackground.WorkerSupportsCancellation = true;
            LATransferBackground.DoWork += LAStreamMode_DoWork;
            LATransferBackground.RunWorkerCompleted += LATransferBackground_RunWorkerCompleted;

            LAFileWriteBackground.WorkerSupportsCancellation = true;
            LAFileWriteBackground.DoWork += LAStreamModeFileWrite_DoWork;
            LAFileWriteBackground.RunWorkerCompleted += LAStreamModeFileWrite_RunWorkerCompleted;


            LATransferTimer.Interval = TimeSpan.FromMilliseconds(100);
            LATransferTimer.Tick += LABufferModeTimer_Tick;

            PWMInputTimer.Interval = TimeSpan.FromMilliseconds(300);
            PWMInputTimer.Tick += PWMInputTimer_Tick;

            ConnectEvent = ConnectCallBack;
            RemoveEvent = RemoveCallBack;
            USBMonitor.AddArrivedEventHandler(DeviceConnectedEvent);
            USBMonitor.AddRemovedEventHandler(DeviceRemovedEvent);
            USBMonitor.Start();

            if (USBMonitor.State == USBPlugEvents.DeviceStates.Arrived)
                DeviceConnectedEvent();
            else
                DeviceRemovedEvent();
        }
        
        public void LA_ConfigAndStart(LASettings Config)
        {
            if (Device.IsConnected == true)
            {
                PWMInputTimer.Stop();

                USBMonitor.Stop();

                byte[] CmdPacket = new byte[USB_OUT_PACKET_SIZE];
                CmdPacket[USB_MODULE_ID_INDEX] = MODULE_LA;
                CmdPacket[USB_CMD_INDEX] = LA_CMD_CONFIG;
                CmdPacket[LA_SAMPLING_MODE_OFFSET] = Config.SamplingMode;
                CmdPacket[LA_CHNL_COUNT_OFFSET] = Config.ChannelsCount;

                LAStreamSampleCount = Config.SampleCount;

                for (int i = 0; i < LA_SAMPLE_COUNT_SIZE; i++)
                    CmdPacket[LA_SAMPLE_COUNT_OFFSET + i] = (byte)(Config.SampleCount >> (8 * i));

                CmdPacket[LA_SAMPLE_FREQ_SRC_OFFSET] = Config.SamplingFreqSource;

                for (int i = 0; i < LA_SAMPLE_TIM_PSC_SIZE; i++)
                    CmdPacket[LA_SAMPLE_TIM_PSC_OFFSET + i] = (byte)(Config.SampleTimPSC >> (8 * i));

                for (int i = 0; i < LA_SAMPLE_TIM_ARR_SIZE; i++)
                    CmdPacket[LA_SAMPLE_TIM_ARR_OFFSET + i] = (byte)(Config.SampleTimARR >> (8 * i));

                CmdPacket[LA_DMA_STREAMS_COUNT_OFFSET] = Config.DMAStreamCount;

                if (Config.IsTriggersActive)
                {
                    CmdPacket[LA_CHNL_TRIG_ACTIVE_OFFSET] = LA_TRIG_ACTIVE;
                    for (int i = 0; i < LogicAnalyzer.CHANNELS_COUNT_MAX; i++)
                        CmdPacket[LA_CHNL_TRIG_SET_OFFSET + i] = Config.Triggers[i];
                }
                else
                    CmdPacket[LA_CHNL_TRIG_ACTIVE_OFFSET] = LA_TRIG_NOT_ACTIVE;

                CmdPacket[LA_EDGE_TRIG_SET_OFFSET] = Config.ExtEdgeTrigger;

                if (Config.SamplingMode == LA_BUFFER_MODE)
                {
                    LAStreamPackets = 1;
                    LAData = new byte[LAStreamPackets][];
                    LAData[0] = new byte[LA_BUFFER_MODE_SAMPLES];
                }
                else
                {
                    LAStreamValueBytes = Config.BytesPerValue;
                    LAStreamPackets = ((LAStreamSampleCount * LAStreamValueBytes) / LA_STREAM_MODE_SAMPLES + 1);
                    LAData = new byte[LA_STREAM_MODE_BUFFER_PACKETS][];
                    for (int i = 0; i < LA_STREAM_MODE_BUFFER_PACKETS; i++)
                        LAData[i] = new byte[LA_STREAM_MODE_SAMPLES];
                }

                if (USB_device.Write(CmdPacket) == false)
                    CommunicationError();

                if (Config.SamplingMode == LA_BUFFER_MODE)
                    LATransferTimer.Start();
                else
                {
                    StreamFile = Config.StreamFilePath;
                    StreamFileWriteFinished = false;
                    IsStreamCancelledByUser = false;
                    LATransferBackground.RunWorkerAsync();
                    LAFileWriteBackground.RunWorkerAsync();
                }
            }
        }

        public void LA_StopSampling()
        {
            if (Device.IsConnected == true)
            {
                if ((LATransferBackground.IsBusy == true)
                 || (LATransferTimer.IsEnabled == true))
                    LACMDPending = LA_CMD_SAMPLE_STOP;
            }
        }

        public void PWM_Config(PWMSettings[] Config)
        {
            if (Device.IsConnected == true)
            {
                USBCmdPacket[USB_MODULE_ID_INDEX] = MODULE_PWM;

                //PWM1
                for (int i = 0; i < PWM_1_TIM_PSC_SIZE; i++)
                    USBCmdPacket[PWM_1_TIM_PSC_OFFSET + i] = (byte)(Config[0].TimPSC >> (8 * i));

                for (int i = 0; i < PWM_1_TIM_ARR_SIZE; i++)
                    USBCmdPacket[PWM_1_TIM_ARR_OFFSET + i] = (byte)(Config[0].TimARR >> (8 * i));

                USBCmdPacket[PWM_1_CHNLS_MASK_OFFSET] = 0;
                for (int chnl = 0; chnl < Config[0].Channels.Length; chnl++)
                {
                    if (Config[0].Channels[chnl].IsActive == true)
                        USBCmdPacket[PWM_1_CHNLS_MASK_OFFSET] |= (byte)(1 << chnl);

                    int Offset = chnl * PWM_1_CCR_M15_SIZE;
                    for (int i = 0; i < PWM_1_CCR_M15_SIZE; i++)
                        USBCmdPacket[PWM_1_CCR_M15_OFFSET + Offset + i] = (byte)(Config[0].Channels[chnl].TimCCR >> (8 * i));
                }

                //PWM2
                for (int i = 0; i < PWM_2_TIM_PSC_SIZE; i++)
                    USBCmdPacket[PWM_2_TIM_PSC_OFFSET + i] = (byte)(Config[1].TimPSC >> (8 * i));

                for (int i = 0; i < PWM_2_TIM_ARR_SIZE; i++)
                    USBCmdPacket[PWM_2_TIM_ARR_OFFSET + i] = (byte)(Config[1].TimARR >> (8 * i));

                for (int chnl = 0; chnl < Config[1].Channels.Length; chnl++)
                {
                    if (Config[1].Channels[chnl].IsActive == true)
                        USBCmdPacket[PWM_2_CHNLS_MASK_OFFSET] |= (byte)(1 << chnl);

                    int Offset = chnl * PWM_2_CCR_M18_SIZE;
                    for (int i = 0; i < PWM_2_CCR_M18_SIZE; i++)
                        USBCmdPacket[PWM_2_CCR_M18_OFFSET + Offset + i] = (byte)(Config[1].Channels[chnl].TimCCR >> (8 * i));
                }

                if (PWMInputTimer.IsEnabled == false)
                {
                    USBMonitor.Stop();
                    if (USB_device.Write(USBCmdPacket) == false)
                        CommunicationError();
                    USBMonitor.Start();
                }
                else
                    IsCmdPending = true;
            }
        }

        public void PWMInput_Config(UInt16 TimPSC)
        {
            if (Device.IsConnected == true)
            {
                USBCmdPacket[USB_MODULE_ID_INDEX] = MODULE_PWM_INPUT;
                USBCmdPacket[USB_CMD_INDEX] = PWM_INPUT_CMD_CONFIG;

                for (int i = 0; i < PWM_INPUT_TIM_PSC_SIZE; i++)
                    USBCmdPacket[PWM_INPUT_TIM_PSC_OFFSET + i] = (byte)(TimPSC >> (8 * i));

                if (PWMInputTimer.IsEnabled == false)
                {
                    USBMonitor.Stop();
                    if (USB_device.Write(USBCmdPacket) == false)
                        CommunicationError();
                    PWMInputTimer.Start();
                }
                else
                    IsCmdPending = true;
            }
        }

        public void PWMInput_Stop()
        {
            if (Device.IsConnected == true)
            {
                SendCMD(MODULE_PWM_INPUT, PWM_INPUT_CMD_STOP);
                PWMInputTimer.Stop();
                USBMonitor.Start();
            }
        }

        public void Close()
        {
            USB_device.Close();
        }

        private void PWMInputTimer_Tick(object sender, EventArgs e)
        {
            byte[] PWMInputData = new byte[USB_IN_PACKET_SIZE];
            SendCMD(MODULE_PWM_INPUT, PWM_INPUT_CMD_GET_DATA, ref PWMInputData);

            ImpulseData NewData = new ImpulseData();
            NewData.Period = (UInt16)(PWMInputData[PWM_INPUT_PERIOD_OFFSET] |
                                     (PWMInputData[PWM_INPUT_PERIOD_OFFSET + 1] << 8));
            NewData.Width = (UInt16)(PWMInputData[PWM_INPUT_DUTY_CYCLE_OFFSET] |
                                     (PWMInputData[PWM_INPUT_DUTY_CYCLE_OFFSET + 1] << 8));

            PWMInput_Data?.Invoke(NewData);

            if (IsCmdPending == true)
            {
                IsCmdPending = false;
                if (USB_device.Write(USBCmdPacket) == false)
                    CommunicationError();
            }
        }

        private void LAStreamMode_DoWork(object sender, DoWorkEventArgs e)
        {
            int PacketCounter = 0;
            StreamBufferPacket = 0;
            while (PacketCounter < LAStreamPackets)
            {
                if (LACMDPending != 0)
                {
                    LACMDPending = 0;
                    IsStreamCancelledByUser = true;
                    break;
                }

                SendCMD(MODULE_LA, LA_CMD_GET_SAMPLES, ref LAData[StreamBufferPacket]);
                PacketCounter++;
                StreamBufferPacket++;
                if (StreamBufferPacket == LA_STREAM_MODE_BUFFER_PACKETS)
                {
                    StreamBufferPacket = 0;
                    StreamBufferOverflow = true;
                }

                if (LATransferBackground.CancellationPending == true)
                {
                    IsStreamCancelledByUser = true;
                    return;
                }
            }
            
            byte[] StatusData = new byte[USB_IN_PACKET_SIZE];
            SendCMD(MODULE_LA, LA_CMD_SAMPLE_STOP, ref StatusData);
            if (LATransferBackground.CancellationPending == true)
                return;
            
            int ValidPackets = 0;
            for (int i = 0; i < LA_STREAM_VALID_PACKETS_SIZE; i++)
                ValidPackets |= StatusData[LA_STREAM_VALID_PACKETS_OFFSET + i] << (8 * i);

            LAStreamSampleCount = (long)(ValidPackets) * LA_STREAM_MODE_SAMPLES / LAStreamValueBytes;

            while (StreamFileWriteFinished == false);
                        
            LA_DataRx_Complete?.Invoke(LAData, LAStreamSampleCount);

            LAData = null;
            USBMonitor.Start();
        }

        private void LATransferBackground_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            LA_Stream_Complete?.Invoke();
        }

        private void LAStreamModeFileWrite_DoWork(object sender, DoWorkEventArgs e)
        {
            using (Stream LAStreamData = new FileStream(StreamFile, FileMode.Append, FileAccess.Write))
            {
                int FileChunck = 0;
                long ChunkCounter = 0;
                byte[] DataBuf = new byte[LA_STREAM_MODE_SAMPLES];

                while (StreamBufferPacket == 0);                    
                while ((ChunkCounter < LAStreamPackets) && (IsStreamCancelledByUser == false))
                {
                    while ((StreamBufferOverflow == false) && (FileChunck >= StreamBufferPacket)
                        && (IsStreamCancelledByUser == false));
                    
                    if (LAStreamValueBytes != 4)
                        LAStreamData.Write(LAData[FileChunck], 0, LA_STREAM_MODE_SAMPLES);
                    else
                    {
                        for (int data = 0; data < (LA_STREAM_MODE_SAMPLES / 2); data += 2)
                        {
                            int Offset = 2 * data;

                            DataBuf[Offset] = LAData[FileChunck][data];
                            DataBuf[Offset + 1] = LAData[FileChunck][data + 1];
                            DataBuf[Offset + 2] = LAData[FileChunck][(LA_STREAM_MODE_SAMPLES / 2) + data];
                            DataBuf[Offset + 3] = LAData[FileChunck][(LA_STREAM_MODE_SAMPLES / 2) + data + 1];
                        }

                        LAStreamData.Write(DataBuf, 0, LA_STREAM_MODE_SAMPLES);
                    }
                                        
                    ChunkCounter++;
                    FileChunck++;
                    if (FileChunck == LA_STREAM_MODE_BUFFER_PACKETS)
                    {
                        FileChunck = 0;
                        while ((StreamBufferPacket == 0) && (IsStreamCancelledByUser == false));
                        StreamBufferOverflow = false;
                    }
                }
            }
        }

        private void LAStreamModeFileWrite_RunWorkerCompleted(object sender, RunWorkerCompletedEventArgs e)
        {
            StreamFileWriteFinished = true;
        }

        private void LABufferModeTimer_Tick(object sender, EventArgs e)
        {
            if (LACMDPending == 0)
            {
                byte[] DevStatus = GetDeviceSystemStatus();
                
                if ((DevStatus[USB_DATA_INDEX] & LA_SAMPLING_CMP) == LA_SAMPLING_CMP)
                {
                    SendCMD(MODULE_LA, LA_CMD_GET_SAMPLES, ref LAData[0]);

                    LATransferTimer.Stop();
                    LA_DataRx_Complete?.Invoke(LAData, LA_BUFFER_MODE_SAMPLES);
                    LAData = null;
                    USBMonitor.Start();
                }
                else
                {
                    if (FirstTimeAfterStop == false)
                    {
                        UInt16 RemainigSamples = 0;
                        for (int i = 0; i < USB_DATA_DMA_CNT_REMAIN_SIZE; i++)
                            RemainigSamples |= (UInt16)(DevStatus[USB_DATA_DMA_CNT_REMAIN_INDEX + i] << (8 * i));

                        LA_DataRx_Progress?.Invoke(RemainigSamples);
                    }
                    else
                        FirstTimeAfterStop = false;
                }
            }
            else
            {
                SendCMD(MODULE_LA, LACMDPending);
                LACMDPending = 0;
                FirstTimeAfterStop = true;
                LATransferTimer.Stop();
                LAData = null;
                USBMonitor.Start();
            }
        }
        
        private void DeviceConnectedEvent()
        {
            USB_device.Open();

            IsDeviceLost = false;
            byte[] DeviceInfo = GetDeviceInfo();

            if (DeviceInfo[USB_DATA_CONTROLLER_ID_INDEX] == RDC2_0064_ID)
            {
                Device.IsConnected = true;
                Device.Firmware = DeviceInfo[USB_DATA_FIRMWARE_INDEX].ToString() + "."
                                + DeviceInfo[USB_DATA_FIRMWARE_INDEX + 1].ToString() + "."
                                + ((DeviceInfo[USB_DATA_FIRMWARE_INDEX + 2] << 8) | DeviceInfo[USB_DATA_FIRMWARE_INDEX + 3]).ToString();

                ConnectEvent?.Invoke(Device.Firmware);
            }
            else
            {
                IsDeviceLost = true;
                Close();
            }
        }

        private void DeviceRemovedEvent()
        {
            Close();
            Device.IsConnected = false;
            RemoveEvent?.Invoke();
        }

        private byte[] GetDeviceSystemStatus()
        {
            byte[] DeviceStatus = new byte[USB_IN_PACKET_SIZE];
            SendCMD(MODULE_SYSTEM, SYS_CMD_GET_STATUS, ref DeviceStatus);
            return DeviceStatus;
        }

        private byte[] GetDeviceInfo()
        {
            byte[] DeviceInfo = new byte[USB_IN_PACKET_SIZE];
            SendCMD(MODULE_SYSTEM, SYS_CMD_GET_ID, ref DeviceInfo);
            return DeviceInfo;
        }

        private void SendCMD(byte DevModule, byte DevCmd)
        {
            byte[] CmdPacket = new byte[USB_OUT_PACKET_SIZE];
            CmdPacket[USB_MODULE_ID_INDEX] = DevModule;
            CmdPacket[USB_CMD_INDEX] = DevCmd;

            if (IsDeviceLost == false)
            {
                if (USB_device.Write(CmdPacket) == false)
                    CommunicationError();
            }
        }

        private void SendCMD(byte DevModule, byte DevCmd, ref byte[] ReadBuf)
        {
            byte[] ZeroPacket = new byte[USB_ZERO_PACKET_SIZE];
            SendCMD(DevModule, DevCmd);
            
            if (IsDeviceLost == false)
            {
                if (USB_device.Read(ReadBuf) == false)
                    CommunicationError();

                if (IsDeviceLost == false)
                    USB_device.Read(ZeroPacket);
            }
        }

        private void CommunicationError()
        {
            LATransferTimer.Stop();
            PWMInputTimer.Stop();
            if (LATransferBackground.IsBusy == true)
                LATransferBackground.CancelAsync();

            Close();
            Device.IsConnected = false;
            IsDeviceLost = true;

            MessageBox.Show("USB connection lost.\n\r" + "Check USB cable and connect the device",
                            "", MessageBoxButton.OK, MessageBoxImage.Error);

            USBMonitor.Stop();
            USBMonitor.Start();
        }
    }
}
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
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace RDC2_0064
{
    public class LASettings
    {
        public byte SamplingMode { get; set; }
        public byte ChannelsCount { get; set; }
        public long SampleCount { get; set; }
        public long ActualSampleCount { get; set; }
        public byte SamplingFreqSource { get; set; }
        public bool IsPLLReprogrammed { get; set; }
        public byte PLLM { get; set; }
        public UInt16 PLLN { get; set; }
        public byte PLLP { get; set; }
        public UInt16 SampleTimPSC { get; set; }
        public UInt16 SampleTimARR { get; set; }
        public byte ActiveExtEdge { get; set; }
        public byte ExtFreqDivider { get; set; }
        public byte ExtFreqActivePulse { get; set; }
        public byte DMAStreamCount { get; set; }
        public bool IsTriggersActive { get; set; }
        public UInt16 TriggerTimPSC { get; set; }
        public UInt16 TriggerTimARR { get; set; }
        public byte[] Triggers { get; set; }
        public byte ExtEdgeTrigger { get; set; }
        public string StreamFilePath { get; set; }
        public string SamplingFrequency { get; set; }


        public int BytesPerValue
        {
            get
            {
                return (ChannelsCount / 8);
            }
        }

        public LASettings ()
        {
            Triggers = new byte[LogicAnalyzer.CHANNELS_COUNT_MAX];
        }
    }
}

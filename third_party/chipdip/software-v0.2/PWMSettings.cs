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
    public class PWMSettings
    {
        public UInt16 TimPSC { get; set; }
        public UInt16 TimARR { get; set; }
        public PWMChannelSettings[] Channels { get; set; }

        public PWMSettings (int ChannelsCount)
        {
            Channels = new PWMChannelSettings[ChannelsCount];
            for (int i = 0; i < ChannelsCount; i++)
                Channels[i] = new PWMChannelSettings();
        }
    }
}

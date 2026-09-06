/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2020
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Windows.Threading;
using System.Management;


namespace RDC2_0064
{
    public class USBPlugEvents
    {
        public enum DeviceStates : byte { Removed, Arrived, };

        private DispatcherTimer CheckTimer = new DispatcherTimer();
        private DeviceStates state;
        private Action ArrivedEventHandler;
        private Action RemovedEventHandler;
        

        public string Filter { get; }
        public DeviceStates State { get { return state; } }

        public USBPlugEvents(string filter, byte CheckPeriod)
        {
            Filter = filter;
            state = GetDeviceState();
            CheckTimer.Interval = TimeSpan.FromSeconds(CheckPeriod);
            //CheckTimer.Tick += CheckTimer_Tick;
        }

        public void Start()
        {
            CheckTimer.Tick += CheckTimer_Tick;
            CheckTimer.Start();
        }

        public void Stop()
        {
            CheckTimer.Tick -= CheckTimer_Tick;
            CheckTimer.Stop();
        }

        public void AddArrivedEventHandler(Action Handler)
        {
            ArrivedEventHandler += Handler;
        }

        public void AddRemovedEventHandler(Action Handler)
        {
            RemovedEventHandler += Handler;
        }

        public void ClearEventHandlers()
        {
            ArrivedEventHandler = null;
            RemovedEventHandler = null;
        }

        public void UpdateState()
        {
            state = GetDeviceState();
        }

        public void SetState(DeviceStates NewState)
        {
            state = NewState;
        }

        private void CheckTimer_Tick(object sender, EventArgs e)
        {
            DeviceStates NewState = GetDeviceState();

            if (state != NewState)
            {
                state = NewState;

                if (state == DeviceStates.Arrived)
                    ArrivedEventHandler?.Invoke();
                else if (state == DeviceStates.Removed)
                    RemovedEventHandler?.Invoke();
            }
        }

        private DeviceStates GetDeviceState()
        {
            DeviceStates state = DeviceStates.Removed;

            using (ManagementObjectSearcher searcher = new ManagementObjectSearcher(@"Select * From Win32_PnPEntity"))
            {
                ManagementObjectCollection ConnectedDevices;
                try
                {
                    ConnectedDevices = searcher.Get();
                    foreach (ManagementBaseObject device in ConnectedDevices)
                    {
                        string DevID = (string)device.GetPropertyValue("DeviceID");
                        if (DevID.IndexOf(Filter) != -1)
                        {
                            state = DeviceStates.Arrived;
                            break;
                        }
                    }

                    ConnectedDevices.Dispose();
                }
                catch (ObjectDisposedException e)
                {
                    Console.WriteLine("Caught: {0}", e.Message);
                }
            }
            
            return state;
        }
    }
}

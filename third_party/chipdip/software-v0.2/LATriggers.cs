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
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace RDC2_0064
{
    public class LATriggers: INotifyPropertyChanged
    {
        private string[] TriggerFullSet =
        {
            "images/Trigger_None.png", "images/Trigger_Low.png", "images/Trigger_High.png",
            "images/Trigger_RisingEdge.png", "images/Trigger_FallingEdge.png", "images/Trigger_AnyEdge.png",
        };

        private string[] TriggerLevelOnly =
        {
            "images/Trigger_None.png", "images/Trigger_Low.png", "images/Trigger_High.png",
        };

        public enum TriggerSet : int
        {
            Full,
            LevelOnly,
        };

        
        private TriggerSet trigtype = TriggerSet.Full;
        private int trigselected = 0;
                

        public string[] TriggerStrings
        {
            get
            {
                if (trigtype == TriggerSet.Full)
                    return TriggerFullSet;
                else
                    return TriggerLevelOnly;
            }
            
        }

        
        public int SelectedTrigger
        {
            get { return this.trigselected; }
            set
            {
                if (this.trigselected != value)
                {
                    this.trigselected = value;
                    this.NotifyPropertyChanged("SelectedTrigger");
                }
            }
        }

        public LATriggers(TriggerSet Type)
        {
            trigtype = Type;
        }

        public event PropertyChangedEventHandler PropertyChanged;
        public void NotifyPropertyChanged(string PropertyName)
        {
            this.PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(PropertyName));
        }
    }
}

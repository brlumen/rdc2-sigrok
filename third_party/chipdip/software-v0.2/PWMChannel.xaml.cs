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
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Navigation;
using System.Windows.Shapes;

namespace RDC2_0064
{
    /// <summary>
    /// Interaction logic for PWMChannel.xaml
    /// </summary>
    public partial class PWMChannel : UserControl, INotifyPropertyChanged
    {
        private int[] dutycyclevalues;
        private int dutycycle = 50;

        public string Title { get; set; }
        public bool IsActive { get; set; }


        public int DutyCycle
        {
            get { return this.dutycycle; }
            set
            {
                if (this.dutycycle != value)
                {
                    this.dutycycle = value;
                    this.NotifyPropertyChanged("DutyCycle");
                }
            }
        }

        public int[] DutyCycleTable
        {
            get { return this.dutycyclevalues; }
            set
            {
                if (this.dutycyclevalues != value)
                {
                    this.dutycyclevalues = value;
                    this.NotifyPropertyChanged("DutyCycleTable");
                }
            }
        }
        


        public PWMChannel()
        {
            InitializeComponent();
            DataContext = this;
        }

        public event PropertyChangedEventHandler PropertyChanged;
        public void NotifyPropertyChanged(string PropertyName)
        {
            this.PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(PropertyName));
        }
    }
}

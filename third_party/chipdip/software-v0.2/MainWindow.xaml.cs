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
    /// Interaction logic for MainWindow.xaml
    /// </summary>
    public partial class MainWindow : Window
    {
        private USBDriver Device;
        
        public MainWindow()
        {
            InitializeComponent();
            DataContext = this;

            Device = new USBDriver(LAModuleConnected, LAModuleRemoved);
            LAModule.AssignDriver(ref Device);
            PWMModule.AssignDriver(ref Device);
            PWMInputModule.AssignDriver(ref Device);

            LAModule.AddStartAction(PWMModule.DisableModule);
            LAModule.AddStartAction(PWMInputModule.DisableModule);
            LAModule.AddStopAction(PWMModule.EnableModule);
            LAModule.AddStopAction(PWMInputModule.EnableModule);
            LAModule.AddCompleteAction(PWMModule.EnableModule);
            LAModule.AddCompleteAction(PWMInputModule.EnableModule);
        }

        private void LAModuleConnected(string Firmware)
        {
            ConnectionImage.Source = new BitmapImage(new Uri("images/Device_connected.png", UriKind.Relative));
            DeviceInfo.Text = "Connected";
            FirmwareVersion.Content = Firmware;
        }

        private void LAModuleRemoved()
        {
            ConnectionImage.Source = new BitmapImage(new Uri("images/Device_disconnected.png", UriKind.Relative));
            DeviceInfo.Text = "Disconnected";
            FirmwareVersion.Content = "";
        }

        private void MainWindow_Closing(object sender, System.ComponentModel.CancelEventArgs e)
        {
            Device.Close();
        }
    }
}

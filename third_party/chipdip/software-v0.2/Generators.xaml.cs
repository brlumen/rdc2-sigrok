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
    /// Interaction logic for PWMGenerator.xaml
    /// </summary>
    public partial class Generators : UserControl
    {
        private static readonly string[] PWM_1_TITLES = { "M15", "M16", "M17", };
        private static readonly string[] PWM_2_TITLES = { "M18", "M19", };
        
        private const int PWM_1_ITEMS_COUNT = 3;
        private const int PWM_2_ITEMS_COUNT = 2;
        private const int PWM_GENERATOR_COUNT = 2;


        private event Action<PWMSettings[]> Apply_Click;


        public Generators()
        {
            InitializeComponent();
            DataContext = this;

            PWM1.InitChannels(PWM_1_ITEMS_COUNT, PWM_1_TITLES);
            PWM2.InitChannels(PWM_2_ITEMS_COUNT, PWM_2_TITLES);
        }

        public void AssignDriver(ref USBDriver Driver)
        {
            Apply_Click += Driver.PWM_Config;
        }

        public void EnableModule()
        {
            ApplyButton.IsEnabled = true;
        }

        public void DisableModule(LASettings Config)
        {
            ApplyButton.IsEnabled = false;
        }

        private void ApplyButton_Click(object sender, RoutedEventArgs e)
        {
            PWMSettings[] PWMConfig = new PWMSettings[PWM_GENERATOR_COUNT];
            PWMConfig[0] = PWM1.GetSettings();
            PWMConfig[1] = PWM2.GetSettings();
            if ((PWMConfig[0] != null) && (PWMConfig[1] != null))
                Apply_Click?.Invoke(PWMConfig);
        }
    }
}

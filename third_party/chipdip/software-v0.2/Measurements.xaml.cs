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
    /// Interaction logic for Measurements.xaml
    /// </summary>
    public partial class Measurements : UserControl
    {
        private readonly string MeasAccuracy = "f4";

        private const double PWM_INPUT_TIMER_BASE_FREQ = 216000000;
        private const int PWM_INPUT_RANGES_COUNT = 3;
        private const int INPUT_1_100Hz_RANGE = 0;
        private const int UPDATE_RESULT_DELAY = 3;


        private static readonly string[] RangesStrings =
        {
            "1 - 100 Hz", "100 Hz - 4 kHz", "> 4 kHz",
        };

        private static readonly UInt16[] TimerPSC = { 3600, 40, 1, };
        private static readonly UInt16[] DetectDelayTicks = { 1, 1, 2, };
        
        private RadioButton[] PWMInputRanges = new RadioButton[PWM_INPUT_RANGES_COUNT];
        private int CurrentRange = INPUT_1_100Hz_RANGE;
        private int NullResultCnt = 0;

        private event Action<UInt16> Measurement_Enable;
        private event Action Measurement_Disable;

        
        public Measurements()
        {
            InitializeComponent();
            DataContext = this;

            for (int i = 0; i < PWM_INPUT_RANGES_COUNT; i++)
            {
                PWMInputRanges[i] = new RadioButton();
                PWMInputRanges[i].GroupName = "PWMInputRanges";
                PWMInputRanges[i].Content = RangesStrings[i];
                PWMInputRanges[i].Tag = i;
                
                if (i == 0)
                    PWMInputRanges[i].IsChecked = true;

                PWMInputRanges[i].Checked += PWMInputRange_Changed;
            }
            RangeItmes.ItemsSource = PWMInputRanges;
        }

        public void AssignDriver(ref USBDriver Driver)
        {
            Measurement_Enable += Driver.PWMInput_Config;
            Measurement_Disable += Driver.PWMInput_Stop;
            Driver.PWMInput_Data += MeasurementComplete;
        }

        public void EnableModule()
        {
            EnableCheck.IsEnabled = true;

            if (EnableCheck.IsChecked == true)
                MeasurementStart();
        }

        public void DisableModule(LASettings Config)
        {
            EnableCheck.IsEnabled = false;
            RangeGroup.IsEnabled = false;
        }

        private void MeasurementComplete(ImpulseData Impulse)
        {
            if ((Impulse.Period != 0) && (Impulse.Width != 0))
            {
                Impulse.Width += DetectDelayTicks[CurrentRange];
                Impulse.Period += DetectDelayTicks[CurrentRange];
                NullResultCnt = 0;
            }
            else if (CurrentRange == INPUT_1_100Hz_RANGE)
            {
                NullResultCnt++;
                if (NullResultCnt < UPDATE_RESULT_DELAY)
                    return;
            }

            double Value = Impulse.Width / (PWM_INPUT_TIMER_BASE_FREQ / TimerPSC[CurrentRange]);
            PulseWidth.Content = ConvertToString.Time(Value, MeasAccuracy);

            Value = Impulse.Period / (PWM_INPUT_TIMER_BASE_FREQ / TimerPSC[CurrentRange]);
            PulsePeriod.Content = ConvertToString.Time(Value, MeasAccuracy);

            if (Value != 0)
                Value = 1.0 / Value;
            PulseFrequency.Content = ConvertToString.Frequency(Value, MeasAccuracy);

            if (Impulse.Period != 0)
                PulseDutyCycle.Content = ConvertToString.Percentage(Impulse.Width, Impulse.Period, MeasAccuracy);
            else
                PulseDutyCycle.Content = ConvertToString.Percentage(0, 1, MeasAccuracy);
        }

        private void MeasurementStart()
        {
            RangeGroup.IsEnabled = true;
            Measurement_Enable?.Invoke((UInt16)(TimerPSC[CurrentRange] - 1));
        }

        private void PWMInputRange_Changed(object sender, RoutedEventArgs e)
        {
            CurrentRange = (int)(sender as RadioButton).Tag;
            Measurement_Enable?.Invoke((UInt16)(TimerPSC[CurrentRange] - 1));
        }

        private void Enable_Checked(object sender, RoutedEventArgs e)
        {
            MeasurementStart();
        }

        private void Enable_UnChecked(object sender, RoutedEventArgs e)
        {
            RangeGroup.IsEnabled = false;
            Measurement_Disable?.Invoke();
        }
    }
}

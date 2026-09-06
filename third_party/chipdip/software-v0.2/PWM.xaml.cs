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
    /// Interaction logic for PWMGeneratorPart.xaml
    /// </summary>
    public partial class PWM : UserControl, INotifyPropertyChanged
    {
        private static readonly string FreqUnits_Hz = "Hz";
        private static readonly string FreqUnits_kHz = "kHz";
        private static readonly string FreqUnits_MHz = "MHz";

        private static readonly string[] FreqUnitsStrings =
        {
            FreqUnits_Hz, FreqUnits_kHz, FreqUnits_MHz,
        };

        private static readonly int[] FreqUnitsMultiplier =
        {
            1, 1000, 1000000,
        };

        private static readonly string CommaChar = ",";
        private static readonly string[] AllowedInputChars =
        {
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            CommaChar,
        };
        
        private const double PWM_TIMER_BASE_FREQUENCY = 108000000;
        private const int PWM_MAX_FREQUENCY = 27000000;
        private const int PWM_TIM_DIV_MAX = 65500;
        private const double PWM_MIN_FREQUENCY = 0.03;
        private const int DutyCycleStep_1_FreqMax = (int)(PWM_TIMER_BASE_FREQUENCY / 100);
        private const int DutyCycleStep_5_FreqMax = (int)(PWM_TIMER_BASE_FREQUENCY / 20);
        private const int DutyCycleStep_10_FreqMax = (int)(PWM_TIMER_BASE_FREQUENCY / 10);
        private const int DutyCycleStep_25_FreqMax = (int)(PWM_TIMER_BASE_FREQUENCY / 4);
        private const int DutyCycleStep_50_FreqMax = (int)(PWM_TIMER_BASE_FREQUENCY / 2);

        private const int DutyCycleStep_1 = 1;
        private const int DutyCycleStep_5 = 5;
        private const int DutyCycleStep_10 = 10;
        private const int DutyCycleStep_25 = 25;
        private const int DutyCycleStep_50 = 50;


        private int PWMChnlsCount;
        private int selectedunits = 0;
        private PWMChannel[] PWMChannels;
        private PWMSettings Settings;
        
        

        public int SelectedUnits
        {
            get { return this.selectedunits; }
            set
            {
                if (this.selectedunits != value)
                {
                    this.selectedunits = value;
                    this.NotifyPropertyChanged("SelectedUnits");
                }
            }
        }

        public string[] FrequencyUnits
        {
            get
            {
                return FreqUnitsStrings;
            }

        }



        public PWM()
        {
            InitializeComponent();
            DataContext = this;

            InputFreqBox.TextChanged += InputFrequency_TextChanged;
        }

        public void InitChannels(int Channels, string[] ChnlTitles)
        {
            PWMChnlsCount = Channels;
            PWMChannels = new PWMChannel[PWMChnlsCount];

            Settings = new PWMSettings(PWMChnlsCount);
            Settings.TimPSC = 2;
            Settings.TimARR = 54000;

            int[] Values = GenerateDutyCycleTable(DutyCycleStep_1);

            for (int i = 0; i < PWMChnlsCount; i++)
            {
                PWMChannels[i] = new PWMChannel();
                PWMChannels[i].Title = ChnlTitles[i];
                PWMChannels[i].DutyCycleTable = Values;
                PWMChannels[i].DutyCycle = 50;
            }

            PWMItems.ItemsSource = PWMChannels;
        }

        public PWMSettings GetSettings()
        {
            double WantedFrequency;
            bool IsValueAcceptable = true;

            if (double.TryParse(InputFreqBox.Text, out WantedFrequency) == true)
            {
                WantedFrequency *= FreqUnitsMultiplier[SelectedUnits];

                if (!((WantedFrequency >= PWM_MIN_FREQUENCY) && (WantedFrequency <= PWM_MAX_FREQUENCY)))
                {
                    MessageBox.Show("PWM frequency out of range \n\r" +
                        "Valid frequency range: " + PWM_MIN_FREQUENCY + " Hz" + " - " +
                        (PWM_MAX_FREQUENCY / 1000000).ToString() + " MHz", "", MessageBoxButton.OK, MessageBoxImage.Error);

                    IsValueAcceptable = false;
                }
            }
            else
            {
                MessageBox.Show("PWM frequency wrong number format", "", MessageBoxButton.OK, MessageBoxImage.Error);
                IsValueAcceptable = false;
            }

            if (IsValueAcceptable == false)
            {
                SelectedUnits = Array.IndexOf(FreqUnitsStrings, FreqUnits_Hz);

                if (WantedFrequency < PWM_MIN_FREQUENCY)
                    InputFreqBox.Text = PWM_MIN_FREQUENCY.ToString();
                else //if (WantedFrequency > PWM_MAX_FREQUENCY)
                    InputFreqBox.Text = PWM_MAX_FREQUENCY.ToString();

                return null;
            }
                
            for (int i = 0; i < PWMChnlsCount; i++)
            {
                Settings.Channels[i].IsActive = PWMChannels[i].IsActive;
                if (Settings.Channels[i].IsActive == true)
                {
                    double CCRValue = (PWMChannels[i].DutyCycle * (Settings.TimARR + 1)) / 100;
                    Settings.Channels[i].TimCCR = (UInt16)CCRValue;
                }
                else
                    Settings.Channels[i].TimCCR = 0;
            }
            
            return Settings;
        }

        private void CalculateFrequency()
        {
            double WantedFrequency;
            double RealFrequency;
            
            if (double.TryParse(InputFreqBox.Text, out WantedFrequency) == true)
            {
                WantedFrequency *= FreqUnitsMultiplier[SelectedUnits];

                if ((WantedFrequency >= PWM_MIN_FREQUENCY) && (WantedFrequency <= PWM_MAX_FREQUENCY))
                {
                    double DbDevidersMult = (PWM_TIMER_BASE_FREQUENCY / WantedFrequency);
                    UInt32 IntDevidersMult = (UInt32)DbDevidersMult;
                    
                    if ((DbDevidersMult - IntDevidersMult) >= 0.5)
                        IntDevidersMult++;

                    int NewDutyCycleStep = DutyCycleStep_1;
                    if (WantedFrequency <= DutyCycleStep_1_FreqMax)
                        NewDutyCycleStep = DutyCycleStep_1;
                    else if (WantedFrequency <= DutyCycleStep_5_FreqMax)
                        NewDutyCycleStep = DutyCycleStep_5;
                    else if (WantedFrequency <= DutyCycleStep_10_FreqMax)
                        NewDutyCycleStep = DutyCycleStep_10;
                    else if (WantedFrequency <= DutyCycleStep_25_FreqMax)
                        NewDutyCycleStep = DutyCycleStep_25;
                    else if (WantedFrequency <= DutyCycleStep_50_FreqMax)
                        NewDutyCycleStep = DutyCycleStep_50;
                    else
                    {
                        Settings.TimPSC = 1;
                        Settings.TimARR = 1;
                    }

                    Settings.TimPSC = 1;
                    
                    while (((IntDevidersMult % Settings.TimPSC) != 0)
                        //|| ((IntDevidersMult / (Settings.TimPSC + 1)) >= DutyCycleStepArrMin)
                        || ((IntDevidersMult / Settings.TimPSC) > PWM_TIM_DIV_MAX))
                    {
                        Settings.TimPSC++;
                        if (Settings.TimPSC > PWM_TIM_DIV_MAX)
                        {
                            break;
                        }
                    }

                    Settings.TimARR = (UInt16)(IntDevidersMult / Settings.TimPSC);
                    
                    int[] Values = GenerateDutyCycleTable(NewDutyCycleStep);
                    for (int i = 0; i < PWMChnlsCount; i++)
                    {
                        PWMChannels[i].DutyCycleTable = Values;
                        PWMChannels[i].DutyCycle = 50;
                    }

                    RealFrequency = PWM_TIMER_BASE_FREQUENCY / Settings.TimPSC / Settings.TimARR;
                    RealFreq.Content = RealFrequency.ToString("f2");                    
                    FreqError.Content = ConvertToString.Percentage(RealFrequency - WantedFrequency,
                                                                   WantedFrequency, "f3");

                    Settings.TimPSC--;
                    Settings.TimARR--;
                }
            }
        }

        private int[] GenerateDutyCycleTable(int DutyCycleStep)
        {
            int ValuesCount = 100 / DutyCycleStep + 1;
            int[] NewTable = new int[ValuesCount];

            for (int i = 0; i < ValuesCount; i++)
                NewTable[i] = i * DutyCycleStep;

            return NewTable;
        }

        private void InputFrequency_TextChanged(object sender, TextChangedEventArgs e)
        {
            CalculateFrequency();
        }

        private void InputFrequency_PreviewInput(object sender, TextCompositionEventArgs e)
        {
            int CharIndex = Array.IndexOf(AllowedInputChars, e.Text);
            bool IsCharAllowed = true;

            if (CharIndex == -1)
                IsCharAllowed = false;
            else if (CharIndex == Array.IndexOf(AllowedInputChars, CommaChar))
            {
                int CommaInputIndex = InputFreqBox.Text.IndexOf(CommaChar);
                if (CommaInputIndex != -1)
                    IsCharAllowed = false;
            }
                        
            if (IsCharAllowed == false)
                e.Handled = true;
        }

        private void FreqUnits_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            CalculateFrequency();
        }

        public event PropertyChangedEventHandler PropertyChanged;
        public void NotifyPropertyChanged(string PropertyName)
        {
            this.PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(PropertyName));
        }
    }
}


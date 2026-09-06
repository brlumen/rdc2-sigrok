/*
********************************************************************************
* COPYRIGHT(c) ЗАО «ЧИП и ДИП», 2021
* 
* Программное обеспечение предоставляется на условиях «как есть» (as is).
* При распространении указание автора обязательно.
********************************************************************************
*/


using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.IO;
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
    /// Interaction logic for LogicAnalyzer.xaml
    /// </summary>
    public partial class LogicAnalyzer : UserControl
    {
        private static readonly string[] ModesStrings = { "Buffer mode", "Stream mode", };
        private static readonly string[][] ChannelsStrings =
        {
          new[] { "0-7 (up to 72 MHz)", "0-15 (up to 72 MHz)",
                  "0-23 (up to 24 MHz)", "0-31 (up to 24 MHz)", },
          new[] { "0-7 (up to 18 MHz)", "0-15 (up to 8 MHz)",
                  "0-23", "0-31 (up to 4 MHz)", },
        };
        private static readonly byte[] ChannelsValues = { 8, 16, 24, 32, };

        private static readonly string SamplesCount_30kSrting = "30k samples";
        private static readonly string SamplesCount_60kSrting = "60k samples";
        private static readonly string SamplesCount_120kSrting = "120k samples";

        private static readonly string[] BufferSampleCountStrings =
        {
            "1k samples", "2k samples", "5k samples", "10k samples", "20k samples",
            SamplesCount_30kSrting, SamplesCount_60kSrting,
            SamplesCount_120kSrting, "160k samples", "240k samples",
        };
        
        private static readonly int[] BufferSampleCountValues =
        {
            1000, 2000, 5000, 10000, 20000,
            30000, 60000,
            120000, 160000, 240000,
        };

        private static readonly string[] StreamSampleCountStrings =
        {
            "1M samples", "2M samples", "5M samples", "10M samples", "20M samples", "50M samples",
            "100M samples", "200M samples", "500M samples",  "1G samples", "2G samples",
            "4G samples", "8G samples", "12G samples", "16G samples",
        };

        private static readonly long[] StreamSampleCountValues =
        {
            1000000, 2000000, 5000000, 10000000, 20000000, 50000000,
            100000000, 200000000, 500000000, 1000000000, 2000000000,
            4000000000, 8000000000, 12000000000, 16000000000,
        };

        private static readonly string Freq_4MHzSrting = "4 MHz";
        private static readonly string Freq_8MHzSrting = "8 MHz";
        private static readonly string Freq_18MHzSrting = "18 MHz";
        private static readonly string Freq_24MHzSrting = "24 MHz";
        private static readonly string Freq_36MHzSrting = "36 MHz";
        private static readonly string Freq_54MHzSrting = "54 MHz";
        private static readonly string Freq_72MHzSrting = "72 MHz";
        private static readonly string Freq_108MHzSrting = "108 MHz*";

        private static readonly string[] SampleFreqStrings =
        {
            "10 kHz", "20 kHz", "50 kHz", "100 kHz", "200 kHz", "500 kHz",
            "1 MHz", "2 MHz", Freq_4MHzSrting, Freq_8MHzSrting, "12 MHz", Freq_18MHzSrting,
            Freq_24MHzSrting, Freq_36MHzSrting, Freq_54MHzSrting,
            Freq_72MHzSrting, Freq_108MHzSrting,
        };

        private static readonly int[] SampleFreqValues =
        {
            10000, 20000, 50000, 100000, 200000, 500000,
            1000000, 2000000, 4000000, 8000000, 12000000, 18000000,
            24000000, 36000000, 54000000,
            72000000, 108000000,
        };

        private static readonly UInt16[] SampleTimerPSC =
        {
            10800, 5400, 2160,         1080, 540, 216,
            108, 54, 27,               9, 9, 6,
            3, 3, 2,
            1, 2,
        };

        private static readonly UInt16[] SampleTimerARR_1Chnl =
        {
            2, 2, 2,                   2, 2, 2,
            2, 2, 2,                   3, 2, 2,
            3, 2, 2,
            3, 1,
        };

        private static readonly string TimeAccuracy = "f1";
        private static readonly string BinaryFileFilter = "Binary files (*.bin)|*.bin";
        private static readonly string UnderlineString = "_";
        private static readonly string ChannelsString = "Chnls";
        

        internal const byte CHANNELS_COUNT_MAX = 32;
        private const int SAMPLE_MODES_COUNT = 2;
        private const int CHANNELS_MODES_COUNT = 4;
        
        private const int BUFFER_MODE = 0;
        private const int STREAM_MODE = 1;

        private const int MAX_SAMPLES_PER_DMA_STREAM = 65000;
        private const int DMA_STREAMS_COUNT_MAX = 5;

        private const int CHANNELS_COUNT_IN_GROUP = 8;
        private const int CHANNELS_GROUP_COUNT = 4;
        private const byte TRIGGER_NONE = 0;

        private const int CHANNELS_0_7_GROUP = 0;
        private const int CHANNELS_0_15_GROUP = 1;
        private const int CHANNELS_0_23_GROUP = 2;
        private const int CHANNELS_0_31_GROUP = 3;


        private RadioButton[] SampleModes = new RadioButton[SAMPLE_MODES_COUNT];
        private RadioButton[] ActiveChannels = new RadioButton[CHANNELS_MODES_COUNT];
        private LATriggers[][] ChnlTriggers = new LATriggers[CHANNELS_GROUP_COUNT][];
        private LASettings LAConfig = new LASettings();
        private byte[][] Samples;
        
        private event Action<LASettings> Start_Click;
        private event Action Stop_Click;
        private event Action Complete_Action;


        public LATriggers EdgeTrigger { get; set; } = new LATriggers(LATriggers.TriggerSet.Full);


        public LogicAnalyzer()
        {
            InitializeComponent();
            DataContext = this;

            ComboBoxItem[] SampleFreqItems = new ComboBoxItem[SampleFreqStrings.Length];
            for (int i = 0; i < SampleFreqStrings.Length; i++)
            {
                SampleFreqItems[i] = new ComboBoxItem();
                SampleFreqItems[i].Content = SampleFreqStrings[i];
                SampleFreqItems[i].HorizontalContentAlignment = HorizontalAlignment.Left;
                SampleFreqItems[i].VerticalContentAlignment = VerticalAlignment.Center;
            }

            SampleCountSelector.ItemsSource = MakeBufferSamplesComboItems();
            SampleCountSelector.SelectedIndex = 0;
            SampleFreqSelector.ItemsSource = SampleFreqItems;
            SampleFreqSelector.SelectedIndex = 0;

            for (int i = 0; i < SAMPLE_MODES_COUNT; i++)
            {
                SampleModes[i] = new RadioButton();
                SampleModes[i].GroupName = "SampleModes";
                SampleModes[i].Content = ModesStrings[i];
                SampleModes[i].Margin = new Thickness(0, 10, 0, 0);
                if (i == 0)
                {
                    SampleModes[i].IsChecked = true;
                    SampleModes[i].Checked += BufferMode_Checked;
                    SampleModes[i].Unchecked += BufferMode_UnChecked;
                }
            }
            ModeItems.ItemsSource = SampleModes;

            for (int i = CHANNELS_0_7_GROUP; i < CHANNELS_MODES_COUNT; i++)
            {
                ActiveChannels[i] = new RadioButton();
                ActiveChannels[i].GroupName = "ActiveChannels";
                ActiveChannels[i].Content = ChannelsStrings[0][i];
                ActiveChannels[i].Checked += ChannelsGroup_Changed;
                ActiveChannels[i].Margin = new Thickness(0, 10, 0, 0);
                if (i == 0)
                    ActiveChannels[i].IsChecked = true;
            }
            ActiveChannels[CHANNELS_0_23_GROUP].Visibility = Visibility.Collapsed;
            ChannelsItems.ItemsSource = ActiveChannels;
            
            for (int i = 0; i < CHANNELS_GROUP_COUNT; i++)
            {
                ChnlTriggers[i] = new LATriggers[CHANNELS_COUNT_IN_GROUP];

                LATriggers.TriggerSet TriggerType = LATriggers.TriggerSet.Full;
                if (i > CHANNELS_0_15_GROUP)
                    TriggerType = LATriggers.TriggerSet.LevelOnly;

                for (int chnl = 0; chnl < CHANNELS_COUNT_IN_GROUP; chnl++)
                    ChnlTriggers[i][chnl] = new LATriggers(TriggerType);
            }
            TrigItems0_7.ItemsSource = ChnlTriggers[0];
            TrigItems8_15.ItemsSource = ChnlTriggers[1];
            TrigItems16_23.ItemsSource = ChnlTriggers[2];
            TrigItems24_31.ItemsSource = ChnlTriggers[3];

            DisableTriggerSettings();

            SampleTimeLabel.Content = "100 ms";
        }
        
        public void AssignDriver(ref USBDriver Driver)
        {
            Start_Click += Driver.LA_ConfigAndStart;
            Stop_Click += Driver.LA_StopSampling;
            Driver.LA_DataRx_Complete += SamplingComplete;
            Driver.LA_DataRx_Progress += SamplingProgress;
            Driver.LA_Stream_Complete += StreamComplete;
        }
        
        public void AddStartAction(Action<LASettings> NewAction)
        {
            Start_Click += NewAction;
        }

        public void AddStopAction(Action NewAction)
        {
            Stop_Click += NewAction;
        }

        public void AddCompleteAction(Action NewAction)
        {
            Complete_Action += NewAction;
        }

        private void SamplingComplete(byte[][] NewData, long ValidDataSize)
        {
            Samples = NewData;
            if (LAConfig.SamplingMode != STREAM_MODE)
            {
                RearrangeSamples();
                ProcessStatus.Value = 100;
                SaveButton.IsEnabled = true;
                StartButton.IsEnabled = true;
                Complete_Action?.Invoke();
            }
            else
            {
                LAConfig.ActualSampleCount = ValidDataSize;

                if (LAConfig.ActualSampleCount >= LAConfig.SampleCount)
                {
                    SetStreamFileLength(LAConfig.SampleCount * LAConfig.BytesPerValue);
                    MessageBox.Show("Sampling has been completed successfully", "",
                                    MessageBoxButton.OK, MessageBoxImage.Information);
                }
                else
                {
                    SetStreamFileLength(LAConfig.ActualSampleCount * LAConfig.BytesPerValue);
                    MessageBox.Show("Sampling has been completed\n\r" +
                                    "Valid samples: " + LAConfig.ActualSampleCount.ToString(), "",
                                    MessageBoxButton.OK, MessageBoxImage.Warning);
                }
            }
        }
        
        private void StreamComplete()
        {
            if (LAConfig.SamplingMode != STREAM_MODE)
                SaveButton.IsEnabled = true;
            StartButton.IsEnabled = true;
            ProcessStatus.IsIndeterminate = false;
            ProcessStatus.Value = 100;
            Complete_Action?.Invoke();
        }

        private void SamplingProgress(UInt16 RemainingSamples)
        {
            ProcessStatus.Value = (100 * (LAConfig.SampleCount - RemainingSamples * LAConfig.DMAStreamCount)) / LAConfig.SampleCount;
        }

        private void UpdateConfig()
        {
            if (SampleModes[BUFFER_MODE].IsChecked == true)
            {
                LAConfig.SamplingMode = BUFFER_MODE;
                LAConfig.SampleCount = BufferSampleCountValues[SampleCountSelector.SelectedIndex];
            }
            else
            {
                LAConfig.SamplingMode = STREAM_MODE;
                LAConfig.SampleCount = StreamSampleCountValues[SampleCountSelector.SelectedIndex];
            }
                
            for (int i = 0; i < CHANNELS_MODES_COUNT; i++)
            {
                if(ActiveChannels[i].IsChecked == true)
                {
                    LAConfig.ChannelsCount = ChannelsValues[i];
                    break;
                }
            }

            LAConfig.SamplingFreqSource = 0;
            LAConfig.IsPLLReprogrammed = false;
            LAConfig.SampleTimPSC = (UInt16)(SampleTimerPSC[SampleFreqSelector.SelectedIndex] - 1);
            LAConfig.SampleTimARR = SampleTimerARR_1Chnl[SampleFreqSelector.SelectedIndex];
            LAConfig.SamplingFrequency = SampleFreqStrings[SampleFreqSelector.SelectedIndex].Replace(" ", "");
            if (SampleFreqStrings[SampleFreqSelector.SelectedIndex] == Freq_108MHzSrting)
                LAConfig.SamplingFrequency = LAConfig.SamplingFrequency.Remove(LAConfig.SamplingFrequency.Length - 1);
            
            if (LAConfig.SamplingMode == STREAM_MODE)
                LAConfig.DMAStreamCount = 1;
            else
            {
                byte SamplesDMAStreams;
                for (SamplesDMAStreams = 1; SamplesDMAStreams < DMA_STREAMS_COUNT_MAX; SamplesDMAStreams++)
                {
                    if ((SamplesDMAStreams * MAX_SAMPLES_PER_DMA_STREAM) >= LAConfig.SampleCount)
                        break;
                }

                byte FreqDMAStreams;
                if (SampleFreqSelector.SelectedIndex <= Array.IndexOf(SampleFreqStrings, Freq_36MHzSrting))
                    FreqDMAStreams = 1;
                else if (SampleFreqSelector.SelectedIndex <= Array.IndexOf(SampleFreqStrings, Freq_72MHzSrting))
                    FreqDMAStreams = 4;
                else //if (SampleFreqSelector.SelectedIndex <= Array.IndexOf(SampleFreqStrings, Freq_108MHzSrting))
                    FreqDMAStreams = 5;

                LAConfig.DMAStreamCount = SamplesDMAStreams;
                if (LAConfig.DMAStreamCount < FreqDMAStreams)
                    LAConfig.DMAStreamCount = FreqDMAStreams;

                if ((LAConfig.DMAStreamCount == 2) || (LAConfig.DMAStreamCount == 3))
                    LAConfig.DMAStreamCount = 4;
            }
            
            for (int chnl = 0; chnl < CHANNELS_COUNT_IN_GROUP; chnl++)
            {
                for (int group = 0; group < CHANNELS_GROUP_COUNT; group++)
                    LAConfig.Triggers[chnl + group * CHANNELS_COUNT_IN_GROUP] = TRIGGER_NONE;
            }

            if (TriggerActivation.IsChecked == true)
            {
                LAConfig.IsTriggersActive = true;
                int ActiveGroupsCount = GetActiveChnlGroup() + 1;
                
                for (int chnl = 0; chnl < CHANNELS_COUNT_IN_GROUP; chnl++)
                {
                    for (int group = 0; group < ActiveGroupsCount; group++)
                        LAConfig.Triggers[chnl + group * CHANNELS_COUNT_IN_GROUP] = (byte)ChnlTriggers[group][chnl].SelectedTrigger;
                }
            }
            else
                LAConfig.IsTriggersActive = false;

            LAConfig.ExtEdgeTrigger = (byte)EdgeTrigger.SelectedTrigger;
        }

        private void RearrangeSamples()
        {
            if (!((LAConfig.DMAStreamCount == 1) && (LAConfig.ChannelsCount <= 16)))
            {
                int BytesPerSample = 1;
                int DMAStreams = LAConfig.DMAStreamCount;

                if ((LAConfig.ChannelsCount == 16) || (LAConfig.ChannelsCount == 32))
                    BytesPerSample = 2;

                int OnePartSamples = ((int)LAConfig.SampleCount / DMAStreams) * BytesPerSample;
                if (LAConfig.ChannelsCount == 32)
                    DMAStreams *= 2;

                List<byte> TempSamples = new List<byte>();

                for (int i = 0; i < OnePartSamples; i += BytesPerSample)
                {
                    for (int stream = 0; stream < DMAStreams; stream++)
                    {
                        for (int ByteNum = 0; ByteNum < BytesPerSample; ByteNum++)
                        {
                            TempSamples.Add(Samples[0][stream * OnePartSamples + i + ByteNum]);
                        }
                    }
                }

                Samples[0] = new byte[TempSamples.Count];
                TempSamples.CopyTo(Samples[0]);
            }
        }

        private void UpdateSampleTime()
        {
            if ((this.IsLoaded == true) && (SampleCountSelector.SelectedIndex != -1))
            {
                double SampleTime;

                if (SampleModes[BUFFER_MODE].IsChecked == true)
                    SampleTime = BufferSampleCountValues[SampleCountSelector.SelectedIndex];
                else
                    SampleTime = StreamSampleCountValues[SampleCountSelector.SelectedIndex];

                SampleTime /= SampleFreqValues[SampleFreqSelector.SelectedIndex];
                SampleTimeLabel.Content = ConvertToString.Time(SampleTime, TimeAccuracy);
            }
        }

        private void ChangeActiveChannelsInfo(int InfoIndex)
        {
            for (int i = 0; i < CHANNELS_MODES_COUNT; i++)
                ActiveChannels[i].Content = ChannelsStrings[InfoIndex][i];
        }

        private void ActivateTriggerSelection(int ChnlsGroup)
        {
            if (TriggerActivation.IsChecked == true)
            {
                switch (ChnlsGroup)
                {
                    case CHANNELS_0_7_GROUP:
                        TrigItems0_7.IsEnabled = true;
                        TrigItems8_15.IsEnabled = false;
                        TrigItems16_23.IsEnabled = false;
                        TrigItems24_31.IsEnabled = false;
                        break;

                    case CHANNELS_0_15_GROUP:
                        TrigItems0_7.IsEnabled = true;
                        TrigItems8_15.IsEnabled = true;
                        TrigItems16_23.IsEnabled = false;
                        TrigItems24_31.IsEnabled = false;
                        break;

                    case CHANNELS_0_31_GROUP:
                        TrigItems0_7.IsEnabled = true;
                        TrigItems8_15.IsEnabled = true;
                        TrigItems16_23.IsEnabled = true;
                        TrigItems24_31.IsEnabled = true;
                        break;
                }
            }
        }

        private void SetLimitsOnSampleCountAndFreq(int ChnlsGroup)
        {
            if (SampleModes[BUFFER_MODE].IsChecked == true)
            {
                if (SampleFreqSelector.SelectedIndex == Array.IndexOf(SampleFreqStrings, Freq_108MHzSrting))
                {
                    int SamplesCount_30kIndex = Array.IndexOf(BufferSampleCountStrings, SamplesCount_30kSrting);

                    for (int i = Array.IndexOf(BufferSampleCountStrings, SamplesCount_30kSrting) + 1; i < BufferSampleCountStrings.Length; i++)
                        (SampleCountSelector.Items[i] as ComboBoxItem).IsEnabled = false;

                    if (SampleCountSelector.SelectedIndex > SamplesCount_30kIndex)
                        SampleCountSelector.SelectedIndex = SamplesCount_30kIndex;
                }
                else
                {
                    switch (ChnlsGroup)
                    {
                        case CHANNELS_0_7_GROUP:
                            for (int i = Array.IndexOf(SampleFreqStrings, Freq_4MHzSrting) + 1; i < SampleFreqStrings.Length; i++)
                                (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = true;

                            for (int i = Array.IndexOf(BufferSampleCountStrings, SamplesCount_30kSrting) + 1; i < BufferSampleCountStrings.Length; i++)
                                (SampleCountSelector.Items[i] as ComboBoxItem).IsEnabled = true;
                            break;

                        case CHANNELS_0_15_GROUP:
                            for (int i = Array.IndexOf(SampleFreqStrings, Freq_4MHzSrting) + 1; i < SampleFreqStrings.Length; i++)
                                (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = true;

                            (SampleCountSelector.Items[Array.IndexOf(BufferSampleCountStrings, SamplesCount_30kSrting) + 1] as ComboBoxItem).IsEnabled = true;
                            (SampleCountSelector.Items[Array.IndexOf(BufferSampleCountStrings, SamplesCount_60kSrting) + 1] as ComboBoxItem).IsEnabled = true;
                            for (int i = Array.IndexOf(BufferSampleCountStrings, SamplesCount_120kSrting) + 1; i < BufferSampleCountStrings.Length; i++)
                                (SampleCountSelector.Items[i] as ComboBoxItem).IsEnabled = false;
                            break;

                        case CHANNELS_0_31_GROUP:
                            for (int i = Array.IndexOf(SampleFreqStrings, Freq_4MHzSrting); i <= Array.IndexOf(SampleFreqStrings, Freq_24MHzSrting); i++)
                                (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = true;

                            for (int i = Array.IndexOf(SampleFreqStrings, Freq_24MHzSrting) + 1; i < SampleFreqStrings.Length; i++)
                                (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = false;

                            (SampleCountSelector.Items[Array.IndexOf(BufferSampleCountStrings, SamplesCount_30kSrting) + 1] as ComboBoxItem).IsEnabled = true;
                            for (int i = Array.IndexOf(BufferSampleCountStrings, SamplesCount_60kSrting) + 1; i < BufferSampleCountStrings.Length; i++)
                                (SampleCountSelector.Items[i] as ComboBoxItem).IsEnabled = false;
                            break;
                    }
                }
            }

            else
            {
                switch (ChnlsGroup)
                {
                    case CHANNELS_0_7_GROUP:
                        for (int i = Array.IndexOf(SampleFreqStrings, Freq_4MHzSrting); i <= Array.IndexOf(SampleFreqStrings, Freq_18MHzSrting); i++)
                            (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = true;

                        for (int i = Array.IndexOf(SampleFreqStrings, Freq_18MHzSrting) + 1; i < SampleFreqStrings.Length; i++)
                            (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = false;
                        break;

                    case CHANNELS_0_15_GROUP:
                        for (int i = Array.IndexOf(SampleFreqStrings, Freq_4MHzSrting); i <= Array.IndexOf(SampleFreqStrings, Freq_8MHzSrting); i++)
                            (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = true;

                        for (int i = Array.IndexOf(SampleFreqStrings, Freq_8MHzSrting) + 1; i < SampleFreqStrings.Length; i++)
                            (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = false;
                        break;

                    case CHANNELS_0_31_GROUP:
                        for (int i = Array.IndexOf(SampleFreqStrings, Freq_4MHzSrting) + 1; i < SampleFreqStrings.Length; i++)
                            (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = false;
                        break;
                }
            }
        }

        private int GetActiveChnlGroup()
        {
            int ActiveChnlGroup;

            for (ActiveChnlGroup = 0; ActiveChnlGroup < CHANNELS_MODES_COUNT; ActiveChnlGroup++)
            {
                if (ActiveChannels[ActiveChnlGroup].IsChecked == true)
                    break;
            }

            return ActiveChnlGroup;
        }

        private ComboBoxItem[] MakeBufferSamplesComboItems()
        {
            ComboBoxItem[] SampleCountItems = new ComboBoxItem[BufferSampleCountStrings.Length];
            for (int i = 0; i < BufferSampleCountStrings.Length; i++)
            {
                SampleCountItems[i] = new ComboBoxItem();
                SampleCountItems[i].Content = BufferSampleCountStrings[i];
                SampleCountItems[i].HorizontalContentAlignment = HorizontalAlignment.Left;
                SampleCountItems[i].VerticalContentAlignment = VerticalAlignment.Center;
            }

            return SampleCountItems;
        }

        private void DisableTriggerSettings()
        {
            TrigItems0_7.IsEnabled = false;
            TrigItems8_15.IsEnabled = false;
            TrigItems16_23.IsEnabled = false;
            TrigItems24_31.IsEnabled = false;
        }

        private void SetStreamFileLength(long NewLength)
        {
            using (Stream StreamFile = new FileStream(LAConfig.StreamFilePath, FileMode.Open))
            {
                StreamFile.SetLength(NewLength);
            }
        }

        private void BufferMode_Checked(object sender, RoutedEventArgs e)
        {
            ChangeActiveChannelsInfo(BUFFER_MODE);
            SampleCountSelector.ItemsSource = MakeBufferSamplesComboItems();
            SampleCountSelector.SelectedIndex = 0;
            SampleFreqSelector.SelectedIndex = 0;

            for (int i = Array.IndexOf(SampleFreqStrings, Freq_18MHzSrting) + 1; i <= Array.IndexOf(SampleFreqStrings, Freq_24MHzSrting); i++)
                (SampleFreqSelector.Items[i] as ComboBoxItem).IsEnabled = true;

            SetLimitsOnSampleCountAndFreq(GetActiveChnlGroup());
            TriggerActivation.IsEnabled = true;
            EdgeTriggerSelector.IsEnabled = true;
            StreamFileButton.IsEnabled = false;
            ProgressValueBlock.Visibility = Visibility.Visible;
        }

        private void BufferMode_UnChecked(object sender, RoutedEventArgs e)
        {
            ChangeActiveChannelsInfo(STREAM_MODE);
            SampleCountSelector.ItemsSource = StreamSampleCountStrings;
            SampleCountSelector.SelectedIndex = 0;
            SampleFreqSelector.SelectedIndex = 0;

            SetLimitsOnSampleCountAndFreq(GetActiveChnlGroup());
            TriggerActivation.IsChecked = false;
            TriggerActivation.IsEnabled = false;
            EdgeTrigger.SelectedTrigger = 0;
            EdgeTriggerSelector.IsEnabled = false;
            SaveButton.IsEnabled = false;
            StreamFileButton.IsEnabled = true;
            ProgressValueBlock.Visibility = Visibility.Hidden;
        }

        private void ChannelsGroup_Changed(object sender, RoutedEventArgs e)
        {
            int ActiveChnlGroup = GetActiveChnlGroup();

            SampleCountSelector.SelectedIndex = 0;
            SampleFreqSelector.SelectedIndex = 0;

            ActivateTriggerSelection(ActiveChnlGroup);
            SetLimitsOnSampleCountAndFreq(ActiveChnlGroup);
        }

        private void StartButton_Click(object sender, RoutedEventArgs e)
        {
            ProcessStatus.Value = 0;
            UpdateConfig();
            Samples = null;
            
            if (LAConfig.SamplingMode == BUFFER_MODE)
            {
                ProcessStatus.IsIndeterminate = false;
                SaveButton.IsEnabled = false;
            }
            else
            {
                if (LAConfig.StreamFilePath == null)
                {
                    MessageBox.Show("Choose file to save stream", "", MessageBoxButton.OK, MessageBoxImage.Error);
                    return;
                }
                else
                {
                    long FileLength = new FileInfo(LAConfig.StreamFilePath).Length;
                    if (FileLength != 0)
                    {
                        MessageBoxResult Result = MessageBox.Show("Stream file is not empty and will be overwritten.",
                            "", MessageBoxButton.OKCancel, MessageBoxImage.Warning);
                        if (Result == MessageBoxResult.OK)
                            SetStreamFileLength(0);
                        else
                            return;
                    }
                }

                ProcessStatus.IsIndeterminate = true;
            }

            Start_Click?.Invoke(LAConfig);
            StartButton.IsEnabled = false;
        }

        private void StopButton_Click(object sender, RoutedEventArgs e)
        {
            Stop_Click?.Invoke();
            StartButton.IsEnabled = true;
        }
        
        private void SaveButton_Click(object sender, RoutedEventArgs e)
        {
            if (LAConfig.SamplingMode == BUFFER_MODE)
            {
                SaveFileDialog ChooseFile = new SaveFileDialog();
                ChooseFile.Filter = BinaryFileFilter;
                ChooseFile.FileName = UnderlineString+LAConfig.ChannelsCount.ToString()+ChannelsString
                                     +UnderlineString+LAConfig.SamplingFrequency;
                
                if (ChooseFile.ShowDialog() == true)
                {
                    BinaryWriter OutputFile;
                    if (!File.Exists(ChooseFile.FileName))
                        OutputFile = new BinaryWriter(File.Create(ChooseFile.FileName));
                    else
                        OutputFile = new BinaryWriter(File.Open(ChooseFile.FileName, FileMode.Create));

                    OutputFile.BaseStream.Position = 0;

                    long DataSize = LAConfig.SampleCount * LAConfig.BytesPerValue;

                    for (int i = 0; i < DataSize; i++)
                        OutputFile.Write(Samples[0][i]);

                    OutputFile.Close();
                    OutputFile.Dispose();
                }
            }
        }

        private void ChooseStreamFileButton_Click(object sender, RoutedEventArgs e)
        {
            SaveFileDialog ChooseFile = new SaveFileDialog();
            ChooseFile.Filter = BinaryFileFilter;
            if (ChooseFile.ShowDialog() == true)
            {
                if (!File.Exists(ChooseFile.FileName))
                    File.Create(ChooseFile.FileName);

                LAConfig.StreamFilePath = ChooseFile.FileName;
                StreamFilePathLabel.Content = ChooseFile.FileName;
            }
        }

        private void TriggerActivation_Checked(object sender, RoutedEventArgs e)
        {
            ActivateTriggerSelection(GetActiveChnlGroup());
        }

        private void TriggerActivation_Unchecked(object sender, RoutedEventArgs e)
        {
            DisableTriggerSettings();
        }

        private void SampleSettingsChanged(object sender, SelectionChangedEventArgs e)
        {
            if (this.IsLoaded == true)
                SetLimitsOnSampleCountAndFreq(GetActiveChnlGroup());

            UpdateSampleTime();
            ProcessStatus.Value = 0;
        }
    }
}
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

namespace RDC2_0064
{
    public class ConvertToString
    {


        public static string Time(double Value, string Accuracy)
        {
            string Units;

            if (Value < 0.001)
            {
                Value *= 1000000;
                Units = " us";
            }
            else if (Value < 1.0)
            {
                Value *= 1000;
                Units = " ms";
            }
            else if (Value < 60.0)
                Units = " s";
            else if (Value < 3600.0)
            {
                Value /= 60.0;
                Units = " m";
            }
            else
            {
                Value /= 3600.0;
                Units = " h";
            }

            return (Value.ToString(Accuracy) + Units);
        }
        
        public static string Frequency(double Value, string Accuracy)
        {
            string Units;

            if (Value >= 1000000.0)
            {
                Value /= 1000000;
                Units = " MHz";
            }
            else if (Value >= 1000.0)
            {
                Value /= 1000;
                Units = " kHz";
            }
            else
                Units = " Hz";

            return (Value.ToString(Accuracy) + Units);
        }

        public static string Percentage(double part, double wholevalue, string Accuracy)
        {
            double DutyCycle = 100 * part / wholevalue;
            return (DutyCycle.ToString(Accuracy) + " %");
        }
    }
}

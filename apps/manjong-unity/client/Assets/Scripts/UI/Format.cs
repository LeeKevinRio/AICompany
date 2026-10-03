using System.Globalization;

namespace Manjong.UI
{
    /// <summary>Number / text formatting shared by all screens (culture independent).</summary>
    public static class Format
    {
        public static string Coins(int coins)
        {
            return coins.ToString("N0", CultureInfo.InvariantCulture);
        }

        /// <summary>"+450", "-450" or "0".</summary>
        public static string Signed(int value)
        {
            if (value > 0) return "+" + value.ToString("N0", CultureInfo.InvariantCulture);
            return value.ToString("N0", CultureInfo.InvariantCulture);
        }

        /// <summary>Counts Unicode code points (surrogate pairs count once).</summary>
        public static int CodePointLength(string s)
        {
            if (string.IsNullOrEmpty(s)) return 0;
            int n = 0;
            for (int i = 0; i < s.Length; i++)
            {
                if (!char.IsLowSurrogate(s[i])) n++;
            }
            return n;
        }
    }
}

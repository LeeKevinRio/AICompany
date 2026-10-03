using System.Collections.Generic;
using UnityEngine;

namespace Manjong.UI
{
    /// <summary>
    /// Tile code -> glyphs / colours / Chinese names.
    /// Codes (see 規則與台數表.md): 1m-9m, 1p-9p, 1s-9s, E S W N, RD GD WD, F1-F8.
    /// </summary>
    public static class TileFace
    {
        static readonly string[] ChineseDigits = { "一", "二", "三", "四", "五", "六", "七", "八", "九" };
        static readonly string[] FlowerNames = { "春", "夏", "秋", "冬", "梅", "蘭", "竹", "菊" };

        public static bool IsSuited(string code)
        {
            if (string.IsNullOrEmpty(code) || code.Length != 2) return false;
            char n = code[0];
            char s = code[1];
            return n >= '1' && n <= '9' && (s == 'm' || s == 'p' || s == 's');
        }

        public static bool IsFlower(string code)
        {
            return !string.IsNullOrEmpty(code) && code.Length == 2 && code[0] == 'F' && code[1] >= '1' && code[1] <= '8';
        }

        /// <summary>Large glyph shown in the middle of the tile.</summary>
        public static string MainGlyph(string code)
        {
            if (string.IsNullOrEmpty(code)) return "";
            if (IsSuited(code))
            {
                int n = code[0] - '1';
                if (code[1] == 'm') return ChineseDigits[n];
                return (n + 1).ToString();
            }
            if (IsFlower(code)) return FlowerNames[code[1] - '1'];
            switch (code)
            {
                case "E": return "東";
                case "S": return "南";
                case "W": return "西";
                case "N": return "北";
                case "RD": return "中";
                case "GD": return "發";
                case "WD": return "白";
            }
            return code;
        }

        /// <summary>Small suit caption under the main glyph ("" for honours and flowers).</summary>
        public static string SubGlyph(string code)
        {
            if (!IsSuited(code)) return "";
            switch (code[1])
            {
                case 'm': return "萬";
                case 'p': return "筒";
                default: return "條";
            }
        }

        public static Color GlyphColor(string code)
        {
            if (string.IsNullOrEmpty(code)) return Palette.Ink;
            if (IsSuited(code))
            {
                switch (code[1])
                {
                    case 'm': return Palette.Man;
                    case 'p': return Palette.Pin;
                    default: return Palette.Sou;
                }
            }
            if (IsFlower(code)) return Palette.Flower;
            switch (code)
            {
                case "RD": return Palette.Man;
                case "GD": return Palette.Sou;
                case "WD": return Palette.Pin;
            }
            return Palette.Honor;
        }

        /// <summary>The white dragon is drawn as a blue outlined frame around a blue "白".</summary>
        public static bool HasFrame(string code)
        {
            return code == "WD";
        }

        /// <summary>Human readable name, e.g. "5m" -> "五萬", "RD" -> "紅中".</summary>
        public static string Name(string code)
        {
            if (string.IsNullOrEmpty(code)) return "";
            if (IsSuited(code)) return ChineseDigits[code[0] - '1'] + SubGlyph(code);
            if (IsFlower(code)) return FlowerNames[code[1] - '1'];
            switch (code)
            {
                case "E": return "東風";
                case "S": return "南風";
                case "W": return "西風";
                case "N": return "北風";
                case "RD": return "紅中";
                case "GD": return "青發";
                case "WD": return "白板";
            }
            return code;
        }

        /// <summary>Wind code -> single character ("E" -> "東").</summary>
        public static string WindName(string wind)
        {
            switch (wind)
            {
                case "E": return "東";
                case "S": return "南";
                case "W": return "西";
                case "N": return "北";
            }
            return string.IsNullOrEmpty(wind) ? "" : wind;
        }

        /// <summary>Sort key: man, pin, sou, winds, dragons, flowers.</summary>
        public static int SortKey(string code)
        {
            if (string.IsNullOrEmpty(code)) return 9999;
            if (IsSuited(code))
            {
                int n = code[0] - '0';
                switch (code[1])
                {
                    case 'm': return 100 + n;
                    case 'p': return 200 + n;
                    default: return 300 + n;
                }
            }
            if (IsFlower(code)) return 600 + (code[1] - '0');
            switch (code)
            {
                case "E": return 401;
                case "S": return 402;
                case "W": return 403;
                case "N": return 404;
                case "RD": return 501;
                case "GD": return 502;
                case "WD": return 503;
            }
            return 9000;
        }

        public static List<string> Sorted(string[] codes)
        {
            var list = new List<string>();
            if (codes == null) return list;
            for (int i = 0; i < codes.Length; i++)
            {
                if (!string.IsNullOrEmpty(codes[i])) list.Add(codes[i]);
            }
            // Stable insertion sort keeps equal codes in server order.
            for (int i = 1; i < list.Count; i++)
            {
                string cur = list[i];
                int key = SortKey(cur);
                int j = i - 1;
                while (j >= 0 && SortKey(list[j]) > key)
                {
                    list[j + 1] = list[j];
                    j--;
                }
                list[j + 1] = cur;
            }
            return list;
        }
    }
}

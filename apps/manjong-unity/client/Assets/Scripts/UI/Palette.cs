using UnityEngine;

namespace Manjong.UI
{
    /// <summary>
    /// Cute pastel palette. Text colours are dark brown instead of pure black.
    /// WCAG contrast (computed offline) for every text/background pairing used:
    ///   Ink on Cream 10.85, Card 11.63, Pink 7.82, Sky 8.43, Butter 9.68, Coral 5.94, Gray 8.15,
    ///   Mint 8.68, RowHighlight 9.69, Lavender 8.43, Peach 8.88, DealerBadge 6.90
    ///   InkSoft on Cream 6.93, Card 7.42, Mint 5.54, Butter 6.18, RowHighlight 6.19
    ///   Suit colours on white tile: Man 5.62, Pin 6.47, Sou 5.32, Honor 13.71, Flower 6.37
    ///   Gain/Loss on Card 6.42/6.51, on RowHighlight 5.35/5.43
    ///   Non-text rings: LastDiscardRing on Mint 3.15, SelectRing on Mint 3.05
    /// Result screen (art spec: work/manjong-unity/art/結算畫面-視覺規範.md):
    ///   ResultStageText on ResultStage 10.85, Ink on ResultGold 8.54, Gain on Card 6.42, InkSoft on Card 7.42,
    ///   Gain/Loss on Cream 5.99/6.08, Ink on Coral 5.94 / DealerBadge 6.90 / Pink 7.82
    ///   Non-text: ResultGold vs ResultStage 8.54, Card vs ResultStage 11.63, ResultShooterRing vs Cream 3.94,
    ///   Loss vs Cream 6.08. Do NOT use Coral as an outline on Cream (1.83) nor LastDiscardRing on ResultStage (2.75).
    /// </summary>
    public static class Palette
    {
        public static readonly Color Cream = Hex(0xFF, 0xF4, 0xE0);
        public static readonly Color Card = Hex(0xFF, 0xFD, 0xF7);
        public static readonly Color CardShadow = new Color(0.42f, 0.30f, 0.20f, 0.18f);

        public static readonly Color Ink = Hex(0x4A, 0x32, 0x26);
        public static readonly Color InkSoft = Hex(0x6B, 0x4E, 0x3D);

        public static readonly Color Mint = Hex(0xBE, 0xE6, 0xCF);
        public static readonly Color MintDeep = Hex(0x9F, 0xD4, 0xB8);

        public static readonly Color Pink = Hex(0xFF, 0xC2, 0xD1);
        public static readonly Color Sky = Hex(0xB5, 0xE0, 0xF7);
        public static readonly Color Butter = Hex(0xFF, 0xE7, 0xA0);
        public static readonly Color Coral = Hex(0xFF, 0x9E, 0x8F);
        public static readonly Color Gray = Hex(0xDD, 0xD5, 0xCC);
        public static readonly Color Lavender = Hex(0xE2, 0xD4, 0xF5);
        public static readonly Color Peach = Hex(0xFF, 0xD8, 0xB8);
        public static readonly Color DealerBadge = Hex(0xFF, 0xB3, 0xA7);
        public static readonly Color RowHighlight = Hex(0xFF, 0xE1, 0xEA);

        public static readonly Color TileFace = Color.white;
        public static readonly Color TileEdge = new Color(0.55f, 0.42f, 0.30f, 0.35f);
        public static readonly Color TileBack = Hex(0xF7, 0xB9, 0xCF);
        public static readonly Color TileBackInner = Hex(0xFC, 0xD9, 0xE6);

        public static readonly Color Man = Hex(0xC6, 0x28, 0x28);
        public static readonly Color Pin = Hex(0x1E, 0x5B, 0xB8);
        public static readonly Color Sou = Hex(0x2B, 0x7A, 0x3A);
        public static readonly Color Honor = Hex(0x3A, 0x2A, 0x20);
        public static readonly Color Flower = Hex(0x8A, 0x3F, 0xA0);

        public static readonly Color Gain = Hex(0x23, 0x6B, 0x30);
        public static readonly Color Loss = Hex(0xA9, 0x32, 0x26);

        public static readonly Color LastDiscardRing = Hex(0xD9, 0x48, 0x0F);
        public static readonly Color SelectRing = Hex(0x2F, 0x80, 0xC9);
        public static readonly Color TurnRing = Hex(0xD9, 0x48, 0x0F);
        /// <summary>Same-kind highlight while choosing a discard: amber outline (3.74:1 on Mint, 4.68:1 on the ivory tile) + pale yellow wash.</summary>
        public static readonly Color SameKindRing = Hex(0x9A, 0x62, 0x00);
        public static readonly Color SameKindWash = new Color(1f, 0.86f, 0.15f, 0.38f);

        // Result screen: the winner's stage is a dark "spotlight" on the pastel card.
        public static readonly Color ResultStage = Hex(0x4A, 0x32, 0x26);
        public static readonly Color ResultStageText = Hex(0xFF, 0xF4, 0xE0);
        public static readonly Color ResultGold = Hex(0xFF, 0xD8, 0x4D);
        /// <summary>Soft halo behind the winning tile (decorative).</summary>
        public static readonly Color ResultGlow = new Color(1f, 0.847f, 0.302f, 0.30f);
        /// <summary>Outline of the player who dealt the winning tile (3.94:1 on Cream).</summary>
        public static readonly Color ResultShooterRing = Hex(0xD9, 0x48, 0x0F);
        /// <summary>Thin separators inside result rows / above the buttons (decorative).</summary>
        public static readonly Color ResultDivider = new Color(0.290f, 0.196f, 0.149f, 0.18f);

        public static readonly Color Dim = new Color(0.20f, 0.13f, 0.09f, 0.55f);
        public static readonly Color Transparent = new Color(0f, 0f, 0f, 0f);

        // Avatar backgrounds (text is Ink on top of them).
        public static readonly Color AvatarMe = Pink;
        public static readonly Color AvatarBear = Peach;
        public static readonly Color AvatarCat = Lavender;
        public static readonly Color AvatarRabbit = Sky;

        static Color Hex(byte r, byte g, byte b)
        {
            return new Color32(r, g, b, 255);
        }
    }
}

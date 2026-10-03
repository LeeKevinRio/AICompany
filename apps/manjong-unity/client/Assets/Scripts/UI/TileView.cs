using UnityEngine;
using UnityEngine.UI;

namespace Manjong.UI
{
    /// <summary>Parametrised tile dimensions (UI units at 1920x1080 reference resolution).</summary>
    public struct TileSize
    {
        public float width;
        public float height;
        public int mainFont;
        public int subFont;
        public int radius;
        public float lip;

        public TileSize(float width, float height, int mainFont, int subFont, int radius, float lip)
        {
            this.width = width;
            this.height = height;
            this.mainFont = mainFont;
            this.subFont = subFont;
            this.radius = radius;
            this.lip = lip;
        }

        public Vector2 Vector
        {
            get { return new Vector2(width, height); }
        }
    }

    public static class TileSizes
    {
        /// <summary>My own hand.</summary>
        public static readonly TileSize Large = new TileSize(76f, 106f, 46, 20, 12, 6f);
        /// <summary>Discard rivers and my melds.</summary>
        public static readonly TileSize Small = new TileSize(40f, 54f, 25, 12, 7, 3f);
        /// <summary>Opponent melds / flowers, result panel hands.</summary>
        public static readonly TileSize Mini = new TileSize(30f, 42f, 19, 10, 6, 3f);
        /// <summary>Opponent concealed hands (backs only).</summary>
        public static readonly TileSize Back = new TileSize(26f, 36f, 0, 0, 5, 3f);
    }

    /// <summary>Builds tile visuals: white rounded face with a thicker "lip" at the bottom, or a pastel back.</summary>
    public static class TileView
    {
        static readonly Color LipColor = new Color32(0xF1, 0xDF, 0xC8, 0xFF);
        static readonly Color BackLipColor = new Color32(0xE8, 0x9C, 0xB8, 0xFF);

        /// <summary>
        /// Creates a face-up tile. The returned rect has its size set; the caller positions it.
        /// Hierarchy: Tile (lip colour + shadow) > Face (white) > Main / Sub texts.
        /// </summary>
        public static RectTransform CreateFace(Transform parent, string code, TileSize size)
        {
            var root = UiFactory.CreatePanel(parent, "Tile_" + code, LipColor, size.radius);
            root.rectTransform.sizeDelta = size.Vector;
            UiFactory.AddShadow(root, Palette.TileEdge, new Vector2(0f, -Mathf.Max(1f, size.lip * 0.5f)));

            var face = UiFactory.CreatePanel(root.transform, "Face", Palette.TileFace, size.radius);
            UiFactory.Stretch(face.rectTransform, 0f, 0f, 0f, size.lip);

            Color color = TileFace.GlyphColor(code);
            string sub = TileFace.SubGlyph(code);

            if (TileFace.HasFrame(code))
            {
                float inset = Mathf.Round(size.width * 0.16f);
                var frame = UiFactory.CreateRing(face.transform, "Frame", color, Mathf.Max(2, size.radius - 2), Mathf.Max(2, Mathf.RoundToInt(size.width / 24f)), 0f);
                UiFactory.Stretch(frame.rectTransform, inset, inset * 1.2f, inset, inset * 1.2f);
            }

            var main = UiFactory.CreateText(face.transform, "Main", TileFace.MainGlyph(code), size.mainFont, color, TextAnchor.MiddleCenter);
            main.fontStyle = FontStyle.Bold;
            main.horizontalOverflow = HorizontalWrapMode.Overflow;
            main.verticalOverflow = VerticalWrapMode.Overflow;

            if (sub.Length > 0)
            {
                main.rectTransform.anchorMin = new Vector2(0f, 0.36f);
                main.rectTransform.anchorMax = new Vector2(1f, 1f);
                main.rectTransform.offsetMin = Vector2.zero;
                main.rectTransform.offsetMax = new Vector2(0f, -1f);

                var subText = UiFactory.CreateText(face.transform, "Sub", sub, size.subFont, color, TextAnchor.MiddleCenter);
                subText.horizontalOverflow = HorizontalWrapMode.Overflow;
                subText.verticalOverflow = VerticalWrapMode.Overflow;
                subText.rectTransform.anchorMin = new Vector2(0f, 0.04f);
                subText.rectTransform.anchorMax = new Vector2(1f, 0.40f);
                subText.rectTransform.offsetMin = Vector2.zero;
                subText.rectTransform.offsetMax = Vector2.zero;
            }
            else
            {
                UiFactory.Stretch(main.rectTransform);
            }
            return root.rectTransform;
        }

        /// <summary>Face-down tile (opponent hands, concealed kongs).</summary>
        public static RectTransform CreateBack(Transform parent, TileSize size)
        {
            var root = UiFactory.CreatePanel(parent, "TileBack", BackLipColor, size.radius);
            root.rectTransform.sizeDelta = size.Vector;
            UiFactory.AddShadow(root, Palette.TileEdge, new Vector2(0f, -Mathf.Max(1f, size.lip * 0.5f)));

            var body = UiFactory.CreatePanel(root.transform, "Body", Palette.TileBack, size.radius);
            UiFactory.Stretch(body.rectTransform, 0f, 0f, 0f, size.lip);

            float inset = Mathf.Max(3f, Mathf.Round(size.width * 0.16f));
            var inner = UiFactory.CreatePanel(body.transform, "Inner", Palette.TileBackInner, Mathf.Max(2, size.radius - 2));
            UiFactory.Stretch(inner.rectTransform, inset, inset, inset, inset);
            return root.rectTransform;
        }

        /// <summary>Puts an outline ring around a tile (last discard, selection).</summary>
        public static Image AddRing(RectTransform tile, Color color, TileSize size, int thickness)
        {
            var ring = UiFactory.CreateRing(tile, "Ring", color, size.radius + thickness, thickness, thickness + 1f);
            return ring;
        }

        /// <summary>Semi-transparent veil that marks a tile as currently not playable.</summary>
        public static void AddVeil(RectTransform tile, TileSize size)
        {
            var veil = UiFactory.CreatePanel(tile, "Veil", new Color(0.55f, 0.47f, 0.40f, 0.35f), size.radius);
            UiFactory.Stretch(veil.rectTransform);
        }
    }
}

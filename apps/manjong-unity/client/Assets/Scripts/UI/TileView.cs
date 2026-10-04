using System.Collections.Generic;
using Manjong.Net;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.UI
{
    /// <summary>Parametrised tile dimensions (UI units at the 1920x1080 reference resolution). Always 3:4.</summary>
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
        public static readonly TileSize Large = new TileSize(75f, 100f, 45, 20, 12, 6f);
        /// <summary>Discard rivers and my melds. Fallback sub caption >= 16.</summary>
        public static readonly TileSize Small = new TileSize(42f, 56f, 25, 16, 7, 3f);
        /// <summary>Opponent melds / flowers, result panel hands, choice menus. Fallback sub caption >= 13.</summary>
        public static readonly TileSize Mini = new TileSize(33f, 44f, 20, 13, 6, 3f);
        /// <summary>Opponent concealed hands (backs only).</summary>
        public static readonly TileSize Back = new TileSize(27f, 36f, 0, 0, 5, 3f);
    }

    /// <summary>
    /// Tile visuals. Primary: the painted tile images in Resources/Tiles/&lt;code&gt;.png (back.png for the back),
    /// 150x200 px with transparent corners, shown with preserveAspect. When an image is missing the tile falls back
    /// to the code-drawn text tile (white rounded face with a lip) and logs a warning once per code.
    /// </summary>
    public static class TileView
    {
        public const string BackCode = "back";
        const string ResourceFolder = "Tiles/";

        static readonly Color LipColor = new Color32(0xF1, 0xDF, 0xC8, 0xFF);
        static readonly Color BackLipColor = new Color32(0xE8, 0x9C, 0xB8, 0xFF);
        static readonly Dictionary<string, Sprite> SpriteCache = new Dictionary<string, Sprite>();

        /// <summary>Cached sprite for a tile code (or "back"); null when Resources/Tiles has no image for it.</summary>
        public static Sprite SpriteFor(string code)
        {
            if (string.IsNullOrEmpty(code)) return null;
            Sprite cached;
            if (SpriteCache.TryGetValue(code, out cached)) return cached; // null is cached too (warn once)

            Sprite sprite = null;
            var tex = Resources.Load<Texture2D>(ResourceFolder + code);
            if (tex != null)
            {
                sprite = Sprite.Create(tex, new Rect(0f, 0f, tex.width, tex.height), new Vector2(0.5f, 0.5f), 100f, 0, SpriteMeshType.FullRect);
                sprite.name = "Tile_" + code;
            }
            else
            {
                Debug.LogWarning("[Manjong] Tile image Resources/" + ResourceFolder + code + ".png not found, using the text tile.");
            }
            SpriteCache[code] = sprite;
            return sprite;
        }

        static RectTransform CreateImageTile(Transform parent, string name, Sprite sprite, TileSize size)
        {
            var rt = UiFactory.CreateRect(name, parent);
            rt.sizeDelta = size.Vector;
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = sprite;
            img.type = Image.Type.Simple;
            img.preserveAspect = true;
            img.raycastTarget = false;
            return rt;
        }

        /// <summary>
        /// Face-up tile with its size set; the caller positions it. The root carries an Image (raycastTarget off),
        /// so callers may enable raycasts / add a Button on it.
        /// </summary>
        public static RectTransform CreateFace(Transform parent, string code, TileSize size)
        {
            Sprite sprite = SpriteFor(code);
            if (sprite != null) return CreateImageTile(parent, "Tile_" + code, sprite, size);
            return CreateTextFace(parent, code, size);
        }

        /// <summary>Face-down tile (opponent hands, concealed kongs).</summary>
        public static RectTransform CreateBack(Transform parent, TileSize size)
        {
            Sprite sprite = SpriteFor(BackCode);
            if (sprite != null) return CreateImageTile(parent, "TileBack", sprite, size);
            return CreateTextBack(parent, size);
        }

        // ---------- Fallback (code-drawn) tiles ----------

        static RectTransform CreateTextFace(Transform parent, string code, TileSize size)
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

        static RectTransform CreateTextBack(Transform parent, TileSize size)
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

        // ---------- Overlays ----------

        /// <summary>Puts an outline ring around a tile (last discard, selection, waits).</summary>
        public static Image AddRing(RectTransform tile, Color color, TileSize size, int thickness)
        {
            return UiFactory.CreateRing(tile, "Ring", color, size.radius + thickness, thickness, thickness + 1f);
        }

        /// <summary>Semi-transparent veil that marks a tile as currently not playable.</summary>
        public static void AddVeil(RectTransform tile, TileSize size)
        {
            var veil = UiFactory.CreatePanel(tile, "Veil", new Color(0.55f, 0.47f, 0.40f, 0.35f), size.radius);
            UiFactory.Stretch(veil.rectTransform);
        }

        // ---------- Melds ----------

        /// <summary>Width a meld occupies: upright tiles plus one sideways tile (the claimed one), 1-unit gaps.</summary>
        public static float MeldWidth(MeldDto m, TileSize size)
        {
            if (m == null) return 0f;
            int n = DtoUtil.Safe(m.tiles).Length;
            if (n == 0) return 0f;
            bool sideways = HasSidewaysTile(m, n);
            return (sideways ? (n - 1) * size.width + size.height : n * size.width) + (n - 1);
        }

        static bool HasSidewaysTile(MeldDto m, int n)
        {
            return m.type != "ankan" && m.claimedIndex >= 0 && m.claimedIndex < n;
        }

        /// <summary>
        /// Builds one meld in a container of size (MeldWidth, size.height) whose children use top-left coordinates;
        /// the caller positions the container. The claimed tile (claimedIndex) lies sideways and bottom-aligned,
        /// as on a real table; a concealed kong shows its two outer tiles face down.
        /// </summary>
        public static RectTransform CreateMeld(Transform parent, MeldDto m, TileSize size)
        {
            var box = UiFactory.CreateRect("Meld_" + DtoUtil.Safe(m.type), parent);
            box.sizeDelta = new Vector2(MeldWidth(m, size), size.height);

            string[] tiles = DtoUtil.Safe(m.tiles);
            bool concealed = m.type == "ankan" && tiles.Length == 4;
            bool sideways = HasSidewaysTile(m, tiles.Length);
            float x = 0f;
            for (int i = 0; i < tiles.Length; i++)
            {
                if (sideways && i == m.claimedIndex)
                {
                    RectTransform t = CreateFace(box, tiles[i], size);
                    t.anchorMin = new Vector2(0f, 1f);
                    t.anchorMax = new Vector2(0f, 1f);
                    t.pivot = new Vector2(0.5f, 0.5f);
                    t.sizeDelta = size.Vector;
                    t.localEulerAngles = new Vector3(0f, 0f, 90f);
                    // Rotated footprint is height x width; centre it horizontally and sit it on the row's bottom edge.
                    t.anchoredPosition = new Vector2(x + size.height * 0.5f, -(size.height - size.width * 0.5f));
                    x += size.height + 1f;
                }
                else
                {
                    bool faceDown = concealed && (i == 0 || i == 3);
                    RectTransform t = faceDown ? CreateBack(box, size) : CreateFace(box, tiles[i], size);
                    UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, 0f), size.Vector);
                    x += size.width + 1f;
                }
            }
            return box;
        }
    }
}

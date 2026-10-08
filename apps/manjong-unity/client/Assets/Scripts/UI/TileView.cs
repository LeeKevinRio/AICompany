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
        /// <summary>Result stage: the winner's melds and hand.</summary>
        public static readonly TileSize Stage = new TileSize(54f, 72f, 32, 20, 9, 4f);
        /// <summary>Result stage: the winning tile (1.28x Stage).</summary>
        public static readonly TileSize StageWin = new TileSize(69f, 92f, 41, 25, 11, 5f);
        /// <summary>Result stage: the winner's flowers (one size below Stage).</summary>
        public static readonly TileSize StageFlower = new TileSize(36f, 48f, 22, 14, 6, 3f);
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
            if (SpriteCache.TryGetValue(code, out cached))
            {
                // A cached "missing" entry is a real null (warn once). A sprite destroyed by Unity (e.g. Play mode
                // without domain reload) compares equal to null but is not a null reference: rebuild it.
                if (ReferenceEquals(cached, null) || cached != null) return cached;
                SpriteCache.Remove(code);
            }

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

        /// <summary>
        /// "Same kind" highlight while a hand tile is selected: a pale yellow wash over the tile plus a thick amber
        /// outline (the outline has 3:1 contrast against the mint table).
        /// </summary>
        public static void AddSameKindHighlight(RectTransform tile, TileSize size)
        {
            var wash = UiFactory.CreatePanel(tile, "SameKindWash", Palette.SameKindWash, size.radius);
            UiFactory.Stretch(wash.rectTransform);
            AddRing(tile, Palette.SameKindRing, size, Mathf.Max(3, Mathf.RoundToInt(size.width / 14f)));
        }

        /// <summary>Small pill sitting on a tile's top edge ("聽", "胡", "自摸"), poking "above" units over the top.</summary>
        public static void AddBadge(RectTransform tile, string text, Color bg, float above)
        {
            float w = 18f + 22f * text.Length;
            var pill = UiFactory.CreatePanel(tile, "Badge_" + text, bg, 12);
            UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 0f), new Vector2(0f, above - 28f), new Vector2(w, 28f));
            UiFactory.CreateRing(pill.transform, "Ring", Palette.LastDiscardRing, 12, 2, 0f);
            var t = UiFactory.CreateLabel(pill.transform, "Text", text, 20, Palette.Ink, TextAnchor.MiddleCenter);
            t.fontStyle = FontStyle.Bold;
            UiFactory.Stretch(t.rectTransform, 2f, 1f, 2f, 1f);
        }

        // ---------- Melds ----------

        /// <summary>Width of a meld: every tile upright and equally spaced (1-unit gaps).</summary>
        public static float MeldWidth(MeldDto m, TileSize size)
        {
            if (m == null) return 0f;
            int n = DtoUtil.Safe(m.tiles).Length;
            return n == 0 ? 0f : n * size.width + (n - 1);
        }

        /// <summary>
        /// Builds one meld in a container of size (MeldWidth, size.height) whose children use top-left coordinates;
        /// the caller positions the container. Tiles are upright in the server's order (for chi the claimed tile
        /// is already in the middle); a concealed kong shows its two outer tiles face down.
        /// Face-up tiles equal to "highlightCode" get the same-kind highlight.
        /// </summary>
        public static RectTransform CreateMeld(Transform parent, MeldDto m, TileSize size, string highlightCode)
        {
            var box = UiFactory.CreateRect("Meld_" + DtoUtil.Safe(m.type), parent);
            box.sizeDelta = new Vector2(MeldWidth(m, size), size.height);

            string[] tiles = DtoUtil.Safe(m.tiles);
            bool concealed = m.type == "ankan" && tiles.Length == 4;
            for (int i = 0; i < tiles.Length; i++)
            {
                bool faceDown = concealed && (i == 0 || i == 3);
                RectTransform t = faceDown ? CreateBack(box, size) : CreateFace(box, tiles[i], size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(i * (size.width + 1f), 0f), size.Vector);
                if (!faceDown && !string.IsNullOrEmpty(highlightCode) && tiles[i] == highlightCode) AddSameKindHighlight(t, size);
            }
            return box;
        }

        /// <summary>
        /// Copies of `code` accounted for by this meld. A concealed kong shows its two inner tiles face up, so
        /// its kind is public and all four copies are known to be used (same rule as the server's `left`).
        /// </summary>
        public static int VisibleCount(MeldDto m, string code)
        {
            if (m == null) return 0;
            string[] tiles = DtoUtil.Safe(m.tiles);
            int n = 0;
            for (int i = 0; i < tiles.Length; i++)
            {
                if (tiles[i] == code) n++;
            }
            return n;
        }
    }
}

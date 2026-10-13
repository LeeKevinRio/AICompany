using System.Collections.Generic;
using Manjong.Net;
using UnityEngine;

namespace Manjong.UI
{
    /// <summary>
    /// The tiles I am waiting on, drawn as a row of chips: the tile picture (Mini size) with a small pill "剩 N" right under it
    /// (N = copies still unseen, from the server's WaitDto.left). A kind with nothing left is greyed out
    /// (washed-out tile, grey pill "剩 0"). Chips sit on a fixed pitch from the row's left edge, one row only; every chip has the same
    /// size whatever the number of kinds. When more kinds than fit are given, the last slot becomes a "+N" chip.
    /// </summary>
    public static class WaitChips
    {
        const float Gap = 9f;
        const float PillW = 38f;
        const float PillH = 20f;
        const float PillGap = 2f;

        /// <summary>Distance between the left edges of two neighbouring chips.</summary>
        public static float Pitch
        {
            get { return TileSizes.Mini.width + Gap; }
        }

        /// <summary>Row height: the tile, a 2 unit gap and the pill below it (the pill never covers the tile face).</summary>
        public static float Height
        {
            get { return TileSizes.Mini.height + PillGap + PillH; }
        }

        /// <summary>How many chips fit into a row of this width.</summary>
        public static int Capacity(float width)
        {
            return Mathf.Max(1, Mathf.FloorToInt((width + Gap) / Pitch));
        }

        /// <summary>Wait entries that can be drawn (a tile code is required), in the server's order.</summary>
        public static List<WaitDto> Valid(WaitDto[] waits)
        {
            var list = new List<WaitDto>();
            WaitDto[] all = DtoUtil.Safe(waits);
            for (int i = 0; i < all.Length; i++)
            {
                if (all[i] != null && !string.IsNullOrEmpty(all[i].tile)) list.Add(all[i]);
            }
            return list;
        }

        /// <summary>Signature of what Build would draw; lets the caller rebuild only on change.</summary>
        public static string Signature(WaitDto[] waits)
        {
            var sb = new System.Text.StringBuilder();
            List<WaitDto> list = Valid(waits);
            for (int i = 0; i < list.Count; i++) sb.Append(list[i].tile).Append(':').Append(Mathf.Max(0, list[i].left)).Append(',');
            return sb.ToString();
        }

        /// <summary>Rebuilds the chips inside `row` (children use top-left coordinates). Returns the number of chips drawn.</summary>
        public static int Build(RectTransform row, WaitDto[] waits)
        {
            UiFactory.DestroyChildren(row);
            List<WaitDto> list = Valid(waits);
            int capacity = Capacity(row.sizeDelta.x);
            int shown = list.Count <= capacity ? list.Count : capacity - 1;
            for (int i = 0; i < shown; i++) CreateChip(row, list[i], i);
            if (shown < list.Count) CreateMore(row, shown, list.Count - shown);
            return shown;
        }

        static void CreateChip(RectTransform row, WaitDto wait, int index)
        {
            TileSize size = TileSizes.Mini;
            int left = Mathf.Max(0, wait.left);
            bool none = left == 0;

            var chip = UiFactory.CreateRect("Chip_" + wait.tile, row);
            UiFactory.Place(chip, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(index * Pitch, 0f), new Vector2(size.width, Height));

            RectTransform tile = TileView.CreateFace(chip, wait.tile, size);
            UiFactory.Place(tile, new Vector2(0f, 1f), new Vector2(0f, 1f), Vector2.zero, size.Vector);
            if (none)
            {
                TileView.AddVeil(tile, size);
                var group = tile.gameObject.AddComponent<CanvasGroup>();
                group.alpha = 0.45f;
                group.blocksRaycasts = false;
                group.interactable = false;
            }

            var pill = UiFactory.CreatePanel(chip, "Count", none ? Palette.Gray : Palette.Coral, 10);
            UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), Vector2.zero, new Vector2(PillW, PillH));
            UiFactory.CreateRing(pill.transform, "Ring", none ? Palette.InkSoft : Palette.LastDiscardRing, 10, 2, 0f);
            var text = UiFactory.CreateLabel(pill.transform, "Text", "剩 " + left, 18, Palette.Ink, TextAnchor.MiddleCenter);
            text.fontStyle = FontStyle.Bold;
            UiFactory.Stretch(text.rectTransform, 1f, 0f, 1f, 0f);
        }

        static void CreateMore(RectTransform row, int index, int more)
        {
            var pill = UiFactory.CreatePanel(row, "More", Palette.Butter, 12);
            UiFactory.Place(pill.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f),
                new Vector2(index * Pitch, -(TileSizes.Mini.height - 28f) * 0.5f), new Vector2(TileSizes.Mini.width + 4f, 28f));
            UiFactory.CreateRing(pill.transform, "Ring", Palette.InkSoft, 12, 2, 0f);
            var text = UiFactory.CreateLabel(pill.transform, "Text", "+" + more, 20, Palette.Ink, TextAnchor.MiddleCenter);
            text.fontStyle = FontStyle.Bold;
            UiFactory.Stretch(text.rectTransform, 1f, 0f, 1f, 0f);
        }
    }
}

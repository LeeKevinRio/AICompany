using System;
using System.Collections.Generic;

namespace Manjong.Screens
{
    /// <summary>
    /// Pure geometry of the result screen (no Unity types, so it can be exercised outside the engine).
    /// All numbers come from work/manjong-unity/art/結算畫面-視覺規範.md. Units are UI units at the 1920x1080
    /// reference resolution; origins are the top-left corner of the owning container, y grows downward.
    /// Tile sizes are duplicated here as constants; ResultPanel checks them against TileSizes once.
    /// </summary>
    public static class ResultLayout
    {
        // ----- Tile sizes (width x height) -----
        public const float StageTileW = 54f, StageTileH = 72f;
        public const float WinTileW = 69f, WinTileH = 92f;
        public const float FlowerTileW = 36f, FlowerTileH = 48f;
        public const float MiniW = 33f, MiniH = 44f;
        public const float SmallW = 42f, SmallH = 56f;

        // ----- Card -----
        public const float CardWidth = 1780f;
        public const float CardMinHeight = 720f;
        public const float CardMaxHeight = 1040f;
        public const float ButtonsZone = 124f;
        public const float RowPadX = 30f;
        public const float InnerW = CardWidth - 2f * RowPadX;     // 1720

        // ----- Win layout: title, stage -----
        public const float WinTitleY = 14f, WinTitleH = 60f;
        public const float StageTop = 82f;
        public const float StagePad = 24f;
        public const float StageInnerW = InnerW - 2f * StagePad;  // 1672
        public const float BandAHeight = 134f;
        public const float BandBTop = 164f;                       // 16 + 134 + 14
        public const float BandBHeight = 112f;
        public const float BandBWrapExtra = 56f;
        public const float BaselineY = BandBTop + 104f;           // bottom edge of every tile of the stage
        public const float BandGapAfterB = 16f;
        public const float StageBottomPad = 18f;
        public const float DealerNoteGap = 8f;
        public const float DealerNoteHeight = 30f;
        public const float StageMeldGap = 28f;
        public const float StageBlockGap = 40f;                   // flowers -> melds
        public const float StageWinGap = 44f;                     // hand -> winning tile, and left block -> hand
        public const float StageWinRightInset = 8f;
        public const float WinTileX = StageInnerW + StagePad - StageWinRightInset - WinTileW;  // 1619
        public const float StageHandRight = WinTileX - StageWinGap;                            // 1575
        public const float StageFlowerWrapDrop = 8f;              // 2nd line top = baseline + 8
        public const float StageMinScale = 0.85f;

        // ----- Tai chips -----
        public const float ChipH = 48f;
        public const float ChipGap = 10f;
        public const float ChipBadgeW = 64f;
        public const int ChipOverflowUnits = 18;

        // ----- Seat rows (compact = other three in a win, roomy = exhaustive draw) -----
        public const float RowWidth = InnerW;
        public const float RowTilesX = 462f;
        public const float RowTilesRight = 1704f;
        public const float RowTilesW = RowTilesRight - RowTilesX;  // 1242
        public const float RowBlockGap = 36f;
        public const float RowFlowerLineGap = 6f;
        public const float RowBottomPad = 10f;
        public const float DrawTitleY = 18f, DrawTitleH = 64f;
        public const float DrawSubtitleY = 86f, DrawSubtitleH = 36f;
        public const float DrawRowsTop = 136f;
        public const int StageRowsAfterWinner = 3;

        public static float RowHeight(bool roomy) { return roomy ? 104f : 76f; }
        public static float RowGap(bool roomy) { return roomy ? 10f : 8f; }
        public static float RowMeldGap(bool roomy) { return roomy ? 28f : 24f; }
        public static float RowTileW(bool roomy) { return roomy ? SmallW : MiniW; }
        public static float RowTileH(bool roomy) { return roomy ? SmallH : MiniH; }
        public static float RowTilesTop(bool roomy) { return (RowHeight(roomy) - RowTileH(roomy)) / 2f; }

        // ---------- Stage tiles ----------

        public static float StageHandWidth(int handTiles)
        {
            return handTiles <= 0 ? 0f : handTiles * (StageTileW + 1f) - 1f;
        }

        public static float StageFlowersWidth(int flowers)
        {
            return flowers <= 0 ? 0f : flowers * (FlowerTileW + 1f) - 1f;
        }

        public static float StageMeldsWidth(IList<int> meldSizes)
        {
            float w = 0f;
            for (int i = 0; i < meldSizes.Count; i++)
            {
                w += (i > 0 ? StageMeldGap : 0f) + meldSizes[i] * (StageTileW + 1f) - 1f;
            }
            return w;
        }

        /// <summary>Flowers (when on the main line), a block gap, then the melds.</summary>
        public static float StageLeftWidth(int flowers, IList<int> meldSizes)
        {
            float w = StageFlowersWidth(flowers);
            if (meldSizes.Count > 0) w += (flowers > 0 ? StageBlockGap : 0f) + StageMeldsWidth(meldSizes);
            return w;
        }

        /// <summary>True when the flowers must move to a second line: one line would not fit in the stage's inner width.</summary>
        public static bool StageFlowersWrap(int flowers, IList<int> meldSizes, int handTiles)
        {
            if (flowers <= 0) return false;
            float need = StageLeftWidth(flowers, meldSizes) + StageWinGap + StageHandWidth(handTiles)
                + StageWinGap + WinTileW + StageWinRightInset;
            return need > StageInnerW;
        }

        /// <summary>
        /// Left block + gap + hand must end at StageHandRight. Returns the uniform scale (1 normally; 0.85 at the
        /// lowest) that makes them fit when even the no-flower line is too wide. Never expected in real games.
        /// </summary>
        public static float StageRowScale(int flowersOnLine, IList<int> meldSizes, int handTiles)
        {
            float need = StageLeftWidth(flowersOnLine, meldSizes) + StageWinGap + StageHandWidth(handTiles);
            float avail = StageHandRight - StagePad;
            if (need <= avail) return 1f;
            return Math.Max(StageMinScale, avail / need);
        }

        // ---------- Tai chips ----------

        public const int SlotNotice = -1;   // "no tai items" sentence
        public const int SlotDealer = -2;   // dealer tai chip

        public struct ChipSlot
        {
            public int Index;   // item index, SlotNotice or SlotDealer
            public int Col;
            public int Row;
            public int Span;    // columns used
        }

        public static int ChipCols(int itemCount, bool dealer)
        {
            return itemCount + (dealer ? 2 : 0) > ChipOverflowUnits ? 8 : 6;
        }

        /// <summary>Largest whole chip width for the column count (6 -> 270, 8 -> 200).</summary>
        public static float ChipWidth(int cols)
        {
            return (float)Math.Floor((StageInnerW - (cols - 1) * ChipGap) / cols);
        }

        /// <summary>Items in server order, then the dealer chip (2 columns, next row if it does not fit).</summary>
        public static List<ChipSlot> ChipSlots(int itemCount, bool dealer, int cols, out int rows)
        {
            var slots = new List<ChipSlot>();
            int col = 0, row = 0;
            Action<int, int> add = (index, span) =>
            {
                if (col + span > cols) { row++; col = 0; }
                slots.Add(new ChipSlot { Index = index, Col = col, Row = row, Span = span });
                col += span;
            };
            if (itemCount <= 0) add(SlotNotice, 2);
            for (int i = 0; i < itemCount; i++) add(i, 1);
            if (dealer) add(SlotDealer, 2);
            rows = row + 1;
            return slots;
        }

        public static float ChipGridHeight(int rows)
        {
            return rows * ChipH + (rows - 1) * ChipGap;
        }

        public static float BandBHeightFor(bool flowersWrap)
        {
            return BandBHeight + (flowersWrap ? BandBWrapExtra : 0f);
        }

        public static float StageHeight(bool flowersWrap, int chipRows, bool dealerNote)
        {
            return 16f + BandAHeight + 14f + BandBHeightFor(flowersWrap) + BandGapAfterB
                + ChipGridHeight(chipRows) + (dealerNote ? DealerNoteGap + DealerNoteHeight : 0f) + StageBottomPad;
        }

        // ---------- Seat rows ----------

        public static float RowHandWidth(bool roomy, int handTiles)
        {
            return handTiles <= 0 ? 0f : handTiles * (RowTileW(roomy) + 1f) - 1f;
        }

        public static float RowFlowersWidth(int flowers)
        {
            return flowers <= 0 ? 0f : flowers * (MiniW + 1f) - 1f;
        }

        public static float RowMeldsWidth(bool roomy, IList<int> meldSizes)
        {
            float w = 0f;
            for (int i = 0; i < meldSizes.Count; i++)
            {
                w += (i > 0 ? RowMeldGap(roomy) : 0f) + meldSizes[i] * (RowTileW(roomy) + 1f) - 1f;
            }
            return w;
        }

        public static float RowLeftWidth(bool roomy, int flowers, IList<int> meldSizes)
        {
            float w = RowFlowersWidth(flowers);
            if (meldSizes.Count > 0) w += (flowers > 0 ? RowBlockGap : 0f) + RowMeldsWidth(roomy, meldSizes);
            return w;
        }

        public static bool RowFlowersWrap(bool roomy, int flowers, IList<int> meldSizes, int handTiles)
        {
            if (flowers <= 0) return false;
            return RowLeftWidth(roomy, flowers, meldSizes) + RowBlockGap + RowHandWidth(roomy, handTiles) > RowTilesW;
        }

        public static float RowHeightFor(bool roomy, bool flowersWrap)
        {
            if (!flowersWrap) return RowHeight(roomy);
            return Math.Max(RowHeight(roomy), RowTilesTop(roomy) + RowTileH(roomy) + RowFlowerLineGap + MiniH + RowBottomPad);
        }

        // ---------- Card ----------

        public static float CardHeightFor(float contentEnd)
        {
            return Math.Min(CardMaxHeight, Math.Max(CardMinHeight, contentEnd + ButtonsZone));
        }
    }
}

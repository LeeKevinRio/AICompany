using System;
using System.Collections.Generic;
using Manjong.Net;
using Manjong.UI;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.Screens
{
    /// <summary>
    /// Hand / game result overlay (spec: work/manjong-unity/art/結算畫面-視覺規範.md; geometry in ResultLayout).
    /// Win: title, then a dark "stage" for the winner (avatar, name, seat wind, self-draw / shooter capsule,
    /// score board with total tai and the amount won, the full tile row with the winning tile enlarged, gold
    /// framed and set apart at the far right, and a grid of tai chips plus a wide dealer-tai chip), then one
    /// compact row for each of the other three (the shooter first). Exhaustive draw: no stage, four roomy rows.
    /// No captions: the layout tells the tile groups apart (flowers + melds left, hand right-aligned, a chi has
    /// the claimed tile in the middle, a concealed kong shows its two outer tiles face down).
    /// The card height is dynamic (720..1040) and the width fixed at 1780: the canvas scales with match 0.5, so a
    /// 16:10 screen is only about 1821 units wide. Content is rebuilt on every Show().
    /// </summary>
    public class ResultPanel
    {
        GameObject root;
        RectTransform card;
        Action onNext;
        Action onLobby;
        Button nextButton;

        public bool IsVisible
        {
            get { return root != null && root.activeSelf; }
        }

        public void Build(Transform parent)
        {
            var dim = UiFactory.CreateBlocker(parent, "ResultPanel", Palette.Dim);
            root = dim.gameObject;
            var cardImg = UiFactory.CreatePanel(dim.transform, "Card", Palette.Card, 40);
            UiFactory.Place(cardImg.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(ResultLayout.CardWidth, ResultLayout.CardMaxHeight));
            UiFactory.AddShadow(cardImg, Palette.CardShadow, new Vector2(0f, -8f));
            card = cardImg.rectTransform;
            root.SetActive(false);
            CheckTileSizes();
        }

        /// <summary>ResultLayout keeps its own copy of the tile sizes; warn once if TileSizes drifted.</summary>
        static void CheckTileSizes()
        {
            bool ok = TileSizes.Stage.width == ResultLayout.StageTileW && TileSizes.Stage.height == ResultLayout.StageTileH
                && TileSizes.StageWin.width == ResultLayout.WinTileW && TileSizes.StageWin.height == ResultLayout.WinTileH
                && TileSizes.StageFlower.width == ResultLayout.FlowerTileW && TileSizes.StageFlower.height == ResultLayout.FlowerTileH
                && TileSizes.Mini.width == ResultLayout.MiniW && TileSizes.Mini.height == ResultLayout.MiniH
                && TileSizes.Small.width == ResultLayout.SmallW && TileSizes.Small.height == ResultLayout.SmallH;
            if (!ok) Debug.LogWarning("[Manjong] ResultLayout tile constants differ from TileSizes; update ResultLayout.");
        }

        public void Hide()
        {
            if (root != null) root.SetActive(false);
        }

        // ---------- Small builders (top-left coordinates) ----------

        static void At(RectTransform rt, float x, float y, float w, float h)
        {
            UiFactory.Place(rt, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -y), new Vector2(w, h));
        }

        static Image Panel(Transform parent, string name, Color color, int radius, float x, float y, float w, float h)
        {
            var img = UiFactory.CreatePanel(parent, name, color, radius);
            At(img.rectTransform, x, y, w, h);
            return img;
        }

        static Text Label(Transform parent, string name, string text, int size, Color color, TextAnchor anchor,
            float x, float y, float w, float h, bool bold = false, int minSize = 0)
        {
            var t = UiFactory.CreateLabel(parent, name, text, size, color, anchor);
            if (bold) t.fontStyle = FontStyle.Bold;
            if (minSize > 0) t.resizeTextMinSize = minSize;
            At(t.rectTransform, x, y, w, h);
            return t;
        }

        static string NameOf(GameView v, int seat)
        {
            var p = DtoUtil.Player(v, seat);
            return p != null && !string.IsNullOrEmpty(p.name) ? p.name : "座位 " + seat;
        }

        static Color SignColor(int value)
        {
            return value > 0 ? Palette.Gain : (value < 0 ? Palette.Loss : Palette.Ink);
        }

        // ---------- Show ----------

        public void Show(GameView v, Action next, Action lobby)
        {
            onNext = next;
            onLobby = lobby;
            UiFactory.DestroyChildren(card);
            root.SetActive(true);
            root.transform.SetAsLastSibling();

            bool gameEnd = v.phase == "game_end";
            HandResult r = v.hasResult ? v.result : null;
            bool isWin = r != null && r.kind == "win" && r.winnerSeat >= 0 && DtoUtil.Player(v, r.winnerSeat) != null;
            bool selfDraw = isWin && (r.selfDraw || r.loserSeat < 0);
            bool bankrupt = gameEnd && v.endReason == "bankrupt";
            int[] deltas = r != null ? DtoUtil.Safe(r.deltas) : new int[0];

            float contentEnd;
            if (isWin) contentEnd = BuildWinLayout(v, r, selfDraw, gameEnd, bankrupt, deltas);
            else contentEnd = BuildDrawLayout(v, r, gameEnd, bankrupt, deltas);

            float cardH = ResultLayout.CardHeightFor(contentEnd);
            if (contentEnd + ResultLayout.ButtonsZone > ResultLayout.CardMaxHeight)
            {
                Debug.LogWarning("[Manjong] Result content ends at y=" + contentEnd + ", card capped at " + ResultLayout.CardMaxHeight + ".");
            }
            card.sizeDelta = new Vector2(ResultLayout.CardWidth, cardH);
            BuildButtons(gameEnd, bankrupt);
        }

        // ---------- Win layout ----------

        float BuildWinLayout(GameView v, HandResult r, bool selfDraw, bool gameEnd, bool bankrupt, int[] deltas)
        {
            string title;
            if (bankrupt)
            {
                title = "金幣歸零，牌局結束·" + NameOf(v, r.winnerSeat) + (selfDraw ? " 自摸" : " 胡牌");
            }
            else
            {
                title = (gameEnd ? "整場結束·" : "") + (selfDraw ? "自摸！" : "胡牌！");
            }
            Label(card, "Title", title, 46, Palette.Ink, TextAnchor.MiddleCenter,
                ResultLayout.RowPadX, ResultLayout.WinTitleY, ResultLayout.InnerW, ResultLayout.WinTitleH, true, bankrupt ? 26 : 0);

            PlayerView winner = DtoUtil.Player(v, r.winnerSeat);
            int winnerDelta = r.winnerSeat < deltas.Length ? deltas[r.winnerSeat] : 0;
            float y = BuildStage(v, r, winner, selfDraw, gameEnd, winnerDelta) + 14f;

            // Others: the shooter first, then clockwise from the winner's next seat.
            var order = new List<int>();
            if (!selfDraw && r.loserSeat >= 0 && r.loserSeat != r.winnerSeat && DtoUtil.Player(v, r.loserSeat) != null) order.Add(r.loserSeat);
            for (int k = 1; k <= 3; k++)
            {
                int seat = (r.winnerSeat + k) % 4;
                if (!order.Contains(seat)) order.Add(seat);
            }
            float end = y;
            for (int k = 0; k < order.Count; k++)
            {
                int seat = order[k];
                var p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                int delta = seat < deltas.Length ? deltas[seat] : 0;
                bool shooter = !selfDraw && seat == r.loserSeat;
                float h = BuildSeatRow(v, p, delta, false, shooter, bankrupt && IsMe(v, p), gameEnd, y);
                end = y + h;
                y = end + ResultLayout.RowGap(false);
            }
            return end;
        }

        static bool IsMe(GameView v, PlayerView p)
        {
            return p.seat == v.mySeat || p.avatar == "me";
        }

        // ---------- Draw layout ----------

        float BuildDrawLayout(GameView v, HandResult r, bool gameEnd, bool bankrupt, int[] deltas)
        {
            string title;
            string subtitle;
            if (bankrupt)
            {
                title = "金幣歸零，牌局結束";
                subtitle = r != null ? "牌摸完了，沒有人胡牌" : "";
            }
            else if (r == null)
            {
                title = gameEnd ? "整場結束" : "本局結束";
                subtitle = "";
            }
            else
            {
                title = (gameEnd ? "整場結束·" : "") + "流局";
                subtitle = "牌摸完了，沒有人胡牌";
            }
            Label(card, "Title", title, 56, Palette.Ink, TextAnchor.MiddleCenter,
                ResultLayout.RowPadX, ResultLayout.DrawTitleY, ResultLayout.InnerW, ResultLayout.DrawTitleH, true, bankrupt ? 26 : 0);
            Label(card, "Subtitle", subtitle, 28, Palette.InkSoft, TextAnchor.MiddleCenter,
                ResultLayout.RowPadX, ResultLayout.DrawSubtitleY, ResultLayout.InnerW, ResultLayout.DrawSubtitleH);

            float y = ResultLayout.DrawRowsTop;
            float end = y;
            for (int seat = 0; seat < 4; seat++)
            {
                var p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                int delta = seat < deltas.Length ? deltas[seat] : 0;
                float h = BuildSeatRow(v, p, delta, true, false, bankrupt && IsMe(v, p), gameEnd, y);
                end = y + h;
                y = end + ResultLayout.RowGap(true);
            }
            return end;
        }

        // ---------- Stage ----------

        /// <summary>Builds the winner's stage at the fixed top; returns the y of its bottom edge (card coordinates).</summary>
        float BuildStage(GameView v, HandResult r, PlayerView winner, bool selfDraw, bool gameEnd, int winnerDelta)
        {
            List<string> sorted = TileFace.Sorted(winner.hand);
            string winning = DtoUtil.Safe(r.winningTile);
            WinSplit split = WinSplit.For(v, winner, sorted, TileFace.IsFlower(winning));

            var meldList = new List<MeldDto>();
            var meldSizes = new List<int>();
            MeldDto[] melds = DtoUtil.Safe(winner.melds);
            for (int i = 0; i < melds.Length; i++)
            {
                if (melds[i] == null || DtoUtil.Safe(melds[i].tiles).Length == 0) continue;
                meldList.Add(melds[i]);
                meldSizes.Add(melds[i].tiles.Length);
            }
            int handTiles = split.Hand.Count > 0 ? split.Hand.Count : (winner.hand != null && winner.hand.Length > 0 ? 0 : Mathf.Max(0, winner.handCount));
            bool handIsBacks = split.Hand.Count == 0 && handTiles > 0;
            string[] flowers = DtoUtil.Safe(winner.flowers);

            bool wrap = ResultLayout.StageFlowersWrap(flowers.Length, meldSizes, handTiles);
            var items = new List<TaiItem>();
            TaiItem[] rawItems = DtoUtil.Safe(r.items);
            for (int i = 0; i < rawItems.Length; i++)
            {
                if (rawItems[i] != null) items.Add(rawItems[i]);
            }
            bool dealerChip = r.dealerTai > 0;
            int cols = ResultLayout.ChipCols(items.Count, dealerChip);
            int chipRows;
            List<ResultLayout.ChipSlot> slots = ResultLayout.ChipSlots(items.Count, dealerChip, cols, out chipRows);
            float stageH = ResultLayout.StageHeight(wrap, chipRows, dealerChip);

            var stageImg = Panel(card, "Stage", Palette.ResultStage, 32, ResultLayout.RowPadX, ResultLayout.StageTop, ResultLayout.InnerW, stageH);
            UiFactory.AddShadow(stageImg, Palette.CardShadow, new Vector2(0f, -6f));
            UiFactory.CreateRing(stageImg.transform, "GoldEdge", Palette.ResultGold, 32, 4, 0f);
            RectTransform stage = stageImg.rectTransform;

            BuildStageHeader(stage, v, r, winner, selfDraw, gameEnd, winnerDelta);
            BuildStageTiles(stage, winner, split, meldList, meldSizes, flowers, handTiles, handIsBacks, wrap);

            float cTop = 16f + ResultLayout.BandAHeight + 14f + ResultLayout.BandBHeightFor(wrap) + ResultLayout.BandGapAfterB;
            BuildChips(stage, items, r.dealerTai, cols, slots, cTop);
            if (dealerChip)
            {
                float noteY = cTop + ResultLayout.ChipGridHeight(chipRows) + ResultLayout.DealerNoteGap;
                Label(stage, "DealerNote", "莊家台只加在與莊家有關的那筆支付", 22, Palette.ResultStageText, TextAnchor.MiddleLeft,
                    ResultLayout.StagePad, noteY, ResultLayout.StageInnerW, ResultLayout.DealerNoteHeight);
            }
            return ResultLayout.StageTop + stageH;
        }

        void BuildStageHeader(RectTransform stage, GameView v, HandResult r, PlayerView winner, bool selfDraw, bool gameEnd, int winnerDelta)
        {
            // Avatar with a gold ring (a slightly larger gold disc behind it).
            var ringDisc = UiFactory.CreateCircle(stage, "AvatarRing", Palette.ResultGold);
            At(ringDisc.rectTransform, 20f, 17f, 116f, 116f);
            var avatar = UiFactory.CreateAvatar(stage, winner.avatar, 108f);
            At(avatar, 24f, 21f, 108f, 108f);

            string name = string.IsNullOrEmpty(winner.name) ? "座位 " + winner.seat : winner.name;
            Label(stage, "Name", name, 46, Palette.ResultStageText, TextAnchor.MiddleLeft, 150f, 20f, 470f, 56f, true);

            string wind = TileFace.WindName(winner.seatWind) + "家";
            float windW = 26f * wind.Length + 28f;
            var windPill = Panel(stage, "WindPill", Palette.Cream, 20, 150f, 84f, windW, 40f);
            Label(windPill.transform, "Text", wind, 26, Palette.Ink, TextAnchor.MiddleCenter, 0f, 0f, windW, 40f, true);
            if (winner.seat == v.dealerSeat)
            {
                var dealer = Panel(stage, "DealerPill", Palette.DealerBadge, 20, 150f + windW + 8f, 84f, 40f, 40f);
                Label(dealer.transform, "Text", "莊", 26, Palette.Ink, TextAnchor.MiddleCenter, 0f, 0f, 40f, 40f, true);
            }

            if (selfDraw)
            {
                var pill = Panel(stage, "SelfDrawPill", Palette.ResultGold, 36, 640f, 47f, 240f, 72f);
                Label(pill.transform, "Text", "自摸", 48, Palette.Ink, TextAnchor.MiddleCenter, 0f, 0f, 240f, 72f, true);
            }
            else
            {
                var pill = Panel(stage, "ShooterPill", Palette.Coral, 36, 640f, 47f, 456f, 72f);
                PlayerView shooter = DtoUtil.Player(v, r.loserSeat);
                string shooterName = NameOf(v, r.loserSeat);
                var sa = UiFactory.CreateAvatar(pill.transform, shooter != null ? shooter.avatar : "", 48f);
                At(sa, 12f, 12f, 48f, 48f);
                Label(pill.transform, "Name", shooterName, 30, Palette.Ink, TextAnchor.MiddleLeft, 70f, 0f, 270f, 72f, true);
                Label(pill.transform, "Shot", "放槍", 36, Palette.Ink, TextAnchor.MiddleCenter, 344f, 0f, 100f, 72f, true);
            }

            BuildScoreBoard(stage, r, gameEnd, winnerDelta, winner.sessionDelta);
        }

        void BuildScoreBoard(RectTransform stage, HandResult r, bool gameEnd, int winnerDelta, int sessionDelta)
        {
            const float bx = 1136f, by = 16f, bw = 560f, bh = 134f, split = 236f;
            var board = UiFactory.CreateRect("ScoreBoard", stage);
            At(board, bx, by, bw, bh);
            Panel(board, "Right", Palette.Card, 28, 0f, 0f, bw, bh);
            Panel(board, "Left", Palette.ResultGold, 28, 0f, 0f, split, bh);
            Panel(board, "Seam", Palette.ResultGold, 1, 120f, 0f, split - 120f, bh);   // squares the left half's right corners
            UiFactory.CreateRing(board, "GoldEdge", Palette.ResultGold, 28, 4, 0f);

            // Total tai: big number plus a smaller 台 sitting at its lower right, centred as a pair in the gold half.
            string num = r.totalTai.ToString();
            float numW = 52f * num.Length;
            float startX = (split - (numW + 48f)) / 2f;
            Label(board, "TotalTai", num, 88, Palette.Ink, TextAnchor.MiddleRight, startX, 14f, numW + 8f, 106f, true);
            Label(board, "TaiUnit", "台", 40, Palette.Ink, TextAnchor.LowerLeft, startX + numW + 10f, 14f, 48f, 100f, true);

            // Amount won (the sign is part of the text), with its unit / session line underneath.
            Label(board, "Amount", Format.Signed(winnerDelta), 64, SignColor(winnerDelta),
                TextAnchor.MiddleCenter, split + 16f, 14f, 292f, 78f, true);
            if (gameEnd)
            {
                Label(board, "Sub", "本場 " + Format.Signed(sessionDelta), 24, sessionDelta > 0 ? Palette.Gain : (sessionDelta < 0 ? Palette.Loss : Palette.InkSoft),
                    TextAnchor.MiddleCenter, split + 16f, 98f, 292f, 28f);
            }
            else
            {
                Label(board, "Sub", "金幣", 24, Palette.InkSoft, TextAnchor.MiddleCenter, split + 16f, 98f, 292f, 28f);
            }
        }

        void BuildStageTiles(RectTransform stage, PlayerView winner, WinSplit split, List<MeldDto> meldList, List<int> meldSizes,
            string[] flowers, int handTiles, bool handIsBacks, bool wrap)
        {
            TileSize ts = TileSizes.Stage;
            TileSize fs = TileSizes.StageFlower;
            TileSize ws = TileSizes.StageWin;
            float baseline = ResultLayout.BaselineY;
            int flowersOnLine = wrap ? 0 : flowers.Length;

            // Row container: bottom-left pivot at the baseline so an (unexpected) uniform shrink keeps the bottoms aligned.
            float scale = ResultLayout.StageRowScale(flowersOnLine, meldSizes, handTiles);
            float availW = ResultLayout.StageHandRight - ResultLayout.StagePad;
            float contW = scale < 1f ? availW / scale : availW;
            if (scale < 1f) Debug.LogWarning("[Manjong] Result stage tiles need scale " + scale + "; check the hand data.");
            var cont = UiFactory.CreateRect("StageTiles", stage);
            UiFactory.Place(cont, new Vector2(0f, 1f), new Vector2(0f, 0f), new Vector2(ResultLayout.StagePad, -baseline), new Vector2(contW, ts.height));
            cont.localScale = new Vector3(scale, scale, 1f);

            // Left: flowers (smaller), a gap, then the melds.
            float x = 0f;
            for (int i = 0; i < flowers.Length; i++)
            {
                RectTransform t = TileView.CreateFace(wrap ? (Transform)stage : cont, flowers[i], fs);
                if (wrap) At(t, ResultLayout.StagePad + i * (fs.width + 1f), baseline + ResultLayout.StageFlowerWrapDrop, fs.width, fs.height);
                else At(t, x + i * (fs.width + 1f), ts.height - fs.height, fs.width, fs.height);
                if (split.IsFlowerWin && i == split.FlowerIndex) TileView.AddRing(t, Palette.ResultGold, fs, 3);
            }
            if (flowersOnLine > 0) x += ResultLayout.StageFlowersWidth(flowersOnLine) + ResultLayout.StageBlockGap;
            for (int m = 0; m < meldList.Count; m++)
            {
                if (m > 0) x += ResultLayout.StageMeldGap;
                float w = TileView.MeldWidth(meldList[m], ts);
                RectTransform box = TileView.CreateMeld(cont, meldList[m], ts, "");
                At(box, x, 0f, w, ts.height);
                x += w;
            }

            // Right: the hand, right-aligned so that the gap to the winning tile is exactly StageWinGap.
            float handLeft = contW - ResultLayout.StageHandWidth(handTiles);
            for (int i = 0; i < handTiles; i++)
            {
                RectTransform t = handIsBacks ? TileView.CreateBack(cont, ts) : TileView.CreateFace(cont, split.Hand[i], ts);
                At(t, handLeft + i * (ts.width + 1f), 0f, ts.width, ts.height);
            }

            // The winning tile: bigger, glowing and gold framed, at the far right. No caption.
            if (split.HasWinningTile)
            {
                float top = baseline - ws.height;
                Panel(stage, "WinGlow", Palette.ResultGlow, ws.radius + 12, ResultLayout.WinTileX - 12f, top - 12f, ws.width + 24f, ws.height + 24f);
                RectTransform t = TileView.CreateFace(stage, split.WinningTile, ws);
                At(t, ResultLayout.WinTileX, top, ws.width, ws.height);
                TileView.AddRing(t, Palette.ResultGold, ws, 5);
            }
        }

        // ---------- Tai chips ----------

        static string DealerChipText(int dealerTai)
        {
            if (dealerTai >= 3)
            {
                int k = (dealerTai - 1) / 2;
                return "莊家＋連 " + k + " 拉 " + k;
            }
            return dealerTai == 1 ? "莊家" : "莊家台";
        }

        void BuildChips(RectTransform stage, List<TaiItem> items, int dealerTai, int cols, List<ResultLayout.ChipSlot> slots, float top)
        {
            float cw = ResultLayout.ChipWidth(cols);
            int nameSize = cols > 6 ? 24 : 28;
            for (int i = 0; i < slots.Count; i++)
            {
                var s = slots[i];
                float x = ResultLayout.StagePad + s.Col * (cw + ResultLayout.ChipGap);
                float y = top + s.Row * (ResultLayout.ChipH + ResultLayout.ChipGap);
                float w = s.Span * cw + (s.Span - 1) * ResultLayout.ChipGap;
                if (s.Index == ResultLayout.SlotNotice)
                {
                    Label(stage, "NoItems", "沒有台數名目（只算底）", 26, Palette.ResultStageText, TextAnchor.MiddleLeft, x, y, w, ResultLayout.ChipH);
                }
                else if (s.Index == ResultLayout.SlotDealer)
                {
                    Chip(stage, "DealerChip", DealerChipText(dealerTai), "+" + dealerTai, Palette.DealerBadge, nameSize, x, y, w);
                }
                else
                {
                    Chip(stage, "Item" + s.Index, items[s.Index].name, items[s.Index].tai.ToString(), Palette.Cream, nameSize, x, y, w);
                }
            }
        }

        /// <summary>Name on the left, gold tai badge (digits only, the badge itself means 台) on the right.</summary>
        static void Chip(Transform parent, string name, string text, string badge, Color bg, int nameSize, float x, float y, float w)
        {
            var chip = Panel(parent, name, bg, 14, x, y, w, ResultLayout.ChipH);
            Label(chip.transform, "Text", text, nameSize, Palette.Ink, TextAnchor.MiddleLeft, 14f, 0f, w - ResultLayout.ChipBadgeW - 20f, ResultLayout.ChipH, false, 18);
            float bx = w - ResultLayout.ChipBadgeW;
            Panel(chip.transform, "Badge", Palette.ResultGold, 14, bx, 0f, ResultLayout.ChipBadgeW, ResultLayout.ChipH);
            Panel(chip.transform, "BadgeSquare", Palette.ResultGold, 1, bx, 0f, 24f, ResultLayout.ChipH);   // squares the badge's left corners
            Label(chip.transform, "BadgeText", badge, 30, Palette.Ink, TextAnchor.MiddleCenter, bx, 0f, ResultLayout.ChipBadgeW, ResultLayout.ChipH, true, 16);
        }

        // ---------- Seat rows (compact under the stage, roomy for an exhaustive draw) ----------

        float BuildSeatRow(GameView v, PlayerView p, int delta, bool roomy, bool shooter, bool bankruptMe, bool gameEnd, float top)
        {
            List<string> sorted = TileFace.Sorted(p.hand);
            WinSplit split = WinSplit.For(v, p, sorted, false);   // not the winner here (or exhaustive): hand unchanged

            MeldDto[] melds = DtoUtil.Safe(p.melds);
            var meldList = new List<MeldDto>();
            var meldSizes = new List<int>();
            for (int i = 0; i < melds.Length; i++)
            {
                if (melds[i] == null || DtoUtil.Safe(melds[i].tiles).Length == 0) continue;
                meldList.Add(melds[i]);
                meldSizes.Add(melds[i].tiles.Length);
            }
            int handTiles = split.Hand.Count > 0 ? split.Hand.Count : (p.hand != null && p.hand.Length > 0 ? 0 : Mathf.Max(0, p.handCount));
            bool handIsBacks = split.Hand.Count == 0 && handTiles > 0;
            string[] flowers = DtoUtil.Safe(p.flowers);

            bool wrap = ResultLayout.RowFlowersWrap(roomy, flowers.Length, meldSizes, handTiles);
            float height = ResultLayout.RowHeightFor(roomy, wrap);
            float rowW = ResultLayout.RowWidth;

            var rowImg = Panel(card, "Row" + p.seat, Palette.Cream, 20, ResultLayout.RowPadX, top, rowW, height);
            RectTransform row = rowImg.rectTransform;
            if (shooter) UiFactory.CreateRing(row, "ShooterRing", Palette.ResultShooterRing, 20, 3, 0f);
            else if (bankruptMe) UiFactory.CreateRing(row, "BankruptRing", Palette.Loss, 20, 3, 0f);

            // ----- Who -----
            float av = roomy ? 64f : 52f;
            var avatar = UiFactory.CreateAvatar(row, p.avatar, av);
            At(avatar, 16f, ResultLayout.RowHeight(roomy) / 2f - av / 2f, av, av);

            float infoX = roomy ? 88f : 78f;
            float infoW = roomy ? 170f : 180f;
            string name = string.IsNullOrEmpty(p.name) ? "座位 " + p.seat : p.name;
            Label(row, "Name", name, roomy ? 30 : 26, Palette.Ink, TextAnchor.MiddleLeft, infoX, roomy ? 14f : 8f, infoW, roomy ? 38f : 34f, true);
            BuildTagLine(row, v, p, shooter, bankruptMe, infoX, roomy ? 56f : 42f);

            Label(row, "Delta", Format.Signed(delta), 34, SignColor(delta), TextAnchor.MiddleRight, 262f, roomy ? 14f : 6f, 170f, 40f, true);
            if (gameEnd)
            {
                Label(row, "Session", "本場 " + Format.Signed(p.sessionDelta), 22, SignColor(p.sessionDelta), TextAnchor.MiddleRight, 262f, roomy ? 54f : 46f, 170f, 26f);
            }
            Panel(row, "Divider", Palette.ResultDivider, 1, 444f, 10f, 2f, ResultLayout.RowHeight(roomy) - 20f);

            // ----- Tiles: flowers + melds left, hand right-aligned -----
            TileSize size = roomy ? TileSizes.Small : TileSizes.Mini;
            TileSize fs = TileSizes.Mini;
            float tilesTop = ResultLayout.RowTilesTop(roomy);
            float x = ResultLayout.RowTilesX;
            for (int i = 0; i < flowers.Length; i++)
            {
                RectTransform t = TileView.CreateFace(row, flowers[i], fs);
                float fTop = wrap ? tilesTop + size.height + ResultLayout.RowFlowerLineGap : tilesTop + size.height - fs.height;
                At(t, x + i * (fs.width + 1f), fTop, fs.width, fs.height);
            }
            if (flowers.Length > 0 && !wrap) x += ResultLayout.RowFlowersWidth(flowers.Length) + ResultLayout.RowBlockGap;
            for (int m = 0; m < meldList.Count; m++)
            {
                if (m > 0) x += ResultLayout.RowMeldGap(roomy);
                float w = TileView.MeldWidth(meldList[m], size);
                RectTransform box = TileView.CreateMeld(row, meldList[m], size, "");
                At(box, x, tilesTop, w, size.height);
                x += w;
            }
            float handLeft = ResultLayout.RowTilesRight - ResultLayout.RowHandWidth(roomy, handTiles);
            for (int i = 0; i < handTiles; i++)
            {
                RectTransform t = handIsBacks ? TileView.CreateBack(row, size) : TileView.CreateFace(row, split.Hand[i], size);
                At(t, handLeft + i * (size.width + 1f), tilesTop, size.width, size.height);
            }
            return height;
        }

        /// <summary>Seat wind, dealer dot, shooter pill and the coins-gone pill, in one line that must fit the name column.</summary>
        static void BuildTagLine(RectTransform row, GameView v, PlayerView p, bool shooter, bool bankruptMe, float x, float y)
        {
            string wind = TileFace.WindName(p.seatWind) + "家";
            float windW = 20f * wind.Length + 4f;
            bool dealer = p.seat == v.dealerSeat;
            const float gap = 4f;
            // Full text "金幣歸零" (88 wide) unless the whole line would pass 200 (dealer + shooter + coins-gone).
            float chain = windW + (dealer ? 24f + gap : 0f) + (shooter ? 64f + gap : 0f);
            string bankruptText = chain + gap + 88f > 200f ? "歸零" : "金幣歸零";
            float bankruptW = 22f * bankruptText.Length + (bankruptText.Length == 2 ? 4f : 0f);

            Label(row, "Wind", wind, 20, Palette.InkSoft, TextAnchor.MiddleLeft, x, y, windW, 26f);
            float cx = x + windW + gap;
            if (dealer)
            {
                var d = Panel(row, "DealerDot", Palette.DealerBadge, 12, cx, y + 1f, 24f, 24f);
                Label(d.transform, "Text", "莊", 20, Palette.Ink, TextAnchor.MiddleCenter, 0f, 0f, 24f, 24f);
                cx += 24f + gap;
            }
            if (shooter)
            {
                var s = Panel(row, "ShooterPill", Palette.Coral, 13, cx, y, 64f, 26f);
                Label(s.transform, "Text", "放槍", 20, Palette.Ink, TextAnchor.MiddleCenter, 0f, 0f, 64f, 26f, true);
                cx += 64f + gap;
            }
            if (bankruptMe)
            {
                var b = Panel(row, "BankruptPill", Palette.Pink, 13, cx, y, bankruptW, 26f);
                Label(b.transform, "Text", bankruptText, 20, Palette.Ink, TextAnchor.MiddleCenter, 0f, 0f, bankruptW, 26f, true);
            }
        }

        // ---------- Buttons ----------

        void BuildButtons(bool gameEnd, bool bankrupt)
        {
            var line = Panel(card, "ButtonsLine", Palette.ResultDivider, 1, 0f, 0f, ResultLayout.InnerW, 2f);
            UiFactory.Place(line.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(ResultLayout.RowPadX, ResultLayout.ButtonsZone - 2f), new Vector2(ResultLayout.InnerW, 2f));

            nextButton = null;
            if (gameEnd)
            {
                string label = bankrupt ? "回大廳領救濟金" : "回大廳";
                var lobbyBtn = UiFactory.CreateButton(card, "LobbyButton", label, Palette.Butter, 38, OnLobby);
                UiFactory.Place((RectTransform)lobbyBtn.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 24f), new Vector2(bankrupt ? 440f : 360f, 88f));
            }
            else
            {
                var nextBtn = UiFactory.CreateButton(card, "NextButton", "下一局", Palette.Pink, 38, OnNext);
                nextButton = nextBtn;
                UiFactory.Place((RectTransform)nextBtn.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(170f, 24f), new Vector2(320f, 88f));
                var leaveBtn = UiFactory.CreateButton(card, "LeaveButton", "先回大廳", Palette.Gray, 34, OnLobby);
                UiFactory.Place((RectTransform)leaveBtn.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(-170f, 24f), new Vector2(280f, 88f));
            }
        }

        /// <summary>"下一局" was sent: show it as waiting and block a second press until the next render.</summary>
        public void SetNextPending()
        {
            if (nextButton == null) return;
            UiFactory.ButtonLabel(nextButton).text = "等待中…";
            UiFactory.SetInteractable(nextButton, false);
        }

        void OnNext()
        {
            if (onNext != null) onNext();
        }

        void OnLobby()
        {
            if (onLobby != null) onLobby();
        }
    }
}

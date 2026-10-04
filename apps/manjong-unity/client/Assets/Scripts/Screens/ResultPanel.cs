using System;
using System.Collections.Generic;
using Manjong.Net;
using Manjong.UI;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.Screens
{
    /// <summary>
    /// Hand / game result overlay.
    /// Top: title, subtitle and (for a win) a separate tai block (items, total, dealer tai).
    /// Then one row per seat, the winner first and highlighted. Each row has clearly separated blocks, left to right:
    ///   1. avatar, name, seat wind / tags, this hand's delta (large)
    ///   2. 手牌: concealed tiles, sorted, tight
    ///   3. melds: one group per meld with a caption (吃 / 碰 / 槓 / 暗槓), gaps between groups
    ///   4. the winning tile on its own (winner only) with an outline and a 胡 / 自摸 caption
    ///   5. 花牌: one size smaller, at the end of the row; on a second line if the row would overflow
    /// Blocks are separated by at least one tile width. Content is rebuilt on every Show().
    /// </summary>
    public class ResultPanel
    {
        public const float CardWidth = 1860f;
        public const float CardHeight = 1040f;
        public const float RowPadX = 30f;              // card edge -> row
        public const float InfoBlockW = 280f;          // block 1
        public const float TilesStartX = 300f;         // row-local x where block 2 starts
        public const float BlockGap = 42f;             // = one Small tile width
        public const float MeldGap = 24f;
        public const float RowPadRight = 16f;
        public const float CaptionH = 22f;
        public const float RowTopPad = 8f;
        public const float RowBottomPad = 10f;
        public const float RowGap = 8f;
        public const float FlowerLineGap = 6f;
        const float ButtonsReserve = 124f;

        static TileSize HandSize { get { return TileSizes.Small; } }
        static TileSize FlowerSize { get { return TileSizes.Mini; } }

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
            UiFactory.Place(cardImg.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(CardWidth, CardHeight));
            UiFactory.AddShadow(cardImg, Palette.CardShadow, new Vector2(0f, -8f));
            card = cardImg.rectTransform;
            root.SetActive(false);
        }

        public void Hide()
        {
            if (root != null) root.SetActive(false);
        }

        static void TopLeft(RectTransform rt, float x, float y, float w, float h)
        {
            UiFactory.Place(rt, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -y), new Vector2(w, h));
        }

        static string NameOf(GameView v, int seat)
        {
            var p = DtoUtil.Player(v, seat);
            return p != null && !string.IsNullOrEmpty(p.name) ? p.name : "座位 " + seat;
        }

        public void Show(GameView v, Action next, Action lobby)
        {
            onNext = next;
            onLobby = lobby;
            UiFactory.DestroyChildren(card);
            root.SetActive(true);
            root.transform.SetAsLastSibling();

            bool gameEnd = v.phase == "game_end";
            HandResult r = v.hasResult ? v.result : null;
            bool isWin = r != null && r.kind == "win" && r.winnerSeat >= 0;
            float innerW = CardWidth - 2f * RowPadX;

            // ----- Title -----
            string title;
            string subtitle;
            if (r == null)
            {
                title = gameEnd ? "整場結束" : "本局結束";
                subtitle = "";
            }
            else if (isWin)
            {
                title = NameOf(v, r.winnerSeat) + " 胡牌！";
                string tileName = TileFace.Name(DtoUtil.Safe(r.winningTile));
                string how = r.selfDraw || r.loserSeat < 0 ? "自摸" : NameOf(v, r.loserSeat) + " 放槍";
                subtitle = tileName.Length > 0 ? how + "·胡 " + tileName : how;
            }
            else
            {
                title = "流局";
                subtitle = "牌摸完了，沒有人胡牌";
            }
            bool bankrupt = gameEnd && v.endReason == "bankrupt";
            if (bankrupt)
            {
                // Coins hit 0: the game ended immediately. Keep this hand's outcome as the subtitle.
                subtitle = r != null ? title + (subtitle.Length > 0 ? "·" + subtitle : "") : "";
                title = "金幣歸零，牌局結束";
            }
            else if (gameEnd && r != null)
            {
                title = "整場結束·" + title;
            }

            var titleText = UiFactory.CreateLabel(card, "Title", title, 52, Palette.Ink, TextAnchor.MiddleCenter);
            titleText.fontStyle = FontStyle.Bold;
            TopLeft(titleText.rectTransform, RowPadX, 18f, innerW, 64f);
            var subText = UiFactory.CreateLabel(card, "Subtitle", subtitle, 30, Palette.InkSoft, TextAnchor.MiddleCenter);
            TopLeft(subText.rectTransform, RowPadX, 84f, innerW, 40f);

            float y = 132f;

            // ----- Tai block (separate from the tiles) -----
            if (isWin) y = BuildTaiBlock(r, y, innerW) + 12f;

            // ----- Player rows: winner first, then the others in seat order -----
            int[] deltas = r != null ? DtoUtil.Safe(r.deltas) : new int[0];
            var order = new List<int>();
            if (isWin) order.Add(r.winnerSeat);
            for (int seat = 0; seat < 4; seat++)
            {
                if (!order.Contains(seat)) order.Add(seat);
            }
            for (int k = 0; k < order.Count; k++)
            {
                int seat = order[k];
                var p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                int delta = seat < deltas.Length ? deltas[seat] : 0;
                bool isWinner = isWin && seat == r.winnerSeat;
                bool isLoser = isWin && !r.selfDraw && seat == r.loserSeat;
                y += BuildPlayerRow(v, p, delta, isWinner, isLoser, gameEnd, y, innerW) + RowGap;
            }
            if (y > CardHeight - ButtonsReserve)
            {
                Debug.LogWarning("[Manjong] Result rows reach y=" + y + ", into the button area (" + (CardHeight - ButtonsReserve) + ").");
            }

            // ----- Buttons -----
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

        /// <summary>Total / dealer tai line plus item chips (6 per row). Returns the y below the block.</summary>
        float BuildTaiBlock(HandResult r, float top, float innerW)
        {
            const int cols = 6;
            const float chipH = 40f;
            const float pad = 12f;
            TaiItem[] items = DtoUtil.Safe(r.items);
            int rows = Mathf.Max(1, (items.Length + cols - 1) / cols);
            float h = pad + 40f + 6f + rows * (chipH + 6f) + pad - 6f;

            var box = UiFactory.CreatePanel(card, "TaiBlock", Palette.Cream, 20);
            TopLeft(box.rectTransform, RowPadX, top, innerW, h);
            UiFactory.CreateRing(box.transform, "Edge", Palette.Butter, 20, 3, 0f);

            string totals = "總台數 " + r.totalTai + " 台";
            if (r.dealerTai > 0) totals += "  ｜  莊家台 " + r.dealerTai + " 台（只算在與莊家有關的支付）";
            var totalText = UiFactory.CreateLabel(box.transform, "Totals", totals, 30, Palette.Ink, TextAnchor.MiddleLeft);
            totalText.fontStyle = FontStyle.Bold;
            TopLeft(totalText.rectTransform, 20f, pad, innerW - 40f, 40f);

            float chipW = (innerW - 40f - (cols - 1) * 8f) / cols;
            if (items.Length == 0)
            {
                // A win can score zero tai (base payment only); say so instead of leaving a blank block.
                var none = UiFactory.CreateLabel(box.transform, "NoItems", "沒有台數名目（只算底）", 24, Palette.InkSoft, TextAnchor.MiddleLeft);
                TopLeft(none.rectTransform, 20f, pad + 46f, 700f, chipH);
            }
            for (int i = 0; i < items.Length; i++)
            {
                if (items[i] == null) continue;
                var chip = UiFactory.CreatePanel(box.transform, "Item" + i, Palette.Butter, 14);
                TopLeft(chip.rectTransform, 20f + (i % cols) * (chipW + 8f), pad + 46f + (i / cols) * (chipH + 6f), chipW, chipH);
                var t = UiFactory.CreateLabel(chip.transform, "Text", items[i].name + "  " + items[i].tai + " 台", 24, Palette.Ink, TextAnchor.MiddleCenter);
                UiFactory.Stretch(t.rectTransform, 8f, 2f, 8f, 2f);
            }
            return top + h;
        }

        // ---------- Row layout (pure geometry, shared with the drawing code) ----------

        /// <summary>Width of the main line's tile blocks (hand, melds, winning tile), starting at TilesStartX.</summary>
        public static float MainLineWidth(int handTiles, IList<int> meldSizes, bool hasWinningTile)
        {
            float step = HandSize.width + 1f;
            float x = 0f;
            bool any = false;
            if (handTiles > 0)
            {
                x += handTiles * step - 1f;
                any = true;
            }
            for (int i = 0; i < meldSizes.Count; i++)
            {
                x += any ? (i == 0 ? BlockGap : MeldGap) : 0f;
                x += meldSizes[i] * step - 1f;
                any = true;
            }
            if (hasWinningTile)
            {
                x += any ? BlockGap : 0f;
                x += HandSize.width;
            }
            return x;
        }

        public static float FlowersWidth(int flowers)
        {
            return flowers <= 0 ? 0f : flowers * (FlowerSize.width + 1f) - 1f;
        }

        public static float RowHeight(bool flowersOnSecondLine)
        {
            float h = RowTopPad + CaptionH + HandSize.height + RowBottomPad;
            if (flowersOnSecondLine) h += FlowerLineGap + CaptionH + FlowerSize.height;
            return h;
        }

        /// <summary>Flowers stay on the main line when it still fits inside the row; otherwise they wrap.</summary>
        public static bool FlowersWrap(float rowWidth, float mainLine, int flowers)
        {
            if (flowers <= 0) return false;
            float end = TilesStartX + mainLine + (mainLine > 0f ? BlockGap : 0f) + FlowersWidth(flowers) + RowPadRight;
            return end > rowWidth;
        }

        // ---------- Row drawing ----------

        float BuildPlayerRow(GameView v, PlayerView p, int delta, bool isWinner, bool isLoser, bool gameEnd, float top, float rowW)
        {
            List<string> sorted = TileFace.Sorted(p.hand);
            string winning = v.hasResult && v.result != null ? DtoUtil.Safe(v.result.winningTile) : "";
            WinSplit split = WinSplit.For(v, p, sorted, TileFace.IsFlower(winning));
            bool winTileApart = split.HasWinningTile && !split.IsFlowerWin;

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
            int flowerCount = flowers.Length + (split.IsFlowerWin && split.FlowerIndex < 0 ? 1 : 0);

            float mainLine = MainLineWidth(handTiles, meldSizes, winTileApart);
            bool wrap = FlowersWrap(rowW, mainLine, flowerCount);
            float height = RowHeight(wrap);

            var row = UiFactory.CreatePanel(card, "Row" + p.seat, isWinner ? Palette.RowHighlight : Palette.Cream, 20);
            TopLeft(row.rectTransform, RowPadX, top, rowW, height);
            if (isWinner) UiFactory.CreateRing(row.transform, "WinRing", Palette.Coral, 20, 3, 0f);
            RectTransform rt = row.rectTransform;

            // ----- Block 1: who and how much -----
            var avatar = UiFactory.CreateAvatar(rt, p.avatar, 56f);
            UiFactory.Place(avatar, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(16f, -20f), new Vector2(56f, 56f));

            string tag = TileFace.WindName(p.seatWind) + "家";
            if (p.seat == v.dealerSeat) tag += "·莊";
            if (isWinner) tag += split.SelfDraw ? "·自摸" : "·胡牌";
            if (isLoser) tag += "·放槍";

            var name = UiFactory.CreateLabel(rt, "Name", p.name, 26, Palette.Ink, TextAnchor.MiddleLeft);
            name.fontStyle = FontStyle.Bold;
            TopLeft(name.rectTransform, 84f, 6f, InfoBlockW - 90f, 30f);
            var tagText = UiFactory.CreateLabel(rt, "Tag", tag, 20, isWinner || isLoser ? Palette.Ink : Palette.InkSoft, TextAnchor.MiddleLeft);
            if (isWinner || isLoser) tagText.fontStyle = FontStyle.Bold;
            TopLeft(tagText.rectTransform, 84f, 36f, InfoBlockW - 90f, 24f);

            var deltaText = UiFactory.CreateLabel(rt, "Delta", "", 30, Palette.Ink, TextAnchor.MiddleLeft);
            deltaText.fontStyle = FontStyle.Bold;
            TopLeft(deltaText.rectTransform, 84f, 60f, InfoBlockW - 90f, 34f);
            if (gameEnd)
            {
                deltaText.text = "本局 " + Format.Signed(delta) + "·本場 " + Format.Signed(p.sessionDelta);
                deltaText.color = p.sessionDelta > 0 ? Palette.Gain : (p.sessionDelta < 0 ? Palette.Loss : Palette.Ink);
            }
            else
            {
                deltaText.text = Format.Signed(delta) + " 金幣";
                deltaText.color = delta > 0 ? Palette.Gain : (delta < 0 ? Palette.Loss : Palette.Ink);
            }

            var divider = UiFactory.CreatePanel(rt, "Divider", new Color(0.42f, 0.30f, 0.24f, 0.25f), 1);
            TopLeft(divider.rectTransform, InfoBlockW + 8f, 10f, 2f, height - 20f);

            // ----- Blocks 2-4 on the main line -----
            TileSize size = HandSize;
            float step = size.width + 1f;
            float tilesTop = RowTopPad + CaptionH;
            float x = TilesStartX;
            bool any = false;

            if (handTiles > 0)
            {
                Caption(rt, "手牌", x, RowTopPad, handTiles * step - 1f, Palette.InkSoft);
                for (int i = 0; i < handTiles; i++)
                {
                    RectTransform t = handIsBacks ? TileView.CreateBack(rt, size) : TileView.CreateFace(rt, split.Hand[i], size);
                    TopLeft(t, x + i * step, tilesTop, size.width, size.height);
                }
                x += handTiles * step - 1f;
                any = true;
            }

            for (int m = 0; m < meldList.Count; m++)
            {
                x += any ? (m == 0 ? BlockGap : MeldGap) : 0f;
                float w = TileView.MeldWidth(meldList[m], size);
                Caption(rt, MeldCaption(meldList[m].type), x, RowTopPad, w, Palette.Ink);
                RectTransform box = TileView.CreateMeld(rt, meldList[m], size, "");
                TopLeft(box, x, tilesTop, w, size.height);
                x += w;
                any = true;
            }

            if (winTileApart)
            {
                x += any ? BlockGap : 0f;
                Caption(rt, split.SelfDraw ? "自摸" : "胡", x - 10f, RowTopPad, size.width + 20f, Palette.Loss);
                RectTransform t = TileView.CreateFace(rt, split.WinningTile, size);
                TopLeft(t, x, tilesTop, size.width, size.height);
                TileView.AddRing(t, Palette.LastDiscardRing, size, 4);
                x += size.width;
                any = true;
            }

            // ----- Block 5: flowers (end of the main line, or a second line when it would overflow) -----
            if (flowerCount > 0)
            {
                TileSize fs = FlowerSize;
                float fx = wrap ? TilesStartX : x + (any ? BlockGap : 0f);
                float captionTop = wrap ? RowTopPad + CaptionH + HandSize.height + FlowerLineGap : RowTopPad;
                float fTop = captionTop + CaptionH + (wrap ? 0f : HandSize.height - fs.height); // bottom-aligned with the main tiles
                string caption = "花牌";
                if (split.IsFlowerWin) caption += split.SelfDraw ? "（自摸 " : "（胡 ";
                if (split.IsFlowerWin) caption += TileFace.Name(split.WinningTile) + "）";
                Caption(rt, caption, fx, captionTop, Mathf.Max(FlowersWidth(flowerCount), 120f), split.IsFlowerWin ? Palette.Loss : Palette.InkSoft);
                for (int i = 0; i < flowerCount; i++)
                {
                    string code = i < flowers.Length ? flowers[i] : split.WinningTile;
                    RectTransform t = TileView.CreateFace(rt, code, fs);
                    TopLeft(t, fx + i * (fs.width + 1f), fTop, fs.width, fs.height);
                    bool isWinFlower = split.IsFlowerWin && (i == split.FlowerIndex || i >= flowers.Length);
                    if (isWinFlower) TileView.AddRing(t, Palette.LastDiscardRing, fs, 3);
                }
            }
            return height;
        }

        static string MeldCaption(string type)
        {
            switch (type)
            {
                case "chi": return "吃";
                case "pon": return "碰";
                case "ankan": return "暗槓";
                default: return "槓"; // kan, kakan
            }
        }

        static void Caption(RectTransform row, string text, float x, float y, float w, Color color)
        {
            var t = UiFactory.CreateLabel(row, "Caption", text, 18, color, TextAnchor.MiddleLeft);
            t.fontStyle = FontStyle.Bold;
            TopLeft(t.rectTransform, x, y, Mathf.Max(w, 40f), CaptionH);
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

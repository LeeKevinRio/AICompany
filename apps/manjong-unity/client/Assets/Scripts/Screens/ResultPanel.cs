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
    /// Then one row per seat, the winner first and highlighted. No captions: the layout tells the tile groups apart.
    /// Left block: avatar, name, seat wind / tags, this hand's delta (large).
    /// Tiles, left to right (all one Small tile tall except the flowers, which are one size smaller):
    ///   flowers, then the melds (a clear gap between groups; a chi has the claimed tile in the middle, a concealed
    ///   kong shows its two outer tiles face down, an open / added kong shows four face-up tiles);
    ///   ... then, right-aligned, the concealed hand, and after a wide gap the winning tile with an outline
    ///   (winner only; every row keeps that slot free so all hands end at the same x).
    /// A flower win marks the winning flower inside the flower group instead. Content is rebuilt on every Show().
    /// The card is narrower than 1920 on purpose: the canvas scales with match 0.5, so a 16:10 screen is only about
    /// 1821 units wide.
    /// </summary>
    public class ResultPanel
    {
        public const float CardWidth = 1780f;
        public const float CardHeight = 1040f;
        public const float RowPadX = 30f;              // card edge -> row
        public const float InfoBlockW = 280f;          // name / delta block
        public const float TilesStartX = 300f;         // row-local x where the tile area starts
        public const float BlockGap = 48f;             // flowers -> melds, hand -> winning tile (wider than a tile)
        public const float MeldGap = 36f;              // between melds
        public const float RowPadRight = 16f;
        public const float RowMinHeight = 96f;         // fits the name block
        public const float TilesTop = 20f;             // (RowMinHeight - Small.height) / 2
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
                y += BuildPlayerRow(v, p, delta, isWinner, isLoser, gameEnd, isWin, y, innerW) + RowGap;
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

        static float TileStep { get { return HandSize.width + 1f; } }

        public static float HandWidth(int handTiles)
        {
            return handTiles <= 0 ? 0f : handTiles * TileStep - 1f;
        }

        public static float FlowersWidth(int flowers)
        {
            return flowers <= 0 ? 0f : flowers * (FlowerSize.width + 1f) - 1f;
        }

        public static float MeldsWidth(IList<int> meldSizes)
        {
            float w = 0f;
            for (int i = 0; i < meldSizes.Count; i++)
            {
                w += (i > 0 ? MeldGap : 0f) + meldSizes[i] * TileStep - 1f;
            }
            return w;
        }

        /// <summary>Left block: flowers, a gap, then the melds. flowers = 0 when they wrap to a second line.</summary>
        public static float LeftWidth(int flowers, IList<int> meldSizes)
        {
            float w = FlowersWidth(flowers);
            if (meldSizes.Count > 0) w += (flowers > 0 ? BlockGap : 0f) + MeldsWidth(meldSizes);
            return w;
        }

        /// <summary>Right block: the hand plus (when a win exists on the table) the reserved winning-tile slot.</summary>
        public static float RightWidth(int handTiles, bool reserveWinSlot)
        {
            return HandWidth(handTiles) + (reserveWinSlot ? BlockGap + HandSize.width : 0f);
        }

        /// <summary>Flowers stay on the main line only while the left and right blocks still keep a block gap apart.</summary>
        public static bool FlowersWrap(float rowWidth, int flowers, IList<int> meldSizes, int handTiles, bool reserveWinSlot)
        {
            if (flowers <= 0) return false;
            float avail = rowWidth - RowPadRight - TilesStartX;
            return LeftWidth(flowers, meldSizes) + BlockGap + RightWidth(handTiles, reserveWinSlot) > avail;
        }

        public static float RowHeight(bool flowersOnSecondLine)
        {
            if (!flowersOnSecondLine) return RowMinHeight;
            return Mathf.Max(RowMinHeight, TilesTop + HandSize.height + FlowerLineGap + FlowerSize.height + RowBottomPad);
        }

        // ---------- Row drawing ----------

        float BuildPlayerRow(GameView v, PlayerView p, int delta, bool isWinner, bool isLoser, bool gameEnd, bool winOnTable, float top, float rowW)
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

            bool wrap = FlowersWrap(rowW, flowerCount, meldSizes, handTiles, winOnTable);
            float height = RowHeight(wrap);

            var row = UiFactory.CreatePanel(card, "Row" + p.seat, isWinner ? Palette.RowHighlight : Palette.Cream, 20);
            TopLeft(row.rectTransform, RowPadX, top, rowW, height);
            if (isWinner) UiFactory.CreateRing(row.transform, "WinRing", Palette.Coral, 20, 3, 0f);
            RectTransform rt = row.rectTransform;

            // ----- Who and how much -----
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

            // ----- Left: flowers (one size smaller), then the melds -----
            TileSize size = HandSize;
            TileSize fs = FlowerSize;
            float x = TilesStartX;
            if (flowerCount > 0)
            {
                // Bottom-aligned with the main tiles, or on a second line when the row would be too tight.
                float fTop = wrap ? TilesTop + size.height + FlowerLineGap : TilesTop + size.height - fs.height;
                for (int i = 0; i < flowerCount; i++)
                {
                    string code = i < flowers.Length ? flowers[i] : split.WinningTile;
                    RectTransform t = TileView.CreateFace(rt, code, fs);
                    TopLeft(t, x + i * (fs.width + 1f), fTop, fs.width, fs.height);
                    bool isWinFlower = split.IsFlowerWin && (i == split.FlowerIndex || i >= flowers.Length);
                    if (isWinFlower) TileView.AddRing(t, Palette.LastDiscardRing, fs, 3);
                }
                if (!wrap) x += FlowersWidth(flowerCount) + BlockGap;
            }

            for (int m = 0; m < meldList.Count; m++)
            {
                if (m > 0) x += MeldGap;
                float w = TileView.MeldWidth(meldList[m], size);
                RectTransform box = TileView.CreateMeld(rt, meldList[m], size, "");
                TopLeft(box, x, TilesTop, w, size.height);
                x += w;
            }

            // ----- Right: the hand (right-aligned), then a wide gap and the winning tile -----
            float rightEdge = rowW - RowPadRight;
            float winX = rightEdge - size.width;
            float handRight = winOnTable ? winX - BlockGap : rightEdge;
            float handLeft = handRight - HandWidth(handTiles);
            for (int i = 0; i < handTiles; i++)
            {
                RectTransform t = handIsBacks ? TileView.CreateBack(rt, size) : TileView.CreateFace(rt, split.Hand[i], size);
                TopLeft(t, handLeft + i * TileStep, TilesTop, size.width, size.height);
            }

            if (winTileApart)
            {
                RectTransform t = TileView.CreateFace(rt, split.WinningTile, size);
                TopLeft(t, winX, TilesTop, size.width, size.height);
                TileView.AddRing(t, Palette.LastDiscardRing, size, 4);
            }
            return height;
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

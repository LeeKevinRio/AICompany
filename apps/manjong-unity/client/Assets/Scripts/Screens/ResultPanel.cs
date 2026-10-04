using System;
using System.Collections.Generic;
using Manjong.Net;
using Manjong.UI;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.Screens
{
    /// <summary>
    /// Hand / game result overlay: winner, loser or self-draw or exhaustive draw, tai items, totals,
    /// per-seat deltas and the four revealed hands. Content is rebuilt on every Show().
    /// </summary>
    public class ResultPanel
    {
        const float CardWidth = 1500f;
        const float CardHeight = 950f;

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

            var titleText = UiFactory.CreateLabel(card, "Title", title, 56, Palette.Ink, TextAnchor.MiddleCenter);
            titleText.fontStyle = FontStyle.Bold;
            TopLeft(titleText.rectTransform, 40f, 26f, CardWidth - 80f, 72f);

            var subText = UiFactory.CreateLabel(card, "Subtitle", subtitle, 32, Palette.InkSoft, TextAnchor.MiddleCenter);
            TopLeft(subText.rectTransform, 40f, 98f, CardWidth - 80f, 46f);

            // ----- Tai items -----
            float y = 160f;
            if (isWin)
            {
                var header = UiFactory.CreateLabel(card, "TaiHeader", "台數名目", 30, Palette.Ink, TextAnchor.MiddleLeft);
                header.fontStyle = FontStyle.Bold;
                TopLeft(header.rectTransform, 50f, y, 400f, 40f);
                y += 46f;

                TaiItem[] items = DtoUtil.Safe(r.items);
                if (items.Length == 0)
                {
                    // A win can score zero tai (base payment only); say so instead of leaving a blank block.
                    var none = UiFactory.CreateLabel(card, "NoItems", "沒有台數名目（只算底）", 26, Palette.InkSoft, TextAnchor.MiddleLeft);
                    TopLeft(none.rectTransform, 50f, y, 700f, 42f);
                }
                const int cols = 4;
                const float colW = 350f;
                const float rowH = 42f;
                for (int i = 0; i < items.Length; i++)
                {
                    if (items[i] == null) continue;
                    int c = i % cols;
                    int row = i / cols;
                    var chip = UiFactory.CreatePanel(card, "Item" + i, Palette.Butter, 14);
                    TopLeft(chip.rectTransform, 50f + c * colW, y + row * (rowH + 6f), colW - 16f, rowH);
                    var t = UiFactory.CreateLabel(chip.transform, "Text", items[i].name + "  " + items[i].tai + " 台", 26, Palette.Ink, TextAnchor.MiddleCenter);
                    UiFactory.Stretch(t.rectTransform, 10f, 2f, 10f, 2f);
                }
                int rows = Mathf.Max(1, (items.Length + cols - 1) / cols);
                y += rows * (rowH + 6f) + 8f;

                string totals = "總台數 " + r.totalTai + " 台";
                if (r.dealerTai > 0) totals += "  ｜  莊家台 " + r.dealerTai + " 台（只算在與莊家有關的支付）";
                var totalText = UiFactory.CreateLabel(card, "Totals", totals, 32, Palette.Ink, TextAnchor.MiddleLeft);
                totalText.fontStyle = FontStyle.Bold;
                TopLeft(totalText.rectTransform, 50f, y, CardWidth - 100f, 46f);
                y += 60f;
            }
            else
            {
                y += 20f;
            }

            // ----- Player rows -----
            int[] deltas = r != null ? DtoUtil.Safe(r.deltas) : new int[0];
            const float playerRowH = 92f;
            float rowsTop = Mathf.Max(y, CardHeight - 130f - 4f * (playerRowH + 8f));
            for (int seat = 0; seat < 4; seat++)
            {
                var p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                int delta = seat < deltas.Length ? deltas[seat] : 0;
                bool isWinner = isWin && seat == r.winnerSeat;
                bool isLoser = isWin && !r.selfDraw && seat == r.loserSeat;
                BuildPlayerRow(v, p, delta, isWinner, isLoser, gameEnd, rowsTop + seat * (playerRowH + 8f), playerRowH);
            }

            // ----- Buttons -----
            nextButton = null;
            if (gameEnd)
            {
                string label = bankrupt ? "回大廳領救濟金" : "回大廳";
                var lobbyBtn = UiFactory.CreateButton(card, "LobbyButton", label, Palette.Butter, 38, OnLobby);
                UiFactory.Place((RectTransform)lobbyBtn.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 28f), new Vector2(bankrupt ? 440f : 360f, 88f));
            }
            else
            {
                var nextBtn = UiFactory.CreateButton(card, "NextButton", "下一局", Palette.Pink, 38, OnNext);
                nextButton = nextBtn;
                UiFactory.Place((RectTransform)nextBtn.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(170f, 28f), new Vector2(320f, 88f));
                var leaveBtn = UiFactory.CreateButton(card, "LeaveButton", "先回大廳", Palette.Gray, 34, OnLobby);
                UiFactory.Place((RectTransform)leaveBtn.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(-170f, 28f), new Vector2(280f, 88f));
            }
        }

        void BuildPlayerRow(GameView v, PlayerView p, int delta, bool isWinner, bool isLoser, bool gameEnd, float top, float height)
        {
            var row = UiFactory.CreatePanel(card, "Row" + p.seat, isWinner ? Palette.RowHighlight : Palette.Cream, 20);
            TopLeft(row.rectTransform, 30f, top, CardWidth - 60f, height);
            if (isWinner) UiFactory.CreateRing(row.transform, "WinRing", Palette.Coral, 20, 3, 0f);

            var avatar = UiFactory.CreateAvatar(row.transform, p.avatar, 64f);
            UiFactory.Place(avatar, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(18f, 0f), new Vector2(64f, 64f));

            string tag = TileFace.WindName(p.seatWind) + "家";
            if (p.seat == v.dealerSeat) tag += "·莊";
            if (isWinner) tag += "·胡";
            if (isLoser) tag += "·放槍";

            var name = UiFactory.CreateLabel(row.transform, "Name", p.name, 28, Palette.Ink, TextAnchor.MiddleLeft);
            name.fontStyle = FontStyle.Bold;
            UiFactory.Place(name.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0f), new Vector2(96f, 4f), new Vector2(210f, 38f));
            var tagText = UiFactory.CreateLabel(row.transform, "Tag", tag, 22, Palette.InkSoft, TextAnchor.MiddleLeft);
            UiFactory.Place(tagText.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 1f), new Vector2(96f, -4f), new Vector2(210f, 32f));

            // Revealed hand (sorted), drawn tile, then melds.
            var tilesArea = UiFactory.CreateRect("Tiles", row.transform);
            UiFactory.Place(tilesArea, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(316f, 0f), new Vector2(880f, TileSizes.Mini.height));
            BuildRevealedTiles(tilesArea, p);

            // Delta column
            var deltaText = UiFactory.CreateText(row.transform, "Delta", "", 30, Palette.Ink, TextAnchor.MiddleRight);
            deltaText.fontStyle = FontStyle.Bold;
            UiFactory.Place(deltaText.rectTransform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-22f, 0f), new Vector2(230f, height - 8f));
            if (gameEnd)
            {
                deltaText.text = "本局 " + Format.Signed(delta) + "\n本場 " + Format.Signed(p.sessionDelta);
                deltaText.fontSize = 26;
                deltaText.color = p.sessionDelta > 0 ? Palette.Gain : (p.sessionDelta < 0 ? Palette.Loss : Palette.Ink);
            }
            else
            {
                deltaText.text = Format.Signed(delta) + " 金幣";
                deltaText.color = delta > 0 ? Palette.Gain : (delta < 0 ? Palette.Loss : Palette.Ink);
            }
        }

        static void BuildRevealedTiles(RectTransform area, PlayerView p)
        {
            TileSize size = TileSizes.Mini;
            float step = size.width + 1f;
            const float groupGap = 10f;
            float x = 0f;

            List<string> hand = TileFace.Sorted(p.hand);
            if (hand.Count == 0 && p.handCount > 0)
            {
                for (int i = 0; i < p.handCount; i++)
                {
                    var back = TileView.CreateBack(area, size);
                    PlaceAt(back, x);
                    x += step;
                }
            }
            for (int i = 0; i < hand.Count; i++)
            {
                PlaceAt(TileView.CreateFace(area, hand[i], size), x);
                x += step;
            }
            string drawn = DtoUtil.Safe(p.drawnTile);
            if (drawn.Length > 0)
            {
                x += groupGap * 0.6f;
                var t = TileView.CreateFace(area, drawn, size);
                PlaceAt(t, x);
                TileView.AddRing(t, Palette.LastDiscardRing, size, 2);
                x += step;
            }

            MeldDto[] melds = DtoUtil.Safe(p.melds);
            for (int m = 0; m < melds.Length; m++)
            {
                if (melds[m] == null || DtoUtil.Safe(melds[m].tiles).Length == 0) continue;
                x += groupGap;
                // Same meld picture as on the table: claimed tile sideways, concealed kong outer tiles face down.
                RectTransform box = TileView.CreateMeld(area, melds[m], size);
                PlaceAt(box, x);
                x += TileView.MeldWidth(melds[m], size) + 1f;
            }

            string[] flowers = DtoUtil.Safe(p.flowers);
            if (flowers.Length > 0) x += groupGap;
            for (int i = 0; i < flowers.Length; i++)
            {
                PlaceAt(TileView.CreateFace(area, flowers[i], size), x);
                x += step;
            }

            // Shrink to fit if an unusually long row would overflow its column.
            float available = area.sizeDelta.x;
            if (x > available && x > 0f)
            {
                float s = available / x;
                area.localScale = new Vector3(s, s, 1f);
            }
        }

        static void PlaceAt(RectTransform tile, float x)
        {
            UiFactory.Place(tile, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(x, 0f), tile.sizeDelta);
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

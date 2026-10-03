using System;
using Manjong.Core;
using Manjong.Net;
using Manjong.UI;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.Screens
{
    /// <summary>Lobby: profile, nickname change, start game, relief coins and leaderboard.</summary>
    public class LobbyScreen : MonoBehaviour
    {
        const int NicknameMax = 12;
        static readonly float[] ColumnStops = { 0f, 0.12f, 0.46f, 0.68f, 0.84f, 1f };

        AppController app;

        Text nicknameText;
        Text coinsText;
        Text statsText;
        InputField nicknameInput;
        Text nicknameHint;
        Button renameButton;
        Button startButton;
        Text startHint;
        Button reliefButton;
        Text reliefHint;

        Button refreshButton;
        Text updatedText;
        RectTransform listContent;
        ScrollRect listScroll;
        Text listStatus;

        PlayerDto me;

        public void Init(AppController owner)
        {
            app = owner;
            var root = (RectTransform)transform;

            var title = UiFactory.CreateLabel(root, "Title", "可愛麻將", 96, Palette.Ink, TextAnchor.MiddleCenter);
            title.fontStyle = FontStyle.Bold;
            UiFactory.Place(title.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -36f), new Vector2(900f, 120f));
            var subtitle = UiFactory.CreateLabel(root, "Subtitle", "台灣 16 張麻將·你對上三隻 AI", 32, Palette.InkSoft, TextAnchor.MiddleCenter);
            UiFactory.Place(subtitle.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -154f), new Vector2(900f, 46f));

            BuildProfileCard(root);
            BuildLeaderboardCard(root);
        }

        // ---------- Build ----------

        static RectTransform Card(Transform parent, string name, float x)
        {
            var card = UiFactory.CreatePanel(parent, name, Palette.Card, 36);
            UiFactory.Place(card.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(x, -60f), new Vector2(820f, 760f));
            UiFactory.AddShadow(card, Palette.CardShadow, new Vector2(0f, -6f));
            return card.rectTransform;
        }

        /// <summary>Places a child rect relative to the card's top-left corner.</summary>
        static void TopLeft(RectTransform rt, float x, float y, float w, float h)
        {
            UiFactory.Place(rt, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -y), new Vector2(w, h));
        }

        void BuildProfileCard(Transform root)
        {
            var card = Card(root, "ProfileCard", -430f);

            var avatar = UiFactory.CreateAvatar(card, "me", 120f);
            TopLeft(avatar, 40f, 40f, 120f, 120f);

            nicknameText = UiFactory.CreateLabel(card, "Nickname", "", 46, Palette.Ink, TextAnchor.MiddleLeft);
            nicknameText.fontStyle = FontStyle.Bold;
            TopLeft(nicknameText.rectTransform, 190f, 44f, 590f, 60f);

            coinsText = UiFactory.CreateLabel(card, "Coins", "", 38, Palette.Ink, TextAnchor.MiddleLeft);
            TopLeft(coinsText.rectTransform, 190f, 108f, 590f, 52f);

            statsText = UiFactory.CreateLabel(card, "Stats", "", 26, Palette.InkSoft, TextAnchor.MiddleLeft);
            TopLeft(statsText.rectTransform, 40f, 186f, 740f, 40f);

            var renameLabel = UiFactory.CreateLabel(card, "RenameLabel", "修改暱稱", 28, Palette.Ink, TextAnchor.MiddleLeft);
            TopLeft(renameLabel.rectTransform, 40f, 244f, 400f, 40f);

            nicknameInput = UiFactory.CreateInput(card, "NicknameInput", "輸入新暱稱（1–12 個字）", 30, NicknameMax);
            nicknameInput.onEndEdit.AddListener(OnNicknameEndEdit);
            bool webPrompt = WebPrompt.IsAvailable;
            TopLeft((RectTransform)nicknameInput.transform, 40f, 290f, webPrompt ? 400f : 560f, 76f);

            renameButton = UiFactory.CreateButton(card, "RenameButton", "改暱稱", Palette.Sky, 30, SubmitNickname);
            TopLeft((RectTransform)renameButton.transform, webPrompt ? 456f : 620f, 290f, 160f, 76f);

            if (webPrompt)
            {
                // Browser IME cannot reach the legacy InputField on WebGL; window.prompt can.
                var promptButton = UiFactory.CreateButton(card, "PromptButton", "中文輸入", Palette.Lavender, 28, OpenBrowserPrompt);
                TopLeft((RectTransform)promptButton.transform, 632f, 290f, 148f, 76f);
            }

            nicknameHint = UiFactory.CreateLabel(card, "NicknameHint", "", 26, Palette.InkSoft, TextAnchor.MiddleLeft);
            TopLeft(nicknameHint.rectTransform, 40f, 374f, 740f, 40f);
            SetNicknameHint("暱稱長度 1–12 個字", false);

            startButton = UiFactory.CreateButton(card, "StartButton", "開始遊戲（東風圈）", Palette.Pink, 44, OnStart);
            TopLeft((RectTransform)startButton.transform, 40f, 440f, 740f, 110f);

            startHint = UiFactory.CreateLabel(card, "StartHint", "", 26, Palette.InkSoft, TextAnchor.MiddleLeft);
            TopLeft(startHint.rectTransform, 40f, 560f, 740f, 40f);

            reliefButton = UiFactory.CreateButton(card, "ReliefButton", "領救濟金", Palette.Butter, 34, OnRelief);
            TopLeft((RectTransform)reliefButton.transform, 40f, 620f, 300f, 80f);

            reliefHint = UiFactory.CreateText(card, "ReliefHint", "金幣低於 1,000 時可領，\n補到 10,000 金幣", 24, Palette.InkSoft, TextAnchor.MiddleLeft);
            TopLeft(reliefHint.rectTransform, 360f, 620f, 420f, 80f);

            var note = UiFactory.CreateLabel(card, "CoinNote", "金幣為遊戲內虛擬點數，不可儲值、不可兌換。", 24, Palette.InkSoft, TextAnchor.MiddleLeft);
            TopLeft(note.rectTransform, 40f, 712f, 740f, 36f);
        }

        void BuildLeaderboardCard(Transform root)
        {
            var card = Card(root, "LeaderboardCard", 430f);

            var title = UiFactory.CreateLabel(card, "Title", "排行榜", 44, Palette.Ink, TextAnchor.MiddleLeft);
            title.fontStyle = FontStyle.Bold;
            TopLeft(title.rectTransform, 40f, 28f, 400f, 60f);

            updatedText = UiFactory.CreateLabel(card, "Updated", "", 24, Palette.InkSoft, TextAnchor.MiddleLeft);
            TopLeft(updatedText.rectTransform, 40f, 88f, 480f, 34f);

            refreshButton = UiFactory.CreateButton(card, "RefreshButton", "重新整理", Palette.Sky, 30, OnRefresh);
            UiFactory.Place((RectTransform)refreshButton.transform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-40f, -32f), new Vector2(200f, 72f));

            var header = UiFactory.CreateRect("Header", card);
            TopLeft(header, 30f, 134f, 738f, 46f);
            string[] headers = { "名次", "暱稱", "金幣", "胡牌次數", "最大台數" };
            for (int i = 0; i < headers.Length; i++)
            {
                var t = UiFactory.CreateLabel(header, "H" + i, headers[i], 26, Palette.InkSoft, i == 1 ? TextAnchor.MiddleLeft : TextAnchor.MiddleCenter);
                t.fontStyle = FontStyle.Bold;
                UiFactory.Column(t.rectTransform, ColumnStops[i], ColumnStops[i + 1], 6f, 6f);
            }

            listScroll = UiFactory.CreateVerticalScroll(card, "List", out listContent);
            TopLeft((RectTransform)listScroll.transform, 30f, 186f, 760f, 544f);

            listStatus = UiFactory.CreateText(card, "ListStatus", "", 30, Palette.InkSoft, TextAnchor.MiddleCenter);
            TopLeft(listStatus.rectTransform, 30f, 186f, 738f, 300f);
        }

        // ---------- State ----------

        public void Show(PlayerDto player)
        {
            me = player;
            if (me == null) return;
            nicknameText.text = me.nickname;
            coinsText.text = "金幣 " + Format.Coins(me.coins);
            statsText.text = "已打 " + me.handsPlayed + " 局·胡牌 " + me.handsWon + " 次·自摸 " + me.selfDraws +
                             " 次·放槍 " + me.dealIns + " 次·最大 " + me.bestTai + " 台";

            bool canPlay = me.coins >= AppController.MinCoinsToPlay;
            UiFactory.SetInteractable(startButton, canPlay);
            UiFactory.SetInteractable(reliefButton, !canPlay);
            if (canPlay)
            {
                startHint.text = "底 100·每台 50·打一圈（東風圈）";
                startHint.color = Palette.InkSoft;
            }
            else
            {
                startHint.text = "金幣不足 1,000，無法開局，請先領救濟金";
                startHint.color = Palette.Loss;
            }
            reliefHint.color = canPlay ? Palette.InkSoft : Palette.Ink;
        }

        public void SetNicknameHint(string message, bool isError)
        {
            nicknameHint.text = message;
            nicknameHint.color = isError ? Palette.Loss : (message == "暱稱已更新" ? Palette.Gain : Palette.InkSoft);
        }

        public void SetLeaderboardLoading()
        {
            if (listContent.childCount == 0)
            {
                listStatus.text = "排行榜載入中…";
                listStatus.color = Palette.InkSoft;
                listStatus.gameObject.SetActive(true);
            }
            UiFactory.SetInteractable(refreshButton, false);
        }

        public void SetLeaderboardError(string message)
        {
            UiFactory.SetInteractable(refreshButton, true);
            UiFactory.DestroyChildren(listContent);
            updatedText.text = "";
            listStatus.text = "排行榜載入失敗\n" + message;
            listStatus.color = Palette.Loss;
            listStatus.gameObject.SetActive(true);
        }

        public void SetLeaderboard(LeaderboardResponse data)
        {
            UiFactory.SetInteractable(refreshButton, true);
            UiFactory.DestroyChildren(listContent);
            listStatus.color = Palette.InkSoft;
            updatedText.text = "更新時間 " + DateTime.Now.ToString("HH:mm:ss");

            LeaderboardEntry[] entries = data != null ? DtoUtil.Safe(data.entries) : new LeaderboardEntry[0];
            if (entries.Length == 0)
            {
                listStatus.text = "目前還沒有人上榜";
                listStatus.gameObject.SetActive(true);
                return;
            }
            listStatus.gameObject.SetActive(false);

            for (int i = 0; i < entries.Length; i++)
            {
                if (entries[i] != null) BuildRow(entries[i]);
            }
            listScroll.verticalNormalizedPosition = 1f;
        }

        void BuildRow(LeaderboardEntry e)
        {
            var row = UiFactory.CreatePanel(listContent, "Row" + e.rank, e.isMe ? Palette.RowHighlight : Palette.Cream, 14);
            UiFactory.FixedHeight(row.gameObject, 58f);
            if (e.isMe) UiFactory.CreateRing(row.transform, "MeRing", Palette.Coral, 14, 3, 0f);

            string[] cells =
            {
                e.rank.ToString(),
                e.isMe ? e.nickname + "（我）" : e.nickname,
                Format.Coins(e.coins),
                e.handsWon + " 次",
                e.bestTai + " 台"
            };
            for (int i = 0; i < cells.Length; i++)
            {
                var t = UiFactory.CreateLabel(row.transform, "C" + i, cells[i], 28, Palette.Ink, i == 1 ? TextAnchor.MiddleLeft : TextAnchor.MiddleCenter);
                if (e.isMe) t.fontStyle = FontStyle.Bold;
                UiFactory.Column(t.rectTransform, ColumnStops[i], ColumnStops[i + 1], 8f, 6f);
            }
        }

        // ---------- Handlers ----------

        void OnNicknameEndEdit(string _)
        {
            if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter)) SubmitNickname();
        }

        void SubmitNickname()
        {
            if (app.IsBusy) return;
            string nick = (nicknameInput.text ?? "").Trim();
            int len = Format.CodePointLength(nick);
            if (len < 1)
            {
                SetNicknameHint("暱稱不能是空白", true);
                return;
            }
            if (len > NicknameMax)
            {
                SetNicknameHint("暱稱最多 12 個字", true);
                return;
            }
            SetNicknameHint("送出中…", false);
            app.ChangeNickname(nick);
        }

        void OpenBrowserPrompt()
        {
            string current = string.IsNullOrEmpty(nicknameInput.text) ? (me != null ? me.nickname : "") : nicknameInput.text;
            string answer = WebPrompt.Ask("輸入新暱稱（1–12 個字）", current);
            if (answer == null) return;
            nicknameInput.text = answer.Trim();
            SubmitNickname();
        }

        void OnStart()
        {
            if (app.IsBusy) return;
            if (me != null && me.coins < AppController.MinCoinsToPlay)
            {
                app.ShowToast("金幣不足 1,000，請先領救濟金");
                return;
            }
            app.StartGame();
        }

        void OnRelief()
        {
            if (app.IsBusy) return;
            app.ClaimRelief();
        }

        void OnRefresh()
        {
            if (app.IsBusy) return;
            app.RefreshLobby();
        }
    }
}

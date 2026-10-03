using System.Collections;
using System.Collections.Generic;
using System.Text;
using Manjong.Core;
using Manjong.Net;
using Manjong.UI;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.Screens
{
    /// <summary>
    /// The game table, driven by WebSocket messages (contract v0.2).
    /// "step" and "state" messages go into one FIFO queue that a coroutine plays in order: each step is drawn and
    /// held for a short delay; a "state" is applied when it reaches the head of the queue and only then unlocks
    /// input (when its options are non-empty). Sending start / action locks input until the next "state".
    /// Every render takes a whole GameView; each region keeps a signature string and is rebuilt only when its
    /// data changed. Relative seat = (seat - mySeat + 4) % 4: 0 me (bottom), 1 next (right), 2 opposite (top), 3 previous (left).
    /// </summary>
    public class TableScreen : MonoBehaviour
    {
        const int MaxEvents = 5;
        const float StepDelay = 0.35f;
        const float HandStartDelay = 0.8f;
        const float WinDelay = 1.2f;
        const float FastDelay = 0.08f;
        const int FastForwardQueueLength = 6;

        const float InfoW = 250f;
        const float InfoH = 110f;
        const float SidePanelW = 300f;
        const float SidePanelH = 530f;
        const int RiverColsWide = 10;   // bottom / top rivers
        const int RiverColsNarrow = 8;  // left / right rivers
        const float RiverGap = 2f;
        const float SelectLift = 24f;

        class SeatUi
        {
            public RectTransform info;
            public RectTransform flowers;
            public RectTransform hand;
            public RectTransform melds;
            public string infoSig;
            public string flowerSig;
            public string handSig;
            public string meldSig;
        }

        /// <summary>Exactly one of step / state is set.</summary>
        class QueuedItem
        {
            public StepDto step;
            public GameView state;
        }

        AppController app;
        RectTransform root;
        RectTransform tableArea;

        readonly SeatUi[] seats = new SeatUi[4];
        readonly RectTransform[] rivers = new RectTransform[4];
        readonly string[] riverSigs = new string[4];

        Text centerRound;
        Text centerWall;
        Text centerTurn;
        Text myCoinsText;

        RectTransform actionBar;
        string actionSig;

        Image hintBar;
        Image hintRing;
        Text hintText;

        GameObject connectionBanner;
        Text connectionText;
        ConnectionState connectionState = ConnectionState.Ready;

        readonly Text[] eventLines = new Text[MaxEvents];
        readonly List<string> events = new List<string>();

        ResultPanel resultPanel;

        readonly Queue<QueuedItem> queue = new Queue<QueuedItem>();
        GameView view;
        bool lastRenderFinal;
        bool pumping;
        bool playing;
        bool awaiting;
        bool fastForward;
        int selectedIndex = -1;
        string myHandContentSig;
        readonly List<string> handOrder = new List<string>();

        // ---------- Build ----------

        public void Init(AppController owner)
        {
            app = owner;
            root = (RectTransform)transform;

            BuildTable();
            for (int rel = 0; rel < 4; rel++) seats[rel] = BuildSeat(rel);
            BuildTopBar();
            BuildEventLog();
            BuildHintBar();

            actionBar = UiFactory.CreateRect("ActionBar", root);
            UiFactory.Place(actionBar, new Vector2(1f, 0f), new Vector2(1f, 0f), new Vector2(-24f, 232f), new Vector2(1000f, 84f));

            BuildConnectionBanner();

            resultPanel = new ResultPanel();
            resultPanel.Build(root);
        }

        static int RiverColsFor(int rel)
        {
            return rel == 0 || rel == 2 ? RiverColsWide : RiverColsNarrow;
        }

        void BuildTable()
        {
            var table = UiFactory.CreatePanel(root, "Table", Palette.Mint, 48);
            tableArea = table.rectTransform;
            UiFactory.Place(tableArea, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 16f), new Vector2(1240f, 680f));
            UiFactory.CreateRing(table.transform, "Edge", Palette.MintDeep, 48, 8, 0f);

            // Center info
            var info = UiFactory.CreatePanel(tableArea, "CenterInfo", Palette.Card, 28);
            UiFactory.Place(info.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(340f, 150f));
            UiFactory.AddShadow(info, Palette.CardShadow, new Vector2(0f, -4f));
            centerRound = UiFactory.CreateLabel(info.transform, "Round", "", 32, Palette.Ink, TextAnchor.MiddleCenter);
            centerRound.fontStyle = FontStyle.Bold;
            UiFactory.Place(centerRound.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -10f), new Vector2(316f, 44f));
            centerWall = UiFactory.CreateLabel(info.transform, "Wall", "", 28, Palette.Ink, TextAnchor.MiddleCenter);
            UiFactory.Place(centerWall.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -56f), new Vector2(316f, 40f));
            centerTurn = UiFactory.CreateLabel(info.transform, "Turn", "", 24, Palette.InkSoft, TextAnchor.MiddleCenter);
            UiFactory.Place(centerTurn.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -98f), new Vector2(326f, 42f));

            // Rivers around the center info (table-local coordinates). Bottom/top: 10 columns, sides: 8 columns.
            float step = TileSizes.Small.width + RiverGap;
            float wideW = RiverColsWide * step - RiverGap;
            float narrowW = RiverColsNarrow * step - RiverGap;
            float riverH = 4f * (TileSizes.Small.height + RiverGap);
            float sideX = wideW * 0.5f + 12f;
            rivers[0] = MakeArea("River0", tableArea, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 1f), new Vector2(0f, -85f), new Vector2(wideW, riverH));
            rivers[2] = MakeArea("River2", tableArea, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0f), new Vector2(0f, 85f), new Vector2(wideW, riverH));
            rivers[1] = MakeArea("River1", tableArea, new Vector2(0.5f, 0.5f), new Vector2(0f, 0.5f), new Vector2(sideX, 0f), new Vector2(narrowW, riverH));
            rivers[3] = MakeArea("River3", tableArea, new Vector2(0.5f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-sideX, 0f), new Vector2(narrowW, riverH));
        }

        static RectTransform MakeArea(string name, Transform parent, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            var rt = UiFactory.CreateRect(name, parent);
            UiFactory.Place(rt, anchor, pivot, pos, size);
            return rt;
        }

        SeatUi BuildSeat(int rel)
        {
            var s = new SeatUi();
            switch (rel)
            {
                case 0: // me, bottom
                    s.info = MakeArea("Seat0Info", root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(24f, 24f), new Vector2(InfoW, InfoH));
                    s.flowers = MakeArea("Seat0Flowers", root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(24f, 146f), new Vector2(InfoW, TileSizes.Mini.height));
                    s.melds = MakeArea("Seat0Melds", root, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 152f), new Vector2(1000f, TileSizes.Small.height));
                    s.hand = MakeArea("Seat0Hand", root, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 20f), new Vector2(1400f, TileSizes.Large.height + SelectLift));
                    break;
                case 2: // opposite, top
                    s.info = MakeArea("Seat2Info", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(-560f, -20f), new Vector2(InfoW, InfoH));
                    s.flowers = MakeArea("Seat2Flowers", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(-560f, -136f), new Vector2(InfoW, TileSizes.Mini.height));
                    s.hand = MakeArea("Seat2Hand", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -20f), new Vector2(620f, TileSizes.Back.height));
                    s.melds = MakeArea("Seat2Melds", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -64f), new Vector2(760f, TileSizes.Mini.height));
                    break;
                default: // sides: 1 right, 3 left
                {
                    bool right = rel == 1;
                    var panel = MakeArea("Seat" + rel + "Panel", root,
                        new Vector2(right ? 1f : 0f, 0.5f), new Vector2(right ? 1f : 0f, 0.5f),
                        new Vector2(right ? -20f : 20f, 45f), new Vector2(SidePanelW, SidePanelH));
                    float innerW = SidePanelW - 20f;
                    s.info = MakeArea("Info", panel, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, 0f), new Vector2(InfoW, InfoH));
                    s.flowers = MakeArea("Flowers", panel, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, -118f), new Vector2(innerW, TileSizes.Mini.height));
                    s.hand = MakeArea("Hand", panel, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, -172f), new Vector2(innerW, 3f * (TileSizes.Back.height + 2f)));
                    s.melds = MakeArea("Melds", panel, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, -298f), new Vector2(innerW, 3f * (TileSizes.Mini.height + 4f)));
                    break;
                }
            }
            return s;
        }

        void BuildTopBar()
        {
            var leave = UiFactory.CreateButton(root, "LeaveButton", "離開", Palette.Gray, 32, OnLeave);
            UiFactory.Place((RectTransform)leave.transform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(20f, -20f), new Vector2(150f, 70f));

            myCoinsText = UiFactory.CreateLabel(root, "MyCoins", "", 26, Palette.Ink, TextAnchor.MiddleLeft);
            UiFactory.Place(myCoinsText.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(22f, -100f), new Vector2(200f, 40f));
        }

        void BuildEventLog()
        {
            var panel = UiFactory.CreatePanel(root, "EventLog", Palette.Card, 24);
            UiFactory.Place(panel.rectTransform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-20f, -20f), new Vector2(420f, 196f));
            UiFactory.AddShadow(panel, Palette.CardShadow, new Vector2(0f, -4f));
            for (int i = 0; i < MaxEvents; i++)
            {
                var t = UiFactory.CreateLabel(panel.transform, "Line" + i, "", 24, Palette.InkSoft, TextAnchor.MiddleLeft);
                UiFactory.Place(t.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(18f, -12f - i * 34.5f), new Vector2(384f, 34f));
                eventLines[i] = t;
            }
        }

        /// <summary>
        /// Waits hint at the bottom-left, above my flowers and clear of my meld row (which can reach y = 212):
        /// "打出後聽…" / "聽牌中…".
        /// </summary>
        void BuildHintBar()
        {
            hintBar = UiFactory.CreatePanel(root, "WaitHint", Palette.Card, 20);
            UiFactory.Place(hintBar.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(24f, 222f), new Vector2(700f, 50f));
            UiFactory.AddShadow(hintBar, Palette.CardShadow, new Vector2(0f, -3f));
            hintRing = UiFactory.CreateRing(hintBar.transform, "Ring", Palette.Coral, 20, 3, 0f);
            hintText = UiFactory.CreateLabel(hintBar.transform, "Text", "", 26, Palette.Ink, TextAnchor.MiddleLeft);
            UiFactory.Stretch(hintText.rectTransform, 18f, 4f, 14f, 4f);
            hintBar.gameObject.SetActive(false);
        }

        void BuildConnectionBanner()
        {
            var banner = UiFactory.CreatePanel(root, "ConnectionBanner", Palette.Butter, 22);
            UiFactory.Place(banner.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -118f), new Vector2(660f, 58f));
            UiFactory.AddShadow(banner, Palette.CardShadow, new Vector2(0f, -3f));
            UiFactory.CreateRing(banner.transform, "Ring", Palette.LastDiscardRing, 22, 3, 0f);
            connectionText = UiFactory.CreateLabel(banner.transform, "Text", "", 28, Palette.Ink, TextAnchor.MiddleCenter);
            connectionText.fontStyle = FontStyle.Bold;
            UiFactory.Stretch(connectionText.rectTransform, 16f, 4f, 16f, 4f);
            connectionBanner = banner.gameObject;
            connectionBanner.SetActive(false);
        }

        // ---------- Public API (called by AppController) ----------

        /// <summary>The last known view is game_end: a reconnect must not send "start" (it would open a new game).</summary>
        public bool IsGameOver
        {
            get { return view != null && view.phase == "game_end"; }
        }

        /// <summary>Entering the table after "start" (new or resumed game). Messages follow via Enqueue*.</summary>
        public void BeginGame()
        {
            StopAllCoroutines();
            ResetState();
            awaiting = true; // locked until the first "state"
            connectionState = ConnectionState.Ready;
            connectionBanner.SetActive(false);
        }

        public void EnqueueStep(StepDto step)
        {
            if (step == null) return;
            queue.Enqueue(new QueuedItem { step = step });
            EnsurePump();
        }

        public void EnqueueState(GameView state)
        {
            if (state == null) return;
            queue.Enqueue(new QueuedItem { state = state });
            EnsurePump();
        }

        /// <summary>Reconnected: drop whatever was still queued and wait for the fresh snapshot.</summary>
        public void PrepareResync()
        {
            queue.Clear();
            fastForward = false;
            awaiting = true;
            selectedIndex = -1;
            if (view != null && !pumping) Render(view, lastRenderFinal);
        }

        /// <summary>The server reported an error that is not followed by a state: unlock and redraw.</summary>
        public void OnServerError()
        {
            awaiting = false;
            if (view != null && !pumping) Render(view, true);
        }

        public void SetConnectionState(ConnectionState state)
        {
            connectionState = state;
            if (view != null && !pumping) Render(view, lastRenderFinal);
            bool ok = state == ConnectionState.Ready;
            connectionBanner.SetActive(!ok);
            if (!ok)
            {
                connectionText.text = state == ConnectionState.Stopped ? "連線已中斷" : "連線中斷，正在重新連線…";
                // Above everything on the table, including an open result panel.
                connectionBanner.transform.SetAsLastSibling();
            }
        }

        public void Hide()
        {
            StopAllCoroutines();
            pumping = false;
            playing = false;
            awaiting = false;
            fastForward = false;
            queue.Clear();
            if (resultPanel != null) resultPanel.Hide();
            gameObject.SetActive(false);
        }

        // ---------- Playback ----------

        void ResetState()
        {
            queue.Clear();
            view = null;
            lastRenderFinal = false;
            pumping = false;
            playing = false;
            awaiting = false;
            fastForward = false;
            selectedIndex = -1;
            myHandContentSig = null;
            handOrder.Clear();
            events.Clear();
            RefreshEventLog();
            actionSig = null;
            for (int i = 0; i < 4; i++)
            {
                riverSigs[i] = null;
                if (seats[i] != null)
                {
                    seats[i].infoSig = null;
                    seats[i].flowerSig = null;
                    seats[i].handSig = null;
                    seats[i].meldSig = null;
                }
            }
            hintBar.gameObject.SetActive(false);
            resultPanel.Hide();
        }

        void EnsurePump()
        {
            if (pumping || !gameObject.activeInHierarchy) return;
            StartCoroutine(PumpRoutine());
        }

        void Update()
        {
            // Tap / click anywhere fast-forwards the queued playback.
#if ENABLE_LEGACY_INPUT_MANAGER
            if (pumping && playing && !fastForward)
            {
                bool tapped = Input.GetMouseButtonDown(0);
                for (int i = 0; !tapped && i < Input.touchCount; i++)
                {
                    if (Input.GetTouch(i).phase == TouchPhase.Began) tapped = true;
                }
                if (tapped) fastForward = true;
            }
#endif
        }

        IEnumerator PumpRoutine()
        {
            pumping = true;
            try
            {
                while (queue.Count > 0)
                {
                    QueuedItem item = queue.Dequeue();
                    CheckGameChanged(item.state != null ? item.state : (item.step != null ? item.step.view : null));
                    if (item.state != null)
                    {
                        // Authoritative snapshot: apply it and unlock (input is possible only if options exist).
                        playing = false;
                        awaiting = false;
                        fastForward = false;
                        Render(item.state, true);
                        continue;
                    }

                    StepDto step = item.step;
                    playing = true;
                    resultPanel.Hide();
                    if (step.view != null) Render(step.view, false);
                    PushEvent(EventText(step));

                    string type = step.@event != null ? step.@event.type : "";
                    float elapsed = 0f;
                    while (elapsed < CurrentDelay(type))
                    {
                        elapsed += Time.unscaledDeltaTime;
                        yield return null;
                    }
                }
            }
            finally
            {
                // Guaranteed even if a render throws, so the table never stays locked in "playing".
                pumping = false;
                playing = false;
            }
            if (view != null && !lastRenderFinal) Render(view, false);
        }

        /// <summary>
        /// A different gameId than the one on screen (e.g. the server restarted while we were reconnecting):
        /// tell the player and start the event log afresh before applying it.
        /// </summary>
        void CheckGameChanged(GameView next)
        {
            if (next == null || view == null) return;
            if (string.IsNullOrEmpty(next.gameId) || string.IsNullOrEmpty(view.gameId) || next.gameId == view.gameId) return;
            app.ShowToast("牌局已重新開始");
            events.Clear();
            RefreshEventLog();
            selectedIndex = -1;
        }

        float CurrentDelay(string eventType)
        {
            if (fastForward || queue.Count > FastForwardQueueLength) return FastDelay;
            if (eventType == "hand_start") return HandStartDelay;
            if (eventType == "win") return WinDelay;
            return StepDelay;
        }

        /// <summary>Server text, except my own draw whose text is empty by contract: "你 摸到 五萬".</summary>
        static string EventText(StepDto step)
        {
            EventDto e = step.@event;
            if (e == null) return "";
            string text = DtoUtil.Safe(e.text);
            if (text.Length == 0 && e.type == "draw" && step.view != null && e.seat == step.view.mySeat && !string.IsNullOrEmpty(e.tile))
            {
                return "你 摸到 " + TileFace.Name(e.tile);
            }
            return text;
        }

        void PushEvent(string text)
        {
            if (string.IsNullOrEmpty(text)) return;
            events.Add(text);
            while (events.Count > MaxEvents) events.RemoveAt(0);
            RefreshEventLog();
        }

        void RefreshEventLog()
        {
            // Oldest at the top, newest at the bottom (bold, full-strength ink).
            int offset = MaxEvents - events.Count;
            for (int i = 0; i < MaxEvents; i++)
            {
                int idx = i - offset;
                bool has = idx >= 0 && idx < events.Count;
                eventLines[i].text = has ? events[idx] : "";
                bool newest = has && idx == events.Count - 1;
                eventLines[i].color = newest ? Palette.Ink : Palette.InkSoft;
                eventLines[i].fontStyle = newest ? FontStyle.Bold : FontStyle.Normal;
            }
        }

        bool CanAct
        {
            get
            {
                return !playing && !awaiting && view != null && view.phase == "playing" &&
                       connectionState == ConnectionState.Ready && DtoUtil.HasOptions(view);
            }
        }

        // ---------- Render ----------

        void Render(GameView v, bool isFinal)
        {
            if (v == null) return;
            view = v;
            lastRenderFinal = isFinal;
            int mySeat = v.mySeat;

            for (int seat = 0; seat < 4; seat++)
            {
                int rel = (seat - mySeat + 4) % 4;
                PlayerView p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                RenderInfo(rel, p, v);
                RenderFlowers(rel, p);
                RenderMelds(rel, p);
                if (rel == 0) RenderMyHand(p, v);
                else RenderOtherHand(rel, p);
                RenderRiver(rel, p, v);
            }

            RenderCenter(v);
            RenderHint(v);
            myCoinsText.text = "我的金幣 " + Format.Coins(v.myCoins);
            RenderActions(v, isFinal);

            bool showResult = isFinal && (v.hasResult || v.phase == "hand_end" || v.phase == "game_end");
            if (showResult) resultPanel.Show(v, OnNextHand, OnBackToLobby);
            else resultPanel.Hide();
        }

        void RenderCenter(GameView v)
        {
            centerRound.text = TileFace.WindName(v.roundWind) + "風圈·第 " + v.handNo + " 局";
            centerWall.text = "剩餘 " + v.wallRemaining + " 張";

            string turn = "";
            if (v.phase == "playing")
            {
                if (CanAct && DtoUtil.HasDiscardOption(v)) turn = "輪到你：點一張牌，再點一次打出";
                else if (CanAct) turn = "請選擇動作";
                else if (awaiting && !playing) turn = "等待伺服器…";
                else if (v.turnSeat >= 0)
                {
                    var p = DtoUtil.Player(v, v.turnSeat);
                    if (p != null) turn = v.turnSeat == v.mySeat ? "輪到你" : "輪到：" + p.name;
                }
            }
            else if (v.phase == "hand_end") turn = "本局結束";
            else if (v.phase == "game_end") turn = "整場結束";
            centerTurn.text = turn;
            centerTurn.color = CanAct ? Palette.Ink : Palette.InkSoft;
        }

        // ----- Waits hint -----

        const int MaxWaitsShown = 4;

        /// <summary>"三筒（剩 2）、六筒（剩 3）"; more than 4 waits are cut to "…等 N 張" so the bar stays one line.</summary>
        static string FormatWaits(WaitDto[] waits)
        {
            var sb = new StringBuilder();
            int total = 0;
            int shown = 0;
            for (int i = 0; i < waits.Length; i++)
            {
                if (waits[i] == null || string.IsNullOrEmpty(waits[i].tile)) continue;
                total++;
                if (shown >= MaxWaitsShown) continue;
                if (sb.Length > 0) sb.Append('、');
                sb.Append(TileFace.Name(waits[i].tile)).Append("（剩 ").Append(Mathf.Max(0, waits[i].left)).Append('）');
                shown++;
            }
            if (total > shown) sb.Append("…等 ").Append(total).Append(" 張");
            return sb.ToString();
        }

        static bool AnyDiscardWaits(GameView v)
        {
            OptionDto[] opts = DtoUtil.Safe(v.options);
            for (int i = 0; i < opts.Length; i++)
            {
                if (opts[i] != null && opts[i].type == "discard" && DtoUtil.Safe(opts[i].waits).Length > 0) return true;
            }
            return false;
        }

        void RenderHint(GameView v)
        {
            string text = "";
            bool listening = false;
            bool canDiscard = CanAct && DtoUtil.HasDiscardOption(v);

            if (canDiscard)
            {
                if (selectedIndex >= 0 && selectedIndex < handOrder.Count)
                {
                    OptionDto opt = DtoUtil.FindOption(v, "discard:" + handOrder[selectedIndex]);
                    WaitDto[] waits = opt != null ? DtoUtil.Safe(opt.waits) : new WaitDto[0];
                    string list = FormatWaits(waits);
                    text = list.Length > 0 ? "打出後聽：" + list : "打出後未聽牌";
                    listening = list.Length > 0;
                }
                else if (AnyDiscardWaits(v))
                {
                    text = "有「聽」標記的牌，打出後就會聽牌";
                }
            }
            else if (v.phase == "playing")
            {
                string list = FormatWaits(DtoUtil.Safe(v.myWaits));
                if (list.Length > 0)
                {
                    text = "聽牌中：" + list;
                    listening = true;
                }
            }

            bool show = text.Length > 0;
            hintBar.gameObject.SetActive(show);
            if (!show) return;
            hintText.text = text;
            hintText.fontStyle = listening ? FontStyle.Bold : FontStyle.Normal;
            hintRing.gameObject.SetActive(listening);
        }

        // ----- Info card -----

        void RenderInfo(int rel, PlayerView p, GameView v)
        {
            SeatUi s = seats[rel];
            bool isDealer = p.seat == v.dealerSeat;
            bool isTurn = v.phase == "playing" && p.seat == v.turnSeat;
            string sig = p.name + "|" + p.avatar + "|" + p.seatWind + "|" + isDealer + "|" + v.dealerStreak + "|" + p.sessionDelta + "|" + isTurn;
            if (sig == s.infoSig) return;
            s.infoSig = sig;
            UiFactory.DestroyChildren(s.info);

            var card = UiFactory.CreatePanel(s.info, "Card", Palette.Card, 24);
            UiFactory.Stretch(card.rectTransform);
            UiFactory.AddShadow(card, Palette.CardShadow, new Vector2(0f, -4f));
            if (isTurn) UiFactory.CreateRing(card.transform, "TurnRing", Palette.TurnRing, 26, 4, 3f);

            var avatar = UiFactory.CreateAvatar(card.transform, p.avatar, 78f);
            UiFactory.Place(avatar, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(12f, 0f), new Vector2(78f, 78f));

            var name = UiFactory.CreateLabel(card.transform, "Name", p.name, 28, Palette.Ink, TextAnchor.MiddleLeft);
            name.fontStyle = FontStyle.Bold;
            UiFactory.Place(name.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(100f, -8f), new Vector2(142f, 36f));

            // Badges: seat wind + dealer (with streak)
            float bx = 100f;
            bx += Badge(card.transform, TileFace.WindName(p.seatWind) + "家", Palette.Sky, bx, 58f) + 6f;
            if (isDealer)
            {
                string dealer = v.dealerStreak > 0 ? "莊·連" + v.dealerStreak : "莊";
                Badge(card.transform, dealer, Palette.DealerBadge, bx, v.dealerStreak > 0 ? 80f : 40f);
            }

            var delta = UiFactory.CreateLabel(card.transform, "Delta", "本場 " + Format.Signed(p.sessionDelta), 22, Palette.Ink, TextAnchor.MiddleLeft);
            delta.color = p.sessionDelta > 0 ? Palette.Gain : (p.sessionDelta < 0 ? Palette.Loss : Palette.InkSoft);
            UiFactory.Place(delta.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(100f, -78f), new Vector2(142f, 26f));
        }

        static float Badge(Transform parent, string text, Color bg, float x, float width)
        {
            var pill = UiFactory.CreatePanel(parent, "Badge", bg, 12);
            UiFactory.Place(pill.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -46f), new Vector2(width, 28f));
            var t = UiFactory.CreateLabel(pill.transform, "Text", text, 20, Palette.Ink, TextAnchor.MiddleCenter);
            UiFactory.Stretch(t.rectTransform, 4f, 1f, 4f, 1f);
            return width;
        }

        // ----- Flowers -----

        void RenderFlowers(int rel, PlayerView p)
        {
            SeatUi s = seats[rel];
            string[] flowers = DtoUtil.Safe(p.flowers);
            string sig = string.Join(",", flowers);
            if (sig == s.flowerSig) return;
            s.flowerSig = sig;
            UiFactory.DestroyChildren(s.flowers);

            TileSize size = TileSizes.Mini;
            for (int i = 0; i < flowers.Length; i++)
            {
                var t = TileView.CreateFace(s.flowers, flowers[i], size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(i * (size.width + 1f), 0f), size.Vector);
            }
        }

        // ----- Melds -----

        void RenderMelds(int rel, PlayerView p)
        {
            SeatUi s = seats[rel];
            MeldDto[] melds = DtoUtil.Safe(p.melds);
            var sb = new StringBuilder();
            for (int i = 0; i < melds.Length; i++)
            {
                if (melds[i] == null) continue;
                sb.Append(melds[i].type).Append(':').Append(string.Join(",", DtoUtil.Safe(melds[i].tiles))).Append(';');
            }
            string sig = sb.ToString();
            if (sig == s.meldSig) return;
            s.meldSig = sig;
            UiFactory.DestroyChildren(s.melds);

            if (rel == 0) LayoutMelds(s.melds, melds, TileSizes.Small, 14f, 99, true);
            else if (rel == 2) LayoutMelds(s.melds, melds, TileSizes.Mini, 12f, 99, true);
            else LayoutMelds(s.melds, melds, TileSizes.Mini, 10f, 2, false);
        }

        /// <summary>Lays melds out in rows of "groupsPerRow" groups; concealed kongs show the outer two tiles face down.</summary>
        static void LayoutMelds(RectTransform area, MeldDto[] melds, TileSize size, float groupGap, int groupsPerRow, bool center)
        {
            const float tileGap = 1f;
            var valid = new List<MeldDto>();
            for (int i = 0; i < melds.Length; i++)
            {
                if (melds[i] != null && DtoUtil.Safe(melds[i].tiles).Length > 0) valid.Add(melds[i]);
            }

            float areaW = area.sizeDelta.x;
            for (int rowStart = 0; rowStart < valid.Count; rowStart += groupsPerRow)
            {
                int rowEnd = Mathf.Min(valid.Count, rowStart + groupsPerRow);
                float rowW = 0f;
                for (int g = rowStart; g < rowEnd; g++)
                {
                    int n = valid[g].tiles.Length;
                    rowW += n * (size.width + tileGap) - tileGap;
                    if (g < rowEnd - 1) rowW += groupGap;
                }
                float x = center ? Mathf.Max(0f, (areaW - rowW) * 0.5f) : 0f;
                float y = -(rowStart / groupsPerRow) * (size.height + 4f);

                for (int g = rowStart; g < rowEnd; g++)
                {
                    MeldDto m = valid[g];
                    string[] tiles = m.tiles;
                    bool concealed = m.type == "ankan" && tiles.Length == 4;
                    for (int i = 0; i < tiles.Length; i++)
                    {
                        bool faceDown = concealed && (i == 0 || i == 3);
                        RectTransform t = faceDown ? TileView.CreateBack(area, size) : TileView.CreateFace(area, tiles[i], size);
                        UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, y), size.Vector);
                        x += size.width + tileGap;
                    }
                    x += groupGap - tileGap;
                }
            }
        }

        // ----- Hands -----

        void RenderOtherHand(int rel, PlayerView p)
        {
            SeatUi s = seats[rel];
            string sig = p.handCount.ToString();
            if (sig == s.handSig) return;
            s.handSig = sig;
            UiFactory.DestroyChildren(s.hand);

            TileSize size = TileSizes.Back;
            int count = Mathf.Max(0, p.handCount);
            if (rel == 2)
            {
                // Single centered row.
                float step = size.width + 1f;
                float total = count * step - 1f;
                float x = Mathf.Max(0f, (s.hand.sizeDelta.x - total) * 0.5f);
                for (int i = 0; i < count; i++)
                {
                    var t = TileView.CreateBack(s.hand, size);
                    UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x + i * step, 0f), size.Vector);
                }
            }
            else
            {
                // Compact grid, 8 per row.
                const int cols = 8;
                for (int i = 0; i < count; i++)
                {
                    int c = i % cols;
                    int r = i / cols;
                    var t = TileView.CreateBack(s.hand, size);
                    UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(c * (size.width + 2f), -r * (size.height + 2f)), size.Vector);
                }
            }
        }

        void RenderMyHand(PlayerView p, GameView v)
        {
            SeatUi s = seats[0];
            List<string> sorted = TileFace.Sorted(p.hand);
            string drawn = DtoUtil.Safe(p.drawnTile);
            bool canDiscard = CanAct && DtoUtil.HasDiscardOption(v);

            var sb = new StringBuilder();
            for (int i = 0; i < sorted.Count; i++) sb.Append(sorted[i]).Append(',');
            sb.Append('|').Append(drawn).Append('|').Append(canDiscard).Append('|');
            if (canDiscard)
            {
                OptionDto[] opts = DtoUtil.Safe(v.options);
                for (int i = 0; i < opts.Length; i++)
                {
                    if (opts[i] != null && opts[i].type == "discard")
                    {
                        sb.Append(opts[i].id).Append('/').Append(DtoUtil.Safe(opts[i].waits).Length).Append(';');
                    }
                }
            }
            string contentSig = sb.ToString();

            // Hand contents or playability changed: any previous selection is meaningless now.
            if (contentSig != myHandContentSig)
            {
                myHandContentSig = contentSig;
                selectedIndex = -1;
            }
            string sig = contentSig + "#" + selectedIndex;
            if (sig == s.handSig) return;
            s.handSig = sig;
            UiFactory.DestroyChildren(s.hand);

            handOrder.Clear();
            handOrder.AddRange(sorted);
            if (drawn.Length > 0) handOrder.Add(drawn);
            if (selectedIndex >= handOrder.Count) selectedIndex = -1;

            TileSize size = TileSizes.Large;
            const float gap = 4f;
            const float drawnGap = 26f;
            int n = handOrder.Count;
            float total = n * size.width + Mathf.Max(0, n - 1) * gap + (drawn.Length > 0 ? drawnGap : 0f);
            float startX = (s.hand.sizeDelta.x - total) * 0.5f;

            for (int i = 0; i < n; i++)
            {
                string code = handOrder[i];
                bool isDrawn = drawn.Length > 0 && i == n - 1;
                float x = startX + i * (size.width + gap) + (isDrawn ? drawnGap : 0f);

                var slot = UiFactory.CreateRect("Slot" + i, s.hand);
                UiFactory.Place(slot, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(x, 0f), size.Vector);

                var tile = TileView.CreateFace(slot, code, size);
                bool selected = i == selectedIndex;
                UiFactory.Place(tile, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(0f, selected ? SelectLift : 0f), size.Vector);

                OptionDto opt = canDiscard ? DtoUtil.FindOption(v, "discard:" + code) : null;
                bool discardable = opt != null;
                if (canDiscard && !discardable) TileView.AddVeil(tile, size);
                if (selected) TileView.AddRing(tile, Palette.SelectRing, size, 4);
                if (discardable && DtoUtil.Safe(opt.waits).Length > 0) AddWaitBadge(tile, size);

                if (discardable)
                {
                    var img = tile.GetComponent<Image>();
                    img.raycastTarget = true;
                    var btn = tile.gameObject.AddComponent<Button>();
                    btn.transition = Selectable.Transition.None;
                    var nav = btn.navigation;
                    nav.mode = Navigation.Mode.None;
                    btn.navigation = nav;
                    int index = i;
                    btn.onClick.AddListener(() => OnTileClicked(index));
                }
            }
        }

        /// <summary>Small "聽" pill sitting on the top edge of a tile: discarding it leaves me ready.</summary>
        static void AddWaitBadge(RectTransform tile, TileSize size)
        {
            var pill = UiFactory.CreatePanel(tile, "WaitBadge", Palette.Coral, 12);
            UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 0f), new Vector2(0f, -12f), new Vector2(40f, 28f));
            UiFactory.CreateRing(pill.transform, "Ring", Palette.LastDiscardRing, 12, 2, 0f);
            var t = UiFactory.CreateLabel(pill.transform, "Text", "聽", 20, Palette.Ink, TextAnchor.MiddleCenter);
            t.fontStyle = FontStyle.Bold;
            UiFactory.Stretch(t.rectTransform, 2f, 1f, 2f, 1f);
        }

        // ----- River -----

        void RenderRiver(int rel, PlayerView p, GameView v)
        {
            string[] discards = DtoUtil.Safe(p.discards);
            bool highlightLast = discards.Length > 0 && v.lastDiscardSeat == p.seat &&
                                 discards[discards.Length - 1] == v.lastDiscardTile;
            string sig = string.Join(",", discards) + "|" + highlightLast;
            if (sig == riverSigs[rel]) return;
            riverSigs[rel] = sig;

            RectTransform area = rivers[rel];
            UiFactory.DestroyChildren(area);
            TileSize size = TileSizes.Small;
            int cols = RiverColsFor(rel);
            for (int i = 0; i < discards.Length; i++)
            {
                int c = i % cols;
                int r = i / cols;
                var t = TileView.CreateFace(area, discards[i], size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f),
                    new Vector2(c * (size.width + RiverGap), -r * (size.height + RiverGap)), size.Vector);
                if (highlightLast && i == discards.Length - 1) TileView.AddRing(t, Palette.LastDiscardRing, size, 4);
            }
        }

        // ----- Action bar -----

        void RenderActions(GameView v, bool isFinal)
        {
            var list = new List<OptionDto>();
            if (isFinal && CanAct)
            {
                OptionDto[] opts = DtoUtil.Safe(v.options);
                for (int i = 0; i < opts.Length; i++)
                {
                    OptionDto o = opts[i];
                    if (o == null || o.type == "discard" || o.type == "next") continue;
                    list.Add(o);
                }
            }

            var sb = new StringBuilder();
            for (int i = 0; i < list.Count; i++) sb.Append(list[i].id).Append('=').Append(list[i].label).Append(';');
            string sig = sb.ToString();
            if (sig == actionSig) return;
            actionSig = sig;
            UiFactory.DestroyChildren(actionBar);

            // Right-aligned, laid out from the right edge leftwards; "pass" ends up right-most.
            float x = 0f;
            for (int i = list.Count - 1; i >= 0; i--)
            {
                OptionDto o = list[i];
                string label = string.IsNullOrEmpty(o.label) ? o.id : o.label;
                float width = Mathf.Clamp(70f + label.Length * 34f, 150f, 360f);
                var btn = UiFactory.CreateButton(actionBar, "Action_" + o.id, label, ColorFor(o.type), 34, null);
                UiFactory.Place((RectTransform)btn.transform, new Vector2(1f, 0f), new Vector2(1f, 0f), new Vector2(-x, 0f), new Vector2(width, 84f));
                if (o.type == "tsumo" || o.type == "ron")
                {
                    UiFactory.CreateRing(btn.transform, "Glow", Palette.LastDiscardRing, 26, 4, 4f);
                    UiFactory.ButtonLabel(btn).fontStyle = FontStyle.Bold;
                }
                string id = o.id;
                btn.onClick.AddListener(() => OnOptionClicked(id));
                x += width + 14f;
            }
        }

        static Color ColorFor(string type)
        {
            switch (type)
            {
                case "tsumo":
                case "ron":
                    return Palette.Coral;
                case "pass":
                    return Palette.Gray;
                case "chi":
                    return Palette.Butter;
                default:
                    return Palette.Sky;
            }
        }

        // ---------- Input ----------

        void OnTileClicked(int index)
        {
            if (!CanAct) return;
            if (index < 0 || index >= handOrder.Count) return;
            string code = handOrder[index];
            OptionDto opt = DtoUtil.FindOption(view, "discard:" + code);
            if (opt == null) return;

            if (selectedIndex == index)
            {
                Send(opt.id);
                return;
            }
            selectedIndex = index;
            RenderMyHand(DtoUtil.Player(view, view.mySeat), view);
            RenderHint(view);
        }

        void OnOptionClicked(string actionId)
        {
            if (!CanAct) return;
            if (DtoUtil.FindOption(view, actionId) == null) return;
            Send(actionId);
        }

        void Send(string actionId)
        {
            if (!app.SendAction(actionId)) return;
            awaiting = true; // until the next "state"
            selectedIndex = -1;
            Render(view, true);
        }

        void OnNextHand()
        {
            if (view == null || awaiting || pumping) return;
            OptionDto next = DtoUtil.FindOption(view, "next");
            if (app.SendAction(next != null ? next.id : "next"))
            {
                awaiting = true;
                resultPanel.SetNextPending();
            }
        }

        void OnBackToLobby()
        {
            app.LeaveTable();
        }

        void OnLeave()
        {
            app.LeaveTable();
        }
    }
}

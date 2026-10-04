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
        const float SidePanelH = 540f;
        const int RiverColsWide = 10;   // bottom / top rivers
        const int RiverColsNarrow = 8;  // left / right rivers
        const float RiverGap = 2f;
        const float SelectLift = 20f;

        // Fixed geometry of my hand (reference 1920x1080, bottom-left origin). Tiles never move when a tile is
        // drawn: slot i is at HandStartX + i * SlotStep, the drawn tile always sits in the separate drawn slot.
        const float HandStartX = 296f;
        const float HandY = 20f;
        const float SlotGap = 4f;
        const float SlotStep = 75f + SlotGap;       // TileSizes.Large.width + gap
        const int MaxSlots = 17;
        const float DrawnGap = 24f;
        const float DrawnSlotX = MaxSlots * SlotStep - SlotGap + DrawnGap; // relative to HandStartX
        const float HandAreaW = DrawnSlotX + 75f;
        const float MyMeldsY = 152f;
        // Waits hint bar (bottom-left, above my flowers, left of the bottom river, below the left seat panel).
        const float HintY = 222f;
        const float HintW = 700f;
        const float HintH = 50f;
        const float HintTallH = 88f;
        const float MyMeldsW = 1000f;
        // Opposite seat: fixed left edge for its concealed row and melds (relative to the screen centre).
        const float TopRowX = -260f;
        // Action panel: bottom-right offset; above the hand's right part, right of my melds, below the right seat.
        static readonly Vector2 ActionPanelOffset = new Vector2(-24f, 160f);

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

        ActionPanel actionPanel;
        /// <summary>聽 toggled on: mark every ready discard and list them all in the hint bar.</summary>
        bool tingOn;

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

            actionPanel = ActionPanel.Create(root, ActionPanelOffset, OnOptionClicked, OnToggleTing);

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
                    s.flowers = MakeArea("Seat0Flowers", root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(24f, 140f), new Vector2(8f * TileSizes.Mini.width, TileSizes.Mini.height));
                    s.melds = MakeArea("Seat0Melds", root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(HandStartX, MyMeldsY), new Vector2(MyMeldsW, TileSizes.Small.height));
                    s.hand = MakeArea("Seat0Hand", root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(HandStartX, HandY), new Vector2(HandAreaW, TileSizes.Large.height + SelectLift));
                    break;
                case 2: // opposite, top
                    s.info = MakeArea("Seat2Info", root, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(-560f, -20f), new Vector2(InfoW, InfoH));
                    s.flowers = MakeArea("Seat2Flowers", root, new Vector2(0.5f, 1f), new Vector2(0f, 1f), new Vector2(-560f - InfoW * 0.5f, -136f), new Vector2(8f * TileSizes.Mini.width, TileSizes.Mini.height));
                    s.hand = MakeArea("Seat2Hand", root, new Vector2(0.5f, 1f), new Vector2(0f, 1f), new Vector2(TopRowX, -20f), new Vector2(MaxSlots * (TileSizes.Back.width + 1f), TileSizes.Back.height));
                    s.melds = MakeArea("Seat2Melds", root, new Vector2(0.5f, 1f), new Vector2(0f, 1f), new Vector2(TopRowX, -64f), new Vector2(780f, TileSizes.Mini.height));
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
                    s.hand = MakeArea("Hand", panel, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, -170f), new Vector2(innerW, 3f * (TileSizes.Back.height + 2f)));
                    s.melds = MakeArea("Melds", panel, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(10f, -292f), new Vector2(innerW, 5f * (TileSizes.Mini.height + 4f)));
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
            UiFactory.Place(hintBar.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(24f, HintY), new Vector2(HintW, HintH));
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
            if (actionPanel != null) actionPanel.Fold();
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
            tingOn = false;
            actionPanel.Fold();
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
            actionPanel.Apply(v, isFinal && CanAct, tingOn);

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

        /// <summary>"打 五萬：聽 三筒（剩 2）、六筒（剩 3）；打 七條：聽 …" for every ready discard.</summary>
        static string AllReadyDiscards(GameView v)
        {
            var sb = new StringBuilder();
            var seen = new HashSet<string>();
            OptionDto[] opts = DtoUtil.Safe(v.options);
            for (int i = 0; i < opts.Length; i++)
            {
                OptionDto o = opts[i];
                if (o == null || o.type != "discard" || DtoUtil.Safe(o.waits).Length == 0 || !seen.Add(o.tile)) continue;
                if (sb.Length > 0) sb.Append('；');
                sb.Append("打 ").Append(TileFace.Name(o.tile)).Append("：聽 ").Append(FormatWaits(o.waits));
            }
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
                else if (tingOn && AnyDiscardWaits(v))
                {
                    text = AllReadyDiscards(v);
                    listening = true;
                }
                else if (AnyDiscardWaits(v))
                {
                    text = "有「聽」標記的牌，打出後就會聽牌（按「聽」全部顯示）";
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
            // Two lines (taller bar, growing upward) only for the full 聽 list; it stays below the left seat panel.
            bool twoLines = tingOn && canDiscard && selectedIndex < 0;
            hintBar.rectTransform.sizeDelta = new Vector2(HintW, twoLines ? HintTallH : HintH);
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
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(i * size.width, 0f), size.Vector); // fixed grid, 8 flowers = 8 widths
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
                sb.Append(melds[i].type).Append(':').Append(string.Join(",", DtoUtil.Safe(melds[i].tiles))).Append('@').Append(melds[i].claimedIndex).Append(';');
            }
            string sig = sb.ToString();
            if (sig == s.meldSig) return;
            s.meldSig = sig;
            UiFactory.DestroyChildren(s.melds);

            if (rel == 0) LayoutMelds(s.melds, melds, TileSizes.Small, 12f);
            else if (rel == 2) LayoutMelds(s.melds, melds, TileSizes.Mini, 10f);
            else LayoutMelds(s.melds, melds, TileSizes.Mini, 10f);
        }

        /// <summary>
        /// Lays melds out from the area's fixed top-left corner, left to right, wrapping to a new row only when the
        /// next meld would cross the area's right edge. Earlier melds never move when a new one is added.
        /// </summary>
        static void LayoutMelds(RectTransform area, MeldDto[] melds, TileSize size, float groupGap)
        {
            float areaW = area.sizeDelta.x;
            float x = 0f;
            float y = 0f;
            for (int i = 0; i < melds.Length; i++)
            {
                MeldDto m = melds[i];
                if (m == null || DtoUtil.Safe(m.tiles).Length == 0) continue;
                float w = TileView.MeldWidth(m, size);
                if (x > 0f && x + w > areaW)
                {
                    x = 0f;
                    y -= size.height + 4f;
                }
                RectTransform box = TileView.CreateMeld(area, m, size);
                UiFactory.Place(box, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, y), box.sizeDelta);
                x += w + groupGap;
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
                // Single row from a fixed left edge (not re-centred when the count changes).
                float step = size.width + 1f;
                for (int i = 0; i < count; i++)
                {
                    var t = TileView.CreateBack(s.hand, size);
                    UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(i * step, 0f), size.Vector);
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
                tingOn = false;
            }
            string sig = contentSig + "#" + selectedIndex + "#" + tingOn;
            if (sig == s.handSig) return;
            s.handSig = sig;
            UiFactory.DestroyChildren(s.hand);

            handOrder.Clear();
            handOrder.AddRange(sorted);
            if (drawn.Length > 0) handOrder.Add(drawn);
            if (selectedIndex >= handOrder.Count) selectedIndex = -1;

            TileSize size = TileSizes.Large;
            int n = handOrder.Count;

            for (int i = 0; i < n; i++)
            {
                string code = handOrder[i];
                bool isDrawn = drawn.Length > 0 && i == n - 1;
                // Fixed slots from the left edge; the drawn tile always goes to the separate drawn slot.
                float x = isDrawn ? DrawnSlotX : i * SlotStep;

                var slot = UiFactory.CreateRect("Slot" + i, s.hand);
                UiFactory.Place(slot, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(x, 0f), size.Vector);

                var tile = TileView.CreateFace(slot, code, size);
                bool selected = i == selectedIndex;
                UiFactory.Place(tile, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(0f, selected ? SelectLift : 0f), size.Vector);

                OptionDto opt = canDiscard ? DtoUtil.FindOption(v, "discard:" + code) : null;
                bool discardable = opt != null;
                if (canDiscard && !discardable) TileView.AddVeil(tile, size);
                if (selected) TileView.AddRing(tile, Palette.SelectRing, size, 4);
                bool readyDiscard = discardable && DtoUtil.Safe(opt.waits).Length > 0;
                if (readyDiscard && tingOn) TileView.AddRing(tile, Palette.Coral, size, 5);
                if (readyDiscard) AddWaitBadge(tile, size);

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
            // Pokes 10 units above the tile top so a lifted tile's badge stays below my meld row.
            UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 0f), new Vector2(0f, -18f), new Vector2(40f, 28f));
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

        void OnToggleTing()
        {
            if (!CanAct) return;
            tingOn = !tingOn;
            RenderMyHand(DtoUtil.Player(view, view.mySeat), view);
            RenderHint(view);
            actionPanel.Apply(view, CanAct, tingOn);
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

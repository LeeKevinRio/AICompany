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
    /// My hand: tiles can be selected at any time during a hand and dragged to reorder (see HandTileDrag); a player-made
    /// order is kept until the next hand and reconciled against every new view. Declared-ready (報聽) hands only select.
    /// Dragging a tile mostly upwards past 90 units and releasing plays it (discard, or ting in the picker); every move of
    /// a tile on screen is a short UiTween (the slots themselves stay at their fixed coordinates).
    /// Table dressing: a green baize (tiled felt + vignette) inside a wooden frame, with an electric-table console in the
    /// middle (round / hand number, wall count, dealer / turn lamps). The other seats' tiles are on the table in a compact ring:
    /// console, the four rivers hugging it (6 per row), then each seat's lane of concealed tiles and melds at the felt edge,
    /// and an info card + flowers station in every corner; the right / left seats are the same layout turned by 90 degrees. Chi / pon / kan / ting / win steps play a big action
    /// word next to the acting seat (ActionFx) and hold the playback for it; the new meld flashes briefly.
    /// </summary>
    public class TableScreen : MonoBehaviour
    {
        const float StepDelay = 0.35f;
        const float HandStartDelay = 0.8f;
        const float WinDelay = ActionFx.WinSeconds;
        const float ActionDelay = ActionFx.ActionSeconds; // another seat's chi / pon / kan / ting: the effect's whole life
        const float OwnActionDelay = 0.12f;               // my own: the effect plays on its own, my next state must not wait
        const float FastDelay = 0.08f;
        const int FastForwardQueueLength = 6;

        // ---------- Table and seat layout ----------
        // A compact ring around the console, from the middle outward: the console, the four rivers hugging it, each seat's lane
        // (concealed tiles and melds) at the felt edge, and a station (info card + flowers) in every corner of the ring.
        // The images in Resources/Table are generated for exactly these numbers and tools/render_table.py checks the whole
        // layout (every melds count, a 30 tile river, 8 flowers) for overlaps. The frame's bottom edge is at y = 270, above the
        // strip that holds the waits hint (left) and the action panel (right); my hand is below that strip.
        const float TableW = 836f;
        const float TableH = 798f;
        const float TableCenterY = 129f;   // table centre above the screen centre
        const float TableWood = 30f;       // width of the wood rail
        const float TableShadow = 48f;     // transparent margin of frame.png that holds its drop shadow
        const float FeltBleed = 8f;        // the baize runs this far under the rail so no gap can show
        const float FeltHalfW = (TableW - 2f * TableWood) * 0.5f;   // 388
        const float FeltHalfH = (TableH - 2f * TableWood) * 0.5f;   // 369
        // Console in the middle of the felt, as wide as a river row (top-left origin inside; the numbers match render_table.py).
        const float ConsoleW = 208f;
        const float ConsoleH = 170f;
        const float ConsoleShadow = 20f;
        const float LampSize = 24f;
        const float LampDist = 26f;

        // Every seat is laid out in its own frame: u runs along the seat's table edge (the seat's left to right), v from that
        // edge toward the table centre; the frame's origin is the left end of the edge. The right / left seats are the same frame
        // turned +90 / -90 degrees (their tiles stand rotated, like on a real table). The opposite seat keeps its tiles upright:
        // its frame sits at the felt's top-right corner with u running toward the screen's left (its own right hand) and v down.
        // Rows, from the edge: lane (concealed tiles from the seat's left, melds from its right end), river. The lane follows the
        // river: 8 units outside its outer row, never closer than 2 rows, one row (46) further out whenever the river reaches a new row
        // (3rd, 4th, 5th) or when the lane's content needs a longer lane than that ring has room for (so two lanes never cross).
        // Within a hand it only moves out, so each seat's lane moves at most three times.
        const float RiverStepX = 35f;      // TileSizes.Mini.width + 2
        const float RiverStepY = 46f;      // TileSizes.Mini.height + 2
        const int RiverCols = 6;           // tiles per row, row 0 touches the console and later rows grow outward
        const int RiverRows = 5;           // rows reserved: 30 tiles; the 31st and later keep going sideways in the outermost row
        const float RiverW = RiverCols * RiverStepX - 2f;   // 208
        const float RiverH = RiverRows * RiverStepY - 2f;   // 228
        const float RiverVOut = 52f;       // outer edge of the river block, measured from the felt edge
        const float LaneV = 6f;            // outer edge of the lane when the river has all 5 rows (the lane's furthest-out place)
        const float LaneGap = 8f;
        const int LaneMinRows = 2;         // the lane never stands closer than behind 2 river rows
        const float BackPitch = 25f;       // TileSizes.SeatBack.width (the concealed tiles stand touching)
        const int OtherHandSlots = 17;
        const float OtherHandWinGap = 10f; // the winning tile of a finished hand sits this far after the last concealed tile
        const float OtherHandW = OtherHandSlots * BackPitch + OtherHandWinGap + 25f;   // 460
        const float MeldGroupGap = 6f;
        const float MeldsAreaW = 5f * (4f * 29f - 1f) + 4f * MeldGroupGap;               // five kongs: 599
        // Info card (100 x 172) and flowers (2 columns x 4 rows) of a seat stand outside the frame, next to its corner:
        // |x| from the table centre (the frame's half width is 418), |y| of the card's edge nearest the middle.
        const float StationCardW = 100f;
        const float StationCardH = 172f;
        const float StationCardX = 502f;   // inner edge of the card
        const float StationCardY = 180f;
        const float StationFlowerX = 434f; // inner edge of the flowers
        const float FlowerStepX = 29f;
        const float FlowerStepY = 39f;
        const float SelectLift = 20f;
        // Swipe-up-to-play gesture (UI units of travel since the press). Armed above SwipeThreshold, disarmed again
        // below SwipeRelease (hysteresis, so the cue does not flicker at the border).
        const float SwipeThreshold = 90f;
        const float SwipeRelease = 80f;
        const float RubberFactor = 0.3f; // a tile that cannot be played only follows the finger this much ...
        const float RubberMax = 28f;     // ... up to this far, then springs back on release
        const float FlyDistance = 160f;
        const float NewTileRise = 12f;    // a tile that arrives in the hand rises this far while fading in
        const float LongTravel = 300f;    // above this horizontal glide distance a slot uses the long, in-out curve ...
        const float LongTravelMax = 1300f; // ... and takes up to LongDuration
        const float LongDuration = 0.30f;

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
        // Waits hint bar: bottom-left strip between my hand and the table (y 164 .. 268, the table's frame starts at 270),
        // left of the action panel. It grows upward: 50 (one text line), 79 / 88 (chips / two text lines), at most 104
        // (chips plus the detail line).
        const float HintY = 164f;
        const float HintW = 700f;
        const float HintH = 50f;
        const float HintTallH = 88f;         // text mode, two lines
        const float HintChipsH = 79f;        // chip mode, one row: 7 + 66 + 6
        const float HintChipsTallH = 104f;   // chip mode with the detail line: 7 + 66 + 3 + 24 + 4
        const float HintLabelW = 118f;
        const float HintPad = 14f;
        // Action panel: bottom-right offset; the strip above the hand's right part and below the table (y 160 .. 270).
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
            /// <summary>River rows the lane stands behind (0 = not placed yet); never decreases within a hand.</summary>
            public int laneK;
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
        /// <summary>The felt / frame / console images were found (otherwise the old plain mint table is drawn).</summary>
        bool textured;
        RectTransform lampLayer;
        string lampSig;

        ActionPanel actionPanel;
        /// <summary>聽 pressed: the declare-ready tile picker is on (only tiles with a "ting:" option can be picked).</summary>
        bool tingOn;

        Image hintBar;
        Image hintRing;
        /// <summary>Text mode: one or two lines filling the bar.</summary>
        Text hintText;
        /// <summary>Chip mode (waits as tile pictures): label + caption on the left, the chip row, an optional detail line below.</summary>
        Text hintLabel;
        Text hintCaption;
        RectTransform hintChips;
        Text hintDetail;
        string hintChipSig;

        GameObject connectionBanner;
        Text connectionText;
        ConnectionState connectionState = ConnectionState.Ready;

        ResultPanel resultPanel;

        readonly Queue<QueuedItem> queue = new Queue<QueuedItem>();
        GameView view;
        bool lastRenderFinal;
        bool pumping;
        bool playing;
        bool awaiting;
        bool fastForward;
        int selectedIndex = -1;
        /// <summary>Kind of the selected hand tile; every visible copy on the table is highlighted ("" = none).</summary>
        string highlightCode = "";
        string laneHandKey = "";
        string myHandContentSig;
        string myTilesSig;
        bool prevCanDiscard;
        bool prevDeclared;
        /// <summary>My hand as displayed, left to right; when drawnSeparate the last entry sits in the drawn slot.</summary>
        readonly List<string> handOrder = new List<string>();
        bool drawnSeparate;

        // Player-made hand order (tile codes, left to right). null = the server's sorting. Kept until the next hand
        // (gameId / handNo change); every new view is reconciled against it (see Reconcile).
        List<string> customOrder;
        string orderKey = "";
        /// <summary>The drawn tile the player dragged into the hand ("" = none); only valid while it is still the drawn tile.</summary>
        string mergedDrawn = "";
        readonly List<RectTransform> handSlots = new List<RectTransform>();
        int dragIndex = -1;
        float dragGrabX;

        enum DragKind { Reorder, Swipe }
        /// <summary>Locked when the drag starts: mostly upwards = swipe gesture, otherwise reorder.</summary>
        DragKind dragKind;
        Vector2 dragPress;
        /// <summary>Action the swipe would send ("discard:x" / "ting:x"); null when this tile cannot be played now.</summary>
        string swipeId;
        bool swipeArmed;
        UiTween swipeCue;

        // Tile played by swipe: its slot stays empty until the server answers (see RenderMyHand).
        int hiddenHandIndex = -1;
        string hiddenSig = "";
        /// <summary>Hand as built last time (codes, drawn-slot flag): lets a rebuild carry on-screen positions over.</summary>
        readonly List<string> builtCodes = new List<string>();
        bool builtDrawn;
        /// <summary>Set around the rebuild after a reorder: new index -> old index, matched first (see MatchOldTiles).</summary>
        List<int> pendingCarry;
        /// <summary>Top layer for tiles flying out of the hand; survives hand rebuilds.</summary>
        RectTransform flyLayer;
        /// <summary>Action words (吃 碰 槓 聽 胡 ...): above the table, below the result panel; never takes clicks.</summary>
        RectTransform fxLayer;
        readonly ActionFxAnim[] activeFx = new ActionFxAnim[4];

        // ---------- Build ----------

        public void Init(AppController owner)
        {
            app = owner;
            root = (RectTransform)transform;

            // Transparent full-screen catcher behind everything: clicking empty space cancels the selection.
            var catcher = UiFactory.CreateBlocker(root, "DeselectCatcher", Palette.Transparent);
            var catcherBtn = catcher.gameObject.AddComponent<Button>();
            catcherBtn.transition = Selectable.Transition.None;
            var catcherNav = catcherBtn.navigation;
            catcherNav.mode = Navigation.Mode.None;
            catcherBtn.navigation = catcherNav;
            catcherBtn.onClick.AddListener(ClearSelection);

            BuildTable();
            for (int rel = 0; rel < 4; rel++) seats[rel] = BuildSeat(rel);
            BuildTopBar();
            BuildHintBar();

            actionPanel = ActionPanel.Create(root, ActionPanelOffset, OnOptionClicked, OnToggleTing);

            BuildConnectionBanner();

            fxLayer = UiFactory.CreateRect("FxLayer", root);
            UiFactory.Stretch(fxLayer);

            resultPanel = new ResultPanel();
            resultPanel.Build(root);

            flyLayer = UiFactory.CreateRect("FlyLayer", root);
            UiFactory.Stretch(flyLayer);
        }

        void BuildTable()
        {
            Vector2 mid = new Vector2(0.5f, 0.5f);
            tableArea = UiFactory.CreateRect("Table", root);
            UiFactory.Place(tableArea, mid, mid, new Vector2(0f, TableCenterY), new Vector2(TableW, TableH));

            Sprite felt = TableArt.Get("felt");
            Sprite shade = TableArt.Get("felt_shade");
            Sprite frame = TableArt.Get("frame");
            Sprite consoleBody = TableArt.Get("console");
            textured = felt != null && shade != null && frame != null;
            if (textured)
            {
                // Baize (tiled, one texel per canvas unit) a little larger than the opening, its vignette over it, then
                // the wooden frame on top (its own drop shadow and inner shadow are baked in; the opening is transparent).
                float openW = TableW - 2f * TableWood;
                float openH = TableH - 2f * TableWood;
                var feltImg = UiFactory.CreateSpriteImage(tableArea, "Felt", felt, Image.Type.Tiled);
                UiFactory.Place(feltImg.rectTransform, mid, mid, Vector2.zero, new Vector2(openW + 2f * FeltBleed, openH + 2f * FeltBleed));
                var shadeImg = UiFactory.CreateSpriteImage(tableArea, "FeltShade", shade, Image.Type.Simple);
                UiFactory.Place(shadeImg.rectTransform, mid, mid, Vector2.zero, new Vector2(openW, openH));
                var frameImg = UiFactory.CreateSpriteImage(tableArea, "Frame", frame, Image.Type.Simple);
                UiFactory.Place(frameImg.rectTransform, mid, mid, Vector2.zero, new Vector2(TableW + 2f * TableShadow, TableH + 2f * TableShadow));
            }
            else
            {
                var plain = UiFactory.CreatePanel(tableArea, "Plain", Palette.Mint, 48);
                UiFactory.Stretch(plain.rectTransform);
                UiFactory.CreateRing(plain.transform, "Edge", Palette.MintDeep, 48, 8, 0f);
            }

            BuildConsole(consoleBody);
        }

        /// <summary>Places a child by its top-left corner inside the console (x right, y down), like the picture was drawn.</summary>
        static void PlaceInConsole(RectTransform rt, float x, float y, float w, float h)
        {
            UiFactory.Place(rt, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -y), new Vector2(w, h));
        }

        /// <summary>
        /// Electric-table console in the middle of the felt: a compass screen (one lamp per seat: gold "莊" = dealer, bright ring
        /// = whose turn it is), an info screen (round and hand number, wall count) and a strip for the turn prompt.
        /// The screens' rectangles are painted into console.png (tools/render_table.py SCREEN_*); without the image they are
        /// drawn as dark rounded panels.
        /// </summary>
        void BuildConsole(Sprite body)
        {
            Vector2 mid = new Vector2(0.5f, 0.5f);
            var console = UiFactory.CreateRect("Console", tableArea);
            UiFactory.Place(console, mid, mid, Vector2.zero, new Vector2(ConsoleW, ConsoleH));
            if (body != null)
            {
                var img = UiFactory.CreateSpriteImage(console, "Body", body, Image.Type.Simple);
                UiFactory.Stretch(img.rectTransform, -ConsoleShadow, -ConsoleShadow, -ConsoleShadow, -ConsoleShadow);
            }
            else
            {
                var bezel = UiFactory.CreatePanel(console, "Body", Palette.ConsoleBezel, 22);
                UiFactory.Stretch(bezel.rectTransform);
                AddConsoleScreen(console, 10f, 10f, 188f, 62f, 12);
                AddConsoleScreen(console, 10f, 78f, 84f, 84f, 14);
                AddConsoleScreen(console, 100f, 78f, 98f, 84f, 12);
            }

            // Info screen (round / hand, wall), compass screen (lamps), turn prompt screen (wraps over up to four lines).
            lampLayer = UiFactory.CreateRect("Lamps", console);
            PlaceInConsole(lampLayer, 10f, 78f, 84f, 84f);

            centerRound = UiFactory.CreateLabel(console, "Round", "", 22, Palette.ConsoleText, TextAnchor.MiddleLeft);
            centerRound.fontStyle = FontStyle.Bold;
            PlaceInConsole(centerRound.rectTransform, 16f, 12f, 176f, 28f);
            centerWall = UiFactory.CreateLabel(console, "Wall", "", 22, Palette.ConsoleGold, TextAnchor.MiddleLeft);
            PlaceInConsole(centerWall.rectTransform, 16f, 40f, 176f, 28f);
            centerTurn = UiFactory.CreateLabel(console, "Turn", "", 18, Palette.ConsoleTextDim, TextAnchor.MiddleCenter);
            PlaceInConsole(centerTurn.rectTransform, 104f, 80f, 90f, 80f);
        }

        static void AddConsoleScreen(RectTransform console, float x, float y, float w, float h, int radius)
        {
            var screen = UiFactory.CreatePanel(console, "Screen", Palette.ConsoleScreen, radius);
            PlaceInConsole(screen.rectTransform, x, y, w, h);
        }

        /// <summary>
        /// The four lamps on the compass screen, one per relative seat (0 me at the bottom, 1 right, 2 opposite at the top,
        /// 3 left): the dealer's lamp is gold and reads "莊", the others show their seat wind; the lamp of the seat whose turn it
        /// is gets a bright ring (and turns mint unless it is the dealer's). Unlit lamps are dark green with dim text, so the
        /// state is never colour alone. Rebuilt only when something it shows changes.
        /// </summary>
        void RenderLamps(GameView v)
        {
            var sb = new StringBuilder();
            sb.Append(v.mySeat).Append('|').Append(v.dealerSeat).Append('|').Append(v.phase == "playing" ? v.turnSeat : -1);
            for (int seat = 0; seat < 4; seat++)
            {
                PlayerView p = DtoUtil.Player(v, seat);
                sb.Append('|').Append(p != null ? p.seatWind : "");
            }
            string sig = sb.ToString();
            if (sig == lampSig) return;
            lampSig = sig;
            UiFactory.DestroyChildren(lampLayer);

            Vector2 mid = new Vector2(0.5f, 0.5f);
            for (int seat = 0; seat < 4; seat++)
            {
                PlayerView p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                int rel = (seat - v.mySeat + 4) % 4;
                bool dealer = seat == v.dealerSeat;
                bool turn = v.phase == "playing" && seat == v.turnSeat;
                Vector2 offset = rel == 0 ? new Vector2(0f, -LampDist)
                    : rel == 1 ? new Vector2(LampDist, 0f)
                    : rel == 2 ? new Vector2(0f, LampDist)
                    : new Vector2(-LampDist, 0f);

                Color fill = dealer ? Palette.ConsoleGold : (turn ? Palette.Mint : Palette.LampOff);
                var lamp = UiFactory.CreatePanel(lampLayer, "Lamp" + rel, fill, 8);
                UiFactory.Place(lamp.rectTransform, mid, mid, offset, new Vector2(LampSize, LampSize));
                if (turn) UiFactory.CreateRing(lamp.transform, "TurnRing", Palette.ConsoleText, 9, 2, 2f);
                var t = UiFactory.CreateLabel(lamp.transform, "Text", dealer ? "莊" : TileFace.WindName(p.seatWind), 17,
                    dealer || turn ? Palette.Ink : Palette.LampOffText, TextAnchor.MiddleCenter);
                t.fontStyle = FontStyle.Bold;
                UiFactory.Stretch(t.rectTransform, 1f, 1f, 1f, 1f);
            }
        }

        static RectTransform MakeArea(string name, Transform parent, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            var rt = UiFactory.CreateRect(name, parent);
            UiFactory.Place(rt, anchor, pivot, pos, size);
            return rt;
        }

        // Seat geometry (u along the seat's edge, v from the edge toward the centre; see the constants' comment).
        static float EdgeLength(int rel)
        {
            return rel == 0 || rel == 2 ? FeltHalfW * 2f : FeltHalfH * 2f;
        }

        /// <summary>
        /// Length a lane may use when it stands behind k river rows, measured from the middle of the seat's edge toward its left end
        /// (the concealed tiles) and toward its right end (the melds). The four corners are a pinwheel: at each corner one seat's melds
        /// end meets the next seat's concealed end, so a lane may run long at its melds end (321) while its concealed end stays short
        /// (183); at 5 rows it is the lane at the felt edge and may use 340 each way. No two lanes cross for any pair of k
        /// (tools/render_table.py check_layout).
        /// </summary>
        static float LaneBackHalf(int k) { return k >= RiverRows ? 340f : 183f; }
        static float LaneMeldHalf(int k) { return k >= RiverRows ? 340f : 321f; }

        /// <summary>Distance of the lane's outer edge from the felt edge: 144 behind 2 rows, 98 behind 3, 52 behind 4, 6 behind 5.</summary>
        static float LaneVAt(int k) { return LaneV + RiverStepY * (RiverRows - k); }

        static int RiverRowsUsed(int discards) { return Mathf.Min(RiverRows, (discards + RiverCols - 1) / RiverCols); }

        /// <summary>
        /// Length the lane's content needs: the concealed tiles of a hand with this many melds (17 - 3 per meld, at least 2, plus the
        /// gap of the winning tile), a gap, and the melds. My lane has no concealed tiles (my hand is below the table).
        /// </summary>
        static float LaneNeed(int rel, MeldDto[] melds)
        {
            int count = 0;
            float used = 0f;
            for (int i = 0; i < melds.Length; i++)
            {
                if (melds[i] == null) continue;
                int n = DtoUtil.Safe(melds[i].tiles).Length;
                if (n == 0) continue;
                used += n * 29f - 1f;
                count++;
            }
            used += MeldGroupGap * Mathf.Max(0, count - 1);
            if (rel == 0) return used;
            float backs = Mathf.Max(2, OtherHandSlots - 3 * count) * BackPitch + OtherHandWinGap - 1f;
            return backs + (count > 0 ? 8f + used : 0f);
        }

        /// <summary>River rows the lane stands behind (3 .. 5).</summary>
        static int LaneRows(int rel, PlayerView p)
        {
            int k = Mathf.Max(LaneMinRows, RiverRowsUsed(DtoUtil.Safe(p.discards).Length));
            float need = LaneNeed(rel, DtoUtil.Safe(p.melds));
            while (k < RiverRows && LaneBackHalf(k) + LaneMeldHalf(k) < need) k++;
            return k;
        }

        /// <summary>Anchored position of the lower-left corner of the area u .. u + w, v .. v + h in a seat frame.</summary>
        static Vector2 SeatAreaPos(int rel, float u, float v, float w, float h)
        {
            return rel == 2 ? new Vector2(-(u + w), -(v + h)) : new Vector2(u, v);
        }

        /// <summary>
        /// Position (left edge) of an item inside an area of a seat frame. The opposite seat's u runs toward the screen's left, so
        /// its items are mirrored inside the area (the area itself is placed by MakeSeatArea).
        /// </summary>
        static float AreaX(int rel, float areaW, float x, float w)
        {
            return rel == 2 ? areaW - x - w : x;
        }

        /// <summary>
        /// The frame of one seat on the table: origin at the left end of the seat's edge, turned +90 (right seat) or -90 degrees
        /// (left seat); the opposite seat's origin is the felt's top-right corner, unrotated.
        /// </summary>
        RectTransform CreateSeatFrame(int rel)
        {
            var frame = UiFactory.CreateRect("Seat" + rel + "Frame", tableArea);
            Vector2 origin;
            float angle = 0f;
            switch (rel)
            {
                case 0: origin = new Vector2(-FeltHalfW, -FeltHalfH); break;
                case 1: origin = new Vector2(FeltHalfW, -FeltHalfH); angle = 90f; break;
                case 2: origin = new Vector2(FeltHalfW, FeltHalfH); break;
                default: origin = new Vector2(-FeltHalfW, FeltHalfH); angle = -90f; break;
            }
            UiFactory.Place(frame, new Vector2(0.5f, 0.5f), Vector2.zero, origin, Vector2.zero);
            frame.localRotation = Quaternion.Euler(0f, 0f, angle);
            return frame;
        }

        /// <summary>
        /// An area u .. u + w, v .. v + h of a seat frame. Its children use top-left coordinates. The opposite seat counts u toward the
        /// screen's left and v downward from the felt's top edge, so its area's lower-left corner is at (-(u + w), -(v + h)).
        /// </summary>
        static RectTransform MakeSeatArea(RectTransform frame, int rel, string name, float u, float v, float w, float h)
        {
            var rt = UiFactory.CreateRect(name, frame);
            UiFactory.Place(rt, Vector2.zero, Vector2.zero, SeatAreaPos(rel, u, v, w, h), new Vector2(w, h));
            return rt;
        }

        /// <summary>The side (sign of x, sign of y) of a seat's station: me lower-left, right seat lower-right, opposite upper-right, left upper-left.</summary>
        static Vector2 StationCorner(int rel)
        {
            switch (rel)
            {
                case 0: return new Vector2(-1f, -1f);
                case 1: return new Vector2(1f, -1f);
                case 2: return new Vector2(1f, 1f);
                default: return new Vector2(-1f, 1f);
            }
        }

        SeatUi BuildSeat(int rel)
        {
            var s = new SeatUi();
            var frame = CreateSeatFrame(rel);
            float edge = EdgeLength(rel);
            Vector2 mid = new Vector2(0.5f, 0.5f);

            // River: touches the console, 6 tiles per row, row 0 innermost; centred on the console's side.
            rivers[rel] = MakeSeatArea(frame, rel, "River", edge * 0.5f - ConsoleW * 0.5f, RiverVOut, RiverW, RiverH);
            // Lane: melds from the seat's right end, the concealed tiles from its left end (my concealed tiles are my hand below the
            // table). Created at its outermost place; UpdateLane moves it behind the river as that grows.
            float uMax = edge * 0.5f + LaneMeldHalf(RiverRows);
            s.melds = MakeSeatArea(frame, rel, "Melds", uMax - MeldsAreaW, LaneV, MeldsAreaW, TileSizes.SeatMeld.height);
            if (rel == 0)
            {
                s.hand = MakeArea("Seat0Hand", root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(HandStartX, HandY), new Vector2(HandAreaW, TileSizes.Large.height + SelectLift));
            }
            else
            {
                s.hand = MakeSeatArea(frame, rel, "Hand", edge * 0.5f - LaneBackHalf(RiverRows), LaneV, OtherHandW, TileSizes.SeatBack.height);
            }

            // Station beside the frame: the info card on the outside, the flowers (2 x 4) on its inner side, top-aligned with the card.
            Vector2 corner = StationCorner(rel);
            s.info = MakeArea("Seat" + rel + "Info", tableArea, mid, mid,
                new Vector2(corner.x * (StationCardX + StationCardW * 0.5f), corner.y * (StationCardY + StationCardH * 0.5f)),
                new Vector2(StationCardW, StationCardH));
            float flowerW = 2f * FlowerStepX;
            float flowerH = 4f * FlowerStepY;
            float left = corner.x > 0f ? StationFlowerX : -(StationFlowerX + flowerW);
            float top = corner.y > 0f ? StationCardY + StationCardH : -StationCardY;
            s.flowers = MakeArea("Seat" + rel + "Flowers", tableArea, mid, new Vector2(0f, 1f), new Vector2(left, top), new Vector2(flowerW, flowerH));
            return s;
        }

        void BuildTopBar()
        {
            // Small, so it fits the margin beside the table (the table leaves at least 110 units on each side).
            var leave = UiFactory.CreateButton(root, "LeaveButton", "離開", Palette.Gray, 28, OnLeave);
            UiFactory.Place((RectTransform)leave.transform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(6f, -6f), new Vector2(100f, 56f));

            // Bottom-left, left of my hand.
            myCoinsText = UiFactory.CreateLabel(root, "MyCoins", "", 24, Palette.Ink, TextAnchor.MiddleLeft);
            UiFactory.Place(myCoinsText.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(26f, 24f), new Vector2(260f, 32f));
        }

        /// <summary>
        /// Waits hint at the bottom-left, in the band between the table frame and my hand. Two modes:
        /// chips (what I wait on as tile pictures with "剩 N", under a label "打出後聽" / "報聽後聽" / "聽牌中", plus an optional
        /// detail line for the selected tile) and plain text for everything else ("打出後未聽牌", the picker prompt ...).
        /// </summary>
        void BuildHintBar()
        {
            Vector2 topLeft = new Vector2(0f, 1f);
            hintBar = UiFactory.CreatePanel(root, "WaitHint", Palette.Card, 20);
            UiFactory.Place(hintBar.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(24f, HintY), new Vector2(HintW, HintH));
            UiFactory.AddShadow(hintBar, Palette.CardShadow, new Vector2(0f, -3f));
            hintRing = UiFactory.CreateRing(hintBar.transform, "Ring", Palette.Coral, 20, 3, 0f);
            hintText = UiFactory.CreateLabel(hintBar.transform, "Text", "", 26, Palette.Ink, TextAnchor.MiddleLeft);
            UiFactory.Stretch(hintText.rectTransform, 18f, 4f, 14f, 4f);

            hintLabel = UiFactory.CreateLabel(hintBar.transform, "Label", "", 24, Palette.Ink, TextAnchor.MiddleLeft);
            hintLabel.fontStyle = FontStyle.Bold;
            UiFactory.Place(hintLabel.rectTransform, topLeft, topLeft, new Vector2(HintPad, -14f), new Vector2(HintLabelW, 30f));
            hintCaption = UiFactory.CreateLabel(hintBar.transform, "Caption", "數字為剩餘張數", 16, Palette.InkSoft, TextAnchor.MiddleLeft);
            UiFactory.Place(hintCaption.rectTransform, topLeft, topLeft, new Vector2(HintPad, -46f), new Vector2(HintLabelW, 22f));
            hintChips = UiFactory.CreateRect("Chips", hintBar.transform);
            UiFactory.Place(hintChips, topLeft, topLeft, new Vector2(HintPad + HintLabelW, -7f),
                new Vector2(HintW - 2f * HintPad - HintLabelW, WaitChips.Height));
            hintDetail = UiFactory.CreateLabel(hintBar.transform, "Detail", "", 22, Palette.Ink, TextAnchor.MiddleLeft);
            UiFactory.Place(hintDetail.rectTransform, topLeft, topLeft, new Vector2(HintPad + 4f, -(7f + WaitChips.Height + 3f)),
                new Vector2(HintW - 2f * HintPad - 4f, 24f));
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
            ClearFx(); // the snapshot that follows is authoritative; nothing that was queued is replayed
            laneHandKey = ""; // and the lanes jump to where it puts them instead of gliding
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
            ClearFx();
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
            myTilesSig = null;
            prevCanDiscard = false;
            prevDeclared = false;
            handOrder.Clear();
            drawnSeparate = false;
            customOrder = null;
            orderKey = "";
            mergedDrawn = "";
            handSlots.Clear();
            dragIndex = -1;
            swipeCue = null;
            hiddenHandIndex = -1;
            builtCodes.Clear();
            builtDrawn = false;
            pendingCarry = null;
            if (flyLayer != null) UiFactory.DestroyChildren(flyLayer);
            tingOn = false;
            lampSig = null;
            hintChipSig = null;
            laneHandKey = "";
            ClearFx();
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
                    seats[i].laneK = 0;
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
            // Tap / click anywhere fast-forwards the queued playback, except on my hand tiles: selecting and
            // dragging them while the others play must not speed the playback up.
#if ENABLE_LEGACY_INPUT_MANAGER
            if (pumping && playing && !fastForward)
            {
                bool tapped = false;
                if (Input.GetMouseButtonDown(0)) tapped = !IsOverMyHandTile(Input.mousePosition);
                for (int i = 0; !tapped && i < Input.touchCount; i++)
                {
                    Touch touch = Input.GetTouch(i);
                    if (touch.phase == TouchPhase.Began && !IsOverMyHandTile(touch.position)) tapped = true;
                }
                if (tapped)
                {
                    fastForward = true;
                    ActionFx.DismissAll(fxLayer);
                }
            }
#endif
        }

        /// <summary>Screen point on one of my hand tiles (their slots and the lifted tiles inside). The canvas is screen-space overlay.</summary>
        bool IsOverMyHandTile(Vector2 screenPoint)
        {
            if (view == null || view.phase != "playing") return false;
            for (int i = 0; i < handSlots.Count; i++)
            {
                RectTransform slot = handSlots[i];
                if (slot == null) continue;
                if (RectTransformUtility.RectangleContainsScreenPoint(slot, screenPoint, null)) return true;
                if (slot.childCount > 0 &&
                    RectTransformUtility.RectangleContainsScreenPoint((RectTransform)slot.GetChild(0), screenPoint, null)) return true;
            }
            return false;
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
                    bool fast = IsFastPlayback;
                    if (fast) ActionFx.DismissAll(fxLayer);
                    if (step.view != null) Render(step.view, false);
                    FxKind fx = PlayStepFx(step, fast);

                    string type = step.@event != null ? step.@event.type : "";
                    bool mine = fx != FxKind.None && view != null && step.@event.seat == view.mySeat;
                    float elapsed = 0f;
                    while (elapsed < CurrentDelay(type, fx, mine))
                    {
                        // The effect plays on its own layer, so a state that lets me act never waits for it to finish: my own
                        // action's state is applied at once, another seat's once its pop-in is over. A win always holds in full.
                        if (fx != FxKind.None && !ActionFx.IsWin(fx) && NextStateIsActionable() &&
                            (mine || elapsed >= ActionFx.EnterSeconds)) break;
                        // Same clock and same per-frame cap as the effect itself (ActionFxAnim), so they stay in step on slow frames.
                        elapsed += Mathf.Min(Time.unscaledDeltaTime, ActionFx.MaxStep);
                        yield return null;
                    }
                    // A win's result panel must not cover its effect: wait until the effect is gone (a tap dismisses it in 0.1 s).
                    if (ActionFx.IsWin(fx) && view != null)
                    {
                        int winRel = (step.@event.seat - view.mySeat + 4) % 4;
                        while (activeFx[winRel] != null) yield return null;
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
        /// tell the player before applying it.
        /// </summary>
        void CheckGameChanged(GameView next)
        {
            if (next == null || view == null) return;
            if (string.IsNullOrEmpty(next.gameId) || string.IsNullOrEmpty(view.gameId) || next.gameId == view.gameId) return;
            app.ShowToast("牌局已重新開始");
            selectedIndex = -1;
        }

        /// <summary>Tap fast-forward, or so many steps queued up that the table must catch up: no effects, minimal holds.</summary>
        bool IsFastPlayback
        {
            get { return fastForward || queue.Count > FastForwardQueueLength; }
        }

        /// <summary>
        /// How long the step stays on screen before the next queue item. Another seat's chi / pon / kan / ting holds for the whole
        /// effect (0.70 s), a win for 1.2 s (the result panel only comes after it); my own action barely holds (0.12 s) because
        /// the effect runs on its own layer and my next state must be able to unlock input at once. Fast playback: 0.08 s.
        /// </summary>
        float CurrentDelay(string eventType, FxKind fx, bool mine)
        {
            if (IsFastPlayback) return FastDelay;
            if (eventType == "hand_start") return HandStartDelay;
            if (eventType == "win" || ActionFx.IsWin(fx)) return WinDelay;
            if (fx != FxKind.None) return mine ? OwnActionDelay : ActionDelay;
            return StepDelay;
        }

        /// <summary>The next queue item is the authoritative state of my own turn (it carries options): apply it right away.</summary>
        bool NextStateIsActionable()
        {
            if (queue.Count == 0) return false;
            GameView next = queue.Peek().state;
            return next != null && next.phase == "playing" && DtoUtil.HasOptions(next);
        }

        // ---------- Action effects ----------

        /// <summary>
        /// Starts the action word for this step (and the new meld's outline) next to the acting seat. Skipped, but still reported
        /// for the hold time, while playback is fast. One effect per seat at a time: a new one replaces the old at once.
        /// </summary>
        FxKind PlayStepFx(StepDto step, bool fast)
        {
            FxKind kind = ActionFx.KindOf(step);
            if (kind == FxKind.None) return kind;
            GameView v = step.view != null ? step.view : view;
            if (v == null || fast || fxLayer == null || !gameObject.activeInHierarchy) return kind;

            int seat = step.@event.seat;
            int rel = (seat - v.mySeat + 4) % 4;
            PlayerView p = DtoUtil.Player(v, seat);
            if (activeFx[rel] != null) activeFx[rel].Dismiss(); // the old one fades out (0.1 s) instead of being cut
            activeFx[rel] = ActionFx.Spawn(fxLayer, kind, rel, p != null ? DtoUtil.Safe(p.name) : "");
            if (!ActionFx.IsWin(kind) && kind != FxKind.Ting) FlashNewMeld(step.@event, p, rel);
            return kind;
        }

        /// <summary>
        /// Outlines the meld the event just made: the last meld of the seat (a kakan: the upgraded meld of that tile). The meld
        /// boxes of the seat's area are in meld order and the freshly built ones are its last children (the old ones are only
        /// destroyed at the end of the frame), so the box is found counting from the end.
        /// </summary>
        void FlashNewMeld(EventDto e, PlayerView p, int rel)
        {
            if (p == null) return;
            MeldDto[] melds = DtoUtil.Safe(p.melds);
            int valid = 0;
            int target = -1;
            for (int i = 0; i < melds.Length; i++)
            {
                MeldDto m = melds[i];
                if (m == null || DtoUtil.Safe(m.tiles).Length == 0) continue;
                bool match = e.type != "kakan" || (m.type == "kakan" && System.Array.IndexOf(DtoUtil.Safe(m.tiles), e.tile) >= 0);
                if (match) target = valid;
                valid++;
            }
            RectTransform area = seats[rel].melds;
            if (target < 0 || area == null) return;
            int index = area.childCount - valid + target;
            if (index < 0 || index >= area.childCount) return;
            var box = area.GetChild(index) as RectTransform;
            if (box != null && box.name.StartsWith("Meld_")) ActionFx.FlashMeld(box);
        }

        void ClearFx()
        {
            if (fxLayer != null) UiFactory.DestroyChildren(fxLayer);
            for (int i = 0; i < activeFx.Length; i++) activeFx[i] = null;
        }

        /// <summary>I have declared ready (報聽): my hand is locked, tile clicks only select.</summary>
        static bool IsDeclared(GameView v)
        {
            PlayerView p = DtoUtil.Player(v, v != null ? v.mySeat : 0);
            return p != null && p.declared;
        }

        /// <summary>My turn to discard and clicking a tile may send "discard:" (never once declared).</summary>
        bool CanDiscardByTile
        {
            get { return CanAct && DtoUtil.HasDiscardOption(view) && !IsDeclared(view); }
        }

        /// <summary>The declare-ready tile picker is on and still valid for the current options.</summary>
        bool TingPicking
        {
            get { return tingOn && CanAct && DtoUtil.HasOptionType(view, "ting"); }
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
            string handKey = DtoUtil.Safe(v.gameId) + "|" + v.handNo;
            if (handKey != laneHandKey)
            {
                // A new hand: every lane starts over behind its river (no glide across hands).
                laneHandKey = handKey;
                for (int i = 0; i < 4; i++)
                {
                    if (seats[i] != null) seats[i].laneK = 0;
                }
            }

            // My hand first: it settles the selection and therefore which kind is highlighted everywhere else.
            PlayerView mine = DtoUtil.Player(v, mySeat);
            if (mine != null) RenderMyHand(mine, v);
            else highlightCode = "";

            for (int seat = 0; seat < 4; seat++)
            {
                int rel = (seat - mySeat + 4) % 4;
                PlayerView p = DtoUtil.Player(v, seat);
                if (p == null) continue;
                RenderInfo(rel, p, v);
                RenderFlowers(rel, p, v);
                RenderMelds(rel, p);
                if (rel != 0) RenderOtherHand(rel, p, v);
                RenderRiver(rel, p, v);
                UpdateLane(rel, p);
            }

            RenderCenter(v);
            RenderHint(v);
            myCoinsText.text = "我的金幣 " + Format.Coins(v.myCoins);
            actionPanel.Apply(v, isFinal && CanAct, tingOn, IsDeclared(v));

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
                if (TingPicking) turn = "報聽：點一張有「聽」的牌，再點一次";
                else if (CanDiscardByTile) turn = "輪到你：點一張牌，再點一次打出";
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
            centerTurn.color = CanAct ? Palette.ConsoleText : Palette.ConsoleTextDim;
            RenderLamps(v);
        }

        // ----- Waits hint -----

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
            string text = "";          // text mode
            string label = "";         // chip mode: label and the waits to draw
            WaitDto[] chips = null;
            string detail = "";        // second line: what the selected tile looks like on the table
            bool listening = false;
            bool canDiscard = CanDiscardByTile;
            string sel = selectedIndex >= 0 && selectedIndex < handOrder.Count ? handOrder[selectedIndex] : "";
            string stats = sel.Length > 0
                ? TileFace.Name(sel) + "：場上已出現 " + CountOnTable(v, sel) + " 張，你手上 " + CountInHand(sel) + " 張"
                : "";

            if (TingPicking)
            {
                // Declare-ready picker: only tiles with a "ting:" option can be picked.
                OptionDto ting = sel.Length > 0 ? DtoUtil.FindOption(v, "ting:" + sel) : null;
                if (ting != null)
                {
                    if (WaitChips.Valid(ting.waits).Count > 0)
                    {
                        label = "報聽後聽";
                        chips = DtoUtil.Safe(ting.waits);
                    }
                    else
                    {
                        text = "報聽打出這張";
                    }
                    detail = stats;
                }
                else
                {
                    text = "選一張打出並聽牌（再按聽取消）";
                }
                listening = true;
            }
            else if (canDiscard)
            {
                if (sel.Length > 0)
                {
                    OptionDto opt = DtoUtil.FindOption(v, "discard:" + sel);
                    WaitDto[] waits = opt != null ? DtoUtil.Safe(opt.waits) : new WaitDto[0];
                    if (WaitChips.Valid(waits).Count > 0)
                    {
                        label = "打出後聽";
                        chips = waits;
                        listening = true;
                    }
                    else
                    {
                        text = "打出後未聽牌";
                    }
                    detail = stats;
                }
                else if (AnyDiscardWaits(v))
                {
                    text = DtoUtil.HasOptionType(v, "ting")
                        ? "有「聽」標記的牌，打出後就會聽牌（按「聽」報聽）"
                        : "有「聽」標記的牌，打出後就會聽牌";
                }
            }
            else if (v.phase == "playing")
            {
                // Not choosing a discard (waiting, declared, someone else's turn): standing waits plus the selected tile's counts.
                if (WaitChips.Valid(v.myWaits).Count > 0)
                {
                    label = "聽牌中";
                    chips = DtoUtil.Safe(v.myWaits);
                    listening = true;
                    detail = stats;
                }
                else
                {
                    text = stats;
                }
            }

            bool chipMode = chips != null;
            bool show = chipMode || text.Length > 0 || detail.Length > 0;
            hintBar.gameObject.SetActive(show);
            if (!show) return;
            hintRing.gameObject.SetActive(listening);

            hintText.gameObject.SetActive(!chipMode);
            hintLabel.gameObject.SetActive(chipMode);
            hintCaption.gameObject.SetActive(chipMode);
            hintChips.gameObject.SetActive(chipMode);
            hintDetail.gameObject.SetActive(chipMode && detail.Length > 0);

            float height;
            if (chipMode)
            {
                // Chips are rebuilt only when what they show changed. Two rows (taller bar, growing upward) only for the detail line.
                hintLabel.text = label;
                string chipSig = label + "|" + WaitChips.Signature(chips);
                if (chipSig != hintChipSig)
                {
                    hintChipSig = chipSig;
                    WaitChips.Build(hintChips, chips);
                }
                hintDetail.text = detail;
                height = detail.Length > 0 ? HintChipsTallH : HintChipsH;
            }
            else
            {
                hintChipSig = null;
                bool twoLines = text.Length > 0 && detail.Length > 0;
                hintText.text = twoLines ? text + "\n" + detail : (text.Length > 0 ? text : detail);
                hintText.fontStyle = listening ? FontStyle.Bold : FontStyle.Normal;
                height = twoLines ? HintTallH : HintH;
            }
            hintBar.rectTransform.sizeDelta = new Vector2(HintW, height);
        }

        /// <summary>
        /// Visible copies of a kind on the table: every river plus every meld's face-up tiles (a concealed kong's
        /// two face-down tiles are not counted). Flowers are a different kind and never match.
        /// </summary>
        static int CountOnTable(GameView v, string code)
        {
            int n = 0;
            PlayerView[] players = DtoUtil.Safe(v.players);
            for (int i = 0; i < players.Length; i++)
            {
                PlayerView p = players[i];
                if (p == null) continue;
                string[] discards = DtoUtil.Safe(p.discards);
                for (int k = 0; k < discards.Length; k++)
                {
                    if (discards[k] == code) n++;
                }
                MeldDto[] melds = DtoUtil.Safe(p.melds);
                for (int k = 0; k < melds.Length; k++) n += TileView.VisibleCount(melds[k], code);
            }
            return n;
        }

        int CountInHand(string code)
        {
            int n = 0;
            for (int i = 0; i < handOrder.Count; i++)
            {
                if (handOrder[i] == code) n++;
            }
            return n;
        }

        // ----- Lanes -----

        /// <summary>
        /// Places the seat's lane (its melds and, for the others, its concealed tiles) behind its river: when the river reaches its
        /// 3rd / 4th / 5th row, or the content needs a longer lane, the lane glides one row further out (180 ms, strong ease-out; with
        /// reduced motion it jumps). The first placement of a hand jumps. These are the other seats' tiles; my own hand never moves.
        /// </summary>
        void UpdateLane(int rel, PlayerView p)
        {
            SeatUi s = seats[rel];
            int k = Mathf.Max(LaneRows(rel, p), s.laneK);
            if (k == s.laneK) return;
            bool first = s.laneK == 0;
            s.laneK = k;
            float edge = EdgeLength(rel);
            float v = LaneVAt(k);
            MoveLaneArea(s.melds, SeatAreaPos(rel, edge * 0.5f + LaneMeldHalf(k) - MeldsAreaW, v, MeldsAreaW, TileSizes.SeatMeld.height), first);
            if (rel != 0) MoveLaneArea(s.hand, SeatAreaPos(rel, edge * 0.5f - LaneBackHalf(k), v, OtherHandW, TileSizes.SeatBack.height), first);
        }

        static void MoveLaneArea(RectTransform area, Vector2 target, bool jump)
        {
            UiTween tween = TweenOf(area);
            if (jump) tween.SetPosition(target);
            else tween.SlideTo(target, UiMotion.Settle);
        }

        // ----- Info card -----

        /// <summary>
        /// The seat's corner card (100 x 172), top to bottom: avatar, name, seat wind, dealer (with streak), the session result with
        /// a caption. Declared ready (報聽): the coral "聽" sticker over the avatar's lower right. Whose turn it is: an orange
        /// ring around the card. Rows are at fixed places whether or not the dealer row is filled.
        /// </summary>
        void RenderInfo(int rel, PlayerView p, GameView v)
        {
            SeatUi s = seats[rel];
            bool isDealer = p.seat == v.dealerSeat;
            bool isTurn = v.phase == "playing" && p.seat == v.turnSeat;
            string sig = p.name + "|" + p.avatar + "|" + p.seatWind + "|" + isDealer + "|" + v.dealerStreak + "|" + p.sessionDelta + "|" + isTurn + "|" + p.declared;
            if (sig == s.infoSig) return;
            s.infoSig = sig;
            UiFactory.DestroyChildren(s.info);

            var card = UiFactory.CreatePanel(s.info, "Card", Palette.Card, 22);
            UiFactory.Stretch(card.rectTransform);
            UiFactory.AddShadow(card, Palette.CardShadow, new Vector2(0f, -4f));
            if (isTurn) UiFactory.CreateRing(card.transform, "TurnRing", Palette.TurnRing, 24, 4, 3f);

            Vector2 topCenter = new Vector2(0.5f, 1f);
            var avatar = UiFactory.CreateAvatar(card.transform, p.avatar, 44f);
            UiFactory.Place(avatar, topCenter, topCenter, new Vector2(0f, -6f), new Vector2(44f, 44f));

            var name = UiFactory.CreateLabel(card.transform, "Name", p.name, 22, Palette.Ink, TextAnchor.MiddleCenter);
            name.fontStyle = FontStyle.Bold;
            UiFactory.Place(name.rectTransform, topCenter, topCenter, new Vector2(0f, -52f), new Vector2(92f, 24f));

            CompactBadge(card.transform, TileFace.WindName(p.seatWind) + "家", Palette.Sky, -78f, 58f);
            if (isDealer) CompactBadge(card.transform, v.dealerStreak > 0 ? "莊·連" + v.dealerStreak : "莊", Palette.DealerBadge, -102f, v.dealerStreak > 0 ? 84f : 40f);

            var caption = UiFactory.CreateLabel(card.transform, "DeltaCaption", "本場", 16, Palette.InkSoft, TextAnchor.MiddleCenter);
            UiFactory.Place(caption.rectTransform, topCenter, topCenter, new Vector2(0f, -128f), new Vector2(92f, 18f));
            var delta = UiFactory.CreateLabel(card.transform, "Delta", Format.Signed(p.sessionDelta), 22, Palette.Ink, TextAnchor.MiddleCenter);
            delta.fontStyle = FontStyle.Bold;
            delta.color = p.sessionDelta > 0 ? Palette.Gain : (p.sessionDelta < 0 ? Palette.Loss : Palette.InkSoft);
            UiFactory.Place(delta.rectTransform, topCenter, topCenter, new Vector2(0f, -145f), new Vector2(94f, 24f));

            if (p.declared)
            {
                var pill = UiFactory.CreatePanel(card.transform, "DeclaredBadge", Palette.Coral, 13);
                UiFactory.Place(pill.rectTransform, topCenter, topCenter, new Vector2(22f, -30f), new Vector2(40f, 26f));
                UiFactory.CreateRing(pill.transform, "Ring", Palette.LastDiscardRing, 13, 3, 0f);
                var t = UiFactory.CreateLabel(pill.transform, "Text", "聽", 20, Palette.Ink, TextAnchor.MiddleCenter);
                t.fontStyle = FontStyle.Bold;
                UiFactory.Stretch(t.rectTransform, 2f, 1f, 2f, 1f);
            }
        }

        /// <summary>Centred pill of the card at the given y (top of the card = 0).</summary>
        static void CompactBadge(Transform card, string text, Color bg, float y, float width)
        {
            var pill = UiFactory.CreatePanel(card, "Badge", bg, 11);
            UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, y), new Vector2(width, 22f));
            var t = UiFactory.CreateLabel(pill.transform, "Text", text, 18, Palette.Ink, TextAnchor.MiddleCenter);
            UiFactory.Stretch(t.rectTransform, 3f, 0f, 3f, 0f);
        }

        // ----- Flowers -----

        void RenderFlowers(int rel, PlayerView p, GameView v)
        {
            SeatUi s = seats[rel];
            string[] flowers = DtoUtil.Safe(p.flowers);
            // Flower win (八仙過海 / 七搶一): the winning flower is marked here instead of next to the hand.
            WinSplit split = WinSplit.For(v, p, null, TileFace.IsFlower(v.hasResult && v.result != null ? v.result.winningTile : ""));
            string mark = split.IsFlowerWin ? split.WinningTile + "@" + split.FlowerIndex : "";
            string sig = string.Join(",", flowers) + "|" + mark;
            if (sig == s.flowerSig) return;
            s.flowerSig = sig;
            UiFactory.DestroyChildren(s.flowers);

            TileSize size = TileSizes.SeatMeld;
            for (int i = 0; i < flowers.Length; i++)
            {
                var t = TileView.CreateFace(s.flowers, flowers[i], size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), FlowerCell(i), size.Vector); // fixed 2 x 4 grid
                if (split.IsFlowerWin && i == split.FlowerIndex) MarkWinningTile(t, size, split.SelfDraw, 4f);
            }
            if (split.IsFlowerWin && split.FlowerIndex < 0)
            {
                // The winner does not hold that flower (七搶一: they hold 7, someone else drew the 8th): show it in
                // the next flower cell, which is still inside the fixed 8-cell flower grid.
                var t = TileView.CreateFace(s.flowers, split.WinningTile, size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), FlowerCell(Mathf.Min(flowers.Length, 7)), size.Vector);
                MarkWinningTile(t, size, split.SelfDraw, 4f);
            }
        }

        /// <summary>Top-left position of flower cell i in the 2 column x 4 row grid of a corner station.</summary>
        static Vector2 FlowerCell(int i)
        {
            return new Vector2((i % 2) * FlowerStepX, -(i / 2) * FlowerStepY);
        }

        /// <summary>Winning tile: thick coral outline plus a "胡" / "自摸" badge.</summary>
        static void MarkWinningTile(RectTransform tile, TileSize size, bool selfDraw, float badgeAbove)
        {
            MarkWinningTile(tile, size, selfDraw, badgeAbove, -1);
        }

        /// <summary>
        /// Winning tile in a seat's lane (rel 1 .. 3): the badge sits just outside the tile, on the side away from the table centre
        /// (it never covers a neighbouring tile or the face), and is always upright on screen: the right / left seats' frames are
        /// turned by +-90 degrees, so their badge is turned back. rel -1: flowers / my own tiles, the badge pokes over the tile's top.
        /// </summary>
        static void MarkWinningTile(RectTransform tile, TileSize size, bool selfDraw, float badgeAbove, int rel)
        {
            TileView.AddRing(tile, Palette.LastDiscardRing, size, Mathf.Max(3, Mathf.RoundToInt(size.width / 15f)));
            string text = selfDraw ? "自摸" : "胡";
            if (rel == 1) TileView.AddBadgeBeside(tile, text, Palette.Coral, size, false, -90f);
            else if (rel == 3) TileView.AddBadgeBeside(tile, text, Palette.Coral, size, false, 90f);
            else if (rel == 2) TileView.AddBadgeBeside(tile, text, Palette.Coral, size, true, 0f);
            else TileView.AddBadge(tile, text, Palette.Coral, badgeAbove);
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
            sb.Append('#').Append(highlightCode);
            string sig = sb.ToString();
            if (sig == s.meldSig) return;
            s.meldSig = sig;
            UiFactory.DestroyChildren(s.melds);

            LayoutMelds(s.melds, rel, melds, TileSizes.SeatMeld, highlightCode);
        }

        /// <summary>
        /// Lays the melds out in one row from the seat's right end (the area's end in u), first meld outermost, each later one
        /// next to it toward the concealed tiles; earlier melds never move when a new one is added. The area is wide enough for
        /// five kongs. The opposite seat's u runs toward the screen's left, so its row is mirrored (AreaX).
        /// </summary>
        static void LayoutMelds(RectTransform area, int rel, MeldDto[] melds, TileSize size, string highlight)
        {
            float areaW = area.sizeDelta.x;
            float used = 0f;
            for (int i = 0; i < melds.Length; i++)
            {
                MeldDto m = melds[i];
                if (m == null || DtoUtil.Safe(m.tiles).Length == 0) continue;
                float w = TileView.MeldWidth(m, size);
                RectTransform box = TileView.CreateMeld(area, m, size, highlight);
                float u = areaW - used - w;   // left edge along u; a mirrored row starts at its left end
                UiFactory.Place(box, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(AreaX(rel, areaW, u, w), 0f), box.sizeDelta);
                used += w + MeldGroupGap;
            }
        }

        // ----- Hands -----

        void RenderOtherHand(int rel, PlayerView p, GameView v)
        {
            SeatUi s = seats[rel];
            List<string> revealed = TileFace.Sorted(p.hand); // only non-empty at hand end
            WinSplit split = WinSplit.For(v, p, revealed, TileFace.IsFlower(v.hasResult && v.result != null ? v.result.winningTile : ""));
            bool showWin = split.HasWinningTile && !split.IsFlowerWin;
            string sig = p.handCount + "|" + string.Join(",", split.Hand) + "|" + (showWin ? split.WinningTile : "");
            if (sig == s.handSig) return;
            s.handSig = sig;
            UiFactory.DestroyChildren(s.hand);

            TileSize size = TileSizes.SeatBack;
            int count = revealed.Count > 0 ? split.Hand.Count : Mathf.Max(0, p.handCount);
            count = Mathf.Min(count, OtherHandSlots);
            for (int i = 0; i < count; i++)
            {
                RectTransform t = revealed.Count > 0 ? TileView.CreateFace(s.hand, split.Hand[i], size) : TileView.CreateBack(s.hand, size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(AreaX(rel, OtherHandW, i * BackPitch, size.width), 0f), size.Vector);
            }
            if (showWin)
            {
                // Right after the last concealed tile, with a gap: the revealed hand is final, nothing moves afterwards.
                var t = TileView.CreateFace(s.hand, split.WinningTile, size);
                float x = count * BackPitch + OtherHandWinGap;
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(AreaX(rel, OtherHandW, x, size.width), 0f), size.Vector);
                MarkWinningTile(t, size, split.SelfDraw, 4f, rel);
            }
        }

        void RenderMyHand(PlayerView p, GameView v)
        {
            SeatUi s = seats[0];
            List<string> sorted = TileFace.Sorted(p.hand);
            string drawn = DtoUtil.Safe(p.drawnTile);
            bool declared = p.declared;
            bool canDiscard = CanAct && DtoUtil.HasDiscardOption(v) && !declared;
            bool tingMode = tingOn && CanAct && DtoUtil.HasOptionType(v, "ting");
            bool interactive = v.phase == "playing";

            // Hand end: if I won, take the winning tile out of the revealed hand and show it in the drawn slot.
            string winTile = "";
            bool winSelfDraw = false;
            if (v.phase != "playing")
            {
                WinSplit split = WinSplit.For(v, p, sorted, TileFace.IsFlower(v.hasResult && v.result != null ? v.result.winningTile : ""));
                if (split.HasWinningTile && !split.IsFlowerWin)
                {
                    sorted = split.Hand;
                    winTile = split.WinningTile;
                    winSelfDraw = split.SelfDraw;
                    drawn = "";
                }
            }

            // A new hand (gameId / handNo changed): forget the player's own order, back to the server's sorting.
            string key = DtoUtil.Safe(v.gameId) + "|" + v.handNo;
            if (key != orderKey)
            {
                orderKey = key;
                customOrder = null;
                mergedDrawn = "";
                builtCodes.Clear(); // a new hand: none of the old tiles is the same tile, nothing glides over
            }

            // The drawn tile stays in its own slot unless the player dragged it into the hand.
            var pool = new List<string>(sorted);
            string separate = drawn;
            if (drawn.Length > 0 && mergedDrawn == drawn)
            {
                pool.Add(drawn);
                separate = "";
            }
            else
            {
                mergedDrawn = "";
            }

            List<string> ordered = pool;
            if (customOrder != null)
            {
                ordered = Reconcile(customOrder, pool);
                customOrder.Clear();
                customOrder.AddRange(ordered);
            }
            handOrder.Clear();
            handOrder.AddRange(ordered);
            drawnSeparate = separate.Length > 0;
            if (drawnSeparate) handOrder.Add(separate);

            // The selection survives anything that leaves my tiles alone (e.g. other seats playing), but not a
            // changed hand, or the turn switching between "only select" and "click again to discard".
            var tb = new StringBuilder();
            for (int i = 0; i < sorted.Count; i++) tb.Append(sorted[i]).Append(',');
            tb.Append('|').Append(drawn).Append("|win:").Append(winTile);
            string tilesSig = tb.ToString();
            if (tilesSig != myTilesSig || canDiscard != prevCanDiscard || declared != prevDeclared || !interactive)
            {
                selectedIndex = -1;
            }
            myTilesSig = tilesSig;
            prevCanDiscard = canDiscard;
            prevDeclared = declared;

            // A tile played by swipe stays hidden only while the server has not answered. If the answer left my tiles
            // as they were (e.g. ILLEGAL_ACTION), the tile comes back (faded in) and the flying copy is dropped.
            int restoreIndex = -1;
            if (hiddenHandIndex >= 0 && (!awaiting || tilesSig != hiddenSig))
            {
                if (tilesSig == hiddenSig && hiddenHandIndex < handOrder.Count)
                {
                    restoreIndex = hiddenHandIndex;
                    if (flyLayer != null) UiFactory.DestroyChildren(flyLayer);
                }
                hiddenHandIndex = -1;
            }

            var sb = new StringBuilder(tilesSig);
            sb.Append('|').Append(canDiscard).Append('|').Append(declared).Append('|');
            OptionDto[] opts = DtoUtil.Safe(v.options);
            for (int i = 0; i < opts.Length; i++)
            {
                if (opts[i] != null && (opts[i].type == "discard" || opts[i].type == "ting"))
                {
                    sb.Append(opts[i].id).Append('/').Append(DtoUtil.Safe(opts[i].waits).Length).Append(';');
                }
            }
            string contentSig = sb.ToString();

            // Options changed: the declare-ready picker from the previous options is meaningless now.
            if (contentSig != myHandContentSig)
            {
                myHandContentSig = contentSig;
                tingOn = false;
                tingMode = false;
            }
            if (selectedIndex >= handOrder.Count) selectedIndex = -1;
            highlightCode = selectedIndex >= 0 ? handOrder[selectedIndex] : "";

            string sig = contentSig + "#" + string.Join(",", handOrder) + "#" + selectedIndex + "#" + tingMode + "#" + interactive + "#" + drawnSeparate + "#h" + hiddenHandIndex;
            if (sig == s.handSig) return;
            s.handSig = sig;
            dragIndex = -1; // a drag in progress dies with its tile
            swipeCue = null;

            // Where every old tile is on screen right now (also mid-glide). A slot that is gone (destroyed) or empty (tile
            // played, waiting for the server) is not a usable source.
            int oldCount = handSlots.Count;
            var oldSlotPos = new Vector2[oldCount];
            var oldTilePos = new Vector2[oldCount];
            var oldUsable = new bool[oldCount];
            int oldUsableCount = 0;
            for (int k = 0; k < oldCount; k++)
            {
                RectTransform old = handSlots[k];
                if (old == null) continue; // destroyed
                oldSlotPos[k] = old.anchoredPosition;
                if (old.childCount == 0) continue; // hidden (played) tile
                oldTilePos[k] = ((RectTransform)old.GetChild(0)).anchoredPosition;
                oldUsable[k] = true;
                oldUsableCount++;
            }
            // Pair every new tile with the old tile it is: the rebuilt tile starts at that tile's on-screen position and
            // glides to its fixed slot (tiles closing ranks after a discard, a drawn tile sliding into the hand). Nothing
            // is carried over in a new hand or when the hand is no longer playable (hand end).
            List<int> hint = pendingCarry;
            if (restoreIndex >= 0)
            {
                // The tile came back (ILLEGAL_ACTION): everything else stays exactly where it was.
                hint = new List<int>(handOrder.Count);
                for (int i = 0; i < handOrder.Count; i++) hint.Add(i == restoreIndex ? -1 : i);
            }
            int[] srcOf = interactive ? MatchOldTiles(handOrder, oldUsable, hint) : MatchOldTiles(new List<string>(), oldUsable, null);
            // Tiles with no predecessor ease in instead of popping, but only within a hand: the deal (builtCodes was just
            // cleared by a new hand) and the very first build show the whole hand at once.
            bool fadeNew = interactive && oldUsableCount > 0 && builtCodes.Count > 0;
            handSlots.Clear();
            UiFactory.DestroyChildren(s.hand);

            TileSize size = TileSizes.Large;
            int n = handOrder.Count;

            for (int i = 0; i < n; i++)
            {
                string code = handOrder[i];
                bool isDrawn = drawnSeparate && i == n - 1;
                // Fixed slots from the left edge; the drawn tile always goes to the separate drawn slot.
                float x = isDrawn ? DrawnSlotX : i * SlotStep;

                int src = i < srcOf.Length ? srcOf[i] : -1;
                bool carry = src >= 0 && oldUsable[src];

                Vector2 slotTarget = new Vector2(x, 0f);
                var slot = UiFactory.CreateRect("Slot" + i, s.hand);
                UiFactory.Place(slot, new Vector2(0f, 0f), new Vector2(0f, 0f), carry ? oldSlotPos[src] : slotTarget, size.Vector);
                handSlots.Add(slot);
                var slotTween = slot.gameObject.AddComponent<UiTween>();
                if (carry) SlideSlot(slotTween, slotTarget);

                if (i == hiddenHandIndex) continue; // played: the flying copy stands in until the server answers

                var tile = TileView.CreateFace(slot, code, size);
                bool selected = i == selectedIndex;
                Vector2 tileTarget = new Vector2(0f, selected ? SelectLift : 0f);
                UiFactory.Place(tile, new Vector2(0f, 0f), new Vector2(0f, 0f), carry ? oldTilePos[src] : tileTarget, size.Vector);
                var tileTween = tile.gameObject.AddComponent<UiTween>();
                if (carry) tileTween.SlideTo(tileTarget, UiMotion.Settle);
                if (!carry && i == restoreIndex)
                {
                    tileTween.SetAlpha(0f);
                    tileTween.FadeTo(1f, UiMotion.Settle);
                }
                else if (!carry && fadeNew)
                {
                    // Arrives from slightly below while fading in (reduced motion: fade only).
                    if (!UiMotion.Reduced) tileTween.SetPosition(tileTarget + new Vector2(0f, -NewTileRise));
                    tileTween.SlideTo(tileTarget, UiMotion.Quick);
                    tileTween.SetAlpha(0f);
                    tileTween.FadeTo(1f, UiMotion.Quick);
                }

                OptionDto discardOpt = canDiscard ? DtoUtil.FindOption(v, "discard:" + code) : null;
                OptionDto tingOpt = tingMode ? DtoUtil.FindOption(v, "ting:" + code) : null;
                bool dimmed = tingMode ? tingOpt == null : canDiscard && discardOpt == null;
                if (dimmed) TileView.AddVeil(tile, size);
                if (selected) TileView.AddRing(tile, Palette.SelectRing, size, 4);
                else if (highlightCode.Length > 0 && code == highlightCode) TileView.AddSameKindHighlight(tile, size);
                // Marker: tiles whose discard leaves me ready (normal turn), or the tiles the 聽 picker accepts.
                bool ready = tingMode ? tingOpt != null : discardOpt != null && DtoUtil.Safe(discardOpt.waits).Length > 0;
                if (tingMode && tingOpt != null) TileView.AddRing(tile, Palette.Coral, size, 5);
                // Pokes 10 units above the tile top so a lifted tile's badge stays below my meld row.
                if (ready) TileView.AddBadge(tile, "聽", Palette.Coral, 10f);

                if (interactive)
                {
                    var img = tile.GetComponent<Image>();
                    img.raycastTarget = true;
                    var drag = tile.gameObject.AddComponent<HandTileDrag>();
                    drag.Index = i;
                    drag.Space = s.hand;
                    drag.Clicked = OnTileClicked;
                    drag.DragStarted = OnTileDragStarted;
                    drag.Dragged = OnTileDragged;
                    drag.DragEnded = OnTileDragEnded;
                }
            }

            builtCodes.Clear();
            builtCodes.AddRange(handOrder);
            builtDrawn = drawnSeparate;
            pendingCarry = null;

            if (winTile.Length > 0)
            {
                var slot = UiFactory.CreateRect("WinningTile", s.hand);
                UiFactory.Place(slot, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(DrawnSlotX, 0f), size.Vector);
                var tile = TileView.CreateFace(slot, winTile, size);
                UiFactory.Place(tile, new Vector2(0f, 0f), new Vector2(0f, 0f), Vector2.zero, size.Vector);
                TileView.AddRing(tile, Palette.LastDiscardRing, size, 5);
                TileView.AddBadge(tile, winSelfDraw ? "自摸" : "胡", Palette.Coral, 10f);
            }
        }

        /// <summary>
        /// Glides a rebuilt slot to its fixed position. Short moves (closing ranks, a dropped tile) use the usual 180 ms
        /// ease-out; a long one (the drawn tile joining the hand) is scaled with the distance, 180 ms at 300 units up to
        /// 300 ms at 1300, on the in-out curve so it reads as travelling across the hand rather than being flung.
        /// </summary>
        static void SlideSlot(UiTween tween, Vector2 target)
        {
            float travel = Mathf.Abs(((RectTransform)tween.transform).anchoredPosition.x - target.x);
            if (travel <= LongTravel)
            {
                tween.SlideTo(target, UiMotion.Settle);
                return;
            }
            float duration = Mathf.Lerp(UiMotion.Settle, LongDuration, Mathf.InverseLerp(LongTravel, LongTravelMax, travel));
            tween.SlideTo(target, duration, UiCurve.InOutStrong);
        }

        /// <summary>
        /// For every tile of the new hand, the index of the old tile it is (-1 = a new arrival). Identity is
        /// (tile code, n-th copy of that code): `hint` (new index -> old index, from a reorder drop or a restored tile)
        /// is honoured first where the codes agree; every remaining new tile takes the first unused old tile of the same
        /// code, in left-to-right order. Only old tiles that were actually on screen (oldUsable) can be matched, so a
        /// tile that was played and hidden never "moves". Works for the server's sorting and for a custom order alike.
        /// </summary>
        int[] MatchOldTiles(List<string> newCodes, bool[] oldUsable, List<int> hint)
        {
            var result = new int[newCodes.Count];
            for (int i = 0; i < result.Length; i++) result[i] = -1;
            var taken = new bool[oldUsable.Length];
            if (hint != null)
            {
                for (int i = 0; i < result.Length && i < hint.Count; i++)
                {
                    int h = hint[i];
                    if (h >= 0 && h < oldUsable.Length && h < builtCodes.Count && oldUsable[h] && !taken[h] && builtCodes[h] == newCodes[i])
                    {
                        result[i] = h;
                        taken[h] = true;
                    }
                }
            }
            var free = new Dictionary<string, Queue<int>>();
            for (int k = 0; k < oldUsable.Length && k < builtCodes.Count; k++)
            {
                if (!oldUsable[k] || taken[k]) continue;
                Queue<int> q;
                if (!free.TryGetValue(builtCodes[k], out q))
                {
                    q = new Queue<int>();
                    free[builtCodes[k]] = q;
                }
                q.Enqueue(k);
            }
            for (int i = 0; i < result.Length; i++)
            {
                if (result[i] >= 0) continue;
                Queue<int> q;
                if (free.TryGetValue(newCodes[i], out q) && q.Count > 0) result[i] = q.Dequeue();
            }
            return result;
        }

        /// <summary>
        /// Applies the player's own order to the tiles now in my hand (multiset match): tiles still held keep their
        /// relative order, tiles that left (discarded, claimed by a meld) drop out, and tiles that arrived are appended
        /// on the right in the server's sorted order.
        /// </summary>
        static List<string> Reconcile(List<string> order, List<string> pool)
        {
            var left = new Dictionary<string, int>();
            for (int i = 0; i < pool.Count; i++)
            {
                int c;
                left.TryGetValue(pool[i], out c);
                left[pool[i]] = c + 1;
            }
            var result = new List<string>(pool.Count);
            for (int i = 0; i < order.Count; i++)
            {
                int c;
                if (left.TryGetValue(order[i], out c) && c > 0)
                {
                    result.Add(order[i]);
                    left[order[i]] = c - 1;
                }
            }
            for (int i = 0; i < pool.Count; i++)
            {
                int c;
                if (left.TryGetValue(pool[i], out c) && c > 0)
                {
                    result.Add(pool[i]);
                    left[pool[i]] = c - 1;
                }
            }
            return result;
        }

        // ----- Hand drag (reorder) -----

        /// <summary>Hand-area tiles other than the dragged one (the separate drawn tile never counts as hand area).</summary>
        int DragOthersCount(bool fromDrawn)
        {
            int handArea = drawnSeparate ? handOrder.Count - 1 : handOrder.Count;
            return fromDrawn ? handArea : handArea - 1;
        }

        bool DraggedFromDrawn
        {
            get { return drawnSeparate && dragIndex == handOrder.Count - 1; }
        }

        /// <summary>Insert position (0..others) for a dragged tile whose left edge is at tileLeft; the drawn tile can also stay put.</summary>
        int DragTarget(float tileLeft, out bool backToDrawn)
        {
            bool fromDrawn = DraggedFromDrawn;
            int others = DragOthersCount(fromDrawn);
            float center = tileLeft + TileSizes.Large.width * 0.5f;
            backToDrawn = fromDrawn && tileLeft >= (others * SlotStep + DrawnSlotX) * 0.5f;
            return Mathf.Clamp(Mathf.FloorToInt(center / SlotStep), 0, Mathf.Max(0, others));
        }

        float DragLeft(Vector2 pointer)
        {
            return Mathf.Clamp(pointer.x + dragGrabX, -SlotStep * 0.5f, DrawnSlotX);
        }

        static UiTween TweenOf(RectTransform rt)
        {
            var t = rt.GetComponent<UiTween>();
            return t != null ? t : rt.gameObject.AddComponent<UiTween>();
        }

        RectTransform TileOf(int index)
        {
            if (index < 0 || index >= handSlots.Count || handSlots[index] == null || handSlots[index].childCount == 0) return null;
            return (RectTransform)handSlots[index].GetChild(0);
        }

        /// <summary>
        /// Action a swipe up on this tile would send, or null when it cannot be played right now (not my turn, playing,
        /// awaiting, declared, a tile the 聽 picker or the discard options dim).
        /// </summary>
        string SwipeActionId(int index)
        {
            if (view == null || view.phase != "playing" || index < 0 || index >= handOrder.Count) return null;
            string code = handOrder[index];
            OptionDto opt = null;
            if (TingPicking) opt = DtoUtil.FindOption(view, "ting:" + code);
            else if (CanDiscardByTile) opt = DtoUtil.FindOption(view, "discard:" + code);
            return opt != null ? opt.id : null;
        }

        /// <summary>
        /// A drag locks its meaning when it starts, from the first 12+ units of travel: mostly upwards = the swipe
        /// gesture (play the tile), anything else = reorder. Once locked, a reorder never turns into a play (and a
        /// swipe never reorders), so a drifting hand cannot play a tile by accident.
        /// </summary>
        void OnTileDragStarted(int index, Vector2 pressPoint, Vector2 current)
        {
            if (view == null || view.phase != "playing" || index < 0 || index >= handSlots.Count) return;
            if (dragIndex >= 0) return; // one drag at a time: a second finger must not hijack the first
            dragIndex = index;
            dragPress = pressPoint;
            swipeArmed = false;
            swipeCue = null;
            swipeId = SwipeActionId(index);
            RectTransform slot = handSlots[index];
            dragGrabX = slot.anchoredPosition.x - pressPoint.x; // from where it is shown now (it may still be gliding)
            slot.SetAsLastSibling(); // on top of its neighbours
            RectTransform tile = TileOf(index);
            Vector2 delta = current - pressPoint;
            dragKind = delta.y > Mathf.Abs(delta.x) ? DragKind.Swipe : DragKind.Reorder;
            if (tile == null) return;
            if (dragKind == DragKind.Reorder)
            {
                // Picked up: lifted like a selected tile.
                TweenOf(tile).SlideTo(new Vector2(0f, SelectLift), UiMotion.Quick);
            }
            else if (swipeId != null)
            {
                swipeCue = CreateSwipeCue(tile, TingPicking ? "放開報聽" : "放開出牌");
            }
        }

        /// <summary>
        /// Reorder: the dragged tile follows the pointer horizontally (directly, no easing) while the others glide
        /// aside (150 ms ease-out, retargeted from where they are whenever the gap moves). Swipe: see DragSwipe.
        /// </summary>
        void OnTileDragged(int index, Vector2 pointer)
        {
            if (dragIndex != index || index >= handSlots.Count) return;
            if (dragKind == DragKind.Swipe)
            {
                DragSwipe(index, pointer);
                return;
            }
            float left = DragLeft(pointer);
            TweenOf(handSlots[index]).SetPosition(new Vector2(left, 0f));

            bool backToDrawn;
            int target = DragTarget(left, out backToDrawn);
            int k = 0;
            for (int i = 0; i < handSlots.Count; i++)
            {
                if (i == index || (drawnSeparate && i == handOrder.Count - 1)) continue;
                int slotIndex = !backToDrawn && k >= target ? k + 1 : k;
                TweenOf(handSlots[i]).SlideTo(new Vector2(slotIndex * SlotStep, 0f), UiMotion.Shift);
                k++;
            }
        }

        /// <summary>Past the threshold, mostly upwards (with hysteresis once armed).</summary>
        bool SwipeInRange(Vector2 delta)
        {
            float limit = swipeArmed ? SwipeRelease : SwipeThreshold;
            return delta.y > limit && delta.y > Mathf.Abs(delta.x);
        }

        /// <summary>
        /// The tile follows the finger. Playable: past 90 units (and more up than sideways) the cue (orange frame and
        /// a "放開出牌" pill) fades in, back under 80 it fades out. Not playable: the tile only follows a third of the
        /// way (max 28 units, rubber band) with no cue, and springs back on release.
        /// </summary>
        void DragSwipe(int index, Vector2 pointer)
        {
            RectTransform tile = TileOf(index);
            if (tile == null) return;
            Vector2 d = pointer - dragPress;
            float baseY = selectedIndex == index ? SelectLift : 0f;
            Vector2 offset;
            if (swipeId != null)
            {
                offset = new Vector2(d.x, baseY + Mathf.Max(0f, d.y));
            }
            else
            {
                offset = new Vector2(Mathf.Clamp(d.x * RubberFactor, -RubberMax, RubberMax),
                    baseY + Mathf.Clamp(d.y * RubberFactor, 0f, RubberMax));
            }
            TweenOf(tile).SetPosition(offset);

            bool armed = swipeId != null && SwipeInRange(d);
            if (armed != swipeArmed)
            {
                swipeArmed = armed;
                if (swipeCue != null) swipeCue.FadeTo(armed ? 1f : 0f, UiMotion.Quick);
            }
        }

        /// <summary>"Release to play" cue on a tile: orange frame plus a pill above it, hidden until armed.</summary>
        static UiTween CreateSwipeCue(RectTransform tile, string label)
        {
            TileSize size = TileSizes.Large;
            var box = UiFactory.CreateRect("SwipeCue", tile);
            UiFactory.Stretch(box);
            TileView.AddRing(box, Palette.LastDiscardRing, size, 5);
            float w = 28f + 24f * label.Length;
            var pill = UiFactory.CreatePanel(box, "Pill", Palette.Coral, 14);
            UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 0f), new Vector2(0f, 14f), new Vector2(w, 34f));
            UiFactory.CreateRing(pill.transform, "Ring", Palette.LastDiscardRing, 14, 2, 0f);
            var text = UiFactory.CreateLabel(pill.transform, "Text", label, 24, Palette.Ink, TextAnchor.MiddleCenter);
            text.fontStyle = FontStyle.Bold;
            UiFactory.Stretch(text.rectTransform, 2f, 1f, 2f, 1f);
            var tween = box.gameObject.AddComponent<UiTween>();
            tween.PassThrough();
            tween.SetAlpha(0f);
            return tween;
        }

        void OnTileDragEnded(int index, Vector2 pointer)
        {
            if (dragIndex != index || view == null) return;
            if (dragKind == DragKind.Swipe)
            {
                EndSwipe(index);
                return;
            }
            bool backToDrawn;
            int target = DragTarget(DragLeft(pointer), out backToDrawn);
            bool fromDrawn = DraggedFromDrawn;
            int drawnOld = drawnSeparate ? handOrder.Count - 1 : -1;
            dragIndex = -1;

            // New order as a permutation of the old indices.
            var perm = new List<int>(handOrder.Count);
            for (int i = 0; i < handOrder.Count; i++)
            {
                if (i != index && i != drawnOld) perm.Add(i);
            }
            bool merged = fromDrawn && !backToDrawn;
            if (!fromDrawn || merged) perm.Insert(Mathf.Clamp(target, 0, perm.Count), index);
            bool stillSeparate = drawnOld >= 0 && !merged;
            if (stillSeparate) perm.Add(drawnOld);

            bool changed = merged;
            for (int i = 0; i < perm.Count && !changed; i++)
            {
                if (perm[i] != i) changed = true;
            }
            int newIndex = index;
            if (changed)
            {
                var codes = new List<string>(perm.Count);
                for (int i = 0; i < perm.Count; i++) codes.Add(handOrder[perm[i]]);
                if (merged) mergedDrawn = handOrder[index];
                if (stillSeparate) codes.RemoveAt(codes.Count - 1); // the drawn slot is not part of the custom order
                if (selectedIndex >= 0) selectedIndex = perm.IndexOf(selectedIndex); // the selection follows its tile
                customOrder = codes;
                pendingCarry = perm;
                newIndex = perm.IndexOf(index);
            }
            // Rebuild every slot (also when nothing changed). Each new slot starts at the position its tile is shown at
            // right now and glides home (180 ms ease-out), so the dropped tile slides into its slot instead of snapping.
            seats[0].handSig = null;
            Render(view, lastRenderFinal);
            pendingCarry = null;
            if (newIndex >= 0 && newIndex < handSlots.Count) handSlots[newIndex].SetAsLastSibling(); // glides over its neighbours
        }

        /// <summary>
        /// Release of a swipe. Armed (what the cue showed) and the tile still playable -> send the action; the tile leaves
        /// as a copy flying up. Otherwise the tile glides back (180 ms ease-out) and nothing is sent.
        /// </summary>
        void EndSwipe(int index)
        {
            RectTransform tile = TileOf(index);
            string id = swipeArmed ? SwipeActionId(index) : null; // re-checked: the table may have moved on during the drag
            bool fire = id != null && id == swipeId && tile != null;
            dragIndex = -1;
            if (fire)
            {
                if (SendTile(index, id))
                {
                    swipeCue = null;
                    return;
                }
                // not sent (connection gone): fall through to the glide back
            }
            if (tile != null) TweenOf(tile).SlideTo(new Vector2(0f, selectedIndex == index ? SelectLift : 0f), UiMotion.Settle);
            if (swipeCue != null) swipeCue.FadeTo(0f, UiMotion.Quick);
            swipeCue = null;
            swipeArmed = false;
        }

        /// <summary>
        /// Plays hand tile `index` (swipe release, or the second click): sends the action, hides the tile's slot until
        /// the server answers and lets a copy fly out from where the tile is shown right now (a selected tile is
        /// lifted, a swiped one is wherever the finger let go). False when nothing was sent (the tile stays).
        /// </summary>
        bool SendTile(int index, string actionId)
        {
            RectTransform tile = TileOf(index);
            if (tile == null || index >= handOrder.Count) return Send(actionId);
            string code = handOrder[index];
            Vector3 world = tile.position;
            hiddenHandIndex = index;
            hiddenSig = myTilesSig;
            if (Send(actionId))
            {
                SpawnFlyGhost(code, world);
                return true;
            }
            hiddenHandIndex = -1;
            return false;
        }

        /// <summary>
        /// A copy of the played tile that rises 160 units while fading out (220 ms, strong ease-out for travel and
        /// opacity). It lives on its own layer, so the hand rebuild that follows the send cannot touch it.
        /// Reduced motion: no travel, just a 100 ms fade.
        /// </summary>
        void SpawnFlyGhost(string code, Vector3 world)
        {
            if (flyLayer == null) return;
            TileSize size = TileSizes.Large;
            var ghost = TileView.CreateFace(flyLayer, code, size);
            UiFactory.Place(ghost, new Vector2(0f, 0f), new Vector2(0f, 0f), Vector2.zero, size.Vector);
            ghost.position = world;
            var tween = ghost.gameObject.AddComponent<UiTween>();
            tween.PassThrough();
            tween.DestroyWhenIdle();
            if (UiMotion.Reduced)
            {
                tween.FadeTo(0f, UiMotion.Quick);
                return;
            }
            tween.SlideTo(ghost.anchoredPosition + new Vector2(0f, FlyDistance), UiMotion.Exit);
            tween.FadeTo(0f, UiMotion.Exit);
        }

        // ----- River -----

        void RenderRiver(int rel, PlayerView p, GameView v)
        {
            string[] discards = DtoUtil.Safe(p.discards);
            bool highlightLast = discards.Length > 0 && v.lastDiscardSeat == p.seat &&
                                 discards[discards.Length - 1] == v.lastDiscardTile;
            string sig = string.Join(",", discards) + "|" + highlightLast + "|" + highlightCode;
            if (sig == riverSigs[rel]) return;
            riverSigs[rel] = sig;

            RectTransform area = rivers[rel];
            UiFactory.DestroyChildren(area);
            TileSize size = TileSizes.Mini;
            float areaH = area.sizeDelta.y;
            for (int i = 0; i < discards.Length; i++)
            {
                // Rows of 6 from the console outward (row 0 touches it); the 5th row has room to keep going sideways.
                int r = i < RiverCols * (RiverRows - 1) ? i / RiverCols : RiverRows - 1;
                int c = i < RiverCols * (RiverRows - 1) ? i % RiverCols : i - RiverCols * (RiverRows - 1);
                // The area's top is its console side, except for the opposite seat whose frame counts v downward: there the
                // console side is the bottom, so rows climb from the bottom edge.
                float y = rel == 2 ? -(areaH - r * RiverStepY - size.height) : -r * RiverStepY;
                var t = TileView.CreateFace(area, discards[i], size);
                UiFactory.Place(t, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(AreaX(rel, RiverW, c * RiverStepX, size.width), y), size.Vector);
                if (discards[i] == highlightCode) TileView.AddSameKindHighlight(t, size, textured ? Palette.FeltSameKindRing : Palette.SameKindRing);
                if (highlightLast && i == discards.Length - 1) TileView.AddRing(t, textured ? Palette.FeltLastDiscardRing : Palette.LastDiscardRing, size, 4);
            }
        }

        // ---------- Input ----------

        /// <summary>
        /// Any time during a hand a click selects my tile (raised, same kind lit up everywhere) and a second click on
        /// it deselects. Two cases need a second click to act: my turn to discard (discard) and the 聽 picker (declare).
        /// A declared hand can only be selected.
        /// </summary>
        void OnTileClicked(int index)
        {
            if (view == null || view.phase != "playing") return;
            if (index < 0 || index >= handOrder.Count) return;
            string code = handOrder[index];

            if (TingPicking)
            {
                OptionDto ting = DtoUtil.FindOption(view, "ting:" + code);
                if (ting == null) return; // dimmed: not a tile the declaration can discard
                if (selectedIndex == index)
                {
                    SendTile(index, ting.id);
                    return;
                }
                selectedIndex = index;
                Render(view, lastRenderFinal);
                return;
            }

            if (CanDiscardByTile && selectedIndex == index)
            {
                OptionDto opt = DtoUtil.FindOption(view, "discard:" + code);
                if (opt != null)
                {
                    SendTile(index, opt.id);
                    return;
                }
            }
            selectedIndex = selectedIndex == index ? -1 : index;
            Render(view, lastRenderFinal); // regions are signature-gated: only the hand, the hint and matching areas rebuild
        }

        /// <summary>Clicking empty space: drop the selection and every same-kind highlight.</summary>
        void ClearSelection()
        {
            if (selectedIndex < 0 || view == null) return;
            selectedIndex = -1;
            Render(view, lastRenderFinal);
        }

        void OnToggleTing()
        {
            if (!CanAct || !DtoUtil.HasOptionType(view, "ting")) return;
            tingOn = !tingOn;
            // A selected tile the picker would dim cannot stay selected.
            if (tingOn && selectedIndex >= 0 && selectedIndex < handOrder.Count &&
                DtoUtil.FindOption(view, "ting:" + handOrder[selectedIndex]) == null)
            {
                selectedIndex = -1;
            }
            Render(view, lastRenderFinal);
        }

        void OnOptionClicked(string actionId)
        {
            if (!CanAct) return;
            if (DtoUtil.FindOption(view, actionId) == null) return;
            Send(actionId);
        }

        /// <summary>Sends the action and locks input until the next "state"; false when nothing was sent.</summary>
        bool Send(string actionId)
        {
            if (!app.SendAction(actionId)) return false;
            awaiting = true; // until the next "state"
            selectedIndex = -1;
            tingOn = false;
            Render(view, true);
            return true;
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

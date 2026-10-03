using System;
using System.Collections.Generic;
using Manjong.Net;
using Manjong.Screens;
using Manjong.UI;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Manjong.Core
{
    /// <summary>
    /// Owns the canvas, the WebSocket connection (contract v0.3: login, account, leaderboard and game), the
    /// logged-in player and screen switching. Screens call the public methods here.
    /// Every request carries a requestId; replies / errors come back with the same id in replyTo, which is how
    /// an error is routed to the UI that asked (nickname hint, relief toast, start hint, ...).
    /// </summary>
    public class AppController : MonoBehaviour
    {
        const float BusyLabelDelay = 0.4f;
        const float ToastSeconds = 3.2f;
        const float RequestTimeoutSeconds = 15f;

        enum RequestKind
        {
            Me,
            Nickname,
            Relief,
            Leaderboard,
            /// <summary>"start" from the lobby: busy until the first step / state, then the table opens.</summary>
            Start,
            /// <summary>"start" sent after a reconnect while sitting at the table.</summary>
            Resync,
            Action
        }

        class PendingRequest
        {
            public RequestKind kind;
            public float sentAt;
            public bool busy;
        }

        public PlayerDto Me { get; private set; }

        Canvas canvas;
        RectTransform screenLayer;
        RectTransform overlayLayer;

        LobbyScreen lobby;
        TableScreen table;

        // Busy blocker
        int busyCount;
        float busySince;
        Image busyBlocker;
        GameObject busyLabel;

        // Error dialog
        GameObject dialog;
        Text dialogTitle;
        Text dialogMessage;
        Button dialogPrimary;
        Button dialogSecondary;
        Action dialogPrimaryAction;
        Action dialogSecondaryAction;

        // Toast
        GameObject toast;
        Text toastText;
        float toastUntil;

        // Connection
        GameConnection connection;
        readonly Dictionary<string, PendingRequest> pending = new Dictionary<string, PendingRequest>();
        readonly List<string> scratchIds = new List<string>();
        bool onTable;

        public bool IsBusy
        {
            get { return busyCount > 0; }
        }

        public bool IsConnected
        {
            get { return connection != null && connection.IsReady; }
        }

        // ---------- Lifecycle ----------

        void Awake()
        {
            // Note: Application.targetFrameRate is deliberately left alone; on WebGL the browser drives the frame loop.
            connection = new GameConnection(TokenStore.Load, TokenStore.Save, TokenStore.Clear);
            connection.Ready += OnSocketReady;
            connection.MessageReceived += OnSocketMessage;
            connection.StateChanged += OnSocketStateChanged;
            connection.TokenReset += OnSocketTokenReset;
            connection.Stopped += OnSocketStopped;
            EnsureCamera();
            EnsureEventSystem();
            BuildCanvas();
            BuildOverlays();

            lobby = CreateScreen<LobbyScreen>("LobbyScreen");
            lobby.Init(this);
            table = CreateScreen<TableScreen>("TableScreen");
            table.Init(this);

            lobby.gameObject.SetActive(false);
            table.gameObject.SetActive(false);
        }

        void Start()
        {
            ShowLobby();
            connection.Open(); // logs in with the stored token, or as a new guest
        }

        void OnDestroy()
        {
            // Closes the socket and cancels the background receive loop (Editor: leaving Play mode).
            if (connection != null) connection.Shutdown();
        }

        void OnApplicationQuit()
        {
            if (connection != null) connection.Shutdown();
        }

        void Update()
        {
            connection.Tick(Time.unscaledTime);
            ExpireRequests();

            if (busyLabel != null)
            {
                bool showLabel = busyCount > 0 && Time.unscaledTime - busySince > BusyLabelDelay;
                if (busyLabel.activeSelf != showLabel) busyLabel.SetActive(showLabel);
            }
            if (toast != null && toast.activeSelf && Time.unscaledTime > toastUntil)
            {
                toast.SetActive(false);
            }
        }

        // ---------- Scene plumbing ----------

        void EnsureCamera()
        {
            if (Camera.main != null)
            {
                Camera.main.clearFlags = CameraClearFlags.SolidColor;
                Camera.main.backgroundColor = Palette.Cream;
                return;
            }
            if (FindAnyObjectByType<Camera>() != null) return;

            var camGo = new GameObject("Main Camera");
            camGo.tag = "MainCamera";
            var cam = camGo.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = Palette.Cream;
            cam.orthographic = true;
            cam.cullingMask = 0;
            DontDestroyOnLoad(camGo);
        }

        void EnsureEventSystem()
        {
            if (FindAnyObjectByType<EventSystem>() != null) return;
            var esGo = new GameObject("EventSystem");
            esGo.AddComponent<EventSystem>();
            esGo.AddComponent<StandaloneInputModule>();
            DontDestroyOnLoad(esGo);
#if !ENABLE_LEGACY_INPUT_MANAGER
            Debug.LogError("[Manjong] StandaloneInputModule needs the legacy Input Manager. " +
                           "Set Player Settings > Active Input Handling to \"Input Manager (Old)\" or \"Both\".");
#endif
        }

        void BuildCanvas()
        {
            var canvasGo = new GameObject("ManjongCanvas", typeof(RectTransform));
            canvasGo.layer = 5;
            DontDestroyOnLoad(canvasGo);
            canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.pixelPerfect = false;

            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 0.5f;
            scaler.referencePixelsPerUnit = 100f;

            canvasGo.AddComponent<GraphicRaycaster>();

            var bg = UiFactory.CreateBlocker(canvasGo.transform, "Background", Palette.Cream);
            bg.raycastTarget = false;

            screenLayer = UiFactory.CreateRect("Screens", canvasGo.transform);
            UiFactory.Stretch(screenLayer);
            overlayLayer = UiFactory.CreateRect("Overlays", canvasGo.transform);
            UiFactory.Stretch(overlayLayer);
        }

        T CreateScreen<T>(string name) where T : MonoBehaviour
        {
            var rt = UiFactory.CreateRect(name, screenLayer);
            UiFactory.Stretch(rt);
            return rt.gameObject.AddComponent<T>();
        }

        void BuildOverlays()
        {
            // Busy blocker: swallows clicks while a request is in flight; label appears after a short delay.
            busyBlocker = UiFactory.CreateBlocker(overlayLayer, "BusyBlocker", Palette.Transparent);
            var labelBg = UiFactory.CreatePanel(busyBlocker.transform, "BusyLabel", Palette.Card, 24);
            UiFactory.Place(labelBg.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(320f, 96f));
            UiFactory.AddShadow(labelBg, Palette.CardShadow, new Vector2(0f, -4f));
            var busyText = UiFactory.CreateLabel(labelBg.transform, "Text", "連線中…", 34, Palette.Ink, TextAnchor.MiddleCenter);
            UiFactory.Stretch(busyText.rectTransform, 12f, 8f, 12f, 8f);
            busyLabel = labelBg.gameObject;
            busyLabel.SetActive(false);
            busyBlocker.gameObject.SetActive(false);

            // Error / retry dialog
            var dim = UiFactory.CreateBlocker(overlayLayer, "Dialog", Palette.Dim);
            dialog = dim.gameObject;
            var card = UiFactory.CreatePanel(dim.transform, "Card", Palette.Card, 32);
            UiFactory.Place(card.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(760f, 420f));
            UiFactory.AddShadow(card, Palette.CardShadow, new Vector2(0f, -6f));

            dialogTitle = UiFactory.CreateLabel(card.transform, "Title", "", 46, Palette.Ink, TextAnchor.MiddleCenter);
            dialogTitle.fontStyle = FontStyle.Bold;
            UiFactory.Place(dialogTitle.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -36f), new Vector2(680f, 64f));

            dialogMessage = UiFactory.CreateText(card.transform, "Message", "", 30, Palette.InkSoft, TextAnchor.MiddleCenter);
            UiFactory.Place(dialogMessage.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -112f), new Vector2(680f, 150f));

            dialogPrimary = UiFactory.CreateButton(card.transform, "Primary", "重試", Palette.Pink, 34, OnDialogPrimary);
            dialogSecondary = UiFactory.CreateButton(card.transform, "Secondary", "關閉", Palette.Gray, 34, OnDialogSecondary);
            UiFactory.Place((RectTransform)dialogPrimary.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(130f, 36f), new Vector2(240f, 80f));
            UiFactory.Place((RectTransform)dialogSecondary.transform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(-130f, 36f), new Vector2(240f, 80f));
            dialog.SetActive(false);

            // Toast
            var toastBg = UiFactory.CreatePanel(overlayLayer, "Toast", Palette.Ink, 26);
            UiFactory.Place(toastBg.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 300f), new Vector2(900f, 84f));
            toastText = UiFactory.CreateLabel(toastBg.transform, "Text", "", 30, Palette.Cream, TextAnchor.MiddleCenter);
            UiFactory.Stretch(toastText.rectTransform, 24f, 8f, 24f, 8f);
            toast = toastBg.gameObject;
            toast.SetActive(false);
        }

        // ---------- Busy / dialog / toast ----------

        void BeginBusy()
        {
            if (busyCount == 0)
            {
                busySince = Time.unscaledTime;
                busyBlocker.gameObject.SetActive(true);
                busyBlocker.transform.SetAsLastSibling();
            }
            busyCount++;
        }

        void EndBusy()
        {
            busyCount = Mathf.Max(0, busyCount - 1);
            if (busyCount == 0)
            {
                busyLabel.SetActive(false);
                busyBlocker.gameObject.SetActive(false);
            }
        }

        public void ShowToast(string message)
        {
            if (string.IsNullOrEmpty(message)) return;
            toastText.text = message;
            toast.SetActive(true);
            toast.transform.SetAsLastSibling();
            toastUntil = Time.unscaledTime + ToastSeconds;
        }

        /// <summary>Modal dialog. Pass secondaryLabel = null to hide the second button.</summary>
        public void ShowDialog(string title, string message, string primaryLabel, Action onPrimary, string secondaryLabel, Action onSecondary)
        {
            dialogTitle.text = title;
            dialogMessage.text = message;
            UiFactory.ButtonLabel(dialogPrimary).text = primaryLabel;
            dialogPrimaryAction = onPrimary;
            dialogSecondaryAction = onSecondary;
            bool hasSecondary = !string.IsNullOrEmpty(secondaryLabel);
            dialogSecondary.gameObject.SetActive(hasSecondary);
            if (hasSecondary) UiFactory.ButtonLabel(dialogSecondary).text = secondaryLabel;
            var primaryRt = (RectTransform)dialogPrimary.transform;
            primaryRt.anchoredPosition = new Vector2(hasSecondary ? 130f : 0f, 36f);
            dialog.SetActive(true);
            dialog.transform.SetAsLastSibling();
        }

        void OnDialogPrimary()
        {
            dialog.SetActive(false);
            var a = dialogPrimaryAction;
            dialogPrimaryAction = null;
            if (a != null) a();
        }

        void OnDialogSecondary()
        {
            dialog.SetActive(false);
            var a = dialogSecondaryAction;
            dialogSecondaryAction = null;
            if (a != null) a();
        }

        // ---------- Screen switching ----------

        public void ShowLobby()
        {
            onTable = false;
            table.Hide();
            lobby.gameObject.SetActive(true);
            lobby.SetConnectionState(connection.State, connection.HasEverConnected, connection.StopCode);
            lobby.Show(Me);
            RefreshLobby();
        }

        void ShowTable()
        {
            onTable = true;
            lobby.gameObject.SetActive(false);
            table.gameObject.SetActive(true);
            table.SetConnectionState(connection.State);
        }

        // ---------- Requests ----------

        /// <summary>Sends a request and remembers what it was for. Null when not connected.</summary>
        string Send(RequestKind kind, string type, string actionId, string nickname, bool busy)
        {
            string id = connection.Request(type, actionId, nickname);
            if (id == null) return null;
            pending[id] = new PendingRequest { kind = kind, sentAt = Time.unscaledTime, busy = busy };
            if (busy) BeginBusy();
            return id;
        }

        PendingRequest Take(string requestId)
        {
            if (string.IsNullOrEmpty(requestId)) return null;
            PendingRequest p;
            if (!pending.TryGetValue(requestId, out p)) return null;
            pending.Remove(requestId);
            if (p.busy) EndBusy();
            return p;
        }

        /// <summary>Removes every pending request of a kind (used for start / action, whose success is a push).</summary>
        bool TakeAll(RequestKind kind)
        {
            scratchIds.Clear();
            foreach (var kv in pending)
            {
                if (kv.Value.kind == kind) scratchIds.Add(kv.Key);
            }
            for (int i = 0; i < scratchIds.Count; i++) Take(scratchIds[i]);
            return scratchIds.Count > 0;
        }

        bool HasPending(RequestKind kind)
        {
            foreach (var kv in pending)
            {
                if (kv.Value.kind == kind) return true;
            }
            return false;
        }

        void ExpireRequests()
        {
            if (pending.Count == 0) return;
            float t = Time.unscaledTime;
            scratchIds.Clear();
            foreach (var kv in pending)
            {
                // Actions have no reply of their own (success = steps + state); the table stays locked until a state.
                if (kv.Value.kind != RequestKind.Action && t - kv.Value.sentAt > RequestTimeoutSeconds) scratchIds.Add(kv.Key);
            }
            for (int i = 0; i < scratchIds.Count; i++)
            {
                PendingRequest p = Take(scratchIds[i]);
                if (p != null) FailRequest(p.kind, "伺服器沒有回應，請再試一次");
            }
        }

        /// <summary>Shows a failure where the player asked for it.</summary>
        void FailRequest(RequestKind kind, string message)
        {
            switch (kind)
            {
                case RequestKind.Nickname:
                    lobby.SetNicknameHint(message, true);
                    break;
                case RequestKind.Relief:
                case RequestKind.Me:
                    ShowToast(message);
                    break;
                case RequestKind.Leaderboard:
                    lobby.SetLeaderboardError(message);
                    break;
                case RequestKind.Start:
                    lobby.SetStartError(message);
                    break;
                case RequestKind.Resync:
                case RequestKind.Action:
                    if (onTable) table.OnServerError();
                    break;
            }
        }

        // ---------- Lobby actions ----------

        public void RefreshLobby()
        {
            if (!connection.IsReady) return;
            if (!HasPending(RequestKind.Me)) Send(RequestKind.Me, "me", "", "", false);
            LoadLeaderboard();
        }

        public void LoadLeaderboard()
        {
            if (!connection.IsReady || HasPending(RequestKind.Leaderboard)) return;
            if (Send(RequestKind.Leaderboard, "leaderboard", "", "", false) != null) lobby.SetLeaderboardLoading();
        }

        public void ChangeNickname(string nickname)
        {
            if (Send(RequestKind.Nickname, "nickname", "", nickname, true) == null)
            {
                lobby.SetNicknameHint("尚未連上伺服器，請稍候再試", true);
            }
        }

        public void ClaimRelief()
        {
            if (Send(RequestKind.Relief, "relief", "", "", true) == null) ShowToast("尚未連上伺服器，請稍候再試");
        }

        /// <summary>Lobby "start": new game or resume. The table opens on the first step / state.</summary>
        public void StartGame()
        {
            if (IsBusy || HasPending(RequestKind.Start)) return;
            if (Send(RequestKind.Start, "start", "", "", true) == null) lobby.SetStartError("尚未連上伺服器，請稍候再試");
        }

        /// <summary>Reconnect after Stopped (logged in elsewhere) or Idle.</summary>
        public void Reconnect()
        {
            connection.Open();
        }

        // ---------- Table actions ----------

        /// <summary>Sends an option id. Returns false (and tells the player) when not connected.</summary>
        public bool SendAction(string actionId)
        {
            if (Send(RequestKind.Action, "action", actionId, "", false) != null) return true;
            ShowToast("連線中斷，正在重新連線…");
            return false;
        }

        /// <summary>Leave the table; the game stays on the server and resumes with "start" from the lobby.</summary>
        public void LeaveTable()
        {
            ShowLobby();
        }

        // ---------- Socket events ----------

        void OnSocketReady()
        {
            if (onTable)
            {
                if (table.IsGameOver)
                {
                    // Never "start" here: it would silently open a new game. The result panel's "回大廳" still works.
                    return;
                }
                table.PrepareResync();
                Send(RequestKind.Resync, "start", "", "", false);
            }
            // In the lobby the auth_ok handler below refreshes the profile and leaderboard.
        }

        void OnSocketMessage(ServerMessage msg)
        {
            switch (msg.type)
            {
                case "auth_ok":
                    SetMe(msg.player);
                    if (!onTable) LoadLeaderboard();
                    break;
                case "player":
                    OnPlayer(msg);
                    break;
                case "leaderboard":
                    Take(msg.replyTo);
                    lobby.SetLeaderboard(msg.entries);
                    break;
                case "step":
                    if (!EnterTableIfStarting()) return;
                    if (msg.step != null) table.EnqueueStep(msg.step);
                    break;
                case "state":
                    if (!EnterTableIfStarting()) return;
                    TakeAll(RequestKind.Action);
                    TakeAll(RequestKind.Resync);
                    if (msg.view != null) table.EnqueueState(msg.view);
                    break;
                case "error":
                    OnSocketError(msg);
                    break;
            }
        }

        void SetMe(PlayerDto player)
        {
            if (player == null || string.IsNullOrEmpty(player.id)) return;
            Me = player;
            if (lobby.gameObject.activeSelf) lobby.Show(Me);
        }

        void OnPlayer(ServerMessage msg)
        {
            PendingRequest req = Take(msg.replyTo);
            SetMe(msg.player);
            if (req == null) return; // post-hand push or "me" reply already handled by SetMe
            if (req.kind == RequestKind.Nickname)
            {
                lobby.SetNicknameHint("暱稱已更新", false);
                LoadLeaderboard();
            }
            else if (req.kind == RequestKind.Relief)
            {
                ShowToast("已領取救濟金，目前金幣 " + Format.Coins(Me != null ? Me.coins : 0));
                LoadLeaderboard();
            }
        }

        /// <summary>Opens the table on the first game message after a lobby "start". False when not playing.</summary>
        bool EnterTableIfStarting()
        {
            if (TakeAll(RequestKind.Start))
            {
                ShowTable();
                table.BeginGame();
                return true;
            }
            // Game messages that arrive while the player sits in the lobby are ignored; "start" brings a fresh state.
            return onTable;
        }

        void OnSocketError(ServerMessage msg)
        {
            string code = msg.code ?? "";
            string text = string.IsNullOrEmpty(msg.message) ? "伺服器發生錯誤" : msg.message;
            PendingRequest req = Take(msg.replyTo);

            switch (code)
            {
                case "INVALID_TOKEN":
                case "AUTH_TIMEOUT":
                case "UNAUTHORIZED":
                    // The close that follows is handled by GameConnection (token kept unless INVALID_TOKEN).
                    return;
                case "NO_GAME":
                    ShowLobby();
                    ShowToast("牌局已結束，請重新開始");
                    return;
                case "NOT_ENOUGH_COINS":
                    if (onTable) ShowLobby();
                    lobby.SetStartError(text);
                    return;
                case "ILLEGAL_ACTION":
                    // A rejected action is followed by a fresh state. "Wait for the other players" (BusyError) is not:
                    // that state arrives when the AI turns finish, so the table simply stays locked until then.
                    ShowToast(text);
                    return;
            }

            if (req != null)
            {
                FailRequest(req.kind, text);
                return;
            }
            // BAD_MESSAGE / INTERNAL / unknown without a matching request.
            ShowToast(text);
            if (onTable) table.OnServerError();
        }

        void OnSocketStateChanged(ConnectionState state)
        {
            lobby.SetConnectionState(state, connection.HasEverConnected, connection.StopCode);
            if (onTable) table.SetConnectionState(state);
            if (state != ConnectionState.Ready && pending.Count > 0)
            {
                // Replies can never arrive on a new socket: fail everything that was in flight.
                scratchIds.Clear();
                foreach (var kv in pending) scratchIds.Add(kv.Key);
                var ids = new List<string>(scratchIds);
                for (int i = 0; i < ids.Count; i++)
                {
                    PendingRequest p = Take(ids[i]);
                    if (p != null) FailRequest(p.kind, "連線中斷，請再試一次");
                }
            }
        }

        void OnSocketTokenReset()
        {
            Me = null;
            ShowToast("登入資料已失效，將建立新的訪客帳號");
            if (onTable) ShowLobby();
        }

        void OnSocketStopped(int closeCode)
        {
            if (closeCode == GameConnection.CloseOriginRejected)
            {
                ShowLobby();
                ShowDialog(
                    "伺服器拒絕連線",
                    "這個網頁的來源不在伺服器允許的清單中（close 4403）。\n請改從伺服器提供的網址開啟遊戲。",
                    "知道了", null, null, null);
                return;
            }
            ShowLobby();
            ShowDialog(
                "已在其他視窗登入",
                "這個帳號在其他視窗或分頁登入了，這裡的連線已中斷。\n若要改在這裡玩，請按大廳右上角的「重新連線」。",
                "知道了", null, null, null);
        }
    }
}

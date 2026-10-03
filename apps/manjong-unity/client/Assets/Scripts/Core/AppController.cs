using System;
using System.Collections;
using Manjong.Net;
using Manjong.Screens;
using Manjong.UI;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Manjong.Core
{
    /// <summary>
    /// Owns the canvas, the HTTP client (account / leaderboard), the game WebSocket, the logged-in player and
    /// screen switching. Screens call the public methods here.
    /// HTTP calls go through Call&lt;T&gt;(); game traffic goes through GameConnection (contract v0.2 section 2).
    /// </summary>
    public class AppController : MonoBehaviour
    {
        const float BusyLabelDelay = 0.4f;
        const float StartTimeoutSeconds = 15f;
        const float ToastSeconds = 3.2f;

        public ApiClient Api { get; private set; }
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

        bool loggingIn;

        // Game socket
        GameConnection connection;
        /// <summary>"start" requested from the lobby; waiting for the first step / state / error.</summary>
        bool pendingStart;
        float pendingStartSince;
        bool onTable;

        public bool IsBusy
        {
            get { return busyCount > 0 || loggingIn; }
        }

        // ---------- Lifecycle ----------

        void Awake()
        {
            // Note: Application.targetFrameRate is deliberately left alone; on WebGL the browser drives the frame loop.
            Api = new ApiClient();
            connection = new GameConnection(() => Api.Token);
            connection.Ready += OnSocketReady;
            connection.MessageReceived += OnSocketMessage;
            connection.ConnectFailed += OnSocketConnectFailed;
            connection.StateChanged += OnSocketStateChanged;
            connection.AuthRejected += OnSocketAuthRejected;
            connection.Replaced += OnSocketReplaced;
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
            StartCoroutine(LoginFlow());
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
            if (pendingStart && Time.unscaledTime - pendingStartSince > StartTimeoutSeconds)
            {
                // Connected (or still trying) but no game message arrived: do not leave the lobby blocked.
                FinishPendingStart();
                ShowDialog("伺服器沒有回應", "開始遊戲的要求逾時，請稍後再試。", "重試", StartGame, "關閉", null);
            }

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

        void ShowNetworkError(Action retry, bool allowClose)
        {
            ShowDialog(
                "連不上伺服器",
                "請確認網路連線與後端伺服器已啟動。\n伺服器位置：" + ApiConfig.BaseUrl,
                "重試",
                retry,
                allowClose ? "關閉" : null,
                null);
        }

        // ---------- Generic call ----------

        /// <summary>
        /// Performs a request with the busy blocker. Network failures show a retry dialog;
        /// 401 triggers a fresh guest login; other API errors go to onFail or a toast with the server message.
        /// </summary>
        public void Call<T>(string method, string path, string jsonBody, Action<T> onOk, Action<ApiError> onFail) where T : class
        {
            StartCoroutine(CallRoutine(method, path, jsonBody, onOk, onFail));
        }

        IEnumerator CallRoutine<T>(string method, string path, string jsonBody, Action<T> onOk, Action<ApiError> onFail) where T : class
        {
            T result = null;
            ApiError error = null;
            BeginBusy();
            try
            {
                if (method == "GET")
                {
                    yield return StartCoroutine(Api.Get<T>(path, r => result = r, e => error = e));
                }
                else
                {
                    yield return StartCoroutine(Api.Post<T>(path, jsonBody, r => result = r, e => error = e));
                }
            }
            finally
            {
                EndBusy();
            }

            if (error == null)
            {
                if (onOk != null) onOk(result);
                yield break;
            }
            if (error.isNetwork)
            {
                ShowNetworkError(() => Call(method, path, jsonBody, onOk, onFail), true);
                if (onFail != null) onFail(error);
                yield break;
            }
            if (error.status == 401)
            {
                ShowToast("登入已失效，正在重新登入…");
                Api.ClearToken();
                Me = null;
                StartCoroutine(LoginFlow());
                yield break;
            }
            if (onFail != null) onFail(error);
            else ShowToast(error.message);
        }

        // ---------- Login ----------

        IEnumerator LoginFlow()
        {
            if (loggingIn) yield break;
            loggingIn = true;

            PlayerDto player = null;
            ApiError error = null;

            BeginBusy();
            try
            {
                if (Api.HasToken)
                {
                    yield return StartCoroutine(Api.Get<PlayerResponse>("/api/me", r => player = r != null ? r.player : null, e => error = e));
                    if (error != null && error.status == 401)
                    {
                        // Stale token: discard and fall through to a new guest account.
                        Api.ClearToken();
                        error = null;
                        player = null;
                    }
                }

                if (error == null && player == null)
                {
                    AuthResponse auth = null;
                    yield return StartCoroutine(Api.Post<AuthResponse>("/api/auth/guest", "{}", r => auth = r, e => error = e));
                    if (error == null && auth != null && !string.IsNullOrEmpty(auth.token))
                    {
                        Api.SetToken(auth.token);
                        player = auth.player;
                    }
                    else if (error == null)
                    {
                        error = new ApiError { status = 0, code = "BAD_RESPONSE", message = "伺服器回傳的登入資料不完整", isNetwork = false };
                    }
                }
            }
            finally
            {
                EndBusy();
                loggingIn = false;
            }

            if (error != null)
            {
                Action retry = () => StartCoroutine(LoginFlow());
                if (error.isNetwork) ShowNetworkError(retry, false);
                else ShowDialog("登入失敗", error.message, "重試", retry, null, null);
                yield break;
            }

            Me = player;
            ShowLobby();
        }

        // ---------- Screen switching ----------

        public void ShowLobby()
        {
            onTable = false;
            table.Hide();
            lobby.gameObject.SetActive(true);
            lobby.Show(Me);
            RefreshLobby();
        }

        void ShowTable()
        {
            onTable = true;
            lobby.gameObject.SetActive(false);
            table.gameObject.SetActive(true);
        }

        // ---------- Lobby actions (HTTP) ----------

        public void RefreshLobby()
        {
            if (loggingIn) return;
            Call<PlayerResponse>("GET", "/api/me", null, r =>
            {
                if (r != null && r.player != null)
                {
                    Me = r.player;
                    lobby.Show(Me);
                }
            }, null);
            LoadLeaderboard();
        }

        public void LoadLeaderboard()
        {
            lobby.SetLeaderboardLoading();
            // Not wrapped in Call(): leaderboard failures are shown inline in the list instead of a dialog.
            StartCoroutine(Api.Get<LeaderboardResponse>("/api/leaderboard",
                r => lobby.SetLeaderboard(r),
                e => lobby.SetLeaderboardError(e.isNetwork ? "連不上伺服器，請按「重新整理」重試" : e.message)));
        }

        public void ChangeNickname(string nickname)
        {
            var body = JsonUtility.ToJson(new NicknameRequest { nickname = nickname });
            Call<PlayerResponse>("POST", "/api/me/nickname", body, r =>
            {
                if (r != null && r.player != null) Me = r.player;
                lobby.Show(Me);
                lobby.SetNicknameHint("暱稱已更新", false);
                LoadLeaderboard();
            }, e =>
            {
                if (!e.isNetwork) lobby.SetNicknameHint(e.message, true);
            });
        }

        public void ClaimRelief()
        {
            Call<PlayerResponse>("POST", "/api/me/relief", "{}", r =>
            {
                if (r != null && r.player != null) Me = r.player;
                lobby.Show(Me);
                ShowToast("已領取救濟金，目前金幣 " + Format.Coins(Me != null ? Me.coins : 0));
                LoadLeaderboard();
            }, null);
        }

        // ---------- Game (WebSocket) ----------

        /// <summary>Lobby "start": opens the socket if needed and sends "start" (new game or resume).</summary>
        public void StartGame()
        {
            if (IsBusy || pendingStart) return;
            pendingStart = true;
            pendingStartSince = Time.unscaledTime;
            BeginBusy();
            if (connection.IsReady) connection.SendStart();
            else connection.Open(); // "start" goes out in OnSocketReady
        }

        /// <summary>Sends an option id. Returns false (and tells the player) when the socket is not ready.</summary>
        public bool SendAction(string actionId)
        {
            if (connection.SendAction(actionId)) return true;
            ShowToast("連線中斷，正在重新連線…");
            return false;
        }

        public bool IsGameConnected
        {
            get { return connection != null && connection.IsReady; }
        }

        /// <summary>Leave the table; the game stays on the server and resumes with "start" from the lobby.</summary>
        public void LeaveTable()
        {
            ShowLobby();
        }

        void FinishPendingStart()
        {
            if (!pendingStart) return;
            pendingStart = false;
            EndBusy();
        }

        void OnSocketReady()
        {
            if (pendingStart)
            {
                connection.SendStart();
            }
            else if (onTable)
            {
                // Reconnected while at the table: resync with a fresh snapshot.
                table.PrepareResync();
                connection.SendStart();
            }
        }

        void OnSocketMessage(ServerMessage msg)
        {
            switch (msg.type)
            {
                case "auth_ok":
                case "player":
                    if (msg.player != null && !string.IsNullOrEmpty(msg.player.id))
                    {
                        Me = msg.player;
                        if (lobby.gameObject.activeSelf) lobby.Show(Me);
                    }
                    break;
                case "step":
                    if (!EnterTableIfStarting()) return;
                    if (msg.step != null) table.EnqueueStep(msg.step);
                    break;
                case "state":
                    if (!EnterTableIfStarting()) return;
                    if (msg.view != null) table.EnqueueState(msg.view);
                    break;
                case "error":
                    OnSocketError(msg.code, msg.message);
                    break;
            }
        }

        /// <summary>Switches to the table on the first game message after "start". False when we are not playing.</summary>
        bool EnterTableIfStarting()
        {
            if (pendingStart)
            {
                FinishPendingStart();
                ShowTable();
                table.BeginGame();
                return true;
            }
            // Messages that arrive while the player sits in the lobby are ignored; "start" brings a fresh state.
            return onTable;
        }

        void OnSocketError(string code, string message)
        {
            string text = string.IsNullOrEmpty(message) ? "伺服器發生錯誤" : message;
            switch (code)
            {
                case "ILLEGAL_ACTION":
                    // The server follows up with a fresh "state", which unlocks the table.
                    ShowToast(text);
                    break;
                case "NO_GAME":
                    FinishPendingStart();
                    ShowLobby();
                    ShowToast("牌局已結束，請重新開始");
                    break;
                case "NOT_ENOUGH_COINS":
                    FinishPendingStart();
                    if (onTable) ShowLobby();
                    lobby.SetStartError(text);
                    break;
                case "UNAUTHORIZED":
                    // A 4401 close follows and is handled in OnSocketAuthRejected.
                    Debug.LogWarning("[Manjong] WebSocket UNAUTHORIZED: " + text);
                    break;
                default:
                    // BAD_MESSAGE / INTERNAL / unknown: no state is guaranteed to follow, so unlock.
                    FinishPendingStart();
                    ShowToast(text);
                    if (onTable) table.OnServerError();
                    break;
            }
        }

        void OnSocketConnectFailed()
        {
            if (!pendingStart) return; // at the table the banner shows and the connection keeps retrying
            FinishPendingStart();
            connection.Shutdown();
            ShowNetworkError(StartGame, true);
        }

        void OnSocketStateChanged(ConnectionState state)
        {
            if (onTable) table.SetConnectionState(state);
        }

        void OnSocketAuthRejected()
        {
            FinishPendingStart();
            ShowToast("登入已失效，正在重新登入…");
            Api.ClearToken();
            Me = null;
            StartCoroutine(LoginFlow()); // ends in ShowLobby()
        }

        void OnSocketReplaced()
        {
            FinishPendingStart();
            ShowLobby();
            ShowDialog(
                "已在其他視窗登入",
                "這個帳號在其他視窗或分頁開始了牌局，這裡的連線已中斷。\n若要改在這裡玩，請按「開始遊戲」。",
                "知道了",
                null,
                null,
                null);
        }
    }
}

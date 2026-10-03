using System;
using UnityEngine;

namespace Manjong.Net
{
    public enum ConnectionState
    {
        /// <summary>Not connected and not trying.</summary>
        Idle,
        Connecting,
        /// <summary>Socket open, "auth" / "guest" sent, waiting for "auth_ok".</summary>
        Authenticating,
        Ready,
        /// <summary>Dropped; waiting for the back-off timer before the next attempt.</summary>
        Reconnecting,
        /// <summary>Server refused us for good (4000 logged in elsewhere, 4403 origin not allowed); no automatic reconnect.</summary>
        Stopped
    }

    /// <summary>
    /// The single connection to the backend (contract v0.3: login, account, leaderboard and game all go here).
    /// - First frame after open is "auth" (stored token) or "guest" (no token); up only after "auth_ok".
    ///   A token from auth_ok is persisted.
    /// - Close 4401 after error INVALID_TOKEN: the token is cleared and the next attempt sends "guest" right away.
    ///   Any other 4401 (UNAUTHORIZED = client bug) and 4408 (AUTH_TIMEOUT) keep the token and retry with back-off.
    /// - Close 4000 (logged in elsewhere) and 4403 (origin not allowed) stop reconnecting.
    /// - "ping" every 25 s; no server traffic for 60 s counts as a dead connection.
    /// - Connect phase times out after 10 s on every platform (a fresh transport is created for the retry).
    /// - Back-off 0.5 s doubling up to 10 s; the counter resets only after 30 s of stable connection.
    /// Must be ticked from the main thread; all events fire on the main thread inside Tick().
    /// </summary>
    public class GameConnection
    {
        public const int CloseUnauthorized = 4401;
        public const int CloseAuthTimeout = 4408;
        public const int CloseReplaced = 4000;
        public const int CloseOriginRejected = 4403;
        public const int CloseRateLimited = 1008;

        const float PingInterval = 25f;
        const float SilenceTimeout = 60f;
        const float ConnectTimeout = 10f;
        const float AuthTimeout = 12f;
        const float StableAfter = 30f;
        const float FirstBackoff = 0.5f;
        const float MaxBackoff = 10f;
        const int MaxEventsPerTick = 256;

        readonly Func<string> loadToken;
        readonly Action<string> saveToken;
        readonly Action clearToken;

        ISocketTransport transport;
        bool wanted;
        int failedAttempts;
        int requestCounter;
        float now;
        float retryAt;
        float lastPingAt;
        float lastReceivedAt;
        float phaseDeadline;
        float readySince;
        /// <summary>error code received on the current socket (decides what a following close means).</summary>
        string lastErrorCode = "";

        public ConnectionState State { get; private set; }

        /// <summary>True once any connection reached Ready in this app session.</summary>
        public bool HasEverConnected { get; private set; }

        /// <summary>Close code that put us into Stopped (0 otherwise).</summary>
        public int StopCode { get; private set; }

        /// <summary>Every server message except pong (auth_ok included, after Ready fired).</summary>
        public event Action<ServerMessage> MessageReceived;
        /// <summary>auth_ok received.</summary>
        public event Action Ready;
        public event Action<ConnectionState> StateChanged;
        /// <summary>The stored token was rejected (INVALID_TOKEN + 4401) and cleared; a guest login follows.</summary>
        public event Action TokenReset;
        /// <summary>Reconnecting stopped because of the given close code (4000 / 4403).</summary>
        public event Action<int> Stopped;

        public GameConnection(Func<string> loadToken, Action<string> saveToken, Action clearToken)
        {
            this.loadToken = loadToken;
            this.saveToken = saveToken;
            this.clearToken = clearToken;
            State = ConnectionState.Idle;
        }

        public bool IsReady
        {
            get { return State == ConnectionState.Ready; }
        }

        /// <summary>Connect (or keep the current connection). Also resumes after Stopped / Idle.</summary>
        public void Open()
        {
            wanted = true;
            if (State == ConnectionState.Idle || State == ConnectionState.Stopped || State == ConnectionState.Reconnecting)
            {
                failedAttempts = 0;
                StopCode = 0;
                StartConnect();
            }
        }

        /// <summary>Disconnect and stop reconnecting. Safe to call repeatedly (e.g. from OnDestroy).</summary>
        public void Shutdown()
        {
            wanted = false;
            CloseTransport();
            SetState(ConnectionState.Idle);
        }

        /// <summary>
        /// Sends a request that needs a logged-in connection. Returns its requestId, or null when not ready or
        /// the transport refused the frame (nothing is queued).
        /// </summary>
        public string Request(string type, string actionId, string nickname)
        {
            if (State != ConnectionState.Ready || transport == null) return null;
            string id = NextRequestId();
            var msg = new ClientMessage { type = type, requestId = id, token = "", actionId = actionId ?? "", nickname = nickname ?? "" };
            if (!transport.Send(JsonUtility.ToJson(msg)))
            {
                Debug.LogWarning("[Manjong] WebSocket send failed for " + type);
                return null;
            }
            return id;
        }

        public void Tick(float time)
        {
            now = time;

            int handled = 0;
            SocketEvent ev;
            while (transport != null && handled < MaxEventsPerTick && transport.TryDequeue(out ev))
            {
                handled++;
                Handle(ev);
            }

            switch (State)
            {
                case ConnectionState.Reconnecting:
                    if (wanted && now >= retryAt) StartConnect();
                    break;
                case ConnectionState.Connecting:
                    if (now >= phaseDeadline) Drop("connect timeout");
                    break;
                case ConnectionState.Authenticating:
                    if (now >= phaseDeadline) Drop("auth timeout");
                    break;
                case ConnectionState.Ready:
                    if (now - lastReceivedAt >= SilenceTimeout)
                    {
                        Drop("no server message for " + SilenceTimeout + " s");
                        break;
                    }
                    if (failedAttempts > 0 && now - readySince >= StableAfter) failedAttempts = 0;
                    if (now - lastPingAt >= PingInterval)
                    {
                        lastPingAt = now;
                        if (!SendRaw(new ClientMessage { type = "ping", requestId = "", token = "", actionId = "", nickname = "" }))
                        {
                            Drop("ping send failed");
                        }
                    }
                    break;
            }
        }

        // ---------- Internals ----------

        string NextRequestId()
        {
            requestCounter++;
            return requestCounter.ToString();
        }

        bool SendRaw(ClientMessage msg)
        {
            return transport != null && transport.Send(JsonUtility.ToJson(msg));
        }

        void StartConnect()
        {
            CloseTransport();
            lastErrorCode = "";
            transport = SocketTransportFactory.Create();
            phaseDeadline = now + ConnectTimeout;
            SetState(ConnectionState.Connecting);
            transport.Connect(ApiConfig.WebSocketUrl);
        }

        void CloseTransport()
        {
            if (transport != null)
            {
                transport.Close();
                transport = null;
            }
        }

        /// <summary>Client-side decision that the connection is dead: tear down and go through the normal close path.</summary>
        void Drop(string reason)
        {
            Debug.LogWarning("[Manjong] WebSocket dropped: " + reason);
            CloseTransport();
            OnClosed(1006);
        }

        void Handle(SocketEvent ev)
        {
            switch (ev.kind)
            {
                case SocketEventKind.Open:
                    SendLogin();
                    break;
                case SocketEventKind.Message:
                    lastReceivedAt = now;
                    HandleText(ev.data);
                    break;
                case SocketEventKind.Error:
                    Debug.LogWarning("[Manjong] WebSocket error: " + ev.data);
                    break;
                case SocketEventKind.Close:
                    transport = null; // the transport is finished after a Close event
                    OnClosed(ev.closeCode);
                    break;
            }
        }

        void SendLogin()
        {
            SetState(ConnectionState.Authenticating);
            phaseDeadline = now + AuthTimeout;
            lastReceivedAt = now;
            string token = loadToken() ?? "";
            var msg = token.Length > 0
                ? new ClientMessage { type = "auth", requestId = NextRequestId(), token = token, actionId = "", nickname = "" }
                : new ClientMessage { type = "guest", requestId = NextRequestId(), token = "", actionId = "", nickname = "" };
            if (!SendRaw(msg)) Drop("could not send " + msg.type);
        }

        void HandleText(string text)
        {
            ServerMessage msg = null;
            try
            {
                msg = JsonUtility.FromJson<ServerMessage>(text);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Manjong] Bad server message: " + e.Message);
            }
            if (msg == null || string.IsNullOrEmpty(msg.type)) return;

            if (msg.type == "pong") return;
            if (msg.type == "error")
            {
                lastErrorCode = msg.code ?? "";
                if (lastErrorCode == "UNAUTHORIZED") Debug.LogError("[Manjong] Server says UNAUTHORIZED: a request was sent before login (client bug).");
            }
            if (msg.type == "auth_ok")
            {
                if (!string.IsNullOrEmpty(msg.token)) saveToken(msg.token);
                lastPingAt = now;
                readySince = now;
                HasEverConnected = true;
                SetState(ConnectionState.Ready);
                if (Ready != null) Ready();
            }
            if (MessageReceived != null) MessageReceived(msg);
        }

        void OnClosed(int code)
        {
            string errorCode = lastErrorCode;
            lastErrorCode = "";

            if (code == CloseReplaced || code == CloseOriginRejected)
            {
                wanted = false;
                StopCode = code;
                SetState(ConnectionState.Stopped);
                if (Stopped != null) Stopped(code);
                return;
            }
            if (!wanted)
            {
                SetState(ConnectionState.Idle);
                return;
            }

            if (code == CloseUnauthorized && errorCode == "INVALID_TOKEN")
            {
                // The only case that discards the token (contract v0.3): retry at once as a guest.
                clearToken();
                if (TokenReset != null) TokenReset();
                retryAt = now;
                SetState(ConnectionState.Reconnecting);
                return;
            }

            // 4408 AUTH_TIMEOUT, other 4401 (UNAUTHORIZED), 1008 rate limit, drops: keep the token, back off.
            failedAttempts++;
            float delay = Mathf.Min(MaxBackoff, FirstBackoff * Mathf.Pow(2f, Mathf.Min(failedAttempts - 1, 10)));
            retryAt = now + delay;
            SetState(ConnectionState.Reconnecting);
            Debug.Log("[Manjong] WebSocket closed (" + code + (errorCode.Length > 0 ? ", " + errorCode : "") +
                      "), retrying in " + delay.ToString("0.0") + " s");
        }

        void SetState(ConnectionState s)
        {
            if (State == s) return;
            State = s;
            if (StateChanged != null) StateChanged(s);
        }
    }
}

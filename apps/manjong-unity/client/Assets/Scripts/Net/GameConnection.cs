using System;
using UnityEngine;

namespace Manjong.Net
{
    public enum ConnectionState
    {
        /// <summary>Not connected and not trying.</summary>
        Idle,
        Connecting,
        /// <summary>Socket open, "auth" sent, waiting for "auth_ok".</summary>
        Authenticating,
        Ready,
        /// <summary>Dropped; waiting for the back-off timer before the next attempt.</summary>
        Reconnecting,
        /// <summary>Server refused us for good (4401 / 4000); no automatic reconnect.</summary>
        Stopped
    }

    /// <summary>
    /// Game WebSocket session on top of an ISocketTransport (contract v0.2 section 2).
    /// - First frame after open is "auth"; the connection counts as up only after "auth_ok".
    /// - "ping" every 25 s while ready.
    /// - Unexpected drops reconnect with exponential back-off capped at 10 s.
    /// - Close 4401 (bad token) and 4000 (logged in elsewhere) stop reconnecting and raise dedicated events.
    /// Must be ticked from the main thread; all events fire on the main thread inside Tick().
    /// </summary>
    public class GameConnection
    {
        public const int CloseUnauthorized = 4401;
        public const int CloseReplaced = 4000;

        const float PingInterval = 25f;
        const float AuthTimeout = 12f;
        const float FirstBackoff = 0.5f;
        const float MaxBackoff = 10f;
        const int MaxEventsPerTick = 256;

        readonly Func<string> tokenProvider;
        ISocketTransport transport;
        bool wanted;
        int failedAttempts;
        float now;
        float retryAt;
        float lastPingAt;
        float authDeadline;

        public ConnectionState State { get; private set; }

        /// <summary>Every server message except pong (auth_ok included, after Ready fired).</summary>
        public event Action<ServerMessage> MessageReceived;
        /// <summary>auth_ok received.</summary>
        public event Action Ready;
        /// <summary>An attempt failed before reaching Ready (a retry is scheduled unless Shutdown is called).</summary>
        public event Action ConnectFailed;
        /// <summary>A ready connection dropped unexpectedly (a retry is scheduled).</summary>
        public event Action Dropped;
        /// <summary>Close code 4401: token rejected.</summary>
        public event Action AuthRejected;
        /// <summary>Close code 4000: the same player connected from somewhere else.</summary>
        public event Action Replaced;
        public event Action<ConnectionState> StateChanged;

        public GameConnection(Func<string> tokenProvider)
        {
            this.tokenProvider = tokenProvider;
            State = ConnectionState.Idle;
        }

        public bool IsReady
        {
            get { return State == ConnectionState.Ready; }
        }

        /// <summary>Connect (or keep the current connection). Also resumes after Stopped.</summary>
        public void Open()
        {
            wanted = true;
            if (State == ConnectionState.Idle || State == ConnectionState.Stopped || State == ConnectionState.Reconnecting)
            {
                failedAttempts = 0;
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

        /// <summary>Sends a game message; false when not ready (nothing is queued).</summary>
        public bool Send(ClientMessage message)
        {
            if (State != ConnectionState.Ready || transport == null) return false;
            return transport.Send(JsonUtility.ToJson(message));
        }

        public bool SendStart()
        {
            return Send(new ClientMessage { type = "start", token = "", actionId = "" });
        }

        public bool SendAction(string actionId)
        {
            return Send(new ClientMessage { type = "action", token = "", actionId = actionId ?? "" });
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
                case ConnectionState.Authenticating:
                    if (now >= authDeadline)
                    {
                        Debug.LogWarning("[Manjong] WebSocket auth timed out");
                        CloseTransport();
                        OnClosed(1006);
                    }
                    break;
                case ConnectionState.Ready:
                    if (now - lastPingAt >= PingInterval)
                    {
                        lastPingAt = now;
                        transport.Send(JsonUtility.ToJson(new ClientMessage { type = "ping", token = "", actionId = "" }));
                    }
                    break;
            }
        }

        // ---------- Internals ----------

        void StartConnect()
        {
            CloseTransport();
            transport = SocketTransportFactory.Create();
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

        void Handle(SocketEvent ev)
        {
            switch (ev.kind)
            {
                case SocketEventKind.Open:
                    SetState(ConnectionState.Authenticating);
                    authDeadline = now + AuthTimeout;
                    transport.Send(JsonUtility.ToJson(new ClientMessage { type = "auth", token = tokenProvider() ?? "", actionId = "" }));
                    break;
                case SocketEventKind.Message:
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
            if (msg.type == "auth_ok")
            {
                failedAttempts = 0;
                lastPingAt = now;
                SetState(ConnectionState.Ready);
                if (Ready != null) Ready();
            }
            if (MessageReceived != null) MessageReceived(msg);
        }

        void OnClosed(int code)
        {
            bool wasReady = State == ConnectionState.Ready;

            if (code == CloseUnauthorized)
            {
                wanted = false;
                SetState(ConnectionState.Stopped);
                if (AuthRejected != null) AuthRejected();
                return;
            }
            if (code == CloseReplaced)
            {
                wanted = false;
                SetState(ConnectionState.Stopped);
                if (Replaced != null) Replaced();
                return;
            }
            if (!wanted)
            {
                SetState(ConnectionState.Idle);
                return;
            }

            failedAttempts++;
            float delay = Mathf.Min(MaxBackoff, FirstBackoff * Mathf.Pow(2f, Mathf.Min(failedAttempts - 1, 10)));
            retryAt = now + delay;
            SetState(ConnectionState.Reconnecting);
            Debug.Log("[Manjong] WebSocket closed (" + code + "), retrying in " + delay.ToString("0.0") + " s");

            if (wasReady)
            {
                if (Dropped != null) Dropped();
            }
            else
            {
                if (ConnectFailed != null) ConnectFailed();
            }
        }

        void SetState(ConnectionState s)
        {
            if (State == s) return;
            State = s;
            if (StateChanged != null) StateChanged(s);
        }
    }
}

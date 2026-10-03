namespace Manjong.Net
{
    public enum SocketEventKind
    {
        Open,
        Message,
        Error,
        Close
    }

    /// <summary>One transport event, always consumed on the Unity main thread.</summary>
    public struct SocketEvent
    {
        public SocketEventKind kind;
        /// <summary>Message text (Message) or diagnostic text (Error).</summary>
        public string data;
        /// <summary>WebSocket close code (Close); 1006 when the connection dropped without a close frame.</summary>
        public int closeCode;

        public static SocketEvent Opened()
        {
            return new SocketEvent { kind = SocketEventKind.Open, data = "", closeCode = 0 };
        }

        public static SocketEvent Text(string text)
        {
            return new SocketEvent { kind = SocketEventKind.Message, data = text ?? "", closeCode = 0 };
        }

        public static SocketEvent Failed(string reason)
        {
            return new SocketEvent { kind = SocketEventKind.Error, data = reason ?? "", closeCode = 0 };
        }

        public static SocketEvent Closed(int code)
        {
            return new SocketEvent { kind = SocketEventKind.Close, data = "", closeCode = code };
        }
    }

    /// <summary>
    /// Minimal text WebSocket. Implementations never invoke callbacks; the owner polls TryDequeue() every frame
    /// on the main thread. After a Close event no further events are produced. Close() is idempotent and silent
    /// (it does not enqueue a Close event).
    /// </summary>
    public interface ISocketTransport
    {
        void Connect(string url);
        /// <summary>Returns false when the socket is not open.</summary>
        bool Send(string text);
        bool TryDequeue(out SocketEvent ev);
        void Close();
    }

    public static class SocketTransportFactory
    {
        public static ISocketTransport Create()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            return new WebGLSocketTransport();
#else
            return new NativeSocketTransport();
#endif
        }
    }
}

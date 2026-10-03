#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;

namespace Manjong.Net
{
    /// <summary>
    /// Browser WebSocket via Assets/Plugins/WebGL/ManjongSocket.jslib. Single threaded: events are queued in JS
    /// and pulled here by polling, so no SendMessage callbacks are involved.
    /// </summary>
    public class WebGLSocketTransport : ISocketTransport
    {
        [DllImport("__Internal")] static extern int ManjongSocketConnect(string url);
        [DllImport("__Internal")] static extern int ManjongSocketSend(int id, string text);
        [DllImport("__Internal")] static extern string ManjongSocketPoll(int id);
        [DllImport("__Internal")] static extern int ManjongSocketState(int id);
        [DllImport("__Internal")] static extern void ManjongSocketClose(int id);

        int id;
        bool closed = true;

        public void Connect(string url)
        {
            Close();
            id = ManjongSocketConnect(url);
            closed = false;
        }

        public bool Send(string text)
        {
            if (closed || id == 0) return false;
            return ManjongSocketSend(id, text) == 1;
        }

        public bool TryDequeue(out SocketEvent ev)
        {
            ev = default(SocketEvent);
            if (closed || id == 0) return false;
            string raw = ManjongSocketPoll(id);
            if (string.IsNullOrEmpty(raw)) return false;

            char tag = raw[0];
            string payload = raw.Length > 1 ? raw.Substring(1) : "";
            switch (tag)
            {
                case 'o':
                    ev = SocketEvent.Opened();
                    return true;
                case 'm':
                    ev = SocketEvent.Text(payload);
                    return true;
                case 'e':
                    ev = SocketEvent.Failed(payload.Length > 0 ? payload : "browser WebSocket error");
                    return true;
                case 'c':
                    int code;
                    if (!int.TryParse(payload, out code)) code = 1006;
                    ev = SocketEvent.Closed(code);
                    ManjongSocketClose(id);
                    closed = true;
                    id = 0;
                    return true;
            }
            return false;
        }

        public void Close()
        {
            if (id != 0) ManjongSocketClose(id);
            id = 0;
            closed = true;
        }
    }
}
#endif

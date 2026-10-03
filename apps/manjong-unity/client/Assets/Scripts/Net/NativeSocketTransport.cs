#if !(UNITY_WEBGL && !UNITY_EDITOR)
using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Manjong.Net
{
    /// <summary>
    /// Editor / desktop WebSocket on System.Net.WebSockets.ClientWebSocket.
    /// Each Connect() creates a Session owning its own socket, cancellation token, outbox and send signal, so
    /// nothing is shared across connections. A background task connects, then runs a receive loop (re-assembling
    /// fragmented frames) and a send loop. Everything it produces goes into the session's ConcurrentQueue, which
    /// the main thread drains in Update. A send failure aborts the socket so the normal close / reconnect path
    /// runs (no silently dropped messages, Send() returns false from then on).
    /// Close() cancels the token and aborts the socket; both loops end and no thread outlives the session.
    /// This file is excluded from WebGL player builds (browsers have no sockets; see WebGLSocketTransport).
    /// </summary>
    public class NativeSocketTransport : ISocketTransport
    {
        const int ConnectTimeoutMs = 10000;
        const int ReceiveBufferSize = 16 * 1024;

        sealed class Session
        {
            public readonly ClientWebSocket socket = new ClientWebSocket();
            public readonly CancellationTokenSource cts = new CancellationTokenSource();
            public readonly SemaphoreSlim sendSignal = new SemaphoreSlim(0);
            public readonly ConcurrentQueue<string> outbox = new ConcurrentQueue<string>();
            public readonly ConcurrentQueue<SocketEvent> inbox = new ConcurrentQueue<SocketEvent>();
            /// <summary>True between a successful connect and the first failure / close.</summary>
            public volatile bool open;
            /// <summary>Set by Close(); the session's events are no longer wanted.</summary>
            public volatile bool discarded;

            public void Post(SocketEvent ev)
            {
                if (!discarded) inbox.Enqueue(ev);
            }

            /// <summary>Stops the session from any thread: no more sends, pending I/O completes with an exception.</summary>
            public void Kill()
            {
                open = false;
                try
                {
                    cts.Cancel();
                }
                catch (ObjectDisposedException)
                {
                }
                try
                {
                    socket.Abort();
                }
                catch (Exception)
                {
                }
            }
        }

        Session current;

        public void Connect(string url)
        {
            Close();
            var session = new Session();
            current = session;
            Task.Run(() => RunAsync(session, url));
        }

        public bool Send(string text)
        {
            Session s = current;
            if (s == null || !s.open) return false;
            s.outbox.Enqueue(text);
            try
            {
                s.sendSignal.Release();
            }
            catch (ObjectDisposedException)
            {
                return false;
            }
            return s.open;
        }

        public bool TryDequeue(out SocketEvent ev)
        {
            Session s = current;
            if (s != null && s.inbox.TryDequeue(out ev)) return true;
            ev = default(SocketEvent);
            return false;
        }

        public void Close()
        {
            Session s = current;
            current = null;
            if (s == null) return;
            s.discarded = true;
            s.Kill();
        }

        static async Task RunAsync(Session s, string url)
        {
            int closeCode = 1006;
            try
            {
                using (var connectTimeout = CancellationTokenSource.CreateLinkedTokenSource(s.cts.Token))
                {
                    connectTimeout.CancelAfter(ConnectTimeoutMs);
                    await s.socket.ConnectAsync(new Uri(url), connectTimeout.Token).ConfigureAwait(false);
                }
                s.open = true;
                s.Post(SocketEvent.Opened());

                using (var sendCts = CancellationTokenSource.CreateLinkedTokenSource(s.cts.Token))
                {
                    Task sendLoop = SendLoopAsync(s, sendCts.Token);
                    try
                    {
                        closeCode = await ReceiveLoopAsync(s).ConfigureAwait(false);
                    }
                    finally
                    {
                        // The receive side ended (close frame, error or cancel): stop the send loop too,
                        // otherwise it would wait on the semaphore forever.
                        sendCts.Cancel();
                        try
                        {
                            await sendLoop.ConfigureAwait(false);
                        }
                        catch (Exception)
                        {
                            // Ends with OperationCanceledException by design.
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                if (!s.cts.IsCancellationRequested) s.Post(SocketEvent.Failed("connect timeout"));
            }
            catch (Exception e)
            {
                s.Post(SocketEvent.Failed(e.GetType().Name + ": " + e.Message));
            }
            finally
            {
                s.open = false;
                try
                {
                    s.socket.Dispose();
                }
                catch (Exception)
                {
                }
                try
                {
                    s.sendSignal.Dispose();
                }
                catch (Exception)
                {
                }
                s.Post(SocketEvent.Closed(closeCode));
            }
        }

        static async Task<int> ReceiveLoopAsync(Session s)
        {
            var buffer = new ArraySegment<byte>(new byte[ReceiveBufferSize]);
            CancellationToken token = s.cts.Token;
            using (var message = new MemoryStream())
            {
                while (!token.IsCancellationRequested && s.socket.State == WebSocketState.Open)
                {
                    WebSocketReceiveResult result = await s.socket.ReceiveAsync(buffer, token).ConfigureAwait(false);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        s.open = false;
                        int code = result.CloseStatus.HasValue ? (int)result.CloseStatus.Value : 1005;
                        try
                        {
                            await s.socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None).ConfigureAwait(false);
                        }
                        catch (Exception)
                        {
                        }
                        return code;
                    }

                    message.Write(buffer.Array, buffer.Offset, result.Count);
                    if (!result.EndOfMessage) continue; // fragmented frame: keep accumulating

                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        string text = Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length);
                        s.Post(SocketEvent.Text(text));
                    }
                    message.SetLength(0);
                }
            }
            return 1006;
        }

        static async Task SendLoopAsync(Session s, CancellationToken token)
        {
            try
            {
                while (!token.IsCancellationRequested)
                {
                    await s.sendSignal.WaitAsync(token).ConfigureAwait(false);
                    string text;
                    while (s.outbox.TryDequeue(out text))
                    {
                        byte[] bytes = Encoding.UTF8.GetBytes(text);
                        await s.socket.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, token).ConfigureAwait(false);
                    }
                }
            }
            catch (OperationCanceledException)
            {
                // Normal shutdown.
            }
            catch (Exception e)
            {
                // A failed send means the connection is unusable: abort so the receive loop ends and the owner
                // sees Error + Close and reconnects, instead of messages vanishing while Send() keeps saying true.
                s.Post(SocketEvent.Failed("send failed: " + e.GetType().Name + ": " + e.Message));
                s.Kill();
            }
        }
    }
}
#endif

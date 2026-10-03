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
    /// A background task connects, then runs a receive loop (re-assembling fragmented frames) and a send loop.
    /// Everything it produces goes through a ConcurrentQueue that the main thread drains in Update.
    /// Close() cancels the token, aborts the socket and lets both loops end; no thread outlives it.
    /// This file is excluded from WebGL player builds (browsers have no sockets; see WebGLSocketTransport).
    /// </summary>
    public class NativeSocketTransport : ISocketTransport
    {
        const int ConnectTimeoutMs = 10000;
        const int ReceiveBufferSize = 16 * 1024;

        struct Tagged
        {
            public int generation;
            public SocketEvent ev;
        }

        readonly ConcurrentQueue<Tagged> inbox = new ConcurrentQueue<Tagged>();
        readonly ConcurrentQueue<string> outbox = new ConcurrentQueue<string>();

        ClientWebSocket socket;
        CancellationTokenSource cts;
        SemaphoreSlim sendSignal;
        int generation;
        volatile bool open;

        public void Connect(string url)
        {
            Close();
            ClearQueues();

            generation++;
            int myGeneration = generation;
            cts = new CancellationTokenSource();
            socket = new ClientWebSocket();
            sendSignal = new SemaphoreSlim(0);

            ClientWebSocket ws = socket;
            CancellationToken token = cts.Token;
            SemaphoreSlim signal = sendSignal;
            Task.Run(() => RunAsync(ws, url, token, signal, myGeneration));
        }

        public bool Send(string text)
        {
            if (!open || socket == null || sendSignal == null) return false;
            outbox.Enqueue(text);
            try
            {
                sendSignal.Release();
            }
            catch (ObjectDisposedException)
            {
                return false;
            }
            return true;
        }

        public bool TryDequeue(out SocketEvent ev)
        {
            Tagged t;
            while (inbox.TryDequeue(out t))
            {
                // Drop anything produced by a socket that has since been closed or replaced.
                if (t.generation != generation) continue;
                ev = t.ev;
                return true;
            }
            ev = default(SocketEvent);
            return false;
        }

        public void Close()
        {
            open = false;
            generation++; // events from the old socket are dropped from now on
            if (cts != null)
            {
                try
                {
                    cts.Cancel();
                }
                catch (ObjectDisposedException)
                {
                }
            }
            if (socket != null)
            {
                // Abort is immediate and makes any pending ReceiveAsync / SendAsync complete with an exception.
                try
                {
                    socket.Abort();
                }
                catch (Exception)
                {
                }
            }
            socket = null;
            cts = null;
            sendSignal = null;
            ClearQueues();
        }

        void ClearQueues()
        {
            Tagged ignoredEvent;
            while (inbox.TryDequeue(out ignoredEvent))
            {
            }
            string ignoredText;
            while (outbox.TryDequeue(out ignoredText))
            {
            }
        }

        void Post(int myGeneration, SocketEvent ev)
        {
            // Events are tagged; TryDequeue discards those whose generation is no longer current.
            if (myGeneration == Volatile.Read(ref generation)) inbox.Enqueue(new Tagged { generation = myGeneration, ev = ev });
        }

        async Task RunAsync(ClientWebSocket ws, string url, CancellationToken token, SemaphoreSlim signal, int myGeneration)
        {
            int closeCode = 1006;
            try
            {
                using (var connectTimeout = CancellationTokenSource.CreateLinkedTokenSource(token))
                {
                    connectTimeout.CancelAfter(ConnectTimeoutMs);
                    await ws.ConnectAsync(new Uri(url), connectTimeout.Token).ConfigureAwait(false);
                }
                open = myGeneration == Volatile.Read(ref generation);
                Post(myGeneration, SocketEvent.Opened());

                using (var sendCts = CancellationTokenSource.CreateLinkedTokenSource(token))
                {
                    Task sendLoop = SendLoopAsync(ws, sendCts.Token, signal);
                    try
                    {
                        closeCode = await ReceiveLoopAsync(ws, token, myGeneration).ConfigureAwait(false);
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
                            // Ends with OperationCanceledException / WebSocketException by design.
                        }
                    }
                }
            }
            catch (OperationCanceledException)
            {
                if (!token.IsCancellationRequested) Post(myGeneration, SocketEvent.Failed("connect timeout"));
            }
            catch (Exception e)
            {
                Post(myGeneration, SocketEvent.Failed(e.GetType().Name + ": " + e.Message));
            }
            finally
            {
                if (myGeneration == Volatile.Read(ref generation)) open = false;
                try
                {
                    ws.Dispose();
                }
                catch (Exception)
                {
                }
                try
                {
                    signal.Dispose();
                }
                catch (Exception)
                {
                }
                Post(myGeneration, SocketEvent.Closed(closeCode));
            }
        }

        async Task<int> ReceiveLoopAsync(ClientWebSocket ws, CancellationToken token, int myGeneration)
        {
            var buffer = new ArraySegment<byte>(new byte[ReceiveBufferSize]);
            using (var message = new MemoryStream())
            {
                while (!token.IsCancellationRequested && ws.State == WebSocketState.Open)
                {
                    WebSocketReceiveResult result = await ws.ReceiveAsync(buffer, token).ConfigureAwait(false);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        int code = result.CloseStatus.HasValue ? (int)result.CloseStatus.Value : 1005;
                        try
                        {
                            await ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "", CancellationToken.None).ConfigureAwait(false);
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
                        Post(myGeneration, SocketEvent.Text(text));
                    }
                    message.SetLength(0);
                }
            }
            return 1006;
        }

        async Task SendLoopAsync(ClientWebSocket ws, CancellationToken token, SemaphoreSlim signal)
        {
            while (!token.IsCancellationRequested)
            {
                await signal.WaitAsync(token).ConfigureAwait(false);
                string text;
                while (outbox.TryDequeue(out text))
                {
                    byte[] bytes = Encoding.UTF8.GetBytes(text);
                    await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, token).ConfigureAwait(false);
                }
            }
        }
    }
}
#endif

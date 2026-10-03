// WebGL-only WebSocket bridge (no third-party packages, no SendMessage callbacks).
// Every socket gets an integer id. Browser events are queued per socket as prefixed strings and the C# side
// polls them once per frame with ManjongSocketPoll:
//   "o"          open
//   "m<text>"    text message
//   "e<reason>"  error (always followed by a close event)
//   "c<code>"    close (last event of a socket)
// ManjongSocketPoll returns a null pointer when the queue is empty (C# sees null).
var ManjongSocketLib = {
  $MJS: {
    nextId: 1,
    sockets: {},
    alloc: function (str) {
      var size = lengthBytesUTF8(str) + 1;
      var buffer = _malloc(size);
      stringToUTF8(str, buffer, size);
      return buffer;
    }
  },

  ManjongSocketConnect: function (urlPtr) {
    var url = UTF8ToString(urlPtr);
    var id = MJS.nextId++;
    var entry = { ws: null, queue: [] };
    MJS.sockets[id] = entry;
    var ws;
    try {
      ws = new WebSocket(url);
    } catch (err) {
      entry.queue.push("e" + String(err));
      entry.queue.push("c1006");
      return id;
    }
    entry.ws = ws;
    ws.onopen = function () { entry.queue.push("o"); };
    ws.onmessage = function (ev) {
      if (typeof ev.data === "string") entry.queue.push("m" + ev.data);
    };
    ws.onerror = function () { entry.queue.push("e"); };
    ws.onclose = function (ev) { entry.queue.push("c" + (ev.code || 1006)); };
    return id;
  },

  ManjongSocketSend: function (id, textPtr) {
    var entry = MJS.sockets[id];
    if (!entry || !entry.ws || entry.ws.readyState !== 1) return 0;
    try {
      entry.ws.send(UTF8ToString(textPtr));
      return 1;
    } catch (err) {
      return 0;
    }
  },

  ManjongSocketPoll: function (id) {
    var entry = MJS.sockets[id];
    if (!entry || entry.queue.length === 0) return 0;
    return MJS.alloc(entry.queue.shift());
  },

  // 0 connecting, 1 open, 2 closing, 3 closed (same as WebSocket.readyState); 3 for unknown ids.
  ManjongSocketState: function (id) {
    var entry = MJS.sockets[id];
    if (!entry || !entry.ws) return 3;
    return entry.ws.readyState;
  },

  ManjongSocketClose: function (id) {
    var entry = MJS.sockets[id];
    if (!entry) return;
    delete MJS.sockets[id];
    if (entry.ws) {
      entry.ws.onopen = null;
      entry.ws.onmessage = null;
      entry.ws.onerror = null;
      entry.ws.onclose = null;
      try { entry.ws.close(1000); } catch (err) { }
    }
  }
};

autoAddDeps(ManjongSocketLib, "$MJS");
mergeInto(LibraryManager.library, ManjongSocketLib);

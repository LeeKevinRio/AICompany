// WebGL-only bridge: the legacy uGUI InputField cannot receive IME (Chinese) composition in browsers,
// so the lobby offers window.prompt() as an alternative way to type a nickname.
// Return value: the typed text, "\u0001" when the user cancelled, "\u0002" when the browser blocked the dialog.
// Browsers return null for both cancel and block (e.g. sandboxed iframes without allow-modals); a blocked
// prompt returns immediately, so a null answer within 80 ms is treated as "blocked".
mergeInto(LibraryManager.library, {
  ManjongPrompt: function (messagePtr, defaultPtr) {
    var message = UTF8ToString(messagePtr);
    var defaultValue = UTF8ToString(defaultPtr);
    var started = Date.now();
    var result = null;
    try {
      result = window.prompt(message, defaultValue);
    } catch (err) {
      result = null;
      started = Date.now();
    }
    if (result === null || result === undefined) {
      result = (Date.now() - started) < 80 ? "\u0002" : "\u0001";
    }
    var size = lengthBytesUTF8(result) + 1;
    var buffer = _malloc(size);
    stringToUTF8(result, buffer, size);
    return buffer;
  }
});

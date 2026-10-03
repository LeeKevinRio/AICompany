// WebGL-only bridge: the legacy uGUI InputField cannot receive IME (Chinese) composition in browsers,
// so the lobby offers window.prompt() as an alternative way to type a nickname.
mergeInto(LibraryManager.library, {
  ManjongPrompt: function (messagePtr, defaultPtr) {
    var message = UTF8ToString(messagePtr);
    var defaultValue = UTF8ToString(defaultPtr);
    var result = window.prompt(message, defaultValue);
    // Distinguish "cancel" from an empty answer with a sentinel the C# side checks.
    if (result === null || result === undefined) {
      result = "\u0001";
    }
    var size = lengthBytesUTF8(result) + 1;
    var buffer = _malloc(size);
    stringToUTF8(result, buffer, size);
    return buffer;
  }
});

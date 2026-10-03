#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace Manjong.UI
{
    public enum PromptStatus
    {
        Ok,
        Cancelled,
        /// <summary>The browser refused to show the dialog (or the platform has none).</summary>
        Blocked
    }

    /// <summary>
    /// Browser text prompt used on WebGL so players can type Chinese via the OS IME.
    /// On other platforms IsAvailable is false and the regular InputField is used.
    /// </summary>
    public static class WebPrompt
    {
        const string CancelSentinel = "\u0001";
        const string BlockedSentinel = "\u0002";

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        static extern string ManjongPrompt(string message, string defaultValue);
#endif

        public static bool IsAvailable
        {
            get
            {
#if UNITY_WEBGL && !UNITY_EDITOR
                return true;
#else
                return false;
#endif
            }
        }

        /// <summary>Shows a blocking prompt. "text" is only meaningful when the status is Ok.</summary>
        public static PromptStatus Ask(string message, string defaultValue, out string text)
        {
            text = null;
#if UNITY_WEBGL && !UNITY_EDITOR
            string result = ManjongPrompt(message ?? "", defaultValue ?? "");
            if (result == null || result == BlockedSentinel) return PromptStatus.Blocked;
            if (result == CancelSentinel) return PromptStatus.Cancelled;
            text = result;
            return PromptStatus.Ok;
#else
            return PromptStatus.Blocked;
#endif
        }
    }
}

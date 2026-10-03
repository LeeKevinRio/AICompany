#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

namespace Manjong.UI
{
    /// <summary>
    /// Browser text prompt used on WebGL so players can type Chinese via the OS IME.
    /// On other platforms IsAvailable is false and the regular InputField is used.
    /// </summary>
    public static class WebPrompt
    {
        const string CancelSentinel = "\u0001";

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

        /// <summary>Shows a blocking prompt. Returns null when cancelled or unavailable.</summary>
        public static string Ask(string message, string defaultValue)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            string result = ManjongPrompt(message ?? "", defaultValue ?? "");
            if (result == null || result == CancelSentinel) return null;
            return result;
#else
            return null;
#endif
        }
    }
}

using UnityEngine;

namespace Manjong.Net
{
    /// <summary>Guest token persisted in PlayerPrefs (IndexedDB on WebGL).</summary>
    public static class TokenStore
    {
        public const string Key = "manjong.token";

        public static string Load()
        {
            return PlayerPrefs.GetString(Key, "");
        }

        public static void Save(string token)
        {
            PlayerPrefs.SetString(Key, token ?? "");
            PlayerPrefs.Save();
        }

        public static void Clear()
        {
            PlayerPrefs.DeleteKey(Key);
            PlayerPrefs.Save();
        }
    }
}

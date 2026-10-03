using System;
using UnityEngine;

namespace Manjong.Net
{
    /// <summary>
    /// Resolves the backend base URL.
    /// WebGL: the page origin (same-origin hosting). The "?api=&lt;url&gt;" override is honoured only when the
    /// page itself is served from localhost, so a crafted link cannot send the guest token to another server.
    /// Editor / other platforms: the MANJONG_API_URL environment variable if set (e.g. when the backend runs on
    /// another port), otherwise http://127.0.0.1:7316 (the backend binds to loopback by default).
    /// </summary>
    public static class ApiConfig
    {
        public const string DefaultBaseUrl = "http://127.0.0.1:7316";

        static string cachedBaseUrl;

        public static string BaseUrl
        {
            get
            {
                if (string.IsNullOrEmpty(cachedBaseUrl)) cachedBaseUrl = Resolve();
                return cachedBaseUrl;
            }
        }

        static string Resolve()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            string pageUrl = Application.absoluteURL;
            if (!string.IsNullOrEmpty(pageUrl))
            {
                Uri uri;
                if (Uri.TryCreate(pageUrl, UriKind.Absolute, out uri))
                {
                    string apiParam = GetQueryParam(pageUrl, "api");
                    if (!string.IsNullOrEmpty(apiParam) && IsLoopback(uri.Host)) return TrimTrailingSlash(apiParam);
                    // scheme://host[:port]
                    return uri.GetLeftPart(UriPartial.Authority);
                }
            }
            Debug.LogWarning("[Manjong] Could not derive API origin from page URL, falling back to " + DefaultBaseUrl);
#else
            string fromEnv = Environment.GetEnvironmentVariable("MANJONG_API_URL");
            if (!string.IsNullOrEmpty(fromEnv)) return TrimTrailingSlash(fromEnv.Trim());
#endif
            return DefaultBaseUrl;
        }

        /// <summary>Returns the unescaped value of a query parameter, or "" when absent.</summary>
        public static string GetQueryParam(string url, string key)
        {
            if (string.IsNullOrEmpty(url)) return "";
            int q = url.IndexOf('?');
            if (q < 0 || q == url.Length - 1) return "";
            string query = url.Substring(q + 1);
            int hash = query.IndexOf('#');
            if (hash >= 0) query = query.Substring(0, hash);

            string[] pairs = query.Split('&');
            for (int i = 0; i < pairs.Length; i++)
            {
                string pair = pairs[i];
                if (pair.Length == 0) continue;
                int eq = pair.IndexOf('=');
                string k = eq >= 0 ? pair.Substring(0, eq) : pair;
                if (!string.Equals(k, key, StringComparison.Ordinal)) continue;
                string v = eq >= 0 ? pair.Substring(eq + 1) : "";
                try
                {
                    return Uri.UnescapeDataString(v.Replace('+', ' '));
                }
                catch (Exception)
                {
                    return v;
                }
            }
            return "";
        }

        static bool IsLoopback(string host)
        {
            return host == "localhost" || host == "127.0.0.1" || host == "[::1]" || host == "::1";
        }

        static string TrimTrailingSlash(string s)
        {
            while (s.Length > 0 && s[s.Length - 1] == '/') s = s.Substring(0, s.Length - 1);
            return s;
        }
    }
}

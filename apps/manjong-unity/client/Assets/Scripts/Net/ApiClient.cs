using System;
using System.Collections;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

namespace Manjong.Net
{
    public class ApiError
    {
        /// <summary>HTTP status code; 0 for transport failures.</summary>
        public long status;
        public string code;
        public string message;
        /// <summary>True when the server could not be reached at all.</summary>
        public bool isNetwork;
    }

    /// <summary>
    /// Thin UnityWebRequest wrapper. Coroutine based (WebGL is single threaded, no async/await).
    /// Owns the guest token persisted in PlayerPrefs.
    /// </summary>
    public class ApiClient
    {
        public const string TokenKey = "manjong.token";
        const int TimeoutSeconds = 20;

        public string Token { get; private set; }

        public ApiClient()
        {
            Token = PlayerPrefs.GetString(TokenKey, "");
        }

        public bool HasToken
        {
            get { return !string.IsNullOrEmpty(Token); }
        }

        public void SetToken(string token)
        {
            Token = token ?? "";
            PlayerPrefs.SetString(TokenKey, Token);
            PlayerPrefs.Save();
        }

        public void ClearToken()
        {
            Token = "";
            PlayerPrefs.DeleteKey(TokenKey);
            PlayerPrefs.Save();
        }

        public IEnumerator Get<T>(string path, Action<T> onOk, Action<ApiError> onError) where T : class
        {
            return Send("GET", path, null, onOk, onError);
        }

        public IEnumerator Post<T>(string path, string jsonBody, Action<T> onOk, Action<ApiError> onError) where T : class
        {
            return Send("POST", path, string.IsNullOrEmpty(jsonBody) ? "{}" : jsonBody, onOk, onError);
        }

        IEnumerator Send<T>(string method, string path, string jsonBody, Action<T> onOk, Action<ApiError> onError) where T : class
        {
            string url = ApiConfig.BaseUrl + path;
            T data = null;
            ApiError error = null;

            UnityWebRequest req;
            if (method == "GET")
            {
                req = UnityWebRequest.Get(url);
            }
            else
            {
                req = new UnityWebRequest(url, method);
                byte[] body = Encoding.UTF8.GetBytes(jsonBody ?? "{}");
                req.uploadHandler = new UploadHandlerRaw(body);
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
            }
            req.SetRequestHeader("Accept", "application/json");
            if (HasToken) req.SetRequestHeader("Authorization", "Bearer " + Token);
            req.timeout = TimeoutSeconds;

            using (req)
            {
                yield return req.SendWebRequest();

                string text = req.downloadHandler != null ? req.downloadHandler.text : "";

                if (req.result == UnityWebRequest.Result.Success)
                {
                    data = ParseOrNull<T>(text);
                    if (data == null)
                    {
                        error = new ApiError
                        {
                            status = req.responseCode,
                            code = "BAD_RESPONSE",
                            message = "伺服器回傳的資料格式不正確",
                            isNetwork = false
                        };
                    }
                }
                else if (req.result == UnityWebRequest.Result.ProtocolError)
                {
                    error = ParseError(req.responseCode, text);
                }
                else
                {
                    // ConnectionError (unreachable, CORS blocked, timeout) or DataProcessingError.
                    error = new ApiError
                    {
                        status = req.responseCode,
                        code = "NETWORK",
                        message = "連不上伺服器",
                        isNetwork = true
                    };
                    Debug.LogWarning("[Manjong] " + method + " " + url + " failed: " + req.error);
                }
            }

            if (error == null)
            {
                if (onOk != null) onOk(data);
            }
            else
            {
                if (onError != null) onError(error);
            }
        }

        static T ParseOrNull<T>(string text) where T : class
        {
            if (string.IsNullOrEmpty(text)) return null;
            try
            {
                return JsonUtility.FromJson<T>(text);
            }
            catch (Exception e)
            {
                Debug.LogWarning("[Manjong] JSON parse failed: " + e.Message);
                return null;
            }
        }

        static ApiError ParseError(long status, string text)
        {
            var err = new ApiError { status = status, code = "HTTP_" + status, message = "", isNetwork = false };
            ErrorEnvelope env = ParseOrNull<ErrorEnvelope>(text);
            if (env != null && env.error != null)
            {
                if (!string.IsNullOrEmpty(env.error.code)) err.code = env.error.code;
                if (!string.IsNullOrEmpty(env.error.message)) err.message = env.error.message;
            }
            if (string.IsNullOrEmpty(err.message))
            {
                err.message = status >= 500 ? "伺服器發生錯誤（" + status + "），請稍後再試" : "請求失敗（" + status + "）";
            }
            return err;
        }
    }
}

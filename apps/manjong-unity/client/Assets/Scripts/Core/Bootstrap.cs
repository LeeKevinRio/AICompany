using UnityEngine;

namespace Manjong.Core
{
    /// <summary>
    /// Code-only entry point: no hand-made scene objects or prefabs are required.
    /// Runs after the first scene loads and spawns the persistent AppController.
    /// </summary>
    public static class Bootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init()
        {
            if (Object.FindAnyObjectByType<AppController>() != null) return;

            var go = new GameObject("ManjongApp");
            Object.DontDestroyOnLoad(go);
            go.AddComponent<AppController>();
        }
    }
}

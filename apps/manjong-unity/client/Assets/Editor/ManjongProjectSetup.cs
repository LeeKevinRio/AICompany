#if UNITY_EDITOR
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

/// <summary>
/// First-open project setup. Creates Assets/Scenes/Main.unity only when it does not exist yet
/// (never overwrites a user scene), registers it in Build Settings and applies WebGL player settings.
/// Also available from the menu: Manjong/Setup Project.
/// </summary>
[InitializeOnLoad]
public static class ManjongProjectSetup
{
    public const string ScenePath = "Assets/Scenes/Main.unity";
    public const string ProductName = "manjong-unity";
    const string TileFolder = "Assets/Resources/Tiles";
    const string CheckedThisSessionKey = "Manjong.ProjectSetupChecked";

    static ManjongProjectSetup()
    {
        EditorApplication.delayCall += AutoSetup;
    }

    static string ProjectRoot
    {
        get { return Directory.GetParent(Application.dataPath).FullName; }
    }

    static bool SceneExists
    {
        get { return File.Exists(Path.Combine(ProjectRoot, ScenePath)); }
    }

    static void AutoSetup()
    {
        if (Application.isBatchMode) return;
        if (EditorApplication.isPlayingOrWillChangePlaymode) return;
        if (SessionState.GetBool(CheckedThisSessionKey, false)) return;
        SessionState.SetBool(CheckedThisSessionKey, true);

        if (SceneExists) return;

        Debug.Log("[Manjong] Main scene not found, running first-time project setup.");
        Run(false);
    }

    [MenuItem("Manjong/Setup Project")]
    public static void SetupFromMenu()
    {
        Run(true);
    }

    /// <summary>Creates the scene if missing, then makes sure Build Settings and Player Settings are correct.</summary>
    public static void Run(bool openSceneIfExists)
    {
        if (!SceneExists)
        {
            if (!CreateMainScene()) return;
        }
        else if (openSceneIfExists && !Application.isBatchMode)
        {
            if (EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            }
        }

        EnsureBuildSettings();
        ApplyPlayerSettings();
        // On a fresh checkout the tile images can be imported before ManjongTileImporter compiles; force a
        // reimport so they pick up the intended settings (mipmaps, uncompressed).
        if (AssetDatabase.IsValidFolder(TileFolder))
        {
            AssetDatabase.ImportAsset(TileFolder, ImportAssetOptions.ImportRecursive | ImportAssetOptions.ForceUpdate);
        }
        WarnAboutInputHandling();
        AssetDatabase.SaveAssets();
        Debug.Log("[Manjong] Project setup done. Press Play (start the backend first) or use Manjong/Build WebGL.");
    }

    static bool CreateMainScene()
    {
        if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
        {
            Debug.LogWarning("[Manjong] Setup cancelled: the current scene has unsaved changes.");
            return false;
        }

        Directory.CreateDirectory(Path.Combine(ProjectRoot, "Assets/Scenes"));
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        if (!EditorSceneManager.SaveScene(scene, ScenePath))
        {
            Debug.LogError("[Manjong] Failed to save " + ScenePath);
            return false;
        }
        AssetDatabase.Refresh();
        Debug.Log("[Manjong] Created " + ScenePath + ". All UI is built from code at runtime.");
        return true;
    }

    public static void EnsureBuildSettings()
    {
        var scenes = new List<EditorBuildSettingsScene>(EditorBuildSettings.scenes);
        bool found = false;
        for (int i = 0; i < scenes.Count; i++)
        {
            if (scenes[i].path == ScenePath)
            {
                found = true;
                if (!scenes[i].enabled)
                {
                    scenes[i] = new EditorBuildSettingsScene(ScenePath, true);
                }
            }
        }
        if (!found) scenes.Insert(0, new EditorBuildSettingsScene(ScenePath, true));
        EditorBuildSettings.scenes = scenes.ToArray();
    }

    public static void ApplyPlayerSettings()
    {
        PlayerSettings.productName = ProductName;
        PlayerSettings.runInBackground = true;
        // Uncompressed output so the backend can serve the build without Content-Encoding headers.
        PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Disabled;
        // 16:9 default canvas; the layout is designed for a 1920x1080 reference resolution.
        PlayerSettings.defaultWebScreenWidth = 1280;
        PlayerSettings.defaultWebScreenHeight = 720;
    }

    static void WarnAboutInputHandling()
    {
#if !ENABLE_LEGACY_INPUT_MANAGER
        Debug.LogWarning("[Manjong] The UI uses StandaloneInputModule (legacy Input Manager). " +
                         "Set Edit > Project Settings > Player > Active Input Handling to \"Input Manager (Old)\" or \"Both\".");
#endif
    }
}
#endif

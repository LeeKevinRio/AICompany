#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

/// <summary>
/// Menu: Manjong/Build WebGL. Outputs to &lt;project root&gt;/Build/WebGL, which the backend serves
/// by default (WEBGL_DIR=../client/Build/WebGL).
/// Batch mode: Unity -batchmode -quit -projectPath . -executeMethod ManjongBuild.BuildWebGL
/// </summary>
public static class ManjongBuild
{
    [MenuItem("Manjong/Build WebGL")]
    public static void BuildWebGL()
    {
        ManjongProjectSetup.Run(false);

        string projectRoot = Directory.GetParent(Application.dataPath).FullName;
        string outputDir = Path.Combine(Path.Combine(projectRoot, "Build"), "WebGL");
        Directory.CreateDirectory(outputDir);

        var options = new BuildPlayerOptions
        {
            scenes = new[] { ManjongProjectSetup.ScenePath },
            locationPathName = outputDir,
            target = BuildTarget.WebGL,
            targetGroup = BuildTargetGroup.WebGL,
            options = BuildOptions.None
        };

        BuildReport report = BuildPipeline.BuildPlayer(options);
        BuildSummary summary = report.summary;
        if (summary.result == BuildResult.Succeeded)
        {
            Debug.Log("[Manjong] WebGL build succeeded: " + outputDir + " (" + (summary.totalSize / (1024 * 1024)) + " MB)");
            if (!Application.isBatchMode) EditorUtility.RevealInFinder(outputDir);
        }
        else
        {
            Debug.LogError("[Manjong] WebGL build " + summary.result + " with " + summary.totalErrors + " error(s).");
            if (Application.isBatchMode) EditorApplication.Exit(1);
        }
    }
}
#endif

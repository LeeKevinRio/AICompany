#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

/// <summary>
/// Import settings for the painted tile images in Assets/Resources/Tiles/ (150x200 px, transparent corners):
/// mipmaps with a Kaiser filter (tiles are drawn as small as ~22 px at 1280x720, so plain bilinear without
/// mipmaps aliases badly), uncompressed, trilinear, alpha is transparency, no power-of-two rescale, clamped.
/// Platform overrides are cleared so WebGL / Standalone use the same uncompressed settings.
/// </summary>
public class ManjongTileImporter : AssetPostprocessor
{
    const string TileFolder = "Assets/Resources/Tiles/";

    void OnPreprocessTexture()
    {
        string path = assetPath.Replace('\\', '/');
        if (!path.StartsWith(TileFolder)) return;

        var importer = (TextureImporter)assetImporter;
        importer.textureType = TextureImporterType.Default;
        importer.mipmapEnabled = true;
        importer.mipmapFilter = TextureImporterMipFilter.KaiserFilter;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.filterMode = FilterMode.Trilinear;
        importer.alphaIsTransparency = true;
        importer.npotScale = TextureImporterNPOTScale.None;
        importer.wrapMode = TextureWrapMode.Clamp;
        importer.isReadable = false;
        importer.ClearPlatformTextureSettings("WebGL");
        importer.ClearPlatformTextureSettings("Standalone");
    }
}
#endif

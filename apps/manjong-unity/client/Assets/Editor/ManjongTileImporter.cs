#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;

/// <summary>
/// Import settings for the painted images in Assets/Resources:
///  - Tiles/ (150x200 px, transparent corners): mipmaps with a Kaiser filter (tiles are drawn as small as ~22 px at
///    1280x720, so plain bilinear without mipmaps aliases badly), uncompressed, trilinear, alpha is transparency, no
///    power-of-two rescale, clamped.
///  - Table/ (tools/render_table.py): uncompressed (compression would band the gradients and the vignette), no
///    power-of-two rescale, alpha is transparency. felt.png is a seamless tile drawn with Image.Type.Tiled, so it repeats
///    (and wraps its bilinear taps at the seams) and gets mipmaps; frame.png / console.png are single sprites drawn near 1:1,
///    mipmapped too (they are scaled down on small screens); felt_shade.png is a smooth gradient stretched over the felt:
///    bilinear, no mipmaps.
/// Platform overrides are cleared so WebGL / Standalone use the same uncompressed settings.
/// </summary>
public class ManjongTileImporter : AssetPostprocessor
{
    const string TileFolder = "Assets/Resources/Tiles/";
    const string TableFolder = "Assets/Resources/Table/";

    void OnPreprocessTexture()
    {
        string path = assetPath.Replace('\\', '/');
        bool tile = path.StartsWith(TileFolder);
        bool table = path.StartsWith(TableFolder);
        if (!tile && !table) return;

        var importer = (TextureImporter)assetImporter;
        importer.textureType = TextureImporterType.Default;
        importer.textureCompression = TextureImporterCompression.Uncompressed;
        importer.alphaIsTransparency = true;
        importer.npotScale = TextureImporterNPOTScale.None;
        importer.isReadable = false;

        if (tile)
        {
            importer.mipmapEnabled = true;
            importer.mipmapFilter = TextureImporterMipFilter.KaiserFilter;
            importer.filterMode = FilterMode.Trilinear;
            importer.wrapMode = TextureWrapMode.Clamp;
        }
        else
        {
            bool shade = path.EndsWith("felt_shade.png");
            bool felt = path.EndsWith("/felt.png");
            importer.mipmapEnabled = !shade;
            importer.mipmapFilter = TextureImporterMipFilter.KaiserFilter;
            importer.filterMode = shade ? FilterMode.Bilinear : FilterMode.Trilinear;
            importer.wrapMode = felt ? TextureWrapMode.Repeat : TextureWrapMode.Clamp;
        }
        importer.ClearPlatformTextureSettings("WebGL");
        importer.ClearPlatformTextureSettings("Standalone");
    }
}
#endif

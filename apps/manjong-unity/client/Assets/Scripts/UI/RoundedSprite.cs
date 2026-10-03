using System.Collections.Generic;
using UnityEngine;

namespace Manjong.UI
{
    /// <summary>
    /// Generates white anti-aliased rounded-rectangle / ring / circle sprites at runtime and caches them.
    /// Rounded sprites carry a 9-slice border so Image.type = Sliced keeps the corner radius at any size.
    /// Tint them through Image.color.
    /// </summary>
    public static class RoundedSprite
    {
        const float PixelsPerUnit = 100f;
        static readonly Dictionary<string, Sprite> Cache = new Dictionary<string, Sprite>();

        /// <summary>Filled rounded rectangle, corner radius in UI units (canvas reference pixels).</summary>
        public static Sprite Filled(int radius)
        {
            radius = Mathf.Clamp(radius, 1, 128);
            string key = "f" + radius;
            Sprite s;
            if (Cache.TryGetValue(key, out s) && s != null) return s;
            s = Build(radius, 0);
            Cache[key] = s;
            return s;
        }

        /// <summary>Rounded outline ring of the given thickness.</summary>
        public static Sprite Ring(int radius, int thickness)
        {
            radius = Mathf.Clamp(radius, 1, 128);
            thickness = Mathf.Clamp(thickness, 1, radius);
            string key = "r" + radius + "_" + thickness;
            Sprite s;
            if (Cache.TryGetValue(key, out s) && s != null) return s;
            s = Build(radius, thickness);
            Cache[key] = s;
            return s;
        }

        /// <summary>Solid circle (use with Image.type = Simple and a square rect).</summary>
        public static Sprite Circle()
        {
            const string key = "circle";
            Sprite s;
            if (Cache.TryGetValue(key, out s) && s != null) return s;

            const int size = 128;
            var tex = NewTexture(size, size);
            var pixels = new Color32[size * size];
            float c = size * 0.5f;
            float r = size * 0.5f - 1f;
            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float dx = x + 0.5f - c;
                    float dy = y + 0.5f - c;
                    float d = Mathf.Sqrt(dx * dx + dy * dy) - r;
                    byte a = (byte)Mathf.RoundToInt(Mathf.Clamp01(0.5f - d) * 255f);
                    pixels[y * size + x] = new Color32(255, 255, 255, a);
                }
            }
            tex.SetPixels32(pixels);
            tex.Apply(false, true);
            s = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), PixelsPerUnit, 0, SpriteMeshType.FullRect);
            s.name = "ManjongCircle";
            Cache[key] = s;
            return s;
        }

        static Sprite Build(int radius, int ringThickness)
        {
            int size = radius * 2 + 4;
            var tex = NewTexture(size, size);
            var pixels = new Color32[size * size];
            float half = size * 0.5f;

            for (int y = 0; y < size; y++)
            {
                for (int x = 0; x < size; x++)
                {
                    float px = x + 0.5f;
                    float py = y + 0.5f;
                    float outer = Coverage(px, py, half, half, half - 1f, radius);
                    float alpha = outer;
                    if (ringThickness > 0)
                    {
                        float innerRadius = Mathf.Max(radius - ringThickness, 0);
                        float inner = Coverage(px, py, half, half, half - 1f - ringThickness, innerRadius);
                        alpha = outer * (1f - inner);
                    }
                    pixels[y * size + x] = new Color32(255, 255, 255, (byte)Mathf.RoundToInt(alpha * 255f));
                }
            }
            tex.SetPixels32(pixels);
            tex.Apply(false, true);

            float b = radius + 1;
            var sprite = Sprite.Create(
                tex,
                new Rect(0, 0, size, size),
                new Vector2(0.5f, 0.5f),
                PixelsPerUnit,
                0,
                SpriteMeshType.FullRect,
                new Vector4(b, b, b, b));
            sprite.name = ringThickness > 0 ? "ManjongRing" + radius : "ManjongRounded" + radius;
            return sprite;
        }

        /// <summary>Anti-aliased coverage of a rounded rect centred at (cx, cy) with half extent "halfExtent".</summary>
        static float Coverage(float px, float py, float cx, float cy, float halfExtent, float radius)
        {
            float inner = halfExtent - radius;
            float dx = Mathf.Max(Mathf.Abs(px - cx) - inner, 0f);
            float dy = Mathf.Max(Mathf.Abs(py - cy) - inner, 0f);
            float d = Mathf.Sqrt(dx * dx + dy * dy) - radius;
            if (radius <= 0f)
            {
                d = Mathf.Max(Mathf.Abs(px - cx), Mathf.Abs(py - cy)) - halfExtent;
            }
            return Mathf.Clamp01(0.5f - d);
        }

        static Texture2D NewTexture(int w, int h)
        {
            var tex = new Texture2D(w, h, TextureFormat.RGBA32, false);
            tex.wrapMode = TextureWrapMode.Clamp;
            tex.filterMode = FilterMode.Bilinear;
            tex.hideFlags = HideFlags.DontSave;
            return tex;
        }
    }
}

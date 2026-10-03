using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

namespace Manjong.UI
{
    /// <summary>Helpers that build uGUI objects in code (no prefabs, no hand-made scene).</summary>
    public static class UiFactory
    {
        static Font font;

        /// <summary>jf open huninn subset from Resources, falling back to Unity's built-in runtime font.</summary>
        public static Font Font
        {
            get
            {
                if (font != null) return font;
                font = Resources.Load<Font>("Fonts/huninn");
                if (font == null)
                {
                    Debug.LogWarning("[Manjong] Resources/Fonts/huninn not found, falling back to LegacyRuntime.ttf");
                    font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                }
                return font;
            }
        }

        // ---------- RectTransform helpers ----------

        public static RectTransform CreateRect(string name, Transform parent)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.layer = 5; // UI layer
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            return rt;
        }

        /// <summary>Anchor at a single point with pivot, position and size.</summary>
        public static void Place(RectTransform rt, Vector2 anchor, Vector2 pivot, Vector2 position, Vector2 size)
        {
            rt.anchorMin = anchor;
            rt.anchorMax = anchor;
            rt.pivot = pivot;
            rt.sizeDelta = size;
            rt.anchoredPosition = position;
        }

        /// <summary>Stretch to fill the parent with insets (left, top, right, bottom).</summary>
        public static void Stretch(RectTransform rt, float left, float top, float right, float bottom)
        {
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = new Vector2(left, bottom);
            rt.offsetMax = new Vector2(-right, -top);
        }

        public static void Stretch(RectTransform rt)
        {
            Stretch(rt, 0f, 0f, 0f, 0f);
        }

        /// <summary>Anchor horizontally by fraction of the parent width and stretch vertically.</summary>
        public static void Column(RectTransform rt, float fromX, float toX, float padLeft, float padRight)
        {
            rt.anchorMin = new Vector2(fromX, 0f);
            rt.anchorMax = new Vector2(toX, 1f);
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = new Vector2(padLeft, 0f);
            rt.offsetMax = new Vector2(-padRight, 0f);
        }

        public static void DestroyChildren(Transform t)
        {
            if (t == null) return;
            for (int i = t.childCount - 1; i >= 0; i--)
            {
                var child = t.GetChild(i);
                child.gameObject.SetActive(false);
                Object.Destroy(child.gameObject);
            }
        }

        // ---------- Graphics ----------

        public static Image CreatePanel(Transform parent, string name, Color color, int radius)
        {
            var rt = CreateRect(name, parent);
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = RoundedSprite.Filled(radius);
            img.type = Image.Type.Sliced;
            img.color = color;
            img.raycastTarget = false;
            return img;
        }

        /// <summary>Outline ring drawn around the parent, extending "outset" units beyond its rect.</summary>
        public static Image CreateRing(Transform parent, string name, Color color, int radius, int thickness, float outset)
        {
            var rt = CreateRect(name, parent);
            Stretch(rt, -outset, -outset, -outset, -outset);
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = RoundedSprite.Ring(radius, thickness);
            img.type = Image.Type.Sliced;
            img.color = color;
            img.raycastTarget = false;
            return img;
        }

        public static void AddShadow(Graphic g, Color color, Vector2 distance)
        {
            var shadow = g.gameObject.AddComponent<Shadow>();
            shadow.effectColor = color;
            shadow.effectDistance = distance;
            shadow.useGraphicAlpha = true;
        }

        public static Image CreateCircle(Transform parent, string name, Color color)
        {
            var rt = CreateRect(name, parent);
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = RoundedSprite.Circle();
            img.type = Image.Type.Simple;
            img.preserveAspect = true;
            img.color = color;
            img.raycastTarget = false;
            return img;
        }

        /// <summary>Full-screen invisible (or tinted) Image that swallows clicks.</summary>
        public static Image CreateBlocker(Transform parent, string name, Color color)
        {
            var rt = CreateRect(name, parent);
            Stretch(rt);
            var img = rt.gameObject.AddComponent<Image>();
            img.color = color;
            img.raycastTarget = true;
            return img;
        }

        // ---------- Text ----------

        public static Text CreateText(Transform parent, string name, string content, int size, Color color, TextAnchor align)
        {
            var rt = CreateRect(name, parent);
            var t = rt.gameObject.AddComponent<Text>();
            t.font = Font;
            t.text = content ?? "";
            t.fontSize = size;
            t.color = color;
            t.alignment = align;
            t.supportRichText = false;
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Overflow;
            t.lineSpacing = 1.1f;
            t.raycastTarget = false;
            return t;
        }

        /// <summary>Single-line text that shrinks to fit its rect instead of wrapping.</summary>
        public static Text CreateLabel(Transform parent, string name, string content, int size, Color color, TextAnchor align)
        {
            var t = CreateText(parent, name, content, size, color, align);
            t.horizontalOverflow = HorizontalWrapMode.Wrap;
            t.verticalOverflow = VerticalWrapMode.Truncate;
            t.resizeTextForBestFit = true;
            t.resizeTextMinSize = Mathf.Max(10, size / 2);
            t.resizeTextMaxSize = size;
            return t;
        }

        // ---------- Button ----------

        public static Button CreateButton(Transform parent, string name, string label, Color bg, int fontSize, UnityAction onClick)
        {
            var img = CreatePanel(parent, name, bg, 22);
            img.raycastTarget = true;
            AddShadow(img, Palette.CardShadow, new Vector2(0f, -4f));

            var btn = img.gameObject.AddComponent<Button>();
            btn.targetGraphic = img;
            var colors = btn.colors;
            colors.normalColor = Color.white;
            colors.highlightedColor = new Color(0.94f, 0.94f, 0.94f, 1f);
            colors.pressedColor = new Color(0.84f, 0.84f, 0.84f, 1f);
            colors.selectedColor = new Color(0.97f, 0.97f, 0.97f, 1f);
            colors.disabledColor = new Color(0.80f, 0.80f, 0.80f, 0.55f);
            colors.colorMultiplier = 1f;
            colors.fadeDuration = 0.08f;
            btn.colors = colors;
            // Mouse / touch UI: no automatic keyboard navigation that could leave a stray "selected" tint.
            var nav = btn.navigation;
            nav.mode = Navigation.Mode.None;
            btn.navigation = nav;

            var text = CreateLabel(img.transform, "Label", label, fontSize, Palette.Ink, TextAnchor.MiddleCenter);
            Stretch(text.rectTransform, 12f, 4f, 12f, 4f);

            if (onClick != null) btn.onClick.AddListener(onClick);
            return btn;
        }

        public static Text ButtonLabel(Button b)
        {
            return b == null ? null : b.GetComponentInChildren<Text>(true);
        }

        /// <summary>Enable/disable a button and dim its label so the state is visible on two channels.</summary>
        public static void SetInteractable(Button b, bool on)
        {
            if (b == null) return;
            b.interactable = on;
            var label = ButtonLabel(b);
            if (label != null)
            {
                var c = Palette.Ink;
                c.a = on ? 1f : 0.55f;
                label.color = c;
            }
        }

        // ---------- InputField ----------

        public static InputField CreateInput(Transform parent, string name, string placeholder, int fontSize, int characterLimit)
        {
            var bg = CreatePanel(parent, name, Color.white, 18);
            bg.raycastTarget = true;
            CreateRing(bg.transform, "Border", Palette.InkSoft, 18, 2, 0f);

            var text = CreateText(bg.transform, "Text", "", fontSize, Palette.Ink, TextAnchor.MiddleLeft);
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Truncate;
            Stretch(text.rectTransform, 18f, 6f, 18f, 6f);

            var ph = CreateText(bg.transform, "Placeholder", placeholder, fontSize, Palette.InkSoft, TextAnchor.MiddleLeft);
            ph.fontStyle = FontStyle.Italic;
            ph.horizontalOverflow = HorizontalWrapMode.Overflow;
            ph.verticalOverflow = VerticalWrapMode.Truncate;
            Stretch(ph.rectTransform, 18f, 6f, 18f, 6f);

            var input = bg.gameObject.AddComponent<InputField>();
            input.targetGraphic = bg;
            input.textComponent = text;
            input.placeholder = ph;
            input.lineType = InputField.LineType.SingleLine;
            input.characterLimit = characterLimit;
            input.caretColor = Palette.Ink;
            input.customCaretColor = true;
            input.caretWidth = 2;
            input.selectionColor = new Color(0.71f, 0.88f, 0.97f, 0.75f);

            var colors = input.colors;
            colors.normalColor = Color.white;
            colors.highlightedColor = new Color(0.97f, 0.97f, 0.97f, 1f);
            colors.pressedColor = new Color(0.93f, 0.93f, 0.93f, 1f);
            colors.selectedColor = new Color(0.95f, 0.99f, 1f, 1f);
            colors.disabledColor = new Color(0.85f, 0.85f, 0.85f, 0.6f);
            input.colors = colors;
            return input;
        }

        // ---------- ScrollRect ----------

        /// <summary>
        /// Vertical ScrollRect with a RectMask2D viewport and a VerticalLayoutGroup content that grows with its rows.
        /// The returned ScrollRect's rect must be placed by the caller. A slim scrollbar sits on the right.
        /// </summary>
        public static ScrollRect CreateVerticalScroll(Transform parent, string name, out RectTransform content)
        {
            var rootRt = CreateRect(name, parent);
            var rootImg = rootRt.gameObject.AddComponent<Image>();
            rootImg.color = Palette.Transparent;
            rootImg.raycastTarget = true; // catches wheel / drag events over empty space
            var scroll = rootRt.gameObject.AddComponent<ScrollRect>();

            var viewport = CreateRect("Viewport", rootRt);
            Stretch(viewport, 0f, 0f, 22f, 0f);
            viewport.gameObject.AddComponent<RectMask2D>();

            content = CreateRect("Content", viewport);
            content.anchorMin = new Vector2(0f, 1f);
            content.anchorMax = new Vector2(1f, 1f);
            content.pivot = new Vector2(0.5f, 1f);
            content.anchoredPosition = Vector2.zero;
            content.sizeDelta = new Vector2(0f, 0f);
            var layout = content.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.childAlignment = TextAnchor.UpperCenter;
            layout.spacing = 6f;
            layout.padding = new RectOffset(0, 0, 0, 0);
            layout.childControlWidth = true;
            layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            var fitter = content.gameObject.AddComponent<ContentSizeFitter>();
            fitter.horizontalFit = ContentSizeFitter.FitMode.Unconstrained;
            fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            // Scrollbar
            var barBg = CreatePanel(rootRt, "Scrollbar", new Color(0.42f, 0.30f, 0.24f, 0.12f), 7);
            barBg.raycastTarget = true;
            var barRt = barBg.rectTransform;
            barRt.anchorMin = new Vector2(1f, 0f);
            barRt.anchorMax = new Vector2(1f, 1f);
            barRt.pivot = new Vector2(1f, 0.5f);
            barRt.sizeDelta = new Vector2(14f, 0f);
            barRt.anchoredPosition = Vector2.zero;

            var slidingArea = CreateRect("SlidingArea", barRt);
            Stretch(slidingArea);
            var handle = CreatePanel(slidingArea, "Handle", Palette.InkSoft, 7);
            handle.raycastTarget = true;
            Stretch(handle.rectTransform);

            var scrollbar = barBg.gameObject.AddComponent<Scrollbar>();
            scrollbar.handleRect = handle.rectTransform;
            scrollbar.targetGraphic = handle;
            scrollbar.direction = Scrollbar.Direction.BottomToTop;

            scroll.content = content;
            scroll.viewport = viewport;
            scroll.horizontal = false;
            scroll.vertical = true;
            scroll.movementType = ScrollRect.MovementType.Clamped;
            scroll.inertia = true;
            scroll.scrollSensitivity = 40f;
            scroll.verticalScrollbar = scrollbar;
            scroll.verticalScrollbarVisibility = ScrollRect.ScrollbarVisibility.Permanent;
            return scroll;
        }

        /// <summary>Adds a LayoutElement with a fixed preferred height (for rows inside layout groups).</summary>
        public static void FixedHeight(GameObject go, float height)
        {
            var le = go.GetComponent<LayoutElement>();
            if (le == null) le = go.AddComponent<LayoutElement>();
            le.minHeight = height;
            le.preferredHeight = height;
            le.flexibleHeight = 0f;
        }

        // ---------- Avatar ----------

        public static Color AvatarColor(string avatar)
        {
            switch (avatar)
            {
                case "me": return Palette.AvatarMe;
                case "bear": return Palette.AvatarBear;
                case "cat": return Palette.AvatarCat;
                case "rabbit": return Palette.AvatarRabbit;
            }
            return Palette.Butter;
        }

        public static string AvatarGlyph(string avatar)
        {
            switch (avatar)
            {
                case "me": return "我";
                case "bear": return "熊";
                case "cat": return "喵";
                case "rabbit": return "兔";
            }
            return "？";
        }

        /// <summary>Round pastel avatar with one character in the middle. Caller places the returned rect.</summary>
        public static RectTransform CreateAvatar(Transform parent, string avatar, float diameter)
        {
            var circle = CreateCircle(parent, "Avatar", AvatarColor(avatar));
            var rt = circle.rectTransform;
            rt.sizeDelta = new Vector2(diameter, diameter);
            var glyph = CreateText(rt, "Glyph", AvatarGlyph(avatar), Mathf.RoundToInt(diameter * 0.5f), Palette.Ink, TextAnchor.MiddleCenter);
            glyph.fontStyle = FontStyle.Bold;
            glyph.horizontalOverflow = HorizontalWrapMode.Overflow;
            Stretch(glyph.rectTransform);
            return rt;
        }
    }
}

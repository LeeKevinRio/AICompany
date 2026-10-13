using Manjong.Net;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.UI
{
    public enum FxKind
    {
        None,
        Chi,
        Pon,
        Kan,
        Ankan,
        Kakan,
        Ting,
        Win,
        Tsumo
    }

    /// <summary>
    /// Big action words ("吃" "碰" "槓" "暗槓" "加槓" "聽" "胡" "自摸") that pop up next to the seat that just acted, so the
    /// player can see who did what while the table plays on. Purpose: state indication (who acted, what they did) and, for my
    /// own actions, feedback. Frequency tier: a few times per hand, so a standard animation; 胡 / 自摸 are rare and get the
    /// delight budget (a larger pop, a gold glow and slowly turning rays).
    ///
    /// One effect = a colour plate with a 5 px Ink outline (readable on the felt and on Cream), the word in Ink with a Card
    /// stroke, a name pill hanging over the plate's lower edge. Everything is transform + opacity only, driven by unscaled
    /// time with the shared strong ease-out curve (UiMotion.Evaluate), and none of it is a raycast target: it never
    /// takes a click away from the table or the action panel.
    ///
    /// Timeline (seconds; the table holds the playback for the same Seconds(kind), see TableScreen):
    ///   action  0.70: pop-in 0.16 (scale 0.90 -> 1.06, opacity 0 -> 1) + settle 0.10 (1.06 -> 1.00), hold 0.26, exit 0.18
    ///                 (opacity 1 -> 0, scale 1 -> 0.96)
    ///   win     1.20: pop-in 0.18 (0.90 -> 1.12) + settle 0.12 (-> 1.00), hold 0.65, exit 0.25; rays scale 0.90 -> 1.00 over
    ///                 0.30 and turn 12 degrees per second
    /// Reduced motion: no scale, no turning rays; opacity only (fade in 0.12, same hold, fade out 0.18).
    /// </summary>
    public static class ActionFx
    {
        public const float ActionSeconds = 0.70f;
        public const float WinSeconds = 1.20f;
        /// <summary>Pop-in plus settle of an action effect: once this has passed, a waiting state may cut the table's hold short.</summary>
        public const float EnterSeconds = 0.26f;
        /// <summary>Longest frame step an effect (and the table's hold for it) advances by, so both run on one clock.</summary>
        public const float MaxStep = 0.05f;

        /// <summary>Which effect, if any, a played step calls for. A win with `result.selfDraw` (or "自摸" in the text) is Tsumo.</summary>
        public static FxKind KindOf(StepDto step)
        {
            if (step == null || step.@event == null) return FxKind.None;
            EventDto e = step.@event;
            if (e.seat < 0 || e.seat > 3) return FxKind.None;
            switch (e.type)
            {
                case "chi": return FxKind.Chi;
                case "pon": return FxKind.Pon;
                case "kan": return FxKind.Kan;
                case "ankan": return FxKind.Ankan;
                case "kakan": return FxKind.Kakan;
                case "ting": return FxKind.Ting;
                case "win":
                    bool selfDraw = step.view != null && step.view.hasResult && step.view.result != null
                        ? step.view.result.selfDraw
                        : DtoUtil.Safe(e.text).Contains("自摸");
                    return selfDraw ? FxKind.Tsumo : FxKind.Win;
            }
            return FxKind.None;
        }

        public static bool IsWin(FxKind kind)
        {
            return kind == FxKind.Win || kind == FxKind.Tsumo;
        }

        /// <summary>Total life of the effect = how long the table holds the playback for it.</summary>
        public static float Seconds(FxKind kind)
        {
            if (kind == FxKind.None) return 0f;
            return IsWin(kind) ? WinSeconds : ActionSeconds;
        }

        public static string Word(FxKind kind)
        {
            switch (kind)
            {
                case FxKind.Chi: return "吃";
                case FxKind.Pon: return "碰";
                case FxKind.Kan: return "槓";
                case FxKind.Ankan: return "暗槓";
                case FxKind.Kakan: return "加槓";
                case FxKind.Ting: return "聽";
                case FxKind.Win: return "胡";
                case FxKind.Tsumo: return "自摸";
            }
            return "";
        }

        static Color PlateColor(FxKind kind)
        {
            switch (kind)
            {
                case FxKind.Chi: return Palette.FxChi;
                case FxKind.Pon: return Palette.FxPon;
                case FxKind.Kan:
                case FxKind.Ankan:
                case FxKind.Kakan: return Palette.FxKan;
                case FxKind.Ting: return Palette.FxTing;
            }
            return Palette.FxWin;
        }

        /// <summary>
        /// Where the effect appears, as an offset from the canvas centre, per relative seat (0 me, 1 right, 2 opposite, 3 left).
        /// The table is compact and full of tiles, so the plates stand beside it, in the empty margins between the stations
        /// (info cards) of the corners: me and the left seat on the left (me lower), the right seat and the opposite seat on the
        /// right (the opposite seat higher). They cover nothing; a plate is at most 264 wide and 150 high with the name pill 19
        /// below it. The margin is at least 492 wide on each side of the 836 wide table in 16:10 (more in 16:9).
        /// </summary>
        public static Vector2 Anchor(int rel)
        {
            switch (rel)
            {
                case 0: return new Vector2(-560f, 49f);
                case 1: return new Vector2(560f, 49f);
                case 2: return new Vector2(560f, 209f);
                default: return new Vector2(-560f, 209f);
            }
        }

        /// <summary>Builds and starts one effect on `layer`. `who` is the player's name shown on the pill under the plate.</summary>
        public static ActionFxAnim Spawn(RectTransform layer, FxKind kind, int rel, string who)
        {
            bool big = IsWin(kind);
            string word = Word(kind);
            int font = big ? 104 : 88;
            float h = big ? 150f : 128f;
            float w = Mathf.Max(big ? 176f : 144f, word.Length * font + 56f);

            var root = UiFactory.CreateRect("Fx_" + kind, layer);
            UiFactory.Place(root, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Anchor(rel), Vector2.zero);
            var group = root.gameObject.AddComponent<CanvasGroup>();
            group.blocksRaycasts = false;
            group.interactable = false;

            RectTransform rays = null;
            if (big)
            {
                var glow = UiFactory.CreateCircle(root, "Glow", Palette.ResultGlow);
                UiFactory.Place(glow.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(300f, 300f));
                rays = CreateRays(root);
            }

            var pop = UiFactory.CreateRect("Pop", root);
            UiFactory.Place(pop, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);

            var plate = UiFactory.CreatePanel(pop, "Plate", PlateColor(kind), 40);
            UiFactory.Place(plate.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(w, h));
            UiFactory.AddShadow(plate, Palette.CardShadow, new Vector2(0f, -6f));
            UiFactory.CreateRing(plate.transform, "Ring", Palette.Ink, 40, 5, 0f);

            var glyph = UiFactory.CreateText(plate.transform, "Word", word, font, Palette.Ink, TextAnchor.MiddleCenter);
            glyph.fontStyle = FontStyle.Bold;
            glyph.horizontalOverflow = HorizontalWrapMode.Overflow;
            glyph.verticalOverflow = VerticalWrapMode.Overflow;
            UiFactory.Stretch(glyph.rectTransform);
            var stroke = glyph.gameObject.AddComponent<Outline>();
            stroke.effectColor = Palette.Card;
            stroke.effectDistance = new Vector2(3f, -3f);

            if (!string.IsNullOrEmpty(who))
            {
                float pw = Mathf.Clamp(36f + 26f * who.Length, 84f, 260f);
                var pill = UiFactory.CreatePanel(pop, "Who", Palette.Card, 18);
                UiFactory.Place(pill.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, -h * 0.5f), new Vector2(pw, 38f));
                UiFactory.CreateRing(pill.transform, "Ring", Palette.Ink, 18, 3, 0f);
                var name = UiFactory.CreateLabel(pill.transform, "Text", who, 26, Palette.Ink, TextAnchor.MiddleCenter);
                name.fontStyle = FontStyle.Bold;
                UiFactory.Stretch(name.rectTransform, 8f, 2f, 8f, 2f);
            }

            var anim = root.gameObject.AddComponent<ActionFxAnim>();
            anim.Setup(group, pop, rays, big, Seconds(kind));
            return anim;
        }

        /// <summary>Twelve rays around the plate, alternating long and short. Decorative, drawn behind the plate.</summary>
        static RectTransform CreateRays(RectTransform parent)
        {
            var rays = UiFactory.CreateRect("Rays", parent);
            UiFactory.Place(rays, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            for (int i = 0; i < 12; i++)
            {
                var arm = UiFactory.CreateRect("Arm" + i, rays);
                UiFactory.Place(arm, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
                arm.localRotation = Quaternion.Euler(0f, 0f, i * 30f);
                var bar = UiFactory.CreatePanel(arm, "Bar", Palette.FxRay, 7);
                UiFactory.Place(bar.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0f), new Vector2(0f, 95f),
                    i % 2 == 0 ? new Vector2(14f, 70f) : new Vector2(10f, 43f));
            }
            return rays;
        }

        /// <summary>Playback sped up (tap, long backlog): every effect still on screen fades out quickly.</summary>
        public static void DismissAll(RectTransform layer)
        {
            if (layer == null) return;
            for (int i = 0; i < layer.childCount; i++)
            {
                var anim = layer.GetChild(i).GetComponent<ActionFxAnim>();
                if (anim != null) anim.Dismiss();
            }
        }

        /// <summary>A meld that was just made: an orange outline that fades out by itself (0.1 s in, hold, 0.3 s out).</summary>
        public static void FlashMeld(RectTransform meld)
        {
            if (meld == null) return;
            var ring = UiFactory.CreateRing(meld, "NewMeldRing", Palette.LastDiscardRing, 10, 4, 3f);
            var group = ring.gameObject.AddComponent<CanvasGroup>();
            group.blocksRaycasts = false;
            group.interactable = false;
            var flash = ring.gameObject.AddComponent<MeldFlash>();
            flash.Setup(group);
        }
    }

    /// <summary>Drives one action effect: scale and opacity on a fixed timeline (see ActionFx), unscaled time.</summary>
    public class ActionFxAnim : MonoBehaviour
    {
        const float DismissSeconds = 0.10f;

        CanvasGroup group;
        RectTransform pop;
        RectTransform rays;
        bool big;
        bool reduced;
        float total;
        float t;
        float from;
        float peak;
        float enter;
        float settle;
        float exit;
        bool dismissed;
        float fromAlpha;
        float fromScale;
        float dismissAt;

        public void Setup(CanvasGroup g, RectTransform popRect, RectTransform raysRect, bool isBig, float seconds)
        {
            group = g;
            pop = popRect;
            rays = raysRect;
            big = isBig;
            total = seconds;
            reduced = UiMotion.Reduced;
            if (reduced)
            {
                from = 1f;
                peak = 1f;
                enter = 0.12f;
                settle = 0f;
                exit = 0.18f;
            }
            else if (big)
            {
                from = 0.90f;
                peak = 1.12f;
                enter = 0.18f;
                settle = 0.12f;
                exit = 0.25f;
            }
            else
            {
                from = 0.90f;
                peak = 1.06f;
                enter = 0.16f;
                settle = 0.10f;
                exit = 0.18f;
            }
            Apply();
        }

        /// <summary>Fade out from where it is right now in 0.1 s (fast-forward, backlog).</summary>
        public void Dismiss()
        {
            if (dismissed) return;
            dismissed = true;
            fromAlpha = group.alpha;
            fromScale = pop.localScale.x;
            dismissAt = t;
            total = t + DismissSeconds;
        }

        void Update()
        {
            t += Mathf.Min(Time.unscaledDeltaTime, ActionFx.MaxStep);
            if (t >= total)
            {
                Destroy(gameObject);
                return;
            }
            Apply();
        }

        void Apply()
        {
            float alpha;
            float scale;
            if (dismissed)
            {
                float k = UiMotion.Evaluate(UiCurve.OutStrong, (t - dismissAt) / DismissSeconds);
                alpha = fromAlpha * (1f - k);
                scale = reduced ? 1f : Mathf.Lerp(fromScale, 0.96f, k);
            }
            else
            {
                if (t < enter)
                {
                    float k = UiMotion.Evaluate(UiCurve.OutStrong, t / enter);
                    alpha = k;
                    scale = Mathf.Lerp(from, peak, k);
                }
                else if (t < enter + settle)
                {
                    alpha = 1f;
                    scale = Mathf.Lerp(peak, 1f, UiMotion.Evaluate(UiCurve.OutStrong, (t - enter) / settle));
                }
                else
                {
                    alpha = 1f;
                    scale = 1f;
                }
                float exitStart = total - exit;
                if (t > exitStart)
                {
                    float k = UiMotion.Evaluate(UiCurve.OutStrong, (t - exitStart) / exit);
                    alpha *= 1f - k;
                    if (!reduced) scale *= Mathf.Lerp(1f, 0.96f, k);
                }
            }
            group.alpha = alpha;
            pop.localScale = new Vector3(scale, scale, 1f);

            if (rays != null && !reduced)
            {
                float grow = Mathf.Lerp(0.90f, 1f, UiMotion.Evaluate(UiCurve.OutStrong, t / 0.30f));
                rays.localScale = new Vector3(grow, grow, 1f);
                rays.localRotation = Quaternion.Euler(0f, 0f, -12f * t);
            }
        }
    }

    /// <summary>Opacity timeline of the new-meld outline: fade in 0.1 s, hold to 0.55 s, fade out 0.3 s, then removed.</summary>
    public class MeldFlash : MonoBehaviour
    {
        const float In = 0.10f;
        const float Hold = 0.55f;
        const float Out = 0.30f;

        CanvasGroup group;
        float t;

        public void Setup(CanvasGroup g)
        {
            group = g;
            group.alpha = 0f;
        }

        void Update()
        {
            t += Mathf.Min(Time.unscaledDeltaTime, 0.05f);
            if (t >= Hold + Out)
            {
                Destroy(gameObject);
                return;
            }
            float alpha = t < In
                ? UiMotion.Evaluate(UiCurve.OutStrong, t / In)
                : t < Hold ? 1f : 1f - UiMotion.Evaluate(UiCurve.OutStrong, (t - Hold) / Out);
            group.alpha = alpha;
        }
    }
}

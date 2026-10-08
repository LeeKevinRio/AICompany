#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif
using UnityEngine;

namespace Manjong.UI
{
    /// <summary>Easing curves (CSS cubic-bezier definitions) shared by every UI tween.</summary>
    public enum UiCurve
    {
        /// <summary>cubic-bezier(0.23, 1, 0.32, 1): strong ease-out. Every entrance, exit and move in the table UI.</summary>
        OutStrong,
        /// <summary>cubic-bezier(0.77, 0, 0.175, 1): strong ease-in-out. Long on-screen travel (a drawn tile joining the hand).</summary>
        InOutStrong
    }

    public static class UiMotion
    {
        const string ReduceKey = "manjong.reduceMotion";

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")]
        static extern int ManjongPrefersReducedMotion();
#endif

        /// <summary>
        /// Reduced motion: positional glides snap to their target and the discard flight becomes a plain fade, but
        /// opacity changes stay (they carry the feedback). WebGL asks the browser
        /// (matchMedia "(prefers-reduced-motion: reduce)", Plugins/WebGL/ManjongMotion.jslib); the Editor and desktop
        /// builds read PlayerPrefs "manjong.reduceMotion" = 1. Read once per session, not per frame.
        /// </summary>
        public static bool Reduced
        {
            get
            {
                if (reduced < 0)
                {
#if UNITY_WEBGL && !UNITY_EDITOR
                    reduced = ManjongPrefersReducedMotion() == 1 ? 1 : 0;
#else
                    reduced = PlayerPrefs.GetInt(ReduceKey, 0) == 1 ? 1 : 0;
#endif
                }
                return reduced == 1;
            }
        }

        static int reduced = -1;

        /// <summary>Neighbour tiles stepping aside while a tile is dragged (retargeted on every new gap).</summary>
        public const float Shift = 0.15f;
        /// <summary>Released / cancelled tile gliding into its slot, a lifted tile dropping back.</summary>
        public const float Settle = 0.18f;
        /// <summary>Tile picked up (lift) and the "release to play" cue fading in or out.</summary>
        public const float Quick = 0.10f;
        /// <summary>Played tile leaving the hand: travel and fade run for the same time.</summary>
        public const float Exit = 0.22f;

        /// <summary>Y of a CSS-style cubic bezier (0,0) (x1,y1) (x2,y2) (1,1) at progress x in 0..1.</summary>
        public static float Bezier(float x1, float y1, float x2, float y2, float x)
        {
            if (x <= 0f) return 0f;
            if (x >= 1f) return 1f;
            // Solve bx(s) = x with a few Newton steps, falling back to bisection when the slope is flat.
            float s = x;
            for (int i = 0; i < 8; i++)
            {
                float err = Coord(x1, x2, s) - x;
                if (Mathf.Abs(err) < 0.0005f) return Coord(y1, y2, s);
                float slope = Slope(x1, x2, s);
                if (Mathf.Abs(slope) < 0.0001f) break;
                s -= err / slope;
            }
            float lo = 0f;
            float hi = 1f;
            s = x;
            for (int i = 0; i < 20; i++)
            {
                float v = Coord(x1, x2, s);
                if (Mathf.Abs(v - x) < 0.0005f) break;
                if (v < x) lo = s; else hi = s;
                s = (lo + hi) * 0.5f;
            }
            return Coord(y1, y2, s);
        }

        static float Coord(float p1, float p2, float s)
        {
            float u = 1f - s;
            return 3f * u * u * s * p1 + 3f * u * s * s * p2 + s * s * s;
        }

        static float Slope(float p1, float p2, float s)
        {
            float u = 1f - s;
            return 3f * u * u * p1 + 6f * u * s * (p2 - p1) + 3f * s * s * (1f - p2);
        }

        public static float Evaluate(UiCurve curve, float x)
        {
            return curve == UiCurve.InOutStrong ? Bezier(0.77f, 0f, 0.175f, 1f, x) : Bezier(0.23f, 1f, 0.32f, 1f, x);
        }
    }

    /// <summary>
    /// Lightweight tweens for one RectTransform: anchored position and opacity (CanvasGroup), each an
    /// independent track. A track always starts from the value on screen right now, so retargeting an unfinished tween
    /// continues from where it is (no jump back to the start). Driven by unscaled time. Not a general animation library.
    /// </summary>
    public class UiTween : MonoBehaviour
    {
        class Track
        {
            public bool Active;
            public Vector2 From;
            public Vector2 To;
            public float Elapsed;
            public float Duration;
            public UiCurve Curve;

            public void Begin(Vector2 from, Vector2 to, float duration, UiCurve curve)
            {
                Active = true;
                From = from;
                To = to;
                Elapsed = 0f;
                Duration = duration;
                Curve = curve;
            }

            /// <summary>Advances by dt and returns the value to show; Active turns false on the last step.</summary>
            public Vector2 Step(float dt)
            {
                Elapsed += dt;
                if (Elapsed >= Duration)
                {
                    Active = false;
                    return To;
                }
                return Vector2.LerpUnclamped(From, To, UiMotion.Evaluate(Curve, Elapsed / Duration));
            }
        }

        const float MaxStep = 0.05f; // a long frame (WebGL hitch) must not skip an animation

        readonly Track pos = new Track();
        readonly Track alpha = new Track();
        RectTransform rt;
        CanvasGroup group;
        bool destroyWhenIdle;

        RectTransform Rt
        {
            get
            {
                if (rt == null) rt = (RectTransform)transform;
                return rt;
            }
        }

        /// <summary>Opacity needs a CanvasGroup (added on first use; it blocks raycasts like any other graphic).</summary>
        CanvasGroup Group
        {
            get
            {
                if (group == null)
                {
                    group = GetComponent<CanvasGroup>();
                    if (group == null) group = gameObject.AddComponent<CanvasGroup>();
                }
                return group;
            }
        }

        /// <summary>For visuals that must never catch the pointer (fly-away ghosts, the swipe cue).</summary>
        public void PassThrough()
        {
            Group.blocksRaycasts = false;
            Group.interactable = false;
        }

        public bool PositionActive
        {
            get { return pos.Active; }
        }

        public bool Busy
        {
            get { return pos.Active || alpha.Active; }
        }

        /// <summary>Where the position will end up (the current position when no tween runs).</summary>
        public Vector2 PositionTarget
        {
            get { return pos.Active ? pos.To : Rt.anchoredPosition; }
        }

        /// <summary>Destroy this object as soon as every track has finished (fly-away ghosts).</summary>
        public void DestroyWhenIdle()
        {
            destroyWhenIdle = true;
        }

        /// <summary>Puts the element at p right now and cancels a running position tween (pointer-following).</summary>
        public void SetPosition(Vector2 p)
        {
            pos.Active = false;
            Rt.anchoredPosition = p;
        }

        /// <summary>
        /// Glides to target from the current on-screen position. A tween already heading to the same target is left
        /// alone, so this can be called every frame; a different target restarts from the current position.
        /// </summary>
        public void SlideTo(Vector2 target, float duration, UiCurve curve)
        {
            if (pos.Active && pos.To == target) return;
            Vector2 current = Rt.anchoredPosition;
            if ((current - target).sqrMagnitude < 0.0001f)
            {
                SetPosition(target);
                return;
            }
            if (duration <= 0f || UiMotion.Reduced)
            {
                SetPosition(target);
                return;
            }
            pos.Begin(current, target, duration, curve);
        }

        public void SlideTo(Vector2 target, float duration)
        {
            SlideTo(target, duration, UiCurve.OutStrong);
        }

        /// <summary>Strong ease-out like the movement (entrances and exits). Kept under reduced motion: it is the gentle replacement for movement.</summary>
        public void FadeTo(float target, float duration)
        {
            if (alpha.Active && Mathf.Approximately(alpha.To.x, target)) return;
            float current = Group.alpha;
            if (duration <= 0f || Mathf.Approximately(current, target))
            {
                alpha.Active = false;
                Group.alpha = target;
                return;
            }
            alpha.Begin(new Vector2(current, 0f), new Vector2(target, 0f), duration, UiCurve.OutStrong);
        }

        public void SetAlpha(float value)
        {
            alpha.Active = false;
            Group.alpha = value;
        }

        void Update()
        {
            if (!Busy)
            {
                if (destroyWhenIdle) Destroy(gameObject);
                return;
            }
            float dt = Mathf.Min(Time.unscaledDeltaTime, MaxStep);
            if (pos.Active) Rt.anchoredPosition = pos.Step(dt);
            if (alpha.Active) Group.alpha = alpha.Step(dt).x;
        }
    }
}

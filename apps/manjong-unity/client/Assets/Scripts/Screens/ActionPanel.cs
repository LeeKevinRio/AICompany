using System;
using System.Collections.Generic;
using Manjong.Net;
using Manjong.UI;
using UnityEngine;
using UnityEngine.UI;

namespace Manjong.Screens
{
    /// <summary>
    /// Fixed action panel above the right part of my hand with six buttons in a fixed order:
    /// 吃 碰 槓 聽 胡 過. It pops in whenever I have a non-discard option (chi / pon / kan / ankan / kakan / ron /
    /// tsumo / pass) or a discard that leaves me ready, and folds away otherwise. Available buttons are lit (colour +
    /// pulsing glow); the rest are greyed out and not clickable. Its rect never changes with the content.
    /// 聽 is local only: it toggles the "show every ready discard" hint and never talks to the server.
    /// Several chi / kan choices open a small menu with tile pictures above the panel.
    /// </summary>
    public class ActionPanel : MonoBehaviour
    {
        public const float Width = 600f;
        public const float Height = 110f;
        const float ButtonSize = 90f;
        const float ButtonGap = 8f;
        const float Pad = 10f;
        const float PopSeconds = 0.15f;

        enum Slot
        {
            Chi = 0,
            Pon = 1,
            Kan = 2,
            Ting = 3,
            Hu = 4,
            Pass = 5
        }

        static readonly string[] Labels = { "吃", "碰", "槓", "聽", "胡", "過" };
        static readonly Color[] LitColors = { Palette.Butter, Palette.Sky, Palette.Lavender, Palette.Mint, Palette.Coral, Palette.Peach };
        static readonly Color DimColor = new Color(0.87f, 0.84f, 0.80f, 1f);

        readonly Button[] buttons = new Button[6];
        readonly Image[] backgrounds = new Image[6];
        readonly Image[] glows = new Image[6];
        readonly Text[] labels = new Text[6];
        readonly Text[] subLabels = new Text[6];
        readonly bool[] lit = new bool[6];

        readonly List<OptionDto> chiOptions = new List<OptionDto>();
        readonly List<OptionDto> kanOptions = new List<OptionDto>();
        OptionDto ponOption;
        OptionDto huOption;
        OptionDto passOption;
        bool tingAvailable;
        bool tingOn;

        Action<string> onSend;
        Action onToggleTing;
        RectTransform menu;
        string optionsSig = "";
        float popStartedAt = -1f;

        public bool IsOpen
        {
            get { return gameObject.activeSelf; }
        }

        /// <summary>Builds the panel anchored at the bottom-right of "parent" (offset from that corner).</summary>
        public static ActionPanel Create(Transform parent, Vector2 bottomRightOffset, Action<string> send, Action toggleTing)
        {
            var bg = UiFactory.CreatePanel(parent, "ActionPanel", Palette.Card, 28);
            UiFactory.Place(bg.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 0f), bottomRightOffset, new Vector2(Width, Height));
            UiFactory.AddShadow(bg, Palette.CardShadow, new Vector2(0f, -5f));
            bg.raycastTarget = true; // clicks between buttons must not fall through to the table

            var panel = bg.gameObject.AddComponent<ActionPanel>();
            panel.onSend = send;
            panel.onToggleTing = toggleTing;
            panel.BuildButtons();
            bg.gameObject.SetActive(false);
            return panel;
        }

        void BuildButtons()
        {
            for (int i = 0; i < 6; i++)
            {
                int slot = i;
                var btn = UiFactory.CreateButton(transform, "Btn_" + Labels[i], "", DimColor, 40, () => OnPressed((Slot)slot));
                var rt = (RectTransform)btn.transform;
                UiFactory.Place(rt, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(Pad + i * (ButtonSize + ButtonGap), 0f), new Vector2(ButtonSize, ButtonSize));

                // Replace the factory's single label with a big glyph and a small caption line.
                Text factoryLabel = UiFactory.ButtonLabel(btn);
                factoryLabel.text = Labels[i];
                factoryLabel.fontStyle = FontStyle.Bold;
                factoryLabel.resizeTextMaxSize = 40;
                factoryLabel.rectTransform.offsetMin = new Vector2(4f, 26f);
                factoryLabel.rectTransform.offsetMax = new Vector2(-4f, -6f);

                var sub = UiFactory.CreateLabel(rt, "Sub", "", 18, Palette.Ink, TextAnchor.MiddleCenter);
                UiFactory.Place(sub.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 6f), new Vector2(ButtonSize - 8f, 22f));

                var glow = UiFactory.CreateRing(rt, "Glow", Palette.LastDiscardRing, 26, 4, 5f);
                glow.transform.SetAsFirstSibling();

                buttons[i] = btn;
                backgrounds[i] = (Image)btn.targetGraphic;
                glows[i] = glow;
                labels[i] = factoryLabel;
                subLabels[i] = sub;
            }
        }

        /// <summary>
        /// Updates the panel from the current options. "canAct" false (playback, waiting, disconnected) folds it.
        /// </summary>
        public void Apply(GameView v, bool canAct, bool tingIsOn)
        {
            chiOptions.Clear();
            kanOptions.Clear();
            ponOption = null;
            huOption = null;
            passOption = null;
            tingAvailable = false;
            tingOn = tingIsOn;

            var sig = new System.Text.StringBuilder();
            OptionDto[] opts = canAct && v != null ? DtoUtil.Safe(v.options) : new OptionDto[0];
            for (int i = 0; i < opts.Length; i++)
            {
                OptionDto o = opts[i];
                if (o == null) continue;
                switch (o.type)
                {
                    case "chi": chiOptions.Add(o); break;
                    case "pon": ponOption = o; break;
                    case "kan":
                    case "ankan":
                    case "kakan": kanOptions.Add(o); break;
                    case "ron":
                    case "tsumo": huOption = o; break;
                    case "pass": passOption = o; break;
                    case "discard":
                        if (DtoUtil.Safe(o.waits).Length > 0) tingAvailable = true;
                        continue;
                    default:
                        continue; // "next" is handled by the result panel
                }
                sig.Append(o.id).Append(';');
            }

            lit[(int)Slot.Chi] = chiOptions.Count > 0;
            lit[(int)Slot.Pon] = ponOption != null;
            lit[(int)Slot.Kan] = kanOptions.Count > 0;
            lit[(int)Slot.Ting] = tingAvailable;
            lit[(int)Slot.Hu] = huOption != null;
            lit[(int)Slot.Pass] = passOption != null;

            bool any = false;
            for (int i = 0; i < 6; i++) any |= lit[i];
            if (!any)
            {
                Fold();
                return;
            }

            string newSig = sig.ToString();
            if (newSig != optionsSig) CloseMenu();
            optionsSig = newSig;

            for (int i = 0; i < 6; i++)
            {
                backgrounds[i].color = lit[i] ? LitColors[i] : DimColor;
                UiFactory.SetInteractable(buttons[i], lit[i]);
                glows[i].gameObject.SetActive(lit[i]);
                subLabels[i].text = "";
                subLabels[i].color = labels[i].color;
            }
            labels[(int)Slot.Hu].text = huOption != null && huOption.type == "tsumo" ? "自摸" : "胡";
            if (huOption != null && huOption.tai >= 0) subLabels[(int)Slot.Hu].text = huOption.tai + " 台";
            if (chiOptions.Count > 1) subLabels[(int)Slot.Chi].text = chiOptions.Count + " 種";
            if (kanOptions.Count > 1) subLabels[(int)Slot.Kan].text = kanOptions.Count + " 種";
            if (tingAvailable) subLabels[(int)Slot.Ting].text = tingOn ? "顯示中" : "看聽牌";

            if (!gameObject.activeSelf)
            {
                gameObject.SetActive(true);
                transform.SetAsLastSibling();
                popStartedAt = Time.unscaledTime;
                transform.localScale = new Vector3(0.85f, 0.85f, 1f);
            }
        }

        public void Fold()
        {
            CloseMenu();
            optionsSig = "";
            if (gameObject.activeSelf) gameObject.SetActive(false);
        }

        void Update()
        {
            if (popStartedAt >= 0f)
            {
                float t = Mathf.Clamp01((Time.unscaledTime - popStartedAt) / PopSeconds);
                float eased = 1f - (1f - t) * (1f - t); // ease-out
                float s = Mathf.Lerp(0.85f, 1f, eased);
                transform.localScale = new Vector3(s, s, 1f);
                if (t >= 1f) popStartedAt = -1f;
            }

            // Pulsing glow on lit buttons; 聽 holds a steady glow while its hint is switched on.
            float pulse = 0.45f + 0.55f * (0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 6f));
            for (int i = 0; i < 6; i++)
            {
                if (!lit[i]) continue;
                Color c = glows[i].color;
                c.a = i == (int)Slot.Ting && tingOn ? 1f : pulse;
                glows[i].color = c;
            }
        }

        void OnPressed(Slot slot)
        {
            switch (slot)
            {
                case Slot.Chi:
                    if (chiOptions.Count == 1) Send(chiOptions[0].id);
                    else if (chiOptions.Count > 1) OpenMenu(chiOptions, true);
                    break;
                case Slot.Pon:
                    if (ponOption != null) Send(ponOption.id);
                    break;
                case Slot.Kan:
                    if (kanOptions.Count == 1) Send(kanOptions[0].id);
                    else if (kanOptions.Count > 1) OpenMenu(kanOptions, false);
                    break;
                case Slot.Ting:
                    if (onToggleTing != null) onToggleTing();
                    break;
                case Slot.Hu:
                    if (huOption != null) Send(huOption.id);
                    break;
                case Slot.Pass:
                    if (passOption != null) Send(passOption.id);
                    break;
            }
        }

        void Send(string id)
        {
            CloseMenu();
            if (onSend != null) onSend(id);
        }

        // ---------- Choice menu (several chi / kan options) ----------

        void CloseMenu()
        {
            if (menu != null)
            {
                menu.gameObject.SetActive(false);
                Destroy(menu.gameObject);
                menu = null;
            }
        }

        void OpenMenu(List<OptionDto> options, bool isChi)
        {
            CloseMenu();
            TileSize size = TileSizes.Mini;
            const float boxH = 92f;
            const float gap = 8f;
            const float cancelW = 84f;
            float boxW = isChi ? 3f * (size.width + 1f) + 24f : 4f * (size.width + 1f) + 24f;
            float w = Pad * 2f + options.Count * boxW + options.Count * gap + cancelW;

            var bg = UiFactory.CreatePanel(transform, "ChoiceMenu", Palette.Card, 22);
            menu = bg.rectTransform;
            UiFactory.Place(menu, new Vector2(1f, 1f), new Vector2(1f, 0f), new Vector2(0f, 8f), new Vector2(w, boxH + Pad * 2f));
            UiFactory.AddShadow(bg, Palette.CardShadow, new Vector2(0f, -4f));
            UiFactory.CreateRing(menu, "Edge", isChi ? Palette.Butter : Palette.Lavender, 22, 3, 0f);
            bg.raycastTarget = true;

            for (int i = 0; i < options.Count; i++)
            {
                OptionDto o = options[i];
                string id = o.id;
                var box = UiFactory.CreateButton(menu, "Choice" + i, "", isChi ? Palette.Butter : Palette.Lavender, 20, () => Send(id));
                UiFactory.Place((RectTransform)box.transform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(Pad + i * (boxW + gap), 0f), new Vector2(boxW, boxH));
                Text caption = UiFactory.ButtonLabel(box);
                caption.text = isChi ? "吃" : KanCaption(o.type);
                caption.fontStyle = FontStyle.Bold;
                caption.rectTransform.offsetMin = new Vector2(4f, boxH - 30f);
                caption.rectTransform.offsetMax = new Vector2(-4f, -2f);

                // Tile pictures: the chi sequence (claimed tile ringed) or the kong tile four times.
                string[] tiles = isChi ? DtoUtil.Safe(o.tiles) : new[] { o.tile, o.tile, o.tile, o.tile };
                var row = UiFactory.CreateRect("Tiles", box.transform);
                float rowW = tiles.Length * (size.width + 1f) - 1f;
                UiFactory.Place(row, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 8f), new Vector2(rowW, size.height));
                for (int k = 0; k < tiles.Length; k++)
                {
                    RectTransform t = o.type == "ankan" && (k == 0 || k == 3) ? TileView.CreateBack(row, size) : TileView.CreateFace(row, tiles[k], size);
                    UiFactory.Place(t, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(k * (size.width + 1f), 0f), size.Vector);
                    if (isChi && tiles[k] == o.tile) TileView.AddRing(t, Palette.LastDiscardRing, size, 2);
                }
            }

            var cancel = UiFactory.CreateButton(menu, "Cancel", "取消", Palette.Gray, 26, CloseMenu);
            UiFactory.Place((RectTransform)cancel.transform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-Pad, 0f), new Vector2(cancelW - gap, boxH));
        }

        static string KanCaption(string type)
        {
            switch (type)
            {
                case "ankan": return "暗槓";
                case "kakan": return "加槓";
                default: return "明槓";
            }
        }
    }
}

---
name: review-animations
description: 以高工藝標準審查動畫與動效 code——十條不可協商標準、逃逸觸發清單、修復偏好階層、Block/Approve 明確判準。qa-reviewer 審查含動效的 UI diff 時必用；預設立場是挑出問題，Approve 要靠品質掙來。非動效的一般 code 審查用 code-review-checklist。
---

> **本 skill 改作自 emilkowalski/skills（MIT），適用於本公司各產品線前端動效工作。**
> **風控地板優先**：凡涉及面向使用者的建議類／揭露類內容，其字級、對比、常駐不摺疊等風控樣式地板與逐字定稿制度優先於本 skill 任何建議；本 skill 不得用於改寫任何風控定稿文案。
>
> 來源：[emilkowalski/skills](https://github.com/emilkowalski/skills) `review-animations`，commit `d23d7f88a2e21c9e4b1418c7abe420f5c1052ba7`；授權見本目錄 [LICENSE](LICENSE)。改作內容：敘述層繁中化、剝除行銷內容與外部 skill 生態指涉；規則與數值忠實保留原文。

# Reviewing Animations — 審查動畫

這是一個專門化的審查 skill，只做一件事：以高工藝標準審查動畫與動效 code。它不寫功能、不修無關的 bug、不審非動效 code。被要求做一般 code review 時，婉拒並指向 `code-review-checklist`。

## 工作姿態

你是對工藝有毒辣眼光的資深 design engineer。你的偏好是**手感對的動效**，不是「能跑」的動效。一段「會動」但發黏、從錯的原點長出來、觸發太頻繁、或會掉幀的 transition，是 regression，不是 pass。預設立場是挑出問題；Approve 要靠品質掙來，不是預設值。

實質標準來自 Emil Kowalski 的動畫方法論。審查*方法*——不可協商標準、逃逸觸發、修復偏好階層、分層輸出、明確核可判準——改作自高強度 code-quality review 的做法。

完整規則目錄（easing 曲線、時長表、spring 參數、手勢、clip-path、效能、a11y）見 [STANDARDS.md](STANDARDS.md)。任何 finding 需要精確數值或引據時就載入它。

## 十條不可協商標準

Diff 裡的每一段動畫都對照這十條。違反即為 finding。

1. **動得有理由。** 每段動畫必須回答「為什麼動」——spatial consistency、state indication、feedback、explanation、或 preventing a jarring change。高頻元素上的「看起來很酷」是 block。

2. **頻率匹配。** 動效強度對應被看見的頻率。鍵盤觸發與每日 100+ 次的操作**不准**有動畫；每日數十次的只給極輕微動效；偶爾出現的用標準動畫；罕見／首次的才可以有 delight。

3. **有反應感的 easing。** 入場／退場元素用 `ease-out` 或強力自訂曲線。UI 上的 `ease-in` 是 block——它拖延使用者最專注的那一刻。內建 CSS easing 太弱，應看到自訂 cubic-bezier。

4. **UI 壓在 300ms 以內。** 超過 300ms 的 UI 動畫要有理由，否則是 finding。逐元素預算見 [STANDARDS.md](STANDARDS.md)。

5. **原點與物理正確性。** Popover／dropdown／tooltip 從 trigger 長出來（`transform-origin`），不是從中心。永不從 `scale(0)` 入場——從 `scale(0.9–0.97)` + opacity 開始。（Modal 豁免——保持置中。）

6. **可中斷性。** 高頻觸發或手勢驅動的動效（toast、toggle、拖曳）必須可中斷——用會從當前狀態重定向的 CSS transition 或 spring，不用從零重播的 keyframes。

7. **只動 GPU 屬性。** 只動畫 `transform` 與 `opacity`。動畫 `width`／`height`／`margin`／`padding`／`top`／`left`（或高負載下的 Framer Motion `x`／`y`／`scale` 簡寫）是效能 finding。

8. **無障礙。** 尊重 `prefers-reduced-motion`（更溫和，不是歸零——保留 opacity／color，拿掉位移）。Hover 動效 gate 在 `@media (hover: hover) and (pointer: fine)` 後面。

9. **不對稱的進出時序。** 深思熟慮的操作（按壓、按住、破壞性確認）動得慢；系統回應要乾脆。press-and-release 或 hold 互動用對稱時序是 finding。

10. **一致性（cohesion）。** 動效要匹配元件性格與整個產品——玩味的可以彈一點，dashboard 保持俐落。性格錯配、或一個刺眼的 crossfade 本可用輕微 blur 銜接兩個狀態，都是 finding。不確定動效手感對不對時，最強的一手往往是刪掉它。

## 逃逸觸發——看到就重手標記

- `transition: all`（不設限的屬性動畫）
- `scale(0)` 或無初始 transform 的純 fade 入場
- 任何 UI 互動上的 `ease-in`；刻意設計的動畫用了弱的內建 easing
- Keyboard shortcut、command palette 開關、或每日 100+ 次操作上的動畫
- UI 時長 > 300ms 且未說明理由
- 錨定 trigger 的 popover／dropdown／tooltip 用 `transform-origin: center`
- Toast、toggle 或任何被快速新增／觸發的元素用 keyframes
- 動畫 layout 屬性（`width`／`height`／`margin`／`padding`／`top`／`left`）
- 頁面忙碌時仍在跑的動效使用 Framer Motion `x`／`y`／`scale` props
- 更新父層 CSS variable 來驅動子元素 transform（style recalc 風暴）
- 位移動效缺 `prefers-reduced-motion` 處理
- 未 gate 的 `:hover` 動效
- press-and-release 或 hold 互動用對稱的進出時序
- 該有 30–80ms stagger 的地方所有東西一次全部入場

## 修復偏好階層

提修法時，優先採用排序靠前的招：

1. **刪掉動畫**（高頻／無目的／鍵盤觸發）。
2. **縮減**——更短的時長、更小的 transform、更少的動畫屬性。
3. **修 easing**——`ease-in` 換 `ease-out`／自訂曲線；用強力 cubic-bezier。
4. **修原點／物理性**——改正 `transform-origin`；`scale(0)` 換成 `scale(0.95)` + opacity。
5. **改成可中斷**——keyframes → transition，手勢驅動改 spring。
6. **搬上 GPU**——layout 屬性 → `transform`／`opacity`；簡寫 → 完整 `transform` 字串；程式化 CSS 用 WAAPI。
7. **不對稱時序**——放慢深思熟慮那側、加快系統回應那側。
8. **打磨**——blur 遮 crossfade、群組加 stagger、入場用 `@starting-style`、「有生命感」的元素用 spring。
9. **無障礙與一致性**——補 reduced-motion 與 hover gating；調校到匹配元件性格。

## 必要輸出格式

兩部分，依此順序。

### Part 1 — Findings 表（必要）

單一 markdown 表格，一列一個問題。不准寫成「Before:/After:」條列。

| Before | After | Why |
| --- | --- | --- |
| `transition: all 300ms` | `transition: transform 200ms ease-out` | Specify exact properties; `all` animates unintended properties off-GPU |
| `transform: scale(0)` | `transform: scale(0.95); opacity: 0` | Nothing appears from nothing — `scale(0)` looks like it came from nowhere |
| `ease-in` on dropdown | `ease-out` + custom curve | `ease-in` delays the moment the user watches most; feels sluggish |
| `transform-origin: center` on popover | `var(--transform-origin)` (Base UI) | Popovers scale from their trigger, not center (modals are exempt) |

### Part 2 — 判決（必要）

其餘評語依影響層級分組，高影響在前，空層省略。

1. **破壞手感的 regression**——發黏的 easing、憑空出現、在高頻／鍵盤操作上觸發。
2. **漏掉的簡化**——該刪或該大幅縮減的動畫。
3. **效能**——非 GPU 屬性、掉幀風險、recalc 風暴。
4. **可中斷性與時序**——該用 transition／spring 的地方用了 keyframes；該不對稱的時序寫成對稱。
5. **原點、物理性與一致性**——錯的原點、性格錯配、刺眼的 crossfade。
6. **無障礙**——reduced-motion 與 pointer/hover gating。

最後給出明確判決：

- **Block**——任何破壞手感的 regression、鍵盤／高頻操作上的動畫、UI 上的 `scale(0)`／`ease-in`、或有現成 GPU 修法的非 GPU 動畫。
- **Approve**——無破壞手感的 regression、無明顯該刪的動效、時長與 easing 都在範圍內、需要可中斷的地方都處理了、reduced-motion 有尊重。

要具體、引 `file:line`。需要數值時（曲線、時長、spring 參數）從 [STANDARDS.md](STANDARDS.md) 取精確值，不要近似。

## 準則

- 預定軌跡的動效優先 CSS transition／`@starting-style`／WAAPI；動態、可中斷、手勢驅動的用 JS／spring。
- 不確定動效手感對不對時，建議用慢動作／逐幀檢視、隔天再用新鮮的眼睛看一次，而不是用猜的。

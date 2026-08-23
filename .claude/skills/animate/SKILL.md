---
name: animate
description: 從零打造一段 UI 動畫——依序決定：該不該動、目的是什麼、用什麼工具、動哪些屬性、曲線與時長、如何中斷與退出，最後寫出實作。凡是要幫元件加動效、做 transition、讓介面「有手感」時必用。審既有動效 diff 用 review-animations；只是要查動效名詞用 animation-vocabulary。
---

> **本 skill 改作自 emilkowalski/skills（MIT），適用於本公司各產品線前端動效工作。**
> **風控地板優先**：凡涉及面向使用者的建議類／揭露類內容，其字級、對比、常駐不摺疊等風控樣式地板與逐字定稿制度優先於本 skill 任何建議；本 skill 不得用於改寫任何風控定稿文案。
>
> 來源：[emilkowalski/skills](https://github.com/emilkowalski/skills) `animate`，commit `d23d7f88a2e21c9e4b1418c7abe420f5c1052ba7`；授權見本目錄 [LICENSE](LICENSE)。改作內容：敘述層繁中化、剝除行銷內容與外部 skill 生態指涉；規則與數值忠實保留原文。

# Building Animations — 打造動畫

這是一個「建構型」skill，只做一件事：把一個動效需求變成一份能一次通過嚴格審查的實作。它不稽核整個 codebase、不批評既有 diff（那是 `review-animations` 的事）、也不主動找哪裡該加動畫。

## 工作姿態

你是親手做這段動畫的資深 design engineer，標準即 `review-animations` 執行的同一套標準——寫出來就要一次過審。

兩種失敗模式，第一種更糟：

1. **把不該動畫的東西動畫了。** 下面的閘門存在的意義，就是有時候要產出零行 code——那是成功，不是偷懶。
2. **對的東西用了錯的配料**——入場用 `ease-in`、`scale(0)`、toast 用 keyframes、dropdown 的時長慢到發黏。

不要把動效選項擺成菜單給人挑。自己下判斷，用一行話講清理由，然後把 code 寫出來。

## 硬規則

1. **依序跑完決策序列。** 第 1、2 步是總閘門——還不知道該不該動之前，不准先挑曲線。
2. **不准憑感覺湊數值。** 每一條曲線、時長、spring 參數都來自下方表格。不要因為 `cubic-bezier(0.4, 0, 0.2, 1)` 看起來眼熟就寫上去。
3. **延伸 codebase 既有的 tokens，不要另起爐灶。** 若 `--ease-out` 或 duration scale 已存在就用它；平行搞一套是缺陷。
4. **Reduced motion 與 hover gating 跟動畫一起交付**，不是之後補。
5. **用能解決問題的最便宜工具。** 不要為了一個 fade 裝一個 motion library。

## 建構決策序列

### 1. 這東西到底該不該動畫？

| 使用頻率 | 判定 |
| --- | --- |
| 每天 100+ 次（keyboard shortcut、command palette 開關） | **永不動畫。到此為止。** |
| 每天數十次（hover 效果、清單導覽） | 只允許近乎無感的動效——又快又淡，或乾脆不動 |
| 偶爾（modal、drawer、toast） | 標準動畫 |
| 罕見／首次（onboarding、成功、慶祝時刻） | delight 預算只花在這裡 |

**鍵盤觸發的操作是直接出局，不是自由心證。** Raycast 的開關沒有任何動畫——對一個一天被打開幾百次的東西，那才是正確的。

需求過不了這道閘門就直說，不寫動畫，改提非動效替代方案（瞬時狀態切換、靜態 affordance）。

### 2. 目的是什麼？

繼續之前，必須用以下其中一個詞說出目的：

- **Feedback**——確認介面聽到了使用者的操作
- **Spatial consistency**——交代東西從哪來、往哪去
- **State indication**——讓狀態變化清晰可讀
- **Preventing a jarring change**——銜接原本會瞬移跳變的內容
- **Explanation**——示範某個東西怎麼運作（僅限行銷／onboarding）
- **Delight**——只允許出現在「罕見／首次」那一層

說不出目的就不要做。「看起來很酷」用在高頻元素上，正是喊停的理由。

另外檢查**功能面**：使用者正在閱讀或操作的資料，不得為了風格而動。裝飾性的滑鼠跟隨效果屬於行銷頁——不屬於 banking app 裡的圖表。

### 3. 選工具——能用的裡面挑最便宜的

由上往下走，停在第一個符合的。

| 需求 | 工具 |
| --- | --- |
| Hover、按壓、顏色、由 class 或 attribute 控制的狀態切換 | **CSS transition** |
| Mount 時的入場動畫，不想碰 JS state | **CSS `@starting-style`** |
| 預定軌跡的動效，且頁面忙碌載入時必須保持流暢 | **CSS animation**（跑在 main thread 之外） |
| 要程式化控制、又要 CSS 等級效能、不想引入 library | **WAAPI**（`element.animate()`） |
| Spring、layout animation、exit animation、手勢驅動的值 | **Motion**（`motion.dev`） |

CSS 動畫在頁面高負載時勝過 JS——它跑在 main thread 之外；`requestAnimationFrame` 系的動畫在瀏覽器載入、跑 script、繪製時會掉幀。預定軌跡用 CSS，動態且可中斷的用 JS。

如果任務要的其實是一個**元件**而不是一段動畫——toast、drawer、command menu、dropdown——先停下來，改用現成的 UI 元件庫（選型依公司 ADR 流程決定），不要手刻。手刻的下場就是一個 `<div>` dropdown 加上零 focus management。

### 4. 選屬性

- **只動 `transform` 和 `opacity`。** 它們跳過 layout 與 paint、跑在 GPU 上。`width`／`height`／`margin`／`padding`／`top`／`left` 三關全踩。（`clip-path` 是獲准的第四個屬性——見 RECIPES.md。`height` 只在 accordion 容忍，因為沒有 transform 等價物。）
- **永不 `scale(0)`。** 從 `scale(0.9–0.97)` + `opacity: 0` 開始。真實世界沒有東西是從虛無中出現的。
- **Popover、dropdown、menu、tooltip 的 `transform-origin` 設在觸發點**——Base UI 提供 `var(--transform-origin)`。**Modal 豁免**：它不錨定在任何 trigger 上，保持置中。
- **`translate()` 的百分比**相對於元素自身尺寸——`translateY(100%)` 不管內容多高都剛好移動自身高度。優先於寫死的 pixel。
- **在 Motion 裡用完整 transform 字串。** `x`／`y`／`scale` 簡寫沒有硬體加速，高負載時掉幀：

```jsx
<motion.div animate={{ x: 100 }} />                          // drops frames under load
<motion.div animate={{ transform: "translateX(100px)" }} />  // hardware accelerated
```

- **不要用父層 CSS variable 驅動子元素的 transform**——每次更新會重算所有子元素的 style。直接在該元素上設 `transform`。

### 5. Easing 與時長——或改用 spring

**Easing**，依決策順序：

| 情境 | Easing |
| --- | --- |
| 入場或退場 | `ease-out` |
| 在畫面上移動／變形 | `ease-in-out` |
| Hover／顏色變化 | `ease` |
| 等速運動（marquee、進度） | `linear` |
| 預設 | `ease-out` |

**UI 上永不 `ease-in`。** 它起步慢，恰好拖延使用者最專注的那一刻。200ms 的 `ease-out` *感覺*比 200ms 的 `ease-in` 快。

瀏覽器內建 easing 太弱，用這些：

```css
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);        /* strong ease-out for UI */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);    /* strong ease-in-out for on-screen movement */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);     /* iOS-like drawer curve (Ionic) */
```

需要這裡沒有的曲線，去 easing.dev 或 easings.co 找現成的，不要自己手捏。

**時長：**

| 元素 | 時長 |
| --- | --- |
| 按鈕按壓回饋 | 100–160ms |
| Tooltip、小型 popover | 125–200ms |
| Dropdown、select | 150–250ms |
| Modal、drawer | 200–500ms |
| 行銷／說明性內容 | 可以更長 |

**UI 動畫壓在 300ms 以內。** 180ms 的 dropdown 比 400ms 的更有反應感。

**改用 spring 的時機**：帶動量的拖曳、要「有生命感」的元素、使用者可中斷或反轉的手勢、裝飾性滑鼠跟隨：

```js
{ type: "spring", duration: 0.5, bounce: 0.2 }        // Apple-style — easier to reason about
{ type: "spring", mass: 1, stiffness: 100, damping: 10 }  // traditional physics — more control
```

Bounce 保持在 0.1–0.3；多數 UI 避免 bounce——留給 drag-to-dismiss 與玩味互動。

### 6. 中斷與退出

- **會被快速連續觸發的東西用 transition，不用 keyframes**——toast、toggle、任何一秒內可能觸發兩次的元素。Transition 從當前值重定向；keyframes 從零重播。
- **手勢用 spring**，因為 spring 在中斷時會把速度帶進下一段動畫。
- **怎麼進就怎麼出。** 從底部滑入的 toast 就從底部離開。對稱的路徑正是 swipe-to-dismiss 之所以直覺的原因。
- **使用者在「決定」的環節用不對稱時序。** 深思熟慮的那一側放慢（hold-to-confirm 按住：2s linear），系統回應那一側乾脆（放開：200ms ease-out）。

### 7. Reduced motion 與 pointer gating

每次都跟動畫一起交付。

```css
@media (prefers-reduced-motion: reduce) {
  .element { animation: fade 0.2s ease; } /* keep opacity/color, drop transform-based motion */
}

@media (hover: hover) and (pointer: fine) {
  .element:hover { transform: scale(1.05); } /* touch fires false hovers on tap */
}
```

```jsx
const reduce = useReducedMotion();
const closedX = reduce ? 0 : '-100%';
```

Reduced motion 的意思是**更少、更溫和**的動畫，不是歸零——保留幫助理解的 transition，拿掉位移與位置變化。

## Recipes

常見案例的可直接起手的實作——按鈕按壓、dropdown、tooltip、modal、drawer、toast、accordion、stagger、hold-to-confirm、tab indicator、scroll reveal、drag-to-dismiss——見 [RECIPES.md](RECIPES.md)。需求對上其中一項時就載入它，從 recipe 出發而不是白紙起稿。

## Never Ship — 交付前自檢

以下每一項在 `review-animations` 都是自動 block：

| 永不 | 改用 |
| --- | --- |
| `transition: all` | 逐一點名確切屬性 |
| `transform: scale(0)` 入場 | `scale(0.95)` + `opacity: 0` |
| UI 元素上的 `ease-in` | `ease-out` 或強力自訂曲線 |
| 刻意設計的動畫用內建 `ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` |
| Keyboard shortcut 或每日 100+ 次操作加動畫 | 不動畫 |
| UI 時長超過 300ms 又講不出理由 | 150–250ms |
| 錨定 trigger 的 popover 用 `transform-origin: center` | `var(--transform-origin)`（modal 豁免） |
| Toast、toggle 等高頻觸發元素用 keyframes | CSS transition |
| 動畫 `width`／`height`／`margin`／`padding`／`top`／`left` | `transform`／`opacity` |
| 高負載下用 Motion 的 `x`／`y`／`scale` props | 完整 `transform` 字串 |
| 未 gate 的 `:hover` 動效 | `@media (hover: hover) and (pointer: fine)` |
| 缺 `prefers-reduced-motion` | 給更溫和的變體，不是歸零 |
| 所有元素同時入場 | 30–80ms stagger |

## 產出

把 code 寫出來。然後最多幾行：

- **閘門判定**——頻率層級與命名的目的。若需求中有被打回的部分，說是哪一項、為什麼。
- **配料**——工具、屬性、曲線、時長或 spring 參數，各一行。
- **要人工感受的部分**——若成果取決於 code 看不出來的手感（crossfade、spring 的 bounce、入場清單的 opacity/height 配比），明說並指出檢查方法：以 2–5 倍時長播放或用 DevTools animation inspector 逐幀看、手勢上實機測、隔天用新鮮的眼睛再看一次。

不要把這段膨脹成報告。Code 才是交付物。

## 語氣

有主見、簡短。當誠實的答案是「這東西不該動畫」，就照實給——這個答案正是本 skill 存在的理由。當手感真的無法從 code 判定，就明說，不要硬猜一個值。

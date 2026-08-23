# Animation Standards Reference — 動畫標準參照

審查背後的精確數值、曲線與規則。Findings 引用這裡的值，不要近似。蒸餾自 Emil Kowalski 的動畫方法論。

## 該不該動畫？（頻率表）

| 頻率 | 判定 |
| --- | --- |
| 每天 100+ 次（keyboard shortcut、command palette 開關） | 永不動畫 |
| 每天數十次（hover 效果、清單導覽） | 拿掉或大幅縮減 |
| 偶爾（modal、drawer、toast） | 標準動畫 |
| 罕見／首次（onboarding、回饋、慶祝） | 可以加 delight |

**永不動畫鍵盤觸發的操作**——它們每天重複數百次，動畫只會讓它們感覺又慢又脫節。（Raycast 開關無動畫——對每天用數百次的東西是正確的。）

動效的正當目的：spatial consistency、state indication、explanation、feedback、preventing jarring change。高頻元素上的「看起來很酷」不算。

## Easing

決策順序：
- 入場或退場 → **`ease-out`**（起步快，有反應感）
- 在畫面上移動／變形 → **`ease-in-out`**
- Hover／顏色變化 → **`ease`**
- 等速運動（marquee、進度） → **`linear`**
- 預設 → **`ease-out`**

**UI 上永不 `ease-in`。** 它起步慢，拖延使用者最專注的那一刻。200ms 的 `ease-out` *感覺*比 200ms 的 `ease-in` 快。

內建 CSS easing 太弱，用強力自訂曲線：

```css
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);        /* strong ease-out for UI */
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);    /* strong ease-in-out for on-screen movement */
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);     /* iOS-like drawer curve (Ionic) */
```

其他曲線去 easing.dev 或 easings.co 找——不要從零手捏。

## 時長

| 元素 | 時長 |
| --- | --- |
| 按鈕按壓回饋 | 100–160ms |
| Tooltip、小型 popover | 125–200ms |
| Dropdown、select | 150–250ms |
| Modal、drawer | 200–500ms |
| 行銷／說明性內容 | 可以更長 |

**規則：UI 動畫壓在 300ms 以內。** 180ms 的 dropdown 比 400ms 的更有反應感。更快的 spinner 讓載入感覺更快（實際時間相同）。第一個 tooltip 之後的直接瞬出（跳過 delay 與動畫）讓整條 toolbar 感覺更快。

## 物理性

- **永不 `scale(0)`。** 從 `scale(0.9–0.97)` + `opacity: 0` 開始。真實世界沒有東西從虛無中出現。
- **原點感知的 popover。** 從 trigger 長出來，不是從中心：
  ```css
  .popover { transform-origin: var(--transform-origin); } /* Base UI */
  ```
  **Modal 豁免**——它出現在 viewport 中央，保持 `transform-origin: center`。
- **按鈕按壓回饋。** `:active` 上 `transform: scale(0.97)`，`transition: transform 160ms ease-out`。要輕微（0.95–0.98）。適用於任何可按壓元素。

## Spring

因為模擬物理所以感覺自然；沒有固定時長——由參數決定何時安定。用於：帶動量的拖曳、「有生命感」的元素（Dynamic Island）、可中斷的手勢、裝飾性滑鼠跟隨。

```js
// Apple-style (easier to reason about) — recommended
{ type: "spring", duration: 0.5, bounce: 0.2 }

// Traditional physics (more control)
{ type: "spring", mass: 1, stiffness: 100, damping: 10 }
```

Bounce 保持輕微（0.1–0.3）；多數 UI 避免 bounce——留給 drag-to-dismiss 與玩味互動。Spring 被中斷時保有速度（keyframes 從零重播），所以最適合使用者可能中途反轉的手勢。

滑鼠互動：用 `useSpring` 插值而不是把值直接綁在滑鼠位置（直接綁 = 假、無動量）。僅限裝飾性動效才這麼做。

## 可中斷性

CSS **transition** 可以在動畫中途被中斷並重定向；**keyframes** 從零重播。任何被快速觸發的東西（連續新增的 toast、toggle），transition 更順。

```css
/* Interruptible — good for dynamic UI */
.toast { transition: transform 400ms ease; }

/* Not interruptible — avoid for dynamic UI */
@keyframes slideIn { from { transform: translateY(100%); } to { transform: translateY(0); } }
```

不用 JS 的入場用 `@starting-style`：

```css
.toast {
  opacity: 1; transform: translateY(0);
  transition: opacity 400ms ease, transform 400ms ease;
  @starting-style { opacity: 0; transform: translateY(100%); }
}
```

舊環境 fallback：`useEffect(() => setMounted(true), [])` + `data-mounted` attribute。

## 不對稱時序

使用者在決定的地方放慢，系統回應的地方加快。

```css
.overlay { transition: clip-path 200ms ease-out; }            /* release: fast */
.button:active .overlay { transition: clip-path 2s linear; }  /* press: slow, deliberate */
```

## 效能

- **只動畫 `transform` 與 `opacity`**——它們跳過 layout／paint、跑在 GPU 上。`padding`／`margin`／`height`／`width`／`top`／`left` 會觸發全部三個渲染階段。
- **不要透過父層 CSS variable 驅動子元素 transform**——會重算所有子元素的 style。直接在元素上設 `transform`。
  ```js
  element.style.setProperty('--swipe-amount', `${d}px`); // bad: recalc on all children
  element.style.transform = `translateY(${d}px)`;        // good: only this element
  ```
- **Framer Motion 簡寫沒有硬體加速。** `x`／`y`／`scale` 走 main thread 的 rAF，高負載時掉幀。用完整 transform 字串：
  ```jsx
  <motion.div animate={{ x: 100 }} />                          // drops frames under load
  <motion.div animate={{ transform: "translateX(100px)" }} />  // hardware accelerated
  ```
- **CSS 動畫在高負載下勝過 JS**——跑在 main thread 之外；rAF 系動畫在瀏覽器載入／跑 script／繪製時會卡。預定軌跡用 CSS，動態／可中斷用 JS。
- **WAAPI** 給你 JS 控制與 CSS 效能（硬體加速、可中斷、零 library）：
  ```js
  element.animate([{ clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0 0)' }],
    { duration: 1000, fill: 'forwards', easing: 'cubic-bezier(0.77, 0, 0.175, 1)' });
  ```

## Transform 與 clip-path

- **`translate` 百分比**相對於元素自身尺寸——`translateY(100%)` 不論尺寸都剛好移動自身高度（toast／drawer 類元件的定位方式）。優先於寫死的 px。
- **`scale()` 連子元素一起縮**（字、icon、內容）——對按壓回饋是 feature。
- **3D**：`rotateX/Y` + `transform-style: preserve-3d` 不用 JS 就能做深度／orbit／翻轉。
- **`clip-path: inset(t r b l)`** 是強力動畫工具：每個值從該側向內吃。用途：reveal-on-scroll（`inset(0 0 100% 0)` → `inset(0 0 0 0)`）、hold-to-delete overlay、無縫 tab 顏色過渡（複製 + clip active 複本）、比較滑桿。

## 手勢與拖曳

- **動量關閉**：不要只看距離門檻——計算速度（`Math.abs(distance)/elapsedMs`），`> ~0.11` 即關閉。一個 flick 就該夠。
- **邊界阻尼**：拖過自然邊界後越拖移動越少（真實的東西停下前會先變慢）。
- **Pointer capture**：拖曳開始就 capture，指標離開範圍時拖曳繼續。
- **Multi-touch 保護**：拖曳開始後忽略新增觸點（`if (isDragging) return`）——防跳位。
- **摩擦而非硬牆**——允許越界拖曳但阻力遞增，不要一道看不見的牆。

## 遮掉不完美的 crossfade

Crossfade 調過 easing／時長仍見兩個狀態疊影時，過渡期間加輕微 `filter: blur(2px)`，把它們融成一次感知上的變形。Blur < 20px（重 blur 很貴，Safari 尤其）。

## Stagger

群組入場加 stagger；項目間 30–80ms。更長的 delay 會感覺慢。Stagger 是裝飾性的——播放期間絕不擋互動。

```css
.item { opacity: 0; transform: translateY(8px); animation: fadeIn 300ms ease-out forwards; }
.item:nth-child(2) { animation-delay: 50ms; }
.item:nth-child(3) { animation-delay: 100ms; }
@keyframes fadeIn { to { opacity: 1; transform: translateY(0); } }
```

## 無障礙

```css
@media (prefers-reduced-motion: reduce) {
  .element { animation: fade 0.2s ease; } /* keep opacity/color, drop transform-based motion */
}
@media (hover: hover) and (pointer: fine) {
  .element:hover { transform: scale(1.05); } /* gate hover motion — touch fires false hovers on tap */
}
```

```jsx
const reduce = useReducedMotion();
const closedX = reduce ? 0 : '-100%';
```

Reduced motion 是更少、更溫和的動畫，不是歸零——保留幫助理解的 transition，拿掉位移／位置變化。

## 除錯（手感不確定時在 review 中建議）

- **慢動作**：時長放大 2–5 倍，或用 DevTools animation inspector。檢查顏色 crossfade 乾淨、easing 不突兀停止、`transform-origin` 正確、多屬性協同不脫拍。
- **逐幀**：Chrome DevTools Animations 面板能看出協同屬性之間的時序漂移。
- **實機**測手勢（drawer、swipe）——手機連 dev server IP、用 Safari remote devtools。
- **隔天新鮮的眼睛**——開發當下看不見的瑕疵，之後會浮出來。

## 一致性（cohesion）

動效匹配元件性格：玩味的可以彈一點；專業 dashboard 要俐落、快。好的 toast 之所以感覺對，是 easing、時長、設計互相和諧——稍慢、用 `ease` 而非 `ease-out`，讀起來優雅。入場／退場清單的 opacity + height 配比靠試錯；沒有公式——調到感覺對為止。

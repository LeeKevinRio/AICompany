# Animation Recipes — 動畫食譜

最常出現的案例，各給一份可直接起手的實作。從 recipe 出發再依需求調整——不要白紙重造。

曲線使用 SKILL.md 定義的 `--ease-out`、`--ease-in-out`、`--ease-drawer` tokens。

---

## Button press — 按鈕按壓

任何可按壓元素。即時回饋，讓介面表示「聽到了」。

```css
.button {
  transition: transform 160ms var(--ease-out);
}

.button:active {
  transform: scale(0.97);
}
```

`scale()` 會連子元素一起縮——label 與 icon 一起動，這正是它讀起來像實體按壓的原因。

這裡不需要 hover gating：`:active` 在觸控裝置上就是真實按壓。任何 `:hover` 樣式另外 gate。

---

## Dropdown、popover、menu、select

從觸發點長出來，不是憑空出現。

```css
.popover {
  transform-origin: var(--transform-origin); /* Base UI supplies this */
  transition:
    opacity 200ms var(--ease-out),
    transform 200ms var(--ease-out);
}

.popover[data-starting-style],
.popover[data-ending-style] {
  opacity: 0;
  transform: scale(0.95);
}
```

`transform-origin` 是全部的重點——面板看起來必須是從你剛點的那個東西裡長出來的。

---

## Tooltip

跟 popover 同構、更快，外加多數實作漏掉的那個細節。

```css
.tooltip {
  transform-origin: var(--transform-origin);
  transition:
    transform 125ms var(--ease-out),
    opacity 125ms var(--ease-out);
}

.tooltip[data-starting-style],
.tooltip[data-ending-style] {
  opacity: 0;
  transform: scale(0.97);
}

/* Once one tooltip is open, neighbours open instantly */
.tooltip[data-instant] {
  transition-duration: 0ms;
}
```

初始 delay 防誤觸；之後同時跳過 delay 與動畫，整條 toolbar 會感覺更快。

---

## Modal

唯一保持置中的 popover。

```css
.modal {
  transform-origin: center; /* exempt — not anchored to a trigger */
  transition:
    opacity 250ms var(--ease-out),
    transform 250ms var(--ease-out);
}

.modal[data-starting-style],
.modal[data-ending-style] {
  opacity: 0;
  transform: scale(0.96);
}

.backdrop {
  transition: opacity 250ms var(--ease-out);
}
```

Backdrop 的 opacity 跟著一起動，兩者才會讀成同一個表面。

---

## Drawer / sheet

```css
.drawer {
  transform: translateY(0);
  transition: transform 500ms var(--ease-drawer);
}

.drawer[data-closed] {
  transform: translateY(100%);
}
```

這是 drawer 類元件（如 Vaul）在入場動畫前先藏起自己的方式。

加上拖曳它就變成手勢問題——見下方 **Drag to dismiss**。

---

## Toast

```css
.toast {
  opacity: 1;
  transform: translateY(0);
  transition:
    opacity 400ms ease,
    transform 400ms ease;

  @starting-style {
    opacity: 0;
    transform: translateY(100%);
  }
}
```

- 用 `ease` 而非 `ease-out`、比一般 UI 稍慢：好的 toast（如 Sonner）之所以讀起來優雅，部分原因是動效調校配合元件本身的性格，而不是套用通用 UI 預算。
- 若 `@starting-style` 不可用，退回 mount flag：

```jsx
useEffect(() => { setMounted(true); }, []);
// <div data-mounted={mounted}>
```

Toast 堆疊、清單 reflow 時，opacity 變化要跟 height 變化互相配合。這一對沒有公式——調到感覺對為止，隔天再看一次。

---

## Accordion / collapse

```css
.content {
  overflow: hidden;
  transition:
    height 200ms var(--ease-out),
    opacity 200ms var(--ease-out);
}
```

保持短——這是少數每一幀都要付 layout 成本的動畫，時長拉長既昂貴又發黏。內容高度用 JS 量（或用會提供高度的 headless primitive），不要動畫到 `auto`。

---

## Stagger 群組入場

給使用者偶爾才看到的清單或 grid 用——不是給每天滑過的清單用。

```css
.item {
  opacity: 0;
  transform: translateY(8px);
  animation: fadeIn 300ms var(--ease-out) forwards;
}

.item:nth-child(2) { animation-delay: 50ms; }
.item:nth-child(3) { animation-delay: 100ms; }
.item:nth-child(4) { animation-delay: 150ms; }

@keyframes fadeIn {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

Stagger 是裝飾性的——播放期間絕不能擋住互動。

---

## Hold to confirm — 按住確認

給誤觸代價太高的破壞性操作用。

```css
.overlay {
  clip-path: inset(0 100% 0 0);
  transition: clip-path 200ms var(--ease-out); /* release: snappy */
}

.button:active .overlay {
  clip-path: inset(0 0 0 0);
  transition: clip-path 2s linear;             /* press: slow and deliberate */
}

.button:active {
  transform: scale(0.97);
}
```

這裡 `linear` 才是對的——填滿是進度指示，進度不該有 easing。

---

## Tab indicator 帶顏色過渡

在一排 tab 上逐一調各自的 color transition 永遠差一口氣。改用 clip。

複製整條 tab 列。把複本設成 active 樣式——不同背景、不同文字色。用 clip 只露出 active 那格，切換時動畫 clip：

```css
.tabs-active-copy {
  clip-path: inset(0 60% 0 20%); /* driven by the active tab's position */
  transition: clip-path 250ms var(--ease-in-out);
}
```

文字與背景完美同步變化，因為它們是同一個元素被逐步顯露，而不是兩個顏色在插值。

---

## Scroll reveal

只給行銷面用。不要對使用者天天造訪的功能 UI 做這件事。

```css
.reveal {
  clip-path: inset(0 0 100% 0);
  transition: clip-path 600ms var(--ease-in-out);
}

.reveal[data-visible] {
  clip-path: inset(0 0 0 0);
}
```

用 `IntersectionObserver` 觸發，或 Motion 的 `useInView` 配 `{ once: true, margin: "-100px" }`。只觸發一次——每次滑過都重播的介面是在跟讀者作對。

---

## Drag to dismiss — 拖曳關閉

手勢食譜。用 spring 而非固定時長，因為使用者可以中途反悔。

```js
// Dismiss on a flick, not just on distance
const timeTaken = Date.now() - dragStartTime.current;
const velocity = Math.abs(swipeAmount) / timeTaken;

if (Math.abs(swipeAmount) >= SWIPE_THRESHOLD || velocity > 0.11) {
  dismiss();
}
```

```js
// Set transform on the dragged element directly.
// Driving it through a CSS variable on the parent recalcs styles for every child.
element.style.transform = `translateY(${distance}px)`;
```

好拖曳與壞拖曳的四個分水嶺：

- **Pointer capture**——拖曳開始就 capture，讓手指移出元素範圍時拖曳仍繼續。
- **Multi-touch 保護**——新的觸點進來時 `if (isDragging) return`，否則中途換手指會讓元素跳位。
- **越界阻尼**——拖過自然邊界後，越拖移動越少。真實的東西在停下前會先變慢。
- **摩擦而非硬牆**——允許越界拖曳但阻力遞增，而不是直接拒絕。

用 spring 收尾，讓被中斷的拖曳保有速度：

```js
{ type: "spring", duration: 0.5, bounce: 0.2 }
```

---

## 用 blur 遮掉收不乾淨的 crossfade

當兩個狀態在過渡期間明顯疊影、調 easing 和時長都救不回來時，把接縫糊掉：

```css
.content {
  transition:
    filter 200ms ease,
    opacity 200ms ease;
}

.content.transitioning {
  filter: blur(2px);
  opacity: 0.7;
}
```

沒有 blur 時，眼睛讀到的是兩個物件在交換；blur 把它們融成一次感知上的變形。控制在 20px 以下——重 blur 很貴，Safari 尤其。

---

## 程式化控制、但不引 library

動效需要 JS 控制但不值得多一個依賴時，WAAPI 給你 CSS 等級的效能：

```js
element.animate(
  [{ clipPath: 'inset(0 0 100% 0)' }, { clipPath: 'inset(0 0 0 0)' }],
  { duration: 1000, fill: 'forwards', easing: 'cubic-bezier(0.77, 0, 0.175, 1)' }
);
```

硬體加速、可中斷、零 bundle 成本。

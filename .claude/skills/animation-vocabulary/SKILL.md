---
name: animation-vocabulary
description: 動效詞彙反查表——把對網頁動畫的模糊描述（「popover 打開時那種彈一下的感覺」→ Pop in；「iOS 拉到底回彈」→ Rubber-banding）對應到精確術語。當有人問「那個效果叫什麼」、或描述一個動效但說不出名字、需要正確用語寫需求單／工單／prompt 時使用。只負責命名效果，不負責設計或實作（實作用 animate）。
---

> **本 skill 改作自 emilkowalski/skills（MIT），適用於本公司各產品線前端動效工作。**
> **風控地板優先**：凡涉及面向使用者的建議類／揭露類內容，其字級、對比、常駐不摺疊等風控樣式地板與逐字定稿制度優先於本 skill 任何建議；本 skill 不得用於改寫任何風控定稿文案。
>
> 來源：[emilkowalski/skills](https://github.com/emilkowalski/skills) `animation-vocabulary`，commit `d23d7f88a2e21c9e4b1418c7abe420f5c1052ba7`；授權見本目錄 [LICENSE](LICENSE)。改作內容：敘述層繁中化、剝除行銷內容；術語與定義忠實保留，惟分類有微調（Page transition／View transition 由 Scroll 節移至 Transitions Between States 節，定義未動）。

# Animation Vocabulary — 動效詞彙表

把對動效的模糊描述轉成精確術語，讓提問的人知道該用什麼詞去要、去寫工單、去下 prompt。

## Quick Start

對方鬆散地描述一個效果，你用這個格式回傳對應術語：

```
**Stagger** — 多個項目依序入場，彼此之間隔一小段 delay，形成瀑布式的層次感。
```

若多個術語都可能符合，最佳匹配放最前面，再列 1–2 個備選，各附一行差異說明。

## 指示

1. **讀意圖，不是讀關鍵字。** 使用者描述的是他們*看到*或*感覺到*的東西（「有彈性」、「滑出去」、「自己畫出來」），不是技術名稱。把感受對應到下方詞彙表。
2. **引用詞彙表原文。** 表內定義是權威版本——照用，不要改寫。
3. **相近術語要辨析。** 當兩個術語競爭時（*Clip-path* vs *Mask*、*Pop in* vs *Bounce*、*Shared element transition* vs *Layout animation*），對比說明讓對方能自己挑。
4. **沒有完全匹配時**，指出最接近的術語並明說是近似，或用詞彙表的語言描述該效果（例如「那是一組 *scale-in* 入場的 *stagger*」）。
5. **不超出這份詞彙表。** 表裡真的沒有的術語就直說沒有，不要發明——但可以用表內的詞解釋概念。
6. **保持精簡。** 問名字就給名字，不要寫論文。術語先行，被追問才展開。

## 範例

**範例 1——憑感覺描述**
使用者：「popover 從你點的那顆按鈕長出來、而不是從自己中心長出來，那叫什麼？」
輸出：
```
**Origin-aware animation** — 元素從觸發它的東西長出來，例如 popover 從打開它的按鈕長出，而不是從自身中心（CSS 預設）。
```

**範例 2——辨析**
使用者：「一張圖變成另一張圖的那種。」
輸出：
```
**Morph** — 一個形狀平滑地變成另一個形狀，例如 Dynamic Island。

相近備選：
- **Crossfade** — 若兩者只是原地互相淡入淡出。
- **Shared element transition** — 若元素從一個位置移動並變形到另一個位置。
```

**範例 3——物理手感**
使用者：「iOS 那種捲到底會抵抗然後彈回來的。」
輸出：
```
**Rubber-banding** — 拖過邊界時的阻力與回彈（iOS overscroll 的手感）。
```

## 詞彙表

### Entrances & Exits — 元素如何出現與消失
- **Fade in / Fade out** — 元素透過 opacity 變化出現或消失。
- **Slide in** — 元素從畫面外（左、右、上、下）滑入。
- **Scale in** — 元素從較小長到全尺寸，通常配 fade。
- **Pop in** — 元素帶一點 overshoot 出現，像彈進定位。
- **Reveal** — 內容被逐步揭開，通常靠動畫 clip-path 或 mask。
- **Enter / Exit** — 元素被加入或移出畫面時播放的動畫。

### Sequencing & Timing — 協調多個元素或時刻
- **Keyframes** — 動畫中定義的節點（0%、50%、100%），瀏覽器補齊中間。
- **Interpolation / Tween** — 在起訖值之間生成所有中間幀，讓運動連續。
- **Stagger** — 多個項目依序入場，彼此隔一小段 delay，形成瀑布。
- **Orchestration** — 刻意編排多段動畫的時序，讓它們讀起來像一次協調的運動。
- **Delay** — 動畫開始前的等待時間。
- **Duration** — 動畫持續多久。
- **Fill mode** — 元素在動畫開始前／結束後是否保留首幀或末幀樣式（如 forwards）。
- **Stepped animation** — 分成離散步驟的動畫，像倒數計時器。

### Movement & Transforms — 改變元素的位置、尺寸或角度
- **Translate** — 沿 X 或 Y 軸移動元素。
- **Scale** — 放大或縮小元素。
- **Rotate** — 繞一個點旋轉元素。
- **Skew** — 沿 X 或 Y 軸斜切元素，剪出非矩形形狀。
- **3D tilt / Flip** — 在 3D 空間旋轉（rotateX / rotateY）以增加深度。
- **Perspective** — 3D 效果的強度——值越低深度越誇張，像觀者靠得更近。
- **Transform origin** — 縮放或旋轉的錨點。
- **Origin-aware animation** — 元素從觸發它的東西長出來，例如 popover 從打開它的按鈕長出，而不是從自身中心（CSS 預設）。

### Transitions Between States — 銜接狀態、視圖或元素
- **Crossfade** — 一個元素淡出、另一個在同位置淡入。
- **Continuity transition** — 以視覺連接前後狀態、讓使用者保持定向的變化，例如同一個矩形放大縮小。
- **Morph** — 一個形狀平滑地變成另一個形狀，例如 Dynamic Island。
- **Shared element transition** — 元素從一個位置移動並變形到另一個位置，像縮圖展開成卡片。
- **Layout animation** — 元素尺寸或位置改變時動畫到新位置，而不是瞬間跳過去。
- **Accordion / Collapse** — 區塊平滑展開／收合高度以顯示或隱藏內容。
- **Direction-aware transition** — 前進時內容往一個方向滑、返回時往反方向滑，讓導覽有方向感。
- **Page transition** — 從一個頁面或路由導向另一個時播放的動畫。
- **View transition** — 瀏覽器在兩個狀態或頁面之間 morph，連接共享元素。

### Scroll — 綁定捲動的動效
- **Scroll reveal** — 元素進入 viewport 時淡入或滑入定位。
- **Scroll-driven animation** — 進度直接綁在捲動位置上的動畫。
- **Parallax** — 前後景以不同速度捲動，製造深度。

### Feedback & Interaction — 回應使用者操作
- **Hover effect** — 游標移到元素上時的視覺變化。
- **Press / Tap feedback** — 點擊時輕微縮小，讓元素有實體感。
- **Hold to confirm** — 按住按鈕時逐漸填滿的進度效果。
- **Drag** — 抓住元素移動，放開時常帶動量。
- **Drag to reorder** — 拖曳清單項目重新排序，其他項目讓位。
- **Swipe to dismiss** — 把元素拖出畫面來關閉它，像 drawer 或 toast。
- **Rubber-banding** — 拖過邊界時的阻力與回彈（iOS overscroll 的手感）。
- **Shake / Wiggle** — 快速左右抖動，表示錯誤或輸入被拒。
- **Ripple** — 從點按位置擴散的圓圈，確認按壓。

### Easing — 速度如何隨動畫變化
- **Easing** — 動畫加速或減速的方式。
- **Ease-out** — 快進慢出。多數 UI 與任何回應使用者的動效的預設。
- **Ease-in** — 慢進快出。通常避免；會顯得發黏。
- **Ease-in-out** — 慢—快—慢。適合已在畫面上、從 A 移到 B 的元素。
- **Linear** — 等速。UI 避免；留給 spinner 或 marquee。
- **Cubic-bezier** — 自訂的 easing 曲線，精確控制。
- **Asymmetric easing** — 加速與減速速率不同的曲線，比對稱曲線更有生命感。

### Spring Animations — 物理式動效，固定時長 easing 的替代
- **Spring** — 由物理參數（tension、mass、damping）而非固定時長驅動的運動。
- **Stiffness / Tension** — 彈簧拉向目標的力道。越高越彈脆。
- **Damping** — 彈簧多快安定。越低越彈、震盪越多。
- **Mass** — 被動畫元素的「重量感」。越重越慢、越沉。
- **Bounce** — 會 overshoot 再安定的彈簧，增添玩味。
- **Perceptual duration** — 彈簧「感覺上」結束的時間，即使底下還在微幅安定。
- **Momentum** — 帶著速度的運動，特別是拖曳或中斷之後。
- **Velocity** — 元素移動的速度與方向。彈簧被中斷時會把它帶進下一段動畫，被甩出去的元素保有速度。
- **Interruptible animation** — 可以在飛行中被平滑重定向、而不必先播完的動畫。

### Looping & Ambient Motion — 自己會動的動畫
- **Marquee** — 連續循環捲動的文字或內容。
- **Loop** — 重複播放的動畫，固定次數或無限。
- **Alternate (yoyo)** — 每一輪先正播再倒播的 loop，而不是跳回起點。
- **Orbit** — 一個元素繞著另一個連續轉圈。
- **Pulse** — 溫和重複的縮放或 opacity 變化，吸引注意。
- **Float** — 溫和連續的上下漂浮，讓靜態元素顯得輕盈有生命。
- **Idle animation** — 元素閒置等待互動時播放的細微動效。

### Polish & Effects — 好與極好之間的小細節
- **Blur** — 用 blur filter 柔化元素或遮掉微小瑕疵。
- **Clip-path** — 把元素裁成形狀，用於 reveal、mask、before/after 滑桿。
- **Mask** — 用形狀或漸層隱藏／顯露元素的一部分——像 clip-path，但邊緣可柔化淡出。
- **Before / after slider** — 可拖曳的分隔線，在兩張疊圖之間擦拭比較。
- **Line drawing** — SVG path 自己畫出自己，像隱形的筆在描。
- **Text morph** — 文字變化時逐字元動畫，把注意力帶到新值上。
- **Skeleton / Shimmer** — 載入時顯示的佔位框加流動光澤。
- **Number ticker** — 數字滾動或遞增到目標值。
- **Tabular numbers** — 等寬數字，數值變化時不會左右位移。ticker、計時器、計數器必備。
- **Typewriter** — 文字一次一個字元出現，像打字。

### Performance — 讓動效順而不卡的因素
- **Frame rate (FPS)** — 每秒繪製的幀數。60fps 是流暢底線；新螢幕上 120fps。
- **Jank** — 瀏覽器跟不上、掉幀時肉眼可見的卡頓。
- **Dropped frame** — 瀏覽器沒趕上繪製期限的一幀，造成微小的頓挫。
- **Compositing** — 讓 GPU 在獨立 layer 上移動或淡出元素，不重跑 layout 與 paint。
- **will-change** — CSS 提示某元素即將動畫，讓瀏覽器提前把它升到獨立 layer。
- **Layout thrashing** — 動畫 width、height、top、left 這類屬性，逼瀏覽器每幀重算 layout，造成 jank。

### Principles to Know — 決定何時動、怎麼動的原則
- **Purposeful animation** — 動效要有功能——定向、回饋、呈現關係——不是純裝飾。
- **Anticipation** — 移動前先往反方向小幅預備，暗示即將發生的事。
- **Follow-through** — 主運動停止後，局部繼續移動並微幅安定，增添重量感。
- **Squash & stretch** — 移動時讓元素形變，傳達重量、速度與彈性。
- **Perceived performance** — 對的動畫讓介面感覺更快，即使實際沒有。
- **Frequency of use** — 動畫被看見得越頻繁，就該越短、越含蓄。
- **Spatial consistency** — 讓元素跨狀態保持身分與位置的連續，使用者永遠不會跟丟。
- **Hardware acceleration** — 只動 transform 與 opacity，讓 GPU 保持流暢。
- **Reduced motion** — 尊重使用者的 prefers-reduced-motion 設定，調淡或移除動效。

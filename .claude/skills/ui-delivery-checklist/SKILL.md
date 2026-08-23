---
name: ui-delivery-checklist
description: UI 交付自檢清單——前端 UI 交付前，實作者對照本清單逐項自檢；qa-reviewer 審查任何含 UI 的 diff 時也用同一份清單複核。涵蓋對比、input 狀態完整性、響應式安全、禁捏造數據、token 紀律等可機械判定的閘門。任何面向使用者的頁面或元件要出手前必用。
---

# UI Delivery Checklist — UI 交付自檢清單

> 本清單概念參考 [Nutlope/hallmark](https://github.com/Nutlope/hallmark)（MIT）的 slop-test 閘門
> （commit `13ac0ec7e148655948100b6396439e481361d690`），取其中**可機械判定、與產品型態無關**的子集，
> 依本公司情境重寫。動效手感的專門審查見 `review-animations`；一般 code 正確性見 `code-review-checklist`。

## 第 0 節・風控地板（最高優先，先讀這節）

本節優先於本清單其餘所有條目，也優先於任何外部設計建議：

1. **地板優先權**：面向使用者的建議類／揭露類內容（免責聲明、風險揭露、任何建議性質文案）
   有風控樣式地板——字級不得低於所在區塊內文、對比不得低於正文標準、與主結論同區塊常駐、
   不得摺疊、不得移至頁尾。任何「簡化版面」「收斂元素」「刪掉不必要內容」的設計建議
   碰到這條地板一律讓位。
2. **逐字定稿不可改**：經風控逐字定稿的文案，一個字都不能動。本清單（與任何 skill）的文案類建議
   對這些內容一律無效；要改只能走風控定稿流程重新審。
3. **白名單讓位**：站內已明文記錄的設計取捨（例如視覺規範中記載的刻意低對比裝飾元素），
   屬於已裁決事項——本清單的機械檢查對白名單內的項目不翻案。發現疑似衝突時，
   先查有無記錄；有記錄就放行並在報告註明，沒有記錄才列為 finding。

## 使用方式

- **實作者**：交付前逐項自檢，每題答案必須是「否」（= 沒踩到）。有「是」就修完再交。
- **qa-reviewer**：審 UI diff 時對照本清單複核，違反項列入 findings 並標 severity
  （對比不足、捏造數據為 BLOCKING；其餘依影響定級）。
- 刻意違反某條時，必須在交付說明中註明理由，並記錄到該產品的視覺規範（形成第 0 節的白名單）。

## 第 1 節・對比與可讀性

- [ ] **1.1 正文對比達標**：所有 body text（< 24px regular 或 < 18px bold）對其*實際*背景
      達 WCAG 4.5:1（或 APCA Lc ≥ 60）。逐一配對每個 `color` 與其生效的 `background-color` 驗算，
      特別注意：卡片換了背景但文字繼承外層 `color`、muted 文字疊在較深的次級表面上。
- [ ] **1.2 大字與圖示對比達標**：大字（≥ 24px regular / ≥ 18px bold）、icon、focus ring
      對背景達 WCAG 3:1（或 APCA Lc ≥ 45）。
- [ ] **1.3 按鈕文字 ≠ 按鈕底色**：按鈕的文字色與填色以 OKLCH 比對，明度（lightness）差 < 5%
      **且** chroma 差 < 0.05 即 fail（黑字黑鈕是最常出貨的錯誤，
      成因通常是換了填色 token 卻忘了換文字 token）。
- [ ] **1.4 深色區塊翻文字色**：任何背景明顯偏深的區塊／面板，同一條規則裡就要把文字色換成亮色，
      並確認巢狀子元素正確繼承——不能只翻表面忘了翻墨水。
- [ ] **1.5 白名單檢查**：以上任何一條疑似違反時，先查該產品視覺規範有無記錄為刻意取捨；
      有記錄不翻案（見第 0 節第 3 條）。

## 第 2 節・Input 與互動狀態完整性

- [ ] **2.1 五態俱全**：input / textarea / select 的 default、hover、focus、error、disabled
      五個狀態都有定義，不是只有 default + hover。
- [ ] **2.2 狀態切換不位移**：狀態間 `border-width` 保持不變（狀態變化走 `background-color`、
      `outline`、`box-shadow`、`border-color`，不走 `border-width`——它會造成 layout shift）。
- [ ] **2.3 Focus ring 用 outline**：focus 樣式用 `outline` + `outline-offset` 實作，
      不用改 border 的方式（同樣是避免幾何位移）。
- [ ] **2.4 同表單同高**：同一表單內 input 高度與相鄰按鈕高度一致。
- [ ] **2.5 Helper text 預留空間**：helper／error 文字的槽位保留 `min-height: 1lh`，
      錯誤出現時不把頁面往下推。
- [ ] **2.6 Disabled 三通道**：disabled 不能只靠 `opacity`——要同時有降透明度、
      `cursor: not-allowed`、以及原生 `disabled` attribute（或 `aria-disabled="true"`）。
- [ ] **2.7 Focus ring 即現**：focus ring 必須瞬間出現，不得有淡入 transition——
      鍵盤使用者需要立即的位置指示。
- [ ] **2.8 所有互動元素狀態齊全**：按鈕、連結等互動元素至少具備
      default + hover + `:focus-visible` + `:active` + `:disabled`（如適用）。

## 第 3 節・響應式安全

- [ ] **3.1 全區間無橫向捲動**：320px–1920px 任一寬度都不得出現水平捲軸。
      防線是 `html` 與 `body` 都設 `overflow-x: clip`（用 `clip` 不用 `hidden`，
      `clip` 保留子孫的 `position: sticky` / `fixed`）。
- [ ] **3.2 可點擊文字不折行**：按鈕文字、nav 連結、tab 標籤、CTA 在任何寬度都不得折成兩行——
      優先縮短文字，其次 `white-space: nowrap` 讓父層 reflow。
- [ ] **3.3 含圖 grid 用 `minmax(0, 1fr)`**：放圖片的 grid track 不得用裸 `1fr`
      （`1fr` 的隱含最小值是內容 intrinsic 寬度，大圖會把版面撐出 viewport）。
- [ ] **3.4 大標題可斷字**：display 級文字（h1、hero 標題等）具備
      `overflow-wrap: anywhere; min-width: 0`，長複合詞不會撐爆窄螢幕。

## 第 4 節・動效底線

（動效手感的完整審查交給 `review-animations`；這裡只留出貨前的機械檢查。）

- [ ] **4.1 無 `transition: all`**：一律逐一點名要過渡的屬性。
- [ ] **4.2 不動畫 layout 屬性**：不得動畫 `width`／`height`／`top`／`left`／`margin`／`padding`
      （accordion 的 height 為已知例外）。
- [ ] **4.3 Reduced motion 有覆蓋**：每一段位移類動效都有
      `@media (prefers-reduced-motion: reduce)` 的溫和替代。
- [ ] **4.4 自動輪播可暫停**：任何自動輪替的內容（carousel、跑馬燈）在 hover 與 focus 時暫停
      （WCAG 2.2.2）。

## 第 5 節・誠實內容

- [ ] **5.1 禁止捏造數據**：頁面上任何量化宣稱（成長百分比、使用人數、正確率、報酬數字……）
      都必須是使用者／需求方提供或有明確來源。不得為了填版面編數字。
      沒有真實數字時：以「—」加標註的占位區塊呈現、明文標「待確認」向需求方要數字、
      或整段改為不依賴數字的設計。**此條違反一律 BLOCKING**——本公司產品線含金融資訊類產品，
      捏造數據同時觸犯風控紅線。
- [ ] **5.2 無占位假資料出貨**：Jane Doe／John Smith 類假名、Lorem ipsum、
      開發用假數列不得出現在交付版本。

## 第 6 節・Token 紀律

- [ ] **6.1 顏色與字體只走 token**：渲染層不得出現脫離 `:root`（或主題區塊）定義的
      inline 色值（`#hex`、`rgb()`、`oklch()`…）或 `font-family`。
      需要新值就先提進 token 區塊命名，再引用。
- [ ] **6.2 間距走既有 scale**：padding／gap／margin 用專案既有的 spacing scale，
      不出現 `padding: 17px` 這種一次性魔術數字。

## 第 7 節・交付前流程

1. **先自評再送審**：跑清單前先快速自問三軸——層級（兩秒內分得出主次嗎）、
   執行（細節都在規格內嗎）、克制（每個元素都有存在理由嗎）。任何一軸明顯偏弱，
   先改一輪再進清單，不要帶著已知弱點進審查。
2. **記錄取捨**：任何刻意違反清單的決定，寫進該產品的視覺規範（含理由），
   讓下一次檢查有白名單可查、不重複翻案。
3. **報告格式**：自檢結果附在交付說明中——通過的節可以一行帶過，
   未通過或走白名單的逐條列出。qa-reviewer 的複核結論併入其標準輸出契約。

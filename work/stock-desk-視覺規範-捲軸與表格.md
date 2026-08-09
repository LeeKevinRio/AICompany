# stock-desk 視覺規範 — 捲軸與持倉表格配色

- 任務來源：CEO 反映持倉明細捲軸在 Windows 系統下顏色對比過於突兀（OS 預設亮色捲軸疊在深色介面上）。
- 範圍：全站捲軸配色規範（非只修一處）+ 持倉表格區配色一致性檢視。
- 分支：`product/stock-desk`。本文件只給規範，不改 code；CSS 由 frontend-engineer 貼入 `apps/stock-desk/frontend/app/globals.css`。

---

## 0. 盤點結論（先講看到什麼）

- 全站色階基準（已盤點，來源見各檔案）：
  - 頁面底色：`body` 用 Tailwind `bg-black`（`#000000`），蓋過 `globals.css` 的 `--background: #0a0a0a`（`html,body { background: var(--background) }` 的選擇器優先度低於 class）。兩者其實非常接近（neutral-950 = `#0a0a0a`），視覺上無感差異，**不建議動**，只在此記錄以免日後有人誤以為是 bug。
  - 卡片 / modal 底色：`bg-neutral-950`（`#0a0a0a`），見 `EditPositionModal.tsx:140`、`EditAlertRuleModal.tsx:238`。
  - 表格區塊：`thead` 一律 `bg-neutral-900 text-neutral-400`；列分隔一律 `border-t border-neutral-800`；外框容器一律 `border border-neutral-800`。跨 5 個表格（`PositionsTable.tsx`、`AlertRulesSection.tsx`、`DataSourcesSection.tsx`、`BacktestReportView.tsx`、`ImportCsvSection.tsx`）**完全一致**，是站內既定慣例。
  - 目前**沒有任何一個表格**有斑馬紋，也**沒有任何一個表格**有列 hover 態 —— 這是全站一致的現況，不是持倉表格單一的缺失（見下方第 2 節）。
  - 站內目前沒有任何 `::-webkit-scrollbar` / `scrollbar-color` 規則，捲軸完全吃系統預設，這正是 Windows 上出現亮色捲軸疊在深色介面、對比突兀的原因。
  - `work/` 下無既有捲軸或表格視覺規範可沿用，本文件為新建規範。

---

## 1. 捲軸規範（全站統一，寫在 `globals.css` 全域層級）

### 1.1 設計決策與色值

目標：捲軸「看得到但不搶戲」，延續站內既有的低對比分隔線語彙（`border-neutral-800` 目前就是用極低對比做「看得到但不搶戲」的分隔線，對黑底對比僅 **1.39:1**，這是已經存在且沒人抱怨的站內慣例，可作為捲軸設計的對比基準參照，不需要另外發明一套更亮的語言）。

| 用途 | Token | Hex | 對黑底 `#000000` 對比 | 對 track（`neutral-900`）對比 |
|---|---|---|---|---|
| 捲軸 track（軌道） | `neutral-900` | `#171717` | 1.05:1 | — |
| 捲軸 thumb 預設 | `neutral-700` | `#404040` | 2.03:1 | 1.73:1 |
| 捲軸 thumb hover | `neutral-600` | `#525252` | 2.68:1 | 2.29:1 |
| 捲軸 thumb active（拖曳中） | `neutral-500` | `#737373` | 4.43:1 | 3.78:1 |

理由：
- **track 用 `neutral-900`**：與站內 `thead` 底色同一階（`bg-neutral-900`），不新增色階，且比純黑 `#000000` 只亮一點點，本身幾乎不可見，只在滾動時給 thumb 一個可辨識的軌跡。
- **thumb 預設用 `neutral-700`**：與站內按鈕/輸入框邊框慣用色同階（`border-neutral-700`，見 `NavBar.tsx:60/69`），對黑底對比 2.03:1，比目前的分隔線（1.39:1）更明顯一階，足以在深色背景上被看到，但仍遠低於文字要求的對比門檻，不會像 Windows 預設淺灰捲軸那樣搶眼。
- **hover / active 逐階變亮**（`neutral-600` → `neutral-500`）：符合站內既有「互動態變亮」慣例（例如 `hover:bg-neutral-800`、`hover:bg-neutral-700` 用在按鈕上），讓使用者滑到捲軸上有清楚的可互動回饋；active（拖曳中）對比拉到 4.43:1，操作時最清楚。
- 這組對比刻意低於 WCAG 1.4.11 非文字元件 3:1 門檻的預設態，是**刻意的設計取捨**：捲軸是系統性 UI chrome、非內容，且站內既有分隔線慣例本就走「極低對比、看得到但不搶戲」路線；若之後有無障礙稽核要求，可直接把 thumb 預設色上調到 `neutral-600`（2.68:1）作為折衷，不需要改動整份規範架構。
- **不動 `neutral-400`**：風控相關文字色階（`text-neutral-400`，已定對黑底 7.66:1）完全不在本規範調整範圍內。

### 1.2 完整 CSS（可直接貼進 `apps/stock-desk/frontend/app/globals.css`）

```css
/* ============================================================
   Dark-theme scrollbar — applies globally to every scrollable
   element (page body, `overflow-x-auto` table wrappers, modals).
   Design rationale: work/stock-desk-視覺規範-捲軸與表格.md
   ============================================================ */

/* Firefox */
* {
  scrollbar-width: thin;
  scrollbar-color: #404040 #171717; /* thumb (neutral-700) / track (neutral-900) */
}

/* WebKit (Chrome / Edge / Safari) */
*::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

*::-webkit-scrollbar-track {
  background: #171717; /* neutral-900 */
}

*::-webkit-scrollbar-thumb {
  background-color: #404040; /* neutral-700 */
  border-radius: 9999px;
}

*::-webkit-scrollbar-thumb:hover {
  background-color: #525252; /* neutral-600 */
}

*::-webkit-scrollbar-thumb:active {
  background-color: #737373; /* neutral-500 */
}

*::-webkit-scrollbar-corner {
  background: transparent;
}
```

放置位置：`globals.css` 的 `@import "tailwindcss";` 之後、`:root` 區塊之前或之後皆可（純附加規則，不影響現有 `--background` / `--foreground` 變數）。

適用範圍：因為用了通用選擇器 `*`，這組規則**一次覆蓋全站**所有捲軸容器 —— 持倉表格的 `overflow-x-auto`、`AlertRulesSection`/`DataSourcesSection`/`BacktestReportView`/`ImportCsvSection`/`LeverageChapterView`/`TechnicalIndicatorsPanel` 的表格捲動、`EditPositionModal`/`EditAlertRuleModal` 的 modal 捲動、以及頁面本身的垂直捲軸，不需要在個別元件補 class。

選配（不強制，需要再加）：若要避免捲軸出現/消失造成版面輕微跳動，可在 `html` 加 `scrollbar-gutter: stable;`，本次任務未要求，先不列入必改項目。

---

## 2. 持倉表格區配色一致性檢視

結論：**持倉表格（`PositionsTable.tsx`）的配色與全站慣例一致，沒有發現突兀色差**。以下逐項列出檢視結果，含 1 個可選（非強制）的一致性微調建議。

| 項目 | 現況（`PositionsTable.tsx`） | 與站內其他表格比對 | 判定 |
|---|---|---|---|
| 表頭 | `bg-neutral-900 text-neutral-400`（:118） | 5 個表格全部相同 | 一致，不動 |
| 列分隔 | `border-t border-neutral-800`（:129） | 5 個表格全部相同 | 一致，不動 |
| 外框 | `border border-neutral-800`（:115） | 5 個表格全部相同 | 一致，不動 |
| 斑馬紋 | 無 | 全站 5 個表格皆無斑馬紋 | 一致（現況即慣例，非缺陷） |
| 列 hover 態 | 無 | 全站 5 個表格皆無 hover 態 | 一致（現況即慣例，非缺陷） |
| 外框圓角 | `rounded-lg`（:115） | `AlertRulesSection`/`DataSourcesSection`/`BacktestReportView` 用 `rounded-md`；只有 `PositionsTable` 與 `ImportCsvSection` 用 `rounded-lg` | **輕微不一致，可選修正** |
| 損益顏色 | `pnlColorClass`：漲用 `text-rose-400`、跌用 `text-emerald-400`（台股慣例：紅漲綠跌） | 與 `BacktestReportView`、`RiskGauge` 等處的紅綠慣例一致 | 一致，不動 |
| 資料狀態徽章 | `DataStatusBadge`：`bg-neutral-800 text-neutral-400`（一般）／`bg-amber-900/40 text-amber-300`（備援源警示） | 與其他警示徽章（`bg-rose-950/50 text-rose-300 border-rose-800` 等）走同一套「半透明底 + 邊框 + 淺色字」語彙 | 一致，不動 |
| 風控文字色階 `neutral-400` | 表頭與次要文字使用，對黑底 7.66:1 | 紅線範圍，不得動 | 不動（依紅線） |

### 可選修正建議（僅建議，frontend-engineer 可自行判斷是否採用）

1. **外框圓角統一**：`PositionsTable.tsx:115` 與 `ImportCsvSection.tsx:74` 目前用 `rounded-lg`，其餘 3 個表格容器用 `rounded-md`。若要收斂成單一標準，建議以出現次數較多的 `rounded-md` 為準，把這兩處的 `rounded-lg` 改成 `rounded-md`。**非必要**，目前差異在視覺上極輕微，不影響任何可讀性或對比，純粹是規格潔癖層級的建議。
2. 若日後想幫長列表加互動回饋（例如滑鼠掃過該列時提示目前對到哪一列的資料），可加：
   ```
   className="border-t border-neutral-800 transition-colors hover:bg-neutral-900/60"
   ```
   `hover:bg-neutral-900/60` 沿用既有 `neutral-900` 色階、加透明度避免過重，與捲軸 track 用色同一邏輯（看得到但不搶戲）。**這是全站性決策**（要嘛 5 個表格一起加，不要只加持倉表格），本次任務未要求，先不列入必改項目，僅記錄供未來需要時使用。

---

## 3. 驗收清單（frontend-engineer 實作後自查 / qa-e2e 抽查用）

- [ ] `globals.css` 已加入第 1.2 節完整 CSS 區塊，且未動到既有 `:root` / `body` 規則。
- [ ] Chrome/Edge（Windows）下，持倉表格與任一 modal 的捲軸皆呈現深灰細條（非系統預設亮色），寬度約 8px。
- [ ] Firefox 下捲軸同樣呈現深色細條（`scrollbar-width: thin` + `scrollbar-color` 生效）。
- [ ] 滑鼠移到捲軸 thumb 上時顏色變亮（hover 態），拖曳時更亮（active 態）。
- [ ] 全站其他捲動容器（表格、modal、頁面本身）捲軸樣式一致，沒有漏改的地方。
- [ ] 未變動 `text-neutral-400`（風控文字色階）與 `pnlColorClass` 的紅漲綠跌邏輯。
- [ ] （若採用可選建議 1）`PositionsTable` 與 `ImportCsvSection` 外框圓角改為 `rounded-md` 後，與其餘表格視覺一致。

---

## 4. 交接

- 規範 → 交 `frontend-engineer` 依第 1.2 節 CSS 原樣貼入 `apps/stock-desk/frontend/app/globals.css`；第 2 節可選建議自行判斷是否採用。
- 實作完成 → 交 `qa-e2e` 依第 3 節清單做 Windows/Chrome 與 Firefox 實機抽查。
- 定稿 → 交 CEO 驗收。

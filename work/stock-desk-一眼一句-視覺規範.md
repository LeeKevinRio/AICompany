# stock-desk 「一眼一句」視覺規範

- 任務來源：`work/stock-desk-一眼一句簡化-派工單.md`（CEO 2026-09-19 原話、dev-lead 診斷 §1、設計方向 §2）。
- 作者：art-lead
- 日期：2026-09-19
- 分支：`product/stock-desk`
- 盤點基準（已用 Read 逐檔盤點，非肉眼猜色值）：
  `apps/stock-desk/frontend/app/position/[symbol]/page.tsx`、`OperationSummaryPanel.tsx`、
  `KeyLevelsPanel.tsx`、`PriceLadder.tsx`、`EntryObservationPanel.tsx`、
  `TechnicalIndicatorsPanel.tsx`、`AdviceCardView.tsx`、
  `apps/stock-desk/frontend/app/page.tsx`、`components/RiskGauge.tsx`、
  `components/PendingAlertsPanel.tsx`、`components/SummaryCards.tsx`、
  `apps/stock-desk/frontend/app/lib/format.ts`（`limitStatusColorClass`）、
  `apps/stock-desk/frontend/app/lib/queries.ts`（`useAlerts`/`useAlertEvents`）、
  `work/stock-desk-視覺規範-捲軸與表格.md`、`work/stock-desk-快市排程-視覺規範.md`（沿用其 token 與色彩紀律）。
- 性質：**視覺規範，不是文案定稿**。凡本文標示「新句」的位置，字面待 creative-lead 起草、
  risk-compliance-officer 覆核（一字不動原則不變）；art-lead 不預先燒進字面，只定位置、字級、字數上限。

---

## A. 觀察報告（art-lead）

**我們為什麼沒早發現**：美術端過去三份規範（捲軸／表格、快市排程四態、圖形化審查）都聚焦在
「單一元件配色與一致性」，從未從「整頁預設視圖的字數總量」角度稽核過。個股頁六個區塊各自遵守
既有風控規範（免責常駐、限定句不摺疊）逐批疊加，卻沒有人定義「一頁最多能有幾個必讀元素」，
美術端也沒建立字數上限這道關卡，等於默許內容持續往上堆。

**我現在看到的問題**：每個區塊都「個別合規」但沒有「整體節制」——操作摘要八要素同進同退、
關鍵價位十條計算依據常駐、風險儀表五條×四行＋12 行資料源，各自局部正確，加總就是「又臭又長」。
且多處新句（一句結論）目前根本不存在，只有導讀句（tagline），這正是 CEO 要的「重點」從未被
產生過的原因。

**我這次要做什麼**：訂出跨區塊統一的「一眼一句」視覺模板（標題列→主視覺／主數字→一句結論→
詳細），逐區指定預設視圖／收合／頁尾三分法的明確清單與 Tailwind class，並誠實標出哪些是全新
文案（需 creative-lead＋風控）、哪些字級調整需要風控正式核准（不擅自繞過既有免責字級規範）。

---

## B. 「一眼一句」視覺規範

### B.1 區塊模板（給 frontend-engineer 直接落地）

適用於 B.2 的技術分析、關鍵價位、六項觀察、建議卡四個區塊（操作摘要為合規強化變體，見 B.2③）。

```tsx
<section className="rounded-lg border border-neutral-800 p-4">
  {/* 標題列：h2 + 右側資料截至徽章 */}
  <div className="flex flex-wrap items-center justify-between gap-2">
    <h2 className="text-lg font-semibold text-neutral-100">{TITLE}</h2>
    <span className="flex flex-wrap items-center gap-1 text-xs text-neutral-500">
      資料時間：{asOf}｜來源：{source}
      <DataMetaStatusBadge status={...} stalenessMinutes={...} isWithinTtl={...} lastBarDate={...} reason={...} />
    </span>
  </div>

  {/* 主視覺或主數字：擇一，圖表用 <div className="mt-3">，數字用下列 */}
  <p className="mt-3 text-3xl font-bold text-neutral-100">{mainValue}</p>

  {/* 一句白話結論：≤ 40 字，不可用紅綠語意色 */}
  <p className="mt-2 text-sm text-neutral-200">{oneLiner}</p>

  {/* 詳細展開 */}
  <details className="group mt-3">
    <summary className="flex cursor-pointer list-none items-center gap-1.5 text-sm text-neutral-400 hover:text-neutral-300 [&::-webkit-details-marker]:hidden">
      <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">
        ▸
      </span>
      詳細
    </summary>
    <div className="mt-3 space-y-3 border-t border-neutral-800 pt-3 text-xs text-neutral-400">
      {detailContent}
    </div>
  </details>
</section>
```

要點：
- `summary` 用 `list-none` ＋ `[&::-webkit-details-marker]:hidden` 隱藏瀏覽器預設三角形，改用文字
  glyph `▸`／`group-open:rotate-90` 做 chevron；這是純 UI 開合圖示，不是方向/語意判斷，不受
  「圖形化審查禁用箭頭」規則約束（該規則只限指標色帶／規則方向 chip）。
- `summary` 與展開內容一律 `text-neutral-400` 起跳，符合「必讀文字 ≥ neutral-400」以外的
  「輔助/次要文字可用既有 neutral-400/500 慣例」原則（見 B.6）。
- 「一句白話結論」若該區塊目前沒有對應文字（技術分析、關鍵價位皆無），標記為**新句**，
  位置與字級先保留，字面待 creative-lead＋風控。

---

### B.2 個股頁六區塊

新順序依派工單 §2.1：① 標題列 → ② 技術分析 → ③ 操作摘要 → ④ 關鍵價位參考 → ⑤ 六項觀察條件 →
⑥ 建議卡 → 頁尾揭露區（不動）。

#### ① 標題列（`page.tsx:217-235`）

- 主視覺：無（結構性資訊列）。
- 留：代號＋名稱（`h1`）、市場徽章、「回總覽」連結。
- **新增**：CEO 要求「標題列右側資料截至徽章」——建議合併 bars／signals／advice 三個查詢的
  `as_of`，取「是否同步」判斷（可直接複用 `EntryObservationPanel.tsx` 既有的
  `buildDataTimesLine`／`synchronized` 邏輯搬到共用位置，不重複造輪），呈現一顆
  `DataMetaStatusBadge` 等級的小徽章：同步顯示單一時間，不同步顯示「資料時間不同步，詳見下方各區塊」。
- 收合／頁尾：無。

#### ② 技術分析（`page.tsx:300-439` + `TechnicalIndicatorsPanel.tsx`）

- 主視覺：K 線＋均線圖（`PriceChart`）。
- 留（預設視圖）：
  - h2「技術分析」＋ K 線徽章（`DataMetaStatusBadge`，bars 查詢）。
  - K 線圖本體。
  - 指標速覽 chips 一列（`IndicatorOverview` 的 `<ul>` chips 本身，不含外框標題／legend）。
  - 一句白話結論 `{TECH_ONE_LINER}`（**新句**：例如「近 N 日呈上升／盤整，收盤在 MA20 上方」，
    需 creative-lead 依 `collectOverviewChips`／均線相對位置產生固定句型，逐字待風控）。
  - 「詳細」。
- 收合（詳細內）：
  - `IndicatorOverview` 標題＋legend 框（`INDICATOR_OVERVIEW_TITLE`／說明句，若未下沉頁尾者）。
  - 七張技術指標卡：MA／RSI／KD／MACD／Bollinger／ATR／成交量 Z 分數。
  - 三張風險量測卡：年化波動度／最大回撤／Beta。
  - signals 徽章（技術指標自己的 `DataMetaStatusBadge`，因與 K 線是不同查詢，provenance 不可共用）。
  - 「共 X 根日線（起訖日）」樣本句。
- 頁尾（既有不動）：`buildTechnicalFooterItems`（`INDICATOR_OVERVIEW_LEGEND`）。

#### ③ 操作摘要（結論卡）（`OperationSummaryPanel.tsx`）—— 模板強化變體

派工單明訂此區塊為合規強化版，預設視圖比通用模板多留 3 個必讀元素，不套用純 4 槽模板：

- 主視覺/主數字：結論大字（`headingLabel`／`attributedHeadline`）。
- 留（同一視覺區塊內，由上到下）：
  1. h2「操作摘要」＋資料徽章。
  2. 結論大字＋信心等級 chip 同一行（維持現行 `text-2xl font-bold` ＋ `信心等級：{label}`）。
  3. 股數區間一行（`quantityRangeText` 單行文字，不含 `basisNote`/`absenceReason` 細節）。
  4. 一句主要依據（held 分支沿用現有 `topMatchedRule` 句；candidate 分支需將
     `compositionText`＋`supportiveDisclaimer` 精簡為一句，**待 creative-lead 改寫**）。
  5. 一句免責（`disclaimer`）縮為同列小字 `text-xs text-neutral-500`，不再用
     `DisclaimerBanner` 橫幅樣式。
     **⚠️ 風控核准前不可實作**：現行規範明文「免責聲明不得小於本文字級、不得摺疊」
     （`OperationSummaryPanel.tsx:200` 附近註解），本項是字級下修，必須先送
     risk-compliance-officer 依派工單 §2.3 正式核准，核准前維持現行 `DisclaimerBanner`。
  6. 「詳細」。
- 收合（詳細內）：信心定義句、反面論點、失效條件、`basisNote`。
  - 若 `restoresComplianceWarning` 或 `staleDataNotice` 存在（非 null），**不收進詳細**，
    維持常駐（見 B.4／B.6 的最低常駐句原則，兩者屬「資料不足／過舊」與「合規警示」類）。
- 頁尾（既有不動）：`buildFooterGuidance`、`buildSummaryFooterItems`。

#### ④ 關鍵價位參考（`KeyLevelsPanel.tsx` + `PriceLadder.tsx`）

- 主視覺：價位階梯（`PriceLadder`，九個 rung 由高到低排列＋相對基準價距離條，本身已是全部關鍵
  價位的總覽圖）。
- 留：
  - h2＋收盤列（`buildKeyLevelsCloseLine`）。
  - `PriceLadder` 圖形本體。
  - 停損建議大字（`stopSuggested`）＋停利建議大字（`target2R`），各自標籤「停損參考」／
    「停利參考」，維持 `font-mono text-xl font-bold text-neutral-100`（無紅綠色）。
  - 一句白話結論 `{KEYLEVELS_ONE_LINER}`（**新句**：例如「收盤在停損與停利之間，距停損 X%」，
    待 creative-lead＋風控）。
  - 「詳細」。
- 收合（詳細內）：
  - 位階卡（`RangeGauge`：區間位階 %、MA60 乖離）——與階梯圖資訊重疊，收合不遺失資訊。
  - 三張小卡完整內文：拉回觀察卡（MA20／MA60／近 60 日低點 rows＋說明句）、
    停損參考卡（基準句＋ATR 條件句）、停利參考卡（anchor cross ref＋2R／固定／移動停利 rows＋
    trailing note）。
  - 面板內殘留限定句（`KEY_LEVELS_HEADER_UNADJUSTED_NOTICE`）。
- 頁尾（既有不動）：`buildKeyLevelsFooterItems` 全部十條計算依據＋樣本句＋各限定句。

#### ⑤ 六項觀察條件（`EntryObservationPanel.tsx`）

- 主視覺：六個圓點列（既有 `aria-hidden` glyph `<ul>`，維持原樣）。
- 留：
  - h2＋`buildConditionCount` 句（「6 條中成立 N 條」，右上角，`text-base font-semibold`）。
  - 六個圓點列。
  - 一句白話結論：**沿用既有 `buildConditionCount` 文字本身**（已存在、≤20 字，不需新文案）。
  - 「詳細」。
- 收合（詳細內）：
  - 六列明細清單（`conditionLabel`／threshold／`observedText`／狀態文字的完整 `<ul>`）。
  - E-1～E-4 限定句（`ENTRY_E1_QUALIFIER`／`ENTRY_E2_XREF`／`ENTRY_E3_DASH_NOTE`／
    `buildDataTimesLine`）。
- 頁尾：`buildFooterGuidance` 指引句維持原位（本身是導向頁尾/詳細的短句，非八要素內容，
  不算「需收合的詳細內容」）。

#### ⑥ 建議卡（規則明細）（`AdviceCardView.tsx`）—— 整卡預設收合

派工單明訂「預設收合，標題列顯示命中 N 條／方向占比條」，故本區塊的 `<details>` 包住整張卡，
`summary` 本身即扮演「主視覺＋主數字」：

```tsx
<details className="group rounded-lg border border-neutral-800">
  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4 [&::-webkit-details-marker]:hidden">
    <span className="flex items-center gap-2">
      <span aria-hidden="true" className="inline-block text-xs transition-transform duration-150 group-open:rotate-90">▸</span>
      <h2 className="text-lg font-semibold text-neutral-100">{ADVICE_CARD_TITLE}</h2>
      <span className="text-sm text-neutral-400">命中 {advice.matched_rules.length} 條</span>
    </span>
    {/* 方向占比條縮小版，寬度固定 8rem，無 legend，僅圖形＋aria-label */}
    <div className="w-32 shrink-0">{miniDirectionBar}</div>
  </summary>
  <div className="space-y-3 border-t border-neutral-800 p-5">{existingAdviceCardBody}</div>
</details>
```

- 留（摺疊前）：命中規則數＋方向占比條縮小版（沿用 `DirectionWeightBar` 的色彙與 100% stacked
  bar 邏輯，僅移除 legend 文字，寬度固定 `w-32`）。
- 一句白話結論：**沿用/組合既有文字**——若 `direction_weights` 非空，取最高權重方向的
  `ruleDirectionLabel`，組成「以{方向}為主」（新組合句，字面待風控）；若為空則不顯示。
- 收合（詳細＝展開後全部內容，不變）：交叉引用句、規則版本/資料時間/觀察區間 meta、
  `blocked_notices`／`downgrade_notices`、命中規則清單、方向清單＋qualifier、風險上限檢查、
  資料完整度＋`skipped_rules`（維持原有巢狀 `<details>`）。
- 頁尾（既有不動）：`buildAdviceFooterItems`（`DIRECTION_SHARE_QUALIFIER`）。

---

### B.3 首頁風險儀表「五列一行式」（`RiskGauge.tsx`）

容器：`rounded-lg border border-neutral-800 p-5`（不變）。

標題列：`h2`「風險儀表」＋右側「判定產生時間：{as_of}」（`text-xs text-neutral-500`，
從原本獨立一行搬到與 h2 同排，沿用模板精神）。

每條上限一列，Grid 版式：

```tsx
<li className="grid grid-cols-[minmax(0,1fr)_4.5rem_6rem_7rem] items-center gap-3 border-t border-neutral-800 py-2 text-sm first:border-t-0">
  <span className="truncate text-neutral-200">第 {check.index} 條・{check.name}</span>
  <span className={`inline-flex items-center justify-center rounded-md border px-2 py-0.5 text-xs font-semibold ${chipClass(check.status)}`}>
    {limitStatusLabel(check.status)}
  </span>
  <div className="h-1 w-full overflow-hidden rounded-full bg-neutral-800">
    {view.showBar && <div className={`h-full rounded-full ${fillColorClass}`} style={{ width: `${view.barWidthPercent}%` }} />}
  </div>
  <span className="text-right font-mono text-xs text-neutral-400">
    {formatPercent(check.observed)}／{formatPercent(check.threshold)}
  </span>
</li>
```

- 欄位順序：名稱（含編號）｜狀態 chip｜細進度條｜觀察值／上限。
- 寬度：名稱 `minmax(0,1fr)` 吃滿剩餘空間（`truncate` 防止過長換行破壞單行）；狀態 chip 固定
  `4.5rem`；進度條固定 `6rem`；觀察值/上限固定 `7rem`（`text-right` 對齊）。窄螢幕若擠壓，允許
  grid 欄寬等比縮小，不強制換行（避免五列一行式在手機上被迫變回多行）。
- 狀態 chip 色：**沿用 `limitStatusColorClass`**，配色升級為「半透明底＋邊框＋淺色字」配方
  （與 `DataStatusBadge`／捲軸規範文件既有語彙一致，而非目前的純文字色）：
  - `passed`：`border-emerald-800 bg-emerald-950/40 text-emerald-300`
  - `violated`：`border-rose-800 bg-rose-950/40 text-rose-300`
  - `not_evaluable`：`border-amber-800 bg-amber-950/40 text-amber-300`
  - **說明**：此為既有「通過／違反／無法評估」事實判定色，非個股頁的「建議/結論」語意色，
    不受本規範 B.6「結論大字不用紅綠」限制（風控 S1 原意是不對可反駁的建議大字上色，本表是
    對照固定上限的事實判定，站內既有慣例，本次不改變其色彙邏輯，只改配方）。
- 進度條高度：`h-1`（4px，比原本 `h-1.5` 更細，呼應「細進度條」用詞與整體瘦身）；
  `not_evaluable` 依 `shouldShowLimitBar` 既有邏輯不畫條（含空條），此邏輯不變。
- 「詳細」（整個風險儀表共用一個 `<details>`，5 列列完之後）內容：
  - 每條上限的 `detail` 完整句＋`worst_symbol`（「觀測值最高：{symbol}」）＋`excluded` 清單
    （若有），逐條列出，格式沿用現行 `ExcludedList`。
  - 「風險預算輸入的假設與限制（N）」清單（`limits.data.notes`）。
  - 「各標的資料來源（N）」清單（原 `SourcesSection`，併入外層 details，不再巢狀
    `<details>`；若任一非 fresh，這份清單本身仍常駐展開在「詳細」內——即使外層摺疊，這點不變
    既有揭露義務，只是使用者要先點開外層「詳細」才看得到，這是本次簡化唯一犧牲的即時可見性，
    需 risk-compliance-officer 確認可接受）。

---

### B.4 警示狀態列三種空狀態（取代 `PendingAlertsPanel.tsx` 與 `RiskGauge` 並排的版位）

版面順序（依派工單 §2.2）：摘要卡 → 持倉表 → 風險儀表（全寬、五列）→ 警示狀態列（全寬、單行為主）。

**狀態 A：沒規則**（`useAlerts` 回傳 `items.length === 0`）

```tsx
<div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3">
  <p className="text-sm text-neutral-300">尚未設定警示規則</p>
  <Link href="/settings" className="text-xs text-sky-400 underline hover:text-sky-300">去設定</Link>
</div>
```

**狀態 B：有規則、沒觸發**（`items.length > 0` 且 `events.data.items.length === 0`）

```tsx
<div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-4 py-3">
  <p className="text-sm text-neutral-300">
    <span className="font-medium text-neutral-100">{enabledCount} 條規則啟用中</span>，目前沒有待處理警示
  </p>
  <span className="text-xs text-neutral-500">{evaluatedAtLabel}</span>
</div>
```

- `enabledCount` = `alerts.data.items.filter(r => r.enabled).length`（`useAlerts` 既有查詢）。
- `evaluatedAtLabel`：**待確認資料來源**——目前程式沒有專門的「排程最近評估時間」欄位，
  最接近的是 `AlertEventListResponse.as_of`（`events` 查詢的回應時間，非排程實際評估時間）。
  在 dev-lead／data-engineer 確認是否有更準確欄位前，暫以此值呈現，且**文案必須誠實標示為
  「查詢時間：{time}」而非「最近評估：{time}」**，避免暗示系統剛評估過；待確認到正確欄位後
  再改字。

**狀態 C：有事件**（`events.data.items.length > 0`）—— 展開為清單，非 `<details>` 摺疊：

```tsx
<div className="rounded-lg border border-amber-800/60 bg-amber-950/10 p-4">
  <div className="flex flex-wrap items-center justify-between gap-2">
    <p className="text-sm font-medium text-amber-300">{count} 條待處理警示</p>
    <Link href="/settings" className="text-xs text-sky-400 underline hover:text-sky-300">管理警示規則</Link>
  </div>
  <ul className="mt-3 space-y-2">{/* 現行 amber card list item 樣式不變 */}</ul>
</div>
```

三態差異：A／B 用中性容器（`border-neutral-800 bg-neutral-950/40`，非警示），只有 C（真的有事件）
才用 `amber` 警示色——這正是解決 CEO「旁邊待處理警示長期為空、看起來很怪」的根因：現行版本
不分狀態，永遠用同一個 `p-5` 大卡＋灰底空白句，A/B 兩態改成單行狀態列後，版面不再顯得「壞掉」。

---

### B.5 字數與行數硬指標（預設視圖，不含「詳細」內容；標點與數字皆計入字數）

| 區塊 | 上限 | 說明 |
|---|---|---|
| 標題列 | 不限 | 結構性資訊（代號/名稱/徽章），非敘述文字 |
| 技術分析 | ≤ 80 字 | 一句結論 + 指標速覽 chip 標籤總和 |
| 操作摘要（結論卡） | ≤ 120 字 | 結論 + 信心等級 + 股數一行 + 一句依據 + 一句免責，五元素合計 |
| 關鍵價位參考 | ≤ 80 字 | 收盤列 + 停損/停利標籤 + 一句結論 |
| 六項觀察條件 | ≤ 80 字 | 條件計數句（六個圓點為圖形，不計字數） |
| 建議卡（摺疊 summary 列） | ≤ 80 字 | 標題 + 命中數句（方向占比條為圖形，不計字數） |
| 首頁風險儀表（含標題列與 5 條列） | ≤ 10 行 | h2+徽章 1 行、5 條各 1 行、「詳細」summary 1 行，共 7 行，留 3 行餘裕 |
| 警示狀態列 | ≤ 2 行 | 單行文字 + 右側連結/時間；狀態 C 的清單本身不受此限（清單是使用者主動要看的內容） |

---

### B.6 不可做的事

1. **不得用紅綠語意色於結論大字**（沿用風控 S1）：操作摘要結論、關鍵價位停損/停利大字、
   技術分析與其他區塊的「一句白話結論」一律 `text-neutral-100`／`text-neutral-200`／既有
   `sky` 語意色（候選模式），不得用 `rose`/`emerald`。RiskGauge 狀態 chip 的 `emerald`/`rose`
   屬於既有「通過/違反」事實判定色，非本條限制對象（見 B.3 說明），但也不可再擴大用到其他
   結論式大字上。
2. **圖不取代字**：任何圖形（`RangeGauge`、`PriceLadder`、`DirectionWeightBar`、六個圓點列、
   風險儀表細進度條）在「詳細」收合中仍必須有等義文字（既有 `aria-label` 或旁側文字），
   不得只靠顏色/長度傳達資訊；收合不等於資訊只留在圖形裡。
3. **對比 ≥ neutral-400**：本規範新增或改版的「一句白話結論」、狀態 chip 文字、五列一行式的
   名稱/狀態/數值欄，一律 `text-neutral-400` 以上（對黑底 ≥ 7.66:1，換算基準沿用
   `work/stock-desk-視覺規範-捲軸與表格.md`）。既有 `text-neutral-500` 僅限「詳細」內的次要
   metadata（資料時間、來源、規則版本號等），不在此次上修範圍內，維持既有站內慣例。
4. 不得新增色階或引入新色相；本規範全部沿用站內既有 neutral / emerald / rose / amber / sky。
5. 不得移除既有頁尾揭露區內容或任何風控鎖定字面——本規範只改「出現層級」（留／收合／頁尾三分），
   字面（含標點）一字不動；新句一律標記為**新句**待走 creative-lead＋風控流程，不可先斬後奏。
6. **不可繞過風控直接調整免責字級**：B.2③ 操作摘要免責句字級下修需 risk-compliance-officer
   正式核准（見該節警語），核准前 frontend-engineer 維持現行 `DisclaimerBanner` 樣式。

---

### B.7 決策卡（個股頁頂部，`page.tsx` 技術分析之上）

任務來源：派工單 §5.4（dev-lead 草案，2026-09-19）＋ CEO 第三次裁定 §5.1／§5.3。
本卡是整頁**第一張卡**，放在標題列與技術分析之間；全部數字沿用既有計算
（`computeKeyLevels()`／`buildOperationSummary()`／`adviceWording.ts`），
**不新增任何模型或算式**，只重排既有結果的呈現位置。本卡**不設「詳細」**——
下方各區塊本身就是它的展開版，因此不套用 B.1 的 `<details>` 收合結構。

盤點基準（同 B.1 沿用清單另加）：`OperationSummaryPanel.tsx`（三種動作大字方框樣式、
`RULE_SOURCE_CHIP`／`NOT_HELD_BADGE`、`DataMetaStatusBadge` compact 用法）、
`KeyLevelsPanel.tsx`（`LevelRow`、停損/停利大字 `font-mono text-xl font-bold` 並排）、
`InsufficientPanel.tsx`／`ErrorPanel.tsx`（既有缺席態元件，本節不改其內部樣式，只補外層
wrapper 高度）。

#### B.7.1 版面

容器沿用 B.1：`rounded-lg border border-neutral-800 p-4`（不需要 `p-5`，本卡內容量少，
維持與其餘區塊相同 padding，不因為是第一張卡就加大）。

桌機（`sm:` 以上，一列：主字左、四個數字右）：

```tsx
<section className="rounded-lg border border-neutral-800 p-4">
  {/* 徽章列：資料截至徽章＋狀態 chip，樣式與 OperationSummaryPanel 徽章列（page.tsx 同款）一致 */}
  <div className="flex flex-wrap items-center justify-between gap-2">
    <span className="flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
      <span className="rounded border border-neutral-700 px-1.5 py-0.5 text-neutral-400">
        資料截至 {mmdd}
      </span>
      <DataMetaStatusBadge status={...} stalenessMinutes={...} isWithinTtl={...} lastBarDate={...} reason={...} compact />
      {notHeld && (
        <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-neutral-400">
          {NOT_HELD_BADGE}
        </span>
      )}
    </span>
  </div>

  {/* 主字（左）＋ 四個數字（右） */}
  <div className="mt-3 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
    {/* 主字位：動作大字＋依規則 chip，或缺席態元件（見 B.7.5） */}
    <div className="flex min-h-[3.5rem] flex-wrap items-center gap-3">
      <span className="inline-block rounded-md border border-neutral-700 bg-neutral-900 px-4 py-2 text-2xl font-bold text-neutral-100">
        {actionLabel}
      </span>
      <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-xs text-neutral-400">
        {RULE_SOURCE_CHIP}
      </span>
    </div>

    {/* 四個數字：收盤／停損參考／停利參考／股數，2×2（手機）→ 一列四欄（桌機） */}
    <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4 sm:gap-x-6">
      <NumberCell label="收盤" value={closeText} />
      <NumberCell label="停損參考" value={stopText} distance={distanceToStopText} />
      <NumberCell label="停利參考" value={targetText} distance={distanceToTargetText} />
      <NumberCell label="股數" value={quantityText} />
    </div>
  </div>
</section>
```

手機（375px，即未加 `sm:` 前綴的預設值）：`flex-col` 讓主字列與數字區塊垂直堆疊、
主字本身 `flex-wrap` 佔滿卡片寬度為一列；數字區塊預設 `grid-cols-2` 即為 2×2，不需要另寫
手機專屬 override class——桌機用 `sm:grid-cols-4` 覆蓋成一列四欄。

`NumberCell`（四個數字共用）：

```tsx
function NumberCell({ label, value, distance }: { label: string; value: string; distance?: string }) {
  return (
    <div className="flex min-h-[4.5rem] flex-col items-start sm:items-end">
      <p className="text-sm text-neutral-400">{label}</p>
      <p className="mt-1 font-mono text-xl font-bold text-neutral-100">{value}</p>
      <p className="mt-0.5 text-xs text-neutral-400">{distance ?? "—"}</p>
    </div>
  );
}
```

- 手機靠左對齊（`items-start`）配合 2×2 掃讀順序（左上收盤→右上停損→左下停利→右下股數）；
  桌機靠右對齊（`sm:items-end`）貼齊卡片右緣，四欄數字視覺上排成一條右邊界。
- `distance` 一律渲染一行（無值時印「—」而非整行消失），四格 `min-h-[4.5rem]`（72px）一致，
  不論該格是否真的有距離小字，高度都相同——這是 B.7.5 防版面跳動的具體實作，不只是缺席態才用。

#### B.7.2 字級階層

| 元素 | class | 說明 |
|---|---|---|
| 動作大字 | `text-2xl font-bold`（**不用 `text-3xl`**，見 B.7.4 理由） | 沿用 `OperationSummaryPanel.tsx` 三種既有方框樣式（見 B.7.3） |
| 四個數字 | `font-mono text-xl font-bold text-neutral-100` | 與 `KeyLevelsPanel.tsx` 停損/停利大字同一 class，維持站內數字排版慣例一致 |
| 標籤（收盤／停損參考／停利參考／股數） | `text-sm text-neutral-400` | 與 `KeyLevelsPanel.tsx` `LevelRow` 標籤同 class |
| 距離小字（距現價 ±x%） | `text-xs text-neutral-400` | **這是風控下限**：依 B.6 第 3 條「本規範新增的一句白話結論／數值欄一律 `text-neutral-400` 以上」，此為主視圖新句（距離 %），不得再降到 `text-neutral-500` |
| 徽章列（資料截至徽章／狀態 chip／未持有徽章） | `text-xs` | 沿用既有徽章 class，見 B.7.1 程式碼 |

#### B.7.3 顏色

1. **停損／停利大字不上紅綠**（風控 S1，沿用 B.6 第 1 條）：`NumberCell` 一律
   `text-neutral-100`，不得依「高於/低於現價」動態切換 `rose`/`emerald`。
2. **距離 % 也不上色**：即使停損距離必為負值（`−a%`）、停利距離必為正值（`+b%`），
   符號本身已經表意，`text-neutral-400` 固定不變，不得因正負號套 `rose`/`emerald`。
3. **唯一允許的語意色**：
   - 既有徽章：`DataMetaStatusBadge` 的既有色彙（含 amber backup／stale 等級）、
     `NOT_HELD_BADGE` 沿用中性 `neutral` 徽章樣式；
   - `role="alert"` 的既有警示框：`StaleDataAlert`（amber）、`restoresComplianceWarning`
     （rose，見 §5.4「股數：`restoresComplianceWarning` 同層」）、`ErrorPanel`（red）、
     `InsufficientPanel`（amber）——這四個是**既有共用元件的既有樣式**，本節只決定
     「放不放在主字位」（見 B.7.5），不新賦予或修改其色彙。
   - 動作大字本身沿用 `OperationSummaryPanel.tsx` 既有三種方框（held：`border-neutral-700
     bg-neutral-900 text-neutral-100` 中性；candidate：`border-sky-800 bg-sky-950/40
     text-sky-300`，屬 B.6 已核准的候選模式語意色；insufficient/no_price：見 B.7.5 缺席態），
     決策卡不另創新配色，一律沿用既有三態。
4. 不得為了「這是第一張卡」而加粗邊框或提高背景對比（如 `border-2`／`border-neutral-600`）
   ——卡片框線與其他區塊一律同一個 `border-neutral-800`，差異只在版面順序，不在視覺強度。

#### B.7.4 與技術分析的間距與視覺分量

- 間距：決策卡與其下方「技術分析」區塊之間沿用站內既有區塊間距 `mt-6`（`page.tsx:254`、
  `KeyLevelsPanel.tsx:378` 既有慣例），不因為決策卡重要就加大留白，也不因為想省空間就縮小。
- 視覺分量的上限是 `h1`：`page.tsx:223` 的個股代號/名稱標題是 `text-2xl font-bold
  text-neutral-100`。決策卡動作大字**維持 `text-2xl`、不得用 `text-3xl`**——若動作大字比
  `h1` 還大，會讓使用者的第一眼落在決策卡而非頁面在講哪一檔股票，違反本節「不得比 h1 標題
  還搶」的前提。動作大字與 `h1` 同字級但視覺上仍能區分主從：動作大字外框有
  `border-neutral-700 bg-neutral-900`（或 candidate 的 `sky`）方框，`h1` 是純文字無框，
  框線本身已提供層級差異，不需要再靠字級拉開。
- 卡內部層級：動作大字 `text-2xl` ＞ 四個數字 `text-xl` ＞ 標籤/距離 `text-sm`/`text-xs`，
  與技術分析區塊自己的 `h2 text-lg` 相比，決策卡數字（`text-xl`）故意大於技術分析的 `h2`，
  但決策卡整體（含徽章列的 `text-xs`）不掛任何比 `h2`更顯眼的裝飾性色塊或動畫，維持「決策卡
  數字最搶眼、但技術分析標題仍清楚是下一個獨立區塊」的分寸。

#### B.7.5 缺席態的視覺

- **數字缺席**（bars 不足或該數字算不出來）：沿用既有 `fmt()` 慣例，直接印「—」，
  class 不變（仍是 `font-mono text-xl font-bold text-neutral-100`），不得把缺席的數字
  改小、改灰或整格拿掉——`NumberCell` 骨架（含 `min-h-[4.5rem]`）在有資料／無資料兩態下
  結構完全相同，只有文字內容從數字換成「—」，避免使用者感覺「版面壞了」。
- **主字位缺席**（`advice` 查詢失敗或 `insufficient_data`/`no_price`）：改放
  `ErrorPanel`／`InsufficientPanel` 取代動作大字＋依規則 chip 那一組。兩者本身都是單行
  `<p>`（`px-4 py-3 text-sm`），比動作大字方框（`px-4 py-2 text-2xl`）矮，若直接替換會讓
  卡片在「有動作」與「缺席」兩態間高度跳動——因此 B.7.1 已在主字位外層包一個
  `flex min-h-[3.5rem] items-center` 容器，兩種內容都放進同一個 wrapper，**不修改
  `ErrorPanel`／`InsufficientPanel` 本身的 class**，只在決策卡這一層用 wrapper 補足高度差。
- 主字位是 `ErrorPanel`/`InsufficientPanel` 時，右側四個數字仍照 B.7.1 骨架完整掛載
  （`grid-cols-2 sm:grid-cols-4` ＋四個 `min-h-[4.5rem]` 的 `NumberCell`），只是每格數值
  都印「—」——不得因為主字缺席就把整個數字區塊拿掉，否則桌機的「一列、主字左數字右」與
  手機的「主字上、2×2 下」兩種版面骨架會在同一頁面因資料狀態不同而長得不一樣，那才是真正
  的版面跳動。

#### B.7.6 版面示意（ASCII）

桌機（≥ 640px，主字左、四個數字一列四欄）：

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 資料截至 09-18 [已快取]                                                    │ ← 徽章列 text-xs
│                                                                            │
│ ┌────────────┐ [依規則]         收盤        停損參考      停利參考     股數 │ ← 標籤 text-sm
│ │  停損參考  │                 105.00       95.00        125.00  120~150股│ ← 數字 text-xl mono
│ └────────────┘                              距現價 −9.5%  距現價 +19%   —  │ ← 距離 text-xs
│  ↑ 動作大字 text-2xl                         ↑ 四個數字，靠右對齊           │
└──────────────────────────────────────────────────────────────────────────┘
```

手機（375px，主字一列、數字 2×2）：

```
┌───────────────────────────────┐
│ 資料截至 09-18 [已快取]         │ ← 徽章列
│                                 │
│ ┌────────────┐ [依規則]         │ ← 主字一列，靠左
│ │  停損參考  │                 │
│ └────────────┘                  │
│                                 │
│ 收盤              停損參考       │ ← 數字 2×2，第一列
│ 105.00            95.00         │
│ —                 距現價 −9.5%  │
│                                 │
│ 停利參考           股數          │ ← 數字 2×2，第二列
│ 125.00            120~150股     │
│ 距現價 +19%        —            │
└───────────────────────────────┘
```

#### B.7.7 待審事項（不預先燒進字面）

- 卡片標題（§5.4：候選「現在怎麼做」／「決策摘要」／不設標題只留動作大字）：本節版面示意
  採「不設標題」畫法（動作大字本身即入口），若 creative-lead／風控最終選了有標題的版本，
  標題沿用 B.1 模板的 `h2 text-lg font-semibold text-neutral-100`，插入徽章列上方，不改動
  本節其餘版面。
- 距離小字文案「距現價 ±x%」：字面待風控核准（§5.4 風控預審重點：新推導算式需補頁尾算式
  行）；本節只定位置與字級，字面（含「距現價」三字与百分比格式）不預先定案。

---

## 交接

1. 本規範 → 交 `frontend-engineer` 依 B.1–B.4 落地；B.2③ 免責字級與 B.4 「查詢時間 vs 評估時間」
   字面兩處，**需等對應審查/確認完成才可實作**，其餘可直接動工。
2. 全新文案（`{TECH_ONE_LINER}`／`{KEYLEVELS_ONE_LINER}`／操作摘要一句依據精簡句／建議卡方向組合句）
   → 交 `creative-lead` 起草 → `risk-compliance-officer` 逐字覆核定稿，art-lead 複核視覺是否因
   文案長度需要微調（非重新設計）。
3. 風控邊界（B.2③ 免責字級、B.3 資料來源清單收進「詳細」後的即時可見性犧牲、B.4 最低常駐句）
   → 交 `risk-compliance-officer` 依派工單 §2.3 裁定「最低常駐線」。
4. 「最近評估時間」欄位缺口（B.4 狀態 B）→ 交 `dev-lead`／`data-engineer` 確認是否有更準確欄位，
   無則維持「查詢時間」誠實標示。
5. 完成實作 → 交 `qa-e2e` 依 B.5 字數/行數硬指標與 B.6 不可做的事逐條實機抽查（截圖比對預設視圖
   字數、對比度、色彙）。
6. 定稿 → 交 CEO 驗收。

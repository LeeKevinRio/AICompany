# stock-desk「一眼一句」實作規格（dev-lead 收斂稿，2026-09-19）

依據：`work/stock-desk-一眼一句簡化-派工單.md`（CEO 原話）、`work/stock-desk-一眼一句-PRD.md`（FR/AC）、
`work/stock-desk-一眼一句-視覺規範.md`（art-lead）、`work/stock-desk-一眼一句-文案稿.md`（creative-lead）、
風控最低常駐線 R1–R10／H1–H5（2026-09-19，APPROVE_WITH_CONDITIONS，全文見派工單 §3.6 與本檔附錄）。
本檔是 frontend-engineer 的**唯一施工依據**；三份來源文件若有出入，以本檔為準（衝突點已由 dev-lead 裁決並註明）。

## 0. 鐵律

1. 風控鎖定字面**一字不改**（含標點）。只改「出現層級」：主視圖／`<details>` 詳細／頁尾。
2. 每個既有字面上線後仍必須在頁面某處渲染（子集合守門，PRD AC-4）；「不渲染」只允許五則 tagline（風控明示可刪）。
3. 新字面只能用本檔 §5 列出的字串（已收斂自文案稿候選）；不得自行編寫其他面向使用者的句子。
4. `<details>` 樣式統一用視覺規範 B.1 的 class 組合；summary 文字用 §5 的入口字。
5. 既有守門測試 `componentWordingScan.test.ts` 的斷言要**改成新層級語意**（例如「由 details 內渲染」），不得刪除任何字面釘住、不得刪測試檔。
6. 不得改後端。不得改 `app/lib/adviceWording.ts`、`KeyLevelsPanel.tsx` 中 exported 常數字面。

## 1. 基準（Playwright，demo 資料 2330，2026-09-19）

| 區塊 | 現況可見字數 | 目標（預設視圖） |
|---|---|---|
| 操作摘要 | 668 | ≤ 160（含風控 R3 一條反面論點；CEO 若推翻 R3 再降） |
| 六項觀察條件 | 397 | ≤ 120（含 R8 E-1 句） |
| 關鍵價位參考 | 820 | ≤ 160（含 R6 兩句、R7 未還原權值句） |
| 技術分析 | 1746 | ≤ 80 |
| 建議卡 | 1331 | ≤ 110（summary 列，含 R9 交叉引用句 70 字） |
| 首頁風險儀表 | 1484 | ≤ 10 行／≤ 260 字（含 H3 觀測值最高、H4 說明句） |
| 個股頁整頁（不含頁尾） | ~5000 | ≤ 800 |

量測腳本：`scratchpad/measure.mjs`（Playwright、`--no-proxy-server`、`http://localhost:3000`）。

## 2. 個股頁（`app/position/[symbol]/page.tsx` 與子元件）

### 2.1 順序

標題列 → 技術分析 → 操作摘要 → 關鍵價位參考 → 六項觀察條件 → 建議卡（預設收合）→ 槓桿專章（既有）→ 頁尾揭露區（不動）。
移除操作摘要下方那句 `buildFooterGuidanceForDataSource(...)`（改放進操作摘要的「詳細」最後一行）。

### 2.2 技術分析

主視圖：
- h2「技術分析」＋右側 bars 徽章列（現有 `資料時間｜來源｜DataMetaStatusBadge`）。
- `PriceChart`（K 線＋均線；bars pending → skeleton；error／insufficient 照舊）。
- 指標速覽 chips 一列（只放 `<ul>` chips；無 chips 時渲染 `INDICATOR_OVERVIEW_EMPTY`）。
- 一句結論：`TECH_ONE_LINER`＝「近 {n} 根日線，收盤 {x}。」（§5-A）。

詳細（`<details>`，summary＝「詳細：七張指標卡與風險量測」）：
- signals 徽章列、`INDICATOR_OVERVIEW_TITLE` 標題、七張指標卡、風險量測三卡、「共 X 根日線（起訖）」句、`buildFooterGuidance(TECHNICAL_ANALYSIS_TITLE)`。
- 移除：`TECHNICAL_CHART_TAGLINE`、`TECHNICAL_INDICATORS_TAGLINE`（不再渲染；常數保留）。

### 2.3 操作摘要（`OperationSummaryPanel.tsx`；風控強化變體）

主視圖（held 分支，由上而下）：
1. h2＋advice 徽章列。
2. 結論大字（`attributedHeadline`）＋同列信心 chip「信心等級：{label}」＋同列 `confidenceMeaning`（text-xs **neutral-400**，R10；不得用 neutral-500）。
3. `disclaimer` 改為 text-xs neutral-400 常駐一行，緊接大字下方（風控核可；不得 truncate／line-clamp）。移除 `DisclaimerBanner` 橫幅樣式。
4. 股數一行：只印「{min} ~ {max} 股」（把 `quantityRangeText` 拆成「股數」與「basis」兩個欄位：在 `operationSummary.ts` 新增 `quantityRangeShares: string | null` 與 `quantityRangeBasis: string | null`；`quantityRangeText` 保留給既有測試但不再直接渲染）。
   - **R4／FR-3**：`basis` 全頁只渲染一次。`restores_compliance=false` 且防禦型動作 → 以 `role="alert"` 紅框樣式渲染 basis（常駐）；否則 basis 收進詳細。`restoresComplianceWarning` 欄位保留，但渲染端不得再第二次印 basis。
5. 一句主要依據：「主要依據：{name}——{explanation}」（既有句）。
6. **R3**：第一條反面論點常駐一行（前綴「反面論點：」既有 h4 字面）。
7. `StaleDataAlert`（有才出現，常駐）。

詳細（summary＝「詳細：反面論點、失效條件與假設」）：其餘反面論點、失效條件全部、basis（非 alert 時）、`buildFooterGuidance(OPERATION_SUMMARY_TITLE)`、`buildFooterGuidanceForDataSource(PAGE_LEVEL_DISCLOSURE_SECTION_TITLE)`。

candidate 分支：主視圖＝h2＋徽章、`headingLabel` 大字＋信心 chip＋`confidenceMeaning`、`disclaimer` 小字、
`compositionText`＋`supportiveDisclaimer` 或 `notSupportiveText` 一行、股數一行、**R2** `CANDIDATE_EVIDENCE_NOTICE` 常駐一行（text-xs neutral-400；並從 `buildSummaryFooterItems` 候選分支移除這句，全頁恰好一次）、第一條反面論點、`StaleDataAlert`。
詳細：`quantityBasisNote`、其餘反面論點、失效條件、指引句。

no_price／no_action 分支：不變（`InsufficientPanel`／`StaleDataAlert`／`DisclaimerBanner` 改同樣 text-xs 行）。
移除 `OPERATION_SUMMARY_TAGLINE` 渲染。

### 2.4 關鍵價位參考（`KeyLevelsPanel.tsx`）

主視圖：
- h2＋收盤列（`buildKeyLevelsCloseLine`）。
- 一句結論：`KEYLEVELS_ONE_LINER`＝「收盤 {x}，位於近 {n} 根區間{位階}。」（§5-B；位階不可算時改印 `buildRangeInsufficientReason`／`buildRangeFlatReason`，R7）。
- `PriceLadder`（主視覺）。
- 兩個大字並排：「停損參考 {stopSuggested}」「停利參考 {target2R}」（font-mono text-xl；無紅綠）。
  - 停損大字下方 **R6** 兩句常駐 text-xs：`anchorBasisSentence(...)`、`KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE|_UNAVAILABLE`。
  - 停利大字下方：`KEY_LEVELS_TARGET_ANCHOR_CROSS_REF`（可收；本檔決定收進詳細）。
- **R7** `KEY_LEVELS_HEADER_UNADJUSTED_NOTICE` 常駐 text-xs（面板底、details 之前）。

詳細（summary＝「查看計算依據」）：位階卡（`RangeGauge`＋MA60 乖離列）、拉回觀察卡、停損卡其餘、停利卡（含三列與 trailing note、anchor cross ref）、`KEY_LEVELS_PULLBACK_EXPLAIN_NOTE`、`buildFooterGuidance(KEY_LEVELS_PANEL_TITLE)`。
移除 `KEY_LEVELS_TAGLINE` 渲染。頁尾 builder 不動。

### 2.5 六項觀察條件（`EntryObservationPanel.tsx`）

主視圖：h2＋右側 `buildConditionCount` 完整句（R8）、六圓點列、`ENTRY_E1_QUALIFIER`（text-xs，R8）、`buildDataTimesLine` **僅在 `synchronized === false` 時**常駐（R8）、`ENTRY_NO_DATA_STATEMENT`（全部無法判定時）。
詳細（summary＝「詳細：六條逐項明細」）：六列明細 `<ul>`、`ENTRY_E2_XREF`、`ENTRY_E3_DASH_NOTE`、`buildDataTimesLine`（synchronized 時）、`buildFooterGuidance(ENTRY_PANEL_TITLE)`。
移除 `ENTRY_PANEL_TAGLINE` 渲染。

### 2.6 建議卡（`page.tsx` 建議卡 section＋`AdviceCardView.tsx`）

整個 section 包在 `<details>`（預設收合）：
- summary 列：h2「建議卡」＋「命中 {N} 條」（既有 Section 標題字面拆用）＋ **R9** `ADVICE_CARD_XREF_TO_SUMMARY` 以 text-xs neutral-400 放在 summary 內第二行。不放方向占比條（避免 R9 附帶的 qualifier 同列要求）。
- 展開：既有 `AdviceCardView` 全部內容（其頂部的 XREF 句改由 summary 承載，卡內不再重複；`context_notes` 假設清單、held/candidate 說明句照舊）。
- advice pending／error／insufficient：照舊渲染在 summary 之下（details 預設展開時）；簡化：這三態不包 details，直接渲染。

### 2.7 標題列

不加新徽章（art-lead 建議的「資料截至徽章」需新字面，本批不做；技術分析區已帶 bars 徽章）。

## 3. 首頁（`app/page.tsx`、`RiskGauge.tsx`、`PendingAlertsPanel.tsx`、`queries.ts`）

### 3.1 版面

摘要卡 → 持倉表 → 風險儀表（全寬）→ 警示狀態列（全寬）。移除 `lg:grid-cols-2` 並排。

### 3.2 風險儀表五列一行式

- 標題列：h2＋右側「判定產生時間：{as_of}」（text-xs neutral-500）。
- **H4** 頂部說明句（既有 2026-08-09 核可全文）常駐 text-xs neutral-400。
- 五列，Grid `grid-cols-[minmax(0,1fr)_auto_6rem_7rem]`：
  1. 「第 {index} 條・{name}」
  2. 狀態 chip（`limitStatusLabel`，配色升級 passed/violated/not_evaluable＝emerald/rose/amber 半透明底）＋**H2**「未納入 {N} 檔」徽章同列。
  3. 細進度條 `h-1`；**H1** `shouldShowLimitBar` 不變（not_evaluable 不畫）。
  4. 「{observed}／{threshold}」font-mono text-xs。
  - **H3**：`worst_symbol !== null` 時，該列第二行 text-xs neutral-400「觀測值最高：{worst_symbol}」（沿用既有字面）。
- **H5**：採方案「主視圖保留新鮮度半句」——details 的 summary 右側附「其中 {N} 檔非即時」（既有 `SourcesSection` summary 字面，僅非 allFresh 時），details 不因非 fresh 自動展開。
- `<details>`（summary＝「詳細：各項判定依據、假設與資料來源」）內：每條 `detail`＋`ExcludedList`、「風險預算輸入的假設與限制（N）」清單、「各標的資料來源（N）」逐檔徽章清單（不再巢狀 details）。

### 3.3 警示狀態列（新元件可命名 `AlertStatusStrip`，取代 `PendingAlertsPanel` 在首頁的位置；`PendingAlertsPanel` 的事件清單樣式抽為內部子元件沿用）

資料：`useAlerts(true)`（規則清單，既有 hook）＋`useAlertEvents(true, true)`。
- 兩者 pending → 一行 skeleton。
- 規則清單為空 →「尚未設定警示規則」＋連結「去設定」（`/settings`）。
- 規則 > 0 且事件為空 →「{N} 條規則已設定，目前沒有待處理警示」＋右側「查詢時間：{events.as_of}」（N＝`enabled` 規則數；用「已設定」而非「啟用中」，避免暗示排程正在跑——風控要求「啟用中」必附最近評估時間，而系統目前沒有該欄位）。
- 事件 > 0 → amber 容器「{N} 條待處理警示」＋「管理警示規則」連結＋既有事件清單（含標記已處理按鈕）。
- 任一查詢 error → 既有紅框錯誤句。

## 4. 測試

- `componentWordingScan.test.ts`：把「常駐不得摺疊」斷言改成「該字面由對應區塊渲染（可在 details 內）」；五則 tagline 改為「常數仍存在但不再渲染」守門；頁尾 L2 不摺疊守門**維持**；建議卡 XREF 改為「在 summary 內」；`CANDIDATE_EVIDENCE_NOTICE` 改為「操作摘要渲染、頁尾 builder 不再輸出」。
- `operationSummary.test.ts`：新增「`quantityRangeShares`／`quantityRangeBasis` 拆分」與「basis 只出現一次」（用 `renderToStaticMarkup` 渲染 `SummaryBody`，斷言 `basis` 子字串 `split().length - 1 === 1`，兩種 `restores_compliance` 情境）。
- 新增 `alertStatusStrip.test.ts`：三態各一（`renderToStaticMarkup`）。
- 新增 `riskGauge` 渲染測試：五列各含 name／status／observed；`not_evaluable` 無 progressbar；`worst_symbol` 同列出現。
- 全套 `npx vitest run` 綠；`npx tsc --noEmit`（或 `npm run typecheck` 若有）綠；`npx eslint`（若有設定）綠。
- 只對自己改過的檔案跑 prettier（若 repo 有）；不得全量格式化。

## 5. 新字面（唯一允許清單；均待風控逐字審，落地時以 exported 常數集中於 `app/lib/oneLinerWording.ts`）

| 常數 | 字面 |
|---|---|
| `DETAILS_SUMMARY_GENERIC` | 詳細說明與依據 |
| `DETAILS_SUMMARY_OPERATION` | 詳細：反面論點、失效條件與假設 |
| `DETAILS_SUMMARY_KEY_LEVELS` | 查看計算依據 |
| `DETAILS_SUMMARY_ENTRY` | 詳細：六條逐項明細 |
| `DETAILS_SUMMARY_TECHNICAL` | 詳細：七張指標卡與風險量測 |
| `DETAILS_SUMMARY_RISK_GAUGE` | 詳細：各項判定依據、假設與資料來源 |
| `buildTechOneLiner(n, x)` | 近 {n} 根日線，收盤 {x}。 |
| `buildKeyLevelsOneLiner(x, n, zone)` | 收盤 {x}，位於近 {n} 根區間{zone}。 |
| `buildAdviceHitCount(n)` | 命中 {n} 條 |
| `ALERTS_NO_RULES` | 尚未設定警示規則 |
| `ALERTS_NO_RULES_LINK` | 去設定 |
| `buildAlertsRulesNoEvents(n)` | {n} 條規則已設定，目前沒有待處理警示 |
| `buildAlertsQueriedAt(t)` | 查詢時間：{t} |
| `buildAlertsPendingCount(n)` | {n} 條待處理警示 |
| `ALERTS_MANAGE_LINK` | 管理警示規則（既有字面沿用） |
| `ALERTS_SCHEDULER_DISABLED` | 排程目前未啟用，警示評估暫不會更新（風控 R-A3 第四態；creative-lead B4 狀態三候選 1） |
| `ALERTS_LOAD_ERROR_PREFIX` | 無法載入警示狀態：（風控 R-A2-4 追認） |

補記（2026-09-19 審查後）：`DETAILS_SUMMARY_ADVICE` 因建議卡 summary 改用 h2＋`buildAdviceHitCount`＋XREF 而未使用，已移除。
警示狀態列優先序：事件 >0 → C；總開關 `settings.alerts.enabled=false` → D；規則 0 → A；否則 B（N＝規則總數，非 enabled 數）。

## 6. 分工

- **frontend-engineer A（個股頁）**：§2 全部＋§4 個股頁相關測試＋`oneLinerWording.ts`。
- **frontend-engineer B（首頁）**：§3 全部＋§4 首頁相關測試；`oneLinerWording.ts` 的首頁常數由 B 新增到同一檔（A 先建檔，B 用 Edit 追加；若檔案尚不存在 B 自行建立，A 再合併）。
- 兩人都不得動對方的檔案；`componentWordingScan.test.ts` 由 A 主責，B 只改 `RiskGauge`／`PendingAlertsPanel` 相關斷言區段。

## 附錄：風控最低常駐線（摘錄）

R1 disclaimer 常駐結論旁｜R2 CANDIDATE_EVIDENCE_NOTICE 回到結論旁（全頁一次）｜R3 至少第一條反面論點｜R4 basis 一次且保留 alert 語意｜
R5 功能性狀態（Insufficient／Stale／Error／Badge）常駐｜R6 停損基準句＋ATR 條件句｜R7 未還原權值句與無資料句｜R8 條數句完整＋E-1＋不同步時的資料時間｜
R9 XREF 在 summary 可見｜R10 信心 chip 與定義句同進同退｜H1 not_evaluable 不畫條｜H2 未納入徽章同列｜H3 觀測值最高同列｜H4 頂部說明句｜H5 新鮮度訊號。

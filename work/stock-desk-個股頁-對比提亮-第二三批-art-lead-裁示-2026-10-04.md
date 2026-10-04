# 個股頁對比提亮第二、三批——art-lead 裁示（2026-10-04，coordinator 轉錄）

總則：依語意角色判斷、不依字級。資訊性文字（說明、揭露、假設、時間戳、來源、資料值、表頭、空狀態）一律 ≥ `neutral-400`。對 `#0a0a0a` 底 500 約 4.2:1 未達 AA 4.5；卡片底更低約 3.8:1；600 約 2.5:1 **不得用於任何文字**。白名單只留：大寫 `tracking-wide` 分組標題、非文字背景／分隔線、真正 disabled 控制項。

## 批次 2（說明類與時間戳容器，只改顏色、無 layout shift、靠 class 斷言不需完整視覺回歸）
- `LeverageChapterView.tsx` L195 `erosion.nature`（揭露句，最優先）、L24 details 內文、L61 `chapter.notes`、L89 `source_note`、L176 理論近似說明；L86／L105／L113／L199 `reason` 類。
- `page.tsx` L563（評估前提說明）、L576 `context_notes`（標題已 400、清單 500 層級反了）、L285（時間戳容器）。
- `AdviceCardView.tsx` L179 `weight_meaning`（600，最差）、L162 空狀態、L245 跳過規則 details 內文。
- `LimitsCheckList.tsx` L31；`DecisionCard.tsx` L362；`OperationSummaryPanel.tsx` L95；`TradingViewChartPanel.tsx` L260（可見字為 `sky-500` 連結，為統一規範改 400）；`PriceChart.tsx` L119 空狀態。

## 批次 3（標籤與控制項，會改表格與 tab 視覺層級，需前後截圖）
- `LeverageChapterView.tsx` L122–L164 八個 `th`、`PriceLadder.tsx` L81 thead、`RangeGauge.tsx` L109 區間標籤、`OperationSummaryPanel.tsx` L301「依據：」前綴、`page.tsx` L339 未選取 tab（非 disabled 不適用豁免）。
- 截圖三狀態：持倉頁 advice 展開含 `context_notes`；槓桿 ETF 章節含 drag 表與 erosion；`PriceLadder`＋tab active／inactive。

## 保留
`TechnicalIndicatorsPanel` h4「技術指標」「風險量測」500（已定案例外）；`AdviceCardView.tsx` L33、`PriceLadder.tsx` L132 背景／分隔線。

## 測試與風控
同步更新釘 class 的斷言；新增掃描：`app/position/[symbol]` 內 `text-neutral-(500|600)` 只允許白名單。`erosion.nature` 與 `context_notes` 為揭露文字、字面不變只改顏色，任務單記「僅樣式變更」通知風控備查，不需重審。UI 變更仍需 qa-e2e 實機驗收。

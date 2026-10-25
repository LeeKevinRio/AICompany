# 任務單：FD-1 flight-deals 機票低價監看器 MVP

- 狀態：build
- 發起人：CEO
- 目前負責：dev-lead
- 相關文件：`work/flight-deals-PRD.md`、`docs/adr/0002-flight-deals-技術棧與資料源.md`（proposed）

## 目標

建立單一服務「機票低價監看器」：小型網頁後台（設定監看、看價格歷史與最便宜時段）、排程定時查價、Telegram 主動推播。使用者為 CEO 本人，單一使用者、本機或自家主機執行。MVP 不含多使用者、登入、訂票、LINE。資料源由 tech-architect 另出 ADR 決定；產品前提為免費來源會壞、價格是查到當下的參考值、實際以訂票網站為準。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-A1 至 AC-E6，共對應 FR-A1 至 FR-E6）。摘要如下：

- 能建立、檢視、修改、停用、刪除監看，輸入錯誤被拒絕（AC-A1 至 A9）。
- 排程定時查價並寫入價格歷史，每監看每輪查詢次數有上限，單一失敗不影響其他，資料源失效可偵測並告警（AC-B1 至 B7）。
- 價格低於門檻、較上次下跌達比例、或創歷史新低時推播 Telegram，同價不重複，內容含必要欄位與查票連結，文案為事實陳述不含建議語氣（AC-C1 至 C9）。
- 網頁可檢視價格歷史趨勢、最便宜組合與最便宜時段，價格附查到時間與過期標示（AC-D1 至 D6）。
- 健康狀態頁、Telegram 測試發送、全域設定、使用量檢視，預設僅限本機或內網存取（AC-E1 至 E6）。

tech-architect 評估關卡需回覆：
1. 資料源選型 ADR（含條款風險、額度、欄位可得性、成本；涉及付費須升級 CEO）。
2. PRD 中標註「由架構決定」的數值與策略（查詢上限、取樣策略、掃描週期、合併筆數、舊歷史區分、幣別處理）。
3. 評估通過才可推進至 `build`；若認為某需求不可行，須退回 product-manager 並附理由。

## 交接紀錄

- 2026-10-25 product-manager → tech-architect：PRD v0.1 與驗收條件已定，請評估可行性並出資料源選型 ADR；PRD 開放問題 1 至 6 待 CEO 回覆，7 至 10 待 tech-architect 回覆。
- 2026-10-25 tech-architect → 總經理：評估「有條件採用」，ADR-0002 草案交出（技術棧 S1、資料源 fast-flights 為主、排程 P1、Telegram 通知、安全與時間金額規範、C-1～C-18 實作約束）；Amadeus 與第三方代抓否決。開放問題 7～10 已在 ADR 回答。
- 2026-10-25 總經理：ADR-0002 落檔（proposed）；PRD 開放問題 1～6 與 ADR 的 CEO 決策採「總經理暫定、CEO 可翻案」處理，裁決表見 ADR「總經理對 PRD 的收斂裁決」。本機實測 fast-flights 3.1.0 可用（附錄）。狀態 spec → build。
- 2026-10-25 總經理 → dev-lead：依 PRD AC-A1～E6 與 ADR-0002 D-1～D-6、C-1～C-18 實作 MVP 於 `apps/flight-deals/`；Travelpayouts adapter 不在本批；交 staged diff 與真實驗證輸出。

# coordinator 定案：下一步排序與 X-3c 開工（2026-10-08，CEO 可推翻）

- 觸發：CEO 2026-10-08 指示「繼續工作 下一步都做」。
- 原則：凡不需要 CEO 本人動作的下一步全部推進；只有 CEO 能做的事（書面知悉、本機執行唯讀腳本、核可 accepted ADR 閘門、ADR-0023 前提 4）整理成單一簽核清單交 CEO，不代為決定。

## 定案一：工作排序
1. **X-3c 現在開工**（原本「待 CEO 依 X-3a 腳本結果排序」）。理由：字面 (a)(b)(c) 已風控逐字核可（(b) 75 字）、RX-1～RX-12 齊備；RK-4（PR-RK4a）依風控 RK4-R12 須排在 X-3c 之後；X-3c 是讀取端撤下、無 DB 寫入，無論 X-3a 結果為 0 列或 ≥1 列都是縱深防護。
2. X-3c 合併後 → **PR-RK5a**（R5-6：X-3c 的 KX-A2 短路與 PR-RK5a 都動 `valuation.py`，後者 rebase）→ **PR-RK4a**（待 tech-architect 補 (A′)／`/limits` predicate 與 RK4-R5 組態枚舉）→ PR-RK4b（`/limits`）→ PR-RK5b／5c（W11-5 前）。
3. PR-2（A 降級句）、PR-3（6-b）、F-1b、O-1、D-13、F-6：排在上述之後；PR-1／PR-2／PR-3 的**合併上線**仍以 CEO 接受 ADR-0023 前提 4 為閘門。

## 定案二：X-3c 實作的例行決定
- **token 名**：`currency_market_mismatch`（creative-lead 草稿代稱，沿用；風控 RX-2 未指定名稱）。後端 `valuation.missing == ["currency_market_mismatch"]`，前端 `MISSING_LABELS["currency_market_mismatch"] = "幣別與市場不符"`。
- **分工**：後端（dev-lead）與前端（frontend-engineer，RX-3／KX-A6）並行，檔案不重疊；art-lead 對 RX-3 徽章樣式出意見（不得新增字面）。
- **字面**：一律逐字取自 `work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md` 第二段核可表（(b) 為 75 字版）。

## 定案三：同時進行的文件工作
- tech-writer 彙編 **R0-2 CEO 知悉包**（C-1～C-5、X-1～X-12 等，逐條注明更正與來源）〔2026-10-08 coordinator 更正：原寫「K-1～K-3」為 coordinator 筆誤，repo 內沒有這組 CEO 知悉項；tech-writer 查證後併入 X-11 與 D-1 說明〕，供 CEO 一次書面簽核。
- creative-lead 起草 **發布說明（release note）**中面向使用者的字面：PR-RK2 銜接句說明（X10-8）、KX-10 對 X-2 的更正（RX-12）→ 送風控逐字審。
- tech-architect 補 RK-4 的 (A′)／`/limits` predicate 與 RK4-R5 組態枚舉、RK5-R4／R5 併入 R5-10、查證 S-L3（`_resolve_fx` 擋不下 NaN 匯率）。

# KT-1 delta 審查（456519a..e505845，KT-R-27(1)）— qa-reviewer

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。

---

## Summary
456519a..e505845 這個範圍只動 1 個檔：`apps/stock-desk/backend/tests/test_api_kelly_disclosures.py`（+36/-7）。內容是兩件事：6fddead 把連接符守門收窄，e505845 新增 KT-R-24 列序測試。守門沒有被放寬，KT-R-23 範圍零 diff。我沒有執行任何測試，下面是讀碼判斷。

## 逐項結論

### 1. 只改測試，沒有放寬守門

**6fddead（連接符守門，`test_only_two_connector_shapes_are_used_and_neither_crosses_over`，L1141-1160）**
- 結論：與我上一輪第 8 點的建議寫法等價，而且多一道。
- 比對建議寫法：
  - 五字迴圈、`allowed = 1 if 「到」且標籤是 fr5-7 else 0`、`label.count(character) == allowed` 都與建議一致（L1151-1159）。
  - 值與 note 的 `rendered` 掃描維持五字全部為零（L1152）。
- 比 6fddead 之前更嚴：
  - 之前 fr5-7 標籤對五個字元全部豁免，現在只豁免「到」一次，其餘四字在每個標籤都必須為 0。
  - 若有人把 fr5-7 標籤的「到」換成「～」或「–」，現在會紅。
- 比我的建議多一行：L1160 的 `assert "，到回測資料最後一根仍未平倉" in ...OPEN_TRIP_AT_END_LABEL`。它把唯一那個「到」的位置也釘住。
- 上一輪的 medium non-blocking 問題已解除。
- 小註記（不構成問題）：fr5-7 列是否渲染，取決於 fixture 的 `oos_open_trip_at_end=1`（L82）。即使沒渲染，L1160 仍直接檢查常數，所以不會漏。

**e505845（KT-R-24 列序測試，L785-807）**
- 結論：有牙。
- 做法：用 `_imported(oos_end_date=None, window_end=_LAST_BAR)`，`kelly.py` L713 因此不渲染 fr5-2，L720 渲染日期列，L727 之後才是回合數。
- 三個斷言：
  - `OOS_PERIOD_LABEL not in labels`（L802）確認前提成立。
  - `labels[:3] == [策略, 最後一根日期, 完整回合數]`（L803-807）精確釘住列序。
- 會紅的情況：
  - 日期列掉到回合數之後。
  - 日期列掉到策略之前。
  - 日期列消失。
  - fr5-2 在 `oos_end_date` 為 NULL 時仍被渲染。
- 與 KT-R-24 條文「日期列佔 fr5-2 原位，緊接前一個存在的列之後、在完整回合數之前」逐字相符。
- `oos_end_date=None` 在既有測試有先例（L485 與 `test_api_kelly.py`），fixture 的 `strategy_id="breakout"` 使策略列存在。

### 2. KT-R-23 範圍零 diff 聲明
**聲明：在 `456519a..e505845` 範圍內，`kelly_wording.py`、`kelly.py`（`_sample_detail`、`_tail_notice`、`_disclosures` 組裝段）、`KellyDisclosuresPanel.tsx`、`types.ts`（`tail_notice` 相關）、`test_kelly_wording.py` 的 `REJECTED_LITERALS`／`KT1_LENGTHS`，全部零 diff。**
- 依據：`git diff --stat 456519a..e505845` 只列出 `test_api_kelly_disclosures.py` 一個檔，完整 diff 我逐行讀完。
- `REJECTED_LITERALS`、`KT1_LENGTHS` 位於 `test_kelly_wording.py`，該檔不在 diff 內。
- 此聲明只涵蓋這個範圍，不涵蓋日後 merge `origin/main` 之類的新 commit。出貨 HEAD 若不是 e505845，要重新確認。

### 3. 一般品質
- 兩處改動風格與同檔一致，測試命名與 docstring 清楚，沒有祕密或產品耦合問題。
- 程式碼與註解皆為英文，符合章程。

## 各檔問題
### `apps/stock-desk/backend/tests/test_api_kelly_disclosures.py`
- Blocking：無。
- Non-blocking：無。

## 第二意見（Codex）
無法執行。`which codex` 回傳 exit 1，此環境沒有安裝 Codex CLI，我也不能安裝。KT-R-26 的 (a) 或 (b) 仍需 coordinator 處理，我這份審查不能取代。

## 唯讀權限判準常數
未觸及。
- 檢查 1：diff 只有 `apps/stock-desk/backend/tests/test_api_kelly_disclosures.py`，沒有 `scripts/validate_agents.py`。
- 檢查 2：diff 內沒有 `READONLY_AGENTS`／`READONLY_ALLOWED_BASH`，所以沒有 shadow 定義，也沒有常數值被改。
- 沒有異動的 agent，也不涉及 ADR。

## 自我揭露
- 沒有執行任何測試，也沒有確認這兩個測試實際通過。KT-R-27(2) 的實跑與原始輸出留存仍須由實作者或 CI 處理。
- 「有牙」是讀碼推演，沒有用變異測試實證，例如改 `kelly.py` 看測試是否變紅。
- 沒有實機畫面驗證，KT-R-19 的 qa-e2e 不在本次範圍。
- 只用了 `git diff`、`git diff --stat` 與 `which codex`，沒有 pipe，其餘用 Read／Grep。

## Verdict
PASS（限 KT-R-27(1) 的 delta 審查：只改測試、沒有放寬守門、KT-R-23 範圍零 diff）。Codex 第二意見缺席、KT-R-27(2) 實跑與 KT-R-26 路徑尚未滿足，所以 KT-1 仍不得標 done。
BLOCKING_ISSUES=false

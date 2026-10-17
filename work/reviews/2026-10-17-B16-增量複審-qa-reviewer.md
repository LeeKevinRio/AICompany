# B-16 增量複審 59e0e6a..7647785（qa-reviewer）

- 審查者：qa-reviewer（唯讀）；Codex 第二意見未執行（環境不可用）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
B-16 增量 `59e0e6a..7647785` 複審：**PASS，無擋件**。diff 只有 `limits.py` 的 docstring（+4 行）與測試檔（+30 行）。我沒有發現任何程式邏輯變動，產品行為零變動。M1 和 L1 都已處理。另有 1 項 low 級小發現，不擋。

## 各部門回報（qa-reviewer）

### 重點逐項
1. **產品行為零變動：成立。** `git diff --stat` 只有兩個檔：
   - `apps/stock-desk/backend/app/advice/limits.py`：新增行全在 `project_position` 的 docstring 內，函式本體沒有動。
   - `apps/stock-desk/backend/tests/test_b16_empty_book_gross_exposure.py`：新增 import、`_EXPECTED_ACTION` 常數、兩行斷言、一個新測試。
   - docstring 的說法與程式一致：`project_position`（1661–1671 行）只更新 position、quantity、gross_exposure、sector 這幾項，不碰 `book_holding_count`。
2. **M1 斷言：合理，且改壞會紅。**
   - 預期值 `{"add": "add", "defensive": "stop_loss"}` 與測試內註解（深度回撤觸發 `stop_loss`）一致，也與上一輪實測值一致。
   - 反向思考：原本只比較 before/after 相等，兩邊同時退化成別的 action（例如都變 `hold`）仍會綠。現在直接釘住 `after["action"]`，訊號或決策邏輯一變就紅，補到了我當初要的缺口。
   - `quantity_range is None` 釘住的是「不給股數」這個結果。
3. **L1 新測試：釘住了保守方向，但有一處斷言力度偏弱（low）。**
   - 真正有力的斷言：
     - `projected.book_holding_count == 0`。
     - 試算後 `gross_exposure_twd > 0`，確認不是靠總曝險為 0 才通過。
     - `_gross(projected).status == "not_evaluable"` 且 `observed is None`。
     - `limit_status_after(..., "gross_exposure", +1000) == "not_evaluable"`。
   - 若日後有人讓 `project_position` 更新計數，試算後 cap 3 會變 `passed`（11 萬 / 900 萬），這幾條會紅，所以方向確實被釘住。
   - **[可維護性][low] 最後兩條 `suggest_quantity_range(...) is None` 偏弱。** 空帳的 `total_equity_twd` 為 0，`notional_caps` 在 1580 行就直接回 `{}`（同檔 `test_an_empty_book_sizes_nothing_either_way` 已說明）。所以這兩條即使 cap 3 退化成 `passed` 也仍然是 None，抓不到 cap 3 的回歸。測試註解寫「no quantity is ever offered on the strength of this projection」，實際守住這點的是前面的 status 斷言，不是這兩條。
   - 建議（不擋）：把註解改成「等於 0 的 equity 本來就不給數量，這兩條是輔助」，或之後補一個 equity>0 但計數為 0 的人工 context 來釘這條路徑。M1 的 `quantity_range is None` 同理，主要守的是「不給股數」本身，不是 cap 3。
4. **唯讀權限判準常數：未觸及。**
   - `--stat` 檔案清單沒有 `scripts/validate_agents.py`。
   - 在 `apps` 下 Grep `READONLY_AGENTS|READONLY_ALLOWED_BASH` 為 0 筆。
   - 我也看了 diff 全文，沒有這兩個符號的增刪，不涉及 agent 名單、常數值或 shadow 定義。

### 第二意見（Codex）
Codex 第二意見未執行（環境不可用）：`codex --version` 回 `command not found`。此限制已如實註記，本輪結論僅憑本地逐行審查。

### 驗證
- 我只讀了 diff、`limits.py` 的 `notional_caps`、`project_position`、`limit_status_after`、`suggest_quantity_range`，以及測試檔 60–260 行。
- 我沒有重跑測試。dev-lead 回報的結果（相關測試 21 passed；ruff、mypy strict 通過；全套 6602 passed、2 xfailed）採信，建議 coordinator 照回報的「下一步」獨立重跑。
- 沒有讀 `.env` 或 `*.db`。

## 下一步
1. 可合併。low 發現（最後兩條斷言的註解與力度）列為後續優化，不擋。
2. coordinator 獨立重跑 pytest、ruff、mypy。
3. 風控裁示 L2（空帳時提醒 skipped 的 reason 字面）。
4. 交 qa-e2e 實機驗收：空帳加有效淨值時，第 3 條要顯示「無法評估」和核可句，且不是綠色。
5. 本輪不涉及 UI 程式碼變更。

Verdict: PASS
BLOCKING_ISSUES=false

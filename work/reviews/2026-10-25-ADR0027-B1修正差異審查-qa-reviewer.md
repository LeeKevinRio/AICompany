# ADR-0027 B1 修正差異審查

- 審查者：qa-reviewer
- 日期：2026-10-25
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論
**PASS，BLOCKING_ISSUES=false。** 4 個檔（+43／-4）的修正都到位，B1 審查的 M1、M2 與 L 類建議都已落實，沒有新增 critical 或 high 問題。
Codex 第二意見未執行（環境不可用），依 CEO #53 合併前補跑。

## 2. 各部門回報（逐項評估）
**M1（test_forecast_boundaries.py）**
- `_band_import_violations` 的 `startswith("app")` 改成 `_top_level(node.module or "") == "app"`，與第 91、100 行判斷一致，`rest` 排除條件同步改了。
- 我確認 dev-lead 的說法成立：`"apscheduler".startswith("app")` 本來就是 False（a-p-s 不是 a-p-p），我上次建議的 apscheduler 格在舊寫法下也會通過，咬不到 bug。這是我上次建議的疏漏。
- `appdirs` 才是真正的對照組：舊寫法下它被當成 app import 排除，結果是 `[]`（漏掉）。新寫法下它進入 `rest`，被判為第三方而回報。dev-lead 的實測表與我讀 code 推導一致。
- 兩格都保留合理：apscheduler 護「第三方 import 一般會被抓」，appdirs 護「前綴誤判」，不重複。註解說明了 appdirs 為何存在。兩格有 C2_LINE 前綴，`app_imports == 1` 成立，失敗只會來自第三方 import 這一條。

**M2（test_forecast_errors.py）**
- `get_args(ThresholdViolation) == THRESHOLD_VIOLATION_ORDER` 成立：errors.py 第 42–51 行的 Literal 與第 54–63 行的 tuple 同為 8 值、同序。`get_args` 回傳 tuple，tuple 對 tuple 比較無假失敗。同時釘住值與順序。新增的 import 都有用到。

**MarketRunRegressedError.source 改關鍵字必填**
- errors.py 第 419 行預設值已移除，與 ADR-0027 D-9.2 一致。
- 該名稱只出現在 errors.py、app/ops_alert/model.py、test_forecast_errors.py 三處；model.py 依 dev-lead 交件不是呼叫點。
- 測試已同步：`_market_run()` 補 `"source": "settlement"`；`test_market_run_missing_a_required_attribute_fails` 迴圈走訪 `_market_run()` 所有 key，source 缺漏現在也驗 TypeError；舊註解已改。其他呼叫處都經 `_market_run(**overrides)`，沒有漏補。

**EXCEPTION_CLASS_PATTERN 註解**：英文、內容正確（`$` 在 re.match／re.search 下會在結尾換行前成立），沒重複格式字串，不影響「恰好 2 處」那格。

**test_ops_alert_model.py 兩格新增**
- `test_job_skipped_allows_equal_run_times`：釘住「只要求遞增順序、不要求時刻相異」，與既有反序／非 UTC 拒絕格互補，有意義。
- `test_a_z_suffix_counts_as_utc`：用 `D2_RULE_4_ROWS[6]`（該列在第 244 行 occurred_at 參數化範圍內，第 279、281 行也用它）；occurred_at 14:12:03 晚於 execution_started_at 14:10:00，順序合理；斷言值原樣保留，與 raw 字串設計一致。這兩格的有效性我只有靜態閱讀的把握，通過與否沿用 dev-lead 的 375 passed。

**問題清單**
- [可維護性][low] app/ops_alert/model.py 的 OPS_ALERT_EXCEPTION_CLASS_PATTERN 有同樣的 `$` 特性但沒補註解。dev-lead 已揭露並交 coordinator 決定；我同意併入 N-133，不擋。
- [Edge case][low] Z 後綴測試只涵蓋 occurred_at 與 execution_started_at，沒涵蓋 skipped_run_times；後者若走另一條 UTC 判斷路徑，Z 後綴行為未被釘住。可併入 N-133，不擋。
- 無 critical、high、medium 問題。

## 3. 驗證
我實際執行的 Bash 指令（逐字）：
1. `git diff -- apps/stock-desk/backend/app/forecast/errors.py apps/stock-desk/backend/tests/test_forecast_boundaries.py apps/stock-desk/backend/tests/test_forecast_errors.py apps/stock-desk/backend/tests/test_ops_alert_model.py` — 無輸出（cwd 為 backend/，相對路徑解析到錯誤位置，屬我的操作失誤，無副作用）。
2. `codex --version` — `/bin/bash: line 1: codex: command not found`（exit 127）。
3. `git diff -- /home/user/AICompany/apps/stock-desk/backend/app/forecast/errors.py /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_boundaries.py /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_errors.py /home/user/AICompany/apps/stock-desk/backend/tests/test_ops_alert_model.py` — 改用絕對路徑重跑，取得完整差異（4 檔，與 dev-lead 聲明的 +43／-4 相符）。

三條都屬 `git diff` 與 `codex --version` 兩類允許指令。其餘讀檔一律用 Read／Grep，未碰 `.env`、`*.db`。我沒有重跑測試、mypy、ruff；375 passed、mypy、ruff 通過沿用 dev-lead 交件原文與 coordinator 重跑結果。

唯讀權限判準常數：未觸及。我沒有另跑 `git diff --name-only | grep` 那兩道檢查，因為本次允許指令僅限 `git diff` 與 `codex --version`，不含管線；但我讀完的完整 diff 只有上述 4 個檔，不含 scripts/validate_agents.py，也無任何 READONLY_AGENTS 或 READONLY_ALLOWED_BASH 字樣。

## 4. 下一步
1. coordinator 可請 dev-lead 將這 4 個檔 `git add`，與已 staged 的 13 檔合併成同一個 B1 變更。
2. 合併前補跑 Codex 第二意見（CEO #53）。
3. N-133 併入兩項：model.py 格式常數註解，以及 skipped_run_times 的 Z 後綴測試。

Verdict: PASS
BLOCKING_ISSUES=false

相關檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/forecast/errors.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_boundaries.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_errors.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_ops_alert_model.py
- /home/user/AICompany/work/reviews/2026-10-25-ADR0027-B1-qa修正-dev-lead.md

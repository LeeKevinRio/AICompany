# 偵測回溯工具複審修正交件（S-6～S-9）

- 審查者：data-engineer
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

複審的 S-6～S-9 已處理完，新 commit 已 push 到同一分支，沒有 amend，也沒有 merge 進 product。
- head：`166c58ca5b0abb9f26f811a776f45d1075c53342`，接在 `51bb945` 之後。
- 後端 CI 全綠：
  - ruff check 通過。
  - ruff format --check：486 files already formatted。
  - mypy app tests：Success（477 files）。我另外對腳本跑了 `mypy --strict`，也通過。
  - `pytest --cov=app --cov-fail-under=90`：9660 passed、1 skipped、2 xfailed，覆蓋率 97.59%。
  - 那 1 個 skip 仍是 S11 的 N-177a 真實常數對齊測試，因為 store 還沒有這些常數。
- 只動 `scripts/n177_n190_backtrack_probe.py` 與 `tests/test_n177_n190_backtrack_probe.py`。

## 各部門回報

### data-engineer

各項與對應測試（`T::` 代表 `apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py::`）：

| 項目 | 做法 | 測試 |
|---|---|---|
| S-7 | 報告標頭改成「報告輸出欄位（rule_id、action、status、source）中的非預期值個數（D-9 用到的列另見理由句）：N」。 | `T::test_s1_enumerated_columns_print_only_known_values_and_the_count_is_reported`（斷言字樣已改，計數為 2） |
| S-8 | `test_d9_a_row_...` 改成嚴格斷言：`guards == ["G-a", "D-9"]`，最後一條理由代碼是 `D-9`，理由句以 `ids={id}` 結尾，沒有 `or`。`test_d9_in_flight_...` 的 `if False` 死分支已刪，直接呼叫 `_report_in`。 | `T::test_d9_a_row_with_an_unexpected_enum_value_withholds_the_trial`、`T::test_d9_in_flight_row_and_s2_status_with_unknown_values` |
| S-9 | 讀 DB 階段遇到 `ValueError`／`TypeError`，只印 `cannot read the DB (unexpected cell value, <類別名>)`，不印例外訊息。`OSError` 與 `sqlite3.Error` 維持原本印訊息。 | `T::test_s5_dirty_data_in_the_db_exits_two_without_a_traceback`（批次編號欄放入 `CELL-VALUE-7731`，斷言 stderr 不含它、含 `ValueError`、全為 ASCII） |
| S-6 | 在 `_classify_affected` 的 D-9／G-a 檢查處加註解：G-a 的規格 SQL 只取 `action IN ('buy','sell')`，所以 `action` 不屬於已知值的列不會被撈到，只能檢查 `rule_id`。程式邏輯沒改，要不要改規格由 TA 裁示。 | 無 |

另有兩點說明：
- 複審說 build 階段已經只印類別名稱，實際上之前 build 階段還印了例外訊息。例如 `KeyError` 會印出鍵名。我順手改成兩個階段都只印類別名稱，例如 `cannot build the report (KeyError)`。
- 既有測試 `T::test_s5_a_previous_json_with_missing_fields_exits_two_without_a_traceback` 斷言的是這個子字串，仍然通過。

## 驗證

- 工具測試：121 passed、1 skipped。
- 全後端：9660 passed、1 skipped、2 xfailed，覆蓋率 97.59%。
- 數字為 commit 前、同一份內容實跑的結果。

## 下一步

- 請 qa-reviewer 確認 `166c58c`。Codex 第二意見待環境可用時補跑。
- 請 TA 裁示 S-6：G-a 的規格 SQL 要不要放寬到不限 `action`。
- N-177a 合併後，請確認 S11 的 skip 測試轉為通過。
- 這個分支可以交給 coordinator 安排合入 product，我不會自己 merge。

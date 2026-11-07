# 偵測回溯工具修正交件（R-1、S-1～S-5、D-9）

- 審查者：data-engineer
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

qa-reviewer 的 R-1 與 S-1～S-5，加上風控 D-9，都已修好並 push 到同一分支，沒有 merge 進 product，也沒有 amend、rebase 或 force push。
- 新 commit：`51bb94562769912db4d11a7fd87dca9b6a6a918a`，接在 `cd7fd91` 之後。
- 後端 CI 全綠：ruff check、ruff format --check（486 files）、mypy app tests（477 files）都通過。
- `pytest --cov=app --cov-fail-under=90`：9660 passed、1 skipped、2 xfailed，覆蓋率 97.59%。
- 唯一的 skip 仍是 S11 的 N-177a 真實常數對齊測試，因為 store 還沒有這些常數。

## 各部門回報

### data-engineer

兩個檔案都在 `/home/user/AICompany/apps/stock-desk/backend/` 下，實際工作位置是 `wt_probe` worktree。
- 腳本：`scripts/n177_n190_backtrack_probe.py`
- 測試：`tests/test_n177_n190_backtrack_probe.py`（`T::` 代表這個測試檔）

| 項目 | 做法 | 測試 |
|---|---|---|
| R-1 | 對齊檢查抽成 `_assert_s2_constants_align`。兩邊空白正規化後比對，並對 `S2_UNAUDITED_SQL` 與 `S2_UNAUDITED_NO_TABLE_SQL` 都斷言。 | `T::test_s11_the_s2_constants_equal_the_store_once_n177a_defines_them`（現在 skip，N-177a 合併後自動啟用）、`T::test_s11_the_alignment_check_passes_against_the_spec_shaped_constants` |
| S-1 | 新增 `ENUM_VALUES` 白名單（`rule_id`、`action`、`status`、`source`）。值不在白名單時輸出「（非預期值）」，計數寫進 `meta.unexpected_enum_values`，報告標頭多一行「非預期值個數」。其他欄位維持原本的 sanitize。 | `T::test_s1_enumerated_columns_print_only_known_values_and_the_count_is_reported`、`T::test_s1_a_clean_book_reports_zero_unexpected_enum_values`、`T::test_s1_the_sanitize_enum_rules` |
| D-9 | 新增防護代碼 `D-9`。該檔判定用到的列只要有非預期枚舉值就列「需人工判讀」，不給試算分配也不給金額。用到的列包括 G-a 的列（`rule_id`）、G-c／N177-F 的在途賣單（`rule_id`）、該檔 S2 列的 `status`。 | `T::test_d9_a_row_with_an_unexpected_enum_value_withholds_the_trial`、`T::test_d9_in_flight_row_and_s2_status_with_unknown_values`、`T::test_d9_known_values_leave_the_trial_alone` |
| S-2 | `INDEX_BARS_SQL` 排除 demo 來源，交易日曆與 N190-B 的快取事實都不含 demo 的 `^TWII` bar。 | `T::test_s2_demo_index_bars_do_not_enter_the_calendar_or_the_cache_fact` |
| S-3 | docstring 與 L8 補一句：WAL 模式的複本可能被 SQLite 在同資料夾建立 `-shm`／`-wal`，DB 雜湊只涵蓋主檔。L8 的代碼不變，限制仍是 L1～L11。 | `T::test_s3_the_wal_sidecar_caveat_is_in_the_docstring_and_the_limitations` |
| S-4 | S2 加權均成本只計成本大於 0 的批次，與 S1 迴圈對齊。 | `T::test_s4_a_non_positive_cost_is_left_out_of_the_whole_symbol_average` |
| S-5 | 組報告與渲染遇到 `ValueError`、`KeyError`、`TypeError`、`AttributeError` 時，改成 exit 2 並印 ASCII 說明，不寫任何檔。讀 DB 階段的 `ValueError`、`TypeError` 也一併改成 exit 2。 | `T::test_s5_a_previous_json_with_missing_fields_exits_two_without_a_traceback`、`T::test_s5_dirty_data_in_the_db_exits_two_without_a_traceback` |

R-1 實測：我用符合規格 4.2 形狀的假常數跑同一個對齊函式，結果通過。再把假的合格批次 SQL 改掉，函式會如預期失敗。

### 與風控 D-9 的出入（請寫進 PR 說明）

1. **只判定「用到」的列。**
   - G-a 的 SQL 只取 `action IN ('buy','sell')`，所以只有 `action` 是 buy 或 sell 的列才可能進入判定，那些列的 `action` 本來就屬於已知值。
   - `action` 本身出現非預期值的列不會被撈進判定，因此不觸發 D-9。
   - 我的測試原本有一個 `action=teleport` 的案例，因此移除；實際會觸發 D-9 的只有 `rule_id` 與 S2 列的 `status`。
2. **報告計數只算有輸出的欄位。**
   - `meta.unexpected_enum_values` 只算報告裡實際印出的欄位（黑名單、帳冊找不到批次列、順延等）。
   - D-9 觸發時用到、但沒有印出的列，不會累加計數；它們以 `D-9` 的理由句與 id 呈現。
3. **`source` 的白名單是空集合。** 目前報告沒有任何類別輸出 `source`，所以我沒有猜供應商名稱；以後若有輸出，所有值都會先被標為非預期，需要再補白名單。

## 驗證

- 工具自己的測試：121 passed、1 skipped。
- 全後端：9660 passed、1 skipped、2 xfailed，覆蓋率 97.59%。
- 執行過程中風控 D-9 追加，我中止並重跑了完整套件，上面是納入 D-9 後的結果。

## 下一步

- 請 qa-reviewer 複審 `51bb945`，Codex 第二意見待環境可用時補跑。
- 請 TA 確認 S-1 的決定，以及上面第 1、3 點。
- N-177a 合併後，請確認 S11 的 skip 測試轉為通過。

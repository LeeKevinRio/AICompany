# N-98 重放取數測試補格

- 審查者：data-engineer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

N-98 的 4 格測試與 docstring 補述都已完成，程式邏輯沒有改，行為與 6def9ef 相同。新增 11 個測試，`tests/test_replay_index_snapshot.py` 全數通過（177 passed，原為 165 加這次新增的 12 個，其中 1 個是 (2) 的 `NaN`／`Infinity` 兩種參數化格）。ruff、ruff format、mypy 都乾淨。沒有 commit、沒有 `git add`，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改 ADR 或 `work/`。

## 各部門回報（data-engineer）

**改動檔案**（在 `apps/stock-desk/backend/` 下，皆為工作樹未暫存）：
- `app/data/providers/yfinance.py`：只改 `_classify_raw_rows` 的 docstring，新增「Edge conventions」段（英文），寫明三點：
  - 「無法轉成整數」以 Python `int()` 加上日期推導判定。JSON 數字 `1704157200.5`（解析成 `Decimal`）是 bar，字串 `"1704157200.5"` 是畸形，原值一律保留。
  - 價格非有限值（`NaN`／`Infinity`）不算畸形，轉成非有限 `Decimal` 後仍是 bar，留給重放閘門處理。
  - volume 非有限值是畸形，因為 `int()` 轉非有限 `Decimal` 會拋例外，整次失敗。
- `tests/test_replay_index_snapshot.py`：新增 `TestNonFiniteValuesAndNonIntegerTimestamps` 類別與兩個輔助函式（`_json_literal_step`、`_body_with_first_timestamp`），並 `import json`。

**新增測試名稱（對應風控 4 格）**
1. close 為 `NaN`／`Infinity`（JSON 字面）是 bar、不是畸形：
   - `test_non_finite_close_is_a_bar_not_malformed`：4 根 bar 的位置都保留，`close.is_nan()` 與 `close.is_infinite()` 成立，無缺口列。
   - `test_non_finite_close_reaches_the_snapshot_as_backup`：service 層回 `BACKUP`、4 根 bar。
2. volume 為 `NaN` 是畸形，reason 與其他畸形格相同：
   - `test_non_finite_volume_is_malformed_with_the_common_reason`：參數化 `NaN`、`Infinity`，reason 與 `close_value_abc` 那格逐字相等且含「無法解析的列」。
   - `test_non_finite_volume_fails_the_service_call_too`：service 回 `UNAVAILABLE`、零 bar。
   - `test_non_finite_volume_on_a_null_gap_row_is_malformed`：缺口列上的非有限 volume 同樣整次失敗。
3. 小數時間戳記：
   - `test_fractional_json_number_timestamp_is_a_bar_with_decimal_raw`：`raw_timestamp` 為 `Decimal("1704157200.5")`，型別確為 `Decimal`，`session_date` 為 2024-01-02。
   - `test_fractional_string_timestamp_is_malformed`：字串 `"1704157200.5"` 整次失敗，reason 含「無法解析的列」。
   - 順手補一格：`test_integer_string_timestamp_is_still_kept_as_a_string`，字串 `"1704157200"` 是 bar，原值型別保留為 `str`。
4. 缺口列時間戳記型別保留，service 原樣轉交：
   - `test_gap_row_keeps_decimal_timestamp_type_through_the_service`：JSON `1704182400.0` 得 `Decimal("1704182400.0")`，`str()` 仍為 `1704182400.0`，保留小數位。
   - `test_gap_row_keeps_string_timestamp_type_through_the_service`：字串 `"1704182400"` 保留為 `str`。
   - `test_service_hands_over_gap_timestamp_types_unchanged`：用假 provider，轉交後型別分別為 `Decimal`、`str`、`int`。

## 驗證

指令都在 `/home/user/AICompany/apps/stock-desk/backend` 下執行：
- `.venv/bin/ruff check .`：All checks passed。
- `.venv/bin/ruff format --check .`：399 files already formatted。
- `.venv/bin/mypy app tests`：no issues found in 395 source files。
- `.venv/bin/python -m pytest -q tests/test_replay_index_snapshot.py`：177 passed。

全套 pytest 依你的指示沒有重跑，由 coordinator 執行。

## 下一步

1. **coordinator**：跑全套 pytest，再決定這兩個檔案要不要併入 N-98 的 commit。
2. 我跑 `git status` 時，工作樹另有兩個不是我改的檔案：ADR-0027（`docs/adr/0027-…登記.md`）與事先宣告草案（`work/research/2026-10-15-…事先宣告草案.md`）。可能是其他流程的未提交修改，請留意 commit 時不要誤帶進 N-98。

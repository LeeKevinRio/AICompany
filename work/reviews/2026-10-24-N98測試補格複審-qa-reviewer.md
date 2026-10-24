# N-98 測試補格複審

- 審查者：qa-reviewer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## Summary
N-98 複審：PASS，無 BLOCKING_ISSUES。`yfinance.py` 只有 docstring 變動（單一 hunk，`+13`、`-0`，全為 `_classify_raw_rows` 的 docstring 新增行），沒有任何行為變更。新增測試真的釘住風控 R-A1 與「下一步」第 4 點的 4 項，不是恆真。範圍只看你指定的兩個檔的未 staged diff，工作樹的 ADR-0027 與事先宣告改動未審。

## 逐項確認

### 1. yfinance.py 只有 docstring
diff 只有 `_classify_raw_rows` docstring 內的 "Edge conventions" 段，沒有程式碼行被增刪。docstring 為英文。三點與 R-A1 字面一致：
- `int()` 加日期推導判定：JSON 數字 `1704157200.5`（讀成 `Decimal`）可轉、是 bar；字串 `"1704157200.5"` 不可轉、是畸形；原值保留。與 R-A1 相符。
- 價格非有限值（`NaN`／`Infinity`）可轉、不是畸形。與 R-A1 相符。
- volume 非有限值是畸形，因為 `int()` 轉非有限 `Decimal` 會拋例外。與 R-A1 相符。
- 小措辭差異：docstring 寫「left for the replay gate's value checks」，R-A1 寫「依 `canonical_bar_values` 與事先宣告 §6.3 X1 處理」。不矛盾，但 X1 才是依據。建議（非阻擋）改成指向 `canonical_bar_values` 與 §6.3 X1，免得日後讀成別的檢查。

### 2. 新測試是否真的釘住（我逐格推演，無法實跑）
- **(1) close 為 NaN／Infinity 是 bar**
  - 用 `json.dumps` 手寫 body（`_json_literal_step`）而不是 `httpx` 的 `json=`，所以 `NaN`／`Infinity` 確實以字面進入。
  - 若程式把非有限價格誤判成畸形，`reason is None` 會失敗。
  - 斷言：四個位置都保留（`session_date == JAN_DAYS`）、`close.is_nan()` 與 `close.is_infinite()` 成立、其餘 close 為 `Decimal("3.0")`、無缺口列。service 層另測得 `BACKUP` 與 4 根 bar。
- **(2) volume 非有限值是畸形**
  - 參數化 `NaN` 與 `inf`：`NaN` 觸發 `ValueError`，`Infinity` 觸發 `OverflowError`，兩者都在 `except` 清單內。
  - reason 與 `close_value_abc` 那格逐字相等，且含「無法解析的列」。
  - service 層回 `UNAVAILABLE`、零 bar，缺口列上的非有限 volume 也整次失敗。
  - 若程式改成略過或放行，會失敗。
- **(3) 小數時間戳記**
  - 以 sentinel 取代法把第一個時間戳記寫成原始 JSON 字面 `1704157200.5`，並用 `assert text.count(sentinel) == 1` 防止取代落空。
  - 斷言：`raw_timestamp == Decimal("1704157200.5")`、`type(...) is Decimal`、日期為 2024-01-02。
  - 字串 `"1704157200.5"` 是畸形。另補一格：整數字串 `"1704157200"` 是 bar，且型別保留為 `str`。
- **(4) 缺口列型別保留**
  - `Decimal("1704182400.0")` 經 service 後仍是 `Decimal`，`str()` 仍為 `1704182400.0`（小數位保留）。
  - 字串 `"1704182400"` 保留為 `str`。
  - 假 provider 測 service 原樣轉交，三種型別 `Decimal`、`str`、`int` 都不被改。
- 沒有只記錄現況而掩蓋錯誤的格子；每格若程式行為偏離 R-A1 都會失敗。

## 各檔問題
### apps/stock-desk/backend/tests/test_replay_index_snapshot.py
- [可維護性][low] **只測了 close 的非有限值。** R-A1 寫的是 open、high、low、close 皆同。程式對四欄走同一個 `_to_price`，風險極低，要補可用參數化覆蓋四欄。不擋。
- [可維護性][low] **`# N-98 (2)` 註記放在 volume 賦值那行，其餘格在函式名行。** 純風格。

### apps/stock-desk/backend/app/data/providers/yfinance.py
- 無問題，見上方 docstring 措辭建議。

## 安全
無祕密、無網路（`httpx.MockTransport`）、無 `.db` 存取，未讀 `.env`。

## 第二意見（Codex）
Codex 第二意見未執行（環境不可用）。錯誤訊息：`/bin/bash: line 1: codex: command not found`。合併前仍須在有 `codex` 的環境補跑 `/review`。

## 唯讀權限判準常數
未觸及。兩道機械檢查（對這次未 staged diff）皆無輸出：`scripts/validate_agents.py` 不在變更清單內；diff 內沒有任何增刪行含 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。沒有異動 agent，也沒有常數 shadow 定義或值被改動，故改了什麼、為何改、有無對應 ADR 皆不適用。

## 後續
- coordinator 的全套含覆蓋率結果仍待確認。
- 依風控：此測試補格須在 `replay_checks.py` 實作前完成，已符合。

Verdict
PASS
無 BLOCKING_ISSUES
BLOCKING_ISSUES=false

涉及檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_replay_index_snapshot.py

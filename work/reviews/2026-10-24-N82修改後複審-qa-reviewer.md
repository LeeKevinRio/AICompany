# N-82 修改後複審

- 審查者：qa-reviewer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## Summary
複審結論：PASS，無 BLOCKING_ISSUES。TA 裁定的第 1、2、5 點與 L-3 都依字面落實，我上次的 M-1、L-2、L-3、L-4 都已處理。`_classify_raw_rows` 三分類與 TA 裁定和 N97-1 字面一致，既有 `_parse_row`／`_parse_result` 行為逐位不變。新發現只有 low 級建議。Codex 第二意見仍未執行（環境不可用）。

審查範圍：`git diff --cached` 三檔，以及 TA 裁定檔、實作者修改回報、N97 起草第二節。工作樹與 staged 內容一致（`git diff` 無輸出）。我不能執行 pytest，測試有效性只做靜態判讀，全套結果以 coordinator 的預跑為準。

## 逐項回答

### 1. `_classify_raw_rows` 三分類對照 TA 裁定與 N97-1
全部一致，逐條如下：
- **陣列長度不一致算畸形**：先檢查五個陣列是否為 list 且長度等於 `timestamp`。`_chart_columns` 的 `or []` 讓缺漏或 null 視同長度 0，與「陣列缺漏或為 null 視同長度 0」相符。非 list 的值（例如字串）也歸畸形。
- **時間戳記**：`None` 或 `bool` 直接畸形。`int(ts)` 失敗，或推導日期時拋 `ValueError`／`OverflowError`／`OSError`／`TypeError`，都轉成 `_MalformedRowError`。
- **有 null 欄位的列，其餘非 null 值也驗證**：確實做了。null 分支會對每個非 null 欄位呼叫 `_to_price`／`_to_volume`，壞值就整次失敗。測試 `bad_value_beside_a_null`（close 為 null、open 為 `"abc"`）釘住這點。
- **範圍外畸形列也整次失敗**：畸形判定都在範圍過濾之前。測試 `malformed_row_outside_range`（start−1 日那列 close 為 `"abc"`）與 `all_null_row_with_millisecond_timestamp` 釘住。
- **缺口**：條件為日期可推導、在 `[start, end]` 內、至少一個 null。缺口放進 `null_gap_rows`，欄位 `raw_timestamp`、`session_date`、`null_fields`（依 open、high、low、close、volume 順序）與 N97-1 的 `{raw_timestamp, session_date, null_fields}` 完全相同。範圍外的缺口不列入，與 (2-l) 相符。沒有缺口時是空 tuple，不是 `None`。
- **只有缺口沒有 bar 仍失敗**：`if not bars` 回「查無…」，有測試 `test_gaps_without_any_bar_still_fail`。
- **好列夾畸形列不外洩**：畸形列在迴圈中途 raise，整個函式回傳失敗，不會回傳先前已收集的好列。測試 `test_good_rows_around_a_malformed_row_are_not_returned` 釘住。
- **同一句 reason**：所有畸形格都回「yfinance 回應含無法解析的列，暫不可用。」。測試斷言 14 格的 reason 集合大小為 1，並在 adapter 與 service 兩層各驗一次。
- **單一請求與請求區間**：永遠一次請求，區間為 `[start−1, end+1]`，加上 `_request_chart_result` 內建的 +1 日後，`period2` 為 `end+2` 日午夜。這與 TA 的 (1-a) 一致，也與 N97-2 一致。多視窗相關程式與常數都已刪除，且有測試確認。
- **`fromtimestamp` 唯一處**：僅在 `_derive_session_date`。呼叫端恰為 `_parse_chart_row` 與 `_classify_raw_rows`，AST 測試釘住這兩層。

### 2. 既有路徑逐位不變
- 逐行比對 `_parse_chart_row`：求值順序仍是 `ts is None`、取五個陣列元素（可能 `IndexError`）、任一為 null 就略過、推導日期、轉換，與原 `_parse_row` 相同。
- `_to_price` 與 `_to_volume` 只是把原本的 `Decimal(str(x))` 與 `int(Decimal(str(x)))` 抽成函式，語意相同。
- `_parse_row` 只是改為呼叫 `_parse_chart_row` 再組 `PriceBar`。`_parse_result` 沿用原有的 `except` 攔截清單（不含 `OverflowError`，維持現狀）與範圍過濾。
- `_request_chart_result` 的 7 個錯誤字句與原 `_fetch` 逐字一致，`_fetch` 與 `get_index_daily_bars` 的請求區間沒動。
- 測試 (2-n) 確認 `get_index_daily_bars` 對毫秒時間戳記、close 短一格、close 為 `"abc"`、全 null 列這些 payload，仍靜默略過畸形列（行為刻意不變）。

### 3. `received_at` 取時點
在 `_request_chart_result` 成功返回後立即取，位置在檢查 `error_reason` 之前、分類之前。這符合 TA (5-a)。失敗路徑也會取一次，但不使用，無害。`_request_chart_result` 返回時已含 JSON 解析時間，所以 `received_at` 會略晚於實際收到 bytes 的時刻。對 `as_of ≤ fetched_at` 的方向是保守的，不是缺陷。測試 `TestReceivedAt` 釘住 `as_of ≤ 請求進入 transport ≤ received_at ≤ 呼叫結束`，service 原樣轉交。

### 4. 上次問題的處理狀況

| 項 | 狀態 |
|---|---|
| M-1 畸形列靜默略過 | 已處理，見第 1 點 |
| M-2 多視窗 | 已刪除（TA 採方案 B），測試確認機制不存在 |
| L-2 失敗格只斷言非空 | 已處理：17 格各加關鍵字斷言，adapter 與 service 兩層都驗；畸形格用 `無法解析的列` 關鍵字 |
| L-3 `source="none"` | 已處理：`ReplayIndexSnapshot.source` 改為 `str \| None`，不支援代號分支為 `None`，docstring 明寫「不是來源名稱，`replay_checks` 不得當來源名寫入」；有 4 個測試 |
| L-4 相對 import | 已處理：import 測試加 `node.level == 0` 斷言 |
| L-1 台北 00:00 的 UTC 日期慣例 | 不在本輪範圍，仍是 N-82／#49 議題。單一請求加上前後各一天，已消除「邊界掉列」的結構性風險 |

### 5. 安全
無祕密，無網路（`httpx.MockTransport`），無 `.db` 存取（只有 `tmp_path` 暫存 DB），未讀 `.env`。

## 各檔問題

### apps/stock-desk/backend/app/data/providers/yfinance.py
- [Edge case][low] **N-1　非有限數值（`NaN`／`Infinity`）的價格會通過 `_to_price` 成為 bar。** Python 的 `json` 預設接受 `NaN`／`Infinity` 字面。`Decimal("nan")` 與 `Decimal("inf")` 能轉換，不會被判成畸形；成交量走 `int(Decimal(...))`，非有限值會丟 `ValueError`／`OverflowError` 而被判畸形。N97-1 的字面是「非 null 的價量值無法轉成數值」，非有限值依字面應視為無法轉成數值。Yahoo 實務上用 null 不用 NaN，風險低。建議在 `_classify_raw_rows` 對價格加 `.is_finite()` 檢查並補一格測試，或請 TA 在 N97-1 明寫是否涵蓋。不擋。
- [可維護性][low] **N-2　`bar is None` 的 unreachable 分支。** 該分支 fail-closed，方向正確；可考慮以 `# pragma: no cover` 或改為 `assert`，純風格，不擋。

### apps/stock-desk/backend/app/services/index.py
- 無問題。新增的 `ReplayNullGapRowLike`、`ReplayIndexNullGapRow`、`received_at`、`null_gap_rows` 都原樣轉交。`well_formed` 規則不變，仍保留序號 1..n 與「每份有 bar」，改由假 provider 測試覆蓋。(b) 的禁用名稱與 import 限制仍成立，只新增標準庫 import。

### apps/stock-desk/backend/tests/test_replay_index_snapshot.py
- [可維護性][low] **N-3　缺口列的 `raw_timestamp` 型別保留，只測了整數。** 缺口列帶 `Decimal` 或字串時間戳記（可推導日期）的情形沒有測試，而 N97 的「型別保留」明文涵蓋 `null_gap_rows`。建議補一格。不擋。
- [可維護性][low] **N-4　`test_failure_with_cached_twii_rows_still_yields_zero_bars` 與 spy 類測試仍近乎恆真。** 這是 ADR (d) 字面要求，可接受，與上次相同。

## 與 N97 起草的字面一致性
- 欄位名稱、順序、「缺口不是列」「空陣列非 null」「單一請求 `[S−1, E+1]`」「`response_seq` 恆為 1」「`received_at` 與 `as_of`」都與程式一致。
- 一處對照提醒：N97-1 寫「時間戳記無法轉成整數」，程式用 `int(ts)`。因此 `Decimal("1704157200.5")` 會截斷成功並照原值保留，而字串 `"1704157200.5"` 會 `ValueError` 而被判畸形。兩者結果不同，這是 `int()` 的語意，與 TA 裁定第 3 點「非整數保留原樣」並不衝突，但建議 N97-1 的字面註明「以 Python `int()` 判定」，免得 dev-lead 日後讀成不同標準。

## 第二意見（Codex）
Codex 第二意見未執行（環境不可用）。錯誤訊息：`/bin/bash: line 1: codex: command not found`。依章程「PR 必經 Codex 第二意見」，合併前仍須在有 `codex` 的環境補跑 `/review`。本次 PASS 是在 Codex 缺席前提下給的。

## 唯讀權限判準常數
未觸及。兩道機械檢查（對 staged diff）皆無輸出：`scripts/validate_agents.py` 不在 staged 檔案清單內；diff 內沒有任何新增或刪除行含 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。沒有異動 agent，也沒有常數在別處出現 shadow 定義或值被改動。改了什麼、為何改、有無對應 ADR：皆不適用。

## 結論與後續
- 無 BLOCKING_ISSUES。
- 非阻擋建議：N-1（非有限價格）、N-3（缺口列型別保留測試）、N97-1 補註 `int()` 判定。
- 仍待：Codex 第二意見；coordinator 的全套含覆蓋率結果；N97 ADR-0027 修訂落檔與風控確認後，`replay_checks.py` 才能實作快照寫入；決策包 #49 兩題。

Verdict
PASS
BLOCKING_ISSUES=false

涉及檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/index.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_replay_index_snapshot.py

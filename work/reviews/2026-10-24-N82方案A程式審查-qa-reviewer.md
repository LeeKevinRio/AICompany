# N-82 方案 A 重放快照取數路徑程式審查

- 審查者：qa-reviewer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## Summary
三個檔的實作整體符合 ADR-0005 I-3 註記 (a)～(g)，既有路徑重構經逐行比對行為不變，沒有 critical 或 high 問題。有兩項實作者裁量點（多視窗切分、逐列略過語意）建議送 TA 裁定，不擋本次放行。Codex 第二意見因環境不可用而未取得。

**Verdict：NEEDS_CHANGES 不成立，結論為 PASS，無 BLOCKING_ISSUES。**

審查範圍：`git diff --cached` 三個檔（`yfinance.py`、`index.py`、新檔 `test_replay_index_snapshot.py`）逐檔讀過，並對照 ADR-0005 註記、ADR-0024 N-93、ADR-0027 D-3 v0.26 句與實作者回報。我不能執行 pytest，測試有效性只做靜態判讀。

## 逐項回答你要我特別審的 5 點

### 1. 是否完全符合 ADR-0005 註記
符合，逐條對照如下。
- **狀態**：函式內 `DataStatus` 成員只有 `BACKUP` 與 `UNAVAILABLE`。成功路徑為 `BACKUP`，其餘分支皆走 `_replay_unavailable`。
- **快取、服務層、額度**：函式本體沒有引用 11 個禁用名稱。`index.py` 新增的 import 只有 `Sequence`、`datetime`、`UTC`、`Decimal`，沒有 import 具體 adapter、cache、quota。
- **輸出型別**：`ReplayIndexSnapshot` 是專用 frozen dataclass，沒有 `meta()`，也沒有 `notes`。欄位為 `index_symbol`、`status`、`as_of`、`source`、`responses`、`reason`，另有 `bar_count` 屬性。
- **fail-closed**：
  - adapter 端：任何一份視窗失敗，就回 `responses=()` 加 `reason`，不回傳第一份好的回應。
  - service 端：`well_formed` 要求符合下列四條，否則一律 `UNAVAILABLE`、零回應。
    - 回應非空。
    - 序號為 1..n。
    - 每份都有 bar。
    - 回傳的代號等於 `^TWII`。
  - 空字串 `reason` 也會被擋下。
- **代號封閉**：service 只收 `MARKET_BENCHMARK["TW"].series_symbol`，其他代號不呼叫 provider。送進 provider 的一律是基準代號，不是傳入值。adapter 端只收 `INDEX_SYMBOL_METADATA` 的鍵，而且起訖日顛倒時零請求。
- **adapter 一側**：新方法不在 `MarketDataProvider` ABC，也不經 `IndexProviderBridge`。檔頭有 role 3 說明，並明寫「未經真實回應驗證」，涵蓋 `exchangeTimezoneName`、`gmtoffset` 與時間戳記時刻，符合註記要求。
- **ADR-0024 N-93**：raw 路徑不讀 `meta.currency`，與例外條文「幣別取自 `INDEX_SYMBOL_METADATA`」一致。
- **ADR-0027 D-3 欄位**：`raw_timestamp`、`response_seq`、`exchange_timezone_name`、`gmtoffset` 皆原值帶出。

### 2. 既有路徑行為不變
我逐行比對 diff，結論是不變。
- `_request_chart_result` 的 7 個錯誤字句與原 `_fetch` 逐字相同，回傳形狀也一致。
- `_chart_columns` 抽自原 `_parse_result` 的前半，條件與 `or []` 語意相同。
- `_parse_chart_row` 與原 `_parse_row` 的求值順序相同，依序為 `ts is None`、`opens[idx]…`、任一 None 就略過、`fromtimestamp`、`Decimal`。`PriceBar` 仍在 `_parse_row` 內組裝，例外攔截位置沒動，所以略過語意不變。
- `get_index_daily_bars` 與 `fetch_chart_closes` 的呼叫鏈是 `_fetch` 加 `_parse_result` 加 `_parse_row`，簽名與回傳值不變。`OverflowError` 在既有路徑仍未攔截，維持現狀，沒有被意外改變。
- `fromtimestamp` 在 `yfinance.py` 只剩 `_parse_chart_row` 一處，測試以 AST 計數釘住。

### 3. 實作者 5 個裁量點的歸類

| 裁量點 | 歸類 | 說明 |
|---|---|---|
| 多視窗切分（1096 天、均分、依推導日期過濾） | 需 TA 裁定，非缺陷 | 邏輯與邊界正確，且有測試。但 ADR 沒有規定何時會有多份回應，1096 這個上限也沒有 Yahoo 端依據，是推測。它會讓同一段區間的請求數與 `response_seq`、`content_sha256` 隨常數而變。建議 TA 明確核可，或改為永遠單請求。若核可，應把 1096 與切分規則記入 ADR 或定義登記，避免日後調整常數而不自覺。 |
| null 列沿用略過不揭露 | 可接受 | Yahoo 的 null 是合法缺口，揭露屬 N-82 範圍外。但見下 M-1：同一個 `except` 也吞掉非 null 的畸形列。 |
| `Decimal`／字串時間戳記保留原樣 | 可接受 | 符合 ADR-0027「不是整數時照原樣存」。`replay_checks.py` 寫 JSON 時要處理 `Decimal`，已列入交接。 |
| service 不吞 provider 例外 | 可接受 | 與 ADR「連線失敗由 `replay_checks` 寫 `fetch_failed`」的分工一致，且有測試。 |
| `as_of` 單一值 | 可接受 | 與 `fetched_at` 的對應留給 `replay_checks`。 |

### 4. 測試有效性
- **AST 掃描器**：不會空轉。
  - `_files_mentioning` 涵蓋 Name、Attribute、alias（含 asname）、def、arg、keyword 與字串常數。
  - 每個測試都斷言定義檔確實被掃到，並有掃描器自測（別名、屬性、`getattr` 字串）。
  - (b) 有守衛，確保名稱含 `replay` 的函式恰為受檢清單。
  - (c) 以集合相等斷言 `{BACKUP, UNAVAILABLE}`，不是單向包含。
- **spy**：抓得到。
  - 先在未打補丁時預置快取列、fetch log、attempt log 與配額列，再對 `PriceBarCache` 與 `QuotaLedger` 的每個公開方法打補丁。
  - 有「spy 確實會計數」的自證測試，並斷言四張表列數不變。
  - 限制：重放函式本來就沒有取得 cache 實例的路徑，所以這組測試近乎恆真。這是 ADR (d) 的字面要求，可接受。
- **(e) 各格**：18 種失敗乘以（單份、第二份失敗）共 36 格，真的在測 fail-closed。
  - 斷言包含：`UNAVAILABLE`、零回應、零 bar、reason 非空、只打 Yahoo 的 `^TWII` 路徑、請求數 ≤ 2。
  - 第二份失敗時，`"2/2" in reason` 保證失敗確實發生在第二份。
  - 第一份失敗時不發第二個請求。
  - 弱點：各格只斷言 reason 非空，沒有釘住各格走到預期的分支。這屬 low，見 L-2。
- **只記錄現況的測試**：
  - 「台北 00:00 時間戳記被標成前一個 UTC 日」那條，已在註解與回報中明示是現況。它釘住了一個可能有問題的慣例，待決策包 #49 實測後需連動調整，不算掩蓋錯誤。
  - 「保留重複日期、保留來源順序」是設計意圖，可接受。

### 5. 安全
- 沒有祕密。
- 沒有網路：測試全用 `httpx.MockTransport` 與假 provider。
- 沒有 `.db` 存取：只有 `tmp_path` 的暫存 DB。
- 沒有讀 `.env`。
- diff 內沒有 api key、token 之類字樣。

## 各檔問題

### apps/stock-desk/backend/app/data/providers/yfinance.py
- [Edge case][medium] **M-1　`_raw_bars` 把非 null 的畸形列也靜默略過，且處理不一致。** 需 TA 裁定，不擋。
  - 現況：沿用的 `except (KeyError, TypeError, ValueError, InvalidOperation, IndexError)` 會吞掉這些列，例如平行陣列比 `timestamp` 短造成 `IndexError`、無法換算的時間戳記、`Decimal` 轉換失敗。
  - 只要至少還有一根 bar，整次就回 `BACKUP` 成功，快照缺列且不告知。
  - 不一致處：同樣是「時間戳記無法換算」，`10**30` 觸發的 `OverflowError` 會整次 fail-closed，而毫秒級時間戳記（約 1.7e12）會觸發 `ValueError: year … out of range`，只是被略過。這是我依 CPython 行為推斷，沒有實跑。
  - 為何要提：null 列是合法缺口，沿用略過可接受。但 ADR-0005 的 fail-closed 條列有「回應無法解析」，畸形列依字面較接近這一條。
  - 建議：raw 路徑把「null 缺口」與「畸形列」分開。畸形列直接整次失敗，或至少計數後回報給 `replay_checks`。請 TA 裁定哪一種。
  - 測試缺口：目前只測了 `10**30`，沒有測 `ValueError` 路徑的毫秒時間戳記。
- [可維護性][medium] **M-2　多視窗切分的 `RAW_CHART_MAX_WINDOW_DAYS = 1096` 缺乏依據。** 見上表，需 TA 核可。
- [Edge case][low] **L-1　範圍過濾以 UTC 推導日期為準。** 若真實 `^TWII` 時間戳記是台北 00:00，起始日當天的 bar 會被推導成前一日而被範圍過濾靜默丟棄，掩蓋 gate (5a)(5b) 想看到的差異。這與既有日線路徑相同，屬 #49 實測議題，記錄即可。

### apps/stock-desk/backend/app/services/index.py
- [可維護性][low] **L-3　不支援代號分支的 `source` 寫死字串 `"none"`。** `replay_checks` 若直接寫入 `fetch_failed` 列，這個字串可能被當成來源名。建議在 docstring 註明，或改用明確的常數。
- 其餘無問題。`well_formed` 不驗證 bar 日期是否落在 `[start, end]`，那是 adapter 的責任，可接受。

### apps/stock-desk/backend/tests/test_replay_index_snapshot.py
- [可維護性][low] **L-2　(e) 各格只斷言 `reason` 非空。** 同一個格子可能因錯誤的原因通過。建議對有明確分支的格子（例如 `chart_error`、`non_json`、`timestamp_missing`）加斷言，比對 reason 中的關鍵字。
- [可維護性][low] **L-4　`test_module_imports_no_cache_quota_or_provider_module` 沒涵蓋相對 import。** 例如 `from ..data import cache` 會被解析成 `data.cache`，不在禁用清單內。目前 `index.py` 沒有相對 import，風險低。可補一個 `node.level > 0` 的斷言。
- [可維護性][low] **L-5　`test_failure_with_cached_twii_rows_still_yields_zero_bars` 近乎恆真。** 見上「測試有效性」，可接受。

## 第二意見（Codex）
Codex 第二意見未執行（環境不可用）。錯誤訊息：`/bin/bash: line 1: codex: command not found`。依角色紅線，我未改走其他途徑。本報告的 PASS 是在「Codex 缺席」前提下給的。若要符合章程「PR 必經 Codex 第二意見」，需在有 `codex` 的環境補跑 `/review`，再合併。

## 唯讀權限判準常數
未觸及。兩道機械檢查（對 staged diff）皆無輸出：
- `scripts/validate_agents.py` 未在 staged 檔案清單內。
- diff 中沒有任何新增或刪除行含 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。

另外：
- 沒有異動任何 agent 定義，也沒有常數在別處出現 shadow 定義或值被改動。
- 改了什麼：無。為何改：不適用。有無對應 ADR：不適用。

## 待辦與建議

**需 TA 裁定（皆非阻擋）**
1. M-2 多視窗切分：核可 1096 與切分規則（並記入 ADR 或定義登記），或改為永遠單請求。
2. M-1 畸形列語意：略過、計數揭露或整次失敗。
3. 建議在 `replay_checks.py` 實作前先定案。該檔實作時 (a) 的允許清單才會真正生效。

**成熟度**
- 全套覆蓋率（目前背景重跑）仍待 coordinator 補上確認。
- 決策包 #49（真實 `^TWII` 時間戳記實測）仍是閘門 (b) 的另一個擋點，本實作不取代它。

**Verdict**
PASS
無 BLOCKING_ISSUES
BLOCKING_ISSUES=false

涉及檔案：
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/index.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_replay_index_snapshot.py

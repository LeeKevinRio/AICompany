# N-82 方案 A 重放快照取數路徑實作

- 審查者：data-engineer
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

N-82 方案 A 的重放快照取數路徑已實作完成，離線測試、lint、型別檢查與全套 pytest 都通過。我沒有 commit、沒有 push，也沒有改 ADR 或 `work/`。驗收 (a)～(g) 加「`fromtimestamp` 只出現一次」都有對應測試。ADR 約束沒有任何一條做不到，也沒有放寬。

有四個設計上的判斷點請 qa-reviewer 與 TA 留意，見「各部門回報」第 4 點與「下一步」。

## 各部門回報（data-engineer）

**1. 改動檔案（均在 `apps/stock-desk/backend/` 下，未 commit）**
- 修改 `app/data/providers/yfinance.py`
- 修改 `app/services/index.py`
- 新增 `tests/test_replay_index_snapshot.py`（118 個測試）

**2. 實際名稱**

adapter 一側（`yfinance.py`）：
- 方法：`YFinanceAdapter.get_index_raw_responses(index_symbol, start, end) -> RawChartFetch`
  - 不在 `MarketDataProvider` ABC，也不經 `IndexProviderBridge`。
  - 代號只收 `INDEX_SYMBOL_METADATA` 內的值，其他代號零請求。
  - 起訖日顛倒時也零請求。
- 型別（都是 frozen dataclass）：
  - `RawChartBar`：`raw_timestamp`、`session_date`、`open`、`high`、`low`、`close`、`volume`。
  - `RawChartResponse`：`response_seq`、`exchange_timezone_name`、`gmtoffset`（原值，缺漏為 `None`）、`bars`。
  - `RawChartFetch`：`index_symbol`、`as_of`、`source`、`responses`、`reason`。
- 共用解析：新增模組層級的 `_parse_chart_row`，是全檔唯一的 `fromtimestamp`。
  - 既有的 `_parse_row` 改為呼叫它再組 `PriceBar`。
  - 新增 `_chart_columns` 抽出欄位陣列。
  - 新增 `_request_chart_result`，是從 `_fetch` 拆出的 HTTP 與信封檢查，錯誤字句不變。
  - 新增 `_raw_bars`，與 `_parse_result` 共用 `_parse_chart_row`。
- 常數 `RAW_CHART_MAX_WINDOW_DAYS = 1096` 與 `_split_windows`（見第 4 點）。
- 檔頭 docstring 新增 role 3 說明，並在 VERIFICATION STATUS 明寫此方法未經真實回應驗證，涵蓋真實 `^TWII` 的時間戳記時刻、`exchangeTimezoneName` 與 `gmtoffset`。

service 一側（`app/services/index.py`）：
- 函式：`fetch_replay_index_snapshot(provider, *, index_symbol, start, end) -> ReplayIndexSnapshot`。沿用暫定名，未更動。
  - 只接受 `MARKET_BENCHMARK["TW"].series_symbol`（`^TWII`）。
  - 其他代號回 `UNAVAILABLE`，且不呼叫 provider。
  - 呼叫 provider 時一律用基準代號，不用傳入值。
- 回傳型別：`ReplayIndexSnapshot`（`index_symbol`、`status`、`as_of`、`source`、`responses`、`reason`，另有 `bar_count` 屬性）。
  - 巢狀型別是 `ReplayIndexResponse`、`ReplayIndexBar`。
  - 不是 `ProviderResult`、`LoadedIndexBars` 或 `LoadedBenchmark`，不設 `meta()`，也不設 `notes`。
- Protocol：`ReplayIndexChartProvider`、`ReplayChartFetchLike`、`ReplayChartResponseLike`、`ReplayChartBarLike`。
  - 全部是結構型的唯讀 property，`index.py` 沒有 import 任何具體 adapter。
  - 新增的 import 只有 `collections.abc.Sequence`、`datetime`、`UTC`、`Decimal`。
- 私有輔助函式：`_replay_unavailable`。
- 常數：`REPLAY_UNSUPPORTED_SYMBOL_REASON`、`REPLAY_FETCH_FAILED_REASON`、`REPLAY_MALFORMED_RESPONSE_REASON`。
- 狀態只用 `DataStatus.BACKUP` 與 `DataStatus.UNAVAILABLE`。
- 模組 docstring 加一段說明此為 I-3 末句的唯一例外。

**3. 驗收對應測試**（測試檔內另有一份對照表在檔頭）

| 驗收 | 測試類別或測試 |
|---|---|
| (a) 呼叫點封閉 | `TestAcceptanceACallSiteClosure`：函式名、adapter 方法名、回傳型別三個名稱、Protocol 名稱、adapter 側 `Raw*` 型別各一個測試。AST 掃 `app/**`，涵蓋 Name、Attribute、import alias、定義名、參數名與字串常數。允許清單寫成 {定義檔, `app/forecast/replay_checks.py`}，註解已寫明該檔尚不存在。含一個掃描器自測（別名、屬性、`getattr` 字串都抓得到）和「定義檔確實被掃到」的防空轉斷言。 |
| (b) 不碰快取、服務層、額度 | `TestAcceptanceBNoCacheServiceQuota`：<br>- 函式本體不含 11 個禁用名稱。<br>- `index.py` 不 import `app.data.cache`、`app.data.quota`、`app.data.providers.*`。<br>- 守衛：模組內名稱含 `replay` 的函式必須恰為受檢清單，之後新增的重放函式不會漏檢。 |
| (c) 狀態 | `TestAcceptanceCStatus`：<br>- AST 斷言 `DataStatus` 成員集合恰為 `{BACKUP, UNAVAILABLE}`。<br>- 函式內無 `disclosed_status`、無 `FRESH`。<br>- 假 adapter 與真 adapter（`MockTransport`）成功皆為 `BACKUP`。<br>- 型別不是三個禁用型別，無 `meta`、`notes`，欄位集合以相等斷言釘住。 |
| (d) 快取與額度 spy | `TestAcceptanceDCacheAndQuotaSpy`：<br>- 用 `tmp_path` 預先放入 `^TWII` 快取列、fetch log、attempt log 與 `provider_quota_usage` 的列。<br>- 對 `PriceBarCache` 與 `QuotaLedger` 的每個公開方法裝計數 spy。<br>- 成功與失敗各跑一次：呼叫次數皆為 0，四張表列數不變。<br>- 成功時回傳的 close 為來源值，不是快取值。<br>- 另有「spy 確實會計數」的自證測試。 |
| (e) fail-closed | `TestAcceptanceEFailClosed`：18 種失敗，各測單份回應與「兩份回應中第二份失敗」，共 36 格。<br>- 失敗種類包含連線錯誤、HTTP 500／404／429、非 JSON、無 `chart`、`chart` 非 dict、`chart.error`、`result` 空／null／非 dict、`timestamp`／`indicators`／`quote` 缺漏、區間內無 bar、空 timestamps、全列 null、時間戳記超出平台範圍。<br>- 每格都回 `UNAVAILABLE`、零回應、零 bar、reason 非空。<br>- 第二份失敗時，連第一份好的回應也不回傳。<br>- 第一份失敗時不發第二個請求。<br>- 另測：快取有 `^TWII` 列時仍零 bar；請求只打 Yahoo 的 `^TWII` chart 路徑；單次失敗最多 2 個請求（傳輸層重試）。<br>- 7 種 provider 回報異常（空字串 reason、序號不從 1 起、序號重複、回應含別的代號、某份無 bar 等）service 側也拒絕。 |
| (f) 代號 | `TestAcceptanceFSymbols`：`^GSPC`、`^NDX`、`^SOX`，另加 `TWII`、`^twii`、`2330`、空字串、`^TWII ` 共 8 種，transport 為 0 次且 provider 為 0 次呼叫。adapter 層另測 `^SOX` 等不在 metadata 的代號零請求。 |
| (g) 既有路徑不變 | `TestAcceptanceGExistingPathsUnchanged`：`PriceBar` 與 `ProviderResult` 欄位集合、`MarketDataProvider.__abstractmethods__ == {"get_daily_bars"}` 皆以集合相等斷言；既有入口仍在；`get_index_daily_bars` 行為不變。<br>`ProviderResult` 的欄位集合含 `rejection`，這是現狀，我沒有動它。<br>既有測試（含 `IndexSeriesService`、`IndexProviderBridge`、`load_index_series`、`load_market_benchmark`、`deps`）完全沒改，全套通過。 |
| `fromtimestamp` 只出現一次 | `TestSingleDateDerivation`：<br>- AST 斷言 `yfinance.py` 中 `fromtimestamp`／`utcfromtimestamp` 恰 1 處。<br>- 該處位於 `_parse_chart_row`。<br>- 呼叫 `_parse_chart_row` 的只有 `_parse_row` 與 `_raw_bars`。<br>- 另有「raw 路徑與 `get_index_daily_bars` 對同一份 payload 產生相同的日期與 OHLCV」的行為測試。 |

**4. 需要裁量或請留意的地方**

1. **多份回應何時發生，ADR 沒規定，我自行設計。**
   - ADR 要求 `response_seq` 與「多份回應中任一份失敗」，但沒說何時會有多份。
   - 我讓 adapter 把超過 `RAW_CHART_MAX_WINDOW_DAYS`（1096 天）的區間均分成多個視窗，每窗一個請求與一個 `response_seq`。
   - 均分是為了不讓最後一窗只剩幾天：沒有交易日的視窗可能被 Yahoo 回錯，進而讓整次失敗。
   - 區間 ≤ 1096 天時只有一個請求，實務上重放區間大多如此。
   - 視窗邊界的 bar 以推導日期過濾，不會重複，已有測試。
   - 1096 這個數字是我的保守選擇，可調。請 TA 確認這個設計沒有違背他的原意，否則改成永遠單請求並不複雜。
2. **raw 路徑沿用既有的逐列略過語意。**
   - 逐列略過的情形有：任一 OHLCV 為 null、時間戳記為 null、列無法解析。
   - 因此「`raw_timestamp` 為 null」在實作上不會出現：沒有時間戳記就推導不出日期，該列整列略過，跟既有路徑一致。
   - 這些略過目前不計數也不揭露，屬於你劃在範圍外的 N-82「null 欄位列計數揭露」。
   - 這代表快照可能少了列，但 adapter 不會告知。
3. **非整數的時間戳記保持原樣。**
   - 因為 JSON 以 `parse_float=Decimal` 解析，帶小數的時間戳記會以 `Decimal` 傳回（有測試）。
   - 字串型的時間戳記若 `int()` 可轉就照原樣保留，日期照推導。
   - 下游 `replay_checks.py` 寫 JSON 時需自行處理 `Decimal`。
4. **service 不吞 provider 拋出的例外。**
   - fail-closed 的 `UNAVAILABLE` 涵蓋 adapter 回報的失敗與異常回應。
   - adapter 未預期的例外（程式錯誤）會直接往上拋，讓 `replay_checks.py` 依 ADR-0027 寫 `fetch_failed` 並帶例外類別。已有測試釘住。
   - adapter 內部對超出平台範圍的時間戳記有特別攔截，會轉成失敗而非拋出。
5. **既有行為的邊界。**
   - 我沒有改 UTC 日期推導，沒有加去重，沒有擋盤中半成品 bar，也沒有碰 `PriceBar`、`ProviderResult`、快取 schema 與 `app/forecast/**`。
   - 有一個測試把「台北 00:00 的時間戳記會被標成前一個 UTC 日」記錄為現況，並保留原始時間戳記，讓閘門 (5a)(5b) 能看到差異。
   - 日後 #49 實測後若改日期慣例，這個測試需要連動調整。
   - `as_of` 是呼叫開始時的 UTC 時間，整份快照一個值，沒有每份回應各自的取得時間。`fetched_at` 的對應由 `replay_checks.py` 決定。

## 驗證

指令都在 `/home/user/AICompany/apps/stock-desk/backend` 下執行，對齊 `.github/workflows/stock-desk.yml` 的 backend job。

- 基準線（改動前）：`.venv/bin/python -m pytest -q` 得 6551 passed、2 xfailed。
- 改動後：
  - `.venv/bin/ruff check .`：All checks passed。
  - `.venv/bin/ruff format --check .`：全部已格式化。
  - `.venv/bin/mypy app tests`（strict）：no issues found in 395 source files。
  - `.venv/bin/python -m pytest --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=90 -q`：**6669 passed、2 xfailed、0 failed**，約 13 分鐘。總覆蓋率 97.18%，高於 CI 的 90% 門檻。
  - 通過數 6669 等於基準線 6551 加上新增的 118 個測試，既有測試沒有任何改動。
  - 新測試檔單獨跑：118 passed。
- 全部離線：用 `httpx.MockTransport` 與假 provider，沒有打網路。DB 只用 `tmp_path`。
- 紅線：沒讀 `.env`，沒碰 `data/*.db`，沒有祕密寫進檔案。`git status` 只有上述三個檔案有變動。

## 下一步

1. **qa-reviewer**：審這三個檔，並做 Codex 第二意見。審查時請特別看第 4 點的 1（視窗切分）與 2（略過列不揭露）。
2. **tech-architect**：確認多視窗設計。若不要，改為永遠單請求即可，驗收 (e)「第二份失敗」的測試要改成在假 provider 層構造。
3. **dev-lead**：之後實作 `app/forecast/replay_checks.py` 時，呼叫端要符合 (a) 的封閉清單，只能 import `fetch_replay_index_snapshot` 與 `Replay*` 型別。
   - 回傳值要在同一個呼叫內寫入快照。
   - 要處理 `raw_timestamp` 可能是 `Decimal` 或字串。
   - 把 `reason` 寫進 `fetch_failed` 列。
4. **CEO 決策包 #49**（真實 `^TWII` 時間戳記實測）仍是閘門 (b) 的另一個擋點，本次實作不取代它。實測完成前，此方法在檔頭仍標示為未經真實回應驗證。

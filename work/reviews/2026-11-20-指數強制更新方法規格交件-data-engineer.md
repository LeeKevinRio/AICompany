# 指數強制更新方法規格交件

- 審查者：data-engineer
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

規格檔：`/home/user/AICompany/work/research/2026-11-19-指數強制更新方法規格-data-engineer.md`。只建立這一個檔，沒有 commit，沒有改產品程式。

**第 1 題單一答案：前提「某一列之後只會被更晚的時刻覆寫」嚴格說不成立，但「每個寫入點的 `as_of` 都是請求時刻」成立。唯一例外是兩個請求重疊的競態，不是任何寫入路徑。**

主線 `apps/stock-desk/` 全目錄（排除 `.venv`、`node_modules`、`__pycache__`、`tests/`）的寫入點只有三個：
- **W1 `app/data/cache.py:215-228`**
  - 這是唯一的 SQL 寫入點，`PriceBarCache.put`。
  - `as_of` 取 bar 自帶值（第 207 行），`fetched_at` 取參數（第 194 行）；兩者在 `ON CONFLICT` 時都無條件覆寫（第 227、228 行），不比較新舊。
- **W2 `app/data/service.py:353`**
  - 這是唯一的非 demo 呼叫端，`fetched_at=self._clock()`。
  - 對 `^TWII`，`as_of` 是 yfinance adapter 在請求前取的 `datetime.now(UTC)`（`yfinance.py:478`，每列 `as_of=now` 在第 745 行），所以同一次呼叫內 `fetched_at ≥ as_of`。
- **W3 `app/demo/seed.py:438`**
  - 它不寫 `^TWII`：標的只有 2330、0050、00631L。
  - 遇到其他來源的同鍵列會拒絕（`seed.py:428-433`）。
  - CLI 不傳 `as_of`，一律是執行當下。
  - 只有手動 `python -m app.demo.seed` 才會執行，不在排程、啟動、API 任何路徑上。
- 其他腳本與 `diagnose.py`、`event_study.py` 對這張表都只 `SELECT`。`delete_by_source` 只刪列，不寫 `as_of`。

**例外路徑（競態）：**
- `as_of` 是請求發出時刻，寫入發生在回應收到之後，而 W1 是最後寫入者勝。
- scheduler 與 API 可以是不同行程（各自有節流與 `lru_cache` 的服務），兩個請求重疊時，較早請求若較晚寫入，會把 `as_of` 改回較早的時間。
- 這會 fail closed：發生在核對之前，核對失敗；發生在核對之後、recorder 讀取之前，是毫秒級窗口，核對會放過。
- 此時值仍是 t0 前後數秒、15:00 之後的 Yahoo 回應，D-3 第 2 點照樣成立，被破壞的只有 G 的「不早於 t0」。
- 建議補充十不要寫「recorder 讀到的時間戳不可能早於 t0」，改寫為已知限制。

## 逐題回答

規格全文在檔內，這裡只列要點與行號（路徑為 `app/data/service.py`，除非另註）。

- **新方法放哪、簽章、回傳型別**
  - 放在 `MarketDataService`，緊接 `get_cached_bars`（486 行）之後，純新增。
  - 簽章：`refresh_daily_bars_live(self, symbol, market, start, end) -> LiveRefreshOutcome`。沒有時鐘參數。
  - `LiveRefreshOutcome` 是 frozen dataclass，欄位：`ok`、`source`、`requested_at`（provider 的 `as_of`）、`written_at`（`put` 用的 `fetched_at`）、`live_bar_count`、`live_latest_date`、`complete`、`reason`。
  - `ok=True` 的定義只有一個：走到 `put` 並完成寫入。回落到快取、被拒、全失敗、被丟光，一律 `ok=False`。
- **既有流程行號**
  - layer 0：298-304，本體 677-853。
  - cooldown：705-712、738-796、818-837，判定函式 `freshness.py:79-86、154-188`。
  - 增量起點：316-318，`_incremental_start` 在 650-675。
  - ladder：306-419。寫快取：352-355、400-403。
  - 回落到快取（新方法不得走）：424-436，`_fall_back_to_cache` 在 959-1043。
- **重用與不可重用**
  - 重用：`_refuse_unadmitted`、`_cache_refuses` / `_judge_bars`、`_incremental_start`、`_try_provider`（含 `_without_unfinished_session`）、`_combine_reasons`。
  - 不可重用：`_try_session_fresh_cache`、`_layer_zero_answer`、`_fall_back_to_cache`、`_cached_result`、`_refused_answer`。
- **既有路徑逐位元不變**
  - 只新增，不抽取。複製約 50 行 ladder，用 T-EQ 測試守住兩邊不漂移。
  - 守門測試有 `test_service.py`、`test_freshness.py`、`test_cache.py`、`test_f9b*`、`test_services_index*.py`、`test_scheduler*.py`。
  - `test_f9b0_rejection.py` 是 AST 守門：只允許 `data/service.py` 產生 `rejection=`，新方法不得違反。
  - `git diff` 對既有行零刪除。
- **取數範圍**
  - recorder：`forecast/recorder.py:668-670`，`start = 台北今日 − (500 + 31)`、`end = 台北今日`，`FETCH_CALENDAR_DAYS` / `FETCH_SLACK_DAYS` 在 145 / 148 行。
  - 強制更新必須用同公式，否則 coverage 的 `covered_start` 可能晚於 recorder 的 start，使 recorder 的 layer 0 落入無 coverage 分支再抓一次。
  - 實際向 Yahoo 要的是「最後一根快取 bar 所在月的 1 日」起（`_incremental_start`），涵蓋 T 日列，並重寫該月所有列的時間戳。
- **`index.py` 新增**
  - `IndexSeriesService.refresh_daily_bars_live` 穿透方法，接在 `get_cached_bars`（213-217）之後。
  - `force_refresh_benchmark(resolver, *, market, lookback_days) -> ForcedBenchmarkRefresh`，含 `live` 與 `latest_cached_bar`。函式內部讀系統時鐘算台北日期，沒有 `now` / `as_of` / `start` / `end` 參數。
  - 必須用 scheduler 同一次取得的 `get_index_resolver()` 物件：同行程內是同一個 `IndexSeriesService`、`MarketDataService`、快取與 yfinance adapter（`api/deps.py:377-379`，`lru_cache`）。
  - 讀回用既有 `get_cached_bars`（唯讀、不寫入、不打外網）。核對 `as_of ≥ t0` 留給 scheduler。
- **強制更新後 recorder 呼叫的逐步走**
  - 22:10 強制更新成功後，recorder 的 layer 0 判 `HAS_LATEST_SESSION`。因為剛抓完，在 1 小時 cooldown 內，806-817 的強制重抓分支不會進入，所以不會有第二次 live 請求。
  - recorder 讀到的 T 日列 `as_of` 就是強制更新那一次的，除非發生上述競態。
  - T 日列缺（例如 null volume）時：最新一根是 T-1，判 `CHECKED_RECENTLY`，同樣不再抓，recorder 回 `no_new_session`。
- **失敗模式**
  - Yahoo 不通、回空、provider 例外、幣別閘拒絕、讀回失敗：`ok=False`，並寫 `record_attempt`。
  - T 日列被 null 丟掉：`ok=True`，但 `live_latest_date < T`。
  - 盤中列被丟光：`ok=False`；只丟部分：`ok=True`，`live_latest_date` 較早。
  - 指數沒有第二個 provider（`deps.py:178-186` 只有 primary）。若將來有備援，呼叫端必須看 `source`。
- **副作用**
  - 強制更新成功會刷新 coverage 與 `last_fetched_at`，之後 1 小時內其他呼叫走快取。失敗只寫 attempt，其他呼叫服務快取並附失敗原因，不會多打 Yahoo。
  - 次日 17:45 的 sector job 不受影響，仍自己抓並蓋 17:45。22:10 之後打開頁面的人會讀到較新的值與時間戳。
  - rate limit：每天最多 +3 個請求（單行程節流 1 秒，重試固定 1/2/4 秒退避），沒有問題。
  - 該月所有列的 `as_of` / `fetched_at` 會被重蓋，既有取證腳本依賴的證據價值本來就會被任何重抓覆寫，不是新問題。
- **測試清單**
  - 共 23 項，全部離線。涵蓋略過 layer 0 與 cooldown、寫入欄位、回落不算成功、盤中列丟棄、增量起點、幣別閘、讀回失敗、例外、`complete=False`、T-EQ 等價、`index.py` 的簽章與讀回、強制更新後 recorder 不再抓、競態文件化測試、scheduler 側的失敗路徑。
  - 詳見規格檔 2.11。

## 驗證

- **做了什麼**：只讀程式與 grep，沒有執行任何程式或測試，沒有讀 `.env`，沒有碰 `data/*.db`，沒有執行 `.bat`。
- **讀過的檔**
  - 資料與服務：`app/data/cache.py`、`app/data/service.py`、`app/data/http.py`、`app/data/providers/yfinance.py`、`app/services/index.py`、`app/api/deps.py`。
  - demo：`app/demo/seed.py`、`app/demo/series.py`。
  - recorder 與排程：`app/forecast/recorder.py`、`app/scheduler.py`。
  - 設計文件：TA 的補充十文件。
  - 測試：既有測試只確認檔名與 AST 守門內容（`test_f9b0_service_scope.py`、`test_f9b0_rejection.py`）。
- **推論（沒有實跑）**：2.8 的逐步走與 2.9 的失敗模式表。
- **未能查證**
  - `_judge_bars` 的 `layer` 標籤是否被測試釘成固定集合（新方法建議用新標籤 `force_refresh`，實作前要 grep）。
  - `tests/market_service_helpers.py` 的假 provider 與時鐘注入是否足以支援 T-EQ。
  - `test_scheduler*.py` 是否釘住 `run_forecast_record` 的呼叫序列。
  - 前端 react-query 的自動重抓行為。
  - Yahoo 在各時點是否回 T 日列、值是否最終。

## 下一步（請轉回 TA；我沒有改設計）

1. **競態（見上方第 1 題例外）**：核對與 recorder 讀取之間的毫秒級窗口。選項：(a) 寫入已知限制，這是我的傾向；(b) 核對放進 recorder，TA 已否決；(c) 同行程互斥，無法根治跨行程。
2. **「強制更新成功但 T 日列缺」**：目前只會變成 `no_new_session`，無可見異常，與補充十第 2 點「失敗進 F-2 分子」不一致。請 TA 決定要不要用 `live_latest_date` 比對 `latest_completed_session` 並 log 或計入 F-2。
3. **23:10 的多餘強制更新**：22:10 已寫入時，23:10 的強制更新是多餘請求，且會讓快取的 T 日列時間戳與帳內快照不同。請決定是否略過。
4. **補跑時段**：13:30～22:10 內補跑時，強制更新保證的只是「不早於 t0」，不是「已是最終收盤」，補跑越接近收盤被修正的機率可能越高（推論）。是否收緊為 ≥ 18:00 由 TA 決定。
5. **`lookback_days` 參數**：若函式連長度參數都不能有，需另置常數並以測試釘與 recorder 相等，或讓 `app.services` 反向 import recorder 常數（違反現有 K-2 方向）。請 TA 決定。
6. **實作前**：由 dev-lead 做，需先確認上面「未能查證」的前三項。qa 以 `git diff` 驗既有行零刪除。

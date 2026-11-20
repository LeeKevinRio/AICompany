# 指數強制更新方法規格（data-engineer，2026-11-19）

依據：tech-architect 定案 `work/reviews/2026-11-19-收盤定案時點重新定案與補充十-tech-architect.md`（補充十第 2、3 點、S-20a）。
全部只讀程式，沒有改任何產品程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有執行 `.bat`，沒有執行任何程式或測試。
路徑簡稱：`app/` = `/home/user/AICompany/apps/stock-desk/backend/app/`（主線）。`data/service.py`、`data/cache.py`、`services/index.py`、`data/freshness.py`、`data/providers/yfinance.py` 與先前讀的 worktree 版逐檔相同，行號沿用。

---

## 第 1 題：`price_bars_cache` 的全部寫入點

### 單一答案：前提「某一列之後只會被更晚的時刻覆寫」——嚴格說**不成立**，但例外只有一條，且不會讓「核對 `as_of ≥ t0`」放過不該放過的值。

分兩層講：

**A. 「每一個寫入點都以請求時刻寫 `as_of`」：成立。** 寫入點（`apps/stock-desk/` 全目錄，排除 `.venv`、`node_modules`、`__pycache__`、`tests/`；含 `app/`、`backend/scripts/`、`scripts/`、`README`、`compose.yaml`、各 `.bat`／`.sh` 文字，沒有 migration 檔會寫這張表）：

| # | 檔案:行號 | `as_of` 寫什麼 | `fetched_at` 寫什麼 | 在正式主 DB 會不會執行到 |
|---|---|---|---|---|
| W1 | `app/data/cache.py:215-228`（`PriceBarCache.put` 的 `INSERT … ON CONFLICT DO UPDATE`，**唯一的 SQL 寫入點**） | `bar.as_of.isoformat()`（第 207 行），即呼叫端交來的 bar 自帶的 `as_of`；`ON CONFLICT` 時 `as_of=excluded.as_of`（第 227 行）無條件覆寫，不比較新舊 | `moment`：參數 `fetched_at`，缺省 `datetime.now(UTC)`（第 194 行）；`ON CONFLICT` 時無條件覆寫（第 228 行） | 是，經 W2 |
| W2 | `app/data/service.py:353`（`MarketDataService.get_daily_bars` 內 `self._cache.put(result.bars, source=result.source, fetched_at=fetched_at)`；全 `app/` 內**唯一的非 demo 呼叫端**） | provider 回傳的 bar 自帶 `as_of`。對 `^TWII`：yfinance adapter 在 `get_index_daily_bars` 開頭取 `now = datetime.now(UTC)`（`data/providers/yfinance.py:478`），`_parse_row` 每列 `as_of=now`（第 745 行），所以是**請求發出前一刻**的時間 | `fetched_at = self._clock()`（`service.py:352`，回應收到後的服務時鐘，預設 `datetime.now(UTC)`，`service.py:264`）；**同一次呼叫內 `fetched_at ≥ as_of`** | 是。是 recorder、sector job、前端 API 共用的唯一寫入路徑。實例化點只有 `api/deps.py:125、135、178`（TW 股票、US 股票、指數；指數那個只有 yfinance 一個 provider） |
| W3 | `app/demo/seed.py:438`（`seed_demo` 內 `cache.put(list(bars), source=DEMO_SOURCE, fetched_at=moment)`） | `build_demo_bars(today=…, as_of=moment)`（`seed.py:425`、`demo/series.py:197-241`），`moment = as_of or datetime.now(UTC)`（`seed.py:424`）。參數 `as_of` 可注入，但 CLI 入口 `main` 呼叫 `seed_demo(cache=…, positions=…, alerts=…)` 沒傳 `as_of`（`seed.py:537-586` 內第 39 個相對行），所以 CLI 一律是執行當下 | `moment`（同上） | **不會對 `^TWII` 執行**：demo 的標的只有 `2330`、`0050`、`00631L`（`seed.py:108-114`），沒有任何 `^` 代碼；且 `seed_demo` 先 `find_foreign_bars`，遇到其他來源的同鍵列就整個拒絕（`seed.py:428-433`）。只在操作者手動執行 `python -m app.demo.seed`（`README.md:283-300`）時才發生，不在任何排程、啟動或 API 路徑上（grep `app/main.py`、`app/scheduler.py` 無 demo 引用） |

**沒有寫入但會改變列的操作（不影響 `as_of` 前提）**：`cache.py:532` `delete_by_source`（只刪列，並清 fetch／attempt log；呼叫端是 `demo/seed.py --reset`）。`cache.py:390` 只刪 attempt log。其餘 `backend/scripts/*.py`、`scripts/*.py`、`app/data/diagnose.py`、`app/backtest/event_study.py` 對這張表都是 `SELECT`（grep 全部 `price_bars` 配 `insert|update|delete|replace|executemany|executescript|ALTER|DROP` 只命中 `cache.py` 的上述幾行）。`tests/` 我不算（題目已排除；測試的 fixture 可寫任意 `as_of`，但不接觸正式主 DB）。

**B. 「某一列之後只會被更晚的時刻覆寫」：不成立，唯一例外是競態。**
- 機制：W1 是「最後寫入者勝」，不是「取 `as_of` 較大者」。`as_of` 是請求**發出**時刻、寫入發生在回應**收到**之後（W2 的 `fetched_at` 與 `as_of` 之間有網路與節流等待）。若兩個請求重疊（例如前端 `/api/signals` 在 t0 − 2 秒發出、慢回應；強制更新在 t0 發出、先回應並先寫入），後寫入的是較早請求的值，**這一列的 `as_of` 會被改回較早的時間（< t0）**。
- 為什麼兩個請求能重疊：scheduler 與 API 可以是不同行程（各自有 `lru_cache` 的服務與各自的 `RateLimitedClient`，節流 `min_interval_seconds=1.0`，`yfinance.py:422`，只在單一行程內有效）；SQLite 的 `busy_timeout` 5000 ms 只是等鎖，不保證順序（`cache.py:36、165`）。
- 在正式主 DB 上會不會發生：**會，但窗口很小**（要在 22:10～23:10 這段有人打開頁面、且該請求恰好在強制更新前後數秒內發出又晚到）。
- 影響：fail closed 的方向。scheduler 在強制更新之後核對 `B.as_of ≥ t0`：
  - 競態發生在核對**之前** → 核對失敗 → 不呼叫 recorder，與「強制更新失敗」同處理（補充十第 2 點）。
  - 競態發生在核對**之後、recorder 讀取之前**（視窗是 scheduler 核對到 recorder 的 `load_market_benchmark` 之間的毫秒級）→ recorder 會讀到 `as_of < t0` 的值，**核對放過了**。這是 TA 前提真正漏掉的洞，但值是「某個稍早於 t0 數秒的 Yahoo 回應」，且該時刻仍遠在 15:00 之後，D-3 第 2 點的定案定義照樣成立；它破壞的只是 G 的「不得早於 t0」這條新規則，不是定案定義。
  - 補救選項（由 TA 決定，我不自行改設計）：(a) 接受並寫入已知限制；(b) 核對改放在 recorder 讀取之後（TA 已否決，理由是改 `code_digest`）；(c) 用 service 層的單一寫入互斥（同行程內有效、跨行程無效，不能根治）。我傾向 (a)，並在補充十寫明。
- 另一個小注意：`t0` 由 scheduler 以 `datetime.now(UTC)` 取，`as_of` 由 adapter 以 `datetime.now(UTC)` 取，同機同時鐘；若系統時鐘在兩者之間被往回調（NTP step）會得到 `as_of < t0`，同樣 fail closed。

結論用字：**前提「成立」的部分**是「每個寫入點的 `as_of` 都是請求時刻」；**不成立的部分**是「之後只會被更晚時刻覆寫」，例外路徑只有「兩個行程的請求重疊導致最後寫入者較早」。demo seed 不是例外路徑（不寫 `^TWII`、不在排程上）。

---

## 第 2 題：強制更新方法規格

### 2.1 既有流程的位置（`app/data/service.py`）

| 步驟 | 行號 |
|---|---|
| 進入點 `get_daily_bars` | 294-436 |
| 不被收的標的拒絕 `_refuse_unadmitted` | 295-297（本體 488-508） |
| layer 0 呼叫 | 298-304（`_try_session_fresh_cache` 677-713 → `_layer_zero_answer` 715-853） |
| **cooldown 判斷（要略過的）** | layer 0 內：738-767（無快取）、768-796（無 coverage）、818-837（`REFETCH` 遇到失敗 attempt）、838-842；快取不被接受時的 cooldown 短路 705-712；判定函式 `data/freshness.py:79-86、154-188` |
| 決定抓取起點 | 316-318，`_incremental_start` 650-675 |
| ladder 迴圈 | 306-309、328-419 |
| 單一 provider 呼叫與盤中列丟棄 | `_try_provider` 886-939、`_without_unfinished_session` 941-957 |
| 幣別閘 | 334-351（`_judge_bars` 554-601） |
| **寫快取** | 352-353（`put`）、355（`record_attempt`）、357-394（增量時讀回合併）、400-403（`record_fetch`，僅 `result.complete`） |
| 全失敗後記 attempt | 423 |
| **回落到快取（新方法不得走）** | 424-436 → `_fall_back_to_cache` 959-1043 |

### 2.2 放哪裡、方法名、簽章、回傳型別

**放在 `MarketDataService` 內，緊接 `get_cached_bars`（第 486 行）之後新增，純新增、不動任何既有行。**

```python
@dataclass(frozen=True)
class LiveRefreshOutcome:
    ok: bool                       # a live provider answered, passed the gates, and its bars were written to the cache
    source: str | None             # source of the answering provider, None when not ok
    requested_at: datetime | None  # ProviderResult.as_of of the answering provider (request time)
    written_at: datetime | None    # the fetched_at passed to cache.put (self._clock())
    live_bar_count: int            # bars of the live answer after the unfinished-session drop
    live_latest_date: date | None  # newest bar date in that live answer, None when none
    complete: bool                 # ProviderResult.complete of the answer
    reason: str | None             # why not ok (provider reasons, joined as the ladder joins them); None when ok

def refresh_daily_bars_live(
    self, symbol: str, market: Market, start: date, end: date
) -> LiveRefreshOutcome: ...
```

- `LiveRefreshOutcome` 定義在 `data/service.py` 模組層（放在 `CurrencyLookupError` 後、約第 71 行之後）。
- 簽章只有範圍（日期），沒有時鐘或「as-of」參數；時鐘仍是建構時注入的 `self._clock`。
- `ok=True` 的定義只有一個：**走到 `service.py:353` 的 `put` 並完成寫入**（`result` 通過 `_try_provider`、通過幣別閘、有 bars）。回落到快取、被拒、全部 provider 失敗、`_without_unfinished_session` 之後沒有列，一律 `ok=False`，**不讀快取當答案**。
- 不改 `PriceService` Protocol（`portfolio/valuation.py:114-126`）；新方法由 `IndexSeriesService` 另開穿透（見 2.7）。

### 2.3 新方法的步驟（逐步，對應既有行）

1. `refused = self._refuse_unadmitted(symbol, market)`（重用，488-508）；非 `None` → `ok=False`，`reason` = 該結果的 `reason`。（指數路徑的 admission 是 `admit_any_shape`，一律放行。）
2. 唯讀取快取一次 `cached = self._cache.get(symbol, market, start, end, now=self._clock())`；若 `cached` 非空且 `self._cache_refuses(..., layer=<新標籤>, source=cached.source)`（重用 510-525）為真，`fetch_start = start`（整段重抓、覆寫被拒的列，與 316-318 的 `layer_zero_refused` 分支相同）；否則 `fetch_start = self._incremental_start(symbol, market, start, end)`（重用，650-675）。
   - 不呼叫 `_try_session_fresh_cache`（它含 cooldown 短路 705-712）。
   - `layer` 標籤：`_judge_bars` 的 `layer` 是 `str`（554-561），既有標籤 `provider`、`incremental_readback`、`layer0_cache`、`fallback_cache`、`cache_only`。新方法建議新標籤 `force_refresh`；我沒查有無測試釘死標籤集合（`tests/test_f9b_cache_currency_gate.py` 是候選），實作前 grep。
3. 對 `[self._primary, *self._backups]`（與 306-309 同序）逐一：
   - `result, reason = self._try_provider(provider, symbol, market, fetch_start, end)`（重用，886-939；盤中列丟棄與 provider 例外吞咽照舊）；`result is None` → 收集 `reason`，下一個。
   - `verdict = self._judge_bars(..., layer="provider", ...)`；非 `ok` → 同 337-351（`fetch_start = start` 的規則照搬），下一個。
   - 通過 → `fetched_at = self._clock()`、`self._cache.put(result.bars, source=result.source, fetched_at=fetched_at)`、`self._cache.record_attempt(symbol, market, at=fetched_at)`（照搬 352-355）。
   - 若 `fetch_start > start`，照搬 357-394 的讀回合併與增量讀回閘；讀回失敗 → 收集 `MERGE_READBACK_FAILED_REASON`、下一個 provider（注意：此時 `put` 已寫入，與既有行為相同）。
   - `result.complete` → `self._cache.record_fetch(symbol, market, start=start, end=end, fetched_at=fetched_at)`（照搬 400-403）。
   - 回 `LiveRefreshOutcome(ok=True, source=result.source, requested_at=result.as_of, written_at=fetched_at, live_bar_count=len(result.bars), live_latest_date=max(bar.date for bar in result.bars), complete=result.complete, reason=None)`。
4. 全部 provider 都沒成功：`self._cache.record_attempt(symbol, market, at=self._clock())`（照搬 423），回 `ok=False`、`reason=_combine_reasons(reasons)`（重用 136-147）。**不呼叫 `_fall_back_to_cache`、`_cached_result`、`_refused_answer`。**

### 2.4 重用與不可重用

- 可重用的私有方法：`_refuse_unadmitted`、`_cache_refuses`／`_judge_bars`、`_incremental_start`、`_try_provider`（內含 `_without_unfinished_session`）、`_refusal_sentence`（633-648，只在有 wording 時；指數路徑 `wording=None`）、模組函式 `_combine_reasons`、`mixed_sources_reason`。
- 不可重用：`_try_session_fresh_cache`、`_layer_zero_answer`（cooldown／coverage 短路）、`_fall_back_to_cache`、`_cached_result`、`_refused_answer`（會把快取或空答案包成成功形狀）。
- 重用 `_try_provider` 的後果要讓 TA 知道：`_without_unfinished_session` 以 `self._clock()` 決定 `latest_closed_session`（941-957）；22:10 時 T 日列保留，13:30 前 T 日列被丟。

### 2.5 怎麼保證既有路徑逐位元不變

- **做法**：只新增（一個 dataclass、一個方法、`IndexSeriesService` 一個穿透方法、`index.py` 兩個函式），不搬移、不改名、不改既有任何一行。我不建議把 306-419 抽成共用私有函式：抽取雖然語意相同，卻讓 `get_daily_bars` 本身出現在 diff 內，「逐位元不變」就要靠測試證明；純新增則 diff 一眼可證。代價是新方法複製約 50 行（步驟 2～4），日後兩邊可能漂移，用下面 T-EQ 測試守住。
- 既有測試守門（我確認存在的檔案；我沒執行）：`tests/test_service.py`（階梯與回落）、`tests/test_freshness.py`、`tests/test_session_calendar.py`、`tests/test_cache.py`、`tests/test_f9b0_service_scope.py`（AST 掃建構點，新方法不建構服務，不受影響）、`tests/test_f9b0_rejection.py`（AST 掃 `ProviderResult(..., rejection=...)`，**只允許 `data/service.py`**；新方法不得新增 `rejection=` 呼叫以外的產生處，且不在 `service.py` 之外）、`tests/test_f9b_cache_currency_gate.py`、`tests/test_f9b_live_currency_gate.py`、`tests/test_f9b0_index_currency_tripwire.py`、`tests/test_services_index.py`、`tests/test_services_index_bridge.py`、`tests/test_playbook_n190_*.py`、`tests/test_scheduler*.py`。新增檔案後這些必須全綠，且 `git diff` 對 `service.py`、`index.py` 的既有行零刪除。

### 2.6 取數範圍與涵蓋 T 日列

- recorder 的範圍：`forecast/recorder.py` 的 `_fetch`（約 664-676）：`run_date = now.astimezone(Asia/Taipei).date()`（668）、`start = run_date - timedelta(days=FETCH_CALENDAR_DAYS + FETCH_SLACK_DAYS)`（669；`FETCH_CALENDAR_DAYS=500`、`FETCH_SLACK_DAYS=31`，`recorder.py:145、148`，共 531 天）、`end = run_date`、呼叫 `load_benchmark(resolver, market=MARKET, start=start, end=run_date)`（670）。`now` 是 `store.now()`（`recorder.py:418`），即系統時鐘。
- 強制更新的範圍要與它**完全同公式**：`end` = 當下台北日期，`start = end − (FETCH_CALENDAR_DAYS + FETCH_SLACK_DAYS)`。理由：(1) layer 0 之後的 `coverage.covered_start <= start` 檢查（`service.py:768`）；強制更新若用較窄範圍，`record_fetch` 的 coverage 可能比 recorder 的 start 晚而使 recorder 的 layer 0 落入「無 coverage」分支（768-796）而再抓一次；用同公式就不會。(2) recorder 的 `end` 與強制更新的 `end` 只在跨午夜時可能不同，見 2.8。
- 實際向 Yahoo 要的範圍：`fetch_start = _incremental_start(...)`：有完整 coverage 時是「最後一根快取 bar 所在月的 1 日」（650-675），否則整段 `start`。`yfinance.py` 的 `period2 = end + 1 日`（`_request_chart_result`，約 641-660），所以含 T 日。T 日在最後快取 bar 之後，必然落在這個月或之後，**涵蓋 T 日列**；該月全部列（包含 T-1 等）的 `as_of`／`fetched_at` 都被這次覆寫。
- 範圍參數的來源：`end`／`start` 不由 scheduler 傳日期，見 2.7（函式自己讀系統時鐘算台北日期，scheduler 只傳「回看天數」這個長度，不是時間點）。

### 2.7 `app/services/index.py` 要新增的內容

1. `IndexSeriesService` 新增穿透方法（接在 `get_cached_bars`，第 213-217 行之後）：
   ```python
   def refresh_daily_bars_live(self, symbol: str, market: Market, start: date, end: date) -> LiveRefreshOutcome:
       return self._inner.refresh_daily_bars_live(symbol, market, start, end)
   ```
   `_inner` 型別是 `PriceService`（Protocol，沒有這個方法）；需要另宣告 `class LiveRefreshService(Protocol)`，`IndexSeriesService.__init__` 不改，穿透方法內以 `getattr` 檢查並在缺少時回 `ok=False`（reason 固定字串，英文，因為給 WARNING 用），不要改 `PriceService`。
2. 新函式（模組層，放在 `load_market_benchmark` 之後，第 412 行後、replay 區塊之前）：
   ```python
   @dataclass(frozen=True)
   class ForcedBenchmarkRefresh:
       live: LiveRefreshOutcome
       latest_cached_bar: PriceBar | None   # the newest-by-date bar the cache holds in the same range, read after the refresh
       reason: str | None                   # why latest_cached_bar is None, or why the refresh did not run

   def force_refresh_benchmark(
       resolver: IndexServiceResolver, *, market: Market, lookback_days: int
   ) -> ForcedBenchmarkRefresh: ...
   ```
   - **沒有 `now`、`as_of`、`start`、`end` 參數。** `lookback_days` 是長度不是時間點（scheduler 傳 `FETCH_CALENDAR_DAYS + FETCH_SLACK_DAYS`，它本來就 import recorder；`app.services` 不 import `app.forecast`，維持 K-2 方向）。若 TA 認為連 `lookback_days` 也不行，退而求其次是把 531 在 `index.py` 另設一個常數並以測試釘它與 recorder 相等；我不建議（兩處真相）。
   - 內部：`today = datetime.now(UTC).astimezone(ZoneInfo(TW_POLICY.timezone)).date()`（`TW_POLICY` 來自 `app.data.freshness`，與 recorder 同一個時區來源），`end = today`，`start = end - timedelta(days=lookback_days)`；`benchmark = MARKET_BENCHMARK.get(market)`（第 309-312 行）取得 `series_symbol`（`^TWII`）；`service = resolver.get(market)`，沒有或沒有穿透方法 → `live.ok=False` 並回，不抓任何東西。
   - 取得與 recorder 同一個實例：由呼叫端傳入 `get_index_resolver()` 的結果（`api/deps.py:377-379`，`_default_index_resolver` 是 `lru_cache(maxsize=1)`，同行程內是同一個 `IndexSeriesService` → 同一個 `MarketDataService` → 同一個 `PriceBarCache`、同一個 `YFinanceAdapter` 與節流）。`scheduler.py` 的 `run_forecast_record` 已是這樣傳給 recorder（`resolver=get_index_resolver()`）；強制更新要在**同一次 job 內用同一個呼叫取得的物件**（先 `resolver = get_index_resolver()`，兩邊共用同一變數）。
   - 步驟：呼叫 `service.refresh_daily_bars_live(symbol, market, start, end)`；`live.ok` 為真才讀回（唯讀）`service.get_cached_bars(symbol, market, start, end)`（`index.py:213-217` 既有穿透；`data/service.py:438-486`，無寫入、不打外網、過幣別閘），取 `max(bars, key=lambda b: b.date)`；任何一步失敗 → `latest_cached_bar=None` 與 `reason`。
   - 它不判斷 `as_of ≥ t0`（補充十：核對在 scheduler）；scheduler 比較 `latest_cached_bar.as_of >= t0`。
   - 回傳型別沒有任何標籤或預測值，沒有違反 D-4 第 3 點。

### 2.8 強制更新之後 recorder 立刻呼叫 `load_market_benchmark`：逐步走

假設 22:10 平日、t0 = 22:10:00、強制更新成功（Yahoo 回 T 日列）：
1. 強制更新寫入：T 日列（與該月其他列）`as_of ≈ 22:10:01`、`fetched_at ≈ 22:10:02`；`record_attempt`、`record_fetch(start, end=T, fetched_at=22:10:02)`；coverage 涵蓋 `[start, T]`，`last_fetched_at = 22:10:02`。
2. scheduler 讀回：`get_cached_bars` → 最新一根 T，`as_of = 22:10:01 ≥ t0` 通過。
3. recorder `_fetch`：`start' = run_date − 531`，與強制更新同日同公式，`start' = start`；`end' = run_date`。`load_market_benchmark` → `get_daily_bars` → layer 0（`_layer_zero_answer`）：
   - `coverage.covered_start <= start'` 成立（等於）。
   - `judge()`：`expected = min(latest_completed_session(22:10)=T, prev_weekday(run_date)=T) = T`；`last_bar = T ≥ T` → `HAS_LATEST_SESSION`。
   - 動不動第 806-817 行的「同市場已有 T+1」強制重抓：該分支條件含 `not policy.is_within_cooldown(now, coverage.last_fetched_at)`；剛抓完 22:10:02，在 1 小時內 → 不進入。即使進入，`later = T+1 > end` 也不成立。
   - → 服務快取，**不發出第二次 live 請求**（`service.py:843-853`），回 `CACHED_STALE` 加 `is_within_ttl=True`。
4. recorder 讀到的 T 日列 `as_of = 22:10:01`（快取欄位 `as_of`，`cache.py:586-598`），`fetched_at`（快照）= 同值（`outlook/inputs.py:160-171`）。因此**時間戳必為強制更新那一次或更晚的**——「更晚」只在 2.9 的競態下才會是「更早」，見第 1 題。
5. T 日列缺的情形（Yahoo 沒回 T，例如 null volume 被丟）：`live_latest_date = T-1`；快取最新一根 T-1，`as_of` 被該月覆寫 ≥ t0，scheduler 核對通過；recorder 的 layer 0：`last_bar = T-1 < expected T` → `judge` 先走 `is_within_cooldown` → `CHECKED_RECENTLY`；再檢查 `coverage.covered_end < expected`（838）：`covered_end = T` 不小於 → 不進 `return None` → **服務快取、不再抓**；recorder 看到最新定案 T-1，`has_record` 為真 → `no_new_session`。這個情形對操作者看起來與「T 還沒有資料」相同；scheduler 可從 `live.live_latest_date` 與 `latest_cached_bar.date` 小於「應有 session」自行判斷並在 log 提示（INFO，英文，無標籤），這是可見性建議，不改設計。
6. 跨午夜小邊界：scheduler 的 `end`（強制更新時）與 recorder 的 `run_date` 若跨 00:00 而不同日，recorder 的 `end' = T+1`：若 T+1 是平日，`expected = min(latest_completed(now)=T (00:xx < 15:00 取前一日), prev_weekday(T+1)=T+1)=T` 仍判 `HAS_LATEST_SESSION`；若 `start'` 比 coverage 的 `covered_start` 晚一天，仍滿足 `covered_start <= start'`。22:10、23:10 都在午夜前（正常情況不跨）；啟動補跑若剛好在 23:59 前後才可能，機率極低，記錄即可。

### 2.9 失敗模式與新方法的回報

| 情形 | 新方法行為 | `LiveRefreshOutcome` |
|---|---|---|
| Yahoo 不通（403、連線逾時、DNS） | adapter 回 `unavailable` 並帶 reason（`yfinance.py:660-664`；5xx 與 transport 錯誤由 `RateLimitedClient` 依固定退避重試，4xx 不重試，`data/http.py:149-160`）；`_try_provider` 回 `(None, reason)`；`record_attempt`（照搬 423） | `ok=False`，`reason` = provider 句子，`source=None` |
| 回空（查無資料、`result` 為空列） | `_try_provider` 931-938 視為被拒的 rung | `ok=False` |
| T 日列因 OHLCV 任一為 null（含 volume）被 `_parse_chart_row` 丟掉（`yfinance.py:301-307`，無 log） | 其餘列照常寫入 | `ok=True`，`live_latest_date < T`（不是 `ok=False`；呼叫端用日期看出） |
| `_without_unfinished_session` 丟掉晚於最近已收盤 session 的列 | 22:10 通常不丟 T；13:30 前會丟 T | 全丟光 → `ok=False`（沒有 bars）；只丟部分 → `ok=True`，`live_latest_date` 較早 |
| 幣別閘拒絕（`_judge_bars` 非 `ok`） | 該 rung 被拒；指數路徑 `fetch_start = start` 之後下一個 rung（337-351） | 無其他 rung → `ok=False` |
| 有其他 provider 可回落 | **指數沒有第二個 provider**：`api/deps.py:178-186` 只有 `primary=IndexProviderBridge(...)`、沒有 `backups`；Alpha Vantage 明確不在指數路徑（`index.py` 約 160-188、`deps.py:155-166` docstring）。新方法仍按 ladder 序走，若將來加了 backup 且主來源失敗、備援成功，`ok=True`、`source` 為備援名，**呼叫端必須看 `source`**；建議 scheduler 目前只接受 `source` 等於 yfinance 的 `source_id`，否則視為核對失敗（這是 TA 決定的政策，我只提出） | 視備援結果 |
| 增量讀回合併失敗（`MERGE_READBACK_FAILED_REASON`） | 已寫入的列保留（既有行為同），該 rung 視為失敗 | `ok=False` |
| `complete=False`（部分答案） | yfinance 指數路徑預設 `complete=True`；若為 False 照搬 404-410，不記 coverage，仍寫入 | `ok=True`，`complete=False` |
| provider 丟例外 | `_try_provider` 吞下並記錄（886-929） | `ok=False` |

任何 `ok=False` 都不得被呼叫端當成成功沿用快取（補充十第 2 點）。

### 2.10 對其他使用者的副作用

- **cooldown 狀態**：強制更新成功 → `record_attempt`、`record_fetch` 寫新的 `last_fetched_at`（約 22:10）→ 之後 1 小時內其他呼叫看到的是 `HAS_LATEST_SESSION` 或 `CHECKED_RECENTLY`，一律走快取，不另外打 Yahoo。強制更新失敗 → 只寫 `last_attempt_at`（晚於上次成功）→ 1 小時內任何走到 `REFETCH` 的呼叫會服務快取並附 `RECENT_ATTEMPT_FAILED_REASON`（`service.py:824-837`），**不會**因此多打 Yahoo；這與既有失敗行為一致。
- **17:45 的 sector job**：次日 17:45 的判斷不受影響（昨晚的 `last_fetched_at` 早已超過 1 小時 cooldown）。它仍會在 17:45 自己抓並蓋 `as_of=17:45`，22:10 的強制更新再把該月（含 T）蓋成 22:10。sector job 本身讀到的值與時間戳在 17:45 當下不變；22:10 之後才讀到的人（前端夜間開頁面、23:xx）會看到較新的值與 `as_of`。
- **前端頁面**：22:10 之後打開 `/api/signals`、`/api/playbook/today` 會讀到強制更新後的值（若 Yahoo 在 17:45～22:10 之間修正了 T 日列，使用者在 22:10 前後看到的 T 收盤可能不同）；`staleness_minutes` 重新計算。這是事實面變化，沒有新增使用者面文字，不涉及風控審查範圍，但我建議 TA 知道。
- **時間戳覆寫的副作用**：該月所有列的 `as_of`／`fetched_at` 被重蓋；既有取證腳本（`backend/scripts/unfinished_bar_probe.py`、`n177_n190_backtrack_probe.py`）依賴 `fetched_at` 看「哪些列在收盤前抓過」，其證據價值本來就會被任何重抓覆寫（它們自己的註解已寫明，`n177_n190_backtrack_probe.py:341`），不是新問題。
- **rate limit**：每個平日 22:10、23:10（若 22:10 失敗才會有 23:10 的強制更新；成功則 23:10 仍會再做一次，因為 TA 設計是「每次執行先強制更新」）、啟動補跑 1 次，每天最多 +3 個 Yahoo 請求，且每個請求是單一 `^TWII` 的單次 chart 呼叫；adapter 單行程節流 1 秒（`yfinance.py:422`）、重試固定 1/2/4 秒退避。Yahoo 無文件化的限額（`yfinance.py` 註解自承），這個量級遠低於 UI 白天 `/api/signals` 的呼叫量，**沒有問題**。補一個提醒：23:10 在 22:10 成功且 recorder 已寫入時，強制更新是多餘的請求（`no_new_session` 的情況）；可由 TA 決定是否在 recorder 已完成當日時略過，我不改設計。

### 2.11 建議的測試清單（全部離線，不打外網）

放在新檔 `tests/test_service_force_refresh.py`、`tests/test_services_index_force_refresh.py`；用 `MarketDataService` 的注入點（假 provider、`:memory:` 或 `tmp_path` 的 `PriceBarCache`、假 `clock`），如 `tests/market_service_helpers.py` 的既有做法（我只確認檔案存在，沒讀內容）；yfinance 契約測試用既有 `httpx.MockTransport` 與合成 fixture（`tests/test_providers_yfinance.py` 的做法）。

單元（service）
1. T-S1 略過 layer 0：快取已有 `HAS_LATEST_SESSION` 的最新 session、coverage 完整、cooldown 內；`refresh_daily_bars_live` 仍呼叫 provider 一次（計數）。
2. T-S2 略過 cooldown：先令 `record_attempt`／`record_fetch` 在 5 分鐘前；仍呼叫 provider。
3. T-S3 寫入：成功後快取 T 日列 `as_of` = provider 的 `as_of`、`fetched_at` = 注入時鐘；`record_fetch` coverage 涵蓋 `[start, end]`；`ok=True`、`written_at`、`requested_at`、`live_latest_date` 正確。
4. T-S4 回落不算成功：provider 失敗、快取有資料 → `ok=False`、快取未被讀成答案、`record_attempt` 被記、`reason` 非空。
5. T-S5 `_without_unfinished_session`：時鐘 13:00 時 provider 回含 T 日列 → T 日列不入快取；時鐘 22:10 保留。全部被丟 → `ok=False`。
6. T-S6 增量起點：快取有完整 coverage 與 T-1 → provider 被要求的 `start` 為 T-1 所在月 1 日（斷言 `fetch_start`）；無 coverage → 整段 `start`。
7. T-S7 幣別閘：provider 回他國幣別 → `ok=False`，不寫快取，不 `record_fetch`。
8. T-S8 讀回合併失敗 → `ok=False`。
9. T-S9 provider 例外 → `ok=False`，不拋出。
10. T-S10 `complete=False` 不記 coverage。
11. T-S11 快取被幣別閘拒絕時整段重抓（`fetch_start = start`）。
12. T-S12 沒有 `rejection=` 的新 `ProviderResult` 產生處（既有 `test_f9b0_rejection.py` 守門，需仍綠）。

等價與守門
13. T-EQ：同一組假 provider、同一份起始快取，分別執行 (a) `get_daily_bars` 且 layer 0 必須落到 ladder（快取為空）與 (b) `refresh_daily_bars_live`；斷言快取列、`price_bars_fetch_log`、`price_bars_attempt_log` 內容逐欄相同。守住複製的 ladder 不漂移。
14. T-REG：對 `get_daily_bars` 的既有行為不加新測試，但跑整個 `tests/test_service.py`、`test_f9b*`、`test_freshness.py`、`test_cache.py`、`test_services_index*.py` 全綠；`git diff` 驗 `service.py`／`index.py` 既有行零刪除。

單元（index）
15. T-I1 `force_refresh_benchmark`：假 resolver（`IndexSeriesService` 包假服務）→ 以 `MARKET_BENCHMARK["TW"].series_symbol` 呼叫、範圍 `end = 台北今日`、`start = end − lookback_days`（用凍結時鐘或注入的假服務記錄參數；不得有 `now` 參數，AST 或 `inspect.signature` 斷言）。
16. T-I2 讀回：`ok=True` 後回傳的 `latest_cached_bar` 是日期最大的一根，其 `as_of` 來自快取。
17. T-I3 失敗：服務缺穿透方法、`ok=False`、讀回為空 → `latest_cached_bar=None` 與 `reason`；不拋例外。
18. T-I4 市場無 benchmark／無服務 → 不呼叫任何東西。
19. T-I5 不存在任何 `price_bars_cache` 以外的 side effect：不寫 recorder 的表（以 `app/forecast`、`app/outlook` 不含新識別字的既有 AST 測試守門，`ADR-0030 D-3 第 5 點`）。

契約／整合（離線）
20. T-C1 強制更新後呼叫 `load_market_benchmark`：用 2.8 的情境（22:10、T 日列由假 provider 回）斷言第二次 provider 呼叫數為 0、recorder 讀到的 T 日 `as_of ≥ t0`。
21. T-C2 T 日列缺（假 provider 不回 T）：強制更新 `ok=True`、`live_latest_date = T-1`；後續 `load_market_benchmark` 不再抓（呼叫數 0）。
22. T-C3 競態：以假 provider 在強制更新寫入後，人為用較早 `as_of` 再 `cache.put` 同一列，斷言最後讀到的 `as_of` 是較早者——這個測試的目的是把第 1 題的例外路徑釘成文件化的已知行為，不是要求修正。
23. T-C4 scheduler 側（TA／dev-lead 實作時）：強制更新失敗或核對失敗 → 不呼叫 recorder、`forecast_run` 未寫、log 一行固定英文 WARNING；核對成功 → 呼叫 recorder 一次。這屬 `tests/test_scheduler*.py`。

---

## 第 3 題：我認為 TA 的設計在資料面做不到或有風險的地方（請轉回 TA，我不自行改設計）

1. **前提「某一列之後只會被更晚的時刻覆寫」不嚴格成立**（第 1 題 B）。`cache.put` 是最後寫入者勝，`as_of` 是請求發出時刻而非寫入時刻；兩行程請求重疊時，`as_of` 可能被較早的請求改回。後果：scheduler 核對與 recorder 讀取之間有毫秒級窗口，`B.as_of ≥ t0` 的保證可能被打破，但值仍是 22:10 前後數秒的 Yahoo 回應，且 15:00 之後，D-3 第 2 點照樣成立。建議在補充十明寫為已知限制，而不是宣稱「recorder 讀到的時間戳不可能早於 t0」。
2. **核對只檢查「日期最大的一根」**：T 日列缺（null volume、Yahoo 不給）時，T-1 在同月被重寫，核對通過，recorder 回 `no_new_session`，沒有任何可見異常（無 `inputs_not_ready`）。這與補充十第 2 點「強制更新失敗 → 不呼叫 recorder、進 F-2 分子」不同：這個情形是「強制更新成功但 T 缺」。建議 scheduler 至少用 `live_latest_date` 與 `TW_POLICY` 的 `latest_completed_session` 比對並 log；是否要算進 F-2 分子由 TA 決定。
3. **「重抓一次」的既有限制沒有被 G 解決，只是被迴避**：recorder 第 421-425 行的第二次 `_fetch` 仍讀同一份快取；G 讓它在正常情況下不會觸發（強制更新之後所有 T 日列 `as_of ≥ t0 ≥ 22:10`），但若競態或其他寫入把 T 日列改成 15:00 前的時間戳，recorder 仍會 `inputs_not_ready`，沒有救援路徑。補充十已列為已知限制，這裡只是確認。
4. **23:10 的強制更新在 22:10 已成功寫入時是多餘請求**，且會用 23:10 的值覆寫快取；對帳無影響（`has_record` 擋住），但快取的 T 日列時間戳與帳內快照的時間戳不再相同，日後人工對照時要知道這件事。
5. **啟動補跑 13:30～22:10 的時段限制與強制更新的互動**：補跑落在 15:00～18:00 時，強制更新會把 T 日列蓋成補跑當下的值並被 recorder 採用，寫入 `late = 0`；補充十的 G 保證的是「不早於 t0」，不是「已是最終收盤」。這與 TA 已接受的已知限制（Yahoo 22:10 的值是否最終無法查證）同類，但補跑時段內的值離收盤更近、被修正的機率可能更高（這是推論，環境無法驗證）。若要更保守，補跑時段可再限制為 ≥ 18:00；那是 TA 的決策。
6. **`force_refresh_benchmark` 的 `lookback_days` 參數**：若 TA 要求函式完全沒有時間類參數，需在 `index.py` 另置常數或讓 `app.services` 反向 import recorder 的常數（違反目前的 import 方向），請 TA 決定。
7. **測試實作前需確認兩件我沒讀到的事**：`_judge_bars` 的 `layer` 標籤是否被既有測試釘成固定集合；`tests/market_service_helpers.py` 提供的假 provider 與時鐘注入方式是否足以支援 T-EQ。

## 驗證摘要

- 讀過／grep 的範圍：`apps/stock-desk/` 全目錄（排除 `.venv`、`node_modules`、`__pycache__`、`tests/`）的 `price_bars`、`PriceBarCache`、`.put(`、`MarketDataService(`、`demo.seed`；`app/data/cache.py`、`app/data/service.py`（173-1050，並重讀 294-436、510-601、650-957）、`app/data/http.py`、`app/data/providers/yfinance.py`、`app/services/index.py`、`app/api/deps.py`、`app/demo/seed.py`、`app/demo/series.py`、`app/forecast/recorder.py`、`app/scheduler.py`、TA 文件的結論與 R-3；既有測試只確認檔名與 AST 守門內容（`test_f9b0_service_scope.py`、`test_f9b0_rejection.py`）。
- 沒有執行任何程式或測試；全部路徑推演（2.8、2.9）屬推論。
- 未能查證：react-query 自動重抓行為；Yahoo 在各時點是否回 T 日列；`layer` 標籤是否被測試固定；`test_scheduler*.py` 內有無釘住 `run_forecast_record` 的呼叫序列。

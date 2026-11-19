# 收盤定案時點與啟動補跑路徑（data-engineer，2026-11-19）

範圍：ADR-0030 待決事項「Yahoo 收盤 15:00～18:00 是否定案；成交量為空的列在快取路徑上怎麼處理」，加上協調者追加的優先題 (i)。
讀的程式：`/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/`（簡稱 `app/`）。
`services/index.py`、`data/cache.py`、`data/service.py`、`data/freshness.py`、`data/providers/yfinance.py`、`data/session_calendar.py`、`outlook/inputs.py` 與主線逐檔 diff 相同。`scheduler.py` 在該 worktree 有未 commit 的修改（`git diff --stat` 顯示 65 增 15 減，內容是 forecast_record 的目標 DB 檢查），所以下列 `scheduler.py` 行號是我讀取當下工作樹的行號，與 HEAD 不同。

---

## 0. 優先題 (i)：22:10 的 T 日 bar，`min(as_of, fetched_at)` 會不會落在 15:00～18:00？

### 單一答案：可能。

最短路徑（以下推導只靠讀程式，我沒有實際執行）：

1. 平日 T 日，15:00 之後、17:45 之前，沒有任何人抓過 `^TWII`；快取裡 `^TWII` 最新一根是 T-1（前一晚 22:10 recorder 留下的）。
2. 17:30 的 `pit_snapshot_capture`（`scheduler.py` `SECTOR_JOBS_HOURS="17,19,21"`、`PIT_CAPTURE_MINUTE=30`，約第 190～191 行）若成功，`market_store.last_ok_session("bars")` 為 T（`data/market_panel.py:764-772`）。
3. 17:45 的 `sector_board_refresh`（`SECTOR_REFRESH_MINUTE=45`，約第 192 行）進 `SectorBoardService._refresh_board(t=T)`（`services/sector_board.py:399-415`），呼叫 `self.reference_taiex(window[0], t)`，也就是 `taiex_reference_return(start, end=T)`（`scheduler.py:469-481`），再呼叫 `load_market_benchmark(get_index_resolver(), market="TW", start, end=T)`（`services/index.py:359-412`）。與 recorder 用的是同一個 resolver、同一個 `MarketDataService`、同一份快取（`api/deps.py:149-190`，`cache_first=True` 在第 181 行；recorder 傳入點 `scheduler.py` 的 `run_forecast_record`，約第 715～721 行）。
4. `MarketDataService.get_daily_bars`（`data/service.py:294`）第一步是 layer 0（`_try_session_fresh_cache` 677-713 → `_layer_zero_answer` 715-853）：現在 17:45 ≥ `TW_POLICY.publish_cutoff` 15:00，`expected_session = min(latest_completed_session(now), prev_weekday(end)) = T`（`data/freshness.py:88-94、191-193`）；快取最後一根是 T-1 < T；上次成功抓取是昨晚，超過 `recheck_cooldown` 1 小時 → `judge()` 回 `REFETCH`（`freshness.py:154-188`）→ 進 ladder，打 Yahoo。
5. Yahoo 回來的 T 日列，`PriceBar.as_of` 是 adapter 發請求當下的 `datetime.now(UTC)`（`data/providers/yfinance.py` 的 `get_index_daily_bars` 464-512 取 `now`、`_parse_row` 第 745 行 `as_of=now`），即約 17:45。`service.py:352-353` 以 `self._clock()` 為 `fetched_at` 寫入快取（`cache.py:177-231`），兩者都約 17:45。
6. 19:45、21:45 的 sector job 與 22:10 的 recorder：現在 ≥ 15:00，`expected = T`，快取最後一根 = T → `HAS_LATEST_SESSION`（`freshness.py:179-180`）。唯一會讓它改成重抓的分支是「另一條 TW 序列已有 T+1 的 bar」（`service.py:806-817`），但 `later = next_weekday(T) > end` 不成立，所以**不重抓、直接沿用快取**（`service.py:843-853`）。
7. recorder 讀到的 T 日 bar：`cache.get`（`cache.py:535-618`）把欄位 `as_of`（17:45）原樣放進 `PriceBar.as_of`；`outlook/inputs.py:160-171` 的 `_snapshot_bar` 把 `fetched_at` 也設成 `bar.as_of`。所以快照 `bars_json` 裡 T 日 bar 的 `as_of = fetched_at ≈ 17:45`，`is_final` 為真（17:45 ≥ 15:00），寫入 T 的 `late = 0` 紀錄，`inputs_max_fetched_at` 也是 17:45。

白話：只要 17:30 的 capture 讓 sector job 的 `t` 等於 T，17:45 就是當天第一個抓 `^TWII` 的人，22:10 的 recorder 用的就是 17:45 的 Yahoo 值，而 ADR D-3 第 2 點在 15:00 之後都算定案。這不是例外情形，是 sector job 開著時的常態路徑。

**這個答案取決於、而我沒有讀到或無法證實的東西**：
- (a) 17:30 capture 是否通常讓 `last_ok_session("bars")` 變成 T：我沒讀 `capture_pit_snapshot`，只讀了 `last_ok_session` 的查詢。若 capture 失敗，`t = T-1`，`end = T-1`，17:45 的 `expected = T-1`，快取已有 → 不抓。這種情況下 22:10 的 recorder 自己第一個抓，stamp 為 22:10（乾淨）。
- (b) 就算不靠 sector job，下面 B 項列的前端呼叫點（白天開頁面）也有同樣效果。
- (c) Yahoo 在 17:45 回的 T 日值是否已是最終值：這個環境連不到 Yahoo，無法查證（見第 1 節）。

### 15:00 之前抓進快取的 T 日 bar，22:10 會不會沿用？

- 盤中（13:30 前，例如 10:00 啟動）：**不會被存進快取**。`MarketDataService._try_provider` 呼叫 `_without_unfinished_session`（`service.py:930、941-957`），丟掉日期晚於 `latest_closed_session(now)` 的 bar；13:30 前 `latest_closed_session` 是前一個平日（`freshness.py:96-111`，`session_close=13:30`）。所以 10:00 的 T 日盤中 bar 在進快取前就被丟棄，recorder 看不到它。
- 13:30～15:00 之間（例如 13:35）若真的發生了一次 live 抓取：T 日 bar 會被保留並寫入快取，`as_of` 約 13:35（早於 15:00）。**會被 22:10 沿用**：22:10 時 `expected = T`，快取最後一根 = T → `HAS_LATEST_SESSION`，不重抓。recorder 讀到 T 日 bar 的 `as_of` 13:35 < 15:00 → 非定案；22:10 屬 `now ≥ cutoff`，recorder 第 421～425 行「重抓一次」，但那次「重抓」仍走 `load_market_benchmark` → layer 0 → 同一份快取，回同一根 → 仍非定案 → `inputs_not_ready`，不寫 T 的紀錄。23:10 重試同樣結果。這個 13:35 的舊值要到 T+1 的 15:00 之後才會因 `REFETCH` 被覆寫，那時 T+1 變成最新定案 bar，T 的紀錄永遠缺。
- 13:30～15:00 要真的發生 live 抓取，需要 layer 0 判 `REFETCH`：此時 `expected = T-1`、快取有 T-1，通常是 `HAS_LATEST_SESSION` 不抓；觸發條件只有 (1) 快取為空或 `coverage.covered_start > start`（`service.py:768-796`）、(2) 同市場另一條非 demo 的 TW 序列已有 T 日 bar（`cache.market_has_session`，`cache.py:358-378`，`service.py:806-817`），例如持股的 TWSE 日線在 14:00 被抓進快取。所以這是罕見路徑，但存在。

---

## 一、TTL 與「用快取／重抓」的完整邏輯

**沒有時鐘 TTL。** 指數路徑的規則是 ADR-0009 的 session 規則（`data/freshness.py` 模組 docstring 第 1～43 行：時鐘 TTL 被明確取代）。常數（`freshness.py:129-134`）：

| 常數 | 值 | 意義 |
|---|---|---|
| `TW_POLICY.publish_cutoff` | 15:00 Asia/Taipei | 此時間後，當天視為「已發布」（註解自承是未查證的保守假設，`freshness.py:123-128`） |
| `TW_POLICY.recheck_cooldown` | 1 小時 | 兩次都「沒有更新的」live 檢查之間最小間隔 |
| `TW_POLICY.session_close` | 13:30 | 此前當日 bar 視為盤中 |

邏輯（`MarketDataService.get_daily_bars`，`service.py:294-436`）：
1. `_refuse_unadmitted`（指數路徑無限制，`deps.py:184`）。
2. `cache_first` 為真（`deps.py:181`）→ layer 0（`service.py:677-853`）：
   - 快取無資料：若「上次 attempt 比上次成功晚、且在 cooldown 內」→ 回 UNAVAILABLE 並說明；否則進 ladder（738-767）。
   - 無 coverage 或 `covered_start > start`：同樣只有 R-8 例外（上次失敗 attempt 在 cooldown 內）才吃快取；否則進 ladder（768-796）。
   - 其餘：`judge()`（`freshness.py:154-188`）= `last_bar_date >= expected_session` → `HAS_LATEST_SESSION`；否則 `last_checked_at` 在 1 小時內 → `CHECKED_RECENTLY`；否則 `REFETCH`。
   - 唯一「多抓」的補充：`HAS_LATEST_SESSION` 且超過 cooldown，若同市場已有 T+1 的 bar 才強制 `REFETCH`（806-817）。
   - 判 `REFETCH` 時，若上次 live attempt 比上次成功晚且在 cooldown 內（來源正在壞），改回快取並標失敗原因（824-837）。
3. ladder：`_incremental_start`（650-675）：有完整 coverage 時，只向 Yahoo 要「最後一根快取 bar 所在月份的 1 日」起的段（recorder 的 start 是 `run_date − 531` 天，`recorder.py:668`）。
4. `_try_provider`（886-939）呼叫 adapter，再 `_without_unfinished_session` 丟掉盤中 bar。
5. 成功 → `cache.put(bars, source, fetched_at=self._clock())`（352-353）、`record_attempt`（355）、完整答案才 `record_fetch`（400-403），回傳的是「快取頭 + live 尾」讀回的合併序列（357-394）。
6. 全部失敗 → `_fall_back_to_cache`（959-1043），回 `CACHED_STALE` 並附原因。

## 二、每根 bar 的 `as_of`／`fetched_at` 怎麼寫、怎麼更新

- adapter：同一次請求回來的**所有**列，`as_of` 都是這次請求的 `now`（`yfinance.py:745`），包含舊的列。
- `cache.put`（`cache.py:177-231`）：`INSERT … ON CONFLICT(symbol, market, trade_date) DO UPDATE SET open, high, low, close, volume, currency, source, as_of, fetched_at = excluded.*`（219-228）。無條件覆寫，不比較值：**同一根 bar 抓到相同值，`as_of` 與 `fetched_at` 照樣被更新**。
- 範圍：只覆寫這次請求回來的列。因增量起點是最後快取 bar 所在月份的 1 日（`service.py:675`），所以「最新那個月」整段每次都被重寫並重蓋時間戳；更早的月份保留原時間戳。
- `cache.get`（535-618）回傳的 `PriceBar.as_of` 是欄位 `as_of`；`fetched_at` 欄位只用來算 `staleness_minutes`（604-611），`PriceBar` 沒有 `fetched_at`。
- 因此 recorder 快照裡的 `fetched_at` 不是快取的 `fetched_at` 欄位，而是欄位 `as_of`（`outlook/inputs.py:160-171`、檔頭 36-41 行註解自述）。它是「最後一次覆寫該列的那次請求的發出時間」。ADR D-3 第 2 點的「`as_of` 與 `fetched_at` 取較早者」在這條路徑上是同一個值取 min，不是兩個獨立來源。

## 三、會觸發 `^TWII` 抓取的呼叫點

只有兩種 symbol 形態進同一個 resolver（`api/deps.py:149-190`）：`load_market_benchmark(market="TW")` 與 `load_index_bars`（`00675L`、`00676R` 對應 `^TWII`，`leverage/index_mapping.py:245-262`）。所有呼叫點：

| 呼叫點 | 觸發時刻 | 位置 |
|---|---|---|
| recorder `forecast_record` | 平日 22:10、23:10、啟動後 3 分鐘 | `scheduler.py` `run_forecast_record`；`FORECAST_RECORD_TIMES`、`FORECAST_RECORD_STARTUP_DELAY`（約 208 行起）；`recorder.py:664-676` |
| sector board 的 `taiex_reference_return` | 平日 17:45、19:45、21:45（`refresh_board`），並在啟動後 2 分鐘補跑一次 `sector_board_refresh`（`SECTOR_REFRESH_STARTUP_DELAY`）；另 PIT capture 17:30/19:30/21:30 之後串接 refresh（我沒讀 capture 的串接細節：docstring 稱 start-up capture 有 chained refresh，見 `scheduler.py` `SECTOR_REFRESH_STARTUP_DELAY` 註解） | `scheduler.py:469-481`；`services/sector_board.py:399-415`；end = `t`（已完成的 session） |
| `GET /api/signals/{symbol}?market=TW` | 前端打開持股頁時；有自己的 bars 才抓基準 | `api/signals.py:108`；前端 `frontend/app/lib/queries.ts:210`（`getSignals`），`lookback_days` 預設 540；`end = date.today()`（容器 `TZ=Asia/Taipei`，`compose.yaml` 第 15、38 行） |
| `GET /api/leverage/{symbol}` | 前端打開槓桿 ETF 章節時（00675L / 00676R 才會對到 `^TWII`） | `api/leverage.py:98` |
| `GET /api/playbook/today` 與 `POST /api/playbook/settle` | 前端開排程台頁面時；`evaluate_today` 與 `_settle_pending` 都可能呼叫 `_load_index_bars` | `playbook/service.py:1503-1512、1963、2160、2324`；`api/playbook.py:581、613`；前端 `queries.ts:420`；`today` 是 UTC 日期（`service.py` `evaluate_today` 第 27 行），在台北 15:00～23:59 與台北日期相同 |
| 啟動預熱 `data_refresh` | 啟動時、平日 15:10、16:30、18:30 | **不抓 `^TWII`**：`refresh_market_data` 只處理持股（`scheduler.py` `refresh_market_data`），已讀確認 |
| `pit_snapshot_capture` | 平日 17:30、19:30、21:30 與啟動 | 我沒有讀到它抓 `^TWII`；grep 整個 `scheduler.py` 只有 `taiex_reference_return` 與 `run_forecast_record` 兩處引用指數 loader |

前端白天被打開會不會觸發抓取並寫進同一份快取：**會**，路徑是 `queries.ts` 的 `queryFn` → `/api/signals`、`/api/playbook/today` → `load_market_benchmark` → 同一個 `MarketDataService` → 同一份 `price_bars_cache`（key = `^TWII`／`TW`／日期）。能不能實際打到 Yahoo，仍要先過 layer 0：15:00 之前 `expected = T-1`，通常吃快取；15:00 之後第一個呼叫者若看到快取缺 T 就 live 抓。我沒有讀 react-query 的 refetch 設定（自動重抓頻率），只確認 `queryFn` 存在且頁面開啟時會呼叫。

---

## 1. 事實題：Yahoo `^TWII` 在 15:00～18:00 是否已定案、是否等於官方收盤

### 結論：無法查證。

這個環境連不到 Yahoo，而且 sandbox 時間已是 2026-11-20 00:14（台北），當日 15:00～18:00 的取樣窗口已經過了，即使連得到 Yahoo 也無法補採當天的窗口值。

### 實際嘗試

| 端點 | 結果 |
|---|---|
| `https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?range=5d&interval=1d` | `curl: (56) CONNECT tunnel failed, response 403`（代理拒絕，一次） |
| `https://query2.finance.yahoo.com/v8/finance/chart/%5ETWII?range=5d&interval=1d` | 同上，403（一次） |
| `https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=20261101&response=json` | HTTP 200，`stat=OK`，欄位 日期／開盤／最高／最低／收盤指數 |
| `https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=20261101&response=json` | HTTP 200，`stat=OK`，欄位 日期／成交股數／成交金額／成交筆數／發行量加權股價指數／漲跌點數 |

沒有再重試，也沒有要求放寬網路。

### 這個環境能驗到什麼

- 能驗到的：證交所兩個端點可連（與我先前報告「官方站連不到」不同，這次可連）。11 月份 14 個交易日，`MI_5MINS_HIST` 收盤與 `FMTQIK` 發行量加權股價指數**逐日完全相同**（腳本比對，0 筆不一致）。2026/11/19（民國 115/11/19）官方收盤 38,426.89；該日 OHLC 為 40,145.73／40,315.53／38,259.70／38,426.89；成交股數 15,301,049,840（取自 FMTQIK）。這些是台北 00:14 取得的值，**此時間點已在當日收盤之後約 10 小時，不代表 15:00～18:00 當時的值**。
- 驗不到的：(1) Yahoo 任何時點的值；(2) 官方站在 15:00～18:00 何時首次出現當日列（回應標頭只有 `Date`，沒有 `Last-Modified`，無法推出發布時間）；(3) Yahoo 的 `volume` 單位是否與 TWSE 成交股數可比（repo 內 `tests/fixtures/yfinance_chart_twii.json` 是合成的，volume 全為 0，`work/research/2026-11-19-對沖PRD三題回覆-data-engineer.md` 已記，不能當證據）。
- 我沒有用記憶中的「Yahoo 通常 xx 時定案」填空。

### 最小取樣方案（只寫方法，由 CEO 或有網路的環境執行）

目的：決定「Yahoo `^TWII` 的 T 日列最早在哪個時點起，與官方最終值一致且之後不再變」。

- **取樣時點（台北時間，T 日）**：13:45、14:30、15:05、15:30、16:30、17:30、18:05、21:00；加一個對照點 T+1 日 08:30（視為最終）。共 9 次 Yahoo 請求／日。
- **請求形狀**：與 adapter 相同，`period1=<T-5 日 UTC 零時>&period2=<T+1 UTC 零時 + 86400>&interval=1d`（`yfinance.py:641-660`），不要用 `range=5d`，因為 adapter 的日期是由 timestamp 的 UTC 日期推出（`yfinance.py:273-280`）。每次存原始 JSON 與抓取時刻（含時區）。
- **每次比對的欄位**：T 日那一列的 `timestamp`（原始值與推出的 UTC 日期是否等於 T）、`open`、`high`、`low`、`close`、`volume`（是否為 null、是否為 0），以及 `meta.regularMarketPrice`、`meta.regularMarketTime`、`meta.exchangeTimezoneName`、`meta.gmtoffset`；同時存 T-1 日那一列（看有沒有被連帶更動）。
- **官方基準**：T+1 日 08:30 之後抓 TWSE `MI_5MINS_HIST`（開高低收，2 位小數）與 `FMTQIK`（收盤與成交股數）。另在 15:05、16:30、18:05 也抓一次 TWSE，記錄官方列何時出現。
- **「已定案」判準**（逐時點、逐日判定）：該時點 Yahoo 的 T 日 `open/high/low/close` 與 TWSE 官方四個值以十進位字串逐一**完全相等**（不做四捨五入容差），且 `close` 與 T+1 08:30 的 Yahoo 值相等；`volume` 另判（單位不同時，只判「與 T+1 08:30 的 Yahoo 值相等且非 null」）。任一欄位不等就記一次偏差。
- **天數**：至少連續 20 個交易日（涵蓋不同星期與一次結算日），並且包含至少一個非交易日的平日當對照（確認 Yahoo 不憑空產生 T 列）。
- **「可加 18:10」的門檻**：18:05 這一點在 20 個交易日內偏差為 0；且 T 日列從未出現 null／缺列。**限制要明講**：20 天零偏差只能支持「失敗率上限約 15%（rule of three，95% 信賴）」，不能證明「從不發生」；若要用「從不」的措辭需要更長期的樣本或來源方的明文保證。
- **「15:00 之後即定案」這個 ADR 假設的檢驗**：看 15:05、15:30、16:30、17:30 各點的偏差率；任何偏差都代表 D-3 第 2 點的定義有洞。
- **請求量**：Yahoo 9 次／日 + TWSE 約 5 次／日，均低；Yahoo 端請走 adapter 同等的節流，不要為取樣放寬。
- 取樣結果要保留原始回應與時戳，才能事後重算；不要存任何憑證。

---

## 2. 程式路徑題（情境 A / B / C、盤中、成交量為空）

共同前提：recorder 的呼叫是 `load_market_benchmark(resolver, market="TW", start=run_date−531 天, end=run_date)`，`run_date` 是 `store.now()` 的台北日期（`recorder.py:418、664-676`）。「補跑」與 22:10 是同一支 `run_forecast_record`（`scheduler.py` `add_job` 的 `next_run_time=started + FORECAST_RECORD_STARTUP_DELAY`，約第 836～840 行；第 3 分鐘補跑沒有任何時段限制）。

### 情境 A：平日 15:30 啟動，15:33 補跑

假設快取有前一晚留下的 `^TWII`（最新 T-1，coverage 涵蓋 start）：
- layer 0：`now=15:33 ≥ 15:00`，`expected = T`，快取最後 T-1 → `REFETCH`（上次抓取是昨晚，超過 1 小時）→ ladder，增量起點為 T-1 所在月的 1 日，向 Yahoo 要該月起至 T。
- 假設 Yahoo 回了 T 日列：`as_of` = 請求發出時刻 ≈ 15:33:0x（UTC 07:33）；快照的 `fetched_at` = `as_of`（`inputs.py:160-171`）；快取欄位 `fetched_at` 約 15:33 但不進快照。
- `is_final(TW, T, as_of, fetched_at)`：cutoff = T 日 15:00 台北 ≤ 15:33 → **判定案**（`data/session_calendar.py:31-51`；`inputs.py:199-214`）。
- `settling` 為空，不重抓；`has_record` 為否 → 計算並 `write_run_records`；`created_at` = 15:33 < T+1 00:00 → **`late = 0`**（`store.py:1096-1100`）。
- 結論：**會寫下 T 的 `late = 0` 紀錄**，只要 Yahoo 當時回了 T 日列。Yahoo 當時回的是不是最終收盤：無法查證。
- 若快取已有 T 日列且 `as_of ≥ 15:00`（例如 15:05 有人開頁面抓過），情況相同：沿用該列，stamp 取它的 `as_of`。

### 情境 B：同日 22:10 排程

- 22:10 時 `expected = T`，快取最後 T → `HAS_LATEST_SESSION`；非 cooldown 內，`later = T+1 > end` 不觸發強制重抓 → **沿用 15:33 的快取，不重抓**（`service.py:798-853`）。
- 若 Yahoo 在 15:33 後修正了 T 日值：**22:10 這一次看不到**，因為沒有發出請求。第一次看到修正的機會，是 T+1 日 15:00 之後（`expected` 變 T+1，快取缺 → `REFETCH`，增量起點為該月 1 日，覆寫 T 日列並蓋新 `as_of`）。
- 即使 22:10 看得到，帳也不變：`has_record(claim_id, T)` 為真 → `pending` 空 → `no_new_session`（`recorder.py:430-432`），不寫入、**也不另存快照**（快照只在 `write_run_records` 內與紀錄同一交易寫入）。`forecast_record` 還有 `UNIQUE (claim_id, data_as_of)`（`schema.py:240`）當後盾。所以帳裡只會有 15:33 那一份快照與紀錄。

### 情境 C：平日 13:35 啟動並補跑

- `now=13:35 < 15:00`：`expected = T-1`。
- 快取已有 T-1 → `HAS_LATEST_SESSION`，**不重抓**，快取裡根本沒有 T 日列。recorder 最新定案 bar 是 T-1，`has_record` 通常已真 → `no_new_session`。沒有被判「不定案」，因為沒有 T 日列。
- 只有前面第 0 節列的罕見觸發條件（`market_has_session(T)` 為真、coverage 缺）才會在 13:30～15:00 抓進 T 日列，`as_of` 約 13:35 < 15:00 → 非定案；因 `now < cutoff`，屬 recorder 的 (b) 分支：T 日列留在 `dropped_rows`、T 不變（`recorder.py:21-24`、`653-661`），仍是 `no_new_session`。
- **之後會不會一直判不定案或被重抓**：這筆 13:35 的快取**會被之後的執行沿用**（22:10 判 `HAS_LATEST_SESSION`，見第 0 節），結果是 22:10 與 23:10 都 `inputs_not_ready`，T 沒有紀錄；且「重抓一次」實質上不是重抓（同一個 layer 0）。要到 T+1 15:00 之後才被覆寫。→ **D-3 第 2 點「重抓一次」在現行取數路徑上無法達成**，因為 `load_market_benchmark` 沒有繞過快取的參數，recorder 也不得有（ADR S-4a 規定傳入的就是 `load_market_benchmark` 本身）。（推論：這是我讀 `recorder.py:421-425` 與 `service.py:798-853` 的結果，我沒有實際執行。）

### 盤中（10:00）啟動補跑

T 日盤中列在 `_try_provider` 內被 `_without_unfinished_session` 丟棄（`service.py:941-957`；13:30 前 `latest_closed_session` 是前一平日）。記錄 INFO log，不進快取。recorder 看到的最新是 T-1 → `no_new_session`。**不會產生暫定值紀錄。**

### 成交量為空的列在快取路徑上怎麼處理

- adapter：`_parse_chart_row`（`yfinance.py:291-318`）只要 open/high/low/close/volume 任一為 `None`，整列回 `None`；`_parse_result` 的 `bar is not None` 條件（約 714 行）把它略過，**沒有 log、沒有計數、不記錄為缺口**（連有效的收盤價一起丟，先前報告已記）。raw 路徑才有 `null_gap_rows`，recorder 不走那條。
- `volume = 0` 通過（`PriceBar` 只拒負值，`data/interface.py:77-82`）；負值被 `ValueError` 吞掉並略過（`yfinance.py` `_parse_result` 的 `except`，debug log）。
- 後果（路徑推論）：T 日列的 volume 為 null → 該列不進快取、不進答案；`record_fetch` 仍記完整覆蓋（`service.py:400-403`）。recorder 看到最新是 T-1：已有紀錄 → `no_new_session`（沒有任何非定案列，所以不是 `inputs_not_ready`），**對操作者看起來與「今天還沒收盤」一樣，沒有可見異常**。1 小時 cooldown 過後（22:10、23:10）會再試；若 Yahoo 一直不給 volume，T 永遠缺，隔天 T+1 成為新的 T。若快取裡已有 T 日列（例如 15:05 抓到的完整列），之後抓到 volume 為 null 的版本時，舊列保持不動（upsert 只覆寫回來的列）。
- 模型計算本身只用 close：`outlook/*.py`、`forecast/band.py` 沒有 volume／open／high／low 的使用（我只 grep 了這幾個檔，其他模組未查）。所以 volume 為 null 影響的是「T 能不能成立」，不是特徵值。

---

## 3. 影響評估：情境 A 寫下 `late = 0` 後，收盤被修正

- 受影響欄位（若 T 日 close 被修正）：快照 `bars_json` 中 T 日列的 close（及 OHLCV，雖模型不用）、`input_series_sha256`（快照 content 雜湊）、紀錄的 `base_close`、`label`、`band_def`、`baseline_predictions_json`（B1、B2、B6、B8 都用 lag 0 的 close）、`evidence`、`content_hash`。推論依據：`outlook/baselines.py:71-80`、`recorder.py:690-709` `_record_content`、`store.py:1725-1759`。
- 帳是 append-only 加 UNIQUE：寫下去就不能改，也不會用修正後的值再寫一筆。
- 驗證層重算：`report verify` 用「帳內快照」重算紀錄（`recorder.py` `check_semantics`／`reproduces`、`report.py` 檔頭 20-27 行），所以重算用的是**當時快照**，不是重抓值，內部一致。
- 驗證層比對結果：`scoring.provisional_comparison` 取「第一個含 T 且有 h 個後續 session 的**後來快照**」（`report.py:215-232`），若該快照裡 T 日 close 與紀錄的 `base_close` 不同，回 `base_close_differs`、不比對（`scoring.py:202-203`）。因為 T+1 15:00 之後快取會被修正值覆寫，後來的快照裡 T 日 close 就是修正值 → 這筆紀錄會**可見地**無法比對，而不是靜默算錯。（`scoring.py` 其餘部分我只讀了這幾行。）
- 驗證層能不能辨識「這筆是 15:00～18:00 之間抓的」：**能，但只靠間接欄位**。快照 `bars_json` 每根 bar 存 `as_of` 與 `fetched_at`（`schema.py:170-174`、`inputs.py:93-105`）、`captured_at`；紀錄存 `inputs_max_fetched_at`（`schema.py:231`、`store.py:1757-1759`）。T 日 bar 的 `as_of` 若在 15:00～18:00，就看得出來。限制：(1) 兩個時間戳是同一個值，不是兩個獨立證據；(2) 是「最後一次覆寫該列的請求」的時刻，不是第一次看到該列的時刻；(3) 快照沒有存「是快取沿用還是這次 live 抓的」，也沒存 Yahoo 的原始 timestamp（`raw_timestamp_available = False`，`inputs.py:245`）。所以能事後篩出「stamp 落在 15:00～18:00 的紀錄」，但無法證明該值是否為暫定值，只能與官方值（`MI_5MINS_HIST`）對照。

---

## 4. 建議（僅供 tech-architect 參考，不是裁示）

在事實題無法查證的前提下，資料面最保守的處置：

1. **把「定案」的下限從 15:00 提高到一個已被取樣證實的時點，在證實前取最晚的候選：18:00（甚至要求 stamp ≥ 18:00）**。這需要 `TW_POLICY.publish_cutoff` 以外的另一個常數，或 `is_final` 的 recorder 專用口徑；ADR-0028 CS-17 的 15:00 是「官方站發布」的假設，不是 Yahoo 的。代價：18:10 之前的 stamp 一律非定案；17:45 sector job 抓的值就不會被 22:10 沿用成「定案」，而是進 `inputs_not_ready`（需要同時處理下一點，否則會卡死）。
2. **處理「重抓一次」實際上沒有重抓的問題**：非定案時 recorder 的重抓必須真的繞過快取，否則 `inputs_not_ready` 會卡到隔天、T 永久缺。選項（需 tech-architect 決定，我不在此設計）：給 loader 一個受限的「強制 live」入口；或由 22:10 / 23:10 以外加一次 live 專用抓取。
3. **不要在查證前加 18:10 那一次**；維持只有 22:10／23:10，並且要求 recorder 在 22:10 抓到的值是 22:10 這次自己抓的（stamp 22:10），而非沿用白天的快取。這會與「白天任何人先抓、22:10 沿用」衝突，需處理 sector 17:45／前端白天抓取寫進同一份快取的問題。
4. **啟動補跑加時段限制**（`now` 在 15:00～18:00 之間不跑，或只在 ≥ 18:00 才跑）。
5. **資料面異常浮上檯面**：recorder 需區分「T 日列缺」與「還沒收盤」；yfinance cache 路徑對 null volume 的整列丟棄至少要有計數或 log（目前無）。這只是可見性，不是補值。
6. **正式登記前的取樣**：先跑第 1 節的最小取樣方案，20 個交易日；在結果出來前，D-3 第 2 點「15:00 即定案」只能視為未驗證的假設，且從本報告的路徑來看，它對 17:45 sector job 與啟動補跑都有直接影響。

---

## 驗證摘要

- 連線：Yahoo query1／query2 皆 403（代理 CONNECT 拒絕）；TWSE `MI_5MINS_HIST`、`FMTQIK` 皆 200，11 月 14 個交易日收盤兩端點一致。
- 讀過：`app/services/index.py`、`app/data/cache.py`、`app/data/service.py`（173-1050）、`app/data/freshness.py`、`app/data/session_calendar.py`、`app/data/providers/yfinance.py`、`app/data/interface.py`（PriceBar／ProviderResult）、`app/outlook/inputs.py`、`app/forecast/recorder.py`（296-470、645-709）、`app/forecast/store.py`（部分）、`app/forecast/schema.py`（部分）、`app/forecast/report.py`、`app/forecast/scoring.py`（部分）、`app/scheduler.py`、`app/services/sector_board.py`（385-430）、`app/api/deps.py`、`app/api/signals.py`、`app/playbook/service.py`（部分）、前端 `lib/api.ts`、`lib/queries.ts`（grep）、`compose.yaml`（grep TZ）、ADR-0030（D-3 與待決事項）。沒有讀 `.env`、沒有碰 `data/*.db`、沒有執行 `.bat`、沒有改任何產品程式、沒有執行任何產品程式或測試。
- 推論（沒有實際執行）：情境 A／B／C 與優先題 (i) 的整條路徑，都是讀程式後推演；沒有用測試或 fixture 實跑。尤其 17:30 capture 是否讓 `t = T`、react-query 的自動重抓頻率、Yahoo 在各時點是否回 T 日列，三項我沒有讀到或無法證實。

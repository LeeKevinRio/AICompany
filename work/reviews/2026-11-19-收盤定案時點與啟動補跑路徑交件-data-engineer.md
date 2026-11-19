# 收盤定案時點與啟動補跑路徑交件

- 審查者：data-engineer
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

報告檔：`/home/user/AICompany/work/research/2026-11-19-收盤定案時點與啟動補跑路徑-data-engineer.md`。只建立這一個檔，沒有 commit，沒有改產品程式。

- **優先題 (i)：可能。** 22:10 的 T 日 bar，`min(as_of, fetched_at)` 可以落在 15:00～18:00，而且在 sector job 開著時是常態。
  - 最短路徑：
    - 17:30 的 PIT capture 若成功，`last_ok_session("bars")` 就是 T。
    - 17:45 的 `sector_board_refresh` 進 `taiex_reference_return(window[0], T)`（`app/scheduler.py:469-481`），再進 `load_market_benchmark`，與 recorder 走同一個 `MarketDataService` 和同一份快取。
    - layer 0 判 `REFETCH`：此時 `expected = T`，快取最新只有 T-1，上次成功抓取是昨晚，超過 1 小時 cooldown。於是 live 打 Yahoo，T 日列的 `as_of` 和 `fetched_at` 約 17:45。
    - 19:45、21:45、22:10 都判 `HAS_LATEST_SESSION`，不重抓。recorder 快照裡 T 日 bar 的 `as_of = fetched_at = 17:45`，在 D-3 第 2 點下算定案，會寫出 `late = 0`。
  - 取決於我沒讀到的東西：17:30 的 capture 成功與否（我沒讀 `capture_pit_snapshot`）。capture 失敗時 `t = T-1`，17:45 不抓，22:10 的 recorder 自己第一個抓，stamp 為 22:10。
- **15:00 之前進快取的 T 日 bar：**
  - 13:30 前（盤中，例如 10:00 啟動）不會進快取，`_without_unfinished_session` 會先丟掉（`app/data/service.py:941-957`）。
  - 13:30～15:00 若發生 live 抓取，T 日列會被快取保留，`as_of` 早於 15:00。22:10 會沿用它，判非定案，recorder 的「重抓一次」又讀同一份快取，結果 `inputs_not_ready`。T 的紀錄永久缺，要到 T+1 的 15:00 後才被覆寫。
  - 13:30～15:00 要真的發生 live 抓取很罕見：需要快取缺 coverage，或同市場另一條 TW 序列已有 T 日 bar（`market_has_session`）。
- **事實題：無法查證。**
  - Yahoo query1、query2 兩次都被代理回 `CONNECT tunnel failed, response 403`。
  - 證交所 `MI_5MINS_HIST` 與 `FMTQIK` 回 HTTP 200，11 月 14 個交易日收盤逐日一致。
  - 但環境時間是台北 11/20 00:14，當日 15:00～18:00 的窗口已過。
  - 回應標頭沒有 `Last-Modified`，推不出官方列何時出現。
- **取樣方案**已寫在報告第 1 節，只寫方法：
  - 9 個取樣時點，另加官方基準。
  - 比對欄位為 OHLCV 與 `meta`。
  - 已定案判準：Yahoo T 日列的開高低收與官方、與 T+1 08:30 的 Yahoo 值逐一完全相等。
  - 至少連續 20 個交易日。20 天零偏差只能支持失敗率上限約 15%（rule of three），不能證明「從不發生」。

## 逐題回答

行號為 `.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/` 下。`scheduler.py` 在該 worktree 有未 commit 的修改，我引用的是讀取當下的行號，與 HEAD 不同；其他核心檔案與主線逐檔 diff 相同。

- **TTL 與用快取／重抓的邏輯**
  - 沒有時鐘 TTL，是 ADR-0009 的 session 規則。常數在 `data/freshness.py:129-134`：`publish_cutoff` 15:00、`recheck_cooldown` 1 小時、`session_close` 13:30。
  - 判斷流程：`data/service.py:294-436`，layer 0 在 677-853，`judge` 在 `freshness.py:154-188`，增量起點在 `service.py:650-675`。
  - 指數路徑 `cache_first=True` 在 `api/deps.py:181`。
- **`as_of`／`fetched_at` 怎麼寫**
  - adapter 同一次請求回來的所有列，`as_of` 都是請求當下的 `now`（`data/providers/yfinance.py:745`）。
  - `cache.put` 是無條件 upsert（`data/cache.py:219-228`）：同一根 bar 抓到相同值，兩個時間欄位照樣被更新。
  - 只覆寫這次請求回來的列。增量起點是最後快取 bar 所在月的 1 日，所以最新那個月每次整段重蓋時間戳。
- **recorder 拿到的 `fetched_at`**
  - 快照的 `fetched_at` 不是快取的 `fetched_at` 欄位，而是欄位 `as_of`（`outlook/inputs.py:160-171`），即最後一次覆寫該列的那次請求的發出時間。
  - 所以 D-3 第 2 點的「兩者取較早」在這條路徑上是同一個值取 min。
- **`^TWII` 抓取呼叫點**
  - recorder：22:10、23:10、啟動後 3 分鐘。
  - sector board：17:45、19:45、21:45，加啟動後 2 分鐘。
  - `/api/signals`（`api/signals.py:108`）：前端持股頁開啟時觸發。
  - `/api/leverage`（`api/leverage.py:98`）：00675L 與 00676R 會對到 `^TWII`。
  - `/api/playbook/today` 與 `/settle`（`playbook/service.py:1503-1512`）。
  - `data_refresh` 只處理持股，不抓 `^TWII`。
  - 前端白天開頁面會觸發抓取，寫進同一份快取。react-query 的自動重抓頻率我沒讀。
- **情境 A（15:30 啟動，15:33 補跑）：** 會寫下 T 的 `late = 0` 紀錄，前提是 Yahoo 當時回了 T 日列。`as_of` 約 15:33，`is_final` 為真（`data/session_calendar.py:31-51`），`created_at` 早於 T+1 00:00（`forecast/store.py:1096-1100`）。
- **情境 B（22:10）：** 沿用 15:33 的快取，不重抓。Yahoo 若修正，22:10 看不到，要到 T+1 的 15:00 後才看得到。就算看到，`has_record` 為真會判 `no_new_session`，不寫第二筆，也不另存快照（快照只在 `write_run_records` 內與紀錄同一交易寫入）。`UNIQUE(claim_id, data_as_of)` 是後盾（`forecast/schema.py:240`）。
- **情境 C（13:35 啟動）：** 通常快取沒有 T 日列，`expected = T-1`，判 `no_new_session`，不是不定案。若有人在 13:30～15:00 抓進 T 日列，會被沿用而卡成 `inputs_not_ready`，見上方「15:00 之前進快取」一條。此時 recorder 無法強制重抓：`load_market_benchmark` 沒有繞過快取的參數，ADR S-4a 也要求傳入的就是它本身。
- **盤中（10:00）：** T 日盤中列被丟，不進快取，不會產生暫定值紀錄。
- **成交量為空：**
  - `_parse_chart_row`（`yfinance.py:291-318`）只要 OHLCV 任一為 null，整列丟掉。無 log、無計數，連有效的收盤價也一起丟。
  - `volume = 0` 通過（`data/interface.py:77-82`）。
  - T 日列缺時，recorder 看起來像「還沒收盤」，不是 `inputs_not_ready`，沒有可見異常。
  - 模型計算只用 close。我只 grep 了 `outlook/*.py` 與 `forecast/band.py`，其他模組未查。
- **影響（情境 A 且收盤被修正）：**
  - 受影響欄位：T 日 close、`base_close`、`label`、`band_def`、B1／B2／B6／B8 基準、`evidence`、`content_hash`，以及快照雜湊。
  - 帳內：驗證層重算用的是帳內快照，不是重抓值（`report verify`）。
  - 比對：`scoring.py:202-203` 在後來快照的 T close 與 `base_close` 不同時回 `base_close_differs`，該筆無法比對，是可見的，不是靜默算錯。
  - 辨識：快照 `bars_json` 有每根 bar 的 `as_of`／`fetched_at`，紀錄有 `inputs_max_fetched_at`，所以能篩出 stamp 落在 15:00～18:00 的紀錄。限制有三：兩個時間戳是同一個值；它是最後一次覆寫的時間，不是第一次看到的時間；沒存 Yahoo 原始 timestamp 與「是否沿用快取」。
- **建議（僅供參考，詳見報告第 4 節）：**
  - 先不要加 18:10。
  - 取樣證實前，「定案」門檻暫用 18:00 這類較晚的下限。
  - 「重抓一次」要有真正繞過快取的受限入口，否則 `inputs_not_ready` 會卡到隔天。
  - 啟動補跑避開 15:00～18:00。
  - 22:10 的值要是自己抓的，不能沿用白天的快取。
  - null volume 至少要有計數或 log。

## 驗證

- 連線：
  - Yahoo query1、query2：403，各一次，沒有再重試。
  - TWSE 兩個端點：200。
- 讀過的檔：
  - 資料路徑：`app/services/index.py`、`app/data/cache.py`、`app/data/service.py`、`app/data/freshness.py`、`app/data/session_calendar.py`、`app/data/providers/yfinance.py`、`app/data/interface.py`。
  - 預測帳：`app/outlook/inputs.py`、`app/forecast/recorder.py`、`app/forecast/store.py`（部分）、`app/forecast/schema.py`（部分）、`app/forecast/report.py`、`app/forecast/scoring.py`（部分）。
  - 呼叫點：`app/scheduler.py`、`app/services/sector_board.py`（部分）、`app/api/deps.py`、`app/api/signals.py`、`app/playbook/service.py`（部分）。
  - 其他：前端 `lib/api.ts` 與 `lib/queries.ts`（用 grep）、`compose.yaml`（grep TZ）、ADR-0030（D-3 與待決事項）。
- 沒做的事：沒讀 `.env`，沒碰 `data/*.db`，沒執行 `.bat`，沒執行任何產品程式或測試。
- 推論（只讀程式，沒實跑）：情境 A、B、C 與優先題 (i) 的整條路徑。
- 三項我沒讀到或無法證實：
  - 17:30 的 capture 是否讓 `t = T`。
  - 前端 react-query 的自動重抓頻率。
  - Yahoo 在各時點是否回 T 日列、值是否為最終值。

## 下一步

1. 正式登記是否暫緩，由 tech-architect 與 CEO 依優先題的「可能」判斷。我的看法：在取樣完成、或「重抓」與「定案時點」兩個缺口補上之前，D-3 第 2 點的 15:00 只能視為未驗證的假設。
2. 請 CEO 或有網路的環境依報告第 1 節的方案取樣，至少 20 個交易日。
3. 若要補強取數路徑（受限的強制 live 入口、null volume 計數、啟動補跑的時段限制），請 tech-architect 先出決議，再由 dev-lead 實作。這些我都沒有動。

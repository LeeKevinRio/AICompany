# V14-03 規章、缺 bar 機制與因子修訂前置查證（data-engineer）

- 審查者：data-engineer
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# data-engineer 回報：V14-03 失效條件規章查證（第 1～3 項）、機制查證（第 4、5 項）、N-17 前置（第 6 項）

我沒有改任何檔案，沒有 commit，沒有讀 `.env`，沒有碰 `*.db`（連 `stat` 也沒做），沒有跑任何查資料的程式，也沒有看任何資料數量。

## 一、本次結論

**1. 第 1～3 項（規章）：這次沒有查到任何官方原文，V14-03 的凍結阻擋項不能解除。**
- 【事實】網路不可用。我對 `www.twse.com.tw`、`twse-regulation.twse.com.tw`、`law.moj.gov.tw`、`www.tpex.org.tw` 各連一次，agent proxy 全部回 `CONNECT tunnel failed, response 403`。查證日期 2026-10-18。
- 我沒有改走其他管道繞過。
- 第 1、2、3 項沒有條文名稱與條次可填。下面凡是記憶來源的內容，都標【推論，待查】，不當成事實。

**2. 「結算窗內是否可能出現結構上沒有一般漲跌幅限制的交易日」：我現在不能回答「無」，也不能回答「有」。**
- 【推論，待查】可能有的情形（只是待查清單，不是結論）：
  - 新上市（初上市）初期的交易日。
  - 減資或面額變更換發新股恢復買賣的初期交易日。
  - 暫停交易後恢復買賣的首日。
- 【推論，待查】處置、全額交割應該只改撮合方式、不改漲跌幅。
- 【推論，待查】我個人傾向是「減資恢復買賣首日仍有漲跌幅，只是基準價改為恢復買賣參考價」。這與 quant 的推測相反，必須以原文為準，不可採信。
- 【事實】repo 內沒有任何官方原文。2026-10-16 探測指令第 6.5.2 節（`/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` L2264–2277）已經列了 8 種情形的人工查證表，欄位全空。我 2026-10-17 的補查回報也寫過「沒有任何官方出處」。
- 這件事要靠人讀官方原文。見第四節。

**3. 就算原文查出「有些日子沒有限制」，這些日子在 repo 現有資料裡也無法從機制上辨識。**
- 新上市：
  - 【事實】listing 快照沒有上市日期。`app/sectors/universe.py:154-174` 的 `_seasoned` 用「第一根可見 bar」算年資，是近似值。
  - 新上市股在前 60 個 session 不進族群母體。
  - 個股 claim 靠 σ60 的有效報酬數擋住新上市股，這是 tech-architect 的推論，我這次沒有重讀。
- 暫停交易後恢復：
  - 【事實】沒有停牌名單來源，停牌股被算成缺漏。
  - 證據：`app/sectors/coverage.py:84-85`（`suspended_count=None`）、`app/sectors/models.py:120-121`、`app/sectors/universe.py:23`。
- 減資、面額變更：
  - 【事實】repo 沒有事件來源。唯一的公司行動來源 `TWT48U_ALL` 是除權除息預告表（`app/dividends/providers.py:1-17`、`:52-60`）。
  - ADR-0027 待決事項也把「分割、減資的事件來源」列為 data-engineer 待查（字串：`分割、減資的事件來源`，約 L2035）。
- 處置、全額交割：沒有來源。
- 所以，除權息事件與停牌標記都辨識不了這些日子。唯一的偵測手段就是價格跳動本身，也就是 V14-03 要偵測的對象。

**4. 方向性推論（供風控判斷，不是規章結論）。**
- 【推論】無漲跌幅的日子只會讓真實大幅行情更容易超過複利門檻。結果是多判成 `split_or_reduction_suspected`，列被作廢或成員被排除。
- 【推論】它不會讓真實分割漏判。
- 這個方向與風控 R14-13 說明誤判方向「對模型有利」的段落是同一方向。

**5. 第 4 項：目前機制無法區分停牌與 `fetch_failed`。**
- 每日 bars 來自單一批次端點，沒有「逐標的取得」這件事。
- 缺 bar 的標的只有兩種可能，而且都沒有逐標的證據。

**6. 第 5 項：`^TWII` 的 T+h bar 可能晚於 22:10 才寫入，路徑見第二節。**

**7. 第 6 項：能判定，但要新寫讀端方法。**
- 【事實】`pit_dividend_announce_rows` 由 `kind='dividend_announce'` 的 run 寫入。該 run 與 bars run 共用同一張 `pit_snapshot_runs`、同一個 `run_id` 序號。
- 【事實】有 `kind`、`status`、`recorded_at`、`session_date`、`content_hash` 可用。
- 【事實】目前沒有任何方法能偵測「晚到公告」或「因子修訂」。
- 【事實】現有 PIT 讀取路徑只取 `(symbol, ex_date)`，完全不讀現金股利、股票股利欄位。

## 二、各部門回報（data-engineer）

ADR 行號說明：我讀 ADR-0027 時，工作樹正被別人修改，行號在我讀的過程中漂移約 5 行。下面 ADR 一律附定位字串，行號只作參考。

### 第 1～3 項：規章（網路不可用，不得當事實）

| 項 | 官方出處（條文名稱、條次） | 查證日期 | 結論 |
|---|---|---|---|
| 1 暫停交易後恢復交易首日的參考價與漲跌幅 | 無，未查到 | 2026-10-18 | 【推論，待查】以暫停前最後收盤價為基準、仍有限制。無原文，不可凍結 |
| 2 減資、面額變更換發新股恢復買賣的參考價與首日（或首五日）限制 | 無，未查到 | 2026-10-18 | 【推論，待查】參考價依恢復買賣參考價計算；首日是否設限不明 |
| 3 其他無一般 10% 限制的制度 | 無，未查到 | 2026-10-18 | 【推論，待查】候選：新上市初期。處置、全額交割應仍有限制 |

**人工查證要問的問題**（建議直接併入探測指令 6.5.2 表，那張表已經有這 8 列）：
- 每一種情形各自要問：
  - 基準價是什麼？
  - 有沒有不設限的天數？天數是幾天？
  - 不設限結束之後怎麼算？
- 要查的情形：
  - 一般上市普通股
  - 新上市
  - 減資恢復買賣
  - 面額變更、分割恢復買賣
  - 暫停交易後恢復買賣
  - 終止上市前最後交易期間
  - 處置股票
  - 全額交割股
- 每項要附原文、網址、條次、讀到日期。

**一個結構上的提醒**（【推論】）：
- 就算限制仍適用，減資或面額變更的恢復買賣參考價與前一日收盤不同。
- 因此跨事件的原始收盤報酬本來就不被 `(1+c)^g − 1` 框住。這正是分割判準要抓的東西，不是前提不成立。
- 前提真正受影響的是：真實的極端行情在無限制日被誤判。

### 第 4 項：停牌與 `fetch_failed` 的機制區分（讀碼，沒看資料）

**【事實】資料怎麼進來**
- 每日 bars 來自單一 TWSE 批次端點 `STOCK_DAY_ALL`。
  - 模組註解寫明「沒有成交（或停牌）的標的就是沒有那一列」，見 `app/data/providers/twse_snapshot.py:6-8`。
  - 我沒有實測，無網路。
- 抓取邏輯在 `twse_snapshot.py:361-385`。
- 單列解析失敗時：
  - 只做 `logger.debug`，並累加一個區域變數 `skipped`（`twse_snapshot.py:376-382`）。
  - 被略過的代號與次數不進任何持久紀錄。
  - 只有在全部列都不可解析時才回錯誤（`:383-384`）。
- 無成交的占位值（`--`、空字串、`N/A`）在 `app/data/providers/_util.py:17`、`:37-56` 被當成不可解析而丟掉。
- 結果：停牌（沒有那一列）和「有那一列但價格欄位是占位值」都在 bars 裡變成「沒有這個標的的 bar」。

**【事實】ok 的判定與持久化**
- run 是否為 `ok` 只看覆蓋率 ≥ 0.98（`app/services/pit_snapshot.py:229-249`）。
- 覆蓋率分母是 listing 的普通股，listing 來自 `t187ap03_L`。該資料集沒有停牌、下市標記。
- `pit_snapshot_runs` 的欄位只有以下幾項（`app/data/market_panel.py:121-134`）：
  - `run_id`、`kind`、`session_date`、`recorded_at`、`source`、`status`
  - `row_count`、`expected_count`、`content_hash`、`reason`
- `market_daily_bars` 沒有失敗、略過、狀態欄位（`market_panel.py:141-158`）。
- `reason` 只在 `partial` 與 `failed` 時有值，是整份 run 的文字，不是逐標的紀錄。
- 整份 bars 失敗時（`pit_snapshot.py:204-215`）寫一筆 `failed` run、沒有任何 bar 列。
  - 這是「整個 session 取得失敗」，與逐標的無關。
  - 在 ok run 內缺 bar 的標的，這個失敗紀錄不適用。
- 同一 session 一旦已有 `ok` run 就略過後續擷取（`pit_snapshot.py:151-153`、`:201-202`），所以也不會有第二次機會看到「這個標的後來補上了」。

**【事實】唯一有逐標的 `failed` 狀態的地方**
- 表是 `market_backfill_progress`（`market_panel.py:205-215`；寫入見 `pit_snapshot.py:393-405`）。
- 這張表是可 upsert 的暫存進度，不是 PIT 紀錄，只用於 D0 之前的 FinMind 暖機。
- 它不能拿來判定每日缺 bar 的原因。

**結論**
- ADR-0027 D-13 的 `fetch_failed` 要求「每一項都要有正面證據，不得由沒有資料反推」。字串：`每一項都要有正面證據`。
- 現行沒有逐標的取得失敗證據。所以停牌、`fetch_failed`、解析失敗的缺 bar，在機制上無法區分。
- 這也回答了 ADR 待決事項那句「市場 DB 能否提供逐標的的取得失敗證據」：不能。
- 日後若要區分，至少需要以下其一：
  - 取得停牌名單的來源（要另案查證資料源，屬 tech-architect 與 CEO 的資料源選型）。
  - 把被略過的列（代號、原因）持久化。這屬 `pit_snapshot` 的改動，要 ADR-0012 修訂。
- 在那之前，V14-03 的「缺 bar 成因無法區分」前提與 LM-63 的「不得斷言停牌」要求，都與現況一致。

### 第 5 項：`^TWII` T+h bar 是否可能晚於當晚 22:10 的評估才寫入

**結論：可能。** 只列路徑，不數次數。以下路徑，【事實】是我讀碼的結果，【推論】另標。

**前置事實**
- `app/forecast` 目錄不存在，22:10 的 `forecast_record` job 還沒有實作（`Glob` 與 grep 皆無）。
- `is_final`、`final_after`、`session_calendar` 在 `app/` 的 `.py` 內零命中，ADR-0028 的定案判斷沒有實作。
- 以下路徑是「現行 repo 的行為」加上「ADR 設計的行為」的合併，我分開標註。

**A. 排程裡有誰會寫 `^TWII`？只有一條。**
- `data_refresh` 只抓使用者持倉。見 `app/scheduler.py:290-295`。
- 持倉不能是 `^` 開頭的標的。見 `app/positions/models.py:37-42`。
- 所以 `data_refresh` 不會抓 `^TWII`。
- 唯一的排程寫入路徑是族群板的重算：
  - 17:30、19:30、21:30 的 `capture_pit_snapshot` 在尾端呼叫 `refresh_sector_board`（`scheduler.py:484-504`）。
  - 17:45、19:45、21:45 另有一個 `sector_board_refresh` job（`scheduler.py:674-687`）。
  - 重算裡呼叫 `taiex_reference_return`（`app/services/sector_board.py:410-415`）。
  - 它經 `load_market_benchmark` 讀 `^TWII`（`scheduler.py:443-458`）。
- 注意，最後一個點是 21:45，與 22:10 只差 25 分鐘。

**B. 這條路徑在 T+h 當天來不及或沒寫的情形**
1. **當天沒有 ok bars run，就沒有重算，也就不會要 `^TWII`。**
   - 重算只在有 ok bars run 的最新 session t 上進行（`sector_board.py:401-415`）。我只讀了這一段，沒有重讀整個 service。
   - bars run 變成 `partial`（覆蓋率不足）或 `failed`（含 session 自證失敗）的條件，見 `pit_snapshot.py:120-122`、`:204-215`、`:234-249`。
2. **排程點錯過。**
   - 三個 sector 相關 job 都沒有設 `misfire_grace_time`（`scheduler.py:659-701`），註解自己寫了「錯過超過一秒就由下一個點補」（`scheduler.py:178-181`）。
   - 啟動時各 job 會補跑一次（capture：`:672`；board refresh：`:686`）。
3. **上游來源在這些時段失敗。**
   - 失敗時不寫入，回頭用快取（`app/data/service.py:421-436`）。
   - 失敗後 TW 的重試冷卻是 1 小時（`app/data/freshness.py:109-111`）。
   - 之後的第一次成功寫入，可能就是晚於 22:10 的 23:10 重試，或是隔天。
4. **盤中值被寫入，並且被當成「已是最新」。**
   - 服務把上游回來的任何一根 bar 直接寫入（`service.py:352-353`）。
   - `app/data/providers/yfinance.py` 的解析只丟掉欄位為 None 的列（`:378-384`），沒有定案判斷。
   - 快取是否夠新，只比較日期（`freshness.py:160-161`；TW 的 15:00 截止見 `:83-89`、`:109-111`）。
   - 於是一根在 T+h 盤中被寫入的 bar，15:00 之後會被判成 `HAS_LATEST_SESSION`，不再重抓（`service.py:797-853`）。
   - 直到下一個 session 的 15:00，期望日期超過最後一根 bar，才重抓。重抓時會從最後一根 bar 的月初整月重拉並覆寫（`service.py:650-675`）。
   - 也就是說，T+h 日的定案值可能第一次出現在 T+h+1 日 15:00 之後，已經晚於 T+h 當晚 22:10。
   - 【推論，待查】Yahoo 圖表端點在盤中是否會回當日未定案的列，我無網路，無法證實。前提是「會回」。
5. **使用者請求觸發的路徑，任何時間都可能發生。**
   - `/api/signals`：`app/api/signals.py:108`。
   - playbook：`app/playbook/service.py:229-233`。
   - 槓桿頁（TW 槓桿 ETF 的標的指數是 `^TWII`）：`app/api/leverage.py:98`；對應見 `app/leverage/index_mapping.py:251`、`:259`。
   - 這些路徑可以在 22:10 之後才第一次寫入該日 bar。
6. **ADR 設計中的 22:10 job 與重試。**
   - 設計是 22:10 執行、23:10 重試、啟動補跑（字串：`平日 22:10 執行，23:10 重試`）。
   - D-7.3 (ii) 設計是在候選 T 的大盤 bar 不是定案列時，「強制重抓恰好一次」（字串：`強制重抓一次`）。
   - 這是記錄端的候選 T。結算端怎麼取 T+h，ADR 沒有同樣寫明強制重抓。我沒有看到。
   - 23:10 的重試與啟動補跑，在設計上本來就晚於 22:10 的評估。

**C. 對 O-1b 與 R14-5 ① 最重要的一條：快取是可覆寫的，沒有「首次寫入」紀錄。**
- 【事實】`price_bars_cache` 以 `(symbol, market, trade_date)` 為主鍵做 upsert，`as_of`、`fetched_at` 每次覆寫（`app/data/cache.py:39-53`、`:177-231`）。
- 沒有歷史表。`price_bars_fetch_log` 只是整個序列一列（`cache.py:76-83`）。
- 所以：
  - 就算 T+h bar 在 22:10 前已存在，之後任何一次含該日的重抓（上面第 4、5 點）都會覆寫它。
  - 事後只能看到最後一次寫入的值與時間，無法重建「評估當下」的版本。
- 這直接佐證風控 R14-5 ① 的要求：大盤的判定視圖必須由 TA 另訂存值方式，單靠現行快取，「以存下的視圖重算，逐位相同」對大盤做不到。
- 另一側：ADR 設計的 `is_final_bar` 要求 `max(as_of, fetched_at) ≤ now`。這靠的是列內的 `as_of`、`fetched_at`，也是會被覆寫的值。

### 第 6 項：市場 DB 的除權息公告與「因子修訂」偵測（N-17 前置）

**1. 由哪種 run 寫入**
- 【事實】`kind='dividend_announce'` 的 run，由每日擷取產生。
  - 擷取順序：listing、classification、dividend_announce、bars（`pit_snapshot.py:129-131`）。
  - 簡單 kind 的寫法：`pit_snapshot.py:156-178`。
  - 資料來自 `TWT48U_ALL`，每列的原始欄位逐字保存（`twse_snapshot.py:430-470`）。
- 內容用 `content_hash` 去重，寫在 `pit_dividend_announce_rows`：
  - 主鍵 `(content_hash, key)`，`key = "{symbol}|{原始 Date}"`（`market_panel.py:190-197`、`:594-631`，key 組合在 `:610`）。
  - 當日內容與先前完全相同時，不重複插入列，但仍寫一筆 run 指向同一個 `content_hash`（`market_panel.py:39-51`、`:618-631`）。
- `ok` 之後同 session 即略過（`pit_snapshot.py:151-153`、`:160-161`）。
  - 所以每個 session 最多一筆 ok 的 dividend_announce run，是該 session 第一次成功的那一筆。
  - session 內再次公告的修訂，要等下一個 session 的第一筆 ok run 才看得到。

**2. `run_id` 是否與 bars run 共用**
- 【事實】共用。四種 kind 全在同一張 `pit_snapshot_runs`，`run_id INTEGER PRIMARY KEY AUTOINCREMENT`（`market_panel.py:121-134`）。
- 含義：
  - `MAX(run_id)` 會因為 listing、classification、dividend_announce 的 run 與 failed run 而前進，不一定是 bars run。
  - failed run 也會佔用序號，它們的 `session_date` 是 NULL（`pit_snapshot.py:135-148`）。
  - 暖機回填每個標的每個交易日各寫一筆 run（`market_panel.py:633-` 起，`pit_snapshot.py:393-405`），只在 D0 之前發生。
- `settle_source_run_max` 取 `MAX(run_id)` 在語意上沒問題（序號只比大小）。
  - 但任何「晚到」的判定必須再加 `kind`、`status='ok'` 的過濾。
  - ADR 的 `scan_late_market_bars` 設計已有 `kind='bars'`、`status='ok'` 的過濾。這是設計上的做法，不是已存在的程式碼。

**3. 有哪些欄位可判定「晚到公告」或「因子修訂」**
- 可用欄位：
  - `kind`、`status`、`session_date`、`recorded_at`、`run_id`、`content_hash`、`source`、`reason`（`market_panel.py:121-134`）。
  - `recorded_at` 是 store 自己的時鐘，不接受呼叫端傳入（`market_panel.py:499`）。
  - `status` 在 dividend_announce 只會是 `ok` 或 `failed`。`quality_failed` 型別存在（`app/data/interface.py:215-226`），但 capture 路徑不寫它。
  - 公告原始欄位存在 `pit_dividend_announce_rows.raw_json`，包含現金股利、股票股利比等（`market_panel.py:190-197`；欄位清單見 `app/dividends/providers.py:24-60`）。
- 偵測邏輯可定義為「比較相鄰兩筆 ok 的 dividend_announce run」：
  - 先比 `content_hash`，相同就是沒有變化（便宜的快速路徑）。
  - 不同時，用 `key` 與 `raw_json` 比對：
    - 新 key：晚到公告。若同一檔另有舊 key，則是除息日異動。
    - 同 key、`raw_json` 不同：公告內容修訂（因子修訂）。
    - key 在後一筆消失，而且後一筆 `session_date` 早於該 key 的除息日：撤銷或改日期。
    - 若後一筆 `session_date` 已晚於除息日：這是正常過期，不是修訂。
  - 「session_date 是否已晚於除息日時預告表仍列出該日」我沒有資料，標【推論，待查】。

**4. 目前沒有的東西，也是 N-17 的實作缺口**
- 【事實】沒有任何偵測方法。
  - `scan_late_market_bars`、`ok_bars_runs_between`、`source_revision`、`dividend_factor_corrected` 在 `apps/stock-desk/backend` 內零命中（Grep）。
- 【事實】現有讀端不夠用。
  - `MarketPanelReader.dividend_announce_observations`（`market_panel.py:1123-1156`，SQL 在 `:295-304`）只回 `(run_id, recorded_at, symbol, ex_date)`。
  - 它依 `recorded_at` 日期過濾、依代號過濾，沒有 `run_id` 範圍參數，也不讀 `raw_json`。
  - 它自己的 docstring 寫明只供測試與 ADR-0016 V-1 離線檢查使用，持倉鏈不得呼叫（`:1133-1135`）。
- 【事實】PIT 視圖根本不載入金額。
  - `_load_dividend_frame` 只 `SELECT symbol, ex_date`，而且排除 `ex_date IS NULL` 的列（`market_panel.py:1031-1064`，SQL 在 `:1048-1052`）。
  - 現有的 `EX_DIVIDEND_COLUMNS` 只有 symbol 與 ex_date。
  - 所以「因子」所需的現金股利、股票股利比，在現行 PIT 視圖裡根本讀不到。偵測「因子修訂」以及 ADR-0027 D-4 第 2 點的還原計算，都需要新的讀取方法去讀 `raw_json`。
- 【事實】dividend_announce 在 PIT 視圖的語意是「所有可見 run 的聯集」（`market_panel.py:883-905`）。
  - 被撤銷或改期的舊公告，仍會留在聯集裡。
  - 所以「聯集裡有哪一列」不能當成「現行公告」。N-17 要明確定義這一點。
- 【推論，待查】預告表只列未來的除息日（`app/dividends/providers.py:99-107`）。除息日之後才發生的更正（例如實際權值重算）不會出現在這張表。這類「事後更正」是否屬於 `dividend_factor_corrected`，需要 TA 定義。

**5. 與主 DB 的區別（呼應 TA 疑義 2）**
- 主 DB 的 `dividend_sync` job（17:50、19:50、21:50）寫的是 `dividend_sync_runs` 與 `dividend_events` upsert（`scheduler.py:688-701`），是 ADR-0016 D-5.2 的持倉鏈。
- 預測鏈要讀的是市場 DB 的 `pit_dividend_announce_rows`。我同意 TA 的出處更正。
- 我 2026-10-18 晚到資料查證檔 L108 引用 D-5.2 是我的錯，在此更正。

## 三、驗證

**實際做的事**
- 讀碼與讀文件：
  - `app/data/market_panel.py`、`app/services/pit_snapshot.py`、`app/data/providers/twse_snapshot.py`、`app/data/providers/_util.py`
  - `app/data/service.py`、`app/data/cache.py`、`app/data/freshness.py`、`app/data/providers/yfinance.py`
  - `app/scheduler.py`、`app/services/index.py`、`app/services/sector_board.py`、`app/sectors/coverage.py`、`app/sectors/universe.py`
  - `app/dividends/providers.py`、`app/data/interface.py`
  - ADR-0027（D-3、D-4、D-7、D-13）
  - 風控 v0.14 審查、quant v0.14 草案、TA 疑義裁定
  - 探測指令 6.5 節與我 2026-10-17 補查回報
- Grep 確認不存在：`app/forecast`、`is_final`、`final_after`、`session_calendar`、`scan_late_market_bars`、`ok_bars_runs_between`、`dividend_factor_corrected`。
- 網路：對 4 個官方域名各嘗試一次，全部被 proxy 拒絕，如第一節。我沒有試圖繞過。

**沒有做的事**
- 沒有跑任何測試或查詢資料的程式，沒有看任何資料數量或結果。
- 沒有讀 `.env`，沒有碰 `stock-desk-market.db`、`stock-desk.db`。
- 沒有實測 `STOCK_DAY_ALL` 對停牌股的實際回傳（無網路）。
- 沒有實測 Yahoo 盤中是否回未定案列。

**事實與推論的邊界**
- 第 4、5、6 項標【事實】的，都是我讀到的程式或 ADR 字面。
- 標【推論】的有：
  - 規章的任何內容。
  - Yahoo 盤中行為。
  - 預告表在除息日當天是否仍列出。
  - 事後更正是否進該表。
  - 無限制日只會多判不會漏判的方向。

## 四、下一步

**1. 規章（凍結阻擋，需要人，建議交 coordinator 轉 CEO）**
- 請 CEO 在可連網的機器上，依探測指令 6.5.2 的表（8 列）逐列填：官方網址、標題、條次、逐字原文、讀到日期。
- 若希望由我代查：需要把 `www.twse.com.tw`（及營業細則所在網域）放行給本 session 的 agent proxy。這是環境權限，不是我能自行處理的。
- 填完後交風控。若任何一列是「無漲跌幅限制」，V14-03 依 R14-15 重新具名送風控。
- 在此之前，N-18 維持開啟，dirdef 不得凍結。

**2. 機制（可併入 V14-03 與 O-1 的條文）**
- 缺 bar 成因：
  - 現況無法區分，V14-03 與 LM-63 現有字面（不斷言成因）與機制一致，不必改。
  - 若日後要「停牌改用單步門檻」，要先有停牌名單來源（資料源選型，歸 tech-architect，必要時升 CEO），這屬新定義版本。
- `^TWII`：
  - 建議 TA 在 R14-5 ① 明訂大盤 bar 的判定視圖存值，不能依賴 `price_bars_cache` 的當前值。原因是第二節 C。
  - 風控 R14-6 的「現行管線下 ① 預期接近 0」這句，對大盤不成立：大盤有多條晚寫入路徑。建議把「個股與族群成員」和「大盤」分開寫。
  - 結算端取 T+h 的大盤 bar 時，是否比照記錄端做一次強制重抓，ADR 沒寫明，請 TA 補。

**3. N-17（因子修訂偵測）**
- 我的前置查證就是第二節第 6 項。請 coordinator 轉 TA。TA 的提案至少要定義：
  - 讀端方法：回傳 `run_id` 範圍內的 dividend_announce run，並讀 `raw_json`，且過濾 `kind` 與 `status='ok'`。
  - 修訂的判準：新 key、同 key 內容變、key 消失，各自的歸屬。
  - 過期與撤銷的分界（依 `session_date` 對除息日）。
  - 每 session 只留第一筆 ok run 的解析度限制，須在 §4.2 揭露。
  - 聯集語意下，被撤銷的公告仍留在 PIT 視圖，要明定處理。
  - 事後更正（除息日之後）是否屬於 `dividend_factor_corrected`。
- 在 TA 提案出來前，我同意 TA 疑義 2 的甲版：`dividend_factor` 標「未涵蓋，不計」。
- 我可以在 TA 提案後，起草讀端方法與 fixture 測試（離線，不打外網）。

**相關檔案**
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/pit_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse_snapshot.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/cache.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/freshness.py
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py
- /home/user/AICompany/apps/stock-desk/backend/app/services/sector_board.py
- /home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md（L2264–2277）
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md

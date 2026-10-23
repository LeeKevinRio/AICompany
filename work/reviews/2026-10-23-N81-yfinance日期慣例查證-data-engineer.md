# N-81 yfinance ^TWII 日期慣例查證

- 審查者：data-engineer
- 日期：2026-10-23
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## N-81 查證回報：yfinance `^TWII` 日期慣例（data-engineer，未改任何 repo 檔、未 commit）

### 1. 本次結論

**日期標示在現有程式的路徑上「大概可靠，但沒有任何程式或測試證實」。** 支撐可靠的那個前提是 Yahoo 的 `^TWII` 日 bar 時間戳記是台北當日 09:00（UTC 01:00）。這個前提我沒能用真實回應驗證，因為 Yahoo 網域被擋。

- **整體平移風險：有，而且有明確的觸發條件。** repo 的 adapter 用 UTC 日期當 bar 日期（`apps/stock-desk/backend/app/data/providers/yfinance.py:385`）。這只在時間戳記的台北時刻不早於 08:00 時等於台北交易日。
  - 若 Yahoo 給的是 09:00，不會平移。
  - 若某天或某段歷史給的是台北當地 00:00（UTC 前一日 16:00），整段會早一天。
  - adapter 不讀 `meta.exchangeTimezoneName`/`gmtoffset`，也不驗時間戳記的時刻，所以平移發生時不會有任何警示。
- **repo 不用 `yfinance` Python 套件。** 它直接呼叫 Yahoo 的 chart JSON 端點（`yfinance.py:25-27, 47-50`）。所以套件的 tz 處理（問題 2）不適用於 repo，只能當對照。
- **測試覆蓋的是合成資料。** `tests/fixtures/yfinance_chart_twii.json` 時間戳記全是 UTC 01:00（台北 09:00），但 `tests/fixtures/README.md:48` 寫明這是「合成、完全未經即時回應驗證」。所以不能拿它證明 Yahoo 真的這樣給。
- **對 V26-01 的含義：**
  - 日期界限本身是機械可檢的，風險集中在「時間戳記到日期」這一步。
  - 這一步可以用快照內保留的原始時間戳記做一次性檢查，成本很低。
  - 建議把「V26-01 另一面 ③ yfinance 日期慣例【未查證】」維持【未查證】，直到 CEO 本機或網路允許的環境實測一次。

### 2. 各部門回報（逐題）

**題 1：每根日 bar 的日期代表什麼？會不會整體平移？**
- 【事實】repo adapter 的轉換是 `datetime.fromtimestamp(int(ts), tz=UTC).date()`（`yfinance.py:385`），範圍過濾 `start <= bar.date <= end`（`yfinance.py:360`）。檔頭自承「以 UTC 日期推導，未驗證的簡化」（`yfinance.py:80-87`）。
- 【事實】離線實算（`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/tzcheck.py`，用 repo 的 `.venv` 跑）：
  - 台北 13:30、09:00、08:00 的時間戳記，UTC 日期與台北日期相同。
  - 台北 07:59 與 00:00 的時間戳記，UTC 日期比台北日期早一天。
- 【事實】合成 fixture 的 4 根 bar，時間戳記皆為 UTC 01:00（台北 09:00），`meta.exchangeTimezoneName` 為 `Asia/Taipei`，日期相符。這是手工構造，只證明程式對這種輸入行為正確。
- 【推論】真實 Yahoo 對 `^TWII` 的 `interval=1d` 時間戳記是該交易日的開盤時刻（台北 09:00）。依據是 fixture 作者的假設加上我對 Yahoo 慣例的印象。
- 【事實】yfinance 套件原始碼（v1.7.0）有針對「Yahoo 日 bar 時間戳記在當地午夜前 22/23 點」的修正（`yfinance/utils.py:902-912`，註解寫「these intervals should start at time 00:00」，例子是巴西）。這說明 Yahoo 的日 bar 時間戳記慣例並非各交易所一致，不能只靠通則推到 `^TWII`。
- 【未查證】真實 `^TWII` 回應的時間戳記時刻、`gmtoffset`，以及歷史上是否曾在某段期間改變慣例。

**題 2：tz-aware 還是 naive？轉 date 會錯位在哪？**
- 【事實】`yfinance` 套件 v1.7.0（對照用，repo 不使用）：
  - `parse_quotes` 先得到 naive UTC index（`utils.py:548-572`，`pd.to_datetime(timestamps, unit="s")`）。
  - `set_df_tz` 轉成交易所時區（`history.py:423`、`utils.py:623-627`）。
  - 日線再取當地日期，重新 localize 成當地午夜（`history.py:497`）。
  - 結果是 tz-aware、`Asia/Taipei` 的 00:00 index，直接 `.date()` 是台北交易日。
  - `Asia/Taipei` 來自回應的 `meta.exchangeTimezoneName`（`history.py:380`）。
- 【事實】錯位點（離線實算）：
  - 對上述 tz-aware 午夜 index 先 `tz_convert("UTC")` 再 `.date()`，會得到前一天（`2024-01-03 00:00+08:00` 變成 `2024-01-02`）。
  - 先 `tz_localize(None)` 再 `.date()` 則正確。
  - 存檔、序列化（CSV、parquet 帶 offset）後以 `utc=True` 解析，也會整段早一天。這屬於「套件路徑」風險。
- 【事實】repo 路徑：
  - adapter 輸出的是 `PriceBar.date`（純 `date`，無時區，`app/data/interface.py` 的 `PriceBar`）。
  - 下游 `bars_to_frame` 以 `pd.Timestamp(bar.date)` 建 naive index（`app/signals/frame.py:45`）。
  - 下游 `.date()` 用在 naive index 上：`app/signals/frame.py:107`、`app/backtest/engine.py:128`、`app/leverage/drag.py:392`、`app/signals/risk.py:300`、`app/backtest/event_study.py:350`。這些不會再平移。
  - 所以 repo 的唯一轉換點就是 `yfinance.py:385`。
  - `app/backtest/basket.py:209-210`、`app/data/panel.py:244/351/367`、`app/data/market_panel.py:255`、`app/backtest/sector_eval.py:1503` 處理的是 TWSE 快照的 `recorded_at`，不是 `^TWII` bar，與本題無關。

**題 3：缺 bar、重複 bar、事後修訂**
- 缺 bar：
  - 【事實】adapter 對任一 OHLCV 欄位為 `None` 的列整列跳過，不補值（`yfinance.py:380-384`）。
  - 【事實】adapter 沒有週末過濾，也沒有休市日表。週末或補班日若 Yahoo 給了 bar，會原樣進來。
  - 【推論】只要有一個欄位（例如 volume）為 null、價格有值，就會被當成「缺 bar」丟掉，這是 adapter 造成的缺漏，不是資料源缺漏。`^TWII` 的 volume 在真實回應中是 0 還是 null，【未查證】。fixture 全是 0。
  - 假日：【推論】Yahoo 沒有開市就沒有 bar，應該不會有假日 bar。
  - 颱風假：【未查證】Yahoo 是否一定沒有該日 bar。草案已規定以獨立來源（官方日曆）核對，這個設計是對的。
  - 補上班日：【未查證】。台灣股市在補班週六是否開市，我沒有查證，需以官方休市日表為準，不憑記憶。
- 重複 bar：
  - 【事實】yfinance 套件有已知處理：日線最後兩列同日就丟掉倒數第二列（`utils.py:687-708`，註解說 Yahoo 在盤中會把當日資料重複回傳，volume 略有不同）；另有 `df[~df.index.duplicated(keep='first')]`（`history.py:536`）。
  - 【事實】repo adapter 沒有去重。重複列會變成兩個同日期的 `PriceBar`（`yfinance.py:349-362`）。`app/data/quality.py:66-77` 有 `_check_duplicates`，但我沒有追到是否每條路徑都呼叫它，【未查證】。
- 盤中半成品 bar：
  - 【推論】盤中呼叫時，Yahoo 當日那根 bar 是即時值，adapter 沒有擋。若快照在台北交易時段內抓，最後一根會是未完成的 bar。
  - 【事實】repo 有 `latest_completed_session`，截止假設為 15:00（`app/data/freshness.py:87-111`），註解說明是安全側假設、未驗證。
- 事後修訂：
  - 【事實】草案自己已承認 yfinance 沒有 PIT 版本（`work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md` 的 N-22c(3) 條目，見 grep 所列）。
  - 【未查證】`^TWII` 歷史收盤被 Yahoo 事後改動的頻率、是否只動最近幾日。

**題 4：現有程式怎麼取、怎麼轉（grep 結果，路徑相對 `apps/stock-desk/backend/`）**
- 取數：
  - `app/data/providers/yfinance.py:122-126` 的 `INDEX_SYMBOL_METADATA`，`^TWII` 對應 `("TW","TWD")`。
  - `app/data/providers/yfinance.py:192-240` 的 `get_index_daily_bars`，狀態固定為 `BACKUP`。
  - `app/data/providers/yfinance.py:267-321` 的 `_fetch`：`period1` 為 start 的 UTC 午夜，`period2` 為 end 的 UTC 午夜加 86400 秒，`interval=1d`。
  - `app/services/index.py:303` 的 `"TW": BenchmarkIndex(series_symbol="^TWII", ...)`。
  - `app/api/deps.py:146-173` 組裝 `IndexProviderBridge(_default_yfinance())`。
  - `app/leverage/index_mapping.py:251, 259` 與 `app/playbook/service.py:9, 64` 也引用 `^TWII`。
- 轉日期：只有 `yfinance.py:385` 一處。
- `tz_convert`/`normalize`：後端沒有任何一處對 `^TWII` bar 使用。`normalize` 的命中都是字串、Decimal 或套件內部，與日期無關。
- 其他 `Asia/Taipei` 的使用（`app/data/panel.py:307`、`app/scheduler.py:170`、`app/data/freshness.py:110` 等）與 `^TWII` bar 日期無關。
- 驗證現況：
  - `yfinance.py:33-45` 記載 2026-08-16 CEO 本機驗證「`^TWII` 回 7 根 fresh bar」，只驗證有資料，沒有記錄時間戳記時刻。
  - `scripts/verify_market_data.py` 在 backend/scripts 下找不到。
  - `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md:470` 寫了要在 CEO 本機核對 `^TWII` 與官方資料的逐日日期（含 `gmtoffset`、`exchangeTimezoneName`），回報裡沒有看到結果，【未查證】是否已跑。

### 3. 驗證（做了什麼、哪些被擋）

- 讀了：`yfinance.py` 全檔、`tests/fixtures/yfinance_chart_twii.json`、`tests/fixtures/README.md`、`tests/test_providers_yfinance.py` 相關段、下游 frame/engine/drag 的日期取用、`freshness.py`，並用 grep 覆蓋指定關鍵字。
- 離線腳本：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/tzcheck.py`，用 repo `.venv` 執行，輸出已列在題 1、題 2。
- 外部查證：
  - `https://raw.githubusercontent.com/ranaroussi/yfinance/main/yfinance/{utils.py,scrapers/history.py,version.py}` 可取得，版本為 1.7.0，原始檔放在 scratchpad `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/yf/`。題 2、題 3 的套件行為引用的是這份原始碼。
  - **被擋：`query1.finance.yahoo.com`（Yahoo chart 端點），CONNECT tunnel 回 403。** 我只試了一次，沒有重試或繞過，所以沒有任何真實 `^TWII` 資料，也沒有抓取時間與筆數可回報（0 筆）。
  - **被擋：`api.github.com`**，回 403，訊息為「此 session 未啟用該 repo 的 GitHub 存取」。因此沒查 yfinance 的 issue。
- 沒讀 `.env`；`data/*.db` 只用 `ls -la` 看過檔案大小與時間，沒讀內容、沒取 sha256。
- repo 狀態：沒有修改任何檔，`git status --short` 無輸出。
- 沒跑 repo 的測試套件，因為本次只查證。

### 4. 下一步（建議 quant 或 TA 在 V26-01 補的項目）

1. **揭露：** 在 V26-01 另一面 ③ 明寫兩件事。
   - repo adapter 以 UTC 日期推導 bar 日期（`yfinance.py:385`）。
   - 它只在時間戳記的台北時刻不早於 08:00 時等於台北交易日；其平移風險是整段性的，不是個別日期的。
2. **快照檢查格（無需連外，可機械檢查）：** 快照要保留原始時間戳記（epoch）與 `meta.exchangeTimezoneName`、`gmtoffset`。閘門 (c) 加一項檢查，全部 bar 的台北時刻必須相同且落在 [08:00, 18:00)，否則視為日期慣例異常，不執行重放。`exchangeTimezoneName` 必須是 `Asia/Taipei`。
3. **對照格：** 以官方日曆（閘門 (b) 已有）核對快照日期集合。特別看兩個方向的訊號：
   - 若平移，會同時出現「週一的 bar 變成前一個週日」與「快照多出週日、少了週五」。
   - 有週日 bar 或整段與官方交易日差一天，就是平移，不是個別缺 bar。
4. **測試格（給 dev-lead/qa）：** 補兩個 adapter 契約測試，用離線構造的時間戳記：
   - 台北 09:00 應得到同日。
   - 台北 00:00（UTC 前一日 16:00）應被拒絕或明確標示，而不是靜默回傳早一天。
   同時在 README 把 fixture 標明仍是合成。這個測試是為了讓風險「被看見」，不是證明 Yahoo 的真實行為。
5. **adapter 層的改善（需 tech-architect/dev-lead 決定，data-engineer 可實作）：**
   - 讀取 `meta.exchangeTimezoneName`/`gmtoffset`，以台北當地日期取代 UTC 日期。
   - 去重或對重複日期明確回報。
   - 不要把「某欄位 null 的列」靜默丟掉，改成以明確的異常計數揭露。
   - 擋掉盤中半成品的當日 bar（快照時間須晚於收盤並給足緩衝）。
6. **真實驗證（需要有網路的環境，CEO 本機或網路政策開通）：** 對 `^TWII` 抓一次公開日線歷史，輸出每根 bar 的原始 epoch、台北時刻、`meta` 時區欄位，並與 TWSE 官方（`MI_5MINS_HIST` 或 FMTQIK）逐日比對。涵蓋 3 件事：日期是否一致、颱風假與補班日是否有 bar、最近數日收盤與官方是否一致。這一步做完才能把【未查證】改成【事實】。若付費或額度不足，依章程列方案升級 CEO，目前這項是公開歷史、不需付費。
7. **N-81 的狀態建議：** 維持「不擋閘門 (d)、D_v」，但把第 2 項的快照檢查納入閘門 (c) 的機械檢查，才能讓「整段平移」變成會被攔下的情況，而不只是事後觀察到 X2 異常。

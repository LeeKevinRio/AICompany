# B-6、B-7 資料面事實查證（data-engineer）

- 審查者：data-engineer（只讀，未修改檔案；僅 stat 兩個 .db）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# B-6、B-7 資料面事實查證（data-engineer）

只讀查證，未修改任何檔案。事先宣告草案、r2'、風控文件、探測指令檔都只讀。路徑皆在 `/home/user/AICompany/apps/stock-desk/backend/app/` 下，除非另註。

## 1. 本次結論

**B-6（指數是否套用分割門檻）**
- 現有程式裡，單日異常門檻有三處，**都只對個股成立，沒有任何一處對指數執行**。
- 指數沒有型別或旗標，只靠代號的 `^` 前綴和獨立的組裝路徑區分。
- 指數路徑目前**只檢查幣別，不檢查價格形狀**。
- R-8 更正與 `unresolvable_missing_data` **只存在於規格，程式裡 0 筆**。

**B-7（B4 的族群歸屬時點）**
- 族群成員名單有 PIT 歷史：市場 DB 的 `pit_classification_rows` 加 `pit_snapshot_runs.recorded_at`，只增不改。
- 目錄庫（`security_directory`）的 `sector` 欄是會被覆寫的現況值，**不是 PIT**。
- **沒有回補機制**，最早只能從市場 DB 第一個 `classification` ok run 的日期起留存。
- 本沙箱看不到 CEO 本機的實際起點。
- 官方是否提供歷史版本，repo 內查不到，**需 CEO 本機探測**。
- 無論選 T 或 T−h，σ_d(T−h) 都需要 T−h 當時的名單，所以兩種選法的最早可用日期一樣。

## 2. 各部門回報

### B-6

**問題 1｜現有異常偵測／分割／減資推論在哪、判準、是否對指數執行**

| 位置 | 判準 | 對象 | 對指數執行？ |
|---|---|---|---|
| `sectors/universe.py:278-284` 呼叫 `sectors/index.py:72-78`（`daily_limit_breaches`）；常數在 `sectors/definition.py:67-70` | 視窗內任一日 \|收盤對收盤\| > 0.10 + 0.01 = 11%，歸類為「③ 公司行動」 | 上市普通股成員（母體 `market` 來自 listing 加 classification 快照） | 否 |
| `portfolio/price_change.py:49-55`、`:314-317`（F7） | TW 持倉單日漲跌幅 \|pct\| > 10 + 1，則不顯示漲跌欄 | `Position` 列 | 否。`positions/models.py:37-42` 明文拒絕 `^` 代號當持倉 |
| `data/quote_quality.py:372-395`（`_price_limit_problem`）；`data/quote_params.py:62`（`IMPLAUSIBLE_MOVE_BAND` = 0.5） | 盤中報價超出來源回報的漲停／跌停價，或在沒有漲跌停欄位時偏離前收超過 50% | `QuoteKey(symbol, board ∈ {tse, otc})` 的盤中報價 | 否。報價鍵是個股加板別，沒有指數通道 |

- 【事實（`backtest/splits.py:1-16`）】`backtest/splits.py` 是 walk-forward 切窗，**與股票分割無關**。要避免與事先宣告 §4.7 的「`walk_forward_splits`」混淆。
- 【事實（`data/quality.py:22-27`）】`QualityIssueType` 只有五種：缺交易日、重複列、幣別不符、未來日期、OHLC 不合理，**沒有跳動／分割類型**。
- 【事實】`check_price_bars` 在 `app/` 內沒有任何呼叫者（grep 只命中定義）。這與 2026-10-17 補查回報發現 1 的結論一致。
- 【事實（`data/price_guard.py:42-48`）】`usable_price` 只判斷「有、有限、> 0」，沒有範圍判斷。
- 【事實】事先宣告 L1025 與 ADR-0027 L362-364 的 `SPLIT_SUSPECT_ABS_RETURN`（10% 加 1%）**在 `app/` 內尚未實作**：`app/outlook`、`dirdef` 都不存在，grep 為 0。
  - 現有可複用的只有 `universe.py` 那一支，它被 ADR 的「固定門檻」描述所沿用。
- 【事實（事先宣告 §1.2、L419；`sectors/index.py:1-15`）】族群不是指數序列。它是成員的等權籃子，現行程式也是臨時由成員收盤算出。
  - 所以「族群指數」在資料層沒有獨立序列，門檻實際是套在成員上。
  - 資料層唯一的指數序列是大盤的 `^TWII`（`services/index.py:302-305`）。

**問題 2｜L1025 對指數有沒有定義；指數怎麼區分**
- 【事實】L1025 與 ADR-0027 L362 的措辭是「單日超過漲跌幅限制加容差」。
  - 該常數被描述為台股一般漲跌幅限制，且「不看該標的當天實際有沒有漲跌幅限制」。
  - 對指數沒有對應的限制概念，條文也沒有說明指數適用與否。
  - 若不改條文而直接套用，字面上就是把 11% 套在 `^TWII` 的單日報酬上。
- 【事實】`PriceBar`（`data/interface.py:46-67`）沒有證券類型、`is_index` 或 `instrument_type` 欄位。指數只靠下列方式區分：
  - 代號 `^` 前綴：`positions/models.py:42`、`leverage/index_mapping.py:65`、`data/diagnose.py:228`。
  - 組裝路徑：`api/deps.py` 的 `_default_index_resolver` 建 `MarketDataService(scope="index")`，再包 `IndexSeriesService`。`service.py` 的 `scope` 是 `"equity" | "index"`（`:267-285`）。
  - 白名單：`data/providers/yfinance.py:118-126` 的 `INDEX_SYMBOL_METADATA`（`^NDX`、`^GSPC`、`^TWII`）。
  - 資料狀態：永遠 `backup`（`services/index.py:129-137`）。
- 【事實（`data/admission.py:192-198`、`api/deps.py` 該函式說明、`data/service.py:345`）】
  - 指數路徑傳入 `admit_any_shape`，明確**不查形狀**，只查幣別（ADR-0024 D-4）。
  - 所以現況下，指數序列內的任何價格異常，進快取前沒有任何檢查。
- 【事實（`data/providers/yfinance.py:371-376`）】yfinance 轉接器遇到值為 None 的列會跳過，不內插。
  - 但跳過只寫 `logger.debug`，不會出現在回傳物件。
  - 缺的日子會落到結算端的 `missing_bar_after_wait` 路徑，不會被默默補值。
- 【事實（`data/cache.py:39-53`、`:215-219`）】快取是 `ON CONFLICT … DO UPDATE` 覆寫，主鍵 `(symbol, market, trade_date)`。
  - 沒有修訂歷史，舊值被覆蓋後就不在了。
- 【推論】指數是成分股的加權平均，單日 ±11% 需要大部分成分股同時接近漲跌停，觸發應當極罕見。
  - 但這是推論，**未用任何 `^TWII` 歷史資料驗證**。
  - 要不要在登記前先數一次「歷史上 ^TWII 超過 11% 的天數」，會碰到風控「任何真實指數結果被看過之前」的限制，歸 quant 與風控決定，資料面可執行但我沒做。

**問題 3｜更正（R-8）與 `unresolvable_missing_data` 路徑在哪**
- 【事實】兩者只在規格：
  - ADR-0027 L259-262、L359-360、L369-370；
  - 事先宣告 §6.4 L1062-1070；
  - 草案 L605。
  - **程式碼、SQL 都是 0 筆**（grep `unresolvable_missing_data`、`correction_job_id`、`supersedes_id` 於 `apps/` 皆無）。
- 【事實（ADR-0027 L49、L246、L280、L356）】規格上，大盤記錄當下把實際用到的 bars 擷取進 `forecast_input_series`（含 `content_sha256`、`source`、`source_status`、`bars_json`、`captured_at`），並揭露 `index_source_status=backup`。結算端大盤用「擷取的指數路徑」。
- 【推論】資料面能支撐「指數資料確認有誤 → R-8 更正或 `unresolvable_missing_data`」，條件有二：
  1. 擷取序列落實為 append-only。因為現況快取會覆寫，沒有擷取序列的話，更正前後的差異無從稽核。
  2. 「確認有誤」要有可執行判準。現況沒有第二來源可比對：官方指數端點（T1-08：`MI_5MINS_HIST`、`MFI94U`、FinMind）還沒探測，Yahoo 是唯一來源。
- 【資料面可行性，不做選法建議】對指數異常，目前能機器偵測的只有：
  - OHLC 不合理（`quality.py:167-189`，需接線）；
  - close ≤ 0 或非有限（`price_guard.py`）；
  - 重複列、未來日期（`quality.py`，同樣需接線）；
  - 單日報酬超過事先登記的門檻（需新寫，指數專用數值是新常數）。
- 【事實】以上沒有一項目前對指數執行。

### B-7

**問題 4｜族群成員名單怎麼存、有沒有 PIT、最早從何時留存**
- 【事實（`data/market_panel.py:119-135`、`:180-187`；`data/interface.py:276-283`）】
  - `pit_snapshot_runs`：每次擷取一列，欄位有 `kind='classification'`、`session_date`、`recorded_at`（由 store 自己的時鐘填，呼叫端不能傳入）、`source`、`status`、`content_hash`。
  - `pit_classification_rows(content_hash, symbol, sector_code, sector_name)` 是內容定址，跨日相同內容只存一份。
  - 每個 symbol 只有**一個** `sector_code`，來自 `t187ap03_L` 的「產業別」兩位碼。**沒有細項（sub-industry）**，`sector_sub`、`theme` 不在 v1（事先宣告 §1.2）。
- 【事實（`market_panel.py:28-50` 檔頭、同檔的 append-only 觸發器、`:~123-181`）】`pit_classification_rows` 與 `pit_snapshot_runs` 都有 `BEFORE UPDATE/DELETE` 觸發器。
- 【事實（`data/panel.py:900-922` `_visible`、`:833-851` `snapshot()`）】
  - 決策日 t 可見的列：`session_date ≤ t` 且 `recorded_at ≤ cutoff(t)`（t 當日 23:59:59 Asia/Taipei）。
  - classification 取最近一次 ok run，缺日沿用，並回傳 `run_id`、`session_date`、`recorded_at`、`carried_sessions`。
  - 這四個值足以記進 `baseline_predictions_json`（風控底線 ①）。
  - `MAX_CARRY_FORWARD_SESSIONS = 5`（`market_panel.py:~103-110`）：超過的樣本視為無效，但這條由消費端（panel）判讀，store 本身不執行。
- 【事實（`directory/store.py:35-47`、`:236-275`）】`security_directory.sector` 是 `UPDATE` 覆寫的現況值，附 `sector_as_of`，沒有歷史、沒有 `recorded_at ≤ cutoff` 語意。
  - 它的涵蓋也只有上市。
  - **不能當 B4 的 PIT 依據。**
- 【事實（`sectors/store.py:108-172`）】`sector_board*` 表只存各族群彙總，不存完整成員名單。完整 S_T 要從 PIT 的 listing、classification、bars 經 `sectors/universe.py:177-236`（`eligible`）重算。
- 【事實（`scheduler.py:25-31`、`:168-173`、`:658-675`）】
  - 每個週一至週五 17:30／19:30／21:30（Asia/Taipei）擷取四種 kind，啟動時也補跑一次。
  - 同一日的 classification 在 17:30 之後才有，所以對決策日 T 的 cutoff（23:59:59）可見。
- 【事實（`services/pit_snapshot.py` 檔頭）】暖身回補 CLI 只寫 `bars`，**不補 listing、classification、dividend_announce**。
- 【事實（`data/interface.py:403-410`）】`MarketSnapshotProvider` 的端點「只回答今天」。
- 【最早留存起點】
  - 程式面：第一個 `kind='classification' AND status='ok'` 的 run 的 `session_date`，也就是排程第一次成功擷取的日子。**不可能更早。**
  - 本沙箱：`stat` 顯示 `data/stock-desk-market.db` 為 98,304 bytes、mtime 2026-10-04 15:09，且被 `.gitignore`（`backend/.gitignore:8`）。
  - 【推論】依大小，這份很可能幾乎沒有累積資料。但我沒讀內容，**無法確認**，也不代表 CEO 本機的狀態。
  - 實際起點需要 CEO 本機的 DB 診斷。探測指令檔 §6.6.3 E 段（約 L1827-1830）已會印出 listing、classification 的 `MIN(session_date)`，不需新增。

**問題 5｜能不能回補歷史族群成員**
- 【事實】repo 內沒有任何官方來源提供歷史版本的證據：
  - 探測指令檔的 `t187ap03_L` 探測（§6.5.3，約 L1658-1693）只為驗證 ETF 是否有列與產業別分布，沒有探測歷史或版本。
  - 該檔 L721、L883 的通則是「多數資料集沒有版本戳；無版本戳者只能靠長期自存快照」。
  - `twse_snapshot.py:100-112` 註解只說明 `t187ap03_L` 是「公司層、當日」的資料。
- 【結論】官方是否有歷史版本：**需 CEO 本機探測**。
- 【事實，限制】
  - 就算回補得到歷史產業別，它**不具** `recorded_at ≤ cutoff(T)` 的 PIT 保證，與 ADR-0012 的 PIT 紀律衝突。
  - 這個衝突的性質同探測檔 L1862 對除權息回補的說明，屬新資料源決策，歸 tech-architect（ADR）與 quant，data-engineer 不自行採用。

建議加入探測指令的項目（**我沒有改該檔**）：
1. **FinMind 公司基本資料類資料集**（名稱為印象：`TaiwanStockInfo`，另 `TaiwanStockInfoWithWarrant`）。先用 datalist 確認名稱，再看：
   - 有沒有日期或更新時間欄位；
   - 同一 `stock_id` 是否有多列（即產業別變更的版本）；
   - 能否用 `start_date`／`end_date` 查歷史；
   - 其產業別分類是否與 TWSE 兩位碼同一套（逐檔比對 `t187ap03_L`，統計不一致檔數）。
   - 授權與額度沿用 §0.4 的 `fm_quota`。
2. **`t187ap03_L` 本身**：
   - 欄位清單中有沒有出表日期、資料日期類欄位；
   - swagger 中該路徑有沒有日期或版本參數（不連網的 swagger 文字搜尋即可，同 6.1 的做法）；
   - 回應標頭的更新時間（`Last-Modified`、`Date`）。
3. **產業別異動的官方公告**。兩項都先以瀏覽器 Network 面板取得實際 URL，只做一次，做法同探測檔 L690：
   - 證交所「產業分類／產業別調整」的公告或沿革頁，有沒有生效日清單；
   - 公開資訊觀測站類的公司基本資料變更紀錄。
   - 兩者路徑我都沒有任何出處，只列查證目標。
4. **本機 DB 診斷增列**（唯讀複本，沿用 §6.6.3 的 `mode=ro`、`PRAGMA query_only=ON`）：
   - 第一個 ok classification 與 listing run 的 `session_date`（已有）；
   - 累積至今 `COUNT(DISTINCT content_hash)`（`kind='classification' AND status='ok'`），也就是產業別名單實際改過幾次；
   - 以相鄰 content_hash 比對，統計 symbol 在 h=3、h=5 窗內 `sector_code` 不同的筆數。
   - 這一項不碰價格與結果，只回答「T 與 T−h 歸屬不同」的頻率，可在看任何 B4 結果之前完成。

**B4 兩種選法在資料面的可行性與限制（不給選法建議）**

兩種選法共同的前提：
- 事先宣告 L438 已規定 B1、B4 的 σ_d(T−h) 一律用 S_{T−h}，所以**不論選哪種，都需要 T−h 當時的 listing 與 classification 快照**。
- 因此 B4 最早可用的 T ＝ 第一個 ok 快照的 session ＋ h 個交易日。兩種選法在這一點沒有差別。
- 若 T−h 沒有可見的 ok classification run，`eligible()` 回傳空母體（`universe.py:183-191`），該 T 的 B4 為「不可用」。

| 項目 | 選 T 的歸屬（`panel.as_of(T)`） | 選 T−h 的歸屬（`panel.as_of(T−h)`） |
|---|---|---|
| 風控底線 ① `recorded_at ≤ cutoff(T)` | 成立 | 成立（cutoff(T−h) ≤ cutoff(T)） |
| 能記進 `baseline_predictions_json` | 可記 `run_id`、`session_date`、`recorded_at`、`carried_sessions` | 同左 |
| 與 S_{T−h} 一致（底線 ②） | **不保證**：該股的 `sector_code` 可能在 T−h 與 T 之間改變，或該股在 T−h 未進 S_{T−h}（上市未滿 60 日、成交金額／成交日數不足、代號 20 未排名、代號 91 排除）。籃子歸屬與成員不一致時的處理須由 quant 登記 | 該股所屬族群與 S_{T−h} 的分類來自同一份快照，歸屬一致。該股仍可能因合格條件不足而不在 S_{T−h} 內 |
| 不可用筆數（底線 ③） | 多一種不可用原因：g_T ≠ g_{T−h} 或不在 S_{T−h}(g_T) | 只有族群不合格（成員 < 5、覆蓋 < 90%）或不在 S_{T−h} |
| 兩種選法的不可用筆數何時可算 | 全部只用 PIT 快照，不用價格結果，需累積 ≥ h 個交易日的 ok 快照後才能算 | 同左 |

- 【推論】兩種選法的不可用筆數目前都算不出來，因為累積量未知，需先有 CEO 本機的診斷結果。
- 【事實】沒有為了選擇而需要看 B4 結果的資料依賴。

## 3. 驗證

- 做過的事：
  - Read：`data/quality.py`、`data/price_guard.py`、`backtest/splits.py`、`sectors/universe.py`、`sectors/index.py`、`sectors/definition.py`、`portfolio/price_change.py`、`services/index.py`、`data/providers/yfinance.py`、`data/market_panel.py`（檔頭、schema、`load_panel_frames`）、`data/panel.py`（`snapshot`、`_visible`）、`directory/store.py`、`scheduler.py`、`data/cache.py` 與探測指令檔、r2'、風控文件。
  - Grep：關鍵字全 `app/` 掃描。
  - `stat`：僅對兩個 `.db`，取大小與 mtime，不讀內容、不取 sha256。
  - Read：只讀 B-6、B-7 查證需要的草案行段（L430-446、L1018-1032、L1225-1235、L289-300、L800-818、L1060-1072）與 ADR-0027 L355-372。
- 沒做的事：
  - 沒有連網。
  - 沒有讀 `.env`。
  - 沒有讀 `*.db` 內容。
  - 沒有跑測試，也沒有執行任何程式。
  - 沒有修改任何檔案。
- 限制：
  - 所有「官方是否有歷史版本」「CEO 本機 DB 的累積起點」都無法在本環境得知。
  - 【推論】標示的項目沒有被實測。
  - 行號以我讀到的工作樹為準；草案（v0.9 未 commit）quant 仍在修改，行號可能漂移。

## 4. 下一步

1. **quant-researcher**
   - B-6：本文件的事實足以讓你具名提案時回答「指數序列是否套用門檻」。須同時處理兩件事：
     - 風控兩條底線；
     - L1025 與 ADR-0027 L362 目前沒有寫明指數是否適用。
   - B-7：登記歸屬時點時，要同時寫明「該股不在 S_{T−h} 時」的處理（風控底線 ②）。
   - 兩項都須在凍結前、看任何真實指數或 B4 結果前定案。
2. **tech-architect**
   - 對齊 A-32：「套用的序列」。
   - 若指數異常改走資料品質，需決定 `check_price_bars` 是否接線、以及指數路徑是否仍維持 `admit_any_shape`（ADR-0024 D-4）。
   - 決定 `forecast_input_series` 是否為 append-only（現況快取會覆寫）。
   - 對齊 A-34 `baselines.py` 的歸屬時點。
   - 判斷歷史回補產業別是否能進 PIT（涉及 ADR-0012 的 PIT 紀律）。
3. **CEO（本機）**：跑探測指令檔既有的 §6.6.3 E，並依上面第 5 點加入我列的 1～4 項（我沒有改該檔）。需要時請 coordinator 指派我新增 §6.9。
4. **風控**：可審查上述事實是否足以支撐凍結前定案。我沒有給選法建議。

**相關檔案**
- `/home/user/AICompany/apps/stock-desk/backend/app/sectors/universe.py`、`sectors/index.py`、`sectors/definition.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/portfolio/price_change.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/quality.py`、`data/service.py`、`data/admission.py`、`data/market_panel.py`、`data/panel.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/index.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/directory/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`
- `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`

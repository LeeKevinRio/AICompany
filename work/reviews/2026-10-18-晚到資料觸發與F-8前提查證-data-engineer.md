# 晚到資料觸發可行性與 F-8 前提查證（data-engineer，唯讀）

- 審查者：data-engineer（本次唯讀）
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

本次只做唯讀查證。我沒有修改任何檔案，也沒有 commit。我沒有讀 `.env`，沒有碰 `data/*.db`，也沒有連網。

**問題 1：可行，但要改成「更正作業端輪詢」，而且觸發預期幾乎不會發生。**
- 「這次新寫入了哪些 session」不需要靠 upsert 前後差異。市場 DB 只有 INSERT，沒有 upsert，也沒有 `ingest_runs` 這張表。對應的紀錄是 `pit_snapshot_runs`。一筆 bars run 剛好對應一個 `session_date`，所以 run 本身就是答案。
- 觸發應由「寫主 DB 的更正作業」在啟動時，經 `MarketPanelReader` 唯讀市場 DB 產生。寫入端（`pit_snapshot`、`MarketPanelStore`）不要動，也不要讓它碰主 DB。
- 不需要另設跨檔事件或回呼介面，只需要在 `MarketPanelReader` 加一個唯讀方法。
- 條文需要補三點，否則會誤觸或漏觸：
  - 要比對到個股層級。
  - 要套 `is_final`。
  - 晚到要用時間先後來定義。
- 有兩個結構性發現，tech-architect 會想知道：
  - 現行管線幾乎不會產生「過了當天才補到的 bars」，所以 `void_late_data_count` 預期近 0。
  - 現行的冪等略過會擋掉「定案後 run」，這和 N-4 的前提有關。

**問題 2：F-8 的事實前提無法在 repo 內查證，維持未查證。**
- 週六補行交易日的探測指令只存在 CEO 代跑的指令稿（§6.2），repo 內沒有任何回填結果。
- 我能確認的只有程式行為：
  - adapter 對週末 bar 不過濾、不特判，來源給什麼就存什麼。
  - 排程只在週一到週五跑。
  - 「週末沒有 session」在我們的管線上是結構性成立的，和台股是否真的休市無關。

## 二、逐題回答

### 問題 1（N-4 晚到資料觸發）

**(a) bars run 能不能可靠知道新寫入了哪些 session**

【查證】
- 沒有 `ingest_runs`。同類紀錄是 `pit_snapshot_runs`（`apps/stock-desk/backend/app/data/market_panel.py:122-134`）：
  - 欄位有 `run_id AUTOINCREMENT`、`kind`、`session_date`、`recorded_at`、`source`、`status`、`row_count`、`expected_count`。
  - bars 內容在 `market_daily_bars`，主鍵 `(run_id, symbol)`（`market_panel.py:156`）。
- 寫入只有 INSERT（`market_panel.py:511`、`533`；`record_symbol_backfill` 在 `:657-687`）。五張表都有 append-only trigger（`:218-236`）。所以沒有「upsert 前後差異」可比，也不需要。
- 一個 run 只能有一個 `session_date`（`market_panel.py:490-497` 的 docstring）。因此「這筆 run 寫了哪個 session」直接讀 `session_date` 即可，不必推算。
- `run_id` 單調遞增、永不重用，是規範性要求（`docs/adr/0012-stock-desk-族群動能與全市場日線.md:267`）。可以拿來當游標。
- 失敗的 run 的 `session_date` 是 NULL（`app/services/pit_snapshot.py:139-147`），不能歸屬到任何 session。
- 每日擷取的冪等略過：
  - `_already_ok_today` 在 `pit_snapshot.py:151-153`，bars 的呼叫在 `:201-202`。已有該 session 的 ok run 就不再寫。
  - 所以活路徑上同一個 session 通常只會有一筆 ok run。
- 擷取的候選日是牆上時鐘的當天（`app/data/providers/twse_snapshot.py:203-204`），再用 FinMind 抽樣交叉比對（`:316-350`）。排程只跑平日（`app/scheduler.py:170-171`）。
- ADR-0012 規定不回填：`docs/adr/0012-…:277`、`:296`、C-10（`:796`）。暖身 CLI 在 D0 之後拒絕執行（`pit_snapshot.py:373-375`）。

【推論，已由上述程式支持】
- 在現行管線下，過了當天才補到的 session s 的 bars 幾乎不會出現。能出現的只有兩種：
  1. 第一次擷取是 partial（覆蓋率低於 0.98，見 `pit_snapshot.py:251-260`）或 failed，同一天晚一點的 19:30 或 21:30 才變 ok。這發生在隔日結算之前。
  2. 人為補寫，目前沒有這條路。
- 因此 `void_late_data_count` 預期近 0。這個觸發要寫，是為了防未來新增回填路徑，不是現況會頻繁發生。
- 個股層級的缺漏不會被補：
  - ok 的門檻是 0.98，所以最多 2% 的標的在該 ok run 裡沒有 bar。
  - 之後同 session 會被冪等略過，所以那一檔的 bar 永遠不會晚到。
  - 因此「session 層級有新 run」不等於「這檔股票有晚到資料」，配對必須查 `market_daily_bars (run_id, symbol)`。
- 現行冪等略過和 A-78 有一個交互作用【事實加推論】：
  - 事實：TW 的 `publish_cutoff` 是 15:00（`app/data/freshness.py:110`）。排程時間都是 17:30 以後，但各排程也都有啟動時單次執行（`app/scheduler.py:24-25`）。
  - 推論：啟動或手動擷取若發生在 15:00 前並寫出 ok run，之後 17:30 的擷取會被略過。於是「定案後的 run」不會出現，而消費端依 A-78 又只認定案後的 run。
  - 這會讓當天沒有可用 bars。ADR-0027 L1395 已承認「當天沒有定案後的 run 補寫」會造成缺日，但沒有說明是這個冪等略過造成的。
  - 這一點我沒有實測盤中資料是否真的被標 ok，只是程式路徑可達。

**(b) 能不能由「讀市場 DB 的一方」產生觸發，要不要另設介面**

【查證】
- C-7（`docs/adr/0012-…:793`）規定持倉資料鏈不讀市場 DB。預測帳是另一條鏈，ADR-0027 L35 明寫市場 DB 只被唯讀、C-8 不變。
- 先例已存在：
  - ADR-0027 A-77 第 12 項（`docs/adr/0027-…:556`）寫的是「每日結算排程用單一函式偵測，不以 run 與事件的先後篩選，涵蓋跨檔窗口」。
  - 第 7 項的寫入函式也在持有主 DB 寫入交易時，經 `MarketPanelReader` 重算（`docs/adr/0027-…:511`）。
- `MarketPanelReader` 以 `mode=ro` 開啟，缺檔讀為無 run（`market_panel.py:1085-1089`）。ADR-0026（庫存版本化軟刪除）沒有對這條讀取路徑加限制（我 grep 該檔只看到市場 DB 的備份與路徑守門規則，見 `docs/adr/0026-…:332-334`、`:416`）。

【判斷】
- **可以由讀端產生。** 不建議從寫端產生，理由有三：
  - 寫端要寫主 DB，會造成跨檔寫入和 C-8 的邊界問題。
  - A-78 已寫「不改 `pit_snapshot`」。
  - 寫端沒有 outcome 資訊，無法判斷哪些列受影響。
- **介面：**
  - 不需要新的事件、回呼或跨檔寫入。
  - 只需要在 `MarketPanelReader` 加一個唯讀方法。字串 `STOCK_DESK_MARKET_DB_PATH` 仍只在 `market_panel.py`，不違反 C-8 與 T-3。
  - 新方法要列入 ADR-0027 的實作約束，並受 ADR-0012 T-3 的 import-graph 測試涵蓋。

**(c) 最小落地條文建議（給 tech-architect，需他定稿）**

> （N-4 晚到資料的觸發；讀端輪詢，寫端不動）
> 1. **誰偵測：** 更正作業，在作業啟動、讀入觸發的同一步。只經 `MarketPanelReader` 新增的唯讀方法讀市場 DB，例如 `ok_bars_runs_between(run_id_exclusive, run_id_inclusive)`，一條 SQL，回傳 `run_id`、`session_date`、`recorded_at`、`source`。`pit_snapshot` 與 `MarketPanelStore` 不得寫主 DB，也不得呼叫更正作業。
> 2. **讀哪裡、讀多少：** 啟動時先取一次 `run_max = MAX(run_id)`。掃描範圍是 `(W, run_max]`。
>    - W 是最近一個「已有 `forecast_correction_job_end` 列」的作業在 `triggers_json` 標頭記下的 `market_scan_to`；首次為 0。
>    - 沒有 end 列的中斷作業，依 ADR-0027 L299 由下一個作業完整重跑，W 不因它前進。
>    - 只取 `kind='bars'`、`status='ok'`、`session_date IS NOT NULL` 的 run。
>    - 每筆再經 `is_final(TW, session_date, recorded_at)`（ADR-0028 CS-17）過濾，不得自行比較時戳。
> 3. **配對（三項都成立才算觸發）：**
>    - 主 DB 有鏈尾列 `status ≠ resolved`，且結算窗 [T, T+h] 含 `session_date`。
>    - 該列的標的（個股或族群成員）在該 run 有一列 `market_daily_bars (run_id, symbol)`。
>    - 該 run 的 `recorded_at` 晚於該鏈尾列的 `computed_at`。這是「晚到」的定義：結算當下該 run 還不存在。
> 4. **觸發項：** `{kind: source_revision, run_id, recorded_at, session_date}` 寫入 `triggers_json`。觸發身分以 `(run_id, recorded_at)` 成對為準。
> 5. **避免重複：**
>    - 游標 W 保證同一個 run 不被兩個完成的作業重複使用。
>    - 寫入函式驗證：新作業的 `market_scan_from` 等於前一個已完成作業的 `market_scan_to`；同一個 `(run_id, recorded_at)` 不得出現在兩個作業的 `triggers_json`。
>    - 因為有第 3 項的時間先後條件，沒有觸發而未前進的游標，下次重掃不會誤觸發：舊 run 對之後才產生的作廢列，不算晚到。
> 6. **還原保護：** 若 W 大於目前市場 DB 的 `MAX(run_id)`，視為市場 DB 被還原。記 WARNING，不靜默重掃，交 N-5 的 `db_restored` 流程處理。ADR-0012 D-2（`docs/adr/0012-…:267`）已要求還原不得重編 `run_id`，這條是縱深防禦。

**三個邊界要寫明，否則 `void_late_data_count` 會低報或語意混淆：**
- 這個觸發只涵蓋「個股與族群成員」。大盤的 T+h bar 來自 `services.index`，不經市場 DB（ADR-0027 M-8，`docs/adr/0027-…:198`）。大盤晚到資料要另外處理，或明寫不涵蓋。
- 除權息因子晚到走「因子修訂」觸發，來源在主 DB（ADR-0016 D-5.2），不是這條。
- `late_data_kinds` 的 `basket_member` 來自 listing 與 classification 的 run，不是 bars run。這條條文沒有涵蓋，要另行決定。
- 目前 outcome 沒有記錄「結算當下市場 DB 看到的 `run_max`」（settlement 欄位清單在 `docs/adr/0027-…:287`）。第 3 項只能比時間，兩邊都是 store 時鐘（同機，偏差小，但不是零）。若要精確比對，建議 outcome 加 `settle_source_run_max`，這是 schema 決策，交 tech-architect。

### 問題 2（F-8：週末作為正面休市證據）

F-8 出現處：
- 事先宣告 `work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md:1461`（§9.2 一帶）。
- ADR-0027 `docs/adr/0027-…:396`、`:401`、`:520`。
- 風控 `work/reviews/2026-10-17-A-15-事先宣告v0.10修正單項確認-風控.md`（「凍結前 F-8」一段）。

**查證到的（repo 內程式與文件）**
- 台股有無週六補行交易日：repo 內沒有答案。
  - `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的 §6.2（`:913`、`:1208-1222`）是要 CEO 代跑的指令稿。三個證據是官方休市表、FinMind `TaiwanStockTradingDate`、本機 DB 週末 bar。
  - `work/` 底下沒有任何回填結果，我也找不到 `twse_holiday_*` 或 `FMTQIK` 的存檔。
  - 官方休市日表尚未接入程式（repo 無 holiday 相關檔案）。
- adapter 對週末 bar：不過濾、不特判。
  - `app/data/providers/` 沒有任何 `weekday` 判斷。我 grep 全部 `app/` 的 `weekday()`，只在以下位置出現：
    - `app/data/calendar.py:85`
    - `app/data/freshness.py:95`、`:101`
    - `app/data/intraday_session.py:115`
  - `twse.py:171` 與 `_util.py:24-34` 只解析民國日期，不過濾星期。
  - `app/data/quality.py:85-100` 只檢查未來日期、重複與日曆缺漏。
  - 結論：來源若回傳週六 bar，會被照存。
- 日曆與新鮮度對週末的假設（和 F-8 直接相關）：
  - `app/data/calendar.py:74-85`：已知範圍內以「有沒有 bar」為準，範圍外才用週一到週五規則。
  - `app/data/freshness.py:80-103`：新鮮度只認週一到週五，週六補行時會低報過舊（方向保守）。
  - `app/data/intraday_session.py:115`：`weekday() >= 5` 一律視為非交易日。
  - `app/data/cache.py:358-378`：`market_has_session` 以任何 live 序列有該日 bar 為正面證據，預設排除 demo。
- 排程只跑平日：`app/scheduler.py:152`、`:170-171`（`mon-fri`）。市場 DB 的擷取候選日是牆上時鐘當天（`twse_snapshot.py:203-204`），並用 FinMind 交叉比對（`:316-350`）。

**推論（有程式支持，但不是對真實市場的查證）**
- 若真有補行的週六：
  - 排程不會在那天擷取，市場 DB 就沒有那天的 session。
  - 這正是風控 v0.10 單項確認指出的缺口：週末加上「市場 DB 沒有 session」會把真實交易日直接確認為 X2。
  - 只有人為在週六啟動才可能寫入。屆時 FinMind 抽樣若有該日 bar，候選日會通過認證；`market_panel.py:466-557` 與 `pit_snapshot.py` 都沒有週末檢查，這筆 session 會被照寫，並走 A-75 (iv) 的證據矛盾路徑。
- 所以對我們的管線而言，「週末沒有 session」是結構性成立的，和台股是否真的休市無關。這使得 F-8 的前提不能由我們自己的資料來驗證。

**我記憶中的外部資訊（未查證，信心中等，不可引用）**
- 我記得台股早年有週六半日交易，已於 2000 年代初取消；現行規則是週六補班日證券市場照常休市；颱風停市沒有補行交易日。
- 我無法連網確認，也無法確認近年有無例外。必須以官方休市表頁面的說明文字、FinMind 長區間日曆、FMTQIK 為準，不可據此回覆 F-8。

## 三、驗證

- 本次沒有跑測試，也沒有產生執行輸出。全部結論來自讀取程式與文件，已列檔案與行號。
- 沒有連網，沒有讀 `.env`，沒有開啟或 `stat` 任何 `data/*.db`。
- 我沒有檢查本機 DB 有無週末 bar，這項只能由 CEO 代跑 §6.2 C，並要排除 demo 資料。demo seeder 會寫一整格平日，見 `cache.py:358-378` 的註解。
- 限制：
  - 預測帳（`app.forecast`、`app.outlook`）在 repo 內尚未實作，所以問題 1 的配對條文只對照 ADR 文字，沒有可執行的程式可驗。
  - `is_final`、`session_calendar.py` 也尚未實作，只在 ADR-0028 CS-17 有定義。

## 四、下一步

**給 tech-architect**
1. 採用上列 (c) 條文，或改寫後定稿。需要決定四件事：
   - `MarketPanelReader` 新增唯讀方法的簽章。
   - `triggers_json` 標頭的 `market_scan_to` 欄位。
   - 是否在 outcome 加 `settle_source_run_max`。
   - 還原保護是否併入 N-5。
2. 在 N-4 條文明寫三個邊界：不涵蓋大盤、不涵蓋因子、不涵蓋 `basket_member`。同時在 `void_late_data_count` 的說明標註「現行管線下預期近 0」，避免日後把 0 當成異常。
3. 裁示 `pit_snapshot` 的 `_already_ok_today` 與 A-78 的衝突：
   - 選項 A：接受現況，缺日由 L1395 的揭露涵蓋。
   - 選項 B：把「已有 ok」改為「已有定案後 ok」。這要改 `pit_snapshot`，和 A-78「不改 `pit_snapshot`」衝突，需要修訂。
   - 我建議先確認實際影響範圍（啟動時盤中資料是否會被標 ok），再裁示。
4. 條文定稿後交我實作 reader 方法與 fixture 測試（離線）。

**給 quant**
1. F-8 的事實前提目前沒有任何查證結果，請維持「待辦」，不要寫成已驗證。
2. 以風控 v0.10 的兩條處理為準：
   - 官方表涵蓋 d 時，表上列為交易日的週末不觸發 (i)。
   - 官方表未涵蓋期間，週末不得單獨構成直接確認，列待查證。
3. 重放（F-6）區間若含近年，需要 CEO 的 §6.2 A、B、C 三項回填結果才能下結論。就算全無週六交易日，結論也只能寫成「某區間內未見」，不能寫「不會有」。
4. 請注意：我們的排程結構使週末永遠沒有 session。X2 (i) 的「週末」證據因此不具鑑別力，只能靠官方日曆來區分。

**給 coordinator / CEO**
- 請 CEO 代跑 §6.2（任何時間皆可，約 1 次請求），並把官方休市表頁面的說明文字、網址與讀到日期貼回，才能補上 F-8 的事實依據。

**相關檔案（絕對路徑）**
- `/home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/pit_snapshot.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/twse_snapshot.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/freshness.py`
- `/home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md`
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`
- `/home/user/AICompany/work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md`

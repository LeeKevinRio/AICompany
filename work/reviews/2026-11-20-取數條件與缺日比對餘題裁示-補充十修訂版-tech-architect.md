# 取數條件與缺日比對餘題裁示、補充十修訂版

- 審查者：tech-architect
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **第一組（強制更新與核對）**：data-engineer 的規格我同意採用，但附四個條件。
  - 等價測試要擴大到四種起始狀態。
  - 加一道 AST 守門。
  - `_judge_bars` 的標籤由我定。
  - 例外不在 `app.services` 內捕捉。
- **競態（A-2）列為已知限制。** 上一版第 1 點 (c)「T 日 bar 必然定案」說得太強，已改正：定案一律由 recorder 依 D-3 第 2 點判定，核對不能證明定案。另外新增驗證層的時間戳事後檢查（第 4 點 (e)），可以辨識其中一部分這類紀錄。
- **「強制更新成功但回應不含 T 日列」（A-3）算成功**，維持現狀，列為已知限制。只加一行 log 提示，不加日期條件作為寫入條件。
- **23:10 每次都強制更新（A-4）**，不先讀帳。
- **啟動補跑的時段（A-5）不改。** 但上一版 S-20a 的 22:09 測試點寫錯了：22:09 加 3 分鐘是 22:12，不在不補跑的時段內，依規則應該補跑。已改為 22:06 與 22:07。
- **`lookback_days`（A-6）採 (a)**：scheduler 從 recorder 取兩個常數相加後傳入。
- **第二組（一鍵檔）**：
  - 主 DB 旁有 `-wal` 或 `-journal` 就 STOP；複本前後主 DB 的大小或修改時間不同也 STOP，用來處理 TOCTOU。
  - 拿掉 `PRAGMA query_only=ON`。
  - 不加對象行，也不加尾端旗標。
  - 重跑有明確界線。
  - N-6、N-8 合併前必辦。
- 會改到補充八字面的裁示，全部寫在補充十新增的第 7 點。**補充八、補充九都不改。**
- **沒有需要 CEO 決定的事項**；所有裁示 CEO 都可以推翻。

## 各題裁示

### 第一組

**A-1 規格：同意，附四個條件。**
- **替代方案我評估過，不採用。**
  - 把 ladder 抽成共用函式：`get_daily_bars` 會出現在 diff 裡，「逐位元不變」就得靠測試證明。
  - 另建一個 `cache_first=False` 的服務實例、看回傳狀態：會破壞 `test_f9b0_service_scope.py` 的建構點守門，也會多出第二套節流。
- **條件一：等價測試（T-EQ）至少涵蓋四種起始狀態**：空快取、coverage 完整時的增量抓取、快取被幣別閘拒絕、即時回答被幣別閘拒絕。比對對象是快取的三張表，逐欄相同。
- **條件二：AST 守門。** 新方法不得呼叫 `_try_session_fresh_cache`、`_layer_zero_answer`、`_fall_back_to_cache`、`_cached_result`、`_refused_answer`。
- **條件三：標籤（A-7 的第一項由我定）。**
  - 即時回答與讀回沿用既有的 `provider`、`incremental_readback`，等價測試才比得起來。
  - 強制更新前檢查快取用的標籤，新增 `force_refresh_cache`。
  - 不改 `_judge_bars` 的 docstring，因為既有行不得刪改；新標籤寫在新方法的 docstring。
  - 我 grep 過 tests，沒有找到把標籤釘成全集的測試，只有個別流程斷言標籤序列。dev-lead 實作前再確認一次。
- **條件四：例外的處理。** `force_refresh_benchmark` 只對結構性缺漏回 `ok=False`（沒有服務、沒有穿透方法、讀回為空），其他例外一律往外拋，由 scheduler 依 (i) 捕捉 `Exception`。
- **不設來源限制。** 指數路徑目前只有一個 provider；要加備援，本身就得先修 ADR。
- **逐條對照**：
  - K-2：`app.services` 不 import `app.forecast`，另加 import graph 測試。
  - K-3：scheduler 進核心仍只經 recorder，新函式在 `app.services`。
  - K-10：見 A-6。
  - K-11：harness 不經 scheduler。
  - S-4a：recorder 拿到的仍是 `load_market_benchmark` 本身。
  - ADR-0009 layer 0：新方法是另一個明示的消費者，`get_daily_bars` 的 layer 0 規則一字不動；ADR-0010 的「不得繞過」只適用 `data_refresh`。
  - ADR-0024 幣別閘：即時回答、讀回、事前快取檢查三處都過閘。
  - `test_f9b0_rejection.py`：新方法回傳 `LiveRefreshOutcome`，不建構 `ProviderResult(..., rejection=)`，`index.py` 也不得建構，守門不受影響。

**A-2 競態：列為已知限制（第 1 點 (e)），並改正說得太強的句子。**
- 改正的兩處：
  - 第 1 點 (c) 改為「定案由 recorder 判定，核對不取代也不證明定案」。
  - 第 2 點的前提句改為「每個寫入點都以請求時刻寫入，但不保證只會被更晚的時刻覆寫」，並刪掉「前提不成立就移到 recorder」的推論。
- 不採互斥鎖：跨行程無效。也不移進 recorder：會改到 `code_digest`、造成定案條件雙重定義，這兩點先前已否決。
- **驗證層能否辨識：部分可以。**
  - 依第 3 點的時段分析，正式路徑上每一筆 `late = 0` 紀錄，都出自 t0 不早於 T 日 22:10 的執行。
  - 所以快照中 T 日 bar 的 `as_of` 早於 22:10，就一定不在核對的涵蓋內。
  - `as_of` 落在 22:10 到 t0 之間的情形，帳內沒有存 t0，辨識不了。`forecast_run.started_at` 晚於 t0，不能拿來代替。
  - 這寫成第 4 點 (e) 的義務。

**A-3 T 日列缺：算成功，維持現狀，列為已知限制（第 1 點 (f)）。只加一行 log，不加寫入條件。**
- 若把「B 的日期等於最近一個已收盤的 session」設為寫入條件，平日休市（例如農曆年）每晚都會被跳過，「最近一次執行」那一行會停住，RC-264 的通知就會誤觸發。而且這條件只能用平日規則，等於把日曆邏輯帶進寫入條件，與補充八「核心不偵測缺日」的處理不一致。
- `freshness.latest_completed_session` 的判斷：
  - 它是 ADR-0009 既有的平日規則，不是交易日曆，也不是休市日資料。
  - scheduler 已經 import `TW_POLICY`，可以用它，但只限用於那一行 WARNING log，不得當寫入條件。這樣不違反補充八第 3 點 (c)。
- 另一個情形會被核對擋下：快取裡原本有 17:45 取得的 T 日列、這次回應卻沒有 T 日列時，B 是那根舊的 T 日列，`as_of` 早於 t0，核對不成立，這次執行被跳過。這個行為正確，寫進第 1 點 (f)。

**A-4 23:10：每次都強制更新，不先讀帳。**
- 理由：
  - scheduler 讀帳（`has_record`）就是經 store 進入核心，與 K-3 的界線衝突。
  - 多一次請求的代價很小。
- 快取與快照時間戳不同沒有壞處：驗證層一律讀帳內快照（D-3 第 5 點禁止用事後重抓的資料取代快照）。如果 Yahoo 在 22:10 到 23:10 之間修正了收盤，隔天的快照會帶著新值，正好讓第 4 點 (a) 的 X3 查得到。

**A-5 補跑時段：第 3 點的時段不改。** 我對照了 `late_cutoff_at`（T 的次一日 00:00）：

| 啟動時刻加 3 分鐘落在 | 這次補跑的 T | 寫出的結果 |
|---|---|---|
| 平日 [22:10, 24:00) | 當日 | 未記錄就寫 `late = 0`；已記錄就是 `no_new_session` |
| 平日 [00:00, 13:30)、週末 | 前一個交易日 T′ | 未記錄只會寫 `late = 1`；已記錄就是 `no_new_session` |
| 平日 [13:30, 22:10) | 不補跑 | — |

- 平日休市日 22:10 之後補跑，T 是前一個 session，也只會寫 `late = 1`。
- 上一版 S-20a 的 22:09 測試點與規則矛盾，改為：13:27、13:30、22:06 不補跑；13:26、22:07、22:10、週六 16:00 補跑。

**A-6 `lookback_days`：採 (a)。**
- scheduler 本來就 import recorder，傳入 `recorder.FETCH_CALENDAR_DAYS + recorder.FETCH_SLACK_DAYS`，`market` 也傳 `recorder.MARKET`。
- K-10 管的是 recorder 的公開函式與 job；長度不是時間點，job 本身仍然沒有參數，所以 K-10 不受影響。
- 不採 (b)：會有兩處真相。不採 (c)：`app.services` 反向依賴 `app.forecast`。
- 加測試釘住傳入值等於 recorder 兩個常數之和。

**A-7：只有標籤要由我定，已定在 A-1。**
- 測試 helper 是否支援等價測試、`test_scheduler*.py` 是否釘住呼叫序列，交給 dev-lead 實作前確認。
- scheduler 自己的測試可以隨 job 的修改一起改；S-20a 的「不改就全過」只適用於 `app/data` 與 `app/services` 的既有測試。

### 第二組

**B-1：偵測到 `-wal` 或 `-journal` 就 STOP；TOCTOU 也要處理。**
- 補充八 (c) 要求「直連 `mode=ro` 須實證 `-wal`、`-shm` 不受影響」。devops-sre 自己的實測顯示 `-shm` 會被改動或新建，所以不能用「接受並記載」帶過。
- TOCTOU 的處理：backup 前後各記一次主 DB 的大小與修改時間（只用 stat，不開連線）。有任何不同，或出現了 `-wal`、`-journal`，就先刪複本、再 STOP。
- 兩種情形共用一句新的固定 STOP 句，送風控。我建議的字面：`STOP: the database is in use or changed during the copy (a -wal or -journal file, or a change of the file). Close every stock-desk window and run again; if this repeats, tell the coordinator.`

**B-2：拿掉這句 PRAGMA。** (c)「SQL 只能 …」的字面涵蓋所有 SQL 敘述，PRAGMA 也算；它本來就是冗餘的，因為複本已經以唯讀開啟。

**B-3：程式不處理。**
- data-engineer 實測：凌晨查詢時，官方當月資料已含前一天。檢查期間的迄日是執行日前一日。
- 加上限縮條件的話，也會遮掉月底真的多出來的一列。
- 改由 coordinator 註記：「快取有、官方無」只有迄日這一天時，在知悉事項註明「可能是官方當月資料還沒有這一天」，結果代號不改判、不據此重跑（第 7 點 (f)）。

**B-4：這一支不加對象行。**
- 讀法：版本行 `gap_check version=1` 的輸出，一律指快取現況。
- 日後讀快照的工具必須用不同的版本行；它的白名單在動工前送風控（第 7 點 (c)）。
- 這樣不改白名單，就不會改到 CEO 看得到的內容。

**B-5：可以重跑，但有界線（第 7 點 (d)）。**
- 只有前一次的結果是 `calendar_unavailable`，或有未檢查月份時，才可以重跑。
- 兩次之間至少隔 1 小時；有結果的執行最多 3 次。
- STOP 或 ERROR、沒有出結果的執行，不計入次數。
- 每一次都逐字 commit。
- 判讀時，缺日清單取所有輸出的聯集，已檢查月份也取聯集；後一次不得取代前一次。
- 閘門以第一份有結果的輸出為準。

**B-6：不加旗標行。** coordinator 在知悉事項寫明 `cache_range_end` 是否早於 `period_end`；讀法寫進 CEO 說明文件（第 7 點 (e)）。

**B-7：**
- 兩項自加的前置檢查（git 乾淨、HEAD 已在 origin）都保留，乾淨檢查另外要涵蓋 `.bat`。
- 自定解讀第 2、5、7 項：照現狀接受。
- 第 3 項限速：首次執行前改為基本間隔 8 秒、失敗後 20 秒，停手條件不變（依 data-engineer 的建議；請求數不變）。
- 第 9 項：不加進度句，由 CEO 說明文件提醒要等幾分鐘。

**B-8：**
- 合併前必辦：N-6（`\d` 全部改 `[0-9]`、`render` 加 `isascii`），以及 N-8 的 `.bat` 納入乾淨檢查。
- N-4 不加句子：看到 `result=` 就代表複本已刪；寫在 CEO 說明文件即可。
- N-7 可以之後再辦。
- N-8 的「先 pull」寫在 CEO 說明文件。

**B-9：** B-1、B-2、B-4、B-5、B-6、B-3 這幾項都只寫在補充十第 7 點，屬於對補充八第 5 點的收緊與讀法，補充八不動。

**補充九：不需要改。** 第 7 點 (d) 指向補充十第 2、3 點，仍然成立。

## 補充十完整最終版全文

**檔頭補充紀錄行**（取代先前補充十那一行）：

- 補充紀錄：2026-11-20 append 補充十（T 日 bar 的取得時點、強制更新與核對的介面、啟動補跑的時段、結算 P(T) 的讀法與驗證層義務、18:10 的判準與取樣、執行狀態段的最近一次執行、帳外缺日比對的讀法與收緊；tech-architect 裁示；第 1 點為已知限制，第 2、3、5 點為收緊，第 4 點為釐清與驗證層義務，第 6 點為揭露，第 7 點為補充八第 5 點的讀法與收緊；不改本文、補充八與補充九的字面、事先宣告 v0.32、規則檔、定義物件與已登記雜湊；第 2、3 點不改 `code_digest` 涵蓋的原始檔，第 6 點改 `app/forecast/report.py`，第 7 點不改 `app/`；依風控 RC-255～RC-264 附條件核可，第 6 點字面依 RC-259 定稿，本次修訂的第 1 點 (c)、(e)、(f)、第 2 點的前提句、第 4 點 (e)、第 7 點 (a)、(d) 經風控確認；CEO 可推翻；來源 `work/research/2026-11-19-收盤定案時點與啟動補跑路徑-data-engineer.md`、`work/research/2026-11-19-非最終收盤對登記效度的影響-quant.md`、`work/reviews/2026-11-19-收盤定案時點重新定案與補充十-tech-architect.md`、`work/reviews/2026-11-19-收盤定案時點定案與補充十判定RC255至RC264-風控.md`、`work/research/2026-11-19-指數強制更新方法規格-data-engineer.md`、`work/reviews/2026-11-20-帳外缺日比對一鍵檔審查-qa.md`、`work/research/2026-11-19-缺日比對一鍵檔資料面審查-data-engineer.md`、`work/reviews/2026-11-19-帳外缺日比對一鍵檔交件-devops-sre.md`、〔本次裁示轉存檔〕、〔風控確認報告〕）

**正文**：

## 補充十：T 日 bar 的取得時點、啟動補跑的時段、結算 P(T) 的讀法、18:10 的判準、最近一次執行與帳外缺日比對的讀法（2026-11-20）

- 決策者：tech-architect。
- 來源：
  - `work/research/2026-11-19-收盤定案時點與啟動補跑路徑-data-engineer.md`
  - `work/research/2026-11-19-非最終收盤對登記效度的影響-quant.md`
  - `work/reviews/2026-11-19-收盤定案時點重新定案與補充十-tech-architect.md`
  - `work/reviews/2026-11-19-收盤定案時點定案與補充十判定RC255至RC264-風控.md`
  - `work/research/2026-11-19-指數強制更新方法規格-data-engineer.md`
  - `work/reviews/2026-11-20-指數強制更新方法規格交件-data-engineer.md`
  - `work/reviews/2026-11-20-帳外缺日比對一鍵檔審查-qa.md`
  - `work/research/2026-11-19-缺日比對一鍵檔資料面審查-data-engineer.md`
  - `work/reviews/2026-11-19-帳外缺日比對一鍵檔交件-devops-sre.md`
  - 〔本次裁示轉存檔〕、〔風控確認報告〕
  - 另讀事先宣告 v0.32 第 877～898、1018～1020、1888、2017 行；`feat/nm5-wiring` 的 `app/scheduler.py`、`app/forecast/recorder.py`、`app/forecast/store.py`、`app/services/index.py`、`app/data/service.py`、`app/data/freshness.py`、`app/outlook/inputs.py`；`feat/gap-check-oneclick` 的 `backend/scripts/gap_check.py`。
- 性質：
  - 第 1 點為已知限制。第 2、3、5 點為收緊，方向都是寫得更少。第 4 點為事先宣告 §6.3 的讀法釐清，以及驗證層 ADR 的義務。第 6 點為揭露。第 7 點為補充八第 5 點的讀法與收緊。
  - 不改本文、補充八與補充九的字面、事先宣告 v0.32、規則檔、定義物件與已登記雜湊。
  - 第 2、3 點只改 `app/scheduler.py`、`app/services/index.py` 與 `app/data/service.py`，都不在 `code_digest` 涵蓋範圍內。
  - 第 6 點改 `app/forecast/report.py`，這個檔在 `code_digest` 涵蓋範圍內。它與補充九第 4、5、8 點對 `store.py`、`report.py` 的改動同在接線 PR，都在第一筆 `forecast_run` 之前。
  - 第 7 點只改 `backend/scripts/gap_check.py` 與它的測試，不改 `app/`。
  - 依風控 RC-255～RC-264 附條件核可；第 6 點的字面依 RC-259 定稿；第 1 點 (c)、(e)、(f)、第 2 點的前提句、第 4 點 (e)、第 7 點 (a)、(d) 經風控確認。CEO 可推翻。

1. **已知限制**（知悉）
   - (a) 現行取數路徑上，快照中 T 日 bar 的 `as_of` 與 `fetched_at` 是同一個值：最後一次覆寫該快取列的那次請求的發出時刻。D-3 第 2 點的「取較早者」在這條路徑上不是兩個獨立證據。
   - (b) 沒有第 2 點時，平日 17:45 的 `sector_board_refresh`，或白天開啟的頁面，會先把 T 日 bar 抓進共用快取；22:10 判 `HAS_LATEST_SESSION` 而沿用，紀錄的 `base_close` 就是當時取得的值。
   - (c) D-3 第 2 點的「重抓一次」在現行路徑上讀的是同一份快取，不是重抓。本補充不改 recorder。T 日 bar 是否定案，一律由 recorder 依 D-3 第 2 點以該 bar 的時間戳判定；第 2 點的核對是額外的條件，不取代、也不證明定案。
   - (d) Yahoo 在 22:10 回傳的 T 日收盤是否為最終值，無法查證。紀錄依事先宣告第 1018 行仍是定案紀錄；之後與獨立來源不同的情形，依第 4 點由驗證層處理。此處的「定案」是事先宣告第 1018 行的技術定義，不代表該值已是來源的最終值。
   - (e) **核對之後的競態**：
     - `price_bars_cache` 的每一個寫入點都以請求發出時刻寫入 `as_of`，但覆寫是最後寫入者勝，不比較新舊；scheduler 與 API 可以是不同行程。
     - 一個早於 t0 發出、晚於強制更新才寫入的請求，可能在第 2 點的核對成立之後、recorder 讀取之前，把 T 日列的時間戳改回早於 t0 的時刻。
     - 此時紀錄用的是那個請求取得的 Yahoo 回應；是否定案照 (c) 由 recorder 判定。被破壞的只有「不早於 t0」。
     - 本補充不以互斥鎖處理（跨行程無效），也不把核對移進 recorder。
     - 帳內不存 t0，這類紀錄只能依第 4 點 (e) 部分辨識。
   - (f) **強制更新成功，但回應不含 T 日列**（例如 Yahoo 那一列有 null，被整列略過）：
     - 快取中日期最大的一根是 T−1，它的時間戳已被這次強制更新重寫，核對成立。
     - recorder 以 T−1 為最新定案 bar：T−1 已有紀錄時記 `no_new_session`；沒有時寫一筆 `late = 1` 的 T−1 紀錄（同補充八第 2 點 (b)）。
     - 這不屬於第 2 點的失敗，這次執行照常留下 `forecast_run`。核心不偵測缺日（補充八第 3 點），scheduler 只依第 2 點記一行 WARNING。
     - 快取中原本已有較早取得的 T 日列、而這次回應不含 T 日列時，B 是那根舊的 T 日列，時間戳早於 t0，核對不成立，這次執行被跳過。
2. **每次執行的取數條件**（收緊）
   - job `forecast_record` 每次執行（22:10、23:10、啟動補跑）依序做五件事：
     1. 補充九第 3 點的目標核對；
     2. 以系統時鐘取 t0；
     3. 強制更新；
     4. 核對；
     5. 呼叫 recorder。
   - 強制更新：
     - `app.data.service.MarketDataService` 新增 `refresh_daily_bars_live(symbol, market, start, end)`，回傳 `LiveRefreshOutcome`。
       - 它依 `get_daily_bars` 的 ladder 段規則走一次：代號准入；快取被幣別閘拒絕時整段重抓，否則用既有的增量起點；依 ladder 順序呼叫 provider；過幣別閘；寫快取；`record_attempt`；增量讀回；`record_fetch`（只限 complete 的回答）；全部 provider 失敗時 `record_attempt`。
       - 不經 layer 0 與 cooldown 判斷，也不走任何回落到快取的路徑。
       - `ok` 為真，若且唯若某一個即時來源的回答通過幣別閘、已寫入快取，而且增量讀回（若有）通過；其餘一律為假，不讀快取當答案。
       - 只新增，不抽取，也不改既有的任何一行。複製的 ladder 以等價測試守住。
     - `app.services.index`：
       - `IndexSeriesService` 新增同名的穿透方法。
       - 新增 `force_refresh_benchmark(resolver, *, market, lookback_days)`，沒有 `now`、`as_of`、`start`、`end` 參數。
       - `end` 是系統時鐘的台北日期，`start` 是 `end` 減 `lookback_days`。它對 `MARKET_BENCHMARK[market]` 的序列呼叫上述方法；`ok` 為真才以 `get_cached_bars` 唯讀讀回同一範圍，回傳日期最大的一根。
       - 結構性缺漏（沒有服務、沒有穿透方法、讀回為空）回報為不成功；其他例外往外拋。
     - scheduler：
       - 用同一次 `get_index_resolver()` 取得的物件，供強制更新與 recorder 共用。
       - `market` 傳 `app.forecast.recorder.MARKET`，`lookback_days` 傳 `FETCH_CALENDAR_DAYS + FETCH_SLACK_DAYS`，都取自 recorder 模組，不另設常數。
       - `app.services` 不 import `app.forecast`。
     - 既有函式的行為與簽章不變。不改 `app/data/providers/yfinance.py` 與 `app/data/cache.py`。
     - 每次執行都做強制更新，不先讀帳判斷 T 是否已有紀錄（K-3）。22:10 已寫入時，23:10 的那次更新是多餘的請求，會讓快取中 T 日列的時間戳與帳內快照不同；驗證層一律讀帳內快照（D-3 第 5 點），不受影響。
   - 核對：以下三項都成立，才呼叫 recorder。
     - (i) 強制更新沒有拋出 `Exception`，而且 `ok` 為真；
     - (ii) 讀回有日期最大的一根 B；
     - (iii) `B.as_of ≥ t0`。
   - 核對不成立時：不呼叫 recorder，記一行固定英文 WARNING，正常返回。不得沿用快取。不捕捉 `BaseException`。固定字面如下：
     - (i) 或 (ii) 不成立：`forecast_record: the live index refresh did not succeed; the run is skipped and the cache is not used`
     - (iii) 不成立：`forecast_record: the newest cached index bar predates this run's start; the run is skipped`
   - 核對成立、但 B 的日期早於 `TW_POLICY.latest_completed_session(t0)` 時：照常呼叫 recorder，另記一行 WARNING：`forecast_record: the refreshed index series ends before the latest weekday session (an exchange holiday or a row missing at the source); the run continues`。
     - `latest_completed_session` 是 ADR-0009 既有的平日規則，不是交易日曆，也不是休市日資料。
     - scheduler 只能把它用在這一行 log，不得用作寫入條件，也不得為此在 `app/` 內新增日曆（補充八第 3 點 (c)）。
   - 以上三行都不含路徑、價格、日期與標籤。
   - 被跳過的執行不寫 `forecast_run`；漏記的 session 依補充五第 1 點 (d) 進入 F-2 分子。第 1 點 (f) 的情形不屬於被跳過。
   - 不變的部分：recorder、store、`load_benchmark is load_market_benchmark`（S-4a）、K-3、K-10、K-11、S-3，以及 D-3 第 2 點的定案定義。
   - 核對放在 scheduler 的前提：`price_bars_cache` 的每一個寫入點都以請求時刻寫入 `as_of`。
     - 唯一的 SQL 寫入點是 `PriceBarCache.put`；正式路徑上的呼叫端只有 `MarketDataService.get_daily_bars`，以及本點新增的方法。
     - 這個前提不保證「之後只會被更晚的時刻覆寫」。例外是第 1 點 (e) 的競態，已列為已知限制。
     - 日後新增的寫入點若使這個前提不成立，須先修訂本點。
   - 本點與第 3 點，必須和 job `forecast_record` 的註冊在同一次合併落地，不得拆成後續 PR（RC-255）。
3. **啟動補跑的時段**（收緊 D-3 第 7 點與補充九第 7 點 (d)）
   - 啟動時刻加 3 分鐘若落在週一至週五台北時間 [`TW_POLICY.session_close`（13:30）, 22:10)，不設啟動補跑，只依排程執行。
   - 落在其他時刻，照 D-3 第 7 點補跑，並適用第 2 點。
   - 理由：
     - 13:30～15:00 的補跑，會讓 T 日列以非定案的時間戳進入快取，並記一次 `inputs_not_ready`；
     - 15:00～22:10 的補跑，會以 22:10 之前取得的值寫下 `late = 0` 紀錄。
   - 各時段的補跑可能寫出的結果（釐清）：
     - 週一至週五 [22:10, 24:00)：T 為當日；未記錄時寫 `late = 0`，已記錄時為 `no_new_session`。
     - 週一至週五 [00:00, 13:30) 與週六、週日：最新定案 session 是前一個交易日 T′，`created_at` 已過 T′ 的 `late_cutoff_at`；未記錄時只會寫 `late = 1`，已記錄時為 `no_new_session`。
     - 因此正式路徑上每一筆 `late = 0` 紀錄，都出自 t0 不早於 T 日 22:10（台北）的執行。依第 5 點加入 18:10 之後，改為 18:10。
   - 與事先宣告第 1020 行「啟動後 3 分鐘補跑」的字面不同；方向是寫得更少，不改登記內容。
   - 驗證報告揭露：第 2、3 點自第一筆紀錄起即生效；另依 RC-258 揭露其餘事項，並含第 1 點 (e)、(f)。
4. **結算 P(T) 的讀法與驗證層 ADR 的義務**
   - 聲明：本點起草時，帳內沒有任何紀錄，起草者與審查者都沒有看過任何暫定對照。
   - 讀法（釐清；風控確認即 R10-5 原意）：
     - 事先宣告第 1888 行規定，結算的 P(T) 一律取 `start_price_json`，也就是結算當下讀取的 T 日收盤；`base_close` 結算不讀。
     - 第 2017 行「P(T) 是記錄當下的那一根（`start_price_json`）」，屬於「確認有誤」的適用單位，指的是寫入 `start_price_json` 時所用的那一根，與同句「已結算列的 P(T+h) 是結算所用的那一根」對稱。它不指 `forecast_record` 寫入當下的 bar，也不指 `base_close`。
     - 兩行一致，不改事先宣告。
   - 驗證層 ADR 的義務：依 D-8 第 5 點起草時必須納入，標準要在任何暫定對照之前固定。
     - (a) `base_close` 與之後快照中 T 日收盤不同時，一律視為 §6.3 X3 觸發，走查證程序；不得默默剔除，也不得一律作廢。
     - (b) 結算的 P(T) 不取 `base_close`：有獨立來源時用獨立來源的值；沒有時用結算當下讀取的值，並列為異常待查證。
     - (c) 只有「確認有誤，而且 5 個觀察交易日內取不到正確值」才作廢，維持 §6.3 字面；預測端不更正。
     - (d) 揭露三件事：`base_close` 與正確值不同的筆數、ε 的分布，以及輸入含已確認有誤 bar 的預測筆數。
     - (e) 時間戳的事後檢查（對應第 1 點 (e)）：
       - 對每一筆 `late = 0` 紀錄，以帳內快照中 T 日 bar 的 `as_of`，對照 T 日的第一個排程時刻（台北 22:10；依第 5 點加入 18:10 之後為 18:10）。
       - 早於該時刻的，表示第 2 點的核對沒有涵蓋它，要計數並揭露。不得僅以此剔除或作廢：定案依 D-3 第 2 點另判，收盤與正確值不同時依 (a) 處理。
       - 介於該時刻與 t0 之間的，帳內沒有 t0，無法辨識，要照實揭露這項限制。`forecast_run.started_at` 晚於 t0，不得代替 t0。
   - 核心不改：`scoring.py` 的 `base_close_differs` 只屬暫定對照，結果是「無法對照」並標出原因，不是驗證統計，也不寫入任何表。驗證層不得把暫定對照的「無法對照」當成剔除或作廢的依據。
   - 期限：本點在接線 PR 合併之前 append。
5. **18:10 的判準與取樣**（收緊 D-3 第 7 點）
   - 起訖（預先固定）：
     - 第一次取樣之前，coordinator 以 commit 在 `work/` 記錄取樣起算日。起算日須晚於該 commit 的日期，只寫日期，不寫任何取樣結果。
     - 取樣期間是起算日（含）起，依 TWSE 官方交易日計的連續 59 個交易日，第 59 個交易日為迄日。
     - 期間不得因結果延長、縮短或中止。一個 ADR 版本只允許一個取樣期間。
   - 判準：以下全部成立才可加 18:10。
     - 期間內每一個交易日，都依 `work/research/2026-11-19-收盤定案時點與啟動補跑路徑-data-engineer.md` 第 1 節的逐字相等規則判定，18:05 這一點都零偏差，而且 T 日列從未缺列或出現 null。
     - 期間內任何一個交易日沒有完整取樣（含工具未執行或連線失敗），都視同偏差。
     - 經風控審查，並經 CEO 明確同意。
   - 期間內任何一次偏差，都表示 18:10 不加。之後若要再評估，須修訂本 ADR，並揭露包含先前偏差在內的全部取樣紀錄。
   - 加入之後，第 2 點照樣適用。
   - 取樣工具（第一次執行前完成，送風控）依風控 RC-261 (b)～(f)，要點如下：
     - 輸出每一行都 fullmatch 白名單；
     - 不 import `app.forecast`、`app.outlook`、`app.dirdef`，不經 `MarketDataService`，不開任何 `data/*.db`；
     - 適用 RC-220 的輸出途徑保證，以及 RC-221、RC-223、RC-228；
     - 要在 CEO 本機定時執行，須另以 AskUserQuestion 取得 CEO 明確同意，由一鍵檔建立排程並提供移除方式；
     - 不得以取樣值計算任何 h 日報酬或標籤；
     - 取樣結果不得用來修改已登記的 claim，也不得用來調整第 2、3 點。
   - 本點要在第一次取樣之前 append。
6. **執行狀態段的最近一次執行**（揭露；RC-259、RC-262）
   - 執行狀態段另列一行最近一次留下執行紀錄的執行，字面依 RC-259。
   - 位置：在「inputs_not_ready 日數（全部期間，台北日期）」那一行之後、F-2 段標題之前，不影響補充九第 5 點的 F-2 段順序。
   - 取值：
     - 取 `run_id` 最大的那一筆，`started_at` 換算成台北時間；`outcome` 印原值，沒有 end 列時印「沒有 end 列」。
     - 帳內沒有執行紀錄時，用第二種變體。
     - 只用現有的唯讀查詢 `store.runs()`；另立查詢時，須經 `_read()`。
   - 屬執行狀態，可以出現在 harness 的完整輸出（補充五第 5 點）。
   - 期限：在接線 PR 落地。
7. **補充八第 5 點（帳外缺日比對）的讀法與收緊**
   - (a) **主 DB 的側檔**（收緊 (c)）：
     - 取複本之前，主 DB 旁有 `-wal` 或 `-journal` 就 STOP，不開任何連線。理由：此時 backup 來源的 `mode=ro` 連線會改動或新建 `-shm`，不符合 (c) 對直接以 `mode=ro` 連主 DB 的要求。
     - 取複本前後各記一次主 DB 的大小與修改時間。backup 完成、來源連線關閉之後，兩者有任何不同，或出現了 `-wal`、`-journal`，就依 (c) 先刪除複本，再 STOP，不印結果。複本刪不掉時，以既有的「複本刪不掉」STOP 句為準。
     - 因此主 DB 一律以 `mode=ro&immutable=1` 開啟，純 `mode=ro` 不用於主 DB。
     - 這兩種情形共用一句新的固定英文 STOP 句，字面經風控定稿之後，才可以第一次執行。
     - port 8000 的檢查不涵蓋 scheduler；以本款的 STOP，以及 CEO 說明文件中的「關閉 scheduler 視窗」共同涵蓋。
   - (b) **SQL 的字面**（讀法）：(c) 的「SQL 只能 …」指對任何連線執行的全部 SQL 敘述，含 PRAGMA。對複本只執行那一句 SELECT。
   - (c) **輸出的對象**（讀法）：
     - 版本行為 `gap_check version=1` 的輸出，一律指快取現況。
     - 日後依 (i) 讀帳內快照的工具，必須使用不同的版本行；它的白名單（含是否加對象行或改鍵名）在動工前送風控。
     - 這一支不加對象行。
   - (d) **重跑**（讀法；界定 (h) 的「重跑到結果有利為止」）：
     - 只有前一次有結果的執行，結果是 `calendar_unavailable`，或 `months_unchecked` 不是 `none` 時，才可以重跑。其他結果（含沒有未檢查月份的 `gaps_found`）不得重跑。
     - 兩次有結果的執行，至少相隔 1 小時；有結果的執行至多 3 次。
     - 以 STOP 或 ERROR 結束、沒有結果的執行，排除原因後可以再執行，不計入次數。
     - 每一次執行（含 STOP、ERROR）的完整輸出，都依 (g) 逐字 commit。
     - 判讀以全部有結果的輸出為準：
       - 任何一次列出的「官方有、快取無」與「快取有、官方無」日期，都計入缺日的揭露，不得以後一次的結果取代前一次；
       - 已檢查月份取聯集；
       - 第 6 點 (a) 的知悉事項，要列出每一次的結果代號。
     - (a) 的閘門以第一份有結果的輸出 commit 為準；重跑不延後、也不提前接線 PR 的合併。
   - (e) **快取尾端**（讀法）：
     - `cache_range_end` 早於 `period_end` 時，尾端的官方交易日依 (d) 列為「快取未涵蓋」，不觸發 `gaps_found`，不加旗標行。
     - coordinator 在第 6 點 (a) 的知悉事項中，另寫明 `cache_range_end` 是否早於 `period_end`；讀法由 CEO 說明文件交代。
   - (f) **官方當月資料的發布延遲**：
     - 程式不處理。
     - 「快取有、官方無」只含 `period_end` 這一天時，coordinator 在知悉事項中照實註明「可能為官方當月資料尚未含該日」。結果代號不改判，也不據此重跑。
   - (g) git 的乾淨檢查涵蓋 `gap-check.bat`。
   - 本點在帳外缺日比對第一次執行之前 append。

- **S-20a（逐條可檢查）**
  - 第 2 點（測試）：
    - service：
      - 略過 layer 0 與 cooldown；
      - 寫入欄位（`as_of`、`fetched_at`、coverage）；
      - 回落到快取不算成功；
      - 盤中列的丟棄；
      - 增量起點；
      - 即時回答被幣別閘拒絕；
      - 被拒的快取整段重抓；
      - 讀回失敗；
      - provider 例外；
      - `complete=False` 時不記 coverage。
    - 等價：至少四種起始狀態（空快取、coverage 完整的增量、快取被幣別閘拒絕、即時回答被幣別閘拒絕）；`get_daily_bars` 走到 ladder 時，與新方法對快取三張表的結果逐欄相同。
    - AST：
      - 新方法不呼叫 `_try_session_fresh_cache`、`_layer_zero_answer`、`_fall_back_to_cache`、`_cached_result`、`_refused_answer`；
      - `force_refresh_benchmark` 沒有 `now`、`as_of`、`start`、`end` 參數；
      - `app.services.index` 不可達 `app.forecast`。
    - `git diff --numstat` 對 `service.py`、`index.py` 的刪除行數為 0。
    - scheduler：
      - 強制更新成功、而且 B 的時間戳 ≥ t0 時，呼叫 recorder 一次，而且與強制更新用的是同一個 resolver 物件。
      - 拋出例外、`ok` 為假、沒有 B、B 的時間戳 < t0：都不呼叫 recorder，記對應的固定字面，不寫 `forecast_run`。
      - B 的日期早於 `latest_completed_session(t0)`：呼叫 recorder，並記第三行。
      - `KeyboardInterrupt` 不被吞。
      - 傳入的 `lookback_days` 等於 recorder 兩個常數之和，`market` 為 `recorder.MARKET`。
    - 整合（離線）：
      - 強制更新之後，recorder 不發出第二次即時請求，有 T 日列與缺 T 日列兩種情形都是；
      - 競態以測試釘為文件化的行為。
    - 既有的 `app/data`、`app/services` 測試不改就全過；`yfinance.py`、`cache.py` 零差異。
    - recorder、store 寫入路徑、harness 三檔零差異。
    - qa 以 grep 列出 `price_bars_cache` 的全部寫入點，確認 `as_of` 都是請求時刻。
  - 第 2、3 點（RC-255）：qa 以 `git log -S` 核對兩件事：產品線上第一次註冊 `forecast_record` 的 commit，與第 2、3 點屬同一次合併；在那之前，沒有任何 commit 註冊 `forecast_record`。
  - 第 3 點（測試）：
    - 平日 13:27、13:30、22:06 啟動時不設補跑；
    - 13:26、22:07、22:10、週六 16:00 啟動時設補跑；
    - 不設補跑時，`add_job` 不帶 `next_run_time` 參數。
  - 第 4 點（RC-257）：qa 核對本補充 append 的 commit 早於接線 PR 的合併 commit。(e) 列入驗證層 ADR 的必辦清單。
  - 第 5 點：
    - qa 核對起算紀錄的 commit 早於第一份取樣輸出的 commit；
    - 期間內每個交易日都有獨立的輸出檔；
    - 判定依本點的「視同偏差」規則計算。
  - 第 6 點（測試）：
    - 兩種變體都與 RC-259 逐字相同，含說明句；
    - 位置在指定的兩行之間；
    - 沒有 end 列時印「沒有 end 列」；
    - `d4_violations` 為空；
    - harness 完整輸出可以含這一行。
  - 第 7 點：
    - 測試：
      - 主 DB 旁有 `-wal`、有 `-journal` 時：STOP，沒有開任何連線，沒有複本；
      - 注入「backup 期間主 DB 被改動」：先刪複本再 STOP，沒有結果行；刪除也失敗時，印的是複本刪不掉的 STOP 句；
      - 執行期 trace：對複本只執行那一句 SELECT，沒有 PRAGMA；
      - 白名單與日期 regex 只用 `[0-9]`，`render` 拒絕非 ASCII；
      - `gap-check.bat` 有未提交變更時 STOP。
    - qa 核對 (d)：
      - `work/` 中每一次執行都有獨立的檔案；
      - 有結果的執行不超過 3 次，間隔至少 1 小時；
      - 每次重跑的前一次結果都在允許範圍內。

### 相對上一版的變動

| 位置 | 變動 | 要不要再送風控 |
|---|---|---|
| 檔頭行、標題、來源、性質 | 加上第 7 點，日期改為 2026-11-20 | 不必（隨本次確認一併看） |
| 第 1 點 (c) | 刪掉「必然定案」，改為「定案由 recorder 判定」 | **要** |
| 第 1 點 (e)、(f) | 新增已知限制 | **要**（併入 RC-258 的揭露清單） |
| 第 2 點 | 寫明介面、核對 (i)～(iii)、三行固定 log、每次都強制更新 | 不必（log 不面向 CEO，方向是收緊） |
| 第 2 點的前提句 | 改寫，刪掉「不成立就移到 recorder」 | **要**（風控原本核可的是舊句） |
| 第 3 點 | 新增各時段可能寫出的結果（釐清） | 不必 |
| 第 4 點 (e) | 新增驗證層義務 | **要** |
| 第 5、6 點 | 不變 | — |
| 第 7 點 (a)、(d) | 新增 STOP 句與重跑界線 | **要**（STOP 句字面要定稿） |
| 第 7 點 (b)、(c)、(e)、(f)、(g) | 讀法與收緊，沒有新的輸出 | 不必 |
| S-20a | 改正第 3 點的 22:09，補上第 2、7 點的測試 | 不必 |

## 驗證

**實際讀過的檔：**
- **規格與報告**：
  - 上一版補充十全文；
  - 2026-11-19 TA 報告第 1～236 行（含補充九全文）；
  - 風控 RC-255～RC-264 報告全文；
  - data-engineer 的規格與交件全文；
  - 補充八最終版全文；
  - qa、data-engineer、devops-sre 三份一鍵檔報告全文。
- **ADR-0030**：以 grep 讀 K-2、K-3、K-10、K-11、S-4a、補充二第 1 點；細讀 D-3 第 1～7 點。
- **ADR-0009**：第 55～114 行。
- **接線 worktree**：
  - `scheduler.py` 全文；
  - `recorder.py` 第 1～76、140～151、355～444、630～676 行；
  - `store.py` 的 `now`、`runs`、`has_record`、`late_cutoff_at` 用法；
  - `outlook/inputs.py` 第 73～246 行；
  - `freshness.py` 全文；
  - `session_calendar.is_final`；
  - `service.py` 第 294～438、554～632 行；
  - `index.py` 的 import 與結構（grep）；
  - `tests/test_f9b0_rejection.py` 全文；
  - 以 grep 查 tests 中的 layer 標籤，結果只有個別流程的斷言，沒有全集清單。
- **一鍵檔**：`gap_check.py` 第 1～130、195～254、305～604 行。

**沒有讀到，或屬推論的：**
- 沒有讀 `test_scheduler*.py`、`market_service_helpers.py`、`api/deps.py`、`cache.py`、`yfinance.py`、`gap_check.py` 的 preflight 與 main 段、一鍵檔的測試檔。
- 「跨行程請求的持續時間有上限，所以實務上 `as_of` 遠晚於 15:00」是推論；但這不影響結論，因為定案一律由 recorder 判定。
- 「SQLite 在 WAL 模式下，有寫入端時會先建 `-wal`，rollback 模式會改動主檔的修改時間」：這是 (a) 第二款 stat 前後比對有效的前提，屬推論，由 devops-sre 以測試實證。
- 兩個 head（`df536340`、`443173b9`）是依 coordinator 與交件所述，我沒有用 git 核對。
- 沒有執行任何程式或測試，沒有讀 `.env`，沒有碰任何 `.db`，沒有改任何檔。

## 下一步

**coordinator**
1. 把第 1 點 (c)、(e)、(f)、第 2 點的前提句、第 4 點 (e)、第 7 點 (a) 的 STOP 句與 (d)，一次送風控。一鍵檔的另外兩句固定句也一併送：`copy_unreadable`，以及沿用自 `cg2_register.py`、核可狀態未確認的 `db_unreadable`。
2. 風控確認之後，把〔本次裁示轉存檔〕與〔風控確認報告〕兩個佔位換成實際檔名（只改這兩處），再 append。
3. 寫入時點：
   - 補充十要在一鍵檔第一次執行前、接線 PR 合併前寫入；第 5 點還要在第一次取樣前寫入。
   - 從預檢到登記完成之間，不得 push。
   - 風控若改了任何字面，退回我重出。
4. 交給 creative-lead 寫進 CEO 說明文件的事項：
   - scheduler 與 frontend 視窗都要關；
   - 執行前先 pull；
   - 約需 2～4 分鐘，期間畫面沒有輸出；
   - 看到 `result=` 就代表複本已刪；
   - ERROR 句與結果同時出現時，以結果為準，並告知 coordinator；
   - data-engineer 第九節的五句；
   - 第 7 點 (d) 的重跑規則。

**dev-lead：接線 PR 第三輪**（`feat/nm5-wiring`）
1. `app/data/service.py`：
   - 新增 `LiveRefreshOutcome`，以及 `refresh_daily_bars_live`，依規格 2.2～2.4。
   - 事前快取檢查用標籤 `force_refresh_cache`；即時回答與讀回沿用 `provider`、`incremental_readback`。
   - 不改既有任何一行，含 `_judge_bars` 的 docstring。
   - `CurrencyLookupError` 照常往外拋。
2. `app/services/index.py`：
   - 新增 `LiveRefreshService` Protocol、穿透方法、`ForcedBenchmarkRefresh`、`force_refresh_benchmark`。
   - 結構性缺漏回 `ok=False`，其他例外往外拋。
   - `LiveRefreshOutcome` 若會造成循環 import，就放在 `TYPE_CHECKING` 下 import。
3. `app/scheduler.py`：
   - `run_forecast_record` 改為第 2 點的五步，共用同一個 resolver。
   - 加三行固定字面的常數。
   - 啟動補跑改為第 3 點：不補跑時**省略** `next_run_time` 參數。在 APScheduler 中傳 `None` 會讓 job 暫停，不可以這樣做。
   - 更新模組與函式的 docstring。
4. 測試：
   - 新增 `tests/test_service_force_refresh.py`、`tests/test_services_index_force_refresh.py`；
   - 擴充 scheduler 測試；
   - 新增 import graph 測試；
   - 內容依 S-20a 第 2、3 點。
5. 實作前先確認：`market_service_helpers.py` 能否支援等價測試；`test_scheduler*.py` 有沒有釘住呼叫序列（有就隨改）。
6. PR 說明附上：`git diff --numstat` 的零刪除，以及三行 log 的字面。

**devops-sre：一鍵檔修改**（`feat/gap-check-oneclick`）
1. 第 7 點 (a)：
   - backup 前，主 DB 有 `-wal` 或 `-journal` 就 STOP；
   - backup 前後比對 `(st_size, st_mtime_ns)`，並確認沒有出現側檔；不一致時先刪複本再 STOP；
   - 新增 STOP 種類，字面待風控定稿；
   - 補測試，含刪除失敗時以哪一句為準。
2. 拿掉 `READ_ONLY_PRAGMA` 的常數與執行；改寫 trace 測試，改為斷言只執行 SELECT。
3. N-6：所有 regex 的 `\d` 改 `[0-9]`（白名單、`_ROC_DATE`、`RUN_FOLDER_PATTERN`、`read_trade_dates`）；`render` 加 `isascii`。
4. N-8：乾淨檢查納入 `../gap-check.bat`，補測試。
5. 限速改為基本間隔 8 秒、失敗後 20 秒，停手條件不變；更新常數、docstring 與測試。
6. 不加對象行、尾端旗標、清除殘留的說明句、進度句。N-7 之後再辦。
7. 改完送 qa 複審，然後才合併；第一次執行要等第 7 點 append，而且 STOP 句已經定稿。

相關檔案：
- `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- `/home/user/AICompany/work/research/2026-11-19-指數強制更新方法規格-data-engineer.md`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/data/service.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/services/index.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/scripts/gap_check.py`

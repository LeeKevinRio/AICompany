# ^TWII 缺日靜默丟列：是否登記前處理與修補時點裁示

- 審查者：tech-architect
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**這個問題不需要、也不應該在 CEO 正式登記之前改程式。** 這是 ADR-0030 已知並接受的限制。日後驗證層只靠已保存的快照加上帳外的官方交易日曆，就判定得出缺日；現有 schema 沒有缺少登記後就補不回來的欄位。我建議採 (a)＋(d)：登記前不動 `app/`，接線 PR 也不動缺日語意，修補留給驗證層 ADR 或接線後另立的 ADR。

登記前可能必須處理的只有一件事，而且不在程式：事先宣告 v0.32 是否要先補一句缺日的揭露。登記時 `prereg_doc_blob` 會凍結，這一句登記後就加不進去。要不要補由 quant 判斷，問題列在第 5 題。

各題裁示：

1. **已接受的限制，ADR 沒有要求核心在記錄當下看到被丟的列。**
   - D-8 第 3 點（約 226 行）把「缺日列與稽核」凍結為附錄，不實作。
   - 「最大代價」（56 行）與 Consequences（301 行）已明寫「缺日原因……無法補記，作廢可能較多」。
   - 229 行已預見驗證層會「從快照事後判定」缺日，並規定屆時要重述 #55 與 55-補 (c) 的代價、送風控。
   - 快照的完整性：D-5 第 1 點的定義是「該筆計算讀過的每一根 bar」。adapter 丟掉的列從沒被讀過，所以快照在定義上仍完整。
   - `dropped_rows_json` 的語意：補充二第 2 點 (b) 與 `inputs.py` 的 `DroppedRow` docstring，限定為「index service 有回傳、但沒進快照」的列，而且原因只有 not_final。adapter 層丟的列本來就不屬於它。
   - `source_status`：補充三第 5 點只要求照實記錄，並禁止拿它當分支條件，與這件事無關。
   - 需要追加附記：要寫成「讀法釐清＋已知盲點」，詳見第 3 題的 (d)。不急於登記前落地，等 quant 回覆後一併定稿。

2. **事後可辨識性在架構上成立，沒有登記後才發現補不回的欄位。**
   - 每筆紀錄的 `input_series_sha256` 都對得到當次快照；`bars_json` 逐根記有 `session_date`（D-5 第 1 點）。拿相鄰兩根之間的日期去比對官方交易日曆，就能找出缺口。D-5 第 4 點已規定官方休市日屬帳外資料，由驗證層另外接入。
   - T 當天整列被丟的情形，可以從 `forecast_run.started_at`、`forecast_run_end.candidate_t` 與交易日曆判定：預期的 session 沒有紀錄。如果之後的快照又出現該日，聯集也查得到。
   - 補不回來的只有缺日原因（是哪一欄 null，或來源根本沒有這列），這正是 56、301 行已接受的代價。
   - 如果要在帳內記錄缺口，需要新增欄位或改變快照語意，依 K-12 屬遷移。這一點登記前改也同樣需要 ADR。
   - 另有一個已知盲點要寫進附記：補充五第 1 點 (d) 的 F-2 分子取「快照中定案 session 的聯集」。來源永久缺席的 session 永遠不會進分子，所以 F-2 會偏低，性質與 (h) 的停機盲點相同。

3. **修補時點與代價：**
   - **(a) 採用**：不動任何東西，`a15e910c…`、tree id `9c157d86…` 與 qa 審查全部維持有效。
   - **(b) 否決**：
     - 只改 `app/data/providers/yfinance.py`：不在 `code_digest` 範圍（D-2 第 1 點），但會改變 `app/` 的 tree id。登記一鍵檔的常數（附記三第 1 點）因此失效，而且這項差異不在補充六第 6 點 (d) 的白名單內，等於 harness 通過失效。結果是 CEO 要重跑驗收、CG-2 PR 要重審。
     - 改 `app/outlook` 或 `app/forecast`：連 `code_digest` 也一起變。
     - 修補本身（新的 DropReason、價格快取要記住 null 列）還得另出 ADR。沒有補不回的東西，不值得付這個代價。
   - **(c) 只允許測試與 adapter log，不允許改缺日語意：**
     - `code_digest` 在接線 PR 本來就會變：補充五第 1、2 點的 F-2 查詢與 WARNING 都在接線 PR 落地。第一次正式執行時沒有前一次執行可比，D-5 第 6 點沒有既有紀錄要重算。我沒看到任何條文要求第一次正式執行的 `code_digest` 等於驗收值。所以「變更 `code_digest`」本身不是障礙。
     - 真正的障礙是語意，有四項：
       - 新增 missing code 牴觸補充五附記：`MISSING_CODES` 等於 §2.5 的四類、五個 code，而 §2.5 屬事先宣告，登記後凍結。
       - 新增 outcome 牴觸 D-2 第 2 點的列舉，也牴觸 K-12。
       - 「缺日就不寫紀錄」是新的拒收規則，依補充三第 5 點的精神須修 ADR。而且來源若永久缺一天，會連續約 315 個 session（N_SNAPSHOT）都寫不了紀錄。**強烈否決。**
       - `app/` 內沒有歷史交易日曆。D-1 第 3 點限定 `session_calendar.py` 只實作 `is_final`，新增日曆就是越界。
     - adapter 改成回報缺口，不屬 `code_digest` 範圍，但要把缺口帶進 `dropped_rows_json`，就得改 `inputs.py`（在 `code_digest` 範圍）與快照語意。快取命中時又拿不到缺口資訊，`dropped_rows_json` 的內容會隨快取狀態而不同，所以不採用。
     - adapter 只加 log，不影響快照，可以做，但我建議拆成獨立小 PR，不擴大 CG-4 的審查面。
   - **(d) 採用為修補路徑**：接線之後另立 ADR，修補屬驗證層。範圍與附記內容如下：
     - 驗證層的範圍：事後缺日判定的口徑、官方交易日曆來源、#55 重述（229 行）、R4～R6 是否進核心。核心期間如果要讓核心本身偵測缺口，只能等 ADR-0026 D-6 處理 schema 之後（CG-3）。
     - 帳外偵測可以早一點做：devops-sre 或 data-engineer 寫一支唯讀腳本，放在 `app/` 以外，比對 `bars_json` 與 TWSE 官方交易日，當日以 commit 記到 `work/`，作為接近即時首判的帳外證據。
     - 附記要寫入的內容：第 1 題的讀法、F-2 盲點、禁止核心以缺口分支（未修 ADR 前），以及驗證層的義務。

4. **開盤值為 0：與核心無關，已確認。**
   - grep `app/outlook`、`app/forecast`、`app/dirdef`：open、high、low 只出現在快照建構（`inputs.py:97-99,163-165`）與重算時的回填（`recorder.py:556`）兩處，只是原樣傳遞。計算只讀收盤價。
   - 開盤值會進入 `content_sha256`，這屬於原樣保存資料，符合 D-5。
   - `quality._check_ohlc_consistency` 在 `app/` 內沒有呼叫者：核心期間不接進核心，接進去就是標記或拒收規則，需要 ADR。開盤值是第二段（T+1 開盤進場）的問題，由第二段的事先宣告（data-engineer 的 R1）與其 ADR 處理，時點在第二段立案時。

5. **給 dev-lead 的指示（`feat/nm5-wiring`）：**
   - **不得**：
     - 改 `app/outlook/**`、`app/forecast/**`、`app/dirdef/**`、`app/data/session_calendar.py` 中任何與缺日有關的行為；
     - 新增 `DropReason` 值、`MISSING_CODES` 成員、outcome 值、表或欄位；
     - 在 `app/` 內新增交易日曆；
     - 以缺口或開盤值作為 recorder 的分支或拒收條件；
     - 改 `app/data/providers/yfinance.py`、`app/data/cache.py`、`app/services/index.py`。
   - **要加**：一個特性測試（只放 `tests/`）。合成一份中間缺一個 session 的 bars，斷言三件事：
     - 快照照原樣保存（缺口保留、沒有補值）；
     - `dropped_rows_json` 不含該日；
     - outcome 與 `missing_json` 跟沒有缺口時的判定規則一致（不新增任何 code）。
     - 測試 docstring 引用 ADR-0030 D-8 第 3 點，並註明「已知限制，修補見後續 ADR」。
   - **可以，但建議另開 PR**：在 adapter 的快取路徑跳過 null 列時記一行 WARNING（symbol、session_date、null 欄名，不含任何價格或標籤），附測試。

## 各部門回報

tech-architect：本次唯讀，沒有改任何檔案。讀過的檔案：
- `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`：D-1～D-9、K 條，補充二、三、五、五附記、六第 6 點、七附記三
- `/home/user/AICompany/apps/stock-desk/backend/app/data/providers/yfinance.py:260-398`
- `/home/user/AICompany/apps/stock-desk/backend/app/outlook/inputs.py:50-291`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/session_calendar.py`（只有 `is_final`）
- `/home/user/AICompany/work/research/2026-11-19-對沖PRD三題回覆-data-engineer.md`

**需要 quant 回答的問題**（附記與「登記前要不要補一句」要等這些答案）：
- Q-a：v0.32 的特徵與 lag，定義的是「快照中第 k 根 bar」，還是「交易日曆上第 k 個 session」？如果是後者，engine 在缺日時就偏離宣告。
- Q-b：凍結前，v0.32 是否必須加一句揭露，例如「核心不即時偵測缺日；驗證層事後依官方交易日曆判定並依凍結附錄處理」？要加就必須在登記前完成。這只動文件，不動 `app/`，也不影響 `code_digest` 與 tree id，但會動到 CG-2 PR 綁定的文件與 `prereg_doc_blob`，需要 qa 補核。
- Q-c：T 到 T+h 之間缺日，會讓實現標籤的 h 個 session 錯位。凍結附錄的作廢規則是否已涵蓋？還是驗證層只能往更嚴的方向補？
- Q-d：data-engineer 的 R2 資料體檢如果查到首個 315 根視窗內真的有缺日，是否構成登記前的阻擋？

## 驗證

- 引用的條文行號都是本次實際讀到的。
- 「核心只讀收盤價」：以 grep 確認 open、high、low 只出現在 `inputs.py` 與 `recorder.py:556`。
- `check_price_bars` 只有 `quality.py` 與兩個 tests 檔引用。
- 「接線 PR 本來就會改 `code_digest`」：依據是補充五第 1、2 點期限都寫「在接線 PR 落地」，是推論，沒有實際比對分支。
- 我沒有執行測試，沒有讀 v0.32，也沒有讀 `baselines.py` 的全文。

## 下一步

1. coordinator：把 Q-a～Q-d 轉給 quant。CEO 的驗收與 CG-2 照原計畫走，不受影響。
2. quant 回覆後，由我定稿附記（性質是釐清＋已知盲點，不放寬），交 tech-writer 落檔。如果 Q-b 需要補揭露，要在 CEO 正式登記之前完成，並由 qa 補核文件綁定。
3. dev-lead：照第 5 題的邊界實作接線 PR。adapter 的 WARNING 如果要做，另開 PR。
4. CEO 驗收之後：決定要不要做 R2 唯讀體檢（腳本放在 `app/` 以外）。

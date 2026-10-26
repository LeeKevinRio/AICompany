# ADR-0030：stock-desk 預測紀錄帳核心——最小記錄器

- 狀態：proposed
- 日期：2026-10-26
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：CEO 2026-10-26 裁定 #57（`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第四節）；方案來源：`work/reviews/2026-10-26-產品審視-tech-architect.md` 方案 A。
- 審查：風控語意審，核可附條件（`work/reviews/2026-10-26-ADR0030語意審-風控.md`，R-1～R-11 已納入）；quant 量化確認（`work/reviews/2026-10-26-ADR0030量化確認-quant-researcher.md`，M-1～M-12 已納入）。
- 適用範圍：僅 product/stock-desk 產品線。
- 前提：純自用（ADR-0025 F-1）；單機、單一使用者。
- 與既有 ADR 的關係：
  - **部分修訂 ADR-0025（accepted）**：C-M1～C-M4（D-11）。只在 ADR-0025 檔頭加一行指標，不原地改寫。每一項都須 CEO 核可，核可前衝突處以 ADR-0025 為準。
  - **部分取代 ADR-0027（proposed）**：未被取代的條文凍結為本 ADR 的附錄（D-8）。ADR-0027 檔頭加凍結註記，內文不再修訂。
  - **ADR-0012（accepted）**：不修訂。核心不讀市場 DB；forward return 類識別字仍只出現在 `app/forecast/scoring.py`（C-15，經 ADR-0025 修訂）。
  - **ADR-0028（proposed）**：只採用 CS-17 的收盤定案判定（D-3 第 2 點），不採用其他條文，也不依賴 VS-6 查證。
  - **ADR-0026、ADR-0029（proposed）**：核心不依賴（D-6 CG-3、K-2）。
  - **ADR-0005（accepted）**：大盤來源 yfinance `^TWII`，恆標 `backup`；不修訂。
  - **相容、不修訂**：其餘 ADR。
- 編號說明：起草時 `docs/adr/` 最後一份是 ADR-0029；0013 為員工線佔用；repo 內 grep `ADR-0030` 無結果。
- 標註約定：〔事實：檔案:行號〕為 2026-10-26 工作目錄的狀態；〔推論〕為起草者判斷。程式路徑相對於 `apps/stock-desk/backend/`。

---

## 評估摘要（結論先行）

**採用**
1. 預測紀錄帳先上線「最小記錄器」：只記大盤 3 日與 5 日兩個前瞻 claim；5 張只增不改的表；每筆附 PIT 輸入快照與四個基準預測；驗證狀態固定為 `unverified`，沒有升級路徑。
2. 寫入截止改為「T 的次一個日曆日 00:00（台北）」，不再依賴盤前時間的查證。
3. 程式語意與執行環境一併鎖住：程式或環境改變後，只要重算結果不一致就停止寫入，要讓新語意生效只能登記新 claim。
4. ADR-0027 的驗證層（結算、作廢、缺日稽核、驗證狀態、F-2、claim 計數細則、重放）凍結為附錄，不實作。「第一個檢查點前 90 天」與「n 達第一個檢查點的 50%」先到者觸發重審。
5. 原始輸入快照完整保存，驗證層日後可以從帳內資料逐位重算。

**否決**
- 維持 ADR-0027 全文路線（A3）；暫停整條預測線（A2）。
- 核心期間把展望方向放上任何使用者畫面，或在任何輸出列出尚未到期的標籤（ADR-0025 D-6.6 不動）。
- 核心期間寫入 on-demand、個股或族群紀錄。
- 以回填過去日期的方式「補樣本」。

**最大代價**
- 規則、dirdef 常數與事先宣告 v0.32 都還沒定稿，第一筆紀錄的時程取決於 quant 與 CEO 的關鍵路徑（約 2～3 週）。
- 驗證層日後重算時，ADR-0027 設計中的部分證據（缺日原因、結算時強制重抓）已無法補記，作廢可能較多。
- 核心期間使用者畫面沒有任何新增；規則文字改任何一字都會讓 n 歸零；程式或執行環境改變時，可能讓記錄停擺。

---

## Context（背景）

### 1. 問題
- ADR-0027 有 25 張表、6 道寫入閘門（另有 on-demand 的 G-7）〔事實：`docs/adr/0027-…:76,86,89`〕，至今沒有任何一筆前瞻紀錄。
- 預測帳的價值取決於累積天數。模型比最強基準高約 13 個百分點時，大盤 5 日約 10 年、3 日約 6 年才有足夠檢定力〔事實：事先宣告 `:840`〕；升級判定多年內不會觸發，卻擋住了第一筆紀錄。
- CEO 裁定 #57：另立 ≤500 行的 ADR，只含記錄、PIT 輸入、基準並列、固定「未驗證」；驗證層凍結，第一個檢查點前再啟用。

### 2. 現況（事實）
- B1／B2 只 commit 了純函式：`app/forecast/`（`errors`、`band`、`definitions`、`claims`）、`app/dirdef/`、`app/outlook/`（`missing`、`volatility`、`basket`）、`app/ops_alert/model.py`。沒有 store、recorder、job 或 route〔`app/forecast/__init__.py:1-7`；`tests/test_forecast_gate_closed.py:40-56`〕。
- 兩個登記表與 `OUTLOOK_RULE_FIELDS` 都是空的〔`app/dirdef/registry.py:62-63`；`app/dirdef/rules.py:56`〕；規則只有附錄 B 的骨架〔事先宣告 `:2581`〕。
- `is_final`、`adjust_series_pit`、`wilder_atr` 都不存在（grep）；`TW_POLICY.publish_cutoff = 15:00` 已存在〔`app/data/freshness.py:131`〕。
- `^TWII` 經 `app/services/index.py` 取得，底層是主 DB 的 `price_bars_cache`〔`app/services/index.py:189`；`app/data/cache.py:39`〕。該表衝突時會覆寫 `as_of`、`fetched_at`；yfinance 路徑的 `as_of` 是取數時刻〔`app/data/providers/yfinance.py:242`〕；表內沒有來源的原始時間戳記。

### 3. 限制
- ADR-0025 規定紀錄只增不改、PIT、並列基準（D-6）；判斷上畫面之前，回放報告必須已產出並經審查（D-6.6）〔`docs/adr/0025-…:412-414`〕。
- quant：「回到 30 天前一路預測」只能當管線驗收，不得消耗唯一一次的正式重放〔`work/reviews/2026-10-26-產品審視-quant-researcher.md:95-109`〕。
- CEO #58：qa-reviewer PASS 加 CI 綠燈即可合併。CEO #60：風控在 ADR 階段審一次語意。

---

## Options（選項比較）

**A. 總體作法**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A1 最小記錄器＋凍結驗證層（採用）** | 盡早累積樣本；沒有升級路徑，不可能誤稱有效 | 要重開部分已核可的風控條件；驗證層日後要重審 | 少記驗證要的欄位。緩解：完整快照（D-5） |
| A2 暫停整條預測線 | 產能全部轉向好用性 | 違背 CEO 的需求；已投入成本歸零 | 重啟時脈絡散失 |
| A3 維持 ADR-0027 全文 | 不必重工 | 仍被七道閘門卡住 | 文件持續漂移 |

**B. 寫入截止時點**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **B1 T 的次一個日曆日 00:00（台北，採用）** | 不需查證盤前時間與交易日曆；操作者在看完夜盤、美股之後再決定要不要補跑的空間最小 | 主機晚上沒開，當天只能記 `late` | 樣本累積變慢 |
| B2 next_session(T) 08:30（ADR-0027 M-1） | 允許清晨補跑 | 依賴 G-4 與 VS-6 查證 | 查證前不能記錄 |
| B3 T+1 09:00（ADR-0025 原文） | 已核可 | 08:30～09:00 可能已有盤前資訊 | 前視偏誤 |

**C. 核心範圍**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **C1 只記大盤（採用）** | 只有一條指數序列；沒有存活者偏差 | 個股與族群較晚開始 | 兩者在 v1 本來就不顯示方向〔推論〕 |
| C2 大盤＋個股＋族群 | 三類同時累積 | 依賴 `adjust_series_pit`、N-120 等未完成項 | 核心被拖回 ADR-0027 的規模 |

---

## Decision（決策）

### D-1 核心範圍與模組
1. **claim**：只有 `scope_kind = market`、`scope_key = 'TAIEX'`、`horizon ∈ {3, 5}`、`kind = forward`，共兩個記錄中 claim。資料源更換依 F-5 處理。
2. **claim 更換**：
   - 規則或定義有任何變更（含只改文字）都是新 claim；核心期間不使用 PATCH／MINOR 沿用原 claim 的機制。驗證層 ADR 可以恢復「`rules_logic_sha256` 與 `definition_logic_sha256` 都不變時沿用原 claim」的機制，但不得回溯改變既有紀錄的 `claim_id`。
   - 核心期間登記任何新的前瞻 claim（含取代既有 claim），都須先修訂本 ADR 並經風控審一次語意；修訂須寫明被取代的 claim、取代當時的 n̂，以及操作者已看過的暫定對照筆數，這些數字日後在驗證報告照實揭露。被取代 claim 的紀錄照常保留並計入 m，不得因取代而不報告。正式 DB 的每次 claim 登記，須在當日以 commit 在 `work/` 記錄 `claim_id` 與 `registered_at`；m 不得少於該紀錄中的 claim 數。
   - 被取代的 claim 不刪、不改，紀錄照常保留。驗證層照樣評估到它實際累積的 n，並在報告中與其後的 claim 並列。m 計入所有曾寫入紀錄的前瞻 claim。登記新 claim 時 `replace_reason` 必填；登記者在登記前看過任何暫定對照（D-5 第 5 點）時，`provisional_results_seen = 1`，日後報告照實揭露。
3. **新增模組**（ADR-0027 D-1 的其餘模組在凍結期間不得建立，K-1）：

| 模組 | 職責 |
|---|---|
| `app/forecast/schema.py` | 5 張表的 DDL 與 trigger；啟動時以 `sqlite_master` 核對，缺任何一項就拒絕寫入 |
| `app/forecast/store.py` | 只增不改的寫入（時間戳由 store 時鐘填入）；唯讀查詢（D_v、n̂、m、記錄中 claim、執行結果） |
| `app/forecast/canonical.py` | bar 值正規化、`content_sha256` 與 `code_digest` 的唯一定義 |
| `app/forecast/recorder.py` | job `forecast_record` 的唯一編排：CG-2 核對 → 跨 commit 核對 → 決定 T → 擷取快照 → 計算 → 寫入 |
| `app/forecast/claims.py` | 既有純函式，另加操作者 CLI `python -m app.forecast.claims register` |
| `app/forecast/scoring.py` | 暫定對照的純函式（D-5 第 5 點）；ADR-0012 C-15 白名單 |
| `app/forecast/report.py` | 操作者 CLI（唯讀）；輸出受 D-4 第 3、5 點限制 |
| `app/outlook/inputs.py` | 大盤輸入：只經 `app.services.index` 取得，只收定案 bar |
| `app/outlook/engine.py` | 規則求值與特徵（純函式；特徵公式依 quant 凍結的規格） |
| `app/outlook/baselines.py` | 發布當下的 B1、B2、B6、B8（D-4） |
| `app/data/session_calendar.py`（新檔） | 只實作 `is_final`（ADR-0028 CS-17 指定的位置）；ADR-0028 核可後由它接手，不另寫第二份 |

4. **擴充**：擴充到個股或族群，須修訂本 ADR（或另立 ADR）並經風控審一次語意，前提至少有四項：ADR-0027 D-4 第 1、2、7 點與 D-5 重審後納入；`adjust_series_pit`、`wilder_atr` 已實作；N-120 的預測端評估已經風控確認；市場 DB 與主 DB 有同一時點的備份。擴充到 on-demand 時，ADR-0027 D-14 G-7 的閘門語意（含不得「算了但不落帳」，以及閘門關閉時不回傳任何方向衍生欄位）須一併恢復。擴充不改變大盤 claim。

### D-2 資料表（主 DB；只列關鍵欄位）
1. `forecast_run(run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at, trigger, code_commit, code_digest, runtime_json, schema_version)`：每次執行的第一個寫入，在讀取任何市場資料之前；`trigger` 只有 `scheduled`。`code_digest` 是 `app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py` 原始檔的正規化 sha256；`runtime_json` 記 Python 版本、平台、依賴鎖檔 sha256。D-5 第 3 點的重算以 `code_digest` 與 `runtime_json` 相同為前提；`code_commit` 只作為出處。
2. `forecast_run_end(run_id PK, outcome ∈ {ok, no_new_session, inputs_not_ready, gate_closed, error}, candidate_t NULL, records_written, error_class NULL, ended_at)`：
   - 沒有 end 列就代表程序中斷；`error_class` 只經 `exception_class_name`。
   - 候選 T 在每個記錄中 claim 都已有紀錄時，記 `no_new_session`，`candidate_t` 照填，不寫紀錄，不得記為 `error`。
3. `forecast_input_series(series_id, content_sha256 UNIQUE, series_kind = 'index_bars', source, source_status, staleness_minutes, reason, dropped_rows_json, raw_timestamp_available, bars_json, captured_at)`：原始輸入快照（D-5），以內容雜湊去重。
4. `forecast_record`：
   - 識別：`forecast_id`（ULID）、`run_id`、`claim_id`、`scope_kind`、`scope_key`、`horizon`、`data_as_of`（T）；
   - 版本：`definition_version`、`definition_sha256`、`rules_version`、`rules_sha256`；
   - 結論：`label ∈ {bullish, range, bearish, insufficient}`、`range_basis`、`missing_json`（`MissingItem` 陣列）、`evidence_json`；
   - 判定材料：`band_def`（`K_h`、`EPS`、`sigma_d`、`valid_returns`、`up_pct`、`down_pct`）、`base_close`、`baseline_predictions_json`（D-4）；
   - PIT 證明：`input_series_sha256`、`inputs_max_fetched_at`；
   - 時間：`created_at`、`late ∈ {0, 1}`、`late_cutoff_at`、`valid_until_session_estimate`；
   - `validation_status`：CHECK 只允許 `'unverified'`；
   - `content_hash`：涵蓋 `forecast_id`、`run_id`、`created_at`、`late` 以外的全部欄位；
   - `UNIQUE(claim_id, data_as_of)`；核心沒有更正列。
5. `forecast_claim_registry(claim_id PK, scope_kind, scope_key, horizon, kind, rules_version, rules_sha256, rules_logic_sha256, rules_bytes, definition_version, definition_sha256, definition_logic_sha256, definition_json, frozen_commit, prereg_doc_path, prereg_doc_blob, review_refs, replaces_claim_id NULL, replace_reason NULL, provisional_results_seen ∈ {0, 1}, registered_at)`：`kind` CHECK 只允許 `'forward'`。
6. **5 張表全部**有 `BEFORE UPDATE`／`BEFORE DELETE` 的 `RAISE(ABORT, 'append-only')`，沒有任何例外。
   - 由查詢導出：`first_record_at` ＝ 該 claim 第一筆 `forecast_record` 的 `created_at`（不論 `late`）；「計入 m」⇔ 該 claim 至少有一筆 `forecast_record`。m ＝ max（計入 m 的前瞻 claim 數，D-1 第 2 點 `work/` 登記紀錄中的 claim 數）。
   - `first_record_at` 與「計入 m」的查詢定義在本 ADR 寫明，須與 ADR-0027 D-10 第 3 點前瞻 claim 的轉值時點同義，不留給驗證層定義；m_eff 的下限沿用 ADR-0027 D-10 第 4 點，不因本 ADR 降低。
7. 寫入驗證沿用已 commit 的單一判定：`band_def` 經 `app/forecast/band.py`，`missing_json` 經 `app/outlook/missing.py`；不成立就拒絕寫入。

### D-3 PIT 輸入與寫入時點
1. **決策日 T**：`app.services.index` 讀到的最新一根定案 bar 的 session 日期。recorder 沒有指定 T、指定時鐘或回填過去日期的參數。
2. **定案**：bar 的 `as_of` 與 `fetched_at` 取較早者，不得早於 T 日 `TW_POLICY.publish_cutoff`（15:00 Asia/Taipei；ADR-0028 CS-17 口徑）。T 日 bar 不定案時重抓一次；仍不定案就記 `inputs_not_ready`，不寫紀錄，不用暫定值，也不改用前一天。
3. **寫入截止**：`late_cutoff_at` ＝ T 的次一個日曆日 00:00:00（Asia/Taipei）。`created_at`（store 時鐘）早於它時 `late = 0`，否則 `late = 1`。`late = 1` 照寫，但永遠不進任何主統計。臨界測試：23:59:59.999999 與 00:00:00。日後若要把截止延後到 00:00 之後，屬放寬，須恢復與 G-4 等效的查證，並經風控審查、CEO 明確同意。
4. **輸入範圍**：只用 T 日（含）以前的定案 bar；快照在同一次執行內擷取，所以 `captured_at ≤ created_at < late_cutoff_at`。
5. **禁用的 hindsight 來源**：`app/forecast/**`、`app/outlook/**` 不得出現 `price_bars_cache`、`dividend_events`、`_hindsight_view` 識別字，不得 import `app.demo`、`app.backtest`、`app.research`，也不得以事後重抓的 bars 取代已擷取的快照。
6. **證據不足照寫**：輸入不足、σ 退化或可評估規則不足時記 `label = insufficient`，`missing_json` 非空，`up_pct`、`down_pct` 為 null；不補值（事先宣告 §5.1）。
7. **排程**：job `forecast_record` 平日 22:10 執行、23:10 重試、啟動後 3 分鐘補跑；`timezone = "Asia/Taipei"`、`max_instances = 1`、`coalesce = True`。data-engineer 確認 Yahoo 在 18:00 之前已是最終收盤之後，可另加一次 18:10 執行（輸入規則不變）。只有這一個 job，也只有 recorder 寫入預測帳。

### D-4 基準並列與驗證狀態固定
1. **發布當下的基準**：每筆紀錄在同一交易內寫 `baseline_predictions_json`：B1、B2、B6、B8，每項為標籤，或 `unavailable` 加原因，另附 B1、B2 的稽核明細（σ_d(T−h)、B1 的 z、B2 各類票數與可投票位置數）。基準與主預測用同一份快照計算，寫入後不重算。
   - B2 的 250 筆，指 T′ ＝ T−h, …, T−h−249 這 250 個快照位置（逐日、重疊）。某位置算不出實現標籤時，該位置不投票，也不往更早的位置補。可投票的位置少於 120 個時記 `unavailable`（`b2_realized_short`）。同票依 震盪 > 偏多 > 偏空。命名不得用 forward return 類識別字。
2. **屬驗證層的基準**：B7、B7r（評估時才算的事後眾數）與 B0（理論值 1/3）屬驗證層，凍結。B5 只適用族群與個股，大盤沒有 B5。
3. **輸出格式**：任何輸出（操作者報告與 `report` 各子命令、管線驗收 harness 的輸出、log、匯出檔，以及日後任何 API）列出模型標籤時，必須在同一列同列四個基準（`unavailable` 照列原因），版面權重相同，不得以顏色、粗體、排序或欄位位置突顯模型標籤；不得只列模型標籤。`valid_until_session_estimate` 尚未過的紀錄，任何輸出都不列模型標籤與基準標籤，只列 T、`late`、是否證據不足、雜湊與執行結果；`report verify` 只輸出核對是否一致，不輸出標籤。log 一律不含標籤。
4. **驗證狀態**：`validation_status` 只有一個值 `unverified`。使用者面字面為「未驗證」。凡顯示這個字面之處，同一處須附：「未驗證：這個判斷還沒有經過前瞻紀錄或歷史回放的驗證，不能認定它比基準準確；它不是機率，也不是勝率。」這段字面只適用於核心期間；任何範圍的回放報告產出或驗證層 ADR 核可之後，須重送風控。`app/` 內沒有計算驗證狀態的函式。
5. **不得彙總**：核心輸出（含操作者報告、管線驗收 harness、log 與匯出檔）不得出現命中率、符合筆數或比例、連續符合或不符合的計數、區間、n、累積圖表，也不得出現「優於」「不如」「準確」「有效」類字樣或彙總；不得依暫定對照的結果排序、篩選或分組。
   - 唯一例外：操作者報告列出重審觸發用的 n̂（D-8 第 4 點），並標明「重審觸發用計數（近似上界估計），不是驗證統計，不代表規則有效」。
   - F-2 所需的缺格點與執行結果計數屬執行狀態，可列於報告，但不得與任何標籤或對照並列。
6. **不上畫面**：`app.main` 不掛載 `/api/forecast`、`/api/outlook`；ADR-0025 D-6.6 不變。

### D-5 原始輸入快照與日後重算
1. **快照內容**：該筆計算讀過的每一根 bar，逐根記 `session_date`、OHLCV、`source`、`as_of`、`fetched_at`。
   - 快照為 T（含）以前最近 N_SNAPSHOT 根定案 bar；N_SNAPSHOT ＝ max(規則最長回看所需根數, 5＋B2_WINDOW＋SIGMA_WINDOW)，v1 為 315，隨 dirdef 凍結。向取數路徑請求時，至少涵蓋 T 前 500 個日曆日。取得不足 N_SNAPSHOT 根時照實記錄根數，依缺項與 B2 不可用規則處理，不擴大、不補值。
   - `price_bars_cache` 沒有來源原始時間戳記，快照記 `raw_timestamp_available = false`。日期慣例（決策包 #49）無法從帳內事後稽核，建議在 CG-1 之前以 #49 (a) 完成一次。日期整段偏移只會讓紀錄全部記為 `late = 1`（fail-closed），所以這不是安全前提。
2. **自足**：紀錄引用 `input_series_sha256`；登記表存規則檔位元組與定義物件的 JSON；`forecast_run` 存 `code_digest` 與 `runtime_json`。
3. **重算不變式**：以快照、登記表中的定義與規則位元組，在 `code_digest` 與 `runtime_json` 相同的前提下重算，`label`、`band_def`、`baseline_predictions_json`、`missing_json` 都要逐位相同，`content_hash` 也相等。`report verify` 執行這項核對；不一致即為 F-3。
4. **結果端資料**：核心不寫結算列。T+h 的 bar 由之後各筆紀錄的快照涵蓋；正式結算由解凍後的驗證層重算。官方休市日、X2 與獨立的指數查證屬帳外資料，由驗證層另外接入。
5. **暫定對照**：`scoring.py` 內的純函式。輸入是一筆紀錄，以及之後涵蓋 T 後 h 個定案 session 的快照，而且 `valid_until_session_estimate` 已過（ADR-0025 AV-18）。它輸出實現標籤，以及模型與四個基準各自是否符合；輸入缺漏、不定案或日期不連續時，輸出「無法對照」與原因。結果不寫入任何表，不被 `store.py`、`recorder.py` import，只由 `report.py` 輸出，並在每次輸出的開頭與結尾各固定標示一次：「暫定對照：非正式結算，結果可能與日後正式結算不同；只對照發布當下可算的四個基準；不計入任何驗證統計，單筆符合與否不代表規則有效；規則未經驗證。」
6. **跨 commit 不變式**：`code_digest` 與前一次執行不同時，recorder 在寫入任何紀錄之前，以目前的程式對每個記錄中 claim 的全部既有紀錄重算 D-5 第 3 點的欄位。任一筆不逐位相同，就記 `gate_closed`（`error_class = SemanticsChanged`），不寫紀錄。要讓新語意生效，只能登記新 claim。`runtime_json` 與前一次執行不同時，同樣執行本點。

### D-6 寫入閘門（CG；全部成立前不得寫入任何紀錄）
- **CG-1**：本 ADR accepted，含 C-M1～C-M4 與 D-11 所列明確同意。
- **CG-2**：凍結與登記。
  - `dirdef-v1.0` 登記於 `PUBLISHED_DIRECTION_DEFINITIONS`，含 C-8 的 `f2_variant` 與決策出處；dirdef 凍結的前置條件（決策包補遺知悉 #15、#16）依 CEO 選擇的甲案或乙案。
  - 大盤 h3、h5 規則登記於 `PUBLISHED_RULESETS`，`OUTLOOK_RULE_FIELDS` 已設定；兩個前瞻 claim 經 CLI 登記，`frozen_commit`、`prereg_doc_blob`（事先宣告 v0.32）、`rules_bytes`、`definition_json` 都非空。
  - CG-2 登記前，規則檔與定義中日後可能渲染給使用者的字串，以 NFKC 正規化並去除空白後跑一次禁詞比對，結果附在登記 PR。N-126 的正式修補期限改為「規則或任何預測相關文字上畫面前」，而且須在渲染當下也套用。
  - recorder 每次執行都先核對：對 D-1 第 1 點的每個 (`scope_kind`, `horizon`)，取登記順序最後的前瞻 claim 為「記錄中 claim」，恰好兩個；每個記錄中 claim 的雜湊等於 `app/forecast/definitions.py` 的回傳結果；其餘前瞻 claim 都出現在其後某列的 `replaces_claim_id`。不成立就記 `gate_closed`，不寫紀錄。
- **CG-3**：核心 schema 第一次在正式主 DB 建立之前，以 SQLite backup API 或 `VACUUM INTO` 取得一次主 DB 的一致備份，路徑與 sha256 記在接線 PR。核心期間不做任何遷移；要改 schema，須等 ADR-0026 D-6 核可並實作。建議 devops-sre 在 n̂ 達 ⌈c₁÷2⌉ 之前讓定期備份上線。
- **CG-4**：`app/forecast/**`、`app/outlook/**`、`app/dirdef/**`、`app/data/session_calendar.py` 與 scheduler 接線，通過 qa-reviewer PASS 與 CI 綠燈（CEO #58）。凡觸及 `app/forecast/**`、`app/outlook/**`、`app/dirdef/**` 的 PR，合併前 `report verify --all` 必須全部一致。
- CG-1、CG-3、CG-4 由 qa-reviewer 在接線 PR 核對；job 只在該 PR 註冊。
- 對 ADR-0027 D-14 的取代：
  - G-1 → CG-1；G-2、G-3 → CG-2；
  - G-4 不再需要，因為 D-3 第 3 點不依賴 08:30；
  - G-5 → CG-3（放寬：不再要求 ADR-0026 D-8 的 DB 路徑守門與身分，以及 D-9 的定期備份組；條件見 D-8 第 3 點還原句與 F-8，須 CEO 明確同意）；
  - G-6 → CG-4；G-7 隨 on-demand 移出核心而失效。

### D-7 30 日管線驗收
1. 用途只限驗證管線，不是績效證據，不計入任何驗證統計，不消耗事先宣告 §4.7 唯一一次的正式重放。管線驗收的輸出不得在任何文件、決策包或規則選擇中被引用為規則表現的依據。
2. 以 `scripts/` 或 `tests/` 內的 harness 執行，使用暫存 DB 與注入時鐘，呼叫同一套 recorder；harness 遇到正式主 DB 路徑就拒絕執行，取數也不得寫入正式主 DB 的 `price_bars_cache`（qa 確認）。佔位規則以注入的登記表通過 CG-2，正式路徑沒有這條注入路徑（K-11）。
3. 不在正式 DB 登記 claim，不寫正式紀錄；登記表 `kind` 只允許 `forward`。
4. **規則集**：
   - 預設的佔位規則有兩組，都不是候選規則：P-0 恆判震盪（輸出恆等於 B6），P-1 符號延續（輸出恆等於 B8）。harness 斷言每一筆的模型標籤與對應基準逐筆相同，暫定對照中兩者是否符合也逐筆相同。證據不足、σ 退化、快照不足與 `late` 臨界，用合成 fixture 驗證。
   - CEO 若選用候選規則，只能用已凍結並 commit 的版本。該版本要在登記表 `review_refs` 與事先宣告註明「已看過管線驗收期間（{起日}～{迄日}）的結果」；這個版本不論日後是否登記或修改，都列入事先宣告的版本歷程揭露，重放報告將這段期間單獨標示。
5. 每次輸出的開頭固定標示：「管線驗收：使用歷史資料，不是前瞻紀錄；只驗證程式流程，不是績效證據，不計入任何驗證統計；規則未經驗證。」第二行依規則集擇一：
   - 佔位規則：「本次使用佔位規則，輸出不是任何將登記規則的判斷。」
   - 候選規則：「本次使用候選規則 {rules_version}；此版本已看過 {起日}～{迄日} 的結果，日後重放報告照實揭露。」
6. 真實資料的 harness 只能用目前快取中的值重建 T 以前的序列，`fetched_at` 為注入值並標 `synthetic_timestamps`。PIT、定案與 `late` 只用合成 fixture 驗證，不得以 harness 結果宣稱真實時序已驗證。harness 視窗由程式機械決定（執行日前最近 21 個定案 session）。D-4 第 3 點「尚未過」在 harness 中以實際時鐘判定。
7. CEO 若選用候選規則：harness 視窗落在重放期 [S, E] 內的部分，正式重放報告要揭露「最後 x 個觀察日的結果在重放前已看過」，並另列排除這段之後的結果；之後的任何修改，依事先宣告 §4.7「看過結果後修改」處理。

### D-8 與 ADR-0027 的關係、凍結附錄與重審觸發
1. **由本 ADR 取代**（僅限大盤核心）：
   - D-1、D-2、D-3；
   - D-4 第 3、4、5、8 點中適用大盤的部分；
   - D-7 第 1 點與寫入截止；
   - D-8 的執行證據部分；
   - D-14。
2. **沿用**：D-13（`MissingItem`）。
3. **凍結為附錄**（不實作，不再修訂）：
   - 凍結的範圍：
     - D-4 第 1、2、6、7 點；D-5；D-6；D-7 其餘各點；
     - D-8 的缺日列與稽核；D-9～D-12；D-15；
     - M-1～M-11；未被本 ADR K 條取代的 FL、FLT；待決事項。
   - 凍結期間，附錄中的 CEO 待決事項暫停。已取得的 CEO 明確同意（決策包 #47、#48、#50、#51、#52、#55）保留，條文不變就不必重問。
   - #55（含 55-補 (c)）的前提是缺日「即時首判」。驗證層若改為從快照事後判定，驗證層 ADR 須在新的判定時點下重述其代價，送風控確認效果不變；效果有變就重問 CEO。
   - 凍結期間主 DB 若發生整檔還原、更換或重建（含 DB 路徑改變），操作者須在執行或發現當日以 commit 在 `work/` 記錄日期、還原點與原因。驗證層 ADR 對因此失去的第 0 相位格點，不得只依事先宣告 §4.1 當作『失去』排除；須在最不利情境 W 中以『模型錯、基準對』放回，或提出不弱於此的處理並經風控審查。
4. **重審觸發**（每個前瞻 claim 各自判定，任一先到即觸發；實際上由 h3 決定時點）：
   - c₁ ＝ 該 claim 已登記 dirdef 的第一個檢查點，大盤為 30（事先宣告 §4.5）。
   - **(T1)** n̂ ≥ ⌈c₁ ÷ 2⌉。n̂ 以至今全部快照中定案 session 的聯集為序列，從 D_v 起每第 h 個 session 取一個格點，計算有 `late = 0` 紀錄、而且其後第 h 個定案 session 已出現的格點數。n̂ 不扣證據不足、作廢、基準不可用與 PIT 違規；驗證層依觀察日重建格點時，兩者可能錯開，所以 n̂ 是正式 n 的近似上界。
   - **(T2)** 今天 ≥ d₁ − 90 個日曆日；d₁ ＝ D_v 加 c₁ × h 個週一至週五，不扣休市日。
   - D_v ＝ 該 claim 第一筆 `late = 0` 紀錄的 T。
   - n̂、d₁ 與是否觸發都只由 `store.py` 的唯讀查詢導出，`report.py` 每次輸出；首次成立時 recorder 記 WARNING。
5. **觸發後**：tech-architect 在 30 日內以凍結附錄為底起草驗證層 ADR，只納入第一個檢查點需要的部分；風控審一次語意，CEO 核可。核可前紀錄照常累積，狀態維持 `unverified`。核可後，ADR-0027 改標 superseded。附錄中影響 n、作廢、結算或 W 的規則只能收緊；要放寬，須逐項標明起草者已看過的暫定對照範圍（截至哪一個 T），送風控，並經 CEO 明確同意。
6. **重審的界限**：
   - `dirdef-v1.0` 已登記的物件與兩個雜湊永不修改。
   - `dirdef-v1.0` 與事先宣告 v0.31 已登記的判定常數與規則（基準集合、檢查點、N_MIN、α\* 相關常數與 m_eff 下限、§4.1 格點與「失去的格點不得補位」、§4.3 條件、作廢計入最不利情境的範圍（CEO #47、#48、#50）、F-3 上限、`f2_variant`、退出期限），對既有 claim 只能往更嚴的方向改。
   - 驗證層 ADR 對既有 claim，只能以另立、只增不改、不在 dirdef 物件內的驗證參數登記，加上更嚴的條件。改動 dirdef 物件本身，一律是新定義版本、新 claim、計數歸零。
   - 驗證層 ADR 相對凍結附錄的每一處刪減或改寫，都須逐條標示收緊、不變或放寬；放寬項須經風控審查與 CEO 明確同意，並在驗證報告揭露「此規則在已有暫定對照之後才定案」。
7. **提前解凍**：CEO 可以單獨提前解凍 ADR-0027 D-9 第 7 點（重放）與相關表，程序同第 5 點。這項順延只在沒有任何方向上使用者畫面時有效。任何 scope 與 horizon 的方向上畫面之前（含依 D-8 第 7 點提前解凍重放的情形），驗證層 ADR（含驗證狀態判定與 F-2）必須已核可並實作；提前解凍重放本身不構成上畫面的充分條件。驗證層 ADR 核可時，對核心期間已經過的每一個檢查點依登記順序回溯判定，負面結果照常生效，並揭露判定日晚於檢查點日；不得因驗證層晚到而略過、合併或重置任何檢查點。

### D-9 保留的安全底線（逐條可檢查）
- **S-1 只增不改**：5 張表都有 UPDATE／DELETE 的 RAISE trigger，沒有例外（`sqlite_master`）。
- **S-2 時間戳由 store 填入**：`started_at`、`created_at`、`captured_at`、`registered_at`、`ended_at` 都不是寫入函式的參數（簽章測試）。
- **S-3 寫入時點**：`late` 由 store 依 D-3 第 3 點計算，不接受呼叫端傳入；`late = 1` 不進任何統計（臨界測試）。
- **S-4 只用定案 bar**：不定案就記 `inputs_not_ready`（測試）。
- **S-5 禁用 hindsight 來源**：依 D-3 第 5 點（grep 加 import graph）。
- **S-6 沒有回填路徑**：recorder 與 job 沒有指定 T 或時鐘的參數（簽章測試）。
- **S-7 定義先凍結**：沒有記錄中 claim 就沒有紀錄（CG-2 執行期核對）。
- **S-8 基準並列**：每筆紀錄都有四個基準（寫入驗證）；輸出依 D-4 第 3 點。
- **S-9 固定未驗證**：`validation_status` CHECK 只允許 `'unverified'`；`app/` 內不得出現 `better_than_baseline`、`not_better_than_baseline`（grep）。
- **S-10 未到期不列標籤、不彙總**：依 D-4 第 3、5 點（報告輸出測試）。
- **S-11 不上畫面**：沒有 forecast／outlook route；ADR-0025 D-6.6 不變（route 掃描）。
- **S-12 可重算**：D-5 第 3、6 點（測試；`report verify`）。
- **S-13 管線驗收隔離**：依 D-7 第 2、3 點（測試）。
- **S-14 claim 更換有紀錄**：依 D-1 第 2 點與 CG-2（執行期核對；`work/` 登記紀錄）。
- **S-15 規則式、不用 LLM、不下單**：ADR-0025 AV-10、AV-20 照舊。
- **S-16 祕密與持倉**：紀錄、快照、log 不含祕密，也不含成本與股數。
- **S-17 合併與備份**：qa PASS 加 CI 綠燈才合併；依 CG-3 備份；不遷移；還原依 D-8 第 3 點記錄。

### D-10 已 commit 的 B1／B2 程式

| 程式 | 處置 |
|---|---|
| `app/dirdef/`（全部） | 沿用。凍結前 `DirectionDefinition` 須補欄位：`SIGMA_WINDOW`、`B2_WINDOW`、`B2_MIN_REALIZED`、`MAJORITY_TIE_ORDER`、`NEFF_BLOCK_LEN`、季節月份、風控 R-1 偏離欄（列入 `DEFINITION_NON_LOGIC_FIELDS`）；驗證常數照樣在凍結時登記 |
| `app/forecast/definitions.py` | 沿用，仍是登記表的唯一讀取點 |
| `app/forecast/claims.py` | `claim_id` 沿用並加登記 CLI；`count_m`、`m_eff` 暫不使用 |
| `app/forecast/band.py` | 沿用（寫入驗證） |
| `app/forecast/errors.py` | 沿用基底、`LabeledThresholdSnapshotIncompleteError`、`exception_class_name`；`WriteGateClosedError` 的閘門列舉改為 CG；其餘例外保留不刪，核心不使用 |
| `app/outlook/missing.py`、`volatility.py` | 沿用 |
| `app/outlook/basket.py` | 暫不使用（族群） |
| `app/ops_alert/model.py` | 暫不使用；心跳由 devops-sre 讀 `forecast_run_end` |
| `tests/test_forecast_gate_closed.py` | 保留到接線 PR；接線 PR 改為「只允許 job `forecast_record`，仍然沒有 route」 |

### D-11 對 ADR-0025 的影響（每項須 CEO 核可；ADR-0027 的 M-1～M-11 隨凍結暫停）
- **C-M1（收緊）**：D-6.2、AV-17、AT-6、F-3、D-12 Phase 3 驗收：截止改為 T 的次一個日曆日 00:00（台北）；欄位改名 `late`，另存 `late_cutoff_at`；臨界改為 23:59:59.999999／00:00:00。
- **C-M2（收緊）**：D-6.1、D-6.2、AV-17：核心只寫 D-2 的 5 張表；不寫 `forecast_outcome`、`plan_record`、`plan_outcome`；沒有 NULL 變成值的例外；不寫更正列；`input_digest` 改由 `input_series_sha256` 承擔。
- **C-M3（改定義）**：D-6.3、AT-7：結果定義改依凍結的 `dirdef-v1.0`（同 ADR-0027 M-3 與事先宣告 C-4）。
- **C-M4（兩面，須明確同意）**：D-6.5、F-2：核心期間驗證狀態只有 `unverified`，F-2 的評估順延到驗證層 ADR 核可之後。收緊面是不可能出現正面宣稱；放寬面是負面結果也不會出現。這項順延只在沒有任何方向上使用者畫面時有效。任何 scope 與 horizon 的方向上畫面之前（含依 D-8 第 7 點提前解凍重放的情形），驗證層 ADR（含驗證狀態判定與 F-2）必須已核可並實作；提前解凍重放本身不構成上畫面的充分條件。驗證層 ADR 核可時，對核心期間已經過的每一個檢查點依登記順序回溯判定，負面結果照常生效，並揭露判定日晚於檢查點日；不得因驗證層晚到而略過、合併或重置任何檢查點。
- **知悉（不修訂）**：D-6.6 不變；D-1 的 `outlook.features → data(index)` 在核心只指 `app.services.index`；待決 #4 在核心期間不實作；D-12 Phase 3 只先交付大盤記錄器。

---

## Consequences（後果）

**好處**
- 規則一凍結就能開始累積樣本；閘門從 7 道降為 4 道，不依賴 ADR-0026、0028、0029 的核可。
- 沒有升級路徑，結構上不可能誤稱「優於基準」；尚未到期的標籤不出現在任何輸出。
- 每筆紀錄自足，程式與環境也一併鎖住，驗證層可以逐位重算。
- 表數從 25 張降為 5 張，trigger 沒有例外。

**代價與壞處**
- **時程**：quant 約 7～10 人日、日曆約 2～3 週，卡點是 C-8、C-4、#15／#16 與事先宣告 v0.32。
- **主機要平日晚上開機**：沒成功執行的日子就是 `late` 或沒有紀錄。h5 的格點會連續落在同一個星期幾，若固定某晚不開機，可能連續失去數週到約 3 個月的格點〔推論〕。
- **重審很快觸發**：h3 約在 D_v 後 36 天（T2）。因為 n＝30 幾乎沒有統計後果，提早設計驗證層反而能減少看過結果再調規則的誘因。
- **只改文字也會讓 n 歸零**：日後若風控要求改規則字面，h5 可能已累積 1～2 年。
- **程式或執行環境改變**：重算不一致就停止寫入，例如升級 Python 造成 1 ulp 的差異；只能登記新 claim，計數歸零。devops-sre 須固定執行環境。
- **部分證據日後無法補**：缺日原因、結算強制重抓、指數查證都沒有；作廢率可能較高〔推論〕。
- **整檔還原**：會遺失紀錄。依 D-8 第 3 點，失去的格點日後以不利於模型的方式計算。
- **畫面沒有新增**：CEO 只能從操作者報告看到已到期的紀錄與暫定對照。
- **只有大盤**：族群的 150 筆顯示閘門會更晚達到。
- **harness 的限制**：harness 驗證不了真實時序下的 PIT 與 `late`，只能靠合成 fixture。
- **容量**：每份快照約 45～50 KB，主 DB 每年約增加 10～15 MB〔推論〕。

---

## 對實作的約束（逐條可檢查；只列架構決策）
- **K-1 模組集合**：凍結期間，`app/forecast/` 只能有 D-1 第 3 點與 D-10 所列的模組；`settlement`、`correction`、`audit`、`validation`、`display`、`views`、`on_demand`、`replay_checks`、`index_verification`、`observed_days`、`market_run_guard`、`ledger_events` 都不得存在（Glob）。
- **K-2 依賴方向**：`app.forecast` → `app.outlook` → `app.dirdef`；`app.outlook.*` 不得 import `app.forecast.*`。兩者不得 import `app.api`、`app.demo`、`app.positions`、`app.portfolio`、`app.backtest`、`app.research`、`app.sectors`、`app.data.market_panel`、`app.ops_alert`；`app.advice.*` 只允許 `definitions.py` import `BANNED_PHRASES`（import graph）。
- **K-3 進入點**：`app.scheduler` 只經 `app.forecast.recorder` 進入核心，只註冊 `forecast_record`；`app.main` 不可達 `app.forecast`、`app.outlook`（import graph、route 掃描）。
- **K-4 單一寫入者**：5 張表的 INSERT 只在 `store.py`；寫入函式只由 `recorder.py` 與登記 CLI 呼叫（AST）。
- **K-5 表集合**：主 DB 中以 `forecast_`、`plan_` 開頭的表，恰好是 D-2 的 5 張（`sqlite_master`）。
- **K-6 單一定義**：`is_final`、bar 正規化與 `code_digest`、σ、標籤公式，各只在 D-1 指定的模組（grep）。
- **K-7 暫定對照隔離**：`scoring.py` 不被 `store.py`、`recorder.py`、`schema.py` import（import graph）。
- **K-8 狀態單值**：`validation_status` 的型別是只含 `'unverified'` 的 `Literal`，表的 CHECK 同值（測試）。
- **K-9 claim 數**：記錄中的前瞻 claim 恰好是 D-1 第 1 點的兩個 (`scope_kind`, `horizon`) 各一個；其餘前瞻 claim 都已被取代（CG-2 執行期核對）。
- **K-10 沒有回填**：recorder 的公開函式與 job 沒有 `T`、`as_of`、`clock` 類參數（簽章測試）。
- **K-11 管線驗收隔離**：harness 遇到正式主 DB 路徑就拒絕；正式程式路徑不 import harness，也沒有注入登記表的路徑（測試、import graph）。
- **K-12 沒有遷移**：`schema_version` 恆為 1；`schema.py` 沒有遷移函式（grep）。

---

## 失效條件（任一成立，本 ADR 須重審）
- **F-1**：核心表合計超過 200 MB，或快照單筆中位數超過 100 KB。
- **F-2**：連續 20 個平日中，以下兩項合計超過 30%：最新快照中出現、但沒有 `late = 0` 紀錄的定案 session 數，加上 `inputs_not_ready` 的日數。另外，任一 claim 自 D_v 起的第 0 相位格點遺失率超過 20% 時，也升級 CEO 與 devops-sre。
- **F-3**：`report verify` 發現任一筆重算不一致。停止記錄並查明。
- **F-4**：需要對預測帳 UPDATE 或 DELETE。
- **F-5**：`^TWII` 日期慣例查證（#49）顯示 bar 日期與台北交易日不一致，或資料源更換。
- **F-6**：n̂ 已達 c₁，驗證層 ADR 仍未核可。升級 CEO。
- **F-7**：要擴充到個股、族群或 on-demand（D-1 第 4 點）。
- **F-8**：主 DB 整檔還原、更換或重建，或備份以外的原因使核心表列數減少。

---

## 待決事項
**CEO**
1. 核可本 ADR；逐項核可 C-M1～C-M4。
2. **C-M4 明確同意**（附 D-11 的條件）。
3. **G-5 → CG-3 明確同意**（附 D-6 末點、D-8 第 3 點、F-8 的條件）。
4. 重審觸發參數：維持 90 天與 50%（建議），或 T2 改為 45 天。
5. dirdef 凍結前置條件：#15、#16 選甲或乙。甲是放寬，須風控確認。
6. C-8（F2-B 或 F2-A）與 C-4：都在關鍵路徑上。
7. 管線驗收用佔位規則 P-0、P-1（建議），或候選規則。
8. 知悉並決定：規則文字改任何一字，n 都會歸零。是否同意凍結前先請風控審規則文字的語意，並保留 D-1 第 2 點日後恢復「只改文字沿用原 claim」的門。
9. 主機平日晚上開機的承諾；是否加 18:10 執行。
10. 在 CG-1 之前以 #49 (a) 在本機代跑一次。
11. 知悉：報告不顯示尚未到期的方向；要看即時方向，等於 ADR-0025 D-6.6 的例外，須您明確同意，風控會保留書面反對意見。核心期間更換 claim 須修訂本 ADR。
12. 確認 C-1：接受多年內只會是「未驗證」。

**風控**：回送本 ADR 中改寫過的字面（逐項單項確認）；審規則文字的語意（凍結前）。

**quant**：凍結 h3、h5 規則與特徵公式規格、`OUTLOOK_RULE_FIELDS`、dirdef 常數與 N-139 的歸屬；事先宣告 v0.32（量化確認第 7 點清單）須在 claim 登記前定稿。

**data-engineer**：Yahoo 收盤在 15:00～18:00 是否已定案、是否等於官方收盤；成交量為空的列在快取路徑上怎麼處理。

**devops-sre**：CG-3 備份；定期備份在 n̂ 達 ⌈c₁÷2⌉ 之前上線；固定執行環境；排程交錯（N-116）；心跳。

**dev-lead**：依序實作 `is_final` → dirdef 補欄位 → schema／store／canonical → inputs／engine／baselines → recorder → claims CLI → report → harness → 接線 PR（核對 CG）。

---

## 未查證事項與作者揭露
- 沒有執行任何程式或測試，也沒有讀任何 DB。
- 強制重抓的方式、`staleness_minutes` 與被丟棄列在取數路徑上能否取得，都沒有逐行確認。
- ADR-0027 D-10 第 3 點前瞻 claim 的轉值時點，我只讀到登記與重放的部分；「第一筆 `forecast_record`」這個讀法依欄位名與事先宣告 §12 推定〔推論〕。
- 時程與容量數字取自 quant 量化確認，都是推論。

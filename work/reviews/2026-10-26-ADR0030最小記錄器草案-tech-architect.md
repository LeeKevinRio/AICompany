# ADR-0030 預測紀錄帳核心（最小記錄器）草案

- 審查者：tech-architect
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- 我起草了 **ADR-0030「預測紀錄帳核心——最小記錄器」**，狀態 proposed，全文在下方 code block。逐段數行約 305 行，沒有實際跑 `wc -l`，在 500 行內。
- 編號：Glob 查到最後一份是 0029。0013 由員工線佔用，ADR-0014、0016、0017 都有編號說明。repo 內 grep `ADR-0030|0030-` 無結果。
- 檔名：`docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- 核心內容：
  - 只記大盤 `^TWII` 的 3 日、5 日兩個前瞻 claim，共 5 張只增不改的表，trigger 沒有任何例外。
  - 每筆紀錄附 PIT 輸入快照，並在同一交易內寫入 B1、B2、B6、B8 四個基準預測。
  - 驗證狀態只有 `unverified` 一個值，DB CHECK 加 `Literal`，沒有升級路徑。
  - 寫入閘門由 7 道降為 4 道（CG-1～CG-4），不再依賴 ADR-0026、0028、0029 的核可。
  - ADR-0027 未被取代的部分全部凍結為附錄，重審觸發依 CEO 的兩個條件，先到者為準。
- **有 6 處與交辦字面不同，請你知悉：**
  1. **D-13（`MissingItem`）沒有凍結，改為沿用。** 記錄「證據不足」當下就要用它，B1 也已實作。
  2. **D-15（政策表、`plan_record`）也一併凍結。** 交辦沒列這一節，但它不屬於核心。
  3. **寫入截止改為「T 的次一個日曆日 00:00（台北）」，不採 ADR-0027 M-1 的 08:30。** 這樣不必查證盤前時間，也不需要交易日曆，G-4 因此整道拿掉。代價是主機必須平日晚上開機，清晨補跑的紀錄會記為 late。
  4. **核心只做大盤。** 個股與族群依賴 `adjust_series_pit`、N-120 等未完成項，留待修訂本 ADR 時擴充。
  5. **「固定未驗證」只出現在操作者報告。** ADR-0025 D-6.6 規定方向要等回放報告審查後才能上畫面，所以核心期間任何使用者畫面都沒有新東西。
  6. **依 CEO 的觸發條件 (T2)，3 日 claim 約在 D_v 後 5 週就觸發重審，5 日約 4 個月**（依週一至週五換算的推論）。

## 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A1 最小記錄器＋凍結驗證層（採用）** | 盡早累積樣本；沒有升級路徑，結構上不可能誤稱有效 | 要重開部分已核可的風控條件；日後重審可能要補表 | 少記驗證要的欄位。緩解：完整保存快照，日後逐位重算 |
| A2 暫停整條預測線 | 產能全部轉向好用性 | 違背 CEO 的需求 | 已投入成本歸零 |
| A3 維持 ADR-0027 全文 | 不必重工 | 仍被 7 道閘門與大量條文卡住 | 文件漂移，追蹤項持續增加 |

寫入截止（B1～B3）與核心範圍（C1～C2）兩張子表在 ADR 的 Options 一節。

## ADR 全文草稿

````markdown
# ADR-0030：stock-desk 預測紀錄帳核心——最小記錄器

- 狀態：proposed
- 日期：2026-10-26
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：CEO 2026-10-26 裁定 #57（`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第四節）；方案來源：`work/reviews/2026-10-26-產品審視-tech-architect.md` 方案 A。
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
1. 預測紀錄帳先上線「最小記錄器」：只記大盤（`^TWII`）3 日與 5 日兩個前瞻 claim；5 張只增不改的表；每筆附 PIT 輸入快照與四個基準預測；驗證狀態固定為 `unverified`，沒有升級路徑。
2. 寫入截止改為「T 的次一個日曆日 00:00（台北）」，不再依賴盤前時間的查證。
3. ADR-0027 的驗證層（結算、作廢、缺日稽核、驗證狀態、F-2、claim 計數細則、重放）凍結為附錄，不實作。「第一個檢查點前 90 天」與「n 達第一個檢查點的 50%」先到者觸發重審。
4. 原始輸入快照完整保存，驗證層日後可以只用帳內資料逐位重算。

**否決**
- 維持 ADR-0027 全文路線（A3）；暫停整條預測線（A2）。
- 核心期間把展望方向放上任何使用者畫面（ADR-0025 D-6.6 不動）。
- 核心期間寫入 on-demand、個股或族群紀錄。
- 以回填過去日期的方式「補樣本」。

**最大代價**
- 規則尚未凍結（`OUTLOOK_RULE_FIELDS` 與兩個登記表都是空的），第一筆紀錄的時程取決於 quant 凍結規則。
- 驗證層日後重算時，ADR-0027 設計中的部分證據（缺日原因、結算時強制重抓）已無法補記，作廢可能較多。
- 核心期間使用者畫面沒有任何新增；價值只在累積樣本。

---

## Context（背景）

### 1. 問題
- ADR-0027 有 25 張表、6 道寫入閘門（另有 on-demand 的 G-7）〔事實：`docs/adr/0027-…:76,86,89`〕，至今沒有任何一筆前瞻紀錄。
- 預測帳的價值取決於累積天數。模型比最強基準高約 13 個百分點時，大盤 5 日約 10 年、3 日約 6 年才有足夠檢定力〔事實：事先宣告 `:840`〕。升級判定多年內不會觸發，卻擋住了第一筆紀錄。
- CEO 裁定 #57：另立 ≤500 行的 ADR，只含記錄、PIT 輸入、基準並列、固定「未驗證」；驗證層凍結，第一個檢查點前再啟用。

### 2. 現況（事實）
- B1／B2 只 commit 了純函式模組：`app/forecast/`（`errors`、`band`、`definitions`、`claims`）、`app/dirdef/`（六個模組）、`app/outlook/`（`missing`、`volatility`、`basket`）、`app/ops_alert/model.py`。沒有 store、recorder、job 或 route〔`app/forecast/__init__.py:1-7`；`tests/test_forecast_gate_closed.py:40-56`〕。
- 兩個登記表與 `OUTLOOK_RULE_FIELDS` 都是空的〔`app/dirdef/registry.py:62-63`；`app/dirdef/rules.py:56`〕；事先宣告只有不在凍結範圍內的規則骨架〔事先宣告 `:2581`〕。
- `is_final`、`adjust_series_pit`、`wilder_atr` 在 `app/` 內都不存在（grep）；`TW_POLICY.publish_cutoff = 15:00` 已存在〔`app/data/freshness.py:131`〕。
- `^TWII` 經 `app/services/index.py` 取得，底層是主 DB 的 `price_bars_cache`〔`app/services/index.py:189`；`app/data/cache.py:39`；事先宣告 `:856`〕。該表衝突時覆寫，不是 PIT，所以必須在記錄當下擷取快照。

### 3. 限制
- ADR-0025（accepted）規定紀錄只增不改、PIT、並列基準（D-6）；判斷上畫面前，歷史回放報告必須已產出並經審查（D-6.6）〔`docs/adr/0025-…:412-414`〕。
- quant 2026-10-26：「回到 30 天前一路預測」只能當管線驗收，不計入驗證統計，也不得消耗唯一一次的正式重放〔`work/reviews/2026-10-26-產品審視-quant-researcher.md:95-109`〕。
- CEO #58：qa-reviewer PASS 加 CI 綠燈即可合併，Codex 在環境可用時補跑。CEO #60：風控在 ADR 階段審一次「拆除護欄或對使用者宣稱」的條文語意。

---

## Options（選項比較）

**A. 總體作法**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A1 最小記錄器＋凍結驗證層（採用）** | 盡早累積樣本；沒有升級路徑，結構上不可能誤稱有效；文件與實作量大降 | 要重開部分已核可的風控條件；驗證層日後要重審，可能補表 | 少記驗證要的欄位。緩解：完整保存原始輸入快照（D-5） |
| A2 暫停整條預測線 | 產能全部轉向好用性 | 違背 CEO「需要投資建議」；已投入成本歸零 | 重啟時脈絡散失 |
| A3 維持 ADR-0027 全文 | 不必重工 | 第一筆紀錄仍被七道閘門與大量條文卡住 | 文件漂移、追蹤項持續增加 |

**B. 寫入截止時點**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **B1 T 的次一個日曆日 00:00（台北，採用）** | 不需查證盤前時間，也不需交易日曆；一定早於 T+1 的任何盤前資訊 | 主機晚上沒開，當天只能記 `late` | 樣本累積變慢 |
| B2 next_session(T) 08:30（ADR-0027 M-1） | 允許清晨補跑 | 依賴 08:30 查證（G-4）與 ADR-0028 VS-6 | 查證前不能開始記錄 |
| B3 T+1 09:00（ADR-0025 原文） | 已核可 | 08:30～09:00 可能已有盤前委託資訊 | 前視偏誤 |

**C. 核心範圍**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **C1 只記大盤（採用）** | 只有一條指數序列；不需還原價、市場 DB、族群成員 | 個股與族群樣本較晚開始 | 兩者在 v1 本來就不顯示方向，延後成本低〔推論〕 |
| C2 大盤＋個股＋族群 | 三類同時累積 | 依賴 `adjust_series_pit`、N-120 等未完成項 | 核心被拖回 ADR-0027 的規模 |

---

## Decision（決策）

### D-1 核心範圍與模組
1. **claim**：只有 `scope_kind = market`、`horizon ∈ {3, 5}`、`kind = forward`，共兩個。`scope_key` 為單一固定值，由 quant 凍結時定名。
2. **同時只有一個在記錄中的 claim**：每個 (`scope_kind`, `horizon`) 只對到一個已登記的前瞻 claim。規則或定義有任何變更（含只改文字）都是新 claim，原 claim 停止記錄；核心期間不使用 PATCH／MINOR 沿用原 claim 的機制。
3. **新增模組**（ADR-0027 D-1 的其餘模組在凍結期間不得建立，K-1）：

| 模組 | 職責 |
|---|---|
| `app/forecast/schema.py` | 5 張表的 DDL 與 trigger；啟動時以 `sqlite_master` 核對，缺任何一項就拒絕寫入 |
| `app/forecast/store.py` | 只增不改的寫入（時間戳由 store 時鐘填入）；唯讀查詢（D_v、n̂、最近一次執行結果） |
| `app/forecast/canonical.py` | bar 值正規化與 `content_sha256` 的唯一定義 |
| `app/forecast/recorder.py` | job `forecast_record` 的唯一編排：CG-2 核對 → 決定 T → 擷取快照 → 計算 → 寫入 |
| `app/forecast/claims.py` | 既有純函式，另加操作者 CLI `python -m app.forecast.claims register` |
| `app/forecast/scoring.py` | 暫定對照的純函式（D-5 第 5 點）；ADR-0012 C-15 白名單 |
| `app/forecast/report.py` | 操作者 CLI（唯讀）：紀錄、基準、暫定對照、重算核對、重審觸發狀態、執行結果 |
| `app/outlook/inputs.py` | 大盤輸入：只經 `app.services.index` 取得，只收定案 bar |
| `app/outlook/engine.py` | 規則求值與特徵（純函式；規則集由呼叫端依登記版本傳入） |
| `app/outlook/baselines.py` | 發布當下的 B1、B2、B6、B8（D-4） |
| `app/data/session_calendar.py`（新檔） | 只實作 `is_final` 一個函式（ADR-0028 CS-17 指定的位置）；ADR-0028 核可後由它接手，不另寫第二份 |

4. **擴充到個股或族群**：須修訂本 ADR（或另立 ADR），並經風控審一次語意。前提至少有四項：ADR-0027 D-4 第 1、2、7 點與 D-5 重審後納入；`adjust_series_pit`、`wilder_atr` 已實作；後續追蹤清單 N-120 的預測端評估已經風控確認；市場 DB 與主 DB 有同一時點的備份。擴充不改變大盤 claim。

### D-2 資料表（主 DB；只列關鍵欄位）
1. `forecast_run(run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at, trigger, code_commit, schema_version)`：每次執行的第一個寫入，在讀取任何市場資料之前完成；`trigger` 只有 `scheduled`。
2. `forecast_run_end(run_id PK, outcome ∈ {ok, inputs_not_ready, gate_closed, error}, candidate_t NULL, records_written, error_class NULL, ended_at)`：沒有 end 列就代表程序中斷；`error_class` 只經 `app/forecast/errors.py::exception_class_name`，不存例外訊息。
3. `forecast_input_series(series_id, content_sha256 UNIQUE, series_kind = 'index_bars', source, source_status, bars_json, captured_at)`：原始輸入快照（D-5），以內容雜湊去重。
4. `forecast_record`：
   - 識別：`forecast_id`（ULID）、`run_id`、`claim_id`、`scope_kind`、`scope_key`、`horizon`、`data_as_of`（T）；
   - 版本：`definition_version`、`definition_sha256`、`rules_version`、`rules_sha256`；
   - 結論：`label ∈ {bullish, range, bearish, insufficient}`、`range_basis`、`missing_json`（ADR-0027 D-13 的 `MissingItem` 陣列）、`evidence_json`；
   - 判定材料：`band_def`（`K_h`、`EPS`、`sigma_d`、`valid_returns`、`up_pct`、`down_pct`）、`base_close`、`baseline_predictions_json`（D-4）；
   - PIT 證明：`input_series_sha256`、`inputs_max_fetched_at`；
   - 時間：`created_at`、`late ∈ {0, 1}`、`late_cutoff_at`、`valid_until_session_estimate`；
   - `validation_status`：CHECK 只允許 `'unverified'`；
   - `content_hash`：涵蓋 `forecast_id`、`run_id`、`created_at`、`late` 以外的全部欄位；
   - `UNIQUE(claim_id, data_as_of)`：每個 claim 每個 T 最多一筆；核心沒有更正列。
5. `forecast_claim_registry(claim_id PK, scope_kind, horizon, kind, rules_version, rules_sha256, rules_logic_sha256, rules_bytes, definition_version, definition_sha256, definition_logic_sha256, definition_json, frozen_commit, prereg_doc_path, prereg_doc_blob, review_refs, registered_at)`：`kind` CHECK 只允許 `'forward'`。
6. **5 張表全部**有 `BEFORE UPDATE`／`BEFORE DELETE` 的 `RAISE(ABORT, 'append-only')`，沒有任何例外。ADR-0027 registry 的一次性轉值不採用：`first_record_at` 與 m 都由查詢導出。
7. 寫入驗證沿用已 commit 的單一判定：`band_def` 經 `app/forecast/band.py` 的 `threshold_inputs()` 與 `labeled_snapshot_violations()`，`missing_json` 經 `app/outlook/missing.py` 的型別驗證；不成立就拒絕寫入。

### D-3 PIT 輸入與寫入時點
1. **決策日 T**：`app.services.index` 讀到的最新一根定案 `^TWII` bar 的 session 日期。recorder 沒有指定 T、指定時鐘或回填過去日期的參數。
2. **定案**：bar 的 `as_of` 與 `fetched_at` 取較早者，不得早於 T 日 `TW_POLICY.publish_cutoff`（15:00 Asia/Taipei；ADR-0028 CS-17 口徑）。T 日 bar 不定案時，以取數路徑既有的方式重抓一次；仍不定案就記 `inputs_not_ready`，不寫紀錄，不用暫定值，也不改用前一天。
3. **寫入截止**：`late_cutoff_at` ＝ T 的次一個日曆日 00:00:00（Asia/Taipei）。`created_at`（store 時鐘）早於它時 `late = 0`，否則 `late = 1`。`late = 1` 照寫，但永遠不進任何主統計。臨界測試：23:59:59.999999 與 00:00:00。
4. **輸入範圍**：只用 T 日（含）以前的定案 bar；快照在同一次執行內擷取，所以 `late = 0` 紀錄的所有輸入，其 `fetched_at` 都早於 `late_cutoff_at`。
5. **禁用的 hindsight 來源**：`app/forecast/**`、`app/outlook/**` 不得出現 `price_bars_cache`、`dividend_events`、`_hindsight_view` 識別字，不得 import `app.demo`、`app.backtest`、`app.research`，也不得以事後重抓的 bars 取代已擷取的快照。
6. **證據不足照寫**：輸入不足、σ 退化或可評估規則不足時記 `label = insufficient`，`missing_json` 非空，`up_pct`、`down_pct` 為 null；不補值，不用替代估法（事先宣告 §5.1）。
7. **排程**：job `forecast_record` 平日 22:10 執行、23:10 重試，啟動後 3 分鐘補跑；`timezone = "Asia/Taipei"`、`max_instances = 1`、`coalesce = True`（沿用 ADR-0027 D-7 第 1 點）。只有這一個 job，也只有 recorder 寫入預測帳。

### D-4 基準並列與驗證狀態固定
1. 每筆紀錄在同一個寫入交易內寫 `baseline_predictions_json`：B1、B2、B6、B8，是事先宣告 §3 大盤必備集合中發布當下就能算的四個。每一項為標籤，或 `unavailable` 加原因。基準與主預測用同一份快照計算，寫入後不重算、不改寫。B2 的歷史已實現標籤，由 dirdef 標籤公式在快照上計算，命名不得用 forward return 類識別字。
2. B7、B7r（評估時才算的事後眾數）與 B0、B5 屬驗證層，凍結。
3. 任何輸出（操作者報告，以及日後任何 API）列出模型標籤時，必須同列四個基準，版面權重相同；不得只列模型標籤。
4. `validation_status` 只有 `unverified` 一個值，使用者面字面為「未驗證」，逐字由風控定。`app/` 內沒有任何計算驗證狀態的函式；要改變狀態，只能經驗證層 ADR 新增的表與程式，不得改寫核心的列。
5. 核心輸出不得出現命中率、區間、n 或「優於」「不如」類彙總。唯一例外：操作者報告列出重審觸發用的 n̂（D-8 第 4 點），並標明「重審觸發用計數，不是驗證統計」。
6. 核心不在任何使用者畫面顯示方向：`app.main` 不掛載 `/api/forecast`、`/api/outlook`；ADR-0025 D-6.6 不變。

### D-5 原始輸入快照與日後重算
1. **快照內容**：該筆計算（特徵、σ_d、B1、B2）讀過的每一根 bar，逐根記 `session_date`、OHLCV、`source`、`as_of`、`fetched_at`，以及取數路徑提供的任何原始時間戳記；正規化只經 `canonical.py`。
2. **自足**：紀錄引用 `input_series_sha256`，登記表存規則檔位元組與定義物件的 JSON，`forecast_run` 存 `code_commit`。重算不依賴工作目錄的現況。
3. **重算不變式**：以快照、登記表中的定義與規則位元組、同一 `code_commit` 重算，`label`、`band_def`、`baseline_predictions_json`、`missing_json` 都要逐位相同，`content_hash` 也相等。操作者 CLI `report verify` 執行這項核對，不一致即為 F-3。
4. **結果端資料**：核心不寫結算列。T+h 的 bar 由之後各筆紀錄的快照涵蓋，並帶有當時的 `fetched_at`；正式結算由解凍後的驗證層從這些快照重算。快照沒涵蓋到的日子，依屆時驗證層的規則處理，可能作廢。
5. **暫定對照**：`scoring.py` 內的純函式。輸入是一筆紀錄，以及之後涵蓋 T 後 h 個定案 session 的快照，而且 `valid_until_session_estimate` 已過（ADR-0025 AV-18）。它依 dirdef 標籤公式輸出實現標籤，以及模型與四個基準各自是否符合；任何輸入缺漏、不定案或日期不連續，就輸出「無法對照」與原因。結果不寫入任何表，不被 `store.py`、`recorder.py` import，只由 `report.py` 輸出，並固定標示「暫定對照，非正式結算，不計入任何驗證統計」（逐字由風控定）。它不是 ADR-0027 D-9 的結算，結果可能不同。

### D-6 寫入閘門（CG；全部成立前不得寫入任何紀錄）
- **CG-1**：本 ADR accepted，含 CEO 對 C-M1～C-M4 的核可。
- **CG-2**：
  - `dirdef-v1.0` 已登記於 `PUBLISHED_DIRECTION_DEFINITIONS`，含 CEO C-8 選定的 `f2_variant` 與決策出處；
  - 大盤 h3、h5 規則已登記於 `PUBLISHED_RULESETS`，`OUTLOOK_RULE_FIELDS` 已設定；
  - 兩個前瞻 claim 已經 CLI 登記，`frozen_commit`、`prereg_doc_blob`、`rules_bytes`、`definition_json` 都非空。
  - recorder 每次執行都先核對：登記表恰好含 D-1 第 1 點的兩個 claim，各自的雜湊等於 `app/forecast/definitions.py` 的回傳結果。不成立就記 `gate_closed`，不寫紀錄。
- **CG-3**：核心 schema 第一次在正式主 DB 建立之前，以 SQLite backup API 或 `VACUUM INTO` 取得一次主 DB 的一致備份，路徑與 sha256 記在接線 PR。核心期間 schema 固定為 v1，不做任何遷移；要改 schema，須等 ADR-0026 D-6（遷移前備份）核可並實作。
- **CG-4**：`app/forecast/**`、`app/outlook/**`、`app/data/session_calendar.py` 與 scheduler 接線，都通過 qa-reviewer PASS 與 CI 綠燈（CEO #58）。
- CG-1、CG-3、CG-4 由 qa-reviewer 在接線 PR 核對；job 只在該 PR 註冊。
- 對 ADR-0027 D-14 的取代：G-1 → CG-1；G-2、G-3 → CG-2；G-4 不再需要，因為 D-3 第 3 點不依賴 08:30；G-5 → CG-3；G-6 → CG-4；G-7 隨 on-demand 移出核心而失效。

### D-7 30 日管線驗收
1. 用途只限驗證管線：取數、定案判定、快照、寫入、重算、暫定對照、報告。它不是績效證據，不計入任何驗證統計，也不消耗事先宣告 §4.7 唯一一次的正式重放。
2. 以 `scripts/` 或 `tests/` 內的 harness 執行，使用暫存 DB 與注入時鐘，呼叫同一套 recorder 程式；harness 遇到正式主 DB 路徑就拒絕執行。正式 recorder 不因此增加回填參數。
3. 不在正式 DB 登記 claim，不寫正式紀錄；登記表 `kind` 只允許 `forward`，結構上不可能登記重放 claim。
4. **規則集**：預設用佔位規則，不得是任何將登記為 claim 的候選規則（例如直接輸出 B8 的計算器）。CEO 若選用候選規則，只能用已凍結並 commit 的版本；該版本要在登記表 `review_refs` 與事先宣告註明「已看過管線驗收期間的結果」，日後重放報告照實揭露，之後任何修改都算新版本。
5. 輸出固定標示「管線驗收，不計入驗證統計，未驗證」（逐字由風控定）。

### D-8 與 ADR-0027 的關係、凍結附錄與重審觸發
1. **由本 ADR 取代**（僅限大盤核心；衝突時以本 ADR 為準）：
   - D-1、D-2、D-3：分別改為本 ADR 的 D-1 第 3 點、沒有例外的只增不改、D-2 的 5 張表；
   - D-4 第 3、4、5、8 點中適用大盤的部分；
   - D-7 第 1 點與寫入截止；
   - D-8：執行證據改由 `forecast_run`／`forecast_run_end` 保存；
   - D-14：改為 CG。
2. **沿用**：D-13（`MissingItem`；記錄當下就要用，B1 已實作）。
3. **凍結為附錄**（不實作，不再修訂）：
   - D-4 第 1、2、6、7 點，D-5，D-6，D-7 其餘各點；
   - D-8 的缺日列與稽核，D-9～D-12（結算、作廢、更正、重放、claim 計數與 m、驗證四態、F-2），D-15；
   - M-1～M-11，未被本 ADR K 條取代的 FL、FLT 各條，以及待決事項。
   - 凍結期間，附錄中的 CEO 待決事項暫停，CEO 不必裁示。已取得的 CEO 明確同意（決策包 #47、#48、#50、#51、#52、#55）保留，條文不變就不必重問。
4. **重審觸發**（每個前瞻 claim 各自判定，任一 claim 先到即觸發）：
   - c₁ ＝ 該 claim 已登記 dirdef 的第一個檢查點。大盤為 `CHECKPOINTS_MARKET_SYMBOL[0]`，事先宣告 §4.5 為 30。
   - **(T1) n 達 50%**：n̂ ≥ ⌈c₁ ÷ 2⌉。n̂ ＝ 第 0 相位格點（D_v，以及其後快照中每第 h 個定案 session）上，有 `late = 0` 紀錄、而且 T+h 已出現在之後某份快照中的格點數。n̂ 不扣作廢與 PIT 違規，是正式 n 的上界，只會讓觸發提早。
   - **(T2) 第一個檢查點前 90 天**：今天 ≥ d₁ − 90 個日曆日；d₁ ＝ D_v 加 c₁ × h 個週一至週五。不扣休市日，所以 d₁ 不晚於實際日期，只會讓觸發提早。
   - D_v ＝ 該 claim 第一筆 `late = 0` 紀錄的 T（同 ADR-0027 D-14 的定義）。
   - n̂、d₁ 與是否觸發，都只由 `store.py` 的唯讀查詢導出，`report.py` 每次都輸出；首次成立時 recorder 記 WARNING。
5. **觸發後**：tech-architect 在 30 日內以凍結附錄為底，起草驗證層 ADR，只納入第一個檢查點真正需要的部分；風控審一次語意，CEO 核可。核可前紀錄照常累積，狀態維持 `unverified`。驗證層 ADR 核可後，ADR-0027 改標 superseded。
6. **重審的界限**：`dirdef-v1.0` 已登記的判定常數（基準集合、檢查點、α\* 相關常數、§4.3 條件、`f2_variant`、退出期限），對既有 claim 只能往更嚴的方向改。要放寬就算新 claim、計數歸零，並須風控與 CEO 明確同意。
7. **提前解凍**：歷史重放是大盤展望上畫面的唯一路徑（ADR-0025 D-6.6），CEO 可以單獨提前解凍 ADR-0027 D-9 第 7 點與相關表，程序同第 5 點。

### D-9 保留的安全底線（逐條可檢查）
- **S-1 只增不改**：5 張表都有 UPDATE／DELETE 的 RAISE trigger，沒有例外（以 `sqlite_master` 核對；啟動時缺一就拒絕寫入）。
- **S-2 時間戳由 store 填入**：`started_at`、`created_at`、`captured_at`、`registered_at`、`ended_at` 都不是寫入函式的參數（簽章測試）。
- **S-3 寫入時點**：`late` 由 store 依 D-3 第 3 點計算，不接受呼叫端傳入；`late = 1` 不進任何統計（臨界測試）。
- **S-4 只用定案 bar**：不定案就記 `inputs_not_ready`，不寫暫定值（測試）。
- **S-5 禁用 hindsight 來源**：依 D-3 第 5 點（grep 加 import graph）。
- **S-6 沒有回填路徑**：recorder 與 job 沒有指定 T 或時鐘的參數（簽章測試）。
- **S-7 定義先凍結**：沒有已登記的 claim 就沒有紀錄（CG-2 執行期核對）；登記表與紀錄都存雜湊，執行期重算比對。
- **S-8 基準並列**：每筆紀錄都有 B1、B2、B6、B8 四項（寫入驗證）；輸出不得只列模型標籤。
- **S-9 固定未驗證**：`validation_status` CHECK 只允許 `'unverified'`；`app/` 內不得出現 `better_than_baseline`、`not_better_than_baseline`（grep）。
- **S-10 fail-closed**：缺漏、不定案或來源不明時，記 `insufficient` 或不寫，不補值。
- **S-11 不上畫面**：沒有 forecast／outlook route；ADR-0025 D-6.6 不變（route 掃描測試）。
- **S-12 可重算**：D-5 第 3 點的不變式（測試；操作者 `report verify`）。
- **S-13 管線驗收隔離**：依 D-7 第 2～3 點（harness 拒絕正式路徑的測試）。
- **S-14 規則式、不用 LLM、不下單**：展望只由 YAML 規則求值；ADR-0025 AV-10、AV-20 照舊。
- **S-15 祕密與持倉**：紀錄、快照、log 不含祕密，也不含持倉成本與股數（核心不讀持倉）。
- **S-16 合併與備份**：qa-reviewer PASS 加 CI 綠燈才合併；依 CG-3 備份；核心期間不遷移。

### D-10 已 commit 的 B1／B2 程式

| 程式 | 處置 |
|---|---|
| `app/dirdef/`（全部） | 沿用。`DirectionDefinition` 的驗證常數（檢查點、α\*、§4.3、bootstrap）照樣在凍結時登記，等於事先宣告判定標準；核心只讀標籤常數與 `CHECKPOINTS_MARKET_SYMBOL` |
| `app/forecast/definitions.py` | 沿用；仍是登記表的唯一讀取點 |
| `app/forecast/claims.py` | `claim_id` 沿用並加登記 CLI；`count_m`、`m_eff` 暫不使用（屬驗證層） |
| `app/forecast/band.py` | 沿用（寫入驗證） |
| `app/forecast/errors.py` | 沿用基底、`LabeledThresholdSnapshotIncompleteError`、`exception_class_name`；`WriteGateClosedError` 的閘門列舉改為 CG 編號；其餘例外類別保留不刪，核心不使用 |
| `app/outlook/missing.py` | 沿用 |
| `app/outlook/volatility.py` | 沿用（`sigma_d`） |
| `app/outlook/basket.py` | 暫不使用（族群） |
| `app/ops_alert/model.py` | 暫不使用。核心以 WARNING log 與 `forecast_run_end` 呈現執行狀態，心跳由 devops-sre 另案讀取 |
| `tests/test_forecast_gate_closed.py` | 保留到接線 PR；接線 PR 改為「只允許 job `forecast_record`，仍然沒有 route」 |

### D-11 對 ADR-0025 的影響（每項須 CEO 核可；ADR-0027 的 M-1～M-11 隨凍結暫停）
- **C-M1（收緊）**：D-6.2、AV-17、AT-6、F-3、D-12 Phase 3 驗收：截止由 T+1 09:00 改為 T 的次一個日曆日 00:00（台北）；欄位 `recorded_after_next_open` 改名 `late`，另存 `late_cutoff_at`；臨界改為 23:59:59.999999 與 00:00:00。
- **C-M2（收緊）**：D-6.1、D-6.2、AV-17：核心只寫 D-2 的 5 張表；`forecast_outcome`、`plan_record`、`plan_outcome` 在核心期間不寫入；「NULL 變成值」的例外不採用；不寫 `supersedes` 更正列，更正留給驗證層從快照重算；`input_digest` 改由 `input_series_sha256` 承擔。
- **C-M3（改定義）**：D-6.3、AT-7：結果定義改依凍結的 `dirdef-v1.0`（對數報酬、σ60、K_3＝K_5＝0.43、嚴格不等式加 EPS、平手歸震盪；同 ADR-0027 M-3 與事先宣告 C-4）。
- **C-M4（兩面）**：D-6.5、F-2：核心期間驗證狀態只有 `unverified`（取代 `insufficient_sample` 的名稱），不產生 `better_than_baseline` 或 `not_better_than_baseline`；F-2 的評估順延到驗證層 ADR 核可之後。收緊面：不可能出現正面宣稱。放寬面：驗證層 ADR 若晚於 n̂ 達 N_MIN，負面結果也不會出現。核心不上畫面，使用者看不到任何狀態〔推論〕，但仍須 CEO 明確同意。
- **知悉（不修訂）**：D-6.6 顯示閘門不變；D-1 依賴圖的 `outlook.features → data(index)`，在核心只指 `app.services.index`，不經 `load_bars`；待決 #4（臨時查詢的個股也記帳）在核心期間不實作；D-12 Phase 3 只先交付大盤記錄器，回放報告與顯示隨驗證層再做。

---

## Consequences（後果）

**好處**
- 規則一凍結就能開始累積前瞻樣本；寫入閘門從 7 道降為 4 道，不再依賴 ADR-0026、0028、0029 的核可。
- 系統沒有升級路徑，結構上不可能誤稱「優於基準」，本身就是 fail-closed。
- 每筆紀錄自足（快照，加上登記的定義與規則位元組），驗證層日後可以逐位重算，不必改寫核心的列。
- 表數從 25 張降為 5 張，trigger 沒有例外。

**代價與壞處**
- **時程不由本 ADR 決定**：規則與 `dirdef-v1.0` 常數凍結之前，一筆都寫不了。
- **主機要在平日晚上開機**：22:10～24:00 沒有成功執行，當天就記 `late`，不計入。相較 ADR-0027 的 08:30，少了清晨補跑的機會。
- **3 日 claim 很快觸發重審**：依 D-8 第 4 點 (T2)，h＝3 時 d₁ 約為 D_v 加 90 個平日（約 126 日曆日），所以約在 D_v 後 5 週觸發；h＝5 約在 D_v 後 4 個月〔推論〕。
- **部分證據日後無法補記**：核心不寫缺日列與原因（例如 `db_restored`），不做結算強制重抓，不記指數查證。驗證層只能依快照與執行紀錄重建，作廢率可能高於 ADR-0027 的設計〔推論〕。
- **整檔還原會遺失紀錄**：還原點之後的紀錄會消失；之後重寫同一個 T 必定是 `late = 1`，不會變成前瞻樣本，但缺口無法標示原因。
- **使用者畫面沒有新增**：核心期間沒有任何方向、狀態或對照上畫面；CEO 只能從操作者報告看到結果。
- **只有大盤**：個股與族群的樣本延後開始；族群的 150 筆顯示閘門也因此更晚達到。
- **暫定對照與正式結算可能不同**：暫定對照不處理休市確認、缺 bar 等待等規則，只在輸入完整時輸出。
- **管線驗收**：用佔位規則就看不到模型本身的表現；改用候選規則，該版本就要帶著「已看過」的揭露。
- 每天一份約 300 根 bar 的快照，主 DB 每年約增加數 MB〔推論〕。

---

## 對實作的約束（逐條可檢查；只列架構決策）
- **K-1 模組集合**：凍結期間，`app/forecast/` 只能有 D-1 第 3 點與 D-10 所列的模組；`settlement`、`correction`、`audit`、`validation`、`display`、`views`、`on_demand`、`replay_checks`、`index_verification`、`observed_days`、`market_run_guard`、`ledger_events` 都不得存在（Glob）。
- **K-2 依賴方向**：`app.forecast` → `app.outlook` → `app.dirdef`；`app.outlook.*` 不得 import `app.forecast.*`。`app/forecast/**`、`app/outlook/**` 不得 import `app.api`、`app.demo`、`app.positions`、`app.portfolio`、`app.backtest`、`app.research`、`app.sectors`、`app.data.market_panel`、`app.ops_alert`；`app.advice.*` 只允許 `app/forecast/definitions.py` import `BANNED_PHRASES`（import graph）。
- **K-3 進入點**：`app.scheduler` 只經 `app.forecast.recorder` 進入核心，也只註冊 job `forecast_record`；`app.main` 不可達 `app.forecast`、`app.outlook`（import graph、route 掃描）。
- **K-4 單一寫入者**：5 張表的 INSERT 只出現在 `app/forecast/store.py`；store 的寫入函式只由 `recorder.py` 與 `claims.py` 的登記 CLI 呼叫（AST 列舉呼叫點）。
- **K-5 表集合**：主 DB 中以 `forecast_`、`plan_` 開頭的表，恰好是 D-2 的 5 張（`sqlite_master` 測試）。
- **K-6 單一定義**：`is_final` 只在 `app/data/session_calendar.py`，bar 正規化只在 `canonical.py`，σ 只在 `volatility.py`，標籤公式只在 `app/dirdef/`（grep）。
- **K-7 暫定對照隔離**：`scoring.py` 不被 `store.py`、`recorder.py`、`schema.py` import；它的回傳型別不出現在任何寫入函式的參數中（import graph、AST）。
- **K-8 狀態單值**：`validation_status` 的型別是只含 `'unverified'` 的 `Literal`，表的 CHECK 同值（測試）。
- **K-9 claim 數**：前瞻 claim 恰好是 D-1 第 1 點的兩個，每個 (`scope_kind`, `horizon`) 只有一個（CG-2 執行期核對）。
- **K-10 沒有回填**：recorder 的公開函式與 job 沒有 `T`、`as_of`、`clock` 類參數；時鐘只在組裝時注入一次（簽章測試）。
- **K-11 管線驗收隔離**：harness 遇到正式主 DB 路徑就拒絕執行；正式程式路徑不 import harness（測試、import graph）。
- **K-12 沒有遷移**：核心期間 `schema_version` 恆為 1；`schema.py` 沒有遷移函式（grep）。

---

## 失效條件（任一成立，本 ADR 須重審）
- **F-1**：核心表合計超過 200 MB，或快照單筆中位數超過 100 KB。
- **F-2**：連續 20 個平日中，`late = 1` 或 `inputs_not_ready` 的日數超過 30%。表示排程或主機方案失效，升級 CEO 與 devops-sre。
- **F-3**：`report verify` 發現任一筆重算不一致。停止記錄，查明是否有 PIT 或程式問題。
- **F-4**：需要對預測帳 UPDATE 或 DELETE。
- **F-5**：`^TWII` 日期慣例查證（決策包 #49）顯示 bar 日期與台北交易日不一致，或資料源更換。〔推論：日期整體偏一天時紀錄會全部記為 `late = 1`，屬 fail-closed，但仍要重審〕
- **F-6**：n̂ 已達 c₁，驗證層 ADR 仍未核可。升級 CEO。
- **F-7**：要擴充到個股、族群或 on-demand（D-1 第 4 點）。

---

## 待決事項
**CEO**
1. 核可本 ADR；逐項核可 C-M1～C-M4。C-M4 有放寬面，須明確同意。
2. C-8：選 F2-B（建議）或 F2-A。它是 dirdef 的必填欄位，必須在任何真實資料被看過之前定案。
3. 與 quant 凍結 `dirdef-v1.0` 常數（事先宣告 C-4）；並知悉判定標準在凍結時一併登記。
4. 確認 C-1：接受大盤展望多年內都只會是「未驗證」。
5. 30 日管線驗收用佔位規則（建議）或候選規則（D-7 第 4 點）。
6. 知悉：核心期間沒有任何方向上畫面；主機須平日晚上開機；3 日 claim 約在 D_v 後 5 週觸發重審；ADR-0027 的 CEO 待決事項暫停。

**風控（依 CEO #60，只審一次語意）**
1. 拆除或替換護欄的條文：D-6（G-4、G-5、G-7 的取代）、D-8 第 1 與第 3 點（缺日列凍結）、C-M4 的放寬面、D-2 第 6 點（不採用 registry 一次性轉值）。
2. D-4 第 3 點（基準並列）與第 5 點（不得彙總）的範圍是否足夠。
3. 操作者報告與管線驗收的固定標示逐字（D-5 第 5 點、D-7 第 5 點）。

**quant**
1. 凍結大盤 h3、h5 規則、`OUTLOOK_RULE_FIELDS` 與 `dirdef-v1.0`（含 N-139 的欄位集合）；這是第一筆紀錄的關鍵路徑。
2. 確認 n̂ 的定義與 c₁；定出 B2 在快照上計算所需的 bar 數，據以決定快照視窗。
3. 事先宣告固定在 v0.31；核心需要的變更（截止時點、快照、單一 claim）集中為一版登記。
4. 佔位規則的形式（D-7 第 4 點）。

**devops-sre**：CG-3 的備份；排程與既有 job 的交錯（N-116）；以 `forecast_run_end` 做心跳的讀取方式。

**dev-lead**：實作順序為 `is_final` → schema／store／canonical → inputs／engine／baselines → recorder → claims CLI → report → harness → 接線 PR（核對 CG）。

---

## 未查證事項與作者揭露
- 沒有執行任何程式或測試，也沒有讀任何 DB。
- 沒有逐行確認 `app.services.index` 是否逐根提供 `fetched_at` 與原始時間戳記，也沒有確認強制重抓的方式。若取數路徑沒有提供，D-5 第 1 點以能提供的時間為限，並在快照中標明缺哪些時間。
- 「每年數 MB」與「約 5 週、4 個月觸發」都是推論。
- B2 需要 250 筆已實現標籤，所需的快照視窗長度沒有計算，由 quant 定。
- 沒有查證 TWSE 盤前委託實際開始的時間；本 ADR 的截止時點刻意設計成不依賴它。
````

## ADR-0027 檔頭指標字面

**ADR-0027**：Grep `^- 狀態：proposed$` 恰好 1 次（第 3 行）；子字串 `狀態：proposed` 也只出現 1 次。

- old：
  ```
  - 狀態：proposed
  ```
- new：
  ```
  - 狀態：proposed（2026-10-26 起：大盤核心由 ADR-0030 部分取代，其餘凍結為 ADR-0030 的附錄，不再修訂；見下一行）
  - 凍結註記（ADR-0030，proposed）：依 CEO 2026-10-26 裁定 #57。由 ADR-0030 取代：D-1、D-2、D-3、D-4 第 3、4、5、8 點的大盤部分、D-7 第 1 點與寫入截止、D-8 的執行證據部分、D-14；沿用：D-13；其餘條文（含 D-5、D-6、D-8 缺日列與稽核、D-9～D-12、D-15、M-1～M-11、FL／FLT、待決事項）凍結，不實作。重審觸發見 ADR-0030 D-8 第 4 點。ADR-0030 核可前，兩份都不得據以寫入前瞻紀錄。
  ```

**ADR-0025**（D-11 要求加這行指標）：
- 錨點：以 `- 修訂（提案中）：ADR-0027（proposed）` 開頭的那一行（第 11 行），Grep 恰好 1 次。
- 在它之後插入一行：
  ```
  - 修訂（提案中）：ADR-0030（proposed）提案部分修訂 D-6.1、D-6.2、D-6.3、D-6.5 驗證狀態、F-2 評估時點、AV-17、AT-6、AT-7、F-3 與 D-12 Phase 3 驗收欄位名（C-M1～C-M4，見 docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md）；ADR-0027 的 M-1～M-11 隨其凍結暫停；各項須 CEO 核可，核可前本檔為準；本檔原文不改。
  ```

**落檔說明**
- 分支：只落在 `product/stock-desk`。ADR-0025 註明產品 ADR 不存在於 main。
- 一個 commit 放三處改動：新檔加上兩個檔頭。commit message 建議：`docs: 新增 ADR-0030 預測紀錄帳核心（最小記錄器）`。
- 依 CEO #60，計數與逐字核對改由腳本或 qa 處理，不送風控。
- 我是唯讀職能，沒有寫任何檔，由 tech-writer 或作者代寫。

## 結案或凍結的追蹤項（N-100～N-149）

部分長列我只讀到前約 160 字，N-115 的子項沒有逐項讀全文。

- **可結案（16 項）**：
  - N-100：已落檔。
  - N-106：job 只在接線 PR 註冊（K-3、CG）。
  - N-107、N-108、N-110、N-117：N-86 的記錄步驟已被取代。
  - N-111、N-129：on-demand 移出核心。
  - N-113、N-128、N-132、N-137、N-146：已在 B1／B2 實作或已被接受。
  - N-122：CG-2／K-9 在執行期核對 claim 集合。
  - N-124：規則位元組存進登記表，每個 horizon 只有一個 claim。
  - N-143：紀錄與登記表都存 `definition_sha256`。
- **可結案（ADR-0027 不再修訂，連帶失效，5 項）**：N-125、N-130、N-131、N-145、N-147。其中 N-147 由 D-1 第 2 點承接，N-125 是因 G-4 拿掉而失效。
- **N-115**：整體結案。子項不是被 D-1／K-1 取代，就是已實作或隨 on-demand 失效。
- **凍結（隨附錄，24 項）**：
  - 驗證層顯示與用語：N-101、N-102、N-103、N-104、N-105。
  - 個股與 `scope_reason`：N-109、N-112。
  - 缺日稽核：N-114；CEO #55 的同意保留。
  - 除權息與結算：N-118、N-119、N-120、N-121、N-123、N-127、N-134、N-135。
  - ops_alert render：N-133。
  - 族群：N-138、N-140、N-141、N-148、N-149。
  - N-142 (b)。
- **維持開啟（核心仍需要）**：
  - N-116、N-139、N-144、N-136、N-142 (a)(c)(d)。
  - N-126 維持開啟，但建議風控把期限由「D_v 前」改為「規則文字上畫面前」。這是改風控定的期限，須風控同意。

## CEO／風控／quant 事項

已寫在 ADR「待決事項」一節，這裡只列要點：
- **CEO**：核可 ADR 與 C-M1～C-M4（C-M4 須明確同意）；決定 C-8；與 quant 凍結 C-4；確認 C-1；選擇管線驗收用哪種規則；知悉 5 週觸發重審與「主機須平日晚上開機」。
- **風控**：審一次拆除或替換護欄的條文語意（G-4、G-5、G-7、缺日列凍結、C-M4 放寬面、registry 一次性轉值不採用）；定兩種固定標示的逐字；N-126 的期限。
- **quant**：凍結規則與 dirdef，這是關鍵路徑；確認 n̂ 與 c₁、B2 所需視窗；事先宣告只集中一版登記；定佔位規則的形式。

## 驗證

方法：只用 Read、Glob、Grep，沒有執行任何指令，沒有寫任何檔。

**完整讀過**
- `/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（L1-74）
- `/home/user/AICompany/work/reviews/2026-10-26-產品審視-tech-architect.md`（L1-162）
- `/home/user/AICompany/work/reviews/2026-10-26-產品審視-quant-researcher.md`（L1-166）
- `/home/user/AICompany/docs/adr/0001-record-architecture-decisions.md`（L1-47）
- `/home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md`（L1-653）

**ADR-0027 部分讀取**（`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`）
- 讀了 L1-319、L337-386、L908-1007、L1615-1654、L2331-2580、L3374-3518。
- Grep 了章節標題、表名、FL-1～FL-12。
- 沒有讀 D-3 其餘部分（L387-907）、D-7 第 2 點以後、D-8、D-9、D-11 其餘部分，以及 FL 全表。

**事先宣告**（`/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`）
- Grep 了章節標題；讀了 L831-940、L1103-1152、L1459-1488、L2324-2345。

**追蹤清單**（`/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`）
- N-100～N-149 各列，長列只讀到前約 160 字。

**程式**（路徑前綴 `/home/user/AICompany/apps/stock-desk/backend/`）
- 完整讀過：`app/forecast/__init__.py`、`app/forecast/claims.py`、`app/dirdef/registry.py`、`app/dirdef/definition.py`、`app/dirdef/__init__.py`、`app/outlook/__init__.py`、`app/ops_alert/__init__.py`。
- 部分讀取：`app/forecast/definitions.py`（L1-60）、`app/dirdef/rules.py`（L1-70）、`app/outlook/basket.py`（L1-50）、`tests/test_forecast_gate_closed.py`（L1-60）。
- Grep：`app/forecast/` 各檔的類別與函式清單、各檔行數；`is_final`、`adjust_series_pit`、`wilder_atr` 都無結果；`TW_POLICY.publish_cutoff` 在 `app/data/freshness.py:131`；`price_bars_cache` 在 `app/data/cache.py:39`；`app/services/index.py` 的簽章；`app/` 內沒有既存的 `forecast_`、`plan_` 表，也沒有狀態字串；`app/data/session_calendar.py` 不存在。

**其他 Grep**
- ADR-0028 的 CS-17、VS-1、VS-4。
- ADR-0026、0028、0029 的狀態列，都是 proposed。
- 0013 的編號說明；`ADR-0030` 無結果。
- 兩個檔頭錨點都恰好 1 次。

**沒有讀**：`回報格式.md`、ADR-0026／0028／0029 全文、`errors.py`／`band.py`／`missing.py`／`volatility.py`／`ops_alert/model.py` 的內文、產品審視總結、N-140 決策草案。

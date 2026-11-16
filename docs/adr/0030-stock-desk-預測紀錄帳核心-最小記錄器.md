# ADR-0030：stock-desk 預測紀錄帳核心——最小記錄器

- 狀態：accepted（CEO 2026-10-26 核可，含 C-M1～C-M4 與 C-M4、G-5→CG-3 的明確同意；決策包二補遺 #64～#67）
- 補充紀錄：2026-11-14 append 補充一（SP-1：5 張表加 BEFORE INSERT 拒絕重複鍵 trigger；tech-architect 裁示，加嚴，不改產品行為與字面，CEO 可推翻；來源 `work/reviews/2026-11-14-G1位置與SP1裁示-tech-architect.md`）。
- 補充紀錄：2026-11-15 append 補充二（SP-B 輸入注入、SP-C 未定案 bar 分流、快照時間欄與 PIT 缺項名；tech-architect 裁示，釐清，不放寬，不改使用者面字面，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第二批交件-dev-lead.md`）。
- 補充紀錄：2026-11-15 append 補充三（跨 commit 比對基準、執行環境取值時點、K-2 禁詞來源、無定案 bar 與 source_status；tech-architect 裁示，收緊與釐清，不改使用者面字面與已登記雜湊，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第三批recorder交件-dev-lead.md`）。
- 補充紀錄：2026-11-15 append 補充三（修訂版）（跨 commit 比對基準、取值時點、K-2 禁詞來源、取代鏈、原子寫入、例外歸類；tech-architect 裁示，收緊與釐清，不改使用者面字面與已登記雜湊，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第三批recorder交件-dev-lead.md`、`work/reviews/2026-11-15-NM5第三批recorder審查-qa-reviewer.md`）。**補充三（修訂版）取代同日稍早落檔的補充三**：兩者衝突時以修訂版為準；初版依 append-only 原樣保留（tech-architect 回報 `work/reviews/2026-11-15-NM5recorder四題與f1f4裁示-tech-architect.md`）。
- 補充紀錄：2026-11-15 append 補充四（第四批解讀確認、CG-2／CG-3 正式登記的執行方式與檢查點、剩餘順序；tech-architect 裁示，釐清與收緊，不改使用者面字面與已登記雜湊；第 4 點的執行方式須 CEO 同意，其餘 CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第四批解讀與CG2登記方式裁示-tech-architect.md`）。
- 補充紀錄：2026-11-15 append 補充五（第五批解讀確認、失效條件 F-2 的計數視窗、D-8 第 4 點 WARNING、管線驗收的斷言範圍與空轉防護、harness 輸出不含 n̂；tech-architect 裁示，釐清與收緊，沒有放寬，不改使用者面字面與已登記雜湊，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第五批交件-dev-lead.md`、`work/reviews/2026-11-15-NM5第五批五點解讀確認-quant.md`）。
- 補充紀錄：2026-11-15 append 補充五附記（第 3 點 (c) missing code 白名單的唯一定義；tech-architect 裁示，釐清不放寬；來源 `work/reviews/2026-11-15-missing-code白名單裁示-tech-architect.md`）。
- 補充紀錄：2026-11-15 append 補充六（D-7 真實資料那一次：取數方式、注入時間戳、完整輸出不落檔、回貼白名單、失敗後的診斷路徑、通過證據與 CG-2 的綁定、`uv.lock` 換行；tech-architect 裁示，釐清與收緊，不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/` 程式；第 1 點 (b) 與第 4 點 (d) 的讀法待風控確認，確認前一鍵檔不得在 CEO 本機執行；其餘 CEO 可推翻；來源 `work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md`）。
- 補充紀錄：2026-11-16 append 補充六附記（風控 RC-158～RC-165 與 CEO #150 的落實：第 1 點 (b) 的檔案操作限制與適用範圍、複本刪除失敗即停止、失敗種類格式、畫面白名單的機械保證、規則檔位元組綁定、`provisional_results_seen` 在 CG-2 的處理；解除第 8 點限制；tech-architect 裁示，收緊不放寬，不改使用者面字面、規則檔、定義物件與已登記雜湊；來源 `work/reviews/2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md`、`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` #150）。
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
| `app/forecast/store.py` | 只增不改的寫入（時間戳由 store 時鐘填入）；唯讀查詢（D_v、n̂、m_db、記錄中 claim、執行結果） |
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
   - 由查詢導出：`first_record_at` ＝ 該 claim 第一筆 `forecast_record` 的 `created_at`（不論 `late`）；「計入 m」⇔ 該 claim 至少有一筆 `forecast_record`。m_db ＝ 計入 m 的前瞻 claim 數（`store.py` 唯讀查詢導出）；m ＝ max（m_db，D-1 第 2 點 `work/` 登記紀錄中的前瞻 claim 數）。`work/` 紀錄不在帳內，`store.py` 只導出 m_db；驗證層、事先宣告與任何引用 m 之處都以 m 為準，不得只用 m_db。
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
   - F-2 所需的計數，限於最新快照中出現、但沒有 `late = 0` 紀錄的定案 session 數、`inputs_not_ready` 日數、各 `outcome` 的執行次數，以及第 0 相位格點遺失率。這些屬執行狀態，可列於報告；不得與任何標籤或對照並列，也不得依標籤、基準或暫定對照的結果分列。
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
  - `dirdef-v1.0` 登記於 `PUBLISHED_DIRECTION_DEFINITIONS`，含 C-8 的 `f2_variant` 與決策出處；dirdef 凍結的前置條件（決策包補遺知悉 #15、#16）：CEO 選甲案（2026-10-26 明確同意，決策包補遺 #65）。`dirdef-v1.0` 只供大盤 claim 使用；個股、族群 claim 登記前，#16 規章查證須已完成、V14-02 須經 CEO 逐項明示同意，查證有任何一列不是一般漲跌幅限制時 V14-03 重新送風控，個股、族群改用新的定義版本。V14-01 的明示同意移到驗證層 ADR 核可時逐項取得；未明示即視為不同意。不同意時的處理須在 CG-2 之前寫入事先宣告 v0.32，只能是 D-8 第 6 點允許的、不在 dirdef 物件內的更嚴驗證參數，不得改 dirdef 物件或更換 claim；寫不出這樣的處理，就不得選甲案。事先宣告 v0.32 須逐行標明大盤 claim 的記錄與結算不依賴 V14-02、V14-03 或漲跌幅前提；有依賴就不得選甲案。驗證報告揭露：`dirdef-v1.0` 在 #16 查證與 V14-01、V14-02 明示同意之前凍結；V14-01 的同意是在已有暫定對照之後才取得。
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
   - #55（含 55-補 (c)）的前提是缺日「即時首判」。驗證層凡不是在觀察日當時即時首判缺日（含從快照事後判定），驗證層 ADR 都須在新的判定時點下重述 #55 與 55-補 (c) 的代價，送風控確認效果不變；效果有變就重問 CEO。上一子點「條文不變就不必重問」對 #55 不適用；這項重述不因 #55 條文字面不變而免除。
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

---

## 補充一：SP-1 預測帳可被 INSERT OR REPLACE 改寫的收緊（2026-11-14）

- 決策者：tech-architect。來源：`work/reviews/2026-11-14-NM5儲存層交件-dev-lead.md` SP-1（已實證：SQLite 預設 `recursive_triggers=OFF` 時，REPLACE 刪除舊列不觸發 BEFORE DELETE trigger，`label` 被改寫）。
- 性質：收緊 D-2 第 6 點與 S-1。補充本文，不改本文；不改任何產品行為與字面，不擴大 CEO 核可範圍。CEO 可推翻。

1. 5 張表各加一個 trigger `{table}_no_replace`：`BEFORE INSERT`，`WHEN EXISTS` 同表中已有任一鍵相同的列，`SELECT RAISE(ABORT, 'append-only')`。須比對的鍵：
   - `forecast_run`：`run_id`；
   - `forecast_run_end`：`run_id`；
   - `forecast_input_series`：`series_id`、`content_sha256`；
   - `forecast_claim_registry`：`rowid`、`claim_id`；
   - `forecast_record`：`rowid`、`forecast_id`、(`claim_id`, `data_as_of`)。
   `WHEN` 子句只比對上列的鍵，不得有其他條件。
2. D-2 第 6 點的 UPDATE／DELETE trigger 不變，仍然沒有 `WHEN`、沒有例外。store 連線維持 `recursive_triggers=ON`，作為第二層防護。
3. `schema_status` 的預期物件含這 5 個 trigger（合計 15 個 trigger）；少一個、內容被改或多一個，都判為不完整，store 拒絕寫入。
4. 本補充必須在 CG-3 正式建表之前落地。正式主 DB 一旦建表，再加這些 trigger 就是遷移，依 K-12 禁止。
5. 未明確指定 rowid 時，SQLite 文件記載 `NEW.rowid` 的值為 undefined。在 D-5 第 6 點鎖定的執行環境下，它若誤中既有列，結果是拒絕寫入（fail-closed），不會放行。
6. 殘留風險（知悉，不處理）：其他程式仍可以 `DROP TRIGGER`、開 `writable_schema` 或直接改檔。`schema_status` 只偵測得到少了或被改過的物件；`report verify` 偵測得到 D-5 第 3 點涵蓋的欄位；但刪掉 trigger 再改寫 `created_at`／`late`，帳內無法偵測。依 ADR-0025 F-1（純自用、單一使用者），蓄意竄改不在威脅模型內。F-4 不變。

- **S-1a（逐條可檢查）**：在預設連線（`recursive_triggers=OFF`）上，第 1 點列出的 9 條鍵路徑各自執行 `INSERT OR REPLACE`，都以 `append-only` 被拒絕，而且原列內容與總列數都不變；store 的正常寫入全部通過（測試）。`sqlite_master` 中恰好有 15 個 ledger trigger（`schema_status`）。

---

## 補充二：大盤輸入的取得方式、未定案 bar 的分流、快照時間欄（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-NM5第二批交件-dev-lead.md` SP-B、SP-C 與待確認事項（已實證：`app.services.index` 在模組層級 import `PriceService`，使 import 它的模組可達 `app.portfolio`、`app.positions`）。
- 性質：釐清 D-1 第 3 點 inputs 列、D-3 第 1～2 點、D-5 第 1 點的讀法。補充本文，不改本文；不放寬 K-2、K-3、K-10、S-4、S-6；不改任何使用者面字面。CEO 可推翻。

1. **取得方式**：正式路徑的大盤輸入，是 `app.services.index.load_market_benchmark` 的回傳值。`app.scheduler` 註冊 job `forecast_record` 時，把這個函式以參數傳入 recorder 的進入點。`app/forecast/**`、`app/outlook/**` 不 import `app.services.index`；`app/outlook/inputs.py` 只依 Protocol 接收回傳值。D-1 第 3 點的「只經 `app.services.index` 取得」以此讀。K-2 依可達性（含遞移 import）判定，不變。這個參數是取數函式，不是 T、`as_of` 或時鐘，K-10 不變；以其他取數函式呼叫 recorder，只限 tests 與 D-7 harness（K-11 不變）。`late` 仍由 store 時鐘判定，所以注入過去的資料只會得到 `late = 1`，或被 UNIQUE 拒絕。
2. **未定案 bar 的分流**：以 store 時鐘讀取執行時刻 now。對每一根未定案 bar（session 日 S）：
   (a) now 不早於 S 日 `TW_POLICY.publish_cutoff`：屬 D-3 第 2 點。recorder 重新呼叫取數函式一次；之後仍有任何一根屬 (a)，就記 `inputs_not_ready`（`candidate_t` 填其中最大的 S），不寫紀錄，也不改用更早的定案 bar 當 T。
   (b) now 早於 S 日 `TW_POLICY.publish_cutoff`：該 session 還不到可以定案的時點，屬 LA-G2-5。這根 bar 不進快照，列入 `dropped_rows_json`；T 為最新一根定案 bar，照常寫紀錄。
3. **快照時間欄**：這條取數路徑上每根 bar 只有一個取回時間，快照的 `fetched_at` 取 `PriceBar.as_of`，`raw_timestamp_available = false`；D-3 第 2 點的「取較早者」因此等於 `as_of`。資料源或取數路徑更換時，依 F-5 重審本點。
4. **PIT 缺項名**：`E-PIT-UNVERIFIED` 的 `item` 為 `inputs_max_fetched_at`，只定義一次。

- **S-4a（逐條可檢查）**：可達性測試不變且全綠；正式路徑上 recorder 進入點只由 `app/scheduler.py` 呼叫，而且傳入的物件就是 `app.services.index.load_market_benchmark`（AST 加 `is` 斷言）；(a) 情形重抓一次後記 `inputs_not_ready`、不寫紀錄；(b) 情形的 `content_hash` 與取數端不回傳該 bar 時相同；快照中每根 bar 都是 `fetched_at == as_of`（測試）。

---

## 補充三：跨 commit 比對基準、執行環境取值時點、K-2 禁詞來源、無定案 bar 與 source_status（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-NM5第三批recorder交件-dev-lead.md` 下一步第 1～4 點（已實證：`app/advice/loader.py:44` → `app/advice/context.py:29` → `app/advice/limits.py:54` → `app.api.kelly_wording`）。
- 性質：收緊 D-5 第 6 點與 K-2；釐清 D-2 第 1～2 點與補充二第 2 點。補充本文，不改本文；不改任何產品行為、使用者面字面、規則檔與定義物件的雜湊。取代 ADR-0027 N113-1「代價」段所述的可達狀態。CEO 可推翻。

1. **比對基準**：D-5 第 6 點的「前一次執行」，讀為以下兩者：(i) run_id 小於本次的最近一次執行；(ii) 最後一次通過執行，即 outcome ∈ {`ok`, `no_new_session`, `inputs_not_ready`} 的執行。本次的 `code_digest` 或 `runtime_json` 與 (i)、(ii) 任一不同，就執行 D-5 第 6 點。沒有通過執行時，視為不同。`gate_closed`、`error` 與沒有 end 列的執行，都不是通過執行。
2. **取值時點**：`code_digest`、`runtime_json`、`code_commit` 在 recorder 模組 import 時取值一次，同一程序內的各次執行都沿用這組值。D-2 第 1 點 `code_digest` 涵蓋範圍內的原始檔，不得在函式內 import，也不得使用 `importlib` 或 `__import__`。更換程式或依賴之後，須重啟排程程序才會生效；重啟前寫入的紀錄出自舊程式，記錄的也是舊值，出處一致。殘留風險（知悉，不處理）：import 讀檔與取值之間的極短窗口。
3. **K-2 禁詞來源**：K-2 依可達性判定，`app.forecast.*`、`app.outlook.*` 不得可達 `app.api` 及其子模組。`BANNED_PHRASES` 的唯一定義移到 `app/advice/banned_phrases.py`，該模組不 import 任何模組。`app/advice/loader.py` 以 `from app.advice.banned_phrases import BANNED_PHRASES as BANNED_PHRASES` 再匯出，所以 ADR-0004、ADR-0022、ADR-0025 所稱的 `loader.BANNED_PHRASES` 仍指同一個物件。`app/forecast/definitions.py` 改由 `app.advice.banned_phrases` import。禁詞的值與順序不變；`app/advice/__init__.py` 不含 import。從 `app.forecast`、`app.outlook` 可達的 `app.advice` 模組，恰好是 `app.advice` 與 `app.advice.banned_phrases`。
4. **沒有定案 bar**：補充二第 2 點 (a) 先適用。處理之後，沒有任何定案 bar，也沒有屬 (a) 的 bar 時（含取數端沒有回傳任何 bar），記 `inputs_not_ready`，`candidate_t` 為 null，不寫紀錄，並計入 F-2 的 `inputs_not_ready` 日數。
5. **`source_status`**：照實記錄於 `forecast_input_series`，不設拒收規則。PIT 與定案的保證來自 D-3 第 2 點的逐根判定與 store 時鐘。`source_status` 不得作為 recorder 或 `app/outlook/**` 的分支條件，也不影響 T、`label`、`band_def`、`baseline_predictions_json`、`missing_json`。ADR-0005 下大盤來源恆為 backup，所以不得以「非 backup」或「非 fresh」作為拒收條件；要設拒收規則，須另修本 ADR。

- **S-12a（逐條可檢查）**：
  - 依序執行 A ok → B gate_closed → B，第三次仍記 `gate_closed`；之後改回 A，會重算並通過；沒有通過執行時會重算（測試）。
  - 第 2 點所列範圍內，函式內沒有 import，也沒有 `importlib`／`__import__`（AST）；程序未重啟時，磁碟變更不改變記錄的 `code_digest`（測試）。
  - 可達集合與 `app.api*` 沒有交集，可達的 advice 模組恰好如第 3 點（import graph）；`loader.BANNED_PHRASES is banned_phrases.BANNED_PHRASES`；h3、h5 的 `rules_sha256`、`rules_logic_sha256` 與 `definition_sha256` 不變（測試）。
  - 只有 (a) bar 時，`candidate_t` 等於最大的 S；沒有任何 bar 時，`candidate_t` 為 null（測試）。
  - 同一組 bars 分別配上 4 種 `DataStatus`，第 5 點所列欄位都逐位相同（測試）。

---

## 補充三（修訂版）：跨 commit 比對基準、取值時點、K-2 禁詞來源、取代鏈、原子寫入、例外歸類（2026-11-15）

- 決策者：tech-architect。來源：dev-lead 第三批交件「下一步」第 1～4 點；qa 第三批審查 f1～f5。已實證的路徑：`app/advice/loader.py:44` → `context.py:29` → `limits.py:54` → `app.api.kelly_wording`。
- 性質：本補充收緊 D-5 第 6 點、D-6 CG-2、K-2、D-4 第 1 點；釐清 D-2 第 1～2 點與補充二第 2 點。補充本文，不改本文；不改使用者面字面，也不改規則檔與定義物件的雜湊。本補充取代 ADR-0027 N113-1「代價」段所述的可達狀態。CEO 可推翻。

1. **比對基準**：D-5 第 6 點的「前一次執行」讀為下列兩者：
   - (i) run_id 小於本次的最近一次執行；
   - (ii) 最後一次通過執行，即 outcome ∈ {`ok`, `no_new_session`, `inputs_not_ready`} 的執行。
   本次的 `code_digest` 或 `runtime_json` 與 (i)、(ii) 任一不同，就執行 D-5 第 6 點。沒有通過執行時，視為不同。`gate_closed`、`error`，以及沒有 end 列的執行，都不算通過執行。
2. **取值時點**：
   - `code_digest`、`runtime_json`、`code_commit` 在 recorder 模組 import 時取值一次，同一程序內的各次執行都沿用。
   - `code_digest` 涵蓋的原始檔，不得在函式內 import，也不得使用 `importlib`、`__import__`。`app/scheduler.py` 在模組層級 import recorder。
   - 每次執行都重算一次磁碟上的 digest。與取值時不同時，記一行 WARNING，不含標籤，照常執行。
   - 更換程式或依賴之後，須重啟排程程序才生效。
3. **K-2 禁詞來源**：
   - K-2 依可達性判定：`app.forecast.*`、`app.outlook.*` 不得可達 `app.api` 及其子模組。
   - `BANNED_PHRASES` 的唯一定義移到 `app/advice/banned_phrases.py`，該模組不 import 任何模組。
   - `app/advice/loader.py` 以 `from app.advice.banned_phrases import BANNED_PHRASES as BANNED_PHRASES` 再匯出；`app/forecast/definitions.py` 改由 `app.advice.banned_phrases` import。
   - 禁詞的值與順序不變。`app/advice/__init__.py` 不含 import。
   - 從上述兩個套件可達的 `app.advice` 模組，恰好是 `app.advice` 與 `app.advice.banned_phrases`。
4. **沒有定案 bar**：補充二第 2 點 (a) 優先適用。處理後若沒有任何定案 bar，也沒有屬 (a) 的 bar，就記 `inputs_not_ready`，`candidate_t` 為 null，不寫紀錄，並計入 F-2。
5. **`source_status`**：照實記錄，不設拒收規則。它不得作為 recorder 或 `app/outlook/**` 的分支條件，也不影響 T、`label`、`band_def`、`baseline_predictions_json`、`missing_json`。要設拒收規則，須修訂本 ADR。
6. **取代鏈**：
   - `replaces_claim_id` 必須指向登記較早、`(scope_kind, scope_key, horizon)` 相同的前瞻 claim；每個 claim 至多被取代一次。
   - 登記 CLI 拒收不合上述條件者；recorder 的 CG-2 核對同樣的條件。
   - 本點須在第一次 CG-2 登記之前落地。
7. **原子寫入**：同一次執行的 `put_input_series` 與全部 `write_record` 放在同一個交易內。任一筆失敗就全部回滾，`records_written` 記 0。INSERT 仍只在 `store.py`（K-4）。
8. **重算失敗的歸類**：
   - 讀取或解析既有紀錄、快照失敗，記 `error`，`error_class` 照例外類別。
   - 目前程式重算失敗，或重算值驗證不過，記 `gate_closed`，`error_class=SemanticsChanged`。
9. **唯讀連線**：store 的唯讀查詢一律經 `_read()`（`query_only`）。

- **S-12a（逐條可檢查）**：
  - 第 1 點：序列 A ok → B gate_closed → B，第三次仍記 `gate_closed`；改回 A 後會重算並通過；沒有通過執行時會重算（測試）。
  - 第 2 點：AST 確認禁用的 import 形式不存在、scheduler 在模組層級 import recorder；有測試確認 digest 不同時只記 WARNING。
  - 第 3 點：可達集合與 `app.api*` 沒有交集（import graph）；`loader.BANNED_PHRASES is banned_phrases.BANNED_PHRASES`；h3、h5 的三種雜湊都不變（測試）。
  - 第 4 點：只有 (a) bar 時，`candidate_t` 等於最大的 S；沒有任何 bar 時，`candidate_t` 為 null（測試）。
  - 第 5 點：同一組 bars 分別配上 4 種 `DataStatus`，第 5 點所列欄位都逐位相同（測試）。
  - 第 6 點：三個反例（跨 horizon、取代兩次、指向較晚的 claim）都被拒收（測試）。
  - 第 7 點：注入第二筆失敗時，ledger 列數為 0（測試）。
  - 第 8 點：兩類失敗各有一個測試，outcome 不同。
  - 第 9 點：`_connect()` 只出現在寫入路徑（AST）。

---

## 補充四：第四批解讀確認、正式登記（CG-2／CG-3）的執行方式、剩餘順序（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-NM5第四批交件-dev-lead.md` 下一步第 1、3 點。
- 性質：釐清補充三（修訂版）第 2、5、8 點與 D-6 CG-2、CG-3；收緊正式路徑的寫入條件。不改使用者面字面，不改規則檔與定義物件的雜湊。CEO 可推翻；第 4 點的執行方式須 CEO 同意。

1. **解讀確認**
   - (a) 補充三（修訂版）第 5 點的禁令，對象是快照的 `source_status`。`app/outlook/missing.py` 中 `MissingItem` 類別內的 `self.source_status`（D-13 缺項欄位）不在禁令內；豁免只限這個模組的這個類別。
   - (b) 第 8 點的「目前程式重算失敗」，涵蓋純計算呼叫拋出的任何 `Exception`。`try` 不得包住帳本讀取與解析，也不捕捉 `BaseException`。
   - (c) 第 2 點的磁碟重算涵蓋 `code_digest` 與 `runtime_json`，可以在接線 PR 之前落地；scheduler 的 AST 檢查仍在接線 PR 套用。
   - (d) ADR-0027 D-10 第 3 點（含 N-84 暫行限制）屬 D-8 凍結附錄，不實作。FL-78 (i) 的禁詞來源讀為 `app.advice.banned_phrases`。第一次登記早於任何 `forecast_run`，由第 2 點保證。日後依 D-1 第 2 點修訂本 ADR 以取代 claim 時，須一併定新 claim 缺日義務的起點。
2. **正式路徑**
   - 正式主 DB 唯一的登記路徑是 `python -m app.forecast.claims bootstrap --production`。`register` 對正式路徑維持一律拒絕。
   - `bootstrap` 須同時成立以下條件，任一不成立就以結束碼 4 拒絕，不寫入：
     - 目標是 `<backend>/data/stock-desk.db`；
     - 環境變數與 `apps/stock-desk/.env` 都沒有設 `STOCK_DESK_DB_PATH`；
     - 主 DB 沒有任何 `forecast_`、`plan_` 開頭的表；
     - 一次給齊 D-1 第 1 點的 h3、h5 兩個 claim，依此順序；
     - `replaces_claim_id` 為空。
   - schema 的全部物件與兩列登記放在同一個寫入交易內，任一步失敗就全部回滾。提交後以唯讀連線確認：`schema_status` 完整、登記表恰好 2 列、`forecast_run` 為 0 列。
   - 正式主 DB 上的核心 schema 只能由 `bootstrap` 建立。其他路徑遇到 schema 不存在時拒絕寫入，不建表。
   - 登記表非空之後，正式路徑沒有任何登記方式。
3. **`prereg_doc_path`**
   - 格式：repo 根目錄起算的相對路徑，以 `/` 分隔；不得含 `./`、`..`、`\`、磁碟代號，也不得是絕對路徑。不合格就拒絕，不自動轉換。`review_refs` 用同一格式。
   - `prereg_doc_blob` 是該路徑在 `frozen_commit` 的 git blob 原始位元組。CLI 須核對 `--prereg-doc-sha256`，不一致就拒絕。
4. **執行者與順序**
   - (1) CG-2 登記 PR 合併。
   - (2) CEO 在本機先執行只讀的預檢檔，回傳結果經 coordinator 核對後，再執行登記檔。登記檔重跑全部預檢，然後依序：
     - 以 SQLite backup API 取得主 DB 一致備份：放在 git 工作樹之外，`integrity_check` 為 ok，記下 sha256；
     - 禁詞比對；
     - `bootstrap`；
     - 輸出回傳內容。

     任一步不成立就停止。回傳內容只含固定文字、計數、雜湊、commit 與時間，不含路徑與代號。一鍵檔不開寫入連線。
   - (3) coordinator 當日以 commit 在 `work/` 記錄 `claim_id`、`registered_at`、`frozen_commit` 與備份 sha256。
   - (4) 接線 PR 在 (3) 之後才合併，記下 CG-3 備份路徑（以家目錄相對寫法）與 sha256。
5. **檢查點**
   - 合併前：
     - M-1：第四、五批已 qa PASS 並合併；D-7 harness 已執行。
     - M-2：事先宣告 v0.32 的路徑、blob id、`git cat-file blob <commit>:<path>` 的 sha256 都寫進 PR；RC-153～RC-157 套用之後，此檔沒有任何變更。
     - M-3：C-8 紀錄檔依 RC-152 第 1 點計算，PR 寫出指令與 commit SHA；風控確認之後沒有任何變更。dirdef-v1.0 的 C-8 雜湊欄等於此值。
     - M-4：`dirdef-v1.0` 登記於 `PUBLISHED_DIRECTION_DEFINITIONS`；兩個 definition 雜湊寫進 PR，並以測試釘住。
     - M-5：h3、h5 登記於 `PUBLISHED_RULESETS`，`OUTLOOK_RULE_FIELDS` 已設定；四個規則雜湊以測試釘住。
     - M-6：禁詞比對輸出附在 PR，命中 0。
     - M-7：YAML 與 M-2、M-3 兩份文件加上 `eol=lf` 屬性，PR 附上 `git ls-files --eol` 的輸出。
     - M-8：一鍵檔以常數固定 M-2～M-5 的雜湊；測試涵蓋第 2 點每個拒絕條件、整筆回滾，以及回傳內容不含路徑。
     - M-9：qa PASS（含 Codex）；風控核對 M-2、M-3、M-6；CI 綠燈；`report verify --all` 一致。
   - 登記前（一鍵檔機械核對，任一不成立就停止）：
     - R-1：`HEAD` 可由 `origin/product/stock-desk` 到達；`HEAD` 與 CG-2 合併 commit 之間，`app/` 與兩份文件沒有 diff，且這些路徑的工作樹乾淨。`frozen_commit` 取 `HEAD`。
     - R-2：每個凍結檔的工作樹 sha256 等於 blob 的 sha256，也等於 M-8 的常數。
     - R-3：port 8000 沒有監聽；沒有設 `STOCK_DESK_DB_PATH`；主 DB 存在於預設位置。
     - R-4：主 DB 沒有 `forecast_`、`plan_` 開頭的表。
     - R-5：備份的 `integrity_check` 為 ok，備份內沒有 `forecast_` 表。
     - R-6：禁詞比對命中 0。
     - R-7：`bootstrap` 結束碼 0，提交後的核對成立。
     - R-8：`provisional_results_seen` 由 CEO 鍵入。
6. **剩餘順序**
   - 第五批 `report.py`＋D-7 harness（同一批）→ CG-2 登記 PR（含 CLI 正式路徑、一鍵檔、登記值）→ 第 4 點 (2)、(3) → 接線 PR。
   - CG-2 登記不得早於 harness 通過。接線 PR 不得與 CG-2 PR 合併。

- **S-14a（逐條可檢查）**：第 1 點各款各有 AST 或測試；第 2、3 點每個拒絕條件各一個測試；整筆回滾測試；M-1～M-9 列在 CG-2 PR 說明中；R-1～R-8 各有對應的 STOP 訊息測試；接線 PR 合併時，`work/` 中已有登記紀錄的 commit。

---

## 補充五：第五批解讀確認、F-2 計數視窗、D-8 第 4 點 WARNING、管線驗收的空轉防護（2026-11-15）

- 決策者：tech-architect。來源：dev-lead 第五批交件「已知限制與解讀」五點；quant 第五批五點解讀確認第 1、3、4 點。另讀 `feat/nm5-forecast-storage`（518046f9）的 `tests/forecast_pipeline_harness.py`：`run_acceptance` 的輸出含 `report.render_status`，該段列出 n̂（第 5 點）。
- 性質：釐清失效條件 F-2、D-7 第 4 點與 D-8 第 4 點的讀法；收緊 F-2 的計數，以及 D-4 第 5 點在 harness 輸出上的適用。補充本文，不改本文；沒有放寬；不改使用者面字面，也不改規則檔、定義物件與已登記雜湊。CEO 可推翻。

1. **F-2 的計數視窗**：只適用 F-2 第一句；第二句的第 0 相位格點遺失率自 D_v 起累計，不受本點影響。報告標題寫「ADR-0030 失效條件 F-2」，與事先宣告的下架規則 F-2 區分。
   - (a) 平日與日期：平日指週一至週五，不扣休市日，與 D-8 第 4 點 T2 使用同一個函式。日期一律以 Asia/Taipei 計。平日 D 要等 D 的 `late_cutoff_at` 已過，才進入視窗，所以當天不計入。
   - (b) 起點：claim c 的起點 S_c ＝ max（c 的 `registered_at` 日期，第一筆 `forecast_run` 的 `started_at` 日期）。不以 D_v 為起點。
   - (c) 視窗與滾動：
     - S_c 以後每連續 20 個平日為一個視窗，逐平日滾動。
     - 視窗的日曆範圍是它的第一個到最後一個平日，含其間的週末。
     - 逐一評估 S_c 以來每一個完整的視窗，任一視窗成立，F-2 就成立；之後的視窗不成立，也不撤銷。
   - (d) 分子：每個 claim 各自計算，等於下列兩項照字面相加，重複的部分不扣除。
     - 視窗日曆範圍內的定案 session 中，該 claim 沒有 `late = 0` 紀錄的 session 數。定案 session 取至今全部快照中定案 session 的聯集，與 n̂ 用同一個查詢。這個集合包含最新快照中的 session，所以不寬於字面。
     - 視窗日曆範圍內，有任一次執行 outcome 為 `inputs_not_ready` 的日數，以 `started_at` 的日期計。同一天多次只算一天；同一天另有 `ok`，也照樣計入。
   - (e) 分母與門檻：分母 ＝ min（20，視窗日曆範圍內的定案 session 數）。分子大於分母的 30% 就成立。分母不會大於 20，所以不寬於「固定 20」的字面讀法；休市日多的視窗會比較嚴。
   - (f) 視窗未滿：S_c 以來不足 20 個平日時，分子大於 6 就成立；否則標示「視窗未滿」。
   - (g) 導出與輸出：
     - 計數與是否成立，只由 `store.py` 的唯讀查詢導出。
     - `report status` 每次輸出：最近一個完整視窗的起迄日、兩項分子、分母、是否成立，以及「自起點以來曾否成立」。
     - 這些屬 D-4 第 5 點的執行狀態：可以依 claim 分列；不得與標籤或對照並列，也不得依標籤、基準或暫定對照分列。
   - (h) 已知盲點（知悉，不處理）：主機整段停機時沒有新快照，停機期間的 session 要等下一次執行的快照出現，才進入分子；停機中執行 `report`，F-2 會偏低。停機的偵測由 devops-sre 的心跳負責（D-10）。
   - 期限：在接線 PR 落地，列為 CG-4 的阻擋項。
2. **D-8 第 4 點的 WARNING**
   - 讀法：「首次成立時 recorder 記 WARNING」讀為「T1 或 T2 成立期間，recorder 每次執行各記一次」，因此涵蓋首次。recorder 不保存「已記過」的狀態，也不新增欄位或表。
   - 內容：每個成立的 claim 記一行，只含固定的英文字面、`claim_id`，以及成立的是 T1、T2 或兩者。不含 n̂、c₁、d₁、D_v、任何計數或日期，也不含標籤。
   - 判定方式：
     - 經 `store.py` 的唯讀查詢判定，「今天」取 store 時鐘的台北日期，在 `forecast_run_end` 寫入之後進行。
     - 判定不得改變 outcome、`records_written`、`error_class` 或任何紀錄。
     - 判定拋出 `Exception` 時，改記一行固定字面的 WARNING，照常結束；不捕捉 `BaseException`。
     - 沒有 D_v 時，T1、T2 都不成立，不記。
   - 期限：在接線 PR 落地，列為 CG-4 的阻擋項。
3. **D-7 第 4 點的斷言範圍與空轉防護**
   - 讀法：「harness 斷言每一筆的模型標籤與對應基準逐筆相同」讀為「每一筆不是 `insufficient` 的紀錄都相同」。
     - 理由：engine 的第 (0) 步排在規則之前（D-3 第 6 點），所以 insufficient 紀錄在字面上不可能等於 B6。這類紀錄依同點後句，以合成 fixture 驗證。
     - D-7 第 1、6 點不變：harness 仍不得宣稱真實時序已驗證。
   - 為免斷言空轉，harness 另加三項，任一不成立就判失敗：
     - (a) P-0、P-1 各自的 h3、h5 claim，都至少有 1 筆非 insufficient 紀錄，而且其中至少 1 筆的暫定對照有結果（不是「無法對照」）。不成立時，失敗種類為 `vacuous_equality`。
     - (b) 模型不是 insufficient、對應基準卻是 `unavailable` 時，判失敗，不跳過。
     - (c) insufficient 紀錄的 missing code 只能是凍結包 §2.5 表內的四類；`missing` 非空 ⇔ `label = insufficient`。
   - 三項都只輸出通過或失敗，以及失敗種類，不輸出筆數。
   - 期限：在真實資料一鍵檔執行之前落地。缺少時，真實資料的 harness 不算通過，依補充四第 6 點也不得進行 CG-2 登記。
4. **暫定對照的實現標籤**：依事先宣告 §2.1，用紀錄自己的 `K_h`、`EPS`、`sigma_d`，以 `app.outlook.volatility.log_return` 與 `app.outlook.baselines.threshold_label` 計算，不另寫（K-6）。不套用 `f2_variant`：C-8 是驗證層的下架規則，隨 D-8 凍結。
5. **harness 輸出中的 n̂**
   - D-4 第 5 點對 n̂ 的唯一例外，只限操作者報告（`report` CLI）。
   - 管線驗收 harness 的輸出，包括只寫進暫存檔的完整輸出與 `render_summary`，都不得含 n̂、T1／T2 的判定列，或 n̂ 的固定標示。F-2 計數與各 outcome 的次數屬執行狀態，可以列。
   - `render_summary` 不得列非 insufficient 的筆數、可對照的筆數，或任何與符合與否有關的計數。
   - 期限：在第五批合併前落地。

- **S-10a、S-13a（逐條可檢查）**：
  - 第 1 點：
    - 以合成帳的測試涵蓋：起點早於第一筆 `forecast_run` 時，那段期間不計入；同一天兩次 `inputs_not_ready` 只算一天；一個 session 未定案且一直沒有紀錄時計入 2；休市日多的視窗以 min（20，s）為分母；只有較早的視窗成立時，「曾否成立」仍為成立；視窗未滿的兩種情形；當天不計入。
    - 平日函式與 T2 相同（AST 或 import）；F-2 計數只在 `store.py` 導出（grep）。
  - 第 2 點：以下四種情形各有測試，outcome 與 `content_hash` 都不變，log 行符合固定格式：不成立時不記；只有 T1；T1 與 T2 同時成立；判定拋出例外時記固定字面的 WARNING。
  - 第 3 點：(a)～(c) 各有一個會判失敗的反例 fixture，例如全部紀錄都是 insufficient 時判 `vacuous_equality`。
  - 第 5 點：harness 的完整輸出與 `render_summary` 都不含「n̂」與 n̂ 的固定標示；`report status` 照常列出 n̂（測試）。

---

## 補充五附記：第 3 點 (c) 的 missing code 白名單（2026-11-15）

- 決策者：tech-architect。條文由 coordinator 依 TA 報告整理；第 2 行為 TA 指定的解讀原文。性質：釐清補充五第 3 點 (c)，不改本文、不放寬。
- 四類＝§2.5 四列、五個 code；唯一定義為 `app.outlook.engine.MISSING_CODES`。
- `MISSING_CODES` 放 `engine.py`、不放 `outlook/missing.py`（`MissingItem.code` 也承載 §2.5 以外的 code，例如 `E-ADJ-COVERAGE`）。harness 引用它，不在 `tests/` 另列成員。
- 它使 `code_digest` 改變，必須在 CG-2 PR 合併前落地；對補充三（修訂版）比對基準、補充四 M-2～M-5 與 CG-2 登記沒有影響。

---

## 補充六：D-7 真實資料那一次的取數、時間戳、回貼內容、診斷路徑與通過證據（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md` T-1～T-7；CEO #149（`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`）。另讀 head `9f45cb2e` 的 `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`app/forecast/canonical.py`、`app/forecast/recorder.py`、`app/data/cache.py`、`app/dirdef/registry.py`。
- 性質：釐清 D-7 第 2、5、6 點、K-11、補充四第 5 點 M-1 與第 6 點、補充五第 3、5 點的讀法；收緊管線驗收輸出的可見範圍與「harness 通過」的效力。補充本文，不改本文；不改使用者面字面、規則檔、定義物件與已登記雜湊；不改 `app/` 任何程式。第 1 點 (b) 與第 4 點 (d) 的讀法送風控確認（Q-1、Q-2），確認前一鍵檔不得在 CEO 本機執行；其餘 CEO 可推翻。

1. **取數**
   - (a) 真實資料那一次的取數由 `scripts/` 內的外層包裝執行：
     - 以位元組複製主 DB 的 `stock-desk.db` 與存在的 `-wal`、`-shm`，複製前後逐檔比對 sha256；
     - 只對複本開 `sqlite3` URI `mode=ro` 連線並設 `query_only`，只 SELECT `price_bars_cache` 中 `symbol = '^TWII'`、`market = 'TW'` 的 `trade_date, open, high, low, close, volume, currency, source`；
     - 轉成 `PriceBar` 後立即刪除複本，再以 `bars` 參數交給 `run_acceptance`。harness 本體不變。
   - (b) 讀法：D-7 第 2 點與 K-11 的「遇到正式主 DB 路徑就拒絕」，對象是 harness 的 ledger 與任何 SQLite 連線的目標。為取得 D-7 第 6 點「目前快取中的值」而以 `open(..., "rb")` 讀主 DB 位元組做複製與雜湊，不在拒絕範圍內。主 DB 不得被任何 SQLite 連線開啟，含唯讀連線與 backup API。（Q-1）
   - (c) 包裝不得 import `app.services`、`app.data.cache`、`app.data.service`、`app.data.providers`；不得有網路呼叫；不得寫入主 DB、複本或任何 `price_bars_cache`。
   - (d) 列到 `PriceBar` 的對應，除 `as_of` 外與 `PriceBarCache` 讀取方法的結果逐欄相同。任一列無法解析就停止，不略過。
   - (e) 以下任一成立就停止，只印固定句，不印任何值或根數：沒有列；任一列無法解析；任一列 `source` 以 `demo` 開頭；任一列 `source` 不是 `yfinance`（F-5 的訊號，由 coordinator 升級 tech-architect）；執行日前的 session 數少於 N_SNAPSHOT 加 `WINDOW_SESSIONS`，兩者都取自程式常數或導出函式。

2. **時間戳**
   - 每根 bar 的 `as_of` 取該 session 當日 20:00 Asia/Taipei，與 `synthetic_series` 的預設相同；快照的 `fetched_at` 依補充二第 3 點等於 `as_of`。不讀快取的 `as_of`、`fetched_at`。answer 的 `reason` 為 `synthetic_timestamps`。
   - 因此，快取中曾在 15:00 前取得、其後未被覆寫的 bar，在 harness 中視為定案。這屬 D-7 第 6 點的限制。任何文件、回貼或報告不得宣稱這一次驗證了真實時序下的 PIT、定案或 `late`。

3. **完整輸出與暫存帳**
   - 補充五第 5 點的「只寫進暫存檔的完整輸出」讀為允許，不是要求。真實資料那一次，`AcceptanceResult.output` 不寫入任何檔案、主控台或 log。包裝對 `AcceptanceResult` 只讀 `passed`，另外呼叫 `render_summary`，不存取其他屬性。
   - 暫存帳在 `finally` 刪除，含 `-wal`、`-shm`、`-journal`；下次啟動先掃除殘留，只掃包裝自己建立、名稱符合格式的子資料夾。全程停用 logging；例外只印固定句，不印例外文字與 traceback。
   - 回貼為 `cleanup=FAILED` 時，操作說明須告知 CEO 不得開啟該資料夾；CG-2 登記前須再執行一次，取得 `cleanup=ok`。

4. **回貼內容**
   - (a) 回貼檔與主控台只輸出白名單行，逐行 fullmatch 固定樣式，其餘丟棄並計入 `summary_lines_dropped`。白名單恰好是：
     - D-7 第 5 點的兩行固定標示；
     - 版本行、`script_sha256_lf`、`harness_sha256_lf`、`git_head`、`git_clean=yes`、`core_autocrlf`、`eol_check=ok`、`code_digest`、`lockfile_sha256`、`definition_sha256`、`definition_logic_sha256`；
     - `db_location=default`、`port_8000_listening=no`、三行 `copy_check`、`refusal_guard=ok`、`cache_depth=sufficient`、`bars_sources`、`bars_sha256`；
     - 每個規則集一組：`render_summary` 的通過或失敗行、執行次數行、失敗種類行、暫存帳 sha256 行、輸出 sha256 行；
     - `acceptance_result`、`cleanup`、`summary_lines_dropped`、`done_at_utc`。
   - (b) 不輸出：
     - `Failure.where`，包括 `vacuous_equality` 的規則集與 horizon；
     - 例外文字、路徑、根數，以及任何筆數或比例。
     - `render_summary` 的「視窗定案 session 數」行明列為已知不輸出，不計入 `summary_lines_dropped`。
   - (c) `bars_sha256` 在呼叫 `run_acceptance` 之前，以 `app.forecast.canonical.content_sha256` 對注入後的整條序列計算，不另寫序列化（K-6）。兩個規則集共用一個值，只輸出一次。`bars_sources` 是封閉集，依第 1 點 (e) 恆為 `yfinance`。兩者都是輸入識別，與規則及 harness 判定無關。
   - (d) 讀法：CEO #149 所稱不得給 CEO 看、也不得經 coordinator 轉述的「結果」，指模型與基準的標籤、暫定對照（含實現標籤與符合與否），以及與它們相關的任何筆數或比例。管線是否通過、失敗種類、各 `outcome` 的執行次數、雜湊與環境檢查，屬 D-4 第 5 點的執行狀態；補充四第 6 點與補充五第 3 點須以它們判定 harness 是否通過，所以可以由 CEO 回貼、經 coordinator 轉交。依此讀法，回貼不構成 D-1 第 2 點「看過暫定對照」，補充四 R-8 填 0 不受影響。（Q-2）

5. **失敗後的診斷**
   - (a) 回貼與任何轉述只到失敗種類為止。
   - (b) 第一步：dev-lead 在隔離 worktree 以合成 fixture 重現該失敗種類，修正後加回歸測試，CEO 在新 head 重跑一鍵檔。
   - (c) 第二步，限合成重現不了時：dev-lead 或 qa-automation 在隔離 worktree 的 `tmp_path`，自行從公開來源取得 `^TWII`，依第 1 點 (d) 與第 2 點的同一規則注入後執行 harness，並以 `bars_sha256` 確認輸入與 CEO 那一次相同。完整輸出與暫存帳只留在該 `tmp_path`，不 commit，不交給 quant、風控、coordinator 或 CEO。
   - (d) dev-lead 與 qa 對 coordinator 的回報（coordinator 逐字轉存）只寫失敗種類、程式層面的原因、修正 commit 與回歸測試名稱。不得含模型、基準或實現標籤，不得含符合與否、T 或任何 session 日期、`claim_id`、任何筆數或比例，也不得含完整輸出的任一行。
   - (e) 兩步都無法定位時，升級 tech-architect。未另修本 ADR 並經風控審查前，不得放行 `where`，不得把完整輸出或暫存帳帶離 CEO 本機，也不得另設會輸出標籤的診斷模式。

6. **通過證據與 CG-2 的綁定**
   - (a) 「harness 通過」成立，指最後一次執行的回貼同時具備：
     - `acceptance_result=PASS`，兩個規則集都通過，失敗種類都是「無」；
     - `refusal_guard=ok`、三行 `copy_check=SAME`、`eol_check=ok`、`git_clean=yes`、`summary_lines_dropped=0`。
     - `cleanup` 不影響通過，依第 3 點處理。補充四第 5 點 M-1 的「D-7 harness 已執行」讀為本款成立。
   - (b) coordinator 當日以 commit 在 `work/` 記錄回貼原文。CG-2 PR 合併前，由 devops-sre 或 dev-lead 執行、qa 判讀，核對下列各項：
     - `git_head` 可由 `origin/product/stock-desk` 到達；
     - 回貼的 `code_digest` 等於在 `git_head` 以 `canonical.code_digest` 算出的值；
     - `lockfile_sha256` 等於 `git cat-file blob <git_head>:apps/stock-desk/backend/uv.lock` 的 sha256；
     - `harness_sha256_lf`、`script_sha256_lf` 等於兩檔在 `git_head` 的 blob 經 LF 正規化後的 sha256。
   - (c) 回貼的 `definition_logic_sha256` 必須等於 M-4 登記的 `dirdef-v1.0` 的同名雜湊。`definition_sha256` 可以不同，因為測試替身的 C-8 欄位是佔位值；但差異只能落在 `DEFINITION_NON_LOGIC_FIELDS`，CG-2 PR 以測試證明。不成立就須重跑。
   - (d) 自 `git_head` 起到 CG-2 PR 合併時的 head 為止，只允許下列差異，其餘任何差異都使通過失效，須在新 head 重跑：
     - `app/dirdef/registry.py` 中 `PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS` 的賦值，以及登記所需的 import 與 `dirdef-v1.0` 物件常數；或 `app/dirdef/` 下只含該物件常數的新檔；
     - `app/outlook/rules/h3.yaml`、`h5.yaml`；
     - `app/forecast/claims.py` 新增的頂層定義與 CLI 分支；在 `git_head` 已存在、且由 harness 遞移呼叫的頂層函式（至少 `register`、`production_path_refusal`）必須 AST 相同；
     - `app/` 以外的登記一鍵檔、文件與測試。但 `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`、`scripts/pipeline_acceptance_real.py` 與 `uv.lock` 必須零差異。

7. **換行與 lockfile**
   - `runtime_info` 的 `lockfile_sha256` 維持對原始位元組取雜湊，不改走 `normalised_source`。理由有三：`runtime_json` 含平台與 Python 建置資訊，跨機器本來就不同；改了會變動 `code_digest`；也與補充四 R-2「原始位元組對 blob」的比法不一致。
   - 根治方式：在 `apps/stock-desk/backend/.gitattributes` 加 `uv.lock text eol=lf`，不改 repo 根目錄的 `.gitattributes`，main 維持零產品耦合。PR 附上 `git ls-files --eol` 輸出，`uv.lock` 須為 `i/lf w/lf`。補充四 M-7 的屬性位置在 CG-2 PR 決定，同樣不得讓 main 綁定產品路徑。
   - 一鍵檔比對釘住檔案的工作樹原始位元組 sha256 與 blob sha256，並以 `git ls-files --eol` 作為第二證據。不一致時只停止，不改 git 設定，也不改檔。補救由 coordinator 提供，限於 `git checkout HEAD -- <path>`，不要求 CEO 修改 `core.autocrlf`。

8. **風控確認前的限制**
   - Q-1（第 1 點 (b)）與 Q-2（第 4 點 (d)）由風控確認。確認前，一鍵檔 PR 可以開發與合併，但不得在 CEO 本機執行。
   - 風控判定 Q-2 偏離 CEO #149 時，由 coordinator 向 CEO 確認。

- **S-13b（逐條可檢查）**：
  - 第 1 點：
    - e2e 測試以合成的假主 DB 驗證：主 DB 路徑只被 `open(..., "rb")`，從未被 `sqlite3.connect`；所有 connect 的目標都在 {複本, 兩個 ledger} 之內。
    - 包裝的 import 集合不含 (c) 所列模組（AST，以及執行期的 `sys.modules`）。
    - socket 被替換為拋例外的替身時，流程照常完成。
    - 列對應與 `PriceBarCache` 讀取結果逐欄相同（`as_of` 除外；`tmp_path` 合成快取）。
    - (e) 每個停止條件各有一個測試。
    - 複本在第一次呼叫 `run_acceptance` 之前已刪除。
    - `app/` 不可達 `scripts/` 與 harness（import graph）。
  - 第 2 點：注入後每根 bar 的 `as_of` 等於該日 20:00 Asia/Taipei；包裝的 SELECT 不含 `as_of`、`fetched_at`（AST）。
  - 第 3 點：包裝對 `AcceptanceResult` 只存取 `passed`，另外呼叫 `render_summary`（AST）；結束後工作資料夾只剩回貼檔；殘留掃除不動格式不符的資料夾（測試）。
  - 第 4 點：
    - 白名單每一樣式各有一個測試；無關的行被丟棄並計數。
    - 「視窗定案 session 數」不輸出，也不計入丟棄數。
    - 回貼不含 `T=`、`claim_id`、完整輸出的任一行，也不含禁詞清單中的字詞。
    - 以兩組不同標籤分佈的序列執行時，回貼除雜湊、`bars_sha256` 與執行次數外逐行相同。
    - `bars_sha256` 等於測試獨立算出的 `content_sha256`，而且兩個規則集共用同一個值（測試）。
  - 第 5 點：qa 審查清單加一行，逐條核對診斷回報不含 (d) 所列內容。
  - 第 6 點：CG-2 PR 說明列出 (b)～(d) 的核對結果；(d) 附上差異檔清單與 AST 比對輸出。
  - 第 7 點：PR 附 `git ls-files --eol` 輸出；`check_pinned_eol` 在臨時 repo 中，CRLF 工作樹判停止，LF 判 ok（測試）。

---

## 補充六附記：風控 Q-1、Q-2 確認條件的落實與第 8 點限制的解除（2026-11-16）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md`（APPROVE 附條件，RC-158～RC-165）；CEO #150（2026-11-16：「算，照這樣做」）。另讀 product 分支 `app/forecast/claims.py`、`store.py`、`schema.py`、`tests/test_forecast_claims_cli.py`。
- 性質：收緊補充六第 1、4、6 點，不放寬；解除第 8 點。不改本文與補充六原文，不改使用者面字面、規則檔、定義物件與已登記雜湊。兩者衝突時以本附記為準。

1. **第 1 點 (b) 的檔案操作（RC-158a）**
   - (a) 主 DB 的 `stock-desk.db` 與它的 `-wal`、`-shm` 只能以 `"rb"` 開啟，不得用其他任何模式開啟，也不得刪除、更名、取代、改時間戳、改權限、截斷或加鎖。這個限制同時適用於 `pathlib.Path` 的等價方法。
   - (b) S-13b 第 1 點的 e2e 監聽測試，擴充到下列呼叫：`open`／`io.open` 的模式、`os.open` 的旗標、`os.remove`、`os.unlink`、`os.rename`、`os.replace`、`os.utime`、`os.chmod`、`os.truncate`、`shutil.move`、`shutil.copy*` 的目的地、`msvcrt.locking`。判定方式是目標以 `samefile` 對三檔中任一檔成立就算命中。測試斷言三檔只出現 `"rb"` 開啟，沒有其他任何命中。
2. **適用範圍（RC-158b）**：第 1 點 (b) 的讀法只適用 D-7 真實資料那一次的 `scripts/pipeline_acceptance_real.py`。其他 tests、scripts 與 `app/` 都不得援引它讀取主 DB。既有探針的依據不受影響，但也不得改以 (b) 為依據。qa 審查清單加一行逐條核對。
3. **複本刪除失敗（RC-158c）**：第一次呼叫 `run_acceptance` 之前，複本任一檔刪不掉時，就印出固定的 ASCII STOP 句並以非零結束碼結束，不呼叫 harness。中文說明逐字採用風控定稿，放在說明文件的 STOP 對照表。測試方式：注入刪除失敗，斷言 harness 沒有被呼叫，而且輸出只有該 STOP 句。
4. **失敗種類（RC-160c）**：`failure_kinds` 維持去重、排序、不帶次數。測試涵蓋兩種情形：同一種失敗出現多次時只列一次；失敗發生的順序不同時，輸出相同。改成依出現順序或帶次數，都要重送風控並修本 ADR。
5. **畫面白名單的機械保證（RC-162）**
   - (a) 包裝程式第一個敘述就要做兩件事：把 `sys.excepthook`、`threading.excepthook`、`sys.unraisablehook` 都換成固定句；執行 `warnings.simplefilter("ignore")`。`app` 與 harness 一律在這之後才 import。
   - (b) 最外層攔截 `BaseException`（含 `KeyboardInterrupt`），只印固定句；`finally` 照常清除暫存，然後以非零結束碼結束，不繼續執行。
   - (c) 本點只適用這個包裝程式。補充四第 1 點 (b) 與補充五第 2 點規定 recorder 不捕捉 `BaseException`，兩者不衝突。
   - (d) e2e 測試擷取整段 stdout 與 stderr，斷言每一行都 fullmatch 白名單或固定的 STOP、ERROR 句。涵蓋的情境包括：正常結束、harness 拋出例外、執行緒例外、警告、注入 `KeyboardInterrupt`（取數中、harness 中、清理中）。
   - (e) 不在保證範圍內：不是 Python 行程寫出的文字，例如主控台回顯與殼層提示，以及直譯器層級的致命錯誤。
6. **第 8 點限制的解除（RC-165）**
   - 依據：風控對 Q-1、Q-2 判定 APPROVE 附條件，沒有 VETO；CEO #150 選第一項，所以 Q-2 不轉為 VETO。第 8 點與補充六檔頭的「待風控確認，確認前不得在 CEO 本機執行」，自本附記起解除。
   - 一鍵檔在 CEO 本機執行前，以下四項都要成立：
     - 一鍵檔 PR 已落實本附記第 1、3、4、5 點的測試；
     - qa PASS（含 Codex），CI 綠燈；
     - 說明文件逐字採用風控定稿（RC-164）；
     - coordinator 確認以上三項。
   - RC-159 至此履行完畢。RC-160a/b、RC-161a/b、RC-164 繼續有效。
7. **CG-2 的 `provisional_results_seen`（風控區塊五末句的使用條件）**
   - (a) `bootstrap --production` 與登記一鍵檔都接受 0 與 1。在其他條件成立時，兩個值都照常寫入並以 0 結束。補充四第 2 點與 R-1～R-8 不得新增任何依這個值拒絕的條件。
   - (b) 值在登記當下由 CEO 鍵盤鍵入。不得有預設值，不得寫死，不得取自檔案或環境變數，也不得設計只接受 0 的確認迴圈。輸入不是 `0` 或 `1` 時就停止，不寫入，不轉換。
   - (c) 兩列都寫入鍵入的值。提交後的唯讀核對，要加上「兩列的值都等於鍵入值」。回傳內容加一行 `provisional_results_seen=<0|1>`，供 RC-161a 的紀錄使用。
   - (d) 0 與 1 各有一個測試，都要登記成功、恰好 2 列、值相符；另加一個無效輸入的測試，斷言不寫入。
   - (e) 若要對 1 設任何阻擋，要先修本 ADR，由 coordinator 刪掉說明文件區塊五的末句，並重送風控。
8. **規則檔位元組（RC-163，採用）**：補充六第 6 點 (d) 的 `h3.yaml`、`h5.yaml`，只能是凍結包 §4.1、§4.2 在 `git_head` 已 commit 的逐字位元組。
   - CG-2 PR 的 M-5 測試，從 `git cat-file blob <git_head>:<凍結包路徑>` 抽出兩個區塊，與 YAML 的 blob 比對 sha256。抽取規則以常數寫明。
   - 凍結包本身從 `git_head` 起要零差異。

- **S-13c（逐條可檢查）**：第 1、3、4、5 點各款，各有上述對應的測試；第 2 點列進 qa 審查清單；第 7 點 (d) 與第 8 點列在 CG-2 PR 說明中，並附上測試名稱。

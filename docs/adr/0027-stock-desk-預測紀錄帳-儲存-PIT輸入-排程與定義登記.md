# ADR-0027：stock-desk 預測紀錄帳——儲存、PIT 輸入、排程與定義登記

- 狀態：proposed
- 日期：2026-10-16
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：
  - ADR-0026 回報附件 B 的共同說明，以及下一步第 2 點〔事實：`work/reviews/2026-10-16-tech-architect-ADR-0026草案與R-106至R-116.md:55,589`〕；
  - coordinator 保留 0027 給本案〔事實：`work/reviews/2026-10-16-T1-01與T1-02-tech-architect評估.md:4`〕。
- 適用範圍：僅 product/stock-desk 產品線。
- 前提：純自用（ADR-0025 F-1）；單機、單一使用者（ADR-0026 F-1）。
- 與既有 ADR 的關係：
  - **部分修訂 ADR-0025（accepted）**：共 11 處（M-1～M-11，見下方「修訂清單」）。
    - 比照 ADR-0025 對 ADR-0004 的作法，只在 ADR-0025 檔頭加一行修訂指標，不原地改寫。
    - **每一項都須 CEO 核可。** M-9（價位口徑）可以單獨核可或駁回，不影響其餘各項。
    - 核可前，衝突處以 ADR-0025 為準。
  - **ADR-0026（proposed）**：
    - 採用其 D-6.6 的建議：預測帳以 component `forecast` 納入 `schema_migrations`〔事實：`docs/adr/0026-…:300`〕。
    - 承接 R-116：D-8 路徑守門、D-6 遷移框架、D-9 備份組，都必須在第一筆前瞻紀錄之前上線。
    - IV-12（還原點不碰預測帳）不變〔事實：`:411`〕。
    - D-9.4 提到的 `db_restored` 缺日原因，偵測方式由本 ADR D-8 定義〔事實：`:351`〕。
  - **ADR-0012（accepted）**：不修訂。
    - C-7 加一條解釋性註記，CEO 知悉即可（D-4.6）。
    - C-8 不變：預測帳在主 DB，市場 DB 只被唯讀〔事實：`docs/adr/0012-…:794`〕。
    - C-10 不受影響〔事實：`:796`〕。
    - C-15 依 ADR-0025 修訂後的白名單：forward return 類識別字只能出現在 `app/forecast/scoring.py`〔事實：`:801`；ADR-0025 `:14`〕。
  - **ADR-0028（proposed，同批）**：本 ADR 依賴它的 `SessionCalendar` 與 `market_hours` VS-6。依賴方向只能是 forecast → data，不得反向。
  - **相容、不修訂**：ADR-0002、0004（修訂後）、0005、0009、0014、0019、0020、0021、0024，以及其餘未列者。
- 編號說明：起草時 `docs/adr/` 最後一份是 ADR-0026；0028 由 coordinator 分配給 T1-02。
- 標註約定：
  - 〔事實：檔案:行號〕為 2026-10-16 工作目錄的狀態；
  - 〔轉引〕為引用其他部門文件、我沒有逐行複核的內容；
  - 〔推論〕為我的判斷；
  - 程式路徑相對於 `apps/stock-desk/backend/`。

> **附註：ADR-0025 檔頭修訂指標（落檔者加在 ADR-0025 狀態區塊「與既有 ADR 的關係」之前）**
> `- 修訂（提案中）：ADR-0027（proposed）提案部分修訂 D-1 接線、D-2.2 解讀、D-3 missing_inputs 型別、D-5.7 價位口徑、D-6.1～D-6.5、AV-17、AT-6、AT-7、F-2、F-3 與 D-12 Phase 3 驗收欄位名（M-1～M-11，見 docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md）；各項須 CEO 核可，核可前本檔為準；本檔原文不改。`
> CEO 核可後，把「提案中」改成核可日期與決策紀錄路徑。

---

## 評估摘要（結論先行）

**採用**
1. **儲存**：預測帳放在主 DB（維持 ADR-0025 E1）。
   - 全部 `forecast_*`、`plan_*` 表都只增不改，由 trigger 強制；`forecast_outcome` 也沒有例外。
   - 唯一例外是 `forecast_claim_registry` 的兩個欄位，各允許一次性轉值。
2. **PIT 輸入**：
   - 個股與族群成員讀市場 DB 的 PIT 視圖，不讀 `price_bars_cache`。
   - 大盤在記錄當下，把實際用到的 bars 擷取進 `forecast_input_series`。
   - 指標吃錨定 T 的 `AdjustedSeries`；ATR 由同一個 Wilder 核心計算。
3. **排程**：
   - 平日 22:10 執行，23:10 重試，啟動時補跑。
   - 逾時線是 next_session(T) 當日 08:30（台北）。
   - 每次執行有協作式期限；缺日由稽核寫成紀錄列。
4. **定義登記**：
   - 定義與規則都凍結並登記雜湊；claim 登記表決定 m。
   - 「只改字面」在結構上無法產生新的 claim。
5. **驗證**：
   - 驗證狀態改為四態，判定時要贏過每一個必備基準；升級只在檢查點，降級當日生效。
   - F-2 改寫成 B 型無效停止規則，加退出期限（主方案）；A 型列為 CEO 的替代選項。
6. **寫入閘門**：ADR-0027 核可、C-8 定案、定義凍結、08:30 查證、ADR-0026 的守門與備份全部完成之前，不得寫入任何前瞻紀錄。

**否決**
- 預測帳放進市場 DB，或另開獨立 DB（理由見 R-106 與 ADR-0025 E2）。
- `forecast_outcome` 的「NULL 變成值」例外。
- 從 `price_bars_cache` 取個股輸入，以及用 `_hindsight_view` 結算。
- F-2 改成「證明比基準差」，或刪除退出期限（風控 VETO 底線）。
- 用放寬 §4.3 或 α\* 的方式解決解讀 A 的問題。

**最大代價**
- 第一筆前瞻紀錄被七道閘門延後。
- B 型會讓尚未驗證的展望最長顯示到 n＝150（大盤 5 日約 3.1 年，見 quant §4.9），全程掛「驗證中」或「未驗證」。
- 價位口徑若改成還原序列（M-9），畫面價位會和券商的未還原 K 線不一致，而且每次除權息都會整組平移。
- 表數多（13 張），寫入規則有一部分在 trigger 裡。

---

## Context（背景）

### 1. 現況（事實）
- 還沒有任何 `app/forecast`、`app/outlook` 程式。`app/` 下沒有這兩個套件（Glob），記錄帳是新建。
- **既有的只增不改作法**有三處：`market_panel.py:230,234`、`sectors/store.py:259-261,269,288`、`dividends/store.py:117-127`。其中 `sector_method_registry` 有一次性轉值的 guard trigger（ADR-0012 C-21〔事實：`docs/adr/0012-…:807`〕）。
- **主 DB 的 `dividend_events` 是 upsert**，鍵是 `(symbol, market, ex_date)`〔事實：`app/dividends/store.py:9-14,54-69`〕，所以不是 PIT。
- **配股不算因子**：只要事件帶 `stock_dividend_ratio`，`adjustment_factor` 一律回 None〔事實：`app/dividends/models.py:50-62`〕。
- **排程**：scheduler 是 `BlockingScheduler(timezone="UTC")`〔事實：`app/scheduler.py:618`〕，所以新 job 必須明定 Asia/Taipei。
- **交易日曆**：已知範圍之外的日期改用週一至週五規則〔事實：`app/data/calendar.py:74-85`〕；`observed_days_after` 只認觀察日〔事實：`:139-154`〕。
- **現行逾時線與開盤時間**：ADR-0025 的逾時線是 09:00〔事實：`docs/adr/0025-…:383`〕；程式裡的 09:00 開盤常數未查證〔事實：`app/data/quote_params.py:29-32`〕。

### 2. 需求來源
- **R-106～R-116**〔事實：`work/reviews/2026-10-16-tech-architect-ADR-0026草案與R-106至R-116.md:591-766`〕。其中 R-114 是差異表〔`:744-753`〕。
- **quant v0.2 草案**：
  - §10 的 18 列調和表〔事實：`work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md:958-985`〕；
  - §9.3 給我的 8 項待辦〔`:911-922`〕；
  - §12 claim 清單〔`:1038-1063`〕。
- **風控裁定**：
  - A-15 R-1～R-8、PA-1～PA-11〔事實：`work/reviews/2026-10-16-A-15-事先宣告草案R-1至R-8與PA-1至PA-11-風控.md`〕；
  - v0.2 單項核對與 C-8 立場〔事實：`work/reviews/2026-10-16-A-15-事先宣告v0.2單項核對與C-8立場-風控.md:40-154`〕。
- **字面所依賴的列舉值**：LM-37～LM-43、LM-46～LM-52〔事實：`work/reviews/2026-10-16-新定位第二批字面逐字審-LM29至LM62-風控.md:88-119,183-198`〕。

### 3. 為什麼要改寫 F-2（風控 C-8 立場第 1 點）
- ADR-0025 的 F-2，是依它自己比較寬的判準寫的：「與最佳基準的差，區間不含 0」，沒有 Bonferroni 校正。
- 本 ADR 的 M-4 把判準改嚴（IUT、α\*＝0.05/48，另加 (d)(e)(f)）。如果再拿同一條嚴格門檻當下架條件，下架就幾乎必定發生。
- quant 表 4〔事實：quant 草案 `:497-506`〕顯示：
  - 解讀 A 下，n＝60 時的下架機率，無預測力是 1.000，高約 13 個百分點是 0.999；
  - 解讀 B 下，對應機率是 0.84 與 0.12。

---

## Options（選項比較）

**A. 儲存位置**（R-106）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A1 主 DB（採用，維持 E1）** | 和持倉同一個隱私邊界、同一組備份 | 主 DB 會變大（每年約 220 MB〔推論〕） | 遷移必須走 ADR-0026 D-6 |
| A2 市場 DB | 和 PIT 資料放在一起 | 要修 ADR-0012 C-8；多出一類寫入者 | 混淆「外部觀察」與「本系統判斷」 |
| A3 獨立 DB | 隔離 | 備份與還原要處理兩個檔 | 只還原一邊時，紀錄會不一致 |

**B. 結算更正**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| B1 NULL 變成值一次（ADR-0025 原文） | 列數少 | trigger 有例外；更正沒有痕跡 | 第一次寫錯就無法更正 |
| **B2 完全只增不改，用 `supersedes_id` 串接（採用）** | trigger 沒有例外；更正可以追溯 | 「最新一筆」要用查詢取得 | 低 |

**C. 逾時線**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| C1 T+1 09:00（ADR-0025 原文） | 已核可 | 08:30～09:00 的盤前委託資訊可能已經存在 | 前視偏誤 |
| **C2 next_session(T) 08:30（採用）** | 保守（R-111、PA-1） | 08:30 這個時間尚未查證 | 查證前不得開始記錄 |

**D. F-2**（C-8，見 D-12）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| D0 維持原文，交給解讀 | 不改 ADR | 解讀分歧；在 M-4 之下幾乎必定觸發 | 失效條件失去辨別力 |
| D-A 解讀 A 明文化（替代） | 顯示時間最短 | 約 0.7～1.2 年就逼出一次重新設計；m 持續膨脹 | 使用者永遠只看到 n<60 的新版本（風控） |
| **D-B B 型無效停止加退出期限（主方案）** | 有辨別力；保留「不得只換說法」的原意 | 未驗證的展望最長可以顯示到 n＝150 | 依賴「驗證中」直白句守住誠實 |

**E. 價位口徑**（M-9）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **P-1 錨定 T 的還原序列（建議）** | 嚴格 PIT；除息日不會出現假缺口 | 與未還原的 K 線不一致；每次除權息都會平移 | 使用者對不上數字（以 `raw_price_at_formation` 揭露） |
| P-2 維持未還原，加底線：跨除息日的 `gap_edge` 不得用原始價 | 數字和券商一致 | 跨除息日的前高、前低會偏差一個配發金額 | 假的結構價位 |

**F. 缺日表示法**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| F1 不寫任何列（TG-a） | 簡單 | 無法區分「漏掉」與「還沒稽核」；`db_restored` 無處可記 | 缺日被低報 |
| **F2 `forecast_gaps` 寫狀態列（採用，TG-b）** | 原因可以稽核；可以計數 | 稽核執行之前看不到 | 以 `last_gap_audit_at` 揭露 |

**G. 缺項原因列舉值放哪裡**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **G1 ADR-0027（採用）** | 它是 `MissingItem` 的欄位；M-7 本來就在本案修訂 D-3 | — | — |
| G2 ADR-0028 | — | 估值狀態只供顯示，不得被 outlook、plan 讀取（ADR-0028 CS-4）；放在那裡會把兩者耦合 | 列舉值漂移 |
| G3 另立 ADR | 可以通用化 | 兩份 ADR 修訂同一個結構 | 重工 |

**H. 個股輸入來源**（R-107）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| H1 `price_bars_cache` | 現成 | 衝突時覆寫，不是 PIT〔轉引 R-107：`cache.py:52,212-231`〕 | 前視偏誤 |
| **H2 市場 DB 的 PIT 視圖（採用）** | 有 `recorded_at` 與 run 證明 | 只涵蓋 TWSE 上市普通股 | 其餘標的一律證據不足 |
| H3 預測帳自存全部 bars | 自我稽核 | 重複儲存 | 只對大盤採用（指數沒有 PIT 儲存） |

---

## 修訂清單（對 ADR-0025，每項須 CEO 核可）

| # | ADR-0025 原文位置 | 原文要點 | 新文 | 依據 |
|---|---|---|---|---|
| **M-1** | D-6.2〔`:383`〕；AV-17〔`:555`〕；AT-6〔`:569`〕；F-3〔`:581`〕；D-12 Phase 3 驗收〔`:496`〕 | t+1 開盤（09:00）之前寫入，否則 `recorded_after_next_open=1`；臨界點 08:59:59／09:00:00 | 截止＝`next_session(T)` 當日 08:30（Asia/Taipei，ADR-0028 VS-6）；欄位改名為 `late`，另存 `late_cutoff_at`、`late_cutoff_basis`；臨界點 08:29:59／08:30:00；Phase 3 驗收改為 `late=0`。駁回時：截止退回 VS-2（09:00），其餘條文不變 | R-111 第 3 點；quant §1.4；PA-1 |
| **M-2** | D-6.1〔`:375`〕；AV-17〔`:555`〕 | 例外是 `forecast_outcome` 的「NULL 變成值」一次性寫入 | 沒有例外，更正以 `supersedes_id` 串接；`forecast_*`、`plan_*` 的唯一例外改為 `forecast_claim_registry` 兩欄各一次轉值 | R-106；quant §6.2 |
| **M-3** | D-6.3〔`:386-391`〕；AT-7〔`:570`〕 | 簡單報酬、σ20、`r_h > b_h` | 以凍結的 `dirdef-v1.0` 為準：對數報酬、σ60（60 個日報酬中至少 55 個有效；σ<0.1% 視為退化）、K_3＝K_5＝0.43、嚴格不等式加 EPS、平手歸震盪；簡單報酬只存在 `realized_return` 作揭露；AT-7 改以 z 的邊界測試。**若 CEO 不採對數報酬與 σ60，`dirdef-v1.0` 必須在 D_v 之前改用原式，不得中途切換**（風控第 1 項） | R-114；quant §2.1；風控第 1 項〔C-8 立場檔 `:43`〕 |
| **M-4** | D-6.5〔`:399-410`〕 | 至少三個基準；「與最佳基準的差」；三態 | 見下方 M-4 細項 | quant §3、§4；PA-2；R-4；第 2、3 項 |
| **M-5** | D-6.4〔`:396`〕 | 回放分樣本內、樣本外 | 大盤回放整段視為樣本外，逐段（126 日）報告，並附 PA-8 限定語。**以 CEO C-5 核可為前提**；C-5 駁回時本項撤回，回放方法改由 quant 另提 | quant §4.7；C-5 |
| **M-6** | D-6.2〔`:384`〕 | 同一個 `(scope, horizon, data_as_of, method_version)` 只能有一筆 | 唯一性只套用在原始列：`(scope_kind, scope_key, horizon, data_as_of, definition_version, rules_version, trigger) WHERE supersedes_id IS NULL`；`supersedes_id` 本身 UNIQUE（更正鏈是線性的）；統計一律用原始列 | quant §6.2、§9.3 第 3 點；R-8 |
| **M-7** | D-3〔`:244`〕 | `missing_inputs: tuple[str, ...]` | 改為 `tuple[MissingItem, ...]`（D-13）；`PositionPlan` 的 insufficient 也用同一型別 | quant §5.2、§9.3 第 4 點 |
| **M-8** | D-1〔`:179`〕；D-2.2〔`:193-198`〕 | `outlook.features → data(load_bars／index)`；大盤輸入含廣度 | 接線改為 `outlook.features → outlook.inputs →`（個股、族群成員）`data.market_panel.MarketPanelReader` 唯讀，或（大盤）`services.index` 並擷取輸入；不得經過 `load_bars`／`price_bars_cache`。D-2.2 加解讀註記：所列輸入是允許的上限，v1 大盤只用指數日線；加入廣度要開新的 `rules_version`（新 claim，m＋1） | R-107 第 8 點；quant §10 D-14 |
| **M-9** | D-5.7〔`:371`〕 | 價位用未還原收盤，跨除息日標 `spans_ex_date` | **可單獨核可**，見 D-6 | R-110 |
| **M-10** | F-2〔`:580`〕 | 連續兩個評估期都是 `not_better_than_baseline` 就重新設計或下架 | 改寫，見 D-12（主方案 B 型，替代方案 A 型） | C-8；風控立場 |
| **M-11** | D-6.1 表清單〔`:376-381`〕；F-3〔`:581`〕 | 五張表；F-3 只寫「暫停顯示，查明」 | 新增 8 張表並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6） | R-106、R-112、R-113；風控第 9 項 |

**M-4 細項**
- (a) **基準採聯集**：
  - B6＝D-6.5 的 (a)；B7（事後眾數）是 (b) 的解讀，**我確認採用**，理由是 B7 的命中率恆 ≥ B7r，比較嚴；B8＝(c)。
  - 必備集合：大盤 B1、B2、B6、B7、B8；族群另加 B3；個股另加 B3、B4。
  - B7r、B0 是參考線，B5 是診斷。
  - B7、B7r 只在評估時計算，寫進 `forecast_validation_snapshot`，不寫進發布當下的 `baseline_predictions`。
- (b) **判定採 IUT**：對每一個必備基準，quant §4.3 的 (a)～(f) 都要成立。「與最佳基準的差」保留為報告指標。
- (c) **α\***＝0.05÷(m_eff×K_c)，m_eff＝max(m, M_PLANNED)，v1 的 M_PLANNED＝8。
- (d) **四態**：
  - `unverified`（取代 `insufficient_sample`）
  - `under_validation`（新增）
  - `not_better_than_baseline`
  - `better_than_baseline`
- (e) **升降不對稱**：升級只在檢查點，降級當日生效（R-4 第 1 點，加上 quant 的 (c)～(f)）。
- (f) **N_MIN**：大盤與個股 30、族群 150，都以不重疊樣本計。
- C-3 的嚴格度屬 CEO 的取捨，不在本 ADR 範圍；風控的 VETO 項照舊。

**只是解讀、不修訂（CEO 知悉）**：
- quant §10 D-5、D-6、D-10、D-11、D-13、D-17、D-18 各列，屬於填參數或名稱對照；
- AV-18 維持，另加「觀察到第 h 日」條件（兩者都要成立）。

---

## Decision（決策）

### D-1 模組邊界

| 模組 | 職責 |
|---|---|
| `app/forecast/schema.py` | component `forecast` 的 DDL、trigger、遷移（ADR-0026 D-6），以及啟動時的 schema 檢查 |
| `app/forecast/store.py` | 只增不改的寫入（時間戳由 store 時鐘填入）；唯讀查詢 |
| `app/forecast/definitions.py` | frozen 的 `DirectionDefinition`、`PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS` |
| `app/forecast/claims.py` | claim 登記與 m 的計算 |
| `app/forecast/recorder.py` | 執行編排：範圍快照、run 與 run_end、協作式期限、逾時判定 |
| `app/forecast/scoring.py` | 結算與基準命中（ADR-0012 C-15 白名單，唯一可以出現 forward return 類識別字的地方） |
| `app/forecast/validation.py` | 驗證快照、四態、F-2 與 F-3 的顯示判定（只讀結算結果，不算報酬） |
| `app/forecast/audit.py` | 缺日稽核 |
| `app/forecast/display.py`（純函式） | 每個 claim 與 scope 的顯示決定（閘門、下架、暫停、逾時） |
| `app/outlook/inputs.py` | PIT 輸入：唯讀 `MarketPanelReader`；大盤擷取 |
| `app/outlook/missing.py`（純函式） | `MissingItem`、`SourceStatus` |
| `app/dividends/adjust.py::adjust_series_pit` | `AdjustedSeries`（R-108） |
| `app/signals/kernels.py::wilder_atr` | ATR 核心（R-109） |
| `app/api/forecast.py` | `GET /api/forecast/status`、`GET /api/forecast/records` |
| `app/api/outlook.py` | `POST /api/outlook/symbols/{symbol}`（on-demand） |

### D-2 儲存（R-106、R-116）
1. 預測帳放在主 DB。
2. 所有 `forecast_*`、`plan_*` 表的 `BEFORE UPDATE`／`BEFORE DELETE` 一律 `RAISE(ABORT, 'append-only')`，照抄 `market_panel.py:230,234` 的形狀。唯一例外是 `forecast_claim_registry`（D-10.3）。
3. 時間戳（`created_at`、`recorded_at`、`detected_at`、`resolved_at`）一律由 store 時鐘填入，以 UTC ISO8601 儲存，不接受呼叫端傳入。
4. 每張表都有明確主鍵，不依賴隱式 rowid。
5. 以 component `forecast` 登記在 `schema_migrations`。遷移只能是欄位保留型（ADR-0026 D-6.5）。

### D-3 資料表（欄位取 ADR-0025 與 quant §6 的聯集；只列關鍵欄位）
- `forecast_run(run_id, trigger ∈ {scheduled, on_demand}, data_as_of, definition_version, rules_versions_json, policy_version, formula_version, code_commit, recorded_at)`
- `forecast_run_end(run_id PK, outcome ∈ {ok, partial, timeout, error}, scopes_done, scopes_missed, ended_at)`：沒有 end 列就代表程序中途崩潰。
- `forecast_scope_snapshot(run_id, scope_kind, scope_key, market, reason ∈ {market, sector, holding, watchlist, queried})`：**不含成本與股數**（AV-9）。
- `forecast_input_series(series_id, content_sha256 UNIQUE, source, source_status, bars_json, captured_at)`：用於大盤與結算路徑，以內容雜湊去重。
- `forecast_record`：
  - 識別：`forecast_id`（ULID）、`run_id`、`claim_id`、`scope_kind`、`scope_key`、`scope_reason`、`horizon`、`data_as_of`；
  - 結論：`label`、`range_basis`、`missing_json`（MissingItem 陣列）、`definition_version`、`rules_version`；
  - 判定材料：`band_def`（threshold_snapshot，含 `up_pct`、`down_pct`）、`base_close`（P\*(T)、原始 P(T)、還原狀態）、`evidence_json`、`invalidations_json`、`coverage_json`、`baseline_predictions_json`；
  - PIT 證明：`inputs_max_recorded_at`、`source_run_min`、`source_run_max`、`input_digest`；
  - 時間：`valid_until_session`、`created_at`、`late`（排程紀錄為 0 或 1；on_demand 為 NULL）、`late_cutoff_at`、`late_cutoff_basis ∈ {official, weekday_assumed}`；
  - 更正與雜湊：`supersedes_id`、`correction_reason`、`content_hash`。
- `forecast_outcome`：
  - 識別：`outcome_id`、`forecast_id`；
  - 結算：`resolved_at`、`settlement_date`、`start_price_json`、`end_price_json`、`window_factors_json`、`realized_log_return`、`realized_z`、`realized_label`、`realized_return`、`hit`、`baseline_hits_json`；
  - 診斷：`diag_open_based_json`、`diag_last_close`、`diag_basket_with_excluded`（風控第 8 項）、`basket_excluded_members_json`、`index_return_diag`；
  - 期間路徑：`invalidation_triggered`、`invalidation_first_hit`、`mae`、`mfe`；
  - 稽核：`input_digest_recomputed`、`digest_match`；
  - 狀態：`status ∈ {resolved, unresolvable_missing_data, excluded_corporate_action}`、`status_reason`（D-9.3）；
  - 更正：`supersedes_id`、`correction_job_id`；
  - 唯一性：`UNIQUE(forecast_id) WHERE supersedes_id IS NULL`，以及 `UNIQUE(supersedes_id)`。
- `forecast_replay`：結構與 `forecast_record` 相同，另加 `freeze_commit`、`replay_session`。永遠不與前瞻紀錄合併。
- `forecast_gaps(gap_id, session, claim_id, scope_key, reason, detected_at, run_id NULL, UNIQUE(session, claim_id, scope_key))`：`scope_key = '*'` 代表整個 claim。
- `forecast_claim_registry`（D-10）、`forecast_validation_snapshot`（D-11）。
- `forecast_ledger_events(event_id, kind ∈ {db_restored, f3_resume_approved}, payload_json, recorded_at)`。
- `plan_record(plan_id, run_id, symbol, market, mode, position_action, reasons_json, levels_json, conditions_json, quantity_json, policy_version, created_at)`：含成本與股數，只存在本機。
- `plan_outcome`：表與只增不改的規則由本 ADR 固定；欄位定義另案處理（quant §6.5，見待決）。

### D-4 PIT 輸入（R-107）
1. **TWSE 上市普通股**：讀 `market_daily_bars` 的 PIT 視圖。
   - 可見性規則與 `panel._visible` 位元相同：`session_date ≤ T`、`recorded_at ≤ cutoff(T)`、只取 ok run、依來源優先序〔轉引 R-107：`panel.py:886-922`〕。
   - 新增以代號為範圍的唯讀方法，並補上等價測試。
2. **還原用的除權息事件**：取 `pit_dividend_announce_rows` 的 PIT 視圖，不讀主 DB 的 `dividend_events`（upsert）。
3. **PIT 證明**：`inputs_max_recorded_at`，以及 `source_run_min`、`source_run_max`。超過 cutoff 就輸出 insufficient，缺項代碼為 `E-PIT-UNVERIFIED`。
4. **上櫃、ETF、美股**：一律 insufficient（`E-SCOPE-OTC`、`E-SCOPE-TYPE`）。
5. **大盤**：把實際用到的 bars 寫進 `forecast_input_series`，並揭露 `index_source_status=backup`。
6. **ADR-0012 C-7 的解釋性註記**（CEO 知悉，不修訂）：
   - C-7 所說的「持倉資料鏈」，指請求觸發、逐代號的鏈：`load_bars → price_bars_cache → 估值`。
   - 展望鏈是另一條（排程，加上專用的 on-demand 端點），而且反向也不得讀 `price_bars_cache` 的個股 bars。
   - `/api/advice` 只讀預測帳。

### D-5 還原序列與 ATR（R-108、R-109）
1. `AdjustedSeries`（frozen，不是 `PriceBar` 的子類）只能由 `adjust_series_pit(bars, events, anchor=T)` 產生，只套用除權息日 ≤ T 的事件。
2. 不變式：`close[anchor] == 原始收盤[T]`，精確相等。
3. 既有的 `back_adjust_bars` 不動。
4. 估值類模組 transitively 不得可達 `app.dividends.adjust`（FL-12）。
5. `wilder_atr` 是唯一的 ATR 核心：
   - `technical.atr` 改為呼叫它，輸出與現行逐位相同；
   - outlook 與 keylevels 用 `AdjustedSeries` 的陣列呼叫它；
   - 前端的簡單平均 ATR 凍結，不得新增使用者。
6. 成交量用原始值；配股不還原，要揭露。

### D-6 價位口徑（M-9，可單獨核可；修訂 D-5.7）
- **P-1（建議）**：價位在錨定 T 的還原序列上偵測與計算，數字以 T 日的原始價格單位表示。
  - `PlanLevel` 新增 `price_basis = "adjusted_anchor_T"` 與 `raw_price_at_formation`；`spans_ex_date` 保留。
  - 還原涵蓋不足（`E-ADJ-COVERAGE`）時，該價位缺席，不退回原始價。
  - `cost_anchor` 不換算，它是金額，不是結構價位。
  - **結果端**：`plan_outcome` 判斷是否觸價時，要把 (T, t] 內的原始價除以該區間內除權息因子的累乘，換算到 T 的價格單位；因子不可用時，該筆標 excluded。
- **P-2（備案）**：維持 D-5.7 原文，另加底線：跨除息日的 `gap_edge` 不得以原始價計算，`zone_cluster` 跨除息日時必須標 `spans_ex_date`。
- 兩案都會改變畫面上的數字或可用的依據，須 CEO 核可。

### D-7 排程、逾時與截止時間（R-111）
1. **job `forecast_record`**：
   - 平日 22:10 執行，23:10 重試，啟動時補跑（啟動後 3 分鐘）；
   - `max_instances=1`、`coalesce=True`、`misfire_grace_time` 30 分鐘；
   - trigger 明定 `timezone="Asia/Taipei"`（因為 scheduler 預設是 UTC，`scheduler.py:618`）。
2. **執行順序**：記錄 → 結算 → 缺日稽核 → 驗證快照。
3. **決策日 T**：市場 DB 中最新一個有 ok bars run 的 session，而且大盤 T 日 bar 已經存在。
4. **逾時判定**：
   - `late_cutoff_at` ＝ `SessionCalendar.next_session(T)` 當日的 VS-6（08:30 Asia/Taipei），寫入時計算並存下，之後不重算。
   - `late_cutoff_basis` 記錄 next_session 是取自官方日曆，還是週一至週五推定。推定只會讓截止線提早，方向保守〔推論〕。
   - `late = created_at ≥ late_cutoff_at`，由 store 決定，不得手動指定。
5. **`{截止時間}`**：
   - API 回傳 `late_cutoff_at`，格式是含 `+08:00` 的 ISO8601。
   - 前端以 Asia/Taipei 格式化為 `MM/DD HH:mm`；年份規則沿用 creative-lead 的通用約定。
   - 前端不得自行推算截止時間，也不得用瀏覽器時區。
6. **補跑**：一律用 `as_of(T)` 的 cutoff；若已逾時，`late=1`，只列示，不計入主統計。
7. **執行期限**：
   - 每次執行以 40 分鐘為協作式期限，在範圍與範圍之間檢查；每個範圍各自一個交易。
   - 逾時後剩下的範圍記為缺日，原因 `timeout`。
8. **on-demand**：
   - 個股在排程範圍內、而且 T 日排程紀錄已存在時，直接回傳既有紀錄，不寫入。
   - 否則寫一筆 `trigger=on_demand`，`late` 為 NULL，不計入主統計，畫面要標示「不計入主統計」（PA-4）。
9. 主機常駐由 devops-sre 負責；API 永遠不執行排程預測。

### D-8 缺日（R-112；字面用 TG-b）
1. **觀察日**：市場 DB 有 ok bars 的 session，聯集大盤實際有 bar 的日期。不用週一至週五推定。
2. **稽核**：對每個觀察日 S、每個已登記的前瞻 claim，若沒有 `late=0` 的排程紀錄，就寫一列 `forecast_gaps`。
   - `reason` 的判定：
     - 該日沒有任何 run：`scheduler_down`
     - 有 run、沒有 end：`job_error`
     - 只有 late 紀錄：`late_only`
     - 期限到時尚未執行的範圍：`timeout`
     - 輸入未就緒：`inputs_not_ready`
     - 落在 `forecast_ledger_events.kind=db_restored` 標記的區間：`db_restored`
   - 有範圍快照時，逐 scope 寫列；沒有快照（例如 scheduler 停機）時，寫 `scope_key='*'`。
3. **`db_restored` 的標記**：整檔還原後，由操作者執行 `python -m app.forecast.ledger_events mark-restored --manifest <path>` 寫入，納入 ADR-0026 D-9.4 的程序（devops-sre）。
4. **不補造**。缺日不計入 n，但要揭露。
5. **渲染**：
   - `late_only` 的缺日列不渲染 TG-b，改以 LM-37 逾時句呈現那筆逾時紀錄；
   - TG-c 的計數不含 `late_only`，日期清單完整列出；
   - `GET /api/forecast/status` 回傳 `last_gap_audit_at`。

### D-9 結算與作廢
1. **觸發條件**（三者都要成立）：
   - 觀察到第 h 個交易日 T+h；
   - 該日資料的 `recorded_at ≤ cutoff(T+h)`；
   - `valid_until_session` 已過（AV-18）。
2. **結算資料**：個股用 `as_of(T+h)` 的 PIT 視圖，不得用 `_hindsight_view`；大盤用擷取的指數路徑。
3. **結算窗**：觀察交易日 T+1～T+h 的日線，報酬自 T 收盤起算。作廢原因（`status_reason`）：
   - `missing_bar_after_wait`：T+h 無 bar，再等 5 個觀察日仍無 → `unresolvable_missing_data`
   - `basket_coverage_below_90`：族群籃子排除停牌或因子不可用的成員後，覆蓋 < 90% → `unresolvable_missing_data`
   - `split_or_reduction_suspected`：窗內單日報酬超過漲跌幅限制加容差（推定，不是確認的事件） → `excluded_corporate_action`
   - `dividend_factor_unusable`：窗內有除權息，但因子算不出來（**含配股**，`models.py:50-62`） → `excluded_corporate_action`
4. **失效條件觸發不作廢**（PA-7）；只記 `invalidation_triggered`，照常結算、照常計分。
5. **更正**：
   - 只限來源資料的更正，不含定義變更。
   - 由確定性作業對受影響日期範圍內的**全部**結算重查（結算窗與受影響日期有交集的都算），記錄 `correction_job_id`。
   - 有變的筆新增一列並填 `supersedes_id`；結算端改用最新一筆，預測端永遠用原始那一筆。
6. 逾時與 on-demand 的紀錄也照常結算，供紀錄清單列示。

### D-10 定義與 claim 登記（R-113，quant §12）
1. **雜湊登記**：
   - `PUBLISHED_DIRECTION_DEFINITIONS` 與 `PUBLISHED_RULESETS` 都登記雜湊，loader 遇到不符就拒絕載入。
   - 另定 **`rules_logic_sha256`**：把規則 YAML 去掉文字欄位（`explanation`、`counterargument`，以及 quant 凍結時列出的其他字面鍵）後，做正規化的 sha256。
   - 同理定 `definition_logic_sha256`：只含常數，不含說明文字。
2. **claim 主鍵**：沿用 R-113 的 `{scope_kind}|h{h}|{rules_version}|{definition_version}|{kind}`，在第一次登記時固定。
   - 之後若只改文字（rules 升 PATCH，或 dirdef 升 MINOR），沿用原 claim。
   - 寫入紀錄時，檢查該筆的 logic 雜湊等於所屬 claim 的雜湊，不符就拒絕。
3. **`forecast_claim_registry`**：
   - 欄位：`claim_id`、`scope_kind`、`horizon`、`kind ∈ {forward, replay}`、`rules_logic_sha256`、`definition_logic_sha256`、`rules_sha256`、`frozen_commit`、`prereg_doc_path`、`prereg_doc_blob`、`review_refs`（風控與 qa 審查紀錄的路徑）、`predecessor_claim_id`、`predecessor_withdrawn_at_n`、`registered_at`、`first_record_at`、`counts_toward_m`。
   - `UNIQUE(scope_kind, horizon, kind, rules_logic_sha256, definition_logic_sha256)`，所以純字面變更無法登記新 claim。
   - guard trigger：只允許 `first_record_at` 由 NULL 變成值，同時 `counts_toward_m` 由 0 變 1，各一次；其餘欄位不得變動，也不得刪除。
4. **m 與 α\***：m＝`counts_toward_m=1` 的列數；v1 起始 6，大盤重放執行後為 8；m_eff＝max(m, 8)。
5. 族群動能的 `sector_method_registry` 不合併計算 m，附風控第 11 項的條件：若展望特徵是看過動能研究結果之後才選的，就要合併。

### D-11 驗證狀態、主統計與顯示
1. **主統計的資格集合 E**：
   - `trigger=scheduled`、`late=0`、`supersedes_id IS NULL`、claim 為 forward、日期 ≥ D_v，而且不是已確認的 PIT 違規列。
   - quant §4.1 的不重疊 n、重疊的次要統計、涵蓋率，**一律只在 E 上計算**。
   - 作廢列不計入 n，但計入最壞情境 W。
   - 逾時與 on-demand 的紀錄另外列出筆數。
2. **`forecast_validation_snapshot`**：
   - 欄位：`claim_id`、`computed_for_session`、`eval_kind ∈ {daily, checkpoint}`、`checkpoint_n`、`n`、`m_at_eval`、`m_eff`、`K`、`alpha_star`、`status`（四態）、`display_state ∈ {gated, shown, suspended_f3, withdrawn_f2}`、`void_rate`、`stats_json`、`bootstrap_seed`、`code_commit`、`computed_at`；
   - `UNIQUE(claim_id, computed_for_session, eval_kind)`；
   - `bootstrap_seed` 由 `(claim_id, session)` 確定性導出（風控第 3 項）。
3. **升降規則**：只有 `checkpoint` 列可以把狀態升為 `better_than_baseline`；`daily` 列只能維持或降級。
4. **顯示閘門**（`display.py`）：
   - 族群 n<150 時，任何對外回應都不出現 bullish／bearish（PA-9、LG-15）；
   - 逾時紀錄不當作當日展望（PA-6）；
   - F-2 下架、F-3 暫停時同樣不出現；
   - CEO #10 的結果作為參數注入。
5. **開盤基準 fail-closed**（風控第 4 項）：開盤基準算不出來，或開盤欄位口徑未查證時，顯示面預設附上隔夜跳空的直白句。
6. **F-3**（M-11）：
   - 上限依 quant 登記：逾時率 >10%、digest 不一致率 >2%、PIT 違規 ≥1 筆；
   - digest 的分母是 min(250, 已結算筆數)；
   - 觸發後 `suspended_f3`；恢復顯示須有 quant 與 data-engineer 的根因文件，經 qa 審查，寫入 `f3_resume_approved` 事件；
   - PIT 違規列移出 E；這些列若曾參與「優於基準」的判定，該判定當日撤銷，到下一個檢查點重判；
   - 數值在 D_v 前凍結。

### D-12 F-2 改寫（M-10；C-8，CEO 擇一）

**共同部分（兩案都適用，而且是風控底線）**
- (i) 評估期就是 quant §4.5 事先宣告的檢查點：大盤與個股為 30、60、100、150、250、500；族群為 150、250、500。
- (ii) **下架的效果**：該 claim 的最新方向標籤從所有顯示面消失，包括 API 的最新方向欄位、提醒、天氣圖示、詳細頁、匯出。紀錄與統計仍可在詳細頁查到；紀錄帳照記，n 繼續累積（風控第 6 項第 2 點、底線 5）。
- (iii) **重新上架**：只能在之後某個事先宣告的檢查點通過 §4.3 全部條件（底線 6）。
- (iv) **重新設計**：
  - 必須是實質的規則變更：`rules_logic_sha256` 或 `definition_logic_sha256` 不同（結構檢查，FL-33），而且實質性要經風控與 qa 審查（`review_refs`）；
  - 必須重新事先宣告（`prereg_doc_blob` 不同）；
  - 新版上畫面時，要同時揭露前一版「於 n＝X 下架」以及前一版的紀錄（`predecessor_*`）；
  - 只改字面不得重置計數（D-10.2、D-10.3）。
- (v) 作廢率 >5% 時，判定取一般情境與 W 之中比較差的那個（底線 3）。
- (vi) 不得用放寬 §4.3 或 α\* 的方式改變下架結果（底線 4；那屬於 C-3）。
- (vii) C-8 必須在 D_v 前定案。之後只能往更嚴的方向改，而且要升版、留紀錄（底線 7）。

**主方案 F2-B（B 型無效停止規則，風控建議，我同意）**
- 下架條件一（無效停止）：自 N_MIN 起，**任兩個相鄰檢查點**（滾動計算：30 與 60、60 與 100……）的模型點估計，在共同子集上都 ≤ 任一必備基準，就下架（底線 1）。
- 下架條件二（退出期限）：在 n＝150（族群 n＝250）的檢查點，狀態不是 `better_than_baseline`，就下架（底線 2）。
- **VETO 底線**：
  - 下架條件不得比條件一寬，也不得改成「證明比基準差」（例如區間上緣低於基準）；
  - 不得刪除條件二。延後條件二須 CEO 書面同意，風控保留書面異議。
- 後果〔合成，quant 表 3、表 4〕：
  - n＝60 時下架機率：無預測力約 84%、高 7 個百分點約 37%、高 13 個百分點約 12%；
  - 在 n＝150 時，高約 13 個百分點的模型通過的機率只有約 0.05～0.07，所以多數 claim 仍會在約 3.1 年（大盤 5 日）時退出〔推論，由表 3 換算〕；
  - 族群的條件二（n＝250）剛好是第二個檢查點，所以族群在 B、A 兩案下的實際差異很小〔推論〕。

**替代選項 F2-A（解讀 A 明文化）**
- 自 N_MIN 起，任兩個相鄰檢查點都不是 `better_than_baseline`，就下架。共同部分 (ii)～(vii) 一樣適用。
- 後果：大盤與個股幾乎都在 n＝60 時下架（5 日約 1.2 年、3 日約 0.7 年），被迫重新設計，m 跟著增加〔合成，表 4〕。
- 照實寫明：解讀 A 是 ADR-0025 三態之下的字面讀法，**不是**風控 PA-1 的要求（風控第 6 項第 1 點）。

**與風控 R-4「降級不對稱」的關係**
1. **管的對象不同**：R-4 管驗證徽章（正面主張何時可以出現、何時必須撤回）；F-2 管 claim 的顯示生命週期（何時整個撤下、何時可以重新設計）。
2. **共同原則**：正面方向只在檢查點發生（R-4 的升級、F-2 的重新上架）；負面方向可以更快（R-4 的降級當日生效）。
3. **F-2 的下架為什麼只在檢查點判定、不每天判定**：
   - 每天判定下架，等於在負向反覆偷看，好模型被下架的機率會升高。
   - 徽章已經每天降級，加上 R-3 的直白句，誠實度已經有保障〔推論〕。
4. **解讀 A 的問題**：
   - 它把 R-3 已定義為「非正面主張」的 `under_validation` 當成失敗；在嚴格的 α\* 之下，`under_validation` 是 n 小時的常態，不是負向證據。
   - 結果是失效條件的觸發與模型好壞無關（1.000 對 0.999），失去辨別力。
   - B 型只計算點估計 ≤ 基準這種負向證據，保留了 F-2「不得只換說法」的原意。
5. **兩者不衝突**：B 型之下，claim 可以掛著「驗證中」徽章顯示，同時受 R-4 每日降級約束，直到條件一或條件二觸發。

### D-13 缺項結構（M-7）

```python
SourceStatus = Literal["not_covered", "fetch_failed", "not_yet_published",
                       "failed_check", "not_configured", "unknown"]

class MissingItem(BaseModel):              # frozen
    code: str                              # dirdef E-code, e.g. "E-BARS-SHORT"
    item: str                              # vocabulary key of the missing input
    required: str | None                   # decimal/int as string
    available: str | None
    source: str | None                     # data source id
    source_status: SourceStatus | None
    attempted_at: datetime | None          # fetch_failed only (attempt time)
    latest_available: date | None          # not_yet_published only
    as_of: date
    detail: dict[str, str]
```

- **不變式**：
  - `label == "insufficient"` 若且唯若 `missing` 非空；
  - `source_status` 非 None 若且唯若 `source` 非 None；
  - `fetch_failed` 必有 `attempted_at`；
  - `not_yet_published` 必有 `latest_available`。
- **判定順序**（第一個成立的就採用，每一項都要有正面證據，不得由「沒有資料」反推）：`not_configured` → `not_covered` → `fetch_failed` → `failed_check` → `not_yet_published` → `unknown`。
- 只有可歸因到某個資料源的缺項才填 `source_status`。例如 `E-SCOPE-TYPE` 是定義範圍外，填 None。
- **封閉列舉**：新增值（例如日後從 `not_configured` 拆出 `missing_setting`，對應 LM-51）須修訂本節，並同步送字面審。
- 不與既有估值的 `missing` token，或 advice 的缺欄位，合併成同一個列舉。

### D-14 寫入閘門（D_v 之前）
**G-1～G-7 全部成立之前，recorder 拒絕寫入任何 `trigger=scheduled` 的前瞻紀錄**（風控第 1 項、底線 7、R-116）：
- G-1：ADR-0027 accepted。
- G-2：C-8 定案。
- G-3：`dirdef-v1.0` 與各規則凍結並 commit，F-3 上限一併凍結；registry 中 `frozen_commit`、`rules_sha256`、`prereg_doc_blob` 都非 NULL。
- G-4：ADR-0028 VS-6 的 `verified_on` 非 None。
- G-5：ADR-0026 D-8、D-6 已上線，D-9 備份組至少成功產出一次。
- G-6：`app/forecast/**` 的 PR 通過 qa-reviewer 與 Codex。
- G-7：on-demand 不受 G-6 以外的限制，但同樣不計入主統計。

D_v ＝該 claim 第一筆 E 紀錄的 T。

### D-15 政策表與行動紀錄（風控第 12 項、R-6 第 3 點）
- 政策表 v0（ADR-0025 D-4.3）的任何條件，都不得引用 `avg_cost`、`cost`、`cost_anchor`、`pnl_vs_cost`、`unrealized_pnl_pct`，由 loader 守門。
- advice 規則中，方向為 reduce、stop_loss、take_profit 的規則，條件也不得引用 `position.unrealized_pnl_pct`。
- 政策表以 `policy_version` v0 凍結；上線後揭露實際觸發頻率，沒有升版不得調整。
- `plan_record` 每個 T 每檔一筆，由同一次排程寫入，只增不改。

---

## Consequences（後果）

**好處**
- 每一筆預測都能自我稽核：輸入（PIT 證明或擷取的序列）、定義、規則雜湊、逾時線都在同一列。
- 「換版本直到好看」與「只改字面重置計數」在結構上被擋下。
- F-2 回復辨別力，又保留「不得只換說法」與退出期限。
- 逾時、作廢、缺日三類都有對應的紀錄型態，字面可以照實寫。

**代價與壞處**
- 第一筆前瞻紀錄要等七道閘門；08:30 若一直查證不到，記錄就一直不能開始。
- F2-B 下，尚未證明的展望最長會顯示約 3 年（大盤 5 日）。誠實度依賴「驗證中」直白句，以及風控的版面限制（不得用綠色、勾號、進度條）。
- M-9 若採 P-1，價位與券商的未還原 K 線不一致，每次除權息都會整組平移；`plan_outcome` 要做換算。
- **展望鏈與持倉鏈的資料源不同**：展望讀市場 DB，持倉讀 `price_bars_cache`。同一個 T 的原始收盤可能不同，plan 必須檢查一致性（FL-25）。
- 13 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。
- 主 DB 每年約增加 220 MB〔推論〕。
- 主機晚上不開機，樣本就不會增加（quant §4.9 的 g）。
- 規則 YAML 必須把文字欄位與邏輯分開，否則 logic 雜湊無法定義。
- API process 會寫入 on-demand 紀錄，因此預測帳有兩個寫入者，靠 SQLite 的序列化與 `busy_timeout` 處理。

---

## 對實作的約束（逐條可檢查）

**儲存與只增不改**
- **FL-1**：所有 `forecast_*`、`plan_*` 表都有 `BEFORE UPDATE`／`BEFORE DELETE` RAISE trigger。`forecast_claim_registry` 的 guard trigger 只放行 D-10.3 的兩欄轉值。檢查方式：以 `sqlite_master` 核對，啟動時缺任何一個就拒絕啟動。
- **FL-2**：時間戳欄位不是 store 方法的參數。檢查方式：AST 檢查簽章。
- **FL-3**：`forecast_record` 與 `forecast_outcome` 的部分唯一索引與 `UNIQUE(supersedes_id)` 存在，以 `sqlite_master` 檢查。
- **FL-4**：component `forecast` 登記在 `schema_migrations`；遷移前備份與雜湊比對沿用 ADR-0026 IV-7。

**PIT 與還原**
- **FL-5**：`app/outlook/**`、`app/forecast/**` 不得出現 `price_bars_cache`、`dividend_events`、`_hindsight_view`（grep）。
- **FL-6**：`app.api.advice` 不可達 `app.data.market_panel`、`app.outlook.inputs`、`app.forecast.recorder`（import graph）。
- **FL-7**：`inputs_max_recorded_at > cutoff(T)` 的紀錄，label 必為 insufficient，而且含 `E-PIT-UNVERIFIED`。
- **FL-8**：`AdjustedSeries` 不是 `PriceBar` 的子類；outlook 與 keylevels 的特徵函式在執行期以 `isinstance` 檢查。
- **FL-9**：`AdjustedSeries.close[anchor] == 原始收盤[T]`，精確相等。
- **FL-10**：`technical.atr` 與重構前逐位相同（golden 測試）；`wilder_atr` 在 `app/` 只有一個定義（grep）。
- **FL-11**：前端非測試檔不得新增簡單平均 ATR 的呼叫點（grep 比對基線）。
- **FL-12**：`app.portfolio.*`、`app.advice.*`、`app.alerts.*`、`app.positions.*`、`app.kelly.*`、`app.playbook.*`，以及 `app.api.{portfolio, positions, settings, alerts, leverage, advice}`，都不可達 `app.dividends.adjust`。
- **FL-13**：forward return 類識別字只能出現在 `app/forecast/scoring.py`（ADR-0012 C-15 修訂後的白名單）。

**排程與逾時**
- **FL-14**：新 job 的 trigger 都帶 `timezone="Asia/Taipei"`。
- **FL-15**：`late` 由 store 計算；`late_cutoff_at` 寫入後不重算；臨界點 08:29:59 為 0，08:30:00 為 1。
- **FL-16**：`late=1` 與 on-demand 的紀錄，永遠不會出現在「當日展望」的 API 回應中。
- **FL-17**：前端非測試檔不得出現 `08:30`、`09:00` 或截止時間的推算（grep）；`{截止時間}` 用 Asia/Taipei 格式化。
- **FL-18**：每個 run 不是有 `forecast_run_end` 列，就是被稽核成 `job_error`。

**缺日與結算**
- **FL-19**：缺日稽核只用觀察日，不呼叫 `TradingCalendar.is_trading_day` 的推定。
- **FL-20**：`late_only` 的缺日列不渲染 TG-b；TG-c 的計數排除 `late_only`。
- **FL-21**：結算三條件缺一就不結算；PA-7 失效觸發的紀錄照常計分。
- **FL-22**：`status_reason` 屬於 D-9.3 的四值封閉列舉，而且與 `status` 的對應固定（表格驅動測試）。
- **FL-23**：更正作業涵蓋所有結算窗與受影響日期有交集的列，不多不少。
- **FL-24**：預測端計分永遠使用原始列。

**銜接**
- **FL-25**：plan 組合價位與估值時，市場 DB 的原始收盤[T] 必須等於估值所用的價格與日期；不一致時，價位缺席，附 `MissingItem(code="E-PRICE-UNUSABLE", source_status="failed_check")`。

**定義與 claim**
- **FL-26**：loader 遇到 `rules_sha256` 不在 `PUBLISHED_RULESETS` 就拒絕載入。
- **FL-27**：寫入紀錄時，logic 雜湊必須等於所屬 claim 的雜湊。
- **FL-28**：m 只增不減；`forecast_validation_snapshot.alpha_star` 等於 0.05÷(max(`m_at_eval`, 8)×K)。
- **FL-29**：只有 `eval_kind=checkpoint` 的列可以使狀態升為 `better_than_baseline`。

**F-2（對應 D-12；逐條對應風控底線）**
- **FL-30**（底線 1）：下架條件的實作與「相鄰兩檢查點的點估計都 ≤ 任一必備基準」等價（表格驅動測試）；程式中不得出現以區間上緣判斷下架的路徑（code review 加測試）。
- **FL-31**（底線 2）：n＝150（族群 250）的退出期限存在，為常數，並有測試釘住。
- **FL-32**（底線 3）：作廢率 >5% 時，F-2 的判定取一般情境與 W 之中比較差的那個。
- **FL-33**（底線 5）：claim 登記遇到相同 logic 雜湊會被 UNIQUE 拒絕；新版的 API 回應附 `predecessor_claim_id` 與 `predecessor_withdrawn_at_n`。
- **FL-34**（底線 5）：`withdrawn_f2` 時，所有對外回應都沒有該 claim 的最新 label（API、提醒 payload、天氣、匯出各一個契約測試）。
- **FL-35**（底線 6）：重新上架只發生在 `checkpoint` 列，而且 §4.3 全部成立。
- **FL-36**（底線 4）：§4.3 與 α\* 的常數屬於 `definition_logic_sha256` 的範圍，任何修改都會產生新定義。
- **FL-37**（底線 7）：C-8 的選擇以常數登記在 dirdef 內，D_v 之後只能往更嚴的方向改，而且要升版。

**閘門與缺項**
- **FL-38**：recorder 在 G-3、G-4 不成立時拒絕寫入排程紀錄（單元測試）；G-1、G-2、G-5、G-6 由 qa 在 PR 描述中核對 CEO 決策紀錄與上線證據。
- **FL-39**：`MissingItem` 的不變式以 model validator 強制；`SourceStatus` 的每個值都有字面（`outlookWording.test.ts::every reason enum has a template`）。
- **FL-40**：政策表 loader 遇到引用 D-15 所列欄位的條件就拒絕（表格驅動測試）。
- **FL-41**：advice 規則中 reduce、stop_loss、take_profit 方向的規則不引用 `unrealized_pnl_pct`（掃描 `default.yaml` 的測試）。

## 測試要求
- **FLT-1**：quant 附錄 C 的 LA-1～LA-7、LG-1～LG-15 全部採用。LG-8 的臨界點依 M-1。
- **FLT-2**：上述每一條 FL 至少有一個測試或 grep 檢查。
- **FLT-3**：颱風假 fixture：
  - `late_cutoff_basis=weekday_assumed` 時，截止線提早，紀錄判為 late；
  - 結算順延到觀察到的交易日；
  - 缺日稽核不會把那天記成缺日。
- **FLT-4**：整檔還原演練：執行 mark-restored 之後，稽核把遺失的 session 記為 `db_restored`。
- **FLT-5**：on-demand 與排程同日：兩筆並存；顯示時優先用排程紀錄；主統計只含排程紀錄。
- **FLT-6**：只改 `explanation` 文字的規則檔：仍屬同一個 claim，計數不重置；改門檻的規則檔：需要新 claim。
- **FLT-7**：M-9 採 P-1 時：跨除息日的前低價位等於還原後的值，`raw_price_at_formation` 正確；`plan_outcome` 換算後的觸價判斷正確。
- **FLT-8**：F2-B 與 F2-A 各一組表格驅動 fixture，重現 quant 表 4 的判定邏輯（不重現機率）。
- **qa-e2e**：Phase 4 上線時，在 375 與 1280 寬度實機驗收逾時、作廢、缺日、下架四種狀態的渲染。

## 失效條件（任一成立，本 ADR 須重審）
- **F-1**：主 DB 超過 1 GB，或證據 JSON 的單筆中位數超過 20 KB。重審證據的儲存方式。
- **F-2**：T1-07 查證盤前委託開始時間不是 08:30。在 D_v 之前修訂 M-1 與 VS-6。
- **F-3**：連續 60 個觀察日的缺日率超過 30%。排程常駐方案失效，升級給 CEO 與 devops-sre。
- **F-4**：需要對預測帳 UPDATE 或 DELETE（例如隱私刪除）。
- **F-5**：預測帳移出主 DB（ADR-0026 F-7）。
- **F-6**：納入上櫃、ETF、美股或 `sector_sub`、`theme`。要新的 PIT 來源，D-4 要重審；新 claim 要計入 m。
- **F-7**：ADR-0012 C-7、C-8，或市場 DB 的 schema 改變。
- **F-8**：m 超過 20。檢定力實質歸零，需要重新檢討 claim 家族的劃分。
- **F-9**：`SourceStatus` 或 `MissingItem` 要被估值、advice 卡或推播採用。另立 ADR 通用化。

## 待決事項
**CEO**
1. 核可 M-1～M-8、M-10、M-11。
2. 單獨裁示 M-9（P-1 或 P-2）。
3. C-8：F2-B（建議）或 F2-A，必須在 D_v 前定案。
4. C-5（決定 M-5 是否成立）。
5. 知悉 D-14 的七道閘門，以及 C-7 的解釋性註記。
6. #10、#15、#16、#17 照舊待決。

**風控**：附件 C 的重送與確認項；FL-30～FL-37 是否完整對應七條底線，請單項核對。

**quant**
- 在凍結版 dirdef 中列出：文字欄位的排除清單、M-3 的常數、C-8 的選擇、F-3 上限。
- 修正 v0.2 對解讀 A 的歸因（風控第 6 項第 1 點）。
- `plan_outcome` 的欄位定義另案提出。

**data-engineer**：VS-6；市場 DB 能否提供逐標的的取得失敗證據（`fetch_failed` 的判定依賴它）；分割、減資的事件來源。

**devops-sre**：常駐方案；把 mark-restored 寫進整檔還原程序。

**dev-lead**：實作順序為 ADR-0026 D-8、D-6 → D-2、D-3 → D-5 → D-4 → D-7、D-8 → D-9 → D-10、D-11 → D-12。

## 未查證事項與作者揭露
- 沒有執行任何程式或測試，也沒有讀任何 DB。
- `panel.py`、`market_panel.py` 的可見性細節與大部分行號，轉引自 R-107，這次沒有重讀。
- 08:30 盤前委託、SQLite 部分唯一索引的行為、每年 220 MB 的量級，都是推論。
- 「在 n＝150 時多數 claim 會退出」是由 quant 的合成表換算，不代表台股的實際情況。

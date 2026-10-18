# ADR-0027：stock-desk 預測紀錄帳——儲存、PIT 輸入、排程與定義登記

- 狀態：proposed
- 日期：2026-10-16
- 決策者：tech-architect（草案）；待 CEO 核可。立案依據：
  - ADR-0026 回報附件 B 的共同說明，以及下一步第 2 點〔事實：`work/reviews/2026-10-16-tech-architect-ADR-0026草案與R-106至R-116.md:55,589`〕；
  - coordinator 保留 0027 給本案〔事實：`work/reviews/2026-10-16-T1-01與T1-02-tech-architect評估.md:4`〕。
- r1 修訂：2026-10-16，依 tech-architect 修訂提案 A-1～A-21
- r2 修訂：2026-10-17，依 tech-architect 修訂提案 A-22～A-41
- r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-54～A-86（含 r3′、r3″、增補與風控 RC‴，套用說明見下一行與「修訂紀錄」）
- r3 系列套用說明：r3、r3′、r3″、增補與風控 RC‴ 於同一次一併套用；衝突時的優先序是 RC‴ > 增補 > r3″ > r3′ > r3（後者被前者覆蓋的部分以前者為準）。狀態維持 proposed。來源（都在 `work/reviews/`）：
  1. r3：`2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md`（A-54～A-86）；風控審查：`2026-10-17-ADR-0027-r3提案審查-風控.md`；
  2. r3′：`2026-10-17-ADR-0027-r3prime補正-tech-architect.md`；風控確認：`2026-10-17-ADR-0027-r3prime單項確認含A96A97與ACB5a-風控.md`；
  3. r3″：`2026-10-17-ADR-0027-r3雙撇併入RC與ADR-0028-A96A97修訂-tech-architect.md`（只取 ADR-0027 的部分；其中 ADR-0028 的 A-96′／A-97′ 與 ADR-0027 FL-25 的 `date_anomaly` fixture 增補不在這次套用範圍）；風控最後確認：`2026-10-17-ADR-0027-r3雙撇與v0.11同批最後確認-風控.md`（RC″-1～RC″-6、N-1、16 項核對）；
  4. 增補：`2026-10-17-ADR-0027-r3雙撇增補RC雙撇與T1至T5-tech-architect.md`（RC″-1～RC″-5、N-1、T-1～T-5、S″-1～S″-3）；
  5. RC‴：`2026-10-17-ADR-0027-RC雙撇增補回送項確認-風控.md` 第二節 RC‴-1～RC‴-4。
  - 不套用：`2026-10-17-ADR-0027修訂提案r3-A54至A79-tech-architect.md`（舊版）、`2026-10-17-ADR-0027-r3雙撇增補RC-tech-architect.md`（舊增補，origin 名稱錯誤）。
  - 沒有新增 A-87 以後的條號；方向統計見「修訂紀錄」。
- 第九、十批衍生待決項套用（2026-10-18，與事先宣告 v0.12 同批）：來源 S1～S9（tech-architect 整合清單，`work/reviews/2026-10-18-ADR-0027-下一批整合與C9-7及Q-3提案-tech-architect.md` 6-1，commit f294cc9），加上風控 2026-10-18 兩份確認（C9-7、Q-3、CS-17 提案確認：commit b55e41f；事先宣告 v0.12 草稿審查：commit 97fbe50）。任何一份都不得單獨 commit；優先序與逐項改動見「修訂紀錄」第九、十批段。狀態維持 proposed。
- A-96″ 增補：2026-10-17，依 ADR-0028 A-96″（FL-25 fixture；A-75 (iv) 官方休市日表的單一定義）。
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
    - （r3，A-79）不修訂；A-78 的根本修法另案（屬 ADR-0012 修訂，要 CEO 核可；data-engineer 先查證）。
  - **ADR-0028（proposed，同批）**：本 ADR 依賴它的 `SessionCalendar` 與 `market_hours` VS-6。依賴方向只能是 forecast → data，不得反向。
    - （r3，A-79）引用 ADR-0028 CS-17 與 R-1（`work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md` §四 R-1）。
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
6. **寫入閘門**：ADR-0027 核可、C-8 定案、定義凍結、08:30 查證、ADR-0026 的守門與備份、`app/forecast/**` 通過 qa-reviewer 與 Codex，全部完成之前，不得寫入任何前瞻紀錄（含 on-demand）。

**否決**
- 預測帳放進市場 DB，或另開獨立 DB（理由見 R-106 與 ADR-0025 E2）。
- `forecast_outcome` 的「NULL 變成值」例外。
- 從 `price_bars_cache` 取個股輸入，以及用 `_hindsight_view` 結算。
- F-2 改成「證明比基準差」，或刪除退出期限（風控 VETO 底線）。
- 用放寬 §4.3 或 α\* 的方式解決解讀 A 的問題。

**最大代價**
- 第一筆前瞻紀錄被六道閘門（G-1～G-6；on-demand 依 G-7 同樣適用）延後。
- B 型會讓尚未驗證的展望最長顯示到 n＝150（大盤 5 日約 3.1 年，見 quant §4.9），全程掛「驗證中」或「未驗證」。
- 價位口徑若改成還原序列（M-9），畫面價位會和券商的未還原 K 線不一致，而且每次除權息都會整組平移。
- 表數多（15 張），寫入規則有一部分在 trigger 裡。

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
| **M-11** | D-6.1 表清單〔`:376-381`〕；F-3〔`:581`〕 | 五張表；F-3 只寫「暫停顯示，查明」 | 新增 10 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`）並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6） | R-106、R-112、R-113；風控第 9 項 |

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
| `app/forecast/views.py`（r1，A-2） | 預測帳**唯一的對外讀取點**：讀 store 與 snapshot，呼叫 `display.py`，回傳 `OutlookView`。`app/api/forecast.py`、`app/api/outlook.py`、`app/api/advice.py`、`app/plan/**`、`app/alerts/**` 都只經過這裡讀 |
| `app/forecast/observed_days.py` | `observed_sessions()`：觀察日集合（A-77 第 3 項）。它要讀 X2 事件，放在 `app/data` 會違反「forecast → data」的依賴方向，所以放在 `app/forecast/`。`observed_sessions(*, as_of)`：`as_of` 之後才寫入的 run、X2 事件、未觀察平日登記都不計入；`as_of` 為 None 時取當下。未扣除 X2 確認日的 (i) 由 `app/data/session_calendar.py` 的 `final_sessions()` 提供，兩者不得混用 |
| `app/outlook/inputs.py` | PIT 輸入：唯讀 `MarketPanelReader`；大盤擷取。σ_d 序列的觀察日由呼叫端（recorder）以參數傳入：`observed_sessions(as_of=cutoff(T))` 的結果（事先宣告 v0.12 V12-19）。`app.outlook.*` 不得 import `app.forecast.*`（recorder 呼叫 outlook，反向會形成循環） |
| `app/outlook/volatility.py`（r2，A-34；純函式） | `sigma_d(log_returns)` 是唯一的 σ 核心，常數 `SIGMA_MIN_VALID`、`SIGMA_FLOOR` 取自 dirdef；大盤、族群、個股共用。只吃已依 V12-19 取好的日報酬序列，不讀觀察日 |
| `app/outlook/basket.py`（r2，A-34；純函式） | 兩個函式：`basket_log_returns(members, series, window)`：依 §2.1 的比值平均式，回傳 `{dates, r_t, V_t, N_t, invalid_days, excluded_members}`；90% 的分母用 \|S_T\|，被排除的權重 > 10% 時輸出 `E-ADJ-COVERAGE`；`basket_hold_ratio(members, series, start, end)`：B1 分子用的買入持有籃子。這個模組不 import 任何 `app.sectors.*`，成員名單以參數傳入 |
| `app/outlook/baselines.py`（r2，A-34） | 發布時點的基準（B1、B2、B3、B4、B6、B8），寫入 `baseline_predictions_json`。B4 ＝ 用 basket.py、以 S_{T−h} 計算的籃子 B1 標籤；依 V7-08：在 T 計算、取 `cutoff(T)` 的資料、P\* 錨定 T；B7、B7r 維持在 validation.py 評估時計算（M-4 (a)）；命名不得使用 forward return 類識別字（ADR-0012 C-15） |
| `app/outlook/missing.py`（純函式） | `MissingItem`、`SourceStatus` |
| `app/dividends/adjust.py::adjust_series_pit` | `AdjustedSeries`（R-108） |
| `app/signals/kernels.py::wilder_atr` | ATR 核心（R-109） |
| `app/api/forecast.py` | `GET /api/forecast/status`；紀錄清單依 scope 拆成三個端點（r3，A-71）：`GET /api/forecast/records/market`、`/sectors/{sector_key}`、`/symbols/{symbol}` |
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
  - （r2，A-29）`forecast_run` 與 `forecast_scope_snapshot`：在同一個交易內寫入（A-25）。
- `forecast_input_series(series_id, content_sha256 UNIQUE, source, source_status, bars_json, captured_at)`：用於大盤與結算路徑，以內容雜湊去重。
  - （r2，A-29）`forecast_input_series`：加 `series_kind ∈ {index_bars, basket_log_returns}`（A-34）。
- `forecast_record`：
  - 識別：`forecast_id`（ULID）、`run_id`、`claim_id`、`scope_kind`、`scope_key`、`scope_reason`、`horizon`、`data_as_of`；
  - 結論：`label`、`range_basis`、`missing_json`（MissingItem 陣列）、`definition_version`、`rules_version`；
  - 判定材料：`band_def`（threshold_snapshot，含 `up_pct`、`down_pct`）、`base_close`（P\*(T)、原始 P(T)、還原狀態）、`evidence_json`、`invalidations_json`、`coverage_json`、`baseline_predictions_json`；
    - （第九批，提案 5；A-65）`band_def.up_pct`、`band_def.down_pct` 的單位是**比值**，例如 0.0107 代表 1.07%，不是百分數。欄位名裡的 `pct` 沿用事先宣告 v0.11 L1083 的名稱，不改名。`forecast_outcome.realized_return` 同樣是比值。
    - 存值是未四捨五入的 IEEE 754 double，由產生 `threshold_snapshot` 的單一函式依事先宣告 v0.11 L505-506 計算寫入。
    - **寫入驗證**（任一項不成立就拒絕）：
      - 兩個值都是有限數；
      - 0 < `down_pct` < 1；
      - `up_pct` > 0；
      - `up_pct` ≥ `down_pct`；
      - 以同一個函式，用同列的 {`K_h`, `sigma_d`, h} 重算，結果逐位相等。
  - PIT 證明：`inputs_max_recorded_at`、`source_run_min`、`source_run_max`、`input_digest`；
  - 時間：`valid_until_session`、`created_at`、`late`（排程紀錄為 0 或 1；on_demand 為 NULL）、`late_cutoff_at`、`late_cutoff_basis ∈ {official, weekday_assumed}`；
  - 更正與雜湊：`supersedes_id`、`correction_reason`、`content_hash`。
  - （r2，A-29）新增 `window_started`：只有 on-demand 列有值，由 store 在寫入時計算 `created_at ≥ late_cutoff_at`；不得由呼叫端傳入，之後也不重算。
  - （r2，A-29）CHECK：`(trigger='scheduled' AND late IN (0,1) AND window_started IS NULL) OR (trigger='on_demand' AND late IS NULL AND window_started IN (0,1))`。
  - （r2，A-29）**所有列（含 on-demand）的 `late_cutoff_at`、`late_cutoff_basis` 都必須非 NULL**，依 D-7.4 的規則在寫入時計算。
- `forecast_outcome`：
  - 識別：`outcome_id`（`INTEGER PRIMARY KEY AUTOINCREMENT`，RC″-2）、`forecast_id`；
  - 結算：`resolved_at`、`settlement_date`、`start_price_json`、`end_price_json`、`window_factors_json`、`realized_log_return`、`realized_z`、`realized_label`、`realized_return`、`hit`、`baseline_hits_json`；
  - 診斷：`diag_open_based_json`、`diag_last_close`、`diag_basket_with_excluded`（風控第 8 項）、`basket_excluded_members_json`、`index_return_diag`；
  - 期間路徑：`invalidation_triggered`、`invalidation_first_hit`、`mae`、`mfe`；
  - 稽核：`input_digest_recomputed`、`digest_match`；
  - 狀態：`status ∈ {resolved, unresolvable_missing_data, excluded_corporate_action}`、`status_reason`（D-9.3）；
  - 更正：`supersedes_id`、`correction_job_id`、`correction_causes`（第十批，提案 1；A-65、A-77 第 8 項）；
    - `correction_causes`：JSON 陣列，封閉列舉（`OUTCOME_CORRECTION_CAUSES`，見 D-11.4 第 11 點 (h)）、排序固定、不重複。
      - `supersedes_id IS NULL` 的列必須為 null；`supersedes_id IS NOT NULL` 的列必須非空。由寫入函式驗證；列舉外的值、空陣列、或與 `supersedes_id` 不一致，都拒絕寫入。
      - 這個欄位和 `forecast_record.correction_reason` 無關，兩者不得互相引用或 join。
  - 唯一性：`UNIQUE(forecast_id) WHERE supersedes_id IS NULL`，以及 `UNIQUE(supersedes_id)`。
- **新增 `forecast_correction_job` 與 `forecast_correction_job_end`**（第十批 R10-1；比照 `forecast_run`／`forecast_run_end`），兩張都只增不改：
  - `forecast_correction_job(correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT, triggers_json, recheck_range_json, started_at)`：作業開始時寫入。`triggers_json` 必須非空，每一項都帶來源參照（`event_id`、查證紀錄 ID、`run_id` 或因子修訂的參照）；沒有觸發就拒絕執行。
  - `forecast_correction_job_end(correction_job_id PK, rechecked_count, changed_count, rejected_count, void_late_data_count, ended_at)`：作業結束時寫入。沒有 end 列代表作業中斷；這時該作業的 `recheck_range_json` 由下一個作業完整重跑，qa 核對涵蓋率。`void_late_data_count` 是作廢之後才補到資料的筆數（見 D-11.4 第 11 點 (h)「作廢列不因之後補到的資料而 supersede」；事先宣告 v0.12 V12-20），不屬於 `rejected_count`。
  - `rejected_count` ＞ 0 時記 WARNING，筆數在 §4.2 揭露。寫入函式拒絕的列不得靜默略過。
  - 這兩張表落實事先宣告 §6.4 第 2 點；`forecast_outcome.correction_job_id` 必須指向 `forecast_correction_job`。
- `forecast_replay`：結構與 `forecast_record` 相同，另加 `freeze_commit`、`replay_session`。永遠不與前瞻紀錄合併。
- `forecast_gaps(gap_id, session, claim_id, scope_key, reason, detected_at, run_id NULL, UNIQUE(session, claim_id, scope_key))`：`scope_key = '*'` 代表整個 claim。
- `forecast_claim_registry`（D-10）、`forecast_validation_snapshot`（D-11）。
- `forecast_ledger_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, kind ∈ {db_restored, f3_resume_approved, pit_violation_confirmed, replay_review_approved, x2_confirmed_non_session, session_calendar_conflict, unobserved_weekday}, payload_json, recorded_at)`（r3″；RC″-2；`unobserved_weekday` 依風控 2026-10-18 Q3-7 加入）：`pit_violation_confirmed` 的 payload 帶 `forecast_id` 與重算值（r1，A-8）。
- `plan_record(plan_id, run_id, symbol, market, mode, position_action, reasons_json, levels_json, conditions_json, quantity_json, policy_version, created_at)`：含成本與股數，只存在本機。
  - **新增欄位**（r1，A-12）：
    - `outlook_display_state`（JSON，以 horizon 為鍵：`{claim_id, forecast_id|null, display_state, availability, unavailable_reason}`）；
    - `outlook_condition_basis ∈ {evaluated, unavailable}`。
  - **新增欄位**（r2，A-29）：
    - 加 `data_as_of`，以及 **`UNIQUE(symbol, market, data_as_of)`**，不含 `policy_version`。每個 (symbol, T) 只有一份 plan；升 `policy_version` 只對還沒有 plan 的 T 生效。
    - 加 **`in_holdings_or_watchlist_at_plan BOOLEAN NOT NULL`**：在同一次 run 計算 plan 時，讀庫存與自選的 store 取得。這是 LM-88 守門的唯一來源。
    - `outlook_display_state` 的 JSON 加兩個鍵 `consumer_surfaces`、`restricting_surfaces`。
- `plan_outcome`：表與只增不改的規則由本 ADR 固定；欄位定義另案處理（quant §6.5，見待決）。

### D-4 PIT 輸入（R-107）
1. **TWSE 上市普通股**：讀 `market_daily_bars` 的 PIT 視圖。
   - 可見性規則在 `panel._visible` 之上加定案下限：`session_date ≤ T`、`recorded_at ≤ cutoff(T)`、只取 ok run、依來源優先序〔轉引 R-107：`panel.py:886-922`〕。
   - **定案下限**（r3，A-78；消費端防護）：對 session s 的 bars，只認 `is_final(TW, s, recorded_at)` 為真（ADR-0028 CS-17）的 ok run 寫入的 bars。適用 D-4.1 PIT 視圖、D-7.3 (i)、D-8.1 (i)、D-9.2 個股與族群成員結算。不改 `pit_snapshot`。
     - **後果**：之後若沒有定案後的 run 補寫，約 60 個交易日內的紀錄可能是證據不足，或作廢。
     - **根本修法**屬於 ADR-0012 修訂，要 CEO 核可；data-engineer 先查證。
   - 新增以代號為範圍的唯讀方法，並補上等價測試。
2. **還原用的除權息事件**：取 `pit_dividend_announce_rows` 的 PIT 視圖，不讀主 DB 的 `dividend_events`（upsert）。
3. **PIT 證明**：`inputs_max_recorded_at`，以及 `source_run_min`、`source_run_max`。超過 cutoff 就輸出 insufficient，缺項代碼為 `E-PIT-UNVERIFIED`。
4. **上櫃、ETF、美股**：一律 insufficient（`E-SCOPE-OTC`、`E-SCOPE-TYPE`）。
5. **大盤**：把實際用到的 bars 寫進 `forecast_input_series`，並揭露 `index_source_status=backup`。
6. **ADR-0012 C-7 的解釋性註記**（CEO 知悉，不修訂）：
   - C-7 所說的「持倉資料鏈」，指請求觸發、逐代號的鏈：`load_bars → price_bars_cache → 估值`。
   - 展望鏈是另一條（排程，加上專用的 on-demand 端點），而且反向也不得讀 `price_bars_cache` 的個股 bars。
   - `/api/advice` 與 plan 只經 `app.forecast.views` 讀取預測帳，不得 import `app.forecast.store`（r1，A-3）。
7. **族群成員輸入**（r2，A-34）：
   - 每個成員讀 D-4.1 的 PIT 日線與 D-4.2 的 PIT 除權息，經 `adjust_series_pit(anchor=T)` 得到一條 `AdjustedSeries`；
   - S_T、S_{T−h} 由 `app/outlook/inputs.py` 從族群的 store 唯讀取得，不經過動能計算（維持 D-10.5，m 不合併）；
   - 成員層的 `E-ADJ-COVERAGE` 在 inputs.py 判定，以 `MissingItem` 帶出成員明細。
   - **輸入存檔**：
     - 籃子日報酬序列寫進 `forecast_input_series`，`series_kind=basket_log_returns`，以內容雜湊去重（同一個 T、同一個族群的 B4 可以共用）；
     - record 的 `evidence_json` 引用它的 `content_sha256`；`input_digest` 涵蓋成員的 PIT 列與這個雜湊；
     - 稽核時從成員 PIT 列重算，必須逐位相同。
   - **狀態**：σ_d 定稿條文仍然沒有生效，要依事先宣告 §2.1 的順序經過 data-engineer、qa（含 Codex）、風控，最後由 CEO 在 C-4 凍結。B4「該股所屬族群」以 T−h 的 PIT classification 快照判定，也就是建立 S_{T−h} 的同一份快照（事先宣告 v0.10 V10-05）。
8. **快取 bar 消費者的封閉列舉**（r3，A-76）：
   - **`CACHE_BAR_CONSUMERS`**：
     1. D-7.3 的大盤 T 日 bar；
     2. D-4.5 的大盤輸入序列；
     3. D-9.2 的大盤結算路徑；
     4. FL-25 的估值價格；
     5. `plan_outcome` 的觸價價格（另案定義時歸入）。
   - 每一項只能經 `is_final_bar` 篩選後取得。不符合的列視為缺，依各自的既有規則處理。新增消費者要先修訂本點。
   - quant 確認這些是否屬於事先宣告的 PIT 輸入；若是，登記為補定義（收緊），D_v 前完成。
   - 驗證見 FL-62。

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
2. **執行順序**：記錄 → 結算 → 缺日稽核 → 驗證快照 → plan（政策表）。T 的 plan 一律使用 `computed_for_session = T` 的 daily snapshot，也就是 T+1 開盤前畫面上用的同一份（r1，A-4）。
3. **決策日 T**（r3，A-75；整點取代；候選 T 的四項與處理依 r3′、r3″）：
   - **候選 T** ＝ 市場 DB 中最新一個有 ok bars run 的 session。候選 T 必須同時滿足四項：
     - (i) A-78 的 run 下限，也就是 T ∈ D-8.1 (i)；
     - (ii) 大盤 T 日 bar 是定案列；
     - (iii) **T 不是 X2 確認日**；
     - (iv) T 不是週末，也不是已接入官方休市日表所列的休市日（風控 2026-10-17 單項確認）。
   - **`is_final_bar`** 只有一個定義，放在 `app/data/session_calendar.py`，引用 ADR-0028 CS-17 與 R-1：
     - `is_final(TW, T, as_of, fetched_at)` 為真（ADR-0028 CS-17），而且 `max(as_of, fetched_at) ≤ now`；
       - `now` 是 store 時鐘（D-2 第 3 點）的讀值，由 recorder 以參數傳入：`is_final_bar(row, *, now)`，沒有預設值。
       - `session_calendar.py` 不讀任何時鐘（grep 不得出現 `datetime.now`、`date.today`、`time.time`），也不 import `app.forecast.*`。
       - 每一次判定候選 T，讀一次時鐘；(ii) 經強制重抓之後重讀一次。
     - 帶時區；
     - 非示範資料；
     - 沒有 `OHLC_INVALID`。
   - **(ii) 不成立時**：經 `app.services.index` 強制重抓一次（寫入仍經 `service.py`）；仍不成立，或 (i) 不成立 → 該 session 記 `inputs_not_ready`；**不得退回更早的 session，也不得使用暫定值。**
   - (iii) 或 (iv) 不成立 → 該 session 記 `inputs_not_ready`，不得退回前一個 session。依 A-77 第 5 項，(iii) 只在 A-77 第 12 項的情形下成立（d 經 X2 確認之後才進入 (i)，又成為候選 T）；其餘情形保留為縱深防禦，以測試斷言。
   - **(i) 成立而且 (iv) 不成立時**：候選 T 依 (i) 必定 ∈ D-8.1 (i)，所以這必然是 A-77 第 5 項的同一種證據矛盾。
     - 記 WARNING，寫入 `session_calendar_conflict`（`origin = candidate_t`）；
     - 一併計入 A-77 第 5 項的揭露與根因查證。
   - (iv) 的「週末」部分受 A-77 第 9 項（F-8）約束：查證若發現週末交易日，(iv) 與 A-77 第 2 項的週末部分同一批修訂，並送風控。
   - （A-96″，K-10，補定義（收緊））**官方休市日表的單一定義**：
     - A-75 (iv) 與 A-77 第 2、4 項所稱的「已接入官方休市日表」，和 ADR-0028 `OfficialSessionCalendar`（T1-13）使用同一份來源、同一個函式定義，涵蓋年度也相同（ADR-0028 VS-5）。超出涵蓋年度時，兩邊同樣視為沒有官方休市日。
     - 這個函式只定義一次，暫定為 `official_holidays(market, year) -> frozenset[date] | None`。None 表示該年不在涵蓋範圍內，或尚未接入。名稱與所在模組由 T1-13 決定，但要遵守 ADR-0028 CS-1、CS-19、CS-25 的 import 限制。
     - A-75 (iv)、A-77、`OfficialSessionCalendar` 都只呼叫它；休市日清單不得出現第二份（grep／AST，比照 ADR-0028 CS-21、CS-25）。
   - （K-11）本句只統一休市日清單。A-75 (iv) 的週末部分不受官方日曆影響，仍依 A-77 第 9 項（F-8）處理；不得讀成官方日曆認定的週六補行交易日可以成為候選 T。
   - （K-12）休市日表的內容或涵蓋年度有任何改動，依 ADR-0028 CS-21 通則判斷方向，判斷不了的一律視為放寬。移除休市日或縮小涵蓋年度，必須送風控。
   - `app.services.index` 新增逐列回傳 `as_of`、`fetched_at`、`source` 的方法〔事實：`cache.py:109` 現行只帶最舊的 `fetched_at`〕。FL-5 不變。
   - `forecast_input_series.bars_json` 每一列都帶這三欄，並納入雜湊。
   - 驗證見 FL-61、FL-19 (e)。
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
   - **去重**（r3，A-73）：
     - 同一個 (symbol, horizon, T, definition_version, rules_version)，on-demand 原始列只寫一筆（M-6 的唯一索引已含 `trigger`）。
     - POST 的處理依序是：有排程紀錄 → 回傳排程紀錄；否則有既有的 on-demand 列 → 回傳既有列，`window_started` 讀已存值；否則寫一筆。並發撞到 UNIQUE 時重讀，不回 5xx。
     - FL-52b (10)：同 T 重查時回傳同一個 `forecast_id`；兩個並發請求只產生一列。
   - on-demand 紀錄使用者看得到，有兩個地方（r1，A-13）：
     - `POST /api/outlook/symbols/{symbol}` 的回應（附 PA-4 標示）；
     - `GET /api/forecast/records/symbols/{symbol}`（帶 `trigger=on_demand`；r3，A-71）。
   - 兩處都經過 D-11.4 第 5 點的閘門：所屬 claim 為 `withdrawn_f2`、`suspended_f3`、`gated` 時，不出現 label。
   - （r3，A-71）D-7.8 第 8 點全文與 FL-52b (9) 所稱「紀錄清單」，指 symbol 端點（`/symbols/{symbol}`）。
   - （r2，A-36）紀錄清單另外依 D-11.4 第 11 點處理；
   - （r2，A-36）`POST /api/outlook/symbols/{symbol}` 登記 `SERVES = {symbol_detail}`；
   - （r2，A-36）on-demand 紀錄永遠不進 policy（D-11.4 第 6 點）。
   - **（r2，A-36；r2'' 依風控 2026-10-17「追加一」的 4 項 required 修正）`POST /api/outlook/symbols/{symbol}` 的處理採 (ii)：比照紀錄清單**（風控 2026-10-17 單項確認，APPROVE WITH CONDITIONS）。
     - 不採 (i)「顯示 label，同區塊附『預測自 {T} 收盤起算，期間已開始』」。理由：所有顯示面只用一條規則；與 PA-6、D-10 一致；不需要多一個揭露片段。
   - **1. 回應形狀依紀錄狀態分三種，一律採封閉 schema（白名單）：**
     - (a) `window_started = 0`、尚未結算：照常經過 D-11.4 第 5 點的閘門；`availability = evaluated` 時帶 label，附 PA-4。
     - (b) `window_started = 1`、尚未結算（下稱「期間已開始、待結算」）：
       - **API 回應本體不得含任何帶方向的欄位。** 這是對 API 本身的要求（API 就是顯示面，`work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md` B-3），不只是前端不渲染。
       - 不得出現的欄位與內容，至少包括：
         - `label`、`range_basis`；
         - 天氣（`OutlookWeather`），以及任何色彩或色調代碼；
         - 方向詞；
         - 以方向表述的失效條件（`invalidations_json`）；
         - `evidence_json`（整個不回，不只其中的標籤）；
         - `baseline_predictions_json`（含基準的方向標籤）。
       - 回應只能含以下白名單欄位，其餘一律不得出現（schema 設 `extra="forbid"`／`additionalProperties: false`）：`forecast_id`、`trigger`、`scope_kind`、`scope_key`、`horizon`、`data_as_of`、`created_at`、`valid_until_session`、`window_started`、`settled`（固定 false）、`availability`（固定 `"unavailable"`）、`status_fragment_id`、`disclosure_fragment_ids`（含 PA-4）、`in_eligible_set`、`exclusion_reasons`。
       - `label` 這個鍵本身不得出現，不是給 null。
       - 白名單要增列欄位，須修訂本點並送風控。
     - (c) 已結算（該 `forecast_id` 有 `forecast_outcome` 列）：依第 4 點。
   - **2. 狀態片段：**
     - (b) 的狀態片段，意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」。
     - 逐字字面為 LM-106（`work/reviews/2026-10-17-新定位第六批字面逐字審-LM94至LM115-風控.md`）；守門 R1、R2 見 D-11.4 第 11 點。
     - POST 回應與紀錄清單用同一個片段 ID（暫定常數 `RECORD_STATUS_ONDEMAND_PENDING`），不另立 POST 專用片段。
     - **本點第 4 點與 A-62 R2 第 6 點所列片段核可之前，FL-52 (d) 失敗**，依 FL-45 (c) 的效力鏈：G-6 不成立 → 不得寫入排程紀錄 → D_v 被擋住。on-demand 依 D-14 的 G-7 同樣受 G-6 約束，也不得寫入。
     - 不得用暫定字面、placeholder、skip 或 xfail 讓測試通過。
   - **3. 資料日期：**
     - (b) 的 schema 中 `data_as_of`（T）為必填、非 NULL。
     - 前端在狀態片段的同一區塊，以既有的「資料截至」徽章呈現；字面沿用 ADR-0009 D-5 的「資料截至 {日期}」家族，日期依年份規則。
     - 徽章日期取這筆紀錄的 `data_as_of`。不得借用頁面上其他區塊的徽章，也不得取 `price_bars_cache` 的 `last_bar_date`（展望鏈與持倉鏈的資料源不同，見 Consequences）。
   - **4. 結算之後：**
     - label 只能以「已結算紀錄＋實際結果」的形式出現，不得呈現為目前展望。
     - 回應中 label 只放在 `settled_record` 物件內。同一物件必須同時帶 `settlement_date` 與結算結果：`status = resolved` 時為 `realized_label`、`hit`。
     - 頂層不得有 `label`。也不得出現在任何「目前展望」的欄位或呈現，包括天氣、首層展望、當日展望欄位、提醒、匯出。FL-16 照舊。
     - 前端在同一區塊同時渲染「已結算」標示與實際結果，所用字面必須是已核可片段。核可之前，已結算的 on-demand 紀錄不顯示 label（fail-closed）。
     - outcome 為作廢時，依 D-11.4 第 11 點 A-62 R2（風控 2026-10-17 C-3）。on-demand 紀錄一律不屬於 E，所以**不得用 LM-38**，改用不帶 W 子句的作廢變體＋LM-110。變體與「原本的預測（已作廢）」框架核可之前，不顯示 label，FL-52 (d) 失敗。
     - 本點適用所有已結算的 on-demand 紀錄（`window_started` 為 0 或 1 都一樣），POST 回應與紀錄清單相同。
   - 選 (ii) 的代價見 A-35。
9. 主機常駐由 devops-sre 負責；API 永遠不執行排程預測。

### D-8 缺日（R-112；字面用 TG-b）
1. **觀察日**（r3，A-77；整點取代。下列第 1～12 項引用時稱「A-77 第 n 項」）：
   1. **定案後 session 集合 (i)**：有 ok bars run、而且 `is_final(TW, d, run.recorded_at)` 為真（ADR-0028 CS-17）的 session d（A-78）。本 ADR 與事先宣告都只引用這一個定義。不得另寫時點比較。
      - 由 `app/data/session_calendar.py` 的純函式 `final_sessions(run_stamps, *, market)` 提供；
      - `run_stamps` 由呼叫端經 `MarketPanelReader` 讀出，函式本身不讀市場 DB（ADR-0028 CS-19）；
      - `final_after(` 的呼叫位置依 ADR-0028 CS-17（只有 `is_final` 與只寫稽核值的 `final_session_evidence`）；本 ADR 其他位置一律經 `is_final` 判定。
   2. **大盤定案列日期 (ii)**：大盤有 `is_final_bar` 列（A-75，排除示範資料）的日期，**扣除週末與已接入官方休市日表所列的休市日**。週末或官方休市日的大盤列，一律不得經 (ii) 成為觀察日。
   3. **觀察日 ＝〔(i) ∪ (ii)〕− X2 確認日 − 已登記的未觀察平日。** 不用週一至週五推定。
      - 第 1 項的 (i) 本身不扣除 X2 確認日。X2 判定（第 4、5 項）、第 12 項的偵測、A-75 (i)，都讀未扣除的 (i)。
      - 單一函式：未扣除的 (i) 由 `session_calendar.py` 的 `final_sessions()` 提供，觀察日由 `observed_sessions()` 提供，兩者不得混用。
      - 依第 5 項，X2 確認當下 d ∉ (i)，所以就 X2 確認日這一項而言，上式在確認當下與 fd87063 版（事先宣告 v0.11）的「(i) ∪〔(ii) − X2 確認日〕」相同，只在第 12 項的情形下不同。未觀察平日那一項見第 10 項：登記當下與不扣除未觀察平日的式子相同，只在登記之後 d 因補寫進入 (i) 或 (ii) 的情形下不同。
   4. **X2 的單一定義在事先宣告 §6.3「大盤指數序列」第 2 點。** 本點只規定 X2 能用的輸入：
      - X2 的對照日曆 ＝ 本點第 1 項的 (i)，加上正面休市證據（週末；已接入、而且 d 在其涵蓋範圍內的官方休市日表）。
      - 不含任何指數 bar，也不含受檢的那根 bar；不讀本點第 3 項的觀察日，也不讀 ADR-0028 `ObservedSessionCalendar`。
      - 官方休市日表的接入屬於 ADR 決策（事先宣告 §9.3 第 18 點 (e)、(i)）；接入之前，正面證據只有週末。
   5. **X2 確認的必要條件含 d ∉ (i)**（風控 2026-10-17 單項確認）。d ∈ (i)、又有正面休市證據時，屬於證據矛盾，一律維持異常待查證，不論獨立來源的結果如何。這時 d 仍經 (i) 是觀察日，這一列照原值計分。
      - 記 WARNING，寫入 `forecast_ledger_events.kind = session_calendar_conflict`，交 data-engineer 查根因。
        - payload：`session_date`、`evidence ∈ {weekend, official_holiday, independent_source_absent, registered_unobserved_weekday}`、`origin ∈ {x2_check, candidate_t, post_x2_final_run, post_unobserved_backfill}`（`post_unobserved_backfill` 依風控 2026-10-18 Q3-7 加入，見第 10 項）、受檢 bar 的參照。`independent_source_absent` 只用於 `origin = post_x2_final_run`（見第 12 項）。`registered_unobserved_weekday` 只用於 `origin = post_unobserved_backfill`（見第 10 項）。
      - **查證照跑**：矛盾列照樣走事先宣告 §6.3「查證程序」①～③，每次查詢都照常新增查證紀錄（查不到也記），由 qa 核對涵蓋率。
        - **但查證結果不改變這一列的狀態**：不得確認 X2，不得移出觀察日，不得寫入 `x2_confirmed_non_session`。
        - 任何程式路徑都不得依查證紀錄改變 d 的觀察日身分（FL-19 (d) 斷言）。
      - **揭露**：`session_calendar_conflict` 的筆數（以不同的 `session_date` 計，並依 `origin` 分列）在驗證報告 §4.2 單獨揭露，不得併入其他異常待查證筆數。
      - **不自動解除**：要解除矛盾，只能修訂本點並送風控。不得依時間經過、查證次數或查證結果自動解除。
      - 第 3 項直接從觀察日移除 X2 確認日；第 5 項保證確認當下 d ∉ (i)。
   6. **平日 d 只出現在 (ii)、不在 (i)**（例如自己的排程停擺，或只有定案前的 run）：X2 只有 (iii) 成立，不得直接確認，列為異常待查證，查證路徑依事先宣告 §6.3「查證程序」。待查證期間 d 照常是觀察日。
   7. **X2 確認的登記**（風控 2026-10-17 RC″-5）：只增不改，寫入 `forecast_ledger_events.kind = x2_confirmed_non_session`。**這筆事件本身就是 X2 的判定紀錄**；`basis = direct` 沒有查證紀錄，以此為準（事先宣告 §6.3 判定紀錄、R-C ④）。
      - **payload**：
        - `session_date`；
        - `basis ∈ {direct, verified}`；
        - `verification_ref`：查證紀錄的參照；
        - `trigger ∈ {weekend, official_holiday} | null`；
        - `checked_bar_ref`：受檢 bar 的參照；
        - `holiday_table = {version, coverage_start, coverage_end} | null`：`trigger = weekend` 時為 null；`trigger = official_holiday`，以及 `basis = verified` 時，記判定當下已接入的表（尚未接入時為 null）；
        - `set_i_check = {runs: [{run_id, recorded_at}], final_after}`：判定當下 d 的 ok bars run 清單，以及 `final_after(TW, d)` 的值（ADR-0028 CS-17）。
          - 改由 `session_calendar.py` 的純函式 `final_session_evidence(run_stamps, d, *, market)` 產生；寫入函式不得自行呼叫 `final_after(`。
          - `final_after(` 的呼叫位置依 ADR-0028 CS-17（風控 2026-10-18 單項確認）：`final_session_evidence` 只把 `final_after` 的回傳值原樣寫入稽核 payload，不參與任何判定；X2 寫入函式判定「d ∉ (i)」只經 `final_sessions()`，不得拿 `set_i_check.final_after` 比較時戳。本項依賴 ADR-0028 CS-17 的同步修訂；兩者同一次 push，ADR-0028 的 commit 在前。
      - 判定時間就是事件的 `recorded_at`，不另設欄位。
      - **寫入函式在同一個交易內驗證**，任一項不成立就拒絕寫入：
        - `basis = direct` ⇒ `verification_ref` 為 null、`trigger` 非 null，而且重算後 d ∉ D-8.1 (i)。另外，`trigger` 要和 d 相符：`weekend` ⇒ d 是週六或週日，而且 `holiday_table` 為 null；`official_holiday` ⇒ d 在 `holiday_table` 的涵蓋範圍內，而且列為休市日。`official_holiday` ⇒ d 是平日（RC‴-2）。
        - `basis = verified` ⇒ `verification_ref` 非 null，指向 `session_date = d`、結果是「來源沒有這一天」的查證紀錄，而且該列只有 X2 偵測的 (iii) 成立。所以 **`trigger` 必須為 null**：d 不是週末，也不是已接入表列的休市日。
        - `set_i_check` 由寫入函式在重算 (i) 時自行填入，不接受呼叫端傳入（比照 D-2 第 3 點）。
        - 重算經 `MarketPanelReader`（唯讀）讀市場 DB，在寫入交易持有期間執行。市場 DB 是另一個檔案，所以不構成跨檔原子性；之後 d 才進入 (i) 的情形，見第 12 項。
      - 觀察日在查詢時排除這些日期。已寫入、日期是 d 的 `forecast_gaps` 等紀錄不刪不改，查詢時一併排除（回覆事先宣告 §9.3 第 18 點 (i) 的註記方式）。
   8. **順延的稽核欄位**（對應事先宣告 R-C）：每一筆順延的結算列，以及結算後才確認、以 supersede 新增的列，`forecast_outcome` 都要帶 `x2_shift_json = {original_t_plus_h, removed_dates, shifted_t_plus_h, x2_event_ids}`，可為 null，只增不改。
      - （第十批，提案 2）**`x2_shift_json` 一律記累計值**：
        - `original_t_plus_h` ＝ 不扣除任何 X2 確認日時的 T+h；
        - `removed_dates`、`x2_event_ids` ＝ 窗內所有已確認的移除日及其事件；
        - `shifted_t_plus_h` ＝ 本列的 `end_price_json.session_date`。
        - 先順延、後來又因其他原因 supersede 的列，同樣帶累計值，不得改成 null。§4.2 的順延筆數依同一計數單位：每筆預測只計一次：更正鏈中任一列的 `x2_shift_json` 非 null 就計入（比照風控 v0.12 確認 Q12-1）。
      - （第十批 R10-5）凡 `x2_shift_json` 非 null 的 `resolved` 列（含非 supersede 列），寫入時驗證 `x2_shift_json.shifted_t_plus_h == end_price_json.session_date`，不成立就拒絕寫入。
   9. **F-8（凍結前，待 data-engineer 查證）**：「週末」作為正面休市證據，前提是前瞻期與重放期都沒有週末交易日。
      - 查證若發現週末交易日：官方日曆列為交易日的週末，不構成正面休市證據；官方表沒有涵蓋的期間，週末的大盤列只能列為異常待查證。這時第 2 項「週末一律不得經 (ii) 成為觀察日」的週末部分要和事先宣告同批修訂，並送風控。
      - 查證若沒有發現：把查證依據與涵蓋期間寫進本點與事先宣告。
   10. **未觀察平日**（風控 2026-10-17 疑義裁定回送 Q-3；A 案，風控 2026-10-18 C9-7 與 Q-3 提案確認）：d 同時滿足以下各項：是平日（Asia/Taipei 週一至週五）；不是已接入、而且涵蓋 d 的官方休市日表所列的休市日；d ∉ (i)；d ∉ (ii)；而且已經有晚於 d 的觀察日。
      - **偵測**：缺日稽核以單一函式 `unobserved_weekdays(start, end)`，逐日檢查 [D_v, 最新觀察日] 內的平日。這裡列舉平日只是為了產生候選，不得用來推定觀察日（FL-19 不變）。
      - **登記先於使用**：任何讀取觀察日集合（`observed_sessions()`）、並寫入主 DB 的作業（排程結算、更正作業、缺日稽核、X2 確認寫入），在讀取之前，要在同一個寫入交易內先呼叫 `unobserved_weekdays`，完成 [D_v, 最新觀察日] 內的登記。登記失敗時，該作業不寫入（fail-closed），記 WARNING。
      - **成立時**：
        - 記 WARNING。
        - 寫一筆 `forecast_ledger_events.kind = unobserved_weekday`，歸入 `E_NEUTRAL_EVENTS`。
        - payload：`session_date`；`holiday_table = {version, coverage_start, coverage_end} | null`；`holiday_coverage ∈ {table_absent, not_covered, listed_as_trading_day}`；`run_evidence = {prefinal_ok_runs: [{run_id, recorded_at}], any_run}`；`index_evidence ∈ {no_row, not_final, demo_only, ohlc_invalid}`；`detected_by_run_id`。
        - payload 由寫入函式自行填入，不接受呼叫端傳入。同一個 `session_date` 只寫一次。
      - **固定排除**：第 3 項為「觀察日 ＝〔(i) ∪ (ii)〕− X2 確認日 − 已登記的未觀察平日」。
        - 登記當下 d ∉ (i) ∪ (ii)，所以上式在登記當下與不扣除未觀察平日的式子「〔(i) ∪ (ii)〕− X2 確認日」相同；只在登記之後 d 因補寫進入 (i) 或 (ii) 的情形下不同。
        - 登記之後，d 即使因補寫進入 (i) 或 (ii)，也不回到觀察日。這時寫 `session_calendar_conflict`，新增 `origin = post_unobserved_backfill`；程式不得自動解除。
        - **`post_unobserved_backfill` 的 payload**：`session_date`；`origin`；`evidence = registered_unobserved_weekday`；`unobserved_event_id`（登記該日的 `unobserved_weekday` 事件）；`backfill_via ⊆ {set_i, set_ii}`，非空；
          - 進入 (i) 時，帶使 d ∈ (i) 的 ok run 中 `run_id` 最小者的 `run_id`、`recorded_at`（比照第 12 項）；
          - 進入 (ii) 時，受檢 bar 的參照指使 d ∈ (ii) 的大盤 `is_final_bar` 列（`source`、`as_of`、`fetched_at`，比照第 7 項的 `checked_bar_ref`）；只進入 (i) 時為 null。
          - payload 由寫入函式自行填入，不接受呼叫端傳入；偵測在第 10 項「登記先於使用」的同一個交易內完成。
          - **寫入函式在同一個交易內驗證**，任一項不成立就拒絕寫入（風控 2026-10-18 E8-1）：
            - `origin = post_unobserved_backfill` ⇔ `evidence = registered_unobserved_weekday`（雙向；其他 origin 不得用這個值，這個 origin 也不得用其他值）；
            - `unobserved_event_id` 指向一筆已存在、`kind = unobserved_weekday`、而且 `session_date` 相同的事件；
            - `backfill_via` 非空，而且和重算結果相符：`set_i` ∈ `backfill_via` ⇔ d ∈ `final_sessions()`（經 `is_final`，ADR-0028 CS-17）；`set_ii` ∈ `backfill_via` ⇔ d ∈ (ii)；
            - 參照欄位與 `backfill_via` 一一對應：`set_i` 不在 `backfill_via` 時，(i) 的 `run_id`、`recorded_at` 為 null；`set_ii` 不在時，受檢 bar 的參照為 null。
          - 同一個 (`session_date`, `origin`) 只寫一次。`backfill_via` 與參照欄位記的是偵測當下的狀態；之後 d 再經另一個集合進入，也不另寫、不改寫，所以這兩個欄位不代表完整的補寫歷程，根因查證要另讀市場 DB。§4.2 ④ 以日數計（風控 2026-10-18 E8-2）。
        - 不寫缺日列，不觸發 §6.4 更正，不改任何已寫入的紀錄。
      - **§4.2 揭露**（quant 登記）：
        - ① 未觀察平日的日數，依 `holiday_coverage` 分列，日期全部列出；
        - ② 其中有定案前 ok run 的日數（`run_evidence.prefinal_ok_runs` 非空）。這類日子候選 T 可能曾因定案條件不成立而記 `inputs_not_ready`，但不會有缺日列；
        - ③ 結算窗 [T, T+h] 跨越未觀察平日的 outcome 筆數（鏈尾，逐列數出），依該日的 `holiday_coverage` 分列；
        - ④ `post_unobserved_backfill` 的日數。
        - 以上都不得併入缺日數，也不得併入 `session_calendar_conflict` 其他 origin 的筆數。
        - `holiday_coverage = listed_as_trading_day` 的未觀察平日（官方表列為交易日，卻沒有任何定案資料），每一筆都交 data-engineer 查根因，比照 `session_calendar_conflict` 的根因流程；§4.2 ① 對這一類另列根因查證狀態。
      - **失效條件**：官方休市日表接入之後，只要出現一筆 `listed_as_trading_day` 的未觀察平日，固定排除對這一類是否仍適當，要送風控重審。重審之前照本項處理，不得由程式自動改變。
   11. 觀察日集合可能因為後來的 X2 確認而回溯縮小。已寫入的 snapshot 不改；之後的 snapshot（含 F-3 逾時率的 60 日窗）用新集合。結算端依事先宣告 §6.4 supersede。觀察日集合不因第 12 項的情形而回復。
   12. **X2 確認之後，d 才進入 (i)（風控 2026-10-17 N-1；第九批提案 3 甲案）**
      - 情境：`x2_confirmed_non_session` 寫入之後（相關列可能已依第 8 項順延），同一個 d 才出現 `is_final(TW, d, run.recorded_at)` 為真（ADR-0028 CS-17）的 ok bars run。這時 d 屬於未扣除的 (i)，和已寫入的事件及 `x2_shift_json` 的前提（d ∉ (i)）矛盾；依第 3 項，d 不回到觀察日。
      - **偵測**：每日結算排程（事先宣告 §6.3「觸發」）用單一函式，對每一筆 `x2_confirmed_non_session` 檢查 d 是否已經 ∈ D-8.1 (i)。偵測呼叫 `final_sessions()`（未扣除的 (i)）。`basis = direct` 和 `verified` 都要檢查。偵測不以該 run 與 X2 事件的先後篩選（涵蓋第 7 項的跨檔窗口）。
      - 成立時：
        - 記 WARNING；
        - 寫入 `session_calendar_conflict`，`origin = post_x2_final_run`；
        - payload 另帶 `x2_event_id`，以及使 d ∈ (i) 的 ok run 中 `run_id` 最小者的 `run_id`、`recorded_at`；
        - `evidence` 取該 X2 事件的 `trigger`。`verified` 列的 `trigger` 是 null，這時 `evidence = independent_source_absent`；
        - 同一個 (`session_date`, `origin`) 已有事件時，不重複寫入。
      - **揭露**：併入第 5 項的 §4.2 單獨揭露（以不同的 `session_date` 計，並依 `origin` 分列）。
      - **觀察日身分怎麼處理**（甲案；風控 2026-10-17 第九批 TA 提案確認；RC‴-3 的偵測條文不動）：
        - **X2 確認優先，固定排除**：d 一經 `x2_confirmed_non_session` 確認，就不再是觀察日；之後 d 進入 (i)，也不改變這一點。
        - 不新增、不修改任何事件。`x2_confirmed_non_session`、`x2_shift_json`，以及已順延或已 supersede 的 outcome，一律不動；不因此觸發 §6.4 更正作業；不寫任何撤回類事件。
        - `session_calendar_conflict`（`origin = post_x2_final_run`）寫入後，程式不得把它標為已解決，也不得因時間經過、run 數或查證結果解除。§4.2 依 origin 分列，持續揭露。
        - §4.2 另外揭露「`x2_event_ids` 含該 X2 事件的 outcome 筆數」。這個數字由 `x2_shift_json` 逐列數出，不另存欄位；每筆預測只計一次：更正鏈中任一列的 `x2_shift_json.x2_event_ids` 含該 X2 事件，就計入（事先宣告 v0.12 V12-04；風控 v0.12 確認 Q12-1）。
        - 根因由 data-engineer 查證（沿用 A-79 待決事項的 `session_calendar_conflict` 根因流程）。任何改變 d 的身分、或回復原 T+h 的做法，都只能修訂本項並送風控，不得由程式或操作者逕行處理。
        - **下游一致**：
          - 缺日稽核不對 d 補寫缺日列；
          - F-3 逾時率的 60 日窗不含 d；
          - 結算窗計數不含 d；
          - A-75 (iii) 因此可能成立（T＝d 時記 `inputs_not_ready`，不退回前一個 session）。
      - (h5) 的 `inputs_not_ready` 不寫缺日列（d 不是觀察日）。這類 d 屬於 (i)，不是未觀察平日；計數來源由 tech-architect 另定（風控第九批 S9-3，suggested）。
      - N-1 未核可不得進入 D_v（登記於待決事項）。〔已決：甲案已核可（風控 2026-10-17 第九批 TA 提案確認；風控 2026-10-18 v0.12 審查第四節），N-1 不再擋 D_v〕
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
     - 覆蓋率以 T 日籃子的成員數計。因為 T 日等權建倉，這等同 T 日權重；不得用 T+h 漂移後的權重或市值權重（r1，A-11）。
   - `split_or_reduction_suspected`：結算窗內任一日，以套用可用除權息因子後的序列計算，單日簡單報酬的絕對值大於 `SPLIT_SUSPECT_ABS_RETURN`（台股一般漲跌幅限制 10% 加容差 1%，凍結在 dirdef）（推定，不是確認的事件） → `excluded_corporate_action`（r1，A-11）
     - 這是固定門檻，不看該標的當天實際有沒有漲跌幅限制。
     - dirdef 自己持有這個常數，不 import `sectors.definition.UniverseRules`。
     - （r2，A-32）**字面**：LM-63 適用於**全部以 `SPLIT_SUSPECT_ABS_RETURN` 判定的標的**（風控 v0.6 核對 B-2，取代第三批「只適用有漲跌幅限制的標的」）。
     - （r2，A-32）**套用的序列**：個股 claim 該股的序列，以及族群成員的序列。`split_or_reduction_suspected` 不套用於大盤指數序列（事先宣告 v0.10 V10-01）。
     - （r2，A-32）**D_v 前要由 data-engineer 查證**：個股 claim 的範圍內（D-4.1：TWSE 上市普通股），有沒有結構上沒有漲跌幅限制的商品。
       - 槓桿／反向 ETF、國外成分 ETF 依 D-4.4 已經是 `E-SCOPE-TYPE`〔事實：本 ADR D-4.4〕；
       - 查證重點是「上市普通股」的判定來源可不可靠，以及 TDR、特別股、受益憑證等其他類型。
     - （r2，A-32）**若有這類商品，D_v 前二選一**：
       - (a) **建議**：事先登記，把它們排除在 claim 之外。dirdef 凍結正面清單 `CLAIM_SECURITY_TYPES`；不在清單內或類型不明的，一律 `E-SCOPE-TYPE`（fail-closed）；
       - (b) 另送 LM-63 的變體。
       - 建議 (a) 的理由：(b) 仍然會對這類商品推論「疑似分割或減資」，把真實的極端結果排除在計分之外，這正是風控指出的問題。
   - `dividend_factor_unusable`：窗內有除權息，但因子算不出來（**含配股**，`models.py:50-62`） → `excluded_corporate_action`
   - （r3，疑義裁定第 15 項；風控 2026-10-17 疑義裁定回送確認 Q-1）`index_bar_confirmed_erroneous`：大盤 P(T) 或 P(T+h) 的收盤經事先宣告 §6.3『大盤指數序列』確認有誤（『確認有誤之後』，L1175–L1177；X2 確認不屬此值，依 A-77 順延），而且依 `missing_bar_after_wait` 的既有等待值（5 個觀察交易日）等待期間，或之後的更正作業，都取不到正確值 → `unresolvable_missing_data`；`diag_last_close` 以最後一根未被確認有誤的收盤計算（事先宣告 v0.10 V10-03）。只適用 `scope_kind = market`。結算後才確認的路徑依 §6.4 supersede，並依 A-65 翻案伴隨句處理。
     - 作廢原因的判定順序中，第五值的位置交 quant 在事先宣告登記（v0.12，凍結前）。
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
   - `trigger=scheduled`、`late=0`、`supersedes_id IS NULL`、claim 為 forward、日期 ≥ D_v，而且不是已確認的 PIT 違規列（各項的取列規則見下三點，r1，A-7）。
   - E 的 `supersedes_id IS NULL` 指的是 `forecast_record`（預測端只用原始列）。
   - 結算端取更正鏈的最後一筆，條件是 `NOT EXISTS (SELECT 1 FROM forecast_outcome o2 WHERE o2.supersedes_id = o.outcome_id)`，**不是** `forecast_outcome.supersedes_id IS NULL`。
   - **主統計就是鏈尾**（第十批，提案 4；A-59）：
     - 事先宣告 §6.4（v0.11 L1220）「統計改用最新的那一筆」的「最新」，就是 D-11.1 的**更正鏈最後一筆**：`NOT EXISTS (SELECT 1 FROM forecast_outcome o2 WHERE o2.supersedes_id = o.outcome_id)`。
       - 不是 `resolved_at` 最大的一筆，不是 `settlement_date` 最大的一筆，也不是 `forecast_outcome.supersedes_id IS NULL`。
       - **不變式**：更正鏈是線性的（`UNIQUE(supersedes_id)`），最後一筆的 `outcome_id` 等於鏈內最大值。只作斷言，不作為取列條件。
     - 每一筆 snapshot 取的是「它讀 E 的那次 read transaction 內看得到的」鏈尾（RC‴-1：先讀序號、再讀 E）。
     - n、命中、基準命中、作廢率與 W，都依鏈尾的 `status`、`realized_label`、`hit`、`baseline_hits_json` 計算。
     - 預測端的 label、`band_def`、`baseline_predictions_json` 一律取原始的 `forecast_record`（LG-3；A-63 RC′-2 子點的四條約束）。
     - 列表上的紀錄（A-61「最新 outcome」）與 LM-131 也用同一個鏈尾，兩者由同一個函式產生（FL-49）。
     - 「更正後命中翻轉」（事先宣告 v0.11 L687、L1221）比較的是：更正鏈中第一筆 `resolved` 列，對上鏈尾。鏈尾不是 `resolved` 時，另外歸入「改為作廢」。已由 quant 登記（事先宣告 v0.12 V12-08）。
   - 「已確認的 PIT 違規列」是指在 `forecast_ledger_events` 有 `kind = pit_violation_confirmed` 事件的 `forecast_id`。
   - quant §4.1 的不重疊 n、重疊的次要統計、涵蓋率，**一律只在 E 上計算**。
   - 作廢列不計入 n，但計入最壞情境 W。
   - 逾時與 on-demand 的紀錄另外列出筆數。
   - **用詞定義**（r3，A-59）：「主統計」指 E 的成員資格；「n」指在 E 內、依 §4.1 不重疊規則計得的筆數。作廢列不計入 n，但計入 W。證據不足列依 §4.1 與 LM-91 第 5 條（quant 書面確認）。兩個詞不得混用。
     - LM-14、LM-37、LM-80 與 D-7.6、D-7.8 的「不計入主統計」都屬實，不改；LM-38「不計入 n」版已於 2026-10-17 經風控單項確認核可（`work/reviews/2026-10-17-LM38與B16註記及B0頁尾單項確認-風控.md` 第 1 項）。LM-38 的適用範圍依 A-62 R2 第 3 點，只用於 E 內的作廢列。E 的定義不變。
2. **`forecast_validation_snapshot`**：
   - 欄位（r1，A-5）：`claim_id`、`computed_for_session`、`eval_kind ∈ {daily, checkpoint}`、`checkpoint_n`、`n`、`m_at_eval`、`m_eff`、`K`、`alpha_star`、`status`（四態）、`display_state ∈ {gated, shown, suspended_f3, withdrawn_f2}`、`void_rate`、`stats_json`、`bootstrap_seeds_json`、`rng_name`、`numpy_version`、`display_reasons_json`、`withdrawn_at_n`、`code_commit`、`computed_at`；
   - `UNIQUE(claim_id, computed_for_session, eval_kind)`；
   - `bootstrap_seeds_json`：鍵為 `"{purpose}|{block_len}"`，值為 seed。
   - **seed 導出式**：`int.from_bytes(sha256(f"{claim_id}|{eval_key}|{purpose}|{block_len}".encode("utf-8")).digest()[:8], "big")`。
     - `claim_id` 取 registry 中的原字串；
     - `eval_key` 前瞻用 ISO 日期 `YYYY-MM-DD`，重放用 `freeze_commit`；
     - `block_len` 寫成十進位整數。
   - **`eval_kind` 刻意不放進導出式**：同一個 session 的 daily 列與 checkpoint 列用同一組 seed，checkpoint 不能換一組亂數重抽。
   - snapshot 不 supersede；來源資料更正只影響之後的 snapshot（A-77 第 11 項）。已寫入的 snapshot 不改、不重算。（第十批 R10-7）
   - 更正作業改變了曾參與 `better_than_baseline` 判定的列的 `status`、`realized_label`、`hit` 或 `baseline_hits_json` 任一項時，該判定在作業完成後的第一筆 daily snapshot 撤銷（降級），在下一個檢查點重判；比照事先宣告 v0.3 第 2 點（PIT 違規）。撤銷的日期、claim、`correction_job_id` 在 §4.2 揭露。daily 列仍不得升級（D-11.3）。（第十批 R10-7；觸發條件依風控 2026-10-18 v0.12 審查 Q12-2 擴為四項）
   - **`purpose` 為封閉列舉**，連同「purpose → 允許的 block_len」對照表凍結在 dirdef，屬於 `definition_logic_sha256` 的範圍。建議值如下，由 quant 在 v0.5 確認：
     - `neff`：block_len ＝ h；
     - `best_diff`、`paired_c`、`paired_c_w`：block_len ∈ {2, 4, 8}；
     - 開盤基準若有用到 bootstrap，再加 `*_open`。
   - snapshot 寫入時，鍵不在對照表內就拒絕寫入。
   - （r3，A-63；RC′-2、RC″-2、RC‴-1）`stats_json` 另登記 `e_read_event_seq`、`e_read_outcome_seq`（`pa9_holds` 的 `e_changed_since` 比較基準，見第 4 點第 11 項 (c)），以及 `e_read_at`（稽核用，不作比較基準；也不用 `computed_at`）。
3. **升降規則**：只有 `checkpoint` 列可以把狀態升為 `better_than_baseline`；`daily` 列只能維持或降級。
4. **顯示閘門**（`display.py`）：
   - 族群 `pa9_holds` 為真，或 G_eff 非空時，任何對外回應都不出現 bullish／bearish（PA-9、LG-15）；
   - 逾時紀錄不當作當日展望（PA-6）；
   - F-2 下架、F-3 暫停時同樣不出現；
   - CEO #10 的結果作為參數注入（只能加入 A-57 列為『#10 可加』的 `gate` 值，不得關閉固定項）。
   - 以下編號 5～12 接續上列原四點，為 r1 新增（A-6）：
   - 5. **單一閘門**：任何顯示面、plan、policy、提醒要取得展望，都只能呼叫 `views.outlook_view(claim_id, scope_key, T, consumer)`，回傳 `OutlookView{forecast_id, display_state, availability ∈ {evaluated, unavailable}, unavailable_reason, label}`。`label` 非 None，若且唯若 `availability = evaluated`。
   - 6. **`unavailable` 的原因**（封閉列舉，依下列優先序取第一個；r2，A-25）：`suspended_f3` → `withdrawn_f2` → `gated` → `surface_not_permitted` → `before_dv` → `missing_scheduled` → `not_in_schedule` → `late` → `insufficient` → `voided`。
     - 同一個 T 的 plan 讀不到 `voided`，這個值只是縱深防禦。
     - policy 只吃 `trigger=scheduled`、`late=0`、同一個 T 的原始紀錄。
     - （r2，A-25）**判定**：R_s 指 `trigger=scheduled`、`supersedes_id IS NULL`、`data_as_of=T` 的原始紀錄。
       - `surface_not_permitted`：claim 層的值。判定讀的驗證狀態，與 `display_state` 取自同一列 T 日 snapshot（A-30 FL-54 (e)）。
       - `not_in_schedule`：**只在 `scope_kind = symbol` 時成立**。條件是：沒有 R_s；T 日至少有一個排程 run；每個排程 run 的範圍快照都不含這檔。
       - `missing_scheduled`：沒有 R_s，而且不符合 `not_in_schedule`。大盤或族群沒有 R_s 時，一律是這個值，即使快照漏掉了自己（那屬於系統故障）。
       - `late`：有 R_s，而且 `late=1`。
       - `insufficient`、`voided`：有 R_s，而且 `late=0`。
     - （r2，A-25）**互斥與窮舉**：
       - 兩個缺紀錄的值（沒有 R_s）與 `late`（有 R_s）依「R_s 是否存在」互斥；
       - 兩個缺紀錄的值之間，依「是否有快照的正面證據」互斥；
       - 有 R_s 時，`late` 只能是 0 或 1，由 D-3 的 CHECK 保證（A-29）。
     - （r2，A-25）**on-demand 紀錄存不存在，都不影響上述任何值**。這適用於 policy，也適用於所有「當日展望」的消費端（風控 v0.6 核對 A-6 ② 已確認）。
     - （r2，A-25）`forecast_scope_snapshot` 要和 `forecast_run` 在同一個交易內、處理任何 scope 之前寫入。這樣「有快照、但不含這檔」才算正面證據。
     - （r2，A-25）**`reasons` 的字面對應**（經 LM-86 的 `{原因}`，由後端在產生 plan 時選定，前端不推斷）：
       - `not_in_schedule`：
         - `plan_record.in_holdings_or_watchlist_at_plan = false` → **LM-88**；
         - 否則 → **LM-89**。
       - `missing_scheduled` → LM-89。
       - `surface_not_permitted` 依守門對應兩個片段，由後端在產生 plan 時選定（r3，A-54）：
         - **S4 選擇規則**：`OutlookView.validation_status = better_than_baseline` → LM-95；其餘三態 → LM-94。
         - **S1 判定來源**：`OutlookView` 新增欄位 `validation_status`（四態之一），和 `display_state` 取自同一列 T 日 snapshot（FL-54 (e)）。plan 端不得另外讀 snapshot。
         - **S1 留存**：`plan_record.outlook_display_state[h]` 新增 `validation_status` 與 `reason_fragment_id`。所有 unavailable 原因都要記；只增不改。`reasons_json` 只能用 `reason_fragment_id` 查表渲染，前端與 API 不得重新推斷。
         - **S2 範圍**：LM-94、LM-95 只在 `scope_kind = symbol` 成立。`REASON_FRAGMENTS[surface_not_permitted]` 的守門含 `scope_kind == symbol`，其他 scope 沒有項目。v0 之後若依第 8 點引用其他 scope，要先有該 scope 的核可片段，否則 FL-52 (c) 失敗。
         - 任何使用者文件、說明頁、tooltip、API 欄位說明，都不得說明 LM-94 和 LM-95 的差別。
         - 顯示面確認（`work/reviews/2026-10-17-顯示面配置初版單項確認-風控.md`）(e) 第 1 點由 LM-86＋LM-94／LM-95 滿足（風控 r3 審查 C-2，`work/reviews/2026-10-17-ADR-0027-r3提案審查-風控.md`）。(e) 第 2～4 點（不做視覺連結、揭露放在 plan 卡內不收合、375 寬度驗收）由 PM、frontend-engineer、qa-e2e 承接，仍是 required。
         - `replay_review_pending` 常駐期間，顯示面確認 (e) 第 1 點改由 LM-86＋A-63 第 5 項（個股變體）承接；該片段不得聲稱展望在本頁或他頁顯示。
       - 其餘七個值與 `pending_triggers`（r3，A-56）：
         - 對應：
           - `suspended_f3` → LM-96；
           - `withdrawn_f2` → LM-97（三個 `withdraw_reason` 共用）。守門是 `scope_kind == symbol`，**而且 dirdef 的 `f2_variant == "F2-B"`**（D-14 G-2 機器部分，A-82）；
           - `gated` → LM-98（守門見 A-57）；
           - `before_dv` → LM-99；
           - `late` → LM-100（有 R_s 而且 `late=1`）；
           - `insufficient` → LM-101（有 R_s、`late=0`、PV-4 第四態）；
           - `voided` → LM-102（觸發時記 WARNING）。
         - LM-96～LM-98 的守門都含 `scope_kind == symbol`；LM-97 另外含 `f2_variant == "F2-B"`。
         - `f2_variant = "F2-A"` 時，`withdrawn_f2` 沒有核可片段，FL-52 (c) 失敗。如果 C-8 選 F2-A，LM-97 的替代片段要和 D-12「CEO 若選 F2-A，列舉值…另外定」同一批另送。
         - LM-99～LM-102 的 `{MM/DD}` 一律取 `data_as_of`（T），套年份規則。
         - LM-99 的「紀錄起算日」要和 LM-84、LM-85、LM-111 一起定案；改詞就要重送。
         - **`pending_triggers`**：`availability = unavailable`，而且 5 日展望條件出現在 `pending_triggers` 時，一律渲染 LM-103（Condition 依 A-70），不得顯示「等待中」；LM-103 和 LM-86 同時出現。
         - 不設 `PLAN_PENDING_OUTLOOK_SUSPENDED_OR_WITHDRAWN`。
   - 7. **不能顯示，就不能引用**（風控 §9.2 底線 1～5）：
     - policy 遇到 `unavailable` 的處理，必須在 D_v 前登記進政策表 v0，使用 `Condition.status = "unavailable"`；
     - 結果不得依賴底層標籤；
     - `reasons` 只能寫狀態，不能寫方向；
     - 下架或暫停時，`pending_triggers` 不得把展望條件列成「等待中」（`pending_triggers` 的渲染見第 6 點，LM-103）。
     - **None 規則**（r3，A-70）：每一種 unavailable 原因下（含 `surface_not_permitted`），凡是評估時用到展望的 `Condition`，`status = unavailable`，`observed`、`threshold` 必為 None。
       - 範圍包括 ADR-0025 D-4.4 的趨勢條件、D-4.5 的 `consider`／`avoid` 展望項，以及持有模式序位 7。
       - 每個 Condition 都宣告 `uses_outlook: bool`，沒有預設值，由 loader 驗證。複合條件整條變成 unavailable。
   - 8. **引用範圍**：v0 只引用同一檔個股的 `symbol|h5` claim（對齊 v0.5 V5-08）。改用其他範圍要升 `policy_version`。
   - 9. **依顯示面判定可用性**（r2，A-26；已採用；依事先宣告 v0.6 D-20、風控 v0.6 核對任務一第 2 點；必須在本 ADR 核可前生效）：
     - 1. **顯示面靜態列舉**：在 `display.py` 定義 `DisplaySurface = Literal["first_layer", "symbol_detail", "alert", "export", "api"]`。
       - `first_layer`：封閉清單，共六項，雙重歸屬取聯集（r3，A-66）：
         1. 市場總覽的天氣區塊；
         2. 「最需要處理」清單；
         3. 首頁警示列（同時屬於 `alert`）；
         4. 族群列表；
         5. 族群詳細頁；
         6. 市場總覽的大盤紀錄清單展開區。
       - `symbol_detail`：個股詳細頁（含持股行動計畫卡）；
       - `alert`：提醒或推播；
       - `export`：匯出；
       - `api`：API 對外回應。
       - 要新增值，須修訂本節並送審。
       - （r3，A-66）市場總覽上的持倉表、摘要卡、風險儀表沒有歸屬（fail-closed）。不在清單內的頁面或元件，一律沒有歸屬。
         - **沒有歸屬的頁面或元件**，不得渲染任何 `OutlookView` 衍生內容（label、天氣、方向色），也不得渲染 A-68 的適用欄位（`position_action`、`reasons`、`pending_triggers`、`add_conditions`、`entry_conditions`、`outlook_refs`）。
         - 首頁持倉表、摘要卡、風險儀表要顯示這類內容，必須先修訂本點、指定歸屬、送風控。
         - 回應中含 A-68 適用欄位的 route，`ENDPOINT_SURFACES` 的 kind 必須是 `plan`，而且 `SERVES ⊆ PLAN_OUTPUT_SURFACES`、`SERVES ⊇ 呼叫它的各元件的歸屬聯集`。
       - （r3，A-66）`symbol_detail` ＝ `/position/[symbol]` 整頁。
       - （r3，A-66）**單一來源**：`PAGE_SURFACES`，前後端共用。元件的 consumer ＝ 它所屬各 surface 的聯集；端點的 `SERVES` 必須 ⊇ 呼叫它的所有元件的 surface 聯集。
       - （r3，A-66）適用 AC-S-7、PA-9／PV-40。驗證見 FL-60。
     - 2. **許可矩陣 `SURFACE_PERMISSIONS`**：放在 `display.py`，鍵為 (scope_kind, surface)，只在 `display_state=shown` 時才查。**fail-closed**：未列入的鍵一律不許可。初版依 R-5、事先宣告 D-5～D-7：
       - （r3，A-67）**v1 列入的格子恰好六個**：(market, first_layer)、(market, api)、(sector, first_layer)、(sector, api)、(symbol, symbol_detail)、(symbol, api)。其餘一律不列入。
       - **(symbol, first_layer) 在程式碼裡不列入，不得寫成條件格。** 開放路徑只寫在 ADR 文字：優於基準、揭露全部核可、升 `policy_version`、送風控，而且 LM-94、LM-95 要重送。
       - `api` 是載體：
         - 每個對外端點都要在 `ENDPOINT_SURFACES` 登記 `SERVES`，而且 `SERVES` 必須至少含一個 `api` 以外的值；
         - 呼叫時 `consumer = SERVES ∪ {api}`；
         - 沒有登記或 `SERVES` 為空的端點，`outlook_view` 一律回 `surface_not_permitted`（執行期 fail-closed）；
         - 由 FL-54 (g) 用 route 列舉測試釘住。
         - `api` 這一格在 `shown` 時許可，限制來自它服務的顯示面。「API 回應不得含有它所服務的任一顯示面不允許的標籤」由此成立。
     - 2a. **天氣圖示**：`OutlookWeather` 是展望 label 的一種呈現形式，不是獨立的顯示面（映射在後端，PRD AV-13 與 NP-A1／NP-A2 列），依它所在端點的 `SERVES` 判定。
       - 市場總覽的天氣屬於 `first_layer`；
       - 第 1 點所列歸屬（`first_layer` 六項、`symbol_detail`）以外的頁面或元件，在清單修訂並送審之前，不得渲染展望 label、天氣、方向色，也不得渲染 A-68 的適用欄位。
     - 2b. **許可的前提是伴隨揭露**：
       - 每一格都登記 `required_disclosures`：D-1／D-5 的驗證徽章與 PV-45 固定句；個股另加 PA-4；「優於基準」時另加 D-2 的開盤基準句，以及 D-4 的區間、n、期間。
       - 所列片段全部核可，這一格才生效；否則不許可。大盤與族群的 `alert`、`export` 也一樣。
       - 由 FL-54 (f) 釘住。
       - 初版的矩陣由 PM 與 `PLAN_OUTPUT_SURFACES` 一併確認；之後任何一格要開放，都要送風控。
     - 3. **`consumer: frozenset[DisplaySurface]`**：每一個顯示面都許可，才是 `evaluated`。這等同「最嚴格的顯示面」，而且不需要顯示面之間有全序。`consumer` 至少要含一個 `api` 以外的顯示面。
     - 4. **plan 的常數**：
       - `PLAN_OUTPUT_SURFACES` 登記在政策表 v0 與本節。**初版 ＝ {first_layer, symbol_detail, api}**（r3，A-68），適用 `position_action`、`reasons`、`pending_triggers`、`add_conditions`、`entry_conditions`、`outlook_refs`；「最需要處理」的排序與成員、`plan_record` 顯示欄位、API 回應適用同一集合；初版經 PM 建議（`work/reviews/2026-10-17-PLAN_OUTPUT_SURFACES與頁面歸屬-product-manager.md`）並經風控顯示面確認（V10-12），之後要改須送審並升 `policy_version`。
       - plan 端只能傳這個常數，plan 的計算函式沒有顯示面參數。所以每個 (symbol, T) 只有一份 plan，不會依顯示面產生不同的 plan。
       - `plan_record` 記錄 `consumer_surfaces` 與 `restricting_surfaces`（A-29）。
       - （r3，A-68）**`alert`、`export` 移出的前提**：渲染、觸發時機、計數 N 都不依賴這些欄位（A-69）。
       - 把 `PLAN_OUTPUT_SURFACES` 改成三項的 PR，必須同時包含 FL-54 (h)，而且 CI 綠燈。
       - **前提未成立時 fail-closed**：D_v 前上述前提任一項未成立（包括契約測試尚未落地），`alert` 與 `export` 就留在 `PLAN_OUTPUT_SURFACES` 內，不得先行縮窄。
       - **登記**：quant 在 v0.10 照實登記方向，在 D_v 前、本 ADR 核可前完成。
       - **加回路徑**：先加回集合、升 `policy_version`、送風控，而且要早於渲染上線。
       - 不得以「plan 實際沒在首頁渲染」為理由移出 `first_layer`。
     - 5. （r3，A-67）v1 期間不論驗證狀態為何，個股展望對政策表一律是 `surface_not_permitted`。
     - 6. 不在執行時判定；任何配置變更都要送審。
   - 10. `PositionPlan.outlook_refs` 只在 `evaluated` 時填 `forecast_id`，其餘情況為 None。
   - 11. **紀錄清單端點同樣經過本閘門**（r3，A-71 改小標）：
     - （r3，A-71）**紀錄清單依 scope 拆成三個端點**：
       - `GET /api/forecast/records/market`：`SERVES={first_layer}`；
       - `/sectors/{sector_key}`：`SERVES={first_layer}`；
       - `/symbols/{symbol}`：`SERVES={symbol_detail}`。
       - 每個端點只回傳自己的 scope；不設總端點；不採「依參數決定 SERVES」。
       - A-27 與 A-60～A-65 一體適用。不得預設排除作廢列或逾時列。
     - （r2，A-27）**不出現 label 的情形**：每筆紀錄依下列順序判斷，任一條成立就不出現 label。「尚未結算」指這個 `forecast_id` 沒有任何 `forecast_outcome` 列。
       - (a) claim 為 `withdrawn_f2` 或 `suspended_f3`，而且尚未結算；
       - (b) **任何 scope** 的 claim 為 `gated`，而且尚未結算；
       - (c) **族群，而且〔`pa9_holds` 為真，或該 claim 當下成立的 `gate` 值集合非空〕，不論 `display_state`**：不論是否結算，都不出現 label（PA-9；ADR-0025 D-6.6）。
         - PA-9 條件 ＝ 該 claim 在 E 內、依 §4.1 計得的不重疊 n < 150。判定只呼叫 `pa9_holds`，其中的落後規則見 RC′-2。
         - 「當下成立的 `gate` 值集合」指查詢時的有效集合 G_eff，定義見 A-57 (iv)。
         - n 讀「判定 `display_state` 的同一列最新 daily snapshot」的 `n`。沒有 snapshot 時，視為 PA-9 成立（fail-closed）。
         - PA-9 條件只有一個判定函式 `pa9_holds`。D-11.4 第 4 點第 1 子項、A-57 族群的 `forward_n_below_min`、本條都呼叫它。
         - **快照落後時 fail-closed**（風控 2026-10-17 RC′-2）：簽章是 `pa9_holds(claim, snapshot, e_changed_since: bool)`。
           - `e_changed_since` 只由 `views` 的單一函式 `e_changed_since(snapshot)` 判定：只要有任何一筆「會改變 E 成員或 n 的事件」，序號大於該 snapshot 記下的對應讀取序號，就為真。
           - 為真時，`pa9_holds` 一律為真，直到之後產出一筆讀取序號涵蓋該事件的 daily snapshot 為止。
           - **事件封閉清單 `E_CHANGING_EVENTS`**：
             - `forecast_ledger_events.kind ∈ {pit_violation_confirmed, x2_confirmed_non_session, db_restored}`，依 `event_id`；
             - `forecast_outcome` 中 `supersedes_id IS NOT NULL` 的列，依 `outcome_id`；
             - 不按 claim 篩選：任一筆成立，所有族群 claim 的 `pa9_holds` 都適用；`n_disclosure_masked`（以及由它決定的 `ValidationBadgeMasked`、`validation_refresh_pending`）對大盤、族群、個股的所有 claim 都適用（C9-7 甲案）。
           - `forecast_ledger_events.kind` 的每個值都必須歸入 `E_CHANGING_EVENTS`，或歸入 `E_NEUTRAL_EVENTS` ＝ {`f3_resume_approved`, `replay_review_approved`, `session_calendar_conflict`, `unobserved_weekday`}（`unobserved_weekday` 依風控 2026-10-18 Q3-7 歸入）。新值沒有歸類時測試失敗；判斷不了的一律歸入 `E_CHANGING_EVENTS`。
           - `forecast_record` 的更正不改變 E 的成員，也不改變 n，所以不列入 `e_changed_since` 的判定，不另設序號（第九批，提案 4）。為使這一點成立，加四條約束：
             1. `forecast_outcome.forecast_id` 必須指向 `supersedes_id IS NULL` 的 `forecast_record`，由寫入函式驗證，不成立就拒絕寫入。更正列不結算。
             2. 結算與 validation 讀 `label`、`band_def`、`baseline_predictions_json` 時取原始列；`base_close` 只供預測端與稽核比對，結算的 P(T) 取 `start_price_json`（R10-5）。
             3. `pit_violation_confirmed` 的 `payload.forecast_id` 必須是原始列，由寫入函式驗證；否則 E 的排除條件會漏掉原始列。
             4. `forecast_record` 的更正路徑不得寫入 `forecast_outcome`，也不得觸發 §6.4 結算端更正作業。
           - **失效條件**：日後若要讓 `forecast_record` 的更正影響 E 或 n，須修訂 RC′-2，另設 `INTEGER PRIMARY KEY AUTOINCREMENT` 的更正序號，並納入 `e_changed_since`。
           - **比較基準：單調遞增序號，不用時間戳**（風控 2026-10-17 RC″-2，二選一採 (b)）：
             - `forecast_ledger_events.event_id` 與 `forecast_outcome.outcome_id` 都是 `INTEGER PRIMARY KEY AUTOINCREMENT`：單調遞增、永不重用。遷移與備份還原都不得重編（比照 ADR-0012 D-2 的 `run_id`）。
             - snapshot 的計算在一個明確開啟的 read transaction 內讀 E，並在同一個 transaction 內讀出兩個值，寫入 `stats_json`：
               - `e_read_event_seq` ＝ 看得到的 `forecast_ledger_events.event_id` 最大值；
               - `e_read_outcome_seq` ＝ 看得到的 `supersedes_id IS NOT NULL` 列中，`outcome_id` 的最大值。
               - 沒有列時記 0。
             - `e_changed_since(snapshot)` 為真，若且唯若下列兩項任一成立：
               - 存在 `kind ∉ E_NEUTRAL_EVENTS`、而且 `event_id > e_read_event_seq` 的事件（含未歸類的值）；
               - 存在 `supersedes_id IS NOT NULL`、而且 `outcome_id > e_read_outcome_seq` 的列。
               - 兩個欄位任一缺漏或不是整數，一律為真。
             - 讀取順序（RC‴-1）：在同一個明確開啟（明確 `BEGIN`）的 read transaction 內，**先讀 `e_read_event_seq`、`e_read_outcome_seq`，再讀 E**。
             - 下列任一情形，`e_changed_since` 為真，並記 WARNING（RC‴-1）：序號欄位缺漏；不是非負整數（bool 不算）；大於目前看得到的對應最大值。
             - `e_changed_since` 比對的 snapshot 與事件最大值，要在同一個 read transaction 內、從同一個主 DB 檔讀出；不得跨請求或跨程序快取 snapshot 或序號。
             - 備份還原後，失落時間線的序號可能被重新配發，所以 DB 檔以外保存的 snapshot 或序號，不得用於任何判定。還原以整個主 DB 檔為單位。
             - 寫入函式與 SQL 不得指定 `event_id`、`outcome_id`，由 SQLite 配號（比照 D-2 第 3 點）。
             - 依據：
               - SQLite 同一個資料庫同時只有一個寫入交易，不論 journal 模式；AUTOINCREMENT 在寫入交易內配號，所以序號順序就是 commit 順序。
               - 因此，read transaction 看得到的最大序號是 S 時，當時還沒 commit、或之後才 commit 的列，序號都大於 S。
               - 這個判定不依賴任何時鐘，也不要求讀 E 和寫入 snapshot 在同一個交易內。
             - `stats_json.e_read_at`（讀 E 那次 read transaction 開始時的 store 時鐘）保留為稽核欄位，**不作為任何判定的比較基準**。比較一律用序號，不用 `e_read_at`，也不用 `computed_at`。
             - 不採 (a)（同一個 `BEGIN IMMEDIATE`）的理由：
               - `recorded_at` 可能在寫入者拿到鎖之前就取好了；
               - 牆鐘不保證單調；
               - 持鎖時間會涵蓋整段 snapshot 計算，第二個寫入者（見 Consequences：預測帳有兩個寫入者）會被擋在 `busy_timeout`。
           - 寫入 snapshot、計算 `gate` 的當下，`pa9_holds` 用本筆剛算出的 n，以 `e_changed_since = False` 呼叫。
           - 依據：n 是 snapshot 寫入時的欄位值，不是查詢當下重算，所以不適用 RC′-2 的免除條款。
         - **`n_disclosure_masked(claim, snapshot)`**（第九批，提案 2；C9-7 甲案）：放在 `views`，是唯一的判定函式。為真，若且唯若〔沒有 daily snapshot，或 `e_changed_since(snapshot)` 為真〕；沒有 scope 條件，任何 scope 都適用（風控 2026-10-18 C9-7 裁定擴及大盤、個股）。gate selector、驗證徽章，以及任何帶該 claim n 的片段，都呼叫這個函式。這個函式在內部自行呼叫 `e_changed_since(snapshot)`，不接受呼叫端傳入的 bool（風控第九批 S9-2，AST 測試）。`e_changed_since` 不按 claim 篩選，所以同一個回應裡的 claim 會一起遮蔽。
         - **徽章資料來源**（風控第九批 C9-6）：LM-03、LM-32、LM-33 的 `{n}`、`{k}`、`{k_i}`、`{n_eff}`、`{lo}`／`{hi}`、`{lo_i}`／`{hi_i}`、`{起}～{迄}`，LM-12 的 `{n}`，以及徽章的狀態，一律取判定 `display_state` 的同一列最新 daily snapshot（與 A-63 (c)、A-57 (iv) 同一列），不得另查，也不得跨列混用。
         - **遮蔽時的回應**（第十一批 LM-153）：`n_disclosure_masked(claim, snapshot)` 為真時，該 claim 的徽章在這次回應中是 `ValidationBadgeMasked`，封閉 schema（`extra="forbid"`），欄位恰好四個：
           - `claim_id`；
           - `masked: Literal[True]`；
           - `mask_reason: Literal["e_changed_since", "no_daily_snapshot"]`：封閉列舉，schema 拒絕列舉外的值；要增列，須送風控重審 LM-153 是否仍屬實；
           - `badge_fragment_id: Literal["LM-153"]`：值只能是 LM-153（風控第十一批 LM-153 條件 ⑬）。
         - 前端只依 `badge_fragment_id` 渲染釘字常數，不得自行持有、拼接或改寫字串，不得渲染 `mask_reason`。
         - 徽章字面登記在 `BADGE_FRAGMENTS`，和 `GATE_FRAGMENT_REGISTRY` 分開。LM-153 不登記 `covers`，不進 gate 登記（條件 ⑩）。
         - 任何 scope 的 claim，`n_disclosure_masked(claim, snapshot)` 為真時都產生 `ValidationBadgeMasked`（LM-153 條件 ⑥，依風控 2026-10-18 C9-7 裁定擴及大盤、個股）。
         - 遮蔽時的回應，其餘子點：
           - 不帶上方「徽章資料來源」一條列出的任何數值；
           - 不帶 LM-03、LM-04、LM-32、LM-33 的片段 ID；
           - 前端不渲染徽章的狀態詞與數字行；
           - 同一區塊的閘門句代入 LM-144，交代筆數待彙整：族群經 LM-122／LM-123／LM-126／LM-127（`covers = {forward_n_below_min}`）；大盤與個股經 LM-120／LM-121（`covers = {validation_refresh_pending}`，風控 2026-10-18 C7-4）。
         - **遮蔽只遮徽章**（條件 ⑫）：LM-76、LM-81，以及 C9-4 例外的歷史值（LM-75、LM-79、LM-81、LM-104 的 `{X0}`／`{X}`，取事件當時寫定的欄位），照各自的條件渲染。產生這些片段的函式不得呼叫 `n_disclosure_masked`。
         - **遮蔽與方向互斥**（條件 ⑪）：（族群）`views` 在任何回應（`OutlookView`、紀錄列、`settled_record`）帶出族群 claim 的 label 之前，要另外確認 `n_disclosure_masked` 為假；為真時不帶 label，並記 WARNING。這是 `pa9_holds` 之外的獨立檢查。依 RC′-2，遮蔽成立時 `pa9_holds` 必然為真，所以這一條是縱深防禦。大盤與個股的讀法見下一點（C7-6）。
         - **大盤與個股適用 LM-153 條件 ⑪ 的讀法**（風控 2026-10-18 C7-6）：遮蔽成立時：
           - (1) 目前展望（`OutlookView`、`outlook_block`）不得渲染 label；
           - (2) 未結算紀錄列依 A-27 (a)、(b) 不出現 label，判定一律用 `views` 調整後的 `display_state`；
           - (3) 已結算紀錄列（`settled_record`，含 A-62 R2 作廢列經 LM-133 呈現的原 label）讀即時的更正鏈鏈尾、不讀 snapshot，照 A-27、A-62、A-65 既有條件渲染。G_eff 含 `validation_refresh_pending`，所以依 A-27 (e) 一律附 PV-45。
           - 這個讀法和族群不同（族群依 A-27 (c) 不論是否結算都不出現 label），對應的是 A-27 既有的 scope 差異，不是另開例外。
         - **同頁一致**（條件 ⑭；風控 2026-10-18 C7-1、C7-4、C7-7 擴及大盤、個股）：
           - 同一次回應中，每個 claim 只判定一次（同一個 read transaction），只產生一個徽章物件，同一頁該 claim 的所有徽章位置（族群含 `sector_cell`、`sector_detail`）都引用它。
           - 同一頁的徽章只能來自同一個回應。前端不得為同一個 claim 從兩個端點取徽章。
           - 同一次回應中，`validation_refresh_pending` 的判定與徽章遮蔽來自同一次 `n_disclosure_masked` 呼叫（同一個 read transaction）。不得出現「G 並列含 LM-144、而同一 claim 的徽章是正常徽章」的組合，反之亦然（LM-153 條件 ⑭ 擴及大盤、個股）。
         - 整個回應（JSON 與渲染結果）都不得含該 claim 的 snapshot n 及其衍生值（API 本身就是顯示面；風控第九批 C9-4，風控 2026-10-18 C7-1 擴及大盤、個股）。唯一的例外是事件當時寫定的歷史值：`withdrawn_at_n`、`checkpoint_n`、`predecessor_withdrawn_at_n`（LM-75、LM-79、LM-81、LM-104 的 `{X0}`／`{X}`）。這些值一律取當時寫定的欄位，不得以現值 n 代入，也不受 `n_disclosure_masked` 影響。FL 加一格：遮蔽中、而且有下架告知時，`{X}` 等於事件欄位；fixture 中 `{X}` 與現值 n 用不同的值。
         - **上線限制**（風控第九批 C9-5）：`ValidationBadgeMasked` 的渲染字面（族群徽章遮蔽變體）核可之前，族群展望區塊不得上線。LM-31「以各展望旁的驗證徽章為準」不得因此刪除或弱化。〔已決：LM-153〕
         - **對族群，(c) 先於 (a)、(b) 判斷。** 選用狀態片段時以 (c) 為準，片段依 A-63 第 11 點選用。
         - (c) 不以 `display_state` 的任何值為條件。
       - (d) **尚未結算而且 `late=1`**：不出現 label，可以顯示「逾時，結算後列示」這個意思的狀態片段（PA-6、D-10、LG-8）。
       - **(d′) on-demand 紀錄，而且 `window_started = 1`、尚未結算**：不出現 label。
         - 狀態片段的意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」。逐字字面為 LM-106；守門 R1、R2 見 A-62。
         - 判定讀寫入時已存的值，臨界點同 FL-15（08:29:59 顯示，08:30:00 不顯示）。
         - 回應形狀（封閉 schema、資料日期、結算後的形式）與狀態片段 ID，依 D-7.8 第 8 點（A-36 第 1～4 點）。紀錄清單與 POST 共用同一個 schema 與片段。
       - （r3，A-62）**字面對應與守門**：(d) → LM-105；(d′) → LM-106（紀錄清單與 POST 共用同一個 ID）。依 A-27 的順序，先成立的規則決定用哪一句。
         - **R1**：(b)、(c) 排在 (d)、(d′) 之前，所以 `gated` claim 的列在結構上選不到這兩句。族群另由 (c) 的優先序保證：(c) 成立的列，選不到 LM-105、LM-106，也選不到 A-63 第 1～3 項。驗證見 FL-58 (e)。
         - **R2（風控 2026-10-17 C-3 附條件核可）**：作廢列結算後，以「原本的 label＋作廢原因片段＋已作廢標示，不附實際結果」呈現。同一個決定適用 A-36 第 4 點的 on-demand 作廢列。條件如下：
           1. 只適用於 A-27 (a)～(c) 沒有擋下的列。族群 (c) 成立時照樣不出現；大盤或個股依 (e)（G_eff 非空，不論 `display_state`）照樣附 PV-45。
           2. **形狀**：
              - label 只放在 `SettledRecordView.settled_record`；
              - 同一物件帶 `settlement_date`（判定作廢的日期）和作廢的 `status`／`status_reason`；
              - 不得出現 `realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`，也不得出現任何部分窗口的報酬；
              - 不用天氣圖示，也不用方向色；
              - 不進入 `current_outlook`、`plan` 兩類端點（A-74）。
           3. **字面**：
              - **LM-38 只能用在 `in_eligible_set = true` 的作廢列**，搭配 LM-109。
              - E 以外的作廢列（逾時、on-demand、起算日前、PIT 違規）用不帶最壞情境子句的作廢變體，搭配 LM-110。變體由 creative-lead 起草、風控核可。
              - 「原本的預測（已作廢）」的呈現框架，由 creative-lead 起草，和「已結算＋實際結果」片段同一批送風控逐字審。
           4. `status_reason` 的每一個值（含 D-9.3 對齊事先宣告 v0.10 V10-03 後的第五值 `index_bar_confirmed_erroneous`）都要有核可片段。沒有核可片段的值，這類列一律不顯示 label。FL-52 的窮舉表要涵蓋 `status_reason` 的全部值。
           5. 只要渲染了 LM-38 或 LM-109，最壞情境的結果就必須真的渲染。
           6. **第 3、4 點的片段核可之前，採 fail-closed（不顯示 label），而且 FL-52 (d) 判定失敗。** 本核可只解決設計層，不會讓 D_v 提前。
       - （r3，A-63）**單列狀態片段**：
         - A-27 (a)～(c) 成立的列，`status_fragment_id` 必填，不得留白。
         - 交 creative-lead 起草的語意（大盤、族群、個股要各自有主詞）：
           1. 已下架，結算後列示；
           2. 暫停顯示，結算後列示；
           3. 大盤或個股 `gated`、未結算：結算後列示；
           4. 族群 `gated`：未達 150 前不顯示方向（n／150），不得暗示之後一定會開放；
           5. A-57 的 G_eff 不只樣本數一項時，用來取代 LM-98 的片段，依第 11 點的涵蓋規則選用。各 scope 的變體另受以下限制（風控 2026-10-17 RC′-8）：
              - **個股變體**：不得聲稱展望在任何頁面顯示（不得沿用 LM-94「只在個股詳細頁顯示」的寫法），也不得預告開放時點；
              - **族群變體**：不得暗示到了 150 筆就會開放；
              - 要在 D_v 前核可。
           6. 第 1、2 項（已下架／暫停顯示，結算後列示）不得用在 (c) 成立的族群列。
           7. 第 4 項的語意是「族群：PA-9 成立時不顯示方向（n／150），不得暗示之後一定會開放」，不論 `display_state`。**第 4 項只涵蓋 `forward_n_below_min`**，只有 G_eff ＝ {`forward_n_below_min`} 時可以單獨使用。
           8. 族群 (c) 成立時，片段依第 11 點選用，不得寫「結算後列示」。
           9. **不設遲滯。** 每次回應都依當下的 `pa9_holds` 判定，不得以「曾經顯示過」維持顯示。重新變成 PA-9 成立後，這些列改用第 4 項，不得繼續寫「結算後列示」。
           10. quant 在驗證報告揭露兩件事：族群重新變成 PA-9 成立的事件（日期、claim、原因事件的參照），以及受影響的列數。這項列入「待決事項 quant」。
           11. **多個 `gate` 值同時成立時的選用規則**（風控 2026-10-17 RC′-3；大盤、族群、個股都適用）：
               - 不得只呈現其中一個閘門，尤其不得只呈現看起來最快解除的那一個。例如族群在 `forward_n_below_min` 與 `replay_review_pending` 同時成立時，不得只用第 4 項。
               - `display.py` 的 `GATE_FRAGMENT_REGISTRY` 是唯一的登記，選用一律經 selector。登記以 (scope_kind, slot) 為鍵，其中 `slot ∈ {record_list, record_list_header, plan_reason, outlook_block, sector_cell, sector_detail}`（風控第八批 T-2）。每個片段登記 `covers: frozenset[gate]`。
                 - `record_list_header` 是紀錄清單的清單層級標頭；`outlook_block` 是大盤與個股的展望區塊；`sector_cell` 是族群列表的單元格；`sector_detail` 是族群詳細頁。
                 - `display.py` 的 `GATE_SLOT_SCOPES` 是封閉登記：
                   - `record_list`、`record_list_header` → {market, sector, symbol}；
                   - `plan_reason` → {symbol}；
                   - `outlook_block` → {market, symbol}；
                   - `sector_cell`、`sector_detail` → {sector}。
                   - 要增列，須修訂本點並送風控。
                 - 上述位置的 gate 片段 ID，只能由 `select_gate_fragments(scope_kind, slot, G_eff, display_state, validation_status, n_masked)` 產生（route 列舉＋AST 測試，比照 FL-60 (d)）。
                   - `display_state` 取 `views` 調整後的值。
                   - `validation_status` 取判定 `display_state` 的同一列最新 daily snapshot 的 `status`（A-57 (iv) 規定取原值）。沒有 snapshot 時為 None；None 一律不選 LM-12。
                   - `n_masked` 只能由 `views.n_disclosure_masked(claim, snapshot)` 產生。這個函式在內部自行呼叫 `e_changed_since(snapshot)`，不接受呼叫端傳入的 bool（風控第九批 S9-2，AST 測試）。
                 - 輸入 `display_state = shown` 而 G_eff 非空時，函式 raise。另加性質測試：`views` 永遠不會產生這個組合（風控第九批 S9-1，FL-52 斷言 (9)）。
                 - **閘門片段登記 `GATE_FRAGMENT_REGISTRY`**（第九批，提案 1；風控第九批 C9-1、C9-2）：封閉登記，放在 `display.py`。要增列，須修訂本點並送風控。
                   - `GATE_SLOT_SCOPES` 的每一個 (scope_kind, slot) 都必須在本登記逐一列出；沒列出的組合 fail-closed。FL-52 斷言本登記與 `GATE_SLOT_SCOPES` 一一對應。
                   - GR（gate 並列句的組裝規則）的固定順序為：`forward_n_below_min`、`validation_refresh_pending`、`replay_review_pending`、`shadow_run_pending`、`settlement_smoke_pending`（風控 2026-10-18 C7-4）。
                   - **原子片段**：只能代入組合句，本身不是 slot 項目。
                     - LM-128：`covers = {forward_n_below_min}`，scope 為 market、symbol。只在 quant 登記了該 scope 的前瞻門檻時，才進入 P(scope)。大盤、個股沒有任何 daily snapshot 時不選用（風控 2026-10-18 C9-7）。
                     - LM-129：`covers = {forward_n_below_min}`，scope 為 sector，限 `n_masked = false`。
                     - LM-144：`covers = {forward_n_below_min}`，scope 為 sector，限 `n_masked = true`。LM-129 與 LM-144 互斥，GR 順序都排第一。
                     - LM-130：`covers = {replay_review_pending}`，各 scope 都可用。
                     - LM-144（C9-7 甲案，風控 2026-10-18 C7-4）：(market、symbol, {`outlook_block`, `record_list`, `record_list_header`}) 登記 LM-144 為 `validation_refresh_pending` 的原子片段，`covers = {validation_refresh_pending}`；族群的 LM-144 登記（`covers = {forward_n_below_min}`）不變。同一字面依 scope 登記不同的 `covers`，由 (scope_kind, slot) 鍵區分，FL-52 逐 scope 斷言。
                   - **slot 項目**：
                     - `outlook_block`（market、symbol）：
                       - LM-12：只在 G_eff ＝ {`forward_n_below_min`}、`display_state = gated`，**而且**同一列 snapshot 的 `status` 是「未驗證」時選用。字面的「未驗證」與「樣本不足，不具推論意義」只在這個條件下屬實。其餘情形一律用 LM-120。`n_disclosure_masked` 為真時不得選用（風控 2026-10-18 C9-7）。
                       - LM-120（`{G 並列}` 取 LM-128（`forward_n_below_min` ∈ G_eff 時）、LM-130、LM-144，依 GR 組裝）：用於其餘所有非空子集。`display_state ∈ {suspended_f3, withdrawn_f2}` 時一律用 LM-120（含 G_eff ＝ {`forward_n_below_min`}），並與 LM-76／LM-81 並列（A-63 第 12 點 (1)）。
                     - `record_list_header`（market、symbol）：只用 LM-120，不登記 LM-12。
                     - `record_list_header`（sector）：只用 LM-120，`{G 並列}` 的原子取 LM-129 或 LM-144（依 `n_masked`）、LM-130，依 GR 組裝。
                     - `record_list`（market、symbol）：A-27 (b) 成立、未結算的列用 LM-121（`{G 並列句}` ＝ LM-120 全文，原子同 `outlook_block` 的 LM-120）；A-27 (a) 的列用 LM-118／LM-119（`covers = ∅`），G_eff 非空時後接 LM-120（A-63 第 12 點 (2)）。
                     - `plan_reason`（symbol）：LM-98 {`forward_n_below_min`}、LM-124 {`replay_review_pending`}、LM-125 {`forward_n_below_min`, `replay_review_pending`}，不變。
                     - `sector_cell`、`sector_detail`（sector）：k＝1 用 LM-127，`{G 單項}` ∈ {LM-129 或 LM-144, LM-130}；k≥2 用 LM-126。
                     - `record_list`（sector）：k＝1 用 LM-122，k≥2 用 LM-123，原子選法同上。
                 - FL-52 任一格失敗，不得以 skip、xfail、placeholder 或暫定字面讓測試通過。
               - **不變式**：選出片段的 `covers` 聯集恰好等於 G_eff。呈現方式二選一：
                 - 逐值並列：固定排序，在同一區塊同時呈現；
                 - 一個涵蓋全部成立值的變體。
               - `plan_reason`（LM-86 只有一個 `{原因}`）只能用單一涵蓋變體，tuple 長度為 1。
               - 適用範圍：第 3 項、第 4 項、第 5 項、LM-98，以及族群 (c) 成立的列。
                 - 第 3 項本身 `covers = ∅`。(b) 成立的大盤或個股列，以第 3 項加上涵蓋 G_eff 的片段呈現。
               - 表內沒有項目的組合，視為沒有核可片段：不出現 label，FL-52 (c)／(d) 判定失敗。
           12. **claim 層與清單列同時呈現**（風控第八批 2.26.10 第 2 點）：
               - (1) claim 層（`outlook_block`，或 `record_list_header`）在 `suspended_f3`／`withdrawn_f2` 而且 G_eff 非空時，同時呈現 LM-76（暫停）／LM-81（下架）與 LM-120，`covers` 聯集等於 G_eff。
               - (2) LM-118、LM-119 的列，在 G_eff 非空時，後面一律接 LM-120（端點不收頁面參數，前端也不得另寫判定，所以不依頁面判斷；風控 2026-10-17 RC″ 回送確認第 7 點核可）。
               - (3) 族群 (c) 優先時，同頁 claim 層（`record_list_header`、`sector_cell`、`sector_detail`）在 `suspended_f3`／`withdrawn_f2` 時要有 LM-76／LM-81。
         - 核可之前，FL-52 (d) 失敗。
     - （r2，A-27）**揭露**：
       - (e) **大盤或個股，而且 G_eff 非空，不論 `display_state`**：已結算紀錄若顯示 label，回應的 `disclosure_fragment_ids` 要含 PV-45 固定句，在同一區塊呈現（風控 2026-10-17 RC″-1）。
         - G_eff 的定義見 A-57 (iv)。大盤與個股的 G_eff ＝「判定 `display_state` 的同一列最新 daily snapshot」的 `gate`；`n_disclosure_masked` 為真時再加入 `validation_refresh_pending`；沒有 snapshot 時依 A-57 (iv)「查詢時閘門」的「沒有 snapshot」子點。
         - (e) 不以 `display_state` 的任何值為條件；`suspended_f3`、`withdrawn_f2` 期間同樣適用。
       - **(f)** 每筆紀錄帶 `in_eligible_set: bool`，值等於該筆是否屬於 E，與 validation 呼叫同一個函式（FL-49）。
         - `exclusion_reasons` 的封閉列舉改為 {`before_dv`, `late`, `on_demand`, `pit_violation_confirmed`}，**`voided` 移出**。
         - 理由：作廢列依 D-11.1 屬於 E（不計入 n，但計入 W）。作廢原因依事先宣告 §4.10 D-12，用 `status_reason` 的既有片段標示（例如 LM-63）。（`in_eligible_set` 的字面另依 A-61 選用，例如作廢列用 LM-109；兩者並列，不互相取代）
         - `in_eligible_set` 的真／偽字面不得寫成「計入 n」，因為證據不足與作廢的列屬於 E、但不計入 n（LM-91）。
         - （r3，A-60）**不變式**：清單每一列，`in_eligible_set = false` 若且唯若 `exclusion_reasons` 非空。
         - E 另有兩個條件沒有對應的 exclusion 值，處理方式是這兩類列**不回傳**：
           - 更正列：清單只回傳 `forecast_record.supersedes_id IS NULL` 的原始列；結算端取更正鏈的最後一筆。
           - 重放列：清單不讀 `forecast_replay`。`forecast_record` 加 insert trigger，要求 `claim_id` 的 registry `kind` 是 forward；`forecast_replay` 反過來，只收 replay。
           - 若要列示更正列或重放列，要先擴充列舉並送審。
         - （r3，A-60；S-6）驗證狀態頁揭露清單沒有回傳的更正列筆數。字面交 creative-lead 起草、風控審；上線條件同 LM-107，不列為 D_v 的前提。
         - 驗證見 FL-58。
       - （r3，A-61）**字面對應**：
         - **`in_eligible_set = true`**：
           - 一般列 → LM-107；
           - 證據不足列（`label = insufficient`）→ LM-108；
           - 作廢列（最新 outcome 的 `status` 為 `unresolvable_missing_data` 或 `excluded_corporate_action`）→ LM-109；
           - 兩者同時成立時選 LM-109。
         - **`in_eligible_set = false`**：用 LM-110，`{原因}` 只取以下四個：
           - `before_dv` → LM-111；
           - `late` → LM-112（只用於排程列）；
           - `on_demand` → LM-113；
           - `pit_violation_confirmed` → LM-114（只用於有事件的列）。
           - 多個原因全部列出：`pit_violation_confirmed` 排第一，其餘照列舉順序，以「；」分隔；不得截斷，也不得寫「等」。
         - **上畫面的前提**：
           - LM-107～LM-110：LM-84 核可，而且驗證狀態頁已上線；
           - LM-108：另需 quant 書面確認 LM-91 第 5 條；
           - LM-109：LM-38 的前置條件已經解除（2026-10-17 風控單項確認），其餘條件不變；
           - 最壞情境的結果必須真的渲染。
         - 不再使用 `counts_in_primary` 系列的常數名。
       - PIT 違規列的標示：已確認的 PIT 違規列以 LM-110＋LM-114 呈現（A-61）。視覺上不得和 E 內的紀錄相同（前端契約測試）。
       - （r3，A-64）**(g)** 以下所有不顯示 label 的回應列，一律用同一個封閉 schema `MaskedRecordView`（`extra="forbid"`）：A-27 (a)、(b)、(c)、(d)、(d′)；POST 回傳的 `late=1` 排程紀錄；FL-34 下架期間的紀錄回應。
         - **白名單**：A-36 第 1 點 (b) 的清單（D-7.8 第 8 點）；排程列用 `late` 取代 `window_started`；`settled` 依實際值；(c) 已結算列可以加 `settlement_date`、`outcome_status`。
         - **不得出現**：
           - `label`、`range_basis`、天氣、色彩代碼、方向詞、`invalidations_json`、`evidence_json`、`baseline_predictions_json`；
           - (c) 另外不得出現 `realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`。
         - 白名單要增列欄位，須修訂本點並送風控。
         - **FAIL_CLOSED 路徑的狀態片段**（第十二批 LM-154；風控 R10-4）：同時滿足以下三點的列，以 `MaskedRecordView` 回傳，`status_fragment_id` 必填，值只能是 LM-154（風控第十二批 LM-154 條件 ③）：
           - `had_listed_result` 為真；
           - 最新 outcome 是 `resolved`；
           - 依 `CORRECTION_REASON_FRAGMENTS` 判為 FAIL_CLOSED。
           - 這是雙向規則：LM-154 也只能出現在這條路徑。
           - 判定只由 `display.py` 的單一函式 `record_status_fragment(row)` 產生。
           - FAIL_CLOSED 的情形是封閉的，只有以下三種：兩個以上的原因；`[dividend_factor_corrected]`；`[window_bar_corrected]` 但 `correction_is_display_neutral(chain)` 為假。`[settlement_close_corrected]`（含 P(T) 收盤有變）依對照表用 LM-150＋LM-152，不屬 FAIL_CLOSED（R10-5 依事先宣告 v0.12 V12-12 書面確認，與本 ADR 同批生效）。
         - A-63「A-27 (a)～(c) 成立的列，`status_fragment_id` 必填，不得留白」擴及本路徑（風控 R10-4）。
         - **FAIL_CLOSED 列的白名單**（R10-4 與 LM-154 條件 ⑤ 合併；兩者不一致時以 ⑤ 為準）：
           - 可帶：A-36 第 1 點 (b) 的清單；排程列用 `late` 取代 `window_started`；`settled = true`。
           - 不帶 `settlement_date`、`outcome_status`：兩者都屬於 R10-6 的 D 欄位，在本路徑不適用 (c) 已結算列的那兩欄。
           - 不得出現：A-64 (g) 的全部禁止欄位；`label`、`realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`；R10-6 的任何 D 欄位（含 `realized_return_display`、`invalidation_*`、`mae`、`mfe`、`diag_*`）；`threshold_display`；`resolved_at`；`correction_causes`。
           - `disclosure_fragment_ids` 不得含 LM-131、LM-132、LM-146、LM-92、LM-133、LM-143、LM-150。大盤列不得含 LM-22。
         - **全域不顯示**（LM-154 條件 ⑥）：這筆紀錄更正後的結果，不得出現在任何回應或匯出，包括驗證狀態頁的逐筆明細、匯出、展開處。所有含紀錄明細的 route 與 `EXPORT_MODULES`，都經過同一個 `record_status_fragment` 判定。
         - **§4.2 的計數來源**（LM-154 條件 ⑫，TA 這一側）：依 LM-154 不顯示結果、但仍計入主統計（鏈尾，D-11.1）的列數，依鏈尾的 `correction_causes` 分列（多原因另列一類）。由同一個判定逐列數出，不另存欄位。quant 在事先宣告 v0.12 §4.2 登記。
         - 驗證見 FL-59。
       - （r3，A-65）**(h)** 已結算、可以顯示 label 的排程列：label 只放在 `settled_record`（和 A-36 第 4 點共用 schema `SettledRecordView`），同一物件帶 `settlement_date` 與結算結果；頂層沒有 `label`；不得當作目前展望呈現。
         - 「已結算＋實際結果」片段的範圍擴及排程紀錄。核可之前不顯示 label，而且這個片段列入 FL-52 (d)。
         - 作廢 outcome 依 A-62 R2 第 1～6 點。
         - (e) PV-45（大盤或個股，而且 G_eff 非空，不論 `display_state`）與 PA-4（依既有規則）照樣適用於已結算的排程列。
         - **結算日期的語意**（增補 T-4）：
           - `start_price_json`、`end_price_json` 都必須帶 `session_date`：實際取用的那個收盤的交易日。
           - `status = resolved` 的列，寫入時驗證兩件事，不成立就拒絕寫入：
             - `settlement_date == end_price_json.session_date`，也就是觀察到的 T+h；X2 順延時就是順延後的 T+h；
             - `start_price_json.session_date == forecast_record.data_as_of`。
           - LM-131 的 `{終點 MM/DD}` 綁定 `end_price_json.session_date`，起點 `{MM/DD}` 綁定 `start_price_json.session_date`。不得代入 `resolved_at` 或任何處理時間。
           - 作廢列的 `settlement_date` 維持 A-62 R2 的「判定作廢的日期」，LM-131 不用在作廢列。
           - （第十批，提案 2）**T-4 的寫入驗證適用於更正鏈上的每一筆 `resolved` 列，包括 supersede 列**：
             - `settlement_date == end_price_json.session_date` ＝ 重算當下的觀察日集合中，T 之後第 h 個觀察日；
             - `start_price_json.session_date == forecast_record.data_as_of`。
           - **依原因分的取值**：
             - `x2_session_removed`：`end_price_json.session_date` ＝ `x2_shift_json.shifted_t_plus_h`。必須晚於前一列的 `end_price_json.session_date`，因為移除觀察日只會讓 T+h 往後移。
             - `settlement_close_corrected`：兩個 `session_date` 都和前一列相同，只有收盤值不同。P(T) 更正時，`start_price_json` 的值取更正後的收盤；`forecast_record.base_close` 不動（預測端一律用原始列，LG-3）。
             - `window_bar_corrected`、`dividend_factor_corrected`：兩個 `session_date` 都和前一列相同。
           - LM-131 的日期綁定照 T-4，不變。
           - （第十批 R10-5）結算的 P(T) 一律取 `start_price_json`（結算當下讀取的 T 日收盤，可以依 §6.4 更正）；`forecast_record.base_close` 只供預測端與稽核比對，結算不讀。A-63 RC′-2 子點第 2 條約束的 `base_close` 依此限縮為稽核用途（quant 已於事先宣告 v0.12 V12-12 書面確認）。
         - **翻案伴隨句**（RC‴-4）：
           - 「曾有結算結果」的判定謂詞 `had_listed_result(forecast_id)` ＝ 更正鏈中，有一筆被 supersede 的 `status = resolved` 列。這是保守取法，不追蹤實際有沒有渲染過。
           - 謂詞為真時，該紀錄必須帶翻案伴隨句：
             - 最新 outcome 的 `status ≠ resolved`（含 `index_bar_confirmed_erroneous` 與其他作廢原因）時，用 LM-143；
             - 最新 outcome 是重算後的 `resolved`（例如 X2 結算後才確認的順延重算、收盤經獨立來源更正後重算）時，依 `CORRECTION_REASON_FRAGMENTS` 用 LM-150（代入 LM-151／LM-152）或 LM-154。
             - 對應的伴隨句核可之前，這類列 fail-closed，不顯示 label。〔已決：R-5＝LM-143（第九批）；R-7＝LM-150～LM-152（第十批）；FAIL_CLOSED＝LM-154（第十二批）〕
             - R-5、R-7 列入 D_v 前置字面清單，未核可不得進入 D_v。〔已決：R-5＝LM-143（第九批）；R-7＝LM-150～LM-152（第十批）；FAIL_CLOSED＝LM-154（第十二批）〕
           - FL-52 的 `status_reason` 窮舉依這個謂詞分成兩條路徑；謂詞為真的路徑另外涵蓋最新 outcome 是 `resolved` 的情形。
           - **更正原因的列舉 `OUTCOME_CORRECTION_CAUSES`**（第十批，提案 1；風控 R10-1～R10-4），依「被更正的是哪一類資料」分類：
             1. `x2_session_removed`：X2 結算後才確認，T+h 順延重算（事先宣告 v0.11 L1180；A-77）。大盤與個股共用觀察日，兩者都適用。
             2. `settlement_close_corrected`：P(T) 或 P(T+h) 的收盤經更正後重算。大盤指數的依據是事先宣告 v0.11 L1175-1177 的獨立來源；個股是收盤本身的來源更正。
             3. `window_bar_corrected`：結算窗內 T+1～T+h−1 的 bar，或任一 bar 的非收盤欄位經確認有誤（事先宣告 v0.11 L1174、L1185）。這類更正動到的是 `diag_*`、`mae`、`mfe`、`invalidation_*`；個股與族群另外可能因 `split_or_reduction_suspected`、覆蓋率等規則改變 `status`。
             4. `dividend_factor_corrected`：除權息因子更正，包括個股與族群成員（§6.4 第 1 點「來源資料」）。
             - 要增列，須修訂本點並送風控。不屬於上述任何一類的 supersede 不得寫入：寫入函式拒絕，fail-closed。
           - **作廢列不因之後補到的資料而 supersede**（第十批 R10-3；風控 2026-10-18 v0.12 審查 Q12-4）：依事先宣告 v0.12 V12-20，`status ≠ resolved` 的 outcome 一經寫入，不因之後補到資料（T+h bar、正確收盤、除權息因子）而 supersede，適用全部作廢原因。更正作業依規則不重算這類列；補到資料的筆數記在 `forecast_correction_job_end.void_late_data_count`，不計入 `rejected_count`，在 §4.2 揭露。寫入函式仍然拒絕任何把作廢列 supersede 的寫入（縱深防禦，計入 `rejected_count`）。補到資料後的診斷標籤，存放處由 TA 定：只增不改，不得寫入 `forecast_outcome`，列入待決事項，D-9 結算程式實作前定案。
           - **原因怎麼歸屬（確定性規則）**：
             - 更正作業把啟動當下所有還沒處理的觸發一次讀入，寫進 `triggers_json`。觸發包括 `x2_confirmed_non_session` 事件、收盤更正的查證紀錄、來源修訂、因子修訂。
             - 對每一筆重查的 outcome，`correction_causes` ＝ 受影響日期和該筆結算窗 [T, T+h] 有交集的所有觸發，所屬類別的集合。
             - 重算後沒有任何欄位改變的筆不寫入（§6.4 第 3 點）。
             - 這個歸屬只會多記、不會少記，多記的結果是 fail-closed。
           - **寫入時的一致性驗證**（不成立就拒絕）：
             - 含 `x2_session_removed` ⇒ `x2_shift_json` 非 null，而且 `x2_event_ids` 包含 `triggers_json` 中與本筆有交集的 X2 事件。
             - `correction_causes ＝ [window_bar_corrected]`、而且 `status = resolved` ⇒ 新列的 D 欄位和前一列逐位相同（D 欄位的定義見下方「診斷欄位更正的例外」）。理由：已實現的報酬與標籤只取決於 P(T)、P(T+h) 和因子，這類更正動不到它們，所以不同就表示歸類錯了。
             - **單一原因的差異驗證**（R10-2；不成立就拒絕寫入）：
               - `[x2_session_removed]` ⇒ 新列的 `end_price_json.session_date` 晚於前一列，而且等於 `x2_shift_json.shifted_t_plus_h`；
               - `[settlement_close_corrected]` ⇒ 兩個 `session_date` 都和前一列相同；`start_price_json`、`end_price_json` 的收盤值至少有一個不同；`window_factors_json` 和前一列相同；
               - `[dividend_factor_corrected]` ⇒ 兩個 `session_date` 都和前一列相同，`window_factors_json` 和前一列不同。
               - 理由：LM-151、LM-152 陳述「哪一類資料被更正」，差異必須和陳述相符。
           - **`CORRECTION_REASON_FRAGMENTS`**：封閉對照表，放在 `display.py`，鍵恰好是 `OUTCOME_CORRECTION_CAUSES` 的全部值。

             | `correction_causes` | 呈現 |
             |---|---|
             | `[x2_session_removed]` | LM-150＋LM-151 |
             | `[settlement_close_corrected]` | LM-150＋LM-152（P(T)、P(T+h) 的收盤更正都適用；R10-5 依事先宣告 v0.12 V12-12 書面確認，與本 ADR 同批生效） |
             | `[window_bar_corrected]` | `correction_is_display_neutral(chain)` 為真 → 不帶伴隨句；否則 FAIL_CLOSED |
             | `[dividend_factor_corrected]` | FAIL_CLOSED |
             | 兩個以上 | FAIL_CLOSED |

             FAIL_CLOSED 的列以 `MaskedRecordView` 回傳，狀態句是 LM-154。不設 P(T) 更正的確認旗標或常數：R10-5 的確認與本表同批生效；日後若撤回 V12-12 的確認，須修訂本表並送風控。
           - **選用規則**：只在 `had_listed_result` 為真、而且最新 outcome 是 `resolved` 時查表，用最新 outcome 的 `correction_causes`（LM-150 ⑦）。最新 outcome 不是 `resolved` 時走 LM-143，不查表。
           - **診斷欄位更正的例外**（第十批，提案 3；方向：放寬，風控 2026-10-17 核可，列入 CEO 知悉）：
             - **D 欄位** ＝ {`status`, `status_reason`, `realized_label`, `hit`, `realized_return`, `realized_log_return`, `realized_z`, `settlement_date`, `start_price_json`, `end_price_json`, `baseline_hits_json`}。比較方式是正規化 JSON 的位元組逐位相同。
             - D 欄位還必須涵蓋 `SettledRecordView` 與任何回應中，該列帶出的全部 `forecast_outcome` 衍生欄位，包括 `realized_return_display`，以及任何回應中出現的 `invalidation_*`、`mae`、`mfe`、`diag_*`（R10-6）。
             - **例外**：`had_listed_result` 為真時，若同時符合以下兩項，這筆紀錄不帶 LM-150，照一般已結算列呈現（LM-131 → LM-22／LM-132 → LM-146 → LM-92）：
               - 更正鏈的每一列都是 `status = resolved`，而且 D 欄位都逐位相同；
               - 每一個 supersede 列的 `correction_causes` 都是 `[window_bar_corrected]`。
             - 任一項不成立，就依上述 `CORRECTION_REASON_FRAGMENTS` 對照表處理。更正鏈只要曾經作廢、或曾經有任何其他原因，都不適用例外。
             - 判定只由後端的單一函式 `correction_is_display_neutral(chain)` 產生，前端不得自行判斷。
             - 被豁免的筆數照實揭露在 §4.2（「診斷欄位更正筆數」），由 quant 登記。
         - 驗證見 FL-59。
       - （第九批，提案 5；A-65）**顯示字串介面**：
         - **單一函式 `format_ratio_as_pct(ratio, *, signed) -> str`**：放在 `app/forecast/display.py`，是純函式。
           - 計算：`Decimal(float(ratio))` 精確轉換 ×100，再 `quantize(Decimal("0.01"), ROUND_HALF_UP)`。Python decimal 的 ROUND_HALF_UP 就是遠離零。不經 str 中間值。
           - `signed=True`：正數加「+」，負數加「−」（U+2212）；捨入後為零時輸出「0.00」，不帶正負號。
           - `signed=False`：要求 ratio > 0。
           - 非有限值一律拋出例外。
           - 輸出不含「%」。
         - **回應欄位**：
           - 凡依下方 LM-146 條件帶 LM-146 的紀錄列，以及單筆展望區塊（LM-93／LM-115），都帶 `threshold_display = {down, up}`（不帶正負號）；
           - 有 LM-131 的列，另帶 `realized_return_display`（帶正負號）；
           - 這三個字串由同一個函式產生。
         - **封閉 schema**：`SettledRecordView`、紀錄列 view、`OutlookView` 都不得帶 `up_pct`、`down_pct`、`realized_return`、`realized_log_return`、`realized_z` 的原始數值。前端只把字串原樣代入，不得對它們呼叫 `toFixed`、`Intl.NumberFormat`、`Math.round`、`parseFloat`（前端 AST 測試）。
         - **片段 ID 由後端決定**：
           - 列的 `disclosure_fragment_ids` 含 LM-146，若且唯若該列渲染 LM-131，或是在非作廢列渲染 `label`；作廢列經 LM-133 顯示的 label 不算。`threshold_display` 的帶出條件相同。
           - 含 LM-92，若且唯若該列有 LM-131。
           - `record_list_header` 含 LM-147，若且唯若至少一個大盤列含 LM-146；含 LM-148，若且唯若至少一個個股列含 LM-146。
           - 族群列若需要 LM-146、但族群變體尚未核可 → 該列不顯示 label（fail-closed）。
         - 判定一律用未四捨五入的值（事先宣告 v0.11 L507、L514）。`scoring.py`、`validation.py` 不得可達 `format_ratio_as_pct`。
         - 驗證見 FL-59。
   - 12. **display_state 單值優先序**（r2，A-28）：優先序 `suspended_f3` > `withdrawn_f2` > `gated` > `shown`，不變。
     - (i) **`suspended_f3` 期間，負面結果照常生效**：檢查點照常計算；降級與 F-2 下架照常生效，`withdraw_reason`、`withdrawn_at_n` 照寫。
     - (ii) **正面結果不認列**：升為 `better_than_baseline`、重新上架，都不認列。
       - snapshot 的 `status` 記不認列之後的有效狀態；
       - 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}}`；
       - 有 `withdraw` 區塊時，設 `positive_suppressed_during_f3 = true`；
       - quant 的檢查點檢討紀錄要揭露這件事。
     - (iii) **與 A-22 的交互作用**：暫停期間剛好碰到 n＝150（族群 250），原始結果是正面但不認列時，有效狀態不是 `better_than_baseline`，條件二成立，以 `f2_deadline` 下架。**不得因此延後退出期限。** LM-74 在這種情形下仍然屬實。
     - (iv) `display_reasons_json` 的結構改為 `{suspend: [...], withdraw: {...}|null, gate: [...]}`（r3，A-57；RC′-1）。
       - **`gate` 不論 `display_state` 都要計算。** 每一筆 snapshot 都列出當下成立的 `gate` 值，範圍是 `GATE_FIXED` ∪ 已啟用的 `GATE_ADDITIONAL`；封閉列舉、固定排序。
       - 沒有成立值時寫 `[]`，任何狀態都不得為 null。`suspended_f3`、`withdrawn_f2` 期間照算照寫。
       - 第 12 點的優先序只決定顯示哪個狀態，不得讓 `gate` 變成 null 或被清空。`display_state = gated`，若且唯若 suspend、withdraw 都不成立，而且 `gate` 非空。
       - **查詢時的有效集合 G_eff**：G_eff ＝ snapshot 的 `gate`；族群的 `pa9_holds` 依 RC′-2 為真時，再加入 `forward_n_below_min`；大盤與個股的 `n_disclosure_masked` 為真時，再加入 `validation_refresh_pending`（見下方「查詢時閘門」）。沒有 snapshot 的大盤與個股依該條的「沒有 snapshot」子點。
         - `OutlookView.display_state` 與 `unavailable_reason`，由 snapshot 的 suspend、withdraw 加上 G_eff，依第 12 點優先序彙整。
         - 這個查詢時調整只可能把 `shown` 變成 `gated`（族群經 `forward_n_below_min`；大盤與個股經 `validation_refresh_pending`），不得有其他方向（性質測試，三個 scope）。
         - `validation_status` 仍取 snapshot 原值。FL-54 (e) 的「同一列」只有這一個例外。
         - v0 的 plan 只引用個股（第 8 點），不受影響。
         - `views` 對外回傳的 `display_state` 一律是調整後的值；任何回應 schema 都不得同時帶 snapshot 原始的 `display_state` 與調整後的值，snapshot 原值只留在資料表供稽核。FL-54 (e) 加一格封閉 schema 斷言。
       - **查詢時閘門 `validation_refresh_pending`**（第九、十批，C9-7 甲案；風控 2026-10-18 C9-7 與 Q-3 提案確認 C7-1～C7-8）：列入大盤與個股的 `GATE_FIXED`；族群不用這個值，族群依 RC′-2 加入 `forward_n_below_min`。
         - 成立，若且唯若 `n_disclosure_masked` 為真。只在查詢時加入 G_eff。snapshot 寫入時依 A-63 以 `e_changed_since = False` 計算，所以 snapshot 的 `gate` 永遠不含它。
         - 效果是 `shown` 變成 `gated`；`suspended_f3`、`withdrawn_f2` 照 snapshot。性質測試見上方『查詢時的有效集合 G_eff』一點。
         - 沒有 snapshot 時（大盤、個股）：`display_state = gated`；G_eff ＝ {`validation_refresh_pending`} ∪ 可在查詢時判定而且成立的固定值（例如 `replay_review_pending`）。不加入 `forward_n_below_min`：n 未知，LM-128「前瞻紀錄樣本不足」無從確認屬實；fail-closed 已由 `validation_refresh_pending` 達成。FL (a) 的「沒有 snapshot」格另外斷言：找不到 LM-128。
         - `plan_reason` 不登記這個值：plan 在 snapshot 之後讀 T 日 snapshot 計算（A-4）。v1 的個股常駐 `replay_review_pending`，plan 不受影響。日後依 §4.7 開放個股之前，要先補一句涵蓋這個值的 `plan_reason` 片段。FL-52 的 P(symbol, `plan_reason`) 不含這個值。
         - 上一點的豁免要綁前提（風控 2026-10-18 C7-5）：FL-52 與 `gate_coverage_gaps` 對 (symbol, `plan_reason`) 的窮舉不含 `validation_refresh_pending`。這個例外只在以下兩個前提同時成立時有效：`REPLAY_APPROVAL_SCOPES` 不含 `symbol`；(symbol, `first_layer`) 依事先宣告 D-20 ③ 對政策表一律 `surface_not_permitted`。FL-52 另加一格：兩個前提任一不成立時，本例外失效，(symbol, `plan_reason`) 含 `validation_refresh_pending` 的子集沒有覆蓋片段即判定失敗。
         - 變動上述任一前提的 PR，必須同時讓 plan 端的展望引用在渲染時經過查詢時閘門（`validation_refresh_pending` 成立時，該展望條件視為 unavailable，依事先宣告 D-19），並附涵蓋這個值的 `plan_reason` 片段，送風控；否則不得合併。
         - **原子片段**：`validation_refresh_pending` 用 LM-144「前瞻紀錄筆數待彙整」，`covers = {validation_refresh_pending}`，scope 為大盤、個股；登記見上方 `GATE_FRAGMENT_REGISTRY`。
         - **徽章**：大盤與個股遮蔽時同樣回 `ValidationBadgeMasked`（LM-153）。
         - **LM-12**：遮蔽時選不到。`outlook_block` 改用 LM-120，原子依 GR 取 LM-128（`forward_n_below_min` ∈ G_eff 時）、LM-130、LM-144。
           - E 變動事件不會讓 n 增加（作廢列不改回結算：R10-3、事先宣告 v0.12 V12-20），所以遮蔽期間選用 LM-128 的依據（判定所用的 snapshot 的 `gate` 含 `forward_n_below_min`）不會因該事件而失真。
           - 失效條件：R10-3／V12-20 日後若允許作廢列改回結算，或新增任何會讓 n 增加的 E 變動事件，本點與 FL (d) 要一併重審。
         - **GR 順序**：見 `GATE_FRAGMENT_REGISTRY`（A-63 第 11 點）。FL 見 §對實作的約束 FL-52「大盤與個股的遮蔽 FL」。
       - **`gate` 的值分成兩類：**
         - **固定啟用**：來源是 accepted ADR 或風控底線，不受 #10 參數關閉。
         - **#10 可加**：只能由 #10 的裁示加入。

       | `gate` 值 | 大盤 | 族群 | 個股 | 類別與來源 |
       |---|---|---|---|---|
       | `forward_n_below_min` | 若 quant 有登記前瞻門檻就固定；沒有登記就不適用 | **固定**（PA-9：E 內 n<150，判定用 `pa9_holds`，見第 4 點第 11 項 (c)） | 同大盤 | 族群：PA-9／LG-15。大盤與個股：〔未查證〕quant 是否登記，交 quant 確認 |
       | `replay_review_pending` | **固定** | **固定** | **固定** | ADR-0025 D-6.6 |
       | `shadow_run_pending` | #10 可加 | #10 可加 | #10 可加 | 決策包 #10 (b) |
       | `settlement_smoke_pending` | #10 可加 | #10 可加 | #10 可加 | PRD 記載的風控建議 |
       | `validation_refresh_pending` | **固定**（只在查詢時加入 G_eff，不寫入 snapshot） | 不適用（族群依 RC′-2 加入 `forward_n_below_min`） | **固定**（同大盤） | C9-7 甲案（風控 2026-10-18）：`n_disclosure_masked` 為真時成立 |

       - `replay_review_pending` 成立，若且唯若該 claim 的 (scope_kind, horizon) 在 `forecast_ledger_events` 沒有 `kind = replay_review_approved` 事件。
         - 事件要附回放報告路徑，以及 quant 與 qa 的審查紀錄路徑；真偽由 qa 核對。
         - 回放若以更細的單位做（例如 scope_key），以較細者為準，這只會更嚴。
         - 某個 scope 沒有回放報告時，這個值會常駐，LM-98 選不到，改用 A-63 第 5 項。
         - **`replay_review_approved` 的寫入前提**（風控 2026-10-17 RC′-8；事先宣告 §4.7、§12）：
           - payload 必須帶 `replay_claim_id`。寫入函式在同一個交易內驗證四件事：該 claim 在 `forecast_claim_registry` 存在、`kind = replay`、(scope_kind, horizon) 與事件相同、`counts_toward_m = 1`。任一項不成立就拒絕寫入。
           - payload 另帶回放報告路徑、quant 與 qa 的審查紀錄路徑，以及報告中「已知偏誤揭露」一節的定位。qa 核對報告確實揭露已知偏誤；族群與個股要揭露存活者偏差，以及除權息紀錄的起點。
           - **不得用一份名目上的回放報告，或已知有偏誤卻沒有揭露的回放報告，來解除閘門。**
           - 族群與個股另外要先完成事先宣告 §4.7 的修訂並經核可。現行 §4.7 規定這兩類重放「只能當內部研究…不上畫面」，修訂核可之前，不得為族群或個股寫入這個事件。這是把既有約束明列出來，不是另立規則。
           - （第九、十批；風控 2026-10-17 疑義裁定回送確認的 suggested，族群的 `replay_review_approved` 只能出現在測試 fixture）事先宣告 §4.7 的修訂核可之前，以下各點成立：
             - 寫入函式另外驗證 claim 的 `scope_kind` ∈ `REPLAY_APPROVAL_SCOPES`。`display.py` 定義 `REPLAY_APPROVAL_SCOPES: Final = frozenset({"market"})`，不得由參數、設定檔或環境變數改變（比照 ADR-0028 CS-12）。
             - 啟動時檢查：主 DB 若已有 scope 不在這個集合內的 `replay_review_approved` 事件，拒絕啟動。
             - FL-58 (e1) 第二格與 (e2) 用到的事件，由測試 fixture 以 SQL 直接插入暫存 DB，不經寫入函式。這兩格另外斷言：同一筆 payload 經寫入函式會被拒絕。
             - grep／AST：`app/` 下沒有以 sector 或 symbol 建構這個事件的程式碼。
       - **#10 只能加，不能減。** `display.py` 定義 `GATE_FIXED`（依上表逐 scope 列出）。#10 的參數只接受 `GATE_ADDITIONAL: frozenset`，而且必須 ⊆ {`shadow_run_pending`, `settlement_smoke_pending`}。
         - 參數含有其他值、含有任何停用或覆寫固定項的鍵，或試圖把固定項設成 false，loader 都拒絕，啟動失敗。
         - #10 可加的值沒有被加入時，不得出現在 `gate`。
         - 要關掉任何固定項，須修訂本 ADR、經 CEO 核可、送風控。
         - **loader 守門**（增補 T-1）：啟用任一 `GATE_ADDITIONAL` 值時，loader 要用和 FL-52 同一個函式 `gate_coverage_gaps(...)`，檢查每個 (scope_kind, slot) 中含該新值的每一個非空子集，是否都有已核可的覆蓋片段。缺任何一個，就拒絕啟用、啟動失敗（fail-closed）。
       - **LM-98 守門**：`scope_kind == symbol`，而且 `gate == [forward_n_below_min]`，另外要求 `unavailable_reason = gated`。其他組合沒有核可片段，FL-52 (c) 失敗（列入 A-63 第 5 項）。
       - 驗證見 FL-53 (f)。
     - (v) 每一筆 snapshot 都由當下的 (F-3, F-2, 閘門) 各項狀態彙整出 `display_state`，不讀上一筆的 `display_state`。
       - 恢復只代表下一筆 snapshot 重新彙整，**不觸發任何新的判定**；
       - 升級與重新上架，只能在恢復之後的下一個事先宣告的檢查點重判。
     - (vi) quant v0.9 登記相同文字。
5. **開盤基準 fail-closed**（風控第 4 項）：開盤基準算不出來，或開盤欄位口徑未查證時，顯示面預設附上隔夜跳空的直白句。
6. **F-3**（M-11）：
   - 上限依 quant 登記：逾時率 >10%（定義見下一點，r1，A-8）、digest 不一致率 >2%、PIT 違規 ≥1 筆；
   - **逾時率**（r1，A-8）＝每個 claim 在最近 60 個觀察交易日（D-8.1 的定義，含 `computed_for_session`）內，排程紀錄中 `late=1` 的比例。
     - 缺日不進分母（缺日由失效條件 F-3 管）。
     - 不足 60 日時怎麼算，由 quant 在 v0.5 登記。
   - digest 的分母是 min(250, 已結算筆數)；
   - **PIT 違規的偵測**（r1，A-8）：結算時，或稽核作業依 `input_digest` 涵蓋的列重算 `inputs_max_recorded_at`。若結果大於 `cutoff(T)`，就寫一筆 `pit_violation_confirmed` 事件。
   - **暫停原因**（r1，A-8；封閉列舉，可同時多值，固定排序）：`pit_violation`、`digest_mismatch`、`late_rate`，寫進 `display_reasons_json`。
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
- (v) 作廢率 >5% 時（底線 3），依『逐檢查點判定』第 1 點的公式逐檢查點套用 W；本 ADR 不另寫第二種表述（FL-32）。
- (vi) 不得用放寬 §4.3 或 α\* 的方式改變下架結果（底線 4；那屬於 C-3）。
- (vii) C-8 必須在 D_v 前定案。之後只能往更嚴的方向改，而且要升版、留紀錄（底線 7）。

**下架原因列舉值（r1 新增，A-9；接在共同部分之後）**
- `withdraw_reason`（單值，封閉列舉，依優先序）：
  - （r2，A-23）`f2_invalid_stop`：`fail_normal(c₀) AND fail_normal(c₁)`；
  - `f2_deadline`：條件二成立；
  - （r2，A-23）`f2_invalid_stop_worst_case`：條件一成立，但上式不成立；
  - （r2，A-23）優先序：`f2_invalid_stop` > `f2_deadline` > `f2_invalid_stop_worst_case`。
- 寫進 snapshot 的 `display_reasons_json`，並同時記錄 `withdrawn_at_n`。
- 條件一必須讀兩個檢查點的 `eval_kind=checkpoint` 列在 `stats_json` 中的同一份計算（一般情境與 W 情境各存一份），不得另外計算一次。
- CEO 若選 F2-A，列舉值在 C-8 決策時另外定，片段要重寫。

**逐檢查點判定（r2，A-23；整條取代 r2 版；原因值與優先序併入上方列舉）**
1. **逐檢查點判定**。相鄰兩個檢查點記為 (c₀, c₁)，對每個 c：
   - `fail_normal(c)`：一般情境下，模型點估計在共同子集上 ≤ 任一必備基準；
   - `fail_w(c)`：W 情境下做同一個比較；
   - 兩者都讀該檢查點 `eval_kind=checkpoint` 列的 `stats_json`，不另外計算。
   - `fail(c) = fail_normal(c) OR (void_rate(c) > 5% AND fail_w(c))`；
   - `void_rate(c)` 讀該檢查點 checkpoint 列的值，定義依事先宣告 §4.3 (f)（v0.8 L576）：作廢列 ÷（已結算列＋作廢列）；
   - 條件一成立，若且唯若 `fail(c₀) AND fail(c₁)`；不要求兩個檢查點的作廢率都 > 5%。
2. **原因值與優先序**：見上方『下架原因列舉值』。
3. **`display_reasons_json.withdraw`** 的結構：`{reason, conditions_met, pair: [{n, void_rate, fail_normal, fail_w}, …], positive_suppressed_during_f3: bool}`。最後一個欄位見 A-28。
4. **片段**：
   - `f2_invalid_stop_worst_case` 在 LM-81 中用 LM-87（WC-a，第五批條件核可），要完整渲染，不得截斷。
   - LM-87「連續兩個檢查點（n＝{X0}、n＝{X}）的結果都不高於基準；其中作廢比例超過 5% 的檢查點，依最不利情境（作廢的預測全數視為不符）計算」由第 1 點的逐檢查點規則保證屬實，滿足 LM-87 的核可條件，不必重送。
5. **兩張對照表**：
   - `LM81_WITHDRAW_REASON_FRAGMENTS` ＝ {`f2_invalid_stop`: LM-75, `f2_deadline`: LM-74, `f2_invalid_stop_worst_case`: LM-87}；
   - （r3，A-58）`LM79_WITHDRAW_REASON_RENDER: Mapping[withdraw_reason, (template_id, reason_fragment_id | None)]`：
     - `f2_invalid_stop` → (LM-79, LM-75)；
     - `f2_deadline` → (LM-79, LM-74)；
     - `f2_invalid_stop_worst_case` → **(LM-104, None)**。LM-87 是 LM-104 核可全文的一部分，不是代入 LM-79 的片段。
   - LM-79 讀前一版的原因時，經 `views` 讀前一版 claim 最後一筆 withdrawn snapshot。
   - （r3，A-58）LM-79 的原有條件同樣適用 LM-104。qa-e2e 在 375 寬度驗收。
6. （r3，A-58）已由 LM-104 滿足（第六批 R6-04）。
7. **quant v0.9**：把相同文字登記進 §4.5 的條件一（v0.8 L643）與底線 3（L658），方向標「補定義（逐檢查點；比『兩點都 > 5%』嚴）」，在 D_v 前完成。C-8 若已經裁示，以知悉項送 CEO。

**主方案 F2-B（B 型無效停止規則，風控建議，我同意）**
- 下架條件一（無效停止）：自 N_MIN 起，**任兩個相鄰檢查點**（滾動計算：30 與 60、60 與 100……）的模型點估計，在共同子集上都 ≤ 任一必備基準，就下架（底線 1）。
- 下架條件二（退出期限）：在 n＝150（族群 n＝250）的檢查點，狀態不是 `better_than_baseline`，就下架（底線 2）。
- **VETO 底線**：
  - 下架條件不得比條件一寬，也不得改成「證明比基準差」（例如區間上緣低於基準）；
  - （r2，A-22）不得刪除條件二（風控 VETO）。
  - （r2，A-22）**任何時點都不得延後：**
    - C-8 定案前，選項集合已經凍結（事先宣告 §4.5），退出期限 n＝150（族群 250）不在可以調整的範圍內；
    - C-8 定案到 D_v 之間，依共同部分 (vii)；
    - D_v 之後，只能往更嚴的方向改（例如提早退出期限），而且要升版、留紀錄。
  - （r2，A-22）原本「CEO 書面同意即可延後」的路徑刪除。依據：事先宣告 V6-03。
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
（r2，A-33）G-1～G-6 全部成立之前，不得寫入任何 `trigger=scheduled` 的前瞻紀錄。強制方式分三種：
- **recorder 執行期強制**：G-3、G-4；以及 dirdef 必須含 `f2_variant`、`c8_decision_ref`、`c8_decision_sha256`（G-2 的登記部分）。recorder 不比對雜湊，也不讀決策檔。
- **G-2 的機器部分**（r3，A-82）：
  - `f2_variant: Literal["F2-A", "F2-B"]`，沒有預設值，屬於 `definition_logic_sha256` 的範圍（承接 FL-37）；
  - `c8_decision_ref` 是 repo 相對路徑；`c8_decision_sha256`；
  - 缺任何一欄，dirdef 就無法凍結；
  - recorder 執行時不讀 `docs/`、`work/`；
  - 這份紀錄是不是 CEO 本人的決定、內容與 `f2_variant` 是否一致，由 qa 核對。
- **CI 檢查**：`c8_decision_sha256` 與 ref 所指的檔案相符。這不是 recorder 執行期的閘門。
- **qa-reviewer 在 PR 核對**：G-1；G-2 的真偽，以及決策紀錄內容與 `f2_variant` 是否一致；G-5；G-6。
- G-7 是 on-demand 寫入的閘門。
- **連帶**：quant v0.9 把事先宣告 v0.8 L639 改成同樣精確的三分寫法。現行的「不是程式強制的機器閘門」在 r2 套用後會低報。

各閘門內容（風控第 1 項、底線 7、R-116）：
- G-1：ADR-0027 accepted。
- G-2：C-8 定案。
- G-3：`dirdef-v1.0` 與各規則凍結並 commit，F-3 上限一併凍結；registry 中 `frozen_commit`、`rules_sha256`、`prereg_doc_blob` 都非 NULL。
- G-4：ADR-0028 VS-6 的 `verified_on` 非 None。
- G-5：ADR-0026 D-8、D-6 已上線，D-9 備份組至少成功產出一次。
- G-6：`app/forecast/**` 的 PR 通過 qa-reviewer 與 Codex。
- G-7：on-demand 紀錄的寫入，同樣要 G-1～G-6 全部成立。強制方式和排程紀錄相同（A-33）。on-demand 的寫入路徑和排程呼叫同一個閘門函式。on-demand 紀錄一律不屬於 E。（r3，A-72）
  - **寫入被閘門拒絕時**（G-1～G-6 任一不成立）：
    - `POST /api/outlook/symbols/{symbol}` 先評估閘門。拒絕時，不呼叫展望計算，也不計算、不回傳任何 label 或方向衍生欄位。
    - 回應用封閉 schema `OnDemandGateClosedView`（`extra="forbid"`），HTTP 200。白名單只有：`symbol`、`trigger`（固定 `on_demand`）、`recorded`（固定 false）、`availability`（固定 `unavailable`）、`status_fragment_id`、`disclosure_fragment_ids`。不帶 `forecast_id`、`data_as_of`、`label`。
    - 不得有任何 route 計算 on-demand 展望卻不經過寫入閘門（不得「算了但不落帳」）。kind 為 `on_demand` 的 route 都要呼叫同一個閘門函式（A-74）。
    - `disclosure_fragment_ids` 的型別是封閉列舉 `ON_DEMAND_CLOSED_DISCLOSURES`（`display.py`，`Literal`）。
      - 清單每一項都要有風控核可的片段，**不得含任何方向衍生片段**。凡是提及、暗示或預告方向、label、天氣、方向色、「結算後列示」的片段都算，包括 LM-94、LM-95、LM-105、LM-106。
      - 增列要修訂本點並送風控。核可之前清單為空。
    - `status_fragment_id` 也是封閉列舉。v1 只有一個值，就是下方的新狀態句。
    - FL-52b (9b) 的全文掃描，涵蓋 `status_fragment_id` 與 `disclosure_fragment_ids` 渲染出來的全文，不只掃 JSON 欄位。FL-38 的 schema 斷言另加：清單以外的 ID 驗證失敗。
    - **新狀態句的限制**（交 creative-lead 起草）：不得預告開始記錄的日期，也不得暗示「快要開放」。
    - **前端不得補方向**：渲染 `OnDemandGateClosedView` 的元件，不得引用 `OutlookView` 衍生型別。收到這個回應之後，也不得改從其他端點取得同一檔的 label、天氣或方向色（前端契約測試，比照 FL-60 (d)）。
    - **狀態字面**：建議新句，語意是「正式記錄開始前，臨時查詢不提供方向」，交 creative-lead 起草、風控逐字審。若改用既有片段，要先經風控單項確認。核可之前，FL-52 (d) 失敗。
    - 驗證見 FL-38。

D_v ＝該 claim 第一筆 `trigger=scheduled`、`late=0`、`supersedes_id IS NULL`、kind＝forward 的 `forecast_record` 的 T（r1，A-10）。
- 不排除 PIT 違規，也不看 label。
- 用查詢導出，一經出現就不會移動：之後的 PIT 違規確認、更正、補跑都不改變 D_v；§4.1 的不重疊格點以它為第 0 相位。
- 因為只增不改，而且 late=0 的紀錄必定早於下一個 session 的紀錄，所以這個最小值是穩定的〔推論〕。

### D-15 政策表與行動紀錄（風控第 12 項、R-6 第 3 點）
1. **成本禁用範圍**（r1，A-1；對齊事先宣告 v0.4 V4-03／LG-16）：以下兩類規則的任何條件樹，不論 action 為何，`field` 與 `ref` 都不得引用持倉成本，或由成本導出的欄位。
   - (a) 經 `app/advice/loader.py::load_rules(path)` 載入的全部 advice 規則 YAML（任何路徑；之後新增的檔案自動納入）；
   - (b) 政策表 v0（`app/plan/policy.yaml`）與之後的各版。
2. **禁用集合只有一個來源**：
   - `app/advice/context.py` 新增 `COST_DERIVED_FIELDS: frozenset[str]`，v1 內容為 `{"position.unrealized_pnl_pct"}`；
   - 同一個檔再定義 `POLICY_FORBIDDEN_FIELDS = COST_DERIVED_FIELDS | {"avg_cost", "cost", "cost_anchor", "pnl_vs_cost"}`；
   - ADR-0021 K-1 的 `ADVICE_RULE_FIELDS` 不修改，成本禁用是另一道獨立的檢查。
3. **守門位置**：寫在 `RuleSet` 的 model validator，與 ADR-0021 K-3 的 `_fields_are_evaluable` 同一層。`load_rules(path)` 經 `RuleSet.model_validate` 必定會跑到它；直接呼叫 `model_validate` 也一樣被擋。錯誤訊息沿用 `<檔名>：規則 <id> 的 condition -- …`，並寫明依據 ADR-0027 D-15。政策表的 loader 用相同的形狀。
   - 3a.（r2，A-31）**執行期守門**：`RuleSet`、`Rule`，以及政策表的 model（`app/plan/policy.py` 的 `PolicyTable` 與它的規則、條件 model）覆寫兩個方法，錯誤訊息都引用 ADR-0027 D-15：
     - `model_construct` 一律 raise `TypeError`；
     - `model_copy` 在 `update` 不是 None 時 raise `TypeError`；不帶 `update` 的複製可以。
     - `Comparison` 不加守門。它被 alerts 共用（`alerts/models.py:36`），而 `RuleSet` 的 after validator 會重新檢查全部欄位，所以不需要。
   - 3b.（r2，A-31）**AST 測試**（範圍 `app/**`）：
     - 不得出現 `<受守門的類別名稱>.model_construct(`；
     - `app/advice/**`、`app/plan/**` 不得出現 `object.__setattr__`；
     - 3a 的覆寫必須存在。
     - 為什麼要兩層：AST 判斷不了 `x.model_copy(update=…)` 的接收者型別〔事實：`app/` 有 20 多處合法用法，例如 `advice/engine.py:328`〕，型別盲區由 3a 補上。
   - 3c.（r2，A-31）**政策表的 loader**：唯一的建構路徑是 `app/plan/policy.py::load_policy(path)` → `PolicyTable.model_validate`。`PolicyTable` 用 after validator `_no_cost_fields`，把所有條件欄位與 `POLICY_FORBIDDEN_FIELDS` 比對；錯誤訊息形狀同 advice 規則，也套用 3a。
   - 3d.（r2，A-31）`PolicyTable` 與它的規則、條件 model 一律用 tuple。這是新程式，沒有遷移成本，所以是 required。
   - 3e.（r2，A-31；suggested）`RuleSet.rules`、`AllOf.all`、`AnyOf.any` 改用 tuple。
   - （r2，A-31）**對既有程式的影響**：`scripts/drawdown_rule_diff.py:100-107` 用了 `Rule.model_copy(update=…)` 和 `RuleSet.model_copy(update=…)`。要在同一個 PR 改成 `RuleSet.model_validate({**current.model_dump(), …})` 重建。`tests/test_drawdown_rule_diff.py` 要維持綠燈。
4. `build_context` 若新增任何由成本導出的欄位，必須同時加入 `COST_DERIVED_FIELDS`（由 FL-41b 擋）。
5. `app.outlook.*` 不可達 `app.positions.*`、`app.portfolio.*`、`app.advice.context`（展望規則在結構上就沒有成本可以讀）。
6. 原第 3、4 點保留：
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
- 第一筆前瞻紀錄要等六道閘門（G-1～G-6；on-demand 依 G-7 同樣適用）；08:30 若一直查證不到，記錄就一直不能開始。
- F2-B 下，尚未證明的展望最長會顯示約 3 年（大盤 5 日）。誠實度依賴「驗證中」直白句，以及風控的版面限制（不得用綠色、勾號、進度條）。
- M-9 若採 P-1，價位與券商的未還原 K 線不一致，每次除權息都會整組平移；`plan_outcome` 要做換算。
- **展望鏈與持倉鏈的資料源不同**：展望讀市場 DB，持倉讀 `price_bars_cache`。同一個 T 的原始收盤可能不同，plan 必須檢查一致性（FL-25）。
- 15 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。
- 主 DB 每年約增加 220 MB〔推論〕。
- 主機晚上不開機，樣本就不會增加（quant §4.9 的 g）。
- 規則 YAML 必須把文字欄位與邏輯分開，否則 logic 雜湊無法定義。
- API process 會寫入 on-demand 紀錄，因此預測帳有兩個寫入者，靠 SQLite 的序列化與 `busy_timeout` 處理。
- （r2，A-35）**D-20 的兩面後果**（給 PM／CEO）：
  - 個股展望在 v1 期間不論驗證狀態，對政策表都是 `surface_not_permitted`，所以 `consider`、`add_conditional` 會長期無法成立（v1 期間個股與族群的 `unavailable_reason` 實際是 `gated`，因為 `replay_review_pending` 常駐；`gated` 的優先序高於 `surface_not_permitted`）；
  - 防禦端同樣長期不會因展望觸發：政策表序位 7 的第一項、`avoid` 的展望項；
  - 畫面只能寫「5 日展望目前不可用（原因），本判斷未納入」。
- （r2，A-35）A-31 的守門要改寫一支研究腳本；之後不得用 `model_copy(update=…)` 重建規則集。
- （r2，A-35；r2'' 依風控 2026-10-17「追加一」）on-demand 查詢從 T+1 08:30 起，到新的 T 進入市場 DB 之前（大致是交易日白天），POST 回應與紀錄清單都不顯示 label，只顯示狀態片段與資料日期。
  - 要等結算之後，才以「已結算紀錄＋實際結果」列示，不會補成目前展望（A-36）。
  - 影響範圍主要是不在排程範圍內的個股；排程範圍內、T 日排程紀錄已存在的個股，POST 直接回傳排程紀錄。
  - 這段期間臨時查詢的用途會變小，**PM 與 CEO 都要知悉**（風控 2026-10-17「追加一」suggested）。
- （r3，A-79）**D_v 前要核可的字面增加**：A-55 (e) 要求「優於基準」狀態的伴隨揭露先核可，否則 D_v 不能開始，即使優於基準預期是好幾年後的事。A-62、A-63、A-65 的片段（清單狀態片段、「已結算＋實際結果」片段、作廢列的呈現）也都屬於 D_v 前置。
- （r3，A-79）**交易時段開機的影響**：主機如果在交易日收盤定案前開機，市場資料可能只抓到盤中值。當天如果沒有定案後的 run 補寫，該日不寫前瞻紀錄（記 `inputs_not_ready`）；該日若依 D-8.1 仍是觀察日（例如大盤有定案列），會留下缺日列，不會補造。之後約 60 個交易日內，部分紀錄可能判成證據不足或作廢，E 內的作廢列計入最壞情境（A-78）。
- （r3，A-79）**`inputs_not_ready` 的影響**：大盤 T 日 bar 必須是定案列才能用。強制重抓一次仍不成立時，該日不寫前瞻紀錄，記 `inputs_not_ready`，不用暫定值頂替，也不改用前一個 session；該日是觀察日時留下缺日列（A-75）。
- （r3，A-79）**紀錄清單拆成三個端點**：依 scope 拆成 market、sectors、symbols 三個端點，每個端點只回傳自己的 scope，不設總端點（A-71，見 D-11.4 第 11 點）。
- （r3′，A-79）**正式記錄前，臨時查詢不給方向，也不會「算了不記帳」**：寫入被閘門拒絕時，POST 不計算、不回傳任何 label 或方向衍生欄位，回應用封閉 schema `OnDemandGateClosedView`（A-72，見 D-14）。
- （r3′，A-79）**族群可能重新隱藏方向**：不設遲滯，每次回應都依當下的 `pa9_holds` 判定。重新變成 PA-9 成立後，這些列改用 A-63 第 4 項，不得繼續寫「結算後列示」（A-63 第 9 點）。
- （r3′，A-79；r3″ RC′-8 整點改寫）**個股與族群常駐 `gated`**：個股與族群在 v1 沒有回放計畫（事先宣告 §4.7），所以常駐 `gated`，任何畫面都不顯示其方向；A-63 第 5 項要在 D_v 前核可。
- （r3′，A-79）**觀察日可能因為 X2 回溯縮小**：已寫入的 snapshot 不改；之後的 snapshot（含 F-3 逾時率的 60 日窗）用新集合。結算端依事先宣告 §6.4 supersede（A-77 第 11 項）。
- （第九、十批，A-79）**X2 確認優先、固定排除的兩面後果**（A-77 第 12 項甲案）：方向：收緊（觀察日只減不增、不新增寫入路徑、不自動改變狀態）。定義忠實度兩面：d 若其實是交易日，受影響紀錄的 T+h 會多跨一個實際交易日，偏差留在統計中，直到修訂本項為止；以 §4.2 揭露與 F-8 查證緩解（風控 2026-10-17 第九批 TA 提案確認）。
- （第九、十批，A-79）**診斷欄位更正例外屬揭露面放寬**（A-65）：只更正診斷欄位、而且更正鏈符合例外條件的紀錄，不帶翻案伴隨句，使用者不知道診斷欄位曾經更正過。畫面上每一個數字都和最初結算時逐位相同；被豁免的筆數在 §4.2 揭露；更正鏈只要曾經作廢、或有其他原因，就不適用（風控 2026-10-17 R-7 對照表與更正鏈提案確認，提案 3）。這是揭露面的放寬，不是風險上限；已經風控核可，列入 CEO 知悉（見待決事項 CEO 第 8 點）。
- （第九、十批，A-79）**LM-154 列看不到結果，但計入主統計**：依 LM-154 不顯示結果的列，結果仍計入主統計（鏈尾，D-11.1），只是畫面看不到；這類列的筆數依鏈尾的 `correction_causes` 分列，在 §4.2 揭露（風控第十二批 LM-154 條件 ⑫）。
- （第九、十批，A-79）**族群徽章在上線初期以遮蔽為常態**：D_v 前族群可能沒有 daily snapshot；沒有 snapshot 時 `n_disclosure_masked` 為真，族群徽章是 LM-153，不是正常徽章（第九批提案 2 待裁 (a)；風控第九批 C9-5）。
- （第九、十批，A-79；風控 2026-10-18 C7-8）**（C9-7 甲案）大盤與個股的 snapshot 落後時遮蔽**：任一筆 E 變動事件之後、下一筆涵蓋它的 daily snapshot 之前，所有 claim 的驗證徽章改為 LM-153，展望不顯示方向。另一面：這段期間，徽章原本的狀態（包括「未優於基準」等負面狀態）也不顯示；但方向同時不顯示、LM-31 常駐、下架與暫停告知（LM-76、LM-81）照常，所以不會造成過度信任。一筆事件會遮掉全部 claim；snapshot 作業失敗時，遮蔽會持續到下一筆 snapshot 成功為止。
- （第九、十批，A-79）**（未觀察平日 A 案）未觀察平日固定排除**：登記之後即使補到資料也不回到觀察日。另一面：這一天若其實是交易日，跨越它的紀錄 T+h 會多跨一個實際交易日，偏差留在統計中，以 §4.2 的四項揭露與 data-engineer 根因查證緩解（Q3-5）。

**需 CEO 知悉事項（白話；r3，A-79，取自風控 r3 審查第三節並經 RC′-9、RC″-4 更新）**
1. 第一版上線期間，個股的 5 日方向一律不拿來算行動建議。另外，因為個股沒有歷史回放報告，**個股詳細頁也不會顯示 5 日方向**，只會照實寫「5 日展望目前不可用（原因）」並附驗證狀態。要開放，得另外送審。
2. 開始正式記錄預測之前，要先核可的文字又多了幾句，包括一些很多年後才會用到的說明，以及作廢紀錄的呈現方式。開始記錄的時間可能再往後延。
3. 正式記錄開始之前，臨時查詢個股也不會給出方向，系統也不會「算了但不記帳」。開始之後，早上 8:30 前已經產生的臨時查詢紀錄，白天再查會照常顯示同一筆，因為它是在預測期間開始前就定下的。
4. 主機如果在交易日收盤定案前開機，市場資料可能只抓到盤中值；當天如果沒有再抓，那一天只要仍算觀察日，就會照實記成缺日，不會補造；如果那一天連大盤的定案資料也沒有，就不算觀察日，也不會出現在缺日紀錄裡。這類平日會另外留下紀錄，在驗證報告逐日列出；之後就算補到資料，也不會改算成觀察日。之後約 60 個交易日內，部分紀錄可能判成證據不足或作廢，作廢的會算進最壞情境。根本修法要改 ADR-0012（已核可），屆時會請你核可。
5. 大盤資料必須是收盤定案後才抓到的才能用。重抓失敗的日子，只要仍算觀察日，就照實記成缺日，不會用暫定值頂替，也不會改用前一天的資料。
6. 族群因為同樣沒有回放報告，第一版期間不會顯示方向，即使累積到 150 筆也一樣。日後如果開放，若有資料違規讓筆數掉回 150 以下，已經顯示過方向的紀錄會重新隱藏，事件會在驗證報告揭露。
7. 閘門條件中的「影子試跑」「上線天數與結算筆數」仍待你在 #10 裁示。但已核可 ADR 規定的條件（族群 150 筆、每個範圍都要有經審查的回放報告）不能用這個裁示關掉。目前只有大盤有回放計畫。
8. **待你決定（不急）**：第一版要不要讓個股或族群顯示方向。不決定的話，就維持不顯示；這在風險上是安全的。要開放，只有兩條路：做該範圍的回放，或修訂 ADR-0025 的閘門。做回放的話，要先修改事先宣告（目前規定個股與族群的回放只能當內部研究、不上畫面），回放結果有已知偏誤，要照實揭露。兩條路都要再送風控。

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
- **FL-62**（r3 新，A-76）：呼叫點 ⊆ `CACHE_BAR_CONSUMERS` 列舉；每一項各一個暫定列 fixture。

**排程與逾時**
- **FL-14**：新 job 的 trigger 都帶 `timezone="Asia/Taipei"`。
- **FL-15**：`late` 由 store 計算；`late_cutoff_at` 寫入後不重算；臨界點 08:29:59 為 0，08:30:00 為 1。
- **FL-16**（r3，A-74）：`late=1` 與 on-demand 紀錄，永遠不會出現在 `current_outlook`、`plan` 兩類端點；`outlook_refs` 不得指向它們。`record_list` 依 D-11.4 第 11 點；`on_demand` 依 D-7.8 第 8 點與 A-36。
  - `ENDPOINT_SURFACES` 每一項加 `kind ∈ {current_outlook, plan, record_list, on_demand}`，沒有預設值；沒有登記 kind 的 route，測試失敗。
- **FL-17**：前端非測試檔不得出現 `08:30`、`09:00` 或截止時間的推算（grep）；`{截止時間}` 用 Asia/Taipei 格式化。
- **FL-18**：每個 run 不是有 `forecast_run_end` 列，就是被稽核成 `job_error`。
- **FL-61**（r3 新，A-75）：
  - (a) **定案邊界**：TW 的 `final_after(T)` 是 15:00:00（ADR-0028 VS-4，CS-17）。
    - `as_of` 14:59:58、`fetched_at` 15:00:01 → `is_final_bar` 為 False（取兩者中較早的）；
    - 兩者都 ≥ 15:00:00 → True；
    - 任一個晚於 `now` → False；
    - 任一個不帶時區或為 None → False。
    - 注入的 `now` 早於 `fetched_at` 一秒 → False；
    - AST 檢查 `is_final_bar` 沒有預設的 `now`。
  - (b) **列層排除**：示範資料列、帶 `OHLC_INVALID` 的列，各一格，`is_final_bar` 都是 False。
  - (c) **重抓一次**：(ii) 不成立時，經 `app.services.index` 強制重抓恰好一次（spy 計次），寫入仍經 `service.py`。
    - 重抓後成立 → 照常記錄；
    - 仍不成立 → 該 session 記 `inputs_not_ready`。
  - (d) **不退回前一 session**：候選 T 的 (i) 或 (ii) 不成立時，不寫任何 `data_as_of` 早於 T 的紀錄，也不使用暫定值。(iii)、(iv) 由 FL-19 (e) 涵蓋。
  - (e) **逐列欄位入雜湊**：`app.services.index` 的新方法逐列回傳 `as_of`、`fetched_at`、`source`。`forecast_input_series.bars_json` 每列帶這三欄；改動任一欄，`content_sha256` 就不同。

**缺日與結算**
- **FL-19**：缺日稽核只用觀察日，不呼叫 `TradingCalendar.is_trading_day` 的推定。
  - （r3，A-77；增補；RC‴-2）fixture：
    - (a) 週末的定案大盤列不成為觀察日（R-B 指定）；
    - (b) 平日只有定案前 ok run、有定案大盤列 → X2 列為異常待查證，d 仍是觀察日；
    - (c) 週末只有定案前 ok run、有大盤列 → X2 直接確認，d 不是觀察日，T+h 順延，`x2_shift_json` 齊全；
      - (c)① 原本的直接確認格，另斷言 payload 七個欄位齊全，而且 `set_i_check` 等於重算的結果。
      - (c)② direct 拒絕寫入：寫入當下注入一筆定案後的 ok run，使 d ∈ D-8.1 (i)；或 `verification_ref` 非 null；或 `trigger` 為 null；或 `trigger` 和 d 不符，也就是平日用 `weekend`，或週末用 `official_holiday`（RC‴-2）；或 `trigger = official_holiday` 但 d 不在 `holiday_table` 的涵蓋範圍內，或不是表列休市日。各一個子例，都期望拒絕寫入、不寫事件、d 仍是觀察日。
      - (c)③ verified 拒絕寫入：`verification_ref` 為 null；或指向的查證紀錄結果不是「來源沒有這一天」；或 `trigger` 非 null；或 `trigger` 為 null 但 d 是週末；或 d 列在已接入的休市日表（RC‴-2）；或 `verification_ref` 指向的查證紀錄 `session_date ≠ d`。各一個子例，都期望拒絕寫入。
    - (d) 週末 d ∈ (i) → 證據矛盾、維持待查證、d 經 (i) 是觀察日、寫入 `session_calendar_conflict`；注入「獨立來源沒有 d」的查證結果後，d 仍是觀察日，也沒有寫入 `x2_confirmed_non_session`；
    - (e) 拆成三格：
      - (e)① 候選 T 是 X2 確認日：除 A-77 第 12 項的情形（見 (h5)）外，屬縱深防禦。測試注入違反前提的狀態，期望 `inputs_not_ready`，而且不退回前一個 session。
      - (e)② 候選 T 是週末，而且 T ∈ (i)：期望 `inputs_not_ready`、WARNING、寫入 `session_calendar_conflict`（`origin = candidate_t`），而且不退回前一個 session。
      - (e)③ 候選 T 是週末，而且 T ∉ D-8.1 (i) → 記 `inputs_not_ready`，不寫 `session_calendar_conflict`，不退回前一個 session（S″-2）。
    - (f) 官方休市日表尚未接入時，平日的官方休市日只有 (iii) 成立 → 列待查證；
    - (g) X2 判定函式的簽章不接受觀察日集合，也不接受任何指數 bar 序列（和事先宣告 LG-25 (f) 對齊）。
    - (h)（第九批，提案 3 甲案）X2 確認之後，注入 d 的定案後 ok run：
      - (h1) d 不是觀察日；
      - (h2) 只寫一筆 `session_calendar_conflict`，payload 帶 `x2_event_id` 與最小的 `run_id`；重跑偵測不重複寫入；
      - (h3) X2 事件、`x2_shift_json`、`forecast_outcome` 的列數與內容，前後雜湊逐位相同；
      - (h4) 不產生 `correction_job_id`；
      - (h5) 候選 T＝d → `inputs_not_ready`；
      - (h6) direct 與 verified 各一格。
    - (i)（Q-3 A 案，風控 2026-10-18 C9-7 與 Q-3 提案確認）未觀察平日：
      - 平日沒有 run、也沒有大盤列 → 只寫一筆事件，d 不是觀察日，沒有缺日列，重跑不重複寫入；
      - 表列休市日、週末、d 是最新日期 → 都不寫事件；
      - 登記之後補寫 run → d 仍然不是觀察日，衝突事件只寫一筆；
      - outcome 與缺日列的雜湊前後相同；
      - 結算寫入之後、缺日稽核之前，補寫 d 的定案資料 → d 在結算當下已登記，仍不是觀察日；outcome 的雜湊不變；`post_unobserved_backfill` 只寫一筆（風控 2026-10-18 Q3-2）；
      - 分別只進入 (i)、只進入 (ii)、兩者都進入 → `backfill_via` 與參照欄位都正確，而且只寫一筆；先進入 (i)、之後才進入 (ii) → 不另寫，`backfill_via` 仍是 {`set_i`}（風控 2026-10-18 E8-3）；
      - 拒絕格四個：`evidence` 和 `origin` 不相配（兩個方向各一格）；`unobserved_event_id` 指向不存在或 `kind` 不符的事件；`backfill_via` 和重算結果不符。
    - 原有三個 fixture（示範列、暫定列、定案前的 run）保留。
- **FL-20**：`late_only` 的缺日列不渲染 TG-b；TG-c 的計數排除 `late_only`。
- **FL-21**：結算三條件缺一就不結算；PA-7 失效觸發的紀錄照常計分。
- **FL-22**：`status_reason` 屬於 D-9.3 的五值封閉列舉，而且與 `status` 的對應固定（表格驅動測試）。
  - 表格驅動測試加三格（r3，疑義裁定第 15 項；風控 Q-1）：
    - market 結算前確認、等待期滿仍取不到 → 寫入此值；
    - market 結算後確認 → supersede 列為此值，`had_listed_result` 為真；
    - 非 market scope 寫入此值 → 拒絕。
  - （第十批，提案 1；風控 R10-2、R10-4）斷言：
    - (a) 對照表的鍵集合 ＝ 列舉；每個值恰好對應 LM-151、LM-152、FAIL_CLOSED、豁免（只限 `[window_bar_corrected]`，依 `correction_is_display_neutral`）四者之一；
    - (b) 寫入函式拒絕列舉外的值、空陣列，以及與 `supersedes_id` 不一致的組合；單一原因的差異驗證（R10-2）的三種拒絕，各一格（子例見下）：
      - `[x2_session_removed]` 而新列的 `end_price_json.session_date` 不晚於前一列，或 ≠ `shifted_t_plus_h` → 拒絕；
      - `[settlement_close_corrected]` 而任一 `session_date` 改變、兩個收盤值都沒變、或 `window_factors_json` 改變 → 拒絕（各一個子例）；
      - `[dividend_factor_corrected]` 而任一 `session_date` 改變、或 `window_factors_json` 沒變 → 拒絕。
    - (c) 「謂詞為真 × 最新 outcome 為 `resolved`」路徑中，`correction_causes` 的每一種情形（四個單值、一組雙值）各一格，逐格斷言全文：
      - LM-151、LM-152 兩格要等於 LM-150 代入後的全文，而且不含「沒有實際結果」、不含日期數字；
      - FAIL_CLOSED 的格（LM-154 條件 ③⑤⑩）：三格——除權息因子；兩個以上原因；未豁免的診斷更正。每格斷言：
        - schema 驗證通過，`status_fragment_id == LM-154`；
        - 狀態行逐字等於 LM-154；全文不含日期數字，不含「作廢」「撤回」「沒有實際結果」，也不含 LM-143、LM-150 的 ID；
        - 沒有白名單以外的鍵；`disclosure_fragment_ids` 不含上列 ID；大盤格不含 LM-22。
      - 對照格：`[x2_session_removed]`；`[settlement_close_corrected]`，P(T) 收盤有變、P(T+h) 收盤有變各一格；豁免成立的 `[window_bar_corrected]`。這四格都找不到 LM-154；兩個收盤更正格的狀態行等於 LM-150 代入 LM-152 的全文。
    - (d) 同一晚注入 X2 確認與收盤更正、兩者和同一筆有交集 → 該筆的 `correction_causes` 有兩個值，結果 fail-closed；
    - (e) 原因為 `window_bar_corrected` 但 D 欄位改變 → 拒絕寫入。
- **FL-23**：更正作業涵蓋所有結算窗與受影響日期有交集的列，不多不少。
- **FL-24**：預測端計分永遠使用原始列。
- **FL-50**（r1，A-11）：用表格驅動測試釘住 D-9.3 的兩點（`split_or_reduction_suspected` 的固定門檻、`basket_coverage_below_90` 以 T 日成員數計）。
- **FL-63**（r3 新，A-78）：「交易日 10:00 啟動」fixture：期望 D 記 `inputs_not_ready`、D 經 (ii) 成為觀察日（所以會留下缺日列）、10:00 的 bars 不進入任何 PIT 輸入或結算窗。

**銜接**
- **FL-25**：plan 組合價位與估值時，市場 DB 的原始收盤[T] 必須等於估值所用的價格與日期；不一致時，價位缺席，附 `MissingItem(code="E-PRICE-UNUSABLE", source_status="failed_check")`。
  - （A-96″；依 ADR-0028 A-96′／A-96″，風控 2026-10-17 A-96 CS-26 第 4 點、A-96′ 單項確認 K-13）**fixture**：
    - **(a)～(e) 五格**：構造 `build_summary` 的輸入，讓 `date_anomaly` 的五個 `sub_reason`（`future_date`、`before_open`、`official_conflict`、`not_a_session`、`unconfirmed_session`）各出現一次。plan 組合價位時，五格都期望價位缺席，並附 `MissingItem(code="E-PRICE-UNUSABLE", source_status="failed_check")`。
    - plan 端不得讀 `valuation_state`（ADR-0028 CS-4）。fixture 只構造輸入，只斷言 plan 的輸出。
    - **(f)(g) 週末對抗格**：(f) `not_a_session`（D 是週末，`price_date == D`）；(g) `unconfirmed_session`（`P < price_date < D`，該日是週末）。
      - 兩格都構造「市場 DB 在該日有定案後的 ok run（`recorded_at ≥ final_after(TW, 該日)`），而且收盤相同」。
      - 期望：依 A-75 (iv)，該日不成為候選 T；記 `inputs_not_ready`；寫入 `session_calendar_conflict`（`evidence = weekend`、`origin = candidate_t`）；plan 的輸出中沒有任何價位取自該日。
    - **(h)(i) 官方休市日對抗格（K-13）**：(h) `official_conflict`（D 是官方休市的平日，`price_date == D`）；(i) `unconfirmed_session`（`P < price_date < D`，該日是官方休市的平日）。
      - 構造方式同 (f)(g)。
      - 期望同上，但 `evidence = official_holiday`。
      - 官方休市日一律取自 A-75 (iv) 的單一定義函式。官方表接入之前（T1-13 前），用注入該函式的測試替身構造，不得在測試內另寫一份休市日清單。

**定義與 claim**
- **FL-26**：loader 遇到 `rules_sha256` 不在 `PUBLISHED_RULESETS` 就拒絕載入。
- **FL-27**：寫入紀錄時，logic 雜湊必須等於所屬 claim 的雜湊。
- **FL-28**：m 只增不減；`forecast_validation_snapshot.alpha_star` 等於 0.05÷(max(`m_at_eval`, 8)×K)。
- **FL-29**：只有 `eval_kind=checkpoint` 的列可以使狀態升為 `better_than_baseline`。
- **FL-47**（r1，A-5）：`bootstrap_seeds_json` 的鍵 ⊆ 對照表；每個值等於導出式的結果（即 LG-20）。
- **FL-48**（r1，A-10）：補跑的 late 紀錄、首筆紀錄後來被確認為 PIT 違規，這兩種 fixture 下 D_v 都不變。
- **FL-49**（r1，A-7）：用表格驅動測試釘住 E 的兩端各自的取列規則（預測端 `forecast_record`、結算端更正鏈的最後一筆）。
  - （第九批，提案 4；掛 A-63）加三格：
    - 對 E 內的原始列寫一筆更正 → E 的成員、n、`e_changed_since` 逐位不變；
    - outcome 指向更正列 → 拒絕寫入；
    - `pit_violation_confirmed` 指向更正列 → 拒絕寫入。
  - （第十批，提案 4；掛 A-59）加三格：鏈長 3 時取第三筆；`resolved_at` 被注入成倒序時，結果不變；snapshot 讀序號之後才 commit 的 supersede，這次 snapshot 不採用。
  - （第十批 R10-7；掛 A-77；觸發條件依風控 2026-10-18 v0.12 審查 Q12-2 擴為四項）加兩格：
    - 注入使檢查點命中翻轉的更正 → 下一筆 daily 降級；同一筆 checkpoint snapshot 的列數與內容逐位不變；
    - 只改 `realized_label`、`hit` 不變的更正 → 下一筆 daily 降級。
- **FL-51**（r1，A-8）：E 排除有 `pit_violation_confirmed` 事件的 `forecast_id`；每個暫停原因都對應到已核可的片段（LM-77 重送後、LM-78、LM-83）。

**F-2（對應 D-12；逐條對應風控底線）**
- **FL-30**（底線 1）：下架條件的實作與「相鄰兩檢查點的點估計都 ≤ 任一必備基準」等價（表格驅動測試）；程式中不得出現以區間上緣判斷下架的路徑（code review 加測試）。
- **FL-31**（底線 2）：n＝150（族群 250）的退出期限存在，為常數，並有測試釘住。退出期限常數屬於 `definition_logic_sha256` 的範圍；之後版本的值只能小於或等於凍結值（測試釘住）（r2，A-22）。
- **FL-32**（底線 3；r2 改，A-24）：F-2 條件一依 D-12「下架原因列舉值」第 1 點的公式，逐檢查點套用 W，並以 FL-45b 的 fixture 釘住。ADR 內不另外寫第二種表述。
- **FL-33**（底線 5）：claim 登記遇到相同 logic 雜湊會被 UNIQUE 拒絕；新版的 API 回應附 `predecessor_claim_id` 與 `predecessor_withdrawn_at_n`。
- **FL-34**（底線 5）：`withdrawn_f2` 時，所有對外回應都沒有該 claim 的最新 label（API、提醒 payload、天氣、匯出各一個契約測試）。
- **FL-35**（底線 6）：重新上架只發生在 `checkpoint` 列，而且 §4.3 全部成立。
- **FL-36**（底線 4）：§4.3 與 α\* 的常數屬於 `definition_logic_sha256` 的範圍，任何修改都會產生新定義。
- **FL-37**（底線 7）：C-8 的選擇以常數登記在 dirdef 內，D_v 之後只能往更嚴的方向改，而且要升版。
- **FL-45**（r1，A-9；r2 改，A-24）：
  - (a) 兩張對照表都完整：每個 `withdraw_reason` 在兩張表都有項目，而且片段 ID 都在風控核可表內。缺任何一個就失敗；不得用 skip、xfail 或暫定字面讓測試通過。
  - (b)（r3，A-58）LM-79、LM-81、LM-104 只從各自的對照表取值，另加四項斷言：
    - (b1) LM-87 不得代入 LM-79 的 `（{下架原因}）`；
    - (b2) worst_case 只用 LM-104，而且只在前一版 `withdraw_reason = f2_invalid_stop_worst_case` 時使用；
    - (b3) LM-104 的兩處 `{X}` 都取 `withdrawn_at_n`（用不同的 n 做 fixture）；
    - (b4) LM-104 內嵌的 LM-87 逐字完整。
  - (c) 效力鏈：FL-45 失敗 → G-6 不成立 → 不得寫入排程紀錄。
- **FL-45b**（r2 新，A-24）：逐檢查點的 fixture，涵蓋五種情形：
  1. 兩點都 > 5%，而且都只靠 W 失敗 → worst_case；
  2. c₀ ≤ 5% 且一般情境失敗，c₁ > 5% 且只靠 W 失敗 → worst_case；
  3. c₀ > 5% 且只靠 W 失敗，c₁ ≤ 5%、一般情境通過、W 失敗 → 不下架；
  4. 兩點一般情境都失敗，作廢率 > 5% → `f2_invalid_stop`；
  5. deadline 與 worst_case 同時成立 → `reason=f2_deadline`，`conditions_met` 含兩者。
- **FL-46**（r1，A-9）：只有一個函式讀 checkpoint 列來判定條件一（grep 加測試）。

**閘門與缺項**
- **FL-38**（r2，A-33）：
  - 單元測試：recorder 在 G-3、G-4 不成立，或 dirdef 缺 `f2_variant`／`c8_decision_*` 時，拒絕寫入；
  - CI 測試：`c8_decision_sha256` 與檔案相符；
  - 其餘項目由 qa 在 PR 描述中核對 CEO 決策紀錄與上線證據。
  - （r3，A-72）on-demand 路徑在 G-3、G-4 不成立時拒絕寫入。
  - （r3，A-72）拒絕寫入的回應要通過 `OnDemandGateClosedView` 的 schema 驗證，也要通過 FL-52b (9b) 的全文掃描；以 spy 斷言展望計算函式沒有被呼叫；route 列舉中所有 kind 為 `on_demand` 的 route 都經過閘門函式。
  - （r3，RC′-6）schema 斷言另加：`disclosure_fragment_ids`、`status_fragment_id` 的清單以外的 ID 驗證失敗；有前端不得補方向的契約測試。
- **FL-39**：`MissingItem` 的不變式以 model validator 強制；`SourceStatus` 的每個值都有字面（`outlookWording.test.ts::every reason enum has a template`）。
- **FL-40**（r1 改，A-1；r2 改，A-31）：
  - (a) `load_policy` 遇到 `POLICY_FORBIDDEN_FIELDS` 的欄位就拒絕（表格驅動）；
  - (b) 直接呼叫 `PolicyTable.model_validate`，同樣被拒；
  - (c) `PolicyTable` 的 `model_construct` 與帶 `update` 的 `model_copy` 都會 raise。
- **FL-41**（r1 改，A-1）：
  - (a) 在暫存目錄放任意檔名的 YAML，經 `load_rules(path)` 載入時，五種 action × `COST_DERIVED_FIELDS` 的每個欄位，不論出現在 `field`、`ref` 或巢狀的 all／any 裡，都會被拒；
  - (b) 直接呼叫 `RuleSet.model_validate`，同樣被拒；
  - (c) 現行 `default.yaml` 可以通過。
  - (d)（r2，A-31）`RuleSet`、`Rule` 的 `model_construct` 與帶 `update` 的 `model_copy` 都會 raise；`model_copy()` 可以正常使用。
- **FL-41b**（r1 新，A-1）：成本不變性。同一組 bars 與部位，只改 `position_cost_twd`，`build_context` 輸出中有差異的鍵必須 ⊆ `COST_DERIVED_FIELDS`。
- **FL-41c**（r1 新，A-1）：D-15 第 5 點的 import graph 檢查。
  - （第九、十批，A-34）另加一條 import graph：`app.outlook.*` 不可達 `app.forecast.*`（σ_d 序列的觀察日由 recorder 以參數傳入；recorder 呼叫 outlook，反向會形成循環）。
- **FL-41d**（r2 新，A-31）：3b 的 AST 測試。
- **FL-42**（r1 新，A-6）：
  - `forecast_record.label` 這個欄位，只有 `app/forecast/{views, display, scoring, validation}.py` 會讀（AST 檢查）；
  - `app.plan.*`、`app.advice.*`、`app.alerts.*`、`app.api.*` 在 `app.forecast` 底下只可達 `views` 與型別模組（import graph）。
- **FL-43**（r1 新，A-6）：標籤不變性（即 LG-22）。在每一種 unavailable 原因下，於 store 層把標籤在 bullish、range、bearish 之間互換，以下輸出都必須逐位相同：`position_action`、`reasons`、`pending_triggers`、各項 conditions、「最需要處理」的排序、提醒 payload、`plan_record` 中會顯示的欄位，以及 API 回應。
  - （r3，A-69）對提醒 payload 的斷言保留。
  - （r3，A-70）擴充：
    - (i) 每一種原因 × 每個 `uses_outlook` 條件，`observed`、`threshold` 都是 None；
    - (ii) 標籤互換的輸出清單加入 `add_conditions`、`entry_conditions`、`quantity_range`；fixture 要含 `add_conditional`、`consider` 兩條路徑。
- **FL-44**（r1 新，A-6；r2 改，A-30）：`plan_record.outlook_display_state` 一定非空。`availability = evaluated`，若且唯若同時滿足：
  - `display_state = shown`；
  - **`consumer_surfaces` 的每個顯示面都許可**；
  - 該筆紀錄符合第 6 點：有 R_s、`late=0`、不是 insufficient 或 voided、T ≥ D_v。
- **FL-52**（r2 新，A-30；r2'' 改 (d)）：原因與片段的對照表允許附守門的項目：`REASON_FRAGMENTS: Mapping[reason, tuple[GuardedFragment, ...]]`。測試項目：
  - (a) 每個值至少有一個項目；
  - (b) 所有片段 ID 都已核可；
  - (c) 每個值的守門，對所有輸入組合都恰好選出一個片段（窮舉表）；
  - (d) `exclusion_reasons` 與紀錄清單的兩個狀態片段（逾時；期間已開始）同樣要對應到已核可的片段。「期間已開始」片段由紀錄清單與 POST 回應共用同一個 ID（A-36 第 2 點）。「期間已開始」片段為 LM-106。本 ADR 任何一處規定『核可之前 FL-52 (d) 失敗』的片段（含 A-62 R2 第 6 點、A-63 單列狀態片段、A-65 (h)、D-7.8 第 4 點），全部核可之前，本項仍失敗。
    - （r3，A-61）擴充：`in_eligible_set` × {一般, 證據不足, 作廢}，以及 `exclusion_reasons` 的每個值，窮舉表都恰好選出一個片段。qa-e2e 在 375 寬度驗收 LM-114。
  - (e)（r3，A-55）**S3**：四態中的每一態 s，(symbol, symbol_detail) 都要列在 `SURFACE_PERMISSIONS`，而且 `required_disclosures(symbol, symbol_detail, s)` 全部核可。這包括 `better_than_baseline` 時的 D-2 開盤基準句，以及 D-4 的區間、n、期間片段。任何一態不成立，FL-52 就失敗。
  - (f)（r3，A-55）**「只在」斷言**：除了 `symbol_detail`、`api`，(symbol, 任何其他 surface) 都不得列入。任何一格要開放，LM-94、LM-95 都要先重送。
  - (g)（r3，A-55）**S4 窮舉表**：`surface_not_permitted` × 四態 × `scope_kind`，每個組合恰好選出一個片段（symbol × `better_than_baseline` → LM-95；symbol × 其餘 → LM-94；非 symbol 沒有項目）。另外斷言 v0 的引用範圍 ⊆ {symbol}。
    - （r3′，A-56）窮舉表加一個維度：`withdrawn_f2` × `f2_variant` × `scope_kind`，只有 (symbol, F2-B) 選到 LM-97，其他組合都沒有項目。
  - (h)（增補 T-3）對每個 scope × {`suspended_f3`, `withdrawn_f2`} × G_eff（∅／非空）逐格斷言 A-63 第 12 點 (1)～(3)，包括渲染出的片段數等於 |G_eff|。
  - （r3″；RC″-3）窮舉範圍：對每一個登記在 `GATE_SLOT_SCOPES`（A-63 第 11 點）的 (scope_kind, slot)，取該 scope 可能出現的 `gate` 值集合 P(scope) ＝ `GATE_FIXED`（該 scope）∪ 已啟用的 `GATE_ADDITIONAL`（風控第八批 T-1）。
    - `forward_n_below_min`：**族群一律加入 `forward_n_below_min`；大盤與個股在 quant 有登記時才加入**（風控 2026-10-17 RC″-3）。
    - 未啟用的 `GATE_ADDITIONAL` 值不在窮舉範圍內。
    - P(scope) 的每一個非空子集，都恰好有一個項目，而且 `covers` 聯集等於該子集。
    - 斷言：
      - 族群 {`forward_n_below_min`, `replay_review_pending`} 選不到「只有第 4 項」；
      - 族群的 P 不論 quant 是否登記，都含 `forward_n_below_min`。
  - （第九批，提案 1；風控第九批 C9-1～C9-3、S9-1；風控 2026-10-18 C7-6）**FL-52 擴充**：
    - 列舉範圍：每一個已登記的 (scope_kind, slot) × `display_state` ∈ {`gated`, `suspended_f3`, `withdrawn_f2`} × P(scope) 的每一個非空子集；× `n_masked` ∈ {真, 假}（三個 scope 都適用；C9-7 甲案）。`outlook_block` 的列舉再 × `status` ∈ 四態 ∪ {None}。
    - 每一格都恰好選出一個 slot 項目，而且 `covers` 聯集等於該子集。
    - 登記與 `GATE_SLOT_SCOPES` 一一對應：`GATE_FRAGMENT_REGISTRY` 逐一列出每一個 (scope_kind, slot)，沒列出的組合 fail-closed（風控第九批 C9-2）。
    - 斷言：
      - (1) `outlook_block`、G_eff＝{`forward_n_below_min`}、`display_state = gated`、同一列 snapshot 的 `status` 是 `unverified`（未驗證），而且 `n_masked` 為假 → 選 LM-12，不選 LM-120；
      - (2) 同上但 `suspended_f3`／`withdrawn_f2` → 選 LM-120，不選 LM-12；
      - (3) |G_eff|≥2 時，任何 slot 都選不到 LM-12；
      - (4) quant 沒有登記前瞻門檻的 scope，LM-12 與 LM-128 都選不到；
      - (5)（族群）`n_masked = true` 時選不到 LM-129。渲染全文中的每一段數字，只能來自已核可字面的固定文字（例如 LM-126、LM-127 的「5 個交易日」），或 `{k}`、`{h}`、`{MM/DD}` 占位；不得有任何占位綁定該 claim 的 snapshot n 或其衍生值。fixture 的 n 取一個不會出現在固定文字裡的值（例如 137），全文掃描找不到這個字串。LM-144 片段本身不含數字。大盤與個股的對應斷言見下方「大盤與個股的遮蔽 FL」(a)。
      - (6) 登記內沒有已撤回的片段（風控第九批 R9-04 撤回的兩句；編號見修訂紀錄 A-63）；
      - (7) G_eff＝{`forward_n_below_min`}、`gated`、`status` ≠ 未驗證，或 `status` 為 None（沒有 snapshot）→ 選 LM-120，不選 LM-12；
      - (8)（LM-153 條件 ⑪）：
        - 族群 × 兩種遮蔽情形 × `display_state` ∈ {`gated`, `suspended_f3`, `withdrawn_f2`} × {已結算, 未結算}：任何回應都沒有該 claim 的 label。
        - 另一格：fixture 強制 `pa9_holds` 回傳假，而 `n_disclosure_masked` 為真 → 仍然沒有 label，並有 WARNING。
        - 大盤、個股格（風控 2026-10-18 C7-6）：遮蔽 × {`e_changed_since`, 沒有 snapshot} × {未結算, 已結算}。未結算列與 `OutlookView` 沒有 label；已結算列有 label 時，`disclosure_fragment_ids` 含 PV-45。
      - (9)（風控第九批 S9-1）`display_state = shown` 而 G_eff 非空時，`select_gate_fragments` raise（fail-closed）；性質測試：`views` 永遠不會產生這個組合。
  - （C9-7 甲案；風控 2026-10-18 C7-2、C7-3、C7-5）**大盤與個股的遮蔽 FL**：
    - (a) 大盤、個股 × {`e_changed_since`, 沒有 snapshot} × snapshot `display_state` 四態：`shown` 變成 `gated`；徽章是 LM-153；找不到 LM-03、LM-04、LM-32、LM-33、LM-12；fixture 的 n 取 137，全文找不到。「沒有 snapshot」格另外斷言：找不到 LM-128。
    - (b) 性質測試：調整只會把 `shown` 變成 `gated`。
    - (c) FL-52 窮舉納入新值；`plan_reason` 的窮舉不含新值。
      - FL-52 另加一格（C7-5）：兩個前提（見 A-57 (iv) 的 `validation_refresh_pending` 條）任一不成立時，本例外失效，(symbol, `plan_reason`) 含 `validation_refresh_pending` 的子集沒有覆蓋片段即判定失敗。
    - (d) 性質測試：任一種 E 變動事件前後，n 不增。
    - (e) snapshot 寫入路徑斷言：寫入的 `gate` 不含 `validation_refresh_pending`（`GATE_FIXED` 的大盤、個股列有這個值，但 snapshot 的 `gate` 永遠不含它）。
  - （S7、S9 第 2 項）**FL-52 謂詞路徑表**：
    - 謂詞為真 × 最新 outcome 是 `resolved` × `correction_causes` 的全部情形：每格恰好落在 {LM-150, LM-154, 豁免（不帶伴隨句）} 其中之一。
    - 謂詞為真 × 最新 outcome 不是 `resolved` → LM-143。
    - 謂詞為假 → 三句都不出現。
    - 性質測試：同一列 LM-143、LM-150、LM-154 至多出現一句。
  - （S7、S9 第 2 項）**FL-52 條件 ⑥ 格**：
    - FAIL_CLOSED fixture 的鏈尾 `realized_return` 取 0.0137，`end_price_json.session_date` 取其他 fixture 列沒有用到的日期。
    - 列舉所有 route（比照 FL-54 (g)）與 `EXPORT_MODULES`：帶該 `forecast_id` 的物件都沒有 D 欄位的鍵；全文找不到「1.37」，也找不到該日期的 MM/DD 字串。
  - （第十批，提案 3）**FL-52 加三格**：
    - 全鏈中性 → 不出現 LM-150、LM-143，LM-131 照常；
    - 鏈中有一列 D 欄位不同 → 依對照表；
    - resolved → 作廢 → resolved 的鏈，即使數值相同也不適用例外（依 R10-3／V12-20，寫入函式會拒絕這種鏈；本格以 fixture 直接插入，並另斷言寫入函式拒絕）。
  - （第十批 R10-6）FL 斷言：回應 schema 中每一個由 `forecast_outcome` 衍生的欄位都屬於 D；新增回應欄位而沒有加入 D，測試就失敗。
  - （r3，A-62 R2 第 4 點；RC‴-4）`status_reason` 的窮舉要涵蓋全部值，並依 `had_listed_result` 分成兩條路徑（見 D-11.4 第 11 點 (h)）。
  - 不得 skip；效力鏈同 FL-45 (c)。
- **FL-52b**（r2 新，A-30；r2'' 改 (9)）：第 6 點的判定用 fixture 釘住六種情形，分別得到對應的值：
  - (1) 沒有 run；
  - (2) 有 run，但快照不含這檔；
  - (3) 快照含這檔，但沒有紀錄；
  - (4) 只有 on-demand 紀錄；
  - (5) `late=1`；
  - (6) `late=0`。
  - 另加性質測試：加入或移除 on-demand 紀錄，值都不變。
  - (7) 快照之後、產生 plan 之前才加入自選 → `not_in_schedule`，旗標為 true → LM-89；
  - (8) 大盤或族群的快照漏掉自己 → `missing_scheduled`，永遠不會是 `not_in_schedule`；
  - (9) on-demand 的建立時間取 08:29:59 與 08:30:00，各分已結算與未結算，共四格。每一格同時驗證紀錄清單與 POST 回應（A-27 (d′)、A-36）：
    - (9a) **schema 斷言**：每一格的回應 JSON，用 A-36 第 1 點對應狀態的封閉 schema 驗證（`additionalProperties: false`）。08:30:00 × 未結算那一格：`label` 鍵不存在，白名單以外的鍵一個都沒有。
    - (9b) **全文掃描**：對 08:30:00 × 未結算的回應本體，遞迴走訪所有鍵與字串值，不得出現：
      - label 列舉值（`bullish`、`range`、`bearish`，以值相等比對）；
      - `OutlookWeather` 的所有列舉值；
      - 色彩或色調代碼；
      - 方向詞清單（單一來源）。
    - (9c) **標籤互換不變**：比照 FL-43，在 store 層把該筆 label 在 bullish、range、bearish 之間互換，08:30:00 × 未結算的回應必須逐位元相同。
    - (9d) **資料日期**：08:30:00 × 未結算的回應，`data_as_of` 非 NULL，而且等於該筆紀錄的 T。
    - (9e) **結算後的形式**：兩個已結算格，label 只出現在 `settled_record` 內，同一物件帶 `settlement_date` 與結算結果，頂層沒有 `label`。另加一格作廢 outcome：期望值依片段核可表決定。核可前不出現 label；核可後依 A-62 R2 第 2 點的形狀，而且不出現 LM-38。
    - (9f) **前端契約測試**：
      - 08:30:00 × 未結算的區塊，只渲染狀態片段、PA-4、「資料截至 {T}」，不渲染天氣圖示，也沒有方向色彩的 class；
      - 已結算的區塊，同時渲染已結算標示與實際結果。
    - 不得 skip；效力鏈同 FL-45 (c)。
  - (10)（r3，A-73）同 T 重查時回傳同一個 `forecast_id`；兩個並發請求只產生一列。
- **FL-53**（r2 新，A-30）：A-28 的 fixture：
  - (a) 暫停期間碰到檢查點，觸發 F-2 → 寫入 `withdraw_reason`，恢復後顯示 `withdrawn_f2`；
  - (b) 先下架、後暫停、再恢復 → 仍然是 `withdrawn_f2`。
  - (c) 暫停期間在 n＝100 有正面原始結果 → 恢復後不是 `better_than_baseline`，`stats_json` 保留原始結果，旗標成立；
  - (d) 暫停期間在 n＝150 有正面原始結果 → `withdrawn_f2`，原因 `f2_deadline`；
  - (e) 在兩個檢查點之間恢復 → 到下一個檢查點之前，狀態都不上升。
  - (f)（r3，A-57）每個 `gate` 值各一個 fixture；多值時不得選到 LM-98。另加：
    - 參數試圖關掉 `replay_review_pending` → loader 拒絕；
    - 參數試圖關掉族群的 `forward_n_below_min` → loader 拒絕；
    - 參數含不在可加清單的值 → loader 拒絕；
    - claim 不存在或 `kind ≠ replay` → writer 拒絕；
    - `counts_toward_m = 0` → writer 拒絕；
    - (scope_kind, horizon) 不符 → writer 拒絕；
    - 在沒有片段的情況下啟用 `shadow_run_pending` → loader 拒絕（增補 T-1；與 FL-52 同一個 `gate_coverage_gaps`）。
- **FL-54**（r2 新，A-30）：
  - (a) `app/plan/**` 呼叫 `outlook_view` 時，`consumer` 只能引用 `PLAN_OUTPUT_SURFACES` 這個名稱，不得寫字面集合（AST）；
  - (b) plan 的計算函式沒有顯示面參數（AST）；
  - (c) `plan_record` 的 UNIQUE 存在（`sqlite_master`）；
  - (d) `SURFACE_PERMISSIONS` 未列入的鍵一律不許可；
    - （r3，A-67）另加兩項斷言：鍵的集合和六格逐項相同；格子的值不得是 callable。
  - (e) LG-22 (a) 情境：個股 `under_validation`、`shown` → `surface_not_permitted`，互換標籤後各項輸出逐位相同。
    - 加一個 fixture：T+1 的 snapshot 升級了，T 的 plan 仍然讀 T 的 snapshot，而且驗證狀態與 `display_state` 出自同一列（`outlook_view` 只讀一次 snapshot 列）；
    - （r3″，S″-3）另加一格封閉 schema 斷言：任何回應 schema 都不得同時帶 snapshot 原始的 `display_state` 與調整後的值。
  - (f) 對每個許可的格子，該顯示面的回應都帶齊 `required_disclosures`；揭露片段還沒核可的格子，判定為不許可；
  - (g) route 列舉測試：每個回應中含 `OutlookView` 衍生欄位的 route，都在 `ENDPOINT_SURFACES` 登記了非空的 `SERVES`；另驗證沒有登記時，結果為 `surface_not_permitted`。
    - （r3，A-74）另驗證每一項的 `kind ∈ {current_outlook, plan, record_list, on_demand}` 已登記；沒有登記 kind 的 route，測試失敗。
  - (h)（r3，A-69）：
    - (h1) `app.alerts.*` 與 `EXPORT_MODULES` 不可達 `app.plan.*`，也不讀 `plan_record`；
    - (h2) 任意變動 A-68 的適用欄位之後，下列各項逐位相同：提醒 payload、是否觸發與觸發時間、N、匯出檔內容。
    - D_v 前落地。
- **FL-55**（r2 新，A-34）：`sigma_d` 在 `app/` 只有一個定義（grep）。
- **FL-56**（r2 新，A-34）：basket 的表格驅動測試：
  - 比值平均與價格水準平均在 fixture 中結果不同；
  - 90% 以 |S_T| 計；
  - 排除 > 10% 輸出 `E-ADJ-COVERAGE`；
  - B1、B4 用 S_{T−h}；
  - `app.outlook.basket`、`app.outlook.volatility` 不可達 `app.sectors.*`。
- **FL-57**（r2 新，A-34）：存檔的序列可以從成員 PIT 列逐位重算。
- **FL-58**（r3 新，A-60、A-62、A-63）：
  - (a) 不變式的性質測試；
  - (b) 不回傳更正列與重放列；
  - (c) insert trigger 拒絕 replay claim；
  - (d) `in_eligible_set` 和 validation 呼叫同一個 E 函式（FL-49）。
  - (e) 選中 LM-105 或 LM-106 的列，所屬 claim 的有效 `display_state ≠ gated`。族群列另外要求：選中 LM-105、LM-106，或 A-63 第 1～3 項時，`pa9_holds` 為 false，而且 G_eff 為空。
    - (e1) 族群 `suspended_f3`、n<150，已下架或未下架：
      - 第一格：`replay_review_pending` 成立（v1 常駐），G_eff ＝ {`forward_n_below_min`, `replay_review_pending`} → 選 (c)。選出片段的 `covers` 聯集等於 G_eff（A-63 第 11 點），不得只選第 4 項，也不得選第 2 項。
      - 第二格：fixture 依 A-57 的解除路徑，建立對應的 replay claim 與 `replay_review_approved` 事件，使 G_eff ＝ {`forward_n_below_min`} → 選 (c)、第 4 項，不得選第 2 項。這只是測試情境，v1 族群沒有回放計畫（事件由測試 fixture 直接插入；寫入函式對同一 payload 拒絕，見 A-57 `REPLAY_APPROVAL_SCOPES`）。
    - (e2) 族群的 `replay_review_pending` 已解除（fixture 同 (e1) 第二格），先 `shown`（n≥150），該列已經顯示過 LM-105。PIT 違規列移出 E 後 n<150 → G_eff ＝ {`forward_n_below_min`}，同一列改選第 4 項，結算後的列也不出現 label（事件由測試 fixture 直接插入；寫入函式對同一 payload 拒絕，見 A-57 `REPLAY_APPROVAL_SCOPES`）。
    - (e3) 族群 n≥150，只因 `replay_review_pending` 而 `gated` → (c) 成立、第 5 項族群變體、結算後也不出現 label。
    - (e4) 族群 `suspended_f3`、n≥150、`replay_review_pending` 成立：(c) 成立，`display_reasons_json.gate` 含 `replay_review_pending`（不是 null），結算後也不出現 label，不得選 A-63 第 2 項。
    - (e5) 族群 `withdrawn_f2`、n≥150、`replay_review_pending` 成立：同 (e4)，不得選第 1 項。
    - (e6) 族群最新 snapshot 的 n＝150；snapshot 之後寫入一筆 `pit_violation_confirmed`。
      - 下一筆 snapshot 之前：`pa9_holds` 為真、(c) 成立、已結算列不出現 label、片段的涵蓋範圍含 `forward_n_below_min`；
      - 之後的 snapshot 依它自己的 n 判定。
      - 另一格：事件在 snapshot 讀 E 之後、寫入 snapshot 之前 commit → 期望同樣 fail-closed。
      - 再加一格：斷言 `forecast_ledger_events.kind` 列舉的每個值都已歸類。
      - RC″-2 格：事件交易早於 snapshot 開始（store 時鐘填入的 `recorded_at` 早於該 snapshot 的 `e_read_at`），但晚於 snapshot commit → 期望 fail-closed（`e_changed_since` 為真）。
      - 時鐘無關格（風控 2026-10-17 RC″ 回送確認第 4 點核可）：注入倒退的 store 時鐘，判定結果和時鐘正常時逐位相同。
      - RC‴-1 六格：
        1. 序號缺漏或不是整數 → 為真；
        2. 序號大於目前最大值 → 為真，而且有 WARNING；
        3. 讀序號與讀 E 之間注入一筆 commit → 為真；
        4. 寫入時指定 `event_id` → 拒絕寫入；
        5. snapshot 之後還原，並寫入 `db_restored` → 為真；
        6. `sqlite_master` 斷言兩欄都是 `INTEGER PRIMARY KEY AUTOINCREMENT`。
  - (f)（r3′，A-63 第 9 點）性質測試：任意的「顯示 → 移出 → n<150」序列，輸出只依當下狀態決定，和歷史無關。
- **FL-59**（r3 新，A-64、A-65）：每一種狀態各一組 schema 驗證、全文掃描、標籤互換後逐位相同。
  - A-65：resolved 一個；作廢的 fixture 分成 E 內、E 外兩格：E 內選 LM-38＋LM-109；E 外選無 W 子句的變體＋LM-110。另斷言 E 外的格子不出現 LM-38。
  - （RC″-1）加四格：大盤 × {`suspended_f3`, `withdrawn_f2`}、個股 × {`suspended_f3`, `withdrawn_f2`}。每一格的 G_eff ＝ {`replay_review_pending`}，紀錄已結算 → 期望出現 label（只在 `settled_record` 內），而且 `disclosure_fragment_ids` 含 PV-45。
  - （第九批，提案 2；風控 C9-4；風控 2026-10-18 C7-1 擴及大盤、個股）**徽章遮蔽格**（LM-153 條件 ⑨）：大盤、族群、個股 × `mask_reason` 兩值，各一格。fixture 的 snapshot n 取 137（不出現在任何已核可字面的固定文字中）。逐格斷言：
    - (m1) 徽章通過 `ValidationBadgeMasked` 的 schema 驗證。`badge_fragment_id` 為其他值、`mask_reason` 未列舉、多出欄位，都驗證失敗。
    - (m2) 徽章位置渲染出的字串，逐字等於 LM-153；兩格的渲染結果逐位相同。
    - (m3) 回應中找不到 LM-03、LM-04、LM-32、LM-33 的 ID。
    - (m4) 回應 JSON 與渲染全文都找不到「137」（照風控第九批 C9-3）。
    - (m5) 對照格 `masked = false`：徽章照常渲染，而且全文找不到 LM-153 的字串。
    - (m6) 同一回應中，同一個 claim 出現在多個徽章位置時，所有位置都是同一個物件（全遮或全不遮）。另加前端契約測試：徽章元件只從所屬頁面的單一端點回應取值。
  - **歷史值格**（LM-153 條件 ⑫，併入風控第九批 C9-4 那一格；大盤、族群、個股）：遮蔽中 × {`suspended_f3`, `withdrawn_f2`}。
    - LM-76、LM-81 照常渲染。
    - LM-75、LM-79、LM-81、LM-104 的 `{X0}`／`{X}` 等於事件欄位（`withdrawn_at_n`、`checkpoint_n`、`predecessor_withdrawn_at_n`），fixture 中這些值都 ≠ 137。
    - 同一個 fixture 把 `masked` 切成假，這些片段的渲染逐位相同。
  - （第九批，提案 5；風控 C9-10）**`format_ratio_as_pct` 的測試**（以下 `fmt`、`disp` 都指 `format_ratio_as_pct` 的輸出）：
    - 性質測試：單調；對稱：`signed=True` 時，捨入後不為零的 x 滿足 fmt(x) ＝「+」＋fmt(|x|, signed=False)、fmt(−x) ＝「−」＋fmt(|x|, signed=False)；捨入後為零時，兩者都輸出「0.00」；R > th ⇒ disp(R) ≥ disp(th)；R ≤ th ⇒ disp(R) ≤ disp(th)；負號那一側同樣要測；
    - 邊界 fixture；
    - schema 中沒有原始比值欄位；
    - 清單標頭 LM-147／LM-148 的選用。
  - （第十批，提案 2）加三格：X2 重算、收盤重算、連續兩次 X2 重算（驗證累計語意）。
- **FL-60**（r3 新，A-66）：
  - (a) 前端 route／元件列舉；
  - (b) `SERVES` 涵蓋呼叫它的元件；
  - (c) `PAGE_SURFACES` 和 D-11.4 第 9 點第 1 點的清單逐項相同。
  - (d)（r3′，A-66）：
    - 前端元件列舉中，沒有歸屬的元件不得引用 `OutlookView` 衍生型別，也不得引用 A-68 欄位（型別或 AST 檢查）；
    - 含 A-68 欄位的 route，kind 必須是 `plan`，而且兩個集合關係都成立。

## 測試要求
- **FLT-1**：quant 附錄 C 的 LA-1～LA-7、LG-1～LG-15 全部採用。LG-8 的臨界點依 M-1。另加 LG-16（新範圍）、LG-20、LG-22（r1，A-14）。
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
5. 知悉 D-14 的六道閘門（G-1～G-6；on-demand 依 G-7 同樣適用），以及 C-7 的解釋性註記。
6. #10、#15、#16、#17 照舊待決。
7. （r3，A-79）知悉 CEO 說明第 1、6、7 點（見 Consequences）；第 8 點不急。
8. （第九、十批，A-79）知悉 A-65 診斷欄位更正例外，屬揭露面放寬，已經風控核可。
9. （第九、十批，A-79）M-11 的表數隨第九、十批由 8 張改為 10 張（知悉）。

**風控**：附件 C 的重送與確認項；FL-30～FL-37 是否完整對應七條底線，請單項核對。

**quant**
- 在凍結版 dirdef 中列出：文字欄位的排除清單、M-3 的常數、C-8 的選擇、F-3 上限。
- 修正 v0.2 對解讀 A 的歸因（風控第 6 項第 1 點）。
- `plan_outcome` 的欄位定義另案提出。
- （r1 新增，A-15）：
  - `purpose` 對照表；
  - 逾時率不足 60 日時的算法；
  - 族群成員疑似分割的處理（排除該成員，或整筆作廢；若選排除，LM-65 的括號要重送）；
  - 作廢原因的判定順序（建議依序 `missing_bar_after_wait` → `dividend_factor_unusable` → `split_or_reduction_suspected` → `basket_coverage_below_90`）。

**data-engineer**：VS-6；市場 DB 能否提供逐標的的取得失敗證據（`fetch_failed` 的判定依賴它）；分割、減資的事件來源。

**devops-sre**：常駐方案；把 mark-restored 寫進整檔還原程序。

**dev-lead**：實作順序為 ADR-0026 D-8、D-6 → D-2、D-3 → D-5 → D-4 → D-7、D-8 → D-9 → D-10、D-11 → D-12。

**r2 新增的待決事項（A-37；r2' 整條取代 r2 版，r2'' 依 R''-6 修改）**
- **風控**：
  - A-36 狀態片段的逐字字面（R6-05 OS-a 或替代案）〔已決：LM-106〕；
  - A-36 第 4 點：作廢 outcome 的 on-demand 紀錄結算後可否顯示 label〔已決：A-62 R2，風控 C-3 附條件核可〕；
  - A-38 中 data-engineer 的確認回報（單項確認）。
- **creative-lead**（依 `work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md` 的 B-8 完整清單）：
  - R5-06 依否決方向重送（`surface_not_permitted`）〔已決：LM-94、LM-95，D-11.4 第 6 點〕；
  - LM-86 `{原因}` 其餘 7 個片段〔已決：LM-96～LM-102〕；
  - `pending_triggers` 的片段：引用 LM-103（r3，A-56）；
  - LM-79 的 worst_case 變體〔已決：LM-104〕；
  - `exclusion_reasons` 的 4 個片段〔已決：LM-111～LM-114〕；
  - 紀錄清單的兩個狀態片段（『期間已開始』片段同時用於 POST 回應，A-36 第 2 點；R6-05 (b′) 的 PS-a、PS-b 因採 (ii) 已不需要，撤回不審）〔已決：LM-105、LM-106〕；
  - `in_eligible_set` 的真／偽字面〔已決：LM-107～LM-110〕；
  - 已結算 on-demand 紀錄的「已結算＋實際結果」呈現字面（既有核可片段不足時起草，A-36 第 4 點）〔已決：LM-131（第八批）〕；
  - 只改名、不必重審：LM-88、LM-89 條件欄的原因值名稱；LM-71 的擴用條件。
- **quant v0.9**：
  - A-23 第 7 點；A-28 (vi)；A-33 的 L639；
  - D-19（L849）、§11（L1317）、LG-23（L1513）中的 `no_scheduled_record` 改為新名稱，並寫明：縱深防禦觸發時，原因值依 A-25 的 R_s／快照規則決定（不是 `late`），而且記 WARNING；
  - 指數序列是否套用分割門檻：已決，見 D-9.3（事先宣告 v0.10 V10-01）；B4『該股所屬族群』的判定時點：已決，見 D-4 第 7 點（V10-05）。
- **data-engineer**：
  - A-32 的查證；族群成員名單是否有 PIT 儲存；
  - D0 前 60 日窗內的除權息涵蓋：`TWT48U_ALL` 沒有歷史回補，族群可能輸出 `E-ADJ-COVERAGE`〔轉引 data-engineer 回報 L29-34〕；
  - 觀察日的確認回報送風控。
- **PM**：
  - `PLAN_OUTPUT_SURFACES` 與 `SURFACE_PERMISSIONS` 的初版；
  - 已決：D-11.4 第 9 點第 1 點（A-66）。
- **dev-lead**：A-31 的腳本改寫。

**r3 新增的待決事項（A-79；含 r3′、r3″、增補、RC‴ 補入的項目）**
- **CEO**：#10 決定 A-57 要啟用哪些 `gate` 值（#10 只能加，不能減）；還沒回覆時，A-63 第 5 項要先起草。
- **風控**：N-1 的處理提案（A-77 第 12 項）送審〔已決：甲案（風控 2026-10-17 第九批 TA 提案確認）〕。
- **tech-architect**：N-1 的處理提案（A-77 第 12 項），標明方向，送風控審；D_v 前必須核可〔已決：甲案（風控 2026-10-17 第九批 TA 提案確認）〕。
  - A-63 第 11 點：`outlook_block` 的選用優先序、selector 簽章、LM-144 的 slot 登記，以及 `e_changed_since` 情形下的驗證徽章遮蔽（第九批，送風控審；D_v 前）〔已決：第九批提案 1、2（風控 2026-10-17 第九批 TA 提案確認 C9-1～C9-6）〕。
  - 平日、而且不是已接入官方休市日表所列休市日的日期 d，如果既不在 D-8.1 (i)，也不在 (ii)，就不是觀察日，也不會有缺日列。這類日期的偵測與 §4.2 揭露方式，由 TA 提案、送風控，D_v 前核可（風控 2026-10-17 疑義裁定回送確認 Q-3）〔已決：A 案（風控 2026-10-18 C9-7 與 Q-3 提案確認），見 A-77 第 10 項〕。
  - （第九、十批）大盤與個股 snapshot 落後（E 變動事件之後、下一筆 daily snapshot 之前）時，徽章與 LM-12 的 n、k、區間與狀態怎麼處理，由 TA 提案、送風控，D_v 前核可〔已決：甲案（風控 2026-10-18 C9-7 與 Q-3 提案確認）〕。
  - （第九、十批）ADR-0028 CS-17 的同步修訂（另開 ADR-0028 commit；依 CS-21 通則送風控單項確認）〔已決：風控 2026-10-18 已單項確認（C9-7 與 Q-3 及 CS-17 提案確認第二節第 3 項）；ADR-0028 與本 ADR 同一次 push 落地，ADR-0028 的 commit 在前〕。
  - （第九、十批）A-77 第 12 項 (h5)：候選 T＝d 記 `inputs_not_ready` 的計數來源（風控第九批 S9-3，suggested；不擋 D_v）。
  - （第九、十批，事先宣告 v0.12 V12-20）補到資料後的診斷標籤，存放處由 TA 定：只增不改，不得寫入 `forecast_outcome`；D-9 結算程式實作前定案。
- **creative-lead**（逐字送風控審）：
  - A-63 第 5 項（含族群變體；個股變體與族群變體各受 RC′-8 限制）；
  - 無 W 子句的作廢變體；
  - 「原本的預測（已作廢）」框架；
  - A-72 狀態句（不得預告開始記錄的日期，也不得暗示「快要開放」）；
  - RC′-3 的多閘門片段（每個 (scope_kind, slot) 的涵蓋變體或並列片段）；
  - R-5、R-7 翻案伴隨句（RC‴-4；列入 D_v 前置字面清單，未核可不得進入 D_v）〔已決：R-5＝LM-143（第九批）；R-7＝LM-150～LM-152（第十批）；FAIL_CLOSED＝LM-154（第十二批）〕。
- **quant**：
  - 大盤與個股的 `forward_n_below_min` 是否有登記門檻；
  - A-63 第 10 點的揭露項（族群重新變成 PA-9 成立的事件，以及受影響的列數）；
  - 驗證報告 §4.2 單獨揭露 `session_calendar_conflict` 筆數（A-77 第 5 項）；
  - 起算日用語；LM-91 第 5 條；v0.10 的 D-20 ① 與 None 規則；A-76 的補定義；趨勢條件要不要拆成兩條。
  - （第九、十批）C9-9（dirdef 凍結前）〔已決：事先宣告 v0.12 V12-19，風控 2026-10-18 v0.12 審查 Q12-4〕；
  - （第九、十批）R10-3 的補 bar 規則（凍結前）〔已決：事先宣告 v0.12 V12-20，風控 2026-10-18 v0.12 審查 Q12-4；ADR 側見 A-65 R10-3 條文〕；
  - （第九、十批）R10-5 書面確認〔已決：事先宣告 v0.12 V12-12，風控 2026-10-18 v0.12 審查第二節 5〕；
  - （第九、十批）`x2_shift_json` 累計語意書面確認〔已決：事先宣告 v0.12 V12-11，風控 2026-10-18 v0.12 審查第二節 5〕；
  - （第九、十批）「更正翻轉」的比較基準〔已決：事先宣告 v0.12 V12-08，風控 2026-10-18 v0.12 審查第二節 1〕；
  - （第九、十批）§4.2 的新揭露項：X2 事件的 outcome 筆數、有更正的紀錄筆數（風控第九批 S9-4，suggested）、診斷欄位更正筆數、`rejected_count`、`void_late_data_count`、撤銷事件、LM-154 列數，以及未觀察平日的 ①～④。
- **data-engineer**：
  - F-8（A-77 第 9 項），以及 `session_calendar_conflict` 的根因流程；
  - suggested：查根因時一併確認，個股與族群成員在 d 的 bars 有沒有進入 PIT 輸入或結算；
  - A-75 的重抓路徑；A-78 的查證。
- **PM**（知悉）：A-72 讓臨時查詢也要等全部閘門成立；A-73 讓 08:30 前產生的紀錄在白天照常顯示 label。A-68 的前提是 AC-S-3「N 不依 plan 欄位計數」，以及 NP-A3 第 (5) 項的修訂。
- **D_v 前置**：N-1 未核可不得進入 D_v（RC‴-3）〔已決：甲案已核可（風控 2026-10-17 第九批 TA 提案確認；風控 2026-10-18 v0.12 審查第四節），N-1 不再擋 D_v〕；R-5、R-7 未核可不得進入 D_v（RC‴-4）〔已決：R-5＝LM-143（第九批）；R-7＝LM-150～LM-152（第十批）；FAIL_CLOSED＝LM-154（第十二批）〕；未觀察平日（風控 2026-10-17 疑義裁定回送 Q-3）的偵測與 §4.2 揭露未核可不得進入 D_v（風控 2026-10-17 疑義裁定回送確認 Q-3）〔已決：A 案（風控 2026-10-18 C9-7 與 Q-3 提案確認）〕；C9-7（大盤與個股的 snapshot 落後處理）未核可不得進入 D_v〔已決：甲案（風控 2026-10-18 C9-7 與 Q-3 提案確認）〕；quant 的 R10-5 書面確認〔已決：事先宣告 v0.12 V12-12，風控 2026-10-18 v0.12 審查第二節 5〕。

## 未查證事項與作者揭露
- 沒有執行任何程式或測試，也沒有讀任何 DB。
- `panel.py`、`market_panel.py` 的可見性細節與大部分行號，轉引自 R-107，這次沒有重讀。
- 08:30 盤前委託、SQLite 部分唯一索引的行為、每年 220 MB 的量級，都是推論。
- 「在 n＝150 時多數 claim 會退出」是由 quant 的合成表換算，不代表台股的實際情況。

---

## 修訂紀錄

> r1（2026-10-16）依 tech-architect 修訂提案 A-1～A-21 套用；本 ADR 適用 A-1～A-15，A-16～A-21 見 ADR-0028。
> 提案來源：`work/reviews/2026-10-16-ADR-0027與0028修訂提案A1至A21-tech-architect.md` 附件 A。
> 被改寫或取代的原文逐字保留於下；「新增」類條目沒有被取代的原文。引用區塊內的文字即 r1 之前的原文。
> 原文中的「D-15」「FL-xx」等編號指 r1 之前的原條文。

**A-1（D-15、FL-40、FL-41、FL-41b、FL-41c）**
- r1（2026-10-16，tech-architect A-1）：D-15 原第 1 點——
  > - 政策表 v0（ADR-0025 D-4.3）的任何條件，都不得引用 `avg_cost`、`cost`、`cost_anchor`、`pnl_vs_cost`、`unrealized_pnl_pct`，由 loader 守門。

  改為見 §D-15 第 1～5 點。
- r1（2026-10-16，tech-architect A-1）：D-15 原第 2 點——
  > - advice 規則中，方向為 reduce、stop_loss、take_profit 的規則，條件也不得引用 `position.unrealized_pnl_pct`。

  改為見 §D-15 第 1～3 點。原第 3、4 點保留，現為 §D-15 第 6 點。
- r1（2026-10-16，tech-architect A-1）：FL-40 原文——
  > - **FL-40**：政策表 loader 遇到引用 D-15 所列欄位的條件就拒絕（表格驅動測試）。

  改為見 §對實作的約束 FL-40。
- r1（2026-10-16，tech-architect A-1）：FL-41 原文——
  > - **FL-41**：advice 規則中 reduce、stop_loss、take_profit 方向的規則不引用 `unrealized_pnl_pct`（掃描 `default.yaml` 的測試）。

  改為見 §對實作的約束 FL-41（提案註明：原本「掃描 `default.yaml`」的寫法作廢）。
- r1（2026-10-16，tech-architect A-1）：FL-41b、FL-41c 為新增，無被取代原文；見 §對實作的約束。

**A-2（D-1 模組表）**
- r1（2026-10-16，tech-architect A-2）：新增一列 `app/forecast/views.py`，無被取代原文；見 §D-1。

**A-3（D-4.6 第三點）**
- r1（2026-10-16，tech-architect A-3）：原文——
  > - `/api/advice` 只讀預測帳。

  改為見 §D-4 第 6 點第三個子項。

**A-4（D-7.2）**
- r1（2026-10-16，tech-architect A-4）：原文——
  > 2. **執行順序**：記錄 → 結算 → 缺日稽核 → 驗證快照。

  改為見 §D-7 第 2 點。

**A-5（D-11.2、FL-47）**
- r1（2026-10-16，tech-architect A-5）：D-11.2 原文（欄位與 seed 兩處）——
  > - 欄位：`claim_id`、`computed_for_session`、`eval_kind ∈ {daily, checkpoint}`、`checkpoint_n`、`n`、`m_at_eval`、`m_eff`、`K`、`alpha_star`、`status`（四態）、`display_state ∈ {gated, shown, suspended_f3, withdrawn_f2}`、`void_rate`、`stats_json`、`bootstrap_seed`、`code_commit`、`computed_at`；
  > - `UNIQUE(claim_id, computed_for_session, eval_kind)`；
  > - `bootstrap_seed` 由 `(claim_id, session)` 確定性導出（風控第 3 項）。

  改為見 §D-11 第 2 點。
- r1（2026-10-16，tech-architect A-5）：FL-47 為新增，無被取代原文；見 §對實作的約束。

**A-6（D-11.4、FL-42～FL-44）**
- r1（2026-10-16，tech-architect A-6）：D-11.4 原四點保留不變，第 5～12 點為新增，FL-42～FL-44 為新增，皆無被取代原文；見 §D-11 第 4 點。

**A-7（D-11.1、FL-49）**
- r1（2026-10-16，tech-architect A-7）：D-11.1 原文——
  > - `trigger=scheduled`、`late=0`、`supersedes_id IS NULL`、claim 為 forward、日期 ≥ D_v，而且不是已確認的 PIT 違規列。

  改為見 §D-11 第 1 點。
- r1（2026-10-16，tech-architect A-7）：FL-49 為新增，無被取代原文；見 §對實作的約束。

**A-8（D-11.6 F-3、D-3 `forecast_ledger_events`、FL-51）**
- r1（2026-10-16，tech-architect A-8）：D-11.6 原文——
  > - 上限依 quant 登記：逾時率 >10%、digest 不一致率 >2%、PIT 違規 ≥1 筆；

  改為見 §D-11 第 6 點（逾時率時間窗、PIT 違規偵測、暫停原因為新增；digest 不一致率與恢復顯示條件維持原文）。
- r1（2026-10-16，tech-architect A-8）：D-3 原文——
  > - `forecast_ledger_events(event_id, kind ∈ {db_restored, f3_resume_approved}, payload_json, recorded_at)`。

  改為見 §D-3 `forecast_ledger_events`。
- r1（2026-10-16，tech-architect A-8）：FL-51 為新增，無被取代原文；見 §對實作的約束。

**A-9（D-12 下架原因列舉值、FL-45、FL-46）**
- r1（2026-10-16，tech-architect A-9）：新增一段，無被取代原文；見 §D-12「下架原因列舉值」。FL-45、FL-46 為新增。

**A-10（D-14 末句、FL-48）**
- r1（2026-10-16，tech-architect A-10）：原文（提案註記其為循環定義）——
  > D_v ＝該 claim 第一筆 E 紀錄的 T。

  改為見 §D-14 末句。
- r1（2026-10-16，tech-architect A-10）：FL-48 為新增，無被取代原文；見 §對實作的約束。

**A-11（D-9.3、FL-50）**
- r1（2026-10-16，tech-architect A-11）：D-9.3 原文——
  > - `split_or_reduction_suspected`：窗內單日報酬超過漲跌幅限制加容差（推定，不是確認的事件） → `excluded_corporate_action`

  改為見 §D-9 第 3 點。
- r1（2026-10-16，tech-architect A-11）：`basket_coverage_below_90` 補一句，無被取代原文；見 §D-9 第 3 點。
- r1（2026-10-16，tech-architect A-11）：FL-50 為新增，無被取代原文；見 §對實作的約束。

**A-12（D-3 `plan_record`）**
- r1（2026-10-16，tech-architect A-12）：新增欄位，無被取代原文；見 §D-3 `plan_record`。

**A-13（D-7.8 on-demand）**
- r1（2026-10-16，tech-architect A-13）：補一句，無被取代原文；見 §D-7 第 8 點。

**A-14（FLT-1）**
- r1（2026-10-16，tech-architect A-14）：加上 LG-16（新範圍）、LG-20、LG-22，無被取代原文；見 §測試要求 FLT-1。

**A-15（待決事項 quant 段）**
- r1（2026-10-16，tech-architect A-15）：新增四項，無被取代原文；見 §待決事項 quant。

---

> r2（2026-10-17）依 tech-architect 修訂提案 A-22～A-41 套用；本 ADR 適用 A-22～A-37、A-41，A-38～A-41 見 ADR-0028。檔頭狀態維持 proposed。
> 套用順序與提案來源（後者取代前者的對應條目）：
> 1. r2：`work/reviews/2026-10-17-ADR-0027與0028修訂提案A22至A41-tech-architect.md` 附件 A（A-22～A-41）。
> 2. r2'（取代 r2 的 A-22～A-41 中標示者）：`work/reviews/2026-10-17-ADR-0027與0028修訂提案r2prime-tech-architect.md` 附件 A。r2' 標示「整條取代」者：A-23、A-25、A-27、A-28、A-29、A-33、A-36、A-37（及 ADR-0028 的 A-38）；其餘（A-22、A-24、A-26、A-30、A-31、A-34、A-35）只改所列部分；未列的 A-32、A-41 照 r2 原文。
> 3. r2''（只動 A-27 (d′)、A-30 FL-52 (d)／FL-52b (9)、A-35、A-36、A-37／B'-1）：`work/reviews/2026-10-17-ADR-0027修訂提案r2雙撇A36增補-tech-architect.md`（R''-1～R''-6）。第四節「另案」與第五節「待確認事項」不套用。
> 風控確認依據：
> - `work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md`
> - `work/reviews/2026-10-17-A-15-事先宣告v0.9核對與A36及B0單項確認-風控.md`（A-36：APPROVE WITH CONDITIONS，見該檔 L21 與「追加一｜A-36」L111 起）
> 被改寫或取代的原文逐字保留於下；「新增」類條目沒有被取代的原文。引用區塊內的文字即 r2 之前的原文。
> 原文與新文中的「附件 B-x」「附件 B'-x」「風控附件 B 確認 B-x」，指上列提案檔與風控確認檔內的編號，不是本 ADR 的章節。
> 本次套用不含 ADR-0028 r3（觀察日來源，另案）。

**A-22（D-12 VETO 底線第 2 點、FL-31）**
- r2（2026-10-17，tech-architect A-22，r2' 改小標與排列）：D-12 主方案 F2-B「VETO 底線」第 2 點原文——
  > - 不得刪除條件二。延後條件二須 CEO 書面同意，風控保留書面異議。

  改為見 §D-12 主方案 F2-B「VETO 底線」。
- r2（2026-10-17，tech-architect A-22）：FL-31 補一句，無被取代原文；見 §對實作的約束 FL-31。

**A-23（D-12「下架原因列舉值」）**
- r2（2026-10-17，tech-architect A-23，r2' 整條取代 r2 版）：原文（`withdraw_reason` 列舉中的兩項）——
  > - `f2_invalid_stop`：一般情境下條件一成立；
  > - `f2_invalid_stop_worst_case`：條件一只在 W 情境下成立（作廢率 > 5%）。

  改為見 §D-12「下架原因列舉值」與其後的「逐檢查點判定」。`f2_deadline` 與該段其餘原文保留。

**A-24（FL-32、FL-45、FL-45b）**
- r2（2026-10-17，tech-architect A-24，r2'）：FL-32 原文——
  > - **FL-32**（底線 3）：作廢率 >5% 時，F-2 的判定取一般情境與 W 之中比較差的那個。

  改為見 §對實作的約束 FL-32。
- r2（2026-10-17，tech-architect A-24，r2'）：FL-45 原文——
  > - **FL-45**（r1，A-9）：每個下架原因都對應到已核可的片段：LM-75、LM-74，以及新片段（待起草）。

  改為見 §對實作的約束 FL-45。
- r2（2026-10-17，tech-architect A-24）：FL-45b 為新增，無被取代原文。

**A-25（D-11.4 第 6 點）**
- r2（2026-10-17，tech-architect A-25，r2' 整條取代 r2 版）：D-11.4 第 6 點原文（首行與 policy 一句）——
  > - 6. **`unavailable` 的原因**（封閉列舉，依下列優先序取第一個）：`suspended_f3` → `withdrawn_f2` → `gated` → `before_dv` → `no_scheduled_record` → `late` → `insufficient` → `voided`。
  >   - policy 只吃 `trigger=scheduled`、`late=0`、同一個 T 的原始紀錄。on-demand 紀錄對 policy 一律是 `no_scheduled_record`（風控待確認）。

  改為見 §D-11 第 4 點的第 6 項。「同一個 T 的 plan 讀不到 `voided`」一句與「policy 只吃…原始紀錄。」保留。

**A-26（D-11.4 第 9 點）**
- r2（2026-10-17，tech-architect A-26，r2' 只改第 2、3 點並新增 2a、2b）：D-11.4 第 9 點原文——
  > - 9. **依顯示面判定可用性**（v0.5 V5-09，待風控）：若採用，最嚴格的顯示面以常數登記在政策表，作為 `consumer` 參數傳入，由 `display.py` 判定，plan 端不得自行判斷。

  改為見 §D-11 第 4 點的第 9 項。

**A-27（D-11.4 第 11 點）**
- r2（2026-10-17，tech-architect A-27，r2' 整條取代 r2 版；r2'' R''-2 取代 (d′)）：D-11.4 第 11 點原文（三個子項）——
  > - `withdrawn_f2`、`suspended_f3` 期間，尚未結算的紀錄不出現 label；
  > - `gated` 的族群，不論是否已結算，都不出現 bullish／bearish（PA-9）；
  > - 這一點是我補的，風控待確認。

  改為見 §D-11 第 4 點的第 11 項。

**A-28（D-11.4 第 12 點）**
- r2（2026-10-17，tech-architect A-28，r2' 整條取代 r2 版）：D-11.4 第 12 點原文——
  > - 12. **display_state 單值優先序**：`suspended_f3` > `withdrawn_f2` > `gated` > `shown`。F-3 恢復後，若 F-2 仍在下架，就顯示下架（風控待確認）。

  改為見 §D-11 第 4 點的第 12 項。

**A-29（D-3 資料表）**
- r2（2026-10-17，tech-architect A-29，r2' 整條取代 r2 版）：`forecast_record` 加 `window_started` 與 CHECK、`forecast_run`／`forecast_scope_snapshot` 同一交易、`plan_record` 加 `data_as_of`／`UNIQUE`／`in_holdings_or_watchlist_at_plan`／`consumer_surfaces`／`restricting_surfaces`、`forecast_input_series` 加 `series_kind`，皆為新增，無被取代原文；見 §D-3。

**A-30（FL-44、FL-52、FL-52b、FL-53、FL-54）**
- r2（2026-10-17，tech-architect A-30，r2'；FL-52 (d)、FL-52b (9) 由 r2'' R''-3、R''-4 取代）：FL-44 原文——
  > - **FL-44**（r1 新，A-6）：`plan_record.outlook_display_state` 一定非空；`availability = evaluated`，若且唯若 `display_state = shown`，而且那筆紀錄符合 D-11.4 第 6 點的條件。

  改為見 §對實作的約束 FL-44。
- r2（2026-10-17，tech-architect A-30）：FL-52、FL-52b、FL-53、FL-54 為新增，無被取代原文。

**A-31（D-15 第 3 點、FL-40、FL-41、FL-41d）**
- r2（2026-10-17，tech-architect A-31，r2' 將 3d 拆成 3d、3e）：D-15 第 3 點原文保留，後面新增 3a～3e 與「對既有程式的影響」，無被取代原文；見 §D-15 第 3 點。
- r2（2026-10-17，tech-architect A-31）：FL-40 原文——
  > - **FL-40**（r1 改，A-1）：政策表 loader 遇到 `POLICY_FORBIDDEN_FIELDS` 的任一欄位就拒絕（表格驅動：每個欄位 × 每個條件類別）。

  改為見 §對實作的約束 FL-40。
- r2（2026-10-17，tech-architect A-31）：FL-41 加 (d)、FL-41d 為新增，無被取代原文。

**A-32（D-9.3 `split_or_reduction_suspected`）**
- r2（2026-10-17，tech-architect A-32）：補四點，無被取代原文；見 §D-9 第 3 點。r2' 未列此條，照 r2 原文。

**A-33（D-14 首句、FL-38）**
- r2（2026-10-17，tech-architect A-33，r2' 整條取代 r2 版）：D-14 首句原文——
  > **G-1～G-7 全部成立之前，recorder 拒絕寫入任何 `trigger=scheduled` 的前瞻紀錄**（風控第 1 項、底線 7、R-116）：

  改為見 §D-14（「（風控第 1 項、底線 7、R-116）」移到 G-1～G-7 清單的引言）。
- r2（2026-10-17，tech-architect A-33）：FL-38 原文——
  > - **FL-38**：recorder 在 G-3、G-4 不成立時拒絕寫入排程紀錄（單元測試）；G-1、G-2、G-5、G-6 由 qa 在 PR 描述中核對 CEO 決策紀錄與上線證據。

  改為見 §對實作的約束 FL-38。

**A-34（D-1 模組表、D-4 第 7 點、FL-55～FL-57）**
- r2（2026-10-17，tech-architect A-34，r2' 只改引用）：依據改為 v0.8 L1217（§9.3 第 15 點）、v0.8 L402 起（§2.1 σ_d 定稿條文）。D-1 新增三列、D-4 新增第 7 點、FL-55～FL-57 為新增，無被取代原文；見 §D-1、§D-4 第 7 點、§對實作的約束。

**A-35（Consequences）**
- r2（2026-10-17，tech-architect A-35，r2'；r2'' R''-5 整條取代 r2' 版）：Consequences「代價與壞處」新增三點，無被取代原文；見 §Consequences。

**A-36（D-7.8 on-demand）**
- r2（2026-10-17，tech-architect A-36，r2' 整條取代 r2 版；r2'' R''-1 整條取代 r2' 版）：D-7.8 第 8 點新增三點與 (ii) 的處理及其 4 項條件，無被取代原文；見 §D-7 第 8 點。
- **依據**：風控 2026-10-17「追加一」——`work/reviews/2026-10-17-A-15-事先宣告v0.9核對與A36及B0單項確認-風控.md`「追加一｜A-36」（L111 起），結論 APPROVE WITH CONDITIONS（該檔 L21）；4 項 required 與 1 項 suggested 見 r2'' R''-1～R''-6。

**A-37（待決事項）**
- r2（2026-10-17，tech-architect A-37，r2' 整條取代 r2 版；r2'' R''-6 修改「風控」「creative-lead」兩段）：新增「r2 新增的待決事項」一段，現有各段原文保留，無被取代原文；見 §待決事項。附件 B'-1 的「建議」「誰決定」欄修改在本 ADR 內沒有對應位置（附件 B' 表在提案檔，不在本 ADR），未套用；其結論（已決 (ii)）已寫在 §D-7 第 8 點。

**A-41（檔頭）**
- r2（2026-10-17，tech-architect A-41）：檔頭新增「r2 修訂」一行，無被取代原文。

---

> r3 系列（2026-10-17）依 tech-architect 修訂提案 A-54～A-86 套用；本 ADR 適用 A-54～A-83、A-85、A-86。A-84（ADR-0028 CS-12「不設執行期旗標」）屬 ADR-0028，已於 commit 1d69acd 落地，不重複套用（來源：r3′ 註記「A-84 已落地」）；A-84 仍計入下方方向統計。檔頭狀態維持 proposed。沒有新增 A-87 以後的條號。
> 套用順序與提案來源（衝突時 RC‴ > 增補 > r3″ > r3′ > r3；後者被前者覆蓋的部分以前者為準）：
> 1. r3：`work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md`（A-54～A-86）；風控審查：`work/reviews/2026-10-17-ADR-0027-r3提案審查-風控.md`（R3-1～R3-13、S-1～S-6）。
> 2. r3′：`work/reviews/2026-10-17-ADR-0027-r3prime補正-tech-architect.md`（R3-1～R3-13、S-1～S-6、X2 同一定義）；風控確認：`work/reviews/2026-10-17-ADR-0027-r3prime單項確認含A96A97與ACB5a-風控.md`（RC′-1～RC′-9）。
> 3. r3″：`work/reviews/2026-10-17-ADR-0027-r3雙撇併入RC與ADR-0028-A96A97修訂-tech-architect.md`（只取 ADR-0027 的部分，即 RC′-1～RC′-9 的條文；其中 ADR-0028 的 A-96′／A-97′ 與 ADR-0027 FL-25 的 `date_anomaly` fixture 增補不在這次套用範圍，另開 commit）；風控最後確認：`work/reviews/2026-10-17-ADR-0027-r3雙撇與v0.11同批最後確認-風控.md`（RC″-1～RC″-6、N-1、16 項核對）。
> 4. 增補：`work/reviews/2026-10-17-ADR-0027-r3雙撇增補RC雙撇與T1至T5-tech-architect.md`（RC″-1～RC″-5、N-1、T-1～T-5、S″-1～S″-3）。不套用舊增補 `work/reviews/2026-10-17-ADR-0027-r3雙撇增補RC-tech-architect.md`（origin 名稱錯誤）。
> 5. RC‴：`work/reviews/2026-10-17-ADR-0027-RC雙撇增補回送項確認-風控.md` 第二節「RC‴ 逐字條文」RC‴-1～RC‴-4。N-1 的 origin 最終名稱是 `post_x2_final_run`。
> 被改寫或取代的原文是 9ba01d6 版的 ADR 原文，逐字保留於下；r3、r3′、r3″ 的中間版沒有落過檔，不進修訂紀錄。「新增」類條目沒有被取代的原文。引用區塊內的文字即 r3 之前（9ba01d6）的原文。
> 提案內的編號對照（本 ADR 本文不再引用這些提案內編號，只引用 A 編號與條號）：
> - R3-1 → A-56；R3-2 → A-57；R3-3 → A-59、A-61；R3-4 → A-61；R3-5、R3-6 → A-63；R3-7 → A-62、A-65、D-7.8 第 8 點第 4 子點、FL-52b (9e)；R3-8 → A-66；R3-9 → A-68；R3-10 → A-72；R3-11 → A-75、A-77、FL-19；R3-12 → 方向標示；R3-13 → A-54。
> - S-1 → D-9.3（A-85）；S-2 → D-4 第 7 點（A-85）；S-3 → D-11.4 (d′) 與 D-7.8 第 8 點第 2 子點；S-4 → A-65；S-5 → A-75 (iii)；S-6 → A-60。
> - RC′-1、RC′-2、RC′-3 → A-63（含 A-57 (iv) 與 FL-52、FL-58）；RC′-4 → A-77 第 5 項；RC′-5 → A-75、FL-19；RC′-6 → A-72；RC′-7 → 方向標示；RC′-8 → A-63 第 5 項、A-54、A-57、A-79；RC′-9 → A-79 的 CEO 說明。
> - RC″-1 → A-63／A-65 的 (e)（連帶 A-62 R2 第 1 點）；RC″-2 → RC′-2 的比較基準（連帶 D-3）；RC″-3 → FL-52 窮舉；RC″-4 → CEO 說明第 8 點；RC″-5 → A-77 第 7 項；N-1 → A-77 第 12 項；T-1 → A-57；T-2、T-3 → A-63；T-4 → A-65；S″-1 → A-75；S″-2 → FL-19 (e)③；S″-3 → A-57。
> - RC‴-1 → RC′-2；RC‴-2 → A-77 第 7 項；RC‴-3 → A-77 第 12 項；RC‴-4 → A-65（取代增補 T-5 的條文）。RC″-6 只涉及事先宣告 v0.11，不在本 ADR。
> 方向統計（RC′-7；沒有任何一條換類別）：
>
> | 方向 | 條數 | 條號 |
> |---|---|---|
> | 收緊 | 19 | A-54～A-57、A-60、A-61、A-63～A-67、A-69、A-70、A-72、A-74～A-78 |
> | 補定義（兩面） | 2 | A-71、A-73 |
> | 不變 | 9 | A-59、A-79～A-86 |
> | 不變＋收緊 | 1 | A-58 |
> | 含有條件放寬的兩面 | 2 | A-62「收緊＋有條件放寬（R2，依風控 r3 審查 C-3；片段核可前 fail-closed）」；A-68（字面與事先宣告 v0.10 V10-12 逐字相同） |
>
> 合計 33，寫成「19／2／9／1／2」。A-77 的方向標註為「收緊（第 5 項相對事先宣告為補定義（兩面），風控 2026-10-17 單項確認）」。〔第九、十批更新：A-77 標註與累計統計（18／2／9／1／3）見修訂紀錄第九、十批段〕

**A-54（D-11.4 第 6 點 `surface_not_permitted` 子項）**
- r3（2026-10-17，tech-architect A-54；加註依 R3-13、r3″ RC′-8；方向：收緊）：D-11.4 第 6 點「`reasons` 的字面對應」`surface_not_permitted` 子項原文——
  > - `surface_not_permitted`：R5-06 依否決方向重送、核可之前，沒有可用的片段，D_v 會被擋住。

  改為見 §D-11 第 4 點第 6 項。

**A-55（FL-52 (e)～(g)）**
- r3（2026-10-17，tech-architect A-55；方向：收緊）：FL-52 新增 (e)～(g)，無被取代原文；見 §對實作的約束 FL-52。

**A-56（D-11.4 第 6 點其餘七個值與 `pending_triggers`）**
- r3（2026-10-17，tech-architect A-56；R3-1 加 LM-97 守門；方向：收緊（補上守門））：D-11.4 第 6 點原文（含 A-85 要求刪除的「NS-a 刪除」一行）——
  > - NS-a 刪除。
  > - 其餘七個值：與 `pending_triggers` 的「恢復前這條條件無法成立」片段同一批送審（A-37）。

  改為見 §D-11 第 4 點第 6 項。「NS-a 刪除」是指令句，不留在本文。
- r3（2026-10-17，tech-architect A-56）：D-11.4 第 7 點末項原文——
  > - 下架或暫停時，`pending_triggers` 不得把展望條件列成「等待中」。

  改為見 §D-11 第 4 點第 7 項（加註 `pending_triggers` 的渲染見第 6 點，LM-103）。

**A-57（D-11.4 第 4 點第 4 子項、第 12 點 (iv)）**
- r3（2026-10-17，tech-architect A-57；r3′ R3-2；r3″ RC′-1、RC′-8；增補 RC″-2 連帶、T-1、S″-3；方向：收緊）：D-11.4 第 12 點 (iv) 原文——
  > - (iv) `display_reasons_json` 的結構固定為 `{suspend: [...], withdraw: {...}|null}`。

  改為見 §D-11 第 4 點第 12 項 (iv)。
- r3（2026-10-17，tech-architect A-57，r3′ R3-2）：D-11.4 第 4 點第 4 子項原文——
  > - CEO #10 的結果作為參數注入。

  改為見 §D-11 第 4 點第 4 子項。

**A-58（D-12 第 5、6 點、FL-45 (b)）**
- r3（2026-10-17，tech-architect A-58；方向：不變＋收緊）：D-12「逐檢查點判定」第 5、6 點原文（被取代的部分）——
  > - `LM79_WITHDRAW_REASON_FRAGMENTS` ＝ {`f2_invalid_stop`: LM-75, `f2_deadline`: LM-74, `f2_invalid_stop_worst_case`: **LM-79 的 worst_case 變體（待送）**}。
  > - **LM-87 不得代入 LM-79**（會出現三層括號）。變體核可之前，這一項空著，FL-45 會失敗。
  >
  > 6. D_v 前，LM-79 的 worst_case 變體必須核可；否則 FL-45 失敗，不得出貨。

  改為見 §D-12「逐檢查點判定」第 5、6 點。第 5 點的 `LM81_WITHDRAW_REASON_FRAGMENTS` 一行與「LM-79 讀前一版的原因時…」一行保留。
- r3（2026-10-17，tech-architect A-58）：FL-45 (b) 原文——
  > - (b) LM-79、LM-81 只從各自的對照表取值；另加斷言：LM-87 永遠不會出現在 LM-79 中。

  改為見 §對實作的約束 FL-45 (b)。

**A-59（D-11.1 用詞定義）**
- r3（2026-10-17，tech-architect A-59；R3-3 更新 LM-38 狀態；方向：不變）：新增，無被取代原文；見 §D-11 第 1 點。

**A-60（D-11.4 第 11 點 (f)、FL-58）**
- r3（2026-10-17，tech-architect A-60；S-6；方向：收緊）：新增不變式與取列範圍，無被取代原文；見 §D-11 第 4 點第 11 項 (f)、FL-58。(f) 首句的括號依 A-85 刪除，原文——
  > - **(f)** 每筆紀錄帶 `in_eligible_set: bool`（r2 叫 `counts_in_primary`，改名），值等於該筆是否屬於 E，與 validation 呼叫同一個函式（FL-49）。

  「改名」是指令句，不留在本文。

**A-61（D-11.4 第 11 點字面對應、FL-52 (d)）**
- r3（2026-10-17，tech-architect A-61；R3-3、R3-4；方向：收緊）：D-11.4 第 11 點「PIT 違規列的標示」原文——
  > - PIT 違規列的標示：已確認的 PIT 違規列要顯示「不計入主統計（原因）」，視覺上不得和 E 內的紀錄相同（前端契約測試）。

  改為見 §D-11 第 4 點第 11 項「PIT 違規列的標示」（以 LM-110＋LM-114 呈現，視覺區隔的要求保留）。字面對應與上畫面的前提為新增，無被取代原文。

**A-62（D-11.4 第 11 點 (d)、(d′)、R1、R2；D-7.8 第 8 點第 4 子點）**
- r3（2026-10-17，tech-architect A-62；r3′ R3-5、R3-7；增補 RC″-1 (3)；方向：收緊＋有條件放寬（R2，依風控 r3 審查 C-3；片段核可前 fail-closed））：D-11.4 第 11 點 (d′) 原文——
  > - 狀態片段的意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」。這句只是語意，逐字字面待風控核可（A-36 第 2 點）。

  改為見 §D-11 第 4 點第 11 項 (d′)（依 S-3，逐字字面為 LM-106；守門 R1、R2 見 A-62）。
- r3（2026-10-17，tech-architect A-62，R3-7 (3)）：D-7.8 第 8 點第 4 子點「作廢」一行原文——
  > - outcome 為 `unresolvable_missing_data` 或 `excluded_corporate_action`（作廢）時，沒有實際結果可以並列。風控確認處理方式之前，不顯示 label，只顯示 `status_reason` 的既有片段。

  改為見 §D-7 第 8 點「4. 結算之後」。R1、R2 為新增，無被取代原文。

**A-63（D-11.4 第 4 點第 1 子項、第 11 點 (c)、(e)、單列狀態片段；RC′-1～RC′-3、RC″-1～RC″-3、T-2、T-3）**
- r3（2026-10-17，tech-architect A-63；r3′ R3-5、R3-6；r3″ RC′-1、RC′-2、RC′-3、RC′-8；增補 RC″-1、RC″-2、RC″-3、T-2、T-3；RC‴-1；方向：收緊）：D-11.4 第 11 點 (c) 原文——
  > - (c) 族群而且 `gated`：不論是否結算都不出現（PA-9）；

  改為見 §D-11 第 4 點第 11 項 (c)。
- r3（2026-10-17，tech-architect A-63，RC′-1 (2)）：D-11.4 第 4 點第 1 子項原文——
  > - 族群 n<150 時，任何對外回應都不出現 bullish／bearish（PA-9、LG-15）；

  改為見 §D-11 第 4 點第 1 子項。
- r3（2026-10-17，tech-architect A-63，增補 RC″-1 (1)）：D-11.4 第 11 點 (e) 原文——
  > - (e) 大盤或個股在 `gated` 時，已結算紀錄若顯示 label，回應的 `disclosure_fragment_ids` 要含 PV-45 固定句，在同一區塊呈現；

  改為見 §D-11 第 4 點第 11 項 (e)。
- r3（2026-10-17，tech-architect A-63）：單列狀態片段（第 1～12 點）、`stats_json` 的序號欄位、FL-58 (e)～(f) 為新增，無被取代原文；見 §D-11 第 4 點第 11 項、§D-11 第 2 點、§對實作的約束 FL-58。

**A-64（D-11.4 第 11 點 (g)、FL-59）**
- r3（2026-10-17，tech-architect A-64；方向：收緊）：新增，無被取代原文；見 §D-11 第 4 點第 11 項 (g)、FL-59。

**A-65（D-11.4 第 11 點 (h)、FL-52b (9e)、FL-59）**
- r3（2026-10-17，tech-architect A-65；S-4；增補 RC″-1 (2)、T-4；RC‴-4；方向：收緊）：新增 (h)，含結算日期的語意（T-4）與翻案伴隨句（RC‴-4，取代增補 T-5 的條文），無被取代原文；見 §D-11 第 4 點第 11 項 (h)。
- r3（2026-10-17，tech-architect A-65，R3-7 (4)）：FL-52b (9e) 原文——
  > - (9e) **結算後的形式**：兩個已結算格，label 只出現在 `settled_record` 內，同一物件帶 `settlement_date` 與結算結果，頂層沒有 `label`。另加一格作廢 outcome：不出現 label（A-36 第 4 點）。

  改為見 §對實作的約束 FL-52b (9e)。

**A-66（D-11.4 第 9 點第 1 點、第 2a 點、FL-60）**
- r3（2026-10-17，tech-architect A-66；R3-8；方向：收緊）：D-11.4 第 9 點第 1 點 `first_layer` 原文——
  > - `first_layer`：首層（市場總覽、「最需要處理」清單）；

  改為見 §D-11 第 4 點第 9 項第 1 點。
- r3（2026-10-17，tech-architect A-66；A-85；R3-8 的 2a 新文取代 A-66 對 2a 的改寫）：D-11.4 第 9 點第 2a 點原文——
  > - 2a. **天氣圖示**：`OutlookWeather` 是展望 label 的一種呈現形式，不是獨立的顯示面（映射在後端，PRD L561、L590），依它所在端點的 `SERVES` 判定。
  >   - 市場總覽的天氣屬於 `first_layer`；
  >   - 不在 D-20 列舉內的頁面，在列舉修訂並送審之前，不得渲染展望 label 或天氣（附件 B'-2）。

  改為見 §D-11 第 4 點第 9 項第 2a 點（「PRD L561、L590」依 A-85 改為「PRD AV-13 與 NP-A1／NP-A2 列」）。

**A-67（D-11.4 第 9 點第 2、5 點、FL-54 (d)）**
- r3（2026-10-17，tech-architect A-67；方向：收緊）：D-11.4 第 9 點第 2 點的三個子項原文——
  > - 大盤：五個顯示面在 `shown` 時都許可；
  > - 族群：五個顯示面在 `shown` 時都許可（150 閘門已經由 `gated` 處理）；
  > - 個股：`symbol_detail` 在 `shown` 時許可；`first_layer`、`alert`、`export` 需要狀態為 `better_than_baseline`（`alert`、`export` 這兩格待確認，見附件 B-3）；

  改為見 §D-11 第 4 點第 9 項第 2 點。
- r3（2026-10-17，tech-architect A-67）：D-11.4 第 9 點第 5 點原文——
  > - 5. 個股展望在「優於基準」之前，對政策表一律是 `surface_not_permitted`。這是 D-20 ③ 由第 2 點推出的結果，不是另立的規則。

  改為見 §D-11 第 4 點第 9 項第 5 點。

**A-68（D-11.4 第 9 點第 4 點）**
- r3（2026-10-17，tech-architect A-68；r3′ R3-9；方向：放寬（展望可用性；只在優於基準且該格送審開放後才可能生效）＋收緊（輸出面）；v1 實效不變）：D-11.4 第 9 點第 4 點原文——
  > - `PLAN_OUTPUT_SURFACES` 登記在政策表 v0 與本節。初版 {first_layer, symbol_detail, alert, export, api}，適用 `position_action`、`reasons`、`pending_triggers`；待 PM 依 Phase 4 版面確認，之後要改須送審並升 `policy_version`。

  改為見 §D-11 第 4 點第 9 項第 4 點。

**A-69（FL-54 (h)、FL-43）**
- r3（2026-10-17，tech-architect A-69；方向：收緊）：FL-54 新增 (h)；FL-43 對提醒 payload 的斷言保留。無被取代原文；見 §對實作的約束 FL-54、FL-43。

**A-70（D-11.4 第 7 點 None 規則、FL-43）**
- r3（2026-10-17，tech-architect A-70；方向：收緊）：新增，無被取代原文；見 §D-11 第 4 點第 7 項、FL-43。

**A-71（D-1、D-7.8 第 8 點、D-11.4 第 11 點：紀錄清單拆成三個端點）**
- r3（2026-10-17，tech-architect A-71；方向：補定義（兩面；依風控顯示面確認 (d)））：D-1 模組表 `app/api/forecast.py` 一列原文——
  > | `app/api/forecast.py` | `GET /api/forecast/status`、`GET /api/forecast/records` |

  改為見 §D-1。
- r3（2026-10-17，tech-architect A-71）：D-7.8 第 8 點原文——
  > - `GET /api/forecast/records`（帶 `trigger=on_demand`）。

  改為見 §D-7 第 8 點。D-7.8 第 8 點與 FL-52b (9) 所稱「紀錄清單」，依 A-71 改指 symbol 端點；本 ADR 以 D-7.8 第 8 點內的一行定義註記處理，未逐處改字。
- r3（2026-10-17，tech-architect A-71）：D-11.4 第 11 點小標原文——
  > - 11. **`GET /api/forecast/records` 同樣經過本閘門**：

  改為見 §D-11 第 4 點第 11 項（小標改為「紀錄清單端點同樣經過本閘門」）。

**A-72（D-14 G-7、FL-38）**
- r3（2026-10-17，tech-architect A-72；r3′ R3-10；r3″ RC′-6；方向：收緊）：D-14 原文（兩處）——
  > - G-7 是 on-demand 的說明，不是排程紀錄的閘門。
  >
  > - G-7：on-demand 不受 G-6 以外的限制，但同樣不計入主統計。

  改為見 §D-14（G-7 新文與寫入被閘門拒絕時的處理）。FL-38 補充為新增，見 §對實作的約束 FL-38。

**A-73（D-7.8 第 8 點：on-demand 去重、FL-52b (10)）**
- r3（2026-10-17，tech-architect A-73；方向：補定義（兩面））：新增，無被取代原文；見 §D-7 第 8 點。

**A-74（FL-16、`ENDPOINT_SURFACES` 的 kind）**
- r3（2026-10-17，tech-architect A-74；方向：收緊）：FL-16 原文——
  > - **FL-16**：`late=1` 與 on-demand 的紀錄，永遠不會出現在「當日展望」的 API 回應中。

  改為見 §對實作的約束 FL-16。FL-54 (g) 隨之擴充。

**A-75（D-7.3 決策日 T）**
- r3（2026-10-17，tech-architect A-75；r3′ R3-11 (2)；r3″ RC′-5；增補 S″-1；方向：收緊）：D-7.3 原文——
  > 3. **決策日 T**：市場 DB 中最新一個有 ok bars run 的 session，而且大盤 T 日 bar 已經存在。

  改為見 §D-7 第 3 點。FL-61 為新增。

**A-76（D-4 第 8 點、FL-62）**
- r3（2026-10-17，tech-architect A-76；方向：收緊）：新增，無被取代原文；見 §D-4 第 8 點、FL-62。

**A-77（D-8.1 觀察日、FL-19）**
- r3（2026-10-17，tech-architect A-77；r3′ R3-11 (1)、(3)；r3″ RC′-4、RC′-5；增補 RC″-5、N-1；RC‴-2、RC‴-3；方向：收緊（第 5 項相對事先宣告為補定義（兩面），風控 2026-10-17 單項確認））：D-8.1 原文——
  > 1. **觀察日**：市場 DB 有 ok bars 的 session，聯集大盤實際有 bar 的日期。不用週一至週五推定。

  改為見 §D-8 第 1 點（第 1～12 項）。第 12 項為 D_v 前待決（N-1）。FL-19 的 fixture 為新增，見 §對實作的約束 FL-19。

**A-78（D-4.1 定案下限、FL-63）**
- r3（2026-10-17，tech-architect A-78；方向：收緊）：D-4.1 原文——
  > - 可見性規則與 `panel._visible` 位元相同：`session_date ≤ T`、`recorded_at ≤ cutoff(T)`、只取 ok run、依來源優先序〔轉引 R-107：`panel.py:886-922`〕。

  改為見 §D-4 第 1 點。FL-63 為新增。

**A-79（檔頭、與既有 ADR 的關係、Consequences、待決事項、修訂紀錄）**
- r3（2026-10-17，tech-architect A-79；r3′；r3″ RC′-8、RC′-9；增補 RC″-4；方向：不變）：Consequences「D-20 的兩面後果」第一子點原文——
  > - 個股展望在「優於基準」之前，對政策表都是 `surface_not_permitted`，所以 `consider`、`add_conditional` 會長期無法成立；

  改為見 §Consequences（句首依 A-79 改為「個股展望在 v1 期間不論驗證狀態」，句尾依 RC′-8 加註）。
- r3（2026-10-17，tech-architect A-79）：檔頭、與既有 ADR 的關係、Consequences 新增各點、CEO 說明（RC′-9；第 8 點為 RC″-4 版）、待決事項補入，皆為新增，無被取代原文。
- 提案原文只列出 r3 新增四點的題目（D_v 前字面增加；交易時段開機的影響；`inputs_not_ready` 的影響；紀錄清單拆成三個端點）與 r3′ 新增四點的題目（其中第三點由 RC′-8 整點改寫），內文取自同一批提案與風控審查中的相關敘述，見 §Consequences。

**A-80（D-12「逐檢查點判定」第 1、2 點）**
- r3（2026-10-17，tech-architect A-80；方向：不變）：第 1 點補上 `fail_normal(c)`、`fail_w(c)` 的定義，並補第 2 點的指引行，無被取代原文；見 §D-12。

**A-81（D-12 共同部分 (v)）**
- r3（2026-10-17，tech-architect A-81；方向：不變）：D-12 共同部分 (v) 原文——
  > - (v) 作廢率 >5% 時，判定取一般情境與 W 之中比較差的那個（底線 3）。

  改為見 §D-12 共同部分 (v)。

**A-82（D-14：G-2 機器部分）**
- r3（2026-10-17，tech-architect A-82；方向：不變）：新增「G-2 的機器部分」，無被取代原文；見 §D-14。

**A-83（「七道閘門」殘留敘述）**
- r3（2026-10-17，tech-architect A-83；方向：不變）：原文（四處）——
  > 6. **寫入閘門**：ADR-0027 核可、C-8 定案、定義凍結、08:30 查證、ADR-0026 的守門與備份全部完成之前，不得寫入任何前瞻紀錄。
  >
  > - 第一筆前瞻紀錄被七道閘門延後。
  >
  > - 第一筆前瞻紀錄要等七道閘門；08:30 若一直查證不到，記錄就一直不能開始。
  >
  > 5. 知悉 D-14 的七道閘門，以及 C-7 的解釋性註記。

  依序改為見 §評估摘要 採用第 6 點、§評估摘要 最大代價、§Consequences 代價與壞處第一點、§待決事項 CEO 第 5 點。待決「風控」段的「七條底線」指 F-2 的風控底線 1～7，不改。

**A-84（ADR-0028 CS-12）**
- r3（2026-10-17，tech-architect A-84；方向：不變）：屬 ADR-0028，已於 commit 1d69acd 落地；本 ADR 不動。

**A-85（外部參照自足化）**
- r3（2026-10-17，tech-architect A-85；r3′ S-1、S-2、S-3；方向：不變）：D-4 第 7 點「狀態」一句原文——
  > - **狀態**：σ_d 定稿條文仍然沒有生效，要依事先宣告 §2.1 的順序經過 data-engineer、qa（含 Codex）、風控，最後由 CEO 在 C-4 凍結。B4「該股所屬族群」要用哪個時點判定，見附件 B-7。

  改為見 §D-4 第 7 點（S-2：引用事先宣告 v0.10 V10-05）。
- r3（2026-10-17，tech-architect A-85）：D-7.8 第 8 點第 1 子點 (b) 原文——
  > - **API 回應本體不得含任何帶方向的欄位。** 這是對 API 本身的要求（API 就是顯示面，風控附件 B 確認 B-3），不只是前端不渲染。

  改為見 §D-7 第 8 點（改寫風控確認檔路徑）。
- r3（2026-10-17，tech-architect A-85；S-3）：D-7.8 第 8 點第 2 子點原文——
  > - (b) 的狀態片段，意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」。**這句只是語意，不是已核可的字面。**
  > - 逐字字面由 creative-lead 起草（風控附件 B 確認 B-8 第 6 項；目前是第六批 R6-05 的 OS-a 候選，正在風控逐字審），風控核可後才可使用。

  改為見 §D-7 第 8 點第 2 子點（逐字字面為 LM-106；守門 R1、R2 見 D-11.4 第 11 點）。
- r3（2026-10-17，tech-architect A-85；S-1）：D-9.3 原文——
  > - （r2，A-32）**套用的序列**：個股 claim 該股的序列，以及族群成員的序列。指數序列見附件 B-6。

  改為見 §D-9 第 3 點（S-1：引用事先宣告 v0.10 V10-01）。
- r3（2026-10-17，tech-architect A-85）：待決事項原文（兩處）——
  > - **creative-lead**（依風控附件 B 確認的 B-8 完整清單）：
  >
  > - 未列舉頁面的歸屬（附件 B'-2）。

  改為見 §待決事項（寫出風控 r2 確認檔的路徑；PM 項改為「已決：D-11.4 第 9 點第 1 點（A-66）」）。
- r3（2026-10-17，tech-architect A-56）：待決事項 creative-lead 段原文（「恢復前這條條件無法成立」改為引用 LM-103）——
  > - `pending_triggers` 的「恢復前這條條件無法成立」片段；

  改為見 §待決事項 creative-lead 段。
- r3（2026-10-17，tech-architect A-85）：「附件 B-3」「附件 B'-2」由 A-67、A-66 取代，其餘在 D-11.4 第 6 點的「NS-a 刪除」、第 11 點 (f) 的「改名」兩處見 A-56、A-60。本修訂紀錄中說明「附件 B-x 指提案檔編號」的那一行保留。

**A-86（編號整理）**
- r3（2026-10-17，tech-architect A-86；方向：不變）：FL-52b 六種情形原文（未編號）——
  > - 沒有 run；
  > - 有 run，但快照不含這檔；
  > - 快照含這檔，但沒有紀錄；
  > - 只有 on-demand 紀錄；
  > - `late=1`；
  > - `late=0`。

  改為編號 (1)～(6)，性質測試不編號。
- r3（2026-10-17，tech-architect A-86）：FL-53 前兩點原文——
  > - 暫停期間碰到檢查點，觸發 F-2 → 寫入 `withdraw_reason`，恢復後顯示 `withdrawn_f2`；
  > - 先下架、後暫停、再恢復 → 仍然是 `withdrawn_f2`。

  改為編號 (a)、(b)。表格以外的 `|S_T|` 不必跳脫：本 ADR 的 D-1 表格內維持跳脫，表格外沒有需要改動的地方。

**D-3（`forecast_outcome` 識別、`forecast_ledger_events`；r3″ 連帶補漏、增補 RC″-2，掛 A-57／A-77）**
- r3″（2026-10-17，tech-architect；方向：不變）：D-3 `forecast_ledger_events` 原文——
  > - `forecast_ledger_events(event_id, kind ∈ {db_restored, f3_resume_approved, pit_violation_confirmed}, payload_json, recorded_at)`：`pit_violation_confirmed` 的 payload 帶 `forecast_id` 與重算值（r1，A-8）。

  改為見 §D-3 `forecast_ledger_events`（列舉補為六個值，並加 `event_id INTEGER PRIMARY KEY AUTOINCREMENT`）。
- 增補 RC″-2（2026-10-17，tech-architect）：D-3 `forecast_outcome` 原文——
  > - 識別：`outcome_id`、`forecast_id`；

  改為見 §D-3 `forecast_outcome`。

---

> r3 系列套用疑義裁定（2026-10-17，tech-architect）：依 `work/reviews/2026-10-17-ADR-0027-r3系列套用疑義裁定-tech-architect.md` 第二節逐字改字。下列為被改字取代的、本檔 r3 系列首次套用版的原文（逐字保留），掛在既有 A 號下；方向皆為不變或收緊，沒有放寬。
> 第五個 `status_reason` 值（`index_bar_confirmed_erroneous`）：疑義裁定原本不改、另案送風控；風控 2026-10-17 疑義裁定回送確認（`work/reviews/2026-10-17-ADR-0027-疑義裁定回送四項確認-風控.md`，commit 807be08）Q-1 要求排進同一批，已於後續一輪套用，見本段最後的「風控疑義裁定回送確認」。

**A-79（Consequences 八點）**
- 裁定第 1 項：L1141–L1148 整段取代；原文——
  > - （r3，A-79）**D_v 前要核可的字面增加**：A-55 (e) 要求「優於基準」狀態的伴隨揭露先核可，否則 D_v 不能開始，即使優於基準預期是好幾年後的事。A-62、A-63、A-65 的片段（清單狀態片段、「已結算＋實際結果」片段、作廢列的呈現）也一樣卡在 D_v 前。
  > - （r3，A-79）**交易時段開機的影響**：主機如果在交易日收盤定案前開機，市場資料可能只抓到盤中值；當天如果沒有再抓，那一天會照實記成缺日，不會補造。之後約 60 個交易日內，部分紀錄可能判成證據不足或作廢，作廢的會算進最壞情境（A-78）。
  > - （r3，A-79）**`inputs_not_ready` 的影響**：大盤資料必須是收盤定案後才抓到的才能用。重抓失敗的日子照實記成缺日，不會用暫定值頂替，也不會改用前一天的資料（A-75）。
  > - （r3，A-79）**紀錄清單拆成三個端點**：依 scope 拆成 market、sectors、symbols 三個端點，每個端點只回傳自己的 scope，不設總端點（A-71，見 D-11.4 第 11 點）。
  > - （r3′，A-79）正式記錄前，臨時查詢不給方向，也不會「算了不記帳」：寫入被閘門拒絕時，POST 不計算、不回傳任何 label 或方向衍生欄位，回應用封閉 schema `OnDemandGateClosedView`（A-72，見 D-14）。
  > - （r3′，A-79）族群可能重新隱藏方向：不設遲滯，每次回應都依當下的 `pa9_holds` 判定；重新變成 PA-9 成立後，這些列改用 A-63 第 4 項，不得繼續寫「結算後列示」（A-63 第 9 點）。
  > - （r3′，A-79；r3″ RC′-8 整點改寫）個股與族群在 v1 沒有回放計畫（事先宣告 §4.7），所以常駐 `gated`，任何畫面都不顯示其方向；A-63 第 5 項要在 D_v 前核可。
  > - （r3′，A-79）觀察日可能因為 X2 回溯縮小：觀察日集合可能因為後來的 X2 確認而回溯縮小。已寫入的 snapshot 不改；之後的 snapshot（含 F-3 逾時率的 60 日窗）用新集合。結算端依事先宣告 §6.4 supersede（A-77 第 11 項）。

  改為見 §Consequences。第 7 行的 RC′-8 逐字文保留不動。CEO 說明第 4、5 點的「照實記成缺日」是風控 r3 審查的逐字白話文，不動。

**A-75（D-7.3 `is_final_bar`、FL-61）**
- 裁定第 2 項（連帶收緊，回送風控）：D-7.3 `is_final_bar` 第一子點原文——
  > - `final_after(TW, T) ≤ min(as_of, fetched_at) ≤ now`（`final_after` 見 ADR-0028 CS-17）；
- 裁定第 2 項：FL-61 原文——
  > - **FL-61**（r3 新，A-75）：(a)～(e)，包含「`as_of` 14:59:58、`fetched_at` 15:00:01」的 fixture，以及「不退回前一 session」。

  改為見 §D-7 第 3 點、§對實作的約束 FL-61。

**A-63（FL-58 (e1)(e2)、第 11 點登記子點、FL-52 T-2 子點、FL-19 (c)②③、標記）**
- 裁定第 4 項：FL-58 (e1)、(e2) 原文——
  > - (e1) 族群 `suspended_f3`、n<150、已下架或未下架 → 選 (c)、第 4 項，不得選第 2 項；
  > - (e2) 族群先 `shown`（n≥150），列已經顯示過 LM-105；PIT 違規列移出 E 後 n<150 → 同一列改選第 4 項，結算後的列也不出現 label；
- 裁定第 4 項：A-63 第 11 點登記子點原文——
  > - LM-12、LM-34、LM-73、LM-98 登記為 `covers = {forward_n_below_min}`，分別放在 `outlook_block`、`sector_cell`／`sector_detail`、`plan_reason`。
- 裁定第 4 項：FL-52 T-2 子點原文——
  > - （增補 T-2；依第八批 LM-129 ②）族群 `forward_n_below_min` 的原子片段在 `e_changed_since` 為真時選不到 LM-129。R-6 片段核可之前，這種情形 fail-closed。
- 裁定第 12 項：A-63 第 12 點 (2) 與 FL-58 時鐘無關格原文——
  > - (2) LM-118、LM-119 的列，在 G_eff 非空時，後面一律接 LM-120〔超出字面：風控只要求「沒有 claim 層的頁面」才接；端點不收頁面參數，前端也不得另寫判定，所以改成一律附〕。
  > - 時鐘無關格〔超出字面，收緊〕：注入倒退的 store 時鐘，判定結果和時鐘正常時逐位相同。
- 裁定第 3 項（收緊）：FL-19 (c)②、(c)③ 句尾各加一個子例，無被取代原文。風控回送確認 suggested，coordinator 定案採用：兩個子例為必要子例（CEO 可推翻）。

  改為見 §對實作的約束 FL-58、FL-52、FL-19 與 §D-11 第 4 點第 11 項。`outlook_block` 的選用優先序等未定事項見 §待決事項 tech-architect；定案之前 FL-52 在該 slot 的 {`forward_n_below_min`} 格失敗（fail-closed，只擋 D_v）。

**A-68（D-11.4 第 9 點第 4 點）**
- 裁定第 7 項：原文片段——
  > 待 PM 依 Phase 4 版面確認，之後要改須送審並升 `policy_version`。

  改為「初版經 PM 確認（`work/reviews/2026-10-17-PLAN_OUTPUT_SURFACES與頁面歸屬-product-manager.md`），之後要改須送審並升 `policy_version`。」

**A-66（D-11.4 第 9 點 2a）**
- 裁定第 8 項：原文——
  > - 不在本點清單內的頁面或元件，在清單修訂並送審之前，不得渲染展望 label、天氣、方向色，也不得渲染 A-68 的適用欄位。

  改為見 §D-11 第 4 點第 9 項第 2a 點（「第 1 點所列歸屬（`first_layer` 六項、`symbol_detail`）以外的頁面或元件」）。

**A-71（D-7.8 第 8 點「紀錄清單」註記）**
- 裁定第 5 項：原文——
  > - （r3，A-71）本點以下與 FL-52b (9) 所稱「紀錄清單」，指 symbol 端點（`/symbols/{symbol}`）。

  改為見 §D-7 第 8 點。

**A-85 與 A-30（過期敘述）**
- 裁定第 15 項：FL-52 開頭、FL-52 (d) 末句原文——
  > - **FL-52**（r2 新，A-30；r2'' 改 (d)）：原因與片段的對照表允許附守門的項目：`REASON_FRAGMENTS: Mapping[reason, tuple[GuardedFragment, ...]]`。測試四點：
  > - (d) …（A-36 第 2 點）。風控核可它的逐字字面之前，本項失敗。
- 裁定第 15 項：D-7.8 第 2 子點原文——
  > - **核可之前，FL-52 (d) 失敗**，依 FL-45 (c) 的效力鏈：G-6 不成立 → 不得寫入排程紀錄 → D_v 被擋住。on-demand 依 D-14 的 G-7 同樣受 G-6 約束，也不得寫入。
- 裁定第 15 項：待決事項 quant v0.9 末項原文——
  > - B-6、B-7（同 r2）。
- 裁定第 15 項：r2 待決清單各項行尾加註「〔已決：…〕」、D-11.4 (f) 句尾加澄清句，原文保留在原處，無被取代原文。

**風控疑義裁定回送確認（2026-10-17，風控，`work/reviews/2026-10-17-ADR-0027-疑義裁定回送四項確認-風控.md`，commit 807be08；以下含本批新增、尚未 commit 的行）**
- Q-1（A-62 R2 第 4 點引用的第五值）：D-9.3 加 `index_bar_confirmed_erroneous` 全文，用風控版本，取代 tech-architect 的版本；FL-22 原文——
  > - **FL-22**：`status_reason` 屬於 D-9.3 的四值封閉列舉，而且與 `status` 的對應固定（表格驅動測試）。

  改為「五值」並加三格，見 §D-9 第 3 點、§FL-22。D-9.3 為新增，無 9ba01d6 的被取代原文。
- Q-2（A-30／FL-52 (d)）：疑義裁定首次套用版的末句——
  > 「期間已開始」片段為 LM-106。A-62 R2 第 6 點所列片段全部核可之前，本項仍失敗。

  改為泛指版本，見 §FL-52 (d)。
- Q-3（A-79 CEO 說明第 4、5 點）：原文——
  > 4. 主機如果在交易日收盤定案前開機，市場資料可能只抓到盤中值；當天如果沒有再抓，那一天會照實記成缺日，不會補造。
  > 5. 重抓失敗的日子照實記成缺日，不會用暫定值頂替，也不會改用前一天的資料。

  （各點其餘文字不變，此處只引被改的句子）改為見 §Consequences CEO 說明第 4、5 點。待決事項 tech-architect 加一條（平日、不在 (i) 也不在 (ii) 的日期），無被取代原文。
- 回送第 3 項條件句：A-63 第 11 點 fail-closed 句之後加「不得以 skip、xfail、placeholder 或暫定字面讓測試通過」，無被取代原文。
- suggested（coordinator 定案採用，CEO 可推翻）：
  - r2 待決清單「已結算＋實際結果」項行尾加註「〔已決：LM-131（第八批）〕」，無被取代原文。
  - A-68 第 9 點第 4 點：首次套用版「初版經 PM 確認（`work/reviews/2026-10-17-PLAN_OUTPUT_SURFACES與頁面歸屬-product-manager.md`），之後要改須送審並升 `policy_version`。」改為「初版經 PM 建議（同路徑）並經風控顯示面確認（V10-12），之後要改須送審並升 `policy_version`。」
- coordinator 依同批機械核對補登（2026-10-18）：待決事項「D_v 前置」行加 Q-3 一句，對應風控疑義裁定回送確認第四節「D_v 前置清單：加 Q-3 待決」；原句「- **D_v 前置**：N-1 未核可不得進入 D_v（RC‴-3）；R-5、R-7 未核可不得進入 D_v（RC‴-4）。」為本批新增、尚未 commit 的行，逐字保留於此。方向：收緊。

---

> 第九、十批衍生待決項套用（2026-10-18，tech-writer）。與事先宣告 v0.12 同批：只 add 這兩個檔案，任何一份都不得單獨 commit。檔頭狀態維持 proposed；沒有新增 A 號（也沒有 A-87 以後的條號）。
> 套用來源與優先序（來源檔都在 `work/reviews/`；S1～S9 沿用 tech-architect 整合清單 6-1 的代號）。衝突時編號小的優先：
> 1. 風控 2026-10-18 C9-7、Q-3、CS-17 提案確認（commit b55e41f）：`2026-10-18-ADR-0027-C9-7與Q-3及CS-17提案確認-風控.md`。取用：C7-1～C7-8（C9-7 甲案）、Q3-1～Q3-7（Q-3 A 案）、第二節第 3 項「CS-17 的 ADR-0027 那一側」、第二節第 4 項 A-77 的方向標註。
> 2. 風控 2026-10-18 事先宣告 v0.12 草稿審查（commit 97fbe50）：`2026-10-18-事先宣告v0.12草稿審查-風控.md`。取用：第二節 Q12-2（R10-7 四項觸發、FL-49 一格）、R10-5 括號句（改為引用 V12-12）、Q12-4 的 R10-3 改寫（取代整合清單較早的 R10-3 寫法）、C9-9 對 A-34 的一句，以及第四節「tech-writer（下一批 ADR-0027）」的 L974 與 N-1 標已核可。
> 3. tech-architect 整合清單（commit f294cc9，S9）：`2026-10-18-ADR-0027-下一批整合與C9-7及Q-3提案-tech-architect.md`。取用：第 1、2、5 項；第 3 項甲案與第 4 項 A 案中，未被上列兩份改寫或取代的部分；第 6 項整合清單（6-1 來源、6-2 優先序、6-3 selector 簽章、6-4 共 38 處、6-5 補登與不一致、6-6 修訂紀錄與方向）。
>    - 整合清單內部的優先序（6-2）：S7 > S6 > S4 > S3 > S2 > S1；同一份風控檔內，指名「取代」的條文優先於被取代的條文；風控逐字條文（「給 tech-writer 照寫」）優先於 TA 條文；S9 是 S6～S8 的落地條文，地位等同各自的來源，和風控逐字文衝突時以風控逐字文為準。
> 4. S1～S8 原始檔，只在需要逐字取文時讀：
>    - S1：`2026-10-17-ADR-0027-第九批TA待決項提案-tech-architect.md`（第二節，提案 1～5）；
>    - S2：`2026-10-17-ADR-0027-第九批TA提案確認-風控.md`（第二節 C9-1～C9-10；S9-1、S9-2、S9-4；S9-3 併入 Q-3）；
>    - S3：`2026-10-17-ADR-0027-R7對照表與更正鏈確認-tech-architect.md`（第二節，提案 1～4）；
>    - S4：`2026-10-17-ADR-0027-R7對照表與更正鏈提案確認-風控.md`（第二節 R10-1～R10-7）；
>    - S5：`2026-10-17-ADR-0027與v0.11同批最終裁定-風控.md`（第二節第 4 項 L974、第 1 項 suggested L1366）；
>    - S6：`2026-10-17-新定位第十一批字面逐字審-LM153-風控.md`（第三節 LM-153 條件 ①～⑭；第五節）；
>    - S7：`2026-10-17-新定位第十二批字面逐字審-LM154-風控.md`（第三節 LM-154 條件 ①～⑫；第五節）；
>    - S8：`2026-10-17-ADR-0027-疑義裁定回送四項確認-風控.md`（第二節回送第 1 項 suggested、第 4 項 suggested）。
> 仍有疑義時，取較嚴（fail-closed）的一方，並回報 coordinator，不自行折衷。
> 被改寫或取代的原文是 commit fd87063 的 ADR 原文，逐字保留於下，掛在各自的 A 號底下；「新增」類條目沒有被取代的原文。引用區塊內的文字即 fd87063 的原文。
> 來源條文引用事先宣告的行號（L1083、L505-506、L507、L514、L687、L1220、L1221、L1174、L1175-1177、L1180、L1185），是來源撰寫時的事先宣告 v0.11 行號，本 ADR 已在正文加註 v0.11；v0.12 的行號會因插入內容而位移。
> 累計方向統計：A-65 由「收緊」改列「含有條件放寬的兩面」（A-65 含 R-7 提案 3 的診斷欄位更正例外，屬揭露面放寬，風控 2026-10-17 核可、CEO 知悉；風控 2026-10-18 C9-7 與 Q-3 提案確認第二節第 4 項確認改類），沒有任何其他一條換類別：
>
> | 方向 | 條數 | 條號 |
> |---|---|---|
> | 收緊 | 18 | A-54～A-57、A-60、A-61、A-63、A-64、A-66、A-67、A-69、A-70、A-72、A-74～A-78 |
> | 補定義（兩面） | 2 | A-71、A-73 |
> | 不變 | 9 | A-59、A-79～A-86 |
> | 不變＋收緊 | 1 | A-58 |
> | 含有條件放寬的兩面 | 3 | A-62「收緊＋有條件放寬（R2，依風控 r3 審查 C-3；片段核可前 fail-closed）」；A-65（R-7 提案 3 的診斷欄位更正例外）；A-68（字面與事先宣告 v0.10 V10-12 逐字相同） |
>
> 合計 33，寫成「18／2／9／1／3」。
> A-77 的方向標註更新為「收緊（第 3 項甲案、第 5 項、第 10 項相對事先宣告為補定義（兩面），風控 2026-10-17 單項確認、2026-10-18 C9-7 與 Q-3 提案確認）」，不換類別。它取代 r3 系列段落中的標註「收緊（第 5 項相對事先宣告為補定義（兩面），風控 2026-10-17 單項確認）」；該段落的原文不改動。
> 本批各 A 號的方向（整合清單 6-6）：不變——A-23、A-59、A-78、A-79；收緊——A-57、A-63、A-75、A-77；收緊＋有條件放寬——A-65（R-7 提案 3，風控核可、CEO 知悉）。

**A-23（D-12「逐檢查點判定」第 4 點）**
- 本批（2026-10-18，tech-writer；S5 第 4 項；風控 v0.12 審查第四節 tech-writer；方向：不變）：第二子項原文——
  > - LM-87「其中作廢比例超過 5% 的檢查點，依最不利情境計算」由第 1 點的逐檢查點規則保證屬實，滿足 LM-87 的核可條件，不必重送。

  改為字面清單 L3442 的 LM-87 全文，見 §D-12。

**A-34（D-1 模組表）**
- 本批（2026-10-18，tech-writer；風控 v0.12 審查第二節 6、第四節 tech-writer，C9-9 的 ADR 端；tech-architect 疑義裁定第 26 項與附帶 A；方向：不變（引用）＋收緊（附帶 A 的 import 限制））：`app/outlook/volatility.py`、`app/outlook/inputs.py` 兩列各加一句，無被取代原文；見 §D-1。A-34 是 r2 的條號，不影響 r3 的累計統計。第一輪套用版（未 commit）的句子見本段最後的「第二輪取代」。

**A-57（D-11.4 第 12 點 (iv)、`GATE_FIXED`、`REPLAY_APPROVAL_SCOPES`、FL-53 (f)）**
- 本批（2026-10-18，S9 第 3 項甲案與第 5 項 (c)；風控 2026-10-18 C7-1、C7-2、C7-3、C7-5；方向：收緊）：新增查詢時閘門 `validation_refresh_pending`（`GATE_FIXED` 的大盤、個股列），以及 `REPLAY_APPROVAL_SCOPES`，無被取代原文；見 §D-11 第 4 點第 12 項 (iv)。
- 本批（2026-10-18，S5 第 1 項 suggested；整合清單 6-4 #32；方向：不變）：FL-53 (f) 末項原文——
  > - 在沒有片段的情況下啟用 `shadow_run_pending` → loader 拒絕（增補 T-1）。

  改為見 §對實作的約束 FL-53 (f)（句尾加「與 FL-52 同一個 `gate_coverage_gaps`」）。

**A-59（D-11.1、FL-49）**
- 本批（2026-10-18，S3 提案 4；方向：不變（對齊））：D-11.1 新增「主統計就是鏈尾」，FL-49 加格，無被取代原文；見 §D-11 第 1 點、§對實作的約束 FL-49。

**A-63（D-11.4 第 11 項 (c) RC′-2 子點、第 11 項「多個 `gate` 值」登記與 selector、FL-52、FL-58、FL-59；風控 2026-10-18 C7-1～C7-8）**
- 本批（2026-10-18，S1 提案 1、2、4；S2 C9-1～C9-6；S6 LM-153 條件 ⑨⑪⑫⑭；S9 第 1 項、6-3、6-5 第 1、5 點；風控 2026-10-18 C7-1～C7-8；方向：收緊）：D-11.4 第 11 點第 11 項「多個 `gate` 值同時成立時的選用規則」第一個子點原文——
  > - `display.py` 定義 `GATE_STATUS_FRAGMENTS: Mapping[(scope_kind, slot), Mapping[frozenset[gate], tuple[fragment_id, ...]]]`，其中 `slot ∈ {record_list, record_list_header, plan_reason, outlook_block, sector_cell, sector_detail}`（風控第八批 T-2）。每個片段登記 `covers: frozenset[gate]`。

  改為見 §D-11 第 4 點第 11 項（`GATE_FRAGMENT_REGISTRY` 是唯一的登記，選用一律經 selector；舊型別無法表達 `display_state` 等條件）。
- 本批（同上）：同一子點的 selector 簽章與登記原文（五行）——
  > - 上述位置的 gate 片段 ID，只能由 `select_gate_fragments(scope_kind, slot, G_eff, e_changed_since)` 產生（route 列舉＋AST 測試，比照 FL-60 (d)）。
  > - LM-12、LM-98 登記為 `covers = {forward_n_below_min}`，分別放在 `outlook_block`、`plan_reason`。
  > - `sector_cell`、`sector_detail` 登記 LM-127（k＝1，`covers` 等於所代入原子片段的 `covers`）與 LM-126（k≥2）。不登記 LM-34、LM-73：兩句已由風控撤回（`work/reviews/2026-10-17-新定位第九批字面逐字審最終版-納入quant回答-風控.md` R9-04）。
  > - `outlook_block` 中 LM-12 與 LM-120 的選用優先序待定（見待決事項 tech-architect）。定案之前，FL-52 在該 slot 的 {`forward_n_below_min`} 格失敗（fail-closed）。
  > - 這一格的失敗不得以 skip、xfail、placeholder 或暫定字面讓測試通過（比照 D-7.8 第 2 點）。第九批提案 1 的 commit 之前，不得合併任何實作 `outlook_block` gate 片段選用的程式。

  改為見 §D-11 第 4 點第 11 項（selector 簽章加 `display_state`、`validation_status`、`n_masked`；`GATE_FRAGMENT_REGISTRY` 取代前四行；最後一行只保留「FL-52 任一格失敗，不得以 skip、xfail、placeholder 或暫定字面讓測試通過」一句）。
  - LM-34、LM-73 撤回（風控第九批 R9-04）：LM-34、LM-73 不得出現在登記、常數、測試或 golden。FL-52 因此有一格斷言登記內沒有這兩句（見 §對實作的約束 FL-52 斷言 (6)）。
- 本批（同上）：FL-52 的 T-2 子點原文——
  > - （增補 T-2；第八批 LM-129 ②，第九批 LM-144）族群 `forward_n_below_min` 的原子片段，在 `e_changed_since` 為真、或該族群 claim 沒有任何 daily snapshot 時，選不到 LM-129，改選 LM-144。

  改為見 §對實作的約束 FL-52（FL-52 擴充：斷言 (1)～(9)）。
- 本批（同上）：新增 `n_disclosure_masked(claim, snapshot)`、徽章資料來源、`ValidationBadgeMasked` 與遮蔽時的回應、整個回應的例外、上線限制、大盤與個股適用條件 ⑪ 的讀法、`forecast_record` 更正不改變 E 的四條約束（均掛在 (c) RC′-2 子點）；FL-49、FL-52、FL-58 (e1)(e2) 句尾、FL-59 加格，皆無被取代原文。

**A-65（D-11.4 第 11 項 (g)(h)、D-3 `forecast_outcome`／`forecast_correction_job`、FL-22、FL-52、FL-59；風控 R10-1～R10-7）**
- 本批（2026-10-18，S3 提案 1、2、3、S1 提案 5、S4 R10-1～R10-6、S7 LM-154、S9 第 2 項與 6-5 第 4 點；方向：收緊＋有條件放寬（R-7 提案 3 診斷欄位更正例外，風控核可、CEO 知悉））：(h)「翻案伴隨句」謂詞為真子項原文——
  > - 最新 outcome 的 `status ≠ resolved`（含 `index_bar_confirmed_erroneous` 與其他作廢原因）時，用 R-5；
  > - 最新 outcome 是重算後的 `resolved`（例如 X2 結算後才確認的順延重算、收盤經獨立來源更正後重算）時，用 R-7。
  > - 對應的伴隨句核可之前，這類列 fail-closed，不顯示 label。
  > - R-5、R-7 列入 D_v 前置字面清單，未核可不得進入 D_v。

  改為見 §D-11 第 4 點第 11 項 (h)（R-5＝LM-143；R-7 依 `CORRECTION_REASON_FRAGMENTS` 用 LM-150 或 LM-154；後兩行加註〔已決〕）。
- 本批（同上）：R10-4 的「這句列入 D_v 前置字面清單，核可之前不得進入 D_v」一句，因 LM-154 已於第十二批核可而不再適用（S7：D_v 前置字面清單到此清空）。
- 本批（同上）：D-3 `forecast_outcome` 更正子項、`forecast_correction_job` 與 `forecast_correction_job_end`、`correction_causes` 列舉與對照表、R10-2、R10-3、R10-5、R10-6、診斷欄位更正例外、`band_def` 單位與顯示字串介面，皆無被取代原文；見 §D-3、§D-11 第 4 點第 11 項 (g)(h)。

**A-75（D-7.3 決策日 T、FL-61）**
- 本批（2026-10-18，S9 第 5 項 (a)；整合清單 6-4 #7、#8、#35；方向：收緊）：D-7.3 第 (iii)、(iv) 子項原文（第二行）——
  > - (iii) 或 (iv) 不成立 → 該 session 記 `inputs_not_ready`，不得退回前一個 session。依 A-77 第 5 項，(iii) 在結構上不會成立；保留它是縱深防禦，以測試斷言。

  改為見 §D-7 第 3 點（依 S1 提案 3：(iii) 只在 A-77 第 12 項的情形下成立）。`is_final_bar` 的 `now` 子點與 FL-61 (a) 兩格為新增，無被取代原文。

**A-77（D-8.1 觀察日、FL-19）**
- 本批（2026-10-18，S1 提案 3、S9 第 5 項 (b)；風控 2026-10-18 CS-17 的 ADR-0027 側、Q3-1～Q3-7；方向：見下各項）：第 1 項原文——
  > 1. **定案後 session 集合 (i)**：有 ok bars run、而且該 run 的 `recorded_at ≥ final_after(TW, d)`（ADR-0028 CS-17）的 session d（A-78）。本 ADR 與事先宣告都只引用這一個定義，由 `app/data/session_calendar.py` 的單一函式提供。不得另寫時點比較。

  改為見 §D-8 第 1 點第 1 項（`is_final(TW, d, run.recorded_at)` 為真；加三點，第三點依風控 2026-10-18 CS-17 的 ADR-0027 側）。方向：不變。風控 2026-10-18 的 CS-17 的 ADR-0027 側，把 TA 整合清單 6-4 #9 加在第 1 項的第三點（只准 `is_final` 呼叫 `final_after(`，與第 7 項的 `final_session_evidence` 自相矛盾）改為「`final_after(` 的呼叫位置依 ADR-0028 CS-17（只有 `is_final` 與只寫稽核值的 `final_session_evidence`）；本 ADR 其他位置一律經 `is_final` 判定。」
- 本批（同上）：第 3 項原文——
  > 3. **觀察日 ＝ (i) ∪〔(ii) − X2 確認日〕。** 不用週一至週五推定。

  改為見 §D-8 第 1 點第 3 項（新公式與三個子點）。方向（風控 2026-10-17 第九批 TA 提案確認 C9-8 逐字，掛第 3 項）：方向：收緊（觀察日只減不增、不新增寫入路徑、不自動改變狀態）。定義忠實度兩面：d 若其實是交易日，受影響紀錄的 T+h 會多跨一個實際交易日，偏差留在統計中，直到修訂本項為止；以 §4.2 揭露與 F-8 查證緩解（風控 2026-10-17 第九批 TA 提案確認）。
- 本批（同上）：第 5 項 payload 與句尾原文——
  > - payload：`session_date`、`evidence ∈ {weekend, official_holiday, independent_source_absent}`、`origin ∈ {x2_check, candidate_t, post_x2_final_run}`、受檢 bar 的參照。`independent_source_absent` 只用於 `origin = post_x2_final_run`（見第 12 項）。
  > - 有了這一條，「(ii) 扣除 X2 確認日」就等於「從觀察日移除 X2 確認日」。

  改為見 §D-8 第 1 點第 5 項（`origin` 列舉加 `post_unobserved_backfill`，風控 2026-10-18 Q3-7；句尾依 C9-8）。
- 本批（同上）：第 7 項 `set_i_check` 與第 8 項、第 11 項，只加子點或句尾，無被取代原文；見 §D-8 第 1 點。第 11 項句尾加「觀察日集合不因第 12 項的情形而回復。」
- 本批（同上）：第 10 項原文——
  > 10. 平日既不是觀察日、也不是官方休市日時，記 WARNING。

  改為見 §D-8 第 1 點第 10 項（未觀察平日，Q-3 A 案）。方向（風控 2026-10-18 Q3-5 逐字，掛第 10 項）：方向：收緊（偵測與留痕；觀察日只減不增；不新增更正路徑；不改任何已寫入的紀錄；不自動改變狀態）。定義忠實度兩面：未觀察平日 d 若其實是交易日（例如官方休市日表列為交易日，但大盤與市場 DB 都沒有定案資料），跨越 d 的紀錄 T+h 會多跨一個實際交易日，偏差留在統計中，直到修訂本項為止；以 §4.2 的四項分列揭露與 data-engineer 根因查證緩解（風控 2026-10-18 C9-7 與 Q-3 提案確認）。
- 本批（2026-10-18，S4 R10-7；風控 2026-10-18 v0.12 審查 Q12-2；整合清單 6-4 #17，掛 A-77 連帶第 11 項；方向：收緊）：D-11.2 原文——
  > - 來源資料更正後 supersede 的列，沿用原 seed。

  改為見 §D-11 第 2 點（snapshot 不 supersede；撤銷規則，觸發條件為 `status`、`realized_label`、`hit`、`baseline_hits_json` 四項任一）。FL-49 加兩格。
- 本批（同上）：`E_NEUTRAL_EVENTS` 的集合原文（D-11.4 第 11 項 (c) RC′-2 子點，掛 A-63；Q-3 A 案歸入）——
  > - `forecast_ledger_events.kind` 的每個值都必須歸入 `E_CHANGING_EVENTS`，或歸入 `E_NEUTRAL_EVENTS` ＝ {`f3_resume_approved`, `replay_review_approved`, `session_calendar_conflict`}。新值沒有歸類時測試失敗；判斷不了的一律歸入 `E_CHANGING_EVENTS`。

  改為見 §D-11 第 4 點第 11 項 (c)（集合加 `unobserved_weekday`）。
- 本批（同上）：第 12 項標題、情境、偵測、「觀察日身分怎麼處理」與其後兩點原文——
  > 12. **X2 確認之後，d 才進入 (i)（D_v 前待決；風控 2026-10-17 N-1，比照第 9 項 F-8）**
  > - 情境：`x2_confirmed_non_session` 寫入之後（相關列可能已依第 8 項順延），同一個 d 才出現 `recorded_at ≥ final_after(TW, d)`（ADR-0028 CS-17）的 ok bars run。這時 d 會依第 3 項經 (i) 變回觀察日，和已寫入的事件及 `x2_shift_json` 矛盾。
  > - **偵測**：每日結算排程（事先宣告 §6.3「觸發」）用單一函式，對每一筆 `x2_confirmed_non_session` 檢查 d 是否已經 ∈ D-8.1 (i)。`basis = direct` 和 `verified` 都要檢查。偵測不以該 run 與 X2 事件的先後篩選（涵蓋第 7 項的跨檔窗口）。
  > - **觀察日身分怎麼處理**：由 tech-architect 另案提案，標明方向，送風控審。核可之前不得自動調整任何已寫入的事件或 `x2_shift_json`。D_v 前必須核可。D_v 前沒有前瞻紀錄，所以不擋本批。
  > - 提案核可之前，不得以程式自動解除這個矛盾。
  > - N-1 未核可不得進入 D_v（登記於待決事項）。

  改為見 §D-8 第 1 點第 12 項（甲案：X2 確認優先、固定排除；風控 2026-10-17 第九批 TA 提案確認）。「觀察日身分怎麼處理」整點與其後的「提案核可之前…」一點由甲案取代；「N-1 未核可不得進入 D_v」一點保留並加註〔已決〕（風控 2026-10-18 v0.12 審查第四節 tech-writer：N-1 標已核可（甲案））。
- 本批（同上）：FL-19 (e)① 原文——
  > - (e)① 候選 T 是 X2 確認日：依 A-77 第 5 項，T ∈ (i) 時結構上不可能，屬縱深防禦。測試注入違反前提的狀態，期望 `inputs_not_ready`，而且不退回前一個 session。

  改為見 §對實作的約束 FL-19。FL-19 (h1)～(h6)、(i) 為新增，無被取代原文。

**A-78（D-4.1 定案下限）**
- 本批（2026-10-18，S9 第 5 項 (b)；風控 2026-10-18 CS-17 的 ADR-0027 側；方向：不變）：D-4.1 原文——
  > - **定案下限**（r3，A-78；消費端防護）：對 session s 的 bars，只認 `recorded_at ≥ final_after(TW, s)`（ADR-0028 CS-17）的 ok run 寫入的 bars。適用 D-4.1 PIT 視圖、D-7.3 (i)、D-8.1 (i)、D-9.2 個股與族群成員結算。不改 `pit_snapshot`。

  改為見 §D-4 第 1 點（`recorded_at ≥ final_after(TW, s)` 改為 `is_final(TW, s, recorded_at)` 為真）。

**A-79（Consequences、CEO 說明、待決事項）**
- 本批（2026-10-18，S9 6-4 #36、#37、6-5 第 7 點；風控 2026-10-18 C7-8、Q3-6、v0.12 審查第四節 tech-writer；方向：不變）：Consequences 新增四點與 C7-8，無被取代原文；見 §Consequences。
- 本批（同上）：CEO 說明第 4 點原文——
  > 4. 主機如果在交易日收盤定案前開機，市場資料可能只抓到盤中值；當天如果沒有再抓，那一天只要仍算觀察日，就會照實記成缺日，不會補造；如果那一天連大盤的定案資料也沒有，就不算觀察日，也不會出現在缺日紀錄裡，這類日子怎麼揭露會在開始記錄前定好。之後約 60 個交易日內，部分紀錄可能判成證據不足或作廢，作廢的會算進最壞情境。根本修法要改 ADR-0012（已核可），屆時會請你核可。

  改為見 §Consequences CEO 說明第 4 點（風控 2026-10-18 Q3-6 版本，取代 Q-3 時的版本）。
- 本批（同上）：待決事項原文（加註〔已決〕的各行）——
  > - **風控**：N-1 的處理提案（A-77 第 12 項）送審。
  > - **tech-architect**：N-1 的處理提案（A-77 第 12 項），標明方向，送風控審；D_v 前必須核可。
  >   - A-63 第 11 點：`outlook_block` 的選用優先序、selector 簽章、LM-144 的 slot 登記，以及 `e_changed_since` 情形下的驗證徽章遮蔽（第九批，送風控審；D_v 前）。
  >   - 平日、而且不是已接入官方休市日表所列休市日的日期 d，如果既不在 D-8.1 (i)，也不在 (ii)，就不是觀察日，也不會有缺日列。這類日期的偵測與 §4.2 揭露方式，由 TA 提案、送風控，D_v 前核可（風控 2026-10-17 疑義裁定回送確認 Q-3）。
  > - R-5、R-7 翻案伴隨句（RC‴-4；列入 D_v 前置字面清單，未核可不得進入 D_v）。
  > - **D_v 前置**：N-1 未核可不得進入 D_v（RC‴-3）；R-5、R-7 未核可不得進入 D_v（RC‴-4）；Q-3（平日、非休市日、既不在 D-8.1 (i) 也不在 (ii) 的日期）的偵測與 §4.2 揭露未核可不得進入 D_v（風控 2026-10-17 疑義裁定回送確認 Q-3）。

  改為見 §待決事項（各行加註〔已決〕；tech-architect 新增 C9-7、ADR-0028 CS-17 的同步修訂與診斷標籤存放處；quant 新增數項；CEO 新增第 8 點；D_v 前置加 C9-7 與 quant 的 R10-5 確認）。

**D-3（`forecast_outcome` 更正子項、`forecast_ledger_events`；掛 A-65、A-77）**
- 本批（2026-10-18，S3 提案 1；S4 R10-1；風控 2026-10-18 Q3-7；方向：收緊）：D-3 `forecast_outcome` 原文——
  > - 更正：`supersedes_id`、`correction_job_id`；

  改為見 §D-3 `forecast_outcome`（加 `correction_causes`）。`forecast_correction_job` 與 `forecast_correction_job_end` 為新增，無被取代原文。
- 本批（2026-10-18，風控 2026-10-18 Q3-7；方向：收緊）：D-3 `forecast_ledger_events` 原文——
  > - `forecast_ledger_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, kind ∈ {db_restored, f3_resume_approved, pit_violation_confirmed, replay_review_approved, x2_confirmed_non_session, session_calendar_conflict}, payload_json, recorded_at)`（r3″；RC″-2）：`pit_violation_confirmed` 的 payload 帶 `forecast_id` 與重算值（r1，A-8）。

  改為見 §D-3 `forecast_ledger_events`（列舉加 `unobserved_weekday`）。
- 本批（2026-10-18，S1 提案 5 條文 A；方向：收緊）：D-3 `forecast_record` 判定材料子項加 `band_def` 單位與寫入驗證，無被取代原文。

**D-1（模組表；掛 A-77）**
- 本批（2026-10-18，S9 第 5 項 (b)、6-4 #2；方向：不變）：新增一列 `app/forecast/observed_days.py`，無被取代原文；見 §D-1。理由：`observed_sessions()` 要讀 X2 事件，放在 `app/data` 會違反「forecast → data」的依賴方向。

**第二輪套用（2026-10-18，同一批）**
> tech-architect 疑義 1～27 裁定（`work/reviews/2026-10-18-ADR-0027-下一批套用疑義裁定-tech-architect.md`，commit d75ebdf）第 1～8、10～14、16、21、24、26 項與附帶 A～D；風控第 8 項單項確認（`work/reviews/2026-10-18-ADR-0027-下一批疑義第8項確認-風控.md`，commit cc24d01）的 E8-1～E8-3，以及第 3 項被取代原句逐字進修訂紀錄的要求。與第一輪、事先宣告 v0.12、ADR-0028 CS-17 同批；ADR-0028 的 commit 在前，同一次 push。方向都是不變或收緊，累計統計 18／2／9／1／3 不變。
> 下列分兩類：(甲) fd87063 的原文被第二輪再改字的部分；(乙) 第一輪套用版（未 commit，不屬於 fd87063）被第二輪取代的字句。兩類都逐字保留。

**甲、fd87063 原文**
- A-79（表數；裁定第 2 項；方向：不變）：評估摘要「最大代價」原文——
  > - 表數多（13 張），寫入規則有一部分在 trigger 裡。

  Consequences「代價與壞處」原文——
  > - 13 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。

  M-11 列原文（修訂清單表）——
  > | **M-11** | D-6.1 表清單〔`:376-381`〕；F-3〔`:581`〕 | 五張表；F-3 只寫「暫停顯示，查明」 | 新增 8 張表並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6） | R-106、R-112、R-113；風控第 9 項 |

  改為 15 張表（D-3 加 `forecast_correction_job`、`forecast_correction_job_end`）；M-11 改為新增 10 張表；CEO 待決事項加第 9 點（知悉）。
- A-63／A-57（甲案擴及三個 scope；裁定第 6 項；方向：收緊）：D-11.4 第 11 項 (c) RC′-2 子點原文——
  > - 不按 claim 篩選：任一筆成立，所有族群 claim 都適用。

  A-27 (e) 揭露原文——
  > - G_eff 的定義見 A-57 (iv)。大盤與個股的 G_eff 就是「判定 `display_state` 的同一列最新 daily snapshot」的 `gate`。

  A-57 (iv) 原文（兩行）——
  > - **查詢時的有效集合 G_eff**：G_eff ＝ snapshot 的 `gate`；族群的 `pa9_holds` 依 RC′-2 為真時，再加入 `forward_n_below_min`。
  > - 這個查詢時調整只可能把族群的 `shown` 變成 `gated`，不得有其他方向（性質測試）。

  改為見 §D-11 第 4 點。

**乙、第一輪套用版**
- A-65（裁定第 2、4、21 項及附帶 D；R10-5 已確認）：
  > - `forecast_correction_job_end(correction_job_id PK, rechecked_count, changed_count, rejected_count, ended_at)`：作業結束時寫入。沒有 end 列代表作業中斷；這時該作業的 `recheck_range_json` 由下一個作業完整重跑，qa 核對涵蓋率。
  > - FAIL_CLOSED 的情形是封閉的，只有以下四種：兩個以上的原因；`[dividend_factor_corrected]`；`[window_bar_corrected]` 但 `correction_is_display_neutral(chain)` 為假；`[settlement_close_corrected]`、P(T) 收盤有變（`start_price_json` 的收盤和前一列不同），而且 quant 還沒有書面確認 R10-5。
  > | `[settlement_close_corrected]` | LM-150＋LM-152；P(T) 收盤有變、而且 quant 尚未書面確認 R10-5 → FAIL_CLOSED |
  > FAIL_CLOSED 的列以 `MaskedRecordView` 回傳，狀態句是 LM-154。`display.py` 的常數 `PT_CORRECTION_CONFIRMED: Final = False`，改成 True 的 PR 必須附 quant 書面確認的路徑，由 coordinator 核對。
  > - (a) 對照表的鍵集合 ＝ 列舉；每個值恰好對應 LM-151、LM-152、FAIL_CLOSED 三者之一；
  > - (b) 寫入函式拒絕列舉外的值、空陣列，以及與 `supersedes_id` 不一致的組合；單一原因的差異驗證（R10-2）的三種拒絕，各一格；
  > - FAIL_CLOSED 的格（LM-154 條件 ③⑤⑩）：四格——除權息因子；兩個以上原因；未豁免的診斷更正；R10-5 確認前、P(T) 收盤有變的收盤更正。每格斷言：
  > - 對照格：`[x2_session_removed]`；P(T) 不變（或 R10-5 已確認）的 `[settlement_close_corrected]`；豁免成立的 `[window_bar_corrected]`。這三格都找不到 LM-154。
  > - 第九批提案 4 第 2 條的「結算…讀 `base_close`」依此限縮為稽核用途
  > - 凡是渲染 `label` 或 LM-131 的紀錄列，以及單筆展望區塊（LM-93／LM-115），都帶 `threshold_display = {down, up}`（不帶正負號）；
  > - resolved → 作廢 → resolved 的鏈，即使數值相同也不適用例外。

  （最後一行為句尾加註前的原句。）已改為見 §D-3、§D-11 第 4 點第 11 項 (g)(h)、§對實作的約束 FL-22、FL-52。`PT_CORRECTION_CONFIRMED` 常數取消：R10-5 的確認（事先宣告 v0.12 V12-12）與對照表同批生效。
- A-77（裁定第 1、3、7、8、11、12 項及附帶 B；方向：不變，第 3 項收緊）：
  > - N-1 未核可不得進入 D_v（登記於待決事項）。〔已決：甲案，已核可（風控 2026-10-17 第九批 TA 提案確認）〕
  > - 先順延、後來又因其他原因 supersede 的列，同樣帶累計值，不得改成 null。這樣 §4.2 的順延筆數只要讀更正鏈的最後一筆，就能逐列數出（R-C）。
  > - 這個數字由 `x2_shift_json` 逐列數出，不另存欄位。
  > - 依第 5 項，X2 確認當下 d ∉ (i)，所以新公式在確認當下和原公式相同，只在第 12 項的情形下不同。
  > - 登記當下 d ∉ (i) ∪ (ii)，所以新公式在登記當下和原公式相同。
  > - payload：`session_date`、`evidence ∈ {weekend, official_holiday, independent_source_absent}`、`origin ∈ {x2_check, candidate_t, post_x2_final_run, post_unobserved_backfill}`（`post_unobserved_backfill` 依風控 2026-10-18 Q3-7 加入，見第 10 項）、受檢 bar 的參照。`independent_source_absent` 只用於 `origin = post_x2_final_run`（見第 12 項）。
  > - **ADR-0028 CS-17 現行的 grep 規則只允許在 `is_final` 內呼叫 `final_after(`。** 要先修訂 CS-17：另開 ADR-0028 commit，送風控單項確認。修訂落地前，不得合併 `final_session_evidence` 與 X2 寫入函式的程式。
  > - 分別只進入 (i)、只進入 (ii)、兩者都進入，`backfill_via` 與參照欄位都正確，而且只寫一筆。
  > - 同一個 (`session_date`, `origin`) 只寫一次；之後 d 再經另一個集合進入，也不另寫。§4.2 ④ 以日數計。
  > - 本 ADR 與事先宣告都只引用這一個定義，由 `app/data/session_calendar.py` 的單一函式提供。不得另寫時點比較。（第 1 項重複句，附帶 B）

  第 3 項（L511 與 L551）的計數單位對齊風控 v0.12 確認 Q12-1；風控 2026-10-18 第 8 項確認將第 3 項列為收緊（計得只會更多）。
- A-63（裁定第 5、6、11 項、附帶 C；方向：收緊）：
  > - (1) `outlook_block`、G_eff＝{`forward_n_below_min`}、`gated` → 選 LM-12，不選 LM-120；
  > - (7) G_eff＝{`forward_n_below_min`}、`gated`、`status` ≠ 未驗證 → 選 LM-120，不選 LM-12；
  > - 列舉範圍：每一個已登記的 (scope_kind, slot) × `display_state` ∈ {`gated`, `suspended_f3`, `withdrawn_f2`} × P(scope) 的每一個非空子集；族群另外 × `n_masked` ∈ {真, 假}。`outlook_block` 的列舉再 × `status` 四態。
  > - (5) 族群 `n_masked = true` 時選不到 LM-129。渲染全文中的每一段數字，只能來自已核可字面的固定文字（例如 LM-126、LM-127 的「5 個交易日」），或 `{k}`、`{h}`、`{MM/DD}` 占位；不得有任何占位綁定該 claim 的 snapshot n 或其衍生值。fixture 的 n 取一個不會出現在固定文字裡的值（例如 137），全文掃描找不到這個字串。LM-144 片段本身不含數字。
  > - 同一區塊經 LM-122／LM-123／LM-126／LM-127 代入 LM-144，交代筆數待彙整。
  > - **遮蔽與方向互斥**（條件 ⑪）：`views` 在任何回應（`OutlookView`、紀錄列、`settled_record`）帶出族群 claim 的 label 之前，要另外確認 `n_disclosure_masked` 為假；為真時不帶 label，並記 WARNING。這是 `pa9_holds` 之外的獨立檢查。依 RC′-2，遮蔽成立時 `pa9_holds` 必然為真，所以這一條是縱深防禦。
  > - 效果是 `shown` 變成 `gated`；`suspended_f3`、`withdrawn_f2` 照 snapshot。A-57 (iv)「查詢時調整只可能把 `shown` 變成 `gated`」的性質測試，擴及三個 scope。
  > - 「更正後命中翻轉」（事先宣告 v0.11 L687、L1221）比較的是：更正鏈中第一筆 `resolved` 列，對上鏈尾。鏈尾不是 `resolved` 時，另外歸入「改為作廢」。由 quant 確認後登記。
- A-34（裁定附帶 A；方向：不變（引用）＋收緊）：
  > | `app/outlook/inputs.py` | PIT 輸入：唯讀 `MarketPanelReader`；大盤擷取。σ_d 序列的觀察日取 `observed_sessions()` 在 cutoff(T) 的可見集合（事先宣告 v0.12 V12-19） |
  > | `app/outlook/volatility.py`（r2，A-34；純函式） | `sigma_d(log_returns)` 是唯一的 σ 核心，常數 `SIGMA_MIN_VALID`、`SIGMA_FLOOR` 取自 dirdef；大盤、族群、個股共用。σ_d 序列的觀察日取 `observed_sessions()` 在 cutoff(T) 的可見集合（事先宣告 v0.12 V12-19） |

  改為由呼叫端（recorder）以參數傳入 `observed_sessions(as_of=cutoff(T))` 的結果；`app.outlook.*` 不得 import `app.forecast.*`；FL-41c 加 import graph。
- A-79（待決事項；裁定第 10 項）：
  > 〔風控 2026-10-18 已單項確認（C9-7 與 Q-3 及 CS-17 提案確認第二節第 3 項）〕。（TA 的「CS-17 同步修訂」行；改為〔已決〕，前提是 ADR-0028 與本 ADR 同一次 push、ADR-0028 在前。）
  > - D_v 前置：「Q-3（平日、非休市日、既不在 D-8.1 (i) 也不在 (ii) 的日期）的偵測與 §4.2 揭露未核可不得進入 D_v」改為「未觀察平日（風控 2026-10-17 疑義裁定回送 Q-3）的偵測與 §4.2 揭露…」，避免與事先宣告 §7.2 的 Q-3 撞號（Q3-1）。
- A-79（r3 系列段落；裁定第 13 項）：r3 系列段落不改寫，只在方向統計下方一行句尾加「〔第九、十批更新：A-77 標註與累計統計（18／2／9／1／3）見修訂紀錄第九、十批段〕」，無被取代原文。
- 同批機械核對（coordinator，`work/reviews/2026-10-18-ADR-0027與v0.12及ADR-0028同批機械核對-coordinator.md`）J-1、J-3（coordinator 定案，CEO 可推翻；方向：不變）。被取代的字句屬本批未 commit 的行，逐字保留：
  > - 先順延、後來又因其他原因 supersede 的列，同樣帶累計值，不得改成 null。§4.2 的順延筆數依同一計數單位：每筆預測只計一次，更正鏈中任一列的 `x2_shift_json` 非 null 就計入（比照風控 v0.12 確認 Q12-1）。
  > - 沒有 snapshot 時（大盤、個股）：…不加入 `forward_n_below_min`：n 未知，LM-128「前瞻紀錄樣本不足」無從確認屬實；fail-closed 已由 `validation_refresh_pending` 達成。FL-52 的「沒有 snapshot」格另外斷言：找不到 LM-128。

  J-1：計數單位句的逗號改成冒號（與 v0.12 §4.2 的 E3-1 句逐字一致）；A-77 第 8 項另一處同類句本來就是冒號。J-3：風控 C7-2 照寫文逐字為「FL (a) 的「沒有 snapshot」格另外斷言」，已改回。
- 說明：乙類各行為第一輪套用版被取代的整句或整行原文（部分行只引被改的那一句）。第二輪新增的 E8-1、E8-2、E8-3、`registered_unobserved_weekday`、第 12 項新句、第 14 項、第 16 項、附帶 A～D，沒有被取代的原文。

---

**A-96″（FL-25 等，另開 commit）**

> A-96″ 增補（2026-10-17）依 ADR-0028 A-96′／A-96″；風控 2026-10-17 A-96′ 單項確認（K-10～K-13；`work/reviews/2026-10-17-ADR-0028-A96A97單項確認-風控.md`）。本 commit 和 r3″ 分開。

**FL-25**：本文不變；新增 fixture (a)～(i)，無被取代原文；見 §對實作的約束 FL-25。方向：收緊。
**A-75 (iv)**：新增 K-10～K-12 三句，無被取代原文；A-75、A-77 已定案的文字不改。方向：補定義（收緊）。這三句掛在既有的 A-75 底下，ADR-0027 的方向統計（33 條，19／2／9／1／2）不變。〔第九、十批更新：現行累計為 18／2／9／1／3（見上「第九、十批」段的累計方向統計），本段不新增 A 號，也不使任何一條換類別，統計不變。〕

- 套用說明（2026-10-18，tech-writer；B 類轉錄）：
  - 條文來源：tech-architect `work/reviews/2026-10-17-ADR-0028-A96雙撇-tech-architect.md` 第三節（以引用區塊內的條文為準，逐字套用；引用區塊之外的補註不寫入本 ADR）。
  - 風控確認：`work/reviews/2026-10-17-ADR-0028-A96雙撇回送項確認-風控.md` 第一節末段（該節內容與 K-10～K-13 一致，沒有意見，可照 TA 原文套用）。
  - ADR-0028 A-96″ 已於 commit c881380 落地；本 commit 的基準是 commit 871e602 的 ADR-0027。
  - 狀態維持 proposed；沒有新增 A 號。
- coordinator 補登（2026-10-18）：A-96″ 小段落地後，檔頭第九、十批那一行的「見『修訂紀錄』最後一段」會指錯，改為「見『修訂紀錄』第九、十批段」；方向不變。原句逐字：「第九、十批衍生待決項套用（2026-10-18，與事先宣告 v0.12 同批）：來源 S1～S9（tech-architect 整合清單，`work/reviews/2026-10-18-ADR-0027-下一批整合與C9-7及Q-3提案-tech-architect.md` 6-1，commit f294cc9），加上風控 2026-10-18 兩份確認（C9-7、Q-3、CS-17 提案確認：commit b55e41f；事先宣告 v0.12 草稿審查：commit 97fbe50）。任何一份都不得單獨 commit；優先序與逐項改動見「修訂紀錄」最後一段。狀態維持 proposed。」

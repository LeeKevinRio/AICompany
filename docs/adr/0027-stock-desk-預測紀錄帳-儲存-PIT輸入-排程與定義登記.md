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
- 剩餘待決項套用（2026-10-18，與事先宣告 v0.13 同批）：N-3～N-6、N-9、N-12 與起算日綁定。來源（都在 `work/reviews/`）：風控 `2026-10-18-ADR-0027剩餘待決項與v0.13提案審查-風控.md`、tech-architect `2026-10-18-ADR-0027-N12與起算日修正補充-tech-architect.md` 與 `2026-10-18-ADR-0027-剩餘待決項N3至N9與起算日提案-tech-architect.md`；衝突時依此順序。任何一份都不得單獨 commit；優先序與逐項改動見「修訂紀錄」的「剩餘待決項（N-3～N-12、起算日）」段。沒有新增 A 號；累計方向統計維持 18／2／9／1／3。狀態維持 proposed。
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
- 表數多（21 張），寫入規則有一部分在 trigger 裡。

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
| **M-11** | D-6.1 表清單〔`:376-381`〕；F-3〔`:581`〕 | 五張表；F-3 只寫「暫停顯示，查明」 | 新增 16 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`；剩餘待決項 N-4 加 `forecast_void_late_diag`；v0.14 V14-01 加 `forecast_settle_eval`；C-22 加 `forecast_index_check`；N-24 加 `forecast_gap_audit`；N-22c 加 `forecast_replay_index_check`、`forecast_replay_outcome`）並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6） | R-106、R-112、R-113；風控第 9 項 |

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
| `app/forecast/settlement.py`（v0.14，V14-01） | 結算評估唯一的寫入端：`run_settlement_evaluation(*, store, market_reader, index_service, clock)`。它讀一次 R、建立判定視圖（D-9.2），呼叫 `scoring.py` 的純函式判定全部未結算的預測，並在同一個主 DB 寫入交易內寫入 `forecast_settle_eval` 與該次評估的全部 `forecast_outcome` 列。簽章不接受 R、判定視圖或判定結果；`forecast_outcome` 的排程結算寫入只能從這個函式呼叫（AST 列舉呼叫點） |
| `app/forecast/validation.py` | 驗證快照、四態、F-2 與 F-3 的顯示判定（只讀結算結果，不算報酬） |
| `app/forecast/audit.py` | 缺日稽核；`forecast_gaps`、缺日稽核所做的未觀察平日登記與 `forecast_gap_audit`（N-24）在同一個主 DB 寫入交易內寫入，`forecast_gap_audit` 只能從這裡寫入（AST） |
| `app/forecast/correction.py`（N-21） | 更正作業唯一的寫入端：`run_correction_job(*, store, market_reader, index_service, clock)`。依 D-9 第 5 點建立並存下判定視圖，呼叫 `scoring.py` 的同一套純函式重算，寫入 supersede 列、`forecast_void_late_diag` 與 `forecast_correction_job_end`。簽章不接受觸發、預測清單、重查範圍、視圖、E、V 或重算結果；`forecast_outcome` 的 supersede 寫入只能從這個函式呼叫（AST） |
| `app/forecast/index_verification.py` | `INDEX_VERIFICATION_SOURCE_REGISTRY`、`coverage_end_at`、獨立來源的查詢介面（D-3「`INDEX_VERIFICATION_SOURCE` 的版本歷史」） |
| `app/forecast/replay_checks.py` | `forecast_replay_index_check` 唯一的寫入端；`replay_period`、`replay_observed_sessions`、`check_replay_gate`；只經 `app.services.index` 讀取 `^TWII`；每次取數嘗試都留紀錄，成功的一次存成唯一的快照 |
| `app/forecast/display.py`（純函式） | 每個 claim 與 scope 的顯示決定（閘門、下架、暫停、逾時） |
| `app/forecast/views.py`（r1，A-2） | 預測帳**唯一的對外讀取點**：讀 store 與 snapshot，呼叫 `display.py`，回傳 `OutlookView`。`app/api/forecast.py`、`app/api/outlook.py`、`app/api/advice.py`、`app/plan/**`、`app/alerts/**` 都只經過這裡讀 |
| `app/forecast/observed_days.py` | `observed_sessions()`：觀察日集合（A-77 第 3 項）。它要讀 X2 事件，放在 `app/data` 會違反「forecast → data」的依賴方向，所以放在 `app/forecast/`。`observed_sessions(*, as_of)`：`as_of` 之後才寫入的 run、X2 事件、未觀察平日登記都不計入；`as_of` 為 None 時取當下。未扣除 X2 確認日的 (i) 由 `app/data/session_calendar.py` 的 `final_sessions()` 提供，兩者不得混用。（v0.14，V14-01）結算端另以 `observed_sessions(*, view)` 呼叫：`view` 是 D-9.2 的判定視圖，或 D-9 第 5 點更正作業的判定視圖（`market_run_max` 取 `market_scan_to`，其餘取 `forecast_correction_job` 的同名欄位）；判定視圖只由 `settlement.py` 與 `correction.py` 建立；(i) 只取 `run_id ≤ view.market_run_max` 的 run，(ii) 只取 `view` 的大盤快照，X2 事件與未觀察平日只取 `event_id ≤ view.ledger_event_max`。`as_of` 與 `view` 恰好給一個。`settlement.py`、`scoring.py` 不得以 `as_of` 呼叫（AST）；預測端照舊用 `as_of=cutoff(T)` |
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
  - （r2，A-29）`forecast_input_series`：加 `series_kind ∈ {index_bars, basket_log_returns, replay_index_bars}`（A-34；`replay_index_bars` 依事先宣告 V16-03，只由 `replay_checks.py` 寫入，前瞻路徑不得讀它）。
  - （tech-architect 2026-10-18；事先宣告 V16-03）**重放快照與 bar 值的正規化**：單一純函式 `canonical_bar_values(row)` 定義如下：
    - 欄位依序為 `session_date`（ISO 日期）、`source`、`open`、`high`、`low`、`close`；
    - 有限數取 IEEE 754 double 的最短往返十進位字串（Python `repr(float)`）；非有限值為字串 `"NaN"`、`"Infinity"`、`"-Infinity"`；缺值為 null。

    `checked_values_sha256` 與 `target_values_sha256` ＝ 以 `canonical_bar_values` 輸出、序列化為 JSON 陣列（`separators=(",", ":")`，UTF-8）後的 sha256。這是既有「正規化」的明文，NaN 依此比較，不做浮點比較（風控 C43）。

    `replay_index_bars` 快照的 `content_sha256` 計算方式：每列取 `canonical_bar_values` 再接 `as_of`、`fetched_at`（ISO8601 原樣字串），各列以其序列化字串排序，整體序列化成 JSON 陣列後取 sha256。每個 registration 只有一份快照，見 `forecast_replay_index_check`。
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
    - （v0.14 對照登記）`diag_basket_with_excluded` 就是事先宣告 §6.3 欄位表與 §1.2 v0.3 第 1 點的 `diag_basket_last_close`（診斷籃子標籤：被排除的成員以最後可得收盤放回籃子算出的標籤）。兩個名稱指同一個欄位、同一個定義。本 ADR 的 schema、程式與測試一律用 `diag_basket_with_excluded`；事先宣告保留 `diag_basket_last_close` 作為定義名稱，不改名。事先宣告凡引用 `diag_basket_last_close` 之處（含 LG-19、LG-29 (h′)），在本 ADR 與程式中都讀作 `diag_basket_with_excluded`。程式中不得出現 `diag_basket_last_close` 這個識別字（grep），避免兩個欄位並存。
    - （v0.14 V14-02）**`basket_excluded_members_json`**：族群籃子被排除的成員，以及逐成員的排除原因（事先宣告 §1.2 第 3 點）。
      - 只限 `scope_kind = sector`：族群列必須非 null，沒有排除時為 `[]`；其他 scope 必須為 null。
      - JSON 陣列，每一項恰為 `{symbol, reasons}`，依 `symbol` 排序、不重複；`symbol` 必須是 T 日籃子 S_T 的成員。T 日權重一律為 1/|S_T|（等權建倉），不另存。
      - `reasons` 非空、不重複，值取自封閉列舉，依 dirdef 常數 `BASKET_EXCLUSION_REASON_ORDER = ("dividend_factor_unusable", "split_or_reduction_suspected", "t_plus_h_bar_unavailable")` 排序。
        - 這是 `VOID_REASON_ORDER` 的相對順序：`t_plus_h_bar_unavailable`（成員在判定視圖中沒有可用於結算的 T+h bar）佔 `missing_bar_after_wait` 的位置。不用 `missing_bar_after_wait` 這個值，是因為成員層沒有自己的等待，等待在 claim 層（D-9.3 `basket_coverage_below_90`）。
        - 常數屬於 `definition_logic_sha256` 的範圍。
      - 三個原因各自判定、全部評估、不短路；一個成員有多個原因時全部記下（事先宣告 §1.2 v0.3 第 3 點依原因分列揭露，風控 R14-11）。
      - 由結算評估或更正的寫入函式，以判定 `void_reasons_json` 的同一次評估、同一個判定視圖填入，不接受呼叫端傳入。寫入後隨該列固定（D-2 第 2 點），不得事後以重讀的資料推回。
      - **寫入驗證**（任一項不成立就拒絕寫入）：排序、不重複、值在列舉內；x ＝ 陣列長度，N ＝ |S_T|：`status = resolved` ⇒ 10x ≤ N；`void_reasons_json = ["basket_coverage_below_90"]` ⇔ 10x > N（整數比較）。
  - 期間路徑：`invalidation_triggered`、`invalidation_first_hit`、`mae`、`mfe`；
  - 稽核：`input_digest_recomputed`、`digest_match`；
  - 狀態：`status ∈ {resolved, unresolvable_missing_data, excluded_corporate_action}`、`status_reason`（D-9.3）；
  - （N-12；事先宣告 v0.13 V13-01、v0.12 V12-14）`void_reasons_json`：作廢判定當下成立的原因集合。
    - JSON 陣列，值取自 D-9.3 的五值封閉列舉，依 `VOID_REASON_ORDER` 排序、不重複。
    - `status = resolved` 時必須為 null；`status ≠ resolved` 時必須非空，而且第一個元素等於 `status_reason`。
    - 由結算或更正的寫入函式，以判定 `status_reason` 的同一次評估填入，不接受呼叫端傳入。寫入後隨該列固定（D-2 第 2 點），不得事後依重讀的資料推回，也不得另表補記。
    - **寫入驗證**（任一項不成立就拒絕寫入）：
      - 值在列舉內，排序正確、不重複；
      - 第一個元素等於 `status_reason`；
      - 依 scope 的允許集合：
        - `market` ⊆ {`index_bar_confirmed_erroneous`, `missing_bar_after_wait`}；
        - `symbol` ⊆ {`dividend_factor_unusable`, `split_or_reduction_suspected`, `missing_bar_after_wait`}；
        - `sector` ⊆ {`basket_coverage_below_90`}（v0.14 V14-02：族群成員在 T+h 沒有可用 bar、因子不可用或符合分割判準時，依事先宣告 §1.2 排除該成員，不在 claim 層記 `missing_bar_after_wait`、`dividend_factor_unusable` 或 `split_or_reduction_suspected`；與事先宣告 V13-01 族群句、LG-28 (i) 同批一致）。
    - **§4.2 的資料來源**：
      - V12-14 (2) ＝ 鏈尾是作廢列、而且 `void_reasons_json` 同時含 `index_bar_confirmed_erroneous` 與 `missing_bar_after_wait` 的筆數；
      - V13-01 (3) ＝ 鏈尾作廢列依完整集合分類計數；
      - 兩者都是每筆預測只計一次，由這一欄逐列數出，不另存欄位。
  - （N-4；晚到資料的觸發第 4 點，風控 2026-10-18 R-11 甲法）**`settle_source_run_max`**：`forecast_outcome` 新增欄位。每次結算評估由寫入端的單一函式讀一次市場 DB 的 `MAX(run_id)`＝R，以 R 界定該次評估的判定視圖（事先宣告 §6.3「觸發」，v0.14 V14-01），在同一個函式內完成該次評估全部預測的判定，並把同一個 R 寫入每一筆結算或作廢列；R 與判定視圖都不接受呼叫端傳入，也不接受呼叫端以其他視圖算出的判定結果。更正作業寫入的列，比照本點：以該作業 `forecast_correction_job` 的 `market_scan_to` 界定重算所用的市場 DB 視圖（只取 `run_id ≤ market_scan_to` 的列），並把同一個值寫入該作業寫入的每一列；不另讀 `MAX(run_id)`，不接受呼叫端傳入。還原保護（D-3「晚到資料的觸發」第 8 點）成立、`market_scan_restore_suspected = 1` 的作業，同節第 9 點「`run_id` ≤ `settle_source_run_max` 的 run 都在判定視圖內」對它寫入的列不保證成立，晚到判定只是下限，依同節第 8 點揭露（風控 2026-10-18 v0.14 單項確認）。大盤列為 null。比較只用序號，不用時鐘（比照 RC″-2）。〔v0.14 取代（V14-01；風控 2026-10-18 v0.14 審查 R14-4）：原寫「結算或作廢寫入當下，由寫入函式經 `MarketPanelReader` 自行取得市場 DB 的 `MAX(run_id)` 填入，不接受呼叫端傳入；大盤列為 null。比較只用序號，不用時鐘（比照 RC″-2）。」〕
  - （v0.14 V14-01；風控 2026-10-18 v0.14 審查 R14-5 ①②）**判定視圖與等待的欄位**：
    - `settle_eval_id`：指向 `forecast_settle_eval`（D-3，下文）。
      - 結算評估寫入的列（`supersedes_id IS NULL`）必須非 null，而且 `settle_source_run_max` 等於該評估的 `market_run_max`。大盤列的 `settle_source_run_max` 依 R14-4 為 null，判定視圖仍由 `settle_eval_id` 追溯。
      - 更正作業寫入的列（`supersedes_id IS NOT NULL`）必須為 null，以 `correction_job_id` 追溯。
    - `wait_sessions`（等待觀察日數 k）：`INTEGER NOT NULL`，≥ 0。
      - 結算評估寫入的列 ＝ 該評估 `observed_sessions_json` 中晚於該列 T+h 的日數；T+h 依同一份清單數出（X2 確認日已排除，所以順延後的 T+h 自動適用）。
      - 由 `run_settlement_evaluation()` 自行計算填入，不接受呼叫端傳入，不得事後以重讀的觀察日推回。
      - 正常排程下為 0～5。評估曾經停擺，或觀察日事後才進入判定視圖時，值可能大於 5；照實記錄，不截斷。
      - 更正作業寫入的列，照抄被 supersede 列的值。
    - `wait_deadline_session`（D_5）：判定視圖中 T+h 之後第 5 個觀察交易日。
      - `wait_sessions ≥ 5` 時必須非 null，而且等於 `observed_sessions_json` 中 T+h 之後第 5 個日期。
      - `wait_sessions < 5` 時為 null：D_5 在判定視圖中還沒有被觀察到，不得推估。
      - 更正作業寫入的列照抄。
    - **寫入驗證**（任一項不成立就拒絕寫入）：
      - 上述各項；
      - 結算評估寫入的列中，`void_reasons_json` 含 `missing_bar_after_wait`、`basket_coverage_below_90` 或 `index_bar_confirmed_erroneous`（只有等待到期限才會成立的原因）⇒ `wait_sessions ≥ 5`；
      - 更正作業寫入的列，三個欄位與被 supersede 列的值不同 → 拒絕。
    - **§4.2 的資料來源**：「等待後結算」① 由 `wait_sessions` 逐列數出，每筆預測只計一次（更正鏈各列的值相同）。分列為 k ＝ 1～4，以及 k ≥ 5（期限評估；k > 5 的筆數另列，表示期限評估之前曾有觀察日未經任何一次評估：評估停擺，或觀察日事後才進入判定視圖）。不另存欄位。
  - 更正：`supersedes_id`、`correction_job_id`、`correction_causes`（第十批，提案 1；A-65、A-77 第 8 項）；
    - `correction_causes`：JSON 陣列，封閉列舉（`OUTCOME_CORRECTION_CAUSES`，見 D-11.4 第 11 點 (h)）、排序固定、不重複。
      - `supersedes_id IS NULL` 的列必須為 null；`supersedes_id IS NOT NULL` 的列必須非空。由寫入函式驗證；列舉外的值、空陣列、或與 `supersedes_id` 不一致，都拒絕寫入。
      - 這個欄位和 `forecast_record.correction_reason` 無關，兩者不得互相引用或 join。
  - 唯一性：`UNIQUE(forecast_id) WHERE supersedes_id IS NULL`，以及 `UNIQUE(supersedes_id)`。
- **新增 `forecast_correction_job` 與 `forecast_correction_job_end`**（第十批 R10-1；比照 `forecast_run`／`forecast_run_end`），兩張都只增不改：
  - `forecast_correction_job(correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT, triggers_json, recheck_range_json, market_scan_from INTEGER NOT NULL, market_scan_to INTEGER NOT NULL, market_scan_restore_suspected INTEGER NOT NULL CHECK (market_scan_restore_suspected IN (0,1)), ledger_event_from INTEGER NOT NULL, ledger_event_max INTEGER NOT NULL, index_check_from INTEGER NOT NULL, index_check_max INTEGER NOT NULL, settle_eval_from INTEGER NOT NULL, settle_eval_max INTEGER NOT NULL, index_series_sha256 NOT NULL, index_final_now NOT NULL, holiday_table_json, view_range_json, observed_sessions_json, started_at)`：作業開始時寫入。`triggers_json` 必須非空，每一項都帶來源參照（`event_id`、查證紀錄 ID、`run_id` 或因子修訂的參照）；沒有觸發就拒絕執行。
    - （N-4；晚到資料的觸發第 2、5、8 點）`market_scan_from`、`market_scan_to`：本作業啟動時 `scan_late_market_bars()` 的掃描範圍 (`market_scan_from`, `market_scan_to`]，以市場 DB 的 `run_id` 表示。作業開始時與 `triggers_json` 在同一個交易內寫入，由寫入函式自行填入，不接受呼叫端傳入。
      - `market_scan_from` ＝ W，也就是 `correction_job_id` 最大、而且已有 `forecast_correction_job_end` 列的作業的 `market_scan_to`；沒有這樣的作業時為 0。
      - `market_scan_to` ＝ 該次掃描取得的 `run_max`；還原保護（第 8 點）成立時，`market_scan_to` ＝ `market_scan_from` ＝ W。
      - 寫入驗證（不成立就拒絕寫入）：`market_scan_from` 等於上述 W；`market_scan_from ≤ market_scan_to`。
      - `market_scan_restore_suspected`：第 8 點成立時為 1，否則為 0，由寫入函式依同一次掃描自行填入，不接受呼叫端傳入。§4.2「可能不完整」的揭露，列出這一欄為 1 的每一個作業（`correction_job_id`、`started_at`、`market_scan_from`）。第 8 點成立、但沒有其他觸發因而沒有寫入作業的掃描，不留下任何列；市場 DB 還原後新寫入、`run_id` 不大於 W 的 run，之後也不會被掃到〔推論：還原後 `run_id` 由還原檔的序號接續〕。所以這些列只是下限，不代表完整的受影響期間；§4.2 照此註明，不得以「沒有這類作業」表示市場 DB 沒有被還原。偵測結果的持久記錄與受影響 run 範圍的界定，列後續追蹤清單 N-20。
      - 不放 `triggers_json`（它是觸發陣列，不是標頭），也不放 `forecast_correction_job_end`（第 5 點的驗證在作業開始時就要做）。
    - （N-21；tech-architect 2026-10-18）**判定視圖欄位**：作業開始時與 `triggers_json` 在同一個交易內寫入，由寫入函式自行填入，不接受呼叫端傳入；取得方式見 D-9 第 5 點「更正作業的判定視圖」。
      - `ledger_event_from`、`index_check_from` ＝ `correction_job_id` 最大、而且已有 `forecast_correction_job_end` 列的作業的 `ledger_event_max`、`index_check_max`；沒有這樣的作業時為 0（比照 `market_scan_from`）。
      - `ledger_event_max`（E）、`index_check_max`（V）＝ 本作業在開始交易內完成未觀察平日登記之後，讀到的 `forecast_ledger_events` 的 `MAX(event_id)` 與 `forecast_index_check` 的 `MAX(check_id)`。
      - `index_series_sha256`、`index_final_now`、`holiday_table_json`、`view_range_json`、`observed_sessions_json`：與 `forecast_settle_eval` 的同名欄位同義，界定本作業的大盤快照、休市日表、範圍與觀察日。
    - （N-29；tech-architect 2026-10-18）`settle_eval_from` ＝ `correction_job_id` 最大、而且已有 `forecast_correction_job_end` 列的作業的 `settle_eval_max`，沒有時為 0；`settle_eval_max` ＝ 本作業在開始交易內讀到的 `forecast_settle_eval` 的 `MAX(settle_eval_id)`，沒有列時為 0。D-9 第 5 點 ④ 的結算快照比對，以及 D-3「晚到資料的觸發」第 1 點的第四類觸發，都只取 `settle_eval_id ≤ settle_eval_max` 的列。寫入驗證與寫入 job_end 時的再驗證，比照上一子點的兩個 from。
      - **寫入驗證**：兩個 from 等於上述值；`from ≤ max`；`index_series_sha256` 指向 `series_kind = index_bars` 的既有列。寫入 job_end 時再驗證一次兩個 from 仍等於當下的值；不成立就拒絕寫入 job_end，記 WARNING（比照「晚到資料的觸發」第 5 點）。
  - `forecast_correction_job_end(correction_job_id PK, rechecked_count, changed_count, rejected_count, rejected_json, pending_json, void_late_data_count, ended_at)`：作業結束時寫入。沒有 end 列代表作業中斷；這時該作業的 `recheck_range_json` 由下一個作業完整重跑，qa 核對涵蓋率。`void_late_data_count` 是作廢之後才補到資料的筆數（見 D-11.4 第 11 點 (h)「作廢列不因之後補到的資料而 supersede」；事先宣告 v0.12 V12-20），不屬於 `rejected_count`。〔N-4：操作定義（補到資料、而且算得出診斷結果）與涵蓋邊界，見 D-3 `forecast_void_late_diag` 與「晚到資料的觸發」〕
  - `rejected_count` ＞ 0 時記 WARNING，筆數在 §4.2 揭露。寫入函式拒絕的列不得靜默略過。
  - （N-29；tech-architect 2026-10-18）**`rejected_json`、`pending_json`**：
    - `rejected_json`：本作業拒絕寫入的每一筆，`[{forecast_id, tail_outcome_id, reason, failed_check, causes}]`，依 `forecast_id` 排序。`reason ∈ {shift_t_plus_h_unobserved, shift_t_plus_h_data_unavailable, shift_index_bar_unverified, write_validation_failed}`。`failed_check` 只在 `write_validation_failed` 時非 null，記被違反的寫入驗證名稱。`causes` ＝ 該筆在本作業歸屬的 `correction_causes`。`rejected_count` ＝ 陣列長度。
    - `pending_json`：本作業結束時的待重算集合（D-9 第 5 點「待重算」，含 `write_validation_failed` 一種），依 `forecast_id` 排序。每項為 `{forecast_id, tail_outcome_id, scope_kind, scope_key, reason, shifted_t_plus_h, observed_through, market_scan_to, causes, since_job_id}`：
      - `shifted_t_plus_h` 在 `shift_t_plus_h_unobserved` 時為 null；
      - `observed_through` ＝ 本作業 `observed_sessions_json` 的最後一日；
      - `market_scan_to` ＝ 本作業的值；
      - `causes` ＝ 該筆在本作業歸屬的 `correction_causes`，必含 `x2_session_removed`；
      - `since_job_id` ＝ 該 `forecast_id` 第一次列入的作業。
    - 內容 ＝ 前一個已完成作業的 `pending_json`，扣掉本作業已為該 `forecast_id` 寫入 supersede 列的項，其餘原樣帶入；本作業新列入、或重查後仍待重算的項，以本作業的值取代（`since_job_id` 不變）。
    - 寫入 job_end 時，在同一交易內驗證下列各項。任一項不成立，就拒絕寫入 job_end，記 WARNING，該作業視為中斷：
      - `rejected_count` 等於 `rejected_json` 的長度；
      - `rejected_json` 中 `causes` 含 `x2_session_removed` 的每一項，都在 `pending_json`；
      - 前一個已完成作業 `pending_json` 的每一項，恰好落在下列之一：本作業為該 `forecast_id` 寫入 supersede 列；本作業重查後沒有任何欄位改變（§6.4 第 3 點，不寫列）；仍在本列 `pending_json`。
    - §4.2 的計數單位：待重算與被拒絕的筆數，以不同的 `forecast_id` 計，依 `reason` 分列。同一筆在多次作業中重查而再被拒絕，不重複計；`rejected_count` 是作業層的計數。
  - 這兩張表落實事先宣告 §6.4 第 2 點；`forecast_outcome.correction_job_id` 必須指向 `forecast_correction_job`。
- **`forecast_void_late_diag`**（N-4；R10-3、事先宣告 v0.12 V12-20）：記錄作廢之後才補到資料的診斷結果。只增不改（D-2 第 2 點的 trigger 照樣適用），不得寫入 `forecast_outcome`。
  - **欄位**：`diag_id INTEGER PRIMARY KEY AUTOINCREMENT`、`outcome_id`、`forecast_id`、`correction_job_id`、`supersedes_diag_id NULL`、`late_data_kinds`、`late_data_refs_json`、`diag_start_price_json`、`diag_end_price_json`、`diag_window_factors_json`、`diag_label`、`diag_hit`、`diag_baseline_hits_json`、`computed_at`（store 時鐘）。
  - **參照**：
    - `outcome_id` 指向 `status ≠ resolved` 的更正鏈鏈尾列。依 R10-3，作廢列不會再被 supersede，所以鏈尾固定。
    - `forecast_id` 等於該列的 `forecast_id`；`correction_job_id` 指向 `forecast_correction_job`。
    - 以上由寫入函式驗證，不成立就拒絕寫入。
  - **`late_data_kinds`**：JSON 陣列，封閉列舉 `VOID_LATE_DATA_KINDS = {t_plus_h_bar, settlement_close, window_bar, dividend_factor, basket_member}`，排序固定、不重複、非空。
    - 歸屬比照 `correction_causes` 的確定性規則：只會多記，不會少記。
    - `late_data_refs_json` 每一項都帶來源參照（`run_id`、查證紀錄 ID，或因子修訂的參照）。
    - 要增列，須修訂本點並送風控。
  - **寫入者只有更正作業**（D-9.5）：
    - 依 R10-3，更正作業不重算作廢列的 outcome。但對重查範圍內 `status ≠ resolved` 的鏈尾列，要以目前可得的資料，經 `scoring.py` 的同一套結算函式算一次診斷結果。
    - D-9.1 的觸發條件與 D-9.2 的結算評估視圖不適用（v0.14 V14-01）。診斷所用的市場 DB 資料只取 `run_id ≤` 本作業的 `market_scan_to`；大盤 bar、X2 確認日、未觀察平日、確認判定紀錄與官方休市日表，依本作業的判定視圖（D-9 第 5 點「更正作業的判定視圖」）；其餘依 D-9.2 的 PIT 規則（定案下限、來源優先序、不得用 `_hindsight_view`）與 D-9.3。
    - 診斷結果本身仍落入任一作廢條件時，不寫列。
  - **鏈**：`UNIQUE(outcome_id) WHERE supersedes_diag_id IS NULL`，以及 `UNIQUE(supersedes_diag_id)`。同一個 `outcome_id` 之後又補到資料時，只在 `diag_*` 和鏈尾不同（正規化 JSON 逐位比較）時才新增一列，並填 `supersedes_diag_id`；相同就不寫。
  - **計數一致**：`forecast_correction_job_end.void_late_data_count` ＝ 該作業寫入本表的列數，由寫入 job_end 的函式在同一個交易內驗證，不成立就拒絕寫入 job_end。所以 `void_late_data_count` 的操作定義是「補到資料、而且算得出診斷結果」的筆數。
  - **用途限制**：
    - 不影響 E、n、W、作廢率、任何 snapshot 欄位或任何狀態判定。本表不屬於 `E_CHANGING_EVENTS`，不在序號比較範圍內，所以不影響 `e_changed_since`。
    - 只有 `validation.py` 的 §4.2 報表可以讀它：
      - 「作廢後補到資料的筆數」以不同的 `forecast_id` 計；
      - 模型與各必備基準的診斷命中率，取每個 `outcome_id` 的鏈尾，只在 E 上計算（D-11.1）。
    - `views`、任何 API route 與匯出都不得讀它，畫面不顯示（AST 列舉呼叫點）。
    - 欄位名不得使用 forward return 類識別字（ADR-0012 C-15），計算只在 `scoring.py` 內。
    - 作廢列的 `status`、`status_reason` 不因本表而改變（V12-20）。
- （N-4）**晚到資料的觸發**（讀端輪詢、寫端不動；data-engineer 2026-10-18 查證）：
  1. **誰偵測**：每日結算排程在結算之後，以及每一次更正作業啟動時，呼叫單一函式 `scan_late_market_bars()`。它只經 `MarketPanelReader` 新增的唯讀方法 `ok_bars_runs_between(run_id_exclusive, run_id_inclusive)` 讀市場 DB（一條 SQL，回傳 `run_id`、`session_date`、`recorded_at`、`source`）。`pit_snapshot` 與 `MarketPanelStore` 不得寫主 DB，也不得呼叫更正作業。掃描有命中時，以命中項為觸發啟動更正作業。同一步另以唯讀查詢檢查三件事，有任一項就同樣啟動（N-21；第三件為 N-29）：
     - (W_E, `MAX(event_id)`] 內有沒有 `x2_confirmed_non_session` 事件；
     - (W_V, `MAX(check_id)`] 內有沒有 `determination ∈ {close_erroneous, non_close_erroneous, correct_close_obtained}` 的確認判定列。
     - （N-29）待重算：最近一個已有 `forecast_correction_job_end` 列的作業，其 `pending_json` 非空，而且 (W_S, `MAX(settle_eval_id)`] 內有一列 `forecast_settle_eval`，對其中某一項成立下列任一條件：
       - `observed_sessions_json` 含晚於該項 `observed_through` 的日期；
       - `scope_kind = market`，而且該列的大盤快照含該項 `shifted_t_plus_h` 的列 r，r 的數值（以 `checked_values_sha256` 的正規化規則比對，同 D-9 第 5 點 ④）與每一列 `settle_eval_id ≤` W_S 的 `forecast_settle_eval` 大盤快照中同一日的列都不同；那些快照都沒有同一日的列時，也算不同（tech-architect 2026-10-18；風控 2026-10-18 確認。理由：同一個數值已由先前的作業比對過，再出現只是重新讀取，不是新資料；23:10 重試與啟動補跑每次都會再寫一列 `forecast_settle_eval`）；
       - `scope_kind ∈ {symbol, sector}`，而且市場 DB 在 (該項 `market_scan_to`, 該列 `market_run_max`] 內，有含該標的（族群為任一成員）在 `shifted_t_plus_h` 的 bar 的 ok 定案 run（經 `ok_bars_runs_between` 與 `is_final`）。

       觸發項為 `{kind: pending_resettle, forecast_id, since_job_id, settle_eval_id}`。本類只讀 `pending_json` 的上列欄位、`forecast_settle_eval` 與市場 DB 的 run，不讀 `forecast_record`、`forecast_outcome`。

     W_E、W_V、W_S 與 D-3 `forecast_correction_job` 的 `ledger_event_from`、`index_check_from`、`settle_eval_from` 同一定義，由同一個函式導出。四類都沒有時不啟動（D-3「`triggers_json` 必須非空」不變）。啟動與否只依本點四類觸發是否存在（第四類只依新的觀察日、結算快照中新出現的大盤數值或新的定案 run 是否存在，不依時間經過，也不依結算評估的執行次數；沒有新資料時不啟動），不讀預測、label、`hit`、基準命中或任何驗證統計（AST）。不得提供以操作者指定的觸發、日期或預測啟動更正作業的 CLI、API 或工具（D-9 第 2 點「不由人工對個別預測觸發」；風控 2026-10-18 C-22 確認）。
  2. **掃描範圍**：先取一次 `run_max = MAX(run_id)`，範圍為 `(W, run_max]`。W 是最近一個已有 `forecast_correction_job_end` 列的作業記下的 `market_scan_to`，首次為 0。沒有 end 列的中斷作業依 D-3 由下一個作業完整重跑，W 不因它前進。只取 `kind='bars'`、`status='ok'`、`session_date IS NOT NULL` 的 run，每筆再經 `is_final(TW, session_date, recorded_at)`（ADR-0028 CS-17）過濾，不得自行比較時戳。
  3. **配對**（三項都成立才算觸發）：主 DB 有鏈尾列 `status ≠ resolved`，而且結算窗 [T, T+h] 含 `session_date`；該列的標的（個股，或族群成員）在該 run 有一列 `market_daily_bars (run_id, symbol)`；該 run 的 `run_id` 大於該鏈尾列的 `settle_source_run_max`（晚到的定義：結算當下市場 DB 還沒有這筆 run）。
  4. **`settle_source_run_max`**：`forecast_outcome` 新增欄位。每次結算評估由寫入端的單一函式讀一次市場 DB 的 `MAX(run_id)`＝R，以 R 界定該次評估的判定視圖（事先宣告 §6.3「觸發」，v0.14 V14-01），在同一個函式內完成該次評估全部預測的判定，並把同一個 R 寫入每一筆結算或作廢列；R 與判定視圖都不接受呼叫端傳入，也不接受呼叫端以其他視圖算出的判定結果。更正作業寫入的列，比照本點：以該作業 `forecast_correction_job` 的 `market_scan_to` 界定重算所用的市場 DB 視圖（只取 `run_id ≤ market_scan_to` 的列），並把同一個值寫入該作業寫入的每一列；不另讀 `MAX(run_id)`，不接受呼叫端傳入。還原保護（D-3「晚到資料的觸發」第 8 點）成立、`market_scan_restore_suspected = 1` 的作業，同節第 9 點「`run_id` ≤ `settle_source_run_max` 的 run 都在判定視圖內」對它寫入的列不保證成立，晚到判定只是下限，依同節第 8 點揭露（風控 2026-10-18 v0.14 單項確認）。大盤列為 null。比較只用序號，不用時鐘（比照 RC″-2）。〔v0.14 取代（V14-01；風控 2026-10-18 v0.14 審查 R14-4）：原寫「結算或作廢寫入當下，由寫入函式經 `MarketPanelReader` 自行取得市場 DB 的 `MAX(run_id)` 填入，不接受呼叫端傳入；大盤列為 null。比較只用序號，不用時鐘（比照 RC″-2）。」〕
  5. **觸發項**：`{kind: source_revision, run_id, recorded_at, session_date}` 寫入 `triggers_json`。觸發身分以 `(run_id, recorded_at)` 成對為準。寫入函式驗證：新作業的 `market_scan_from` 等於前一個已完成作業的 `market_scan_to`；同一個 `(run_id, recorded_at)` 不得出現在兩個已有 `forecast_correction_job_end` 列的作業的 `triggers_json`：作業開始時對照已完成的作業驗證；寫入 job_end 時再驗證一次，同時驗證本作業的 `market_scan_from` 仍等於當下的 W，而且沒有 `correction_job_id` 大於本作業、已有 end 列的作業。任一項不成立就拒絕寫入 job_end，記 WARNING（該作業視為中斷，依 D-3 由下一個作業完整重跑）。沒有 end 列的中斷作業的觸發，由下一個作業依第 2 點重新掃得，不受此限。因此，已完成的作業依 `correction_job_id` 排列時，掃描範圍首尾相接、不重疊。
  6. **涵蓋邊界**：本觸發只涵蓋個股 claim 與族群成員的 bars。大盤的 T+h bar 與收盤不經市場 DB（M-8），不在本觸發內；除權息因子晚到應由「因子修訂」觸發涵蓋（D-11.4 第 11 點 (h)：`OUTCOME_CORRECTION_CAUSES` 第 4 類 `dividend_factor_corrected`，以及同點「原因怎麼歸屬」所列的因子修訂觸發；事件來源依 D-4 第 2 點，是市場 DB 的 `pit_dividend_announce_rows`，不是 ADR-0016 D-5.2 的主 DB 同步紀錄）。該觸發的偵測方式（誰偵測、讀哪種 run、怎麼配對、晚到怎麼判定）尚未定義（後續追蹤清單 N-17）；定義落地並經風控確認、修訂本點之前，`dividend_factor` 視為沒有觸發涵蓋。同一個缺口也使第 4 類 `dividend_factor_corrected` 沒有觸發來源，已結算列不會因除權息因子更正而 supersede；這一面是事先宣告 §6.4 既有規則的實作缺口，N-17 是 D-9 結算程式實作前的阻擋項，不得以本點的「未涵蓋，不計」揭露代替；`basket_member`（listing、classification 的 run）沒有任何觸發涵蓋。`VOID_LATE_DATA_KINDS` 中沒有觸發涵蓋的種類，在 §4.2 標「未涵蓋，不計」，不得以 0 呈現。
  7. **預期量**：現行管線不回填（ADR-0012 C-10），同一 session 有 ok run 之後即略過（`_already_ok_today`），所以 `void_late_data_count` 預期接近 0〔推論，data-engineer 2026-10-18〕。這是預期，不是驗收門檻，0 不得當成「沒有晚到資料」的證據。失效條件：新增任何回填路徑，或 N-16 改變冪等略過時，重查本點。
  8. **還原保護**：W 大於目前市場 DB 的 `MAX(run_id)` 時，視為市場 DB 被還原：記 WARNING；本次不產生任何 `source_revision` 觸發，W 不前進，其餘觸發照常；§4.2 揭露該期間的作廢後補到資料筆數可能不完整，直到 devops-sre 依 ADR-0026 D-9.4 處理並修訂本點。不得靜默重掃。
  9. 與 O-1 的關係（v0.14 V14-01 定案）：`run_id` ≤ 該列 `settle_source_run_max` 的 run 都在判定視圖內，判定時已經評估過，不屬於本點的晚到；`run_id` 大於者依第 3 子點判定。〔v0.14 取代（V14-01）：原寫「9. 與 O-1 的關係：等待期間才寫入、在作廢寫入前已存在的 run，不屬於本點的晚到；這類 bar 的歸屬依 O-1 定案（後續追蹤清單 N-13）。」〕
- **`forecast_settle_eval`**（v0.14 V14-01；風控 2026-10-18 v0.14 審查 R14-5 ①）：每次結算評估一列，記下該次評估的判定視圖。只增不改（D-2 第 2 點）。由 `run_settlement_evaluation()` 在該次評估的主 DB 寫入交易內寫入（D-9.2 執行順序 ⑤）；欄位全部由該函式自行填入，不接受呼叫端傳入。
  - **欄位**：
    - `settle_eval_id INTEGER PRIMARY KEY AUTOINCREMENT`；
    - `market_run_max INTEGER NOT NULL`（R）；
    - `ledger_event_max INTEGER NOT NULL`（E；沒有事件時為 0）；
    - `index_check_max INTEGER NOT NULL`（V；沒有紀錄時為 0）；
    - `index_series_sha256 NOT NULL`（大盤快照，指向 `forecast_input_series.content_sha256`）；
    - `index_final_now NOT NULL`（建快照時傳給 `is_final_bar` 的 store 時鐘讀值）；
    - `index_refetch ∈ {not_needed, refetched, refetch_failed}`；
    - `holiday_table_json`（`official_holiday_table_meta(TW)` 的值，可為 null）；
    - `view_range_json = {start, end}`；
    - `eval_set_count INTEGER NOT NULL`、`eval_set_sha256 NOT NULL`（評估集合 U，D-9.2；U 為空時 count 為 0，sha256 取空字串的值）；
    - `observed_sessions_json`（範圍內的觀察日，遞增、不重複）；
    - `waiting_json`（本次判定為等待的預測，`[{forecast_id, wait_sessions}]`，依 `forecast_id` 排序；沒有時為 `[]`）；
    - `started_at`（store 時鐘）。
  - **寫入驗證**（任一項不成立，整個評估交易都不寫入）：
    - `market_run_max` ≥ 前一列的值（倒退依 D-9.2「R 倒退」處理）；
    - `index_series_sha256` 指向已存在、`series_kind = index_bars` 的列；
    - `waiting_json` 中的預測，在同一個交易內沒有 outcome 列，而且都是判定視圖中 T+h 已觀察到、`valid_until_session` 已過、尚未結算、屬於評估集合 U 的預測；本列寫入的每一筆 outcome 也都屬於 U；
    - 同一個交易寫入的每一筆 outcome 列，`settle_eval_id` 都等於本列。
  - **用途**：
    - 稽核與重算（FL-65）；
    - §4.2「等待後結算」③：每筆 daily snapshot 當下仍在等待中的預測，取該 snapshot 之前最近一列的 `waiting_json`；
    - 事先宣告 §6.3 X3 的跨擷取比對：每次評估各存一份大盤快照。
  - **限制**：不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何狀態判定。只有 `validation.py` 的 §4.2 報表、稽核工具、`settlement.py`（前一列的 `market_run_max` 與 `index_check_max`，D-9.2、D-3 `forecast_index_check`）、`correction.py`（D-9 第 5 點 ④ 所用的快照與 N-29 的比對），以及 D-3「晚到資料的觸發」第 1 點的啟動檢查（N-29 第四類）可以讀它；`views`、API route 與匯出不得讀它（AST 列舉呼叫點，比照 `forecast_void_late_diag`）。
- **`forecast_index_check`**（C-22；tech-architect 2026-10-18，與 N-21 同批）：事先宣告 §6.3「大盤指數序列」的偵測紀錄、「查證程序」的查證紀錄，以及 X1、X3、X4 的確認判定紀錄，存在同一張表、共用一個序號。只增不改（D-2 第 2 點）。D-9.2 的 V（`forecast_settle_eval.index_check_max`）與 D-9 第 5 點的 `forecast_correction_job.index_check_max` 都是本表的 `MAX(check_id)`，沒有列時為 0。X2 的判定紀錄仍是 `x2_confirmed_non_session`（A-77 第 7 項），不寫入本表。
  - **共通欄位**：`check_id INTEGER PRIMARY KEY AUTOINCREMENT`；`entry_kind ∈ {detection, verification, determination}`；`detection_id`（detection 列為 null；其餘列必須指向同表 `entry_kind = detection` 的列）；`session_date`（受檢 bar 的交易日；非 detection 列必須等於所指 detection 列的值）；`written_by ∈ {recorder, settle_eval}`；`recorded_at`（store 時鐘）。以下各組欄位只在對應的 `entry_kind` 非 null，其餘列必須為 null：
    - **detection**：
      - `check_item ∈ {x1_close_unusable, x1_close_involved, x1_non_close, x2_pending, x3, x4}`；
      - `x2_case ∈ {set_iii_only, conflict}`（只限 `x2_pending`；conflict 指 A-77 第 5 項的證據矛盾）；
      - `checked_bars_json`：受檢 bar 的完整列，每列帶 OHLC、`source`、`as_of`、`fetched_at`；X3 為兩次擷取的同日列，X4 為相鄰兩日的列；
      - `checked_values_sha256`：只對各列的 (`session_date`, `source`, OHLC) 做正規化後的 sha256，不含 `as_of`、`fetched_at`（快取每次覆寫這兩欄，D-9.2）。
    - **verification**：
      - `query_point ∈ {on_detection, daily_recheck, source_onboarding}`（事先宣告 §6.3「查證程序」①～③）；
      - `queried_at`（查詢前的 store 時鐘）；
      - `source_name`、`source_version`：`result = source_not_connected` 時兩者為 null，其餘必須非 null；
      - `result ∈ {value_obtained, source_has_no_day, query_failed, source_not_connected, outside_coverage}`（`outside_coverage` 依 D-3「`INDEX_VERIFICATION_SOURCE` 的版本歷史」）；
      - `source_values_json`、`comparison_json`：只在 `value_obtained` 時非 null，內容是獨立來源的值、官方公布位數，以及逐欄四捨五入後是否相等。
    - **determination**：
      - `determination ∈ {close_erroneous, non_close_erroneous, no_error, correct_close_obtained}`；
      - `basis ∈ {direct, verified}`；
      - `basis_check_id`：`verified` 時指向同一個 detection、`result = value_obtained` 的查證列；`direct` 時為 null；
      - `target_bar_json`：判定對象那一根 bar 的列，必須是所指 detection 的 `checked_bars_json` 其中一列；`correct_close_obtained` 另帶取自 `basis_check_id` 的正確收盤。
      - `target_values_sha256`：`target_bar_json` 那一列，依 `checked_values_sha256` 的同一個正規化規則算出的 sha256。
  - **唯一性**：
    - `UNIQUE(session_date, check_item, checked_values_sha256) WHERE entry_kind = 'detection'`：同值的 bar、同一個偵測項只登記一次。來源改寫使數值不同時，視為新的偵測。
    - `UNIQUE(detection_id, determination, target_values_sha256) WHERE entry_kind = 'determination'`：一個 detection 涉及多列 bar 時（X1 同一交易日兩列、X3 兩次擷取、X4 相鄰兩日），每一列各自判定，同一列的同一種判定只寫一次。
  - **與事先宣告 §6.3 的對應**：

    | §6.3 情形 | detection | verification | determination |
    |---|---|---|---|
    | X1 收盤本身不可用（三種） | `x1_close_unusable` | 不查 | `close_erroneous`、`direct`，與 detection 同一交易 |
    | X1 不一致而牽涉收盤 | `x1_close_involved` | ①～③ | 收盤不符 → `close_erroneous`，同一交易另寫 `correct_close_obtained`（獨立來源值即正確值）；只有非收盤不符 → `non_close_erroneous`；全部相符 → `no_error`；都是 `verified` |
    | X1 其餘（只限非收盤欄位） | `x1_non_close` | 不查 | `non_close_erroneous`、`direct` |
    | X2 只有 (iii) | `x2_pending`、`set_iii_only` | ①～③ | 來源沒有這一天 → 不寫 determination，改寫 `x2_confirmed_non_session`（`basis = verified`，`verification_ref` ＝ 該查證列）；來源有 d → `no_error` |
    | X2 證據矛盾（A-77 第 5 項） | `x2_pending`、`conflict` | ①～③ 照跑 | 一律不寫 |
    | X2 直接確認 | 不寫本表 | — | `x2_confirmed_non_session`、`basis = direct`（不變） |
    | X3、X4 | `x3`、`x4` | ①～③ | 同「X1 不一致而牽涉收盤」 |

  - **待查證集合**：`check_item ∈ {x1_close_involved, x2_pending, x3, x4}` 的 detection 列，同時符合以下兩項：
    - 沒有 `close_erroneous`、`non_close_erroneous` 或 `no_error` 的 determination；
    - `x2_pending` 另外沒有 `verification_ref` 指向其查證列的 `x2_confirmed_non_session` 事件。

    `conflict` 列永遠在集合內。
  - **寫入者與時機**（交易邊界：detection、該次 ① 查證，以及由它導出的 determination 或 `x2_confirmed_non_session` 同一交易；② 與 ③ 的每一筆查證列，與由它導出的 determination 或 `x2_confirmed_non_session` 同一交易；不同查證列各自一個交易）：
    - **recorder**：大盤 claim 記錄所用的每一根 `^TWII` bar（特徵窗與 T 日），比對偵測項；有觸發而且身分尚未登記時，寫 detection 與 ①（`direct` 項寫 determination）。
    - **`run_settlement_evaluation()` 的 D-9.2 ③**：
      - 快照內每一根 bar，處理同上；
      - 獨立來源已接入時（dirdef 外的 ADR 常數 `INDEX_VERIFICATION_SOURCE` 非 None），對當時全部待查證列各做一次 ②；
      - 該常數的 `version` 還沒有出現在 `check_id` ≤ 前一列 `forecast_settle_eval.index_check_max`（沒有前一列時為 0）的任何 `source_onboarding` 列時，對全部待查證列做一次 ③，取代當次的 ②。`INDEX_VERIFICATION_SOURCE` 的涵蓋範圍擴大時一律升 `version`，因此同樣觸發 ③（事先宣告 §6.3「查證程序」③「含涵蓋範圍擴大」）。
      - 都在 ④ 讀 V 之前完成。
    - 其他任何程式路徑（API、CLI、更正作業、重放、缺日稽核）都不得寫入本表（AST 列舉呼叫點）。查不查、先查哪一筆，都不得依預測、標籤或結果決定。
    - （風控 2026-10-18 C-22 確認 suggested (a)）**由查證列導出的 X2 確認**：`basis = verified` 的 `x2_confirmed_non_session`，只能和它 `verification_ref` 所指的查證列在同一個交易內、由同一個 store 函式寫入：先寫查證列，再寫事件；`verification_ref` 只取該函式剛寫入的 `check_id`，不接受呼叫端傳入（AST 列舉呼叫點）。A-77 第 7 項的寫入驗證在插入事件之前完成；不成立時（例如重算後 d ∈ D-8.1 (i)），查證列照樣寫入，事件不寫，記 WARNING，該 detection 留在待查證集合（事先宣告 §6.3「查證程序」：每次查詢都新增一列，查不到也記）。
  - **判定時怎麼讀**（D-9.2 ⑥、D-9 第 5 點 ④）：
    - 只讀 `check_id ≤` 視圖的 `index_check_max` 的列。
    - 判定用到的大盤 bar（P(T)、P(T+h) 收盤，以及窗內 bar 的診斷欄位），依 (`session_date`, `source`, OHLC) 與 `target_bar_json` 比對，套用相符的 determination：
      - `close_erroneous` 而沒有 `correct_close_obtained` → 該收盤確認有誤、尚未取得正確值；
      - 有 `correct_close_obtained` → 用其正確收盤，結算列記明來源；
      - `non_close_erroneous` → 只影響診斷欄位。
    - 「所用的 bar」：P(T) 取 `start_price_json`（R10-5）；已結算列重算時，取 D-9 第 5 點「已結算數值所用的大盤 bar」。P(T) 與已結算列所用的 bar，只在它本身相符一筆 `close_erroneous`、而沒有 `correct_close_obtained` 時，才是「確認有誤、尚未取得正確值」；同一 `session_date` 其他 bar 的 `close_erroneous` 不影響它，它若屬於待查證集合，依下一子點照原值計分。尚未用於結算的 P(T+h)（含 X2 順延後的新 T+h）以交易日為單位：同一 `session_date` 任一根 bar 有 `close_erroneous`、而沒有 `correct_close_obtained` 時，該日收盤是「確認有誤、尚未取得正確值」。上述兩種情形下，該日數值不同的 bar，只有在不屬於待查證集合內任何 detection 的 `checked_bars_json` 時，才算事先宣告 §6.3「確認有誤之後」所說「通過 X1～X4 的來源修訂值」；屬於待查證集合時（例如與已確認有誤的那次擷取構成 X3），不算取得正確值。讀法依事先宣告 §6.3「確認有誤之後」V15-03 登記（風控 2026-10-18 v0.15 單項確認；後續追蹤清單 N-26、N-27）。
    - 除上一子點的情形外，沒有 determination 的待查證 bar 照原值計分。
  - **寫入驗證**（寫入函式加 BEFORE INSERT trigger；任一項不成立就拒絕寫入）：
    - 各組欄位的 null 與非 null 規則依上文。
    - `basis = direct` ⇔ 所指 detection 的 `check_item ∈ {x1_close_unusable, x1_non_close}`；兩者的 determination 分別只能是 `close_erroneous`、`non_close_erroneous`。
    - `no_error` 與 `close_erroneous`、`non_close_erroneous` 對同一個 detection 互斥。
    - `correct_close_obtained` 必須已有同一 detection、同一 `target_values_sha256` 的 `close_erroneous`，而且 `basis = verified`。
    - `x2_pending` 只能有 `no_error`，而且只限 `x2_case = set_iii_only`、`basis = verified`、`basis_check_id` 所指查證列 `result = value_obtained`；不讀 D-8.1 (i)，d 已經進入 (i) 也照寫（風控 2026-10-18 C-22 確認 suggested (b)）。`conflict` 寫任何 determination 都拒絕（A-77 第 5 項）。理由：`no_error` 的意思是「獨立來源有 d，d 是交易日，這根 bar 沒有 X2 的錯誤」（事先宣告 §6.3 X2「只有 (iii) 成立」一支）；d ∈ (i) 和它同向，不矛盾。d ∉ (i) 是 X2 確認的必要條件（A-77 第 5 項），不是 `no_error` 的條件；要求它，會讓 d 進入 (i) 之後、獨立來源也確認有 d 的 detection 永遠留在待查證集合。
  - **用語綁定**：本 ADR 其他位置的「查證紀錄」「查證紀錄 ID」「查證紀錄的參照」，指本表 `entry_kind = verification` 的列與它的 `check_id`。「確認判定紀錄」「收盤更正的查證紀錄」指 `entry_kind = determination` 的列。X2 依 A-77 第 7 項。
  - **用途限制**：
    - 不屬於 `E_CHANGING_EVENTS`。
    - `views`、API route 與匯出不得讀它。只有以下呼叫點可以讀（AST 列舉呼叫點），讀寫一律經 `store.py`：`recorder.py`（偵測身分是否已登記）；`settlement.py`（D-9.2 ③ 的待查證集合、④ 的 V）；`correction.py` 與 D-3「晚到資料的觸發」第 1 點的啟動檢查（N-21 的觸發與 V）；`scoring.py` 的判定；`validation.py` 的 §4.2 報表（查證紀錄依 `result` 分列的筆數、異常待查證數）；稽核工具。
  - **重放**：不寫本表（D-9 第 7 點）。
- `forecast_replay`：結構與 `forecast_record` 相同，另加 `freeze_commit`、`replay_session`、`replay_gate_check_id`（指向 `forecast_replay_index_check` 中 `gate_passed = 1` 的 gate 列；寫入驗證見該表）。永遠不與前瞻紀錄合併。
- **`INDEX_VERIFICATION_SOURCE` 的版本歷史**（tech-architect 2026-10-18；風控 2026-10-18 v0.15 單項確認第四節 ADR 端第 5 項；事先宣告 §4.7 執行閘門 (1)、§4.7「重放期的起訖日」V16-02）：
  - **形狀**：dirdef 外的 ADR 常數，放在 `app/forecast/index_verification.py`（暫定名）。
    - 每一項為 `IndexVerificationSource = {source_name, version, coverage_start, coverage_end}`（frozen）。`version` 是正整數；`coverage_start` 是日期；`coverage_end` 是日期，或 `rolling`。
    - 只增不改的序列為 `INDEX_VERIFICATION_SOURCE_REGISTRY: tuple[IndexVerificationSource, ...]`。`INDEX_VERIFICATION_SOURCE` ＝ 序列的最後一項，序列為空時為 None。
  - **涵蓋範圍**：
    - 每個版本的涵蓋範圍是一整段連續的日曆區間，以單一函式 `coverage_end_at(v, t)` 取上界：
      - 固定日期時，就是 `coverage_end`；
      - `rolling` 時，是 `is_final(TW, d, t)` 為真的最晚日曆日 d（ADR-0028 CS-17），只依日期與時鐘判定。
    - 涵蓋範圍必須依獨立來源本身可提供的完整連續區間登記，不得為了重放或任何結果而截短或延長。登記時附 data-engineer 的來源範圍查證。
    - 涵蓋範圍只取自本序列，不得由查詢結果、來源回應或任何資料推定（AST：讀涵蓋範圍的程式一律經本序列與 `coverage_end_at`）。
  - **版本規則**（性質測試）：
    - `version` 自 1 起，每一項加 1；版本序跨 `source_name` 也維持單調；
    - 已登記的項不得修改或刪除；
    - `source_name` 或涵蓋範圍有任何改變，一律新增一項，並升 `version`；
    - 同一個 `source_name` 時，新項的涵蓋範圍必須包含前一項；
    - 更換 `source_name`，或縮小涵蓋範圍，須送風控，方向依 K-12 判斷，判斷不了的一律視為放寬。
    - 比較涵蓋範圍的包含關係時，`rolling` 視為晚於任何固定日期；同一個 `source_name` 由 `rolling` 改為固定日期，視為縮小。
    - 涵蓋範圍的查證（data-engineer）只依獨立來源本身的資料或文件，不得讀取 `^TWII`，也不得讀取任何重放或前瞻結果。
  - **重放 v\* 的判斷**（事先宣告 V16-02）：依本序列的順序，取第一個「`coverage_end` 不早於 E」的版本。`rolling` 版本在這個判斷中視為不早於任何日期，所以 v\* 不隨 (a) 進行的時點而改變。
  - **ADR 登記表**：每一項都以本 ADR 的修訂登記在下表。程式中的序列必須與下表逐項、逐欄相同（qa-reviewer 機械核對）。「登記 commit」＝ 程式中該項首次出現的那個 commit，由下一個 commit 補填，核對採執行／判斷分離（章程 §4）：由具 Bash 權限的職能以 `git log` 唯讀取得，逐字存入 `work/`，qa-reviewer 依存檔判讀。

    | `version` | `source_name` | `coverage_start` | `coverage_end` | 登記 commit | 登記的修訂 |
    |---|---|---|---|---|---|
    | （尚無登記；`INDEX_VERIFICATION_SOURCE` 為 None） | | | | | |

  - **查證紀錄的涵蓋核對**（`forecast_index_check` 與 `forecast_replay_index_check` 的查證列、日曆查詢列都適用）：
    - `source_version` 必須在本序列中，`source_name` 與該版本相同；
    - `session_date` 晚於 `coverage_end_at(v, queried_at)`，或早於 `coverage_start` 時，不查詢，`result = outside_coverage`，該觸發仍為異常待查證；
    - `result = source_has_no_day` ⇒ `session_date` 在 [`coverage_start`, `coverage_end_at(v, queried_at)`] 內（寫入驗證）。
    - 事先宣告 §6.3 X2「獨立來源在它的涵蓋範圍內沒有 d」的「涵蓋範圍」，就是本點的登記值。
  - **首次登記的同批條件**：本序列由空變為非空的修訂，必須同批定案四件事，並送風控：
    - 後續追蹤清單 N-28 的第一項（d ∈ D-8.1 (i)、獨立來源在涵蓋範圍內沒有 d）；
    - X1「收盤本身不可用」在接入後是否查證（風控 2026-10-18 v0.15 單項確認 B-3 suggested）。
    - `coverage_end = rolling` 時，data-engineer 對來源公布時點的查證：`is_final(TW, d, t)` 為真時，來源已公布 d 的指數日資料。查證不成立時，只能登記固定的 `coverage_end`，或另定較晚的上界並送風控；
    - 若同批採用上一項（X1「收盤本身不可用」接入後也查證），重放端（事先宣告 V16-04 不補值）是否對齊，同批由 quant 具名提出；不對齊時，重放與前瞻在這一點的差異照實揭露。

    在此之前，FL-69 斷言本序列為空。
- **重放登記檔**（tech-architect 2026-10-18；事先宣告 §4.7 執行閘門 (a)、§4.7「重放期的起訖日」V16-02）：
  - **位置**：`apps/stock-desk/registrations/replay/<replay_claim_id>.json`，在執行閘門 (a) 以單一 commit 加入。之後不得修改；同一 replay claim 不得有第二份。
  - **欄位**（JSON，鍵固定）：`format_version`；`replay_claim_id`；`definition_version`；`rules_version`；`freeze_commit`；`freeze_evidence`；`F`；`E`；`v_star`；`S`；`n_req`；`holiday_table_meta`；`computed_with`。
    - `freeze_evidence = {kind: "github_pr_merge", repo, base_ref, pr_number, created_at, merged_at, merge_commit_sha}`；
    - `v_star = {source_name, version, coverage_start, coverage_end, registration_commit}`；
    - `n_req = {value, rule_max_lookback, sigma_window, baseline_lookbacks}`；
    - `holiday_table_meta` ＝ `official_holiday_table_meta(TW)` 的值，尚未接入時為 null；
    - `computed_with = {function: "replay_period", code_commit}`。
  - **凍結日 F 的取得依據**：F ＝ `merged_at` 換算為 Asia/Taipei 的日期。`merged_at` 取自「首次把 `freeze_commit` 併入 origin 上 `base_ref` 分支的那個 PR」，由 GitHub 伺服器記錄。`base_ref` 固定為事先宣告 §4.7「重放期的起訖日」所載的分支，不得在 (a) 時選擇。首次的判準：`freeze_commit` 是 `merge_commit_sha` 的祖先，但不是其第一個 parent 的祖先；所以該 PR 必須以 merge commit 方式併入，squash 或 rebase 併入時判準不成立。不得使用 git 的作者或提交日期，也不得使用 store 時鐘。判準不成立，或凍結 commit 沒有經 PR 併入時，不得進行 (a)。`freeze_evidence` 的核對採執行／判斷分離（章程 §4）：由具 Bash 權限的職能（coordinator 或 devops-sre）以 `gh api` 與 `git merge-base --is-ancestor` 唯讀取得原始回應，逐字存入 `work/`，qa-reviewer 只依存檔判讀；不得為此放寬 qa-reviewer 的權限。
  - **重算核對**：S、E、N_req 只由單一純函式 `replay_period(F, registry, definition_version, rules_version)` 算出。另驗證 `F` 等於 `freeze_evidence.merged_at` 換算的 Asia/Taipei 日期，`freeze_evidence.base_ref` 等於事先宣告所載的分支；不成立就拒絕寫入。DB 登記列寫入時，以檔內的 F 與程式的登記序列重算；與檔內的值不同，或 `v_star` 與程式序列中該版本不同，就拒絕寫入。
- **`forecast_replay_index_check`**（tech-architect 2026-10-18；風控 2026-10-18 v0.15 單項確認第四節 ADR 端第 5 項；事先宣告 §4.7 執行閘門、§6.3「重放期的日曆檢查與查證」「重放的觀察日與決策日」V16-01、V16-05）：重放的起訖日登記、快照、偵測、查證、確認判定、日曆查詢與閘門檢查紀錄，存在同一張表、共用一個序號。只增不改（D-2 第 2 點）。不寫 `forecast_index_check`，也不寫 `forecast_ledger_events`（D-9 第 7 點）。
  - **共通欄位**：
    - `check_id INTEGER PRIMARY KEY AUTOINCREMENT`；
    - `entry_kind ∈ {registration, snapshot, detection, verification, determination, calendar_query, gate}`；
    - `registration_id`：registration 列為 null；其餘列必須指向同表的 registration 列；detection 以後的各列所用快照，一律是 `fetch_outcome = stored` 的那一列，所以序號上一律晚於登記（風控 C40）；
    - `recorded_at`（store 時鐘）。

    各組欄位只在對應的 `entry_kind` 非 null。
  - **registration**：`replay_claim_id`（`forecast_claim_registry` 中 `kind = replay` 的 claim）、`registration_commit`、`registration_file_sha256`、`replay_start`（S）、`replay_end`（E）、`freeze_commit`、`freeze_date`（F）、`v_star_version`。
    - `UNIQUE(replay_claim_id) WHERE entry_kind = 'registration'`：起訖日登記後不得改動。
    - `freeze_commit` 必須是 `registration_commit` 的祖先，`registration_commit` 必須是重放執行時 `code_commit` 的祖先；`forecast_replay.freeze_commit` 必須等於本列的 `freeze_commit`（核對方式同「重放登記檔」，執行／判斷分離）。
  - **snapshot**：`fetch_outcome ∈ {stored, fetch_failed}`。`stored` 列帶 `snapshot_sha256`（指向 `forecast_input_series`，`series_kind = replay_index_bars`）、`snapshot_range_json = {start: S, end: E}`、`bar_count`；`fetch_failed` 列的 `snapshot_sha256` 為 null，`detail_json` 帶例外類別。
    - `UNIQUE(registration_id) WHERE entry_kind = 'snapshot' AND fetch_outcome = 'stored'`：只有一份，存入後不得重新下載（事先宣告 V16-03）。
    - 取數函式取得回應後，在同一個呼叫內寫入 `forecast_input_series` 與 `stored` 列，中間不得有其他讀取或判斷，也不得先檢視內容再決定是否寫入。取數或寫入失敗時寫 `fetch_failed` 列，之後可以再取。取數嘗試次數列入事先宣告 §4.7 揭露。
    - 快照只含日期在 [S, E] 內的列。
  - **detection**：
    - `session_date`；
    - `check_item ∈ {x1_close_unusable, x1_close_involved, x1_non_close, x2_pending, x4}`（X3 不適用）；
    - `date_kind ∈ {weekend, official_holiday, weekday, weekday_holiday_unknown}`：官方休市日表沒有接入、或沒有涵蓋 d 時，平日記 `weekday_holiday_unknown`；
    - `checked_bars_json`、`checked_values_sha256`，各列必須在本 registration 的快照內。

    快照中每一根 bar 都寫一列 `x2_pending`（V15-02）。`UNIQUE(registration_id, session_date, check_item, checked_values_sha256) WHERE entry_kind = 'detection'`。
  - **verification**：`detection_id`；`query_point ∈ {pre_execution, requery_failed, requery_version_change, requery_inconsistent}`；`requery_round INTEGER NOT NULL`（首輪為 0）；`queried_at`；`source_name`；`source_version`；`result`；`source_values_json`；`comparison_json`（規則同 `forecast_index_check`，含 `outside_coverage`）。`UNIQUE(detection_id, requery_round)`。
  - **calendar_query**：`session_date`（[S, E] 內的每一個日曆日）、`requery_round`、`queried_at`、`source_name`、`source_version`、`result`、`source_values_json`。`UNIQUE(registration_id, session_date, requery_round) WHERE entry_kind = 'calendar_query'`。重放的觀察日 O，只由最新一輪 `result = value_obtained` 的列導出（單一函式 `replay_observed_sessions(registration_id)`）。
  - **determination**：`detection_id`；`determination ∈ {close_erroneous, non_close_erroneous, no_error, correct_close_obtained, x2_non_session}`；`basis`；`basis_check_id`；`target_bar_json`；`target_values_sha256`。
    - `x2_non_session` 只能是 `basis = verified`，`basis_check_id` 所指查證列 `result = source_has_no_day`；這是重放中 X2 確認的唯一紀錄。
    - 重放中 X2 不寫 `basis = direct`（V15-02）。
    - `correct_close_obtained` 的 `basis_check_id`，必須是本 registration 閘門所用 `source_name`、`source_version` 的查證列（事先宣告 V16-04）。
  - **gate**：
    - `gate_passed ∈ {0,1}`；
    - `gate_json`：所用的 `source_name`、`source_version` 與該版本的涵蓋範圍；`snapshot_sha256`；[S, E]；待查證觸發數；查證列與日曆查詢列依 `result`、依輪次分列的筆數；不成立的條件；
    - `check_max` ＝ 寫入當下同一 registration 最大的 `check_id`。
  - **寫入規則**：
    - 只有 `app/forecast/replay_checks.py`（D-1）可以寫入本表（AST）。
    - 重查：查詢失敗時，對最新一輪仍為 `query_failed` 的全部列（detection 與日曆日分別計）以同一程序重查；版本在首輪之後改變時，全部重查一輪；X2 查證與日曆查詢不一致時，依事先宣告 V16-05 閘門 (3) 全部重查一輪。同一輪不得只查部分；某一輪不完整時，gate 函式拒絕寫入。
    - gate 列只由單一函式 `check_replay_gate(registration_id)` 寫入。它只讀本表、`INDEX_VERIFICATION_SOURCE_REGISTRY` 與 `forecast_input_series`，不呼叫來源查詢，也不讀任何報酬、標籤或結果（AST）。
    - `gate_passed = 1`，若且唯若事先宣告 §4.7 閘門 (1)～(4) 全部成立：
      - (1) [S, E] ⊆ [`coverage_start`, `coverage_end_at(v, 最新一輪最早的 queried_at)`]；
      - (2) 每一筆待查證 detection 在最新一輪都有查證列，同一 `source_name`、`source_version`，結果都是 `value_obtained` 或 `source_has_no_day`；
      - (3) 日曆查詢完整、版本一致，而且與 X2 查證一致；
      - (4) 依「與重放結果的關係」的寫入驗證。
    - 閘門不成立時照實寫列，不改起訖日。
  - **與重放結果的關係**：`forecast_replay` 與 `forecast_replay_outcome` 的每一列都指向同一列 `gate_passed = 1` 的 gate。寫入驗證：該 gate 列的 `check_max` 等於寫入當下同一 registration 最大的 `check_id`（gate 之後沒有新的偵測或查證）；所用快照的 sha256 等於 gate 的 `snapshot_sha256`（閘門 (4)）。
  - **用途限制**：不屬於 `E_CHANGING_EVENTS`。`views`、API route 與匯出不得讀它；只有 `replay_checks.py`、重放執行函式、`validation.py` 的 §4.7 揭露與稽核工具可以讀（AST）。重放執行之後，不再寫入本 registration 的列。
- **`forecast_replay_outcome`**（tech-architect 2026-10-18；事先宣告 §6.3「重放中確認有誤之後」V16-04）：每筆 `forecast_replay` 恰好一列，與該列在同一個交易內，由重放執行函式寫入。只增不改。
  - **欄位**：
    - `replay_outcome_id INTEGER PRIMARY KEY AUTOINCREMENT`；
    - `replay_forecast_id`（UNIQUE，指向 `forecast_replay`）、`registration_id`、`gate_check_id`、`snapshot_sha256`；
    - `settlement_date`（O 中 T 之後第 h 個觀察日）；
    - `start_price_json`、`end_price_json`：每個都是 `{session_date, close, close_source ∈ {snapshot, independent_source}, bar_values_sha256, detection_ids, determination_check_id, verification_check_id}`。T+h 沒有 bar 時為 `{session_date, close: null, close_source: null, bar_missing: true}`；
    - `realized_log_return`、`realized_z`、`realized_label`、`realized_return`、`hit`、`baseline_hits_json`；
    - `diag_open_based_json`、`diag_last_close`、`index_return_diag`、`diag_unavailable_json`（因非收盤欄位有誤而不可用的診斷欄位）、`window_missing_dates_json`；
    - `mae`、`mfe`、`invalidation_triggered`、`invalidation_first_hit`；
    - `status`、`status_reason`、`void_reasons_json`（`market` 的允許集合）；
    - `recorded_at`。
  - **不得有的欄位**（schema 測試）：`wait_sessions`、`wait_deadline_session`、`settle_source_run_max`、`settle_eval_id`、`supersedes_id`、`correction_job_id`、`correction_causes`、`x2_shift_json`。重放中 k 與 D_5 不適用；O 在判定前已經扣除 X2 確認日，沒有順延。
  - **寫入驗證**（任一項不成立就拒絕寫入）：
    - `close_source = independent_source` ⇔ `determination_check_id` 指向同一 bar（同一 `target_values_sha256`）的 `correct_close_obtained`，而且 `verification_check_id` 等於它的 `basis_check_id`；
    - `close_source = snapshot` ⇒ 該 bar 沒有 `close_erroneous`；
    - `status_reason = index_bar_confirmed_erroneous` ⇒ P(T+h) 的 bar 有 `x1_close_unusable` 的 `close_erroneous`（`direct`），而且沒有 `correct_close_obtained`；
    - `status_reason = missing_bar_after_wait` ⇔ 快照沒有 `settlement_date` 的 bar；
    - `diag_last_close` 非 null ⇔ `status ≠ resolved`；
    - 正確值不得取自其他查證列、日曆查詢列或其他版本（事先宣告 V16-04）。
  - **用途限制**：不寫 `forecast_outcome`。只有 `validation.py` 的 §4.7 報告與稽核工具可以讀；`views` 經 §4.7 報告呈現，不得直接讀（AST）。
- `forecast_gaps(gap_id, session, claim_id, scope_key, reason, detected_at, run_id NULL, UNIQUE(session, claim_id, scope_key))`：`scope_key = '*'` 代表整個 claim。
- **`forecast_gap_audit`**（N-24；tech-architect 2026-10-18；落實風控 2026-10-18 C-22 確認 N24-1「揭露判定進度」）：每次成功的缺日稽核（D-8 第 2 點）一列，記下該次稽核的判定上界。只增不改（D-2 第 2 點）。
  - **欄位**：
    - `audit_id INTEGER PRIMARY KEY AUTOINCREMENT`；
    - `audit_now NOT NULL`：稽核開始、讀任何資料之前讀一次的 store 時鐘；D-8 第 2 點「判定上界」的比較一律用這個值，不另讀時鐘；
    - `range_json`：[D_reg, 最新觀察日]，`{start, end}`；D_reg 為 None 時為 null；
    - `judged_through`：本次已判定的觀察日中最晚的一日；沒有時為 null；
    - `judged_count INTEGER NOT NULL`、`unjudged_count INTEGER NOT NULL`：範圍內已判定、尚未判定的觀察日數；
    - `gaps_written INTEGER NOT NULL`：本次寫入的 `forecast_gaps` 列數；
    - `recorded_at`（store 時鐘）。
  - **寫入者與時機**：只有 `audit.py` 的缺日稽核函式（AST 列舉呼叫點）。與同一次稽核的 `forecast_gaps` 列、A-77 第 10 項的未觀察平日登記在同一個主 DB 寫入交易內，最後寫入、隨該交易 commit。稽核失敗、交易 rollback 時不留任何列，所以本表只記成功的稽核。欄位全部由該函式自行填入，不接受呼叫端傳入（D-2 第 3 點）。
  - **寫入驗證**（任一項不成立，整個稽核交易都不寫入，記 WARNING）：
    - `range_json` 為 null ⇒ `judged_through` 為 null，兩個計數與 `gaps_written` 都是 0；
    - `judged_through` 為 null ⇔ `judged_count = 0`；
    - `judged_through` 非 null 時，它是本次稽核所讀觀察日集合中、範圍內的一日；而且已判定的日子，恰好是範圍內 ≤ `judged_through` 的全部觀察日：這些日子都有 `late_cutoff_at ≤ audit_now`，晚於它的每一日都有 `late_cutoff_at > audit_now`（`late_cutoff_at` 以 D-7.4 的同一個函式、取 T ＝ S 計算）；
    - `judged_count + unjudged_count` ＝ 範圍內的觀察日數；
    - `gaps_written` ＝ 本交易寫入的 `forecast_gaps` 列數，而且每一列的 `session` ≤ `judged_through`；
    - `judged_through` 早於前一列的值時（例如觀察日集合因 X2 確認而回溯縮小，A-77 第 11 項），記 WARNING，照實寫入，不拒絕。
  - **讀取**（AST 列舉呼叫點；讀取一律經 `store.py`）：
    - `views.py`：`GET /api/forecast/status` 的 `last_gap_audit_at` ＝ `audit_id` 最大一列的 `audit_now`，`gap_judged_through` ＝ 同一列的 `judged_through`；沒有任何列時兩者都是 null（D-8 第 5 點）。API route 原樣回傳；`app/api/**` 與前端不得以 `late_cutoff_at`、`forecast_gaps` 或時鐘導出這兩個值（AST）。
    - `recorder.py` 的編排函式：D-7 第 2 點「本次缺日稽核已 commit」＝ 本次執行的稽核寫入了本表的一列，以稽核函式回傳的 `audit_id` 確認。
    - `validation.py`：缺日率（失效條件 F-3）與任何以缺日界定的分母，只計 ≤ 所用列 `judged_through` 的觀察日（D-8 第 2 點 N-24「比率不因尚未判定而偏低」）。驗證快照所用的列是本次執行稽核寫入的那一列，它的 `audit_id` 記入該 snapshot 的 `stats_json`（鍵 `gap_audit_id`），以存下的值重算時結果逐位相同。
    - 稽核工具。
  - **限制**：不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定；匯出不得讀它。
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
     3. D-9.2 的大盤結算路徑（v0.14：每次結算評估讀一次，必要時強制重抓一次，結果存入 `forecast_input_series`，見 D-9.2）；
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
   - （N-23）`max_instances=1` 時，前一次執行尚未結束，新的觸發點（含 23:10 重試）會被略過、不排隊。`EVENT_JOB_MAX_INSTANCES`、`EVENT_JOB_MISSED` 都要有 listener 記 WARNING，內容帶被略過的觸發時刻；告警規格依 ADR-0026（devops-sre，後續追蹤清單 N-23 (1)）。結算評估是否啟動只依 D-7.7 期限，不得以剩餘時間的估計決定。
2. **執行順序**：記錄 → 結算 → 缺日稽核 → 晚到掃描與更正作業（有觸發時，D-3「晚到資料的觸發」第 1 點）→ 驗證快照 → plan（政策表）。T 的 plan 一律使用 `computed_for_session = T` 的 daily snapshot，也就是 T+1 開盤前畫面上用的同一份（r1，A-4）。
   - （v0.14；風控 2026-10-18 B-3 回送確認）結算評估失敗（含 D-9.3 `span_sessions` 的例外與 D-9.2「R 倒退」）時，記 WARNING，本次執行仍照順序執行缺日稽核，不得略過：依 A-77 第 10 項，結算讀取範圍以外的日期由缺日稽核登記。
   - （N-23；tech-architect 2026-10-18；dev-lead 查證方案 A）**步驟隔離**：
     - 各步在單一 job `forecast_record` 內，由 `recorder.py` 的單一編排函式依序呼叫。
     - 一步失敗（拋出 `Exception`，或回傳非成功的結果）時，記 WARNING，不中止後續步驟；後續步驟是否執行，只依下一子點的前置條件。
     - 結算失敗的例外只在編排函式中、`run_settlement_evaluation()` 呼叫的外面接住；接住時，該函式的主 DB 交易已 rollback（D-9.2 ⑦）。
     - 不得拆成多個 APScheduler job（要改動須先修訂 D-7.1）。
     - D-7.7 期限已到、結算評估沒有啟動時，視同結算失敗：記 WARNING，缺日稽核照常執行。
   - （N-23）**前置條件**：
     - 缺日稽核與更正作業：不依賴前面任何一步是否成功。
     - 驗證快照：以下三項都成立才寫：本次執行的結算評估已 commit（寫入了 `forecast_settle_eval` 的一列）；本次缺日稽核已 commit；本次晚到掃描與更正作業已完成（沒有觸發因而不啟動，或已寫入 `forecast_correction_job_end`）。任一項不成立，本次不寫驗證快照，記 WARNING，也不寫任何 fail-closed 列。理由：snapshot 有 UNIQUE 而且不重算（D-11.2），寫入的落後或 gated 列，之後重試成功也蓋不掉；缺日稽核失敗時寫快照，缺日率（失效條件 F-3）與依缺日界定分母的統計會偏低；更正作業未完成時寫快照，會把已知待 supersede 的結算（例如收盤已確認有誤）計入 T 的驗證統計（風控 2026-10-18 C-22 確認）。
     - plan：`computed_for_session = T` 的 daily snapshot 存在時才寫；不存在時本次不寫 plan，記 WARNING，不得改用較早的 snapshot。
     - 已有同一 T 的快照或 plan 列時，視為略過，不是錯誤。
     - 23:10 重試與啟動補跑依同樣的條件補寫。
   - （N-23）**持續失敗期間**：
     - 沒有 T 的 snapshot 時，展望依 D-11.4 既有的「沒有 snapshot」規則處理。
     - 沒有 T 的 plan 時，任何面（`PLAN_OUTPUT_SURFACES` 全部，含 API）都不得把較早的 plan 當成 T 的 plan 呈現；API 也不得以較早的 plan 回填 T。呈現方式尚未定義（狀態句、是否並列較早的 plan 與它的資料日期），由 PM 評估、creative-lead 起草、風控審查（後續追蹤清單 N-25）。核可前，plan 衍生內容（含較早的 plan，以及 `position_action`、`reasons`、`pending_triggers`、`add_conditions`、`entry_conditions`、`outlook_refs` 與「最需要處理」的排序與成員）一律不渲染；免責句與時間戳句照常常駐，時間戳句只標示該畫面實際渲染內容的資料日期，不得把 T 代入任何 plan 相關位置（fail-closed）。
     - 這是 plan 渲染上線前的阻擋項（比照後續追蹤清單 C-2）：N-25 核可之前，plan 渲染不得上線，所以上線後不會出現「plan 區塊空白、沒有說明」的畫面。
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
   - （N-3；A-77 第 12 項 (h5) 的計數來源）**(i) 成立、(iii) 不成立時：**
     - (i) 成立時，(iii)、(iv) 都要判定，不得因為其中一項不成立就略過另一項。
     - 記 WARNING，寫入 `session_calendar_conflict`，`origin = candidate_t_x2`。
     - payload：
       - `session_date`、`origin`；
       - `x2_event_id`：使 (iii) 不成立的那筆 `x2_confirmed_non_session` 事件；
       - `evidence`：取該 X2 事件的 `trigger`；`trigger` 為 null（`basis = verified`）時為 `independent_source_absent`；
       - 使 d ∈ (i) 的 ok run 中 `run_id` 最小者的 `run_id`、`recorded_at`（比照第 12 項）；
       - `detected_by_run_id`：該次 recorder 已寫入 `forecast_run` 時填入，否則為 null。
     - payload 由寫入函式自行填入，不接受呼叫端傳入。
     - 寫入函式在同一個交易內驗證，任一項不成立就拒絕寫入：
       - `x2_event_id` 指向一筆已存在、`kind = x2_confirmed_non_session`、`session_date` 相同的事件；
       - `evidence` 和該事件的 `trigger` 相符（null ⇔ `independent_source_absent`）；
       - 重算後 d ∈ `final_sessions()`。
     - 同一個 (`session_date`, `origin`) 只寫一次；同一個 d 之後再成為候選 T，不另寫。
     - 和 `origin = candidate_t` 互相獨立：(iv) 也不成立時（`basis = direct`，d 是週末或官方休市日），兩筆都寫。§4.2 依 origin 分列，各自以不同的 `session_date` 計，不跨 origin 去重。
     - 不寫缺日列（d 不是觀察日），不改 d 的觀察日身分，不觸發 §6.4。歸入 `E_NEUTRAL_EVENTS`（沿用 `session_calendar_conflict` 的歸類）。程式不得把它標為已解決。
   - **(i) 成立而且 (iv) 不成立時**：候選 T 依 (i) 必定 ∈ D-8.1 (i)，所以這必然是 A-77 第 5 項的同一種證據矛盾。
     - 記 WARNING，寫入 `session_calendar_conflict`（`origin = candidate_t`）；
     - 一併計入 A-77 第 5 項的揭露與根因查證。
   - (iv) 的「週末」部分受 A-77 第 9 項（F-8）約束：查證若發現週末交易日，(iv) 與 A-77 第 2 項的週末部分同一批修訂，並送風控。
   - （A-96″，K-10，補定義（收緊））**官方休市日表的單一定義**：
     - （A-96″，K-10；N-9 改寫）本 ADR 凡提及「已接入（而且涵蓋 d 的）官方休市日表」之處，包括 A-75 (iv)，以及 A-77 第 2、4、5、7、10 項（含第 7 項 `trigger = official_holiday` 的寫入驗證、第 7 項與第 10 項 payload 的 `holiday_table`、第 10 項的 `holiday_coverage` 與偵測條件），都和 ADR-0028 `OfficialSessionCalendar`（T1-13）使用同一份來源、同一個函式定義，涵蓋年度也相同（ADR-0028 VS-5）。超出涵蓋年度時，各處同樣視為沒有官方休市日。日後新增的引用處同樣適用；本句的列舉只是提示，不是範圍。
     - 這個函式只定義一次，暫定為 `official_holidays(market, year) -> frozenset[date] | None`。None 表示該年不在涵蓋範圍內，或尚未接入。名稱與所在模組由 T1-13 決定，但要遵守 ADR-0028 CS-1、CS-19、CS-25 的 import 限制。
     - A-75 (iv)、A-77、`OfficialSessionCalendar` 都只呼叫它；休市日清單不得出現第二份（grep／AST，比照 ADR-0028 CS-21、CS-25）。
     - （N-9）**表的中繼資料也只有一個來源**：和 `official_holidays` 同一個模組，定義 `official_holiday_table_meta(market) -> {version, coverage_start, coverage_end} | None`（暫定名；名稱與模組由 T1-13 決定，import 限制同上）。
       - None 表示尚未接入。`coverage_start`、`coverage_end` 是 VS-5 涵蓋年度的第一天與最後一天，由同一份來源導出，不另存第二份。
       - 不變式（性質測試）：`official_holidays(market, y)` 為 None，若且唯若 meta 為 None，或 y 不在 [`coverage_start.year`, `coverage_end.year`] 內。
       - A-77 第 7、10 項 payload 的 `holiday_table` 只取自 meta。
       - 第 10 項 `holiday_coverage` 依序判定：meta 為 None → `table_absent`；`official_holidays(market, d.year)` 為 None → `not_covered`；回傳的集合不含 d → `listed_as_trading_day`。集合含 d 時，d 依定義不是未觀察平日，不得寫入。
       - grep／AST：寫入 `holiday_table`、`holiday_coverage` 或 `trigger = official_holiday` 的程式，只呼叫這兩個函式，不得另讀來源，也不得另存清單（比照 ADR-0028 CS-21、CS-25）。
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
        - payload：`session_date`、`evidence ∈ {weekend, official_holiday, independent_source_absent, registered_unobserved_weekday}`、`origin ∈ {x2_check, candidate_t, candidate_t_x2, post_x2_final_run, post_unobserved_backfill}`（`candidate_t_x2` 依 N-3 加入，見 A-75 (iii)）（`post_unobserved_backfill` 依風控 2026-10-18 Q3-7 加入，見第 10 項）、受檢 bar 的參照。`independent_source_absent` 只用於 `origin ∈ {post_x2_final_run, candidate_t_x2}`。`registered_unobserved_weekday` 只用於 `origin = post_unobserved_backfill`（見第 10 項）。
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
      - （C-22）`verification_ref` 是 `forecast_index_check.check_id`。所指的列必須是 `entry_kind = verification`、`result = source_has_no_day`，它的 detection 列 `check_item = x2_pending`、`x2_case = set_iii_only`、`session_date = d`；不成立就拒絕寫入（FL-19 (c)③ 加格）。
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
   9. **F-8（凍結前，待 data-engineer 查證）**：「週末」作為正面休市證據，前提是前瞻期沒有週末交易日（重放期依事先宣告 §6.3「重放期的日曆檢查與查證」V15-02，週末不作直接確認，不受本項約束）。〔剩餘待決項註：data-engineer 2026-10-18 查證結論為 repo 內無法查證，需 CEO 本機代跑探測指令 §6.2；凍結前狀態以事先宣告 §9.2 與風控 v0.13 審查 R-4 為準〕
      - 查證若發現週末交易日：官方日曆列為交易日的週末，不構成正面休市證據；官方表沒有涵蓋的期間，週末的大盤列只能列為異常待查證。這時第 2 項「週末一律不得經 (ii) 成為觀察日」的週末部分要和事先宣告同批修訂，並送風控。
      - 查證若沒有發現：把查證依據與涵蓋期間寫進本點與事先宣告。
   10. **未觀察平日**（風控 2026-10-17 疑義裁定回送 Q-3；A 案，風控 2026-10-18 C9-7 與 Q-3 提案確認）：d 同時滿足以下各項：是平日（Asia/Taipei 週一至週五）；不是已接入、而且涵蓋 d 的官方休市日表所列的休市日；d ∉ (i)；d ∉ (ii)；而且已經有晚於 d 的觀察日。
      - **偵測**：缺日稽核以單一函式 `unobserved_weekdays(start, end)`，逐日檢查 [D_reg, 最新觀察日] 內的平日。這裡列舉平日只是為了產生候選，不得用來推定觀察日（FL-19 不變）。
      - **登記起點 D_reg**（v0.14；tech-architect B-3 回送，風控 2026-10-18 B-3 回送確認）：D_reg ＝主 DB 中全部 `forecast_record` 的 T 的最小值，不分 claim、`trigger`、`late`、`supersedes_id`；沒有任何紀錄時為 None，這時不登記。由單一唯讀查詢 `ledger_registration_start() -> date | None` 導出，每次呼叫重新導出，不存成水位。D_reg 不晚於任何 claim 的 D_v（D-14），所以 [D_reg, 最新觀察日] 是原範圍 [D_v, 最新觀察日] 的超集合。改用 D_reg 的理由：D_v 依 claim 而異；逾時紀錄與 on-demand 紀錄依 D-9 第 6 點照常結算，它們的 T 可能早於 D_v；整檔還原也可能使 D_v 移後（D-14 N-5）。`forecast_replay` 不在 D_reg 的導出範圍（重放的涵蓋見後續追蹤清單 N-22a、N-22b）。
      - **登記先於使用**：任何讀取觀察日集合（`observed_sessions()`）、並寫入主 DB 的作業（排程結算、更正作業、缺日稽核、X2 確認寫入），在讀取之前，要在同一個寫入交易內先呼叫 `unobserved_weekdays`，完成登記：登記範圍是 [D_reg, 最新觀察日] 與該作業讀取觀察日集合的日期範圍的交集；判準中的 (i)、(ii)、X2 確認日、官方休市日表與「晚於 d 的觀察日」，一律取該作業讀取觀察日集合時所用的同一份輸入，不另行讀值；D_reg 在同一個寫入交易內導出（結算評估見 D-9.2 執行順序 ②～④；更正作業的市場 DB 部分以該作業的 `market_scan_to` 界定）。缺日稽核每次執行都讀取並登記整個 [D_reg, 最新觀察日]。每次都涵蓋整個範圍，不得只從上次登記的終點續掃。作業讀取範圍以外的日期，由缺日稽核登記（D-7 執行順序：結算 → 缺日稽核；結算失敗時缺日稽核照常執行，見 D-7 第 2 點）；缺日稽核未成功執行時，這些日期延到下一次成功執行才登記。期間任何讀到這些日期的作業，仍依本句先行登記，所以判定不受影響；只是 §4.2 ① 在該期間少列這些日期，缺日稽核的執行時點以 `GET /api/forecast/status` 的 `last_gap_audit_at` 揭露（風控 2026-10-18 B-3 回送確認：補定義（兩面），放寬面是讀取範圍以外的日期延到缺日稽核才登記）。登記失敗時，該作業不寫入（fail-closed），記 WARNING。
      - **登記先於使用的適用範圍**（N-21；tech-architect 2026-10-18）：
        - 「該作業讀取觀察日集合的日期範圍」：結算評估為快照範圍（D-9.2 ④）；更正作業為 `view_range_json`（D-9 第 5 點）；缺日稽核為 [D_reg, 最新觀察日]。
        - X2 確認寫入本身不讀觀察日集合（第 4 項），依上句交集為空，本身不登記，也不呼叫 `unobserved_weekdays` 與 `ledger_registration_start()`（AST）。在結算評估 ③ 寫入時，同一份輸入的登記由 ④ 完成（D-9.2）。
        - recorder 以 `observed_sessions(as_of=cutoff(T))` 讀觀察日，不屬於上句的作業，不呼叫 `unobserved_weekdays` 與 `ledger_registration_start()`（AST）。理由：(1) 登記當下 d ∉ (i) ∪ (ii)，觀察日集合不因登記與否改變；(2) `as_of` 視圖是過去時點的輸入，以它登記，會把之後才進入 (i) 或 (ii) 的真交易日永久登記成未觀察平日。
        - recorder 寫入的 X2 確認與 `forecast_index_check` 列，依第二子點。
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
      - (h5) 的 `inputs_not_ready` 不寫缺日列（d 不是觀察日）。這類 d 屬於 (i)，不是未觀察平日；計數來源由 tech-architect 另定（風控第九批 S9-3，suggested）。〔已決：計數來源為 `session_calendar_conflict`（`origin = candidate_t_x2`），見 A-75 (iii)（N-3）〕
      - N-1 未核可不得進入 D_v（登記於待決事項）。〔已決：甲案已核可（風控 2026-10-17 第九批 TA 提案確認；風控 2026-10-18 v0.12 審查第四節），N-1 不再擋 D_v〕
2. **稽核**：對每個觀察日 S、每個已登記的前瞻 claim，若沒有 `late=0` 的排程紀錄，就寫一列 `forecast_gaps`。
   - （N-24；tech-architect 2026-10-18）**判定上界**：
     - 觀察日 S 只在稽核當下的 store 時鐘 ≥ S 的 `late_cutoff_at` 之後，才判定要不要寫缺日列，`reason` 依當時的狀態判定。`late_cutoff_at` 以 D-7.4 的同一個函式、取 T ＝ S 計算。
     - 在這之前不寫，也不寫任何暫定列；這時 S 只是尚未判定，`last_gap_audit_at` 照常前進。
     - 理由：S 的 `late=0` 紀錄只可能在 `late_cutoff_at` 之前寫入。過了這個時點，判定才是終局的。例如 22:10 記錄失敗、23:10 重試成功時，S 沒有缺日列。
     - A-77 第 10 項的登記不受本點影響。
     - 另一面：S 的缺日列晚約一天才出現，所以 F-3 逾時率、TG-b、TG-c 對 S 的反映也晚約一天。
     - **比率不因尚未判定而偏低**（風控 2026-10-18 C-22 確認）：缺日率（失效條件 F-3）的分子與分母，只計已判定的觀察日，也就是 S 的 `late_cutoff_at` 已過、而且已經過一次成功稽核的日子。D-11 第 6 點 F-3 逾時率以排程紀錄計；尚未判定的 S，不得以「沒有缺日列」計入任何以缺日界定的分母。所以本點只延後反映，不降低比率。
     - **揭露判定進度**：`GET /api/forecast/status` 另回傳 `gap_judged_through`，也就是最近一次成功的缺日稽核已判定的觀察日中最晚的一日；沒有時為 null。由寫入端記錄（存放處由 tech-architect 定），不得由前端或 API 以 `last_gap_audit_at` 推算。`last_gap_audit_at` 不再代表「稽核當日已判定」。TG-b、TG-c 或任何缺日計數若在畫面上呈現，都要讓使用者看得出統計只到 `gap_judged_through`，文案另經 creative-lead 起草、風控審查。〔已決：存放於 D-3 `forecast_gap_audit`（N-24；tech-architect 2026-10-18）〕
     - 殘餘情形：官方日曆在稽核判定之後變動、使 S 的截止線延後時，依 K-12 送風控。
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
   - `GET /api/forecast/status` 回傳 `last_gap_audit_at`，以及 `last_settle_eval_at`（最後一筆 `forecast_settle_eval` 的 `started_at`；沒有任何列時為 null），以及 `gap_judged_through`（D-8 第 2 點 N-24）（v0.14；風控 2026-10-18 B-3 回送確認）。這三個值若要在畫面上呈現，文案另經 creative-lead 起草、風控審查。
   - （N-24）`last_gap_audit_at`、`gap_judged_through` 都取 D-3 `forecast_gap_audit` 中 `audit_id` 最大的一列（分別是 `audit_now`、`judged_through`），兩個值出自同一列；沒有任何列時都是 null。所以 `last_gap_audit_at` 是最近一次**成功**的缺日稽核的稽核時刻，失敗的嘗試不會讓它前進。

### D-9 結算與作廢
1. **觸發條件**（三者都要成立；v0.14 V14-01 改以判定視圖界定，見第 2 點）：
   - 判定視圖中已觀察到第 h 個交易日 T+h（觀察日依第 2 點「觀察日」）；
   - 判定視圖中有可用於結算的 T+h 資料。個股、大盤、族群各自的定義依事先宣告 §6.3「觸發」（v0.14 V14-01；大盤一句依風控 2026-10-18 v0.14 審查 R14-2）；只有定案前 run 的 bar 不算可用（A-78；後續追蹤清單 N-16）。沒有時不寫入任何 outcome，該筆等待，期限見第 3 點 `missing_bar_after_wait`；
   - `valid_until_session` 已過（AV-18）。
   - 本點只規定結算端。預測端（特徵、label、σ_d(T)、`threshold_snapshot`）仍只用 `recorded_at ≤ cutoff(T)` 的資料（D-4），不受影響。
2. **結算資料與判定視圖**（v0.14 V14-01；風控 2026-10-18 v0.14 審查 R14-4、R14-5 ①）：每次結算評估由 `app/forecast/settlement.py` 的單一函式 `run_settlement_evaluation()`（D-1）執行。該次評估結算所讀的一切資料，都以它的**判定視圖**為準；判定視圖的界定值存在 `forecast_settle_eval`（D-3）。以存下的視圖重算，結果必須逐位相同。
   - **市場 DB**（個股與族群成員的日線、除權息事件）：讀一次 R ＝ `MAX(run_id)`，以 R 界定（D-3 `settle_source_run_max`，R14-4）。只取 `run_id ≤ R`、ok run 的列；定案下限依 A-78，來源優先序與 D-4.1、D-4.2 的 PIT 規則照舊；不得用 `_hindsight_view`。界定只比較序號，不拿 `recorded_at` 與任何時刻比較。
   - **大盤 `^TWII` bar**：不得依賴 `price_bars_cache` 的當前值。該表以 `(symbol, market, trade_date)` 為主鍵 upsert，`as_of`、`fetched_at` 每次覆寫，沒有首次寫入紀錄，事後無法重建評估當下的版本（data-engineer 2026-10-18 查證第 5 項 C【事實：`app/data/cache.py`】）。
     - 每次評估經 `app.services.index` 讀一次大盤列，每列帶 `as_of`、`fetched_at`、`source`（D-7.3），只留 `is_final_bar(row, now=…)` 為真的列（A-75；`now` 是讀取前的 store 時鐘讀值）。快照範圍內的全部列寫入 `forecast_input_series`（`series_kind = index_bars`；每列帶上述三欄並納入雜湊，以內容雜湊去重）；`content_sha256` 記入 `forecast_settle_eval.index_series_sha256`，所用的 `now` 記入 `index_final_now`。
     - 該次評估凡用到大盤 bar 的判定，一律只讀這份快照：觀察日的 (ii)、可用於結算的大盤 T+h 資料、P(T) 與 P(T+h) 收盤、事先宣告 §6.3「大盤指數序列」的 X1～X4 偵測。
     - **評估集合與快照範圍**（N-21 風控 suggested；tech-architect 2026-10-18）：
       - ② 在讀大盤列之前，以一個主 DB 唯讀查詢讀一次「沒有任何 `forecast_outcome` 列的 `forecast_record`」，得到本次的評估集合 U（不分 `trigger`、`late`）。
       - 快照範圍 ＝ [U 的 T 的最小值, 評估當日（Asia/Taipei）]；U 為空時為 [評估當日, 評估當日]。記入 `view_range_json`。U 的筆數、排序後 `forecast_id` 串的 sha256，記入 `eval_set_count`、`eval_set_sha256`。
       - ⑥ 恰好判定 U，不在 ④ 另讀未結算集合。② 之後才寫入的紀錄（例如 on-demand POST）不屬於本次評估：不寫 outcome，不列入 `waiting_json`，由下一次評估納入。這依寫入時點機械決定，不看預測內容；等待以觀察日計數，所以不會讓任何預測少等。
       - ④ 在寫入交易內驗證：U 的每一筆仍然沒有 outcome 列。不成立時，整個評估不寫入，記 WARNING。
       - U 為空時，評估照常執行 ③、④、⑤，寫一列 `forecast_settle_eval`（`waiting_json = []`）。
     - **強制重抓**（比照 D-7.3 (ii)）：快照範圍內，只要有任一 session d 屬於以 R 為界的 `final_sessions()`、而大盤在 d 沒有 `is_final_bar` 列，就經 `app.services.index` 強制重抓恰好一次（寫入仍經 `service.py`），重讀時鐘與大盤列之後才建快照。重抓之後仍然沒有，d 的大盤資料在本次評估就算不可用，依第 1 點等待。重抓條件只看上述日期集合，不看預測、label 或結果；不得對個別預測或個別日期另行重抓（事先宣告 §6.3「觸發」判定視圖一點的失效條件，風控 R14-7）。`index_refetch` 記 `not_needed`、`refetched` 或 `refetch_failed`（重抓拋例外時記這一值，本次以重抓前讀到的列建快照）。
   - **主 DB 的確認與查證紀錄**：在 `run_settlement_evaluation()` 的主 DB 寫入交易內讀一次 E 與 V，判定只用序號 ≤ E、≤ V 的紀錄。
     - E ＝ `forecast_ledger_events` 的 `MAX(event_id)`，涵蓋 X2 確認、未觀察平日、`session_calendar_conflict`。
     - V ＝ `forecast_index_check` 的 `MAX(check_id)`；查證紀錄與 X1、X3、X4 確認判定紀錄共用這個序號（D-3，C-22）。
     - E、V 和該次評估的全部寫入在同一個主 DB 交易內，交易期間不會插入其他列。
     - 查證紀錄與確認判定紀錄存於主 DB 的 `forecast_index_check`（D-3；只增不改、以 `INTEGER PRIMARY KEY AUTOINCREMENT` 為序號；C-22 於 2026-10-18 定案）。③ 寫入的列都早於 ④ 讀 V，所以本次評估當場的查證與判定都在判定視圖內。
   - **觀察日**：以 `observed_sessions(*, view)`（D-1）取得。
     - (i) 只取 `run_id ≤ R` 的 run（經 `final_sessions()`）；(ii) 只取大盤快照；X2 確認日與已登記的未觀察平日只取 `event_id ≤ E` 的事件。
     - 快照範圍內的結果存入 `forecast_settle_eval.observed_sessions_json`。
     - T+h、D_5、`wait_sessions`、第 3 點的 g，一律由這份清單與 `event_id ≤ E` 的 `unobserved_weekday` 事件導出。
   - **執行順序**（同一個函式內依序執行，不得調換）：
     ① 讀 R。之後不再讀市場 DB 的 `MAX(run_id)`。
     ② 讀時鐘與大盤列，需要時強制重抓一次，建立大盤快照。之後不再讀大盤列。同一步讀取官方休市日表一次（`official_holiday_table_meta` 一次，`official_holidays` 每個涉及的年度各一次；未接入時為 null），之後本次評估不再讀；③ 的 X2 確認寫入（本身不登記未觀察平日，見 A-77 第 10 項「登記先於使用的適用範圍」；休市日表仍用這一份，因為 payload 的 `holiday_table` 與 `trigger = official_holiday` 要用到它）、④ 的登記、`span_sessions`，以及 `forecast_settle_eval.holiday_table_json`，都使用這一份（風控 2026-10-18 B-3 回送確認）。
     ③ 以 R 與快照執行事先宣告 §6.3「大盤指數序列」的偵測，以及「查證程序」①、②。查證紀錄與 X2 確認照既有規則寫入：每一筆查證紀錄與由它導出的確認判定或 X2 確認同一個交易；不同查證紀錄、直接確認的 X2，各自一個交易（D-3 `forecast_index_check`「寫入者與時機」）。寫入規則依 D-3 `forecast_index_check`：快照內每根 bar 的偵測與 ① 查證；獨立來源已接入時，對全部待查證列做 ②；來源版本第一次出現時，以 ③ 取代當次的 ②。
     ④ 開啟主 DB 寫入交易。依 A-77 第 10 項「登記先於使用」，以 R、大盤快照，以及 ② 讀取的同一份官方休市日表，完成 [D_reg, 最新觀察日] ∩ 快照範圍內的未觀察平日登記（D_reg 在本交易內導出；最新觀察日以同一份輸入判定），之後讀 E、V。快照範圍以外的日期，本次評估沒有 (ii) 的依據，也不讀它們的觀察日，不在本步登記（由缺日稽核登記）。每筆未結算預測的 T 都不早於快照範圍的起點，也不早於 D_reg，所以結算窗內符合判準的日期都在本步登記。`span_sessions` 檢查 A-77 第 10 項判準時，使用 ② 讀取的同一份官方休市日表，不另行讀取。官方休市日表接入時，本步與 V14-03 的偵測範圍同批送風控。
     ⑤ 寫入大盤快照與 `forecast_settle_eval`。
     ⑥ 對評估集合 U（②）的每一筆判定：結算或作廢的寫入 `forecast_outcome`；等待的記入 `waiting_json`。
     ⑦ commit。任一步失敗，整個交易不寫入，記 WARNING，由下一次執行完整重跑。
   - **全量評估**：一次評估涵蓋全部未結算的預測，不逐筆挑選，也不由人工對個別預測觸發。`run_settlement_evaluation()` 的簽章不接受預測清單、R、E、V、視圖或判定結果（AST）。等待與否只依可用的 T+h 資料是否存在，不讀 label、`hit`、基準命中或任何驗證統計（AST 列舉 import，比照第 3 點「判定順序」）。
   - **不切分**：結算評估是一個主 DB 寫入交易，不依 D-7.7 在範圍之間切分。D-7.7 的期限已到時，本次不啟動評估，由下一次執行（23:10 重試、啟動補跑或次一交易日）完整執行。等待以觀察日計數，不以評估次數計，所以略過的評估不會讓任何預測少等。
   - **R 倒退**：R 小於前一筆 `forecast_settle_eval.market_run_max` 時，視為市場 DB 被還原：記 WARNING，本次不寫入（fail-closed），直到 devops-sre 依 ADR-0026 D-9.4 處理並修訂本點（比照 D-3「晚到資料的觸發」第 8 點）。
   - **失效條件**（風控 R14-7）：新增任何回填路徑（含人工補跑擷取）之前，須經 tech-architect 出 ADR 並送風控；回填只能以 session 或全市場為單位，不得依預測或標的挑選。屆時重查本點與 §4.2「等待後結算」。
   - **預測端不受影響**：D-4 的 `cutoff(T)` 與 `observed_sessions(as_of=cutoff(T))` 照舊。
3. **結算窗**：觀察交易日 T+1～T+h 的日線，報酬自 T 收盤起算。作廢原因（`status_reason`）：
   - `missing_bar_after_wait`：沒有可用於結算的 T+h 資料，至判定視圖中已觀察到 D_5 的評估仍無（v0.14，V14-01） → `unresolvable_missing_data`
     - 期限：判定視圖中已觀察到 T+h 之後第 5 個觀察交易日 D_5 的第一次評估（以序號判定，不比較時鐘；D_5 以該次評估可見的觀察日判定，寫入該列）。D_5 寫入 `wait_deadline_session`，等待觀察日數寫入 `wait_sessions`（D-3）。期間任一次評估的判定視圖中出現可用的 T+h 資料，就在該次評估結算；等待期間才寫入的資料可以使用。所以等待期滿時，每一筆都恰為 `resolved` 或作廢之一（事先宣告 §9.2 O-1 (a)）。
     - 判定視圖內、因定案下限（A-78）或品質檢查而不可用的 bar，在判定當下已經評估過，該列依上文落入結算或作廢之一，不屬於晚到。之後才寫入的定案 run（`run_id` 大於該列的 `settle_source_run_max`）依 D-3「晚到資料的觸發」判定，只進 `forecast_void_late_diag`（風控 v0.13 審查 R-4 (b)；v0.14 審查 R14-3）。
     - `diag_last_close` 以同一個判定視圖計算。
   - `basket_coverage_below_90`：族群籃子排除 T+h 沒有可用 bar（停牌等）、因子不可用或符合分割判準的成員後，覆蓋 < 90%，至判定視圖中已觀察到 D_5 的評估仍是如此（v0.14，V14-01、V14-02） → `unresolvable_missing_data`
     - 覆蓋率以 T 日籃子的成員數計。因為 T 日等權建倉，這等同 T 日權重；不得用 T+h 漂移後的權重或市值權重（r1，A-11）。
     - （v0.14，V14-02）三種原因合併計算，每個成員只計一次。以整數判定：x ＝ 被排除的成員數，N ＝ T 日籃子的成員數，10x > N 即覆蓋 < 90%；不以浮點比值判定。
     - （v0.14，V14-01）族群在 claim 層等待：某次評估的判定視圖中覆蓋 ≥ 90%，就在該次評估結算；至判定視圖中已觀察到 D_5 的評估仍 < 90%，就記此值，`diag_basket_with_excluded` 以同一個判定視圖計算。被排除的成員與原因記在 `basket_excluded_members_json`（D-3）。
   - `split_or_reduction_suspected`：在判定視圖中（第 2 點），以套用可用除權息因子後的序列（只含判定視圖中通過 A-78 定案下限的 bar），取結算窗 [T, T+h] 內對象有 bar 的觀察日 T ＝ d_0 < d_1 < … < d_m。任一相鄰對 (d_{j−1}, d_j) 的簡單報酬 r_j ＝ P\*(d_j) ÷ P\*(d_{j−1}) − 1，大於上界 (1 + c)^{g_j} − 1，或小於下界 (1 − c)^{g_j} − 1，就成立（c ＝ `SPLIT_SUSPECT_ABS_RETURN`，台股一般漲跌幅限制 10% 加容差 1%，凍結在 dirdef；不新增常數）（推定，不是確認的事件） → `excluded_corporate_action`（r1，A-11；v0.14 V14-03 擴及跨越缺 bar 日的相鄰對，依事先宣告 §6.3 作廢規則第 3 點）
     - （v0.14，V14-03；風控 R14-13）**g_j**：定義引用事先宣告 §6.3 作廢規則第 3 點。g_j 是 (d_{j−1}, d_j] 內判定視圖的觀察交易日數（D-8.1 第 3 項，不含 X2 確認日），加上未觀察平日（A-77 第 10 項）的日數。
       - 在判定視圖中，未觀察平日指 `event_id ≤ ledger_event_max` 的 `unobserved_weekday` 事件所登記的日期。依「登記先於使用」，判定當下符合 A-77 第 10 項判準的日期，在讀 E 之前都已登記。登記之後因補寫進入 (i) 或 (ii) 的日期，依 A-77 第 10 項「固定排除」仍不是觀察日，但同樣計入 g（它可能是交易日，理由同事先宣告該點）。
       - g_j 由 `scoring.py` 的單一函式 `span_sessions(d_prev, d_cur, *, view)` 計算，只讀判定視圖。g_j ＝ 1 即原本「相鄰兩個觀察日都有 bar」的情形。
       - 結算窗內若有日期符合 A-77 第 10 項判準、卻沒有 `event_id ≤ ledger_event_max` 的 `unobserved_weekday` 登記事件（例如落在登記範圍之外），`span_sessions` 拋例外，該次評估不寫入（fail-closed），記 WARNING；不得把該日當成 0 步略過（風控 2026-10-18 v0.14 單項確認）。
       - （說明；風控 2026-10-18 B-3 回送確認）本例外是不變式的守衛，不是預期中的營運狀態：依 A-77 第 10 項與 D-9.2 執行順序 ②、④，結算評估在讀 E 之前、同一個交易內，以同一份輸入完成 [D_reg, 最新觀察日] ∩ 快照範圍的登記，每筆未結算預測的結算窗都在此範圍內；所以本例外只在登記範圍或輸入與判定不一致時成立，屬於程式缺陷或本條未涵蓋的情形。更正作業重算時呼叫同一個函式，同樣適用：該作業不寫入。
         - 例外訊息與 WARNING 至少帶：符合判準卻未登記的 `session_date` 清單、受影響的預測筆數、D_reg、快照範圍（更正作業為重查範圍與 `market_scan_to`）。
         - 觸發後只有一條處理路徑：查出根因，修正程式或本條，送風控。不得捕捉本例外後繼續寫入；不得提供以呼叫端或操作者指定日期或 payload 寫入 `unobserved_weekday` 的 CLI、API 或工具（A-77 第 10 項「payload 由寫入函式自行填入」）。
     - （v0.14，V14-03；風控 R14-14）**換算門檻**：換算門檻由 `scoring.py` 單一函式計算；g ＝ 1 時直接以 |r| > c 判定，g ≥ 2 的上下界以不受二進位浮點誤差影響的方式計算。函式是 `split_suspect_exceeds(r: float, g: int) -> bool`，算法如下：
       - c 就是 dirdef 常數 `SPLIT_SUSPECT_ABS_RETURN` 本身（IEEE 754 double），型別不變，不另存十進位字串，也不另存第二份常數。
       - r 照原方式以 double 算出（上式，同一個函式），不捨入。
       - g ＝ 1：以 double 直接比較 `abs(r) > c`，與原「單日簡單報酬的絕對值大於 c」逐位相同。
       - g ≥ 2：以標準庫 `fractions.Fraction` 做精確有理數運算。C ＝ `Fraction(c)`（c 這個 double 的精確值），上界 U ＝ (1 + C)^g − 1，下界 L ＝ (1 − C)^g − 1；`Fraction(r) > U` 或 `Fraction(r) < L` 就成立。不得以 double 的 `**`、`math.pow`、`exp`／`log` 計算上下界，也不得先把 r 或上下界捨入。
       - g 必須是 ≥ 1 的 `int`；否則拋例外，不得默認為 1。
       - 文件與報表中的百分比（例如 g ＝ 2 的 +23.21%／−20.79%），是精確值捨入到兩位小數後的呈現，判定不讀它們。
       - 理由：
         - (1) 有限 double 之間的比較本來就是精確的，而且 `Fraction(c)` 等於 c，所以 g ＝ 1 時精確路徑與 |r| > c 等價。明寫 |r| > c，是讓「與原規則相同」可以直接讀出；FL-66 另以性質測試斷言兩條路徑一致。
         - (2) 不採 `decimal`：`Decimal(c)` 有五十多位有效數字，g 次方後會超過預設 context 的 28 位精度而被捨入，結果取決於 context 設定，等於多一個可調參數。若改用十進位常數 `Decimal("0.11")`，g ＝ 1 時就與原規則不同：double 的 0.11 略大於十進位的 0.11，r 恰為 double 0.11 時原規則不觸發、十進位比較會觸發，違反 LG-30 (k)。
         - (3) 不採整數基點：r 是還原後價格的比值，不是有限位數的十進位數，換成基點必須先捨入，捨入規則本身就成為新的判定邊界。只有原始價格（有限位十進位）才能以交叉相乘精確比較，還原序列不符合。
         - (4) g ≤ 10 時，Fraction 的分子分母只有數百位元，每個相鄰對算一次，成本可忽略〔推論，未量測〕。
     - 門檻只由 c 與 g 換算，不看該標的當天實際有沒有漲跌幅限制。換算以「每個交易日都有一般漲跌幅限制」為前提；失效條件與凍結阻擋見事先宣告 §6.3 作廢規則第 3 點與 §9.2（風控 R14-15；data-engineer 規章查證，後續追蹤清單 N-18）。
     - dirdef 自己持有這個常數，不 import `sectors.definition.UniverseRules`。
     - （r2，A-32）**字面**：LM-63 適用於**全部以 `SPLIT_SUSPECT_ABS_RETURN` 判定的標的**（風控 v0.6 核對 B-2，取代第三批「只適用有漲跌幅限制的標的」）。〔v0.14：LM-63 的「單日」在 V14-03 之下不屬實，待 creative-lead 重送、風控核可；核可前 LG-21 失敗（R14-18）〕
     - （r2，A-32）**套用的序列**：個股 claim 該股的序列，以及族群成員的序列。`split_or_reduction_suspected` 不套用於大盤指數序列（事先宣告 v0.10 V10-01）。族群成員的序列符合時，依事先宣告 §1.2 排除該成員，不在 claim 層記此值，也不使整筆族群預測作廢（v0.14 V14-02）；跨越缺 bar 日的相鄰對同樣適用，大盤指數序列同樣不適用（v0.14 V14-03）。
     - （r2，A-32）**D_v 前要由 data-engineer 查證**：個股 claim 的範圍內（D-4.1：TWSE 上市普通股），有沒有結構上沒有漲跌幅限制的商品。
       - 槓桿／反向 ETF、國外成分 ETF 依 D-4.4 已經是 `E-SCOPE-TYPE`〔事實：本 ADR D-4.4〕；
       - 查證重點是「上市普通股」的判定來源可不可靠，以及 TDR、特別股、受益憑證等其他類型。
     - （r2，A-32）**若有這類商品，D_v 前二選一**：
       - (a) **建議**：事先登記，把它們排除在 claim 之外。dirdef 凍結正面清單 `CLAIM_SECURITY_TYPES`；不在清單內或類型不明的，一律 `E-SCOPE-TYPE`（fail-closed）；
       - (b) 另送 LM-63 的變體。
       - 建議 (a) 的理由：(b) 仍然會對這類商品推論「疑似分割或減資」，把真實的極端結果排除在計分之外，這正是風控指出的問題。
   - `dividend_factor_unusable`：窗內有除權息，但因子算不出來（**含配股**，`models.py:50-62`） → `excluded_corporate_action`
   - （r3，疑義裁定第 15 項；風控 2026-10-17 疑義裁定回送確認 Q-1）`index_bar_confirmed_erroneous`：大盤 P(T) 或 P(T+h) 的收盤經事先宣告 §6.3『大盤指數序列』確認有誤（『確認有誤之後』，L1175–L1177；X2 確認不屬此值，依 A-77 順延），而且依 `missing_bar_after_wait` 的既有等待值（5 個觀察交易日）等待期間（v0.14：期限依 `missing_bar_after_wait` 的期限評估，以判定視圖判定），或之後的更正作業，都取不到正確值 → `unresolvable_missing_data`；`diag_last_close` 以最後一根未被確認有誤的收盤計算（事先宣告 v0.10 V10-03）。只適用 `scope_kind = market`。結算後才確認的路徑依 §6.4 supersede，並依 A-65 翻案伴隨句處理。
     - （N-27；tech-architect 2026-10-18）**結算後才確認，不另等待**：已結算列的 P(T) 或 P(T+h) 收盤，在更正作業的判定視圖（D-9 第 5 點 ④）中為「確認有誤、尚未取得正確值」時，該次更正作業就以本值改記作廢，supersede 前一列（事先宣告 §6.3「確認有誤之後」：「結算後才確認：……取得正確值就重算；取不到就改記 `unresolvable_missing_data`」）。不等待 5 個觀察交易日，不延到之後的作業，也不看 T+h 之後已有多少觀察日。上句「等待期間……，或之後的更正作業」依此讀：等待只屬於結算前確認（結算評估）；結算後才確認，只看該次更正作業的判定視圖。寫入驗證見 D-11.4 第 11 點 (h) R10-2「適用範圍」。
       - 理由：(1) 事先宣告「結算後才確認」一支沒有等待；(2) 延後判定需要一個依時間經過的啟動條件，與 D-3「晚到資料的觸發」第 1 點「啟動與否只依本點四類觸發是否存在」不合（N-29 加入的第四類同樣只依資料事件）；(3) 延後期間，已結算列會照原值呈現一個收盤已確認有誤的結果，不帶 LM-143（風控 2026-10-18 C-22 確認 B-1）。
       - 代價：作廢列依 R10-3 不再 supersede。之後才取得的正確值，只能依 D-3 `forecast_void_late_diag` 記診斷結果，不回到 `resolved`。同一情形若在結算前確認，D_5 之前取得正確值就會照常結算。兩條路徑的差別只取決於確認與結算的先後，不看預測內容或結果；只在獨立來源已接入、① 查詢失敗、而 D_5 之前的某次 ② 取得數值時才會出現【推論】。
       - `wait_sessions`、`wait_deadline_session` 照抄被 supersede 列（D-3，不變）；D-3「結算評估寫入的列中……⇒ `wait_sessions ≥ 5`」不適用於本路徑（不變）。
       - 這類作廢依事先宣告 §6.3「以上作廢一律計入作廢率與 W」照常計入。
     - 作廢原因的判定順序中，第五值的位置交 quant 在事先宣告登記（v0.12，凍結前）。〔已決：完整順序依事先宣告 v0.13 V13-01（第五值的位置依 V12-14），見本點下方「判定順序」（N-12）〕
   - （N-12；事先宣告 v0.13 V13-01）**判定順序**：`index_bar_confirmed_erroneous` → `dividend_factor_unusable` → `split_or_reduction_suspected` → `basket_coverage_below_90` → `missing_bar_after_wait`，第一個成立的就是 `status_reason`。
     - 順序常數 `VOID_REASON_ORDER` 凍結在 dirdef，屬於 `definition_logic_sha256` 的範圍，字面與 V13-01 逐字相同：`VOID_REASON_ORDER = ("index_bar_confirmed_erroneous", "dividend_factor_unusable", "split_or_reduction_suspected", "basket_coverage_below_90", "missing_bar_after_wait")`。FL-22 另加一格：dirdef 的常數等於此 tuple。
     - 判定只由 `scoring.py` 的單一函式 `void_reasons(...)` 產生。五個值全部評估、不短路，回傳依 `VOID_REASON_ORDER` 排序的成立集合；`status_reason` 取第一個。
     - （N-22）「全部評估」指該 scope 允許集合（D-3 `void_reasons_json`）內的值；不在允許集合內的值不評估，這不算短路。`scope_kind = market` 不評估 `split_or_reduction_suspected`、`dividend_factor_unusable`、`basket_coverage_below_90`，不呼叫 `span_sessions` 與 `split_suspect_exceeds`，所以大盤的結算窗不經 D-9.3 B-3 的例外守衛。族群成員層的排除判定（D-3 `basket_excluded_members_json`：成員的因子、分割判準與 T+h bar）不受本句影響，照常評估。大盤不使用 g。未觀察平日的登記對大盤只有兩個作用：A-77 第 10 項「固定排除」（登記之後 d 才補寫進入 (i) 或 (ii) 時，d 仍不是觀察日），以及 §4.2 ③ 的計數。
     - 只讀 bar、除權息事件、因子計算結果與確認紀錄，不讀 label、`hit`、基準命中或任何驗證統計（AST 列舉 import）。
   - **判定時點**（V13-01）：
     - T+h 有 bar 時，在結算時判定。
     - T+h 缺 bar 時，在等待期滿或期間補到 bar 時一次判定；等待期間不得先以其他原因寫入作廢列。〔待決 O-1（N-13）：等待期間才補到的 T+h bar 依 D-9.1 第 2 點照字面不能用於結算，「期間補到 bar」一支的可用條件依 O-1 定案；定案時須滿足事先宣告 §9.2「仍開著的凍結前事項」O-1 的 (a)～(c)。O-1 定案前不得凍結〕〔已決：v0.14 V14-01（風控 2026-10-18 v0.14 審查有條件核可）；「期間補到 bar」一支依 D-9.1、D-9.2 的判定視圖可達，讀法見下一子點；凍結另受 V14-01 放寬待 CEO 明示同意的限制（待決事項 CEO 段第 11 點）〕
     - （v0.14 V14-01）上兩子點的讀法：「T+h 有 bar／缺 bar」指判定視圖中「有／沒有可用於結算的 T+h 資料」（第 1 點）；「期間補到 bar」指期間任一次評估的判定視圖中出現可用的 T+h 資料；「等待期滿」指判定視圖中已觀察到 T+h 之後第 5 個觀察交易日 D_5 的第一次評估（以序號判定，不比較時鐘；D_5 以該次評估可見的觀察日判定，寫入該列）。五值全部以同一個判定視圖評估。
     - 更正作業重算時依同一個函式與同一個順序。依 R10-3，作廢列寫入之後原因集合不再改變。
   - **部分窗口**：沒有可用的 T+h bar 時，`split_or_reduction_suspected` 以判定視圖中、結算窗內已有的 bar 之間的相鄰對評估（相鄰對與 g 依上文；V13-01、v0.14 V14-03）。
     - 跨越缺 bar 日的相鄰對也比對門檻，門檻依跨越日數 g 換算（v0.14 V14-03，事先宣告 §6.3 作廢規則第 3 點；風控 2026-10-18 v0.14 審查有條件核可）。〔已決：N-14 → V14-03〕
     - 另一面依 V14-03 修訂列方向欄：g 大時門檻寬，跨長停牌的小幅減資仍偵測不到；跨越未觀察平日的相鄰對門檻較寬，g ≥ 6（只會在跨越未觀察平日時出現）時 1:2 分割（−50%）偵測不到，官方休市日表接入之前，跨越平日假期的相鄰對可能屬此類【推論，依 A-77 第 10 項字面】；停牌期間實際步數比 g 少，敏感度偏低。以事先宣告 §4.2「跨缺 bar 的大幅變動」揭露；官方休市日表接入時，偵測範圍重新送風控（風控 2026-10-18 v0.14 單項確認）。
4. **失效條件觸發不作廢**（PA-7）；只記 `invalidation_triggered`，照常結算、照常計分。
5. **更正**：
   - 只限來源資料的更正，不含定義變更。
   - 由確定性作業對受影響日期範圍內的**全部**結算重查（結算窗與受影響日期有交集的都算），記錄 `correction_job_id`。
   - 有變的筆新增一列並填 `supersedes_id`；結算端改用最新一筆，預測端永遠用原始那一筆。
   - **更正作業的判定視圖**（N-21；tech-architect 2026-10-18，比照 D-9.2）：更正作業由 `app/forecast/correction.py` 的單一函式 `run_correction_job()` 執行。重算所讀的一切資料，以本作業的判定視圖為準；界定值存在 `forecast_correction_job`（D-3）。以存下的視圖重算，結果必須逐位相同。執行順序（不得調換）：
     ① 依 D-3「晚到資料的觸發」第 2 點掃描，取得 `market_scan_to`。之後不再讀市場 DB 的 `MAX(run_id)`。
     ② 以 `ledger_registration_start()` 唯讀導出 D_reg，讀時鐘與大盤列一次，建立本作業的大盤快照：
       - 範圍 ＝ [D_reg, 作業開始當日（Asia/Taipei）]，記入 `view_range_json`；
       - 只留 `is_final_bar(row, now=…)` 為真的列，寫入 `forecast_input_series`（`series_kind = index_bars`，以內容雜湊去重）；`content_sha256` 記入 `index_series_sha256`，`now` 記入 `index_final_now`；
       - 不強制重抓：D-9.2 的強制重抓只屬於結算評估；
       - 同一步讀官方休市日表一次（`official_holiday_table_meta` 一次，`official_holidays` 每個涉及的年度各一次；未接入時為 null），meta 記入 `holiday_table_json`；
       - 之後本作業不再讀大盤列與休市日表。
     ③ 開啟主 DB 寫入交易，依序：
       - 重新導出 D_reg；早於 `view_range_json.start` 時不寫入，記 WARNING；
       - 依 A-77 第 10 項，以 `market_scan_to` 界定的 (i)、本作業的大盤快照，以及 ② 的休市日表，完成 [D_reg, 最新觀察日] 內的未觀察平日登記；
       - 讀 E、V；
       - 依 D-11.4 第 11 點 (h)「原因怎麼歸屬」讀入觸發；
       - 寫入 `forecast_correction_job`（含 `observed_sessions_json`）；commit。
     ④ 重算：
       - (i) 只取 `run_id ≤ market_scan_to` 的 run；(ii) 只取本作業的大盤快照；
       - X2 確認日與未觀察平日只取 `event_id ≤ ledger_event_max`；確認判定紀錄只取 `check_id ≤ index_check_max`；
       - `span_sessions` 使用 ② 的休市日表；
       - **已結算數值所用的大盤 bar**（風控 2026-10-18 C-22 確認）：日期 d 落在被重查列的更正鏈中任一列的結算窗 [T, 該列的 T+h] 內時，重算所用 d 的大盤 bar，一律取「更正鏈中最早一個結算窗涵蓋 d 的列」所用判定視圖的大盤快照中 d 的列，再依 D-3 `forecast_index_check`「判定時怎麼讀」套用 `check_id ≤ index_check_max` 的確認判定；不取本作業快照中 d 的列。所用的快照：結算評估寫入的列，取其 `settle_eval_id` 的 `index_series_sha256`；更正作業寫入的列，取其 `correction_job_id` 的 `index_series_sha256`。兩份快照中 d 的列數值不同時，記 WARNING（帶 `forecast_id`、d），不改變本規則。
       - 更正鏈中沒有任何結算窗涵蓋的日期（例如 X2 順延後的新 T+h），取本作業快照的列。該列必須與某一列 `settle_eval_id ≤` 本作業 `settle_eval_max` 的 `forecast_settle_eval` 大盤快照中 d 的列數值相同（以 `checked_values_sha256` 的正規化規則比對），也就是已經過 D-9.2 ③ 的偵測。不成立時（本作業快照沒有 d 的列，或沒有數值相同的快照列），該筆不寫入，依下一子點列為待重算。
       - （N-29；tech-architect 2026-10-18；風控 2026-10-18 v0.15 單項確認第二節 C、N-29 單項確認）**待重算**：重算含 `x2_session_removed`，而且依本作業的判定視圖有下列任一情形時，該筆不寫 supersede 列，也不改記作廢，計入 `rejected_count`，記 WARNING，列入 `forecast_correction_job_end.rejected_json` 與 `pending_json`：
         - `shift_t_plus_h_unobserved`：`observed_sessions_json` 中 T 之後的觀察日不足 h 個，順延後的 T+h 還沒有觀察到；
         - `shift_t_plus_h_data_unavailable`：順延後的 T+h 已觀察到，但沒有可用於結算的 T+h 資料。個股與族群依事先宣告 §6.3「觸發」，市場 DB 只取 `run_id ≤ market_scan_to`；大盤是本作業快照沒有 d 的 `is_final_bar` 列；
         - `shift_index_bar_unverified`：大盤，本作業快照有 d 的列，但依上一子點找不到數值相同的結算快照列。

         這三種情形下，事先宣告 §6.3「判定時點」的「等待期間不得先以其他原因寫入作廢列」同樣適用：不以結算窗延長後才成立的其他原因，先行改記作廢。待重算列依 D-3「晚到資料的觸發」第 1 點的第四類觸發重查，畫面依 D-11.4 第 11 點 (g)「待重算路徑的狀態片段」呈現。期限與到期時的處理依事先宣告登記（後續追蹤清單 N-29 (b)）；登記之前不改記作廢，持續待重算。
         - 未通過上一子點比對的日期，在本作業的重算中一律視為沒有可用於結算的資料，任何欄位（含 `diag_*`、`mae`、`mfe`）都不得讀取它的列；期限到期時，`shift_index_bar_unverified` 依事先宣告 N-29 (b)，與 `shift_t_plus_h_data_unavailable` 同樣處理。
         - 重算含 `x2_session_removed`、但寫入驗證拒絕寫入的列（`write_validation_failed`），同樣不寫列，列入 `rejected_json` 與 `pending_json`，畫面依同一路徑遮蔽。這一種不是資料尚未到齊，不適用事先宣告 N-29 (b) 的期限，不因到期改記作廢；處理路徑只有一條：查出根因，修正程式或本條，送風控。修正之後，由第四類觸發重查。待重算項的 `reason` 以最近一次重查該項的作業判定（D-3 `pending_json`「以本作業的值取代」；沒有重查的項原樣帶入，所以等於最近一個已有 `forecast_correction_job_end` 列的作業的 `pending_json` 中該項的 `reason`）。期限是否適用、是否已到期，由重查該項的作業，依本作業的判定視圖與本作業判定的 `reason` 決定。`write_validation_failed` 的項重查後成為前三種情形之一時，自該次作業起適用事先宣告 N-29 (b) 的期限；起算依 N-29 (b)，不因曾為 `write_validation_failed` 而重設、延後或扣除該段期間；該次重查時已到期者，依 D-11.4 第 11 點 (h)「適用範圍」的 (乙) 改記作廢。前三種情形的項重查後成為 `write_validation_failed` 時，自該次作業起不適用期限，依本子點查出根因、送風控；修正後重新適用期限時，同樣不重設起算（tech-architect 2026-10-18；風控 2026-10-18 確認）。
         - 理由：延用前一列的結果，等於照順延前的結果呈現；直接採用本作業快照的列，等於讀未經偵測的 bar（風控 N21-3）。待重算同時避開這兩者，並留下逐筆紀錄。
       - 觀察日的 (ii) 仍取本作業快照。
       - 之後不再讀 `MAX(event_id)`、`MAX(check_id)`。
     - **理由**：
       - 重查的是已結算的舊預測，T 可能早於任何一次結算評估的快照範圍，所以不沿用 `forecast_settle_eval` 的快照。
       - 範圍取 [D_reg, 作業開始當日]，與缺日稽核的登記範圍相同。
       - 不強制重抓：同一次執行的結算評估，已處理它自己快照範圍內的缺漏。前一列已用過的日期，依上文取當時的快照，不受 `price_bars_cache` 事後的改寫或缺漏影響。事先宣告 §6.3 要求結算所用的每一根大盤 bar 都經過偵測；結算之後的改寫沒有經過偵測，不得經更正作業默默改變已結算的數值（R10-5：P(T) 取 `start_price_json`）。
6. 逾時與 on-demand 的紀錄也照常結算，供紀錄清單列示。
7. **重放不走本條的結算路徑**（N-22；tech-architect 2026-10-18 查證）：
   - `forecast_replay` 的結算不呼叫 `run_settlement_evaluation()`、`run_correction_job()`、`observed_sessions(*, view)`、`span_sessions`、`unobserved_weekdays` 與 `ledger_registration_start()`；
   - 不讀也不寫 `forecast_settle_eval`、`forecast_correction_job`、`forecast_index_check`；
   - 重放的起訖日登記、快照、偵測、查證、判定、日曆查詢與閘門，寫入 D-3 `forecast_replay_index_check`；重放結果寫入 D-3 `forecast_replay_outcome`；快照存於 `forecast_input_series`（`series_kind = replay_index_bars`）。
   - （N-22d）§4.7 的 126 日分段只由一個共用的純函式產生：從第一個 T 起，每 126 個觀察日一段，尾段照列並標明。不得直接以 `walk_forward_splits` 產生分段，因為它丟掉尾段，又要求 `train_size > 0`（`app/backtest/splits.py:70-71,84-85`）。可以把 `app/backtest/sector_eval.py:884-897` 的 `segment_bounds` 移到 `app/backtest/splits.py` 共用，`forecast` 不得 import `app.backtest.sector_eval`。尾段的報告定義依事先宣告登記（N-22d）；登記之前不得執行重放。
   - 不寫 `forecast_ledger_events` 的 `x2_confirmed_non_session`、`unobserved_weekday`、`session_calendar_conflict`；
   - 不寫 `forecast_outcome`。

   理由：
   - v1 重放只限大盤（事先宣告 §4.7）；`split_or_reduction_suspected` 不套用於大盤指數序列（第 3 點；事先宣告 §4.7 B-6），g 沒有用途。
   - 重放期可能有部分或全部日期早於市場 DB 的涵蓋起點（暖身的起日，ADR-0012 D-3、C-11；C-10 不回填）〔推論；重放期起訖日未登記，見後續追蹤清單 N-22c〕〔v0.16 註：重放期起訖日的決定規則已由事先宣告 v0.16 V16-02 登記，實際值於 §4.7 執行閘門 (a) 登記；本點原文不改〕。套用前瞻的判定視圖，涵蓋起點之前每個平日假期都會符合 A-77 第 10 項判準。

   重放結算的存放、判定視圖、觀察日來源，以及 X2 (iii) 在重放期的對照日曆，在重放結算程式實作前另行定義，送風控；涉及事先宣告 §4.7、§6.3 的字面時，由 quant 登記（後續追蹤清單 N-22b）。〔已決：X2 在重放期的對照日曆已由事先宣告 v0.15 V15-01、V15-02 登記；其餘部分已由事先宣告 v0.16 V16-01～V16-04 登記，見本點句末〕定義之前不得實作重放結算。X2 在重放期的對照日曆，已由事先宣告 §6.3「重放期的日曆檢查與查證」（v0.15，V15-01、V15-02）登記；其餘已由事先宣告 v0.16 登記：觀察日來源與決策日，見 §6.3「重放的觀察日與決策日」（V16-01）；起訖日，見 §4.7「重放期的起訖日」（V16-02）；預測端序列，見 §4.7「重放預測端所用的序列」（V16-03）；判定視圖與確認有誤之後的路徑，見 §6.3「重放中確認有誤之後」（V16-04）。存放見本點上方新增的子點；登記紀錄、版本歷史與快照正規化，見 D-3 對應各點。

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
   - （N-5）**整檔還原不另設撤銷**：依 RC‴-1（還原以整個主 DB 檔為單位）與 ADR-0026 D-9.1、D-9.4（主 DB 與市場 DB 取自同一組 `Connection.backup`），留在還原後檔內的 snapshot，它讀到的 outcome 與事件都在它之前 commit，所以也都在檔內〔推論：SQLite 線上備份產生一致的時點快照〕。因此，還原後留存的 `better_than_baseline` 判定不會有參與列遺失；R10-7 不因 `db_restored` 觸發。
   - （N-5）**前提被破壞時撤銷**（縱深防禦）：任何 snapshot 的 `e_read_event_seq`、`e_read_outcome_seq` 或 `e_read_job_end_seq` 大於目前看得到的對應最大值時，除了 RC‴-1 已規定的「`e_changed_since` 為真、記 WARNING」，另外：
     - 該 claim 的有效狀態若是 `better_than_baseline`，在下一筆 daily snapshot 撤銷（降級），到下一個檢查點重判，比照 R10-7；
     - 記 ERROR，交 devops-sre 依 ADR-0026 D-9.4 查還原程序；
     - `mark-restored` 在寫入 `db_restored` 的同一個交易內做這項掃描，結果寫入 payload：`seq_check ∈ {ok, failed}`，以及不成立的 snapshot 清單。掃描不成立仍照寫事件，因為缺日原因要留痕；
     - §4.2 揭露撤銷的日期、claim，以及觸發撤銷的 snapshot。
   - （N-5 甲案）**失落時間線的檢查點不得重抽**：
     - `db_restored` 的 payload 由 `mark-restored` 自行填入，至少含 `backup_set_id`、`backup_taken_at`（取自 manifest）。事件的 `recorded_at` 就是還原時點。
     - B_s ＝ `backup_taken_at` 當下或之前最新的觀察日；R_s ＝ 事件 `recorded_at` 當下或之前最新的觀察日。
     - N_R(claim) ＝〔還原後檔內，第 0 相位格點（事先宣告 §4.1）中 ≤ B_s 的個數；D_v 不存在或晚於 B_s 時為 0〕＋ ⌈ |`observed_sessions()` ∩ (B_s, R_s]| ÷ h ⌉。有多筆 `db_restored` 時各自計算，取最大值。〔推論：每個格點最多讓 n 加 1，所以 N_R 是失落時間線在還原當下可能達到的 n 的上限〕
     - `db_restored` 寫入之後才判定的檢查點，若 `checkpoint_n ≤ N_R`：
       - 正面結果（升為 `better_than_baseline`、重新上架）不認列；負面結果（降級、F-2 下架）照常生效。
       - 記法比照 A-28 (ii)：`stats_json.raw_checkpoint_result` 照寫；`suppressed_positive` 加必填欄位 `cause ∈ {suspended_f3, db_restored}`。
       - 比照 A-28 (iii)：在 n＝150（族群 250）時正面結果不認列，條件二就成立，不得因此延後退出期限。LM-74 在 `cause = db_restored` 的情形下仍然屬實：有效狀態不是 `better_than_baseline`，原始結果另記於 `stats_json.raw_checkpoint_result` 並在 §4.2 揭露。
     - N_R 只由單一函式 `restore_checkpoint_bound(claim)` 計算。它只讀主 DB 與觀察日函式，不讀 DB 檔以外的任何東西（RC‴-1）。
     - §4.2 揭露每一筆 `db_restored`：`backup_taken_at`、還原時點、遺失的觀察日數、各 claim 的 N_R，以及因本點而不認列的檢查點，以及可能遺失判定的檢查點（`checkpoint_n ≤ N_R`、而且還原後檔內在 `db_restored` 之前沒有該檢查點判定紀錄者），並註明失落時間線上的判定（含可能的升級與 F-2 下架）無法重現。
     - 本點的統計面規則由 quant 在事先宣告登記（v0.13）；登記之前照本點處理。
   - **`purpose` 為封閉列舉**，連同「purpose → 允許的 block_len」對照表凍結在 dirdef，屬於 `definition_logic_sha256` 的範圍。建議值如下，由 quant 在 v0.5 確認：
     - `neff`：block_len ＝ h；
     - `best_diff`、`paired_c`、`paired_c_w`：block_len ∈ {2, 4, 8}；
     - 開盤基準若有用到 bootstrap，再加 `*_open`。
   - snapshot 寫入時，鍵不在對照表內就拒絕寫入。
   - （r3，A-63；RC′-2、RC″-2、RC‴-1；N29-11）`stats_json` 另登記 `e_read_event_seq`、`e_read_outcome_seq`、`e_read_job_end_seq`（`pa9_holds` 的 `e_changed_since` 比較基準，見第 4 點第 11 項 (c)；第三個依風控 2026-10-18 N-29 單項確認 N29-11 加入），以及 `e_read_at`（稽核用，不作比較基準；也不用 `computed_at`）。
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
             - （N-29；風控 2026-10-18 N-29 單項確認）`forecast_correction_job_end` 的每一列，依 `correction_job_id`（待重算集合改變驗證統計的成員，事先宣告 N-29 (b) (i)）。（TA 補：snapshot 端對應的讀取序號為 `stats_json.e_read_job_end_seq`，見下文「比較基準」。）
               - 依據與範圍（tech-architect 2026-10-18）：job_end 寫入時，「最近一個已完成作業」換成本作業，D-11.4 第 11 點 (g) 的 (a)、(b) 隨之改變。會使 n 改變、卻沒有其他 `E_CHANGING_EVENTS` 的，是某筆預測離開或進入待重算集合、而本作業沒有為它寫入 supersede 列：(b) 中順延後 T+h 不變的列（例如週末的 X2 確認）；前一作業的 pending 項重查後沒有任何欄位改變（D-3 job_end 驗證第 3 子點）；已寫入順延結果的列，經其他類觸發重查後被拒而新列入。是否屬於這幾種，不在序號比較中判斷；依「判斷不了的一律歸入 `E_CHANGING_EVENTS`」，每一列都計。代價：作業沒有改變集合時也會遮蔽，到下一筆 daily snapshot 為止。依 D-7.1 第 2 點的執行順序，作業在驗證快照之前完成，同一次執行的 snapshot 已涵蓋；遮蔽只發生在驗證快照之後才完成的作業。
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
             - （N29-11；tech-architect 2026-10-18）`forecast_correction_job_end` 沒有自己的配號欄，以 `correction_job_id`（`forecast_correction_job` 的 `INTEGER PRIMARY KEY AUTOINCREMENT`，作業開始時配號）比較。作業開始的順序不等於 job_end 的 commit 順序，所以下文「依據」對這個序號不直接成立；改由 D-3「晚到資料的觸發」第 5 點「沒有 `correction_job_id` 大於本作業、已有 end 列的作業」的再驗證保證。這項驗證與 job_end 的 INSERT 在同一個寫入交易內完成，所以已寫入的 job_end 依 `correction_job_id` 遞增的順序 commit：read transaction 看得到的最大值是 S 時，之後才 commit 的 job_end 列，`correction_job_id` 都大於 S。移除或放寬這項再驗證時，須同時修訂本點。
             - snapshot 的計算在一個明確開啟的 read transaction 內讀 E，並在同一個 transaction 內讀出三個值，寫入 `stats_json`：
               - `e_read_event_seq` ＝ 看得到的 `forecast_ledger_events.event_id` 最大值；
               - `e_read_outcome_seq` ＝ 看得到的 `supersedes_id IS NOT NULL` 列中，`outcome_id` 的最大值。
               - `e_read_job_end_seq` ＝ 看得到的 `forecast_correction_job_end` 列中，`correction_job_id` 的最大值（N29-11；不論 `pending_json` 是否為空）；
               - 沒有列時記 0。
             - `e_changed_since(snapshot)` 為真，若且唯若下列三項任一成立：
               - 存在 `kind ∉ E_NEUTRAL_EVENTS`、而且 `event_id > e_read_event_seq` 的事件（含未歸類的值）；
               - 存在 `supersedes_id IS NOT NULL`、而且 `outcome_id > e_read_outcome_seq` 的列。
               - 存在 `correction_job_id > e_read_job_end_seq` 的 `forecast_correction_job_end` 列（N29-11）。
               - 三個欄位任一缺漏或不是整數，一律為真。
             - 讀取順序（RC‴-1）：在同一個明確開啟（明確 `BEGIN`）的 read transaction 內，**先讀 `e_read_event_seq`、`e_read_outcome_seq`、`e_read_job_end_seq`，再讀 E**（N29-11：這裡的 E 包括事先宣告 N-29 (b) (i) 的待重算集合，由 D-11.4 第 11 點 (g) 讀取兩個集合的那一個 `store.py` 函式讀取）。
             - 下列任一情形，`e_changed_since` 為真，並記 WARNING（RC‴-1）：序號欄位缺漏；不是非負整數（bool 不算）；大於目前看得到的對應最大值。
             - `e_changed_since` 比對的 snapshot 與事件最大值，要在同一個 read transaction 內、從同一個主 DB 檔讀出；不得跨請求或跨程序快取 snapshot 或序號。
             - 備份還原後，失落時間線的序號可能被重新配發，所以 DB 檔以外保存的 snapshot 或序號，不得用於任何判定。還原以整個主 DB 檔為單位。
             - 寫入函式與 SQL 不得指定 `event_id`、`outcome_id`，以及 `forecast_correction_job` 的 `correction_job_id`，由 SQLite 配號（比照 D-2 第 3 點）。
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
         - （N-6）**遮蔽期的計數來源**：
           - 不新增欄位。由 `views` 的單一函式 `mask_episodes(claim_id, *, as_of)` 從既有資料重建。它和 `e_changed_since` 放在同一個模組、共用同一個序號比較函式，不用時鐘。
           - **變動項**：`kind ∉ E_NEUTRAL_EVENTS` 的 `forecast_ledger_events`（依 `event_id`）、`supersedes_id IS NOT NULL` 的 `forecast_outcome`（依 `outcome_id`），以及 `forecast_correction_job_end`（依 `correction_job_id`；N29-11）。
           - 對 claim c 與變動項 x：
             - S_cover ＝ c 的 daily snapshot 中，對應讀取序號 ≥ x 的序號、`computed_for_session` 最早的一筆；
             - S_before ＝ c 的 daily snapshot 中，對應讀取序號 < x 的序號、`computed_for_session` 最晚的一筆；
             - 讀取序號缺漏、或不是非負整數的 snapshot，視為不涵蓋任何變動項（RC‴-1）。
           - 同一組 (S_before, S_cover) 的變動項合為一個遮蔽期，`reason = e_changed_since`。
             - 遮蔽日數 ＝ |`observed_sessions(as_of)` ∩ (S_before.`computed_for_session`, S_cover.`computed_for_session`]|。
             - 還沒有 S_cover 時，視為進行中，右端取 `as_of` 當下最新的觀察日。
           - 沒有 S_before（D_v 之後還沒有任何 daily snapshot）時：`reason = no_daily_snapshot`，日數 ＝ |`observed_sessions(as_of)` ∩ [D_v, 第一筆 daily snapshot 的 `computed_for_session`]|。D_v 不存在時不計。
           - 正常情形下日數是 1：事件在當晚 snapshot 讀 E 之後 commit，由下一個觀察日的 snapshot 涵蓋。
           - **WARNING**：缺日稽核（D-8.2）每次執行時，對每個已登記的 forward claim 呼叫 `mask_episodes`。有遮蔽日數 ≥ 2 的遮蔽期（進行中或剛結束）就記 WARNING，帶 claim、`reason`、S_before 的 `computed_for_session`，以及變動項的最小序號。
           - 日數以 `computed_for_session` 與觀察日計，不以牆鐘計（比照 RC″-2）。觀察日集合可能因 X2 確認而回溯縮小（A-77 第 11 項），所以 §4.2 揭露時一併記下 `as_of`。
           - `mask_episodes` 只供 §4.2 與 WARNING 使用，不得作為 `n_disclosure_masked` 或任何顯示判定的輸入。
           - §4.2 的揭露項目與格式，由 quant 在事先宣告登記（v0.13）。
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
         - （N-29；tech-architect 2026-10-18）**待重算路徑的狀態片段**：同時滿足以下兩點的列，以 `MaskedRecordView` 回傳，`status_fragment_id` 必填，值只能是待重算片段（暫定常數 `RECORD_STATUS_RESETTLE_PENDING`；逐字由 creative-lead 起草，送風控；PA-8）。這是雙向規則：待重算片段也只能出現在本路徑。
           - 鏈尾是 `status = resolved` 的列；
           - 符合下列任一項：
             - (a) 鏈尾的 `outcome_id` 出現在最近一個已有 `forecast_correction_job_end` 列的作業的 `pending_json`；
             - (b) 有一筆 `x2_confirmed_non_session` 事件，`event_id` 大於該作業的 `ledger_event_max`（沒有已完成作業時取 0），`session_date` 落在 (該筆的 T, 鏈尾 `end_price_json.session_date`]，而且不在鏈尾 `x2_shift_json.x2_event_ids`。這是已知要順延、但還沒經過更正作業處理的列。
           - 判定只由 `display.py` 的 `record_status_fragment(row)` 產生；兩個集合由 `views.py` 經 `store.py` 的單一唯讀函式讀取（AST 列舉呼叫點），這是 `views` 讀取 `forecast_correction_job`、`forecast_correction_job_end` 的唯一呼叫點；唯一的例外是第 4 點第 11 項 (c) 的序號比較函式（`e_changed_since` 與 `mask_episodes` 共用）。它經 `store.py` 的另一個單一唯讀函式，只讀 `forecast_correction_job_end` 的 `correction_job_id`，不讀該表其他欄位，也不讀 `forecast_correction_job`；回傳值只用於序號比較，不得進入任何回應、匯出或 `record_status_fragment` 的判定。snapshot 寫入端讀 `e_read_job_end_seq` 也只經這個函式（N29-11；風控 2026-10-18 確認；AST 列舉呼叫點）。`validation.py` 依事先宣告 N-29 (b) 計算驗證統計時，呼叫讀取上述兩個集合的那一個 `store.py` 函式（AST 列舉呼叫點）。
           - 優先序：本路徑先於 LM-150、LM-154、「診斷欄位更正的例外」與一般已結算列的呈現。最新 outcome 不是 `resolved` 時不適用，走 LM-143。與其他規則同時成立時（tech-architect 2026-10-18 補定義；風控 2026-10-18 確認）：
             - A-27 (a)、(b)、(d)、(d′) 只適用於尚未結算的列，與本路徑（鏈尾 `resolved`）不會同時成立。
             - 族群列不適用本路徑（LM-155 條件 ⑧）。A-27 (c) 成立時，依 (c) 與第 11 點選用 gate 片段；本路徑的禁止欄位與全域不顯示另外適用，所以 (c) 已結算列可加的 `settlement_date`、`outcome_status` 在這類列不得出現。(c) 不成立時，在族群已結算 label 核可、並經風控確認本路徑擴及族群之前，不顯示 label 與任何結算結果，FL-52 (d) 對該格失敗。
             - `in_eligible_set = false` 的列（已確認的 PIT 違規，以及 `before_dv`、`late`、`on_demand`）：狀態行用本路徑的待重算片段；資格標示照 A-61，並列 LM-110 與全部原因片段（PIT 列含 LM-114，排第一），視覺區隔照舊。兩者分屬不同位置，不互相取代；LM-110、LM-114 不在本路徑的禁止清單內。片段中「計入作廢統計」指事先宣告 §4.2 作廢數 (7)：E 以外的列到期作廢時照樣逐筆計入 (7)，不計入作廢率與 W（事先宣告 V18-03、V18-04；quant 2026-10-18 書面確認）。這個前提改變時，E 以外的列不得用本路徑的片段，改為不顯示 label 與任何結算結果，FL-52 (d) 對該格失敗，回送風控。
             - PV-45 是否附加，照 A-27 (e) 既有條件，本點不改。
             - 本路徑與 LM-150、LM-154、「診斷欄位更正的例外」之間的優先序不變。
           - 白名單比照 FAIL_CLOSED 列：
             - 可帶 `settled = true`；
             - 不帶 `settlement_date`、`outcome_status` 與 R10-6 的任何 D 欄位；
             - 不得出現 A-64 (g) 的全部禁止欄位，以及 `label`、`realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`、`threshold_display`、`resolved_at`、`correction_causes`；
             - `disclosure_fragment_ids` 不得含 LM-131、LM-132、LM-146、LM-92、LM-133、LM-143、LM-150、LM-151、LM-152、LM-154。大盤列不得含 LM-22。
           - 全域不顯示比照 LM-154 條件 ⑥。
           - 片段核可之前，FL-52 (d) 失敗（比照 A-36 第 2 點的效力鏈），不得以暫定字面、placeholder、skip 或 xfail 讓測試通過。
           - (b) 會把順延後 T+h 不變的列（例如週末的 X2 確認）也暫時遮蔽，直到作業完成為止。方向保守；作業完成後改依 (a) 判定。
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
           - **作廢列不因之後補到的資料而 supersede**（第十批 R10-3；風控 2026-10-18 v0.12 審查 Q12-4）：依事先宣告 v0.12 V12-20，`status ≠ resolved` 的 outcome 一經寫入，不因之後補到資料（T+h bar、正確收盤、除權息因子）而 supersede，適用全部作廢原因。更正作業依規則不重算這類列；補到資料的筆數記在 `forecast_correction_job_end.void_late_data_count`，不計入 `rejected_count`，在 §4.2 揭露。〔N-4：操作定義（補到資料、而且算得出診斷結果）與涵蓋邊界，見 D-3 `forecast_void_late_diag` 與「晚到資料的觸發」〕寫入函式仍然拒絕任何把作廢列 supersede 的寫入（縱深防禦，計入 `rejected_count`）。補到資料後的診斷標籤，存放處由 TA 定：只增不改，不得寫入 `forecast_outcome`，列入待決事項，D-9 結算程式實作前定案。〔已決：存放於 `forecast_void_late_diag`，見 D-3（N-4）〕
           - **原因怎麼歸屬（確定性規則）**：
             - 更正作業把啟動當下所有還沒處理的觸發一次讀入，寫進 `triggers_json`。觸發包括 `x2_confirmed_non_session` 事件、收盤更正的查證紀錄、來源修訂、因子修訂。〔N-17：因子修訂觸發的偵測方式尚未定義，定義落地前不會產生這類觸發，見 D-3「晚到資料的觸發」第 6 點〕（N-21）「還沒處理」以序號界定：
               - `x2_confirmed_non_session` 事件取 `event_id` ∈ (`ledger_event_from`, `ledger_event_max`]；
               - 確認判定紀錄取 `forecast_index_check` 中 `check_id` ∈ (`index_check_from`, `index_check_max`]、`determination ∈ {close_erroneous, non_close_erroneous, correct_close_obtained}` 的列。對每一筆重查的 outcome 個別歸類：`determination ∈ {close_erroneous, correct_close_obtained}`、而且 `target_bar_json.session_date` 是該筆的 T 或 T+h → `settlement_close_corrected`；其餘（含 T、T+h 的 `non_close_erroneous`，以及窗內其他日的任何判定）→ `window_bar_corrected`；
               - 來源修訂依 D-3「晚到資料的觸發」。
               - （N-29）待重算觸發（`pending_resettle`）：對該 `forecast_id`，以 `pending_json` 該項的 `causes` 計入（必含 `x2_session_removed`）；受影響日期為 [該筆的 T, 本作業 `observed_sessions_json` 的最後一日]。前一個已完成作業 `pending_json` 中的 `forecast_id`，本作業只要重查它（不論由哪一類觸發），都同樣併入該項的 `causes`，受影響日期同上。

               中斷作業不使 from 前進，它的觸發由下一個作業重新讀得。
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
               - （N-27；tech-architect 2026-10-18）**適用範圍**：上三項只適用於新列 `status = resolved`。新列 `status ≠ resolved`（已結算列經更正後改記作廢）時，上三項不適用，改以下列各項驗證，任一項不成立就拒絕寫入：
                 - 前一列 `status = resolved`（作廢列不得被 supersede，R10-3 不變）；
                 - 屬於下列兩種之一：
                   - **(甲)**（N-27）`scope_kind = market`，`status_reason = index_bar_confirmed_erroneous`；以本作業的判定視圖（D-9 第 5 點 ④）、經 `scoring.py` 的同一個函式重算，P(T) 或 P(T+h) 至少一根的收盤是 D-3 `forecast_index_check`「判定時怎麼讀」所說的「確認有誤、尚未取得正確值」；而且 `correction_causes` 至少含 `settlement_close_corrected` 或 `x2_session_removed` 之一（風控 2026-10-18 v0.15 單項確認 C 段 suggested；tech-architect 2026-10-18 採用）。
                   - **(乙)**（N-29）`correction_causes` 含 `x2_session_removed`，不限 scope（仍受 D-3 `void_reasons_json` 依 scope 的允許集合限制）；以本作業的判定視圖、經 `scoring.py` 的同一套函式、以順延後的 T+h 重算（五值全部評估，D-9.3「判定順序」），得到的 `status`、`status_reason`、`void_reasons_json`、`basket_excluded_members_json`、`window_factors_json` 與新列逐位相同，而且 `status_reason ≠ index_bar_confirmed_erroneous`（那一支屬 (甲)）。`void_reasons_json` 含 `missing_bar_after_wait` 或 `basket_coverage_below_90` 時，另須事先宣告已依後續追蹤清單 N-29 (b) 登記期限，而且本作業的判定視圖已到期；登記之前，這兩種情形依 D-9 第 5 點「待重算」處理，不寫作廢列。
                 - `correction_causes` 不含 `x2_session_removed` 時：`x2_shift_json` 與前一列相同，而且以本作業觀察日導出的 T+h 等於前一列的 `end_price_json.session_date`。含 `x2_session_removed` 時：依上方「寫入時的一致性驗證」第一子點，而且 `x2_shift_json.shifted_t_plus_h` 等於以本作業觀察日導出的 T+h，並晚於前一列的 `end_price_json.session_date`；
                 - (甲)：`window_factors_json` 和前一列相同（(乙) 依該支的逐位相同驗證；窗延長後可能與前一列不同）。

                 (甲)、(乙) 以外的改記作廢，不屬於本 ADR 已定義的 supersede，一律拒絕（fail-closed，計入 `rejected_count`，記 WARNING）。理由：作廢列依下方「選用規則」走 LM-143，不查 `CORRECTION_REASON_FRAGMENTS`，所以上三項「差異必須和 LM-151、LM-152 的陳述相符」的前提不存在；作廢列也沒有可比較的結算收盤。改以重算依據驗證，事先宣告 §6.3「確認有誤之後」的「結算後才確認：……取不到就改記 `unresolvable_missing_data`」才寫得進去（FL-22「market 結算後確認」一格）。
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
       - 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}, cause ∈ {suspended_f3, db_restored}}`（`cause` 必填；`db_restored` 依 D-11 第 2 點 N-5 甲案）；
       - （N-5 甲案；`cause` 的取值）同一個檢查點兩個原因同時成立時，`cause = suspended_f3`（與第 12 點的優先序一致）。`cause` 只供稽核與 quant 的檢查點檢討紀錄使用；§4.2「整檔還原」列的「因本點而不認列的檢查點」（D-11 第 2 點 N-5 甲案）依 `restore_checkpoint_bound` 判定，不依 `cause`。所以兩個原因同時成立的檢查點，§4.2「整檔還原」列與 quant 的 F-3 檢查點檢討紀錄兩邊都計入，不得因為 `cause` 只記一個值而只計一邊。下一點的 `positive_suppressed_during_f3` 只在 `suspended_f3` 成立時設定，不因 `db_restored` 而設定。
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
- （N-5）「一經出現就不會移動」以沒有整檔還原為前提。還原的備份時點早於 D_v 時，D_v 依還原後的檔重新導出，可能晚於失落時間線上的 D_v。這時 §4.2 揭露該 claim「D_v 晚於 B_s，而且有 `db_restored` 事件」。
- 因為只增不改，而且 late=0 的紀錄必定早於下一個 session 的紀錄，所以這個最小值是穩定的〔推論〕。
- （「起算日」用語，LM-84 條件 1）D_v 由單一函式 `claim_dv(claim_id) -> date | None` 導出。它是 store 的唯讀查詢；`validation.py` 判定 E、`views` 填字面，都呼叫它。值是 session 日期（`data_as_of`），不是寫入日期。
- 字面的 `{起算日}`（LM-84、LM-85）與「紀錄起算日」（LM-99、LM-111）都綁定這個值，日期依年份規則格式化。〔用語是否改詞待後續追蹤清單 N-15；值的綁定已由 tech-architect、quant 確認〕
- `claim_dv` 為 None 時：
  - LM-84、LM-85 不渲染（承接 2026-10-16 B-6）；
  - `before_dv` 不成立：plan 的 unavailable 原因與紀錄清單的 `exclusion_reasons`，都不得出現 `before_dv`。
  - 〔推論，已核對 A-60 的不變式：D_v 不存在時，清單回傳的每一列都是 on-demand 或 `late=1` 的排程列，所以 `exclusion_reasons` 照樣非空〕
- LM-84、LM-85 的一個實例只綁一個 claim 的 D_v。驗證狀態頁的同一區塊涵蓋多個 claim 時，不得用單一個 `{起算日}` 渲染；版面由 creative-lead 與 frontend 依 DV-7 處理。改成頁面層級的寫法（例如不帶日期）屬於改詞，要重送。

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
- 21 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。
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
- （剩餘待決項，N-5 甲案）**甲案的殘餘**：失落時間線若已在 `checkpoint_n ≤ N_R` 的檢查點觸發 F-2 下架，新時間線重判時結果若不再是負面，claim 就不會下架；使用者曾看到的下架會消失。〔風控 2026-10-18 裁定：採甲案、駁回乙案（乙案使 LM-75／LM-87 不屬實）；殘餘風險以 §4.2「整檔還原」列揭露為條件書面接受，最終責任由 CEO 負〕

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
      - (h5) 候選 T＝d → `inputs_not_ready`，而且恰好寫一筆 `origin = candidate_t_x2`，重跑不重複寫入；
      - (h6) direct 與 verified 各一格：verified 格斷言沒有 `origin = candidate_t`；direct 格斷言兩個 origin（`candidate_t`、`candidate_t_x2`）各一筆。
      - （N-3）加一格：`x2_event_id` 指向不同 `session_date` 的事件，或 `evidence` 和 `trigger` 不符，各自拒絕寫入。
    - (i)（Q-3 A 案，風控 2026-10-18 C9-7 與 Q-3 提案確認）未觀察平日：
      - 平日沒有 run、也沒有大盤列 → 只寫一筆事件，d 不是觀察日，沒有缺日列，重跑不重複寫入；
      - 表列休市日、週末、d 是最新日期 → 都不寫事件；
      - 登記之後補寫 run → d 仍然不是觀察日，衝突事件只寫一筆；
      - outcome 與缺日列的雜湊前後相同；
      - 結算寫入之後、缺日稽核之前，補寫 d 的定案資料 → d 在結算當下已登記，仍不是觀察日；outcome 的雜湊不變；`post_unobserved_backfill` 只寫一筆（風控 2026-10-18 Q3-2）；
      - 分別只進入 (i)、只進入 (ii)、兩者都進入 → `backfill_via` 與參照欄位都正確，而且只寫一筆；先進入 (i)、之後才進入 (ii) → 不另寫，`backfill_via` 仍是 {`set_i`}（風控 2026-10-18 E8-3）；
      - 拒絕格四個：`evidence` 和 `origin` 不相配（兩個方向各一格）；`unobserved_event_id` 指向不存在或 `kind` 不符的事件；`backfill_via` 和重算結果不符。
      - （N-9）加四格：`holiday_coverage` 三個值各一格，fixture 共用同一個假來源；另一格斷言 meta 與 `official_holidays` 的不變式。
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
      - （N-27）改記作廢的 supersede：已結算列在結算之後，窗內一日經 X2 確認；順延後的新 T+h，在某一列 `forecast_settle_eval` 大盤快照中的 bar 觸發 X1 收盤本身不可用（`close_erroneous`、`direct`），沒有 `correct_close_obtained` → 更正作業寫入 `index_bar_confirmed_erroneous` 作廢列，`correction_causes` 含 `x2_session_removed`，不被 R10-2 拒絕，最新 outcome 走 LM-143；新 T+h 的列與快照列的比對以 `checked_values_sha256` 的正規化規則進行，NaN 收盤不因浮點比較而判為不同。同一 fixture 另做五個拒絕子例：`scope_kind ≠ market`；`status_reason ≠ index_bar_confirmed_erroneous`；前一列已作廢；`x2_shift_json.shifted_t_plus_h` 不等於以本作業觀察日導出的 T+h；重算後收盤並非「確認有誤、尚未取得正確值」。另一格（事先宣告 V15-03 適用單位）：結算所用的擷取 B1 本身沒有確認有誤，結算之後另一次擷取 B2 觸發 X1 收盤本身不可用，B1、B2 構成的 X3 在待查證集合 → 更正作業不寫新列，B1 照原值計分，計入事先宣告 §4.2 作廢數 (6)。
      - （N-29）(乙)：個股結算後 X2 順延，延長後的窗含除權息、因子不可用 → 寫入 `dividend_factor_unusable` 作廢列，不被拒絕；重算結果與新列的 `void_reasons_json` 不同 → 拒絕。新 T+h 沒有資料、N-29 (b) 尚未登記 → 不寫 `missing_bar_after_wait`，列入待重算。(甲)：`correction_causes = [window_bar_corrected]` 的 `index_bar_confirmed_erroneous` 作廢 → 拒絕（S-1）。(乙) 列的 `window_factors_json` 與重算結果相同、與前一列不同 → 不被拒絕；(甲) 列的 `window_factors_json` 與前一列不同 → 拒絕。
    - (c) 「謂詞為真 × 最新 outcome 為 `resolved`」路徑中，`correction_causes` 的每一種情形（四個單值、一組雙值）各一格，逐格斷言全文：
      - LM-151、LM-152 兩格要等於 LM-150 代入後的全文，而且不含「沒有實際結果」、不含日期數字；
      - FAIL_CLOSED 的格（LM-154 條件 ③⑤⑩）：三格——除權息因子；兩個以上原因；未豁免的診斷更正。每格斷言：
        - schema 驗證通過，`status_fragment_id == LM-154`；
        - 狀態行逐字等於 LM-154；全文不含日期數字，不含「作廢」「撤回」「沒有實際結果」，也不含 LM-143、LM-150 的 ID；
        - 沒有白名單以外的鍵；`disclosure_fragment_ids` 不含上列 ID；大盤格不含 LM-22。
      - 對照格：`[x2_session_removed]`；`[settlement_close_corrected]`，P(T) 收盤有變、P(T+h) 收盤有變各一格；豁免成立的 `[window_bar_corrected]`。這四格都找不到 LM-154；兩個收盤更正格的狀態行等於 LM-150 代入 LM-152 的全文。
    - (d) 同一晚注入 X2 確認與收盤更正、兩者和同一筆有交集 → 該筆的 `correction_causes` 有兩個值，結果 fail-closed；
    - (e) 原因為 `window_bar_corrected` 但 D 欄位改變 → 拒絕寫入。
  - （N-12；事先宣告 v0.13 V13-01）**表格驅動格**加 `void_reasons_json`：逐格斷言 `status_reason`、`status`、`void_reasons_json`：
    - LG-28 (a)：market 收盤確認有誤＋T+h 缺 bar；
    - LG-28 (b)：因子不可用＋分割；
    - LG-28 (c)：缺 bar＋因子不可用，另斷言 `diag_last_close` 為 null；
    - LG-28 (d)：缺 bar＋分割，同樣斷言 `diag_last_close` 為 null；
    - LG-28 (e)：三者同時成立；
    - LG-28 (f)：族群成員缺 bar 或因子不可用時，claim 層不出現 `missing_bar_after_wait`、`dividend_factor_unusable`；
    - LG-28 (g)：等待期間不寫入作廢列；
    - LG-28 (h)：label 互換後輸出逐位相同；
    - LG-28 (i)（v0.14 V14-02）：族群成員符合分割判準。
      - 排除後覆蓋 ≥ 90% → `resolved`，`void_reasons_json` 為 null；`basket_excluded_members_json` 含該成員，`reasons = ["split_or_reduction_suspected"]`；`diag_basket_with_excluded` 以觸發判準的那條序列的最後可得收盤放回該成員。
      - 排除後覆蓋 < 90%，至判定視圖中已觀察到 D_5 的評估仍是 → `void_reasons_json = ["basket_coverage_below_90"]`。
      - 同一成員同時沒有可用的 T+h bar → `reasons = ["split_or_reduction_suspected", "t_plus_h_bar_unavailable"]`。
    - （v0.14）寫入驗證格另加，各自拒絕：
      - `sector` 列的 `void_reasons_json` 含 `split_or_reduction_suspected`；
      - `basket_excluded_members_json` 有以下任一情形：排序錯誤、原因不在列舉、成員不屬於 S_T、10x 與 `status` 不一致、非族群列卻非 null。
      - 另斷言：dirdef 的 `BASKET_EXCLUSION_REASON_ORDER`，等於由 `VOID_REASON_ORDER` 去掉 `index_bar_confirmed_erroneous`、`basket_coverage_below_90`，再把 `missing_bar_after_wait` 換成 `t_plus_h_bar_unavailable` 的結果。
    - 另加寫入驗證格：集合排序錯誤、第一個元素 ≠ `status_reason`、超出 scope 允許集合、`resolved` 列非 null，各自拒絕寫入。
  - （風控 R-6′）另加一格：dirdef 的常數 `VOID_REASON_ORDER` 等於 D-9.3 宣告的 tuple。
- **FL-23**：更正作業涵蓋所有結算窗與受影響日期有交集的列，不多不少。
- **FL-64**（N-4；掛 A-65（R10-3）；D-3「晚到資料的觸發」第 1～9 點（第 9 點 v0.14 V14-01 加））：fixture 用離線的假市場 DB 與主 DB。
  - (a) 誰偵測（第 1 點）：
    - 呼叫點列舉（AST）：`scan_late_market_bars()` 只在每日結算之後與更正作業啟動時被呼叫；
    - 市場 DB 只經 `MarketPanelReader.ok_bars_runs_between` 讀取；`app/forecast/**`、`app/outlook/**` 不另開市場 DB 連線，也不出現它的路徑字串（grep，比照 ADR-0012 T-3）；
    - `pit_snapshot`、`MarketPanelStore` 不 import `app.forecast.*`，也不開主 DB（import graph）；
    - 沒有命中、也沒有其他觸發 → 不寫 `forecast_correction_job`。
  - (b) 掃描範圍（第 2 點）：
    - W 等於 `correction_job_id` 最大、而且有 end 列的作業的 `market_scan_to`；沒有這樣的作業時為 0；
    - 兩端各一格：`run_id = W` 不取，`run_id = run_max` 取；
    - 掃描中注入 `run_id > run_max` 的新 run → 本次不取，下一次取得；
    - 過濾各一格，都不產生觸發：`kind ≠ 'bars'`；`status ≠ 'ok'`；`session_date IS NULL`；`is_final(TW, session_date, recorded_at)` 為假。AST 斷言掃描函式不直接比較 `recorded_at` 與任何時間值。
  - (c) 配對（第 3 點）：
    - 三項都成立 → 恰好一個觸發項；
    - 三項各自不成立各一格，都不產生觸發：鏈尾 `status = resolved`；`session_date` 不在 [T, T+h]；該標的在該 run 沒有 `market_daily_bars` 列；`run_id ≤ settle_source_run_max`（含相等一格）；
    - 族群：成員在該 run 有列 → 觸發；非成員有列 → 不觸發。
  - (d) `settle_source_run_max`（第 4 點）：
    - 寫入函式的簽章沒有這個參數（AST）；
    - 值等於該次結算評估讀到的 R（＝ `forecast_settle_eval.market_run_max`）。評估讀 R 之後、寫入之前在假市場 DB 注入新 run → 值仍等於 R，不等於寫入當下的 `MAX(run_id)`（R14-4；LG-29 (d)）。更正作業寫入的列，值等於該作業的 `market_scan_to`；作業啟動之後、寫入之前注入新 run → 值不變（風控 2026-10-18 v0.14 單項確認）。大盤列為 null，個股與族群列非 null；
    - 注入倒退的 store 時鐘，觸發結果逐位相同。
  - (e) 觸發項與鏈接（第 5 點）：
    - `source_revision` 項恰有 `kind`、`run_id`、`recorded_at`、`session_date` 四鍵；
    - `market_scan_from` ≠ W → 拒絕寫入；
    - 同一個 `(run_id, recorded_at)` 出現在兩個已完成作業 → 拒絕；
    - 中斷作業（沒有 end 列）之後的下一個作業：`market_scan_from` 等於中斷作業之前那個已完成作業的 `market_scan_to`，重新掃得同一批觸發，可以寫入並寫完 job_end；
    - 兩個作業交錯：`correction_job_id` 較大的作業先寫完 job_end，較小的作業再寫 job_end → 拒絕、記 WARNING；本作業開始之後 W 已改變 → 拒絕寫入 job_end、記 WARNING；兩種情形之後的下一個作業都可以寫入並寫完 job_end，其他觸發不被擋下；被拒的較小 id 作業沒有 job_end 列；性質測試：任意交錯之下，已寫入 job_end 的 commit 順序與 `correction_job_id` 的順序相同（N29-11 比較基準）。
    - 性質測試：已完成的作業依 `correction_job_id` 排列，(`market_scan_from`, `market_scan_to`] 首尾相接、不重疊。
  - (f) 涵蓋邊界（第 6 點）：
    - 大盤作廢列，注入晚到的指數 T+h bar → 不產生 `source_revision` 觸發；
    - §4.2 報表對沒有觸發涵蓋的組合輸出「未涵蓋，不計」，不輸出 0：大盤 × {`t_plus_h_bar`, `settlement_close`}；三個 scope × `basket_member`；三個 scope × `dividend_factor`（N-17 定義落地前）。即使 `forecast_void_late_diag` 沒有任何列也一樣；
    - 對照格：個股 × `t_plus_h_bar` 沒有列時輸出 0。
  - (g) 還原保護（第 8 點）：W 大於假市場 DB 的 `MAX(run_id)` →
    - 記 WARNING，不產生任何 `source_revision` 觸發；
    - 有其他觸發時作業照常啟動，而且 `market_scan_from = market_scan_to = W`；該作業 `market_scan_restore_suspected = 1`，第 8 點不成立的作業為 0；§4.2 報表列出這些作業，並帶「只是下限」的註明；
    - 下一次掃描的 W 不變；`ok_bars_runs_between` 不被以 0 或目前的 `MAX(run_id)` 為下界呼叫（不重掃）。
  - (h)（v0.14 V14-01；第 9 點，風控 R14-4）與判定視圖的關係：
    - 等待期間寫入、`run_id ≤` 該列 `settle_source_run_max` 的 run（判定時已在視圖內）→ 不產生 `source_revision` 觸發（相等一格與 (c) 共用）；
    - 判定視圖內只有定案前 run 的 T+h bar，作廢之後才寫入定案 run（`run_id` 大於 `settle_source_run_max`）→ 依 (c) 產生觸發（風控 R14-3）；
    - 評估讀 R 之後、寫入之前插入的 run → 不在該評估的判定視圖內，依 (c) 判為晚到（對應 LG-29 (d)）。
  - 第 7 點是預期量，不是規則，不設格。
- **FL-65**（v0.14 V14-01；D-9.1、D-9.2、D-9.3 `missing_bar_after_wait`、D-3 `forecast_settle_eval` 與等待欄位；對應事先宣告 LG-29 (a)～(j)、(h′)；風控 R14-1～R14-5、R14-9）：fixture 用離線的假市場 DB、假主 DB 與假的 `app.services.index`。
  - (a)（LG-29 (a)）個股 T+h bar 在 T+h 之後第 2 個觀察日才寫入 → 在第一次看得到它的評估寫入 `resolved`，`wait_sessions = 2`，`settle_source_run_max` 等於該評估的 `market_run_max`；之前兩次評估的 `waiting_json` 都含這筆預測。
  - (b)（LG-29 (b)；R14-1）判定視圖中已觀察到 D_5 的第一次評估仍沒有可用的 T+h bar → `missing_bar_after_wait`，`wait_sessions = 5`，`wait_deadline_session = D_5`。這次評估是 D_5 當晚的排程（store 時鐘早於 D_5 的 23:59:59），不延到 D_6。之後才寫入的 run 依 FL-64 (h) 只進診斷。
  - (c)（LG-29 (c)）只有定案前 run 的 T+h → 不可用，依 (a) 或 (b)。
  - (d)（LG-29 (d)）見 FL-64 (d)、(h)。
  - (e)（LG-29 (e)；O-1b）以存下的 `forecast_settle_eval`（R、E、V、大盤快照、`index_final_now`、`holiday_table_json`）重算 → outcome 列（含 `void_reasons_json`、`basket_excluded_members_json`、`wait_sessions`、`wait_deadline_session`）與 `observed_sessions_json` 逐位相同。評估之後以不同的值覆寫 `price_bars_cache` 的大盤列，再補寫 `run_id > R` 的 run 與 `event_id > E` 的事件 → 重算結果不變。
  - (f)（LG-29 (f)）label 互換後，等待與否、寫入的評估、`status`、`void_reasons_json`、`wait_sessions` 逐位相同；涵蓋 (h′) 與 (i)。
  - (g)（LG-29 (g)；強制重抓）大盤 T+h 定案 bar 隔日才擷取 → 等待後結算，不會停在未結算。另加：
    - T+h 當晚快取只有非定案列、(i) 已有 T+h → 強制重抓恰好一次（spy 計次）；
    - 重抓取得定案列 → 當次結算，`index_refetch = refetched`；
    - 重抓後仍沒有 → 等待；
    - 重抓拋例外 → `refetch_failed`，等待；
    - 沒有缺漏 → 不重抓，`not_needed`。
  - (h)（LG-29 (h)）族群排除後覆蓋在第一次評估 < 90%、之後 ≥ 90% → 在 ≥ 90% 的那次評估結算。
  - (h′)（LG-29 (h′)）至判定視圖中已觀察到 D_5 的評估仍 < 90% → `void_reasons_json = ["basket_coverage_below_90"]`，`diag_basket_with_excluded` 以同一個判定視圖計算，`wait_sessions ≥ 5`。
  - (i)（LG-29 (i)；R14-2）大盤 P(T) 收盤確認有誤、等待期間取得正確值 → 在取得當次的評估結算為 `resolved`，記明所用來源；該正確值所在紀錄的序號 ≤ 該評估的 `index_check_max`，序號大於者不採用。至 D_5 評估仍未取得 → `index_bar_confirmed_erroneous`，`wait_sessions ≥ 5`。
  - (j)（LG-29 (j)；R14-5 ②）每一列的 `wait_sessions` 等於寫入當下 `observed_sessions_json` 中晚於 T+h 的日數。評估停擺 3 個觀察日後恢復、期間的觀察日事後才進入視圖 → 期限評估寫入一列，`wait_sessions > 5`，`wait_deadline_session` 仍等於 T+h 之後第 5 個觀察日。
  - (k)（全量與 AST）
    - `run_settlement_evaluation()` 的簽章沒有 R、E、V、視圖、預測清單或判定結果參數；
    - `forecast_outcome` 的排程結算寫入只從它呼叫；
    - `settlement.py`、`scoring.py` 不以 `as_of` 呼叫 `observed_sessions`；
    - 等待判定的呼叫圖不 import、也不讀 label、`hit`、基準命中與驗證統計；
    - 一次評估中，市場 DB 的 `MAX(run_id)` 只讀一次；大盤列只讀一次，重抓時再讀一次（spy 計次）。
  - (l)（寫入驗證）以下各自拒絕：
    - 結算評估列的 `settle_eval_id` 為 null；
    - `settle_source_run_max` ≠ `market_run_max`；
    - `void_reasons_json` 含等待類原因，而 `wait_sessions < 5`；
    - `wait_deadline_session` 與 `wait_sessions` 不一致；
    - 更正列的三個欄位與被 supersede 列不同；
    - `waiting_json` 中的預測在同一個交易內有 outcome；
    - `index_series_sha256` 指向不存在的列。
  - (m)（不切分與倒退）
    - D-7.7 期限已到 → 不寫任何 `forecast_settle_eval` 與 outcome 列；
    - 評估交易中途拋例外 → 兩者都沒有任何列；
    - R 小於前一列的 `market_run_max` → 記 WARNING，不寫入。
  - (n)（N-21 風控 suggested）② 與 ④ 之間注入 on-demand 紀錄 → 該筆不在 outcome 與 `waiting_json`，`eval_set_count` 不含它，下一次評估納入；U 為空 → 寫一列 `forecast_settle_eval`，`view_range_json` 首尾都是評估當日，`last_settle_eval_at` 前進；② 之後 U 的某筆被其他寫入者寫入 outcome → 整個評估不寫入。
- **FL-66**（v0.14 V14-03；D-9.3 `split_or_reduction_suspected` 的 g 與換算門檻；對應事先宣告 LG-30 (a)～(l)；風控 R14-13、R14-14）：表格驅動加性質測試。
  - (a)（LG-30 (a)）全部 g ＝ 1 的序列：輸出與 v0.13 的原規則逐位相同（性質測試，含隨機 double，以及 c 附近以 `math.nextafter` 取得的鄰值）。
  - (b)～(e)（LG-30 (b)～(e)）四格照列，數值取自 LG-30。
  - (f)（LG-30 (f)）族群成員跨缺 bar 觸發 → 依 V14-02 排除該成員，`reasons` 含 `split_or_reduction_suspected`。
  - (g)（LG-30 (g)）沒有可用的 T+h bar → 只比對已有 bar 之間的相鄰對；其中 g ≥ 2 的相鄰對超過換算門檻 → `split_or_reduction_suspected`，`diag_last_close` 為 null（對應 LG-28 (d) 的 g ≥ 2 格）。
  - (h)（LG-30 (h)）`^TWII` 序列不呼叫 `split_suspect_exceeds`；事先宣告 §6.3 X4 的查證觸發照舊以單日 |r| > c 判定，不做 g 換算；`scope_kind = market` 的結算評估與更正作業中，`span_sessions` 呼叫次數為 0（spy）；重放路徑不 import `app.forecast.settlement`、`app.forecast.correction`，不呼叫 `span_sessions`、`unobserved_weekdays`、`ledger_registration_start`（AST，N-22）。
  - (i)（LG-30 (i)；AST）dirdef 沒有第二個門檻常數；以 g 換算門檻的運算只出現在 `split_suspect_exceeds`；該函式內沒有 double 的 `**`、`pow`、`math.pow`、`math.exp`、`math.log`。
  - (j)（LG-30 (j)；R14-13）
    - 窗內有一個未觀察平日，相鄰對跨越它而且沒有其他缺日 → g ＝ 2；
    - 該日登記之後補寫進入 (i) → 仍計入 g；
    - 登記事件的 `event_id` 大於該評估的 `ledger_event_max` → 不計入；
    - 結算窗內有符合 A-77 第 10 項判準、卻沒有登記事件的日期 → `span_sessions` 拋例外，該次評估不寫入任何列；
    - （B-3 回送；ADR 自有，不對應 LG-30；正常營運不觸發的對照格）以下 fixture 都經 `run_settlement_evaluation()` 執行，斷言 `span_sessions` 不拋例外、該日在 ④ 已登記、g 計入該日：(1) `late=1` 或 on-demand 紀錄的 T 早於該 claim 的 D_v，結算窗跨越 D_v 之前的未觀察平日；(2) 尚無任何 claim 有 D_v、只有逾時或 on-demand 紀錄；(3) 整檔還原使 D_v 移後（N-5），還原檔內有 T 早於新 D_v 的未結算紀錄；(4) 評估停擺數個觀察日後的第一次評估；(5) 啟動補跑；
    - 快照範圍以外、只屬於 (ii) 的日期 → 結算評估不登記它；同一次執行的缺日稽核也不登記它（該日 ∈ (ii)）；
    - 快照範圍以外、符合 A-77 第 10 項判準的日期 → 結算評估不登記它；同一次執行的缺日稽核登記它；
    - 更正作業：重查範圍內的日期 d 只在 `run_id > market_scan_to` 的 run 中屬於 (i) → 該作業的登記與判定都以 `market_scan_to` 界定 d，`span_sessions` 不拋例外；
    - 一次評估內（含 ③ 的 X2 確認寫入），`official_holiday_table_meta` 恰好讀一次、`official_holidays` 每個年度恰好讀一次（spy）；`forecast_settle_eval.holiday_table_json` 等於該次讀到的 meta；`ledger_registration_start()` 不晚於每個 claim 的 `claim_dv()`；
    - 結算評估中 `span_sessions` 拋例外 → 同一次執行的缺日稽核照常執行並寫入（D-7 第 2 點）。
    - X2 確認日 → 不計入。
  - (k)（LG-30 (k)；R14-14）
    - g ＝ 1、r ＝ +c 與 r ＝ −c → 都不觸發；
    - g ＝ 2～5，r 取精確上下界兩側最近的 double → 判定與以 `Fraction` 寫成的參考實作相同；
    - g ＝ 1 時精確路徑與 |r| > c 一致（性質測試）；
    - g 為 0、負數或非 `int` → 拋例外。
  - (l)（LG-30 (l)；風控 2026-10-18 v0.14 單項確認）h ＝ 5、窗內有 1 個已登記的未觀察平日、相鄰對 (T, T+5) 跨越整個窗 → g ＝ 6；r ＝ −50%（下界 −50.30%）→ 不觸發、`resolved`；事先宣告 §4.2「跨缺 bar 的大幅變動」② 與 ③ 都計入。
- **FL-67**（C-22；D-3 `forecast_index_check`；N-23；N-24）：
  - (a) 對應表每一列各一格，斷言寫入的列種與欄位。
  - (b) 同值的 bar 第二晚再偵測，不寫新的 detection，也不寫新的 ① 查證；`fetched_at` 不同、值相同，視為同一身分；值改變則是新身分。
  - (c) 獨立來源已接入時，每次評估中，`check_id` 落在 (前一列 V, 本列 V] 的 `daily_recheck` 列，涵蓋前一列 V 時的全部待查證列；來源版本第一次出現時是 `source_onboarding`，不另做 `daily_recheck`。
  - (d) 寫入驗證各一格拒絕：`direct` 用在需查證的項目；`no_error` 與 `close_erroneous` 並存；`correct_close_obtained` 沒有先行的 `close_erroneous`；`conflict` 寫入任何 determination；非 detection 列的 `session_date` ≠ 所指 detection 的值；FL-19 (c)③ 加格：`verification_ref` 指向非 verification 列、`x2_case = conflict` 的列，或其他 `session_date` 的列；`correct_close_obtained` 的 `target_values_sha256` 與所指 `close_erroneous` 不同。
  - (e) 評估讀 V 之後再插入的判定列不採用（對應 LG-29 (i)）。
  - (f) 寫入呼叫點只有 recorder 與 D-9.2 ③（AST）。
  - (g) N-23：結算拋例外、R 倒退、期限已到三種情形各一格 → 缺日稽核寫入、驗證快照與 plan 都不寫、不出現 fail-closed 列；23:10 重試成功 → 補寫兩者；缺日稽核失敗 → 快照不寫；更正作業已啟動、沒有寫入 job_end → 驗證快照與 plan 都不寫。
  - (h) N-24：S 的 `late_cutoff_at` 之前稽核 → 不寫 S 的缺日列；22:10 記錄失敗、23:10 重試寫入 `late=0` → 隔晚稽核不寫缺日列；只有逾時紀錄 → `late_only`；gap_judged_through 等於最近一次成功稽核已判定的最晚觀察日；S 的 late_cutoff_at 之前，缺日率的分子分母都不含 S。
  - (i) X3 兩次擷取都與獨立來源不符，或 X4 相鄰兩日都不符 → 各寫一列 `close_erroneous`（`target_values_sha256` 不同），不違反唯一性；同一列同一種判定第二次寫入 → 拒絕。
  - (j) 同日已有 `close_erroneous`、沒有 `correct_close_obtained`，來源修訂值與已確認有誤的那次擷取構成 X3、在待查證集合內 → 不算取得正確值；等待期滿依 `index_bar_confirmed_erroneous` 作廢。
  - (k) `views`、API route、匯出 import 或呼叫本表的讀取函式 → AST 失敗；C22-1 所列的讀取呼叫點各一格可以讀。
  - (l)（suggested (a)）查證列與導出的 X2 確認同一交易：在兩次插入之間注入例外 → 兩者都不存在；重算後 d ∈ D-8.1 (i) → 查證列存在、事件不存在、記 WARNING，detection 仍在待查證集合；從其他呼叫點以既有查證列的 `check_id` 寫入 `basis = verified` 的事件 → AST 失敗。
  - (m)（suggested (b)）`x2_pending`、`set_iii_only` 的 d 在偵測之後進入 D-8.1 (i)，之後的 ② 取得 d 的數值 → 寫入 `no_error`，detection 離開待查證集合；同一情形改為「來源沒有這一天」→ 依 (l) 不寫 X2 確認，detection 留在集合內。
  - (n)（N-24 存放處）稽核成功 → `forecast_gap_audit` 恰好一列，與該次的 `forecast_gaps` 列同一交易；稽核在寫入前拋例外 → 兩者都沒有，`last_gap_audit_at`、`gap_judged_through` 不前進；status 回傳值等於最新一列的 `audit_now`、`judged_through`（AST：API route 不 import `late_cutoff_at` 的函式）；驗證快照的 `stats_json.gap_audit_id` 等於本次稽核的 `audit_id`；寫入驗證三種拒絕各一格：已判定的日子不是前綴、`gaps_written` 不符、缺日列的 `session` 晚於 `judged_through`。
- **FL-68**（N-21；D-9 第 5 點、D-3 `forecast_correction_job`）：
  - (a) 以存下的 `forecast_correction_job` 重算，supersede 列與 `forecast_void_late_diag` 列逐位相同；作業開始之後注入 `run_id > market_scan_to` 的 run、`event_id > ledger_event_max` 的事件、`check_id > index_check_max` 的判定列，或覆寫 `price_bars_cache` 的大盤列 → 結果不變。
  - (b) 一次作業中，`MAX(run_id)`、`MAX(event_id)`、`MAX(check_id)`、大盤列、`official_holiday_table_meta` 各恰好讀一次（spy）；不強制重抓。
  - (c) `view_range_json.start` 等於 D_reg；結算窗早於最近一次結算評估快照起點的舊預測，仍能以本作業快照重算。
  - (d) 只有 X2 事件觸發（沒有市場 DB 命中）→ 作業啟動；只有確認判定列觸發 → 作業啟動；`no_error` 判定列 → 不啟動。
  - (e) 中斷作業之後的下一個作業，兩個 from 等於前一個已完成作業的 max，重新讀得同一批觸發；性質測試：已完成作業的 (from, max] 首尾相接、不重疊（三種序號各一）。
  - (f) 簽章沒有觸發、預測清單、重查範圍、視圖、E、V 參數（AST）；supersede 寫入只從 `run_correction_job()` 呼叫。
  - (g)（風控 C-22 確認）結算之後改寫 `price_bars_cache` 中前一列結算窗內某日的值 → 重算取「更正鏈中最早涵蓋該日的列」的快照值，記 WARNING，結果與沒有改寫時逐位相同；X2 順延後的新 T+h bar 不在任何 `settle_eval_id ≤ settle_eval_max` 的 `forecast_settle_eval` 快照中（或數值不同）→ 該筆不寫入，`rejected_count` 加 1，`rejected_json` 與 `pending_json` 各一項（`shift_index_bar_unverified`）。
  - (h) 啟動檢查不讀 label、`hit`、結果（AST 列舉 import）；更正作業沒有 CLI 或 API 入口（AST 列舉呼叫點）。
  - (i)（N-27）更正作業在被重查列的 D_5 之前啟動，判定視圖中 P(T+h) 收盤「確認有誤、尚未取得正確值」→ 當次寫入作廢列，不延後；`wait_sessions`、`wait_deadline_session` 等於被 supersede 列；之後的作業取得 `correct_close_obtained` → 不 supersede 該作廢列，只寫 `forecast_void_late_diag`。
  - (j)（N-29）三種待重算各一格（尚未觀察到、沒有可用資料、大盤列未經偵測）→ 不寫 supersede 也不寫作廢，`rejected_json`、`pending_json` 各一項，紀錄清單回傳待重算片段，不含 label 與實際結果。下一次結算評估帶來新觀察日，或含 d、而且數值是新出現的快照列 → 第四類觸發啟動，寫入 supersede（`correction_causes` 含 `x2_session_removed`），該項離開 `pending_json`，畫面改為 LM-150＋LM-151。沒有任何新資料的評估 → 不啟動（spy）。（(γ)；風控 2026-10-18 確認）大盤項：23:10 重試與啟動補跑各再寫一列 `forecast_settle_eval`，d 的列與 W_S 以內某一列快照數值相同 → 不啟動（spy），沒有新的 job_end，`e_changed_since` 維持為假；d 的數值改變 → 啟動；各次執行的數值依序為 A、B、A → 只有 B 那一次啟動；W_S 以內的快照都沒有 d 的列 → 啟動；`write_validation_failed` 的大盤項在重試時不啟動，新觀察日照常啟動。（風控 2026-10-18 確認，(g)「優先序」與 D-9 第 5 點「待重算」）已確認 PIT 違規、鏈尾 `resolved`、在待重算集合 → 狀態行是待重算片段，資格標示並列 LM-110 與 LM-114（LM-114 排第一），回應不含 label 與順延前結果；`on_demand`、`late`、`before_dv` 各一格同理（分別並列 LM-113、LM-112、LM-111）；族群列且 A-27 (c) 成立 → 不回傳待重算片段，回應不含 `settlement_date`、`outcome_status` 與順延前結果；族群列且 (c) 不成立 → 不顯示 label 與任何結算結果；E 以外的列到期作廢 → §4.2 作廢數 (7) 計入、依 E 分列，作廢率與 W 不變。`write_validation_failed` 項修正後重查成為 `shift_t_plus_h_data_unavailable`：未到期 → 留在 `pending_json`、`reason` 改寫、`since_job_id` 不變；已到期（依 N-29 (b) 起算，不扣除被拒期間）→ 依 (乙) 改記作廢；等待資料項重查後成為 `write_validation_failed` → 到期不改記作廢。前一作業 `pending_json` 的某一項既沒有處理、也沒有帶入 → 拒絕寫入 job_end。X2 事件已寫入、作業尚未完成 → 該列回傳待重算片段。啟動檢查不讀時鐘差（AST）。重算含 `x2_session_removed` 而寫入驗證拒絕 → 列入 `pending_json`（`write_validation_failed`），回傳待重算片段，N-29 (b) 到期也不改記作廢。pending 項由其他類觸發重查 → `correction_causes` 含 `x2_session_removed`。前一作業的 pending 項本作業重算無任何欄位改變 → 不寫列、離開 `pending_json`，job_end 照寫。大盤 `shift_index_bar_unverified` 到期 → 視為沒有可用資料、改記作廢（成立集合含 `missing_bar_after_wait`），`diag_*` 不讀未通過比對的列（spy）。待重算片段不出現在本路徑以外；大盤待重算列不含 LM-22、`threshold_display`（schema 測試）。驗證統計不計入待重算集合；job_end 寫入後 `e_changed_since` 為真。（N29-11）週末 X2、順延後 T+h 不變：snapshot 在 (b) 期間寫入，之後作業不寫列、寫入 job_end → 到下一筆 snapshot 之前，`e_changed_since` 與 `n_disclosure_masked` 為真；下一筆 snapshot 的 n 含該列；`mask_episodes` 的變動項含該 job_end，日數為 1。對照格：同一次執行中，作業在驗證快照之前寫入 job_end → 該 snapshot 的 `e_read_job_end_seq` 涵蓋它，`e_changed_since` 為假。AST：`views` 讀 `forecast_correction_job_end` 的呼叫點恰好是 D-11.4 第 11 點 (g) 所列的兩個 `store.py` 函式。序號函式的 SQL 只選取 `correction_job_id`；其回傳值不出現在任何 response model 或匯出欄位（AST／schema 斷言）。
- **FL-69**（`INDEX_VERIFICATION_SOURCE` 版本歷史；`forecast_replay_index_check`；`forecast_replay_outcome`）：
  - (a) 登記序列目前為空；性質測試：版本逐項加 1、跨 `source_name` 單調、已登記項不可變、同名時涵蓋只增不減；程式序列與 ADR 登記表逐欄相同。
  - (b) `coverage_end_at` 在 `rolling` 時只依日期與時鐘；涵蓋以外 → `outside_coverage`，不呼叫來源（spy）；涵蓋以外寫 `source_has_no_day` → 拒絕。
  - (c) registration 之前寫 detection、snapshot 或 calendar_query → 拒絕；同一 claim 第二列 registration → 拒絕；第二份 snapshot → 拒絕；登記檔的 S、E、N_req 與重算結果不同 → 拒絕。
  - (d) 閘門 (1)～(4) 各一格不成立 → `gate_passed = 0`，`forecast_replay` 寫入被拒；gate 之後再寫 detection → 引用該 gate 的結果列被拒；重查只涵蓋部分失敗列 → gate 函式拒絕；`check_replay_gate` 不 import 報酬或標籤的模組，也不呼叫來源（AST、spy）。
  - (e) 重放路徑不寫 `forecast_index_check`、`forecast_ledger_events`、`forecast_outcome`（AST）。
  - (f) 結果列：`independent_source` 對應的查證列不是 `basis_check_id` → 拒絕；含 `wait_sessions` 等禁欄 → schema 失敗；X1 收盤本身不可用的 P(T+h) → `index_bar_confirmed_erroneous`，不讀同日 X2 查證列或日曆查詢列的值（spy）。
  - (g) `checked_values_sha256` 對 NaN 收盤的兩列相同；快照 sha256 重算逐位相同。
  - (h) 登記檔的 `F` 不等於 `freeze_evidence.merged_at` 的 Asia/Taipei 日期，或 `base_ref` 不是事先宣告所載的分支 → 拒絕寫入 registration 列。
  - (i) 取數失敗 → 寫 `fetch_failed` 列，之後可以再取；已有 `stored` 列後再取數 → 拒絕；回應取得後到寫入之間不呼叫其他讀取（spy）。
  - (j) 同一個 `source_name` 由 `rolling` 改為固定日期 → 性質測試判為縮小，拒絕。
- **FL-24**：預測端計分永遠使用原始列。
- **FL-50**（r1，A-11）：用表格驅動測試釘住 D-9.3 的兩點（`split_or_reduction_suspected` 的固定門檻、`basket_coverage_below_90` 以 T 日成員數計）。
  - （N-12；對應 LG-28 (d)）加一格：T+h 缺 bar，窗內已有的 bar 中有一日超過 `SPLIT_SUSPECT_ABS_RETURN` → 判為 `split_or_reduction_suspected`。
  - V10-08 定案之後，補族群成員分割一格。〔已決：V14-02，見 FL-22 LG-28 (i) 與 FL-66 (f)〕
  - （v0.14 V14-03）g ≥ 2 的換算門檻，以及 g ＝ 1 的逐位等價，見 FL-66；本條原有各格都是 g ＝ 1，照舊成立。
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
  - （N-5）加一格：還原到 D_v 之前。
  - （起算日）加兩格：
    - D_v 為 None → 找不到 LM-84、LM-85，也找不到 `before_dv`；
    - 兩個 claim 的 D_v 不同 → 各自渲染自己的日期。
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
    - （N-6）`mask_episodes` 加格：
      - 正常情形 → 1 日，不記 WARNING；
      - snapshot 漏一天 → 2 日，記 WARNING；
      - 序號缺漏的 snapshot 不涵蓋變動項；
      - 沒有 snapshot 時自 D_v 起算；
      - 注入倒退的時鐘，結果逐位相同。
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
      - （N29-11）RC‴-1 第 1、2、3、5 格對 `e_read_job_end_seq` 各加一格（第 3 格注入的是一筆 job_end commit；第 2 格另斷言依 N-5 撤銷 `better_than_baseline`）；寫入 `forecast_correction_job` 時指定 `correction_job_id` → 拒絕寫入；`sqlite_master` 斷言 `forecast_correction_job.correction_job_id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`。
      - （N-5）RC‴-1 六格之後加兩格：序號大於最大值時撤銷 `better_than_baseline`；還原後 `checkpoint_n ≤ N_R` 的檢查點正面結果不認列、負面結果照常生效。
        - 兩個原因同時成立的檢查點：`cause = suspended_f3`；有 withdraw 區塊時 `positive_suppressed_during_f3 = true`；§4.2「整檔還原」列含此檢查點。只有 `db_restored` 成立：`cause = db_restored`，`positive_suppressed_during_f3` 不為 true。
      - （N-5）N_R 邊界加一格：D_v 晚於 B_s。
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
  - （N-4；掛 A-65）加四格：
    1. 作廢列落在重查範圍內，資料已補到 → `forecast_void_late_diag` 寫一列，`forecast_outcome` 列數不變，job_end 計數為 1；
    2. 同一份資料重跑 → 不新增列；
    3. 診斷結果仍是作廢 → 不寫列，計數為 0；
    4. `views` 與 route 都不可達 `forecast_void_late_diag`（AST）。
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
10. （剩餘待決項，N-4）M-11 的表數隨 `forecast_void_late_diag` 由 10 張改為 11 張；全部表數由 15 張改為 16 張（知悉）。
11. （v0.14）V14-01、V14-02 為放寬，而且改動本 ADR D-9 的字面；核可本 ADR 時逐項明示同意，未明示前不得凍結 dirdef（風控 2026-10-18 v0.14 審查 R14-17）。V14-01 的明示同意涵蓋 D-9.2 的結算端強制重抓（補定義（兩面）：放寬面是大盤等待減少、少數原本會作廢的列改為結算；收緊面是重抓限定為每次評估、全市場、恰好一次，排除逐筆裁量；風控 2026-10-18 v0.14 單項確認）。
12. （v0.14，知悉）M-11 的表數隨 `forecast_settle_eval` 由 11 張改為 12 張，全部表數由 16 張改為 17 張（風控 2026-10-18 v0.14 單項確認：屬知悉，不需明示同意）。
13. （C-22，知悉）M-11 的表數隨 `forecast_index_check` 由 12 張改為 13 張，全部表數由 17 張改為 18 張（風控 2026-10-18 C-22 確認：屬知悉，不需明示同意）。
14. （N-24，知悉）M-11 的表數隨 `forecast_gap_audit` 由 13 張改為 14 張，全部表數由 18 張改為 19 張。
15. （N-22c、v0.16，知悉）M-11 的表數隨 `forecast_replay_index_check`、`forecast_replay_outcome` 由 14 張改為 16 張，全部表數由 19 張改為 21 張。

**風控**：附件 C 的重送與確認項；FL-30～FL-37 是否完整對應七條底線，請單項核對。

**quant**
- 在凍結版 dirdef 中列出：文字欄位的排除清單、M-3 的常數、C-8 的選擇、F-3 上限。
- 修正 v0.2 對解讀 A 的歸因（風控第 6 項第 1 點）。
- `plan_outcome` 的欄位定義另案提出。
- （r1 新增，A-15）：
  - `purpose` 對照表；
  - 逾時率不足 60 日時的算法；
  - 族群成員疑似分割的處理（排除該成員，或整筆作廢；若選排除，LM-65 的括號要重送）〔已決：v0.14 V14-02，排除該成員；LM-65 重送待 creative-lead 起草、風控核可，核可前 LG-21 失敗（風控 2026-10-18 v0.14 審查 R14-18）；V14-02 為放寬，CEO 明示同意前不得凍結 dirdef〕；
  - 作廢原因的判定順序（建議依序 `missing_bar_after_wait` → `dividend_factor_unusable` → `split_or_reduction_suspected` → `basket_coverage_below_90`）。〔已決：事先宣告 v0.13 V13-01。與本句的建議不同，`missing_bar_after_wait` 由第一改為最後；tech-architect 同意，理由見修訂紀錄 N-12〕

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
  - （第九、十批）A-77 第 12 項 (h5)：候選 T＝d 記 `inputs_not_ready` 的計數來源（風控第九批 S9-3，suggested；不擋 D_v）。〔已決：計數來源為 `session_calendar_conflict`（`origin = candidate_t_x2`），見 A-75 (iii)（N-3）〕
  - （第九、十批，事先宣告 v0.12 V12-20）補到資料後的診斷標籤，存放處由 TA 定：只增不改，不得寫入 `forecast_outcome`；D-9 結算程式實作前定案。〔已決：存放於 `forecast_void_late_diag`，見 D-3（N-4）〕
  - **O-1（後續追蹤清單 N-13）**：ADR-0027 D-9.1 第 2 點的 cutoff 與 §6.3「等待期間補到就結算」互相矛盾。O-1 定案前不得凍結。定案必須同時保證：(a) 等待期滿時，每一筆都恰為 `resolved` 或作廢之一，不得有兩者皆非、因而不在 n、作廢率與 W 任一項中的列；(b) 等待期間才寫入、但不能用於結算的 bar，必須落入結算，或落入 ADR-0027 `forecast_void_late_diag` 的晚到判準之一；(c) 「T+h 無 bar」指「沒有可用於結算的 bar」（含只有定案前 run 的情形，後續追蹤清單 N-16），不是字面上的「資料表沒有列」。〔已決：v0.14 V14-01，風控 2026-10-18 v0.14 審查有條件核可；(a)～(c) 的落實見 D-9.1、D-9.2、D-9.3 `missing_bar_after_wait`（R14-1、R14-3）；本列 (a)～(c) 原文保留作歷史紀錄（R14-17）；V14-01 為放寬，CEO 明示同意前不得凍結 dirdef〕
  - （v0.14 V14-01）事先宣告 §6.3「查證程序」的查證紀錄，以及 X1、X3、X4 確認判定紀錄的存放表：主 DB、只增不改、以 `INTEGER PRIMARY KEY AUTOINCREMENT` 為序號（D-9.2 的 V 依賴它）。D-9 結算程式實作前定案，送風控。〔已決：`forecast_index_check`，見 D-3（C-22，tech-architect 2026-10-18；風控 2026-10-18 C-22 確認）〕
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
  - （v0.14）V14-03 失效條件的規章查證（後續追蹤清單 N-18；凍結阻擋，風控 R14-15）。
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

---

> 剩餘待決項（N-3～N-12、起算日）套用（2026-10-18，tech-writer）。
> - **與事先宣告 v0.13（V13-01～V13-08）同批**：ADR-0027 與事先宣告 v0.13 任何一份都不得單獨 commit，比照 871e602：同一個 commit，或同一次 push 的相鄰 commit（風控 2026-10-18 審查第四節「批次安排」）。檔頭狀態維持 proposed。
> - **累計方向統計維持 18／2／9／1／3**（見上「第九、十批」段的方向表，合計 33）：本批不新增 A 號（也沒有 A-87 以後的條號），也不使任何一條換類別。本批掛載的 A-56、A-61、A-63、A-75、A-77 原本屬收緊類，A-65 屬含有條件放寬的兩面類，A-10、A-11 屬 r1，不在 33 條統計內（tech-architect 提案第一節；風控審查第四節「累計統計 18／2／9／1／3 由 coordinator 核對：沒有新增 A 號」）。
> - **來源與優先序**（來源檔都在 `work/reviews/`；衝突時排在前面的為準）：
>   1. 風控 `2026-10-18-ADR-0027剩餘待決項與v0.13提案審查-風控.md`：第四節「tech-writer ADR-0027 照改清單」；第二節 B 的逐字字句 R-3′、R-6′、R-7、R-8、R-9、R-10、R-11、R-15。**R-11 採甲法（`settle_source_run_max`），coordinator 定案，CEO 可推翻**；乙法（以 `resolved_at` 比較時鐘）未採用，改採乙法須回送風控單項確認。
>   2. tech-architect `2026-10-18-ADR-0027-N12與起算日修正補充-tech-architect.md`：N-12（`void_reasons_json`、D-9.3 三點、L617 與 L1835 的〔已決〕、FL 對應）；起算日修正（殘餘歧義成立，是否改詞待後續追蹤清單 N-15）。
>   3. tech-architect `2026-10-18-ADR-0027-剩餘待決項N3至N9與起算日提案-tech-architect.md`：N-9、N-3、N-4 的表（原「建議條文」改由風控 R-11 取代）、N-5（N5-1、N5-2 甲案、N5-3；乙案不寫）、N-6、起算日綁定三條。
> - 被取代的原文是 commit d7601f7 的 ADR 原文（下文 L 開頭的行號，指該 commit 的行號），逐字保留於下，掛在各自的條目底下；tech-architect 提案中從未落入 ADR、但被風控逐字字句取代的文字，標「提案原文」一併保留。引用區塊內的文字即原文；「新增」與「句尾加註」類條目沒有被取代的原文。
> - 本批沒有套用的 suggested 項目（風控審查標為 suggested，由各部門自行斟酌）：N-9 不變式加 `coverage_start` 為 1 月 1 日、`coverage_end` 為 12 月 31 日一格；N-6 WARNING「剛結束」的定義；N-5 devops-sre 於還原前另存各 claim 的 `display_state`，以及 N5-1 〔推論〕加「並行寫入中備份、還原」的 FLT。N-4 的 `market_scan_from`／`market_scan_to` 做成 `forecast_correction_job` 欄位一項，已由 tech-architect 疑義裁定第 3 項採用，見 N-4 段。風控 2026-10-18 疑義四項單項確認另標三項 suggested，本批同樣不套用：（一）D-11.4 第 11 點 (h) 第 4 類 `dividend_factor_corrected` 之後也加同一個 N-17 註；（二）FL-64 (f) 的大盤 × `dividend_factor` 本來就不適用（風控說明：大盤用價格指數，不套用除權息因子），報表可考慮標「不適用」，和「未涵蓋」區分；（三）中斷作業（或 job_end 被拒的作業）已經寫入的 `forecast_void_late_diag` 列，之後的重跑因為鏈去重不會再寫，結果是逐作業的 `void_late_data_count` 合計會比 diag 表以 `forecast_id` 計的筆數少（風控建議 tech-architect 在 §4.2 (iv) 另列「沒有 end 列的作業寫入的 diag 列數」，或寫明以 diag 表為準；風控註明這是原本就有的問題）。

**N-9（D-7 第 3 點 K-10；掛 A-75 的 A-96″，連帶 A-77；方向：補定義（收緊））**
- 本批（2026-10-18，tech-writer；tech-architect 提案 N-9；風控 2026-10-18 核可，補定義（收緊））：D-7.3 K-10 第一子點（L398）原文——
  > - A-75 (iv) 與 A-77 第 2、4 項所稱的「已接入官方休市日表」，和 ADR-0028 `OfficialSessionCalendar`（T1-13）使用同一份來源、同一個函式定義，涵蓋年度也相同（ADR-0028 VS-5）。超出涵蓋年度時，兩邊同樣視為沒有官方休市日。

  改為見 §D-7 第 3 點 K-10 第一子點（凡提及處一律適用）。K-10 下新增「表的中繼資料也只有一個來源」一點（`official_holiday_table_meta`），FL-19 (i) 加四格，皆無被取代原文。

**N-3（D-7 第 3 點 A-75 (iii)、D-8 第 1 點第 5 項與第 12 項 (h5)、FL-19 (h5)(h6)；掛 A-77，連帶 A-75；方向：補定義（收緊））**
- 本批（2026-10-18，tech-writer；tech-architect 提案 N-3；風控 2026-10-18 核可）：D-8.1 第 5 項 payload 子點（L487）中被取代的兩處原文——
  > - `origin ∈ {x2_check, candidate_t, post_x2_final_run, post_unobserved_backfill}`
  > - `independent_source_absent` 只用於 `origin = post_x2_final_run`（見第 12 項）。

  改為見 §D-8 第 1 點第 5 項（`origin` 加 `candidate_t_x2`；`independent_source_absent` 改用於 `origin ∈ {post_x2_final_run, candidate_t_x2}`）。該子點的其餘文字（包含 `post_unobserved_backfill` 依風控 2026-10-18 Q3-7 加入的括號註、`registered_unobserved_weekday` 一句）不變；tech-architect 提案沒有說明該括號註是否一併取代，保留原樣。
- 本批（同上）：FL-19 (h5)(h6)（L1484-1485）原文——
  > - (h5) 候選 T＝d → `inputs_not_ready`；
  > - (h6) direct 與 verified 各一格。

  改為見 §對實作的約束 FL-19 (h5)(h6)，並加一格。
- 本批（同上）：A-75 (iii) 處理句（L392）之後新增「(i) 成立、(iii) 不成立時」一點；A-77 第 12 項 (h5) 句尾（L575）與待決事項（L1879）加〔已決〕；皆無被取代原文。

**N-4（D-3 `forecast_void_late_diag`、`settle_source_run_max`、晚到資料的觸發；掛 A-65（R10-3）；方向：補定義（收緊），A-65 不換類別）**
- 本批（2026-10-18，tech-writer；tech-architect 提案 N-4 的表；風控 2026-10-18 R-8、R-11）：`forecast_void_late_diag` 一表與用途限制，無被取代原文；見 §D-3。
- 本批（同上）：提案原文（tech-architect 提案 N-4「建議條文」，從未落入 ADR；被風控 R-11 取代）——
  > - （N-4）**晚到資料的觸發**：一筆 ok run 新寫入 session s 的 bars，而且主 DB 有結算窗 [T, T+h] 含 s、`status ≠ resolved` 的鏈尾列時，這筆 run 視為「來源修訂」觸發，帶 `run_id` 納入下一次更正作業的 `triggers_json`。

  改為見 §D-3 的「晚到資料的觸發」（風控 R-11 甲法逐字）。風控取代的理由：原條文沒有寫由誰起動，而 D-3 規定「沒有觸發就拒絕執行」，若掃描只在更正作業啟動時跑，沒有其他觸發時就永遠不會掃，計數會無聲低報；本 ADR 的判定一律用序號，不用時鐘。甲法新增 `forecast_outcome.settle_source_run_max`，無被取代原文。
- 本批（同上；風控 R-8）：D-3 `forecast_correction_job_end` 段（L299）句尾、D-11.4 第 11 點 (h) R10-3 一點（L1049）「補到資料的筆數記在…」一句之後，各加指向 `forecast_void_late_diag` 與「晚到資料的觸發」的註記，原文不改；L1049 句尾與待決事項（L1880）加〔已決〕，原文不改。理由（風控）：不加的話，舊定義和新的操作定義並存，舊句就不屬實。
- 本批（2026-10-18，tech-architect 疑義裁定第 1 項；方向：不變）：表數隨 `forecast_void_late_diag` 加 1。計數口徑：D-3 列出的每一張主 DB 表（含 `plan_*`）；M-11 的新增數為其減去 ADR-0025 D-6.1 原有的五張。評估摘要「最大代價」原文——
  > - 表數多（15 張），寫入規則有一部分在 trigger 裡。

  Consequences「代價與壞處」原文——
  > - 15 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。

  M-11 列原文（修訂清單表）——
  > | **M-11** | D-6.1 表清單〔`:376-381`〕；F-3〔`:581`〕 | 五張表；F-3 只寫「暫停顯示，查明」 | 新增 10 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`）並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6） | R-106、R-112、R-113；風控第 9 項 |

  改為 16 張表；M-11 改為新增 11 張表；CEO 待決事項第 9 點原文不改，另加第 10 點（知悉）。
- 本批（2026-10-18，tech-architect 疑義裁定第 3 項；採風控 R-11 suggested 的作法；方向：補定義（收緊））：D-3 `forecast_correction_job` 欄位清單原文——
  > `forecast_correction_job(correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT, triggers_json, recheck_range_json, started_at)`

  改為見 §D-3（加 `market_scan_from`、`market_scan_to` 與其子點）。本批前言「沒有套用的 suggested 項目」清單中「；N-4 的 `market_scan_from`／`market_scan_to` 做成 `forecast_correction_job` 的欄位」一句同步刪去（原句尾：「…以及 N5-1 〔推論〕加「並行寫入中備份、還原」的 FLT；N-4 的 `market_scan_from`／`market_scan_to` 做成 `forecast_correction_job` 的欄位。」）。
- 本批（2026-10-18，tech-architect 疑義裁定第 5 項；方向：補定義（收緊））：新增 FL-64，無被取代原文；見 §對實作的約束 FL-64。(f) 的「〔第 2 項採甲版時〕三個 scope × `dividend_factor`」標記，已於風控 2026-10-18 單項確認後改字，見下一條。
- 本批（tech-architect 疑義裁定第 2 項；風控 2026-10-18 單項確認：採甲版，加已結算列的因子更正一句與「原因怎麼歸屬」的 N-17 註；乙版否決）：「晚到資料的觸發」第 6 點原文——
  > 除權息因子晚到走「因子修訂」觸發（ADR-0016 D-5.2）；

  改為見 §D-3「晚到資料的觸發」第 6 點（風控逐字字句，來源 `work/reviews/2026-10-18-ADR-0027疑義四項單項確認-風控.md` 第二節第 1 項）。理由：被取代的出處是持倉鏈的覆蓋判定來源（主 DB `dividend_sync_runs`）；預測鏈的除權息事件依 D-4 第 2 點取自市場 DB，FL-5 禁止 `app/forecast/**` 讀主 DB 的 `dividend_events`。〔甲版另加：「因子修訂」觸發在本 ADR 沒有偵測定義，列後續追蹤清單 N-17〕
  - 同一次單項確認的另外兩處：D-11.4 第 11 點 (h)「原因怎麼歸屬」第一個子點句尾加 N-17 註（無被取代原文）；FL-64 (f) 原文「〔第 2 項採甲版時〕三個 scope × `dividend_factor`」改為「三個 scope × `dividend_factor`（N-17 定義落地前）」。
  - 方向：收緊（揭露）＋補定義（風控）。事先宣告 v0.13 V13-08 (iv) 由 quant 同批改，不在本 ADR。
- 本批（2026-10-18，tech-architect 疑義裁定第 3 項附帶；風控 2026-10-18 單項確認（加 job_end 時的 W 與 id 驗證）；方向：補定義（兩面；淨效果收緊））：「晚到資料的觸發」第 5 點被取代的原句——
  > 同一個 `(run_id, recorded_at)` 不得出現在兩個作業的 `triggers_json`。

  改為見 §D-3「晚到資料的觸發」第 5 點（風控逐字字句，來源同上第二節第 2 項），FL-64 (e) 新增兩格。理由（tech-architect 疑義裁定、風控單項確認）：原字面與 D-3「中斷作業由下一個作業完整重跑」、第 2 點「W 不因中斷作業前進」互相衝突，作業一旦中斷，後續作業會永久卡住。風控另指出作業並行、而且交錯完成時有同樣的卡死路徑（作業 B，id 1，掃 (0,25]，先開始；作業 A，id 2，掃 (0,20]，後開始；兩者都完成，W 取 A 的 20；下一次掃描重新掃到 B 在 (20,25] 的觸發，開始時被「已完成作業不得重複」擋下）；風控註明這個情境依條文字面推出，沒有確認更正作業實際上會不會並行。
  - 提案原文（tech-architect 疑義裁定第 3 項附帶的取代字句，從未落入 ADR；風控補上 W 與 id 驗證後取代）——
    > 同一個 `(run_id, recorded_at)` 不得出現在兩個已有 `forecast_correction_job_end` 列的作業的 `triggers_json`：作業開始時對照已完成的作業驗證；寫入 job_end 時再驗證一次，不成立就拒絕寫入 job_end（該作業視為中斷，依 D-3 由下一個作業完整重跑）。沒有 end 列的中斷作業的觸發，由下一個作業依第 2 點重新掃得，不受此限。
- 本批（2026-10-18，tech-architect 疑義裁定第 3 項 (3b)；風控 2026-10-18 單項確認：核可並修改，加「只是下限」的註明；方向：收緊（揭露）＋補定義）：D-3 `forecast_correction_job` 欄位清單在 `market_scan_to INTEGER NOT NULL` 之後加 `market_scan_restore_suspected`；(3a) 子點之下新增 `market_scan_restore_suspected` 一點；FL-64 (g) 句尾加字。無被取代原文。提案原文（tech-architect 疑義裁定 (3b) 的子點句，從未落入 ADR；風控不採用）——
  > 第 8 點成立時 `market_scan_restore_suspected` ＝ 1，否則為 0；§4.2「可能不完整」的期間，由這一欄為 1 的作業逐列數出。

  - 編號更正：風控原字句為 N-18，因追蹤清單編號已用，coordinator 改編 N-20，語意不變（coordinator 裁定，CEO 可推翻；N-18 已用於 V14-03 規章查證）。
  - 事先宣告 v0.13 V13-08 (iv) 的涵蓋邊界一句與修訂列方向欄，由 quant 同批改，不在本 ADR。

**N-5（D-11 第 2 點 N5-1、N5-2 甲案，D-14 N5-3，Consequences，FL-48、FL-58；掛 A-63（RC‴-1）、A-77 第 11 項（R10-7）、A-10（D-14）；方向：補定義（收緊））**
- 本批（2026-10-18，tech-writer；tech-architect 提案 N-5；風控 2026-10-18 裁定：N5-1、N5-3 核可，N5-2 採甲案、駁回乙案；R-9、R-10）：N5-1、N5-2、N5-3 與 Consequences 的「甲案的殘餘」，無被取代原文。乙案（`checkpoint_n ≤ N_R` 的檢查點，F-2 條件一的 `fail(c)` 一律視為成立）不寫入條文；風控駁回的理由是它使 LM-75、LM-87 不屬實，且違反 F-2 B 型「只計點估計 ≤ 基準這種負向證據」。
- 本批（同上）：N5-2 的統計面規則由 quant 在事先宣告 v0.13 登記（V13-07）；本 ADR 條文維持 tech-architect 提案原句「登記之前照本點處理」。
- 本批（2026-10-18，tech-architect 疑義裁定第 4 項 (4a)；方向：不變）：A-28 (ii) 原文——
  > - 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}}`；

  改為見 §D-11 第 4 點第 12 項 (ii)（加 `cause`，同步 N5-2；N5-2 寫「記法比照 A-28 (ii)」，被比照處原本沒有這個欄位）。裁定第 4 項 (4b)（兩個原因同時成立時的 `cause` 取值，以及 `positive_suppressed_during_f3` 的適用範圍）已於風控 2026-10-18 單項確認後套用，見下一條。
- 本批（2026-10-18，tech-architect 疑義裁定第 4 項 (4b)；風控 2026-10-18 單項確認：核可，補「兩邊」指的是哪兩邊；方向：補定義（收緊））：A-28 (ii) 之後、「有 `withdraw` 區塊時」之前，新增 `cause` 取值一點；FL-58 (e)「（N-5）RC‴-1 六格之後加兩格」一格之下新增一格（來源 `work/reviews/2026-10-18-ADR-0027疑義四項單項確認-風控.md` 第二節第 4 項）。無被取代原文。提案原文（tech-architect 疑義裁定 (4b) 的句子，從未落入 ADR；風控補字後取代）——
  > - （N-5 甲案；`cause` 的取值）同一個檢查點兩個原因同時成立時，`cause = suspended_f3`（與第 12 點的優先序一致）。`cause` 只供稽核與 quant 的檢查點檢討紀錄使用；§4.2「因本點而不認列的檢查點」（D-11 第 2 點 N-5 甲案）依 `restore_checkpoint_bound` 判定，不依 `cause`，所以兩個原因同時成立的檢查點兩邊都計入。下一點的 `positive_suppressed_during_f3` 只在 `suspended_f3` 成立時設定，不因 `db_restored` 而設定。

**N-6（D-11 第 4 點第 11 項 (c) RC′-2 子點，FL-52；掛 A-63（C9-7 甲案）；方向：補定義（收緊））**
- 本批（2026-10-18，tech-writer；tech-architect 提案 N-6；風控 2026-10-18 核可）：`mask_episodes` 遮蔽期的計數來源，緊接在 `n_disclosure_masked` 一點（L844）之後新增；FL-52 加格；皆無被取代原文。

**N-12（D-3 `forecast_outcome` `void_reasons_json`、D-9.3 三點、L617、L1835、FL-22、FL-50；掛 A-65，連帶 A-11；方向：補定義（收緊））**
- 本批（2026-10-18，tech-writer；tech-architect 補充 N-12；風控 2026-10-18 核可，R-3′、R-6′、R-7）：D-3 `void_reasons_json`、D-9.3「判定順序」「判定時點」「部分窗口」三點，無被取代原文；見 §D-3、§D-9 第 3 點。
- 本批（同上）：提案原文（tech-architect 補充 N-12「部分窗口」的後兩個子點，從未落入 ADR；被風控 R-7 取代）——
  > - 「單日報酬」指相鄰兩個觀察日都有 bar 的日子。
  > - 跨越缺 bar 日的報酬是否也要比對門檻，現行字面沒有涵蓋，交 quant 在凍結前提案；提案核可之前照現行字面。

  改為見 §D-9 第 3 點「部分窗口」（風控 R-7 逐字）。取代的理由（風控）：原句寫成定義，又寫「提案核可之前照現行字面」，等於先替 N-14 選了不保守的一邊，而且沒有並陳另一面。
- 本批（同上）：L617 句尾加〔已決〕；L1835（待決事項 quant 段）句尾加〔已決〕，L1835 原句不改；皆無被取代原文。
- 本批（同上；tech-architect 補充 N-12「修訂紀錄 N-12 的理由」逐字）：
  > 同意 V13-01 的順序。除了 quant 的三個結構理由，ADR 端另有一點：R10-3／V12-20 規定作廢列一經寫入，原因不因之後補到的資料而改變。五個原因中，只有 `missing_bar_after_wait` 是由「沒有資料」得出的，可能被晚到的資料否定；其餘四個都有正面證據，資料補到之後仍然成立。排在最後，寫定的 `status_reason` 就不會和之後補到的資料矛盾。L1835 原本的建議沒有附理由，撤回。
- 本批（同上；風控 R-3′）：D-9.3「判定時點」第二子點句尾的 O-1 但書，以及待決事項 tech-architect 段新增的 O-1 一列，無被取代原文。O-1 定案前不得凍結。

**起算日（D-14；掛 A-10，連帶 A-56（LM-99）、A-61（LM-111）；方向：補定義（收緊））**
- 本批（2026-10-18，tech-writer；tech-architect 提案「起算日」與補充修正；風控 2026-10-18 核可三條綁定、R-15 的 ADR 端）：D-14 D_v 定義下新增 `claim_dv` 的三條綁定，無被取代原文。tech-architect 補充修正的結論是：值的綁定符合 D-14，但「紀錄起算日」的詞義殘餘歧義成立，是否改詞待後續追蹤清單 N-15；改詞的話 LM-84、LM-85、LM-99、LM-111 四句同批重送（字面遷移清單 L3544，轉引 tech-architect 補充），不改詞則不觸發重送。

**D-8.1 第 9 項（F-8；掛 A-77；方向：不變）**
- 本批（2026-10-18，coordinator 裁定，CEO 可推翻）：D-8.1 第 9 項「**F-8（凍結前，待 data-engineer 查證）**」第一行原文不改，僅在句尾加註〔剩餘待決項註：data-engineer 2026-10-18 查證結論為 repo 內無法查證，需 CEO 本機代跑探測指令 §6.2；凍結前狀態以事先宣告 §9.2 與風控 v0.13 審查 R-4 為準〕；無被取代原文。註中的「§6.2」對應 `work/research/2026-10-16-Phase1資料源探測指令-CEO本機代跑.md` 的 §6.2（依 data-engineer 查證檔 `work/reviews/2026-10-18-晚到資料觸發與F-8前提查證-data-engineer.md` L26、L121）；「事先宣告 §9.2」「風控 v0.13 審查 R-4」依 coordinator 裁定字面轉錄，tech-writer 未逐一回查。

---

> v0.14 對應條文（V14-01～V14-03）套用（2026-10-18，tech-writer；tech-architect 起草，風控 2026-10-18 v0.14 審查 R14-4、R14-5、R14-12、R14-14 與單項確認）。與事先宣告 v0.14 同批：同一個 commit，或同一次 push 的相鄰 commit，任何一份都不得單獨 commit。被取代的原文以 commit d338006 的 ADR 為準。本批不新增 A 號；V14-01 掛 A-65（R10-3）與 A-11，V14-02、V14-03 掛 A-11、A-32；累計方向統計 18／2／9／1／3 不變，統計只涵蓋 A-54～A-86 的 33 條：V14-02、V14-03 掛的 A-11、A-32 屬 r1、r2，不在統計內；V14-01 掛的 A-65 原屬「含有條件放寬的兩面」類，不換類別；所以統計不變，不代表本批沒有放寬。V14-03 為收緊，另一面之一為放寬（R14-13），依事先宣告 V14-03 修訂列揭露，不列入 CEO 逐項明示；但本批含兩項放寬（V14-01、V14-02），CEO 核可時逐項明示（待決事項 CEO 段第 11 點）。
> - **來源與優先序**（來源檔都在 `work/reviews/`；衝突時排在前面的為準）：
>   1. 風控 `2026-10-18-ADR-0027-v0.14條文與事先宣告v0.14四項單項確認-風控.md`：第四節「tech-writer 照改清單」第 1～12 點；第二節 B 的逐字字句 B-1～B-10。
>   2. tech-architect `2026-10-18-ADR-0027-v0.14對應條文起草-tech-architect.md`：C-01～C-25 的條文、定位字串與被取代的原文。
>   3. 風控 `2026-10-18-v0.14草案審查-風控.md` 第二節 A 的 R14-4 原字句。
> - 定位一律用字串，不用行號。下列被取代的原文，取自套用前的 ADR 檔現況（任務說明：HEAD 為 d338006 之後的版本，ADR 本身沒有未 commit 的修改），並與 tech-architect 起草所引的被取代原文逐字比對一致；tech-writer 沒有用 git 對 d338006 逐字核對，請 coordinator 對照 d338006 核對。「提案原文」指 tech-architect 起草、從未落入 ADR、被風控逐字字句取代的文字。
> - 風控 C-25 附帶條件：統計的涵蓋範圍已寫入上段（B-8 插入句）。

**V14-01（D-9.1 第 2 點、D-9.2、D-9.3 `missing_bar_after_wait`、D-3 `forecast_settle_eval` 與等待欄位；掛 A-65（R10-3）、A-11；方向：放寬，CEO 明示同意）**
- 本批（2026-10-18，tech-writer；tech-architect C-01；風控 2026-10-18 v0.14 審查有條件核可）：D-9.1（觸發條件）被取代的原文——
  > 1. **觸發條件**（三者都要成立）：
  >    - 觀察到第 h 個交易日 T+h；
  >    - 該日資料的 `recorded_at ≤ cutoff(T+h)`；
  >    - `valid_until_session` 已過（AV-18）。

  方向：放寬（結算可以讀 `recorded_at` 晚於原 cutoff 的資料）；另一面為補定義：補上 O-1c，大盤 T+h 晚到時不再既不結算也不作廢。
- 本批（同上；tech-architect C-02；風控 R14-4、R14-5 ①）：D-9.2 被取代的原文——
  > 2. **結算資料**：個股用 `as_of(T+h)` 的 PIT 視圖，不得用 `_hindsight_view`；大盤用擷取的指數路徑。

  方向：放寬（V14-01 本體）＋補定義（收緊）（存值、全量、AST、R 倒退 fail-closed）；強制重抓一項為補定義（兩面），併入 V14-01 的 CEO 明示同意（風控 2026-10-18 v0.14 單項確認）。
  - 提案原文（tech-architect C-02 的引用，從未落入 ADR；風控單項確認指出事先宣告「觸發」段沒有「⑤」編號，是懸空引用，改字）——
    > （事先宣告 §6.3「觸發」V14-01 ⑤）

    改為「（事先宣告 §6.3「觸發」判定視圖一點的失效條件，風控 R14-7）」，見 §D-9 第 2 點「強制重抓」。
- 本批（同上；tech-architect C-03）：D-9.3 `missing_bar_after_wait` 被取代的原文——
  > - `missing_bar_after_wait`：T+h 無 bar，再等 5 個觀察日仍無 → `unresolvable_missing_data`

  方向：放寬；另一面：期限從時鐘改為序號（R14-1），作廢在 D_5 當晚就寫入，不延到 D_6。
- 本批（同上；風控 R14-4 逐字，加單項確認的更正作業句）：D-3 `forecast_outcome` 的 `settle_source_run_max` 欄位說明，以及「晚到資料的觸發」第 4 點，兩處被取代的原文（兩處逐字相同）——
  > 結算或作廢寫入當下，由寫入函式經 `MarketPanelReader` 自行取得市場 DB 的 `MAX(run_id)` 填入，不接受呼叫端傳入；大盤列為 null。比較只用序號，不用時鐘（比照 RC″-2）。

  兩處的取代文字（含「更正作業寫入的列，比照本點」一句）逐字相同。「晚到資料的觸發」第 9 點被取代的原文——
  > 9. 與 O-1 的關係：等待期間才寫入、在作廢寫入前已存在的 run，不屬於本點的晚到；這類 bar 的歸屬依 O-1 定案（後續追蹤清單 N-13）。

  - 提案原文（tech-architect R14-4 相容性核對的缺口一補句，從未落入 ADR；風控單項確認改為綁定 `market_scan_to`，不另讀 R，理由：更正作業啟動時已讀過一次 `run_max` 並存為 `market_scan_to`，再讀 R 會是第二次讀值，兩次之間插入的 run 會落在重算視圖內，卻又被下一個作業的掃描範圍當成晚到）——
    > 更正作業寫入的列，比照本點：由更正作業的寫入函式在作業啟動時讀一次 R，以 R 界定該作業的重算視圖，並把同一個 R 寫入該作業寫入的每一列；不接受呼叫端傳入。
- 本批（同上；tech-architect C-14，清單外連帶，風控核可）：D-3 `forecast_void_late_diag`「寫入者只有更正作業」第二子點被取代的原文——
  > - D-9.1 第 2 點的 cutoff 條件不適用，因為補到的資料本來就晚於 cutoff；其餘依 D-9.2、D-9.3。

  方向：補定義（收緊）。理由：D-9.1 第 2 點取代之後，原句指向的 cutoff 條件已不存在，等於懸空引用。
- 本批（同上；tech-architect C-12 與風控 B-5）：D-3 `forecast_outcome` 新增 `settle_eval_id`、`wait_sessions`、`wait_deadline_session`，無被取代原文。提案原文（tech-architect C-12 的兩句，從未落入 ADR；風控單項確認改字：k 存原值、不截斷，評估停擺之外另含「觀察日事後才進入判定視圖」）——
  > 正常排程下為 0～5。評估曾經停擺、期間的觀察日事後才進入視圖時，期限評估的值可能大於 5。
  >
  > （期限評估；k > 5 的筆數另列，表示評估曾停擺）

  - 其中第二句出現在 tech-architect C-12 的「§4.2 的資料來源」一點：「分列為 k ＝ 1～4，以及 k ≥ 5（期限評估；k > 5 的筆數另列，表示評估曾停擺）。」
- 本批（同上）：D-3 新表 `forecast_settle_eval`（C-13，表數 16→17、M-11 11→12）、D-1 模組表 `settlement.py` 一列與 `observed_days.py` 列句尾（C-15）、D-4.8 `CACHE_BAR_CONSUMERS` 第 3 項句尾（C-24）、D-9.3「判定時點」讀法子點（C-08）、FL-65（C-19），皆無被取代原文。
- 本批（同上；tech-architect C-23；方向：不變，CEO 知悉）：表數連帶，被取代的原文（各為該行整行）——
  > - 表數多（16 張），寫入規則有一部分在 trigger 裡。
  >
  > - 16 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。
  >
  > | **M-11** | D-6.1 表清單〔`:376-381`〕；F-3〔`:581`〕 | 五張表；F-3 只寫「暫停顯示，查明」 | 新增 11 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`；剩餘待決項 N-4 加 `forecast_void_late_diag`）並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6） | R-106、R-112、R-113；風控第 9 項 |

  改為 17 張、17 張表、新增 12 張表（加 `forecast_settle_eval`）。待決事項 CEO 段新增第 11、12 點（第 12 點為知悉，單獨一點，風控單項確認）。

**V14-02（D-9.3 `basket_coverage_below_90`、D-3 `sector` 允許集合、D-3 `basket_excluded_members_json`、A-32 套用的序列、FL-22、FL-50；掛 A-11、A-32；方向：放寬，CEO 明示同意）**
- 本批（同上；tech-architect C-04）：D-9.3 `basket_coverage_below_90` 首行被取代的原文——
  > - `basket_coverage_below_90`：族群籃子排除停牌或因子不可用的成員後，覆蓋 < 90% → `unresolvable_missing_data`

  方向：放寬（作廢面與 W 面，依 R14-10）＋ claim 層等待（V14-01 放寬）；整數判定一項為不變（實作精確化）。新首行把「停牌」改為「T+h 沒有可用 bar（停牌等）」並加等待一句，超出風控 R14-12 的要求，風控單項確認核可，事先宣告同步。
- 本批（同上；tech-architect C-10）：D-3 `void_reasons_json` 寫入驗證 `sector` 允許集合被取代的原文——
  > - `sector` ⊆ {`split_or_reduction_suspected`, `basket_coverage_below_90`}。V10-08 定案為「排除該成員」時，`sector` 收窄為 {`basket_coverage_below_90`}，與 V10-08 同批修訂本點。

  方向：補定義（收緊），寫入驗證收窄；實質方向隨 V14-02（放寬）。
- 本批（同上；tech-architect C-06、C-11、C-16、C-17）：A-32「套用的序列」句尾加、D-3 對照登記與 `basket_excluded_members_json`、FL-22 LG-28 (i) 與寫入驗證格、FL-50 句尾〔已決〕與一格，皆無被取代原文。C-06 的可選子點（A-32「字面」句尾〔v0.14〕註）與 D-9.3 `index_bar_confirmed_erroneous` 的期限一句（風控單項確認 B-10），皆為 suggested，本批採用。
- 本批（同上；tech-architect 第 7 小節第 11 點；風控單項確認第二節 A 第 11 點）：新列舉值 `t_plus_h_bar_unavailable` 與排序常數 `BASKET_EXCLUSION_REASON_ORDER`，無被取代原文（風控單項確認：核可，補定義（收緊），事先宣告要註明）。

**V14-03（D-9.3 `split_or_reduction_suspected`、「部分窗口」；掛 A-11、A-32；方向：收緊，另一面之一為放寬（R14-13））**
- 本批（同上；tech-architect C-05；風控 R14-13、R14-14、單項確認）：D-9.3 `split_or_reduction_suspected` 首行與第一子點被取代的原文（兩行）——
  > - `split_or_reduction_suspected`：結算窗內任一日，以套用可用除權息因子後的序列計算，單日簡單報酬的絕對值大於 `SPLIT_SUSPECT_ABS_RETURN`（台股一般漲跌幅限制 10% 加容差 1%，凍結在 dirdef）（推定，不是確認的事件） → `excluded_corporate_action`（r1，A-11）
  >   - 這是固定門檻，不看該標的當天實際有沒有漲跌幅限制。

  方向：收緊（跨缺 bar 的相鄰對新增比對）；另一面（R14-13）：跨越未觀察平日的相鄰對，門檻比現行讀法寬；R14-14 一項為不變（g ＝ 1 逐位等價）＋補定義（g ≥ 2 的算法）。g 以判定視圖中「已登記」的未觀察平日界定（tech-architect 第 7 小節第 6 點；風控單項確認：相對 R14-13 字面，對登記後才補寫進入 (i) 或 (ii) 的日期是放寬，結構理由同 R14-13），另加 fail-closed 子點（收緊）：結算窗內有符合 A-77 第 10 項判準、卻沒有登記事件的日期時，`span_sessions` 拋例外，該次評估不寫入。風控 B-3 附帶：登記範圍 [D_v, 最新觀察日] 若可能不涵蓋某些未結算預測的結算窗，tech-architect 須改提延伸登記範圍的方案並回送風控；不得讓這個 fail-closed 在正常營運中觸發。〔已決：tech-architect B-3 回送，風控 2026-10-18 B-3 回送確認；登記起點改為 D_reg，見 A-77 第 10 項、D-9.2 執行順序 ②與④（後續追蹤清單 N-21）〕
- 本批（同上；tech-architect C-09，風控單項確認：取代，不只加〔已決〕）：D-9.3「部分窗口」三行被取代的原文——
  > - **部分窗口**：T+h 缺 bar 時，`split_or_reduction_suspected` 以判定當下、結算窗內已有的 bar 評估（「任一日」照字面）。
  >   - 「單日報酬」在現行字面下讀為相鄰兩個觀察日都有 bar 時的報酬。跨越缺 bar 日的報酬是否也比對門檻，現行字面沒有涵蓋，待決 N-14（後續追蹤清單），凍結前定案；定案前不得凍結 dirdef。
  >   - 另一面（照實並陳）：現行讀法下跨越停牌日的公司行動判不到；T+h 有 bar 時，該列會以含未還原跳動的報酬結算並計入 n。

  方向：不變（指向）。實質方向在 D-9.3 `split_or_reduction_suspected`。取代的理由：風控 2026-10-18 v0.14 審查第二節 C 的連帶項目寫「移入〔v0.14 取代〕註」，同一份文件第四節 tech-writer 照改清單第 3 點寫「只加〔已決〕」，兩者互相矛盾；風控單項確認裁定以第二節 C 為準（取代），並更正自己的第四節第 3 點。前兩行照 tech-architect 原文，第三子點用風控單項確認 B-4。
  - 提案原文（tech-architect C-09 第三子點，從未落入 ADR；風控單項確認 B-4 取代：加 g ≥ 6 的分割偵測範圍與失效條件，並更正自己原先「g ≤ h ≤ 5，分割在全部情形下都偵測得到」一句）——
    > - 另一面依 V14-03 修訂列方向欄：g 大時門檻寬，跨長停牌的小幅減資仍偵測不到；跨越未觀察平日的相鄰對門檻較寬；停牌期間實際步數比 g 少，敏感度偏低。以事先宣告 §4.2「跨缺 bar 的大幅變動」揭露。

**待決事項與其他〔已決〕標記（方向：不變）**
- 本批（同上；tech-architect C-07、C-20、C-21；風控單項確認第四節第 10 點）：D-9.3「判定時點」第二子點的 O-1 但書（C-07）、待決事項 tech-architect 段的 O-1 列（C-20）、待決事項 quant 段的 V10-08 列（C-21），都只加〔已決〕，原句保留，無被取代原文。「部分窗口」不在此列，依上條取代。
- 本批（同上；tech-architect C-22；風控單項確認 B-7）：待決事項 tech-architect 段與 data-engineer 段各新增一列，無被取代原文。CEO 段新增第 11、12 點，無被取代原文。提案原文（tech-architect C-22 的 CEO 段第 11 點，從未落入 ADR；風控單項確認：表數 16→17 屬知悉，要在 CEO 段單獨列一點，不得和放寬項的明示同意寫在同一點；V14-01 的明示同意涵蓋結算端強制重抓，不另立一項）——
  > 11. （v0.14）V14-01、V14-02 為放寬，而且改動本 ADR D-9 的字面；核可本 ADR 時逐項明示同意，未明示前不得凍結 dirdef（風控 2026-10-18 v0.14 審查 R14-17）。另請知悉：M-11 的表數隨 `forecast_settle_eval` 由 11 張改為 12 張，全部表數由 16 張改為 17 張。

**FL-64（D-3「晚到資料的觸發」；掛 A-65（R10-3）；方向：收緊（測試））**
- 本批（同上；tech-architect C-18；風控單項確認 B-2）：FL-64 標題、(d)、末行三處被取代的原文。標題（只有「第 1～8 點」一處改字）——
  > - **FL-64**（N-4；掛 A-65（R10-3）；D-3「晚到資料的觸發」第 1～8 點）：fixture 用離線的假市場 DB 與主 DB。

  (d) 子點——
  > - 值等於寫入當下假市場 DB 的 `MAX(run_id)`；大盤列為 null，個股與族群列非 null；

  末行——
  > - 第 7 點是預期量，不是規則，不設格；第 9 點（O-1）待 O-1 定案時同批補格。

  (d) 的改字是和 R14-4 的必要連帶（tech-architect 第 6 小節缺口二：原字面與 R14-4「讀於評估開始」、LG-29 (d) 矛盾）；風控單項確認再加更正作業一格：值等於該作業的 `market_scan_to`。FL-65、FL-66 為新增，無被取代原文；FL-66 (g) 句尾、(j) 一格與新增 (l) 為風控單項確認 B-6 的增補。

---

> N-21 結算路徑套用（B-3 回送，2026-10-18，tech-writer；tech-architect 回送：`work/reviews/2026-10-18-未觀察平日登記範圍查核與B3回送-tech-architect.md`；風控 B-3 回送確認：`work/reviews/2026-10-18-B3回送N21登記範圍單項確認-風控.md`）。本批是單獨一批，依風控第四節第 1 點另開，不動 v0.14 已落地的字；事先宣告不改字（風控第一節：本批不改字）。字句以風控第二節 C 為準、逐字寫入；tech-architect 原稿只作參考。本批不新增 A 號；累計方向統計維持 18／2／9／1／3。本批沒有任何一項需要 CEO 明示同意（風控第二節 A）。
> - 套用順序：P-1（兩個動作）、P-2、P-3a、P-3b、P-4、說明句、P-5、P-6、FL-66 標題、V14-03 修訂列的〔已決〕註（風控第四節第 1 點）。
> - 被取代的原文取自套用前的 ADR 檔現況（任務說明：HEAD 為 a4aca90，ADR 本身沒有未 commit 的修改）；tech-writer 沒有用 git 對 a4aca90 逐字核對，請 coordinator 對照 a4aca90 核對。
> - 後續追蹤清單（`work/dispatch/2026-10-17-後續追蹤清單.md`）的 N-21 狀態更新與 N-22、N-23 新增列不在本 ADR，依風控第四節第 2 點 (11) 由 coordinator 處理。

**N-21 結算路徑（B-3 回送，2026-10-18）（A-77 第 10 項、D-7 第 2 點、D-8 第 5 點、D-9.2 執行順序 ②④、D-9.3 B-3 子點、FL-66、V14-03 修訂列；掛 A-77；方向：逐項標示，見各項）**
- P-1（A-77 第 10 項「偵測」＋新增 D_reg 子點；tech-architect B-3 回送；風控 B-3 回送確認第二節 C P-1）：「偵測」被取代的原文（該子點整行）——
  > - **偵測**：缺日稽核以單一函式 `unobserved_weekdays(start, end)`，逐日檢查 [D_v, 最新觀察日] 內的平日。這裡列舉平日只是為了產生候選，不得用來推定觀察日（FL-19 不變）。

  動作一：該句的範圍起點由 D_v 改為 D_reg。動作二：在「偵測」子點之後、同一層新增「登記起點 D_reg」子點，無被取代原文。方向：補定義（收緊）（風控第二節 A：核可，改標註，加 N-22 指向）。
- P-2（A-77 第 10 項「登記先於使用」；風控 B-3 回送確認第二節 C P-2）：被取代的原文（該子點整行；被取代的是「完成 [D_v, 最新觀察日] 內的登記。」一句，其後「登記失敗時，該作業不寫入（fail-closed），記 WARNING。」逐字保留）——
  > - **登記先於使用**：任何讀取觀察日集合（`observed_sessions()`）、並寫入主 DB 的作業（排程結算、更正作業、缺日稽核、X2 確認寫入），在讀取之前，要在同一個寫入交易內先呼叫 `unobserved_weekdays`，完成 [D_v, 最新觀察日] 內的登記。登記失敗時，該作業不寫入（fail-closed），記 WARNING。

  方向：補定義（兩面）。放寬面是讀取範圍以外的日期延到缺日稽核才登記。風控第二節 B 的放寬內容原文：缺日稽核以外的作業，只登記自己讀取的範圍。讀取範圍以外的日期，改由同一晚稍後的缺日稽核登記；缺日稽核失敗時延到下一晚。這個放寬同時消除 G5（風控第二節 B）。代價（風控第二節 B）：缺日稽核失敗期間，§4.2 ① 會少列這些日期，條文已照實寫出，並指向 `last_gap_audit_at`。CEO 明示同意：否（風控第二節 A、B：不是風險上限的預設值，也不改變任何判定結果）。不得只標「收緊」。
- P-3a（D-9.2 執行順序 ②；風控 B-3 回送確認第二節 C P-3a，風控新增）：② 原行（原句保留在行首，新句接在行尾）——
  > ② 讀時鐘與大盤列，需要時強制重抓一次，建立大盤快照。之後不再讀大盤列。

  方向：補定義（收緊），修正 G5（風控第二節 A 的 P-3 列）。tech-architect 原稿把官方休市日表放在 ④ 讀取；風控 B-3 回送確認指出 ③ 的 X2 確認寫入也要讀這份表，改為 ② 讀一次，③、④、`span_sessions` 共用；原稿「接入時併入 `forecast_settle_eval`」與 D-3 既有的 `holiday_table_json` 欄位重複，刪除，改綁現有欄位（風控第一節）。D-3 的欄位定義本批沒有改動。
- P-3b（D-9.2 執行順序 ④；風控 B-3 回送確認第二節 C P-3b）：④ 原行——
  > ④ 開啟主 DB 寫入交易。依 A-77 第 10 項「登記先於使用」，以 R 與快照完成未觀察平日登記，之後讀 E、V。

  方向：補定義（收緊），修正 G5（風控第二節 A 的 P-3 列）。
- P-4（FL-66 (j)；風控 B-3 回送確認第二節 C P-4）：在 (j) 的「結算窗內有符合 A-77 第 10 項判準、卻沒有登記事件的日期」那一格之後，新增 ADR 自有的對照格（不對應 LG-30）；(j) 原有各格一字不改，無被取代原文。方向：收緊（測試）（風控第二節 A：修改，增補四格）。風控第二節 A 寫「增補四格」，第二節 C 的逐字字句實際為六個子項（第一項含五個 fixture）；tech-writer 依第二節 C 逐字寫入，未增減，請 coordinator 核對。
- 說明句（D-9.3 B-3 子點之後、同一層；風控 B-3 回送確認第二節 C 說明句）：新增「說明」子點與其下兩個子點，B-3 本句一字不改，無被取代原文。方向：補定義（收緊）；風控第二節 A 將此項由選用改為必要。字句為風控改寫版（風控第二節 C「改說明句的理由」：tech-architect 原句是無條件斷言，前提有三處尚未落地，並漏寫「不得捕捉」「不做補登記工具」）。
- P-5（D-7 第 2 點「執行順序」下新增第一個子點；風控 B-3 回送確認第二節 C P-5，風控新增）：只插在 D-7 第 2 點本文之後那一處，本修訂紀錄 A-4（D-7.2）段內引用區塊裡的同名字串不動；無被取代原文。方向：補定義（收緊）（風控第二節 A）。
- P-6（D-8 第 5 點 status API；風控 B-3 回送確認第二節 C P-6，風控新增）：被取代的原文（該子點整行）——
  > - `GET /api/forecast/status` 回傳 `last_gap_audit_at`。

  方向：收緊（揭露）（風控第二節 A）。
- FL-66 標題（風控 B-3 回送確認第二節 C「FL-66 標題」）：被取代的原標題行——
  > - **FL-66**（v0.14 V14-03；D-9.3 `split_or_reduction_suspected` 的 g 與換算門檻；對應事先宣告 LG-30 (a)～(k)；風控 R14-13、R14-14）：表格驅動加性質測試。

  改為對應 LG-30 (a)～(l)。方向：不變（文字）（風控第二節 A；風控確認 LG-30 已有 (l)，FL-66 也已有 (l)）。
- V14-03 修訂列（風控 B-3 回送確認第二節 C「V14-03 修訂列」）：在「風控 B-3 附帶：登記範圍 … 不得讓這個 fail-closed 在正常營運中觸發。」句末加〔已決：tech-architect B-3 回送，風控 2026-10-18 B-3 回送確認；登記起點改為 D_reg，見 A-77 第 10 項、D-9.2 執行順序 ②與④（後續追蹤清單 N-21）〕；原句保留，無被取代原文。風控第二節 A 的方向表沒有這一列，本批不另標方向。

---

> C-22 存放表與 N-21～N-24（2026-10-18）套用（2026-10-18，tech-writer；tech-architect 提案：`work/reviews/2026-10-18-C22存放表與N21更正作業視圖及N22至N24提案-tech-architect.md`；風控單項確認：`work/reviews/2026-10-18-C22與N21至N24單項確認-風控.md`）。
> - **本批單獨成批**，依風控第二節 I 段「另開一批」套用，與前一批（N-21 結算路徑，B-3 回送）分開。
> - **事先宣告不改字**：風控第二節 I 第 14 點「事先宣告本批 diff 為空」。tech-writer 本批沒有動事先宣告檔。
> - **不新增 A 號**，累計方向統計維持 18／2／9／1／3（見上「第九、十批」段的方向表）。
> - **本批沒有任何一項需要 CEO 明示同意**（風控第一節、第二節 A 的 CEO 欄）；表數 17→18 屬知悉（風控第二節 E），單獨列於待決事項 CEO 段第 13 點。條件式的例外不在本 ADR：N-22b 若 quant 選 (a)，到時才要 CEO 明示同意（風控第二節 D，後續追蹤清單）。
> - **來源與優先序**：
>   1. 風控 `2026-10-18-C22與N21至N24單項確認-風控.md`：第二節 I 段「tech-writer 照改清單」第 1～14 點（依序套用）；第二節 F 段的逐字字句；第二節 A 段的方向標（S-1、S-6 的方向欄照 F 段逐字）。
>   2. tech-architect `2026-10-18-C22存放表與N21更正作業視圖及N22至N24提案-tech-architect.md`：F 段沒有列出的條目照 TA 原字面；定位字串與被取代的原文。
> - 定位一律用字串，從檔尾往前套。下列被取代的原文，取自套用前的 ADR 檔現況（任務說明：HEAD 為 be8c66a 之後的版本，ADR 本身沒有未 commit 的修改）；tech-writer 沒有用 git 對 be8c66a 逐字核對（本任務沒有 git 工具），請 coordinator 對照 be8c66a 核對。
> - **提案原文不逐字重錄**：tech-architect 提案中從未落入 ADR、被風控 F 段逐字字句取代的文字（C22-1 的五處、C22-6 第 13 點、C22-7 的〔已決〕註、N21-3 的第三條理由、N21-4、N21-5 的第二個列點、N21-7 的簽章禁止項、N22-2、N23-2 的兩處、FL-67 的 (d)(g)(h) 句尾），以及風控 F 段取代 TA 的條目，一律指向 TA 提案的同名條目，不在此重錄；理由是風控第二節 J 的機械核對有數項要求這些字零命中。
> - 本批沒有套用的項目：風控第二節 I 第 15、16 點（後續追蹤清單與決策包二補遺第 18 項）由 coordinator 處理，不在本 ADR；第二節 G 的約束 C21～C33 與第二節 H 的各部門事項不在本 ADR 條文內，本批未寫入。

**C-22 存放表與 N-21～N-24（2026-10-18）（D-3、D-1、D-7、D-8、D-9、A-77 第 7、10 項、FL-65～FL-68、Consequences、待決事項；掛 A-65、A-77、A-75；方向：逐項標示，見各項）**
- C22-1（D-3 新表 `forecast_index_check`，插在 `forecast_replay` 那一行之前；tech-architect 提案 C22-1 加風控 F 段 5 處修改）：無被取代原文。方向：補定義（收緊）。風控的五處修改：determination 組加 `target_values_sha256`；唯一性改為以判定對象那一列為單位，寫入驗證的 `correct_close_obtained` 條件同步改；`INDEX_VERIFICATION_SOURCE` 涵蓋範圍擴大一句；「判定時怎麼讀」的待查證 bar 拆成兩個子點（暫定讀法，取較嚴的一面；quant 依後續追蹤清單 N-26 登記）；用途限制改列讀取呼叫點。送風控：已確認。CEO：否（表數見 C22-6）。
- C22-2（D-9.2 V 的定義；方向：不變（指向））：被取代的原文（該行整行）——
  > - V ＝ 查證紀錄與 X1、X3、X4 確認判定紀錄的序號上限。
- C22-3（D-9.2 存放表待決句；方向：不變（定案指向））：被取代的原文（該行整行）——
  > - 查證紀錄與確認判定紀錄的存放表，本 ADR 尚未定義（待決事項 tech-architect 段；D-9 結算程式實作前定案）。不論存在哪裡，都必須是主 DB 中只增不改、以 `INTEGER PRIMARY KEY AUTOINCREMENT` 為序號的表，否則本點的 V 不成立。
- C22-4（D-9.2 ③；方向：補定義（收緊））：在「查證紀錄與 X2 確認照既有規則寫入，各自一個交易。」之後接上一句，無被取代原文。
- C22-5（A-77 第 7 項 `verification_ref` 綁定；方向：補定義（收緊））：在「判定時間就是事件的 `recorded_at`，不另設欄位。」之後、同一層新增一點，無被取代原文。
- C22-6（表數連帶；方向：不變，CEO 知悉；風控 2026-10-18 C-22 確認：屬知悉，不需明示同意）：被取代的原文——評估摘要「最大代價」（該行整行）——
  > - 表數多（17 張），寫入規則有一部分在 trigger 裡。

  M-11 列的第四格（修訂清單表）——
  > 新增 12 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`；剩餘待決項 N-4 加 `forecast_void_late_diag`；v0.14 V14-01 加 `forecast_settle_eval`）並取欄位聯集（D-3）；`forecast_outcome.status` 三值不變，另加 `status_reason`；F-3 補上分母、恢復條件與 PIT 違規處理（D-11.6）

  Consequences「代價與壞處」（該行整行）——
  > - 17 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。

  改為 18 張；M-11 改為新增 13 張表（在 `forecast_settle_eval` 之後加「；C-22 加 `forecast_index_check`」）。待決事項 CEO 段新增第 13 點（字句照風控 F 段），無被取代原文。
- C22-7（待決事項 tech-architect 段，v0.14 V14-01 一列；方向：不變）：在該列句末加〔已決：`forecast_index_check`，見 D-3（C-22，tech-architect 2026-10-18；風控 2026-10-18 C-22 確認）〕，原句保留，無被取代原文。字句照風控 F 段（TA 提案的註記末尾是待風控確認的標記，風控改為確認出處；提案原文見 TA 提案 C22-7）。
- N21-1（D-3 `forecast_correction_job` 欄位清單；方向：補定義（收緊））：被取代的原文（該欄位清單的結尾一段）——
  > market_scan_restore_suspected INTEGER NOT NULL CHECK (market_scan_restore_suspected IN (0,1)), started_at)

  改為在 `market_scan_restore_suspected` 之後、`started_at` 之前加 9 欄：`ledger_event_from`、`ledger_event_max`、`index_check_from`、`index_check_max`、`index_series_sha256`、`index_final_now`、`holiday_table_json`、`view_range_json`、`observed_sessions_json`。編輯註記：TA 字面首尾的反引號是提案文件的 code span 包裝，ADR 該處的反引號在被取代字串之前、之後，沒有重複寫入。
- N21-2（D-3 `forecast_correction_job` 欄位說明；方向：補定義（收緊））：在 `triggers_json`「不放」子點之前、同一層新增「判定視圖欄位」一點，無被取代原文。編輯註記：依 tech-architect 確認，與 `market_scan_*` 一點並列。
- N21-3（D-9 第 5 點「更正作業的判定視圖」；方向：補定義（收緊）；風控：修改後核可，TA 對新子點若有實作疑義，回送風控單項確認）：在「有變的筆新增一列並填 `supersedes_id`；……」之後、同一層新增，無被取代原文。風控兩處修改：④ 的「`span_sessions` 使用 ② 的休市日表；」與「之後不再讀 `MAX(event_id)`、`MAX(check_id)`。」之間新增三個子點（已結算日期取當時的快照、更正鏈沒有任何結算窗涵蓋的日期、觀察日的 (ii)）；「理由」第三子點整句改字（TA 原理由句以 R10-2 的差異驗證拒絕寫入為由；風控第一節第 3 點指出 R10-2 的 `[x2_session_removed]` 只檢查 `end_price_json.session_date`，不檢查 P(T)，該理由不成立；提案原文見 TA 提案 N21-3 的「理由」第三子點）。
- N21-4（D-3「晚到資料的觸發」第 1 點，啟動者缺口；方向：補定義（收緊））：被取代的原文（該句，位於第 1 點「誰偵測」的句尾）——
  > 掃描有命中時，以命中項為觸發啟動更正作業；沒有命中時不啟動（D-3「`triggers_json` 必須非空」不變）。

  改為見 §D-3「晚到資料的觸發」第 1 點（風控 F 段整段取代 TA 字面：W_E、W_V 與 `ledger_event_from`、`index_check_from` 同一定義、同一個函式導出；啟動與否只依三類觸發是否存在；不得提供以操作者指定觸發、日期或預測啟動更正作業的入口）。連帶：R10-2 的 `[settlement_close_corrected]` 是否擋掉「改記作廢」的 supersede，風控未查證，交 tech-architect 查（後續追蹤清單 N-27，N-21 的結案條件）。
- N21-5（D-11.4 第 11 點 (h)「原因怎麼歸屬」第一個子點；方向：補定義（收緊））：在該子點的〔N-17…〕註之後接上「（N-21）「還沒處理」以序號界定」一段，無被取代原文；第二個列點照風控 F 段整句取代 TA 字面（歸類改為對每一筆重查的 outcome 個別判定，`determination` 與 `target_bar_json.session_date` 兩項都成立才歸 `settlement_close_corrected`）。
- N21-6（D-3 `forecast_void_late_diag`「寫入者只有更正作業」第二子點；方向：補定義（收緊））：在「`market_scan_to`；」與「其餘依」之間插入一句，無被取代原文。
- N21-7（D-1 模組表，新增 `app/forecast/correction.py` 一列；方向：不變（模組歸屬））：無被取代原文。風控改字：簽章禁止項由 TA 的「觸發、視圖、E、V 或重算結果」改為「觸發、預測清單、重查範圍、視圖、E、V 或重算結果」。
- N21-8（D-1 `observed_days.py` 列；方向：補定義（收緊））：被取代的原文——
  > `view` 是 D-9.2 的判定視圖；
- N21-9／FL-68（對實作的約束；方向：收緊（測試））：新增 FL-68，插在 FL-24 之前、FL-67 之後，無被取代原文。字句為 TA (a)～(f) 加風控 F 段 (g)(h)。
- N22-1（D-9 新增第 7 點，重放不走本條的結算路徑；方向：補定義（收緊））：無被取代原文。風控改字：括號內的指向由後續追蹤清單 N-22 改為 N-22b（凍結阻擋）。
- N22-2（D-9.3 `void_reasons` 子點之後新增一點；方向：不變（釐清））：無被取代原文。風控整段取代 TA 字面：補上族群成員層的排除判定不受影響一句，並更正 TA 對「登記」作用的描述（大盤的未觀察平日登記有兩個作用：A-77 第 10 項「固定排除」，以及 §4.2 ③ 的計數）。
- N22-3（FL-66 (h)；方向：收緊（測試））：在 (h) 句末加一段。編輯註記：TA 字面不帶句號，原句末的句號移到新增段之後。被取代的原句尾——
  > 不做 g 換算。
- S-1（D-9.2 快照範圍；tech-architect 提案；風控核可字面）：被取代的原文（該行整行）——
  > - 快照範圍 ＝ [該次評估全部未結算預測的 T 的最小值, 評估當日（Asia/Taipei）]，記入 `view_range_json`。

  改為「評估集合與快照範圍」一點，見 §D-9 第 2 點。方向：補定義（收緊）。② 之前已存在的紀錄，判定不變；② 與 ④ 之間寫入的紀錄，延到下一次評估，依寫入時點機械決定，不看內容；被延後的紀錄，結算時點可能晚一次評估【推論：只在市場 DB 落後時可能】。U 為空時的快照範圍，原本沒有定義。
- S-2（D-9.2 ⑥；方向：不變（釐清））：被取代的原文——
  > ⑥ 對全部未結算的預測判定：結算或作廢的寫入 `forecast_outcome`；等待的記入 `waiting_json`。
- S-3（D-3 `forecast_settle_eval` 欄位；方向：補定義（收緊））：在 `view_range_json` 一項之後新增 `eval_set_count`、`eval_set_sha256` 一項，無被取代原文。
- S-4（D-3 `forecast_settle_eval` 寫入驗證；方向：收緊）：被取代的原文——
  > 而且都是判定視圖中 T+h 已觀察到、`valid_until_session` 已過、尚未結算的預測；
- S-5（FL-65 新增 (n)；方向：收緊（測試））：在 (m) 之後新增，無被取代原文。
- S-6（A-77 第 10 項「登記先於使用的適用範圍」；方向：補定義（收緊））：在「成立時」子點之前、與「登記先於使用」同一層新增，無被取代原文。第二子點照風控 F 段整句改字（TA 字面只說「本身不登記」；風控加「也不呼叫 `unobserved_weekdays` 與 `ledger_registration_start()`（AST）」）。方向欄逐字：補定義（收緊）。recorder 照舊字面落在「任何讀取觀察日集合、並寫入主 DB 的作業」之內，本點把它排除；登記當下 d ∉ (i) ∪ (ii)，recorder 讀到的觀察日不因此改變，以 `as_of` 視圖登記則會造成永久誤登記，所以實質是收緊。
- P-3a 括號（D-9.2 執行順序 ②；風控更正自己的字；方向：不變（釐清））：風控 2026-10-18 C-22 確認更正 B-3 回送確認 P-3 的前提（P-3a 括號原寫 X2 確認寫入的交易內也要依 A-77 第 10 項登記；X2 確認寫入依 A-77 第 4 項不讀觀察日集合，登記範圍的交集為空，括號內的「登記」沒有內容）。被取代的原文——
  > （含其交易內依 A-77 第 10 項的登記）

  改為見 §D-9 第 2 點執行順序 ②（風控 F 段逐字，只換括號；括號前後的字不動）。休市日表仍在 ② 讀一次的理由，不是登記，而是 X2 payload 的 `holiday_table` 與 `trigger = official_holiday` 本身要用到這份表，所以 FL-66 (j) 的 spy 格照舊成立（風控第二節 B-2）。
- N23-1（D-7 第 2 點「執行順序」本文那一句；方向：補定義（收緊））：被取代的原文（只有這一句；同一行後半「T 的 plan 一律使用……」不動；本修訂紀錄 A-4（D-7.2）段內引用區塊的同名字串不動）——
  > 2. **執行順序**：記錄 → 結算 → 缺日稽核 → 驗證快照 → plan（政策表）。

  P-5 子點本句不動。
- N23-2（D-7 第 2 點，P-5 子點之後新增「步驟隔離」「前置條件」「持續失敗期間」三點；方向：補定義（收緊））：無被取代原文。風控兩處修改：「前置條件」的驗證快照子點整句改字（加「更正作業完成」第三項前置）；「持續失敗期間」的第二、第三子點整句改字（plan 衍生內容明列範圍，涵蓋 `PLAN_OUTPUT_SURFACES` 全部三個面；API 不得以較早的 plan 回填 T；時間戳句不得把 T 代入 plan 相關位置；plan 渲染上線前的阻擋項）。TA 提案原文見 TA 提案 N23-2。
- N23-3（D-7 第 1 點 listener；方向：收緊（揭露））：在 `timezone="Asia/Taipei"` 那一子點之後、同一層新增，無被取代原文。
- N24-1（D-8 第 2 點「判定上界」；方向：補定義（兩面））：在 D-8 第 2 點之下、`reason` 判定清單之前新增，無被取代原文。風控在「另一面」子點之後加兩個子點（比率不因尚未判定而偏低；揭露判定進度，新增 `gap_judged_through`，存放處由 tech-architect 另定）。收緊面：不再有與實際紀錄永久矛盾的 `job_error`。放寬面：缺日與 F-3 逾時率的反映延後約一天。CEO 明示同意：否（風控第二節 B-3：沒有改任何門檻或預設值；延後有確定的上限；比率不會因此偏低；修掉的是一個永久性錯誤）。
- D-8 第 5 點 status 行（N24-1 連帶；方向：補定義（兩面），同 N24-1）：被取代的原文（該子點整行）——
  > - `GET /api/forecast/status` 回傳 `last_gap_audit_at`，以及 `last_settle_eval_at`（最後一筆 `forecast_settle_eval` 的 `started_at`；沒有任何列時為 null）（v0.14；風控 2026-10-18 B-3 回送確認）。這兩個值若要在畫面上呈現，文案另經 creative-lead 起草、風控審查。

  改為在「以及 `last_settle_eval_at`（……）」之後加「，以及 `gap_judged_through`（D-8 第 2 點 N-24）」，「這兩個值」改為「這三個值」。
- FL-67（對實作的約束，新增，插在 FL-24 之前、FL-68 之前；方向：收緊（測試））：無被取代原文。字句為 TA (a)～(h) 加風控 F 段的加格：(d) 句末加 `correct_close_obtained` 的 `target_values_sha256` 與所指 `close_erroneous` 不同；(g) 句末加更正作業已啟動、沒有寫入 job_end 的一格；(h) 句末加 `gap_judged_through` 與缺日率分子分母的一格；新增 (i)～(k) 三格。編輯註記：加格處的句號移到加格之後，TA 與風控字句不增減。
- 指向更正（A-77 第 10 項「登記起點 D_reg」子點末句；coordinator 裁定，CEO 可推翻；方向：不變）：追蹤清單 N-22 已拆為 N-22a、N-22b，coordinator 更正指向，語意不變（比照先前 N-18 改 N-20 的作法）。被取代的原句——
  > `forecast_replay` 不在 D_reg 的導出範圍（重放的涵蓋見後續追蹤清單 N-22）。

  改為「（重放的涵蓋見後續追蹤清單 N-22a、N-22b）」，該句其餘不動。
- FL-68 (f) 同步（coordinator 依 N21-7 同步，CEO 可推翻；方向：收緊（測試））：與 N21-7（風控 F 段）的簽章禁止項一致。被取代的原句——
  > - (f) 簽章沒有觸發、視圖、E、V 參數（AST）；supersede 寫入只從 `run_correction_job()` 呼叫。

  改為「簽章沒有觸發、預測清單、重查範圍、視圖、E、V 參數」，其餘不動。
- 事先宣告：本批不改字（風控第二節 I 第 14 點）。後續追蹤清單 N-21～N-27 與決策包二補遺第 18 項不在本 ADR（風控第二節 I 第 15、16 點）。

---

> N-24 存放處與 C-22 suggested（2026-10-18）套用（2026-10-18，tech-writer；tech-architect 提案：`work/reviews/2026-10-18-N27與gap_judged_through存放處提案-tech-architect.md` 第二節 B、C、D 段）。
> - **本批單獨成批**，與前一批（C-22 存放表與 N-21～N-24）分開；同一份 TA 提案的第二節 A 段（N27-1～N27-4）正在送風控，本批不套用。
> - **事先宣告不改字**：本批沒有動事先宣告檔。
> - **不新增 A 號**，累計方向統計維持 18／2／9／1／3（見上「第九、十批」段的方向表）。
> - **表數 18→19 屬知悉**（M-11 由 13 張改為 14 張）；單獨列於待決事項 CEO 段第 14 點，比照第 12、13 點。本批沒有任何一項需要 CEO 明示同意。
> - **B-1 是 TA 更正自己上一輪的字面錯誤**（風控 2026-10-18 C-22 確認 suggested (b)）：TA 把 X2 確認的必要條件「d ∉ (i)」誤抄成 `no_error` 的條件，本批改為不讀 (i)。計分不變（待查證列與 `no_error` 都照原值計分），只是待查證數減少（TA 提案 B-1 方向欄）。
> - **回送風控**：依 coordinator 任務說明，依風控 C-22 確認 A 段註記，本批不回送風控。tech-writer 本批沒有重讀風控檔 A 段原文，該註記的字面請 coordinator 對照 `work/reviews/2026-10-18-C22與N21至N24單項確認-風控.md`。G-4（`last_gap_audit_at` 取值）依 TA 提案請風控知悉；風控若認為該值應包含失敗的嘗試，再回送。
> - **A-4 依 coordinator 裁定採用**（CEO 可推翻）；方向：收緊。TA 提案列為 suggested，採不採由 coordinator 決定。
> - **定位與被取代原文**：定位一律用字串，從檔尾往前套（為避免被取代原文寫入本段後造成定位字串重複，實際操作是先套條文、後寫本段）。被取代的原文取自套用前的 ADR 檔現況（任務說明：HEAD 為 `13eb2e2`，C-22 批次已落地，ADR 本身沒有未 commit 的修改）；tech-writer 沒有用 git 對 `13eb2e2` 逐字核對（本任務沒有 git 工具），請 coordinator 對照核對。
> - **本批沒有套用的項目**：TA 提案第二節 A 段 N27-1～N27-4；C 段末的殘餘情形（候選 N-28、官方休市日表接入時併入重審的兩項）；E 段約束 C34～C39；F 段交給 quant、風控的事項。這些屬後續追蹤清單或約束，不在本批條文內。

**N-24 存放處與 C-22 suggested（2026-10-18）（D-1、D-3、D-8、D-9、FL-67、Consequences、評估摘要、修訂清單 M-11、待決事項；方向：逐項標示，見各項）**
- G-1（D-3 新表 `forecast_gap_audit`，插在 `forecast_gaps` 那一行之後；方向：補定義（收緊））：無被取代原文。落實風控 2026-10-18 C-22 確認 N24-1「揭露判定進度」。送風控：依風控 A 段註記不必回送，`gap_judged_through` 的定義沒有改。CEO：表數屬知悉（G-5）。
- G-2（D-1 模組表 `app/forecast/audit.py` 一列；方向：不變（模組歸屬））：被取代的原文（該列的前兩格）——
  > `| `app/forecast/audit.py` | 缺日稽核 |`
- G-3（D-8 第 2 點，風控 N24-1 揭露判定進度子點的句末；方向：補定義）：在句末接上〔已決：存放於 D-3 `forecast_gap_audit`（N-24；tech-architect 2026-10-18）〕，風控原句不動，無被取代原文。
- G-4（D-8 第 5 點，status 行之後、同一層新增一點；方向：補定義）：無被取代原文。TA 提案的說明：這和 A-77 第 10 項「延到下一次成功執行才登記」的揭露用意一致。送風控：請風控知悉。
- G-5（表數連帶；方向：不變，CEO 知悉）：被取代的原文——評估摘要「最大代價」（該行整行）——
  > - 表數多（18 張），寫入規則有一部分在 trigger 裡。

  Consequences「代價與壞處」（該行整行）——
  > - 18 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。

  M-11 列第四格（修訂清單表）兩處——
  > 新增 13 張表（第九、十批加

  > ；C-22 加 `forecast_index_check`）並取欄位聯集

  改為：評估摘要與 Consequences 的「18 張」改為「19 張」；M-11 的「新增 13 張表」改為「新增 14 張表」；在 `forecast_index_check` 之後加「；N-24 加 `forecast_gap_audit`」。待決事項 CEO 段新增第 14 點，無被取代原文。編輯註記：C-22 批次的 C22-6 條目（上）與本條引用的「18 張」「13 張」是當時的原文，不改。
- G-6／FL-67 (n)（對實作的約束；方向：收緊（測試））：在 (m) 之後新增 (n)，無被取代原文。TA 提案 G-6 寫「插在 C 段的 (m) 之後」，順序為 (l)、(m)、(n)，接在 (k) 之後。
- A-1（D-3 `forecast_index_check`「寫入者與時機」；風控 2026-10-18 C-22 確認 suggested (a)；方向：補定義（收緊））：被取代的原文（標頭，同定位字串）——
  > **寫入者與時機**（各自一個交易：detection、該次 ① 查證，以及由它導出的 determination 同一交易）：

  另在「其他任何程式路徑（API、CLI、更正作業、重放、缺日稽核）都不得寫入本表」那一行之後、同一層新增「由查證列導出的 X2 確認」一點，無被取代原文。理由（TA 提案）：查證列和 X2 確認分成兩個交易時，中途中斷會留下一筆「來源沒有這一天」、卻沒有 X2 確認的查證列；下一次 ② 會再查一次，X2 確認改由較晚的查證列導出，確認時點就隨「有沒有中斷」而不同。
- A-2（D-9.2 ③；方向：補定義（收緊））：被取代的原文（只換這一句；其後 C22-4 的句子不動）——
  > 查證紀錄與 X2 確認照既有規則寫入，各自一個交易。
- A-3／FL-67 (l)（對實作的約束；方向：收緊（測試））：在 (k) 之後新增 (l)，無被取代原文。
- A-4（D-3 `forecast_index_check`「寫入者與時機」D-9.2 ③ 子點；coordinator 裁定採用，CEO 可推翻；方向：收緊）：被取代的原文（只換這一段）——
  > 還沒有出現在任何 `source_onboarding` 列時

  改為「還沒有出現在 `check_id` ≤ 前一列 `forecast_settle_eval.index_check_max`（沒有前一列時為 0）的任何 `source_onboarding` 列時」。理由（TA 提案）：③ 部分寫入之後，如果該次評估在 ④ rollback，該 version 已經出現在部分 `source_onboarding` 列，下一次就不會再做完整的 ③。
- B-1（D-3 `forecast_index_check`「寫入驗證」`x2_pending` 一點；TA 更正自己上一輪的字面錯誤，風控 2026-10-18 C-22 確認 suggested (b)；方向：補定義（更正 TA 的錯誤））：被取代的原文（該點整行）——
  > - `x2_pending` 只能有 `no_error`，而且只限 `x2_case = set_iii_only`，寫入時重算 d ∉ D-8.1 (i)；`conflict` 寫任何 determination 都拒絕（A-77 第 5 項）。

  送風控：不必，請風控知悉。
- B-2／FL-67 (m)（對實作的約束；方向：收緊（測試））：在 (l) 之後新增 (m)，無被取代原文。
- N21-2 移位（D-3 `forecast_correction_job` 欄位說明；依 tech-architect 確認；方向：不變（編排））：「判定視圖欄位」一點（主點與四個子點）整段移出 `market_scan_from`、`market_scan_to` 那一點（N-4）之下，改成與 `market_scan_*` 一點並列，也就是 `forecast_correction_job` 的直接子點，位置在「不放 `triggers_json`」子點之後、`forecast_correction_job_end(` 那一行之前。縮排：主點由 6 個空格改為 4 個，四個子點由 8 個空格改為 6 個；字句不變。修訂紀錄 N21-2 條目的編輯註記改字，被取代的原文——
  > 編輯註記：依 TA「同一層」的指示，該點與「不放 `triggers_json`」子點同一縮排，即位於 `market_scan_from`、`market_scan_to` 那一點（N-4）之下；若要與該點並列，請 coordinator 回送 tech-architect 確認。

  改為「編輯註記：依 tech-architect 確認，與 `market_scan_*` 一點並列。」N21-2 條目的首句（「在 `triggers_json`「不放」子點之前、同一層新增……」）本批未改字，其所述位置以本條為準。

---

> v0.15 對應條文與 N-27（2026-10-18）套用（2026-10-18，tech-writer；風控單項確認：`work/reviews/2026-10-18-v0.15草案與N27單項確認-風控.md` 第四節「ADR 端連帶清單」「與 v0.15 同批」第 1～4 項；tech-architect 提案：`work/reviews/2026-10-18-N27與gap_judged_through存放處提案-tech-architect.md` 第二節 A 段 N27-1、N27-2、N27-4）。
> - **與事先宣告 v0.15 同批**：本批與事先宣告 v0.15 要放在同一個 commit，或同一次 push 的相鄰 commit，任何一份都不得單獨 commit（風控 2026-10-18 v0.15 單項確認第一節「同批規則適用」、第四節「與 v0.15 同批」）。
> - **不新增 A 號**，累計方向統計維持 18／2／9／1／3（見上「第九、十批」段的方向表）。
> - **本批沒有任何一項需要 CEO 明示同意**（風控 2026-10-18 v0.15 單項確認第一節、第二節 A 的 CEO 欄）。
> - **第 1 項取代的是 C-22 批次寫入的暫定讀法**：D-3 `forecast_index_check`「判定時怎麼讀」的該子點，是 C-22 批次 C22-1 第 4 處（見上 C22-1 條目）寫入的暫定讀法，原文自稱「取較嚴的一面」，以交易日為單位。風控依據：風控 2026-10-18 v0.15 單項確認第二節 B-3（V15-03 改為「以所用的 bar 為單位」，尚未結算的 P(T+h) 維持以交易日為單位）、第二節 C（N-27 路徑一）、第四節「ADR 端連帶清單」第 1 項（逐字字句；取代 TA I-1 的作法）。
> - **N27-3 不用 TA 原稿**，改用風控第四節第 4 項的字句；TA 原稿見 TA 提案 N27-3，不在此重錄。D-9 第 5 點「已結算數值所用的大盤 bar」第二子點的括號，同照風控第四節第 4 項。N27-1 修訂紀錄的方向欄照風控字句寫成「補定義（兩面）」。
> - **本批沒有套用的項目**：風控第四節第 5～8 項（不在同批之內）；TA 提案第二節 A 段以外的項目（B、C、D 段已在前一批「N-24 存放處與 C-22 suggested」套用）；約束 C34～C45 不在本批條文內。
> - **定位與被取代原文**：定位一律用字串，從檔尾往前套（先套條文、後寫本段，避免被取代原文寫入本段後造成定位字串重複）。風控稱第 1 項的子點在 L476，套用前實際位於 L477；本批以字串定位，不以行號。被取代的原文取自套用前的 ADR 檔現況（任務說明：HEAD 為 `ea800c3`，ADR 本身沒有未 commit 的修改）；tech-writer 沒有用 git 對 `ea800c3` 逐字核對（本任務沒有 git 工具），請 coordinator 對照核對。

**v0.15 對應條文與 N-27（2026-10-18）（D-3、D-9、A-77 第 9 項、D-11.4 第 11 點 (h) R10-2、FL-22、FL-68；方向：逐項標示，見各項）**
- 第 1 項（D-3 `forecast_index_check`「判定時怎麼讀」暫定讀法子點；風控第四節 ADR 端第 1 項；對應事先宣告 §6.3「確認有誤之後」V15-03）：該子點整句取代，取代 TA I-1 的作法。方向：補定義（兩面）；CEO：否。其後「除上一子點的情形外，沒有 determination 的待查證 bar 照原值計分。」不動。被取代的原文（該子點整行）——
  > - 同一 `session_date` 已有 `close_erroneous`、而沒有 `correct_close_obtained` 時，該日數值不同的 bar，只有在不屬於待查證集合內任何 detection 的 `checked_bars_json` 時，才算事先宣告 §6.3「確認有誤之後」所說「通過 X1～X4 的來源修訂值」；屬於待查證集合時（例如與已確認有誤的那次擷取構成 X3），不算取得正確值，該收盤仍是「確認有誤、尚未取得正確值」。這是暫定讀法，取較嚴的一面（風控 2026-10-18 C-22 確認）；quant 依後續追蹤清單 N-26 在事先宣告登記讀法，若登記的讀法較寬，以放寬送風控。
- 第 2 項（D-9 第 7 點，兩處；風控第四節 ADR 端第 2 項）：方向：不變（理由更正與指向）（coordinator 依風控確認補標，CEO 可推翻；風控第四節第 2 項原未標方向）。理由第二子點整句取代，被取代的原文——
  > - 重放期在市場 DB 的涵蓋之前〔推論：ADR-0012 C-10 不回填〕。套用前瞻的判定視圖，重放期每個平日假期都會符合 A-77 第 10 項判準。

  另在末段句（「重放結算的存放、判定視圖、觀察日來源，……定義之前不得實作重放結算。」）句末加「X2 在重放期的對照日曆，已由事先宣告 §6.3「重放期的日曆檢查與查證」（v0.15，V15-01、V15-02）登記；其餘（存放、判定視圖、觀察日來源、起訖日、預測端序列、確認有誤之後的路徑）見後續追蹤清單 N-22c。」原句保留，無被取代原文。
- 第 3 項（A-77 第 9 項 F-8；風控第四節 ADR 端第 3 項）：方向：補定義（兩面），隨事先宣告 V15-02（風控 v0.15 單項確認 A 段 V15-02 列）（coordinator 依風控確認補標，CEO 可推翻；風控第四節第 3 項原未標方向）。只換這一段，被取代的原文——
  > 前提是前瞻期與重放期都沒有週末交易日

  改為「前提是前瞻期沒有週末交易日（重放期依事先宣告 §6.3「重放期的日曆檢查與查證」V15-02，週末不作直接確認，不受本項約束）」。A-75 (iv) 那兩處不動。
- N27-1（D-11.4 第 11 點 (h) R10-2「單一原因的差異驗證」之後新增「適用範圍」一點，位於「理由：LM-151、LM-152 陳述……」之前、與 R10-2 三項同一層；TA 提案 N27-1 字面）：無被取代原文。送風控：已核可（風控 2026-10-18 v0.15 單項確認第二節 A、C）。方向：補定義（兩面）：寫入驗證對 `scope_kind = market`、`status_reason = index_bar_confirmed_erroneous` 的改記作廢放寬一格，改以五項重算依據驗證；另一面是讓事先宣告 §6.3「結算後才確認……取不到就改記」與 FL-22 已規定的作廢寫得進去，畫面改走 LM-143，作廢計入作廢率與 W，其他作廢一律拒絕。（TA 提案原標「補定義（收緊）」，風控改標。）CEO：否。
- N27-2（D-9.3 `index_bar_confirmed_erroneous` 一點，新增為第一個子點，位於「作廢原因的判定順序中，第五值的位置交 quant 在事先宣告登記……」之前；TA 提案 N27-2 字面）：無被取代原文。送風控：已核可，照 TA 字面（風控第二節 A、C）。方向：補定義（收緊）。CEO：否。
- N27-3（FL-22 (b)，`[dividend_factor_corrected]` 拒絕子例之後、同一層新增；風控第四節 ADR 端第 4 項字句）：無被取代原文。方向：收緊（測試）（風控第二節 A）。字句為風控改寫版（路徑一在 V15-03 新讀法下不再成立，fixture 改用 X2 順延的路徑重建，並加 B1／B2 一格；新 T+h 與快照列的比對改以 `checked_values_sha256` 的正規化規則進行）。CEO：否。
- D-9 第 5 點「已結算數值所用的大盤 bar」第二子點（風控第四節 ADR 端第 4 項）：該子點（「更正鏈中沒有任何結算窗涵蓋的日期……」）的「數值相同」之後加括號「（以 `checked_values_sha256` 的正規化規則比對）」，其餘不動，無被取代原文。方向：補定義（收緊）：以正規化雜湊比對，避免 NaN 收盤因浮點比較永遠判為不同（風控 v0.15 單項確認 C 段 N27-3）（coordinator 依風控確認補標，CEO 可推翻；風控第四節第 4 項原未標方向）。
- N27-4（FL-68 (h) 之後新增 (i)；TA 提案 N27-4 字面）：無被取代原文。送風控：已核可，照 TA 字面。方向：收緊（測試）。CEO：否。
- D-9 第 7 點末段句前半的狀態註（coordinator 裁定，CEO 可推翻；方向：不變（狀態註））：tech-writer 回報第 1 項新增的末段句，與同一段前半「X2 (iii) 在重放期的對照日曆，在重放結算程式實作前另行定義」並存而有張力。coordinator 裁定原句保留，在「（後續追蹤清單 N-22b）。」之後、「定義之前不得實作重放結算。」之前插入〔已決（X2 部分）：X2 在重放期的對照日曆已由事先宣告 v0.15 V15-01、V15-02 登記，見本點句末；其餘部分見 N-22c，仍待定義〕。無被取代原文。

---

> 重放存放與 v0.16 對應條文（2026-10-18）套用（2026-10-18，tech-writer；風控單項確認：`work/reviews/2026-10-18-v0.16草案與重放存放單項確認-風控.md` 第四節「tech-writer 照改清單」第 1～10 點；tech-architect 提案：`work/reviews/2026-10-18-N29與重放存放及plan略過紀錄與v0.16定名提案-tech-architect.md` 第二節 C 段 I2-1～I2-9、G 段「v0.16 這一批」、E 段首次登記同批閘（已併入 I2-2））。
> - **與事先宣告 v0.16 同批**：本批與事先宣告 v0.16 要放在同一個 commit，或同一次 push 的相鄰 commit，任何一份都不得單獨 commit（風控 2026-10-18 v0.16 單項確認第一節「同批規則確認」、第四節 tech-writer 照改清單第 10 點；TA 提案第一節「同批關係」）。
> - **不新增 A 號**，累計方向統計維持 18／2／9／1／3（見上「第九、十批」段的方向表）。
> - **本批沒有任何一項需要 CEO 明示同意**（風控 2026-10-18 v0.16 單項確認第一節、第二節 A 的 CEO 欄）；表數 19→21 屬知悉（同確認第二節 E）。
> - **本批沒有套用的項目**：TA 提案第二節 B 段 N-29（N29-1～N29-10）與 D 段 `plan_coverage_log`（I3-1～I3-3，含其表數 21→22 與 FL-70），另一位風控審查中，各自成批；因此本批表數只算 19→21，TA G 段「第 3 項先落地」的替代數字（20→22、15→17）不適用。G 段「第 3 項那一批：21→22」也不在本批。
> - **分支名**：ADR 本文不寫分支名，一律指向事先宣告 §4.7「重放期的起訖日」所載的分支；任務說明載明事先宣告所載的分支是 `product/stock-desk`（coordinator 轉述，tech-writer 未獨立查證）。
> - **定位與被取代原文**：定位一律用字串，從檔尾往前套（先套條文、後寫本段，避免被取代原文寫入本段後造成定位字串重複）。被取代的原文取自套用前的 ADR 檔現況（任務說明：HEAD 為 `e21cbbf` 之後的版本，ADR 本身沒有未 commit 的修改）；tech-writer 沒有用 git 對該 commit 逐字核對（本任務沒有 git 工具），請 coordinator 對照核對。
> - **TA 原稿與風控改字**：新增的子點中，風控改過的 TA 原稿字句（I2-2 三處、I2-5 登記檔與 `forecast_replay_index_check` 各處、I2-7 (b) 第一處、I2-7 (c)、I2-8、I2-9）從未寫入本 ADR，本段不重錄，TA 原稿見 TA 提案第二節 C 段；本 ADR 只記風控的最終字句。
> - **本段含被取代原文的逐字引用**，其中的定位字串（例如「19 張」「其餘部分見 N-22c，仍待定義」）會在本段命中，屬歷史列，不是現行條文。

**重放存放與 v0.16 對應條文（2026-10-18）（D-3、D-1、D-9 第 7 點、評估摘要、修訂清單 M-11、Consequences、對實作的約束 FL-69、待決事項；方向：逐項標示，見各項）**
- I2-1（D-3 `forecast_replay` 一行；TA 提案 I2-1）：方向：補定義（收緊）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。被取代的原文（該行整行）——
  > - `forecast_replay`：結構與 `forecast_record` 相同，另加 `freeze_commit`、`replay_session`。永遠不與前瞻紀錄合併。
- I2-2（D-3 新增「`INDEX_VERIFICATION_SOURCE` 的版本歷史」一點，插在 `forecast_replay` 一行之後；TA 提案 I2-2，風控三處改字、首次登記同批條件由兩項改為四項）：無被取代原文。風控改字：(1)「版本規則」最後加兩個子點（`rolling` 視為晚於任何固定日期；涵蓋範圍的查證不得讀取 `^TWII`，也不得讀取任何重放或前瞻結果）；(2)「ADR 登記表」一點的登記 commit 核對，改為執行／判斷分離（章程 §4）；(3)「首次登記的同批條件」改為「必須同批定案四件事」，在既有兩個子點之後加兩個子點（`rolling` 的來源公布時點查證；重放端是否與前瞻對齊 X1 收盤本身不可用接入後的查證）。方向：補定義（收緊）；首次登記同批條件：收緊。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- I2-3（D-3 `forecast_index_check` verification 組的 `result` 列舉；TA 提案 I2-3；與事先宣告 §6.3 查證程序結果列舉 V16-08 同批）：方向：收緊。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。只換這一段，被取代的原文——
  > `result ∈ {value_obtained, source_has_no_day, query_failed, source_not_connected}`
- I2-4（D-3 `forecast_input_series` 的 `series_kind` 一點，另在同一層新增「重放快照與 bar 值的正規化」一點；TA 提案 I2-4）：方向：補定義（收緊）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。「重放快照與 bar 值的正規化」無被取代原文。只換這一段，被取代的原文——
  > 加 `series_kind ∈ {index_bars, basket_log_returns}`（A-34）。
- I2-5（D-3 新增「重放登記檔」與 `forecast_replay_index_check` 兩點，緊接 I2-2 之後；TA 提案 I2-5，風控改字：`freeze_evidence` 加 `base_ref`、`created_at`，`v_star` 加 `registration_commit`；「凍結日 F 的取得依據」整點改寫；「重算核對」插入 F 與 `base_ref` 的驗證；registration 組的祖先關係更正為 freeze ⊂ registration ⊂ 執行時 `code_commit`；snapshot 組加 `fetch_outcome` 與取數嘗試的規則；共通欄位 `registration_id` 一點加「detection 以後的各列所用快照，一律是 `fetch_outcome = stored` 的那一列」）：無被取代原文。方向：補定義（收緊）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- I2-6（D-3 新增 `forecast_replay_outcome` 一點，緊接 `forecast_replay_index_check` 之後；TA 提案 I2-6，照 TA 字面）：無被取代原文。方向：補定義（收緊）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- I2-7 (a)（D-9 第 7 點，「不讀也不寫 `forecast_settle_eval`、……」一行之後、同一層新增一個子點；TA 提案 I2-7 (a)）：無被取代原文。方向：不變（指向）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- I2-7 (b)（D-9 第 7 點末段，兩處；TA 提案 I2-7 (b)，第一處的新字用風控 suggested 字句）：方向：不變（指向）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。第一處被取代的原文（從「〔已決（X2 部分）：」起整個括號）——
  > 〔已決（X2 部分）：X2 在重放期的對照日曆已由事先宣告 v0.15 V15-01、V15-02 登記，見本點句末；其餘部分見 N-22c，仍待定義〕

  第二處被取代的原文（行尾）——
  > 其餘（存放、判定視圖、觀察日來源、起訖日、預測端序列、確認有誤之後的路徑）見後續追蹤清單 N-22c。
- I2-7 (c)（D-9 第 7 點，在 (a) 新增的子點之後、同一層新增 N-22d 約束；TA 提案 I2-7 (c)，風控改字：句末加「登記之前不得執行重放」）：無被取代原文。方向：補定義（收緊）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- I2-8（D-1 模組表，在 `app/forecast/display.py` 一列之前新增兩列；TA 提案 I2-8，風控改字：`replay_checks.py` 一列的描述改為每次取數嘗試都留紀錄、成功的一次存成唯一的快照）：無被取代原文。方向：不變。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- I2-9（對實作的約束，新增 FL-69，插在 FL-68 之後、FL-24 之前；TA 提案 I2-9 (a)～(g)，風控加 (h)、(i)、(j)）：無被取代原文。方向：收緊（測試）。風控 2026-10-18 v0.16 單項確認；CEO：表數知悉。
- G 表數（19→21；評估摘要、Consequences、修訂清單 M-11、待決事項；TA 提案 G 段「v0.16 這一批」）：方向：知悉（風控 2026-10-18 v0.16 單項確認第二節 A 的 G 列與第二節 E：屬知悉，不需明示同意）。評估摘要「最大代價」該行整行，被取代的原文——
  > - 表數多（19 張），寫入規則有一部分在 trigger 裡。

  Consequences「代價與壞處」該行整行，被取代的原文——
  > - 19 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。

  M-11 列第四格（修訂清單表）兩處，被取代的原文——
  > 新增 14 張表（第九、十批加

  > ；N-24 加 `forecast_gap_audit`）並取欄位聯集

  改為：評估摘要與 Consequences 的「19 張」改為「21 張」；M-11 的「新增 14 張表」改為「新增 16 張表」；在 `forecast_gap_audit` 之後加「；N-22c 加 `forecast_replay_index_check`、`forecast_replay_outcome`」。待決事項 CEO 段新增第 15 點，無被取代原文。編輯註記：本段之前各批次條目引用的「18 張」「19 張」「13 張」「14 張」是當時的原文，不改。CEO：表數知悉。
- D-9 第 7 點「理由」第二子點的狀態註（coordinator 裁定，CEO 可推翻；方向：不變（狀態註））：tech-writer 回報該子點的「〔推論；重放期起訖日未登記，見後續追蹤清單 N-22c〕」在 V16-02 登記起訖日的決定規則之後已過時。coordinator 裁定原句保留，在該〔……〕之後插入〔v0.16 註：重放期起訖日的決定規則已由事先宣告 v0.16 V16-02 登記，實際值於 §4.7 執行閘門 (a) 登記；本點原文不改〕。無被取代原文。
- 後續仍待另批處理（不在本批 ADR 內）：決策包二補遺第 20 項改寫、後續追蹤清單 N-22c／N-22d／N-28／S-2 的更新，由 coordinator 依風控 2026-10-18 v0.16 單項確認第四節處理。

---

> N-29 待重算（2026-10-18）套用（2026-10-18，tech-writer；風控單項確認：`work/reviews/2026-10-18-N29與plan略過紀錄單項確認-風控.md` 第四節「tech-writer 照改清單」N-29 批第 1～9 點；tech-architect 提案：`work/reviews/2026-10-18-N29與重放存放及plan略過紀錄與v0.16定名提案-tech-architect.md` 第二節 B 段 N29-1～N29-9，風控沒有另給字句處照 TA 原字面）。
> - **本批單獨成批**：不與 v0.16 批（上一段）、plan 批（`plan_coverage_log`）同批。風控要求 N-29 批內部不得拆開，期限為 D-9 結算程式實作前（風控 2026-10-18 N-29 單項確認第一節「同批與表數」）。
> - **事先宣告 N-29 (b) 另由 quant 在後續版次登記**，版次不早於本批，且必須在 dirdef 凍結前（風控 2026-10-18 N-29 單項確認第一節、第四節 quant 照改清單）。本批的 ADR 字面以「事先宣告 N-29 (b)」「後續追蹤清單 N-29 (b)」指向它，登記之前，到期處理不生效，依 D-9 第 5 點「待重算」持續待重算。
> - **不新增 A 號**，累計方向統計維持 18／2／9／1／3（見上「第九、十批」段的方向表）。
> - **本批沒有任何一項需要 CEO 明示同意**（風控 2026-10-18 N-29 單項確認第一節、第二節 A 的 CEO 欄）。
> - **N29-6 的方向為「補定義（兩面）」**，照風控字句（見下 N29-6 條目）。
> - **表數不變**：本批只在既有兩張表（`forecast_correction_job`、`forecast_correction_job_end`）加欄位，不加表（TA 提案第一節「表數」）。
> - **本批沒有套用的項目**：(1) plan 批（風控第 10～12 點：I3-1～I3-3，`plan_coverage_log`、FL-70），下一批另做；(2) N29-10（交 quant 的事先宣告字面、交 creative-lead 的 `RECORD_STATUS_RESETTLE_PENDING` 片段起草），不在本 ADR 內；(3) N29-11（`E_CHANGING_EVENTS` 加 `forecast_correction_job_end`）：原列於此處為「本批未套用」，現已套用（2026-10-18，tech-writer 後續一批）。風控字句要求的 snapshot 端讀取序號欄名，由 tech-architect 定為 `stats_json.e_read_job_end_seq`（`work/reviews/2026-10-18-N29-11第三序號與LM155三項確認-tech-architect.md` 第一節第 1 點），套用內容與被取代原文見下方 N29-11 條目，本處原文（被取代）亦錄存於該條目。原文所述「與本批同一個 commit」的要求（風控第四節 coordinator 核對第 22 點）仍由 coordinator 在 commit 時處理；tech-writer 本批未 commit。
> - **標點處理**：N29-8 風控要求在首句「值只能是待重算片段（……PA-8）」之後接「這是雙向規則：待重算片段也只能出現在本路徑。」；TA 原句以冒號接兩個條件子點，tech-writer 把冒號改為句號、再接該句，子點內容不動。請 coordinator 確認可接受。
> - **TA 提案中未插入的一句**：TA 提案 N29-6 另有一句「(乙) 列的 `wait_sessions`、`wait_deadline_session` 照抄被 supersede 列，D-3 原規則不變；所用的期限可由本作業的 `observed_sessions_json` 重算得出。」，TA 沒有把它放進「新字」，風控第四節也沒有列為要寫入的字句，所以本批沒有寫入 ADR 本文（B 類轉錄不順手補字）。
> - **定位與被取代原文**：定位一律用字串，從檔尾往前套（先套條文、後寫本段）。被取代的原文取自套用前的 ADR 檔現況（任務說明：HEAD 為 `bcc84db`，ADR 本身沒有未 commit 的修改）；tech-writer 沒有用 git 對該 commit 逐字核對（本任務沒有 git 工具），請 coordinator 對照核對。TA 提案所載行號因 v0.16 批而漂移，一律以字串為準。
> - **本段含被取代原文的逐字引用**，其中的定位字串（例如「三類都沒有時不啟動」「其他 scope、其他 `status_reason` 的改記作廢」）會在本段命中，屬歷史列，不是現行條文。

**N-29 待重算（2026-10-18）（D-3、D-9 第 5 點、D-11.4 第 11 點 (g)(h)、FL-22、FL-68；掛 A-65、A-77；方向：逐項標示，見各項）**
- N29-1（D-3 `forecast_correction_job` 欄位清單，及其後「判定視圖欄位」子點之下新增一點；TA 提案 N29-1）：方向：補定義（收緊）。送風控：已核可，照 TA 字面（風控 2026-10-18 N-29 單項確認第二節 A）。CEO：否。欄位清單只換這一段，被取代的原文——
  > index_check_max INTEGER NOT NULL, index_series_sha256 NOT NULL

  另在「`index_series_sha256`、`index_final_now`、……與 `forecast_settle_eval` 的同名欄位同義」一行之後、同一層新增一點，無被取代原文。
- N29-2（D-3 `forecast_correction_job_end` 欄位清單，及 `rejected_count` ＞ 0 一行之後新增一點；TA 提案 N29-2，風控三處改字）：方向：補定義（收緊）。風控改字：(1) `rejected_json` 的項加 `causes`；(2) `pending_json` 首句改為「本作業結束時的待重算集合（D-9 第 5 點「待重算」，含 `write_validation_failed` 一種）」；(3) 寫入 job_end 的驗證第 2、3 子點改字（第 2 子點以 `causes` 含 `x2_session_removed` 判定；第 3 子點加「本作業重查後沒有任何欄位改變（§6.4 第 3 點，不寫列）」一格）。TA 原稿的這幾處從未寫入本 ADR，本段不重錄，TA 原稿見 TA 提案第二節 B 段 N29-2。CEO：否。欄位清單只換這一段，被取代的原文——
  > rejected_count, void_late_data_count, ended_at)
- N29-3（D-9 第 5 點 ④「已結算數值所用的大盤 bar」第二子點，並在其後、同一層新增「待重算」一點；TA 提案 N29-3，風控改字）：方向：補定義（收緊）。風控改字：在「待重算」一點的「理由」子點之前、同一層插入兩個子點（未通過比對的日期視為沒有可用資料、任何欄位都不得讀取；`write_validation_failed` 同樣列入 `rejected_json` 與 `pending_json`、不適用 N-29 (b) 期限），並把首句出處括號改為「（N-29；tech-architect 2026-10-18；風控 2026-10-18 v0.15 單項確認第二節 C、N-29 單項確認）」（TA 原括號為「（N-29；tech-architect 2026-10-18；風控 2026-10-18 v0.15 單項確認第二節 C）」，從未寫入本 ADR）。CEO：否。第二子點整句取代，被取代的原文（取自 ADR 現況，含 v0.15 批加入的括號「（以 `checked_values_sha256` 的正規化規則比對）」；TA 提案所引原文沒有這個括號）——
  > - 更正鏈中沒有任何結算窗涵蓋的日期（例如 X2 順延後的新 T+h），取本作業快照的列。該列必須與某一列 `forecast_settle_eval` 大盤快照中 d 的列數值相同（以 `checked_values_sha256` 的正規化規則比對），也就是已經過 D-9.2 ③ 的偵測；不成立時，該筆不寫入，計入 `rejected_count`，記 WARNING。
- N29-4（D-3「晚到資料的觸發」第 1 點與 D-9 第 5 點「理由」引文；TA 提案 N29-4 (a)～(d)，風控核可照 TA 字面，同意改動風控 N21-4 的「三類」）：方向：(a)～(c) 補定義（收緊）；(d) 不變（引文同步）。CEO：否。
  - (a) 被取代的原文——
    > 同一步另以唯讀查詢檢查兩件事，有任一項就同樣啟動（N-21）：
  - (b) 在 `(W_V, MAX(check_id)]` 那一行之後、同一層新增，無被取代原文。
  - (c) 被取代的原文——
    > W_E、W_V 與 D-3 `forecast_correction_job` 的 `ledger_event_from`、`index_check_from` 同一定義，由同一個函式導出。三類都沒有時不啟動（D-3「`triggers_json` 必須非空」不變）。啟動與否只依本點三類觸發是否存在，
  - (d) 被取代的原文——
    > 與 D-3「晚到資料的觸發」第 1 點「啟動與否只依本點三類觸發是否存在」不合
- N29-5（D-11.4 第 11 點 (h)「原因怎麼歸屬」，「來源修訂依 D-3『晚到資料的觸發』。」一行之後、同一層新增一點；TA 提案 N29-5，風控句末加「前一個已完成作業 `pending_json` 中的 `forecast_id`，……受影響日期同上。」）：無被取代原文。方向：補定義（收緊：只會多記）。CEO：否。
- N29-6（D-11.4 第 11 點 (h) R10-2「適用範圍」一點：把 N-27 的兩個子點改為 (甲)、(乙) 兩支，並調整其後兩處；併入 S-1；TA 提案 N29-6，風控改 (乙) 與 `window_factors_json` 一行）：方向：補定義（兩面）：放寬面是寫入驗證對 X2 順延後重算得出的作廢不限 scope 與原因；另一面是只有事先宣告 §6.3 L1328、L1330 已規定、逐位重算相同的作廢寫得進去，等待類原因須 N-29 (b) 登記且到期，作廢計入作廢率與 W，(甲) 加 S-1，其他一律拒絕。CEO：否（風控 2026-10-18 N-29 單項確認）。(甲) 照 TA 字面；(乙) 為風控改字版（`void_reasons_json` 依 scope 的允許集合限制；比對加 `window_factors_json`）。被取代的原文（兩個子點，整行）——
  > - `scope_kind = market`，`status_reason = index_bar_confirmed_erroneous`；
  > - 以本作業的判定視圖（D-9 第 5 點 ④）、經 `scoring.py` 的同一個函式重算，P(T) 或 P(T+h) 至少一根的收盤是 D-3 `forecast_index_check`「判定時怎麼讀」所說的「確認有誤、尚未取得正確值」；

  「適用範圍」下的 `window_factors_json` 一行整行取代（風控字句），被取代的原文——
  > - `window_factors_json` 和前一列相同。

  「其他 scope、……一律拒絕」一句，只換前半，被取代的原文——
  > 其他 scope、其他 `status_reason` 的改記作廢，不屬於本 ADR 已定義的 supersede，一律拒絕

  該句其餘部分不動。
- S-1（已併入 N29-6 的 (甲)：`correction_causes` 至少含 `settlement_close_corrected` 或 `x2_session_removed` 之一）：無被取代原文。方向：收緊（風控 2026-10-18 N-29 單項確認第二節 A 的 S-1 列：核可，已併入 (甲)）。CEO：否。
- N29-7（D-3 `forecast_settle_eval` 的「限制」一點，更正讀取限制與 `settlement.py`、`correction.py` 實際讀取的既有不一致；TA 提案 N29-7）：方向：補定義（更正既有不一致；AST 允許清單形式上擴大，只限已核可條文本來就要求的讀取）（風控 2026-10-18 N-29 單項確認第二節 A）。CEO：否。只換這一段，被取代的原文——
  > 只有 `validation.py` 的 §4.2 報表與稽核工具可以讀它；`views`、API route 與匯出不得讀它（AST 列舉呼叫點，比照 `forecast_void_late_diag`）。
- N29-8（D-11.4 第 11 點 (g)，「§4.2 的計數來源」一行之後、與「FAIL_CLOSED 路徑的狀態片段」同一層新增「待重算路徑的狀態片段」一點；TA 提案 N29-8，風控改四處：雙向規則一句、`validation.py` 呼叫同一個 `store.py` 函式一句、「優先序」子點改字、白名單加 `threshold_display` 與 `disclosure_fragment_ids` 子點改字並加「大盤列不得含 LM-22」）：無被取代原文。方向：收緊（揭露）。CEO：否。片段逐字由 creative-lead 起草，送風控（PA-8），核可之前 FL-52 (d) 失敗。
- N29-9（對實作的約束 FL-68 (g)、新增 (j)，FL-22 (b) 加一格；TA 提案 N29-9，風控在 (j) 與 FL-22 句末加字）：方向：收緊（測試）。CEO：否。FL-68 (j) 與 FL-22 新格無被取代原文。FL-68 (g) 只換這一段，被取代的原文——
  > X2 順延後的新 T+h bar 不在任何 `forecast_settle_eval` 快照中（或數值不同）→ 該筆不寫入，`rejected_count` 加 1。
- N29-11（`E_CHANGING_EVENTS` 加 `forecast_correction_job_end`，第三序號 `stats_json.e_read_job_end_seq`；tech-architect 2026-10-18 回報 `work/reviews/2026-10-18-N29-11第三序號與LM155三項確認-tech-architect.md` 第二節「決策：可直接貼入的字面」第一～五組；風控依據：2026-10-18 N-29 單項確認）：本條取代原「本批未套用」條目與上方「本批沒有套用的項目」(3)，兩處原文逐字錄存於本條末。風控方向：收緊；CEO：否。本條只記 tech-writer 這一批已套用的項目，字句逐字照 TA 的「可直接貼入的字面」，沒有另補技術細節。（coordinator 2026-10-18 補註：上句與「風控方向：收緊」只指 TA 第一～五組；T-1～T-8 的字句來源是風控 2026-10-18 單項確認的照改清單，方向逐項見下列兩點。）
  - **已套用**：第一組 1-a～1-c、第二組 2-a～2-c、第三組 3-a～3-e 與 3-g、第四組 4-a、第五組 5-a～5-d。方向（依 TA 回報）：1-a、1-c、2-b、3-a、3-b、3-d、4-a 收緊；1-b 不變（編排）；3-c 補定義（收緊）；3-e 收緊（揭露）；3-g 補定義（不放寬：只多開一個只讀一欄的呼叫點）；5-a～5-c 收緊（測試）；2-a、2-c 隨 2-b 同步字數，TA 未另標方向；5-d 為本修訂紀錄的改寫。4-a 的第一句是風控原字（風控 2026-10-18 N-29 單項確認），一字不改。
  - **風控 2026-10-18 修改後核可（T-1、T-2），方向：補定義（不放寬）；CEO：否**：3-g 改到的 D-11.4 第 11 點 (g)「判定只由 `display.py` 的 `record_status_fragment(row)` 產生……」一句，是風控已核可過的字句。本批原依 coordinator 指示先照 TA 字面套，coordinator 另送風控做單項確認；風控已於 2026-10-18 單項確認（`work/reviews/2026-10-18-N29-11與LM155追加及作廢統計單項確認-風控.md` 第四節 T-1、T-2），並要求照風控字句改寫：T-1 取代 3-g 的 TA 字面，T-2 取代 3-b 括號內的「同一個 `store.py` 函式」一句。被取代的原文見本條末「T-1～T-9 被取代的原文」。
  - **原「本批未套用，須先送風控」一點，已依風控 2026-10-18 單項確認（同上檔第四節 T-3～T-8）改寫為已套用**，字句逐字照該檔。各項方向：
    - (γ)（含 L419、FL-68 (j)）：補定義（兩面）；CEO：否。
    - (2)：補定義（收緊）；CEO：否。
    - (3)：補定義（收緊）；CEO：否。
    - 測試格：收緊（測試）；CEO：否。
  - **N29-11a 備案**：經風控 2026-10-18 否決，不寫入 ADR。
  - 1-a（D-11 `forecast_validation_snapshot` 一點的 `stats_json` 登記）：被取代的原文——
    > （r3，A-63；RC′-2、RC″-2、RC‴-1）`stats_json` 另登記 `e_read_event_seq`、`e_read_outcome_seq`（`pa9_holds` 的 `e_changed_since` 比較基準，見第 4 點第 11 項 (c)），以及 `e_read_at`（稽核用，不作比較基準；也不用 `computed_at`）。
  - 1-b（D-11.4 第 11 點 (c)「比較基準」，「snapshot 的計算在一個明確開啟的 read transaction 內讀 E」一點）：只換「兩個值」為「三個值」，被取代的原文（整點）——
    > snapshot 的計算在一個明確開啟的 read transaction 內讀 E，並在同一個 transaction 內讀出兩個值，寫入 `stats_json`：
  - 1-c：在 `e_read_outcome_seq` 一行之後、「沒有列時記 0。」之前、同一層新增 `e_read_job_end_seq` 一行，無被取代原文。
  - 2-a（`e_changed_since(snapshot)` 一點）：只換「兩項」為「三項」，被取代的原文（整點）——
    > `e_changed_since(snapshot)` 為真，若且唯若下列兩項任一成立：
  - 2-b：在「存在 `supersedes_id IS NOT NULL`、而且 `outcome_id > e_read_outcome_seq` 的列。」一行之後、同一層新增第三項比較，無被取代原文。
  - 2-c：只換「兩個欄位」為「三個欄位」，被取代的原文（整行）——
    > 兩個欄位任一缺漏或不是整數，一律為真。
  - 3-a（D-11 `forecast_validation_snapshot`「前提被破壞時撤銷」一點）：只換序號清單，被取代的原文——
    > 任何 snapshot 的 `e_read_event_seq` 或 `e_read_outcome_seq` 大於目前看得到的對應最大值時
  - 3-b（D-11.4 第 11 點 (c)「讀取順序（RC‴-1）」一點）：只換粗體部分，被取代的原文——
    > **先讀 `e_read_event_seq`、`e_read_outcome_seq`，再讀 E**
  - 3-c：在 `event_id`、`outcome_id` 都是 `INTEGER PRIMARY KEY AUTOINCREMENT` 那一點之後、同一層新增一點，無被取代原文。
  - 3-d（D-11.4 第 11 點 (c)「寫入函式與 SQL 不得指定」一點）：只換前半，被取代的原文——
    > 寫入函式與 SQL 不得指定 `event_id`、`outcome_id`，由 SQLite 配號
  - 3-e（D-11.4 第 11 點 (c) N-6「變動項」一點）：只換後半，被取代的原文——
    > ，以及 `supersedes_id IS NOT NULL` 的 `forecast_outcome`（依 `outcome_id`）。
  - 3-g（D-11.4 第 11 點 (g)，待重算路徑的「判定只由 `display.py` 的 `record_status_fragment(row)` 產生」一點）：只換前半句，被取代的原文——
    > 這是 `views` 讀取 `forecast_correction_job`、`forecast_correction_job_end` 的唯一呼叫點。
  - 4-a：在 `forecast_outcome` 中 `supersedes_id IS NOT NULL` 的列一行之後、同一層新增 `forecast_correction_job_end` 一項與其「依據與範圍」子點，無被取代原文。
  - 5-a（FL-58 之下，RC‴-1 六格之後）：在「`sqlite_master` 斷言兩欄都是 `INTEGER PRIMARY KEY AUTOINCREMENT`。」一行之後、與「（N-5）RC‴-1 六格之後加兩格」同一層新增一點，無被取代原文。
  - 5-b（FL-68 (j) 句尾）：在「驗證統計不計入待重算集合；job_end 寫入後 `e_changed_since` 為真。」之後接字，無被取代原文。
  - 5-c（FL-64 (e) 句尾）：在「兩種情形之後的下一個作業都可以寫入並寫完 job_end，其他觸發不被擋下；」之後接字，無被取代原文。
  - 5-d：改寫兩處「N29-11 本批未套用」。第一處是上方「本批沒有套用的項目」(3)，被取代的原文——
    > (3) **N29-11（`E_CHANGING_EVENTS` 加 `forecast_correction_job_end`）本批未套用**：風控字句要求 snapshot 端的讀取序號欄名「由 TA 依 `e_changed_since` 的既有形狀補上」，但 `e_changed_since` 的既有形狀是 `stats_json` 的兩個讀取序號 `e_read_event_seq`、`e_read_outcome_seq`（D-11.4 第 11 點 (c)「比較基準」，並引用於 D-11 `forecast_validation_snapshot` 一點的 `stats_json` 登記與「前提被破壞時撤銷」），沒有任何既有欄位能記 `correction_job_id`，補上這一點必須新增 `stats_json` 欄位與 `e_changed_since` 的第三項比較，欄名無法由既有形狀推出，因此停下來回報 coordinator，由 tech-architect 定欄名後再補（不得由 tech-writer 自訂）。本批 FL-68 (j) 風控字句末句「job_end 寫入後 `e_changed_since` 為真」依賴 N29-11，在 N29-11 補上之前，這句與 `E_CHANGING_EVENTS` 的清單不一致；風控要求 N29-11 與本批同一個 commit（風控第四節 coordinator 核對第 22 點），請 coordinator 在 N29-11 補上之後再一起 commit。

    第二處是本條自己的原文（整行），被取代的原文——
    > - N29-11（`E_CHANGING_EVENTS` 加 `forecast_correction_job_end`）：**本批未套用**，見上方「本批沒有套用的項目」(3)。風控方向：收緊；CEO：否。
  - T-1～T-9 被取代的原文（風控 2026-10-18 單項確認，`work/reviews/2026-10-18-N29-11與LM155追加及作廢統計單項確認-風控.md` 第四節「給 tech-writer 的照改清單」；新增字句逐字照該清單，被取代的原文逐字錄存於下）：
    - T-1（D-11.4 第 11 點 (g) 待重算路徑「判定只由 `display.py` 的 `record_status_fragment(row)` 產生」一點，從「這是 `views` 讀取」到該點句尾「（AST 列舉呼叫點）。」整段取代；被取代的是 3-g 套用後的 TA 字面）——
      > 這是 `views` 讀取 `forecast_correction_job`、`forecast_correction_job_end` 的唯一呼叫點；唯一的例外是第 4 點第 11 項 (c) 的序號比較函式（`e_changed_since` 與 `mask_episodes` 共用）。它經 `store.py` 的另一個單一唯讀函式讀取 `forecast_correction_job_end` 的 `correction_job_id`，不讀其他欄位；snapshot 寫入端讀 `e_read_job_end_seq` 也只經這個函式（N29-11；AST 列舉呼叫點）。`validation.py` 依事先宣告 N-29 (b) 計算驗證統計時，呼叫同一個 `store.py` 函式（AST 列舉呼叫點）。
    - T-2（D-11.4 第 11 點 (c)「讀取順序（RC‴-1）」一點括號內，只換這一句）——
      > 由 D-11.4 第 11 點 (g) 的同一個 `store.py` 函式讀取
    - T-3（D-3「晚到資料的觸發」第 1 點，第四類觸發大盤子條件，整行取代）——
      > - `scope_kind = market`，而且該列的大盤快照含該項 `shifted_t_plus_h` 的列；
    - T-4（同一點之下「W_E、W_V、W_S ……」一段括號內，只換這一句）——
      > 第四類只依新的觀察日、新的結算快照列或新的定案 run 是否存在，不依時間經過；沒有新資料時不啟動
    - T-5（FL-68 (j)，兩處）：第一處只換這一句，被取代的原文——
      > 下一次結算評估帶來新觀察日或含 d 的快照列 → 第四類觸發啟動

      第二處是在「沒有任何新資料的評估 → 不啟動（spy）。」之後接字，無被取代原文。
    - T-6（D-11.4 第 11 點 (h)，「修正之後，由第四類觸發重查。」句尾接字）：無被取代原文。
    - T-7（D-11.4 第 11 點 (g) 待重算路徑「優先序」一點，從「優先序：」到「走 LM-143。」整點取代）——
      > 優先序：本路徑先於 LM-150、LM-154、「診斷欄位更正的例外」與一般已結算列的呈現。與 PIT 違規列的標示（LM-110＋LM-114）或 A-27 (c) 同時成立時的取捨，由 tech-architect 在本點補定義，隨待重算片段送風控；補定義之前，同時成立的列不顯示 label 與任何結算結果。最新 outcome 不是 `resolved` 時不適用，走 LM-143。
    - T-8（測試格，兩處）：FL-68 (j) 在 T-5 新加的 (γ) 格之後接字，以及 5-b 末句「所列的兩個 `store.py` 函式。」之後接字：無被取代原文。
    - T-9（本修訂紀錄 N29-11 條目的兩點，整點取代）——
      > - **3-g 待風控單項確認**：3-g 改到的 D-11.4 第 11 點 (g)「判定只由 `display.py` 的 `record_status_fragment(row)` 產生……」一句，是風控已核可過的字句。本批依 coordinator 指示先照 TA 字面套，coordinator 另送風控做單項確認；風控確認之前，本項狀態為「待風控單項確認」。

      > - **本批未套用，須先送風控**（TA 回報「追加三點」與備案；本批沒有套用，也沒有改動對應條文）：(1) 的 (γ)（D-3 第四類觸發的大盤子條件，即 `scope_kind = market`，而且該列的大盤快照含該項 `shifted_t_plus_h` 的列 那一句）；(2) 的 D-11.4 第 11 點 (h) 待重算項 `reason` 明文（TA 回報定位為「修正之後，由第四類觸發重查。」句尾）；(3) 的 D-11.4 第 11 點 (g)「優先序」子點補定義；N29-11a 備案（只在 (γ) 被否決時才需要）。

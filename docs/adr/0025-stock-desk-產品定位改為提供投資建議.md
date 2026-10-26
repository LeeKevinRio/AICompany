# ADR-0025：stock-desk 產品定位改為提供投資建議——建議引擎擴充、價位後端化、預測紀錄與分期

- 狀態：**accepted**
  - 〔2026-10-16 CEO 核可：CEO 書面原話「第二節全部核可，五日方向指未來5日」（第二節＝`work/dispatch/2026-10-15-決策包-ADR-0025與新定位.md` 第二節）；決策紀錄見 `work/dispatch/2026-10-16-CEO決策-ADR-0025核可與五日方向.md`〕
  - 原狀態文字（保留）：proposed〔2026-10-16 已核可，見上〕
  - 生效範圍：依上列決策紀錄「生效範圍」一節（coordinator 定案，CEO 可推翻）；文末「待決事項—CEO」各項的結果以〔〕註記於各項行尾。
- 日期：2026-10-15
- 決策者：tech-architect（草案）；待 CEO 核可。〔2026-10-16 CEO 核可，見狀態欄〕產品定位本身已由 CEO 於 2026-10-15 書面決定（`work/dispatch/2026-10-15-CEO決策-產品定位改為提供投資建議.md`），本 ADR 不重議定位，只決定架構、模組邊界、資料契約與分期。
- 適用範圍：僅 product/stock-desk 產品線（本 ADR 不存在於 main）。
- 前提：使用範圍為 B1（b-1）純自用（CEO 決策紀錄第 33 行，coordinator 定案，CEO 可推翻）。前提改變即觸發失效條件 F-1。
- 修訂（提案中）：ADR-0027（proposed）提案部分修訂 D-1 接線、D-2.2 解讀、D-3 missing_inputs 型別、D-5.7 價位口徑、D-6.1～D-6.5、AV-17、AT-6、AT-7、F-2、F-3 與 D-12 Phase 3 驗收欄位名（M-1～M-11，見 docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md）；各項須 CEO 核可，核可前本檔為準；本檔原文不改。
- 修訂（提案中）：ADR-0030（proposed）提案部分修訂 D-6.1、D-6.2、D-6.3、D-6.5 驗證狀態、F-2 評估時點、AV-17、AT-6、AT-7、F-3 與 D-12 Phase 3 驗收欄位名（C-M1～C-M4，見 docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md）；ADR-0027 的 M-1～M-11 隨其凍結暫停；各項須 CEO 核可，核可前本檔為準；本檔原文不改。
- 與既有 ADR 的關係（細節見 Context §4）：
  - **部分修訂 ADR-0004（accepted）**：§4「無目標價」縮窄（見 D-5.1）；`DISCLAIMER` 常數字面與 Decision §5「研究與教育工具」的定位理由失效，改由風控重訂；§1～§3、§5 規則版本化、`ACTION_DIRECTION`、保守閘門全部維持。比照 ADR-0024 對 ADR-0009 的做法，只在 ADR-0004 檔頭「修訂」清單加一行指標，不原地改寫。**須 CEO 核可。**
  - **取代 ADR-0018（proposed）**：計算歸屬（D-1 後端唯一來源、D-2 `AdviceResponse` 同層欄位、D-5 基準價與 fail-closed）以及 K-1～K-16、T-1～T-7 的守門精神，由本 ADR D-5 吸收沿用。固定比率公式（D-3 的 0.92A、1.2A、2R）與「需要 CEO 決定」#1、#2 不再適用於畫面；舊公式「搬遷＋golden parity」那一期不執行（理由見 D-5.6）。ADR-0018 狀態改為 `superseded by ADR-0025`。
  - **部分修訂 ADR-0012（accepted）**：C-15 識別字白名單加入 `app/forecast/scoring.py`；其餘不變（含 L401「board 不帶任何規則引擎輸出」）。**須 CEO 核可。**
  - **相容、不修訂**：ADR-0002、0003、0005、0006、0007、0008、0009、0010、0011、0014、0015、0016、0017、0019、0020、0021、0022、0023、0024。
- 編號說明：起草時 `docs/adr/` 最後一份為 ADR-0024；0013 為員工線佔用。
- 標註約定：〔事實：檔案:行號〕為起草者 2026-10-15 讀到的工作目錄狀態；〔盤點所引〕為轉引 `work/research/2026-10-15-外部prompt需求對照盤點.md`、起草者未逐一複核；〔推論〕為起草者判斷。行號會隨 commit 漂移。

---

## 評估摘要（結論先行）

- **採用**：
  1. 規則式擴充（Options A1）。新增四個後端純函式層：方向判斷 `app/outlook`、結構式價位 `app/keylevels`（沿用 ADR-0018 的套件名，內容換成 levels v2）、持股行動 `app/plan`、預測紀錄與計分 `app/forecast`。既有 `build_advice` 的行為與輸出欄位不動。
  2. 3 日與 5 日各用一份規則檔、各自的結果定義、各自的驗證統計；任何程式路徑都不得從一個 horizon 推出另一個。
  3. 價位一律由結構（擺動高低點、前高前低、缺口邊緣、均線）、ATR 緩衝與量價證據推出，每個價位至少附一筆可核對依據。系統自己的價位不得以固定百分比為依據；固定比率只允許來自使用者自設參數，並且要標明是使用者的參數。
  4. 預測紀錄採 append-only、point-in-time，必須在下一個交易時段開盤前寫入。歷史回放與上線紀錄分開報告；兩者都要並列基準，未優於基準就直接呈現。
  5. 族群分三層（主族群／細項／題材）。主族群取官方產業別；細項與題材必須附公司業務或官方來源依據，並標註生效與記錄時間。
  6. 預設不引入 LLM。
- **否決**：
  - 黑箱 ML 直接產生方向或動作（ADR-0004 維持）。
  - LLM 生成分析。
  - 改寫既有 engine action 列舉。
  - 沿用固定百分比價位。
  - 付費資料或付費模型。
- **最大代價**：
  - 證據要累積很久。以單一標的的 5 日判斷為例，不重疊樣本一年只有約 50 筆〔推論〕。可預期的是，大多數判斷在相當長一段時間內都會顯示「證據不足」或「未優於基準」。
  - 這次修訂要推翻多項風控既有裁示：phase8 §1.3、§4 C5／C6／C8，以及 PX-3／4／5／7／12／13／25。必須等風控重訂護欄後才能出貨。

---

## Context（背景）

### 1. 舊定位（事實）
- 產品說明明文：「本工具為研究與教育用途，不產生投資建議、目標價或操作指引。」〔盤點所引：`work/stock-desk-產品說明.md:3`〕
- 建議卡常數 `DISCLAIMER = "本工具為研究與教育用途，非投資建議"`〔事實：`apps/stock-desk/backend/app/advice/engine.py:60`〕；每頁頁尾常駐同義句〔盤點所引：`frontend/app/layout.tsx:20`〕。
- ADR-0004 §4：「規則只輸出『加碼／觀望／減碼／停損／獲利』，不輸出『目標價』」〔事實：`docs/adr/0004-…:107-110`〕。Decision §5 的理由是「Stock Desk 定位『研究與教育工具』」〔事實：同檔 `:66-67`〕。
- 定位與功能已經有落差：建議卡輸出 add／hold／reduce／stop_loss／take_profit〔事實：`engine.py:56`〕；前端關鍵價位面板輸出停損 `max(A−2ATR, 0.92A)`、停利 `1.2A` 與 2R〔事實：`frontend/app/lib/keyLevels.ts:78-83,138-145`〕。

### 2. 新定位
- CEO 2026-10-15：「我需要的就是投資建議」。要納入的能力有八項，見決策紀錄第 20-28 行。外部 prompt 的護欄一併採納，見第 29 行。
- 維持的部分（決策紀錄第 35 行）：point-in-time、成本、樣本門檻、不自動下單、不用黑箱 ML 直接產生動作。
- 是否引入 LLM 不在 CEO 決策範圍內，須另案處理。本 ADR D-10 給出建議。

### 3. 外部 prompt 對架構有約束力的要求（原文 `work/research/2026-10-15-外部prompt需求原文.md`）
- 不承諾準確率；不編造行情、消息、機率、價位；證據不足時說明缺什麼（L15）。
- 一般指標計算不使用語言模型；若使用，要說明用途、資料流與 Token 成本；不增加付費服務（L21-22）。
- 目前盤勢與未來 3／5 日展望要分開，不能把當日漲跌當成預測（L31）。天氣要有資料日期、依據與有效涵蓋（L33）。
- 分類要有公司業務或官方來源，不能把參與供應鏈直接當成主業（L48）。只分析部分成分股時，要標示抽樣方法與覆蓋（L51）。
- 每個價位都要有可核對的依據，不得用任意固定百分比（L76）。加碼要同時有價格、量能、趨勢、預算條件，不能因為下跌就攤平（L79）。停損不保證成交（L80）。不自動下單（L81）。
- 3 日與 5 日分開定義、分開驗證；使用還原股價；禁止前視、事後挑選與存活者偏誤；與基準比較；樣本不足要直說；方向回顧、策略績效、校準機率三者分開；保存當時的預測與後續結果（L89-97）。
- 不經同意，不得把成本與股數傳到外部服務（L42）。

### 4. 與既有 ADR 的衝突點清單

| ADR（狀態） | 條文 | 與新定位或 prompt 的關係 | 處理 |
|---|---|---|---|
| 0002（accepted） | L35「建議引擎必須是 YAML 規則式…不得用黑箱模型直接產生建議動作」；L36「ML 層只輸出機率與區間並經校準，不輸出價格點位」 | 不衝突，本 ADR 沿用 | 不修訂 |
| 0002 | L12「非自動下單系統、非預言機」 | 仍然成立（不自動下單、不承諾準確率） | 不修訂 |
| 0004（accepted） | §4 無目標價（L107-110） | 衝突：prompt 要求分批停利、壓力等向上價位 | **部分修訂**：縮窄為 D-5.1 的禁令 |
| 0004 | 卡片 `disclaimer`（L205）、Decision §5 定位理由（L66-70） | 衝突：字面不再為真 | **部分修訂**：字面交風控重訂（D-11） |
| 0004 | 約束 1～3、5（action 列舉、禁用詞、反駁點與失效條件、版本化） | 不衝突，並延伸套用到 outlook 規則 | 維持 |
| 0018（proposed） | D-3 `FIXED_STOP_RATIO=0.92`、`COST_TARGET_RATIO=1.2`、2R；CEO 待決 #1、#2 | 衝突：固定百分比包裝成系統價位（prompt L76） | **取代**；計算歸屬與守門精神由 D-5 吸收 |
| 0018 | K-3：`app.advice.*` 不得 import `app.keylevels` | 不衝突，本 ADR 沿用（由 `app/plan` 負責組合） | 沿用 |
| 0012（accepted） | C-15：forward return 等識別字只能出現在 `basket.py`、`sector_eval.py`、`app/research/**`〔事實：`docs/adr/0012-…:800`〕 | 衝突：預測計分需要計算 forward return | **部分修訂**：白名單加 `app/forecast/scoring.py` |
| 0012 | L401：board「不產生、不儲存任何分數…不帶任何規則引擎輸出」〔事實〕 | 不衝突的前提是族群展望另存，不放進 board | 維持；約束 AV-12 |
| 0012 | L678：納入上櫃須升 `method_version`〔事實〕 | 相關：記憶體等族群在上櫃 | 維持；在 Phase 3／4 處理 |
| 0014（proposed） | D-11：盤中價只用於持倉估值顯示〔事實：`docs/adr/0014-…:239-241`〕 | 不衝突，本 ADR 重申所有判斷只用日線收盤 | 不修訂 |
| 0020（proposed） | 觀察窗單一來源（540） | 新模組沿用同一個常數 | 不修訂 |
| 0021（proposed） | 規則欄位可評估子集 | outlook 規則套用同一個不變式 | 不修訂 |
| 0022／0023（proposed） | 風險上限判定 | `app/plan` 重用 `evaluate_limits`／`project_position`，不另立判定 | 不修訂 |
| 0010（proposed） | 整書 0 網路 IO | 大盤、族群展望改由排程預算後持久化，API 只讀 | 不修訂 |
| 0003、0005、0006、0008、0009、0011、0015、0016、0017、0019、0024 | 資料層、Kelly、事件研究、匯率、持倉寫入 | 無衝突 | 不修訂 |

### 5. 非 ADR 的既有裁示衝突（本 ADR 不裁決，列給風控重訂）
- phase8 風控定調 §1.3 禁用清單：支撐位、壓力位、停利價、進場價、攤平、勝率等〔事實：`work/stock-desk-phase8-風控定調.md:42-54`〕。
- 同檔 §4 C5「向上價位一律否決」、C6「候選模式不輸出價位」、C8「價位欄位 allowlist 長度為 1」〔事實：同檔 `:93-96`〕。
- 七則初審 PX-1（LLM）、PX-3（跨標的篩選或排序）、PX-4（價位行動點）、PX-5（行動三選一）、PX-7／PX-13（消息面）、PX-12（支撐壓力用語）、PX-25（主題化歸類）〔事實：`work/reviews/2026-10-13-外部交易提示詞七則-風控初審.md:35-41,57,62,88`〕。
- 族群動能 PRD「不做自訂概念股分組」、派工單「題材」VETO〔盤點所引〕。
- 依 CEO 決策紀錄第 34 行：風控不再就「要不要提供建議」行使否決，但對內容仍有否決權。

### 6. 可重用的既有資產（事實）
- 規則引擎：缺欄位時跳過（skip）而不判為不成立、方向分組加總、保守閘門、反駁點與失效條件〔`engine.py:146-185,301-410`〕。
- 指標：MA5／20／60、RSI14、MACD、布林、ATR14（Wilder）、KD、量 z 分數〔`signals/technical.py:12-14,43-55`〕。
- 回測引擎：結構性 point-in-time，第 t 日只拿得到 `iloc[:t+1]`〔`backtest/engine.py:3-18`〕。事件研究：Wilson 區間與不重疊子樣本〔`backtest/event_study.py:29-39`〕。
- 費稅模型（`verified_on=None`，滑價 0）〔`backtest/costs.py:47-55`〕。
- 除權息還原只用於量測〔`dividends/adjust.py:5-18`〕。
- 族群 board 與 append-only 統計表〔`sectors/store.py:98-252`〕。
- 風險預算：`atr_stop_multiple`、`max_loss_per_trade`〔`advice/limits.py:556-559`〕。

### 7. 現況缺口
- 沒有任何 3／5 日展望或預測紀錄〔盤點所引〕。
- add 規則沒有量能條件〔事實：`default.yaml:37-86`〕。
- 系統沒有現金資料〔事實：`advice/book.py:14-17,127-130`〕。
- 前端 ATR 用簡單平均，後端指標用 Wilder，兩者不一致〔事實：`keyLevels.ts:38,125-133` 對照 `technical.py:12-14`〕。
- 族群只有上市官方大類〔盤點所引：`sectors/definition.py:173`〕；沒有基本面、消息面資料源〔盤點所引〕。

---

## Options（選項比較）

**A. 總體作法**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A1 規則式擴充：新增 outlook／levels v2／plan／forecast 四層，`build_advice` 不動（採用）** | 可解釋、進 git、可重算；沿用既有閘門與測試；符合 ADR-0002／0004 | 規則撰寫與參數登記要花人力；效能上限受限於規則 | 規則過度保守，長期被判「未優於基準」 |
| A2 統計模型（有序 logit、梯度提升樹）輸出方向與機率 | 可能更準；可輸出機率 | 沒有上線紀錄可校準；容易過擬合；ADR-0004 拒絕 | 「有效 AI」的假象 |
| A3 LLM 分析師（讀資料後產出敘事與建議） | 開發快、文字自然 | 無法重算、無法 point-in-time 稽核；容易編造（違反 prompt L15）；有 Token 成本；有隱私疑慮 | 編造的價位與消息 |
| A4 維持研究定位（現狀） | 零改動 | 違反 CEO 決策 | — |

**B. 方向判斷方法**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **B1 YAML 規則投票，加上明確的「震盪」帶與「證據不足」閘門（採用）** | 與 advice 同一套語意；每條規則都附依據與失效條件 | 門檻屬人工 | 參數若在看過結果後才調整，就是擬合 |
| B2 條件頻率表（以歷史上同狀態後 h 日的分布決定標籤） | 有統計依據 | 狀態一多樣本就太稀；仍需人工定義狀態 | 降級為 B1 的證據欄位使用 |
| B3 校準機率模型 | 可輸出機率 | 需要大量上線樣本 | 延後到 Phase 5 另立 ADR |

**C. 持股行動與既有 action 的關係**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| C1 改寫 engine `action` 列舉 | 只有一套詞彙 | 會破壞警示（共用 `COMPARISON_OPS`）、Kelly、前端與大量測試 | 回歸面太大 |
| **C2 `app/plan` 以宣告式政策表，從 engine 輸出＋展望＋價位＋上限＋預算推出 `position_action`（採用）** | engine 不動；政策表可版本化、可審 | 多一層 | 兩層語意要在卡片上同時揭露 |
| C3 另寫一套獨立的行動引擎 | 自由度高 | 同一畫面出現兩個聲音 | 自相矛盾 |

**D. 價位依據**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| D1 固定比率（現況：0.92、1.2、±3%） | 簡單 | 違反 prompt L76；與標的的結構無關 | — |
| D2 只用 ATR 倍數 | 會隨波動調整 | 沒有結構意義；仍是任意倍數 | 被讀成任意數字 |
| **D3 結構樞紐（擺動高低、前高前低、缺口、均線）聚成價位區，加上 ATR 緩衝，並附觸價次數與量能（採用）** | 每個價位都能回指到 K 棒；符合「反覆受阻」等證據要求 | 樞紐要等 k 根後才確認（point-in-time 延遲）；參數較多 | 參數須事先登記 |
| D4 量價分布（volume profile） | 能看出成交密集區 | 只有日線時誤差大 | 延後；若做要標示為近似 |

**E. 預測紀錄的儲存位置**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **E1 主 DB 的 `forecast_*` 表，以 trigger 禁止 UPDATE／DELETE（採用）** | 與持倉同一份備份、還原與匯出（Phase 2） | 主 DB 變大（量級小） | 遷移須遵守 Phase 2 的版本化規則 |
| E2 獨立的 `forecast.db`（比照 ADR-0012 市場 DB） | 隔離 | 備份與還原要處理兩個檔 | 只還原一邊會造成紀錄不一致 |

**F. 族群分類的來源**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **F1 主族群取官方產業別；細項與題材由人工策展，每筆附證據來源與日期（採用）** | 有依據、point-in-time 可追溯 | 要人力；初期覆蓋低 | 覆蓋不足必須揭露 |
| F2 由 LLM 從公司描述自動分類 | 覆蓋快 | 無法重算；會把供應鏈參與誤判為主業（違反 prompt L48） | 編造 |
| F3 只用第三方的概念股清單 | 現成 | 授權不明；依據不明 | 合規風險 |

**G. LLM**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **G1 不引入（採用，預設）** | 可重算、零 Token 成本、零外送 | 消息面與法說比較只能列示或人工整理 | 消息面功能受限 |
| G2 只用於公開文本的結構化（去重、摘要、欄位抽取），不參與方向、價位、動作 | 可擴大消息面覆蓋 | 有 Token 成本；仍有編造風險；需要新 ADR、CEO 授權付費、風控審查 | 摘要失真 |

---

## Decision（決策）

### D-1 總體架構與模組邊界

依賴方向只能由上往下。

```
api/advice.py ──(同一快照)──> plan ──> outlook(讀持久化紀錄)、keylevels、advice.engine 輸出、advice.limits、backtest.costs
scheduler ──> outlook.engine ──> outlook.features ──> signals、sectors(公開 API)、data(load_bars／index)
scheduler ──> forecast.recorder ──> forecast.store
scheduler ──> forecast.scoring ──> data(load_bars)、dividends.adjust
taxonomy(store＋models) <── outlook.features（只讀）
```

- `app/outlook/`、`app/keylevels/`、`app/plan/`：純函式，不做 IO、不讀時鐘（時間以參數注入）、不讀環境變數。
- `app/forecast/`：`store.py`（append-only）、`recorder.py`、`scoring.py`。
- `app/taxonomy/`：`models.py`、`store.py`。
- `/api/advice` 在 `AdviceResponse` 新增同層欄位 `key_levels`、`outlook`、`plan`（比照 ADR-0018 D-2 的作法）。`advice` 卡片本身維持 `build_advice` 的原樣輸出。
- 新端點只讀已持久化的計算結果：`GET /api/outlook/market`、`GET /api/outlook/sectors`、`GET /api/sectors/{code}/members?sort=turnover&page=`（Phase 4）。

### D-2 方向判斷（outlook）

1. **範圍**：`scope ∈ {market, sector_main, sector_sub, theme, symbol}`；`horizon ∈ {3, 5}`（交易日）。
2. **輸入**：
   - 只用日線收盤序列，以及由日線導出的量。
   - 大盤：加權指數日線（ADR-0005 路徑，恆標 `backup`），加上 ADR-0012 市場 DB 算出的廣度（上市）。
   - 族群：ADR-0012 的 `calculation_set` 成員，或 taxonomy 成員（D-7）的等權彙總。
   - 個股：本標的日線，以及由日線重取樣的週線。
   - 盤中價不得作為輸入（ADR-0014 D-11）。
3. **方法**：
   - `app/outlook/rules/h3.yaml` 與 `h5.yaml` 兩份規則檔，schema 比照 `app/advice/loader.py`：`extra="forbid"`、`version` semver、`BANNED_PHRASES` 掃描、欄位必須在可評估子集內（ADR-0021）。
   - 每條規則宣告 `direction ∈ {bullish, bearish, range}`、`weight`、`explanation`、`counterargument`、`invalidation`（機器可檢查的運算式）。
   - 判定順序：
     - (a) 可評估規則占比 < `MIN_COMPLETENESS`，標為 `insufficient`。
     - (b) 否則計算淨權重 `W_bull − W_bear`；其絕對值 < θ_h，標為 `range`；並記下 `range_basis ∈ {range_evidence, conflicting_evidence}`（有 range 規則命中時為前者）。
     - (c) 其餘依正負號標為 `bullish` 或 `bearish`。
   - θ_h 與 `MIN_COMPLETENESS` 由 quant 事先登記；兩個 horizon 各自一組。
4. **3 日與 5 日分開**：各自的規則檔、特徵窗、門檻、結果定義（D-6.3）與統計。兩者結論可以不同，畫面照列，不調和。
5. **條件頻率（Options B2）只作證據**：「歷史上同一規則狀態之後 h 日的分布（n、中位數、Wilson 區間）」以 `Evidence(kind="inference")` 附上，不參與決定標籤。
6. **不輸出機率**：機率要等 Phase 5 另立 ADR 並經校準。在那之前，回應中不得出現機率、勝率、「機會」等數值或字樣（字面由風控定）。

### D-3 證據與失效條件的資料結構（規範性；欄位名變更須經 tech-architect 覆核）

```python
class Evidence(BaseModel):            # frozen
    id: str
    kind: Literal["fact", "inference", "unconfirmed"]
    rule_id: str | None
    field: str                         # vocabulary key, e.g. "ma20.slope_5"
    value: Decimal | None
    unit: str
    window: str                        # e.g. "60 bars to 2026-10-14"
    as_of: date
    source: str                        # data source id (twse/tpex/finmind/yfinance+backup ...)
    formula_ref: str                   # key into server-side formula text table
    stance: Literal["supports", "opposes", "neutral"]

class Invalidation(BaseModel):         # frozen
    id: str
    rule_id: str | None
    expr: str                          # machine-checkable: "<field> <op> <value|level_ref>"
    level_ref: str | None              # PlanLevel.kind when bound to a price
    valid_until_session: date          # t + h trading days
    status: Literal["armed", "triggered", "expired", "uncheckable"]

class OutlookJudgment(BaseModel):      # frozen
    scope_kind: Literal["market", "sector_main", "sector_sub", "theme", "symbol"]
    scope_key: str
    horizon: Literal[3, 5]
    label: Literal["bullish", "range", "bearish", "insufficient"]
    range_basis: Literal["range_evidence", "conflicting_evidence"] | None
    evidence: tuple[Evidence, ...]
    counter_evidence: tuple[Evidence, ...]
    invalidations: tuple[Invalidation, ...]   # non-empty unless label == "insufficient"
    missing_inputs: tuple[str, ...]           # what is lacking, stated (prompt L15)
    coverage: Coverage                        # members used / expected, sampling rule, market scope
    data_as_of: date; valid_until_session: date
    method_version: str; rules_version: str
    validation: ValidationRef                 # D-6.5
    forecast_id: str | None                   # ledger row this judgment was recorded as
```

- `kind="fact"`：可由資料直接重算的量測。`inference`：規則或統計推出的判讀。`unconfirmed`：來源尚未查證或資料不完整。後端決定類別，前端只能照欄位渲染（prompt L54）。
- `Coverage` 必含：`members_used`、`members_expected`、`sampling_rule`（例：「全成員」或「依成交金額前 N」）、`market_scope`（例：「僅上市」）、`index_source_status`（ADR-0005 的 `backup`）。

### D-4 持股行動（plan）與既有 action 的映射

1. **engine 不動**：`CardAction` 仍為 6 值〔事實：`engine.py:56`〕，警示與 Kelly 照舊。
2. **政策表**：新增 `app/plan/policy.yaml`（有 `policy_version`）。`position_action` 依模式取值：
   - 持有模式（`held is True`）：`hold`（持有）、`wait`（等待）、`reduce`（減碼）、`add_conditional`（符合條件後加碼）、`insufficient`。
   - 候選模式（`held is False`）：`consider`（可考慮）、`wait`（等待）、`avoid`（避免）、`insufficient`。
   - 持有狀態不明（`held is None`）：一律 `insufficient`，並附原因。
3. **持有模式的預設判定順序（v0 草案；內容由 quant 提、風控審，結構由本 ADR 固定）**：

| 序 | 條件 | `position_action` | `reason` | 對應的既有 engine action |
|---|---|---|---|---|
| 1 | engine `insufficient_data`，或必要價位不可得 | `insufficient` | `missing_inputs` | insufficient_data |
| 2 | 收盤 < 失效價（`invalidation` 的 `relation=crossed`） | `reduce` | `invalidation_hit` | 涵蓋 stop_loss |
| 3 | engine action ∈ {stop_loss, reduce} | `reduce` | `defensive_rules` | stop_loss、reduce |
| 4 | engine action = take_profit，或收盤 ≥ 第 1 階分批停利且該階尚未處理 | `reduce` | `take_profit_tier` | take_profit |
| 5 | engine action = add，且 `add_conditions` 全部 `met` | `add_conditional`（`conditions_met=true`） | `add_conditions_met` | add |
| 6 | engine action = add，但有任一加碼條件 `unmet` 或 `unavailable` | `wait` | `pending_add_conditions` | add（降級） |
| 7 | 5 日展望 = bearish，或收盤距失效價 ≤ x×ATR | `wait` | `watch_invalidation` | hold |
| 8 | 其他 | `hold` | `thesis_intact` | hold |

4. **加碼條件（`add_conditions`，四類缺一不可，每條三態）**：
   - 價格：突破並收在壓力區上緣之上，或回測支撐區不破（依據來自 D-5）。
   - 量能：成交量與 20 日中位數的比值在事先登記的區間內。量能條件只能當門檻，不得單獨構成理由（prompt L59）。
   - 趨勢：收盤 > MA60，且 5 日展望 ≠ bearish。
   - 預算：加碼後 `project_position` 的五條上限都不是 violated；以新失效價計算的單筆風險 ≤ `max_loss_per_trade`；加碼金額（含費稅）≤ 自報的可用現金。可用現金不明時，此條為 `unavailable`。
   - **禁止攤平**：任何讓 `add_conditional` 成立的路徑，都不得只靠「價格低於成本」或「回撤加深」。loader 守門：方向為 add 的規則，條件樹必須至少含一個趨勢類欄位（白名單）。
5. **候選模式**：
   - `consider` 必須全部滿足：收盤在進場觀察區內、趨勢與量能條件成立、5 日展望 ≠ bearish、可建倉股數 > 0。
   - 任一防禦條件成立就判 `avoid`：結構失效，或 5 日展望 = bearish。
   - 其餘為 `wait`，並列出待觸發條件。
   - 依風控 RED-1〔事實：`entryObservation.ts:111-116`〕，候選模式不得把「未命中防禦規則」當成正面證據。
6. **風險數字分欄**：`risk_from_close`（每股、金額、占總資產比、是否含費稅、`cost_model_verified_on`）與 `pnl_vs_cost`（相對成本的損益）是兩個獨立物件，不得合併（prompt L78）。
7. **`execution_caveats`**：只要畫面出現失效價或停損類價位，就必附跳空、跌停、流動性不足時無法成交的揭露 id（prompt L80）。
8. **股數**：沿用 `suggest_quantity_range`。可用現金是新增的使用者自報欄位，比照 `SelfReportedNetWorth`：記錄輸入時間，過期就不再使用〔事實：`limits.py:592` 的類別〕。

```python
class PositionPlan(BaseModel):         # frozen
    mode: Literal["held", "candidate", "unknown"]
    position_action: Literal["hold", "wait", "reduce", "add_conditional",
                             "consider", "avoid", "insufficient"]
    reasons: tuple[str, ...]
    pending_triggers: tuple[Condition, ...]
    add_conditions: tuple[Condition, ...]        # held only
    entry_conditions: tuple[Condition, ...]      # candidate only
    levels: tuple[PlanLevel, ...]
    risk_from_close: RiskFromClose | None
    pnl_vs_cost: PnlVsCost | None                # held only
    quantity_range: dict | None                  # from suggest_quantity_range
    execution_caveats: tuple[str, ...]
    engine_ref: EngineRef                        # rules_version, action, aggregated_action
    outlook_refs: dict[Literal["h3", "h5"], str | None]   # forecast_id
    formula_version: str; policy_version: str; data_as_of: date

class Condition(BaseModel):
    id: str
    category: Literal["price", "volume", "trend", "budget", "outlook", "risk_cap"]
    status: Literal["met", "unmet", "unavailable"]
    observed: Decimal | None; threshold: Decimal | None
    basis: str                                   # formula_ref
```

### D-5 價位計算（levels v2，後端化）

1. **ADR-0004 §4 修訂內容**：
   - 系統不得輸出點位預測：「將到達 X」「目標價」「合理價」「fair_value」「上看」。
   - 系統不得輸出估值價。
   - 可以輸出「條件價位」：語意必須是「若價格在 X 的哪一側收盤，則觸發 Y」。每個價位都要有依據，並附失效條件。
   - 向上的分批停利價位屬於條件價位。用語由風控定。
2. **計算歸屬**：`app/keylevels/` 是唯一實作（沿用 ADR-0018 D-1 的精神）。前端不計算任何價位、距離、狀態或門檻（沿用 ADR-0018 K-8、K-11、K-15）。
3. **依據種類（`basis_kind`）**：

| `basis_kind` | 定義（參數由 quant 事先登記） | point-in-time 注意 |
|---|---|---|
| `swing_high` / `swing_low` | 樞紐：該根高（低）點高於（低於）左右各 k 根 | 第 i 根要到 i+k 才確認，第 t 日只能使用 i ≤ t−k 的樞紐 |
| `prior_high_n` / `prior_low_n` | 近 n 根最高（最低），n ∈ 事先登記的集合（例：20、60、252） | — |
| `zone_cluster` | 多個樞紐或前高前低在 ±c×ATR 內聚成一個區，附觸價次數 `touch_count` 與觸價日 | 觸價次數就是「反覆受阻」的證據 |
| `gap_edge` | 未回補缺口的上下緣 | — |
| `moving_average` | MA20／MA60（與 signals 同一個定義） | — |
| `weekly_swing` | 由日線重取樣的週線樞紐 | 當週尚未收完的週 K 標為 `partial`，不得當作確認樞紐 |
| `atr_buffer` | 結構價位再減（或加）m×ATR14。ATR 採 Wilder，與 `signals/technical.py` 同源 | 只用第 t 日的 ATR |
| `trailing_peak_atr` | 持有以來最高收盤 P 減 m×ATR（承接 ADR-0018 D-4 的概念，但不設 0.92P 下限） | 沿用 ADR-0018 D-5 的持有窗與 fail-closed |
| `user_risk_budget` | 由使用者設定換算：`atr_stop_multiple`、`max_loss_per_trade`、playbook 參數 | 必須引用設定名稱與值；這是使用者的參數，不是系統的分析 |
| `cost_anchor` | 平均成本（只作為相對成本損益的基準，本身不是行動價位） | — |

   - **`fixed_ratio` 不在列舉中。** 系統價位的依據不得是固定百分比。
4. **價位種類（`PlanLevel.kind`）與最低依據要求**：
   - `support` / `resistance`：至少一個 `zone_cluster`，或 `prior_*`。
   - `entry_zone_low` / `entry_zone_high`（進場觀察區）：取最近一個支撐區的上下緣。若條件不成立（例如結構已破壞），回 null，並附原因。
   - `invalidation`（失效價）：論點所依賴的那個支撐區下緣，再減 `atr_buffer`。持有模式另外並列 `risk_budget_stop`（`user_risk_budget`），兩者都顯示，不取最大值後只顯示一個。
   - `take_profit_tier`（分批停利 1..n）：依序取上方的壓力區。上方沒有歷史壓力時（例如創 252 日新高），才改用 `atr_buffer` 的擴展階，並明寫「上方無歷史壓力參考」。
   - `trailing`（移動停利）：只在持有模式、且持有窗可得時輸出。
5. **資料契約**：

```python
class LevelBasis(BaseModel):
    basis_kind: Literal["swing_high", "swing_low", "prior_high_n", "prior_low_n",
                        "zone_cluster", "gap_edge", "moving_average", "weekly_swing",
                        "atr_buffer", "trailing_peak_atr", "user_risk_budget", "cost_anchor"]
    params: dict[str, str]                 # decimal strings
    touches: tuple[tuple[date, Decimal], ...]
    touch_count: int | None
    bar_range: tuple[date, date]
    formula_ref: str

class PlanLevel(BaseModel):
    kind: Literal["support", "resistance", "entry_zone_low", "entry_zone_high",
                  "invalidation", "risk_budget_stop", "take_profit_tier", "trailing"]
    tier: int | None
    price: Decimal
    bases: tuple[LevelBasis, ...]          # len >= 1
    relation: Literal["above_close", "below_close", "crossed"]
    distance_from_close_pct: Decimal
    spans_ex_date: bool                    # raw-close level formed across an ex-date
```

6. **不執行 ADR-0018 的「舊公式搬遷＋golden parity」**：理由是舊的 0.92／1.2／2R 會被 levels v2 整組取代，先搬再換等於做兩次工。現行前端面板（含 ADR-0018 案 A，commit `66ed876`〔ADR-0018 所述〕）維持原狀，到 Phase 4 一次切換。回測 `five_conditions` 的 ×1.2 屬於策略參數，`FIVE_CONDITIONS_NOTE` 不動，也不得出現在 plan 價位中。
7. **價格口徑**：價位用未還原收盤（與估值同口徑，`dividends/adjust.py:12-18`）。價位所依據的區間如果跨過除權息日，`spans_ex_date=true`，並在依據中揭露。

### D-6 預測紀錄與事後檢驗

1. **資料表**（主 DB，Options E1；全部以 trigger 禁止 UPDATE／DELETE，例外只有 `forecast_outcome` 的「NULL 變成值」一次性寫入，比照 ADR-0012 C-21）：
   - `forecast_run(run_id, trigger ∈ {scheduled, on_demand}, data_as_of, method_version, rules_version, policy_version, formula_version, code_commit, input_digest, recorded_at)`
   - `forecast_record(forecast_id, run_id, scope_kind, scope_key, horizon, label, range_basis, base_close, band_def, evidence_json, invalidations_json, coverage_json, valid_until_session, supersedes, recorded_after_next_open)`
   - `plan_record(plan_id, run_id, symbol, market, mode, position_action, reasons_json, levels_json, conditions_json, quantity_json)`
     - 持倉成本與股數只存在本機 DB；任何對外請求都不得帶出（AV-9）。
   - `forecast_outcome(forecast_id, resolved_at, outcome_close, outcome_source, realized_return, realized_label, invalidation_first_hit, mae, mfe, status ∈ {resolved, unresolvable_missing_data, excluded_corporate_action})`
   - `plan_outcome(plan_id, horizon, levels_touched_json, first_touch_kind, status)`
2. **point-in-time 規則**：
   - 第 t 日的紀錄必須在 t+1 交易時段開盤（台北 09:00）之前寫入。否則 `recorded_after_next_open=1`，紀錄照存，但不計入上線統計。
   - 同一個 `(scope, horizon, data_as_of, method_version)` 只能有一筆。資料修正後要重算時，新增一筆並以 `supersedes` 指向舊筆，不得覆寫。
   - `input_digest` 為輸入 bars 的雜湊；計分時重算一次，不一致就標記。
3. **結果定義（每個 horizon 分開；參數由 quant 事先登記，看過結果後不得更改）**：
   - `r_h = adj_close[t+h] / adj_close[t] − 1`，採還原股價。
   - `b_h = k_h × σ20(t) × √h`，σ20 為第 t 日以前 20 日的日報酬標準差。
   - `r_h > b_h` 判為 bullish、`r_h < −b_h` 判為 bearish，其餘為 range。
   - 窗內有分割或減資：`excluded_corporate_action`。
   - 大盤用加權指數；族群用與 outlook 相同的等權成員集合。
4. **與回測的關係**：
   - 歷史回放：在歷史上逐日以 point-in-time 切片呼叫同一個 `outlook.engine`（共用程式，不另寫一份），產出「歷史回放報告」。
   - 上線紀錄：`forecast_*` 表。
   - 兩者分開報告，不得合併計數。
   - 回放報告遵守 backtest-protocol：分樣本內、樣本外；不得調參到好看；參數調整歷程要留紀錄。
   - 族群的存活者偏誤沿用 ADR-0012 的 PIT 機制，未達條件時標 `not_evaluated`。
   - 三類報告分開：方向回顧（本節）、交易策略績效（既有 `run_backtest`、F-11）、校準機率（Phase 5，另立 ADR）（prompt L95）。
5. **基準比較（`ValidationRef`）**：
   - 至少並列三個基準：
     - (a) 恆判 range。
     - (b) 氣候法：同期無條件的三態頻率。
     - (c) 延續法：以過去 h 日報酬的符號判斷。
   - 指標：三態命中率；非 range 判斷的方向命中率（附 Wilson 區間）；與最佳基準的差（以 block bootstrap 求區間，因為樣本重疊）。
   - `status`：
     - 樣本數 < N_MIN：`insufficient_sample`。
     - 差值區間涵蓋 0 或為負：`not_better_than_baseline`。
     - 其餘：`better_than_baseline`。
   - 回應永遠附 n 與期間，數字照列不隱藏。
   - N_MIN 由 quant 登記，並說明不重疊樣本的換算方式（prompt L94：30 筆不得視為已證明有效）。
6. **顯示閘門**：
   - 一個 scope 與 horizon 的判斷要上畫面，前提是該組合的歷史回放報告已產出，並經 quant 與 qa 審查。不論結果好壞都照實呈現。
   - 是否加上「上線影子試跑 N 個交易日」，列為 CEO 待決 #3。

### D-7 族群三層分類與題材

1. **資料模型**（主 DB）：
   - `taxonomy_node(node_id, layer ∈ {main, sub, theme}, parent_id, name, definition, taxonomy_version)`
     - `main` 對應官方產業別；`sub` 的 parent 必為某個 `main`；`theme` 跨產業，沒有 parent。
   - `taxonomy_membership(symbol, market, node_id, role ∈ {primary_business, revenue_segment, supply_chain_participant}, revenue_share, evidence_kind ∈ {official_industry_code, company_business_description, revenue_breakdown, company_ir_document, official_value_chain_listing, curated_note}, evidence_ref, evidence_date, effective_from, effective_to, recorded_at, curator)`
2. **規則**：
   - `main` 只來自官方產業別：上市取 `t187ap03_L`；上櫃待資料源查證。
   - `sub` 要求 `role ∈ {primary_business, revenue_segment}`。
   - `role=supply_chain_participant` 只能掛在 `theme`，不得推出 `main` 或 `sub`（prompt L48）。
   - 每筆歸屬都必須有 `evidence_ref` 與 `evidence_date`，沒有就不得寫入。
3. **point-in-time**：回放與上線計算一律以 `effective_from ≤ t` 且 `recorded_at ≤ t 收盤` 為準。在任何生效日之前回填的歸屬，標為 `backfilled`，不計入上線統計（比照 ADR-0012 的 `backfill_non_pit`）。
4. **細分範圍（先做的範圍由 PM 排序）**：
   - 金融：銀行、壽險、產險、證券、金控。
   - 營建：建設開發、營造工程、建材。
   - 醫療：新藥、學名藥、原料藥、CDMO、生物製劑、細胞治療、診斷、醫材、通路、照護（prompt L47）。
   - 細項名單由 PM 與 CEO 定；本 ADR 只固定模型。
5. **與 ADR-0012 的界線**：
   - `sector_board` schema 不變；族群展望不寫進 board（L401）。
   - `app.sectors` 的 C-1 白名單不變；由 `app/outlook` 單向讀 `app.sectors` 的公開 API。
   - 納入上櫃要升 `method_version`（L678）。

### D-8 天氣比喻

1. **兩個不同型別，不得互換**：`CurrentWeather`（目前盤勢，描述第 t 日已發生的狀態）與 `OutlookWeather`（第 t 日對 h 日的展望，由 `OutlookJudgment.label` 映射而來）。
2. **映射表**：放在後端 `app/outlook/weather_map.yaml`，有版本；前端只依列舉值取圖示。

| 物件 | 輸入 | 映射 |
|---|---|---|
| `CurrentWeather` | `trend_state ∈ {up, flat, down}`（指數相對 MA20／MA60 與 MA20 斜率）× `vol_regime ∈ {normal, high}`（20 日年化波動，定義沿用 playbook 快市的口徑，但程式要移到 `app/signals`，見 AV-11） | up/normal：晴；flat/normal：多雲；down/normal：陰雨；任一 trend 遇 high：加註雷雨（高波動）。門檻由 quant 登記 |
| `OutlookWeather` | `label` | bullish：晴；range：多雲；bearish：雨；insufficient：「不預報」（霧，或灰色無圖示） |

3. **每個天氣物件必附**：`data_as_of`、`basis`（Evidence id 清單）、`coverage`（例：僅上市、指數來源 `backup`）、`valid_until_session`（只有展望有）。
4. **禁止降雨機率式的數字**：不得出現「降雨機率 N%」或任何類似比喻的數值，直到 Phase 5 的校準 ADR（D-2.6）。

### D-9 消息面、基本面、盤中價：資料源需求（只列需求與候選，不決定採購；不得新增付費服務）

| 需求 | 用途 | 候選（全部未查證；由 data-engineer 依 `data-source-integration` 查證端點、授權、額度、point-in-time 時間欄位） | 期別 |
|---|---|---|---|
| 官方加權指數日線 OHLC | 大盤展望、天氣 | TWSE 官方指數資料；現行 yfinance `^TWII` 為 backup〔ADR-0021 所述 `services/index.py`〕 | Phase 1 |
| 官方休市日 | 區分休市與盤後、計算 `valid_until_session` | TWSE 年度休市日公告 | Phase 1 |
| 分割、減資等公司行動 | 還原與排除 | TWSE／TPEx 公告；既有族群動能的公司行動保險 | Phase 1 |
| 費率、稅率查證 | `risk_from_close` 含費稅 | 主管機關與交易所公開資料（填 `CostModel.verified_on`） | Phase 1 |
| 上櫃產業別與全市場日線 | 族群主層含上櫃 | TPEx OpenAPI（ADR-0012 DE-4 記載上櫃產業別無來源，需重查） | Phase 3 |
| 公司業務描述、營收結構 | 細項與題材的證據 | 公開資訊觀測站（MOPS）公司基本資料、年報；TWSE 產業價值鏈資訊平台（授權與可機讀性未查證） | Phase 3／4（人工策展） |
| 月營收、季財報（單季／累計、實際值、發布時間） | 基本面 | MOPS／TWSE OpenAPI；FinMind 免費層 dataset（額度未查證） | Phase 5 |
| 產業專用指標（金融、營建、新藥） | 基本面 | 可機讀的免費來源多半不存在〔推論〕；沒有就顯示「資料不足」 | Phase 5 |
| 官方重大訊息、法說會資料 | 消息面（來源、發布時間、事件時間） | MOPS 重大訊息、法說會資訊；只列示，不解讀，直到風控重訂 PX-13 | Phase 5 |
| 第三方新聞 | 消息面 | RSS 等（授權不明，預設不採） | Phase 5 以後 |
| 盤中價 | 盤中估值 | ADR-0014 MIS（非公開文件介面，CEO 已接受風險；待 10/05 實測結果） | 依 ADR-0014 |
| 三大法人、融資融券 | 籌碼證據 | TWSE OpenAPI（未查證）；不得把法人買超解讀為主力（prompt L58） | Phase 5 |
| 可用現金 | 加碼預算條件 | 使用者自報（新欄位，比照自報淨值） | Phase 2 |

- 任何需要付費才能取得的來源：升級 CEO 決定（ADR-0003 約束 11(c)）。沒有資料源時顯示「資料不足」，不得以 LLM 或記憶補值。
- 「消息是否已反映」只能這樣呈現：事件日相對大盤的超額報酬（`fact`），加上標為 `inference` 的判讀；不得把推測當事實（prompt L71）。

### D-10 LLM

1. **預設不引入**：方向標籤、價位、行動、天氣、分類，一律不得由 LLM 產生。`pyproject.toml` 不得加入 LLM SDK（AV-10）。
2. **若日後引入，只限 Options G2 的範圍**：公開文本（重大訊息、法說內容）的去重、摘要與欄位抽取，輸出成 `Evidence(kind="unconfirmed")`，必須附原文引句與來源連結。須另立 ADR、CEO 書面授權付費、風控全新審查（PX-1）。
3. **資料流**：只送公開文本；持股代號、成本、股數、占比一律不送（prompt L42）。
4. **Token 成本估算式**（單價由 devops-sre 查證當時的官方價格，不憑記憶）：
   - 每週 Token ≈ Σ(標的) 文件數 × (平均輸入 Token ＋ 平均輸出 Token)。
   - 量級示例〔推論，假設值〕：30 檔 × 每週 5 份 × (1,500＋200) ≈ 25.5 萬 Token／週。
   - 成本＝Token 數 × 查證後的單價。

### D-11 字面治理與過渡

1. ADR 核可前，現行程式與使用者面字面一律不變（CEO 決策紀錄第 36 行）。
2. 核可後，由 creative-lead 盤點所有宣稱「研究與教育用途、非投資建議、不產生目標價、非預測模型」的字面，含 `engine.py:60`、`layout.tsx:20`、產品說明、README、`adviceWording.ts` 的 §3 相關句〔盤點所引〕。全部送風控逐字審，與新功能同一批出貨，不得先行。
3. 風控持有的守門測試（禁用詞清單 `shared/forbidden-terms.json`、價位 allowlist 長度 1、前端 `FRONTEND_FORBIDDEN_TERMS`），只能在引用新風控裁示編號的 PR 中修改（AV-14）。

### D-12 分期

依外部 prompt L119 的排序：資料正確性 → 庫存安全 → 分析可靠性 → 日常操作 → 擴充。Phase 2 與 Phase 3 的設計工作可以並行，但出貨順序固定。

| 期 | 前提 | 交付 | 驗收條件（逐條可檢查） | 新資料源 |
|---|---|---|---|---|
| **Phase 0 治理（無程式）** | CEO 決策紀錄 | ADR-0025 accepted；ADR-0004、ADR-0012 修訂指標；ADR-0018 標為 superseded；風控新護欄文件；PM 新 PRD；quant 事先登記文件（D-2.3、D-5.3、D-6.3、D-6.5、D-8 的所有參數）；art-lead 視覺規範（海軍藍、薄荷綠、氣象）；creative-lead 字面遷移清單 | 上述文件全部在 `work/` 或 `docs/adr/`，CEO 書面核可；quant 文件的 commit 早於 Phase 3 任何回放執行（以 git 時間佐證） | 無 |
| **Phase 1 資料正確性** | Phase 0（F-9b2／F-9c 不受此限，照原計畫） | F-9b2、F-9c；全部缺價時總額顯示「—」（`Totals` 可為 null，盤點 B4）；官方指數來源；休市日；公司行動偵測；費率查證（`verified_on`）；收盤、盤後、休市、前收參考估值的狀態標籤（不依賴 MIS） | `no_data` 時 API 總額為 null，前端顯示「—」（測試）；費率 `verified_on` 不為 None；休市日標籤有官方來源 fixture 與契約測試；`index_source_status` 正確浮上 | 指數、休市日、公司行動、費率 |
| **Phase 2 庫存安全** | Phase 1 的缺價修正 | 軟刪除、復原、修改歷史（append-only `position_events`）；應用程式內匯出；匯入預覽、合併、取代，取代前建立還原點；schema 版本（`PRAGMA user_version`）與遷移前自動備份；DB 絕對路徑守門；可用現金自報欄位；對外送出資料的說明。**建議另立 ADR-0026（庫存版本化與還原點）**，因為軟刪除語意會跨估值、警示、advice、playbook | 任一遷移前後所有持倉列逐欄相等（測試）；還原點往返位元組相同；匯入未確認前零寫入；已刪除持倉不出現在任何估值路徑（測試）；qa-e2e 實機驗收 | 無（可用現金為使用者自報） |
| **Phase 3 分析可靠性** | Phase 1；Phase 0 的 quant 登記；ADR-0012 C-15 修訂已核可 | `app/forecast`（表、recorder、scoring）**先於**任何顯示上線；`app/keylevels` levels v2；`app/outlook`（h3、h5；大盤、上市主族群、持倉與自選）；`app/plan` 與政策表 v0；排程 job（在 `sector_board_refresh` 之後）；歷史回放報告（含基準）；`app/taxonomy` 模型與主層 | 截斷不變性測試：第 t 之後補資料，不改變第 t 的判斷；兩個 horizon 獨立（AT-3）；每個 `PlanLevel` 至少一筆依據且沒有固定比率（AT-5）；上線紀錄連續 ≥ N 個交易日、`recorded_after_next_open=0`；回放報告經 quant＋qa（含 Codex 或 CEO 書面放行）審查 | 上櫃產業別（若做上櫃）；公司業務來源（人工） |
| **Phase 4 日常操作** | Phase 3 回放報告審查完畢；風控核可字面 | 市場總覽天氣（目前盤勢與 3／5 日分開）；持股行動計畫卡；「最需要處理」清單（排序規則以政策表固定）；族群精簡列表加詳細頁（全成員依成交金額排序，伺服端分頁）；細項（金融、營建、醫療）；已保存的分析進頁自動載入；狀態區分（尚未分析、分析中、來源失敗、資料過期、樣本不足）；前端關鍵價位面板與 `entryObservation` 觀察帶一次切換到後端值；視覺改版；自選股加上依 plan 價位的條件提醒（日線收盤） | qa-e2e 在 375 與 1280 寬度實機驗收；前端 grep 不得出現價位或門檻運算（AV-13）；五種狀態各有渲染測試；風控逐字核可的字面逐字釘住 | 無（盤中依 ADR-0014 另案） |
| **Phase 5 擴充** | Phase 4 穩定；各資料源查證完成 | 基本面（月營收優先）；官方重大訊息列示；法說變化（LLM 須另立 ADR）；組合相關性與歷史重演（F-12）；交易日誌（F-16）；檢查清單（F-13）；錯誤模式；校準機率（另立 ADR，前提是上線紀錄達 N_MIN） | 各自的 PRD 與 ADR | 見 D-9 |

---

## Consequences（後果）

**好處**
- 每個建議都能回溯到規則、公式與 K 棒；畫面與回放共用同一套程式，分叉從構造上消除。
- 預測紀錄讓「準不準」成為可檢驗的事實，而不是宣稱；未優於基準時，系統會自己說。
- 價位有結構依據，取代 0.92、1.2、±3% 這類固定比率；ADR-0018 #1、#2 不必再裁示。
- engine、警示、Kelly、回測、F-11 都不受影響。

**代價與壞處**
- 證據累積非常慢：h=5、每日一筆時樣本高度重疊，單一標的一年約只有 50 筆不重疊樣本〔推論〕。多數判斷會長期停在「證據不足」或「未優於基準」；這是誠實的結果，但使用者體感會是「建議很保守、很常說不知道」。
- 規則與參數都由人工事先登記；要調整就得升版本，舊的上線紀錄不能沿用到新版本，又要重新累積。
- 樞紐要等 k 根才確認，價位比肉眼看到的晚 k 天出現。
- 同一個標的會同時有三種聲音：engine action、`position_action`、playbook 指令。只能靠來源標示與衝突揭露處理，不會自動調和。
- 推翻風控既有裁示的範圍很大，Phase 4 能否出貨取決於風控新護欄。
- 族群細項與題材要靠人工策展，初期覆蓋低，必須揭露覆蓋率。
- 主 DB 會持續變大（append-only）；Phase 2 的備份與還原必須涵蓋 `forecast_*` 表。
- 價位用未還原收盤，除權息前後的價位可能失真，只能揭露（`spans_ex_date`）。
- 大盤指數來源在官方來源查證前一直是 `backup`，天氣會帶著這個標示。

**被此決策約束的事**：見「對實作的約束」。

---

## Alternatives considered（棄卻的方案）

1. **黑箱 ML 產生方向或動作（A2）**：沒有上線樣本可以校準，過擬合風險高，ADR-0004 拒絕。保留到 Phase 5，以「只輸出校準機率」的形式另立 ADR。
2. **LLM 分析師（A3）**：無法重算，有編造風險，與 prompt L15、L21-22 衝突，而且有隱私與成本問題。
3. **改寫 engine action 列舉（C1）**：回歸面太大，價值低。
4. **固定百分比或純 ATR 倍數的價位（D1、D2）**：違反 prompt L76。
5. **先把 ADR-0018 的舊公式搬到後端再換**：重工（D-5.6）。
6. **預測紀錄放獨立 DB（E2）**：備份與還原會分裂。
7. **由第三方概念股清單或 LLM 分類（F2、F3）**：沒有依據、授權不明。

---

## 對實作的約束（逐條可檢查）

- **AV-1** 所有判斷（outlook、levels、plan、天氣）只用日線收盤。`app/outlook`、`app/keylevels`、`app/plan`、`app/forecast` 不可達 `app.services.quotes`、`app.data.providers.twse_mis`（import graph，延伸 ADR-0014 I-6）。
- **AV-2** `app/outlook`、`app/keylevels`、`app/plan`、`app/taxonomy/models.py` 為純函式：不得 import `sqlite3`、`os`、`dotenv`、`httpx`／`requests`，也不得呼叫 `datetime.now`；時間一律由參數注入（grep 加 AST）。
- **AV-3** `app.advice.*` 不得 import `app.keylevels`、`app.outlook`、`app.plan`；advice 的 `KNOWN_FIELDS` 不得含價位或展望欄位（沿用 ADR-0018 K-3）。
- **AV-4** `build_advice` 的輸出鍵集合與既有測試斷言不變（沿用 ADR-0018 K-4）。
- **AV-5** 每個 `PlanLevel.bases` 長度 ≥ 1；`basis_kind` 列舉中沒有 `fixed_ratio`；`app/keylevels` 非測試檔中不得出現 `0.92`、`1.2`、`FIXED_STOP_RATIO`、`COST_TARGET_RATIO`（grep）。`user_risk_budget` 依據必須含設定名稱與值。
- **AV-6** 回應中不得出現 `target_price`、`price_target`、`fair_value`、`expected_price` 欄位名（OpenAPI schema 掃描）。
- **AV-7** `add_conditional` 成立時，四類條件（price、volume、trend、budget）都必須存在且為 `met`；收盤 < 失效價時不得是 `add_conditional`；add 方向的規則條件樹至少含一個趨勢類欄位（loader 守門加表格驅動測試）。
- **AV-8** h3 與 h5 各自一份規則檔、各自一組結果參數；不存在任何以一個 horizon 的標籤或特徵推出另一個 horizon 的程式路徑（測試：把 h5 規則檔換成空集合，h3 結果不變，反之亦然）。
- **AV-9** 持倉成本、股數、占比不得出現在任何對外 HTTP 請求中（以 HTTP client spy 測 scheduler 與 API 的完整一輪）。
- **AV-10** `pyproject.toml` 與 `package.json` 不得含 LLM SDK（`anthropic`、`openai`、`langchain` 等；CI grep），直到另一則 ADR 核可。
- **AV-11** `app/plan`、`app/outlook` 不得 import `app.playbook`；`app.playbook` 不得 import `app.plan`、`app.outlook`、`app.forecast`。playbook 用的快市波動與 M1 定義，如果要共用，就移到 `app/signals`（比照 `data/calendar.py` 的搬遷先例〔事實：`data/calendar.py:3-21`〕）。系統輸出不得寫入任何 playbook 表。
- **AV-12** `sector_board*` 各表的 schema 不變；`app.sectors` 的 C-1 白名單不變；族群展望只存在 `forecast_*` 表。
- **AV-13** 前端不得計算價位、距離、門檻、天氣映射或狀態。`entryObservation.ts` 的 `ENTRY_RANGE_MAX_PCT`、`ENTRY_PULLBACK_MAX_ABS_PCT` 與 `keyLevels.ts` 的計算本體，在 Phase 4 切換時刪除（grep，延伸 ADR-0018 K-11）。
- **AV-14** 風控守門測試（禁用詞、價位 allowlist、`FRONTEND_FORBIDDEN_TERMS` 同步）只能在 PR 描述引用新風控裁示編號時修改；qa-reviewer 必查。
- **AV-15** 只要 `PositionPlan` 含 `invalidation`、`risk_budget_stop` 或 `trailing`，`execution_caveats` 就必定非空（契約測試）。
- **AV-16** 任何金額或比率的輸入缺值時，輸出 null，不得是 0（延伸盤點 B4）。
- **AV-17** `forecast_*`、`plan_*` 表有 trigger 禁止 UPDATE／DELETE（例外只有 outcome 的一次性 NULL 轉值）；`recorded_after_next_open` 由寫入時的時鐘與休市日計算，不得手動指定。
- **AV-18** 計分只讀 `valid_until_session` 已過的 bars；`forecast_outcome` 寫入時重算 `input_digest`，不一致就記錄。
- **AV-19** 回應中不得出現機率、勝率類數值欄位（`probability`、`win_rate`、`hit_rate` 只允許出現在 `ValidationRef` 的歷史統計內，且必附 n 與區間）。
- **AV-20** 不得新增任何券商下單介面或模組（import graph 加 grep `order`／`broker` 白名單）。
- **AV-21** taxonomy membership 寫入時，缺 `evidence_ref` 或 `evidence_date` 就拒絕；`supply_chain_participant` 不得掛到 `main` 或 `sub` 層（store 測試）。
- **AV-22** 新模組使用的回看窗一律 import ADR-0020 的單一常數，不得另定。

## 測試要求（摘要）

- **AT-1**：截斷不變性。outlook、levels、plan 對 `bars[:t+1]` 的結果，不因追加 t 之後的 bar 而改變（含樞紐 k 根延遲）。
- **AT-2**：shift 偵測。把特徵整體前移一格（偷看 t+1）時，回放統計應明顯改變；canary fixture 在正確實作下不得命中。
- **AT-3**：horizon 獨立（AV-8）。
- **AT-4**：政策表。表格驅動逐列覆蓋 D-4 的每一序位，含持有、候選、不明三種模式。
- **AT-5**：價位性質。每個 `PlanLevel` 都有依據；`invalidation` 不高於它所依據的支撐區下緣；分批停利依序遞增；`spans_ex_date` 正確。
- **AT-6**：預測紀錄 append-only、point-in-time 時間判定（臨界：t+1 08:59:59 與 09:00:00）、`supersedes` 鏈。
- **AT-7**：計分。人工構造的 r_h 落在帶寬邊界；公司行動排除；基準三種並列；N_MIN 邊界。
- **AT-8**：守門測試 AV-1～AV-3、AV-5、AV-6、AV-9～AV-13、AV-20、AV-22。
- **AT-9**：天氣。兩個型別無法互相指派（型別測試）；每個列舉值都有映射；`insufficient` 對應「不預報」。
- 前端：狀態渲染、字面逐字釘住、AV-13 的 grep。

---

## 失效條件（任一成立時，本 ADR 須重審）

- **F-1**：使用範圍超出純自用（分享或商業化）。屆時本 ADR 整體重審；對他人提供投資建議可能涉及證券投資顧問相關法規〔推論，須法務確認〕。
- **F-2**：某個 scope 與 horizon 的上線紀錄達 N_MIN 後連續兩個評估期都是 `not_better_than_baseline`。該組合必須重新設計或下架，不得只換說法。
- **F-3**：`recorded_after_next_open` 的比率 > 事先登記的上限，或計分時發現 `input_digest` 不一致的比率 > 上限。暫停顯示，查明是否有前視問題。
- **F-4**：CEO 授權引入 LLM 或付費資料源。須另立 ADR。
- **F-5**：風控新護欄否決向上的條件價位、候選模式結論或題材分類。對應的 D-4.5、D-5.4、D-7 撤回並修訂本 ADR。
- **F-6**：Phase 1 的官方指數或休市日來源查證失敗。大盤天氣維持 `backup` 標示，`valid_until_session` 改以觀察到的 bar 日期事後計算，並揭露。
- **F-7**：ADR-0012 C-15 修訂未獲核可。`app/forecast/scoring.py` 不得實作，Phase 3 卡住。

---

## 待決事項

**CEO**
1. 核可本 ADR；核可 ADR-0004 部分修訂（§4 縮窄、DISCLAIMER 與定位理由失效）；核可 ADR-0012 C-15 部分修訂；知悉 ADR-0018 被取代，原待決 #1、#2 隨之撤銷。〔2026-10-16 CEO 已核可〕
2. 再次確認純自用前提（F-1）。〔2026-10-16 CEO 已再確認〕
3. 顯示閘門：(a) 歷史回放報告審查後即可顯示，附上線紀錄筆數；或 (b) 另加上線影子試跑 N 個交易日才顯示。**建議 (a)**，因為回放已能提供基準比較，影子試跑只會延後，不會改善誠實度〔推論〕。〔仍待 CEO〕
4. 預測紀錄的排程範圍：大盤、上市主族群、持倉、自選。on-demand 查詢的紀錄是否也計入（建議分開統計）。〔2026-10-16 CEO 已核可個股範圍＝庫存、自選、使用者查詢的個股（決策包 #5）；大盤、上市主族群的排程範圍與 on-demand 是否計入統計仍待 CEO（決策包 #19）〕
5. 新增「可用現金」自報欄位（加碼預算條件需要；不填時加碼條件為 `unavailable`）。〔仍待 CEO〕
6. 分期順序確認；Phase 2 與 Phase 3 的設計是否並行。〔2026-10-16 CEO 已核可〕
7. 確認不引入 LLM（D-10）。〔2026-10-16 CEO 已確認不引入 LLM〕
8. 細項與題材的策展人力：由 CEO 本人附證據建立，或延後。〔仍待 CEO〕
9. Phase 1 資料源查證需要可連網環境（CEO 本機或 devops-sre）。〔仍待 CEO〕
10. 是否同意另立 ADR-0026（庫存版本化與還原點）。〔2026-10-16 CEO 已同意立案 ADR-0026〕
- 註記：族群列表的「五日方向」＝未來 5 個交易日的展望（CEO 2026-10-16，見 `work/dispatch/2026-10-16-CEO決策-ADR-0025核可與五日方向.md` 二）；屬預測，受本 ADR「先記錄，再顯示」與驗證狀態標示約束，不是過去 5 日漲跌。

**風控（risk-compliance-officer）**
1. 新護欄取代或修訂以下裁示：phase8 §1.3（支撐、壓力、進場、停利、攤平、勝率等用語）、§4 C5／C6／C8；PX-3（族群詳細頁依成交金額排序、族群列表是否構成跨標的排序）、PX-4、PX-5（持有、等待、減碼、加碼與可考慮、等待、避免）、PX-7／PX-13、PX-12、PX-25。
2. `DISCLAIMER` 與全站定位句的新字面。
3. 天氣比喻是否可用，以及「不預報」狀態的用語；禁止降雨機率式數字（D-8.4）的確認。
4. `execution_caveats`、「未優於基準」、「證據不足」、「事實／推論／未確認」標籤的字面。
5. 推播警示的禁用清單（`買進/賣出/加碼/減碼/建議…`，phase8 L18）在新定位下要不要放寬；建議維持。
6. engine、plan、playbook 三種聲音並存時的衝突揭露規格。

**PM（product-manager）**
1. 依 D-12 改寫 PRD，每期附 Given/When/Then 驗收條件。
2. 「最需要處理」清單的排序規格（政策表的序位）。
3. 細項範圍與先後（金融、營建、醫療先做哪些）。
4. 首層「一個主要操作」的定義；五種分析狀態的定義。
5. 自選股範圍與上限（影響排程計算量）。

**quant-researcher**：事先登記 θ_h、MIN_COMPLETENESS、k_h（結果帶寬）、N_MIN 與不重疊換算、樞紐 k、聚類容差 c、ATR 緩衝 m、量能區間、天氣門檻、政策表 v0；回放方法論（樣本內與樣本外、block bootstrap 參數）。

**data-engineer**：D-9 表內 Phase 1 與 Phase 3 的資料源查證，含 point-in-time 時間欄位。

**art-lead**：深色海軍藍、薄荷綠與氣象視覺規範（取代 `stock-desk-視覺規範` 的 neutral 色階〔盤點所引〕）。

---

## 對既有在途工作的影響

| 工作 | 影響 | 處理 |
|---|---|---|
| F-9b2（幣別閘門 attempt log） | 無；屬 Phase 1 資料正確性 | 照原出貨條件（Codex 補跑或 CEO 書面放行） |
| F-9c（yfinance `meta.currency`） | 無；屬 Phase 1 | 六項硬性前提不變 |
| KT-1（Kelly 未平倉／跨界字面） | 內容是計數揭露，不是定位宣稱〔推論，未逐字檢查是否含「非投資建議」〕 | 照原計畫出貨。KT-R-4 過渡期禁止增修 Kelly 字面，所以 D-11 的字面遷移在 KT-1 出貨前不得觸及 Kelly 字面 |
| F-11（回測報告，已合併） | 字面與功能維持；它是 prompt 所列三類報告中的「策略績效」 | Phase 3 回放報告可重用 `episodes` 與 `report` 的純函式，但不得改動 F-11 的 golden（F11-A-26）與既有輸出；F-11 字面中若有舊定位句，納入 D-11 遷移清單送風控 |
| playbook（排程台） | 歸屬語「你自行設定的規則之機械執行結果，非本系統的判斷或建議」〔盤點所引：`playbook/wording.py:114-117`〕在 AV-11 成立的前提下仍然為真；playbook 的 S1 0.90、P1 1.20 等固定比率屬使用者參數〔事實：`playbook/models.py:96-110`〕，不受 D-5「系統價位不得用固定比率」約束 | 嚴守 AV-11；PX-28 的邏輯（系統輸出不得成為使用者規則）維持；同頁並存時依風控新規格揭露 |
| ADR-0018 案 A（已上線） | 由 Phase 4 切換取代 | 切換前維持現狀 |
| `entryObservation` 六項觀察條件 | 六項條件改為候選模式的 `Evidence`；MA20±3% 觀察帶由進場觀察區取代 | Phase 4 切換 |
| 規則 1.1.0 待 CEO R2 知悉 | 無 | 照原狀 |
| ADR-0014 盤中價 | 無；重申不作為判斷輸入 | 照原狀等實測 |
| F-12／F-13／F-14／F-16（規劃中） | F-14 週線與量價併入 Phase 3（levels v2 與 features）；其餘列 Phase 5 | PM 重排 |

---

## 未查證事項與作者揭露

- ADR-0005、0006、0008～0011、0015～0017、0019、0022、0023 只核對了狀態列，沒有讀全文；ADR-0012、0014 讀了部分。
- 標〔盤點所引〕的行號沒有逐一複核。
- D-9 所有候選資料源的端點、授權、額度、時間欄位全部未查證。
- 「不重疊樣本一年約 50 筆」與 LLM Token 量級都是推論或假設值。
- 沒有逐字檢查 KT-1、F-11 已定稿字面中是否含舊定位句。
- 沒有讀 `api/advice.py`，對 `AdviceResponse` 現況的描述轉引自 ADR-0018。

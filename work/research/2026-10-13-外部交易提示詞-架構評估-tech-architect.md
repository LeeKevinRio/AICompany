<!-- tech-architect 唯讀回報原文；coordinator 轉存，2026-10-13 -->

# tech-architect 架構評估：外部交易提示詞七則與 stock-desk 的整合（唯讀；由 coordinator 轉錄）

## 一、本次結論

- **建議採「A 為主、C 搭配」，B 現階段否決。** 這七則提示詞底下的實際需求，大部分能做成確定性、可離線測試的功能，也能沿用 ADR-0004。真正非 LLM 不可的只有 Prompt 3（新聞去噪），它在產品內的風險最高、價值最低，所以不進產品。
- **B 的問題是結構性的，不是調參數能補的。** 會碰到的衝突：
  - ADR-0004（accepted）明文「完全拒絕黑箱模型直接生成建議動作」。
  - ADR-0002（accepted）規定「不得用黑箱模型直接產生建議動作」。
  - 「字面須風控逐字核可」與 LLM 的自由生成文字無法同時成立。
  - 持倉、交易紀錄會外送第三方。
  - LLM API 依 token 付費，碰到 ADR-0003 的「絕不付費」紅線。
  - 要做 B，必須另立 ADR 局部取代 ADR-0004，並由 CEO 裁決成本與隱私。這件事不屬於架構師可以自行放行的範圍。
- **各則判定：**

| 則 | 判定 |
|---|---|
| Prompt 1（挑 5 檔、給進場／停損／停利） | **否決**。等於對未持有標的給目標價，違反 ADR-0004 架構約束 4「無目標價」；也需要訂單流、選擇權部位這類目前沒有、多半要付費的資料。原貼文裡被示範的那個 AI 助理自己也拒答了。 |
| Prompt 3（新聞轉交易） | 不進產品，也不做內部 skill，因為本環境沒有外網，agent 讀不到新聞。 |
| Prompt 2、4、5、6、7 | 走 A。Prompt 4 的方法論部分同時走 C（併入 `backtest-protocol`）。 |

- **可在本環境離線開工的**（都還要先有 product-manager 的 PRD）：
  - C：修 `backtest-protocol`。
  - A1：價格版跳空下跌事件回測。
  - A2：組合曝險與歷史壓力回放。
  - A3：交易紀錄檢討。
  - A4：交易日清單。
- **需要連網查證，或需要 CEO 決定的：**
  - 財報公告日資料源（Prompt 4 的「與獲利相關」過濾），要新開 ADR。
  - 任何 LLM 依賴（B）。
  - 全市場漲幅榜。
  - 選擇權部位。

## 二、各部門回報

### tech-architect（本評估）

#### 輸入契約缺口（先講清楚，不阻擋這次的篩選評估）

- 沒有 PRD 和驗收條件：要向 product-manager 要。這次只做「進不進產品、模組邊界」的篩選，不是 build 規格。
- 沒有非功能需求（LLM 預算、隱私底線）：要向 CEO 要。B 路線的成本數字由 devops-sre 查證現行定價，本評估不寫任何價格或版本。

#### 盤點到的既有能力（讀碼確認）

- `pyproject.toml` 依賴裡沒有任何 LLM SDK，確認。
- `app/playbook/engine.py` 檔頭明寫 `which is the whole reason this rule set is code and not a prompt`。產品既有立場就是「規則寫成 code，不寫成 prompt」。
- 回測：
  - `app/backtest/engine.py` 是單資產引擎，部位以 target weight（佔權益比例）表示。
  - `strategies.py` 用 `build_strategy(name)` 管一組封閉的策略。
  - `report.py` 已有 CAGR、Sharpe、Sortino、MDD、勝率、B&H 對照、walk-forward。
  - `costs.py` 有 `CostModel`，`episodes.py` 有 round-trip 統計。
  - `event_study.py` 有事件研究，只讀本機快取，資料不經網路。
- 相關性：`app/signals/risk.py::correlation_matrix` 和 `signals/service.py::compute_correlation` 已經存在，但沒有任何 API 對外提供（`app/api` 裡 grep 不到）。beta 也已有。產業集中度上限見 ADR-0022。
- 交易紀錄：`positions/models.py` 只有 `avg_cost`、`opened_at`、`note`，**沒有逐筆交易歷史**，Prompt 6 沒有資料可用。
- 新聞、財報日、選擇權：app 內完全沒有（grep `earnings|news|options` 沒有命中任何相關程式）。除權息有 `TWT48U_ALL`，但只有未來預告。

#### 評估摘要

- **採用：** A 路線，四個確定性功能（A1～A4），加上 C 路線（`backtest-protocol` 增補）。
- **否決：** 產品內嵌 LLM（B）、Prompt 1 的選股功能、產品內新聞分析（Prompt 3）。
- **延後到新 ADR：** 財報公告日資料源、週線以外的新時間框架以外的其他新資料。

#### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A. 規則式產品功能** | 沿用 ADR-0004，零新依賴（比照 ADR-0012 Options E1）；日線都經 `MarketDataService`，自動繼承 ADR-0024 的幣別閘門與 fail-closed；可離線用 fixture 測、可回溯（`rules_version`、`source`、`as_of`）；字面是固定句，能逐字送風控 | 做不出「讀新聞」「判斷市場哪裡定價錯」這類自然語言判斷；每個功能都要 PRD、要寫碼、要送審 | 範圍膨脹：七則一起做會把產品做成「交易助理」，偏離 ADR-0004「研究與教育工具」的定位，所以要分期，而且 Prompt 1 不做 |
| **B. 產品內嵌 LLM** | 開發快，Prompt 2、3、5、6 的敘述型輸出馬上有；能處理非結構化輸入（新聞、自由格式的交易紀錄） | 與 ADR-0004、ADR-0002 正面衝突；輸出不確定，無法逐字核可；沒有離線可測的品質保證（只能 stub）；e2e 無外網，只驗得到降級路徑 | 持倉與交易紀錄外送第三方；廠商端模型改版造成無聲漂移，無法回溯；幻覺出不存在於資料層的價格，繞過 ADR-0024 那套「沒有合格幣別就不印價格」的防線；按 token 計費碰到「絕不付費」紅線；AV 條款「非再散布」，把行情餵給 LLM 廠商可能構成再散布（ADR-0003 約束 11(d)） |
| **C. 只當內部工作方法** | 成本最低；Prompt 4 的「先寫假設、樣本不足直說、最糟交易、連敗、環境依賴」正好補上 `backtest-protocol` 的缺口；產品不動 | 對產品使用者沒有直接價值；Prompt 3、6、7 當成 skill，在本環境不是缺資料（沒網路、沒交易紀錄）就是根本執行不了 | skill 在 main，必須維持零產品耦合，不能寫死 stock-desk 的路徑或門檻（例如 ADR-0006 的 `MIN_OOS_ROUND_TRIPS = 20`）；照抄外部貼文原文有授權疑慮，應改寫為公司語言 |

#### 七則逐一對應：需求、資料源、既有 ADR、離線可測性

| 則 | 拆出來的確定性需求 | 需要的資料與既有資料層的關係 | 新 ADR？ | 離線可測 |
|---|---|---|---|---|
| 1 選股＋進出場 | 不做 | 漲幅榜：台股只有 ADR-0012 的 `market_daily_bars`（`STOCK_DAY_ALL` 當日快照）。ADR-0012 明定這張表若有其他用途「須另立 ADR」，ADR-0018 K-5 也把 `app.data.market_panel` 列為多個模組不可達。美股沒有全市場來源，ADR-0003 的 AV 一天 25 次也撐不住。即時報價受 ADR-0014 D-11、I-6 限制，只能用於持倉估值顯示，signals、advice、playbook 都不得觸及。選擇權部位與訂單流沒有任何來源，多半要付費 | 否決，不立案 | 不適用 |
| 2 圖表判讀 | 日線與週線（由日線重新取樣）、量價背離、趨勢強弱。三選一的結論要走 ADR-0004 規則引擎，並沿用 ADR-0018 關鍵價位 | 只需既有日線，經 `load_bars` 和 ADR-0024 閘門。週線由日線推導，不必新資料源 | 不用新資料源 ADR。若新增「未持有標的的買／等／遠離」動作詞彙，屬於擴充 ADR-0004 的 action 集合，要另立 ADR 並送風控 | 可以 |
| 3 新聞轉交易 | 確定性能做的只有「事件日曆」：列出財報、除權息、重大訊息的時間點，不解讀內容 | 新聞源完全沒有，還有授權與再散布問題；去噪本質上是 NLP | 進產品就要新的資料源 ADR 加上 B 的 ADR。建議不做 | 解讀部分不能離線測 |
| 4 盈利後錯位回測 | 新策略 id：「下跌 ≥5% 後兩日確認、第 2 日進、30 日或收破低點出」，每筆等額部位，單邊 5bps 滑點，報告加交易筆數門檻、最糟 5 筆、最長連敗、B&H 對照 | **A1（現在就能做）**：純價格版，不過濾財報，只用既有日線。**A1b（要連網）**：「與獲利相關」需要財報公告日，候選有台股公開資訊觀測站、美股 SEC EDGAR 申報日、AV 的 earnings 類端點，**本環境全部未查證**。這是新的 provider，不屬於 `PriceBar`，ADR-0024 的幣別閘門管不到，但代號必須共用 D-4 准入與 `canonical_us_symbol`。另有一個風險：十年美股若用未調整價，股票分割日看起來像 -50% 的「事件」，會被誤判（ADR-0003 尚缺事實 3，adjusted 口徑仍未定案） | A1 不用（新增策略 id 依 ADR-0018 D-8 的先例）。A1b 要新開「財報公告日事件資料源與 point-in-time 規則」ADR | A1 可以。A1b 的契約測試要等 CEO 本機錄真實 fixture；在那之前只能用檔名標 `synthetic` 的 fixture（比照 ADR-0014 的作法） |
| 5 組合真正在賭什麼 | 對外提供既有的相關性矩陣與 beta，加上產業與幣別曝險，再加「歷史壓力回放」：把持倉放進過去真實的下跌區間重放，不做假設情境。**不輸出重新配比的權重**，那是建議類輸出，要另走風控 | 只用既有日線。單一請求的 IO 預算受 ADR-0010 限制：N 檔持倉 × 多年的 bars 不可在請求內走 live 梯子，必須 cache-only，或盤後批次算好（比照 ADR-0012 C1）。「單一宏觀事件」若要因子資料（利率、美元、油價）就是新資料源，延後處理 | 只是對外提供相關性的話不用。壓力回放的演算法與計算時點要立一則小 ADR 或併入 PRD 規格；因子資料要另立 ADR | 可以 |
| 6 交易紀錄挑漏洞 | 新增逐筆交易紀錄（CSV 匯入或手動輸入），做確定性診斷：部位大小分布、贏家與輸家持有期間差異（處置效應）、出場是否違反停損、同類型錯誤重複出現。輸出「規則」時，要對應到既有 playbook 規則或固定模板，不自由生成 | 沒有外部資料源；個資只存本機 SQLite | 要。新模組 `app/journal/` 的邊界與資料表需要一則 ADR | 可以 |
| 7 交易日清單 | 依台股盤中時段（ADR-0014 D-3：09:00～13:25）產生固定清單：盤前看資料新鮮度、警示、playbook 指令與除權息日曆，盤中與盤後各有固定項目。「第一小時不追高」這類句子屬建議文案，必須風控逐字審 | 只用既有資料（playbook、alerts、`TWT48U_ALL`）。清單項目若要引用盤中價，需修訂 ADR-0014 D-11 | 不用。屬內容加前端，字面送風控 | 可以 |

#### 決策（ADR 草案要點，不落檔；編號以落檔時目錄為準）

目前 `docs/adr/` 最後一號是 0024，0013 已由員工線佔用，暫編如下。

**ADR-0025（暫編）：stock-desk 外部交易提示詞的整合邊界——產品不嵌入 LLM，需求以確定性模組實作**

- **Context：** CEO 2026-10-13 提供七則社群提示詞（外部素材，非公司規範）。產品沒有 LLM 依賴；ADR-0002 與 ADR-0004（皆 accepted）要求建議必須可解釋、走 YAML 規則式。風控要求使用者面字面逐字核可。ADR-0024 用 fail-closed 確保「價格沒有合格幣別就不印」。
- **Options：** 同上方 A、B、C 三列。
- **Decision：**
  1. 產品後端與前端不新增任何 LLM／生成式 AI 的 SDK 或 HTTP 呼叫。
  2. 七則提示詞只當作「需求來源」，依上表拆成確定性功能，各功能由 PRD 立案。
  3. Prompt 1 不立案。
  4. Prompt 3 產品內只能做不解讀內容的事件日曆，而且要先有事件資料源 ADR。
  5. 外部提示詞原文不得當作產品字面，也不得成為規則的 explanation 來源。
- **Consequences：**
  - 好處：所有新功能繼承既有的可回溯、fail-closed、離線可測、風控逐字核可。
  - 壞處：做不出「讀新聞」「自由敘述的分析」，使用者想要這類輸出，只能在產品外自行使用 AI 助理。
  - 每個功能都要走完整的 PRD → 風控流程，交付比 B 慢。
- **重啟條件（要走 B 必須同時滿足）：**
  1. CEO 書面同意付費與資料外送。
  2. 新 ADR 局部取代 ADR-0004，並寫明 LLM 只能放在「非建議路徑」。
  3. 輸出只能從風控已核可的固定句裡選，或只給 CEO 本人在內部使用、不上產品畫面。
  4. 每次呼叫記錄 model id、prompt hash、回應、`as_of`，達到可回溯。
  5. 送出的資料只能是已通過 ADR-0024 閘門的序列，持倉的 `note` 與數量要遮罩。
  6. API key 只從環境變數讀取。
  7. 測試全部用 stub，e2e 只驗降級路徑。
  8. risk-compliance-officer 審查再散布條款（ADR-0003 約束 11(d)）。
- **與既有 ADR：** 不取代任何 ADR，是再確認 ADR-0002、ADR-0004。

**ADR-0026（暫編，A1b 啟動時才寫）：財報公告日事件資料源與 point-in-time 規則**

- 新增 `EventCalendarProvider`（形狀為「代號 → 事件日清單」）。不得擴充 `MarketDataProvider`，理由比照 ADR-0014 A3 和 ADR-0012 §7：不把兩種資料形狀混在同一個介面。
- 每筆事件帶 `source`、`as_of`、`recorded_at`。
- 「與獲利相關」的判定窗要寫死：公告日當天或下一個交易日，盤後公告對應到下一個交易日，時區明列。
- 決策只能讀「當時已知」的事件。歷史回補的事件屬 hindsight，必須在報告中揭露（比照 ADR-0012 D-14）。
- 代號共用 ADR-0024 D-4 准入。
- 來源候選由 data-engineer 比較、devops-sre 查證額度與條款。用到 AV 的話會吃一天 25 次的額度，必須照 ADR-0003 約束 3 預算化。

**ADR-0027（暫編，A3 啟動時）：交易紀錄模組 `app/journal/` 的邊界**

- 結構：純函式的診斷模組，加上自己的 store（主 DB 新表）。
- 依賴方向：`api.journal` → `{journal, positions.models（只取型別）}`。
- 禁止事項：`app.journal` 不 import `app.advice`、`app.playbook`、`app.data.providers`、`app.services.quotes`；`app.advice` 不 import `app.journal`。也就是說，交易紀錄在另立 ADR 前不得影響建議卡。

#### 對實作的約束（逐條可檢查）

- **K-1** `backend/pyproject.toml` 不得出現 LLM／生成式 AI 套件。在 `tests/` 加一條依賴清單掃描測試，套件名單由 qa-reviewer 維護。另外以 grep 確認 `app/` 沒有對 LLM 廠商網域的 HTTP 呼叫。
- **K-2** 新策略（A1）必須經 `build_strategy` 註冊為新的 id，不得改動 `five_conditions` 等既有策略的語意（比照 ADR-0018 D-8）。
- **K-3** A1 的勝率、平均獲利、平均虧損、損益比、最長連敗，以 **round-trip** 為單位計算（`episodes.py`），不得用 fill 層統計。理由見 ADR-0006 Context 第 5 點：每日再平衡會產生微額 fill。「每筆等額」若用 target weight 實作，必須有測試證明不會產生持有期間的微額再平衡 fill。
- **K-4** 交易筆數低於門檻時，報告要明示「樣本不足、不具統計意義」，同時仍照實呈現數字（`backtest-protocol` 紅線：不隱藏）。門檻值由 quant-researcher 登記在方法論文件；不得直接沿用提示詞的「30」，也不得與 ADR-0006 的 20 混用、卻不說明。
- **K-5** 滑點與手續費一律經 `CostModel`。費率要有查證日期，不得寫死在策略裡。
- **K-6** 「最糟 5 筆交易的當時市場狀況」只能呈現同期指數報酬（依 ADR-0005 的指數路徑），不得生成文字敘述，也不得引用新聞。
- **K-7** A1、A2 所有日線讀取都經 `MarketDataService`，不得繞道（ADR-0024 D-1）。被閘門拒收的序列在相關性、壓力回放、回測中一律視為缺漏，不得補值或改用其他序列代替。
- **K-8** A2 在請求內不得對 N 檔持倉跑 live 日線梯子：只能 cache-only，或讀盤後批次結果。要有「零 HTTP」測試（比照 ADR-0010 R-1）。
- **K-9** A2 不輸出重新配比後的權重或目標部位。若 PRD 要求，另立 ADR 並送風控。
- **K-10** A4 清單和 A1～A3 所有使用者可見字面，一律以常數集中管理，並經 risk-compliance-officer 逐字核可後才能出貨。占位字面要有守門測試，禁止出貨（比照 ADR-0014 W9）。
- **K-11** 新模組都不得觸及盤中報價（ADR-0014 I-6 的 import graph 名單要加入新模組），也不得觸及 `app.data.market_panel`（ADR-0012 和 ADR-0018 K-5）。
- **K-12** C 路線對 `backtest-protocol` 的修改只能寫通用方法論，不得出現 stock-desk 路徑、常數或門檻值（CLAUDE.md §1 零產品耦合）；外部貼文改寫為公司語言，不照抄。

#### C 路線：`backtest-protocol` 建議增補（交 quant-researcher 起草，走 `chore/agent-*`）

1. **事前登記假設：** 跑回測之前，書面寫下「這個策略在賭什麼」和「在什麼環境下會失效」，跑完後對照，防止事後自圓其說。可與 ADR-0012 的 m 版本登記精神對齊，但 skill 不能引用產品 ADR。
2. **最少樣本：** 交易筆數低於門檻要直說沒有統計意義，門檻由各專案方法論登記。
3. **報告欄位增補：** 最糟 N 筆交易附日期、最長連敗。
4. **結論必答三題：** 是真優勢還是噪音、是哪一種市場環境造就的、實盤前期最可能從哪裡讓人失望。
5. **檢查清單加一項：** 價格序列是否已處理分割與除權息，避免「假事件」。

### 其他部門（本次未派工，只列交接需求）

- **product-manager：** 依 A1～A4 寫 PRD 和驗收條件；判斷 Prompt 2 的「未持有標的三選一」是否真有需求。
- **quant-researcher：** A1 方法論（事件定義、門檻、PIT 規則）；C 的 skill 增補草稿。
- **data-engineer：** 財報日來源比較表（A1b 前置）；A3 的交易紀錄 CSV 欄位。
- **devops-sre：** 查證候選事件來源的額度與條款；若 CEO 仍要評估 B，查證 LLM 定價與資料保留政策。
- **risk-compliance-officer：** A1～A4 的全部字面；Prompt 1 否決的確認；B 若重啟時的再散布與個資審查。
- **creative-lead：** A4 清單與各功能字面草稿。

## 三、驗證

- **實際讀過：**
  - 外部素材原文：`/home/user/AICompany/work/research/2026-10-13-外部交易提示詞七則-原文.md`
  - ADR-0001、0003、0004 全文
  - ADR-0005、0006、0008、0011、0012、0014、0018、0021、0024 的前段，以及 0002、0010 的相關條文
  - `/home/user/AICompany/.claude/skills/backtest-protocol/SKILL.md`、`data-source-integration/SKILL.md`
  - `/home/user/AICompany/apps/stock-desk/backend/pyproject.toml`
  - `app/playbook/engine.py`、`app/backtest/event_study.py` 檔頭
  - 用 grep 盤點過 `backtest/engine.py`、`strategies.py`、`report.py`、`signals/risk.py`、`signals/service.py`、`positions/models.py`、`dividends/providers.py`
- **沒有讀完的：**
  - ADR-0012（1157 行，讀到 L388）、ADR-0014（讀到 L439）、ADR-0024（讀到 L211）。本評估引用的條文都在已讀範圍，但未讀段落可能還有相關約束，落檔前請 tech-writer 交叉比對。
  - ADR-0015、0016、0017、0019、0020、0022、0023 只看了狀態行。
- **事實與推論分開：**
  - 「`correlation_matrix` 沒有對外 API」和「沒有逐筆交易表」是 grep 的結果，屬於確認過的事實。
  - 「美股分割日會被誤判成下跌事件」是依 ADR-0003 尚缺事實 3 推出來的，沒有對真實資料驗證。
  - 財報日候選來源（公開資訊觀測站、SEC EDGAR、AV earnings 類端點）在本環境**全部未查證**，只是候選名單，不是規格。
- **ADR 狀態要注意：** 這次引用的 ADR-0011、0014、0018、0021、0024 都是 **proposed**，不是 accepted；與它們相關的約束，以最後核可的版本為準。
- **紀律：** 全程唯讀，沒有改任何檔案；沒有讀 `.env` 或任何 `*.db`；沒有執行測試或任何指令；沒有指定任何套件版本或價格。

## 四、下一步

1. **CEO 裁決：**
   - (a) 是否同意「B 現階段否決、A＋C 分期」。
   - (b) 是否接受 Prompt 1 不立案。
   - (c) A1～A4 的優先順序。架構建議 C → A1 → A2 → A3 → A4：A1 和 A2 重用既有能力最多。
2. **可立即離線開工，不需連網：**
   - quant-researcher 從 origin/main 開 `chore/agent-backtest-protocol-*`，起草 skill 增補，經 qa-reviewer 審查後合併回 main，再由產品線 `merge origin/main` 同步。
   - product-manager 起草 A1、A2 的 PRD。
3. **PRD 到位後：** 由 tech-architect 出 A1、A2 的實作約束定稿；A3 啟動時出 ADR-0027 草案，交 tech-writer 落檔。
4. **需要連網或 CEO 本機：** A1b 的財報日來源查證，由 data-engineer 加 devops-sre 負責，CEO 本機錄 fixture，之後才寫 ADR-0026。
5. **若 CEO 仍想評估 B：** 先提供預算上限和「哪些資料可以外送」的書面底線。之後由 devops-sre 查證定價與保留政策、風控審再散布與個資，tech-architect 才會出局部取代 ADR-0004 的草案；在此之前，任何 LLM 依賴的 PR 一律否決。

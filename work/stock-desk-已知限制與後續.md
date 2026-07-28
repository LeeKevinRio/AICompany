# Stock Desk — 已知限制與後續工作清單

**編寫日期**：2026-07-26  
**撰寫者**：tech-writer（基於代碼實地確認）  
**對象**：開發團隊、tech-architect、risk-compliance-officer、CEO

---

## 限制清單

### 1. US 市場無 data provider adapter

**現況**：
- 後端定義上支援 `Market="US"` 與 `Currency="USD"`（見 `app/positions/models.py` 與 `app/data/interface.py`）。
- 但僅實作了台股適配：`TWSEProvider`、`TPExProvider`、`FinMindProvider`（見 `app/data/providers/`）。
- 美股無任何 adapter；嘗試查詢 US 標的會降級至快取，最終回 `unavailable`。

**影響**：
- 任何 US 標的（美股、美國 ETF）均無法取得日線數據。
- 相應的訊號、建議卡、槓桿拆解均無法計算。
- 使用者可以手動輸入 US 部位，但該部位在儀表板與決策中形同「無效」。

**解法方向**：
- 實作 Alpha Vantage adapter（ADR-0003 提案之主來源；25 req/day 免費額度）。
- 實作 yfinance adapter（備援來源；額度無限但非官方，隨時可能失效）。
- 額度管理：單日持倉標的數 ≤ 25 時 AV 足夠；超過需跨日或動用備援。
- 涉及 ADR-0003 的降級鏈、來源標示、快取 TTL、ticker 正規化等架構決策。

**建議負責角色**：dev-lead / tech-architect（需重評 ADR-0003 的實施狀態與優先序）。

---

### 2. 指數日線無來源（影響槓桿 ETF 情境推估）

**現況**：
- 槓桿 ETF 的情境推估（`app/leverage/erosion.py`）需要「標的指數」的日線（e.g., QQQ 對應 Nasdaq-100）。
- 後端無任何指數 adapter。
- **Drag 拆解同樣需要指數日線**；無指數時 drag 與 erosion **兩區都回 insufficient_data**。

**影響**：
- 所有 `instrument_type == "leveraged_etf"` 持倉的 leverage chapter，drag 與 erosion 區塊都恆回 `status="insufficient_data"`。
- 使用者既看不到已發生的拖曳拆解，也看不到情境推估。

**解法方向**：
- 評估是否需要指數日線。若 US 市場 adapter 實作（見上），可同時接入 Alpha Vantage 的指數行情（^GSPC、^IXIC 等）。
- 若台股槓桿 ETF 也需指數，評估 TWSE 是否公開指數日線，或使用 FinMind 備援。
- 架構上需新增指數 adapter，可能沿用既有 provider 介面擴充。

**建議負責角色**：tech-architect / dev-lead（先明確需求優先序；是否要支援槓桿 ETF 情境推估）。

---

### 3. 槓桿 ETF 倍數與費用率未查證

**現況**：
- `app/leverage/detect.py` 維護一份 **17 筆硬編碼的槓桿 ETF 註冊表**，來源明文標示為「模型訓練知識」。
- 無外部資料源、無爬蟲、無 pattern matching：每筆直寫倍數與費用率。
- `verified` 欄位**永遠為 false**（REGISTRY_VERIFIED_ON = None，17 筆全部硬編碼 False）。
- Metadata 若不準確，drag decomposition（費用效應）與 erosion scenario 的數字會偏誤。

**影響**：
- 槓桿 ETF 拆解中的費用效應計算若使用未驗證的費率，結果不可信。
- 場景推估中的目標倍數若錯誤，推估方向錯誤。
- 使用者看卡片時若不展開 metadata 的 `verified` 欄位，可能過度信賴不準確的數字。

**解法方向**：
1. 人工更新 metadata（特別是常見台灣槓桿 ETF 的費率與倍數），標記 `verified=true`。
2. 自動源（爬蟲、API）維護 metadata；或依賴 FinMind / 台灣期交所公開資訊。
3. UI 端強調 metadata 的驗證狀態徽章；未驗證者明顯警示。
4. 測試中增加 golden fixtures（實錄的知名 ETF 拆解結果），防止 regression。

**建議負責角色**：risk-compliance-officer（確認哪些 ETF 需要查證）+ dev-lead（實作自動維護機制）。

---

### 4. 產業欄位缺失

**現況**：
- `Position` 模型（`app/positions/models.py`）無 `sector` 欄位。
- 風險上限中的「單一產業佔比上限」（第 2 條）恆無法評估，回 `status="not_evaluable"`。
- ADR-0002 提到建議引擎輸入應涵蓋產業，但無數據來源。

**影響**：
- 產業集中度風險無法量化，第 2 條上限形同虛設。
- 多產業組合的風險評估不完整。

**解法方向**：
1. 新增 `Position.sector` 欄位（Literal 列舉或自由文本）。
2. 資料源：人工輸入 + TWSE/FinMind 代碼對應表（代碼 → 產業分類）。
3. CSV 匯入時新增 sector 欄。
4. 產業代碼標準化（e.g., 台灣產業分類、GICS）。

**建議負責角色**：product-manager（產業分類標準）+ dev-lead（欄位 migration、UI 更新）。

---

### 5. Kelly 準則輸入無來源

**現況**：
- `app/advice/limits.py` 定義了 `kelly_fraction_cap` 與 `kelly_position_cap`（預設值分別 0.25 與 0.10）。
- Kelly 準則需要「勝率」、「獲利：虧損比」等歷史績效數據。當前無任何計算這些數據的模組。
- 第 5 條上限（Kelly 部位上限）幾乎總是 `not_evaluable`。

**影響**：
- Kelly 上限形同虛設，只作為保守預防上限，無實用價值。
- 使用者若信賴 Kelly 準則，需外部手工計算並填入設定頁，體驗割裂。

**解法方向**：
1. 計算 Kelly 輸入（勝率、獲利損失比）：
   - 可從 backtest 結果直接提取。
   - 或從實際交易歷史回溯（需新增交易日誌模組）。
2. 新增「Kelly 計算器」UI，接收歷史績效參數，輸出建議的 Kelly 部位。
3. 允許使用者在設定頁手工調整 Kelly 相關參數。
4. 若暫無實作，建議在上限檢查說明文案中明示「本上限需要盈虧比等輸入，當前暫未實作」。

**建議負責角色**：tech-architect / product-manager（評估 Kelly 的業務必要性）+ dev-lead（如實作，涉及計算與 UI）。

---

### 6. 總曝險無現金資料

**現況**：
- `app/advice/book.py` 明確說明：系統無現金或融資餘額數據。
- `PortfolioContext.gross_exposure_twd` 恆為 `None`。
- 第 3 條上限（總曝險上限；預設 100%）恆 `not_evaluable`。

**影響**：
- 無法計算帳戶總曝險（含空頭、融資倍數等）。
- 杠桿度不可知；過度集中或融資的風險無法檢測。
- 上限形同虛設。

**解法方向**：
1. 接入券商帳戶 API（取得現金、融資、保證金數據）。
   - 台灣：整合複委託 API（富邦、永豐等）或直連元大、國泰等。
   - 美股：Interactive Brokers、Alpaca 等提供帳戶餘額 API。
2. 折衷方案：使用者手工輸入「帳戶總淨值」，系統計算 `gross_exposure = 持倉市值 / 淨值`。
3. 文案強調當前的限制，提醒使用者手工追蹤曝險。

**建議負責角色**：CEO（業務決策）/ risk-compliance-officer（風控詢價）+ dev-lead（技術整合）。

---

### 7. 外幣 FX 風控層未接線

**現況**：
- `app/data/providers/fx.py` 是**完整的台灣銀行 USD/TWD 日線匯率 adapter**，實作了速率限制、7 天回溯、缺值不捏造等機制。
- **但該 adapter 本身帶未查證狀態**（`fx.py:6-10, 19-25` 自述）：端點與 CSV 欄位格式未對照線上實際回應查證（開發環境無外網）；且「當日匯率」取的是即期買入價與賣出價的**中點模型值**，非官方收盤匯率。與回測費率未查證屬同一類問題，美股 adapter 上線前須補上常駐揭露。
- `app/portfolio/valuation.py` 已接線進估值層，會自動轉換幣別、拆解標的/匯率貢獻。
- **但** `app/advice/book.py` 的風控輸入路徑（計算風險上限的上下文）尚未接 FX。
- 結果：US 部位的價格類上限會回 `not_evaluable`。

**影響**：
- 混幣投資組合的風險度量不完整（無法統一單位比較風險上限）。
- 雖然估值層已做幣別轉換，風控層卻用不上，形同半功能狀態。

**解法方向**：
1. 在 `advice/book.py` 的 PortfolioContext 構建時補入 FX 轉換。
2. 確保風控上限層能讀到統一幣別的風險度量。

**建議負責角色**：dev-lead / risk-compliance-officer（確認幣別轉換的精度與時點）。

---

### 8. 回測策略僅 ma_cross

**現況**：
- `app/backtest/strategies.py` 僅定義 `ma_cross`（20/60 日均線交叉），無其他策略。
- API 端點對未知策略回 422（`KeyError` 攔截）。

**影響**：
- 使用者只能用一個教科書例子回測；無法驗證自己的策略想法。
- 產品的回測功能侷限於演示，實用性低。

**解法方向**：
1. 新增內置策略：
   - RSI 超賣反彈（RSI < 30）。
   - 高低點突破（N 日新高）。
   - 動量策略（動量 > 0）。
   - 等等。
2. 允許使用者上傳 Python 程式碼定義策略（高風險，需沙箱與審核）。
3. 短期可固化 2-3 常見策略；長期評估使用者自定義的必要性與安全性。

**建議負責角色**：product-manager（策略優先序）+ dev-lead（實作）。

---

### 9. 警示規則無「修改」端點（HTTP PUT / PATCH 缺席）

**現況**：
- `app/api/alerts.py` 只實作 `GET`（列出）、`POST`（新增）、`DELETE`（刪除）三個動詞，沒有 `PUT` / `PATCH`。
- 要調整一條既有規則的門檻或啟用狀態，目前只能刪掉重建；重建後規則會拿到新的 id。
- 已產生的警示事件（`alert_events`）不會被連帶刪除，歷史記錄本身不受影響。

**影響**：
- 微調門檻（例如把 price_above 從 1000 改成 1050）的操作成本偏高。
- 規則 id 變動後，若日後要做「同一條規則的觸發歷史」統計，事件與規則的對應會斷開。

**解法方向**：
1. 補 `PUT /api/alerts/{rule_id}`（整條替換）或 `PATCH`（部分欄位），沿用既有 pydantic discriminated union 驗證。
2. 前端 `AlertRulesSection.tsx` 補編輯表單，重用新增表單的欄位元件。
3. 若要保留觸發歷史的關聯性，更新時維持同一 `rule_id`。

**建議負責角色**：dev-lead（後端端點）+ frontend-engineer（編輯 UI）。

---

### 10. 風控官在 Phase 6 放行時列管的 7 項 suggested

**現況**：以下為 risk-compliance-officer 於 Phase 6 審查通過（APPROVE）時明列、且同意不擋本次上線的建議事項。七項皆不構成保證性語氣、隱藏風險或不實陳述，但都屬於「可以更好」：

1. **`quantity_range_reason` 欄位**：`quantity_range` 為 `null` 時，前端只顯示概略說明「無法從風險上限推導」，不區分實際成因。實際共**七條路徑**（`app/advice/limits.py`）——其中六種是「想推導但推導不出來」，一種是「這個動作本來就不產生區間」：

   | 成因 | 位置 |
   | --- | --- |
   | 無價格（`price_twd()` 為 None 或 ≤ 0） | limits.py:485-487 |
   | `notional_caps` 全空（無總資產） | limits.py:488-490 |
   | 買方：上限已無剩餘額度 | limits.py:496-501 |
   | 賣方：無超額（`current - binding_value <= 0`） | limits.py:515-516 |
   | 賣方：持股不足 1 股 | limits.py:518-525 |
   | 賣方：步數上限內無法驗證 | limits.py:526-537 |
   | `action` 為 `hold` / `insufficient_data`（本來就不產生區間） | limits.py:563 |

   其中「買方無剩餘額度」與「hold 本來就沒有」是最常出現的兩種。

   風控官放行條件有二：(a) 此項須留在 backlog，下次動到建議卡時一併處理；(b) **在該欄位經其審查前，這句概略文案不得被改寫成指稱特定成因**——把安全的概略敘述改成具體宣稱，反而可能為假。成因愈多，(b) 就愈必要：上表七條路徑正是這個條件的事實基礎。

2. **建議卡「總資產」未加限定語**：實為「已成功估值的部位市值合計」，不含現金。誤差方向保守（分母偏小、比率偏高、更早擋下加碼），揭露收在同頁 `context_notes`。建議改為「總資產（已估值部位市值）」或在上限清單上方加一行常駐限定語。

3. **命中規則未標示方向**：後端已產出 `has_conflict` 與 `direction_weights`，畫面未使用，讀者看不出本次有無反向證據同時命中。

4. **回測報告缺一行常駐警語**：建議加「回測為歷史模擬結果，內含成交假設與費率假設，不代表未來績效」。（該頁已有三項更具體的揭露，故未列 required。）

5. **槓桿專章假設清單預設收合**：建議 drag / erosion 兩區各補一句 inline 摘要，讓最關鍵的一兩條假設不必展開即可見。

6. **`signal_condition` 未納入警示 banned-word 測試**：其字彙為封閉集合，實務上無法混入動作動詞，但測試建議補一條。

7. **`RiskGauge` 五條 not_evaluable 為硬編碼**：後端補上逐部位台幣市值等輸入後不會自動翻轉，會停留在偏保守的「無法評估」。方向安全但長期名實不符，建議改由後端回報。

另有兩項風控官已宣告**在設定頁允許調整上限值之前必須轉為 required**（目前預設值下不成立問題）：

- **`default.yaml` 的 `concentration_watch` 硬寫 12% 門檻**，卻引用可調的「單一標的佔比上限」；使用者若把上限調到 10%，畫面會在上限已被突破時仍顯示「接近上限」。**（已完成：規則文案改為只陳述規則自身的固定 12% 門檻，並把上限判定指回卡片風險上限清單；規則集升版 1.0.2，風控官已於複審定稿）**

- **`RiskBudget` 的 `max_position_weight`（上界 0.50）與 `max_gross_exposure`（上界 1.50）硬性上界**；放寬須經風控官與 CEO 書面同意。**（已實裝於 `advice/limits.py`，超界回 422 並附繁中理由；`MAX_POSITION_WEIGHT_CEILING` = 0.50、`MAX_GROSS_EXPOSURE_CEILING` = 1.50 兩個數值已於 2026-07-26 經風控審查後由 CEO 書面定案，出處記於該檔常數註解）**

**影響**：皆為揭露品質與可讀性層面；不影響目前輸出的正確性與誠實性。

**解法方向**：下次動到建議卡 / 回測頁 / 槓桿專章時順道處理；上述兩項硬性上界已確認，無待辦。

**建議負責角色**：frontend-engineer（2、3、4、5、7 的呈現）+ dev-lead（1、6 與設定頁）+ risk-compliance-officer（新文案定稿）。

---

### 11. Codex 第二意見因環境無憑證缺席

**現況**：
- CLAUDE.md 規定 code review 需 qa-reviewer + OpenAI Codex CLI 第二意見。
- 當前 sandbox 環境無外網憑證，Codex 調用失敗。

**影響**：
- 對 stock-desk 的 code review 無第二意見，增加風險。
- 量化、訊號層的邏輯複雜，缺乏獨立審查。

**解法方向**：
- 環境修復：由 devops-sre 配置 Codex API 密鑰與代理穿透。
- 臨時方案：qa-reviewer 手工執行更嚴格的邏輯複查（特別是回測、訊號、建議引擎）。

**建議負責角色**：devops-sre（環境修復）/ qa-reviewer（臨時強化審查）。

---

## 後續工作優先序建議

基於影響度與依賴關係：

### P0（Must Have，影響產品核心功能）
1. **實作 US 市場 adapter**（Alpha Vantage + yfinance）
   - 解決「美股無數據」問題。
   - 後序：FX、指數 bars 都依賴此基礎。
   - 時間估計：2 週（tech-lead）。

2. **產業欄位補全**（Position.sector）
   - 第 2 條風控上限得以真正運作。
   - 相對簡單的欄位 migration。
   - 時間估計：1 週（dev-lead）。

3. **風控層接線 FX**（`advice/book.py`）
   - 美股 adapter 實作後即可同步。
   - 讓混幣投資組合的風險評估完整。
   - 時間估計：1-2 天（dev-lead）。

### P1（Should Have，顯著提升完整性）
4. **指數日線 adapter**（槓桿 ETF 情境推估）
   - 待 US adapter 實作後，同時接入指數。
   - drag 拆解與 erosion 推估都會恢復功能。
   - 時間估計：1 週（tech-lead）。

5. **Kelly 準則實現**
   - 若 backtest 頻繁使用，可直接抽取 Kelly 輸入。
   - 否則可推遲至有交易日誌模組之後。

6. **補 PUT/PATCH 警示規則端點**
   - 提升編輯使用體驗。
   - 時間估計：2-3 天（frontend-engineer + dev-lead）。

### P2（Nice to Have，功能增強）
7. **新增內置回測策略**（RSI、突破等）
   - 提升回測工具的實用性。
   - 可漸進式新增（無 breaking change）。

8. **Codex 環境修復**
   - 加強 code review 質量；不是功能性的。

9. **使用者自定義策略**（長期願景）
   - 需沙箱、審核、版本控制等基建；優先度低。

10. **帳戶 API 整合**（現金、融資、總曝險）
    - 長期理想狀態；短期可用文案提醒使用者手工監測。

---

## 跨團隊協作點

| 工作項目 | 涉及團隊 | 決策點 |
| --- | --- | --- |
| US adapter | dev-lead、tech-architect | ADR-0003 實施排期、額度管理策略確認 |
| 產業欄位 | product-manager、dev-lead | 產業分類標準確認（GICS vs. 台灣標準等） |
| FX 風控層接線 | dev-lead、risk-compliance-officer | 幣別轉換精度、時點確認 |
| 指數 bars | dev-lead、tech-architect | US adapter 後同步規劃 |
| Kelly 計算 | tech-architect | 是否需要；若需，優先序 |
| 警示規則編輯 | frontend-engineer、dev-lead | 是否支援軟 PUT、還是只保留 delete-and-recreate |
| 風控文案審查 | risk-compliance-officer、tech-writer | 編製審查清單、落檔標準 |
| Codex 修復 | devops-sre | 環境配置 |

---

## 文件與代碼對照表

實地確認的代碼位置供後續追蹤：

| 限制項 | 相關代碼檔 | 行數範圍 |
| --- | --- | --- |
| 1. US adapter 缺失 | `app/data/providers/__init__.py` | (僅 twse/tpex/finmind) |
| | `app/positions/models.py` | (Market 定義) |
| 2. 指數 bars + drag 缺失 | `app/leverage/drag.py:291-296` | (无指数 → insufficient_data) |
| | `app/leverage/service.py:163-166` | (同上，drag+erosion) |
| 3. Metadata 未驗證 | `app/leverage/detect.py:44,87-88` | (verified_on=None, ALL false) |
| 4. 產業欄位缺失 | `app/positions/models.py` | (無 sector) |
| | `app/advice/limits.py:40-46` | (LIMIT_IDS, LIMIT_NAMES) |
| 5. Kelly 無來源 | `app/advice/limits.py:82-86` | (Kelly 預設值) |
| 6. 總曝險無現金 | `app/advice/book.py:180-193` | (fx_to_twd 邏輯、gross_exposure 無) |
| 7. FX 風控層未接 | `app/data/providers/fx.py:1-216` | (完整 adapter) |
| | `app/advice/book.py` | (未接線) |
| 8. 策略僅 ma_cross | `app/backtest/strategies.py:28-69` | (STRATEGY_IDS) |
| 9. 警示規則無編輯 | `app/api/alerts.py:84-120` | (僅 GET/POST/DELETE) |
| 10. 風控 7 項 suggested + 2 required | 見 #10 段落 | Phase 6 審查紀錄 |
| 11. Codex 缺席 | 環境級 | (sandbox 無外網憑證) |

---

## 更新日誌

- **2026-07-26**：修訂版；基於代碼實地確認，修正 FX 與 drag 的敘述，明確 required 項目的實裝狀態，更新優先序建議。
- **2026-07-28**：~~台股資料源首次真實環境驗證通過~~ **此筆記錄已撤銷**。查證結果：
  (a) 實測確認開發容器的網路政策無法連至 TWSE / FinMind / TPEx（三者皆遭代理拒絕，2026-07-28 重測仍然如此）；
  (b) CEO 澄清其瀏覽並非以 Docker 在本機執行；合理推斷（待 CEO 確認）其看到的是 E2E 驗收期間
  容器內伺服器經 Claude Code 網頁預覽呈現的畫面——該環境的資料為離線示範資料（`source=demo_synthetic`），並非真實台股行情。
  結論：**台股資料源至今仍未經任何真實環境驗證**，維持「待有網環境查證」狀態。
  教訓：查證紀錄必須附可觀測證據（來源徽章、後端 log）；「畫面上有數字」不構成驗證。

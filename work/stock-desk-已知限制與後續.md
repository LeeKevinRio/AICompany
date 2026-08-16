# Stock Desk — 已知限制與後續工作清單

**編寫日期**：2026-07-26  
**撰寫者**：tech-writer（基於代碼實地確認）  
**對象**：開發團隊、tech-architect、risk-compliance-officer、CEO

> 檔案路徑慣例：本檔內裸寫 `app/...` 的路徑（原 2026-07-26 版本沿用）皆相對於
> `apps/stock-desk/backend/`；2026-08-10 新增內容改用完整前綴 `backend/app/...`／
> `frontend/app/...`（相對於 `apps/stock-desk/`），兩者指向同一組檔案，僅前綴寫法不同。

---

## 限制清單

### 1. US 市場 adapter 已實作，但未經真實環境驗證（原「無 adapter」已過時）

**已解決（Phase 7，dev-lead；ADR-0005）**：
- `app/data/providers/alpha_vantage.py`（主）與 `app/data/providers/yfinance.py`（備援）已實作並接線：
  `MarketDataService(primary=AlphaVantageAdapter(), backups=[YFinanceAdapter()], cache_first=True)`
  （`backend/app/api/deps.py:89-94`，ADR-0005 決策四：TTL 快取先行 → AV → yfinance → 任何快取 → unavailable）。
- 需要環境變數 `ALPHA_VANTAGE_API_KEY`；未設定時主來源在發送請求前就直接放棄
  （`backend/app/data/providers/alpha_vantage.py:98,161`），自動降級至 yfinance 備援或快取。

**仍存在的限制**：
- 兩個 adapter 的端點與回應格式都是「依公開文件與訓練知識撰寫（2026-07-23），未對照真實回應
  查證」——本沙盒環境對外網 HTTPS 被擋，無法連線驗證（`backend/app/data/providers/alpha_vantage.py:16-20`）。
- 在本沙盒環境裡，即使 adapter 已接線，實際查詢仍只會拿到 `unavailable`（egress 被擋）。

**影響**：US 標的的日線、訊號、建議卡、槓桿拆解**架構上可以計算**（adapter 存在且接線），
但尚不能視為「production ready」——回應格式尚未經過一次真實請求驗證。

**查證方式**：`apps/stock-desk/scripts/verify_market_data.py`（CEO 本機一鍵核實工具，見
`work/stock-desk-數據核實操作說明.md`）。

**建議負責角色**：devops-sre / data-engineer（在有網路的機器執行核實工具，核實後更新
`alpha_vantage.py` / `yfinance.py` 檔頭的查證日期與 `verified` 狀態）。

---

### 2. 指數日線已有 adapter，但僅 12/17 檔槓桿 ETF 有對映指數（原「無任何指數 adapter」已過時）

**已解決大部分（Phase 7，dev-lead；ADR-0005 決策一、二）**：
- 指數序列現由 yfinance 提供，經 `IndexProviderBridge` 接進與 US 市場同一套
  `MarketDataService`（`cache_first=True`），TW/US 兩個市場共用同一個服務
  （`backend/app/api/deps.py:98-120`）。
- `app/leverage/index_mapping.py` 是「槓桿 ETF 代號 → 可查詢指數代號」對映表：17 檔登記標的中
  **12 檔為 `official_index`**（有可查詢代號，如 `^NDX`／`^GSPC`／`^TWII`），**5 檔為明確聲明的
  `unmapped`**（`00631L`、`00632R`、`00680L`、`SOXL`、`SOXS`；`index_mapping.py:168-295`）。
  `unmapped` 不是「還沒做」，是「已查過、查不到可用序列，且刻意不拿追蹤 ETF 代理」
  （`index_mapping.py:25-27,139-155`）——代理標的自身的費用率與折溢價會污染拆解的費用效應與殘差。
- `GET /api/leverage/{symbol}` 已實際呼叫 `load_index_bars` 並把結果傳入 `build_leverage_chapter`
  （`backend/app/api/leverage.py:84-100`），**不是**寫死 `index_bars=None` 的呼叫。

**現在的限制範圍縮小為**：
- 上述 5 檔 unmapped 標的（含最常見的 `00631L`）的 drag 與 erosion 仍恆回 `insufficient_data`，
  原因是「臺灣50指數沒有已查證的免費日線代號」，而非「系統沒有指數 adapter」
  （`index_mapping.py:139-143`）。
- 對映表本身（12 檔 mapped 的序列代號是否真的可查詢）**尚未查證**：`MAPPING_VERIFIED_ON = None`，
  17 筆全部 `verified=False`（`index_mapping.py:60,112`）。
- 本沙盒環境對外網被擋，即使是 mapped 的標的，此環境內實測仍只會拿到 `unavailable`。

**影響**：`instrument_type == "leveraged_etf"` 的持倉**不再全部恆回 `insufficient_data`**；
mapped 的 12 檔在有網路且對映查證通過後可計算，unmapped 的 5 檔則設計上就是不計算，並附明確原因。

**解法方向**：
1. devops-sre／data-engineer 在有網路環境查證 12 檔 mapped 序列代號是否確實可查詢，
   設定 `MAPPING_VERIFIED_ON` 與各列 `verified=true`。
2. 5 檔 unmapped 標的若要支援，需先找到臺灣50指數／ICE 半導體指數／ICE 美國公債指數的
   已查證免費日線來源，這是資料來源問題，不是接線問題。

**建議負責角色**：devops-sre（查證）/ tech-architect（若要支援 unmapped 標的，需評估新資料源）。

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

### 4. 產業欄位已補上（FR-12，原「Position 無 sector 欄位」已過時）

**已解決（Phase 8 C1 批，dev-lead，commit `9f283ec`；審查：qa PASS + risk-compliance-officer
APPROVE，2026-08-09，`work/reviews/c1-phase8-review.md`）**：
- `Position.sector: str | None`（`backend/app/positions/models.py:73`），**僅限台股**
  （`market != "TW"` 時 `sector` 必須為 `None`，`models.py:91-92`）。
- 合法值為 TWSE 37 個產業別的封閉清單，不接受自訂文字
  （`backend/app/positions/sectors.py:36-73,80-83`）；清單經
  `GET /api/positions/sectors` 提供給前端下拉選單（`backend/app/api/positions.py:60-61`）。
- 前端持倉表單已接線（台股顯示 37 選項下拉；非台股停用並沿用後端 422 訊息），經等效實機驗收
  PASS（`work/dispatch/2026-08-09-frontend-wiring.md`「4 PASS」段）。
- 風控第 2 條上限（單一產業佔比）已可實際計算聚合，不再恆 `not_evaluable`
  （`backend/app/advice/book_limits.py` 的 `sector_weight` 聚合邏輯）。

**仍存在的限制**：
- 美股（US）持倉不可填產業別（`sectors.py:85-89`）——GICS 與 TWSE 是不同體系，沒有已裁決的
  美股分類標準，US 持倉的第 2 條上限對該檔標的仍是 `not_evaluable`。
- 台股 37 類清單本身**未對照官方 TWSE 資料查證**，屬「模型訓練知識」彙整，等待 data-engineer
  在有網路環境覆核（`backend/app/positions/sectors.py:17-27`）。

**建議負責角色**：data-engineer（查證台股清單）/ product-manager（若要支援美股，需先定分類標準）。

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

> **2026-08-05 更新（Phase 8 / FR-9，dev-lead）**：已採下方「解法方向」第 2 項的折衷方案落地——
> 使用者可在設定頁自報「帳戶總淨值（新台幣）」，第 3 條上限據此實際計算，
> **由長期 not_evaluable 轉為實際生效，可能開始擋下加碼建議**（見 `work/stock-desk-發布說明.md`）。
> 以下「現況」描述的是 FR-9 之前的狀態，且**在使用者尚未輸入淨值、輸入已滿 30 天未更新、
> 或任一部位無法估值時仍然成立**。券商 API（第 1 項）未做，帳戶現金與融資餘額仍無資料來源。

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

**進度更新（2026-08-02）**：Phase 8 FR-9 採解法方向 2（手動輸入帳戶總淨值）。六個前置問題已由 risk-compliance-officer 書面定案（分母選項 B、30 天失效／7 天提示、三檔防呆不靜默 clamp、僅存最新一筆、不新增絕對金額界、只收 TWD），全文見 `work/stock-desk-phase8-風控定調.md`，FR-9 前置閘門解除。

---

### 7. 外幣 FX 風控層已接線（原「尚未接 FX」已過時）

**已解決（獨立必修任務 FX1，dev-lead，commit `51a5eac`；qa PASS 2026-08-09，
`work/reviews/c1-phase8-review.md`「qa 終審 FX1+文案批」段）**：
- `app/api/advice.py` 的 `/api/advice/{symbol}` 端點已注入 `fx_provider`，經
  `resolve_fx_quote` 算出報價後傳入建議引擎的風控上下文（`backend/app/api/advice.py:31,43,54,81,106`）。
- `app/api/portfolio.py` 的 `/api/portfolio/limits`（FR-8，帳本層五條上限彙總）同樣逐檔注入 FX
  報價（`backend/app/api/portfolio.py:105,149`）。
- `app/advice/book.py::build_book_context` 據此算出 `fx_to_twd`（`backend/app/advice/book.py:582`），
  風控上限層與估值層現在讀同一份幣別轉換。
- 本次修復同時修正一個既有 bug（FX1）：`_position_rollup` 先前用原幣價直接填
  `position_market_value_twd`、未乘匯率，使美股持倉第 1 條上限（單一標的佔比）的比率系統性低估
  約 30 倍（`work/reviews/c1-phase8-review.md`「升級必修」段）；已修復並補回歸測試。

**仍存在的限制**：
- FX adapter 本身（`app/data/providers/fx.py`）仍未對照真實回應查證（見前一節「資料適配狀態」）。
- 「當日匯率」取的是即期買賣價的中點模型值，非官方收盤匯率（`fx.py:19-25`）。
- 僅支援 USD/TWD 一種幣別對；美股 adapter 若日後支援其他幣別，FX 層需要同步擴充。

**建議負責角色**：devops-sre（查證 FX adapter 端點）。

---

### 8. 回測策略已擴充為三種（FR-10/FR-11，原「僅 ma_cross」已過時）

**已解決（Phase 8 C1 批，dev-lead，commit `a8c3aba`；qa PASS，2026-08-09）**：
- `app/backtest/strategies.py` 現有三個內建策略：`ma_cross`（趨勢跟隨，原有）、`rsi_reversal`
  （均值回歸，FR-10，進場 RSI<30／出場 RSI 50 中線）、`breakout`（突破，FR-11，20 日新高進場／
  10 日新低出場，Turtle System 1 參數）（`backend/app/backtest/strategies.py:1-60`）。
- 前端 `BacktestForm` 策略下拉已接線三種策略（`work/dispatch/2026-08-09-frontend-wiring.md`
  「4 PASS」段：三策略數字互異、envelope 齊）。
- qa 審查確認 `_replay` 無 look-ahead、無跨折污染，RSI 抽取有 golden test
  （`work/reviews/c1-phase8-review.md`「通過」段）。

**仍存在的限制**：策略參數固定於模組常數，不開放使用者調參
（`strategies.py:17-18`，FR-10/FR-11 明訂範圍外）；不支援使用者自定義策略（原「解法方向 2」未做）。

**建議負責角色**：product-manager（是否需要開放調參或自定義策略，屬未來優先序評估）。

---

### 9. 警示規則已可修改（FR-1，原「無 PUT/PATCH 端點」已過時）

**已解決（Phase 8 C1 批，dev-lead，commit `91dbb37`；qa 兩輪退修後 PASS，
`work/reviews/c1-phase8-review.md`；風控 APPROVE，`work/dispatch/2026-08-09-frontend-wiring.md`）**：
- `PUT /api/alerts/{rule_id}`（整條替換）與 `PATCH /api/alerts/{rule_id}`（部分欄位）皆已實作，
  兩者都保留原 `rule_id`（`backend/app/api/alerts.py:108-153`）。
- 前端 `AlertRulesSection` / `EditAlertRuleModal` 已接線編輯表單，經等效實機驗收 PASS；過程中
  修復了一個 `Number("")===0` 陷阱（空字串門檻被誤存為 0）與 ref 型條件（欄位對欄位比較）的
  唯讀顯示（`work/dispatch/2026-08-09-frontend-wiring.md` commit `32188bd`、`155bdfd`）。
- 已產生的 `alert_events` 不受編輯影響，`rule_id` 不變，觸發歷史的對應關係維持
  （原「解法方向 3」已落實）。

**仍存在的限制**：新增規則表單（非編輯）有相同的「`buildAlertParams` 回 null 即靜默不送出」
寫法，尚未比照編輯表單修復，列為後續待辦（`work/dispatch/2026-08-09-frontend-wiring.md`
「BLOCKING 退修完成」段末「已知限制」）。

**建議負責角色**：frontend-engineer（新增規則表單同型修復，下批處理）。

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

7. ~~`RiskGauge` 五條 not_evaluable 為硬編碼~~ **已解決（FR-8，2026-08-09）**：`RiskGauge.tsx`
   已改接 `GET /api/portfolio/limits`（`backend/app/api/portfolio.py:99-157` +
   `backend/app/advice/book_limits.py`），逐條上限的 `status`/`observed`/`threshold`/`detail`
   皆原樣渲染自後端回應，不再是前端寫死的五個 `not_evaluable`
   （`frontend/app/components/RiskGauge.tsx:17-32,143-145`）。文案已完成四輪風控審查並 APPROVE
   定稿（`work/reviews/c1-phase8-review.md`「風控四輪確認」段）。

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

**2026-08-10 更新**：原表格中的 US adapter、產業欄位、FX 風控層接線、指數 adapter、
PUT/PATCH 警示端點、內建回測策略（RSI／突破）六項功能已於 Phase 7／Phase 8 交付，
移出功能待辦；下表為交付後仍剩餘的工作（多為「查證」而非「開發」）。

### P0（Must Have，已實作功能的正確性前提）
1. **查證美股／指數資料鏈**（`ALPHA_VANTAGE_API_KEY`、yfinance、`index_mapping.py` 12 檔
   mapped 序列代號）
   - Adapter 與對映表都已存在，但都標記 `verified=False`，且本沙盒環境無法連外驗證。
   - 查證方式：`apps/stock-desk/scripts/verify_market_data.py`（見
     `work/stock-desk-數據核實操作說明.md`）。
   - 負責角色：devops-sre / data-engineer（需在有網路的機器執行）。

2. **查證 FX adapter**（`app/data/providers/fx.py`）
   - 已接線至估值層與風控上限層，但端點與 CSV 欄位格式未對照真實回應查證。
   - 負責角色：devops-sre。

3. **查證台股產業別清單**（`app/positions/sectors.py`）
   - 37 類清單未對照官方 TWSE 資料查證。
   - 負責角色：data-engineer。

### P1（Should Have，顯著提升完整性）
4. **Kelly 準則實現**（見第 5 項限制）
   - 若 backtest 頻繁使用，可直接抽取 Kelly 輸入。
   - 否則可推遲至有交易日誌模組之後。

5. **槓桿 ETF 中 5 檔 unmapped 標的補齊指數來源**（`00631L`／`00632R`／`00680L`／`SOXL`／`SOXS`，
   見第 2 項限制）
   - 需先找到已查證的免費指數日線來源，屬資料來源問題。
   - 負責角色：tech-architect（評估新資料源）。

6. **新增警示規則表單同型修復**（`buildAlertParams` 回 null 即靜默不送出，見第 9 項限制）
   - 編輯表單已修復，新增表單尚未比照處理。
   - 負責角色：frontend-engineer。

### P2（Nice to Have，功能增強）
7. **使用者自定義回測策略**（長期願景）
   - 需沙箱、審核、版本控制等基建；優先度低。

8. **帳戶 API 整合**（券商現金、融資餘額；見第 6 項限制）
   - 折衷方案（使用者自報淨值）已於 Phase 8 FR-9 上線；券商 API 本身仍未做。
   - 長期理想狀態；短期已有文案提醒使用者自報範圍的限制。

9. **Codex 環境修復**（見第 11 項限制）
   - 加強 code review 質量；不是功能性的。

---

## 跨團隊協作點

**2026-08-10 更新**：US adapter、產業欄位、FX 風控層接線、指數 bars、警示規則編輯五項已交付
（見上方各限制項），下表移除已結案的決策點，僅保留仍待決或待查證的項目。

| 工作項目 | 涉及團隊 | 決策點 |
| --- | --- | --- |
| 美股／指數／FX／產業清單查證 | devops-sre、data-engineer | 需有網路環境執行 `verify_market_data.py` 等查證工具 |
| 5 檔 unmapped 槓桿 ETF 補指數來源 | tech-architect | 是否值得投入尋找新資料源；若需，優先序 |
| Kelly 計算 | tech-architect | 是否需要；若需，優先序 |
| 新增警示規則表單同型修復 | frontend-engineer | 比照編輯表單的修法即可，屬已知修法 |
| 風控文案審查 | risk-compliance-officer、tech-writer | 編製審查清單、落檔標準 |
| Codex 修復 | devops-sre | 環境配置 |

---

## 文件與代碼對照表

實地確認的代碼位置供後續追蹤（2026-08-10 對照 commit `273b27a` 更新；行號會隨時間漂移，
抽驗請以檔案內文定位而非只信任行號）：

| 限制項 | 現況 | 相關代碼檔 | 行數範圍 |
| --- | --- | --- | --- |
| 1. US adapter | 已接線，未查證 | `app/api/deps.py` | 89-94 |
| | | `app/data/providers/alpha_vantage.py` | 16-20（未查證聲明）、98,161（API key） |
| 2. 指數 bars + drag | 已接線，12/17 mapped，5 unmapped | `app/leverage/index_mapping.py` | 60,112（verified=False）、168-295（對映表） |
| | | `app/api/leverage.py` | 84-100（實際呼叫 load_index_bars） |
| 3. Metadata 未驗證 | 仍未解決 | `app/leverage/detect.py` | 44,87-88（verified_on=None, ALL false） |
| 4. 產業欄位 | 已實作（FR-12，TW-only） | `app/positions/models.py` | 73,91-92（sector 欄位、TW-only 驗證） |
| | | `app/positions/sectors.py` | 36-73,85-89（37 類清單、US 拒絕） |
| 5. Kelly 無來源 | 仍未解決 | `app/advice/limits.py` | 349-351（Kelly 上限預設值）、452（無來源說明） |
| 6. 總曝險無現金 | Phase 8 FR-9 折衷方案已上線（見第 6 項限制內文） | `app/advice/book.py` | 483,574（gross_exposure_twd 邏輯） |
| 7. FX 風控層 | 已接線（FX1） | `app/api/advice.py` | 31,43,54,81,106 |
| | | `app/api/portfolio.py` | 99-157（`/api/portfolio/limits`，FR-8） |
| 8. 回測策略 | 已擴充為三種（FR-10/FR-11） | `app/backtest/strategies.py` | 1-60 |
| 9. 警示規則編輯 | 已實作（FR-1） | `app/api/alerts.py` | 108-153（PUT/PATCH） |
| 10. 風控 7 項 suggested + 2 required | 第 7 項（RiskGauge 硬編碼）已解決，其餘未變 | `frontend/app/components/RiskGauge.tsx` | 17-32,143-145 |
| 11. Codex 缺席 | 仍未解決 | 環境級 | (sandbox 無外網憑證) |

---

## 更新日誌

- **2026-07-26**：修訂版；基於代碼實地確認，修正 FX 與 drag 的敘述，明確 required 項目的實裝狀態，更新優先序建議。
- **2026-07-28**：~~台股資料源首次真實環境驗證通過~~ **此筆記錄已撤銷**。查證結果：
  (a) 實測確認開發容器的網路政策無法連至 TWSE / FinMind / TPEx（三者皆遭代理拒絕，2026-07-28 重測仍然如此）；
  (b) CEO 澄清其瀏覽並非以 Docker 在本機執行；合理推斷（待 CEO 確認）其看到的是 E2E 驗收期間
  容器內伺服器經 Claude Code 網頁預覽呈現的畫面——該環境的資料為離線示範資料（`source=demo_synthetic`），並非真實台股行情。
  結論：**台股資料源至今仍未經任何真實環境驗證**，維持「待有網環境查證」狀態。
  教訓：查證紀錄必須附可觀測證據（來源徽章、後端 log）；「畫面上有數字」不構成驗證。
- **2026-08-12**（目錄同步首次真實網路驗證,CEO 本機執行,附終端輸出證據）：
  `app.directory.sync` 兩資料源皆 PASS——TWSE 上市 1379 筆、TPEx 上櫃 10,400 筆(含 ETF/債券 ETF),
  目錄總筆數 11,779。過程修正兩個推測錯誤:(a) TPEx 欄位名原推測為中文,實為英文
  `SecuritiesCompanyCode`/`CompanyName`(據 CEO 抓回的真實回應樣本修正,commit `1faac80`);
  (b) `--verify-sectors` 官方產業別欄回傳代碼非名稱,補代碼→名稱對照層(commit `f58bb9e`),
  覆核實測 32 項一致,差異 5 項經 CEO 裁決:存託憑證納入清單(commit `e4244f3`)、
  文化創意/綜合企業/農業科技/電子商務 4 項保留。上方 2026-07-28 的「待有網環境查證」狀態,
  就**目錄同步**部分至此解除;行情資料源(quotes/FinMind)與除權息 `app.dividends.sync`
  仍未經真實驗證,維持待查。
- **2026-08-12（續,除權息同步真實驗證通過,CEO 本機執行,附終端輸出證據）**：
  `app.dividends.sync` PASS——最終寫入 118 筆除權息預告事件,略過 6 列(官方資料標「權」
  但配股欄空白的內部不一致,依防禦規則拒收並計數揭露,屬設計預期)。過程修正:
  (a) 原推測端點 `TWT49U` 實測為死路(回 HTML 且不在官方 swagger 目錄),CEO 以 swagger
  探測+真實樣本確認正解為 `exchangeReport/TWT48U_ALL`(除權除息預告表),data-engineer
  據實測樣本重寫解析(commit `0c4e683`);(b) `Exdividend` 值域首版推測「息權」,CEO 實測
  全表分佈(息 102/權 12/權息 10)確認實際字序為「權息」,修正後該 10 筆正常收錄
  (commit `bac546a`)。
  重要特性與誠實界線:(a) 預告表僅含未來事件、無歷史回補→同步採逐次累積語意,
  需定期執行;(b) 現金股利可還原,股票股利(除權)因資料源不含換算所需參考價規則,
  本期僅記錄不計算,整筆事件誠實標示不還原;(c) 僅上市,上櫃未涵蓋。
  至此**資料同步 CLI 三項(目錄/產業覆核/除權息)全部經真實網路驗證**;
  行情資料源(quotes/FinMind/AV/yfinance/FX)仍未經真實驗證,維持待查
  (查證工具:`scripts/verify_market_data.py`)。
- **2026-08-16（產業別自動帶入真實驗證通過,CEO 本機執行,附終端輸出證據）**：
  目錄同步三段全 PASS——上市 1378/上櫃 10,489(目錄計 11,936);產業別寫入 1,094 列
  (官方 1,095 筆中 1 筆代號不在目錄,如實揭露未新增);持倉回填 4 檔個股
  (3037/2327/8046→電子零組件業、2330→半導體業),3 檔 ETF 依 fail-safe 跳過。
  第 2 條風險上限(單一產業佔比)自此對個股實際生效;限制清單 #4「台股清單未查證」
  隨 2026-08-12 產業覆核+本次落地全面解除。功能全鏈:dev(cf814a8)→qa PASS→
  併發加固(e8e291a)→風控三輪定稿(work/reviews/2026-08-16-產業別來源說明句-風控三輪.md)
  →落地(acf3de7)→留痕(b11241f)。
- **2026-08-10**（tech-writer，文件過期清償，對照 commit `273b27a` 逐項核實）：第 1、2、4、7、8、
  9 項與第 10 項第 7 小點原本敘述「尚未實作／尚未接線」，經逐檔讀 code 確認已於 Phase 7／
  Phase 8 交付並通過 qa/風控審查，已改寫為「已解決」並附目前限制範圍與代碼行號；第 3、5、11
  項與第 10 項其餘小點經覆核仍為現況，未變更。同步更新「後續工作優先序建議」「跨團隊協作點」
  「文件與代碼對照表」。另同批更新 `apps/stock-desk/README.md`（離線示範模式、資料適配狀態表、
  目錄同步啟動步驟）。

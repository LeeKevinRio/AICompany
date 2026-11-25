# 前端減字另案登記與前端折衷排程（product-manager）

- 日期：2026-11-25
- 依據：
  - `work/reviews/2026-11-25-前端減字三項逐字審RC712至RC718-風控.md`（以下稱「風控審」，RC-712～RC-718）
  - `work/reviews/2026-11-25-畫面簡潔易懂盤點-product-manager.md`（以下稱「盤點」）
  - `work/reviews/2026-11-25-high修正提前代價與前端折衷與ADR時點評估-tech-architect.md` 第 2 點（以下稱「TA」，:98-159）
- 守則：本檔不擬任何使用者看得到的字句。新字面一律標「字面待 creative-lead 起草、風控定稿」。
- 編號：下列「另案 A／B／C」是本檔內的暫稱，正式追蹤編號由 coordinator 加進追蹤清單時指派（我沒有查證追蹤清單現況）。
- 行號來自 2026-11-25 在 HEAD `fa9dd420` 的讀取，動工前要重對。

---

## 一、三個另案登記

### 另案 A（對應 RC-712 待決 2）：「例如 0.15 = 15%」例子與 `:98` 同批改

- 範圍
  - `apps/stock-desk/frontend/app/settings/SettingsForm.tsx:463`（風險預算區說明句內的「例如 0.15 = 15%」）。注意：RC-712 的定稿句會先改這一句（加「除 ATR 停損倍數外，」），本案在那之後接著改例子，兩案不可同時動同一行。
  - `SettingsForm.tsx:98`（單一標的佔比上限的欄位說明，現況為「（比例，例如 0.15 代表 15%）」）。
  - 只有這兩處在 `frontend/app`（排除測試）出現 0.15／15% 的畫面字面，Grep 確認。
  - 對應測試的逐字鎖定（RC-717 第 1 項會鎖第一句定稿全文）要同批更新，由 frontend-engineer 列出。
- 為什麼要做
  - 現行預設上限已是 0.10（`backend/app/settings/migrations.py` 把舊預設 0.15 遷移為 0.10），例子卻還是舊預設值 0.15，容易被讀成「建議值」。風控 2026-10-26 的 suggested 仍有效（`work/reviews/2026-10-26-第1條上限下修審查-風控.md:149`，我未重讀）。
  - 兩處是同一個例子，風控審 RC-712 要求同批改，避免互相不一致。
  - 不能只拿掉例子：拿掉後「分數」易被讀成「得分」（風控審 RC-712）。所以要換數字，不是刪除。
- 誰起草：creative-lead（只換例子數字，其餘不動；仍須遵守 RC-712「不得再用『每一項』全稱、ATR 停損倍數必須被排除」）。
- 誰審：risk-compliance-officer 逐字審，之後 qa-reviewer。
- 能不能在正式登記前合併：**能**（只動 frontend）。前提：
  - 比照 RC-718 的條件（修訂八流程、coordinator 書面確認 #156 期間尚未開始、backend 零差異）；
  - 必須排在 RC-712 定稿句合併之後，或與它同一個分支依序提交。
- 驗收條件
  - Given 設定頁的風險預算區，When 讀取 `:463` 的說明句與第 1 條欄位的 `:98` 說明，Then 兩處使用同一個換過的例子，且字面為風控定稿全文逐字相同。
  - Given 例子已更新，When 對 `frontend/app`（排除 `__tests__`）Grep `0\.15`，Then 沒有任何畫面字面殘留舊例子。
  - Given `:463` 句，When 檢查 ATR 停損倍數，Then 該句仍明確排除 ATR 停損倍數（RC-712 的約束不退步）。
  - Given diff，When qa 核對，Then 只動 `SettingsForm.tsx` 與對應測試；backend 零差異；沒有其他使用者可見字面變動。

### 另案 B（對應 RC-715）：後端 `UNVERIFIED_RATES_NOTE` 與 `RATE_PROVENANCE_NOTE`

- 範圍（碰 backend `app/`，**一律正式登記後才做**）
  1. `apps/stock-desk/backend/app/api/backtest.py:89-92`（`UNVERIFIED_RATES_NOTE`，含「verified_on 為 null」，Grep 確認在 `:90`）。
  2. 6 個 golden 檔：`backend/tests/golden/backtest/` 底下的 breakout、five_conditions、ma_cross、ma_cross__dividends_adjusted、ma_cross__insufficient_data、rsi_reversal（清單取自風控審，我沒有逐檔重 Grep）。
  3. `backend/tests/test_api_backtest.py:103` 用常數，風控審判定不用改。
  4. `backend/app/api/settings.py:110-113`（`RATE_PROVENANCE_NOTE`：「cost_model 的預設費率尚未經主要來源查證（verified_on 為 null）；查證後請更新 verified_on 與各項費率。」）。它被 `settings.py:461` 放進 `notes`（未查證時），測試在 `backend/tests/test_api_settings.py:16,46`。
- 為什麼要做
  - 只改前端（RC-712～718 那批）後，費率未查證時 notes 清單仍會出現「verified_on 為 null」。風控接受這段過渡，因為兩處都還揭露「未查證」。
  - 盤點 P1-3、P1-5：兩處費率句幾乎同字，重複出現。
  - `RATE_PROVENANCE_NOTE` 還指示使用者「查證後請更新 verified_on」。見下方查證，畫面上做不到這件事。
- **查證結果：使用者能不能在畫面上更新 `verified_on`？答案：不能。**
  - `SettingsForm.tsx:152`：`COST_FIELDS` 的型別是 `FieldSpec<Omit<CostModelSettings, "verified_on">>[]`，即欄位清單排除 `verified_on`。
  - `SettingsForm.tsx:429-436`：儲存時 `costModelPartial` 只收 `COST_FIELDS`，`verified_on` 一律 `settings.settings.cost_model.verified_on` 原值帶回，等於畫面送出時不會改它。
  - `SettingsForm.tsx:494-496`：`verified_on` 在畫面上只是唯讀徽章（「已查證（日期）」或「尚未查證」）。`:500-504` 另有一行未查證說明，字面沒有出現「verified_on」。
  - 前端其餘引用（`lib/types.ts:1002,1013`、`LeverageChapterView.tsx:82`、`types.ts:786,2562`）都是型別或別的模組的唯讀顯示，與費率的 `verified_on` 無關。
  - 未查證：後端 `PUT /api/settings` 是否接受由 API 直接改 `verified_on`（`backend/app/settings/models.py:75` 看到欄位有日期格式 pattern，但我沒有讀 PUT 路徑），以及是否有任何非畫面的更新途徑（例如改設定檔）。所以「查證後請更新」這句在畫面上無法照做，是已查證；「完全沒有途徑」不是。
  - 對本案的影響：這句不能只刪字，要重新決定「使用者查證後要怎麼做」。此題屬產品決策（要不要在畫面提供更新查證日的入口，或把這句改成不指示動作），**需 CEO 決定，我不替他決定**。
- 誰起草：creative-lead（`RATE_PROVENANCE_NOTE` 必須新擬；`UNVERIFIED_RATES_NOTE` 風控審已給有條件的只刪字定稿，到時要對照當時程式重新確認，且若 P1-3 決定把兩處費率句併掉，以那時的審查為準）。
- 誰審：risk-compliance-officer 逐字審；tech-architect 評估 backend 與 golden 影響；qa-reviewer 審 golden 重產。
- 能不能在正式登記前合併：**不能**（碰 backend `app/`）。
- 驗收條件
  - Given 費率未查證（`rates_verified` 為 false），When 產出回測報告，Then `notes` 清單仍含一句費率未查證的揭露（不得因減字而消失），且不含「verified_on」字樣。
  - Given 6 個 golden 檔，When 重產並比對，Then 差異只有該句字面，沒有任何數值變動。
  - Given `GET /api/settings` 在費率未查證時，When 讀取 `notes`，Then 其中的說明不再指示使用者做畫面上做不到的動作；若 CEO 決定要提供更新入口，則另開 PRD，不併入本案。
  - Given 費率已查證，When 產出報告與設定，Then 不出現上述未查證句（行為不退步）。
  - Given backend 測試，When 跑 `test_api_backtest.py`、`test_api_settings.py`，Then 綠燈。

### 另案 C（對應 RC-716）：警示事件其餘 10 個鍵與值的中文標籤

- 範圍
  - `apps/stock-desk/frontend/app/components/PendingAlertsPanel.tsx:7-15`（`ObservedValues`，目前直接印 `${key}: ${value ?? "—"}`，以「　」相連）。
  - 現有標籤來源：`lib/format.ts:493-497` 的 `signalFieldLabel`、`format.ts:461`「最新收盤價」、`SIGNAL_FIELD_OPTIONS`、`alertFieldEvaluability.test.ts:319`「大於（>）」（皆取自風控審，我沒有重讀）。
  - 「其餘 10 個鍵」的清單：風控審沒有列舉。由 frontend-engineer 先對 `engine.py` 實際寫入 `observed` 的鍵與值做清單（含 `op`、`field`、`violated_limit_ids`、`threshold`、`currency`、`bar_as_of`、`signals_as_of` 等）。這份清單是動工前置條件，我沒有查證 10 個鍵究竟是哪些。
  - RC-716 主案（只把鍵名轉成 `signalFieldLabel`、分隔與順序不變）已在 RC-718 那批前端合併，不屬本案。
- 為什麼要做：畫面上仍露出工程鍵名與值（盤點 P1-5）。
- 誰起草：creative-lead；frontend-engineer 先交鍵與值的清單，並標出哪些已有既有標籤。
- 誰審：risk-compliance-officer 逐字審（含版面調整）；qa-reviewer；涉及版面再加 qa-e2e（375／1280）。
- 能不能在正式登記前合併：**能**（只動 frontend），前提比照 RC-718；不得動 backend。起草與清單可立即開始。
- 必須遵守風控 RC-716 的四點約束
  1. `bar_as_of`、`signals_as_of` 一定留在畫面上；標籤要讓人看出是「資料的日期」，與觸發時間分開，也不能暗示即時資料。
  2. **值**也要處理，不只鍵名：`op` 的 `gt`、`field` 的 `rsi14.last`、`violated_limit_ids` 的 id。有既有標籤優先用。
  3. 若要拿掉與後端 message 重複的值（收盤價、門檻、幣別），前提是資料日期仍看得到，且版面調整也送風控。**案 C（整個拿掉）已被否決，不得帶入任何分支**。
  4. 「最新收盤價」放在事件列可能被讀成現在的最新價（事件可能放了好幾天才處理），起草時一併評估；這點不擋本案。
- 驗收條件
  - Given 任一種警示事件（價格門檻、signal_condition、限額違反各一），When 事件列渲染，Then 每個鍵與每個值都顯示為風控定稿的中文標籤，畫面上不出現原始鍵名（`rsi14.last`、`gt`、`violated_limit_ids` 等）。
  - Given 事件的 `observed` 含 `bar_as_of` 或 `signals_as_of`，When 渲染，Then 該日期仍出現，且標籤標明是資料日期。
  - Given 事件有 N 個項目，When 渲染，Then 項目數量與順序不變，沒有任何 `filter` 掉項目的寫法。
  - Given 把標籤改回舊字，When 跑測試，Then 逐字鎖定測試變紅（延續 RC-717 第 4 項的防護）。
  - Given diff，When qa 核對，Then backend 零差異。

---

## 二、前端折衷排程建議（TA 第 2 點）

來源：TA `:98-159`。四項都是只動 frontend，不需要 CEO 決定（TA `:222`）；是否把 backend high 修正提前到登記前，是另一題，需 CEO 決定，不在本節。每項都要新字面、每項都要 qa 加 qa-e2e（375／1280）（TA `:98`）。

### 排序（依使用者價值與風險）

| 順位 | 項目 | 使用者價值 | 風險 | 與盤點合併 |
|---|---|---|---|---|
| 1 | RC-695（收起技術分析區） | 高：壞值時畫面印出離譜數字（TA 舉例「收盤 -1.00」），CEO 會直接讀到錯誤結論 | 中：後端仍回數值，前端只能不顯示，不能更正 | 合併 P0-4（RC-693／695 本體在內，與 P0-4 a、b 對齊同一判斷）。共用同一個判斷函式 |
| 2 | H1（關鍵價位拒算與決策卡加註） | 高：單日跳空會讓停損與動作失真；但只適用台股、可能多拒算 | 中高：要定門檻（與 ADR-0016 F7、`sectors/definition.py` 兩個定義對齊或說明差異）；ADR-δ 要先落檔才能實作（TA `:36,182`）；決策卡動作是後端算的，只能加註 | 與 P0-4 b（決策卡「—」補原因句）同一張卡、同一批字面；與 RC-695 共用判斷函式 |
| 3 | F1／F2（首頁狀態 B） | 中：目前放心句在排程根本沒跑時也會出現（TA `:108` 沒有任何訊號代表排程輪跑過）。F1 涵蓋所有成因 | F1 低；F2 中，只涵蓋摘要失敗，涵蓋面窄 | 與盤點 P1-7（RC-650／654 同類）併單；與 P0-5（首頁風險儀表）同屬首頁，可同一個前端分支批次審 |

說明
- 排序理由：RC-695 與 H1 是「畫面給出看似正常、實際失真的數字」，風險直接落在 CEO 判斷上；狀態 B 是「放心句可能不真」，屬於歸因問題，影響較間接。這是我依 TA 的事實做的判斷，順序若與風控、TA 想法不同，以他們為準。
- RC-695 先於 H1：兩者共用判斷函式，先落地壞值判斷，H1 只需加跳空條件；而且 H1 要等 ADR-δ。
- F1 與 F2：F1 優先（涵蓋全部成因、順帶處理 RC-654「查詢時間不是檢查時間」）；F2 是否追加，建議等 F1 後再決定，因為涵蓋面窄、要多讀一個 query。TA 說兩者可併做、工時各為中。
- 注意 α2 落地時，狀態 B 字面要再換一次、風控要審兩輪（TA `:115`）；所以 F1 字面請設計成短期過渡。
- TA 另指出：前端折衷要合併在 G_acc 之前才確定不影響驗收，受「新發現 A」6(d) 讀法拘束（TA `:96`）。讀法未定案前，F1／F2、H1、RC-695 都不要合併；起草與清單可先走。我沒有讀該讀法的內容。

### 各項 Given/When/Then

新字面一律：**字面待 creative-lead 起草、風控定稿**（我不擬）。

**F1（狀態 B 不看訊號）**
- Given 首頁警示狀態列處於「沒有待處理警示」的狀態 B，When 渲染，Then 不顯示放心句，也不顯示會被讀成檢查時間的「查詢時間」（或改標，字面待 creative-lead 起草、風控定稿）。
- Given 狀態 A／C／D／E 等其他狀態，When 渲染，Then 行為與字面完全不變。

**F2（代理訊號）**
- Given 首頁持倉摘要查詢回 `isError`，When 渲染警示狀態列，Then 不顯示狀態 B，改顯示一行中性句（字面待 creative-lead 起草、風控定稿）。
- Given 摘要查詢成功，When 渲染，Then 行為與 F1 相同；且不多發請求（共用 cache）。

**H1（關鍵價位拒算與決策卡加註）**
- Given 台股標的日線視窗內有單日跳空超過門檻（門檻待 ADR-δ 與 data-engineer 查證），When 渲染個股頁，Then 關鍵價位面板拒算，並顯示新原因句，不沿用「沒有可用日線資料」（字面待 creative-lead 起草、風控定稿）。
- Given 同一情形，When 渲染決策卡，Then 停損格隨之拒算，並顯示條件式加註（字面待 creative-lead 起草、風控定稿）；動作與命中規則仍照後端輸出，不被隱藏。
- Given 沒有跳空，When 渲染，Then 關鍵價位與決策卡與現況逐字相同。
- Given 非台股標的，When 渲染，Then 不啟動跳空偵測。
- Given 推播、排程台、回測、事件研究、Kelly，When H1 上線，Then 行為不變（本項只動畫面）。

**RC-695（收起技術分析區）**
- Given `bars.data.bars` 內任一根 close／high／low 非有限或 ≤ 0，When 渲染個股頁，Then 技術分析的圖、一句結論、指標列、指標面板整組收起，改顯示一句原因（字面待 creative-lead 起草、風控定稿）；一句結論不再印出「收盤 -1.00」類數字。
- Given 日線全部正常，When 渲染，Then 技術分析區與現況逐字相同。
- Given 壞值情形，When 同頁的關鍵價位、決策卡渲染，Then 三處採用同一個判斷口徑，不出現同屏一邊「有 N 根日線」、一邊「沒有可用日線」的矛盾（盤點 P0-4 a）。

### 與 P0／P1 的合併建議

- 單一前端分支 1：RC-695 + 盤點 P0-4 a、b + 技術分析一句結論（RC-693／695 本體）。共用判斷函式，字面一次交 creative-lead，風控一次審。
- 單一前端分支 2：H1。等 ADR-δ 落檔後再實作（TA `:182`），可與分支 1 共用函式，但風險不同，建議拆開審。
- 單一前端分支 3：F1（+ 之後的 F2）+ 盤點 P1-7 + P0-5（首頁）。字面同一批審。
- 不建議合併進折衷的：P0-1、P0-2、P0-3（碰 backend 或需 quant 先定算法）、P1-1～P1-4（重複整併，需風控先判定「合併是否滿足原核可條件」）。

---

## 三、P1「狀態詞彙表」獨立任務（盤點 P1-6）

### 範圍
- 目標：把「算不出來／資料有問題／沒有這筆」三類狀態，從目前五個詞（無法評估、無法判定、無法估值、資料不足、無法計算）及相關說法，定成一張對照表，全站依表替換。
- 現況對照（盤點 P1-6 表）：
  - 上限算不出：`lib/format.ts:334`、`riskRemediationWording.ts:86`；後端 `limits.py:411,442`、`kelly_wording.py:333-335,379-381`。
  - 六項條件：`entryObservationWording.ts:26,118,123,128`。
  - 部位估值：`oneLinerWording.ts:130,140`、`valuationWording.ts:22-33`、後端 `book.py:191`、`gate_wording.py`。
  - 資料來源取不到／日線不足：`DataMetaStatusBadge.tsx:128,163`、`InsufficientPanel.tsx:9`、`adviceWording.ts:53`、`format.ts:344,353`。
  - 某格算不出：`decisionCardWording.ts:76`、`KeyLevelsPanel.tsx:110,229,299`、`adviceWording.ts:221`、`quantityAbsenceWording.ts:61`。
  - 「—」的意思：`entryObservationWording.ts:65`、`KeyLevelsPanel.tsx:68-69`、決策卡沒有定義（S-1）。
  - 盤點未讀完的區域（`AdviceCardView`／`LimitsCheckList`、`PriceLadder`、庫存頁、`playbook/`、槓桿專章、`AlertRulesSection`、`DataSourcesSection` 全文、`playbook/wording.py`、`sectors_wording.py`、`gate_wording.py`）不在現有對照內，動工前要補盤。
- 做法分三階段（按此順序，不得跳過）
  1. 詞表定案：PM 與 creative-lead 列出狀態清單，creative-lead 提每個狀態用哪個詞；risk-compliance-officer 審**這張表**（不逐句審）。tech-architect 確認後端狀態代碼（`not_evaluable`、`unavailable` 等）與詞表的對應，不改代碼值。
  2. 前端替換（可在正式登記前做，只動 frontend）：`format.ts:334`、`entryObservationWording.ts:26`、`DataMetaStatusBadge.tsx:128` 等。
  3. 後端字面替換（正式登記後才做，碰 backend `app/`）：`limits.py`、`book.py`、`kelly_wording.py`、`api/settings.py:150` 等；其中大量是風控核可句，需風控逐句判定。
- 不在範圍：
  - 不改狀態判定邏輯，也不改 API 欄位值（只換顯示字面）。
  - 不處理 P0-4 的「壞值」歸因新字面（那是 P0-4 的另案）。
  - 不動 RC-556 除權息句。
  - 不處理風控因避禁用詞而刻意用英文欄位名的地方（`KellyInputsSection.tsx:63-71`，盤點 P1-5），除非風控同意。
- 為什麼單獨立案：跨前後端、跨大量風控核可句，夾在 P0 修正裡會拖慢 P0（盤點 P1-6、登記建議 3）。
- 誰起草：creative-lead（詞表）；frontend-engineer（替換清單與測試連動）；backend 階段由實作部門依 tech-architect 評估。
- 誰審：risk-compliance-officer（詞表、後端核可句）；qa-reviewer；涉及畫面再加 qa-e2e。
- 能不能在正式登記前合併：階段 1、2 能（階段 2 比照 RC-718 條件）；階段 3 不能。

### 驗收條件
- Given 詞表定案，When 檢視全站使用者可見字面，Then 同一狀態（上限算不出、條件算不出、部位無法估值、資料來源取不到、日線根數不足、壞值）各只用詞表指定的一個詞，且詞與詞之間意思不重疊。
- Given 「資料不足」一詞，When 全站 Grep，Then 它只用在詞表指定的那一種狀態；「來源取不到」與「根數不夠」用不同的詞（盤點 P0-4 c）。
- Given 畫面上的「—」，When 出現在六項條件、關鍵價位、決策卡，Then 三處的意思在畫面上有一致、可見的說明（決策卡 S-1 解決）。
- Given 前端替換完成，When 跑測試，Then 逐字鎖定測試更新後全綠，且改回舊字會變紅；既有風控核可句只有被詞表授權的部分被改動，其餘逐字不變。
- Given 後端替換完成，When 跑後端測試與 golden 比對，Then 差異只有字面；`not_evaluable` 等代碼值不變。
- Given 風控審詞表，When 有任何一個狀態被改成讓使用者少看到揭露，Then 風控否決，該項不得合併。

---

## 開放問題

1. 另案 B：是否要在畫面提供更新費率查證日的入口，或把「查證後請更新」句改成不指示動作？需 CEO 決定（影響 `RATE_PROVENANCE_NOTE` 起草方向）。
2. 另案 B：後端 `PUT /api/settings` 是否接受由 API 改 `verified_on`？問 tech-architect 或 backend 實作者。
3. 另案 C：observed 其餘 10 個鍵的確切清單？問 frontend-engineer。
4. 前端折衷：TA「新發現 A」6(d) 的讀法何時定案？問 coordinator／風控。
5. 風控審待決 5：RC-716 主案是現在做還是併入另案 C？我的建議：已隨 RC-718 那批前端合併（風控已 APPROVE，改善有限但沒有揭露減少）；不另等另案 C。若 coordinator 另有安排，以其為準。

# 第 1 條單一標的上限下修提案（#61）

- 審查者：quant-researcher
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# quant-researcher 提案：第 1 條單一標的上限下修（#61，配合 5-K 停用）

本次只用 Read、Grep 和唯讀的 Bash（sed、grep）。沒有寫檔，沒有讀 `.env` 或 `*.db`，也沒有跑測試或回測。

## 本次結論

1. **建議新預設值：所有標的一律 10%（方案 A）。** 停用第 5 條前，只要某標的有可用的 Kelly 輸入，它的上限一定不超過 `kelly_position_cap`，而這個值的硬上界是 0.10（`limits.py:563` 的 `le=0.10`）。所以 10% 是「不會讓這些標的變寬」的最大單一數字。12% 或維持 15%，都會讓原本卡在 10% 的標的變寬。分級（槓桿 ETF 更嚴）留到下一批再做，理由見下面的比較。
2. **單改預設值，對已經存檔的使用者沒有效果，#61 會落空。** `SettingsStore.save` 每次都把四個區段整份寫入（`settings/store.py:95-110`）。即使使用者只存過淨值或費率，`risk_budget` 也已經用 `max_position_weight=0.15` 明確寫進 DB 了（測試 `test_api_settings.py:550-555` 證明了這個行為）。改預設值只影響「從來沒存過任何設定」的安裝。所以要嘛把已存的值改掉，要嘛由使用者自己操作，兩者都需要 CEO 裁定（見 S1、S2、S3）。
3. **10% 不能讓「每個標的的上限都不高於停用前」完全成立。** Kelly 可用額度小於 10% 的標的（包括 edge 不是正數、額度 = 0、原本完全擋住加碼的標的），停用後上限反而會升到 10%。會變寬的時間是「該筆 Kelly 輸入剩下的有效期」：Kelly 輸入 30 天就過期（`limits.py:186` 的 `KELLY_STALE_AFTER_DAYS = 30`），過期後舊系統本來就會回到第 1 條，所以最多 30 天。要完全不變寬，就得加上方案 D（日落）：先凍結新輸入，等既有的值自然過期，再落地 5-K。
4. **不需要升 `rules_version`。** 它是規則 YAML 的版本（`advice/rules/default.yaml:33`，由 `engine.py:391` 輸出），與 RiskBudget 無關。如果採用 S2（揭露式遷移），另外需要一個遷移標記，而且不能放進 RiskBudget 欄位。
5. **5-K 有一個高風險的實作陷阱。** RiskBudget 設了 `extra="forbid"`（`limits.py:533`）。如果 5-K 把 `kelly_fraction_cap` 和 `kelly_position_cap` 從模型移除，DB 裡舊的 payload 會驗證失敗，整個 `risk_budget` 區段會靜默回到預設值（`store.py:116-128`，只寫一行 log）。使用者自訂的總曝險、單筆虧損等設定會全部被重設。

## 提案（方案比較）

### 方法論依據（沒有引用任何法規數字）
- **約束推導**：停用前，有可用 Kelly 輸入的標的，實際上限是 `min(第1條, min(max(f*,0)×kelly_fraction_cap, kelly_position_cap))`（`limits.py:951-960`），其中 `kelly_position_cap ≤ 0.10`。停用後，實際上限只剩第 1 條。要讓每個標的停用後的上限都不高於停用前，單一數字最大只能取 10%。
- **跳空與集中度的算術**：第 4 條（ATR 單筆虧損 1%）假設停損能在停損價成交，管不到跳空、跌停或流動性不足；第 1 條才是與波動估計無關的集中度防線。單一標的跌 d，帳本虧 w×d：
  - d = 30% 時，w = 15% 虧 4.5%，w = 10% 虧 3%；
  - d = 50% 時，w = 15% 虧 7.5%，w = 10% 虧 5%。

  這是情境算術，不代表發生機率。
- **分散度**：持股都頂到上限時，至少要 1/w 檔：15% 約 6.7 檔，10% 是 10 檔。
- **與第 4 條的關係**：第 4 條換算成權重是 `1% × close ÷ (2×ATR)`。ATR/close 為 2%、3%、5% 時，第 4 條允許的權重分別約 25%、16.7%、10%。也就是說，低波動個股原本是第 1 條在約束，下修會直接收緊這類標的。
- **限制**：10% 是政策參數，不是回測得來的，沒有任何樣本內擬合，也沒有歷史驗證。

### 方案比較

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| **A（建議）** | 所有標的一律 10% | 改動最小（一個預設值加前端顯示），規則好解釋；符合 #61「先下修第 1 條」 | 波及全部持股，不只 Kelly 標的；7～10 檔等權的帳本會「全部已違反」 | Kelly 額度小於 10% 的標的仍會變寬，最多 30 天；已存檔的使用者要搭配 S2 或 S3 才有效 |
| B（只收緊的分級） | 個股、ETF、期貨 ETF 10%；槓桿 ETF 為 10% ÷ \|倍數\|（例如 2 倍 → 5%） | 依曝險而不是依市值，方法上較正確 | `PortfolioContext` 沒有 instrument_type（`limits.py:1057` 自承）；instrument_type 是逐筆持倉欄位（`positions/models.py:35,142`），同一檔可能混合多種類型；候選標的沒有持倉，無從判斷類型，只能回退到最嚴的一級；要新增欄位、文案和測試，與目前的簡化方向衝突 | 由使用者自報類型，標錯就會放寬（可交叉比對 `leverage/detect.py` 的註冊表） |
| B'（ETF 放寬） | 寬基 ETF 給較高上限 | 符合常見的核心持股做法 | 違反 #61；系統無法穿透 ETF（`limits.py:243-260` 的殘餘風險揭露），也分不出寬基、主題、主動式 | **否決** |
| C | 12%，或維持 15% | 「已違反」的衝擊較小 | 原本卡在 Kelly 10% 的標的會變寬；等於 CEO 已經不選的 (a) 案 | **否決** |
| **D（日落，可與 A 併用）** | 現在就凍結 Kelly 匯入和手填（伺服器端拒絕）；既有的值繼續讓第 5 條計算到過期，所有可用的值過期後才落地 5-K 停用 | 唯一能讓所有標的都不變寬的做法；額外改動很少 | 5-K 最多延後 30 天；這段期間畫面上仍會出現單位有錯的數字（方向偏保守：產品算出的值不會大於正確公式算出的值）；與 5-K 定稿字面的時機要由風控重排 | 低 |

**建議組合**：A 加上 S2。再依 dev-lead 盤點的結果決定：
- 如果目前沒有任何可用的 Kelly 輸入，或可用的值都剛好是 10%：A 就足夠；
- 如果有任何一筆額度小於 10%：併用 D，或由 CEO 書面接受最多 30 天的殘餘放寬。

### 已存設定的處理

| 選項 | 內容 | 評估 |
|---|---|---|
| S1 | 只改預設值 | 已存檔的使用者維持 15%，等於放寬，不符 #61 |
| **S2（建議）** | 揭露式一次性遷移：只在已存值等於舊預設 0.15（以 EPSILON 比較）、而且還沒遷移過時，改成 0.10。另外寫一筆遷移紀錄（原值、新值、時間、依據 #61），設定頁和風險儀表都要顯示，可以隨時查到。使用者想調回 15%，走現有的放寬確認（`riskWidening.ts:37-41`）。其他自訂值（例如 0.12）不動 | 不是靜默覆蓋，而且可以稽核。缺點是分不出 0.15 是使用者刻意選的還是系統補的預設，所以要 CEO 裁定，揭露字面要送風控 |
| S3 | 不遷移，上線前由使用者本人到設定頁改成 0.10，5-K 的 merge 以 `GET /api/settings` 回傳值 ≤ 0.10 為前置條件 | 只有確定是單一安裝時才可行，靠人工操作 |

## 影響面清單（檔案:行號）

### 後端：下修後行為會改變的地方
- `apps/stock-desk/backend/app/advice/limits.py:536-545`：預設值 0.15 改成 0.10。pydantic 產生的 OpenAPI 預設值也會跟著變。
- `limits.py:141-150`（`MAX_POSITION_WEIGHT_CEILING = 0.50`）、`:473-503`（`_ceiling_message`、`_ceiling_description`）：不受影響，文字只引用上限 50%，沒有引用預設值。我不建議為 #61 調整硬上限：停用前使用者本來就能用 DELETE Kelly 輸入的方式脫離第 5 條，所以 10% 從來不是擋得住使用者自己的保證。這點交風控確認。
- `limits.py:1022-1045`：`_check_single_position_weight`。持股佔比在 [10%, 15%) 之間的，會從 passed 變成 violated（等於門檻也算違反，見 `_breaches` 在 `:1017-1019`）。
- `limits.py:1559`：`notional_caps` 第 1 條的額度從 0.15×equity 變成 0.10×equity。
- `limits.py:1655-1834`：`suggest_quantity_range`。
  - add：第 1 條是最緊的上限時，可加碼股數變少（例如 `_ctx()` 的上緣從 1,176 股變成約 555 股）；
  - reduce、stop_loss、take_profit：要賣的股數變多；
  - 持股在 10%～15% 之間的，加碼區間變成 None。
- `apps/stock-desk/backend/app/advice/engine.py:359-368`：持股 ≥10% 而規則結論為 add 的，改成 hold，並附上「加碼建議被第 1 條上限…擋下」（也就是 2-V、2-R、加碼被擋的字面會出現在更多檔上）。`:370` 的股數區間同步改變。`:316` 的 `RiskBudget()` 是 fallback，產品路徑會傳入已存的設定（`api/advice.py:168-169`）。
- 其他讀 `settings.risk_budget` 的路徑，會一起改變：
  - `app/api/portfolio.py:151,182`：帳本層、風險儀表；
  - `app/advice/book_limits.py:100,452,610,633`：threshold 照原樣往下傳；
  - `app/scheduler.py:391`、`app/api/alerts.py:209,216`：警示評估；
  - `app/api/kelly.py:1170`。
- `app/alerts/engine.py:296-351`：上限警示是「狀態型」（只要 violated 就觸發，受冷卻時間限制）。`limit_id` 為 `single_position_weight` 或 `any` 的規則，在 10%～15% 之間的持股上會開始觸發推播。

### 已存設定與儲存機制
- `app/settings/store.py:95-110`：`save` 每次寫入全部區段，所以預設值一旦被存過就固定下來，不會跟著程式改變。
- `store.py:116-128`：區段驗證失敗時，靜默回到預設值（這就是 5-K 陷阱的來源）。
- `app/settings/models.py:181-231`：`AppSettingsPatch.apply_to` 以區段為單位整份取代；如果送的是部分欄位，缺的欄位會回到模型預設，不是回到已存的值。
- `app/api/settings.py:375-390`：PUT 的流程是 load → apply_to → save。

### 前端
- `apps/stock-desk/frontend/app/settings/SettingsForm.tsx:85`：`defaultValue: 0.15` 改成 0.1。`:252` 會顯示「預設值：…」。`:84` 和 `:360` 的「例如 0.15」只是舉例，要不要改交給 creative-lead 和風控決定。
- `SettingsForm.tsx:122-132`：Kelly 兩個欄位（5-K 範圍）。`:333,352` 會把整份 `risk_budget` 送出。
- `frontend/app/lib/riskWidening.ts:37-41`：下修不會觸發確認，這是正確的；S2 之後如果使用者調回 15%，會觸發確認。
- `frontend/app/components/RiskGauge.tsx:176`、`frontend/app/lib/riskGauge.ts:36-38`：門檻從後端讀，進度條比例會變（例如 7% 持股從 47% 變成 70%）。

### 既有測試（靜態估計，最終以 pytest 實跑為準）
- 直接釘住預設值的，要改成 0.10：
  - `backend/tests/test_advice_limits.py:96`；
  - `backend/tests/test_api_settings.py:33,132,519,560,577`（後兩個是「損壞時回到預設值」的測試，回退後變成 0.10，方向更保守）。
- 用 `BUDGET = RiskBudget()`（`test_advice_limits.py:56`）測第 1 條機制的測試：`:222-226`（150,000 剛好等於 15%）、`:1401-1411`（1,176 / 588）、`:1414-1416`、`:1429-1439`（589）、`:1625`（basis 字面「588 ~ 1,176」），以及 `:1478`、`:1493`、`:1511`、`:1545-1546`、`:1703`、`:1815-1816`、`:1869` 要逐一確認哪條是最緊的上限。
- `backend/tests/test_advice_book.py:420-442`（984 股、「14.38% < 15%」）。
- 下列檔案也都用 `RiskBudget()` 預設，佔比落在 10%～15% 的 fixture 可能翻轉狀態：`test_advice_engine.py`、`test_advice_book_limits.py`、`test_adr0023_own_unvalued.py`、`test_alerts_snapshot.py`、`test_x3c_currency_market_mismatch.py`、`test_playbook_rebalance.py`、`test_f9b_*`、`test_rk4*`。
- `backend/tests/alerts_helpers.py:138`：只有 docstring 寫「15% cap」。fixture 本身是 30% 和 5%，不受影響。
- 前端 `riskWidening.test.ts:177` 用的是字面值 0.15 → 0.2，不依賴預設，不受影響。

### 文件
- `work/stock-desk-產品說明.md:340,495` 寫了「預設 15%」。

## 給 dev-lead 的實作約束（可逐條檢查）

1. `limits.py` 的 `max_position_weight` 預設改成 `0.10`，旁邊寫註解記錄依據：#61（2026-10-26）、風控審查檔路徑、本提案。`MAX_POSITION_WEIGHT_CEILING` 不動。
2. `SettingsForm.tsx:85` 的 `defaultValue` 和後端同步改成 `0.1`。另加一個測試，斷言前後端的預設值相等，或至少各自釘住 0.10。
3. 已存設定依 CEO 裁定的 S2 或 S3 處理。不得在沒有揭露的情況下改寫任何已存值；也不得在評估時用 `min(已存值, 0.10)` 偷偷夾住，因為這違反 `limits.py:518-523` 的「不夾值」原則。
4. 如果採 S2：
   - 遷移標記放在獨立的資料列或資料表，不得加進 RiskBudget 欄位（會出現在 PUT body 裡，使用者可以竄改）；
   - 只遷移等於 0.15 的值，其他值不動；
   - 遷移紀錄包含原值、新值、時間、依據；
   - 多次啟動結果相同（idempotent）；
   - 要有測試涵蓋：已存 0.15 → 0.10 並留下紀錄、已存 0.12 不動、從沒存過 → 0.10、第二次啟動不再改。
5. **5-K 不得從 RiskBudget 移除 `kelly_fraction_cap` 和 `kelly_position_cap`**（`extra="forbid"`，`limits.py:533`），否則舊 payload 會讓整個區段靜默回到預設值。保留欄位、標記為已停用。要有測試：含 Kelly 欄位的舊 payload，load 之後其他欄位都保持原值。
6. 第 1 條機制測試的處理方式：測試主旨本來就隱含 15% 的，改成明確傳 `RiskBudget(max_position_weight=0.15)`。被測的行為和斷言都不改，依據是 ADR-0023 風控判準 (3)（`docs/adr/0023-…md:362`）。另外新增以 0.10 預設值為準的案例：剛好 10% 是 violated、9.99% 是 passed、add 上緣的股數。不得為了讓測試通過而改斷言數字。
7. 合併前，dev-lead 用唯讀查詢盤點並回報：
   - (i) 目前可用的 Kelly 輸入檔數，`age_days < 30`；
   - (ii) 每檔的 `kelly_allowed_weight`，分成 =0、(0,10%)、=10% 三組，附各自的到期日；
   - (iii) 已存的 `max_position_weight` 值；
   - (iv) 佔比在 [10%,15%) 的持股檔數。
8. 與 5-K 同一批落地，順序是：先讓第 1 條生效（含已存值的處理），再停用第 5 條。不得出現只有一半落地的中間版本。
9. 5-K 的連帶事項：
   - 停用後第 5 條不得算進 `violated`（`engine.py:360`）；
   - 不得算進警示 `any` 的評估（`alerts/engine.py:296-304`）；
   - 不得出現在 `suggest_quantity_range` 的「缺少可用資料」句子裡（`limits.py:1720-1735`）。原因是停用不等於缺資料，這句的寫法交風控定。
10. 不升 `rules_version`（`rules/default.yaml:33`）。在 changelog 或 limits.py 的註解記錄這次預設值變更。

## Kelly 輸入既有值的處理（問題 4）
- **保留不刪**：`kelly_inputs` 資料表和匯入嘗試紀錄（`app/kelly/store.py`、`app/kelly/attempts.py`）留作稽核，嘗試次數也是多重比較的證據。
- **不使用**：第 5 條改回「已停用」狀態，不讀這些值，不參與 `notional_caps` 和數量區間。
- **伺服器端也要凍結**，不能只停用前端按鈕：
  - `POST /{symbol}/import-backtest`（`api/kelly.py:1346`）和 `PUT /{symbol}`（`:1178`）回明確的停用錯誤，避免匯入嘗試次數繼續累積；
  - `DELETE`（`:1220`）保留，那是使用者自己的資料；
  - `GET` 可以保留，但要標示「已停用」。
- **日後如果恢復**：所有停用前的值一律作廢，不得沿用。理由有三：
  - 公式單位要改，同一個值意義已經不同；
  - 回測成交假設預計改成隔日開盤，舊的匯入值本來就要重跑；
  - 30 天後自然過期。

  建議恢復時只接受恢復日之後建立的輸入。

## 使用者會看到的變化（事實清單，交風控審）
1. 佔比在 [10%, 15%) 的持股，第 1 條從「通過」變成「已違反第 1 條上限：單一標的佔比 12.00%（上限 10.00%）」。剛好 10% 也算違反。
2. 這些持股如果規則結論是加碼，會改成續抱參考，並附「加碼建議被第 1 條上限（單一標的佔比上限）擋下。」
3. 減碼、停損、停利的股數區間會出現或變大（要賣到 10% 以下）；加碼區間變小或消失；候選標的的試算買進股數變少。
4. 設定了 `single_position_weight` 或 `any` 上限警示的人，會收到新的推播。
5. 風險儀表的門檻顯示變成 10.00%，進度條比例變大。
6. 7～10 檔接近等權的帳本，每一檔都會是「已違反」，加碼參考全部被擋（第 1 條的分母不含現金）。這會讓「已違反」變得到處都是、失去辨識度。
7. 第 1 條的 detail 句子不會說明門檻改過；如果採 S2，使用者的設定值會被改，需要揭露。
8. Kelly 額度 = 0 的標的（原本因為 edge 不是正數而一律違反、擋住加碼），停用後可以加碼到 10%；額度在 (0,10%) 的標的上限也會變寬。這是方案 A 唯一會變寬的地方。
9. 過去的警示事件和卡片，保留當時的 15% 字樣，不會回頭改寫。

## 需要風控、CEO 處理的事項

**CEO**
1. 選擇方案：A（建議）、A+D，或 A 加上書面接受最多 30 天的殘餘放寬。依據是 dev-lead 盤點的第 7 點 (ii)。
2. 已存設定的處理選 S2（建議）或 S3，S1 不符 #61。S2 會改寫一個可能是使用者刻意選的 0.15，需要書面同意。
3. 確認不為 #61 調整 `MAX_POSITION_WEIGHT_CEILING`（0.50）。

**風控**
1. 審查 10% 這個數字和它的依據；確認 B'（ETF 放寬）維持否決。
2. 需要的揭露字面（由 creative-lead 起草）：
   - S2 的遷移告知；
   - 「第 1 條預設已下修」的說明，要不要出現、出現在哪裡；
   - 「已違反」大量出現時的說明，以及第 6 點的辨識度問題要不要處理；
   - `SettingsForm.tsx:84,360` 的「例如 0.15」要不要改。
3. 如果採 D：5-K 定稿字面（「已停用，不參與任何判斷」）的上線時機要重排；日落期間 Kelly 輸入區要顯示「暫停新輸入」的字面。
4. 停用後，數量區間「缺少可用資料」句子裡排除第 5 條的寫法（約束 9）。

**未驗證事項**：可用 Kelly 輸入的檔數和額度分布、已存的 `max_position_weight` 實際值、佔比在 10%～15% 之間的持股數，都需要讀 DB，我沒有驗證。測試影響是靜態估計，以 pytest 實跑為準。

## 相關檔案
- /home/user/AICompany/apps/stock-desk/backend/app/advice/limits.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/settings/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/settings/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/settings.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/kelly.py
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py
- /home/user/AICompany/apps/stock-desk/frontend/app/settings/SettingsForm.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/riskWidening.ts
- /home/user/AICompany/apps/stock-desk/backend/tests/test_advice_limits.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_api_settings.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_advice_book.py
- /home/user/AICompany/work/reviews/2026-10-26-風控五項整改字面逐字審-風控.md
- /home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md
- /home/user/AICompany/docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md

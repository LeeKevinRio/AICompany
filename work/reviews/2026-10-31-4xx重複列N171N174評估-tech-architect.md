# Q2 4xx、重複 EMERGENCY 列、N-171、N-174 技術評估

- 審查者：tech-architect
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 評估：Q2 的 4xx、重複 EMERGENCY 列、N-171、N-174

## 一、本次結論

先說明我能做到的範圍：我只有讀檔與搜尋工具，沒有執行任何程式或測試。下文的「讀碼判定」都是讀碼的結論；「已驗證」只用在 repo 裡已有測試釘住的行為，而且那些測試我也沒有跑。

1. **Q2（4xx 是否等於零寫入）：可以保證，附三個前提。** 在現行程式碼中，`POST /api/playbook/emergency-exit` 所有可能的 4xx，都在端點函式與它的 dependency 執行之前產生，所以這次請求沒有寫入任何東西（包括 playbook 狀態、指令列、價格快取與額度帳）。三個前提：
   - (a) 出清路徑上不出現 `HTTPException`。現況：全 app 只有 5 個 api 模組有，playbook 沒有。
   - (b) 遵守 ADR-0033 C-6（不得回任何 4xx）。
   - (c) 前端與後端之間沒有反向代理。
   - 但要注意：4xx 只代表「這次請求」零寫入，不代表「目前沒有待執行的出清指令」，因為先前那次可能已經寫入。若要為 4xx 另立字面，必須限定在「這次送出」，並送風控審。
2. **重複 EMERGENCY 列（CEO-2）：建議先用唯讀查詢盤點數量，再採「不清＋讀取側去重」。** 重複列不會造成現金重複入帳，也不會重複扣股數，因為有 `min`／`max` 保護。會翻倍的是：結算當次的 executed 計數、結算清單的行數，以及 R16 日誌裡多出一筆「executed 但實際移動 0 股」的列。刪除列我標 **VETO**。
3. **N-171：可以做，規模中等。** 做法是 `/today` 新增一個獨立欄位，條件與 C-4 的覆蓋條件完全相同。
   - 這個欄位能分辨 Q5 的 (ii)／(iii)，但只在 T+1 結算前、且有 open 批次時成立。
   - 它會讓 NB-6 第 2 句過時，所以要回審。
   - 排序建議：**N-166 → N-171 → N-168**。N-168 已因 N-172 定調而暫停，N-171 不依賴 F5。
4. **N-174：推定部分成立。**
   - 「結算不看模式」成立。
   - 「與 FROZEN_NOTE 矛盾」只在一種子情境成立：同一個 data_date 重複評估，第二次翻成防守或 S3。
   - 這個子情境的根因與 N-172（F5）相同，不是 N-168 的出清型問題。B-2a 戳記不能直接套用，建議併入 N-172 一起設計。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### Q2：出清的 4xx 來源逐一判定（全部為讀碼判定）

先排除會回 4xx 的應用層邏輯：
- 端點只有一個 dependency 參數：`api/playbook.py:536-539`。
- 這個 dependency 沒有任何參數：`api/deps.py:341-343`。
- 端點沒有 query、header、body 參數，所以 FastAPI 不會解析 body，**不可能出現 422**（RequestValidationError）。送任何 body 都會被忽略。
- 全 app 只有 `api/{settings,kelly,positions,alerts,leverage}.py` 用到 `HTTPException`，playbook 的 api、service、store 都沒有（grep 結果）。
- 沒有任何自訂 `exception_handler`（grep 結果為 0）。

| 來源 | 狀態碼 | 發生位置 | 寫入前？ |
|---|---|---|---|
| 缺 `X-Stock-Desk-Client` header | 403 | `client_header.py:40-58`，是純 ASGI middleware，不讀 body、不進 router | 是，零寫入。**已驗證**：`tests/test_client_header.py:52-58` 用 `_ExplodingService`（`:21-25`）釘住「沒有碰到 service」 |
| body 驗證 | 422 | 不存在（理由見上） | 不適用 |
| 路徑錯誤 | 404 | Starlette router 找不到路由 | 是，endpoint 與 dependency 都沒有執行 |
| 方法錯誤 | 405 | router 路徑相符但方法不符 | 是 |
| CORS 預檢被拒 | 400 | `main.py:64-69` 的 CORSMiddleware，只針對 OPTIONS | 是；而且瀏覽器根本不會送出 POST。前端拿到的是 fetch 例外，被歸類成 status 0 的網路失敗（`frontend/app/lib/api.ts:179-181`），不是 4xx |
| HTTP 格式錯誤、header 過大 | 400／431 | uvicorn／h11，在進入 app 之前 | 是 |
| dependency 建構失敗（store 遷移） | 500，不是 4xx | `deps.py:321-328` | 不屬於 4xx |
| 回應模型驗證失敗 | 500，不是 4xx | 由 `server_error.py:44-59` 送出 | 不屬於 4xx |

前端的 4xx 只會來自真實的 HTTP 回應（`api.ts:183-195`），而且是直連後端（`api.ts:46`），沒有經過 proxy。

**結論：在三個前提下，「4xx 等於本次請求零寫入」成立。**

建議 dev-lead 補兩條守門測試：
- OpenAPI 中這個端點的 responses 不含 422；
- playbook 的 api、service、store 都不 import `HTTPException`。

#### Q2-bis：既有重複 EMERGENCY 列（讀碼判定）

**現況程式仍是 N-166 之前的版本。** 證據：
- `service.py:837-868` 仍是兩個獨立 transaction；
- 回應模型 `api/playbook.py:263-277` 還沒有 `pending_directives`。

**對結算與帳冊的實際影響：**

同一個 (symbol, batch_no) 有兩列 `settled=0` 的 EMERGENCY 賣單時：
1. `settle_pending` 依 id 順序處理，每列各自被 claim（`store.py:883-898`）。
2. 第一列：`moved=min(remaining, shares)` 等於 N，現金入帳一次，批次 `remaining=0` 並轉 closed（`store.py:942-949`）。
3. 第二列：`moved=min(0, N)=0`，現金不變，批次維持 closed。
4. emergency_exit 不寫 schedule 列，所以 `_mark_schedule` 是 no-op。

**不會重複的部分：** 不會重複賣出，不會重複入帳，closed 批次也不會被重新開啟（只有 planned 批次會被買進，見 `engine.py:699-711`）。

**會翻倍的部分：**
- 結算當次 `SettlementResult.executed` 與 `SETTLEMENT_SUMMARY`（`service.py:303-313`）；
- `settlement.settled` 清單的行數；
- 尚未結算前，每天的 `settlement.unsettled` 都會列兩行；
- R16 日誌（`store.py:784-824`）永久留下第二筆 status=executed、帶 settled_open_price，但實際移動 0 股的列。目前沒有任何 API 對外提供 `directive_log`（grep：只有測試用），所以使用者看不到這部分。

**跨日重複**（第一天的指令沒抓到開盤價、第二天又出清，兩列的 execution_date 不同）：先有開盤價的那一列移動股數，現金仍只入帳一次。

**N-166 合併後，這些舊列的行為：**
- C-4 用「存在」判定覆蓋，所以舊的未結算重複列仍算覆蓋，不會再新增列，這是正確的。
- 但如果 `pending_directives` 照列直接輸出，會列出兩行。風控已要求 S1／S2 的佔位符以批次去重、股數用 remaining_shares 計算（風控 N-166 審查 `:89-90`）。N-171 的欄位也有同樣問題。
- 已結算（`settled=1`）的舊重複列，對新邏輯完全沒有作用。
- ADR-0033 方案 (e) 的 partial unique index（`WHERE ... settled=0`）只有在「仍存在未結算的重複列」時才建不起來。這些列會在下一次有開盤價的結算時自然消化。

**清理方案比較：**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (a) 不清＋讀取側去重（建議） | 不碰 R16；未結算的重複列會自然消化；零遷移 | 每個新的讀取端都要記得去重 | 用單一 store 讀取方法加守門測試收斂 |
| (b) 一次性標記遷移：未結算重複列中除最小 id 外，改為 `settled=1`＋新狀態值 | 可以啟用 (e) 縱深防禦 | 要新增 `DirectiveStatus`（`models.py:47`），前端 union 與 label 要同步，要送風控定字面；跨日重複該留哪一列，在 R10 下無從得知 | 若只處理 execution_date 相同的重複列則可行；若在啟動時自動執行，必須 `BEGIN IMMEDIATE`、冪等，且應先 dry-run |
| (c) 刪除重複列 | 資料最乾淨 | 違反 R16 留存 | **VETO** |
| (d) 改寫已結算列的 status | 帳面正確 | 改寫已經回報給使用者的歷史 | **VETO** |
| (e) 在遷移中無條件建 partial unique index | 縱深防禦 | 舊 DB 有重複列時建 index 失敗，啟動後所有端點都會 500 | **VETO（無條件版）**。盤點確認零未結算重複列之後才能建，而且失敗時要 fail-soft |

**盤點用的唯讀查詢**（交 CEO 本機或 devops-sre 以 `sqlite3 -readonly` 執行，我不碰 DB）：

```sql
SELECT symbol, batch_no, COUNT(*) n, SUM(settled=0) unsettled, GROUP_CONCAT(id), GROUP_CONCAT(execution_date)
FROM playbook_directives WHERE rule_id='EMERGENCY' AND action='sell'
GROUP BY symbol, batch_no HAVING COUNT(*) > 1;
```

#### Q3：N-171 由 `/today` 揭露待執行出清指令

**做法：**
- `TodayResponse` 新增加法欄位，暫名 `pending_exit_directives: list[DirectiveLine]`，`PlaybookEvaluation` 與 `types.ts` 同步。
- 資料來源：新的 store 讀取方法，條件逐字等於 C-4：`rule_id='EMERGENCY' AND action='sell' AND settled=0`，**不加 execution_date 條件**。
- 不能用 `store.pending_directives(on_or_before=…)`，因為它會濾掉 `execution_date > as_of` 的列（`store.py:853-855`），而那正是 T 到 T+1 開盤前最需要顯示的指令。
- 在 authored 路徑上，要在 `settle_pending` 之後讀（`service.py:631`）。

**與 C-7 的互動：**
- C-7 管的是出清回應。`/today` 適用同一精神，而且有更硬的理由：`RuleSetConfirmPanel.tsx:40-47` 明寫「帳冊裡的每一筆指令」之所以成立，是因為 EMERGENCY 指令永遠不會併入 `TodayResponse.directives`。
- 混進 `directives` 會讓這句確認文案變成不實陳述。**VETO：不得混入 `directives`、`snapshot`、`settlement`。**
- 這個欄位也不得影響 `rules_fully_evaluated`、`no_directive_note`、`page_summary`（`api/playbook.py:389-394`）。

**與 N-168 B-2a 的互動：**
- C-B9 的待成交買單清單也在 `/today`，也要在 `settle_pending` 之後讀。兩者可以共用同一次讀取（同一個 conn，快照一致），但必須是兩個欄位。
- **VETO：N-171 欄位不得含 buy 列**（延伸 N-168 VETO-2）。
- 風控 W-B2L 要求帶標示批次的每一行 EMERGENCY 指令都附註，所以 N-168 落地時，必須把 W-B2L 補到 N-171 的清單上。

**unauthored 路徑：**
- `_unauthored_evaluation`（`service.py:542-612`）不結算、不寫入，docstring 寫明只對批次簿做存在檢查。
- 出清不受 authorship 閘門限制（EX-2），所以這條路徑上也可能有待執行的出清指令。
- 建議在這條路徑上也做唯讀揭露，但這擴大了「題 9」的檢查範圍，要風控認可。

**NB-6 第 2 句：**
- 第 2 句是「狀態列無法顯示這次是否已產生賣出指令」（PRD `:283`）。頁面一旦能顯示清單，這句就變成過時、而且是以省略造成誤導，所以 N-171 合併前必須回審。
- 第 1 句的 (ii) 與第 3 句由 N-166 改變，屬於 D-2 的回審範圍。

**能否分辨 Q5 的 (ii) 與 (iii)：**
- N-166 之前：在 T+1 結算前、且有 open 批次時可以分辨。(ii) 是凍結但清單為空；(iii) 是凍結且清單非空。
- 結算之後清單會清空，分辨線索變成 snapshot 的批次是 closed 還是 open。
- EMPTY 分支兩者無差別。unauthored 路徑的 mode 是 `unconfirmed`，看不到凍結，只能看清單。
- N-166 之後 (ii) 消失，清單改為分辨 (i) 與 (iii)。

**規模粗估：**
- backend：S～M，一個讀取方法、兩條 service 路徑、一個欄位，約 8 條測試。
- frontend：M，新區塊不能放進 DirectiveLedger，要處理與 sticky 狀態列、N-170 後備位置的版面關係，加上鏡射測試。
- 另需風控定字面（標題、歸屬語可能沿用 S4、空狀態）與 NB-6 回審。
- 整體：中。

**排序：**
- 不併入 N-166 的 PR。理由是範圍外項目一律另開（ADR-0033 附錄 D 的慣例），而且 N-166 已有風控閘門。
- 排在 N-166 之後、N-168 之前。
- 謂詞要沿用 N-166 落地後的 C-4 單一來源。

**N-171 約束（給 qa-reviewer 逐條檢查）：**
- N171-C1：獨立欄位，預設 `[]`，`types.ts` 同步。
- N171-C2：謂詞與 C-4 共用同一個來源，不加 execution_date 條件，不呼叫 `pending_directives(on_or_before)`。
- N171-C3：不得由 mode 或 `emergency_until` 推導（比照 N-168 VETO-1）。
- N171-C4：依 CEO-2 的裁示去重，以 (symbol, batch_no) 為單位，不得加總重複列的股數。
- N171-C5：不含 buy 列。
- N171-C6：store 不 import wording（C-10）；字面放 `wording.py`，風控核可前不得合併。
- N171-C7：前端不經過 DirectiveLedger 渲染，並有守門測試證明 `RuleSetConfirmPanel` 那句前提仍然成立。
- N171-C8：NB-6 第 2 句回審通過前不得合併。

#### Q4：N-174 查證

**讀碼判定：**
- R 進場只在 `mode=="normal"`、排程日、指數可用時產生（`engine.py:1142`、`:1250-1251`）。
- 模式由同一次 evaluate 的 data_date 決定（`engine.py:1129-1137`、`:344-373`）。
- 買單的 execution_date 等於 `next_trading_day(data_date)`（`engine.py:1099`）。
- 結算沒有任何模式判斷（`service.py:238-315`），而且先於評估執行（`service.py:631` 早於 `:671`）。
- **所以「凍結或防守模式下到期的 R 買單照樣結算」成立。**

**分情境判定：**
- **(a) 模式在 T+1 收盤才翻轉（常態）。** 買單在 T+1 開盤執行，早於觸發翻轉的收盤資料。帳冊記的是凍結前已發生的事，FROZEN_NOTE（`wording.py:290`）是對之後的陳述，**不矛盾**。同一個回應中結算區塊與 FROZEN_NOTE 並陳可能令人困惑，屬於字面議題。
- **(b) T+1 沒抓到開盤價，之後才補結算。** 仍以 T+1 開盤價記帳，屬事實，**不矛盾**。
- **(c) 同一個 data_date 重複評估，第二次翻成 S3 或防守。** 例如第一次呼叫時部分標的或指數只有 T-1 的資料，一小時後重抓到 T 的資料，未實現損益跨過 S3 門檻，或防守條件成立。第一次寫入的 R 買單（執行日 T+1，尚未開盤）仍會結算，而第二次的 FROZEN_NOTE 說「不執行」，第二次的 `directives` 也不再列出那筆買單。**矛盾成立**，與 N-168 的 U-A／U-B 實害相同。這是讀碼推定，要請 qa-automation 重現。

**與 N-168 的關係：**
- (c) 在後果上與 N-168 同型，但根因不同：
  - N-168 是使用者的動作（出清）落在買單產生之後、執行之前；
  - (c) 是同一個 data_date 重評估沒有定義語意，與 N-172（F5，`evaluate_today` 沒有當日去重）同根。
- **B-2a 戳記不能直接套用，理由三點：**
  1. 觸發點在 `evaluate_today` 的 `apply_effects`（`store.py:730-735`），那裡是多個各自開 conn 的寫入，沒有出清那種單一 `BEGIN IMMEDIATE` 可以掛；
  2. W-B 系列字面的主體是「你提交全部出清」，套到系統判斷的翻轉上是不實陳述；
  3. L4 欄位若身兼兩種語意，要另立 ADR。
- **建議：** N-174 併入 N-172 一起設計「同一 data_date 重評估語意」，例如「首次評估為準、之後重播」或「後次覆蓋並處置前次的待成交單」，屬產品與風控的取捨。ADR-0034 的戳記欄位維持出清專用，不為 N-174 預留。

#### 範圍外新發現（讀碼判定，建議另開追蹤）

- **F7（建議 medium）：執行日可能落在未預期的休市日，指令永遠不會結算。**
  - 預定執行日超出已觀察範圍時走 weekday fallback（`data/calendar.py:74-85`、`:91-93`）。
  - 遇到颱風假或春節，預定執行日會落在休市日；結算要求 `bar.date == execution_date` 完全相符（`service.py:275-277`），所以這列永遠不會結算。
  - 若是 EMERGENCY 指令，在 N-166 加 CEO-1（過期未結算也算覆蓋）之下，它會永遠被視為已覆蓋；批次在帳冊上永遠是 open。
  - 請 qa-automation 重現。
- **F6（low）：unauthored 狀態下指令不會結算。**
  - unauthored 路徑不結算（`service.py:628-630` 在 `:631` 之前就 return）；前端從不呼叫 `POST /settle`（grep 結果為 0）；scheduler 也不碰 playbook（grep 結果為 0）。
  - 所以 unauthored 狀態下的出清指令不會結算。只有用 seed 建出持倉的情境才會遇到。

### 應經手但尚未經手
- risk-compliance-officer：4xx 是否另立字面；N-171 的字面與 unauthored 揭露；NB-6 第 2 句回審。
- qa-automation：重現 N-174 (c)、F7。
- devops-sre 或 CEO：執行唯讀盤點查詢。
- dev-lead：守門測試與落地。

## 三、驗證

- 讀過的程式（前綴 `apps/stock-desk/backend/app/`）：`api/playbook.py`、`api/client_header.py`、`api/server_error.py`、`api/deps.py`、`main.py`、`playbook/service.py`（`:1-80`、`:150-350`、`:540-920`）、`playbook/store.py`（`:100-219`、`:540-983`）、`playbook/engine.py`（`:58-83`、`:340-420`、`:783-902`、`:1060-1319`）、`playbook/models.py:40-47`、`data/calendar.py`、`services/index.py`（grep）。
- 前端：`lib/api.ts:46`、`:150-205`、`:465-474`；`playbook/RuleSetConfirmPanel.tsx:30-54`；`playbook/SettlementPanel.tsx:1-40`。
- 測試：`tests/test_client_header.py`。
- 文件：ADR-0033、PRD N164N165（相關段落）、風控 N164N165、N-166、N-168 裁示、本人 N-168 評估、追蹤清單 N-166～N-174。
- grep 範圍：`HTTPException`／`RequestValidationError`、`directive_log`／`playbook_directives` 的使用端、`playbook/settle` 的呼叫端、scheduler 對 playbook 的引用。
- **已驗證：** 只有 403 在進入 router 之前就被擋下、不碰 service 這一點，由既有測試 `test_client_header.py:52-58`、`:76-79` 釘住（我未執行）。其餘全部是讀碼判定。
- 我沒有執行任何程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 四、下一步

### 需要 CEO 裁示
1. **Q2 的 4xx 字面：**
   - (a) 維持現行保守字面（建議）。403 只會因前端漏帶 header 而出現，實際價值低。
   - (b) 另立「本次未處理」字面。限定只講本次，不得暗示沒有待執行指令，要送風控審，並以上述三個前提與兩條守門測試為條件。
2. **CEO-2 重複列：**
   - (a) 先盤點，再採不清＋讀取側去重（建議）。若盤點結果為零未結算重複列，可另議啟用 (e)。
   - (b) 一次性標記遷移，只處理 execution_date 相同的未結算重複列；要新增狀態值並經風控定字面。
   - 刪除列與改寫已結算列：**VETO**。
3. **N-171 排序與範圍：** 確認 N-166 → N-171 → N-168 的順序，以及 unauthored 路徑也要揭露（需風控認可）。
4. **N-174：** 併入 N-172 一起設計（建議），不併入 N-168；並以 N-172 裁定同一 data_date 重評估的語意。
5. **F6、F7：** 是否另開追蹤（F7 建議 medium）。

### VETO 彙整
- 刪除 R16 指令列。
- 改寫已結算列的 status。
- 在遷移中無條件建 partial unique index。
- N-171 混入 `directives`、`snapshot`、`settlement`，或含 buy 列。
- N-171 用 mode／`emergency_until` 推導，或用 `pending_directives(on_or_before)` 讀取。

### 交接
- PM：依本評估撰寫 N-171 PRD。
- 風控：處理上列字面與回審事項。
- dev-lead：Q2 的兩條守門測試，以及 N-171 的 C1～C8。
- tech-writer：N-171 若採用，需新的 ADR（補充 0033、不取代）。

### 相關檔案
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/client_header.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/server_error.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/deps.py
- /home/user/AICompany/apps/stock-desk/backend/app/main.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_client_header.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/api.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/RuleSetConfirmPanel.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/SettlementPanel.tsx
- /home/user/AICompany/docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md
- /home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md
- /home/user/AICompany/work/reviews/2026-10-31-N164N165版面與失敗字面-風控.md
- /home/user/AICompany/work/reviews/2026-10-31-N166新字面與延長凍結揭露-風控.md
- /home/user/AICompany/work/reviews/2026-10-31-N168方案裁示-風控.md
- /home/user/AICompany/work/reviews/2026-10-31-N168技術評估-tech-architect.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

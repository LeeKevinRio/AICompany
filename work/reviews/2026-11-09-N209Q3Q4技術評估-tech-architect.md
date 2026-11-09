# N-209 Q-3、Q-4 技術評估

- 審查者：tech-architect
- 日期：2026-11-09
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- **Q-3(a)：後端不會因為「規則集尚未確認」而拒絕 REBALANCE。PRD FR-2 舉的例子不符合現況。**
  - 現況 code 沒有 authorship 閘。未確認時呼叫，會用系統預設參數照樣執行，回 200、`status:"ok"`，並寫入 TOTAL_DEPLOY=0。
  - 批次表為空時同樣回 200 `ok`。
  - TOTAL_DEPLOY 鍵不存在時，回應與訊息都會以 0 代入。
  - 目前唯一的「拒絕」是 `insufficient_data`，它是執行後才回的 200，不是事前檢查。
- **Q-3(b)：三種回應都沒有「寫入時間」這個欄位。**
  - ok：帶新的 TOTAL_DEPLOY（未格式化的 Decimal 字串）。
  - insufficient_data：帶 snapshot 讀到的值，鍵不存在時是 `"0"`。
  - superseded：只在 N-197a 合入後才有。目前值與時間都寫在 `message` 文字裡，結構化欄位只有 `previous_total_deploy`。
  - 前端能另外讀取的來源是 `GET /api/playbook/rule-set`，但它在鍵不存在時同樣回 `total_deploy:"0"`。
- **Q-4：不會因為 retry 而重送。**
  - `QueryClient` 沒有 defaultOptions。專案內 17 個 mutation 都沒有設 `retry`，函式庫對 mutation 的預設值是 0。
  - 但有兩條路徑在實質上等於重送或延後送出，FR-8／FR-10 要另外防：
    - mutation 預設的 `networkMode:"online"` 會在離線時暫停，恢復連線後自動送出；
    - 連點時，若按鈕還沒重新渲染成鎖定狀態，會送出兩次。
- **可行性判定：**

| 需求 | 技術上可行 | 需要後端改動嗎 |
|---|---|---|
| FR-8 | 可行 | 不需要，純前端 |
| FR-10 | 可行 | 不需要，純前端 |
| FR-2 | 可行 | 不必然。但「未確認時要不要擋」須由 CEO 與風控裁決；若要擋，就要改後端 |
| FR-5 | 純前端勉強可行，靠 `total_deploy_set_at === null` 推斷 | 建議以後端加法欄位明示 |
| FR-9 ok（附帶判定） | 嚴格照 PRD 要「本次寫入時間」 | 需要後端改動 |

- **建議另開一張後端小單（暫稱 N-209b）：** 只加 API 欄位，排在 N-197a 合入之後、N-209 前端之前。不得併進 N-197a，因為 N197a-C1 規定 `app/api/**` 零 diff。

## 二、各部門回報

### tech-architect（唯讀評估；現況以工作樹 product/stock-desk `a3a8829` 為準）

**前提事實：現況連 N-195 都還沒合入。**
- `set_total_deploy`、`read_rebalance_inputs`、`TotalDeployStamp`、`REBALANCE_SUPERSEDED` 在 `apps/` 內都搜不到。
- N-195 在 `fix/n195-rebalance-no-cash`（`1bdbbda`），依追蹤清單第 409 列，要等 R2 與 N-177a 同一批合入。
- N-196、N-197a 只有 spec，沒有 code。所以下表「合入後」一欄依 spec 推論，不是讀碼結果。

#### Q-3(a) 三種情境的實際行為

路徑：
- 端點：`apps/stock-desk/backend/app/api/playbook.py:692-715`；回應模型 `:185-198`，`status` 型別是 `str`。
- service：`apps/stock-desk/backend/app/playbook/service.py:1809-1947`。

| 情境 | 現況（a3a8829） | N-195／N-196／N-197a 合入後（依 spec） |
|---|---|---|
| 規則集尚未確認 | **沒有閘**（端點與 service 都沒有呼叫 `rule_set_authorship`）。`active_params` 退回系統預設（store.py:1130-1131）。現金鍵不存在時讀成 0（store.py:1022）；確認前沒有 open 批次，所以 deployed=0。結果回 200 `ok`，`total_assets="0"`、`new_total_deploy="0"`，並經 `set_capital` 寫入 cash、total_deploy=0、set_at、source=`quarterly_rebalance` 四個鍵（service.py:1908-1912、store.py:1048-1055） | 仍然沒有閘，仍回 200 `ok`、TD=0。N-195 之後不再建立 cash 鍵（N195-C6）。N-197a 之後，snapshot 與鎖內三個鍵都是 None，比對相等，寫入成功（N197a-T8，修訂四檔 :350） |
| TOTAL_DEPLOY 鍵不存在 | 只有「從未確認、也從未 REBALANCE」時才會發生，因為鍵只由 `set_capital` 建立。`portfolio_state` 以 `Decimal("0")` 代入（store.py:1023），`previous_total_deploy="0"`。ok 訊息會寫成「TOTAL_DEPLOY 由 0.00 重算為 …」（wording.py:1045-1048）。**這與 FR-5「不得以 0 代入」的精神衝突** | snapshot 時不存在：同左（`_portfolio_from_state` 原樣搬移）。snapshot 之後才被寫入：回 200 `superseded`。snapshot 時存在、鎖內卻不存在：依 spec 2.2 raise `TotalDeployStampInvariantError`，回 **500 text/plain**，不寫入任何值（主 spec :2462-2494） |
| 批次表為空 | `symbols=[]`，不載入日線（service.py:1468-1482），`missing=[]`。回 200 `ok`，TD = 現金 × deploy_ratio，並寫入 | 同左。寫入改走 `set_total_deploy`，加上戳記比對 |
| 持股缺收盤價 | 回 200 `insufficient_data`，`REBALANCE_BLOCKED`（wording.py:1057-1060），不寫入（service.py:1855-1868） | 同左；N196-C4 規定缺日線一律走這條 |
| 例外 | 未處理的例外經 `CorsVisibleServerErrorMiddleware` 回 **500 text/plain "Internal Server Error"**（server_error.py:44-59）。缺 `X-Stock-Desk-Client` header 回 **403 JSON**（client_header.py:44-58），但前端 `request()` 對 POST 一定會帶（api.ts:175）。**注意：500 可能發生在寫入 commit 之後**，例如 `set_capital` 已 commit，接著 `record_directives`（service.py:1925-1946）失敗 | 多一種 500：invariant 例外，但不會有寫入 |

**stamp 比對：**
- 現況：完全沒有。寫入是無條件的 `set_capital`（service.py:1908），所以 R-5′ 的交錯仍在（ADR-0041:108）。
- N-195：只寫三個鍵、不比對（主 spec :1441-1458）。
- N-196：日線載入後，以一個 DEFERRED `BEGIN` 讀批次與 state（主 spec :1735-1771）。
- N-197a：在 `BEGIN IMMEDIATE` 內比對三個鍵的原始字串，不一致就拒寫並回 `superseded`，不重試（修訂四檔 :271-304、C3/C4 :324-328）。

**給 Q-2(a) 的技術事實（供風控判斷，不代為下結論）：**
- N-177a（R-α）、N-195、N-196 都合入之後，結算與 REBALANCE 並發，結果等於某一種先後執行（主 spec :1785-1791）。
- 結算不寫三個 TOTAL_DEPLOY 鍵，所以不會造成誤拒（N197a-T3）。

#### Q-3(b) 回應帶了什麼

| 回應 | 現況 | 合入後 |
|---|---|---|
| ok | `new_total_deploy`：Decimal 原字串，可能有 3 位小數，不是 .2f。**沒有寫入時間**：寫入時間在 store 內部才產生（store.py:1052），不回傳。`executed_at` 是 UTC 日期（service.py:1827），`as_of` 是回應時刻（api/playbook.py:714），兩者都不是寫入時間 | 同左；N195／N196／N197a-C1 都規定 API 零 diff |
| insufficient_data | `previous_total_deploy` 是 snapshot 值（鍵不存在時為 `"0"`），`new_total_deploy:null`，沒有時間 | 同左，值改由單一 snapshot 取得（N196-C3） |
| superseded | 不存在（models.py:525 的 Literal 只有兩個值） | 200；`previous_total_deploy` = 鎖內讀到的目前值；**時間只在 `message` 內**：風控定稿字面，`{set_at}` 由 `taipei_wall_time` 產生，格式 `YYYY-MM-DD HH:MM:SS 台北時間`（風控定稿檔 :119；主 spec :2497-2516）。沒有結構化的時間欄位 |

前端可另外讀取的來源：`GET /api/playbook/rule-set`（api/playbook.py:630-650），欄位見 `:258-261`、`:519-526`。
- `total_deploy: str`，鍵不存在時是 `"0"`；
- `total_deploy_set_at: ISO | null`，鍵不存在時是 null；
- `total_deploy_source`。
- 這個端點只讀不寫（service.py:1976-1985）。目前只有 `RuleSetConfirmPanel` 在未確認模式下會掛這個 query（queries.ts:431-438）。

另外兩點：
- `/today` 的回應沒有 TOTAL_DEPLOY 欄位。畫面上「TOTAL_DEPLOY 相關顯示」實際上是 R1 每批股數，要靠 invalidate `["playbook-today"]` 更新。
- 前端目前沒有 `postPlaybookRebalance`，也沒有對應的型別。

#### Q-4 QueryClient 與 mutation 的 retry

- `QueryClient` 建立處：`apps/stock-desk/frontend/app/providers.tsx:9`，`new QueryClient()`，沒有 defaultOptions。全 app 沒有 `setDefaultOptions` 或 `setMutationDefaults`。
- 這個字面已被測試釘住：exitFlowStructure.test.ts:135、emergencyExitOffline.test.ts:146、entryObservationPending.test.ts:244（FE-C1）。
- 函式庫預設值（安裝版本 5.101.4，依 node_modules 原始碼）：
  - mutation：`retry: this.options.retry ?? 0`（query-core/src/mutation.ts:199）；
  - `networkMode` 預設 `'online'`（retryer.ts:53-54）。離線時 `isPaused`（mutation.ts:206、213），恢復連線後自動送出。
- 全部 mutation 都在 `apps/stock-desk/frontend/app/lib/queries.ts`，**沒有一個設 `retry`**。行號如下：

| 行號 | mutation |
|---|---|
| 117-123 | useCreatePosition |
| 125-132 | useUpdatePosition |
| 141-155 | usePatchPosition |
| 157-168 | useDeletePosition |
| 197-203 | useImportPositionsCsv |
| 245-249 | useRunBacktest |
| 260-276 | useUpdateSettings |
| 287-295 | useEvaluateAlertsNow |
| 297-305 | useCreateAlert |
| 307-315 | useUpdateAlert |
| 317-325 | useDeleteAlert |
| 336-344 | useAckAlertEvent |
| 446-455 | useConfirmPlaybookRules |
| 490-527、537-540 | emergencyExitMutationOptions / useEmergencyExit：`networkMode:"always"`，刻意不設 retry、scope |
| 567-585 | useUpdateKellyInput |
| 588-599 | useDeleteKellyInput |
| 607-625 | useImportKellyBacktest |

- 檔內其餘的 `retry: 1`／`false` 都是 `useQuery`，屬於 GET。`GET /rule-set` 的 `retry:1` 是唯讀重讀，不違反 FR-8／FR-10。
- `request()`（api.ts:167-205）：
  - 沒有 timeout，也沒有 AbortController；
  - 網路錯誤丟 `ApiError(…, 0)`（:179-181）；
  - 非 2xx 丟 `ApiError("請求失敗（HTTP n）", n)`（:183-195）。
- 已有 TA 確認：client 斷線不會中止後端同步端點（主 spec :2628-2634）。所以「逾時、網路錯誤」時，後端可能仍會跑完並寫入，只能當作「結果不明」。

#### 方案比較（Q-3(b)、FR-4／5／9 的資料來源）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 純前端：開確認畫面與出結果後重讀 `GET /rule-set`，以 `set_at===null` 判斷「沒有紀錄」，用 format.ts 格式化 | 後端零 diff，N-197a 後即可動工 | ok 的寫入時間是事後重讀，不保證是本次寫入的（中間可能插入資金確認）；`formatDateTime` 只到分鐘，格式是「（台北時間）」，和 superseded 字面的秒級「 台北時間」不一致；JS 的 `.2f` 捨入可能與 Python Decimal 的 `.2f` 不同（後者依預設 context 是 ROUND_HALF_EVEN，未實跑）；「沒有紀錄」要靠 C6 不變式推斷 | 中 |
| **B 後端加法欄位（N-209b，建議）**：`RebalanceResponse` 與 `RuleSetResponse` 加入後端算好的 `.2f` 金額字串、`taipei_wall_time` 時間字串、`total_deploy_recorded: bool`。ok 分支由 service 產生 `at`，傳給 `set_total_deploy(at=…)` 後原樣回傳 | 單一格式來源，與「UI 不得改寫字面」的既有原則一致（api/playbook.py:85、:250-254 的先例）；ok 的時間就是本次寫入值；FR-5 改為明示，不靠推斷 | 動到 service、models、api 三層；必須是 N-197a 之後的獨立 PR；要 qa 審 | 低 |
| C 新增 `GET /total-deploy` 端點 | payload 小 | 與 `/rule-set` 重複，多一條讀取路徑，對 ok 的寫入時間沒有幫助 | 中，不採 |

**未確認時要不要擋（FR-2），交 CEO 與風控裁決：**
- **(甲) 加 authorship 閘**：未確認時回 200、新 status（例如 `unauthored`），不寫入，比照 `/settle` 的先例（api/playbook.py:621-624）。
  - 好處：同時消除「由 0.00 重算」這個以 0 代入的情況，也不會在使用者未採用的規則集下寫入資金決策。另外，依 ADR-0043 D6，任何一次 TD 寫入都會讓戳記改變而解開閘（`work/reviews/2026-11-09-ADR0043修訂一與補充四改寫-tech-architect.md:340-350`），甲案也避免這種狀況。
  - 代價：要新字面（送風控），Literal 也要再加一個值。
- **(乙) 維持現況**：PRD FR-2 要更正例子，ok 訊息中的「0.00」交風控判斷。
- **TA 建議甲。**

#### 決策（ADR 草案，編號由 coordinator 給；狀態 proposed；補充 ADR-0041，不取代）

- **Context：**
  - N-209 讓 REBALANCE 的回應首次有前端使用者。N197a 2.4 的已知限制（主 spec :2528-2531）因此成立：OpenAPI 上沒有說明 `previous_total_deploy` 的語意。
  - 現有回應沒有寫入時間、沒有「是否有紀錄」，金額也不是 .2f。
  - 未確認時 REBALANCE 會寫入 TD=0。
- **Decision：**
  1. 另開 N-209b，只做加法欄位（方案 B），並為 `previous_total_deploy` 加上 `Field(description=…)`；
  2. 排程：N-197a 合入 → N-209b → N-209 前端；
  3. authorship 閘依 CEO 與風控裁決，若採用就併入 N-209b。
- **Consequences：**
  - 好處：顯示的值單一來源，FR-4、FR-5、FR-9 都能逐字對齊。
  - 壞處：N-209 多一個後端 PR 與一輪 qa；若採甲，要多一句風控字面並延後時程；與 N-197a 碰到同一個函式，必須等它合入，不得 rebase 搶先。

#### 對實作的約束（qa-reviewer 可逐條檢查）

- **F-1**：`postPlaybookRebalance()` 走 `request()`，POST，不帶 body。
- **F-2**：mutation options 設 `networkMode:"always"`。不得出現 `retry`、`retryDelay`、`scope`、`mutationKey`。`providers.tsx` 的 `new QueryClient()` 字面不得改，不得用 `setMutationDefaults`。
- **F-3**：用同步的 ref 鎖，在 `mutate` 之前檢查並設定；只在 mutate-level 的 `onSettled` 釋放。按鈕在 `lock || isPending` 時鎖定。比照 useEmergencyExitFlow.ts:66、:96-108。
- **F-4**：結果分類用執行期的封閉集合判定，不信任 TS 型別。N-209 若在 N-197a 之後上線，集合是 `{ok, insufficient_data, superseded}`。其餘情況一律走 FR-10，絕不判為「失敗」：未知 status、缺欄位、`ApiError` status 0、任何非 2xx（含 500，因為 500 可能發生在寫入 commit 之後）。
- **F-5**：不加 AbortController 或 timeout 中止。任何路徑都不自動重送。使用者要再執行，必須重新走 FR-3 的確認畫面。
- **F-6**：hook-level 的 `onSettled`（成功或失敗都跑）：對 `["playbook-today"]` 先 cancel 再 invalidate，並 invalidate `["playbook-rule-set"]`。兩者都不 await。
- **F-7**：入口元件不得 import 日期、日曆或窗口相關模組（`taipeiDay`、calendar、ADR-0043 窗口欄位），樣式只依鎖定狀態變化。以結構測試釘住，比照 exitFlowStructure.test.ts。
- **F-8**：`message` 原樣顯示。若採方案 B，金額與時間只取後端算好的欄位，前端不再格式化。若退回方案 A，「沒有紀錄」只能依 `total_deploy_set_at === null` 判斷，不得依 `total_deploy === "0"`。
- **B-1**（N-209b）：只做加法，不改既有欄位型別、不改既有字面。`set_total_deploy(` 在 `rebalance` 內仍恰好出現一次（N197a-T7）。不得重開 N-197a 的 C1。

## 三、驗證

- 已讀檔並逐行核對（以上行號都出自本 checkout）：
  - 後端：`backend/app/api/playbook.py`、`app/playbook/{service,store,models,wording}.py`、`app/api/{server_error,client_header}.py`、`app/main.py`；
  - 前端：`frontend/app/{providers.tsx,lib/queries.ts,lib/api.ts,lib/format.ts}`；
  - 函式庫：`node_modules/@tanstack/query-core/src/{mutation,retryer,queryClient}.ts`；
  - 文件：ADR-0041、主 spec（N-195 :1441-1458、N-196 :1703-1806、N-197a required :2443-2586）、修訂四 N-197a 草案 :240-352、風控 N-197a 裁示 :69-97、`REBALANCE_SUPERSEDED` 定稿 :117-125、ADR-0043 修訂一 D6。
- **未驗證：**
  - 沒有 Bash，所以無法跑 git。「現況 = HEAD a3a8829」是依 `.git/refs` 與工作樹推定，沒有排除未 commit 的改動。
  - N-195 分支 `1bdbbda` 的實際 code 沒有讀到（git 物件不可讀）。N-196、N-197a 欄位依 spec 推論。
  - 沒有跑任何測試。Python Decimal `.2f` 與 JS 捨入不一致的說法，是依預設 context 推論，未實測。
  - TanStack 行為依安裝的 5.101.4 原始碼，版本查證屬 devops-sre。
- 未讀 `.env`，未碰任何 `data/*.db`，沒有寫入任何檔案。

## 四、下一步

1. **CEO 與風控**：裁決 authorship 閘（甲或乙）。若採甲，creative-lead 擬新的 status 字面，送風控逐字定稿。
2. **風控**：Q-2(a) 可參考上面「給 Q-2(a) 的技術事實」一段。乙案下，ok 訊息「由 0.00」是否可接受，也由風控判定。
3. **PM**：
   - FR-2 改寫例子：後端不會因未確認而拒絕，除非採甲。
   - FR-9 ok 的「寫入時間」：註明需要 N-209b；若不做 N-209b，就改成「目前讀到的 TOTAL_DEPLOY 與時間」。
   - AC-17：在 N-209 排在 N-197a 之後的前提下，`superseded` 已是已知值，改用真正未知的值注入測試。
   - FR-10 的「逾時」：前端沒有 timeout 機制，請刪除或改寫。
4. **coordinator**：決定是否開 N-209b（排在 N-197a 之後、N-209 前端之前），以及 ADR 編號（或併為 ADR-0041 補充）。tech-writer 在 N-209 上線時，評估 ADR-0041 R-5′ 中「目前前端沒有 REBALANCE 的入口」這句是否需要加註。
5. **frontend-engineer**：依 F-1～F-8 實作，並複核 Q-4 的 node_modules 判讀。devops-sre 查證 `@tanstack/react-query` 5.101.4 的版本行為。
6. 完成後照章程走 qa-reviewer（含 Codex）與 qa-e2e 實機驗收。

相關檔案：
- `/home/user/AICompany/work/stock-desk-REBALANCE畫面入口-PRD.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py`
- `/home/user/AICompany/apps/stock-desk/frontend/app/providers.tsx`
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts`
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/api.ts`
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md`
- `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-07-修訂六與ADR0042與N199審查及REBALANCE_SUPERSEDED定稿-風控.md`

# ADR-0033：stock-desk EMERGENCY_EXIT 重複呼叫的覆蓋判定式冪等

- 狀態：accepted（CEO #76、#77，2026-10-29 裁定；落檔前提：新字面經風控核可前不得合併，見 Decision 8）
- 日期：2026-10-29（tech-architect 草案日期 2026-10-29）
- 決策者：tech-architect（草案）；CEO #76（方案 (d)）、#77（凍結日取 max）於 2026-10-29 裁定；risk-compliance-officer 負責新字面與歸屬語定稿（**尚未經手**）。
- 來源簡稱（皆在 `work/` 下）：
  - [TA]：`reviews/2026-10-29-N166出清重複呼叫防護評估-tech-architect.md`（Q1～Q5、C-1～C-11、T-1～T-6、F-T1～F-T6，以及該檔的「ADR 草案」一節）
  - [決策包]：`dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（第 92 行 #76、第 93 行 #77）
  - [風控前置]：`reviews/快市排程-風控前置意見.md`（EX-2、EX-3，引自 [TA]）
  - [qa-automation]：`reviews/2026-10-29-N163N164沙盒出清-代跑交件-qa-automation.md`（A3，引自 [TA]）
- 與既有 ADR 的關係：
  - 沿用 N-154、N-156 的「`BEGIN IMMEDIATE` 鎖內重讀」模式（[TA]；N-156 的鎖模式在 `settings/migrations.py`，不在 `settings/store.py`）。
  - 不修改任何既有 ADR。ADR-0001 禁止原地改寫已生效 ADR。
- 適用範圍：僅 product/stock-desk；程式路徑相對於 `apps/stock-desk/backend/`。
- 標註約定：
  - 本檔為 [TA] 草案加 CEO #76／#77 裁定的轉錄，屬記錄決策脈絡（B 類）。
  - 文內 `檔案:行號` 為 [TA] 撰寫時（2026-10-29）的快照，會隨 commit 漂移，抽驗請以內容定位。
  - 本檔未改動草案的技術敘述。tech-writer 落檔時僅抽驗了 `playbook/service.py` 的 `emergency_exit`（該函式內 `freeze_until` 以 `calendar.shift(as_of, params.emergency_freeze_trading_days)` 計算、批次篩選只看 `status`／`remaining_shares`、先 `apply_effects` 再 `record_directives`）與 `playbook/store.py` 的 `freeze_emergency`（直接覆寫），與草案敘述一致；其餘行號未逐條重驗。
  - **字面規則**：`EMERGENCY_EXIT_ALREADY_PENDING` 與「延長凍結」揭露句的實際文字**一律不寫進本檔**。新字面僅放 `wording.py`，風控核可前不得合併。

---

## Context（背景）

以下出自 [TA]（Q1 現況判定與 ADR 草案 Context）：

- N-163 實機：修鎖前雙擊或同 task 連點兩次，會送出 2 筆 `POST /api/playbook/emergency-exit`。前端 ref 鎖（commit 74979dd）只擋得住同一對話框；兩個分頁、網路重送、直接打 API 仍會重複。
- **現況沒有任何「已凍結」或「已出清」的檢查**：
  - 端點 `api/playbook.py:536-551` 直接呼叫 `service.emergency_exit()`；全 app 沒有任何 `exception_handler`。
  - `playbook/service.py:722-740` 的 docstring 明寫「never gated on ... a freeze」（風控 R11）。
- **同一天重複呼叫會重複產生賣出指令，凍結期不變**：
  - 批次在 T+1 結算前一直是 open；結算只發生在 `playbook/store.py:900-959`，`tests/test_playbook_settlement.py:216-217` 釘住「出清後、結算前批次仍是 open」。
  - `service.py:754-756` 只篩 `status=="open" and remaining_shares>0`，不看是否已有待執行的 EMERGENCY 指令。
  - 寫入走 `store.py:784-824`，是純 INSERT；`playbook_directives` 沒有唯一約束（`store.py:129-153`）。
  - 回應是 200，message 再說一次「已產生 N 批…」。
  - 凍結日 `service.py:750` 用 `shift(as_of, 20)`，同一天值相同；`store.py:563-564` 直接覆寫，所以不會延長。
- **隔天再呼叫（仍在凍結中）**：`emergency_until` 被覆寫成 `shift(新的一天, 20)`，凍結期延長。若尚未結算（例如當天沒抓到開盤價而被列為 unsettled）會再重複產生賣出指令；若已結算、批次為 closed，走 EMPTY 分支，不產生指令，但凍結期一樣延長。
- **重複指令結算後的後果**：現金不會重複入帳（`store.py:943` 的 `min(remaining, shares)`）；但 R16 指令日誌會出現兩筆已執行的賣出，股數為實際兩倍，結算摘要的 executed 數也翻倍（`service.py:303-313`）。本產品不下單（風控 R10），使用者拿著回應自行到券商下單，會收到兩次「賣出 N 批」。
- **並發會雙寫，且循序呼叫就會雙寫**：端點是同步 `def`，在 threadpool 內執行，整條路徑沒有鎖；先讀批次、打網路（`service.py:742-745`），才寫凍結（`837-847`）與指令（`848-868`）；兩者分屬兩個獨立 transaction（`store.py:466-476`、`store.py:792`）。因此修法不能只在鎖外先查一次，檢查必須放進鎖內。
- **限制**：風控 EX-2（出口不得有前置條件）、EX-3（凍結期間 SELL 類加再次 EXIT 可執行），出處 [風控前置] `:43-45`；`mode_reason` 禁存快照（`service.py` 該處註解「覆審: mode_reason 禁存快照字串」）。出清不可逆。

## Options（選項比較）

### 防護方案

| 方案 | 優點 | 缺點 | 風險／結論 |
|---|---|---|---|
| (a) 已凍結回 409 | 最簡單 | 違反 EX-2、EX-3；前端 `EmergencyExitControl.tsx:263-266` 會顯示「全部出清送出失敗：…」，但出清其實已生效，誤導使用者；第二個分頁也看到「失敗」；會打破 `tests/test_playbook_exit_matrix.py:167-178` 的 emergency_frozen 案例；會擋掉真實存在的合法再出清（見附錄 D 的 F1） | **否決**。變體 (a′)「只有全部批次都已覆蓋才回 409」較好，但前端仍呈現成失敗且仍要新字面，不如 (d) |
| (b) 凍結期內回傳第一次結果 | 前端零改動；沿用現有字面 | 同樣違反 EX-3；第 10 天再按會重播「預定 X 日開盤送出」，但那天已過；需另存結果，而 `mode_reason` 依規定不得存快照 | **否決**：不實陳述 |
| (c) Idempotency key | 業界標準；重試回同一份結果 | 只擋得住同一對話框重試，擋不了兩個分頁（兩把不同的 key）與直接打 API（沒帶 key），而這兩種正是 N-166 要處理的情境；key 若改必填即在出口加前置條件，違反 EX-2，也違反 `service.py:731-735`「precondition 是出口唯一不能有的東西」 | **不採用**。可留作日後補強，非必要 |
| (d) 鎖內只補未覆蓋批次（覆蓋判定式冪等） | 涵蓋所有來源；保留 EX-3；零前置條件；前端程式碼不需改（成功時 message 原文照印，`EmergencyExitControl.tsx:311-326`），新增回應欄位皆為加法 | 要一句新字面；回應多一個欄位；store 多一個 transaction 方法 | **採用（CEO #76，2026-10-29）**。字面被風控否決就不能合併 |
| (e) partial unique index 當縱深防禦 | 資料層最後防線 | `playbook_directives` 建 `UNIQUE(symbol, batch_no) WHERE rule_id='EMERGENCY' AND settled=0`；若既有 DB 已有重複資料，建 index 會失敗 | 這次不列為必要（[TA]） |

### 重複呼叫時的凍結日（CEO #77）

| 方案 | 說明 | 結論 |
|---|---|---|
| **取較晚者（max）** | `max(既有 emergency_until, shift(as_of, days))`；重複出清會延長凍結期；與確認畫面（`build_exit_confirm`）的預告一致 | **採用（CEO #77，2026-10-29）**，須揭露 |
| 純重複時不延長 | 重複呼叫不動凍結日 | 未採。[TA] 指出 `/today` 的 `exit_confirm` 要跟著改，範圍較大 |

## Decision（決策）

1. **採 (d)，並採 max 凍結日**（CEO #76、#77，2026-10-29）。網路與資料載入在鎖外完成；單一 `BEGIN IMMEDIATE` 內重讀 open 批次、未結算的 EMERGENCY sell（`settled=0`）與 `emergency_until`；只替沒被覆蓋的批次寫新指令；指令與凍結在同一 transaction 寫入。
2. **覆蓋的定義**：(symbol, batch_no) 存在一列 `rule_id='EMERGENCY' AND action='sell' AND settled=0`（C-4）。
3. **凍結日（CEO #77）**：`freeze_until = max(stored_until, calendar.shift(as_of, days))`，不得縮短；值沒變就不寫。回應與 message 用實際生效的值。`build_exit_confirm`（`service.py:173-196`）改用同一條 max 規則，讓 `tests/test_api_playbook.py:300` 的「預告值＝實際值」繼續成立（C-5）。
   - 後果：**重複出清會延長凍結期**，此事須對使用者揭露（見 Consequences 與 Decision 8）。
4. **一律回 200**，不得回 409 或任何 4xx，不得新增必填 header 或 body（EX-2、EX-3；C-6）。
5. **回應形狀**：`directives` 只放本次新寫入的指令；新增 `pending_directives: list[DirectiveLine]` 放先前已在的覆蓋指令，屬加法欄位，`types.ts` 同步加上，前端不強制渲染（C-7）。
6. **message 分三支**（C-8）：
   - 有新指令 → `EMERGENCY_EXIT_RESULT`（計數只算新指令）；
   - 沒有新指令、但有覆蓋 → `EMERGENCY_EXIT_ALREADY_PENDING`（新字面）；
   - 兩者皆無 → `EMERGENCY_EXIT_EMPTY`。
   - 第二支不得沿用 EMPTY（「目前無持有批次」在這時是假的），也不得沿用 RESULT（會變成「已產生 0 批」）。
7. **沿用 N-154 的鎖內重讀模式**；`mode_reason` 照舊即時計算、不儲存（C-9）；store 不 import `wording` 或 `engine`（C-10）。
8. **字面規則（風控閘門）**：
   - 新字面僅放 `wording.py`，**風控核可前不得合併**。
   - 本 ADR 不記載 `EMERGENCY_EXIT_ALREADY_PENDING` 與延長凍結揭露句的實際文字；字面由 risk-compliance-officer 定稿，逐字以風控定稿文件為準。
   - `EMERGENCY_EXIT_ALREADY_PENDING` 是否掛 `EXIT_ATTRIBUTION`：**依風控裁定**（[TA] 指出現行歸屬句寫的是「本次操作中提交」，套在先前提交的指令上並不精確）。
   - 延長凍結的揭露要放在哪些位置（回應 message、確認畫面等）：**依風控裁定**，本 ADR 不預設。
9. **不採**：409、必填 idempotency key、凍結期內重播第一次結果（見 Options）。

## Consequences（後果）

- 好處：
  - 重複呼叫不論來源（雙擊、兩個分頁、網路重送、直接打 API）都不會重複產生賣出指令。
  - 500 不再留下「只凍結、沒指令」的半套狀態（指令與凍結同一 transaction，T-5 驗證）。
  - 重試變安全，且重試的回應會說明先前是否已受理：回 RESULT 代表先前那次沒有受理；回 ALREADY_PENDING 代表先前那次已受理。
  - 保留 EX-3：已有覆蓋的批次不重寫，凍結期間新出現的 open 批次仍可被再出清（F-T2）。
- 代價：多一句要送風控的字面；store 多一個 transaction 方法；回應多一個欄位 `pending_directives`。
- **會延長凍結期（CEO #77），須揭露，揭露字面由風控定稿。**
  - 隔天刻意再按仍會把 `emergency_until` 往後延（取 max）；與確認畫面的預告一致。
  - 同一天純重複呼叫時，max 取值相同，不延長。
  - 在風控定稿並實作前，不得宣稱「重複出清不影響凍結期」。
- 壞處與殘留（[TA]）：
  - `as_of` 是 UTC 日期，台灣時間 08:00 前後的重試可能延長凍結一個交易日。
  - 結算 claim 與 settle 不在同一個 transaction（`store.py:883-898` 與 `store.py:900-959`），兩者之間有極小窗口可能多寫一列；現金有 `min` 保護。
  - 單看 500 仍無法判斷是否已受理（組回應失敗仍可能發生），要靠重試；見附錄 C。
  - 既有 DB 若已有重複資料，本 ADR 不處理（方案 (e) 未採）。
- 被約束：
  - 禁止以 409 或必填 key 處理重複。
  - 持鎖期間禁止任何 I/O（C-3）。
  - N-166 合併前，文案不得暗示「重送是安全的」（見附錄 C，給 NB-6）。
- 前端文案（NB-6）：待 product-manager 依附錄 C 的事實撰寫；任何面向使用者的建議性文案依 CLAUDE.md 第 0 條第 5 點須經風控審查。

## 待決

- CEO 核可方案與凍結日：**已裁**（#76、#77，2026-10-29）。
- 風控（**未經手，擋合併**）：
  1. 新字面 `EMERGENCY_EXIT_ALREADY_PENDING` 定稿。
  2. 該句是否掛 `EXIT_ATTRIBUTION`。
  3. 延長凍結的揭露字面與放置位置（CEO #77 要求須揭露）。
- product-manager：依附錄 C 撰寫 NB-6。
- dev-lead：依附錄 A（C-1～C-11）與附錄 B（T-1～T-6、F-T1～F-T6）實作。
- frontend-engineer（建議，非本 ADR 約束）：把 `invalidateQueries(playbook-today)` 改到 `onSettled`，讓 500 之後模式徽章能反映已寫入的凍結（[TA]）。
- 附錄 D 的 F1～F4 為範圍外發現，另開追蹤，不併入 N-166。
- 落檔後待 coordinator 處理：commit、ADR 索引（若有）同步。本任務只新增本檔，未改其他檔案。

---

## 附錄 A：對實作的約束（交 dev-lead，qa-reviewer 可逐條檢查）

以下 C-1～C-11 逐條轉錄自 [TA]。

- **C-1**：emergency-exit 的所有 DB 寫入（新指令＋`emergency_until`）在同一個 connection 的單一 `BEGIN IMMEDIATE` 內完成。`emergency_exit` 不得再呼叫 `apply_effects` 或 `record_directives`。
- **C-2**：鎖內必須重讀三樣東西，分支判斷只能用這三樣鎖內讀到的值：
  - open 且 `remaining_shares>0` 的批次；
  - 覆蓋集合；
  - `emergency_until`。
- **C-3**：持鎖期間不得呼叫任何 resolver 或網路。原因是 busy_timeout 只有 5s（`data/cache.py:36`）。
  - 價格、指數、日曆、params 都在鎖外先載入。
  - 傳進 store 的指令建構 callback 必須是純函式。
  - 若某個批次在鎖內才出現、鎖外沒預載它的 symbol，走 `NOTHING_LOADED` 加 `DATA_GAP_NOTE` 的既有路徑（風控 R5）。
- **C-4**：覆蓋的定義是：(symbol, batch_no) 存在一列 `rule_id='EMERGENCY' AND action='sell' AND settled=0`。只替「沒被覆蓋」的批次寫新指令。
- **C-5**：凍結日 `freeze_until = max(stored_until, calendar.shift(as_of, days))`，不得縮短。值沒變就不寫。（CEO #77 已裁定採 max。）
  - 回應與 message 要用實際生效的值。
  - `build_exit_confirm`（`service.py:173-196`）要用同一條 max 規則，讓 `tests/test_api_playbook.py:300` 的「預告值＝實際值」繼續成立。
- **C-6**：不論是重複呼叫或已凍結，一律回 200，不得回 409 或任何 4xx（EX-2、EX-3）。不得新增必填的 header 或 body。
- **C-7**：回應的 `directives` 只放本次新寫入的指令。新增 `pending_directives: list[DirectiveLine]`，放先前已在的覆蓋指令，屬於加法欄位，`types.ts` 同步加上。前端不強制渲染這個欄位。
- **C-8**：message 分三支：
  - 有新指令 → `EMERGENCY_EXIT_RESULT`（計數只算新指令）；
  - 沒有新指令、但有覆蓋 → `EMERGENCY_EXIT_ALREADY_PENDING`（新字面，只放 `wording.py`，風控核可前不得合併）；
  - 兩者皆無 → `EMERGENCY_EXIT_EMPTY`。
  - 第二支不得沿用 EMPTY，因為「目前無持有批次」在這時是假的；也不得沿用 RESULT，因為會變成「已產生 0 批」。
- **C-9**：`mode_reason` 照舊即時計算，不得儲存。第二支的 attribution 依風控裁定。
- **C-10**：分層邊界：store 不 import `wording` 或 `engine`；service 不自己開 sqlite connection。`record_directives` 與 `apply_effects` 對 `evaluate_today` 的行為不變，共用 INSERT 時抽出 `_insert_directives(conn, ...)`。
- **C-11**：錯誤處理沿用 N-154 寫法：`if conn.in_transaction: ROLLBACK`，然後原樣 raise。鎖等超過 busy_timeout 視為失敗，不得靜默略過。

## 附錄 B：測試規格

轉錄自 [TA]，沿用 `tests/test_schema_migration_race.py` 的寫法。dev-lead 落地後，以下全綠為準。

**並發測試**

- **T-1 thread 版**：`threading.Barrier(_THREADS=8)`，join 用 `_JOIN_TIMEOUT_S`。
  - 每個 thread 各自建一個 `PlaybookStore`／`PlaybookService`，指向同一個 tmp 檔，同時呼叫 `emergency_exit(today=TUESDAY)`。
  - 再加一個變體：所有 thread 共用同一個 service，模擬 lru_cache 單例。
  - 斷言：
    - failures 為空；
    - 每個 open 批次恰好一列 `rule_id='EMERGENCY' AND settled=0`；
    - `emergency_until == shift(TUESDAY, 20)`；
    - 恰好一個結果的 `directives` 非空，其餘結果都是 `[]` 且 message 為 ALREADY_PENDING。
- **T-2 process 版**：`multiprocessing.get_context("spawn")` 加 `context.Barrier(_PROCESSES=6)`，錯誤寫進 `.err` 檔。斷言同 T-1。
- **T-3 鎖內重讀**（比照 `test_add_missing_columns_loser_rechecks_under_the_lock`）：
  - 先跑一次出清讓贏家寫入，再讓第二次呼叫的鎖外預讀是過時的（例如 monkeypatch 鎖外的 `list_batches` 回傳寫入前的狀態）。
  - 用 `set_trace_callback` 收集 SQL，斷言：出現 `BEGIN IMMEDIATE` 與 `COMMIT`；沒有任何新的 INSERT；指令列數不變。
- **T-4 鎖被占用**（比照 `..._raises_when_the_write_lock_stays_taken`）：
  - holder 先執行 `BEGIN IMMEDIATE`，出清端的 timeout 設 0.05。
  - 斷言：raise 含 "locked" 的錯誤；指令與 `emergency_until` 都沒變。
- **T-5 原子性**：在 transaction 內插入第一列後 monkeypatch 讓它 raise。斷言：零指令列、`emergency_until` 沒變、`not in_transaction`。這一條同時證明附錄 C 的狀態 (ii) 已經消失。
- **T-6 鎖內零 I/O**：Fake price/index service 記錄呼叫序號，與 trace 合併排序。斷言所有載入呼叫都早於 `BEGIN IMMEDIATE`。

**功能測試**

- **F-T1**：同一天循序呼叫兩次。第二次零新列、回 ALREADY_PENDING、狀態完全不變。
- **F-T2（EX-3）**：出清並結算、批次轉 closed 之後，再 seed 一個新的 open 批次。再次出清恰好替新批次寫一列。`test_playbook_exit_matrix.py:167-178` 必須照樣通過。
- **F-T3**：隔天再按，且覆蓋指令尚未結算。零新列，凍結日為 max（CEO #77：此時凍結日被延長為新算值）。
- **F-T4**：已存的凍結日晚於新算出的值時，凍結日不縮短。
- **F-T5**：去重之後結算，executed 數等於批次數，現金只入帳一次。
- **F-T6**：什麼都沒持有時，EMPTY 分支維持不變。
- **API 測試**：用 TestClient 連 POST 兩次。兩次都是 200；第二次 `directives==[]`、`pending_directives` 非空。全套測試裡不得出現 409。

## 附錄 C：500 時能不能判斷請求是否已被處理（給 product-manager 寫 NB-6 的事實）

轉錄自 [TA] Q5，皆為讀碼判定、[TA] 未執行程式。

**現況：不能。**

- 500 的回應本文是 Starlette 預設的 `Internal Server Error`，因為沒有自訂 handler。
- 前端只顯示「全部出清送出失敗：Internal Server Error」（[qa-automation] A3）。
- 失敗時前端不會刷新 `playbook-today`，只有成功時才刷（`frontend/app/lib/queries.ts:456-463`）。

500 發生後，後端實際可能處於三種狀態，前端分不出來：

| 狀態 | 何時發生 | 後端實際狀態 |
|---|---|---|
| (i) 什麼都沒寫 | 在 `service.py:837` 之前失敗 | 無變化 |
| (ii) 只寫了凍結，沒寫賣出指令 | 在 `837-847` 與 `848-868` 這兩個 transaction 之間失敗 | 已凍結，但沒有任何賣出指令 |
| (iii) 全部寫完 | 在組回應時失敗（`api/playbook.py:540-551`） | 已凍結，賣出指令也已寫入 |

- 連 `/today` 也分辨不了 (ii) 和 (iii)：`TodayResponse` 不揭露待執行的 EMERGENCY 指令（`api/playbook.py:219-260`），而 mode 在兩種狀態下都是 `emergency_frozen`。
- 網路斷線、沒收到回應，也是同樣的不確定。
- 現況下重試並不安全：在 (iii) 時重試會產生重複的賣出指令。

**本 ADR 落地後（[TA]）：**

- 寫入改成全有或全無，(ii) 消失。
- 500 本身仍然無法判斷，因為 (iii) 的組回應失敗依然可能發生。
- 但重試變安全，且重試的回應會說明真相：回 RESULT 代表先前那次沒有受理；回 ALREADY_PENDING 那一支代表先前那次已經受理。

**給 NB-6 的界線：** N-166 合併前，文案不得暗示「重送是安全的」。

## 附錄 D：範圍外發現（建議另開追蹤，不併入 N-166）

轉錄自 [TA]。

- **F1（[TA] 已讀碼確認，建議嚴重度 medium）**：出清前已寫入、尚未結算的 R 系列買進指令，出清後仍會在 T+1 結算成 open 批次。
  - 依據：`settle_pending` 不檢查模式（`service.py:258-315`），`emergency_exit` 也不取消待執行的買單。
  - 後果：與 message 的「R 系列自 {executed_at} 起暫停」矛盾。這也是 EX-3 再出清在實務上必要的原因。
  - 需要 PM、風控、CEO 定調。
- **F2（low）**：claim 與 settle 分屬兩個 transaction（`store.py:883-898` 與 `store.py:900-959`），即 Consequences 殘留風險所指的窗口。
- **F3（潛在，[TA] 稱目前無 API 可觸發）**：現行凍結日是覆寫，若日後開放修改 `emergency_freeze_trading_days`，可以靠再出清縮短凍結；C-5 的 max 規則已一併封住。
- **F4（[TA] 標為未查證）**：凍結期間 S/P 系列照常評估，可能替已有待執行 EMERGENCY 指令的批次再產生賣出指令。建議 qa-automation 驗證。

## 附錄 E：[TA] 列出的相關檔案

路徑前綴 `/home/user/AICompany/`：

- `apps/stock-desk/backend/app/api/playbook.py`
- `apps/stock-desk/backend/app/playbook/service.py`
- `apps/stock-desk/backend/app/playbook/store.py`
- `apps/stock-desk/backend/app/playbook/engine.py`
- `apps/stock-desk/backend/app/data/sqlite_util.py`
- `apps/stock-desk/backend/app/settings/migrations.py`（N-156 的鎖模式在這裡，不在 `settings/store.py`）
- `apps/stock-desk/backend/tests/test_schema_migration_race.py`
- `apps/stock-desk/backend/tests/test_playbook_exit_matrix.py`
- `apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx`
- `apps/stock-desk/frontend/app/lib/queries.ts`
- `work/reviews/快市排程-風控前置意見.md`
- `work/reviews/2026-10-29-N163N164沙盒出清-代跑交件-qa-automation.md`

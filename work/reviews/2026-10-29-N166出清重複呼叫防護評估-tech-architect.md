# N-166 EMERGENCY_EXIT 重複呼叫防護評估（ADR-0033 草案）

- 審查者：tech-architect
- 日期：2026-10-29
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

**結論：需要 CEO 決策，同時要送風控。** 我建議採方案 (d)「覆蓋判定式冪等」，否決 (a)、(b)，(c) 不採用。

- **現況**：重複呼叫一定會雙寫，不需要並發，循序打兩次就會發生。每次都回 200。第二次以後會再產生一整組相同的賣出指令。隔天再按會把凍結期往後延。
- **(a) 必須否決**：風控 EX-3 明定「凍結期間 SELL 類＋再次 EXIT 可執行」，(a) 直接違反，也會讓既有測試失敗。
- **(d) 的做法**：在 `BEGIN IMMEDIATE` 鎖內重讀狀態，只替「還沒有未結算 EMERGENCY 賣出指令」的 open 批次產生新指令。凍結日取 max，不縮短。一律回 200。
- **擋合併的風控項**：(d) 需要一句新字面（「已有待執行出清」這支），必須先送 risk-compliance-officer。這句定稿前不能合併。
- **需要新 ADR**：草案在下方，編號暫定 0033。

---

## 2. 各部門回報

- **tech-architect（本人，唯讀）**：讀了 api/service/store/engine、N-154/N-156 的鎖模式、兩份驗收證據、風控前置意見、前端出清元件與 mutation，以及相關測試。產出現況判定、方案比較、約束、測試規格和 ADR 草案。沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。
- **其他部門**：本次未參與。
- **應把關但尚未經手的有兩個**：
  - risk-compliance-officer：要審新字面，以及「已有待執行出清」這支要不要掛歸屬語。
  - product-manager：要用第 5 題的事實寫 NB-6。

---

## 3. 驗證

以下判定全部來自讀碼，附檔案:行號。我沒有跑程式。dev-lead 落地後，要以下方的測試規格全綠為準。

### Q1 現況判定

路徑前綴：`apps/stock-desk/backend/app/`，下同。

1. **沒有任何「已凍結」或「已出清」的檢查**
   - 端點 `api/playbook.py:536-551` 直接呼叫 `service.emergency_exit()`。
   - 全 app 沒有任何 `exception_handler`（grep 結果為 0）。
   - `playbook/service.py:722-740` 的 docstring 明寫「never gated on ... a freeze」（風控 R11）。

2. **同一天重複呼叫：賣出指令重複產生，凍結期不變**
   - 批次在 T+1 結算前一直是 open。結算只發生在 `playbook/store.py:900-959`，測試 `tests/test_playbook_settlement.py:216-217` 也釘住「出清後、結算前批次仍是 open」。
   - `service.py:754-756` 只篩 `status=="open" and remaining_shares>0`，不看是否已有待執行的 EMERGENCY 指令。所以每次都替同一批次再產生一行 sell。
   - 寫入走 `store.py:784-824`，是純 INSERT。`playbook_directives` 沒有唯一約束（`store.py:129-153`）。
   - 回應是 200，message 再說一次「已產生 N 批…」。
   - 凍結日：`service.py:750` 用 `shift(as_of, 20)`，同一天算出來的值相同。`store.py:563-564` 直接覆寫，所以不會延長。

3. **隔天再呼叫（還在凍結中）**
   - 凍結期會延長：`emergency_until` 被覆寫成 `shift(新的一天, 20)`。
   - 如果這時還沒結算（例如當天沒抓到開盤價，被列為 unsettled），會再重複產生賣出指令。
   - 如果已經結算、批次是 closed，會走 EMPTY 分支，不產生指令，但凍結期一樣延長。

4. **重複指令結算後的後果**
   - 現金不會被重複入帳：`store.py:943` 有 `min(remaining, shares)` 擋住。
   - 但 R16 指令日誌會出現兩筆已執行的賣出，股數是實際的兩倍。結算摘要裡的 executed 數也會翻倍（`service.py:303-313`）。
   - 更嚴重的是：本產品不下單（風控 R10），使用者是拿著回應自己去券商下單。他會收到兩次「賣出 N 批」。

5. **並發時會雙寫**
   - 端點是同步 `def`，在 threadpool 裡跑。整條路徑沒有任何鎖。
   - `service.py:742-745` 先讀批次、打網路，`837-847` 才寫凍結，`848-868` 才寫指令。
   - 凍結與指令分屬兩個獨立 transaction（`store.py:466-476`、`store.py:792`）。

6. **修法必須在鎖內做檢查**：既然循序呼叫就會雙寫，修法就不能只在鎖外先查一次。檢查一定要放進鎖內。

### Q2 方案比較

| 方案 | 怎麼配合 `BEGIN IMMEDIATE` 鎖內重讀 | 對前端的影響 | 新字面 | 判定 |
|---|---|---|---|---|
| (a) 已凍結就回 409，附固定 detail | 鎖內重讀 `emergency_until`，若凍結中就 ROLLBACK 並回 409。實作最簡單 | `EmergencyExitControl.tsx:263-266` 會顯示「全部出清送出失敗：…」，但其實出清已經生效，會誤導使用者；第二個分頁也會看到「失敗」 | 要，detail 字串要送風控 | **否決**，理由見表下 |
| (b) 同一凍結期內重複呼叫回傳第一次的結果 | 鎖內重讀凍結狀態，凍結中就讀出儲存的第一次結果 | 不需要改 | 沿用現有字面，但會變成不實陳述 | **否決**：同樣違反 EX-3；第 10 天再按會重播「預定 X 日開盤送出」，但那天已經過了；還要另存結果，而 mode_reason 依規定不得存快照 |
| (c) idempotency key | 新增一張 key→結果 的表，鎖內查 key | 前端要產生 key，並在重試時沿用 | key 若改成必填，錯誤字面要送風控 | **不採用**：見表下 |
| (d) 覆蓋判定式冪等 | 鎖外載入資料；鎖內重讀 open 批次、未結算的 EMERGENCY sell、`emergency_until`；只寫沒被覆蓋的批次；凍結日取 max；指令與凍結同一個 transaction | 前端程式碼不需要改，因為成功時 message 是原文照印（`EmergencyExitControl.tsx:311-326`）。新增的回應欄位都是加法 | 要一句「已有待執行出清」 | **採用** |

**(a) 否決理由**
- 違反 EX-3（凍結期間可再次 EXIT）與 EX-2（出口不得有前置條件）。出處：`work/reviews/快市排程-風控前置意見.md:43-45`；該處也寫明省略 EX-2/EX-4，裁定自始不成立。
- 會打破 `tests/test_playbook_exit_matrix.py:167-178` 的 emergency_frozen 案例。
- 會擋掉真實存在的合法再出清，見第 4 節的 F1。
- 變體 (a′)「只有全部批次都已覆蓋才回 409」：比 (a) 好，但前端仍會呈現成「失敗」，而且一樣要新字面，不如 (d)。

**(c) 不採用的理由**
- 只擋得住同一對話框重試，擋不了兩個分頁（兩把不同的 key）和直接打 API（沒帶 key），而這兩種正是 N-166 要處理的情境。
- 如果把 key 改成必填，等於在出口加前置條件，違反 EX-2，也違反 `service.py:731-735`「precondition 是出口唯一不能有的東西」。
- 可以留作日後補強，非必要。

**另外考慮過的 (e)：partial unique index 當縱深防禦**
- 做法：`playbook_directives` 建 `UNIQUE(symbol, batch_no) WHERE rule_id='EMERGENCY' AND settled=0`。
- 若既有 DB 已有重複資料，建 index 會失敗。這次不列為必要。

### Q5 附帶問題：500 時能不能判斷請求是否已被處理（給 product-manager 的事實）

**現況：不能。**
- 500 的回應本文是 Starlette 預設的 `Internal Server Error`，因為沒有自訂 handler。
- 前端只顯示「全部出清送出失敗：Internal Server Error」（qa-automation A3）。
- 失敗時前端不會刷新 `playbook-today`，只有成功時才刷（`frontend/app/lib/queries.ts:456-463`）。

500 發生後，後端實際可能處於三種狀態，前端分不出來：

| 狀態 | 何時發生 | 後端實際狀態 |
|---|---|---|
| (i) 什麼都沒寫 | 在 `service.py:837` 之前失敗 | 無變化 |
| (ii) 只寫了凍結，沒寫賣出指令 | 在 `837-847` 與 `848-868` 這兩個 transaction 之間失敗 | 已凍結，但沒有任何賣出指令 |
| (iii) 全部寫完 | 在組回應時失敗（`api/playbook.py:540-551`） | 已凍結，賣出指令也已寫入 |

- 連 `/today` 也分辨不了 (ii) 和 (iii)。`TodayResponse` 不揭露待執行的 EMERGENCY 指令（`api/playbook.py:219-260`），而 mode 在兩種狀態下都是 `emergency_frozen`。
- 網路斷線、沒收到回應，也是同樣的不確定。
- 現況下重試並不安全：在 (iii) 時重試會產生重複的賣出指令。

**N-166 落地後：**
- 寫入改成全有或全無，(ii) 這種狀態消失。
- 500 本身仍然無法判斷，因為 (iii) 的組回應失敗依然可能發生。
- 但重試變安全了，而且重試的回應會說明真相：
  - 回 RESULT：代表先前那次沒有受理。
  - 回「已有待執行出清」：代表先前那次已經受理。

**給 NB-6 的界線：**
- N-166 合併前，文案不得暗示「重送是安全的」。
- 建議 frontend-engineer 把 `invalidateQueries(playbook-today)` 改到 `onSettled`，讓 500 之後模式徽章能反映已寫入的凍結。

---

## 4. 下一步

1. **CEO 決策**：核可方案 (d)，並決定隔天再按時凍結期的處理。
   - 預設 max：會延長，與確認畫面的預告一致。
   - 另一個選項是「純重複時不延長」：這樣 `/today` 的 `exit_confirm` 要跟著改，範圍比較大。
2. **risk-compliance-officer**：審新字面 `EMERGENCY_EXIT_ALREADY_PENDING`，並裁定這支要不要掛 `EXIT_ATTRIBUTION`。現行那句寫的是「本次操作中提交」，套在先前提交的指令上並不精確。
3. **後續交接**：
   - tech-writer 落檔 ADR（先確認編號）。
   - dev-lead 依下方約束與測試實作。
   - F1 另開追蹤項。

---

### 對實作的約束（交 dev-lead，qa-reviewer 可逐條檢查）

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
- **C-5**：凍結日 `freeze_until = max(stored_until, calendar.shift(as_of, days))`，不得縮短。值沒變就不寫。
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

### 測試規格（沿用 `tests/test_schema_migration_race.py` 的寫法）

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
- **T-3 鎖內重讀（比照 `test_add_missing_columns_loser_rechecks_under_the_lock`）**：
  - 先跑一次出清讓贏家寫入，再讓第二次呼叫的鎖外預讀是過時的（例如 monkeypatch 鎖外的 `list_batches` 回傳寫入前的狀態）。
  - 用 `set_trace_callback` 收集 SQL，斷言：出現 `BEGIN IMMEDIATE` 與 `COMMIT`；沒有任何新的 INSERT；指令列數不變。
- **T-4 鎖被占用（比照 `..._raises_when_the_write_lock_stays_taken`）**：
  - holder 先執行 `BEGIN IMMEDIATE`，出清端的 timeout 設 0.05。
  - 斷言：raise 含 "locked" 的錯誤；指令與 `emergency_until` 都沒變。
- **T-5 原子性**：在 transaction 內插入第一列後 monkeypatch 讓它 raise。斷言：零指令列、`emergency_until` 沒變、`not in_transaction`。這一條同時證明 Q5 的狀態 (ii) 已經消失。
- **T-6 鎖內零 I/O**：Fake price/index service 記錄呼叫序號，與 trace 合併排序。斷言所有載入呼叫都早於 `BEGIN IMMEDIATE`。

**功能測試**
- **F-T1**：同一天循序呼叫兩次。第二次零新列、回 ALREADY_PENDING、狀態完全不變。
- **F-T2（EX-3）**：出清並結算、批次轉 closed 之後，再 seed 一個新的 open 批次。再次出清恰好替新批次寫一列。`test_playbook_exit_matrix.py:167-178` 必須照樣通過。
- **F-T3**：隔天再按，且覆蓋指令尚未結算。零新列，凍結日為 max。
- **F-T4**：已存的凍結日晚於新算出的值時，凍結日不縮短。
- **F-T5**：去重之後結算，executed 數等於批次數，現金只入帳一次。
- **F-T6**：什麼都沒持有時，EMPTY 分支維持不變。
- **API 測試**：用 TestClient 連 POST 兩次。兩次都是 200；第二次 `directives==[]`、`pending_directives` 非空。全套測試裡不得出現 409。

### ADR 草案（給 tech-writer 落檔；編號暫定 0033，main 目前最大是 0032，落檔前請確認）

```markdown
# ADR-0033：stock-desk EMERGENCY_EXIT 重複呼叫的覆蓋判定式冪等

- 狀態：proposed
- 日期：2026-10-29
- 決策者：tech-architect（草案）、CEO（核可）、risk-compliance-officer（新字面）

## Context（背景）
N-163 實機：修鎖前 dblclick 或同 task 連點兩次，會送出 2 筆 POST /api/playbook/emergency-exit。
前端 ref 鎖（74979dd）只擋得住同一對話框；兩個分頁、網路重送、直接打 API 仍會重複。
現況（service.py:742-868）：不檢查已出清。批次在 T+1 結算前仍是 open，所以每次呼叫都重產整組
賣出指令（純 INSERT、無唯一約束），隔天再按還會覆寫並延長凍結。凍結與指令分屬兩個 transaction，
500 時可能只寫了凍結。出清不可逆，而使用者是依回應自行到券商下單（風控 R10）。
限制：風控 EX-2（出口不得有前置條件）、EX-3（凍結期間可再次 EXIT）；mode_reason 禁存快照。

## Options（選項比較）
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (a) 已凍結回 409 | 最簡單 | 違反 EX-2/EX-3；前端顯示成「送出失敗」 | 擋掉合法的再出清 |
| (b) 凍結期內回傳第一次結果 | 前端零改動 | 違反 EX-3；重播已過期的事實；需儲存結果 | 不實陳述 |
| (c) Idempotency key | 業界標準；重試回同一份結果 | 擋不了兩個分頁或沒帶 key 的呼叫；改成必填就違反 EX-2 | 防護不完整 |
| (d) 鎖內覆蓋判定 | 涵蓋所有來源；保留 EX-3；零前置條件 | 要一句新字面；回應多一個欄位 | 字面被否決就不能合併 |

## Decision（決策）
採 (d)。網路與資料載入在鎖外完成。單一 BEGIN IMMEDIATE 內重讀 open 批次、
未結算的 EMERGENCY sell（settled=0）與 emergency_until，只替沒被覆蓋的批次寫新指令，
凍結日取 max(stored, shift(as_of, days))、不縮短；指令與凍結同一 transaction 寫入。
一律回 200。message 分三支：RESULT／ALREADY_PENDING（新字面，須風控核可）／EMPTY。
回應新增 pending_directives。build_exit_confirm 用同一條 max 規則。沿用 N-154 的鎖內重讀模式。

## Consequences（後果）
- 好處：重複呼叫不論來源都不會重複產生賣出指令；500 不再留下「只凍結」的半套狀態；重試變安全，
  而且重試的回應會說明先前是否已受理。
- 代價：多一句要送風控的字面；store 多一個 transaction 方法；回應多一個欄位。
- 壞處與殘留：
  - 隔天刻意再按仍會延長凍結（與確認畫面的預告一致）。
  - as_of 是 UTC 日期，台灣時間 08:00 前後的重試可能延長凍結一個交易日。
  - 結算 claim 與 settle 不在同一個 transaction，兩者之間有極小窗口可能多寫一列（現金有 min 保護）。
  - 單看 500 仍無法判斷是否已受理，要靠重試。
- 約束：禁止以 409 或必填 key 處理重複；持鎖期間禁止任何 I/O。
```

### 範圍外發現（建議另開追蹤，不併入 N-166）

- **F1（已讀碼確認，建議嚴重度 medium）**：出清前已寫入、尚未結算的 R 系列買進指令，出清後仍會在 T+1 結算成 open 批次。
  - 依據：`settle_pending` 不檢查模式（`service.py:258-315`），`emergency_exit` 也不取消待執行的買單。
  - 後果：與 message 的「R 系列自 {executed_at} 起暫停」矛盾。這也是 EX-3 再出清在實務上必要的原因。
  - 需要 PM／風控／CEO 定調。
- **F2（low）**：claim 與 settle 分屬兩個 transaction（`store.py:883-898` 與 `store.py:900-959`），就是 ADR 殘留風險裡提到的那個窗口。
- **F3（潛在，目前無 API 可觸發）**：現行凍結日是覆寫，若日後開放修改 `emergency_freeze_trading_days`，可以靠再出清縮短凍結。C-5 的 max 規則已一併封住。
- **F4（未查證）**：凍結期間 S/P 系列照常評估，可能替已有待執行 EMERGENCY 指令的批次再產生賣出指令。建議 qa-automation 驗證。

### 相關檔案

- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/sqlite_util.py
- /home/user/AICompany/apps/stock-desk/backend/app/settings/migrations.py（N-156 的鎖模式在這裡，不在 `settings/store.py`）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_schema_migration_race.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_playbook_exit_matrix.py
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts
- /home/user/AICompany/work/reviews/快市排程-風控前置意見.md
- /home/user/AICompany/work/reviews/2026-10-29-N163N164沙盒出清-代跑交件-qa-automation.md

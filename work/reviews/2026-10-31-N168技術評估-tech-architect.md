# N-168 技術面評估（ADR-0034 草案）

- 審查者：tech-architect
- 日期：2026-10-31
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-168 出清後待結算 R 買單：技術面評估（tech-architect）

## 1. 本次結論

**技術面兩案都做得出來，我沒有否決 B-2a 或 A。PM 方案比較裡有兩處技術前提不成立，需要更正。** 選哪一案是產品取捨，由 CEO 裁示；純就技術面，我略偏 B-2a。

**更正 1：B-2a 也要改出清的 transaction。**
- PM 的總覽表寫「B-2a 不改出清 transaction」，這不成立。
- 「出清後成交」標示無法由既有資料可靠推得（見第 1 題）。要可靠，就必須在出清的同一個 `BEGIN IMMEDIATE` 內，替待成交買單打一個戳記。
- 所以 A 與 B-2a 對出清 transaction 的改動量相同：多一次鎖內 SELECT，加一次對同一批列的 UPDATE。差別只在 UPDATE 寫的內容。
- 規模兩案都屬「中」。B-2a 不是「小到中」。

**更正 2：A 不必然與 ADR-0033 衝突。**
- 只要把撤回或戳記設計成加法，就與 C-1／C-2／C-7／C-8 沒有字面衝突。加法的意思是：寫入放在同一個 transaction、多一項鎖內讀取但不參與三支分支的選擇、新增獨立欄位、字面用附加句。
- B-2a 也一樣。
- 兩案都要另立 **ADR-0034**，性質是「補充 ADR-0033、不取代」。0033 維持 accepted，不原地改寫（ADR-0001:18）。
- 例外：如果風控要求 message 新增第四支，就會與 C-8「分三支」直接衝突。這時要改走「ADR-0034 取代 0033」：完整重述 C-1～C-11，0033 標 superseded。

**排序：N-168 排在 N-166 之後，不合併成同一分支。**
- 理由是 ADR-0033 自己明文規定 F1「另開追蹤，不併入 N-166」（`docs/adr/0033-…:115`、`:216-219`）。
- 出清側改動要等 N-166 合併後再做。B-2a 的結算與 schema 部分可以先平行開發（下文稱 N-168a）。

**VETO（架構否決），共 5 條：**
- **VETO-1**：不得用「讀取時比較 `emergency_until`／批次日期／出清日」來推導標示。也不得在結算時用「as_of 是否落在凍結期」來判定。理由見第 1 題。
- **VETO-2**：待成交 R 買單不得併入 C-4 的覆蓋集合，也不得放進 `directives` 或 `pending_directives` 欄位。transaction 內不得呼叫 `store.pending_directives(...)`。
- **VETO-3（僅 A 案）**：撤回不得用 `missed` 狀態表示，不得經過 `store.settle()`，也不得刪除指令列（違反 R16 留存）。
- **VETO-4**：N-168 不得併入 N-166 的同一分支或同一 PR。這違反 ADR-0033:115。
- **VETO-5**：N-168 在出清時的寫入，不得放在 N-166 那個 `BEGIN IMMEDIATE` 之外另開 transaction。這違反 C-1。

**範圍外新發現 F5（讀碼判定，未執行，建議 medium-high，另開追蹤）**
- 現象：排程日（週二、四）重複呼叫 `GET /today`，會替同一個 `planned` 批次重複寫入 R1 買單。
- 後果：T+1 結算時，現金會被重複扣款，股數卻只是被覆寫成一次的量。
- 這直接影響 N-168：「待成交 R 買單」可能出現同一批次有多列的情況。
- 證據見第 3 節。

---

## 2. 各部門回報

- **tech-architect（本人，唯讀）**
  - 讀過的資料：PM 方案比較、ADR-0033、ADR-0001、我 10-29 的評估、風控 10-31 的 N-166 字面審查、追蹤清單。
  - 讀過的程式：`playbook/{models,store,service,engine}.py`、`api/playbook.py`、`data/calendar.py`、`data/sqlite_util.py`、前端 `types.ts`／`playbookView.ts`／`queries.ts`、`tests/test_playbook_settlement.py`。
  - 沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案，也沒有跑程式。
- **應經手但尚未經手**
  - risk-compliance-officer：附加句的字面、標示語意（見 Q1 末段），以及是否需要第四支 message。
  - qa-automation：重現 F5。
  - dev-lead：落地。
  - CEO：選案。

---

## 3. 驗證

以下判定全部來自讀碼，沒有執行。路徑前綴為 `apps/stock-desk/backend/app/`。

### Q1「出清後成交」標示的資料來源

**結論：既有資料推不出來，需要新欄位。**

推不出來的理由：
1. **出清日沒有被保存。**
   - 出清只保存 `emergency_until`（`playbook/store.py:563-564`）。
   - `executed_at` 只存在回應裡（`models.py:575`），沒有寫進 DB。
   - EMPTY 分支一列 EMERGENCY 指令都不寫（`service.py:754-756`、`:848-868`）。然而「只有 planned 批次，又有待成交買單」正是 F1 的典型情境，這時 DB 裡沒有任何出清痕跡。
2. **不能用 `emergency_until` 往回推出清起點。**
   - N-166 的 C-5 改採 max 之後，凍結日會被延長。
   - 參數版本可能已變更（鐵律④）。
   - 日曆在最後一根 K 線之後走 weekday fallback（`service.py:184-186`）。
   - 這三點都會讓往回推的結果失準。
   - 另外，模式判定 `data_date <= emergency_until` 沒有下界（`engine.py:354`），所以單靠 until 無法框出凍結期間。
3. **批次的 `entry_date` 等於買單的 `execution_date`（`store.py:934`），可能早於出清日。**
   - 例如 T1 沒抓到開盤價，出清之後才補結算。
   - 這時「出清後成交」在事實上是錯的。
   - 建議風控把標示的語意改成「出清當時尚未結算、不在該次出清範圍」。這屬於字面，交風控決定。
4. **不能在結算時以「as_of ≤ emergency_until」判定（VETO-1）。**
   - 結算是惰性的：只在 `GET /today`（`service.py:631`）或 `POST /settle`（`api/playbook.py:437-445`）時才跑。scheduler 沒有呼叫 playbook（grep 結果為 0）。
   - 使用者若在凍結結束後才回來開頁，標示就會漏掉。
5. **在讀取時推導的標示，凍結一結束就會消失。** 這做不到 AC-3 要求的「重新整理後仍存在」。

標示來源的方案比較：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| L1 讀取時比較日期 | 不需遷移 | 推不出出清起點 | VETO-1 |
| L2 結算時看是否在凍結期 | 不改出清路徑 | 惰性結算會漏標 | VETO-1 |
| L3 凍結起始時在 `playbook_state` 存 directive id 水位線（max id），加一個批次欄位 | 只需遷移一欄 | 正確性隱含地依賴兩件事：AUTOINCREMENT 單調遞增、凍結期間 R 不產生指令 | 可行，但不直觀 |
| **L4（建議）** 出清 transaction 內替待成交買單打戳記，加一個批次欄位 | 每列有明確的事實紀錄，冪等，好測試；FR-2／FR-7 可以直接查 | 需遷移兩欄 | 最低 |

L4 的 schema 遷移影響，比照 N-154：
- 在 `_MIGRATIONS`（`store.py:161-170`）加兩筆 nullable TEXT：一筆在 `playbook_directives`（戳記），一筆在 `playbook_batches`（標示）。
- 由 `add_missing_columns` 在 `BEGIN IMMEDIATE` 下補欄（`data/sqlite_util.py:84-124`），多 process 競態已有處理。
- `status TEXT` 沒有 CHECK 約束（`store.py:148`）。

**最大的實作陷阱：`save_batch` 是整列 `INSERT OR REPLACE`（`store.py:371-400`）。**
- 新的批次欄位必須同步加進四處：`_BATCH_COLUMNS`（`:172-188`）、`_row_to_batch`（`:335-369`）、`save_batch`、`BatchState`（`models.py:201-228`）。
- 漏掉任何一處，`roll_peak_closes`（`store.py:410-417`）每天都會把標示洗回 NULL。

其他後果：
- 既有 DB 的舊批次無法回填，因為沒有凍結歷史可依據。
- 若部署回滾到舊碼，舊的 `save_batch` 會把標示清掉。

### Q2 改選 A 的影響面

**新增指令狀態。**
- 狀態值加在 `DirectiveStatus`（`models.py:47`）。DB 不需遷移。
- 撤回時同一個 UPDATE 寫四件事：`status=<新值>`、`settled=1`、`settled_at`、`settled_open_price` 為 NULL。
- `settled=1` 帶來兩個效果：
  - `pending_directives` 會排除這些列（`store.py:849`）。
  - `claim_directive` 的 `WHERE settled=0` 會讓這些列永遠不會被結算（`store.py:895`）。
- `playbook_schedule` 對應列的狀態也要在同一個 conn 內更新。現行 `_mark_schedule`（`store.py:961-976`）自己開 connection，要改成接收 conn 參數的版本（C-10）。

**R3 重試上限與 MISSED 語意。**
- 撤回不經過 `settle()`，所以 `missed_count` 不會加一（`store.py:915-920`），`defer_count` 也不變。
- R3 上限（`engine.py:806`、`:839`）因此不受撤回影響。
- MISSED 的定義是「開盤價超出價帶」（`engine.py:1308-1318`），撤回不能套用（VETO-3）。

**前端呈現。**
- `types.ts:1621` 的狀態 union 要加新值。
- `playbookView.ts:204` 是窮舉的 `Record`，少一個 label 就編譯不過，正好可以當強制機制。label 字面交風控。
- 目前沒有任何 API 對外提供 `directive_log`（grep 結果為 0）。所以撤回的列只會出現在出清回應的新欄位，以及 `/today` 的新欄位（若做）。
- W-A4 不建議放進 `SETTLEMENT_SUMMARY`（`wording.py:376-379`）。那句的意思是「依開盤價判定」，而撤回根本不經過結算。

**W-A5／W-A6 需要額外持久化。**
- W-A6 是重送時再說一次「先前已撤回」。要做到這點，必須知道本次凍結從何時開始，因此要在 `playbook_state` 存一個凍結起點的 KV（不需遷移），而且只在進入新凍結時寫入。
- W-A5 可以等 R1 再替同一批次排入時，由 service 查該批次被撤回過的列。

**與 ADR-0033 的對照：**

| 約束 | 與 A 的關係 | 判定 |
|---|---|---|
| C-1（`0033:124`） | 撤回在同一個 `BEGIN IMMEDIATE` 內做，就符合 C-1。括號裡列舉的寫入集合要由 ADR-0034 擴充 | 不衝突 |
| C-2（`0033:125-128`） | 鎖內多讀第四樣。第四樣只決定附加句與新欄位，不參與三支分支的選擇 | 不衝突，ADR-0034 要明寫 |
| C-7（`0033:138`） | 新增獨立欄位。不得混入 `directives`／`pending_directives` | 不衝突（VETO-2） |
| C-8（`0033:139-143`） | 「無持有、但有撤回」會落到 EMPTY。EMPTY 說的「目前無持有批次」仍然為真，只是資訊不完整。用附加句就不衝突，比照風控 S2／S3／S6 的組合方式（風控 10-31 審查:79-82） | 附加句不衝突；**若開第四支就衝突，要另立取代 0033 的 ADR** |

PM 寫「A 衝突、需修訂 0033」，只有在開第四支的情況下才成立。

### Q3 transaction 內「待成交 R 買單」的界定條件

條件寫法：

```sql
action = 'buy' AND settled = 0 AND status = 'pending'
```

- 必須在同一個 conn 的同一個 `BEGIN IMMEDIATE` 內讀取。
- 與 C-4 的覆蓋條件（`rule_id='EMERGENCY' AND action='sell' AND settled=0`，`0033:133`）用 `action` 就能互斥。
- **不要加 `execution_date` 條件。** 過期未結算的買單（沒抓到開盤價）仍然算待成交。這與風控 CEO-1 對 EMERGENCY 指令的處理精神一致。
- **不要用 `store.pending_directives(on_or_before=...)`**，原因有兩個：
  - 它會濾掉 `execution_date > as_of` 的列（`store.py:853-855`），而 T1 買單正是主要情境。
  - 它自己開 connection（`store.py:856`），違反 C-10。
- **不要用 `rule_id LIKE 'R%'`**：這樣會誤納 `REBALANCE`。
- 目前唯一會產生 buy 的地方是 `engine.py:952-958`（R1），所以只看 `action='buy'` 就夠。要加一條守門測試，把這件事釘住。
- 依 F5，結果可能出現同一個 (symbol, batch_no) 有多列。揭露時的股數加總，必須依 F5 的處置決定怎麼算。

### Q4 凍結結束後 `planned` 批次的行為

PM 的讀法正確。
- R 的進場條件是：`mode=="normal"`、排程日（週二、四，`data/calendar.py:87-89`）、指數可用（`engine.py:1142`、`:1250-1262`）。
- 符合條件時，每個標的挑 batch_no 最小的 `planned` 批次（`engine.py:699-711`）。
- 凍結要到 `data_date > emergency_until` 才解除（`engine.py:354`）。

**A 案：會再買。**
- 批次 Y 維持 `planned`，計數器都不變。
- 凍結後第一個排程日，R1 會以新的收盤價、重新計算股數（`engine.py:943-958`），再替 Y 產生一筆買單。
- U-A 使用者會因此重複建倉，這是結構性結果。技術上只能靠 W-A5 揭露來緩解。
- 若改把 Y 標成 `skipped`，會變成「名額不補」，這是產品變更，要 CEO 裁示。

**B-2a 案，依結算結果分三種：**
- **成交**：Y 轉 open，R 前進到 Y+1。這是正常的分批推進，不會重複 Y。
  - 但在 U-B（未下單）情境，幻影批次的股數會被計入末批的股數計算（`engine.py:177`），扣過的現金也會影響鐵律①的計算。
- **MISSED**：`missed_count+1`，Y 仍是 `planned`。凍結後依 E-2 重試，與現況一致（AC-5）。
- **一直沒結算**（沒抓到開盤價）：凍結後，`evaluate_today` 會先跑結算（`service.py:631`）。若仍未結算，R 會再替 Y 寫一筆。這是 F5 的變體。

### Q5 實作順序與共用 transaction

**現況。**
- N-166 尚未落地：`service.py:837-868` 仍是 `apply_effects` 加 `record_directives`，兩個獨立的 transaction。
- 兩案都要改同一個 `emergency_exit`，以及 N-166 新增的 store transaction 方法。平行開發一定會在文字與 T-1～T-6 的斷言上衝突。

**順序。**
1. N-166 先合併。
2. N-168 從合併後的 main 線（產品分支）另開分支，做出清側。
3. B-2a 的 N-168a（schema、settle 複製戳記、BatchSnapshot、`/today` 欄位）可以在 CEO 裁示後平行開發，測試時直接 seed 已打戳記的列。
4. A 案幾乎全部在出清側，只能在 N-166 之後做。

**共用 transaction 不會衝突的條件：**
- N-168 的 SELECT 與 UPDATE 都在 C-1 那個 transaction 內完成。
- 以 `IS NULL`（B-2a）或 `status='pending'`（A）為條件。這樣重送時零寫入，F-T1「狀態完全不變」仍然成立。
- T-3 原本的斷言要擴充，加上「也沒有任何 UPDATE」。
- T-5 原子性要涵蓋戳記或撤回的回滾。

**殘留風險。**
- claim 與 settle 分屬兩個 transaction（`store.py:883-898`、`:900-959`），中間有窗口（F2／N-169）。
- 若出清剛好落在這個窗口：買單已被 claim、批次仍是 `planned`，兩案都抓不到這筆，結果是 B-2a 漏標、A 照樣成交。

#### B-2a 約束清單（粗估）

- **C-B1**：待成交買單依 Q3 的條件，在鎖內用同一個 conn 讀取。
- **C-B2**：覆蓋查詢必須含 `action='sell'`。買單不參與覆蓋，也不參與三支分支的選擇。
- **C-B3**：戳記在 C-1 的 transaction 內寫入，三支分支都要寫（含 EMPTY）。用 `WHERE 戳記 IS NULL`，戳記值為出清的 as_of。
- **C-B4**：回應新增一個加法欄位，不得混入 `directives`／`pending_directives`。`types.ts` 同步。
- **C-B5**：message 只能附加句子，不改 `EMERGENCY_EXIT_RESULT`／`EMERGENCY_EXIT_EMPTY`（`wording.py:326-337`），也不改已核可的 S1。store 不 import wording。
- **C-B6**：`settle()` 處理 buy 成交時，把戳記複製到批次標示。MISSED 不加標示。`settle_pending`／`settle_directive` 不加模式判斷。
- **C-B7**：兩個 nullable 欄位經 `_MIGRATIONS` 加入，不回填。批次欄位必須貫穿 `BatchState`、`_BATCH_COLUMNS`、`_row_to_batch`、`save_batch`。
- **C-B8**：`BatchSnapshot`（`models.py:361-375`）帶出標示。engine 只照抄，不做判斷。
- **C-B9**：`/today` 列出「已打戳記且尚未結算」的買單，必須在 `settle_pending` 之後讀取。
- **C-B10**：不得自動替帶標示的批次產生 EMERGENCY 賣單（排除 B-2b）。
- **C-B11**：R、S、P 的引擎邏輯不改。

#### B-2a 測試清單（粗估）

- **T-B1**：EMPTY 分支。只有 Y 的待成交買單，出清後該列被打戳記、出現在新欄位，零賣單。
- **T-B2**：RESULT 分支。只替 X 寫賣單，Y 被列出，覆蓋集合不含買單。
- **T-B3**：同一天重送。trace 中沒有 INSERT 也沒有 UPDATE，回 ALREADY_PENDING，清單仍在。
- **T-B4**：結算成交後 Y 為 open 並帶標示。標示要在以下動作後都還在：`roll_peak_closes`、再跑一次 `evaluate_today`、建新的 store 實例。
- **T-B5**：MISSED 情境。不加標示，`missed_count+1`。
- **T-B6**：超過 until 才結算，仍有標示。這條用來證明 L2 的漏洞已封住。
- **T-B7**：出清時已過期的待成交買單也會被打戳記。
- **T-B8**：凍結結束後才產生的買單、出清前就已結算的買單，都不加標示。
- **T-B9**：Y 轉 open 後再出清（AC-7、F-T2），恰好替 Y 寫一列。
- **T-B10**：擴充 T-1／T-2。每一列只被打一次戳記。
- **T-B11**：擴充 T-5。戳記會一起回滾。
- **T-B12**：舊 DB 遷移與競態，比照 `test_schema_migration_race.py`。
- **T-B13**：凍結期間 Y 轉 open 後，沒有任何自動產生的 EMERGENCY 賣單。
- **T-B14**：`/today` 在結算前列出、結算後移除。
- **T-B15**：凍結後第一個排程日，R 處理的是 Y+1。
- **T-B16**：守門測試，確認只有 R1 會產生 buy。

#### A 約束清單（粗估）

- **C-A1**：界定條件同 Q3。
- **C-A2**：撤回在 C-1 的 transaction 內完成。同一個 UPDATE 寫入新狀態、`settled=1`、`settled_at`；schedule 列也在同一個 conn 內更新。
- **C-A3**：新增狀態值。不得沿用 `missed`，不得經過 `settle()`，不得 DELETE，不得動 `missed_count`／`defer_count`。
- **C-A4**：Y 維持 `planned`。
- **C-A5**：新增獨立回應欄位。
- **C-A6**：message 只能附加句子；三支結構不變。
- **C-A7**：不改 `SettlementResult` 的計數。
- **C-A8**：W-A6 需要凍結起點 KV，且只在進入新凍結時寫入。W-A5 由 service 依批次查詢撤回紀錄。
- **C-A9**：前端 union 與 label map 同步。

#### A 測試清單（粗估）

- **T-A1**：EMPTY 分支撤回。T1 結算後現金不變，結算結果不列出該筆。
- **T-A2**：RESULT 分支。只替 X 寫賣單。
- **T-A3**：重送時零寫入。
- **T-A4**：撤回的列不會被 claim，兩個計數器都不變。
- **T-A5**：過期未結算的買單也會被撤回。
- **T-A6**：出清與 settle 並發（Barrier）。結果只能是「成交」或「撤回」其中之一，不能兩者都發生。
- **T-A7**：原子性回滾。
- **T-A8**：凍結後 R1 再替 Y 排入買單，並帶 W-A5。這條是把重複建倉風險釘成測試。
- **T-A9**：schedule 列的狀態已更新。
- **T-A10**：撤回之後再 MISSED 3 次，恰好在第 3 次被 skip。
- **T-A11**：前端 `playbookView.test.ts` 加測新狀態的 label。

### F5 證據（範圍外，請 qa-automation 重現）

- `GET /today` 每次都會呼叫 `evaluate_today`（`api/playbook.py:405-422`），前端用 react-query 讀取（`frontend/app/lib/queries.ts:411-418`）。
- `evaluate_today`（`service.py:614-685`）沒有「當日已評估」的去重。
- 週二當天跑結算，排除了週三才執行的買單（`store.py:853-855`），所以批次仍是 `planned`。
- 接著 R1 會再挑同一批次（`engine.py:699-711`、`:952-958`）。
- 週三結算時，兩列都成交：`shares` 被覆寫成一次的量，現金卻扣了兩次（`store.py:930-941`）。
- 現有測試只在週三重跑（`tests/test_playbook_settlement.py:178-193`），週三不是排程日，所以沒有覆蓋到這個情境。

### ADR-0034 草案（proposed，給 tech-writer；編號以落檔時確認為準）

- **標題**：stock-desk 出清時待結算 R 買單的處置（補充 ADR-0033，不取代）
- **Context**：F1（`0033:216-219`）。上述 Q1 的五點說明既有資料推不出標示。另需載明 R10 下無法得知使用者是否已在券商下單。
- **Options**：A／B-1／B-2a／B-2b／C／D，取自 PM 的比較；再加上標示來源 L1～L4，取自本文 Q1 的表。
- **Decision**：依 CEO 選案，採 B-2a＋L4 或 A。兩案都在 0033 的 C-1 transaction 內擴充「鎖內第四項讀取」與「同一批列的 UPDATE」。三支 message 結構不變，只附加句子。
- **Consequences**：
  - B-2a：需遷移兩欄、不回填、回滾會清掉標示、可能出現幻影批次。
  - A：新增指令狀態、凍結後會重複建倉、W-A6 需要凍結起點 KV。
  - 兩案共通：claim／settle 窗口殘留（F2）、F5 會影響待成交清單的計數。
  - 若風控要求第四支 message，本 ADR 改為取代 0033。

---

## 4. 下一步

### 需 CEO 裁示

1. **選 B-2a 或 A。** 技術輸入只有三點：兩案都要改出清 transaction；規模都是中；技術面略偏 B-2a。偏 B-2a 的理由有三個：
   - 不新增指令生命週期狀態；
   - 重送時要帶出的揭露可以直接查到；
   - A 在凍結後會重複建倉，這是結構性的。
2. **排序。** 確認 N-168 排在 N-166 之後、走獨立分支（VETO-4），並允許 B-2a 的 N-168a 平行開發。
3. **F5 開新追蹤項。** 建議 medium-high，並請 qa-automation 先寫測試重現。F5 的修法（例如引擎略過已有待成交買單的批次）會改變 A 案下的 R 行為，最好在 N-168 build 之前定調。

### 交接

- **risk-compliance-officer**：
  - 附加句的字面（不改 RESULT、EMPTY、S1）；
  - 標示語意請改為「出清時尚未結算」，不用「出清後成交」（理由見 Q1 第 3 點）；
  - 是否需要第四支 message。若需要，ADR 改走取代 0033。
- **product-manager**：依上面兩處更正，修訂 PRD 的總覽表與 AC。
- **tech-writer**：CEO 選案後，依草案落檔 ADR-0034。
- **dev-lead**：N-166 合併後，依 C-B 或 C-A 清單與 T-B 或 T-A 清單實作。

### 相關檔案

- /home/user/AICompany/work/prd/2026-10-31-N168出清後待結算R買單-方案比較.md
- /home/user/AICompany/docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md
- /home/user/AICompany/docs/adr/0001-record-architecture-decisions.md
- /home/user/AICompany/work/reviews/2026-10-31-N166新字面與延長凍結揭露-風控.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/sqlite_util.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py
- /home/user/AICompany/apps/stock-desk/backend/tests/test_playbook_settlement.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/types.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/playbookView.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts

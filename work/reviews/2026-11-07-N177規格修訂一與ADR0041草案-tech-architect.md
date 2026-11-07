# N-177 規格修訂一、ADR-0041 草案、ADR-0035 補充六草案

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**RC-1 可以在 N-177a 範圍內修好，所以不送殘留分析。採用方案 R-α，只動 store.py；service、engine、models、wording 都不改。**

- **範圍比 RC-1 點名的大。** 會用過時讀值整列覆寫批次的地方，不只風控點名的逐批 sell 分支，另有四處會造成同樣的實害（被 S2 關閉的批次復活）：
  - `settle` 的 missed 區塊（store.py:1512-1517）；
  - `roll_peak_closes`（:869-876，`/today` 結算後執行）；
  - `apply_effects` 的 `trailing_on`（`_update_batch`，:1199、:1202-1208）；
  - `apply_effects` 的 `defer_reset`（:1193-1196）。
  
  另外，逐批 buy 用過時現金值寫回，會抹掉並發 S2 的入帳。只修 sell 分支不滿足 RC-1 第 1 點，所以這幾處一起修。
- **R-α 的做法：**
  - `settle` 中每一筆會改股數或現金的動帳（S2 與逐批 buy／sell），都在同一個 conn、單一 `BEGIN IMMEDIATE` 內完成「讀批次 → 讀現金 → 計算 → 只 UPDATE 本分支的欄位」；
  - missed 計數改成一句遞增 UPDATE；
  - 結算以外的批次寫入者改成只寫自己的欄位，不寫股數，也不加 `BEGIN IMMEDIATE`；
  - 結果：app 內不再有 `save_batch` 呼叫點。兩個結算請求並發時，帳冊結果等於依取得寫鎖順序的某一個循序執行。
- **否決的方案：**
  - 只修 sell 分支：其他寫入者仍會復活批次；
  - 行程內 `threading.Lock`：只在單一行程有效，靠部署假設撐著；
  - service 層序列化：違反 ADR-0040 Decision 14 第 3 點，而且鎖會跨過網路載入；
  - 樂觀並發：要動 models 與所有呼叫者；
  - trigger：抓不到 `INSERT OR REPLACE`，N172-C9 也不准用 trigger。
- **與 data-engineer 的實作沒有直接衝突。** 我在 RC-2～RC-6 之外加的解讀與約束都標了 [TA 補]。有一處要風控裁定：RC-6（私人資料不得進 repo）與 RC-9 第 4 點（TA 逐案評估要寫成書面）同時適用時怎麼處理。
- 修訂一、ADR-0041 全文、ADR-0035 補充六，三份全文在第二節的 code block 裡。

## 二、各部門回報

### tech-architect（本人，唯讀）

**評估摘要**
- 採用 R-α。N-177a 的改動範圍（C3）擴大到：buy／sell／missed 的實作、`roll_peak_closes`、`apply_effects` 的 `defer_reset`、`_update_batch`。
- C-B6 是行為約束，不是程式碼凍結。新寫法寫入的值與 C-B6 逐值相同，由三樣東西守住：
  - N-168 既有測試的斷言零改動（C9）；
  - 差分測試 T27：拿修訂前的程式當參考實作逐值比對；
  - C18：行為等價條款。
- 4.9 第 3 點寫的「N-177a 不碰 buy 分支」，這次一併更正。
- RC-1 以外還有兩個相鄰問題，不擋 N-177a，但要風控裁示：
  - **R-1′**：REBALANCE 在鎖外讀現金、再整值寫回，可能抹掉並發結算的現金異動。這個問題修訂前就存在；N-177a 只多了「S2 入帳被抹掉」這一種，方向保守。
  - **R-2′**：N2 在鎖外預讀批次，並發時可能少揭露一次，帳冊本身是對的。我提出 Q-g：讓 N2 改用 N-177b 的鎖內結果判定。

**方案比較、決策、對實作的約束**：方案比較在修訂一 1.2；決策在 ADR-0041 草案 Decision 5；約束是修訂一 1.5 的 C3、C6、C7、C9(3)、C16～C18、4.8(i)、T19、T20、T23～T29、QB-11、QB-12。

**決定性交錯測試的寫法（回應 RC-1 第 2 點）**
- T23、T24 在同一個 DB 檔開兩個 store 實例，代表兩個並發請求。
- 注入點：用自訂 Connection factory，在「第一句寫入 `playbook_batches` 或 `playbook_state` 之前」插入另一個請求的結算。
  - 修訂前，這個點正好是舊分支 `get_batch` 讀完、`set_cash`／`save_batch` 寫入之前；
  - 修訂後，是鎖內讀完、寫入之前。
- 斷言只看最終帳冊，與執行時序無關。
- PR 要附上本機輸出，證明把新 helper 換回舊分支時，這兩個測試會失敗。

**與 RC-2～RC-6 的一致性（data-engineer 已依風控原文實作）**
- 與風控原文一致。我加的部分全部標 [TA 補]：
  - 枚舉欄位遇到非預期值時，輸出固定字樣；
  - G-c′ 的「受影響批次」讀作該檔目前全部合格批次；
  - 判斷 repo 工作樹時，`.git` 是檔案（worktree）也算；
  - (B) dry-run 指紋不寫進 repo：指紋是 (symbol, id, 金額) 的雜湊，id 已知時可以窮舉還原；
  - TA 的逐案評估不落檔進 repo，由 coordinator 直接轉交 CEO。
- 若 data-engineer 的實作與 [TA 補] 不同，請在 PR 說明列出，交 TA 判定，不當作 BLOCKING。
- RC-7 說要取代「第 5 節『也可以更晚』」，但這句其實在第 7 節第 5 步（第 5 節 C8 也有類似寫法）。兩處都已修訂。

---

**全文一：N-177 規格 修訂一（附到原規格檔末）**

````markdown
## 修訂一（tech-architect，2026-11-07；回應風控 RC-1～RC-10）

- 依據：[風控-177R] `work/reviews/2026-11-07-N177實作規格審查與C6至C10確認-風控.md`
- 程式依據：product/stock-desk checkout（同本檔第 6 行），只讀，未執行。行號以內容定位。
- 本修訂取代本檔對應段落；沒提到的段落維持原文。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀；標 [待風控] 的需要風控再審。

### 1. RC-1：並發結算的機制（擋 N-177a 合併）

#### 1.1 盤點：會以過時讀值覆寫批次或現金的寫入者
讀碼盤點 store.py 對 `playbook_batches` 與 `STATE_CASH` 的所有寫入（`app/` 內沒有其他模組寫這兩者）：

| # | 寫入者 | 讀寫方式 | 會碰到 S2 動過的批次嗎 | 並發下的結果 |
|---|---|---|---|---|
| W1 | `settle` 逐批 sell（`get_batch` → `set_cash(portfolio_state()…)` → `save_batch`） | 三個呼叫各開連線；整列 `INSERT OR REPLACE` | 會（open 批次） | RC-1：批次復活；現金重複入帳，或抹掉別筆入帳 |
| W2 | `settle` missed 區塊（`get_batch` → `save_batch(missed_count+1)`） | 同上，整列 | 會（S／P／EMERGENCY 的 missed 列，所屬批次是 open） | 批次復活 [TA 補] |
| W3 | `settle` 逐批 buy（`get_batch` → `_exit_stamp` → `set_cash` → `save_batch`） | 同上 | 批次不會（G1 保證 buy 只動 planned，S2 只動 open）；現金會 | 抹掉並發 S2 的入帳（現金少記）[TA 補] |
| W4 | `roll_peak_closes`（`list_batches` → 逐批 `save_batch`），`/today` 結算後執行 | 整列 | 會（只處理 open） | 批次復活 [TA 補] |
| W5 | `apply_effects` → `_update_batch`（`trailing_on`） | `get_batch` → 整列 | 會（engine 只對 open 批次發 trailing_on，engine.py:596、:610） | 批次復活 [TA 補] |
| W6 | `apply_effects` 的 `defer_reset`（`list_batches` → `save_batch`） | 整列 | 會（buy 成交不會把 `defer_count` 歸零，open 批次可能非 0） | 批次復活 [TA 補] |
| W7 | `apply_effects` → `_update_batch`（`defer_increment`、`batch_skipped`） | 整列 | `/today` 走不到：service 先濾掉 `LINE_BOUND_EFFECTS`，改在鎖內由 `_apply_bound_effects` 欄位化寫入 | 一併欄位化，不留整列寫入點 |
| W8 | `rebalance` → `set_capital(cash=portfolio.cash, …)`（service.py:1538 讀、:1612 寫） | 鎖外讀現金、整值寫回 | 現金會 | 抹掉並發結算的入帳或扣款（R-1′，見 1.6） |
| W9 | `confirm_rules` → `set_capital(cash=capital)` | 使用者宣告資金，覆寫就是它的語意 | — | 不屬競態（見 1.6） |
| — | `_apply_bound_effects`、`commit_emergency_exit` | 鎖內、欄位化 | — | 沒有問題 |

結論：W1 不是唯一一處。W2、W4～W6 會造成同樣的實害（被 S2 關閉的批次復活），W3 會抹掉 S2 的入帳。只修 W1 不滿足 RC-1 第 1 點的「結果」。

#### 1.2 方案比較

| 方案 | 內容 | 改動範圍 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|---|
| R-α | (i) `settle` 的逐批 buy／sell 改成：同一 conn、單一 `BEGIN IMMEDIATE` 內「讀批次 → 讀現金 → 計算 → 只 UPDATE 本分支的欄位 → 現金讀改寫」；missed 改成單一句 `missed_count = missed_count + 1`。(ii) W4～W7 改成欄位化 UPDATE，不再整列寫入 | 只有 store.py；service、engine 零 diff | SQLite 寫鎖跨執行緒、也跨行程；與 `commit_evaluation`、`commit_emergency_exit`、`_settle_s2_fill` 同一模式；可以用 SQL trace 檢查 | 動到 buy 分支的實作（C-B6 行為不變，程式碼要改）；C3 擴大；`/today` 有成交時多幾個短交易 | 中低：行為等價由 T27 差分測試綁住 | **採用** |
| R-α′ | 只修 W1 | 最小 | diff 最小 | W2、W4～W6 仍會復活批次；W3 仍會抹掉 S2 入帳 | 不滿足 RC-1 第 1 點 | 否決 |
| R-β | store 模組層級的 `threading.Lock`：`settle` 全程、`roll_peak_closes`、`apply_effects` 都持鎖 | store.py，各函式外面包一層 | 舊分支本體可以零 diff | 只在單一行程內有效。現況 uvicorn 是單 worker（compose、Dockerfile、dev-up 都沒有 `--workers`），scheduler 也不碰 playbook，但這只是部署假設，沒有東西強制；在鎖外新增呼叫點就破功；SQL 層看不出來，qa 無法從 trace 檢查 | 中 | 否決 |
| R-γ | service 層序列化（`_settle_pending` 整段，或 `evaluate_today`／`settle_on_request` 整段持鎖） | service.py | 概念簡單 | 違反 ADR-0040 Decision 14 第 3 點與 C3；鎖會跨過網路載入 bars，`/today` 互相排隊；同樣只限單一行程；結算以外的 W4～W6 沒蓋到 | 高 | 否決 |
| R-δ | 樂觀並發：`save_batch` 帶版本（`updated_at`）比對，失敗就重試 | models.py（`BatchState` 沒有 updated_at）、store 的所有呼叫者 | 不持鎖 | 要動 models 與所有呼叫者；重試邏輯要逐一設計；超出範圍 | 高 | 否決 |
| R-ε | 用 SQLite trigger 擋「closed → open」 | `_SCHEMA` | 不動程式 | `INSERT OR REPLACE` 是先刪再插，UPDATE trigger 抓不到；N172-C9／T14 不准 trigger；擋不住現金重複 | 高 | 否決 |

結論：N-177a 範圍內做得到（只動 store.py），所以不提出殘留分析。1.6 的 R-1′、R-2′ 是 RC-1 以外的相鄰問題，另附分析。

#### 1.3 R-α 規格

**(1) `settle` 的結構（修訂 4.3）**
```python
if is_s2_fill(directive):
    ...                                    # unchanged from 4.3
if directive.status == "missed" and directive.batch_no is not None:
    self._count_missed(directive)          # one UPDATE, no read
if directive.status != "executed" or directive.batch_no is None:
    self._mark_schedule(directive)
    return
self._settle_batch_line(directive, price=_settle_price(directive, fill_price),
                        directive_id=directive_id)
self._mark_schedule(directive)
```
- `_count_missed`：`UPDATE playbook_batches SET missed_count = missed_count + 1, updated_at = ? WHERE symbol = ? AND batch_no = ?`。
  - 批次不存在時影響 0 列，等同現行的 `if batch is not None`。
  - 不寫 `entry_before_exit_on`（C-B6「MISSED 不加標示」）。

**(2) `_settle_batch_line`（新私有 helper；寫法比照 `_settle_s2_fill`／`commit_evaluation`，錯誤處理照 C-11）**
1. `with closing(self._connect()) as conn`，執行 `BEGIN IMMEDIATE`。
2. 在這個 conn 上讀批次：與 `get_batch` 同一句 SELECT，透過接收 conn 的私有讀取 helper。讀不到時 `COMMIT` 並 return，`settle` 照舊只做 `_mark_schedule`。
3. buy：
   - 在同一個 conn 讀 L4 戳記（與 `_exit_stamp` 同一句 SELECT）；`directive_id` 為 None 時不讀，與現行相同。
   - 新值與現行 :1529-1539 逐字相同：`status='open'`、`entry_date`、`cost=price`、`shares`、`remaining_shares=directive.shares`、`peak_close=price`、`entry_before_exit_on`（戳記為 None 時沿用鎖內讀到的值）。
   - 寫入：`UPDATE playbook_batches SET status = ?, entry_date = ?, cost = ?, shares = ?, remaining_shares = ?, peak_close = ?, entry_before_exit_on = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?`。
   - 現金：`_add_cash(conn, -(price × directive.shares))`。
4. sell：
   - `moved = min(鎖內 remaining, directive.shares)`；`remaining = max(0, 鎖內 remaining − directive.shares)`；`status` 與 P1／P2／P3 的標記和現行 :1542-1555 逐字相同。
   - 寫入：`UPDATE playbook_batches SET remaining_shares = ?, status = ?, p1_done = ?, p2_done = ?, trailing_active = ?, p3_last_date = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?`。值取自鎖內讀值再套上變更，所以沒變的欄位，寫回的就是鎖內當下的值。
   - 現金：`_add_cash(conn, price × moved)`。
5. 其他 action：不寫。這條路徑走不到，因為非下單列寫入時就已是 settled（見 `record_directives`）。現行在這裡會整列重寫一次（只改 updated_at），這是全案唯一不等價的地方。
6. `COMMIT`。例外時先 `if conn.in_transaction: ROLLBACK`，再原樣 raise。
- 持鎖期間不得呼叫任何會另開連線的 `self.*` 方法：`get_batch`、`portfolio_state`、`_exit_stamp`、`set_cash`、`save_batch`。

**(3) 共用的 conn helper（模組層級或私有方法，各只有一份定義）**
- 接收 conn 的批次讀取：`SELECT {_BATCH_SELECT} … WHERE symbol = ? AND batch_no = ?`，轉換沿用既有的 `_row_to_batch`。`get_batch` 可以改成委派給它（行為不變），但不得另寫第二份 SELECT。
- `_add_cash(conn, delta)`：在 conn 上讀 `STATE_CASH`（沒有這個鍵時視為 `Decimal("0")`，與 `portfolio_state` 相同），再以 `_write_state(conn, {STATE_CASH: str(cash + delta)})` 寫回。`_settle_s2_fill`（4.5）與 `_settle_batch_line` 共用。
- 寫入次數要與現行等價：
  - buy／sell 一律呼叫 `_add_cash`，delta 為 0 也要寫，因為現行的 `set_cash` 每次都寫，鍵會因此被建立；
  - S2 依 4.5，只在 Σmoved > 0 時呼叫（T12）。

**(4) 結算以外的批次寫入者改成欄位化（W4～W7）**
- `roll_peak_closes`：讀取照舊用 `self.list_batches()`，比較邏輯不變。寫入改為同一個 conn（`with closing(...) as conn, conn:`，不加 `BEGIN IMMEDIATE`），逐批執行 `UPDATE playbook_batches SET peak_close = ?, updated_at = ? WHERE symbol = ? AND batch_no = ? AND status = 'open'`。
- `defer_reset`：`UPDATE playbook_batches SET defer_count = 0, updated_at = ? WHERE symbol = ? AND defer_count <> 0`。
- `_update_batch`：不讀，直接 `UPDATE playbook_batches SET <欄> = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?`。
  - 欄名只能來自白名單 `defer_count`、`status`、`trailing_active`，也就是現有三個呼叫者用到的三個欄位；其他欄名 raise `ValueError`。
  - 布林值轉成 int，與 `save_batch` 相同。
- 這幾處**不得**加 `BEGIN IMMEDIATE`。
  - 理由：`test_playbook_same_day_race.py` 的 T14（`(begin,) = …`）與 `_writes_inside`（取第一個 `BEGIN IMMEDIATE`），都假設沒有結算成交的 `/today` 只有一個 `BEGIN IMMEDIATE`，也就是 `commit_evaluation` 那一個。
  - 單句 UPDATE 本身就是原子的；改成欄位化之後，就算讀值過時，也覆寫不到股數或 status。

**(5) 為什麼這樣滿足 RC-1 第 1 點**
- 所有改動股數或現金的寫入（`_settle_s2_fill`、`_settle_batch_line`），都在 SQLite 寫鎖內讀、在同一個寫鎖內寫。SQLite 同時只允許一個寫交易，所以兩個結算請求的動帳結果，等於依取得寫鎖順序的某一個循序執行。4.10 的三點在每一種循序順序下都成立（T6 測了兩種順序）。
- 結算以外的寫入者只寫自己的欄位（peak_close、defer_count、trailing_active、status='skipped'），不寫 `remaining_shares`、`shares`，也不寫 open／closed 的 status，所以不會讓 S2 關閉的批次復活。
  - `batch_skipped` 只由 engine 對 planned 批次發出；在 `/today` 中，它由鎖內的 `_apply_bound_effects` 寫入。
- `app/` 內不再有任何 `save_batch` 呼叫點。`INSERT OR REPLACE INTO playbook_batches` 只留在 `save_batch` 的定義裡，給測試建 fixture 用。
- 不改的地方：claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169）。這不影響上面的結論：claim 只決定誰處理哪一列，帳冊結果只取決於動帳交易的先後。

#### 1.4 改動範圍的判定（回答 RC-1 的三個問題）
- **舊分支是不是 C-B6／N-168 守護的範圍？**
  - buy 分支與 missed 區塊是：C-B6 規定「buy 成交時把戳記複製到批次標示；MISSED 不加標示」。
  - sell 分支不是 C-B6 的條文本身，但與 buy 同在 `settle` 本體內。
  - 判定：C-B6 是**行為**約束，不是程式碼凍結。R-α 寫入的值與 C-B6 的行為逐值相同，由三項守住：N-168 既有測試斷言零改動（C9）、T27 差分測試、C18。
  - 4.9 第 3 點「N-177a 不碰 buy 分支」由本修訂更正為「N-177a 改寫 buy 分支的讀寫方式（鎖內讀、欄位化寫），值與 C-B6 行為不變」。
  - 改寫 buy 分支屬於「改動 `settle` 的動帳實作」。依 A-2，由 ADR-0041 承載並送風控。
- **`save_batch` 的其他呼叫者會不會受影響？**
  - `save_batch` 本體零 diff。
  - app 內原有的呼叫者（W1、W2、W4、W6、W7）全部改走欄位化寫入，行為等價；`test_playbook_store.py` 中 roll_peak／apply_effects 的既有測試應原樣綠燈。
  - 測試 fixture 照舊可以用 `save_batch`。
  - `get_batch` 只讀，`service._batch_of`（N2、W-B3）照舊使用。
- **與 C3 的關係**：C3 要擴充，見 1.5。service.py、engine.py、models.py、wording.py 仍然零 diff。

#### 1.5 約束與測試的修訂（取代 4.11、4.12 的對應條文）

- **C3（取代）**：改動範圍只限 store.py 的以下部分：
  - (a) 模組 docstring；
  - (b) 4.2 的常數與兩個函式；
  - (c) `_SCHEMA` 末尾追加一條 DDL；
  - (d) `settle`：抽出 `_settle_price`、插入 S2 分支、missed 區塊改呼叫 `_count_missed`、逐批分支改呼叫 `_settle_batch_line`、更新 docstring；
  - (e) `_settle_s2_fill`；
  - (f) `_settle_batch_line`、`_count_missed`；
  - (g) 1.3(3) 的 conn helper；`get_batch`、`_exit_stamp` 只允許改成委派（行為不變）；
  - (h) `roll_peak_closes` 的寫入；
  - (i) `apply_effects` 的 `defer_reset` 分支；
  - (j) `_update_batch`。
  - 其餘零 diff，特別是：`commit_evaluation`、`_read_logged`、`read_in_flight`、`_read_exit_state`、`_apply_bound_effects`、`commit_emergency_exit`、`claim_directive`、`batch_blocking_claim`、`_insert_directives`、`BATCH_LEFT_PLANNED_SQL`、`blacklist`、`save_batch`、`set_cash`、`set_capital`、`portfolio_state`、`list_batches`、`_mark_schedule`、`_MIGRATIONS`、`_init_schema` 本體。
  - 以下零 diff：service.py（含 `_lines`、`_settle_pending`、`rebalance`）、wording.py、models.py、`app/api/**`、`app/data/**`、`app/services/**`。
  - 改動 `playbook_batches` 股數（`shares`、`remaining_shares`）或 cash 的寫入，只出現在 `_settle_s2_fill`、`_settle_batch_line`（經 `_add_cash`）。
- **C6（取代）**：
  - S2 依 4.4、4.5；逐批 buy／sell 依 1.3(2)；價格只走 `_settle_price`。
  - `settle` 的任何分支都不得呼叫 `save_batch`、`set_cash`、`portfolio_state`、`get_batch`、`_exit_stamp`，也不得產生 `INSERT OR REPLACE INTO playbook_batches`。
- **C7（取代）**：
  - 同一筆 S2 的合格讀取、批次更新、現金讀改寫、稽核寫入，都在同一 conn 的單一 `BEGIN IMMEDIATE` 內完成。
  - 同一筆逐批 buy／sell 的批次讀取、戳記讀取（buy）、批次更新、現金讀改寫，同樣在同一 conn 的單一 `BEGIN IMMEDIATE` 內完成。
  - 錯誤處理照 C-11；持鎖期間沒有其他 I/O，也不另開連線。
- **C9（追加第 (3) 點）**：既有測試中以 trace 取「第一個」或「唯一一個」`BEGIN IMMEDIATE` 的斷言，若涵蓋的流程含有結算成交：
  - PR 要逐條列出，並說明修訂一之後，斷言指到的仍是原本那個交易；
  - 不得弱化既有斷言；需要修改的，列入第 (2) 點交 qa 判定；
  - 已知位置：`test_playbook_same_day_race.py::_writes_inside`、同檔 T14 的 `(begin,) =`、`test_playbook_exit_race.py` :376、`test_playbook_entry_before_exit.py` :546、:562。後兩處是 emergency_exit，預期不受影響。
- **C16（取代）**：4.12 與本節的 T1～T29 全部存在且綠燈（BLOCKING）。
- **C17（新增）**：結算以外的批次寫入者（`roll_peak_closes`、`defer_reset`、`_update_batch`）只用欄位化 UPDATE：
  - 不寫 `shares`、`remaining_shares`；
  - 不寫 `status`，唯一例外是 `_update_batch` 的 `status='skipped'`；
  - 不加 `BEGIN IMMEDIATE`。
- **C18（新增）**：行為等價。
  - 循序執行時，逐批 buy／sell／missed 寫出的批次各欄（`updated_at` 除外）與現金，都和修訂前逐值相同；
  - buy／sell 一律寫現金，delta 為 0 也寫；
  - 唯一不等價的是 1.3(2) 第 5 步那條走不到的路徑。
- **4.8 (i)（取代）**：
  - N-177a 改動股數與現金的寫入程式，只在 `_settle_s2_fill`、`_settle_batch_line`，兩者都是 `settle` 的私有 helper；後者取代既有寫入，不是新路徑。
  - X-3 的前提「帳冊股數只在 claim 之後由 `settle` 改變」維持（T19）。
  - C17 的寫入者不碰股數與 cash，不屬於 Decision 14 第 2 點規範的對象。

**測試（追加 T23～T29；T19、T20 取代）**
- **T19（取代）**：
  - `app/` 內寫 `remaining_shares` 或 `shares` 的 `UPDATE playbook_batches`，只出現在 `_settle_s2_fill`、`_settle_batch_line`；
  - `INSERT INTO playbook_fill_moves` 只出現在 `_settle_s2_fill`；
  - `STATE_CASH` 的寫入只在 `set_cash`、`set_capital`、`_add_cash`，而 `_add_cash` 只被上述兩個 helper 呼叫；
  - `INSERT OR REPLACE INTO playbook_batches` 只在 `save_batch` 的定義內；
  - AST 檢查：`app/` 內沒有 `save_batch(`、`set_cash(` 的呼叫點。
- **T20（取代）**：SQL trace。
  - S2 分支與逐批 buy／sell 的批次 SELECT、現金 SELECT 與所有寫入，都夾在同一條連線的 `BEGIN IMMEDIATE` 與 `COMMIT` 之間；
  - missed 只有一句 `missed_count = missed_count + 1` 的 UPDATE。
- **T23（RC-1 決定性交錯：逐批先進入讀寫窗口）**：
  - 設定：同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B，等同兩個請求，也等同兩個行程。一批 open、remaining=100、cost 已設；待結算 S1（該批，參數化 40 股與 100 股）與 S2（100 股）。A claim S1，B claim S2。
  - 注入點：把 A 的 `_connect` 換成自訂 `Connection` factory，`execute` 在 A **第一句寫入 `playbook_batches` 或 `playbook_state`** 的 SQL 送出之前執行 hook。修訂前，這個點就是舊分支「`get_batch` 讀完之後、`set_cash`／`save_batch` 寫入之前」；修訂後，是鎖內讀完之後、寫入之前。
  - hook：另開執行緒跑 `B.settle(S2, …)`，最多等它 0.5 秒，然後放行 A；A 結束後 join B。BUSY_TIMEOUT 是 5 秒，B 不會逾時失敗。
  - 斷言（與時序無關）：
    - 該批 closed、remaining 0；
    - 現金 = 初值 + p1 × 40 + p2 × 60（100 股版本：初值 + p1 × 100）；
    - S2 稽核列 = 該批 60 股（100 股版本：sentinel 一列）；
    - 不出現 open 且 remaining > 0 的該批。
- **T24（RC-1 原情境：S2 先進入讀寫窗口）**：
  - 與 T23 角色互換：hook 掛在 B 的第一句寫入之前，在 hook 中另開執行緒跑 `A.settle(S1, …)`。
  - 斷言：該批 closed、remaining 0；現金 = 初值 + p2 × 100（S1 入帳 0）；S2 稽核列 = 該批 100 股。
  - 這就是 RC-1 描述的「A 讀到 remaining=100、B 關閉批次」的交錯；修訂後，A 的讀取一定發生在 B commit 之後。
- **T23／T24 的效力證明**：PR 說明附上本機輸出，顯示把 `_settle_batch_line` 暫時換回修訂前的逐批分支本體時，T23、T24 會失敗（批次復活，或現金不符）。這份對照不 commit。
- **T25（結構）**：用 spy 包住 `get_batch`、`save_batch`、`set_cash`、`portfolio_state`、`_exit_stamp`、`list_batches`。對以下各情況各跑一次 `settle`，上述方法的呼叫次數都是 0：
  - executed buy；
  - executed sell（S1、P1、P2、P3、EMERGENCY）；
  - missed sell、missed buy；
  - executed S2。
- **T26（結算以外的寫入者）**：
  - (i) S2 先關閉某批後，把 `list_batches` monkeypatch 成回傳關閉前（open、100 股）的過時清單，再以較高收盤呼叫 `roll_peak_closes`：DB 中該批仍是 closed、remaining 0。
  - (ii) 對 closed 批次套用 `trailing_on`、`defer_reset`：remaining 與 status 不變。
  - (iii) SQL trace：`roll_peak_closes`、`defer_reset`、`_update_batch` 只送出 C17 允許的 UPDATE，沒有 `BEGIN IMMEDIATE`，也沒有 `INSERT OR REPLACE`。
  - (iv) `_update_batch` 收到白名單以外的欄名時 raise `ValueError`。
- **T27（行為等價的差分測試）**：
  - 測試檔內放一份修訂前逐批分支與 missed 區塊的參考實作，只供比對。
  - 固定 seed，至少 300 組：隨機 book；隨機 buy／sell（S1、S2 以外的 S、P1～P3、EMERGENCY）／missed 列；涵蓋批次不存在、remaining 0、`directive_id` 為 None、有／無 L4 戳記。
  - 循序執行時，新舊兩者的批次各欄（`updated_at` 除外）與現金完全相同，`playbook_state` 的鍵集合也相同。
- **T28（`/today` 的交易數）**：以合入 N-190 後的 head 為準。
  - 沒有結算成交時，`evaluate_today` 的 trace 恰好一個 `BEGIN IMMEDIATE`；
  - 有 k 筆 executed 逐批列（含批次不存在）、m 筆 executed S2 時，恰好 1 + k + m 個。
- **T29（逐批動帳中途失敗）**：
  - 注入 `_add_cash` 拋例外：該批各欄與現金都不變，例外原樣拋出，沒有留下未關閉的交易；
  - 該列維持 `settled=1／executed`（F2 殘留釘住，歸 N-169，同 T9）。

**QB 追加**
- QB-2：hunk 逐一對照 C3 的 (a)～(j)。
- QB-3 追加：`INSERT OR REPLACE INTO playbook_batches` 在 `app/` 內只有一處。
- QB-4：改為 T1～T29；T7 至少 500 組、T27 至少 300 組，seed 都固定。
- QB-11（新增）：T23、T24 的效力證明附在 PR 說明。
- QB-12（新增）：N-168 的 T-B 系列、`test_playbook_settlement*.py`、`test_playbook_store.py` 原樣綠燈；C9 第 (3) 點的清單完整。

#### 1.6 RC-1 以外的相鄰問題（不擋 N-177a；[待風控] 裁示）

**R-1′：REBALANCE 以鎖外讀值寫回現金（W8）**
- 程式事實：`rebalance` 在 service.py:1538 讀 `portfolio_state()`，在 :1612 以 `set_capital(cash=portfolio.cash, …)` 整值寫回，中間只有純計算。
- 實害：
  - 若中間有並發結算 commit，那一筆的現金異動會被抹掉。
  - 修訂前就存在：buy 扣款與 sell 入帳都會被抹掉；抹掉 buy 扣款時現金多記，方向不保守。
  - N-177a 新增的只有「S2 入帳被抹掉」，現金少記，方向保守。
- 頻率：極低。REBALANCE 是手動、季末才跑，而且要與另一分頁的結算成交落在同一個毫秒級窗口。
- 可偵測性：現金是單一 KV、沒有異動歷史（ADR-0035 Decision 9），偵測工具判定不了。
- 歸類：ADR-0035 Consequences 的「結算時現金的讀改寫競態」原本歸 N-169。R-α 已消除結算內部的那一部分，REBALANCE 是剩下的唯一一處。
- 修法（不在 N-177a）：store 新增只寫 TOTAL_DEPLOY 三個鍵的方法，`rebalance` 改用它。service.py 只動 `rebalance` 一處，不是 N-190 的熱點。
- 請風控二選一：(a) 接受為歸 N-169 的殘留；(b) 另開小單，在 R2 之前或與 R2 同一個 release 上線。
- `confirm_rules` 的 `set_capital(cash=capital)` 是使用者宣告資金，覆寫就是它的語意，不列為競態。

**R-2′：N2 的鎖外預讀**
- 程式事實：N2 在 service.py:1360 先讀批次，之後才呼叫 `settle`。並發時，另一個請求的 S2 可能在這兩步之間關閉該批。
- 結果：EMERGENCY 實際移動 0 股，但 N2 沒有出現。帳冊正確，只是少揭露一次。
  - 反方向不會發生：closed 批次不會回到 open，因為 buy 只動 planned，而批次不會回到 planned。
- 頻率：低。要同一批同時有在途 EMERGENCY 與 S2，而且兩個結算請求並發。
- 修法：N-177b 的 `SettleOutcome` 已經有鎖內讀值，可以讓 N2 改依回傳值判定，字面不變。但 N177b-C6 規定 N2 的判斷零 diff，所以列為 **Q-g** 送風控。同意的話，N177b-C6 改為「N2 字面零 diff；判斷來源改為 `SettleOutcome`，判斷條件等價」。

**不處理（說明）**：
- `evaluate_today` 在 :1901 讀的 book，在並發下可能早於另一個請求的 S2，engine 可能因此對已關閉的批次再出 S/P。
- 這些列結算時零移動（4.10），由 N-177b 的 Q-c 句揭露。
- 這屬於 N-182 E-2 同類的「評估輸入過時」問題，帳冊不會因此出錯。

### 2. 4.10、4.14 的修訂（RC-1 第 3 點）

**4.10**：在第一個子彈前加入：
- 前提：以上在結算循序執行時成立；並發的處理見 RC-1。

並追加（[待風控]）：
- 修訂一：依 1.3，每一筆動帳的讀、算、寫都在同一個 `BEGIN IMMEDIATE` 內，並發結算在帳冊上的結果等於某一個循序順序，所以上述三點在並發下也成立（T23、T24）。

末兩個子彈改為：
- 殘留：非 EMERGENCY 的 S/P 在「批次存在但已沒有股數」時零移動、無聲。依 RC-7 歸 N-177b，期限見第 5 節。
- 風控已確認循序前提下成立（2026-11-07 A-1）。偵測工具的 G-c 依 RC-2 改為事實欄，另設 G-c′（第 6 節）。

**4.14 第 2 點（取代）**：
- 舊的逐批分支（buy、sell、missed），以及 `roll_peak_closes`、`trailing_on`、`defer_reset`，原本先在各自的連線讀批次與現金，再以整列 `INSERT OR REPLACE` 與整值寫回。並發時會：
  - (i) 以過時讀值覆寫已被 S2 關閉或減少的批次，股數與 status 一起復活；
  - (ii) 讓同一批股數的現金入帳兩次；
  - (iii) 抹掉其他結算的現金異動。
- 其中 (i)、(ii) 是 N-177a 新增的交錯（RC-1）。N-177a 依修訂一 R-α 一併修正，不列為殘留。
- 修正後剩下的相鄰問題是 R-1′（REBALANCE 寫回現金）與 R-2′（N2 鎖外預讀），見修訂一 1.6，待風控裁示。

**4.14 第 3 點（取代）**：4.10 的零移動 S/P 無聲：歸 N-177b（RC-7），最遲與第三包同一個 release。

**4.9 第 3 點第 2 子彈（更正）**：C-B6 衝突已不存在，因為 N-168 已合併。N-177a 改寫 buy 分支的讀寫方式（修訂一 1.3），寫入值與 C-B6 行為不變。

### 3. 第 5 節（N-177b）的修訂（RC-7、RC-8）

**範圍（取代）**：
- store.py：`settle` 的回傳值，由 `_settle_batch_line` 的鎖內讀值決定；
- service.py：`_settle_pending` 與結算 warnings；
- wording.py：加三個常數與項目格式。
- 在 N-177a 合併之後開工。

**判定（取代）**：`SettleOutcome(NamedTuple)` 有兩個欄位，日後只能再做加法。
- `missing_batch_row: bool`：同時滿足以下條件時為真。
  - `status == 'executed'`；
  - `action in ORDER_ACTIONS`；
  - `not is_s2_fill(directive)`；
  - `batch_no is None`，或 `_settle_batch_line` 在鎖內讀不到批次。
- `empty_batch_sell: bool`（Q-c，RC-7）：同時滿足以下條件時為真。
  - `status == 'executed'`、`action == 'sell'`；
  - `not is_s2_fill(directive)`、`rule_id != 'EMERGENCY'`；
  - 批次在鎖內讀得到，而且鎖內讀到的 `remaining_shares == 0`。
- 其他情況一律為假，包括：S2（含零移動 sentinel）、missed、非下單列，以及部分移動（0 < remaining < shares）。
- 兩個欄位都取自鎖內讀值，所以並發時也與實際動帳一致（修訂一 1.3）。不得在 service 另讀一次。

**service（追加）**：收集 `empty_batch_sell` 為真的列。EMERGENCY 在判定時已排除，由 N2 揭露。

**位置（取代）**：在結算 warnings 中依序為 SUMMARY → W-B3 → N2 → buy 句 → sell 句 → Q-c 句（暫定）。最終順序隨字面定稿一併決定。

**字面（追加 Q-c 句）**：
- 識別名暫定 `SETTLEMENT_EMPTY_BATCH_SELL_NOTE`，只放在 `wording.py`；creative-lead 擬稿，風控逐字定稿。
- 只陳述「判定時該批次在帳冊已無持股，股數與現金都未因本筆變動」這個事實。
- 必含「本系統不下單」與「實際持股以你的券商回報為準」；不推測使用者是否已賣出。
- 禁用詞同 RC-3：「需」「應」「建議」「務必」「盡快」「否則」「安全」「對應」。
- 可用欄位：symbol、batch_no（此句一定是整數）、shares、execution_date、rule_id。

**期限（取代第 7 節第 5 步，以及 N177b-C8 的「可以更晚」）**：
- N-177b（含 Q-c 句）最遲與第三包同一個 release 上線；可以更早，不得更晚。
- 依 Q-e，「第三包」是 R2 之後的下一個 release，所以 N-177b 只能搭 R2，或搭第三包的那個 release。

**EMERGENCY 找不到批次時「走不到」的論證（RC-8，寫入本規格）**：
- 現況核對：
  - EMERGENCY 找不到批次列時，N2 第二句「帳冊中這幾批只依另一筆賣出指令減少一次股數」不為真；
  - `SETTLEMENT_EXIT_ITEM` 遇到 `batch_no` 為 None 時，會印出「第 None 批」。
- 這條路徑走不到，理由：
  1. EMERGENCY 列只從當下存在的批次產生（service.py:414-420），`batch_no=batch.batch_no` 一定是整數。
  2. `app/` 內沒有任何 `DELETE FROM playbook_batches`（grep 的結果只有 positions、alerts、playbook_state、cache、kelly）。
  3. 批次列只由 `ensure_batches` 的 `INSERT OR IGNORE` 建立；`save_batch` 的 `INSERT OR REPLACE` 是刪除後立即在同一句插回，而且修訂一之後 app 內已沒有 `save_batch` 呼叫點。
  4. 所以 EMERGENCY 列所屬的批次列一旦存在，就不會消失。
- 論證不涵蓋手動改 DB；RC-9 第 4 點禁止手動改 DB。
- N177b-T3 保留為釘住測試。
- 日後若發現走得到的路徑，要回 TA 與風控，不得以 N2 代替揭露。

**約束修訂**：
- N177b-C3：`_settle_pending` 的 diff 只限接收回傳值與追加 warnings。
- N177b-C6：維持「N2 的判斷與字面零 diff」；若風控同意 Q-g，依 1.6 改寫。
- N177b-C9（新增）：兩個判定欄位只由 store 在鎖內決定，service 不得另讀批次來判定。
- N177b-C8：維持「可以搭 R2 上線，但不得延後 N-177a」，並加上本節的期限。

**測試追加**：
- N177b-T9：非 EMERGENCY 的 S1、P1 在 remaining 0 的批次上判定成交 → Q-c 句恰好一次，帳冊與現金不變。
- N177b-T10：EMERGENCY 在 remaining 0 的批次上 → 只有 N2，沒有 Q-c 句。
- N177b-T11：部分移動（0 < remaining < shares）→ 沒有 Q-c 句。
- N177b-T12：用 T24 的設定（S2 先關閉批次，並發的 S1 隨後結算）→ S1 那一次的結果含 Q-c 句。
- N177b-T13：S2 零移動 sentinel → 沒有 Q-c 句。
- N177b-T14：Q-c 句與 buy 句、sell 句同時出現時，順序正確。

### 4. 第 6 節（偵測工具）的修訂（RC-2、RC-3、RC-5、RC-6）

data-engineer 已依風控原文實作 RC-2～RC-6，以下內容與風控原文一致。標 [TA 補] 的是 TA 的解讀或新增；若與已完成的實作不同，請在 PR 說明列出，交 TA 判定，不視為 BLOCKING。

**6.2 exit code 4（取代）**：以下情況拒絕執行：
- 指向正式 DB；
- 輸出檔已存在；
- out-dir 是正式資料夾；
- **`--out-dir` 位於 repo 工作樹內**（RC-5）：解析成實際路徑後，自身或任一上層目錄存在 `.git`。目錄或檔案都算，worktree 的 `.git` 是檔案 [TA 補]。

**6.3 S8（取代）**：
- 報告不得含「需」「建議」「應」「務必」「盡快」「否則」「安全」「對應」。
- 唯一例外是逐字的固定標籤「需人工判讀」：掃描前先移除這個標籤字串，再掃其餘內容；標籤後的理由文字照樣要掃。
- 掃描兩層：
  - (i) 腳本中所有字串常數（AST，含 f-string 的常數部分）；
  - (ii) 用 fixture 實跑後的 `report.md` 與 `report.json`。
- 報告不得原樣輸出 DB 裡的自由文字欄位，例如 `rule_summary`、`limit_note`、各種理由句；只能輸出截取後的 token，例如 N190-B 的指數狀態（RC-3）。
- [TA 補] 枚舉欄位（rule_id、action、status、source）只在值屬於已知集合時原樣輸出；否則輸出固定字樣「（非預期值）」並計數，避免 DB 內容進入報告。

**6.3 S12（新增）**：RC-5 的 repo 工作樹判定要有測試：
- out-dir 在含 `.git` 目錄的暫存樹內 → exit 4；
- 在含 `.git` 檔案的暫存樹內 → exit 4；
- 在樹外 → 正常執行。

**6.4（取代閘門行，新增兩句）**：三句都逐字取自 [風控-177R] RC-4，放在模組常數；測試從該檔的「」逐字抽取比對。
- 閘門行，取代原本的「N-177 部署閘門：受影響標的 X 檔（X > 0 時需要 CEO 逐檔裁示）」：
  「N-177 部署閘門：受影響標的 {n} 檔。依風控 A-1 條件 1，這個數字大於 0 時，N-177a 部署前由 CEO 逐檔在 (A)、(B) 之間選擇；本報告不預設任何一個選項。」
- 每張試算表的上方各出現一次：
  「試算回補現金 = 第一張 S2 的成交判定價 × 試算分配股數合計。這個數字假設你已依第一張 S2 在券商賣出且成交（L9），按 N-177a 的分配規則算出，不一定等於你實際成交的金額；實際成交的股數與價格，只有你的券商對帳單能確認。」
- 放在判讀圖例區：
  「可試算：本檔沒有觸發本報告列出的任何一條誤判防護，所以列出試算；這不表示試算結果與你的券商紀錄一致。」
- `{n}` 是唯一的佔位符；`report.json` 的 `gate` 欄位不變。
- 修訂一 R-α 不改變 4.4 的分配規則，所以第二句中的「N-177a 的分配規則」仍然指 4.4。

**6.5 G-c（取代）與 G-c′（新增）（RC-2）**：
- G-c 不再是誤判防護，改成事實欄，明細就是 N177-F。查詢沿用原文 SQL，篩選 `batch_no` 屬於該 symbol 現在的合格批次的列。
- **G-c′**（誤判防護）：N177-F 的列中（含 EMERGENCY），只要有任一張 `execution_date <= 第一張 S2.execution_date`，該標的就列為「需人工判讀」。
- [TA 補] 「受影響批次」讀作該 symbol 現在的全部合格批次，與 N177-F 是同一個集合。這比「只算試算分配股數大於 0 的批次」寬，方向保守。
- 工具第一版就照這個最終形式實作；原文「風控接受之後……要另提 PR」刪除。
- (B) 的可試算範圍因此擴大：受影響批次上有在途賣單、但都晚於第一張 S2 的標的，只要沒有觸發其他防護，就可以試算。
- 6.7 追加以下測試：
  - G-c′ 正例：在途單的 `execution_date` 等於或早於第一張 S2；
  - 反例：只有晚於的在途單 → 可試算，F 欄列出；
  - EMERGENCY 在途單觸發 G-c′。

**6.8 私人資料（取代「報告內含持股與現金」那一段）（RC-6）**：
- 報告留在 CEO 本機，不 commit 進 repo；`--out-dir` 在 repo 內時，工具拒絕執行（RC-5）。
- CEO 把 `report.md` 交給 coordinator，轉給 TA 與風控。收到報告的 agent（coordinator、TA、風控）在回報與審查檔中，只引用 id 與筆數，不轉錄報告內容。
- `work/`、`docs/` 與 release 紀錄（QB-10、M-1）只能記錄：
  - 閘門檔數與各類筆數；
  - 腳本 SHA-256；
  - 執行前後的 DB 雜湊、run_at；
  - 每檔以「第一張 S2 的 directive id」識別的 CEO 選擇（A 或 B），以及 apply 的時間。
- 不得記錄 symbol、股數、價格、現金金額，除非 CEO 書面同意。
- CEO 依 6.9 做的逐檔書面確認（symbol、id、金額），原件留在 CEO 本機；repo 只引用 id。
- [TA 補] (B) dry-run 的指紋不寫進 repo，只記「指紋與閘門報告一致：是／否」。理由：指紋是 (symbol, id, 金額) 的雜湊，id 已知時可以窮舉還原。
- [TA 補，待風控] RC-9 第 4 點的「TA 逐案評估書面」含股數與金額，同樣屬私人資料：不落檔進 repo，由 coordinator 直接轉交 CEO；repo 只記「id、已評估、評估日期」。這是 RC-6 與 RC-9 第 4 點同時適用時的解法。

**6.9（追加）**：
- 指紋以**閘門那次**的報告為準（RC-9 第 3 點）。
- 需人工判讀的標的，dry-run 的比對對象是「閘門報告該列的事實欄 + TA 逐案評估書面中的分配與金額」，使用同一個 apply 工具、同一套指紋檢查（RC-9 第 4 點）。
- 不得手動改 DB。

### 5. 第 8 節（CEO 決策點）的修訂（RC-9）

**D-1（取代）**：R2 停機時，閘門偵測大於 0 檔，就要逐檔在 (B) 與 (A) 之間選擇，沒有預設選項（風控 A-1）：
- (B)：依第一張 S2 回補，用券商對帳單確認；
- (A)：只對未來生效，掛 (c) 揭露。

**不得替 CEO 預設 (A)**：
- 不得因停機時間的壓力，替 CEO 預設 (A)。
- 以下任一情況，R2 延後、舊版（R1 build）恢復服務，下一次停機重跑閘門，並附 `--previous-json`：
  - (B) apply 工具尚未審查通過；
  - 需人工判讀的案子尚未評估完。
- 延後後的 R2 仍然算「R1 的下一個 release」（ADR-0040 Decision 13），(c) 不因此回復為 required。
- 延後期間不得出其他功能 release，hotfix 除外。

**閘門那次的確認**：
- CEO 以**一份**書面確認涵蓋完整清單；沿用前次選擇的列，也要列入。
- `diff_vs_previous` 標「與前次不同」的列，不沿用前次的選擇。
- (B) dry-run 的指紋必須與**閘門那次**的報告一致。

**需人工判讀的標的**：
- CEO 可以選 (A)，或提供券商資訊，由 TA 逐案評估。
- 評估結果寫成書面，依 6.8 不落檔進 repo。
- 經 CEO 依 6.9 逐檔確認後，才能用同一個 apply 工具、同樣的指紋檢查寫入。
- 不得手動改 DB。

**G-b 的情況**：預設**不重跑** REBALANCE，因為 TOTAL_DEPLOY 會跟著變大；只有 CEO 明確決定時才重跑。這與 ADR-0035 Decision 9 末段一致。

**流程（新增）**：
- 第一次執行若大於 0 檔：
  - TA 立刻起草 6.9 的 spec，讓工具在 R2 之前完成審查；
  - creative-lead 同時開始擬 (c) 的字面（suggested），以免選 (A) 時趕不上下一個 release。
- 「不需要決策的項目」：原文的「G-b 另外決定是否重跑」刪除，改為上面的預設不重跑；其餘不變。
- 第 7 節第 4 步依本節改寫為：「大於 0 檔：CEO 逐檔裁示 → (B) apply → 部署；任一前提未滿足時，依 D-1 延後 R2」。
````

---

**全文二：ADR-0041 草案（由 tech-writer 落檔為 `docs/adr/0041-…md`）**

```markdown
# ADR-0041：stock-desk 排程台 S2 成交動帳、成交移動稽核表與結算動帳的鎖內讀改寫（補充 ADR-0035、ADR-0039，不取代）

- 狀態：proposed
- 日期：2026-11-07
- 決策者：
  - tech-architect：草案；
  - risk-compliance-officer：審查。2026-11-07 CONDITIONAL APPROVE（RC-1～RC-10）；修訂一待再審；
  - CEO：核可，待定。
- 來源簡稱（都在 `work/reviews/` 下）：
  - [TA-177S]：`2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`（第 4～8 節與檔末「修訂一」）
  - [風控-177R]：`2026-11-07-N177實作規格審查與C6至C10確認-風控.md`
  - [風控-177]：`2026-11-05-N177修復與N190字面裁示-風控.md`
  - [M1]：`2026-11-05-ADR0035補充五修正一-tech-architect.md`
- 適用範圍：只有 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。

## Context（背景）
1. `store.settle` 遇到 S2（`batch_no` 為 NULL）時，只做 `_mark_schedule` 就 return。這一列已經被 claim 為 executed，但股數沒減、現金也沒入帳，所以 S2 每天重發（F8／N-177）。
2. S2 是整檔層級的單，會跨多個批次移動股數。逐批重放（ADR-0039 Decision 10）推不出它在每一批各移動了多少股。
3. ADR-0035 的 Decision 6、6′、Consequences 與 N172-C8 都寫明 `settle()` 零 diff。本 ADR 判定這是 N-172a 的範圍約束（見 Decision 4），不是 `settle` 永久不得修改的架構決策。
4. 並發結算的問題：
   - `/today` 與 `POST /settle` 都是 sync def，會在 threadpool 中並行執行，而 `_settle_pending` 沒有鎖。
   - 既有的逐批分支先在各自的連線讀批次與現金，之後以整列 `INSERT OR REPLACE` 與整值寫回。
   - S2 開始寫帳之後，並發時，已被 S2 關閉的批次會被過時讀值覆寫而復活，同一批股數的現金可能入帳兩次（[風控-177R] RC-1）。
   - `roll_peak_closes`、`trailing_on`、`defer_reset` 也以整列寫回，同樣會讓批次復活（[TA-177S] 修訂一 1.1）。
5. 限制：
   - engine 零 diff（C-B11）；
   - service 零 diff（ADR-0040 Decision 14 第 3 點）；
   - 不新增 `DirectiveStatus`；
   - 不改指令列；
   - 既有資料不得在啟動時自動遷移。

## Options（選項比較）
| 議題 | 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| S2 寫入 | 新 helper：單一 conn、`BEGIN IMMEDIATE`，只 UPDATE `remaining_shares`／`status`／`updated_at` | 原子；欄位不變式可以從 SQL 檢查 | 多一個私有 helper | 低 | 採用 |
| | 沿用 `get_batch`／`save_batch`／`set_cash` | 程式少 | 多批之間會出現半套狀態；整列重寫 | 中 | 否決 |
| 稽核 | 加法表 `playbook_fill_moves`（含 `source` 欄與零移動 sentinel） | 下游可以精確判定 | 多一張新表；動到 X-14 的表名斷言 | 低 | 採用 |
| | M0，或在 `playbook_directives` 加欄位 | 範圍小 | M0 的判定脆弱；加欄位時，一張 S2 跨多批，一個欄位裝不下 | 中 | 否決 |
| 並發 | R-α：所有動帳都在鎖內讀改寫、只寫自己的欄位；結算以外的批次寫入者改成欄位化寫入 | SQLite 寫鎖跨執行緒、也跨行程有效；可以用 trace 檢查 | 動到 buy 分支的實作；C3 擴大 | 中低 | 採用 |
| | 只修逐批 sell 分支 | diff 最小 | 其他整列寫入者仍會讓批次復活 | 不滿足 RC-1 | 否決 |
| | 行程內 `threading.Lock` | 舊分支可以零 diff | 只在單一行程內有效，靠部署假設成立 | 中 | 否決 |
| | service 層序列化 | 概念簡單 | 違反 ADR-0040 D14.3；鎖會跨過網路 I/O；只限單一行程 | 高 | 否決 |
| | 樂觀並發（版本比對） | 不持鎖 | 要動 models 與所有呼叫者 | 高 | 否決 |

## Decision（決策）
1. **S2 分支**：`settle` 新增 S2 分支，規格依 [TA-177S] 第 4 節與修訂一（N177-C1～C18、T1～T29）。
2. **稽核表**：
   - 新增加法稽核表 `playbook_fill_moves`，只有 S2 寫入；逐批列繼續走重放。
   - S2 的 `directive_id` 為 None 時，在任何寫入之前 raise。
3. **單一定義**：共用常數只有一份，由 N-177a 定義，N-188 引用。
4. **ADR-0035 的範圍判定**：
   - ADR-0035 Decision 6、6′、Consequences 中「`settle()` 零 diff」的各句與 N172-C8，判定為 N-172a 的範圍約束（ADR-0035 補充六；[TA-177S] 第 4.7 節），原文不改。
   - 仍然有效的不變式：
     - 不新增 `DirectiveStatus`；
     - 不做批次層級 claim；
     - G1 的 SQL 零 diff；
     - 不寫 `missed`；
     - 帳冊只在 claim 成功之後才動；
     - C-B6 的 buy 行為零改動。
   - **日後任何改動 `settle` 動帳語意的變更，仍然要有自己的 ADR 並經風控審查；不得把本判定讀成「`settle` 從此開放修改」。**
5. **結算動帳的並發語意（R-α，回應 RC-1）**：
   - `settle` 中每一筆會改動股數或現金的動帳（S2 與逐批 buy／sell），都在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成：讀批次與現金、計算、只 UPDATE 該分支負責的欄位、讀改寫現金。
   - missed 計數改成單一句遞增 UPDATE。
   - 結算以外的批次寫入者（`roll_peak_closes`、`defer_reset`、`_update_batch`）改成欄位化 UPDATE，不寫股數。
   - `app/` 內不再以 `INSERT OR REPLACE` 整列寫批次。
   - 結果：兩個結算請求並發時，帳冊結果等於依取得寫鎖順序的某一個循序執行；寫入值與修訂前循序執行時逐值相同（C18、T27）。
6. **ADR-0039 Decision 10**：要在群組 B 開工前補充修訂（[TA-177S] 第 4.9 節）。
7. **既有資料**：
   - 只能用離線工具處理（[TA-177S] 第 6 節的偵測工具、6.9 的 apply 工具）；
   - 啟動時自動遷移 VETO；
   - 不改指令列（(D) VETO）。
8. **部署閘門**：N-177a 的部署以偵測閘門為前提（C15；[風控-177] A-1 條件 1）。
   - R2 停機時跑最後一次偵測。
   - 結果大於 0 檔時，CEO 逐檔裁示與 (B) apply 必須在新版開始服務之前完成。
   - 前提未滿足時，R2 延後，舊版恢復服務（[風控-177R] RC-9）。
9. **release 位置**：依 ADR-0040 Decision 13，N-177a 必須是 N-190 release 之後的下一個 release，中間不得夾其他功能 release（hotfix 除外）。依 RC-9 延後的 R2，仍然算這個位置。
10. **N-177b**：
    - `settle` 改為回傳 `SettleOutcome`，只做加法。
    - 揭露兩類情況：「找不到批次列」的 buy／逐批 sell；非 EMERGENCY 逐批 sell 的零移動（Q-c）。
    - 判定取自 Decision 5 的鎖內讀值。
    - 最遲與第三包同一個 release 上線（RC-7）。

## Consequences（後果）
- 好處：
  - S2 回到「出清整檔、成交即動帳」的既有語意；每天重發與黑名單往後推的現象，只剩真正在途的情況。
  - 「哪張 S2 移動了哪批多少股」成為落檔事實。
  - 結算內部的現金讀改寫競態隨 Decision 5 消除，也就是 ADR-0035 Consequences「F2 與結算時現金的讀改寫競態」的後半段；批次不會再被過時讀值整列覆寫。
- 壞處：
  - **RC-1 的處理結果**：以 Decision 5 修正，不列為殘留；風控再審確認前為暫定。若再審後改判為殘留，必須附風控的書面接受。
  - **Q-c 的零移動無聲狀態**：非 EMERGENCY 的 S/P 在批次已無股數時零移動，而且沒有揭露；N-177a 會讓這種情況更常發生。這個狀態持續到 N-177b 上線為止，期限是最遲與第三包同一個 release（RC-7）。
  - 相鄰殘留，待風控裁示（[TA-177S] 修訂一 1.6）：
    - R-1′：REBALANCE 以鎖外讀值寫回現金，可能抹掉並發結算的現金異動；
    - R-2′：N2 在鎖外預讀，並發時可能少揭露一次。
  - N-177a 的改動範圍擴及 buy 分支與 missed 區塊的實作，以及 `roll_peak_closes`、`apply_effects`、`_update_batch`，這幾個函式不再零 diff。C-B6 的行為由 N-168 既有測試與差分測試 T27 綁住。
  - `/today` 有成交時，每筆成交多一個短的 `BEGIN IMMEDIATE`。寫鎖被佔用超過 busy_timeout（5 秒）時，依 C-11 以 `database is locked` 失敗，不會靜默略過。
  - store 有第二份「合格批次」述詞，用 parity 測試綁住。
  - 新表會動到 X-14 的表名斷言。
  - claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169）。claim 之後若當機，會留下「executed 但沒有稽核」的列，判定為未動帳（多報方向）。
  - N-188 上線前，S2 成交是兩次評估之間帳冊變動的新來源，沒有揭露（[風控-177] A-3 已書面接受，期限是第三包）。
  - 群組 A 的 P-5(c) 殘留會更常發生。
- 被約束：
  - 新增改動 `playbook_batches` 股數或 cash 的寫入，只能放在 `settle` 的私有 helper 內，並在單一 `BEGIN IMMEDIATE` 內讀改寫。
  - 結算以外的批次寫入者只能做欄位化寫入，不得寫股數。
  - 日後改動 `settle` 的動帳語意，依 Decision 4 另立 ADR 並送風控。

## 與其他 ADR 的關係
- **ADR-0035**：補充，不取代，原文不改。
  - Decision 6／6′／N172-C8 的「`settle()` 零 diff」判定為 N-172a 的範圍約束（補充六）。
  - Consequences「F2 與結算時現金的讀改寫競態」中，結算內部的現金競態由本 ADR Decision 5 消除。
  - F2（claim／settle 分屬兩個 transaction）與 REBALANCE（R-1′）仍歸 N-169，待風控裁示。
- **ADR-0039**：Decision 10 在群組 B 開工前以補充修訂（[TA-177S] 第 4.9 節）。原文不改。
- **ADR-0034**：無衝突，原文不改。
  - C-B6 的行為不變：buy 成交時複製 L4 戳記，MISSED 不加標示。
  - 實作從整列寫入改為鎖內欄位化寫入，由「N-168 既有測試斷言零改動」與 T27 守住。
  - C-B11 維持（engine 零 diff）。
- **ADR-0040**：原文不改。
  - Decision 14 第 2 點「不得新增任何改動 `playbook_batches` 股數或 cash 的路徑」，適用對象是 ADR-0040／N-190 的 build。N-177a 的 S2 分支與 Decision 5 的鎖內讀改寫，依本 ADR 審查。
  - 本 ADR 的寫入都在 `settle` 的私有 helper 內、claim 之後，所以 X-3 的前提「帳冊股數只在 claim 之後由 `settle` 改變」不變。
  - N-177a 不得併入 N-190。
  - release 位置依 Decision 13。
- **ADR-0033**：C-10 第二句已由 ADR-0035 Decision 10 判為 N-166 的範圍約束。本 ADR 對 `apply_effects` 的改動不改變行為，不衝突。
- 本 ADR 不取代任何 ADR。
```

---

**全文三：ADR-0035 補充六（4.7 判定，含 A-2 那一句）**

插入位置：`docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md` 標頭。放在第 8 行（開頭是「- 補充五（tech-architect 2026-11-04，」的那一行）之後、第 9 行「- 日期：2026-10-31（tech-architect 草案與追加評估日期 2026-10-31）」之前，成為新的第 9 行。原本第 9 行以後依序往下移。

```markdown
- 補充六（tech-architect 2026-11-07，回應 N-177a 與風控 `work/reviews/2026-11-07-N177實作規格審查與C6至C10確認-風控.md` A-2）：Decision 6「`settle()` 零 diff（避開 0034 的 C-B6）」、6′「不得……改 `settle()`」、Consequences「engine 零 diff、`settle()` 零 diff」與「被約束」中「G1……不得改 `settle()`」兩句，以及 N172-C8（[TA2] 修訂版）中 `settle()` 維持零 diff 的部分，判定為 **N-172a 的範圍約束**，不是 `settle` 永久不得修改的架構決策（理由：這些條文是為了 N-172a 當時與 N-168 並行修改 `settle` 的範圍與衝突而設，N-168 已於 9253032 合併；先例是補充四對 `settle_pending` 的同類判定）。仍然有效、日後改動 `settle` 必須遵守的不變式：不新增 `DirectiveStatus`；不做批次層級 claim（claim 仍逐列由 `claim_directive` 進行）；G1 的 SQL 零 diff；不寫 `missed`；帳冊只在 claim 成功之後才動；C-B6 的 buy 行為零改動。**日後任何改動 `settle` 動帳語意的變更，仍然要有自己的 ADR 並經風控審查；不得把本判定讀成「`settle` 從此開放修改」。** N-177a 對 `settle` 的改動（S2 分支，以及修訂一 R-α 對逐批分支讀寫方式的改寫）由 ADR-0041 承載並經風控審查。本判定自本補充落檔起生效；生效以前，qa-reviewer 依本 ADR 字面仍應判 BLOCKING，所以 N-177a 合併以本判定生效為前提。Consequences「N-172a 不改 `settle()`，C-B6 不受影響」一語描述的是 N-172a，仍為事實，不受影響。全文見 `work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` 第 4.7 節與檔末「修訂一」；本檔原文不改（比照補充一～五先例，CEO 可推翻改為另立取代 ADR）。
```

---

**哪些修訂需要再送風控**

A. **一定要再送：RC-1 選定的機制改到了既有分支。**
1. 修訂一第 1 節全部（R-α）。範圍：
   - `settle` 的 buy、sell、missed 實作改寫；
   - `roll_peak_closes`、`apply_effects` 的 `defer_reset`、`_update_batch` 改成欄位化；
   - C3、C6、C7、C9(3)、C16～C18、4.8(i)、T19、T20、T23～T29、QB-11、QB-12。
2. 4.9 第 3 點的更正：N-177a 現在會改寫 buy 分支的實作。

B. **新的判斷，需要風控裁示**
3. 4.10 追加句：「並發下也成立（T23、T24）」。
4. R-1′（REBALANCE）：二選一，接受為殘留，或另開小單。
5. R-2′／Q-g：是否同意 N2 改依鎖內回傳值判定。同意的話，N177b-C6 要跟著改。
6. 4.14 第 2 點改寫後的內容。

C. **第 5 節**
7. `empty_batch_sell` 的判定定義：排除部分移動，判定來源改為鎖內讀值。
8. RC-8「走不到」的論證寫法，請確認符合 RC-8 的條件。

D. **第 6 節中標 [TA 補] 的項目**
9. 枚舉欄位遇到非預期值時輸出固定字樣。
10. G-c′ 的「受影響批次」讀作全部合格批次。
11. 判斷 repo 時，`.git` 是檔案也算。
12. dry-run 指紋不寫進 repo。
13. TA 逐案評估不落檔進 repo。這是 RC-6 與 RC-9 第 4 點同時適用時的解法。

E. **第 8 節**
14. 兩點推論：R2 延後期間不得出其他功能 release；延後時 (c) 不回復為 required。

F. **ADR-0041 全文**：RC-10 擋它落檔。

G. **ADR-0035 補充六**：A-2 那一句風控沒有用「」給逐字版本，我是依原意轉寫的，請確認措辭。

**不需要再送**：
- RC-4 三句的放置位置（逐字照抄）；
- RC-5 的 exit 4；
- RC-3 的禁用詞清單本身；
- RC-9 中照抄的部分。

### 其他部門
本輪沒有參與。

## 三、驗證

- **讀過的文件（全文）**：
  - `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格審查與C6至C10確認-風控.md`
  - `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`
  - `/home/user/AICompany/docs/adr/0001-record-architecture-decisions.md`
- **讀過的文件（部分）**：
  - `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`：:1-30、:138-209
  - ADR-0034 的 C-B6、C-B11（grep）
  - ADR-0040 的 Decision 13、14（:255-290）
  - `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` 中 N-169 的相關列
- **讀過的程式**（`/home/user/AICompany/apps/stock-desk/backend/`，只讀，未執行）：
  - `app/playbook/store.py`：:1-100、:500-630、:740-1030、:1150-1310、:1420-1590
  - `app/playbook/service.py`：:400-430、:1215-1430、:1516-1555、:1590-1620、:1715-1740、:1830-1940
  - `app/api/playbook.py`：:560-628
  - `app/api/deps.py`：:305-334（store 是行程內單例）
  - `app/data/cache.py`：:505-534（BUSY_TIMEOUT 5 秒）
  - grep 的對象：所有 `playbook_batches` 寫入、`DELETE FROM`、`save_batch`／`set_cash`／`get_batch` 呼叫點、`LINE_BOUND_EFFECTS`、engine 的 `trailing_on`／`defer_reset`、scheduler（不碰 playbook）、uvicorn 啟動方式（compose、Dockerfile、dev-up 都沒有 `--workers`）
  - 測試：`test_playbook_same_day_race.py`（:183-391，T14 與 `_writes_inside` 對 `BEGIN IMMEDIATE` 的假設）、`test_playbook_exit_race.py`（:197-244）、`test_playbook_entry_before_exit.py`（:430-600、:1630-1660）、`test_playbook_settlement_g1.py`（:280-350）、`test_playbook_settle_on_request.py`（:70-160）
- **未查證**：
  - N-190 分支對 `roll_peak_closes`、`apply_effects`、`_update_batch`、`settle` 的實際 diff。repo 內找到的兩個 worktree 都是 N-166 之前的舊版本，不是 N-190；
  - T23／T24 的 Connection factory 注入法實際能不能跑；
  - CEO 正式環境的 worker 數。R-α 不依賴 worker 數，所以這項不影響結論；
  - RC-1 的實際並發頻率。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案。

## 四、下一步

1. **coordinator**：
   - 把「全文一」附到 `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` 檔末；
   - 依「需要再送風控」清單 A～G 送風控再審；
   - 追蹤清單：N-169 的「結算時現金讀改寫競態」在 N-177a 合併後縮小為 F2 加 R-1′；
   - 確保補充六在 N-177a 合併前落檔（A-2 的治理要求）。
2. **risk-compliance-officer**：再審 A～G。其中 A 項（R-α）通過之前，N-177a 不合併。
3. **dev-lead**：可以依修訂一第 1 節開發 N-177a，但風控再審、補充六落檔之前不得合併。PR 必須附 T23／T24 的效力證明，以及 C9(3) 的清單。
4. **data-engineer**：拿第 6 節的 [TA 補] 項目和已完成的實作逐項對照，不同之處列在 PR 說明。RC-4 的三句一律從風控原檔抽取比對，不要從本修訂抽。
5. **tech-writer**：
   - 風控確認 RC-10 與修訂一之後，把「全文二」落檔為 ADR-0041（proposed）；
   - 風控確認 A-2 句的措辭後，依指定位置把「全文三」插入 ADR-0035 標頭。
6. **creative-lead**：N-177b 的 buy 句、sell 句與 Q-c 句（`SETTLEMENT_EMPTY_BATCH_SELL_NOTE`）一起擬稿，送風控。
7. **qa-reviewer**：N-177a 依修訂後的 C3、C6、C7、C9、C16～C18、QB-2～QB-4、QB-11、QB-12 審查。
8. **devops-sre**：release 紀錄的格式依修訂一 6.8（只用 id，不記指紋）；R2 延後的規則依修訂一第 5 節。
9. **CEO**：目前沒有要決定的事。只有風控把 R-1′ 升級時才需要裁決。

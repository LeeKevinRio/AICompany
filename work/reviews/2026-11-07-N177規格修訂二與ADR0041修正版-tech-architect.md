# N-177 規格修訂二與 ADR-0041 修正版

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**修訂二和 ADR-0041 修正版都寫好了，全文在第二節的兩個 code block 裡。風控只要比對第 7 節索引列出的修改處；有三個新問題要請風控裁示。**

- **Q-g 採用方案 (ii)**：拿掉 `empty_batch_sell` 對 EMERGENCY 的排除，store 只回報與規則無關的事實，由 service 用一個函式 `_settled_line_note` 分流四句。
  - 「EMERGENCY 賣出」仍然只有 `_is_exit_sell` 一份定義。
  - N2 的條件逐項等價於 `held is None or held.remaining_shares <= 0`，差別只在讀取時點（3.6）。
  - 為了逐字對應，`== 0` 改成 `<= 0`。app 內 remaining 不會是負數，所以實際走得到的情況結果不變。
- **R-α／RC-1 已結案**，N-177a 可以照修訂一第 1 節開發。
- 依你的五點寫好的部分：4.10 追加句（逐字照風控）、4.14 第 2 點改寫、6.9 apply 工具約束、N-195 spec、ADR-0041 依 F 項修正。
- **三個要風控裁示的新問題 [待風控]：**
  1. **3.11，風控三條要求互相衝突。** EMERGENCY 的 `batch_no` 是 None 時，「warnings 不得出現 None」、「N2 字面零 diff」、「EMERGENCY 找不到批次只進 N2」三條不能同時成立：N2 的項目格式會印出「第 None 批」。
     - TA 的做法：依 RC-8，這條路徑走不到，所以「不得出現 None」的測試排除這個組合，並用具名常數列出來。
     - 另一個做法是替 N2 新增項目格式，但要有新字面，由風控決定。
  2. **5.6，新發現。** REBALANCE 先讀批次（:1535），等日線載入（可能要幾秒）之後才讀現金（:1538）。如果中間有賣出結算 commit，總資產會重複計算，TOTAL_DEPLOY 偏高，方向不保守。
     - 這個問題修訂前就存在，而且超出「不再寫 cash」，所以沒有放進 N-195。
     - TA 建議另開小單，期限與 N-195 相同。
  3. **T15 照字面做，驗不出 Q-g 的效果。** 風控要求的「T24 設定、S1 換成 EMERGENCY」我保留為 T15。但這個設定下，A 的 claim 要等 B commit 之後才會執行，舊的預讀也會讀到 0，所以換回舊碼也不會失敗。
     - 我加了 T16：注入點改在 A 呼叫 `settle` 之前，就是 R-2′ 的實際窗口，並且要求附上換回舊碼後 T16 失敗的本機輸出。

## 二、各部門回報

### tech-architect（本人，唯讀）

**評估摘要**
- Q-g 採用 (ii)，否決 (i)。方案比較在修訂二 3.2。
- N2 的判斷只有 `SettleOutcome` 一個來源。`_settle_pending` 裡的 `_batch_of` 只剩 W-B3 那一處，而且在 `settle` 之後（N177b-C9、T21）。
- 「排序比照 N2」的實際意思：N2 目前沒有排序，是照迴圈順序 append，也就是 `pending_directives` 的 id 遞增。三句的 `{items}` 照同樣規則（3.5）。
- 6.9 工具：只能對 `playbook_batches` 下 UPDATE，SET 只限三欄。[TA 補] 任何 INSERT 都禁止，備份檔與輸出檔也不得放在 repo 內。
- N-195：新增 `set_total_deploy`，只寫三個 TOTAL_DEPLOY 鍵；`rebalance` 只改 :1612 一處呼叫。不另立 ADR，因為這是移除一處既有寫入，不是新增寫入路徑。
- 順帶查證風控 A 項的 suggested：`test_playbook_same_day_idempotency.py:420-437`（`test_evaluate_today_hands_no_line_bound_effect_to_apply_effects`）已經釘住「service 不把 `LINE_BOUND_EFFECTS` 傳給 `apply_effects`」。這則測試的情境只觸發 `defer_increment`；`batch_skipped` 走的是同一個以集合比對的濾除（service.py:1916）。

**全文一：N-177 規格 修訂二（附到原規格檔末）**

````markdown
## 修訂二（tech-architect，2026-11-07；回應風控再審 [風控-177R2]）

- 依據：[風控-177R2] `work/reviews/2026-11-07-N177修訂一再審與N177b定稿-風控.md`（A：CONDITIONAL APPROVE；B：CONDITIONAL APPROVE）。
- 程式依據：同本檔第 6 行的 checkout，只讀，未執行。行號以內容定位。
- 本修訂取代本檔與修訂一的對應段落；沒提到的段落維持原文。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀；標 [待風控] 的需要風控裁示。
- 修改處索引見第 7 節；依風控指示，Q-g 與 ADR-0041 只比對修改處。

### 0. 風控再審結果的登錄（不改判斷）
- R-α（修訂一第 1 節）：APPROVE。RC-1 以修正結案，不列為殘留。
- N-177a 依修訂一第 1 節開發。合併前提：
  - ADR-0035 補充六已生效（已依 G 項定稿落檔）；
  - ADR-0041（proposed）依 F 項修正後落檔；
  - QB-11 的效力證明；
  - qa 沒有 BLOCKING。
- 修訂一 1.6 的兩項，以本節取代「[待風控] 裁示」：
  - R-1′：選 (b)，另開小單 N-195（本修訂第 5 節）。
  - R-2′／Q-g：同意，附條件，擋 N-177b 合併（本修訂第 3 節）。

### 1. 4.10 追加句（取代修訂一第 2 節「並追加（[待風控]）」的那一句）
- 修訂一：依 1.3，每一筆改動股數或現金的動帳，讀、算、寫都在同一個 `BEGIN IMMEDIATE` 內；並發結算在各批股數、open／closed 狀態與現金上的結果，等於依取得寫鎖順序的某一個循序執行，所以上述三點在並發下也成立。這個結論以 C6、C7、C17 成立為前提，由 T20、T23～T26 檢查。
- 範圍說明（不屬於追加句本身）：
  - 結算以外的寫入者在鎖外，可能把 `trailing_active`、`defer_count` 寫到剛被關閉的批次上。
  - 這不影響股數、狀態與現金，但整本帳冊的狀態不一定等於任何一個循序順序。
  - 所以本句只對這三項成立，不得改寫成「帳冊結果」。

**1′. 修訂一 1.3(5) 第一點的用語同步 [TA 補]**
- 「所以兩個結算請求的動帳結果，等於依取得寫鎖順序的某一個循序執行」改為：
- 「所以兩個結算請求在各批股數、open／closed 狀態與現金上的結果，等於依取得寫鎖順序的某一個循序執行」。
- 理由同 1。

### 2. 4.14 第 2 點（取代修訂一第 2 節的版本）
- 修訂前，以下寫入者都先在各自的連線讀批次與現金，再以整列 `INSERT OR REPLACE` 與整值寫回：
  - 舊的逐批分支（buy、sell、missed）；
  - `roll_peak_closes`、`trailing_on`、`defer_reset`。
- 並發時可能：
  - (i) 以過時讀值整列覆寫已被關閉或減少的批次，股數與 status 一起復活；
  - (ii) 讓同一批股數的現金入帳兩次；
  - (iii) 抹掉其他結算的現金異動。
- (i)、(ii) 不是 N-177a 新增的交錯。同樣的整列覆寫與重複入帳，在 N-177a 之前就存在於：
  - 逐批賣出之間：兩個請求並發結算同一批的兩張逐批 sell，各自讀到同一個 remaining；
  - 逐批賣出與 `roll_peak_closes`／`trailing_on`／`defer_reset` 之間：例如 `/today` 的 `roll_peak_closes` 讀完批次之後，並發的 `POST /settle` 賣出同一批，`roll_peak_closes` 再以讀到的舊列整列寫回。
- N-177a 新增的是 S2 也加入這些交錯（RC-1），頻率因此提高。
- (iii) 就是 ADR-0035 Consequences 已接受、歸 N-169 的「結算時現金的讀改寫競態」。
- R-α（修訂一 1.3）把 (i)～(iii) 在結算內部一併消除，不列為殘留（[風控-177R2] A 項與書面紀錄）。
- 剩下的相鄰問題：
  - R-1′（REBALANCE 寫回現金）→ N-195（本修訂第 5 節）；
  - R-2′（N2 鎖外預讀）→ Q-g，併入 N-177b（本修訂第 3 節）。
- 已知限制：
  - R-α 之前的歷史資料，沒有任何工具檢查過這類交錯；
  - 現金是單一 KV、沒有異動歷史，所以偵測不到；
  - 頻率低，不列為 N-177a 的殘留；
  - 第 6 節的偵測工具不涵蓋這一類，也不因本條擴充。

### 3. Q-g：N2 改依鎖內結果判定（擋 N-177b 合併；取代修訂一第 3 節的對應段落）

#### 3.1 缺口（[風控-177R2] B 項 R-2′／Q-g 第 1 點）
- 修訂一的 `SettleOutcome` 中：
  - `missing_batch_row` 涵蓋「EMERGENCY 找不到批次列」；
  - `empty_batch_sell` 依定義排除 EMERGENCY。
- 所以「EMERGENCY 在鎖內讀到 remaining 0」這個情況，兩個欄位都表達不出，N2 無法只靠回傳值判定。

#### 3.2 方案比較
| 方案 | 內容 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| Q-g(i) 加欄位 | 新增第三個欄位，例如 `exit_nothing_held`：EMERGENCY，而且鎖內讀不到批次或 remaining ≤ 0；兩個既有欄位不變 | 只做加法；既有欄位的語意不變 | store 要自行判斷「這是 EMERGENCY」，與 service 的 `_is_exit_sell` 形成第二份定義，日後可能漂移；EMERGENCY 找不到批次時，`missing_batch_row` 與新欄位同時為真，語意重疊，service 還要再排除一次 | 中 | 否決 |
| Q-g(ii) 拿掉排除，service 分流 | `empty_batch_sell` 不再排除 EMERGENCY；store 只回報兩個與規則無關的事實；service 以既有的 `_is_exit_sell` 在單一函式內分流 | store 不帶任何規則判斷；「EMERGENCY 賣出」仍然只有 `_is_exit_sell` 一份定義；兩個欄位互斥；四句的分流集中在一處，可以窮舉測試 | `empty_batch_sell` 的定義與 C 項接受的版本有兩處不同，要再比對；service 必須正確分流（由 T17 綁住） | 低 | **採用** |

#### 3.3 判定（取代修訂一第 3 節「判定（取代）」中的 `empty_batch_sell` 一項）
- `SettleOutcome(NamedTuple)` 仍然只有兩個欄位，日後只能再做加法。
- `missing_batch_row: bool`：定義不變。同時滿足以下條件時為真：
  - `status == 'executed'`；
  - `action in ORDER_ACTIONS`；
  - `not is_s2_fill(directive)`；
  - `batch_no is None`，或鎖內讀不到批次。
- `empty_batch_sell: bool`（取代）：同時滿足以下條件時為真：
  - `status == 'executed'`、`action == 'sell'`；
  - `not is_s2_fill(directive)`；
  - 批次在鎖內讀得到，而且鎖內讀到的 `remaining_shares <= 0`。
- 與修訂一版本只差兩處：
  - (1) 拿掉 `rule_id != 'EMERGENCY'`；
  - (2) `== 0` 改為 `<= 0`，與現行 N2 的 `held.remaining_shares <= 0` 逐字對應。app 內 remaining 不會是負數（逐批 sell 用 `max(0, …)`，S2 用 `min`），所以在走得到的範圍內，(2) 不改變結果。
- 兩個欄位互斥：`missing_batch_row` 為真時，鎖內沒有讀到批次，`empty_batch_sell` 必為假。
- 其他情況一律為假，與修訂一相同：S2（含零移動 sentinel）、missed、非下單列、部分移動。
- store 的判定不引用任何 `rule_id`。store.py 中的 `'EMERGENCY'` 字面不因 N-177b 增加。

#### 3.4 store 端
- `_settle_batch_line` 把鎖內讀取的結果交回 `settle`：有沒有讀到批次、鎖內的 remaining。`settle` 據此組出 `SettleOutcome`。
- 判定用的值，必須是同一個 `BEGIN IMMEDIATE` 內、寫入之前讀到的值。
- 各情況的回傳值：
  - `batch_no is None` 的 executed 下單列：沿用現行的提前 return，不讀 DB，回 `missing_batch_row=True`；
  - missed、S2、非下單列：兩個欄位都是 False。

#### 3.5 service 端：四句的分流（單一函式）
```python
_N2 = "exit_nothing_held"               # SETTLEMENT_EXIT_NOTHING_MOVED_NOTE
_UNBOOKED_BUY = "unbooked_buy"          # SETTLEMENT_UNBOOKED_BUY_NOTE
_UNBOOKED_SELL = "unbooked_sell"        # SETTLEMENT_UNBOOKED_SELL_NOTE
_EMPTY_BATCH_SELL = "empty_batch_sell"  # SETTLEMENT_EMPTY_BATCH_SELL_NOTE


def _settled_line_note(line: Directive, booked: SettleOutcome) -> str | None:
    """The one place that routes a settled line to N2 or an N-177b note (N177b-C10)."""
    if line.status != "executed":
        return None
    if _is_exit_sell(line):
        return _N2 if (booked.missing_batch_row or booked.empty_batch_sell) else None
    if booked.missing_batch_row:
        return _UNBOOKED_BUY if line.action == "buy" else _UNBOOKED_SELL
    if booked.empty_batch_sell:
        return _EMPTY_BATCH_SELL
    return None
```
- 名稱可以由 dev-lead 調整（Enum、Literal 都可以），但必須是單一函式；`_settle_pending` 只依它的回傳值，把該列放進對應的清單。
- `_settle_pending` 迴圈中的流程：
  - claim 成功之後，`booked = self._store.settle(...)`；
  - 呼叫 `_settled_line_note(outcome, booked)`；
  - 依回傳值 append 到四個清單之一。
- 刪除 N2 原本在 `settle` 之前的 `_batch_of` 預讀（service.py:1357-1362）。W-B3 在 `settle` 之後的 `_batch_of`（:1367）不變。
- 四個清單都依迴圈順序 append，也就是 `pending_directives` 的 id 遞增順序。這與現行 N2 `moved_nothing` 的順序相同，對應 [風控-177R2] B 件實作條件 3「排序比照 N2」。

#### 3.6 N2 的判定與現行等價，而且只有一個來源（N177b-C9）
- 現行條件：
  - `_is_exit_sell(outcome) and outcome.status == "executed"`；
  - 而且 `held is None or held.remaining_shares <= 0`；
  - `held = _batch_of(outcome)`：`batch_no` 為 None 時是 None，否則是 `get_batch` 的結果。
- 新條件：
  - `_is_exit_sell(line) and line.status == "executed"`；
  - 而且 `missing_batch_row or empty_batch_sell`。
- EMERGENCY 賣出列的 `action == 'sell'`，屬於 `ORDER_ACTIONS`（store.py:229）；`rule_id != 'S2'`，所以 `is_s2_fill` 為假。因此：
  - `missing_batch_row` ⇔ `batch_no is None` 或鎖內讀不到批次 ⇔ 現行的 `held is None`；
  - `empty_batch_sell` ⇔ 鎖內讀到批次，而且 `remaining_shares <= 0` ⇔ 現行的 `held is not None and held.remaining_shares <= 0`。
- 條件逐項相同，差別只在讀取時點：
  - 現行是在 `settle` 之前另開連線讀；新的是在 `settle` 的動帳交易內、寫入之前讀。
  - 循序執行時，兩者讀到同一個值（同一迴圈中較早的列都已 commit），所以結果相同。
  - 並發時，新的判定與實際動帳一致，這就是 R-2′ 的修正。
- 判斷來源只有 `SettleOutcome` 一個。service 不得為 N2、buy 句、sell 句、Q-c 句另讀批次。

#### 3.7 字面、項目格式與順序（[風控-177R2] B 件）
- 字面：
  - 五段字面以 [風控-177R2]「B 件：N-177b 字面」的「逐字定稿」為準：`SETTLEMENT_UNBOOKED_BUY_NOTE`、`SETTLEMENT_UNBOOKED_SELL_NOTE`、`SETTLEMENT_EMPTY_BATCH_SELL_NOTE`、`SETTLEMENT_UNBOOKED_ITEM`、`SETTLEMENT_UNBOOKED_ITEM_NO_BATCH`。
  - 只放在 `wording.py`。測試從該檔各識別名之後的第一個「」逐字抽取比對（N177b-C5）。
  - 本規格不轉錄字面，以免出現第二份。
- 項目格式：
  - buy 句、sell 句的每一項依 `batch_no is None` 選用：None 用 `SETTLEMENT_UNBOOKED_ITEM_NO_BATCH`，否則用 `SETTLEMENT_UNBOOKED_ITEM`。
  - Q-c 句只用 `SETTLEMENT_UNBOOKED_ITEM`。`empty_batch_sell` 為真時一定讀到了批次，`batch_no` 是整數。
  - 欄位：symbol、batch_no（只有 `SETTLEMENT_UNBOOKED_ITEM` 用）、shares（指令股數）、rule_id、execution_date（ISO 格式，與 N2 相同）。
  - `{items}` 以「、」連接，順序依 3.5 最後一點。
- 順序定稿：SUMMARY → W-B3 → N2 → buy 句 → sell 句 → Q-c 句。這取代修訂一第 3 節「位置（取代）」中的「（暫定）」。
- N2 的字面、`SETTLEMENT_EXIT_ITEM` 與 `exit_items` 的組法零 diff。

#### 3.8 RC-8「走不到」論證的前提補充（[風控-177R2] C 項）
- 修訂一第 3 節論證第 3、4 點，前提是「沒有任何寫入者刪除或整列重寫批次列」。
  - 在 `app/` 內，由 T19 保證；
  - 在 `app/` 外，由 6.9 工具的約束保證（本修訂第 4 節 A1、A4、AT-1～AT-3）。
- 論證其餘文字不變。「日後若發現走得到的路徑，要回 TA 與風控，不得以 N2 代替揭露」維持。
- EMERGENCY 找不到批次時進 N2、不進 sell 句：這是 Q-b 已接受的既有分流（[風控-177R2] B 項第 2 點），不是以 N2 代替揭露的新路徑。

#### 3.9 約束修訂
- **N177b-C3（取代）**：`_settle_pending` 的 diff 只限：
  - 接收 `settle` 的回傳值；
  - 以 `_settled_line_note` 取代 N2 的預讀判定：刪除 :1357-1362 的預讀，N2 的 append 移到 `settle` 之後；
  - 追加三句 warnings。
  - 取開盤價的方式、claim、G1、W-B3、N1／N1b、SUMMARY 的組法零 diff。
- **N177b-C5（補充）**：逐字比對的來源是 [風控-177R2] 的「逐字定稿」。
- **N177b-C6（取代，依修訂一 1.6）**：
  - N2、W-B3、SUMMARY 的字面零 diff；
  - W-B3、SUMMARY 的判斷零 diff；
  - N2 的判斷來源改為 `SettleOutcome`，條件與現行 `held is None or held.remaining_shares <= 0` 等價（3.6）；
  - N2 的既有測試斷言零改動。
- **N177b-C9（取代）**：
  - `missing_batch_row`、`empty_batch_sell` 只由 store 依 `settle` 動帳交易內、寫入之前讀到的值決定；
  - service 不得為 N2 與三句另讀批次；
  - `_settle_pending` 內的 `_batch_of` 只剩 W-B3 那一處，而且在 `settle` 之後。
- **N177b-C10（新增）**：
  - N2、buy 句、sell 句、Q-c 句的分流只在 `_settled_line_note` 一處，每一列至多進入其中一句；
  - 「EMERGENCY 賣出」只用 `_is_exit_sell` 判斷，不得另寫 `rule_id == "EMERGENCY"`。
- **N177b-C11（新增）**：
  - 所有結算 warnings 的渲染結果都不得含子字串「None」，比對區分大小寫。範圍是 `SettlementResult.warnings` 的每一個元素，含 unsettled 理由、SUMMARY、W-B3、N2 與三句。
  - 既有的來源代碼 `none`（`NOTHING_LOADED`）是小寫，不在此限。
  - 唯一已知的例外見 3.11。
- **N177b-C12（新增）**：項目格式依 3.7 選用；`{items}` 的連接與排序依 3.7。

#### 3.10 測試修訂與追加（全部 BLOCKING）
- **N177b-T3（修訂）**：EMERGENCY 找不到批次。
  - 用 `batch_no` 為整數、批次列不存在的列；不得用 `batch_no` 為 None 的列（見 3.11）。
  - 斷言：只有 N2，沒有 buy 句、sell 句、Q-c 句；帳冊與現金不變。
- **N177b-T15（T24 的設定，S1 換成 EMERGENCY）**：
  - 設定同 T24：
    - 同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B；
    - 一批 open、remaining=100、cost 已設；
    - B 待結算 S2（100 股），已 claim；
    - T24 的 S1 換成同一批的 EMERGENCY 賣出；
    - A 側經 `PlaybookService` 的結算流程（`_settle_pending`）執行，使用 fake 日線，開盤價為 p1。
  - 注入點與 T24 相同：
    - hook 掛在 B 第一句寫入之前；
    - hook 中另開執行緒跑 A 的結算，最多等 0.5 秒後放行 B；
    - B 完成後 join A。
  - 斷言：
    - N2 恰好出現一次，項目是該批；
    - 沒有 sell 句、Q-c 句；
    - 該批 closed、remaining 0；
    - 現金 = 初值 + p2 × 100（EMERGENCY 入帳 0）；
    - S2 稽核列 = 該批 100 股。
  - 說明：A 的 claim 是寫入，會等 B commit 之後才執行，所以在這個設定下，舊的預讀也會讀到 0，N2 本來就會出現。本測試釘住「S2 先 commit 時 N2 不漏」，不證明 Q-g 的效力；效力由 T16 證明。
- **N177b-T16（R-2′ 的決定性交錯，證明 Q-g 的效力）**：
  - 設定同 T15。
  - 注入點改為：包住 A 的 store 的 `settle`，在它被呼叫時、委派給真實 `settle` 之前執行 hook。這是 R-2′ 的窗口：A 已經 claim（舊碼也已經預讀），但 A 的動帳交易還沒開始。
  - hook：以 B 跑完 `settle(S2)` 並 commit。此時 A 不持有寫鎖。
  - 斷言：N2 與帳冊的斷言同 T15。
  - 效力證明：PR 說明附上本機輸出，顯示把 N2 暫時換回「`settle` 之前以 `_batch_of` 預讀」的判定時，T16 會失敗（N2 沒有出現）。這份對照不 commit（比照 QB-11）。
- **N177b-T17（四句互斥與 N2 等價）**：
  - 窮舉：每一組實跑一次結算。組合如下：
    - action ∈ {buy, sell}；
    - rule_id ∈ {一個既有的 buy 規則, S1, P1, EMERGENCY, S2}；
    - status ∈ {executed, missed}；
    - `batch_no` ∈ {整數, None}；
    - 批次 ∈ {不存在, remaining 0, 0 < remaining < shares, remaining ≥ shares}。
  - 每一組的斷言：
    - 該列至多出現在 N2、buy 句、sell 句、Q-c 句其中一句；
    - 出現在哪一句（或都不出現），與 3.5 的分流結果相同。
    - 本項測的是分流，不是走不走得到，所以 app 走不到的組合也要跑。
  - 差分：
    - 固定 seed，至少 300 組隨機 book 與待結算列，循序執行；
    - 測試檔內放一份現行 N2 判定的參考實作：`settle` 之前以 `get_batch` 讀取，條件 `held is None or held.remaining_shares <= 0`；
    - 新舊兩者的 N2 項目集合與順序必須完全相同。
- **N177b-T18（四句同時出現）**：一次結算同時有 W-B3、N2、buy 句、sell 句、Q-c 句。斷言：
  - 順序是 SUMMARY → W-B3 → N2 → buy 句 → sell 句 → Q-c 句；
  - 每一列只出現一次；
  - `{items}` 以「、」連接，依 id 遞增。
- **N177b-T19（不得出現「None」）**：
  - 適用範圍：T1～T18 的每一個情境，加上專設的一組：buy 與逐批 sell 的 `batch_no` 為 None；EMERGENCY 的 `batch_no` 為整數而批次列不存在；G1 拒絕；沒有開盤價。
  - 斷言：`warnings` 的每個元素都不含「None」。
  - 3.11 的組合不納入，並在測試中以具名常數列出這項排除。
- **N177b-T20（項目格式的選用）**：
  - `batch_no` 為 None → `SETTLEMENT_UNBOOKED_ITEM_NO_BATCH`；
  - `batch_no` 為整數 → `SETTLEMENT_UNBOOKED_ITEM`；
  - Q-c 句一律用 `SETTLEMENT_UNBOOKED_ITEM`。
- **N177b-T21（單一來源，靜態檢查）**：AST 檢查以下各點：
  - `_settle_pending` 中 `_batch_of` 只出現一次，而且在 `self._store.settle(` 之後；
  - N2 與三句的清單只依 `_settled_line_note` 的回傳值 append；
  - service.py 除了 `_is_exit_sell`，沒有新增 `"EMERGENCY"` 字面。
- 修訂一的 N177b-T1～T14，除 T3 外都維持。T10、T12 不變。

#### 3.11 [待風控] EMERGENCY 的 `batch_no` 為 None，與 C11 的交集
- 依 3.6，EMERGENCY 的 `batch_no` 為 None 時，`missing_batch_row` 為真，進 N2，與現行相同。N2 的項目用 `SETTLEMENT_EXIT_ITEM`，會印出「第 None 批」（風控 RC-8 已核對）。
- 以下三條要求，在這個組合上無法同時成立：
  - 「所有結算 warnings 都不得出現『None』」（B 件實作條件 2）；
  - 「N2 的字面零 diff」（B 項 Q-g 第 4 點）；
  - 「EMERGENCY 找不到批次時只進 N2」（B 項 Q-g 第 2 點）。
- TA 的處理：
  - 依 RC-8，這個組合在 app 內走不到：EMERGENCY 列只從現存的批次產生，`batch_no` 一定是整數（service.py:414-420）。
  - 所以 C11 與 T19 排除這個組合，並以具名常數列出。
  - 不改 N2 的字面，也不新增 N2 的項目格式。
- 替代方案：為 N2 新增一個不含批次編號的項目格式，`batch_no` 為 None 時選用。這需要新字面，也會改動 N2 的組法，牴觸 N177b-C6。
- 請風控二選一：
  - (a) 接受上述排除；
  - (b) 要求新增項目格式，由 creative-lead 擬稿、風控定稿。

### 4. 6.9 (B) apply 工具的追加約束（擋 6.9 工具審查；[風控-177R2] C 項追加條件、D-13 第 3 點）
適用於 TA 日後另出的 6.9 spec；該 spec 不得放寬本節。

**4.1 寫入形式**
- **A1 `playbook_batches`**：
  - 只能 `UPDATE`。SET 只限 `remaining_shares`、`status`、`updated_at`，與 4.4、C6 是同一組欄位；WHERE 以 `symbol`、`batch_no` 定位。
  - 不得 `DELETE`，不得 `INSERT OR REPLACE`／`REPLACE INTO`。
  - [TA 補] 任何形式的 `INSERT` 都不得使用，含 `INSERT OR IGNORE`：工具不建立批次列。
- **A2 `playbook_fill_moves`**：只能用一般 `INSERT`，`source='repair'`；不得 UPDATE、DELETE。
- **A3 `playbook_state`**：
  - 只寫 `STATE_CASH`，形式與 `_write_state` 的 upsert 相同；
  - 值不得為 None，因為 `_write_state` 收到 None 會 DELETE 該鍵。
- **A4 `playbook_directives` 與其他表**：
  - 零寫入；
  - 任何表都不得 `DELETE`、`DROP`、`ALTER`；
  - schema 由新版 `_init_schema` 在 6.9 第 3 點的步驟中建立，不由工具建立。
- **A5 工具若 import `app.playbook.store`**：
  - 不得呼叫 `save_batch`、`set_cash`、`set_capital`、`ensure_batches`；
  - 不得以 None 值呼叫 `_write_state`／`_set_state`；
  - 可用的符號以 6.9 spec 的白名單為準。
- 理由：
  - 修訂一第 3 節 RC-8 論證第 4 點「批次列一旦存在就不會消失」，前提是沒有寫入者刪除或整列重寫批次列。
  - T19 的 AST 檢查只涵蓋 `app/`，而 6.9 工具在 `app/` 之外。

**4.2 輸入檔路徑**
- **A6**：
  - 適用的輸入檔：含金額的 CEO 確認、TA 逐案評估的分配與金額等。
  - 輸入檔路徑解析成實際路徑後，自身或任一上層目錄存在 `.git`（目錄或檔案都算）時，工具以 exit 4 拒絕執行。
  - 判定方式與 6.2 的 RC-5 相同：兩者共用同一份實作，或以同一組測試案例參數化。
- **A7**：拒絕必須發生在開啟 DB、建立備份、讀取輸入檔內容之前。
- **A8 [TA 補]**：備份目的地與 dry-run 的輸出檔，同樣不得位於 repo 工作樹內（判定同 A6），因為內容是帳冊複本。

**4.3 測試（BLOCKING；6.9 spec 的測試清單必須包含）**
- **AT-1 靜態**：掃描工具原始碼中所有字串常數（AST，含 f-string 的常數部分）：
  - 不含 `DELETE`、`INSERT OR REPLACE`、`REPLACE INTO`、`DROP`、`ALTER`，不分大小寫；
  - 以 `INSERT` 開頭的語句，只指向 `playbook_fill_moves` 與 A3 的 `playbook_state` upsert；
  - 沒有 A5 禁用方法的呼叫點。
- **AT-2 SQL trace**：對 fixture（含多批、部分關閉）實跑 apply：
  - 所有碰到 `playbook_batches` 的語句都是 `UPDATE`，SET 只含 A1 的三欄；
  - 沒有任何 DELETE。
- **AT-3 結果**：apply 前後：
  - `playbook_batches` 的列數與 `(symbol, batch_no)` 集合相同；
  - A1 三欄以外的欄位逐值相同；
  - `playbook_directives` 逐列相同。
- **AT-4 路徑**：
  - 輸入檔在含 `.git` 目錄的暫存樹內 → exit 4；
  - 在含 `.git` 檔案的暫存樹內 → exit 4；
  - 以 symlink 指向樹內 → exit 4；
  - 在樹外 → 正常執行；
  - exit 4 時，DB 檔雜湊不變，也沒有產生備份。
- **AT-5 [TA 補]**：備份目的地或輸出檔在樹內 → exit 4。

### 5. N-195：REBALANCE 不再寫 cash（R-1′；[風控-177R2] B 項選 (b)）

**5.1 定位**
- 小單 N-195（追蹤清單已開，P1），負責：dev-lead。
- 期限：
  - 目標與 R2 同一個 release；
  - 最遲與第三包同一個 release，不得更晚；
  - 不擋 N-177a 合併，也不擋 R2 部署。
- release 位置的推論：
  - 依 Q-e，第三包是 R2 之後的下一個 release，所以 N-195 只能搭 R2，或搭第三包的那個 release。
  - [TA 補] R2 依 RC-9 延後期間，N-195 不得單獨出 release。N-195 不屬於 hotfix。
- 範圍只限「REBALANCE 不再寫 cash」，依風控 B 項不必回風控；超出這個範圍就要回風控（含 5.6）。
- 不另立 ADR：這是移除一處既有的現金寫入，不是新增寫入路徑。歸屬記在 ADR-0041 的 Consequences 與「與其他 ADR 的關係」。

**5.2 程式事實**
- `rebalance` 的讀寫順序：
  - service.py:1535 讀批次（`list_batches`）；
  - :1537 載入日線；
  - :1538 讀 `portfolio_state()`；
  - :1612 寫入 `set_capital(cash=portfolio.cash, total_deploy=new_total_deploy, source=REBALANCE_SOURCE)`。
- `set_capital`（store.py:945-967）以一次 `_set_state` 寫四個鍵：`STATE_CASH`、`STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE`。
- REBALANCE 寫回的 cash，就是 :1538 讀到的值，本身不改變現金。寫它的唯一效果，是並發時把中間 commit 的結算現金異動蓋掉。

**5.3 規格**
- store.py：
  - 新增私有 helper `_total_deploy_state(total_deploy, source, at) -> dict[str, str]`，回傳 `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE` 三個鍵。值的格式與現行 `set_capital` 逐字相同：`str(total_deploy)`、`(at or datetime.now(UTC)).isoformat()`、`source`。
  - 新增 `set_total_deploy(*, total_deploy: Decimal, source: str, at: datetime | None = None) -> None`：內容是 `self._set_state(_total_deploy_state(...))`，只寫這三個鍵。docstring 註明 D-2 與 N-195。
  - `set_capital` 只允許改成 `self._set_state({STATE_CASH: str(cash), **_total_deploy_state(...)})`，寫入的鍵與值不變。
- service.py：
  - `rebalance` 只改 :1612 這一個呼叫，改為 `self._store.set_total_deploy(total_deploy=new_total_deploy, source=REBALANCE_SOURCE)`。
  - 其餘零 diff，包括：:1535、:1538 的讀取，總資產與 TOTAL_DEPLOY 的計算，`RebalanceResult`，REBALANCE 指令列，所有字面。

**5.4 約束 N195-C1～C8（qa-reviewer 逐條檢查）**
- **C1**：
  - diff 只含：store.py 中 5.3 的 helper、`set_total_deploy`、`set_capital` 的委派；service.py `rebalance` 中的那一個呼叫；`tests/**`。
  - engine.py、models.py、wording.py、`app/api/**`、`app/data/**`、`app/services/**` 零 diff。
- **C2**：
  - `rebalance` 不呼叫 `set_capital`、`set_cash`，也不寫 `STATE_CASH`；
  - `set_total_deploy` 不寫 `STATE_CASH`。
- **C3**：`confirm_rules` 的 `set_capital(cash=capital, …)`（W9）零 diff，仍然寫 cash（使用者宣告資金）。
- **C4**：三個鍵在同一個連線、同一個交易中寫入（`_set_state` 的 `with conn:`）。不加 `BEGIN IMMEDIATE`，不改 `_write_state`。
- **C5**：不得順手修改 TOTAL_DEPLOY 的計算輸入或讀取時點（見 5.6）；要改就回 TA 與風控。
- **C6**：
  - 狀態鍵的差異只有一處：`STATE_CASH` 鍵原本不存在時，REBALANCE 不再建立它。
  - `portfolio_state()` 對缺鍵回 `Decimal("0")`，所以讀到的值不變。
  - 既有測試若斷言 REBALANCE 之後的鍵集合，要逐條列在 PR 說明，交 qa 判定。
- **C7**：
  - 獨立 PR，以 merge commit 合入 product；
  - 不得併入 N-177a、N-190、N-188、N-189 的 PR；
  - 合入前 merge 最新 product（不得 rebase），之後重跑完整 CI 與 seam。
- **C8**：release 位置依 5.1。

**5.5 測試 N195-T1～T7（全部 BLOCKING）**
- **T1（循序）**：
  - REBALANCE 之後，TOTAL_DEPLOY、set_at、source 與現行相同；
  - `STATE_CASH` 的值與 REBALANCE 前逐字相同；
  - `test_playbook_rebalance.py` 的既有斷言原樣綠燈。
- **T2（SQL trace）**：
  - REBALANCE 對 `playbook_state` 的寫入，只有三句 upsert，鍵就是三個 TOTAL_DEPLOY 鍵；
  - 任何一句的參數都不含 `STATE_CASH`。
  - overshoot 時既有的指令列寫入不受影響。
- **T3（決定性交錯：並發結算的現金異動不會被 REBALANCE 蓋掉）**：
  - 設定：
    - 同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B；
    - A 交給 `PlaybookService` 跑 `rebalance`；B 代表並發的結算請求；
    - 一批 open（remaining 100、cost 已設），有可用的估價。
  - 注入點：
    - 把 A 的 `_connect` 換成自訂 `Connection` factory；
    - 在 A **第一句寫入 `playbook_state`** 的 SQL 送出之前，執行 hook；
    - 修訂前，這個點是 `set_capital` 寫入之前；修訂後，是 `set_total_deploy` 寫入之前。兩者都在 :1538 讀取之後。
  - hook：以 B 跑完一筆結算並 commit。A 此時不持有寫鎖，所以 B 不必等待。結算參數化為三種：
    - 逐批 sell S1 40 股：入帳 p × 40；
    - 另一批 planned 的逐批 buy 100 股：扣款 p × 100；
    - N-177a 已在 base 時，加上 S2 100 股：入帳 p × Σmoved。
  - 斷言（與時序無關）：
    - 最終現金 = 初值 + 該筆結算的現金異動；
    - TOTAL_DEPLOY = A 依 :1538 讀值算出的值；
    - source = `REBALANCE_SOURCE`。
- **T3 的效力證明**：
  - PR 說明附上本機輸出，顯示把 :1612 暫時換回 `set_capital(cash=portfolio.cash, …)` 時，T3 的每一個參數都失敗（現金等於初值）。
  - 這份對照不 commit。
- **T4**：`confirm_rules` 仍然寫 cash。既有測試原樣綠燈；沒有涵蓋時補一則。
- **T5**：`set_capital` 改成委派之後，固定 `at`，寫入的四個鍵與值和修訂前逐字相同。
- **T6（AST）**：
  - `app/` 內 `set_capital(` 的呼叫點只在 `confirm_rules`；
  - `rebalance` 內恰好一個 `set_total_deploy(` 呼叫，沒有 `cash=` 關鍵字引數。
- **T7**：`STATE_CASH` 鍵不存在時跑 REBALANCE：鍵仍不存在，`portfolio_state().cash == Decimal("0")`。
- S2 參數的歸屬 [TA 補]：N-195 先於 N-177a 合併時，由 N-177a 的 PR 在 T3 追加 S2 參數，並列入 N-177a 的 QB-12 清單。

**5.6 觀察 [待風控]（不在 N-195 範圍）：REBALANCE 的總資產取自兩個不同時點的讀取**
- 程式事實：:1535 讀批次，:1537 載入日線（可能跨網路、數秒級），:1538 才讀現金。
- 兩次讀取之間如果有結算 commit：
  - 逐批 sell 或 S2：批次仍以舊股數計入市值，現金卻已含入帳。總資產重複計算，TOTAL_DEPLOY 偏高，方向不保守。
  - buy：現金已扣款，批次仍是 planned、不計入市值。總資產偏低，方向保守。
- 性質與範圍：
  - 這是修訂前就存在的「評估輸入過時」，不是寫入覆蓋；
  - N-195 只移除寫回，不改這一點；
  - N-177a 讓 S2 也加入這個窗口。
- 頻率：極低。REBALANCE 是手動、季末才跑；但窗口是日線載入期間，比 R-1′ 的毫秒級窗口寬。
- 可偵測性：
  - REBALANCE 的總資產、新舊 TOTAL_DEPLOY 會出現在回傳值與字面中；
  - 但現金沒有異動歷史，事後無法回推。
- 可能的修法（不在 N-195）：日線載入後，在同一個讀交易中重讀批次與現金，再計算。這會改變 REBALANCE 計算輸入的讀取時點，超出「不再寫 cash」，依風控 B 項要回風控。
- 請風控裁示：
  - (a) 接受為既有殘留；
  - (b) 併入 N-195，N-195 因此要回風控審查；
  - (c) 另開小單。
- TA 建議 (c)，期限比照 N-195。理由是讓 N-195 維持不必回審的範圍，趕上 R2。

### 6. 其他風控附條件的登錄（不改判斷；逐字以 [風控-177R2] 為準）
- 6.3 S8 的「（非預期值）」附 D-9：非預期值出現在某檔判定或試算用到的列時，該檔列為「需人工判讀」，不給試算金額（data-engineer）。
- 6.8 的 TA 逐案評估附 D-13 四點。第 3 點已寫入本修訂第 4 節 A6。
- 第 8 節的 R2 延後附 E 的三點條件（coordinator）。
- suggested：
  - 「service 不把 `LINE_BOUND_EFFECTS` 傳給 `apply_effects`」已由 `test_playbook_same_day_idempotency.py::test_evaluate_today_hands_no_line_bound_effect_to_apply_effects` 釘住；
  - buy 並發雙扣款記進 N-169；
  - R-1′ 修好前，以內部通知告知 CEO。

### 7. 修改處索引（風控比對用）
| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | 4.10 追加句（本修訂 1） | 取代，逐字採用 | B 項 4.10 |
| 1′ | 修訂一 1.3(5) 第一點 | 用語同步 [TA 補] | B 項理由 |
| 2 | 4.14 第 2 點（本修訂 2） | 取代 | B 項 4.14 |
| 3 | 修訂一 1.6 的狀態（本修訂 0） | 登錄 | A、B 項 |
| 4 | 第 5 節 `empty_batch_sell` 的定義（3.3） | 取代：拿掉 EMERGENCY 排除；`== 0` 改 `<= 0` | Q-g 第 1、2 點 |
| 5 | store 端回傳（3.4） | 新增 | Q-g |
| 6 | service 分流函式（3.5） | 新增 | Q-g 第 1、2 點 |
| 7 | 等價論證（3.6） | 新增 | Q-g 第 2 點、N177b-C9 |
| 8 | 字面、項目格式、順序（3.7） | 取代「暫定」 | B 件、實作條件 1～3 |
| 9 | RC-8 論證的前提（3.8） | 補充 | C 項追加條件 |
| 10 | N177b-C3、C5、C6、C9 取代；C10～C12 新增（3.9） | 約束 | Q-g 第 2、4 點、實作條件 2 |
| 11 | N177b-T3 修訂；T15～T21 新增（3.10） | 測試 | Q-g 第 3 點、實作條件 1、2 |
| 12 | 3.11 | [待風控] | 實作條件 2 與 Q-g 第 2、4 點的交集 |
| 13 | 6.9 的 A1～A8、AT-1～AT-5（本修訂 4） | 新增約束 | C 項、D-13 第 3 點 |
| 14 | N-195 spec（本修訂 5.1～5.5） | 新增 | B 項 R-1′ |
| 15 | 5.6 | [待風控] 觀察 | 新發現 |
| 16 | 本修訂 6 | 登錄 | D-9、D-13、E、suggested |

（修訂二由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。3.11、5.6 待風控裁示；ADR-0041 依 F 修正並經風控確認後才落檔。）
````

**全文二：ADR-0041 修正版（依風控 F 項；風控確認後由 tech-writer 落檔為 `docs/adr/0041-…md`）**

```markdown
# ADR-0041：stock-desk 排程台 S2 成交動帳、成交移動稽核表與結算動帳的鎖內讀改寫（補充 ADR-0035、ADR-0039，不取代）

- 狀態：proposed
- 日期：2026-11-07
- 決策者：
  - tech-architect：草案；
  - risk-compliance-officer：審查。2026-11-07 CONDITIONAL APPROVE（RC-1～RC-10）；修訂一 2026-11-07 再審 CONDITIONAL APPROVE；
  - CEO：核可，待定。
- 來源簡稱（都在 `work/reviews/` 下）：
  - [TA-177S]：`2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`（第 4～8 節，以及檔末「修訂一」「修訂二」）
  - [風控-177R]：`2026-11-07-N177實作規格審查與C6至C10確認-風控.md`
  - [風控-177R2]：`2026-11-07-N177修訂一再審與N177b定稿-風控.md`
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
   - 同樣的整列覆寫在 N-177a 之前就存在於逐批賣出之間；修訂前的歷史資料沒有被檢查過（[TA-177S] 修訂二第 2 節）。
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
   - **日後任何改動 `settle` 動帳語意，或改動其動帳讀寫方式（含並發處理）的變更，仍然要有自己的 ADR 並經風控審查；不得把本判定讀成『`settle` 從此開放修改』。**
5. **結算動帳的並發語意（R-α，回應 RC-1）**：
   - `settle` 中每一筆會改動股數或現金的動帳（S2 與逐批 buy／sell），都在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成：讀批次與現金、計算、只 UPDATE 該分支負責的欄位、讀改寫現金。
   - missed 計數改成單一句遞增 UPDATE。
   - 結算以外的批次寫入者（`roll_peak_closes`、`defer_reset`、`_update_batch`）改成欄位化 UPDATE，不寫股數。
   - `app/` 內不再以 `INSERT OR REPLACE` 整列寫批次。
   - 結果：兩個結算請求並發時，各批股數、open／closed 狀態與現金的動帳結果，等於依取得寫鎖順序的某一個循序執行；寫入值與修訂前循序執行時逐值相同（C18、T27）。
   - 範圍：結算以外的寫入者在鎖外，可能把 `trailing_active`、`defer_count` 寫到剛被關閉的批次上。這不影響股數、狀態與現金，但整本帳冊的狀態不一定等於任何一個循序順序（[風控-177R2] B 項）。
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
    - 揭露：
      - 「找不到批次列」的 buy／逐批 sell；
      - 非 EMERGENCY 逐批 sell 的零移動（Q-c）；
      - EMERGENCY 的零移動與找不到批次列，仍由 N2 揭露，N2 字面零 diff。
    - 判定取自 Decision 5 的鎖內讀值，只由 store 在鎖內決定；service 不得另讀批次來判定（N177b-C9）。
    - N2 也改依 `SettleOutcome` 判定，判斷條件與現行等價；N2 與三句的分流只有一處（Q-g；N177b-C6、C10；[TA-177S] 修訂二第 3 節）。
    - 最遲與第三包同一個 release 上線（RC-7）。

## Consequences（後果）
- 好處：
  - S2 回到「出清整檔、成交即動帳」的既有語意；每天重發與黑名單往後推的現象，只剩真正在途的情況。
  - 「哪張 S2 移動了哪批多少股」成為落檔事實。
  - 結算內部的現金讀改寫競態隨 Decision 5 消除，也就是 ADR-0035 Consequences「F2 與結算時現金的讀改寫競態」的後半段；批次不會再被過時讀值整列覆寫。
- 壞處：
  - **RC-1 的處理結果**：以 Decision 5 修正。風控 2026-11-07 再審確認，不列為殘留。
  - **Q-c 的零移動無聲狀態**：非 EMERGENCY 的 S/P 在批次已無股數時零移動，而且沒有揭露；N-177a 會讓這種情況更常發生。這個狀態持續到 N-177b 上線為止，期限是最遲與第三包同一個 release（RC-7）。
  - 相鄰問題（風控 2026-11-07 再審裁示）：
    - R-1′：REBALANCE 以鎖外讀值寫回現金，可能抹掉並發結算的現金異動；抹掉 buy 扣款時現金多記，方向不保守。
      - 處理：另開小單 N-195，REBALANCE 不再寫 cash；
      - 期限：目標與 R2 同一個 release，最遲與第三包同一個 release，不得更晚；
      - 不擋 N-177a 合併，也不擋 R2 部署；修好之前，這個競態仍在。
    - R-2′：N2 在鎖外預讀，並發時可能少揭露一次。
      - 處理：Q-g 併入 N-177b，擋 N-177b 合併；
      - N-177b 上線前，這個缺口仍在。
  - N-177a 的改動範圍擴及 buy 分支與 missed 區塊的實作，以及 `roll_peak_closes`、`apply_effects`、`_update_batch`，這幾個函式不再零 diff。C-B6 的行為由 N-168 既有測試與差分測試 T27 綁住。
  - `/today` 有成交時，每筆成交多一個短的 `BEGIN IMMEDIATE`。寫鎖被佔用超過 busy_timeout（5 秒）時，依 C-11 以 `database is locked` 失敗，不會靜默略過。
  - store 有第二份「合格批次」述詞，用 parity 測試綁住。
  - 新表會動到 X-14 的表名斷言。
  - claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169）。claim 之後若當機，會留下「executed 但沒有稽核」的列，判定為未動帳（多報方向）。
  - N-188 上線前，S2 成交是兩次評估之間帳冊變動的新來源，沒有揭露（[風控-177] A-3 已書面接受，期限是第三包）。
  - 群組 A 的 P-5(c) 殘留會更常發生。
- 被約束：
  - 在 `app/` 內，新增改動 `playbook_batches` 股數或 cash 的寫入，只能放在 `settle` 的私有 helper 內，並在單一 `BEGIN IMMEDIATE` 內讀改寫。既有的例外：
    - Decision 7 的離線工具（不在 `app/` 內）：6.9 apply 工具對 `playbook_batches` 只用 UPDATE，不得 DELETE 或 `INSERT OR REPLACE`；輸入檔在 repo 工作樹內時拒絕執行（[TA-177S] 修訂二第 4 節）；
    - `confirm_rules` 的 `set_capital(cash=capital)`：使用者宣告資金，覆寫就是它的語意。
    - REBALANCE 的 `set_capital(cash=portfolio.cash, …)` 是既有寫入者，不是例外，由 N-195 移除。
  - 結算以外的批次寫入者只能做欄位化寫入，不得寫股數。
  - 日後改動 `settle` 的動帳語意，或改動其動帳讀寫方式（含並發處理），依 Decision 4 另立 ADR 並送風控。

## 與其他 ADR 的關係
- **ADR-0035**：補充，不取代，原文不改。
  - Decision 6／6′／N172-C8 的「`settle()` 零 diff」判定為 N-172a 的範圍約束（補充六）。
  - Consequences「F2 與結算時現金的讀改寫競態」中，結算內部的現金競態由本 ADR Decision 5 消除。
  - F2（claim／settle 分屬兩個 transaction）仍歸 N-169；REBALANCE 寫回現金（R-1′）由 N-195 修正（[風控-177R2] B 項）。
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

**ADR-0041 修改處索引（風控比對用）**
| F 點 | 位置 | 改了什麼 |
|---|---|---|
| F1 | 標頭「決策者」的 risk-compliance-officer 一行 | 「修訂一待再審」改為「修訂一 2026-11-07 再審 CONDITIONAL APPROVE」 |
| F1 | Consequences 壞處第 1 點（RC-1） | 「暫定…」改為「風控 2026-11-07 再審確認，不列為殘留」 |
| F1 | Consequences 壞處「相鄰問題」 | R-1′ 改為 N-195 與期限；R-2′ 改為 Q-g 併入 N-177b |
| F1 連帶 | 「與其他 ADR 的關係」ADR-0035 第 3 點 | 「F2 與 REBALANCE 仍歸 N-169，待風控裁示」改為「F2 歸 N-169；R-1′ 由 N-195 修正」。不改的話會與 F1 矛盾 |
| F2 | Decision 5「結果」一點 | 「帳冊結果」改為「各批股數、open／closed 狀態與現金的動帳結果」 |
| F2 | Decision 5 新增「範圍」一點 | 寫明結算以外的寫入者會造成的例外，理由同 B 項 |
| F3 | Context 第 4 點，新增最後一點 | 採用風控的句子，加上出處 |
| F4 | 被約束第 1 點 | 限定在 `app/` 內；列出兩個既有例外（離線工具附 6.9 的 UPDATE-only 約束、`confirm_rules`）；註明 REBALANCE 不是例外，由 N-195 移除 |
| F5 | Decision 4 最後一點 | 換成 G 的定稿措辭，保留粗體，巢狀引號用『』 |
| F5 | 被約束第 3 點 | 補上「或改動其動帳讀寫方式（含並發處理）」 |
| F5 | Decision 10 | 補上 N2 由 `SettleOutcome` 判定（Q-g）、N177b-C9；另加 N177b-C6、C10 與修訂二出處 |
| 額外 | 來源簡稱 | 新增 [風控-177R2]；[TA-177S] 的說明加上「修訂二」 |

**對實作的約束（摘要；條文以全文一為準，可逐條檢查）**
- N-177b：N177b-C3、C5、C6、C9 取代；C10～C12 新增；T3 修訂；T15～T21 新增。T16 要附效力證明。
- 6.9 工具：A1～A8；AT-1～AT-5。
- N-195：N195-C1～C8；T1～T7。T3 要附效力證明。

### 其他部門
本輪沒有參與。risk-compliance-officer 的比對、tech-writer 的落檔都在下一步。

## 三、驗證
- **讀過的文件：**
  - `/home/user/AICompany/work/reviews/2026-11-07-N177修訂一再審與N177b定稿-風控.md`：全文
  - `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂一與ADR0041草案-tech-architect.md`：全文
  - `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`：:1-390、:600-689，以及標題與 coordinator 註記（grep）
  - `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`：:1-12（確認補充六已依 G 項定稿落檔），Decision 9、Consequences（grep）
  - `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格審查與C6至C10確認-風控.md`：RC-8（grep）
  - `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`：N-195 已開單（grep）
- **讀過的程式（`/home/user/AICompany/apps/stock-desk/backend/`，只讀，未執行）：**
  - `app/playbook/service.py`：:304-306、:1290-1419、:1516-1625；`_batch_of` 呼叫點、`NOTHING_LOADED`（grep）
  - `app/playbook/store.py`：:602-612、:920-967、:1485-1559；`ORDER_ACTIONS`、`LINE_BOUND_EFFECTS`（grep）
  - `app/playbook/wording.py`：N2、`SETTLEMENT_EXIT_ITEM`、`SETTLEMENT_NO_OPEN_PRICE`（grep）
  - `tests/test_playbook_rebalance.py`：:75-175
  - `tests/test_playbook_same_day_idempotency.py`：:405-437
- **未查證：**
  - N-177a、N-177b 都還沒有實作，`_settle_batch_line` 的回傳方式是依規格設計的；
  - T15、T16、N195-T3 的注入法能不能實際跑通；
  - 5.6 的實際頻率；
  - N-190 對 `rebalance` 的實際 diff。N195-C7 已要求合入前 merge 最新 product。
- 沒有執行任何測試。我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案。

## 四、下一步
1. **coordinator：**
   - 把全文一附到 `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` 檔末；
   - 把全文一、全文二連同兩份修改處索引轉給風控比對，並請風控裁示 3.11（a／b）與 5.6（a／b／c）；
   - 依風控 suggested，用內部通知告訴 CEO R-1′ 的事實：修好之前，REBALANCE 與結算同時執行時，結算的現金異動可能被蓋掉；
   - N-169 追蹤記下 buy 並發雙扣款的疑點。
2. **risk-compliance-officer：**
   - 比對第 7 節與 ADR-0041 索引列出的修改處；
   - 裁示 3.11、5.6；
   - 確認 F 之後，交 tech-writer 落檔 ADR-0041（proposed）。
3. **dev-lead：**
   - N-177a 照修訂一第 1 節開發；
   - N-195 可以現在開工，照修訂二第 5 節，目標搭 R2；
   - N-177b 要等風控確認 Q-g 的修改處，並裁示 3.11 之後才能定案。
4. **CEO：** 目前沒有要決定的事。5.6 如果風控升級，才需要裁決。

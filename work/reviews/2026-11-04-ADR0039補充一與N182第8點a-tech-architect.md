# ADR-0039 補充一與風控第 8 點 (a) 書面確認

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：風控第 8 點 (a) 書面確認，以及 ADR-0039 補充一

## 一、本次結論

**1. 第 8 點 (a)：書面確認成立。**
- 只看 app 程式能走到的路徑，unauthored 狀態下不可能存在待成交的 R 系列買單。例外只有 seed、手動改 DB，或換上一份內容不一致的 DB 檔。
- authorship 沒有任何從 true 變回 false 的路徑。
- 另外確認一點：`user_authored` 的判斷**與日期無關**。所以改變 `as_of` 或系統時鐘，都不會讓它翻回 false。
- 依據見第二段 A。

**2. ADR-0039：採「補充一」，不改寫 v3。理由有四：**
- 風控明文要求「以補充方式寫入」。
- v2 剛落檔，風控這次回審是對著 v2 的條號寫的；改寫會讓他們的引用失效。
- 這五項加上狀態更新都是局部修改，v2 的骨架不變。
- dev-lead 即將開工 N-171-A，qa 審一份短的差異比審 300 行的重寫可靠。
- 代價是讀者要讀兩層。我建議 CEO 核可轉 accepted 時，由 tech-writer 把 v2 和補充一機械合併成 v3，語意不變。

**3. 補充裡有兩處和風控原文不完全一樣，請風控確認：**
- **群組 B 的 `LOOKBACK_DAYS`：證明不了它是超集，所以我撤回日曆日下界，改成 SQL 不設下界（S-5）。**
  - 資料有缺口時（指數載入失敗、個股缺 bar），日曆在範圍內的交易日可能不足 20 天。保留期因此被拉長，超出 180 個日曆日的下界，列就會被靜默漏掉。
  - 而且 authored 路徑的日曆是在 `read_in_flight` 之後才建的，讀取當下沒辦法依日曆決定下界。
- **A-6 的測試 (m)：「calendar 沒有被呼叫」照字面無法斷言，改成三項等價斷言（S-2 第 5 點）。**
  - 原因是 unauthored 路徑本來就會建 `TradingCalendar(())`：`build_exit_confirm` 在 `service.py:1113-1118`，群組 B 的 unauthored 日曆也是這樣。
  - 改法維持原意：A-6 不經過 calendar。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### A. 第 8 點 (a) 書面確認

**命題一：unauthored 狀態下，除了 seed 或手動改 DB，不存在待成交的 R 系列買單。成立。**
- **買單只有一個寫入點。**
  - app 內產生 `action="buy"` 的只有 `engine.py:979`，`rule_id="R1"`。grep 全 app，`action="buy"` 只出現這一處。
  - `engine.evaluate` 在 app 內唯一的呼叫點是 `service.py:1193`，位在 `evaluate_today` 的 authorship 閘門之後（`:1148-1150`）。產出的列只經 `commit_evaluation` 寫入。
- **寫 `playbook_directives` 的另外兩條路徑都不寫 buy：**
  - `record_directives` 只有 `rebalance` 呼叫，寫入的列是 `action="none"`（`service.py:900-917`、`:937`）；
  - `commit_emergency_exit` 只寫 EMERGENCY 賣單。
- **app 外的程式：**`backend/scripts/n172_duplicate_probe.py` 以唯讀模式開 DB（`?mode=ro`，`:244`）。其他會寫 playbook 表的只有 tests。
- **推論：**每一筆 buy 列寫入時，authorship 都是 true。

**命題二：authorship 沒有從 true 變回 false 的路徑。成立。**
- **判斷依據：**`rule_set_authorship` 只看兩項（`store.py:915-947`）：
  - `playbook_state` 裡有沒有 `STATE_RULE_SET_CONFIRMED_AT`；
  - `playbook_rule_params` 的**總列數**是否大於 0。
  - 兩項都不帶 `on_date` 條件，所以 `user_authored` 與日期無關。`on_date` 只影響 `version` 和 `rule_set_date`。
- **`playbook_rule_params` 不會被刪：**
  - 全 app 沒有對它的 DELETE；
  - 寫入只有 `confirm_rule_set` 和 `submit_rule_change`，都是 `INSERT OR REPLACE`，列數不會因此減少；
  - playbook store 裡沒有 DROP，也沒有重建表（DROP 和 RENAME 只出現在 positions 和 sectors 的 store）。
- **確認旗標不會被刪：**
  - `playbook_state` 唯一的刪除點是 `_write_state` 收到值為 None 時（`store.py:457-467`）；
  - `STATE_RULE_SET_CONFIRMED_AT`、`STATE_RULE_SET_VERSION` 只由 `confirm_rule_set` 寫入，值是時間戳和版本字串，從不為 None（`:969-974`）；
  - 其他 `_set_state` 呼叫點都不碰這兩個 key（`:811`、`:847`、`:860`、`:863`、`:866`、`:869`、`:1186`）。
- **API 沒有刪除或重設規則集的端點：**playbook router 只有 `/today`、`/settle`、`/rule-set`、`/confirm-rules`、`/rebalance`、`/emergency-exit`。

**例外與前提**
- 例外：seed、手動改 DB、換上一份內容不一致的 DB 檔。
  - 換成全新的 DB 檔時 authorship 是 false，但也沒有 buy，不變式仍成立。
  - 還原一份一致的備份，也仍成立。
- 讀的是 product 工作樹，也就是切面之前的程式。切面依 QB-1 只動結構；N-182 依交件說明沒有碰 authorship，也沒有新增寫 buy 的路徑。
- 這兩個命題目前沒有守門測試，所以我把它們寫成補充一 S-6 的約束 C21，加上測試。
- 回審觸發照風控第 8 點 (d) 和 P-4：出現 true→false 路徑，或 N-175 改成在 unauthored 下結算。

#### B. 形式選擇：補充或 v3

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| 補充一（附在 v2 之後） | 符合風控要求；風控引用的 v2 條號仍有效；差異短，好審 | 讀者要讀兩層 | 兩層之間可能有不一致：補充一用「取代 v2 某句」明列，降低這個風險 | **採用** |
| v3 全文改寫 | 單一文本 | 約 300 行重寫，重審成本高；風控的條號引用失效；違反風控明示的形式 | 謄寫時無意改動語意 | 不採；建議轉 accepted 時機械合併 |

#### C. 可直接落檔的文字

**檔頭行**（貼在 ADR-0039「日期」行之後）

```
- 補充一（tech-architect 2026-11-04，回應 `work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md`）：A-15 欄位與同列順序、A-6 謂詞、N171-C17 的形狀、P-5(c) 殘留、群組 B 讀取下界（撤回 `LOOKBACK_DAYS` 日曆日下界）、authorship 單調性前提（C21），以及 Decision 11、13、16 與「待決」的狀態更新，以本檔末「補充一」節為準；v2 本文不改。轉 accepted 時可由 tech-writer 機械合併為 v3，語意不變。
```

**全文**（附在 ADR-0039 檔末）

```
## 補充一：風控 2026-11-04 回審的落地事項

- 日期：2026-11-04
- 決策者：tech-architect；字面與條件出自 risk-compliance-officer（`work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md`，下稱 [風控 1104]）
- 性質：補充 v2，不改 v2 本文。下文寫「取代」的地方，以本補充為準。
- 程式位置是 2026-11-04 工作樹 `product/stock-desk` 的快照（切面尚未落地），請以內容定位。

### S-1 A-15 欄位與同列順序
1. 識別名 `PENDING_EXIT_SHARES_REDUCED_NOTE`（A-15，required）。逐字以 [風控 1104] 第 4 點為準，沒有佔位符。
2. 不新增欄位，放進 `PendingExitRow.notes`。和 A-6、A-11、A-12 一樣是同列附註，由後端判定，前端不做判斷。
3. 渲染條件：該行的任一底層列 `shares` 大於該行的 `shares`（也就是批次在讀取點的 `remaining_shares`）。
   - 底層列：歸入該行的 EMERGENCY 候選列，同 symbol、同 batch_no、同類別。unauthored 路徑取該批次的全部列。
   - 由純函式 `exit_row_shares_reduced(line_shares: Sequence[int], *, remaining_shares: int) -> bool` 判定。
   - 輸入只取同一次 `read_in_flight` 的列與批次，不經分類，不用 calendar，不呼叫 resolver。
   - covering、stale、unclassified 三類的行都適用，unauthored 路徑也適用。
4. 同列順序固定，由後端組好：
   - covering 行與 unclassified 行：`text`（A-5）→ `notes` 依序為 [A-6]、[A-15] → `entry_before_exit_note`（W-B2L）。
   - stale 行：`text`（`EMERGENCY_EXIT_STALE_ITEM`）→ `notes` 依序為 A-11 或 A-12、[A-15] → `entry_before_exit_note`。
   - 前端依 `text`、`notes`（照清單順序）、`entry_before_exit_note` 的順序渲染。不得重新排序、篩選或自行撰寫文字。
   - 前端不得以 `pending_exit_directives` 渲染任何文字。
5. 剩餘股數歸零時，批次已非 open，該行不在 A（見 S-4）。A-15 不處理這種情況。

### S-2 A-6 謂詞（[風控 1104] 第 1 點）
1. 謂詞是純函式 `exit_row_past_due(execution_dates: Sequence[date], *, as_of: date) -> bool`，等於 `any(d < as_of for d in execution_dates)`。
2. `as_of` 用同一次 `evaluate_today` 的 `as_of`，即 `today or datetime.now(UTC).date()`，UTC 日期。這與 S3（`service.py:1317` 的 `day < as_of`）同一口徑。不得改用 `data_date`。
3. 不得經過 `TradingCalendar`（空日曆也不行），不得讀日線，不得呼叫 resolver。函式簽名不收 calendar，也不收 bars。
4. 只用在 covering 行與 unclassified 行，v2 Decision 4 不變。
5. 測試口徑：unauthored 路徑本來就會建 `TradingCalendar(())`（`build_exit_confirm`，以及群組 B 的 unauthored 日曆），所以不斷言「整條路徑沒有呼叫 calendar」。改為三項：
   - (a) AST／簽名測試：`exit_row_past_due` 不收 calendar 與 bars；函式體不引用 `TradingCalendar`、`calendar`、`load_` 或任何 resolver；
   - (b) unauthored 回應出現 A-6 時，market resolver 與 index resolver 的呼叫次數都是 0；
   - (c) property test：任意日期序列與 `as_of` 下，結果等於 `any(d < as_of)`。

### S-3 N171-C17 的形狀（取代 v2 附錄 A 的 C17）
1. 位置：新增 service 方法 `PlaybookService.settle_on_request(*, today: date | None = None) -> SettlementResult`，歸 N-171 擁有。
   - `POST /api/playbook/settle` 改呼叫它。
   - `app/api/` 內不得直接呼叫 `settle_pending(`。
2. 流程：
   - `as_of = today or datetime.now(UTC).date()`；
   - 第一步讀 `self._store.rule_set_authorship(as_of).user_authored`。這和 `evaluate_today` 是同一個判斷，必須在任何 `pending_directives`、日線載入、claim 之前；
   - 為 false 時，直接回 `SettlementResult(settled_on=as_of, settled=[], unsettled=[], warnings=[wording.SETTLEMENT_UNAUTHORED_NOTE])`。`executed`、`missed` 由 property 算出，都是 0；
   - 為 true 時，`return self.settle_pending(today=as_of)`，行為不變。
3. 不動的部分：`settle_pending`、`_settle_pending`（ADR-0035 補充四 S-2.4、SEAM-T6）、`evaluate_today`。
   - 理由：閘門若放進 `settle_pending`，SEAM-T6 的等式在 unauthored 情境就不成立；authored 的 `/today` 也會重複讀一次 authorship。
4. 回應：HTTP 200。`warnings` 恰好是 `[SETTLEMENT_UNAUTHORED_NOTE]`，不得同時有 `SETTLEMENT_NOTHING_PENDING`、`SETTLEMENT_SUMMARY` 或其他任何句子。字面逐字以 [風控 1104] 第 2 點為準。
5. 零寫入、零載入：trace 只出現 SELECT，沒有 INSERT／UPDATE／DELETE；market resolver 與 index resolver 都呼叫 0 次。
6. `/today` 不帶這句：
   - unauthored 的 `/today` 維持 `settlement=None`；
   - `evaluate_today` 不呼叫 `settle_on_request`；
   - `SETTLEMENT_UNAUTHORED_NOTE` 在 `/today` 回應中出現 0 次。
7. 合併：C17 與這句字面，放在 N-171-A 的同一個 PR，或更早的 PR（[風控 1104] 結論條件 4）。
8. 回審觸發：N-175 改成在 unauthored 下結算，或 S-6 的單調性被打破時，A-13 和這句字面都要回審。

### S-4 P-5(c) 的殘留（取代 v2 Consequences 中「closed 批次上、仍算涵蓋的未結算列……（P-5(c)，待風控）」一句）
1. 「在帳冊仍記為持有」定義為 open 且 `remaining_shares > 0`，也就是 `_read_exit_state` 的 `open_batches`。C11、A-2 修訂版、NB-6 第 2 段第二版共用這個定義，不得另寫。
2. 所屬批次在帳冊已不再記為持有的未結算出清列，不在 A，由 A-2 修訂版明示這個範圍。這類列在 `/today` 上只有以下揭露：
   - (i) 符合判準 Z：結算區附 N1，批次子句為「已無持股」；
   - (ii) 已到期但不符合判準 Z：結算區只有 `SETTLEMENT_NO_OPEN_PRICE`；
   - (iii) 未到期：不顯示，結算時以 N2 揭露一次。
3. (ii)、(iii) 是風控書面接受的殘留，根源是 F4／N-169 與 N-166 之前的重複列，N-169 落地時回審。
4. (ii) 的畫面上仍有「賣出 N 股、待結算」，有誘發重複賣出的風險。這是既有字面，不在 N-171 範圍，風控列為 suggested，交 N-169 一併處理。

### S-5 群組 B 的讀取下界（取代 v2 Decision 10「下界取 `settled_at >= as_of − LOOKBACK_DAYS` 個日曆日」）
1. 條件（[風控 1104] 第 5 點）：讀取結果必須是保留期判定的超集。凡是 `as_of <= calendar.shift(settled_on, 20)` 的列，都必須讀到；這裡的 calendar 就是做判定的那一份。
2. 判定：日曆日常數下界**無法證明**是超集。
   - `shift` 對起點單調。所以超集成立的充分條件是：calendar 在 `[as_of − L, as_of − 1]` 內至少有 20 個交易日。
   - 資料完整時，這個條件成立，而且餘裕很大：180 個日曆日約有 120 個交易日，春節長假約 9 個日曆日。unauthored 用空日曆，交易日就是平日，也成立。
   - 但 authored 路徑的 calendar，在觀察範圍內以「當天有沒有 bar」判定交易日。指數載入失敗、個股缺 bar 時，範圍內的交易日可能不足 20，保留期被拉長而超出下界，列會被靜默漏掉。
   - authored 路徑的 calendar 是在 `read_in_flight` 之後才建的，讀取當下無法依 calendar 決定下界；事後發現不足，也不能補讀（ADR-0035 補充四 R-4）。
3. 決策：
   - 群組 B 的 SQL 不設 `settled_at` 下界，保留期只由 `settled_exit_retained` 判定。B-4（出清鎖內）同樣處理。
   - 成本：候選列是歷來判定 executed 的 EMERGENCY 賣單。每個批次一生最多一列實際減少股數，另有 N-166 之前的重複列，所以總量受批次總數限制，不會隨天數失控。重放需要的賣出列，也只讀這些批次的。
   - 日後若量測證明需要下界，只能用「讀取前就能決定、且對任何 calendar 都成立」的下界，由 tech-architect 另出補充。
4. 測試：
   - TB2 加春節長假的邊界案例（風控）；
   - 新增 TB8：calendar 稀疏（指數載入失敗、個股缺 bar），使某列 `settled_on` 早於 `as_of − 180` 個日曆日、但 `shift(settled_on, 20) >= as_of`，這列仍要列出；
   - TB4 的 trace 確認群組 B 的 SQL 不含 `settled_at` 下界。
5. 這一節屬於 B 的閘門，不影響 A 的合併。

### S-6 authorship 單調性（前提；P-5(b)、A-13、C17 與 N-182 的 unauthored 不渲染 W-B6b 都依賴它）
1. 前提：`rule_set_authorship(d).user_authored` 只會從 false 變成 true，而且與 `d` 無關。
2. 依據（讀碼）：
   - 判斷只看確認旗標，以及 `playbook_rule_params` 的總列數；
   - `playbook_rule_params` 沒有 DELETE，寫入都是 `INSERT OR REPLACE`；
   - 確認旗標只由 `confirm_rule_set` 寫入，值從不為 None；`_write_state` 只有在值為 None 時才刪除 key；
   - playbook 的表沒有 DROP，也沒有重建。
3. 推論：買單只由 `engine.py:979` 的 R1 產生，只經 authored 的 `evaluate_today` 寫入。因此 unauthored 下不存在待成交的 R 系列買單。例外是 seed、手動改 DB，或內容不一致的 DB 檔。
4. 回審觸發：任何 PR 新增 true→false 的路徑，或 N-175 改成在 unauthored 下結算，就送風控回審 A-13、`SETTLEMENT_UNAUTHORED_NOTE`，以及 N-182 解讀點 5。

### S-7 狀態更新
1. Decision 11 的 A 閘門：「P-4、P-5 的退回項，風控重審通過」改為 [風控 1104] 的四項：
   - A-2 修訂版；
   - A-15；
   - NB-6 第 2 段第二版；
   - C17 加 `SETTLEMENT_UNAUTHORED_NOTE`，放在同一個 PR 或更早的 PR。
   其餘字面維持 11-03 定稿：A-1、A-3～A-9、A-11～A-14、`EMERGENCY_EXIT_STALE_ITEM`。前端時點與 S-A～S-D 照舊。
2. Decision 13（NB-6）：第 2 段改用第二版。第一版和 11-03 修訂版，在 grep 中都要為 0。仍然原子替換。
3. Decision 1：`lead_template` 改用 A-2 修訂版，仍保留字面上的 `{read_at}`。
4. Decision 10（B，仍受閘門限制）：
   - `{shares}` 取實際減少的股數，風控 P-7(i) 已確認。少於該列股數時，同列附 B-5（草稿）。B 的行因此要加 `notes: list[str]`，B 閘門通過時定案；
   - 重放與帳冊不一致只會發生在 F2 並發窗口，風控 P-7(ii) 已確認，歸 N-169；
   - 保留期從 `settled_at` 的 UTC 日期起算（CEO #103 知悉）；
   - B-2 末句改用 [風控 1104] 的修訂草稿。
5. Decision 16 的 P-8：「晚幾毫秒」更正為「可能晚到秒級」，風控確認不影響語意。
6. 待決：P-4、P-5(c)、P-6、P-7、P-8、A-6 已由 [風控 1104] 結案。剩下的有：
   - S-2 第 5 點、S-5 待風控確認；
   - B-1～B-5 待核可；
   - CEO 核可轉 accepted；
   - PM 出 PRD v0.2，含 F-8(2)(a)／AC-N171-12，以及 A-15 的 AC。

### S-8 附錄 A、B 增修
- 附錄 A（皆為 BLOCKING）：
  - C17′：以 S-3 為準，取代 v2 的 C17。
  - C21：S-6 的前提有守門測試：
    - app 內沒有 `DELETE FROM playbook_rule_params`，playbook 的表沒有 DROP；
    - `STATE_RULE_SET_CONFIRMED_AT`、`STATE_RULE_SET_VERSION` 只在 `confirm_rule_set` 內寫入，且不以 None 寫入；
    - 對任意兩個日期，`user_authored` 的結果相同。
  - C22：A-15 依 S-1 判定與排序；前端不以 `pending_exit_directives` 渲染文字。
  - C23：A-6 依 S-2。
  - C24：群組 B 與 B-4 的 SQL 不設 `settled_at` 下界（S-5）。
- 附錄 B：
  - T17′：S-2 第 5 點的 (a)(b)(c)。
  - T18′：S-3 第 4～6 點，包括 trace、resolver 0 次、`/today` 出現 0 次、authored 時行為不變。
  - T25：P1 先部分減股之後，出現 A-15，股數等於剩餘股數；股數相等時不出現；三類的行都測（[風控 1104] (k)）。
  - T26：批次已 closed 的未結算出清列不進區塊，A-2 照常出現（[風控 1104] (l)）。
  - T27：前端守門：不以 `pending_exit_directives` 渲染文字；同列依 `text`、`notes`、`entry_before_exit_note` 的順序渲染。
  - T28：C21 的守門測試。
  - TB2′、TB8：見 S-5 第 4 點。
  - T22 增列（suggested）：正常回應中，`{read_at}` 的代入值不得是「時間不明」。
```

#### D. 對實作的約束（摘要，qa 可逐條檢查）
1. `app/api/` 內 grep `settle_pending(` 為 0；`/settle` 只呼叫 `settle_on_request`。
2. 在 N-171-A 的 PR 內，`settle_pending`、`_settle_pending`、`evaluate_today` 的 diff 不碰 authorship。
3. `exit_row_past_due`、`exit_row_shares_reduced` 是純函式，簽名不收 calendar、bars 或 resolver。
4. 群組 B 的 SQL 裡沒有 `settled_at >=`。
5. C21 的守門測試存在且綠燈。

### 其他部門
本次未參與（純評估）。需要的經手見第四段。

## 三、驗證

**讀過的文件**
- 風控 `work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md` 全文。
- 我的 `work/reviews/2026-11-04-ADR0039v2答覆風控P1至P8-tech-architect.md` 全文。
- `docs/adr/0039-…md` 的檔頭，並 grep 了 C17、C20、`LOOKBACK_DAYS`。確認目前落檔的是 v2，還沒有任何補充。

**讀過的程式**（product 工作樹）
- `store.py`：`:66-84`、`:457-467`、`:470-509`、`:776-778`、`:870-1000`、`:1086-1148`。
- `service.py`：`:594-713`、`:898-942`、`:1048-1253`、`:1317`。
- `models.py`：`:423-459`。
- `api/playbook.py`：`:100-121`、`:299-325`、`:445-457`，以及 router 清單。
- `data/calendar.py`：`:55-134`。
- `engine.py`：`:770-994`。

**grep 過**
- 全 app 的 `action="buy"`、`DELETE FROM`、`DROP TABLE`、`RENAME`、`_set_state(`／`_write_state(`、`STATE_RULE_SET_*`、`record_directives(`、`evaluate(`。
- app 以外引用 `PlaybookStore` 的程式：只有唯讀的 probe 腳本。

**沒驗證到的事**
- 全部是讀碼推論，沒有執行任何測試。
- S-5 說資料缺口會讓交易日不足 20，是依 `TradingCalendar.is_trading_day` 在觀察範圍內的語意推得的，沒有實際重現。建議由 qa-automation 以 TB8 重現。
- N-182 與切面分支看不到，S-6 的「沒有新增路徑」是依交件說明判斷的。

**本次限制**
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案，沒有使用 git。

## 四、下一步

1. **coordinator／tech-writer：**
   - 檔頭行貼在 ADR-0039「日期」行之後；
   - 全文附在 ADR-0039 檔末，標題「補充一」；
   - 本回報存為 `work/reviews/2026-11-04-ADR0039補充一與N182第8點a-tech-architect.md`。
2. **risk-compliance-officer：** 確認兩處和原文不同的地方：
   - S-2 第 5 點：(m) 的斷言改為三項，意旨不變；
   - S-5：撤回下界，改為不設下界。這比原條件更嚴，屬於 B 閘門。
   第 8 點 (a) 已在第二段 A 書面確認。
3. **dev-lead（N-171-A）：** 以 v2 加補充一為準，重點是 C17′、C21～C23、T17′、T18′、T25～T28。
4. **qa-reviewer：** 審 N-171-A 時，附錄 A 以 v2 加補充一 S-8 為準。審 N-182 時，可以把 S-6 當作解讀點 5 的技術依據。
5. **product-manager：** PRD v0.2 依 S-4、S-1 改寫 AC-N171-12，並新增 A-15 的 AC。
6. **CEO（只需知悉）：** 轉 accepted 時，建議把 v2 和補充一機械合併成 v3。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md
- /home/user/AICompany/work/reviews/2026-11-04-ADR0039v2答覆風控P1至P8-tech-architect.md
- /home/user/AICompany/docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py
- /home/user/AICompany/apps/stock-desk/backend/scripts/n172_duplicate_probe.py

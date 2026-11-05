# ADR-0035 補充五：同日重評估顯示的舊列在帳冊動帳後的同列揭露（N-188）

- 日期：2026-11-04
- 決策者：tech-architect（規格）；risk-compliance-officer 定向（`work/reviews/2026-11-04-N188方向裁示-風控.md`：採 (1b)、同列 note、N2 接受多報、與 W-B2LS 的互斥與順序、P1；`work/reviews/2026-11-04-N189方向裁示-風控.md` 第二節之 2：D1／D2 的同列位置與順序）
- 性質：補充 ADR-0035 Decision 4，不取代。依補充四 S-6 R-3 修訂 S-3 固定項第 4 項（`_lines` 簽名）；修訂補充四釐清七 E-30 第 3、4 點；擴充 S-7 QB-7；新增 QB-18。不改 golden，不授權重錄。ADR-0035 原文不改；CEO 可推翻，改為另立取代 ADR。
- 依據：`work/reviews/2026-11-04-N188查證與方向評估-tech-architect.md`；`work/reviews/2026-11-04-N189查證與方向評估-tech-architect.md` 第二節之 5；`work/reviews/2026-11-04-N168釐清七E30裁示-風控.md`；補充四 S-2～S-7 與釐清一～七。
- 程式位置：2026-11-04 工作樹 `product/stock-desk` 的快照（N-168 尚未合併，其分支 head 為 `5d6056c`），會漂移，請以內容定位。全部是讀碼判定，未執行。
- 字面規則：本檔只寫識別名。實際文字由 creative-lead 擬稿，風控逐字定稿，只放在 `wording.py`；風控核可前不得合併。

## X-1 範圍
1. 對象：`/today` 的 `directives` 中，`action='sell'` 且 `rule_id ∈ SETTLED_SINCE_RULE_IDS = ("S1","S2","P1","P2","P3")` 的 logged 列（Decision 4 取最小 id 的那一列，以下記為 L）。
2. 不適用：R／M1 列（ADR-0035 Consequences 已接受首次決策為準，另由 G1、W-B6b 處理）；EMERGENCY（不在 logged 內，由 A-15、N-171 區塊處理）；REBALANCE；出清回應；三個在途清單；N-171 區塊的各列。
3. 只加揭露，不改任何指令的股數、時效或是否寫入（Decision 1、3、4，N172-C6、C11 全部維持）。

## X-2 動帳述詞（只定義一次）
1. `PlaybookStore.BOOK_MOVING_SETTLEMENT_SQL`：類別屬性，**緊接在 `def settle` 之前**，作用在別名 `s` 的 `playbook_directives` 列上：
   `s.settled = 1 AND s.status = 'executed' AND s.batch_no IS NOT NULL AND s.action IN (ORDER_ACTIONS) AND EXISTS (SELECT 1 FROM playbook_batches AS b WHERE b.symbol = s.symbol AND b.batch_no = s.batch_no)`
   - 對應 `settle` 走到動帳分支的條件：`status == "executed"`、`batch_no is not None`、批次列存在、buy／sell 分支。`#:` 註解要寫明這個對應關係，以及「N-177 改 `settle` 時必須同步修改」。
   - `settle` 本身零 diff（docstring 也不改）。
   - 批次列從不刪除（`store.py` 沒有 `DELETE FROM playbook_batches`），所以讀取當下的 EXISTS 是 settle 當時條件的超集，只會多報、不會漏報。
2. 本列寫入後是否動帳（`_read_settled_since`），對每一個在 X-1 範圍內的 L 判定：
   `EXISTS (SELECT 1 FROM playbook_directives AS s WHERE <BOOK_MOVING_SETTLEMENT_SQL> AND s.symbol = L.symbol AND (L.batch_no IS NULL OR s.batch_no = L.batch_no) AND COALESCE(s.settled_after_id, :floor) >= L.id)`
   - S2（`batch_no` 為 NULL）看同一 symbol；逐批列看同一批。
   - 不排除 `s.id = L.id`：依讀碼，L 不可能在自己仍是當日執行日時就被結算；萬一發生，結果往觸發的方向。
   - `:floor` 的定義見 X-4 第 3 點；鍵不存在時，NULL 戳記一律視為大於等於任何 id，也就是觸發。
3. 讀取點：
   - 在 `commit_evaluation` 的 `BEGIN IMMEDIATE` 內，同一個 conn，接在 logged 列讀取之後呼叫一次。
   - 把現有 `_read_logged` 的查詢與「每個 K1 取最小 id」抽成 `_read_logged_rows(conn, execution_date) -> list[PendingDirective]`。`_read_logged` 改為回傳它的 `.directive`，行為零差異。
   - `_read_settled_since(conn, rows)` 只吃這份 rows 的 id，不得再寫一份「每個 K1 取最小 id」。
   - 只允許 SELECT。
4. 結果以加法欄位寫入 `EvaluationCommit.settled_since_keys: frozenset[DecisionKey] = frozenset()`，以 K1（`store.decision_key`）為鍵。`written`、`logged` 零 diff。
   - 這不違反釐清六 E-25 第 3 點：該點禁止的是「為了改用 id 比對而改 `EvaluationCommit`」；本欄位是本補充授權的加法欄位，W-B6／ENTRY 的比對仍是 K1。
5. **不屬 R-4 的判定：**
   - R-4 管的是 `read_in_flight` 之外的在途讀取。本讀取只讀當日 logged 列、`settled = 1` 的列、批次列是否存在，以及 floor，不讀任何 `settled = 0` 的列或在途狀態，因此不是在途讀取。
   - 判定成立的條件，違反任一條即視為 R-4：
     - (a) 不加入任何 `settled = 0`、`status = 'pending'` 的條件；
     - (b) 結果只經 `EvaluationCommit.settled_since_keys` → `PlaybookEvaluation.line_facts.settled_since_keys` → `_lines`，只用於 `share_notes` 的 N-188 項目與 `entry_before_exit_note(settled_since=...)`；不得被 `same_day_warnings`、N-171／N-168／N-182 的任何在途清單、W-B6／W-B6b、ENTRY／A 的排除、任何 warnings 引用；
     - (c) 每次 `commit_evaluation` 恰好呼叫一次。
   - 與釐清一 E-2 第 3 點（VETO「鎖內重讀 blocked」）不同：blocked 是在途資料，本讀取不是。
6. **QB-7 白名單擴充：** grep 範圍增加 `settled_after_id`、`BOOK_MOVING_SETTLEMENT_SQL`、`STATE_SETTLED_AFTER_ID_FLOOR`、`_read_settled_since(`。`app/` 內只准出現在下列位置：
   - `_SCHEMA`、`_MIGRATIONS`；
   - `_init_schema`（floor）；
   - `claim_directive` 的 UPDATE；
   - 常數定義處；
   - `_read_settled_since` 本體；
   - `commit_evaluation` 內的唯一一次呼叫。
   出現第二個讀取點即 BLOCKING。釐清三對 `pending_directives(` 的兩處白名單不變。

## X-3 漏報只限兩種已知殘留（風控第二節之 1 (a)）
1. 前提（讀碼）：在非並發情況下，帳冊股數只會由 `settle` 改變。其他 `save_batch` 呼叫只更新 peak、defer、missed、status、trailing。`apply_effects` 跳過 `FILL_DEPENDENT_EFFECTS`。這個前提由 N188-T15 的 AST 守門釘住。
2. 因此述詞是「本列產生之後帳冊股數變動」的必要條件，只會有以下兩種漏報：
   - **(a-1) 並發窗口（F2／N-169 類）：**
     - 另一個請求的 claim 落在「寫下 L 的那個請求讀 `book`（`list_batches()`）之後、L 插入之前」。這時 claim 的水位小於 L.id，所以不觸發，但 L 的股數是依動帳前的帳冊算的。
     - claim 和 settle 分屬兩個 transaction 時，「claim 在讀帳前、settle 在讀帳後」也屬這一類。
     - 另一個請求以舊值整列覆寫批次（`save_batch` 的 INSERT OR REPLACE 讀改寫競態）也屬這一類。
     - **這類漏報不會在之後的重新整理中自行修正**，因為 L.id 與水位的關係固定不變。
     - 必須寫進 `_read_settled_since` 與 `commit_evaluation` 的 docstring。
   - **(a-2) N-177 落地前 S2 不動帳（F8）：**
     - 已判定成交的 S2 列（`batch_no` 為 NULL）不會動帳，所以不在述詞內。使用者的實際持股可能已經改變，但同一 symbol 的其他列不會觸發。
     - N-177 落地時，必須在同一個 PR 內完成以下三件：
       - 改 `BOOK_MOVING_SETTLEMENT_SQL`，納入 S2 的動帳條件；
       - 改 X-2 第 2 點的範圍：S2 動帳時，同一 symbol 的逐批列也要觸發；
       - 改 N188-T9，並送風控回審 `SETTLED_SINCE_*` 字面與 W-B2LS 的 P（風控 N-189 裁示第二節之 3 (b)）。
     - 絆線：N188-T9 把「S2 已判定成交 ⇔ 不呼叫 `set_cash` ⇔ 述詞為假」釘死。N-177 一改 `settle`，T9 就會轉紅。
     - 若 N-177 先於 N-188 合進 product，N-188 直接以 N-177 之後的 `settle` 為準實作上述擴充，(a-2) 就不存在；QB-18.5 的對照以 N-188 分支起點的 `settle` 為準。
3. 除這兩種之外，不得有其他漏報。新發現的漏報路徑一律 PR 停住，送 tech-architect 與風控。
4. 已知多報，往觸發的方向，可接受：
   - N2（判定成交但沒動帳，例如批次已無股數）；
   - 批次列在結算後才建立；
   - legacy 列，見 X-4 第 3 點。

## X-4 先後判定的精度與依據（風控第二節之 1 (b)）
1. **查證（讀碼）：**
   - `created_at`：`commit_evaluation` 在 `BEGIN IMMEDIATE` **之前**取 `moment = datetime.now(UTC).isoformat()`（`store.py:1201`、`:1203`）；同一次 commit 的所有列共用這個值。
   - `settled_at`：`claim_directive` 把 `datetime.now(UTC).isoformat()` 當成 UPDATE 的參數，值在語句取得寫鎖之前就算好了（`:1372`）。
   - 精度是微秒，但 `isoformat()` 在 microsecond 為 0 時會省略小數部分，所以字串長度不固定。SQLite 以 TEXT 字典序比較，碰巧排序正確，但很脆弱。
   - 時鐘來源是系統牆鐘（非單調，NTP 或手動校時都可能讓它倒退），沒有可注入的時鐘。backend 與 scheduler 是兩個 process，共用同一個 DB。
   - 兩個值都在鎖外取得，所以時間戳的先後不等於 commit 的先後。
   - **結論：無法嚴格判定，不採用時間戳。**
2. **方案比較：**
   | 方案 | 內容 | 判定 |
   |---|---|---|
   | O-1 | `settled_at > created_at` | 牆鐘倒退或同一微秒時會誤判；鎖外取值，先後不等於 commit 順序。不採 |
   | O-2 | `>=`，加上排除本次寫入列 | 能排除自我觸發，但牆鐘倒退時會漏報，不在 X-3 的兩種之內。不採 |
   | **O-3** | claim 時寫入 id 水位 `settled_after_id` | 不依賴時鐘，嚴格判定。代價是一個 migration 欄位，加上 claim UPDATE 多寫一欄。**採用** |
   | O-4 | 專用單調計數器，加上評估讀帳時的水位隨列存檔 | 可以把 (a-1) 收窄到 claim／settle 分裂的部分，但要改 `commit_evaluation` 的輸入與指令列欄位，侵入面大。並發屬 N-169，本案不採 |
3. **O-3 規格：**
   - 新欄位 `playbook_directives.settled_after_id INTEGER`，可為 NULL，同時加進 `_SCHEMA` 與 `_MIGRATIONS`。
   - `claim_directive` 的 UPDATE 加一個 SET：`settled_after_id = (SELECT MAX(id) FROM playbook_directives)`。WHERE、G1 條件、其他參數與回傳值零 diff。
   - 嚴格性的依據：
     - SQLite 寫者序列化，UPDATE 在語句開頭就取得寫鎖，讀到的是最新提交的狀態；
     - id 是 AUTOINCREMENT，不重用，也從不 DELETE。
     - 由此：L 在 claim 之前提交 ⇒ 水位 ≥ L.id；L 在 claim 之後提交 ⇒ L.id > 水位。
   - 同一請求「先結算、再寫入」：本次 claim 的水位 < 之後插入的 L.id ⇒ 不觸發。
   - 較早寫入的 L 遇上本次結算 ⇒ 觸發。
   - **floor：** `STATE_SETTLED_AFTER_ID_FLOOR`。在 `_init_schema` 內、`add_missing_columns` 之後，每次啟動以「取既有值與目前 `COALESCE(MAX(id),0)` 的較大者」寫入（只增不減）。
     - 這保證每一個 NULL 戳記的 claim 都早於 floor。
     - 若有舊版 process 在 N-188 的 schema 下並行 claim，這項保證就不成立。因此**部署條件**是：不得同時有舊版與新版 backend 處理請求，由 devops-sre 確認 compose 的換版方式。
     - 回滾到舊版、再重新部署時，由「只增不減」的 floor 吸收，不需要人工改 DB。
   - **禁止：** 回填 legacy 列的 `settled_after_id`（違反 N172-C11 與 Decision 9 的 VETO）；以任何方式改寫 floor 以外的既有列。
4. **代價（多報，往觸發的方向）：** L.id ≤ floor 的 logged 列，只要同範圍內有 NULL 戳記的動帳列就會觸發。這限於「backend 重啟前已寫入、且屬於當日預定執行日」的列，到下一個預定執行日就消失。
5. 與 Decision 6／N172-C8：本條不新增 `DirectiveStatus`、不做批次層級 claim、`settle()` 零 diff，claim 會鎖定哪些列與 rowcount 都不變。「claim_directive 只允許 G1」判定為 N-172a 的範圍約束（比照補充四 S-2.4 對 `settle_pending` 的判定）。CEO 可推翻。

## X-5 資料流與 `LineFacts`
1. `models.py`：
   - 新增型別別名 `DecisionKey = tuple[str, int | None, str, str, str]`；
   - 新增 frozen 的 `LineFacts`（比照 `LabeledBatch`），欄位 `settled_since_keys: frozenset[DecisionKey] = frozenset()`，擁有者 N-188；
   - `PlaybookEvaluation` 新增 `line_facts: LineFacts = LineFacts()`。
   - engine 零 diff，靠預設值兼容。
2. `evaluate_today` 在 authored 路徑的 `model_copy(update=...)` 中，寫入 `line_facts=LineFacts(settled_since_keys=commit.settled_since_keys)`。unauthored 路徑維持預設值，即空集合。
3. `LineFacts` 的加法擴充規則，列為新的 S-3 固定項：
   - 只能新增有空預設值的欄位，每個欄位要註明擁有者與 ADR 條號；
   - 既有欄位不得改名、改型別、移除；
   - N-189(D1)／(D2) 依各自的補充新增欄位，**不構成 R-3**。

## X-6 `_lines` 簽名（R-3）與同列欄位
1. **S-3 固定項第 4 項修訂為：**
   `_lines(directives: Sequence[Directive], *, labeled_batches: Sequence[LabeledBatch], line_facts: LineFacts) -> list[DirectiveLine]`
   - 兩個參數都是 keyword-only、必填、無預設值；
   - `_lines` 仍是唯一的 `DirectiveLine(` 建構點（SEAM-T5）；
   - 這是最後一次為同列揭露改簽名，之後的需求一律走 X-5 第 3 點。
2. **`DirectiveLine` 新增 `share_notes: list[str]`，預設為空清單。**
   - 這是「本列股數」相關揭露的有序清單，只由 `_lines` 填入，不得拼進 `line`，也不得併入 `entry_before_exit_note`（風控第二節之 2）。
   - 採空清單而不用 null：同一列可能有 0～3 句，空清單是唯一的「無」狀態。
3. **槽位與順序（風控 N-189 裁示第二節之 2）：**
   - 由 `service.share_notes(directive, facts, *, settled_since) -> list[str]` 依程式順序組成，順序只在這個函式內定義：
     - 第 1 槽：N-188，即 `service.settled_since_note`；
     - 第 2 槽：保留給 N-189(D1)；
     - 第 3 槽：保留給 N-189(D2)；
     - 值為 None 的槽不放入清單。
   - N-189 只能在第 2、3 槽填入，不得重排第 1 槽。
4. `_lines` 對每一列：
   - 先算 `flag = service.settled_since(directive, line_facts)`，以 `store.decision_key` 判定是否屬於 `settled_since_keys`，不得另寫 K1；
   - 同一個 `flag` 傳給 `service.share_notes(..., settled_since=flag)` 與 `service.entry_before_exit_note(..., settled_since=flag)`；
   - 每列只算一次。
5. `service.settled_since_note(directive, *, settled_since) -> str | None`：
   - `settled_since` 為真、且列屬於 X-1 範圍時：S2 回傳 `wording.SETTLED_SINCE_SYMBOL_NOTE`，逐批列回傳 `wording.SETTLED_SINCE_BATCH_NOTE`；
   - 其餘回傳 None。
   - 兩個常數是不含佔位符的靜態字串。定稿若需要佔位符，PR 停住送 tech-architect；不得含任何股數。
   - 若字面需要由多個常數組成，常數一律以 `SETTLED_SINCE_` 開頭，只在本函式內組合。
6. **各呼叫點：**
   | 呼叫點 | `line_facts` | `share_notes` |
   |---|---|---|
   | `/today` 的 `directives` | `evaluation.line_facts` | 只有 X-1 範圍內的列可能非空 |
   | `/today` 的三個在途清單 | `LineFacts()` | 恆為 `[]`（buy、EMERGENCY，不適用） |
   | `_pending_exit_block`（N-171） | `LineFacts()` | `DirectiveLine` 上恆為 `[]`；`PendingExitRowResponse` 與群組 B **不新增也不複製**這個欄位（不適用） |
   | 出清回應的 `directives`、`pending_directives` | `LineFacts()` | 恆為 `[]` |
   | rebalance | `LineFacts()` | 恆為 `[]` |
   - 本補充明文授權：N-188 可以在 N-171 擁有的 `_pending_exit_block` 內，對 `_lines` 的那一次呼叫補上 `line_facts=LineFacts()`，只限這一處、這一個引數（比照釐清一 E-1 第 5 點）。
   - N-171-B1／B2 等之後新增的呼叫點也照表傳入，誰後合就由誰補上，不構成 R-5。
7. **`types.ts`：**
   - `PlaybookDirectiveLine` 加 `share_notes?: string[]`，宣告為 optional，缺鍵一律視為 `[]`；
   - 註解寫明擁有者（N-188 第 1 槽，N-189 第 2、3 槽）與本條號；
   - 補充四 2.2(d) 的既有宣告零 diff。
8. **R-3 的處理：**
   - N-171-A 已合進 product（`a320f5d`），「N-171-A 先合」在實質上已經滿足（比照 E-29 第 3 點）。
   - N-168 合併後 N-188 才開分支（X-10），沒有並行的一方在改固定項。
   - SEAM-T5 的不變式測試 `test_t5_labeled_batches_is_keyword_only_and_required` 零 diff。
   - N-168 改過的 `test_t5_the_line_is_never_touched...`，以及其他測試對 `_lines` 的呼叫，只補 `line_facts=LineFacts()`，屬 E-4 第 3 點的裝置變更，斷言零改動，並在 PR 說明列出。

## X-7 渲染條件與順序（風控第二節之 4；修訂補充四釐清七 E-30 第 3、4 點）
1. **E-30 第 3、4 點改為：**
   - 依風控 E-30 裁示第 2 點過濾後，沒有任何項目時回傳 None；
   - P 成立，**而且** `settled_since` 為假：渲染 W-B2LS；`shares` 大於項目合計時再接 W-B2LSr；
   - 其他情況（P 不成立，或 `settled_since` 為真）：渲染 W-B2LSf，後面絕不接 W-B2LSr；
   - 不 raise，不用 `assert`。
   - `entry_before_exit_note` 新增 keyword-only、必填的 `settled_since: bool`（N-168 擁有的簽名，依本補充擴充）；`_labeled_snapshot` 傳 `False`。逐批列（W-B2L）不受 `settled_since` 影響。
2. **S2 列允許的組合：**
   - N-188 note ＋ W-B2LSf；
   - 只有 W-B2LS（可接 W-B2LSr）；
   - 只有 W-B2LSf；
   - 只有 N-188 note；
   - 兩者皆無。
   **禁止：** N-188 note 與 W-B2LS 或 W-B2LSr 同時出現。
3. 逐批的 S/P 列：N-188 note 可以和 W-B2L 並存。
4. **順序（所有列一致）：** `line` → `share_notes`（N-188 → D1 → D2）→ `entry_before_exit_note`（W-B2L／W-B2LS／W-B2LSf，＋W-B2LSr）。
   - 前端渲染 `/today` `directives` 的元件依這個順序同列顯示，不摺疊、不用 tooltip、不縮寫、不截斷；
   - 排版容不下時回審風控，不得自行處理。
5. E-30 第 6 點的殘留（股數剛好抵銷）收窄到只剩 X-3 (a-1)。風控 E-30 裁示第二節之 3 (b) 的釘住測試，期望值由 W-B2LS 改為 W-B2LSf，並且 `share_notes` 含 N-188 note。這是本補充授權的 W-B2LS 回審改動，不視為違反 N-168 測試的保護。
6. 本補充同時符合 W-B2LS 的兩個回審觸發：「新增結算時點的戳記」，以及風控修訂後的 E-30 第 6 點 (c)。回審就在 N-188 的同一個 PR 內完成。
7. **同包上線：**
   - 第 1 點的條件修訂，與 `share_notes` 的後端產生，放在**同一個 commit**；
   - 後端、`wording.py`、前端元件、測試放在**同一個 PR**；
   - PR 以 merge commit 合進 product，不 squash，不 cherry-pick 個別 commit 進 product 或任何部署分支（比照 E-14 第 2 點 (d)）；
   - 風控逐字定稿與 qa-e2e 驗收完成前，不得合併，也不得部署。

## X-8 SEAM／golden
1. 新增 `approved/n188.json`：
   - `owner`：N-188；
   - `added_keys`：`[{"key": "share_notes", "source": "ADR-0035 補充五 X-6 第 2 點"}]`（名稱不得出現在 golden 的任何深度）；
   - `filled`：空；
   - `deltas`：預測為空。
2. 預測依據：golden 的 9 個回應中，沒有「稍早寫入、之後才有動帳」的 S/P 列。`after_exit.today_next_day` 的結算發生在同一請求的寫入之前，依 X-4 不觸發。golden 中也沒有帶標示的 S2 列（E-24 第 3 點 (b)），所以 X-7 預期零差異。
3. **補位測試（BLOCKING）：** T2 不比對刪除鍵，所以以 `golden_bodies` 新增一條測試，斷言 9 個回應中每一個 `DirectiveLine` 的 `share_notes == []`。實測不成立時停住，送 tech-architect，不得登記差異來解決。N-189 只能把這條斷言改成自己補充核准的期望值。
4. golden 零 diff，`GOLDEN_SHA256` 不改；`n168.json`、`n171a.json` 零 diff。出現任何差異時，依 E-7 第 3 點停住。
5. `settled_after_id` 不進任何 API 回應（`directive_log` 只有測試在用）。

## X-9 測試（BLOCKING）
- N188-T1：無標示的 S2，同一預定執行日評估兩次，兩次之間讓後補 bar 成交一筆同 symbol 的單。走兩條路：第二次 `/today` 的自身結算，以及 `POST /settle`。斷言 S2 列的 `share_notes == [SETTLED_SINCE_SYMBOL_NOTE]`，其餘列為 `[]`。
- N188-T2：逐批 S1，同批較早的一筆賣單晚結算。斷言 `[SETTLED_SINCE_BATCH_NOTE]`；其他批次的列為 `[]`。
- N188-T3：兩次評估之間沒有結算時不觸發；連續三次重新整理，回應相同。
- N188-T4：MISSED，以及 G1 拒絕的列，不觸發。
- N188-T5：N2（判定成交但批次已無股數）會觸發，內容逐字等於常數。
- N188-T6：自我觸發排除。本次自身結算讓買單成交，之後本次才寫入的 S/P 列為 `[]`。對照組：同一次結算遇上較早寫入的列，會觸發。
- N188-T7：時鐘無關。把 store 的 `datetime.now` 換成固定值，以及會倒退的序列，T1、T6 的結果不變。
- N188-T8：legacy 與 floor。L.id > floor 時，NULL 戳記的動帳列不觸發；L.id ≤ floor 時觸發；floor 鍵缺失時觸發。重複呼叫 `_init_schema`、或多個 process 同時呼叫，floor 只增不減。
- N188-T9：述詞與 `settle` 等價（以 `set_cash` spy 觀察），矩陣為 status ∈ {executed, missed}、action ∈ {buy, sell}、batch_no ∈ {NULL, 存在, 不存在}。其中「S2 executed ⇒ 述詞為假」是 N-177 的絆線。
- N188-T10：`claim_directive` 寫入 `settled_after_id == claim 當下的 MAX(id)`；N172-T20、T21 與 G1 的既有測試零 diff。
- N188-T11：X-7 的組合。
  - 單元測試涵蓋 (P, settled_since, 有無項目) 的全部組合；
  - property test 斷言輸出只會落在 X-7 第 2 點允許的組合內；
  - 「剛好抵銷」案例依 X-7 第 5 點；
  - E-30 第 5 點 (b) 的整合測試另外斷言 `share_notes` 帶有 N-188 note。
- N188-T12：X-6 第 6 點的各呼叫點，`share_notes` 都是 `[]`；`PendingExitRowResponse` 沒有這個鍵。
- N188-T13：X-8 第 3 點的 golden 補位測試。
- N188-T14：前端。
  - 同列的渲染順序是 `line` → `share_notes`（依清單順序）→ `entry_before_exit_note`；
  - 不摺疊，沒有 tooltip；
  - 缺 `share_notes` 鍵的舊 fixture 能正常渲染（比照 SEAM-T8）。
  - UI 加 qa-e2e 實機驗收。
- N188-T15：AST 守門。`app/` 內對 `shares`／`remaining_shares` 的 `model_copy(update=...)` 只出現在 `settle`；`set_cash(` 只出現在 `settle`。
- N188-T16：R-4 守門。
  - 以 `set_trace_callback` 證明 `_read_settled_since` 只執行 SELECT，每次 `commit_evaluation` 呼叫一次，且在 logged 列讀取之後；
  - SEAM-T3、T4 仍然綠燈。
- N188-T17：N-188 的字面整檔掃描與禁用詞測試（「需」「應」「建議」「務必」「盡快」「否則」「安全」「已取消」「已撤單」「你已買進」各 0 次；含「本系統不下單」）。轉紅時依 E-20 第 7 點處理。

## X-10 時序與固定項基準
1. N-168 目前在 `feat/stock-desk-exit-pending-r-buys`（head `5d6056c`）實作中，照現有裁示合併，不得含任何 N-188 行為。
2. N-188 要等 N-168 以 merge commit 合進 product（以下記為 `<M168>`）之後，才從 `origin/product/stock-desk` 開分支，建議名稱 `feat/stock-desk-n188-settled-since-note`。設計與字面擬稿現在就可以並行。
3. **固定項基準 = `<M168>` 上的 S-3 固定項。** 也就是 `5c2d3e1` 的固定項，加上 E-29 修訂的 `LabeledBatch`（含 `remaining_shares`、`symbol_open_shares`）。QB-6 以 `git diff <M168> <head>` 判定，除下列項目外零 diff：
   - X-6 第 1 點的 `_lines` 簽名；
   - X-5 的 `LineFacts`。
   N-168 擁有項以 `<M168>` 的版本為準，本補充只授權 X-7 第 1 點與 X-7 第 5 點這兩處改動。
4. **N-177 的先後（風控 N-189 裁示第二節之 3：N-177 排在 N-188 之前）：**
   - 若 N-177 先合，X-2 依 X-3 第 2 點 (a-2) 末段，以 N-177 之後的 `settle` 為準；
   - 若 N-177 後合，由 N-177 的 PR 負責同步述詞、N188-T9 與字面回審，否則 N-177 不得合併。
5. 不 rebase。後合的一方依 S-5 第 3 點 merge 最新 product，並在 merge 之後的 head 重跑全部 CI。
6. **上線耦合（風控 N-189 裁示第二節之 4）：** N-190 的修正不得早於 N-188 揭露、W-B2LS 回審與 N-189(D1) 揭露上線；同時上線可以。
7. 若 N-168 被 revert，或改為不合併，N-188 停住，由 tech-architect 重定基準。

## X-11 QB-18（N-188 的 PR；qa-reviewer 含 Codex，全部 BLOCKING）
- QB-18.1：`engine.py` 零 diff（C-B11、N172-C3）。
- QB-18.2：沒有對指令列 DELETE；`playbook_directives` 上新增的寫入只有 `claim_directive` 那一個 SET；沒有回填；`_insert_directives`、`_new_decisions`、`_is_logged` 零 diff；不在既有 K1 下另寫新列（Decision 1、N172-C11）。
- QB-18.3：`/today` 的 `directives` 仍等於 `commit.logged`；`_read_logged` 的既有測試零 diff；service 不重算任何供顯示的股數；`SETTLED_SINCE_*` 不含任何佔位符（Decision 4、N172-C6）。
- QB-18.4：觸發只來自 `line_facts.settled_since_keys`；`service.settled_since`、`settled_since_note`、`share_notes` 不讀 warnings、`line` 或任何字串（題 12 allowlist）。
- QB-18.5：X-2 全部條件。
  - `BOOK_MOVING_SETTLEMENT_SQL` 緊接在 `settle` 之前，是唯一定義；`'executed'` 的 SQL 字面只出現在這個常數裡；
  - `settle` 零 diff；
  - N188-T9 綠燈；
  - X-2 第 3 點的讀取點與唯一一次呼叫；
  - X-2 第 5 點 (a)～(c)；
  - X-2 第 6 點的 QB-7 白名單，第三處即 BLOCKING。
- QB-18.6：store 不 import wording（N172-C7）；`SETTLED_SINCE_*` 只在 `wording.py`，屬性引用只在 `service.settled_since_note`（AST 口徑比照 E-26 第 4 點）；風控逐字核可檔在合併前已存在，並以程式比對原文。
- QB-18.7：X-10 第 3 點的固定項基準；`LineFacts` 符合 X-5 第 3 點；`DirectiveLine(` 只在 `_lines` 內；SEAM 的不變式斷言零 diff，裝置變更逐條列在 PR 說明。
- QB-18.8：N188-T1～T17 存在且綠燈；X-3 (a-1) 的 docstring 存在，並寫明「不自癒」。
- QB-18.9：X-7 全部條件。
  - W-B2LS 只在「P 成立且 `settled_since` 為假」時渲染；
  - 禁止的組合不會出現；
  - 第 1 點的修訂與 `share_notes` 的後端產生在同一個 commit；
  - 後端、前端、字面在同一個 PR，以 merge commit 合併；
  - qa-e2e 已實機驗收。
- QB-18.10：X-8 全部條件（含 QB-12 的既有口徑）。
- QB-18.11：X-10 第 2～6 點：分支起點、merge 後的 head 上 CI 全綠、N-177 與 N-190 的耦合。
- QB-18.12：`_pending_exit_block` 的 diff 只有 X-6 第 6 點授權的那一個引數；`PendingExitRowResponse` 零 diff。

## X-12 後果
- 好處：
  - 使用者照著下單的那一行，在帳冊有動帳證據時帶有揭露，超賣與少賣兩個方向都涵蓋；
  - W-B2LS 的「剛好抵銷」殘留收窄到只剩並發；
  - N-189 不必再走一次 R-3。
- 代價：
  - 新增一個 migration 欄位與一個 state 鍵；
  - claim UPDATE 多寫一欄；
  - 每次 backend 重啟後，重啟前已寫入的當日 S/P 列可能多報（X-4 第 4 點）；
  - N2 多報；
  - (a-1) 並發漏報不會自行修正；
  - N-177 之前有 (a-2)。
- 被約束：
  - 不得以時間戳判定先後；
  - 不得回填 `settled_after_id`；
  - 不得在 `read_in_flight` 或鎖外另讀動帳；
  - 不得把重算的股數放進句子或任何一列。
- 交 tech-writer：
  - 把 X-3 的殘留與 X-4 第 4 點的多報，以補充方式寫進 ADR-0035 的 Consequences，不得原地改寫；
  - 一併記錄 E-30 第 6 點的殘留收窄（風控 E-30 裁示第二節之 3 (a)）。

## X-13 附帶判定：N168-D5 的 `after` 更新（N-168 分支 `9de6f9f`）
1. 可以接受。依據是釐清二 E-7 第 2 點與 E-8，不是 E-20（E-20 第 5 點明文 golden 不適用）。
   - D5 屬於 E-8 預先核准的類別：W-B3 以 insert 插在 `after_exit.today_next_day.settlement.warnings[1]`。
   - `after` 本來就要求「完整的最終值」逐字等於定稿。風控修訂 W-B3 之後，把 `after` 換成新定稿是同一筆差異的取值更新，不是新的差異。
   - E-24 第 2 點的「`n168.json` 不改」只針對 snapshot 的三個刪除鍵，不涵蓋 D5。
2. 條件（BLOCKING，併入 QB-12／QB-16）：
   - (a) D5 的 `id`、`scenario`、`body`、`path`、`op`、`approval` 零 diff，只改 `after` 與 `source`；D1～D4 零 diff；`deltas` 恰好是 D1～D5。
   - (b) `after` 等於風控修訂版 W-B3 以該情境的值渲染的結果，由 qa 手算核對；`source` 指向定稿 W-B3 修訂版的風控檔。
   - (c) `after` 的改動與 `wording.py` 中 W-B3 常數的改動在同一個 commit（`9de6f9f` 已符合）；PR 說明列出「T2 在改 `after` 之前為紅、差異只在 D5，改之後轉綠」。
   - (d) 合併前，W-B3 修訂版要在風控的逐字核可範圍內。

---
（coordinator 2026-11-04 落檔：tech-architect 回報 code block 逐字轉存。）

## X-14 補註：對 `test_the_exit_adds_no_column_table_or_state_key` 的連動（2026-11-04）
1. X-4 新增的 `settled_after_id` 欄位與 `STATE_SETTLED_AFTER_ID_FLOOR`，會讓這支測試的欄位串列、`after <= PRE_N166_STATE_KEYS`、`declared == PRE_N166_STATE_KEYS` 三條斷言轉紅。這些新增與 ADR-0033 C-9 無關：C-9 管的是出清路徑不儲存 mode_reason 與旗標；本補充的欄位與鍵不由出清寫入。
2. 准改範圍：比照 N-168 的 `ADR0034_COLUMNS`，新增具名常數，內容為：`playbook_directives` 末尾多 `settled_after_id`，state key 多 floor 鍵。三條斷言的期望值改為「既有期望 ∪ 本常數」，仍用精確相等；`PRE_N166_*` 與其他斷言零 diff。放在 N-188 PR 的單獨一個 `test:` commit，PR 說明列出。
3. 併入 QB-18.7 檢查。

（X-14 由 coordinator 2026-11-05 附加，原文見 `work/reviews/2026-11-05-N168之I8追認與補充五X14-tech-architect.md`。）


---

# ADR-0035 補充五 修正一：X-4 legacy 戳記、S2 納入觸發、與 ADR-0040 (乙) 的交互（N-188）

- 日期：2026-11-05
- 決策者：tech-architect（規格）。依據：
  - 風控 `work/reviews/2026-11-05-N168視覺規範R1R3與補充五及N188定稿-風控.md` B-(c) VETO、B-(d) required；
  - 風控 `work/reviews/2026-11-05-N177修復與N190字面裁示-風控.md` A-1、A-3、A-4、B-5；
  - `work/reviews/2026-11-05-N177修正範圍評估-tech-architect.md` 第 3 節；
  - CEO #108。
- 性質：修正補充五，不另立 ADR。本修正取代補充五的下列條文：
  - X-2 第 1 點的 `#:` 註解要求、第 2 點、第 5 點的讀取清單、第 6 點；
  - X-3 全部；
  - X-4 第 3 點的 floor 段與部署條件、第 4 點；
  - X-9 的 N188-T8、T9、T15；
  - X-10 第 4、6 點；
  - X-11 的 QB-18.2、.5、.8、.11；
  - X-12 的對應項；
  - X-14 第 2 點。
  未列出的條文不變。
- 狀態：風控確認本修正之前，補充五（含本修正）與風控 C 節的定稿常數都不得合併、不得部署。
- 程式位置：2026-11-05 本 checkout 的 `apps/stock-desk/backend/app/`。全部是讀碼判定，未執行。

## M1-1 X-4 修正：拿掉 floor，NULL 戳記以列本身的 id 當水位下界

1. 讀碼確認風控 B-(c) 的推論成立：
   - `PlaybookStore()` 由 `api/deps.py:311-319` 的 `lru_cache` 在每個 process 建一次，`__init__` 會呼叫 `_init_schema`（`store.py:664-668`）。所以 floor 每次 backend 啟動都會升高；dev 的 `uvicorn --reload` 每次改檔也會升一次。
   - legacy 列的戳記永遠是 NULL，`COALESCE(NULL, :floor) >= L.id` 對重啟前寫入的 L 恆為真。述詞含 buy，所以凡是曾經有買進成交的 symbol，當日的 S/P 列在重啟後全部觸發，而觸發來源的 claim 可能早於 L 好幾天。第一句因此不為真。
   - 另外發現一處：風控方向參考的計數「`settled = 1 AND settled_after_id IS NULL` 的列數」，照字面會算進非下單列。`_insert_directives` 對順延、跳過、無動作的列以 `settled = 1` 直接寫入（`store.py:584`），新版也不寫戳記，所以每次評估計數都會增加，floor 幾乎每次重啟還是會再升。若要用計數，必須限定 `action IN ORDER_ACTIONS`。
2. 方案比較：
   | 方案 | 內容 | 優點 | 缺點、風險 | 判定 |
   |---|---|---|---|---|
   | F-1 計數門檻 | 記錄 NULL 戳記的下單列數，增加時才升 floor | 沿用 floor，改動小 | 計數沒限定下單列就會失效；部署條件不成立時，失敗方向是不實陳述；多一個 state 鍵；X-14 三條斷言都要改 | 不採 |
   | F-2 NULL 一律不觸發 | 移除 COALESCE | 永遠不會不實 | 漏報比 F-3 多：連 s.id ≥ L.id 這種可以確定為真的情況也丟掉 | 被 F-3 支配，不採 |
   | **F-3 以 s.id 當水位下界** | `COALESCE(s.settled_after_id, s.id) >= L.id` | 依構造為真；沒有 floor、沒有 state 鍵；重啟對判定零影響；部署條件不成立時只會漏報 | 新增 (a-3)，要靠部署條件歸零 | **採用** |
   | F-4 legacy 變體句 | NULL 觸發時改出一句不講先後的句子 | 不漏報 | 要新字面，風控多審一輪；若仍是每次重啟升 floor，大量列同時出現，習慣性忽略的問題還在 | 不採 |
   | F-5 NULL 列改用時間戳 | `settled_at > created_at` | 舊列也能判 | X-4 第 1 點已判定不嚴格，牆鐘倒退時第一句可能為假 | 不採 |
3. 決策（O-3′）：
   - 刪除 `STATE_SETTLED_AFTER_ID_FLOOR`、`_init_schema` 內的 floor 寫入，以及 `:floor` 參數。對 N-188 而言，`_init_schema` 只多 `_MIGRATIONS` 的一個欄位，沒有其他 diff。
   - X-2 第 2 點的水位條件逐字改為 `COALESCE(s.settled_after_id, s.id) >= L.id`。
   - 嚴格性依據：
     - claim 以 `WHERE id = ?` 更新、rowcount 為 1，表示該列在 claim 當下已存在，所以 claim 當下的 MAX(id) ≥ s.id。
     - 因此 s.id ≥ L.id ⇒ 真實水位 ≥ L.id ⇒ claim 晚於 L 提交。
     - NULL 戳記列只會往「不觸發」偏，不會讓第一句不實。
     - 有戳記的列，判定與 O-3 相同。
   - 重啟、`_init_schema` 重複呼叫、多個 process 同時啟動，對判定都沒有影響，因為不再有任何啟動時寫入的狀態。
   - 禁止事項維持：不得回填 `settled_after_id`；不得用時間戳判定 NULL 戳記列的先後；不得新增 state 鍵來代替 floor。
4. 代價：新增已知漏報 (a-3)，見 M1-2 第 5 點。X-4 第 4 點（重啟後多報）刪除。
5. **部署條件（devops-sre；取代 X-4 第 3 點的部署條件）：**
   - **適用時機**：只限從「不寫戳記的版本」換成「寫戳記的版本」：
     - (i) N-188 首次部署；
     - (ii) 回滾到不含 N-188 的 build 之後再重新部署。
     N-188 上線之後，凡是部署不含 N-188 的 build（例如從舊 commit 打的 hotfix 或 ADR-0040 build），一律視為回滾。其他部署與重啟都不需要這項條件。
   - **一律要遵守**：不得同時有新、舊版 backend 處理請求（compose 先停再起）。讀碼確認 scheduler 不碰 playbook：`app/` 內只有 `api/` 與 `playbook/` 引用 `PlaybookStore`。
   - **條件 A（預設）**：停服務後、新版啟動前，以唯讀查詢確認下式為 0：
     `SELECT COUNT(*) FROM playbook_directives WHERE action = 'sell' AND rule_id IN ('S1','S2','P1','P2','P3') AND settled = 0`
     - 依據：`/today` 會顯示的 X-1 列一定還沒結算。L 的預定執行日 E = next_trading_day(data_date)（engine.py:1122）。要結算 L，必須有 L.symbol 在 E 的 bar；data_date 取各序列最新的 bar 日（service.py:1587），所以一旦有了 E 的 bar，data_date ≥ E，頁面就改顯示下一個預定執行日。前提是之後的載入不讓資料日倒退。
     - 所以這個查詢涵蓋部署後所有可能被顯示的 L，而且不必實作交易日曆。
     - 條件 A 成立時，部署後被顯示的 L 都是部署後才寫入，L.id 大於任何舊版 claim 的真實水位，(a-3) 為零。
   - **條件 B（A 不成立時的替代，要風控確認可以用）**：
     - 確認沒有任何舊版 claim 晚於現存未結算的 S/P 賣單，也就是下式為 0：
       `settled = 1 AND settled_after_id IS NULL AND action IN ('buy','sell') AND settled_at >= (上述未結算 S/P 賣單的 MIN(created_at) 往前推 10 分鐘)`
     - 這是運維探針，時間戳只用來判斷部署時機，不進產品判定。時鐘誤差的後果只是 (a-3) 漏報，不會產生不實陳述。
   - **A、B 都不成立**：延後部署，等條件 A 成立；或送風控逐案審。
   - **探針**：比照 `scripts/n172_duplicate_probe.py`：唯讀、對複本執行、不 import app、不連網。結果附在 release 紀錄。
   - **離線修復**：N-177 (B) 這類離線工具若在 N-188 上線之後才 apply，會在沒有 claim 的情況下改動帳冊，同樣歸 (a-3)。apply 前也要符合條件 A 或 B。

## M1-2 X-2／X-3 修正：S2「已判定成交」納入觸發（風控 B-(d)）

1. **共用常數，只有一份定義：**
   - `S2_FILL_ENTRY`：N-177a 的進入條件 `status='executed' AND action='sell' AND rule_id='S2' AND batch_no IS NULL`（N177-C4）。
     - 以一個常數定義。`settle` 的 S2 分支判斷，和 `_read_settled_since` 用的 SQL 片段，都從它導出，不得各寫一份字面。
     - 放在 `BOOK_MOVING_SETTLEMENT_SQL` 旁邊，緊接在 `def settle` 之前。
   - `S2_ELIGIBLE_BATCH_SQL`（別名 `b`）：`b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL`。
     - 這是 N177-C5 的合格批次，與 engine.py:213、:420 同義，由 C5 的 parity property test 綁住。
     - N-177a 的分配查詢與本述詞共用這一份。
   - `<FILL_MOVES>`：N-177a 的 M2 加法表，表名由 dev-lead 定。本述詞只用 `directive_id`、`batch_no`、`shares_moved` 三欄。
   - **定義者**：照計畫 N-177a 先合，三者由 N-177a 定義，N-188 只引用。若 N-188 先合，前兩者由 N-188 定義，N-177a 改為引用。
   - `BOOK_MOVING_SETTLEMENT_SQL` 文字不變：N-177a 不改逐批動帳分支，N-177b 不動帳。它的 `#:` 註解改為：「對應 `settle` 的逐批動帳分支；`settle` 的動帳分支若再修改，必須同步修改本常數與 `S2_FILL_ENTRY`。」
2. **X-2 第 2 點改為（N-177a 已合的版本）：**
   `EXISTS (SELECT 1 FROM playbook_directives AS s WHERE s.symbol = L.symbol AND s.settled = 1 AND COALESCE(s.settled_after_id, s.id) >= L.id AND ((<BOOK_MOVING_SETTLEMENT_SQL> AND (L.batch_no IS NULL OR s.batch_no = L.batch_no)) OR (<S2_FILL_ENTRY 的 SQL> AND (L.batch_no IS NULL OR EXISTS (SELECT 1 FROM <FILL_MOVES> AS m WHERE m.directive_id = s.id AND m.batch_no = L.batch_no AND m.shares_moved > 0) OR (NOT EXISTS (SELECT 1 FROM <FILL_MOVES> AS m WHERE m.directive_id = s.id) AND EXISTS (SELECT 1 FROM playbook_batches AS b WHERE b.symbol = L.symbol AND b.batch_no = L.batch_no AND <S2_ELIGIBLE_BATCH_SQL>))))))`

   各分支：
   - **(A) 逐批動帳**：與補充五相同。
   - **(B1) L 是 S2 列**：同 symbol 有任何一筆 executed S2 被 claim，就觸發。以 claim 為準，不看稽核表（風控 B-(d)1）。
     - 零移動的 S2、claim 之後還沒 settle 就中斷的 S2，都會觸發。這屬於 N2 類多報，第一句「判定了…成交」仍為真。
   - **(B2) L 是逐批列、S2 已結算**：稽核表有這張 S2 在 L.batch_no 移動股數大於 0 的紀錄，才觸發。
     - N-177a 只在合格批次上移動股數，所以這表示 S2 結算時這批屬於合格批次，符合 B-(d)2。
   - **(B3) L 是逐批列、S2 已 claim 但沒有任何稽核紀錄**（claim 後、settle 前中斷）：這批在讀取當下合格，才觸發。
     - 讀取當下合格 ⇒ claim 當時合格。理由（讀碼）：
       - L 是這批的 S/P 賣單，而 engine 只對 open、cost 非 NULL、remaining_shares > 0 的批次發這類單（engine.py:420），所以 L 評估時這批已經是 open；
       - 批次 open 之後不會回到 planned（G1），remaining_shares 只減不增，cost 不再改。
       這個前提由 N188-T19 的 property test 釘住。
     - 所以 (B3) 不會讓「涉及這批」為假。「claim 後當機」也因此不會成為 X-3 之外的新漏報路徑：這是把 B-(d)1 的考量延伸到逐批列。
   - **不觸發的情況**：S2 已結算，但在 L.batch_no 移動 0 股（股數已分配給較舊的批次）。這批的帳冊股數沒有因這張 S2 改變，不屬於 X-3 定義的漏報；B-(d)2 是必要條件，不是充分條件。送風控確認。
   - 只允許 SELECT。讀取點與呼叫次數照 X-2 第 3 點，不變。
3. **X-2 第 5 點（R-4 判定）的讀取清單改為**：
   - 當日 logged 列；
   - `settled = 1` 的列；
   - 批次列的現況（是否存在、status、remaining_shares、cost）；
   - `<FILL_MOVES>`。
   批次現況與稽核表都是已結算的帳冊事實，不是在途資料。(a)～(c) 不變。
4. **與 N-177a 的先後：**
   - **照計畫，N-177a 先合：**
     - N-188 照第 2 點全文實作，以 N-188 分支起點（含 N-177a）的 `settle` 為準，(a-2) 不存在。
     - N-177a 若最後採 M0（不設稽核表），(B2) 無法成立，PR 停住送 TA 與風控。
   - **N-188 先合：**
     - 實作第 2 點去掉稽核表的版本：(B) 改為 `<S2_FILL_ENTRY 的 SQL> AND (L.batch_no IS NULL OR EXISTS (SELECT 1 FROM playbook_batches AS b WHERE b.symbol = L.symbol AND b.batch_no = L.batch_no AND <S2_ELIGIBLE_BATCH_SQL>))`。
     - 這時 S2 不動帳，批次維持 open，(B3) 的論證同樣成立。不得帶著 (a-2) 上線（B-(d)）。
     - 之後 N-177a 的 PR 必須在同一個 PR 內改成第 2 點全文。否則 S2 關閉批次之後，逐批列就失去觸發。同一個 PR 還要改 N188-T9、T18、T19，並送風控確認。沒改，N-177a 不得合併。
   - **不論哪一種先後**，以下都放在 N-188 的 PR 內：
     - W-B2LS 回審；
     - 風控 A-3 的釘住測試（N-177 評估第 3 節第 4 點）；
     - A-4 (b) 的翻轉測試。
5. **X-3 修正：**
   1. **前提改為**：非並發情況下，帳冊股數只由 `settle` 改變，包括 N-177a 的 S2 分支與它的私有 helper。離線修復工具除外，歸 (a-3)。N188-T15 擴充到涵蓋 N-177a 的 SQL 寫入點。
   2. **漏報仍只限兩種，但組成改變：**
      - **(a-1) 並發窗口**：內容不變，仍然「不自癒」。docstring 加寫窗口寬度（風控 B-(b) suggested）：
        - 讀帳點是 `evaluate_today` 在載入序列之後呼叫的 `list_batches()`（service.py:1616）；
        - 窗口到 `commit_evaluation` 的 `BEGIN IMMEDIATE`（:1636）為止；
        - 中間只有本地 DB 讀寫（`portfolio_state`、`symbol_states`、`fast_market_state`、`apply_effects`、`save_fast_market`）和純計算，**不含取資料**；遇到鎖時，最長等到 busy timeout；
        - claim 只在 backend process 裡發生，所以並發來源只有同一個 process 內並行的請求。
      - **(a-2)**：刪除。依第 4 點，兩種先後下都不存在。
      - **(a-3) 部署／離線修復邊界（新增）：**
        - 情況一：不寫戳記的版本做了 claim（NULL 戳記），claim 落在 L 寫入之後，而且被結算那一列的 id 小於 L.id，這時不觸發。
        - 情況二：離線工具在 L 寫入之後改動了帳冊。
        - 只會在 M1-1 第 5 點的時機發生，範圍限於當時仍會被顯示的 L；到下一個預定執行日，這些 L 就不再顯示。
        - 條件 A 成立時為零；只靠條件 B 時，殘留只來自時鐘誤差。
        - 不自癒，理由同 (a-1)。
   3. X-3 第 3 點不變：出現其他漏報路徑，一律 PR 停住。
   4. **已知多報改為下列各項，第一句都為真：**
      - N2；
      - 批次列在結算之後才建立；
      - 零移動的 executed S2 觸發 S2 列；
      - claim 後、settle 前中斷的 S2，觸發 S2 列與 (B3) 的逐批列；
      - S2 列因同 symbol 新批次買進成交而觸發（「也可能少於」那一支為真）。
      legacy 列不再是多報來源。

## M1-3 ADR-0040 (乙) 上線後的影響（依 CEO #108 的條件判斷）

1. (乙) 的範圍（CEO #108）：只改 `is_usable` 與 snapshot／`LoadedSeries` 的欄位；指令列照實記 `cached_stale`；不用 runtime 旗標。
2. 觸發頻率：
   | 項目 | 現況（N-190 預載實測成立、CEO #107） | (乙) 上線後 |
   |---|---|---|
   | X-1 範圍內的 L 數量 | 被預載的持有標的整天都是 `cached_stale`，S/P 不評估，幾乎沒有 L | 回到每天正常評估的數量 |
   | 單一 L 的觸發條件 | — | 不變：L 寫入之後、預定執行日輪替之前，同 symbol 或同批有 claim。實際來源只有兩種：某檔開盤價的 bar 晚到，由之後的請求結算；以及 `POST /settle`。同一個請求內，結算一律在寫入 L 之前（service.py:1572 先於 :1636） |
   | claim 的時點 | 結算不看 `data_status`（service.py:1051-1057 只找預定執行日的開盤價） | 不變，(乙) 不改結算 |
   | `_read_settled_since` 的呼叫次數 | 每次 `/today` 一次 | 不變 |
   - **結論**：N-188 note 出現的總次數，會從接近 0 回到正常水準，因為現在根本沒有 L 可以觸發；但單一 L 被觸發的機率，不因 (乙) 而提高。
   - 「重新評估更常發生」增加的是同一預定執行日內新 K1 的寫入。新寫入的列晚於先前的 claim，依 X-4 不觸發；舊列的判定不受影響。
   - **前提**：N-190 第一包（評估沿用結算那一次的序列）已經上線。若第一包被回退，評估與結算用的序列可能不同，「L 依據的 bar 比結算看得到的 bar 新」會成為 claim 晚於 L 的常見來源，觸發會增加。增加的方向是觸發，字面仍為真。
3. 對 X-3：
   - (a-1)：窗口寬度不變；發生次數與並行請求數成正比，(乙) 不改變請求數。
   - (a-3)：S/P 賣單恢復出現之後，條件 A 比較難成立，會更依賴條件 B。
   - 沒有新的漏報路徑：(乙) 不新增帳冊寫入點，第一點的前提不變，由 T15 守住。
4. 對 X-4：戳記與 (乙) 沒有交互。唯一的交集在部署：N-188 已上線後，若 ADR-0040 的 build 不含 N-188，等同回滾，適用 M1-1 第 5 點。
5. **給 ADR-0040 起草者的約束**（違反任何一條，就回 TA 與風控）：
   - 不得把 `list_batches()`（service.py:1616）移到載入序列之前，也不得在 :1616 到 `commit_evaluation` 之間加入取資料或任何網路 I/O；
   - 不新增任何改動 `playbook_batches` 股數或 cash 的路徑；
   - 不改 `_settle_pending` 取開盤價的方式；
   - N-188 已部署時，ADR-0040 的 build 必須包含 N-188。
6. **X-10 第 6 點改寫：**
   - 原文「N-190 的修正不得早於 N-188」，已被風控 `2026-11-04-N190重裁-風控.md` 第 5 點與 `2026-11-05-N177修復與N190字面裁示-風控.md` B-5 第 2 點取代。
   - 實測已成立，CEO #108 已核可：第一包、第二包 (乙) 都不等第三包。兩包上線到第三包上線之間的殘留，風控已書面接受，期限是第三包緊接在 N-177 之後。
   - 本補充不再設 N-190 的上線耦合。

## M1-4 測試、QB-18、X-12、X-14 的修訂

1. **測試（BLOCKING）：**
   - **N188-T8 改為「legacy 與重啟」：**
     - NULL 戳記、s.id < L.id 的動帳列（buy、逐批 sell、S2 都要測），不論 claim 早晚，都不觸發；
     - NULL 戳記、s.id ≥ L.id 的動帳列會觸發；
     - **VETO 釘住**：舊列 s 早於 L 好幾天、L 今日寫入；重新建 store（呼叫 `_init_schema`）N 次之後打 `/today`，所有列的 `share_notes == []`；
     - `_init_schema` 前後，`playbook_state` 的鍵集合不變。
   - **N188-T9 改為「述詞與 `settle` 等價」：**
     - 矩陣：rule_id ∈ {S1/P, S2, EMERGENCY}、status ∈ {executed, missed}、action、batch_no ∈ {NULL, 存在, 不存在}；
     - 觀察方式改為比對 settle 前後的批次與 cash，不再只靠 `set_cash` spy，因為 N-177a 的 S2 分支在單一交易內寫入；
     - 斷言：(A) ⇔ 逐批動帳；executed S2 ⇔ (B1)；(B2) ⇔ 這批移動股數大於 0；
     - 絆線：batch_no 存在、但批次列不存在 ⇒ 述詞為假、帳冊不變。N-177b 改到這裡時會轉紅。
   - **N188-T18（新）：S2 列。**
     - 較早的 S2 在兩次評估之間被 claim，三種情況都要觸發：已結算且移動股數大於 0、零移動、claim 後未 settle（模擬中斷）；
     - `share_notes == [SETTLED_SINCE_SYMBOL_NOTE]`；
     - W-B2LS 家族不渲染，改出 W-B2LSf 或 None（風控 A-3 BLOCKING）。
   - **N188-T19（新）：逐批列由 S2 觸發。**
     - (B2) 移動股數大於 0：觸發；移動 0 股：不觸發；
     - (B3) 沒有稽核紀錄、批次合格：觸發；沒有稽核紀錄、批次已 closed：不觸發；
     - property test：在任意操作序列下，批次 open 之後不回 planned、remaining_shares 不增、cost 不變；engine 的逐批 S/P 賣單只出現在合格批次上。
   - **N188-T20（新）**：條件 A、B 的探針查詢在 fixture DB 上的結果；探針不 import app。
   - **N188-T15 擴充**：N-177a S2 分支對 `playbook_batches` 的 SQL 寫入，只出現在 `settle` 的私有 helper。
   - 風控 A-4 (b) 的翻轉測試併入 N188-T11。
2. **QB-7 白名單（取代 X-2 第 6 點）：**
   - grep 範圍：`settled_after_id`、`BOOK_MOVING_SETTLEMENT_SQL`、`S2_FILL_ENTRY`、`S2_ELIGIBLE_BATCH_SQL`、`<FILL_MOVES>` 的表名、`_read_settled_since(`。
   - `app/` 內只准出現在：
     - `_SCHEMA`、`_MIGRATIONS`；
     - `claim_directive` 的 UPDATE；
     - 常數定義處；
     - `settle` 與它的私有 helper；
     - `_read_settled_since` 本體；
     - `commit_evaluation` 內唯一的一次呼叫。
   - 刪除 `STATE_SETTLED_AFTER_ID_FLOOR` 與「`_init_schema`（floor）」兩項。
   - 日後 ADR-0039 群組 B 要讀稽核表時，由它的補充擴充白名單。
3. **QB-18 的修訂：**
   - **QB-18.2 追加**：`playbook_state` 沒有新增鍵；對 N-188 而言，`_init_schema` 只多 `_MIGRATIONS` 的一個欄位。
   - **QB-18.5 改為**：
     - `BOOK_MOVING_SETTLEMENT_SQL` 文字不變，緊接在 `settle` 之前；
     - `S2_FILL_ENTRY`、`S2_ELIGIBLE_BATCH_SQL` 各只有一份定義，`settle` 的 S2 分支與 `_read_settled_since` 都由它們取得，不得另寫 `'executed'`、`'S2'` 的條件字面；
     - 水位條件逐字等於 `COALESCE(s.settled_after_id, s.id) >= L.id`，沒有 `:floor`；
     - 實作的述詞版本與 N-177a 的實際先後一致（M1-2 第 4 點）；
     - N188-T8、T9、T18、T19 綠燈；
     - X-2 第 3 點、第 5 點 (a)～(c)；
     - 本修正第 2 點的 QB-7 白名單。
   - **QB-18.8 改為**：N188-T1～T20 都存在且綠燈；(a-1)、(a-3) 的 docstring 都在，寫明「不自癒」，(a-1) 另寫明窗口寬度。
   - **QB-18.11 改為**：檢查 X-10 第 2～5 點；N-177 的先後依 M1-2 第 4 點；X-10 第 6 點依 M1-3 第 6 點，不再檢查 N-190 耦合。
   - **QB-18.13（新）**：PR 說明附上部署條件、探針路徑與適用時機；探針唯讀、不 import app、不連網。實際部署前的探針結果由 devops-sre 附在 release 紀錄。這一項屬於 release gate，qa-reviewer 只在 PR 階段檢查說明與探針，不檢查部署結果。
   - **QB-18.14（新）**：與 N-177a 共用的常數只由其中一個 PR 定義，另一個 PR 只引用，不得出現第二份。
4. **X-14 第 2 點改為**：
   - 具名常數只含「`playbook_directives` 末尾多 `settled_after_id`」；
   - state key 不增加，所以 `after <= PRE_N166_STATE_KEYS`、`declared == PRE_N166_STATE_KEYS` 兩條斷言零 diff、不會轉紅；
   - 只改欄位那一條斷言。
5. **X-12 的修訂：**
   - 刪除代價「每次 backend 重啟後多報」；
   - 新增代價：
     - (a-3) 部署邊界的漏報，以及隨之而來的部署條件；
     - S2 述詞要讀批次現況與稽核表；
     - N-177a 與 N-188 共用常數造成的耦合；
   - 新增好處：重啟對判定零影響；少一個 state 鍵；(a-2) 消失；
   - 交 tech-writer：在 Consequences 的補充中，把 X-3 的「兩種」寫成 (a-1)、(a-3)，不得原地改寫。

## M1-5 送風控確認的項目
- R1：X-4 改採 F-3（NULL 戳記以 s.id 當水位下界），不採 F-1 計數門檻。理由見 M1-1 第 1、2 點，包括「計數會算進非下單列」的讀碼發現。
- R2：X-3 仍然是「兩種」，但組成從 (a-1)、(a-2) 改為 (a-1)、(a-3)。(a-3) 的範圍與期限見 M1-2 第 5 點。
- R3：部署條件 A（未結算的 S/P 賣單為 0），以及替代用的條件 B（以時間戳做運維探針，失敗時只會漏報），是否可以接受。
- R4：N-188 上線之後才 apply 的離線修復，比照部署條件處理。
- R5：逐批列在 S2 結算時移動 0 股不觸發；(B3) 在中斷時以讀取當下的合格狀態判定。
- R6：新增的多報類型（M1-2 第 5 點之 4）。
- R7：N-177 裁示 A-3 寫「照 TA 第 3 節」，即 S2 以稽核表「移動股數大於 0」為準；這與 B-(d)1「以 claim 為準」不一致。本修正以 B-(d)1 為準，S2 列不看稽核表。請確認 A-3 的這部分已被 B-(d)1 取代。
- R8：M1-3 對 (乙) 的判斷，以及給 ADR-0040 的約束。

（修正一由 coordinator 2026-11-05 附加，原文見 `work/reviews/2026-11-05-ADR0035補充五修正一-tech-architect.md`；風控確認 R1～R8 前不得合併、不得部署。）

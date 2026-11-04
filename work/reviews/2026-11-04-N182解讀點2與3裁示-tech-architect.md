# N-182 解讀點 2、3 裁示與補充四釐清一

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-182 解讀點 2、3 裁示

## 一、本次結論

**解讀點 2（擁有權）：可以接受，需要補一段釐清。** 下面的「釐清一」可以直接貼在補充四檔末。
- 依據是 S-5 第 4 點的明文授權。S-3「允許」條款不是依據。
- qa-reviewer 引用的是「任一方新增自己的加法欄位」。這句講的是在自己的擁有項上加欄位，不包括在別人的擁有項上加欄位。如果這樣解讀成了先例，之後誰都可以去動別人的型別，所以要在釐清文字裡寫清楚。
- 其他做法都不行：
  - 在 `InFlightRead` 加第三個欄位，會碰到固定項（R-3）。
  - 另開一個讀取點，違反 R-4。
  - 放進 `PendingExitRead`，等於放到 N-171 的出清資料裡，語意不對。
- 結論是 dev-lead 的做法是唯一合規的做法。

**解讀點 3（快照）：接受為已知限制，不修。附兩個條件，都要在 N-182 合併前完成。**
- dev-lead 描述的觸發情境，在單一請求內不會發生。他說的是：同一次評估在 commit 內把批次 skip 掉，而這個批次還有待成交買單。
  - K2 會擋掉這種情況，推導見第二段。qa-reviewer 的報告也沿用了這個錯誤描述，需要更正。
- 真正會觸發的只有並發。在 `read_in_flight` 之後、commit 讀 logged 之前，另一個請求的結算讓同一批次的另一筆買單成交。這屬於 F2／N-169 那一類的並發窗口。
- 批次狀態只會離開 planned、不會回到 planned。所以錯誤只可能是漏報，不會多報，下一次 `/today` 就會修正。
- 兩個修法都不採：
  - 「在鎖內重讀 blocked」：**VETO**。
  - 「commit 後依 effects 重算」：不採。

**分支 `fix/stock-desk-n182-blocked-entry-note` 有沒有其他違反補充四的地方：** 依交件說明加 qa 報告判斷，**沒有看到違反**。但有 4 項我看不到 diff、無法確認，要交 qa 實查（見第二段 D）。另外先預告一個規格缺口：SEAM-T2 常駐之後會和 N-168 衝突，不影響 N-182。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### A. 解讀點 2：擁有權

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (a) 在 `EntryBeforeExitRead` 加 `blocked`，查詢放在 `_read_entry_before_exit`（dev-lead 的做法） | 在同一個 read transaction 內，單一來源落在 N-168 本來就要用的位置 | 寫進了 N-168 的擁有項 | N-168 之後可能改寫它，讓單一來源分裂 | **採用**，用釐清一約束 N-168 |
| (b) `InFlightRead` 加第三個欄位 | 擁有權清楚 | 改到固定項 | 觸發 R-3 | 否決 |
| (c) N-182 另寫一次讀取 | 不碰 N-168 | 在 `read_in_flight` 之外讀在途資料 | 觸發 R-4，兩份快照 | 否決 |
| (d) 放進 `PendingExitRead` | 不碰 N-168 | 那是 N-171 的出清資料，語意不對 | N-171 改寫時會帶走它 | 否決 |

**可以直接貼上的補充文字（貼在補充四檔末）：**

```
## 釐清一（tech-architect 2026-11-04，回應 N-182 交件解讀點 2、3）

- 性質：釐清 S-2.3(c)、S-3、S-5 第 4 點與 S-7。不改任何固定項，不改 S-6 的判準。
- 依據：`work/reviews/2026-11-04-切面與N182交件-dev-lead.md` 解讀點 2、3；`work/reviews/2026-11-04-N182審查-qa-reviewer.md` 第 5、6 項。

### E-1 先行建立者（S-3、S-5 第 4 點）
1. S-5 第 4 點的情況已成立：N-182 先於 N-168 合併，由 N-182 建立 ADR-0034 補充一 S-1 第 3 點要求的「G1 擋下類」單一來源。N-182 因此是下列項目的**先行建立者**：
   - (a) `EntryBeforeExitRead.blocked` 欄位，名稱、型別與預設值以 N-182 合併時為準；
   - (b) `_read_entry_before_exit` 內填入 `blocked` 的查詢；
   - (c) store 常數 `BATCH_LEFT_PLANNED_SQL`，以及 `claim_directive`、`batch_blocking_claim`、`_read_entry_before_exit` 三處對它的直接引用。
2. 擁有權不移轉：(a)(b) 仍是 N-168 的擁有項；(c) 屬於 G1（ADR-0035 Decision 6′），不歸任何一方擁有。
3. N-168 對上列項目**只能擴充、不得改寫**：
   - 可以：
     - 在 `EntryBeforeExitRead` 新增欄位；
     - 在 `_read_entry_before_exit` 新增查詢；
     - 在 `blocked` 的查詢多選欄位，但列集合不變；
     - 在 service 端從 `blocked` 再篩出自己的清單。例如 `/today` 的 `entry_before_exit_blocked_directives` 只列已打 L4 戳記的列（ADR-0034 補充一 S-3 第 6 點）。
   - 不可以：
     - 把 `blocked` 改名、改型別或移除；
     - 改變 `blocked` 的列集合條件。列集合是待成交買單（風控 2026-11-01 共用定義：`action='buy' AND settled=0 AND status='pending'`）中符合 `BATCH_LEFT_PLANNED_SQL` 的列；
     - 另寫一份「批次已非 planned」的條件；
     - 讓 W-B6b、ENTRY、A 的排除改讀 `blocked` 以外的來源；
     - 改動 `tests/test_playbook_pending_entry_blocked.py` 的既有斷言。
   - W-B6 與 W-B6b 必須互斥（風控 2026-11-01 必改 3），而且必須以 `blocked` 或 `BATCH_LEFT_PLANNED_SQL` 切分，不得另外判斷。
4. N-168 若必須改寫上列項目才能完成，PR 先停住，由 tech-architect 出補充修正規格。(a)(b) 不是固定項，所以這種情況**不構成** S-6 的回退判準；但沒有補充就改寫，視同違反 S-5 第 4 點。
5. S-3「允許」條款中「自己的加法欄位」，指在自己的擁有項上、或在自己 ADR 定義的回應欄位上新增欄位，**不包括**在他方擁有項上加欄位。他方的擁有項，只有在 S-5 第 4 點這類有明文授權的情況下，才能由別人先行建立，並受本節第 3 點約束。
6. N-182 不填 `entry_before_exit_blocked_directives`，它恆為 `[]`；也不改 `_entry_before_exit_lines` 的回傳。這兩項連同 W-B6、W-B1d，仍由 N-168 實作。

### E-2 兩份快照（S-2.3(c)）
1. 判定：已知限制，接受，不修。
2. 理由：
   - 批次狀態只會離開 planned，不會回到 planned。所以 `read_in_flight` 讀到的 `blocked`，只會比 commit 鎖內的實際狀態少，不會多。
   - 單一請求內碰不到這個落差：
     - 本次評估在 commit 內能改變批次狀態的，只有 `batch_skipped`，而且只隨本次寫入的 R 系列列套用（N172-C5）；
     - ENTRY 與 A 計入的買單，是同一 symbol、同一預定執行日已記錄的 R1 買單。K2 會擋下本次對這個 symbol 的任何 R 系列新列，所以這個 symbol 的批次在 commit 內不會變動；
     - `apply_effects` 不套用 `batch_skipped`，也不套用成交類 effect。
   - 實際的觸發只有並發：在 `read_in_flight` 之後、commit 讀 logged 之前，另一個請求的結算讓同一批次的另一筆買單成交（planned → open）。這歸入 F2／N-169 的並發窗口殘留，下一次 `/today` 會修正。
3. 不採的修法：
   - 在鎖內重讀 blocked：**VETO**。
     - 這是 `read_in_flight` 之外的在途讀取，違反 R-4；
     - 而且 W-B6b 和 ENTRY／A 的排除會出自兩份快照，同一列可能兩邊都不出現，違反風控「互斥，合起來剛好是全部」。
   - commit 後依 effects 重算：不採。它只處理上面說的單一請求內碰不到的情況，對並發沒有作用。
4. 若日後必須消除這個殘留，唯一與本補充相容的方向，是把 `read_in_flight` 的呼叫時點移到 `commit_evaluation` 之後：
   - 因為狀態單向變動，較晚的快照只會往「帳冊不會判定」的方向偏，而這個方向是正確的；
   - 這要改 S-2.3(c)，須由 tech-architect 另出補充，評估對 N-168、N-171 的影響之後才能動。
5. 接受此限制的條件，N-182 合併前要完成，qa-reviewer 列為 BLOCKING：
   - (a) `same_day_warnings` 的 docstring 寫明此限制：觸發只有並發，單一請求內由 K2 排除；
   - (b) 新增一條守門測試：同一 symbol、同一預定執行日已有已記錄的 R1 待成交買單時，即使引擎本次對這個 symbol 產出 R3 skip，`evaluate_today` 之後這個 symbol 各批次的 status 仍與呼叫前相同；而且回應中 ENTRY／W-B6b 的分類，與呼叫結束後依 DB 重新計算的分類相同。

### E-3 S-7 增列檢查項
- QB-10（N-168 的 PR）：
  - E-1 第 3 點逐條檢查；
  - `store.py` 內「批次是否為 planned」的 SQL 比較，只出現在 `BATCH_LEFT_PLANNED_SQL`；
  - `tests/test_playbook_pending_entry_blocked.py` 的既有斷言零改動。
- QB-11（N-182 的 PR）：
  - E-1 第 6 點；
  - `blocked` 的列集合等於 E-1 第 3 點所述的集合；
  - E-2 第 5 點的 docstring 與守門測試存在且綠燈。
```

#### B. 解讀點 3：快照

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (i) 接受為已知限制，加 docstring 與守門測試 | 零結構變動；這個殘留只在並發時出現，只會漏報，下一次就修正 | 並發窗口內，ENTRY／A 仍可能誤稱「帳冊會照常判定」 | 風控 P2(d) 擔心的重複下單，在並發時仍可能發生 | **採用**，需風控確認 |
| (ii) 在鎖內重讀 blocked | 鎖內是準的 | 違反 R-4；W-B6b 與 ENTRY 的排除來自兩份快照，同一列可能兩邊都消失 | 比現況更糟 | **VETO** |
| (iii) commit 後依 effects 重算 | 不需要讀 DB | 只處理單一請求內本來就碰不到的情況，對並發無效 | 留下死碼 | 不採 |
| (iv) 把 `read_in_flight` 移到 commit 之後 | 錯誤只會往安全方向偏 | 要改 S-2.3(c)，並重新評估 N-168、N-171 | 規格大改，只為處理邊界情況 | 現在不做，保留為日後方向 |

**為什麼說「單一請求內不會發生」**（依 product 工作樹讀碼）：
- ENTRY／A 只計預定執行日 E 的已記錄買單（`_read_logged(conn, evaluation.execution_date)`）。引擎唯一會產出 buy 的是 R1。
- 在 commit 內，能讓批次離開 planned 的只有 `batch_skipped`。
  - 它只套用在本次寫入的 R 系列列所屬的 (symbol, batch_no) 上。
  - 本次評估中，產生 skip 的列一律是 R3（M1 的資料缺漏路徑在跳過時也是 R3）。
- K2（`_is_logged`、`_new_decisions`）的規則是：同一 (symbol, E) 已有任何 R 系列列，本次就不寫該 symbol 的 R 系列新列；同一次呼叫內也互相檢查。
  - 所以，只要已有 (X, b, E) 的 R1 買單，本次對 X 就不會寫入 skip，X 的批次在 commit 內不會變。
- commit 外的 `apply_effects` 已在 service 端濾掉 `LINE_BOUND_EFFECTS`，`FILL_DEPENDENT_EFFECTS` 本身也會跳過，所以不會改批次 status。
- 剩下的唯一路徑是並發結算。並發 commit 走的 skip 路徑同樣被 K2 擋下。

**請風控確認：** 這個殘留會影響風控必改 5 的完整性，因此建議合併前由風控書面確認可接受，可以和解讀點 5、6、9、10 同批處理。

#### C. 對實作的約束（逐條，qa 可檢查）
1. N-182：`entry_before_exit_blocked_directives` 恆為 `[]`，`_entry_before_exit_lines` 的回傳不動（釐清一 E-1 第 6 點）。
2. N-182：`blocked` 的列集合等於「`action='buy' AND settled=0 AND status='pending'`，且符合 `BATCH_LEFT_PLANNED_SQL`」。交件說明沒有提到 `status='pending'`，請 qa 對 diff 實查。
3. N-182：完成 E-2 第 5 點 (a)(b)。這把 qa 原本列為 medium、不擋的 docstring 跟進升為 BLOCKING，另外新增 (b) 的守門測試。
4. N-168：依釐清一 E-1 第 3、4 點擴充，不得改寫（QB-10）。
5. 修正描述：docstring、PR 說明與後續文件裡的觸發描述，都改成「並發結算」，不要再寫「同一次評估在 commit 內 skip」。

#### D. 分支是否有其他違反補充四之處（只依交件說明與 qa 報告）
- **沒有看到違反：**
  - QB-6：固定項零 diff。
  - QB-8：SEAM-T4、T5 綠燈。
  - `_settle_pending` 簽名不變，只在函式內設定 `refused_by_g1`。補充四 S-3 只禁改名、改型別、改簽名、改呼叫次數，函式內容可以改。
  - `refused_by_g1` 不外洩到 API：`UnsettledLineResponse` 是明確欄位映射。
  - `batch_blocking_claim` 由 JOIN 改成 scalar subquery，兩者等價。qa 報告留下的疑點已經確認：`playbook_batches` 的 `PRIMARY KEY (symbol, batch_no)` 在 `store.py:83`，`batch_no NOT NULL`。
- **看不到 diff、要交 qa 實查的 4 項：**
  1. 上一節約束 1：`entry_before_exit_blocked_directives` 與 `_entry_before_exit_lines` 沒動。N-182 head 上 SEAM-T1 綠燈是間接證據，但只涵蓋 golden 情境。
  2. 上一節約束 2：`blocked` 的列集合。
  3. `UnsettledLine.refused_by_g1` 有預設值 False，既有的建構點不受影響。
  4. QB-7：qa 自承只依 diff 推定。建議用 `git diff <empty-tree> 7370d68 -- apps/stock-desk/backend/app/playbook/service.py` 讀全檔，查 `evaluate_today` 呼叫鏈上有沒有第二個在途讀取點。
- **程序面：**
  - N-182 的 PR 必須等切面合進 product、做完 `git merge origin/product/stock-desk` 之後才能開（S-5 第 1 點、QB-5）。
  - 切面 PR 若在審查中又加了 commit，N-182 要重新 merge。
  - 本機是 Python 3.13，CI 是 3.12，3.12 上還沒跑過（解讀點 13）。本機全綠不等於 QB-4／QB-5 成立，要以遠端 CI 為準。
- **規格缺口預告（不擋 N-182）：**
  - SEAM-T2 規定「之後常駐」，但它的 golden 是切面前的基準。
  - N-168 的 W-B6 和 W-B3 一旦合法地改變 golden 情境中既有欄位的值（例如出清後凍結期的 warnings、結算 warnings），就會和「既有斷言只准因新增鍵而改」衝突。
  - N-182 head 上 T2 仍是綠燈，所以現在沒有問題。N-168 開工前，我再出釐清二，定義「核准的行為差異要逐條列舉，不得重錄 golden」。
- **順帶確認：**
  - 解讀點 12：可以接受。`tests/seam_helpers.py`、golden JSON、前端測試都算 2.1 所說的「新增的測試檔」。條件是 `app/` 不得 import `seam_helpers`，golden 不得重錄。
  - 解讀點 11：前端測試直接讀後端 golden 可以接受。這是 monorepo，前後端在同一次 checkout 裡，而且 golden 是凍結的基準。

### 其他部門
- 本次未參與（純評估）。需要的經手見第四段。

## 三、驗證

**讀過的文件**
- dev-lead 交件全文。
- 補充四全文（「A」節）。
- qa-reviewer 的 N-182 審查全文。
- 風控 2026-11-01 P2～P5 裁示的相關段落：共用定義、P2(d)、P4、P5、必改項。
- ADR-0034 補充一 S-1、S-3 第 6 點。
- 追蹤清單中 N-169、N-182 兩列。

**讀過的程式**（product 工作樹，也就是切面之前的快照，會漂移，請以內容定位）
- `store.py`：`:66-84`（批次表主鍵）、`:225-243`、`:309-391`（K2、`_apply_bound_effects`）、`:427-438`、`:1013-1059`（`apply_effects`）、`:1101-1148`（`commit_evaluation`）、`:1254-1301`（G1）。
- `service.py`：`:420-552`（`same_day_warnings`）、`:1048-1253`（`evaluate_today`）。
- `engine.py`：`:770-990`。確認 buy 只來自 R1，skip 一律是 R3 列加 `batch_skipped`。

**沒有驗證到的事**
- 我看不到 `fix/stock-desk-n182-blocked-entry-note` 的程式，第二段 D 的結論只依交件說明與 qa 的 diff 閱讀。
- 「單一請求內不會發生」是在切面之前的程式上推導的。N-182 若改動了 K2、`_apply_bound_effects` 或 `apply_effects`，推導就要重做。交件沒有提到這些改動，E-2 第 5 點 (b) 的守門測試就是為了把這個前提固定下來。
- 沒有執行任何程式或測試。

**本次限制**
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案，沒有使用 git。

## 四、下一步

1. **coordinator／tech-writer：** 把第二段 A 的「釐清一」原文貼到 `work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 的「A」節末尾。ADR-0035 的檔頭補充行建議加上一句「另見補充四釐清一（2026-11-04）」。
2. **dev-lead：** 在 N-182 分支補上 E-2 第 5 點的 (a) docstring 與 (b) 守門測試，觸發描述改成「並發結算」。
3. **qa-reviewer：**
   - 依 QB-11 與第二段 D 的 4 項實查重審 N-182 的增量；
   - 把審查報告第 6 項的觸發描述更正為並發；
   - QB-10 列入 N-168 的審查清單。
4. **risk-compliance-officer：** 書面確認 E-2 的殘留可以接受：只在並發時出現，只漏報，下一次修正，歸入 F2／N-169。可以和解讀點 5、6、9、10 一起回覆。
5. **tech-architect（我）：** N-168 開工前出釐清二，處理 SEAM-T2 常駐後與合法行為差異的衝突。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-04-切面與N182交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-04-N182審查-qa-reviewer.md
- /home/user/AICompany/work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md
- /home/user/AICompany/work/reviews/2026-11-01-ADR0034補充一-tech-architect.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py

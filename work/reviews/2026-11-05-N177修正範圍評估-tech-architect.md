# N-177 修正範圍評估

- 審查者：tech-architect
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-177（含補）修正範圍、既有資料修復與連動評估（tech-architect，唯讀）

## 一、本次結論

**根因確認（讀碼）。** `store.settle` 在 `directive.batch_no is None`（S2）或找不到批次列時，直接 `_mark_schedule` 後 return。指令列這時已被 claim 成 executed，但股數不減、現金不入帳。S2 的 `batch_closed` effect 屬 FILL_DEPENDENT，評估時被略過，結算時也沒人套用。engine 對黑名單標的照樣跑 S/P（`engine.py:1234` 在 `:1254` 的黑名單判斷之前），所以價格沒回升前，每天都會再發一張全數的 S2。

另有一個新發現：`blacklist()` 用的是 `INSERT OR REPLACE`（`store.py:832-838`），每天重發一次 S2，黑名單的起訖日就被往後推一次。

**方向。**
- **N-177a：S2 成交動帳。**
  - 只改 `store.settle`，另加一張加法稽核表，engine 零 diff。
  - 股數依 `batch_no` 遞增分配，以指令列股數為上限；每批 `min` 保護；現金以成交價乘上實際移動的股數入帳。
  - **不需要任何新字面**，所以是最快止血的路徑。
- **N-177b（補）：找不到批次列的 buy／sell。** 行為不變（不動帳），改成結構化地回報「判定成交但未動帳」，新增一句結算揭露，要送風控定稿。這條路徑正常程式碰不到，可以排在 N-177a 之後合併。

**和既有約束的衝突。**
- 與 engine 零 diff（C-B11、N172-C3）不衝突。
- 與 ADR-0035 Decision 6、N172-C8 的「`settle()` 零 diff」字面上衝突。我判定這是 N-172a 的範圍約束，比照補充四對 N172-C8 的同類判定，要在 spec 中明文記錄。
- 與 ADR-0039 Decision 10（群組 B 重放「`batch_no` 為 NULL 不計」）有實質衝突，群組 B 開工前要先補充修訂。
- 與 ADR-0034 不衝突：C-B6 維持、C-B11 維持。

**暫行揭露 (c)。** 述詞可以結構化判定，但它要 R-3 改 `_lines`、經 creative-lead 擬稿、送風控逐字定稿，成本不低於修正本身。我建議不要拿它取代修正。它的真正用途是：上線前若偵測到已受影響的資料、而 CEO 選「只對未來生效」，就用它當**既有資料的揭露**。

**CEO。** 修正本身不需要，這是回到 S2「出清整檔」的既有語意，沒有產品規則面的取捨。既有資料若偵測到受影響的列，修復方式要 CEO 裁示（比照 CEO #85）。原因是 R10 之下有「少賣或超賣」的取捨：回補會讓帳冊假設使用者已經照第一張 S2 賣出。偵測結果為 0 列就不需要 CEO。

## 二、各部門回報

### tech-architect（本人，唯讀）

程式路徑相對於 `/home/user/AICompany/apps/stock-desk/backend/app/`。

#### 1. 根因與修正範圍

**現況（讀碼，未執行）**
- `playbook/store.py:1420-1426`：status 不是 executed、或 `batch_no is None`、或 `get_batch` 回 None 時，只做 `_mark_schedule` 就 return。
  - S2 一律 `batch_no=None`（`engine.py:676-681`），而且是 stop_loss、不設價格帶，永遠判 executed（`engine.py:1338-1339`）。所以每一張 S2 都是「executed 但不動帳」。
- 結算前 claim 已經把列改成 `settled=1, status='executed'`（`store.py:1367-1374`，`service.py:1072`），這張單就此結束。
- 找不到批次列的 buy（N-177 補）：補充一 S-1 讓 G1 不擋它（`BATCH_LEFT_PLANNED_SQL`，`store.py:248-252`）。claim 成功後，`settle` 走同一個 return。
  - `tests/test_playbook_settlement_g1.py:263-284` 現在就把這個行為釘住：claim 成功、帳冊不變、unsettled 為空。
  - 找不到批次列的逐批 sell 也走同一條路。EMERGENCY 有 N2 揭露，其餘規則完全無聲。
- 黑名單：S2 的 `blacklist` effect 每次評估都會套用，`INSERT OR REPLACE` 把 `triggered_on` 和 `until` 改成最後一次觸發的日期。既有受影響的標的，黑名單會比規則規定的晚到期，方向是少買。

**修正的最小範圍（N-177a）**
- 進入條件：`status='executed' AND action='sell' AND rule_id='S2' AND batch_no IS NULL`。其他 `batch_no` 為 NULL 的列行為不變。
- 合格批次與 engine S2 的股數同義（`engine._symbol_average_cost`，`engine.py:208-219`）：同 symbol、`status='open'`、`remaining_shares>0`、`cost IS NOT NULL`。
  - store 不 import engine（現況如此，維持分層），改用 property test 守住兩邊對齊。
- 分配方式：依 `batch_no` 遞增。`left = directive.shares`，每批 `moved = min(remaining, left)`，歸零的批次改為 closed；現金加上 `price × Σmoved`。S2 不動 `p1_done`、`p2_done`、`p3_last_date`、`trailing_active`。

**分配方式的比較**

| 方案 | 優點 | 缺點、風險 | 判定 |
|---|---|---|---|
| **依 `batch_no` 遞增，以列股數為上限** | S2 是整檔層級的 N 股單。這個做法讓帳冊的整檔合計等於「使用者照單賣出 N 股後」的持股。新進場的批次 `batch_no` 一定最大（`_next_planned_batch` 取最小的 planned），所以評估時已存在的批次會先被分配 | 評估之後有較早批次被減股時，剩下的股數會落到最新那批。但整檔合計仍然正確 | **採用** |
| 依比例分配 | — | 全數出清的規則用比例分配沒有意義；會有尾數；每批留下零股殘部，之後 S1、P 規則會在殘部上再發單，也就是新的幻影賣單 | 否決 |
| 不設上限，結算時整檔 open 全部關閉 | 寫法最直覺 | 評估後才成交的批次也會被關閉，但使用者的券商單沒有賣這些股數，帳冊會少記，停損涵蓋出現缺口 | 否決 |
| 評估時記下組成，結算時照組成動帳 | 可以消除 W-B2LS「剛好抵銷」的殘留 | 要改 `commit_evaluation` 和 K1 落檔；結算時的組成可能已過時；觸發 W-B2LS 回審第 1 點與 N-188 重新設計 | 不在本單，可列入 ADR-0036 |

**原子性**
- S2 這條路徑上，所有批次的更新、現金的讀改寫、稽核紀錄，都在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成，錯誤處理照 C-11。
- 現行 sell 是 `set_cash` 和 `save_batch` 各開一個連線（`store.py:1443`、`:1457`）。S2 若沿用這種寫法，多批之間會出現半套狀態。
- claim 和 settle 仍分屬兩個 transaction（F2，歸 N-169），本單不處理。

**稽核紀錄的兩個方案**
- **M2（建議採用）：加法表。** 新增一張表（名稱由 dev-lead 定，例如 `playbook_fill_moves`），欄位為 directive_id、symbol、batch_no、shares_moved、price、settled_at。
  - 每一張在修正後結算的 executed S2，都至少寫一列；一股都沒移動時，寫一列 `batch_no` 為 NULL、股數 0 的紀錄。
  - 好處：
    - 「哪張 S2 移動了哪批多少股」成為落檔事實，不必事後重建；
    - 既有資料（修正前、沒有紀錄的 S2）可以精確區分；
    - N-188 述詞、ADR-0039 群組 B 重放、(c) 述詞都能精確判定；
    - claim 之後當機導致沒有紀錄時，會被判成「未動帳」，結果是多報，誠實。
  - 代價：會觸發 W-B2LS 回審第 1 點（「新增組成紀錄」），但風控條件 (b) 本來就要求回審。
- **M0：不加紀錄。** 範圍最小。但群組 B 重放和既有資料判定都必須分辨修正前後的 S2 列，只能靠時間切點，比較脆弱。只有在偵測結果確認既有資料為 0 列時才可以接受。

**N-177b（補）的處理方式**

| 方案 | 判定 |
|---|---|
| (i) 行為不變（claim 成功、不動帳），`settle` 回傳結構化結果（例如移動股數、是否套用），service 在結算 warnings 加一句「判定成交但帳冊沒有對應批次，未動帳」 | **採用**。補充一 S-1 的測試 (i)～(iii) 不變，只追加揭露斷言；字面要經風控 |
| (ii) 比照 G1 拒絕 claim | 不採：推翻補充一 S-1，而且會留下每天出現在 unsettled 的永久 pending 列 |
| (iii) 結算時自動補建批次列 | VETO：破壞 `ensure_batches` 的不變式，等於替使用者發明一個計畫 |
| (iv) 只扣現金 | VETO：有現金沒有股數 |

**與 engine 零 diff（C-B11、N172-C3）**
- 不衝突，engine 一行不改。
- 代價：S2 的合格批次述詞在 store 有第二份實作，用 parity property test 守住。
- engine 產生的 `batch_closed` effect 繼續保持未使用。

**與 ADR 的關係**
- **ADR-0035**：
  - Decision 6（`settle()` 零 diff）、6′（「不得改 `settle()`」）、Consequences 第 182 行與第 204 行、N172-C8 都寫明 `settle()` 零 diff。
  - 理由是「避開 0034 的 C-B6」，也就是 N-172a 當時與 N-168 並行修改的範圍問題。補充四已經把 N172-C8 對 `settle_pending` 的限制判定為 N-172a 的範圍約束，這裡同理。
  - N-177 不新增 `DirectiveStatus`，claim 仍逐列進行（不做 Decision 6 否決的「批次層級 claim」），不寫 `missed`，不改 G1。
  - **這個判定要寫進 spec**，否則 qa 依 N172-C8 會判 BLOCKING。
- **ADR-0034**：不衝突。
  - C-B6（buy 成交時把戳記複製到批次標示）是 N-168 對 `settle()` buy 分支的修改，N-177 不得動它。
  - C-B11 維持。標示「持續到 closed」：S2 關閉批次之後標示結束，符合原意。
- **ADR-0039**：
  - Decision 10 第 146 行寫「`batch_no` 為 NULL 的列不計（與 `settle()` 一致）」。N-177 之後這句不再成立，群組 B 會算錯「實際減少股數」。
  - Options 第 83 行否決「在 `settle()` 記錄移動股數」，理由是與 C-B6 衝突、會有兩個來源。採 M2 時，這個理由要在補充中重新論證：只有 S2 是跨批移動，紀錄只限 S2；逐批列仍走重放。
  - 群組 B 目前還在閘門後、沒有實作，所以補充要在群組 B 開工前落檔。
  - 群組 A 有一處互動：S2 關閉一個有在途 EMERGENCY 列的批次後，那一列會從區塊消失，落入 P-5(c) 殘留（已歸 N-169），N-177 會讓它更常發生。之後 EMERGENCY 列判定成交時會出 N2，字面為真。

#### 2. 既有資料修復（風控條件 (a)，另附給風控）

**受影響資料的形狀**
- 同一標的有一張或多張 executed S2，每天重發。
- 批次仍是 open，現金少記。
- 黑名單日期被推後。
- 價格若已回升，幻影部位上可能已經發過 S1／P 單，甚至已經判定成交。

**另一個要先講清楚的副作用**
- 只上修正、不修復時，既有受影響的標的在下一張 S2 成交時會被關閉，但現金是以**那一天**的開盤價入帳，不是第一張 S2 的成交價。
- 這個差額會永久留在帳冊上。
- 價格已回升的標的，幻影部位會一直留著。

| 方案 | 做法 | 風險 | R16 | 要 CEO |
|---|---|---|---|---|
| (A) 只對未來生效，揭露既有不一致 | 上修正；唯讀偵測報告交 CEO；受影響標的的列上掛 (c) 型揭露，直到不一致消失 | 現金永久偏差；價格已回升的標的，幻影部位會持續產生 S/P 單；揭露要有 R-3 與字面 | 不動任何列 | 偵測到受影響列時要 CEO 知悉並裁示；0 列時不需要 |
| **(B) 一次性離線修復，附稽核**（比照 D-A 的 R-3 工具） | 停服務、備份、對複本 dry-run → CEO 逐檔確認 → apply。對每段事件的第一張 executed S2，依 N-177a 的分配規則關批次、以該列 `settled_open_price` 回補現金；寫入加法稽核表，標記 source=repair，連到 directive_id。**不改、不刪任何指令列**，重發的 S2 列保留 | R10：若使用者其實沒照第一張賣出，帳冊會少記，停損涵蓋出現缺口。誤判防護：以下情況不給回補金額，只列「需人工判讀」：第一張 S2 之後該檔有其他 executed 賣單或買單；`total_deploy_set_at` 晚於第一張 S2 的結算時間；之後跑過 REBALANCE（TOTAL_DEPLOY 是用偏低的現金算的，由 CEO 決定是否重跑）。黑名單預設不改，只在報告中列出 | 指令列不動；批次與現金的變動有稽核 | **要**（同 CEO #85） |
| (C) 產品內請使用者確認 | UI 問使用者是否已在券商賣出 | 這就是 N-173（D 方案，待定調），要獨立 PRD 與風控審查，太重 | — | 併入 N-173，本單不做 |
| (D) 改寫既有指令列（把重發列標成作廢或 missed） | — | 違反 R16、N172-C11、ADR-0035 Decision 9 的 VETO | — | **VETO** |
| (E) `_init_schema` 啟動時自動回補 | — | 違反 ADR-0035 Decision 9（R-1 自動遷移 VETO） | — | **VETO** |

**建議的順序**
1. **先做唯讀偵測**，比照 N-152 與既有的 `/home/user/AICompany/apps/stock-desk/backend/scripts/n172_duplicate_probe.py`：停服務、對複本執行、唯讀、不 import app、不連網。新增以下類別：
   - executed S2，且同 symbol 仍有合格 open 批次、`entry_date` 早於該 S2 的 `execution_date`；
   - 每檔的重發次數；
   - 黑名單的 `triggered_on` 與第一張 S2 的差距；
   - executed、但 `batch_no` 為 NULL 或找不到批次列的非 S2 列；
   - 上線時仍 pending 的 S2（會在修正後正常結算，只列出）。
2. 偵測為 0 列：只上修正，不需要 CEO，也不需要 (c)。
3. 偵測大於 0 列：CEO 裁示選 (B) 或 (A)。
   - 本產品的使用者就是 CEO 本人，可以用券商對帳單逐檔確認，所以 (B) 加上逐檔確認，實質上就涵蓋了 (C) 的用意。
   - CEO 無法確認的標的，改走 (A) 加揭露。
   - **(B) 必須在 N-177a 上線之前、或停服務時同步執行**。若修正先上線，下一張 S2 會以錯誤的價格先把幻影部位關掉，修復工具就只能全部判成「需人工判讀」。
4. 校正之後若要在 UI 揭露，要送風控（ADR-0035 Decision 11 第 3 點）。

#### 3. 連動

**N-188 的動帳述詞（補充五尚未落檔，可以直接定成 N-177 之後的版本）**
- 現行候選：同 symbol（逐批列限同一批）有一列 `status='executed' AND batch_no IS NOT NULL AND action IN ORDER_ACTIONS AND settled_at > 本列.created_at`。
- 要改的地方：
  1. 本列是 S2 時：同 symbol 的 executed S2 也算，條件是有稽核紀錄、而且移動股數大於 0。
  2. 本列是第 k 批的逐批列時：除了同批的 executed 列，也要納入「同 symbol、有稽核紀錄且 `batch_no=k`、移動股數大於 0」的 S2。
  3. 修正前的 S2 列沒有紀錄，自然不計。這也符合事實，因為它們當時確實沒動帳。
- 「動帳條件」只定義一次，放在 `settle` 旁邊（N-188 約束第 5 點），而且要和 N-177a 的進入條件同一個常數。
- N-177a 若先上線，在 N-188 上線之前，S2 成交會成為一個新的「兩次評估之間帳冊變動」來源，而且沒有揭露。這屬於 N-188 既有缺口的延伸，相較於每天重發全數 S2，淨效益明顯為正，但要請風控書面知悉。

**W-B2LS 的前提 P（E-30：`shares == symbol_open_shares`，而且項目合計 ≤ `shares`）**
- 定義本身不用改。
- 要回審的具體項目：
  1. 採 M2 會觸發 ADR-0034 補充三回審條件第 1 點。
  2. 新情境：同一個 E 的 S2 列已經記下，兩次評估之間有一張較早的 S2 成交、整檔關閉。這時項目全部被過濾（`remaining_shares` 為 0），W-B2LS 和 W-B2LSf 都回 None。這一列只能靠 N-188 note 揭露，所以 N-188 述詞一定要含 S2（上面第 1 點）。
  3. 「剛好抵銷」殘留多了一條新途徑：S2 關閉較舊的批次，同時有一批帶標示的買單成交、股數相同，P 仍成立，W-B2LS 會宣稱「包含」那批。請風控確認是否沿用原本的接受理由。
  4. 新增測試：較早的 S2 在兩次評估之間成交時，S2 列不渲染 W-B2LS 家族；N-188 上線後，斷言 N-188 note 出現。

**N-168（分支已實作，審查中）**
- 語意上不受影響：E-30 (c) 的 property test 跑在同一份 book 上，與結算無關；標示「持續到 closed」不變。
- 但兩者都改 `store.settle`：N-168 依 C-B6 改 buy 分支，N-177a 改 sell／NULL 分支。所以：
  - **不得併入 N-168**：N-168 擁有 buy 分支，併入會讓審查重來，範圍也不同。
  - N-177a 可以從 product 另開分支並行開發。哪一張後合併，就由它 merge 最新的 product，以 merge commit 合併、不 rebase，並在 merge 後的 head 重跑完整 CI。
  - qa 要確認 C-B6 的測試斷言零改動。
- 我讀不到 N-168 分支對 `settle()` 的實際改法，衝突的程度沒有實查。

**N-189、N-190**
- N-189 D1 的 S2 述詞（同 symbol 有未結算的較早賣單，含 EMERGENCY）不變。N-177 修好之後，S2 的每日重發只剩真正的在途路徑 (a)，正好由 D1 涵蓋。
- N-190 的上線耦合不包含 N-177。S2 列會結算，本來就不受 N-190 的遮蔽影響。

#### 4. 暫行揭露（風控條件 (c)）

**述詞可以結構化判定（L 述詞）**
- 同一 symbol 存在一列 `rule_id='S2' AND action='sell' AND batch_no IS NULL AND settled=1 AND status='executed'`；N-177a 落地後再加上「沒有稽核紀錄」。
- 而且存在一個批次 `status='open' AND remaining_shares>0 AND cost IS NOT NULL AND (entry_date IS NULL OR entry_date < 該 S2.execution_date)`。
- `entry_date` 用嚴格小於，可以排除該 S2 成交之後才進場的批次。`entry_date` 為 NULL 時算成立，屬多報方向，請風控確認。
- 純 SQL，不比對字串。

**讀取點**
- 它讀的是已結算列加上批次，不是在途資料，**不屬 R-4、不得放進 `read_in_flight`**。
- 比照 N-188：放在 `commit_evaluation` 鎖內，和 `_read_logged` 讀同一份快照，以加法欄位放進 `EvaluationCommit`。spec 要明文判定它不屬 QB-7 白名單的範圍。

**和 N-188 note 的位置關係**
- 兩句說的都是「本列股數」與帳冊的關係，方向互補：
  - (c)：帳冊少減了一張已成交的 S2；
  - N-188：本列寫入之後帳冊動過。
- 兩者可以同時成立，但不矛盾。
- 候選順序：`line` → (c) → N-188 → D1 → D2 → W-B2L 系列。理由是 (c) 說的是帳冊本身有誤，而且是全數超賣。最後順序由風控定。
- 互斥候選：比照 N-188，(c) 出現時，W-B2LS／W-B2LSr 不渲染，改走 W-B2LSf。

**範圍提醒**
- 價格回升之後，幻影批次上的 S1、P 列也是同一類超賣，但風控的 (c) 只寫了 S2 列。是否擴及逐批列（該批符合上述批次條件），請風控裁示。

**成本判斷**
- (c) 需要：補充五的同列 note 欄位位置、走 R-3 改 `_lines` 簽名、creative-lead 擬稿、風控逐字定稿。
- N-177a 不需要任何字面。
- 所以「修正排不進下一輪」的機率，應該低於「(c) 排不進下一輪」。我建議 N-177a 直接排進下一輪，(c) 改成既有資料方案 (A) 的揭露。
- 不論採不採 (c)，補充五都要先預留這個位置，避免兩輪 R-3。

#### 5. 是否需要 CEO

- **修正本身：不需要。** S2 出清整檔、成交即動帳（CEO 裁決七），都是既有語意。
  - 以列股數為上限、依 `batch_no` 分配，是在 R10 下唯一讓整檔合計等於「照單成交後持股」的分法，沒有新的規則取捨。
  - 黑名單、名額不補都不變。
- **既有資料：偵測大於 0 列時需要。** 回補等於替 CEO 認定「已照第一張 S2 賣出」，牽涉少賣與超賣的取捨，與 CEO #85 同性質。
- **選配，屬內部操作建議、不是面向使用者的文案：** coordinator 可以比照 ADR-0035「暫行緩解」的先例，轉告 CEO 一句話：「修正上線前，同一檔在第一張 S2 之後的 S2 列，股數可能多於實際持股。」

#### 6. 對開單的約束（N177-C1～C16，qa-reviewer 逐條檢查）

1. **C1**：`engine.py` 零 diff。
2. **C2**：不 DELETE、不 UPDATE 指令列（claim 現有的 UPDATE 除外）；不在既有 K1 下另寫新列；不新增 `DirectiveStatus`；`claim_directive` 與 G1 的 SQL 零 diff；不新增 `pending_directives` 呼叫點（QB-7）。
3. **C3**：N-177a 的程式改動只限 `store.settle` 與它的私有 helper、加法表的 schema。`commit_evaluation`、`_read_logged`、`read_in_flight`、`_read_exit_state`、`_lines` 零 diff。
4. **C4**：S2 路徑的進入條件逐字等於 `status='executed' AND action='sell' AND rule_id='S2' AND batch_no IS NULL`。其他 `batch_no` 為 NULL 的列行為不變。
5. **C5**：合格批次 = 同 symbol、`status='open'`、`remaining_shares>0`、`cost IS NOT NULL`，依 `batch_no` 遞增排序。要有 parity property test：任意 book 上，合格批次的合計等於 `engine._symbol_average_cost(book 中該 symbol)[1]`。
6. **C6**：每批移動 `min(remaining, left)`；Σmoved ≤ `shares`，也 ≤ 合格批次合計；歸零的批次改為 closed；現金加上 `price × Σmoved`（`price` 的取法同現行）；S2 不改 p 旗標與 `trailing_active`。
7. **C7**：同一筆 S2 的所有批次更新、現金讀改寫、稽核紀錄，在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成，錯誤處理照 C-11。
8. **C8**（採 M2 時）：用 `CREATE TABLE IF NOT EXISTS` 建加法表；每一張修正後結算的 executed S2 至少一列紀錄（零移動也要一列）；其他規則不寫紀錄；`_init_schema` 不得回填舊 S2。
9. **C9**：buy 分支的 C-B6 行為零改動，N-168 測試的斷言零改動；`test_a_missing_batch_row_is_not_refused` 的 (i)～(iii) 不改，只允許追加斷言。
10. **C10**：`settle()` 的回傳值只做加法；N2 的判斷與字面零 diff。
11. **C11**：store 不 import wording，也不 import engine。
12. **C12**：N-177a 零新字面。N-177b 的字面只放在 `wording.py`，風控逐字定稿前不得合併。
13. **C13**：SEAM golden 不得重錄。若有差異，依釐清二登記到 `tests/golden/seam/approved/<owner>.json`。
14. **C14**：獨立 PR，不與 N-168、N-188、N-189 同一個 PR。以 merge commit 合併；後合併者 merge 最新 product 並重跑完整 CI。
15. **C15**：既有資料修復只能用離線工具，流程為 dry-run → CEO 確認 → apply，只寫加法稽核；啟動時自動遷移 VETO。
16. **C16**：測試（BLOCKING）：
   - S2 成交後整檔關閉，現金正確；
   - 價格持續低於門檻 N 天，日誌中只有一張 S2；
   - 列股數小於合格批次合計（評估後有新批進場）：最新批不動或部分減股，整檔合計 = 原合計 − `shares`；
   - 列股數大於合格批次合計（較早批已被減股）：只入帳合計；
   - 同一次結算 S1 加 S2，兩種 id 順序都測：不出現負數，不重複入帳；
   - C5 的 parity 測試；
   - `cost` 為 None 的批次被排除；
   - 交易中途注入失敗：沒有半套狀態；
   - 重跑結算不會再動帳；
   - `/today` 與 `POST /settle` 結果相同；
   - 有在途 EMERGENCY 時 S2 成交，之後 EMERGENCY 判定成交出 N2，N-171 區塊不再列出該批（釘住 P-5(c) 路徑）；
   - 較早的 S2 在兩次評估之間成交時，S2 列不渲染 W-B2LS 家族；
   - qa 重現測試的 expected 轉綠。

#### 7. 時序（相對 N-168、N-188、N-189、N-190）

1. **現在就可並行，不碰產品碼：**
   - qa-automation 重現 F8 與 N-177 補。追蹤清單沒有看到 F8 的重現紀錄，目前仍是讀碼判定。
   - dev-lead 或 data-engineer 擴充唯讀偵測腳本，只改 `scripts/` 與 tests。是否在 CEO #84 的授權範圍內，請 coordinator 確認。
2. **TA 出 spec：** 等風控確認修復方向與 (c) 的定位後出。內容包括：本評估、ADR-0035「`settle()` 零 diff 屬範圍約束」的判定、M2 的表、ADR-0039 Decision 10 重放的修訂。是新的短 ADR 還是補充，由 coordinator 依先例定。
3. **N-177a：** 從 product 開分支，不依賴 N-168 的程式碼，排進下一輪。合併順序依 C14。偵測若大於 0 列，CEO 裁示的修復要在上線前、或停服務時同步完成。
4. **N-177b：** 排在 N-177a 之後，等字面定稿。
5. **N-188（補充五）：** 動帳述詞直接定成包含 S2 的版本，並預留 (c) 的位置；實作排在 N-177a 合併之後。W-B2LS 的回審（含本評估第 3 節第 1～4 點）與 N-188 同一個 PR。
6. **N-189 D1／D2：** 排在 N-188 之後，不受 N-177 影響。
7. **N-190：** 照風控耦合，不早於 N-188 與 N-189(D1)。與 N-177 無耦合。
8. **群組 B：** 開工前要先有 ADR-0039 的補充（重放納入 S2）。

### 其他部門
本次未參與（product-manager、risk-compliance-officer、creative-lead、dev-lead、qa-reviewer、qa-automation、qa-e2e、devops-sre、data-engineer、tech-writer、frontend-engineer、art-lead 等）。應經手但尚未經手的有三個：
- 風控：修復方案、(c) 的定位與是否擴及逐批列、N-177a 先上線時 N-188 揭露缺口的書面知悉、「剛好抵銷」的新途徑；
- qa-automation：重現；
- coordinator：偵測腳本的授權。

## 三、驗證

**讀過的程式**（`/home/user/AICompany/apps/stock-desk/backend/`）：
- `app/playbook/store.py`：`:150-649`、`:696-860`（節選）、`:1080-1482`
- `app/playbook/engine.py`：`:208-219`、`:640-734`、`:806-851`、`:1100-1342`
- `app/playbook/service.py`：`:300-302`、`:990-1229`、`:1305-1339`
- `tests/test_playbook_settlement_g1.py`：`:255-304`
- `tests/test_playbook_store.py`、`tests/test_playbook_acceptance.py`：只 grep S2
- `scripts/n172_duplicate_probe.py`：只 grep 類別

**讀過的文件：**
- `/home/user/AICompany/work/reviews/2026-11-04-N189方向裁示-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-04-N189查證與方向評估-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-04-N188查證與方向評估-tech-architect.md`（`:30-108`）
- `/home/user/AICompany/work/reviews/2026-11-04-ADR0034補充三-tech-writer.md`
- `/home/user/AICompany/work/reviews/2026-11-04-N168風控S5S6技術補裁與釐清七-tech-architect.md`（E-28～E-33）
- `/home/user/AICompany/work/reviews/2026-11-04-N168後端修正交件-dev-lead.md`（grep）
- `/home/user/AICompany/work/reviews/2026-11-01-ADR0035補充一-tech-architect.md`（grep）
- `/home/user/AICompany/work/reviews/2026-10-31-N172修法與資料修復評估-tech-architect.md`（F8 段）
- `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`（`:1-30`、`:118-267`）
- `/home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md`（grep）
- `/home/user/AICompany/docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md`（`:36-155` 與 grep）
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`（`:260-354`）

**未查證的部分：**
- 全部是讀碼判定，沒有執行。
- N-168 分支對 `settle()` 的實際 diff 沒有看到。
- 正式 DB 是否已有受影響的列，未知。依指示沒有碰 `data/*.db`，要靠偵測腳本確認。
- 「同一次評估內 S2 與 R 系列進場同時觸發」是否可能，沒有追完，不在本單。

我沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

**CEO 要親自驗證的：** 本輪沒有。偵測結果若大於 0 列，屆時要用券商對帳單逐檔確認。

## 四、下一步

1. **coordinator：**
   - 把 N-177 拆成 N-177a（S2 動帳，P1，下一輪）與 N-177b（補，P1，排在 a 之後）；
   - 派 qa-automation 重現 F8 與 N-177 補；
   - 確認偵測腳本是否在 CEO #84 的授權範圍內，並派工；
   - 把本評估轉給風控。
2. **risk-compliance-officer：**
   - 裁示既有資料修復的方向（建議：先偵測；0 列只修正；大於 0 列送 CEO 在 (B) 與 (A) 之間選）；
   - 確認 (c) 改定位為既有資料揭露，以及是否擴及逐批列；
   - 書面知悉 N-177a 先上線時 N-188 的揭露缺口；
   - 確認「剛好抵銷」的新途徑是否沿用原接受理由。
3. **tech-architect：** 風控回覆後出 N-177 spec，含 C1～C16、ADR-0035 範圍判定、ADR-0039 Decision 10 修訂。補充五起草時，把動帳述詞定成含 S2 的版本，並預留 (c) 的位置。
4. **CEO：** 現在不需要裁決。只有偵測結果大於 0 列時，才要裁示修復方式（同 CEO #85 的性質）。

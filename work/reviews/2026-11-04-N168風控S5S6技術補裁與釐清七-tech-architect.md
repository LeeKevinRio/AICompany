# N-168 風控 S5／S6 技術面補裁（附釐清七）

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：風控 S5／S6 裁示的技術面補裁，附釐清七

## 一、本次結論

三點都裁了，寫成釐清七（E-28～E-33），全文在第二段。結論是**卡住一處**：W-B2LS 照現行的固定項做不出來，要改一個固定項，觸發 R-3，所以本次出補充修正規格。

1. **第 5 點條件 (ii)：有一條路徑會渲染「不是本次評估產出」的 S2 列。**
   - 路徑：只有 `/today` 的 `directives`。它取自 `commit.logged`（ADR-0035 Decision 4），所以同一預定執行日稍早那次評估記下的 S2 列，在之後的評估中會原樣顯示。
   - 其他路徑都不會出現 S2：出清回應、`pending_exit_directives`、N-171 區塊、兩個買單清單、rebalance。原因是這些列不是 EMERGENCY（逐批產生，`batch_no` 不是 null，見 `service.py:413-419`），就是 buy，或是 `labeled_batches=()`。
   - **批次集合不保證一致。** 舊 S2 列的 `shares` 是用當時的 book 算的，標示卻是用本次的 book 算的。兩次評估之間，只要有結算讓同一 symbol 的批次變動，兩者就會不一致。例如：V4 後補 bar 讓打過戳記的買單成交、前次載入失敗這次成功，或中間有人呼叫 `POST /settle`。
   - **風控的守門「標示批次合計 ≤ `shares`」必要但不夠。** 稍早的 S2 列記下之後，又有一批成交並帶上標示時，只要其他批次夠大，合計仍然 ≤ `shares`，但 W-B2LS 會宣稱這一列包含了那一批，這是不實陳述。所以要多加一個前提：`shares` 等於同一份 book 中該 symbol 的持有合計。
   - **守門放在 service 層的純函式**，也就是 `entry_before_exit_note` 的 S2 分支，做成執行期的判斷：
     - 不得 raise：`/today` 回 500 會讓 FROZEN、W-B6 等所有揭露一起消失；
     - 不得用 Python `assert`：`-O` 會把它拿掉；
     - 不放在 engine（C-B8、C-B11）、API 或前端。
   - **前提不成立時怎麼呈現，要風控定**：(β) 不渲染，靠同頁快照列上的 W-B2／W-B2L 揭露；或 (δ) 另定一句後備句。我只裁定不得 raise、也不得照常渲染 W-B2LS。
2. **與 E-26 有衝突，而且衝突在 E-26 之外。**
   - **衝突點在固定項。** W-B2LS 的 `{labeled_items}` 需要各批的 `remaining_shares`，前提判斷又需要該 symbol 的持有合計。`_lines` 唯一的資料來源是 `labeled_batches`，而 `LabeledBatch` 只有 `symbol`、`batch_no`、`entry_date` 三個欄位。`_lines` 的簽名和 `LabeledBatch` 都是 S-3 的固定項，所以 R-3 成立。
   - **我裁定的做法**：在 `LabeledBatch` 加兩個必填欄位，`remaining_shares` 和 `symbol_open_shares`；`_lines` 的簽名不動（E-29）。
   - **E-26 擴充**：引用點的約束擴及兩個新常數（以及風控若另定的後備句常數）；QB-13 的 AST 口徑同步擴充。
   - **golden**：預期沒有新的差異，由 E-24 第 3 點 (b) 的測試實證；若 golden 中有任何 `DirectiveLine` 的 note 不是 null，就停住。
3. **E-24 第 3 點 (a) 照常成立。**
   - 理由一：它是以識別名 `wording.ENTRY_BEFORE_EXIT_NOTE` 定義的，改值後依 E-20 第 1 點自動跟著變。
   - 理由二：批次列的 `batch_no` 是 int，永遠走 W-B2L，不會走到 S2 分支。
   - 理由三：這個鍵在 T2 的刪除鍵裡，golden 沒有差異，`n168.json` 不改。
   - 例外：測試若把整句字面寫死，依 E-20 第 3 點整條替換。

## 二、各部門回報

**tech-architect（本人，唯讀）**：讀了以下文件與程式（worktree）：

- 風控 11-04 裁示的第二節第 3～6 點與逐條意見；
- `engine.py:208-219`（`_symbol_average_cost`，S2 股數 = open、cost 非 null、`remaining_shares>0` 的批次合計）與 `:654-694`（S2）；
- `api/playbook.py` 中 `_lines` 的全部呼叫點（`:433`、`:545-571`、`:708`、`:731-740`）；
- `service.py:413-419`（EMERGENCY 逐批產生）；
- `models.py:366-378`（`LabeledBatch`）；
- `store.py:130-153`（schema）；
- `wording.py:1271-1278`（`labeled_items`）；
- `LabeledBatch(` 的所有建構點：只有 `service.py:743`、N-168 自己的測試、SEAM T5 第 460 行。N-171 沒有建構它；`test_playbook_pending_exit_block.py` 只有 AST 守門。
- `types.ts` 沒有 `LabeledBatch`，前端不受影響。

### 釐清七全文（附於補充四檔末）

```
## 釐清七（tech-architect 2026-11-04，回應風控 `work/reviews/2026-11-04-N168停止點S3至S6裁示-風控.md` 第二節第 4～6 點）

- 性質：依 S-6 R-3 修正 S-3 固定項 `LabeledBatch`（2.2(c)）；釐清 E-24 第 3 點、E-26、E-12 QB-13。不改 `_lines` 簽名與其他固定項，不改 golden，不授權重錄。
- 依據：風控同檔第 4 點（S5 (i) 原始整數）、第 5 點（W-B2LS／W-B2LSr 與條件 (i)～(iv)）、第 6 點（W-B2L 修訂）；ADR-0035 Decision 4；ADR-0034 C-B8、C-B11；N-168 worktree `8efacd8`（讀碼，未執行）。

### E-28 S2 列的渲染路徑（風控第 5 點條件 (ii)）
1. S2 列（`action='sell'`、`batch_no` 為 NULL）只由 engine `_evaluate_symbol_stop` 產生。`_lines` 的呼叫點中，只有 `/today` 的 `directives` 可能含 S2：
 - EMERGENCY 逐批產生，`batch_no` 不是 NULL：出清回應的 `directives`、`pending_directives`，以及 `pending_exit_directives` 與 N-171 區塊都是 EMERGENCY；
 - `entry_before_exit_*` 只有 buy；
 - rebalance 傳 `labeled_batches=()`。
2. `/today` 的 `directives` 是 `commit.logged`。同一預定執行日稍早一次評估記下的 S2 列會原樣顯示，它的 `shares` 是用當時的 book 算的；`labeled_batches` 則是用本次的 `book` 算的（`labeled_batches_of(book)`）。兩次評估之間，只要該 symbol 的批次變動（V4 後補 bar 或前次載入失敗後的結算成交、`POST /settle`、其他改動批次的寫入），兩者的批次集合就不一致。單一請求內，engine 與標示用的是同一份 `book`，條件 (i) 成立。
3. 「標示批次 `remaining_shares` 合計 ≤ `shares`」是必要條件，但不充分：稍早的列記下之後，若又有帶標示的批次成交，只要其他批次夠大，合計仍然 ≤ `shares`，但這一列並不包含那一批。

### E-29 `LabeledBatch` 固定項修訂（R-3）
1. `LabeledBatch` 新增兩個必填、無預設值的欄位：
 - `remaining_shares: int`：該批的剩餘股數；
 - `symbol_open_shares: int`：與該批同一份批次清單中，該 symbol 的 `engine._symbol_average_cost(...)[1]`。
 兩者都和標示取自同一份批次清單（`/today` 為 `book`，出清為 C-2 讀到的 open 批次，unauthored 為 `list_batches`）。不得另寫 open／cost／`remaining_shares` 的述詞；engine 零 diff（C-B11）。
2. 其他固定項不變：`_lines` 的簽名、`labeled_batches` 的欄位型別、`read_in_flight`、`types.ts`（`LabeledBatch` 不序列化）。
3. R-3 的處理：
 - 若 N-171-A 已合進 product（worktree 已含 `_pending_exit_block`／`pending_exit_block`，由 coordinator 確認），「N-171-A 先合」的回退在實質上已經滿足。
 - 若尚未合併，本條的 commit 要等 N-171-A 合併、N-168 merge product 之後才能落地。
 - E-13 第 5 點「N-168 先過閘門時以 cherry-pick 先行」的路徑，對 N-168 取消。
4. QB-6／E-15 的例外：在 `LabeledBatch` 的程式行中，只准新增本條的兩個欄位，docstring 可以同時改正（含 I11 所指「`_lines` is the only reader」）。SEAM T5 第 460 行的 `LabeledBatch(...)` 補上兩個引數，屬 E-4 第 3 點的 fixture 變更：斷言零改動，並在 PR 說明列出。
5. 對 N-171 沒有影響：N-171 不建構 `LabeledBatch`，只把 `labeled_batches` 原樣轉給 `_lines`（E-26 第 3 點）。

### E-30 W-B2LS／W-B2LSr 的渲染規則與守門
1. 在 `service.entry_before_exit_note` 的 `batch_no is None` 分支實作。簽名歸 N-168 擁有，可以新增 keyword 參數傳入該列的 `shares`。批次列（`_labeled_snapshot`）的 `batch_no` 一律是 int，不得走到這個分支。
2. 項目：同一 symbol 的標示批次中 `remaining_shares > 0` 的那些，依 batch_no 遞增，以 `wording.labeled_items` 渲染，股數印原始整數（S5 (i)）。沒有任何項目時回傳 None。`remaining_shares` 為 0 的標示批次不列入；這點請風控確認。
3. 前提 P：`shares == symbol_open_shares`（同一 symbol 各項目的這個值必須相同，不同時視為 P 不成立），而且項目合計 ≤ `shares`。
 - P 成立：渲染 W-B2LS；`shares` 大於項目合計時，再接 W-B2LSr。
4. P 不成立：
 - 不得 raise，不得用 `assert`，不得照常渲染 W-B2LS；
 - 改為回傳風控所定的處置：(β) None，或 (δ) 另定的後備句。
 - 風控定案之前，此分支不得合併。
5. 守門放在 service 層的這個函式；engine、API、前端都不做判斷。測試（BLOCKING）：
 - (a) 分支的單元測試：P 成立時，有、無 W-B2LSr 兩種；P 不成立時，`shares` ≠ 持有合計、項目合計 > `shares` 兩種。
 - (b) 整合測試：同一預定執行日評估兩次，兩次之間讓同一 symbol 的一筆打過戳記的買單成交（後補 bar 或 `POST /settle`）；斷言第二次回應的 S2 列依第 4 點處置。
 - (c) property test：任意 book 上，engine 以該 book 產出的 S2 列，搭配同一份 book 的 `labeled_batches_of`，P 恆成立。
 - (d) `_labeled_snapshot` 不會走到 S2 分支。
6. 已知殘留（交風控）：兩次評估之間批次增減的股數剛好抵銷、合計不變時，P 成立，但該列當時的組成可能不同。

### E-31 E-26 的擴充
1. `app/` 內，`ENTRY_BEFORE_EXIT_NOTE`、`ENTRY_BEFORE_EXIT_SYMBOL_NOTE`、`ENTRY_BEFORE_EXIT_SYMBOL_REST_NOTE`（以及風控若另定的後備句常數）的屬性引用，只能出現在 `service.entry_before_exit_note` 內。該函式可以呼叫 `wording.labeled_items`（與 W-B7 共用項目模板）。
2. `entry_before_exit_note(` 的呼叫者仍然恰好兩個（E-26 第 1 點），而且只有 `_lines` 會傳入 `batch_no=None`。
3. QB-13 的 AST 口徑擴及第 1 點的全部常數；`DirectiveLine(` 只能在 `_lines` 內，`_lines` 的簽名不變（SEAM-T5）。
4. golden：預期沒有新的差異。若 E-24 第 3 點 (b) 的測試發現 golden 中有任何 `DirectiveLine` 的 note 不是 null，停住送 tech-architect。
5. W-B2L 的改值依 E-20 處理：
 - 以識別名引用的地方自動跟著變；
 - 逐字抽取測試的來源改成風控 11-04 檔；
 - 常數值、抽取來源、逐字守門放在同一個 commit，並在 PR 說明列出。

### E-32 E-24 第 3 點 (a) 照常成立
(a) 以識別名定義；批次列一律走 W-B2L；這個鍵在 T2 的刪除鍵內，golden 沒有差異，`n168.json` 不改。測試若把整句字面寫死，依 E-20 第 3 點整條替換。

### E-33 S-7 增列檢查項
- QB-17（N-168 的 PR）：
 - E-29：`LabeledBatch` 的 diff 只有第 1 點的兩個欄位與 docstring；兩個值都出自同一份批次清單；`symbol_open_shares` 經 `_symbol_average_cost` 計算；engine 零 diff；第 3 點的合併時點；SEAM T5 只改 fixture。
 - E-30 第 1～5 點的測試存在且綠燈；不得 raise，也沒有 `assert`。
 - E-31 第 1～3 點的 AST 檢查。
```

**應經手但尚未經手**
- risk-compliance-officer：
  - E-30 第 4 點：P 不成立時選 (β) 或 (δ)；選 (δ) 要逐字定稿；
  - E-30 第 2 點：`remaining_shares` 為 0 的批次不列入；
  - E-30 第 6 點：已知殘留。
- coordinator：確認 N-171-A 是否已合進 product（決定 E-29 第 3 點的時點）。
- qa-reviewer（含 Codex）：QB-16、QB-17。

**其他部門**：product-manager、devops-sre、data-engineer、frontend-engineer、tech-writer 等，本次未參與（純評估）。

## 三、驗證

- 以上全部是讀碼判定，我沒有執行任何東西。
- E-28 第 2 點的不一致情境是推論，沒有重現；E-30 第 5 點 (b) 的整合測試就是它的實證，若重現不出來，請 dev-lead 回報。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。
- **建議 CEO 親自確認**：不需要。R-3 依 S-6 不需要 CEO 裁示。

## 四、下一步

1. **coordinator**：把釐清七附在補充四檔末，ADR-0035 標頭改為「釐清一～七」；並確認 N-171-A 是否已合併。
2. **dev-lead**：
   - 現在就做：E-23、E-24、S3、S4、S5 (i)、W-B2L 與 W-B3 的改值。
   - W-B2LS 與 E-29 的 `LabeledBatch` 修訂，等 E-29 第 3 點的時點成立，而且風控裁定 E-30 第 4 點之後再做。
3. **風控**：裁 E-30 的第 2、4、6 點。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-04-N168停止點S3至S6裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/playbook/models.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/playbook/service.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/playbook/engine.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/api/playbook.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/tests/test_playbook_today_seam.py

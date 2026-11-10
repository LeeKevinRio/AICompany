# N-209b 規格補遺三（RC-25）、風控讀碼推論確認、N-210 評估（ADR-0044 草案）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-209b 規格補遺（RC-25）、風控讀碼推論確認（RC-23、RC-26、RC-27、P-6、P-7），以及 N-210 評估（ADR-0044 草案）

## 一、本次結論

全程唯讀：沒有改任何檔案，沒有執行任何指令，沒有讀 `.env`，也沒有碰 `data/*.db`。

**交付 A：N-209b 規格補遺**
- 新 status 定名為 **`cash_unrecorded`**（同時回答 PRD Q-11），字面識別名為 `REBALANCE_CASH_UNRECORDED`。
- 閘的位置、AST 測試、A6 不變式、F-4 封閉集合、T1 的四格矩陣都已寫成可貼上的條文（下文 A-1）。
- **恢復路徑：畫面上沒有。**
  - 已確認後，資金確認入口不會再渲染（playbookView.ts:322-324、page.tsx:204）。
  - REBALANCE 依 RC-25 會拒寫。
  - 唯一偶然可行的路徑：資金確認失敗後，若前端還沒重新取得 `/today`，面板仍在，再按一次就會補寫。這不是設計出來的路徑，重新整理後就消失。
  - 另外有一個連帶缺陷：這個狀態下，賣出成交會由 `set_cash` 建立現金鍵，而值只有賣出所得。之後 RC-25 的閘會放行。也就是說，「鍵存在」不等於「使用者記錄過現金」。
- **B-1 已改寫**，窮舉 N-209b 的五項變更與三類既有輸入的行為改變。其中一點以前漏掉了：TD 鍵不存在時，`_NO_PREVIOUS` 本身就改變了既有 ok 分支的 `message`。補遺二 A5 原本寫「ok 既有欄位逐值不變」，這句與 C5 矛盾，本次一併更正。
- **N-209b 合併前要定稿的字面只有三項**：`REBALANCE_UNAUTHORED`、`REBALANCE_CASH_UNRECORDED`、`REBALANCE_RESULT_NO_PREVIOUS`。
  - RC-29 的兩句不依任何後端值。TA 建議放在 N-209 前端，擋 N-209 合併，不擋 N-209b。
  - 若風控要把這兩句放進後端 `message`，就會改動 `REBALANCE_RESULT`，B-1 要再加一項。請風控裁示。

**交付 B：風控的讀碼推論**
- **RC-23：兩個方向都成立，但有三點要更正或補充。**
  1. 「批數小於 bpt 時投入低於配額」只在「每批金額不小於收盤價」時成立。1 股下限是另一個既有性質，與批數不一致無關。
  2. 「之後每批至少 1 股」成立，但不是「恰好 1 股」：價格下跌或前面有跳過的批次時，會再補足一次。
  3. **planned 估算的分支在現有呼叫點根本走不到**，因為 `_next_planned_batch` 只取最小號的 planned 批次（engine.py:738-750）。後果句不得依賴這個分支。
- **RC-26：成立。**
  - buy 和逐批 sell 都會被 claim 成 executed（或 missed），帳冊（`playbook_batches`）與現金（`playbook_state.cash`）都不動。
  - `SETTLEMENT_SUMMARY` 的已成交計數會把這一列算進去。
  - N-177a、ADR-0042 上線後行為相同；N-177b 只是另外加揭露。
  - 1d 已依 RC-26 改寫，附只回計數的 SQL。
- **RC-27：R3 的三種 `git log` 和 R4 的 `git diff` 在零命中時都是 exit 0。** 依 git 的文件化行為判斷，未實跑。
  - 沒有一條像 `git grep` 那樣零命中回 exit 1，所以「exit 不是 0 → BLOCKING」不會誤擋。
  - 另外發現一個漏洞：R4 的路徑若打錯字，結果會是「沒有輸出、exit 0」，等於靜默放行。建議 R4 與 R5 共用同一份路徑清單，並加控制組。
- **§9 P-6、P-7：判定文字與 SQL 已給**，只回 0 或 1。另外建議增列 P-8（已確認 × 現金鍵不存在），直接偵測上面的恢復路徑缺口，由風控決定要不要採用。

**第三部分：N-210（RC-29）評估，ADR-0044 草案（proposed）**
- **TA 建議**：採 (iii-a)「`/today` 常駐標示，以落檔時間與 TD 設定時間判定」，加上 (iv)「REBALANCE ok 結果在寫鎖內列出受影響的列」。否決 (ii)，不採 (i)。
- **N-209b 能不能在同一次讀取中回傳受影響的列：能，但只能在 N-197a 的寫鎖交易內做。** 現行程式沒有這個交易。建議做成 N-209b 之後的獨立加法 PR（暫稱 N-210a），不再擴大 N-209b。
- **兩點事實修正，交風控：**
  1. 「每檔最多一批」的上限是靠 G1 成立，不是靠 K2。K2 只管同一個預定執行日。
  2. 受影響的列若是輪內末批，差額等於整檔配額在新舊 TD 之間的差，不是每批金額的差。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 交付 A：N-209b 規格補遺（可直接貼上，併入補遺二-4）

````markdown
# ADR-0043 修訂一補遺三（tech-architect 2026-11-10，依 CEO #126（甲）與風控 `work/reviews/2026-11-10-N207N209擬字面前置裁示-風控.md` RC-25、RC-26、RC-27、RC-30、RC-35）

## 補遺三-1：補遺二-4 改寫

- 「若 CEO 採甲（RC-19）」標題改為「**甲案（CEO #126 採用；RC-19、RC-25）**」。
- 「若 CEO 採乙」整段標為「**不採（CEO #126），僅留紀錄**」，N209b-B1～B5 不實作。
- 共通段的「〔TA 新發現，交風控裁示〕現金鍵不存在」子彈刪除，改由下列 N209b-A7 取代。

### N209b-A1′（取代 A1 的 AST 子彈；閘的位置不變）
- AST 測試以 `rebalance` 的 FunctionDef 為對象，依原始碼順序斷言以下各點：
  1. 第一個 `self._store.<name>(...)` 呼叫是 `rule_set_authorship`。
  2. 緊接著的第一個 `If` 節點，條件讀 `.user_authored`，body 以 `Return` 結束。body 內允許的 store 呼叫只有 `portfolio_state`（A2）。
  3. 這個 `If` 之外的下一個 store 呼叫是 `capital_record`。
  4. 緊接著的下一個 `If` 節點，條件讀 `.cash_recorded`，body 以 `Return` 結束，body 內零 store 呼叫。
  5. 常數 `FORBIDDEN_BEFORE_GATES` = {`list_batches`, `_load_symbol_bars`, `_load_index_bars`, `set_total_deploy`, `set_capital`, `set_cash`, `record_directives`}，再加上 N-197a 實際合入的鎖內讀寫方法名。集合中任一名稱的 Call 節點，`lineno` 都必須大於第 4 點那個 `If` 的 `end_lineno`。
  6. 兩個 `Return` 所用的回傳物件建構函式若抽出，必須是模組層級的純函式：AST 斷言函式本體不含 `self` 與任何 store 參照。

### N209b-A2′（補 A2）
- unauthored 的 `warnings == [message]`，比照 insufficient_data（`service.py:1866-1867`）。
- `previous_total_deploy_recorded` 可以由同一次 `portfolio_state()` 讀取的鍵存在性判定；不讀時為 False，畫面不得呈現。

### N209b-A7（RC-25，新增）：現金鍵閘
- **status**：`cash_unrecorded`。字面識別名 `REBALANCE_CASH_UNRECORDED`，不含任何佔位符。
- **store 加法方法** `capital_record() -> CapitalRecord`：
  - 一次 `_state_map()` 讀取，回傳三項：
    - `portfolio: PortfolioState`：與 `portfolio_state()` 由同一個建構函式產生，逐欄相同；
    - `cash_recorded: bool`：`STATE_CASH` 鍵存在；
    - `total_deploy_recorded: bool`：`STATE_TOTAL_DEPLOY` 鍵存在。
  - 定義是「鍵存在」，不是「值不為 0」（同 RC-20）。`portfolio_state()` 的行為與簽名不變。
- **位置**：authorship 閘返回之後、任何 `FORBIDDEN_BEFORE_GATES` 呼叫之前（A1′）。
- **回傳**：
  - `status="cash_unrecorded"`，`executed_at=as_of`；
  - `total_assets`、`new_total_deploy`、`deployed_value`、`overshoot` 都為 None，`directives=[]`；
  - `message = wording.REBALANCE_CASH_UNRECORDED`，`warnings == [message]`；
  - `previous_total_deploy = record.portfolio.total_deploy`（鍵不存在時是代入的 0，畫面不得呈現）；
  - `previous_total_deploy_recorded = record.total_deploy_recorded`；
  - 所有 `*_2f` 與 `written_at_taipei` 都為 None。
- **只檢查一次就足夠的理由（讀碼）**：
  - app/ 內 `STATE_CASH` 的寫入者只有 `set_capital`（`store.py:1050`）與 `set_cash`（`store.py:1097`），兩者都寫 `str(...)`。
  - `_write_state` 只在值為 None 時 DELETE（`store.py:690-694`），沒有任何呼叫者對 `STATE_CASH` 傳 None。
  - 所以鍵一旦存在，就不會在同一次 `rebalance` 後段的 snapshot 或鎖內讀取時消失。
- **守門測試**：AST 掃描 `store.py`，所有以 `STATE_CASH` 為鍵的 dict 字面值，只能出現在 `set_capital`、`set_cash` 兩個函式內，而且值不是 `None` 常數。日後新增寫入或刪除 `STATE_CASH` 的路徑，要回 TA。
- **型別**：`RebalanceResult.status` 的 Literal、API 回應型別、前端 `types.ts` 的 union，三處一律是 `{"ok", "insufficient_data", "superseded", "unauthored", "cash_unrecorded"}`。`superseded` 以 N-197a 實際合入為準。

### N209b-A4′（取代 A4）：F-4 封閉集合
- 封閉集合為 `{ok, insufficient_data, superseded, unauthored, cash_unrecorded}`。
- `unauthored` 與 `cash_unrecorded` 只顯示 `message`：不走 FR-10，不顯示 ok，也不顯示「失敗」。
- 集合以外的值一律走 FR-10。

### N209b-A6′（取代 A6，兩個拒寫分支都適用）
- 以下各點，對 `unauthored` 與 `cash_unrecorded` 分別逐一斷言：
  1. `playbook_state` 全表傾印前後逐位元相同（涵蓋 cash、total_deploy、total_deploy_set_at、total_deploy_source 四鍵）；
  2. `playbook_directives` 列數不變；
  3. `playbook_batches` 全表傾印前後相同；
  4. 個股與指數日線 loader 的 spy 呼叫 0 次；
  5. store spy 的 `list_batches`、`set_total_deploy`、`set_capital`、`set_cash`、`record_directives` 都是 0 次。

### N209b-T1′（取代 N209b-T1）
- **已確認**時，參數化下表：

| # | 現金鍵 | TD 鍵 | 期望 status | `message` 識別名 | `previous_total_deploy_recorded` |
|---|---|---|---|---|---|
| 1 | 存在 | 存在 | ok | `REBALANCE_RESULT` | True |
| 2 | 存在 | 不存在 | ok | `REBALANCE_RESULT_NO_PREVIOUS` | False |
| 3 | 不存在 | 存在 | cash_unrecorded | `REBALANCE_CASH_UNRECORDED` | True |
| 4 | 不存在 | 不存在 | cash_unrecorded | `REBALANCE_CASH_UNRECORDED` | False |

- **附加參數**：
  - 1a：TD 鍵存在、值為 "0" → 同第 1 列。
  - 1b：現金鍵存在、值為 "0" → ok，不是 cash_unrecorded。值為 0 也是紀錄。
  - 3a、4a：同 3、4，另外有一檔持股缺收盤價 → 仍回 cash_unrecorded。用來釘住「現金閘先於資料」。
- 第 4 列以「直接呼叫 `confirm_rule_set`、不呼叫 `set_capital`」建構，對應 `service.py:2021`→`:2030` 之間中斷的情境。
- **T1b**：**未確認** × 上表四種組合 → 全部回 unauthored。用來釘住「authorship 閘先於現金閘」。

### N209b-A5′（取代 A5，以及 2026-11-09 Q3Q4 評估中的 B-1）：B-1 改寫
- **N-209b 不是只做加法。** 變更窮舉如下：
  1. `rebalance` 新增兩個提前返回（unauthored、cash_unrecorded），位於任何批次讀取、日線載入與寫入之前。
  2. status 值域增加兩個值（models、API、前端型別三處）。
  3. ok 分支在 `previous_total_deploy_recorded` 為假時，`message` 改用 `REBALANCE_RESULT_NO_PREVIOUS`。**這是既有分支、既有欄位的值改變。**
  4. store 新增加法方法 `capital_record()`。
  5. 回應新增加法欄位（C2、C3）。
- **既有輸入的行為改變**（窮舉，供 PM 修改 FR-19 與寫 release note）：
  - (a) 未確認：原本回 ok、insufficient_data 或 superseded，並寫入 TD=0。改回 unauthored，零寫入。
  - (b) 已確認、現金鍵不存在：原本回 ok 或 insufficient_data，總資產以 0 代入。改回 cash_unrecorded，零寫入。
  - (c) 已確認、現金鍵存在、TD 鍵不存在、結果為 ok：`message` 的識別名改變。
- **不變的部分（差分測試釘住）**：
  - 輸入落在「已確認、現金鍵存在」時，ok（TD 鍵存在）、insufficient_data、superseded 的既有欄位值逐值不變。
  - insufficient_data 在 TD 鍵不存在時，`message` 也不變（`REBALANCE_BLOCKED` 不含金額）。
- **維持**：
  - `set_total_deploy(` 在 `rebalance` 內恰好出現一次（N197a-T7）；
  - 不重開 N197a-C1；
  - `REBALANCE_RESULT`、`REBALANCE_BLOCKED`、`REBALANCE_OVERSHOOT_WARNING`、`REBALANCE_SUPERSEDED` 字面不改。

### N209b-A8：恢復路徑缺口（RC-25 第 4 點；現況就有，本單不修，列給 CEO）
- **持續狀態怎麼形成**：
  - `confirm_rule_set` 本身就分兩次 commit：先 INSERT 參數列（`store.py:1194-1205`），再寫確認鍵（`:1206-1211`）。
  - 第一次 commit 之後，authorship 就成立，因為參數表計數大於 0（`store.py:1173-1176`）。
  - 之後在 `active_params`（`service.py:2029`）或 `set_capital`（`:2030`）完成之前，若發生例外或行程終止，就會留下「已確認、現金與 TD 都不存在」的狀態（假設先前從未設定過）。
- **畫面上的恢復路徑：沒有。**
  - 資金確認入口只在 `mode === "unconfirmed"` 時渲染（`playbookView.ts:322-324`、`page.tsx:204`）。mode 由 authorship 決定，所以下一次取得 `/today` 之後，入口就消失了。
  - REBALANCE 依 A7 回 cash_unrecorded。
  - 沒有其他資金輸入入口。
  - 偶然路徑：`useConfirmPlaybookRules` 只在成功時 invalidate（`queries.ts:446-454`）。失敗後到下一次 refetch 之前，面板仍在。這時再按一次會走已確認分支，補寫 `set_capital`。這不是設計路徑，不得寫進任何字面。
  - 畫面以外：以 API 重送 `POST /confirm-rules` 會補寫，但依 R-10、RC-32，不得呈現為解開或恢復的方式。要不要寫進 #118 手動說明，由 CEO 與風控決定。
- **使用者在這個狀態下看到什麼**：
  - `/today` 走已確認路徑。現金為 0，`_apply_cash_floor` 的 budget ≤ 0，所有 R1 都被剔除，並附 `SHRINK_TO_ZERO_NOTE`（`engine.py:1043-1060`）。
  - S、P 系列照常評估。
- **連帶缺陷（交風控）**：
  - 這個狀態下若有 open 批次（例如 CEO 依 #117 手動寫入的批次），賣出成交會經 `set_cash(0 + 所得)`（`store.py:1638`）建立現金鍵。
  - 之後 A7 的閘就會放行，REBALANCE 以「只含賣出所得」的現金算出 TD。
  - 「鍵存在」不等於「使用者記錄過現金」。現金鍵沒有自己的來源與時間欄位，現行資料分不出這兩種情況。建議以 §9 P-8 在部署前偵測。
````

**A-4 字面清單（N-209b 合併前必須由風控定稿）**

| # | 識別名 | 出處 | 內容限制 | 備註 |
|---|---|---|---|---|
| 1 | `REBALANCE_UNAUTHORED` | RC-19、N209b-A3、FR-25 | 未執行；沒有寫入任何值；原因是規則集尚未確認；指向「確認規則集並設定資本額」。不得有金額（含 0.00）、「已執行」「重算」、時機建議 | 擬稿前要先有風控對 PM Q-9 的答覆（「重算」二字的禁用範圍） |
| 2 | `REBALANCE_CASH_UNRECORDED` | RC-25、N209b-A7、FR-26 | 未執行；沒有寫入任何值；原因是現金沒有紀錄，無法陳述總資產。不得推測原因、不得有金額、不得有「已執行」「重算」、不得指向畫面上不存在的入口、不得有時機建議 | 擋 N-209b 合併；同樣受 Q-9 影響 |
| 3 | `REBALANCE_RESULT_NO_PREVIOUS` | RC-18、N209b-C5、FR-24 | 不得含 `{previous}`；要寫明「先前沒有紀錄」 | `{assets}`、`{new}`、`{ratio}` 的金額只能經 C4 的單一格式化函式產生 |

- **不屬於 N-209b、改擋 N-209 前端合併的字面**：
  - RC-29 的確認畫面常駐句、ok 結果畫面的加寫句；
  - RC-28 的停用事實句；
  - FR-10 的結果不明句；
  - 入口名稱與入口說明。
- **TA 建議**：RC-29 的兩句不依任何後端值，所以做成 N-209 前端的靜態字面，只在確認畫面與 ok 分支顯示，緊鄰 `message`。這樣 `REBALANCE_RESULT` 不必改，B-1 的 (c) 也不必擴大。若風控要放進後端 `message`，B-1 要再加一項「`REBALANCE_RESULT` 字面改變」。
- **附帶請風控留意**：RC-29 句子「已產生、尚未結算的買進指令……結算時仍以原股數計入帳冊」，對兩種列不為真：
  - 被 G1 擋下的列：claim 被拒，永遠不入帳（`store.py:1544-1555`）；
  - 孤兒列：claim 成功，但帳冊不動（見 B-2）。

  措辭可能要限定為「成交結算時」，或限定為「批次仍待進場者」。由風控決定。

#### 交付 B：風控讀碼推論的確認（可直接貼上）

````markdown
# 風控 2026-11-10 讀碼推論確認（tech-architect 2026-11-10）

## B-1（RC-23）：最新一輪批數與 bpt 不一致的後果
依據：ADR-0043 :134-156 的規格函式（現行 `engine.py:186-215` 是第 1 輪的特例）、`_next_planned_batch`（`engine.py:738-750`）、R1 計算點（`engine.py:982-990`）、鐵律①（`engine.py:1020-1072`）。以下的「位置」指 `batch_no - offset`。第 2 輪以後一律連號；第 1 輪經 §9 STOP-1 確保為 1～n 連號。

**前提事實：planned 估算分支在現有呼叫點走不到。**
- `already` 對 planned 批次以「今日收盤價、現行每批金額」估算（:154）。
- 但 R1 只對該檔最小號的 planned 批次計算股數（`engine.py:738-750`，呼叫於 :775、:839），所以被計算批次之前、同一輪的各批一定都已不是 planned。
- 因此 `already` 實際上是：已成交批次的 `shares`（closed 批次也以原成交股數計入），加上 skipped 批次的 `shares`（= 0，`models.py:219` 的預設值）。
- `service.py:711` 重算的是同一張指令、同一份輸入，結論相同。
- 後果句**不得**依賴「planned 估算」的語意。

**(1) 最新一輪批數 actual < bpt（例如開輪後 bpt 調高）：成立，屬保守方向，但要加限定。**
- 每一批的位置都小於 bpt，沒有任何一批走末批分支，每批都是 `max(1, floor(per_batch / close))`，其中 `per_batch = TD / n_targets / 現行 bpt`。
- 後果有三項：
  - 沒有末批補足；
  - 被跳過批次的金額不會被補回；
  - 每批金額依現行（較大的）bpt 計算，比開輪時小。
- 「投入低於每檔配額」只在「每批金額不小於收盤價」時成立：在評估當下的收盤價與 TD 下，該輪合計不超過配額的 actual/bpt。
- 每批金額小於收盤價時，1 股下限讓每批都買 1 股，合計仍可能超過配額。這是 1 股下限的既有性質，actual 等於 bpt 時同樣存在，與批數不一致無關。後果句不得寫成無條件的「必定低於」。

**(2) 最新一輪批數 actual > bpt（例如開輪後 bpt 調低）：成立，屬不保守方向。**
- 位置 1～bpt−1 依每批金額計算。這時每批金額依較小的 bpt 算，比開輪時大。
- 位置 bpt 走末批分支，以股數補足到 `floor(TD / n_targets / close)` 減去已占用的股數。這是「依當日收盤價、以股數計」的補足。
- **「之後每批至少 1 股」成立，但不是「恰好 1 股」。** 位置 bpt+1 以後每一批都再走一次末批分支，計算股數是 `max(1, floor(配額 / 當日收盤) − 已占用)`：
  - 價格持平或上漲時，通常恰好 1 股；
  - 價格下跌，或前面有批次被跳過（shares = 0）時，會再補足一次，可能多於 1 股。
- **「可能超過每檔配額」成立。** 價格持平、而且前面各批都依計算股數成交時，位置 bpt 成交後股數已達 floor(配額 / 收盤)；再多 1 股，依 floor 的定義，金額就超過配額。所以只要第 bpt+1 批成交，該輪就超過配額。
- 「至少 1 股」是計算股數，之後仍受 R2、R3 與鐵律①剔減，不得寫成「會買進」。

**對字面的限制（交 creative-lead；風控定稿）**
- 方向只依後端給的 `actual` 與 `bpt` 決定。
- 可以寫：
  - 小於時：「沒有末批補足」，以及「各批依現行 bpt 計算」；
  - 大於時：「自第 {bpt} 批起每一批都依整檔配額補足計算，至少 1 股，該輪合計可能超過每檔配額」。
- 不可以寫：
  - 小於時，無條件的「投入必定低於配額」；
  - 大於時，「之後每批只買 1 股」；
  - 任何依賴 planned 估算的句子；
  - 任何建議修改 bpt 的話。

## B-2（RC-26）：`get_batch` 回 None 時的結算（成立）
- **claim**：
  - buy：`BATCH_LEFT_PLANNED_SQL` 是 `EXISTS(... b.status <> 'planned')`（`store.py:279-283`）。找不到批次列時，EXISTS 為假，`NOT` 之後為真，所以 claim 成功（`store.py:1548-1555`）。
  - sell：`action <> 'buy'` 直接成立，同樣 claim 成功。
  - claim 寫入 `settled=1`、`settled_at`、`settled_open_price`、`status`（executed 或 missed），並各自 commit。
- **settle**（`service.py:1656` → `store.py:1580-1653`）：
  - executed：`get_batch` 回 None，於 :1616-1619 執行 `_mark_schedule` 後直接 return。沒有走到 `save_batch`（:1652）與 `set_cash`（buy :1635、sell :1638）。
  - missed：:1610-1612 的 `get_batch` 回 None，不遞增 missed_count；:1613-1615 return。
  - `_mark_schedule` 只 UPDATE `playbook_schedule`。`record_schedule` 在 app/ 內沒有呼叫點，所以這個表通常是空的，UPDATE 影響 0 列。
- **結論**：`playbook_batches` 與 `playbook_state.cash` 都不動；指令列狀態成為 executed 或 missed。
- **使用者面向的後果**：
  - 這一列會被 `settled.append`（`service.py:1663`），計入 `SETTLEMENT_SUMMARY` 的已成交數。
  - buy 不會觸發 W-B3（`:1660` 的 `_batch_of` 回 None）。
  - sell 只有 EMERGENCY 有 N2 揭露，其餘規則完全無聲（TA 2026-11-05 N-177 修正範圍評估 :48）。
- **合入後的範圍**：N-177a 與 ADR-0042 合入後，claim 與動帳併入同一個交易，找不到批次列時仍然不動帳。N-177b（ADR-0041 Decision 10）只另外加上結構化揭露。所以本項在新版之下仍然成立。
- **來源**：這種列只可能來自 app/ 以外的寫入。手動 DELETE 批次列就會產生（`work/reviews/2026-11-08-N208手動換標的操作說明-dev-lead.md:562`）。

### 1d（風控 2026-11-10 RC-26 保留並擴大；取代補遺二-1d）：N-207 規格 乙、§9 表 P-2 列，「盤點項目」欄末尾增列
；另計 `playbook_directives` 中 `settled = 0`、`batch_no` 不為 NULL，而且（`batch_no < 1`，或對應的 (symbol, batch_no) 在 `playbook_batches` 中沒有列）的列數，只回計數。大於 0 → **STOP-1**。理由（風控 2026-11-10 RC-26）：這兩種列都只可能來自 app/ 以外的寫入。前者讓結算失敗（補遺二-1a）；後者讓結算把指令列標為 executed 或 missed，而帳冊與現金都不動（`store.py:1548-1555`、`:1607-1619`），並計入結算摘要的已成交數。

判定 SQL（唯讀；只回一個整數）：
```sql
SELECT COUNT(*) FROM playbook_directives AS d
WHERE d.settled = 0
  AND d.batch_no IS NOT NULL
  AND (d.batch_no < 1
       OR NOT EXISTS (SELECT 1 FROM playbook_batches AS b
                      WHERE b.symbol = d.symbol AND b.batch_no = d.batch_no));
```

〔TA 追加，風控可刪〕1d-2：另計 `settled = 0 AND batch_no IS NULL AND action IN ('buy', 'sell') AND rule_id <> 'S2'` 的列數，大於 0 → **STOP-1**。
- 理由：app/ 內 `batch_no` 為 NULL 的買賣列只有 S2（TA 2026-11-04 N168 釐清七 :59；`engine.py:692-711`）。其他規則的這種列，在 `store.py:1613-1615` 同樣被標為 executed 而不動帳，N-177a 只修 S2。
- S2 的未結算列由 N-177a 的部署閘門處理（ADR-0041 Decision 8），不在本條。
```sql
SELECT COUNT(*) FROM playbook_directives
WHERE settled = 0 AND batch_no IS NULL
  AND action IN ('buy', 'sell') AND rule_id <> 'S2';
```

## B-3（RC-27）：R3、R4 在零命中時的 exit 語意
命令原文見 `work/reviews/2026-11-09-RC7與ADR0043修訂一補遺-tech-architect.md:99-103`。

| 條 | 命令 | 零命中時 | 有命中時 | 非 0 的情形 |
|---|---|---|---|---|
| R3a | `git log --format='%H%x09%s' <M_209>..<base>` | 沒有輸出，exit 0 | 有輸出，exit 0 | 修訂版本解析失敗等錯誤（exit 128） |
| R3b | `git log -i -E --grep='^revert' --format=... <M_209>..<base>` | 沒有輸出，exit 0 | 有輸出，exit 0 | 同上；regex 不合法 |
| R3c | `git log -F --grep=<s> --format=%H <M_209>..<base>` | 沒有輸出，exit 0 | 有輸出，exit 0 | 同上 |
| R4 | `git diff --name-status --diff-filter=D <M_209> <base> -- <路徑>` | 沒有輸出，exit 0 | 有輸出，exit 0（沒有加 `--exit-code` 或 `--quiet`） | 修訂版本解析失敗等錯誤 |

- **結論**：R3、R4 沒有任何一條像 `git grep` 那樣零命中回 exit 1。補遺二-2a 的「exit 不是 0 → BLOCKING」只會在命令出錯時觸發，不會誤擋零命中。
- **條件**：R4 不得加 `--exit-code` 或 `--quiet`；加了以後，有差異時會回 exit 1，語意就改變了。
- **新發現的漏洞**：`git diff` 對兩個 commit 之間的 pathspec，即使路徑不存在也不報錯。錨點路徑打錯字時，R4 會「沒有輸出、exit 0」，等於靜默放行。
- **補強（〔TA 追加，風控可刪〕）**：
  1. R4 的路徑清單與 R5 的對應路徑必須取自同一份錨點登錄的字面。每一條 R4 路徑至少要有一條 R5 regex 指向它。這樣路徑打錯時，R5 會以「沒有輸出、exit 1」判為 BLOCKING。
  2. 每條錨點路徑加跑 `git cat-file -e <M_209>:<路徑>; echo "exit=$?"`，必須是 `exit=0`。這證明該路徑在 `<M_209>` 存在。
  3. 控制組：執行者另跑 `git log -F --grep=0000000000000000000000000000000000000000 --format=%H <M_209>..<base>; echo "exit=$?"`，預期沒有輸出、`exit=0`，原樣記錄。用來實證本表的零命中語意。
- 2a 的「〔TA 追加〕」標記改註「風控 2026-11-10 保留」。

## B-4（RC-30、RC-35）：N-207 規格 乙、§9 表增列
authorship 的判定依 `rule_set_authorship`（`store.py:1164-1176`）：確認鍵存在，或 `playbook_rule_params` 有任何一列，就算已確認。這個判定與日期無關。以下兩項都只回 0 或 1，不回代號；SQL 出錯（例如缺表）時，不得解讀為 0，判讀不了就回 TA。

| 項目 | 盤點項目 | 判定 | 處置 |
|---|---|---|---|
| P-6 | authorship 已確認 × 批次表為空，只回布林值 | 下列 SQL 回 1 為真 | 不是 STOP。結果記入交件紀錄；為真時，CEO 部署通知要寫明「首次設定後，只能經 REBALANCE 解開待生效」（RC-30） |
| P-7 | authorship 未確認 × TD 鍵存在，只回布林值 | 下列 SQL 回 1 為真 | 不是 STOP。結果記入交件紀錄；為真時，部署前回報風控（RC-35） |

```sql
-- P-6
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_batches)
THEN 1 ELSE 0 END;

-- P-7
SELECT CASE WHEN
  NOT (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
       OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND EXISTS (SELECT 1 FROM playbook_state WHERE key = 'total_deploy')
THEN 1 ELSE 0 END;
```

〔TA 建議，風控可刪〕P-8：authorship 已確認 × 現金鍵不存在，只回布林值。為真時，表示正處於補遺三-1 A8 的持續狀態，畫面上沒有恢復路徑。部署前回報風控與 CEO。
```sql
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_state WHERE key = 'cash')
THEN 1 ELSE 0 END;
```
鍵名取自 `store.py:220-233` 的常數值。
````

#### 第三部分：N-210（RC-29）評估

**評估摘要**
- 採用 (iii-a) 常駐標示，加上 (iv) REBALANCE 結果在寫鎖內列出受影響的列。
- 否決 (ii)：它把揭露問題變成帳冊不實。
- 不採 (i)：它會延後調低 TD，等於把同類危害轉移到其他標的；而且會卡住 N-207 唯一的解閘路徑。
- N-209b 能在同一次讀取中回傳受影響的列，前提是在 N-197a 的寫鎖交易內做。建議另開加法 PR（暫稱 N-210a），不擴大 N-209b。

**方案比較**（詳見 ADR 草案的 Options）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) 拒寫 | 帳冊不會有新舊 TD 交錯 | 延後調低 TD；卡住 T-09 的解閘路徑；要排除 G1 列與資料缺口列 | 中 |
| (ii) 結算截股 | 帳冊不超過新上限 | 帳冊與券商實況不符；違反多個 ADR 不變式 | 高（否決） |
| (iii-a) 讀取時判定標示 | 零寫入；涵蓋所有 TD 寫入者 | 方向未知；依賴 set_at 單調遞增 | 低 |
| (iii-b) 落檔戳記 | 標示不會消失 | 指令列多一條 UPDATE 路徑；兩個 TD 寫入者都要打戳 | 中 |
| (iv) 結果列出受影響列 | 決定當下就是精確清單 | 依賴 N-197a 的鎖 | 低 |

**ADR 草案（可直接貼上）**

````markdown
# ADR-0044：stock-desk 排程台 REBALANCE 之後，未結算的 R 系列買進列如何處置

- 狀態：proposed
- 日期：2026-11-10
- 決策者：tech-architect（草案）；risk-compliance-officer（審查，須在 N-207 上線前完成，RC-29）；CEO（決定修正或接受殘留，FR-27）

## Context（背景）
1. 事實（讀碼；風控 RC-29 已核對）：
   - R1 的股數在評估當下，以當時的 TOTAL_DEPLOY 計算（`engine.py:982-988`；ADR-0043 D3 第 5 點）。
   - 指令列落檔之後，決策欄位不再改寫。app/ 內對 `playbook_directives` 的 UPDATE 只有兩處：claim 的結算欄位（`store.py:1550`）與 ADR-0034 的 L4 戳記（`store.py:440`）。ADR-0035 的 N172-C11 明定「不 DELETE、不 UPDATE 既有指令列」。
   - 結算以列上的 `directive.shares` 寫入批次並扣現金（`store.py:1622-1635`）。
   - G1 只擋「批次已非 planned」的列，不重驗 TD（`store.py:279-283`、`:1548-1555`）。
   - `/today` 原樣列出已落檔的列（ADR-0035 Decision 4、N172-C6）。
2. 後果：
   - REBALANCE 調低 TD 之後，已產生、尚未結算的 R1 仍以舊股數成交入帳，`/today` 也一直顯示舊股數。
   - 調高 TD 時方向保守（少買）。
3. 量級（對 RC-29 的事實修正）：
   - 上限來自 G1，不是 K2。K2 只限同一個預定執行日。前一張 R1 還沒結算時，次日評估會對同一批再出一張，但同一批只會成交一次，其餘的列會被 G1 擋下。所以每檔最多一批受影響。
   - 若受影響的是輪內末批，股數為 `floor(TD / n / close) − 已占用`。差額等於整檔配額在新舊 TD 之間的差，不是每批金額的差。
4. 限制：
   - 系統無從得知使用者是否已在券商下單（ADR-0035 R10）；
   - N-207 讓 REBALANCE 成為已確認後唯一的解閘路徑（T-09），使用頻率會上升；
   - 新一輪的 R1 在閘開之後才產生，股數用的是新 TD，不受影響。受影響的是其他標的先前評估留下的 R1。
5. 受影響列的定義：
   - ADR-0034 C-B1 的 `_PENDING_ENTRY_WHERE`（`store.py:288`：`action = 'buy' AND settled = 0 AND status = 'pending'`），而且該 (symbol, batch_no) 的批次列存在、status 為 planned。
   - 被 G1 擋下的列永遠不入帳；孤兒列成交了也不動帳。兩者都不屬於「結算時以原股數計入帳冊」的範圍。

## Options（選項比較）
| 方案 | 內容 | 優點 | 缺點 | 風險 | 與 N172-C11 | 與 ADR-0035（及相關 ADR） |
|---|---|---|---|---|---|---|
| (i) 拒寫 | 有受影響列時，REBALANCE 不寫入，回新 status | 帳冊不會出現新舊 TD 交錯 | (1) 被 G1 擋下的列永遠 `settled=0`（`store.py:1544-1546`），資料缺口的列也會懸置，必須排除，否則 REBALANCE 永久被擋；(2) 延後調低 TD 的期間，其他標的的新 R1 仍以較高的舊 TD 計算，危害只是轉移；(3) 卡住 N-207 唯一的解閘路徑（T-09）；(4) 檢查必須放在 N-197a 的寫鎖內，避免檢查與寫入之間的競態，等於改動 N-197a 的鎖內本體；(5) 又多一個 status 與一句字面 | 中 | 相容（不寫指令列） | 相容，不動 `commit_evaluation`；讀取必須沿用 C-B1 的單一定義（ADR-0034 VETO-2） |
| (ii) 結算截股 | 結算時把股數截在現行 TD 算出的上限內 | 帳冊不超過新上限 | (1) 指令列就是使用者下單的依據，券商成交的是原股數，帳冊截股後會少記持股，S/P 不評估多出的股數，與 ADR-0041 R-6′ 同類；(2) 上限要選價格（開盤或收盤）與輪內脈絡，又多一個定義來源；(3) 截後的股數要落在哪裡：寫回指令列違反 C11；只寫批次，則列、帳冊、券商三方不一致 | 高 | 寫回 `shares` 即違反；不寫回則帳與列不一致 | 違反 ADR-0035 與 ADR-0041 Decision 4 列為仍有效的「C-B6 buy 行為零改動」；ADR-0041 Decision 4 要求改 `settle` 動帳語意必須另立 ADR；動到 ADR-0042 的同一交易 |
| (iii-a) 讀取時判定標示 | `/today` 對受影響列中「落檔時間早於現行 TD 設定時間」者加常駐標示，後端逐列給旗標 | 零寫入；涵蓋所有 TD 寫入者（REBALANCE、API 重送資金確認）；不動任何交易 | (1) 只知道「之後 TD 曾被寫入」，不知道方向，也不知道值有沒有變（沒有 TD 歷史）；(2) 依賴 `total_deploy_set_at` 單調遞增，時鐘倒退時標示可能消失；(3) 評估讀取 TD 到 commit 之間若有 REBALANCE commit，那一列以舊 TD 計算、落檔時間卻較晚，會漏標 | 低 | 相容（只讀） | 相容：不改 Decision 4、N172-C1、C6；set_at 在 logged 與 in-flight 讀取之後才讀，只會多標、不會少標。與 ADR-0034 的關係：風控 D6 要求「以落檔事實判定，不以可覆寫的值反推」；本案的 `created_at` 是落檔事實，`set_at` 雖可覆寫但單調遞增，是否符合 D6 由風控裁示 |
| (iii-b) 落檔戳記 | TD 寫入時，在同一個寫鎖內對受影響列寫入一次性戳記欄位，比照 L4（`store.py:440`） | 標示不依賴可覆寫的值，完全符合 D6 | (1) 指令列多一條 UPDATE 路徑；(2) 兩個 TD 寫入者（`set_total_deploy`、`set_capital`）都要在鎖內打戳，`confirm_rules` 目前不在任何鎖內 | 中 | 字面上衝突，要 ADR-0035 補充明列為第三個例外 | 要改 N-197a 的鎖內本體與 `confirm_rules`；要風控審 |
| (iv) 結果列出受影響列 | 在 N-197a 寫鎖交易內，以同一個常數 SELECT 受影響列（代號、預定執行日、股數），只有 ok 分支回傳 | 寫入當下的精確清單，不會漏列 | 依賴 N-197a 的鎖；沒有該鎖的現行程式做不到「同一次讀取」 | 低 | 相容（只讀） | 相容；N172-C2 類的「持鎖期間零網路」照舊成立 |

## Decision（決策，proposed）
1. **採 (iii-a) + (iv)**。(ii) 否決，(i) 不採。若風控認定 ADR-0034 D6 適用於本案，改採 (iii-b)，並另立 ADR-0035 補充。
2. **單一定義**：在 store 新增常數 `KEPT_PENDING_ENTRY_SQL`，內容為 `_PENDING_ENTRY_WHERE` 加上「批次列存在且 status = 'planned'」。(iii) 與 (iv) 都拼接這個常數，不得另寫。
3. **(iii-a) 判定**：
   - 後端對 `/today` 中每一列符合第 2 點的指令列（包括今日指令表與 in-flight 清單），回傳 `td_rewritten_since_logged: Literal["yes", "no", "unknown"]`。
   - 條件：`parse(total_deploy_set_at) > parse(created_at)` 為 yes。任一方解析失敗時為 unknown。
   - 比較在 Python 內以 datetime 進行，不在 SQL 內比字串。
   - set_at 必須在 logged 與 in-flight 讀取之後才讀，不得更早。
   - 前端不得自行計算，只依旗標顯示。
4. **(iv)**：
   - 在 N-197a 的 REBALANCE 寫鎖交易內，於寫入之前以第 2 點的常數讀取受影響列，依 (symbol, execution_date, id) 排序。
   - 回應加法欄位 `kept_pending_entries: list[KeptEntry] | None`，`KeptEntry = (symbol, execution_date, shares)`。只有 ok 分支有值，其他分支一律為 None，不是 `[]`。
   - 這些列進入 `message` 時，經 RC-20 的單一格式化步驟。
   - 清單為空時，要不要寫「沒有受影響的指令」，由風控裁示。在鎖內讀取的前提下，這句在寫入當下為真；沒有在鎖內讀取時，不得寫這句。
5. **字面**：creative-lead 擬稿，風控逐字定稿。
   - 標示句限於事實：本列在 TOTAL_DEPLOY 最近一次重新設定之前產生；股數依產生當時的值計算；成交結算時以本列股數計入帳冊。
   - 不得寫方向（系統不知道），不得有任何建議或時機提示。unknown 的情況要另擬一句。
6. **範圍與時序**：
   - 實作做成 N-210a（後端）與 N-210b（前端），排在 N-209b 之後，都是加法，不擴大 N-209b。
   - 本 ADR 須在 N-207 上線前經風控審過，再送 CEO 決定修正或接受殘留。

## Consequences（後果）
- 好處：
  - 使用者在下單前讀 `/today` 時，看得到哪些列是在 TD 重設之前產生的；
  - REBALANCE 結果畫面可以具體列出受影響的列；
  - 帳冊語意、結算、指令列都不改。
- 壞處與殘留：
  - **R-a 競態**：評估讀取 TD 之後、commit 之前，若有 REBALANCE commit，那一列以舊 TD 計算，卻不會被標示，也不在 (iv) 清單內。窗口大小沒有量測。修法是在 `commit_evaluation` 鎖內比對評估所用的 TD set_at，屬於 ADR-0035 補充，不在本 ADR。
  - **R-b**：標示不帶方向，TD 調高時也會出現。
  - **R-c**：時鐘倒退時，標示可能消失；`set_at` 無法解析時顯示 unknown。
  - **R-d**：揭露無法撤回使用者已在券商下的單（R10）。
  - **R-e**：`/today` 多一次狀態讀取。
- 被約束的事：
  - (ii) 類「結算時改股數」的方案日後若要重提，必須另立 ADR，並處理 ADR-0041 Decision 4、ADR-0042 與 R10；
  - 第 2 點常數只能有一份；
  - 前端不得自行推斷旗標。
````

**對實作的約束（qa-reviewer 可以逐條檢查）**
- C-N210-1：`KEPT_PENDING_ENTRY_SQL` 只能有一個定義，(iii) 與 (iv) 都拼接它。以 grep 計數釘住。
- C-N210-2：`td_rewritten_since_logged` 由後端計算。前端 grep 不得出現 `created_at` 與 `set_at` 的比較。
- C-N210-3：set_at 的讀取在 logged 與 in-flight 讀取之後。以呼叫順序測試釘住。
- C-N210-4：(iv) 的 SELECT 在 N-197a 的寫鎖交易內、寫入之前執行，持鎖期間零網路呼叫。以 trace 測試釘住。
- C-N210-5：非 ok 分支的 `kept_pending_entries` 為 None。
- C-N210-6：不得 UPDATE `playbook_directives` 的任何新欄位，除非依 (iii-b) 另立 ADR-0035 補充。
- 禁止事項：不得在結算時改變股數；不得以 `pending_directives` 取代 C-B1 的定義。

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - `/home/user/AICompany/work/reviews/2026-11-10-N207N209擬字面前置裁示-風控.md`（全文）
  - `/home/user/AICompany/work/reviews/2026-11-09-N207字面待查與修訂一補遺二-tech-architect.md`（全文）
  - `/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` #126（grep）
  - `/home/user/AICompany/work/reviews/2026-11-09-RC7與ADR0043修訂一補遺-tech-architect.md` :80-130（R1～R5 原文）
  - `/home/user/AICompany/work/reviews/2026-11-09-N209Q3Q4技術評估-tech-architect.md`（grep `set_total_deploy`、B-1）
  - `/home/user/AICompany/work/stock-desk-REBALANCE畫面入口-PRD.md` v1.3 :116-147、:200-279
  - `/home/user/AICompany/docs/adr/0043-…季度窗口.md` :90-189
  - `/home/user/AICompany/docs/adr/0041-…鎖內讀改寫.md` :25-114
  - ADR-0035 :200-262、ADR-0034（grep Decision 與 D6）、ADR-0042（狀態行）、ADR-0001 模板
  - 追蹤清單與歷次評估中與「找不到批次列」、S2 相關的段落（grep）
- **讀過的程式**（只讀，行號依目前工作樹）：
  - `backend/app/playbook/service.py`：:680-729、:1516-1712、:1805-2035
  - `backend/app/playbook/store.py`：:215-290、:690-694（grep）、:703-743、:1000-1110、:1120-1237、:1250-1336、:1500-1684；以 grep 查過 `UPDATE playbook_directives`、`STATE_CASH`、`_set_state` 的所有呼叫點
  - `backend/app/playbook/engine.py`：:150-239、:660-750（grep）、:930-1004、:1020-1080
  - `backend/app/playbook/models.py`：:205-229、:511-528
  - 前端 `playbookView.ts` :300-345、`api.ts` :445-463、`queries.ts` :435-455；grep 過 `confirm-rules` 與 `RuleSetConfirmPanel`
- **沒有查證的部分**：
  - 沒有 Bash，所以 RC-27 的 exit 語意是依 git 的文件化行為推論，沒有實跑。建議以 B-3 的控制組在執行紀錄中實證。
  - RC-23、RC-26、恢復路徑全部是讀碼推論，沒有實跑。
  - 工作樹裡還沒有 N-177a、N-195、N-196、N-197a、N-209b 的程式碼。`settle` 的分析依現行程式；合入後的行為依 ADR-0041 Decision 10 與 ADR-0042 推論。`capital_record`、`set_total_deploy`、N-197a 的鎖內方法名都只是規格名稱。
  - (iii-a) 的 R-a 競態窗口大小沒有量測。
  - `RuleSetResponse` 目前是否帶 TD 的來源欄位，沒有查（與 PM Q-10 有關）。
  - CEO 本機 DB 的 P-2（含 1d）、P-6、P-7、P-8 結果都不明。
- **需要 CEO 親自確認**：A8 的恢復路徑缺口要不要處理（例如補一個已確認後的資金入口），本單不修；N-210 決定修正或接受殘留。

## 四、下一步

1. **risk-compliance-officer**：
   - 確認 RC-23 的更正：「低於配額」的限定條件、「至少 1 股」不等於「恰好 1 股」、不得依賴 planned 估算；確認後 creative-lead 才擬 W-24。
   - 確認 RC-26 的結論與 1d 的 SQL；裁示 1d-2 與 B-3 補強的去留。
   - 裁示 P-8 的去留。
   - 裁示 RC-29 兩句的位置：TA 建議放在 N-209 前端；並判斷句子是否要限定為「成交結算時」。
   - 審 ADR-0044 草案（N-207 上線前），並判定 ADR-0034 D6 是否適用於 (iii-a)。
   - 回答 PM Q-9（擋字面 1、2 的擬稿）與 Q-10。TA 的技術補充：若 RC-35 適用於 N-209，最小的加法是在 `RuleSetResponse` 帶出來源，或沿用乙案 B4 的旗標定義 `not user_authored and total_deploy_recorded`，可以併入 N-209b，但要先查 `RuleSetResponse` 現況。
2. **tech-writer**：把補遺三-1 併入補遺二-4；B-2 的 1d 取代補遺二-1d；B-3 併入 2a；B-4 併入 §9（風控確認後）；ADR-0044 經風控審過後落檔為 proposed。
3. **dev-lead**：
   - N-209b 依 A1′、A2′、A4′、A5′、A6′、A7、T1′、T1b 實作；
   - §9 加入 P-6、P-7 與 1d（加 P-8、1d-2，若風控保留）；
   - 等 ADR-0044 經 CEO 核可後，再開 N-210a 與 N-210b。
4. **creative-lead**：等 Q-9 答覆後，擬 `REBALANCE_UNAUTHORED`、`REBALANCE_CASH_UNRECORDED`、`REBALANCE_RESULT_NO_PREVIOUS`。W-24 等風控確認 B-1 後再擬。
5. **product-manager**：
   - Q-11 改為 `cash_unrecorded`，替換 FR-9、FR-10、FR-26、AC-17、AC-29 的暫稱；
   - FR-19「既有 status 值與字面仍不改」依 B-1 改寫，因為 (c) 會改變既有 ok 的 `message`；
   - FR-26 第 6 點引用 A8。
6. **coordinator**：
   - 把 A8 的恢復路徑缺口與連帶缺陷列給 CEO；
   - N-210 依 ADR-0044 登錄 N-210a 與 N-210b 的時序；
   - P-6、P-7（與 P-8，若採用）的結果記入交件紀錄。

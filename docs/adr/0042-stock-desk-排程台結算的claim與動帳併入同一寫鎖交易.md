# ADR-0042：stock-desk 排程台結算的 claim 與動帳併入同一個寫鎖交易（N-198／N-169F2；補充 ADR-0035、ADR-0041，不取代）

- 狀態：accepted（CEO #111，2026-11-08）
- 註記（依 ADR-0034 補充四 J-10，2026-11-10 CEO #136 核可後生效）：ADR-0034 補充四 J-3 對本檔 N198-C1「engine.py 零 diff」作範圍判定，見 ADR-0043 D3 第 7 點；本檔原文不改。
- 日期：2026-11-07（同日修正版二：回應 [風控-ADR42] R1、R2、R4、S5，以及 [風控-ADR42 回審] R9～R11、S6、S9）
- 決策者：
  - tech-architect：草案、修正版、修正版二；
  - risk-compliance-officer：2026-11-07 審查，CONDITIONAL APPROVE，決策 P1 核可，附 R1～R4；同日回審，CONDITIONAL APPROVE，R1～R4 符合，附 R9～R11；同日再回審（[風控-ADR42 回審二]），CONDITIONAL APPROVE，R9～R11 符合，CEO 通知全文改版；同日第三次回審（[風控-ADR42 回審三]），CONDITIONAL APPROVE，R14 符合，流程名詞對照確認，附 R18。本 ADR 依第三次回審的判定更新；
  - CEO：2026-11-08 核可（決策包 #111）。
- 落檔附記：tech-writer 2026-11-07 依 [風控-ADR42 回審二] 第二節第 4 點落檔；第 3 點 (a)(b)(c) 為依 [風控-ADR42 回審二] 授權替換，第 1 點為只刪字。同日依 [TA-177S] 修訂八與 TA 的 R14～R16 改寫套用 E-1～E-3；E-2 (6b) 兩點依 [風控-ADR42 回審三] 授權插入。
- 來源簡稱（都在 `work/reviews/` 下）：
  - [TA-177S]：`2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`（修訂一 1.3 的 R-α、修訂四第 4 節、修訂六、修訂七、修訂八）；
  - [風控-197]：`2026-11-07-N177修訂四比對與N197裁示-風控.md`；
  - [風控-ADR42]：`2026-11-07-修訂六與ADR0042與N199審查及REBALANCE_SUPERSEDED定稿-風控.md`；
  - [TA-E2]：`2026-11-04-N182解讀點2與3裁示-tech-architect.md`（E-2）；
  - [風控-1104]：`2026-11-04-ADR0039v2回審與N182字面-風控.md`（第 11 點）；
  - [風控-ADR42 回審]：`2026-11-07-ADR0042修正版與N199第5節回審-風控.md`；
  - [風控-ADR42 回審二]：`2026-11-07-ADR0042修正版二與修訂八回審-風控.md`；
  - [風控-ADR42 回審三]：`2026-11-07-R14至R16改寫回審-風控.md`。
- 適用範圍：只有 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 程式位置：主 checkout，N-190 以 3985f4d 合入之後的 tip。只讀、未執行，以內容定位。
- 流程名詞：product 線目前不使用 GitHub PR。本 ADR 中的「PR」「PR 說明」「PR 開出／建立」「PR 分支」「PR head」，依 [TA-177S] 修訂八第 0 節的對照表讀。
- 前提：N-177a、N-177b、N-199 尚未合入。本 ADR 以三者的規格為前提（見「先後與相依」）。

## Context（背景）

1. **現況：claim 與動帳分屬不同交易（F2）。**
   - `claim_directive`（store.py:1531-1555）是一句條件 UPDATE，以自己的連線獨立 commit。G1 的條件也在這一句裡（`BATCH_LEFT_PLANNED_SQL`，store.py:279-283）。
   - `_settle_pending`（service.py:1553 起）對每一列依序執行：
     - claim（:1632）；
     - claim 失敗時，另開連線讀 G1 的拒絕原因（:1635）；
     - N2 的鎖外預讀（:1653）；
     - `settle`（:1656）。
   - `settle` 內：
     - N-177a 的 R-α 之後，每一筆動帳各有自己的 `BEGIN IMMEDIATE`（ADR-0041 Decision 5）；
     - missed 計數是單句 UPDATE；
     - `_mark_schedule` 另開連線（store.py:1663-1678）。
   - claim 與動帳之間沒有任何補償機制。
2. **後果（ADR-0041 R-6′，風控定稿）：**
   - (a) **並發**：某一列已 claim、動帳還沒 commit 時，另一個 `/today` 在 service.py:2199 讀到該批仍是 planned，排程日可能對同一批再出一張 R1 買進指令。
   - (b) **失敗**：claim 之後動帳失敗（例如 `database is locked`、行程終止），該批會停在 planned。之後的排程日，不需要並發也會再出 R1；G1 不會擋，畫面也沒有揭露。
3. **追蹤清單 :382：buy 的 UPDATE 沒有 planned 守衛。**
   - 同一批有兩筆待結算的 buy、而兩個結算並發時，兩邊的 claim 都可能在任一邊動帳之前通過 G1（因為批次仍是 planned）。
   - 結果是兩筆都動帳：現金重複扣款，批次欄位被後寫的一筆覆寫。
   - R-α 的 buy 分支以 `UPDATE ... WHERE symbol = ? AND batch_no = ?` 寫入，沒有檢查 status（[TA-177S] 修訂一 1.3(2) 第 3 點）。
4. **並發從哪裡來（讀碼查證，未實跑）：**
   - 後端的同步 `/today` 在 threadpool 中執行，client 斷線不會讓它停下來：
     - FastAPI 0.139.2 對非 coroutine 端點走 `run_in_threadpool`（`fastapi/routing.py:337-347`），也就是 `anyio.to_thread.run_sync`，`abandon_on_cancel=False`；
     - uvicorn 0.51.0 斷線時只標記 `disconnected`（`h11_impl.py:107-130`、`:464-465`）；
     - 本 app 的三層 middleware（main.py:59-69）都是純 ASGI，不監聽斷線。
   - 前端的 `getPlaybookToday()`（api.ts:437-439）不接 TanStack 的 `signal`。所以 `cancelQueries` 不會中止 fetch，HTTP 請求照樣送完（query-core `query.ts:444-457`）。
   - 會造成兩個 `/today` 在後端並行的前端路徑：
     - **兩個分頁或兩個視窗**：各自有一個 QueryClient，彼此不會去重。
     - **讀取中重新整理**：舊請求照樣跑完，新頁面立刻送出新的請求。
     - **出清的 `onSettled`**（queries.ts:522-525）：`cancelQueries` 之後接 `invalidateQueries`，在途的舊請求不會中止。
       - query 已有資料時，`invalidateQueries` 的 `cancelRefetch` 預設為 true（queryClient.ts:317-319），會靜默取消舊的、立刻發出新的（query.ts:411-413）。
       - 首次載入時，`cancelQueries` 先讓 retryer 進入 rejected，接著的 `fetch` 會重新發出請求（query.ts:404-419）。
       - 兩種情況，後端都會並行。
     - **資金確認的 `onSuccess`**（queries.ts:450-452）：機制相同。但這個按鈕只在尚未確認時出現；在途的舊請求若在確認 commit 之前讀到 authorship，就走 unauthored 路徑、不結算（service.py:2150-2152），所以與 F2 幾乎無關。
   - 不會造成並發的路徑：
     - **視窗 focus**：`refetch({ cancelRefetch: false })`（query.ts:333-336），在途時共用同一個 promise；
     - **`retry: 1`**：在前一次失敗回應之後才重送，後端那一次已經結束；
     - **同頁兩處使用 `usePlaybookToday`**（page.tsx:60、PendingExitBlock.tsx:43）：同一個 key、同一個 QueryClient，會去重。
   - `POST /api/playbook/settle` 也經由 `_settle_pending`，與 `/today` 之間同樣會並發。
5. **限制：**
   - 不新增 `DirectiveStatus`；
   - 不做批次層級 claim；
   - G1 的 SQL 零 diff；
   - 不寫 `missed` 以外的新狀態；
   - 帳冊只在 claim 成功之後才動；
   - C-B6 的 buy 行為零改動（ADR-0035 6′、ADR-0041 Decision 4）；
   - engine 零 diff（C-B11）；
   - 持鎖期間不得有網路 I/O；
   - 唯一的寫入同步機制是 SQLite 寫鎖（排除行程內鎖，理由同 ADR-0041 的 R-β）。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|
| P1：**逐列**單一 `BEGIN IMMEDIATE`：claim、G1 原因讀取、動帳、schedule 標記 | 兩種 R-6′ 變體與 :382 都根治；粒度與 R-α 相同；一列失敗時只回滾那一列，之前已 commit 的列保留；寫鎖只持有到 SQL 結束 | 動到 `_settle_pending` 與 store 的交易邊界；每一次 claim 嘗試多一個短交易；一列失敗會中止本次結算，id 排在後面的到期列這一次不處理；確定性失敗時每次都如此（見 Consequences） | 低 | **採用** |
| P2：整次結算一個 `BEGIN IMMEDIATE` | 整次結算原子；交易數最少 | 一列失敗，整批都回滾，連之前的列也不留，所有結算停擺；N2 與 W-B3 在鎖外讀，看不到交易內的寫入；持鎖時間隨列數增長 | 中 | 否決 |
| P3：claim 之後動帳失敗就補償（把 settled 改回 0） | 交易邊界不動 | 違反「已 claim 的列不會被 unclaim」（`batch_blocking_claim` 的前提）；行程終止時補償不會執行，失敗變體仍在 | 高 | 否決 |
| P4：新增「claiming」中間狀態 | 失敗可以偵測 | 新增 `DirectiveStatus`，被禁止；要改前端與字面 | 高 | 否決 |
| P5：(b-ii) G0 守衛（`commit_evaluation` 不寫同批的 R1） | 不動結算 | 風控已否決作為過渡方案（[風控-197] 4 第 3 點）；失敗變體會變成該批永久停住 | 中 | 否決 |
| P6：service 層的 `threading.Lock` | 簡單 | 只在單一行程內有效；qa 無法以 SQL trace 檢查 | 中 | 否決 |
| P1 的變體：逐列 catch 例外，跳過失敗列繼續 | 其他列照常結算 | 失敗被吞掉，違反 C-11；要另設揭露與字面 | 高 | 否決 |

## Decision（決策）

1. **新的 store 方法 `claim_and_settle`**：唯一的結算進入點，一列一次呼叫。
```python
class ClaimSettle(NamedTuple):
    """What one claim-and-settle transaction did (ADR-0042)."""

    claimed: bool
    #: G1 refused the claim: the status of the batch that is no longer planned.
    refused_by: BatchStatus | None
    #: N-177b's outcome when claimed; None otherwise.
    settled: SettleOutcome | None


def claim_and_settle(
    self, directive_id: int, outcome: Directive, *, open_price: Decimal
) -> ClaimSettle: ...
```
   - 一個連線、一個 `BEGIN IMMEDIATE`，依序執行：
     - (a) claim 的 UPDATE。SQL 只有一份定義：把 `claim_directive` 現行的 SQL 文字，原樣移到模組常數 `_CLAIM_SQL`，並且仍然是由 `BATCH_LEFT_PLANNED_SQL` 拼接而成。`settled_at` 在鎖內取值。
     - (b) rowcount 為 0：在同一個連線執行 `batch_blocking_claim` 的那句 SELECT（模組常數 `_BLOCKING_CLAIM_SQL`，文字逐字不變），然後 `COMMIT`。這時沒有任何寫入。
     - (c) rowcount 為 1：在同一個連線執行 `settle` 的本體 `_settle_on(conn, outcome, fill_price=open_price, directive_id=directive_id)`：
       - S2 → `_settle_s2_fill(conn, …)`；
       - missed → `_count_missed(conn, …)`；
       - executed 逐批 → `_settle_batch_line(conn, …)`；
       - 最後 `_mark_schedule(conn, outcome)`。
       - 這些 helper 都改為接收 conn，自己不再 BEGIN 或 COMMIT，也不另開連線。
     - (d) `COMMIT`。
   - 例外處理：先 `if conn.in_transaction: ROLLBACK`，再原樣 raise（C-11）。
   - `ClaimSettle.settled` 的型別以 N-177b 先合入為前提。改走 N-198 先合入的路線時，依 N198-C9 由 TA 補充改寫。
2. **buy 的 planned 守衛（消除 :382）**
   - 根本上的守衛是 G1：它在同一個寫鎖交易內判定，而 SQLite 同一時間只允許一個寫交易，所以第二筆 buy 的 claim 一定看到已經 open 的批次，被 G1 拒絕。
   - 另加防禦性斷言：`_settle_batch_line` 的 buy 路徑，在鎖內讀到的批次 `status` 必須是 `"planned"`，否則 raise `ClaimInvariantError(RuntimeError)`，整個交易回滾，連 claim 也回滾。
   - 這是 Python 端比對鎖內讀到的值，不是新的 SQL 比較，所以不違反「批次是否 planned 的 SQL 只在 `BATCH_LEFT_PLANNED_SQL`」（ADR-0039 補充 E-3、QB-10）。
3. **`_settle_pending`**
   - 每一列只呼叫一次 `claim_and_settle`，取代現行的 `claim_directive` → `batch_blocking_claim` → `settle` 序列。
   - 依回傳值分流：
     - claimed：進 `settled`；
     - refused_by 不為 None：G1，進 `unsettled`，`refused_by_g1=True`；
     - 兩者皆非：別的請求已處理，`continue`。
   - N2 依 N-177b 改由 `SettleOutcome` 判定（Q-g）。
   - W-B3 的事後讀取（`_batch_of`）不變。
   - **取開盤價的程式段（`series = loaded.get(...)` 到 `if opening is None: ... continue`）零 diff**，維持 ADR-0040 Decision 14 第 3 點的實質要求。
   - 逐列迴圈不 catch `claim_and_settle` 的例外，例外原樣往外拋（C-11）。後果見 Consequences「失敗分兩種」。
4. **保留的公開方法**
   - `claim_directive`、`batch_blocking_claim`、`settle` 保留，供測試與手動重放使用，改為委派到同一份 SQL 與 `_settle_on`。
   - `settle` 自己包一個 `BEGIN IMMEDIATE`。
   - `app/` 內這三者都不得有呼叫點（N198-C3）。
5. **語意**
   - 循序執行：帳冊各欄（`updated_at`、`settled_at` 除外）、現金、schedule、指令列的 `settled`／`status`／`settled_open_price`，都與 N-198 之前逐值相同。
   - 並發：每一列的 claim、動帳與 schedule 一起 commit。任何讀者都看不到「已 claim 但未動帳」的狀態。兩個結算請求的結果，等於依取得寫鎖順序的某一個循序執行。
   - 失敗：
     - 一列在任何一步失敗，那一列的 claim、動帳、schedule 都不會留下；該列維持 `settled=0`／`pending`。
     - 失敗發生在逐列處理中時，例外中止本次 `_settle_pending`：id 比失敗列小、已經 commit 的列保留；id 比它大的到期列，本次不處理（到期列以 `ORDER BY id ASC` 取出，store.py:1528）。
     - 失敗發生在逐列處理之前時（例如讀取到期列時某一列無法解析，store.py:1529 的 `_row_to_pending`），本次沒有任何列結算，也沒有任何列被 claim，包括 id 比該列小的列。
     - 下一次結算會重新判定該列的 G1 與開盤價。重試能不能成功，取決於失敗的性質：暫時性失敗可能成功，確定性失敗每次都會再失敗（見 Consequences）。
6. **約束（qa 逐條檢查，全部 BLOCKING）**
   - **N198-C1**：diff 範圍。
     - store.py 只限：`_CLAIM_SQL`、`_BLOCKING_CLAIM_SQL`、`ClaimSettle`、`ClaimInvariantError`、`claim_and_settle`、`_settle_on`；`_settle_s2_fill`、`_settle_batch_line`、`_count_missed`、`_mark_schedule` 改為接收 conn；`claim_directive`、`batch_blocking_claim`、`settle` 改為委派。
     - service.py 只限 `_settle_pending` 的逐列迴圈。
     - `tests/**`。
     - engine.py、models.py、wording.py、`app/api/**`、`app/data/**`、`scripts/**`、frontend 零 diff。`scripts/**` 零 diff 的意思是：T9 用的偵測工具就是 `<base>` 上 N-199 合入後的版本，N-198 不得修改它。
   - **N198-C2**：`BATCH_LEFT_PLANNED_SQL`、`_insert_directives` 零 diff；`_CLAIM_SQL`、`_BLOCKING_CLAIM_SQL` 與 N-198 之前的 SQL 文字逐字相同（以測試釘住）。
   - **N198-C3**：`app/` 內 `claim_and_settle(` 恰好一處，就在 `_settle_pending`；`claim_directive(`、`batch_blocking_claim(`、store 的 `.settle(` 呼叫點都是 0（AST 判定）。
   - **N198-C4**：交易內的語句序列，依 Decision 1：
     - 從 `BEGIN IMMEDIATE` 開始；
     - 接 claim UPDATE；
     - 接「G1 原因 SELECT」或「動帳語句加上 schedule UPDATE」；
     - 以 `COMMIT` 結束。
     - 持鎖期間不另開連線，沒有網路，也不呼叫會另開連線的 `self.*`。
   - **N198-C5**：股數與 cash 的寫入者仍然只有 `_settle_s2_fill`、`_settle_batch_line`（經由 `_add_cash`），名稱不變（N177a-T19 照舊通過）；不新增寫入路徑。
   - **N198-C6**：Decision 2 的斷言存在，失敗時整個交易回滾。
   - **N198-C7**：以 merge commit 合入。base 與先後順序，依 [TA-177S] 修訂六第 1 節、修訂七與修訂八的方法驗證。N-198 的代入值如下：
     - 前置單有三張。`<M_1>`、`<M_2>`、`<M_3>` 分別是 N-177a、N-177b、N-199 在 product 上的 merge commit，都是完整 40 碼。
     - (i)、(ii) 的指令區塊，在 `<M_2>` 那一行之後追加一行：`git merge-base --is-ancestor <M_3> <base>; echo "exit=$?"`。修訂六 1.5 第 3 點，對 N-198 讀為「兩份紀錄中，三條 `--is-ancestor` 都是 `exit=0`」。
     - 1.6 的旁證，N-198 要跑三份 diff。判準同修訂六 1.6：某個錨點出現在 `-` 行，而同一份 diff 沒有任何 `+` 行含同一個錨點，旁證就不成立。
       - `git diff <M_1> <base> -- apps/stock-desk/backend/app/playbook/store.py`：錨點是 `_settle_batch_line`、`_settle_s2_fill` 的定義，regex 同修訂六 1.6 表；
       - `git diff <M_2> <base> -- apps/stock-desk/backend/app/playbook/`：錨點是 `SettleOutcome` 的定義。名稱以 N-177b 實際合入的為準，不同時回 TA；
       - `git diff <M_3> <base> -- apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`：錨點是 N-199 的四個 SQL 常數定義行。
       - 後兩者的 regex，`|` 是 regex 的交替，不是字面：
```
^[-+]\s*class SettleOutcome\b
^[-+]N199_(FILL_NOT_BOOKED|SAME_BATCH_BLOCKED|MULTI_EXECUTED_BUY|BATCH_BUYS)_SQL\s*=
```
     - 合入前 merge 最新 product，之後重跑完整 CI 與 seam golden。
     - 本條是預設路線（N-177b 先合入）的寫法。改走 N-198 先合入時，`<M_2>` 與第二份 diff 只能由 N198-C9 的 TA 補充改寫。N198-C9 (b) 各項成立之前，本條照上文判定，也就是 base 不含 N-177b 就判 BLOCKING。
   - **N198-C8**：既有測試的修改只限以下三類，並逐條列在 PR 說明交 qa 判定：
     - (i) N177a-T9、T29「該列維持 `settled=1`／executed（F2 殘留）」的斷言，改為「該列維持 `settled=0`／`pending`，claim 已回滾」；
     - (ii) N177a-T28 與 `test_playbook_same_day_race.py::_writes_inside`、同檔 T14 中以「第一個或唯一一個 `BEGIN IMMEDIATE`」取交易的斷言：`/today` 的 `BEGIN IMMEDIATE` 數，改為 1 加上本次「有開盤價的到期列」數，包括 taken、G1、missed；
     - (iii) 直接呼叫 `claim_directive` 再呼叫 `settle` 的既有測試照舊通過，不得改寫。
   - **N198-C9（合入路線）**：
     - 預設路線：N-177b 在 N-198 之前合入，C7 照上文。
     - N-198 先合入的路線，以下 (a)～(c) 全部成立才可以走：
       - (a) TA 出補充，內容至少包括：
         - Q-g、N177b-C6／C9 改為從 `claim_and_settle` 的回傳取值；
         - N-177b 合入之前 `ClaimSettle.settled` 的型別與取值；
         - C7 的 `<M_2>` 與第二份 diff 的改寫。
       - (b) 補充送達風控，以及風控對補充的審查紀錄，都必須早於 N-198 送審，不得事後補。「送審」依 [TA-177S] 修訂八第 0 節，指該版交件紀錄首次出現在 `origin/product/stock-desk` 上。舉證方式如下，全部都要成立（[風控-ADR42 回審] R10；[風控-ADR42 回審二] R14）：
         - (1) 風控對該補充的審查紀錄，在 N-198 送審之前已經存在於 `work/reviews/`，而且在 (ii) 讀取當下，在 `refs/remotes/origin/product/stock-desk` 上可達。也就是說，(c) 的「審查紀錄存在」提前到送審之前。（「已 push」依 [風控-ADR42 回審二] 第二節第 2 點 (3) 降為「讀取當下可達」。）
         - (2) N-198 的交件紀錄在**首版**就要列出三個路徑：補充、coordinator 的送審紀錄、風控的審查紀錄；另外要列出 (6) 的 `<R>`，寫完整 40 碼。qa 依交件紀錄路徑在 `origin/product/stock-desk` 上的 git 歷史判定：這些引用若是首版之後才補上的，就判 BLOCKING。
         - (3) 送審紀錄要記到分鐘，並註明時區（Asia/Taipei）。
         - (4) 先後無法確立，就判 BLOCKING。例如：只有日期、時區不明、紀錄缺漏，或任一條指令沒有原文、沒有完整輸出、沒有 `exit=` 行。
         - (5) 風控在 risk-gate 核對 (1)～(3) 與 (6) 的紀錄。
         - (6) 以內容雜湊確立先後。現行流程沒有 PR，所以不以 PR 建立時間為錨點。
           - 名詞：
             - `<R>`：風控審查紀錄所在的 commit，完整 40 碼，由交件紀錄首版列出。
             - `<D>`：交件紀錄路徑首次出現在 `origin/product/stock-desk` 的那個 commit，完整 40 碼。
             - `<head>`：同 [TA-177S] 修訂六 1.1。
           - (6a) 證明 `<R>` 的 tree 含有三份紀錄：
             - 原樣貼出 `<R>` 的 tree 中，(2) 列出的三個路徑各自的項目，包括 blob 雜湊。
             - 任一路徑不在 `<R>` 的 tree 中，就判 BLOCKING。
           - (6b) 證明紀錄沒有事後改寫：
             - 同一份紀錄再貼出這三個路徑在 (ii) 讀取當下、`refs/remotes/origin/product/stock-desk` 版本的 blob 雜湊。
             - 任一路徑的兩個雜湊不同，就判 BLOCKING：這表示該紀錄在 `<R>` 之後被改寫過。
             - 因此這三份紀錄在 `<R>` 之後都不得再修改，coordinator 的補記也一樣，要補記就另開檔案。
             - coordinator 的送審紀錄必須是本次送審專用的獨立檔案，不得是會持續更新的檔案（例如追蹤清單）。
             - (a) 的 TA 補充同樣必須是獨立檔案，不得是會持續追加修訂的規格檔（例如 [TA-177S]）。日後要併入規格檔，只能以引用方式併入，原檔不動。
             - 任一路徑在讀取當下的 `refs/remotes/origin/product/stock-desk` 中不存在，同樣判 BLOCKING。
           - (6c) 證明 `<R>` 在 product 上可達：
             - `git merge-base --is-ancestor <R> refs/remotes/origin/product/stock-desk`，結果必須是 `exit=0`。
             - 另外貼出 `git ls-remote origin refs/heads/product/stock-desk` 的輸出。它的值必須等於讀取當下本機 `refs/remotes/origin/product/stock-desk` 的值；不等就重做 (6c)。
             - 只接受 `product/stock-desk`。審查紀錄在產品線上；`main` 依 CLAUDE.md §1 不放產品內容，不適用。
           - (6d) 證明 `<R>` 早於送審，也早於受審對象：
             - `git merge-base --is-ancestor <R> <D>`，結果必須是 `exit=0`；
             - `git merge-base --is-ancestor <R> <head>`，結果必須是 `exit=0`。
             - 理由：commit SHA 由內容與 parent 決定，以 `<R>` 為祖先的 commit，不可能在 `<R>` 之前算出來。qa 審的就是 `<head>`（[TA-177S] 修訂八第 1 節，四個值相等），所以 qa 的審查必然晚於這份審查紀錄。
             - 第二條實際上要求：N-198 分支在送審之前，已經 merge 過含有 `<R>` 的 product。這和 C7「合入前 merge 最新 product」同方向，不會延後開工。
           - (6e) 交件紀錄的歷史：
             - 貼出交件紀錄路徑在 `origin/product/stock-desk` 上的完整 commit 歷史，每一筆都寫完整 40 碼，並貼出首版之後每一筆對該檔的 diff。歷史只有一筆，就表示「沒有任何編輯」。
             - 依 [TA-177S] 修訂六 1.7 重新送審時，每一版新的交件紀錄都各自適用 (2) 與 (6d)。
           - 時間的交叉核對：
             - 送審紀錄所載的送達時間（到分鐘，Asia/Taipei），必須早於 coordinator 派工紀錄所載「N-198 送 qa 審查」的時間所在的那一分鐘。落在同一分鐘或更晚，依 (4) 判 BLOCKING。
             - 這兩個時間都由 coordinator 記錄，只用來抓出錯誤，不是先後的主要證據；主要證據是 (6d)。
           - 執行與判斷分離（ADR-0007）：
             - qa-reviewer 的工具是 Read、Grep、Glob、`codex`、`git diff`，不為此新增工具。
             - (6a)～(6e) 由 [TA-177S] 修訂六 1.3 (ii) 的執行者執行。指令原文與完整輸出原樣記入 `work/reviews/` 的本案審查紀錄，每條都附 `exit=` 行，並記錄讀取時間（到分鐘，Asia/Taipei）。
             - 只用唯讀的 git 查詢，實際指令由 devops-sre 指定；本 ADR 只訂要證明的事。
             - 獨立性依 [TA-177S] 修訂八第 2 節，以角色判定。
             - qa 與風控讀這份紀錄判定。
           - 殘留：
             - 證明不了 push 的時點，只證明 `<R>` 早於 `<D>` 與 `<head>`，而且讀取當下在 product 上可達。這一項 [風控-ADR42 回審二] 第二節第 2 點 (3) 已接受。
             - `<D>` 何時 push、qa 何時被派工，都由 coordinator 記錄，git 證明不了。(6d) 的第二條不受影響。
             - `product/stock-desk` 禁止 force push 是公司規範；伺服器端有沒有強制，待 devops-sre 書面查證。沒有強制時，(6c) 只證明讀取當下可達。
             - qa 無法親自重現，與 [TA-177S] 修訂六 1.8 的殘留相同。
       - (c) (1) 的審查紀錄不是 VETO，而且其 required 在 N-198 合入之前已經處理。
     - N-177b 延誤，不構成 N-198 延到第三包之後的理由（見「先後與相依」第 5 點）。
7. **測試（全部 BLOCKING；用真實 `PlaybookStore`、檔案型 DB）**
   - **N198-T1（R-6′ 並發變體）**：
     - 設定：B 的 `claim_and_settle` 在 claim UPDATE 之後、動帳之前執行 hook；hook 另開執行緒跑 A 的 `evaluate_today`，最多等 0.5 秒後放行 B，最後 join A。
     - 斷言：A 沒有對 (s, k) 寫入 R1；排程日只對 k+1 出單；任何時刻都讀不到「r 是 `settled=1`，而 k 是 planned」。
     - 效力證明：PR 說明附本機輸出，顯示換回 N-198 之前的序列時本測試失敗。這份對照不 commit。
   - **N198-T2（失敗變體）**：分別對 `_add_cash`、batch UPDATE、`_mark_schedule` 注入例外。
     - (i) 斷言：該列 `settled=0`／`pending`；批次、現金、schedule 都不變；例外原樣拋出；沒有留下未結束的交易。
     - (ii) 下一次結算正常完成，而且只動帳一次。
     - (iii) 同一次結算中有三筆到期列，對中間那一列注入例外。斷言：id 較小的那一列已經 commit；id 較大的那一列仍是 `settled=0`／`pending`，帳冊沒有動。這一項把 Decision 5 的中止語意釘住。
     - (iv) 同一次結算中，被解析的到期列前後都還有到期列，對其中一列的解析（`_row_to_pending`）注入例外。斷言：例外原樣拋出；所有到期列都仍是 `settled=0`／`pending`；批次、現金、schedule 都不變。這一項釘住 Decision 5「失敗發生在逐列處理之前」的語意；pending 的讀取與解析不得因 N-198 移進逐列迴圈（N198-C1 本來就不允許改 `pending_directives`）。
   - **N198-T3（:382）**：同一批有兩筆待結算 buy。A 在 claim 之後執行 hook，另開執行緒跑 B 的 `claim_and_settle`。
     - 斷言：現金只扣一次；批次的值來自 A 那一筆；B 被 G1 拒絕。
     - 效力證明同 T1。
   - **N198-T4**：SQL trace，依 C4；並以 connection factory 計數，確認交易期間沒有開第二個連線。
   - **N198-T5（循序等價）**：固定 seed，至少 300 組，以測試檔內的 N-198 之前參考實作比對，依 Decision 5 的循序條款。
   - **N198-T6**：AST，依 C3。
   - **N198-T7**：Decision 2 的斷言：對已經 open 的批次直接呼叫 buy 路徑，會 raise，而且 claim 也回滾。
   - **N198-T8**：C2 的 SQL 文字逐字比對。
   - **N198-T9**：N-199 偵測工具對 T1～T3 產生的 DB 執行，N199-A、N199-B、N199-C 都是 0 筆。工具必須取自 `<base>` 上 N-199 合入後的版本（C1、C7）。

## Consequences（後果）

- 好處：
  - R-6′ 的兩種變體，對 N-198 部署之後才 claim 的列都消除：
    - 並發時，讀者只看得到 claim 之前或動帳之後的狀態；
    - 失敗時，claim 不會留下。
  - :382 的重複扣款消除（Decision 2）。
  - ADR-0041 Consequences「claim 之後若當機，會留下『executed 但沒有稽核』的列」：
    - 對 N-198 部署之後才 claim 的列不再發生。claim 之後任一步失敗或行程終止時，claim 與動帳都不會留下。
    - N-198 部署之前已被 claim 的列仍適用，以 N-199 事後檢查（見 ADR-0041:114 補註）。
  - missed 計數與 schedule 標記，和 claim 一起成為原子操作。
- 壞處與代價：
  - **E-2（追蹤清單 :314）不消除。**
    - E-2 的窗口在本請求的 `read_in_flight`（service.py:2157）與 `commit_evaluation`（:2222）之間：另一個請求的整筆結算在這段時間內 commit。N-198 只改另一個請求內部的交易邊界，不改本請求的讀取時點。
    - E-2 的前提是「同一批有不只一筆待結算買進」。這個前提的來源有：R-6′ 的兩種變體、跨日重發（ADR-0035 V4）、N-172a 之前的重複。N-198 只拿掉第一項。**E-2 的前提少了 R-6′ 這一個來源；實際頻率未量測。**
    - 殘留仍歸 N-169，修法方向維持風控同意的 (iv)：把 `read_in_flight` 移到 commit 之後（[風控-1104] 第 11 點 (d)）。本 ADR 不處理。追蹤清單 :314 已註明 E-2 不因 N-198（F2）合入而結案（[風控-ADR42] R5）。
  - **失敗分兩種，後果不同（Decision 5）：**
    - **暫時性失敗**，例如超過 busy_timeout（5 秒）的 `database is locked`、行程終止：
      - 依 C-11 失敗，該列不留任何痕跡；
      - 下一次結算重新判定，可能成功。
    - **確定性失敗**，例如 Decision 2 的 `ClaimInvariantError`、資料格式錯誤，重試也不會成功：
      - 失敗的那一列（或無法解析的那一列）每一次都留在 pending；已確認規則集時，每一次 `/today` 都依 C-11 失敗。
      - **確定性失敗會讓每一次今日頁面讀取都失敗，期間不會顯示任何指令，包括停損停利。**
      - 直到修好為止，今日頁面持續無法使用；S/P 系列的賣出指令也不會出現。
    - 讀碼事實（TA 讀碼，風控在 [風控-ADR42 回審] 第二節第 1 點核對；都只讀、未執行；適用範圍依該審查的 R9）：
      - `_settle_pending` 在評估之前執行（service.py:2153），例外會往外拋，所以評估與 `commit_evaluation` 都不會執行，`/today` 這段期間也不會寫入新的指令列（「全部出清」另計，見下）。
      - 已確認規則集時，`/today`（service.py:2150-2153）與 `POST /api/playbook/settle`（`settle_on_request`，service.py:1524-1551）都經由同一個 `_settle_pending`，所以同樣每一次都失敗。未確認規則集時，兩者都不結算，直接回傳。
      - 到期列以 `ORDER BY id ASC` 取出（store.py:1528）；逐列迴圈（service.py:1611-1665）沒有 try/except，例外會中止整次結算。
        - 失敗發生在逐列處理中時：
          - id 比失敗列小的列，各自 commit 之後保留；
          - id 比它大的到期列每一次都輪不到，修好之前都不會結算。這包括這段期間由「全部出清」寫入的出清賣出列。
          - `playbook_directives.id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`（store.py:135），id 不重用、只增不減，所以停擺期間寫入的出清列，id 一定比失敗列大。出清列的執行日是下一個交易日（service.py:2329），到期之後就排在失敗列後面。
        - 失敗發生在逐列處理之前時（例如讀取到期列時某一列無法解析，store.py:1529）：本次沒有任何列結算，包括 id 比該列小的列。
      - 「全部出清」（`emergency_exit`，service.py:2288 起）不經過 `_settle_pending`，所以不會因為結算失敗而無法送出。
        - 但如果確定性失敗的原因也出現在出清讀取的資料中（例如批次列），出清同樣會失敗。
        - 出清寫入的賣出列，要等結算恢復之後才會記入帳冊。
      - 出清只替帳冊上已 open 的批次寫賣出列（`classify_exit_batches`，service.py:358）。
        - 停擺期間到期、但尚未記入帳冊的買進列，它的批次在帳冊上仍是 planned，出清不會替它寫賣出列。
        - 出清會在同一寫鎖內讀出這類待成交買單（`ExitEntryRead`，store.py:404-418；ADR-0034 Decision 2），交給回應組字（service.py:2343-2348）。回應字面未逐字核對。
        - 這是既有行為；停擺會讓它一直持續到結算恢復。
    - 這是行為變更：
      - N-198 之前：claim 已經留下，同樣的錯誤只失敗一次，之後就被靜默吞掉（帳冊少記）。
      - N-198 之後：從「隱藏的帳冊落差」變成「看得見、但會持續的停擺」。
      - 風控已接受這個方向，理由是不再隱藏（[風控-ADR42] 第 2(e) 點）。
      - 不採「跳過失敗列、繼續處理後面的列」：那會讓失敗變成靜默，違反 C-11。
  - `/today` 的 `BEGIN IMMEDIATE` 數，變成 1 加上有開盤價的到期列數。寫鎖競爭的次數增加，但每一次都只持有到 SQL 結束。超過 busy_timeout（5 秒）時，依 C-11 以 `database is locked` 失敗，而且那一列不留任何痕跡；之後的行為依上一點的暫時性失敗。
  - schedule 標記失敗時，現在會連同 claim 與動帳一起回滾。以前是 claim 與動帳留下、schedule 沒標。這是行為變更，方向是保守的。之後的行為依「失敗分兩種」：暫時性的，下一次重新判定；確定性的，持續停擺，直到修好。
  - 一列 commit 之後，若 `_settle_pending` 的後段失敗（例如字面組裝），帳冊是一致的，但那一次的回應沒有送達；下一次 `/today` 不會再把這些列列為本次結算。這是既有行為，不是本 ADR 新引入的。
  - N-198 部署之前寫入的資料，仍可能帶著 R-6′ 的痕跡，由 N-199 的偵測工具事後檢查。
- 被約束：
  - `app/` 內結算的唯一進入點是 `claim_and_settle`。新增任何會 claim 或會動帳的呼叫點，要回 TA 與風控。
  - ADR-0041「被約束」中「只能放在 `settle` 的私有 helper 內，並在單一 `BEGIN IMMEDIATE` 內讀改寫」，讀為「`settle` 或 `claim_and_settle` 的私有 helper，在呼叫者持有的單一 `BEGIN IMMEDIATE` 內讀改寫」。
  - 日後改動結算的交易邊界，或改動逐列迴圈對例外的處理方式，依 ADR-0041 Decision 4，另立 ADR 並送風控。

## 與其他 ADR 的關係
- **ADR-0035**：補充，不取代，原文不改。
  - Decision 6′ 的「G1 判斷與 claim 原子化」維持，G1 的 SQL 零 diff。
  - 6′ 的殘留風險與 Consequences「F2 並發窗口仍在」，由本 ADR 消除。
  - 「不做批次層級 claim」維持：仍是逐列 claim。
- **ADR-0041**：補充，不取代。
  - Decision 4 列出的不變式全部維持：「帳冊只在 claim 成功之後才動」加強為「與 claim 同一交易」。
  - Decision 5 的 R-α 是本 ADR 的前提：本 ADR 把它的交易邊界往外擴到 claim。
  - R-6′ 的「已修正」註記，照風控逐字：「R-6′ 由 N-169F2 修正：claim 與動帳在同一交易內 commit。」N-198 以 merge commit 合入 product 之後才落檔；CEO 內部通知（N-197 (b)）維持到 N-198 **部署**為止。
  - Consequences「claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169）…判定為未動帳（多報方向）」那一點（ADR-0041:114），加上以下補註。補註依 [風控-ADR42] 第 2(b) 點的定稿，逐字照錄：
    - 落檔時點：N-198 以 merge commit 合入 product 之後，時點比照 R-6′ 的已修正註記；
    - CEO 通知維持到 N-198 部署為止。
    - 「補註：本點由 ADR-0042（N-198）修正：claim 與動帳在同一交易內 commit，claim 之後任一步失敗或行程終止時，claim 與動帳都不會留下。本點，以及 R-6′ 對本點「判定為未動帳（多報方向）」適用範圍的說明，仍適用於 N-198 部署之前已被 claim 的列；這些列以 N-199 偵測回溯工具事後檢查。」
- **ADR-0040**：原文不改。
  - Decision 14 第 1 點：不涉及。
  - 第 2 點：不新增寫入路徑（C5）。
  - 第 3 點「`_settle_pending` 零 diff」：與 ADR-0041 對第 2 點的判定相同，適用對象是 ADR-0040／N-190 的 build；N-177b 也已經改動 `_settle_pending`（ADR-0041 Decision 10）。實質要求「不得改取開盤價的方式」維持，由 Decision 3 的零 diff 段守住，qa 逐 hunk 檢查。
  - 第 4 點：不涉及。
- **N177a-C2**：`claim_directive`、`batch_blocking_claim` 零 diff，是 N-177a PR 的範圍約束，不追溯到後續單。
  - N-198 改的是委派方式，SQL 文字逐字不變（C2）。
  - `BATCH_LEFT_PLANNED_SQL`、`_insert_directives` 仍然零 diff。
- **ADR-0034**：C-B6 的行為不變，由 T5 的差分測試與 N-168 既有測試守住。C-B11 維持（engine 零 diff）。
- **ADR-0039**：群組 B 的讀取時點不變；N-171 區塊不受影響。
- 本 ADR 不取代任何 ADR。

## 先後與相依
1. **N-177a（R-α）必須先合入**，沒有例外。本 ADR 改的是 R-α 各個 helper 的交易歸屬。N-198 的 PR 要在 N-177a 合入 product 之後才開。release 位置照 ADR-0040 Decision 13：N-177a 是 N-190 之後的下一個 release。
2. **N-177b 預設先合入。**
   - 兩者都改 `_settle_pending`，也都動 `settle` 的回傳（`SettleOutcome`）。
   - 若 N-177b 在第三包凍結前趕不上，N-198 可以先合入，但要依 N198-C9 處理：
     - TA 出補充：Q-g、N177b-C6／C9 改為從 `claim_and_settle` 的回傳取值；N-177b 合入之前 `ClaimSettle.settled` 的型別；一併修改 N198-C7 的 `<M_2>` 與第二份 diff。
     - 這份補充必須在 **N-198 送審之前**送到風控。風控對它的審查紀錄，也要在送審之前已經存在，並在 `origin/product/stock-desk` 上可達，不得事後補。「送審」的定義與舉證都依 N198-C9 (b)。這只會延後送審的時間：N-198 分支要先 merge 含有該審查紀錄的 product。不會延後合入（[風控-ADR42 回審] 第二節第 1 點）。
   - N-177b 延誤，不構成 N-198 延期的理由（第 5 點）。
3. **N-195、N-196、N-197a**：沒有邏輯相依（REBALANCE 路徑）；都會動到 store.py，依 C7 merge 最新 product 即可。
4. **N-199：N-198 相依於 N-199。**
   - N-199 必須在 N-198 合入之前，已經以 merge commit 合入 product。
   - N198-T9 要用 N-199 的工具；N198-C7 以 `<M_3>` 驗證 ancestry。
   - 依風控的排程，dev-lead 在 N-177a、N-199（以及預設的 N-177b）都合入之後，才開工 N-198。
   - N-199 的期限是 R2，比第三包早，所以 N-198 不會因此延後。
   - N-198 部署之後，再跑一次 N-199（N-199 spec 第 5 節）。
5. **期限**（[風控-197] 第二節第 4 點第 2 項；[風控-ADR42] R4）：
   - 實作最遲與第三包同一個 release。
   - 趕不上時，在第三包凍結前回報風控並附理由。
   - 要延期，需要 CEO 書面同意；風控會書面保留不同意見。
   - N-177b 延誤，不構成 N-198 延到第三包之後的理由；這種情況改走第 2 點與 N198-C9 的路線。
6. **N-198 部署時通知 CEO**（[風控-ADR42 回審] 第二節第 3 點、R11；全文依 [風控-ADR42 回審二] 第二節第 3 點改版）：
   - N-198 部署時，coordinator 依 [風控-ADR42 回審二] 第二節第 3 點，**逐字**送出 CEO 通知；部署之前不得送。[風控-ADR42 回審] 第二節第 3 點的舊版全文作廢，不得送出。
   - 送達時點、確認 CEO 收到、授權範圍（只准刪字，不准改寫），都以 [風控-ADR42 回審二] 該點為準。本 ADR 不轉錄通知全文。
   - 這是新送的一則，不撤回 N-197 (b) 的兩則通知。
   - 部署之前，coordinator 先核對該點「授權範圍」列出的各項事實和要部署的版本一致。不一致時回風控；風控回覆之前，不部署 N-198。

## 待決
- 無。CEO 已於 2026-11-08 核可（#111）。

# ADR-0042 修正版、N-199 spec 第 5 節修正版、修訂七

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：ADR-0042 修正版、N-199 spec 第 5 節修正版、S1～S5 評估（修訂七）

## 一、本次結論

- **ADR-0042 修正版全文**附在第二節區塊一。改了以下幾處：
  - **R1**：N-199 必須在 N-198 合入之前已經在 product 上。N198-C7 改為三個前置單的 ancestry 驗證，`<M_3>` 就是 N-199。「先後與相依」第 4 點原本寫「不相依」，和 T9 矛盾，已改正。
  - **R2**：Consequences 逐字寫入風控要求的那句揭露。我讀碼時另外查到三件事，標成 [TA 補，待風控確認]：
    - 到期列以 `ORDER BY id ASC` 處理，例外會中止迴圈。所以發生確定性失敗時，id 排在失敗列後面的到期列一律不會結算，包括這段期間「全部出清」寫入的出清列。
    - `/settle` 同樣會失敗。
    - 「全部出清」本身不經過結算，仍然可以送出。
  - **原稿有兩處說法不正確，一併修正**：P1 的優點原本寫「一列失敗只影響那一列」，Consequences 原本寫「那一列下次重試」。事實是：失敗會中止整次結算，而確定性失敗會一直重複。
  - **R4**：新增 N198-C9（路線約束）。若改走 N-198 先合入，TA 補充必須在 N-198 的 PR 開出之前送達風控，並一併改寫 C7。N-177b 延誤不構成延期理由，已寫進第 5 點。
  - **R3**：ADR-0041:114 的補註改用風控定稿，逐字照錄。落檔時點是 N-198 以 merge commit 合入之後。
  - **S5：採用**，改成事實陳述。
  - 修改索引 F1～F18 附在區塊一之後。
- **N-199 spec 第 5 節修正版**附在第二節區塊二。R7、R8 都逐字寫入。另有三處 [TA 補]，都待風控確認：
  - **stdout 要多印四行**：分別是腳本雜湊、DB 前後雜湊、執行時間（改第 3 節）。R7 之後任何 agent 都不能讀報告檔，而 `work/` 要記錄的雜湊與執行時間，目前的 stdout 沒有印（`n177_n190_backtrack_probe.py:1931-1934`）。
  - **R7 的讀檔禁令限縮範圍**：只限對 production 複本產生的報告。否則 data-engineer 與 qa 連測試產生的報告都不能讀。
  - **更正一項事實**：原稿說「N-198 部署之後 N199-C 不再新增」，這不對。部署前已命中 N199-A、批次仍是 planned 的資料，之後同批 R1 若成交，部署後仍會新增 N199-C 的列。
  - R6 的配套修改（第 2 節註解、QB-5）放在同一區塊。
- **S1～S4 評估結果：**
  - S1、S2 採用，寫成修訂七，見第二節區塊三。
  - S4 採用為「另開單」，登錄在修訂七，不在 N-197a 範圍。
  - S3 不採用，理由見第二節，並在修訂七登錄重啟條件。
- **R5 已經落地**，追蹤清單 :314 已有【2026-11-07 風控 R5】註記，我讀過確認。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 評估摘要
- **採用：**
  - R1、R2、R4 依風控文字修改 ADR；
  - R3 逐字採用定稿；
  - S5 採用；
  - N-199 依 R6～R8 修改；
  - S1、S2 寫入修訂七；
  - S4 另開單。
- **否決：**
  - 結算迴圈「跳過失敗列、繼續處理後面的列」：會讓失敗變成靜默，違反 C-11。
  - S3 在 N-197a 內加 `Field(description=...)`：理由見下方。
- **另外處理：** 讀碼時發現原稿兩處說法錯誤，一併修正：
  - P1 的「一列失敗只影響那一列」；
  - Consequences 的「那一列下次重試」。

#### 方案比較

| 議題 | 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| 確定性失敗的迴圈語意 | (a) 例外中止整次結算（現行，加上揭露） | 不靜默，符合 C-11；改動最小 | id 排在失敗列後面的到期列都無法結算，今日頁面持續停擺 | 中，但看得見 | **採用** |
| | (b) 逐列 catch，跳過失敗列繼續 | 其他列照常結算 | 失敗被吞掉，違反 C-11；要多一套揭露與字面 | 高 | 否決 |
| `work/` 要記的雜湊與執行時間從哪來 | (a) stdout 多印四行 ASCII | CEO 照抄整行就好，不必開報告檔；可測試 | 第 3 節 stdout 多四行，T9 要配套 | 低 | **採用，[待風控]** |
| | (b) CEO 從 report.md 手抄 64 碼雜湊 | 不改程式 | 容易抄錯；要讀報告檔才拿得到 | 中 | 否決 |
| C9 的「PR 開出前送達」怎麼舉證 | (a) qa 比對頁面上的時間，風控在 risk-gate 確認自己的收件時間 | 不需要 Bash；最後一道是風控本人 | commit 時間可以自訂，只能當旁證 | 低 | **採用** |
| | (b) 只靠 PR 說明聲明 | 簡單 | 無法查核 | 高 | 否決 |
| S3 | (a) 不在 N-197a 加 `Field`，登錄重啟條件 | C1 維持 `app/api/**` 零 diff | OpenAPI 上暫時沒有欄位說明 | 低 | **採用** |
| | (b) 在 N-197a 加 | API 文件完整 | C1 要擴大到 api 檔；目前沒有任何消費者 | 低 | 否決 |

#### 區塊一：ADR-0042 修正版全文（交 tech-writer，等風控確認 R1、R2、R4 之後落檔為 `docs/adr/0042-stock-desk-排程台結算的claim與動帳併入同一寫鎖交易.md`，狀態維持 proposed）

````markdown
# ADR-0042：stock-desk 排程台結算的 claim 與動帳併入同一個寫鎖交易（N-198／N-169F2；補充 ADR-0035、ADR-0041，不取代）

- 狀態：proposed
- 日期：2026-11-07（同日修正版，回應 [風控-ADR42] R1、R2、R4 與 S5）
- 決策者：
  - tech-architect：草案與修正版；
  - risk-compliance-officer：2026-11-07 審查，CONDITIONAL APPROVE。決策 P1 核可，附 R1～R4；R1、R2、R4 修正之後回風控確認；
  - CEO：核可，待定。
- 來源簡稱（都在 `work/reviews/` 下）：
  - [TA-177S]：`2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`（修訂一 1.3 的 R-α、修訂四第 4 節、修訂六、修訂七）；
  - [風控-197]：`2026-11-07-N177修訂四比對與N197裁示-風控.md`；
  - [風控-ADR42]：`2026-11-07-修訂六與ADR0042與N199審查及REBALANCE_SUPERSEDED定稿-風控.md`；
  - [TA-E2]：`2026-11-04-N182解讀點2與3裁示-tech-architect.md`（E-2）；
  - [風控-1104]：`2026-11-04-ADR0039v2回審與N182字面-風控.md`（第 11 點）。
- 適用範圍：只有 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 程式位置：主 checkout，N-190 以 3985f4d 合入之後的 tip。只讀、未執行，以內容定位。
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
     - 例外中止本次 `_settle_pending`：id 比失敗列小、已經 commit 的列保留；id 比它大的到期列，本次不處理（到期列以 `ORDER BY id ASC` 取出，store.py:1528）。
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
   - **N198-C7**：以 merge commit 合入。base 與先後順序，依 [TA-177S] 修訂六第 1 節與修訂七的方法驗證。N-198 的代入值如下：
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
     - 本條是預設路線（N-177b 先合入）的寫法。改走 N-198 先合入時，`<M_2>` 與第二份 diff 只能由 N198-C9 的 TA 補充改寫。補充依 C9 送達之前，本條照上文判定，也就是 base 不含 N-177b 就判 BLOCKING。
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
       - (b) 該補充在 N-198 的 PR **開出之前**送達風控，不得事後補。PR 說明要列出補充的檔案路徑與 coordinator 的送審紀錄。qa 讀頁面比對時間：PR 頁面的建立時間，對照送審紀錄所載的送達時間，以及送審紀錄的 commit 頁面時間。commit 時間可以由作者自訂，所以這只是旁證；最終由風控在 risk-gate 確認自己收件早於 PR 建立。送達晚於 PR 建立，或沒有送審紀錄，就判 BLOCKING。
       - (c) 風控對該補充的審查紀錄存在於 `work/reviews/`，不是 VETO，其 required 已處理。
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
      - 該列每一次都回滾、留在 pending，每一次 `/today` 都依 C-11 失敗。
      - **確定性失敗會讓每一次今日頁面讀取都失敗，期間不會顯示任何指令，包括停損停利。**
      - 直到修好為止，今日頁面持續無法使用；S/P 系列的賣出指令也不會出現。
    - [TA 補，待風控確認] 以下是讀碼得到的事實，都只讀、未執行：
      - `_settle_pending` 在評估之前執行（service.py:2153），例外會往外拋，所以評估與 `commit_evaluation` 都不執行；這段期間也不會寫入新的指令列。
      - `POST /api/playbook/settle` 經由同一個 `_settle_pending`（service.py:1524-1551），同樣每一次都失敗。
      - 到期列以 `ORDER BY id ASC` 逐列處理（store.py:1528），例外會中止迴圈。
        - id 比失敗列小的列，各自 commit 之後保留；
        - id 比它大的到期列，每一次都輪不到，修好之前都不會結算。這包括這段期間由「全部出清」寫入的出清賣出列，因為它們的 id 一定比較大。
      - 「全部出清」本身（`emergency_exit`，service.py:2288 起）不經過 `_settle_pending`，仍然可以送出，回應也照常列出出清指令；只是這些列要等結算恢復，才會記入帳冊。
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
     - 這份補充必須在 **N-198 的 PR 開出之前**送到風控，不得事後補。
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

## 待決
- [待風控] 確認本修正版的 R1、R2、R4，包括：
  - Consequences「失敗分兩種」中 [TA 補] 的讀碼事實；
  - N198-C9 (b) 的舉證方式。
- [待風控] N-198 部署時，「確定性失敗會持續停擺」這項行為變更，要不要通知 CEO（使用者），由風控決定。
- CEO：核可。
````

#### ADR-0042 修改索引（F1～F18，風控比對用）

| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| F1 | 檔頭：日期、決策者、來源簡稱、前提 | 登錄審查結果；新增 [風控-ADR42]；前提加上 N-199 | [風控-ADR42] |
| F2 | Options：P1 列；新增「逐列 catch」變體列 | 改正「一列失敗只影響那一列」；把跳過失敗列列為否決的選項 | 隨 R2，[TA 補] |
| F3 | Decision 1 末點 | `ClaimSettle.settled` 的型別以 N-177b 先合入為前提，另一路線依 C9 | 隨 R4 |
| F4 | Decision 3 末點 | 逐列迴圈不 catch 例外（C-11） | 隨 R2 |
| F5 | Decision 5 失敗語意 | 寫明中止語意與 `ORDER BY id ASC`；區分暫時性與確定性 | R2 |
| F6 | N198-C1 | 加 `scripts/**` 零 diff | 隨 R1（T9 用 base 上的工具） |
| F7 | N198-C7 | 改為三個前置單；追加 `<M_3>` 那一行；N-198 的三份旁證 diff 與 regex | R1 |
| F8 | N198-C9（新增） | 合入路線：補充在 PR 開出之前送達風控，並改 C7；舉證方式 | R4 |
| F9 | N198-T2 (iii)（新增） | 用測試釘住中止語意 | 隨 R2 |
| F10 | N198-T9 | 工具取自 `<base>` 上 N-199 合入後的版本 | R1 |
| F11 | Consequences 好處第 1、3 點 | 「N-198 之前寫入的列」改為「部署之前已被 claim 的列」；當機改為任一步失敗或行程終止 | 與 R3 定稿一致 |
| F12 | Consequences E-2 | 「頻率會下降」改為事實陳述；列出前提的三個來源；引用 R5 | S5 |
| F13 | Consequences「失敗分兩種」（新增） | 逐字寫入 R2 那句揭露；附 [TA 補] 讀碼事實；寫明行為變更 | R2 |
| F14 | Consequences 的 busy_timeout 與 schedule 標記兩點 | 拿掉單獨的「那一列下次重試」 | R2「不得只寫下次重試」 |
| F15 | 被約束第 3 點 | 加上「改動逐列迴圈對例外的處理方式」也要另立 ADR | 隨 R2 |
| F16 | 與其他 ADR 的關係：ADR-0041:114 | 草稿換成風控定稿，逐字照錄；寫明落檔時點 | R3 |
| F17 | 先後與相依第 2、4、5 點 | 第 2 點：補充在 PR 開出之前送達、一併改 C7。第 4 點：改為「相依」，消除和 T9 的矛盾。第 5 點：N-177b 延誤不構成延期理由 | R4、R1、R4 |
| F18 | 待決 | 更新：已解決的項目移除，新增兩項待風控 | — |

#### 區塊二：N-199 spec 第 5 節修正版（取代原第 5 節全文；後附第 2、3、6 節的配套修改）

````markdown
## 5. 隱私（RC-6）與命中回報（修正版，回應 [風控-ADR42] R6～R8）
- `report.md`、`report.json` 含標的、股數、價格與時間，屬於持股資料：
  - 不得 commit；
  - 不得貼進 `work/`（那也是 repo）；
  - 不得貼進任何對話紀錄。
- **逐檔明細只由 CEO 在本機讀；任何 agent 都不得讀 `report.md`、`report.json`。**
  - 沒有任何轉交明細的路徑。coordinator 與其他 agent 都不經手明細，不以任何方式轉交，也不得要求 CEO 貼出明細。
  - [TA 補，待風控確認] 範圍：這條限制指的是對 production DB 複本執行所產生的報告。N199-T1～T12 由測試以合成 DB 產生、再由測試讀取的報告，不在此限。測試不得以 production DB 或其複本當輸入（S6、RC-5 照舊）。
- 工具既有的 git 工作樹拒絕檢查（RC-5）照舊。
- 交付之後，CEO 依 [TA-177S] 6.8 的步驟執行：停服務；複製 `.db`，有 `-wal`、`-shm` 時一起複製；對複本執行。
- **回報進 `work/` 的內容只能有三個計數、腳本與 DB 的雜湊、執行時間。** 也就是：
  - 三個計數；
  - 腳本 SHA-256；
  - DB 的前後 SHA-256；
  - 執行時間。
  - 這些值由 CEO 從 stdout 抄給 coordinator，只抄以下七行（第 3 節）：`n199_a_rows=`、`n199_b_rows=`、`n199_c_rows=`、`script_sha256_lf=`、`db_sha256_before=`、`db_sha256_after=`、`run_at_utc=`。
  - `report_md=`、`report_json=` 兩行不抄。`gate_affected_symbols=` 屬於 N-177 閘門，依 [TA-177S] 6.8 的原規定處理，不屬於本節。
- 任一計數大於 0：coordinator 通知風控與 CEO。
  - N199-A、N199-C 的列，請 CEO 以券商對帳單核對該批的實際持股；N199-B 的列，請 CEO 核對是否曾依該待結算列（`pending.id` 對應的指令）在券商下單。這是事實核對的請求，不是處置建議；處置另行裁示。
  - 對應的列，由 CEO 在本機的 `report.md` 中自行找出。
- 命中不改變 exit code（第 1 節）。
- 建議：N-198 部署之後再跑一次。
  - N-198 部署之後才 claim 的列，不會產生新的 N199-A。
  - 部署前已命中 N199-A、而且批次仍是 planned 的資料，之後同批的 R1 若成交，部署之後會新增一列 N199-C，原本那列 N199-A 隨之消失。這是部署前資料的延續，不表示 N-198 失效。
  - N199-B 仍可能因跨日重發（V4）或 N-172a 之前的重複而命中。
````

第 2、3、6 節的配套修改（同一份 spec，一併交 data-engineer）：

````markdown
### 配套修改（N-199 spec 第 2、3、6 節）
- 第 2 節（R6）：
  - `N199_MULTI_EXECUTED_BUY_SQL` 上方註解的開頭 `#: N199-C ([TA 補]): `，改為 `#: N199-C (required, risk R6): `；後文不變。
  - 說明文字「N199-C（[TA 補]）」一律改稱「N199-C（風控 R6 列為 required）」。
- 第 3 節 stdout（[TA 補，待風控確認]；R7 之後，`work/` 要記錄的雜湊與執行時間，必須有一個不必讀報告檔就拿得到的來源）：
  - 在 `n199_c_rows=<n>` 之後追加四行 ASCII：
    - `script_sha256_lf=<64 hex>`：與 report.json 中既有的腳本雜湊同值；
    - `db_sha256_before=<64 hex>`；
    - `db_sha256_after=<64 hex>`；
    - `run_at_utc=<ISO 8601，UTC>`：與 report.json 中的執行時間同值。
  - 只在 exit 0 時印出。exit 0 時 before 與 after 必然相同，不同就已經依 S5 以 exit 3 結束。
- 第 4 節 N199-T9 追加：
  - 上述四行存在、都是 ASCII，值與 report.json 對應的值相同；
  - stdout 的每一行都符合以下白名單之一：`n177_n190_backtrack_probe version=`、`gate_affected_symbols=`、`report_md=`、`report_json=`、`n199_[abc]_rows=`、`script_sha256_lf=`、`db_sha256_(before|after)=`、`run_at_utc=`；
  - stdout 不含任何測試 DB 中的 symbol 字串。
- 第 6 節新增 QB-5：N199-C 是 required（風控 R6）。N199-C 的 SQL、輸出欄位或 N199-T5 任一項缺少，就判 BLOCKING。
````

#### 區塊三：修訂七（附到規格檔末）

````markdown
## 修訂七（tech-architect，2026-11-07；回應風控 [風控-ADR42] suggested S1～S4）

- 依據：[風控-ADR42] `work/reviews/2026-11-07-修訂六與ADR0042與N199審查及REBALANCE_SUPERSEDED定稿-風控.md`，結論 CONDITIONAL APPROVE。
- 本修訂只取代或新增下面點名的段落，其餘維持修訂六。S5 屬 ADR-0042，已併入 ADR-0042 修正版，不在這裡。

### 1. 1.6 表格中 regex 的跳脫（S1，採用）
- 修訂六 1.6 表「稽核表 DDL」那一列的 `\|`，是 markdown 表格的跳脫，不是 regex 的一部分。實際要用的 regex 是：
```
^[-+].*CREATE TABLE IF NOT EXISTS (playbook_fill_moves|\{FILL_MOVES_TABLE\})
```
  - `|` 是 regex 的交替；
  - `\{`、`\}` 才是 regex 的跳脫，比對字面的花括號，要保留。
- 表中其他各列都不含 `\|`，照表使用。
- 照抄成 `\|` 時，比對的是字面的直線符號，這個錨點永遠抓不到。所以 qa 以本節為準。
- ADR-0042 N198-C7 的 regex 已改放在程式碼區塊，不經過表格。

### 2. qa 以 PR 頁面的 head SHA 對照（S2，採用）
- 修訂六 1.5 新增第 6 點（全部都要成立；不成立就判 BLOCKING）：
  - 6. qa 從 PR 頁面讀出 head commit 的完整 40 碼（commits 分頁最後一個 commit，取 commit 頁面網址中的 SHA）。它必須等於 (i)、(ii) 兩份紀錄中的 `<head>`，也必須等於 qa 實際審查的 commit。
  - 這一步是讀頁面，不需要 Bash。
  - 理由：1.5 第 4 點的 `git diff --stat` 輸出為空，只代表兩者的 tree 相同，不代表是同一個 commit。同一個 tree 的另一個 commit（例如 rebase 之後、或空 commit），祖先關係可能不同，(i)、(ii) 的 ancestry 判定就不適用於它。
- 修訂六 1.7 的重做清單，加上 1.5 第 6 點。
- 適用於 N196-C8、N197a-C8，以及 ADR-0042 的 N198-C7。

### 3. 名詞與判斷的延伸（配合 ADR-0042 修正版）
- 修訂六 1.1：只在 N198-C7 新增 `<M_3>`，也就是 N-199 在 product 上的 merge commit，完整 40 碼。
- 修訂六 1.5 第 3 點：對 N198-C7 讀為「三條 `--is-ancestor` 都是 `exit=0`」。N196-C8、N197a-C8 不變。

### 4. `set_capital(at=...)` 的時區守衛（S4，採用為另開單；不在 N-197a 範圍）
- 現況：`set_capital` 的 `at: datetime | None`（store.py:1033-1055）接受沒有時區的 datetime，並原樣寫入 `isoformat()`。app 內兩個呼叫點（service.py:1908、:2030）都不傳 `at`。
- 對 N-197a 的影響：N197a-C11 在讀取端會 fail closed（沒有時區就 raise）。所以破口不會變成錯誤的字面，但失敗時點會延後到拒絕路徑。
- 另開單，編號由 coordinator 給，P3，不擋 N-197a：
  - `set_capital`，以及 N-195 的 `set_total_deploy`（若它接受 `at`）：`at` 不為 None 而且沒有時區時，在任何寫入之前 raise `ValueError`。
  - 測試：傳入沒有時區的 `at` → `ValueError`，四個鍵逐字不變；有時區的 `at` 照舊寫入。
  - 開工前用 grep 找出 `tests/**` 中傳入沒有時區 `at` 的既有呼叫，逐條列出，改為有時區的值。

### 5. 不採用：S3（`RebalanceResponse.previous_total_deploy` 的 `Field(description=...)`）
- 理由：
  - 前端沒有使用這個回應（修訂四 3.6）；
  - `message` 已經以「目前的 TOTAL_DEPLOY 為…」說明語意；
  - 加這一項，要把 C1 擴大到 `app/api/playbook.py`，打破 N-197a 對 `app/api/**` 的零 diff，換來的只是目前沒有消費者的 OpenAPI 說明。
- 重啟條件：前端新增 REBALANCE 的入口，或任何程式開始讀取 `RebalanceResponse` 時，同一張單必須加上這個 `Field(description=...)`，內容與修訂六 2.4 的 docstring 一致。依 R-5′，新增入口本來就要先回風控，所以這個條件會在那時被檢查。

### 6. 修改處索引（風控比對用）

| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | 1.6 DDL 錨點的 regex | 註明實際 regex 是 `\|` 解跳脫後的 `\|`（交替），並給出程式碼區塊版本 | S1 |
| 2 | 1.5 新增第 6 點；1.7 重做清單 | 新增：讀 PR 頁面的 head SHA 對照 `<head>` | S2 |
| 3 | 1.1 `<M_3>`；1.5 第 3 點對 N198-C7 的讀法 | 新增 | 配合 ADR-0042 R1 |
| 4 | `set_capital(at=...)` 守衛 | 登錄另開單 | S4 |
| 5 | S3 | 不採用，登錄重啟條件 | S3 |

（修訂七由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。）
````

> 注意：修訂七第 6 節索引第 1 列的「性質」欄，因為也在 markdown 表格內，`|` 必須寫成 `\|` 才不會切斷表格。落檔後讀起來是「`|` 解跳脫後的 `|`」，語意以第 1 節的程式碼區塊為準。若要避免混淆，coordinator 可以把該格改成「註明實際 regex 中的直線符號是交替，並給出程式碼區塊版本」，這只刪字、不改語意，我授權這樣改。

#### S1～S5 評估摘要
- **S1：採用**，見修訂七第 1 節。
- **S2：採用**，見修訂七第 2 節，同時適用 N198-C7。
- **S3：不採用**，見修訂七第 5 節，已登錄重啟條件。
- **S4：採用為另開單**，見修訂七第 4 節。
- **S5：採用**，見 ADR-0042 F12。

#### 對實作的約束（新增或變更，逐條可由 qa 檢查）
- **N-198：**
  - N198-C1 加上 `scripts/**` 零 diff；
  - N198-C7 改為三個前置單 ancestry，加上三份旁證 diff；
  - 新增 N198-C9（路線，送達早於 PR 建立）；
  - 新增 N198-T2 (iii)（中止語意）；
  - N198-T9 的工具取自 base。
- **N-199：**
  - R7：任何 agent 都不讀報告檔，沒有轉交路徑；
  - R8：N199-B 命中時也請 CEO 核對；
  - stdout 多四行，T9 加白名單斷言（待風控）；
  - 新增 QB-5（N199-C 是 required）。
- **N-196、N-197a、N-198：** 修訂六 1.5 新增第 6 點（PR 頁面的 head SHA）；1.6 的 DDL regex 以修訂七第 1 節為準。

### 其他部門
本輪沒有參與。

## 三、驗證

**讀過的文件：**
- `/home/user/AICompany/work/reviews/2026-11-07-修訂六與ADR0042與N199審查及REBALANCE_SUPERSEDED定稿-風控.md`，全文。
- `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂六與ADR0042草案與N199spec-tech-architect.md`，全文，是我的原稿。
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md` :100-139，其中 :114 原文已核對。
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` :308-317。:314 已有 R5 註記。
- `/home/user/AICompany/work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md`，用 grep 讀 E-2 相關行。

**讀過的程式**（都是只讀，沒有執行）：
- `apps/stock-desk/backend/app/playbook/service.py`：
  - `_settle_pending` :1553-1672：迴圈內沒有 try/except；
  - `settle_on_request` → `settle_pending`（:1516-1551）；
  - `evaluate_today` :2123-2162：結算在評估之前，見 :2153；
  - `emergency_exit` :2288-2337：用 grep 確認不呼叫 `_settle_pending`。
- `apps/stock-desk/backend/app/playbook/store.py`：
  - `pending_directives` :1505-1529：`ORDER BY id ASC` 在 :1528；
  - `set_capital` :1033-1055。
- `apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`：
  - `SCRIPT_VERSION = "1"`（:58）；
  - `main` 的 stdout（:1931-1934）只有 version、gate 計數、兩個報告路徑，沒有雜湊與執行時間。

**發現的落差：**
- 上一輪我回報主 checkout 沒有 `n177_n190_backtrack_probe.py`。這次用 glob 查到它已經存在。我沒有比對它和 scratchpad `wt_probe` 版本是否相同。spec 開頭「開工前先比對」的要求照舊，請 coordinator 一併確認。

**未查證：**
- 確定性失敗在實際環境中的發生頻率。
- N-177b 中 `SettleOutcome` 的實際名稱與所在檔案：C7 已寫「以實際合入的為準」。
- report.json 中雜湊與執行時間的實際鍵名：配套修改寫的是「與既有值同值」，不指定鍵名。
- 前端在 `/today` 回 500 時的實際畫面：結論只依「不會有指令資料」，不依畫面細節。

我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案，也沒有執行任何 Bash 指令。

## 四、下一步

1. **coordinator：**
   - 把本回報逐字轉存到 `work/reviews/`；
   - 把修訂七附到規格檔末；
   - 把 ADR-0042 修正版與 N-199 第 5 節修正版（含配套修改）送風控確認；
   - 確認主 checkout 的 probe 與 `wt_probe` 版本是否相同；
   - S4 另開單並給編號。
2. **risk-compliance-officer：**
   - 確認 R1、R2、R4 的修改；
   - 判定三項 [TA 補]：
     - ADR Consequences 的讀碼事實；
     - N-199 stdout 多四行；
     - R7 讀檔禁令只限 production 複本產生的報告；
   - 決定 N-198 部署時，要不要通知 CEO「確定性失敗會持續停擺」。
3. **tech-writer：**
   - ADR-0042 在風控確認之後落檔，狀態維持 proposed；
   - ADR-0041:114 的補註與 R-6′ 的已修正註記，等 N-198 以 merge commit 合入 product 之後才落檔，文字逐字照 ADR-0042「與其他 ADR 的關係」。
4. **data-engineer：** 依修正後的 N-199 spec 實作。N199-C 是 required；stdout 的四行等風控確認之後再實作。
5. **dev-lead：**
   - N-198 在 N-177a、N-199（以及預設的 N-177b）合入之後才開工；
   - 若要改走 N-198 先合入，先通知 TA 出補充，送達風控之後才可以開 PR。
6. **qa-reviewer：**
   - 新增與變更的約束都列為 BLOCKING，包括 N198-C7、C9、T2 (iii)、N-199 的 QB-5，以及修訂六 1.5 第 6 點；
   - 1.6 的 DDL regex 以修訂七第 1 節為準。
7. **CEO：** ADR-0042 的核可，等風控確認修正版之後再做。

**相關檔案：**
- /home/user/AICompany/work/reviews/2026-11-07-修訂六與ADR0042與N199審查及REBALANCE_SUPERSEDED定稿-風控.md
- /home/user/AICompany/work/reviews/2026-11-07-N177規格修訂六與ADR0042草案與N199spec-tech-architect.md
- /home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py

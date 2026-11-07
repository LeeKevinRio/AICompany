# ADR-0041：stock-desk 排程台 S2 成交動帳、成交移動稽核表與結算動帳的鎖內讀改寫（補充 ADR-0035、ADR-0039，不取代）

- 狀態：proposed
- 日期：2026-11-07
- 決策者：
  - tech-architect：草案；
  - risk-compliance-officer：審查。2026-11-07 CONDITIONAL APPROVE（RC-1～RC-10）；修訂一 2026-11-07 再審 CONDITIONAL APPROVE；修訂二與本修正版 2026-11-07 比對確認；
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
   - service 零 diff（ADR-0040 Decision 14 第 3 點；此句只適用於 N-177a，N-177b 的 Decision 10 會改 service）；
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
    - R-3′：REBALANCE 先讀批次、載入日線之後才讀現金；兩次讀取之間若有賣出結算 commit，已賣出的股數會同時以市值與現金計入總資產，TOTAL_DEPLOY 偏高，方向不保守。這是修訂前就存在的評估輸入過時，N-177a 讓 S2 也加入這個窗口。處理：另開小單 N-196，期限比照 N-195；修法會改變 REBALANCE 計算輸入的讀取時點，要經風控審查；修好之前，這個問題仍在（[TA-177S] 修訂二 5.6）。
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

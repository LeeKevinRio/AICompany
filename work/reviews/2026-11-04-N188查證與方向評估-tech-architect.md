# N-188 查證與方向評估

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

N-188 確實會發生。我讀了 product/stock-desk 的現行程式（`.git/HEAD` 指向 `product/stock-desk`），只讀碼，沒有執行。

- **成立的必要條件**：同一預定執行日的兩次評估之間，有一筆同 symbol 的列在帳冊判定成交。目前帳冊股數只有一條路徑會變：`_settle_pending` 呼叫 `store.settle`。
- **影響範圍不只 S2**：逐批的 S1／P1／P2／P3 列也受影響，但只在批次減股的方向。R／M1 列與 EMERGENCY 列不屬於本單。
- **現有揭露都沒有蓋住**：W-B2LSf 只管帶標示的批次；N-172 系列的幾句、A-15、結算 warnings 也都不涵蓋這個情況。
- **前提更正**：ADR-0036 尚未存在。它保留給 N-172b／N-176 的「在途單生命週期」，還沒起草。同日重複評估的規則全部在 ADR-0035（accepted）及其補充一～四。
- **建議方向**：走方向 (1) 揭露句，觸發條件用結構化的「本列寫入後帳冊有變動」證據 (1b)。這是加法，不與任何 accepted ADR 衝突，不需要 CEO 決策。方向 (2) 改寫 logged 與 ADR-0035 衝突，TA 建議否決。方向 (3) 不衝突，可作為風控的後備選項。
- **時序**：不併入 N-168。設計與字面現在就可以並行；實作要等 N-168 合進 product 之後，從 product 開分支。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 1. 查證：寫入條件與顯示路徑
程式路徑相對於 `/home/user/AICompany/apps/stock-desk/backend/app/`。

- **`/today` 的評估流程**（`playbook/service.py:1542-1691`）：
  1. 先結算（`:1572`）；
  2. 讀 `book`（`:1616`），交 engine 評估（`:1618`）；
  3. `commit_evaluation`（`:1636`）；
  4. 回應的 `directives` 設為 `commit.logged`（`:1666`）。
- **`commit_evaluation`**（`playbook/store.py:1172-1219`）：在 `BEGIN IMMEDIATE` 內做 `_new_decisions`。
  - K1 是 `(symbol, batch_no IS, rule_id, action, execution_date)`；R 系列另用 K2（`:380-426`）。
  - 已經記過的 K1 不再寫入，舊列也不改（N172-C11）。
  - `_read_logged`（`:498-509`）讀出該執行日所有 R／S／P／M1 列，排除 `EMERGENCY`、`REBALANCE`（`:236`），以 K1 取最小 id。
- **規則出處**：上述行為就是 ADR-0035 Decision 1、3、4 與 N172-C6、C11。
  - S2 的 K1 是 `(symbol, NULL, 'S2', 'sell', 執行日)`。
  - 所以第二次評估就算用新的 book 算出不同股數，也寫不進去，頁面仍顯示第一次的列。列裡的 `shares` 與 `rule_summary` 的「均成本／出清 N 股」都停在第一次。
- **兩次評估之間會讓股數變動的路徑**：
  - 帳冊股數只在一處改變：`store.settle`（`store.py:1399-1457`），而且只在列為 executed、`batch_no` 不是 NULL、批次列存在時動帳（`:1420-1426`）。
  - 它唯一的呼叫點是 `_settle_pending`（`service.py:1096`）。觸發者有兩個：`/today` 的評估，以及 `POST /settle`（`service.py:969-996`、`api/playbook.py:594-607`）。
  - scheduler、rebalance、出清都不動股數。MISSED 只會把 `missed_count` 加 1。
- **實際成立的情境**：Y 有一列在途單，它的預定執行日 D′ 小於等於 as_of，但 Y 的序列裡還沒有 D′ 的 bar，所以結算判不了（`service.py:1053-1070`）。同時 Y 的快照仍然可用：
  - `is_usable` 只看 status 與 source（`engine.py:63-65`、`:1196-1210`）；
  - 快照的 `data_date` 取各 symbol 自己的最新 bar（`service.py:132-158`）；
  - 執行日則由所有序列中最新的日期決定（`engine.py:1122`）。

  第一次評估以舊 book 寫下 S2。之後 D′ 的 bar 進來（單一標的資料落後，或 V4 式的後補），第二次評估或 `POST /settle` 讓那一列成交，book 改變，但頁面仍顯示舊列。
- **對風控列出的三個觸發來源的修正**：
  - 「前次載入失敗」本身不足以成立：寫下 S2 的那一次，Y 的資料必須可用。只有「當時判不了結算、但快照可用」這個組合才會成立。
  - `POST /settle` 不是獨立成因，它和 `/today` 用同一個函式。但它會讓第二次 `/today` 的結算區塊看不到那筆成交，連僅有的間接線索都沒了。

#### 2. 影響範圍
| 列 | 是否受影響 | 方向 |
|---|---|---|
| S2（整檔） | 是。後補的買單成交、或其他批次減股，都會讓 `shares` 不等於目前 open 合計 | 補買單成交：列股數**少於**帳冊（少賣）。補賣單成交：列股數**多於**帳冊（超賣） |
| S1、P2 移動停利（`remaining_shares` 全賣） | 是。該批較早的賣單晚結算時就會發生 | 列股數多於帳冊；帳冊有 `min` 保護（`store.py:1442`），但使用者看到的是舊股數 |
| P1／P3（依比例） | 是，條件同上 | 同上 |
| 逐批列遇到晚成交的買單 | 否。該批第一次評估時仍是 planned，沒有 S/P 列；第二次評估寫的是新 K1，股數依新帳冊 | — |
| R／M1 | 不屬本單。ADR-0035 Consequences 已接受「首次決策為準」；批次已非 planned 的情況由 G1／W-B6b 處理 | — |
| EMERGENCY | 不在 logged 裡；在途出清列減股由 A-15 承接 | — |

相鄰問題，不屬本單：
- 帳冊變動後 S2 不再觸發時，engine 改出逐批列。這些列的 K1 不同，會被寫入，同一頁就會同時出現舊 S2 和新的 S1／P 列。ADR-0035 Consequences 已接受「同一批同一天先後出現不同規則的賣單」，但沒有談到由帳冊變動引起的情況。
- engine 評估 S/P 時不扣除未結算的賣單，所以第一次評估寫下的列本身就可能偏大。F4（N-169）只講 EMERGENCY 的在途單。我沒有查到追蹤清單有一般 S/P 在途賣單的條目，請 coordinator 確認。

#### 3. 現有揭露都沒有蓋住
- **W-B2LS／W-B2LSf（N-168）**：只在有標示批次時渲染，與風控第二節之 4 的判斷一致。
- **A 句 `SAME_DAY_EARLIER_LINES_DATA_GAP_NOTE`**（`wording.py:357-362`）：只在本次這檔資料不可用時出現。本情境中資料可用，不會渲染。
- **ENTRY（`:334-344`）與 W-B6b（`:383-393`）**：只處理 R 系列買單。
- **A-15（`:714-720`）**：只出現在出清區塊的 EMERGENCY 列。
- **結算 warnings `SETTLEMENT_SUMMARY`（`:729-733`）**：只當次出現，下一次重新整理或走 `POST /settle` 就不見了，也沒有說明表中股數已過時。

#### 4. 方向評估
| 方向 | 優點 | 缺點 | 與 accepted ADR |
|---|---|---|---|
| (1a) 揭露句：凡是本次沒寫入的 S/P 賣出列一律附揭露 | 不需要新讀取 | 從第二次重新整理開始每一列都帶，與風控否決「一律 W-B2LSf」的理由相同 | 不衝突 |
| **(1b) 揭露句：本列寫入後有帳冊變動的證據才附** | 用既有欄位、不改 schema：logged 列的 `created_at`，比對同 symbol（逐批列限同一批）是否有一列 `status='executed'`、`batch_no IS NOT NULL`、`action IN ORDER_ACTIONS`、`settled_at > created_at`。這正好對應 `settle` 的動帳條件，是必要條件 | 可能多報：判定成交但沒動帳的 N2 情況也會觸發。並發時可能漏報：另一個請求在本次讀 book 之後、commit 之前 claim，屬 F2／N-169 類殘留。N-177 修好 S2 動帳之後，述詞要擴及 S2 | 不衝突（Decision 4、R16、C6、C11 全部維持） |
| (1c) 比對列股數與目前帳冊 | 不需要新 SQL | P1／P3 依比例計算，要在 service 重寫 engine 的語意，違反 E-29 的精神；剛好抵銷時會漏報 | 不衝突，但不建議 |
| (2) 重評估時改寫 logged，或在同一 K1 下另寫新列 | 頁面股數等於帳冊 | 使用者可能已依舊列下單（R10）；另寫新列會重新帶出 V3 式的重複賣單 | **衝突**：ADR-0035 Decision 1、3、4，N172-C6、C11，S-α（CEO #83）與 B-2a 精神（CEO #79）。要另立取代 ADR 並由 CEO 裁決，TA 建議否決 |
| (3) 每一列標示「依產生時帳冊」 | 永遠為真，實作最簡單 | 不告訴使用者帳冊已經變了，容易被習慣性忽略；每支 golden 都會有差異 | 不衝突 |

建議採 (1b)。放的位置由風控決定：
- **頁面層 warning**：比照 A 句，列出受影響列的 symbol、規則、股數。不碰 S-3 固定項。
- **同列 note**：`_lines` 的輸入不足以判斷，需要改它的簽名，屬 S-3 固定項，走 R-3。要由 TA 出補充，不需要 CEO。

#### 5. 對開單的約束（qa-reviewer 可逐條檢查）
1. `engine.py` 零 diff（C-B11、N172-C3）。
2. 不得 DELETE 或 UPDATE 既有指令列，也不得在已存在的 K1 下另寫新列（N172-C11、Decision 1）。
3. `/today` 的 `directives` 仍等於 `commit.logged`（Decision 4、N172-C6）；不得把重算的股數當成一列顯示。
4. 觸發只能來自結構化資料，不得比對字串（題 12 allowlist）。
5. 「動帳」述詞只定義一次，放在 `store.settle` 的動帳條件旁邊。
   - 在 `commit_evaluation` 的鎖內，與 `_read_logged` 在同一份快照讀取，結果以加法欄位放進 `EvaluationCommit`。
   - 這不是 `read_in_flight` 的在途讀取；要在 TA 補充中明文判定不屬 R-4，並更新 QB-7 的 grep 白名單。
6. store 不得 import wording（N172-C7）。字面只放在 `wording.py`，風控逐字定稿前不得合併。
7. S-3 固定項不得變動；若選同列 note，要先有 TA 補充。
8. 測試，列為 BLOCKING：
   - 無標示的 S2：兩次評估之間讓後補 bar 成交（一次走 `/today`，一次走 `POST /settle`），斷言揭露出現；
   - 逐批 S1：中間有較早賣單晚結算，斷言揭露出現；
   - 中間沒有結算時不觸發；
   - MISSED 與 G1 拒絕的列不觸發；
   - N2（判定成交但沒動帳）依風控決定處理；
   - 並發殘留寫進 docstring；
   - N-177 落地時同步改述詞並補測試。
9. 與 W-B2LS／W-B2LSf 在同一列 S2 上的先後與互斥，由風控定。
   - 特別是 (1b) 觸發、而 P 成立渲染 W-B2LS 的情況，兩句的說法會互相矛盾。
   - (1b) 的證據可以把風控已接受的「剛好抵銷」殘留收窄，但這會改變 N-168 的行為，所以要等 N-168 合併後，作為 W-B2LS 回審處理，不得併入 N-168。

### 其他部門
本次未參與。

## 三、驗證
- 讀過的程式：
  - `playbook/store.py`：`:64-153`（schema 含 `created_at`、`settled_at`）、`:218-258`、`:340-509`、`:1084-1219`、`:1324-1457`；
  - `playbook/service.py`：`:132-158`、`:430-705`、`:940-1159`、`:1542-1691`；
  - `playbook/engine.py`：`:63-65`、`:200-219`、`:405-708`、`:1105-1324`；
  - `playbook/wording.py`：`:320-399`、`:714-743`。
- 讀過的文件：
  - `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md` 全文；
  - `/home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 的 S-3～S-6 與釐清七；
  - `/home/user/AICompany/work/reviews/2026-11-04-N168釐清七E30裁示-風控.md` 全文；
  - 追蹤清單 N-169、N-176、N-177、N-188 等列。
- 用 Glob 確認 `docs/adr/` 沒有 0036；ADR-0035 Decision 8 與 ADR-0039 都寫明 0036 尚未起草。
- 全部是讀碼判定，沒有執行。這個情境還沒有實證，需要 qa-automation 依第 5 點第 8 項的情境重現。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 四、下一步
1. **coordinator**：
   - 開 N-188 單，優先度維持 P2。若風控認為超賣方向需要升級，由風控提出。
   - 更正追蹤清單中「ADR-0036 同日重複評估」的說法，改為 ADR-0035。
   - 確認一般 S/P 在途賣單不扣除是否已有追蹤條目。
2. **risk-compliance-officer**：決定方向 (1b) 或 (3)、頁面層或同列、N2 情況、與 W-B2LS／W-B2LSf 的先後；再由 creative-lead／PM 擬稿，送風控逐字定稿。
3. **tech-architect**：風控定向之後，出 ADR-0035 補充五，寫明述詞、讀取點、不屬 R-4 的判定，以及第 5 點的約束。若選同列 note，一併處理 S-3 固定項。
4. **dev-lead**：等 N-168 合進 product 之後，從 product 開分支實作，不得與 N-168 並行修改 `evaluate_today`、`same_day_warnings`、`_lines`。
5. **qa-automation**：重現無標示 S2 與逐批 S1 兩個情境。
6. **CEO**：本單現階段不需要裁決。只有在有人主張方向 (2)，或風控要求改變行為而不只是揭露時，才要升級 CEO，因為那會與 ADR-0035 Decision 4 及 CEO #83 衝突。

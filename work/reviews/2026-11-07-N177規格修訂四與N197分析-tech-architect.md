# N-177 規格修訂四與 N-197 並發分析

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- **N-196 的三項 required 都已寫進修訂四**，修訂四全文在第二節。
  - 3.9 第 4 點的回復條款，逐字照風控 2(e) 第 3 項。
  - C8 改成可以檢查的寫法。
  - R-3′「已修正」註記照 2(e) 第 2 項逐字寫入，並標明要等 N-196 合入 product 之後，才由 tech-writer 落檔。
- **C8 的驗證方式有一個衝突，需要風控確認。** 依 `scripts/validate_agents.py:65` 的 `READONLY_ALLOWED_BASH` 與 `.claude/agents/qa-reviewer.md:4`，qa-reviewer 只能執行 `codex` 和 `git diff`，不能執行 `git merge-base`。
  - 修訂四改走「執行與判斷分離」：dev-lead 和 coordinator 各自執行 `git merge-base --is-ancestor`，把輸出附在紀錄上；qa 讀兩份輸出下判斷，另外用 `git diff` 檢查 N-177a、N-195 的內容確實在 base 裡。
  - 要讓 qa 自己執行，需要我出 ADR、CEO 核可。本修訂沒有提出這一點。
- **四項 suggested 全部採用。**
  - T17 改為「`count("None")` 等於例外列的筆數 n」，網格加一組 n ≥ 2。
  - T22 加 (c′)，把 AST 掃描範圍擴大。
  - 3.9 新增第 5 點，記下 REBALANCE_BLOCKED 的字面在競態路徑上不精確。
  - T4 的 hook 改成「只觸發一次，而且只在讀交易內觸發」。
- **N-197 (a)，`confirm_rules` 與 REBALANCE 並發：風控的初判成立。**
  - 只有一種交錯有問題：REBALANCE 讀完 snapshot 之後、寫入之前，`confirm_rules` 寫入了資金。
  - N-195 之後，在使用者調降資金（X < C0）時，TOTAL_DEPLOY 會比兩種循序結果的較大者再高 (C0 − X)·r。
  - `active_params` 的版本交錯不會產生額外偏差。
  - 事後從 DB 偵測不到。
  - 修法採用風控提的方向，並做兩點強化：比對三個 TOTAL_DEPLOY 鍵的原始字串，比對和寫入放在同一個 `BEGIN IMMEDIATE` 內。
  - 這個修法另開小單 **N-197a**（暫定編號），排在 N-196 之後，期限最遲第三包。N-196 不改。
- **N-197 (b)，兩個 `/today` 並發造成重複 buy：路徑走得到，現有機制都沒有完全涵蓋。**
  - in-flight 讀取不涵蓋，K1/K2 不涵蓋，N-182 E-2 也不涵蓋。G1 只保護帳冊，在事後揭露。
  - 根源是 F2（claim 與動帳分屬兩個交易，歸 N-169）。
  - 我另外發現一個變體：claim 之後動帳失敗時，不需要並發就會重複出單，而且 G1 擋不住。
  - 這一項不會動到 `rebalance` 或 `set_total_deploy`，所以不必修訂 N-196。是否補揭露、是否提高 N-169 的優先度，由風控決定。

## 二、各部門回報

### tech-architect（唯讀）

這次交付的是修訂四全文。coordinator 請原文附到 `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` 的檔末。

````markdown
## 修訂四（tech-architect，2026-11-07；回應風控 [風控-196]）

- 依據：[風控-196] `work/reviews/2026-11-07-N177修訂三比對與N196spec審查-風控.md`。結論是 CONDITIONAL APPROVE：N-196 spec 核可，附三項 required；3.9 第 3 點接受為 R-4′；`confirm_rules` 的交錯要 TA 分析。
- 程式依據：同本檔第 6 行的 checkout，只讀，未執行。行號以內容定位。前端只用 grep 查證事實，沒有改動。
- 本修訂只取代或新增下面點名的段落，其餘維持修訂三。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀；標 [待風控] 的需要風控裁示。
- 修改處索引見第 6 節。

### 0. 風控審查結果的登錄（不改判斷）
- N-196 spec 已核可，附三項 required，見第 1 節。C8 由 suggested 提升為 required，風控確認這是條件 1 能夠生效的前提。
- 3.9 第 3 點不另開單，接受為已知殘留。tech-writer 已落檔為 ADR-0041 R-4′（ADR-0041:107）。我目視比對過，與風控原文一致。
- CEO 通知的補充句由 coordinator 送達，最遲在下一次 REBALANCE 之前，本修訂不轉錄。前端名稱的事實見 3.6。

### 1. N-196 的修訂（required 與 suggested）

**1.1 3.9（第 3 點取代；新增第 4～6 點；第 1、2 點與末點不變）**
- 第 3 點（取代）：`evaluate_today` 在 :1901 讀批次、在 :1902 讀現金，分屬兩個連線。風控 2026-11-07 裁示接受為已知殘留、不另開單，已落檔為 ADR-0041 R-4′，含失效條款。N-196 不擴充（C10）。`evaluate_today` 日後若改用單一讀交易，依 C7 回 TA，並回風控審。
- 第 4 點（新增；逐字照 [風控-196] 第二節 2(e) 第 3 項）：「若 N-177a 的 R-α 被回退，而 N-196 保留，R-3′ 回到未修正狀態：coordinator 要通知風控，風控第二節第 5 點的 CEO 內部通知也恢復有效。」
- 第 5 點（新增；[風控-196] 2(f) suggested，採用）：
  - T3 的競態路徑（重讀後才出現、沒有載入日線的標的）會回 `REBALANCE_BLOCKED`。字面寫的是「{symbols} 沒有可用收盤價」，但在這條路徑上，資料其實有，只是這一輪沒有載入，所以字面不完全精確。
  - 方向是拒絕、不寫入，重跑一次就會恢復，沒有隱藏風險。依 C5，字面維持不改，列為已知限制。
- 第 6 點（新增）[TA 補]：
  - 第 1 點說「snapshot 之後、寫入之前 commit 的結算，等於循序」，這只適用於結算。
  - 同一個窗口內若有 `confirm_rules` 的 `set_capital` commit，結果不等於任何循序執行，見本修訂第 3 節。
  - N-196 不處理這一點（C10），由 N-197a 處理。修好之前，以風控補充的 CEO 通知揭露。

**1.2 N196-C8（取代；可檢查）**
- 實質要求不變：
  - PR 的 base 必須同時含 N-177a（R-α）與 N-195；
  - PR 在 N-195 合入 product 之後才開，不得與 N-195 並行修改 `rebalance`。
- `<base>` 的定義：以 qa 審查當下的 PR head 為準，`<base>` = `git merge-base <product 分支> <N-196 PR head>`。如果合入前又 merge 了最新的 product（C9），就以新的 head 重新計算。
- PR 說明必須列出：
  - N-177a、N-195 在 product 上的 merge commit，完整 40 碼 SHA，附 PR 編號；
  - `<base>` 的 SHA。
- 驗證條件，兩項都要成立：
  - `git merge-base --is-ancestor <N-177a merge commit> <base>` 的 exit code 為 0；
  - `git merge-base --is-ancestor <N-195 merge commit> <base>` 的 exit code 為 0。
- [TA 補，待風控確認執行方式] 執行與判斷分離：
  - 依 CLAUDE.md §4 與 `scripts/validate_agents.py` 的 `READONLY_ALLOWED_BASH`，qa-reviewer 目前只能執行 `codex` 與 `git diff`，不能執行 `git merge-base`。
  - **執行**：
    - (i) dev-lead 在 PR 說明附上兩條指令、stdout 與 exit code；
    - (ii) coordinator（或 devops-sre）在自己的 checkout 上獨立重跑，把輸出記在本案的審查紀錄（`work/reviews/`）。
  - **判斷**：qa-reviewer 比對 (i) 與 (ii) 的 SHA 和 exit code，再用 `git diff` 做內容旁證：
    - `git diff <N-177a merge commit> <base> -- apps/stock-desk/backend/app/playbook/store.py` 不得出現刪除 `_settle_batch_line`、`_settle_s2_fill`，或 `playbook_fill_moves` DDL 的 hunk；
    - `git diff <N-195 merge commit> <base> -- apps/stock-desk/backend/app/playbook/` 不得出現刪除 `set_total_deploy` 的 hunk。
  - 兩份輸出缺任何一份、彼此不一致，或旁證不成立，都判 BLOCKING。
  - 若要改由 qa 直接執行 `git merge-base`，要把它加進 `READONLY_ALLOWED_BASH`，這需要 TA 出 ADR、CEO 核可。本修訂不提出。
- **QB-N196-2（新增，BLOCKING）**：C8 的 SHA、兩份輸出與 `git diff` 旁證都要齊備，而且都成立。

**1.3 ADR-0041 R-3′「已修正」註記（交 tech-writer；時點受限）**
- 時點：N-196 以 merge commit 合入 product 之後才能落檔，由 coordinator 確認 merge commit 後通知 tech-writer。合入之前不得落檔。
- 位置：ADR-0041 Consequences 的 R-3′ 那一點（ADR-0041:106）末尾，作為補註。
- 逐字（照 [風控-196] 第二節 2(e) 第 2 項）：「R-3′ 由 N-196 修正；此修正以 N-177a 的 R-α（每筆結算的股數與現金在同一交易內 commit）為前提。」
- 時點要分清楚：
  - 這則註記在**合入**時落檔；
  - 風控第二節第 5 點的 CEO 內部通知，依 3.9 末點，維持到 N-196 **部署**為止。
- [TA 補] N-196 本身若被回退，coordinator 要請 tech-writer 撤回這則註記，並通知風控。R-α 被回退的情況，依 3.9 第 4 點處理。

**1.4 N196-T4（修訂；[風控-196] 2(f) suggested，採用）**
- 包裝 `_read_all_batches` 的 wrapper 改為：
  - 先呼叫原函式。
  - 只有在「hook 尚未觸發，而且 `conn.in_transaction` 為真」時，才執行 hook。後者表示這次呼叫位在 `read_rebalance_inputs` 的 DEFERRED 讀交易內；`list_batches` 的自動提交讀取不會觸發。
  - 先設旗標、再執行 hook。hook 執行期間如果有重入的呼叫（例如 B 端或 fixture 經由 `list_batches`），一律直接走原函式，不再觸發。
- 測試結束時斷言 hook 恰好觸發一次。觸發次數為 0 或大於 1，都算失敗。
- 其餘斷言不變，效力證明併入 QB-N196-1，也不變。

### 2. N-177b 的 suggested（[風控-196] 第二節第 1 點第 4、6 項；採用）

**2.1 N177b-T17 追加斷言第 3 點（取代）**
- 原句「該元素中『None』只出現一次（`count("None") == 1`），而且出現在『第 None 批』裡」，改為：
  - 設 n 為該次結算中 `is_c11_exception` 為真的列數（n ≥ 1）；
  - 斷言 N2 元素滿足 `count("None") == n`，而且 `count("第 None 批") == n`。
  - 兩者相等，就表示每一次「None」都出現在「第 None 批」裡。依據是 wording.py:956 的 `SETTLEMENT_EXIT_ITEM` 會組出「第 {batch_no} 批」。
- [TA 補] 網格至少要有一次結算的 n ≥ 2，也就是兩筆 `batch_no` 為 None 的 EMERGENCY executed sell，symbol 或預定執行日不同，讓泛化後的斷言真的被執行到。
- 其他斷言不變：恰好一個元素含「None」，而且它就是 N2；逐字等於格式化結果；其他元素不含「None」；fixture 不得含「None」。

**2.2 N177b-T22（追加 (c′)；(a)(b)(c) 不變）**
- 掃描範圍：`app/playbook/**`，以及 `app/` 內任何 import 了 `Directive` 的模組（以 AST 的 import 判定，不寫死清單）。
- (c′-1) EMERGENCY 名稱集合：範圍內模組層級以 Assign 或 AnnAssign 綁定到 `ast.Constant("EMERGENCY")` 的名稱，由測試計算，不寫死。現況只有 store.py:291 的 `EMERGENCY_RULE_ID`。
  - `Directive(...)` 的 `rule_id=` 值符合以下任一種，就算作 EMERGENCY 建構：
    - `ast.Constant("EMERGENCY")`；
    - `ast.Name`，id 屬於上述集合；
    - `ast.Attribute`，attr 屬於上述集合。
  - 範圍內的總數恰好一處，就是 (c) 的那一處。
- (c′-2) `X.model_copy(update=<Dict 字面>)` 的 Dict 中，含鍵 `"batch_no"` 或 `"rule_id"` 的呼叫，數量為 0。
  - 現況我 grep 過：`app/` 內 `"batch_no":` 為 0 處；`"rule_id":` 只有 `app/api/alerts.py:261` 一處，是回應用的 dict，不是 `model_copy`。
  - `"rule_id"` 是我加的 [TA 補]：把別的 Directive 複製成 EMERGENCY，也是同一種繞過。
- (c′-3) 無法靜態判讀的形式，以 baseline 釘住，只准調低：
  - `Directive(...)` 帶 `**` 展開，或 `rule_id=` 的值不是 Constant、Name、Attribute；
  - `model_copy(update=...)` 的 update 不是 Dict 字面，或 Dict 帶 `**` 展開。
  - 以具名常數列出 (檔案, 函式, 計數)，PR 附上對 N-177b base 的實測值，比照 T21。N-177a 的 R-α 會改寫 store.py 的 `_update_batch` 與 settle 的 sell 分支，所以 base 的計數要實測，不能沿用本 checkout。
  - 調高要回 TA。
- 失敗時，依 N177b-C13 的回復條款處理。

### 3. N-197 (a)：`confirm_rules` 與 REBALANCE 並發（[風控-196] 第二節第 4 點）

**3.1 程式事實（只讀）**
- REBALANCE（`service.rebalance`，:1516 起）的步驟：
  - R1：:1535 `list_batches`，只用來決定 symbols；
  - 載入日線，數秒級；
  - **R_s**：snapshot 讀取。N-196 之前是 :1538 `portfolio_state()`；N-196 之後是 `read_rebalance_inputs()`。讀到現金 C0、持股，以及 TOTAL_DEPLOY 的三個鍵；
  - R_p：:1539 `active_params(as_of)`，獨立連線；
  - 純計算：TA = C0 + D，TD′ = TA·r；
  - **R_w**：寫入。N-195 之前是 :1612 `set_capital(cash=C0, total_deploy=TD′, source=REBALANCE_SOURCE)`，四個鍵；N-195 之後是 `set_total_deploy`，三個鍵。
  - R_s 到 R_w 之間沒有網路，窗口是毫秒級。
- `confirm_rules`（:1722-1739）的步驟，每一步各開連線、各自一個交易：
  - C_a：`rule_set_authorship`。
  - 尚未確認過時，另外執行：
    - `active_params`，這時回的是 `system_default_params`（store.py:724-732，`RuleParams(effective_date=on_date)`）；
    - `next_version`；
    - `_evaluation_data_date`：`list_batches` 加上日線與指數載入，數秒級；
    - **C_α**：`confirm_rule_set`。交易 α 以 `INSERT OR REPLACE` 寫 params 列；交易 β 由 `_set_state` 寫 confirmed_at 與 version（store.py:1098-1123）。
  - **C_p**：:1733 `active_params(as_of)`。
  - **C_w**：:1734 `set_capital(cash=X, total_deploy=X·r, source=CONFIRMATION_SOURCE)`，單一交易寫四個鍵（store.py:945-967、:925-927）。
  - `_rule_set_status`：回應中的 portfolio 在 C_w 之後讀取。
- 符號定義：C0 是 R_s 讀到的現金；X 是使用者送出的資金；D 是 R_s 讀到的持股以收盤估值；r 是 deploy_ratio；t_r、t_c 是兩者的寫入時刻。
- 循序結果：
  - S1（先確認、再 REBALANCE）：現金 X，TD = (X + D)·r，source 為 rebalance，set_at 為 t_r。
  - S2（先 REBALANCE、再確認）：現金 X，TD = X·r，source 為 user_confirmation，set_at 為 t_c。

**3.2 交錯表：N-195 之前（現行 production）**

| # | C_w 的位置 | 可能的起始先後 | 最終現金 | 最終 TD | source／set_at | 等於 | 偏差 |
|---|---|---|---|---|---|---|---|
| 1 | C_w < R_s | confirm 先開始；或 REBALANCE 先開始，但還在載入日線 | X | (X+D)·r | rebalance／t_r | S1 | 無 |
| 2 | R_s < C_w < R_w | 兩邊都可能先開始。首次確認在 C_w 之前也有數秒的日線載入，所以「confirm 先開始」也可能落在這一列 | **C0**（X 被蓋回） | (C0+D)·r | rebalance／t_r | 都不是，等同「這次確認沒有發生」 | 使用者剛填的資金無聲消失。confirm 回應若在 R_w 之前讀 portfolio，會顯示 X。X < C0 時，現金與 TD 都偏高，鐵律①的 budget 也以 C0 計算，方向不保守；X > C0 時兩者都偏低 |
| 3 | R_w < C_w | REBALANCE 先開始 | X | X·r | user_confirmation／t_c | S2 | 無 |

- 第 1、3 列仍有 R-1′（REBALANCE 寫回現金，蓋掉並發結算），那是另一件事，由 N-195 修正。

**3.3 交錯表：N-195 之後（N-196 前後相同，只差 R_s 的位置）**

| # | C_w 的位置 | 最終現金 | 最終 TD | source／set_at | 等於 | 偏差 |
|---|---|---|---|---|---|---|
| 1 | C_w < R_s | X | (X+D)·r | rebalance／t_r | S1 | 無 |
| 2 | R_s < C_w < R_w | X | **(C0+D)·r** | rebalance／t_r | 都不是 | TD 與 S1 相差 (C0 − X)·r，見 3.5 |
| 3 | R_w < C_w | X | X·r | user_confirmation／t_c | S2 | 無 |

**3.4 `confirm_rules` 自身的非原子序列，以及與 R_p 的版本交錯**
- 首次確認的路徑：
  - 尚未確認時，`playbook_rule_params` 一定是空的。`rule_set_authorship` 只要有任何一列 params，就判定為已確認（store.py:1085-1088）。
  - 所以 C_α 寫入的 payload，是 `system_default_params` 的複本，只改了 version 與 effective_date（service.py:1724-1731）。
  - R_p 落在交易 α 之前，讀到系統預設；落在 α 之後，讀到新列。兩者的 deploy_ratio 相同，所以 TD 不受影響。
  - R_s 是否看得到交易 β 的 confirmed_at／version 鍵，REBALANCE 都不使用。
- 已確認過的路徑：`confirm_rules` 不寫 params，C_p 和 R_p 都是單句 SELECT。
- 第三方的參數變更：鐵律④規定變更在下一個交易日才生效，所以同一個 as_of 讀不到。
- 唯一的例外是兩次呼叫跨過 UTC 日界，as_of 不同。這時兩邊各自採用自己當天生效的版本，與循序執行相同，不產生新的偏差類型。
- 結論：
  - 版本交錯不產生額外偏差，偏差只來自 C_w 的位置（第 2 列）。
  - N196-C5 讓 `active_params` 留在 snapshot 之外，這個安排是安全的。
  - [TA 補，範圍外] 兩次首次確認並發時，兩邊會取到同一個 `next_version`，`INSERT OR REPLACE` 之後只會留下一列，不影響 REBALANCE。

**3.5 偏差方向與影響面（第 2 列，N-195 之後）**
- TD − max(S1, S2) = (C0 − X)·r。理由是 D ≥ 0，所以 S1 ≥ S2。
  - X < C0（調降資金）：TD 高於兩種循序結果，方向不保守，而且鎖定到下一次 REBALANCE 或下一次 `confirm_rules`。
  - X > C0：TD 低於 S1。若 C0 + D < X，也低於 S2，偏保守；否則介於兩者之間。
- 影響途徑：TD 只進入 `planned_batch_shares`（engine.py:176-205，每批金額 = TD ÷ n_targets ÷ 3），也就是 R1 的每批股數會偏大。
- N-195 之後，鐵律①（engine.py:1021-1027，`budget = cash − 0.3 × 總資產`）用的是正確的現金 X，所以 30% 現金底線仍然成立。偏差只放大每批股數，最多放大到底線為止。N-195 之前，底線本身就以錯誤的 C0 計算。
- 首次確認的情況：確認前 C0 = 0（`STATE_CASH` 只由 `set_capital` 建立；REBALANCE 寫回的也是 0），D = 0（確認前沒有 R1，不可能有 open 批次）。
  - N-195 之後：TD = 0，偏保守。但 R1 的每批股數會因為 `max(1, …)` 變成 1 股，直到下一次 REBALANCE 為止。
  - N-195 之前：現金被寫回 0，所有買單都依 `SHRINK_TO_ZERO_NOTE` 被剔除，使用者看得到。
  - 這兩種情況在前端都沒有自行修正的入口，見 3.6。

**3.6 頻率（讀碼與前端 grep 的事實）**
- 前端沒有任何呼叫 `POST /api/playbook/rebalance` 的 client。frontend/ 內 grep「rebalance」為 0；「REBALANCE」只出現在 `types.ts:1699` 的 rule id 型別。所以 REBALANCE 目前只能由使用者直接呼叫 API。
- 資金輸入的 UI（`RuleSetConfirmPanel.tsx`，按鈕「確認規則集並設定資本額」）只在 `mode === "unconfirmed"` 時渲染（`playbookView.ts:322-324`、`page.tsx:204`）。確認之後再改資金，也只能直接呼叫 API。
- 所以只用 UI 時，首次確認的 X ≥ C0 = 0，走不到不保守的分支。不保守的分支需要「已確認之後，以 API 調降資金」，同時「以 API 執行 REBALANCE」，而且寫入要落在毫秒級的窗口內。
- 判定：頻率極低。依風控 5.6 的同一理由，頻率低不構成免修的理由。
- 給 coordinator：CEO 通知中「資金確認」與「執行 REBALANCE」的對應名稱，以上事實可供參考。若因為沒有 UI 入口而無法只改名稱，依風控規定回風控，不得改意思。

**3.7 可偵測性**
- N-195 之後的第 2 列，與第 1 列的狀態形狀相同：source 都是 rebalance，set_at 都是 t_r，現金都是 X，只有 TD 的值不同。要區分兩者，需要 R_s 當時的 C0 與 D。
  - 現金沒有異動歷史（ADR-0035 Decision 9）；
  - D 只出現在 REBALANCE 的回應裡，只有超額時才落成指令列的 rule_summary；
  - `confirm_rules` 的 set_at／source 被 R_w 覆寫。已確認過的再次確認不留其他落檔紀錄：`STATE_RULE_SET_CONFIRMED_AT` 與 params 的 `submitted_at` 只在首次確認時寫入。
- 判定：`set_at`、`source` **不足以事後辨識**，DB 內沒有可以回推的資料。N-195 之前的第 2 列，只有使用者自己記得填過的金額時，才可能察覺。

**3.8 候選修法比較**

| 方案 | 內容 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| F-a 戳記比對（風控方向，TA 強化） | `set_total_deploy` 在單一 `BEGIN IMMEDIATE` 內，讀取 TOTAL_DEPLOY 三個鍵的原始字串，與 N-196 snapshot 讀到的值比對；相同才寫入，不同就不寫入，並揭露 | 加法，不動 N-196 的讀交易；結算不寫這三個鍵，所以不會誤拒，3.9 第 1 點的語意維持；結果一定等於某一個循序執行，或「REBALANCE 未執行」 | 新增一個拒絕狀態與一句字面（creative-lead 擬稿、風控逐字）；models 的 Literal 做加法；局部取代 N195-C4 | 低 | **採用**，另開 N-197a |
| F-a′ 戳記比對加自動重試 | 拒絕寫入後重讀、重算一次 | 使用者不必重跑 | 等於替使用者無聲選定 S1 的順序 | 中 | 否決 |
| F-b 單一寫交易 | REBALANCE 的讀、算、寫都在一個 `BEGIN IMMEDIATE` 內（`commit_emergency_exit` 的模式） | 永遠等於某一個循序執行；沒有拒絕路徑，也沒有新字面 | 推翻已核可的 N-196（C2 規定 DEFERRED、T4「寫入者不被擋」、T5）；估值要在寫鎖內做；要重送風控，N-196 可能趕不上 R2 | 中 | 現在否決，保留為日後方向 |
| F-c confirm 端偵測 | confirm 寫入前，檢查是否有 REBALANCE 正在進行 | — | 沒有「進行中」的標記，要新增 state 鍵與清除邏輯；當機時標記會殘留 | 中高 | 否決 |
| F-d 行程內鎖 | service 層用 `threading.Lock` 包住兩者 | 簡單 | 只在單一行程內有效（R-β 先例）；SQL trace 看不到，qa 無法檢查 | 中 | 否決 |
| F-e 接受為殘留 | 只靠 CEO 通知 | 零改動 | TD 是風險上限，偏差不保守、鎖定一季；事後偵測不到 | 中 | 不建議；若 CEO 決定採用，風控已表示會書面保留不同意見 |

- 對風控方向的評估：方向成立，TA 做三點強化。
  - (1) 比對三個鍵（TD、set_at、source）的原始字串，不只比 set_at，也不比解析後的值。這樣可以避免時間戳解析度造成的 ABA；Windows 上 `datetime.now` 的解析度我沒有查證。三個值完全相同，就表示資金宣告等價，不會造成實害。
  - (2) 比對與寫入必須在同一個寫鎖交易內，否則「先檢查再寫入」本身又是一個競態。
  - (3) 戳記取自讀取現金的同一個 snapshot，N-196 的 state 讀取本來就含這三個鍵。
- 為什麼戳記就夠：
  - N-195 之後，結算以外的現金寫入者只剩 `set_capital`。依 N177a-T19，`set_cash` 在 `app/` 內沒有呼叫點；依 N195-T6，`set_capital` 只在 `confirm_rules` 被呼叫。
  - `set_capital` 在同一個交易內寫戳記（N195-C4）。
  - 所以「戳記不變」等價於「snapshot 之後沒有資金宣告寫入」。

**3.9 N-197a spec 草案（暫定編號，coordinator 登錄時可改；送風控審）**
- 定位：
  - 小單，負責 dev-lead。base 必須含 N-195 與 N-196，以 N196-C8 的同一種方法驗證。
  - 期限：最遲與第三包同一個 release。R2 延後期間不得單獨出 release，也不屬於 hotfix。
  - 不擋 N-196，也不擋 R2。
  - 在 N-197a 上線之前，第 2 列是殘留，以風控補充的 CEO 通知揭露，並登錄 ADR-0041 R-5′（第 5 節草稿）。
- store.py（各只有一份定義）：
```python
class TotalDeployStamp(NamedTuple):
    """The three TOTAL_DEPLOY keys exactly as stored; None where a key is absent (N-197a)."""

    total_deploy: str | None
    set_at: str | None
    source: str | None


class TotalDeployWrite(NamedTuple):
    """What :meth:`PlaybookStore.set_total_deploy` found under the lock, and whether it wrote."""

    written: bool
    found: TotalDeployStamp


def _total_deploy_stamp(state: Mapping[str, str]) -> TotalDeployStamp: ...
    # the three keys STATE_TOTAL_DEPLOY / _SET_AT / _SOURCE, raw, None if absent


def _read_total_deploy_stamp(conn: sqlite3.Connection) -> TotalDeployStamp: ...
    # one SELECT key, value FROM playbook_state WHERE key IN (?, ?, ?); then _total_deploy_stamp
```
  - `RebalanceRead` 加法新增 `stamp: TotalDeployStamp`。`read_rebalance_inputs` 內只讀一次 `state = _read_state_map(conn)`，同時交給 `_portfolio_from_state` 與 `_total_deploy_stamp`。仍然只有兩句 SELECT，N196-C2 不變。
  - `set_total_deploy` 取代 N-195 5.3 的簽名，`expected` 是必填，沒有預設值：
```python
    def set_total_deploy(
        self, *, total_deploy: Decimal, source: str, expected: TotalDeployStamp,
        at: datetime | None = None,
    ) -> TotalDeployWrite:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                found = _read_total_deploy_stamp(conn)
                written = found == expected
                if written:
                    _write_state(conn, _total_deploy_state(total_deploy, source, at))
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        return TotalDeployWrite(written=written, found=found)
```
- service.py `rebalance`：只改 N-195 那一個呼叫，並新增拒絕分支：
```python
        write = self._store.set_total_deploy(
            total_deploy=new_total_deploy, source=REBALANCE_SOURCE, expected=book.stamp
        )
        if not write.written:
            message = wording.REBALANCE_SUPERSEDED.format(...)  # fields below
            return RebalanceResult(
                executed_at=as_of, status="superseded", total_assets=None,
                previous_total_deploy=Decimal(write.found.total_deploy or "0"),
                new_total_deploy=None, deployed_value=None, overshoot=None,
                directives=[], message=message, warnings=[message],
            )
```
- models.py：`RebalanceResult.status` 改為 `Literal["ok", "insufficient_data", "superseded"]`，只做加法。
  - `app/api/playbook.py:189` 的 `RebalanceResponse.status` 是 `str`，零 diff。
  - 前端沒有使用這個回應（3.6），零 diff。
- 字面：識別名暫定 `REBALANCE_SUPERSEDED`，只放在 wording.py，由 creative-lead 擬稿、風控逐字定稿。
  - 可用欄位：`found.total_deploy`（格式 .2f）、`found.set_at`。
  - 只陳述事實：本次 REBALANCE 執行期間，TOTAL_DEPLOY 已被另一項操作改寫；本次沒有寫入任何值；目前的 TOTAL_DEPLOY 是多少；要以目前的資金重算，需要再執行一次 REBALANCE。
- 約束 N197a-C1～C10（qa-reviewer 逐條檢查）：
  - **C1 diff 範圍**：
    - store.py：上面兩個型別、兩個 helper、`RebalanceRead` 的欄位、`read_rebalance_inputs` 內共用 state map、`set_total_deploy`；
    - service.py `rebalance`：只有該呼叫與拒絕分支；
    - models.py：Literal 加法；
    - wording.py：一個常數；
    - `tests/**`。
    - engine.py、`app/api/**`、`app/data/**`、`app/services/**`、frontend 零 diff。
  - **C2 交易**：
    - 一個連線、一個 `BEGIN IMMEDIATE`；
    - 對 `playbook_state` 恰好一句 SELECT，只限三個鍵；
    - 接著 0 句或 3 句 upsert（經 `_write_state`），然後 `COMMIT`；
    - 沒有其他語句，不呼叫其他 `self.*`，沒有網路；錯誤處理照 C-11。
  - **C3 比對**：三個原始字串（鍵不存在為 None）全部相等才寫入。不比對現金，不比對解析後的值。
  - **C4 rebalance**：
    - `set_total_deploy(` 恰好一次，`expected=` 只能是 `book.stamp`，`book` 是同一次 `read_rebalance_inputs()` 的結果；
    - 不重試、不重讀；
    - 拒絕時不呼叫 `record_directives`，也沒有其他寫入。
  - **C5**：`set_capital`、`confirm_rules` 零 diff。confirm 維持無條件寫入，也就是後寫者為準（W9）。
  - **C6 不變式**：`app/` 內結算 helper 以外，任何寫 `STATE_CASH` 的函式，都必須在同一個交易內寫入三個 TOTAL_DEPLOY 鍵（現況只有 `set_capital`）。新增這類寫入者時，要回 TA 與風控。
  - **C7**：N196-C2、C3、T4、T5 不變。N195-C4「不加 `BEGIN IMMEDIATE`」只對 `set_total_deploy` 失效；`_set_state`、`_write_state`、`set_capital` 不變。
  - **C8**：base 與先後依 N196-C8 的同一種方法驗證，對象改為 N-195、N-196 的 merge commit。
  - **C9**：獨立 PR，以 merge commit 合入；不得併入其他單；合入前 merge 最新的 product（不得 rebase），之後重跑完整 CI 與 seam。
  - **C10**：字面在風控逐字定稿之前不得合併，PR 以程式從風控原檔逐字比對。
- 測試 N197a-T1～T9（全部 BLOCKING；用真實 `PlaybookStore`、檔案型 DB）：
  - **T1 循序**：N195-T1～T7、N196-T1～T7 原樣綠燈。只有直接釘住 N195-C4 的斷言可以修改，要逐條列在 PR 說明，交 qa 判定。
  - **T2 決定性交錯**：
    - A 跑 `rebalance`。把 A 的 `_connect` 換成自訂 factory，在 `set_total_deploy` 的 `BEGIN IMMEDIATE` 送出之前，以另一個 store／service 實例 B 完成 `confirm_rules(capital=X)`。
    - 參數化 X < C0、X > C0、X = C0。X = C0 時 set_at 不同，仍然要拒絕。
    - 斷言：`status == "superseded"`；最終四個鍵逐字等於 B 寫入的值；沒有 REBALANCE 指令列；`message` 逐字等於格式化後的字面。
  - **T2 的效力證明**：PR 說明附上本機輸出，顯示把比對暫時拿掉、改成無條件寫入時，三個參數都失敗，TD 變成 (C0 + D)·r。這份對照不 commit（比照 QB-11）。
  - **T3**：同一個注入點改為由 B 完成一筆逐批 S1 結算 → `status == "ok"`，寫入成功，最終現金 = C0 + 該筆入帳。這證明結算不會造成誤拒。
  - **T4**：同一個注入點改為由 B 完整跑一次 REBALANCE → A 被拒，最終狀態等於 B 寫入的值。
  - **T5（寫鎖序列化）**：在 A 的比對 SELECT 之後、upsert 之前，另開執行緒跑 B 的 `confirm_rules`。B 的 `set_capital` 要等到 A commit 之後才完成，而且在 busy_timeout 內完成。最終結果等於 S2。
  - **T6 SQL trace**：比對交易的語句序列，依 C2。三個 upsert 的參數都不含 `STATE_CASH`。
  - **T7 AST**：
    - `set_total_deploy` 的 `expected` 沒有預設值；
    - `app/` 內 `set_total_deploy(` 只出現在 `rebalance`；
    - `expected=` 的運算式是 `book.stamp`。
  - **T8**：snapshot 時三個鍵都不存在、寫入時仍然不存在 → 寫入成功。snapshot 時不存在、窗口內 B 完成首次確認 → 拒絕。
  - **T9**：字面逐字比對風控原檔。
- QB-N197a-1：T2 的效力證明附在 PR 說明。

### 4. N-197 (b)：兩個 `/today` 並發時的重複 buy（[風控-196] 第二節第 3 點「另外的觀察」）

**4.1 路徑走得到嗎：走得到（讀碼推論，未實跑）**
1. A、B 兩個請求都已確認規則，同時 `GET /today`。API 是同步的 `def`（`app/api/playbook.py:582`），在 threadpool 中並行，沒有任何鎖。
2. 有一筆到期的 R1 buy r：批次 k 是 planned，預定執行日 E ≤ as_of，E 的開盤 bar 已存在。
3. B 執行 `claim_directive(r)` 並 commit（store.py:1453-1460，單句 UPDATE；r 變成 settled=1、executed）。
4. A 跳過 r，有兩種情形：
   - A 的 `pending_directives` 在第 3 步之後才讀，r 不在清單內；
   - 或 A 的 claim 回 False，`batch_blocking_claim` 回 None（因為 settled=1），A 執行 `continue`（service.py:1339-1356）。
5. B 的 `settle(r)` 尚未 commit：
   - N-177a 之前，要到 `save_batch` 才把 k 改成 open（store.py:1521-1557，五個連線）；
   - N-177a 之後，要到 `_settle_batch_line` 的 COMMIT。
6. A 執行 :1861 `read_in_flight` → :1862 `list_batches` → :1864-1865 載入日線與指數 → :1898 `roll_peak_closes` → **:1901 `list_batches`，讀到 k 仍是 planned**。
   - 只有 :1901 會進入 engine。:1862 只決定要載入哪些 symbol，而且本來就包含 planned 批次。
   - 所以 B 的 commit 若落在 :1862 與 :1901 之間，A 會讀到 open，等同循序執行，沒有問題。
7. engine 這邊：若 data_date 是排程日（週二或週四，而且是交易日；`calendar.py:52`、`:87-89`），而且 `entries_allowed`（正常模式、指數可用；engine.py:1168），`_next_planned_batch`（engine.py:722-734）會選中 k。若 k 沒有被 R2／R3 處理，就產出 R1 buy，預定執行日 E_A = next_trading_day(data_date) > E。
8. A 執行 `commit_evaluation`：K1 是 `(s, k, R1, buy, E_A)`，K2 是 `(s, E_A)`，都是新的鍵，所以這張 buy 會寫入。
- data_date 是排程日的情況：使用者在 E 當天沒有開 `/today`，到之後的排程日才開；或休市讓 E 落在週二或週四。依日常用法，這不罕見。
- 窄的條件在第 5、6 步之間：B 從 claim commit 到動帳 commit 只有毫秒級，A 卻要經過兩次日線載入（即使命中快取，也比 B 的窗口長）。B 必須停頓得比這段更久，例如等寫鎖（busy_timeout 5 秒）、執行緒排程，或磁碟慢。
- **[TA 補] 失敗變體**：B 在 claim 之後動帳失敗，例如 `database is locked`、行程終止，或 N-177a 之前在 `set_cash` 與 `save_batch` 之間失敗。這時 k 會一直停在 planned，**不需要並發**，之後的排程日也會對 k 再出 R1。而且這時 G1 不會擋（k 仍是 planned），帳冊只記一次成交。

**4.2 現有機制是否涵蓋**

| 機制 | 涵蓋嗎 | 理由 |
|---|---|---|
| in-flight 讀取（:1861） | 否 | 只讀 settled=0 的列，而 r 在第 3 步之後是 settled=1；而且 in-flight 不是 engine 的輸入，engine 的批次來自 :1901 |
| K1／K2（`commit_evaluation`） | 否 | 鍵含預定執行日。E 的開盤 bar 存在，所以 E ≤ data_date < E_A，鍵不同 |
| N-182 E-2 | 否 | E-2 處理的是揭露：前提是同一批已經有兩筆買單，ENTRY／A 誤述其中一筆。本路徑是**產生**那第二筆買單。產生之後，A 的回應有可能觸發 E-2 那一種誤述：`blocked` 取自 :1861，當時 k 仍是 planned。這一點是讀碼推論，我沒有逐字核對 `same_day_warnings` 的觸發條件 |
| G1（ADR-0035 Decision 6′） | 部分 | 只保護帳冊：E_A 的結算會被 G1 拒絕（k 已是 open），列入 unsettled，附 `SETTLEMENT_BATCH_ALREADY_FILLED_NOTE`（wording.py:963-969，已寫明「若已買進且成交，你在券商的這檔持股可能多於帳冊所記」），之後每次結算都會再列出。但這是事後揭露，指令已經送到使用者手上。失敗變體不受 G1 保護 |
| F2／N-169 | 根源 | 這是 claim 與動帳分屬兩個交易時，被並發讀取者看到的那個窗口。追蹤清單 N-169 只把 F2 登錄為 low，沒有寫出「對同一批再出 R1」這個後果。我只核對了追蹤清單第 264 列與 ADR-0041:112、:127 |

**4.3 影響**
- 使用者可能在券商多買一批，股數 ≈ TD ÷ n_targets ÷ 3 ÷ 收盤價，帳冊不會記錄。
- 循序執行時，同一個排程日本來就會對 k+1 出 R1。並發時改成對 k 出單，之後的排程日 k+1 照樣會出單。結果是券商持股比帳冊多一批，該檔的配置超出一批。
- 若 k 是最後一批，循序執行時根本不會出單，並發時則多出一張。
- 若 A 的 :1902 也早於 B 的 commit，鐵律①的 budget 會以扣款前的現金計算，比實際寬鬆 r 的成本。
- 可偵測性：
  - 並發變體：DB 中同一批有一筆 executed buy 與一筆被 G1 拒絕的 pending buy，可以查得到；使用者也會看到 G1 的句子。
  - 失敗變體：DB 中有 executed buy，但批次仍是 planned，可以查得到；但使用者看不到任何揭露。

**4.4 修法選項與歸屬**

| 方案 | 內容 | 優點 | 缺點 | 判定 |
|---|---|---|---|---|
| (b-i) 合併 claim 與動帳 | claim 與動帳在同一個 `BEGIN IMMEDIATE` 內（N-169 的 F2 修法） | 根治兩種變體：失敗時兩者都不發生，列維持 pending，之後重試 | 會動到 `claim_directive`／G1 的結構與 `_settle_pending`（ADR-0040 Decision 14 第 3 點、N177a-C2 的零 diff 約束）；要另立 ADR | **TA 建議作為 N-169 的修法方向** |
| (b-ii) 鎖內 G0 守衛 | 在 `commit_evaluation` 的 `_new_decisions` 中，若 (s, k) 已有 settled=1 且 executed 的 buy 列，就不寫這次新的 R1 | 在鎖內判斷是可靠的：第 3 步的 claim 一定已經 commit；不變式「批次是 planned，卻有 executed buy 列」只會出現在 F2 窗口或失敗後 | 動到 ADR-0035 擁有的 K 邏輯；並發變體會讓當天少出單；失敗變體會讓 k 永久停住，需要新的揭露字面 | 只在風控認為 N-169 落地之前不能接受時，才作為過渡方案 |
| (b-iii) 書面殘留 | 登錄 ADR-0041 R-6′ 與 N-169，依靠 G1 的事後揭露 | 零改動 | 並發變體只有事後揭露；失敗變體沒有揭露 | TA 建議現在先採 (b-iii)，修法方向是 (b-i)；要不要補揭露、要不要提高 N-169 的優先度，由風控決定 [待風控] |

- 不動 `rebalance` 或 `set_total_deploy`，所以 N-196 spec 不修訂，也不另開 N-196 的小單。

### 5. ADR-0041 殘留登錄草稿（[待風控]：風控定稿後交 tech-writer，放在 Consequences 的 R-4′ 之後）
- R-5′ 草稿：「R-5′：REBALANCE 讀取 snapshot 之後、寫入 TOTAL_DEPLOY 之前，若 `confirm_rules` 寫入資金，最終現金是新填的資金，TOTAL_DEPLOY 卻依舊現金算出，不等於任何循序結果；使用者調降資金時偏高（N-195 之前，新填的資金還會被蓋回舊值）。事後無法從帳冊辨識。處理：N-197a 在寫入時比對 snapshot 的 TOTAL_DEPLOY 戳記，不一致就拒寫並揭露；期限最遲第三包；修好之前，這個交錯仍在（[TA-177S] 修訂四第 3 節）。」
- R-6′ 草稿：「R-6′：claim 與動帳分屬兩個交易（F2）。並發的 `/today` 若在另一請求 claim 某筆買進之後、動帳 commit 之前讀到批次，會把該批看成仍待買進，排程日可能對同一批再出一張 R1 買進指令；帳冊由 G1 擋下並在之後的結算揭露，但使用者可能已在券商下單。claim 之後動帳失敗時，該批會停在待買進，之後的排程日不需並發也會再出單，G1 不會擋，也沒有揭露。歸 N-169（[TA-177S] 修訂四第 4 節）。」

### 6. 修改處索引（風控比對用）
| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | N-196 3.9 第 3 點（1.1） | 取代：登錄 R-4′ | [風控-196] 二-3 條件 1 |
| 2 | 3.9 第 4 點（1.1） | 新增，逐字 | 二-2(e) 第 3 項 |
| 3 | 3.9 第 5 點（1.1） | 新增：REBALANCE_BLOCKED 的字面不精確 | 二-2(f) suggested，採用 |
| 4 | 3.9 第 6 點（1.1） | [TA 補]：confirm 的交錯不屬於第 1 點 | 二-4、本修訂第 3 節 |
| 5 | N196-C8（1.2） | 取代：列出 SHA、`--is-ancestor` 兩項 exit code 為 0 | 二-2(e) 第 1 項 |
| 5′ | C8 執行與判斷分離（1.2） | [TA 補，待風控確認執行方式]：qa 不能執行 `git merge-base`，改由 dev-lead 與 coordinator 執行，qa 判斷，加 `git diff` 旁證 | CLAUDE.md §4、`READONLY_ALLOWED_BASH` |
| 6 | QB-N196-2（1.2） | 新增 | 二-2(e) 第 1 項 |
| 7 | R-3′「已修正」註記（1.3） | 逐字；合入後才落檔 | 二-2(e) 第 2 項 |
| 7′ | 1.3 末點 | [TA 補]：N-196 被回退時撤回註記 | 同上 |
| 8 | N196-T4（1.4） | 修訂：只觸發一次、只在讀交易內觸發、重入直接放行 | 二-2(f) suggested，採用 |
| 9 | N177b-T17（2.1） | 取代：`count("None")` 與 `count("第 None 批")` 都等於 n；網格加 n ≥ 2 | 二-1 第 4 項 suggested，採用 |
| 10 | N177b-T22 (c′)（2.2） | 新增：具名常數、`model_copy` 的鍵（含 rule_id）、不可判讀形式以 baseline 釘住 | 二-1 第 6 項 suggested，採用 |
| 11 | N-197 (a) 分析（3.1～3.7） | 新增：兩份交錯表、版本交錯、方向、頻率、可偵測性 | 二-4 |
| 12 | 修法比較與 N-197a spec 草案（3.8、3.9） | 新增：採用 F-a 並強化三點；送風控審 | 二-4 候選修法 |
| 13 | N-197 (b) 分析（4.1～4.4） | 新增：走得到；涵蓋表；失敗變體；修法選項 | 二-3 另外的觀察 |
| 14 | ADR-0041 R-5′、R-6′ 草稿（5） | [待風控] | 二-3、二-4 |
| 15 | `evaluate_today` 改成單一讀交易 | 登錄，不處理（日後改動時順手做，仍回風控審） | 二-3 條件 3 suggested |

（修訂四由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。N-197a spec 與第 5 節草稿待風控審。）
````

### 其他部門
本輪沒有參與。

## 三、驗證

**讀過的文件：**
- `/home/user/AICompany/work/reviews/2026-11-07-N177修訂三比對與N196spec審查-風控.md`，全文。
- `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`：:1-563、修訂一 :688-947、修訂二第 5 節到檔末 :1418-1558、修訂三 :1559-1935。
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md` :92-136。確認 R-4′ 已在 :107，與風控原文目視一致；R-3′ 在 :106。
- `/home/user/AICompany/work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md` 的 E-2 段落，以及 `/home/user/AICompany/work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md` 第 11 點。
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` 的 N-169、N-195～N-197 列。

**讀過的程式**（都在 `/home/user/AICompany/apps/stock-desk/backend/app/`，只讀，未執行）：
- `playbook/service.py`：:1231-1420（`settle_on_request`、`_settle_pending`、`_batch_of`）、:1516-1739（`rebalance`、`_evaluation_data_date`、`_rule_set_status`、`confirm_rules`）、:1827-1935（`evaluate_today`）。
- `playbook/store.py`：:540-650（`_read_logged`、`_write_state`）、:724-732（`system_default_params`）、:915-1129（state、`set_capital`、`active_params`、`rule_set_authorship`、`confirm_rule_set`、`next_version`）、:1235-1574（`commit_evaluation`、`read_in_flight`、`pending_directives`、`claim_directive`、`batch_blocking_claim`、`settle`）。
- `playbook/engine.py`：:170-215、:715-1045、:1265-1299。
- `playbook/wording.py`：:944-957，以及 :963-969 與 :994-997 的 grep 結果。
- `playbook/models.py`：`PortfolioState`、`RebalanceResult` 的 grep 結果。
- `data/calendar.py`：:15-125。
- `api/playbook.py`：:185-198、:650-715。

**前端（只 grep 與讀檔）：**
- frontend/ 內沒有任何呼叫 `/rebalance` 的地方；
- `playbookView.ts:322-324`、`page.tsx:204`：確認面板只在 `unconfirmed` 時渲染；
- `RuleSetConfirmPanel.tsx`：:1-75、:165。

**grep：**
- `app/` 內的 `model_copy(`、`"rule_id":`、`"batch_no":`；
- `scripts/validate_agents.py:65` 的 `READONLY_ALLOWED_BASH`；
- `.claude/agents/qa-reviewer.md:4` 的 tools。

**未查證：**
- 第 3、4 節的交錯都是讀碼推論，沒有實跑。
- 4.1 第 5、6 步之間的實際時間比例沒有量測，「B 要停頓得比 A 的兩次日線載入更久」是結構推論。
- Windows 上 `datetime.now` 的解析度。
- `same_day_warnings` 中 ENTRY／A 在本路徑上的實際觸發條件。
- TanStack Query 的背景重取會不會造成 `/today` 並發。
- N-177a、N-195、N-196 都還沒有實作。

我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案，也沒有執行任何指令。

## 四、下一步

1. **coordinator：**
   - 把第二節的 ````markdown 區塊原文附到 `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` 的檔末；
   - 在 N-196 開 PR 之前，把修訂四送風控，包括 N-197 (a)(b) 的分析、N-197a spec 草案、R-5′／R-6′ 草稿，以及 1.2 的執行與判斷分離；
   - 確認 CEO 通知的名稱時，參考 3.6 的前端事實：REBALANCE 沒有 UI 入口，確認之後改資金也沒有 UI 入口。如果不能只改名稱，就回風控；
   - 在追蹤清單登錄 N-197a（暫定編號）。
2. **risk-compliance-officer：**
   - 審 N-197a spec；
   - 裁示 (b) 是否補揭露或通知，以及 N-169 的優先度；
   - 定稿 R-5′、R-6′；
   - 確認 C8 改由執行與判斷分離的方式可以接受。
3. **tech-writer：** R-3′ 的已修正註記，要等 coordinator 確認 N-196 已合入 product 之後才落檔。R-5′、R-6′ 要等風控定稿之後再落檔。
4. **dev-lead：**
   - N-196 依修訂三加修訂四第 1 節開發（C8 的證據、T4 的修訂）；
   - N-177b 依修訂四第 2 節調整 T17、T22；
   - N-197a 要等風控核可、而且 N-196 合入之後才開工。
5. **qa-reviewer：** 把 QB-N196-2、修訂後的 T4、T17、T22 (c′) 列為 BLOCKING；C8 依 1.2 判斷。
6. **CEO：** 目前沒有要決定的事。如果日後要讓 qa 直接執行 `git merge-base`，需要我出 ADR、由 CEO 核可，本次沒有提出。如果 CEO 想把 (a) 接受為無期限殘留（F-e），風控已表示會書面保留不同意見。

**相關檔案：**
- `/home/user/AICompany/work/reviews/2026-11-07-N177修訂三比對與N196spec審查-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py`
- `/home/user/AICompany/apps/stock-desk/frontend/app/playbook/RuleSetConfirmPanel.tsx`
- `/home/user/AICompany/scripts/validate_agents.py`

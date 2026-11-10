# ADR-0044：stock-desk 排程台 REBALANCE 之後，未結算的 R 系列買進列如何處置

- 狀態：proposed
- 日期：2026-11-10（修訂一，同日：併入風控 C-1～C-9，增列 (iii-c)、R-f、R-g；定稿，同日：併入風控 RC-52 三項 required 與 suggested、RC-53 條件 1～3、RC-53 時序選擇）
- 決策者：
  - tech-architect：草案、修訂一、定稿；
  - risk-compliance-officer：審查 2026-11-10 CONDITIONAL APPROVE，附 C-1～C-9；**風控 2026-11-10 確認修訂一（RC-52～RC-54）**，見 `work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md`；
  - CEO：裁示 (iii-c) 採否（Decision 1 寫法 A／B）、Decision 6 的時序選擇，以及修正或接受殘留 R-a～R-g。
- 依據：
  - [TA-210]：`work/reviews/2026-11-10-N209b補遺三與N210評估ADR0044草案-tech-architect.md` 第三部分
  - [風控-44]：`work/reviews/2026-11-10-交付B裁示ADR0044審查與字面定稿-風控.md` 第二部分（C-1～C-9）、RC-40、RC-47
  - [TA-44r1]：`work/reviews/2026-11-10-ADR0044修訂一與RC42C1W25f確認-tech-architect.md`（修訂一）
  - [風控-44r1]：`work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md`（RC-52～RC-54）
  - [TA-197]：`work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md` 3.8～3.9（N-197a、`TotalDeployStamp`、`TotalDeployWrite`）
  - [TA-209]：`work/reviews/2026-11-09-N209Q3Q4技術評估-tech-architect.md`（N-209b 方案 B）
- 適用範圍：僅 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 標註：
  - 行號是 2026-11-10 工作樹的快照。N-177a、N-195、N-196、N-197a、N-209b 都還沒合入，行號會漂移，抽驗請以內容定位。
  - `set_total_deploy`、`TotalDeployStamp`、`TotalDeployWrite`、`_total_deploy_stamp`、`_read_total_deploy_stamp`、`_total_deploy_state` 與 N-197a 的寫鎖交易都是規格名稱，以實際合入為準；名稱不同時回 TA。

## Context（背景）

1. **事實**（讀碼；風控 RC-29、RC-47 已核對）：
   - R1 的股數在評估當下，以當時的 TOTAL_DEPLOY 計算（`engine.py:982-988`；ADR-0043 D3 第 5 點）。
   - 指令列落檔後，決策欄位不再改寫。app/ 內對 `playbook_directives` 的 UPDATE 只有兩處：claim 的結算欄位（`store.py:1550`）與 ADR-0034 的 L4 戳記（`store.py:440`）。ADR-0035 的 N172-C11 明定「不 DELETE、不 UPDATE 既有指令列」。
   - 結算以列上的 `directive.shares` 寫入批次並扣現金（`store.py:1622-1635`）。
   - G1 只擋「批次已不是 planned」的列，不重驗 TD（`store.py:279-283`、`:1548-1555`）。
   - `/today` 原樣列出已落檔的列（ADR-0035 Decision 4、N172-C6）。
2. **後果**：
   - REBALANCE 調低 TD 之後，已產生、尚未結算的 R1 仍以舊股數成交入帳，`/today` 也一直顯示舊股數。
   - 調高 TD 時，方向是保守的（少買）。
3. **量級**（**更正風控 RC-29**；風控 RC-47 已確認）：
   - RC-29 原本寫「超出量最多是每檔一批、每批金額的差」，這低估了，以下段落取代。
   - **「每檔最多一批」靠的是 G1，不是 K2。** K2 只限同一個預定執行日。
     - 前一張 R1 還沒結算時，次日評估會對同一個最小號 planned 批次再出一張。
     - 該批一旦成交或被跳過，其餘的列都會被 G1 擋下。
     - planned 批次不會因為賣出而被 touched。
     - 所以「仍待進場」的受影響列，每檔只會指向一個批次。同一批次可能有多張列，但最多只有一張成交入帳。
   - **受影響的批次不是輪內末批時**：股數為 `max(1, floor(TD / n / bpt / close))`，差額是每批金額在新舊 TD 之間的差。
   - **受影響的批次是輪內末批時**：股數為 `floor(TD / n / close) − 已占用`，差額等於**整檔配額**在新舊 TD 之間的差。bpt = 1 時，每一批都是末批。
   - 因此單檔的最大差額是整檔配額之差（R-g）。
4. **限制**：
   - 系統無從得知使用者是否已經在券商下單（ADR-0035 R10）。
   - N-207 讓 REBALANCE 成為已確認後唯一的解閘路徑（T-09），使用頻率會上升。
   - 新一輪的 R1 在閘開之後才產生，用的是新 TD，不受影響。受影響的是其他標的先前評估留下的 R1。
5. **受影響列的定義**：
   - 符合 ADR-0034 C-B1 的 `_PENDING_ENTRY_WHERE`（`store.py:288`：`action = 'buy' AND settled = 0 AND status = 'pending'`），而且該 (symbol, batch_no) 的批次列存在、status 為 planned。
   - 被 G1 擋下的列永遠不入帳；孤兒列成交了也不動帳。這兩種都不屬於「結算時以原股數計入帳冊」的範圍。
6. **TD 設定時間的寫入與取值時點**（讀碼；是 Decision 7 的依據；風控 RC-52 已核對）：
   - **寫入者**：現況唯一的寫入者是 `set_capital`（`store.py:1033-1055`），呼叫點是 `service.py:1908`（rebalance）與 `:2030`（confirm_rules）。依 N-195、N-197a 規格，rebalance 之後改用 `set_total_deploy`（三個鍵），`set_capital` 只剩 confirm_rules 在用（N195-T6）。
   - **取值時點的問題**：
     - `set_capital` 的 set_at 在組 dict 時就取值（`:1052` `(at or datetime.now(UTC)).isoformat()`），早於 `_set_state` 開連線（`:1014`），也早於第一句 upsert 取得寫鎖（`:697`）。
     - 兩個寫入者並發時，先取時間、後 commit 的一方會把 set_at 寫成**較早**的值。
     - 所以現況下，即使時鐘沒有倒退，set_at 也可能往回走。往回走時，created_at 介於兩個時間之間的列會從 yes 變成 no，正是 D6 要防的「標示消失」（風控 RC-52 撤回「值只會往後移」的無條件說法）。Decision 7 第 3 款把取值移到寫鎖之後，這個前提才成立。
   - **`at` 參數**：
     - `set_capital` 與 N-197a 規格的 `set_total_deploy`（[TA-197] :273-276）都有 `at` 參數。app/ 內沒有呼叫者傳 `at`；`tests/test_n172_duplicate_probe.py:194-198` 有傳。
     - [TA-209] 方案 B 規劃 N-209b 的 ok 分支「由 service 產生 `at`，傳給 `set_total_deploy(at=…)` 後原樣回傳」，這等於在寫鎖外取時間。由 Decision 7 第 3 款取代。
   - **created_at 的取值時點**：指令列的 `created_at` 在 `commit_evaluation` 取得寫鎖**之前**取值（`store.py:1372` 先於 `:1374`）。這只會讓 created_at 偏早、標示偏向 yes，方向保守，本 ADR 不改（風控 RC-52 同意）。時鐘解析度粗時，created_at 與 set_at 可能相等，見 Decision 7 第 5 款。
7. **R-a 的窗口**（讀碼）：
   - `evaluate_today` 在 `service.py:2200` 讀 TD，在 `:2222` 呼叫 `commit_evaluation`，created_at 在 `store.py:1372` 取值。
   - 這段期間沒有網路呼叫（日線在 `:2160-2161` 已載入），但有 `apply_effects` 與 `save_fast_market` 各自的寫入（`:2213-2218`），遇到寫鎖時，每一筆都可能等到 busy_timeout。
   - 窗口大小沒有量測。

## Options（選項比較）

| 方案 | 內容 | 優點 | 缺點 | 風險 | 與 N172-C11 | 與 ADR-0035（及相關 ADR） |
|---|---|---|---|---|---|---|
| (i) 拒寫 | 有受影響列時，REBALANCE 不寫入，回新 status | 帳冊不會出現新舊 TD 交錯 | (1) 被 G1 擋下的列永遠 `settled=0`（`store.py:1544-1546`），資料缺口的列也會懸置，都必須排除，否則 REBALANCE 永久被擋；(2) 延後調低 TD 的期間，其他標的的新 R1 仍以較高的舊 TD 計算，危害只是轉移；(3) 卡住 N-207 唯一的解閘路徑（T-09）；(4) 檢查必須放在 N-197a 的寫鎖內，等於改動 N-197a 的鎖內本體；(5) 多一個 status 與一句字面 | 中 | 相容（不寫指令列） | 相容，不動 `commit_evaluation`；讀取必須沿用 C-B1 的單一定義（ADR-0034 VETO-2） |
| (ii) 結算截股 | 結算時把股數截在現行 TD 算出的上限內 | 帳冊不超過新上限 | (1) 券商成交的是原股數，帳冊截股後會少記持股，S、P 不評估多出的股數；(2) 上限要選價格與輪內脈絡，又多一個定義來源；(3) 截後的股數放在哪裡都不對：寫回指令列違反 C11，只寫批次則列、帳冊、券商三方不一致 | 高 | 寫回 `shares` 即違反；不寫回則帳與列不一致 | 違反 ADR-0041 Decision 4 列為仍有效的「C-B6 buy 行為零改動」；改 `settle` 動帳語意必須另立 ADR；動到 ADR-0042 的同一交易 |
| (iii-a) 讀取時判定標示 | `/today` 對受影響列中「落檔時間早於現行 TD 設定時間」者加常駐標示，後端逐列給旗標 | 零寫入；涵蓋所有 TD 寫入者；不動任何交易 | (1) 只知道 TD 之後曾被寫入，不知道方向，也不知道值有沒有變；(2) 依賴 set_at 單調遞增（Decision 7）；(3) R-a 會漏標 | 低 | 相容（只讀） | 相容。風控裁示 ADR-0034 D6 不直接適用、原則適用，以 Decision 7 滿足 |
| (iii-b) 落檔戳記 | TD 寫入時，在同一寫鎖內對受影響列打一次性戳記，比照 L4（`store.py:440`） | 標示不依賴可覆寫的值 | (1) 指令列多一條 UPDATE 路徑；(2) 兩個 TD 寫入者都要在鎖內打戳 | 中 | 字面上衝突，要 ADR-0035 補充 | 要改 N-197a 的鎖內本體與 `confirm_rules` |
| (iii-c) INSERT 時落檔評估依據 | 指令列 INSERT 時，把評估所用的 TD 戳記（TD、set_at、source 三個原始字串）寫入新欄位；讀取時與現行戳記逐字比對 | 以落檔事實判定，不比時間先後；可給 TD 的方向；只在 INSERT 時寫入 | 加一個欄位與 migration；`commit_evaluation`、`_insert_directives` 的簽名做加法；舊列沒有值 | 低 | 相容（只 INSERT，不 UPDATE） | 相容，見下方評估 |
| (iv) 結果列出受影響列 | 在 N-197a 寫鎖交易內，以同一個常數 SELECT 受影響列，只有 ok 分支回傳 | 寫入當下的精確清單 | 依賴 N-197a 的鎖；寫入之後才 commit 的列不在清單內（R-a） | 低 | 相容（只讀） | 相容；持鎖期間零網路 |

### (iii-c) 評估（風控 C-2；風控 RC-53 意見已附）

**內容**
- **欄位**：`playbook_directives` 新增可為 NULL 的欄位 `td_basis TEXT`。
  - 加在 `_MIGRATIONS`，比照 ADR-0034 C-B7，不回填。
  - 值是本次評估所用 `TotalDeployStamp` 的 JSON（三個原始字串，鍵不存在時為 null），只經過單一的 encode／decode helper。
  - 用一個 JSON 欄而不用兩個欄，理由有兩點：
    - 要分辨「舊列（NULL）」與「評估當時 TD 鍵不存在」。後者在 A8 狀態下會發生，用兩個欄都是 NULL 就分不出來。
    - 三個鍵一起存，和 N-197a 的比對單位一致，可以避免時間戳解析度造成的 ABA。
- **寫入**：
  - `commit_evaluation` 新增必填的 keyword 參數 `td_basis: TotalDeployStamp`，沒有預設值，經 `_insert_directives` 寫入本次 INSERT 的每一列。
  - `record_directives`（REBALANCE 的無單列、測試）與 `commit_emergency_exit` 寫入 NULL。
  - app/ 內的 R1 buy 只來自 `commit_evaluation`。
- **來源**：
  - `evaluate_today` 把 `:2200` 的 `portfolio_state()` 換成一個新的 store 方法，暫稱 `portfolio_with_stamp()`。它只做一次 `_state_map()`，同時產生 `PortfolioState` 與 `TotalDeployStamp`，建構函式與 `portfolio_state()`、N-197a 的 `_total_deploy_stamp` 共用。
  - 交給 `evaluate()` 的 portfolio 與交給 `commit_evaluation` 的 stamp，必須來自同一個回傳值。
- **判定**：
  - `td_basis` 不為 NULL 時，與現行戳記（Decision 3 同一次讀取的原始字串）逐字比對：
    - 相同為 no，不同為 yes；
    - decode 失敗，或現行戳記讀取失敗，為 unknown。
  - yes 時，另外給 `td_change: Literal["lower", "higher", "same_value", "unknown"]`：以 Decimal 比較兩個 TD 值，任一方解析失敗為 unknown。
  - 另外給 `td_flag_basis: Literal["recorded", "time_order"]`，標明這一列是依落檔事實判定，還是依 (iii-a) 判定。
  - **`td_flag_basis` 與 `td_change` 只是後端判定的結果，不得用來改變前端的字面**（風控 RC-53 條件 1；見 Decision 5、C-N210-15）。
  - `td_basis` 為 NULL 時，依 Decision 3（(iii-a)）判定。

**成本**
- **結構面**：
  - 一個 migration 欄位；
  - `_insert_directives` 加一個 keyword 參數，三個呼叫者都要改；
  - `commit_evaluation` 的簽名做加法；
  - 一個新的 store 讀取方法；
  - encode／decode helper；
  - 讀取端的 SELECT 要帶出新欄位。
- **交易面**：不新增交易，也不新增鎖內語句，仍是同一句 INSERT，只是多一欄。
- **測試面**：
  - migration：舊 DB 會補上欄位，舊列為 NULL，走 (iii-a)；
  - `commit_evaluation` 與 `commit_emergency_exit` 的 SQL trace 斷言：INSERT 的欄位清單會改變；
  - schema 釘住測試要盤點，例如 `tests/test_playbook_exit_idempotency.py:740` 起的欄位清單；
  - 新增交錯測試（C-N210-14）。
- **相依**：N-197a 的 `TotalDeployStamp` 與 helper。N-210a 原本就相依 N-197a。
- **TA 估計**：中等。全部是加法，但會碰到 `commit_evaluation` 這個測試密集的區域。沒有量化估工。

**與 N172-C11、ADR-0035、ADR-0041、`commit_evaluation` 的關係**
- **N172-C11**：只在 INSERT 時寫入，從不 UPDATE，相容。C-N210-6 照舊。
- **N172-C1**（單一 `BEGIN IMMEDIATE`）不變。
- **N172-C2**（持鎖期間零 resolver、零網路、零其他 store 呼叫）不變。`td_basis` 是呼叫前就算好的值。
- **K1、K2 與 G1**：K1、K2 的查詢與 G1 的 SQL 都不得引用 `td_basis`（補充六：G1 零 diff）。
- **結算（ADR-0041 Decision 4）**：`settle` 與 claim 的 SQL 不得引用 `td_basis`，確保結算的動帳語意零改動（風控 RC-53 條件 2；C-N210-12）。
- **Decision 4、N172-C6**（回傳已落檔列）不變；讀取時可以帶出新欄位。
- **ADR-0033 C-10**（兩條路徑共用同一句 INSERT）維持。
- **ADR-0043 I-4**：engine 不讀 `TotalDeployStamp`。(iii-c) 只動 service 與 store，`engine.py` 零 diff。
- **結論**：不改 ADR-0035 的任何 Decision 或約束，所以不需要 ADR-0035 補充。

**能否關閉 R-a、R-b、R-c**（風控 RC-53、RC-54：以本分項說法為準）
- **R-a**：
  - `/today` 的標示：對有 `td_basis` 的列，**可以關閉**。判定依據是評估實際用的戳記，不是時間先後。評估讀到舊戳記之後才有 REBALANCE commit，那一列記的是舊戳記，會判為 yes。
  - (iv) 清單：**不受影響**。清單是寫入當下已落檔列的快照，之後才 commit 的舊 TD 列不在清單內（但在 `/today` 會標 yes）。
  - 所以 C-3 照舊。R-a 關閉的效果，只是可以把**時間限定句**送風控審，不是可以寫「沒有受影響的指令」。風控不預核這類句子：寫入之後仍可能出現以舊 TD 計算的列，句子必須一併揭露這一點。
- **R-b**：**部分關閉**。可以給出 TD 的方向（調高、調低、值相同），但不給股數差。方向句要風控另外審，審過之前，C-9「不得寫方向」照舊。
- **R-c**：對有 `td_basis` 的列**可以關閉**，因為是逐字相等比對，不比先後。舊列仍有 R-c。

**舊列如何退回 (iii-a)**
- **判定**：`td_basis` 為 NULL 的列，一律依 Decision 3 判定，Decision 7 全部照舊適用。所以採用 (iii-c) 時，Decision 7 第 3 款對 `set_capital` 的修改仍然要做。
- **範圍**：N-210a 部署前已落檔、仍符合 Decision 2 的列。這些列多半在下一次結算後就離開範圍，所以退回路徑是過渡性的；但資料缺口使結算延後時，可能停留較久。
- **回退 N-210a 時**：欄位保留（`add_missing_columns` 不刪欄）。回退期間寫入的列為 NULL，重新部署後走 (iii-a)。
- **不採的替代做法：「舊列一律判為 unknown、不改 `set_capital`」**（風控 RC-53 條件 3）。不採理由：
  1. 若 (iii-c) 拆成 N-210c（Decision 6 選項 2），過渡期間**全部列**都走 (iii-a)，(iii-a) 本身必須正確，第 3 款不能省。
  2. 第 3 款同時修掉現況「set_at 會往回走」的缺陷（Context 第 6 點）。這個缺陷與 (iii-c) 無關，本來就要修。

**TA 建議：採用。風控意見（RC-53）：建議採用，而且放進 N-210a，不拆單。**
1. 可以關閉風控最在意的 R-a（`/today` 標示），而且不改 `commit_evaluation` 的交易或鎖內語句。
2. 新列不再依賴 set_at 的先後順序。Context 第 6 點那種失效與 R-c，對新列都不成立。
3. 全部是加法，只在 INSERT 時寫入，與 N172-C11、ADR-0035、ADR-0033 C-10、ADR-0043 I-4 都相容。
4. 保留了方向資訊，日後可以用來揭露（R-b），但要先送風控審。

**代價**：N-210a 的範圍擴大，要碰 `commit_evaluation` 的簽名與 trace 測試，C-8 的時程壓力也會增加。時序選擇見 Decision 6。

## Decision（決策，proposed）

1. **方案選擇**（tech-writer 依 CEO 裁示，保留寫法 A 或寫法 B 其中一段，刪除另一段與本行括號說明）
   - **寫法 A（CEO 採用 (iii-c)）**：
     - 採 (iii-a) + (iii-c) + (iv)。Decision 3A 生效，Decision 3 只用於 `td_basis` 為 NULL 的列。
     - (ii) 否決：帳冊截股後，帳冊與券商實況不符。
     - (i) 不採：危害只是轉移，而且會卡住 T-09。
     - (iii-b) 不採：風控裁示 ADR-0034 D6 不直接適用，但原則適用，以 Decision 7 滿足。
     - 「舊列一律判為 unknown、不改 `set_capital`」不採（風控 RC-53 條件 3，理由見 Options「舊列如何退回 (iii-a)」）。
     - C-N210-12～15 適用。
   - **寫法 B（CEO 不採 (iii-c)）**：
     - 採 (iii-a) + (iv)。Decision 3A 整段刪除；Options 的 (iii-c) 列與評估小節保留作為紀錄。Consequences「(iii-c) 不採理由」填入 CEO 書面理由（風控 C-2）。
     - (ii) 否決：帳冊截股後，帳冊與券商實況不符。
     - (i) 不採：危害只是轉移，而且會卡住 T-09。
     - (iii-b) 不採：風控裁示 ADR-0034 D6 不直接適用，但原則適用，以 Decision 7 滿足。
     - C-N210-12～15 不適用；Decision 7 全部照舊適用。
2. **單一定義**：store 新增常數 `KEPT_PENDING_ENTRY_SQL`，內容是 `_PENDING_ENTRY_WHERE` 加上「批次列存在且 status = 'planned'」。(iii) 與 (iv) 都拼接這個常數，不得另寫。
3. **(iii-a) 判定**
   - 後端對 `/today` 中每一列符合第 2 點的指令列（包括今日指令表與 in-flight 清單），回傳 `td_rewritten_since_logged: Literal["yes", "no", "unknown"]`。
   - 判定只經單一純函式 `td_rewritten_since(created_at_raw, set_at_raw)`，解析與比較規則依 Decision 7 第 5 款（時間相等為 unknown）。
   - set_at 以**原始字串**讀取，讀取時點在 logged 與 in-flight 讀取之後。
   - 不得經由 `portfolio_state()` 的 `datetime.fromisoformat`（`store.py:1024`）取得。那裡解析失敗會 raise，`/today` 就會失敗，違反 C-6。
   - 比較在 Python 內以帶時區的 datetime 進行，不在 SQL 內比字串。
   - 前端不得自行計算。
3A. **(iii-c) 判定**（只在寫法 A 生效）：
   - 依 Options「(iii-c) 評估」的「內容」寫入與判定。`td_basis` 為 NULL 的列走第 3 點。
   - `td_flag_basis` 與 `td_change` 只是後端判定的結果（風控 RC-53 條件 1）。依這兩個欄位改變字面的句子，都要先送風控；例如依 recorded 寫成較肯定的語氣，或寫出方向。在那之前，不論判定依據為何，yes 與 unknown 一律用第 5 點的同一套定稿句。
4. **(iv)：REBALANCE 結果列出受影響的列**
   - 在 N-197a 的 REBALANCE 寫鎖交易內、寫入之前，以第 2 點的常數讀取受影響的列，依 (symbol, batch_no, execution_date, id) 排序。
   - 回應新增加法欄位 `kept_pending_entries: list[KeptBatch] | None`：
     - `KeptBatch` 的欄位是 symbol、batch_no、`entries: list[(execution_date, shares)]`，以及後端給的 `multiple_entries: bool`。
     - batch_no 只當分組鍵；要顯示批號時，依 W-19 的顯示批號規則。
   - 只有 ok 分支有值，其他分支一律為 None，不是 `[]`。
   - **清單為空時（風控 C-3）**：
     - 不得寫「沒有受影響的指令」或任何等義的句子。
     - 清單區塊整段不顯示，包括標題，只留 N9-06 的靜態句。
     - 理由：讀取時正在進行的評估，可能在寫鎖釋放後才 commit 一張以舊 TD 計算的列。
     - R-a 關閉之後（`commit_evaluation` 鎖內比對，或寫法 A 的 `/today` 標示），才能送風控審一句有時間限定的版本，例如「本次寫入時，沒有…」。風控不預核；句子必須一併揭露「寫入之後仍可能出現以舊 TD 計算的列」（RC-53）。
   - **ok 分支卻是 None 時（風控 C-5）**：前端顯示「清單無法取得」（字面由風控定稿），不得當成空清單。
   - **`message` 不改**（RC-40）：清單由前端從結構化欄位渲染。若要放進 `message`，就是改動 `REBALANCE_RESULT`，要比照 B-1 揭露，並回送風控。
5. **字面**（creative-lead 擬稿，風控逐字定稿；C-5、C-9）
   - **(iii) 的 yes 標示句**，只限三件事實：
     - 本列在 TOTAL_DEPLOY 最近一次重新設定之前產生；
     - 股數依產生當時的值計算；
     - 帳冊子句與 N9-05 用同一套限定：「成交結算時，若所指的批次仍待進場，以本列股數計入帳冊」。
   - **unknown 句**另外擬一句。
   - yes 句與 unknown 句**不依 `td_flag_basis`、`td_change` 分版**（風控 RC-53 條件 1）。要分版，先送風控。
   - **(iv) 清單的字面**：同一批次有多張列時，要寫明同一批次只會有一筆成交。另外要有「清單無法取得」一句。
   - **禁止事項**：
     - 不得寫方向。寫法 A 之下，方向句也要另送風控審，審過之前仍不得寫。
     - 不得依判定依據改變語氣。
     - 不得有任何建議或時機提示。
6. **範圍、時序與審查**（風控 C-8、RC-52、RC-53）
   - **實作分單**，都排在 N-209b 之後，都是加法，不擴大 N-209b：
     - N-210a（後端）：第 2、3、4、7 點；寫法 A 時加上 3A（時序選項 2 除外）；
     - N-210b（前端）：第 4、8 點；
     - N-210c（只在時序選項 2 存在）：3A。
   - **Decision 7 第 3 款對 `set_capital` 的修改，必須和 Decision 3 同在 N-210a，不得拆出延後**（風控 RC-52）。
   - **審查紀錄**：風控 2026-11-10 CONDITIONAL APPROVE（C-1～C-9）；**風控 2026-11-10 確認修訂一（RC-52～RC-54）**，見 `work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md`。RC-52 三項 required 與 RC-53 條件 2 併入後不必回送風控，由 qa-reviewer 逐條檢查。
   - **時序選擇（CEO 決定；以下依風控偏好排序）**：
     1. **首選**：N-210a（寫法 A 時含 (iii-c)）與 N-210b，在 N-207 部署前合入。
     2. **可接受（只在寫法 A 有意義）**：先合入不含 (iii-c) 的 N-210a 與 N-210b，再把 (iii-c) 拆成 N-210c 隨後合入。條件：
        - CEO 書面接受「N-210c 合入前，R-a 仍是殘留」；
        - C-3、C-4 照舊；
        - 第 3 款仍在 N-210a。
     3. **先讓 N-207 上線**：依 C-8，CEO 書面逐項接受 R-a～R-g，記入交件紀錄。書面要寫明：N-210a／b 合入之前，`/today` 沒有標示，REBALANCE 結果沒有清單，只有 N-209 前端的 N9-05、N9-06 兩句靜態字面。
   - 理由（風控）：N-207 會讓 REBALANCE 的使用頻率上升（T-09），而且 RC-47 顯示量級是整檔配額之差。
7. **D6 的替代保證：TD 設定時間的守門條款**（風控 C-1，RC-52 加嚴；全部 BLOCKING；寫法 A 時仍適用）
   1. **寫入者封閉**（AST，`store.py`；RC-52 required-3）：
      - (a) 以 `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE` 任一為鍵的 dict 字面值，只能出現在 TD 寫入函式內。N-197a 合入後，這個函式是 `_total_deploy_state`，它的呼叫者只能是 `set_total_deploy` 與 `set_capital`。N-197a 若沒有抽出 helper，就是這兩個函式本身。
      - (b) 這三個常數不得出現在其他 `_write_state`／`_set_state` 呼叫的引數中，也不得作為 subscript 賦值的目標。
      - (c) **動態鍵封閉**：`_set_state` 本體轉交 `values`，以及 TD 寫入函式，不受本項限制。其餘所有 `_write_state`／`_set_state` 呼叫，值引數必須是 dict 字面值，而且鍵全部是模組層 `STATE_*` 名稱（`ast.Name`）。
      - (d) **原生 SQL**：`store.py` 內每個含 `playbook_state` 的字串常數（不分大小寫、不含 docstring；f-string 的每一段各自計算），只能是下列三種之一：
        - 位於 `_write_state` 函式本體內；
        - 位於 `_SCHEMA` 的 `CREATE TABLE` DDL；
        - 去掉前導空白後以 `SELECT` 開頭，而且不含 `INSERT`、`UPDATE`、`DELETE`、`REPLACE` 任一字（字界比對、不分大小寫）。

        效果：對 `playbook_state` 的寫入型 SQL 只出現在 `_write_state`（現況 `:694`、`:697` 成立）。把表名拆開，或把表名放進變數，含表名的那一段都不符合三種形式，一樣擋下。
      - (e) **字串常數**：值恰為 `"total_deploy"`、`"total_deploy_set_at"`、`"total_deploy_source"` 的字串常數，在 `store.py` 只能作為模組層 `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE` 賦值的右側（現況 `:221`、`:228`、`:229`）。另外，除了這三處常數定義，任何非 docstring 的字串常數都不得以子字串形式含有 `total_deploy_set_at` 或 `total_deploy_source`。
   2. **範圍封閉**（AST，`app/`）：
      - `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE` 這三個名稱，以及字串常數 `"total_deploy_set_at"`、`"total_deploy_source"`，只出現在 `store.py`。
      - app/ 內含 `playbook_state` 的 SQL 字串只出現在 `store.py`。
      - 這兩點現況都成立。
   3. **值的來源**：
      - set_at 的值是 `datetime.now(UTC).isoformat()`，在同一個連線的 `BEGIN IMMEDIATE` 成功之後、`COMMIT` 之前取值，與 TD 在同一次 commit。
      - **允許的兩種寫法**（AST；RC-52 suggested）：
        - (i) 運算式 `datetime.now(UTC).isoformat()` 直接放在 dict 的值位置；
        - (ii) 先在同一函式內指定給區域變數，再把該名稱放進 dict。條件有四：
          - 是單一 `Assign`，目標為單一 `Name`，右側恰為 `datetime.now(UTC).isoformat()`；
          - 該敘述在原始碼順序上位於該函式的 `conn.execute("BEGIN IMMEDIATE")` 之後；
          - 與寫入位於同一個 `try` 區塊內；
          - 該名稱在函式內沒有其他賦值。
        - 時鐘呼叫若在 `_total_deploy_state` 本體內，`_total_deploy_state` 本體依 (i) 或 (ii)，而且它的每個呼叫點都位於呼叫者的 `BEGIN IMMEDIATE` 之後、同一個 `try` 區塊內。
      - TD 寫入函式（`set_total_deploy`、`set_capital`、`_total_deploy_state`）不得有任何時間參數。AST 檢查：沒有名為 `at` 的參數，也沒有 annotation 含 `datetime` 的參數。
      - 不得複製或還原舊值：值的運算式只能是上列兩種寫法，不引用任何讀取結果。
      - 不得寫 None：值的運算式不是 None 常數，也不是含 None 的條件運算式。
      - SQL trace 加時鐘 spy：時鐘呼叫發生在 `BEGIN IMMEDIATE` 之後、`COMMIT` 之前；TD 與 set_at 的 upsert 在同一對 BEGIN／COMMIT 之間。
      - **交錯測試（RC-52 required-2；必須在現行程式上失敗）**：
        - **時鐘**：以遞增假時鐘取代 `app.playbook.store` 模組內的 `datetime`。每次 `now(tz)` 回傳前一次加 1 微秒，帶 UTC 時區，以 lock 保護。
        - **暫停點**：包裝 `PlaybookStore._connect`。B 執行緒第一次呼叫時，設定事件 `b_paused` 並等待事件 `a_done`；等待設逾時，逾時就讓測試明確失敗，不得無限等待。
          - 這個點在現行 `set_capital` 中位於取時間（`:1052`）之後、第一句寫入之前；
          - 在修正後的寫入函式中位於 `BEGIN IMMEDIATE` 之前。
          - 兩個版本都用同一個 hook。
        - **步驟**：
          1. B 執行緒呼叫寫入函式；
          2. 主執行緒等到 `b_paused` 後，讓 A 完成一次完整寫入（`BEGIN IMMEDIATE`、取時間、commit），記下 A 寫入的 set_at；
          3. 設定 `a_done`，B 繼續；
          4. B 結束後讀回 set_at。
        - **斷言**：最終 set_at 不早於 A 寫入的值。
        - **參數化**：B ∈ {`set_capital`, `set_total_deploy`}，A ∈ {`set_capital`, `set_total_deploy`}。B 為 `set_total_deploy` 時，B 的 `expected` 在 A commit 後會不符，可能不寫入；斷言照樣適用。
        - **效力證明**：「現行程式」指 N-210a 的 base（含 N-197a，不含本款修改）。把本測試檔放到 base 上執行，B 為 `set_capital` 的各組必須失敗。執行輸出原樣附在 PR 說明，比照 C-N210-14。測試本身 commit，失敗輸出不 commit。B 為 `set_total_deploy` 的各組在 base 上也會通過，只作回歸守門，不算效力證明。
        - 測試 DB 必須是檔案 DB，不得用 `:memory:`。
      - **本次寫入值的回傳**：`set_total_deploy` 的回傳型別 `TotalDeployWrite`（[TA-197]）加一個加法欄位 `stored: TotalDeployStamp | None`：有寫入時為本次寫入的三個原始字串，沒寫入時為 None。
        - 需要「本次寫入時間」的呼叫者（N-209b 的 ok 分支，N-209 PRD FR-9）一律取自這個欄位。
        - [TA-209] 方案 B「由 service 產生 `at` 傳入 `set_total_deploy`」由本款取代。
        - N-209b 若先合入而且用了 `at=`，N-210a 要把它改成讀 `stored`，並列入 N-210a 的變更窮舉。
      - **本款對 `set_capital` 的改動**：
        - 改為自己開 `BEGIN IMMEDIATE`，不再經 `_set_state`，並移除 `at` 參數。
        - 對 `set_capital` 而言，這部分取代 N195-C4「不加 BEGIN IMMEDIATE」與 N197a-C7 的對應句。
        - N197a-C5（`set_capital` 零 diff）只約束 N-197a 那張 PR，不受影響。
        - `set_capital` 仍在同一個交易內寫四個鍵（N197a-C6）。
        - `tests/test_n172_duplicate_probe.py:194-198` 改以直接 SQL 種入，同檔 `:135` 已有同型寫法。
   4. **DELETE 路徑**：`_write_state` 的 DELETE 分支（`store.py:694`）不會收到這三個鍵。由第 1、3 款的 AST 保證；另以 SQL trace 斷言 TD 寫入交易內沒有 DELETE。
   5. **讀取、解析與比較**（RC-52 required-1）：
      - 單一純函式。兩個時間一律解析為帶時區的 datetime（`utcoffset()` 不為 None）。
      - naive、解析失敗、任一缺值，一律為 unknown，不得為 no。
      - 比較：
        - set_at **晚於** created_at → yes；
        - **相等 → unknown**；
        - set_at **早於** created_at → no。
      - 相等以 datetime 的瞬時相等判定，不同時區寫法的同一瞬間也算相等。
      - 理由：created_at 在鎖外取值，set_at 在鎖內取值；時鐘解析度粗時兩者可能相等，這時分不出先後。判 no 等於斷言「沒有重設」，不誠實。
      - 參數化測試表：

| # | created_at | set_at | 期望 |
|---|---|---|---|
| 1 | 有效、帶時區 | 缺值 | unknown |
| 2 | 缺值 | 有效、帶時區 | unknown |
| 3 | naive | 有效、帶時區 | unknown |
| 4 | 有效、帶時區 | naive | unknown |
| 5 | 不可解析 | 有效 | unknown |
| 6 | 有效 | 不可解析 | unknown |
| 7 | t | t + 1 微秒 | yes |
| 8 | t | t（同一字串） | unknown |
| 9 | t（`+00:00`） | 同一瞬間的 `+08:00` 寫法 | unknown |
| 10 | t | t − 1 微秒 | no |

   6. **日後變更**：新增 TD 或 set_at 的寫入路徑，或改動第 3 款的取值方式，都要回 TA 與風控。
   7. **適用範圍**：寫法 A 之下，第 1～6 款仍然適用，因為舊列會退回 (iii-a)。
8. **前端呈現**（風控 C-4、C-6；RC-53 條件 1）
   - 旗標為 no 時，不渲染任何文字。
   - 畫面上不得有「未標示的列依現行 TOTAL_DEPLOY 計算」或任何等義的圖例、說明、tooltip。
   - `/today` 多出的那次讀取若失敗，全部旗標為 unknown，`/today` 照常呈現。不得回 no，也不得讓 `/today` 失敗。
   - 前端不得自行比較 `created_at` 與 set_at，也不得自行比較 `td_basis`。
   - 前端不得讀取 `td_flag_basis`、`td_change` 來選擇或改變字面。

## Consequences（後果）

- **好處**：
  - 使用者在下單前讀 `/today` 時，看得到哪些列是在 TD 重設之前產生的。
  - REBALANCE 結果畫面可以具體列出受影響的列。
  - 帳冊語意、結算、既有指令列都不改。
  - Decision 7 第 3 款同時修掉現況「set_at 可能往回走」的缺陷，並以「在現行程式上會失敗」的測試證明修法有效。
- **殘留與裁示**：

| 殘留 | 內容 | 風控裁示 | 寫法 A（採 (iii-c)）的效果 |
|---|---|---|---|
| R-a 競態 | 評估讀取 TD 之後、commit 之前若有 REBALANCE commit，那一列以舊 TD 計算，(iii-a) 不會標示，也不在 (iv) 清單內（窗口見 Context 第 7 點） | 附 C-3、C-4，可以作為殘留交 CEO；建議修正 | `/today` 標示關閉；(iv) 清單不變，C-3 照舊。時序選項 2 下，到 N-210c 合入前仍是殘留 |
| R-b 沒有方向 | 標示不帶方向，TD 調高時也會出現 | 接受。標示只陳述事實，不寫方向 | 可以給出 TD 方向；方向句要另送風控審 |
| R-c 時鐘倒退 | 時鐘倒退時，標示可能消失；無法解析或時間相等時為 unknown | 接受，附 Decision 7 第 5 款的 unknown 規則（RC-52：相等亦為 unknown） | 新列關閉；舊列仍有 |
| R-d 撤不回券商的單 | 揭露無法撤回使用者已經在券商下的單（R10） | 接受，屬系統性限制 | 不變 |
| R-e 多一次讀取 | `/today` 多一次狀態讀取 | 接受，附 C-6 | 不變 |
| R-f 結算後沒有標示 | 結算以後，帳冊上沒有標示。這一列以舊股數入帳的事實，只在結算前的 `/today` 與 REBALANCE 當下揭露。這與 ADR-0034 D6「標示持續到 closed」不同 | 列入殘留（C-7），待 CEO 接受或修正 | 不變。修法是結算時把標示複製到批次，比照 C-B6 的 `entry_before_exit_on`。這屬於改動 `settle` 的動帳語意，依 ADR-0041 Decision 4 要另立 ADR，不在本 ADR |
| R-g 量級 | 單檔差額最大為整檔配額在新舊 TD 之間的差（RC-47，Context 第 3 點） | 列入殘留（C-7） | 不變 |

- **(iii-c) 不採理由**：只在寫法 B 填入，附 CEO 書面理由；TA 列的成本見 Options。
- **代價**：
  - `set_capital` 改用自己的 `BEGIN IMMEDIATE`，等鎖時間從第一句 upsert 提前到交易開頭，語意不變。
  - 一個既有測試要改種入方式。
  - `TotalDeployWrite` 多一個加法欄位；N-209b 取本次寫入時間的方式隨之確定。
  - 時間相等改判 unknown，unknown 會略多。
  - 寫法 A 時，見 Options 的成本。
- **被約束的事**：
  - (ii) 類「結算時改股數」的方案日後若要重提，必須另立 ADR，並處理 ADR-0041 Decision 4、ADR-0042 與 R10。
  - 第 2 點的常數只能有一份。
  - 前端不得自行推斷旗標，也不得依 `td_flag_basis`、`td_change` 改變字面。
  - TD 與 set_at 的寫入受 Decision 7 約束。
- **與既有 ADR 的關係**：
  - 與 ADR-0034、0035、0041、0042、0043 都沒有衝突，不取代任何一則。
  - 局部取代的 TA 規格句（都不是 ADR）：
    - 對 `set_capital` 局部取代 N195-C4 與 N197a-C7 的對應句；
    - 取代 [TA-209] 方案 B 中「service 產生 `at` 傳給 `set_total_deploy`」一句；
    - 對 [TA-197] 的 `set_total_deploy` 簽名移除 `at`，`TotalDeployWrite` 增列 `stored`。

## 附錄：對實作的約束（qa-reviewer 逐條檢查）

- **C-N210-1**：`KEPT_PENDING_ENTRY_SQL` 只能有一個定義，(iii) 與 (iv) 都拼接它。以 grep 計數釘住。
- **C-N210-2**：旗標由後端計算。前端 grep 不得出現 `created_at`、`set_at`、`td_basis` 的比較。
- **C-N210-3**：set_at 的讀取在 logged 與 in-flight 讀取之後，以呼叫順序測試釘住。讀取用原始字串，不經 `portfolio_state()`。
- **C-N210-4**：(iv) 的 SELECT 在 N-197a 寫鎖交易內、寫入之前執行，持鎖期間零網路呼叫。以 trace 測試釘住。
- **C-N210-5**：非 ok 分支的 `kept_pending_entries` 為 None。
- **C-N210-6**：不得 UPDATE `playbook_directives` 的任何新欄位。`UPDATE playbook_directives` 的出現位置只能維持現有兩處。
- **C-N210-7**：Decision 7 第 1～5 款各有對應的測試，全部 BLOCKING。其中：
  - 第 1 款含 (a)～(e) 五項 AST；
  - 第 3 款含兩種允許寫法的正反例：在 `BEGIN IMMEDIATE` 之前指定給區域變數，必須被判違規；
  - 第 5 款含上表第 8、9 列（相等為 unknown）。
- **C-N210-8**：清單為空時，清單區塊不存在於 DOM（render 測試）。前端 grep「沒有受影響」計數為 0。
- **C-N210-9**：ok 分支而清單為 None 時，渲染「清單無法取得」（render 測試）。
- **C-N210-10**：旗標為 no 時零文字（render 測試）。前端 grep 不得出現 Decision 8 禁止的圖例句。
- **C-N210-11**：對 `/today` 的額外讀取注入例外 → 全部旗標為 unknown，`/today` 回 200。
- **C-N210-12**（寫法 A）：
  - `td_basis` 只在 `_insert_directives` 的 INSERT 寫入；
  - K1、K2、G1 的 SQL 不引用 `td_basis`（grep）；
  - **`settle`、`claim_and_settle`，以及兩者呼叫的 store helper，其 SQL 字串都不含 `td_basis`**（AST 收集這些函式本體的字串常數；風控 RC-53 條件 2）；
  - `store.py` 內 `td_basis` 只出現在以下位置（白名單）：`_MIGRATIONS` 該欄定義、`_insert_directives`、`commit_evaluation`（轉交參數）、encode／decode helper、`/today` 旗標讀取方法；
  - `commit_evaluation` 的 `td_basis` 參數沒有預設值（AST）；
  - `evaluate_today` 交給 `evaluate()` 的 portfolio 與交給 `commit_evaluation` 的 stamp，來自同一次 `portfolio_with_stamp()` 呼叫（AST）；
  - `engine.py` 零 diff。
- **C-N210-13**（寫法 A）：migration 測試。舊 DB 補上欄位，舊列為 NULL，判定走 (iii-a)，`td_flag_basis == "time_order"`。
- **C-N210-14**（寫法 A）：交錯測試。在評估讀取戳記之後、`commit_evaluation` 之前注入一次 REBALANCE commit → 該列為 yes、`td_flag_basis == "recorded"`。把比對換成 (iii-a) 時，這個測試會失敗，作為效力證明；失敗輸出附在 PR 說明，不 commit。
- **C-N210-15**（寫法 A；風控 RC-53 條件 1）：
  - 前端 grep `td_flag_basis`、`td_change`、`tdFlagBasis`、`tdChange` 計數為 0；
  - 後端組 yes／unknown 字面的函式（`wording.py` 與 API 組句處）的 AST 不引用這兩個名稱；
  - render 測試：同一個 yes 列在 `td_flag_basis` 為 recorded 與 time_order 時，渲染出的字串逐字相同。
- **C-N210-16**：Decision 7 第 3 款交錯測試的效力證明。N-210a 的 PR 說明附上「本測試檔在 base 上執行」的原樣輸出，B 為 `set_capital` 的各組都是 FAILED；沒附就不得合併。
- **C-N210-17**：
  - `set_total_deploy`、`set_capital`、`_total_deploy_state` 的簽名沒有 `at`（AST）；
  - `TotalDeployWrite` 有 `stored` 欄位，`stored` 為 None 若且唯若 `written` 為假（參數化測試）；
  - `rebalance` 的 ok 分支取本次寫入時間時只讀 `write.stored`，`rebalance` 內不呼叫 `datetime.now`（AST）。
- **禁止事項**：不得在結算時改變股數；不得以 `pending_directives` 取代 C-B1 的定義。

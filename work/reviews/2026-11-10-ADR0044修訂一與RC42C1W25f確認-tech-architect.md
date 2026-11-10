# ADR-0044 修訂一全文、RC-42 與 C-1 前提確認、W-25f 語意確認

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：ADR-0044 修訂一全文、RC-42 與 C-1 前提確認、W-25f 語意確認

## 一、本次結論

全程唯讀。沒有改任何檔案，沒有執行任何指令，沒有讀 `.env`，也沒有碰 `data/*.db`。

**交付 1：ADR-0044 修訂一全文已寫好**（proposed，見第二段，可直接貼上）。
- C-1～C-9 都已併入。C-1 寫成 Decision 7 的七款守門條款，每款都能用 AST、SQL trace 或參數化測試檢查。
- Options 增列 (iii-c)，評估寫在 Options 之下的小節。**TA 建議採用**，最終由 CEO 決定。
- Consequences 增列 R-f、R-g；Context 第 3 點註明「更正風控 RC-29」，並寫入 RC-47 的量級更正。
- Decision 第 4 點已依 C-3 改寫：清單為空時，清單區塊整段不顯示。
- 時序依 C-8 寫在 Decision 6。

**讀碼新發現（會影響風控接受 (iii-a) 的前提，要回送風控確認）**
- 風控裁示 D6 時依據的前提是「set_at 每次寫入都是寫入當下的時間，只會往後移」。這個前提**在現況程式不成立**，不必等到時鐘倒退，set_at 就可能往回走。
- 原因是 `set_capital` 先取時間、後取寫鎖：`store.py:1052` 在組 dict 時就呼叫 `datetime.now(UTC)`，比 `_set_state` 開連線（`:1014`）和第一句 upsert 取得寫鎖（`:697`）都早。兩個寫入者並發時，先取時間但後 commit 的那一方，會把 set_at 寫成較早的值，原本已出現的 yes 標示就會消失。
- 另外，現行 `set_capital` 與 N-197a 規格的 `set_total_deploy` 都有 `at` 參數（`store.py:1039`；`work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md:275`），違反 C-1「不得由參數傳入」。
- 我在 C-1 第 3 款補上修法，比風控原條件更嚴：
  - 時間必須在同一連線的 `BEGIN IMMEDIATE` 成功之後才取；
  - 移除 `at` 參數；
  - 因此 `set_capital` 要改為自己開 `BEGIN IMMEDIATE`。對 `set_capital` 而言，這部分取代 N195-C4 與 N197a-C7 的對應句。

**交付 2：兩項前提**
1. **RC-42 成立：authorship 在 app/ 內是單調的。**
   - 確認鍵唯一可能的刪除路徑是 `_write_state` 收到 None 值（`store.py:694`），但沒有任何呼叫者對確認鍵傳 None。
   - `playbook_rule_params` 在 app/ 內沒有 DELETE 或 UPDATE，只有 `INSERT OR REPLACE`（`:1196`、`:1228`，主鍵是 version），列數不會減少。
   - 限定條件：app/ 以外的寫入（手動 SQL、DB 檔替換）不在範圍內。
2. **C-1：現況 TD 與 set_at 的寫入者只有 `set_capital`**，呼叫點有兩個（`service.py:1908` 是 rebalance，`:2030` 是 confirm_rules）。依 spec，N-195／N-197a 合入後 rebalance 改用 `set_total_deploy`，`set_capital` 只剩 confirm_rules 在用。值的來源與問題見上段。

**交付 3：W-25f 語意確認成立，附三個顯示條件。**
- 依 D7 第 2 點，只要顯示條件照下面三條，「今日仍用高波動門檻」在顯示時一定為真。
- 另有兩個讀碼觀察要交風控，**不擋 W-25f 定稿**：
  - O-1：隔日到新資料進來之前，標籤已消失，但今日頁仍用 20%，方向不保守；
  - O-2：D7 第 3 點的 prev 以台北今日計算，資料落後時，取消標記反而會讓舊資料的評估改用 20%。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 交付 1：ADR-0044 修訂一全文（proposed，可直接貼上）

````markdown
# ADR-0044：stock-desk 排程台 REBALANCE 之後，未結算的 R 系列買進列如何處置

- 狀態：proposed
- 日期：2026-11-10（修訂一，同日：併入風控 C-1～C-9，增列 (iii-c)、R-f、R-g）
- 決策者：tech-architect（草案）；risk-compliance-officer（審查：2026-11-10 CONDITIONAL APPROVE，附 C-1～C-9；修訂一的 C-1 第 3 款與 (iii-c) 回送確認）；CEO（裁示 (iii-c) 採否，以及修正或接受殘留 R-a～R-g）
- 依據：
  - [TA-210]：`work/reviews/2026-11-10-N209b補遺三與N210評估ADR0044草案-tech-architect.md` 第三部分
  - [風控-44]：`work/reviews/2026-11-10-交付B裁示ADR0044審查與字面定稿-風控.md` 第二部分（C-1～C-9）、RC-40、RC-47
  - [TA-197]：`work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md` 3.8～3.9（N-197a、`TotalDeployStamp`）
- 適用範圍：僅 product/stock-desk。路徑相對於 `apps/stock-desk/backend/`。
- 標註：
  - 行號是 2026-11-10 工作樹的快照。N-177a、N-195、N-196、N-197a、N-209b 都還沒合入，行號會漂移，抽驗請以內容定位。
  - `set_total_deploy`、`TotalDeployStamp`、`_total_deploy_stamp`、`_read_total_deploy_stamp`、`_total_deploy_state` 與 N-197a 的寫鎖交易都是規格名稱，以實際合入為準；名稱不同時回 TA。

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
6. **TD 設定時間的寫入與取值時點**（讀碼；修訂一新增，是 C-1 的依據）：
   - **寫入者**：現況唯一的寫入者是 `set_capital`（`store.py:1033-1055`），呼叫點是 `service.py:1908`（rebalance）與 `:2030`（confirm_rules）。依 N-195、N-197a 規格，rebalance 之後改用 `set_total_deploy`（三個鍵），`set_capital` 只剩 confirm_rules 在用（N195-T6）。
   - **取值時點的問題**：
     - `set_capital` 的 set_at 在組 dict 時就取值（`:1052` `(at or datetime.now(UTC)).isoformat()`），早於 `_set_state` 開連線（`:1014`），也早於第一句 upsert 取得寫鎖（`:697`）。
     - 兩個寫入者並發時，先取時間、後 commit 的一方會把 set_at 寫成**較早**的值。
     - 所以現況下，即使時鐘沒有倒退，set_at 也可能往回走。風控 D6 判定所依的「值只會往後移」在現況不成立。C-1 第 3 款把取值移到寫鎖之後，使這個前提成立。
   - **`at` 參數**：`set_capital` 與 N-197a 規格的 `set_total_deploy`（[TA-197] :273-276）都有 `at` 參數。app/ 內沒有呼叫者傳 `at`；`tests/test_n172_duplicate_probe.py:194-198` 有傳。
   - **created_at 的取值時點**：指令列的 `created_at` 在 `commit_evaluation` 取得寫鎖**之前**取值（`store.py:1372` 先於 `:1374`）。這只會讓 created_at 偏早、標示偏向 yes，不會漏標，本 ADR 不改。
7. **R-a 的窗口**（讀碼）：
   - `evaluate_today` 在 `service.py:2200` 讀 TD，在 `:2222` 呼叫 `commit_evaluation`，created_at 在 `store.py:1372` 取值。
   - 這段期間沒有網路呼叫（日線在 `:2160-2161` 已載入），但有 `apply_effects` 與 `save_fast_market` 各自的寫入（`:2213-2218`），遇到寫鎖時，每一筆都可能等到 busy_timeout。
   - 窗口大小沒有量測。

## Options（選項比較）

| 方案 | 內容 | 優點 | 缺點 | 風險 | 與 N172-C11 | 與 ADR-0035（及相關 ADR） |
|---|---|---|---|---|---|---|
| (i) 拒寫 | 有受影響列時，REBALANCE 不寫入，回新 status | 帳冊不會出現新舊 TD 交錯 | (1) 被 G1 擋下的列永遠 `settled=0`（`store.py:1544-1546`），資料缺口的列也會懸置，都必須排除，否則 REBALANCE 永久被擋；(2) 延後調低 TD 的期間，其他標的的新 R1 仍以較高的舊 TD 計算，危害只是轉移；(3) 卡住 N-207 唯一的解閘路徑（T-09）；(4) 檢查必須放在 N-197a 的寫鎖內，等於改動 N-197a 的鎖內本體；(5) 多一個 status 與一句字面 | 中 | 相容（不寫指令列） | 相容，不動 `commit_evaluation`；讀取必須沿用 C-B1 的單一定義（ADR-0034 VETO-2） |
| (ii) 結算截股 | 結算時把股數截在現行 TD 算出的上限內 | 帳冊不超過新上限 | (1) 券商成交的是原股數，帳冊截股後會少記持股，S、P 不評估多出的股數；(2) 上限要選價格與輪內脈絡，又多一個定義來源；(3) 截後的股數放在哪裡都不對：寫回指令列違反 C11，只寫批次則列、帳冊、券商三方不一致 | 高 | 寫回 `shares` 即違反；不寫回則帳與列不一致 | 違反 ADR-0041 Decision 4 列為仍有效的「C-B6 buy 行為零改動」；改 `settle` 動帳語意必須另立 ADR；動到 ADR-0042 的同一交易 |
| (iii-a) 讀取時判定標示 | `/today` 對受影響列中「落檔時間早於現行 TD 設定時間」者加常駐標示，後端逐列給旗標 | 零寫入；涵蓋所有 TD 寫入者；不動任何交易 | (1) 只知道 TD 之後曾被寫入，不知道方向，也不知道值有沒有變；(2) 依賴 set_at 單調遞增（C-1）；(3) R-a 會漏標 | 低 | 相容（只讀） | 相容。風控裁示 ADR-0034 D6 不直接適用、原則適用，以 C-1 滿足 |
| (iii-b) 落檔戳記 | TD 寫入時，在同一寫鎖內對受影響列打一次性戳記，比照 L4（`store.py:440`） | 標示不依賴可覆寫的值 | (1) 指令列多一條 UPDATE 路徑；(2) 兩個 TD 寫入者都要在鎖內打戳 | 中 | 字面上衝突，要 ADR-0035 補充 | 要改 N-197a 的鎖內本體與 `confirm_rules` |
| (iii-c) INSERT 時落檔評估依據 | 指令列 INSERT 時，把評估所用的 TD 戳記（TD、set_at、source 三個原始字串）寫入新欄位；讀取時與現行戳記逐字比對 | 以落檔事實判定，不比時間先後；可給 TD 的方向；只在 INSERT 時寫入 | 加一個欄位與 migration；`commit_evaluation`、`_insert_directives` 的簽名做加法；舊列沒有值 | 低 | 相容（只 INSERT，不 UPDATE） | 相容，見下方評估 |
| (iv) 結果列出受影響列 | 在 N-197a 寫鎖交易內，以同一個常數 SELECT 受影響列，只有 ok 分支回傳 | 寫入當下的精確清單 | 依賴 N-197a 的鎖；寫入之後才 commit 的列不在清單內（R-a） | 低 | 相容（只讀） | 相容；持鎖期間零網路 |

### (iii-c) 評估（風控 C-2）

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

**與 N172-C11、ADR-0035、`commit_evaluation` 的關係**
- **N172-C11**：只在 INSERT 時寫入，從不 UPDATE，相容。C-N210-6 照舊。
- **N172-C1**（單一 `BEGIN IMMEDIATE`）不變。
- **N172-C2**（持鎖期間零 resolver、零網路、零其他 store 呼叫）不變。`td_basis` 是呼叫前就算好的值。
- **K1、K2 與 G1**：K1、K2 的查詢與 G1 的 SQL 都不得引用 `td_basis`（補充六：G1 零 diff）。
- **Decision 4、N172-C6**（回傳已落檔列）不變；讀取時可以帶出新欄位。
- **ADR-0033 C-10**（兩條路徑共用同一句 INSERT）維持。
- **ADR-0043 I-4**：engine 不讀 `TotalDeployStamp`。(iii-c) 只動 service 與 store，`engine.py` 零 diff。
- **結論**：不改 ADR-0035 的任何 Decision 或約束，所以不需要 ADR-0035 補充。

**能否關閉 R-a、R-b、R-c**
- **R-a**：
  - `/today` 的標示：對有 `td_basis` 的列，**可以關閉**。判定依據是評估實際用的戳記，不是時間先後。評估讀到舊戳記之後才有 REBALANCE commit，那一列記的是舊戳記，會判為 yes。
  - (iv) 清單：**不受影響**。清單是寫入當下已落檔列的快照，之後才 commit 的舊 TD 列不在清單內（但在 `/today` 會標 yes）。
  - 所以 C-3 照舊。R-a 關閉的效果是可以把**時間限定句**送風控審，不是可以寫「沒有受影響的指令」。
- **R-b**：**部分關閉**。可以給出 TD 的方向（調高、調低、值相同），但不給股數差。方向句要風控另外審，審過之前，C-9「不得寫方向」照舊。
- **R-c**：對有 `td_basis` 的列**可以關閉**，因為是逐字相等比對，不比先後。舊列仍有 R-c。

**舊列如何退回 (iii-a)**
- **判定**：`td_basis` 為 NULL 的列，一律依 Decision 3 判定，Decision 7（C-1）全部照舊適用。所以採用 (iii-c) 時，C-1 第 3 款對 `set_capital` 的修改仍然要做。
- **範圍**：N-210a 部署前已落檔、仍符合 Decision 2 的列。這些列多半在下一次結算後就離開範圍，所以退回路徑是過渡性的；但資料缺口使結算延後時，可能停留較久。
- **回退 N-210a 時**：欄位保留（`add_missing_columns` 不刪欄）。回退期間寫入的列為 NULL，重新部署後走 (iii-a)。
- **替代做法**（列給風控與 CEO 參考，不是 TA 建議）：舊列一律判為 unknown，就可以不改 `set_capital`，代價是部署初期 unknown 較多。風控已經指定退回 (iii-a)，本 ADR 照此寫。

**TA 建議：採用。**
1. 可以關閉風控最在意的 R-a（`/today` 標示），而且不改 `commit_evaluation` 的交易或鎖內語句。
2. 新列不再依賴 set_at 的先後順序。Context 第 6 點那種失效（並發寫入讓 set_at 往回走）與 R-c，對新列都不成立。
3. 全部是加法，只在 INSERT 時寫入，與 N172-C11、ADR-0035、ADR-0033 C-10、ADR-0043 I-4 都相容。
4. 保留了方向資訊，日後可以用來揭露（R-b）。

**代價**：N-210a 的範圍擴大，要碰 `commit_evaluation` 的簽名與 trace 測試，C-8 的時程壓力也會增加。若 CEO 在時程上要求 N-210a 先上，可以把 (iii-c) 拆成 N-210c 隨後合入；N-210c 合入之前，R-a 仍是殘留，C-3、C-4 照舊。

## Decision（決策，proposed）

1. **方案選擇**
   - 採 (iii-a) + (iv)。
   - (ii) 否決：帳冊截股後，帳冊與券商實況不符。
   - (i) 不採：危害只是轉移，而且會卡住 T-09。
   - (iii-b) 不採：風控裁示 ADR-0034 D6 不直接適用，但原則適用，以 Decision 7（C-1）滿足。
   - **(iii-c)**：TA 建議與 (iii-a)、(iv) 並用，由 CEO 裁示。
     - 採用時，Decision 3A 生效，Decision 3 只用於 `td_basis` 為 NULL 的列。
     - 不採時，Decision 3A 整段刪除，並在 Consequences 的「(iii-c) 不採理由」寫明理由（風控 C-2）。
2. **單一定義**：store 新增常數 `KEPT_PENDING_ENTRY_SQL`，內容是 `_PENDING_ENTRY_WHERE` 加上「批次列存在且 status = 'planned'」。(iii) 與 (iv) 都拼接這個常數，不得另寫。
3. **(iii-a) 判定**
   - 後端對 `/today` 中每一列符合第 2 點的指令列（包括今日指令表與 in-flight 清單），回傳 `td_rewritten_since_logged: Literal["yes", "no", "unknown"]`。
   - 判定只經單一純函式 `td_rewritten_since(created_at_raw, set_at_raw)`，解析規則依 Decision 7 第 5 款。
   - set_at 以**原始字串**讀取，讀取時點在 logged 與 in-flight 讀取之後。
   - 不得經由 `portfolio_state()` 的 `datetime.fromisoformat`（`store.py:1024`）取得。那裡解析失敗會 raise，`/today` 就會失敗，違反 C-6。
   - 比較在 Python 內以帶時區的 datetime 進行，不在 SQL 內比字串。
   - 前端不得自行計算。
3A. **(iii-c) 判定**（只在 CEO 採用時生效）：依 Options「(iii-c) 評估」的「內容」寫入與判定。`td_basis` 為 NULL 的列走第 3 點。
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
     - R-a 關閉之後（`commit_evaluation` 鎖內比對，或採 (iii-c) 的 `/today` 標示），才能送風控審一句有時間限定的版本，例如「本次寫入時，沒有…」。
   - **ok 分支卻是 None 時（風控 C-5）**：前端顯示「清單無法取得」（字面由風控定稿），不得當成空清單。
   - **`message` 不改**（RC-40）：清單由前端從結構化欄位渲染。若要放進 `message`，就是改動 `REBALANCE_RESULT`，要比照 B-1 揭露，並回送風控。
5. **字面**（creative-lead 擬稿，風控逐字定稿；C-5、C-9）
   - **(iii) 的 yes 標示句**，只限三件事實：
     - 本列在 TOTAL_DEPLOY 最近一次重新設定之前產生；
     - 股數依產生當時的值計算；
     - 帳冊子句與 N9-05 用同一套限定：「成交結算時，若所指的批次仍待進場，以本列股數計入帳冊」。
   - **unknown 句**另外擬一句。
   - **(iv) 清單的字面**：同一批次有多張列時，要寫明同一批次只會有一筆成交。另外要有「清單無法取得」一句。
   - **禁止事項**：
     - 不得寫方向。採用 (iii-c) 之後，方向句也要另送風控審，審過之前仍不得寫。
     - 不得有任何建議或時機提示。
6. **範圍與時序**（風控 C-8）
   - **實作分兩張單**，都排在 N-209b 之後，都是加法，不擴大 N-209b：
     - N-210a（後端）：第 2、3、4、7 點，CEO 採用 (iii-c) 時加上 3A；
     - N-210b（前端）：第 4、8 點。
   - **審查流程**：本 ADR 經風控審過後送 CEO。風控 2026-11-10 已 CONDITIONAL APPROVE；修訂一的 C-1 第 3 款與 (iii-c) 要回送風控確認。
   - **風控建議**：N-210a 與 N-210b 在 **N-207 部署前**合入。理由是 N-207 會讓 REBALANCE 的使用頻率上升（T-09），而且 RC-47 顯示量級是整檔配額之差。
   - **CEO 若選擇接受殘留、先讓 N-207 上線**：要以書面記錄接受 R-a～R-g，逐項列名，記入交件紀錄。書面要寫明：N-210a／b 合入之前，`/today` 沒有標示，REBALANCE 結果沒有清單，只有 N-209 前端的 N9-05、N9-06 兩句靜態字面。
7. **D6 的替代保證：TD 設定時間的守門條款**（風控 C-1；全部 BLOCKING；採用 (iii-c) 時仍適用）
   1. **寫入者封閉**（AST，`store.py`）：
      - 以 `STATE_TOTAL_DEPLOY` 或 `STATE_TOTAL_DEPLOY_SET_AT` 為鍵的 dict 字面值，只能出現在 TD 寫入函式內。
      - N-197a 合入後，這個函式是 `_total_deploy_state`，它的呼叫者只能是 `set_total_deploy` 與 `set_capital`。N-197a 若沒有抽出 helper，就是這兩個函式本身。
      - 這兩個常數不得出現在其他的 `_write_state`／`_set_state` 呼叫中，也不得作為 subscript 賦值的目標。
   2. **範圍封閉**（AST，`app/`）：
      - `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT` 這兩個名稱，以及字串常數 `"total_deploy_set_at"`，只出現在 `store.py`。
      - app/ 內含 `playbook_state` 的 SQL 字串只出現在 `store.py`。
      - 這兩點現況都成立。
   3. **值的來源**：
      - set_at 的值是 `datetime.now(UTC).isoformat()`，在同一個連線的 `BEGIN IMMEDIATE` 成功之後、`COMMIT` 之前取值，與 TD 在同一次 commit。
      - TD 寫入函式（`set_total_deploy`、`set_capital`、`_total_deploy_state`）不得有任何時間參數。AST 檢查：沒有名為 `at` 的參數，也沒有 annotation 含 `datetime` 的參數。
      - 不得複製或還原舊值。AST 檢查：值的運算式只能是 `datetime.now(UTC).isoformat()`，不引用任何讀取結果。
      - 不得寫 None。值的運算式不是 None 常數，也不是含 None 的條件運算式。
      - SQL trace 加時鐘 spy：時鐘呼叫發生在 `BEGIN IMMEDIATE` 之後、`COMMIT` 之前；TD 與 set_at 的 upsert 在同一對 BEGIN／COMMIT 之間。
      - 交錯測試（比照 N197a-T5）：A 持 REBALANCE 寫鎖時，B 的 `confirm_rules` 開始等待；A commit 之後 B 完成。斷言最終 set_at 不早於 A 寫入的 set_at。
      - 本款對 `set_capital` 的改動：
        - 改為自己開 `BEGIN IMMEDIATE`，並移除 `at` 參數。
        - 對 `set_capital` 而言，這部分取代 N195-C4「不加 BEGIN IMMEDIATE」與 N197a-C7 的對應句。
        - N197a-C5（`set_capital` 零 diff）只約束 N-197a 那張 PR，不受影響。
        - `set_capital` 仍在同一個交易內寫四個鍵（N197a-C6）。
        - `tests/test_n172_duplicate_probe.py:194-198` 改以直接 SQL 種入，同檔 `:135` 已有同型寫法。
   4. **DELETE 路徑**：`_write_state` 的 DELETE 分支（`store.py:694`）不會收到這兩個鍵。由第 1、3 款的 AST 保證；另以 SQL trace 斷言 TD 寫入交易內沒有 DELETE。
   5. **讀取與解析**：
      - 單一純函式。兩個時間一律解析為帶時區的 datetime（`utcoffset()` 不為 None）。
      - naive、解析失敗、任一缺值，一律為 unknown，不得為 no。
      - 參數化測試表：set_at 缺值 → unknown；created_at 缺值 → unknown；任一為 naive → unknown；任一不可解析 → unknown；set_at 晚於 created_at → yes；相等或較早 → no。
   6. **日後變更**：新增 TD 或 set_at 的寫入路徑，或改動第 3 款的取值方式，都要回 TA 與風控。
   7. **適用範圍**：採用 (iii-c) 時，第 1～6 款仍然適用，因為舊列會退回 (iii-a)。
8. **前端呈現**（風控 C-4、C-6）
   - 旗標為 no 時，不渲染任何文字。
   - 畫面上不得有「未標示的列依現行 TOTAL_DEPLOY 計算」或任何等義的圖例、說明、tooltip。
   - `/today` 多出的那次讀取若失敗，全部旗標為 unknown，`/today` 照常呈現。不得回 no，也不得讓 `/today` 失敗。
   - 前端不得自行比較 `created_at` 與 set_at，也不得自行比較 `td_basis`。

## Consequences（後果）

- **好處**：
  - 使用者在下單前讀 `/today` 時，看得到哪些列是在 TD 重設之前產生的。
  - REBALANCE 結果畫面可以具體列出受影響的列。
  - 帳冊語意、結算、既有指令列都不改。
  - C-1 第 3 款同時修掉現況「set_at 可能往回走」的缺陷。
- **殘留與裁示**：

| 殘留 | 內容 | 風控裁示 | 採 (iii-c) 的效果 |
|---|---|---|---|
| R-a 競態 | 評估讀取 TD 之後、commit 之前若有 REBALANCE commit，那一列以舊 TD 計算，(iii-a) 不會標示，也不在 (iv) 清單內（窗口見 Context 第 7 點） | 附 C-3、C-4，可以作為殘留交 CEO；建議修正 | `/today` 標示關閉；(iv) 清單不變，C-3 照舊 |
| R-b 沒有方向 | 標示不帶方向，TD 調高時也會出現 | 接受。標示只陳述事實，不寫方向 | 可以給出 TD 方向；方向句要另送風控審 |
| R-c 時鐘倒退 | 時鐘倒退時，標示可能消失；無法解析時為 unknown | 接受，附 C-1 的 unknown 規則 | 新列關閉；舊列仍有 |
| R-d 撤不回券商的單 | 揭露無法撤回使用者已經在券商下的單（R10） | 接受，屬系統性限制 | 不變 |
| R-e 多一次讀取 | `/today` 多一次狀態讀取 | 接受，附 C-6 | 不變 |
| R-f 結算後沒有標示 | 結算以後，帳冊上沒有標示。這一列以舊股數入帳的事實，只在結算前的 `/today` 與 REBALANCE 當下揭露。這與 ADR-0034 D6「標示持續到 closed」不同 | 列入殘留（C-7），待 CEO 接受或修正 | 不變。修法是結算時把標示複製到批次，比照 C-B6 的 `entry_before_exit_on`。這屬於改動 `settle` 的動帳語意，依 ADR-0041 Decision 4 要另立 ADR，不在本 ADR |
| R-g 量級 | 單檔差額最大為整檔配額在新舊 TD 之間的差（RC-47，Context 第 3 點） | 列入殘留（C-7） | 不變 |

- **(iii-c) 不採理由**：CEO 不採時填入，附 CEO 書面理由；TA 列的成本見 Options。
- **代價**：
  - `set_capital` 改用自己的 `BEGIN IMMEDIATE`，等鎖時間從第一句 upsert 提前到交易開頭，語意不變。
  - 一個既有測試要改種入方式。
  - 採用 (iii-c) 時，見 Options 的成本。
- **被約束的事**：
  - (ii) 類「結算時改股數」的方案日後若要重提，必須另立 ADR，並處理 ADR-0041 Decision 4、ADR-0042 與 R10。
  - 第 2 點的常數只能有一份。
  - 前端不得自行推斷旗標。
  - TD 與 set_at 的寫入受 Decision 7 約束。
- **與既有 ADR 的關係**：
  - 與 ADR-0034、0035、0041、0042、0043 都沒有衝突，不取代任何一則。
  - 只對 `set_capital` 局部取代 TA 規格 N195-C4 與 N197a-C7 的對應句（不是 ADR）。
````

**對實作的約束（qa-reviewer 可以逐條檢查）**
- **C-N210-1**：`KEPT_PENDING_ENTRY_SQL` 只能有一個定義，(iii) 與 (iv) 都拼接它。以 grep 計數釘住。
- **C-N210-2**：旗標由後端計算。前端 grep 不得出現 `created_at`、`set_at`、`td_basis` 的比較。
- **C-N210-3**：set_at 的讀取在 logged 與 in-flight 讀取之後，以呼叫順序測試釘住。讀取用原始字串，不經 `portfolio_state()`。
- **C-N210-4**：(iv) 的 SELECT 在 N-197a 寫鎖交易內、寫入之前執行，持鎖期間零網路呼叫。以 trace 測試釘住。
- **C-N210-5**：非 ok 分支的 `kept_pending_entries` 為 None。
- **C-N210-6**：不得 UPDATE `playbook_directives` 的任何新欄位。`UPDATE playbook_directives` 的出現位置只能維持現有兩處。
- **C-N210-7**：Decision 7 的第 1～5 款各有對應的測試，全部 BLOCKING。
- **C-N210-8**：清單為空時，清單區塊不存在於 DOM（render 測試）。前端 grep「沒有受影響」計數為 0。
- **C-N210-9**：ok 分支而清單為 None 時，渲染「清單無法取得」（render 測試）。
- **C-N210-10**：旗標為 no 時零文字（render 測試）。前端 grep 不得出現 Decision 8 禁止的圖例句。
- **C-N210-11**：對 `/today` 的額外讀取注入例外 → 全部旗標為 unknown，`/today` 回 200。
- **C-N210-12**（採用 (iii-c) 時）：
  - `td_basis` 只在 `_insert_directives` 的 INSERT 寫入；
  - K1、K2、G1 的 SQL 不引用 `td_basis`（grep）；
  - `commit_evaluation` 的 `td_basis` 參數沒有預設值（AST）；
  - `evaluate_today` 交給 `evaluate()` 的 portfolio 與交給 `commit_evaluation` 的 stamp，來自同一次 `portfolio_with_stamp()` 呼叫（AST）；
  - `engine.py` 零 diff。
- **C-N210-13**（採用 (iii-c) 時）：migration 測試。舊 DB 補上欄位，舊列為 NULL，判定走 (iii-a)，`td_flag_basis == "time_order"`。
- **C-N210-14**（採用 (iii-c) 時）：交錯測試。在評估讀取戳記之後、`commit_evaluation` 之前注入一次 REBALANCE commit → 該列為 yes、`td_flag_basis == "recorded"`。把比對換成 (iii-a) 時，這個測試會失敗，作為效力證明，附在 PR 說明、不 commit。
- **禁止事項**：不得在結算時改變股數；不得以 `pending_directives` 取代 C-B1 的定義。

#### 交付 2：兩項前提的確認

**(1) RC-42：authorship 是否單調。成立（範圍限 app/）。**
- **authorship 的判定**：`rule_set_authorship`（`store.py:1164-1176`）在確認鍵存在、或 `playbook_rule_params` 有任何一列時，就判為已確認。`user_authored` 與 on_date 無關。
- **DELETE（grep app/ 全部）**：
  - playbook 表唯一的 DELETE 是 `_write_state` 收到 None 值時的 `DELETE FROM playbook_state`（`store.py:694`）。既有測試 `tests/test_playbook_settle_on_request.py:298-305` 也斷言這是 playbook store 唯一的 DELETE。
  - 其他 DELETE 都是別的表：`kelly/store.py:278`、`positions/store.py:388`、`alerts/store.py:219`、`data/cache.py:390`、`:522`、`:532`。
- **`_write_state` 的呼叫者**：`_set_state`（`:1015`），以及 `commit_emergency_exit`（`:1437`，鍵是 `STATE_EMERGENCY_UNTIL`，值是 isoformat，不會是 None）。
- **`_set_state` 的呼叫者，以及哪些可能傳 None**：

| 位置 | 函式 | 鍵 | 可能為 None |
|---|---|---|---|
| `:1048-1055` | `set_capital` | 現金與 TD 三鍵 | 否 |
| `:1084-1094` | `save_fast_market` | 含 `fast_market_vol` | 只有 `fast_market_vol` |
| `:1097` | `set_cash` | 現金 | 否 |
| `:1100` | `freeze` | 凍結 | 否 |
| `:1103` | `freeze_emergency` | 出清凍結 | 否 |
| `:1106-1111` | `set_defense` | 含 `defense_since` | 只有 `defense_since`（解除防禦時） |
| `:1206-1211` | `confirm_rule_set` | `rule_set_confirmed_at`、version | 否，`moment` 一定是字串 |

  沒有任何呼叫者對 `STATE_RULE_SET_CONFIRMED_AT` 傳 None。
- **`playbook_rule_params`**：
  - app/ 內沒有 DELETE 或 UPDATE。
  - 寫入只有 `INSERT OR REPLACE`：`:1196`（`confirm_rule_set`）與 `:1228`（`submit_rule_change`）。
  - 主鍵是 `version`（`:104`）。REPLACE 只取代同一個主鍵的列，所以 `COUNT(*)` 不會減少。
- **整表刪除**：app/ 內的 DROP 都是別的表（`positions/store.py:157`、`:163`，`sectors/store.py:377`）。playbook 的 `_MIGRATIONS`（`:178-193`）只加欄。
- **對 N9-08 的意義**：
  - 旗標 `not user_authored and total_deploy_recorded` 為真，表示目前未確認。
  - 依單調性，寫入 TD 的當下也一定未確認：若當時已確認，現在仍會是已確認。
  - 所以「這筆紀錄寫入時，規則集尚未確認」為真，前提是 TD 由 app/ 寫入。
- **限定條件**：
  - app/ 以外的寫入（手動 SQL、DB 檔替換或還原）不在範圍內，比照 R-10、1d。
  - `scripts/` 的兩支 probe 我只看到 SELECT（`n172_duplicate_probe.py:121`、`n177_n190_backtrack_probe.py:181`），沒有全文盤點。
- **建議（交 dev-lead，隨 N9-08 的旗標一起做）**：加一個守門測試。
  - AST 檢查：`STATE_RULE_SET_CONFIRMED_AT` 作為 dict 鍵，只出現在 `confirm_rule_set`，而且值不是 None。
  - 檢查含 `playbook_rule_params` 的 SQL 字串，不含 DELETE 或 UPDATE。
  - 日後新增刪除路徑時，回 TA 與風控。

**(2) C-1：TD set_at 的寫入者與值的來源**

**現況**
- **寫入者**：dict 字面值以 `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE` 為鍵的，只有 `set_capital`（`store.py:1048-1055`）。這三個常數在 app/ 內只在 `store.py` 被引用（`:221`、`:228`、`:1020`、`:1023`、`:1051-1053`）。
- **呼叫點**：
  - `service.py:1908-1912`：`rebalance`，source 為 `REBALANCE_SOURCE`；
  - `service.py:2030-2034`：`confirm_rules`，source 為 `CONFIRMATION_SOURCE`。
  - 兩處都沒有傳 `at`。
- **值的來源**：`(at or datetime.now(UTC)).isoformat()`（`:1052`）。
  - 是帶時區的 UTC 時間；
  - 與 TD 在同一個 `with conn` 內一起 commit；
  - **但取值時點早於取得寫鎖**（見 ADR Context 第 6 點），所以並發時不單調；
  - 而且 `at` 參數允許從外部傳入。
- **其他路徑**：沒有任何路徑對這三個鍵寫入 None。

**spec（N-195、N-197a，[TA-197] 3.9）**
- REBALANCE 改用 `set_total_deploy(..., expected=..., at=None)`，只寫 TD 三鍵，在 `BEGIN IMMEDIATE` 內經 `_total_deploy_state(total_deploy, source, at)` 寫入。取值在鎖內，這點正確，但仍有 `at` 參數。
- 之後 `set_capital` 只剩 `confirm_rules` 在用（N195-T6）。依 N197a-C5、C7，`set_capital` 零 diff，也不加 `BEGIN IMMEDIATE`。

**結論**
- 寫入者封閉成立：N-197a 之後只有兩個寫入函式。
- 值的來源要依 ADR Decision 7 第 3 款修正兩處：
  - 移除兩個函式的 `at` 參數；
  - `set_capital` 改在寫鎖之後才取時間。
- 這是對風控 C-1 的加嚴。原因是風控所依的「值只會往後移」在現況不成立，所以要回送風控確認。

#### 交付 3：W-25f 語意確認

**結論：確認成立。** W-25f 原稿是「高波動標記已取消：{M} 月 {D} 日起適用（依系統日曆推算），今日仍用高波動門檻」，讀法與 D7 第 2 點一致，前提是後端照下列三個條件顯示。這三個條件是後端約束，不改字面，因此依風控 RC-32 與第三部分的裁示，W-25f 可以定稿。

- **W25f-1（顯示條件）**：
  - `high_volatility == 0`，而且 D7 第 2 點那一個單一純函式以參考日算出的生效值為 1。這等價於 `high_volatility_prev == 1` 且參考日不晚於 `changed_on`。
  - 不得用「目標值為 0 且 `changed_on` 不為 NULL」來判定。同一天先標記再取消時，prev 是 0，這時「今日仍用高波動門檻」不為真。
- **W25f-2（參考日）**：
  - 參考日用 `today_tpe`，取值來源與 D1 第 4 點、D8 第 6 點相同，也和 D7 第 3 點計算 prev 時所用的日期一致。
  - 在這個條件下，W-25f 只會在 `today_tpe == changed_on` 當天顯示。
  - 那一天所有 `/today` 評估的 data_date 都不會晚於 `today_tpe`，也就是不晚於 `changed_on`，所以生效值等於 prev，也就是 1。
  - 因此「今日仍用高波動門檻」在顯示時一定為真。
- **W25f-3（日期）**：
  - {M}/{D} = `calendar.next_trading_day(changed_on)`（D7 第 5 點）。
  - 「起適用」指的是**依據資料日**：依據資料日為 M/D（含）以後的評估，改用一般門檻。
  - 日曆退回判定的限制，已由「（依系統日曆推算）」揭露。
  - creative-lead 備註裡的「到 M 月 D 日」要讀成「到 M 月 D 日的資料進來之前」：M/D 當天收盤資料進來之前，今日頁仍用高波動門檻。W-25f 句子本身沒有寫「到」，所以字面不受影響。

**讀碼觀察（交風控與 PM，不擋 W-25f 定稿）**
- **O-1：標籤消失的缺口**
  - 情境：`today_tpe` 已晚於 `changed_on`，但 `/today` 的 data_date 仍不晚於 `changed_on`。例如隔日收盤資料進來之前、週末、休市、資料落後。
  - 這時 W-25f 已不顯示（參考日判定為已適用），W-27 也可能跟著不顯示，但今日頁仍用 20%。
  - 方向不保守：放寬的門檻仍在使用，畫面上卻看不到。
  - 這和 FR-51 的 S2 判定基準差異是同一型問題。W-25e 也有對稱的缺口，但方向是保守的。
  - TA 建議：比照 FR-51，把高波動標籤也納入「本頁依台北日期判定；今日頁依資料日判定」那句事實說明。由風控裁示。
- **O-2：D7 第 3 點的 prev 以台北今日計算**
  - 資料落後時，prev 可能記到一個從來沒有適用過的值。
  - 例：週一標記後，週二早上（data_date 仍是週一）取消。
    - 取消前，以週一資料做的評估用 15%（標記要從週二的資料起才適用）。
    - 取消時，prev 以週二計算，記為 1。
    - 取消後，同樣以週一資料做的評估改用 20%。
  - 也就是說，取消標記反而讓舊資料的評估改用較寬的門檻，方向不保守。
  - 已落檔的 P3 列受 K1 保護，不受影響；只影響之後才做出的 P3 判斷。
  - W-25f 的句子在這個情境下仍然為真。
  - 只靠日曆沒有完美的修法，要不要修 ADR-0043 D7，由 TA 另行評估，交風控知悉。

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - `/home/user/AICompany/work/reviews/2026-11-10-交付B裁示ADR0044審查與字面定稿-風控.md`（全文）
  - `/home/user/AICompany/work/reviews/2026-11-10-N209b補遺三與N210評估ADR0044草案-tech-architect.md`（全文）
  - `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`：:220-352（N-197a spec）
  - `/home/user/AICompany/work/stock-desk-N207字面草稿-creative-lead.md`：grep W-25、T-25f
  - `/home/user/AICompany/work/reviews/2026-11-10-N207N209擬字面前置裁示-風控.md`：grep RC-32、W-25f
  - `/home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md`：grep FR-49、AC-65、FR-51
  - ADR-0043：:15-50、:313-328，grep `today_tpe`
  - ADR-0034：grep D6
  - ADR-0035：grep N172-C1、C2、C11
  - ADR-0001 模板
- **讀過的程式**（唯讀）：
  - `apps/stock-desk/backend/app/playbook/store.py`：:95-239、:680-749、:1000-1247、:1250-1472
  - `apps/stock-desk/backend/app/playbook/service.py`：:1890-2035、:2123-2252
  - `apps/stock-desk/backend/tests/test_playbook_exit_idempotency.py`：:725-754
- **grep**（app/ 與 backend 全部）：`DELETE`、`_write_state(`、`_set_state(`、`STATE_TOTAL_DEPLOY`、`set_at`、`rule_set_confirmed_at`、`playbook_rule_params`、`playbook_state`、`DROP`、`set_capital(`、`confirm_rule_set(`、`set_total_deploy`、`at=`、`isolation_level`、`_connect`。
- **沒有查證的部分**：
  - 沒有 Bash，以上全部是讀碼推論，沒有實跑。「set_at 可能往回走」的競態要以 Decision 7 第 3 款的交錯測試實證。
  - N-195、N-197a、N-209b 都還沒合入，`set_total_deploy` 依 spec 推論。
  - R-a 的窗口大小沒有量測。
  - (iii-c) 的成本是定性估計。schema 釘住測試只看了一處，沒有全面盤點。
  - `scripts/` 兩支 probe 沒有全文盤點。
  - CEO 本機 DB 的狀態不明。
- **需要 CEO 親自決定**：
  1. (iii-c) 採或不採（TA 建議採用）。
  2. N-210a／b 是否在 N-207 部署前合入。若選擇接受殘留，要書面記錄接受 R-a～R-g。

## 四、下一步

1. **risk-compliance-officer**：
   - 確認修訂一的兩處變更：Decision 7 第 3 款（風控所依的「set_at 只會往後移」在現況不成立，加嚴後才成立），以及 (iii-c) 的評估。
   - 裁示 O-1（高波動標籤是否納入 FR-51 的判定基準說明）；知悉 O-2。
2. **tech-writer**：風控確認後，把第二段的 ADR 全文以 proposed 落檔為 `docs/adr/0044-…md`。CEO 裁示 (iii-c) 後，依 Decision 1 刪除或保留 3A，並填入不採理由。
3. **coordinator**：
   - 把 (iii-c) 的採否與 C-8 的時序選擇送 CEO。
   - 若 CEO 選擇接受殘留，取得逐項列名 R-a～R-g 的書面紀錄，記入交件紀錄。
4. **creative-lead**：W-25f 依本次確認改標「定稿」。依 Decision 5 擬 (iii) 的 yes 句、unknown 句、(iv) 清單句與「清單無法取得」，送風控。
5. **dev-lead**：
   - CEO 核可後，開 N-210a（含 Decision 7；採用時加 3A）與 N-210b。
   - 隨 N9-08 的旗標加上 RC-42 的守門測試。
   - W-25 標籤依 W25f-1～3 實作。
6. **product-manager**：若風控採納 O-1，修改 FR-51 的範圍。

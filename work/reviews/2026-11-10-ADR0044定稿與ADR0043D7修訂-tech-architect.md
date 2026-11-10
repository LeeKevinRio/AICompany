# ADR-0044 定稿版、ADR-0043 D7 第 1～3 點修訂（O-2）、RC-57 條件 3 規格

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：ADR-0044 定稿版、ADR-0043 D7 第 1～3 點修訂（O-2）、RC-57 條件 3 規格

## 一、本次結論

全程唯讀：沒有改檔、沒有執行指令、沒有讀 `.env`、沒有碰 `data/*.db`。三項交付都完成，可以直接貼上。其中**兩件事要回送風控**，**一件事要通知 dev-lead**。

**交付 1：ADR-0044 定稿版全文（proposed）**，見第二段 1-A，後面接約束 C-N210-1～17。
- RC-52 的三項 required 都已併入 Decision 7。
  - 第 5 款：時間相等判為 unknown。
  - 第 3 款：交錯測試改成在 B 的第一次 `_connect` 暫停。這個測試在 N-210a 的 base 上一定會失敗，失敗輸出作為效力證明。
  - 第 1 款：補上原生 SQL 的封閉、三個字串常數只能出現在常數定義處，以及動態鍵的封閉。
- RC-52 的 suggested（先存成區域變數再寫入）已併入第 3 款。
- RC-53 條件 1、2 已併入：新增 C-N210-15，並擴寫 C-N210-12。條件 3 的「舊列一律判為 unknown」替代做法，在 Options 與 Decision 1 寫明不採。
- 「決策者」欄與 Decision 6 已改為「風控 2026-11-10 確認修訂一（RC-52～RC-54）」，並附上檔名。
- Decision 1 寫成寫法 A／B 兩段，由 CEO 裁示後二擇一。Decision 6 列出三種時序，依風控偏好排序。
- **新發現（通知 dev-lead）**：N-209 評估方案 B 規劃 ok 分支「由 service 產生 `at`，傳給 `set_total_deploy(at=…)`」，這與第 3 款「寫入函式不得有時間參數」衝突。
  - 解法已寫進第 3 款：`TotalDeployWrite` 加一個欄位 `stored`，N-209b 改從這個回傳值取本次寫入時間。
  - N-209b 若先合入並用了 `at=`，N-210a 就要回頭改它。

**交付 2：ADR-0043 D7 第 1～3 點修訂**，見第二段 2-A～2-E。
- 改用「只能新增的變更歷程表」`playbook_high_volatility_log`，精確保持 FR-30：
  - 每一筆變更，從資料日晚於它的 `changed_on` 起適用；
  - 判定只依 id 排序；
  - 驗收標準 1 是由結構保證成立的。
- 這是精確做法，不是近似，所以**不偏離 AC-65，沒有 AC 需要 PM 修改**。只建議 PM 補兩處說明、加兩條新 AC（都是加嚴）。
- 較嚴退回只用在兩處：評估時資料無法解析（生效值取 0），以及時鐘倒退時的寫入規則。
- D3 第 7 點 J/I 條文一字未動，I-4 原文也不動。不過 D4 第 3、4 點、D9 第 1 點、Consequences「被約束」要連動改字，全文附在 2-B。
- **字面真偽有變，回送風控**：
  1. **W-25f「今日仍用高波動門檻」不再恆真。** O-2 原例中，週二早上取消、資料日還是週一時，今日頁其實用 15%。方向保守，但字面不實。
  2. **W-25e 多了一種方向不保守的落差。** 資料落後期間內有多次變更時，標籤寫「尚未適用」，今日頁卻用 20%。這仍在 W-27 第二句的揭露範圍內。
  - W-25d、W-27、W-22 第二行的真偽沒有改變。

**交付 3：RC-57 條件 3**，見第二段 3-A～3-C。
- 新設 store 方法 `rule_set_snapshot(on_date)`：一個連線、一個 `BEGIN`…`COMMIT`，一次讀出確認鍵、參數表的現行列與 COUNT，以及 TD 三鍵。旗標 `td_recorded_while_unauthored` 只在這裡算。
- 不併入 `capital_record()`。
- 放在新的後端加法單 **N-209c**，順序是 N-209b 之後、N-209 前端之前。閘仍是 AC-20，不擋 N-209b。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 交付 1-A：ADR-0044 定稿版全文（proposed，可直接貼上）

````markdown
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
````

#### 交付 1-B：對實作的約束（qa-reviewer 可以逐條檢查）

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

#### 交付 2：ADR-0043 D7 第 1～3 點修訂（風控 RC-56，O-2）

**2-0 方案比較**

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| **(A) 只能新增的變更歷程（採用）** | 每次變更 INSERT 一列（value、changed_on）；某個資料日的生效值 = changed_on 早於該日的列中 id 最大者，沒有就用基準值 | 精確保持 FR-30；多次變更、同日來回、資料落後都正確；變更歷史不被覆寫，可稽核；判定不需要日曆 | 多一張表、兩個 trigger；D4 的寫入集合要加一處；名單頁標籤與今日頁的落差在少數情形下改變方向（見 2-D） | 低 |
| (B) 保留 prev／changed_on 兩欄，無法判定時取 0 | 寫入時若可能有資料日落在 changed_on 之前的評估，prev 取 0 | 改動小 | 單一個 prev 表達不了「資料日週一用 0、週二用 1」，所以只能近似；取 0 時當日評估改用 15%，違反 AC-65 第二段（「今日取消，今日 16% 仍不觸發」），必須由 PM 改 AC | 中 |
| (C) 存「起適用資料日」= `next_trading_day(changed_on)` | 寫入時以日曆算出生效日 | 判定簡單 | 依賴日曆退回判定，休市推算錯誤會直接改變門檻；原 D7 第 2 點刻意不用日曆 | 中 |
| 維持現行 D7 | — | — | O-2：取消標記反而讓舊資料的評估改用 20%，違反 FR-30 本意，風控不接受殘留 | 高（風控不接受） |

**2-A：D7 第 1～3 點修訂全文（可直接貼上，取代 ADR-0043 現行 D7 標題與第 1～3 點；第 4～6 點原文不改）**

````markdown
### D7：高波動標記的接線與生效（併入 N-204；第 1～3 點 2026-11-10 依風控 RC-56（O-2）修訂，待風控確認。確認前 D7 不得轉 accepted，N-204 的 D7 實作不得合併）

1. **資料：只能新增的變更歷程**
   - 在 `_SCHEMA` 新增表 `playbook_high_volatility_log`（`CREATE TABLE IF NOT EXISTS`），欄位如下：
     - `id INTEGER PRIMARY KEY AUTOINCREMENT`
     - `symbol TEXT NOT NULL`
     - `value INTEGER NOT NULL CHECK (value IN (0, 1))`
     - `changed_on TEXT NOT NULL CHECK (date(changed_on) IS changed_on)`：Asia/Taipei 日期，ISO 格式，取值見第 3 點
     - `created_at TEXT NOT NULL`：UTC ISO
   - 這張表沒有 UNIQUE 約束，所以 `INSERT OR REPLACE` 不可能取代既有列。
   - 另以 `CREATE TRIGGER IF NOT EXISTS` 擋 UPDATE 與 DELETE（`RAISE(ABORT, …)`），比照 D9 第 3 點。
   - app/ 內對這張表只有第 3 點那一句 INSERT。`INSERT OR REPLACE`、UPDATE、DELETE 計數為 0（grep）。
   - `playbook_symbols.high_volatility` 改稱**基準值 B**：
     - 是部署前就存在的值，app/ 內不寫（現況就沒有寫入者，見 Context 第 1 點）；
     - `playbook_symbols` 沒有該檔的列時，B = 0。
   - **撤回**原第 1 點的 `high_volatility_prev`、`high_volatility_changed_on` 兩欄，不新增。
   - D3 第 7 點 I-4 原文不動：那兩個名稱照樣不得出現在 `engine.py`。新名稱的 engine 檢查見第 2 點。
   - **第 4～6 點的讀法**（原文不改，依此對照）：
     - 「`changed_on`」指該檔歷程中 **id 最大一列**的 `changed_on`；
     - 「`changed_on` 為 NULL」（第 6 點）指該檔在歷程表**沒有任何列**；
     - 「目標值」指第 2 點的 T；
     - 第 4 點的 `effective` 指第 2 點的 E。

2. **判定：單一純函式**（與 `entry_gate_open` 同放 `store.py`，只有一份定義）
   - `HighVolChange(NamedTuple)`：`id: int`、`value: int`、`changed_on: date`。
   - **生效值** `effective_high_volatility(*, base: int, history: Sequence[HighVolChange], on: date) -> int`，記為 E(on)：
     - 適用列 = `history` 中 `changed_on < on` 的列；
     - 有適用列時，取其中 **id 最大者**的 value；沒有就取 base。
   - **目標值** `target_high_volatility(*, base: int, history: Sequence[HighVolChange]) -> int`，記為 T：
     - `history` 有列時，取 id 最大者的 value；沒有就取 base。
   - 兩個函式都只依 id 排序，不依 `changed_on` 排序。
   - **評估**：`on = data_date`。
     - data_date 都是交易日，所以「`changed_on` 早於 data_date」等價於「變更日之後的第一個交易日起適用」。
     - 依據資料日不晚於變更日的評估，用的是變更前的值（FR-30、AC-65）。
     - 每一筆變更各自從它的 `changed_on` 之後適用，不會覆寫任何較早資料日的生效值。
     - 判定不需要日曆，也不受週一到週五退回判定的影響。
   - **名單頁標籤**：`on = today_tpe`，取值來源與 D1 第 4 點、D8 第 6 點相同。
     - W-25d：T = 1 且 E(today_tpe) = 1；
     - W-25e：T = 1 且 E(today_tpe) = 0；
     - W-25f：T = 0 且 E(today_tpe) = 1；
     - 其餘情形不顯示高波動標籤。
     - W-25e、W-25f 的日期依第 5 點。
   - **讀取**：`symbol_states(on)` 用一個連線、一個讀取交易（`BEGIN`…`COMMIT`），讀出 `playbook_symbols` 與 `playbook_high_volatility_log`，對每檔呼叫上述函式。
   - **較嚴退回**（RC-56 驗收標準 2）：
     - 歷程列或基準值無法解析時，評估路徑上該檔的生效值一律為 0（BIAS25 大於 15%），不得取 1。在 app/ 內這種情況由 CHECK 約束排除，只可能來自 app 外的寫入。
     - 名單頁遇到同一情形，不得以 0 或 1 代入標籤，這次讀取視為失敗。
     - app 外的寫入列為殘留，比照 RC-49 條件 4。
   - **engine 名稱檢查**（補 I-4 的可檢查形式，不改 I-4）：`engine.py` 不出現 `playbook_high_volatility_log`、`HighVolChange`、`effective_high_volatility`、`target_high_volatility`。engine 照舊只透過 `build_market_snapshot(high_volatility=…)` 拿到值（第 4 點）。

3. **寫入：高波動標記操作**（D4 的兩步流程與鎖內流程）
   - (a) **鎖內讀取**：該檔的基準值與全部歷程列（依 id）。
   - (b) **時鐘**：以 D4 第 3 點 (b) 讀到的時鐘，換算成 Asia/Taipei 日期 `today_tpe`。
   - (c) **冪等**：新值等於 T 時，零寫入，也不寫稽核列（比照 D2 第 5 點）。
   - (d) **`changed_on` 的取值**：
     - 一般情形（該檔沒有歷程，或 `today_tpe` 不早於最新一列的 `changed_on`）：`changed_on = today_tpe`。
     - 時鐘倒退（`today_tpe` 早於最新一列的 `changed_on`）：
       - 標記（新值 1）：取 `max(today_tpe, 最新一列的 changed_on)`；
       - 取消（新值 0）：取 `today_tpe`。
     - 兩種取法都不比「以 `today_tpe` 寫入」寬：標記延後適用；取消不延後，而且因為 id 最大，會蓋過較晚日期的那一列。
   - (e) **INSERT** 一列：symbol、value、changed_on、created_at。
   - (f) **D9 稽核列**照常寫入。`detail_json` 記入本次歷程列的 id、value、changed_on。
   - **預覽摘要**（D4 第 1 點）包含：symbol、目前的 T、最新一列的 id（沒有則為 null）、新值、預覽時算出的 `changed_on`。
     - 確認時在鎖內重算，任一項不同就拒絕、零寫入（FR-22）。
     - 預覽與確認之間跨過台北日期，也會因 `changed_on` 不同而拒絕，使用者要重新預覽。
   - **性質**（RC-56 驗收標準 1 的論證，由結構保證）：
     - 新增的一列只會改變 `on` 晚於它的 `changed_on` 的 E(on)。
     - 所以任何一次變更，都不改變依據資料日不晚於本次 `changed_on` 的評估所用的生效值。
   - **同日來回切換**：同一天寫入的各列，對 `on` 不晚於該日的判定都不適用；對 `on` 晚於該日的判定，只看 id 最大的那一列。所以回到原值時，任何資料日的生效值都不變。
   - **多次變更**：每一筆各自從它的 `changed_on` 之後適用。例：週一標記、週二取消、週三再標記，則依據資料日週一用 0、週二用 1、週三用 0、週四起用 1。
````

**2-B：連動修訂（不在 D7 第 1～3 點，但要和 2-A 同一次落檔；D3 第 7 點 J-1～J-10、I-1～I-5 一字不動）**

- 檔頭變更紀錄加一行：「2026-11-10 依風控 RC-56（O-2）修訂 D7 第 1～3 點，以及 D4 第 3、4 點、D9 第 1 點、Consequences『被約束』的連動句（待風控確認）」。
- **D4 第 3 點 (a)**，句末加：「；高波動標記操作另讀該檔在 `playbook_high_volatility_log` 的全部列」。
- **D4 第 3 點 (d)**，改為：「(d) 寫入只限四處：`playbook_symbols` 的自有欄位 upsert、`playbook_batches` 的新輪 INSERT、`playbook_high_volatility_log` 的 INSERT（只限高波動標記操作，D7 第 3 點）、`playbook_roster_log` 的 INSERT；」
- **D4 第 4 點**：「三張表都逐列不變」改為「四張表（含 `playbook_high_volatility_log`）都逐列不變」。
- **D9 第 1 點 `detail_json`**，括號內句末加：「、高波動標記的歷程列 id、value、changed_on」。
- **Consequences「被約束」第一點**，改為：「名單路徑只能寫 `playbook_symbols` 的自有欄位、`playbook_batches` 的新輪 INSERT、`playbook_high_volatility_log` 的 INSERT、`playbook_roster_log` 的 INSERT；」
- **Consequences「壞處與代價」**，加一點：「高波動改為只能新增的歷程表：多一張表與兩個 trigger。名單頁標籤依台北日期、今日頁依資料日，兩者的落差在資料落後期間內有多次變更時會改變形態；W-25f 第三子句在這種情形下可能不實，由風控裁示（D7 第 2 點、RC-56 驗收標準 4）。」
- **待決 → 風控**，加：「確認 D7 第 1～3 點修訂與連動句（RC-56）；CEO 若先核可其餘段落，核可範圍要明示排除 D7 第 1～3 點，標為『待修訂（O-2）』」。

**2-C：參數化測試表（RC-56 驗收標準 3）**

日期採 2026-11：11-09 週一、11-10 週二、11-11 週三、11-12 週四、11-13 週五、11-14 週六、11-15 週日、11-16 週一。E 的測試不依賴日曆；涉及 M/D 的標籤測試，用固定的日曆 fixture。

評估（E）：

| # | 情境 | B | 歷程（依 id；changed_on:value） | on | 期望 E | 說明 |
|---|---|---|---|---|---|---|
| E1 | 沒有歷程 | 0 | — | 11-10 | 0 | |
| E2 | 沒有歷程、既有標記 | 1 | — | 11-10 | 1 | D7 第 6 點：部署當下即適用 |
| E3a | 單次標記，當日 | 0 | 11-10:1 | 11-10 | 0 | AC-65 第一段：當日用舊門檻 |
| E3b | 同上，次一交易日 | 0 | 11-10:1 | 11-11 | 1 | |
| E4a | 單次取消，當日 | 1 | 11-10:0 | 11-10 | 1 | AC-65 第二段 |
| E4b | 同上，次一交易日 | 1 | 11-10:0 | 11-11 | 0 | |
| E5 | **O-2 原例，取消前** | 0 | 11-09:1 | 11-09 | 0 | 15% |
| E6a | **O-2 原例，取消後** | 0 | 11-09:1, 11-10:0 | 11-09 | **0** | 取消前後都是 15%（驗收標準 1） |
| E6b | 同上 | 0 | 同上 | 11-10 | 1 | 週一的標記從週二資料起適用 |
| E6c | 同上 | 0 | 同上 | 11-11 | 0 | 週二的取消從週三資料起適用 |
| E7a | 週末標記 | 0 | 11-14:1 | 11-13 | 0 | 週五資料在週末評估，用舊值 |
| E7b | 同上 | 0 | 11-14:1 | 11-16 | 1 | |
| E8a | 週末取消 | 1 | 11-15:0 | 11-13 | 1 | |
| E8b | 同上 | 1 | 11-15:0 | 11-16 | 0 | |
| E9a | 同日來回，回到原值 | 0 | 11-10:1, 11-10:0 | 11-10 | 0 | |
| E9b | 同上 | 0 | 同上 | 11-11 | 0 | 生效值不變 |
| E10 | 同日來回（B=1） | 1 | 11-10:0, 11-10:1 | 11-11 | 1 | |
| E11a | 同日三次 | 0 | 11-10:1, 11-10:0, 11-10:1 | 11-10 | 0 | |
| E11b | 同上 | 0 | 同上 | 11-11 | 1 | |
| E12 | 多次變更、逐日 | 0 | 11-09:1, 11-10:0, 11-11:1 | 11-09／11-10／11-11／11-12 | 0／1／0／1 | 舊設計在 on=11-10 會得到 0（錯，偏嚴），取消後在 on=11-09 會得到 1（錯，O-2） |
| E13 | 多次變更跨週末 | 0 | 11-13:1, 11-14:0, 11-16:1 | 11-13／11-16／11-17 | 0／0／1 | 週五標記、週六取消，兩者都從週一起適用；id 較大的取消勝出 |
| E14a | 時鐘倒退後取消（依第 3 點 (d) 寫入） | 0 | 11-12:1, 11-10:0 | 11-10 | 0 | 與寫入前相同 |
| E14b | 同上 | 0 | 同上 | 11-11 | 0 | 與寫入前相同（寫入前沒有適用列，取 B） |
| E14c | 同上 | 0 | 同上 | 11-13 | 0 | 寫入前是 1；取消不延後，偏嚴 |
| E15 | 歷程列不可解析（以直接 SQL 繞過 CHECK 的 fixture 模擬 app 外寫入） | 0 | 11-09:1 加一列壞資料 | 11-10 | 0 | 較嚴退回 |

寫入（W）：

| # | 情境 | 期望 |
|---|---|---|
| W1 | 一般：最新一列 11-09，`today_tpe` = 11-10 | `changed_on` = 11-10 |
| W2 | 時鐘倒退標記：最新 11-12:0，`today_tpe` = 11-10，新值 1 | `changed_on` = 11-12 |
| W3 | 時鐘倒退取消：最新 11-12:1，`today_tpe` = 11-10，新值 0 | `changed_on` = 11-10 |
| W4 | 冪等：新值等於 T | 歷程表、稽核表列數都不變 |
| W5 | 預覽在台北 11-10 23:59:59，確認在 11-11 00:00:01 | 拒絕，四張表逐列不變 |
| W6 | 對歷程表 UPDATE 或 DELETE | trigger ABORT |
| W7 | 拒絕或失敗的高波動操作 | 四張表逐列不變（FR-39、AC-61） |

性質測試（P）：

- **P1（驗收標準 1，窮舉）**：
  - 範圍：日期取 11-09～11-16 共 8 天；B ∈ {0, 1}；歷程長度 0～3，依第 3 點規則逐筆寫入，含時鐘倒退；再寫入一筆。
  - 斷言：對所有 `on` 不晚於新列 `changed_on` 的日期，寫入前後的 E(on) 相同。
  - 以 itertools 窮舉即可，不需要額外套件。
- **P2**：名單頁與評估只呼叫同一組函式（grep：store 與 API 內，`effective_high_volatility` 之外沒有第二份判定）。

標籤（L，`on = today_tpe`）：

| # | 歷程（承上） | today_tpe | T | E | 標籤 | 今日頁資料日 → 實際門檻 | 備註 |
|---|---|---|---|---|---|---|---|
| L1 | E3 | 11-10 | 1 | 0 | W-25e，M/D = 11/11 | 11-09 或 11-10 → 15% | 一致 |
| L2 | E3 | 11-11 | 1 | 1 | W-25d | 11-10 → 15% | O-1 型落差，方向保守，與舊設計相同 |
| L3 | E4 | 11-10 | 0 | 1 | W-25f，M/D = 11/11 | 11-09 或 11-10 → 20% | 第三子句為真 |
| **L4** | **E6（O-2 原例取消後）** | **11-10** | **0** | **1** | **W-25f，M/D = 11/11** | **11-10 → 20%（真）；11-09 → 15%（「今日仍用高波動門檻」為假）** | **真偽有變**：方向保守，但字面不實 |
| L5 | E9 | 11-10 | 0 | 0 | 不顯示 | 15% | W25f-1 的禁止條款：不得以「T=0 且有歷程」判定 |
| **L6** | **E12** | **11-11** | **1** | **0** | **W-25e，M/D = 11/12** | **11-10 → 20%；11-11 → 15%** | **新增的不保守落差**：標籤寫「尚未適用」，今日頁（資料日 11-10）用 20% |
| L7 | E7 | 11-15（週日） | 1 | 1 | W-25d | 11-13 → 15% | O-1 型落差，方向保守，與舊設計相同 |
| L8 | E8 | 11-15（週日） | 0 | 1 | W-25f，M/D = 11/16 | 11-13 → 20% | 第三子句為真 |
| L9 | 任一列帶 W-25d／e／f | — | — | — | W-27 顯示 | — | 條件不變 |

**2-D：W25f-1～3、W-25d、W-25e 重新核對（RC-56 驗收標準 4、RC-58）**

讀碼前提：`evaluate_today` 的 `as_of` 是 UTC 日期（`service.py:2149`），data_date 是最新一根 bar 的日期（`:2168`）；沒有 bar 時取 `as_of`（`:2172`）。所以 data_date 不晚於 `today_tpe`。這個前提只用在下面對字面的分析；2-A 驗收標準 1 的論證不依賴它。

| 字面 | 顯示條件（新） | 與舊設計相比 | 字面真偽 |
|---|---|---|---|
| W-25d「高波動：已適用」 | T=1 且 E(today_tpe)=1 | 顯示的日子相同 | **不變**。依台北日期為真；與今日頁不同時，方向保守，由 W-22 第二行、W-27 第二句揭露 |
| W-25e「高波動：尚未適用，{M} 月 {D} 日起適用（依系統日曆推算）」 | T=1 且 E(today_tpe)=0；M/D = `next_trading_day(最新一列 changed_on)` | 顯示的日子相同 | **字面依台北日期仍為真**。但**新增一種方向不保守的落差**（L6）：資料落後期間內有多次變更時，今日頁用 20%，標籤寫「尚未適用」。這種情形一定是「資料日早於台北今日」，落在 W-27 第二句的揭露範圍內。舊設計在這個情形下今日頁用 15%，但那是 FR-30 的錯誤結果。**回送風控知悉** |
| W-25f「高波動標記已取消：{M} 月 {D} 日起適用（依系統日曆推算），今日仍用高波動門檻」 | 見下方 W25f-1′～3′ | 顯示的日子相同 | **真偽有變**：舊設計下顯示時恆真；新設計下 L4 情形為假。**回送風控** |
| W-27（RC-55 定稿） | 任一列帶 W-25d／e／f | 不變 | 真。第二句正好涵蓋 L4、L6 |
| W-22 第二行（RC-55 定稿） | 常駐 | 不變 | 真 |

**W25f-1′～3′（creative-lead 草稿 W-25 備註的替換句，可直接貼上）**

- **W25f-1′（顯示條件）**：T = 0 且 E(today_tpe) = 1，T 與 E 是 ADR-0043 D7 第 2 點的兩個純函式。不得以「T = 0 且該檔有歷程列」判定，因為同一天先標記再取消時 E = 0。
- **W25f-2′（參考日與真偽）**：
  - 參考日用 `today_tpe`，來源與 D1 第 4 點、D8 第 6 點相同。一般情形下，只會在 `today_tpe` 等於最新一列 `changed_on` 的當天顯示。
  - **「今日仍用高波動門檻」不再恆真**：今日頁的資料日 d 早於 `today_tpe`，而且該檔另有一列（不是最新那一列）的 `changed_on` 落在 [d, `today_tpe`) 時，今日頁可能用一般門檻。例如 O-2 原例週二早上：資料日仍是週一，實際用 15%。
  - 這種情形方向保守（實際門檻比字面所說的嚴）。它一定落在「資料日早於台北今日」的範圍內，W-27 第二句已有揭露。
- **W25f-3′（日期）**：{M}/{D} = `calendar.next_trading_day(最新一列 changed_on)`。「起適用」指依據資料日為 M/D（含）以後的評估改用一般門檻，讀法不變。

**交風控裁示：W-25f 第三子句怎麼處理（TA 不改字面）**

- **F1**：字面不變，把 L4 列為殘留。理由：方向保守，而且只在「資料日早於台北今日」時發生，W-27 第二句與 W-22 第二行已揭露。
- **F2**：由 creative-lead 改擬第三子句，寫成在所有情形都為真的事實。內容要點：依據資料日在 M/D 之前的評估，仍依先前的標記判定；一般情形下就是高波動門檻。改擬後由風控逐字定稿。
- **TA 建議 F2**。風控在 RC-55 撤回 W-27 舊第二句，用的是同一個理由：句子在缺口內不成立。名單頁拿不到 data_date（RC-21、Q-C14 已否決第二個資料日來源），所以沒有任何後端顯示條件能保證這個子句恆真。

**2-E：PRD 影響**

- **不偏離 AC-65**，沒有 AC 需要 PM 修改。理由：
  - AC-65 兩段都已由 E3a、E3b、E4a、E4b 覆蓋；
  - AC-34～36、FR-30～32、FR-49 都成立；
  - 近似做法（方案 B）才會違反 AC-65，本案不採。
- **建議 PM 補充（都是加嚴或說明，非必要）**：
  - FR-39 與 AC-61 的「高波動標記」，註明包含變更歷程表；
  - 新增 AC：「Given 週一標記、週二台北日資料日仍為週一時取消；When 以週一資料評估；Then 取消前後都用 15%」（E5、E6a）；
  - 新增 AC：多次變更逐日生效值（E12）。
- W-25f 若依 F2 改字面，FR-1 的標籤用詞不受影響（FR-1 沒有寫第三子句）。

**附帶觀察（不在本次範圍，交 TA 另案與 AC-95）**：新設計讓「取消既有標記」有一條正常的 app 路徑，也就是寫入一列 value=0。但這條路徑不改基準值 B，P-4a 盤點（`high_volatility=1` 的列數）的結果不會變。D7 第 6 點「取消」的移除方式，仍要另案設計並送風控。

#### 交付 3：RC-57 條件 3（同一讀取交易）

**3-A：放在哪裡**

- **TA 決定**：另設 store 方法 `rule_set_snapshot()`，不併入 `capital_record()`。實作放在新的後端加法單 **N-209c**，順序為 N-209b 之後、N-209 前端之前。閘仍是 N-209 PRD AC-20：旗標沒就位，N-209 前端不得合併。不擋 N-209b（RC-42）。
- **不併入 `capital_record()` 的理由**：
  1. `capital_record()` 是 `rebalance` 的現金閘。N209b-A1′ 以 AST 釘住「先 `rule_set_authorship`、後 `capital_record`」的順序；若把 authorship 放進 `capital_record`，`rebalance` 就會有兩個 authorship 來源。
  2. `capital_record()` 的規格是一次 `_state_map()`，不含參數表的 COUNT。
  3. N9-08 的消費者是 `GET /rule-set`（N-209 FR-4 的確認畫面與 FR-10 的結果不明畫面都讀它，見 [TA-209] 方案 B 與 F-6），不是 `rebalance`。
- **dev-lead 可以把它併入 N-209b**，但必須同時滿足兩點：N-209b 還沒送 review；併入後不延後 N-209b 的合併。不滿足就走 N-209c。
- **現況的問題（讀碼）**：
  - `_rule_set_status`（`service.py:1968-1974`）呼叫 `rule_set_authorship`，後者先 `_state_map()` 開一個連線，再另開連線查現行列與 COUNT（`store.py:1164-1173`）；
  - 接著 `portfolio_state()` 又開一個連線（`:1017-1019`）。
  - 所以旗標與金額分布在三個連線、沒有交易的讀取上。這正是 RC-57 的反例：`confirm_rule_set` 先 commit 參數列（`:1194-1205`），`confirm_rules` 之後才 `set_capital`（`service.py:2030`）。

**3-B：store 方法規格**

```python
class RuleSetSnapshot(NamedTuple):
    authorship: RuleSetAuthorship
    portfolio: PortfolioState
    stamp: TotalDeployStamp            # raw strings of the three TD keys (N-197a)
    total_deploy_recorded: bool        # STATE_TOTAL_DEPLOY key exists (same definition as capital_record)
    td_recorded_while_unauthored: bool # not authorship.user_authored and total_deploy_recorded

def rule_set_snapshot(self, on_date: date) -> RuleSetSnapshot:
    with closing(self._connect()) as conn:
        conn.execute("BEGIN")  # DEFERRED: read transaction, no write lock
        try:
            state = _read_state_map(conn)  # SELECT key, value FROM playbook_state
            row = conn.execute(<the in-force SELECT used by rule_set_authorship>, (on_date.isoformat(),)).fetchone()
            total = conn.execute("SELECT COUNT(*) FROM playbook_rule_params").fetchone()
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    # pure construction after COMMIT, from the captured values only
```

- **結構**：
  - 一個連線、一個 `BEGIN`、三句 SELECT、`COMMIT`，比照 `read_in_flight`（`store.py:1474-1497`，ADR-0035 補充四 2.3）的先例。
  - playbook store 是 WAL 模式（`store.py:842` `enable_wal`）。讀取交易從第一句 SELECT 起固定在同一個快照，之後才 commit 的寫入看不到。
  - 錯誤處理照 C-11：先 ROLLBACK，再原樣 raise。
- **單一定義**：
  - authorship 由新的純函式 `_authorship_from(state, in_force_row, params_count)` 產生。`rule_set_authorship()` 也改為呼叫它，判定邏輯只有一份；它自己的讀取方式可以不變。
  - portfolio 用 N-197a 的 `_portfolio_from_state`，與 `portfolio_state()` 共用。
  - stamp 用 `_total_deploy_stamp(state)`。
  - `total_deploy_recorded` 與 `capital_record()` 共用同一個「鍵存在」判定。
  - `td_recorded_while_unauthored` 只在 `rule_set_snapshot` 內計算一次。
- **service**：`_rule_set_status` 的 authorship 與 portfolio 只取自一次 `rule_set_snapshot(as_of)`。`RuleSetStatus` 加一個欄位 `snapshot`。`active_params` 與 `in_force_effective_date` 不變，它們不影響 N9-08 的真偽。`confirm_rules` 的回傳也經 `_rule_set_status`，所以一併適用。
- **API**：`RuleSetResponse` 新增 `td_recorded_while_unauthored: bool`。這個欄位，以及 N-209b 新增的 `.2f` 金額、台北時間字串、`total_deploy_recorded`，全部取自 `status.snapshot`。
- **前端**（N-209 前端）：確認畫面與結果不明畫面上的金額、設定時間、N9-08 顯示與否，都必須取自**同一個** `RuleSetResponse` 物件，不得混用 `/today`、`rebalance` 回應或較舊的 query 快取。欄位缺漏時走 RC-35／RC-42 的「旗標拿不到」：不顯示金額，也不顯示時間。

**3-C：約束與測試（qa-reviewer 可逐條檢查）**

- **S-1（AST）**：`_rule_set_status` 本體恰好呼叫一次 `rule_set_snapshot`，而且不呼叫 `rule_set_authorship`、`portfolio_state`、`capital_record`、`_state_map`。
- **S-2（SQL trace）**：`rule_set_snapshot` 的 `_connect` spy 恰為 1 次。語句依序是 `BEGIN`、三句 SELECT、`COMMIT`，沒有任何寫入語句。
- **S-3（grep 或 AST）**：`td_recorded_while_unauthored` 的運算式在 app/ 內只有一處（store）；service 與 API 只轉交。前端只從回應讀取（PRD 已規定）。
- **S-4（參數化）**：確認鍵存在與否 × COUNT 是否大於 0 × TD 鍵存在與否，共 8 種組合。期望旗標 = `not (確認鍵 or COUNT>0) and TD 鍵`。每一組的 `authorship` 與同一個 fixture 下 `rule_set_authorship()` 的結果逐欄相同。
- **S-5（交錯測試，附效力證明）**：
  - **暫停點**：在讀取執行緒的連線上裝 `set_trace_callback`，於「`SELECT COUNT(*) FROM playbook_rule_params` 之後的下一句語句」開始執行時暫停。
    - 現行程式中，這一句是 `portfolio_state` 的 `SELECT key, value FROM playbook_state`；
    - 新程式中，這一句是 `COMMIT`；
    - 兩個版本都用同一個 hook。
  - **寫入方**：讀取暫停期間，主執行緒依 `confirm_rules` 的順序，呼叫 `confirm_rule_set(...)`，再呼叫 `set_capital(...)`，兩者都 commit。之後放行讀取。
  - **fixture**：寫入前是未確認，TD 鍵不存在，或者存在但是舊值。
  - **斷言**：回傳的 (authorship, TD set_at) 必須是某一個已 commit 的狀態：寫入前（未確認、舊 TD 或無 TD）或寫入後（已確認、新 TD）。不得出現「未確認 + 新 TD」。
  - **效力證明**：把本測試放到 N-209c 的 base 上，以 `GET /rule-set` 或 `_rule_set_status` 執行，必須失敗：authorship 在暫停前已讀為未確認，portfolio 在暫停後讀到新 TD。失敗輸出原樣附在 PR 說明。
  - 測試 DB 必須是檔案 DB（WAL）。
- **S-6（錯誤）**：在第二句 SELECT 注入例外 → ROLLBACK 後原樣 raise，`GET /rule-set` 回 5xx，前端走「旗標拿不到」。
- **S-7（前端結構測試）**：N9-08、金額、時間三個元件的 props 來自同一個 `RuleSetResponse` 值（比照 `exitFlowStructure.test.ts` 的寫法）。
- RC-57 條件 2（authorship 單調的守門測試）與條件 4（交件紀錄），維持先前交給 dev-lead 與 coordinator 的安排。本規格不取代它們。

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - 全文：`/home/user/AICompany/work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md`、`/home/user/AICompany/work/reviews/2026-11-10-ADR0044修訂一與RC42C1W25f確認-tech-architect.md`
  - 部分：
    - `/home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md`：:1-120、:195-475，含 D3 第 7 點、D4、D7、D9
    - `/home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md`：grep FR-30～34、FR-39、FR-46、FR-49、FR-51、AC-34～39、AC-61、AC-65、AC-85、AC-86
    - `/home/user/AICompany/work/stock-desk-N207字面草稿-creative-lead.md`：W-22、W-25、W-27
    - `/home/user/AICompany/work/stock-desk-N209字面草稿-creative-lead.md`：N9-08
    - `/home/user/AICompany/work/reviews/2026-11-10-補擬四句裁定-風控.md`：RC-49
    - `/home/user/AICompany/work/stock-desk-REBALANCE畫面入口-PRD.md`：:70-120 與 grep
    - `/home/user/AICompany/work/reviews/2026-11-10-N209b補遺三與N210評估ADR0044草案-tech-architect.md`：:54-133
    - `/home/user/AICompany/work/reviews/2026-11-09-N209Q3Q4技術評估-tech-architect.md`：:120-179
    - `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`：:255-295
- **讀過的程式**（唯讀）：
  - `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`：:118-129、:200-244、:640-760、:836-842、:966-1235、:1340-1510；grep `playbook_state`、`total_deploy` 字串、`BEGIN`、`journal_mode`／`enable_wal`
  - `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`：:1960-2039、:2145-2179
  - `/home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py`：:240-262、:495-528
- **沒有查證的部分**（沒有 Bash，以下全部是讀碼推論，沒有實跑）：
  - 兩個交錯測試在 base 上會失敗，是推論，要以 C-N210-16 與 S-5 的實跑輸出實證。
  - SQLite 是否接受 `CHECK (date(changed_on) IS changed_on)`，要由 dev-lead 實測；不接受時改用 GLOB 格式檢查，日期有效性交給純函式驗證。
  - 在 `set_trace_callback` 內阻塞，會不會讓 WAL 下的另一個連線無法 commit，依 SQLite 的 WAL 語意推論沒有問題，沒有實測。
  - N-197a、N-209b 都還沒合入，`TotalDeployWrite`、`_read_state_map`、`_portfolio_from_state` 都是規格名稱。
  - 「data_date 不晚於 today_tpe」是依 `service.py:2149`、`:2168` 推論，loader 的上限沒有逐行驗證。
  - CEO 本機 DB 的狀態不明。
- **需要 CEO 親自決定**：
  1. ADR-0044 Decision 1 用寫法 A 或寫法 B（風控與 TA 都建議 A），以及 Decision 6 的三種時序（風控偏好 1 > 2 > 3）。
  2. 若要先核可 ADR-0043 的其餘段落，核可範圍要明示排除 D7 第 1～3 點與 2-B 的連動句。

## 四、下一步

1. **risk-compliance-officer**：
   - 確認 ADR-0043 D7 第 1～3 點修訂與 2-B 連動句（RC-56）；
   - 裁示 W-25f 第三子句的處理（F1 或 F2，TA 建議 F2）；
   - 知悉 W-25e 新增的不保守落差（L6）。
   - ADR-0044 定稿不必回送，由 qa-reviewer 逐條檢查。
2. **tech-writer**：
   - 把 1-A 以 proposed 落檔到 `docs/adr/0044-…md`；CEO 裁示後，依 Decision 1 保留寫法 A 或 B。
   - 風控確認 D7 之後，把 2-A、2-B 併入 ADR-0043。D3 第 7 點不得改動。
3. **dev-lead**：
   - N-210a 照 Decision 7 與 C-N210-1～17 實作，PR 附上 C-N210-16 的效力證明。
   - **N-209b 的 ok 寫入時間不要用 `at=`，改讀 `TotalDeployWrite.stored`**（C-N210-17）。
   - 開 N-209c，依 3-B、3-C 實作，在 N-209 前端合併前就位。
4. **coordinator**：把 Decision 1（寫法 A／B）與 Decision 6 的三種時序放進 CEO 決策包；告知 CEO ADR-0043 D7 的閘仍在，等風控確認。
5. **creative-lead**：W-25 備註換成 W25f-1′～3′；風控若裁示 F2，改擬 W-25f 第三子句。
6. **product-manager**：評估 2-E 的兩處說明與兩條新 AC（非必要，都是加嚴）。

相關檔案：
- /home/user/AICompany/work/reviews/2026-11-10-ADR0044修訂一確認與O1O2裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-ADR0044修訂一與RC42C1W25f確認-tech-architect.md
- /home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md（D4 :225-250、D7 :314-331、D9 :373-385）
- /home/user/AICompany/work/stock-desk-N207字面草稿-creative-lead.md（W-25 :372-391、W-27 :243-251、W-22 :339-350）
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py（`_write_state` :690-700、`set_capital` :1033-1055、`rule_set_authorship` :1152-1184、`confirm_rule_set` :1186-1211、`read_in_flight` :1474-1497）
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py（`_rule_set_status` :1968-1974、`confirm_rules` :2018-2034、`evaluate_today` :2149-2172）
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py（`_rule_set_response` :500-528）

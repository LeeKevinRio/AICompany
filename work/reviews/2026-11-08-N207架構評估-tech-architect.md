# N-207 架構評估（Q-T1～Q-T10）

- 審查者：tech-architect
- 日期：2026-11-08
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**整體判定：N-207 可以做，而且不必違反 ADR-0035「批次永不重置」。需要另立一則新 ADR（暫編 ADR-0043，proposed），補充 ADR-0035、ADR-0041、ADR-0042，不取代任何一則。** PRD 有幾處需要先改，其中兩處是事實錯誤（見 Q-T1 與 Q-T7）。

- **Q-T1 停止新進場**：採 PM 傾向的「標的層旗標」。做法如下：
  - 在 `playbook_symbols` 加一欄 `entry_stopped`，不動任何批次列。
  - service 組 engine 輸入時，剔除已停止標的的 planned 批次，engine 零 diff。
  - 新增批次狀態的方案否決（VETO）：G1 會把停止前已產生的 R1 擋下，違反 FR-10；重新加入時又要把狀態改回 planned。
  - 共用 `paused` 的方案否決：S1 站回 25MA 的自動恢復會把它清掉。
  - **PRD 事實錯誤**：`paused` 是 **S1** 的排程暫停（`models.py:248`、`engine.py:476-482`），**S2** 是黑名單（`playbook_blacklist`）。使用者的停止要和這兩者都互不覆蓋。
- **Q-T3 重新加入已出清的標的**：
  - 主鍵 `(symbol, batch_no)` 不動。新批次用該檔沒用過的 `batch_no`（目前最大值加 1 起），以一般 INSERT 寫入，另加輪次欄 `batch_round`。
  - 主鍵改為含輪次的方案否決（VETO）：要重建表，G1 的 SQL 也要改，違反 ADR-0035 補充六的「G1 SQL 零 diff」。
  - 把舊批次改回 planned 的方案否決（VETO）：這就是重置。
  - **代價**：engine 的 `planned_batch_shares` 用 `batch_no < batches_per_target` 判斷末批（`engine.py:208`），第 4～6 批會被誤算成末批。要支援新一輪就得改 engine 這個函式，屬規則語意變更，要送風控。另一個選擇是 v1 明確拒絕（不會靜默無效），由 CEO 選。
- **Q-T4 互斥**：**不建議照 FR-22 字面做「執行中就拒絕」**。
  - 讀碼確認，TOTAL_DEPLOY 只等於（現金加持股市值）乘以投入比例（`service.py:1834-1871`），和名單無關。名單寫入與 REBALANCE、confirm-rules、`claim_and_settle` 寫的資料不重疊。
  - 所以機制定為三點：每次名單寫入只開一個 `BEGIN IMMEDIATE`；鎖內重新驗證；兩步確認的操作要比對預覽摘要。這樣結果就等於某一個循序執行。
  - 不設「執行中」標記，也不用行程內鎖。兩者先前都已否決過（N-197 分析的 F-c、F-d，ADR-0042 的 P6）。
  - FR-23 擔心的「批次改了、TOTAL_DEPLOY 沒改」這種半套狀態，結構上不存在。
  - AC-44 結構上成立，前提是名單寫入不改既有批次列與指令列。
- **Q-T7 / N-204 現況確認屬實**：
  - `build_market_snapshot` 有三個呼叫點（`service.py:417`、`:1840`、`:2185`），都沒有傳 `high_volatility`。
  - `symbol_states` 只 SELECT `symbol, paused, paused_since`（`store.py:971`），`SymbolState` 也沒有這個欄位（`models.py:242-253`）。
  - app 內沒有任何地方寫入這個欄位，engine 則已經實作 +20%（`engine.py:487`）。
  - 判定：這是**沒接上線的 bug，不是設計**。store 的模組說明本來就寫明這張表存放「高波動清單 membership」（`store.py:16`）。
  - **PRD 事實錯誤**：P3 比的是 **BIAS25（收盤對 25MA 的乖離）大於 15% 或 20%**（`engine.py:492`），不是報酬率。AC-34、AC-35 的「達 +16%」要改。
- **先後關係**：
  - 本單的 base 必須含 N-177a 與 N-195（R2）。
  - 如果採用 FR-21 的生效閘，本單相依於 N-197a，也就是要沿用 `TotalDeployStamp`。
  - 和 N-196、N-198 沒有邏輯相依，但建議排在第三包（N-196、N-197a、N-198）之後再合入。
- **是否碰到 store.py 的動帳路徑**：不碰動帳語句，但會碰 store.py。唯一的交集是共用的批次讀取 helper（`_BATCH_SELECT`／`_row_to_batch`），只做加法欄位。詳見第二節 F。

## 二、各部門回報

### tech-architect（唯讀）

#### A. 評估摘要
- 採用：
  - 標的層 `entry_stopped`；
  - 單調遞增的 `batch_no` 加 `batch_round`；
  - 名單寫入用單一寫鎖交易，加上預覽摘要比對；
  - 生效閘用 TOTAL_DEPLOY 戳記的不等式（如果保留 FR-21）；
  - 高波動在 `evaluate_today` 接線；
  - 稽核表只增不改。
- 否決：新批次狀態；共用 `paused`；主鍵加輪次；重置舊批次；以 `INSERT OR IGNORE` 或 `INSERT OR REPLACE` 建新批次；執行中標記；行程內鎖；把 REBALANCE 和名單提交包成一個大交易。

#### B. 逐題

**Q-T1：停止新進場怎麼表達**

| 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|
| T1-A 新批次狀態（例如 `stopped`） | 狀態一眼可見 | 停止前已產生的 R1 會被 G1 擋下（批次不再是 planned），違反 FR-10，而且會套上「可能多於帳冊所記」的錯誤字面；重新加入要改回 planned，等於重置；`BatchStatus` 要擴充，前端 union 與字面都要改 | 高 | **VETO** |
| T1-B 共用 `playbook_symbols.paused` | 零 schema 變更 | S1 站回 25MA 時會發 `resume_symbol`，清掉使用者的停止（`engine.py:1239-1255`、`store.py:1259-1260`），違反 FR-12 | 高 | **VETO** |
| T1-C 在記憶體中把停止併進 `paused` 或 `blacklisted` 再交給 engine | 不改 schema | 併進 `paused`：每天都會觸發 `resume_symbol` 加 `defer_reset` 副作用。併進 `blacklisted`：`every_symbol_evaluated` 永遠是 false（`engine.py:1277-1282`），「規則已全數評估」再也不會出現 | 中 | 否決 |
| **T1-D `playbook_symbols` 加 `entry_stopped`（加 `entry_stopped_on`），service 從 engine 輸入剔除該檔 planned 批次** | 批次列與指令列零變動；`set_paused` 的 ON CONFLICT 只更新 paused 兩欄（`store.py:992-994`），不會互相覆蓋；engine 零 diff；停止期間不累計 M1 順延與 R3 跳過計數 | engine 輸入與帳冊顯示用的批次清單不同，要有單一定義；`evaluation_marks` 必須收同一份過濾後的輸入（它的契約是「engine 收到的東西」，`service.py:545`） | 低 | **採用** |

- 細節：
  - 已停止的標的若沒有 open 批次，整檔不交給 engine，也就不會出資料缺漏警示。
  - 日線載入範圍維持不變，仍是所有批次的 symbol（`service.py:2159`）。載入範圍會影響 `build_calendar` 與 `data_date`，v1 不動。
- 並發：停止若在某次評估讀取之後才 commit，那次評估仍會寫出 R1。這等於「先評估、後停止」，依 FR-10 照常結算並揭露，不需要動 ADR-0035 擁有的 `commit_evaluation`。
- 需要 ADR：是，ADR-0043 D2。
- PRD 修改：
  - FR-12、AC-13 改成「與 S1 排程暫停（站回 25MA 自動恢復）、S2 黑名單（60 交易日到期）都互相獨立」；
  - 補一句：停止期間該檔 planned 批次不累計順延與 missed 計數。

**Q-T2：生效順序**
- 方案：
  - (a) **戳記閘（建議，如果 CEO 保留 FR-21）**：
    - 新批次 INSERT 時，記錄鎖內讀到的 TOTAL_DEPLOY 三個鍵的原始字串，也就是 N-197a 的 `TotalDeployStamp`，存在新批次列的 `entry_gate` 欄。
    - 評估時如果目前的戳記仍等於記錄值，該批就不交給 engine。
    - REBALANCE 與 confirm 都零 diff。只比對字串是否相等，不比時間先後，比照 ADR-0035 補充五「不用時間戳」的先例。
  - (b) 不設閘，新標的立即生效。最簡單；每批金額是 TD ÷ n_targets ÷ 批數，和換了哪幾檔無關，所以財務上一致。
  - (c) 名單提交和 REBALANCE 合成一個 API、一個交易：否決。REBALANCE 有數秒的日線載入，鎖內不得有網路；也會推翻 N-196、N-197a 的契約。
- REBALANCE 失敗、被 `REBALANCE_BLOCKED` 或 `REBALANCE_SUPERSEDED` 擋下時：已提交的名單**保留，待生效**，重跑 REBALANCE 就解開。不設「整筆作廢」，因為作廢需要補償寫入或 DELETE。
- 閘為什麼要放在批次列上，不放在 `playbook_symbols`：`evaluate_today` 讀批次（`:2199`）和讀 symbol_states（`:2208`）分屬兩個連線。閘若放在標的層，會出現「讀到新批次、卻沒讀到閘」的偏斜，新標的會在 REBALANCE 之前就出 R1。放在批次列上，同一次讀取就能自洽，也不必把 `evaluate_today` 改成單一讀交易（那會觸發 ADR-0041 R-4′ 的回風控條款）。
- 需要 ADR：採 (a) 時納入 ADR-0043 D6。
- PRD 修改：FR-21、AC-25 寫明順序是「先提交，再 REBALANCE」；反過來做的話新標的會待生效，再跑一次 REBALANCE 即可。FR-1 要顯示「待生效」。

**Q-T3：重新加入已 closed 的標的**

| 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|
| 主鍵改為 `(symbol, round, batch_no)` | 語意直觀 | SQLite 改主鍵要重建表；指令列沒有 round，K1、G1、claim、settle 的 `WHERE symbol=? AND batch_no=?` 全部會有歧義；違反 ADR-0035 補充六的「G1 SQL 零 diff」與 N198-C2 | 高 | **VETO** |
| 把舊批次改回 planned | 零 schema 變更 | 直接違反「永不重置」；舊的永久 pending R1 會被 G1 放行，成交到重置後的批次，重複買進 | 高 | **VETO** |
| 用 `INSERT OR IGNORE`（`ensure_batches`）建新批次 | 現成 | 就是風險 5 的靜默無效 | 高 | **VETO** |
| service 層把 `batch_no` 重新編號後交給 engine | engine 零 diff | 每個 directive 與 effect 都要反向對映；rule_summary 的「第 N 批」會和帳冊不一致 | 中高 | 否決 |
| **單調 `batch_no` 加 `batch_round` 欄** | 主鍵、G1、K1、指令列全部不變；「每個 (symbol, batch_no) 一生最多一筆 executed R1」比現在更強；舊輪殘留的 pending buy 被 G1 擋下（舊批次是 closed），不會成交到新輪 | engine 的 `planned_batch_shares` 要改成「輪內序位、末批是輪內最後一批」，service 只把每檔最新一輪交給 engine；rule_summary 會顯示「第 4 批」 | 中 | **建議（若 v1 要支援）** |
| v1 明確拒絕（「此標的已無待進場批次，本版不支援開新一輪」） | 零 schema、零 engine 改動；風險 5 以明確拒絕關閉 | FR-16 延後 | 低 | 可選 |

- 「永不重置」的保證：
  - 既有批次列在名單路徑上零 UPDATE；
  - 新批次只能以未用過的 `batch_no` 一般 INSERT，衝突就 raise；
  - 前置條件「舊輪全部 closed 或 skipped」在鎖內判定。closed 與 skipped 都是終態，所以舊輪之後永遠不會再變動。
- 需要 ADR：是，ADR-0043 D3。若要改 engine，ADR 要明寫 ADR-0034 C-B11「R、S、P 引擎邏輯不改」屬 N-168 的範圍約束（比照 ADR-0035 補充六的先例），並送風控。
- PRD 修改：補上案例矩陣。
  - (i) 有 planned：解除停止；
  - (ii) **有 open、沒有 planned**：解除停止後不會再買。PRD 目前漏掉這一格，必須揭露；
  - (iii) 全部 closed 或 skipped：開新一輪，或依 CEO 的選擇拒絕。
  - 另外，企劃寫的是「每檔3批輪動」（`work/stock-desk-快市排程-企劃.md:271`），而季度提交時「保留、但三批已用完」的標的也會遇到同樣問題。這交 CEO 決定。

**Q-T4：互斥機制**

| 方案 | 判定 | 理由 |
|---|---|---|
| **M-a 單一寫鎖交易，加鎖內重驗，加預覽摘要比對** | **採用** | 跨執行緒、也跨行程（backend 與 scheduler）有效；SQL trace 可以檢查 |
| M-b 在 `playbook_state` 放執行中標記或 lease | 否決 | 當機時標記會殘留；要改 REBALANCE 與 confirm，會推翻 N-196、N-197a 的契約（同 F-c） |
| M-c `threading.Lock` | 否決 | 只在單一行程內有效（ADR-0041 R-β、ADR-0042 P6） |
| M-d 用一個大交易包住 REBALANCE 或 confirm 的整個流程 | 否決 | 鎖內會有網路 I/O（N172-C2） |
| M-e 檔案鎖 | 否決 | 依平台而異，SQL trace 看不到 |

交錯分析（讀碼推論，未實跑）：

| 並發的兩方 | 兩邊寫入的資料 | 結果 |
|---|---|---|
| 名單 × REBALANCE | REBALANCE 只讀 open 批次與現金（`:1836-1853`）；名單不建 open、不寫現金與 TD | 交換律成立，兩種循序的結果相同 |
| 名單 × confirm | confirm 寫 params（首次確認寫的是系統預設的複本）與資金；名單只讀 n_targets | 等於某一個循序。FR-24 的檢查若在名單改變之前讀到，等於「先 confirm、後改名單」 |
| 名單 × `claim_and_settle` | settle 寫批次狀態與股數、現金、指令列、schedule；名單寫 `playbook_symbols`、新的 `batch_no` 列、稽核表 | 寫入不相交。前置條件由寫鎖序列化。N-198 之前的 F2 窗口仍在，但和名單無關 |
| 名單 × `evaluate_today` | 評估在鎖外讀取 | 等於「先評估、後寫名單」，或者相反。輪次與閘都放在批次列上，避免讀取偏斜 |
| 名單 × 名單 | — | 寫鎖序列化，加鎖內重驗與摘要比對 |
| REBALANCE × confirm | — | 由 N-197a 處理（本單不動） |

- FR-23、FR-25 都能保證，前提是第二節 D 的 C1～C6 成立。
- 需要 ADR：是，ADR-0043 D4、D5。
- PRD 修改：
  - FR-22、AC-26～AC-29 改寫為結果導向：「結果等同某一個循序執行；確認前若名單或預覽內容已改變，就拒絕並零寫入」。
  - 刪掉「執行中就拒絕」與「被哪一項擋下」的訊息需求。

**Q-T5**：同意 FR-10。依據是 N172-C11、ADR-0035 的 S-α、R10，以及 CEO #79 選的 B-2a（保留並揭露、不撤回）。改寫指令列或新增撤回狀態都會被否決（VETO）。不需要新 ADR。

**Q-T6**：v1 只揭露，不補列、不刪列，engine 不改。
- 讀碼推論：
  - 參數從 3 改成 2：第 2 批變成末批，會吸收整檔餘額，第 3 批大約只剩 1 股；
  - 從 3 改成 4：只會投入大約 3/4。
  - 兩種情況都沒有超過整檔配額太多（最多多 1 股）。
- 根本處理屬於「改 `batches_per_target`」那張另案：要嘛在既有輪次有未終結批次時拒絕變更，要嘛只套用到新輪次（要搭配 Q-T3 的 engine 改動）。那張另案要有自己的 ADR。本單不需要。

**Q-T7：高波動接線**
- 存放位置直接用 `playbook_symbols.high_volatility`。
- 接線：
  - `symbol_states` 加讀這一欄，`SymbolState` 加一個加法欄位。
  - `evaluate_today` 在建 snapshot（`:2183-2194`）**之前**讀一次 `symbol_states`。同一份結果同時傳給 `build_market_snapshot(high_volatility=...)` 和 engine（現在 `:2208` 的讀取點要往前移）。
  - `:417`（出清）與 `:1840`（REBALANCE）不傳，因為它們不評估 P3。
- 寫入：新增一個 store 方法，只 upsert `high_volatility`，並在同一交易內寫稽核。
- 要不要走 `request_rule_change`：不建議。那個流程沒有 API；把清單放進 `RuleParams` 會牽動規則集確認、版本與字面。但鐵律④（改規則要收盤後書面、次日生效）的精神適用，生效時點交 CEO 選。
- 接線本身對既有 DB 零行為變更（欄位全是 0），**除非 CEO 曾手動寫過 1**。部署前要用唯讀方式盤點。
- 需要 ADR：納入 ADR-0043 D7，不另立。
- PRD 修改：FR-30、FR-32、AC-34、AC-35 改成「P3 過熱減碼：BIAS25 大於 15%（高波動大於 20%），而且冷卻期已過、剩餘股數 ÷ 3 大於 0」。

**Q-T8：代號驗證**
- 流程：
  - 在鎖外，走評估用的同一條路：`load_bars(..., market=PLAYBOOK_MARKET)`（`service.py:1472`），其中含 ADR-0024 的 `admit_symbol`。
  - 另外在名單模組內加一條台股形狀規則。草案是「4～6 位數字，可帶一個大寫英文字母字尾」。確切規則由 data-engineer 對照 TWSE、TPEx 的代號空間查證，並保留 `00631L` 這類合法字尾。
  - 不自動正規化（`2330.TW` 直接拒絕）。
- 失敗要分兩類：
  - 確定性失敗（形狀錯、`symbol_not_admitted`）：拒絕。
  - 暫時性失敗（逾時、來源錯誤）：以「暫時無法確認，可重試」拒絕，不陳述為「取不到日線」。
  - 兩類都零寫入。
- 「零寫入」的範圍是名單相關的資料表。資料層快取可能會留下日線，PRD 要寫明。
- 不需要新 ADR。形狀規則不放進 ADR-0024 的資料層准入，因為放進去會影響持倉。

**Q-T9：季度窗口**
- 先例衝突：REBALANCE 的 docstring 明寫「manual by design……engine has no calendar of quarters」（`service.py:1817-1819`）。引入季度窗口是新概念，要寫進 ADR-0043 D8。
- 若採日曆窗口：
  - 寫成單一定義的純函式；
  - 在 API 層與寫鎖內都強制；
  - 以 Asia/Taipei 日期判定。現在 `as_of` 用的是 UTC 日期（`service.py:2149`），台北 00:00～08:00 之間會差一天；
  - 已知限制：`TradingCalendar` 在已知 bar 範圍之外，會退回只看是否為週一到週五（`calendar.py:39`、`:85`）。
- 精確邊界由 CEO 回答 Q-C1。

**Q-T10**：系統不得自動停止任何標的。
- 建議在「改 `n_targets`」那張另案的請求端，就拒絕「新值小於目前啟用檔數」。
- 萬一已經發生（例如既有資料），至少要揭露，並讓 confirm-rules 拒絕（FR-24）。要不要再加「全體 R 系列 fail-closed」，交 CEO 選。
- 本單不需要 ADR。

#### C. ADR-0043 草案要點

暫定標題：「ADR-0043（proposed）：stock-desk 排程台標的名單的表達、批次輪次與名單寫入交易（補充 ADR-0035、ADR-0041、ADR-0042，不取代）」。下一個編號是 0043；0036 保留給在途單生命週期，目前沒有檔案。

- **Context**：
  - N203 查證；
  - ADR-0035 的不變式；
  - ADR-0041「結算以外的批次寫入者只能欄位化寫入」；
  - ADR-0042「唯一的結算進入點是 `claim_and_settle`」。
- **Decision**：
  - **D1**：名單是 `playbook_batches` 裡的 distinct symbol，作為單一真實來源，不另立名單表。「啟用」是名單內且 `entry_stopped=0`。S1 暫停、S2 黑名單、待生效中的標的仍算啟用（占名額，名額不補）。
  - **D2**：停止新進場依 T1-D。
  - **D3**：批次身分維持 `(symbol, batch_no)` 主鍵。新批次一律以 max+1 起的 `batch_no` 一般 INSERT。加法欄位 `batch_round`（既有列預設 1）。engine 只收每檔最新一輪。若 CEO 選 v1 拒絕，本條只保留身分規則。
  - **D4**：每次名單寫入是一個連線、一個 `BEGIN IMMEDIATE`：
    - 鎖內重讀並驗證：啟用檔數不大於 n_targets、前置條件、窗口、預覽摘要是否一致；
    - 寫入：`playbook_symbols` 的欄位、新批次列、稽核；
    - 鎖內零網路；
    - 錯誤處理照 C-11。
  - **D5**：互斥語意與交錯表，見 Q-T4。
  - **D6**：戳記閘（如果採用）。新列加 `entry_gate` 欄，只在 INSERT 時寫一次，之後不更新。
  - **D7**：高波動接線點與生效時點。
  - **D8**：季度窗口的純函式與時區。
  - **D9**：稽核表 `playbook_roster_log`，id 用 AUTOINCREMENT，只 INSERT；FR-20 的書面紀錄就是其中的提交事件。可選的縱深防禦：用 SQLite trigger 擋 UPDATE 與 DELETE。
- **Consequences**：
  - 好處：關閉 N203 的 8 點風險；REBALANCE、confirm 與結算路徑零 diff。
  - 壞處：
    - engine 輸入與帳冊清單分開，要守住單一定義；
    - 「第 4 批」這類字面要經風控；
    - 並發評估仍可能為剛停止的標的出一張 R1（依 FR-10 揭露）；
    - 戳記閘有 ABA 殘留，和 N-197a 相同；
    - 若改 engine，就是規則語意變更。
- **與其他 ADR 的關係**：
  - ADR-0035 不變式加強為「新批次只用未用過的 batch_no」；
  - ADR-0041 新增一種批次寫入者：INSERT 新列，`shares=0`，不屬於動帳；
  - ADR-0042 本單不新增任何 claim 或動帳呼叫點。

#### D. 對實作的約束（qa-reviewer 逐條檢查）
- **N207-C1**：
  - `app/` 內沒有 `DELETE FROM playbook_batches`；
  - 沒有 `INSERT OR IGNORE` 或 `INSERT OR REPLACE INTO playbook_batches`；
  - `ensure_batches` 在 `app/` 內沒有呼叫點；
  - 名單模組對 `playbook_batches` 零 UPDATE（AST 加 SQL trace 判定）。
- **N207-C2**：名單路徑不 INSERT、UPDATE 或 DELETE `playbook_directives`。
- **N207-C3**：名單路徑不寫 `STATE_CASH` 與 TOTAL_DEPLOY 三鍵（N197a-C6 不受影響）。
- **N207-C4**：以下零 diff，名單路徑也不呼叫它們：
  - `claim_and_settle`、`settle`、`_settle_*`、`_add_cash`；
  - `commit_evaluation`、`commit_emergency_exit`；
  - `set_capital`、`set_total_deploy`、`read_rebalance_inputs`、`rebalance()`；
  - `BATCH_LEFT_PLANNED_SQL`、`_CLAIM_SQL`、`_insert_directives`。
- **N207-C5**：交易邊界照 D4；SQL trace 只有一個 `BEGIN IMMEDIATE`；鎖內沒有 resolver、沒有網路。
- **N207-C6**：`set_paused`、`blacklist`、`apply_effects` 不寫 `entry_stopped`、`high_volatility`；名單路徑不寫 `paused`、`paused_since`、`playbook_blacklist`。
- **N207-C7**：`engine.py` 零 diff。CEO 若選支援新一輪，只准改 `planned_batch_shares` 一個函式，並附差分測試：單輪的既有資料逐值相同，至少 300 組 seed。
- **N207-C8**：「engine 輸入批次」只由 service 內單一函式產生；`evaluation_marks` 與 `evaluate` 收同一個物件。
- **N207-C9**：`high_volatility` 只在 `evaluate_today` 傳入，值取自同一次 `symbol_states` 讀取，而且這次讀取在建 snapshot 之前。
- **N207-C10**：稽核表在 `app/` 內只有 INSERT。
- **N207-C11**：確認型操作（停止、季度提交）在鎖內重算摘要，和預覽比對；不一致就拒絕、零寫入。
- **N207-C12**：代號驗證在鎖外，照 Q-T8；暫時性失敗與確定性失敗分開回報；不正規化。
- **N207-C13**：窗口判定只有一份定義，用 Asia/Taipei 日期，以注入時鐘測試。
- **N207-C14**：回應與 schema 不含 recommend、score、rank、candidate、suggest；名單依代號升冪排序（FR-2 擇此）。
- **N207-C15**：
  - base 含 N-177a 與 N-195；採戳記閘時也要含 N-197a；
  - 以 merge commit 合入，合入前 merge 最新 product；
  - schema 釘住測試（`tests/test_playbook_exit_idempotency.py:738`）的修改要逐條列給 qa 判定。
- **N207-C16**：新字面只放 `wording.py`；風控逐字定稿之前不得合併。

#### E. 和 N-196、N-197a、N-198 的先後
- N-196、N-198：沒有邏輯相依。本單不碰 `rebalance` 與結算。
- N-197a：
  - 採戳記閘時，本單相依於它的 `TotalDeployStamp`（單一定義）。
  - FR-24 要改 `confirm_rules`，而 N197a-C5 規定 N-197a 對 `confirm_rules` 零 diff。所以本單無論如何都排在 N-197a 合入之後。
- N-198：
  - 本單要在批次讀取 helper 加欄位，會影響 N198-T5 的差分基準。
  - N-198 有第三包的期限，本單不應該占掉它的開發排程。
  - 建議 N-198 先合入。
- 建議順序：R2（N-177a、N-195）→ N-196 → N-197a → N-177b → N-198 → N-207。ADR、spec 與風控字面現在就可以並行進行。

#### F. 是否碰到 store.py 的動帳路徑
- **不碰動帳語句。**
- 會改的 store.py 部分：
  - `_SCHEMA`、`_MIGRATIONS`（加法欄位、新稽核表）；
  - `symbol_states`；
  - 新的名單寫入方法；
  - `_BATCH_SELECT`、`_row_to_batch`、`BatchState` 加 `batch_round`、`entry_gate`。
- 最後一項是結算鎖內讀取也會用到的共用 helper，要求只做加法；由 N198-T5 與 ADR-0041 的 C18／T27 守住。
- 新增的 INSERT 寫的是 `shares=0` 的 planned 新列，不改股數也不改現金，在 ADR-0043 裡登錄為允許的寫入者。

### 其他部門
本輪沒有參與。

## 三、驗證
- 讀過的文件：
  - PRD `/home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md`（全文）；
  - `/home/user/AICompany/work/reviews/2026-11-08-N203排程台標的寫入路徑查證-dev-lead.md`（全文）；
  - `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`（全文）；
  - ADR-0035、ADR-0042（全文）；
  - ADR-0041「被約束」與 Decision 5（grep）；
  - ADR-0034 C-B11、ADR-0024 准入（grep）；
  - 企劃 `:262-291`；
  - 追蹤清單中 N-169～N-207 各列。
- 讀過的程式（只讀、未執行；主 checkout，N-177a 尚未合入，行號會漂移）：
  - `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`：`:60-190`、`:836-1055`、`:1240-1280`；
  - `/home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py`：`:170-229`、`:436-495`、`:690-810`、`:1180-1309`；
  - `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`：`:140-184`、`:395-434`、`:536-566`、`:1468-1517`、`:1809-1888`、`:1987-2076`、`:2123-2232`；
  - `/home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py`（grep 與 `:240-259`）；
  - `/home/user/AICompany/apps/stock-desk/backend/app/data/admission.py`：`:95-154`；
  - `/home/user/AICompany/apps/stock-desk/backend/app/data/calendar.py`（grep）。
- grep 查證：
  - `high_volatility`、`build_market_snapshot(` 的全部出現位置；
  - `playbook_symbols`（含測試的 schema 釘住）；
  - `pause_symbol`、`blacklisted`。
- 未查證：
  - 交錯分析都是讀碼推論；
  - N-177a、N-197a 合入後的實際行號與 helper 名稱；
  - 台股代號的完整形狀空間；
  - Windows 上 `datetime.now` 的解析度（影響戳記的 ABA）。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案，也沒有執行任何指令。

## 四、下一步
1. **CEO**：回答下方的架構取捨，以及 PRD 的 Q-C1～Q-C9。另外有一題新增：「保留、但三批已用完」的標的，季度提交時要不要開新一輪（關係到「每檔3批輪動」的解讀）。
2. **product-manager**：依第二節各題的「PRD 修改」改版，重點如下：
   - FR-12、AC-13 改 S1／S2；
   - AC-34、AC-35 改 BIAS25；
   - FR-22～FR-24 改寫為結果導向；FR-24 引用的「FR-25」應為 FR-26；
   - FR-26 分成「啟用檔數」與「今日可進場檔數」兩個數字；
   - 補上重新加入的案例矩陣；
   - 寫明零寫入的範圍；
   - 寫明窗口的時區；
   - 寫明 EMERGENCY 凍結期間名單變更是否允許。
3. **tech-architect**：CEO 回覆之後，出 ADR-0043 正式草案與 N-207 的實作規格（C1～C16、測試清單），送風控。
4. **devops-sre／data-engineer**：部署前準備唯讀盤點（比照 N-199 的作法），由 CEO 在本機執行，盤點以下各項：
   - 實際檔數對 n_targets；
   - 每檔批數對 batches_per_target；
   - `high_volatility=1` 的列數；
   - `batch_no` 是否有斷號。
5. **risk-compliance-officer**：審 PRD 附錄列的 10 句字面，加上「第 4 批」或輪次的呈現、待生效的揭露，以及（如果採用）engine 改動。
6. **coordinator**：在追蹤清單登錄 N-207 的先後（排在 N-198 之後），並把 N-204 判定為「沒接上線的 bug」、併入 N-207。

## 需要 CEO 決定的架構取捨
1. **重新加入已出清的標的（Q-T3）**
   - (A) v1 就支援新一輪：單調 `batch_no` 加 `batch_round`，engine 的 `planned_batch_shares` 改成輪內計算，要送風控。
   - (B) v1 明確拒絕，FR-16 延後。批次身分規則仍先寫進 ADR。**TA 建議 (B) 先上線，(A) 另開子單。** 如果「每檔3批輪動」的意思是會循環使用批次，就改選 (A)。
2. **新標的生效閘（Q-T2／FR-21）**
   - (A) 保留：用戳記閘，任何一次 TOTAL_DEPLOY 寫入（REBALANCE 或 confirm）都會打開，相依於 N-197a。
   - (A′) 同 (A)，但只有 REBALANCE 寫入才打開。
   - (B) 取消，立即生效。**TA 建議 (A)。**
3. **季度窗口（Q-T9）**
   - (A) 日曆窗口，API 層強制，有週一到週五退回判定的已知限制。
   - (B) 比照 REBALANCE 的「manual by design」，由使用者宣告換季、留下稽核，系統不判斷日曆。**TA 中立，傾向 (A)，因為 PM 要求在 API 層強制。**
4. **高波動標記的生效時點（Q-T7）**
   - (A) 下一次評估就生效。
   - (B) 下一個交易日生效（鐵律④的精神），要多一欄生效日。
   - (C) 只能在季度窗口內變更。**TA 建議 (B)。**
5. **n_targets 被調到低於啟用檔數（Q-T10）**
   - (A) 在調參數的另案請求端拒絕，加上揭露。
   - (B) (A) 再加上「全體 R 系列 fail-closed」。
   - (C) 只揭露。**TA 建議 (A)。**
6. **互斥語意（Q-T4）**：是否同意把 FR-22 從「執行中就拒絕」改成「結果等同循序執行；確認前內容已變就拒絕」。**TA 建議同意。** 不同意的話，就要另建執行中標記，那會推翻 N-196、N-197a 的契約。
7. **排程**
   - (A) N-207 排在第三包（N-196、N-197a、N-198）之後。
   - (B) 提前，但只能先上不依賴 N-197a 的部分（例如高波動的接線與寫入）。**TA 建議 (A)。**

相關檔案：
- `/home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md`
- `/home/user/AICompany/work/reviews/2026-11-08-N203排程台標的寫入路徑查證-dev-lead.md`
- `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂四與N197分析-tech-architect.md`
- `/home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md`
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md`
- `/home/user/AICompany/docs/adr/0042-stock-desk-排程台結算的claim與動帳併入同一寫鎖交易.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/data/admission.py`

# ADR-0039：stock-desk `/today` 常駐揭露待執行與近期已結算的出清指令（補充 ADR-0033，不取代）

- 狀態：accepted（CEO #104，2026-11-04 核可；v2 本文加檔末「補充一」；群組 B 另受風控 B 閘門約束）
- 日期：2026-11-03（v2：納入風控 2026-11-03 N-171 字面裁示與 P-1～P-8 答覆）
- 補充一（tech-architect 2026-11-04，回應 `work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md`）：A-15 欄位與同列順序、A-6 謂詞、N171-C17 的形狀、P-5(c) 殘留、群組 B 讀取下界（撤回 `LOOKBACK_DAYS` 日曆日下界）、authorship 單調性前提（C21），以及 Decision 11、13、16 與「待決」的狀態更新，以本檔末「補充一」節為準；v2 本文不改。轉 accepted 時可由 tech-writer 機械合併為 v3，語意不變。
- 決策者：
- tech-architect（草案）
- CEO #98～#101（範圍）、CEO #102（並行，見 ADR-0035 補充四）
- risk-compliance-officer：群組 A 字面 A-1～A-14 為條件式定稿；群組 B 字面 B-1～B-4 為草擬，另有閘門
- 出處：`work/reviews/2026-11-03-N171字面與NB6回審-風控.md`
- 與既有 ADR 的關係：
- ADR-0033：補充，不取代，原文不改。C-4（判準 Z 收窄版）是謂詞來源；C-7 不變。
- ADR-0034 補充一：引用 S-3、S-4。Decision 9 依風控 F-11 修正 S-3 第 5 點的套用範圍。
- ADR-0035 補充四：依其切面實作。只改 N-171 擁有的部分，不改固定項。
- ADR-0037：區塊不讀、也不寫 receipt store。
- ADR-0036：保留給 N-172b／N-176，本 ADR 不涉入。
- 來源（`work/` 下）：
- PRD `prd/2026-11-01-待執行出清指令常駐揭露-N171.md` v0.1
- [TA-4xx] `reviews/2026-10-31-4xx重複列N171N174評估-tech-architect.md`
- [TA-P1] `reviews/2026-11-01-ADR0034補充一-tech-architect.md`
- [風控 N171] `reviews/2026-11-03-N171字面與NB6回審-風控.md`
- 決策包 #98～#102
- 程式位置為 2026-11-03 工作樹 `product/stock-desk` 的快照，以內容定位。全部為讀碼判定，未執行。
- 字面規則：本檔只寫識別名，逐字以 [風控 N171] 為準。

## Context（背景）

1. 問題：
 - 出清指令只存在於那一次回應裡。重新整理、關分頁、離開頁面、500 之後就看不到（問題 1）。
 - 結算後才重送會走 EMPTY，造成誤導（問題 2）。
 - R10 殘留：風控書面接受，延續到群組 B 上線為止（[風控 N171] 給 CEO 的知悉項）。
2. 現況（讀碼）：
 - 覆蓋判定：`service.py:237-261` `exit_line_still_covers`。
 - 候選列與 open 批次：`store.py:1203-1220` `_read_exit_state`。
 - 逐批判定：`plan_emergency_exit`（`service.py:298-401`）。
 - 結算：只為已到期列載入日線（`:628`、`:638`），並用同一份序列判 N1（`:694`、`:761-821`）。
 - unauthored 路徑：不結算、不載入、不寫入（`:1048-1119`）。
 - `POST /settle`：沒有 authorship 閘門（`api/playbook.py:449-457`）。
 - 凍結只停 R 系列，S/P 每天照常評估（`engine.py:1164-1165`）。
 - 已結算列有 `settled_at`、`settled_open_price`；EMERGENCY 一律判 executed（`engine.py:1338-1339`）。
 - `settle()` 用 min／max 移動股數（`store.py:1345-1351`），不記錄實際移動了多少股。
 - `TodayResponse.as_of` 是 API 層的時間戳（`api/playbook.py:413`）。
3. 對 PM 指出的三點，tech-architect 的判定：
 - (1) N171-C2 已過時：確認。
 - (2) unauthored 以空序列判定會全部判為涵蓋：確認。v2 改為 unauthored 完全不分類。
 - (3) 群組 A 解不了「結算後重送走 EMPTY」：確認，由群組 B 處理。
4. 限制：R10、R16、EX-2、EX-5；ADR-0033 C-3、C-9、C-10；GET /today 不新增寫入；題 9 零痕跡；ADR-0037 的 FE-C2、VETO-1、VETO-3、VETO-5；風控 P-1～P-8。

## Options（選項比較）

### 一、群組 A 的 API 形狀
| 方案 | 結論 |
|---|---|
| (a) 單一清單，只列仍涵蓋的列 | 不採。違反 CEO #100 |
| (b) 在 `DirectiveLine` 加分類欄位 | 不採。分類語意會外溢到帳冊 |
| (c) 依類別分三個逐列清單（v1） | 撤回。風控 F-8(1) 選了「一批一行」 |
| (d) 後端組好的區塊／小節／行結構，每行帶類別與同批是否另有仍涵蓋的列 | **採用**：符合 P-2、F-8(1)、固定組合順序 |

### 二、判準 Z 用哪一份日線（P-1）
| 方案 | 結論 |
|---|---|
| (i) 另寫 `settled=0` 謂詞 | **VETO** |
| (ii) 用 `evaluate_today` 的第二次載入 | 不採：和 N1 用的不是同一份序列 |
| (iii) 用結算本身的序列（`_settle_pending`） | **採用** |
| (iv) unauthored 路徑也載入日線 | **VETO**（題 9、P-3） |

### 三、unauthored 路徑（P-3）
| 方案 | 結論 |
|---|---|
| (u1) 用空序列判定 | **VETO** |
| (u2) 全部不分類 | **採用**（P-3） |
| (u3) 不需日線就能判定的部分照判 | 撤回：這就是「不載入日線也能分類」，會讓 A-4、A-13 退回重審 |
| (u4) 不揭露 | 否決（CEO #99） |

### 四、群組 B（P-7）
| 方案 | 結論 |
|---|---|
| (B-α) 讀取時計算，保留期內列出 | **採用** |
| (B-β) 後端存「關閉」狀態 | 否決（CEO #101） |
| (B-γ) 只做 EMPTY 附加句 | 不採為主要方案；B-4 依風控定為 required |
| (B-δ) 併入群組 A | **VETO** |
| 認定「實際減少股數的列」：重放日誌 | **採用**（純函式、不寫入） |
| 認定方式：在 `settle()` 新增欄位記錄移動股數 | 不採：要改 `settle()`（與 N-168 C-B6 衝突）；舊資料仍得重放，等於兩個來源 |

## Decision（決策）

1. 欄位：皆為加法、預設空；`PlaybookEvaluation` 同義；`types.ts` 同步，欄位標為 optional，缺鍵視為空。
 - `pending_exit_directives: list[DirectiveLine]`（切面已定義）：群組 A 全部的列，三類都含。依 symbol、batch_no、execution_date、id 遞增排序，經 `_lines` 建立。這是原始資料，前端不拿它來渲染文字。
 - `pending_exit_block: PendingExitBlock | None`：沒有任何一行時為 None。前端只在 `today.isSuccess` 且此欄非 None 時渲染。
   - `title`：A-1。
   - `lead_template`：A-2，保留字面的 `{read_at}`（Decision 16 的 P-8）。
   - `sections: list[PendingExitSection]`：依固定順序排列。
   - `closing_notes: list[str]`：authored 為 [A-14]；unauthored 為 [A-13, A-14]。
 - `PendingExitSection`：
   - `kind`：covering／stale／unclassified。
   - `label`：A-7、A-8 或 None。
   - `lead`：A-3、A-9 或 A-4。
   - `rows: list[PendingExitRow]`。
 - `PendingExitRow`：
   - `symbol`、`batch_no`。
   - `shares`：批次的 `remaining_shares`。
   - `coverage`、`batch_has_covering`（P-2）。
   - `execution_dates: list[str]`。
   - `text`：A-5，或 `EMERGENCY_EXIT_STALE_ITEM`。
   - `notes: list[str]`：同列的附註，包括 A-6、A-11 或 A-12。
   - `entry_before_exit_note: str | None`：W-B2L，見 Decision 9。
 - 群組 B 另有閘門，加 `settled_exit_block: SettledExitBlock | None`：
   - `title`：B-1。
   - `lead`：B-2，其中 `{retention_days}` 由常數渲染。
   - `rows`：每列含 `symbol`、`batch_no`、`shares`、`execution_date`、`open_price`、`settled_on`、`text`（B-3）、`entry_before_exit_note`、`directive`。
2. 候選列與 open 批次：
 - N-171 的 `_read_pending_exits(conn)` 呼叫 `_read_exit_state(conn)`。
 - 不得另寫 EMERGENCY 候選列的 SQL。
 - 只收屬於 `open_batches` 的列（P-5(a)）。
 - 不含 buy 列，不含已結算列。
3. 分類（P-1、P-3）：
 - 從 `plan_emergency_exit` 抽出純函式 `classify_exit_batches(state, series_for) -> list[ExitBatchClass]`。
   - 每個 open 批次一筆：`batch`、仍涵蓋的列 `live`、已不涵蓋的列 `stale`。
   - 逐列只用 `exit_line_still_covers` 判定。
 - `plan_emergency_exit` 改為呼叫它，行為零差異。
 - authored：`series_for = run.loaded.get(symbol, NOTHING_LOADED).bars`，其中 `run` 是同一次 `/today` 的 `_settle_pending`。
 - unauthored：不呼叫它。各 open 批次上的列全部歸 unclassified。
4. 行（F-8(1)）：
 - 每個 (symbol, batch_no) 在每個類別中各一行，依 symbol、batch_no 遞增排序。
 - `shares` 取該批次在讀取點的 `remaining_shares`，與 S1／S2 的 `{pending_shares}` 同一定義（P-6）。
 - `execution_dates`／`stale_dates` 只取該類別的列，去重後遞增，ISO 格式；unauthored 取全部的列。
 - A-6：該行任一列 `execution_date < as_of` 時附上；判斷基準與 S3 相同（UTC 日期）。只用於 covering 行與 unclassified 行。
 - stale 行依 `batch_has_covering` 附 A-11 或 A-12。
5. 組合順序：照 [風控 N171] 第二節之 2 的固定順序，由後端組好；前端不重新排序，也不自行撰寫文字。
6. 讀取與一致性：
 - 資料出自切面的 `read_in_flight()`，與 N-168 的清單在同一次 read transaction 內。
 - 零寫入；N-171 不新增任何日線載入。
7. unauthored 路徑：照舊不結算、不載入、不寫入；不分類。
8. 不由 mode 或 `emergency_until` 推導；不含 buy 列。
9. W-B2L（風控 F-11，修正 ADR-0034 補充一 S-3 第 5 點）：
 - A 區塊三類的行、B 區塊的行，都要帶 W-B2L。
 - 一律取自該行底層列經 `_lines(..., labeled_batches=...)` 產生的 `entry_before_exit_note`。同一批次的列結果相同，取任一列即可。
 - 套用規則由 N-168 實作；不得把 W-B2L 拼進 `text`。
 - N-171 先合併的話，這個欄位永遠是 null，畫面上不留空位（AC-N171-21）。
10. 群組 B（P-7）：
 - 來源：在 `_read_pending_exits` 內，同一個 transaction 讀取：
   - `rule_id='EMERGENCY' AND action='sell' AND settled=1 AND status='executed' AND settled_at IS NOT NULL` 的列；
   - 下界取 `settled_at >= as_of − LOOKBACK_DAYS` 個日曆日；
   - 同時讀出這些批次的全部已成交賣出列與批次列。
 - 實際減少的股數：用純函式 `replay_exit_sell_moves(batch, sells)` 重算。
   - 依 `(settled_at, id)` 順序重放，邏輯與 `settle()` 的 min／max 相同；`batch_no` 為 NULL 的列不計（與 `settle()` 一致）。
   - 每批最多一列出清列的減少股數大於 0，B 只取這一列；N2 那類列被排除。
   - `{shares}` 預設取減少的股數，待風控確認。
 - 保留期：
   - 常數 `SETTLED_EXIT_RETENTION_TRADING_DAYS = 20`，放在 service，不放 `RuleParams`。
   - `settled_on` 取 `settled_at` 的 UTC 日期。
   - 列出條件：`as_of <= calendar.shift(settled_on, 20)`，判定寫在純函式 `settled_exit_retained`。
 - 日曆：
   - authored：用 `evaluate_today` 的 calendar。
   - 出清的 B-4：用出清自己的 calendar。
   - unauthored：用 `TradingCalendar(())`。
 - 不存狀態，沒有關閉機制。
 - B-4：在出清鎖內由 `_read_exit_state` 多讀一項，用同一組純函式判定；組合順序照 [風控 N171] 第二節之 6。
11. 分階段（CEO #98）：
 - A：
   - P-4、P-5 的退回項，風控重審通過；
   - A-1～A-14 逐字落地，NB-6 第 2 段原子替換；
   - 出清畫面包已合進 product 之後才做前端；
   - S-A～S-D 四張畫面附在 PR，經風控書面終核。
 - B1：A 合併之後；B 閘門（P-7 確認、B-1～B-3 核可）通過。
 - B2（B-4）：N-168 合併之後；B-4 核可。
 - 群組 B 任何程式碼在閘門通過前不得合進 product。
 - 結論：**可同包，不建議拆案**。
12. 與切面的關係：
 - N-171 只改 `PendingExitRead`、`_read_pending_exits`、`_pending_exit_lines` 與本 ADR 的加法欄位。
 - 不改 ADR-0035 補充四 S-3 的固定項。
 - 合併時依補充四的 S-5、S-6。
13. NB-6：
 - 第 2 段改為風控修訂版，守門測試斷言其中包含 `PENDING_EXIT_BLOCK_TITLE`；第 1 段、第 3 段不動，第 3 段即 `wording.py:541-546`。
 - 後端常數、前端鏡射、守門測試、字面絆線測試放在同一個 commit，並在 N-171 的 PR 內。
 - 舊的第 2 段在 grep 中為 0。
 - 群組 B 上線時再回審一次。
14. `directives` 排除 EMERGENCY（`_read_logged` 與 `UNKEYED_RULE_IDS`）：確認，並補端到端守門測試。
15. 約束與測試：見附錄 A、附錄 B。
16. 風控前提 P-1～P-8 答覆：
 - P-1 成立：見 Decision 3。
 - P-2 成立：見 Decision 1、4。
 - P-3 成立：v2 改為 unauthored 不分類。A-6 只比對日期、不算分類，請風控確認。
 - P-4 附條件：要加 N171-C17（unauthored 時 `POST /settle` 不結算），新字面 `SETTLEMENT_UNAUTHORED_NOTE` 由風控定。排程程序與前端都不會結算。
 - P-5：
   - (a) 只收 open 批次：成立。
   - (b) unauthored 不會有 closed 批次的未結算列：附條件成立。authorship 只會從 false 變 true，加上 C17 之後即成立；seed／手動改 DB 除外。
   - (c)「每天由 N1 揭露」只對判準 Z 下已不涵蓋的列成立：部分不成立，退回風控重審 F-8(2)(a) 與 A-2 的範圍。
 - P-6：定義成立。剩餘股數可能小於出清列的股數（資料落後時 S/P 先結算、F7），已回報風控。
 - P-7：附條件成立，見 Decision 10。`{shares}` 的口徑待風控確認。
 - P-8：附條件成立。`{read_at}` 由前端用 `formatDateTime(data.as_of)` 代入，恰好一次；與頁面「回應時間」同一個值、同一個格式函式。
17. warnings：
 - 群組 A／B 區塊不放進 `warnings`，`warnings` 零 diff。
 - N-168 W-B6 在 FROZEN_NOTE 之後的位置、N-172a 的錨點、`UNAUTHORED_HOLDING_NOTE` 都不受影響。

## Consequences（後果）

好處：
- 結算前與結算後 20 個交易日內，都有後端資料作為來源的常駐檢視。
- 分類結果與結算、出清一致（P-1）。
- 不新增狀態，也不新增寫入。

代價：
- 區塊結構由後端組好，欄位較複雜。
- 群組 B 要重算股數。
- `POST /settle` 多一個閘門與一句字面。

壞處與殘留：
- `/today` 失敗時看不到區塊。
- 群組 B 超過 20 個交易日後消失（沒有數據依據）。
- closed 批次上、仍算涵蓋的未結算列：不在 A；未到期時 `/today` 看不到（P-5(c)，待風控）。
- 剩餘股數可能小於出清列股數（P-6，根源在 F4／N-169）。
- 重算在 F2 並發窗口下可能和實際帳冊不一致。
- unauthored 路徑無法分類，日曆有偏差。
- 結算時載入失敗，會一律判為仍涵蓋（降級方向與出清相同）。
- 長期無法結算的列會一直留在區塊（F7／N-176、F6）。
- N-175 若改為在 unauthored 下結算，A-13 要回審。
- B2 要等 N-168 合併。

規模估計：
- A：後端 S～M（約 24 條測試），前端 M。
- B1：後端 S～M（含重算，約 10 條測試），前端 S。
- B2：S。

## 待決

- 風控：
- P-4 的閘門字面；
- P-5(c) 的重審；
- P-6 是否另外揭露；
- P-7 `{shares}` 的口徑；
- P-8 的前端代入；
- A-6 是否不算分類。
- CEO：本 ADR 轉 accepted；知悉群組 B 以 `settled_at` 為起算日。
- PM：PRD v0.2，依 [風控 N171]「給 product-manager」各點與本 ADR 改寫 FR-3、AC-N171-5、AC-N171-11、AC-N171-12、AC-N171-14、M2、FR-B2。
- art-lead：在風控限定的位置與順序內出版面。

## 附錄 A：N171-C 約束（qa-reviewer 逐條檢查，皆為 BLOCKING）

- C1：欄位為加法，預設空；`types.ts` 標 optional；收到舊回應時前端不出錯。
- C2″：
- 候選列只來自 `_read_exit_state`；
- 分類只經 `classify_exit_batches`（抽自 `plan_emergency_exit`，出清也走這裡）；
- 判準 Z 只用 `exit_line_still_covers`；
- authored 用 `_settle_pending` 載入的序列；
- 不另寫 SQL、不呼叫 `pending_directives(on_or_before)`、不加 execution_date 條件、不另外載入日線。
- C3：不由 mode 或 `emergency_until` 推導。
- C4″：一批一類一行；`shares` 取批次 `remaining_shares`，不得加總各列股數；日期依類別去重後遞增。
- C5：不含 buy 列，不含已結算列。
- C6：
- 字面只放 `wording.py`，逐字等於 [風控 N171]；
- store 不 import wording；
- 「建議」只出現在白名單內的歸屬否定句。
- C7：前端
- 是獨立元件，只讀 `["playbook-today"]`；
- 不經過 `DirectiveLedger`；
- 不 import receipt store 或 mutation；
- 不 sticky；
- 不摺疊、不截斷、不加 CTA、不放空殼；
- 位置照風控規定；
- 渲染每一行的 `entry_before_exit_note`。
- C8：NB-6 第 2 段原子替換；第 3 段等於 `wording.py:541-546`。
- C9：只經由 `read_in_flight` 讀取；過程中零寫入。
- C10：unauthored 不載入、不結算、不寫入、不分類。
- C11：只收 open 批次。
- C12：群組 B 不存狀態、沒有關閉機制；保留期綁常數；B 不併入 A。
- C13：`directives` 不含 EMERGENCY。
- C14：沒有任何一行時，`pending_exit_block` 為 None，畫面不出現任何字面。
- C15：`DirectiveLine` 只經由 `_lines` 建立；W-B2L 不得拼進 `text`。
- C16：B-4 不改 EMPTY 本文，不新增 message 分支。
- C17：unauthored 時 `POST /settle` 不 claim、不動帳，回 200 並附 `SETTLEMENT_UNAUTHORED_NOTE`；字面待風控。
- C18：`warnings` 零 diff。
- C19：`{read_at}` 只由前端以 `formatDateTime(data.as_of)` 代入一次；後端不代入。
- C20：B 的列與 `{shares}` 只經 `replay_exit_sell_moves` 認定；B-4 共用同一組函式。

## 附錄 B：測試清單

- T1～T10：風控 dev-lead 清單第 7 項 (a)～(j)，逐條實作，其中 (j)：同一時點重送時，S1 的 `{pending_shares}` 等於區塊股數。
- T11：同一份 DB 讀兩次，結果相同；用新的 service 實例讀取，模擬重新整理與第二個分頁。
- T12：模式與凍結日的變化不影響區塊內容。
- T13：R1 的待成交列不進區塊。
- T14：trace 顯示 N-171 的路徑零寫入、零新增載入。
- T15：分類一致性：第二次載入回傳不同資料時，區塊分類仍與 N1 一致，證明用的是結算那一份序列。
- T16：`plan_emergency_exit` 重構前後，既有的出清測試斷言不變；`classify_exit_batches` 有等價性測試。
- T17：unauthored：resolver 沒有被呼叫；全部 unclassified；A-4、A-13 出現；零寫入。
- T18：unauthored 時 `POST /settle` 不 claim、不動帳（C17）；authored 時行為不變。
- T19：closed 批次上的列被排除。
- T20：重送走 ALREADY_PENDING、隔天重送、EX-3 三種情況下，區塊內容正確。
- T21：`warnings` 與 N-172a 錨點測試不改斷言。
- T22：前端以 `formatDateTime(as_of)` 代入，恰好一次；鏡射常數逐字相同。
- T23：SEAM-T3～T5 仍為綠燈。
- T24：qa-e2e：AC-N171-12 的四條路徑，以及風控 S-A～S-D 四張畫面與 DOM 擷取。
- TB1～TB3：保留期的邊界日、遇休市日、unauthored 日曆。
- TB4：重算：P1 先減一部分後才出清、S1 先關閉批次、N-166 前的重複列、判準 Z 的舊列後補日線，四種情況下認定正確。
- TB5：讀取零寫入、schema 不變。
- TB6：B-4 只在有保留期內的已結算出清列時附加；EMPTY 本文不變。
- TB7：B-4 與 B 區塊對同一份 DB 判定一致。

## 補充一：風控 2026-11-04 回審的落地事項

- 日期：2026-11-04
- 決策者：tech-architect；字面與條件出自 risk-compliance-officer（`work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md`，下稱 [風控 1104]）
- 性質：補充 v2，不改 v2 本文。下文寫「取代」的地方，以本補充為準。
- 程式位置是 2026-11-04 工作樹 `product/stock-desk` 的快照（切面尚未落地），請以內容定位。

### S-1 A-15 欄位與同列順序
1. 識別名 `PENDING_EXIT_SHARES_REDUCED_NOTE`（A-15，required）。逐字以 [風控 1104] 第 4 點為準，沒有佔位符。
2. 不新增欄位，放進 `PendingExitRow.notes`。和 A-6、A-11、A-12 一樣是同列附註，由後端判定，前端不做判斷。
3. 渲染條件：該行的任一底層列 `shares` 大於該行的 `shares`（也就是批次在讀取點的 `remaining_shares`）。
 - 底層列：歸入該行的 EMERGENCY 候選列，同 symbol、同 batch_no、同類別。unauthored 路徑取該批次的全部列。
 - 由純函式 `exit_row_shares_reduced(line_shares: Sequence[int], *, remaining_shares: int) -> bool` 判定。
 - 輸入只取同一次 `read_in_flight` 的列與批次，不經分類，不用 calendar，不呼叫 resolver。
 - covering、stale、unclassified 三類的行都適用，unauthored 路徑也適用。
4. 同列順序固定，由後端組好：
 - covering 行與 unclassified 行：`text`（A-5）→ `notes` 依序為 [A-6]、[A-15] → `entry_before_exit_note`（W-B2L）。
 - stale 行：`text`（`EMERGENCY_EXIT_STALE_ITEM`）→ `notes` 依序為 A-11 或 A-12、[A-15] → `entry_before_exit_note`。
 - 前端依 `text`、`notes`（照清單順序）、`entry_before_exit_note` 的順序渲染。不得重新排序、篩選或自行撰寫文字。
 - 前端不得以 `pending_exit_directives` 渲染任何文字。
5. 剩餘股數歸零時，批次已非 open，該行不在 A（見 S-4）。A-15 不處理這種情況。

### S-2 A-6 謂詞（[風控 1104] 第 1 點）
1. 謂詞是純函式 `exit_row_past_due(execution_dates: Sequence[date], *, as_of: date) -> bool`，等於 `any(d < as_of for d in execution_dates)`。
2. `as_of` 用同一次 `evaluate_today` 的 `as_of`，即 `today or datetime.now(UTC).date()`，UTC 日期。這與 S3（`service.py:1317` 的 `day < as_of`）同一口徑。不得改用 `data_date`。
3. 不得經過 `TradingCalendar`（空日曆也不行），不得讀日線，不得呼叫 resolver。函式簽名不收 calendar，也不收 bars。
4. 只用在 covering 行與 unclassified 行，v2 Decision 4 不變。
5. 測試口徑：unauthored 路徑本來就會建 `TradingCalendar(())`（`build_exit_confirm`，以及群組 B 的 unauthored 日曆），所以不斷言「整條路徑沒有呼叫 calendar」。改為三項：
 - (a) AST／簽名測試：`exit_row_past_due` 不收 calendar 與 bars；函式體不引用 `TradingCalendar`、`calendar`、`load_` 或任何 resolver；
 - (b) unauthored 回應出現 A-6 時，market resolver 與 index resolver 的呼叫次數都是 0；
 - (c) property test：任意日期序列與 `as_of` 下，結果等於 `any(d < as_of)`。
 - (d)（風控 2026-11-04 確認時追加，見 `work/reviews/2026-11-04-ADR0039補充一確認-風控.md`）：A-6 只能在 `exit_row_past_due` 回傳 True 時附上，且全程式只有這一個呼叫點，以靜態掃描斷言。

### S-3 N171-C17 的形狀（取代 v2 附錄 A 的 C17）
1. 位置：新增 service 方法 `PlaybookService.settle_on_request(*, today: date | None = None) -> SettlementResult`，歸 N-171 擁有。
 - `POST /api/playbook/settle` 改呼叫它。
 - `app/api/` 內不得直接呼叫 `settle_pending(`。
2. 流程：
 - `as_of = today or datetime.now(UTC).date()`；
 - 第一步讀 `self._store.rule_set_authorship(as_of).user_authored`。這和 `evaluate_today` 是同一個判斷，必須在任何 `pending_directives`、日線載入、claim 之前；
 - 為 false 時，直接回 `SettlementResult(settled_on=as_of, settled=[], unsettled=[], warnings=[wording.SETTLEMENT_UNAUTHORED_NOTE])`。`executed`、`missed` 由 property 算出，都是 0；
 - 為 true 時，`return self.settle_pending(today=as_of)`，行為不變。
3. 不動的部分：`settle_pending`、`_settle_pending`（ADR-0035 補充四 S-2.4、SEAM-T6）、`evaluate_today`。
 - 理由：閘門若放進 `settle_pending`，SEAM-T6 的等式在 unauthored 情境就不成立；authored 的 `/today` 也會重複讀一次 authorship。
4. 回應：HTTP 200。`warnings` 恰好是 `[SETTLEMENT_UNAUTHORED_NOTE]`，不得同時有 `SETTLEMENT_NOTHING_PENDING`、`SETTLEMENT_SUMMARY` 或其他任何句子。字面逐字以 [風控 1104] 第 2 點為準。
5. 零寫入、零載入：trace 只出現 SELECT，沒有 INSERT／UPDATE／DELETE；market resolver 與 index resolver 都呼叫 0 次。
6. `/today` 不帶這句：
 - unauthored 的 `/today` 維持 `settlement=None`；
 - `evaluate_today` 不呼叫 `settle_on_request`；
 - `SETTLEMENT_UNAUTHORED_NOTE` 在 `/today` 回應中出現 0 次。
7. 合併：C17 與這句字面，放在 N-171-A 的同一個 PR，或更早的 PR（[風控 1104] 結論條件 4）。
8. 回審觸發：N-175 改成在 unauthored 下結算，或 S-6 的單調性被打破時，A-13 和這句字面都要回審。

### S-4 P-5(c) 的殘留（取代 v2 Consequences 中「closed 批次上、仍算涵蓋的未結算列……（P-5(c)，待風控）」一句）
1. 「在帳冊仍記為持有」定義為 open 且 `remaining_shares > 0`，也就是 `_read_exit_state` 的 `open_batches`。C11、A-2 修訂版、NB-6 第 2 段第二版共用這個定義，不得另寫。
2. 所屬批次在帳冊已不再記為持有的未結算出清列，不在 A，由 A-2 修訂版明示這個範圍。這類列在 `/today` 上只有以下揭露：
 - (i) 符合判準 Z：結算區附 N1，批次子句為「已無持股」；
 - (ii) 已到期但不符合判準 Z：結算區只有 `SETTLEMENT_NO_OPEN_PRICE`；
 - (iii) 未到期：不顯示，結算時以 N2 揭露一次。
3. (ii)、(iii) 是風控書面接受的殘留，根源是 F4／N-169 與 N-166 之前的重複列，N-169 落地時回審。
4. (ii) 的畫面上仍有「賣出 N 股、待結算」，有誘發重複賣出的風險。這是既有字面，不在 N-171 範圍，風控列為 suggested，交 N-169 一併處理。

### S-5 群組 B 的讀取下界（取代 v2 Decision 10「下界取 `settled_at >= as_of − LOOKBACK_DAYS` 個日曆日」）
1. 條件（[風控 1104] 第 5 點）：讀取結果必須是保留期判定的超集。凡是 `as_of <= calendar.shift(settled_on, 20)` 的列，都必須讀到；這裡的 calendar 就是做判定的那一份。
2. 判定：日曆日常數下界**無法證明**是超集。
 - `shift` 對起點單調。所以超集成立的充分條件是：calendar 在 `[as_of − L, as_of − 1]` 內至少有 20 個交易日。
 - 資料完整時，這個條件成立，而且餘裕很大：180 個日曆日約有 120 個交易日，春節長假約 9 個日曆日。unauthored 用空日曆，交易日就是平日，也成立。
 - 但 authored 路徑的 calendar，在觀察範圍內以「當天有沒有 bar」判定交易日。指數載入失敗、個股缺 bar 時，範圍內的交易日可能不足 20，保留期被拉長而超出下界，列會被靜默漏掉。
 - authored 路徑的 calendar 是在 `read_in_flight` 之後才建的，讀取當下無法依 calendar 決定下界；事後發現不足，也不能補讀（ADR-0035 補充四 R-4）。
3. 決策：
 - 群組 B 的 SQL 不設 `settled_at` 下界，保留期只由 `settled_exit_retained` 判定。B-4（出清鎖內）同樣處理。
 - 成本：候選列是歷來判定 executed 的 EMERGENCY 賣單。每個批次一生最多一列實際減少股數，另有 N-166 之前的重複列，所以總量受批次總數限制，不會隨天數失控。重放需要的賣出列，也只讀這些批次的。
 - 日後若量測證明需要下界，只能用「讀取前就能決定、且對任何 calendar 都成立」的下界，由 tech-architect 另出補充。
4. 測試：
 - TB2 加春節長假的邊界案例（風控）；
 - 新增 TB8：calendar 稀疏（指數載入失敗、個股缺 bar），使某列 `settled_on` 早於 `as_of − 180` 個日曆日、但 `shift(settled_on, 20) >= as_of`，這列仍要列出；
 - TB4 的 trace 確認群組 B 的 SQL 不含 `settled_at` 下界。
5. 這一節屬於 B 的閘門，不影響 A 的合併。

### S-6 authorship 單調性（前提；P-5(b)、A-13、C17 與 N-182 的 unauthored 不渲染 W-B6b 都依賴它）
1. 前提：`rule_set_authorship(d).user_authored` 只會從 false 變成 true，而且與 `d` 無關。
2. 依據（讀碼）：
 - 判斷只看確認旗標，以及 `playbook_rule_params` 的總列數；
 - `playbook_rule_params` 沒有 DELETE，寫入都是 `INSERT OR REPLACE`；
 - 確認旗標只由 `confirm_rule_set` 寫入，值從不為 None；`_write_state` 只有在值為 None 時才刪除 key；
 - playbook 的表沒有 DROP，也沒有重建。
3. 推論：買單只由 `engine.py:979` 的 R1 產生，只經 authored 的 `evaluate_today` 寫入。因此 unauthored 下不存在待成交的 R 系列買單。例外是 seed、手動改 DB，或內容不一致的 DB 檔。
4. 回審觸發：任何 PR 新增 true→false 的路徑，或 N-175 改成在 unauthored 下結算，就送風控回審 A-13、`SETTLEMENT_UNAUTHORED_NOTE`，以及 N-182 解讀點 5。

### S-7 狀態更新
1. Decision 11 的 A 閘門：「P-4、P-5 的退回項，風控重審通過」改為 [風控 1104] 的四項：
 - A-2 修訂版；
 - A-15；
 - NB-6 第 2 段第二版；
 - C17 加 `SETTLEMENT_UNAUTHORED_NOTE`，放在同一個 PR 或更早的 PR。
 其餘字面維持 11-03 定稿：A-1、A-3～A-9、A-11～A-14、`EMERGENCY_EXIT_STALE_ITEM`。前端時點與 S-A～S-D 照舊。
2. Decision 13（NB-6）：第 2 段改用第二版。第一版和 11-03 修訂版，在 grep 中都要為 0。仍然原子替換。
3. Decision 1：`lead_template` 改用 A-2 修訂版，仍保留字面上的 `{read_at}`。
4. Decision 10（B，仍受閘門限制）：
 - `{shares}` 取實際減少的股數，風控 P-7(i) 已確認。少於該列股數時，同列附 B-5（草稿）。B 的行因此要加 `notes: list[str]`，B 閘門通過時定案；
 - 重放與帳冊不一致只會發生在 F2 並發窗口，風控 P-7(ii) 已確認，歸 N-169；
 - 保留期從 `settled_at` 的 UTC 日期起算（CEO #103 知悉）；
 - B-2 末句改用 [風控 1104] 的修訂草稿。
5. Decision 16 的 P-8：「晚幾毫秒」更正為「可能晚到秒級」，風控確認不影響語意。
6. 待決：P-4、P-5(c)、P-6、P-7、P-8、A-6 已由 [風控 1104] 結案。剩下的有：
 - S-2 第 5 點、S-5 待風控確認；
 - B-1～B-5 待核可；
 - CEO 核可轉 accepted；
 - PM 出 PRD v0.2，含 F-8(2)(a)／AC-N171-12，以及 A-15 的 AC。

### S-8 附錄 A、B 增修
- 附錄 A（皆為 BLOCKING）：
- C17′：以 S-3 為準，取代 v2 的 C17。
- C21：S-6 的前提有守門測試：
  - app 內沒有 `DELETE FROM playbook_rule_params`，playbook 的表沒有 DROP；
  - `STATE_RULE_SET_CONFIRMED_AT`、`STATE_RULE_SET_VERSION` 只在 `confirm_rule_set` 內寫入，且不以 None 寫入；
  - 對任意兩個日期，`user_authored` 的結果相同。
- C22：A-15 依 S-1 判定與排序；前端不以 `pending_exit_directives` 渲染文字。
- C23：A-6 依 S-2。
- C24：群組 B 與 B-4 的 SQL 不設 `settled_at` 下界（S-5）。
- 附錄 B：
- T17′：S-2 第 5 點的 (a)(b)(c)。
- T18′：S-3 第 4～6 點，包括 trace、resolver 0 次、`/today` 出現 0 次、authored 時行為不變。
- T25：P1 先部分減股之後，出現 A-15，股數等於剩餘股數；股數相等時不出現；三類的行都測（[風控 1104] (k)）。
- T26：批次已 closed 的未結算出清列不進區塊，A-2 照常出現（[風控 1104] (l)）。
- T27：前端守門：不以 `pending_exit_directives` 渲染文字；同列依 `text`、`notes`、`entry_before_exit_note` 的順序渲染。
- T28：C21 的守門測試。
- TB2′、TB8：見 S-5 第 4 點。
- T22 增列（suggested）：正常回應中，`{read_at}` 的代入值不得是「時間不明」。

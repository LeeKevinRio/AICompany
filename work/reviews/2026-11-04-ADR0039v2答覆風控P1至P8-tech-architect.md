# ADR-0039 v2：答覆風控 P-1～P-8

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 補充回報：答覆風控 P-1～P-8，ADR-0039 改為 v2

## 一、本次結論

八項前提的判定如下：

| 判定 | 項目 |
|---|---|
| 成立 | P-1、P-2 |
| 改設計後成立 | P-3 |
| 附條件成立 | P-4、P-6、P-7、P-8 |
| 部分不成立 | P-5（要退回風控） |

- **P-3：**我原本的設計在 unauthored 路徑上，會把預定執行日還沒到（`execution_date >= as_of`）的列直接判為涵蓋。這正是風控說的「不載入日線也能分類」，會讓 A-4、A-13 退回重審。所以我撤回這部分，改成 unauthored 一律不分類。
- **P-4：**現況不成立。`POST /api/playbook/settle` 沒有檢查使用者是否已確認規則集，直接打 API 就能在 unauthored 狀態結算。我加一條約束（N171-C17）：unauthored 時這支端點不結算。補上之後 P-4 成立。端點被擋時回應要附一句新字面，這句要送風控。
- **P-5：**「只收 open 批次」這一點成立。但風控引用的理由（批次已 closed 的舊列，每天由結算區的 N1 揭露）只有一部分成立。N1 只掛在「判準 Z 下已不再涵蓋」的列上。其他 closed 批次上的未結算出清列，要嘛只有「尚無開盤價」那句，要嘛完全不出現。所以 F-8(2)(a) 的例外描述要退回風控重審，A-2 的「列出……帳冊尚未結算的賣出指令」是否要限定範圍，也一併交風控判斷。
- **P-6：**定義相同，成立。凍結期間 S/P 系列照常評估，所以**剩餘股數確實可能小於出清列的股數**，已回報風控。
- **P-7：**三點都可以做。第三點（取「實際讓帳冊減少股數」的那一列）比較麻煩：DB 沒有存每一列實際減了多少股，要從日誌重算一次。
- **P-8：**附條件成立。`{read_at}` 不在後端代入，改由前端用頁面上同一個 `formatDateTime(as_of)` 代入，這樣值與格式才保證和頁面其他地方相同。
- **其他確認：**
  - 群組 A 區塊不放進 warnings。N-168 P4 的 warnings 順序與 N-172a 的錨點都不受影響，已寫進 ADR。
  - 覆蓋判定共用 `exit_line_still_covers` 與 `plan_emergency_exit` 的逐批邏輯，並抽成單一 helper，已寫進 N171-C2″。
- **API 形狀改了：**風控 F-8(1) 接受「一批一行」，所以 ADR-0039 改為後端組好的區塊結構，每一行帶類別與「同批是否另有仍涵蓋的列」。
- **ADR-0035 補充四（A）不需修改：**上述變更都落在 N-171 自己擁有的範圍，或屬於加法欄位。

## 二、各部門回報

### tech-architect（本人，唯讀）

**P-1～P-8 逐條答覆**（已寫進 ADR-0039 v2 Decision 16）

**P-1 成立**
- 分類用的就是結算本身載入的那一份序列：經切面的 `_settle_pending` 取得 `run.loaded`，同一次 `_load_symbol_bars(…, today=as_of)` 的結果。結算區的 N1／N1b（`_with_stale_exit_notes`，`service.py:694`）也是用這一份判的。
- 結算只載入「已到期待結算列」的標的。已到期的出清列一定在這些標的裡；沒到期的列，用什麼序列判都會是涵蓋，所以不用載入。
- N-171 本身不新增任何一次載入。`evaluate_today:1154` 原本就有的評估用載入，N-171 不使用。

**P-2 成立**
- 每一行帶 `coverage`（covering／stale／unclassified）與 `batch_has_covering`。
- A-11 或 A-12 由後端依 `batch_has_covering` 選好，前端只負責顯示。

**P-3 成立（改設計）**
- unauthored 路徑不呼叫覆蓋判定，所有行都是 unclassified。
- 照舊不載入日線、不結算、不寫入。
- A-6（預定執行日已過）只比對預定執行日與 `as_of`，不算分類。這點請風控確認。

**P-4 附條件**
- 讀碼結果：
  - `evaluate_today` 在 authorship 檢查之後才結算（`:1149-1151`）；
  - 排程程序不 import playbook（grep 結果：只有 api 與 playbook 自身）；
  - 前端從不呼叫 `/settle`（grep 為 0）；
  - **但** `POST /api/playbook/settle`（`api/playbook.py:449-457`）沒有 authorship 閘門。
- 要讓 P-4 成立，N-171-A 須加 N171-C17：unauthored 時 `POST /settle` 不結算，回 200，並附一句新字面 `SETTLEMENT_UNAUTHORED_NOTE`。這句要風控定字面，不能沿用 `SETTLEMENT_NOTHING_PENDING`，因為在那個狀態下它是假話。
- 另一種做法是風控把 A-13 改成不帶絕對宣稱的寫法。我建議加閘門。
- N-175（unauthored 狀態下不結算，即 F6）若日後改成「在 unauthored 下結算」，A-13 要回審。

**P-5 部分不成立，退回風控**
- (a) 只收 open 且 `remaining_shares>0` 的批次：**成立**。和 `_read_exit_state` 讀批次的條件相同。
- (b) unauthored 路徑不會有 closed 批次的未結算列：**附條件成立**。
  - authorship 只會從 false 變 true：確認旗標與 `playbook_rule_params` 都沒有刪除路徑（grep `DELETE FROM` 只刪 `playbook_state` 的指定 key，沒有刪 rule set 的 key）。
  - 所以 unauthored 等於從未確認過規則集。這種狀態下唯一的結算路徑就是 `POST /settle`，P-4 的閘門補上之後就沒有了。
  - 例外：seed 或手動改 DB，不在保證範圍內。
- (c) 理由「authored 路徑每天由 N1 揭露」：**部分不成立**。
  - N1 只掛在判準 Z 下已不再涵蓋的列。
  - closed 批次上、仍算涵蓋的未結算出清列：
    - 若已到期，只顯示 `SETTLEMENT_NO_OPEN_PRICE`；
    - 若未到期，`/today` 完全看不到，等到結算時才出現 N2。
  - 實際會發生的例子：
    - N-166 之前、跨日的重複出清列；
    - P-6 的情況：S1 先把批次結算成 closed，出清列還沒到期。
  - 要請風控重審 F-8(2)(a) 的例外描述，並檢查 A-2「列出……帳冊尚未結算的賣出指令」在這種情況下是否言過其實。
  - NB-6 第 2 段「不寫全部」那段理由仍然成立。

**P-6 定義成立，並回報「會小於」**
- `{shares}` 等於該批次的 `remaining_shares`。這和 S1／S2 的 `{pending_shares}` 同一個定義：`ExitPending.shares` 是被涵蓋批次的 `remaining_shares` 加總（`service.py:1313-1319`、`wording.py:835-`）。
- 剩餘股數小於出清列股數的情況，在 `engine.py:1164-1165` 有依據：凍結只停 R 系列，S/P 系列每天照常評估。會發生在兩種情形：
  - 資料落後：T 日盤中 `data_date` 還是 T-1，產生預定執行日為 T 的 P 或 S 賣單；同一天出清，產生預定執行日為 T+1 的 EMERGENCY。T 日晚上 P／S 先結算，剩餘股數就減少，甚至歸零讓批次 closed；
  - F7：出清列卡在休市日，之後的 S/P 賣單照常結算。
- 剩餘股數歸零時，批次 closed，該行離開群組 A，就變成 P-5(c) 的情況。
- 是否另外揭露，由風控判斷。根源是 F4／N-169（凍結期間 S/P 會替已有出清單的批次再出賣單），不在 N-171 範圍。

**P-7 附條件成立（群組 B）**
- 結算日取 `settled_at` 的 UTC 日期：成立。這和我原本給 CEO-1 的建議預設相同，所以 CEO-1 改為只需知悉。
- 保留期綁具名常數 `SETTLED_EXIT_RETENTION_TRADING_DAYS = 20`，`{retention_days}` 由這個常數渲染：成立。
- 交易日曆口徑：
  - 用同一次請求的 `build_calendar`（已載入的個股日線加指數日線），觀察範圍外以平日推算；
  - `/today` 的 authored 路徑與出清的 B-4 都用這個口徑；
  - unauthored 路徑用空日曆。
- 「實際讓帳冊減少股數的那一列」：DB 沒有存實際減少的股數，要用純函式 `replay_exit_sell_moves` 重算：
  - 依 `(settled_at, id)` 的順序重放該批次所有已成交的賣出列；
  - 做法完全照 `settle()` 的 `min`／`max`（`store.py:1345-1351`）；
  - 每批最多一列出清列會減少股數，N2 那類「移動 0 股」的列自然被排除。
- 有兩點要風控確認：
  - (i) `{shares}` 我建議取「實際減少的股數」。正常情況下它等於該列的股數；P-6 的情況下會比列的股數小。
  - (ii) 重算的結果和實際帳冊，只有在 F2 的並發結算窗口才可能不一致（歸 N-169）。
- 會減少股數的出清列一定會讓批次 closed（出清後剩餘股數只減不增），所以 B-2「這幾批在帳冊已不再記為持有」為真。
- B-4 與 B 區塊共用同一組函式，即同一個來源。

**P-8 附條件成立**
- `TodayResponse.as_of = now_iso()`，在 API 層組回應時產生（`api/playbook.py:413`）；前端用 `formatDateTime(asOf)` 顯示，時區 Asia/Taipei（`PositionSnapshotTable.tsx:37`、`format.ts:193`）。後端無法重現前端的時區與格式。
- 做法：A-2 以樣板 `lead_template` 下發，保留字面上的 `{read_at}`；前端只代入這一處，用 `formatDateTime(data.as_of)`。
- 守門測試要斷言三件事：鏡射常數逐字相同、代入恰好一次、代入值來自同一份回應的 `as_of`。前端代入有先例（`sectorMomentumWording.ts` 的樣板）。
- 嚴格說，`as_of` 比讀取點晚幾毫秒。我判斷這不影響「依 {read_at} 讀取的紀錄」的意思，請風控確認。

**其他兩件**
- **單一 helper：**從 `plan_emergency_exit` 抽出純函式 `classify_exit_batches`，出清與 N-171（authored）都經由它判定；判準 Z 仍只有 `exit_line_still_covers` 一個來源；不另寫任何 EMERGENCY 的 SQL，候選列只來自 `_read_exit_state`。寫進 N171-C2″。
- **warnings：**群組 A／B 區塊是獨立欄位，`warnings` 零 diff。N-168 W-B6 在 FROZEN_NOTE 之後的位置、N-172a `same_day_warnings` 的錨點、`UNAUTHORED_HOLDING_NOTE` 都不變。寫進 N171-C18 與 Decision 17。

**ADR-0039 從 v1 到 v2 的主要改動**
- 欄位：撤回 `stale_exit_directives`、`unclassified_exit_directives`、`pending_exit_notes`，改為 `pending_exit_block`（區塊、小節、行三層結構）。`pending_exit_directives` 保留，改為群組 A 全部列的原始資料，前端不拿它來渲染。
- unauthored：撤回 u3，改採 u2（全部不分類）。
- W-B2L：依風控 F-11，A 區塊三類的行與 B 區塊的行都經 `_lines` 的結果帶出 W-B2L。這取代我 v1 寫的「B 不帶 W-B2L」。
- 新增：N171-C17（`POST /settle` 閘門）、C18（warnings 零 diff）、C19（`{read_at}` 由前端代入）、C20（B 用重算認定）；Decision 16（P-1～P-8 答覆）、Decision 17（warnings）。
- 群組 B 改成一批一行，需要重算，B1 的後端規模由 S 調為 S～M。結論仍是**可同包**。

### 可直接貼上：ADR-0039 v2 全文（取代先前回報中的 B 塊）

```
# ADR-0039：stock-desk `/today` 常駐揭露待執行與近期已結算的出清指令（補充 ADR-0033，不取代）

- 狀態：proposed
- 日期：2026-11-03（v2：納入風控 2026-11-03 N-171 字面裁示與 P-1～P-8 答覆）
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
```

### 應經手但尚未經手
- **risk-compliance-officer**：P-4 的新字面 `SETTLEMENT_UNAUTHORED_NOTE`（或改寫 A-13）、P-5(c) 重審、P-6 是否另外揭露、P-7 的 `{shares}` 口徑、P-8 的前端代入、A-6 是否不算分類。
- **product-manager**：PRD v0.2。
- **CEO**：只需知悉（見下一步）。

其他部門：本次未參與。

## 三、驗證

- 讀過：
  - 風控 `work/reviews/2026-11-03-N171字面與NB6回審-風控.md` 全文；
  - `store.py:915-975`（authorship 只會從 false 變 true）；
  - `engine.py:1105-1194`（凍結只停 R 系列）；
  - `wording.py`：S1／S2 的 `pending_shares`、`ExitPending`、`ATTRIBUTION_NO_USER_RULES`、`UNAUTHORED_HOLDING_NOTE`、`SETTLEMENT_NOTHING_PENDING`；
  - 前端 `format.ts:193`、`PositionSnapshotTable.tsx:37`；
  - 前端樣板代入的先例 `sectorMomentumWording.ts`。
- grep 過：`/settle` 的呼叫端（只有 api 本身）；import playbook 的模組（沒有排程程序）；`DELETE FROM` 的範圍。
- 「P-6 會小於」與「P-5(c) closed 批次上的列」都是讀碼推論。建議 qa-automation 以「資料落後時，S1 先結算關閉批次」的情境重現。
- 沒有執行程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改檔案。

## 四、下一步

1. coordinator：
   - 用本回報的 v2 全文取代先前的 B 塊，交 tech-writer 落檔 ADR-0039；
   - ADR-0035 補充四（A 塊）維持原樣；
   - 把 P-4 的新字面與 P-5(c) 送回風控重審。A-1～A-14 在重審之前，視為「條件尚未全部成立」。
2. CEO：
   - 原 CEO-1 改為只需知悉：群組 B 以 `settled_at`（帳冊判定當天）起算 20 個交易日，風控與我的判斷一致；
   - 知悉 R10 殘留延續到群組 B 上線；
   - 本 ADR 轉 accepted 要由 CEO 核可。
3. dev-lead：N-171-A 開工時以 v2 為準，注意 C2″、C17～C20。C17 是 A 合併的前提。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-03-N171字面與NB6回審-風控.md
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/wording.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/format.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/PositionSnapshotTable.tsx

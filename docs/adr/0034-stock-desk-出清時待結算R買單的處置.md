# ADR-0034：stock-desk 出清時待結算 R 買單的處置（補充 ADR-0033，不取代）

- 狀態：accepted（CEO #79、#80，2026-10-31 裁定；落檔前提：新字面經風控逐字定稿後才可合併、F5（N-172）修法定調前 N-168 不開工實作，見 Decision 8、Decision 9 與 Consequences）
- 日期：2026-10-31（tech-architect 草案日期 2026-10-31）
- 決策者：tech-architect（草案與技術評估）；risk-compliance-officer（方案裁示 CONDITIONAL APPROVE B-2a，2026-10-31；字面逐字定稿）；CEO #79（採 B-2a、標示來源採 L4）、#80（B-2b 列為永久紅線）於 2026-10-31 裁定。
- 與 ADR-0033 的關係：
  - **補充 ADR-0033，不取代**。ADR-0033 維持 accepted，原文不改（ADR-0001 決策生效後不得原地改寫）。
  - 本 ADR 只在 0033 的 C-1、C-2、C-7、C-8 之上做**加法**（見 Decision 2～4）。與 0033 任一條沒有字面衝突。
  - **取代條件**：若日後風控要求 message 新增第四支，會與 0033 的 C-8「message 分三支」直接衝突；屆時**不得修改本 ADR 或 0033**，改為另立一份「取代 ADR-0033」的新 ADR，完整重述 C-1～C-11，並將 0033 標為 `superseded by ADR-NNNN`。出處：[TA] Q2「與 ADR-0033 的對照」C-8 列、ADR-0034 草案 Consequences 末項。
- 來源簡稱（皆在 `work/` 下）：
  - [TA]：`reviews/2026-10-31-N168技術評估-tech-architect.md`（Q1～Q5、L1～L4、VETO-1～VETO-5、C-B1～C-B11、T-B1～T-B16、C-A／T-A、F5、「ADR-0034 草案」一節）
  - [風控]：`reviews/2026-10-31-N168方案裁示-風控.md`（方案表態、D1～D7、W 系列識別名與組合順序、逐條意見）
  - [PM]：`prd/2026-10-31-N168出清後待結算R買單-方案比較.md`（方案 A／B-1／B-2a／B-2b／C／D、FR-1～FR-8、AC-1～AC-11）
  - [決策包]：`dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`（第 95 行 #79、第 96 行 #80；第 100 行 coordinator 定案）
  - [追蹤清單]：`dispatch/2026-10-17-後續追蹤清單.md`（N-168 補2、N-172、N-173、N-174）
  - [ADR-0033]：`docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md`
  - [風控 N-166]：`reviews/2026-10-31-N166新字面與延長凍結揭露-風控.md`（S1～S9；本檔未讀其全文，僅引用 [風控] 與 [TA] 對它的轉述）
- 適用範圍：僅 product/stock-desk；程式路徑相對於 `apps/stock-desk/backend/`（前端路徑相對於 `apps/stock-desk/frontend/`）。
- 標註約定：
  - 本檔為 [TA]、[風控]、[PM] 加 CEO #79／#80 裁定的轉錄，屬記錄決策脈絡（B 類）。tech-writer 落檔時**沒有讀 code、沒有執行程式**，也沒有替草案補任何技術細節。
  - 文內 `檔案:行號` 一律是 [TA]、[風控] 撰寫時（2026-10-31）的快照，會隨 commit 漂移，**tech-writer 未逐條重驗**，抽驗請以內容定位。
  - 引用 ADR-0033 時，本檔改引**條號與附錄名稱**（C-1、附錄 D F1 等），不沿用 [TA] 的 `0033:行號`：落檔時抽驗發現 [TA] 引的 0033 行號與目前檔案相比偏 1 行（例：C-1 在目前檔案第 125 行，[TA] 引為 124），內容無誤。
  - **字面規則**：風控 W 系列的實際文字**一律不寫進本檔**。本檔只寫識別名；**逐字以 `work/reviews/2026-10-31-N168方案裁示-風控.md` 為準，僅放 `wording.py`**，風控逐字核可前不得合併。
  - **面向使用者的標示語意**（[TA] Q1 第 3 點、[風控] D1）：寫成「**出清當時尚未結算、不在該次出清範圍**」。[PM] 草稿用過的「出清後成交」只能當內部識別名，**不得出現在任何面向使用者的文字**（理由：[風控] D1 指出「成交」在使用者未下單的情境下是斷言券商端事實，「出清後」也有歧義）。標示的實際字面由風控 W-B2 定稿，不在本檔。

---

## Context（背景）

以下出自 [PM]（背景與目標）、[TA] Q1 與 ADR-0034 草案 Context，以及 [ADR-0033] 附錄 D F1。

- **問題（ADR-0033 附錄 D 的 F1）**：出清前已寫入、尚未結算的 R 系列買進指令，出清後仍會在 T+1 結算成 open 批次，與出清 message 的「R 系列暫停」互相矛盾。
  - 此時批次 Y 是 `planned`、買單是 pending；出清只看 open 批次，所以買單完全不在出清範圍內。（[PM] 機制 1、2；`playbook/engine.py:699-711`、`playbook/service.py:754-756`、`playbook/store.py:930-941`，皆為 [PM]／[TA] 快照。）
  - 結算不看模式，`GET /today` 會自動觸發結算，所以凍結期間的結算不需要使用者動作。（[PM] 機制 3；`service.py:258-315`、`:631`。）
  - 本產品沒有任何帳冊修正入口，使用者無法手動新增、刪除或修改批次。（[PM] 機制 5；[PM] R-3。）
- **核心難題（R10）**：本產品不下單，系統無從得知使用者在 T0 到 T1 之間**是否已依買單到券商下單**。在系統內處置買單，不等於券商那邊沒成交；不處置，也不等於券商那邊有成交。所以任何方案都必須先選定一個帳冊假設，並對另一種可能誠實揭露。（[PM]「核心難題」；[TA] ADR-0034 草案 Context 要求載明此點。）
- **[PM] 方案比較有兩處技術前提不成立，由 [TA] 更正：**
  1. [PM] 總覽表寫「B-2a 不改出清 transaction」。**不成立**：標示無法由既有資料可靠推得（見下），要可靠就必須在出清的同一個 `BEGIN IMMEDIATE` 內替待成交買單打戳記。所以 A 與 B-2a 對出清 transaction 的改動量相同（多一次鎖內 SELECT、加一次對同一批列的 UPDATE），差別只在 UPDATE 寫的內容；規模兩案都屬「中」。
  2. [PM] 寫「A 衝突、需修訂 0033」。**不必然**：只要撤回或戳記設計成加法，就與 0033 的 C-1／C-2／C-7／C-8 沒有字面衝突；只有開第四支 message 才會衝突。
- **標示來源推不出來的五個理由**（[TA] Q1，皆為讀碼判定，未執行）：
  1. 出清日沒有被保存：出清只保存 `emergency_until`（`store.py:563-564`），`executed_at` 只存在回應裡（`models.py:575`）；EMPTY 分支一列 EMERGENCY 指令都不寫（`service.py:754-756`、`:848-868`），而「只有 planned 批次又有待成交買單」正是 F1 的典型情境。
  2. 不能用 `emergency_until` 往回推出清起點：N-166 的 C-5 改採 max 後凍結日會被延長；參數版本可能已變更；日曆在最後一根 K 線之後走 weekday fallback；模式判定 `data_date <= emergency_until` 沒有下界（`engine.py:354`）。
  3. 批次的 `entry_date` 等於買單的 `execution_date`（`store.py:934`），可能早於出清日（例：T1 沒抓到開盤價，出清之後才補結算）。所以以「出清後」描述這類批次在事實上可能是錯的（該詞僅為內部識別名，見檔頭「標註約定」）；[TA] 建議面向使用者的語意改為「出清當時尚未結算、不在該次出清範圍」，由風控決定字面。
  4. 不能在結算時以「as_of ≤ emergency_until」判定：結算是惰性的，只在 `GET /today`（`service.py:631`）或 `POST /settle`（`api/playbook.py:437-445`）時才跑；使用者若在凍結結束後才回來，標示會漏掉。
  5. 在讀取時推導的標示，凍結一結束就會消失，做不到 [PM] AC-3 要求的「重新整理後仍存在」。
- **U-B 的實害**（[風控]「一、本次結論」）：[PM] 低估了 U-B（使用者未下單）的風險。風險不只是看到幻影批次，而是系統會對使用者並未持有的股數發出 S/P 或 EMERGENCY 賣出指令；使用者照做就可能誤下賣單（超賣或違約交割）。所以風控加了必要揭露，見 Decision 5。
- **限制**：
  - 風控 EX-2（出口不得有前置條件）、EX-3（凍結期間 SELL 與再次 EXIT 可執行）、EX-5（確認面板中性一步）、R10、R16（指令留存）；出處 [PM]、[風控]。
  - ADR-0033 的 C-1～C-11 與三支 message 結構已 accepted，不得原地改寫。
  - [風控] 已定稿的 `EMERGENCY_EXIT_RESULT`、`EMERGENCY_EXIT_EMPTY`、S1～S9 等既有字面不接受修改。

## Options（選項比較）

### 處置方案（取自 [PM]，加註 [風控] 裁示與 [TA] 技術判定）

| 方案 | 內容（[PM]） | [風控] 裁示 | [TA] 技術判定 | 結論 |
|---|---|---|---|---|
| A 出清時撤回 | 出清時把待成交 R 買單標為撤回，不再進結算；批次維持 `planned` | 附條件接受（不建議）：不能援引 R12；U-A（使用者已在券商下單）情境下持倉對系統隱形且帳冊內無法回收，須由 CEO 書面承擔（MA-7） | 做得出來；規模「中」；需新增指令狀態；凍結後 R1 會再替同一批次排買單，造成重複建倉（結構性結果） | **未採** |
| B-1 結算時略過 | 結算時略過屬凍結期的 R 買單並標示 | **否決**：A 的缺點全有、告知更晚，且以「未成交」類狀態斷言券商端事實，違反 R10 | 未單獨評估 | **否決** |
| **B-2a 轉 open＋標示** | 結算照常轉 open、扣帳冊現金，批次帶標示，不自動賣出，使用者可再次出清（EX-3） | **附條件接受（建議）**：延續全系統既有的帳冊假設，符合 R10，出口不動；風控版與 [PM] 版有 7 處差異（D1～D7） | 做得出來；規模「中」（非 [PM] 寫的「小到中」）；技術面略偏 B-2a | **採用（CEO #79，2026-10-31）** |
| B-2b 系統自動賣出 | 成交後系統自動替該批次寫 EMERGENCY 賣出指令 | **否決，建議列為永久紅線**：判斷主體變成系統，歸屬語不實，對未持有的股數產生賣出指令有實害，繞過 EX-5 | 未單獨評估 | **否決；永久紅線（CEO #80，2026-10-31）** |
| C 只揭露 | 只在出清當下揭露，結算不改、不標示 | 單獨成案**否決**：揭露時點對不上使用者最需要資訊的時點；**作為 B-2a 的必要元件納入** | — | 單獨**否決**，納入 B-2a |
| D 使用者回報成交 | 買單改成「待你確認」，由使用者回報已下單／未下單 | 可接受為後續方向，不併入 N-168；條件：回報不得擋出清、未回報時預設行為是 B-2a 而非 A、依 R16 落檔標明「使用者自行回報」與時間戳、須獨立 PRD 與風控審查 | — | 未併入；另開追蹤 N-173（[追蹤清單]） |

**A 案未採說明**：[TA] 為 A 案列了約束清單 C-A1～C-A9 與測試清單 T-A1～T-A11，因 A 案未採，本檔不全文收錄，需要時查 [TA]。其要點（轉錄自 [TA]）：撤回在 0033 的 C-1 transaction 內完成；新增指令狀態值，不得沿用 `missed`、不得經過 `settle()`、不得 DELETE、不得動 `missed_count`／`defer_count`；批次維持 `planned`；W-A6 需要凍結起點 KV；前端 union 與 label map 同步。若 CEO 日後改選 A，[風控] 的 must 級要求 MA-1～MA-7 與預審稿見 [風控] 第二節之六；屆時本 ADR 需另行處理，不得原地改寫。

### 標示來源（取自 [TA] Q1）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| L1 讀取時比較日期 | 不需遷移 | 推不出出清起點 | VETO-1 |
| L2 結算時看是否在凍結期 | 不改出清路徑 | 惰性結算會漏標 | VETO-1 |
| L3 凍結起始時在 `playbook_state` 存 directive id 水位線，加一個批次欄位 | 只需遷移一欄 | 正確性隱含地依賴兩件事：AUTOINCREMENT 單調遞增、凍結期間 R 不產生指令 | 可行，但不直觀 |
| **L4（採用，CEO #79）** 出清 transaction 內替待成交買單打戳記，加一個批次欄位 | 每列有明確的事實紀錄，冪等，好測試；FR-2／FR-7 可以直接查 | 需遷移兩欄 | 最低 |

[風控] D6 的要求：標示要以**落檔事實**判定，不得用可被覆寫的 `emergency_until` 反推；標示持續到批次 closed 為止，凍結結束後也不撤掉。L4 符合此要求（[TA] 判定，[風控] 已表態「能不能由既有資料推得，由 TA 判斷」）。

## Decision（決策）

1. **採 B-2a 加 L4**（CEO #79，2026-10-31；[決策包] 第 95 行原文：照常結算記為持有並以落檔戳記標示，停損停利照常評估，可再次出清收回）。
   - 出清時替「待成交 R 買單」打落檔戳記；結算成交時把戳記複製到批次標示；標示持續到批次 closed。
   - 結算照常：成交轉 open 並扣帳冊現金；MISSED 不加標示。
   - 系統不自動替標示批次產生任何 EMERGENCY 賣單；想賣，由使用者再次提交全部出清（EX-3）。
   - 「待成交 R 買單」的界定條件（[TA] Q3）：`action = 'buy' AND settled = 0 AND status = 'pending'`，在同一個 conn 的同一個 `BEGIN IMMEDIATE` 內讀取。不加 `execution_date` 條件（過期未結算的買單仍算待成交）；不使用 `store.pending_directives(on_or_before=...)`；不使用 `rule_id LIKE 'R%'`（會誤納 `REBALANCE`）。
2. **擴充 0033 的 C-1 transaction（加法）**：在 0033 的 C-1 那個 `BEGIN IMMEDIATE` 內，
   - **鎖內第四項讀取**：待成交 R 買單（0033 的 C-2 原列三項：open 批次、覆蓋集合、`emergency_until`）。第四項**只決定附加句與新欄位，不參與三支分支的選擇**，也不併入 C-4 的覆蓋集合。
   - **對同一批列的 UPDATE**：寫入戳記。0033 的 C-1 括號所列舉的寫入集合（新指令、`emergency_until`）由本 ADR 擴充為再加上戳記 UPDATE。
   - 三支分支都要寫戳記（含 EMPTY）；以戳記欄 `IS NULL` 為條件，重送時零寫入，使 0033 的 F-T1「狀態完全不變」仍然成立。
   - 寫入**不得**放在這個 transaction 之外另開 transaction（VETO-5）。
   - 讀取時點：W-B1 清單的讀取時點（鎖內或鎖外）[風控] 要求由 TA 判定並書面記錄；[TA] 的 C-B1 判定為**鎖內、同一個 conn**，本 ADR 即為該書面記錄。
3. **0033 的 C-7、C-8（加法）**：
   - C-7：回應新增獨立的加法欄位（C-B4），不得混入 `directives`／`pending_directives`；`types.ts` 同步。
   - C-8：**三支 message 結構不變，只附加句子**。RESULT 支、ALREADY_PENDING 支、EMPTY 支各自維持原字面，附加句依 [風控] 的組合順序接在後面（見 Decision 5）。不新增第四支。
4. **不修改既有字面**：`EMERGENCY_EXIT_RESULT`、`EMERGENCY_EXIT_EMPTY`、S1～S9、`MODE_REASON_EMERGENCY`、`FROZEN_NOTE`、`SETTLEMENT_SUMMARY`、`RULE_TEXT[EMERGENCY]` 一字不動（[風控] 第二節之四；[TA] C-B5：store 不 import wording）。「R 系列（新倉進場）暫停」的範圍由新增的附加句承擔。
5. **新增字面（只列識別名；逐字以 `work/reviews/2026-10-31-N168方案裁示-風控.md` 為準，僅放 `wording.py`，風控逐字核可前不得合併）**：

   | [風控] 代號 | 識別名 | 用途（[風控] 標示的位置） |
   |---|---|---|
   | W-B1 | `EMERGENCY_EXIT_PENDING_ENTRY_NOTE` | 出清回應，三支 message 都用 |
   | W-B1p | `EMERGENCY_EXIT_PENDING_ENTRY_PAST_DUE_NOTE` | 出清回應，待成交買單已過預定執行日時（與 S3 同一規則） |
   | W-B2 | `ENTRY_BEFORE_EXIT_LABEL` | 批次標示（面向使用者的語意見檔頭「標註約定」） |
   | W-B2L | `ENTRY_BEFORE_EXIT_NOTE` | 批次列與該批次每一行 S/P/EMERGENCY 指令（`/today` 帳冊與出清回應的 directives），同列、不摺疊、不用 tooltip |
   | W-B3 | `SETTLEMENT_ENTRY_BEFORE_EXIT_NOTE` | 結算：`settlement.warnings` 中緊接在 `SETTLEMENT_SUMMARY` 之後 |
   | W-B6 | `PENDING_ENTRY_FROZEN_NOTE` | `/today`：`warnings` 中緊接在 `FROZEN_NOTE` 之後（對應 [PM] FR-2） |
   | W-B7 | `EMERGENCY_EXIT_LABELED_BATCH_NOTE` | 出清回應與再次出清的回應，放在 S1 或 S2 之後 |

   - W-B4 不另立一句，內容分別併入 W-B3 與 W-B2L；W-B5（ALREADY_PENDING 支）不另立一句，由 W-B1 與 W-B7 承擔。
   - **message 組合順序**（[風控] 第二節之四，接續 N-166 的組合順序，S 系列字面在 [風控 N-166]）：
     - RESULT 支：RESULT＋［S2］＋［S3］＋［W-B7］＋［W-B1］＋［W-B1p］＋［S6］
     - ALREADY_PENDING 支：S1＋［S3］＋［W-B7］＋［W-B1］＋［W-B1p］＋［S6］
     - EMPTY 支：EMPTY＋［W-B1］＋［W-B1p］＋［S6］
     - F-c 情境（既有截止日晚於新算值）照樣用 S7 替換凍結子句。
   - 歸屬語：W-B1 列出的是先前已發出的 R 指令狀態，**不觸發** EXIT 類歸屬語（`EXIT_ATTRIBUTION`、S4、S5），也不在出清橫幅另掛規則歸屬語；EMPTY 支的歸屬語維持 None。N-166 裁示中「message 有描述任何指令就渲染歸屬語」的條件限於 EMERGENCY 指令（[風控]「書面紀錄」；釐清範圍只限 N-168）。
   - 面向使用者的字面限制（摘自 [風控] 第二節之三，逐條內容以該文件為準）：W 系列不得含該文件列出的禁用詞與「你已買進」類說法，且須含「本系統不下單」；已成交與未成交兩種可能要對稱陳述；不得談再出清的代價；再出清的路徑只准寫「可再次提交全部出清」。
6. **B-2b 列為永久紅線**（CEO #80，2026-10-31）：凡使用者未在**該次操作**中提交出清的 EMERGENCY 指令，一律禁止；系統不得未經使用者提交而自動產生 EMERGENCY 賣單。重開的唯一途徑是 CEO 修改豁免框架，並經新一輪風控審查（[決策包] 第 96 行）。即使將來有方案 D，正確路徑仍是由使用者自己再次出清（[風控]）。對應實作約束：C-B10、T-B13。
7. **排序與分支**（[決策包] #79；[風控] 第四節之 3；[TA] 排序）：
   - N-168 **排在 N-166 之後**，且**要在 N-166 合併後才合併**（[風控]：W-B7 與 W-B1 接在 S1、S2 的組合順序上）。
   - N-168 走**獨立分支**，不得併入 N-166 的同一分支或同一 PR（VETO-4）；N-168 的出清側改動從 N-166 合併後的線另開分支。
8. **字面規則（風控閘門）**：新字面僅放 `wording.py`，風控逐字核可前不得合併；`wording.py` 之外不得出現 W 系列的實際文字；[風控] 的「逐條意見」中標 required 的項目，qa-reviewer 列為 BLOCKING。
9. **前置條件：F5（N-172）**（[追蹤清單] N-168 補2）：**F5 的修法定調前，N-168 不開工實作。** 見 Consequences「已知風險」。
10. **出清確認面板不動**（[風控] CEO-3 建議 (a)；[決策包] 第 100 行 coordinator 定案「N-168 風控 CEO-3 … 維持面板不動」，**CEO 可推翻**）。若 CEO 日後要求事前揭露，條件見 [風控] 第二節之七，且須回審。
11. **實作與測試約束**：以附錄 B（VETO-1～VETO-5）、附錄 C（C-B1～C-B11）、附錄 D（T-B1～T-B16）為準。

## Consequences（後果）

- **好處**：
  - 延續全系統既有的帳冊假設（依預定執行日開盤價在帳冊判定、實際成交以券商回報為準），符合 R10；出口不動，EX-2、EX-3 沒有新風險（[風控]、[PM]）。
  - 不新增指令生命週期狀態（[TA] 偏 B-2a 的理由之一）。
  - 每列有明確的落檔事實，標示在凍結結束後仍存在；重送時要帶出的揭露可以直接查到（[TA]）。
  - 重送時零寫入（以 `IS NULL` 為條件），與 0033 的冪等一致（[TA] Q5）。
- **代價與壞處**（[TA] 草案 Consequences、Q1、Q4）：
  - 需遷移兩欄（`playbook_directives` 一欄戳記、`playbook_batches` 一欄標示，皆 nullable TEXT，經 `_MIGRATIONS` 加入）。
  - **不回填**：既有 DB 的舊批次無法補標示，因為沒有凍結歷史可依據。
  - **回滾會清掉標示**：若部署回滾到舊碼，舊的 `save_batch`（整列 `INSERT OR REPLACE`）會把標示清掉。
  - **最大的實作陷阱**：`save_batch` 是整列 `INSERT OR REPLACE`，新批次欄位必須同步加進 `_BATCH_COLUMNS`、`_row_to_batch`、`save_batch`、`BatchState` 四處；漏掉任何一處，`roll_peak_closes` 每天都會把標示洗回 NULL（見 C-B7、T-B4）。
  - **可能出現幻影批次**：U-B（使用者未下單）情境下，結算仍會記為持有並扣帳冊現金；幻影批次的股數會被計入末批的股數計算（`engine.py:177`），扣過的現金也會影響鐵律①的計算。收回方式是使用者再次提交全部出清，這會延長凍結期（沿用 0033 的 C-5 max 規則；[風控] CEO-1 (a) 估計約延長 1 個交易日，[PM] R-1／開放問題 2 估計一到兩個交易日，兩處估計不一致，本 ADR 不採信任一數字）。
  - 凍結結束後的行為（[TA] Q4）：成交的批次 Y 轉 open，R 前進到 Y+1，不重複 Y；MISSED 則 `missed_count+1`、Y 仍是 `planned`，凍結後依 E-2 重試，與現況一致；一直沒結算（沒抓到開盤價）時，凍結後 R 會再替 Y 寫一筆，這是 F5 的變體。
- **已知風險**：
  - **F5（N-172；[TA] 讀碼判定，未執行，建議 medium-high；[追蹤清單] 列 P1（建議））**：排程日（週二、四）重複呼叫 `GET /today`，會替同一個 `planned` 批次重複寫入 R1 買單；T+1 結算時現金被重複扣款、股數卻只被覆寫成一次的量。證據鏈（[TA] 的 F5 證據）：`GET /today` 每次都呼叫 `evaluate_today`（`api/playbook.py:405-422`）；`evaluate_today`（`service.py:614-685`）沒有當日去重；週二結算排除了週三才執行的買單（`store.py:853-855`），批次仍是 `planned`，R1 再次挑到同一批次（`engine.py:699-711`、`:952-958`）；週三結算時兩列都成交（`store.py:930-941`）；現有測試只在週三重跑（`tests/test_playbook_settlement.py:178-193`），未覆蓋此情境。**待 qa-automation 重現**（尚未重現）。
    - 對本 ADR 的影響：「待成交 R 買單」可能出現同一個 (symbol, batch_no) 有多列；W 系列揭露時的股數加總要怎麼算，**必須依 F5 的處置決定**（[TA] Q3），本 ADR 不預設。
    - [TA] 判斷：F5 的修法（例如引擎略過已有待成交買單的批次）會改變 R 的行為，最好在 N-168 build 之前定調。
    - **因此本 ADR 的前置條件是：F5 修法定調前，N-168 不開工實作**（Decision 9）。
  - **claim／settle 窗口（0033 附錄 D 的 F2、N-169）**：claim 與 settle 分屬兩個 transaction，中間有窗口。若出清剛好落在這個窗口，買單已被 claim、批次仍是 `planned`，本 ADR 抓不到這筆，結果是漏標（[TA] Q5 殘留風險）。本 ADR 不處理。
  - **R10 無法觀測**：系統無從得知使用者是否已在券商下單，也無法代為處理使用者在券商端的委託；這是 B-2a 的前提而非可修的缺陷，由揭露字面承擔。
  - 既有 DB 若在 0033 落地前已有重複資料，不在本 ADR 處理範圍（沿用 0033）。
- **被約束**：
  - 禁止 B-2b（永久紅線，Decision 6）。
  - 禁止以「讀取時比較日期」或「結算時看是否在凍結期」推導標示（VETO-1）。
  - 禁止把待成交 R 買單併入 C-4 覆蓋集合或放進 `directives`／`pending_directives`（VETO-2）。
  - 禁止併入 N-166 的分支或 PR（VETO-4）；出清時的寫入禁止在 C-1 的 `BEGIN IMMEDIATE` 之外另開 transaction（VETO-5）。
  - R、S、P 的引擎邏輯不改（C-B11）。
  - 若日後風控要求 message 新增第四支：改為另立取代 0033 的 ADR（見檔頭）。

## 待決

- CEO 核可方案與永久紅線：**已裁**（#79、#80，2026-10-31）。
- **F5（N-172）定調**：qa-automation 重現、tech-architect 與 dev-lead 決定修法；定調前 N-168 不開工實作。
- **N-168a 是否可先行平行開發**：[TA] 建議允許 B-2a 的 schema、settle 複製戳記、`BatchSnapshot`、`/today` 欄位等部分在 N-166 合併前先做（稱 N-168a，測試時直接 seed 已打戳記的列），該項列在 [TA] 的「需 CEO 裁示」第 2 點；但 [決策包] #79 未載入此項，且 [追蹤清單] N-168 補2 的前置條件是 F5 定調前不開工實作。**本 ADR 不採認 N-168a 可先行，待 CEO 另行裁示。**
- 風控：W-B1、W-B1p、W-B2、W-B2L、W-B3、W-B6、W-B7 已逐字定稿於 [風控]；合併前仍須經逐字核可紀錄（[PM] AC-11）；[風控] 要求 W-B2、W-B2L 排版容不下時一律回審，不得縮寫或截斷。
- product-manager：依 [TA] 兩處更正與 [風控] 的 required 項，修訂 PRD 總覽表與 AC（含 [風控] 列出的新增 AC、R-1 補寫 U-B 實害、方案 C 描述中的催促用語不得進入任何字面）。
- dev-lead：N-166 合併且 F5 定調後，依附錄 C、附錄 D 實作；qa-reviewer 把 [風控] 逐條意見的 required 項列為 BLOCKING。
- 後續追蹤（不併入 N-168；[追蹤清單]）：N-173（方案 D 使用者回報成交）、N-174（防守模式或 S3 凍結模式下，前一排程日已產生、未結算的 R 買單仍會次日結算，與 `FROZEN_NOTE` 矛盾，讀碼推定、待 tech-architect 查證）。
- 落檔後待 coordinator 處理：commit、ADR 索引（目前 `docs/adr/` 下沒有索引檔）同步。ADR-0033 不改（含不加指向本 ADR 的註記，ADR-0001 禁止原地改寫已生效 ADR）；若要在 0033 留指標，須另案由 CEO 與 tech-architect 決定。本任務只新增本檔，未改其他檔案。

---

## 附錄 A：[TA] 列出的相關檔案

路徑前綴 `/home/user/AICompany/`：

- `work/prd/2026-10-31-N168出清後待結算R買單-方案比較.md`
- `docs/adr/0033-stock-desk-EMERGENCY_EXIT重複呼叫的覆蓋判定式冪等.md`
- `docs/adr/0001-record-architecture-decisions.md`
- `work/reviews/2026-10-31-N166新字面與延長凍結揭露-風控.md`
- `apps/stock-desk/backend/app/playbook/{store,service,engine,models}.py`
- `apps/stock-desk/backend/app/api/playbook.py`
- `apps/stock-desk/backend/app/data/{sqlite_util,calendar}.py`
- `apps/stock-desk/backend/tests/test_playbook_settlement.py`
- `apps/stock-desk/frontend/app/lib/{types,playbookView,queries}.ts`

## 附錄 B：架構否決（VETO-1～VETO-5）

逐條轉錄自 [TA]「本次結論」。

- **VETO-1**：不得用「讀取時比較 `emergency_until`／批次日期／出清日」來推導標示；也不得在結算時用「as_of 是否落在凍結期」來判定。
- **VETO-2**：待成交 R 買單不得併入 C-4 的覆蓋集合，也不得放進 `directives` 或 `pending_directives` 欄位；transaction 內不得呼叫 `store.pending_directives(...)`。
- **VETO-3（僅 A 案；A 案未採，記錄備查）**：撤回不得用 `missed` 狀態表示，不得經過 `store.settle()`，也不得刪除指令列（違反 R16 留存）。
- **VETO-4**：N-168 不得併入 N-166 的同一分支或同一 PR；這違反 ADR-0033 附錄 D 的 F1「另開追蹤，不併入 N-166」。
- **VETO-5**：N-168 在出清時的寫入，不得放在 N-166 那個 `BEGIN IMMEDIATE` 之外另開 transaction；這違反 C-1。

## 附錄 C：B-2a 約束清單（C-B1～C-B11，交 dev-lead，qa-reviewer 可逐條檢查）

逐條轉錄自 [TA]（標「粗估」）。行號為 [TA] 快照。

- **C-B1**：待成交買單依 Q3 的條件（`action='buy' AND settled=0 AND status='pending'`），在鎖內用同一個 conn 讀取。
- **C-B2**：覆蓋查詢必須含 `action='sell'`。買單不參與覆蓋，也不參與三支分支的選擇。
- **C-B3**：戳記在 C-1 的 transaction 內寫入，三支分支都要寫（含 EMPTY）。用 `WHERE 戳記 IS NULL`，戳記值為出清的 as_of。
- **C-B4**：回應新增一個加法欄位，不得混入 `directives`／`pending_directives`。`types.ts` 同步。
- **C-B5**：message 只能附加句子，不改 `EMERGENCY_EXIT_RESULT`／`EMERGENCY_EXIT_EMPTY`（`wording.py:326-337`），也不改已核可的 S1。store 不 import wording。
- **C-B6**：`settle()` 處理 buy 成交時，把戳記複製到批次標示。MISSED 不加標示。`settle_pending`／`settle_directive` 不加模式判斷。
- **C-B7**：兩個 nullable 欄位經 `_MIGRATIONS` 加入，不回填。批次欄位必須貫穿 `BatchState`、`_BATCH_COLUMNS`、`_row_to_batch`、`save_batch`。
- **C-B8**：`BatchSnapshot`（`models.py:361-375`）帶出標示。engine 只照抄，不做判斷。
- **C-B9**：`/today` 列出「已打戳記且尚未結算」的買單，必須在 `settle_pending` 之後讀取。
- **C-B10**：不得自動替帶標示的批次產生 EMERGENCY 賣單（排除 B-2b）。
- **C-B11**：R、S、P 的引擎邏輯不改。

[風控] 逐條意見（required）另補充的要求，與上列不重複者：標示判定依 D6、以落檔事實判定，持續到 closed，只有 MISSED 的買單不加標示；前端 W-B2、W-B2L 同列顯示，不摺疊、不用 tooltip，排版容不下時回審。

## 附錄 D：B-2a 測試清單（T-B1～T-B16，交 dev-lead）

逐條轉錄自 [TA]（標「粗估」）。

- **T-B1**：EMPTY 分支。只有 Y 的待成交買單，出清後該列被打戳記、出現在新欄位，零賣單。
- **T-B2**：RESULT 分支。只替 X 寫賣單，Y 被列出，覆蓋集合不含買單。
- **T-B3**：同一天重送。trace 中沒有 INSERT 也沒有 UPDATE，回 ALREADY_PENDING，清單仍在。
- **T-B4**：結算成交後 Y 為 open 並帶標示。標示要在以下動作後都還在：`roll_peak_closes`、再跑一次 `evaluate_today`、建新的 store 實例。
- **T-B5**：MISSED 情境。不加標示，`missed_count+1`。
- **T-B6**：超過 until 才結算，仍有標示。這條用來證明 L2 的漏洞已封住。
- **T-B7**：出清時已過期的待成交買單也會被打戳記。
- **T-B8**：凍結結束後才產生的買單、出清前就已結算的買單，都不加標示。
- **T-B9**：Y 轉 open 後再出清（AC-7、F-T2），恰好替 Y 寫一列。
- **T-B10**：擴充 T-1／T-2。每一列只被打一次戳記。
- **T-B11**：擴充 T-5。戳記會一起回滾。
- **T-B12**：舊 DB 遷移與競態，比照 `test_schema_migration_race.py`。
- **T-B13**：凍結期間 Y 轉 open 後，沒有任何自動產生的 EMERGENCY 賣單。
- **T-B14**：`/today` 在結算前列出、結算後移除。
- **T-B15**：凍結後第一個排程日，R 處理的是 Y+1。
- **T-B16**：守門測試，確認只有 R1 會產生 buy（[TA] Q3：目前唯一會產生 buy 的地方是 `engine.py:952-958`）。

與 0033 附錄 B 的關係（[TA] Q5）：0033 的 T-3 原本的斷言要擴充，加上「也沒有任何 UPDATE」；T-5 原子性要涵蓋戳記的回滾；0033 的 T-1～T-6、F-T1～F-T6 其餘不變。

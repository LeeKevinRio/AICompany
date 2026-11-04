# ADR-0035 補充四釐清二（SEAM 常駐後的合法差異、E-11 共用面）

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

釐清二寫好了，全文在第二段 B，可以直接貼到補充四檔末。要點如下：

1. **golden 凍結，不得重錄。** `pre_seam_responses.json` 以 `5c2d3e1` 的內容為準，逐位元凍結。T2 會加一條 sha256 釘選。合法的差異改登記到 `tests/golden/seam/approved/<擁有者>.json`，一個擁有者一個檔。登記規則：
   - 每筆差異要寫明 `before`、`after`，以及依據和核准出處；
   - T2 先把這些差異套到 golden 上，再和實際回應做完全比對；
   - 不准用萬用字元，不准遮蔽欄位，不准把既有鍵當成新增鍵略過；
   - message 只准附加（對應 C-B5）。
2. **核准權責。**
   - 依據只能是已定稿的 ADR 條文或風控的逐字定稿。
   - N-168 在 golden 上的 5 筆差異（D1～D5），由本釐清預先核准類別；精確值由 qa 逐字核對，字面另以風控合併前的逐字核可為準。
   - 清單以外的差異，PR 先停住，由我書面逐筆核准。屬於移除、或會改變使用者既有揭露的，另需風控書面確認。
   - 不需要 CEO 裁示。
3. **規格缺口比我預告的大。** 除了 T2，以下三處也是「切面期斷言」，描述的是 stub 狀態，N-171-A 和 N-168 一填入資料就會轉紅：
   - T1 的「三個清單為 `[]`」；
   - T4 最後一行的 `read == InFlightRead(...)`；
   - T5 的「note 為 None」。

   其中 QB-8 要求 T4、T5 保持綠燈。所以釐清二把斷言分成兩類：不變式斷言常駐、零改動；切面期斷言只能由擁有者依登記調整。**N-171-A 已經開工，一填 `pending_exit_directives`，T1、T4 就會紅。dev-lead 不要自行改這兩個測試**，要等 E-10 的機制 PR，或依 E-10 第 3 點以先行建立者身分處理。
4. **這套規則對 N-171-A、N-182 都適用。**
   - N-171-A 的差異清單必須為空，只登記新增鍵與 `filled` 項目。
   - N-182 不用建登記檔，T1、T2、T4、T5 都不改。
   - N-182 上 T2 仍綠，是因為它的行為只對「批次已非 planned 的待成交買單」生效，而 golden 的 9 個回應裡一列都沒有。所以這個綠燈只證明 N-182 沒有外溢到 golden 情境，不證明 N-182 正確，正確性要靠它自己的測試檔。
5. **N-168 和 N-171-A 並行時，新找到 3 個擁有權衝突點**，都已寫進 E-11 並列入 QB-13：
   - `_read_exit_state`／`EmergencyExitState` 沒有擁有者，兩邊都要碰；
   - N-171-A 要從 `plan_emergency_exit` 抽出 `classify_exit_batches`，N-168 同時在改出清路徑；
   - N-171 各行的 W-B2L 必須只有一個來源。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### A. 方案比較：golden 常駐之後如何容納合法差異

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (a) 每個 PR 在新程式上重錄 golden | 最省事 | T2 變成自己比自己；SEAM-T8 的「缺新鍵舊回應」fixture 會失效；並行分支在同一份 796 行 JSON 上衝突 | 夾帶的非預期差異看不出來 | **VETO** |
| (b) 從比對中遮蔽會變的欄位（例如整個 `warnings`） | 簡單 | 遮蔽範圍大於實際差異，等於拆掉守門 | 其他分支在同一欄位的回歸漏掉 | 否決 |
| (c) 切面合併後就撤掉 T2 | 沒有衝突 | 並行期間失去跨分支回歸守門，而並行正是切面存在的理由 | — | 否決 |
| (d) golden 凍結，加上依擁有者分檔的「核准差異登記」，逐條寫明 before／after | 每筆差異都可以追到依據；用不到的差異會讓 T2 轉紅；各寫各的檔，不衝突 | 需要一次 test-only 的機制改寫 | 登記檔被濫用，由 QB-12 檢查 | **採用** |
| (e) 每個分支各自複製一份 golden | 互不干擾 | 基準分裂，合併後不知道以哪份為準 | — | 否決 |

#### B. 釐清二全文（貼在補充四檔末、釐清一之後）

```
## 釐清二（tech-architect 2026-11-04，SEAM 守門測試常駐後的合法行為差異）

- 性質：釐清 S-4（SEAM-T1、T2、T4、T5）與 S-7，並依 S-3 補定兩個未列入擁有權的共用面（E-11）。不改任何固定項，不改 S-6 判準，不改 golden。
- 依據：`work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md` 第二段 D 的規格缺口預告；`work/reviews/2026-11-04-切面審查-qa-reviewer.md` 對 golden 錄製來源的意見；ADR-0034 補充一、補充二（`work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md`）；ADR-0039 v2 與補充一。
- 程式位置：2026-11-04 工作樹 `product/stock-desk`（含切面合併 `5c2d3e1`、出清畫面包、`d7e1756`；不含 N-182），請以內容定位。

### E-4 斷言分類
1. SEAM 測試裡的斷言分成兩類：
 - (a) 不變式斷言：常駐，之後任何 PR 都不得改。
   - T1：每個今日回應都有 2.2(a) 的三個鍵；`directives`、`pending_directives` 與三個清單的每一列都有 `entry_before_exit_note` 鍵；每個情境都有可檢查的列。
   - T2：去掉時鐘鍵與已登記的新增鍵之後，回應等於「golden 套用已核准差異」的結果（E-6）。
   - T3、T6、T7 全部。
   - T4：只有 `BEGIN`、SELECT、`COMMIT`；讀取失敗時 ROLLBACK 並原樣 raise。
   - T5：AST 掃描；`labeled_batches` 為 KEYWORD_ONLY 且無預設值；`line.line == wording.directive_line(...)`；service 欄位預設為空。
   - T8 全部。
 - (b) 切面期斷言：描述的是 stub 狀態，擁有者填入後必然改變。
   - T1 的「三個清單值為 `[]`」與「`entry_before_exit_note` 為 null」；
   - T2 golden 中既有欄位的值；
   - T4 `test_t4_the_read_is_begin_selects_commit` 最後一行 `read == InFlightRead(exits=PendingExitRead(), entries=EntryBeforeExitRead())`；
   - T5 `test_t5_the_line_is_never_touched_and_the_note_stays_null` 的 note 為 None 斷言。
2. S-4 SEAM-T2 的「既有斷言只准因新增鍵而改」只約束切面 PR 本身。切面之後的 PR：切面期斷言只能依 E-6、E-7 調整，不變式斷言一律零改動。
3. 只改測試裝置、不改斷言與 fixture 的變更不算斷言改動，但要在 PR 說明列出。例如 `d7e1756` 為 SEAM-T8 包上 `ExitReceiptStoreProvider`。
4. 違反本釐清屬 BLOCKING，在該 PR 內修正，不構成 S-6 回退。只有在必須改固定項時，才依 R-3 處理。

### E-5 golden 凍結
1. `apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json` 以 `5c2d3e1` 的內容為準，逐位元凍結：
 - 不得重錄，不得手改，不得增刪情境或回應；
 - 重新格式化、重新排序、改縮排，都算修改。
2. T2 增加一條斷言：golden 的 sha256 等於常數 `GOLDEN_SHA256`。
 - 常數取 `git show 5c2d3e1:<上列路徑>` 的雜湊，在 E-10 的機制 PR 中寫入；
 - 寫入之後不得修改。
3. 理由：
 - golden 是切面前的基準。在改過的程式上重錄，T2 就是自己比自己，夾帶的非預期差異看不出來。
 - SEAM-T8 把它當成「缺新鍵的舊回應」fixture。重錄會帶入新鍵，T8 就失去意義。
 - 並行的分支若各自重錄，會在同一份檔案上衝突，而且無法有意義地解。
 - 錄製來源 `31753cb` 只有在檔案不變時，才能被重新驗證。
4. 需要新情境時，寫在擁有者自己的測試，不加進 golden。
5. 本釐清不授權任何重錄。若真的需要（例如 migration 讓 golden 情境無法重建），PR 先停住，由 tech-architect 另出補充。

### E-6 核准差異登記
1. 位置：`apps/stock-desk/backend/tests/golden/seam/approved/`，一個擁有者一個 JSON 檔：`n168.json`、`n171a.json`，之後 B1、B2 各自加檔。
 - PR 只能改自己的檔。
 - N-182 不建檔。
2. 檔案內容：
 - `owner`。
 - `added_keys`：本案新增的回應鍵。每項含 `key`，以及 `source`（定義它的 ADR 條號）。
 - `filled`：本案填入的切面期項目，可以是：
   - `today_lists`：三個清單中的哪幾個；
   - `note`；
   - `in_flight`：`exits` 或 `entries`。

   每項含 `source`，以及 `test`（以精確值斷言其內容的測試 node id）。
 - `deltas`：既有欄位值的差異。每項含：
   - `id`（例如 `N168-D1`）；
   - `source`：定稿依據，寫 ADR 條號或風控文件加句名；
   - `approval`：E-7 的核准出處；
   - `scenario`、`body`、`path`：`path` 是由鍵與索引組成的陣列；
   - `op`：`replace`、`insert`、`remove` 三選一；
   - `before`：replace、remove 必填，為 golden 在該路徑的原值；
   - `after`：replace、insert 必填，為完整的最終值。
3. T2 的比對步驟：
 1) 確認 golden 的 sha256（E-5 第 2 點）。
 2) 依檔名順序讀入全部登記檔，檢查格式，並確認 `id` 不重複。
 3) 刪除鍵 = 時鐘鍵 ∪ 切面的四個鍵 ∪ 全部的 `added_keys`。`added_keys` 的名稱不得出現在 golden 的任何深度。
 4) 期望值 = golden 的複本，依檔案順序、再依檔內順序套用 `deltas`：
   - replace、remove：當下的值必須等於 `before`；
   - insert：索引不得超過 list 長度；
   - 路徑最後一段是 `message` 時，只准 replace，而且 `after` 必須以 `before` 開頭（ADR-0034 C-B5：只能附加）。
 5) 斷言：實際回應去掉刪除鍵之後，等於期望值。
4. 禁止事項：
 - 萬用字元、正規表示式、謂詞，或任何「忽略此欄」的寫法；
 - 把既有鍵登記成 `added_keys`，藉刪除鍵略過差異；
 - `after` 等於 `before` 的空差異；
 - 不同擁有者的差異落在同一個 list 或同一個葉節點。遇到這種情況，PR 停住，由 tech-architect 裁定；
 - 用整個 list 的 replace 代替逐元素的 insert／remove。差異一律寫在會變動的最小路徑上；字串整條 replace，不做子字串修補。
5. 每筆登記的差異都必然會被用到：用不到的差異會讓期望值與實際回應不符，T2 轉紅。
6. 切面期斷言的調整方式：
 - T1：登記在 `filled` 的清單或 note，不再斷言為 `[]`／null；「鍵存在」照舊斷言。沒有登記的照舊斷言為空。
 - T4：最後一行改成只對沒登記在 `filled.in_flight` 的部分，斷言等於預設值。BEGIN、SELECT、COMMIT 的斷言不動。
 - T5：只有 N-168 可以改 `test_t5_the_line_is_never_touched_and_the_note_stays_null` 的 note 斷言：
   - 改為 W-B2L 規則的期望值；
   - 另加一個「未標示批次的 note 為 None」案例；
   - `line.line` 的斷言一字不動。
 - `filled` 的 `test` 必須在 golden 的同一組情境上，以精確值斷言填入的內容。

### E-7 核准權責
1. 差異的依據只能是已定稿的來源：accepted 或已核可補充的 ADR 條文，或風控的逐字定稿加上它的渲染條件。依據沒有寫到的差異，一律不核准。
2. E-8 列出的差異，由本釐清預先核准類別。
 - `after` 的精確值由 qa-reviewer 對照依據逐字核對。
 - 字面類差異另以風控合併前的逐字核可為準（ADR-0034「合併前仍須經逐字核可紀錄」）。
3. E-8 以外的差異：
 - PR 先停住，dev-lead 送 tech-architect；
 - tech-architect 在 `work/reviews/` 下以書面逐一 `id` 核准，`approval` 欄寫那份檔案的路徑；
 - 屬於 `remove`，或會改變面向使用者既有揭露的，另需 risk-compliance-officer 書面確認。
4. qa-reviewer（含 Codex 第二意見）是每個 PR 的閘門，QB-12 列為 BLOCKING。
5. 不需要 CEO 裁示。差異若與 accepted ADR 衝突，以 ADR 為準並退回，不得以登記差異繞過。

### E-8 N-168 的預先核准清單（依讀碼預測，以實際 diff 為準）
golden 中只有 `after_exit` 情境會被 N-168 改到。這個情境的設定是：
- 批次 1 為 planned，帶一筆 2026-08-12 的 R1 待成交買單；
- 8/11 出清批次 2、3；
- 8/12 結算時，這筆買單成交。

| id | 路徑 | op | 依據 | 內容 |
|---|---|---|---|---|
| N168-D1 | `after_exit.exit.message` | replace | ADR-0034 W-B1；補充二 RESULT 支組合順序 | golden 原文之後附加 W-B1 |
| N168-D2 | `after_exit.exit_repeat.message` | replace | 同上，ALREADY_PENDING 支 | golden 原文之後附加 W-B1 |
| N168-D3 | `after_exit.today.warnings[1]` | remove | 補充二 P4、P5：W-B6 列過的列從 ENTRY 排除，全部被排除時 ENTRY 不渲染 | 移除 `SAME_DAY_EARLIER_ENTRY_NOTE` 那一句 |
| N168-D4 | `after_exit.today.warnings[1]` | insert | ADR-0034 W-B6；補充二 P4（緊接 FROZEN_NOTE） | W-B6 |
| N168-D5 | `after_exit.today_next_day.settlement.warnings[1]` | insert | ADR-0034 W-B3（緊接 SETTLEMENT_SUMMARY） | W-B3 |

- 依序套用 D3、D4 之後，`after_exit.today.warnings` 為 [FROZEN_NOTE, W-B6]。
- 預期不會出現在 golden 中的句子與值：
  - W-B1b、W-B6b：沒有批次已非 planned 的買單；
  - W-B1d：每個批次只有一列；
  - W-B1p：預定執行日沒有過期；
  - W-B2／W-B2L 的非 null 值：golden 中沒有標示批次上的賣出列。

  實際出現上述任何一項，或出現 D1～D5 以外的差異（例如 message 另外附加了 S10、W-B7），都算 E-8 以外，依 E-7 第 3 點處理。
- `added_keys`：`entry_before_exit_on`、`entry_before_exit_label`（ADR-0034 補充一 S-3 第 3 點）。
  - `BatchSnapshot.entry_before_exit_note`，以及出清回應的兩個清單，與切面鍵同名，已經被刪除，不需要登記。
- `filled`：
  - `today_lists` 的 `entry_before_exit_directives`：golden 中，`after_exit.today` 應有批次 1 的那 1 列；
  - `entry_before_exit_blocked_directives` 可登記也可不登記；登記時，`test` 要斷言 golden 中為 `[]`；
  - `in_flight` 的 `entries`；
  - T5 的 note 斷言依 E-6 第 6 點調整。
- authored、unauthored 兩個情境：零差異。

### E-9 適用範圍
1. 本釐清適用於切面之後的每一個 PR。
2. N-171-A：
 - `deltas` 必須為空：N-171-A 只填新鍵（ADR-0039 補充一 T21：`warnings` 與 N-172a 錨點測試不改斷言）。出現任何差異，依 E-7 第 3 點停住。
 - `added_keys`：ADR-0039 Decision 1 的頂層新鍵，目前是 `pending_exit_block`。只登記最外層的鍵，不登記 `rows`、`text`、`notes`、`title`、`lead` 這類內層名稱；例如 `title` 已經出現在 golden 的 `cap1_disclosure` 裡。
 - `filled`：
   - `today_lists` 的 `pending_exit_directives`：golden 中，`after_exit.today` 應有批次 2、3 兩列，`unauthored.today_after_exit` 應有批次 1 一列，其餘今日回應為 `[]`；
   - `in_flight` 的 `exits`。
 - N-171-A 不改 T5。
 - `POST /settle` 改走 `settle_on_request` 之後，SEAM-T6「`POST /settle` 的既有測試不改斷言」照舊適用。若有任何既有斷言要改，依 E-7 第 3 點逐條送核。
3. N-171-B1、B2：比照 N-171-A。
 - B1 登記 `settled_exit_block`；
 - B2 的 B-4 只附加在 EMPTY 支，golden 中沒有 EMPTY 支，預期零差異。
4. N-182：
 - `deltas`、`added_keys`、`filled` 都為空，不建登記檔；T1、T2、T4、T5 零改動。
 - T2 在 N-182 上仍綠，原因是 N-182 的行為只對「批次已非 planned 的待成交買單」生效，而 golden 的 9 個回應中沒有這種列：
   - `after_exit.today` 唯一的買單在批次 1，而批次 1 仍是 planned。所以 ENTRY／A 的排除集合是空的，句子與 golden 相同，W-B6b 也不渲染。
   - `after_exit.today_next_day` 的買單，在同一次呼叫的 `_settle_pending` 中已經成交。`read_in_flight` 在結算之後才執行，讀到時這筆已不是待成交。
   - authored 情境的買單都在 planned 批次上。
   - unauthored 情境沒有買單，N-182 也不在這條路徑上計算（風控 2026-11-04 第 8 點 (b)）。
   - `refused_by_g1` 不進 API。
 - 所以 T2 綠燈只證明 N-182 沒有外溢到 golden 情境，不證明 N-182 正確。N-182 的正確性由 `tests/test_playbook_pending_entry_blocked.py` 負責。
 - N-182 merge product 之後，T2 必須在登記為空的情況下仍綠。若轉紅，不得用登記差異解決，要視為 merge 引入的回歸，先查明原因。

### E-10 機制落地
1. 下列項目以單獨一個 test-only PR 落地：讀取登記檔；依 E-6 改寫 T1、T2、T4；寫入 sha256 釘選。
 - 只動 `tests/test_playbook_today_seam.py`、`tests/seam_helpers.py`，以及 `tests/golden/seam/approved/` 目錄（初始不放任何擁有者檔）；
 - `app/` 零 diff，golden 零 diff。
2. 時點：
 - 在 N-171-A 送 PR 之前合進 product；
 - N-171-A、N-168 merge 含此 PR 的 product 之後，再加自己的登記檔。
3. 若 N-171-A 完成時機制 PR 尚未合併：
 - N-171-A 可以作為先行建立者，把機制放在自己 PR 內一個獨立、只含測試的 commit；
 - N-168 對機制只能加自己的登記檔，不得改寫（比照 E-1 第 3 點）。
4. qa-reviewer 驗收：
 - 登記為空時，T1～T8 全綠，且 T2 的判定和改寫前等價；
 - 變異測試，下列每一項都要讓 T2 轉紅：
   - 暫時改動任一回應的既有欄位值；
   - 登記一筆 `before` 錯誤的差異；
   - 登記一筆空差異；
   - 登記一個和 golden 撞名的 `added_keys`。
 - 變異測試做完要還原，並在交件說明中列出。

### E-11 N-168 與 N-171-A 並行的共用面（補 S-3）
1. `PlaybookStore._read_exit_state`／`EmergencyExitState`：
 - 現況：
   - N-171-A 在 `read_in_flight` 內呼叫它（ADR-0039 Decision 2）；
   - N-168 要在出清鎖內讀待成交買單（C-B1），並帶出批次標示（ADR-0034 補充一 S-3 第 7 點）；
   - B2 之後還要多讀一項；
   - S-3 沒有把它列為任何一方的擁有項。
 - 裁定：列為共用面，不歸任何一方，比照 `BATCH_LEFT_PLANNED_SQL`。
   - 只准加法：可以在 `EmergencyExitState` 加有預設值的欄位；
   - 既有三個查詢的條件與排序不變；
   - 隨 C-B7 經 `_BATCH_SELECT` 增加的批次欄位，不算改條件。
 - N-168 在出清鎖內讀待成交買單的查詢，**不得**放進 `_read_exit_state`。要放在另一個函式，由 `commit_emergency_exit` 用同一個 conn、在同一個 transaction 內呼叫。
   - 理由：放進去的話，N-171 的 `read_in_flight` 會經由 `exits` 帶出 N-168 的買單資料，同一份回應裡的買單就有兩個來源。
 - `/today` 上：N-171 只用 `exits` 的 open 批次與出清列；N-168 的清單只出自 `entries`。
2. `plan_emergency_exit`／`classify_exit_batches`：
 - `classify_exit_batches` 由 N-171-A 抽出，行為零差異（ADR-0039 Decision 3），歸 N-171 擁有。
 - N-168 不得把買單或 W-B1 的邏輯加進 `classify_exit_batches`，也不得加進 `plan_emergency_exit` 的覆蓋與分支判定（C-B2）。
 - N-168 在出清路徑上的改動，限於兩處：
   - `commit_emergency_exit` 內的戳記寫入與買單讀取；
   - `emergency_exit` 在 commit 之後組 message 與 `labeled_batches`。
 - 兩邊在同一段程式上的文字衝突，由後合併的一方解決。出清回應的既有斷言，只准出現 E-8 的 D1、D2。
3. W-B2L 的單一來源：
 - `PendingExitRow` 與群組 B 各行的 `entry_before_exit_note`，只能從 `_lines` 產生的 `DirectiveLine.entry_before_exit_note` 複製（ADR-0039 Decision 9）。
 - `app/` 內，`ENTRY_BEFORE_EXIT_NOTE` 只能在 N-168 的套用規則中被引用，而這個規則只由 `_lines` 呼叫。N-171 不得讀取 `labeled_batches` 自行判斷。
 - 後合併的一方，在 merge 之後補一條整合測試：標示批次上的出清列，在 `pending_exit_directives` 與對應的 `PendingExitRow` 上，帶有相同的 W-B2L。
4. SEAM 登記檔：依 E-6 第 1 點各寫各的檔，不構成衝突。
5. 下列交集已有規則，不是新的衝突點：
 - `_to_response`、`TodayResponse`、`types.ts`：各加各的加法欄位，相鄰行衝突在 merge 時解決（S-3「允許」）；
 - `same_day_warnings`：只有 N-168 會改（ADR-0039 補充一 T21）；N-182 建立的部分受 E-1 約束；
 - `_settle_pending`：只有 N-168 改 warnings（W-B3）；N-171-A 不動（ADR-0039 補充一 S-3 第 3 點）。
6. N-168 內部的同一快照要求：ENTRY 排除 W-B6 列時，用的是同一次 `read_in_flight` 的 `entries` 的 directive id 集合，不得在鎖內另讀戳記（R-4，與 E-2 第 3 點同理）。

### E-12 S-7 增列檢查項
- QB-12：適用於切面之後的每一個 PR，含 N-182、N-171-A／B、N-168 與 E-10 的機制 PR。
 - golden 零 diff：`git diff 5c2d3e1 <merge 後 head> -- apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json` 為空，且 `GOLDEN_SHA256` 未改。
 - PR 只改自己的登記檔。
 - 每筆差異都符合以下各項：
   - 在 E-8 清單內，或附有 E-7 第 3 點的書面核准；
   - `source` 指向已定稿的條文；
   - `after` 與定稿逐字相符，由 qa 用情境的值手算渲染結果核對；
   - message 差異只有附加；
   - `remove` 有明文的移除規則。
 - `added_keys` 都是擁有者 ADR 所定義的回應鍵，只登記最外層，且與 golden 不撞名。
 - `filled` 的每一項都有以精確值斷言內容的測試，而且這些測試在 golden 情境上執行。
 - E-4 第 1 點 (a) 的不變式斷言零 diff：逐行檢查 `tests/test_playbook_today_seam.py` 的 diff。
 - PR 說明逐條列出差異 id、新增鍵、切面期斷言的調整，並與登記檔一一對應。
 - N-182：登記為空；T1、T2、T4、T5 零改動；在 merge 後的 head 上綠燈。
- QB-13：適用於 N-168 與 N-171-A 的 PR。
 - E-11 第 1 點：`_read_exit_state` 既有三個查詢的條件與排序零 diff；N-168 的出清鎖內買單查詢不在 `_read_exit_state` 裡。
 - E-11 第 2 點：`classify_exit_batches` 與 `plan_emergency_exit` 的覆蓋判定沒有讀取買單。
 - E-11 第 3 點：
   - grep `ENTRY_BEFORE_EXIT_NOTE`，在 `app/` 內只出現在 `_lines` 的套用規則中；
   - N-171 各行的 note 只從 `DirectiveLine` 複製；
   - 後合併的一方已補上整合測試。
 - E-11 第 6 點。
```

**ADR-0035 檔頭的補充行**，建議在補充四那一行後面加上：「另見補充四釐清一、釐清二（2026-11-04）」。

#### C. 擁有權評估摘要（N-168 與 N-171-A 並行）

| 衝突點 | 雙方各碰什麼 | 現行規格是否涵蓋 | 裁定 |
|---|---|---|---|
| `_read_exit_state`／`EmergencyExitState` | N-171-A 在 `read_in_flight` 內讀它；N-168 要在出清鎖內讀買單、帶出標示；之後 B2 也要加讀 | 未涵蓋，屬新衝突 | 共用面、只准加法；N-168 的買單查詢不得放進這個函式（E-11 第 1 點） |
| `plan_emergency_exit` | N-171-A 抽出 `classify_exit_batches`；N-168 改出清路徑 | 部分涵蓋（只有 C-B2） | 分類函式歸 N-171；N-168 只改 commit 前後的特定位置（E-11 第 2 點） |
| N-171 各行的 W-B2L | N-171 組出各行；套用規則屬於 N-168 | 涵蓋（ADR-0039 D9），但缺可檢查的守門 | 只准複製；加 grep 守門與整合測試（E-11 第 3 點） |
| SEAM-T1／T4 的切面期斷言 | 兩邊填入資料都會讓它轉紅 | 未涵蓋，屬新衝突 | 依 E-6 分檔登記，加上機制 PR |
| `_to_response`、`types.ts`、`same_day_warnings`、`_settle_pending` | — | 已涵蓋 | 不是新衝突 |

#### D. 對實作的約束
逐條見釐清二的 E-5、E-6、E-10、E-11，qa 依 QB-12、QB-13 逐條檢查。

### 其他部門
本次未參與，屬純評估。需要的經手見第四段。

## 三、驗證

**讀過的文件**
- 補充四全文與釐清一；
- 我在 N-182 解讀點 2、3 的裁示全文；
- N-182 補件交件全文；
- 風控 N-168 P2～P5 裁示全文；
- ADR-0034 檔頭與附錄 C、補充一全文；
- ADR-0039 v2 的 Decision 1～12、補充一 S-1～S-5；
- 切面審查與切面交件中所有提到 golden 的段落。

**讀過的程式**（product 工作樹）
- `tests/test_playbook_today_seam.py` 全檔、`tests/seam_helpers.py` 全檔、`tests/golden/seam/pre_seam_responses.json` 全檔；
- `same_day_helpers.py` 中的 `buy_line`、`hold`、`log_like_before_n172a`；
- `store.py`：`:276-315`（`InFlightRead` 與兩個 stub）、`:1183-1270`（`commit_emergency_exit`、`_read_exit_state`、`read_in_flight`）；
- `service.py`：`:1178-1407`（`evaluate_today`、`emergency_exit`）；
- `api/playbook.py`：`:300-329`（`_lines`）及所有 `_lines` 呼叫點；
- `test_api_playbook.py` 中 `/settle` 的測試與 harness：harness 有呼叫 `confirm_rule_set`，所以 `settle_on_request` 預期不影響這些測試。

**沒有驗證到的事**
- E-8 的 D1～D5 是依風控與 ADR 的渲染條件推導 golden 情境得出的預測。N-168 還沒有程式，以實際 diff 為準；多出或少掉的差異，都依 E-7 第 3 點處理。
- 我看不到 N-182 分支的程式。E-9 第 4 點的「T2 仍綠的原因」，是依 N-182 交件說明、golden 內容（批次 1 的 status 為 planned），以及 product 上 `read_in_flight` 位在 `_settle_pending` 之後推得的。
- 我沒有算 `GOLDEN_SHA256`（沒有執行任何指令），要由機制 PR 從 `5c2d3e1` 的 blob 計算。
- 我沒看到 `d7e1756` 的 diff，「只改測試裝置、不改斷言」是依 coordinator 的說法，請 qa 依 E-4 第 3 點確認。
- 出清畫面包有沒有改到後端回應，我沒有核對。依 coordinator 的說法，合併後只修了 SEAM-T8，推定 T2 在 product 上是綠的。

**本次限制**：沒有執行任何程式或測試，沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案，沒有使用 git。

## 四、下一步

1. **coordinator／tech-writer**：
   - 把第二段 B 的釐清二貼到 `/home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 檔末、釐清一之後；
   - 在 ADR-0035 的檔頭補充行加上「另見補充四釐清一、釐清二（2026-11-04）」。
2. **dev-lead（請 coordinator 立即轉知，N-171-A 已開工）**：
   - 填入 `pending_exit_directives` 之後，T1、T4 會轉紅，不要自行改這兩個測試；
   - 先做 E-10 的 test-only 機制 PR。來不及的話，依 E-10 第 3 點，以先行建立者身分放成獨立 commit；
   - N-171-A 的 `deltas` 必須為空；
   - 實作時遵守 E-11 第 1～3 點。
3. **qa-reviewer**：
   - 把 QB-12、QB-13 列入 N-182 重審（merge product 之後）、機制 PR、N-171-A、N-168 的審查清單；
   - N-182 這次只需查 QB-12 的最後一項，以及 golden 零 diff；
   - 確認 `d7e1756` 只改測試裝置。
4. **N-168 開工時**：以 E-8 為差異基準；字面類差異 D1、D2、D4、D5 由風控在合併前做逐字核可。D3 的移除依據是風控 P4／P5 的明文規則，屬預先核准類別，不需要另外送風控。
5. **CEO**：本次不需要裁示。
6. **待辦提醒**：dev-lead 在 N-182 補件第四段第 3 點問的「結算內兩處 `pending_directives` 算不算 R-4 的在途讀取點」，本次沒有處理，仍待我另行回覆。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-04-N182補件交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md
- /home/user/AICompany/work/reviews/2026-11-01-ADR0034補充一-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-04-ADR0039補充一與N182第8點a-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-04-切面審查-qa-reviewer.md
- /home/user/AICompany/docs/adr/0034-stock-desk-出清時待結算R買單的處置.md
- /home/user/AICompany/docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md
- /home/user/AICompany/apps/stock-desk/backend/tests/test_playbook_today_seam.py
- /home/user/AICompany/apps/stock-desk/backend/tests/seam_helpers.py
- /home/user/AICompany/apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py

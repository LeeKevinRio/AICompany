# N-168 停止點 S1、S2、I3、I5 裁示（附釐清六）

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-168 停止點 S1、S2、I3、I5 裁示，附釐清六

## 一、本次結論

四點都可以放行，條件寫在下方的釐清六（E-23～E-27），可以直接附在補充四檔末。有一點要先更正 dev-lead：**S1 只改第 482 行，CI 不會全綠。**

1. **S1：准改，屬切面期斷言，不算改寫 N-182 建立的部分。但准改範圍是第 482、483 兩行，不是一行。**
   - 第 483 行是 `len(_blocked_notes(second.warnings)) == 1`。`_blocked_notes` 用前綴 `"尚有 "` 篩選，而 W-B6（`PENDING_ENTRY_FROZEN_NOTE`，`wording.py:480`）也是以「尚有 」開頭。
   - 所以第 482 行改好後，第 483 行會算到 2，轉紅。現在沒看到，是因為第 482 行先失敗，第 483 行根本沒執行到。這是讀碼判定，我沒有執行。
2. **S2：照 E-8 末段的字面算是 E-8 以外；本裁示就是書面核准。**
   - 錯在我的預測，不在實作：當時只看了賣出列，漏掉同一情境 8/12 的結算會讓打過戳記的買單成交，批次 1 轉 open 並帶標示。這正是 C-B6、C-B8、補充一 S-3 第 3 點規定的結果。
   - 這三個鍵都在刪除鍵裡，不是 `deltas`，`n168.json` 不改。
   - 因為 T2 看不到這三個鍵，要另補一條測試，在 golden 情境上用精確值斷言（BLOCKING）。
3. **I3：K1 比對合規，而且比用 directive id 更正確。** E-11 第 6 點寫「directive id」是我寫得過度具體，改為 K1。
4. **I5：可以。** E-11 第 3 點「只由 `_lines` 呼叫」和補充一 S-3 第 3 點互相衝突，是我的筆誤，依 S-3 改寫，並同步改 QB-13 的 grep 口徑。

## 二、各部門回報

**tech-architect（本人，唯讀）**：讀了停止點全文、補充四與釐清一～五全文、補充一 S-1～S-4、風控 P2～P5 裁示，以及 worktree `8efacd8` 上的相關程式與測試。依據如下：

- **S1 為什麼是切面期斷言**
  - N-182 自己寫明 W-B6 不在它的範圍：受保護檔的模組 docstring（第 13-14 行）寫「W-B6 and W-B1d are N-168's, not here」，該測試的 docstring（第 463-464 行）寫「W-B6 and W-B1d (N-168) are not part of this change」。
  - 期望值 `[ENTRY, W-B6b]` 成立的前提，是 `same_day_warnings` 的 `entries=()` 還是 stub。
  - 「W-B6 列過的列從 ENTRY 排除」是 P4 寫明「既有規則維持」的規則，早於 N-182。N-168 一填入 W-B6，這個期望值必然改變，性質和 E-4(b) 相同。
  - N-182 建立的部分都沒被動到：`blocked` 的列集合與 `BATCH_LEFT_PLANNED_SQL`、W-B6b 的內容與 K1 去重、`refused_ids` 排除、W-B6b 排在區塊最後，以及 ENTRY 和 A 用 `blocked_keys` 做的排除。
  - 單元層的 `test_the_block_is_placed_after_frozen_note_or_first` 不傳 `entries`，仍然守住 ENTRY → W-B6b 的順序，零改動。
- **I3 為什麼 id 反而會錯**
  - `EvaluationCommit.logged` 是 `list[Directive]`，沒有 id（`store.py:440`）。
  - `logged` 與 `entries` 雖然都是「每個 K1 留最小 id」，但取自不同的母體：`logged` 是預定執行日已記錄的列，`entries` 是打過戳記、仍未結算的列。兩邊選出的 id 可能不同。
  - 用 id 比對時，同一個 K1 可能同時出現在 W-B6 和 ENTRY，違反風控的「互斥」與 K1 去重規則。N-182 的 `blocked_keys` 也是用 K1。
- **I5 實際結構**：`entry_before_exit_note`（`service.py:751`）是唯一的渲染點。呼叫者只有 `_lines`（`api/playbook.py:394`）和 `_labeled_snapshot`（`service.py:782`）。在 `/today` 上，兩者拿到的是同一個 `labeled` tuple（`service.py:1865`、`:1874-1875`），所以同一批次的賣出列和批次列不可能不一致。

**S3～S6 的技術牽連**（字面仍歸風控裁）：

- **S5 有技術牽連。** `test_the_item_template_exists_once` 鎖住三件事：service 裡只有 `_entry_item` 引用 `SAME_DAY_EARLIER_ENTRY_ITEM`；`app/` 裡 `wording.py` 以外沒有其他模組寫出「批買進 {shares} 股」；`same_day_warnings` 恰好呼叫 `_entry_item` 兩次。現在能過，是因為 W-B6 走的是 `_pending_entry_frozen_notes`。風控有三種可能的選擇：
  - (i) 維持原始整數：零影響。
  - (ii) 只有 W-B 系列改用千分位：可以做到，但只能在 `_entry_item` 上加 keyword 參數。不得新增第二個引用此模板的函式，也不得新增同文字的常數。同一頁會出現兩種格式（W-B6 和 W-B6b 相鄰），呈現由風控決定。
  - (iii) 全部統一用千分位：會改變已上線的 ENTRY（N-172a）與 W-B6b（N-182）在 1,000 股以上時的輸出，等於改寫 N-182 建立的部分，要依 E-1 第 4 點停住，另出補充。而且受保護檔的 `_item` helper 印的是原始整數，現有測試的股數都是 666 或 100，全綠也證明不了等價。
- **S3、S6：沒有架構牽連。**
  - S3：golden 的 `today_next_day` 沒有 N2（出清的兩批都有持股），無論怎麼排序都不影響 D5 的路徑。
  - S6：只影響 `_lines` 的 S2 列，改動限在 `entry_before_exit_note` 內；`_labeled_snapshot` 傳入的 `batch_no` 一律是 int。
- **S4：沒有架構牽連。**
- **I11 附帶確認**：`LabeledBatch` 的 docstring 照舊不改。它不是 `#` 註解行，改了會違反 E-15 第 1 點的口徑；而且「until then」本來就是描述過去的狀態。

**應經手但尚未經手**
- risk-compliance-officer：S3～S6，以及 W 系列合併前的逐字核可。S5 請參考上面 (i)～(iii) 的技術代價。
- qa-reviewer（含 Codex）：依 QB-16 審查。
- frontend-engineer：S-4 的 UI 閘門。

**其他部門**：product-manager、devops-sre、data-engineer、art-lead、tech-writer 等，本次未參與（純評估）。

### 釐清六全文（附於補充四檔末）

```
## 釐清六（tech-architect 2026-11-04，回應 `work/reviews/2026-11-04-N168後端停止點-dev-lead.md` S1、S2、I3、I5）

- 性質：釐清釐清一 E-1 第 3 點與 E-3 QB-10、釐清二 E-8、E-11 第 3 點與第 6 點、E-12 QB-13。不改任何固定項，不改 S-6 判準，不改 golden，不授權重錄。
- 依據：ADR-0034 Decision 5（W-B6）、補充一 S-1、S-3 第 3、4 點；風控 `work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md` P4、P5、必改 3、6；N-168 分支 `8efacd8`（讀碼，未執行）。

### E-23 N-182 守門檔中的一處切面期斷言（S1）
1. 判定：`tests/test_playbook_pending_entry_blocked.py::test_the_block_order_in_an_emergency_freeze` 在凍結期的期望值 `[ENTRY, W-B6b]`，是 N-182 在 W-B6 尚為 stub（`same_day_warnings` 的 `entries=()`）時寫下的斷言；該檔模組 docstring 與該測試 docstring 均寫明 W-B6 不在 N-182 範圍內。P4「W-B6 列過的列從 ENTRY 排除」早於 N-182，N-168 填入 W-B6 後此期望值必然改變，性質比照 E-4 第 1 點 (b)。這不算改寫 E-1 第 1 點所列的 N-182 建立項目。
2. 准改範圍：只限這個測試函式，只限下列四處；名稱、fixture、其餘各行與檔內其他測試、helper（`_item`、`_entry`、`_w_b6b`、`_blocked_notes`、`_entry_notes`）、模組 docstring，一律零改動；不新增 helper，不新增 import。
 (a) 第 482 行改為：`assert second.warnings[position + 1 : position + 3] == [w_b6, _w_b6b(blocked)]`，其中 `w_b6 = wording.PENDING_ENTRY_FROZEN_NOTE.format(entry_count=1, entry_items=_item(entry))`，此賦值寫在本函式內。
 (b) 第 483 行改為：`assert _blocked_notes(second.warnings) == [w_b6, _w_b6b(blocked)]`。理由：W-B6 也以「尚有 」開頭，原本的 `len(...) == 1` 在 W-B6 渲染後必然變成 2；改成精確串列相等比原斷言更嚴格。
 (c) 新增一行：`assert _entry_notes(second.warnings) == []`（P4、P5：全部被排除時 ENTRY 不渲染）。
 (d) 該函式的 docstring 可改寫為描述新的期望：凍結期 2330 的 R1 有戳記、批次為 planned，歸 W-B6，因此不進 ENTRY；2454 的列歸 W-B6b；並註明「N-168 依補充四釐清六 E-23 調整」。
 若依 (a)～(c) 實測仍有紅燈，PR 停住送 tech-architect，不得改用其他寫法。
3. 落地：在 N-168 分支上新增一個只改此檔的 `test:` commit，不得 amend、rebase 既有 commit。PR 說明列出：`c5565eb` 上此測試為紅、本 commit 之後轉綠，以及 (a)～(d) 逐條對應。
4. `test_the_block_is_placed_after_frozen_note_or_first` 不傳 `entries`，仍是 ENTRY → W-B6b 順序的守門測試，零改動；它必須維持綠燈。
5. 釐清 E-1 第 3 點「不得讓 ENTRY 的排除改讀 `blocked` 以外的來源」：這句約束的是「批次已非 planned」的排除，該排除仍只用 `blocked`（`blocked_keys`）。ENTRY 對 W-B6 列的排除是 P4 另訂的排除，來源是同一次 `read_in_flight` 的 `entries`（經 `_entry_before_exit_lines` 以 `blocked` 的 id 切分後的 W-B1 類），不違反該句。A 不做 W-B6 排除（P5 只對 ENTRY）。
6. 不構成先例：N-182 守門檔的其他既有斷言，仍依 E-1 第 3、4 點處理。

### E-24 E-8 預測的更正（S2）
1. 判定：`after_exit.today_next_day.snapshot` 中，批次 1 的 `entry_before_exit_on`、`entry_before_exit_label`、`entry_before_exit_note` 為非 null，依 E-8 末段的字面屬 E-8 以外。原因是 E-8 的預測只考慮了賣出列，漏掉同一情境 8/12 的結算讓有戳記的買單成交，批次 1 因此轉為 open 並帶標示（C-B6、C-B8、補充一 S-3 第 3 點）。
2. 本條即 E-7 第 3 點的書面核准。這三個鍵都在刪除鍵內（兩個登記為 `added_keys`，一個是切面鍵），不是 `deltas`，不需要也不得編 id；`n168.json` 不改。新增鍵不是 remove，也不改既有揭露，不需要 E-7 第 3 點的風控另行確認；字面仍以合併前的逐字核可為準。
3. 補位條件（BLOCKING）：T2 不比對刪除鍵，所以在 `tests/test_playbook_entry_before_exit.py` 以 golden 情境（`golden_bodies`）新增一條測試，對 9 個回應逐一斷言：
 (a) 每個 `snapshot` 列的這三個鍵，只有 `after_exit.today_next_day` 的批次 1 為非 null，值以精確值斷言：`entry_before_exit_on` 為出清的 as_of；`entry_before_exit_label` 為 `wording.ENTRY_BEFORE_EXIT_LABEL`；`entry_before_exit_note` 為 `wording.ENTRY_BEFORE_EXIT_NOTE` 以該批次 `entry_date` 渲染的結果。其餘各列各回應一律為 null。
 (b) 每個回應中每一個 `DirectiveLine` 的 `entry_before_exit_note` 為 null（E-8「golden 中沒有標示批次上的賣出列」的預測，以此釘住）。若實測不成立，停住送 tech-architect。
 這條測試不登記進 `filled`：`filled` 的種類由機制固定，N-168 不得擴充機制（E-10 第 3 點、E-13 第 5 點）。在 PR 說明列出它的 node id。
4. E-8「預期不會出現」清單中的「W-B2／W-B2L 的非 null 值」，改讀為「`DirectiveLine.entry_before_exit_note` 的非 null 值」。

### E-25 E-11 第 6 點改寫（I3）
1. 改為：ENTRY 排除 W-B6 列時，以 `store.decision_key`（K1）比對；比對集合只取自同一次 `read_in_flight` 的 `entries`，經 `_entry_before_exit_lines` 得出、且只在 `emergency_frozen` 模式下取用的那份 W-B6 列；不得在鎖內另讀戳記，也不得另寫一份 K1 定義。
2. 理由：`EvaluationCommit.logged` 不帶 id。`logged` 與 `entries` 雖然各自都是每個 K1 留最小 id，但取自不同母體，選出的 id 可能不同；用 id 比對時，同一個 K1 可能同時出現在 W-B6 與 ENTRY，違反必改 3、6。N-182 的 `blocked_keys` 也以 K1 比對。
3. 不得為了改用 id 比對而去改 `EvaluationCommit`。

### E-26 E-11 第 3 點第 2 小點改寫（I5）
1. 改為：`app/` 內，`wording.ENTRY_BEFORE_EXIT_NOTE` 只能在 `service.entry_before_exit_note` 內被引用；該函式的呼叫者恰好兩個：`api.playbook._lines`（賣出列，補充一 S-3 第 4 點）與 `service._labeled_snapshot`（`BatchSnapshot` 批次列，補充一 S-3 第 3 點）。
2. 同一份回應中，兩個呼叫者拿到的 `labeled_batches` 必須是同一個值：`/today` 用的就是寫進 `evaluation.labeled_batches` 的那一個 tuple。出清回應日後若帶批次快照，同樣適用。
3. N-171 的程式（`_pending_exit_lines`、`_pending_exit_block` 等）不得呼叫上列任一函式；`labeled_batches` 只准原樣轉給 `_lines`，各列的 note 只從 `DirectiveLine` 複製。
4. QB-13 的 grep 口徑改為 AST 層級：統計 `app/` 內對 `ENTRY_BEFORE_EXIT_NOTE` 的屬性引用，以及對 `entry_before_exit_note(` 的呼叫點；docstring 與註解不計入。

### E-27 S-7 增列檢查項
- QB-16（N-168 的 PR）：
 - E-23：`git diff <merge base> <head> -- apps/stock-desk/backend/tests/test_playbook_pending_entry_blocked.py` 只含 E-23 第 2 點 (a)～(d)，且在單獨一個 `test:` commit；`test_the_block_is_placed_after_frozen_note_or_first` 零 diff、綠燈。QB-10「既有斷言零改動」以此為唯一例外。
 - E-24 第 3 點的測試存在、在 golden 情境上執行、綠燈；`n168.json` 的 `deltas` 恰好是 D1～D5。
 - E-25：`same_day_warnings` 中 W-B6 的排除集合只取自 `entries`，用 `decision_key` 比對；`evaluate_today` 傳入的 `entries` 與 `blocked` 出自同一個 `in_flight`。
 - E-26 第 1～4 點。
```

## 三、驗證

- 以上全部是讀碼判定，我沒有執行任何測試。最關鍵的預測是「第 482 行改好後，第 483 行會轉紅」，依據是兩句字面都以「尚有 」開頭（`wording.py:384`、`:480`）加上 `_blocked_notes` 的前綴篩選（受保護檔第 113-114 行）。請 dev-lead 在新 commit 上實測確認。
- 我讀過的程式（worktree `8efacd8`）：
  - `service.py`：`:459-801`、`:1047-1065`、`:1690-1890`；
  - `api/playbook.py`：`:355-443`；
  - `store.py`：`:428-451`；
  - `models.py`：`:366-380`；
  - `wording.py`：相關常數；
  - `tests/test_playbook_pending_entry_blocked.py`：`:1-135`、`:440-540`、`:770-847`；
  - `tests/test_playbook_entry_before_exit.py`：7(g)、E-11、SEAM 相關段落；
  - `tests/golden/seam/approved/n168.json` 全文。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。
- **建議 CEO 親自確認**：不需要。本次沒有與 accepted ADR 衝突，也沒有重大成本影響。

## 四、下一步

1. **coordinator**：把上面的釐清六附在 `/home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 檔末，並把原文另存到 `work/reviews/` 下，比照釐清一～五。
2. **dev-lead**：依 E-23 新增一個 `test:` commit（第 482、483 行加 1 行新斷言，docstring 可改），依 E-24 第 3 點補 golden 情境測試，然後重跑完整 CI。若 E-23 實測仍有紅燈，停住回報。之後再等風控裁完 S3～S6，才 push 並送 qa-reviewer。
3. **風控**：裁 S5 時請參考第二段 (i)～(iii) 的技術代價。選 (iii) 要另出補充，因為會改到 N-182 已上線的 W-B6b 輸出。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-04-N168後端停止點-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-01-ADR0034補充一-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-01-N168字面裁示P2至P5-風控.md
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/tests/test_playbook_pending_entry_blocked.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/tests/test_playbook_entry_before_exit.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/tests/golden/seam/approved/n168.json
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/playbook/service.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/playbook/wording.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/api/playbook.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168/apps/stock-desk/backend/app/playbook/store.py

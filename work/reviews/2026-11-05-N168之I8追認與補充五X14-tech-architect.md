# N-168 I8 追認與補充五 X-14 補註

- 審查者：tech-architect
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**I8 的兩處既有斷言改動，我書面追認，可以合併。** 兩處都是 accepted 規則的必然結果，斷言沒有變寬，也不在 E-23 的範圍內或 SEAM 不變式之內。這次追認是單次的，條件見下，不構成先例。

讀碼時還發現一件事：補充五落地時，會讓同一支 schema 測試轉紅。我寫了一段 X-14 補註，請 coordinator 附加到補充五的檔末。

## 二、各部門回報

### tech-architect（本人，唯讀）

**1. `test_playbook_same_day_flip.py::test_entry_note_after_an_emergency_freeze`（:334）：追認。**
- product 上的原版斷言是：`FROZEN_NOTE` 的下一句等於 ENTRY。
- 修改後的斷言：
  - 下一句是 W-B6（`PENDING_ENTRY_FROZEN_NOTE`，以 1 筆、`ONE_BUY_SHARES` 精確渲染）；
  - 新增 `_entry_note(...) not in second.warnings`；
  - `directives == [("R1","buy")]` 零改動。
- 依據：這個情境中，出清會依 ADR-0034 C-B1 替待成交的 R1 打上 L4 戳記，所以 P4／P5 必然把它歸到 W-B6、從 ENTRY 排除。和 E-23 是同一個機制。
- 嚴格度：精確串列位置相等的斷言仍在，另外多了一條排除斷言，沒有變寬。
- 範圍：這個檔不是 N-182 的守門檔，不受 E-1 第 3 點保護，所以不需要走 E-23 的程序。

**2. `test_playbook_exit_idempotency.py::test_the_exit_adds_no_column_table_or_state_key`（:833）：追認。**
- 原版斷言是 `columns == PRE_N166_COLUMNS`。
- 修改後：`PRE_N166_COLUMNS` 本身零 diff；期望值改為「各表原有欄位依序，後面再接 `ADR0034_COLUMNS` 的欄位」。`ADR0034_COLUMNS` 只有兩欄：`playbook_batches.entry_before_exit_on`、`playbook_directives.exit_stamped_on`。
- 和實作一致：分支 `store.py:175-176` 的 `_MIGRATIONS` 正是這兩欄，符合 C-B7「兩個 nullable 欄位經 `_MIGRATIONS` 加入」。
- 不變的部分：表名、索引、state key 的三條斷言零改動，`declared == PRE_N166_STATE_KEYS` 也沒動。
- 嚴格度：仍是逐表的有序串列相等，多出任何第三欄都會轉紅，沒有變寬。

**追認條件（併入 QB-16，BLOCKING）：**
- (a) `git diff <merge base> 5d6056c` 在這兩個檔上，只有上述改動，加上 :334 的 docstring、`ADR0034_COLUMNS` 常數與它的註解。兩檔其他測試零 diff。
- (b) PR 說明逐條列出 I8 的兩處，並引用本追認。
- (c) 可選：:833 的 docstring「schema 與 N-166 之前相同」可以改成「N-166 之前的 schema 加上 ADR-0034 C-B7 的兩欄」，只改註解。

**3. 補充五 X-14 補註（請附加到 `work/reviews/2026-11-04-ADR0035補充五-tech-architect.md` 檔末）：**

```
## X-14 補註：對 `test_the_exit_adds_no_column_table_or_state_key` 的連動（2026-11-04）
1. X-4 新增的 `settled_after_id` 欄位與 `STATE_SETTLED_AFTER_ID_FLOOR`，會讓這支測試的欄位串列、`after <= PRE_N166_STATE_KEYS`、`declared == PRE_N166_STATE_KEYS` 三條斷言轉紅。這些新增與 ADR-0033 C-9 無關：C-9 管的是出清路徑不儲存 mode_reason 與旗標；本補充的欄位與鍵不由出清寫入。
2. 准改範圍：比照 N-168 的 `ADR0034_COLUMNS`，新增具名常數，內容為：`playbook_directives` 末尾多 `settled_after_id`，state key 多 floor 鍵。三條斷言的期望值改為「既有期望 ∪ 本常數」，仍用精確相等；`PRE_N166_*` 與其他斷言零 diff。放在 N-188 PR 的單獨一個 `test:` commit，PR 說明列出。
3. 併入 QB-18.7 檢查。
```

### 其他部門
本次未參與。

## 三、驗證
- 讀過的程式：
  - worktree `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n168fe/apps/stock-desk/backend/tests/test_playbook_same_day_flip.py:290-360`；
  - 同一 worktree 的 `tests/test_playbook_exit_idempotency.py:700-866`；
  - 同一 worktree 的 `app/playbook/store.py`（grep `_MIGRATIONS` 那兩欄）；
  - product 對應的兩個檔（`/home/user/AICompany/apps/stock-desk/backend/tests/test_playbook_same_day_flip.py:326-355`、`test_playbook_exit_idempotency.py:700-855`），用來比對改動前後。
- 讀過的文件：
  - `/home/user/AICompany/work/reviews/2026-11-04-N168後端審查-qa-reviewer.md` 的 M-2；
  - `/home/user/AICompany/work/reviews/2026-11-04-N168後端停止點-dev-lead.md` 的 I8；
  - ADR-0034 的 C-B7。
- 前後版本是逐行讀檔比對的，我沒有權限跑 `git diff`，所以 commit 邊界（是否只在 `c5565eb`）由 qa-reviewer 依條件 (a) 核對。
- 我沒有執行測試，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 四、下一步
1. **coordinator**：
   - 把 X-14 附加到補充五檔末；
   - 轉知 qa-reviewer：M-2 已追認，條件 (a)(b) 列為 BLOCKING。
2. **dev-lead**：PR 說明列出 I8 的兩處與本追認；D5 改引 E-7 第 2 點／E-8（補充五 X-13）。
3. **qa-reviewer**：依條件 (a) 用 `git diff` 核對兩個檔的 diff 邊界。

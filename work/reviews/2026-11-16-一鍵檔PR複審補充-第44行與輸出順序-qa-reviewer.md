# 真實資料一鍵檔 PR 複審補充（第 44 行與輸出順序）

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論（追加 commit `2a13e613` 後）

**PASS（程式碼審查結論）。BLOCKING_ISSUES=false。** 前一份報告的 7 項判準與 M-1（medium，不阻擋）結論不變。追加的 commit 三項核對全部成立。Codex 仍不可用，維持單家審查。

## 各部門回報：三項核對

1. **第 44 行逐字相同：成立。**
   - `git diff 6dd8794f 2a13e613 --stat` 只有說明文件 1 個檔案、1 行增、1 行減。
   - 詞級 diff 只換了兩處：「那一行英文告訴」改成「開頭的每一行英文都告訴」，並插入「有時會連續出現兩行；……等 coordinator 回覆」整句。
   - 我讀了 worktree 說明文件第 44 行全文，與風控報告 `work/reviews/2026-11-16-操作說明兩行固定句補字-風控.md` 第 19 行的「第 44 行替換後全文」逐字相同。
   - 其他定稿句沒動：R-2 的 `[NOTE]` 句、「不要開啟」句、重啟句都在。第 44 行以外沒有任何異動。
   - 結構上，風控給的是整行全文，本次 diff 只動這一行。

2. **輸出順序符合風控前提：成立。**
   - 腳本 `apps/stock-desk/backend/scripts/pipeline_acceptance_real.py`：
     - 第 938-941 行先 `say(str(stop))`（或第 943 行的 `INTERRUPTED`、第 946 行的 `UNEXPECTED`）。
     - 第 954-957 行在最後一次清理之後才 `say(OUTER_STOP_SENTENCES["copy_not_deleted"])`。
     - 所以原句在前，`copy_not_deleted` 句永遠在後。
     - 已由 `copy_stop_shown` 擋掉重複，只出現一次。
   - 測試 `apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py` 用 `out == [...]` 精確比對順序：
     - `test_b2_copy_changed_and_the_copy_cannot_be_deleted_shows_the_copy_stop`，第 1445 行起，期望 `[copy_changed, copy_not_deleted]`。
     - `test_b2_guard_failed_and_the_copy_cannot_be_deleted_shows_the_copy_stop`，第 1465 行起，期望 `[guard_failed, copy_not_deleted]`。
     - `test_b2_an_interrupt_or_error_before_the_reader_and_a_stuck_copy_shows_the_copy_stop`（參數 `KeyboardInterrupt`、`RuntimeError`），期望 `[INTERRUPTED 或 UNEXPECTED, copy_not_deleted]`。
     - `test_b2_the_copy_stop_is_shown_once_when_the_flow_already_raised_it`，期望只有單句。
   - 以上為讀碼結論，我沒有跑測試。

3. **引用的片段是固定句開頭：成立。** 說明文件引用的 `STOP: the database copy could not be deleted` 是腳本 `OUTER_STOP_SENTENCES["copy_not_deleted"]`（第 334-338 行）的開頭，逐字相同。腳本原句是「STOP: the database copy could not be deleted, so the check did not continue. ...」，引文之後接的是逗號，所以第 44 行的「開頭」說法正確。

### 技術面補充（不影響結論）

- 新句涵蓋的情境是前一份報告的兩行情況。M-1 描述的是「sweep 階段被中斷時，舊複本不會被畫面告知」，這時畫面只有 `INTERRUPTED` 或 `UNEXPECTED` 一行，說明文件沒有對應的指示，仍屬 medium、非阻擋。若 M-1 修了，畫面一樣會是原句加 `copy_not_deleted` 兩行，與第 44 行的描述一致。
- 風控前提「原句在前、`copy_not_deleted` 在後」，之後若有人改動 `main` 的收尾順序，這幾個測試會失敗，因為它們是精確比對。

## 驗證

- 已執行：
  - 兩次 `git diff`（`--stat` 與 `--word-diff`），範圍 `6dd8794f..2a13e613`。
  - 讀風控補字報告全文。
  - 讀 worktree 說明文件第 44 行全文。
  - 對照腳本第 334-338、938-957 行。
- 唯讀權限判準常數：**未觸及**。本次追加的 commit 只動 `work/dispatch/` 下一份文件，不碰 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的增減。
- 沒有做：沒有跑測試、沒有讀 `.env`、沒有碰任何 `*.db`。

## 下一步

1. **coordinator**：此 commit 可併入同一 PR。M-1 是否本輪修，由你決定。
2. 通知 CEO 執行的前提不變：CI 綠燈，加上你自己的確認，因為 `11989 passed` 我未重現。

相關檔案：
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/backend/scripts/pipeline_acceptance_real.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py
- /home/user/AICompany/work/reviews/2026-11-16-操作說明兩行固定句補字-風控.md

BLOCKING_ISSUES=false

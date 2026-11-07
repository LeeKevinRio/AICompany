# N-177a 全案審查

- 審查者：qa-reviewer
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**PASS，BLOCKING_ISSUES=false。** 這是單家審查，Codex 待環境可用時補跑。`codex --version` 回報 command not found，所以 QB-9 目前缺席，不能視為已滿足。

- **覆蓋範圍**：C1～C18、QB-1～QB-12、修訂五六項都逐條對過，沒有 critical 或 high。
- **衝突清單第 6 項**：可以接受，理由與細節見第二節。
- **審查方式**：只讀 diff 與測試碼，沒有自己跑 pytest。CI 數字（9973 passed、2 xfailed、覆蓋率 97.65%）採信交件，沒有獨立重現。
- **合併時機**：N-177a 合入 product 等於 R2 部署，這點只登錄，不在我的判斷範圍。

## 二、各部門回報（審查發現）

### 逐條核對

- **QB-1／C1／C3／C10～C13（零 diff）**
  - `git diff ffe2718 5962b7d --stat` 只有 6 個檔：`store.py` 加 5 個測試檔。
  - `engine.py`、`service.py`、`models.py`、`wording.py`、`app/api`、`app/data`、`app/services`、`tests/golden` 都零 diff。
  - 前端、`scripts/`、`.github/`、`.claude/`、`docs/`、`CLAUDE.md` 相對 `ffe2718` 也沒有 diff。
  - store.py 沒有新增 import，所以 C11 成立。
  - `settle` 回傳型別仍是 None。
- **QB-2／C3 hunk 對照**：每個 hunk 都落在 C3 (a)～(j)。
  - `commit_evaluation`、`claim_directive`、`save_batch`、`set_cash`、`_mark_schedule`、`_init_schema` 都沒動。
  - `get_batch` 與 `_exit_stamp` 只改成委派 `_read_batch`、`_read_exit_stamp`，行為不變。
- **C4／C5（S2 條件與合格批次）**
  - `S2_FILL_ENTRY`、`s2_fill_entry_sql`、`is_s2_fill` 都從同一個 NamedTuple 衍生。
  - `S2_ELIGIBLE_BATCH_SQL` 逐字等於規格，並與 engine 的均成本集合做 parity（T7，500 組，seed 固定）。
- **C6／C7／C8（S2 動帳與稽核表）**
  - `_settle_s2_fill` 在單一連線的 `BEGIN IMMEDIATE` 內完成讀取、分配、現金、稽核寫入，錯誤路徑會檢查 `in_transaction` 再 ROLLBACK。
  - 只寫 `remaining_shares`、`status`、`updated_at`，沒有 `INSERT OR REPLACE`。
  - 現金只在 Σmoved > 0 時動。
  - 稽核表有 CHECK 約束，零移動寫 sentinel 一列。
  - `directive_id` 為 None 時，在任何寫入之前 raise `ValueError`。
- **C14／QB-8（merge 與分支）**
  - `5962b7d` 相對 `c9e6ddb` 的 6 個檔全在 `work/`，與交件所述一致。
  - 這個 merge commit 的訊息漏列兩個 commit（3994a0e、ffe2718），規定不得 amend，交件已更正，我接受。
  - merge 的衝突解法第 1～5 項都對，內容見第 3 項。
- **QB-4／C16（測試清單）**
  - T1～T29 都找到對應測試。
  - T7 是 `Random(177)` 跑 500 組，T27 是 `Random(17727)` 跑 300 組，案例數都達標。
  - T18 依修訂五拆成三項，另外新增 `"executed"` 計數與 ValueError 兩項。
- **QB-5／C9（既有測試改動）**
  - `test_playbook_exit_idempotency.py` 只加 `N177A_TABLES` 並取聯集，`PRE_N166_*` 與 `ADR0034_COLUMNS` 零 diff。
  - 交件列出的 trace 型 `BEGIN IMMEDIATE` 斷言都沒改，且逐條說明了為何指到的仍是原本那個交易。
  - 另外動到偵測工具的一個測試，就是第 6 項。
- **QB-6**：golden 沒有重錄。
- **QB-7／QB-11（PR 說明與效力證明）**：交件的 PR 草稿含 4.7 判定、4.8 關係、R2 位置、偵測閘門與「不含 N-190 程式碼」聲明。

### R-α 鎖內讀改寫（C6／C7／C17／C18）

- **`app/` 內的呼叫點（T19）**：Grep 結果只剩 `save_batch` 與 `set_cash` 的定義與註解，沒有任何呼叫點。
  - 4 處 `save_batch` 呼叫已全部改成欄位化 UPDATE：`roll_peak_closes`、`defer_reset`、`_update_batch`，以及 `settle` 的 missed 區塊。
  - `settle` 的 buy／sell 分支改走 `_settle_batch_line`。
- **`_settle_batch_line`（C7、C18）**
  - 在鎖內讀批次、戳記，更新後做 `_add_cash`。
  - 寫入的欄位與值，對照舊的整列 `save_batch` 路徑逐欄相同。
  - 現金的 delta 為 0 時也寫，和舊行為一致。
  - 批次不存在時不寫，交易空 COMMIT。
- **`_add_cash`（T19 的寫入點限制）**：只被兩個結算 helper 呼叫。
- **C17**
  - `roll_peak_closes`、`defer_reset`、`_update_batch` 都是欄位化 UPDATE，不碰股數與現金，也沒有 `BEGIN IMMEDIATE`。
  - 只有 `_update_batch` 的 `status='skipped'` 例外，另加欄名與 status 的 ValueError 守衛（修訂五第 6 點）。守衛放在 `batch_no is None` 的提早 return 之前，符合 fail-closed。

### 效力證明

- **QB-11（T23、T24）**：成立。把 `_settle_batch_line` 換回舊分支後，4 個案例各自失敗。
  - 失敗現象依序是批次復活、S2 重複動帳、批次復活、S2 入帳被抹掉。
  - 還原後 4 passed，連跑 15 次全綠。
  - 這四種失敗剛好對應 RC-1 的兩種交錯，不是隨機失敗。
- **T21（F8 重現）**：成立。
  - 移除 `is_s2_fill` 區塊後，失敗在第一個斷言 `['S2'] == []`，也就是次日又發 S2。
  - 現金斷言（初值 + 80 × 900）已補上。
  - 交件裡只貼了移除後的失敗輸出，沒有看到現金斷言單獨失效的證明，但修訂五沒要求，不構成問題。

### 衝突清單第 6 項的判定：可以接受

- **改動內容**：`test_the_report_states_whether_the_audit_table_exists` 的 fixture 先 `DROP TABLE playbook_fill_moves`，斷言零 diff。
- **接受理由**
  1. 偵測閘門本來就是在 R2 停機時，對尚未被 N-177a 版本開過的 DB 跑。「表不存在」是閘門實際會遇到的狀態，DROP 是在忠實重現它，不是在弱化測試。
  2. 同檔 481 行有「表存在 → True」的對照測試，兩個分支都有釘住。
  3. 斷言與其他測試沒動。
  4. 沒有削弱任何 C9 的斷言。
  5. 改動只在 tests，不碰 app。
- **替代做法**：不需要。若 tech-architect 偏好，可改成用不經 `PlaybookStore` 的 raw DDL fixture，但那是風格差異，不是必要。
- **登記**：這是 C14 merge 時的語意衝突解法，請 coordinator 在修訂索引補一行「qa 已判定可接受」。

### 各檔問題

#### `apps/stock-desk/backend/app/playbook/store.py`

- **[可維護性][low]** `roll_peak_closes` 的 UPDATE 沒有「只往高寫」的守衛。
  - 它仍然依 `list_batches()` 的過時快照決定要寫哪些批，並無條件把 `peak_close` 設成快照算出的值。
  - 並發下，過時的較低值可能蓋掉較新的較高 `peak_close`。
  - C17 與 T26 沒有要求這點，行為與舊版等價，不擋。
  - 建議 N-177b 或後續單補 `AND (peak_close IS NULL OR peak_close < ?)`。
- **[Edge case][low]** `_update_batch` 的 `status='skipped'` UPDATE 沒有 `WHERE status` 守衛。
  - 過時的 `batch_skipped` effect 理論上可把已 closed 的批改成 skipped。
  - 這屬於 C17 明文的唯一例外，舊行為也一樣，不擋，只登錄。

#### `apps/stock-desk/backend/tests/test_n177_n190_backtrack_probe.py`

- **[可維護性][low]** 該檔模組 docstring 的「The N-177a audit table does not exist in the store yet」已過時。交件已自行揭露並維持零 diff，建議之後順手更新。

## 三、驗證

### 唯讀權限判準常數（每次必填）

未觸及。兩道機械檢查都沒有命中：

1. `git diff ffe2718 5962b7d --name-only -- scripts/validate_agents.py` 沒有輸出。
2. 我無法用 pipe 跑第二道檢查，改用 Grep 在 worktree 的 `apps/` 搜尋 `READONLY_AGENTS|READONLY_ALLOWED_BASH`，0 個檔、0 次出現。diff 只含 `apps/` 與 `work/`，`scripts/`、`.claude/`、`docs/` 都零 diff，所以沒有 shadow 定義，也沒有常數值被改。
3. 異動 agent 名單為空，改了什麼：無；為何改：不適用；ADR：不適用。

### 越界自我檢查

- **Bash 只用了 3 次，都是允許的唯讀用法**
  - `git -C <worktree> diff ffe2718 5962b7d --stat`
  - `git -C <worktree> diff ffe2718 5962b7d -- <path>`，用在 store.py 與兩個既有測試檔
  - `git -C <worktree> diff` 的 `--name-only` 與 `--stat` 變體，用在核對 5962b7d 相對 c9e6ddb 只動 `work/`，以及唯讀判準常數
  - `codex --version`（1 次，回報 command not found）
- **沒有越界**
  - 其餘全用 Read、Grep、Glob。
  - 沒有 pipe、沒有 `cd`、沒有 `&&`。
  - 沒有讀 `.env`，沒有碰 `data/*.db`。
  - 沒有改檔、沒有 staging、沒有 commit。
  - 沒有寫報告檔。

### Codex 第二意見

不可用（`codex` 不在 PATH）。記為：單家審查，Codex 待環境可用時補跑。依 qa-reviewer 紅線，在 Codex 補跑完成之前，這個 PASS 是附條件的。請 coordinator 在環境可用後補跑，並在 PR 合併前確認沒有新的 high 以上問題。

## 四、下一步

1. **coordinator**
   - 在修訂索引補記第 6 項已由 qa 判定可接受。
   - 環境可用時補跑 Codex `/review`，補完才算滿足 QB-9。
   - 登錄「合入 product 等於 R2 部署」，且前置為 ADR-0041 落檔與 CEO 本機跑偵測閘門。
2. **dev-lead（非阻擋，擇期處理）**
   - 更新偵測工具測試檔的過時 docstring。
   - 評估 `roll_peak_closes` 加上只往高寫的守衛。
3. **合入當下**：依 C14 再 merge 一次最新 product 並重跑完整 CI 與 seam，再請 qa 看新增的 merge commit。

相關路徑
- worktree：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n177a`
- 主要審查檔：`apps/stock-desk/backend/app/playbook/store.py`、`apps/stock-desk/backend/tests/test_playbook_s2_fill.py`、`apps/stock-desk/backend/tests/test_playbook_settle_locked.py`
- 交件與規格：`/home/user/AICompany/work/reviews/2026-11-07-N177a修訂五與merge交件-dev-lead.md`、`/home/user/AICompany/work/reviews/2026-11-07-N177a停止點裁示-tech-architect.md`、`/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`

## Verdict
PASS
BLOCKING_ISSUES=false

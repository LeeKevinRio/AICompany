# N-177a 修訂五落實與 merge product 交件

- 審查者：dev-lead
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

修訂五第四節第 1、2 點都已完成。merge 後的 head 跑完整 CI，前後端全綠，T28 綠燈；偵測工具的 S11 測試現在實際執行並 PASSED，不再 skip。分支已 push：`origin/fix/stock-desk-n177a-s2-fill` = `5962b7d3dd76226b1627beb495d216bf9e751dee`，已含 product 最新的 tip `ffe2718`。沒有 merge 進 product。

這次的新 commit，都在 a7481e1 之後新增，沒有 amend 也沒有 rebase：
- `3039ca910e89a44ff09df6c34416db8b65db33a9`：fix，處理修訂五第四節第 1 點的 (1)～(3)。
- `c9e6ddbe63a91dcf1aaaedb481ceed6068dfe739`：依 C14 merge `origin/product/stock-desk`，當時 tip 是 `60b6eec`，已含 N-190 的 3985f4d 與偵測工具的 f589be8。
- `5962b7d`：第二次 merge。
  - 原因：push 前一刻 fetch，發現 product 又多了 4 個只動 `work/` 的 docs commit：e90612c、d64be43、3994a0e、ffe2718。
  - 檔案清單核對過，6 個檔全部在 `work/`；`apps/`、`scripts/`、`.github/`、`.claude/`、`docs/`、`CLAUDE.md` 與 c9e6ddb 相比零 diff，所以 c9e6ddb 的 CI 結果適用。
  - **注意**：這個 merge commit 的訊息只寫到 e90612c、d64be43，漏了 3994a0e、ffe2718。規定不得 amend，所以在這裡更正。
  - 我讀過帶進來的規格「修訂二～六」，裡面沒有新增 N-177a 的程式要求。內容是 N-177b、N-195～N-199、6.9 工具與規格文字，修訂六的 C8 程序適用於 N-196／N-197a。

**有一項 merge 解法沒有預先核可，要 qa／TA 判定。** 偵測工具的測試 `test_the_report_states_whether_the_audit_table_exists`（詳見第三節衝突清單第 6 項）：
- 這個測試假設 `PlaybookStore` 不會建出 `playbook_fill_moves`。N-177a 合入後這個前提不成立，測試會轉紅。
- 我只改了它的 fixture：先 `DROP TABLE playbook_fill_moves`，重現「沒被 N-177a 版本開過的複本」。斷言零 diff。
- 這不在 C9 的 (1)～(3) 內，屬於 C14 下 merge 時的語意衝突解法。我先做了才能讓 CI 全綠，再 push 讓 qa 審。若 TA 不接受這個解法，退回改成另一種做法即可。

## 二、各部門回報

### dev-lead（本人）

**commit 3039ca9（修訂五第四節第 1 點）**
- (1) `s2_fill_entry_sql`：`assert alias.isidentifier()` 改為 `if not alias.isidentifier(): raise ValueError(...)`，字句照第四節第 1 點 (1)。`git diff a7481e1..3039ca9 -- app/` 只有這一處（+2/−1）。
- (2) T18：
  - (a) 改成 `pytest.raises(ValueError, match="identifier")`。
  - (b) `PRE_N177A_S2_VALUES` 的註解改為引用「修訂五 S-1 (a)」，寫明那是黑名單來源紀錄、不屬條件字面、不得改寫成引用 `S2_FILL_ENTRY`。
  - (c) 新增 `test_t18_the_blacklist_source_record_is_the_one_s2_in_apply_effects`：`apply_effects` 內只有一個 `"S2"`，而且就是 `func.attr == "blacklist"` 那個 Call 上 `rule_id` 關鍵字的值。
  - (d) 新增 `test_t18_executed_is_the_entry_and_the_per_batch_gate_only`：`"executed"` 的位置排序後等於 `["S2_FILL_ENTRY", "settle"]`，而且 settle 那一處是 `directive.status != 'executed'`。
  - `test_t18_the_s2_literal_is_stated_once` 拆成三項斷言：
    - 具名清單逐處只出現一次；
    - 含 `'S2'` 的 SQL 字串常數為 0 個；
    - `remaining_shares > 0 AND b.cost IS NOT NULL` 只出現在 `S2_ELIGIBLE_BATCH_SQL`。
- (3) T21：補上 `cash == START_CASH + Decimal(80) * 900`，即初值加上當日開盤價 80 × S2 的 900 股。

**merge c9e6ddb 解的衝突**，見第三節的衝突清單。

### 其他部門
本輪沒有參與。

## 三、驗證

### T21 效力證明（本機；輸出沒有 commit）
做法：暫時刪掉 `settle` 的 `if is_s2_fill(directive):` 整個區塊，共 8 行，到 `return` 為止。
```
E       AssertionError: assert ['S2'] == []
E         
E         Left contains one more item: 'S2'
E         Use -v to get more diff
tests/test_playbook_s2_fill.py:189: AssertionError
FAILED tests/test_playbook_s2_fill.py::test_t21_f8_an_executed_s2_is_not_issued_again_the_next_day
1 failed, 1 warning in 0.15s
```
這次失敗在第一個斷言：次日又發了一張 S2。還原 store.py 後重跑是 `1 passed`。

### merge 時解的衝突清單（c9e6ddb；PR 說明要逐條列出交 qa）
1. **store.py 模組 docstring**（文字衝突）：兩張新表都列入，`playbook_evaluation_marks`（N-190）在前、`playbook_fill_moves` 在後。表數改成「Nine」：product 仍寫「Six」，但實際列出 8 張，加上本表是 9 張。
2. **store.py `_SCHEMA` 末尾**（文字衝突）：N-190 的記號表 DDL 連同註解在前，`playbook_fill_moves` 在後。
3. **`test_playbook_exit_idempotency.py`**（文字衝突）：
   - `ADR0040_TABLES` 與 `N177A_TABLES` 兩個具名常數並存；
   - names 斷言改為 `... | ADR0040_TABLES | N177A_TABLES`；
   - `PRE_N166_*` 與 `ADR0034_COLUMNS` 零 diff。
4. **T18 (iii)**（語意衝突，修訂五已預先核可）：`PRE_N177A_S2_VALUES` 加入 `"SETTLED_SINCE_RULE_IDS"`。這個常數的值與位置零 diff。
5. **`tests/s2_fill_helpers.py::enclosing`**（第 4 項的配套）：`SETTLED_SINCE_RULE_IDS` 是模組層級的 AnnAssign，原本會被歸到 `<module>`。現在一併辨識 AnnAssign 的目標名。
6. **`tests/test_n177_n190_backtrack_probe.py::test_the_report_states_whether_the_audit_table_exists`**（語意衝突，未預先核可）：fixture 加上 `DROP TABLE playbook_fill_moves`，加 4 行；斷言零 diff。該檔模組 docstring 的「The N-177a audit table does not exist in the store yet」已經過時，但我維持零 diff 沒改。
- `origin/product/stock-desk..HEAD` 的程式差異只有 `app/playbook/store.py` 與 tests：`s2_fill_helpers.py`、`test_n177_n190_backtrack_probe.py`（+4）、`test_playbook_exit_idempotency.py`、`test_playbook_s2_fill.py`、`test_playbook_settle_locked.py`。

### CI 數字（merge 後的 head c9e6ddb；5962b7d 的程式樹與它相同）
- 後端（主 venv）：
  - `ruff check .`：All checks passed
  - `ruff format --check .`：497 files already formatted
  - `mypy app tests`：Success: no issues found in 488 source files
  - `pytest --cov=app --cov-fail-under=90`：**9973 passed, 2 xfailed**，0 skipped。總覆蓋率 97.65%，store.py 99%。
  - 34 個 warnings 與上次相同，都是既有測試 `test_api_playbook_cap1_disclosure.py:364` 的連線沒有 close 造成的 ResourceWarning。
- 前端：frontend 與 a7481e1 零 diff，`npm ci` 後跑：
  - typecheck：exit 0
  - vitest：116 files / 3086 tests passed
  - next build：Compiled successfully，exit 0
- 原始輸出：
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/ci_backend_merge.txt`
  - `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/ci_frontend_merge.txt`

### T28 與 S11
- **T28**：在合入 N-190 後的 head c9e6ddb 上單獨重跑：
  - `test_t28_a_today_with_nothing_filled_takes_one_lock` PASSED
  - `test_t28_each_fill_takes_one_lock_of_its_own` PASSED（1+3+1）
- **S11**：`test_s11_the_s2_constants_equal_the_store_once_n177a_defines_them` 已啟用並 **PASSED**，不再 skip。同檔其他 S11 項目也都 PASSED：
  - `test_s11_the_state_and_table_names_the_probe_reads_exist_in_the_store`
  - `test_s11_eligible_batch_query_matches_the_engine_average_cost_parity`
  - 其餘 S11 項目

### 資料安全
- 沒有讀 `.env`，沒有碰 `data/*.db`；測試一律用 `tmp_path`。
- 沒有碰其他 worktree。

## 四、下一步

1. **coordinator**：
   - 依修訂六 1.7 規定，PR head 已變動，ancestry 紀錄要以 `5962b7d` 為準。
   - 請 TA／qa 判定衝突清單第 6 項。
   - 開 PR，用下面的草稿。
2. **qa-reviewer**：
   - 審查依據：C1～C18、QB-1～QB-12 與修訂五，Codex 第二意見；
   - 審 merge commit c9e6ddb 的衝突解法（清單第 1～6 項）；
   - 核對 5962b7d 相對 c9e6ddb 只動 `work/`。
3. **合入 product**：前提是 ADR-0041（proposed）落檔，以及 qa 沒有 BLOCKING。依 coordinator 對 N-195 的定案，N-177a 合入本身就是 R2 部署，所以要先等 CEO 本機跑偵測閘門。合入當下再 merge 一次最新 product，並重跑 CI。

---

### PR 說明草稿

**標題**：fix: S2 成交動帳與成交移動稽核表，並以 R-α 修正並發結算（N-177a）

**摘要**
- `store.settle` 對 S2（`batch_no IS NULL`）原本只標記 schedule，帳冊不減股也不入帳，S2 因此每天重發（F8）。
- 這個 PR 依 ADR-0041（proposed）在 `settle` 新增 S2 分支 `_settle_s2_fill`：
  - 在單一 `BEGIN IMMEDIATE` 內，依 `batch_no` 由小到大分配合格批次；
  - 現金讀改寫；
  - 寫入加法稽核表 `playbook_fill_moves`，零移動時寫 sentinel。
- 依修訂一 R-α：
  - 逐批 buy／sell 改由 `_settle_batch_line` 在鎖內讀改寫；
  - missed 改成單句遞增；
  - `roll_peak_closes`、`defer_reset`、`_update_batch` 改為欄位化 UPDATE；
  - `app/` 內不再有 `save_batch`／`set_cash` 呼叫點。
- 程式只改 `app/playbook/store.py`。service.py、engine.py、models.py、wording.py、`app/api|data|services`、golden 都是零 diff。
- **不含 N-190 的程式碼**。N-190 是依 C14 以 merge 吸收進來，不是本 PR 的改動。

**Commits**
- 73ffbd1：S2 動帳與稽核表
- a7481e1：R-α
- 3039ca9：修訂五
- c9e6ddb：merge product（C14）
- 5962b7d：merge product（docs）

**規格判定與關係（QB-7）**
- 4.7：ADR-0035 Decision 6／6′／N172-C8 判定為 N-172a 的範圍約束，原文不改。ADR-0035 補充六已落檔，A-2 的句子依風控 G 定稿：日後改動 `settle` 的動帳語意或讀寫方式（含並發處理），要另立 ADR 並經風控審查。
- 4.8：
  - ADR-0040 Decision 14 第 2 點的適用對象是 N-190 的 build；
  - N-177a 改動股數與現金的寫入，只在 `settle` 的私有 helper `_settle_s2_fill`、`_settle_batch_line` 內；
  - 不併入 N-190；
  - Decision 14 第 3 點：`_settle_pending` 零 diff。
- **Release 位置：R2**，必須是 N-190 release（R1）的下一個 release，中間不得夾其他功能 release，hotfix 除外（ADR-0040 Decision 13）。N-195 依 coordinator 定案與本 PR 同批。
- **偵測閘門**（C15、風控 A-1 條件 1）：
  - R2 停機時以 `scripts/n177_n190_backtrack_probe.py` 跑最後一次，結果附在 release 紀錄；
  - 大於 0 檔時，CEO 逐檔在 (A)、(B) 之間裁示，沒有預設選項；(B) apply 要在同一次停機內、新版開始服務之前完成；
  - 前提沒滿足時，依 D-1 延後 R2；
  - (D)、(E) 維持 VETO，黑名單預設不改。

**QB-11 效力證明**：把 `_settle_batch_line` 暫時換回修訂前的逐批分支本體（輸出沒有 commit）。
```
E       AssertionError: assert ('open', 60) == ('closed', 0)
tests/test_playbook_settle_locked.py:246: AssertionError
E       assert [(1, 100)] == [(None, 0)]
tests/test_playbook_settle_locked.py:265: AssertionError
E       AssertionError: assert ('open', 60) == ('closed', 0)
tests/test_playbook_settle_locked.py:246: AssertionError
E       AssertionError: assert Decimal('1009000') == (Decimal('1000000') + (Decimal('80') * 100))
tests/test_playbook_settle_locked.py:281: AssertionError
FAILED tests/test_playbook_settle_locked.py::test_t23_a_per_batch_sell_in_its_window_lets_s2_book_after_it[40]
FAILED tests/test_playbook_settle_locked.py::test_t23_a_per_batch_sell_in_its_window_lets_s2_book_after_it[100]
FAILED tests/test_playbook_settle_locked.py::test_t24_s2_in_its_window_lets_the_per_batch_sell_book_after_it[40]
FAILED tests/test_playbook_settle_locked.py::test_t24_s2_in_its_window_lets_the_per_batch_sell_book_after_it[100]
4 failed, 1 warning in 1.30s
```
- 四個失敗依序代表：批次復活、S2 重複動帳、批次復活、S2 入帳被抹掉。
- 還原後 4 passed；T23／T24／T25／T29 連跑 15 次全綠。

**T21 效力證明**：暫時刪掉 `if is_s2_fill(directive):` 區塊後，`assert ['S2'] == []` 失敗（次日又發 S2）；還原後綠燈。

**C9 清單（QB-5、QB-12）**
- (1) `test_playbook_exit_idempotency.py::test_the_exit_adds_no_column_table_or_state_key`：新增 `N177A_TABLES`；names 斷言取聯集；merge 後與 N-190 的 `ADR0040_TABLES` 並存。`PRE_N166_*`、`ADR0034_COLUMNS` 零 diff。
- (2) 沒有任何既有斷言釘住「S2 不動帳」：只做 (1) 時，完整 suite 與 baseline 相同，都是 9539 passed。
- (3) 以 trace 取第一個或唯一一個 `BEGIN IMMEDIATE` 的斷言，全部沒改、原樣綠燈。各處的流程都沒有結算成交，所以斷言指到的仍是原本那個交易：
  - `test_playbook_same_day_race.py::_writes_inside`（T11）：同日重評，沒有到期的下單列；
  - 同檔 T14 的 `(begin,) =`：全新 desk；
  - `test_playbook_exit_race.py:376`、`test_playbook_entry_before_exit.py:546`、`:562`：都是 emergency_exit，不經過 settle。
- merge 時的追加修改：`test_n177_n190_backtrack_probe.py::test_the_report_states_whether_the_audit_table_exists` 的 fixture 加上 DROP，斷言零 diff，交 qa／TA 判定。

**merge c9e6ddb 衝突解法**：同本報告第三節的衝突清單第 1～6 項。

**修訂五索引**（`work/reviews/2026-11-07-N177a停止點裁示-tech-architect.md`）
| # | 位置 | 性質 | 本 PR 落實 |
|---|---|---|---|
| 1 | T18 第 3 點，追加兩點 | 取代、追加：具名例外與 `"executed"` 計數 | `test_t18_the_s2_literal_is_stated_once`、`test_t18_the_blacklist_source_record_is_the_one_s2_in_apply_effects`、`test_t18_executed_is_the_entry_and_the_per_batch_gate_only`、`test_t18_the_entry_and_the_eligible_set_read_word_for_word`（ValueError）；(iii) 在 c9e6ddb |
| 2 | QB-3 第一點 | 取代：限定為條件字面 | 同上 |
| 3 | C4 第二點 | 取代：限定為 S2 成交條件 | `settle` 只用 `is_s2_fill`；通用狀態閘的次數由 T18 釘住 |
| 4 | 4.2 位置條文、程式註解 | 取代：常數分兩段；assert 改成 ValueError | store.py 現狀；3039ca9 |
| 5 | T21 | 取代：自寫版，加現金斷言與效力證明 | 3039ca9；效力證明見上 |
| 6 | 1.3(4)、T26(iv) | 追加：status 守衛 | `_update_batch`；`test_t26_iv_update_batch_refuses_anything_off_its_list` |

C3、C17、QB-7 白名單與 ADR-0041 都不變。

**CI**：見本報告第三節的 CI 數字（後端 9973 passed、2 xfailed，覆蓋率 97.65%；前端 tsc／vitest／next build 全綠）。

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01WfgD8MUGHNitQHywjXPu4E

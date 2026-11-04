# N-171-A 後端 merge product 與補件（5621e94）

- 審查者：dev-lead
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

三則追加指示都處理完了，CI 全綠，分支已 push（head `5621e94`），worktree 已移除。
- **merge product**：最新 product 已併入。N-182 帶來的衝突只有一處 import 行。SEAM-T2 在 n171a 的 deltas 為空時仍綠燈，T4 也是綠燈。N-182 的測試檔零改動。
- **風控解讀點 3、6**：守門照裁示收緊，風控指定的三個變異測試都讓測試轉紅，跑完已還原。
- **釐清四**：E-15 註解 commit 已提交；E-13 (e) 逐 commit 測試紀錄附在下面；E-16 檢查全數通過。

有一件事要知道：我 push 之後，product 又前進了兩個只有文件的 commit（`10e5254` 風控版面裁示、`725ae8b` 前端交件存檔），還沒併進本分支。要併的話要再跑一次完整 CI，請指示。

## 各部門回報（dev-lead）

### merge 與衝突
- **merge commit**：
  - `2fa5c06`：併入 N-182 與 N-183
  - `39d4234`：風控裁示存檔，只有文件
  - `65237ec`：釐清四存檔，只有文件
- **衝突**：只有一處，在 `service.py` 的 `from collections.abc import ...`。N-171-A 加了 `Callable`，N-182 加了 `Set as AbstractSet`，兩行都保留。
- **自動合併的檔案**：`store.py`、`models.py`、`wording.py` 自動合併。N-182 建立的 `EntryBeforeExitRead.blocked`、`BATCH_LEFT_PLANNED_SQL`、`g1_blocked_entries`、`same_day_warnings` 沒有改寫（釐清一 E-1）。
- **N-182 測試檔**：`tests/test_playbook_pending_entry_blocked.py` 與 product 的 diff 為 0 行。
- **golden**：`git diff 5c2d3e1 HEAD -- …/pre_seam_responses.json` 為空。

### 釐清四
- **E-15**：`5621e94` 是只改註解的 `docs:` commit，改的是 `models.py` 與 `types.ts`（`//:`）中 `pending_exit_directives` 的擁有者行，內容照 E-15 第 4 點的建議文字。
  - diff 中非註解的變更行數為 0，名稱、型別、預設值、簽名都沒動。
  - 依 E-15 第 3 點，`api/playbook.py` 的擁有者行和 `types.ts` 的 "No view renders them yet." 沒改。
- **E-16**：以 AST 擷取比對 `5c2d3e1` 與 HEAD。
  - `InFlightRead`、`read_in_flight`、`_read_exit_state`、`EmergencyExitState` 四者逐位元相同。
  - 每條路徑的 `read_in_flight()` 各只呼叫一次（`service.py:1494`、`:1576`）。
  - `_read_pending_exits` 只呼叫 `_read_exit_state`，不讀買單，也不引用 `BATCH_LEFT_PLANNED_SQL`。
  - QB-7：`app/` 內的 `pending_directives(` 只有兩處（`service.py:1033`、`:1201`），都在釐清三白名單上。
  - SEAM-T2、T3、T4 都是綠燈。N-171 與 N-182 的字面掃描沒有互相掃到對方而轉紅。
- **E-13 (e)**：用 detached worktree 跑 `tests/test_playbook_today_seam.py`。已確認 `app`、`tests` 都是從 detached 那份 import，不是主 worktree。

  | commit | 結果 |
  |---|---|
  | `0f02cf3` | 16 passed |
  | `909899b` | 16 passed |
  | `01e99cb` | 32 passed（多出的 16 條是機制本身的登記規則測試） |

  逐條 PASSED 清單：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n171/seam_per_commit.txt`

### 風控解讀點 3、6（commit `c732359`）
- **解讀點 6**
  - `SETTLEMENT_UNAUTHORED_NOTE` 的豁免詞收窄為逐字的「本回應的」，斷言它恰好出現 1 次，剔除後「應」出現 0 次。
  - A-2 修訂版、A-15（`test_a2_and_a15_carry_no_modal_ying_and_get_no_exemption`）和 NB-6 第二版（前後端各一條）都直接斷言「應」為 0，不給豁免。
- **解讀點 3**
  - 11-03 版專有子句改用風控列的三處：「會列出目前尚未結算」「該區塊沒有出現，」「指令結算後也不再列於該區塊」。另外斷言這三處都不在第二版內。
  - 守門比對的是串接後的值：
    - 後端以 AST 取常數，相鄰字串已合併；
    - 前端原始碼先合併 `"…" + "…"` 再比對；
    - 前端檢查 `wording.py` 時，也先合併相鄰字串。
- **風控指定的三個變異測試**（每個都轉紅，做完已還原）
  - M1：在 `wording.py` 新增一個拆成兩行、值等於第一版的常數。後端守門 1 條失敗，前端 1 條失敗。
  - M2：把前端 `body[1]` 改回第一版並拆行。後端 1 條失敗，前端 4 條失敗。
  - M3：把「會列出」＋「目前尚未結算」拆成兩行塞進 `SETTLEMENT_NOTHING_PENDING`。後端 1 條失敗，前端 1 條失敗。
- **`NB6_P1`**：沒有任何測試使用它。已修正抽取腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/n171/extract.py`，改取該列第三欄。重抽的結果等於 `EXIT_RESULT_UNCONFIRMED_STATES`。
- **suggested**：`playbookView.ts` 的 NB-6 註解補了一句，說明第 2 段與 N-171 上線耦合。

### 本輪新增的 commit（接在前次交件之後）
- `2fa5c06` merge：N-182、N-183
- `c732359` test：依風控解讀點 3、6 收緊字面守門
- `39d4234` merge：風控裁示存檔
- `65237ec` merge：釐清四存檔
- `5621e94` docs：E-15 擁有者註解

## 驗證（head `5621e94`）
- **backend**
  - ruff check：All checks passed
  - ruff format --check：483 files already formatted
  - mypy strict：475 source files，沒有錯誤
  - pytest --cov：9383 passed、2 xfailed，覆蓋率 97.57%（門檻 90%）
  - 個別檔案覆蓋率：`api/playbook.py`、`models.py`、`wording.py` 100%，`service.py` 99%，`store.py` 98%
  - 34 個 ResourceWarning：baseline `6d994e3` 加 `--cov` 時也是 34 個，不是本次引入
- **frontend**
  - tsc：exit 0
  - vitest：114 個檔案、2987 tests passed
  - next build：exit 0
- 沒有讀 `.env`，沒有碰 `data/*.db`

## 下一步
1. **coordinator**：決定要不要再 merge product 新增的兩個文件 commit（`10e5254`、`725ae8b`）；若要，我再跑一次完整 CI。之後把 frontend-engineer 的 `feat/stock-desk-pending-exit-block-ui` merge 回本分支。
2. **qa-reviewer（含 Codex）**：審查本分支。重點如下：
   - QB-6、7、12、13、14
   - E-13 (a)～(e)、E-14 (a)～(b)、E-16
   - 風控解讀點 3 (a)(b) 與三個變異測試，以及解讀點 6
3. **風控**：前端與 S-A～S-D 完成後做最終終核。

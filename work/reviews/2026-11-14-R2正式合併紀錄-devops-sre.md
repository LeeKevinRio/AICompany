# R2 正式合併紀錄（N-177a、N-195）

- 審查者：devops-sre
- 日期：2026-11-14
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
已合併並推送。
- F1 = `95f4573ecf9e005b9a354ab31e5fb6deb6bd1f7e`（合入 N-177a）
- F2 = `ef6c6b9707553bf8c8f66ab41f7bf981ffb911be`（合入 N-195）

`origin/product/stock-desk` 由 `7c0615a` 快轉到 F2。9 個步驟全部照做，每一步的輸出都符合預期，中途沒有停下。

## 各部門回報
devops-sre（我）：
- 兩次 `merge --no-ff` 都沒有衝突。
- F1 合入 6 個檔案：`store.py`、`s2_fill_helpers.py`、`test_playbook_s2_fill.py`、`test_playbook_settle_locked.py`，另有 `test_n177_n190_backtrack_probe.py` 與 `test_playbook_exit_idempotency.py` 兩個小改動。
- F2 合入 3 個檔案：`service.py`、`store.py`、`test_playbook_rebalance_no_cash.py`。
- commit message 照你給的全文，附 Co-Authored-By 與 Claude-Session。
- 因為 `-F -` 讀不到 stdin，我改寫成暫存檔再用 `-F`。內容與你給的一致。
- 沒有讀 `.env`，沒有碰 `*.db`，沒有 force push、rebase 或 amend。

## 驗證
1. fetch 後的實際 SHA：
   - `origin/product/stock-desk` = `7c0615a78809b2c1f1a695b4b8a6c070d42b1893`，等於 P。
   - `origin/staging/r2-n177a-n195` = `513c07da0ce7692597858ce17f11db0abd97f422`，等於 M2。
   - `origin/fix/stock-desk-n177a-s2-fill` = `5962b7d3dd76226b1627beb495d216bf9e751dee`，等於 A。
   - `origin/fix/n195-rebalance-no-cash` = `1bdbbdada25a7f3553adeb5d8083c11a4f9a9e3b`，等於 B。
2. `git diff --stat 232ff91… 7c0615a…`：共 10 個檔案、710 行新增，沒有刪除。
   - 路徑是 octal 跳脫的中文檔名，所以我另用 `--name-only -z` 確認，10 個檔案的頂層目錄全部是 `work/`。
3. 兩次 merge 都乾淨完成。
4. parents 全部符合：
   - `F1^1` = `7c0615a78809b2c1f1a695b4b8a6c070d42b1893`，等於 P。
   - `F1^2` = `5962b7d3dd76226b1627beb495d216bf9e751dee`，等於 A。
   - `F2^1` = `95f4573ecf9e005b9a354ab31e5fb6deb6bd1f7e`，等於 F1。
   - `F2^2` = `1bdbbdada25a7f3553adeb5d8083c11a4f9a9e3b`，等於 B。
5. `git diff --quiet M2 F2 -- apps/ .github/ scripts/` 輸出 `exit=0`，程式碼與預備合併完全相同。
6. 在 F2 上的 CI 等效檢查，全部通過：
   - backend：
     - `uv sync --frozen` 成功。
     - `ruff check` 輸出 All checks passed。
     - `ruff format --check` 輸出 502 files already formatted。
     - `mypy app tests` 輸出 Success: no issues found in 491 source files。
     - 完整 pytest：`10241 passed, 2 xfailed, 34 warnings in 991.97s (0:16:31)`，coverage 97.65%（門檻 90%），pytest exit=0。
   - compose-validate：`docker compose config` exit 0；shared database guard 也通過，輸出「backend 與 scheduler 共用 volume stock-desk-data 掛載於 /app/data，STOCK_DESK_DB_PATH 一致；對外 port 皆只綁本機迴環介面」。
   - frontend：
     - `npm ci` 成功，有 npm audit 提示。
     - typecheck 無錯。
     - vitest：116 個測試檔、3086 個測試全過。
     - build 成功。
   - 根目錄 `python scripts/validate_agents.py` 輸出「OK（15 個 agents 全數通過）」。
   - 單獨執行的三組測試：
     - `tests/test_playbook_today_seam.py`：32 個全部 PASSED，沒有 skipped。
     - `test_playbook_settle_locked.py -k t28`：2 個 PASSED，分別是 `test_t28_a_today_with_nothing_filled_takes_one_lock` 與 `test_t28_each_fill_takes_one_lock_of_its_own`。
     - `test_n177_n190_backtrack_probe.py -k s11`：10 個全部 PASSED，沒有 skipped。包含 `test_s11_the_s2_constants_equal_the_store_once_n177a_defines_them`、`test_s11_the_alignment_check_passes_against_the_spec_shaped_constants`、`test_s11_the_marker_selects_exactly_the_index_gap_lines`、`test_n199_t6_s11_parity_with_the_store_g1_condition` 等。
7. 推送前 `git ls-remote origin product/stock-desk` 仍是 `7c0615a78809b2c1f1a695b4b8a6c070d42b1893`。
8. 推送一次成功，沒有重試：`7c0615a..ef6c6b9  ef6c6b9707553bf8c8f66ab41f7bf981ffb911be -> product/stock-desk`。
9. 推送後 `git ls-remote origin product/stock-desk` 為 `ef6c6b9707553bf8c8f66ab41f7bf981ffb911be`，等於 F2。

## 下一步
- 回滾方式：不能 force push，要用新 commit 退回。
  - 執行 `git revert -m 1 ef6c6b9707553bf8c8f66ab41f7bf981ffb911be`，再執行 `git revert -m 1 95f4573ecf9e005b9a354ab31e5fb6deb6bd1f7e`，兩個 revert 作為新 commit 走 fast-forward 推送。
  - 這會退掉 N-195 與 N-177a，保留 `work/` 下的文件。
  - 退回前請先通知 CEO。
- 我沒有查 GitHub 上 push 觸發的 `stock-desk` workflow 結果。需要的話，請 coordinator 或我確認遠端 CI 是否綠燈。
- coordinator 可以解除對 product/stock-desk 的推送凍結。
- 本地分支 `r2-final` 還留在我的 worktree，可以隨時刪除。
- 預備分支 `staging/r2-n177a-n195` 仍在遠端，是否清理請 coordinator 決定。

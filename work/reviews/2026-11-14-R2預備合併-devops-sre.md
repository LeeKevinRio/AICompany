# R2 預備合併（staging）

- 審查者：devops-sre
- 日期：2026-11-14
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
預備合併完成且全綠，但有一項需要你注意（見「驗證」第 8 點）：我推送期間 origin/product/stock-desk 被別人推進了，不是我造成的。
- P  = 232ff9186af8d6a60143e8d597c166c9f4f34248（origin/product/stock-desk，我 fetch 當下）
- M1 = 24459285c923f599b944c3897746a1ad35c78ae4
- M2 = 513c07da0ce7692597858ce17f11db0abd97f422
- 預備分支 `staging/r2-n177a-n195` 已推送，`ls-remote` 等於 M2。
- 兩次 merge 都沒有衝突。
- 我沒有推送 product/stock-desk，沒有 force push、rebase 或 amend。沒有讀 `.env`，沒有碰 `data/*.db`。

## 各部門回報
devops-sre（我）：
- 步驟 1：`origin/fix/stock-desk-n177a-s2-fill` = 5962b7d3dd76226b1627beb495d216bf9e751dee（等於 A）。`origin/fix/n195-rebalance-no-cash` = 1bdbbdada25a7f3553adeb5d8083c11a4f9a9e3b（等於 B）。
- 步驟 3：M1 合入 A，變動 6 個檔案，+2091/-62，`store.py` 與 test 檔自動合併。M2 合入 B，變動 3 個檔案，+470/-13，`store.py` 自動合併。
- 步驟 5：`git diff --stat <P> <M2>` 共 8 個檔案，+2561/-75：
  - `backend/app/playbook/service.py`（6）
  - `backend/app/playbook/store.py`（431）
  - `backend/tests/s2_fill_helpers.py`（新增，268）
  - `backend/tests/test_n177_n190_backtrack_probe.py`（4）
  - `backend/tests/test_playbook_exit_idempotency.py`（6）
  - `backend/tests/test_playbook_rebalance_no_cash.py`（新增，436）
  - `backend/tests/test_playbook_s2_fill.py`（新增，823）
  - `backend/tests/test_playbook_settle_locked.py`（新增，662）
  - 以上路徑都在 `apps/stock-desk/` 底下。

## 驗證
1. 步驟 1 的 A、B 都吻合，P 的 40 字元見上。
2. 步驟 4 的 parents 全部吻合：
   - `M1^1` = 232ff918…（等於 P）
   - `M1^2` = 5962b7d3…（等於 A）
   - `M2^1` = 24459285…（等於 M1）
   - `M2^2` = 1bdbbdad…（等於 B）
3. 步驟 5：`git diff --quiet 1c64201 M2 -- apps/stock-desk/backend/app apps/stock-desk/frontend/app` 輸出 `exit=0`。產品程式碼與整合基底 I 完全相同。
4. 步驟 6 的 CI 等效檢查（在 M2 上，乾淨 `.venv`，`uv sync --frozen`）：
   - `uv sync --frozen`：成功。
   - `ruff check .`：`All checks passed!`
   - `ruff format --check .`：`502 files already formatted`
   - `mypy app tests`：`Success: no issues found in 491 source files`
   - `pytest --cov=app --cov-fail-under=90`：`Required test coverage of 90% reached. Total coverage: 97.65%`，`10241 passed, 2 xfailed, 34 warnings in 950.53s (0:15:50)`，exit=0。
   - 10241 比 I 當時的 10197 多 44 個，因為 P 比 I 的 product 基底新。這是推測，我沒有逐項比對。
   - 第一次跑 pytest 超過背景 30 分鐘上限被系統終止，不是測試失敗。我改用更長 timeout 重跑，得到上面的結果。
   - compose-validate：`docker compose config > /dev/null` 為 exit=0。guard 輸出「[compose-guard] 通過:backend 與 scheduler 共用 volume「stock-desk-data」掛載於「/app/data」,且 STOCK_DESK_DB_PATH=「/app/data/stock-desk.db」一致;所有對外 port 皆只綁本機迴環介面。」，exit=0。
   - 為了避開 worktree 對複合 pipe 的限制，我把 JSON 先寫到暫存檔再餵給 guard，內容與指令等效。
   - frontend：`npm ci` 完成（有 npm audit 提示，不影響結果）。`npm run typecheck`（`tsc --noEmit`）無錯誤。vitest 為 `Test Files 116 passed (116)`、`Tests 3086 passed (3086)`。`npm run build` 完成，輸出路由表。
   - 根目錄 `python3 scripts/validate_agents.py`：`validate_agents: OK（15 個 agents 全數通過）`
   - 跑完後 `git status --short` 為空，工作樹乾淨。
5. 步驟 7（T28 與 S11）：
   - 交件文件第「T28 與 S11」一節只列出測試名稱，沒有寫當時用的 pytest 指令。我沒有猜，改用測試名稱與檔案自行組指令。
   - 在 M2 上執行 `uv run pytest -v -rA tests/test_playbook_settle_locked.py -k t28`，結果 `2 passed`：
     - `test_t28_a_today_with_nothing_filled_takes_one_lock` PASSED
     - `test_t28_each_fill_takes_one_lock_of_its_own` PASSED
   - 在 M2 上執行 `uv run pytest -v -rA tests/test_n177_n190_backtrack_probe.py -k s11`，結果 `10 passed`，沒有 skipped：
     - `test_s11_the_s2_constants_equal_the_store_once_n177a_defines_them` PASSED（交件指定的那一個）
     - 其餘 S11 項目：`index_gap_marker`、`rule_param_defaults`、`demo_source_and_index_keys`、`state_and_table_names`、`alignment_check_passes`、`probe_sql_restates`、`eligible_batch_query_matches_engine_average_cost_parity`、`marker_selects_exactly_the_index_gap_lines`，加 `test_n199_t6_s11_parity_with_the_store_g1_condition`，全部 PASSED。
   - 文件裡的「seam」一詞，我沒有在測試名稱中找到 `seam`。T28 這兩個測試是否就是文件所指的 seam 測試，我無法確認，需要 dev-lead 確認。
6. 步驟 8 的推送：`git push -u origin staging/r2-n177a-n195` 一次成功，是 `[new branch]`，沒有重試。之後 `git ls-remote origin staging/r2-n177a-n195` 為 `513c07da0ce7692597858ce17f11db0abd97f422`，等於 M2。
7. 步驟 8 的 product 檢查：預期沒有變動，實際有變動。
   - 推送後 `git ls-remote origin product/stock-desk` 為 `c20910411077bf6eb20a614fa400bcce5eb252c4`，不是 P。
   - 我從未對 product/stock-desk 執行 push，這是其他 session 在我作業期間推進的。
   - 新 tip 是 P 的後代（`merge-base --is-ancestor` exit=0）。P 到新 tip 共 3 個 docs commit，包含 `docs: 記錄 CEO #144（主力轉回預測核心；排程台其餘八項凍結）`，相關變動只有 `work/` 下的 4 個文件，+154 行，沒有程式碼變動。
   - 因此 M2 的程式碼驗證結論仍成立。M2 的 first parent 是 232ff918，不是新 tip。

## 下一步
1. coordinator：CEO #144 的內容是「主力轉回預測核心；排程台其餘八項凍結」。R2（排程台）正式合入 product 前，請先確認這項決議是否影響 R2 部署閘門。
2. 正式合入前要重新對齊最新 product tip（目前 c209104），再 merge 一次並重跑 CI，交件文件第四節也這樣要求。因為新增的只是 docs，預期不會衝突。
3. 預備分支已就緒：`origin/staging/r2-n177a-n195` = M2。這個分支沒有開 PR，也沒有部署。正式合入要等部署閘門通過與 qa、CEO 的另行指示。
4. dev-lead：請確認 T28 這兩個測試是否就是文件所指的 seam 測試，並補上當時實際用的 pytest 指令。
5. pytest 全套約 16 分鐘，超過預設背景 30 分鐘上限的風險在正式 CI 不適用，但本機驗證請預留更長 timeout。

原始 pytest 輸出：/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/pytest_full.txt

# CG-2 前置 PR 合併紀錄

- 審查者：devops-sre
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
CG-2 前置 PR 已合併並推送：**M = 8b22c114f201e34218758452da310617baab42da**，fast-forward 推到 `product/stock-desk`，一次成功。沒有衝突，也沒有停下。M 上所有檢查（含 Python 3.12 的 CI 等效檢查）全綠後才推。

## 各部門回報（devops-sre）
- fetch 後 N = `f6660b0b4a9d8e9b3b53d377381acc8e25d1d2e9`，P = `ae1bc1209e5929c72f86482b60ab798aca344f3d`，兩者都與你給的固定值相同。
- 合併步驟：`git checkout -B cg2-prereq-final P`，再 `git merge --no-ff -F <訊息檔> N`。訊息逐字照你的內容，含兩行署名。策略是 ort。
- 本地分支 `cg2-prereq-final` 在我的 worktree（`/home/user/AICompany/.claude/worktrees/agent-a9c5272eeba267d38`）。訊息檔與 log 都在 scratchpad 的 `nm5/` 下，沒有進 repo。
- 驗證用 venv：專屬目錄 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/nm5/venv-ci`。在 M 上重新執行了 `uv sync --frozen --python /usr/bin/python3.12`，輸出 `Checked 46 packages`。editable 安裝本來就指向這個 worktree，所以不需要重裝。
- 鐵則都守住：沒讀 `.env`、沒碰 `data/*.db`、沒執行一鍵檔、沒 force/rebase/amend、沒送部署通知。管線驗收 harness 只用測試檔裡的合成 fixture，沒有用真實資料。

## 驗證
- 父提交：M^1 = `ae1bc1209e5929c72f86482b60ab798aca344f3d`（等於 P），M^2 = `f6660b0b4a9d8e9b3b53d377381acc8e25d1d2e9`（等於 N）。
- `git diff --name-only P M` 恰為 8 個檔，1078 行新增、101 行刪除，與你給的清單逐一相符：
  - `app/dirdef/__init__.py`
  - `app/dirdef/definition.py`
  - `app/dirdef/registry.py`
  - `app/forecast/definitions.py`
  - `app/forecast/schema.py`
  - `app/forecast/store.py`
  - `tests/test_forecast_bootstrap.py`（新增）
  - `tests/test_forecast_store.py`
  - 以上路徑都在 `apps/stock-desk/backend/` 下。
- P 與 M 之間零 diff：`app/forecast/claims.py`、`app/main.py`、`app/scheduler.py`、`app/outlook/rules`、`tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`、`scripts`、`uv.lock`、`apps/stock-desk/pipeline-acceptance.bat`，以及整個 `work/dispatch`。對這些路徑的 `git diff --name-only` 為 0 筆。
- 四個規則雜湊（在 M 上用 `load_ruleset` 加 `rules_logic_sha256`，以 `BANNED_PHRASES` 載入，檔案位元組算 sha256），與先前合併紀錄逐字相同：
  - h3 rules_sha256 `f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443`：相同
  - h3 logic `ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484`：相同
  - h5 rules_sha256 `0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c`：相同
  - h5 logic `e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb`：相同
- 登記表仍為空：`PUBLISHED_DIRECTION_DEFINITIONS` 長度 0，`PUBLISHED_RULESETS` 長度 0。這兩個常數定義在 `app/dirdef/registry.py`，`app/forecast/definitions.py` 重新匯出；我是從 `definitions` 讀的，長度為 0 與 0。
- Python 3.12 檢查（M 上）：
  - `"$UV_PROJECT_ENVIRONMENT/bin/python" -V`：`Python 3.12.3`。
  - `app.__file__`（從 `/tmp` 啟動，不靠 cwd）：`/home/user/AICompany/.claude/worktrees/agent-a9c5272eeba267d38/apps/stock-desk/backend/app/__init__.py`。這是 M 的 worktree，證明測的是 M 的程式。
  - `ruff check .`：All checks passed。
  - `ruff format --check .`：546 files already formatted。
  - `mypy app tests`：Success, no issues found in 534 source files。
  - 全套 `pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：12053 passed、2 xfailed、1 warning，總覆蓋率 97.81%（門檻 90%），耗時 0:35:58，exit=0。
- 管線驗收 harness（合成資料，Python 3.12）：`tests/test_pipeline_acceptance_real_flow.py`、`..._bars.py`、`..._eol.py` 共 193 passed。其中 `test_the_two_rule_sets_each_have_a_complete_group` 斷言 P-0 與 P-1 都是「通過」、`ok=21` 各一組。另外加跑 `tests/test_forecast_bootstrap.py`，連同上述三檔共 237 passed。
- **M 上的 `code_digest` = `a15e910cad72389e12429025f3fb64fe1ff6b67b58cdbbea25123bd44bb77461`**，取自 `recorder.LOADED.code_digest`，與 dev-lead 在 `10fbdf9` 算出的值逐字相同。
- compose-validate：`docker compose config` exit 0。shared database guard 通過：backend 與 scheduler 共用 volume `stock-desk-data`，掛載於 `/app/data`，`STOCK_DESK_DB_PATH=/app/data/stock-desk.db` 一致，所有對外 port 只綁本機迴環介面。
- frontend：`npm ci` 成功（有 npm audit 提示，與本次無關）；typecheck exit 0；vitest 116 個檔案、3086 個測試全過；build exit 0。
- 根目錄 `python scripts/validate_agents.py`：OK（15 個 agents 全數通過）。
- 推送前 `git ls-remote origin refs/heads/product/stock-desk` = `ae1bc1209e5929c72f86482b60ab798aca344f3d`（等於 P），工作樹乾淨。
- 推送：`git push origin 8b22c114f201e34218758452da310617baab42da:product/stock-desk`，輸出 `ae1bc12..8b22c11`（fast-forward）。
- 推送後 `git ls-remote` = `8b22c114f201e34218758452da310617baab42da`（等於 M）。

## 下一步
1. 我沒有查推送觸發的 GitHub Actions 結果，請 coordinator 確認 `stock-desk` workflow 三個 job（backend、compose-validate、frontend）都綠燈。
2. 回滾方式：這次只新增一個 merge commit，可用 `git revert -m 1 8b22c114f201e34218758452da310617baab42da` 退回，不需 force push。是否回滾由 CEO 決定。
3. 這個 PR 沒有任何 `app/` 模組呼叫新路徑，正式路徑仍無法建表，這是設計如此。後續 CG-2 要接上時，是另一個 PR。
4. 目前的 `code_digest` 已是 `a15e910c…7461`，之後只要 `app/` 有變動就會不同，需重新比對。

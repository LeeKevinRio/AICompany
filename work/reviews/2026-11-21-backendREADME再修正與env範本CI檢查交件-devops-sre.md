# backend README 再修正與 .env.example CI 檢查交件

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
兩件都完成並 push，未開 PR、未合併。

## 各部門回報（devops-sre）

### 第一件：`docs/backend-readme-db-path`
- base 為前次 head `d5789608f04a0bf666b39cf092923cc479105772`。
- 新 head 完整 SHA：`df796a6b2a50284ef2cb12739f21023572d5a430`。fast-forward push（`d578960..df796a6`）。
- 新增一個 commit，trailer 兩行如指示，只改 `apps/stock-desk/backend/README.md`。

逐處原／新，行號為新檔行號：
1. 第 54 行
   - 原：不論設在程序環境、空值或 `.env` 都不行；設了，排程每次都跳過，「正式登記與 bootstrap 也會拒絕」。
   - 新：
     - 空值也不行，也不得寫進 `.env`。
     - 預測紀錄排程（`forecast_record`，接線後）看的是 scheduler 程序自己的環境，有這個變數（含空值）就每次都跳過、只記一行 WARNING。
     - `.env` 只有被載入進 scheduler 程序（`dev-up.bat` 的 `UV_ENV_FILE`）才會造成跳過，scheduler 本身不讀 `.env`；只對 API 程序設不會讓它跳過。
     - 登記改寫為「正式登記（`bootstrap --production`）則不論程序環境或 `<backend>/../.env` 設了這個變數（含空值）都會拒絕」，不再讀成兩條路。
2. 第 64～66 行
   - 原：「決定唯一一顆 SQLite 檔（快取、持倉、設定、警示規則/事件全部共用）」。
   - 新：決定「主 DB」（快取、持倉、設定、警示規則/事件共用，WAL 模式）；市場資料與研究資料各有獨立 SQLite 檔（`STOCK_DESK_MARKET_DB_PATH`，預設 `./data/stock-desk-market.db`；研究 DB 預設 `./data/stock-desk-research.db`）。
3. 第 110～112 行（示範資料指令註解）
   - 原：不加 `--db-path` 會寫進預設主 DB（相對於 cwd 的 `./data/stock-desk.db`），和預測紀錄帳是同一個檔。
   - 新：不加 `--db-path` 時寫進 `resolve_db_path()` 的結果，有設 `STOCK_DESK_DB_PATH` 就是它指的檔，否則是相對於 cwd 的 `./data/stock-desk.db`；在 backend 目錄、沒設變數時，就是預測紀錄帳那個檔；在執行預測紀錄的主機上不得這樣跑。
4. 第 150 行附近（原第 148 行）
   - 原：日線／持倉／警示規則一律不寫。
   - 新：日線／持倉／警示規則的資料列一律不寫；但三個 store 的建構子在衝突檢查之前就會建立目錄與資料表，所以目標檔與空表可能已經存在。

驗證：
- `git diff d5789608… HEAD --stat`：`apps/stock-desk/backend/README.md | 14 ++++++++------`，1 file changed, 8 insertions(+), 6 deletions(-)。只有這一個檔。
- 行尾空白 0、CR 0。
- `STOCK_DESK_DB_PATH` 命中 7 行，逐行說明：
  - 第 54 行：新措辭，符合 dev-lead 事實 1、2。
  - 第 64 行：「決定主 DB」，符合事實 4。
  - 第 67 行：compose 顯式設定，是事實，沒動。
  - 第 110 行：改為「有設就寫到它指的檔，否則 `./data/stock-desk.db`」，符合事實 3。
  - 第 115 行：`--db-path` 隔離，「不需要、也不應該設」，沒動。
  - 第 144 行：限定在非預測紀錄機器、對那一個 API 程序，沒動。
  - 第 152 行：seed 訊息現況加「不要照做」，沒動。
  - 沒有未限定的「建議設定」或「沿用」。

### 第二件：`test/env-example-db-path-check`
- base SHA：`f093e1b5eb464152f2330b36beef331b1152cbf3`。這是 `origin/product/stock-desk` 最新 head，已不是前次的 `9e0d81c`。
- head 完整 SHA：`1fed802b07017e89a5d510236d2462ea46ac380d`。
- 新檔：`apps/stock-desk/backend/tests/test_env_example_db_path.py`，92 行。

設計：
- 純函式 `scan_env_lines(lines) -> (has_active, has_comment)`。
  - active 的 regex 是 `^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=`。
  - 註解行判斷是去掉前導空白後以 `#` 開頭且含該名稱。
- 內部函式 `_inspect_env_example(path)` 讀檔後只回傳布林；檔案不存在或無法讀取（`OSError`、`UnicodeDecodeError`）回傳 `None`。
- CI-only 測試 `test_env_example_has_no_active_db_path_ci_only`：
  - `GITHUB_ACTIONS != "true"` 時，在開檔前就 `pytest.skip`。skip 訊息是固定字串，不含檔案內容。
  - 固定路徑是 `Path(__file__).resolve().parents[1].parent / ".env.example"`，也就是 `<backend>/../.env.example`。
  - 檔案不存在或無法讀取：以固定字串 `pytest.fail`。
  - 有 active 行：`pytest.fail(".env.example has an active STOCK_DESK_DB_PATH line")`。
  - 沒有 active 行：用 `warnings.warn` 輸出固定字串，區分「appears only in comments」與「not present」。
  - 整個流程沒有 `assert`，不輸出行內容，也不輸出行號。
  - docstring 為英文，只寫「CEO decision 2026-11-21, scope: …」，沒有 model ID。
- 純函式測試共 6 個：不存在、只有註解、有 active 行（含空白與等號前空格）、`export` 寫法、相似名稱 `STOCK_DESK_DB_PATH_OTHER` 不算 active、`tmp_path` 下檔案不存在。這些測試只餵假字串或 `tmp_path`，本機也會跑。

驗證輸出：
- `git diff f093e1b… HEAD --stat`：只有 `.../backend/tests/test_env_example_db_path.py | 92 +`，1 file changed, 92 insertions(+)。
- 本機執行 `env -u GITHUB_ACTIONS uv run pytest tests/test_env_example_db_path.py -rs -q`：`SKIPPED [1] tests/test_env_example_db_path.py:58: CI-only check (GITHUB_ACTIONS is not 'true')`，結果 `6 passed, 1 skipped, 1 warning`。那個 warning 來自 fastapi testclient 的 httpx 棄用提示，與本檔無關。
- `ruff check`：All checks passed。
- `ruff format --check`：1 file already formatted。
- `mypy`（單檔）：`Success: no issues found in 1 source file`。我只對該檔跑，沒有跑整個 `app tests`。
- Grep 確認：新檔中只有 `_ENV_EXAMPLE` 那一個固定路徑，唯一的讀檔呼叫是第 45 行 `path.read_text`，沒有 glob、沒有 `open`，也沒有其他 `.env*` 存取。
- 本機測試過程中我沒有設定過 `GITHUB_ACTIONS`，也沒有讓測試讀到 `.env.example`。

## 驗證
見上，兩件各自附於其下。

## 下一步
- 兩個分支都交 qa-reviewer（含 Codex）審查，README 的 diff 送風控知悉（RC-460）。
- 第二件的 CI 設定是否會把該測試跑起來、`GITHUB_ACTIONS` 是否為 `"true"`，需要在實際 CI 上確認；測試不修改 workflow。

worktree：`/home/user/AICompany/.claude/worktrees/agent-a2a08a5c2fbafcb22`。目前停在 `test/env-example-db-path-check`。

### 沒有查證的事
- 沒有在 CI 實際跑過讀檔那一條路徑，也沒有確認 `.env.example` 現況是否通過，因為限制不讀。
- 沒有跑 `uv run mypy app tests` 全量，只跑單檔。
- 第一件的措辭依 dev-lead 核對文，我沒有重新讀程式確認。
- 本機 `uv run` 在 `apps/stock-desk/backend/.venv` 建了 venv。該目錄被 gitignore，`git status` 乾淨。

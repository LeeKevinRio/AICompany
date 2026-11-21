# backend README 與 .env.example CI 檢查兩支分支複審（單家審查）

- 審查者：qa-reviewer
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

單家審查（Codex 不可用，依 CEO 決策 #58，未跑 /review）。兩支分開給結論。

# 第一支：`docs/backend-readme-db-path`（head df796a6）

## 本次結論
**PASS_WITH_NOTES，BLOCKING_ISSUES=false。** 無 critical 或 high。有 1 項 medium（見註 1）建議在合併前一併處理，其餘為 low。

## 各部門回報（qa-reviewer 逐項核對）
- (1) diff 範圍：`git diff --name-only` 只有 `apps/stock-desk/backend/README.md`。成立。
- (2) 逐句對照 dev-lead 的「應寫成的事實」，下列各項都符合：
  - 第 1 項：scheduler 程序環境有變數（含空值）就每次跳過、只記一行 WARNING，對照 `scheduler.py` 699～700 行（`in os.environ`）與 668～671 行。`.env` 只有被載入進 scheduler 程序（`dev-up.bat` 的 `UV_ENV_FILE`）才生效、scheduler 本身不讀 `.env`、只對 API 程序設不會跳過，也都符合。
  - 第 2 項：bootstrap 不論程序環境或 `<backend>/../.env` 都拒絕，對照 `claims.py` 403～406 行。
  - 第 3 項：「預測紀錄只寫 `<backend>/data/stock-desk.db`」，對照 `scheduler.py` 686～709 行。
  - 第 4 項：compose 顯式設定變數，因此 compose 不是會記錄預測的部署形態，推論成立。
  - 第 5 項：seed 不加 `--db-path` 時寫進 `resolve_db_path()` 的結果，對照 `seed.py` 559 行。「在 backend 目錄、沒設變數時才是預測紀錄帳那個檔」的前提也寫了。`--db-path` 相對 cwd 的說法也成立。
  - 第 6、7 項：寫進主 DB 的後果，照 dev-lead 條列。
  - 第 6 項旁支：「三個 store 建構子在衝突檢查前就建目錄與表」，與 `seed.py` 560～562 行（建構在 `seed_demo` 之前）一致。
  - 第 9 項：衝突訊息仍建議設變數、「在那之前不要照做」，與 dev-lead 第 9 項一致。
  - 第 10 項：第 64 行改為「主 DB」，並列市場與研究 DB 與其預設路徑，與 dev-lead 第 10 項一致。
- (3) 未限定的「建議設定／沿用 `STOCK_DESK_DB_PATH`」：base 版有 4 處（表格列、第 64 行「唯一一顆」、第 109 行「沿用」、第 142 行「建議改用 …／`STOCK_DESK_DB_PATH`」），head 全部改過。第 142 行現在只建議 `--db-path`。head 內剩下的提及都有「不執行預測紀錄的機器」或「不得」的限定。
- (4) 沒有給 CEO 的句子，沒有叫讀者去讀主機部署手冊或 `local-run`。提到 `dev-up.bat` 只是在說明機制，不是導讀。
- (5) 沒有寫 product 上不存在的程式行號。
- (6) `git diff --check` 無輸出（無行尾空白）。diff 內無 CR、model ID、祕密。

## 備註（不擋）
1. [可維護性／事實範圍][medium] 「正式登記（`bootstrap --production`）…都會拒絕」與「預測紀錄排程（接線後）」的處理不一致。
   - 我讀 product 版 `app/forecast/claims.py`：搜尋不到 `production_target`、`env_file_sets_db_path`、`--production`，所以這條只在接線版存在。
   - 同一格裡 scheduler 那句有標「接線後」，bootstrap 這句沒有。
   - 建議在該句加「（登記接線後）」，或由 coordinator 確認合併順序。
2. [Edge case][low] 第 2 項的「含空值都會拒絕」未涵蓋 `export STOCK_DESK_DB_PATH=...` 寫法。dev-lead 實測 uv 會載入這種寫法，但 `claims.py` 的 regex 比對不到。README 句子對這個寫法略有過度保證。dev-lead 已建議記進追蹤清單，我同意不擋。
3. [可維護性][low] 「那句訊息將在正式登記後另行修正」是時程承諾，修正後容易過期。建議修正 `seed.py` 時一併刪掉這句。
4. [可維護性][low] 表格該格過長，可讀性差。
5. [可維護性][low] 新增的 `STOCK_DESK_MARKET_DB_PATH` 與研究 DB 說明，是 dev-lead 標明「要不要在這支 PR 改由 tech-architect／coordinator 決定」的項目。我沒有看到該決定的紀錄，請 coordinator 確認。內容本身與 dev-lead 相符。
6. [可維護性][low] seed 區塊的註解提到「預測紀錄帳」，product 上尚無此帳，與註 1 同類，可加「接線後」。

## 唯讀權限判準常數
未觸及。檢查 1：`git diff --name-only` 結果只有 README.md，不含 `scripts/validate_agents.py`。檢查 2：diff 內無 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`，也無 shadow 定義或值異動。異動 agent 名單為空；改了什麼、為何改、有無 ADR 三問答案分別是：僅 README 文字、不涉及常數、不需 ADR。

---

# 第二支：`test/env-example-db-path-check`（head 1fed802）

## 本次結論
**PASS_WITH_NOTES，BLOCKING_ISSUES=false。** RC-483 三項核對全部通過。僅有 low 備註。

## 各部門回報

### RC-483 三件事
- **(a) 只讀那一個路徑：通過。**
  - 路徑推算：`Path(__file__).resolve().parents[1].parent / ".env.example"`。以 `apps/stock-desk/backend/tests/x.py` 計，`parents[0]` 是 `tests`，`parents[1]` 是 `backend`，再 `.parent` 是 `apps/stock-desk`，結果是 `apps/stock-desk/.env.example`，正確。
  - 檔案內沒有 glob、iterdir 或其他 `.env*` 路徑。
  - 模組載入時的 `resolve()` 只解析測試檔自身，不開目標檔。
- **(b) 不輸出內容：通過。**
  - 字串：所有 `pytest.skip`、`pytest.fail`、`warnings.warn` 都是固定字串。CI 測試函式內沒有 `assert`，所以沒有 assertion rewriting 帶出內容的問題。
  - 讀檔：讀入的內容只存在於 `_inspect_env_example` 的暫時運算式，回傳只有兩個 bool 或 `None`。
  - 例外：`OSError` 與 `UnicodeDecodeError` 在函式內被吞掉並回 `None`，不會傳出 traceback（`UnicodeDecodeError` 的訊息帶位元組片段，但被攔住了）。`path.is_file()` 若遇權限問題可能丟 `PermissionError`，但訊息只會含路徑，不含內容。
  - `--tb`／`-l`：CI 的 pytest 指令是 `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`（`stock-desk.yml` 39 行），沒有 `-l` 或 `--showlocals`。`pyproject.toml` 搜尋不到 `addopts`、`filterwarnings`、`--tb`、`showlocals`。
  - 殘餘風險：極低。即使未來被加上 `--showlocals`，失敗框架（測試函式）的 locals 只有 bool 與 `Path`，內容字串不在該框架內。
  - 未驗證：CI 環境若有 `PYTEST_ADDOPTS`，我無法查看。
  - 輸出：warning 會在 pytest 摘要顯示「僅在註解中」或「不存在」的固定句，符合 CEO 同意的「只輸出有／沒有、是否 `#` 開頭」。
- **(c) 沒有其他讀 `.env*` 的程式碼：通過。** diff 只新增這一個檔。Grep 該 worktree 的 `tests/` 與 `app/` 另有 31 個檔含 `.env`，皆為本次 diff 之前已存在（多為環境變數名稱字串），不是本次引入。

### 其他核對
- 本機 skip：`os.environ.get("GITHUB_ACTIONS") != "true"` 在 `is_file()` 與 `read_text` 之前就 skip，訊息為固定字串。`conftest.py` 的 autouse fixture 只設 DB 路徑環境變數，不碰 `GITHUB_ACTIONS`。
- 純函式測試：只餵假字串或 `tmp_path`（空檔案、不存在路徑）。
- regex 與註解判斷：
  - `STOCK_DESK_DB_PATH_OTHER=` 因名稱後必須接 `\s*=`，不算 active，有測試覆蓋。
  - 前導空白、`export`、`NAME =` 都能判為 active。
  - 行內 `FOO=1 # STOCK_DESK_DB_PATH` 不算 active（正確，非變數設定）。
  - 比 `claims.py` 的 regex 多了 `export`，較嚴格，方向正確。
  - BOM 由 `utf-8-sig` 處理，CRLF 由 `splitlines` 處理。
- 風格：讀碼判斷符合 ruff 的 E、F、I、UP、B、W 與 line-length 100。最長一行約 95 字元；import 順序合 isort；`warnings.warn` 有 `stacklevel`；型別標註完整，mypy strict 應過。`git diff --check` 無輸出。我沒有實際執行 ruff 與 mypy，`ruff format --check` 是否過只能靠推判。
- CI 影響：`--cov=app` 只量 `app/`，測試檔在 `tests/`，不影響覆蓋率，也不影響 `app/` tree id。
- CI 觸發：workflow 的 paths 含 `apps/stock-desk/**`，改 `.env.example` 會觸發 CI。

### 備註（不擋，均為 low）
1. [Edge case] 小寫 `stock_desk_db_path=` 與無 `=` 的裸 `STOCK_DESK_DB_PATH` 行不被判為 active。Linux 上環境變數區分大小寫，實務風險低。
2. [Edge case] `.env.example` 缺檔在 CI 會 fail（訊息為固定字串）。檔案是追蹤檔，合理。
3. [測試] CI 專屬讀檔路徑與 active 分支只會在 CI 執行，本機驗證不到。純函式測試已涵蓋判斷邏輯，可接受。
4. [可維護性] 範圍約束（一個測試、一個固定路徑、只輸出布林）已寫在 docstring 中，後人若想擴充需先重新取得 CEO 同意，建議保留該段。

## 唯讀權限判準常數
未觸及。檢查 1：`git diff --name-only` 只有 `tests/test_env_example_db_path.py`，不含 `scripts/validate_agents.py`。檢查 2：diff 內無 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`，也無 shadow 定義或值異動。異動 agent 名單為空；改了什麼、為何改、有無 ADR 三問答案分別是：僅新增一個測試檔、與常數無關、不需 ADR。

---

## 驗證
實際執行的指令（皆為單一 `git diff`）：
- `git diff 9e0d81c… df796a6…`
- `git diff --name-only` 與 `git diff --check`（第一支）
- `git diff f093e1b… 1fed802…`
- `git diff --name-only` 與 `git diff --check`（第二支）

另用 Read、Grep、Glob 讀下列檔案：
- 接線版 `scheduler.py` 660～721 行、`claims.py` 380～411 行
- product 版 `seed.py` 540～581 行
- `.github/workflows/stock-desk.yml`、`pyproject.toml`、`conftest.py`
- dev-lead 核對檔、第二支新檔

## 沒有查證的事
- 沒有讀任何 `.env*`（包括 `.env.example`），沒有設 `GITHUB_ACTIONS`，沒有碰 `backend/data/`。
- 沒有執行 pytest、ruff、mypy、seed 或任何程式。
- `cache.py` 90～110 行我沒有另外讀，這部分只依賴 dev-lead 的核對。
- 沒有核對 tech-architect 與 devops 的交件原文，第一支以 dev-lead 的條列為準。
- 沒有確認 CI 環境的 `PYTEST_ADDOPTS`。
- 沒有確認 coordinator 對第 64 行擴寫範圍的決定。

## 下一步
1. 第一支：coordinator 決定是否在合併前處理註 1（bootstrap 句加「接線後」限定），同時確認註 5 的範圍決定。處理後我可快速複審該句，或視為 PASS_WITH_NOTES 直接進風控知悉（RC-460）。
2. 第二支：可進風控 RC-483 選項 2 的確認與合併流程。涉及 CI，合併後請看 CI 綠燈，包含 `ruff format --check`。
3. 追蹤清單：`export` 寫法的 regex 漏洞，以及 `seed.py` 的訊息與 `--help` 文字修正，併入「拒絕寫入主 DB」任務。

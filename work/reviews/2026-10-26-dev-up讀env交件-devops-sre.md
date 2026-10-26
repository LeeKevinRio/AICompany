# 原生啟動讀.env交件

- 審查者：devops-sre
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 變更摘要

分支 `fix/stock-desk-dev-up-env`，從 `product/stock-desk` f73c466 長出，已 `git push -u origin`。HEAD = `fc63261d00827a1f5381453d1dd35a5bf2c17ce3`。沒有 merge 進 product/stock-desk，也沒有 push 到 product/stock-desk。

Commit 共 5 個，每個都帶 Co-Authored-By 與 Claude-Session 兩行：
1. `21e413d` fix: 後端與 scheduler 啟動時印出祕密載入狀態
2. `1a12791` fix: dev-up.bat／dev-up.sh 啟動時讀取 apps/stock-desk/.env
3. `4a963a2` docs: README 改以原生 dev-up 為主、更正多顆 DB 並補原生備份還原
4. `e9982ba` docs: local-run skill 補 .env 載入與原生備份還原（只改 product 分支這份）
5. `fc63261` fix: 狀態行測試還原 logger 等級（見下方「過程中的失誤」）

### 建議 1：原生啟動讀 .env

**uv 查證**（本環境）：
- `uv --version` 輸出 `uv 0.11.32 (x86_64-unknown-linux-gnu)`。
- `uv run --help` 的相關段落：
  ```
  --env-file <ENV_FILE>   Load environment variables from a `.env` file [env: UV_ENV_FILE=]
  --no-env-file           Avoid reading environment variables from a `.env` file [env: UV_NO_ENV_FILE=]
  ```
- 我在 scratchpad 實測：
  - `--env-file` 和 `UV_ENV_FILE` 都能載入檔案內容，含雙引號值。
  - 同名的 shell 環境變數優先於檔案（`FOO=fromshell` 贏過檔案裡的 `fromfile`）。
  - **檔案不存在時 uv 直接報錯**：`error: No environment file found at: nope.env`，exit code 2。
  - `UV_ENV_FILE` 設成空字串等同沒設。
- 所以腳本必須先判斷檔案存在才指向它。

**做法**：
- 檔案存在就設 `UV_ENV_FILE`，也就是等效的 `uv run --env-file`。
- 選環境變數而不是在每條指令後加參數，是因為 bat 的 `cmd /k "..."` 巢狀引號容易出錯，路徑含空格或括號時尤其危險。
- 後端與 scheduler 的兩個 `uv run` 都會繼承這個變數，所以兩邊都讀得到。
- 檔案不存在時 `unset`／清空該變數，照常啟動並印一行 `[ENV]` 提示。
- 腳本只印檔案路徑，不印內容。

**程式內的載入狀態行**：
- 新增 `apps/stock-desk/backend/app/env_status.py`。只取「去除空白後是否非空」的布林值，值本身不存、不格式化、不切片、不傳給 logger。
- 輸出格式：`FINMIND token：已設定；Alpha Vantage key：未設定；Discord webhook：…；Telegram：…`。
- Telegram 要 token 與 chat id 兩個都有才算已設定，與 `notify()` 的實際條件一致。
- 我多加了 Alpha Vantage 一項，因為審視提到它同樣會靜默失效。
- 呼叫點：`app/main.py` 的 lifespan 在 `configure_logging()` 之後，以及 `app/scheduler.py` 的 `main()` 在 `configure_logging()` 之後。
- 新增 `tests/test_env_status.py`，共 9 個測試：
  - 全未設定、全設定、Telegram 缺一半、空白值、預設讀 process 環境。
  - 走真實的 API lifespan 與 scheduler `main()`，讀真實 stderr。
  - 用假值斷言輸出不含值，也不含值的前綴、後綴與特徵片段。

### 建議 5：文件

**README**：
- 快速啟動第一段改為「CEO 日常：雙擊 dev-up.bat」，並寫明 `.env` 說明。
- Docker 移到「選用：Docker 啟動」。
- 「全部使用者資料都在一顆 SQLite」已更正。實際 grep 確認至少三顆：
  - 主 DB `stock-desk.db`：`data/cache.py:28`。
  - 市場 DB `stock-desk-market.db`：`data/market_panel.py:95`。
  - 研究 DB `stock-desk-research.db`：`research/sector_biased/store.py:45`。
  - 其餘 store（positions、settings、alerts、directory、dividends、kelly、quota 等）都走 `resolve_db_path()`，所以在主 DB。
- 新增原生路徑備份與還原：先停三個程序，成套複製 `backend/data/` 內所有 `*.db`、`*.db-wal`、`*.db-shm`。還原時先清掉舊的 `-wal` 與 `-shm`，避免舊 WAL 被套到剛還原的 DB 上。
- Docker 段落寫明直接 `tar` 執行中的 WAL DB 不保證一致快照，要嘛 `docker compose stop` 後備份，要嘛線上備份。
- `.env` 說明改成一張表，列出實際被讀到的啟動方式：dev-up、docker compose、手動 `uv run --env-file`。並註明應用程式本身沒有 dotenv 載入（grep 確認 `app` 內零命中）。
- 環境變數表補 `STOCK_DESK_MARKET_DB_PATH` 與 `STOCK_DESK_RESEARCH_DB_PATH`。
- 目錄樹補 dev-up。

**`.claude/skills/local-run/SKILL.md`**（product 分支這份）：
- 補 bat 與 sh 的 `.env` 載入說明。
- 手動指令加 `--env-file ../.env`，並註明檔案不存在時要拿掉。
- 更正「第二顆 DB」的說法。
- 新增「資料與備份（原生路徑）」小節。

## 環境與版本

- uv 0.11.32（本環境實測）。
- `--env-file` 最低支援版本〔未查證〕。dev-up 用環境變數，舊版 uv 會忽略它，此時啟動時的狀態行會顯示「未設定」，所以不是靜默失效。

## 驗證結果

**bash -n**：`bash -n dev-up.sh` 通過（輸出 `ok`）。

**bat 逐行改動說明**（全部標：未在 Windows 實機驗證）：
- 檔頭加 2 行 REM：說明 `.env` 由 `UV_ENV_FILE` 載入，以及系統環境變數優先。純註解。
- 在「repo 狀態檢查」與「3. pull」之間新增 `2b` 區塊：
  - `set "ENV_FILE=%~dp0.env"`：`%~dp0` 以反斜線結尾，所以得到 `...\apps\stock-desk\.env`。
  - `if exist "%ENV_FILE%" ( ... ) else ( ... )`：存在時走第一支。
  - `set "UV_ENV_FILE=!ENV_FILE!"`：延遲展開，路徑含 `)` 時 echo 與 set 不會壞掉。
  - 兩行 echo 提示載入。文字裡刻意不含括號或特殊字元，因為在括號區塊內。
  - else 分支 `set "UV_ENV_FILE="`：清掉可能殘留的外部值，避免指向不存在的檔而讓 uv 報錯。
  - 再 echo 兩行「找不到 .env，照常啟動」。
- 「:backend_ok」裡一行 REM 註解更新，說明 `UV_ENV_FILE` 會被繼承。
- `start "..." cmd /k "cd /d ... && uv run ..."` 兩條**沒有改**。`UV_ENV_FILE` 靠子視窗繼承父環境。這是核心假設，未在 Windows 驗證。
- 其他沒動。

**CRLF**：
- `file dev-up.bat` → `DOS batch file, ASCII text, with CRLF line terminators`。
- `grep -c $'\r'` 為 285，`wc -l` 為 285，每行都有 CR。
- `git ls-files --eol` → `i/lf w/crlf attr/text eol=crlf`。`.gitattributes` 沒改。

**其他實測**（在本機 Linux）：
- 用假的 `.env` 設 `UV_ENV_FILE`，再跑 `uv run python` 呼叫 `describe_env_status()`，輸出 `FINMIND token：已設定；…Telegram：已設定`（其餘兩項未設定）。不設時全部為未設定。
- Python `sqlite3.Connection.backup()` 對 WAL 檔、有寫入連線開著的情況可備份，已實測。

**CI 原文**（`apps/stock-desk/backend`，與 `.github/workflows/stock-desk.yml` 同指令）：
```
uv run ruff check .             -> All checks passed!
uv run ruff format --check .    -> 439 files already formatted
uv run mypy app tests           -> Success: no issues found in 434 source files
uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90
  TOTAL    19140   500   97%
  Required test coverage of 90% reached. Total coverage: 97.39%
  ========== 8086 passed, 2 xfailed, 18 warnings in 1041.50s (0:17:21) ==========
```

**過程中的失誤**：第一次整套 pytest 出現 6 個失敗，都在 `tests/test_portfolio_coverage_wiring.py`，單獨跑會過。
- 原因：我的新測試跑完沒還原 `app` logger 的 INFO 等級。後續測試在 `caplog.at_level(DEBUG)` 下收不到 DEBUG 紀錄。
- 修法：比照 `test_r1_secret_redaction.py` 加 autouse 還原 fixture，即 `fc63261`。重跑整套全綠，如上。

## 回滾方式

- 分支尚未合併，不想要就不要合併，或直接刪除遠端分支。
- 已合併後要退回：`git revert` 這 5 個 commit。
- 單項退回：
  - bat／sh 退回：還原 `dev-up.bat` 與 `dev-up.sh`，行為回到不讀 `.env`。
  - 狀態行退回：移除 `app/env_status.py`、`main.py` 與 `scheduler.py` 各一行呼叫、`tests/test_env_status.py`。

## 未驗證事項

1. **bat 全部未在 Windows 實機驗證**。重點是：
   - `if exist ... ( ) else ( )` 區塊與延遲展開。
   - `start cmd /k` 子視窗是否真的繼承 `UV_ENV_FILE`。
   - 路徑含空格或括號的情況。
   - `.env` 內容含 CRLF 或 BOM 時 uv 的解析，我只測了 LF 檔。
2. `dev-up.sh` 只做了 `bash -n`，沒有整支執行：它會 `git pull` 並起 npm，不適合在此環境跑。`.env` 載入邏輯是用 `UV_ENV_FILE` 加 `uv run` 單獨實測過。
3. 〔未查證〕項目，README 與 skill 內已標：
   - `--env-file` 的 uv 最低版本。
   - `python:3.12-slim` 映像內有沒有 `sqlite3` CLI。
   - 容器內 `/app/data` 是否真的同時放三顆 DB。這是由 `WORKDIR /app` 推論的，沒有實際 build。
   - Docker 與原生資料互搬的流程。
   - 備份與還原步驟都沒有在 Windows 或實際 volume 演練。
   - 市場 DB 各表能否由資料源完全重建，以 ADR-0012 為準。
   - 研究 DB 是否在一般運作下就會產生。
4. 我沒讀 `.env`，也沒碰 `*.db`。`apps/stock-desk/.env.example` 被權限擋下，沒讀到，所以沒核對範本內容。README 的變數名稱是從程式碼常數取的。
5. 其他文件的相關過時處：
   - `work/stock-desk-產品說明.md:443-444` 寫 `cp .env.example .env`。這句現在對 bat 是正確的，但它的備份說明我沒查。
   - `backend/README.md` 同樣沒查。
   - 這兩份不在本次範圍，我沒改。
6. 建議 2、3、4 沒做。建議 3 的 R-1 `configure_logging()` 已在 product 分支上，本次是沿用它。
7. 這批動到 `.claude/skills/` 與 bat，依規定要交 qa-reviewer 審查後才算完成，尚未審。

主要檔案（worktree 內絕對路徑，前綴 `/home/user/AICompany/.claude/worktrees/agent-aa078b54360377fd2/`）：
- `apps/stock-desk/dev-up.bat`
- `apps/stock-desk/dev-up.sh`
- `apps/stock-desk/README.md`
- `.claude/skills/local-run/SKILL.md`
- `apps/stock-desk/backend/app/env_status.py`
- `apps/stock-desk/backend/app/main.py`
- `apps/stock-desk/backend/app/scheduler.py`
- `apps/stock-desk/backend/tests/test_env_status.py`

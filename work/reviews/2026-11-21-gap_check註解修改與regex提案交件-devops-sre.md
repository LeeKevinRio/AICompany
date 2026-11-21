# gap_check 註解修改與舊 regex 修正提案交件

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 第一件：gap_check 註解（已推送）

**本次結論**：已完成並推送，fast-forward `f6aff2c..1faae4a`。分支 `wip/gap-check-comment`，新 head 完整 SHA 是 `1faae4a73636d7d276d3748da10ff2ee9e3311f6`。遠端 head 先確認過是 `f6aff2ce61bb15dd4d1e5d52b54e6668801eaf3e`。沒有 rebase、amend 或 force。commit 是 `chore: gap_check 註解刪去對已退役登記腳本的指稱`，含你指定的兩行 trailer。

**變更**：`apps/stock-desk/backend/scripts/gap_check.py` 第 180 行，原為 `# Verbatim from the risk-control report (RC-272, S-3; replaces the cg2_register.py line):`，現為 `# Verbatim from the risk-control report (RC-272, S-3):`。鄰行沒動。

**驗證（qa 核對 1～7）**
- `git diff --name-status f6aff2ce… 1faae4a…` 輸出：`M apps/stock-desk/backend/scripts/gap_check.py`
- diff 只有一刪一增（`-U0` 只有第 180 行的舊行與新行）。
- `ast.dump` 比對：腳本是 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/astcmp.py`，兩個 rev 各 `git show` 後 parse，輸出 `ast equal: True`。
- `tests` 目錄 diff 為空。
- `pipeline_acceptance_bat_frozen.txt` 的 blob 是 `5b0b271e52f100a7f8584fe7e1ec9889c4cee717`，符合預期。
- **與指示不符，請 tech-architect 留意**：`apps/stock-desk/.gitattributes` 在這個 commit 裡不存在，`rev-parse` 回 fatal。你給的雜湊 `445bacf6a94c34ec9f0738289785d52e1ab368b8` 實際是 `apps/stock-desk/backend/tests/fixtures/.gitattributes`，即 frozen 檔旁邊那個，路徑記錯了。該檔雜湊相符。順帶列出：`apps/stock-desk/backend/.gitattributes` 是 `e4c7a63f…`，根目錄 `.gitattributes` 是 `f2cec03e…`。
- 退役字樣的 `git grep -nP 'cg2_register(?!s)|cg2-register|cg2-preflight|verify_cg2_instruction'` 對 `apps/stock-desk` 零命中。
- ruff check：All checks passed。ruff format --check：550 files already formatted。mypy app tests：no issues found in 537 source files。
- `pytest tests/test_gap_check_flow.py tests/test_gap_check_logic.py`：203 passed（已推送的 commit 本身，約 105 秒）。

## 第二件：第 90 行舊 regex 評估（只提案，未 commit）

**提案檔**：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gap_check_regex_proposal.diff`
- 內容：`gap_check.py` 一行改動，加上 `tests/test_gap_check_logic.py` 新增 50 行。
- 我為了驗證曾暫時套用，存完 diff 後已 `git checkout --` 還原。工作樹乾淨，HEAD 仍是 `1faae4a`，沒有 commit 也沒有推送。

**用途與影響**
- `env_file_sets_db_path()`（第 758 行）逐行用 `ENV_KEY_PATTERN.match` 找 app 目錄 `.env` 有沒有設 `STOCK_DESK_DB_PATH`。preflight 在複製任何東西之前呼叫它，命中就 `RunStop("env_file_db_path")`。
- 擋的原因是 `.env` 設了這個鍵，gap-check 就可能讀到真實 DB 路徑而不是複本。
- 只看鍵、不讀值。`test_ast_the_env_file_is_only_searched_for_the_key_never_read_for_values` 釘住這點，且要求函式 AST 仍含 `ENV_KEY_PATTERN.match(line)`。
- 目前 pattern 的漏洞：`export STOCK_DESK_DB_PATH=...` 與 `stock_desk_db_path=...` 認不出，守門被繞過，gap-check 會照跑。對 CEO 畫面的影響是「該擋沒擋」，而不是多出任何訊息。

**建議**
1. **要不要在合併前修**：建議修。原因是這是「該擋沒擋」的漏網，修法風險極小（一行 regex 加 flag，AST 斷言與 STOP 路徑不動），而合併後再改會讓 `script_sha256_lf` 再變一次。最後決定在你。
2. **diff 內容**
   - pattern 改為 `re.compile(r"^\s*(?:export\s+)?STOCK_DESK_DB_PATH\s*=", re.IGNORECASE)`，與 claims 修正後規格一致。
   - 正例 7 個：無空白、前後空白、`export`、`export` 多空白、小寫、`Export` 混合大小寫、首行 BOM。
   - 反例 7 個：`# ` 註解、`..._OTHER`、`X` 前綴、`exportSTOCK...`（無空白）、無 `=`、`OTHER=STOCK_DESK_DB_PATH=1`、`API_KEY=...`。
   - 都透過 `gc.env_file_sets_db_path(tmp_path/".env")`，另有一個斷言驗 pattern 字面與 `IGNORECASE`。
   - 「與 `claims._ENV_FILE_KEY` 相等」的斷言**不建議此時加**：gap-check 分支與我剛 fetch 的 `origin/product/stock-desk` 都沒有 `_ENV_FILE_KEY`。`claims.py` 在這兩處都是舊版，只有 `DB_PATH_ENV_VAR`。待新版 claims 合進來後，再另加相等斷言。
   - 驗證結果：新增測試 14 個全過。`test_gap_check_logic` 加 `test_gap_check_flow` 合計 218 passed。ruff、format、mypy 全綠。
   - 過程中一個 BOM 測試曾因我把 BOM 行放在第二行而失敗，BOM 只有首行會被 `utf-8-sig` 吃掉，這是我的測試寫錯，不是產品問題，已修。
3. **STOP 字面**：不變。`env_file_db_path` 仍是 `STOP: STOCK_DESK_DB_PATH is set in the .env file of the app.`，只是命中範圍變大。
4. **會不會動到凍結基準或被釘雜湊的檔**：不會。`pipeline_acceptance_bat_frozen.txt` 與 `tests/fixtures/.gitattributes` 都不動。`gap_check.py` 自身的 `script_sha256_lf` 是執行時計算並印出，不是被釘住的值，但這個值會隨之改變（我剛才的註解 commit 也已改變一次），所以 CEO 若有手抄舊雜湊要重對。

**沒有查證的事 / 需要你知道的**
- 同樣的舊 regex 還有兩份：`scripts/pipeline_acceptance_real.py:289` 與 `scripts/r2_first_run.py:35`，同樣漏 `export` 與大小寫。這兩份不在你的範圍，我沒動，請 tech-architect 決定是否一併處理。
- 第 90 行的 `Final` 型別標註我保留，沒改。
- 沒有核對 `claims._ENV_FILE_KEY` 的新版實際字面，因為兩條分支都還沒有。我只依你訊息給的規格。
- 沒有跑完整測試套件，只跑 gap_check 兩個檔，加上 ruff 與 mypy 全量。
- 沒有讀 `.env*`、沒碰 `data/`、沒執行 `.bat`，測試用 `tmp_path`。

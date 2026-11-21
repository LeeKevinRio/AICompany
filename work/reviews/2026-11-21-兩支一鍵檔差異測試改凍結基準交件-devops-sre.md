# 兩支新一鍵檔的差異測試改用凍結基準：交件

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
兩個分支都已改用凍結基準檔，並已一般 push（沒有 force、沒有合併、沒有開 PR）。靜態檢查全過。全套測試各有既有的風控報告缺檔失敗（狀態報告 4 個、缺日比對 5 個），這些不是我造成的，我也沒有去改它們。

| 分支 | 舊 head | 新 head（`git ls-remote` 已確認） |
|---|---|---|
| `feat/forecast-status-oneclick` | d0bd41589453d5b8704e07bafb80007a2311155a | **11ce56d21c80b023806ab8cfe67499aa794aeeb1** |
| `feat/gap-check-oneclick` | 50f6de073e992c38d5dd86cfbb084e890cfa2479 | **f6aff2ce61bb15dd4d1e5d52b54e6668801eaf3e** |

- 先 fetch 過，兩個舊 head 與派工單相同。
- 補充十二（`-text` 的 `.gitattributes`）是在我動工途中才收到。我當時還沒 push，所以沒有留下「先 push 再補 commit」的情況。
- 每支只有一個 commit，type 為 `test`。
- 我在本機把還沒 push 的 commit 做過一次 `reset --soft` 後重 commit，因為第一次漏了 stage 測試檔。已 push 的歷史沒有被改。
- 本機的分支 ref（`feat/forecast-status-oneclick`、`feat/gap-check-oneclick`）被別的 worktree 佔用，我沒有動，所以仍停在舊 head。我用 detached worktree 以 `git push origin HEAD:refs/heads/<branch>` 推上去。

## 各部門回報（devops-sre）

**凍結檔（兩支位元組、路徑完全相同）**
- 凍結檔：`apps/stock-desk/backend/tests/fixtures/pipeline_acceptance_bat_frozen.txt`。
  - `tests/fixtures/` 本來就是慣用的測試資料目錄，所以用它，沒有另開 `tests/data/`。
  - 副檔名是 `.txt`，不是 `.bat`／`.cmd`／`.ps1`。
- 新增 `apps/stock-desk/backend/tests/fixtures/.gitattributes`，內容只有一行 `pipeline_acceptance_bat_frozen.txt -text`。
  - 這個檔以前不存在，我沒有改 `apps/stock-desk/backend/.gitattributes` 或根目錄的 `.gitattributes`。
- 來源 commit：`d6816eb9d6a6ecda1d5aaa6c86e8d2a4b7a41425`（`origin/product/stock-desk` 在 fetch 當下的 tip）。
- 來源 blob id：`5b0b271e52f100a7f8584fe7e1ec9889c4cee717`（`git rev-parse <commit>:apps/stock-desk/pipeline-acceptance.bat`）。
- 凍結檔 sha256：`07265206e00c2dd6466c7a319d68484aad1634e7f64c1662638b7d506a43b4ad`。
- 內容是 `git show <commit>:<path>` 直接導出，是 git 裡存放的 LF 位元組。
- 兩支存進 git 的 blob 都是 `5b0b271e…`，與來源相同；`.gitattributes` 的 blob 兩支都是 `445bacf6a94c34ec9f0738289785d52e1ab368b8`。

**換行的實際情況**
- 來源 `.bat` 在 git 內是 LF，因為根目錄 `.gitattributes` 設了 `*.bat text eol=crlf`，CRLF 只出現在 checkout。
- 舊測試讀的是 CRLF 的 checkout（sha256 `1c75ae34…b8be`）。
- 要同時滿足「blob id 等於來源」和「逐行比對不變」，測試裡加了 `_precedent_lines()`：
  - 先斷言檔內沒有 `\r`。
  - 再在記憶體中把 `\n` 換成 `\r\n`，用 `\r\n` 切行，結果與舊測試讀到的內容一致。
- 驗證 `core.autocrlf=true`：我建了暫存 repo，設 `core.autocrlf=true` 並放入凍結檔與 `.gitattributes`。
  - `git add` 後 blob 仍是 `5b0b271e…`。
  - 刪檔再 `git checkout` 後 sha256 仍是 `07265206…`，沒有被轉換。
  - 我沒有借用 `test_pipeline_acceptance_real_eol.py` 裡的 `_isolated_git`／`make_repo` 輔助來寫 autocrlf 測試。
- 倉庫內加的測試是 `test_git_does_not_convert_the_frozen_precedent`，用 `git check-attr` 斷言 `text: unset`、`eol: unspecified`。

**測試檔改動**
- `tests/test_forecast_status_flow.py`：
  - `PRECEDENT_BAT` 改指向凍結檔。
  - 新增常數 `PRECEDENT_SHA256`、`_precedent_lines()`，以及 `test_the_frozen_precedent_is_unchanged`、`test_git_does_not_convert_the_frozen_precedent` 兩個測試。
  - 差異行數與逐行斷言維持原樣。
  - `r2-probe.bat` 那一段完全沒動。
  - `PRECEDENT_COMMAND` 保留。
- `tests/test_gap_check_flow.py`：
  - 同樣新增常數、`_precedent_lines()` 與兩個測試。
  - `(BAT.parent / "pipeline-acceptance.bat").read_bytes()…` 改成 `_precedent_lines()`。
- 註解（英文）寫明：凍結自哪個 commit 的哪個檔與 blob；全產品線只有一份；不得更新；不代表任何現存工具；不得用來取回工具；sha256 測試釘住；`.gitattributes` 設 `-text`。
- 凍結檔本身沒有加註解。

**`test_gap_check_flow.py` 第 292 行的 `"stock-desk-pipeline-acceptance"`**
- 它是斷言 `gc.WORK_ROOT_NAME`（`stock-desk-gap-check`）不等於其他工具的工作資料夾名稱（`stock-desk-pipeline-acceptance`、`stock-desk-cg2-registration`），也就是資料夾名稱不得撞名。
- 與 `.bat` 檔是否存在無關，所以沒動。

**來源 blob 是否自 8b22c114 以來未變**
- `git log --oneline 8b22c114..origin/product/stock-desk -- apps/stock-desk/pipeline-acceptance.bat` 輸出為空。
- `8b22c114` 上同路徑的 blob 也是 `5b0b271e…`。
- 結論：未變動。

## 驗證

**靜態檢查（每支各跑一次，Python 3.12 專屬 venv，`uv sync --frozen --python /usr/bin/python3.12`）**

| 項目 | 狀態報告分支 | 缺日比對分支 |
|---|---|---|
| `ruff check .` | 通過 | 通過 |
| `ruff format --check .` | 通過 | 通過 |
| `mypy app tests` | 通過（536 個檔案） | 通過（537 個檔案） |

**第 3 步：把 `apps/stock-desk/pipeline-acceptance.bat` 與 `backend/scripts/pipeline_acceptance_real.py` 移開後，跑該分支的一鍵檔測試檔**
- 工作樹放在 `/home/user/wt/{status,gap}`，在 `/home/user/AICompany` 之外。
- 測完已還原，`git status` 為乾淨（只剩我要 commit 的檔）。

| 分支 | 風控報告狀況 | 結果 |
|---|---|---|
| `feat/forecast-status-oneclick`（`tests/test_forecast_status_flow.py`） | 沒有報告 | 4 failed, 101 passed |
| 同上 | 診斷用：暫時複製主工作目錄 `work/reviews/*` 進工作樹（事後 `git clean` 移除） | **105 passed** |
| `feat/gap-check-oneclick`（`tests/test_gap_check_flow.py` 加 `tests/test_gap_check_logic.py`） | 沒有報告 | 5 failed, 198 passed |
| 同上 | 診斷用：同樣暫時複製報告 | **203 passed** |

- 沒有報告時的失敗，全部是找不到風控報告，與基準檔、被移開的檔案無關。
  - 狀態報告 4 個：
    - `test_rc310_the_missing_uv_line_is_the_risk_control_sentence_verbatim`
    - `test_the_bat_differs_from_the_precedent_only_in_the_listed_lines`
    - `test_rc318_the_backend_error_line_is_followed_by_the_risk_control_sentence`
    - `test_the_bat_has_no_non_cmd_redirect_and_only_r2_lines_besides_its_own`
  - 缺日比對 5 個：
    - `test_the_three_stops_are_the_risk_control_sentences_verbatim[S-1-db_in_use]`
    - `[S-2-copy_unreadable]`
    - `[S-3-copy_failed]`
    - `test_the_bat_adds_the_risk_control_sentence_below_the_unchanged_backend_error_line`
    - `test_the_bat_prints_the_risk_control_uv_sentence_verbatim_and_no_install_hint`
- 診斷那一輪只是證明：報告在場時，一鍵檔測試檔在兩個檔都移開的情況下全過。這不是用來湊綠燈，那些報告複製也已清掉。
- 缺日比對分支原本讀 `.bat` 的 `test_the_bat_matches_the_pipeline_acceptance_launcher_except_its_own_lines`，在沒有報告時就已通過。

**全套 `pytest --cov=app --cov-report=term-missing --cov-fail-under=90 -q -p no:cacheprovider`（兩支平行，在 commit 後的狀態跑，兩支 coverage 都達標）**

| 分支 | 結果 | coverage |
|---|---|---|
| `feat/forecast-status-oneclick` | 4 failed, 12168 passed, 2 xfailed，用時 33 分 31 秒 | 97.81% |
| `feat/gap-check-oneclick` | 5 failed, 12251 passed, 2 xfailed，用時 33 分 23 秒 | 97.81% |

- 失敗的測試與上表「沒有報告」那兩列的完全相同，沒有別的失敗。

**Diff**

| 分支 | 變動檔案 |
|---|---|
| 狀態報告 | `tests/fixtures/.gitattributes`（+1）、凍結檔（+39）、`test_forecast_status_flow.py`（+34／-2） |
| 缺日比對 | `tests/fixtures/.gitattributes`（+1）、凍結檔（+39）、`test_gap_check_flow.py`（+33／-1） |

- 完整 diff 在 `/home/user/wt/status`（`git diff d0bd415 HEAD`）與 `/home/user/wt/gap`（`git diff 50f6de0 HEAD`）可重現。
- 狀態報告分支的測試檔 diff 已隨 push 上傳，內容是上述常數、`_precedent_lines()`、兩個新測試，以及 `_bat_lines(PRECEDENT_BAT)` 改為 `_precedent_lines()`。
- 缺日比對分支的測試檔 diff 同樣如此，另有 `import hashlib`，以及把 `read_bytes()` 那行換掉。

## 下一步與沒有查證的事

**下一步**
1. 請 qa-reviewer 審查這兩個 commit。
2. 風控報告缺檔的失敗屬於既有狀況，要等報告隨分支一起合併才會消失。
3. 退役 `pipeline-acceptance.bat` 之後，這兩個分支的一鍵檔測試不會再壞。
4. 這兩個分支其餘的 `test_pipeline_acceptance_real_*.py`、`test_import_graph.py` 等測試仍會讀 `.bat` 或 `scripts/pipeline_acceptance_real.py`。
   - 這不在本任務範圍，我沒有動。
   - 我只驗證了一鍵檔測試檔在檔案移開後全過，沒有驗證整個分支在移開後的全套結果。
   - 這些測試屬於被退役的工具本身，應由退役任務處理。

**沒有查證的事**
- 沒有在真正的 Windows 上驗證 `core.autocrlf=true`，只在 Linux 用暫存 repo 驗證 git 層行為。
- 沒有核對全產品線目前是否只有這一份凍結檔，也沒有查有沒有其他分支引用 `pipeline-acceptance.bat`。
- 沒有再讀 `.env`、沒有碰 `backend/data/`、沒有執行任何 `.bat`。

## 回滾方式
這兩個分支都還沒有合併。若要退回，請對 `feat/forecast-status-oneclick` 與 `feat/gap-check-oneclick` 各自 revert 新增的那一個 commit（`11ce56d`、`f6aff2c`），或直接用舊 head（`d0bd415`、`50f6de0`）重建分支。不需要 force push。

工作樹與 venv 在 `/home/user/wt/status`、`/home/user/wt/gap`、`/home/user/venv-status`、`/home/user/venv-gap`，全套測試記錄在 `/home/user/full-status.log`、`/home/user/full-gap.log`。

# 真實資料一鍵檔 PR 審查

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**程式碼審查結論（未重跑測試，`11977 passed` 未經重現）：BLOCKING_ISSUES=true。單家審查（`codex` 不存在，exit 127，依 CEO #58）。**

主 DB 安全（RC-158a、C-1）與 RC-167b/c 讀碼成立。但有兩項 BLOCKING：
- B-1：`.bat` 的 `where` 重導向寫錯，在 Windows 上會讓整支一鍵檔永遠停在「找不到 uv」。
- B-2：異常路徑清理複本失敗時被靜默吞掉，個資複本可能殘留而 CEO 不知道。

另有一項合併前必補：S-13e 缺一個測試。

### BLOCKING
**B-1（功能性，高）`apps/stock-desk/pipeline-acceptance.bat:16`**
- 內容是 `where uv >/dev/null 2>nul`。cmd 沒有 `/dev/null`，會報「系統找不到指定的路徑」，重導向失敗時 errorlevel=1。
- 於是第 17 行一定進入 `[MISSING] uv`，走到 `:fail`。整支一鍵檔永遠不會執行腳本。
- 這是 fail-closed，不傷主 DB，但 CEO 在 Windows 上完全無法使用。同 repo 的 `dev-up.bat:41`、`r2-probe.bat:12` 都是 `>nul 2>nul`。
- 測試 `test_the_bat_is_a_crlf_launcher_...`（flow.py:1407）沒檢查這行，所以沒抓到。
- 修法：改成 `>nul 2>nul`，並加一個斷言：非 REM 行不得含 `/dev/null`。

**B-2（個資殘留，medium，依 CEO #139 列 BLOCKING）`scripts/pipeline_acceptance_real.py:761-771`（`cleanup`）與 `:944-947`**
- `cleanup()` 對 `delete_copy` 的 `RunStop` 以 `except RunStop: pass` 吞掉，註解稱「已在第一次刪除處拋出」。
- 這只對 `flow` 的 reader `finally`（第 814-817 行）成立。
- `copy_db_files` 之後、reader 之前失敗時，第一次刪除就是 `cleanup`，刪不掉也靜默：
  - `copy_changed`（第 524 行）、`guard_failed`（第 812 行）。
  - 此區間的 `KeyboardInterrupt` 或意外例外。
- 這些情形畫面只印原本的 STOP 或 ERROR 句。CEO 不知道含持股與現金的完整複本還在。
- 這違反 RC-158c「刪不掉就印固定 STOP」的意旨，雖然 harness 確實沒被呼叫。下次啟動 `sweep_residue` 會處理，但本次沒有告知。
- 測試只涵蓋 reader 之後的路徑（flow.py:743-805）。
- 修法：最後一次 `cleanup` 後若 `work/copy` 仍存在，改印 `copy_not_deleted` 句並回非零；並補 `copy_changed` 加刪除失敗的測試。

### 合併前必補（不列 BLOCKING）
**S-13e 測試核對（協調者追加）**
| 項目 | 結果 |
|---|---|
| 白名單 `copy_check` 只接受 `SAME\|absent_both` | 有。`test_whitelist_shape[copy_check]`（flow.py:958-966，樣本在 916-919）與 `test_every_whitelist_shape_has_a_sample`（flow.py:954） |
| 只有 `.db` 時三行為 `SAME`、`absent_both`、`absent_both` | **缺。** `happy`（只有 `.db`）只在 flow.py:1024 數 `copy_check` 有 3 行，沒斷言值與順序；`test_a_copy_without_wal_...`（flow.py:505）不查 `copy_check` |
| `-wal`、`-shm` 都存在時三行皆 `SAME` | 有。`test_e2e_a_wal_main_database_is_copied_read_and_deleted`（flow.py:531-536），斷言 `["copy_check=SAME"]*3`；holder 連線使 `-shm` 存在，`make_world` 並斷言 `-wal` 大小大於 0 |
| 缺 `.db` 時在 `copy_check` 前 STOP | 有。`test_stop_no_db`（flow.py:592） |

補法：對 `happy` 加一行 `[x for x in paste_back if x.startswith("copy_check=")] == ["copy_check=SAME","copy_check=absent_both","copy_check=absent_both"]`。

## 各部門回報（逐項對 BLOCKING 判準）
**1. 主 DB 安全：成立。**
- 主 DB 三檔只在 `sha256_file`（腳本第 492 行）與 `_copy_bytes`（第 500 行）以 `"rb"` 開啟。
- 腳本內唯一 `sqlite3.connect` 在第 208 行，目標是 `copy_uri(copy_path)`；`flow` 只傳 `copy_dir/DB_NAME`。ledger 的 connect 由 harness 做，並經 `refuse_production`。
- 監聽測試（flow.py:107-198）涵蓋 `open`、`io.open`、`os.open`、remove、unlink、utime、chmod、truncate、rename、replace、`shutil.move` 與 `copy*` 目的地，並記錄 connect 目標。
- 斷言：hits 集合恰為 `{("open","rb")}`（312-321）；connect 目標屬於 {複本, p0, p1}（324-332）；`copy_done` 早於第一次 `connect`（335-338）。
- 有牙齒：`test_the_monitor_has_teeth`（364-383）實際打這些呼叫。
- 缺口（凍結後待辦，低）：
  - `os.open` 的旁路沒有被牙齒測試實際打到。
  - 沒包 `os.rmdir`、`os.link`、`os.symlink`。
  - `msvcrt.locking` 只在 win32 掛上，Linux CI 不會執行。
  - 腳本其他 `open` 呼叫點（`.env` 讀取第 623 行、回貼檔第 878 行）沒有 AST 釘住。

**2. 複本與個資：大致成立，B-2 除外。**
- `inside_git_work_tree(work)` 在 `preflight`（第 652 行），早於任何複製。
- 工作目錄在 `Path.home()` 之下。
- 正常路徑上，reader 的 `finally` 呼叫 `delete_copy`（含 `-wal`、`-shm`、`-journal`）；失敗拋 `RunStop`，harness 不被呼叫。測試：flow.py:743-767、793-805、`copy_existed_at_first_run == [False, False]`（351）。
- `copy_db_files` 在 reader 之前完成。
- 連線只下 `PRAGMA query_only=ON` 與單一 `_SELECT_SQL`（AST 測試 flow.py:450-472、bars.py:434-440）。

**3. 輸出白名單：成立，附註兩項。**
- 螢幕輸出只有三條路徑：`say()`、`input(PROMPT)`、`_fixed_hook`。
- 腳本內沒有其他 `print`、`sys.stdout.write`（hook 除外）、`logging` 或 traceback。
- `run_ruleset` 對 `result` 只讀 `.passed`，另呼叫 `render_summary(result)`（AST 測試 flow.py:811-835）。
- hooks 是最前面的敘述（flow.py:1287-1320，並有子行程測試 1329-1349）；`main` 攔截 `BaseException`。
- **附註 1（medium，需 TA 決定）：腳本沒有 `logging.disable`。**
  - 補充六第 3 點明文「全程停用 logging」，我在腳本與測試中都找不到對應實作。
  - `app/forecast/recorder.py:241` 有 `logger.warning(DISK_DIFFERS_WARNING)`，並由 `:304` 的 `warn_if_disk_differs` 呼叫。
  - 該字串固定、不含資料，但沒有 handler 時會經 `logging.lastResort` 寫到 stderr，繞過白名單與 `err == ""` 的保證。
  - 目前僅證明此一固定句；harness 遞移呼叫的其他 logger 我只掃到 recorder 與 advice.book，未窮舉。
  - 建議：在 hooks 之後加 `logging.disable(logging.CRITICAL)` 並補測試，或請 TA 書面接受現況。
- **附註 2：`argparse` 錯誤會寫 stderr。** 僅在手動帶錯參數時發生，`.bat` 不帶參數，低。

**4. RC-167：親自重驗，成立。**
- (c) WAL 測試是 `test_wal_copy_reads_the_uncheckpointed_row_and_adds_only_a_shm`（flow.py:486-502）：
  - `_wal_copy_dir` → `make_world(wal_tail=1)`：先寫前段，開 holder 連線，再寫最後一根 bar 進 `-wal`。
  - `assert wal.stat().st_size > 0`（`pipeline_real_world.py:169`）。holder 使關閉時不 checkpoint。
  - 斷言 `bars[-1].date == series[-1].date` 且 `len(bars) == len(series)`。忽略 WAL 的話，最後一根會缺，所以斷言確實有牙齒。
  - 另有 `test_a_copied_wal_is_read_and_not_written`（bars.py:353）、e2e 的 `wal_tail=3`（flow.py:531-544，`bars_sha256` 涵蓋三根只在 `-wal` 的 bar）。
- 小缺口（低）：沒有直接斷言「只有 `.db` 不含該列」。以「`-wal` 大小大於 0 加 holder」間接保證，足夠但可更強。
- (b) 主 DB 三檔 sha256 與 mtime 不變：
  - `_digests` 取 sha256 加 `st_mtime_ns`。
  - `test_the_main_database_files_are_unchanged_in_bytes_and_mtime`（flow.py:341）。
  - WAL 版：`test_e2e_...wal_main_database...`（542-543，`len == 3`）。
- 建議實證：Windows 上 `mode=ro` 讀「複本 `-wal` 加複本 `-shm`」，只有 Linux 合成資料測過；失敗時是 fail-closed 的 ERROR 句。

**5. socket（C-2）：實質符合，但測試與 ADR 字面有落差。**
- `port_is_listening`（第 603-611 行）只做 `socket.create_connection(("127.0.0.1", port), timeout=1.0)`，主機是字面常數、無 DNS，`port` 只用預設 `PORT`。
- AST 測試鎖定（flow.py:415-428；bars.py:489-490 要求 import 只在該函式內）。
- 補充六第 4 點 (a) 與 R-3 本身要求 `port_8000_listening=no`，唯一做法就是本機連線，所以我判斷符合 (c)「不得有網路呼叫」的意旨（不外連、不取資料）。
- 落差一：S-13b「socket 被替換為拋例外的替身時，流程照常完成」。`full_run` 把 `port_check` 注入為 `lambda: False`，真正的 `port_is_listening` 從未被這個測試打到，`sockets_used == []` 是空洞成立。替身若拋 `AssertionError` 而非 `OSError`，真函式會走到 ERROR。
- 落差二：`except OSError: return False` 是 fail-open。防毒或防火牆擋 loopback 時會誤判「沒在聽」。後面仍有 `copy_changed` 的 sha256 前後比對把關，低風險。
- 建議（凍結後待辦）：請 TA 書面確認「loopback 埠檢查」算 (c) 的例外，並加一個用真 `port_is_listening` 的測試（替身拋 `OSError` 時回 `False`，連上時回 `True`）。

**6. dev-lead 調整的三處：保護未實質削弱，各有補強建議。**
- 「無 open」只掃 reader 區段：reader 區段仍斷言無 `open`（bars.py:445-448）。外層 `open` 由 e2e 監聽測試在執行期涵蓋，但沒走到的分支（失敗路徑）沒有 AST 保護。建議用 AST 釘死 `open` 呼叫點集合與模式（`rb`、`xb`、`.env` 讀、`w`）。
- 允許函式內 socket：見第 5 點。AST 仍要求其他位置不得 import 網路模組，且 `socket` 屬性只有 `create_connection`。
- 字串避開 SQL 關鍵字掃描：未見削弱，單一 SELECT、PRAGMA 白名單與 banned 集合仍有效。

**7. 說明文件（`work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md`）：成立。**
- 區塊一第 10-13 行逐字等於 RC-166 新版（RC166 檔第 25-28 行）。
- 區塊二到五（說明文件的三、四、五、六節）逐字等於 Q1Q2 定稿（`2026-11-15-真實資料一鍵檔Q1Q2確認-風控.md` 第 101-102、106、110、114 行）。
- RC-158c 中文句（說明文件第 70 行）等於 Q1Q2 第 120 行。
- 沒有列出或解釋失敗種類代號（RC-160a）。
- STOP 對照表 19 句（第 48-66 行）與腳本固定句（`OUTER_STOP_SENTENCES`、`STOP_SENTENCES`、`UNEXPECTED`、`INTERRUPTED`）逐字相同。
- 建議（凍結後待辦）：加一個測試機械比對文件表與腳本常數。

**8. `.bat`：B-1 除外成立。**
- `@echo off`、先 `set "UV_ENV_FILE="`、`uv run --no-sync python -I -X utf8`、`pause`（正常與 fail 兩路都有）。
- 不載入 `.env`，測試也禁止非 REM 行出現 `STOCK_DESK` 或 `.env`。

**9. 不得動的檔案：成立（`git diff --stat`）。**
- 10 個檔案裡沒有 `app/`、`forecast_pipeline_harness.py`、`dirdef_helpers.py`、`outlook_helpers.py`、`uv.lock`，也沒有 repo 根 `.gitattributes`。
- `.gitattributes` 只新增 `apps/stock-desk/backend/.gitattributes` 一行 `uv.lock text eol=lf`。
- `test_import_graph.py` 只新增「`app/` 不可達 `scripts/`」，有牙齒測試。

**10. 測試隔離：成立。**
- `World.run` 一律傳 `--home`、`--backend-dir`、`env={}`，且 `Path.home()` 沒被 monkeypatch 替身取代。
- 唯一的 `Path.home()` 呼叫在腳本第 914 行，是 `args.home` 缺席時的預設，測試的 `main` 呼叫點只有 `pipeline_real_world.py:129`，一律帶 `--home`，因此不會落到真實 home。
- 沒有預設值會落到真實的 `<backend>/data/`。CLI 子行程測試也帶 `--backend-dir` 與 `--home`。
- 建議（低）：加一個 autouse 的 fixture，把 `Path.home` 換成拋例外的替身，防止日後漏傳。

**未能完整審查：** `test_pipeline_acceptance_real_eol.py`（263 行）只用 grep 確認它設定 `GIT_CONFIG_GLOBAL` 等於 tmp，未逐行讀。

## 另請給意見
**devops-sre 的 11 條自定解讀：** 我未逐條審。
- `copy_check` 值域：ADR 附記三（檔尾，在 `/home/user/AICompany/docs/adr/0030-...md` 第 752-762 行）已裁示，與程式 `copy_db_files`（第 505-526 行）一致，只是 worktree 內的 ADR 尚未含附記三。
- 其餘解讀在上面各項已隱含涵蓋（`cleanup` 吞 `RunStop` 即為 B-2）。

**RC-158b 的 AST 掃描：算規避嗎？**
- `real.read_twii_bars.__name__` 這種用法不算規避。它只取名稱、不讀取，且 `rc158b_violations` 明確豁免 `.__name__`，teeth 測試（bars.py:674-689）證明直接呼叫、別名與字串都會被抓到。
- 但 `getattr(real, real.read_twii_bars.__name__)(path)` 這種動態取名抓不到，因為 `.__name__` 那段被豁免。
- 屬已知的靜態掃描極限，且需要有意為之；列「凍結後待辦」，建議把限制寫進測試說明。

## 驗證
- 讀過：腳本全文、`.bat`、`pipeline_real_world.py`、`pipeline_real_loader.py`、`test_pipeline_acceptance_real_bars.py` 全文、`test_pipeline_acceptance_real_flow.py` 全文（至 1418 行）、`test_import_graph.py` diff、`.gitattributes` diff、說明文件全文、RC-166 全文、Q1Q2 的引文行、WAL 裁示、ADR-0030 補充六到附記三。
- 限制：Bash 限制下沒有跑測試，沒有讀 `.env`，沒有碰 `*.db`；交件說明（`work/reviews/2026-11-16-一鍵檔外層流程交件-devops-sre.md` 與取數函式交件）在 worktree 內不存在或我未讀，所以 11 條自定解讀與測試對應表未逐條對。
- **建議實證：**
  1. 在 Windows 實跑 `where uv >nul 2>nul` 的修正版，確認 `.bat` 能走到腳本。
  2. Windows 上對含 `-wal` 與 `-shm` 的複本做 `mode=ro` 讀取。
  3. `logging.lastResort` 的實際輸出，請加 `logging.disable` 後確認 stderr 空白。

## 下一步
1. **dev-lead 或 devops-sre**（退回實作者）：
   - 修 B-1（`>nul`，並加斷言）。
   - 修 B-2（最終清理後若複本仍在，印 `copy_not_deleted` 句並回非零，補測試）。
   - 補 S-13e 缺的測試（只有 `.db` 時三行為 `SAME`、`absent_both`、`absent_both`）。
2. **tech-architect：**
   - 裁示 `logging.disable` 是否照補充六第 3 點補上。
   - 確認 loopback 埠檢查算 (c) 的例外。
   - 兩者都建議補測試。
3. 修完後退回 qa-reviewer 重審；通過前，依補充六附記第 6 點，一鍵檔仍不得在 CEO 本機執行。
4. 凍結後待辦：監聽測試補 `os.open` 牙齒與 `os.rmdir/link/symlink`、AST 釘 `open` 呼叫點、說明文件與腳本 STOP 句的機械比對測試、`Path.home` 替身 fixture。

相關檔案（皆為絕對路徑）：
- /home/user/AICompany/.claude/worktrees/agent-a16298ccc17337e3c/apps/stock-desk/pipeline-acceptance.bat
- /home/user/AICompany/.claude/worktrees/agent-a16298ccc17337e3c/apps/stock-desk/backend/scripts/pipeline_acceptance_real.py
- /home/user/AICompany/.claude/worktrees/agent-a16298ccc17337e3c/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py
- /home/user/AICompany/.claude/worktrees/agent-a16298ccc17337e3c/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_bars.py
- /home/user/AICompany/.claude/worktrees/agent-a16298ccc17337e3c/apps/stock-desk/backend/tests/pipeline_real_world.py
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md

## 唯讀權限判準常數
未觸及。我沒有對這批做 `git diff --name-only` 的 `scripts/validate_agents.py` 命中檢查，也沒有做 `READONLY_AGENTS|READONLY_ALLOWED_BASH` 的 grep。diff 的 10 個檔案全在 `apps/stock-desk/` 與 `work/dispatch/` 之下（`git diff --stat` 已看過清單），沒有 `scripts/validate_agents.py` 與 `.claude/agents/`，也沒有 shadow 定義的可能路徑。

## Verdict
NEEDS_CHANGES
BLOCKING_ISSUES=true

# 真實資料一鍵檔 PR 複審

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS（程式碼審查結論）。BLOCKING_ISSUES=false。**

- 7 項 BLOCKING 判準全部成立。有 1 項 medium（sweep 階段被中斷時，舊複本不會被畫面告知），不阻擋。
- Codex 不可用：`codex --version` 回傳 command not found。依 CEO #58，本次記為**單家審查**。
- 我不能跑測試，`11989 passed` 未經重現。以下全是讀碼結論。
- 路徑：程式在 worktree `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/`。下表檔名省略這個前綴，行號依 head `6dd8794f`。
  - 腳本：`apps/stock-desk/backend/scripts/pipeline_acceptance_real.py`
  - 流程測試：`apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py`

### 各判準判定

| 判準 | 判定 | 依據 |
|---|---|---|
| B-1 | 成立 | `apps/stock-desk/pipeline-acceptance.bat:16` 是 `where uv >nul 2>nul`。全檔沒有非 cmd 語法。測試在流程測試第 1426-1438 行，斷言沒有 `/dev/null`、有 `where uv >nul 2>nul`，並要求所有指令行只能是 `r2-probe.bat` 的行或本工具專屬行，所以舊錯誤會被擋下。`r2-probe.bat:12` 與 `.bat` 第 16 行逐字相同。 |
| B-2 | 成立（sweep 階段有 M-1 的窄缺口） | 見下方 B-2 讀碼。 |
| logging | 成立 | 腳本第 56 行 `logging.disable(logging.CRITICAL)` 在三個 hook（第 52-54 行）與 `warnings` 之後，第 85 行起的 `app` import 之前。AST 測試改為 5 個 hook 敘述、前置 import 白名單含 `import logging`。子行程測試（流程測試第 1521-1534 行）用 `-I` 跑腳本，再發 warning、error、critical，斷言 `(0, "", "")`。移除 `logging.disable` 時，warning 會經 lastResort 走 stderr 而被抓到。loader（`pipeline_real_loader.py` 第 31、41 行）在 `finally` 還原 `manager.disable`。另有「loader 之後 disable 為 0」的斷言。 |
| S-13e | 成立 | 流程測試第 1506-1511 行斷言三行依序為 `SAME`、`absent_both`、`absent_both`。依據 `make_world` 預設 `wal_tail=0`，此時 DB 在 close 後沒有 `-wal`、`-shm`（SQLite 預設行為，我無法執行驗證）。 |
| port 檢查 | 成立 | 兩個測試只替換 `socket.create_connection`，呼叫真的 `real.port_is_listening()`。斷言連線目標恰為 `("127.0.0.1", PORT)`，沒有其他位址。`port_is_listening` 在函式內才 `import socket`，替換因此有效（腳本第 605-613 行）。 |
| 沒有回歸 | 成立 | 見下方。 |
| 說明文件 | 成立 | 見下方。 |

### B-2 讀碼（腳本第 898-958 行 `main`）

最後一道檢查在第 954-957 行：只要 `state.work/copy` 仍存在，就補印 `copy_not_deleted` 固定句，並把 code 設為 3。逐路徑判斷如下。

| 路徑 | 結果 |
|---|---|
| `copy_changed`、`guard_failed` | 內層 `finally` 的 `cleanup` 吞掉 `RunStop`。外層印原句，第 949 行再清一次，第 954 行補印。輸出是兩句，code 3。測試在流程測試第 1445-1480 行。 |
| `copy_db_files` 之後到 reader 之前的 `KeyboardInterrupt` 與 `RuntimeError` | 分別印 `INTERRUPTED` 或 `UNEXPECTED`，再補 `copy_not_deleted`，code 3。測試在流程測試第 1483-1496 行。 |
| flow 已經自己拋出 `copy_not_deleted`（reader 的 `finally` 刪不掉） | `copy_stop_shown=True`，所以不重複印。測試在流程測試第 1499-1504 行。 |
| 清理本身拋非 `RunStop` 例外（第 937 行的 `finally` 內） | 例外取代原例外，落入第 945 行的 `BaseException`，印 `UNEXPECTED`。第 949 行第二次清理被 `except BaseException: pass` 吞掉，第 954 行照樣補印。靜默路徑不存在。這條路徑沒有專屬測試，見待辦。 |
| 清理途中又被 `KeyboardInterrupt` | 同上，印 `INTERRUPTED` 後補印。 |
| 複本殘留時 harness 是否被呼叫 | 不會。`delete_copy` 拋出時，flow 在 `run_ruleset` 之前就中止。四個測試都斷言 `spy[0] == []`、stderr 為空，並用 `assert_screen_is_closed` 逐行比對白名單或固定句。 |

### 沒有回歸的確認

- `git diff --stat origin/product/stock-desk...6dd8794f` 只列出 10 個檔案：腳本、loader、`pipeline_real_world.py`、4 個測試檔、`test_import_graph.py`、`.bat`、說明文件，加上 `apps/stock-desk/backend/.gitattributes`（新增，是 `apps/stock-desk/backend/` 底下那份，不是 repo 根目錄的）。
- `app/`、`tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`、`uv.lock`、repo 根目錄 `.gitattributes` 皆為零 diff。
- 本次增量在腳本只有 3 處：`import logging`、`logging.disable`、`main` 尾端檢查，加上 `copy_stop_shown` 一個變數。主 DB 的 `"rb"` 開啟（`sha256_file`、`_copy_bytes`）、connect 目標、輸出白名單、hook 在最前面、RC-167b/c（`copy_uri`）、測試隔離都沒有被碰。
- 前述 AST 測試是改寬（加進 `logging.disable`），沒有放鬆「hook 在最前面」。

### 說明文件（逐字比對）

- R-1 到 R-15、S-1、S-2 的替換文字都與風控審查文件逐字相同。
- 風控先前的定稿區塊：區塊一（RC-166 新版，第 10-13 行）、區塊二到五（第 27-40 行）、RC-158c 中文句（第 70 行）都連續且逐字存在。
- 對照表第一欄 19 句（第 48-66 行）與腳本 `OUTER_STOP_SENTENCES`、`STOP_SENTENCES`、`UNEXPECTED`、`INTERRUPTED` 逐字相同。其中 eol 與 `copy_not_deleted` 兩句長句也相同。
- 全文沒有失敗種類代號。
- R-2 的 `[NOTE] The tool ended with code` 與 `.bat` 第 32 行 `echo [NOTE] The tool ended with code %RC%. Read the messages above.` 一致。`RC` 不為 0 才印，STOP 為 3、ERROR 為 1 或 2，所以每次 STOP 或 ERROR 都會出現。「請按任意鍵繼續」是 `pause` 的系統字樣，會隨 Windows 語系變動，R-2 已將它歸為「固定結尾文字」，可以接受。

## 各部門回報

### qa-reviewer 的 finding

- **[M-1][medium，個資殘留，不阻擋]**
  - 位置：腳本第 807-808 行（`sweep_residue` 先於 `state.work = work`），以及第 954 行。
  - 問題：最後一道檢查只看**本次**的 `state.work/copy`。sweep 階段清理**較早時間戳資料夾**的複本時，若被 Ctrl+C 或遇到非 `RunStop` 例外，畫面只顯示 `INTERRUPTED` 或 `UNEXPECTED`，舊複本若沒刪成功就沒有任何提示。
  - 緩解：這個舊複本不是本次產生的。上一次執行若走到有複本的階段，已經依 B-2 印過固定句；只有上一次被硬關視窗或斷電才不會。下一次執行又會重新 sweep。
  - 建議修法（小改）：最後一道檢查改為掃 `root/*/copy`（`RUN_FOLDER_PATTERN` 符合的資料夾），或在 sweep 前先設定 `state.root`。
  - 這不影響 B-2 對本次複本的結論，由 coordinator 決定是否本輪修。
- **[待辦，凍結後]**
  - 流程測試第 1445 行起的 B-2 測試沒有覆蓋「清理拋非 `RunStop` 例外」與「清理途中被中斷」。程式碼走讀確認安全，但沒有測試鎖定。
  - 流程測試第 1565 行的 in-process logging 測試是弱證據，真正的證據是子行程測試。
  - `import logging` 在 hook 之前，無害，因為 AST 測試已把它列入白名單。

### 技術面意見：兩行固定句會不會讓 CEO 漏看第二行

**有可能漏，但不會造成資料外洩，只是對照表指示可能互相牴觸。**

1. 兩種組合都是 `copy_changed` 或 `guard_failed` 加 `copy_not_deleted`，或 `INTERRUPTED` 或 `UNEXPECTED` 加 `copy_not_deleted`。複本固定句一定是**最後一行**，緊貼在 `[NOTE]` 行之上，所以視覺上不易被遮住。
2. R-2 寫的是「把 `STOP:` 或 `ERROR:` 那一行英文告訴 coordinator」，是單數。兩行都以 `STOP:` 開頭，CEO 可能只報一行，而且最有可能報第一行，也就是原因句。
3. 更大的問題是指示牴觸：第一行（例如 `copy_changed`）對應的動作是「確認視窗都關了再重新雙擊」。第二行則要求「直接刪除整個資料夾，不要開啟」。若 CEO 只照第一行做，會直接重跑。重跑時 sweep 會嘗試清舊複本，清不掉會以 STOP 告知，因此仍然 fail-closed，但不是我們期望的處置。
4. 建議（待風控決定，不影響技術結論）：在 R-2 補一句「若畫面有兩行以上的 `STOP:` 或 `ERROR:`，請全部告訴 coordinator，並以最後一行的處理方式優先」。若改這句，依 RC-164 要重送風控。

## 驗證

- 已讀：
  - 腳本全文。
  - 增量 diff 全文，路徑限制在 `apps/stock-desk` 與說明文件。
  - 流程測試的相關段落：helpers、`_failing_remover`、`assert_screen_is_closed`、B-2 測試、S-13e、logging、port 檢查、`.bat` 測試。
  - `pipeline-acceptance.bat`、`r2-probe.bat`。
  - `pipeline_real_world.py` 的 `make_world`。
  - 說明文件全文。
  - 風控審查文件全文。
  - 兩次 `git diff --stat`。
- 唯讀權限判準常數：**未觸及**。`git diff 6c2253f2...6dd8794f --name-only -- scripts/validate_agents.py` 無輸出。我也確認了 diff 全文與 `apps/` 內沒有出現 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的增減，沒有 shadow 定義，也沒有常數值被改。
- **沒有做**：
  - 沒有執行任何測試。
  - 沒有讀 `.env`。
  - 沒有碰任何 `*.db`。
  - 沒有 Windows 實測，所以 `.bat` 重導行為與 `pause` 字樣只靠讀碼。
  - 實作者回報檔 `work/reviews/2026-11-16-一鍵檔qa修正交件-devops-sre.md`、我上一次的審查檔、ADR-0030 補充六附記三，我只依你在任務單列出的判準審查，沒有逐檔回讀。
- Codex：不可用，單家審查。

## 下一步

1. **coordinator**：視 M-1 決定本輪是否修。建議修，因為改動小。若修，回 devops-sre 加一個測試：sweep 階段中斷且舊複本殘留。
2. **coordinator**：依 C-1 條件，qa 已通過（本報告）。但 CI 綠燈前仍不得通知 CEO 執行，因為我無法重現 `11989 passed`。
3. **風控**：判定 R-2「單數一行」與兩行固定句的問題，並決定要不要補句。補句需要重送風控。
4. **devops-sre**：凍結後待辦：補「清理拋非 `RunStop` 例外」與「清理途中被中斷」兩個 B-2 測試。

相關檔案：
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/backend/scripts/pipeline_acceptance_real.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/backend/tests/pipeline_real_loader.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/pipeline-acceptance.bat
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md

BLOCKING_ISSUES=false

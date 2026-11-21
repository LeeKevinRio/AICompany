# dev-up.bat 第 191 行改字與內部文件補充交件（RC-446、RC-452、RC-453）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

RC-446、RC-452、RC-453 已做完，三個 commit 已分開，新分支已 push。

- 分支 `chore/dev-up-scheduler-fail-wording` 由 `docs/host-manual-ceo-notice`（`9a7bdef52dfe9c0b09f94f38d319500e82869470`）開出。
- 新 head：`97e11c1c7fd0d77cb8522b640ee1a75c4689bd68`，`git ls-remote` 確認遠端相同。
- 沒有動 `chore/dev-up-missing-tool-wording` 與 `docs/host-manual-ceo-notice`，沒有 amend、rebase、force push。

**commit trailer 偏差，請知悉。** 你要求的 `Co-Authored-By` 是另一個模型名稱，我改用系統提示指定的 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`（`Claude-Session` 照用）。理由是 agent 訊息不能取代系統指定的 attribution。要改的話需由你或使用者本人確認。repo 檔案內容沒有寫任何 model ID，只有 commit trailer 有。

## 各部門回報

### 三個 commit

| 順序 | SHA | 動到的檔 |
|---|---|---|
| A（程式） | `aafba4376aa682123290c611bdb266fefd2d6340` | `apps/stock-desk/dev-up.bat`（第 191 行）、`apps/stock-desk/backend/tests/test_dev_up_missing_tool_wording.py` |
| B（內部文件） | `acfa58a732391fca288ecd6ab046a07b09066889` | `work/dispatch/2026-11-21-缺工具時的安裝引導-內部-devops-sre.md`（5.2 的 `[FAIL] scheduler` 列） |
| C（內部文件） | `97e11c1c7fd0d77cb8522b640ee1a75c4689bd68` | 同一份內部文件 |

**commit A**
- `dev-up.bat` 第 191 行換成風控 RC-446 的定稿整行。
  - 腳本從風控檔案第 189 行程式讀入，逐字、ASCII。
  - 腳本內先斷言舊行內容與行數 307（含檔尾空片段）再寫入。
- 測試檔新增 4 條：
  - (a) 整行逐字等於定稿，且仍在第 191 行、上一行是 `call :check_scheduler`。
  - (b) `[FAIL]` 側文字純 ASCII，且不含 `( ) & | < > ^ % ! ; "`。
  - (c) `[OK]   scheduler running - window 'stock-desk scheduler'` 側不變。
  - (d) 新句子雖以 `Tell the coordinator.` 結尾，但不是整行 `echo Tell the coordinator.`，所以不影響既有計數測試。
- 既有計數測試 `test_the_coordinator_sentence_appears_exactly_the_expected_number_of_times` 實跑通過。

**commit B**
- 5.2 表中 `[FAIL] scheduler` 那列同步為 `not found running`。
- 該列只寫字樣開頭並註明整行見風控判定檔，沒有把整行複製進去。

**commit C**
- 5.2 新增三列，格式照既有表，寫明前面已執行與尚未執行的步驟：
  - `Cancelled.`（82 行，經 83 行進 `:fail`）：寫明發生在 `git pull` 與停止舊程序之前，前一行（79 行）會印出目前分支名稱。
  - `Cancelled. Not starting a second copy.`（263 行，對應埠的 Stop 回答 N）。
  - 同一句（296 行，對應舊 scheduler 的 Stop 回答 N）。
- 刪掉「本表沒有列 `Cancelled.`……另行判斷」，改為引用 RC-449、RC-450；`[NOTICE]` 維持不列。
- 5.3 新增第 8 點，只引用編號：
  - `Cancelled.` 第一次回覆用 R3-0C，不用 R3-0。
  - 82 行轉 devops-sre；預測紀錄期間同日通知 tech-architect。
  - 82 行不得用 R3，不得問 CEO 分支或原因，不得叫 CEO 執行 git 或按 `Y`。
  - 263、296 行照 RC-438 判斷，含 (e)。
- 5.3 第 7 點補三件事，只引用編號：
  - `[OK]` 也不得當成記錄的依據（RC-444）。
  - CEO 只回「已執行」時，依 RC-447 追問一次。
  - 「R3 的送出條件以 RC-438 全文為準，本節只摘列部分」（點出 (f)、(g)）。
  - 送了 R3-0 或 R3-0C 而不送 R3 時，解除字面先送風控（RC-437、RC-449）。
- 第 6 節（qa 備註 4）：「另案處理」改為「由 `docs/host-manual-ceo-notice` 分支依 RC-428、RC-429 處理，截至本文件撰寫時尚未合併」。
- qa 備註 5 我沒有另外處理，因為我手上沒有該備註原文。
- 沒有抄入任何對 CEO 的訊息字面；R1、R2、R3、R3-0、R3-0C、追問句、解除句都只引用名稱與編號。

## 驗證

**diff 範圍**（對 `9a7bdef…`）
- `--stat`：3 個檔，65 insertions、5 deletions。
- `--numstat`：
  - 測試檔：`51 0`。
  - `dev-up.bat`：`1 1`。
  - 內部文件：`13 4`。
- `dev-up.bat` 的 hunk 只有一行：
```
@@ -191 +191 @@ call :check_scheduler
-if errorlevel 1 (echo [FAIL] scheduler not running - check the 'stock-desk scheduler' window. The app still works but there is no background refresh or alerts.) else (echo [OK]   scheduler running - window 'stock-desk scheduler')
+if errorlevel 1 (echo [FAIL] scheduler not found running - while it is not running there is no background refresh, no alerts and no forecast recording. Do not try to fix it yourself. Tell the coordinator.) else (echo [OK]   scheduler running - window 'stock-desk scheduler')
```

**位元組核對**
- 倉庫 index 內的 `dev-up.bat` 是 LF，`.gitattributes` 設 `*.bat text eol=crlf`，工作樹是 CRLF。
- 所以我把舊版（`git show HEAD:`）換成 CRLF 後逐行比對新檔，結果如下。
  - 新檔純 ASCII：True。
  - CRLF、LF、CR 各 306，全檔都是 CRLF。
  - 行數：舊 306、新 306。
  - 逐行不同處：只有第 191 行。

**測試與品質門檻**
- `test_dev_up_missing_tool_wording.py` 全檔：23 passed。
- 名稱含 `dev_up`、`bat`、`import_graph` 的檔共 32 passed：
  - `test_dev_up_missing_tool_wording.py`
  - `test_f9b_t12_label_verbatim.py`
  - `test_import_graph.py`
  - `test_playbook_classify_exit_batches.py`
- 名稱含 `lockfile_eol` 的檔不存在。內容含 `dev-up.bat` 的另一個檔 `test_r2_first_run.py` 也包含在後面的全套裡。
- 與 CI 相同的指令（`.github/workflows/stock-desk.yml`）：
  - `uv run ruff check .`：All checks passed。
  - `uv run ruff format --check .`：547 files already formatted。
  - `uv run mypy app tests`：no issues in 535 source files。
  - `uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=90`：**12090 passed、0 failed、2 xfailed**（1801.78 秒），覆蓋率 **97.81%**，門檻 90% 已達。
- 環境：
  - CI 的 setup-python 是 3.12，我的環境是 Python 3.13（`.venv/lib/python3.13`）。
  - CI 用 `uv sync --frozen`；我用 `uv sync --locked`，同樣依 lockfile。
  - 測試沒有執行任何 `.bat`，讀的是檔案位元組。

## 下一步

1. qa-reviewer 複審 `dev-up.bat` 一行與新測試，並核對 RC-452 的內部文件（含沒有對 CEO 的字面）。
2. 送風控對第 191 行做單項確認（RC-446）。
3. 合併順序（RC-446 的最晚時點是接線 PR 合併之前，且不得與接線 PR 同一個 PR）：
   - 本分支疊在 `docs/host-manual-ceo-notice` 上，後者又疊在改字分支上。
   - 合併順序必須是改字分支、手冊分支、本分支，且是三個獨立 PR。
4. 請 coordinator 注意：
   - 本地分支 `chore/dev-up-missing-tool-wording` 被另一個工作樹（`agent-a9629b70c09d9bd6a`）佔用。
   - 我先前是以 detached HEAD 推到該遠端分支，那個工作樹的本地分支會落後，需要時先 `git pull`。
5. 前次交件中，第三件（心跳責任確認書）仍在 scratchpad：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/D-10心跳責任確認-devops-sre.md`，待 coordinator 覆蓋回 `work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`。其中 (五) 與 RC-448～RC-453 尚未同步，例如 R3-0C。

**沒有查證的事**
- Windows 實機一律沒有驗證：`choice`、`taskkill`、`netstat`，以及新 `[FAIL]` 行實際印出的樣子。
- `:check_scheduler` 的假陰性（PowerShell 查詢失敗也會回傳 1）是依風控與我讀程式的推論，沒有實機驗證。
- CI 的實際遠端執行結果（GitHub Actions）沒有看，只在本機用相同指令跑。
- `dev-up.sh` 第 122 行的同義舊字面依指示沒有改。
- 風控 RC-455 之後的內容我只讀了 RC-446、RC-449～RC-453 與相關段落，沒有通讀整份判定檔。

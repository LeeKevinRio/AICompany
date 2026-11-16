# 真實資料一鍵檔 M-1 修正審查

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

程式碼審查結論：PASS。BLOCKING 判準 1 到 7 全部成立。我沒有重現 `11995 passed`，也不能跑測試。
另有 1 項 medium：`copy_left_behind` 在 `main` 的最後一道檢查中沒有攔截 `OSError`，會讓「清理中途失敗」這條路徑多出一個 traceback。建議在凍結前順手修，但不擋合併。
Codex 不可用：`codex --version` 回 exit 127（command not found）。依 CEO #58 記為「單家審查」，未執行 `/review`。

## 各部門回報

判準 1，M-1 已修，成立。
- `state.root = root` 在 `/scripts/pipeline_acceptance_real.py:816`，位於 `preflight` 與 `sweep_residue`（821）之前。
- sweep 階段拋 `KeyboardInterrupt` 或 `RuntimeError` 時，`cleanup` 只處理 `state.work`。sweep 時 `state.work` 仍是 `None`，所以舊複本留著。
- 最後一道檢查 `copy_left_behind(state.root)`（968）掃整個 root，涵蓋本次資料夾與所有符合 `RUN_FOLDER_PATTERN` 的舊資料夾。
- `code != 3 or not copy_stop_shown` 的條件下，code 2 與 code 1 都會補印，並回 3。

判準 2，順序與句數，成立。
- 原句在前，`copy_not_deleted` 在後，只印一次。
- sweep 自己拋 `RunStop("copy_not_deleted")` 時，`copy_stop_shown` 為 True，不重複印。
- diff 沒有新字串，固定句集合與白名單未動。風控「原句在前、`copy_not_deleted` 在後」的前提仍成立。

判準 3，沒有新的靜默路徑，但有一條新的非白名單輸出路徑，列 medium。

**[medium] 最後一道檢查沒有攔截 `OSError`，會產生 traceback**
位置：`/scripts/pipeline_acceptance_real.py:764-773`（`copy_left_behind`），呼叫處在 968，位於所有 `try` 之外。

在 Python 3.12 下（`pyproject.toml` 要求 >=3.12），`Path.is_dir` 與 `Path.exists` 只吞 ENOENT、ENOTDIR、EBADF、ELOOP。`root.iterdir()`，以及 `(folder / COPY_DIR).exists()` 遇到 EACCES 時，都會拋 `PermissionError`。

- 畫面會印什麼：Python 預設的 traceback，內含完整路徑與 `stock-desk-pipeline-acceptance`。這違反 D-4 與 #149 的「畫面只有固定句」。
- 結束碼：1（未處理例外）。
- 新增的退步：舊程式的最後一道檢查只看 `state.work`，不會走到這裡。
- 具體情境：某個舊資料夾（名稱符合格式）權限被改壞，`sweep_residue` 在 593 行拋 `PermissionError`。畫面先印 `UNEXPECTED`，接著最後檢查又拋同樣的錯誤。結果是固定句加 traceback，結束碼 1，原本是乾淨的 `UNEXPECTED`。
- 純粹只有 `root.iterdir()` 拋錯而 sweep 沒先拋，需要 root 在兩次讀取之間才變得不可讀，機率極低。上述舊資料夾權限壞掉的情境較實際。
- 不會碰到主 DB，也沒有個資殘留，所以按 CEO #139 列 medium，不列 BLOCKING。
- 建議修法：在 `main` 用 `try/except OSError` 包住 `copy_left_behind`，並 fail-closed。無法確認時視為複本可能還在，印 `copy_not_deleted` 並回 3，不新增句子。另補一個測試，讓 `iterdir` 或 `exists` 拋 `PermissionError`，斷言輸出是固定句。若 CEO 認為要凍結，也可列凍結後待辦，但這是一行修法，建議現在做。

`copy_left_behind` 對 symlink 與權限的行為：
- 名稱符合格式的 symlink 會被跳過（`is_symlink`，770 行），與 `sweep_residue`（589 行）一致，不會跟進 symlink 去看目標。
- 不是資料夾的同名檔案：`(folder / "copy").exists()` 對檔案底下的路徑回 False（ENOTDIR 被吞），不會誤報。
- 權限不足的子資料夾：如上，在 3.12 會拋出，沒有被攔截。

判準 4，B-2 無回歸，成立。
- diff 沒動既有 B-2 測試，順序精確比對的斷言不變。
- 新行為對 B-2 情境是超集：本次資料夾的 `copy` 仍被掃到。

判準 5，主 DB 安全，成立。
- 掃描根是 `home / "stock-desk-pipeline-acceptance"`（277 行）。
- 只做 `iterdir`、`is_symlink`、`exists`，不刪、不寫。不會碰 `<backend>/data/`。

判準 6，新測試有牙齒，成立。
- sweep 中斷兩個情境（`KeyboardInterrupt`、`RuntimeError`）：remover 對舊資料夾的 `stock-desk.db` 拋錯。`delete_copy` 逐檔呼叫 remover（569 行），所以真的會觸發。
  - 非 `OSError` 的例外不被 `delete_with_retry` 吞掉，會一路傳到 `main`。
  - 兩者都精確比對 `[first, copy_not_deleted]`、結束碼 3、`copy` 仍在、harness 未被呼叫。
- 反例（舊資料夾只有 `p0`、`p1`）：結束碼 0、不印 `copy_not_deleted`、`p0` 被掃掉。
- 函式本身：涵蓋 `notes`、`20260101` 不算，以及 `None`、不存在的 root、符合格式的資料夾。
- 兩個補的待辦測試（清理拋非 `RunStop`、清理在兩個 ledger 之間被中斷）精確比對輸出與結束碼，並檢查無殘留。
- 缺口：沒有 `OSError` 的測試，與上面的 medium 對應。
- devops-sre 自述反向驗證為 2 failed、7 passed；我未重現，僅在閱讀上確認邏輯成立。

判準 7，diff 範圍，成立。`git diff` 只有 `scripts/pipeline_acceptance_real.py` 與 `tests/test_pipeline_acceptance_real_flow.py` 兩個檔，說明文件、`app/`、harness、`uv.lock` 都沒動。

## 驗證

- 方式：`git diff 2a13e61..1a6dbb2` 全文，加上 worktree 內 `pipeline_acceptance_real.py` 的 `main`、`flow`、`sweep_residue`、`delete_copy`、`delete_with_retry`、`copy_left_behind` 逐行閱讀。
- 未做：沒有跑測試，沒有重現 11995 passed。
- 唯讀權限判準常數：未觸及。兩道檢查（`scripts/validate_agents.py` 檔名、`READONLY_AGENTS|READONLY_ALLOWED_BASH`）在此 diff 範圍皆為空，改動全在 `apps/stock-desk/backend/` 底下。
- 不用 `--staged`，直接以 `2a13e61..1a6dbb2` 取 diff。

## 下一步

1. 凍結前建議：devops-sre 在 `main` 以 `try/except OSError` 包住 `copy_left_behind`，並 fail-closed，同時補一個測試。屬於小修，改完不必再走完整重審，只需確認不新增句子、順序不變。
2. 若 CEO 決定不修，請把它登記為凍結後待辦，並在交件記錄中註明「權限被改壞的舊資料夾會出 traceback」。
3. 風控的前提（原句在前、`copy_not_deleted` 在後）沒有被動搖，文件審查流程照舊。
4. 檔案：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_oneclick/apps/stock-desk/backend/scripts/pipeline_acceptance_real.py`、`.../tests/test_pipeline_acceptance_real_flow.py`。

## Verdict
PASS（單家審查，Codex 不可用；含 1 項 medium）
BLOCKING_ISSUES=false

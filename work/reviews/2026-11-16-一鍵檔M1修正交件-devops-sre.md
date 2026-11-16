# 真實資料一鍵檔 M-1 修正交件

- 審查者：devops-sre
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

qa 複審的 M-1 已修完。已 fast-forward push（2a13e61..1a6dbb2），`git ls-remote` 確認遠端 head 等於本地 head。說明文件一個字都沒動。

**新 head（40 碼）：`1a6dbb24e14faef12f77a1ee382b180e9c7e1c47`**

- 開工前先 fetch，並 fast-forward 到 `2a13e61311690e8d6110cd9695509a6e9e9ac062`（coordinator 的兩個文件 commit）。
- 本輪只有一個 commit：`1a6dbb24e14faef12f77a1ee382b180e9c7e1c47`，`fix:` 開頭，署名行照系統規定。
- 這個 commit 只改兩個檔：`scripts/pipeline_acceptance_real.py` 與 `tests/test_pipeline_acceptance_real_flow.py`。
- `app/`、harness、`uv.lock` 相對 `origin/product/stock-desk` 的 diff 為空。

## 各部門回報

**修法（M-1）**
- `State` 新增 `root`，在 `flow` 一開頭、`sweep_residue` 之前就設好。
- 新函式 `copy_left_behind(root)` 掃整個工作根目錄，只看名稱符合 `RUN_FOLDER_PATTERN` 且不是 symlink 的資料夾；其底下只要還有 `copy` 就回 `True`。本次的資料夾也包含在內。
- `main` 最後一道檢查改用它。畫面上的順序不變：原本的 STOP 或 ERROR 句在前，`copy_not_deleted` 在後，只印一次，結束碼 3。
- 沒有新增任何句子，固定句集合與白名單都沒動。

**新測試**（`tests/test_pipeline_acceptance_real_flow.py`）
- `test_m1_a_sweep_that_fails_and_leaves_an_old_copy_shows_the_copy_stop`，參數化兩種情形：
  - `KeyboardInterrupt`：畫面依序為 `INTERRUPTED`、`copy_not_deleted`。
  - `RuntimeError`：畫面依序為 `UNEXPECTED`、`copy_not_deleted`。
  - 兩者都斷言結束碼 3、harness 沒被呼叫、每行 fullmatch 固定句，且舊複本確實還在。
- `test_m1_an_old_run_with_only_ledger_folders_does_not_show_the_copy_stop`：反例。舊資料夾只有 `p0`、`p1` 時不印 `copy_not_deleted`，結束碼 0，且舊的 `p0` 被掃掉。
- `test_m1_the_check_looks_only_at_run_folders_with_a_copy`：直接測 `copy_left_behind`。名稱格式不符的資料夾（`notes`、`20260101`）不算；根目錄不存在或為 `None` 回 `False`。
- qa 列的兩個待辦測試，只補測試，沒改行為：
  - `test_qa_cleanup_raising_an_unexpected_error_is_the_fixed_error_sentence`：清理拋非 `RunStop` 例外時，畫面只有 `UNEXPECTED`，結束碼 1，無殘留。
  - `test_qa_cleanup_interrupted_between_the_two_ledgers_leaves_nothing`：清理在兩個 ledger 之間被中斷時，畫面只有 `INTERRUPTED`，結束碼 2，無殘留。

## 驗證

- **全套測試**：`uv run pytest --cov=app --cov-fail-under=90`，**11995 passed、2 xfailed**，覆蓋率 **97.80%**，耗時 31 分 52 秒。比上一輪多 6 個測試。
- **ruff check**：All checks passed。**mypy** `app tests scripts/pipeline_acceptance_real.py`：Success，534 source files。
- **反向驗證**：暫時把最後檢查改回只看本次 `state.work/copy`，`-k "m1_ or b2_"` 結果為 **2 failed、7 passed**。失敗的是兩個 sweep 中斷或例外的 M-1 測試；B-2 與反例仍通過，符合預期。還原後（以 `cp` 還原備份）`-k "m1_ or qa_ or b2_"` 為 11 passed。
- **push**：輸出 `2a13e61..1a6dbb2`；`ls-remote` 回 `1a6dbb24e14faef12f77a1ee382b180e9c7e1c47`。

## 下一步

1. **qa-reviewer**：請在 `1a6dbb2` 確認 M-1 與兩個待辦測試。
2. **coordinator**：風控審說明文件的流程照舊，我沒有動文件。
3. **已知限制**：
   - 檢查只看「名稱符合格式的資料夾底下有沒有 `copy`」，不列舉其中的檔案；`root.iterdir()` 若本身拋 `OSError`，沒有另外攔截。
   - Windows 上沒實測的部分與先前回報相同。

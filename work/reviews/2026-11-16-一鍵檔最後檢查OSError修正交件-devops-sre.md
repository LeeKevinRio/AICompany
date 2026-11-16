# 真實資料一鍵檔：最後檢查 OSError 修正交件

- 審查者：devops-sre
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

qa 的 M-2 已修。`main` 最後一道檢查遇到 `OSError` 時，一律視為「複本可能還在」，印 `copy_not_deleted` 固定句，結束碼 3。已 fast-forward push（1a6dbb2..052ac69），`git ls-remote` 確認遠端等於本地。說明文件、`app/`、harness 都沒動。

**新 head（40 碼）：`052ac698e5489936658a6caa873a7c6329c9a45b`**

本輪只有一個 commit：`052ac698e5489936658a6caa873a7c6329c9a45b`，`fix:` 開頭，署名行照系統規定。只改兩個檔：`scripts/pipeline_acceptance_real.py` 與 `tests/test_pipeline_acceptance_real_flow.py`。

## 各部門回報

**修法**
- 在 `main` 的最後一道檢查，用 `try/except OSError` 包住 `copy_left_behind(state.root)`。
- 拋 `OSError` 時視為 `left = True`（fail-closed）。
- 沒有新增任何句子。輸出順序不變：原句在前，`copy_not_deleted` 在後，只印一次，結束碼 3。

**修正前的實證**（你要求的第 1 點）
- 方法：用真實的 `python -I` 子行程，經 `runpy` 載入修正前的腳本，再呼叫 `main`。
- 情境：工作根目錄下有名稱符合格式的舊資料夾 `20260101-000000`。我用 monkeypatch 讓 `Path.iterdir`（或 `Path.exists`）拋 `PermissionError`，這樣 `sweep_residue` 先拋錯、最後檢查也拋同樣的錯。
- 結果，`iterdir` 與 `exists` 兩種情境完全相同：
  - 結束碼 **1**。
  - stdout 兩行，內容相同：`ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.`
  - 第一行來自 `main` 的 `except BaseException`，第二行來自 `sys.excepthook`（最後檢查在所有 `try` 之外，是未攔截例外）。
  - stderr 只有 uv 自己的 `UV_NATIVE_TLS` 棄用警告，不是腳本印的；**沒有 Python 的 traceback**。
- 判讀：你的推測成立，hook 擋住了 traceback。所以修正前**不算違反白名單**，畫面每行都是固定句。實際問題有兩個：
  - 固定 ERROR 句重複印了兩次。
  - 舊複本可能還在，畫面卻沒有 `copy_not_deleted` 提示。
  - 這是遺漏提示，不是洩漏。
- 修正後，同一個驅動腳本在同樣兩種情境下，stdout 為：
  - 第一行 `ERROR: unexpected failure; …`
  - 第二行 `STOP: the database copy could not be deleted, …`
  - 結束碼 **3**。

**新測試**（`tests/test_pipeline_acceptance_real_flow.py`）
- `test_m2_a_permission_error_in_the_last_check_shows_the_copy_stop`，參數化 `iterdir`、`exists`：畫面是 `[UNEXPECTED, copy_not_deleted]`，結束碼 3，stderr 為空，每行 fullmatch 固定句，harness 沒被呼叫。
- `test_m2_the_last_check_alone_failing_is_fail_closed_and_shown_once`：只有最後檢查失敗（替身 `copy_left_behind` 拋 `PermissionError`），畫面最後一行是 `copy_not_deleted` 且只出現一次，結束碼 3，每行 fullmatch。

## 驗證

- **全套測試**：`uv run pytest --cov=app --cov-fail-under=90`，**11998 passed、2 xfailed**，覆蓋率 **97.80%**，耗時 31 分 35 秒。比上輪多 3 個測試。
- **ruff check**：All checks passed。**mypy** `app tests scripts/pipeline_acceptance_real.py`：Success，534 source files。
- **反向驗證**：把 `left = True` 暫時改回 `raise`，`-k m2_` 的 3 個測試全部失敗；還原後 3 個全過。
- **push**：輸出 `1a6dbb2..052ac69`，`ls-remote` 回 `052ac698e5489936658a6caa873a7c6329c9a45b`。

## 下一步

1. **qa-reviewer**：請在 `052ac69` 確認 M-2。
2. **已知限制**：
   - Windows 上沒實測，與先前回報相同。
   - 上面的修正前實證用 monkeypatch 模擬 EACCES；本機以 root 執行，無法用真實的權限位元觸發 `PermissionError`。

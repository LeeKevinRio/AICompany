# CG-2 前置 PR 補測試確認與總結論

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
程式碼審查結論：兩個補測試設計成立，無 BLOCKING。我不能跑測試，`12053 passed` 未經我重現。Codex 不可用（codex: command not found），依 CEO #58 記為「單家審查」。

判準逐項：
1. 只動測試檔：成立。diff 僅 `tests/test_forecast_bootstrap.py`（+139、無刪除），`app/` 與其他測試沒動。
2. S-15a 第 1 點：成立。
   - 斷言精確為 `{(store.py,_write),(schema.py,create_schema)}`，與 `store.py:635`、`schema.py:415` 吻合。
   - 掃描涵蓋直接名稱、import 別名、屬性呼叫（含模組別名），另含 `getattr(m,"create_objects")`。
   - 牙齒測試涵蓋四種呼叫形式、模組層級、遮蔽用例（`create_objects = 1` 不算呼叫），並有真實 store.py 加 sneaky 呼叫者的反向檢查。
3. COMMIT 失敗測試：成立。
   - wrapper 只在 COMMIT 拋錯，其他 execute 轉給真連線；in_transaction、close、`__getattr__` 也轉給真連線。
   - 例外有用 `pytest.raises(..., match=)` 斷言往外拋。
   - 對照 `store._write`（`store.py:631-642`）：`closing` 會呼叫 wrapper 的 close；COMMIT 丟錯時 in_transaction 仍為真，ROLLBACK 必被送出。
   - `log[-3:] == ["COMMIT","ROLLBACK","<close>"]` 同時鎖住「有 ROLLBACK」與「ROLLBACK 先於 close」。拿掉 ROLLBACK 或 close、或顛倒順序，都會失敗。
   - 事後用新連線查 sqlite_master 無帳本物件，並呼叫 `_assert_untouched` 確認非帳本表不變。
   - dev-lead 的揭露成立：沒有 ROLLBACK 時，關閉連線也會丟掉未提交的交易，所以事後狀態斷言本身不具牙齒，有牙齒的是順序斷言。
   - 這樣夠用：回滾路徑是明確的程式碼行為，順序斷言就是它的行為證據，事後狀態斷言當 end-to-end 完整性保險。
4. 只用 tmp_path、無 monkeypatch 殘留：成立。`db` fixture 用 tmp_path；monkeypatch 只改 `store_module._open_connection`，已手動 `undo()`，fixture 收尾也會還原。

## 各部門回報
- qa-reviewer 發現（皆 low，不阻擋）：
  - [Edge case][low] 掃描抓不到賦值別名（`x = create_objects; x(c)`），也不處理 lambda 作用域。現況不是問題，可由後續 AST 守門補強。
  - [可維護性][low] wrapper 的 `sql.split()[0]` 遇空字串 SQL 會 IndexError，目前不會發生。
- 唯讀權限判準常數：未觸及。diff 只動一個測試檔，沒碰 `scripts/validate_agents.py`，也沒有 READONLY_AGENTS 或 READONLY_ALLOWED_BASH 的異動。

## 驗證
- 讀過完整 diff，以及 `store.py:600-660`、`schema.py:388-420`、`_open_connection`、測試的 import 與輔助函式（`ScriptedClock`、`START`、`pair`、`LEDGER_PREFIXES`、`_digest`、`_assert_untouched`、`_app_sources` 皆存在）。
- 未執行測試。Codex 不可用，為單家審查。

## 下一步
PASS，不涉及 UI，回報 CEO。

總結論：前置 PR 在 head `f6660b0b`，範圍 `origin/product/stock-desk...f6660b0b4a9d8e9b3b53d377381acc8e25d1d2e9`，以程式碼審查而言沒有任何尚未解決的 BLOCKING（單家審查，測試結果未經我重現）。

BLOCKING_ISSUES=false

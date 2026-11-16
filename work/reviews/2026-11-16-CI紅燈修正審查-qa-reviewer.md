# CI 紅燈修正審查

- 審查者：qa-reviewer
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
PASS（程式碼審查結論）。`BLOCKING_ISSUES=false`。
審查方式：單家審查（Codex 不可用，`codex: command not found`，依 CEO #58）。
實作者回報的 3.12 下 `11998 passed` 與兩項反向驗證，我沒有重現。

## 各部門回報（依 BLOCKING 判準）

**1. 保護沒有被實質削弱：成立**
- 範圍與規格：
  - diff 只動測試與一份文件。
  - `FORBIDDEN_APP_MODULES` 四個 app 模組仍在 `banned = FORBIDDEN_APP_MODULES + RUNTIME_NETWORK_MODULES`，執行期檢查沒變。
- AST 層：
  - `NETWORK_MODULES` 原值保留（`socket`、`urllib`、`requests`、`httpx`、`yfinance`）。
  - `test_the_script_imports_no_forbidden_module` 的三條斷言原樣保留：
    - `without="port_is_listening"` 時命中集合為空。
    - 全文命中集合恰為 `{"socket"}`。
    - 沒有 `importlib` 與 `__import__`。
  - 我讀了腳本的 import 清單（頂層加 function-local），只有 `port_is_listening` 內有 `import socket`，其餘沒有網路模組。
- 取捨判斷：
  - `urllib.parse` 與 `socket` 在執行期只是「被載入」，不是「被呼叫」。這個放寬合理，且符合「不得有網路呼叫」的意旨。
  - 腳本若真做 HTTP，會載入 `urllib.request`、`http.client`、`requests`、`httpx`，這些仍被禁。
- 直接用 `socket` 的缺口：
  - 腳本自己直接用 `socket`，由 AST 層擋（腳本內只准那一處 loopback）。
  - 腳本實際執行時，由 `test_reading_works_with_the_socket_replaced` 擋：它把 `socket.socket` 與 `socket.create_connection` 換成拋例外的替身。
  - 這兩層加上禁用清單，對「腳本自己」的覆蓋夠。
  - 殘留缺口：腳本所依賴的 `app.*` 或第三方套件，在深處直接 `import socket` 並連線。這個情形現在只靠流程測試的替身擋，執行期檢查看不到。
  - 嚴重度 low。這個路徑要先通過 `app.services` 與 `app.data.*` 的禁用，缺口很窄。歸「凍結後待辦」。

**2. `RUNTIME_NETWORK_MODULES` 清單：合理**
- 清單：
  - `urllib.request`、`http.client`、`ssl`、`ftplib`、`smtplib`、`poplib`、`imaplib`、`xmlrpc.client`、`requests`、`httpx`、`yfinance`。
  - 這些是會做網路 I/O、且依實作者實測在 3.12 與 3.13 都不會被動載入的模組。
- `asyncio`：不建議加。
  - `asyncio` 本身 import `socket`，且常被第三方套件載入，加了誤判風險高。
  - 它只是事件迴圈，真要連線仍會走 `socket` 或 `ssl`。
- 可選補強（凍結後待辦，low）：`urllib3`、`aiohttp`、`websockets`、`http.server` / `socketserver`、`webbrowser`。
  - 加之前要先確認不被現有依賴動載入，否則會重演同一種紅燈。
  - 注意 `ssl` 已在清單內。若未來依賴升級會動載入 `ssl`，要回頭處理。

**3. 只改測試：成立**
- 腳本、`app/`、harness、`uv.lock`、`.bat`、說明文件都沒有改動。
- diff 只有測試檔，加一份 `work/dispatch/` 文件。

**4. 新文件：成立，有兩點小事**
- 內容與指令：
  - 根因敘述與測試的註解一致。
  - 指令可照抄：`<ENVDIR>` 以佔位符表示，沒有祕密、也沒有真實使用者路徑。
- 可記為凍結後待辦（low）：
  - `grep -m1 'python-version'` 依賴 workflow 裡第一個 `python-version` 就是 backend job 的。文件已寫「印不出數字就停下」，但「印出別的版本」沒涵蓋。
  - 文件引用的「修訂八」、run 314，我沒有核對。

**D-4 / #149 / 正式資料庫 / 個資**
- 本次變更沒有觸及正式資料庫，也沒有個資殘留。
- 測試仍保留 `assert list(tmp_path.iterdir()) == []` 與 stdout、stderr 皆空。
- 沒有違反 D-4 或 #149。

## 驗證
- 實際做過的：
  - 逐行讀過 diff。
  - 讀過測試的 AST 與執行期兩段，以及腳本的 import 清單。
  - 確認 `NETWORK_MODULES` 與三條 AST 斷言沒變。
- 沒做的：
  - 沒有跑 pytest，也沒有重現實作者在 3.12 下的 `11998 passed` 與反向驗證。
  - 沒有重現各模組在兩個 Python 版本的載入實測表。這是「清單在兩版都不誤判」的前提。

## 下一步
- 可進 risk-gate / 合併。純測試與文件，不涉 UI，不需 qa-e2e。
- 合併前請 devops-sre 在遠端 CI（Python 3.12）確認該測試轉綠。這才是前提的最終驗證。
- 凍結後待辦（皆 low）：
  1. 清單視情況補 `urllib3`、`aiohttp`、`websockets` 等，先在兩個版本確認不被動載入。
  2. 考慮對 `app.*` 依賴樹加「socket 替身」的整合測試，補上殘留缺口。
  3. 文件補一句「`PYV` 與 backend job 對應」的核對提示。

審查的檔案：
- `/home/user/AICompany/.claude/worktrees/agent-a9c5272eeba267d38/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_bars.py`
- `/home/user/AICompany/.claude/worktrees/agent-a9c5272eeba267d38/apps/stock-desk/backend/scripts/pipeline_acceptance_real.py`

BLOCKING_ISSUES=false

# CG-2 前置 PR 補測試交件

- 審查者：dev-lead
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
兩個測試已補在同一分支 `feat/nm5-cg2-prereq-store-bootstrap`，`app/` 沒有改動。新 head 是 `f6660b0b4a9d8e9b3b53d377381acc8e25d1d2e9`，從 `10fbdf9` fast-forward 推上去；`git ls-remote` 回傳 `f6660b0b4a9d8e9b3b53d377381acc8e25d1d2e9 refs/heads/feat/nm5-cg2-prereq-store-bootstrap`。`git diff --stat 10fbdf9 HEAD` 只動了 `apps/stock-desk/backend/tests/test_forecast_bootstrap.py` 一個檔（+139 行）。

COMMIT 失敗的情境不必改 `app/` 就能做出來。兩項反向驗證都確認新測試會擋下問題，但「拿掉回滾」那一項有一點要注意，見「驗證」第 2 點。

## 各部門回報（dev-lead）
Commit：`f6660b0` `test: create_objects 呼叫點收緊到函式層級與 COMMIT 失敗的回滾測試（補充七附記 S-15a）`

**1. S-15a 第 1 點（函式層級的 AST 斷言）**
- `test_s15a_create_objects_is_called_from_exactly_two_functions`：掃描全部 `app/`，呼叫點恰為 `{("forecast/store.py", "_write"), ("forecast/schema.py", "create_schema")}`。這比交辦的「store.py 內恰為 `_write`、schema.py 內恰為 `create_schema`」更嚴：其他模組都不得呼叫。
- 掃描函式 `_create_objects_sites` 會把以下寫法都算成呼叫：
  - 直接名稱 `create_objects(...)`；
  - import 別名，如 `from ... import create_objects as x` 後的 `x(...)`；
  - 任何 `<expr>.create_objects(...)`，例如 `schema.create_objects`、模組別名；
  - `getattr(..., "create_objects")`。
- 呼叫點記為最內層包住它的函式名稱；在模組頂層則記為 `<module>`。
- 牙齒測試 `test_s15a_the_function_scan_has_teeth`：
  - 上述每種寫法各有一個例子，另加一個「只是賦值、不是呼叫」不算數的例子。
  - 再讀進真的 store.py 原始碼，在記憶體裡附加一個用別名呼叫 `create_objects` 的 `sneaky` 函式，斷言掃描結果變成 `{"_write", "sneaky"}`。這就是第一項反向驗證，已寫成常駐測試。

**2. COMMIT 本身失敗的回滾測試**
- `test_a_failing_commit_rolls_everything_back`：在測試裡把 `store_module._open_connection` 換成一個包住真連線的 wrapper `CommitFailsConnection`。它收到 `execute("COMMIT")` 時拋 `sqlite3.OperationalError`，其他呼叫照常轉給真連線，並記下每句 SQL 的第一個字與 `close`。
- 斷言：
  - 例外往外拋；
  - 兩列 INSERT 都已執行過，最後三步依序是 `COMMIT` → `ROLLBACK` → `<close>`，也就是 store 自己先下 ROLLBACK 才關閉；
  - 撤掉 wrapper 後用新連線查 `sqlite_master`，沒有任何帳本物件；
  - 非帳本表內容不變，主檔位元組不變，資料夾內沒有殘留檔。

## 驗證
**反向驗證（都沒有改真的 `store.py`）**
1. 多一個呼叫者：見上面的牙齒測試，掃描會抓到 `sneaky`。
2. 拿掉回滾：
   - 替身是 `ForecastStore._write` 的複本，刪掉 `except`／ROLLBACK 分支，用 monkeypatch 換上去，再跑 COMMIT 失敗測試，結果如預期失敗：`assert ['INSERT', 'C...T', '<close>'] == ['COMMIT', 'R...K', '<close>']`。
   - 替身放在 scratchpad，沒有 commit：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/reverse/test_reverse_no_rollback.py`。
   - 要注意：沒有 ROLLBACK 時，`closing()` 關閉連線也會把交易丟掉，所以「沒有帳本物件、非帳本表不變」這類檢查單獨並不會失敗。這個測試真正擋下「拿掉回滾」的，是「COMMIT 之後、關閉之前，store 自己下了 ROLLBACK」那一條斷言。

**測試結果（都在 head `f6660b0`）**

| 環境 | `app` 來源 | 指定 4 檔 | 全套 |
|---|---|---|---|
| Python 3.13.17（預設 `.venv`） | 本 worktree 的 `apps/stock-desk/backend/app/__init__.py` | 553 passed | 這次沒有重跑 |
| Python 3.12.3（專屬 venv `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/venv312-cg2prereq`） | 同上 | 553 passed | 12053 passed、2 xfailed、0 failed，覆蓋率 97.81%（門檻 90） |

- 指定 4 檔是 `tests/test_forecast_bootstrap.py`、`tests/test_forecast_store.py`、`tests/test_forecast_schema.py`、`tests/test_forecast_boundaries.py`。
- 3.13 沒有重跑全套，因為交辦只要求 3.12 跑全套；這次只新增測試，沒有改程式。
- `ruff check .`：All checks passed。`ruff format`：沒有需要改的檔。`mypy app tests`：534 個檔沒有問題。

**自定解讀**
1. 呼叫點的比對範圍擴大到全部 `app/`，比交辦字面嚴。
2. COMMIT 失敗是用 wrapper 在 COMMIT 送出前拋錯來模擬，SQLite 實際上沒有執行那次 COMMIT；這測的是 store 的「失敗就回滾」路徑。
3. 牙齒測試讀的是 store.py 原始碼在記憶體裡的複本，沒有任何檔案被改。

## 下一步
1. 請 qa 確認補上的兩個測試，然後合併前置 PR，CI 須綠燈。
2. 合併後，我把 `feat/nm5-cg2-registration` 同步到新的 product，再實作補充七第 5 點與附記第 3 點的 CG-2 部分。說明裡會照指示加一行 `definition_sha256` 的計算時點。

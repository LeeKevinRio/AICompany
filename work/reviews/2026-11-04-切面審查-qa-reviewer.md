# /today 切面審查（79575e4，PASS）

- 審查者：qa-reviewer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
單家審查（Codex 不可用：本機 `codex: command not found`，待環境可用時補跑）。我沒有跑任何測試，dev-lead 自報的 CI 數字我沒有獨立重現。結論 PASS，無 critical 或 high，有 3 個 medium/low 建議。

## 各部門回報

### Summary
這個 refactor 只改結構，沒有發現行為差異。diff 共 9 檔，全落在 `apps/stock-desk/` 底下（backend app 4 檔、tests 3 檔含 golden、frontend 2 檔）。

### QB-1～QB-4 實查
- **QB-1 檔案範圍**：`git diff --stat` 的 9 檔全在 2.1 允許範圍內。
- **QB-2 零 diff**：`wording.py`、`engine.py` 不在 diff 內。`store.py` 的 diff 只有新增（`PendingExitRead`、`EntryBeforeExitRead`、`InFlightRead`、2 個 stub、`read_in_flight`），沒有碰 `_MIGRATIONS` 或 `_init_schema`。
- **QB-3 既有測試**：diff 內沒有修改或刪除既有測試，新檔都是 add。
- **QB-4 `_lines`**：`labeled_batches` 是 keyword-only 且必填，全部 5 個呼叫點都有傳。`rebalance` 傳 `()`，`emergency_exit` 傳 `result.labeled_batches`，`line` 仍是 `wording.directive_line` 原樣，`entry_before_exit_note` 固定為 `None`。

### 零行為差異
- **`_settle_pending` 搬移**：函式本體等價。差異只有三處：
  - 去掉 `as_of = today or ...`，改由 `settle_pending` 傳入。
  - 回傳包成 `SettlementRun`。
  - `evaluate_today` 改呼叫 `_settle_pending`。
- **`today or datetime.now(UTC).date()` 的位置**：搬到 `settle_pending`，求值順序不變。
- **子類別覆寫風險**：我查過，沒有任何子類別覆寫 `settle_pending`，所以 `evaluate_today` 改走私有方法不會繞過覆寫。
- **兩個 stub**：只有 `del conn` 然後回傳空 tuple，不執行 SELECT。`read_in_flight` 只送 `BEGIN` 和 `COMMIT`（DEFERRED，不取寫鎖）。例外路徑照 `commit_emergency_exit` 的慣例 ROLLBACK 後原樣 raise。
- **unauthored 路徑**：呼叫一次 `read_in_flight`，位置在 `rule_set_authorship` 判斷之後、仍然不載入也不寫入，SEAM-T7 以 trace 驗證沒有寫入語句。

### 各檔問題
#### `apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json`，`seam_helpers.py`（SEAM-T2 評估）
- [可維護性][medium] **golden 的錄製過程在 repo 裡不可驗證。**
  - 只有一個 commit，golden 與切面程式同時進來，我無法證明它真的錄於切面前。
  - `seam_helpers.py` 的 `__main__` 與 docstring 說明了方法：只 import 切面前就存在的名稱，在舊程式上執行 `record`。
  - 方法本身合理，時鐘也釘住（`FullyClockedService`、`as_of` 剔除），可重現性夠。
  - 建議：在交件說明或 golden 旁補一行錄製所用的 base commit（`31753cb`）與指令。審查者可以 checkout 31753cb 重錄比對，這是最乾淨的證明。我沒有做這步。
- [Edge case][medium] **涵蓋的回應組合偏窄。**
  - 涵蓋：authored 的 R1 日兩次、exit 與 repeat、隔日、unauthored 加 exit 後。
  - 沒涵蓋：`POST /rebalance`。`rebalance` 的 `_lines(..., labeled_batches=())` 是這次被改過的呼叫點，卻沒有 golden 保護。
  - 沒涵蓋：賣出訊號的 `/today` 回應（S/R 系規則觸發的 sell directive）、非 normal 的其他 mode、有 warnings 的情境。
  - 風險面低，因為 `_lines` 對任何輸入都是同一個函式。
  - 建議：補一個 rebalance 場景，再補一個含 sell 規則的場景。要補就得在舊程式上重錄，所以也可以記為後續項。
- 另外，golden 比對只剔除 `as_of`、`SEAM_KEYS`，不剔除其他欄位，這點是對的，沒有過度寬鬆。

#### `apps/stock-desk/backend/tests/test_playbook_today_seam.py`（SEAM-T5 等）
- [可維護性][low] **T5 的 AST 掃描有已知漏洞。**
  - 它抓 `DirectiveLine(...)` 與 `DirectiveLine.<method>(...)`，包含屬性存取形式。
  - 抓不到的情況：別名 import（`from ... import DirectiveLine as DL`）、`getattr`、`model_validate` 這類由別的名稱間接建立的情況。
  - 以現有規模可接受。若要補強，可加一條 import 掃描，禁止 `app/` 內除 `api/playbook.py` 外 import `DirectiveLine`。
- [可維護性][low] T4 的 `assert read == InFlightRead(exits=PendingExitRead(), entries=EntryBeforeExitRead())` 較弱：兩個空 NamedTuple 在 tuple 層級彼此相等，所以這條斷言分辨不出 exits 與 entries 有沒有被對調。N-171 與 N-168 填內容時會變強，現在不阻擋。
- 模組 docstring 寫的前端檔名是 `.test.tsx`，實際檔名是 `.test.ts`，請順手修正。

#### `apps/stock-desk/frontend/app/lib/types.ts`
- 新增的 4 個欄位全是 optional，與舊後端相容。沒有問題。

#### `apps/stock-desk/frontend/app/playbook/__tests__/TodaySeamFixture.test.ts`（解讀點 11）
- [可維護性][low] **前端測試用相對路徑直接讀後端 golden，形成跨套件耦合。** 我判斷可以接受，理由如下：
  - 它在同一個 monorepo，golden 是真實回應形狀，比手寫 fixture 可信。
  - 風險是日後有人重新整理 golden 目錄，或前端單獨部署、單獨跑 CI 時找不到檔案。
  - 建議：在 golden JSON 或 `seam_helpers.py` 註明「前端 SEAM-T8 依賴此檔」，並確認前端 CI 的 checkout 範圍包含 backend 目錄。這點我沒有核實 CI 設定。

### 解讀點 13（Python 3.13 對 3.12）
我沒有發現不相容。
- `isinstance(x, ast.FunctionDef | ast.AsyncFunctionDef)` 需要 3.10 以上，3.12 可用。
- 空 body 的 NamedTuple 只放 docstring，3.12 可用。
- `del` 參數、`from __future__ import annotations`、`collections.abc.Sequence` 都沒有版本問題。
- 沒用到 3.13 專屬語法或 `sqlite3` 3.13 新行為；`set_trace_callback` 和 `monkeypatch sqlite3.connect` 在 3.12 一樣可用。
- 殘餘風險：T4 的 SQL trace 字串格式（`BEGIN` 在不同 sqlite 版本是否原樣回報）我沒有在 3.12 實跑，需靠 CI 確認。

### 唯讀權限判準常數
未觸及。`git diff 31753cb 79575e4 --name-only -- .claude scripts docs CLAUDE.md` 無輸出；本次 diff 全在 `apps/stock-desk/`，沒有 `scripts/validate_agents.py` 的異動，也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的出現。我沒有執行契約中帶 pipe 的 grep 形式（本次權限不允許 pipe），改以 `--name-only` 路徑篩選加人工讀完整 diff 代替，如實記錄。常數沒有 shadow 定義，也沒有值被改動。

### code-review-checklist 自檢
- 逐檔看完 diff（9 檔），其中 golden 796 行只看結構，未逐行核對數值。
- 未見祕密、`.env`、`data/*.db` 的存取。
- 注解與程式碼用英文，符合章程。
- Bash 越界：無。我只用了 `git diff` 與 `codex --version`。

## 驗證
- 已做：靜態閱讀完整 diff，以 Grep 確認沒有 `settle_pending` 的子類別覆寫。
- 未做：沒有跑 pytest、vitest、ruff、mypy，也沒有在 31753cb 重錄 golden。dev-lead 自報的 CI 結果沒有獨立重現。
- Codex 第二意見：缺席，單家審查，Codex 待環境可用時補跑。依紅線，Codex 缺席已明確註記；若 CEO 要求正式放行須補跑。

## 下一步
1. dev-lead：補註 golden 的錄製 base 與指令；修正 docstring 的 `.test.tsx` 筆誤；視需要加 rebalance 與 sell 場景。
2. 環境可用時補跑 Codex `/review`。
3. 本審查無 UI 變更（前端只有型別與測試），不需 qa-e2e，回報 CEO，可進 risk-gate。

## Verdict
PASS
BLOCKING_ISSUES=false

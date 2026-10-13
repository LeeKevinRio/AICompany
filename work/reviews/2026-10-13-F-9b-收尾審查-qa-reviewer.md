# F-9b 收尾三 commit 審查（d40e95e..818039f）— qa-reviewer

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。

---

## Summary
PASS，BLOCKING_ISSUES=false。三個 commit（948147f、d8adafd、818039f）把我上一輪 non-blocking 5 項都落實了，測試有牙，diff 只碰 3 個測試檔和 1 份 PR 說明。（e) 列那句範圍外的機械比對說明建議保留。以下只有 non-blocking 與 suggested。

審查範圍：`d40e95e..818039f`，我讀了完整 diff（4 檔，+65／-4）。Codex 不可用：`codex: command not found`（exit 127）。我沒有實跑 pytest、mypy、ruff。

## 逐項結論

1. 上輪 5 項是否落實：全部成立。
   - F9W-41：`test_f9b_risk_conditions.py` L117 改成 `assert expected.endswith(w_c_prime)`，連句號一起釘。L118 的 `count(...removesuffix("。")) == 1` 保留。成立，有牙。因為 `expected` 本身是獨立手寫的 f-string，句號被 `_combine_reasons` 拿掉就紅，和實作者自述一致。
   - F9W-44：`test_f9b_risk_conditions.py` L130-141 新增 `isolated_yfinance` fixture，L144 以 `@pytest.mark.usefixtures` 套用。成立，見第 4 項。
   - F9W-43：`test_f9b_cache_currency_gate.py` L462-473，fx 改成具名變數 `fx = _CountingFx()`，新增 `valuation.fx is None and valuation.fx_open is None` 與 `fx.calls == 0`。`_CountingFx.calls` 在 L516、L521 確實存在，`fx_open` 也是 `PositionValuation` 的欄位（`valuation.py` L288）。同檔 L554 已有同款斷言，風格一致。成立。`fx.calls == 0` 是唯一能抓到「refused 分支偷問匯率」的斷言，和你說的反向驗證相符。
   - T-12 機械比對：新檔 `test_f9b_t12_label_verbatim.py`，成立，見第 4 項。
   - PR 說明：文首行號快照註明、(d) 補 `load_failures`，成立。我核對過 `engine.py` L148、L410、L420、L466，以及 `scheduler.py` L414、L418，描述屬實（INFO 升 WARNING）。`app/` 下沒有 `load_failures` 進 API 回應，「此欄位只進 log，API 回應不帶」屬實。

2. 只碰測試與 PR 說明：成立。`git diff --stat d40e95e..818039f -- apps/stock-desk/backend/app apps/stock-desk/frontend work/reviews` 輸出為空。整個範圍只有 `test_f9b_cache_currency_gate.py`、`test_f9b_risk_conditions.py`、新檔 `test_f9b_t12_label_verbatim.py` 與 PR 說明。

3. PR 說明沒刪改核可字面：成立。我逐行看 hunk：
   - 文首新增一行行號快照。
   - (d) 的 `_load_isolated` 列，原文完整保留，只是在「排程 tick 只留 log」後補了句號並附加新句（含 `load_failures`）。
   - (e) 的 T-12 列，原文完整保留，後面附加一句。
   - 沒有任何核可字面（T-xx、W-c 等）被動到。

4. fixture 隔離與 T-12 測試：
   - `isolated_yfinance`（L130-141）：前清、後 close 殘留 adapter 再清。`YFinanceAdapter.close()` 存在（`providers/yfinance.py` L154），`cache_info().currsize` 判斷避免在沒建過時才去建一個。即使測試中途失敗，yield 之後的 teardown 仍會跑。副作用範圍僅限 `deps._default_yfinance` 一個 `lru_cache`，沒有新的全域副作用，也沒動環境變數或 monkeypatch。與 `test_api_deps.py` 的 `isolated_deps` 同一做法（`cache_clear()` 前後各一次），風格一致。
   - T-12 regex：`_LABEL` 在 `valuationWording.ts` 恰一筆命中（L32；L17 是註解，不吻合行首格式）。`_PINNED` 在 `valuationWording.test.ts` 恰一筆命中（L56）；L57 到 L64 是 `toHaveLength`、`not.toMatch`、`missingSummary(...)` 等不同形狀，不會誤中。`[label] = findall(...)` 的解構在 0 筆或多筆時都會拋 `ValueError`，不會空轉通過。`assert t12` 防空。L28 標題列斷言（`lines[27]`）防行號漂移，我讀 worktree 內裁定檔 L28、L29，確實是「**T-12 庫存頁標籤（主案）**」與「> 代號或價格單位不採用」，三者逐字相同。
   - 讀檔路徑：`REPO = Path(__file__).resolve().parents[4]`，與 `test_f9b_cache_currency_gate.py` L56 的 `RULING_2` 一致，且裁定檔在 worktree 內存在。

5. 一般品質：新檔 docstring 清楚，註解與程式碼都是英文，符合章程。沒有新增 `except`，沒有祕密。

## 各檔問題

### `apps/stock-desk/backend/tests/test_f9b_t12_label_verbatim.py`
- [可維護性][low] non-blocking：`[label] = _LABEL.findall(source)` 失敗時是 `ValueError: not enough values to unpack`，訊息不如 `assert` 清楚。建議（可選）先 `matches = findall(...)`，再 `assert len(matches) == 1, matches`。
- [Edge case][low] non-blocking：`_LABEL` 要求行尾逗號，且前端測試要求單行 `expect(...).toBe(...)`。若日後 prettier 改行或字串改用單引號，測試會紅（解構失敗）。這是 fail-closed 方向，可接受，不需要改。
- [可維護性][low] non-blocking：硬寫 `lines[27]`、`lines[28]` 是刻意的。裁定檔若插入行會紅，這符合「改裁定須回風控」的精神。

### `apps/stock-desk/backend/tests/test_f9b_risk_conditions.py`
- [可維護性][low] non-blocking：`test_f9w44_…` 建 resolver 時也會建出 twse、tpex、finmind 的 adapter，這些沒有被 close。這與修改前行為相同，且不是 `lru_cache` 留存的物件，不影響其他測試，只是資源在測試結束後等 GC。不需要處理。
- [可維護性][low] non-blocking：fixture 進入時 `cache_clear()` 會丟掉先前測試留下的 adapter 而不 close。這是別的測試的責任，且該 adapter 本來就會留到行程結束，不算新問題。

### `apps/stock-desk/backend/tests/test_f9b_cache_currency_gate.py`
- 無問題。

### `work/stock-desk-F-9b-PR說明-2026-10-13.md`
- 範圍外那句（(e) T-12 列補機械比對說明）：建議保留。它是事實描述，內容屬實（測試確實讀裁定二 L29、`valuationWording.ts`、前端測試三方比對），且正好補上同表格原先「仍是寫死字串」那段的揭露，沒有它反而會讓讀者以為 T-12 只靠人工核對。該句沒有動任何核可字面，與「改字須回風控」無關。唯一提醒：這是實作者自行加的，建議在交接時註明一聲，不需要重審。

## 第二意見（Codex）
無法執行：`codex: command not found`（exit 127）。這延續前幾段審查的缺席。CLAUDE.md 要求 PR 審查含 Codex，是否放行由 CEO 決定。本次 diff 全為測試與文件，且是對既已 PASS 的 non-blocking 的落實，風險低。

## 唯讀權限判準常數
未觸及。兩道檢查：
- (1) `git diff --stat d40e95e..818039f` 只列 3 個測試檔與 1 份 PR 說明，沒有 `scripts/validate_agents.py`。
- (2) 完整 diff 逐行讀過，沒有任何 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的 `+`／`-` 行。我的 Bash 不能 pipe，所以改以讀 diff 全文代替 grep。
- 沒有 shadow 定義，沒有常數值改動，沒有 agent 異動。

## 自我揭露
- Bash 只用了 `git -C <worktree> diff --stat`（兩次，含一次限定路徑）、`git -C <worktree> diff`，以及 `codex --version`（找不到）。其餘用 Read／Grep／Glob。沒有 Write／Edit／staging／commit。
- 沒有實跑 pytest、ruff、mypy。「6171 passed／2 xfailed」「mypy 386 檔」與五組反向驗證都是實作者自述，我未獨立重現。我從斷言結構判斷合理：F9W-41 的 `endswith`、F9W-43 的 `fx.calls == 0` 與 T-12 的三方等式都能抓到各自描述的變異。
- T-12 的 regex 命中數是靠 Grep 與 Read 判斷（`valuationWording.ts` 一筆、`valuationWording.test.ts` 一筆），沒有實際跑 `findall`。
- `load_failures` 的行號我核對了 `engine.py` L420 與 `scheduler.py` L414-418，但沒逐行確認 `engine.py` L418-420 外層迴圈的確按 (symbol, market) 計，這點採信上輪的審查結果。

相關檔案（絕對路徑）：
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_t12_label_verbatim.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_risk_conditions.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_cache_currency_gate.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/work/stock-desk-F-9b-PR說明-2026-10-13.md`

## Verdict
PASS（上輪 non-blocking 5 項確實落實；(e) 範圍外一句建議保留）
BLOCKING_ISSUES=false

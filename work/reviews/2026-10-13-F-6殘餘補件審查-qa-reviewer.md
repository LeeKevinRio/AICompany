# F-6 殘餘補件 (1)(2) 審查（cb10b1e..bb860ec）— qa-reviewer

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。

---

## Summary
兩項補件都依我先前的要求落實，沒有發現問題。diff 範圍是 `cb10b1e..bb860ec`，共 2 檔 +12/-4：`service.py` 只加了 docstring，`test_service.py` 只收緊斷言。我沒有跑 pytest、ruff、mypy，實作者自述的結果我沒驗證。Codex 這次也不能用。

## 逐項結論

### 1. 兩項補件是否落實，斷言是否有牙
- **補件 1a，`test_service.py:330`：已落實。**
  - 新增 `assert first.reason == second.reason == RECENT_ATTEMPT_FAILED_REASON`。
  - `first` 在 `:319` 是跑過 ladder 的第一次失敗，`second` 在 `:321` 是冷卻期內的第二次。這剛好補上我勾核表 C8 後半缺的「第一次與第二次字面相同」，也補了 F-6 要求的 `first.reason` 斷言。
  - 全等比對，所以 W-38 條件若退回 `reason=combined`（第一次變 `None`），這行會轉紅。這是我讀碼的推論，不是實測。
- **補件 1b，`:808`：已落實。**
  - 冷卻期第二次改成 `assert cooled.reason == f"{RECENT_ATTEMPT_FAILED_REASON} {spliced}"`，跟第一次的 `:805` 同一個字面。
  - 原本的 `is not None`、`startswith`、`endswith` 三行已刪。它們只比首尾，字串中間或前後加東西（例如 `"MUTANT"`）會被放過，現在全等會抓到。
- 實作者自述的反向驗證我無法重跑，但從斷言形式看合理。

### 2. `service.py` diff 只有 docstring
- 只有 `:661-668` 新增 9 行 docstring，沒有程式碼行異動。
- 函式簽名 `reasons: Sequence[str] = ()`（`:659`）和邏輯（`:670-720`）都沒動。
- docstring 是英文，沒有簡體字，「風控 F11-W-38」是正體。
- 內容與實際相符：Grep 確認 `_fall_back_to_cache` 只有 `:320` 一個呼叫點，而該點在 `:319` 的 `record_attempt` 之後，也就是所有 rung 都試過之後。

### 3. 選 docstring 而非改必填
可接受。
- 我先前說兩個做法二擇一，docstring 是其中之一。
- 目前只有一個呼叫點，沒有現行風險。
- 改必填會動簽名，也牽動呼叫端，超出「補件」的範圍。
- 殘餘風險：docstring 只靠自律，日後新增呼叫端若漏讀，不會有編譯期或 mypy 擋。這個風險我在先前勾核裡已經是 non-blocking，維持。

### 4. 一般品質
- 測試註解（`:329`）是英文，邏輯單純。
- **風格提醒（low）：** docstring 的 `風控 F11-W-38` 是英文 docstring 裡夾中文。同一檔 `:596`、`:702` 已有同樣的引用慣例，所以沿用即可，不必改。

## 各檔問題
### `apps/stock-desk/backend/app/data/service.py`
- 無 blocking。
- 無 non-blocking。

### `apps/stock-desk/backend/tests/test_service.py`
- 無 blocking。
- 無 non-blocking。

## 仍待辦（沿用先前勾核，與本批無關）
- ADR-0009 D-3 加註：RECENT 句已擴及第一次失敗，由 tech-writer 處理。
- qa-e2e 下一輪重錄 `price.reason=null` 基準，並收窄驗收條件第 3 條。
- F-6 任務單在結案紀錄註明由 F11-W-38 落地，殘餘項是 (1)(2) 加上上面兩項，狀態再更新。
- 補件 (1)(2) 完成後，F-6 剩 ADR 加註與 e2e 基準重錄兩項才算整體結案。

## 第二意見（Codex）
無法執行：`codex --version` 回 `command not found`，環境沒有安裝。沒有跨廠商意見，只有本地讀碼。這批只有 docstring 加兩處測試斷言收緊，沒有行為變更，風險低。依紅線這項缺席請 coordinator 知悉。

## 唯讀權限判準常數
未觸及。
- `git diff cb10b1e..bb860ec --stat` 只列出 `service.py` 和 `test_service.py`，不含 `scripts/validate_agents.py`。
- 全文 diff 的 +/- 行沒有出現 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。
- 因指令限制不能 pipe，我是以 stat 清單加目視全文 diff 代替 grep。
- 沒有成員資格異動、沒有常數值改動，也沒有其他檔案出現 shadow 定義。因為沒有觸及，不需要對應 ADR。

## 自我揭露
- 只用了 `git diff` 加 `--stat`、Read、Grep，另外嘗試 `codex --version` 失敗。
- 沒有跑任何測試或靜態檢查。實作者自述的 ruff、format、mypy 384 檔、pytest 6378 passed／2 xfailed 都未驗證。
- 「斷言有牙」是讀碼和全等語意的推論，沒有實際做 mutation 測試。
- 沒有檢查簡體字以外的編碼細節，只目視確認 docstring 沒有簡體字。

相關檔案：
- /home/user/AICompany/.claude/worktrees/agent-a71ad24d89f0fa3c0/apps/stock-desk/backend/app/data/service.py（`:653-710`、呼叫點 `:320`）
- /home/user/AICompany/.claude/worktrees/agent-a71ad24d89f0fa3c0/apps/stock-desk/backend/tests/test_service.py（`:304-331`、`:777-808`）

## Verdict
PASS
BLOCKING_ISSUES=false

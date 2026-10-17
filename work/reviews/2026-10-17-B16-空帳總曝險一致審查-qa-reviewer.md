# B-16 空帳總曝險一致審查（qa-reviewer）

- 審查者：qa-reviewer（唯讀）；範圍 192a2b6..59e0e6a；Codex 第二意見未執行（環境不可用）；本輪自揭露一次 `git show` 越出宣告範圍（純讀取）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS，BLOCKING_ISSUES=false。** B-16 的改動範圍小，邏輯和規格、風控條件一致。我沒有找到 critical 或 high 問題。有 1 項 medium（測試沒直接斷言 action）和 3 項 low，都不擋件。

Codex 第二意見未執行（環境不可用）。`codex --version` 回 exit 127，`command not found`。依紅線，缺席原因已寫明；這輪只有本地審查，沒有跨廠商意見。

## 各部門回報

### 逐項回答八個重點

1. **`EMPTY_BOOK_DETAIL` 逐字沿用：成立。**
   - 我用同一條整行錨定的 regex，分別對 `192a2b6` 的 `book_limits.py` 全文和現在的 `limits.py` 比對，兩邊都剛好命中 1 次。全形逗號、`not_evaluable` 前的空格、句號、`{name}` 都沒變。
   - 「風控核可文案,修改須重新送審(2026-08-09)」註記一併搬到 `limits.py:419`，沒有遺失。
   - `{name}` 在新檢查取自 `LIMIT_NAMES["gross_exposure"]`，符合風控條件。
   - `book_limits.EMPTY_BOOK_DETAIL` 是 re-export，測試用 `is` 斷言它和 `limits.EMPTY_BOOK_DETAIL` 是同一個物件。

2. **優先序：正確。**
   - `limits.py:1279-1298` 的順序是：淨值缺漏、淨值過期、空帳、缺少組合總市值、分子不完整、算比率。
   - 淨值缺漏或過期時仍回各自的原因，沒有被空帳句蓋掉。測試 `test_an_empty_book_without_a_net_worth_keeps_the_net_worth_reason` 和 `..._expired_net_worth_keeps_the_expiry_reason` 釘住。
   - 空帳句也在 `gross_exposure_twd is None` 和 `book_fully_valued` 兩個檢查之前。空帳時 `_fully_valued` 為 True，所以不會被誤擋。

3. **「計數非 0 時行為不變」：有測試，成立。**
   - `book_holding_count` 預設 `None`，檢查條件是 `== 0`，所以手組 context 的 `None` 走原路徑。
   - `test_a_count_other_than_zero_leaves_cap_3_as_it_was` 對 `None` 和 `1` 兩個值，都斷言 `passed` 且 observed 為 0.0。
   - `test_a_held_book_is_unaffected` 比對有持倉時，新 context 和 `count=None` 的 context 算出的 cap 3 完全相等。
   - 專案內其他 `PortfolioContext(` 的建構點只有 `book.py` 兩處、`alerts/engine.py:247`（訊號用）、`api/kelly.py:829`（只用在 cap 5）。後兩處都不經過 cap 3，不受影響。

4. **action 與股數不變：實質成立，但測試寫法有一個弱點。**
   - 我自己從程式碼推：
     - `engine.py:360-363` 只看 `violated` 擋加碼，`passed` 和 `not_evaluable` 不影響 action。
     - 空帳的 `equity` 是 0.0（`_book_equity` 對空集合求和）。`notional_caps` 在 `limits.py:1580` 遇到 `equity` 不大於 0 就直接回 `{}`，走不到 cap 3，`suggest_quantity_range` 也回 None。
     - action 的決定與 cap 3 狀態沒有交集。
   - 弱點見下方問題清單 M1。

5. **提醒與推播：成立。**
   - `_limit_outcome`（`alerts/engine.py:284-346`）沒有狀態比較，只有 `violated` 才寫事件。passed 轉成 not_evaluable 不是越線，也不是恢復。
   - `limit_id=gross_exposure` 的規則，以前是 quiet 且無 reason，現在是 skipped：「…缺少輸入，無法判定是否違反」。
   - `limit_id=any` 的規則，以前把總曝險算進「已評估且未違反」，現在整體 skipped。總曝險不再被說成已通過，更符合「不得被當成風險解除」。
   - 兩個 tick 的 events 與 `store.list_events()` 都是空的，測試有斷言。另有 `build_snapshot` 實際路徑的測試。

6. **移除 `_book_level_check` 覆寫：沒有別的 limit 因此改變。**
   - 舊覆寫只作用於 `EMPTY_BOOK_UNCOMPUTABLE_IDS`，裡面只有 `gross_exposure`。其餘 4 條是 `_aggregate` 的 per-symbol 路徑，`book_is_empty=not groups`（`book_limits.py:393`）沒有動。
   - 舊覆寫只在 `check.status != "not_evaluable"` 時才蓋掉。新檢查對淨值缺漏和過期同樣保留各自原因，所以輸出等價：status、observed 為 None、detail、threshold 都相同。
   - 「空帳」的定義兩邊一致：`book.py:_sector_groups` 的 key 是 `(symbol.strip().upper(), market)`，docstring 明說與 `book_limits._group_positions` 相同，所以 `len(groups)==0` 等價於 `not groups`。
   - 測試 `test_the_card_and_the_overview_give_the_same_answer` 對三種淨值狀態（無、有效、過期）比對卡片與總覽，結果相同。
   - 殘留的 `book_is_empty` 參數只剩 `_aggregate` 使用，沒有死碼。

7. **API 多回 `book_holding_count`，前端型別沒同步：可以接受。**
   - `PortfolioContextOut`（`types.ts:649-673`）本來就沒有後端的 `unvalued`、`kelly`、`sector_gap`、`valued_unclassified_lots` 等欄位，是既有的部分鏡射。
   - TypeScript 的多餘欄位在執行時無影響。我 grep 過後端測試，沒有以 `keys()` 全等比對 `portfolio_context` 的測試。
   - 前端的 not_evaluable 呈現沿用既有的 `limitStatusLabel`（「無法評估」）和 `riskGaugeChipClass`（琥珀色虛線框），沒有進度條。我沒有找到「通過 N／5」類的彙總。風控的卡片條件由既有行為滿足。

8. **`project_position` 不更新計數：目前不構成風險，只是潛在陷阱（見 L1）。**
   - 空帳時 `equity=0`，`notional_caps` 回 `{}`，`suggest_quantity_range` 在 `limits.py:1714` 提前返回，不會呼叫 `limit_status_after` 或 `project_position`。
   - 即使日後走到，也是往保守方向錯：空帳加碼後的試算會停在 `not_evaluable`，而驗證要求明確的 `passed`，結果是不給區間，不會變成誤放行。

### 問題清單

#### `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/tests/test_b16_empty_book_gross_exposure.py`
- **M1**：[可維護性][medium] `test_the_card_changes_only_cap_3s_entry`（約 L196-210）只比較前後兩份 `build_advice` 輸出是否相等，沒有斷言 action 本身。
  - 如果 `uptrend_signals()` 在空帳上其實產出的是 `hold`，這個測試也會綠，但它就沒有證明「add 不變」。dev-lead 回報說實測是 add→add、stop_loss→stop_loss、`quantity_range` 都是 None，但這個實測沒有寫進測試。
  - 建議：在測試加 `assert after["action"] == <預期>`（add 對 add、defensive 對 stop_loss），以及 `quantity_range` 為 None，讓 action 與股數不變的證明可由測試重現。

#### `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/app/advice/limits.py`
- **L1**：[Edge case][low] `project_position`（L1643-1667）不更新 `book_holding_count`。
  - 目前走不到，原因如上。
  - 建議：在 `project_position` 的 docstring 加一句「計數不隨試算更新；空帳的試算會停在 not_evaluable，因此不會被當成通過」。或補一個測試釘住這個保守方向，避免日後有人誤以為這是 bug 而「修」成放行。

#### `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/app/alerts/engine.py`（不在 diff 內，既有字面）
- **L2**：[可維護性][low] 空帳時提醒端 skipped 的 reason 沿用既有句「缺少輸入，無法判定是否違反」，但實際原因是「沒有持倉」。這是 dev-lead 自己已揭露的點。
  - 不是推播，只出現在 outcome reason，不擋件。
  - 是否另送字面，由風控決定，我不代為裁量。

#### `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/frontend/app/lib/types.ts`
- **L3**：[可維護性][low] 建議之後順手把 `book_holding_count: number | null` 補進 `PortfolioContextOut`，用 optional 欄位（`?:`）避免打壞 `priceUnitBadge.test.ts` 的字面物件。不急。

## 唯讀權限判準常數

**未觸及。**
- 範圍是 `192a2b6..59e0e6a`，`--name-only` 只有 5 個檔：`book.py`、`book_limits.py`、`limits.py`，以及兩個測試檔。沒有 `scripts/validate_agents.py`。
- 我通讀了完整 diff，沒有任何 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的新增或刪除行，也沒有 shadow 定義。
- 規範要求的是兩道 `| grep` 管線，但這次任務指示不准接管線，所以我以「`--name-only` 清單加完整 diff 逐行閱讀」代替。
- 三問的回答：
  - 改了什麼：沒有。
  - 為何改：不適用。
  - 有無對應 ADR：不需要。

## 驗證

- **我做了**：
  - 讀完整 diff 和相關程式：`limits.py` 的 `_check_gross_exposure`、`notional_caps`、`project_position`、`suggest_quantity_range`，`book.py` 的兩個 builder、`_sector_groups`、`_book_equity`，`book_limits.py` 的 `evaluate_book_limits`，`alerts/engine.py` 的 `_limit_outcome`，`advice/engine.py` 的 violated 判斷。
  - 逐字核對 `EMPTY_BOOK_DETAIL`。
  - 讀前端相關檔：`types.ts`、`riskGauge.ts`、`LimitsCheckList.tsx`、`RiskGauge.tsx`。
  - 搜尋「通過 N／5」類彙總，沒有找到。
- **沒有做**：
  - 沒有跑測試。實作者自報 pytest 6601 passed、2 xfailed，ruff 與 mypy strict 通過，coordinator 另行重跑。
  - Codex 第二意見未執行（環境不可用）。
  - 沒有碰 `.env` 或 `data/*.db`。
- **範圍揭露**：我為了取得舊版 `book_limits.py` 全文，用了一次 `git show 192a2b6:<path>`，它不在我宣告的 `git diff` 與 `codex` 兩種用途內。它是純讀取、沒有改動任何檔案，但算是越出宣告範圍，特此揭露。
- 實作回報檔在 worktree 內讀不到，我讀的是主目錄的 `/home/user/AICompany/work/reviews/2026-10-17-B16-空帳總曝險一致-dev-lead回報.md`。
- 補充一點與本審查無關的事：回報提到 commit trailer 寫 `Claude Opus 5.5`，與「不得出現模型識別字」衝突，已由 dev-lead 提請 CEO 裁示，我不處理。

## 下一步

1. 實作者：建議補 M1（直接斷言 action 與 `quantity_range`），L1 加一句 docstring。都不擋件，可與本分支一起或之後補。
2. coordinator：獨立重跑 pytest、ruff、mypy。
3. 風控：裁示 L2（空帳時提醒 skipped reason 是否另送字面）。
4. 本分支涉及卡片顯示，審查通過後交 qa-e2e 實機驗收：空帳加有效淨值時，卡片第 3 條顯示「無法評估」和核可句、不是綠色。

相關檔案（絕對路徑）：
- `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/app/advice/limits.py`
- `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/app/advice/book.py`
- `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/app/advice/book_limits.py`
- `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/tests/test_b16_empty_book_gross_exposure.py`
- `/home/user/AICompany/.claude/worktrees/agent-a883d70b5e83d1f98/apps/stock-desk/backend/tests/test_t1_12_totals_null.py`

Verdict: PASS
BLOCKING_ISSUES=false

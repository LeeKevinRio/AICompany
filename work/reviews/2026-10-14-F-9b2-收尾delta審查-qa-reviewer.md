# F-9b2 收尾 delta 審查（a2f8b2a..2c003bc）— qa-reviewer

> 轉存：coordinator，2026-10-14，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。

---

## Summary
994da94 和 2c003bc 落實了 tech-architect R-81 與 PR 說明的收尾要求。我沒有找到 critical 或 high 問題，也沒有 blocking。建構子不變式正確，兩個方向都有測試。第 4、5 步程式、既有 F-9b 測試與所有核可字面在這個範圍內都沒有被改到。我用 `git diff --stat` 和完整 diff 逐檔看過。Codex 無法執行，已在下方註明。

## 逐項結論
1. **R-81 不變式正確，測試有牙：通過。**
   - `apps/stock-desk/backend/app/data/service.py` L282-290 的 `rejection_marker != (scope == "equity")` 就是 R-81 建議的式子。股票設 False 和指數設 True 兩個方向都會 raise。
   - L291-293 保留「True 必須有 wording」的檢查。這個檢查排在不變式之後，所以只有在 scope 是 equity、marker 是 True、wording 是 None 時才會走到。`test_a_marker_needs_the_wording_it_states`（`tests/test_f9b2_marker_guard.py` L800-810）正好是這個組合，仍然有效。
   - 新增的 `test_an_equity_ladder_cannot_drop_the_marker`（L786-797）用 equity、有 wording、`rejection_marker=False`，就是 R-81 要求的那一則。指數方向由既有的 `test_the_index_scope_cannot_keep_the_marker`（L773-783）涵蓋。
   - 其他建構點都不受影響：`deps.py` L129、L140、L186 是 True、True、False。`tests/market_service_helpers.py` L44-46 用 `scope == "equity"` 推導。`tests/test_f9b0_service_scope.py` L101、L117 是 equity 加 True。`MarketDataService(` 的全部呼叫點我都查過。
   - 錯誤訊息帶上 `scope` 和 `rejection_marker` 的值，方便除錯。
2. **第 4、5 步程式、既有 F-9b 測試、字面零改動：通過。**
   - `service.py` 的 diff 只有建構子 L279-293，沒有動到 L294 以後。
   - 測試檔只新增一則函式，沒有改到任何既有測試。
   - 範圍內沒有出現 `test_f9b_*.py`。
3. **PR 說明（`work/stock-desk-F-9b2-PR說明-2026-10-14.md`）：通過。**
   - F9W-56 (d)：新增 (l) 節摘要 F9W-53～F9W-57，檔頭也引用。
   - F9W-54 (a)(b)(c)：寫在 (g) 的「裁示」段，三條條件完整。
   - F9W-56 (c)：qa-e2e 改列 F-9c 合併前 required，內容是 375／1280 驗 T-14 美、T-14 台、C′、T-12 與 2e。
   - R-81～R-87：(i) 第 1～4 點改寫為引用 R-81～R-84，(g) 引用 R-87，R-85、R-86 併入 (k) 與 (h)。這與 tech-architect 的「對實作的約束」1～5 逐條對得上。
   - 我上一輪 non-blocking 1：(i)3 改成「讀回為 None 或被擋兩種」，並把殘留列給風控（F9W-57）。
   - 核可字面沒有被刪改：diff 內沒有任何 T-14、C′、T-15、T-17、W-a、W-b 的字面被動到。被改寫的只有設計說明段落。
   - Codex 缺席有揭露，寫明「合併前須補跑，或由 CEO 決定是否放行」，寫法誠實。
4. **一般品質：通過。** 命名、註解（英文）、commit 切分都符合章程。

## 各檔問題
### blocking
無。

### non-blocking
- `tests/test_f9b2_marker_guard.py` L788、L774、L801［可維護性］［low］：三則建構測試都只用 `match="marker"`。新訊息兩條分支都含「marker」，所以測試分不出是不變式還是「需要 wording」的檢查在 raise。目前每則的輸入只會命中預期的那一條，所以今天不會誤判。建議把 match 收緊，例如不變式用 `"must be True for an equity"`，wording 檢查用 `"needs its wording"`。日後有人調整檢查順序時，這能避免測試靜默通過。
- PR 說明 commit 表第 7 列寫「（本次）」，沒有 hash。合併前補上 2c003bc，或改成實際 hash。
- PR 說明 (i)4 刪掉了原文的「F9W-49 (c)」引用，只剩 F9W-24。這只是引用變少，不影響字面或結論，也可以不補。
- 我沒有跑 pytest、ruff、mypy。PR 說明寫的「6667 passed／2 xfailed」、R81-M1～M3 反向驗證，以及 F-9b 兩檔單跑 66 passed，我都沒有重現。我只能從讀碼判斷：M1 到 M3 的推論成立，三種改壞方式都會被這兩則測試抓到。

## 第二意見（Codex）
無法執行。`command -v codex` 回傳 exit 1，這個環境沒有 codex。章程要求合併前補跑 Codex，或由 CEO 明示放行。PR 說明已揭露這點。

## 唯讀權限判準常數
未觸及。此範圍的檔案只有 `service.py`、`test_f9b2_marker_guard.py` 和 PR 說明，沒有 `scripts/validate_agents.py`。範圍內的 diff 也沒有出現 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`，所以兩道檢查都沒命中，也沒有 shadow 定義或常數值改動。`service.py` 的 `rejection_marker` 與這兩個常數無關。

## 自我揭露
- 我的 Bash 只用了 `git -C <worktree> diff` 與 `diff --stat`，另外跑了一次 `command -v codex` 確認 codex 是否存在。其餘都用 Read／Grep／Glob。我沒有改檔、沒有 staging、沒有 commit。
- 沒有重現測試與 lint 結果。這份 PASS 建立在讀碼和 diff 比對上，不是執行結果。

## Verdict
PASS（附條件：合併前補 Codex 第二意見，或由 CEO 明示放行；這與我上一輪的條件相同，沒有新增）
BLOCKING_ISSUES=false

檔案：
- `/home/user/AICompany/.claude/worktrees/agent-a23c8918520245bb9/apps/stock-desk/backend/app/data/service.py`
- `/home/user/AICompany/.claude/worktrees/agent-a23c8918520245bb9/apps/stock-desk/backend/tests/test_f9b2_marker_guard.py`
- `/home/user/AICompany/.claude/worktrees/agent-a23c8918520245bb9/work/stock-desk-F-9b2-PR說明-2026-10-14.md`

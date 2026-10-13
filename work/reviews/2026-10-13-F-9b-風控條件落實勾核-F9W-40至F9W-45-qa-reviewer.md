# F-9b 風控條件落實勾核（F9W-40～F9W-45）— qa-reviewer

> 轉存：coordinator，2026-10-13，子 agent 回報逐字轉存。
> 審查範圍：feat/stock-desk-f9b `a3be985..d40e95e` 與 `a9fb896..fe91012`（worktree，未 push）。
> Codex 第二意見未執行（環境不可用）。

---

## Summary
結論 PASS，BLOCKING_ISSUES=false。63a9b7d、d40e95e 與 fe91012 已落實風控 F9W-40～F9W-45。三個範圍內沒有新增 `except`，也沒有改任何字面或既有 skip 句。測試斷言與風控條文逐項對得上。PR 說明 (c)(d)(e) 的呼叫點傳播路徑，我抽讀程式後屬實。以下全是 non-blocking。

審查範圍：`a3be985..d40e95e` 與 `a9fb896..fe91012`，我讀了兩個範圍的完整 diff（共 8 個檔案）。Codex 不可用：`codex: command not found`（exit 127）。

## 勾核表（F9W-40～F9W-45）

| 條件 | 結果 | 依據 |
|---|---|---|
| F9W-40 (a) 新增 `_load_isolated` 列、更正 snapshot 列 | 勾 | PR 說明 (d) 表已新增，內容與 `alerts/engine.py` L470-490、L424-425、L501-533 一致。記 WARNING 並附 `exc_info`，以空 snapshot 繼續。價格規則與訊號規則用既有句，`POST /api/alerts/evaluate` 回 200，status 為 skipped。snapshot 那列已更正為「由 `_load_isolated` 攔截」。 |
| F9W-40 (b) 五個呼叫點逐一交代 | 勾（屬實） | 見下方傳播路徑驗證。 |
| F9W-40 (c) 前端 500 證據改填程式位置 | 勾 | `api.ts` L172-184 屬實：非 JSON 的 500 轉成「請求失敗（HTTP 500）」。`missingSummary` 在非測試程式只用於 `PositionsTable.tsx` L86、L100，屬實。「不可達、不需實機驗」已寫入。 |
| F9W-40 不得新增 `except` | 勾（未命中） | 兩個範圍的 app 程式 diff 只有 `service.py` 的條件式與註解，沒有 `except`。測試裡只有 `raise`。PR 說明有明寫「沒有新增任何 except」。 |
| F9W-41 alerts C-34 (b) | 勾，有牙 | `test_f9b_risk_conditions.py::test_f9w41_…` 用手寫 f-string `資料來自 cached_stale 層（{loaded.source}）。 {loaded.reason}`（單一空格）。`snapshot.reason`、`snapshot.data_disclosure` 都與它完全相等，W-c′ 句出現一次，觸發訊息 `endswith(expected)`。`loaded` 來自獨立的 `load_bars` 呼叫，不是從 snapshot 反推。layer note 的組成或接法一改，等式就紅。 |
| F9W-42 (a)(b)(c) PR 說明更正 | 勾 | playbook 列改寫成最終字串路徑，已追到 `playbook/service.py` L279-289、L360-361、L758-763、L784，與程式一致。「待 qa 核對」已刪。已增列 alerts 觸發訊息、evaluate skip outcome、Kelly import 三列。Kelly 確實不帶 `loaded.reason`：`kelly.py` 沒有 `load_bars`，`sample_gate.py` 用自己的 `INSUFFICIENT_DATA_MESSAGE`。(e) 已改成逐常數說明比對方式；T-11 改為讀裁定二 L26，我核對過行號與 `removeprefix("> ")`，與 `ruling.md` L26 逐字相同。 |
| F9W-43 跨層組合 | 勾，有牙（見重點 3） | `test_f9w43_…` 有 W-c、W-c′ 兩個變體。`reason == _combine_reasons([T-15, 句])` 完全相等，T-15 恰一次，`bars == []`，`rejection == category`（D-7 (2) 優先序，unit_mismatch／unit_missing 各一）。`cache.gets == 2` 證明 fallback 沒有再讀快取，`_layers == ["incremental_readback","provider"]`，估值器 `missing == [T-12 token]`。 |
| F9W-44 `source_id` 絆線 | 勾 | `test_f9w44_…` 走真實 `deps._default_resolver.__wrapped__()`，TW 與 US 的主層與 backup 都檢查，`isinstance str` 加 `.strip()` 非空。另釘 `seen == ["twse","tpex","finmind","alpha_vantage","yfinance"]`，增減 rung 都會紅。docstring 寫明轉紅須回風控，不得只改期望值，符合條文。 |
| F9W-45 taiex | 勾 | (d) 表該列已補「同進同出」與程式位置，「待 qa-e2e」改為「不可達、不需實機驗」。新增兩則測試：有值時數字與 `TAIEX_REFERENCE` 都在，None 時兩者都不在；組態錯誤時 `taiex_reference_return` 回 None，且恰好一筆 ERROR、`exc_info[0] is CurrencyLookupError`，沒有降噪。我另外確認程式 `scheduler.py` L451-453 仍是 `logger.exception`。 |

呼叫點傳播路徑驗證（抽讀程式）：
- `price_change.py` L193-197：`ChangeScreen` 只吃已完成的 `PositionValuation`，lookup 是 ex-date 與 calendar，不碰 `MarketDataService`。判「否」成立。
- `sector_board.py` L365／L371：全檔只有 `reference_taiex` 碰到資料層，其餘讀 store。判「否」成立。
- `scheduler.py` L344：記 ERROR 後 `raise`，屬實。
- `scheduler.py` L502：`capture_pit_snapshot` 呼叫的 `refresh_sector_board` 內部，只會經 `taiex_reference_return`（L451 先攔下）碰到資料層，傳不到這一層。判「否」成立。
- `scheduler.py` L610：`_guarded` 是排程最外層，屬實。
- `app/` 下其餘資料層呼叫者，我只確認了 `api/portfolio.py` L159（無 except）；`pit_snapshot`、`event_study`、`market_panel` 與資料服務無關。

## 各檔問題（全部 non-blocking）

### `apps/stock-desk/backend/tests/test_f9b_risk_conditions.py`
- [可維護性][low] F9W-41 的 W-c′ 子字串斷言用 `w_c_prime.removesuffix("。") in expected`，句尾「。」沒被釘到。因為 reason 只有這一句，建議改 `expected.endswith(w_c_prime)`，連句號一起釘。
- [可維護性][low] F9W-44 為了建 resolver 會執行 `_default_yfinance()`。它是 `lru_cache`，建好的 adapter 會留在行程內，可能影響之後的測試。目前綠，但這是全域副作用。另外 `service._primary`、`_backups` 是私有屬性（已加 `type: ignore`）。

### `apps/stock-desk/backend/tests/test_f9b_cache_currency_gate.py`（F9W-43）
- [Edge case][low] 估值器那段只重驗「`rejection` → T-12 token」的對映，等於再斷言一次 `result.rejection`。它用 inline `_CountingFx()`，卻沒斷言 fx 未被詢問（F9W-18）。F9W-18 已有其他測試覆蓋，所以不構成缺口。

### `work/stock-desk-F-9b-PR說明-2026-10-13.md`
- [可維護性][low] 通篇以行號引用（`engine.py` L470-490 等）。日後程式一動就過時。合併前的快照可接受，不需改。
- [可維護性][low] (d) 的 `_load_isolated` 列沒提 `EvaluationResult.load_failures`，排程會以它升為 WARNING（`scheduler.py` L414）。不影響風控判斷。

## 重點逐項回應
1. 範圍內沒有新增 `except`，也沒有字面或既有 skip 句改動：成立。`a3be985..d40e95e` 在 `app/` 下沒有任何改動（只有測試與 `work/`）。`a9fb896..fe91012` 只改 `service.py` 的條件式與註解／docstring。
2. 各條測試有牙：已逐項對過，見勾核表。7 種 mutation 全擋是 dev-lead 自述，我沒有重跑，但從斷言結構判斷合理。
3. F9W-43 估值器「用同一份回覆」：足夠。估值器只讀 `rejection` 與 `bars`（`valuation.py` L489-492），而競態在估值器自己的窗口無法重現，直接餵這份回覆是唯一可行做法。不過它與前面的 `rejection == category` 斷言有重疊。
4. PR 說明 (c)(d)(e)：已照 F9W-40／42／45 改寫且屬實，見上。
5. T-12 前端仍寫死字串的揭露：足夠。PR 說明 (e) 明列「仍是寫死字串，與裁定二 L29 逐字相同，前端測試不讀 repo 外的 `work/` 檔」。我核對過 `valuationWording.ts` L32、前端測試 L56 與 `ruling.md` L29，三者逐字相同。suggested：後端 pytest 可同時讀裁定二 L29 與 `valuationWording.ts` 原始碼互比，把這一項也機械化。
6. `valuationWording.test.ts` 改成「預設全部 ≤8、例外明列」：強度沒降，反而升高。`MISSING_LABELS` 全數迭代，只有 `symbol_or_unit_rejected` 一個例外。再加 `expect(非例外鍵).toEqual(五個舊 token)` 防空轉。上方的鍵集合 `toEqual` 仍在，未來新增 token 必紅。T-12 的 10 字另有獨立測試釘住。
7. fe91012：`service.py` 的 `if verdict == "mismatch" or self._scope == "index": fetch_start = start` 與 ADR-0024 D-4／D-2 (2) 一致，也和 L420 的終局判斷（`refusals and self._scope == "index"`）對稱。新測試 `test_on_the_index_path_a_w_c_prime_also_asks_the_next_rung_for_the_whole_range` 斷言主層被縮窄、backup 被問整段、bars 是 backup 自己的。拿掉該條件，backup 會被問縮窄範圍，斷言會紅。R-75 測試變體新增 `backup-answers` 參數，並斷言 status 為 BACKUP 與回覆不含 T-15，覆蓋上輪 suggested。docstring 去掉「F-9b0, observation only」，內容屬實。上輪三項 non-blocking 都已處理。

## 第二意見（Codex）
無法執行：`codex: command not found`（exit 127）。這延續先前兩段 PASS 的缺席，CLAUDE.md 要求 PR 審查含 Codex，是否放行由 CEO 決定。

## 唯讀權限判準常數
未觸及。兩道檢查我都做了：
- (1) `git diff --stat` 在兩個範圍都只列出測試、`service.py` 與 `work/` 檔，沒有 `scripts/validate_agents.py`。
- (2) 兩個範圍的完整 diff 我逐行讀過，沒有任何 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的 `+`／`-` 行。
- 沒有 shadow 定義，沒有常數值改動，沒有 agent 異動。我的 Bash 受限於不可 pipe，所以改以讀 diff 全文代替 grep。

## 自我揭露
- Bash 只用了 `git diff`、`git diff --stat` 與 `codex --version`（找不到）。
- 沒有執行 pytest、mypy、vitest、tsc。後端 6170 passed、mypy 385 檔、前端 2089 passed、tsc 通過，以及 50 種 mutation，都是 dev-lead 自述。我從測試新增數（6164 到 6170，與 2 個 F9W-43 參數加 4 則新測試吻合）與斷言結構判斷合理，但未獨立實跑。
- 呼叫點傳播路徑我讀了約定的幾處與 `app/` 全域檔案清單，沒有對每個模組做完整的呼叫圖分析。
- 這次沒有 Write／Edit／staging／commit，也沒有任何唯讀邊界之外的操作。

相關檔案（絕對路徑）：
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_risk_conditions.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_cache_currency_gate.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_book_cause_group.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/tests/test_f9b_live_currency_gate.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/backend/app/data/service.py`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/apps/stock-desk/frontend/app/lib/__tests__/valuationWording.test.ts`
- `/home/user/AICompany/.claude/worktrees/agent-a14fc7d2aaea1c99b/work/stock-desk-F-9b-PR說明-2026-10-13.md`

## Verdict
PASS（F9W-40～F9W-45 勾核完成，可交 qa-e2e 依 F9W-46 (a)、F9W-47 驗收）
BLOCKING_ISSUES=false

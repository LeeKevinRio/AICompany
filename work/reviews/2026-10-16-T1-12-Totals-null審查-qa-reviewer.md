# T1-12 Totals null 審查（27dc826..192a2b6）— qa-reviewer

> 轉存：coordinator，2026-10-16，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。
> coordinator 記錄：qa-reviewer 自首第一次呼叫 codex 時接了 `| tail` 並用 `cd &&`（指令因 codex 不存在未執行）；仍屬權限邊界違規，第二次發生，列入給 CEO 的回報。

---

## 1. 本次結論

**PASS，BLOCKING_ISSUES=false。** 審查範圍是 27dc826..192a2b6，14 個檔案。

**Codex 第二意見未執行（環境不可用）。** 我試了兩次，`codex` 都回 `command not found`（exit 127），所以沒有跨廠商意見。照章程，這個缺席要由 coordinator 或 CEO 知悉後再決定要不要合併。以下只是本地審查的結論。

我先對自己的程序瑕疵自首。第一次呼叫 codex 時，我在指令後面接了 `| tail`，並且用了 `cd &&`。那個指令因為 codex 不存在而根本沒跑起來。所有 `git diff` 都是單獨執行，沒有接管線。

重點逐項結論如下：

| # | 重點 | 結論 |
|---|---|---|
| 1 | B4 檔案 0 行 | 通過 |
| 2 | 不改的測試本體不得動 | 通過，但有第 3 點那一處偏離 |
| 3 | `test_advice_book.py` 兩個測試的本體被改 | 合理，沒有掩蓋行為變化 |
| 4 | 不得把 null 當 0 | 通過 |
| 5 | validator 雙向 | 通過 |
| 6 | 前端不得出現 null 或 NaN | 通過 |
| 7 | T4 (b) 只是釘住現況 | 確認不是新行為 |

**1. B4 檔案為 0 行。** 我跑了 `git diff 27dc826..192a2b6 --stat`，路徑限定為 `advice/limits.py`、`book_limits.py`、`alerts/snapshot.py`、`api/advice.py`、`api/portfolio.py`、`playbook/`，輸出是空的。

**2. 不改的測試。** 評估清單內的測試函式本體都沒動：
- `test_portfolio_summary.py` 只改了 `test_summary_no_positions_is_no_data`，這是 A-1 的「必須改」項。
- `f1b:845`、`x3c:358`、`advice_helpers.book_summary`、`_empty_summary` 都在 A-1 的「必須改」與 T5 名單內。
- `_summary` fixture（`test_advice_book.py:108-121`）沒動。

**3. 偏離評估的那一處，我判斷合理。**
- 根因確實存在。`_summary` 手寫 totals 為 600,000，逐檔加總是 650,000（`test_advice_book.py:108-121`、`:541-545`）。
- 舊版 `_book_equity` 讀手寫值，新版改讀逐檔加總，所以測試的期望值才變。
- production 的 `build_summary` 是同一批 ok 列、同一順序累加，所以 totals 一定等於逐檔加總（`summary.py:277-287`；helper 在 `:153-171`）。使用者實際看到的是 50,000 ÷ 650,000 = 7.69%，8.33% 本來就是 fixture 不一致的產物。
- `_book_equity` 的三元組在所有 production 帳上逐位不變：
  - no_data 帳，舊版 `float(Decimal(0))` 與新版空和 0.0 一致。
  - partial 與 complete 帳，加數與順序相同。
  - `test_c2_the_helper_and_book_equity_equal_the_total` 在 partial 與 complete 兩種帳上釘住了這點。
- 零分母那個測試仍然會走到 guard。第 2 個列是 `quantity="0"`，所以 `_valued_unclassified` 數到 1 筆，count 非零，equity 為 0.0，於是被 `book.py:881` 的 `equity <= 0.0` 擋下、不出句。換法後分母為零的路徑還是測得到。
- 剩下一個小瑕疵：該測試仍帶著 `market_value="0"`，現在不再發揮作用（見下方 low 項）。

**4. 沒有任何一條 production 路徑把 null 當 0。**
- `app/` 內只有 `summary.py` 讀 totals 的金額欄位（C1 守門的 pattern 也這樣設計）。
- `_book_equity`（`book.py:587`）與 `_review_reported_net_worth`（`settings.py:352`）改用 helper。helper 的 0 是「空集合的和」，不是替缺值補數。
- 完整性由 `valued_count` 與 `total_count`、`book_fully_valued` 另外判斷，與評估 A-3 的論證一致。

**5. validator 雙向生效**（`summary.py:78-90`）。
- `no_data` 任一欄有值，raise。
- `partial` 或 `complete` 任一欄為 None，raise。
- 測試用 `parametrize` 對五個欄位、兩種 status 各測一次，另有合法形狀的正向測試。

**6. 前端。**
- `types.ts` 改成 `string | null`，註解寫明 null iff no_data。
- `SummaryCards.tsx` 保留 A-1 的 status 遮罩，只改註解。
- `formatMoney(null)` 回「—」，`pnlColorClass(null)` 回中性灰（`format.ts:159`、`:259`）。
- 新測試斷言 html 不含 `null` 或 `NaN`，並涵蓋 zero、nonzero、null 三種 payload。
- 非測試的前端程式只有 `SummaryCards` 讀 totals 金額（我 grep 過）。

**7. T4 (b) 確認是照現況釘住，不是新增行為。**
- 因為 `_book_equity` 回傳的三元組和舊版逐位相同，所有下游（`limits.py`、`book_limits.py`）收到的輸入完全一致。
- 空帳加自報淨值時，advice 卡 `passed 0%`、`/limits` 為 not_evaluable 的不一致，本案前後都存在。
- 測試註解也寫明「Checked last so the pin above also runs against the pre-T1-12 code」。

## 2. 各部門回報（問題清單）

沒有 critical 或 high。

### `tests/test_t1_12_totals_null.py:219-231`
- [可維護性][low] C1 的 regex 只抓 `.totals.<欄位>` 的直接讀取。`t = summary.totals; t.market_value_twd`、`getattr` 或 `model_dump()["totals"]` 這幾種寫法抓不到。建議在 docstring 註明這個限制。Phase 3 的 `plan`、`forecast`、`outlook` 若繞過，就要靠 review 把關。

### `tests/test_advice_book.py:580`
- [可維護性][low] `market_value="0"` 現在是殘留參數，已不影響結果，因為 equity 改由逐檔加總。留著會讓人誤以為分母零是由它造成。可選擇移除，或在註解標明它只是 fixture 手寫 totals。

### `app/portfolio/summary.py:78-90`
- [Edge case][low] `model_validator` 管不到 `model_construct` 或 `model_copy(update=...)`。我在 `app/` 沒看到這種用法，風險不大，僅供留意。

### `docs/adr/0014`
- [可維護性][low] 評估 A-4 已指出的 ADR-0014 D-6 勘誤，仍待 tech-writer，與本 diff 無關。

## 唯讀權限判準常數

未觸及。
- 我用 `git diff 27dc826..192a2b6 --name-only -- scripts .claude docs CLAUDE.md` 檢查，輸出為空，沒有 `scripts/validate_agents.py` 或 agent 定義的異動。
- 我用 `git diff 27dc826..192a2b6 -G"READONLY_AGENTS|READONLY_ALLOWED_BASH" --name-only` 檢查，輸出為空。
- 沒有 shadow 定義，也沒有常數值被改動。
- 這兩個檢查為了遵守「不接管線」，改用 `--name-only` 與 `-G` 達成同樣目的。命中檔案是零。

## 3. 驗證

- 我只做 code 判斷，沒有執行測試。dev-lead 自報的結果是 pytest 6581 passed / 2 xfailed、vitest 2255 passed、tsc 與 mypy strict 通過，這些我無法佐證，要靠 coordinator 獨立重跑 pytest。
- 我實際核對過 `summary.py`、`book.py`、`settings.py` 的 diff、`test_t1_12_totals_null.py` 全檔、前端 diff，以及評估 A-5 的逐條約束：
  - B1～B3、C1、C2、T1、T2、T4、T5、F1～F4 都有對應實作與測試。
  - B4 為零行。
  - T3 通過，但如第 3 點所述，`test_advice_book.py` 有兩個測試本體變動，我判定為合理偏離。
- 尚未驗收的是 F5（AC-B4b-4）：375 與 1280 寬度的實機畫面，要由 qa-e2e 做。

## 4. 下一步

1. **coordinator** 獨立重跑 pytest 與 vitest，並決定 Codex 缺席時是否放行合併。這是章程 §3 要求的第二意見，環境裡沒有 `codex`，需要 CEO 知悉。
2. **qa-e2e** 做 AC-B4b-4 的實機驗收（375 與 1280 寬度），這是涉及 UI 的必經步驟。
3. **dev-lead** 可順手處理上面三個 low 項，不擋件。
4. **PM** 決定 T4 (b) 那個既有不一致（advice 卡 `passed 0%`、`/limits` 為 not_evaluable）要不要另案處理。改字面要送 risk-compliance-officer。
5. **tech-writer** 補 ADR-0014 D-6 勘誤。

審查對象路徑：`/home/user/AICompany/.claude/worktrees/agent-af2ae34c07c9586f7`

Verdict: PASS
BLOCKING_ISSUES=false

# T1-12 Totals no_data 回 null 實作回報 — dev-lead

> 轉存：coordinator，2026-10-16，子 agent 回報逐字轉存。分支 `fix/stock-desk-t1-12-totals-null`（worktree `.claude/worktrees/agent-af2ae34c07c9586f7`），commit 1f03d80、192a2b6，未 push、未合併。

---

## 1. 本次結論

T1-12 做完了，分成兩個 commit 交件，等 qa-reviewer 審查（含 Codex 第二意見）。沒有 push，也沒有 merge。

- 分支 `fix/stock-desk-t1-12-totals-null`，基底是 27dc826（開工前確認過 `git log --oneline -1` 就是 27dc826）
- worktree：`/home/user/AICompany/.claude/worktrees/agent-af2ae34c07c9586f7`
- 1f03d80 `fix: 前端 Totals 金額型別改為可為 null，並補強 A-1 總額測試`
- 192a2b6 `fix: 全部無法估值時 API 總額改回 null，內部消費者改由逐檔加總`

所有部位都無法估值時（空帳也算），API 的五個金額欄位現在回 `null`，`status` 仍是 `no_data`；部分可估值與全部可估值的帳，行為和原本完全一樣。有一處偏離評估，見第 2 段最後。

## 2. 各部門回報

**dev-lead（本人）** 依附件 A-5 實作。commit 前已先列出要改的檔案，實際只動了下面這些：

後端（192a2b6）
- `apps/stock-desk/backend/app/portfolio/summary.py`（B1）
  - `Totals` 五個金額欄位改成 `Decimal | None`。
  - 新增 `@model_validator(mode="after")`，強制「`no_data` ⇔ 五個欄位皆為 None」，兩個方向都會 raise。
  - `build_summary` 在 `ok_count == 0` 時五個欄位都給 None，其餘運算式逐字不變。
  - 新增 `valued_market_value_twd(positions: Sequence[SummaryPosition]) -> Decimal`，空集合回 `Decimal(0)`；docstring 寫明它是內部分母、不是顯示用總額。
  - 模組與 `Totals` 的 docstring 補上 null 的語意。
- `apps/stock-desk/backend/app/advice/book.py`（B2）：`_book_equity` 改成用 helper 加總，回傳型別與三個呼叫端都沒動，docstring 同步更新。
- `apps/stock-desk/backend/app/api/settings.py`（B3）：`_review_reported_net_worth` 第 352 行改用 helper，後面的邏輯沒動。
- 新增 `apps/stock-desk/backend/tests/test_t1_12_totals_null.py`，30 個測試：
  - T1：全缺價、空帳的 JSON 五欄皆為 null；有估值的帳仍是字串。
  - T2：validator 兩個方向、每個欄位各測一次。
  - C1：grep 守門，含一個證明 pattern 抓得到舊寫法的測試。
  - C2：partial 與 complete 帳上 `totals == helper` 且 `_book_equity[0] == float(totals)`。
  - T4 (a)～(d)。
  - A-4 建議的漲跌測試：totals 為 null 時，該列的 `change` 仍不是 null。
- T5 與舊斷言修正：
  - `tests/advice_helpers.py::book_summary`、`tests/test_unusable_close_f1.py::_empty_summary`：沒有可估值列時改給 None。
  - `test_portfolio_summary.py:146`、`test_unusable_fx_f1b.py:845`、`test_x3c_currency_market_mismatch.py:358`：斷言改成 `is None`。

前端（1f03d80）
- `apps/stock-desk/frontend/app/lib/types.ts`（F1）：五個金額改成 `string | null`，註明「null iff no_data」。
- `apps/stock-desk/frontend/app/components/SummaryCards.tsx`（F2）：只改註解，A-1 的遮罩保留。
- `apps/stock-desk/frontend/app/lib/__tests__/summaryCardsNoDataTotals.test.ts`（F3）：
  - 新增「payload 金額為 null」的案例；
  - complete 全 0 改成四格都 `toBe("NT$0")`；
  - 斷言畫面不含 `null`、`NaN`。
- `apps/stock-desk/frontend/app/lib/__tests__/summaryBanner.test.ts`（F4，non-blocking 項目，順手做了）：no_data 的 fixture 改用 null。

**偏離評估之處（1 項）**

評估說內部行為「逐位不變」，這在 production 成立，但 `tests/test_advice_book.py` 有兩個測試因此變紅，不在 A-1 的「不改」清單裡，我改了它們的函式本體：
- 原因：`_summary` fixture（第 108-121 行，在不改清單內，**沒有動**）手寫 totals = 600,000，但它的逐檔加總是 650,000。舊的 `_book_equity` 讀手寫值，新的改讀逐檔加總，所以兩邊對不上。
- `test_unclassified_holdings_are_disclosed_as_a_possible_understatement`：期望值從 `8.33%` 改成 `7.69%`（50,000 ÷ 650,000）。
- `test_the_understatement_disclosure_is_dropped_without_a_denominator`：原本用 `market_value="0"` 造出零分母，現在改用 quantity 為 0 的列，讓逐檔加總本身就是 0，「分母為 0 不出句」這個 guard 照樣測得到。
- production 的 totals 一定等於逐檔加總，所以使用者看到的原因句不受影響。

**其他部門**：本次未參與。

## 3. 驗證（全部實際執行）

後端
- `ruff check .`：All checks passed!
- `ruff format --check .`：399 files already formatted。
- `mypy app tests`（strict，與 CI 相同）：Success，395 個檔案沒有問題。
- 全套 `pytest`（含 CI 的 `--cov-fail-under=90`）：
  - 改動前基準：6551 passed、0 failed、2 xfailed。
  - 改動後：6581 passed、0 failed、2 xfailed，總覆蓋率 97.17%。多出的 30 個就是新測試檔。
  - `summary.py` 100%、`settings.py` 100%、`book.py` 99%。
- T4 先在**改動前的 code** 上跑過，確認是「跟現況相同」：(a)～(d) 的條件全部成立，只有斷言 null 的那幾行失敗，這是預期的。
- T4 (b) 釘住的現況：`/limits` 的總曝險是 not_evaluable，detail 含「帳本內沒有任何持倉」；**advice 卡**的總曝險卻是 `passed`、observed 為 0.0。

前端
- `npx --no-install vitest run`：80 個檔案、2255 個測試全過。
- `npx --no-install tsc --noEmit`：exit 0。

邊界
- `git diff --stat 27dc826..HEAD`：共 14 個檔案，597 行新增、78 行刪除，就是上面列的那些。
- B4 的檔案（`advice/limits.py`、`book_limits.py`、`alerts/snapshot.py`、`api/advice.py`、`api/portfolio.py`、`playbook/**`）在 `git diff 27dc826..HEAD` 裡是 0 行。
- C1 的 regex 套在舊 code 上剛好抓到 `settings.py:352` 和 `book.py:583` 兩處，套在新 code 上抓到 0 處。
- T3：`test_portfolio_summary`、`f1b`、`x3c` 的改動只落在要改的那幾個函式；`test_api_advice`、`test_api_settings`、`test_demo_seed`、`test_portfolio_coverage_wiring` 都沒動。
- 祕密：兩個 commit 的 diff 用關鍵字掃過，沒有命中；沒有讀 `.env`，也沒碰 `data/*.db`。
- 清理：複製進來的 `node_modules`、`tsc` 產生的 `tsconfig.tsbuildinfo`、scratch 的後端副本都已刪除，worktree 是乾淨的。
- commit 訊息：除了指定要加的 Co-Authored-By 那一行，沒有其他模型識別字。

## 4. 下一步

1. **qa-reviewer**：審查 27dc826..192a2b6，跑 Codex `/review`。請特別看第 2 段那項偏離（test_advice_book 兩個測試）能不能接受。
2. **qa-e2e**：在 375 與 1280 寬度實機驗收 AC-B4b-4（F5），我這次沒做。
3. **PM／CEO**：T4 (b) 釘住了一個既有的不一致——空帳加上自報淨值時，advice 卡的總曝險顯示 `passed 0%`，`/limits` 卻是 not_evaluable。這不是本案造成的，我只是照現況釘住，沒判斷對錯；要不要處理由 PM 決定，改字面要送風控。
4. **PR 說明**（日後開 PR 時）：依 A-5 D 段要附五欄改前／改後的 JSON 對照、空帳行為、A-1 消費者表、為什麼採方案 (ii)、T1～T4 結果。本次沒有開 PR。
5. **合併**：仍待 CEO 對 Codex 的決定。

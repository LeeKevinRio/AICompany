# 信任缺陷 R4 絆線輕量核對

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

## Summary
這個 commit（c0ebe66，相對 804cdb1）只動兩個前端測試檔，沒有動產品程式。風控 R4 的四項斷言都在，三項核對全部通過，沒有發現問題。

## 核對結果

### 1. 風控 R4 四項斷言：逐字比對，全部在
依據是風控結案文件第 1 點 (e)。測試位置：`/home/user/AICompany/.claude/worktrees/agent-a5f3beaeb925ce4f2/apps/stock-desk/frontend/app/lib/__tests__/entryObservationPending.test.ts`，"page.tsx wiring" 區塊內，新增 `R4: the three queries are always enabled and never seeded with placeholder / initial / previous data`。

- (1) 通過。測試逐字斷言 page.tsx 含 `useSignals(symbol, market, true)`、`useBars(symbol, market, true)`、`useAdvice(symbol, market, true)`。我另用 Grep 確認 `page.tsx:94-96` 實際就是這三行，斷言目前成立。
- (2) 通過。測試切出 queries.ts 的 `useSignals`、`useBars`、`useAdvice` 三個 hook 本體，每個都斷言：
  - 含 `enabled: enabled && symbol.length > 0,`。
  - 不含 `placeholderData`、`keepPreviousData`、`initialData`。
  - 我確認 `queries.ts:205-230` 的三個 hook 結尾都是單獨一行 `}`，測試用 `"\n}\n"` 找函式結尾的切法有效。`:209`、`:218`、`:227` 也都是該逐字條件。
- (3) 通過。測試斷言 providers.tsx 含 `new QueryClient()` 且不含 `defaultOptions`。`providers.tsx:8` 實際是 `useState(() => new QueryClient())`，沒有 defaultOptions。
- (4) 通過。測試前的註解逐字寫入「風控 2026-10-26 結案確認 R4（重開條件絆線）：此測試一旦要改，即觸發風控 2026-10-26 第 1 點的重開條件，須送回風控重審。」另附英文理由，說明查詢被停用會永遠 pending，預填資料會印出別檔的計數。
- 順帶確認：檔案開頭已有 `readFileSync`、`fileURLToPath` 的 import，新測試沒有缺 import。

### 2. 只動測試，沒動產品程式：通過
`git diff 804cdb1 c0ebe66 --stat` 只有兩個檔案：
- `entryObservationPending.test.ts`：+21 行。
- `summaryBanner.test.ts`：+3 行、-27 行（不含 fixture 檔本身，fixture 沒有被改）。

兩檔都在 `app/lib/__tests__/` 下，沒有產品原始碼，也沒有員工線檔案。

### 3. summaryBanner.test.ts 改用共用 fixture 沒改到斷言：通過
完整 diff 只有三處變動：
- 刪掉 `SummaryPositionItem` 的 type import。
- 新增 `import { UNVALUED_POSITION } from "./summaryCardsFixtures"`。
- 把內嵌的 `UNVALUED` 物件改成 `const UNVALUED = UNVALUED_POSITION;`。

沒有任何 `expect`、斷言或測試案例被動到。我把刪掉的內嵌物件與 `summaryCardsFixtures.ts:9-34` 的 `UNVALUED_POSITION` 逐欄比對，每個欄位都相同，包含 id 1、symbol 2330、quantity 1000、avg_cost 895.44，以及 valuation 的 insufficient_data 和 missing ["price"]。其餘使用處只剩 `:52` 的 `[UNVALUED]`，沒有被改。上一輪的 low 項已解決。

## 第二意見（Codex）
無法執行。`codex --version` 回傳 exit 127（command not found），環境沒有 codex。依既有降級規則，這裡明確註記缺席；本輪是風控指定的輕量核對，不含完整 Codex review。

## 唯讀權限判準常數
未觸及。我用 Grep 工具檢查，這個 commit 的 diff 只有兩個前端測試檔，沒有 `scripts/validate_agents.py`，diff 內也沒有 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的增減行。另外在 worktree 全域（排除 `work/`）搜尋，這兩個常數只出現在既有的 5 個檔案：`scripts/validate_agents.py`、ADR-0007、`code-review-checklist` SKILL.md、`.claude/agents/qa-reviewer.md`、`CLAUDE.md`。這些檔案都不在本 commit 內，沒有 shadow 定義。

## Verdict
PASS（風控 R4 四項斷言核對通過；Codex 因環境缺席未執行，已註記）。
BLOCKING_ISSUES=false

## 自我揭露：我執行過的 Bash 指令
1. `git diff 804cdb1 c0ebe66 --stat`
2. `git diff 804cdb1 c0ebe66`
3. `codex --version`（exit 127）

沒有使用管線、cd、git show、git log 等其他指令。其餘全部用 Read、Grep、Glob 工具。沒有讀 `.env`，也沒有碰 `*.db`。第一次用 Read 讀 worktree 內的 work/reviews 路徑失敗，因為該檔在主 checkout `/home/user/AICompany/work/reviews/`，改讀該處。

相關檔案：
- /home/user/AICompany/work/reviews/2026-10-26-信任缺陷結案確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-26-信任缺陷R4交件-dev-lead.md
- /home/user/AICompany/.claude/worktrees/agent-a5f3beaeb925ce4f2/apps/stock-desk/frontend/app/lib/__tests__/entryObservationPending.test.ts
- /home/user/AICompany/.claude/worktrees/agent-a5f3beaeb925ce4f2/apps/stock-desk/frontend/app/lib/__tests__/summaryBanner.test.ts
- /home/user/AICompany/.claude/worktrees/agent-a5f3beaeb925ce4f2/apps/stock-desk/frontend/app/lib/__tests__/summaryCardsFixtures.ts

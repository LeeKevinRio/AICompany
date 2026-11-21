# local-run 轉介版交件（product 上，chore/local-run-referral）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
product 上的轉介版已完成並 push，沒有開 PR、沒有合併。main 側舊分支 `chore/agent-local-run-referral`（head 8f09d2a）沒有動，也沒有再 push 或刪除。

- 分支：`chore/local-run-referral`
- base SHA：`b1990a430ae070d4f77497a184d84a45bbc62cea`（origin/product/stock-desk 最新 head）
- head 完整 SHA：`0280efd41a1270185a929f6f51e5296261c46633`
- worktree：`/home/user/AICompany/.claude/worktrees/agent-ad1709704c47c91c6`
- 變更檔：`/home/user/AICompany/.claude/worktrees/agent-ad1709704c47c91c6/.claude/skills/local-run/SKILL.md`
- 新檔全文 42 行。整檔替換 120 行舊版（diff：28 新增、106 刪除）。
- commit 訊息為 `chore: local-run 改為不輸出指令的轉介版`，trailer 兩行照指定；repo 內容沒有 model ID。

## 各部門回報（devops-sre）
五條調整所在行：
1. 第 8 行：宣告改成「本 skill 只屬 `product/stock-desk`，不 merge 回 main」；原「屬員工線、零耦合」宣告已刪。
2. 第 20 行：寫出 R1、R2、R3、R3-0、R3-0C、RC-447，只列代號，不寫字面也不摘要。第 20 行同時註明字面與送出條件以追蹤清單為準；第 25 行寫明「以 `work/dispatch/2026-10-17-後續追蹤清單.md` 為準；本檔和清單不一致時，以清單為準」。
3. 第 24 行：暫時轉介目標直接指向 `work/dispatch/2026-10-17-後續追蹤清單.md`。
4. 第 29～36 行：六條禁止事項（第 31～36 行）全數保留。
5. 全檔沒有給 CEO 的字面，也沒有 `STOCK_DESK_DB_PATH`。第 35 行只用「`.env` 或環境變數」的一般說法，且屬於禁止事項。

另外，原稿轉介步驟第 4、5 點在新稿順延為第 4（暫時目標）、第 5（以清單為準，新增）、第 6（找不到定稿字面時送風控，沿用原稿）。

## 驗證
- `git diff b1990a4… --stat`：只有 `.claude/skills/local-run/SKILL.md`（28 insertions, 106 deletions）。
- `git diff b1990a4… --stat -- apps/stock-desk/backend/app`：空輸出。
- Grep `uv run|npm run|git |taskkill|kill|lsof|STOCK_DESK_DB_PATH|\.env`：
  - 第 31、33、35 行：命中 `uv run`、`npm run`、`taskkill`、`kill`、`lsof`、`.env`，全在禁止事項清單內。
  - 第 3、8、40、41、42 行：命中的是「skill」裡的 `kill` 字串，不是指令。
  - `git ` 與 `STOCK_DESK_DB_PATH` 零命中；禁止事項第 2 條寫的是 `git`（後面沒有空格）。
- Grep `R1|R2|R3|RC-447`：只有第 20 行一筆，全是代號，沒有請求字面。
- `python scripts/validate_agents.py`：`validate_agents: OK（15 個 agents 全數通過）`。
- commit 前 `git status` 只有該檔被修改。

## 下一步
1. qa-reviewer（含 Codex）審查，並做 tech-architect 第 4 點的核對項。
2. 被刪除的工程內容清單見我前一份回報（對 120 行舊版的節名與行號）。依裁示，搬到 `apps/stock-desk/docs/本機執行-工程參考.md` 這類新工程文件是另一件。
3. main 側的 `chore/agent-local-run-referral` 保留不動，待 CEO 或 coordinator 決定如何處置。

**沒有查證的事**
- 追蹤清單內容是否與第 20 行列出的六個代號完全一致。我只確認清單檔與重判報告檔存在，沒有逐項比對。
- 重判報告第 4 點的 qa 核對項我沒有逐條讀。
- README 的 CEO 操作段目前是否已落地。
- 新 skill 在新會話中實際觸發的行為（沒有實測）。

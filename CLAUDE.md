# CLAUDE.md — AI 虛擬公司章程

> 公司章程：只放每次都要遵守的最高原則與守則。
> 組織細節見 `docs/org-chart.md`，交接流程見 `docs/handoff-protocol.md`，長流程放 `.claude/skills/`。

---

## 0. 最高原則（所有人都要遵守）

1. **語言規則**：所有說明文字、討論、commit message、文件一律使用**繁體中文（台灣用語）**；
   技術名詞保留英文；**程式碼與註解一律用英文**。
2. **跨廠商分工**：開發使用 Claude Code，code review 由 qa-reviewer 加呼叫 **OpenAI Codex CLI**（`/review`）做第二意見。
3. **安全第一**：任何祕密（API key、token、密碼）**絕不**寫進檔案或 commit，只透過環境變數 / 已被 `.gitignore` 的 `.env` 讀取。
4. **回報格式**：每一次回應都必須走 [`回報格式.md`](回報格式.md) 的四段式——本次結論、各部門回報、驗證、下一步。
5. **風險閘門**：任何**面向使用者的建議類文案**（投資、健康、法律等建議性質內容）必須經
   **risk-compliance-officer** 審查，他有否決權。

---

## 1. 分支哲學（員工線 vs 產品線）

- **main = 員工線**：只放 `.claude/`（agents / skills / commands）、`CLAUDE.md`、`docs/`、驗證腳本。
  main 保持**零產品耦合**：agent 敘述不得綁死任何產品的檔案路徑或商業邏輯。
- **產品線**：每個產品開自己的長命分支（`product/<名稱>`），從 main 長出來，
  定期 `merge origin/main` 吸收最新員工能力；**產品分支永遠不 merge 回 main**。
- 開發產品途中要改員工能力：從 origin/main 另開 `chore/agent-*` 分支改，合併回 main 後再回產品線同步。

---

## 2. 組織與流程

- 組織圖與各部門職責：[`docs/org-chart.md`](docs/org-chart.md)（與 `.claude/agents/` 嚴格同步，CI 驗證）。
- 任務狀態機：`draft → spec → build → review → risk-gate → done`，
  任務單格式、退件與否決規則見 [`docs/handoff-protocol.md`](docs/handoff-protocol.md)。
- **「通過審查」才算完成**：未經 qa-reviewer 審查通過（無 `BLOCKING_ISSUES`）的工作不得視為 done；
  涉及 UI 再加 qa-e2e 實機驗收。
- 架構決策以 ADR 記錄在 `docs/adr/`（模板見 ADR-0001）；與 accepted ADR 衝突時以 ADR 為準。
- 過程文件、企劃、art brief、任務單放 `work/`。

---

## 3. Git 守則

- **Conventional Commits**：`<type>: <繁中簡短描述>`，type 用 `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `ci`。
- 一個 commit 一個語意，不要巨型 commit。
- **禁止 force push main**；push 被拒先 `git pull --rebase`，衝突逐檔說明後處理。
- 每個 PR 必須通過 qa-reviewer 審查（含 Codex 第二意見）且 CI 綠燈才可合併。
- Commit 前確認無任何祕密夾帶；不確定要不要 commit 就先問 CEO。

---

## 4. 安全守則

- 祕密只能來自環境變數或 `.env`（已被 `.gitignore`）；`.env.example` 只放假值。
- 新增 agent 或 skill 時遵守**最小權限**：唯讀職能（審查、風控、架構評估）不得有 Write / Edit / Bash。
- repo 若可能設為 public，提交前確認無 `*.key` / `.codex/` / `.env` 被追蹤。

---

## 5. 員工線維護

- 新增 / 修改 agent 後必跑 `python scripts/validate_agents.py`（CI 也會跑）：
  frontmatter 規格、name 唯一、tools 白名單、必要小節、唯讀角色權限、org-chart 同步，全綠才可 commit。
- 共用長流程放 `.claude/skills/<name>/SKILL.md`：
  `code-review-checklist`、`release-flow`、`data-source-integration`、`backtest-protocol`、`creative-masters`。

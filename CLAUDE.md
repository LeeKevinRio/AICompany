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
- 新增 / 修改 agent 遵守最小權限。**唯讀職能（審查、驗收、風控、架構評估）不得有 Write / Edit / 未限定範圍的 Bash**，
  實際可下的指令以 `.claude/lib/agent_policy.py` 的 `READONLY_ALLOWED_BASH`（hook 與 `scripts/validate_agents.py` 共用）明列之**非變更性且可窮舉**者為限
  （目前：`codex`、`git diff`）；新增項目須經 tech-architect 出 ADR 並由 CEO 核可。
  這是**規範性要求**：越界即違規，**不因系統沒擋下來而免責**。
- **現況揭露：執行層已由 PreToolUse hook 強制（2026-09-28 於 `chore/agent-readonly-hook` 落地，合併進 main 後生效）。**
  `.claude/settings.json` 登記 matcher 為 `Write|Edit|Bash` 的 hook，執行 `.claude/hooks/readonly_guard.py`；
  政策的唯一權威來源是 `.claude/lib/agent_policy.py`（`scripts/validate_agents.py` 亦從此匯入）。
  唯讀角色的 Write / Edit 一律阻擋；Bash 僅 qa-reviewer 有白名單（`git diff` 與兩種核准的 `codex` 用法），
  其餘唯讀角色的 Bash 一律阻擋；**對唯讀角色預設阻擋**，腳本內部錯誤時以 exit 2 阻擋（fail-closed）；
  **非唯讀角色與主執行緒不受此 hook 影響**（主執行緒的錯誤路徑見下方已知限制 ⑤）。
  agent frontmatter 的 `tools:` 仍是工具粒度白名單，`Bash(pattern)` 的括號部分不被解析、不構成命令級限制；強制力來自 hook，不是 frontmatter。
- **已知限制（如實揭露）：**
  ① 前提是執行環境有 `python3`——依官方文件只有 exit 2 會阻擋，找不到指令屬非阻擋性錯誤，工具呼叫會被放行（fail-open）。
  CEO 2026-09-28 裁定目前只在雲端 Linux session 使用、列為前提並如實揭露；日後若要在原生 Windows 使用，須先解決這一點。
  另：上文「腳本內部錯誤以 exit 2 阻擋」不適用於直譯器層錯誤（例如 `PYTHONHOME` 使直譯器啟動失敗為 exit 1，同樣等於放行）；
  hook 指令自 2026-09-30 起改為 `python3 -I`，已縮小此面，但 `env` 若改 `PATH` 使 `python3` 指向他處，`-I` 擋不住（未處理）。
  ② hook 的指令拆解器是手寫的、未做過 fuzz 測試；設計上寧可誤擋，但無法排除有未知的 shell 構造能繞過。
  ③ hook 只管 Write / Edit / Bash；唯讀角色的其他工具仍由 frontmatter 的 `tools:` 白名單控制。
  ④ 只在「含有這份 `settings.json` 的分支被 checkout 的工作目錄」中生效；合併進 main 後，各產品線須 `merge origin/main` 同步才會生效。
  ⑤ 死結與修正：原設計中，hook 匯入政策檔時若出錯（例如政策檔損壞），會連主執行緒的 Write / Edit / Bash 一起擋，
  導致無法用工具修復政策檔。ADR-0013 D6 的修正是「先對沒有 `agent_type` 的呼叫（主執行緒）放行，再匯入政策」：
  修正後政策檔損壞時，**復原方式是由主執行緒直接修復政策檔**；subagent 仍維持 fail-closed。
  ⑥ 執行層的檔案（政策、hook、`settings.json`、validator、CI 設定、審查規則本身）可被非唯讀角色修改，
  且未進版控的本機設定可能讓 hook 失效。這一項以 ADR-0013 的周界檢查、審查前的 liveness canary 與
  CODEOWNERS 加 branch protection 維持；其中 CODEOWNERS 與 branch protection 屬平台層控制，
  落地狀態以 ADR-0013 為準，**未在 GitHub 設定完成前不構成控制**。
  ⑦ `disableAllHooks`：依官方文件，在 `.claude/settings.local.json`（不進版控）或 CLI 的 `--settings` 寫入
  `"disableAllHooks": true` 即可停用專案 hook，只有 managed settings 的 hook 關不掉。任何有 Write 或 Bash 的角色都能自行建立該檔，
  CODEOWNERS 與審查都偵測不到；2026-09-30 加入的路徑守衛（subagent 以 Write／Edit 寫 `.claude/settings*.json`、`.claude/hooks/`、
  `.claude/lib/` 一律阻擋，devops-sre 豁免）只擋 Write／Edit、擋不住 Bash 寫檔，屬部分緩解。
  因此 hook 的實際保證等級是**防意外與合作式越界，不是對抗性防護**；事後偵測靠審查時的 canary。
  managed settings 需 Team 或 Enterprise 方案，目前不列為承諾，待 CEO 確認方案後由 tech-architect 評估。細節見 ADR-0013「2026-09-30 後續修補與揭露」。
  依據、實證與完整殘餘風險見 `docs/adr/0007-唯讀驗收職能的權限邊界與-e2e-降級路徑.md`（accepted）與
  `docs/adr/0013-唯讀邊界執行層的完整性周界與審查分級.md`（accepted，延伸 ADR-0007，不取代）。
- **工具缺席不得以放寬唯讀邊界解決**：改走「執行/判斷分離」，或由 devops-sre 建置能力受限的執行介面（MCP / 受限 CLI）。
- repo 若可能設為 public，提交前確認無 `*.key` / `.codex/` / `.env` 被追蹤。

---

## 5. 員工線維護

- 新增 / 修改 agent 後必跑 `python scripts/validate_agents.py`（CI 也會跑）：
  frontmatter 規格、name 唯一、tools 白名單、必要小節、唯讀角色權限、org-chart 同步，全綠才可 commit。
- 共用長流程放 `.claude/skills/<name>/SKILL.md`：
  `code-review-checklist`、`release-flow`、`data-source-integration`、`backtest-protocol`、`creative-masters`、`art-outsource`、
  `animate`、`review-animations`、`animation-vocabulary`、`ui-delivery-checklist`、`e2e-fallback`。

# AI 虛擬公司（AICompany）

一個用 **Claude Code** 多 agent 編排出來的「AI 虛擬公司」模板。
你（人類）是 **CEO**，從 Claude Code 下指令；底下十五個部門各是一個 Claude Code subagent，分工協作。
程式碼開發用 Claude Code 本身，code review 改用 **OpenAI Codex CLI**（跨廠商抓盲點）。

> **雙線模型**：`main` 是**員工線**，只放 agents / skills / 治理文件（零產品耦合）；
> 每個產品開自己的 `product/<名稱>` 長命分支，從 main 長出並定期 merge main 吸收最新員工能力，
> **永遠不 merge 回 main**。詳見 [CLAUDE.md](CLAUDE.md) 第 1 節。

> 全公司規則：說明文字一律**繁體中文（台灣用語）**，技術名詞與程式碼保留英文。詳見 [CLAUDE.md](CLAUDE.md)。

---

## 這家公司怎麼運作

完整組織圖與十五個部門的職責見 [`docs/org-chart.md`](docs/org-chart.md)，摘要：

| 部門群 | Agents | 做什麼 |
| --- | --- | --- |
| 產品規劃 | product-manager、tech-architect | PRD 與驗收條件；技術選型與 ADR（有否決權） |
| 研發 | dev-lead、frontend-engineer、data-engineer、quant-researcher | 後端／前端／資料層／量化研究 |
| 品管審查 | qa-reviewer、qa-automation、qa-e2e | code review（Codex 第二意見）／自動化測試／實機驗收 |
| 風控與資安 | risk-compliance-officer、security-engineer | 建議類文案把關（有否決權）／secrets 與弱點掃描 |
| 創意美術 | creative-lead、art-lead | 企劃文案／視覺規範 |
| 維運文件 | devops-sre、tech-writer | CI/CD 與部署／README、ADR 落檔、changelog |

### 標準協作流程

任務狀態機 `draft → spec → build → review → risk-gate → done`，
任務單格式、退件與否決規則見 [`docs/handoff-protocol.md`](docs/handoff-protocol.md)。摘要：

1. **CEO 下任務** → product-manager 產出 PRD 與驗收條件，tech-architect 做技術評估。
2. **實作部門動工** → 完成後 `git add` 成 staged diff。
3. **qa-reviewer 審查** → 本地審查 + 跨廠商 `/review`（Codex）；涉及 UI 再由 qa-e2e 實機驗收。
4. **風險閘門** → 面向使用者的建議類產出必經 risk-compliance-officer。
5. **通過才算完成**：`BLOCKING_ISSUES=true` 退回修正重審；通過則回報 CEO。

---

## CEO 怎麼下指令

在 Claude Code 對話框直接講要做的事即可，subagent 會依 description 自動派工；也可以明確指名：

- 開發：`請 dev-lead 實作一個 ...`
- 審查：`請 qa-reviewer 審查目前 staged 的變更`（或在審查時跑 `/review` 叫 Codex）
- 企劃：`請 creative-lead 想三個 ... 的方向並寫成企劃`
- 美術：`請 art-lead 給這個產品一份 art brief 與配色規範`

產出文件會放在 [`work/`](work/)。

---

## 需要設定的認證

### 1) Claude Code
- 安裝並登入 Claude Code（Anthropic 帳號 / API）。本 repo 的 agents、commands、settings 都在 `.claude/`。

### 2) OpenAI Codex CLI（給 qa-reviewer 跨廠商審查用）
- 安裝 Codex CLI。
- 二選一認證：
  - **API key**：把 `OPENAI_API_KEY` 填進 `.env`（見下方），或設成環境變數。
  - **ChatGPT 登入**：執行 `codex login`，不需 API key。
- 審查時由 `/review` 呼叫 `codex exec --sandbox read-only ...`（只讀不改）。

### key 放哪
1. 複製範本：
   ```bash
   cp .env.example .env      # PowerShell: Copy-Item .env.example .env
   ```
2. 編輯 `.env`，填入真實值（至少 `OPENAI_API_KEY`，若用 API key 認證）。
3. `.env` 已被 `.gitignore`，不會進 git。

---

## 安全注意（重要）

- **絕不**把 API key / token / 密碼寫進任何檔案或 commit；只放 `.env`（已被 gitignore）。
- `.env.example` 只放假值與說明。
- 若這個 repo 可能設為 **public**，commit 前再次確認：`.gitignore` 生效、沒有 `*.key` / `.codex/` / `.env` 被追蹤。
  ```bash
  git status --ignored        # 確認祕密檔在 ignored 區
  git ls-files | grep -Ei 'env|key|secret|codex'   # 應該沒有東西冒出來
  ```

---

## 目錄結構

```
.
├── CLAUDE.md              # 公司章程（最高原則 / 守則，精簡版）
├── README.md             # 本檔
├── 回報格式.md            # 每次回應的四段式回報格式
├── .gitignore            # 擋祕密與雜訊
├── .env.example          # 環境變數範本（假值）
├── docs/
│   ├── org-chart.md      # 組織圖與部門總表（與 agents 嚴格同步，CI 驗證）
│   ├── handoff-protocol.md  # 任務單格式 / 狀態機 / 退件與否決規則
│   └── adr/              # 架構決策紀錄（ADR-0001 為模板）
├── scripts/
│   └── validate_agents.py   # agent 規格驗證（CI 也會跑）
├── .github/workflows/
│   └── validate.yml      # CI：驗證 agents 與 org-chart 同步
├── .claude/
│   ├── settings.json     # 專案預設（權限 / env）
│   ├── agents/           # 十五個部門的 subagent 定義
│   ├── skills/           # 共用流程技能包（code-review-checklist、release-flow、
│   │                     #   data-source-integration、backtest-protocol、creative-masters）
│   └── commands/
│       └── review.md     # /review：呼叫 Codex 做跨廠商審查
└── work/                 # 企劃、art brief、任務單等過程文件
```

---

## TODO（之後補）

- [ ] 補上實際專案的程式碼目錄結構與技術棧。
- [ ] 安裝建議的 skills（見 [`.claude/skills/README.md`](.claude/skills/README.md)）。
- [x] 依實際 Codex CLI 版本確認 `/review` 的指令與 flag。（已對 codex-cli 0.142.3 驗證）
- [ ] 視需要調整各 agent 的 `model` 與工具權限。

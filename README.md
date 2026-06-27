# AI 虛擬公司（AICompany）

一個用 **Claude Code** 多 agent 編排出來的「AI 虛擬公司」模板。
你（人類）是 **CEO**，從 Claude Code 下指令；底下四位總監各是一個 Claude Code subagent，分工協作。
程式碼開發用 Claude Code 本身，code review 改用 **OpenAI Codex CLI**（跨廠商抓盲點）。

> 全公司規則：說明文字一律**繁體中文（台灣用語）**，技術名詞與程式碼保留英文。詳見 [CLAUDE.md](CLAUDE.md)。

---

## 這家公司怎麼運作

```
            CEO（你，人類）
                 │ 下指令
   ┌─────────┬───┴────┬──────────┐
dev-lead  qa-reviewer creative-lead art-lead
（開發）    （審查）     （企劃文案）   （美術）
```

| 角色 | 是誰 | 做什麼 |
| --- | --- | --- |
| **CEO** | 你（人類） | 下任務、做決策、驗收 |
| **dev-lead** | subagent | 寫 code、實作、修 bug、跑測試 |
| **qa-reviewer** | subagent | 測試與 code review（唯讀），呼叫 Codex 做第二意見 |
| **creative-lead** | subagent | 發想、企劃、文案 |
| **art-lead** | subagent | 美術方向、視覺規範、art brief |

### 標準協作流程
1. **CEO 下任務** → 描述要做什麼。
2. **dev-lead 實作** → 寫 code，`git add` 成 staged diff。
3. **qa-reviewer 審查** → 本地審查 + 跨廠商 `/review`（Codex）。
4. **通過才算完成**：若 `BLOCKING_ISSUES=true` 退回 dev-lead 修正重審；通過則回報 CEO。

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
├── CLAUDE.md              # 公司章程（組織 / 流程 / 規範）
├── README.md             # 本檔
├── .gitignore            # 擋祕密與雜訊
├── .env.example          # 環境變數範本（假值）
├── .claude/
│   ├── settings.json     # 專案預設（權限 / env）
│   ├── agents/           # 四位總監的 subagent 定義
│   │   ├── dev-lead.md
│   │   ├── qa-reviewer.md
│   │   ├── creative-lead.md
│   │   └── art-lead.md
│   ├── skills/           # 技能包（建議掛 superpowers / anthropics / openai skills）
│   │   └── README.md
│   └── commands/
│       └── review.md     # /review：呼叫 Codex 做跨廠商審查
└── work/                 # 企劃、art brief、草稿等過程文件
```

---

## TODO（之後補）

- [ ] 補上實際專案的程式碼目錄結構與技術棧。
- [ ] 安裝建議的 skills（見 [`.claude/skills/README.md`](.claude/skills/README.md)）。
- [ ] 依實際 Codex CLI 版本確認 `/review` 的指令與 flag。
- [ ] 視需要調整各 agent 的 `model` 與工具權限。

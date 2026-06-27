# CLAUDE.md — AI 虛擬公司章程

> 這份檔案是「公司章程」，定義組織、角色、協作流程與規範。
> Claude Code 每次啟動都會自動讀取本檔，請全體成員（agents）一律遵守。

---

## 0. 最高原則（所有人都要遵守）

1. **語言規則**：所有說明文字、討論、註解、commit message、文件一律使用**繁體中文（台灣用語）**；
   技術名詞與程式碼（function、class、API、framework 名稱等）**保留英文**。
2. **跨廠商分工**：開發使用 Claude Code，code review 使用 **OpenAI Codex CLI**（換一家模型，抓不同盲點）。
3. **安全第一**：任何祕密（API key、token、密碼）**絕不**寫進檔案或 commit，只透過環境變數 / 已被 `.gitignore` 的 `.env` 讀取。

---

## 1. 組織架構

```
            CEO（人類，從 Claude Code 下指令）
                       │
   ┌───────────┬───────┴───────┬───────────────┐
dev-lead    qa-reviewer    creative-lead     art-lead
（開發總監）  （測試/審查總監） （創意總監）       （美術總監）
```

| 角色 | subagent | 職責 | 工具權限 |
| --- | --- | --- | --- |
| **CEO** | 人類 | 下任務、做最終決策、驗收 | — |
| **dev-lead** | `dev-lead` | 寫 code、實作功能 | Read, Write, Edit, Bash, Glob, Grep |
| **qa-reviewer** | `qa-reviewer` | 測試、code review（唯讀，不可改 code），跨廠商呼叫 Codex 做第二意見 | Read, Grep, Glob |
| **creative-lead** | `creative-lead` | 發想、企劃、文案 | Read, Write, Edit, Glob, Grep |
| **art-lead** | `art-lead` | 美術方向、視覺規範、art brief、風格一致性 | Read, Write, Edit, Glob, Grep |

---

## 2. 協作流程（標準作業）

```
CEO 下任務
   │
   ▼
dev-lead 實作 ──► git add（staged diff）
   │
   ▼
qa-reviewer 審查
   │  ├─ 本地審查（Read / Grep / Glob）
   │  └─ 跨廠商第二意見：執行 /review（呼叫 Codex headless review）
   │
   ▼
是否通過？
   ├─ 否（BLOCKING_ISSUES=true）► 退回 dev-lead 修正，重跑審查
   └─ 是 ► 任務完成，回報 CEO
```

- **「通過審查」才算完成**。未經 qa-reviewer 審查通過的工作，不得視為 done。
- 企劃 / 美術類產出（creative-lead、art-lead）以文件形式交付到 `work/`，由 CEO 驗收。

---

## 3. 工作產出位置

- 所有過程文件、草稿、art brief、企劃案放在 `work/`（已建立，內容預設不進 git 追蹤細節，請依需要調整）。
- 正式程式碼依專案結構放置（TODO：之後依實際專案補上目錄規範）。

---

## 4. Commit / PR 規範

- **Commit message 格式**（繁中說明 + 英文技術名詞）：
  ```
  <type>: <簡短描述>

  <可選的詳細說明>
  ```
  `type` 採用 Conventional Commits：`feat` / `fix` / `docs` / `refactor` / `test` / `chore`。
- **每個 PR 都必須通過 qa-reviewer 審查**（含 Codex 第二意見），確認無 `BLOCKING_ISSUES` 才可合併。
- Commit 前務必確認**沒有夾帶任何祕密**（key、token、`.env`）。
- 不確定要不要 commit 時，先問 CEO。

---

## 5. 安全守則

- 祕密只能來自環境變數或 `.env`（`.env` 已被 `.gitignore`）。
- `.env.example` 只放假值與說明，**不放真 key**。
- 若本 repo 可能設為 **public**，提交前再次確認 `.gitignore` 生效、無 `*.key` / `.codex/` / `.env` 被追蹤。

---

## 6. TODO（之後由 CEO 補）

- [ ] 補上實際專案的程式碼目錄結構與技術棧規範。
- [ ] 掛上建議的開源 skills（見 `.claude/skills/README.md`）。
- [ ] 視需要調整各 agent 的 `model` 設定與工具權限。

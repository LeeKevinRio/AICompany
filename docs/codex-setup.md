# Codex CLI 設定指南

## 用途

Codex CLI（`@openai/codex`，OpenAI 出品）用於**跨廠商 code review 第二意見**：
`qa-reviewer` 審查 staged diff 時，除了自己（Claude）逐檔閱讀，還會透過
`.claude/commands/review.md` 定義的 `/review` 呼叫 Codex 做一次獨立 headless
review，目的是抓出同一家模型看不到的盲點。這是 `CLAUDE.md` 最高原則
「跨廠商分工」的落地機制。

## 安裝方式

跑 `scripts/setup-codex.sh`：

```bash
bash scripts/setup-codex.sh
```

腳本行為（冪等，可重複執行）：
- 若 `codex` 指令已存在於 PATH，直接印出目前版本並跳過安裝。
- 否則執行 `npm install -g @openai/codex`；若因 TLS 憑證問題失敗，會自動
  設定 `npm config set cafile /root/.ccr/ca-bundle.crt`（本環境的 proxy CA
  bundle）後重試，最多重試 2 次。
- 安裝完成後印出 `codex --version` 供人工確認。
- 檢查環境變數 `OPENAI_API_KEY` 是否存在；不存在只印出提醒文字，**不會**
  把任何金鑰寫入檔案。

版本查證紀錄（devops-sre 實際安裝時查證，非記憶）：本次於 2026-08-06 執行
`npm install -g @openai/codex` 裝得的版本為 `codex-cli 0.146.1`（npm registry
當下最新版）。之後每次重新安裝都會是當下 npm registry 上的最新版本，若需要
釘住特定版本請改用 `npm install -g @openai/codex@<version>` 並更新本文件。

## 認證方式

依 `CLAUDE.md` 安全守則，**祕密絕不寫進檔案或 commit**。Codex CLI 認證只透過
以下其中一種方式，兩者都不進 repo：

1. **環境變數 `OPENAI_API_KEY`**（建議）：由 CEO 在執行環境（shell profile
   或部署平台的 secrets 管理）自行設定，本 repo 內任何檔案都不會出現實際金鑰值。
2. **ChatGPT 帳號登入**：執行 `codex login` 走互動式登入流程，不需要
   `OPENAI_API_KEY`。此方式在 headless / CI 環境不適用，僅適合互動式本機
   使用。

若 `OPENAI_API_KEY` 未設定，`scripts/setup-codex.sh` 會印出提醒：
「需要 CEO 在環境設定中提供 OPENAI_API_KEY，祕密絕不寫進檔案」。

## 降級策略：CLI 或金鑰不可用時

`/review` 的前置條件是 Codex CLI 已安裝且已認證。若任一條件不成立
（例如：`codex` 指令不存在、`codex --version` 失敗、`OPENAI_API_KEY` 未設定
且未 `codex login`、或呼叫時因 proxy / API 額度等原因失敗）：

1. `qa-reviewer` **不得**因此卡住整個審查流程，也**不得**跳過第二意見這件事
   本身不留紀錄就直接放行。
2. 在審查報告的「第二意見（Codex）」段落**明確註記不可用的原因**
   （例如：`Codex CLI 未安裝`、`OPENAI_API_KEY 未設定`、`codex exec 逾時 / 額度不足`）。
3. 改採**強化人工複查**作為替代：`qa-reviewer` 針對
   `.claude/skills/code-review-checklist/SKILL.md` 的檢查清單逐項再過一輪
   （特別是安全與 edge case 兩類，這是跨廠商第二意見最常補到的地方），並在
   報告中註明「已因 Codex 不可用改採強化人工複查」。
4. 這個降級**不影響** `PASS` / `NEEDS_CHANGES` 與 `BLOCKING_ISSUES` 的判斷
   邏輯——只影響輸出報告中第二意見段落的內容，Verdict 仍需基於實際審查結果給出。
5. 若 Codex 長期不可用（例如 CEO 尚未提供 API key），這是環境設定缺口，
   `qa-reviewer` 應在報告中提示，由 devops-sre 或 CEO 補齊，而不是自行想辦法
   繞過或在檔案中暫存金鑰。

## 相關文件

- `.claude/commands/review.md`：`/review` command 的實際執行步驟。
- `.claude/skills/code-review-checklist/SKILL.md`：qa-reviewer 的標準審查流程與檢查清單。
- `.claude/agents/qa-reviewer.md`：qa-reviewer 的角色定義與輸出契約。

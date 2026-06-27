---
description: 跨廠商 code review — 呼叫 OpenAI Codex CLI 對目前 staged 的 git diff 做 headless review，輸出結構化結果。
---

# /review — 跨廠商第二意見審查

這個 command 換一家模型（OpenAI Codex）來審查 staged diff，目的是抓出 Claude 自己看不到的盲點。
主要由 **qa-reviewer** 在審查流程中呼叫。

## 前置條件
- 已安裝 Codex CLI（`codex`），可執行。
- 已設定認證：`OPENAI_API_KEY`（在 `.env` 或環境變數），或已用 ChatGPT 帳號登入 Codex。
- 已把要審查的變更 `git add` 成 staged diff。

## 執行步驟

1. 先確認有 staged 變更（若為空就提示先 `git add`）：

   ```bash
   git --no-pager diff --staged --stat
   ```

2. 呼叫 Codex 做 read-only headless review：

   ```bash
   codex exec --sandbox read-only "你是資深 code reviewer。請審查目前 staged 的 git diff（請自行執行 git --no-pager diff --staged 取得內容）。用繁體中文（台灣用語）輸出，技術名詞保留英文，格式如下：

   ## Summary
   （整體評估）

   ## 各檔問題
   逐檔列出：bug、edge case、安全、效能、可維護性，每項標 severity（critical/high/medium/low）與修正建議。

   ## Verdict
   PASS 或 NEEDS_CHANGES。
   若有任何 critical 或 high 問題，請在最後一行明確輸出：BLOCKING_ISSUES=true；否則輸出 BLOCKING_ISSUES=false。"
   ```

3. 把 Codex 的輸出整理進 qa-reviewer 的審查報告「第二意見（Codex）」段落。
4. 只要結果含 `BLOCKING_ISSUES=true`，即退回 dev-lead 修正。

## 備註
- `--sandbox read-only` 確保 Codex 只讀不改，符合審查只讀原則。
- 若改用 ChatGPT 登入而非 API key，請先依 Codex CLI 文件完成 `codex login`。
- 指令語法已對 **codex-cli 0.142.3** 驗證：`codex exec` 子指令存在，`-s, --sandbox read-only` 為合法值。
- 替代方案：Codex 內建專門的 review 子指令，會以 Codex 原生格式輸出，可審查未提交的變更：

  ```bash
  codex exec review --uncommitted
  ```

  本流程預設採用上面步驟 2 的自訂 prompt 版本，因為它能固定以繁體中文輸出並在最後一行給出 `BLOCKING_ISSUES=true/false`，方便接回 qa-reviewer 的判斷流程。

---
description: 產品線同步員工線 — 從 origin/main 合併最新的 agents / skills / 章程到目前產品分支。
---

# /sync-main — 吸收員工線最新能力

在**產品分支**(如 `product/stock-desk`)上執行,把 main 的最新員工能力合併進來。

## 執行步驟

```bash
git fetch origin && git merge origin/main
```

## 衝突處理原則

- **`.claude/` 與 `CLAUDE.md` 的衝突:一律以 main 的版本為準**(員工線以 main 為唯一真相來源):

  ```bash
  git checkout --theirs .claude/ CLAUDE.md
  git add .claude/ CLAUDE.md
  ```

- 其他檔案(README、docs、產品碼)逐檔判斷:產品線自己的內容保留,員工線治理文件以 main 為準。
- 解完衝突後 `git commit` 完成 merge,不要 `--abort` 後放著不同步。

## 為什麼用 merge 不用 rebase

這是**長命且已推送**的分支,rebase 會改寫歷史並強迫 force push(公司 git 守則禁止)。
merge 保留兩線的真實歷史,衝突也只需解一次。

## 紅線

- 絕不把產品分支 merge 回 main。
- 絕不在產品分支直接改 `.claude/` 或 `CLAUDE.md`;要改員工能力,從 origin/main 開 `chore/agent-*` 分支,併回 main 後再回來跑 `/sync-main`。

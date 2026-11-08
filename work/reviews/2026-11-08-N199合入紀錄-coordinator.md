# N-199 合入紀錄（依修訂八第 1 節「合入綁定」）

- 合入者角色：coordinator
- 合入位置：scratchpad worktree `wt_n190fix`（detached）
- 時間：2026-11-08（Asia/Taipei）

| 項目 | 值 |
|---|---|
| `<tip_m>` | a456b305e81158af96242f81f6f720d5dac07e51 |
| `<head>` | e13f3164707b63828789ca7c664f15a79af0e3e2 |
| `<M>` | 260ecc5da9fe2d01fdc55ebc5ded3060fa3318ae |

## push 前核對
- `git rev-list --parents -n1 <M>` → `<M> <tip_m> <head>`：恰好兩個 parent，第一個是 `<tip_m>`，第二個是 `<head>`。
- 核對時 `origin/product/stock-desk` 仍等於 `<tip_m>`。
- 完整 CI 跑在 `<M>` 上：
  - backend：ruff All checks passed；format 494 files；mypy no issues（485 files）；pytest 9908 passed、1 skipped、2 xfailed，覆蓋率 97.62%（PYTEST=0）。
  - compose：config exit=0；guard exit=0,0。
  - frontend：TSC=0；VITEST=0（3086 passed）；BUILD=0。
  - validate_agents：OK。
- merge 訊息檔內容：見 `<M>` 的 commit message。

## push
- `git push origin 260ecc5da9fe2d01fdc55ebc5ded3060fa3318ae:refs/heads/product/stock-desk` → `a456b30..260ecc5`，fast-forward，沒有 force，exit=0。

## push 後核對
- `refs/remotes/origin/product/stock-desk` = 260ecc5da9fe2d01fdc55ebc5ded3060fa3318ae
- `git ls-remote origin refs/heads/product/stock-desk` = 260ecc5da9fe2d01fdc55ebc5ded3060fa3318ae
- `<M>^2` = e13f3164707b63828789ca7c664f15a79af0e3e2 = `<head>`

## 殘留揭露
- 合入者與 push 後核對的執行者同為 coordinator；devops-sre 尚未指定正式指令。
- qa 審查是單家審查（QB-4 Codex 待環境可用時補跑）。

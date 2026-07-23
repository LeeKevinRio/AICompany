---
name: release-flow
description: 版本發佈標準流程：語意化版號、changelog、git tag。devops-sre 發版與 tech-writer 整理變更日誌時必用。
---

# Release Flow — 版本發佈流程

## 版號規則（Semantic Versioning）

`MAJOR.MINOR.PATCH`：
- **MAJOR**：不相容的行為 / 介面變更。
- **MINOR**：向下相容的新功能。
- **PATCH**：向下相容的修正。
- 0.x 階段（尚未穩定）：MINOR 當作破壞性變更、PATCH 當作一般變更。

## Changelog 規則

- 檔案：`CHANGELOG.md`，最新版本在最上面。
- 每個版本區塊：版本號、日期、分類條列——`Added` / `Changed` / `Fixed` / `Removed` / `Security`。
- 內容寫「對使用者的影響」，不是 commit message 的複製貼上。
- 未發佈的變更累積在 `## [Unreleased]` 區塊，發版時搬進新版本區塊。

## 發佈步驟

1. **前置檢查**（缺一不可）：
   - CI 全綠（測試、lint、type check、安全掃描）。
   - qa-reviewer 無未解的 BLOCKING_ISSUES。
   - 面向使用者的建議類文案已過 risk-compliance-officer。
2. **定版**：依變更內容決定版號；更新版本欄位（package 檔、設定檔）與 `CHANGELOG.md`。
3. **Commit**：`chore: release vX.Y.Z`（conventional commits）。
4. **Tag**：`git tag -a vX.Y.Z -m "vX.Y.Z"`，推 tag 前先確認 CEO 同意對外發佈。
5. **部署**：由 devops-sre 依部署文件執行，附健康檢查結果與回滾方式。

## 紅線

- 不跳過前置檢查發版；不對外發佈未經 CEO 同意的版本。
- 不重用、不移動已發佈的 tag。
- 發現發出去的版本有嚴重問題：發新 PATCH 修正或回滾，不改寫歷史。

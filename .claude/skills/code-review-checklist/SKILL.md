---
name: code-review-checklist
description: 公司標準 code review 流程與檢查清單。qa-reviewer 審查任何 staged diff 時必用；實作者交件前自檢也適用。
---

# Code Review Checklist — 標準審查流程

## 流程

1. `git --no-pager diff --staged --stat` 確認審查範圍；為空就退回請實作者先 `git add`。
2. 逐檔審查（不是抽樣），對照下方清單。
3. 執行 `/review` 取得 OpenAI Codex 跨廠商第二意見；無法執行時在報告註明原因。
4. 綜合兩邊結果，依 qa-reviewer 的輸出契約產出報告，最後一行必為 `BLOCKING_ISSUES=true|false`。

## 檢查清單

### 正確性（Bug）
- [ ] 邏輯與 PRD 驗收條件一致；邊界值（0、負數、空集合、極大值）行為正確。
- [ ] 錯誤路徑有處理，不會把例外吞掉或以錯誤狀態繼續執行。
- [ ] 併發 / 重入 / 重複觸發不會造成資料不一致。

### Edge case
- [ ] null / undefined / 空字串 / 空陣列都有對應行為。
- [ ] 時區、日期邊界（跨日、跨月、閏年）、幣別與單位換算正確。
- [ ] 外部資源失敗（網路、檔案、API 限流）有降級或明確錯誤。

### 安全
- [ ] 無祕密（key、token、密碼）進入 code、設定或測試 fixture。
- [ ] 外部輸入有驗證與跳脫（injection、路徑穿越、SSRF）。
- [ ] 權限與範圍最小化；不引入來路不明的依賴。

### 效能
- [ ] 無不必要的迴圈內 I/O、重複查詢、N+1。
- [ ] 大資料量路徑有分頁 / 串流 / 上限保護。

### 可維護性
- [ ] 命名、結構、註解密度與既有 code 一致；code 與註解用英文。
- [ ] 無大段複製貼上；重複邏輯有抽出。
- [ ] 測試隨變更同步更新；被刪除的行為其測試也一併處理。

## Severity 定義

| 級別 | 定義 | 效果 |
| --- | --- | --- |
| critical | 資料毀損、安全漏洞、祕密外洩、結果錯誤 | BLOCKING |
| high | 主要流程 bug、明顯效能坑、缺少關鍵錯誤處理 | BLOCKING |
| medium | 邊界缺漏、可維護性問題 | 應修，不擋件 |
| low | 風格、命名、小重構建議 | 建議 |

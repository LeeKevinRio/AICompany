---
name: code-review-checklist
description: 公司標準 code review 流程與檢查清單。qa-reviewer 審查任何 staged diff 時必用；實作者交件前自檢也適用。
---

# Code Review Checklist — 標準審查流程

## 流程

1. `git --no-pager diff --staged --stat` 確認審查範圍；為空就退回請實作者先 `git add`。
2. 確認範圍後**立刻**跑下一節的兩道觸及檢查，命中與否都要記下來——它決定這輪要不要用「權限判準」的眼光讀 diff。
3. 逐檔審查（不是抽樣），對照下方清單。
4. 執行 `/review` 取得 OpenAI Codex 跨廠商第二意見；無法執行時在報告註明原因。
5. 綜合兩邊結果，依 qa-reviewer 的輸出契約產出報告，最後一行必為 `BLOCKING_ISSUES=true|false`。

## 唯讀權限判準常數：Verdict 前的強制檢查

`scripts/validate_agents.py` 的 `READONLY_AGENTS`（誰算唯讀職能）與 `READONLY_ALLOWED_BASH`
（唯讀職能**宣告上**可持有哪些 Bash）兩個常數，是章程 §4 唯讀邊界在**宣告層**的判準，不是一般 code
（依據見 `docs/adr/0007-唯讀驗收職能的權限邊界與-e2e-降級路徑.md`）。改動它們等於改動
「判斷者不得具備變更受判斷物的能力」這條不變式的適用範圍。

**先認清這道檢查在防什麼**：唯讀邊界目前**在執行層沒有任何強制**——`tools:` 的 `Bash(pattern)`
不被解析，validator 只靜態檢查定義檔上的宣告，管不到任何一次實際呼叫（PreToolUse hook 建置中，
見章程 §4）。所以這裡守的是**宣告與制度的完整性**：常數被悄悄改動而無人指出，等於連紙上的邊界
都失守。**不要想著「反正 CI 會擋」**——CI 擋的只是定義檔裡的字串，不是行為，而 linter 也無法防禦
自己的維護者。

**先跑指令再判斷，不憑印象**（兩者皆在 qa-reviewer 宣告的唯讀 Bash 用途內；
審查 staged diff 時以 `--staged` 代 `<base>...<head>`）：

```bash
git diff <base>...<head> --name-only | grep -x scripts/validate_agents.py
git diff <base>...<head> -- . | grep -E '^[+-].*(READONLY_AGENTS|READONLY_ALLOWED_BASH)'
```

任一命中，**Verdict 之前**必須先逐條列出，缺一不得下 Verdict：

1. **改了什麼**——常數的前後值逐項對照；涉及成員資格時列出異動的 agent 名單。
2. **為何改**——變更理由，以及對唯讀不變式的實際影響（哪個角色因此多了或少了什麼能力）。
3. **是否有對應 ADR**——寫出 ADR 編號與其狀態。新增 `READONLY_ALLOWED_BASH` 項目須經
   tech-architect 出 ADR 並由 CEO 核可（章程 §4），**無 accepted ADR 即為 blocking**。

此節與下方檢查清單同等強制。不因 diff 只有幾行、或看起來只是註解與排版而略過——
判準常數的變更在 diff 上通常就是小的，這正是它需要被單獨盯住的原因。

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

- **`READONLY_AGENTS` 的成員資格異動**（把 agent 加入或移出唯讀清單）一律以 **high** 計，
  不得列為 non-blocking：清單的進出直接決定一個角色在制度上能否持有完整 `Bash`，而 validator 只依
  此清單去檢查定義檔上的 `tools` 宣告——**清單本身的增刪連這層靜態檢查都碰不到**，
  執行層則自始就沒有強制（見 ADR-0007 Context 的 2026-08-25 查證）。
  這是唯一以「改了哪個常數」而非以後果嚴重度定 severity 的例外——理由正是後果在審查當下讀不出來。
  依 qa-reviewer 的交接對象升級 tech-architect 或 CEO 裁定。

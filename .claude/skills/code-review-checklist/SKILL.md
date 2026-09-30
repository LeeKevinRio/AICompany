---
name: code-review-checklist
description: 公司標準 code review 流程與檢查清單。qa-reviewer 審查任何 staged diff 時必用；實作者交件前自檢也適用。
---

# Code Review Checklist — 標準審查流程

## 流程

1. **先跑 liveness canary**（見下一節「步驟 0」），把結果記進報告。
2. `git --no-pager diff --staged --stat` 確認審查範圍；為空就退回請實作者先 `git add`。
3. 確認範圍後**立刻**跑下一節的周界檢查（步驟 1），命中與否都要記下來——它決定這輪要不要用「周界」的眼光讀 diff，並依步驟 2 分級。
4. 逐檔審查（不是抽樣），對照下方清單。
5. 執行 `/review` 取得 OpenAI Codex 跨廠商第二意見；無法執行時在報告註明原因。
6. 綜合兩邊結果，依 qa-reviewer 的輸出契約產出報告，最後一行必為 `BLOCKING_ISSUES=true|false`。

## 唯讀權限判準常數：Verdict 前的強制檢查

> 節名沿用舊名，因為 `.claude/lib/agent_policy.py` 的註解與 qa-reviewer 的報告欄位都以此名稱引用。
> 判準的範圍已由 ADR-0013 擴大為下列「周界路徑」，不再只是幾個常數。

執行層（PreToolUse hook 與 validator 的靜態檢查，見章程 §4、ADR-0007）**以政策檔為準**，
而政策檔、hook、設定、validator、CI 設定與本審查規則本身，都是可以被具寫入權的角色修改的檔案。
這些檔案被悄悄改弱，hook 就照新規則放行、CI 也照新規則判綠，**兩層都不會攔**。
所以這裡守的是**執行層本身的完整性**。**不要想著「反正 CI 或 hook 會擋」**——它們擋的是違反規則的行為，
擋不了規則本身被改，而 linter 也無法防禦自己的維護者。
（依據見 `docs/adr/0013-唯讀邊界執行層的完整性周界與審查分級.md`，延伸 ADR-0007，不取代。）

### 周界路徑（共 9 條，以路徑為準，不要再列舉符號）

- `.claude/lib/`
- `.claude/hooks/`
- `.claude/settings.json`
- `.claude/settings.local.json`
- `scripts/validate_agents.py`
- `.github/workflows/validate.yml`
- `.claude/skills/code-review-checklist/SKILL.md`（本檔）
- `.claude/agents/qa-reviewer.md`
- `CODEOWNERS`

路徑清單要跟著目錄結構維護（代價揭露見 ADR-0013 Consequences）。

### 步驟 0：liveness canary（每次審查都要先跑）

```bash
git --no-pager diff --stat -- 'readonly-guard-canary()'
```

- **預期：被 hook 擋下**，stderr 以「`readonly_guard: 阻擋`」開頭。這個指令是 ADR-0013 明文核准的用法，不算越界。
- **若正常跑完、沒被擋**：代表本 session 的 hook 沒有生效（可能原因：本機設定、缺 `python3`、該分支沒有 `settings.json`）。
  報告要寫明「**hook 未生效**」並升級 devops-sre。這屬於環境問題，**不擋受審的 diff，除非該 diff 同時命中周界**。
- canary 本身無害：沒有 hook 時，它只是對一個不存在的 pathspec 做唯讀 diff。
- 它只能證明「本 session、該角色」的 hook 有生效，不能證明其他角色或其他 session。

### 步驟 1：周界檢查（先跑指令再判斷，不憑印象）

審查 staged diff 時：

```bash
git --no-pager diff --staged --name-status -- .claude/lib/ .claude/hooks/ .claude/settings.json .claude/settings.local.json scripts/validate_agents.py .github/workflows/validate.yml .claude/skills/code-review-checklist/SKILL.md .claude/agents/qa-reviewer.md CODEOWNERS
```

審查分支範圍時，把 `--staged` 換成 `<base>...<head>`（放在 `--name-status` 之後、`--` 之前）。
`<base>`、`<head>` 只是佔位符，實際執行時要換成真實的 ref；指令中不得出現 `<`、`>` 字元，否則會被 hook 擋下。

- **只要有輸出，就視為命中周界。** 用 `--name-status` 是因為 `D`（刪除）、`R`（改名）、`A`（新增）可以直接對應下方的嚴重度。
- 本流程不接管線；需要進一步篩選時，讀輸出即可，不要另外串指令。

### 步驟 2：嚴重度三級（命中周界後）

命中任一級，**Verdict 之前**都必須要求實作者回答四問，缺一不得下 Verdict：

1. **改了什麼**——前後值逐項對照；涉及成員資格時列出異動的 agent 名單。
2. **為何改**——變更理由，以及對唯讀不變式的實際影響（哪個角色因此多了或少了什麼能力）。
3. **有無對應 ADR**——寫出 ADR 編號與其狀態。
4. **屬哪一級，以及判定依據。**

**T1：直接升級 tech-architect／CEO，不進退回迴圈；沒有 accepted ADR 不得放行。**
被擋的一方沒有「修正」動作可做，退件只會空轉一輪。
T1 的四問隨升級一併交給 tech-architect／CEO，不退回實作者。

- `READONLY_AGENTS` 或 `READONLY_BASH_SCOPED_AGENTS` 成員異動（加入或移出）。
- 新增 `BashRule` 或新的 declared token。
- hook 被停用、刪除或取消登記。
- `settings.json` 的 hook command 或 matcher 被修改。
- `settings.json` 的 env 新增影響 Python 的變數（`PYTHON*`）。
- `validate.yml` 移除驗證步驟，或讓步驟失敗時不影響結果。
- 唯讀 agent 檔被刪除或改名。

**T2：high → `BLOCKING_ISSUES=true`，退回補依據。** 放行條件：security-engineer 簽核，
且 CEO 裁定已記入 ADR 落地狀態。

- 既有規則內的放寬：flag allowlist 新增項目、matcher 形狀放寬。
- `_DANGEROUS_CHARS` 刪減項目。
- 解析邏輯變寬鬆。
- fail-closed 路徑有任何改動。
- 刪除或弱化 deny 類測試。
- `.claude/lib/` 或 `.claude/hooks/` 新增 `.py` 檔或 package。
- 審查檢查本身（本檔、qa-reviewer 的對應段落）被刪除或弱化。

**T3：一般規則。** 收緊性異動、純註解或文字修改、新增測試都屬此級。
**例外**：收緊後會擋掉公司文件規定的審查指令，至少算 medium，且必須同步修正文件。

**兜底規則：**

- 無法判定屬哪一級 → 以 T2 計。
- 同一個 diff 同時有放寬與收緊 → 依放寬的那一級計。
- 步驟 1 的路徑檢查指令本身被擋 → 視同命中 T2。

此節與下方檢查清單同等強制。不因 diff 只有幾行、或看起來只是註解與排版而略過——
周界檔案的變更在 diff 上通常就是小的，這正是它需要被單獨盯住的原因。

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

- **命中執行層周界的變更，嚴重度依上方「步驟 2：嚴重度三級」定，不依一般後果嚴重度判斷。**
  T1 不得放行且不進退回迴圈，直接升級 tech-architect 或 CEO 裁定；T2 以 **high** 計，`BLOCKING_ISSUES=true`；
  T3 依一般規則。以「改了哪個檔案、哪類規則」而非以後果嚴重度定級，理由是後果在審查當下讀不出來
  （依據見 ADR-0007 落地狀態與 ADR-0013）。
- 環境問題（例如 canary 顯示 hook 未生效）本身不列入上表，處理方式見「步驟 0」。

# 風控整改併產品線 merge 輕審

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

## 結論：PASS（輕審，只審合併本身；單家審查，Codex 待環境可用時補跑）

## Summary
b4cbc5d 的衝突解法正確，兩邊語意併起來沒有問題。合併後相對產品線只多出整改分支本來的內容，沒看到夾帶的額外改動。

## 逐項核對

### 1. componentWordingScan.test.ts（唯一文字衝突檔）
- 我方 4 條全留：`riskRemediationWording.ts`、`limitNotices.ts`、`UnvalidatedNotice.tsx`、`StopQualifier.tsx`。
- 產品線 1 條保留：`quantityAbsenceWording.ts`，排在 `SCANNED_FILES` 最後。
- `git diff f66fc9d b4cbc5d` 與 `git diff 6b20774 4c9e1fe` 對這個檔逐 hunk 比對，內容相同。只差兩點：
  - 行號位移。
  - 前者多出 `quantityAbsenceWording.ts` 那一條。
- 兩個 diff 都沒有刪任何守門斷言，`-` 行全是整改本來的改寫（K-1、K-2、3-F、3-S、C-10、C-11、1-L 等）。
- `4c9e1fe..b4cbc5d` 對此檔只新增 2 行（註解加條目）。
- 衝突標記（`<<<<<<<`、`>>>>>>>`、單獨一行 `=======`）：
  - 我 Grep 了工作樹的 frontend 目錄，結果為零。
  - 工作樹是 47ee7ff，不是 b4cbc5d，所以這項只算旁證。
  - 反證是 diff 本身沒有任何標記行。

### 2. 自動合併的語意重疊檔
- **DecisionCard.tsx**
  - `f66fc9d..b4cbc5d` 的 diff 與 `6b20774..4c9e1fe` 的 diff 內容一致。
  - 4-T／C-11 把停利格移走後，主視圖格數是 4 變 3，網格改為 `lg:grid-cols-3`。
  - 股數格（`DECISION_CARD_QUANTITY_LABEL`）仍在，值為 `quantityRangeShares ?? QUANTITY_ABSENT_SHORT_BY_CAUSE[quantityAbsenceCause ?? "unspecified"]`。
  - 所以股數成因在停利格移走後仍有呈現位置，沒有因為整改而消失。
  - `QUANTITY_RANGE_ABSENT_SHORT` 的 import 已由產品線那側移除，現在只在 `quantityAbsenceWording.ts` 內當 `unspecified`（C-0）的值，沒有殘留未用 import。
  - 整改字面都在：`UnvalidatedNotice`、`StopQualifier`、`LimitNoticeBlock`、`OPERATION_REFERENCE_DISCLAIMER`（3-S）。信心 chip 和 R3 指引句已撤，是整改本意。
- **operationSummary.ts**
  - 兩邊各加欄位，沒有互相覆蓋：整改側加 `topMatchedRuleId` 與 `pickTopMatchedRuleId`；產品線側加 `blockedAction`、`quantityAbsenceCause`，並讓 `quantityAbsenceReason` 依成因取字。
  - 整改側沒動 `quantityAbsenceReason`，所以沒有衝突。
- **adviceWording.ts**
  - 產品線改了 `QUANTITY_RANGE_ABSENCE_TEXT`／`QUANTITY_RANGE_ABSENT_SHORT` 的註解，字面沒動。
  - 整改側只在 `CONFIDENCE_PREFIX` 加了孤兒註記。
  - 兩處在不同位置，都在。
- **apps/stock-desk/README.md**
  - 產品線的 dev-up、備份、`.env` 大改保留。
  - 整改的免責聲明（第 6 行）保留。
  - `f66fc9d..b4cbc5d` 對此檔只有那一行 1 增 1 減。

### 3. 夾帶檢查
- `git diff f66fc9d b4cbc5d --stat` 與 `git diff 6b20774 4c9e1fe --stat` 的檔案清單、各檔增刪行數都相同，總計皆為 35 檔、+2185／-200。
- 前者的 `componentWordingScan.test.ts` 與後者同為 57 行異動。這些行數相同的檔案我沒有逐檔全文比對，只比了重疊的 4 檔加測試檔，其餘靠 stat 一致作旁證。
- 因此合併沒有多帶任何檔，也沒有多帶任何一行，與交件者「除了解衝突沒改別的」的說法相符。
- `4c9e1fe..b4cbc5d` 的 75 檔全是產品線側內容，沒有碰：
  - `scripts/`
  - `.claude/agents`
  - `.claude/commands`
  - `CLAUDE.md`
- 唯一碰到 `.claude/` 的是 `.claude/skills/local-run/SKILL.md`，來自產品線，不影響 agent 權限。

## BLOCKING
無。

## NON-BLOCKING
1. `apps/stock-desk/frontend/app/lib/operationSummary.ts` 約 205–220 行：`pickTopMatchedRuleId` 被插在 `pickTopMatchedRule` 的 doc comment 與函式之間，導致那段註解掛在錯的函式上。
   - 這是整改分支 4c9e1fe 就有的問題，不是合併造成的。
   - 建議下次碰到這支檔時順手把註解移回去，不必擋這次合併。
2. 資訊整合風險，限於我用唯讀工具看不到的部分：
   - held 且加碼被風險上限擋下時，會同時出現兩段字：`LimitNoticeBlock` 的「被擋加碼句」（整改 2 項），和股數格的 D-b／Q-b 成因字（產品線）。
   - 兩者各自經風控審過。我無法在 b4cbc5d 的樹上渲染，不能確認兩句同時並排時語意是否重複或矛盾。
   - 建議 qa-e2e 實機驗收時挑「held + add 被擋」的標的看一眼。
   - 若出現矛盾，再送 risk-compliance-officer。
3. 驗證方式限制：
   - 目前工作樹是 47ee7ff，不是 b4cbc5d，所以我全程只用 `git diff` 比對，沒有讀合併後的完整檔案。
   - 結論是由 diff 一致性推得。

## 唯讀權限判準常數
未觸及。
- `git diff 4c9e1fe b4cbc5d --name-only -- scripts .claude/agents .claude/commands CLAUDE.md`：無輸出。`scripts/validate_agents.py` 不在兩個範圍的 stat 清單內。
- 我用 `git diff 6b20774 b4cbc5d -G"READONLY_AGENTS|READONLY_ALLOWED_BASH" --stat` 找成分出現這兩個常數名稱的異動（取代被禁的 pipe 檢查）。
- 命中的只有 6 個 `work/reviews/*-qa-reviewer.md` 審查檔（文件，只是提及名稱），沒有任何 `.py`、`.ts` 或 agent 定義檔，所以：
  - 沒有 shadow 定義。
  - 常數值沒變。
  - 沒有成員資格異動。
  - 不需要 ADR。

## 權限紀律紀錄
- Bash 只用了 `git diff <範圍> [--stat|--name-only] [-- 路徑]` 與一次 `codex --version`。
- 唯一超出你列出的 Bash 範圍的是第 2 項常數檢查：用了 `git diff -G"…" --stat` 取代被禁的 pipe。內容仍是唯讀 `git diff`，但嚴格說是你範圍外的 flag，特此註記。
- 沒有 pipe、`;`、`&&`、重導向或 `cd`，沒有跑測試。
- 沒讀 `.env`，沒碰 `backend/data/*.db`。
- `codex --version` 回報 `command not found`（exit 127）。Codex 不可用，**單家審查，Codex 待環境可用時補跑**。

## 合併建議
可以放行：
- 依 `docs/handoff-protocol.md`，合併後的程式碼異動涉及 UI，請走 qa-e2e 實機驗收，並請其特別看上面 NON-BLOCKING 第 2 點的場景。
- Codex 第二意見待環境可用後補跑。因為這是純合併審查且兩側已各自 PASS，我不認為補跑的結果會翻盤，但程序上要補。

相關路徑：
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/__tests__/componentWordingScan.test.ts`
- `/home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/DecisionCard.tsx`
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/operationSummary.ts`
- `/home/user/AICompany/apps/stock-desk/frontend/app/lib/adviceWording.ts`
- `/home/user/AICompany/apps/stock-desk/README.md`

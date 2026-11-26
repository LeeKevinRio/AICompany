# F1 首頁狀態 B 審查

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論：PASS_WITH_NOTES（BLOCKING_ISSUES=false）
單家審查（Codex 依 CEO 決策 #58 不可用，未跑 /review）。RC-769 F1 的 qa 核對項，除「綠燈」一項只能引用實作者自報外，都符合。有 2 個 low 註記，不擋件。可送 risk-gate，但 qa-e2e 要先補。

## 各部門回報（qa-reviewer）

### 1. RC-769 F1 qa 核對項
| 項目 | 判定 | 證據 |
|---|---|---|
| 字串與 RC-760 逐字相同 | 符合 | `oneLinerWording.ts` 新字面為 `` `${n} 條規則已設定。這裡沒有列出待處理警示，不代表警示檢查已完成。` ``。對照 RC-760 定稿（審查文件第 65 行）：`{n}` 與「條」之間是一個半形空格，「。」「，」「。」都是全形。n 傳入 `rules.length`（`AlertStatusStrip.tsx:103`），是規則總數。 |
| 右側 `<span>` 已移除 | 符合 | diff 刪除 `<span className="text-xs text-neutral-500">…`。head 的狀態 B 只剩 `<p className="text-sm text-neutral-300">`，樣式沒有變淡。 |
| `buildAlertsQueriedAt` 與 JSDoc 一併移除 | 符合 | diff 刪除函式與 JSDoc。我在 head 的 `frontend/app` 搜尋，該字串只出現在 `componentWordingScan.test.ts:2173、2178、2179` 的負向斷言，沒有呼叫端。 |
| A、C、D、錯誤句字面與優先序不變 | 符合 | head 的 `AlertStatusStrip.tsx:58-95` 順序仍是 C、D、A、B。diff 中 A、C、D 與錯誤句的渲染碼都沒有改。有改的是兩處註解，不影響渲染。D 的字面 `ALERTS_SCHEDULER_DISABLED` 與測試 `toBe` 都沒動。 |
| RC-770 F1 測試都做到、改回舊字會變紅 | 符合 | 見第 2 節。「改回舊字會變紅」是實作者自報的實測（5 個測試失敗）。我沒有重跑，但從斷言內容看，`toBe`、`toContain(整個 <p>)`、`not.toContain("目前沒有待處理警示")` 確實會抓到舊字。 |
| typecheck、vitest、build、lint 綠燈 | 無法獨立確認 | 只有實作者自報：tsc exit 0、vitest 3149 全過、build 成功、無 lint script。我沒有獨立重跑（見第 5 節）。 |
| 新增註解用英文並標註 RC-760～RC-772 | 符合（有 low 註記） | `oneLinerWording.ts` 與 `AlertStatusStrip.tsx` 的新註解是英文，都標了「RC-760 to RC-772」。測試的新註解也標了。 |

### 2. RC-770 F1 的 1～5 項
1. 做到。`componentWordingScan.test.ts` 的 `buildAlertsRulesNoEvents(4)` 改為 `toBe` 定稿全文，n = 4。
2. 做到。移除 `buildAlertsQueriedAt` 的斷言與 import，新增原始碼掃描測試。範圍比要求大：`oneLinerWording.ts` 和 `AlertStatusStrip.tsx` 都檢查「查詢時間」「buildAlertsQueriedAt」「目前沒有待處理警示」。
3. 做到。`alertStatusStrip.test.ts` 的期望改成新全文（含 `:133-134` 那處，n = 1），並加了 `not.toContain("目前沒有待處理警示")`、`not.toContain("查詢時間")`、`not.toMatch(/安全|正常|無風險|沒事/)`。另外多比對整個 `<p>` 標籤與 `not.toContain("<span")`，比要求更嚴。
4. 做到。狀態 D 的反向斷言（`not.toContain("條規則已設定")`）不在 diff 內，原樣保留。
5. 做到。規則全部停用時，期望新全文（n = 2），並加了 `not.toContain("0 條規則已設定")`。

### 3. 移除 `eventsAsOf` prop：可接受
- 狀態 B 是它唯一的使用處，移除後留著會變成無用參數，所以連同 `formatDateTime` import 一併拿掉合理。
- 依賴檢查：我在 head 的 `frontend/app` 搜尋 `eventsAsOf`，零命中。`AlertStatusStripView` 只有兩處使用：`AlertStatusStrip.tsx:138` 的 wiring（已同步改）和 `alertStatusStrip.test.ts`（`renderStrip` 已同步移除參數）。`SectorMomentumCard.tsx:210` 只是註解提到，不依賴。
- `app/page.tsx`、`queries.ts` 在 diff 中零變動，符合檔案範圍。
- `AlertStatusStripViewProps` 是 export，有外部呼叫端的風險。上面的搜尋已排除 `frontend/app` 內的呼叫端，所以可接受。
- 這屬於範圍外的小改動，建議在 risk-gate 時一併告知 risk-compliance-officer。

### 4. qa-e2e：要做
- 依據：CLAUDE.md §2「涉及 UI 再加 qa-e2e 實機驗收」，加上 RC-769 共同條件第 6 點（375 與 1280 的證據；e2e 不能用時，照 ADR-0007 與 e2e-fallback 處理）。
- 實作者自己說明沒有做 e2e，也沒有人工看過渲染畫面。
- 建議範圍：狀態 A、B、C、D 與載入失敗，在 375 與 1280 兩種寬度，共 10 張。
- 重點看：
  - 狀態 B 整句在 375 是否被截斷或溢出。
  - 句子變長後，`flex flex-wrap justify-between` 容器只剩一個子元素，是否有版面問題。
  - 對比（`text-neutral-300` 疊在 `bg-neutral-950/40` 上），這是既有樣式，沿用定稿要求。
- 若 e2e 工具缺席，走 e2e-fallback，不得放寬唯讀邊界。

### 5. 驗證
typecheck、vitest、build 都未獨立重跑。上面的結果全是實作者自報。我的 Bash 只准跑兩條 `git diff`，其餘用 Read、Grep。

## 問題清單
### apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx
- [可維護性][low] 新增的英文註解直接接在既有的中文註解同一個區塊（`:97-100`），語言混在一起。建議把英文與中文註解分段。不擋件。

### apps/stock-desk/frontend/app/lib/oneLinerWording.ts
- [可維護性][low] 狀態 D 的 JSDoc 被改寫成「狀態 B（N 條規則已設定）會被誤讀成…」（約 `:94`），以中文改寫。這是為了避開舊句的 Grep，用意合理，但語意稍弱。可接受。

### 其他
- [風控註記] `settings/DirectorySection.tsx:75、81` 的「查詢時間」是別的功能，依 RC-769 註明不在範圍，不是問題。
- head 的 `frontend/app`（含 `__tests__`）搜尋「目前沒有待處理警示」，只出現在測試的負向斷言。排除 `__tests__` 後零命中，符合 risk-gate 的 Grep 條件。
- 實作者揭露「依據檔不在 base 工作樹，從 `e433c3aa` 讀取」。我直接讀的是工作目錄的審查文件，RC-760、RC-769、RC-770 的字面與其所述一致。

## 唯讀權限判準常數
未觸及。diff --stat 只列 4 個 `apps/stock-desk/frontend/` 檔案，沒有 `scripts/validate_agents.py`。我讀完整份 diff，沒有任何 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH` 的增減行，也沒有 shadow 定義。因權限限制不能加管線，這兩道檢查是以讀 `--stat` 與完整 diff 的方式替代 grep。

## 下一步
1. qa-e2e 在 375、1280 兩寬度，對狀態 A、B、C、D 與載入失敗取證。
2. 送 risk-compliance-officer 做 risk-gate，並附上 `eventsAsOf` 移除的說明。
3. 合併前，由 coordinator 書面確認 RC-769 共同條件第 1～5 點。
4. 建議 CI 或實作者提供 typecheck、vitest、build 的獨立綠燈證據。

## 我跑過的指令與讀過的檔案
指令（只有這兩條）：
1. `git diff --stat 872adcc1d3bbbc136d3ce7d7008d6f6dbfcc77a2 e054055f7ce83eeffe1461a40c6b4ca49ce20dea`
2. `git diff 872adcc1d3bbbc136d3ce7d7008d6f6dbfcc77a2 e054055f7ce83eeffe1461a40c6b4ca49ce20dea`

讀過的檔案：
- `/home/user/AICompany/.claude/skills/code-review-checklist/SKILL.md`
- `/home/user/AICompany/.claude/skills/ui-delivery-checklist/SKILL.md`
- `/home/user/AICompany/work/reviews/2026-11-26-前端調整字面逐字審RC760至RC772-風控.md`（Grep 加 Read 第 55-79、243-332 行）
- `/home/user/AICompany/work/reviews/2026-11-26-F1首頁狀態B實作交件-frontend-engineer.md`
- `/home/user/AICompany/.claude/worktrees/agent-ae6916d8ea93b35d9/apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx`（第 45-144 行）
- 以 Grep 搜尋 `/home/user/AICompany/.claude/worktrees/agent-ae6916d8ea93b35d9/apps/stock-desk/frontend/app` 的整個 `app` 目錄（`eventsAsOf`、`buildAlertsQueriedAt`、`AlertStatusStripView`、「目前沒有待處理警示」、「查詢時間」）

Verdict: PASS_WITH_NOTES
BLOCKING_ISSUES=false

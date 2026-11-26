# RC-695 技術分析區收起審查

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**PASS_WITH_NOTES，BLOCKING_ISSUES=false**（單家審查，Codex 依 CEO 決策 #58 不可用，未跑 `/review`）。

RC-769 RC-695 段的四項核對全部「符合」。RC-770 的 1～5 項都有做到。`keyLevels.ts` 的行為和原本一致。實作者揭露的三點都可接受。沒有 critical 或 high。有 3 項 low、1 項 medium 的建議，都不擋件。

## 各部門回報（qa-reviewer）

**一、RC-769 RC-695 段核對**

| 核對項 | 判定 | 證據 |
|---|---|---|
| 收起與保留範圍和 RC-764 完全一致 | 符合 | 見下方範圍對照。 |
| 載入中、載入失敗、`insufficient_data` 三個分支不變 | 符合 | `page.tsx:386-390` 沒有進 diff。`technicalCollapsed` 要求 `bars.data.status === "ok"` 才可能為真（`:142-145`）。新測試涵蓋載入中和 `insufficient_data` 兩個分支。 |
| 日線正常時技術分析區逐字不變 | 符合 | 見下方正常日線的說明。 |
| T-3 的測試都綠 | 符合，但未獨立重跑 | 依實作者回報，全量 3191 個測試通過。我讀碼確認 `priceUnitBadge.test.ts:767` 鎖的字面 `{bars.isSuccess && bars.data.status === "ok" && (` 還在（`page.tsx:391`）。 |

**範圍對照（RC-764 與 `page.tsx` 的對照）**
- **收起，全部做到：**
  - `PriceChart`、signals 的錯誤與資料不足面板、`IndicatorOverviewChipsRow`、一句結論：都在 `:395` 起三元的 else 側。
  - `<details>` 裡 signals 的骨架（`:467`）、`TechnicalIndicatorsPanel`（`:468`）、「共 N 根日線」那一行（`:474`）：都加了 `!technicalCollapsed`。
- **保留，全部沒動：**
  - `<details>` 本身（`:427`）。
  - 兩行「資料來源：」加完整徽章（`:441-464`）。
  - 頁尾導引句（`:480`）。
  - 標題列的 compact 徽章：不在 diff 內。
- **樣式：** `text-sm text-neutral-400`，符合 RC-764。
- **其他：**
  - 定稿句常數逐字等於 RC-764，渲染位置只有一處。
  - 零差異檔 `KeyLevelsPanel.tsx`、`DecisionCard.tsx`、`entryObservation.ts`、`entryObservationWording.ts`：不在 diff stat 內。
  - backend：diff stat 沒有 backend 檔。

**正常日線逐字不變：** 三元的 else 側是原本區塊搬進來，只是沒重新縮排，標記內容沒變。其他三處是 `!technicalCollapsed &&`，正常時為 true，輸出等同。實作者說他拿 head 和 base 的整頁 HTML 比對過，結果相同，但那次比對沒留在 repo，我沒法重驗。新測試只是部分替代。

**二、RC-770 RC-695 段 1～5 項（逐項讀過新測試檔）**
1. 常數用 `toBe` 鎖字，並鎖前綴「目前沒有可用的日線資料」。做到。
2. close、high、low 各自測 `NaN`、`Infinity`、`-Infinity`、`0`、`-1`、`abc`、空字串，全部回「不可用」。正常批次回「可用」。做到。
3. 壞值 fixture 有 4 組（close 0、high -1、low 0、close `abc`）：
   - 定稿句只出現 1 次。
   - 圖表、指標列、指標卡、「近 100 根日線」、「共 100 根日線」都消失。
   - 資料來源行數與徽章數和正常頁相同，頁尾導引句還在。
   - 做到。
4. 禁用詞「資料錯誤」「損壞」「重新抓取」「暫」「恢復」：常數不含，整頁的出現次數不多於正常頁。做到。
5. 反向：正常 fixture、日線載入中、日線 `insufficient_data` 都不出現定稿句。做到。

**三、`keyLevels.ts` 行為對照（讀 `keyLevels.ts:102-108` 和 `dailyBarsUsability.ts:33-47`）**
- **判斷規則：** 原本是三個欄位串在一起 `.some(!Number.isFinite(n) || n <= 0)`，用 `parseFloat`。現在是 `parseFloat`、有限值、`> 0`，三欄逐根檢查。邏輯等價，`NaN` 一樣被擋。
- **空陣列：** `if (bars.length === 0) return null` 還在最前面，順序沒變。共用函式對空陣列回「可用」，所以 `computeKeyLevels([])` 仍回 `null`。
- **其他：** `closes`、`highs`、`lows` 仍在函式內計算，供後面使用。新測試另外驗證兩者對壞值和正常批次的判定一致。
- 結論：與原本 `:101-106` 一致。

**四、揭露三點的判定**
- **三元運算子、內層不重新縮排：接受。**
  - 是為了保住既有測試鎖的字面，也讓 diff 小。
  - 風險只有縮排不整齊，格式化或後續 H1 改動時再整理即可。
  - 該處已有英文註解說明。
- **空陣列回「可用」：接受。**
  - 函式註解寫明了，`computeKeyLevels` 自己保留長度判斷。
  - 這是現況：「ok 但 0 根」的頁面不收起，RC-764 沒規定。
  - 這點應記入追蹤，不擋件。
- **部分「變紅」實測在三元重構前做：接受。**
  - 舊字和 `high` 檢查兩項測在舊結構上。
  - 但拿掉判斷那項在最終結構上重測過，7 個變紅。
  - 舊字測的是常數 `toBe`，和結構無關，所以失效風險低。
  - 我沒獨立重跑。

**五、RC-767 要求**
- 共用函式有回傳型別 union，註解預留 `gap` 狀態（`{d}`、`{x}`、`{k}`）。
- 註解固定判斷順序：先整批壞值，再跳空，非台股不判。
- 註解要求呼叫端用 `=== "unusable"`。`page.tsx:145` 和 `keyLevels.ts:108` 都照做。
- 不可用狀態下，測試斷言「跳空」「公司行動」「已除權」不出現。diff 內也沒有任何 H1 字面。
- RC-767 說四處（技術分析區、關鍵價位面板、決策卡、六項條件）讀同一結果。這次落地了其中兩處：技術分析區和關鍵價位。決策卡和六項條件屬 RC-766 第 3、4 項，另案，符合 RC-769 的範圍限制。

**六、發現（皆不擋件）**
- [Edge case][medium] `page.tsx:142-145` 的 `technicalCollapsed` 用 `bars.data !== undefined`，但渲染處（`:391`、`:441`、`:474`）用 `bars.isSuccess`。
  - 日線重抓失敗而 React Query 保留舊的壞值 data 時，`isError` 為真、`data` 仍在。
  - 此時 `<details>` 裡的卡片被收起，但主視圖是錯誤面板，不會出現定稿句，兩邊不一致。
  - 建議改用 `bars.isSuccess && bars.data.status === "ok"`，讓判斷與渲染條件一致。這需要走後續小修。
- [Edge case][low] 定稿句只放在 `chartTab === "local"` 的面板。TradingView 分頁目前被旗標關閉，若日後打開，`<details>` 會收起卻看不到定稿句。實作者已揭露。
- [可維護性][low] `<details>` 摘要字「詳細：七張指標卡與風險量測」在壞值狀態下名不副實。這是 RC-766 第 2 項已列的 low，要改需 creative 起草並送風控，這次不動是對的。
- [可維護性][low] 「逐字不變」的 head 與 base 整頁比對沒留在 repo。可考慮留一個正常 fixture 的快照測試。

**唯讀權限判準常數**
- 未觸及。`git diff --stat` 的 4 個檔都在 `apps/stock-desk/frontend/app` 下，沒有 `scripts/validate_agents.py`。
- 完整 diff 我逐行讀過，沒有 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH` 的任何出現，也沒有新增 shadow 定義或改值。
- 我沒有照 skill 的管線寫法跑 grep 指令，因為本次授權的 Bash 不准加管線，改以逐行閱讀 diff 代替。

## 驗證
- typecheck、vitest、build：**未獨立重跑**。以上數字引自實作者交件（typecheck 無錯誤、vitest 120 檔 3191 測試全過、build 成功）。lint 無 script。
- UI 檢查清單：
  - 此次是只加一個 `<p>` 的收起邏輯，沒有新增顏色或 input。
  - 沒有新增 inline 色值，只用既有 token class，`text-neutral-400` 在深色底的對比沿用 `KeyLevelsPanel` 同一個樣式，在站內已有的取捨裡。
  - 沒有捏造數據。
- Codex 第二意見：未執行（CEO 決策 #58）。

## 下一步
**qa-e2e 範圍：** 我同意建議範圍：壞值與正常兩種 fixture，各跑 375 與 1280，共 4 組。補充幾點，符合 CLAUDE.md 與 RC-769 共同條件第 6 點：
- 壞值組要把 `<details>` 展開截圖，確認兩行「資料來源：」徽章還在、沒有橫向捲動、定稿句在 375 不折出怪行。
- 正常組要確認技術分析區與現況一致。
- 順手各看一次日線載入中。載入失敗與 `insufficient_data` 兩個分支已由單元測試鎖住，視覺上可不必另跑。
- e2e 不可用時走 ADR-0007 與 `e2e-fallback`，risk-gate 需看到證據。

通過後送 qa-e2e，再送 risk-compliance-officer 做 risk-gate。medium 那項建議請實作者在 e2e 前後小修，不阻擋。

BLOCKING_ISSUES=false

## 我跑過的指令
1. `git diff --stat 872adcc1d3bbbc136d3ce7d7008d6f6dbfcc77a2 fba26f8f75e72098f34c60ebaf1b858cf4f9a586`
2. `git diff 872adcc1d3bbbc136d3ce7d7008d6f6dbfcc77a2 fba26f8f75e72098f34c60ebaf1b858cf4f9a586`

## 我讀過的檔案
- `/home/user/AICompany/.claude/skills/code-review-checklist/SKILL.md`
- `/home/user/AICompany/.claude/skills/ui-delivery-checklist/SKILL.md`
- `/home/user/AICompany/work/reviews/2026-11-26-前端調整字面逐字審RC760至RC772-風控.md`（讀 RC-764、RC-766、RC-767、RC-769、RC-770 段）
- `/home/user/AICompany/work/reviews/2026-11-26-RC695技術分析區收起實作交件-frontend-engineer.md`
- `/home/user/AICompany/.claude/worktrees/agent-ac1b2db2a6f4826f8/apps/stock-desk/frontend/app/lib/keyLevels.ts`（`:80-115`）
- `/home/user/AICompany/.claude/worktrees/agent-ac1b2db2a6f4826f8/apps/stock-desk/frontend/app/position/[symbol]/page.tsx`（`:366-490`）
- 另以 Grep 查 head 的 `technicalCollapsed`、`evaluateDailyBarsUsability` 出現位置（範圍限 `frontend/app` 下的 `position/**` 與 `lib/*.ts`）。

# PR-β 三條條件閘門審查

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS_WITH_NOTES，BLOCKING_ISSUES=false。** 只對 head `bf4a5fd58ee67972bae97446614dff446c44584c` 有效。這次是單家審查（Codex 依決策 #58 不可用）。

- RC-862 的 qa 核對項、第 1～9 點、RC-863 第 1～7 點全部符合。唯一的缺口是 (g) 跳空，因為型別裡沒有 gap 這個值，本來就無法測。
- 實作者揭露的三點都可以接受，各有附帶條件，見下方第 4 節。
- 沒有 critical 或 high 問題。有 3 個 medium 和 low 的備註，不擋件。
- 兩個 commit 的切法符合 RC-862 第 7 點。
- 需要 qa-e2e 補 375 和 1280 的實機截圖，這是合併前還沒完成的項目，不是 code 問題。

唯讀權限判準常數：未觸及。
- 兩道指令的 pipe 版本不在我獲准的四條 Bash 內，所以沒有跑。
- 替代證據：`git diff --stat` 列出 8 個檔，全在 `apps/stock-desk/frontend/app/`，沒有 `scripts/validate_agents.py`。
- 指令 2、3 的完整 diff 我逐行看過，沒有出現 `READONLY_AGENTS` 或 `READONLY_ALLOWED_BASH`。
- 名單異動為空，常數的值和 shadow 定義也沒有異動。
- 沒有異動，所以不涉及「為何改」和 ADR 的問題。

## 各部門回報（qa-reviewer）

### 1. RC-862 qa 核對項

- **閘門只讀共用函式結果，沒有第二份壞值判斷：符合。**
  - `entryObservation.ts` 的 `isBarsGateOpen(usability, levels)` 只做 `usability?.status === "usable" && levels !== null`，沒有掃 bars 的 close、high 或 low（commit 1 diff）。
  - 三條都讀同一個布林值 `barsGateOpen`。
  - 後端的 `signals.status`、`advice.status`、`advice === null` 原樣保留，只會讓結果更嚴。
  - 頁面只用 `evaluateDailyBarsUsability(bars.data.bars)` 的同一個 `dailyBarsUsability`（`page.tsx:146-149`），沒有再呼叫一次。
- **零差異：符合。**
  - 指令 1 的 stat 沒有出現下列任何檔案：`dailyBarsUsability.ts`、`keyLevels.ts`、`EntryObservationPanel.tsx`、`ruleDirection.ts`、`indicatorBands.ts`、`DecisionCard.tsx`、backend。
  - `entryObservationWording.ts` 的 diff 只動 3 個 qualifier 字串（指令 2、3）。三個 formula、`ENTRY_CONDITION_THRESHOLDS`、`ENTRY_STATUS_LABELS`、`ENTRY_NO_DATA_STATEMENT` 都不在 diff 內。
  - `entryObservation.ts` 裡也沒有動這些常數。
- **允許值寫法與 bars 未載入的路徑：符合。**
  - 只有明確的 `"usable"` 才放行，`null`、`undefined`、`unusable`、`{status:"gap"}`、`{}` 都關。
  - `evaluateEntryObservation` 的第 5 個參數是必填，沒有預設值。
  - 頁面在 `bars.data` 缺少或 `status !== "ok"`（error、insufficient_data、pending）時傳 `null`（`page.tsx:146-149`），三條全關。
  - 空陣列：共用函式回 `usable`，但 `computeKeyLevels([])` 回 null（`keyLevels.ts:103`），所以 `levels !== null` 把它擋下。
  - 測試涵蓋：未載入、空陣列、未知值、有 levels 但 verdict 為 null。
- **判定範圍等價（第 9 點）：符合，而且是結構性的。**
  - `computeKeyLevels` 自己就呼叫 `evaluateDailyBarsUsability(bars).status === "unusable"` 來整批拒算（`keyLevels.ts:108`），兩邊用同一份判斷。
  - 共用函式的判定是：整批任一根的 close、high、low 非有限或 ≤ 0 就不可用（`dailyBarsUsability.ts:32-47`）。這和 RC-862 第 9 點的字面一致。
  - 測試 `entryObservationUnusableGate.test.ts` 的 RC-862 point 9 區塊，用同一組 fixture 斷言兩邊判定一致：(a)～(d)、`NaN` close、乾淨 bars。

### 2. RC-862 行為要求第 1～9 點

1. **單一 fail-closed 閘門：符合。** 見上。未來新增的值（例如 gap）、`undefined` 一律關。「跳空」目前不存在，見第 4 節第 2 項。
2. **bars 未成功載入也要攔：符合。** error、非 ok、空陣列都攔，不預設為可用。
3. **不依賴後端狀態：符合。** 有一條測試專門斷言「後端 advice 是 ok 但 bars 壞時仍被攔」，也斷言 `advice === null` 時仍是無法判定。
4. **不得有第二份壞值判斷：符合。** 沒有掃描 bars。`levels !== null` 的判定見第 4 節。
5. **規則條件壞值下一律無法判定：符合。**
   - 閘門檢查在 `rulesCondition` 最前面，所以不論 `held` 是 true、false 或 null，也不論 `matched_rules` 是空陣列或有乾淨規則，結果都一樣。
   - RED-1 路徑維持不變，只是排在閘門之後。
   - 測試涵蓋 held true 加空規則、held true 加乾淨規則、held false、held null。
6. **正常狀態下六條逐條不變：符合。**
   - 放行路徑的程式碼沒有被改動。
   - 測試 (f) 鎖住：rules 在 held 且無防禦型命中時是 met，`observed` 為 0；動能 met 且 `observed` 為 50；成交量 met 且 `observed` 為 0.5。
   - 唯一的行為差異是「ok 加 0 根」時，動能和成交量從原本可能判定變成無法判定，這是 RC-872 第 1 點要求的，不算偏離。
7. **commit 切法：符合，已用指令 2、3 核對。**
   - commit 1（指令 2）：
     - 閘門函式、新參數、`rulesCondition` 的閘門；
     - 只改 `ENTRY_BASIS_RULES.qualifier`（RC-860）；
     - 規則的測試，以及簽名連動的測試更新；
     - `page.tsx` 那 1 行。
     - 動能和成交量的程式碼和字面，在 commit 1 都沒有被動到。
   - commit 2（指令 3）：
     - `momentumCondition`、`volumeCondition` 加閘門參數；
     - 兩個 qualifier 改成 RC-802 兩句；
     - 動能、成交量和渲染層的測試，以及 `componentWordingScan.test.ts` 的 RC-802 鎖定；
     - 三個 `entryObservation.test.ts` 的測試調整，見第 6 節。
   - 規則條件的行為和 RC-860 字面在同一個 commit，動能和成交量的行為和 RC-802 兩句在同一個 commit，符合要求。
   - 單獨 revert commit 2 不會破壞 commit 1。但單獨 revert commit 1 會讓 commit 2 無法編譯，因為閘門函式和參數在 commit 1。這不違反 RC-862 第 7 點的字面，只是備註，不擋。
8. **註解用英文，`rulesCondition` 上方補了閘門理由：符合。**
   - 小備註：commit 1 的閘門註解寫著「momentum and volume in the next commit」，commit 2 已經改掉。如果日後只留 commit 1，這句會過時，不構成問題。
9. **範圍等價：符合。** 見上。

### 3. RC-863 第 1～7 點

1. **符合。** `componentWordingScan.test.ts` 在 commit 2 加入：兩句 `toBe` 全文、`not.toContain("資料不足")`。
2. **符合。**
   - `toBe` RC-860 全文。
   - `startsWith` 原句。
   - `toContain("不因未命中而視為成立")`。
   - 九個禁用詞逐一斷言不含：壞值、資料錯誤、損壞、後端、仍、照常、取得、跳空、公司行動。
   - `:2025` 既有的 `toContain` 沒有被動到，diff 沒有刪除。
3. **符合。** 斷言 `buildEntryBasisRange(252).qualifier` 以「沒有可用日線」開頭，RC-860 也含「沒有可用日線」。
4. **符合。** 三個 formula 用 `toEqual` 鎖現況；既有的 `ENTRY_STATUS_LABELS`、`ENTRY_CONDITION_THRESHOLDS`、`ENTRY_NO_DATA_STATEMENT` 鎖定沒被動到。
5. **符合，(g) 無法做。**
   - (a)～(d)、(e)（未載入和 ok 加 []）、(f) 都有，壞值情形同時斷言 `observed` 和 `reference` 為 `null`。
   - fixture 是最壞情形：signals ok、RSI 50、z 0.5，advice 是 held 加空 `matched_rules`。
   - (g) 跳空因型別沒有 gap 而無法測。這是 PR-γ 的前置，見第 4 節。
6. **符合。**
   - (a)～(d)、bars 未載入、ok 加 [] 共六種，`ENTRY_NO_DATA_STATEMENT` 剛好出現 1 次。
   - `buildConditionCount(met, un)` 的所有組合都不出現。
   - `buildDefensiveHitsText(0)`、「命中 0 條」、「50.00」都不出現。
   - (f) 正常狀態印計數句、不印無法判定的整句。
7. **未獨立重跑。** 實作者自報 `sharedForbiddenTerms`、`componentWordingScan`、`entryObservation*` 共 759 筆全過。我只確認指令範圍涵蓋這三組。

### 4. 實作者揭露三點

1. **空陣列用 `levels !== null`：可以接受，不算第二份壞值判斷。**
   - RC-862 第 4 點禁止的是掃描 bars 的 close、high、low。`levels` 是呼叫端已算好的 `computeKeyLevels` 輸出，閘門沒有讀任何 bar 值。
   - RC-872 第 1 點本來就允許呼叫端自己擋長度，這是同一個意圖的間接實作。
   - 測試 `evaluateDailyBarsUsability([])` 為 usable 而閘門仍關，已鎖住這個語意。
   - 備註 [可維護性][low]：這個耦合只在「`computeKeyLevels` 只對空陣列或不可用回 null」成立。PR-γ 如果讓 `computeKeyLevels` 在跳空時也回 null，閘門會被拉到關閉，方向是保守的，但會和 RC-862 第 1 點的「跳空要放行」矛盾。PR-γ 必須同步重審閘門。
2. **gap 狀態目前不存在：可以接受。**
   - `dailyBarsUsability.ts:20` 的型別只有 `usable` 和 `unusable`，此時閘門只放行 `usable` 就等於「可用與跳空」都放行（跳空不存在）。
   - 測試用 `{status:"gap"}` 證明未知值被擋。
   - 附帶條件（登記給 PM）：PR-γ 加入 gap 時，要在同一支 PR 改閘門並補 (g) 測試，同時依 RC-865 第 4 點把「momentum、volume、rules 怎麼處理」補進前置清單。
3. **跑紅用工作樹還原 base 的三個檔：有條件接受。**
   - RC-864 要的是「base 上跑紅」，這個做法是等價的：還原的三個檔（`entryObservation.ts`、`entryObservationWording.ts`、`page.tsx`）正好是全部的源碼變更，測試維持 head 版本。
   - 26 筆失敗（24 加 2）和涵蓋範圍合理。實作者也有做「拿掉閘門、改回舊字」的反向實測。
   - 我沒有重跑，也沒有看 `red.txt`。
   - 備註 [可維護性][low]：「還原後 `git status` 乾淨且 HEAD 仍是 `bf4a5fd5`」是實作者自報。風控如果要求更嚴，可以請 frontend-engineer 在獨立分支上，用 base commit 加新測試檔重跑一次。

### 5. RC-871：`page.tsx` 是否只多傳一個參數

符合。指令 1 的 stat 是 `page.tsx | 1 +`，指令 2 的 diff 只新增一行 `dailyBarsUsability,`，附在既有的 `evaluateEntryObservation(...)` 呼叫末尾。這是 PR-α 已算好的同一個結果，沒有再呼叫共用函式，也沒有新增其他傳遞。

### 6. 既有測試改動

**判定：都是必要更新，沒有放寬斷言。** 但我數到的比實作者說的多一處。

- **簽名連動（新必填第 5 個參數）：**
  - `entryObservation.test.ts`、`entryObservationPending.test.ts`、`priceUnitBadge.test.ts` 的呼叫補上 `USABLE` 或由 `evaluateDailyBarsUsability` 算出。
  - 這些地方除了補參數，斷言文字沒有動。
- **4 條「levels = null 改傳 `levels()`」逐條確認（commit 2，`entryObservation.test.ts`）：**
  1. RSI 70，預期 `conditions[3]` 是 `unmet`。
  2. RSI 69.9，預期 `conditions[3]` 是 `met`。
  3. z 2，預期 `conditions[4]` 是 `unmet`。
  4. z 1.99，預期 `conditions[4]` 是 `met`。
  - 只有第一個參數從 `null` 改成 `levels()`，預期值、邊界值、斷言方法都沒變。
  - 必要的原因：閘門要求 `levels !== null`，原本傳 null 會讓動能和成交量被關閉，這四條邊界測試就測不到邊界。邊界值的測試強度沒有下降。
- **第 5 處（實作者沒列）：** `levels null` 區塊（`entryObservation.test.ts:142`）的第 5 個參數從 `USABLE` 改成 `null`（commit 2）。
  - 這個測試只斷言 range、trend、pullback 無法判定和 `observationBand` 為 null，沒有斷言動能和成交量，所以斷言沒有放寬。
  - 這個改動語意上更準確（levels 為 null 代表 bars 不可用或未載入），不構成問題。請實作者下次交件把它列進去。

### 7. qa-e2e 範圍

需要 qa-e2e 補實機驗收，單元測試不能替代，因為都是 `renderToStaticMarkup`。交件也自承沒有實機環境。範圍如下。

- **必做（RC-862 要求）：**
  - 壞值 fixture 用 (a)（最新一根 close 為 0）或 (c)（較早一根 close 為 0），signals 回健康的 RSI 和 z 值，advice 回 `held: true` 加空規則。
  - 375 和 1280 兩種寬度各一組截圖。
  - 頁尾展開後，確認 RC-860 完整可見，不截斷、不放 tooltip。逐字：「未持有此標的，或持有狀態未定時，本條一律無法判定，不因未命中而視為成立；沒有可用日線時，本條也無法判定。」
- **建議一併看的項目（同一頁，不增加環境成本）：**
  - 面板顯示「目前六條條件均無法判定。」剛好 1 次，沒有計數句，也沒有「命中 0 條」，沒有印 RSI 或 z 值。
  - 頁面其他區塊（關鍵價位、決策卡、技術分析區收起）對同一組壞值的狀態和面板一致。
  - 動能與成交量頁尾（RC-802 兩句）在 375 寬度的換行是否可讀。
  - 正常 bars 狀態的面板和現況一致。
- UI delivery checklist 第 1 節的對比、第 3 節的響應式，這次沒有新增樣式或元件，只是文字內容換了，沒有 UI 層級的新增 finding。第 0 節的風控地板：頁尾字面逐字未改，頁尾仍在原位。

### 備註（均不擋件）

- [可維護性][low] 見第 4 節第 1 項，`levels !== null` 與 PR-γ 的耦合。
- [可維護性][low] 見第 2 節第 7 點：只 revert commit 1 會讓 commit 2 無法編譯。
- [Edge case][medium] RC-862 的 (g) 跳空測試缺席，是目前不存在 gap 狀態造成的，但 PR-γ 前必須補，否則閘門與跳空放行會悄悄衝突。需 PM 登記。
- [可維護性][low] 實作者在交件說明 commit 結尾的署名用了另一組版本，與目前系統要求的署名不同。這次我沒有取得 commit 訊息全文（只能用指令 4 的標題行），不做判定，請 coordinator 合併前確認。

## 驗證

- **typecheck、vitest、build：未獨立重跑。** 以下都是實作者自報，我沒有驗證：
  - `tsc --noEmit` exit 0。
  - 全量 vitest 123 個檔、3257 則全過。
  - `next build` exit 0。
  - head 上的 759 則綠，以及 base 邏輯加 head 測試的 26 則紅。
- 我讀過的 diff 是 base 到 commit 1、commit 1 到 head 的完整 diff，不是抽樣。
- 沒有 Codex 第二意見，原因是決策 #58。
- 零差異是靠 stat 的檔案清單和 diff 內容判定，不是靠跑 `git diff -- <路徑>`（只准四條指令）。
- 沒有檢查的項目：實機畫面、`red.txt` 的原始輸出、commit 訊息全文。

**跑過的指令（只有四條，逐字照打）**
1. `git diff --stat 034fc40f3e990d18dfc5dd8a444d61d535176dbf bf4a5fd58ee67972bae97446614dff446c44584c`
2. `git diff 034fc40f3e990d18dfc5dd8a444d61d535176dbf b1ed0ea7`
3. `git diff b1ed0ea7 bf4a5fd58ee67972bae97446614dff446c44584c`
4. `git log --oneline 034fc40f3e990d18dfc5dd8a444d61d535176dbf..bf4a5fd58ee67972bae97446614dff446c44584c`

**讀過的檔案**
- `/home/user/AICompany/.claude/skills/code-review-checklist/SKILL.md`
- `/home/user/AICompany/.claude/skills/ui-delivery-checklist/SKILL.md`
- `/home/user/AICompany/work/reviews/2026-11-26-規則條件補字與PR-β範圍RC860至RC866-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-26-RC772補起草逐字審RC800至RC809-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-26-PR-α-risk-gate-RC870至RC876-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-26-PR-β三條條件閘門實作交件-frontend-engineer.md`
- head 工作樹 `/home/user/AICompany/.claude/worktrees/agent-a56fbb59886a97c8a/apps/stock-desk/frontend/app/`：
  - `lib/dailyBarsUsability.ts`（全檔）
  - `lib/keyLevels.ts`（70-139）
  - `position/[symbol]/page.tsx`（90-179）
  - `lib/__tests__/entryObservation.test.ts`（136-150）
  - `position/[symbol]/EntryObservationPanel.tsx`（Grep `allUnavailable|ENTRY_NO_DATA_STATEMENT`，命中 11、139、147）
- 另外用 Glob 列出 `work/reviews/2026-11-26-*`，只為了確認檔名。

## 下一步

1. **qa-e2e：** 照上述第 7 節補 375 和 1280 的截圖與判讀。請 qa-automation 先出證據。
2. **風控 risk-gate：** 可以進。head 一旦改變（rebase、amend、新 commit），核准就失效。
3. **frontend-engineer：** 不需修改。把第 6 節的「第 5 處測試改動」補進交件說明即可。
4. **PM 登記：** PR-γ 前置要加入「同步改閘門、補 (g) 跳空測試、重審 `levels !== null` 的耦合」（對應 RC-865 第 4 點）。
5. **coordinator：** 合併前確認 commit 署名行，以及 RC-864 的 e2e 截圖已附。

BLOCKING_ISSUES=false

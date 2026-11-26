# PR-β 三條條件閘門實作交件

- 審查者：frontend-engineer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

PR-β 已實作並 commit 在分支 `fix/entry-conditions-unusable-gate`，沒有 push、merge、rebase、amend。
- 動能、成交量、規則三條共用單一 fail-closed 閘門 `isBarsGateOpen`，只讀頁面傳入的 `evaluateDailyBarsUsability` 結果。
- 規則條件的行為與 RC-860 字面在 commit 1，動能、成交量的行為與 RC-802 兩句在 commit 2。
- 跑紅（base 邏輯）26 筆失敗，跑綠（head）759 筆全過。typecheck、全量 vitest、build 全綠。
- 有三件事要請審查者注意，見「偏離與沒有查證」：沒有 gap 狀態、空陣列的實作方式、`page.tsx` 的實際變更。

**SHA**
- base：`034fc40f3e990d18dfc5dd8a444d61d535176dbf`
- commit 1：`b1ed0ea7`，`fix: 日線不可用時規則條件一律無法判定，並補上頁尾字面`
- commit 2（head）：`bf4a5fd58ee67972bae97446614dff446c44584c`，`fix: 日線不可用時動能與成交量條件無法判定，並改頁尾兩句`

**閘門實作**（`apps/stock-desk/frontend/app/lib/entryObservation.ts`）
```ts
function isBarsGateOpen(usability: DailyBarsUsability | null, levels: KeyLevels | null): boolean {
  return usability?.status === "usable" && levels !== null;
}
```
- 只有明確 `"usable"` 才開，是列出允許值的寫法。`"unusable"`、`null`、`undefined`、未來新增的值（例如 `"gap"`）都關。
- `evaluateEntryObservation` 新增必填的第 5 個參數 `barsUsability: DailyBarsUsability | null`，沒有預設值。
- 閘門關著時，三條都回 `status: "unavailable"`、`observed: null`、`reference: null`。
- 沒有掃描 bars，沒有讀 `signals.status`、`advice.status` 這類後端狀態。既有的後端狀態檢查原樣保留。

**字面在原始碼中的實際內容**（`entryObservationWording.ts`）
- `ENTRY_BASIS_MOMENTUM.qualifier`（`:126`）：`RSI(14) 無法取得時，本條無法判定；30、70 兩端點本身不算成立。`
- `ENTRY_BASIS_VOLUME.qualifier`（`:131`）：`z 值無法取得時，本條無法判定；−2、2 兩端點本身不算成立。`
- `ENTRY_BASIS_RULES.qualifier`（`:136`）：`未持有此標的，或持有狀態未定時，本條一律無法判定，不因未命中而視為成立；沒有可用日線時，本條也無法判定。`
- 以上三句與 RC-802、RC-860 逐字一致。三個 formula、`ENTRY_CONDITION_THRESHOLDS`、`ENTRY_STATUS_LABELS`、`ENTRY_NO_DATA_STATEMENT` 零差異。

**零差異檢查**
- `git diff --name-only 034fc40f HEAD` 針對 `app/position`、`ruleDirection.ts`、`indicatorBands.ts`，只列出 `page.tsx`。
- `EntryObservationPanel.tsx`、`DecisionCard.tsx`、`ruleDirection.ts`、`indicatorBands.ts` 都沒有出現在 diff。
- `dailyBarsUsability.ts`、`keyLevels.ts`、`apps/stock-desk/backend` 的 diff 為 0 行。

## 各部門回報

**diff 統計**（全部在 `apps/stock-desk/frontend/app/` 下）

整體（base 到 head）：8 個檔案，+374 / −31
```
27	0	lib/__tests__/componentWordingScan.test.ts
22	17	lib/__tests__/entryObservation.test.ts
22	4	lib/__tests__/entryObservationPending.test.ts
243	0	lib/__tests__/entryObservationUnusableGate.test.ts   (新檔)
2	1	lib/__tests__/priceUnitBadge.test.ts
53	6	lib/entryObservation.ts
4	3	lib/entryObservationWording.ts
1	0	position/[symbol]/page.tsx
```
commit 1（base 到 `b1ed0ea7`）：8 個檔案，+262 / −25
```
20	0	componentWordingScan.test.ts
22	17	entryObservation.test.ts
22	4	entryObservationPending.test.ts
153	0	entryObservationUnusableGate.test.ts
2	1	priceUnitBadge.test.ts
40	2	entryObservation.ts
2	1	entryObservationWording.ts
1	0	page.tsx
```
commit 2（`b1ed0ea7` 到 head）：5 個檔案，+118 / −12
```
7	0	componentWordingScan.test.ts
5	5	entryObservation.test.ts
90	0	entryObservationUnusableGate.test.ts
14	5	entryObservation.ts
2	2	entryObservationWording.ts
```

**`page.tsx` 的變更**：只有一行，在既有的 `evaluateEntryObservation(...)` 呼叫末尾加上 `dailyBarsUsability,`。這是 PR-α 已算好的那個結果物件，沒有再呼叫共用函式。

## 驗證

**RC-864 跑紅（base 邏輯加新測試）**
- 做法：先把兩個 commit 做完，再用 `git checkout 034fc40f -- app/lib/entryObservation.ts app/lib/entryObservationWording.ts "app/position/[symbol]/page.tsx"`，把這三個原始碼檔還原成 base。測試檔維持 head 版本。
- 這種做法下，新測試多傳的第 5 個參數在 runtime 會被 base 邏輯忽略。測試完後用 `git checkout HEAD -- <同三檔>` 還原，`git status` 乾淨、HEAD 仍是 `bf4a5fd5`。
- 這不是「新測試 commit 在 base 上」的字面做法，是以工作樹重現的。
- 指令：`npx vitest run app/lib/__tests__/entryObservationUnusableGate.test.ts app/lib/__tests__/componentWordingScan.test.ts app/lib/__tests__/entryObservation app/lib/__tests__/sharedForbiddenTerms.test.ts`
- 條件：base 邏輯 `034fc40f`，加 head 測試檔。
- 結果：exit=1，`Test Files 2 failed | 4 passed (6)`，`Tests 26 failed | 733 passed (759)`。
  - `entryObservationUnusableGate.test.ts` 24 筆失敗，涵蓋：
    - 規則的 (a)～(d)、(e)；
    - 動能與成交量的 (a)～(d)、(e)；
    - fail-closed；
    - 渲染層 (a)～(d) 加 (e) 兩種；
    - 「後端狀態不是壞值訊號」。
  - `componentWordingScan.test.ts` 2 筆失敗：RC-860 規則字面鎖定、RC-802 動能與成交量字面鎖定。
- 完整輸出存在 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/red.txt`。

**RC-864 跑綠（head `bf4a5fd58ee67972bae97446614dff446c44584c`）**
- 同一指令：exit=0，`Test Files 6 passed (6)`，`Tests 759 passed (759)`，0 失敗。
- 這一組涵蓋 RC-863 第 7 點列的 `sharedForbiddenTerms.test.ts`、`componentWordingScan.test.ts`（含組合禁語）、`entryObservation*.test.ts`。

**改回舊字、拿掉閘門的實測**（每次實測後都還原，工作樹乾淨）
- 把動能字面改回「資料不足時」：`componentWordingScan.test.ts` 1 筆失敗（`Tests 1 failed | 661 passed`），失敗的是 RC-802 鎖定那筆。
- 把規則字面的後綴拿掉：`componentWordingScan.test.ts` 1 筆失敗（`Tests 1 failed | 661 passed`）。
- 把 `isBarsGateOpen` 改成永遠回 `true`（拿掉閘門）：`app/lib/__tests__` 全部 `Tests 24 failed | 2699 passed`。
- 備案字面（RC-861 等）沒有另外實測，只靠 `toBe` 全文鎖定。

**交件前檢查**（在 `apps/stock-desk/frontend`，head `bf4a5fd5`）
- `npm ci`：`added 98 packages`，成功。
- `npx tsc --noEmit`：exit 0，沒有輸出。
- `npx vitest run` 全量：exit 0，`Test Files 123 passed (123)`，`Tests 3257 passed (3257)`。
- `npm run build`（`next build`）：exit 0，路由表正常產出，包含 `ƒ /position/[symbol]`。

**測試涵蓋（對照 RC-863）**
- 第 1、2、3、4 點：在 `componentWordingScan.test.ts`。
  - 三個 qualifier 都用 `toBe` 全文鎖定，並檢查不含禁用詞。
  - 位階頁尾與規則頁尾同用「沒有可用日線」。
  - 三個 formula 現況鎖定。
  - 既有的常數鎖定沒動。
- 第 5 點：在新檔 `entryObservationUnusableGate.test.ts`。
  - 矩陣 (a)～(f)，壞值情形同時斷言 `observed` 和 `reference` 為 `null`。
  - fixture 刻意設成最壞：signals ok，RSI 50、z 0.5；advice 是 `held: true` 加 `matched_rules: []`。
  - (b) 和 (d) 的規則邊界也有測，涵蓋「未持有」與「持有但命中乾淨規則」。
- 第 6 點：渲染層，壞值與 (e) 的情形下，「目前六條條件均無法判定。」恰好出現 1 次。`buildConditionCount` 的所有組合都沒出現，也沒有「命中 0 條」。
- RC-872 第 1 點：`ok 加 []` 的測試有兩種：
  - 純函式層，規則、動能、成交量三條都測；
  - 渲染層。
- RC-862 第 9 點的等價證明：用同一組 fixture 斷言「`evaluateDailyBarsUsability` 為 unusable 時，`computeKeyLevels` 回 null」。含 (a)～(d) 和 `NaN` close；乾淨 bars 時兩者都可用。
- 既有測試改動：
  - 呼叫 `evaluateEntryObservation` 的測試補上第 5 個參數。
  - 原本傳 `levels = null` 又期待動能有結果的 4 條斷言，改傳 `levels()`。
  - 這是簽名變更和閘門造成的必要更新，不是放寬斷言。

## 偏離與沒有查證

1. **空陣列的實作方式（請審查者確認）。**
   - `evaluateDailyBarsUsability([])` 回 `usable`（`dailyBarsUsability.ts:37-40` 的契約，我沒動）。
   - 為了不改共用函式、也不在 `page.tsx` 多傳東西，閘門用 `levels !== null` 判斷是否有日線。`computeKeyLevels` 只在空陣列或不可用時回 null，所以「usable 加 levels 為 null」就等於「ok 加 []」。
   - 這沒有掃描 bar 值，但是用 `levels` 當空陣列的替身。
   - 如果風控或 qa 認為這等於第二份判斷，替代方案是 `page.tsx` 多傳一個長度。那會違反 RC-871「只限傳入狀態」的範圍，所以我沒有這麼做。
2. **RC-862 第 1 點的「跳空」值目前不存在。**
   - `DailyBarsUsability` 型別只有 `usable` 和 `unusable`，沒有 gap。因此閘門只放行 `"usable"`。
   - 測試用 `{ status: "gap" }` 證明未知值會被攔。
   - 等 PR-γ 加入 gap 時，必須同步改閘門，並依 RC-865 第 4 點重審。RC-862 的 (g) 跳空情形因此無法做成「和現況相同」的測試。
3. **測試裡有刻意的型別斷言。**
   - fail-closed 測試用 `as DailyBarsUsability | null`，餵入 `undefined`、`{status:"gap"}`、`{}`，這是為了模擬 runtime 的壞輸入。
   - 只出現在測試。原始碼沒有 `any` 或強制斷言。
4. **RC-864 的 e2e 截圖沒有做。**
   - 我沒有啟動實機環境，也沒有 375 與 1280 寬度的截圖。
   - 照 `e2e-fallback` 應由 qa-e2e 補上。
   - 頁尾文字在 375 寬度是否完整可見（不截斷、不放 tooltip）未實測。
5. **「壞值時面板顯示 allUnavailable」只有 `renderToStaticMarkup` 的靜態渲染驗證。** 沒有在真實瀏覽器和真實後端回應下驗證。
6. **沒有查證的事項。**
   - 後端在壞值下實際回什麼（dev-lead 的讀碼推論我沒有重驗，PR-β 的設計也不依賴它）。
   - `FRONTEND_FORBIDDEN_TERMS` 之外的人工禁用詞比對（風控已做，我只靠既有掃描測試）。
7. **環境與流程。**
   - 沒讀 `.env*`，沒碰 `backend/data/`，沒執行 `.bat`，沒碰其他 worktree。
   - 沒有被拒絕的動作。有兩次命令因為組合過長被工具拒絕，我拆開重跑，沒有繞過任何限制。
   - `npm ci` 輸出 npm audit 提示，我沒有處理，與本任務無關。
   - commit 結尾的 Co-Authored-By 與 Claude-Session 兩行，我照你指定的版本寫（`Claude Opus 5.5`）。系統提醒要求的是另一組署名，兩者不同，我以你的任務指示為準。

**下一步**：交 qa-reviewer 審查（含 Codex 第二意見），再由 qa-e2e 補 375 與 1280 寬度截圖，最後送風控 risk-gate。head 一旦改變，風控的核准就會失效。

**相關路徑**（皆在 `/home/user/AICompany/.claude/worktrees/agent-a56fbb59886a97c8a/apps/stock-desk/frontend/app/`）
- `lib/entryObservation.ts`
- `lib/entryObservationWording.ts`
- `position/[symbol]/page.tsx`
- `lib/__tests__/entryObservationUnusableGate.test.ts`
- `lib/__tests__/componentWordingScan.test.ts`

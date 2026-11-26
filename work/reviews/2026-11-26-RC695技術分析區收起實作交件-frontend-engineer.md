# RC-695 技術分析區收起實作交件

- 審查者：frontend-engineer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
RC-695 已完成並 commit 在 `fix/technical-section-unusable-bars`（只 commit，未 push、merge、rebase、amend）。日線有任一根 close、high、low 不是有限值或 ≤ 0 時，技術分析區收起，改顯示定稿句。backend 零差異。

- base SHA：`872adcc1d3bbbc136d3ce7d7008d6f6dbfcc77a2`
- head SHA：`fba26f8f`（只有這一個 commit）

`git diff --stat 872adcc1 HEAD`
```
 .../__tests__/technicalSectionUnusableBars.test.ts | 271 +++++
 .../frontend/app/lib/dailyBarsUsability.ts         |  48 ++
 .../frontend/app/lib/keyLevels.ts                  |   4 +-
 .../frontend/app/position/[symbol]/page.tsx        |  24 +-
 4 files changed, 343 insertions(+), 4 deletions(-)
```
`git diff --numstat 872adcc1 HEAD`
```
271	0	apps/stock-desk/frontend/app/lib/__tests__/technicalSectionUnusableBars.test.ts
48	0	apps/stock-desk/frontend/app/lib/dailyBarsUsability.ts
3	1	apps/stock-desk/frontend/app/lib/keyLevels.ts
21	3	apps/stock-desk/frontend/app/position/[symbol]/page.tsx
```
`apps/stock-desk/backend` 的 diff 是 0 行。`KeyLevelsPanel.tsx`、`DecisionCard.tsx`、`entryObservation.ts`、`entryObservationWording.ts` 都不在 diff 內。

## 各部門回報（frontend-engineer）

**共用函式（RC-767）**
- 新檔 `apps/stock-desk/frontend/app/lib/dailyBarsUsability.ts`，匯出 `evaluateDailyBarsUsability(bars)`，回傳 `{status:"usable"} | {status:"unusable"}`。
- 判斷用 `parseFloat`、有限值、> 0，三個欄位逐根檢查，和原本 `keyLevels.ts:101-106` 一致。
- `computeKeyLevels` 已改讀同一個函式，不再自己判斷（`keyLevels.ts:103-104` 的呼叫；原行為不變）。
- 型別 union 上有英文註解，說明 H1 會加 "gap" 狀態，並要求呼叫端用 `=== "unusable"` 判斷，不要用 `!== "usable"`。

**定稿字面（原始碼中的實際內容）**
`dailyBarsUsability.ts:28-29`
```
export const TECHNICAL_SECTION_NO_DATA_STATEMENT =
  "目前沒有可用的日線資料，技術分析區的圖表與指標不顯示。";
```
- 渲染位置在 `page.tsx:396`：`<p className="mt-3 text-sm text-neutral-400">`。

**收起的元件（`page.tsx`）**
- `PriceChart`：`:400`
- signals 錯誤面板 `ErrorPanel`：`:407`
- signals 資料不足面板 `InsufficientPanel`：`:409`
- `IndicatorOverviewChipsRow`：`:412`
- 一句結論 `buildTechOneLiner`：`:416`
  - 以上都在 `technicalCollapsed ? … : (<>…</>)` 的 else 側（`:395` 起）。
- `<details>` 裡的 signals 骨架：`:467`
- `TechnicalIndicatorsPanel`：`:468-469`
- 「共 N 根日線」那一行：`:474-476`
  - 這三處加了 `!technicalCollapsed`。

**保留的元件（`page.tsx`）**
- `<details>` 本身：`:427`
- 兩行「資料來源：」加完整徽章：`:443`、`:455`（未動）
- 頁尾導引句 `buildFooterGuidance`：`:480`
- 標題列的 compact 徽章：約 `:304` 附近（未動）
- 日線載入中、載入失敗、`insufficient_data` 三個分支：未動。`technicalCollapsed` 只在日線 `status === "ok"` 時才可能成立（`:142-145`）。

**重構細節**
- 原有的 `{bars.isSuccess && bars.data.status === "ok" && (` 這個字面保留，內層改成三元運算子。
- 原因：既有測試 `priceUnitBadge.test.ts:767` 用 `toContain` 鎖這個字面。我先寫成 `&& !technicalCollapsed` 時，那條測試變紅，所以改成三元。
- 內層區塊刻意沒有重新縮排，以縮小 diff，所以 `page.tsx:395-398` 附近縮排略不整齊。

## 驗證
在 `apps/stock-desk/frontend` 執行：
- `npm ci`：成功（會印 audit 提示，我沒有處理）。
- `npm run typecheck`（`tsc --noEmit`）：無錯誤。
- 全量 `npx vitest run`：120 個檔案、3191 個測試全部通過。
  - T-3 既有測試都綠，包含 `keyLevelsNonPositivePanel`、`priceUnitBadge`、`entryObservationPending`、`componentWordingScan`。
  - 新增的 `technicalSectionUnusableBars.test.ts` 有 41 個測試。
- `npm run build`（next build）：成功，`/position/[symbol]` 正常產出。
- lint：`package.json` 沒有 lint script，沒有跑。

**新測試涵蓋 RC-770 的 RC-695 段 1～5 項**
1. 常數 `toBe` 定稿；它和 `KEY_LEVELS_NO_DATA_STATEMENT` 都以「目前沒有可用的日線資料」開頭。
2. close、high、low 各自測 `NaN`、`Infinity`、`-Infinity`、`0`、`-1`、`abc`、空字串，全部回「不可用」。
   - 正常批次回「可用」。
   - 另外驗證它和 `computeKeyLevels` 的拒算結果一致。
3. 整頁渲染壞值 fixture（close 0、high -1、low 0、close 非數字字串各一組）：
   - 定稿句只出現 1 次。
   - 圖表、指標列、指標卡、一句結論、根數行都消失。
   - 兩行「資料來源：」數量與正常頁相同（至少 2 行），徽章數量相同，頁尾導引句還在，`<details>` 還在。
   - 另測 signals 資料不足面板在壞值時被收起，以及 signals 載入中時 `<details>` 裡的骨架被收起。
4. 禁用詞「資料錯誤」「損壞」「重新抓取」「暫」「恢復」：
   - 常數本身不含。
   - 整頁的出現次數不多於正常頁，因為正常頁本來就可能有這些字。
   - 另外確認沒有 H1 字面（跳空、公司行動、已除權）。
5. 反向測試：
   - 正常 fixture 仍有圖表、一句結論、根數行，且不含定稿句。
   - 日線載入中和日線 `insufficient_data` 兩個分支不出現定稿句。
   - 一次性比對（未留在 repo）：正常 fixture 的整頁 HTML，head 和 base 逐位元組相同（`cmp` 結果 IDENTICAL）。

**改回舊字或拿掉判斷後變紅的實測**（改完都已還原；最終 head 重跑全綠）
- 把定稿句改成舊備案字「本區無法使用的數值不顯示」：6 個測試變紅（常數 `toBe`、4 個壞值渲染、signals 資料不足面板）。
- 把 `page.tsx` 的判斷改成 `false`（拿掉判斷，重構後的最終結構上實測）：7 個測試變紅（4 個壞值渲染、signals 資料不足面板、骨架、`page.tsx` 讀共用判斷的原始碼檢查）。
- 把共用函式的 `high` 檢查拿掉：8 個測試變紅（7 個 `high` 壞值案例，加 1 個整頁 `high -1` 渲染）。
- 這輪實測是在結構改成三元之前做的：舊字、`high` 檢查兩項測於「`&& !technicalCollapsed` 版」。拿掉判斷那項在最終結構上重測過。

## 下一步
送 qa-reviewer 審查；涉及 UI，通過後再送 qa-e2e 在 375 與 1280 實機驗收，之後送 risk-compliance-officer 做 risk-gate。

**偏離與沒有查證的事項**
- 依據文件在 worktree 內不存在（它沒進 git）。我直接唯讀了主 checkout 的 `/home/user/AICompany/work/reviews/2026-11-26-前端調整字面逐字審RC760至RC772-風控.md`，只讀沒有改。
- 空陣列：`evaluateDailyBarsUsability([])` 回「可用」，因為沒有壞值。`computeKeyLevels` 仍保留自己的 `length === 0` 判斷，行為不變。但 bars 回應 `status === "ok"` 而陣列為空時，頁面不會收起。這是延續現況，RC-764 沒指定這種情況。
- 定稿句放在原本圖表分頁（local tabpanel）的位置，也就是 `<details>` 之前，全頁只出現 1 次。`TRADINGVIEW_CHART_ENABLED` 目前為 false；若日後打開 TradingView 頁籤，TradingView 面板用的是自己的資料，本次沒有改它。
- `<details>` 的摘要字「詳細：七張指標卡與風險量測」在壞值狀態下名不副實。RC-766 第 2 項已列為 low，要改摘要字需 creative 起草並送風控，所以沒動。
- 我沒有跑 e2e 或實機截圖（375 與 1280），沒有 qa-e2e 證據。
- 沒有跑 Codex 第二意見（`/review`）。
- 沒有確認 RC-769 第 2 點（#156 與暫緩解除）的書面確認，那是 coordinator 在合併當下的事。
- 沒有被拒的動作。
- 唯一的 `.env*` 與 `backend/data/` 沒有碰。

# F1 首頁狀態 B 實作交件

- 審查者：frontend-engineer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
F1 已完成並 commit，沒有 push、merge、rebase 或 amend。首頁警示狀態列的狀態 B 已換成 RC-760 定稿，右側「查詢時間」`<span>` 已不渲染。
- 分支：`fix/alert-strip-state-b-f1`
- base SHA：`872adcc1d3bbbc136d3ce7d7008d6f6dbfcc77a2`
- head SHA：`e054055f7ce83eeffe1461a40c6b4ca49ce20dea`

## 各部門回報（frontend-engineer）
變更檔案共 4 個，都在授權範圍內。`app/page.tsx`、`queries.ts` 和 backend 都是零差異（`git diff --name-only base HEAD` 只列這 4 個）。
- `apps/stock-desk/frontend/app/lib/oneLinerWording.ts`：`buildAlertsRulesNoEvents` 改為定稿句，移除 `buildAlertsQueriedAt` 和它的 JSDoc，並加英文註解標註 RC-760～RC-772。
- `apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx`：狀態 B 只剩 `<p className="text-sm text-neutral-300">`，`<span>` 已移除。
- `apps/stock-desk/frontend/app/lib/__tests__/alertStatusStrip.test.ts`：照 RC-770 F1 的 1～5 項改寫。
- `apps/stock-desk/frontend/app/lib/__tests__/componentWordingScan.test.ts`：同上，逐字比對與原始碼掃描都改了。

`git diff --stat`（commit 前）：
```
 AlertStatusStrip.tsx            | 14 +++++---------
 alertStatusStrip.test.ts        | 22 ++++++++++++++--------
 componentWordingScan.test.ts    | 16 +++++++++++++---
 oneLinerWording.ts              | 18 +++++++-----------
 4 files changed, 39 insertions(+), 31 deletions(-)
```
`git diff --numstat`（commit 前）：
```
5   9   apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx
14  8   apps/stock-desk/frontend/app/lib/__tests__/alertStatusStrip.test.ts
13  3   apps/stock-desk/frontend/app/lib/__tests__/componentWordingScan.test.ts
7   11  apps/stock-desk/frontend/app/lib/oneLinerWording.ts
```

定稿字面在原始碼裡的內容（`oneLinerWording.ts:80`）：
```
return `${n} 條規則已設定。這裡沒有列出待處理警示，不代表警示檢查已完成。`;
```
- `{n}` 和「條」之間是一個半形空格，其餘標點都是全形。
- `n` 是 `rules.length`，也就是規則總數。

額外的改動，都沒有碰到使用者看得到的字面：
- `AlertStatusStripViewProps` 的 `eventsAsOf` prop 移除。狀態 B 不再用它，留著會變成無用參數，所以連同 `formatDateTime` import 和 wiring 一起拿掉。
- 兩處註解原本引用舊句「目前沒有待處理警示」，改成不含舊句的寫法。這是為了讓 RC-769 的 risk-gate 用 Grep 時，`frontend/app`（排除 `__tests__`）裡沒有舊句。

測試依 RC-770 F1 的 1～5 項：
1. `buildAlertsRulesNoEvents(4)` 用 `toBe` 比對定稿全文。
2. 新增一個測試，斷言 `oneLinerWording.ts` 和 `AlertStatusStrip.tsx` 原始碼不含「查詢時間」「buildAlertsQueriedAt」「目前沒有待處理警示」。原本 `buildAlertsQueriedAt` 的斷言已移除。
3. 狀態 B 的渲染結果比對整個 `<p class="text-sm text-neutral-300">…</p>`。另外斷言不含「目前沒有待處理警示」「查詢時間」「<span」，也不符合 `/安全|正常|無風險|沒事/`。
4. 狀態 D 的 `not.toContain("條規則已設定")` 保留。
5. 規則全部停用時，仍印規則總數 2，且不含「0 條規則已設定」。

## 驗證
在 `apps/stock-desk/frontend` 跑的真實結果：
- `npm ci`：成功，只有 npm audit 的提示。`package-lock.json` 沒有變動。
- `tsc --noEmit`：exit 0，無錯誤。
- 全量 vitest：119 個檔案、3149 個測試全部通過。
- `next build`：成功，路由表正常輸出。
- lint：`package.json` 沒有 lint script，沒有跑。

改回舊字時變紅的實測：
- 做法：暫時把 `oneLinerWording.ts` 的句子換回「`${n} 條規則已設定，目前沒有待處理警示`」，再跑 `alertStatusStrip.test.ts` 和 `componentWordingScan.test.ts`。
- 結果：5 個測試失敗（659 個通過），失敗的是：
  - `alertStatusStrip.test.ts` 的 3 個：狀態 B 整句、規則全部停用、`schedulerEnabled` 為 null 的優先序。
  - `componentWordingScan.test.ts` 的 2 個：警示狀態列常數逐字比對、RC-770 F1 原始碼掃描。
- 還原後全量 vitest 回到 3149 個全過。還原的方式是從備份檔覆蓋，沒有留下舊字殘留。

## 下一步
送 qa-reviewer，照 RC-769 的 F1 核對項審查。通過後送 risk-compliance-officer 做 risk-gate，合併前還要 qa-e2e 在 375 和 1280 兩個視口的證據。

偏離與未查證事項：
- 依據檔不在 base `872adcc1` 的工作樹裡。我從 commit `e433c3aa`（「docs: 存檔前端調整字面逐字審 RC-760 至 RC-772」）用 `git show` 讀取內容，逐字照 RC-760、RC-769、RC-770 F1 做。我沒有確認 `e433c3aa` 是不是 base 的祖先；該 git 指令被環境拒絕，我沒有繞過。
- `eventsAsOf` prop 的移除不在任務明列的項目裡，是我判斷的結果；若要保留 prop，需要另外處理無用參數。
- 沒有做 e2e 和 375／1280 視口截圖，也沒有人工看過渲染畫面。樣式只靠 class 字串斷言確認。
- 容器仍保留 `flex flex-wrap justify-between`，因為現在只有一個子元素，所以版面上沒有影響。我沒有實機確認。
- 沒有跑 Codex `/review`。

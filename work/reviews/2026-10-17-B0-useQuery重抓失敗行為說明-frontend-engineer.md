# B0：useQuery 重抓失敗沿用舊 data 的行為書面說明（frontend-engineer）

- 審查者：frontend-engineer（只讀，未改檔）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**成功後背景重抓失敗時，面板會繼續照「最後一次成功」的 positions 渲染，畫面沒有任何提示。** 這和 `keyLevelsAnchor.ts` 的文件說法（failed → holding-unknown）不一致。它只在「首次載入就失敗、手上沒有 data」時才成立。

我建議在 B0 補一行 `isSuccess` 守門（方案 1），不新增字面。此外 KeyLevelsPanel 沒有 DecisionCard 那種 advice 與 positions 的矛盾降級，這點風控也要知道（見 4）。

下列路徑都以 worktree `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d`（HEAD 8d6d1f3）下的 `apps/stock-desk/frontend/` 為根。

### 1. 四種情形的 `positions.data` 與 anchorSource

【事實】
- `app/lib/queries.ts:86-93`：`usePositions` 只設 `retry: 1`，沒有 `staleTime`、`refetchInterval`、`placeholderData`。
- `app/position/[symbol]/page.tsx:128`：`resolveKeyLevelsAnchor(positions.data, symbol, market)`。這裡直接傳 `.data`，沒有看 `isError`、`isSuccess`、`isFetching`。
- `app/lib/keyLevelsAnchor.ts:30`：`!positions` 才回 `holding-unknown`。
- 同檔 :32 是 `lots.length===0` 回 `close-not-held`；:33、:42 是幣別不符或成本不可用回 `close-unknown`；:48 是正常情況，回 `"cost"`。
- 程式裡沒有叫 `held` 的值，持有分支就是 `"cost"`，加上 `close-unknown`（已確認持有但成本不可用）。
- query-core 5.101.4 的 `build/modern/query.js:375-389`（`case "error"`）：fetch 失敗時 `status:"error"`，但 `...state` 保留舊 data，並標 `isInvalidated:true`。
- `queryObserver.js:331,334`：`isLoadingError = isError && !hasData`，`isRefetchError = isError && hasData`。

| 情形 | `positions.data` | status／isSuccess | anchorSource |
|---|---|---|---|
| 首次載入中 | `undefined` | pending／false | `holding-unknown` |
| 首次載入失敗（retry 1 次、預設間隔約 1 秒後才轉 error） | `undefined` | error／false（isLoadingError） | `holding-unknown` |
| 成功後重抓中 | 舊 data | success／true（isFetching 為 true） | 依舊 data：`cost`／`close-unknown`／`close-not-held` |
| 成功後重抓失敗 | 舊 data（保留） | error／false（isRefetchError 為 true） | 依舊 data，同上，**不會**變 `holding-unknown` |

【推論】重抓中的 retry 期間，status 仍是 success，只累加 `fetchFailureCount`。要整輪重試都失敗才會翻成 error。

### 2. 何時重抓、跨頁新增或刪除後的行為

【事實】
- `app/providers.tsx:8`：`new QueryClient()` 沒有任何 defaultOptions。全 app 的 `refetchInterval` grep 無結果，所以沒有輪詢。
- `queryClient.js:271-272`：`refetchOnReconnect` 預設為 `networkMode !== "always"`，即 true。
- `retryer.js:7-8`：預設 retryDelay 為 `min(1000*2^n, 30000)`。

【推論】以下是 v5 預設值，我沒有逐行驗到：`staleTime` 0、`gcTime` 5 分鐘、`refetchOnWindowFocus` 與 `refetchOnMount` 皆為 true。

觸發重抓的時機：
- **mount：** 回到本頁時，因為 staleTime 為 0，會先吃快取再背景重抓。
- **視窗聚焦與網路重連：** 會重抓。
- **mutation：** `queries.ts:109-112`（`invalidatePositionQueries`）。create、update、patch、delete（含 delete 回 404 的 `onError`，:163）與匯入（:199）都會讓 `["positions"]` 失效。
- **本頁沒有自己的 mutation：** 它是唯讀。

跨頁新增或刪除後回到本頁：
- 在 `/positions` 操作時，該頁的 observer 還在，invalidate 會立刻重抓，快取通常已是新的。
- 離開後快取保留 5 分鐘，回來仍會再重抓一次。
- 超過 5 分鐘未被觀察，快取被回收，再進入等於首次載入，走 `holding-unknown`。
- 如果「刪除後的重抓」或「回到本頁的重抓」失敗，快取仍是刪除前的資料，就落入情形 3。
- **無逾時：** `app/lib/api.ts:158-170` 的 `fetch` 沒有 timeout 或 AbortSignal，重抓中（情形 4）的時間不設上限。

### 3. 沿用舊 data 時有沒有提示

【事實】
- 在 `app/` 非測試程式碼中，`isRefetchError`、`isRefetching`、`isFetching`、`isStale`、`dataUpdatedAt`、`placeholderData` 全部 grep 為 0 筆。
- positions 的狀態只有兩處被讀：`page.tsx:128` 讀 `.data`；`leverageHolding.ts:40-43` 讀 `isError`／`isSuccess`／`data`，用來決定要不要啟用槓桿查詢。
- **沒有任何 UI 提示。**
- positions 失敗不會有 ErrorPanel，只有 bars、signals、advice 各自的 ErrorPanel（page.tsx:372、385、532）。

### 4. 風險評估

【事實】兩個面板的行為不同。
- **DecisionCard**（`DecisionCard.tsx:266-277`）有交叉降級：advice 說 held 但 anchor 是 `close-not-held`，或 advice 說 candidate 但 anchor 是 `cost`，一律降成 `close-unknown`。advice 本身 `isError` 時整張卡改顯示 ErrorPanel（:531-537）。
- **KeyLevelsPanel**（`KeyLevelsPanel.tsx:412-417`）只看 `anchorSource`，不讀 advice，沒有交叉檢查。
- 它的渲染條件是 `bars.data && status==="ok"`（page.tsx:~488），不看 `isSuccess`，所以 bars 重抓失敗時也沿用舊資料。

【推論】風險情境。
- **A：已刪除，卻顯示持有分支。**
  - 條件：使用者在 `/positions` 刪除後，「刪除後的重抓」失敗，例如後端重啟或斷線；或是另一個分頁、另一台裝置刪除。接著進入本頁，mount 重抓又失敗。
  - 結果：anchor 仍是 `cost` 或 `close-unknown`。KeyLevelsPanel 照樣印 LM-16（基準句）、LM-17（持有標籤）、LM-19（相對成本損益列）。
  - DecisionCard 在 advice 也失敗時是 ErrorPanel，不外露。advice 成功且回 candidate 時被降成 `close-unknown`，也不外露。
  - 所以外露面主要是 KeyLevelsPanel，而且需要 bars 的快取也在。
- **B：新增了，卻顯示未持有。**
  - 條件相反：新增持倉後重抓失敗，快取沒有該筆。
  - 結果：anchor 是 `close-not-held`，面板印「未持有」試算。
  - 這違反 R10/R11「未確認不得宣稱未持有」的精神，因為 `isRefetchError` 時其實是「未確認」。
  - DecisionCard 若 advice 是 held 會降級，KeyLevelsPanel 不會。
- **持續多久：**
  - 情形 4（重抓中）：一次請求的時間，無逾時上限。
  - 情形 3（重抓失敗）：**直到下一次成功重抓為止。** 沒有輪詢、retry 只有 1 次，下一個觸發點只有視窗聚焦、重連、重新 mount、mutation invalidate。分頁一直停在前景且後端持續不可用時，可無限期維持。
  - 快取被 gc 的上限是 5 分鐘，但前提是沒有 observer。本頁開著時不會被回收。
- 槓桿章節在情形 3 會被啟用（`isError` 為 true，`leverageHolding.ts:41`），由後端把關，此路徑安全。

### 5. 改善方案（不新增字面，未實作）

- **方案 1（建議，改 1 行）：** `page.tsx:128` 改成 `resolveKeyLevelsAnchor(positions.isSuccess ? positions.data : undefined, symbol, market)`。
  - 效果：refetch 失敗（status 為 error）時視同 `holding-unknown`，沿用既有、已核准的 fail-closed 行為（KeyLevelsPanel 的「—」、DecisionCard 的 `close-unknown`），並與 `isLeverageQueryEnabled` 的 `isError` 邏輯一致。
  - 取捨：後端暫時連不上時，持有者的面板會暫時變「—」，屬 fail-closed。
  - 情形 4（重抓中）仍用舊 data。若要連這段也封住，要再加 `&& !positions.isFetching`，但每次視窗聚焦都會閃一下，不建議。
- **方案 2（同效果，更易測）：** 把判斷收進 resolver，簽名比照 `PositionsQueryState`，吃 `{isSuccess, data}` 這個 slice，在 `keyLevelsAnchor.ts` 內判斷。
  - 好處：可以直接在 `keyLevelsHoldingUnknown.test.ts` 加「error 且帶舊 data」的案例。目前 resolver 只能看到 `data`，單測無法表達這個情境。
  - 代價：要改 resolver 簽名，所有呼叫端與既有測試都要跟著改。
- 兩案都不動 art brief 或 wording。同時建議把 `keyLevelsAnchor.ts:14-15` 與 `page.tsx:479-484` 的註解，以及 DecisionCard 註解中「pending／failed」的說法對齊實際行為。

## 各部門回報

- frontend-engineer：以上書面說明完成。只讀碼，沒有改檔、沒有 commit、沒有啟動 server，也沒有讀 `.env` 或 `*.db`。
- 該判定交風控：KeyLevelsPanel 是否要比照 DecisionCard 補矛盾降級，需要風控裁示。

## 驗證

- 讀碼範圍：`page.tsx`、`queries.ts`、`providers.tsx`、`keyLevelsAnchor.ts`、`leverageHolding.ts`、`DecisionCard.tsx`、`KeyLevelsPanel.tsx`、`api.ts`。
- TanStack 版本：`package.json` 與 lockfile 皆為 5.101.4。worktree 內沒有 `node_modules`，我讀的是主 repo `/home/user/AICompany/apps/stock-desk/frontend/node_modules/@tanstack/query-core`，版本同為 5.101.4。
- 未驗證項：
  - 未執行任何測試或 server。
  - v5 的 `refetchOnWindowFocus`、`staleTime` 0、`gcTime` 5 分鐘預設值，是依官方預設推論，我沒有逐行讀到預設值的定義。
  - 沒讀既有測試的內容，不確定有沒有涵蓋「error 且帶舊 data」。

## 下一步

1. 由風控決定：B0 是否先採方案 1 或 2，或維持現狀並記為已知限制。
2. 若採方案 1 或 2，交 frontend-engineer 實作：改一行或改 resolver，並在 `keyLevelsHoldingUnknown.test.ts` 補「error 且帶舊 data」案例，修正註解。實作後走 qa-reviewer。
3. 若要連 KeyLevelsPanel 的跨 query 矛盾也補齊，需另開單，因為這牽涉 DecisionCard 的既有邏輯。

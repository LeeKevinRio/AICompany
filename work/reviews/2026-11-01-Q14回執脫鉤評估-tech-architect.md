# Q14 回執與 mutation 脫鉤評估

- 審查者：tech-architect
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**評估結論：建議把出清流程整組提升到頁面層。回執改用頁面層 reducer 保存，對話框改為頁面層的兄弟節點。另有三項 VETO、一項事實更正。**

1. **Q14 回執脫鉤：建議方案 A（頁面層 `useReducer`）。**
   - reducer 只有一種 action：`accepted`。state 是 `{ seq, response } | null`，沒有任何清除路徑。
   - context 不採用，`useMutationState` 否決。獨立 store 列為備案：只有在風控／PM 裁定「離開 `/playbook` 再回來也不得結束回執」時才改用，而且要放在 Providers 範圍，不得用 module singleton。
2. **對話框與 `today` 的資料流：**
   - `dataUpdatedAt` **可以**作為 R-4 的依據，但有三個前提（見各部門回報 2a）。
   - 逐句比對與送出鎖的先後關係**可以保證**「送出中 R-5 不會觸發」，前提是遵守 FE-C15～FE-C18：比對寫在 layout effect 裡，鎖在 effect 執行當下讀 ref。
   - 對話框放在頁面層，只依 `isOpen` 條件掛載，不在 `today.isSuccess` 閘門之下，也不在任何觸發鈕的宿主元件裡。
3. **焦點 info：建議要處理，列為 must。**
   - 做法：換位當下，只有在「對話框沒開、舊觸發鈕在卸載時持有焦點、commit 後焦點已落到 `<body>`」三個條件同時成立時，才把焦點交給新的觸發鈕，並使用 `preventScroll`。
   - 這不違反「不搬動焦點」類要求：它只救回已經丟失的焦點，不從使用者選定的位置搬走焦點。
   - 但這是 FR-13f 範圍外的新焦點行為（PRD:450 寫明「不新增新的焦點行為」），需要 PM 補 FR-13g／AC，並請風控知悉。
4. **TanStack Query v5 語意（repo 安裝的是 5.101.4）：**
   - (a) 背景重新取得失敗時 `isSuccess` 為 false：**成立**。但在 `retry: 1` 的重試等待期間，`isSuccess` 仍為 true。
   - (b) `invalidateQueries` 會取消飛行中的 `/today` 請求：**只有在 query 已經有 data 時才成立**。首次載入中（沒有 data）不會取消，而是併入原本那次請求。所以 **AC-55 只靠 invalidate 會失敗**，必須先呼叫 `cancelQueries`（FE-C13）。這更正了風控與 PRD 風險 17 的讀碼推論。

**VETO（否決）**
- **VETO-1**：橫幅從 `mutation.data`／`mutation.isSuccess` 渲染，或回執生命週期從 mutation 狀態推導（包含 `useMutationState`）。現行寫法 `EmergencyExitControl.tsx:311-326` 就屬於這一類，必須改掉。
- **VETO-2**：對話框、它的 state、送出鎖、`useMutation` observer，由 `today.isSuccess` 閘門之下或觸發鈕宿主內的元件持有。現況 `page.tsx:48` 加上 `ModeStatusBar.tsx:50` 就是這樣，見各部門回報 2c 的實證。
- **VETO-3**：把回執或 `exit_confirm` 存進 sessionStorage、localStorage、IndexedDB、cookie、URL 或 `history.state`。

---

## 各部門回報

### tech-architect（本人，唯讀）

#### 1. Q14 方案比較

| 方案 | 重新整理後必清空？ | 與 `onSettled` invalidate 的互動 | 能否寫測試（本 repo 沒有 jsdom，`vitest.config.ts:13-14`） | 其他缺點與風險 | 結論 |
|---|---|---|---|---|---|
| A 頁面層 `useReducer` | **必清空**（記憶體內的元件 state）。離開 `/playbook` 也會清空，和現況相同 | 無互動：invalidate 只讓 `today` 重新渲染，reducer 不受影響。捲動的 effect 只看 `receipt.seq`，所以 refetch 不會再捲 | reducer、隱藏判斷、捲動判斷都是純函式，可在 node 測；初始結構用 `renderToStaticMarkup` 測 | 「離開頁面再回來」會結束回執，是否等同重新整理要裁定（見下一步 Q15） | **採用** |
| B context | 由 provider 放的位置決定：放在 page 就等於 A，放在 root 就等於 D | 同 A | 可注入 value 做靜態渲染測試 | 只是傳遞機制，本身不是儲存。消費者都在 page 內，用 props 就夠，多一層間接、也容易被跨頁沿用 | 不採用（D 成立時可以當傳遞層） |
| C `useMutationState` | 目前會清空，因為沒有 persister；但這要靠「以後也不加 persister」才成立 | 不受 invalidate 影響，但受 **mutation GC** 影響：`reset()`、下一次 `mutate()`、卸載都會讓舊 mutation 失去 observer（`mutationObserver.ts:96-100, 119-123, 134`），沒有 observer 後 5 分鐘被回收（`mutation.ts:143-146, 155-162`；`removable.ts:25-28`）。例如第二次送出失敗後取消，5 分鐘後橫幅消失，違反 FE-3 | 要用真的 QueryClient 加假計時器，測的是 TanStack 內部語意 | 回執生命週期被綁在 mutation cache 上，正是 FE-3 禁止的形態；改 `gcTime: Infinity` 又會讓 cache 無上限增長 | **否決**（VETO-1） |
| D 獨立 store | 在記憶體內就會清空。能撐過 SPA 換頁 | 無互動 | store 是純 TS 模組，最好測；但 module singleton 需要測試用的 reset | module singleton 在 SSR 時會跨請求共用；換頁回來要避免重捲（`lastHandledSeq` 要在掛載時初始化） | 備案，限 Providers 範圍（比照 `providers.tsx:8`） |

#### 2. 對話框與 `today` 的資料流（Q2；即 PRD 的 Q12 (2)(3)）

**(a) `dataUpdatedAt` 可以作為 R-4 的依據，前提三點：**
- 語意符合 R-4 的「取得時間」：
  - 成功時寫入 `dataUpdatedAt ?? Date.now()`（`query.ts:731-734`），是前端時鐘的取得時刻。
  - 失敗時不改它（`query.ts:670-684`），所以 R-2 保留的舊句仍帶著原本的取得時間。
  - 內容完全相同的 refetch 也會更新它（`query.ts:654-664`）。
  - observer 結果原樣暴露這個值（`queryObserver.ts:573`）。
- **前提 1**：對話框要在採用那組句子時，把 `heldAt` 存進自己的 state。不要直接讀即時的 `today.dataUpdatedAt`：送出鎖期間會跳過比對，第 3 步的降級句也不更新，這兩種情況下即時值和「持有的那一組」不一致。
- **前提 2**：台北日曆日用固定 UTC+8 的算術，或 `Intl` 的 `Asia/Taipei`，寫成純函式。比對的兩端用同一個前端時鐘。使用者的系統時鐘若不準，日界也會跟著偏，這點可接受，但要記錄下來。
- **前提 3（需風控確認）**：成功取得、而且逐句比對內容相同時，就把 `heldAt` 更新為新的 `dataUpdatedAt`。理由：那一組句子在新的取得時刻被重新取得過，仍然為真。不更新的話，會在剛確認過內容沒變的情況下仍降級，屬於多餘的出口摩擦（EX-2）。
- **R-4 的評估時機**（回答 AC-52、PRD:1259）：
  - 每次比對執行時；
  - 依 `heldAt` 設定的「下一個台北午夜」計時器觸發時；
  - `visibilitychange` 轉為可見、或視窗取得焦點時（涵蓋背景分頁計時器被節流、筆電睡眠）；
  - 「我已閱讀，繼續」與「確認送出全部出清」的處理函式開頭，以同步方式再檢查一次。
  - 送出鎖期間一律不評估。
  - 送出前若檢查到 R-4 成立、而且確認過的是正式句，這次點擊改為執行 R-5 退回第 2 步，不送出。這時鎖還沒取得，不算「送出中換句」，但它把一次送出點擊轉成退步，**請風控確認**。

**(b) 逐句比對與送出鎖的先後關係：不會讓 R-5 在送出中觸發。** 時序如下：
1. 使用者點擊後，`submit` 處理函式同步執行：先判斷 `lockRef.current || isPending`，再做 R-4 同步檢查，然後設 `lockRef = true`，最後呼叫 `mutate()`。
2. `mutate()` 會同步 dispatch pending（`mutation.ts:213`），但 React 看到 `isPending` 要等 notifyManager 以 `setTimeout 0` 排程（`notifyManager.ts:15`）。這段空窗由 ref 補上，和現行 `EmergencyExitControl.tsx:71-74` 的理由相同。
3. JS 是單執行緒，effect 不會插在事件處理函式中間執行。所以只要比對寫在 effect 裡、而且**在 effect 執行當下讀 `lockRef.current`**，就不存在「鎖已取得、比對卻看到 false」的交錯。
4. 如果比對先發生並退回第 2 步，變動句的勾選已被清掉，「繼續」鈕會變成 disabled（`playbookView.ts:396-398`），不會誤觸前進。
5. 失敗後的順序：mutate 層級的 `onSettled` 先釋放鎖，然後才通知 listener（`mutationObserver.ts:163-224`）。`isPending` 列在 effect 的依賴裡，所以鎖釋放後會對最新的 `today` 重跑一次比對，符合 R-5「出清失敗後 R-2～R-4 照樣適用」。
- **禁止**在 render 內做比對。現行 `EmergencyExitControl.tsx:80-82` 就是在 render 內處理，必須刪除。

**(c) 元件邊界：**
- `PlaybookPage` 唯一一次呼叫 `usePlaybookToday`（`page.tsx:38`）。
- 頁面層的 `useEmergencyExitFlow` 持有：`useEmergencyExit` observer、回執 reducer、`isOpen`、`lockRef`、共用的 `triggerRef`、關閉時的焦點歸還、換位時的焦點交接。
- `ExitTriggerButton` 是純外觀元件。它出現在兩個位置：一是 `{today.isSuccess && <ModeStatusBar trigger={…}/>}`，二是 h1 列內的 `{!today.isSuccess && …}`。兩處由同一個判斷式決定，所以任一 frame 恰好一個。
- `EmergencyExitDialog` 是頁面根節點的子節點，只依 `isOpen` 條件掛載，照舊 portal 到 body。它在掛載時依 R-1 決定那組核取句，所有本地 state 隨關閉卸載而丟棄，這同時滿足 F-1「關閉時丟掉」和「重新開啟時不出現 N1」。
- **VETO-2 的實證**（現行結構撐不過 `/today` 失敗）：
  - success 轉 error 時，`EmergencyExitControl` 被卸載，observer 退訂並移除（`mutationObserver.ts:96-100`）。
  - observer 沒有 listener 時，mutate 層級的 callback 不會執行（`mutationObserver.ts:164`），所以 `setStep("idle")` 和釋放鎖（`EmergencyExitControl.tsx:108-115`）都不會發生。
  - portal 對話框隨元件一起消失，違反 FR-7b、V-46、AC-22。
  - 重新掛載後是新的 observer，從 idle 預設 state 開始（`mutationObserver.ts:145-148`），回執也跟著遺失。

#### 3. 焦點 info：能處理，建議處理，不違反「不搬動焦點」

- **為什麼要處理：** 最常見的路徑不是使用者剛好按 Tab 停在觸發鈕上，而是：`/today` 非 success 時出清成功，焦點依 FR-13f 回到 h1 列的觸發鈕；接著 `onSettled` 的重新取得成功，觸發鈕換位，焦點掉到 `<body>`。V-12、V-38(c)（規範:207、:334）要求這幾種狀態下焦點不得落在 `<body>`，不處理的話這兩條會不穩定。
- **怎麼做：**
  - `ExitTriggerButton` 卸載時，在 layout effect cleanup（或 ref cleanup）裡記下「`document.activeElement === 自己`」。
  - 新觸發鈕掛載時，在 layout effect 裡檢查三個條件：對話框沒開、上一步有記到、目前 `activeElement` 是 body 或 null。三者都成立才呼叫 `focus({ preventScroll: true })`。
  - 兩顆鈕在同一次 commit 換位，cleanup 先執行、mount 後執行，順序成立。
  - 「cleanup 執行時節點還在 DOM 內」是 React 的實作順序，不是文件保證，**要由 qa-e2e 在三家瀏覽器實測**。若某家不成立，結果只是退回現狀（焦點落在 body），不會更糟。
- **不違反風控要求的理由：** 既有的「不搬動焦點」條款各有對象：
  - §2.4 與 N-163：焦點不搬到橫幅；
  - V-41：不靠焦點讓失敗面板可見；
  - R-6：N1 出現時不搬動焦點；
  - F-7：不得落在 `ErrorPanel` 或 body。
  
  本做法只在焦點已經丟失時，把它交給同名、同動作的控制項；不從使用者選定的元素搬走，不捲動，不帶新字面。這比較接近 F-7 的精神，而不是違反它。

#### 4. TanStack Query 5.101.4 語意（`node_modules/@tanstack/query-core/package.json:3`）

**(a) 背景重新取得失敗時 `isSuccess` 為 false：成立。**
- error action 把 status 設為 `'error'`，但保留 data（`query.ts:670-684`）。
- `isSuccess = status === 'success'`（`queryObserver.ts:568`），這時 `isRefetchError` 為 true（`queryObserver.ts:588`）。
- 但書 1：`retry: 1`（`queries.ts:420`）期間，`failed` action 只更新失敗計數（`query.ts:632-637`），所以重試等待中 `isSuccess` 仍為 true，要等重試也失敗才轉 false（延遲見 `retryer.ts:49-51, 171-174`）。
- 但書 2：已經有 data 時，從 error 重新取得的過程中 status 不會改回 pending（`query.ts:710-728`），失敗面板會持續到成功為止。沒有 data 時重新取得會轉成 pending，畫面改顯示骨架。

**(b) `invalidateQueries` 會取消飛行中的請求：部分成立。**
- `invalidateQueries` 轉呼叫 `refetchQueries`，`cancelRefetch` 預設為 true（`queryClient.ts:291-320`）。
- 但 `query.fetch` 只在 `this.state.data !== undefined` 時才靜默取消舊請求（`query.ts:404-413`）；沒有 data 時直接回傳正在進行的那個 promise（`query.ts:414-418`）。
- 被取消的那次請求，晚到的回應會被丟棄（`retryer.ts:88-93, 112, 119`）。但 `getPlaybookToday` 沒有讀 `signal`（`api.ts:437-439`；`query.ts:449-456, 548`），所以網路請求本身不會中止。
- 視窗取得焦點時的 refetch 不取消飛行中請求（`query.ts:333-336`）。
- **對 AC-55 的影響：** AC-55 的情境是首次載入中、沒有 data。出清前發出的那次 GET 晚到後會被套用，而且不會另發新請求，狀態列可能停在 `normal`。
- **解法：** 在 hook 層的 `onSettled` 先同步呼叫 `void cancelQueries(["playbook-today"])`：它以 revert 方式還原到 pending／idle（`queryClient.ts:276-289`；`query.ts:541-547, 594-601`），不會派發 error，畫面維持骨架。然後再呼叫 `void invalidateQueries(...)`。
- 兩者都**不得 await**：hook 層的 callback 會在 dispatch success 之前被 await（`mutation.ts:246-271`），await 了會讓「送出中」一直延續到 `/today` 回來。
- 現行程式只在成功時 invalidate（`queries.ts:463-466`），還沒有落實 FR-8a。

#### 決策（ADR 草案，交 tech-writer 落檔）

```markdown
# ADR-0036：stock-desk 排程台出清流程的狀態擁有層——回執與 mutation 脫鉤、對話框提升至頁面層

- 狀態：proposed
- 日期：2026-10-31
- 決策者：tech-architect（草案）、CEO（核可）

## Context（背景）
- 風控 r3 回審 FE-3／FE-4 與 PRD FR-7a、FR-7b、FR-12、FR-12b 要求：
  - 回執只被重新整理或新回執結束；
  - 對話框撐過 `/today` 任何狀態；
  - 觸發鈕依 `today.isSuccess` 在兩處換位（r3 §10 方案 B）。
- 現況的回執、對話框、mutation observer 都在 `ModeStatusBar` 內的 `EmergencyExitControl`，位於 `isSuccess` 閘門之下（page.tsx:48、ModeStatusBar.tsx:50）。
  - 卸載時 observer 被移除，mutate 層級的 callback 不會執行（query-core mutationObserver.ts:96-100、164）；
  - 回執取自 `mutation.data`，`reset()` 或下一次 `mutate()` 都會清掉它（mutationObserver.ts:119-143）。
- 讀碼確認：`invalidateQueries` 在 query 沒有 data 時不取消飛行中請求（query.ts:404-418）。
- 前端測試環境為 node、沒有 jsdom（vitest.config.ts:13-14）。

## Options（選項比較）
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 頁面層 reducer | 生命週期與頁面一致；沒有全域狀態；reducer 是純函式、可測 | 離開頁面即結束 | 「離開頁面」是否等同重新整理需裁定 |
| B context | 方便注入 | 只是傳遞層、多一層間接 | 被跨頁沿用 |
| C useMutationState | 不用自己保存 | 綁在 mutation GC（預設 5 分鐘）與 cache 內部語意 | 回執提前消失 |
| D 獨立 store | 撐過 SPA 換頁、最好測 | 全域狀態 | module singleton 在 SSR 跨請求共用 |

## Decision（決策）
1. 回執由 PlaybookPage 的 reducer 持有。只有 `accepted` 一種 action，seq 單調遞增，沒有清除路徑。若 D 經裁定成立，改用 Providers 範圍的 store，介面不變。
2. `useEmergencyExit` observer、`isOpen`、送出鎖、觸發鈕 ref、焦點歸還與交接，提升到頁面層的 `useEmergencyExitFlow`。對話框是頁面層節點，只依 `isOpen` 條件掛載。觸發鈕是純外觀元件，依 `today.isSuccess` 在兩處擇一渲染。
3. R-2～R-6 寫成純 reducer，由對話框內的 layout effect 驅動。effect 執行當下讀送出鎖。
4. `useEmergencyExit` 在 `onSettled` 先同步呼叫 `cancelQueries`，再呼叫 `invalidateQueries`，兩者都不 await。

## Consequences（後果）
- 好處：
  - 回執與對話框都不受 `/today` 狀態影響；
  - V-42、V-46、AC-55、AC-60 有結構性保證；
  - 核心規則可在 node 環境做單元測試。
- 代價：
  - `EmergencyExitControl` 要拆成三個單元；
  - N-159 的 portal 守門測試（EmergencyExitPortal.test.ts）要改掃新檔案；
  - 頁面元件變複雜；
  - 回執在離開頁面時結束（若 D 成立則不會）。
- 約束：沿用 ADR-0002 的 TanStack Query，不引入狀態管理套件。新增一個 `cancelQueries` 呼叫點，不改 react-query 預設值（與 ADR-0035 Context 一致）。
- 壞處：焦點交接依賴 React 的 commit 順序（cleanup 先於 DOM 移除），要靠 e2e 守住；無法在 node 環境驗證。
```

#### 對實作的約束（逐條可檢查）

- **FE-C1** 回執 state 只存在 `PlaybookPage`（或它呼叫的 page 專屬 hook）的 `useReducer`。`app/playbook/` 下沒有其他元件持有回執。
- **FE-C2** `exitReceiptReducer` 的 action union 只有 `accepted`。state 是 `{ seq: number; response: PlaybookEmergencyExitResponse } | null`，seq 每次 +1。沒有 clear 或 reset 類 action。
- **FE-C3** 橫幅只從 receipt 渲染。`app/playbook/` 內不得以 `mutation.data`、`mutation.isSuccess`、`useMutationState`、`getMutationCache` 驅動橫幅（VETO-1）。
- **FE-C4** 只在頁面層 observer 的 mutate 層級 `onSuccess` 中 dispatch `accepted`。不在 render 中，也不在監看 mutation 狀態的 effect 中。
- **FE-C5** 回執與 `exit_confirm` 不得寫入任何持久化媒介（VETO-3）。可以用 grep 檢查 `sessionStorage|localStorage|indexedDB|document.cookie|history.state`。
- **FE-C6** `<main>` 內的 `role="status"` 容器是 h1 列的下一個兄弟，無條件渲染：不在任何依 `today.*` 切換的條件或 fragment 內，沒有 `key`，沒有 class。頁面根節點的元素型別在各狀態下相同。
- **FE-C7** 橫幅 R 的隱藏條件是純函式 `today.isSuccess && today.data.mode_reason === receipt.response.mode_reason`，在 page 內與狀態列閘門同一次 render 計算（V-16、FE-2）。
- **FE-C8** 捲動 effect 的依賴只有 `receipt?.seq`。`lastHandledSeq` 在掛載時初始化為當下的 seq，只有 seq 大於它時才捲動。不依賴任何 `today.*`（FE-4）。
- **FE-C9** `mutation.reset()` 只能在打開對話框時用來清掉上一輪的失敗面板。失敗面板顯示條件是 `mutation.isError && step === "final"`；R-5 退步時不 reset（FR-14g）。
- **FE-C10** `useEmergencyExit` observer、`isOpen`、`lockRef`、`triggerRef` 都在頁面層。`ModeStatusBar` 不得 import 對話框或 `useEmergencyExit`（VETO-2）。
- **FE-C11** `EmergencyExitDialog` 的掛載條件只有 `isOpen`，不出現在任何 `today.*` 條件之下。
- **FE-C12** 觸發鈕的兩個位置由同一個 `today.isSuccess` 判斷式擇一渲染，共用同一個 ref 物件。
- **FE-C13** `useEmergencyExit` 的 hook 層 `onSettled`（成功與失敗都會執行）依序呼叫 `void cancelQueries` 和 `void invalidateQueries`，兩者都只針對 `["playbook-today"]`，都不 await。
- **FE-C14** R-1：對話框在掛載時以 `exitConfirmChecks(today.isSuccess ? today.data.exit_confirm : null)` 決定句子，並記下 `source` 與 `heldAt = today.isSuccess ? today.dataUpdatedAt : null`。全部存在對話框自己的 reducer 內，對話框外沒有副本。`today` 由 page 以 prop 傳入，不另開 observer。
- **FE-C15** R-2～R-6 寫成純函式 `exitDialogReducer`。刪除 `EmergencyExitControl.tsx:80-82`；render 內不做任何比對。
- **FE-C16** 比對由對話框內的 `useLayoutEffect` 驅動，依賴是 `[today.status, today.dataUpdatedAt, isPending, tick]`。第一行在執行當下讀 `lockRef.current || isPending`，鎖住就直接返回。不得把鎖的狀態先存成 render 期間的變數再拿進 effect 用。
- **FE-C17** `submit` 的同步順序固定為：鎖判斷、R-4 同步檢查、`lockRef = true`、`mutate()`。鎖只在 mutate 層級的 `onSettled` 釋放。
- **FE-C18** R-4 只在持有的是正式句時適用。台北日曆日用純函式計算。評估時機依各部門回報 2a 的四類；送出鎖期間一律不評估。逐句相同時更新 `heldAt`，此條待風控確認。
- **FE-C19** 關閉時的焦點歸還寫在頁面層 effect，條件是 `isOpen` 由 true 轉 false，做法是 `triggerRef.current?.focus({ preventScroll: true })`。現行 `EmergencyExitControl.tsx:135` 沒有帶 `preventScroll`，要改。
- **FE-C20** 換位時的焦點交接依第 3 點的三個條件，三者同時成立才執行，並帶 `preventScroll`。除此之外，不得新增任何焦點移動。

#### 測試清單

在 node 環境的 vitest 跑：
- **FE-T1** `exitReceiptReducer`：
  - 初始值為 null；
  - 第一次 accepted 後 seq 為 1，第二次 accepted 後 seq 為 2，並取代舊回執；
  - 未知 action 回傳同一個參照；
  - 用 `@ts-expect-error` 斷言沒有 clear 類 action。
- **FE-T2** 隱藏判斷的真值表：
  - `isSuccess` 為 false 時一律不隱藏；
  - 嚴格相等時隱藏；
  - 只差空白時不隱藏。
- **FE-T3** `shouldScrollForReceipt` 的判斷，加上一個源碼掃描：捲動 effect 的依賴陣列只有 seq。
- **FE-T4** `renderToStaticMarkup` 渲染 `PlaybookPage`，QueryClient 依序預置四種狀態：pending、沒有 data 的 error、有 data 的 error、success。每種都斷言：
  - `<main>` 內恰有 1 個 `role="status"`，而且緊接在 h1 列之後；
  - 「全部出清」觸發鈕恰有 1 個。
- **FE-T5** 源碼掃描（對應 FE-C3、FE-C5、FE-C10、FE-C11、FE-C15）：
  - 沒有 `today.data?.exit_confirm`；
  - 沒有以 mutation 狀態驅動的橫幅；
  - `EmergencyExitPortal.test.ts` 改掃新檔案。
- **FE-T6** 函式庫契約測試，直接用 QueryClient 與 QueryObserver：
  - (a) refetch 失敗後 `isSuccess` 為 false、`isRefetchError` 為 true、data 仍在；重試等待中 `isSuccess` 仍為 true。
  - (b) 有 data 時 invalidate，被取消那次請求晚到的回應不套用。
  - (c) 沒有 data 時 invalidate 會併入原本的請求。這條用來記錄缺口，升級套件時若語意改變會被抓到。
  - (d) 先 `cancelQueries` 再 invalidate：舊回應被丟棄，status 全程維持 pending。
  - (e) 內容相同的 refetch 會更新 `dataUpdatedAt`；error 不改它。
- **FE-T7** `useEmergencyExit`：用 `vi.mock` 替換 api，搭配 MutationObserver，斷言成功與失敗時都依序執行 cancel 與 invalidate，而且 mutation 的結束不等 `/today` 回來。
- **FE-T8** `exitDialogReducer` 情境矩陣：
  - R-2；
  - R-3：降級句換正式句，已勾與未勾兩種；
  - R-3：正式句同一天內數字改變，已勾與未勾兩種；
  - 內容相同：不換句，更新 `heldAt`；
  - R-4：已勾與未勾兩種；
  - R-5：第 3 步正式句會退步，第 3 步降級句不退步；
  - 鎖住時不做任何變化，解鎖後重跑；
  - N1 跨步驟保留；
  - 句數不一致時的處理。
- **FE-T9** 台北日界的純函式：以 15:59:59.999Z、16:00:00Z 為邊界，比照現有測試在多個 TZ 下跑。
- **FE-T10** `planSubmit(state, now, locked)` 回傳 `ignore`、`stepBack` 或 `submit` 三者之一。
- **FE-T11** `shouldHandOffFocus` 的真值表。

交 qa-e2e 實機：
- **FE-T12**：
  - `role="status"` 在各狀態間是同一個節點（`===`）；
  - 焦點交接在三家瀏覽器實測，並確認「焦點在別處」或「對話框開著」時不交接；
  - `scrollY` 差為 0；
  - AC-55 的延遲 mock；
  - AC-60 的三條序列。

### 其他部門
本次只有本人評估，其他部門沒有參與。

---

## 驗證

**讀過的檔案：**
- 依據文件：
  - 風控 r3 回審全文；
  - Q11 裁示全文；
  - 規範 r3 的 §2.4（:140-179）、V-16～V-20（:250-259）、§10（:382-481），以及 grep 命中的 V-12、V-38、V-42、V-45、V-46、§13；
  - PRD 的 FR-7～FR-14g（:260-529）、AC-8、AC-21、AC-55～AC-60，以及 Q12、Q14 列。
- 前端程式：
  - `page.tsx`、`ModeStatusBar.tsx`、`EmergencyExitControl.tsx` 全文；
  - `queries.ts:1-60, 400-479`；`playbookView.ts:380-444`；
  - `providers.tsx`、`vitest.config.ts`、`next.config.ts`、`package.json`；
  - `EmergencyExitPortal.test.ts:1-60`；`api.ts` 的 grep 命中處。
- TanStack 原始碼：
  - `query.ts`（:395-776 的相關段落）、`queryObserver.ts:440-599`、`queryClient.ts:255-344`；
  - `mutationObserver.ts` 全文、`mutation.ts:105-274`、`useMutationState.ts` 全文；
  - `removable.ts`、`retryer.ts`、`notifyManager.ts` 的 grep 命中處。
- 既有 ADR：ADR-0001、ADR-0002:20、ADR-0031、ADR-0033、ADR-0035:39 的相關段落。與既有 ADR 沒有衝突。

**判斷的性質：**
- 全部是讀碼推論，沒有跑任何程式或測試。
- 「layout effect cleanup 先於 DOM 移除」是 React 實作順序的推論，需要 qa-e2e 實測。
- 沒讀 `.env`，沒碰 `data/*.db`，沒改任何檔案。

---

## 下一步

**交辦事項：**
- **frontend-engineer**：依 FE-C1～FE-C20 拆分 `EmergencyExitControl`，並在同一個 PR 補上 FE-T1～FE-T11。
- **tech-writer**：把 ADR-0036 草案落檔到 `docs/adr/`，狀態為 proposed。
- **risk-compliance-officer**（只需確認，不涉及新字面）：
  - (1) Q4(b) 更正：AC-55 的讀碼推論只有部分成立，已改用 FE-C13 補上；
  - (2) FE-C18 的 `heldAt` 更新規則；
  - (3) 送出前同步檢查到 R-4 時，把點擊轉為退步；
  - (4) 焦點交接（FE-C20）知悉。
- **product-manager**：
  - 新增 Q15：「離開 `/playbook` 再回來」是否視同重新整理。若不視同，改採方案 D。
  - 新增 FR-13g 與對應 AC，承接焦點交接。
  - 關閉 Q12：以本報告第 2、4 點作答。
  - 更新風險 17：invalidate 只在 query 已有 data 時才取消飛行中請求，已以 FE-C13 補救。
- **qa-automation**：FE-T6 是套件升級時的守門測試，列入常駐測試。
- **qa-e2e**：執行 FE-T12。V-12、V-38(c) 增加一種情境：「關閉後 `/today` 才恢復」。

**需要 CEO 裁示：** 只有 ADR-0036 的核可。Q15 由風控與 PM 先裁定，若影響回執地板再升級。

**相關檔案：**
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/page.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/ModeStatusBar.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/EmergencyExitControl.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/playbookView.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/__tests__/EmergencyExitPortal.test.ts
- /home/user/AICompany/apps/stock-desk/frontend/node_modules/@tanstack/query-core/src/query.ts
- /home/user/AICompany/apps/stock-desk/frontend/node_modules/@tanstack/query-core/src/queryClient.ts
- /home/user/AICompany/apps/stock-desk/frontend/node_modules/@tanstack/query-core/src/mutationObserver.ts
- /home/user/AICompany/work/prd/2026-10-29-出清後回饋畫面-N164N165.md
- /home/user/AICompany/work/art/2026-10-29-出清後回饋畫面-視覺規範.md

# ADR-0037 補充一（FE-R3 揭露地板 INV-1、FE-C24 networkMode）

- 審查者：tech-architect
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**裁定：FE-R3 走路 1（不吞例外），再加一條細化：`accept()` 先寫入，再吞掉訂閱者的例外。** 下方補充一可以直接貼進 ADR-0037。本次沒有新 VETO，只在 VETO-4 加一條補註。

1. **路 1 的核心是一條不變式 INV-1：「出清 mutation 為 success，就代表該次回應已寫入 store」。**
   - 對話框只在 success 時關閉（mutate 層的 `onSuccess`）。所以「對話框關閉、沒有橫幅」在結構上不可能出現。
   - 寫入失敗時，mutation 會落到 error，顯示 NB-6。
   - 這樣 FE-R3 的地板由 TanStack 自己的控制流保證，不需要頁面另外補判斷。
2. **`accept()` 先寫入、再吞訂閱者例外：要。**
   - reducer 算新 state 或提交 snapshot 時拋出：例外外漏，mutation 變 error，顯示 NB-6。
   - 通知訂閱者時拋出：每個訂閱者各自 try/catch，例外交給注入的 `onSubscriberError`，不從 `accept()` 外漏。
   - 結果是「`accept()` 正常返回」等於「snapshot 已提交」。不會出現「橫幅已寫入，卻被當成失敗」的情況。
3. **路 2 否決。**
   - 它會讓 mutation 狀態（success）和畫面（失敗）分岔；
   - 要新增頁面旗標，還要改 FE-C9；
   - 頁面卸載時一樣救不到；
   - 比對 `receipt.seq` 的寫法很容易長成 VETO-1 那種「從 mutation 推導回執」的形態。
4. **FE-C24 已寫好。** 除了 `retry`、`scope`，我另外加了 `retryDelay` 和 `mutationKey`，因為 `queryClient.ts:625-626` 只有在帶 `mutationKey` 時才會合併 `setMutationDefaults`。這兩鍵和 `8493a82` 現況一致，不需要再改程式。
5. **程序提醒：** ADR-0001:18 寫的是「生效後不得原地改寫，要改就開新 ADR 取代」。本補充改到的是 Decision 2 的「包 try/catch」字樣，屬於決策條文，不只是實作約束。照 coordinator 指示，我比照 ADR-0033 第 6 行的先例寫成補充，本文一字不改。但建議請 **CEO 知悉這份補充**。若 CEO 認為改到 Decision 文字就該依 ADR-0001 開新 ADR，我可以改寫成 ADR-0038 部分取代。

## 各部門回報

### tech-architect（本人，唯讀）

#### A. 檔頭補充行（貼在 ADR-0037 檔頭「狀態」之後）

```markdown
- 補充一（tech-architect 2026-11-01，依風控 `work/reviews/2026-11-01-ADR0037殘留與r32-風控.md` 的 FE-R1、FE-R3 與第 1、2 項裁示）：Decision 2 的「包 try/catch」、FE-C4、FE-T13(c) 以補充一為準；新增 INV-1、FE-C24 與 VETO-4 補註；Consequences 中 `networkMode` 與「送出中離開頁面、之後請求失敗」兩項改為已裁定。全文見〈連結〉；本檔原文不改。
```

#### B. 補充一全文（放在連結指向的位置）

```markdown
# ADR-0037 補充一：回執寫入失敗的揭露地板、出清 mutation 的 networkMode

- 日期：2026-11-01
- 撰寫：tech-architect
- 依據：risk-compliance-officer〈ADR-0037 兩項殘留裁定與規範 r3.2 確認〉（2026-11-01）的第 1 項、第 2 項、3e，以及 FE-R1、FE-R3；frontend-engineer〈出清畫面包 FE-R1～FE-R5〉的 FE-R3 段。
- 效力：本補充與 ADR-0037 本文衝突時，以本補充為準；ADR-0037 本文不改。
- 行號：TanStack Query 5.101.4 在 2026-11-01 的快照；路徑前綴 `apps/stock-desk/frontend/node_modules/@tanstack/`。

## S-1 揭露地板（FE-R3）

### 背景
ADR-0037 原 FE-C4 要求定義層 `onSuccess` 用 try/catch 吞掉 `accept()` 的例外。結果是：一旦 `accept()` 拋出例外，mutation 仍然是 success，mutate 層 `onSuccess` 照樣關閉對話框，畫面上變成「2xx 已到、對話框已關、沒有橫幅、也沒有 NB-6」。風控的揭露地板是：收到 2xx 之後，畫面上必須有受理橫幅或 NB-6 其中之一。

### 決策
1. **INV-1**：出清 mutation 的 status 為 `success`，就代表該次回應已寫入 store（`receipt.seq` 前進，`receipt.response` 是該次回應）。
   - 對話框只在 success 時由 mutate 層 `onSuccess` 關閉。所以 INV-1 成立時，「對話框關閉、沒有橫幅」不可能出現。
   - 寫入失敗的話，mutation 為 `error`，失敗面板依 FE-C9 顯示 NB-6。
2. **採「不吞例外」**。`accept()` 拋出的例外依 `query-core/src/mutation.ts:246-251` 傳到 `:273` 的 catch，接著：
   - 定義層 `onError`（`:288`）與 `onSettled`（`:313`）執行，cancel 與 invalidate 只跑一次，因為 `:263` 沒有執行到；
   - dispatch error（`:324`）；
   - mutate 層 `onError`／`onSettled` 釋放送出鎖，對話框不關閉；
   - 重新拋出的例外由 `react-query/src/useMutation.ts:56` 的 `.catch(noop)` 收掉。
3. **`accept()` 先提交、後通知**。訂閱者的例外不得從 `accept()` 外漏。所以「`accept()` 正常返回」等於「snapshot 已提交」。
4. **否決路 2**（保留吞例外，由頁面比對 `receipt.seq` 補救），理由：
   - mutation 狀態與畫面分岔；
   - 要新增頁面旗標並修改 FE-C9；
   - 頁面卸載時同樣無效；
   - 容易長成 VETO-1 的形態。
5. Decision 2 的「（同步、包 try/catch、不碰任何 UI 狀態）」改讀為「（同步、不吞例外、不碰任何 UI 狀態）」。

### FE-C4（補充一修訂版，取代 ADR-0037 原 FE-C4）
- **FE-C4** `accepted` 只在 `emergencyExitMutationOptions(queryClient, receiptSink)` 的定義層 `onSuccess` dispatch。工廠只依賴窄介面 `ExitReceiptSink { accept(response): void }`。
  - (a) `onSuccess` 本體只有一個動作 `receipts.accept(response)`：同步執行，回傳 undefined。**不得用 try/catch 或 `.catch`，也不得以任何方式攔下 `accept()` 拋出的例外。**
  - (b) `accept()` 的內部順序固定：
    1. 用 reducer 算出新 state；
    2. 提交 snapshot；
    3. 逐一通知訂閱者。

    第 1、2 步拋出的例外原樣外漏。第 3 步每個訂閱者各自用 try/catch 包住，例外交給建構時注入的 `onSubscriberError`（預設 `(e) => void Promise.reject(e)`），不得中斷其他訂閱者，也不得從 `accept()` 外漏。
  - (c) `accept()` 是 store 寫入的唯一入口。第 2 步之前，除了 reducer 本身，不得加入任何可能拋出例外的邏輯，包括驗證、log、格式化。
  - (d) 定義層 callback 不得關閉對話框、移動焦點、動送出鎖或捲動。mutate 層 `onSuccess` 只關閉對話框，mutate 層 `onSettled` 只釋放送出鎖，兩者都不 dispatch `accepted`。
  - (e) 不得在 render、effect、MutationCache config、`setMutationDefaults` 或 MutationCache 訂閱中寫回執。
  - (f) 不得用頁面層旗標、比對 `receipt.seq` 或任何 mutation 狀態以外的條件，決定是否關閉對話框或是否顯示失敗面板（否決路 2）。
  - (g) 失敗面板不得呈現 `error.message` 或例外內容。用戶端例外和網路錯誤、5xx 一樣，落入 NB-6 的同一支字面。

### FE-T13(c)（補充一修訂版，取代原 FE-T13(c)；(a)(b)(d) 不變）
用真的 `QueryClient` 加 `MutationObserver`，套用 `emergencyExitMutationOptions(client, sink)`；mutate 一律比照 `useMutation.ts:56` 加 `.catch(noop)`。
- **(c1) sink 同步拋出例外**（stub 的 `accept` 直接 throw）：
  - 最終 status 為 `error`；
  - mutate 層 `onSuccess` 呼叫 0 次，`onError`、`onSettled` 各 1 次；
  - 定義層 `onSettled` 恰好 1 次，`cancelQueries`、`invalidateQueries` 各恰好 1 次；
  - 沒有 unhandled rejection。
- **(c2) store 的 reducer 拋出例外**（用真的 store，透過測試注入點讓 reducer throw）：
  - snapshot 與寫入前是同一個參照；
  - 訂閱者沒有被通知；
  - mutation 為 `error`。
- **(c3) 訂閱者拋出例外**（用真的 store，掛兩個訂閱者，第一個 throw）：
  - `accept()` 正常返回；
  - snapshot 的 seq 前進，response 是該次回應；
  - 第二個訂閱者恰好被通知 1 次；
  - `onSubscriberError` 的 spy 恰好被呼叫 1 次，參數是該例外；
  - mutation 為 `success`，mutate 層 `onSuccess` 恰好 1 次。
- **(c4) INV-1 情境矩陣**：情境為 {正常、c1、c2、c3、`mutationFn` reject}，每種都斷言：
  - 沒有「status 為 `success` 但 seq 沒前進」的組合；
  - status 為 `error` 時 `isError` 為 true，失敗面板條件 `isError && step === "final"` 在 step 為 final 時成立。
- **(c5) 源碼掃描**：
  - 工廠的 `onSuccess` 本體不含 `try`、`catch`、`.catch(`；
  - store 的通知迴圈內，每個訂閱者呼叫都包在 try/catch 中。

## S-2 出清 mutation 的 networkMode（FE-R1）

### FE-C24（新增）
- **FE-C24** 出清 mutation 只在定義層 `emergencyExitMutationOptions` 設定 `networkMode: "always"`，這個字面在 `lib/queries.ts` 恰好出現一次。
  - (a) 出清 options 不得有 `retry`、`retryDelay`、`scope`、`mutationKey` 鍵。
    - mutation 的 retry 預設就是 0（`query-core/src/mutation.ts:199`）。
    - 不帶 `mutationKey`，是因為 `query-core/src/queryClient.ts:625-626` 只在有 key 時才合併 `setMutationDefaults`。禁止 key，就封住了從 defaults 注入 retry 或 networkMode 的路徑。
  - (b) 不得在 `providers.tsx`、`defaultOptions` 或 `setMutationDefaults` 設定 `networkMode` 或 `retry`。這也和 FE-C1、`entryObservationPending.test.ts:243-245` 的 R4 絆線一致。
  - (c) 理由：
    - `'online'` 在離線時會讓 mutation 處於 `pending` 加 `isPaused`（`query-core/src/retryer.ts:53-57, 109, 219-225`），恢復連線後由 `queryClient.ts:84-90` 自動送出；
    - retry 要經過 `canContinue`（`retryer.ts:104-107`），分頁不在焦點或離線時會暫停；
    - 兩者都是延後送出。
  - (d) 守門測試：`lib/__tests__/emergencyExitOffline.test.ts`（FE-R2，`69cd00d`）列為常駐。程式已在 `8493a82` 落地。

### VETO-4 補註
- 離線暫停與 retry 都屬於延後送出，納入 VETO-4。離線暫停包括 `networkMode: 'online'`，以及任何會讓出清 mutation 進入 `isPaused` 的設定。

## S-3 Consequences 修訂（取代 ADR-0037 Consequences「壞處與殘留」中的對應兩點）

- **`networkMode`：已裁定。**
  - 依據：風控 2026-11-01 第 2 項判 `'online'` VETO、`'always'` APPROVE；FE-R1；程式 `8493a82`、測試 `69cd00d`。
  - 出清 mutation 的定義層為 `networkMode: "always"`，沒有 retry、scope（FE-C24）。
  - 離線時 fetch 立即失敗，顯示 NB-6，不暫停，事後也不自動送出；使用者可以立即重試（EX-2）。
  - 代價：NB-6 第 1 句「可能已受理」對離線來說高估了不確定性。風控判定方向保守，可以接受。
  - 不改全域預設；`providers.tsx` 的字面與 R4 絆線不受影響。
  - 依風控第 1 項 C-1，必須和本包在同一個 PR 上線。
- **送出中離開頁面、之後請求失敗：已裁定，本包不揭露。**
  - 依據：風控 2026-11-01 第 1 項，條件 C-1～C-4。
  - 這個缺口由 N-171 承接。R10 的殘留風險由風控書面接受。
  - 不得實作任何「上一次送出仍在處理中／已失敗」的顯示，也不得從 mutation cache 推導上次送出的狀態（C-4）。
  - 頁面卸載後才發生 `accept()` 失敗，也歸入這個殘留。
- **新增（S-1 的後果）：**
  - 好處：INV-1 讓「2xx 已到、卻沒有任何揭露」在頁面掛載期間無法發生。
  - 代價：前端內部錯誤（store 的 reducer bug）也會顯示成 NB-6，使用者可能因此重送。重送時 N-166 會回 S1，不會重複產生指令（ADR-0033）。
  - 定義層 `onSettled` 若在 success 路徑拋出（`mutation.ts:263`），橫幅已經寫入、mutation 卻是 error，畫面上會同時有橫幅和 NB-6。兩者都為真，可以接受，這和 busy_timeout 回 500 時的組合同類。

## S-4 待決更新
- 「`networkMode` 另案裁定」與「離開期間失敗的揭露」兩項移出待決。
- 新增（不擋本包）：出清 POST 的用戶端逾時。`request()` 沒有逾時（`app/lib/api.ts:167`），列為另案，由 tech-architect 評估，逾時後走 NB-6（風控 suggested）。
```

### 其他部門
本次只有本人評估。

## 驗證

- 讀過的檔案：
  - `/home/user/AICompany/work/reviews/2026-11-01-ADR0037殘留與r32-風控.md` 全文；
  - `/home/user/AICompany/work/reviews/2026-11-01-出清畫面包FER-frontend-engineer.md` 全文；
  - `/home/user/AICompany/docs/adr/0001-record-architecture-decisions.md` 的 grep 命中處（:17-18、:25）。
- 例外的傳遞路徑（`mutation.ts:246 → :273 → :288、:313、:324`，以及 `useMutation.ts:56`）、defaults 合併條件（`queryClient.ts:623-628`）、retry 預設值（`mutation.ts:199`），都是本輪稍早已讀過的原始碼段落，這次重新對照，沒有重新執行任何程式。
- 我沒有 Bash，無法讀 `69cd00d` 的程式碼。`accept()` 目前的內部順序與 `onSubscriberError` 注入點是否已存在，只依交件描述判斷，由 frontend-engineer 實作時確認，qa-reviewer 實查。
- 全部是讀碼推論。FE-T13(c1)～(c5) 就是用來驗證這些推論的測試。沒讀 `.env`，沒碰 `data/*.db`，沒改任何檔案。

## 下一步

- **coordinator／tech-writer**：
  - 補充一全文放到連結位置（建議由轉存本回報的檔案承載，或放 `docs/adr/` 旁的補充檔，由 coordinator 定）；
  - A 段那行貼進 ADR-0037 檔頭；
  - ADR-0037 本文不改。
- **CEO**：知悉補充一改到了 Decision 2 的「包 try/catch」字樣。若認為要依 ADR-0001:18 開新 ADR 取代，請指示，我改寫成 ADR-0038。
- **frontend-engineer**：
  - 依補充一的 FE-C4 (a)～(g) 修改 `emergencyExitMutationOptions` 與 store 的 `accept()`；
  - 依 FE-T13(c1)～(c5) 改寫並新增測試；
  - FE-C24 已符合，不用改。
- **risk-compliance-officer**：知悉 INV-1 與 FE-C4 (g)（失敗面板不呈現例外內容，用戶端例外落入同一支 NB-6）。
- **qa-reviewer**：實查 FE-C4 (b) 的提交順序、FE-C24 的四個禁用鍵、FE-T13(c4) 的矩陣。
- **qa-automation**：FE-T13 與 `emergencyExitOffline.test.ts` 列為常駐守門測試。

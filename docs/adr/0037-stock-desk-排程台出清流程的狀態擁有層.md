# ADR-0037：stock-desk 排程台出清流程的狀態擁有層——回執存於 Providers 範圍的記憶體 store、對話框提升至頁面層

- 狀態：accepted（CEO #97，2026-11-01 核可；風控對兩項殘留的裁定見 `work/reviews/2026-11-01-ADR0037殘留與r32-風控.md`，networkMode 改 `'always'` 等必改項由該裁定追加，本檔原文不改）
- 日期：2026-11-01（初稿 2026-10-31 以 0036 編號起草；0036 已由 ADR-0035 Decision 8 預留給「在途單生命週期」，改用 0037）
- 決策者：tech-architect（草案）；risk-compliance-officer（Q15 裁示採方案 D，2026-11-01）；CEO（核可）
- 來源簡稱（皆在 `work/reviews/` 下）：
  - [TA-Q14]：`2026-11-01-Q14回執脫鉤評估-tech-architect.md`
  - [風控-Q15]：`2026-11-01-Q14四項Q15與PRDv5確認-風控.md`（FE-1～FE-8、Q15 定義）
  - [FE 交件]：`2026-11-01-出清畫面包實作交件-frontend-engineer.md`（方案 A 版實作，`origin/fix/stock-desk-exit-feedback` HEAD `bbd823e`）
  - [N166]：`2026-11-01-N166判準Z回修-dev-lead.md`；ADR-0033
  - [風控-S1]：`2026-10-31-N166新字面與延長凍結揭露-風控.md`
- 與既有 ADR 的關係：
  - 沿用 ADR-0002 的 TanStack Query，不引入狀態管理套件。
  - 不改 react-query 全域預設值，與 ADR-0035 Context「前端 react-query 使用預設值」一致。
  - 「重送安全」以 ADR-0033 Decision 1～6 為前提。
  - 不取代、不修改任何既有 ADR。
- 適用範圍：僅 product/stock-desk；路徑相對於 `apps/stock-desk/frontend/`。
- 標註：文內 `檔案:行號` 是 2026-11-01 的快照（TanStack Query 5.101.4）。

> **落檔註記（tech-writer，2026-11-01）**
>
> 1. **Q15 的裁示**：Q15（離開 `/playbook` 再回來，是否視同重新整理）由風控（risk-compliance-officer）裁示**不視同、採方案 D**（Providers 範圍的記憶體 store），不採方案 A。依據：`work/reviews/2026-11-01-Q14四項Q15與PRDv5確認-風控.md`（本檔 Decision 1 即據此寫成 D 版）。
> 2. **編號變更**：初稿原以 0036 編號起草；0036 已由 ADR-0035 預留給「在途單生命週期」（N-172b／K3 與 N-176），故改用 0037。這項是 coordinator 定案（2026-11-01，CEO 可推翻），記在決策包 `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` 第 116 行。
> 3. **來源與類別**：本檔是 `work/reviews/2026-11-01-ADR0037D版與FE2評估-tech-architect.md` 第「1. ADR-0037 修訂草案」一節的轉錄，屬記錄決策脈絡（B 類）。Context 至待決為草案主文照轉錄；附錄 A、B、C 分別為同一節後面的「對實作的約束」（FE-C1～FE-C23）、「測試清單（修訂版）」（FE-T1～FE-T14）、「VETO 清單」（VETO-1～VETO-5），皆照轉錄。tech-writer 落檔時**沒有讀 code、沒有執行程式**，也沒有替草案補任何技術細節。
> 4. **行號未重驗**：文內 `檔案:行號`（含 `mutation.ts`、`mutationObserver.ts`、`retryer.ts`、`queryClient.ts`、`api.ts`、`page.tsx`、`ModeStatusBar.tsx`、`layout.tsx`、`vitest.config.ts` 等）是 tech-architect 撰寫時的快照，tech-writer 未逐條重驗，抽驗請以內容定位。來源評估檔自己也標明：所有結論都是讀碼推論，沒有跑任何程式或測試；tech-architect 沒有 Bash，無法 `git show` 兩個分支，方案 A 版實作只依 [FE 交件] 的描述判斷。
> 5. **未收錄的部分**：來源評估檔還有「2. FE-2 寫法比較與建議」與「3. info：新頁面實例的送出鎖為 false 時的重送」兩節。草案主文的 Options 與 Consequences 已涵蓋其結論，這兩節本檔不另收錄，需要時請讀來源檔。

---

## Context（背景）
- 風控 r3 FE-3／FE-4 與 PRD FR-7a、FR-7b、FR-12、FR-12b 要求：
  - 回執只會因「重新整理」或「被新一次受理的回執取代」而結束；
  - 對話框撐過 `/today` 的任何狀態；
  - 觸發鈕依 `today.isSuccess` 在兩處換位。
- 現況（`product/stock-desk`）：回執、對話框、mutation observer 都在 `isSuccess` 閘門之下的 `EmergencyExitControl` 內（`page.tsx:48`、`ModeStatusBar.tsx:50`）。
  - 元件卸載時，observer 被移除，mutate 層級的 callback 不會執行（`mutationObserver.ts:96-100, 164`）。
  - 回執取自 `mutation.data`，`reset()` 或下一次 `mutate()` 都會清掉它（`mutationObserver.ts:119-143`）。
- Q15（風控裁示）：SPA 換頁離開 `/playbook` 再回來，**不視同**重新整理。採方案 A 等於多開一條結束路徑，屬於放寬回執地板。
  - NavBar 以 `next/link` 做 SPA 換頁。
  - Providers 在 root layout 包住所有路由（`layout.tsx:17`）。
- FE-2：受理回應到達時，就算 `/playbook` 已卸載，回執仍要寫入。mutate 層級的 `onSuccess` 在卸載後不會執行（`mutationObserver.ts:164`）。
- 送出中離開再回來時，新頁面實例的送出鎖是 false，可能再送一次。依 EX-2 不擋；重送安全要由後端冪等（ADR-0033）保證。
- `invalidateQueries` 在 query 沒有 data 時，不會取消飛行中的請求（`query.ts:404-418`）。
- 前端測試環境為 node，沒有 jsdom（`vitest.config.ts:13-14`）。

## Options（選項比較）

### 回執存放處
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 頁面層 reducer | 沒有全域狀態，最簡單 | 離開頁面就結束 | 放寬回執地板（風控否決） |
| B context | 方便注入 | 只是傳遞層，本身不是儲存 | 放的位置決定一切，等於 A 或 D |
| C `useMutationState` | 不用自己保存 | 綁在 mutation GC（5 分鐘）與 cache 內部語意 | 回執提前消失（VETO-1） |
| **D Providers 範圍 store** | 撐過 SPA 換頁；store 是純 TS，最好測 | 多一個全域範圍的狀態；Providers 要多一層 | module singleton 在 SSR 會跨請求共用（以 FE-C1 禁止） |

### FE-2 寫入點
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **(a) `useEmergencyExit` 定義層 `onSuccess`** | 寫在 `Mutation.execute` 內，不依賴 observer（`mutation.ts:246-251`）；pending 中的 mutation 不會被 GC（`mutation.ts:155-158`）；與 FE-C13 的 `onSettled` 同一層 | 要自己包 try/catch；會被 await | 例外外漏時，已受理的回應會走失敗分支（`mutation.ts:273`） |
| (b) MutationCache config 的 `onSuccess`（`new QueryClient({ mutationCache })`） | 全域一定會執行 | 對所有 mutation 都會觸發，要另加 key 過濾；Providers 要知道 playbook 的領域邏輯；`mutation.ts:238` 一樣沒有 try | 改動 `providers.tsx` 的 `new QueryClient()` 字面，會觸發 `entryObservationPending.test.ts:243-245` 的風控 R4 絆線 |
| (b′) Providers 內呼叫 `setMutationDefaults` | 不動 QueryClient 建構式 | Providers 一樣耦合 playbook；hook 若也定義 `onSuccess`，會依 `queryClient.ts:623-628` 的 spread 順序**靜默覆蓋**掉 default | 回執靜默丟失 |
| (c) Providers 內訂閱 MutationCache 的 `updated` 事件（`mutation.ts:389-397`） | 不改 options | 依賴 cache 事件的形狀；同樣有 Providers 耦合；要加 mutationKey；listener 拋出的例外沒人接 | 實質上是從 mutation 狀態推導回執，貼近 VETO-1 |
| (d) store 自己發 POST | 卸載與否完全無關 | store 會持有在途狀態；對話框要的 `isPending`／`isError` 得重做一套；繞過 ADR-0002 | 違反 F-1（VETO-5） |

### 送出鎖的範圍
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **維持頁面實例範圍（ref）** | 符合 F-1、EX-2；擋得住同一對話框的雙擊 | 跨實例可能重送 | 重送的安全由 ADR-0033 承擔，見 Consequences |
| 提升到 store | 跨實例也只送一次 | 違反 F-1；`request()` 沒有逾時（`api.ts:167`），請求卡住或 mutation 離線暫停（`retryer.ts:109, 219-225`）時，鎖會一直保持到重新整理 | 出口出現看不見的前置條件，違反 EX-2（VETO-4） |
| mutation `scope` 序列化（`mutationCache.ts:160-188`） | TanStack 內建 | 第二次要排隊等第一次結束；與 FE-6(b)「不排隊」的精神相反 | 和上一列一樣會卡住（VETO-4） |

## Decision（決策）
1. **回執存於 Providers 範圍的記憶體 store（方案 D）。**
   - store 實例由 `providers.tsx` 以 `useState(() => createExitReceiptStore())` 建立，經 context 提供。
   - 頁面以 `useSyncExternalStore` 讀取。
   - state 是 `{ receipt: { seq, response } | null; scrolledSeq }`。action 只有 `accepted` 與 `scrollHandled` 兩種，沒有清除路徑。
   - 名詞定義：
     - **工作階段**：同一份文件（document）的存續期間。
     - **重新整理**：任何一次新的文件載入，包括 F5／reload、關閉或新開分頁、在網址列輸入、硬導航。同一份文件內的 SPA 換頁不算。
   - 在這個定義下，回執地板條文一字不改。
   - 橫幅只在 `/playbook` 渲染（FE-4）。
2. **寫入點是 `useEmergencyExit` 的定義層 `onSuccess`**（同步、包 try/catch、不碰任何 UI 狀態）。mutate 層級的 callback 只處理 UI：關閉對話框、釋放送出鎖。
3. **頁面層 `useEmergencyExitFlow`** 持有 `useEmergencyExit` observer、`isOpen`、送出鎖、觸發鈕 ref、焦點歸還與交接，生命週期等於頁面實例。
   - 對話框是頁面層節點，只依 `isOpen` 條件掛載。
   - 觸發鈕是純外觀元件，依 `today.isSuccess` 在兩處擇一渲染。
4. **R-2～R-6 寫成純 reducer**，由對話框內的 layout effect 驅動，effect 執行當下讀送出鎖。同一次評估的順序固定：先處理新的成功資料（R-3 或更新 `heldAt`），再評估 R-4（FE-5）。
5. **`useEmergencyExit` 的定義層 `onSettled`** 先同步呼叫 `cancelQueries`，再呼叫 `invalidateQueries`，兩者都不 await。
6. **送出鎖維持頁面實例範圍，不提升。** 跨實例重送的正確性由 ADR-0033 的鎖內覆蓋判定式冪等保證。前端不加任何跨實例閘門。
7. **捲動以「每份回執」為單位：** 「已捲過」的標記 `scrolledSeq` 放在 store；對話框開著時延後，關閉後才捲（FE-3）。

## Consequences（後果）
- 好處：
  - 回執撐過 `/today` 的任何狀態，也撐過 SPA 換頁；
  - 送出中離開頁面，回應到達後仍會寫入，回來時看得到；
  - V-42、V-46、AC-55、AC-60、AC-64 有結構性保證；
  - 核心規則都能在 node 環境做單元測試。
- 代價：
  - 多一個全域範圍的 store，Providers 多一層 context provider；
  - [FE 交件] 的方案 A 實作要遷移：`useReducer` 移出頁面、`lastHandledSeq` 刪除，`exitFlowStructure` 測試的「only one receipt reducer」和「dispatchReceipt 在 onSuccess」兩條要改寫；
  - 定義層 `onSuccess` 必須自己包 try/catch。
- 重送（跨頁面實例，送出鎖為 false）：
  - **後端**：第二次 POST 會在鎖內重讀並判定已覆蓋，不寫新指令，回 200 的 ALREADY_PENDING（S1），S1 完整重述先前那份指令。
    - 同一個 UTC 日內，凍結日取 max 後不變；
    - 若兩次請求剛好跨 UTC 午夜（台北 08:00），會延長一個交易日，由 S6 揭露；
    - 鎖等待超過 busy_timeout 5s 時，第二次回 500（ADR-0033 C-11、T-4），對話框顯示 NB-6 失敗面板，再重試會得到 ALREADY_PENDING。
  - **前端**：回執以「到達順序」取代。兩種到達順序下，最後一份都是真話，所以不另做排序或去重。
- 壞處與殘留：
  - 同一份文件內 Providers 若被重掛（目前沒有 root 的 `global-error`、`template`），回執會遺失。FE-C1 禁止重掛 Providers。
  - 部署造成 Next 的硬導航屬於新的文件載入，回執清空，符合定義。
  - bfcache 還原的是同一份文件，回執保留，符合定義。
  - 定義層 `onSuccess` 寫入發生在 success dispatch 之前（`mutation.ts:246` 先於 `:271`），橫幅可能比對話框關閉早一個 frame 出現。這是 FE-C8 捲動要延後的理由之一。
  - 送出中離開頁面、之後請求失敗：失敗不會在任何地方顯示（store 依 F-1 不存失敗）。這是 A 時期就有的缺口，D 沒有讓它變差，**交風控裁定是否需要揭露**。
  - mutation 預設 `networkMode: 'online'`：離線時按送出，請求會暫停，連線恢復後才自動送出（`retryer.ts:219-225`、`queryClient.ts:84-90`），可能發生在使用者離開頁面之後。這是既有行為、不在本 ADR 範圍，**交風控／PM 另案裁定**是否對出清這個 mutation 改用 `networkMode: 'always'`。
  - 焦點交接依賴 React 的 commit 順序（cleanup 先於 DOM 移除），只能靠 e2e 守住。
- 被約束：
  - 不引入狀態管理套件；
  - 不改 react-query 全域預設值；
  - `providers.tsx` 保留 `new QueryClient()` 字面；
  - 本前端變更不得早於含 ADR-0033 Decision 1～6 的 N-166 上線。

## 待決
- CEO 核可本 ADR。
- 風控：上面兩項殘留的裁定（離開期間失敗的揭露、`networkMode`）；FE-C8「對話框開著時延後捲動」知悉。

---

## 附錄 A：對實作的約束（FE-C1～FE-C23，交 frontend-engineer，qa-reviewer 可逐條檢查）

逐條轉錄自來源評估檔。標「改」或「新」者為本次（D 版）異動，其餘沿用 [TA-Q14]。

- **FE-C1（改）** 回執只存在 `app/lib/exitReceiptStore.ts` 建立的 store 實例中。
  - 實例由 `app/providers.tsx` 的 `useState(() => createExitReceiptStore())` 建立，經 context 提供。
  - store 模組頂層不得有可變狀態：沒有 top-level `let`、沒有模組層級的實例、沒有 `globalThis`／`window` 掛載。
  - `app/playbook/` 內不得用 `useState`、`useReducer`、`useRef` 持有回執副本。讀取一律透過 `useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)`，`getServerSnapshot` 回傳初始空狀態。
  - `providers.tsx` 必須保留 `new QueryClient()` 字面，不得出現 `defaultOptions`、`mutationCache`、`MutationCache`、`setMutationDefaults`。
  - Providers 不 import `app/playbook/` 的任何模組，不得加 `key`，不得移進 `template.tsx`。
- **FE-C2（改）** store 的 state 是 `{ receipt: { seq: number; response: PlaybookEmergencyExitResponse } | null; scrolledSeq: number }`，初始值 `{ receipt: null, scrolledSeq: 0 }`。
  - action 只有兩種：
    - `accepted(response)`：seq +1，取代 receipt；
    - `scrollHandled(seq)`：`scrolledSeq = max(scrolledSeq, seq)`，不動 receipt。
  - 沒有 clear、reset 或 setter。
  - 不得有其他欄位，依 F-1：不放 `exit_confirm`、對話框 state、送出鎖、mutation、在途旗標（VETO-5）。
- **FE-C3** 橫幅只從 store 的 receipt 渲染。`app/playbook/` 內不得以 `mutation.data`、`mutation.isSuccess`、`useMutationState`、`getMutationCache` 驅動橫幅（VETO-1）。
- **FE-C4（改）** `accepted` 只在 `useEmergencyExit` 的定義層 `onSuccess` dispatch，也就是 `emergencyExitMutationOptions(queryClient, receiptSink)` 工廠裡的那一個。規則如下：
  - 工廠只依賴窄介面 `ExitReceiptSink { accept(response): void }`；
  - 同步執行，回傳 undefined；
  - 是該 callback 的第一個動作；
  - 用 try/catch 包住，catch 內寫 `void Promise.reject(e)`，不得讓例外外漏；
  - 定義層 callback 不得關閉對話框、移動焦點、動送出鎖或捲動；
  - mutate 層級的 `onSuccess` 只關閉對話框，mutate 層級的 `onSettled` 只釋放鎖，兩者都不 dispatch `accepted`；
  - 不得在 render、effect、MutationCache config、`setMutationDefaults` 或 MutationCache 訂閱中寫回執。
- **FE-C5** 回執與 `exit_confirm` 不得寫入任何持久化媒介（VETO-3），grep 範圍包含 store 模組。
- **FE-C6** `<main>` 內的 `role="status"` 容器是 h1 列的下一個兄弟節點，無條件渲染：不在任何依 `today.*` 切換的條件或 fragment 內，沒有 `key`，沒有 class。
- **FE-C7** 橫幅 R 的隱藏條件是純函式 `today.isSuccess && today.data.mode_reason === receipt.response.mode_reason`，在 page 內與狀態列閘門同一次 render 計算。
- **FE-C8（改）** 捲動以每份回執為單位：
  - 判斷是純函式 `shouldScrollForReceipt(receiptSeq, scrolledSeq, isOpen)`，成立條件為 `receiptSeq > scrolledSeq && !isOpen`。
  - 頁面層捲動 effect 的依賴陣列恰為 `[receipt?.seq, scrolledSeq, isOpen]`，不含任何 `today.*`（FE-4）。
  - effect 執行當下從 `store.getSnapshot()` 重讀 `scrolledSeq`，不得使用 render 期間的值，以防 StrictMode 重跑時捲兩次。
  - 捲動後同步 dispatch `scrollHandled(seq)`。
  - 刪除頁面實例內的 `lastHandledSeq`。
- **FE-C9** `mutation.reset()` 只能在打開對話框時呼叫。失敗面板的顯示條件是 `mutation.isError && step === "final"`，R-5 退步時不 reset。
- **FE-C10（改）** observer、`isOpen`、`lockRef`、`triggerRef` 都在頁面層的 `useEmergencyExitFlow`，生命週期等於頁面實例，不得提升到 store、context、module 或任何跨頁面實例的範圍（VETO-4）。`ModeStatusBar` 不 import 對話框或 `useEmergencyExit`（VETO-2）。
- **FE-C11** 對話框的掛載條件只有 `isOpen`，不出現在任何 `today.*` 條件之下。
- **FE-C12** 觸發鈕的兩個位置由同一個 `today.isSuccess` 判斷式擇一渲染，共用同一個 ref。
- **FE-C13** 定義層的 `onSettled` 依序呼叫 `void cancelQueries` 和 `void invalidateQueries`，只針對 `["playbook-today"]`，都不 await。
- **FE-C14** R-1：對話框在掛載時決定核取句，並把 `source` 與 `heldAt` 存在對話框自己的 reducer 內。`today` 由 page 以 prop 傳入。
- **FE-C15** R-2～R-6 寫成純函式 `exitDialogReducer`；render 內不做任何比對。
- **FE-C16** 比對由對話框內的 `useLayoutEffect` 驅動，依賴是 `[today.status, today.dataUpdatedAt, isPending, tick]`。第一行在執行當下讀 `lockRef.current || isPending`。
- **FE-C17（改，FE-6）** `submit` 的同步順序固定為：鎖判斷、R-4 同步檢查、`lockRef = true`、`mutate()`。
  - R-4 只在鎖還沒取得、而且持有正式句時適用：
    - 第 3 步：退回第 2 步；
    - 第 2 步按「繼續」：原地換句，不前進。
  - 這次點擊直接消耗掉，`POST` 0 筆，不排隊，事後也不自動送出，不呼叫 `reset()`。
  - 鎖只在 mutate 層級的 `onSettled` 釋放。
- **FE-C18（改，FE-5）** `heldAt` 只在以下條件全部成立時更新：
  - `today.isSuccess`；
  - `today.dataUpdatedAt > heldAt`；
  - 送出鎖沒被取得；
  - 持有的是正式句；
  - 和 R-3 共用同一個比較函式，逐句嚴格相等（不 trim，句數也要相同）。

  其他規則：
  - 同一次評估先處理新資料，再評估 R-4；
  - 更新後依新的 `heldAt` 重設「下一個台北午夜」計時器；
  - error 與重試等待期間一律不更新；
  - 跨日也適用（AC-52 的「同一個台北日曆日內」限定已刪除）。
- **FE-C19** 關閉時的焦點歸還寫在頁面層 effect，觸發條件是 `isOpen` 由 true 轉 false，做法是 `focus({ preventScroll: true })`。
- **FE-C20（改，FE-8）** 換位時的焦點交接只在三個條件同時成立時執行，並帶 `preventScroll`。另外：
  - 每次卸載都覆寫「是否持有焦點」的標記；每次掛載都把它消耗掉，不論有沒有交接；
  - 只呼叫一次 `focus`，不用 rAF 或計時器重試；
  - 「關閉」與「換位」發生在同一次 commit 時，不得連續搬動焦點兩次。

  除此之外不得新增任何焦點移動。
- **FE-C21（新，FE-4）** `ExitReceiptBanner` 與 `useExitReceipt` 只能被 `app/playbook/` 下的檔案 import。`providers.tsx` 只 import store 的工廠與 provider。
- **FE-C22（新）** 出清相關檔案不得出現 `scope:`、`useIsMutating`，也不得用 `useMutationState`、`getMutationCache().find*` 決定送出、`disabled`／`aria-disabled` 或觸發鈕狀態（VETO-4）。
- **FE-C23（新）** 上線耦合：`fix/stock-desk-exit-feedback` 不得早於含 ADR-0033 Decision 1～6 的 N-166 合併或上線。dev-lead 要求和判準 Z（`36c7ceb`）一起上線或在它之後，這點照舊適用。

## 附錄 B：測試清單（修訂版，FE-T1～FE-T14）

逐條轉錄自來源評估檔。標「改」或「新」者為本次（D 版）異動；「不變」者沿用 [TA-Q14]。

node 環境的 vitest：
- **FE-T1（改）** store：
  - 初始值；
  - 連續兩次 accepted，seq 依序為 1、2，並取代舊回執；
  - `scrollHandled` 取 max、不動 receipt；
  - 未知 action 回傳同一個參照；
  - 用 `@ts-expect-error` 斷言沒有 clear 類 action；
  - **兩次 `createExitReceiptStore()` 得到的實例互不影響**；
  - subscribe 會收到通知；`getServerSnapshot` 回傳初始值。
- **FE-T2** 隱藏判斷的真值表（不變）。
- **FE-T3（改）** `shouldScrollForReceipt` 真值表，含 `isOpen`。再加源碼掃描：
  - 依賴陣列恰為三項；
  - effect 內呼叫 `getSnapshot()`；
  - 沒有 `lastHandledSeq`。
- **FE-T4（改）** 用 `renderToStaticMarkup` 渲染四種 `/today` 狀態，每種再分「store 有回執／沒有回執」兩組。斷言照舊。
- **FE-T5（改）** 源碼掃描，在原有項目外新增 FE-C1、FE-C4、FE-C21、FE-C22 的掃描：
  - `providers.tsx` 的字面；
  - store 模組沒有 top-level `let`；
  - `accepted` 只在 `queries.ts` 的定義層 `onSuccess` 出現；
  - import 範圍；
  - 沒有 `scope:`、`useIsMutating`。
- **FE-T6、FE-T7** 不變。
- **FE-T8（改）** 新增 FE-5(e) 的兩個情境：
  - 跨日後新取得、內容相同：更新 `heldAt`，沒有 N1，不退步；
  - 順序顛倒會誤出 N1 的反例。
- **FE-T9** 不變。
- **FE-T10（改）** 新增：
  - 退步並重新勾選後，下一次點擊送出 `POST` 恰好 1 筆；
  - 第 2 步按「繼續」遇到 R-4：原地換句、不前進。
- **FE-T11（改）** 新增「殘留標記」的真值表情境。
- **FE-T13（新，FE-2 契約）** 用真的 `QueryClient` 加 `MutationObserver`，套用 `emergencyExitMutationOptions(client, sink)`：
  - (a) subscribe 後送出（mutate 搭配 deferred），在 resolve 前 unsubscribe，模擬卸載；resolve 之後，store 有 seq 1，而 mutate 層級 `onSuccess` 的 spy 沒有被呼叫（記錄 `mutationObserver.ts:164` 的行為）。
  - (b) `accept` 被呼叫的當下，mutation 的 status 仍是 `pending`。
  - (c) sink 拋出例外時，mutation 最終 status 仍為 `success`，data 存在。
  - (d) 請求失敗時 store 不變。
- **FE-T14（新）** 兩個 observer 各送一次，模擬舊頁面與新頁面。兩種到達順序都要跑，斷言 seq 為 2、receipt 是最後到達的那份、每份各寫入一次。

交 qa-e2e 實機（headless Chromium 為準）：
- **FE-T12（改）** 原有項目照舊，另加：
  - AC-64 (a)～(e)；
  - 送出中按返回（POST 用延遲 mock），回來時橫幅出現，只捲一次；
  - 第一次還在飛行時從新頁面再送一次：`POST` 恰好 2 筆，橫幅是最後到達的那份，沒有 pageerror；
  - 第一份回執到達時第二個對話框正開著：對話框不關閉，捲動延到關閉之後；
  - 對話框關閉時的焦點歸還與緊接著的捲動，不會讓焦點落到 `<body>`。

建議（不阻擋）：dev-lead 或 qa-automation 補一支 API 層的並發測試：兩個 thread 用 TestClient 同時 POST，結果應為一筆 RESULT、一筆 ALREADY_PENDING。ADR-0033 的 T-1／T-2 已在 service 層涵蓋。

## 附錄 C：VETO 清單（VETO-1～VETO-5）

逐條轉錄自來源評估檔。VETO-1～VETO-3 沿用 [TA-Q14]，VETO-4、VETO-5 為本次新增。

- **VETO-1**：橫幅從 `mutation.data`／`mutation.isSuccess` 渲染，或回執生命週期從 mutation 狀態推導（包含 `useMutationState`）。
- **VETO-2**：對話框、它的 state、送出鎖、observer 由 `today.isSuccess` 閘門之下或觸發鈕宿主內的元件持有。
- **VETO-3**：回執或 `exit_confirm` 寫入 sessionStorage、localStorage、IndexedDB、cookie、URL 或 `history.state`。
- **VETO-4（新增）**：用任何跨頁面實例的機制擋住、延後或排隊送出，包括 store 裡的鎖、mutation `scope`、`useIsMutating`／`useMutationState`／`getMutationCache()` 這類送出閘門。理由：EX-2、F-1，以及沒有逾時的請求會讓鎖一直保持到重新整理。
- **VETO-5（新增）**：store 越界，包括：
  - module singleton，或掛在 `globalThis`／`window`；
  - 含 `{receipt, scrolledSeq}` 以外的欄位；
  - 由 store 發出請求，或持有在途狀態。

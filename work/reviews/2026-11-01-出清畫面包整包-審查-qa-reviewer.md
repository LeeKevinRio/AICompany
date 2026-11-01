# 出清畫面包整包審查（PASS）

- 審查者：qa-reviewer
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**結論：PASS。`BLOCKING_ISSUES=false`。**

- 範圍：`git diff origin/fix/stock-desk-exit-idempotency...origin/fix/stock-desk-exit-feedback`，41 檔，+4971/-458。
- 我逐檔讀了所有來源檔和全部測試檔，不是抽樣。
- 我沒有發現 critical 或 high 的問題。
- ADR-0037 與補充一的架構約束都落實。
- 風控裁示的必改項逐條滿足，見下方對照表。
- 所有新字面都與風控原文逐字相同，前端鏡射和後端常數之間有讀 `wording.py` 的守門測試。
- 這包涉及 UI，通過後還要做 qa-e2e 實機驗收。測試環境是 node 加 `renderToStaticMarkup`，沒有 jsdom。所以 layout effect、焦點、捲動、計時器這些執行期行為，沒有任何自動化測試跑過，只能靠 qa-e2e。

**Codex 第二意見：** 執行 `codex --version` 回 `command not found`（exit 127）。本結論是**單家審查，Codex 待環境可用時補跑**。

**Bash 使用：** 只用了 `git diff`（含 `--stat`、`--name-only`、`-G`、`-U0`）和一次 `codex --version`，沒有 pipe、沒有 `cd`，沒有越出白名單。

### 唯讀權限判準常數

**未觸及。**

- `git diff --name-only … -- scripts/validate_agents.py`：無輸出。
- `git diff -G'READONLY_AGENTS|READONLY_ALLOWED_BASH' --stat …`：無輸出。
- 這是整個 diff 範圍的搜尋，沒有任何檔案出現這兩個常數名。所以：
  - 改了什麼：沒有。成員名單沒變，也沒有其他檔案的 shadow 定義，常數的值也沒變。
  - 為何改：不適用。
  - 對應 ADR：不適用。
- 另外確認 `.claude/`、`docs/`、`CLAUDE.md` 不在這次 diff 內。後端只動了 `wording.py` 與 `test_playbook_wording.py`。
- 共用的 `ErrorPanel.tsx` 不在 diff 內，沒有被改動。

## 各部門回報

### frontend-engineer 交件：逐項核對

**1. 新字面（逐字比對）**

- **N1：** 風控 Q11 原文與 `wording.py` 常數、`playbookView.ts` 的 `EXIT_CONFIRM_CHECKS_UPDATED`、測試四處逐字相同。我用 `git diff -G` 以整句當 regex 命中這四個檔案。
- **降級句 1b、NB-6 標籤與三句：**
  - 原始碼把字串拆成多行串接，所以 `-G` 整句 regex 不會命中。
  - 我改成逐字目視比對風控 N166合併後字面、CEO87 回審、Q8 原文，全部相同，包含第 3 句的修訂版。
  - 前端和後端之間，`exitWordingMirror.test.ts` 用 `pythonWording.ts` 在測試時讀 `wording.py`，做 byte-for-byte 比對。
  - 這份測試另外把風控核可的字面寫死一份。所以只改一邊會失敗，兩邊一起改成未核可字面也會失敗。
  - helper 遇到不支援的寫法會 throw，不會悄悄回傳空值。
  - 還有「兩者於送出後的執行結果中顯示」的全 app 原始碼 grep 守門，後端註解也沒有殘留這句。
- 禁用詞（安全、放心、已執行、已出清、未確認、請關閉、視窗、只暫停了）在前後端都有負面斷言。

**2. ADR-0037 架構約束**

- store 不是 module singleton：`useState(() => createExitReceiptStore())`。`providers.tsx` 的 `new QueryClient()` 字面保留，只新增 `<ExitReceiptStoreProvider>` 包住 children。
- 定義層 `onSuccess` 本體只有 `receipts.accept(response)`，沒有 try/catch，也沒有 async。
- `dispatch` 的順序是 reducer、提交 snapshot、逐一通知。
  - 提交之前只有 `const next = reduce(...)` 和 no-op 判斷。
  - 每個訂閱者各自 try/catch，例外交給 `onSubscriberError`，預設是 `void Promise.reject`。
  - handler 自己拋出也不中斷迴圈。
  - `state = next` 只出現一次。
- `networkMode: "always"` 只出現一次。options 沒有 retry、retryDelay、scope、mutationKey。
- 沒有跨頁面實例的送出閘門：`lockRef` 只在 `useEmergencyExitFlow` 的 `useRef`。
- 沒有任何持久化媒介的使用（我讀碼確認）。
- 橫幅只在 `page.tsx` 渲染。
- 失敗面板條件是 `isError && state.step === "final"`，沒有傳遞 `error`。`mutation.reset()` 只在 `open()`。
- 掃描測試顯示 `ExitFailurePanel` 與對話框不含 `error.message`、`ApiError` 等。

**3. R-1 至 R-6**

- `exitDialogState.ts` 是純函式 reducer，我逐條對照過。
- 重點：
  - **heldAt：** 新成功資料先更新 `heldAt`，再用更新後的值評估 R-4。測試有順序顛倒會誤出 N1 的反例。
  - **跨日：** 固定 UTC+8 算術，邊界 23:59:59.999 與 00:00:00.000 都有測。
  - **送出中不換句：** `locked` 時回傳同一個物件。layout effect 第一行在執行當下讀 `lockRef.current || isPending`。
  - **R-5 退步：** 只有確認的是正式句才退。確認的是降級句時整個不動，N1 也不出現。
  - **N1：** 只在「至少清掉一個勾選」時顯示，R-4 跨日也一樣。它放在常駐、無 class 的 `role="status"` 容器，步驟之間是同一個節點。
  - **送出前 R-4 檢查：** 順序為鎖判斷、`planSubmit`、取鎖、`mutate`。stepBack 這一擊被消耗掉，沒有 POST，也沒有 `reset()`。有「退步後重勾，下一擊恰好送出」的測試。

**4. 後備觸發鈕（方案 B）**

- h1 列是 `<div class="flex items-center justify-between gap-3">`，沒有背景、邊框、sticky 或 role。
- 觸發鈕沒有 aria-label、title、disabled 等。
- `PlaybookPageStates.test.ts` 在四種 `/today` 狀態下做 V-33 的反向斷言，另外證明 `/today` 非 success 時整頁沒有 sticky 或 fixed 元素。

**5. 失敗面板**

- 面板 class 與視覺規範 V-39、V-40 逐字相同：中性色階，一個標籤加三個 `<p>`，`role="alert"`，沒有 tabIndex，沒有彩色 token。
- 面板用 `useLayoutEffect` 捲動對話框容器，`behavior: "auto"`，不搬焦點。

**6. 焦點**

- 歸還與交接都用 `focus({ preventScroll: true })`，而且各只呼叫一次，沒有 rAF 或計時器重試。
- 交接旗標每次卸載都覆寫，每次掛載都消耗。
- 同一次 commit 內關閉加換位，不會連續搬動焦點兩次。
- 掃描測試要求所有觸發鈕的 `.focus(` 呼叫都帶 `preventScroll`。

**7. 測試有效性**

- **FE-T13(c4) 矩陣：**
  - 我從測試設計推演，「吞例外」這個變異確實會被抓到。c1 與 c2 的情境在被吞後 status 會是 success，但 seq 沒前進，就會破壞斷言。
  - 弱點見 NB-2。
- **FE-R2 離線測試：** 可信。
  - 用真的 `QueryClient`、`MutationObserver` 和 `onlineManager`，並有還原。
  - 另有一個對照組：拿掉 `networkMode` 的同一個離線送出，確實會 `pending` 加 `isPaused` 且 mutationFn 0 次。這證明測試前提成立。
- **`exitFlowStructure` 掃描：** 不是空轉。
  - 每個負面斷言前面都有正面錨點，例如 `toHaveLength(1)`、`indexOf > -1`，以及 `onSuccess` 區段的整段 regex 比對。
  - 掃描前先剝除註解。
  - 弱點見 NB-1。
- 變異驗證的聲稱，從測試設計來看是可信的。我自己沒有重跑變異。

**8. ui-delivery-checklist**

- 對比：內文用 `neutral-300` 到 `neutral-100`，底色是 `neutral-900` 或 `neutral-950`，均達標。
- 狀態完整性：disabled 同時有 `aria-disabled`、`opacity` 與 `cursor-not-allowed`。
- 響應式：
  - 對話框容器有 `max-h` 加 `dvh` 加 `overflow-y-auto`。
  - 但按鈕沒有 `whitespace-nowrap`，見 NB-6。
- 不捏造數據：測試用 SENTINEL 字串，畫面沒有數字。
- token 紀律：只用 Tailwind class，沒有 inline 色值。橫幅 class 與視覺規範 §4 逐字相同。

**9. 章程**

- 祕密：我用 `-i -G` 掃 api key、secret、password 等樣式，只命中被刪除的 `EmergencyExitControl.tsx`，沒有新增行。
- 範圍：後端只有 `wording.py` 與其測試。
- commit trailer：**無法驗證**。Bash 白名單不含 `git log`。請 coordinator 在合併前用 `git log --format=%B` 檢查 18 個 commit 的 Co-Authored-By 與 Claude-Session。

### 非阻擋項

行號說明：該分支沒有 checkout 在工作樹，白名單也沒有 `git show`，我只能從 diff 取得內容，無法精確取得行號。以下以「檔案：函式或測試名」定位，行號以分支 HEAD 為準。

- **NB-1　`playbook/__tests__/exitFlowStructure.test.ts`（medium）：**
  - 測試「no storage … in the exit flow」掃的 `exitFiles` 只含 `app/playbook/**` 與 `exitReceipt.ts`、`exitDialogState.ts`、`taipeiDay.ts`、`exitFocus.ts`。
  - 它**沒有包含 `lib/exitReceiptStore.ts` 與 `lib/exitReceiptContext.tsx`**。
  - ADR FE-C5 明文寫「grep 範圍包含 store 模組」。store 的另一個測試只擋 `globalThis|window|document|self.`，不擋 `localStorage`、`sessionStorage`、`indexedDB`、`document.cookie`。
  - 現行程式碼沒有寫入持久化媒介，我讀碼確認過，所以不阻擋。但 VETO-3 的守門有缺口，建議把這兩檔加進 `exitFiles`。
- **NB-2　`lib/__tests__/emergencyExitSettle.test.ts`，測試 `(c4) INV-1 matrix`（low）：**
  - 矩陣沒有對每個情境寫死預期 status。若 normal 或 c3 悄悄變成 error，會走 else 分支而通過。
  - 另外 `const step: "final" = "final"; result.isError && step === "final"` 是常數，等同重複斷言 `isError`。
  - 這些屬於補充一對 c4 的字面要求本身偏弱。真正的失敗面板條件由 `exitFlowStructure` 的 `showFailure` 逐字掃描，以及 c1 至 c3 的個別測試保護。
  - 建議在矩陣加 `expectedStatus` 欄位。
- **NB-3　`playbook/EmergencyExitDialog.tsx`，`useEffect(() => { headingRef.current?.focus() }, [state.step])`（low）：**
  - 步驟標題的 `focus()` 沒有 `preventScroll`。
  - 它在 `fixed inset-0` 的 portal 內，實際不會捲動頁面。而且測試把 `.focus(` 次數寫死為 3。
  - 但有人把 FE-C19 / FE-C20 的 preventScroll 精神延伸，這裡可以順手補。
- **NB-4　commit 排序（process，low）：**
  - `52e40da`、`59232cf` 兩個測試 commit 排在來源 commit 之前，單獨 checkout 會失敗，這會影響 `git bisect`。章程要求「一個 commit 一個語意」。
  - 交件已揭露，也不能 rebase。
  - 建議合併時採 squash merge，或在 PR 描述註記。
- **NB-5　`playbook/useEmergencyExitFlow.ts` 捲動 effect（low，qa-e2e 驗）：**
  - 若 SPA 換頁回來時，離開期間才到達的回執遇到 `/today` 仍是 pending，`statusBarRef` 為 null，`barBottom` 取 0。
  - 狀態列稍後掛載時，橫幅是否被蓋住，只靠 `scroll-mt-40` 的固定偏移。
  - 這是未在瀏覽器驗證的邊界。
- **NB-6　`playbook/ExitTriggerButton.tsx`、`EmergencyExitDialog.tsx`（low）：**
  - 按鈕沒有 `whitespace-nowrap`（ui-delivery-checklist 3.2）。
  - 依字數估算在 320px 下沒有折行風險，但沒有明確防線。
  - 按鈕也沒有明確的 `focus-visible` 樣式，沿用瀏覽器預設，這和既有元件一致。
- **NB-7　流程耦合（FE-C23）：** 這條分支長在 N-166 分支之上。PR 不得早於 N-166 合併。product 線上還有 `get_cap1_weight` 到 `get_cap1_reading` 的測試 import 修正，由 coordinator 處理。
- **NB-8　未完成的前幾輪遺留（交件已揭露，非本次阻擋）：**
  - 「我已閱讀，繼續」用 `aria-disabled`，qa 腳本須查 `aria-disabled`，不能查 `disabled`。
  - 視覺規範 §7 要求在 `work/stock-desk-快市排程-視覺規範.md` 補註，沒做。
  - 出清 POST 沒有用戶端逾時，補充一 S-4 列為另案。

### 風控裁示對照表（✓＝實作與測試皆滿足；✓*＝程式碼滿足，執行期行為待 qa-e2e）

| 裁示 | 項目 | 結果 |
|---|---|---|
| N164N165 版面與失敗字面 | 必改 1 橫幅撐過 `/today` 失敗 | ✓ 橫幅在 page 層 `role="status"` 內，不受 today 閘門影響 |
| 〃 | 2 對話框撐過 `/today` 失敗 | ✓ 以 `flow.isOpen` 為唯一掛載條件，在 `</main>` 之後 |
| 〃 | 3 不以舊資料渲染狀態列 | ✓ 維持 `today.isSuccess` 閘門 |
| 〃 | 4 mode_reason 隱藏條件 | ✓ `isSuccess` 加嚴格相等，同一次 render |
| 〃 | 5 移除即卸載 | ✓ 條件渲染，無 CSS 隱藏或 sr-only，測試有反向斷言 |
| 〃 | 6 橫幅內部順序與 `border-neutral-600` | ✓ |
| 〃 | 7 其他區塊不動 | ✓ 橫幅與帳冊之間無新元素 |
| 〃 | 8 狀態列 `bg-black` | ✓ 無 backdrop-blur，無 max-h、overflow、line-clamp，有掃描 |
| 〃 | 9 NB-6 專用面板 | ✓ 不動 `ErrorPanel`，不附後端原文或狀態碼 |
| 〃 | 10 單一來源加守門 | ✓ `exitWordingMirror.test.ts` |
| 〃 | 11 `onSettled` 重新取得 | ✓ 先 cancel 再 invalidate，都不 await |
| 〃 | 12 捲動 | ✓* 一次、`auto`、不搬焦點；快市 V-9 待 qa-e2e |
| Q8 | F-1 來源 | ✓ `isSuccess ? data.exit_confirm : null`，全 app 僅此一處 |
| 〃 | F-2 逐句比內容 | ✓ 被 Q11 R-3 取代，皆已實作 |
| 〃 | F-3 鏡射 1b | ✓ 逐字加守門 |
| 〃 | F-4 觸發鈕無新字面、不 disabled | ✓ |
| 〃 | F-5 後備容器限制 | ✓ |
| 〃 | F-6 V-16 判斷式 | ✓ |
| 〃 | F-7 焦點回歸 | ✓* |
| 〃 | F-8 無「模式未知」字面 | ✓ |
| 〃 | 降級句 1b | ✓ |
| Q11 | F-1（改）、F-2（改）、F-9、F-10 | ✓ |
| 〃 | R-1 至 R-6 | ✓ 見 §2 第 3 點 |
| 〃 | N1 | ✓ |
| r3 回審 | FE-1 至 FE-8 | ✓（FE-1 h1 列、FE-2 隱藏條件、FE-3 生命週期、FE-4 per-receipt 捲動、FE-6 N1 條件、FE-7 失敗面板、FE-8 無新字面皆有對應測試）；FE-5 焦點回歸為 ✓* |
| Q14 四項 Q15 與 PRD v5 | FE-1 Providers store | ✓ |
| 〃 | FE-2 卸載後仍寫入 | ✓ FE-T13(a) |
| 〃 | FE-3 per-receipt 捲動 | ✓ |
| 〃 | FE-4 橫幅僅 `/playbook` | ✓ 掃描鎖定 |
| 〃 | FE-5 heldAt | ✓ |
| 〃 | FE-6 送出前 R-4 | ✓ |
| 〃 | FE-7 cancel 再 invalidate | ✓ |
| 〃 | FE-8 焦點交接 | ✓* |
| ADR-0037 殘留與 r3.2 | FE-R1 `networkMode` | ✓ |
| 〃 | FE-R2 離線測試 | ✓ |
| 〃 | FE-R3 揭露地板 INV-1 | ✓ 路 1 |
| 〃 | FE-R4 捲動 effect 對齊 FE-C8 | ✓ |
| 〃 | FE-R5 不顯示上次送出狀態 | ✓ |
| N166 合併後字面 | NB-6 標籤與前兩句 | ✓ |
| CEO87 回審 | NB-6 第 3 句修訂版 | ✓ |

## 驗證

**我實際做的：**
- 讀完 41 檔 diff 中所有來源檔與測試檔，包含 `exitDialogState.test.ts`（573 行）、`emergencyExitSettle.test.ts`、`exitFlowStructure.test.ts` 等。
- 讀完上列所有風控裁示、補充一，以及 ADR-0037 的 FE-C 與 FE-T 條文。
- 對視覺規範 V-33 至 V-46 和橫幅 class 做了對照。
- 跑了上述 `git diff` 查詢。

**我沒做的：**
- 沒有重跑 `npm run typecheck`、`npm test`、`npm run build`、`pytest`，因為 Bash 白名單不允許。交件的 CI 結果是：
  - 前端 2852 tests passed。
  - 後端 8535 passed，覆蓋率 97.44%。
  - 這些數字我引述，未獨立驗證。
- 沒有看過畫面，沒有任何執行期行為的驗證。
- 沒有 Codex 第二意見。
- 沒有檢查 commit trailer。
- 沒讀 `.env`，沒碰 `data/*.db`。

## 下一步

1. **合併流程：**
   - 由 coordinator 驗 18 個 commit 的 trailer。
   - 維持 N-166 先合併、本分支後合併。
   - 建議 squash merge。
2. **建議處理 NB-1：** 把 `exitReceiptStore.ts` 與 `exitReceiptContext.tsx` 加進持久化掃描。這不阻擋合併，可由 frontend-engineer 後續補。
3. **Codex 補跑：** 環境可用時補跑 `codex` review。
4. **qa-e2e 必測情境**（headless Chromium；375×812、375×667、1280 寬；mock 控制 `/today` 與 `POST` 時機）：
   - **後備觸發鈕與換位：**
     - `/today` 在 success 與 pending、首次載入失敗、背景重新取得失敗之間切換。
     - 逐 frame 取樣：觸發鈕恰好 1 個，位移符合 V-34，整頁沒有 sticky 或 fixed（V-36）。
     - 在 h1 列觸發鈕上按 Tab 後 `/today` 恢復，焦點交接到新觸發鈕、不捲動。
   - **失敗加上 `/today` 也失敗：**
     - 在第 3 步，POST 回 500 與網路失敗各一輪，之後 `/today` 重新取得也失敗。
     - 對話框與失敗面板節點引用不變（V-46）。
     - 標籤行在 375×667 內可見，焦點仍在「確認送出全部出清」（V-41）。
     - 在最高的組合下量：1b 降級句加 N1 加失敗面板。
   - **R-2 至 R-6：**
     - R-3：降級句換成正式句，只清第 2 句、出現 N1。
     - R-3：變動句原本沒勾，不出現 N1。
     - R-5：第 3 步遇內容變動，退回第 2 步；遇降級句確認則不動。
     - R-5 退步後再進第 3 步，失敗面板重新出現。
     - 送出中發生變動，不換句。
     - R-4：mock 系統時鐘跨過台北午夜，包含第 2 步按「繼續」、第 3 步按「確認送出」，確認 POST 0 筆，且重勾後下一擊恰好 1 筆。
     - 跨日後新取得但內容相同：`heldAt` 前進、無 N1、不退步。
   - **橫幅生命週期：**
     - 開啟、取消、Esc、送出中、送出失敗、`/today` 失敗，橫幅都不消失。
     - 第二次受理取代第一次。
     - 整頁 R 次數在任一 frame 都 ≥ 1。
   - **SPA 換頁（AC-64）：**
     - 離開 `/playbook` 再回來，橫幅逐字相同，已顯示過的不再捲動。
     - 回來時 `/today` 失敗，R ≥ 1。
     - 離開期間才到達的回執，回來時捲一次（NB-5）。
     - 送出中按返回，回來時橫幅出現、捲一次。
     - 兩個頁面實例各送一次，POST 恰好 2 筆，橫幅是最後到達的那份。
   - **離線：** 瀏覽器離線時按「確認送出」，立即失敗、顯示 NB-6、不停在「送出中…」、取消與 Esc 沒被鎖住、恢復連線後不自動重送。
   - **捲動與快市：** 快市啟動加 frozen 加長橫幅，橫幅第一行不被狀態列蓋住（風控必改 12 / V-9）。
   - **焦點與捲動：** 關閉對話框後焦點回到觸發鈕，`scrollY` 前後差為 0。
   - **無障礙：**
     - 報讀軟體對 N1 的 `role="status"` 唸出。
     - 「我已閱讀，繼續」須查 `aria-disabled`。
   - **注入錯誤路徑（INV-1）：** sink 或 reducer 拋出例外時，對話框不關、顯示 NB-6。這無法在 production build 注入，需要用測試建置的手法。
   - **回歸：** 全頁在 320 至 1920 寬無橫向捲動，Firefox 與 WebKit 補跑。

分支：`origin/fix/stock-desk-exit-feedback`（HEAD `47f8ad9`）。主要檔案在 `/home/user/AICompany/apps/stock-desk/frontend/app/` 下：`lib/exitReceiptStore.ts`、`lib/exitDialogState.ts`、`lib/queries.ts`、`playbook/useEmergencyExitFlow.ts`、`playbook/EmergencyExitDialog.tsx`、`playbook/__tests__/exitFlowStructure.test.ts`。後端檔案是 `/home/user/AICompany/apps/stock-desk/backend/app/playbook/wording.py`。

BLOCKING_ISSUES=false

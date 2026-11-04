# N-171 群組 A 前端交件（738691b）

- 審查者：frontend-engineer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-171 群組 A 的前端做完了。分支 `feat/stock-desk-pending-exit-block-ui` 已 push，基底是 origin 後端分支的 `3fcaf4f`，worktree 已移除。tsc、vitest、`next build` 都綠。

- 新增獨立元件 `PendingExitBlock`，只透過 `usePlaybookToday(true)` 讀 `["playbook-today"]`。
- 它掛在 `page.tsx` 的 `today.isSuccess` 片段第一個位置。
- 依 r1 §1.3 的 class 骨架實作。R-1～R-6 的條件已落實並有測試。
- 沒有動 `types.ts`，`pending_exit_directives` 的註解和 "No view renders them yet." 都沒碰。
- 沒有 rebase、沒有 squash、沒有 merge product，沒有在後端分支上 commit。

偏離交辦之處：
1. 專案沒有 jsdom 或 testing-library，我沒有新增依賴。測試用 `renderToStaticMarkup` 加一個小型 HTML parser 還原成 DOM 樹，用來斷言結構與 textContent。computed style、幾何和視口條款在 vitest 驗不到，列在下面給 qa。
2. 區塊的渲染條件除了 non-null，還要「各小節 rows 合計 ≥ 1」。這是 r1 §1.1 與 F9 的規定，並非我自行加的。

## 條款對照
測試檔：`apps/stock-desk/frontend/app/playbook/__tests__/PendingExitBlock.test.ts`，共 68 條。

| 條款 | 狀態 | 依據 |
|---|---|---|
| VP-1 位置 | 部分 vitest | 區塊緊接 `role="status"` 之後、先於 attribution、summary、warnings；祖先沒有 role 或 aria-live；`page.tsx` 原始碼斷言它是片段第一個子元素。祖先不是 dialog、`RuleSetConfirmPanel`、帳冊等，未逐一驗，列給 qa。 |
| VP-2 間距 | 只驗 class | 以 class 對應 §1.3（`mt-6`、`mb-6`、`mt-2`、`mt-1`、`py-3`、`divide-y`、stale 的 `pt-4`）。px 數值列給 qa。 |
| VP-3 欄線 | qa | 無 `max-w`、padding 或 flex，欄線為頁面欄位。 |
| VP-4 無盒 | 驗 class | 無 `rounded`、`shadow`、`bg-*`、左右 border；允許的線只有 `ul` 的 `border-y`、`divide-y` 和 stale 的 `border-t-2`。 |
| VP-5 static | 驗 class | 無 `sticky`、`fixed`、`absolute`。 |
| VP-6 無圖示 | vitest | 無 svg、img、canvas、i；無裝飾字元（`：•·✓✔✅☑✗❌⚠–—`）；所有文字節點只可能是哨兵字串或 `{read_at}` 戳記，證明前端沒自撰字。 |
| VP-7 無彩色 | 驗 class | 無色相 class。 |
| VP-8、VP-9 字級與色階 | 驗 class | 只出現 `text-lg` 和 `text-sm`，文字色只有 `neutral-100` 和 `neutral-300`。行 `text-sm text-neutral-100`，附註、導言為 `neutral-300`。 |
| VP-10 順序與完整 | vitest | 標題、導言、各小節、末尾說明的 textContent 逐字全等。不重排：stale 在前、列倒序，輸出都跟著陣列。 |
| VP-11 附註同列 | vitest | 見 R-1 與同列順序。 |
| VP-12 不截斷 | vitest | 禁用 class 清單逐一斷言，包括 `truncate`、`line-clamp`、`overflow-`、`max-h-`、`nowrap`、`break-all`、`sticky`、`hidden`、`sr-only`、`opacity-`、`text-ellipsis`。無 title、aria-label、aria-describedby、details。原始碼也掃一次。scroll 和 Range 矩形列給 qa。 |
| VP-13、VP-14 | qa | 只能驗 `break-words` 的 class。 |
| VP-15 無斷點 | vitest | 無 `sm:`、`md:`、`lg:` 等前綴。三視窗 DOM 相同為單一版型，由此推得。 |
| VP-16 無 flex 或 grid | vitest | class 掃描。 |
| VP-17、R-3 | vitest | h3 若且唯若 label 非 null，非 null 時 `aria-labelledby` 指向 h3。stale 為 `mt-6 border-t-2 border-neutral-500 pt-4`，其餘 `mt-4`。無 dashed 或 dotted。stale 與 covering 的 ul、li、text、note 的 class 簽章完全相同，無 opacity、line-through、更淡色階或 style。 |
| VP-18 | qa | 與橫幅、狀態列、觸發鈕並存時的幾何與 `role="status"` 節點保留。 |
| VP-19 | vitest | `/today` pending 或 error 時不渲染區塊，連標題都沒有。h1 列和 V-33、V-36 的量測列給 qa。 |
| VP-20 | vitest | null、缺鍵、sections 為空時，整頁 markup 與缺鍵的 markup 逐位元組相同。 |
| VP-21 | qa | sticky 計數。 |
| VP-22 | vitest | 區塊內無 a、button、input、tabindex、onclick、role。 |
| VP-23 | vitest | 根是 `section[aria-labelledby=h2.id]`，id 唯一。標題層級 h2 → h3。無 role、aria-live、aria-atomic、aria-busy。 |
| VP-24 | vitest | 無 transition 或 animate class。 |
| C7 | vitest | 只 import `lib/format`、`lib/queries`、`lib/types`、`react`。不 import 回執 store、mutation 或 `useQueryClient`，用原始碼斷言。 |
| C19 | vitest | `{read_at}` 由前端代入。 |
| C22、T27 | vitest | 元件原始碼不含 `pending_exit_directives`。回應中塞入哨兵的 raw 清單，畫面上為 0。raw 清單改空或缺鍵時，區塊 markup 不變。block 為 null 時，有內容的 raw 清單也渲染 0。`page`、`DirectiveLedger`、`ModeStatusBar`、`ExitReceiptBanner` 原始碼也不含。 |
| T19 | vitest | 對應風控第四節第 1 點的獨立性斷言（元件 import 檢查，見 C7 列）。 |
| T22 | vitest | `{read_at}` 恰好代入一次，結果等於 `formatDateTime(data.as_of)`，換 `as_of` 結果跟著變，不殘留 `{read_at}`。`leadWithReadAt` 用函式 replacer，戳記不會被當成 `$` 樣式。 |
| 同列順序（A-15） | vitest | `<li>` 的子元素依序為 text、notes（依陣列）、`entry_before_exit_note`，中間無其他元素，也無游離文字節點。覆蓋 A-6、A-15、A-11、A-12 的順序。 |
| null 不留空位 | vitest | note 為 null 時 `<li>` 內 p 數量等於 1 加 `notes.length`。全區塊沒有 textContent 為空的 p、h3、li。 |
| R-2 | vitest | 附註 class 固定為 `mt-1 break-words text-sm text-neutral-300`，無縮排、邊線、底色或 opacity，不弱於導言。 |
| R-6 | vitest | 子孫無 `aria-live`、`role="status"`、`role="alert"`。 |
| SEAM-T8 | 綠 | `TodaySeamFixture.test.ts` 通過。 |
| NB-6（解讀點 3(d)） | vitest | 渲染真實的 `EXIT_FAILURE_WORDING` 到 `ExitFailurePanel`。第 2 段 `<p>` 的 textContent 全等於 `body[1]`，長度也相同，單一文字節點，3 個「。」，無摺疊或截斷 class。11-03 版專有的三個子句為 0。 |

我做了兩次變異驗證：把末尾說明改成 `truncate`，測試轉紅；把 label 條件反轉，測試轉紅。兩次都已還原。

## 列給 qa-automation 實機量測
環境為 headless Chromium，視窗 375×812、375×667、1280×900。顏色先用 canvas 轉成 sRGB 再比。

- VP-2：§2.1 全部 px 值，容差 ±1。包括 24 與 24、8、16 或 24、18（stale 的 `h3` 離小節上緣）、4、25、16。
- VP-3：區塊與 `<h1>`、`<main>` 內容欄的 left、width（343 或 992）。`scrollY=0` 時區塊在狀態列之下，且 `right ≤ innerWidth`。
- VP-4：所有子孫的 computed 值：背景 alpha=0、radius=0、左右 border=0、padding=0、無 box-shadow。
- VP-4 另含空白帶像素取樣為 (0,0,0)。
- VP-5：捲動 0、中段、底部時區塊的文件座標不變。
- VP-7：computed 色為無彩色，`max−min ≤ 3`。
- VP-8、VP-9：computed font-size、weight、color，與黑底的對比 ≥ 7:1，並與 `page_summary` 動態比較。
- VP-11：附註的 `top − 前一個 p.bottom = 4`，行距 25，`<li>` 高度公式，附註與 text 的 left 差 ≤ 1px。
- VP-12：computed overflow 為 visible、`scrollHeight ≤ clientHeight+1`、Range 矩形不超出區塊。
- VP-13、VP-14：F5 最長情境。
  - 375 寬導言行數 ≥ 10，1280 寬 ≤ 7。
  - `p` 高度為 20 的整數倍。
  - 20 字元 `symbol` 不溢出。
  - 8 個日期各自只有 1 個矩形。
  - 無水平捲軸。
  - 另量 320×640（建議項，不阻擋）。
- VP-16：computed `display` 皆為 block 或 list-item。
- VP-17：三類 computed 值相同，border-style 為 solid，stale 上線 2px 且色為 neutral-500。
- VP-18：F6 有無區塊的橫幅、狀態列、觸發鈕前後差。`role="status"` 是同一個 DOM 節點。掛載時 `scrollY` 不變。V-9、V-10、V-11、V-12、V-47 的量值。
- VP-19：非 success 時的 h1 列與 V-33、V-36。
- VP-21：sticky 恰好 1 個，fixed 為 0。
- VP-22：Tab 順序在有無區塊時相同，hover 前後顏色不變。
- VP-24：區塊掛載與卸載的瞬間，逐 frame 取樣 opacity 恆為 1。
- 整頁截圖：F2、F4、F5、F6 各兩個視窗，加 S-A～S-D 與 DOM 擷取。
- R-4：最長 fixture 在 375×812 的整頁截圖與區塊總高。
- R-3：stale 粗線實際效果（風控終核用）。

## CI 數字
在 `apps/stock-desk/frontend` 執行：
- `npm run typecheck`（tsc）：通過，零輸出。
- `npm test`：115 個檔案、3057 tests 全過。後端交件基準是 114 個檔案、2987 tests，新增 1 檔、70 tests（含本檔 68 條）。
- `npm run build`：成功。

## commit 清單
推送時是 `origin/feat/stock-desk-pending-exit-block` 的 `3fcaf4f` 加 2 個 commit，不含 merge，可直接 merge。
1. `edc8dea` feat：/playbook 新增全部出清產生、尚未結算的賣出指令區塊（N-171 群組 A 前端）
   - `apps/stock-desk/frontend/app/playbook/PendingExitBlock.tsx`
   - `apps/stock-desk/frontend/app/playbook/page.tsx`
2. `738691b` test：N-171 區塊結構、同列順序、T22／T27 與 NB-6 第 2 段渲染守門
   - `apps/stock-desk/frontend/app/playbook/__tests__/PendingExitBlock.test.ts`

兩個 commit 都帶了 `Co-Authored-By: Claude Opus 5.5` 和 `Claude-Session` trailer。

## 已知限制
- 區塊的 `isSuccess` 判斷是元件自己讀 query。背景重取失敗時（`isSuccess` 為 false），區塊與頁面其他內容一起消失，與 page 現有行為一致，也符合 VP-19 的 F12。
- 區塊永遠渲染在 `mt-6 mb-6`。相鄰兄弟的 margin 取大者，最終是 24px，這點需要實機確認。

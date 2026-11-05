# N-168 前端同列說明交件（d1ff816）

- 審查者：frontend-engineer
- 日期：2026-11-05
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
N-168 前端依 art 規範 r1 實作完成並已 push。分支 `feat/stock-desk-exit-pending-r-buys`，新增 commit `d1ff816`（上一個是 `2e7c157`，只新增 commit）。tsc、vitest、next build 全綠。R-3 sticky 尚待風控；若被否決，改走規範 §10 的退路 B（卡片）。

## 各部門回報（frontend-engineer）
### 改了哪些元件
- `apps/stock-desk/frontend/app/lib/noBreakDates.tsx`（新增）：`withNoBreakDates` 從 `PendingExitBlock` 搬到 `lib`，行為不變。`PendingExitBlock` 仍 re-export，既有 import 不受影響。
- `apps/stock-desk/frontend/app/lib/rowNotes.ts`（新增）：`collectRowNotes(source)` 依 §7.1 回傳字串陣列。
  - 現在只放 `entry_before_exit_note`，N-188、N-189(D1)、N-189(D2) 只留註解位置，不渲染任何新欄位。
  - 缺鍵、`null`、`""` 會被濾掉，不拆、不合併、不改字。
- `apps/stock-desk/frontend/app/playbook/DirectiveLedger.tsx`：依 §1.3，在 grid 之後、`limit_note` 之前加 `row-notes` 容器（`mt-2 space-y-1`）。每句一個 `<p className="break-words text-sm text-neutral-300">`，沒有 note 時整個容器不渲染。
- `apps/stock-desk/frontend/app/playbook/PositionSnapshotTable.tsx`：依 §3.2。
  - 捲動容器加 `@container`。
  - 每批次在批次列後多一個子列：`tr[snapshot-note-row]` > 單一 `td colSpan=6` > `div[snapshot-note-pin]`（`sticky left-3 w-[calc(100cqw-1.5rem)]`）。
  - pin 內是 label `p`（`font-semibold neutral-100`）加 `row-notes`（有 label 時 `mt-1`）。
  - 只有帶子列的批次列才把 `py-2` 改 `pb-1 pt-2`。
  - 欄寬、`min-w-[640px]`、批次列各 `td` 的 nowrap 沒動。
  - label 與 note 為空時不渲染子列；label 空字串也視為沒有。
- `apps/stock-desk/frontend/app/playbook/PendingExitBlock.tsx`：只改 import 與 re-export，渲染邏輯零 diff。
- 出清橫幅 `ExitReceiptBanner` 與結算面板 `SettlementPanel`：零 diff。

### C-1 答覆
W-B2LS 與 W-B2LSr 由後端合成同一字串（`service.entry_before_exit_note` 內 `note += REST_NOTE`，直接相接）。前端整串放同一個 `<p>`，不拆。`collectRowNotes` 測試已鎖住這點。

### C-2 答覆
我 grep 了 `app/` 非測試檔：`ExitReceiptBanner` 只渲染 message、mode_reason、attribution、warnings。沒有任何元件渲染 `directives` 或 `pending_directives` 的列。與規範 §2 一致，規範不需改版。

### E-26 第 3 點（N-171 區塊的 note 是否完整）
讀 `api/playbook.py` `_pending_exit_block`：row 的 `entry_before_exit_note` 取自 `_lines(row.directives, labeled_batches=...)[0].entry_before_exit_note`。
- 和 `DirectiveLine` 走同一個函式，所以與帳冊上同一批的 note 逐字一致。
- N-171 的列都是 EMERGENCY、`batch_no` 為整數，只會走 W-B2L，不會走到 S2 分支（W-B2LS／W-B2LSf）。這是預期行為。
- 結論：**完整，沒有發現缺漏，我沒有改後端。**
- 兩個風險供 dev-lead 知悉，不是缺陷：一是 `[0]` 在 `row.directives` 為空時會 IndexError；二是 `_lines` 以 `directive.shares` 傳入，只對 S2 有影響，N-171 不受影響。

## 驗證
- `npx tsc --noEmit`：無錯誤（含新測試，嚴格模式，無型別逃生口）。
- `npx vitest run`：116 個檔案、3086 個測試全過（含 SEAM-T8 的 4 個案例）。
- `npx next build`：成功。
- 產出的 CSS 確認含 `container-type:inline-size` 與 `width:calc(100cqw - 1.5rem)`，Tailwind 4 有產出對應 class。
- 新測試 `app/playbook/__tests__/RowNotes.test.ts` 涵蓋：
  - 有 note、無 note（`null`／`""`／缺鍵）；
  - 批次列 label 加 note、只有 label、只有 note、舊 body 無子列；
  - 約 310 字長句完整、無 `truncate`、`line-clamp`、`overflow`、`title`、`aria-` 等；
  - ISO 日期只被 nowrap span 包住，容器無 nowrap；
  - DOM 順序為 grid → `row-notes` → `limit_note`；
  - `collectRowNotes` 的順序與 C-1 合成字串。
- 為了搬動 `withNoBreakDates`，改了 `PendingExitBlock.test.ts` 的兩條原始碼掃描斷言：
  - import 白名單加上 `../lib/noBreakDates`；
  - nowrap 恰好一個的檢查改掃 `lib/noBreakDates.tsx`，並新增 `PendingExitBlock.tsx` 本身不得含 nowrap。
  - 守門意圖不變。
- 限制：專案沒有 jsdom，所以幾何、computed style 與視口條款都沒在 vitest 驗，留給 qa-e2e。

### ui-delivery-checklist 自檢
- 色值、字級、間距：對照 §1.3、§3.2 的 class 骨架逐項核過（`mt-2`、`space-y-1`、`mt-1`、`pb-1 pt-2`、`pb-3 pt-0`）。
- 空狀態：缺鍵、`null`、`""` 都不渲染容器或子列。
- 載入中與錯誤狀態：由既有頁面處理，本次沒動。
- 數字單位與時間戳：新增的只有後端字串，本次沒有新增數字。
- 手機 375 與桌面：只靠 class 結構保證，未實機量測，留給 qa-e2e。
- 面向使用者文字：全部是後端字串逐字渲染，前端沒有新增字面。

## 給 qa-e2e 的驗收重點
fixture 都是 mock `/today`，不要讀 `data/*.db`。
- **VP-168-1～5、16、17（帳冊）**：用 N1～N4、N6。選擇器是 `[data-testid="row-notes"]`，在 `ul.mt-3 > li` 內，位於 grid 與 `limit_note` 之間。N6 在目前實作只能餵出一句（只有 `entry_before_exit_note`），因為新欄位尚未存在。4 句堆疊要等 N-188／N-189 欄位進來，或由 qa 直接對 `row-notes` 做 DOM 注入式測試。
- **VP-168-7～12、13（批次列）**：N5 的 A、B、C 批。選擇器是 `snapshot-batch-row`、`snapshot-note-row`、`snapshot-note-pin`。表格捲動容器的選擇器是 `section:has(> h2) div.overflow-x-auto`，要在部位快照那一個。
- **VP-168-8（最關鍵）**：375 寬下 `scrollLeft` 為 0 與為最大值時，各量一次文字矩形是否在可視區內縮 11px 之內。
- **VP-168-14**：加 320×640。
- **VP-168-6、15**：橫幅與結算零差異，我沒有動這兩個檔案。
- **VP-21 口徑**：有批次 note 時，頁面會多出 `snapshot-note-pin` 這個 sticky 元素，只有 `left`，沒有 `top`、`right`、`bottom`。依 §9.2，量測時要扣掉它。
- C-3 由 qa-e2e 自行回覆。

## 已知限制與規範疑義
1. **`sticky` 加 `100cqw` 在表格內的行為沒有實機驗證。** 這是最大的不確定點，需要 VP-168-8 實測。
   - 風險一：`td` 在 `table-layout: auto` 下，內容的 `width: calc(100cqw - 1.5rem)` 會參與欄寬計算，可能影響整張表的寬度。規範預期 pin 寬度 ≤ 可視寬，不會撐寬 `td`，但 375 寬時表格是 640px，要靠 VP-168-9 確認六欄寬度不變。
   - 風險二：`@container` 把捲動容器設為 `container-type: inline-size`。這是 size containment，作用在 `overflow-x-auto` 的 div，其寬度本來就由外部決定，我判斷影響不大，但要實測。
   - 風險三：`position: sticky` 的祖先若有 `overflow` 非 visible，sticky 的參照是最近的捲動祖先，也就是 `overflow-x-auto` 的 div。這正是規範要的行為。但 `td` 本身不是捲動容器，sticky 子元素在 `td` 內只能在 `td` 的範圍內位移，而 `td` colSpan=6 寬度等於整張表，所以應該沒問題。
   - 如果 qa-e2e 判定「容不下」，依規範送風控回審，不得截斷。
2. **N6 預留壓力 fixture 現階段只能 1 句**（見上）。規範 §9.1 的 VP-168-16 要 4 句，需等新欄位或由 qa 注入。
3. **規範 §6 建議 `withNoBreakDates` 搬到 `app/lib/`，我照做了。** 副作用是 `PendingExitBlock.test.ts` 兩條原始碼掃描斷言需更新（見上）。
4. 風控 R-1、R-2、R-3 尚待裁示，我先照 r1 實作，核可前視為暫定。
5. 沒有使用 `data/*.db`，沒有讀 `.env`。

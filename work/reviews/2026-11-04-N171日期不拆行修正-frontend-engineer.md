# N-171 區塊日期 nowrap 修正交件（346d5cb）

- 審查者：frontend-engineer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
VP-14 的前端修法已完成並 push 到 `origin/feat/stock-desk-pending-exit-block`（5e7c31c → 346d5cb）。tsc、vitest、next build 全過。實機的日期矩形數我沒有量，要請 qa-automation 重驗。

## 各部門回報（變更說明）
- 檔案 `apps/stock-desk/frontend/app/playbook/PendingExitBlock.tsx`
  - 新增 `withNoBreakDates(value)`，用 `(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)` 切分字串。
  - 每個命中包成 `<span className="whitespace-nowrap">`，span 上只有這一個 class，沒有其他屬性。
  - 只切 text node，不加字、不改順序、不改連字號（沒用 U+2011）。
  - 沒有日期的字串原樣回傳同一個 string。
  - 非日期的片段是相鄰的獨立 text node，沒有補空白或空字串。
  - `<p>` 的 class 不變，維持 normal。
- 套用範圍
  - 你指定的 `r.text`、`notes`。
  - r2 §1.3 第 ④ 點要求同樣處理，所以我也套用到 `entry_before_exit_note`、區塊 `lead`、小節 `lead`、`closing_notes`。
  - `title` 與 `label` 不處理，因為 r2 沒列。
  - 區塊 `lead` 是先代入 `{read_at}` 再包裝。
- 與你指令不同的一處：regex 我加了前後不得緊鄰數字的條件（lookaround）。這樣「12345-67-891」「2026-11-111」這類較長的數字串不會被誤包。要退回純 `\d{4}-\d{2}-\d{2}` 只需改一行。
- 誤包檢查
  - 股數與批號是純整數，不符合格式。
  - `{read_at}` 戳記經 `formatDateTime` 輸出，實測為 `2026/10/28 08:00（台北時間）`，用斜線，不符合格式。
  - 測試已鎖定這兩點。

## 驗證
- 測試（`app/playbook/__tests__/PendingExitBlock.test.ts`）
  - 守門測試調整：
    - 通用禁用 class 清單與原始碼 token 清單移除 nowrap。
    - 改由 `nowrapViolations` 把關：帶 nowrap 的元素必須是 `p` 直屬的 `span`，class 恰為 `whitespace-nowrap`，無其他屬性，且內容只有一個完整 ISO 日期，否則算違規。
    - 原始碼中 `nowrap` 必須恰好出現 1 次。
    - 另有負向測試證明守門會變紅：容器帶 nowrap、非日期內容的 span、span 多帶 title、多 class、父層不是 p、`section` 帶 `text-nowrap`。
  - 新增日期測試：
    - 日期全被包住，span 內只有日期字元、單一 text child。
    - 每個 `<p>` 的 `textContent` 與後端字串逐字相同。
    - 沒有多出空白或空 text node；整串就是日期時只有一個 child。
    - `<p>` 與容器 class 不變。
    - 非日期數字串不被包，無日期字串不受影響（回傳同一個 string）。
    - lead、closing 有包，title 沒包，戳記不包。
    - 全文與原始碼無 U+2011。
- CI 數字（本機）
  - tsc `--noEmit`：無輸出，通過。
  - vitest：115 檔全過，3067 測試全過（原 3066，我新增 11 個 case，同時調整了既有的 2 處守門測試）。
  - `next build`：Compiled successfully。
- VP-16 的 display 規則在這個套件裡沒有對應測試（靜態 markup 無法量 computed display），所以沒有需要調整的現有測試。span 一律是 `p` 的直接子元素，這點由 `nowrapViolations` 保證。

## commit 清單
- `346d5cb` fix: 待執行出清區塊的 ISO 日期以 nowrap span 包住，避免在連字號拆行（VP-14）。只動上述 2 個檔案。
- worktree 與暫時分支已移除。沒有讀 `.env`，沒有碰 `data/*.db`，沒有 rebase、force push 或 merge product。

## 下一步（給 qa-automation 重驗 VP-14 的注意事項）
1. 重驗情境：`f5`、`f5u`，視窗 375、320、1280。
   - 日期 span 的 Range 矩形數要等於 1。
   - 日期 span 的 `white-space` 是 nowrap，`<p>` 的是 normal。
   - span 的 display 是 inline，且必須是 `p` 的直接子元素。
2. 320 寬要確認 `scrollWidth <= innerWidth`，日期 token 約 85px，不應撐出橫向捲軸。
3. 不退步的項目：VP-6、VP-10、VP-12，以及 V 系列 A、B、D、E、F、G 組有／無區塊對照。
4. VP-10 的 `textContent`／`innerText` 與 API 值要逐字相同。
5. 有包的範圍是 `text`、`notes`、`entry_before_exit_note`、區塊 `lead`、小節 `lead`、`closing_notes`；`title`、`label` 沒有包。
6. 風控知悉：這次沒有新增或改動任何面向使用者的字面。
7. 本次沒有跑 Chromium 實機，斷行行為只能靠上述實機重驗確認。

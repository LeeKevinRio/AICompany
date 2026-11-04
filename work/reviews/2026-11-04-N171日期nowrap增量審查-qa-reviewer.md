# N-171 日期 nowrap 增量審查（346d5cb，PASS）

- 審查者：qa-reviewer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
PASS，BLOCKING_ISSUES=false。增量 `5e7c31c..346d5cb` 只有 2 個前端檔案（`PendingExitBlock.tsx`、`PendingExitBlock.test.ts`）。實作符合 r2 §1.3 末條的五項約束，套用範圍正確。守門測試沒有放寬到讓其他截斷類 class 漏網。
我沒跑 vitest 和 tsc。Bash 只准 `git diff` 和 `codex --version`，所以結論來自靜態閱讀。

## 各部門回報（逐項審查）

### 重點 1：`withNoBreakDates` 對照 r2 §1.3 末條五項約束
- **只切 text node：符合。** 函式只做 `slice` 和 `matchAll`，輸出是 string 與 span 交錯的 Fragment。
- **不改字：符合。** 切出的片段首尾相接，不補、不丟、不重排。沒命中時原樣回傳字串，連 Fragment 都不包。測試有 `textContent` 逐字相等、無多餘空白、無空字串子節點三項斷言。
- **不用 U+2011：符合。** 原始碼與輸出標記都有負向斷言。
- **span 只有一個 class：符合。** 只有 `className="whitespace-nowrap"`，沒有 `title`、`aria-*`、顏色或粗細。測試斷言 `attrs` 恰等於 `{class}`。
- **`<p>` 維持 normal：符合。** 所有 `<p>` 與容器的 class 都沒動，測試也斷言 `<p>`、區塊根、`<li>` 沒有 nowrap。
- **lookaround `(?<!\d)…(?!\d)`：合理，但嚴格來說比 r2 文字多一層限制。**
  - r2 寫的是 `\d{4}-\d{2}-\d{2}`，沒有邊界。
  - 沒有邊界時，`12345-67-891` 會被誤切出 `2345-67-89`，把券商單號或股數類字串錯當日期，與 r2 的意圖（ISO 日期）不符。
  - 加邊界只會少包、不會多包，也不會改字，所以安全。
  - **[可維護性][low]** 請 frontend-engineer 或 art 把「兩側不得緊鄰數字」補進 r3 或 §1.3 的註記，讓 qa-e2e 和 qa-automation 的正則與實作一致。
  - **[Edge case][low]** `2026-11-111` 這類字串不包，這是刻意的，測試有覆蓋。
- **[Edge case][low] 環境相容性。** lookbehind 需要 Safari 16.4 以上。這是內部工具，可接受。
- **[可維護性][low]** `m.index` 在舊版 TS 型別是 `number | undefined`。我沒跑 tsc，請 CI 的 typecheck 把關。若 CI 報錯，改用 `m.index!` 即可。

### 重點 2：套用範圍
- 對照 r2 §1.3 末條 ④ 與 VP-14 的清單，範圍正確。
- 有套用：`r.text`、`notes[]`、`entry_before_exit_note`、區塊 `lead`、小節 `s.lead`、`closing_notes[]`。
- 沒套用：`title`（h2）與 `label`（h3）。r2 清單不含這兩者，測試也斷言 h2 沒有 span、文字原樣。
- 套用範圍和 r2 ④ 一致，沒有擴大也沒有遺漏。

### 重點 3：`{read_at}` 順序
- 寫法是 `withNoBreakDates(leadWithReadAt(...))`，先代入、後包裝。
- `leadWithReadAt` 仍用 function replacer 代入，每次恰好一次，T22 不受影響。
- 若 `formatDateTime` 輸出剛好含 ISO 日期，也只是被包 span，字面不變。
- 測試斷言 stamp 不含 ISO 日期，且 `lead` 的 `textContent` 等於 `LEAD 2026-11-11 ${stamp}`。

### 重點 4：守門測試嚴謹度
- **`nowrapViolations`：夠嚴。**
  - 只要 class 含 `nowrap`，就必須同時滿足：tag 是 span、class 恰為 `whitespace-nowrap`、attrs 只有一個、單一字串子節點且完整符合 ISO 日期、父節點是 `<p>`。其中任一不符就算違規。
  - 這比 r2 的要求還嚴。
  - 負向測試涵蓋 7 種情境：`<p>` 上的 nowrap、非日期內容、多餘 `title`、多 class、父節點是 `div`、`text-nowrap` 在容器上、正常日期 span 為 0 違規。
- **原始碼 `nowrap` 恰好 1 次：** 去除註解後 `match(/nowrap/g)` 必須恰為 1 次，並要求包含 `className="whitespace-nowrap"`。任何新增的 nowrap（含放進樣板字串的）都會轉紅。
- **未放寬其他截斷類：** 從禁用清單移除的只有 `"nowrap"` 這一個 token。`truncate`、`line-clamp`、`overflow-`、`max-h-`、`break-all`、`whitespace-pre`、`keep-all`、`text-ellipsis`、`hidden` 等全數保留，原始碼清單同樣只少了 `nowrap`。
- **[可維護性][low]** 原有的 class 迴圈清單已不含 nowrap，nowrap 的把關改由 `nowrapViolations` 在 `datedBlock` 與 lead 區塊上執行，沒有套用到所有預設 fixture 的渲染結果。
  - 因為原始碼只有 1 個 nowrap 且位置固定，實質上沒有漏洞。
  - 若想更保險，可在原禁用 class 區段再補一次 `expect(nowrapViolations(node)).toEqual([])`。不擋合併。

### 重點 5：字面、C22、T27、aria/title
- 字面零變動：沒有新增任何面向使用者的字串，只有切分。
- C22、T27：獨立性測試的 import 白名單仍是 `../lib/format`、`../lib/queries`、`../lib/types`、`react`。新增的 `Fragment`、`ReactNode` 來自既有的 `react` 那一行，白名單照過。沒有碰 `pending_exit_directives`。
- 新增程式碼沒有 `aria-*` 或 `title`，原始碼的禁字測試仍保留。
- 檔案註解也更新了，說明 nowrap 只允許用在日期 span，容器一律不行。

### 重點 6：唯讀權限判準常數
## 唯讀權限判準常數
未觸及。兩道機械檢查的對象是 `scripts/validate_agents.py` 與 `READONLY_AGENTS` / `READONLY_ALLOWED_BASH`。本增量的完整 diff 只含 2 個前端檔案，不含這個腳本，也沒有出現這兩個常數名。三問回答如下：
- 改了什麼：沒有改。
- 為何改：不適用。
- 有無對應 ADR：不需要。
- 常數在別處的 shadow 定義：本次 diff 中不存在。
- 常數的值有無被改動：沒有。

## 驗證
- **越界記錄：** 沒有越界。我只用了 `git diff`（兩次）和 `codex --version`。
- **Codex 狀態：** `codex --version` 回傳 `command not found`（exit 127）。**單家審查，Codex 待環境可用時補跑。**
- **其他讀取：** 我讀了 r2 視覺規範與 diff 的暫存輸出檔。我沒有讀 `.env`，也沒有碰 `data/*.db`。
- **未驗證項目：** 實際斷行行為（VP-14、VP-16 的 375、320、1280 寬度與 computed `white-space`）需要排版引擎，不在我的審查範圍，也不在 vitest 範圍內。

## 下一步
1. 交 qa-e2e 重驗 VP-14（`f5`、`f5u`；375、320、1280 寬），並補跑 VP-6、VP-10、VP-12、VP-16 與 V 系列有／無區塊對照。
2. 請 CI 的 typecheck 確認 `m.index` 型別。
3. 低優先：把 lookaround 邊界補進 r2 或 r3 文件，讓規範與實作一致。
4. Codex 可用後補跑第二意見。

## Verdict
PASS
BLOCKING_ISSUES=false

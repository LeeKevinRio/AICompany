# 出清橫幅遮擋補償增量審查（b3d6284..db2ee33，PASS）

- 審查者：qa-reviewer
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
增量 b3d6284..db2ee33 沒有 critical 或 high 問題，判 PASS，不阻擋。
- 補償邏輯逐條符合 r3.5a 與 PRD FR-3：觸發 `top < barBottom+12`，目標 `barBottom+16`，同步完成點用 2 個 frame 且上限 60，手動捲動用輸入事件，額度每份回執 1 次，狀態列卸載不補，`behavior:"auto"`，不搬焦點，程式內沒有安全閥。
- 有幾個 medium 和 low 的觀察，列在下面，建議之後處理，不擋本次放行。
- 單家審查，Codex 待環境可用時補跑：本環境 `codex --version` 回 exit 127（command not found）。
- 我只讀了 diff，沒有跑任何測試。frontend-engineer 自報的 tsc exit 0、vitest 2882 passed、next build 成功，我沒有獨立重現。他也自承遠端 CI 沒查。

## 各部門回報（各檔問題）

### apps/stock-desk/frontend/app/lib/receiptCompensation.ts
- 符合性：
  - `receiptCompensationDelta` 的常數 12、16、60 都對。
  - 條件順序是「額度用盡 → 手動捲動 → 無狀態列 → 未達觸發」，都回 0。
  - delta 為負值（往上捲），在 12 到 16 之間不動，遲滯區間正確。
  - 檔案內沒有任何安全閥，也沒有 scrollY。
- 同步完成點：`stabilize` 第一個 frame 記錄高度，第二個 frame 相同就判定，等於「連續 2 個 frame 相同」。`waited >= 60` 時仍判一次。
- 額度：只在 `delta !== 0` 時設 `quotaUsed`。`arm(newSeq)` 重置額度與 `userScrolled`，所以第二份回執獨立。`arm` 同 seq 是冪等的。
- 狀態列卸載：`barBottom === null` 回 0，符合 V-47(f3)。
- [可維護性][low] `dispose()` 把 `phase` 設成 `"done"`，而 `arm` 同 seq 又是冪等。若 dev StrictMode 在 mount 時雙跑 effect，掛載當下就 arm 的回執，補償會永久失效。實際上回執通常在掛載之後才出現，影響極小。建議 `arm` 同 seq 但 `phase === "done"` 且 `quotaUsed` 為 false 時不要直接 return，或讓 dispose 不覆寫 `phase`。

### apps/stock-desk/frontend/app/playbook/useReceiptCompensation.ts
- 狀態只放在 `useRef`，沒有進 store，沒有持久化，也沒有開 query observer。這符合 FE-C2 與 INV-1。
- 手動捲動：只聽 `wheel`、`touchmove`、`keydown`（過 `isScrollKey`），listener 為 passive。沒有 scroll 事件，也沒有 scrollY。
- `window.scrollBy({behavior:"auto"})`，沒有 focus。
- [Edge case][medium] `fetching = fetchStatus === "fetching"`，所以 `"paused"`（離線）會被當成「refetch 結束」。這時若 `sawFetching` 為 true，會立刻進入 stabilize 並判定，之後 `phase` 變 done。連線恢復後真正的 refetch 結束時不會再補。離線時狀態列不會長高，所以實害小，但語意不嚴謹。建議只把 `"idle"` 視為結束，`"paused"` 維持不變。
- [Edge case][low] effect 順序：fetching 的 effect 在 flow 的 scroll effect 之前宣告，所以 `isFetchingNow()` 在 arm 時讀到的是同一個 commit 的最新值。這點正確。
- 同一個 commit 裡 refetch 剛好結束並同時 arm 時，會等下一次 refetch。這就是交件第 4 點的競態。

### apps/stock-desk/frontend/app/playbook/useEmergencyExitFlow.ts
- `compensation.arm(seq, isFetchingNow())` 放在 `receiptStore.scrollHandled(seq)` 之後，也在 `shouldScrollForReceipt` 提早 return 之後。已顯示過的回執回來不會 arm，符合 V-47(e)。
- 這個 diff 只在 scroll effect 尾端加了一行，`accept()` 與其他既有流程的順序沒動。
- 新增的註解與參數名裡沒有 `today` 字樣。我只能從 diff 判斷，沒有 grep 整個檔案（見「權限越界」一節）。
- 參數型別 `"fetching" | "paused" | "idle" = "idle"` 的預設值合理。

### apps/stock-desk/frontend/app/playbook/page.tsx
- 只改了 `useEmergencyExitFlow(today.fetchStatus)`。分層沒有被破壞，把值傳進去而不是在 hook 內開 query，理由成立。

### 測試（receiptCompensation.test.ts、exitFlowStructure.test.ts）
- 真值表有 2⁴ 窮舉（obstructed × userScrolled × quotaUsed × hasBar），斷言是「只有全條件滿足才非 0」，有效。
- controller 案例涵蓋 (a)(b)(c)(d)、第二份回執、冪等、狀態列卸載、2 frame 穩定、60 frame 上限、dispose。
- [可維護性][medium] 結構測試對「套用安全閥」的攔截太窄，只擋 `OVER_HALF|innerHeight * 0.5|0.5 *`。像 `innerHeight / 2`、`window.innerHeight >` 或換個常數名稱的安全閥都抓不到。建議改成擋 lib 與 hook 中任何 `innerHeight` / `visualViewport` / `clientHeight` 引用。
- [可維護性][low] 偵測手動捲動只擋 `addEventListener("scroll"`，擋不到 `onscroll=` 或 `useEffect` 比對。其餘（`scrollY`、`pageYOffset`、`.focus(`、`scrollIntoView`、`behavior: "smooth"`）都有擋。
- 測試漏了 paused 與「refetch 在 arm 前就結束」的行為斷言。這兩點目前只靠交件說明，沒有鎖住。
- 既有的 `useEmergencyExitFlow\(today\.fetchStatus\)` 計數改動是必要且合理的。

## 交件六個解讀點
1. 首捲沒有重寫，宣稱數學上等於 max()：**有條件接受。** 我無法在這個環境讀到 `exitReceipt.ts`，因為工作樹在 main，沒有該檔。這是依 b3d6284 已 PASS 的前提接受。若 `receiptScrollCorrection` 只在遮擋時才往上補，結果就等於 max()。建議 qa-automation 實機確認。
2. 狀態列卸載時完全不補：接受，符合 V-47(f3)。
3. 不論首捲有沒有發生都 arm：接受，與 FR-3 的情境一致。
4. arm 之前 refetch 已結束的競態：**可接受，但要記為已知限制。** refetch 結束後狀態列已是新高度，首捲用的是即時高度，所以多數情況不需要補償。損失只發生在極短視窗內。
5. Space 鍵計入：接受。
6. 重新掛載競態：接受，該回執已標記為已捲。

## 回歸檢查
- 增量只動 6 個檔案，其中 JSX、class、色值、字面全部零變動（diff 內沒有任何 JSX 或字面）。
- `ui-delivery-checklist` 對比、狀態、響應式、假數據等項目不適用。遮擋是否真的消失，只能靠實機驗，必須由 qa-automation 與 qa-e2e 重跑，這點我不能代替。
- `code-review-checklist` 自檢：沒有祕密，沒有 console，沒有 any，錯誤路徑（卸載、null）都有處理。

## 唯讀權限判準常數
未觸及。
- `git diff b3d6284 db2ee33 --name-only -- scripts .claude` 無輸出，沒有動 `scripts/validate_agents.py`，也沒有動 `.claude/`。
- `git diff b3d6284 db2ee33 -G "READONLY_AGENTS|READONLY_ALLOWED_BASH" --name-only` 無輸出，這兩個常數沒有任何新增、刪除或值變動，也沒有 shadow 定義。
- 異動 agent 名單為空，沒有改任何東西，因此不需要對應 ADR。

## 權限越界揭露
- 沒有越界。我只跑了 `git diff` 與 `codex --version`，沒有 pipe，沒有 `cd`，沒有讀 `.env` 或 `data/*.db`。
- 由於工作樹在 main，我讀不到分支上的完整檔案，flow 檔是否有 `today` 字樣只能從 diff 判斷（diff 內沒有）。

## 下一步
1. 交 qa-automation 重跑實機，用 db2ee33，需能控制 `/today` refetch 回應時機，並照 AC-68 重驗清單，包含 C 組三種寬度、tall1、tall2 與 87→127px。
2. 實機通過後再交 qa-e2e 復驗。
3. 建議 frontend-engineer 在後續小修處理上述 medium：`paused` 不算結束，以及強化安全閥的結構測試。

## Verdict
PASS
BLOCKING_ISSUES=false

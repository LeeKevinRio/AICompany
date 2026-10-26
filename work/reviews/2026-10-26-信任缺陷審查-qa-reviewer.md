# 信任缺陷分支審查

- 審查者：qa-reviewer
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

BLOCKING_ISSUES=false

## Summary
兩個前端 commit（缺陷 1、缺陷 3）的根因與修法站得住，新測試有鑑別力，沒有刪斷言，也沒有新增使用者可見字面。缺陷 2 判為設計使然的依據三處都核對屬實。有一個需要風控點頭的中等問題（載入中骨架把 E-1、E-4 一併隱藏），不阻擋，但合併前要有答覆。

我沒有跑測試，也沒有重跑 CI。「修正前會紅」是靜態推演，CI 數字（2316 passed）取自交件原文，我沒有獨立驗證。

## 各檔問題

### apps/stock-desk/frontend/app/position/[symbol]/EntryObservationPanel.tsx:119-126
- [可維護性／風控邊界][medium] `pending` 分支只回傳標題加骨架，E-1 的「以上六條門檻」說明句和 E-4「資料截至」句在載入中整段消失。
  - 同檔 L31-36 與 L155-156 的註解寫明「E-4 不得被任何條件包住（風控 L-10b）」「always rendered」，L139 還有 REQ-1「六列永遠列出」。這分支是新增的條件包覆，與註解所記的核可裁示字面上衝突。
  - 它不產生任何建議性內容，我判斷是低風險。但裁示是風控的，我不能代為放行。
  - 建議：合併前請 risk-compliance-officer 書面確認載入中例外成立。若不成立，改成載入中仍渲染 E-1、E-4，只遮計數、圓點和逐列判定。
  - 若風控放行，請同步改 L31-36、L155-156 的註解，否則註解會與程式矛盾。dev-lead 已在交件「已知限制」自行揭露此事。
- [Edge case][low] React Query v5 在離線時，`fetchStatus` 為 paused，`status` 仍是 pending，骨架會一直不消失；修正前則會顯示「無法判定」。
  - 此頁沒有 `isPaused` 處理，屬罕見情境，可記為已知限制，不必擋。

### apps/stock-desk/frontend/app/lib/entryObservation.ts:159-181、position/[symbol]/page.tsx:151
- 無問題。`isEntryObservationPending` 只看 `isPending`，即 v5 的「還沒有 data」。
  - 查詢成功或重試用完後的 error 都不算 pending，所以真的沒資料時照舊顯示「無法判定」。
  - 背景 refetch 已有 data，不會閃。
  - bars／signals／advice 三個 hook 都是 `enabled: true && symbol.length>0`，不會有「disabled 所以永遠 pending」的誤傷。
  - `observationBand` 只由 bars 的 MA20 算出（entryObservation.ts:144-148），不受 pending 影響。

### apps/stock-desk/frontend/app/position/[symbol]/PriceChart.tsx:136、page.tsx:387
- 無問題。`movingAveragesPending={signals.isPending}`，只在 signals 第一次載入中才抑制「均線資料不足」。
  - signals 成功但無 MA、insufficient、error 三種已結束狀態，都仍顯示該句。
  - PriceChart 在 page.tsx:36 是直接 import，不是 `next/dynamic`，所以整頁測試裡 MA 備註有真的被渲染，不是空轉。
- [Edge case][low] signals 為 error 時顯示「均線資料不足」，措辭偏弱。這是既有行為，且旁邊有 ErrorPanel，不在這次範圍。

### apps/stock-desk/frontend/app/components/SummaryCards.tsx:12-24、77-81
- 無問題。`empty = no_data && positions.length === 0`。
  - 後端 `_totals_status`（summary.py:259-264）在 `ok==0` 時一律回 `no_data`，所以空持倉必為 `no_data`，不會漏接。
  - 「有持倉但全部無法估值」仍走核可橫幅 `SUMMARY_BANNER_NO_DATA`。四張卡改「—」是合理的：原本同一畫面寫「總計無法計算」卻印 NT$0，自相矛盾，而且改動僅限 `no_data`。
  - `status === "complete"` 且加總為 0 時，因為後端 `ok>0` 才會是 complete，仍印 NT$0，守門測試有鎖。
  - `pnlColorClass(null)` 回中性灰，與原先 "0" 的結果一致，不會有顏色退化。
- [可維護性][low] 空持倉時「尚無持倉」在總覽出現兩次（橫幅加持倉明細區的 EmptyPositionsState），交件已揭露。可接受，不阻擋。
- [可維護性][low] 橫幅用 `<p role="status">` 並重用 `EMPTY_TITLE`，沒有「新增持倉」連結，連結只在下方 EmptyPositionsState。與核可字面無衝突，不需處理。

### 測試檔
- `entryObservationPending.test.ts`（新，12 個）：
  - 我逐個推演修正前的結果：8 紅（`isEntryObservationPending` 為 undefined 使 2 個 helper 測試與面板測試拋錯、PriceChart 忽略新 prop、接線字串斷言、整頁冷載入出現 MA 備註與部分計數）、4 綠。
  - 4 綠是設計上的守門測試：已結束但無資料、PriceChart 已結束、整頁 reload、整頁 insufficient。與交件說的「8 紅 4 綠」吻合。
  - 其中「接線字串斷言」是對原始碼做字串比對，較脆弱，但另有整頁測試補強，可接受。
- `summaryCardsEmptyBook.test.ts`（新，4 個）：覆蓋空持倉、有持倉但無法估值、complete 且 0 等情境。
  - 第 1 個斷言用整段 HTML 字串比對，樣式一改就會紅，但這是刻意釘死中性樣式與「不得出現 amber」，可接受。
- `priceUnitBadge.test.ts`（改）：只換情境，把「advice、signals 都沒到」改成「advice 已結束但無卡、signals 已到」，原斷言 `["technical","key-levels","entry"]` 原樣保留，另外新增「advice 未到時不出 entry chip」的斷言。沒有刪掉任何斷言。
- `summaryBanner.test.ts`（改）：只在 `no_data` 時餵入一筆無法估值的持倉，其餘斷言與核可字面檢查完全沒動。

## 逐項核對（對應你的 5 點）
1. 缺陷 1：根因成立（signals 因冷啟動需另抓大盤指數而晚到，前端把「未到」當「不足」）。pending 只在真正載入中生效，已結束且無資料時照實顯示「無法判定」與「均線資料不足」，有對應測試。新測試修正前會紅（見上）。
2. 缺陷 3：修法正確。超出範圍的那處（有持倉但全不可估值時卡片也印「—」）合理。complete 且加總真為 0 時仍印 NT$0，有守門測試。
3. 缺陷 2 的依據，三處我都親自讀過：
   - `engine.py:363-368`：`action == "add" and violated` 時降為 `hold` 並寫入 `blocked_notices`，與交件所述的「第 1 條上限擋下」一致。
   - `limits.py:1655-1672`：docstring 寫明 `add` 與 `reduce/stop_loss/take_profit` 才有範圍，「anything else -- None」。
   - `test_advice_limits.py:1858-1861`：`test_hold_and_unknown_actions_get_no_range` 釘住 hold 與 insufficient_data 皆為 None。
   - 判定為設計使然成立。使用者誤解是字面與版位問題，要改屬建議類文案，需送 risk-compliance-officer，建議 CEO 另開單。
4. 使用者可見字面：未新增。重用 `EMPTY_TITLE`、`ENTRY_PANEL_TITLE`、既有「—」。`aria-busy` 是屬性不是文字。MA 備註字面未動。
5. 兩個既有測試：只改情境，未刪斷言（見上）。

## 第二意見（Codex）
無法執行。`codex --version` 回傳 exit 127（command not found），此環境未安裝 Codex CLI。依 CEO #58 在此註明，本次僅有本地審查，無跨廠商意見。

## 唯讀權限判準常數
未觸及。
- 第一道（`--name-only` 比對 `scripts/validate_agents.py`）：我的 Bash 權限不含 grep 管線，改以 `--stat` 人工核對。變更的 9 個檔案全在 `apps/stock-desk/frontend/` 下，不含 `scripts/validate_agents.py`。
- 第二道（比對 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH`）：我人工通讀了全部非測試檔 diff、兩個既有測試的 diff 與 `summaryCardsEmptyBook.test.ts` 的 diff，並讀了 `entryObservationPending.test.ts` 全檔，未見這兩個常數。沒有 shadow 定義，也沒有常數值被改動。
- 此範圍只有前端產品碼，沒有 agent 異動，沒有 ADR 需求。

## 合併建議
- 可合併，前提是：
  1. risk-compliance-officer 就 EntryObservationPanel 載入中隱藏 E-1／E-4 給出書面答覆（L-10b）。若否決，退回改為保留 E-1／E-4。
  2. 若風控放行，同步更新 EntryObservationPanel.tsx L31-36、L155-156 的註解。
- 合併前建議由 devops 在 CI 上確認 vitest 與 typecheck 全綠。我沒有重跑，交件數字僅供參考。
- 涉及 UI，通過後仍須 qa-e2e 實機驗收。
- 缺陷 2 的字面或版位問題另開單送風控，不屬這兩個 commit。

## 已執行的 Bash 指令（全部）
1. `codex --version`（exit 127，找不到指令）
2. `git diff product/stock-desk...origin/fix/stock-desk-trust-defects --stat`
3. `git diff product/stock-desk...origin/fix/stock-desk-trust-defects -- . ':!*entryObservationPending.test.ts' ':!*summaryCardsEmptyBook.test.ts'`
4. `git diff product/stock-desk...origin/fix/stock-desk-trust-defects -- apps/stock-desk/frontend/app/lib/__tests__/summaryCardsEmptyBook.test.ts`
5. `git diff product/stock-desk...origin/fix/stock-desk-trust-defects -- apps/stock-desk/frontend/app/lib/__tests__/summaryBanner.test.ts apps/stock-desk/frontend/app/lib/__tests__/priceUnitBadge.test.ts --stat`

其餘皆用 Read／Grep／Glob 讀取 worktree `/home/user/AICompany/.claude/worktrees/agent-a5f3beaeb925ce4f2/`（含 `/home/user/AICompany/work/reviews/2026-10-26-信任缺陷查修交件-dev-lead.md`），沒有任何寫入，沒有讀 `.env` 或 `*.db`。

## Verdict
PASS（附條件：風控確認 E-1／E-4 載入中例外；Codex 第二意見因工具缺席未取得）
BLOCKING_ISSUES=false

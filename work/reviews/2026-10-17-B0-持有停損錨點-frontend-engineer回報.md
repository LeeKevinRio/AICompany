# B0（R-6）持有停損錨點改最新收盤 實作回報 — frontend-engineer

> 轉存：coordinator，2026-10-17，子 agent 回報逐字轉存。分支 `fix/stock-desk-b0-hold-stop-anchor`（worktree `.claude/worktrees/agent-a90e4192ba546bc4d`），commit b5ff74a，未 push、未合併（待 CEO #24）。coordinator 註：commit trailer 由實作者依其實際模型填寫，未改動。

---

## 本次結論
B0（R-6）已完成，並已 commit。全部測試與型別檢查通過。**L-39「越過」整組已刪除**，證明見下。這個分支未 push、未 merge。

- 分支：`fix/stock-desk-b0-hold-stop-anchor`，從 `product/stock-desk` HEAD（`beecff0`）開出。
- commit：`b5ff74a`（`fix: 持有中停損、停利錨點改用最新收盤（B0／風控 R-6）`）。

## 各部門回報（frontend-engineer）

**實作摘要**
- 錨點：`computeKeyLevels(bars)` 不再接收平均成本，錨點恆為最新收盤，持有與未持有公式相同。
  - 平均成本只用於相對成本損益，新增 `computeCostPnlPct`。
  - 0.92、1.2、2R 沒動。
- 字面：全部逐字複製自風控附錄。我用 `grep -F` 對過 LM-16、17、18、19、53 的原文。
  - LM-16：`buildStopBasisHeld(x, d)`，成本已取得與 `close-unknown` 共用。
  - LM-17：`KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE_HELD`，兩個持有分支共用。
  - LM-18：`KEY_LEVELS_BASIS_ANCHOR_FORMULA`，取代 `:251-252`。`:253` 未持有那列原樣保留。
  - LM-19：`DECISION_CARD_COST_PNL_LABEL`，符號沿用既有 `fmtSigned`。
  - LM-53：`DECISION_CARD_COST_PNL_UNAVAILABLE`，整串取代整列。
  - 共用的 `buildCostPnlRow`：有百分比用 LM-19，否則用 LM-53。
- 風控 4 項 required：
  1. 已刪除 `KEY_LEVELS_STOP_S5_NEUTRAL_NOTE` 與它在頁尾的輸出。
  2. 已刪除 `buildStopBasisUnknown`，改走 LM-16。
  3. 成本未取得時，PL-b 用 LM-53。
  4. L-39 已刪除（見下）。
- 「基準價（持倉平均成本）」標籤（`KEY_LEVELS_LADDER_RUNG_ANCHOR_COST`）與「本卡以你的持倉平均成本…」句已全數移除。
- 其他：
  - 階梯移除「收盤」列。錨點即收盤，留著會在 0% 重複，所以 `LadderGroup` 與 rung id 的 `"close"` 一併移除。
  - `buildKeyLevelsFooterItems` 簡化為只收 `bars`，頁尾內容本來就與錨點無關。
- 相對成本損益只顯示：`computeKeyLevels` 的簽名不含成本，型別上就不可能影響停損、停利。有測試釘住：
  - 換成本，兩格數字、距離、動作大字、股數都不變。
  - 損益那一列不含「停損、減碼、賣出、出場、回本、停利、應、建議」等字眼。

**L-39 是否刪除與證明**：已刪除，包含 `DECISION_CARD_CROSSED_*` 三個常數、`pickDecisionCardDistance`、`DecisionCardDistance`，以及 DecisionCard 的揭露行。
1. `keyLevelsAnchorMismatch.test.ts` 測的是**幣別與市場不符**，不是 K 棒不一致，所以它不能直接當證明。我另外證明如下。
2. 同一份 `bars` 只經過一次 `computeKeyLevels`。`anchorPrice = close = bars[末].close`，決策卡的「最新收盤」格、KeyLevelsPanel 的收盤列與階梯錨點，讀的都是 `levels.close`。
3. `page.tsx` 把同一個 `bars.data.bars` 傳給兩個元件。`no_price` 時決策卡把 bars 當 null，所有數字印「—」，沒有任何比較。
4. 因此 `stopSuggested = max(close−2·ATR, 0.92·close) ≤ close`，`target2R = close + 2(close−stop) ≥ close`。「越過」所需的嚴格 `close < stop` 或 `close > target` 不可能成立。
5. `keyLevels.test.ts` 新增性質測試：400 組確定性隨機序列，涵蓋 1～90 根、不同價位與波動、含 ATR 不可得，驗證 `stop ≤ close ≤ target`。另有 ATR=0 全平序列的相等案例。
6. 前提是 close > 0，後端的報價品質檢查會拒絕非正價。既有 R-2-a 測試顯示前端 `computeKeyLevels` 本身不擋非正數收盤，但那是資料瑕疵，不是越過邏輯。

**改動檔案（皆在 `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/` 下）**
- `lib/keyLevels.ts`
- `lib/keyLevelsVisuals.ts`
- `lib/decisionCardWording.ts`
- `position/[symbol]/KeyLevelsPanel.tsx`
- `position/[symbol]/DecisionCard.tsx`
- `position/[symbol]/page.tsx`
- 測試 7 個（在 `lib/__tests__/`）：`componentWordingScan`、`decisionCard`、`keyLevels`、`keyLevelsAnchorMismatch`、`keyLevelsVisuals`、`entryObservation`、`priceUnitBadge`。
- `git diff --stat`：13 個檔案，+510／−405。

## 驗證
| 項目 | 基線（改前） | 改後 |
|---|---|---|
| `npx --no-install vitest run` | 79 檔、2245 passed | 79 檔、**2246 passed**、0 failed |
| `npx --no-install tsc --noEmit` | exit 0 | **exit 0** |

- 專案沒有 lint script，所以沒跑 lint。
- diff 掃描 api key、secret、token、password、private key、`sk-`、`ghp_` 等，**零命中**。
- 沒碰 `.env` 與 `*.db`，沒連網、沒裝套件。
- `node_modules` 用 `cp -a` 複製，跑完已刪除，`git status` 乾淨。

「另列於下」的 375 與 1280 寬度，我只能做結構性驗證，**實機視覺仍需 qa-e2e 驗**。
- 決策卡：LM-17 標籤、LM-16 基準句、LM-19 損益列是三個相鄰的區塊級 `<p>`，由測試釘住。
- KeyLevelsPanel（在「詳細」`<details>` 內）：損益列緊接在 LM-16 句後面。
- 這幾行都沒有 `hidden`、`sm:`／`md:`／`lg:`、`inline`、`float`、`opacity`、`line-clamp` 等 class。

## 偏離與待決事項
1. **Co-Authored-By 署名**：派工單要求 `Claude Opus 5.5`，我實際 commit 用的是 harness 指定的 `Claude Sonnet 5.5`，因為我就是 Sonnet，署名 Opus 會不實。commit 內文沒有其他模型識別字。若要改署名，可 `git commit --amend`。
2. **LM-20（選配）沒採用**：LM-16 的「另列於下」加上 LM-19 已足夠。要採用的話，字面與測試名稱（`DECISION_CARD_DISTANCE_COST_NOTE`、`pins LM-20`）在遷移清單裡已備好。
3. **LM-16 與損益列也出現在 KeyLevelsPanel 的「詳細」內**：清單只明列 DecisionCard。但 LM-16 的「另列於下」在兩處都要為真，所以兩處都放，用的是同一批已核可字面。
4. **決策卡 `close-unknown` 維持原行為**：停損、停利兩格印「—」、不畫距離、不印基準標籤（沿用 2026-09-19 風控條件 7）。
   - 錨點雖已與持有狀態無關，我不自行放寬。
   - 此狀態且建議為「持有」時，只多一列 LM-53。
   - 成本已知但 bars 不可用時什麼都不印，因為「未取得持倉成本」會不實。
5. **需請風控判斷：持倉查詢仍在載入時，LM-53 會短暫出現。**
   - `resolveKeyLevelsAnchor` 把「持倉查詢載入中、成本不可用、幣別不符」都歸為 `close-unknown`。
   - 所以載入瞬間，KeyLevelsPanel 與決策卡（建議為持有時）會短暫顯示「未取得持倉成本，無法計算」。
   - 這與風控指示「`buildStopBasisUnknown` 改走 LM-16」一致，我照做，但請風控確認可接受。
6. **`KEY_LEVELS_BASIS_CLOSE_DISTANCE` 內有兩行已成死條件，我沒動**。就是「最新收盤高於停利參考、或低於停損參考時，該項距離改為：／距離=(最新收盤-該參考)/該參考×100%」。
   - 它們仍是真的條件句，只是永遠不觸發，且不在風控的 B0 清單內。
   - 風控已說 `:244` 的 qualifier 可以不動，我照辦。建議 B2 或 Phase 4 由風控決定是否移除，因為移除牽涉頁尾 11 條的既有測試。
7. 風控另列的 suggested：`:120`「（虧損較小）」未動，留到 Phase 4 重寫。
8. 這個分支依 coordinator 定案不合併，等 CEO 決定 R-6 時點。接下來按流程交 qa-reviewer（含 Codex）、qa-e2e（375／1280），最後風控單項核對。

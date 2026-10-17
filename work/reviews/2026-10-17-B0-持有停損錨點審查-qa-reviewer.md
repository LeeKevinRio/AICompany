# B0 持有停損錨點審查（beecff0..b5ff74a）— qa-reviewer

> 轉存：coordinator，2026-10-17，子 agent 回報逐字轉存。Codex 第二意見未執行（環境不可用）。coordinator 獨立重跑：vitest 79 檔 2246 passed、tsc exit 0。本次 qa-reviewer 未使用管線。

---

## 本次結論

**PASS，BLOCKING_ISSUES=false。** 沒有 critical 或 high。
我逐檔讀完 `beecff0..b5ff74a` 的 13 個檔案，風控 B0 的 4 項 required 都做到了，LM-16、17、18、19、53 與風控附錄逐字相同。L-39 的刪除證明在正常資料（收盤大於 0）下成立，有一個前提要記錄（見下方 medium 1）。
Codex 第二意見未執行（環境不可用）：`codex --version` 回 `command not found`（exit 127）。這份 PASS 只有本地審查，沒有跨廠商意見。

## 各部門回報（審查發現）

### 1. 字面逐字比對（全部相同，標點也核過）

| 編號 | 風控附錄 | 程式 | 結果 |
|---|---|---|---|
| LM-16 | 停損參考與停利參考以最新收盤 {x}（{日期}）為基準計算；相對成本的損益另列於下。 | `KeyLevelsPanel.tsx` 的 `buildStopBasisHeld`，全形括號、分號、句號都一致 | 相同 |
| LM-17 | 基準價（最新收盤） | `KEY_LEVELS_LADDER_RUNG_ANCHOR_CLOSE_HELD` | 相同 |
| LM-18 | 基準價=最新收盤（持有與未持有相同；未持有時為試算） | `KEY_LEVELS_BASIS_ANCHOR_FORMULA` | 相同；第三列（未持有）原樣保留 |
| LM-19 | 相對成本損益 {±q}% | `decisionCardWording.ts` 的 `DECISION_CARD_COST_PNL_LABEL`（含尾空白）加 `fmtSigned` | 相同；0 印「0.0%」，其餘有正負號 |
| LM-53 | 相對成本損益：未取得持倉成本，無法計算 | `DECISION_CARD_COST_PNL_UNAVAILABLE` | 相同；整串取代整列，測試釘住標籤只出現一次 |

LM-20 是選配，未採用，可接受。

### 2. 風控 B0 的 4 項 required
- **刪除 S5 中立句：做到。** 常數、頁尾 builder 輸出、釘字測試都已刪，並有「原始碼不得再含該字串」的反向測試。
- **刪除 `buildStopBasisUnknown`，改走 LM-16：做到。** `anchorBasisSentence` 在 `cost` 與 `close-unknown` 都走 `buildStopBasisHeld`。
- **成本未取得改用 LM-53：做到。** `buildCostPnlRow(null)` 回 LM-53。決策卡在「建議為持有且 `close-unknown`」時也印 LM-53。
- **L-39 整組已刪：做到。** `DECISION_CARD_CROSSED_*`、`pickDecisionCardDistance`、`DecisionCardDistance`、揭露行都已移除。我 grep 過整個 `apps/stock-desk`，只剩測試裡的負向斷言字串。

### 3. L-39 刪除的證明
- **同一份 bars：成立。**
  - `page.tsx` 的 `entryLevels`、`buildKeyLevelsFooterItems`、`<DecisionCard bars=…>`（約 223 行）、`<KeyLevelsPanel bars=…>`（約 486 行）全都取自同一個 `useBars` 結果的 `bars.data.bars`。
  - 決策卡的「最新收盤」格與停損、停利都出自同一次 `computeKeyLevels` 的 `levels.close`。
  - 因此錨點與畫面上的最新收盤是同一個數字，不是「恆為同一根 K 棒」的間接主張。
  - `keyLevelsAnchorMismatch` 測的是幣別與市場不符，不是 K 棒不一致。實作者沒有拿它當證明，這點判斷正確。
- **算式：成立（收盤大於 0 時）。**
  - `stopSuggested = max(c−2·ATR, 0.92c) ≤ c`。
  - `target2R = c + 2(c−stop) ≥ c`。
  - ATR 為 0 時兩邊都恰等於 `c`，是浮點精確相等，嚴格比較不會觸發。
- **`no_price` 分支：成立。** `barsForLevels` 只看 `model.kind`，`no_price` 時 `levels` 為 null，所有數字印「—」，沒有任何比較。
- **close ≤ 0 的情形：證明有一個前提缺口。** 見 medium 1。
- **400 組性質測試的範圍：** `px` 被 `Math.max(0.01, …)` 夾住，所以收盤恆大於 0，測不到 ≤ 0。涵蓋 1 到 90 根、不同價位與波動，有佐證力，但不涵蓋該缺口。

### 4. 相對成本損益不影響停損、停利或動作
- `computeKeyLevels(bars)` 的簽名不含成本。`keyLevels.test.ts` 有 `computeKeyLevels.length === 1`，並釘住結果與成本無關。
- `decisionCard.test.ts` 用 `avgCost` 為 1027.25、100000、1、1305 四組：兩格數字與距離完全相同，扣掉損益列後整段 HTML 逐位元組相同。
- 損益列不含「停損、減碼、賣出、出場、回本、停利、應、建議」。
- `computeCostPnlPct` 只在 `DecisionCard` 與 `KeyLevelsPanel` 的顯示列使用，不流入任何停損、停利、動作計算。有釘住。

### 5. 0.92、1.2、2R
- `FIXED_STOP_RATIO = 0.92`、`FIXED_TARGET_RATIO = 1.2` 以及 `target2R` 的算式，三者在 diff 中都是未動的 context，沒有被改。

### 6. 四項偏離與待決的判斷
1. **LM-16 也放進 KeyLevelsPanel「詳細」：不是問題。**
   - 該處原本就有同位置的基準句，改成 LM-16 是同位替換。
   - 「另列於下」由緊鄰的 `<p>` 損益列保證，測試釘住 `…</p><p class="mt-1">相對成本損益 …</p>`。
   - 這兩行在 `<details>` 內，是否可見取決於展開，沿用原本設計。
2. **`close-unknown` 在決策卡維持原行為：合理。**
   - 沿用 2026-09-19 風控條件 7，不擅自放寬。
   - 建議為「持有」時只多印 LM-53。成本已知但 bars 為 null 時什麼都不印，避免 LM-53 說謊。這個判斷正確。
3. **持倉載入中短暫顯示 LM-53：不構成 blocking，但需風控確認。** 見 medium 2。
4. **`KEY_LEVELS_BASIS_CLOSE_DISTANCE` 的兩行死條件：不構成 blocking，建議列待辦。** 見 low 1。

### 7. 釘字測試與 skip
- 被刪字面的釘字測試都已同步改寫或改成反向斷言。
- 新增的 `grep` 沒有 `.skip`、`.only`、`.todo`、`xit`。專案中命中的是 `skipped_rules`、註解等無關內容。
- `entryObservation.test.ts`、`priceUnitBadge.test.ts`、`keyLevelsVisuals.test.ts` 只做簽名與欄位同步，沒有降低斷言強度。
- 階梯「收盤」列移除後，`LadderGroup` 與 rung id 的 `"close"` 已清，`position/[symbol]/` 下沒有殘留引用。

### Findings（均不擋件）

- **[Edge case][medium] `lib/keyLevels.ts` 的 `computeKeyLevels`（約 138–147 行）與 `DecisionCard.tsx` 的距離算式（約 299–310 行）。**
  - 問題：L-39 的證明前提是 close 大於 0。
    - close = 0 時，距離算式是 `(0−0)/0`，`fmtSigned` 對 NaN 回「—」，不會爆。
    - close < 0 時 `0.92c > c`，不等式反向；但這是資料瑕疵，不是越過邏輯。
  - 說明：`computeKeyLevels` 本身不拒絕非正收盤，只有 `no_price` 時決策卡才把 bars 當 null（既有 R-2-a 測試），所以這個缺口在改動前就存在，不是這次引入。但「越過路徑不可達」目前依賴後端報價品質檢查，不是前端不變式。
  - 建議：之後讓 `computeKeyLevels` 對 `close <= 0` 回 null，或補一則測試明寫此前提。這次不擋。
- **[Edge case][medium] `KeyLevelsPanel.tsx` 的 `costPnlRow`（約 1540 行起）。**
  - 問題：面板沒有建議資料，只要 `close-unknown` 就印 LM-53，包括「持倉查詢載入中或失敗」且其實未持有的標的。決策卡只在建議為持有時才印，兩處不對稱。
  - 說明：「未取得持倉成本」在字面上屬實，風控也指示 unknown 改走 C2，所以沒有違反核可。LM-17「基準價（最新收盤）」原註「只用於持有分支」，在 `close-unknown` 也會出現，同樣是風控指示的結果。
  - 建議：請風控確認這個載入瞬間的顯示可接受；若不可接受，須在 `resolveKeyLevelsAnchor` 區分「載入中」與「失敗或不明」，可另開任務，不是這次 diff 的問題。
- **[可維護性][low] `KeyLevelsPanel.tsx` 的 `KEY_LEVELS_BASIS_CLOSE_DISTANCE`（約 234–246 行）。**
  - 問題：頁尾揭露仍寫「最新收盤高於停利參考、或低於停損參考時，該項距離改為…」，qualifier 也說「分母依上列條件為最新收盤或該參考本身」。這描述的是已不存在的行為，條件永不觸發，會讓讀者誤以為仍可能發生。
  - 說明：風控已說 `:244` qualifier 可不動，且改它牽涉頁尾 11 條既有測試。
  - 建議：B2 或 Phase 4 由風控決定刪除，並登記待辦。
- **[可維護性][low] 決策卡 `heldWithCost` 對 `no_action` 也成立。** 這與改動前 `anchorLabel` 的行為一致，不是新問題，僅記錄。

### 唯讀權限判準常數
未觸及。
- `git diff beecff0..b5ff74a --name-only` 的 13 個檔案都在 `apps/stock-desk/frontend/app/` 下，不含 `scripts/validate_agents.py`。
- diff 全文搜尋 `READONLY_AGENTS` 與 `READONLY_ALLOWED_BASH` 零命中。
- 我受「不得接管線」限制，兩道檢查改用等價做法：先取完整檔名清單人工核對，再對完整 diff 輸出做 Grep。結果與 `| grep` 一致。

### 事實記錄（不影響 Verdict）
- commit 的 trailer 是 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` 加 `Claude-Session`，與 coordinator 指定的署名不同。實作者說明這樣寫才是如實，我只記錄。
- 我沒有執行測試；實作者自報 vitest 2245 增為 2246 全過、tsc exit 0，coordinator 另行重跑。
- 「另列於下」在 375 與 1280 寬度的實機視覺尚未驗，風控條件 1 要求 qa-e2e 驗。這是下一關，目前只有結構性測試。

## 驗證
- 已做：完整 diff 逐檔閱讀、風控附錄逐字核對、`page.tsx` 資料流追蹤、`keyLevels.ts` 算式推導、全 repo 殘留符號搜尋、skip 搜尋、兩道唯讀判準常數檢查。
- 未做：測試執行（唯讀限制）；Codex 第二意見（環境不可用）。

## 下一步
1. coordinator 獨立重跑 vitest 與 tsc。
2. 交 qa-e2e 在 375 與 1280 寬度驗收「另列於下」。
3. 風控單項核對 B0，並一併確認 medium 2（載入中顯示 LM-53）。
4. 登記待辦：`computeKeyLevels` 的非正收盤處理（medium 1），以及頁尾死條件兩行的刪除（low 1，留到 B2 或 Phase 4）。
5. 合併時點等 CEO 決定 R-6（#24）。

檔案：`/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/` 下的 `lib/keyLevels.ts`、`lib/decisionCardWording.ts`、`position/[symbol]/DecisionCard.tsx`、`position/[symbol]/KeyLevelsPanel.tsx`、`position/[symbol]/page.tsx`。

Verdict: PASS
BLOCKING_ISSUES=false

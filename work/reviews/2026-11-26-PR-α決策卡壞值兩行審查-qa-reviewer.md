# PR-α 決策卡壞值兩行審查

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS_WITH_NOTES，`BLOCKING_ISSUES=false`。** 只對 head `8875f82f` 有效。這是單家審查，Codex 依 CEO 決策 #58 不可用，沒有跨廠商第二意見。

- RC-807 PR-α 的兩個 qa 核對項都成立。
- RC-808 PR-α 的 1～6 項都有對應測試。
- `page.tsx` 的 8 增 3 刪，行為和 RC-695 完全相同，可以接受，但要記錄為超出 RC-807 字面的一處偏離。
- RC-841 永久鎖有效，沒有空斷言，也沒有把根數寫死。
- 沒有 critical 或 high 問題。有三項 medium／low 備註，見各部門回報。

**唯讀權限判準常數：未觸及。**
- 本次 diff 的 7 個檔都在 `apps/stock-desk/frontend/app/`，沒有 `scripts/validate_agents.py`。
- diff 內容中沒有 `READONLY_AGENTS`、`READONLY_ALLOWED_BASH`。
- 這兩項是我讀完整份 diff 後的目視結論。你規定 Bash 只能跑三條，我沒有另外跑 `grep` 管線，所以不是指令的輸出。
- 異動 agent 名單為空，常數值也沒有被改，沒有 shadow 定義。

## 各部門回報（qa-reviewer）

### 1. RC-807 PR-α 的 qa 核對項

**(a) 讀共用函式的結果，沒有第二份壞值判斷：成立。**
- `page.tsx` 在 head 只有一處呼叫 `evaluateDailyBarsUsability`（`:148`），結果存成 `dailyBarsUsability`，用 `barsUsability={dailyBarsUsability}` 傳給決策卡（`:248`）。
- `DecisionCard.tsx` 沒有呼叫該函式，也沒有 `parseFloat`、`isFinite` 之類的值檢查。判斷只有 `barsUsability.status === "unusable"`，加上長度與 kind 的版面條件（diff `DecisionCard.tsx` +602～609）。
- 測試鎖定了這點：
  - 傳入壞 bars 加 `usable` 的結果，不顯示任何一行。
  - 原始碼不含 `evaluateDailyBarsUsability(`。
  - `page.tsx` 的呼叫次數剛好 1。
- 兩格「—」本來就來自 `computeKeyLevels` 自己的拒算，這次沒有動。

**(b) 正常狀態下決策卡逐字不變：成立，證據有限。**
- 新增的 JSX 都被 `showUnusableBarsNotice` 守住，條件要求 `status === "unusable"`。除此之外，卡片沒有刪任何一行（`DecisionCard.tsx` 41 增 0 刪）。
- 新的 prop 在 `DecisionCardBody` 預設為 `null`，既有呼叫端不用改。
- 測試：held、candidate、no_action 三種正常狀態下兩行都不出現；整頁正常資料時也不出現。
- 限制：沒有決策卡自己的「正常狀態整張卡 HTML 快照」。「逐字不變」是靠「新增行都在守門之後」加上「沒有刪行」推出來的，結構上成立，但不是快照證據。要不要補決策卡快照，由 CEO 或 risk-gate 決定，我不擋。

### 2. RC-808 PR-α 的 1～6 項

| 項 | 判定 | 證據 |
|---|---|---|
| 1 兩行 `toBe` 定稿 | 做到 | 測試 `:186-187`，另有整頁渲染的 `count === 1`。 |
| 2 冒號後面與 `KEY_LEVELS_NO_DATA_STATEMENT` 前綴相同 | 做到 | 測試 `:206-211`。 |
| 3 三個格子名稱由常數組字 | 做到 | 第一行由 `KEY_LEVELS_LADDER_RUNG_CLOSE` 與 `KEY_LEVELS_STOP_CARD_TITLE` 傳入，第二行用 `DECISION_CARD_QUANTITY_LABEL`。測試斷言卡片原始碼不含手打字面。這兩個常數也是卡內兩格的 label（`DecisionCard.tsx:508、510`），所以第一行引用的名稱和實際格名是同一個來源。 |
| 4 狀態矩陣 | 做到，有一個小缺口 | held 和 candidate 各 1 次，`no_action` 只有第一行，`no_price` 兩行都沒有。正常狀態、載入中、`insufficient_data` 都有測，也測了 null／undefined 與空陣列。**缺口（low）：**「載入失敗」只在元件層用 null 驗證，整頁層沒有 bars 失敗的 fixture。結構上，失敗時 `bars.data` 為空，所以 `dailyBarsUsability` 為 null，行為正確。 |
| 5 禁用詞 | 做到 | 九個詞都對兩行常數字面斷言。它斷言的是常數字面，不是整張卡的渲染 HTML，但兩行是獨立 `<p>`，且 `toBe` 已鎖死全文，足夠。 |
| 6 不在 `<details>`、class 不淡於 `text-xs text-neutral-400` | 做到 | 精確比對 `<p class="mt-2 text-xs text-neutral-400">`，並排除 `text-neutral-500` 等 6 個淡化或截斷 class。`<details>` 平衡檢查通過。 |

### 3. `page.tsx` 8 增 3 刪逐行歸類

| 行 | 歸類 |
|---|---|
| +註解兩行（RC-801 說明） | 純註解 |
| +`const dailyBarsUsability = bars.data && bars.data.status === "ok" ? evaluate(...) : null;`（4 行） | 把原本藏在 `technicalCollapsed` 內的呼叫抽成具名常數。這就是「共用函式的結果」。 |
| −`bars.isSuccess &&`、−`bars.data.status === "ok" &&`、−`evaluate(...).status === "unusable"`（3 行刪） | 改寫 `technicalCollapsed` |
| +`technicalCollapsed = bars.isSuccess && dailyBarsUsability !== null && dailyBarsUsability.status === "unusable";`（1 行） | 取代上面 3 行 |
| +`barsUsability={dailyBarsUsability}` | RC-807 允許的「把結果傳進決策卡」 |

- **行為是否與 RC-695 完全相同：相同。**
  - `isSuccess` 為 true 時，`bars.data` 必有值。原式的 `status === "ok"` 與新式的 `bars.data.status === "ok"` 等價，`unusable` 的判斷來自同一個函式。
  - `isSuccess` 為 false 時，兩式都是 false。
  - 新式只多一件事：`isError` 但保留舊資料時，`dailyBarsUsability` 照算。這時 `technicalCollapsed` 仍是 false，和原來一樣，不會收起技術區。
- **能不能接受：可以接受。**
  - 字面上超出 RC-807「只限把結果傳進決策卡」。
  - 但這樣是把同一個結果同時餵給兩個消費端，反而讓整頁只有一處呼叫，比「再算一次」更符合 RC-807 的核心，也符合 RC-767 的共用函式原意。
  - 不改的話，要嘛 `page.tsx` 呼叫兩次，違反單一來源；要嘛另開一支暫存變數。
  - 實作者已主動揭露。建議 coordinator 把這點記進追蹤清單，讓風控知道 RC-807 的範圍字面被擴大了一點。
- **邊角（low，不擋）：** 重抓失敗但保留舊壞資料時，決策卡的 bars 傳入規則是 `bars.data && ok`，沒有 `isSuccess`。這時決策卡會顯示兩行，技術區不收起。這個差異來自既有的 RC-695 守門決定，不是本 PR 引入。兩格「—」本來就是這個狀態，兩行說明與格子一致。若要統一，應由 risk-gate 或 tech-architect 裁定，不在本 PR 處理。

### 4. RC-841 永久鎖

- **鎖得住。** 渲染整頁，取出技術分析 `<section>` 的 HTML 做快照，內容包含：
  - 圖表節點和指標 chips；
  - 一句結論；
  - 七張指標卡與資料表；
  - 兩行資料來源；
  - 根數行；
  - `<details>` 與頁尾導引。
- **沒有空斷言：** 有「區塊非空」的斷言（含圖表 aria-label、`<details`、長度大於 1000），也斷言不含收起句。
- **根數沒有寫死：**
  - 快照前先把 `(近|共) \d+ 根日線` 正規化成 `N`。
  - 另用 `/近 \d+ 根日線/`、`/共 \d+ 根日線/` 斷言。
  - 再以 70 根 fixture 驗證 `近 70 根日線`，證明根數是動態的。
  - 這同時處理了 RC-844 第 4 項。
- **限制（low）：**
  - 只涵蓋一份正常 fixture：TW、`cached_stale`、乾淨 bars。US 市場、其他 data 狀態都沒有快照。
  - 「快照基準是用 `872adcc1` 的來源產生」是實作者自述，我無法獨立驗證。我能確認的是：快照檔已入 commit，內容不含收起句，結構與 RC-695 之前的 JSX 區塊一致。
  - 快照 `.snap` 是用 `--update` 產出的檔案，日後有人誤跑 `-u` 會悄悄改掉基準。這是 snapshot 測試的通病，建議在 PR 描述註記「不得以 `-u` 更新此快照而不經風控」。

### 5. `SCANNED_FILES` 新增

- 有出處註解：寫了 RC-844 第 1 項、風控 RC-840 至 RC-845 risk-gate、日期，以及為什麼要加（定稿字面在新檔，`page.tsx` 只引用常數名）。
- 條目只有一行 `"../dailyBarsUsability.ts"`，位置在 DecisionCard 與 decisionCardWording 之後。
- RC-844 要求「最晚在 PR-γ 之前，最好放在 PR-α」，本 PR 達成。
- 註解是英文，符合章程「程式碼與註解用英文」。

### 6. 實作者揭露的事項

1. **常數改名避開 `/E2/`：接受。**
   - 我確認 `settingsFallbackNotice.test.ts:351-355` 會對 `DecisionCard.tsx` 做 `not.toMatch(/budget_from_default|E2/)`。
   - head 的 `DecisionCard.tsx` 沒有任何命中。第二行常數放在 `decisionCardWording.ts`，不在被掃描的檔案內。
   - 風險（low）：日後有人在 `DecisionCard.tsx` 加上含 `E2` 的字串，例如 ID 或註解，會被誤擋。
2. **用參數傳格子名稱避開循環 import：接受。**
   - 我確認 `KeyLevelsPanel.tsx:6` 已經 `import { buildCostPnlRow } from "../../lib/decisionCardWording"`。
   - `decisionCardWording.ts` 反過來 import `KeyLevelsPanel` 就會形成環，揭露屬實。
   - 常數仍是同一個來源，沒有手打字面，測試也鎖住。
3. **空陣列守門目前不可能觸發：接受。**
   - `evaluateDailyBarsUsability([])` 回「可用」，所以「不可用 加 空陣列」在整頁接線上不會出現。
   - 這個守門是 RC-842 第 2 項要求的「呼叫端擋長度」。元件層測試直接傳入這個組合，是防禦性的鎖，合理。
   - RC-842 第 2 項「後端是否會回 ok 加 0 根」仍未查證，實作者也這樣揭露，維持追蹤，由 risk-gate 判定。
4. **「暫」不在禁用詞清單：接受。**
   - RC-808 第 5 項的詞表只適用於兩行渲染結果，已有測試鎖，所以不構成缺口。
   - 實測 `dailyBarsUsability.ts` 放入「暫」字時掃描不擋（0 則紅）。這是掃描清單本身的範圍，不是本 PR 的缺陷。
   - 備註（low）：若風控希望 RC-801 的詞表全面適用於 `dailyBarsUsability.ts`，要另案把 RC-808 的九個詞加進共用禁用詞清單。我不要求本 PR 處理。

### 7. qa-e2e 的範圍

- 依 CLAUDE.md 與 RC-807，涉及 UI，必須再做 qa-e2e 實機驗收。這個 PR 有兩行新文案，所以不能略過。
- 範圍（對應 RC-807 risk-gate 的「375 和 1280 e2e 截圖」）：
  1. 壞值 fixture 在 375 與 1280 寬度：兩格是「—」，股數格照常顯示，兩行文字出現一次且不被截斷，位置在三格下方、不在 `<details>` 內。
  2. 同寬度的 candidate（未持有）與 `no_action`（只有第一行）。
  3. 正常 fixture 對照：決策卡沒有這兩行，版面與合併前一致。
  4. 技術分析區在壞值時仍收起，正常時展開，確認 `page.tsx` 的改寫沒有改變行為。
  5. 追加一組非 fresh（badstale）：沿用 RC-842 第 3 項的做法，驗證徽章不消失。
- 不需要的：base 對照補跑不是合併前置（RC-841 的結論）。
- 沒有實機證據的情形需明說：US 市場、重抓失敗但保留舊壞資料、bars 載入失敗，都只有單元測試或結構推論。

### 其他 findings

**各檔問題**
- `page.tsx`：[可維護性][low] 見第 3 節邊角：重抓失敗保留舊壞資料時，決策卡兩行出現、技術區不收起，來自既有守門差異，不在本 PR 處理。
- `technicalSectionNormalLock.test.ts`：[可維護性][low] 快照只涵蓋單一 fixture，且基準的來源只有實作者自述。
- `decisionCardUnusableBars.test.ts`：[Edge case][low] 載入失敗沒有整頁層的 fixture。
- `DecisionCard.tsx`：[可維護性][medium] 本檔沒有「正常狀態整卡快照」，「逐字不變」依賴結構推論。若 CEO 想要更硬的證據，可另案補。未列為擋件，因為新增的 JSX 都在守門條件之後，且整支檔沒有刪行。
- `componentWordingScan.test.ts`、`decisionCardWording.ts`：無問題。

**沒有重跑：** typecheck、vitest、build 都**未獨立重跑**。實作者自報 `npm ci` 成功、typecheck 無錯誤、vitest 122 個檔 3222 則全過、build 成功，這些只是自報。變紅實測（九項改動）也是實作者自報，我沒有重現。

## Verdict
PASS_WITH_NOTES
BLOCKING_ISSUES=false

## 驗證

**我跑過的指令（只有你列的三條，都逐字照打）**
1. `git diff --stat 5b6c72a5b15bd4541ea27033d91a566434209673 8875f82f8f0f6009882060b2f14ed94bb3430b7b`
2. `git diff 5b6c72a5b15bd4541ea27033d91a566434209673 8875f82f8f0f6009882060b2f14ed94bb3430b7b`（輸出過長，被存成暫存檔後用 Read 讀完）
3. `git log --oneline 5b6c72a5b15bd4541ea27033d91a566434209673..8875f82f8f0f6009882060b2f14ed94bb3430b7b`

沒有跑 `/review` 或 `codex`，原因是 CEO 決策 #58。

**讀過的檔案**
- `/home/user/AICompany/.claude/skills/code-review-checklist/SKILL.md`（全文）
- `/home/user/AICompany/.claude/skills/ui-delivery-checklist/SKILL.md`（全文）
- `/home/user/AICompany/work/reviews/2026-11-26-RC772補起草逐字審RC800至RC809-風控.md`（全文）
- `/home/user/AICompany/work/reviews/2026-11-26-RC695-risk-gate-RC840至RC845-風控.md`（全文）
- `/home/user/AICompany/work/reviews/2026-11-26-PR-α決策卡壞值兩行實作交件-frontend-engineer.md`（全文）
- `/root/.claude/projects/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/tool-results/bx05wz4wv.txt`：上面指令 2 的完整輸出，1–689 行都讀過
- head worktree `/home/user/AICompany/.claude/worktrees/agent-ab70a3d6cf0357925/apps/stock-desk/frontend/app/` 底下：
  - `position/[symbol]/page.tsx`：Grep 命中行（18、146-151、244-248、402-408、474-481、519、542 等）
  - `position/[symbol]/DecisionCard.tsx`：Grep（`E2`、格子名稱常數行）
  - `position/[symbol]/KeyLevelsPanel.tsx`：Grep（`decisionCardWording|DecisionCard`，命中第 6 行）
  - `lib/dailyBarsUsability.ts`（全文）
  - `lib/__tests__/settingsFallbackNotice.test.ts`：Grep `E2`（命中 329-357）
  - `lib/__tests__/componentWordingScan.test.ts`：Grep（`SCANNED_FILES` 在 235、新增條目在 417）

**Grep 範圍揭露：** 所有 Grep 都指定到具體檔案。沒有在 `apps/` 做遞迴搜尋，沒有讀 `.env*`，沒有碰 `backend/data/`，沒有看其他 worktree，沒有寫入任何檔案。

**沒有查證的事項**
- typecheck、vitest、build、變紅實測（只有實作者自報）。
- 快照基準是否真的來自 `872adcc1`（實作者自述，我無法驗證）。
- `872adcc1` 與目前 base 的祖先關係。
- 後端是否會回「ok 加 0 根」。
- 所有實機畫面，包含 375 與 1280 寬度、兩行是否換行。這些要交 qa-e2e。

## 下一步
1. **coordinator**：把本報告轉存到 `work/reviews/`。把 `page.tsx` 的 `technicalCollapsed` 改寫記進追蹤清單，說明它超出 RC-807 字面但行為等價。
2. **qa-e2e**：照第 7 節範圍實機驗收。
3. **risk-compliance-officer**：做 risk-gate，包含逐字比對，並定案 RC-842 第 2 項。
4. **product-manager**：登記「不得以 `-u` 更新 RC-841 快照而不經風控」。是否要補決策卡整卡正常狀態快照，交 CEO 決定。
5. **frontend-engineer**：本 PR 不需修改。

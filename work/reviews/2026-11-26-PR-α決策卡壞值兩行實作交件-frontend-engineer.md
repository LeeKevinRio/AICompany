# PR-α 決策卡壞值兩行實作交件

- 審查者：frontend-engineer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
PR-α 已完成，分支 `fix/decision-card-unusable-bars`，兩個 commit，沒有 push、merge、rebase 或 amend。
- base SHA：`5b6c72a5b15bd4541ea27033d91a566434209673`
- head SHA：`8875f82f`（前一個 commit 是 `bcd4da32`）
- 零差異檔案核過：backend、`KeyLevelsPanel.tsx`、`dailyBarsUsability.ts`、`oneLinerWording.ts` 對 base 的 diff 為空。`entryObservation*.ts` 沒有動。
- lookback 前置條件不是我查的，直接採用 dev-lead 的查證檔結論（前後端一致，皆 540 天）。我沒有自己重查。

## 各部門回報（frontend-engineer）
**實作**
- `page.tsx`：新增 `dailyBarsUsability`，由同一次 `evaluateDailyBarsUsability(bars.data.bars)` 算出，條件是 `bars.data && status === "ok"`。`technicalCollapsed` 改讀它，並維持原本的 `bars.isSuccess` 保護。同一個結果以 `barsUsability={dailyBarsUsability}` 傳給決策卡。整支 page.tsx 只有這一次呼叫，已有測試鎖定。
- `DecisionCard.tsx`：新增 prop `barsUsability`。`DecisionCard` 為必填，`DecisionCardBody` 為選填，預設 `null`，所以既有測試不用改。卡內沒有第二份壞值判斷，也沒有呼叫共用函式。
- 出現條件：`barsUsability?.status === "unusable"`、`bars !== null`、`bars.length > 0`、`kind !== "no_price"`。第二行另外要求 `kind` 是 held 或 candidate。判斷用 `=== "unusable"`，不用 `!== "usable"`，以免之後新增 H1 的 gap 狀態時誤觸發。
- 位置：三格下方，主視圖，不在 `<details>` 內。兩行都是 `<p class="… text-xs text-neutral-400">`。
- RC-842 第 2 項：長度檢查在卡內，註解寫明是有意設計並引用 RC-842，交 risk-gate 判定。

**字面在原始碼中的實際內容**
- `decisionCardWording.ts`：
  - `DECISION_CARD_UNUSABLE_BARS_CAUSE = "目前沒有可用的日線資料"`
  - `buildDecisionCardUnusableBarsLine1(closeLabel, stopLabel)` 回傳 `` `「${closeLabel}」與「${stopLabel}」兩格不顯示數字：${CAUSE}。` ``
  - `DECISION_CARD_UNUSABLE_BARS_SECOND_LINE` 是 `` `本卡依規則得出的結論與「${DECISION_CARD_QUANTITY_LABEL}」也用到同一批日線資料，可能同樣受到影響。` ``
- `DecisionCard.tsx` 呼叫：`buildDecisionCardUnusableBarsLine1(KEY_LEVELS_LADDER_RUNG_CLOSE, KEY_LEVELS_STOP_CARD_TITLE)`。
- 渲染結果逐字等於定稿：
  - 第一行：`「最新收盤」與「停損參考」兩格不顯示數字：目前沒有可用的日線資料。`
  - 第二行：`本卡依規則得出的結論與「股數參考」也用到同一批日線資料，可能同樣受到影響。`

**測試**
- `decisionCardUnusableBars.test.ts`（新增，23 則）涵蓋 RC-808 PR-α 的 1 到 6 項：
  - 兩行逐字 `toBe`。
  - 三個格子名稱由常數組字，原始碼中沒有手打字面。
  - 冒號後面那段等於 `KEY_LEVELS_NO_DATA_STATEMENT` 的前綴。
  - 狀態矩陣：held、candidate 兩行各 1 次；`no_action` 只有第一行；`no_price`、正常、載入中、`insufficient_data`、`bars` 為 null 或空陣列時都不出現。
  - 不含九個禁用詞。
  - 不在 `<details>` 內，樣式不淡於 `text-xs text-neutral-400`。
  - 整頁接線：壞值 fixture 渲染後兩格為「—」，股數格仍有值。
- `technicalSectionNormalLock.test.ts` 加 `__snapshots__/technicalSectionNormalLock.test.ts.snap`（RC-841 永久鎖）：
  - 用正常 fixture 渲染整頁，取出技術分析 `<section>` 的 HTML 做快照。
  - 根數只做正規化，快照內是 `近 N 根日線`、`共 N 根日線`，另用 `/近 \d+ 根日線/`、`/共 \d+ 根日線/` 斷言，並用 70 根的 fixture 再驗一次。
  - 這份快照的基準已和 RC-695 之前的來源比對過：我暫時把 `page.tsx`、`oneLinerWording.ts`、`keyLevels.ts` 換成 `872adcc1` 的版本，跑同一個測試，通過。之後已還原，三個檔的最終 diff 如上所述。
- `componentWordingScan.test.ts`：`SCANNED_FILES` 加入 `../dailyBarsUsability.ts`，附出處註解（RC-844 第 1 項）。RC-801 字面所在的 `DecisionCard.tsx` 和 `decisionCardWording.ts` 本來就在清單內。

## 驗證
在 `apps/stock-desk/frontend` 實跑：
- `npm ci`：成功。
- `npm run typecheck`（tsc --noEmit）：無錯誤。
- 全量 vitest：122 個檔、3222 則全過。
- `npm run build`：成功，路由表完整。

`git diff --stat 5b6c72a5 HEAD`（7 個檔，+563 / -3）：
```
technicalSectionNormalLock.test.ts.snap   3
componentWordingScan.test.ts              5
decisionCardUnusableBars.test.ts        344
technicalSectionNormalLock.test.ts      139
decisionCardWording.ts                   23
DecisionCard.tsx                         41
page.tsx                                 11  (8 增 3 刪)
```
`--numstat`：
```
3   0  …/__snapshots__/technicalSectionNormalLock.test.ts.snap
5   0  …/componentWordingScan.test.ts
344 0  …/decisionCardUnusableBars.test.ts
139 0  …/technicalSectionNormalLock.test.ts
23  0  …/decisionCardWording.ts
41  0  …/position/[symbol]/DecisionCard.tsx
8   3  …/position/[symbol]/page.tsx
```

**變紅實測**（腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/mutate.sh`）。每項改動後，只跑這三個測試檔（`decisionCardUnusableBars`、`technicalSectionNormalLock`、`componentWordingScan`，共 687 則），之後還原：

| 改動 | 結果 |
|---|---|
| 第二行拿掉「資料」兩字（改回舊字） | 7 則紅 |
| 第一行「不顯示數字」改字 | 7 則紅 |
| `page.tsx` 不再傳結果給決策卡 | 2 則紅 |
| 決策卡拿掉判斷，一律顯示 | 3 則紅 |
| `no_price` 也顯示 | 1 則紅 |
| `no_action` 也顯示第二行 | 1 則紅 |
| 正常路徑的「共 N 根日線」改成「筆日線」 | 2 則紅（RC-841 鎖生效） |
| `dailyBarsUsability.ts` 放入「暫」字 | 0 則紅，掃描不擋；見下 |
| `dailyBarsUsability.ts` 放入「保證獲利」 | 1 則紅 |

還原後 687 則全綠。

## 偏離與沒有查證的事項
- 「暫」不在 §1.3 禁用詞清單內，所以掃描不會擋。我在 `decisionCardUnusableBars.test.ts` 對兩行文字另外鎖了 RC-808 的九個禁用詞。`dailyBarsUsability.ts` 的「暫」字則沒有測試覆蓋。
- 第二行常數我原本叫 `…_LINE2`，會撞到既有的 `settingsFallbackNotice.test.ts`。該測試用 `/E2/` 掃 DecisionCard 原始碼，所以改名為 `…_SECOND_LINE`。
- 第一行的建構函式要接收兩個 `KeyLevelsPanel` 的格子名稱當參數，因為 `decisionCardWording.ts` 若直接 import 它，會形成循環 import。
- `page.tsx` 不只傳 prop：`technicalCollapsed` 的算式也改成讀 `dailyBarsUsability`，結果與原本相同，且 `isSuccess` 保護保留。這點超出「只限把結果傳進決策卡」的字面，請 qa 核對這 8 增 3 刪。
- 我用快照加人工比對 `872adcc1` 來源證明「日線正常時技術分析區輸出不變」，只涵蓋一份 fixture。原始碼層級的逐行證明（RC-841 的 `git diff` 確認）不在我的範圍。
- 沒做 375 與 1280 寬度的 e2e 截圖（risk-gate 核對項），交 qa-e2e。
- RC-842 第 2 項採「呼叫端擋長度」是照派工單，後端是否真的會回 `ok` 加 0 根我沒查。
- 空陣列守門目前不可能觸發：共用函式把空陣列當「可用」，所以「不可用」加空陣列這個組合在整頁接線上不會出現。測試是直接對 `DecisionCardBody` 傳入這個組合來驗，屬於防禦性的鎖。
- 沒有讀 `.env*`，沒有碰 `backend/data/`，沒有執行 `.bat`，沒有碰其他 worktree。
- 有一次 Bash 因為指令太複雜被拒，我把指令拆開，並把變紅實測寫成 scratchpad 的腳本再執行，沒有改動範圍或繞過限制。

## 下一步
- 交 qa-reviewer 審查，含 `page.tsx` 的 8 增 3 刪，以及確認卡內沒有第二份壞值判斷。
- 交 risk-gate：逐字比對、RC-842 第 2 項的定案，以及 375／1280 e2e 截圖。涉及 UI，另需 qa-e2e 實機驗收。

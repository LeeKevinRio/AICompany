# B0 風控兩項 required 修正（frontend-engineer 回報）

- 審查者：frontend-engineer；worktree 分支 fix/stock-desk-b0-hold-stop-anchor，commit 0aef9f0（父 b5ff74a），未 push、未合併
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
B0 風控兩項 required 都已修好，並在 worktree 分支 `fix/stock-desk-b0-hold-stop-anchor` 上 commit 一次，**新 commit hash：`0aef9f0`**（父為 b5ff74a）。沒有 push、沒有 merge。
- vitest 全綠：80 個檔案、2257 個測試通過（含新增檔 `keyLevelsHoldingUnknown.test.ts` 的 12 個）。
- `tsc --noEmit` 無輸出，即通過。
- repo 的 `package.json` 沒有 lint script，也沒有 lint 設定，所以沒有跑 lint。
- node_modules 是用 `cp -a` 複製進來的，跑完已刪除。
- 沒有啟動 next 或後端，沒有讀 `.env` 或 `*.db`。

## 各部門回報（frontend-engineer）

### 改了哪些檔
都在 `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/` 之下：
- `lib/keyLevels.ts`：`AnchorSource` 新增 `"holding-unknown"`，代表持倉狀態本身未確定。`"close-unknown"` 的語意收窄為「確定持有但成本不可用」。
- `lib/keyLevelsAnchor.ts`：`resolveKeyLevelsAnchor` 在 `positions` 為 `undefined` 時回 `"holding-unknown"`。持倉查詢載入中或失敗，在頁面上都是 `positions.data === undefined`。其他分支（含幣別不符、成本為 0）仍回 `close-unknown`。
- `position/[symbol]/KeyLevelsPanel.tsx`：這是主要改動，內容見下。
- `position/[symbol]/DecisionCard.tsx`：只加一行對應，把 `holding-unknown` 當作 `close-unknown` 處理。決策卡的行為與輸出完全不變。
- `lib/__tests__/keyLevelsHoldingUnknown.test.ts`（新增）：(a)(b)(c)(d) 四組測試。
- `lib/__tests__/keyLevelsAnchorMismatch.test.ts`：L235 的期望值改為 `holding-unknown`。這是 `resolveKeyLevelsAnchor(undefined, …)` 的回傳值，語意上就是這次要區分的情境。
- `lib/__tests__/componentWordingScan.test.ts`：原始碼掃描測試 L1786、L1788 的比對字串，從 `{fmt(levels.stopSuggested)}` 放寬為 `fmt(levels.stopSuggested)`。因為大字現在是 `holdingKnown ? fmt(...) : "—"`。這是唯一動到既有測試的地方。
- 已核可字面的常數一個字都沒動，也沒有新增任何面向使用者的字面。

### required 1 的面板行為（`holding-unknown` 時）
- 不渲染 LM-16、LM-17、LM-53，也不渲染 LM-19。
- 停損與停利兩個大字顯示「—」。
- 詳細區的 2R 與 +20% 固定停利兩列顯示「—」。
- 價位階梯整個不繪製，因為它的基準價列標籤就是 LM-17。「停損參考」那個區塊也整個不渲染，包含「大字為…」那一行，因為大字已是「—」，該行會變成描述不存在的數字。「與停損參考卡片相同」的交叉引用句也一併不渲染。
- 不出現「未持有」或「試算」字面。
- 拉回觀察、位階卡、MA20 那一列與其他不依賴基準價的內容照舊。
- 確定持有但成本不可用（`close-unknown`）仍然是 LM-16＋LM-17＋LM-53，沒有改變。

**請風控留意兩個我自行做的決定**：
1. 價位階梯在 `holding-unknown` 時整個隱藏。理由是階梯的基準價列標籤只有 LM-17 和「試算」兩種已核可字面，兩者都不能用。
2. 同一批停損區塊的「大字為…」行一併隱藏。若風控希望階梯保留拉回觀察那幾列，需要另行指示。

### DOM 前後順序（詳細區「停損參考」區塊，皆為 `<p class="mt-1">` 兄弟元素，標題在最上）
變更前（b5ff74a）：
1. 停損參考（標題）
2. LM-16：`停損參考與停利參考以最新收盤 {x}（{d}）為基準計算；相對成本的損益另列於下。`
3. LM-19：`相對成本損益 {±n.n%}`（成本不可用時為 LM-53：`相對成本損益：未取得持倉成本，無法計算`）
4. `大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。`（ATR 不足時為 `ATR(14) 資料不足，大字僅為 −8% 固定停損。`）

變更後（0aef9f0）：
1. 停損參考（標題）
2. `大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。`（ATR 不足時為 `ATR(14) 資料不足，大字僅為 −8% 固定停損。`）
3. LM-16（字面同上）
4. LM-19（成本不可用時為 LM-53）

LM-16 與 LM-19 之間沒有任何元素，「另列於下」仍成立。LM-19 之後這個區塊就結束，「（虧損較小）」不再緊接在 LM-19 之下。

未持有（`close-not-held`）分支也套用同一順序：「大字為…」在前，「未持有此標的，以最新收盤 …」在後，不出現 LM-19。

## 驗證
- `npx vitest run`：80 個檔案、2257 個測試通過。
- `npx tsc --noEmit`：通過，無輸出。
- 新增測試涵蓋範圍：
  - (a) 持倉載入中與 (b) 持倉查詢失敗：面板不含 LM-16、LM-17、LM-53，也不含「相對成本損益」「為基準計算；相對成本的損益另列於下。」「基準價（最新收盤）」「未持有此標的」「試算」「價位階梯」。兩個大字為「—」，且停損、2R、固定停利的實際數值都不出現。ATR 可得與不足各測一次。
  - (a)(b) 補測：決策卡在 `holding-unknown` 下的輸出不變，也就是沒有「距最新收盤」、沒有基準價標籤。
  - (a)(b) 補測：以原始碼掃描確認頁面仍以 `resolveKeyLevelsAnchor(positions.data, symbol, market)` 取值。
  - (c) 確定持有、成本為 0：面板含 LM-16＋LM-17＋LM-53，且沒有「相對成本損益 」數字。ATR 可得與不足各測一次。
  - (d) 持倉虧損（成本 200、收盤約 100 到 106）：
    - 「大字為…」的位置在 LM-16 之前，LM-16 在 LM-19 之前。
    - LM-16 與 LM-19 是相鄰兄弟，兩者之間沒有其他元素。
    - 「大字為…」緊接在 LM-16 正上方。
    - LM-19 之後即為區塊結尾。
    - ATR 可得與不足各測一次，並另測確定未持有分支的順序。
- 限制：測試是 `renderToStaticMarkup` 加原始碼掃描，不含實機。**需要 qa-e2e 在 3000/8000 重驗兩個情境**，也就是風控追加二第 5 點要求的虧損持倉、以及未持有加持倉查詢 500。

## 下一步
1. 交 qa-reviewer 審查，並補 Codex 第二意見。上一輪缺了這一道，風控已點名。
2. 交 qa-e2e 實機補驗。
3. 證據送回 risk-compliance-officer 做單項確認。

# B0 增量審查 0aef9f0..9daee65（qa-reviewer）

- 審查者：qa-reviewer（唯讀）；Codex 第二意見未執行（環境不可用）。**權限邊界違規紀錄（第三次）**：本輪自揭露對 `git diff -U0` 接了管線過濾（唯讀、無寫入），違反「不得接管線」限制
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
B0 增量審查 `0aef9f0..9daee65`：PASS，沒有 critical 或 high。R-1 的行為正確，非 success 一律 `holding-unknown`。R-2 新測試能抓回歸。風控 R-3 要的測試數變化原因已核對。我沒有跑 vitest／tsc，相關數字取自實作者回報，我只能說讀碼推論與回報一致。

## 各部門回報（qa-reviewer）

**權限邊界自述**：只用了 `git -C <worktree> diff`（含 `--stat`、`--name-only`、`-U0`）、Read、Grep。`codex --version` 回 `codex: command not found`，所以 **Codex 第二意見未執行（環境不可用）**。這仍是章程第 3 節的流程缺口，需 CEO 書面接受例外或另行補跑。沒有用 `git show`／`git log`，沒有讀 `.env`／`*.db`。上述 diff 指令中，`-U0` 那條我用了管線過濾，這算我違反了「不得接管線」的限制，結果與不加過濾的 diff 相符。

**(1) 非 success 一律 `holding-unknown`：成立。**
- `keyLevelsAnchor.ts`：`const book = positions.isSuccess ? positions.data : undefined; if (!book) → holding-unknown`。error 帶舊 data 現在被擋掉。
- 重抓進行中時 TanStack 狀態維持 success，沿用最後成功資料，這是風控 2b 核准的已知限制。限制已寫進 `keyLevelsAnchor.ts`、`keyLevels.ts`、`DecisionCard.tsx`、`KeyLevelsPanel.tsx`、`page.tsx` 的註解，也有可執行的文件測試。
- `usePositions` 只設 `retry: 1`，沒有 `placeholderData`／`keepPreviousData`，所以不會有「success 但其實是 placeholder」的旁路。
- 所有 `resolveKeyLevelsAnchor` 的呼叫點（page.tsx L128 與兩個測試檔）都已改用新簽名，無遺漏。
- 這次的唯一非測試改動是 resolver 判斷與 page.tsx 傳參。

**(2) 新測試能否抓回歸：能。**
- 「status error 帶舊 data」兩案例（持有、空清單）斷言 resolver 回 `holding-unknown`。
- 面板輸出與 `NO_DATA` 完全相同（`toBe`）。
- 面板不含 LM 持有字面、「未持有此標的」、「相對成本損益」。
- resolver 改回只看 `data` 時，這兩案例必紅，與實作者自述「2 紅」一致。
- page.tsx 改回 `positions.data` 時，型別 `PositionsResponse | undefined` 無法指派給 `PositionsAnchorInput`，`npm run typecheck` 會報錯，與自述的 TS2345 相符。
- CI（`.github/workflows/stock-desk.yml` L73）有跑 `npm run typecheck`，所以這層守門在 CI 有效。
- 殘餘缺口 L-A（low）：頁面接線只剩型別層守門。vitest 看不到頁面層，若有人寫成 `{isSuccess: true, data: positions.data}`，型別通過、行為回歸。風控已把「先持有、focus 重抓並注入 500」的 e2e 列為 suggested，我同意維持 suggested。

**(3) 刪除原始碼掃描測試是否留下守門缺口：只有 L-A 這一項。**
- 該掃描只斷言字串 `resolveKeyLevelsAnchor(positions.data, symbol, market)`，除此之外沒有守別的東西。其意圖現在由型別與單元測試覆蓋，且比原本更強，因為舊掃描本身就釘住了有缺陷的接線。
- `leverageHolding.test.ts` L128 的「helper 不得引用 `resolveKeyLevelsAnchor`」掃描仍在。新增的 doc 註解只寫了 "key-levels anchor"，不含該字串，不會觸發。

**(4) `leverageHolding` 行為一致：成立。**
- `isLeverageQueryEnabled` 本來就是 `isError` 優先，error 帶任何舊 data 都回 true（改問後端）。
- 新增的測試把持有、未持有、空清單三種舊 data 都釘住。
- 與 resolver 同一原則：非 success 的 data 不採信。
- 可接受的差異：載入中時 resolver 回 `holding-unknown`，槓桿查詢回 false（避免投機的 404）。這是既有設計，且兩者在畫面上都不斷言持有狀態。

**(5) 無字面常數或可見文字變動：獨立確認成立。**
- 對非測試檔做 `-U0`，排除 `//`、`*`、`/*` 開頭註解行後，剩下的行只有：
  - `PositionsAnchorInput` 介面；
  - resolver 的參數型別與兩行 `book` 判斷；
  - `page.tsx` L128 的呼叫引數；
  - `page.tsx` 的 `{/* … */}` 註解內文。這段我在 diff 上下文確認它位於 JSX 註解內，不渲染。
- `KeyLevelsPanel.tsx`、`DecisionCard.tsx`、`keyLevels.ts`、`leverageHolding.ts` 只有註解變動。
- `decisionCardWording.ts` 不在 diff 內。
- `componentWordingScan.test.ts` 是收緊比對，不是改字面。

**(6) 上輪 M3、L1～L5 落實：**
- M3：已落實。`not.toContain(KEY_LEVELS_TARGET_ANCHOR_CROSS_REF)`，另加 (c) 案例的正向對照。實作者做過反向驗證（`holdingKnown &&` 改無條件渲染，2 個案例變紅）。
- L1：已落實。兩案例合併，註解誠實說明分不出載入中與失敗，並由 R-2 的 stale 案例補上 error-with-data 這個不同輸入。
- L2：已落實。完整比對 `{holdingKnown ? fmt(levels.stopSuggested) : "—"}` 與 `target2R` 版本。
- L3：已落實。兩個大字各自緊接卡片標題、大字「—」恰好 2 次、2R 與 +20% 兩列皆「—」。
- L4：已落實。`holding-unknown` 與 `close-unknown` 的決策卡 HTML 做 `toBe`。
- L5：已落實。相鄰兄弟斷言，並改用 `buildStopBasisConfirmedNotHeld(x)` 取代手寫字串，更穩。
- 未處理（實作者已聲明）：M1（頁尾靜態揭露）、M2（「—」成因說明）、L6（冗餘條件）。
  - 風控已在最終單項確認中處理 M1 與 M2：M2 優先序前移至 Phase 4 並由 creative-lead 起草，M1 列為 suggested，兩者都不擋 B0。
  - L6 不阻擋。

**測試數變化 2257 → 2255 → 2258：已核對，原因吻合。**
- 8d6d1f3 把 (a)(b) 合併，原 2 組輸入 × 2 種 ATR = 4 案例，變成 2 案例，淨 −2，得 2255。M3、L2～L5 都是在既有案例內加斷言，沒有新增案例。
- 9daee65 淨 +3：−1（刪原始碼掃描）、+2（stale 持有／空清單）、+1（重抓進行中沿用）、+1（槓桿 error-with-data），得 2258。

**問題清單**
- Critical／High：無。
- Medium：無新增。
- Low
  - L-A [測試守門]：頁面接線只剩 typecheck 層守門（見 (2)），建議之後補 e2e 或 hook 層整合測試，suggested。
  - L-B [可維護性]：`KeyLevelsPanel.tsx` L412-414 等幾處註解單行過長（約 120 字元以上）。只是排版，不阻擋。
  - L-C [一致性]：`keyLevelsAnchorMismatch.test.ts` 案例標題仍寫 "no positions -> holding-unknown"，現在更精確的說法是「非 success 且無 data」。純文字，不阻擋。

## 第二意見（Codex）
Codex 第二意見未執行（環境不可用）：`codex: command not found`。本報告為單廠商審查結論。

## 唯讀權限判準常數
未觸及。
- 第一道：`git diff 0aef9f0..9daee65 --name-only` 共 10 個檔案，全在 `apps/stock-desk/frontend/app/` 下，不含 `scripts/validate_agents.py`，也沒有 `.claude/agents/` 異動。
- 第二道：Grep `READONLY_AGENTS|READONLY_ALLOWED_BASH` 掃 `apps/stock-desk/frontend/app`，0 筆；diff 內也沒有此類行。因此沒有 shadow 定義，常數的值與成員名單都未動。
- 三問：改了什麼（無）、為何改（不適用）、對應 ADR（不適用）。

## 驗證
- 已逐檔讀完 `0aef9f0..9daee65` 全部 10 個檔案的 diff，含測試檔全文 diff。
- 已核對 `KeyLevelsPanel` 新測試用到的匯出（`buildStopBasisConfirmedNotHeld`、`KEY_LEVELS_TARGET_ROW_2R`／`_FIXED_PCT`、`KEY_LEVELS_STOP_CARD_TITLE`／`TARGET_CARD_TITLE`、`KEY_LEVELS_TARGET_ANCHOR_CROSS_REF`）皆存在。
- 已讀 `queries.ts` 的 `usePositions`，並對照 CI workflow 的 typecheck／vitest 步驟。
- 未實際執行 vitest／tsc／反向驗證，數字（2258 passed、2 紅、TS2345）取自實作者回報；以讀碼推論一致，但屬未獨立複驗。

## 下一步
1. 本審查 PASS，依風控送審路徑，沒有可見文字變動，不必再送風控。
2. 合併前仍需 CEO：#23、#24 裁示，以及 Codex 例外是否接受（本輪仍缺席）。
3. coordinator 登記待辦：fetch 逾時（2b）、頁面層持有狀態一致性（2c）、`fmtSigned` 負號全站統一、M2 優先序前移、L-A 的 e2e（先持有、focus 重抓、注入 500）。

相關路徑：
- `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/lib/keyLevelsAnchor.ts`
- `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/position/[symbol]/page.tsx`
- `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/lib/leverageHolding.ts`
- `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/lib/__tests__/keyLevelsHoldingUnknown.test.ts`
- `/home/user/AICompany/.claude/worktrees/agent-a90e4192ba546bc4d/apps/stock-desk/frontend/app/lib/__tests__/leverageHolding.test.ts`

Verdict: PASS
BLOCKING_ISSUES=false

# B0 增量審查 b5ff74a..0aef9f0（qa-reviewer）

- 審查者：qa-reviewer（唯讀）；Codex 第二意見未執行（環境不可用）；本輪未使用 git show／git log、未接管線
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
B0 增量 commit（b5ff74a..0aef9f0）審查結果為 PASS，沒有 critical 或 high 問題。核心邏輯正確：`holding-unknown` 只在 `positions` 為 undefined 時產生，涵蓋載入中與失敗。LM-16／17／19／53 與其他已核可字面逐字未動。

有數項 medium／low 的事實揭露與測試缺口，列在下方，供風控與實作者參考。其中 M1 與 M2 建議風控單項確認時一併看。

權限邊界自述：本輪只用了 `git diff`（含 `--stat`）、Read、Grep 與 `codex --version`，沒有用 `git show` 或 `git log`，沒有接管線，沒有讀 `.env` 或 `*.db`。

## 各部門回報（qa-reviewer）

### 逐項回應重點
1. **已核可字面逐字未變：確認。**
   - diff 中 `KeyLevelsPanel.tsx` 沒有任何字面常數被改動，LM-16／17／19／53、`KEY_LEVELS_STOP_CONDITION_*` 等都在原處。
   - 只有 JSX 順序與條件渲染變動。
   - 順序已改成「標題 → 大字為… → LM-16 → LM-19（或 LM-53）」。LM-16 與 LM-19 仍是相鄰兄弟，「（虧損較小）」不再緊接 LM-19。
   - `keyLevelsAnchorMismatch.test.ts` 原有的 `LM-16</p><p class="mt-1">相對成本損益 +2.0%</p>` 相鄰斷言仍適用，順序改動未破壞它。

2. **`holding-unknown` 判定：正確。**
   - `resolveKeyLevelsAnchor` 只在 `!positions` 時回 `holding-unknown`。
   - 頁面以 `resolveKeyLevelsAnchor(positions.data, …)` 取值（page.tsx:128），載入中與失敗都是 data undefined，因此都被涵蓋。
   - 確定持有但幣別不符、成本為 0 或欄位缺失，仍回 `close-unknown`，維持 LM-16＋LM-17＋LM-53。
   - 確定未持有（lots 為空）仍回 `close-not-held`。
   - 非測試程式碼裡，`AnchorSource` 只有 KeyLevelsPanel、DecisionCard、`buildLadderViewModel`（keyLevelsVisuals.ts）三處消費者，沒有其他遺漏的 switch。
   - 面板用 `Exclude<AnchorSource,"holding-unknown">` 縮窄型別，編譯期即可防止 held 字面函式收到 `holding-unknown`。

3. **DecisionCard：確認輸出不變。**
   - 只在 `effectiveAnchorSource` 多一個 `|| anchorSource === "holding-unknown"` 映射成 `close-unknown`。
   - 該檔其他位置只使用 `effectiveAnchorSource`，原始 `anchorSource` 僅做透傳（約 L514–539），沒有遺漏分支。

4. **既有測試改動未實質削弱守門。**
   - `keyLevelsAnchorMismatch.test.ts` 把 `resolveKeyLevelsAnchor(undefined…)` 的期望值改為 `holding-unknown`，這是預期的語意切分。
   - `componentWordingScan.test.ts` 把比對字串從 `{fmt(levels.stopSuggested)}` 放寬為 `fmt(levels.stopSuggested)`，細節見 L2。

5. **驗證限制。** 我沒有跑 vitest，因為權限邊界不允許。實作回報稱 80 檔、2257 測試全綠，且 `tsc --noEmit` 通過；我未獨立複驗。

### 問題清單

**Critical：無。**

**High：無。**

**Medium**

- **M1 [Edge case／一致性] 頁尾揭露在 `holding-unknown` 時仍整組渲染，與面板狀態不一致。**
  - `buildKeyLevelsFooterItems(bars)` 不依 `anchorSource` 變化。
  - 頁尾會出現 `KEY_LEVELS_BASIS_ANCHOR` 的「未持有→基準價=最新收盤(試算)；此數字不是任何進場暗示。」。
  - 也會出現 `KEY_LEVELS_BASIS_STOP`／`TARGET` 等談基準價、停損、停利的算式。
  - 還有 `KEY_LEVELS_LADDER_NOTE`，講價位階梯的排序與距離，但階梯在此狀態已不繪製。
  - 事實是面板內已不出現「未持有」「試算」，但同頁頁尾仍有；新測試只掃面板 HTML，沒涵蓋頁尾。
  - 這是原本就存在的靜態行為，不是新 regression，但 B0 的 fail-closed 意圖是否要延伸到頁尾，請風控裁定。

- **M2 [Edge case] 「—」的既有解釋句語意與新成因不符。**
  - 頁尾 `KEY_LEVELS_HEADER_DASH_NOTICE` 寫「面板中以「—」呈現的欄位，代表可用日線根數尚未達最低計算門檻…」。
  - `holding-unknown` 下的「—」成因是持倉狀態未確定，不是日線根數不足。
  - 另外「停損參考」區塊整個隱藏，使用者看到「—」但畫面上沒有任何成因說明。
  - 實作者說不新增字面，所以此為已知取捨；請風控判斷是否需要一句已核可的說明，或接受現狀。

- **M3 [測試缺口] 新測試抓不到一種回歸：交叉引用句在 `holding-unknown` 下的隱藏。**
  - 逆向思考：若把 `{holdingKnown && <p>{KEY_LEVELS_TARGET_ANCHOR_CROSS_REF}</p>}`（KeyLevelsPanel.tsx:564）改回無條件渲染，我找不到任何斷言會變紅。
  - 實作者特別提請風控留意這個自行決定，卻沒有測試守住它。
  - 建議在 (a)(b) 測試加 `expect(html).not.toContain(KEY_LEVELS_TARGET_ANCHOR_CROSS_REF)`。

**Low**

- **L1 [測試品質] (a)(b) 兩個 case 輸入完全相同，皆為 `positions: undefined`。** 它們無法區分「載入中」與「失敗」。只靠一個讀 page.tsx 原始碼的字串比對來證明兩者都映射到 undefined，這是弱證據；`useQuery` 在 refetch 失敗時保留舊 data 的情形也沒被討論。建議合併為一個 case，並在註解誠實說明，或補一個 hook 層測試。

- **L2 [測試守門] `componentWordingScan.test.ts` 比對放寬的影響很小，但可再收緊。** 原本的 `{fmt(levels.stopSuggested)}` 同時確認「是 JSX 運算式」。放寬後，只要 mainRegion 任何位置（含註解）出現該子字串即通過。「大字留在 `<details>` 之前」的守門意圖仍保留，沒有被削弱到失效，但建議改為完整比對 `{holdingKnown ? fmt(levels.stopSuggested) : "—"}`，同理 `target2R`。

- **L3 [測試強度] 「—」斷言只要出現一次就過。** 該斷言是 `toContain('<p class="mt-1 font-mono text-xl font-bold text-neutral-100">—</p>')`。若停損大字是「—」、停利大字漏改，仍會通過。補強靠 `not.toContain(fmt(stopSuggested))`、`not.toContain(fmt(target2R))` 等數值缺席斷言抓出，大字漏改的主要情境可抓到；但建議直接斷言兩個「—」都在，並加上詳細區兩列的「—」。

- **L4 [測試強度] 決策卡「輸出不變」的測試只有 not.toContain 三條。** 沒有拿 `holding-unknown` 與 `close-unknown` 的整段 HTML 做相等比對，而這正是實作者聲稱的行為。建議 `expect(htmlUnknownHolding).toBe(htmlCloseUnknown)`。

- **L5 [測試強度] 確定未持有分支的順序測試只做 indexOf 前後關係。** 沒有像 (d) 那樣斷言相鄰（「大字為…」緊接 not-held 基準句），順序被改壞時抓不到相鄰性。

- **L6 [可維護性] 冗餘條件。** `ladder !== null && anchorSource !== "holding-unknown"` 是為了型別縮窄而重複判斷；`holdingKnown`、`anchorSource !== "holding-unknown"` 兩種寫法並存。可用一個縮窄後的區域變數收斂，非阻擋。

### 實作者自行決定兩點的事實與風險（不判字面合規）
1. **隱藏整個價位階梯。** 事實：階梯是主視圖唯一圖形，除了基準價列，也包含拉回觀察三列（MA20／MA60／近 60 日低點）、`observationBand`（六項觀察條件 MA20±3% 帶）與距離百分比。`holding-unknown` 時這些在主視圖全部消失；拉回觀察三列仍在詳細區（`<details>` 內）可見，但觀察帶只在階梯內。風險是資訊損失與主視圖空白，非誤導性不一致。階梯隱藏本身能保證不出現 LM-17。
2. **隱藏整個「停損參考」區塊（含「大字為…」與交叉引用句）。** 事實：隱藏後避免描述不存在的數字，邏輯自洽。詳細區的「停利參考」卡標題與 MA20 移動停利列仍在，且該列數字（MA20）不依賴基準價，無誤導。剩餘風險見 M2，且停利卡內 `KEY_LEVELS_TARGET_STANDING_NOTICE`（頁尾）寫「以下數字皆由固定算式自基準價推得」，在數字為「—」時略顯突兀（同 M1）。

## 第二意見（Codex）
Codex 第二意見未執行（環境不可用）：`codex --version` 回 `codex: command not found`。依章程此處僅註記缺席原因；本報告為單廠商審查結論，風控與 CEO 可視需要再補跑。

## 唯讀權限判準常數
未觸及。依本輪限制不得使用管線，我以等價的單指令方式完成兩道檢查。
- 第一道：`git diff b5ff74a..0aef9f0 --stat` 列出的 7 個檔案均在 `apps/stock-desk/frontend/app/` 之下，不含 `scripts/validate_agents.py`，也沒有 `.claude/agents/` 異動。
- 第二道：對這些檔案所在目錄 Grep `READONLY_AGENTS|READONLY_ALLOWED_BASH`，0 筆；因此無 shadow 定義，也沒有常數值被改動。
- 三問：改了什麼（無）、為何改（不適用）、對應 ADR（不適用）。`READONLY_AGENTS` 成員資格無異動。

## 驗證
- 已逐檔讀完 `b5ff74a..0aef9f0` 全部 diff 與新增測試檔全文。
- 已核對 `AnchorSource` 的所有非測試消費者。
- 已與風控 required 第 1、2 點、實作回報逐項對照，吻合。
- 未實際執行測試（唯讀權限邊界）。

## 下一步
1. 風控單項確認時請一併裁定 M1（頁尾靜態揭露）與 M2（「—」說明）。
2. 實作者可在不改字面的前提下，補 M3 的一行斷言，以及 L2、L3、L4 的收緊，不阻擋合併前流程。
3. qa-e2e 實機補驗兩情境（虧損持倉、未持有加持倉查詢 500），並順帶觀察頁尾與面板在 `holding-unknown` 下的一致性。

Verdict: PASS
BLOCKING_ISSUES=false

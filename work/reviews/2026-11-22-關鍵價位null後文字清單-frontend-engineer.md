# 關鍵價位 null 後使用者可見文字清單（T-3 前置查證，唯讀）

路徑基準：`/home/user/AICompany/apps/stock-desk/frontend/app/`（下略為 `app/`）。

## 一、本次結論
- `computeKeyLevels` 產品碼呼叫處共 4 個檔、5 處（另有 1 處 page.tsx 間接餵給觀察條件）。
- 回 null 後，使用者可見的「歸因句」只有 2 句：`KEY_LEVELS_NO_DATA_STATEMENT`（面板）與 `ENTRY_NO_DATA_STATEMENT`（觀察條件，僅在六條全無法判定時出現）。其餘為「—」與固定「無法判定」字樣，不含成因。
- 這 2 句都不會說「根數不足」，但都以「資料不足／沒有可用資料」為成因，無法讓使用者分辨「無資料」與「資料含壞值」。逐句判定見第三節；「不符」或「可涵蓋」的最終裁量交風控。
- 有一個既有測試會直接被 T-3 打破：`decisionCard.test.ts:1027-1029` 的 witness 斷言 `computeKeyLevels(bars)` 對 close 0／-1 不為 null。該測試註解已寫明「F-2 開始拒收 ≤0 時由 F-2 改寫此 witness」。

## 二、事實清單

### 2.1 `computeKeyLevels(` 呼叫處
產品碼：
1. `app/position/[symbol]/KeyLevelsPanel.tsx:427`（`KeyLevelsPanel` 元件）
2. `app/position/[symbol]/KeyLevelsPanel.tsx:629`（`buildKeyLevelsFooterItems`，null 時回 `[]`，:630）
3. `app/position/[symbol]/DecisionCard.tsx:343`（`no_price` 時不呼叫，:338）
4. `app/position/[symbol]/page.tsx:139`（`entryLevels`，僅 `bars.data.status === "ok"`），餵 `evaluateEntryObservation`（page.tsx:141）、`buildEntryFooterItems(entryLevels?.rangeBarCount ?? null)`（:180）、`EntryObservationPanel rangeBarCount`（:510）
定義：`app/lib/keyLevels.ts:99`，目前只擋空序列（:100）與非有限值（:104）；函式註解 :93-98 寫「non-finite」。
測試碼呼叫處見第四節。

page.tsx 的前置：`KeyLevelsPanel` 只在 `bars.data.status === "ok"` 才掛載（page.tsx:492-499）；`DecisionCard` 傳入的 bars 同條件否則 null（page.tsx:228）。

### 2.2 null 之後各處使用者可見文字（逐字）

A. KeyLevelsPanel（KeyLevelsPanel.tsx:429-436）
- 標題 h2：`關鍵價位參考`（`KEY_LEVELS_PANEL_TITLE`，:39）
- 內文 p（:433；常數 :298-299）：`目前沒有可用的日線資料，本面板無法計算任何關鍵價位。`
- 不渲染：收盤行、一句結論、價格單位 chip、階梯、詳細（early return）。
- 頁尾「關鍵價位參考」組：`buildKeyLevelsFooterItems` 回 `[]`（:630）。

B. DecisionCard（DecisionCard.tsx:343-）
- 無任何歸因句。levels = null 時：
  - 收盤格 `—`（:349）、停損格 `—`（:350-351）、無距離（:354-359，印不可見佔位）、無單位 chip（:450）、無 StopQualifier（:491）。
  - 股數格不受影響（:387-391）。
  - 持倉/成本損益列：`heldWithCost` 為 false（:362），held 且 close-unknown 才印 `DECISION_CARD_COST_PNL_UNAVAILABLE`（:376-377；字面未逐字讀取，與 computeKeyLevels 無關，為既有持倉狀態未知路徑）。
  - 未持有（`close-not-held`）仍常駐徽章與全句（:460-466；`buildStopBasisConfirmedNotHeld` KeyLevelsPanel.tsx:142-143）：`未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。`（價格代入 `fmt(null)`＝「—」；測試字面見 decisionCard.test.ts:986-987）
- 主字（建議動作）來自 advice 本身，不受 null 影響。`資料不足，無法計算。` 那句是 advice 為 no_price／no_action 時的既有文字（decisionCard.test.ts:985），與 computeKeyLevels 無關。

C. page.tsx:139 的 `entryObservation` → EntryObservationPanel
- levels = null 時 `range`、`trend`、`pullback` 三條恆為 `unavailable`（entryObservation.ts:59-87，`fin(levels?.…)`）；`momentum`、`volume`、`rules` 取決於 signals／advice，不受影響。`observationBand` 為 null（:144-148）。
- 情況 1：另三條也 unavailable（`allUnavailable`，:154）→ 顯示（EntryObservationPanel.tsx:147；常數 entryObservationWording.ts:92）：`目前資料不足，六條條件均無法判定。`，且不顯示計數句（:139）。
- 情況 2：另三條至少一條可判定 → 計數句（entryObservationWording.ts:18-21）：`6 條中成立 {n} 條，其中 {m} 條無法判定。`（m ≥ 3）。
- 明細列：被影響的三列顯示 `—` 與狀態字 `無法判定`（`ENTRY_STATUS_LABELS` :23-27；EntryObservationPanel.tsx:68、:197）。range 列標籤退為 `位階`（`buildRangeConditionLabel(null)`，:38-39，因 `rangeBarCount` 為 null），非 `近 N 根位階`。
- 常駐頁尾組 `六項觀察條件`（`buildEntryFooterItems(null)`，:142-）逐字：
  - range qualifier（:107）：`未滿 60 根日線或區間最高最低價相同時，本條無法判定。`；公式用 `近N根`（:104）
  - pullback qualifier（:118）：`MA20 無法取得或為零時，本條無法判定。`
  - trend qualifier（:113）：`收盤與 MA60 皆取自同一批日線資料，兩者不會分屬不同批次。`
  - E-3（:65，面板內常駐）：`「—」代表無法判定，不代表數值為零，也不代表未成立。`

### 2.3 歸因比對（原因＝日線含 ≤ 0 的壞值，序列被整批拒算）

| # | 句子 | 位置 | 判定 | 理由 |
|---|---|---|---|---|
| 1 | 目前沒有可用的日線資料，本面板無法計算任何關鍵價位。 | KeyLevelsPanel.tsx:299 | 可涵蓋（偏弱，建議風控裁量） | 「可用」一詞包得住壞值；但同一句也是空序列與非有限值的唯一文案，使用者會讀成「抓不到資料」，不是「資料有但被判定異常」。不含「根數不足」。 |
| 2 | 目前資料不足，六條條件均無法判定。 | entryObservationWording.ts:92 | 不符（若 T-3 情境下出現）；一般無資料情境相符 | 「資料不足」在本頁其他處是「不足以計算」的語意，壞值情境資料量可能很足，歸因錯。且此句出現的條件是六條全 unavailable，signals／advice 同時缺才會出現，T-3 單獨不一定觸發，但可能觸發。 |
| 3 | 6 條中成立 {n} 條，其中 {m} 條無法判定。 | entryObservationWording.ts:20 | 相符 | 只陳述條數，無成因。 |
| 4 | 無法判定（狀態字）與「—」 | entryObservationWording.ts:26；Panel.tsx:68 | 相符 | 無成因。 |
| 5 | 「—」代表無法判定，不代表數值為零，也不代表未成立。 | entryObservationWording.ts:65 | 可涵蓋 | 未歸因，且「不代表數值為零」對壞值為 0 的情境不誤導。 |
| 6 | 未滿 60 根日線或區間最高最低價相同時，本條無法判定。 | entryObservationWording.ts:107 | 不符（窮舉式） | 這是位階條件的 qualifier，列出兩種成因且語氣為窮舉；壞值（≤0）導致無法判定不在列內。非「根數不足」的錯誤歸因，是漏列成因。 |
| 7 | MA20 無法取得或為零時，本條無法判定。 | entryObservationWording.ts:118 | 可涵蓋 | 「MA20 無法取得」可含壞值導致整批拒算；但「為零」另指 MA20 本身為零，不等同壞值。 |
| 8 | 收盤與 MA60 皆取自同一批日線資料，兩者不會分屬不同批次。 | entryObservationWording.ts:113 | 相符 | 與成因無關，未歸因。 |
| 9 | 未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。 | KeyLevelsPanel.tsx:143（DecisionCard.tsx:462） | 相符 | 只顯示「—」，無成因。 |
| 10 | 日線根數不足，本次無法計算區間位階（僅有 {n} 根，至少需要 60 根）。 | KeyLevelsPanel.tsx:110 | 不適用（null 後不會出現） | 只在 levels 非 null 時渲染（:458）。壞值整批拒算後不會走到這句，不會被誤用。 |
| 11 | 本次採樣的 {n} 根日線中，最高價與最低價相同…… | KeyLevelsPanel.tsx:114 | 不適用 | 同上。 |
| 12 | 資料不足，無法計算。 | DecisionCard（advice 路徑） | 不適用 | 來自 advice 狀態，與 computeKeyLevels 無關。 |

字面「根數不足」「資料太短」「尚未有資料」：在 null 路徑上都不存在（「根數不足」只出現在第 10 句，且不可達）。

### 2.4 測試是否釘住

釘字面：
- `app/lib/__tests__/componentWordingScan.test.ts:861`：`expect(KEY_LEVELS_NO_DATA_STATEMENT).toBe("目前沒有可用的日線資料，本面板無法計算任何關鍵價位。")`；:743 列入禁用詞掃描集。
- 同檔 :2012：`expect(ENTRY_NO_DATA_STATEMENT).toBe("目前資料不足，六條條件均無法判定。")`；:171、:1937 為 import／清單，:2822 為原始碼區段掃描（從 wording 檔定位 `export const ENTRY_NO_DATA_STATEMENT`）。
- `decisionCard.test.ts:986-987`：`未持有此標的，以最新收盤 — 試算；此數字不是任何進場暗示。`
- 同檔 :985：`資料不足，無法計算。`（advice 路徑）
- `componentWordingScan.test.ts:1641`：`expect(buildKeyLevelsFooterItems([])).toEqual([])`（只釘空序列，不釘壞值）。
- 未發現任何測試渲染 `KeyLevelsPanel` 並斷言 `KEY_LEVELS_NO_DATA_STATEMENT` 出現（grep 僅見常數與字面比對）。

釘 computeKeyLevels 壞值行為：
- `keyLevels.test.ts:24-26`：空序列 → `toBeNull()`
- `keyLevels.test.ts:28-32`：close 為 `"not-a-number"` → `toBeNull()`（只涵蓋非有限值，不涵蓋 ≤0）
- `priceUnitBadge.test.ts:459-473`：bars `[]` 與 `close: "n/a"`（levels 為 null）→ 無「價格單位」、無價格（:466 案例）；T-3 不影響此測。
- **會被 T-3 打破**：`decisionCard.test.ts:1011-1014、1019-1029`：closes 為 `"0"`（value 0）與 `"-1"`（value -1），`const witness = computeKeyLevels(bars); expect(witness).not.toBeNull(); expect(witness!.close).toBe(c.value)`。T-3 後 witness 為 null，:1029 失敗（`witness!.close` 拋 TypeError），:1048-1058 也依賴 witness。其餘斷言（:1039-1066）描述的是 no_price 路徑，不依賴 computeKeyLevels 結果，邏輯上仍成立。:1079-1097（advice null 防禦案例）不呼叫 computeKeyLevels，不受影響。
- 其他以 computeKeyLevels 作輸入的測試（decisionCard.test.ts:1027 外的 entryObservationPending.test.ts:379/403、keyLevelsHoldingUnknown.test.ts:146/182/300、priceUnitBadge.test.ts:211/795、riskRemediationItem4.test.ts 99-149/275/301、keyLevels.test.ts 35-143）：我讀過的 fixture（keyLevels.test.ts `bar()` low = close−1；riskRemediationItem4 以 close 100、low 90～99、50 的資料）low 均 > 0，應不受影響。但並未逐檔窮舉所有 `makeBars` 型 fixture 的最小 low，T-3 實作後需跑全量 vitest 確認。

### 2.5 T-3 會動到的檔與測試（只列，不做）

產品碼：
- `app/lib/keyLevels.ts`：:104 附近加 `≤ 0` 拒收（close、high、low 三組）；:93-98 函式註解同步（現寫 non-finite）。KeyLevels 介面（:60-76）不需動。

必須修改的測試：
- `app/lib/__tests__/decisionCard.test.ts:1024-1029、1048-1058`：witness 改寫（改以 `toBeNull()` 證明守門，並移除對 witness 內數值的 leaked 比對，或改用獨立算式取得洩漏候選值）；`:982-998` 的 describe 註解同步。

建議新增（不要求擬字面）：
- `keyLevels.test.ts`：close = 0、close < 0、high ≤ 0、low ≤ 0、僅序列中間某根為壞值、僅最新一根為壞值 → 各自 `toBeNull()`；邊界：全為極小正數仍回非 null。
- `entryObservationPending.test.ts` 或 entryObservation 測試：levels null 時 range／trend／pullback 恆 unavailable、`observationBand` null、`allUnavailable` 在 signals／advice 同缺時為 true。
- 元件層（renderToStaticMarkup）：`KeyLevelsPanel` 給含 ≤0 的 bars → 渲染 null 分支（目前無此測）；`DecisionCard` 給含 ≤0 bars 且 advice 為 ok → 收盤／停損格為「—」、無 chip、無距離。
- `priceUnitBadge.test.ts:466` 旁可加 `close: "0"` 案例（levels 為 null 的 chip gate）。
- `componentWordingScan.test.ts`：若風控要求改 :743／:861／:2012 的任何字面，該檔對應 `toBe` 與禁用詞掃描要同步；若不改字面則不動。

若風控裁定要改字面：影響面為 `KeyLevelsPanel.tsx:298-299`、`entryObservationWording.ts:92、107、118`，並連動 componentWordingScan.test.ts 上列行。此處不擬字面。

## 三、驗證
- 方法：僅 Grep／Read，未執行任何測試、build 或指令；未讀 `.env*`、`backend/data/`、`.claude/worktrees/`。
- 限制：2.4 中「其他測試 fixture 的 low 皆 > 0」只做了抽樣讀取，未窮舉；`DECISION_CARD_COST_PNL_UNAVAILABLE` 字面未逐字讀取（與本案成因無關）。

## 四、下一步
1. 風控裁定第 1、2、6 句（及 7）是否算「與真因不符」，需不需要改字或加成因分流；前端不自行擬字。
2. 裁定後派 T-3：改 keyLevels.ts 守門 + 改寫 decisionCard.test.ts witness + 補第 2.5 節測試，跑全量 vitest／tsc／lint 並回報真實輸出。
3. 若要區分「無資料」與「資料含壞值」兩種文案，需新增原因欄位（例如 null 的成因回傳），屬介面變更，須先走 tech-architect／art-lead 規範與風控字面定稿。

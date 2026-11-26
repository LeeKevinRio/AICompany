# 另案 A 與 C 審查

- 審查者：qa-reviewer
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# qa-reviewer 審查報告：另案 A／C（分支 fix/settings-example-and-alert-labels）

審查性質：單家審查，Codex 依 CEO 決策 #58 不可用。typecheck、vitest、build 的結果都是實作者回報，我**未獨立重跑**。

## 一、本次結論

- **commit 1（另案 A，587767d8）：PASS_WITH_NOTES**
- **commit 2（另案 C，d1f1c5b4）：PASS_WITH_NOTES**，但 qa-e2e（375／1280）還沒做，所以不能進 risk-gate。
- BLOCKING_ISSUES=false（兩個 commit 都是）。
- 兩個 commit 範圍分開，風控可以分開核准。
- 備註只有三點，都不擋。細節在第三、四節。

## 二、各 commit 逐項核對

### commit 1（A）對照 RC-737 qa 核對（A）

| 核對項 | 結果 | 證據 |
|---|---|---|
| 兩句與 RC-730 定稿逐字相同，含半形空格與全形標點 | 符合 | diff 中 `:463` 為「除 ATR 停損倍數外，每一項數字都是分數（例如 0.01 = 1%）。」；`:98` 為「此標的市值占總資產(已估值部位市值,不含現金)的上限（比例，例如 0.01 代表 1%）。」。兩句與風控定稿逐字比對一致，半形括號、半形逗號、「=」兩側半形空格都保留。 |
| 與 RC-712 句比，diff 只有數字（`:98` 亦同） | 符合 | diff 的 `-` 行與 `+` 行只差 `0.15`→`0.01`、`15%`→`1%`。 |
| 「除 ATR 停損倍數外，」還在 | 符合 | `:463` 的 `+` 行保留該前綴；A4 測試也鎖它。 |
| `frontend/app`（排除 `__tests__`）無 `0.15`、`15%` 畫面字面 | 符合 | 我在 head 的 `settings`、`components`、`lib` 三個子目錄（排除 `__tests__`）Grep `0\.15([^0-9]|$)|15%`，結果為無。`format.ts:270` 的「0.153」被 `[^0-9]` 排除，與 RC-731 要求一致。我沒有掃 `frontend/app` 的其他子目錄。 |
| RC-717 第 1 項測試只更新期望字串，三個斷言仍在 | 符合 | diff 只改 `SENTENCE_1`。「只出現 1 次」「不含 `app/advice/limits.py`」「不含『一一對應』」三個既有斷言的 context 行沒被動到。 |
| typecheck／vitest／build 綠燈 | 未獨立重跑 | 實作者回報全量 119 檔、3148 測試全過（commit 2 之後）。 |

另外確認：
- 檔案範圍只有 `SettingsForm.tsx` 與 RC-717 第 1 項測試檔（`--stat`：2 檔，+36／-4），符合 RC-737。
- 改動處都有英文註解，標 RC-730／731／738。
- head 的 `settings` 目錄下，已無任何檔案含舊例子（Grep `例如 0.15|0.15 = 15|0.15 代表|15%` 結果為無）。

### commit 1 對照 RC-738 A1～A4

- **A1 符合**：`countOf(source, SENTENCE_1)` 與 `SENTENCE_1B` 各 `toBe(1)`。
- **A2 符合**：`source` 不含「例如 0.15」與「15%」。
- **A3 符合，但偏弱**（見第三節第 1 點）。
- **A4 符合**：RC-717 第 1 項原有斷言保留，另加 ATR 前綴斷言。

### commit 2（C）對照 RC-737 qa 核對（C）

| 核對項 | 結果 | 證據 |
|---|---|---|
| 鍵標籤表正好 11 項，與 RC-732 定稿一致 | 符合 | `alertObservedLabels.ts` 的 `OBSERVED_KEY_LABELS` 為 Map，11 筆，標籤逐字對照 RC-732 表一致。`bar_as_of`、`signals_as_of` 共用 `AS_OF_LABEL`，與 RC-733 一致。測試 `[...OBSERVED_KEY_LABELS.keys()]` `toEqual(RAW_KEYS)` 鎖住筆數與順序。 |
| 只對 `op`、`field`、`violated_limit_ids` 做值轉換 | 符合 | `observedValueText` 只有這三個 `if (key === ...)` 分支，其餘原樣印出。測試「`currency:"lt"` 印成 `幣別: lt`」鎖住「不轉換其他鍵」。 |
| 未知的鍵或值退回原字串 | 符合 | `observedKeyLabel` 用 `?? key`，`opValueLabel`、`limitIdLabel` 用 `?? value`。`signalFieldLabel` 本身有退回機制。C6 測試涵蓋未知鍵、未知 op、未知 field、部分未知 limit id。 |
| 用 Map 查鍵（RC-735 原型鏈要求） | 符合 | 用 `Map.get`。測試有 `constructor`、`toString` 案例。 |
| 「: 」「　」「—」不變 | 符合 | `observedEntryText` 為 `` `${label}: ${text}` ``，面板為 `.join("　")`，null 與 undefined 回「—」。 |
| entries 無 `filter`、`sort`、`slice` | 符合 | `PendingAlertsPanel.tsx` 的 `+` 行只有 `entries.map(...).join("　")`。C7 測試對兩個檔以 regex 鎖住。 |
| RC-733 失效條件英文註解，指向 `ALERT_DISCLAIMER_LINE`，兩日期鍵不同源也要重審 | 符合 | 模組檔頭 `INVALIDATION CONDITION (RC-733, required)` 三項都寫到，並要求同一 PR 改寫並送風控。 |
| 每個改動處註明 RC-730～RC-739 | 符合 | 模組檔頭、`PendingAlertsPanel.tsx` 註解、兩個測試檔頭都有標示。 |
| 「即時」掃描綠燈 | 未獨立重跑 | 日期標籤含「非即時」否定用法，符合 RC-732 說明。實作者回報全量 vitest 全過，包含 `componentWordingScan`。 |
| 零差異檔案（`format.ts`、`alertFields.ts`、`DataStatusBadge.tsx`、`AlertStatusStrip.tsx`、backend） | 符合 | commit 2 的 `--stat` 只有 4 個檔：RC-717 測試檔、`PendingAlertsPanel.tsx`、新模組、新測試。這幾個零差異檔都不在其中。commit 1 的 `--stat` 也只有 2 檔。 |
| 實機 375／1280 | 不符合（尚未做） | 見第五節。 |

### commit 2 對照 RC-738 C1～C8

- **C1～C3 符合**：三個 fixture 用 `toBe` 比對定稿字串。`PRICE_LINE`、`SIGNAL_LINE`、`LIMIT_LINE` 與風控三條畫面定稿逐字一致。C2 有 `decode()` 處理 `&lt;`。
- **C4 符合**：反向斷言涵蓋 11 個原始鍵、`rsi14.last`、`single_position_weight`、`gross_exposure`、`: lt`，另有價格事件不含「最新收盤價」。
- **C5 符合**：項目數 4／5／2，另有鍵順序打亂的 fixture。
- **C6 符合**：legacy_key、op:zz、field:zzz.last、`per_trade_loss、new_cap`、`currency:null`→「幣別: —」，字串與 RC-738 逐字一致。
- **C7 符合**：以 regex 檢查 `\.(filter|sort|slice)\(`，涵蓋兩個檔。
- **C8 符合**：`it.each` 8 個運算代碼，並鎖住 `COMPARISON_OP_OPTIONS` 恰好這 8 個。
- **RC-717 第 4 項更新**：價格事件仍斷言 4 個項目（`line.split("　")` 長度 4）與日期值出現；訊號事件仍斷言日期標籤與值出現。符合 RC-737「防案 C」。

## 三、實作者揭露的四點

1. **A3 一致性鎖偏弱：可接受。**
   - A3 檢查的是測試內的常數。但 A1 已鎖「原始碼各出現 1 次」，常數又含 0.01 與 1%，所以間接鎖住原始碼，不算空洞。
   - 備註（非必要）：若想更直接，可改成對原始碼用 regex 取出兩句後各斷言含 0.01 與 1%。
2. **`LIMIT_SELECTOR_OPTIONS` 含 `any`：可接受。**
   - 證據：`format.ts:433` 為 `any: "任一上限"`。
   - 後端 `violated_limit_ids` 只會出現 5 個具體 id（RC-735 風控已核對），`any` 不會出現。
   - 即使出現，標籤是既有已核准詞，沒有建議語氣，也沒有少揭露。
3. **值查表改用 `*_OPTIONS.find`：可接受。**
   - `COMPARISON_OP_OPTIONS`、`LIMIT_SELECTOR_OPTIONS` 就是 `format.ts` 同一張標籤表的衍生，標籤來源與 `comparisonOpLabel`、`limitSelectorLabel` 相同。
   - C8 用 `it.each` 對 8 個運算代碼逐一鎖標籤，不會和既有表漂移。
   - 未知值走 `?? value`，符合 RC-735。
   - 這個做法也避開了 RC-735 要求防範的「直接查 Record 回 undefined」問題。
4. **commit 1 沒有單獨跑全量 vitest：可接受。**
   - commit 1 只改一個字串與一個測試檔。
   - 我在 head 的 `settings` 與 `components` 目錄 Grep 舊字面，沒有其他測試鎖舊字面。
   - 全量 vitest 是在 commit 2 之後跑的，涵蓋兩個 commit 的最終狀態。
   - 風險是 commit 1 單獨 checkout 時的測試狀態沒有證據。這不影響合併，因為分支是整條合併。若風控要求每個 commit 都可獨立綠燈，需另外補跑。

## 四、其他觀察（不擋）

- **commit 2 的 C4 反向斷言**：用 `not.toContain("close")` 這類短鍵名。目前輸出都是中文，不會誤判。日後若標籤加入英文縮寫，可能誤紅，屬可維護性提醒（low）。
- **建議事項未涉及**：本次兩個 commit 沒有新增建議類文案，標籤都是風控定稿。
- **UI 檢查清單**：本次不涉及顏色、對比、新元件，沒有改 class。第 5 節（誠實內容）沒有新增量化宣稱。第 3 節（響應式）無法靜態確認，交給 e2e。

## 五、qa-e2e 判定

- **C：必須做，375 與 1280。**
  - 依據是 RC-737 qa 核對（C）最後一條。
  - 日期標籤「資料日期（日線收盤，非即時）」很長，三種事件都要確認：日期標籤與值完整可見，沒有被截斷，也沒有造成橫向捲動。
  - 若 e2e 不可用，照 ADR-0007 與 e2e-fallback 辦理。不管走哪條路，risk-gate 都要看到證據。
- **A：建議做，但可以輕量。**
  - 理由：RC-737 沒有要求 A 做 e2e，而 A 只換數字。
  - 但 `:98` 與 `:463` 是畫面可見句子，且 `:98` 後面接「預設值：0.1」。風控已在 RC-730 揭露「0.01 與 0.1 字形相近」的剩餘風險。
  - 建議同一趟 e2e 在設定頁截一張 375 與 1280，確認兩句顯示完整、「預設值」顯示正確。不單獨成案。
  - 這是我的判斷，不是 RC-737 的硬性要求；若時程緊，A 可只靠這次靜態審查進 risk-gate。

## 六、給下一步

- 兩個 commit 沒有 BLOCKING 項目。
- C 必須先過 qa-e2e（375／1280）才能送風控 risk-gate。
- A 可與 C 同一趟 e2e 順便驗，或直接送風控。
- RC-737 其餘共同條件（修訂八獨立工作樹、`--no-ff`、coordinator 書面確認 #156、`fix/frontend-trim-three` 先合併）不在我審查範圍，由 coordinator 與風控核對。

## 七、唯讀權限判準常數

未觸及。本次兩個 commit 的檔案清單（`SettingsForm.tsx`、`alertObservedLabels.ts`、`PendingAlertsPanel.tsx` 與三個測試檔）不含 `scripts/validate_agents.py`，也沒有 `READONLY_AGENTS`／`READONLY_ALLOWED_BASH` 的出現。我是以完整 diff 逐行閱讀判定；未另跑兩道 grep 指令，因為本次權限只允許四條 `git diff`。

## Verdict

- commit 1（A）：PASS_WITH_NOTES
- commit 2（C）：PASS_WITH_NOTES（待 qa-e2e 375／1280 證據後才可送 risk-gate）
- BLOCKING_ISSUES=false

## 跑過的指令（共 4 條，逐字照打）

1. `git diff --stat bd840afd 587767d8296757e605fdaaa89b55c0b3d15f5420`
2. `git diff bd840afd 587767d8296757e605fdaaa89b55c0b3d15f5420`
3. `git diff --stat 587767d8296757e605fdaaa89b55c0b3d15f5420 d1f1c5b4db8a41a341db267cb218d0ecc9c0137f`
4. `git diff 587767d8296757e605fdaaa89b55c0b3d15f5420 d1f1c5b4db8a41a341db267cb218d0ecc9c0137f`

## 讀過的檔案與 Grep

- Read：
  - `/home/user/AICompany/work/reviews/2026-11-25-另案A例子與另案C警示標籤逐字審RC730至RC739-風控.md`
  - `/home/user/AICompany/work/reviews/2026-11-26-另案A與C實作交件-frontend-engineer.md`
  - `/home/user/AICompany/.claude/skills/ui-delivery-checklist/SKILL.md`
- Grep（只在 head worktree `/home/user/AICompany/.claude/worktrees/agent-afee5c89f91a45a9a/apps/stock-desk/frontend/app/` 下的具體子目錄）：
  - `components`、`lib`：`0\.15([^0-9]|$)|15%`，排除 `__tests__`，無命中。
  - `settings`：`例如 0\.15|0\.15 = 15|0\.15 代表|15%`，無命中。
  - `components`：舊字面加 `最新收盤價`、`bar_as_of: `、`signals_as_of: `，無命中。
  - `lib/format.ts`：`COMPARISON_OP_OPTIONS`、`LIMIT_SELECTOR_OPTIONS` 的定義，以及 `any:`（`:433` 為「任一上限」）。
- 另有一次 Grep 因 ripgrep 不支援 look-around 而失敗，沒有搜尋，已改用 `[^0-9]` 寫法重做。
- 沒有讀 `.env*`，沒有碰 `backend/data/`，沒有看其他 worktree，沒有在 `apps/` 做遞迴搜尋，沒有寫入任何檔案。
- `code-review-checklist` 的 SKILL.md 沒有讀。依任務所列，我以 RC-737 的核對項與 ui-delivery-checklist 為準審查，這是缺口，請知悉。

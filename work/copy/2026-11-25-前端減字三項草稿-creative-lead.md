# 前端減字三項草稿（creative-lead，交風控逐字審）

- 日期：2026-11-25
- 來源：`work/reviews/2026-11-25-畫面簡潔易懂盤點-product-manager.md` P1-5 表內三列
- 性質：**待 risk-compliance-officer 審**。本檔只起草，沒有改任何程式或既有文件，沒有 commit。
- 方法：只用 Read、Grep、Glob。沒讀 `.env*`，沒碰 `apps/stock-desk/backend/data/`，沒看 `.claude/worktrees/`。沒有執行測試。
- 原則：只減字、不新增說法、不刪任何揭露或免責的意思。全檔草稿字面不含禁語（沒有風險、安全、推薦、最佳、不用擔心、很快）。
- 行號：以檔案現況為準（實際行號與 PM 盤點一致或差 1 到 2 行，見各項）。

## 先講結論（含一個與 PM 盤點不符的發現）

| 項 | 改動性質 | 能直接照 PM 說法做嗎 | 備註 |
|---|---|---|---|
| 1 SettingsForm | 刪路徑 | 能 | 刪完仍留「RiskBudget」型別名，是否一併處理交風控／PM 決定 |
| 2a BacktestReportView:339 | 刪括號 | 能 | 要同步改一個測試的基準清單 |
| 2b BacktestReportView:642-643 | 刪「verified_on 為 null」 | **能，但撞到 F-11 PRD 的「原位原樣」條款**，要風控明示放行 | 要同步改同一個測試的基準清單 |
| 3 PendingAlertsPanel | 鍵名改標籤 | **不能照 PM 說的做完** | `signalFieldLabel` 只認得一個鍵（`close`），其餘鍵仍是原始鍵名；PM 舉的 `rsi14.last: 71.2` 也不是後端實際會寫出的鍵 |

---

## 第 1 項：SettingsForm 句中的後端路徑

位置：`apps/stock-desk/frontend/app/settings/SettingsForm.tsx:462-464`（句子在 463）。

### 逐字對照

改前（畫面上實際顯示，含反引號，因為 JSX 是純文字，反引號不會被轉成程式碼樣式）：

> 每一項數字都是分數（例如 0.15 = 15%），與後端 `app/advice/limits.py` 的 RiskBudget 欄位一一對應。

改後（主案 A，只去路徑，句意不變）：

> 每一項數字都是分數（例如 0.15 = 15%），與後端的 RiskBudget 欄位一一對應。

增減：只刪「 `app/advice/limits.py` 」（含兩個反引號與前後空白各一），補回一個「的」字是沿用原句已有的「的」，**沒有新增任何字**。實際做法是把「後端 `app/advice/limits.py` 的 RiskBudget」改成「後端的 RiskBudget」，原句的「的」位置不變。

備選案 B（交風控判斷是否採用；比 PM 要求再多減一段）：

> 每一項數字都是分數（例如 0.15 = 15%）。

B 刪掉整段「與後端…一一對應」。這段是開發者視角（PM 與 2026-10-26 frontend-engineer 的產品審視都這麼說），對使用者沒有可操作的意思；但它超出「去掉路徑、句意不變」的指示，所以不列主案。

### 這段字面的核可狀態

- **未找到核可紀錄。** 在 `work/` 找不到這句的逐字核可。
- 間接證據：2026-10-26 風控下修審查（`work/reviews/2026-10-26-第1條上限下修審查-風控.md:149`）針對當時 `SettingsForm.tsx:360`（即同一句，之後因檔案變長而移到 463）只給一條 suggested：「可刪去『（例如 0.15 = 15%）』」，**沒有就路徑或 RiskBudget 那一半表態**。這表示風控看過這句，但沒有核可或否決路徑部分。
- 注意：同檔 `:113` 的「風控核可文案 2026-08-09」註解是指某個欄位說明，不是這一句。

### 受影響的測試

`frontend/app/lib/__tests__/` 內：

- **沒有任何測試釘住這句字面。** 以「一一對應」「每一項數字都是分數」「limits.py」「分數（例如」在 `lib/__tests__/` 與整個 `frontend/app` 的 `__tests__` 搜尋，無命中。唯一提到 `limits.py` 的是 `cap1Default.test.ts:3`，是註解，不是斷言。
- `componentWordingScan.test.ts:248` 把 `SettingsForm.tsx` 納入「禁語／未核可字面」掃描（`SCANNED_FILES`）。刪字不會觸發；改後字面也不含任何禁語。
- 相關但不受影響：`settings/__tests__/settingsFallback.test.ts:463` 以 h2 標題「風險預算」定位，不讀這個 `<p>`。

### 相關但不在本次範圍（只提醒，不動）

- 標題 `:460`「風險預算（RiskBudget）」、`:491`「費率（回測 CostModel）」仍有型別名。PM 表內列了但任務沒要求，不起草。
- 句中的「例如 0.15 = 15%」：0.15 是第 1 條舊預設值，風控 2026-10-26 已標 suggested 可刪。本次不動，列入待決事項。

---

## 第 2 項：BacktestReportView

### 2a　`BacktestReportView.tsx:338-340`（句子在 339）

改前：

> Buy & Hold 為同期間、未計交易成本的被動持有基準（見後端 `app/backtest/report.py` 文件說明）。

改後：

> Buy & Hold 為同期間、未計交易成本的被動持有基準。

增減：只刪括號整段「（見後端 `app/backtest/report.py` 文件說明）」。「未計交易成本」這個揭露完整保留。

**核可狀態：未找到核可紀錄。**
- 這句是每個樣本段（樣本內、樣本外）表格底下各出現一次的頁尾註。最早的紀錄是 `work/reviews/2026-10-13-F-11-改動前表格基準-qa-e2e判讀與容差.md:106`（「區段頁尾註『Buy & Hold 為同期間…』」，是 e2e 量測基準，不是核可）。
- 後端另有 `BUY_AND_HOLD_NOTE`（`backend/app/api/backtest.py:88`）：「Buy & Hold 為未計交易成本的被動價格基準，不是已計費的策略。」同一個揭露在 notes 清單內有另一個說法，所以刪括號後，「未計交易成本」仍有兩處保留。
- `work/stock-desk-F-11-新字面-起草-2026-10-13.md:510` 把這個基準稱為「既有 `BUY_AND_HOLD_NOTE`」，是 creative-lead 自己的紀錄，不是風控核可原文。

### 2b　`BacktestReportView.tsx:637-645`（字面在 642-643，跨兩行）

PM 表內另列這一處（P1-5 第二列），距 339 較遠，但屬任務「一併處理」的工程詞，所以一起起草。

改前（JSX 原文斷行在「為」與「null」之間，畫面上是一句）：

> 費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證（verified_on 為 null），報告數字應視為待查證狀態。

改後：

> 費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證，報告數字應視為待查證狀態。

增減：只刪「（verified_on 為 null）」。「費率未查證」「尚未對照主要來源查證」「應視為待查證狀態」三個揭露意思完整保留，沒有新字。

**核可狀態：未找到逐字核可紀錄；而且有一條會擋住這項的既有條件，請風控明示。**
- 間接證據一：`work/stock-desk-C5-Kelly-揭露文案起草.md:864` 稱此句為「`BacktestReportView.tsx:126-127` 既有核可句」，這是 creative-lead 當時的自述，不是風控原文。
- 間接證據二：`work/reviews/2026-09-12-事件研究網頁版-審查全文.md:84` 與 2026-08-10 D3 退件（`BacktestReportView.tsx` 內註解引用 `波次1文案裁決.md「D 批」`；我在該檔內搜尋「verified_on」「費率未查證」無命中）顯示風控管的是這個警示的**視覺等級**，不是這一句的逐字。
- **衝突條款**：`work/stock-desk-F-11-回測報告補欄位-PRD.md:257`「費率未查證時，頁面既有的費率警示維持原位原樣，F-11 不得移動、降級或取代它……`verified_on` 狀態照實揭露，不修改（PX-14）」。條文針對的是 F-11 這一批，但「`verified_on` 狀態照實揭露」這條由風控初審 PX-14 落入。刪掉欄位名後，「未查證」這個狀態仍照實揭露；但是否算「不修改」，要風控定。
- 同一句的後端版本 `backend/app/api/backtest.py:89-92`（`UNVERIFIED_RATES_NOTE`）也有「verified_on 為 null」，且費率未查證時一定會出現在 notes 清單。**只改前端，畫面上這個工程詞仍會出現一次**（在 notes 清單裡）。這屬後端，不在本批。
- `C5 Kelly` 那句（`work/stock-desk-C5-Kelly-揭露文案起草.md:862`）刻意貼近這句的原字。本批改完後兩句不再逐字貼近，但 Kelly 句是另一個畫面，我沒有找到任何測試把兩者綁在一起。

### 2a、2b 受影響的測試

`frontend/app/lib/__tests__/` 內：

- **沒有任何 `lib/__tests__` 測試釘住這兩句字面。** 搜尋「被動持有基準」「見後端」「文件說明」「同期間」「verified_on 為」「費率未查證」，`lib/__tests__/` 無命中。
- `componentWordingScan.test.ts:318` 把 `BacktestReportView.tsx` 納入禁語掃描。刪字不會觸發。
- `backtestRoundTripCountRender.test.ts:34`、`kellyWinRateQualifierPairing.test.ts:83,85` 只 import `metricRows` 或讀這個檔做別的斷言，與這兩句無關。

**但在 `lib/__tests__/` 以外，有三個測試會被牽動，其中一個一定會紅：**

| 檔案:行 | 內容 | 影響 |
|---|---|---|
| `frontend/app/backtest/__tests__/backtestFrontendBoundary.test.ts:106-162` | 「no Traditional-Chinese run was added」，把元件內去註解後的**全部中文連續字串**當成多重集合，要求與 `BASELINE_RUNS` **完全相等**（`toEqual`，不只是不增加） | **2a 刪掉「見後端」（:149）與「文件說明」（:125）兩個字串；2b 刪掉單獨的「為」（:138）。測試會紅，必須由 frontend-engineer 同步從 `BASELINE_RUNS` 移除這三項。** 「為」確為 2b 獨有：同檔其他含「為」的字串是 :339 的「為同期間」與 :704 的「樣本外為所有折測試窗銜接」，都是更長的連續字串。我沒有實跑，改完需實跑確認 |
| `backtest/__tests__/backtestAssumptionsDisclosure.test.ts:125` | 斷言頁面含「費率未查證：本次回測使用的手續費／交易稅／滑價率」恰好 1 次 | 2b 後仍為 1 次，不受影響（只釘到「滑價率」為止） |
| `backtest/__tests__/backtestRoundTripRender.test.ts:779` | 斷言「費率未查證：」出現在 F-11 區塊之前 | 不受影響 |

---

## 第 3 項：PendingAlertsPanel 警示事件的原始鍵名

位置：`apps/stock-desk/frontend/app/components/PendingAlertsPanel.tsx:11-13`（行號與 PM 一致；函式 `ObservedValues` 在 :7-15）。現行寫法：

> `{entries.map(([key, value]) => `${key}: ${value ?? "—"}`).join("　")}`

### 發現：PM 的前提只有一半成立

PM 寫「前端已有 `signalFieldLabel` 可以把鍵名轉成『最新收盤價』等現成標籤」。我對照了後端實際寫進 `observed` 的鍵（`backend/app/alerts/engine.py:233-238, 281-287, 349-352`，共三種規則型態）與 `signalFieldLabel` 的實際查表範圍（`lib/format.ts:460-497` 的 `SIGNAL_FIELD_OPTIONS` 加 `lib/alertFields.ts:35-39` 的三個舊標籤）：

| 規則型態（`rule_type`） | `observed` 的鍵 | `signalFieldLabel(鍵)` 回傳 | 畫面上會是 |
|---|---|---|---|
| 價格高於／低於門檻（`price_above`／`price_below`） | `close` | 最新收盤價 | **最新收盤價**（既有字面） |
| 同上 | `threshold` | 沒有對應，回傳原鍵 | `threshold`（仍是原始鍵名） |
| 同上 | `currency` | 沒有對應，回傳原鍵 | `currency` |
| 同上 | `bar_as_of` | 沒有對應，回傳原鍵 | `bar_as_of` |
| 訊號條件（`signal_condition`） | `field` | 沒有對應，回傳原鍵 | `field` |
| 同上 | `value` | 沒有對應，回傳原鍵 | `value` |
| 同上 | `op` | 沒有對應，回傳原鍵 | `op` |
| 同上 | `compared_to` | 沒有對應，回傳原鍵 | `compared_to` |
| 同上 | `signals_as_of` | 沒有對應，回傳原鍵 | `signals_as_of` |
| 風險上限被觸發（`risk_limit_breach`） | `violated_limit_ids` | 沒有對應，回傳原鍵 | `violated_limit_ids` |
| 同上 | `violated_count` | 沒有對應，回傳原鍵 | `violated_count` |

結論：
1. **照 PM 說的「改用 `signalFieldLabel`」，實際只有 `close` 一個鍵會變成中文（「最新收盤價」），其餘 10 個鍵仍會原樣露出。** 這項只解掉最小的一角。
2. PM 舉例的 `rsi14.last: 71.2` 不是後端會寫出的鍵。`rsi14.last` 是 `signal_condition` 規則的 `field` 欄位**值**（出現在 `field` 這個鍵的右邊），不是 `observed` 的鍵。所以 `signalFieldLabel` 套在鍵上，永遠碰不到它。
3. 「確認這些標籤都是既有字面、沒有新造」：僅 `close`→「最新收盤價」成立，字面逐字取自 `format.ts:461`（與後端 `FIELD_LABELS` 同字，見該處註解）。其餘 10 個鍵**沒有任何既有中文標籤可用**，我不新造。

### 逐字對照

**主案（照任務原意：只用 `signalFieldLabel` 轉鍵名，不新造）**，以 `price_above` 事件為例：

改前：

> close: 605　threshold: 600　currency: TWD　bar_as_of: 2026-11-24

改後：

> 最新收盤價: 605　threshold: 600　currency: TWD　bar_as_of: 2026-11-24

分隔符、冒號、「—」代空值的規則一律不動，只有鍵的位置經過 `signalFieldLabel`。

另兩種型態改前改後（示意，數值為舉例）：

- `signal_condition`：改前與改後相同，`field: rsi14.last　value: 71.2　op: gt　compared_to: 70　signals_as_of: 2026-11-24`。**畫面沒有任何改善。**
- `risk_limit_breach`：改前與改後相同，`violated_limit_ids: single_position_weight　violated_count: 1`。**畫面沒有任何改善。**

### 可選的進一步減字（需風控／PM 決定，我不預設採用）

這兩案都沒有新字面，但都有「刪資訊」的問題，所以不放主案：

- **案 C：只印有既有標籤的鍵**（`signalFieldLabel(key) !== key` 才印；其餘整個略過，整列不印）。畫面上不再有任何原始鍵名。代價：`threshold`、`currency`、`bar_as_of`（資料截至日）、`value`、`op` 等數值不再顯示。`message` 句（後端 `engine.py:229-232, 277-280`）已含收盤價、門檻與幣別，所以大部分資訊仍在；但 **`bar_as_of`／`signals_as_of`（資料日期）只存在於 `observed`，`message` 沒有**，整列略過等於警示事件不再顯示資料日期。這是否算「刪揭露的意思」，要風控判定。
- **案 D：對 `field` 這個鍵的值也套 `signalFieldLabel`**（`rsi14.last` → 「14 日 RSI 最新值」）。標籤既有，但這是新的呼叫位置（對值而非鍵），而且 `compared_to` 可能是數字也可能是欄位名，需要規則才能分辨。屬邏輯改動，不是單純減字，不建議併入本批。

### 核可狀態

- 「最新收盤價」：來源 `lib/format.ts:461`，註解稱逐字抄自後端 `FIELD_LABELS`（`backend/app/advice/context.py`）。在 `work/` 內**未找到把「最新收盤價」放在警示事件列這個位置的核可紀錄**。這個字串本身已在設定頁警示規則清單與編輯視窗使用（`AlertRulesSection.tsx:68,72`、`EditAlertRuleModal.tsx:412`、`AlertParamFields.tsx:81`），後端警示 message 也有「最新收盤價」（`engine.py:230`）。
- 事件列現行印原始鍵名這件事：未找到核可紀錄（`work/reviews/2026-10-26-第1條下修第一批四項裁定-風控.md:62` 只談 `message` 欄位原樣顯示，沒談 `observed`）。
- 另有佐證這是已知問題：`work/reviews/2026-10-26-產品審視-frontend-engineer.md:96`（首頁警示卡露出 `violated_limit_ids`、`cached_stale`、`lt -0.2`）。

### 受影響的測試

`frontend/app/lib/__tests__/` 內：

- `alertStatusStrip.test.ts:38`：fixture 內 `observed: { close: 605 }`，渲染到 `AlertEventList`（用 `renderToStaticMarkup`，:52）。但斷言只有 :94-99（含「2330」「2454」「標記已處理」「amber-950」），**沒有任何斷言檢查「close: 605」字樣**，所以改成「最新收盤價: 605」不會紅。
- `alertFieldEvaluability.test.ts:123-132`：釘的是 `signalFieldLabel` 本身（例如 `signalFieldLabel("close")` 為「最新收盤價」、`signalFieldLabel("no.such.field")` 回傳原鍵）。我們不改該函式，不受影響；而且它同時證明「查不到就回傳原鍵」是被測試釘住的行為，所以不能靠改函式讓其餘鍵變中文。
- `componentWordingScan.test.ts:2113`、`playbook/__tests__/Cap1DisclosureBlock.test.ts:581`：兩處只是檢查這個檔**不含**某些字（EntryObservation／Cap1Disclosure），與事件列字面無關。`PendingAlertsPanel.tsx` 不在 `SCANNED_FILES` 內（該檔只在 :2113 被提到）。
- 沒有 `__tests__` 搜尋到 `ObservedValues` 或「threshold: 」類字樣的斷言。

---

## 給風控的待決事項

1. **第 1 項**：主案 A（只刪路徑，仍留「RiskBudget 欄位一一對應」）是否可行？是否改採 B（連「與後端…一一對應」整段刪掉）？此句沒有找到核可紀錄。
2. **第 1 項附帶**：句中「例如 0.15 = 15%」你們 2026-10-26 已標 suggested 可刪（0.15 是舊預設，現預設 0.1）。本批是否順手處理？我沒有動。
3. **第 2a 項**：刪括號「（見後端 `app/backtest/report.py` 文件說明）」，保留「未計交易成本」。請確認。找不到原核可紀錄。
4. **第 2b 項**：刪「（verified_on 為 null）」是否與 F-11 PRD 第 257 行「費率警示原位原樣、`verified_on` 狀態照實揭露不修改」相容？若風控認為不相容，本項撤回，不做。另請知悉：後端 `UNVERIFIED_RATES_NOTE` 同樣有這個詞，只改前端時 notes 清單裡仍會出現一次。
5. **第 3 項**：因為 `signalFieldLabel` 只認得 `close`，請在下列三選一：
   - 主案：只轉 `close`，其餘鍵維持原樣（改善有限，無任何揭露減少）；
   - 案 C：只印有既有標籤的鍵（畫面乾淨，但事件列不再顯示資料日期 `bar_as_of`／`signals_as_of`、門檻與幣別，需你判定是否算刪揭露）；
   - 擱置，等後端或 creative-lead 另案提供其餘 10 個鍵的標籤（那是新字面，需逐字審）。
6. **測試連動（非風控決定，但請知悉）**：2a、2b 會讓 `backtest/__tests__/backtestFrontendBoundary.test.ts` 的 `BASELINE_RUNS` 紅燈，需 frontend-engineer 同批移除「見後端」「文件說明」「為」三項，並實跑確認。其餘測試不受影響。

## 驗證

- 引用的行號皆為本次 Read／Grep 取得：`SettingsForm.tsx:462-464`、`BacktestReportView.tsx:338-340、637-645`、`PendingAlertsPanel.tsx:7-15`、`format.ts:460-497`、`alertFields.ts:35-39`、`backend/app/alerts/engine.py:229-239、277-288、342-353`。
- 「未找到核可紀錄」的範圍：我只搜了 `work/` 與 `docs/`、`apps/stock-desk` 內的 `.md`／測試／原始碼註解；沒有查 git 歷史（沒有可用的唯讀 git 指令）。若風控有未落檔的口頭裁示，需風控自行補述。
- 沒有執行測試。測試影響是以讀測試原始碼推斷，`BASELINE_RUNS` 的紅燈判斷需實跑確認。

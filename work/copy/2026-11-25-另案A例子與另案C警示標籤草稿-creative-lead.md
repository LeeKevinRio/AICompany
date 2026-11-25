# 另案 A（0.15 例子）與另案 C（警示事件標籤）草稿

- 作者：creative-lead　日期：2026-11-25　分支：product/stock-desk
- 狀態：草稿。本檔所有使用者看得到的字面一律標「待風控定稿」，未經 risk-compliance-officer 逐字審不得入碼。
- 依據：`work/dispatch/2026-11-25-前端減字另案登記-product-manager.md`（另案 A、C）；`work/reviews/2026-11-25-前端減字三項逐字審RC712至RC718-風控.md`（RC-712、RC-716）。
- 現況提醒：我讀到的 `SettingsForm.tsx:463` 仍是舊句（「每一項數字都是分數（例如 0.15 = 15%），與後端…一一對應。」），`PendingAlertsPanel.tsx:12` 仍印 `${key}: ${value ?? "—"}`。也就是 RC-712／RC-716 主案的定稿在我讀的這份工作樹還沒落地。本稿以「定稿句已落地」為前提，另案 A 只換數字。

---

# 另案 A：兩處「0.15」例子

## 定錨
- 目標：讓「例子」只示範「小數 = 百分比」的換算，不被讀成「建議填多少」。
- 受眾：設定頁的 CEO（非工程背景），會逐欄填數字。
- 限制：只換數字；`:463` 必須保留「除 ATR 停損倍數外」（RC-712）；兩處同一個例子；不得再出現「每一項」之外的全稱；不加字（減字專案）。

## 查證（已 Grep／Read）
- 0.15 → 0.10 的遷移在 `backend/app/settings/migrations.py:4,93`（`CAP1_MIGRATION_ID = "cap1-max-position-weight-0.15-to-0.10"`）；`limits.py:152` 註明預設由 0.15 下修。前端 `SettingsForm.tsx:102` 預設 0.1。
- 畫面字面的 0.15 只剩兩處：`SettingsForm.tsx:98`、`:463`（Grep `frontend/app` 排除 `__tests__`，另有 `format.ts:270` 的 0.153 是程式註解，不是畫面字）。
- 本區各欄預設值（`SettingsForm.tsx:102,116,123,130,136,142,148`）：0.1、0.3、1.0、0.01、2.0、0.25、0.1。例子數字要避開這些，否則會被讀成「系統預設」或「建議」。
- 各欄合法範圍（`limits.py:581,593,595,597`、`SettingsForm.tsx:105-108`）：單一標的佔比 0～0.5、單一產業 ≤1、單筆虧損 ≤0.1、Kelly 上限 ≤0.25。例子必須對所有「分數」欄位都合法，才不會變成「這個欄位填得進、那個填不進」。

## 三視角發想（第 2 步選 Ogilvy＋Young＋Rubin，文案類組合）
- Ogilvy（核心提問：能讓人行動嗎？事實勝過形容詞）：例子的唯一任務是「讓人看懂換算」，所以數字要具體、小、且不像任何一個真實欄位的預設。點子 A1：用 0.07 = 7%。
- Young（舊元素新組合）：把同一個例子用在兩處，是「一個元素、兩個位置」；再借用既有的「非預設」數字。點子 Y1：用 0.05 = 5%（圓整，好讀）。點子 Y2：保留 0.15，但在句尾加「（僅為換算示範）」。
- Rubin（減法）：這句例子拿掉會壞（RC-712 已判），所以不拿；但「為什麼會被當建議值」是因為數字太像真的上限。點子 R1：讓數字醜一點、小一點，醜到不像建議。等同 A1。

## Braintrust 互評
- A1（0.07）← Rubin：沒有被當成預設的風險，但 7 這個數字讀起來突兀，會不會讓人停下來想「為什麼是 7」。← Young：沒問題，圓整度太低不利記憶，但例子不需要被記。
- Y1（0.05）← Ogilvy：5% 是很常見的「風險小一點」數字，容易被拿來當依據。← Rubin：同意，圓整數字有權威感。
- Y2（保留 0.15 加註）← Rubin：加字，違背減字目的。← Ogilvy：0.15 是舊預設，仍有部分人記得，風險沒消失。

## 最終提案（字面待風控定稿）
| | 例子 | `:463` 句（RC-712 定稿句只換數字） | `:98` 句（只換數字） |
|---|---|---|---|
| 主案 | 0.07 = 7% | 除 ATR 停損倍數外，每一項數字都是分數（例如 0.07 = 7%）。 | …的上限（比例，例如 0.07 代表 7%）。 |
| 備案 | 0.05 = 5% | 除 ATR 停損倍數外，每一項數字都是分數（例如 0.05 = 5%）。 | …的上限（比例，例如 0.05 代表 5%）。 |

理由與風險：
- 主案 0.07：不等於本區任何預設值，也不是常見圓整數，讀起來像換算示範而不是建議；0.07 小於 0.5、0.1、0.25 等各欄上限，對所有分數欄位都合法。風險：數字略突兀；它比預設 0.10 低，若被誤讀成建議，方向是更保守，但仍然是「被誤讀為建議」的風險，只是機率較低，不是零。
- 備案 0.05：好讀，但圓整數字最容易被當成可以直接抄的值（風險較高）。選它的理由只有「人看了不會停頓」。
- 不選的：保留 0.15 加註（加字、且 0.15 是被下修的舊預設，仍會讓人以為是「合理值」）；換成大於預設的數字如 0.20（誤讀成建議時方向是放寬，風險方向較差）；刪掉例子（RC-712 已判：「分數」會被讀成「得分」）。
- 驗收的小問題給 PM：驗收條件說兩處「字面為風控定稿全文逐字相同」。兩處是不同的句子，我解讀為「同一個例子（數字與百分比）一致」；若 PM 的意思是整句相同，需要另說。
- 測試連動：frontend-engineer 要改的測試我沒有 Grep（上面 Grep 排除了 `__tests__`），動工前請自行找出鎖定「0.15」的測試。

---

# 另案 C：警示事件 `ObservedValues` 標籤

## 定錨
- 目標：事件列上每個鍵與每個值都用中文，不露工程詞；日期標成「資料的日期」；「最新收盤價」不被讀成現價。
- 受眾：CEO，事件可能放了好幾天才處理，在手機（375）與桌機都會看。
- 限制：RC-716 四點；項目數量與順序不變、不得 filter；只動 frontend；不得暗示即時；不得有建議語氣；標籤要短（事件列是 `text-xs` 一行）。

## 清查一：`observed` 實際會帶的全部鍵（`backend/app/alerts/`）
`observed` 只有三個產生點，型別為 `dict[str, float | str | None]`（`engine.py:233,281,349`；`models.py:266`）。共 11 個鍵（RC-716 主案已處理 `close`，剩 10 個，與 PM 所說「其餘 10 個」吻合）：

| 事件類型 | 鍵 | 值的來源與型別 | 位置 |
|---|---|---|---|
| 價格門檻（price_above／below） | `close` | 最新一根日線收盤價，數字 | `engine.py:234` |
| | `threshold` | 規則設定的門檻，數字 | `engine.py:235` |
| | `currency` | 幣別代碼字串（如 TWD）或 null | `engine.py:236`，值源 `snapshot.py:162` |
| | `bar_as_of` | 最新日線的日期，ISO 字串（YYYY-MM-DD） | `engine.py:237`，值源 `snapshot.py:165`（`latest.date.isoformat()`） |
| 訊號條件（signal_condition） | `field` | 欄位路徑字串，如 `rsi14.last` | `engine.py:282` |
| | `value` | 該欄位的數值（左邊） | `engine.py:283` |
| | `op` | 比較運算代碼：gt、gte、lt、lte、eq、ne、abs_gt、abs_lt | `engine.py:284`，集合見 `advice/engine.py:124-133` |
| | `compared_to` | 被比較的「數值」（規則比的是固定值或另一欄位，兩種情況這裡都是數字，不含另一欄位的名稱） | `engine.py:285`，邏輯 `:267-275` |
| | `signals_as_of` | 同一個 `snapshot.as_of`，ISO 日期字串 | `engine.py:286` |
| 風險上限（risk_limit_breach） | `violated_limit_ids` | 被觸發的上限 id，用「、」串成一個字串 | `engine.py:350` |
| | `violated_count` | 被觸發的條數，數字（以 float 存，如 2.0） | `engine.py:351` |

補充：
- 上限沒被觸發時回傳空 `{}`（`engine.py:328`），且不寫事件，所以事件列不會看到空的 `observed`；`ObservedValues` 對空物件已回 null（`PendingAlertsPanel.tsx:9`）。
- `violated_limit_ids` 的 id 只會是這五個（`limits.py:75-81`）：`single_position_weight`、`sector_weight`、`gross_exposure`、`per_trade_loss`、`kelly_fraction`。
- `field` 的值是使用者在欄位選單選的路徑，選單有 19 個（`format.ts:460-480`）；舊規則可能還有三個已不可評估的欄位（`alertFields.ts:21-25`）。
- 前端其他地方沒有消費 `observed` 的點：Grep `frontend/app`（排除測試）只有 `PendingAlertsPanel.tsx:6,7,8,45` 與無關的 `RiskGauge.tsx`、`entryObservation.ts`。
- 舊事件（資料庫裡更早寫入的）可能有不同鍵：我沒有查證，所以未知鍵必須退回顯示原鍵名，不能丟掉（也不得 filter）。

## 清查二：既有中文標籤（優先沿用）
| 要標的東西 | 既有標籤 | 出處 |
|---|---|---|
| `op` 的值 | 大於（>）、大於等於（≥）、小於（<）、小於等於（≤）、等於（=）、不等於（≠）、絕對值大於（\|x\|>）、絕對值小於（\|x\|<） | `format.ts:396-405`，取用函式 `comparisonOpLabel` `:411`；渲染後呈現「大於（&gt;）」見 `alertFieldEvaluability.test.ts:248,319` |
| `field` 的值 | 例如 `rsi14.last` → 「14 日 RSI 最新值」、`close` → 「最新收盤價」等 19 個 | `format.ts:460-480`，取用函式 `signalFieldLabel` `:493`；測試 `alertFieldEvaluability.test.ts:131` |
| `field` 的舊值 | beta.value → 相對指標的 beta；position.weight → 此標的佔投資組合比重；position.unrealized_pnl_pct → 此部位未實現損益率 | `alertFields.ts:35-39`（已併入 `signalFieldLabel`） |
| `violated_limit_ids` 的值 | 單一標的佔比上限、單一產業佔比上限、總曝險上限、單筆最大可承受虧損、分數 Kelly 部位上限 | `format.ts:432-439`，函式 `limitSelectorLabel` `:445`；後端同名 `limits.py:92-97` |
| `close` 的鍵 | 最新收盤價 | `format.ts:461`；後端 message 也這樣寫 `engine.py:230` |
| `threshold` 的鍵 | 沒有 UI 標籤；後端 message 用「設定的門檻」（`engine.py:231`），其他處有「價格高於門檻」（`format.ts:417`）、「門檻價格」（`alertRuleForm.ts:107`） | 沿用 message 的詞 |
| `currency` 的鍵 | 「幣別」 | `EditPositionModal.tsx:65` |
| 資料日期的說法 | 「資料日期 {日期}（日線收盤，非即時）」；「資料截至 {日期}」 | `DataStatusBadge.tsx:17-19`；`oneLinerWording.ts:53`、`BacktestReportView.tsx:350`、`entryObservationWording.ts:89` |
| 觸發時間 | 卡片右上角 `formatDateTime(event.triggered_at)`，沒有標籤 | `PendingAlertsPanel.tsx:42` |
| 完全沒有既有標籤 | `field`、`value`、`op`、`compared_to` 的鍵；`violated_limit_ids`、`violated_count` 的鍵；`bar_as_of`、`signals_as_of` 的鍵；`currency` 的值（代碼） | 以下起草 |

一個順帶的發現（不在本案範圍）：訊號條件的後端 message 本身印出原始運算代碼，「符合設定的條件 gt 30」（`engine.py:278-280`）。事件列上方那一行會露出 `gt`，這是後端字面，前端改 `ObservedValues` 修不到，需另案（backend、需風控審）。請 PM 評估要不要登記。

## 三視角發想（第 2 步：標籤與文案類組合 Ogilvy＋Young＋Rubin）
- Ogilvy（核心提問：事實勝過形容詞；你會讓家人這樣讀嗎？）
  - O1：每個日期標籤自帶「這是哪一種日期」：「資料日期（日線，非即時）」。理由：讀者最容易犯的錯就是把日期當觸發時間，直接寫破。
  - O2：「最新收盤價」改成不含「最新」的說法，如「資料日收盤價」，讓價格與日期綁在一起。
  - O3：值也用白話：`gt` 顯示成既有的「大於（>）」。
- Young（舊元素新組合：全部用公司已用過的詞）
  - Y1：價格門檻事件的 4 個標籤全部借既有詞：最新收盤價、設定的門檻、幣別、資料日期（日線，非即時）（來自 `DataStatusBadge.tsx:18` 的核可句式）。
  - Y2：`violated_limit_ids` 的每個 id 逐一換成 `limitSelectorLabel`，用原本的「、」連接。
  - Y3：日期標籤沿用 `entryObservationWording.ts:89` 的「資料截至」。
- Rubin（減法：還能拿掉什麼？）
  - R1：兩個日期鍵只留一種說法，不在標籤上區分「日線」與「指標」。
  - R2：把「（日線，非即時）」拿掉，只留「資料日期」。
  - R3：不新造任何詞，缺的標籤只用既有詞組出。

## Braintrust 互評（只給問題，不給解法）
- O1 ← Rubin：兩個日期都帶一長串括號，一行 `text-xs` 裡會把重點擠到看不見，手機換行後日期值離標籤太遠。← Young：括號內容是否和 `DataStatusBadge` 核可句逐字一致？不一致就算新字面，要整個重審。
- O2（資料日收盤價）← Young：這是新詞，不在既有清單，後端 message 同一張卡仍寫「最新收盤價」，兩處用詞不一致。← Rubin：「資料日」這三個字讀者要停下來想一下。
- O3 ← Rubin：沒問題，值的標籤是 RC-716 第 2 點的底線，不是亮點。
- Y1 ← Ogilvy：用既有詞確實安全，但「最新收盤價」在事件列的誤讀問題原封不動留著（RC-716 第 4 點沒被回答）。← Rubin：「設定的門檻」在 `observed` 那行與上面 message 重複，兩行讀起來像同一句講兩次。
- Y2 ← Ogilvy：id 轉標籤後，使用者仍分不出哪一條是 `violated_count` 計的。← Rubin：「觸發的上限」與「觸發的上限數量」兩個標籤太像，擠在一起像打錯字。
- Y3 ← Ogilvy：「資料截至」放在鍵位置時讀起來像整頁的截止時間，不像這個事件的日期；而且「截至」會讓人想到「現在」。
- R1 ← Ogilvy：兩個日期是不同鍵、不同事件類型，標籤相同沒問題；但若後端日後讓兩個日期分開（資料更新時間不同），標籤就說錯話。← Young：同意風險，但目前兩者同源（`engine.py:237,286` 都是 `snapshot.as_of`）。
- R2 ← Ogilvy：拿掉「非即時」就退回到 RC-716 第 1 點要避免的狀態（不暗示即時 ≠ 明講不是即時）。這個減法不通過。
- R3 ← Ogilvy：`value`、`compared_to` 這類標籤用既有詞組不出來，只能新寫。

## 最終提案（全部字面待風控定稿）

### 主案：鍵與值全中文化，日期自帶「非即時」，收盤價改和日期綁在一起
鍵標籤（`ObservedValues` 套用，順序與分隔 `: `、「　」不變）：

| 鍵 | 標籤（待風控定稿） | 來源 | 對 RC-716 的對照 |
|---|---|---|---|
| `close` | 資料日收盤價 | 新詞（改自既有「最新收盤價」） | 第 4 點：去掉「最新」，與日期綁定，見下 |
| `threshold` | 設定的門檻 | 既有，`engine.py:231` | 第 2 點不涉及 |
| `currency` | 幣別 | 既有，`EditPositionModal.tsx:65` | — |
| `bar_as_of` | 資料日期（日線，非即時） | 改自 `DataStatusBadge.tsx:18` | 第 1 點：「資料日期」＝資料的日子，不同於右上角的觸發時間；「非即時」明講；日期值本身照印 |
| `signals_as_of` | 指標資料日期（日線，非即時） | 同上 | 第 1 點，同上；「指標」說明這是指標計算用的資料日 |
| `field` | 判斷欄位 | 新詞 | — |
| `value` | 該欄位數值 | 新詞（刻意不用「目前」，避免暗示即時） | 第 1 點精神：不暗示即時 |
| `op` | 比較方式 | 新詞 | — |
| `compared_to` | 比較對象數值 | 新詞 | — |
| `violated_limit_ids` | 觸發的上限 | 新詞，與 message「觸發風險上限」（`engine.py:331`）同詞 | — |
| `violated_count` | 觸發的上限數量 | 新詞 | — |

值標籤（RC-716 第 2 點）：
- `op` → `comparisonOpLabel`（大於（>）等，`format.ts:411`）。
- `field` → `signalFieldLabel`（`format.ts:493`），例如 `rsi14.last` → 14 日 RSI 最新值。
- `violated_limit_ids` → 以「、」切開，逐個走 `limitSelectorLabel`（`format.ts:445`），再用「、」接回。
- 日期值、數字值、幣別代碼：照原值（我不替「TWD」另造「新台幣」，沒有既有標籤，造詞反而多一個要審的新字面）；null 仍顯示「—」。
- 未知鍵或未知值（舊事件、未來新增）：退回顯示原字串，不丟棄、不 filter。

價格門檻事件畫面示意（待風控定稿）：
```
資料日收盤價: 605　設定的門檻: 600　幣別: TWD　資料日期（日線，非即時）: 2026-11-24
```
訊號條件事件示意：
```
判斷欄位: 14 日 RSI 最新值　該欄位數值: 28.4　比較方式: 小於（<）　比較對象數值: 30　指標資料日期（日線，非即時）: 2026-11-24
```
風險上限事件示意：
```
觸發的上限: 單一標的佔比上限、總曝險上限　觸發的上限數量: 2
```

RC-716 四點逐條對照：
1. 日期留在畫面：兩個日期鍵都在，數量與順序不變；標籤「資料日期」與右上角無標籤的 `formatDateTime(triggered_at)` 用詞明顯不同；「（日線，非即時）」明講不是即時。通過。限制：標籤很長，手機要換行（`<p>` 本來就會換行），請 qa-e2e 在 375 確認日期值沒被擠到看不見。
2. 值也有標籤：`op`、`field`、`violated_limit_ids` 三種工程值都走既有表（大於（>）、14 日 RSI 最新值、上限名稱）；其餘值是數字、日期、幣別代碼。通過。
3. 拿掉重複值：本案不拿，所以不觸發版面審。若 PM 日後想拿掉 `close`／`threshold`／`currency`，前提是 `bar_as_of`、`signals_as_of` 仍在畫面，並另送風控。我不建議在這個案子裡做：減法容易引出「和 message 比對」的需求，而 message 沒有寫日期（`engine.py:229-232,277-280`），這一行是唯一的資料日期。
4. 最新收盤價被讀成現價：見下一段。

### 第 4 點：「最新收盤價」被讀成現價，方案比較
- 問題的實質：`close` 是「評估當下那一根日線的收盤價」，`snapshot.as_of` 是它的日期（`snapshot.py:165`）；事件放了幾天後，畫面上的「最新收盤價」就不是當下最新。
- 方案 1（主案採用）：事件列上的 `close` 改標「資料日收盤價」，價格與同列的資料日期綁在同一個說法。優點：不再主張「最新」，且只動標籤字面，不動順序。風險：新詞要審；與上方 message（後端寫「最新收盤價」，`engine.py:230`）用詞不同，兩行並排時需讀者自己對起來。
- 方案 2（備案）：`close` 維持「最新收盤價」（RC-716 主案已核准、與 message 一致），只靠日期標籤的「（日線，非即時）」負責澄清。優點：零新詞，最小改動。風險：「最新」兩字仍在，問題只被後面的日期標籤部分緩解；日期在整行最後面，讀者沒讀到就會誤讀。
- 方案 3（不採用）：把資料日期移到最前面或換行。優點：最直接。不採用原因：改變項目順序，違反 PM 驗收「順序不變」，屬版面調整，需另送風控與 qa-e2e。可以留給之後的版面案。
- 方案 4（不採用）：用 tooltip 說明。專案對 hover-only 有紀錄性的排斥（`alertFieldEvaluability.test.ts:166` 的測試名稱即「無 tooltip／sr-only／details」），手機上也看不到。
- 另一個建議（不在本案，給 PM）：右上角的 `triggered_at`（`PendingAlertsPanel.tsx:42`）沒有任何標籤。若加「觸發時間」就能和「資料日期」成對，更清楚；這是版面字面改動，需另案。

### 備案：只改鍵名與值，不碰 `close` 的說法
同主案，但 `close` 維持「最新收盤價」（方案 2），兩個日期標籤與其他標籤不變。何時用：風控認為「資料日收盤價」是新說法而不放行，或 PM 想先把「與 message 用詞一致」放第一位。

## 減法檢查（Rubin）
- 拿掉「判斷欄位」？不能：沒有它，「該欄位數值」會變成一個沒有主詞的數字。
- 拿掉「觸發的上限數量」？可以考慮：它和前一項的條數重複，且 message 已寫「第 X 條」。但這是減揭露，且 PM 驗收要求項目數量不變，不在本案做。
- 把兩個日期標籤的長括號縮短？風險是退回不明講非即時；不做。

## 風險與給風控的待決
1. 「（日線，非即時）」是否可沿用 `DataStatusBadge.tsx:18` 的「日線收盤，非即時」？我刻意不用「收盤」二字，因為我沒有查證最新一根日線在盤中會不會是未收盤的量；若風控確認可用，就逐字同 `priceDateTooltip`，用詞更一致。
2. `value` 的標籤我避開了「目前」，但 `field` 的值本身含「最新值」（`format.ts:462-468` 等既有標籤）。這是既有核可字面，我不動；日期標籤負責補足。
3. `signals_as_of` 與 `bar_as_of` 目前同源；若日後分開，標籤要重審。
4. 所有新詞（資料日收盤價、判斷欄位、該欄位數值、比較方式、比較對象數值、觸發的上限、觸發的上限數量、資料日期（日線，非即時）、指標資料日期（日線，非即時））都是新字面，待風控定稿。沒有任何一句是建議、預測或承諾性質。
5. 對 frontend-engineer 的測試建議（延續 RC-717 第 4 項）：用三種事件 fixture 斷言輸出逐字等於定稿、畫面不含 `rsi14.last`、`gt`、`violated_limit_ids`、`bar_as_of` 等原始字串；斷言項目數與順序不變；斷言未知鍵與未知值仍會顯示（防止被 filter）；把標籤改回舊字測試會紅。
6. 不確定且需交 frontend-engineer 確認：`limitSelectorLabel` 的參數型別是 `LimitSelector`（含 `any`，`format.ts:432-445`），傳入字串時要處理型別與未知 id 的退回邏輯，這是實作細節，我沒有改碼。

---

## 我讀過的檔案與行號
- `work/dispatch/2026-11-25-前端減字另案登記-product-manager.md` 全檔
- `work/reviews/2026-11-25-前端減字三項逐字審RC712至RC718-風控.md` 全檔
- `.claude/skills/creative-masters/SKILL.md` 全檔；`references/masters.md` 全檔
- `apps/stock-desk/frontend/app/components/PendingAlertsPanel.tsx` 全檔（1-58）
- `apps/stock-desk/frontend/app/settings/SettingsForm.tsx` 90-154、455-469
- `apps/stock-desk/frontend/app/lib/format.ts` 385-510
- `apps/stock-desk/frontend/app/lib/alertFields.ts` 全檔
- `apps/stock-desk/frontend/app/components/DataStatusBadge.tsx` 1-30
- `apps/stock-desk/backend/app/alerts/engine.py` 180-365
- `apps/stock-desk/backend/app/alerts/snapshot.py` 150-175
- `apps/stock-desk/backend/app/advice/limits.py` 73-97
- `apps/stock-desk/backend/app/advice/engine.py` 122-135
- Grep（只看命中行）：`settings/migrations.py`（0.15／0.10）、`alerts/`（observed）、`frontend/app`（0.15、signalFieldLabel 等、幣別／資料日期／資料截至、門檻、observed）、`advice/limits.py`（預設值與範圍）、`backend/app`（`bar_as_of`、`violated_limit_ids`、`LIMIT_IDS`、`COMPARISON_OPS`）

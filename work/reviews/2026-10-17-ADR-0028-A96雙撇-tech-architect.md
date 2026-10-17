# ADR-0028 A-96″ 與 ADR-0027 A-96″ 另開 commit 條文（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0028 A-96″（K-1～K-16 條文化）與 ADR-0027 A-96″ 另開 commit 條文（tech-architect，唯讀）

## 一、結論

**K-1～K-16 都已寫成可直接套用的條文。整體方向是「不變＋收緊」，沒有任何一處放寬。** 以下 6 項超出風控條件或需要風控過目，已在條文內標〔待風控確認〕或〔超出條件〕，第五節逐項列出：

1. **`/api/leverage` 的歸類（K-14，必回送）：結論是納入 `BARS_DERIVED_BLOCKS`。** 專章確實會渲染由 `load_bars` 列算出的數字和日期，例如持有交易日數、曆日數、資料截至日、實際報酬。依據見第四節。
   - 條文因此多了四處，全部標〔待風控確認〕：
     - 第 1 點 v1 涵蓋範圍加上 leverage；
     - `BARS_DERIVED_BLOCKS` 加 `LeverageChapterView`；
     - CS-4 的 grep 範圍加 `app/leverage`；
     - CST-11 加 leverage 一格。
2. **觸發條件採 K-14 (i)：每個區塊依自己取用的 envelope 觸發。** 不採 (ii) 整頁聯集。比較見第二節 (3) 之前的小表。
3. **K-8 的結構性質加了一個前提：「該列也在同一次 `market_session_evidence` 讀取結果內」。** 測試的定義域因此變窄，可能被讀成放寬，所以回送。
4. **技術分析區段的 bars 日期讀取點掛在 `PriceChart` 底下。** 這樣 K-2 的「每個讀取點都要歸類」和機械核對第 3 點的「恰好這些項目」才能同時成立。這屬於解讀，回送知會。
5. **兩處 `<details>` 位置的落法：**
   - 建議卡本身收在 `<details>` 裡（`page.tsx` L537-578），揭露改放在 `<details>` 之前、同一個 `<section>` 內；
   - 頁尾兩組依 K-1 字面放在組內。頁尾區本身是 `<details>`（`PageFooterDisclosures.tsx` L62），這是唯一允許揭露落在 `<details>` 內的地方，而且不取代主視圖的揭露。
6. **風控條件沒涵蓋的 4 個缺口，我沒有寫進條文**，附上可直接套用的建議文字，請風控裁定（第五節 G-1～G-4）。最重要的是 G-1：signals、advice、leverage 的「資料截至」日期呈現，不在 K-3 的範圍內。

**K-1 和 K-15 點名的元件與 builder 都已在原始碼確認存在：**

| 名稱 | 檔案:行號 |
|---|---|
| `PriceChart` | `PriceChart.tsx:39`；K 棒在 L75-86 |
| `buildTechOneLiner` | `lib/oneLinerWording.ts:23`；呼叫點 `page.tsx:393-398` |
| `buildKeyLevelsFooterItems` | `KeyLevelsPanel.tsx:556-585`；L572 `buildBasisClose`、L583 `buildFooterSample`；呼叫點 `page.tsx:171` |
| `buildEntryFooterItems` | `lib/entryObservationWording.ts:141`；呼叫點 `page.tsx:175` |
| `KeyLevelsPanel` | `KeyLevelsPanel.tsx:365`；L380 呼叫 `computeKeyLevels` |
| `EntryObservationPanel` | `EntryObservationPanel.tsx:92` |
| `DecisionCard` | `DecisionCard.tsx:505`；L282-290 呼叫 `computeKeyLevels` |
| `IndicatorOverviewChipsRow` | `TechnicalIndicatorsPanel.tsx:168` |
| `TechnicalIndicatorsPanel` | `TechnicalIndicatorsPanel.tsx:624` |
| `OperationSummaryPanel` | `OperationSummaryPanel.tsx:62` |
| `AdviceCardView` | `AdviceCardView.tsx:111` |
| `PriceUnitBadge` | `PriceUnitBadge.tsx:68`；只做幣別檢查，L55-61 |
| `tvExchangeHint` | `page.tsx:126`，經 `lib/tradingViewSymbol.ts:71`，只讀 `data.source` |
| `computeKeyLevels` | `lib/keyLevels.ts:99`；`closeDate` 取最後一列，L107 |

(以上元件檔案都在 `apps/stock-desk/frontend/app/position/[symbol]/` 下，`lib/` 指 `apps/stock-desk/frontend/app/lib/`。)

**定位基準的限制：** 我沒有跑 git，所以沒有確認 commit b3401bd。
- 工作目錄的 ADR-0028 檔頭到 r3″ 為止，沒有 CS-26 以後的條文，和「A-96 套用前」一致。下面的行號都以工作目錄為準。
- 工作目錄的 ADR-0027 還沒套用 r3，檔內查無 A-75。第三節的定位依 r3 提案（A-75 → D-7.3、A-77 → D-8.1）、r3′ R3-11 和 r3″ RC′-5 的文字推定。

## 二、ADR-0028 條文（基準 b3401bd）

「＞」後面是給 tech-writer 的條文。A-96′ 沒有落過檔，所以它的中間版文字不進修訂紀錄。

### (1) 檔頭：L9「r3″ 更正」之後加一行
> - A-96″／A-97′ 修訂：2026-10-17，依 tech-architect ADR-0028 A-96″（D-6 第 13 點、CS-4 補充、CS-26、CS-27、CST-10～CST-12；風控 2026-10-17 A-96′ 單項確認 K-1～K-16）。A-96″ 為不變＋收緊，A-97′ 為收緊。`/api/leverage` 的歸類待風控確認。

### (2) D-6：第 12 點（L209）之後新增第 13 點（K-6、K-8）
> 13. （A-96″）個股詳細頁有下列幾類數字和日期，都出自同一個 loader（`load_bars`）讀進的日線，而且都不讀 `valuation_state`：
>     - 前端以 `/api/bars` 的列計算或直接呈現的：
>       - 關鍵價位，以及關鍵價位面板的停損與目標參考；
>       - 六項觀察條件；
>       - 操作卡（`DecisionCard`）的收盤、停損、停利；
>       - K 線圖（`PriceChart`），會把每一列直接畫成 K 棒；
>       - 技術分析結論句（取最後一列收盤）；
>       - 頁尾「關鍵價位參考」與「六項觀察條件」兩組（收盤、日期、根數）。
>     - 後端以各端點自己載入的列計算的：
>       - 指標（`/api/signals`）；
>       - 操作摘要與建議卡（`/api/advice`）；
>       - 槓桿專章的持有期間與報酬拆解（`/api/leverage`，只有持股才有），〔K-14 歸類待風控確認〕。
>     - 資料列有日期異常時，照樣進入這些計算。本 ADR 不改變計算，只要求揭露（CS-26）。
>     - 這同時適用於持股與「確認未持有」的標的。非持股沒有 `build_summary` 列；CS-26 第 1 點的逐列標記落地之前，非持股完全沒有日期異常的檢查。
>     - **涵蓋限制**：逐列標記只抓得到日曆判定為非交易日的列；observed／weekday_assumed basis 下的平日休市列不會被標記（同第 1 點）。
>     - 要不要在資料層剔除異常列，屬於第 10 點「寫入側品質閘門另案」，本點不處理。

### (3) CS-4（L288）：原句一字不改，句末之後加子項（K-5）
> - （A-96″，澄清，方向不變）CS-4 只約束上列的後端計算模組。前端顯示層可以讀 `valuation_state`，以及 CS-26 的逐列 `date_anomaly` 標記與 envelope 的 `date_anomaly_rows`、`anomaly_valid_until`，但只能用來做同區塊揭露，不得改變任何計算或計算的輸入。
>   - 這句只是澄清現行範圍，不得被讀成禁止日後改採「附原因、不渲染」的 fail-closed 做法。那屬於顯示面變更，要另外送風控。
> - （A-96″，收緊）**grep 範圍擴大**：
>   - 被檢查的字串：`row_date_anomaly`、`date_anomaly`、`date_anomaly_rows`、`anomaly_valid_until`。
>   - 禁止範圍是上列模組的**計算 package**，不得呼叫或讀取這些字串：
>     - 現存的是 `app/advice`、`app/alerts`、`app/kelly`、`app/playbook`、`app/signals`；
>     - limits、outlook、plan、forecast，以落地時的 package 路徑為準；
>     - 另加 `app/leverage`〔隨 K-14 歸類，待風控確認〕。
>   - 這是落實 CS-26 第 4 點「計算不變」。
> - **envelope 組裝層例外（K-5）**：
>   - 除了 `close_state.py` 內 D-4 狀態機自己的呼叫之外，只有 `app/api/{bars,signals,advice,leverage}.py` 可以呼叫 `row_date_anomaly`。
>   - 呼叫時機只能在該端點的計算完成之後，用途只限附加標記。
>   - 其他 `app/api/*.py` 和任何計算 package 都不得呼叫（grep）。
> - **「計算不變」性質測試**：適用 `/api/bars`、`/api/signals`、`/api/advice`，以及 `/api/leverage`〔待風控確認〕。
>   - 同一份 `load_bars` 輸入跑兩次：(a) 正常組裝；(b) 用 stub 把 `row_date_anomaly` 換成永遠回 None。
>   - 除了 `date_anomaly`、`date_anomaly_rows`、`anomaly_valid_until` 三個欄位，兩次的回應 payload 必須逐位相同。
>   - 用 spy 斷言 `row_date_anomaly` 的第一次呼叫，晚於該端點的計算函式回傳；計算函式的簽章不接受任何異常標記參數。

### (4) CS-25（L337）之後新增 CS-26

方案比較（K-14 的觸發條件）：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) 每個區塊依自己的 envelope（採用） | 揭露在「本區塊」層級屬實；1200 日的 leverage 窗口裡有一筆舊週末列，不會讓整頁都出現揭露 | 要維護一張區塊對應來源的表 | 表漏列會少揭露 → 用 AST 測試「來源 ⊇ 實際取用」來釘住，判斷不了的一律列入全部來源 |
| (ii) 整頁取聯集 | 實作最簡單，結構上不可能少揭露 | 區塊字面只能指稱「本頁」，揭露疲乏 | 字面若寫成「本區塊」就不屬實 |

> - **CS-26**（A-96″，收緊；風控 2026-10-17 A-96 條件、A-96′ 單項確認 K-1～K-16）：個股詳細頁中由日線列衍生的數字與日期，在所用日線含日期異常列時，要在同一區塊揭露。
>   - 持股價格區塊在 `valuation_state = date_anomaly` 時渲染 LM-70（PM AC-B5a-10），依 CS-27。
>
> 1. **觸發條件：逐列標記，涵蓋實際進入計算的日線。**
>    - **判定函式**：`close_state.py` 抽出純函式 `row_date_anomaly(trade_date, *, D, phase, calendar) -> sub_reason | None`。
>      - D、phase 依 D-4「先定義」；D 不是交易日時，phase 為 None。calendar 是同一個 `SessionCalendar`。
>      - D-4 的 R2、R2′、R2″、R2‴ 改成呼叫它，輸出不變（CST-2 維持綠燈）。
>    - **判定規則**：
>      - `trade_date > D` → `future_date`；
>      - `trade_date == D`、D 是交易日，而且在 `pre_open` → `before_open`；
>      - `trade_date == D`、D 不是交易日 → basis＝official 時為 `official_conflict`，否則為 `not_a_session`；
>      - `trade_date < D`，而且 `is_session(trade_date)` 為 False → `unconfirmed_session`。
>        - 這一項對 `P < trade_date < D` 的列就是 R2‴；對 `trade_date < P`（含 P 為 None）的歷史列是延伸。
>        - D-4 本身仍只在 `price_date > P` 時套用 R2‴；`price_date < P` 或 P 為 None 時仍走 R6，估值狀態不變。
>      - 其他情形 → None。`trade_date == P` 時必為 None。
>    - **`/api/bars/{symbol}` 的欄位**：
>      - 每一列帶 `date_anomaly: Literal["future_date","before_open","official_conflict","not_a_session","unconfirmed_session"] | None`，由後端逐列計算；
>      - envelope 帶 `date_anomaly_rows: int`，等於標記非 None 的列數；
>      - envelope 帶 `anomaly_valid_until`：語意同 D-4 的 `state_valid_until`，前端資料層依它重新取得。
>    - **其他端點（K-14）**：
>      - 凡是個股頁取用、而且由 `load_bars` 的列計算出來的端點，envelope 都帶 `date_anomaly_rows: int` 與 `anomaly_valid_until`。
>      - 計算用同一個 `row_date_anomaly` 和同一個 calendar 建構函式，作用在**該端點自己載入的列**上，不得沿用 `/api/bars` 的結果。
>      - v1 涵蓋 `/api/signals`、`/api/advice`。
>      - `/api/leverage` 擬納入，只對 `load_bars` 載入的 ETF 列計算，不含 `load_index_bars` 的指數列〔K-14 歸類，待風控確認〕。
>      - 欄位為必填，前端型別不得標成 optional。
>    - **後端計算約束**（每個端點、每次請求）：
>      - 只讀一次時鐘，D 由 `now.astimezone(VS-1)` 取得（同 CS-3）。各端點現行的 `end = date.today()`（`bars.py:89`、`signals.py:94`、`advice.py:156`、`leverage.py:95`）不得當作 D；窗口本身不在本條範圍內。
>      - calendar 和 `build_summary` 用同一個建構函式（官方優先，退回 D-9 觀察日曆），不得另建。
>      - 最多一次 `market_session_evidence` 讀取，窗口依 D-9 第 6 點，用該端點所載各列日期的最小值代入。
>      - 只在 envelope 組裝層、計算完成之後附加（CS-4 例外）。
>    - **持股與非持股一體適用**：各端點都不讀 `valuation_state`，也不依是否持有分流。
>    - **回送條件（K-16）**：實作時出現以下任一情形，要回送風控，不得自行降級成只標 `> P`，也不得改由前端判定：
>      - 共用的 calendar 建構函式重用不了，要另建一份日曆；
>      - 每個請求的 evidence 讀取超過一次；
>      - 會違反 CS-1 或 CS-19 的可達性。
>    - **前端觸發（K-14 (i)）**：每個登記區塊依第 2 點表內登記的「觸發來源」觸發，不得只看 `/api/bars`。
>      - 來源 `bars`：傳入該區塊的 bars 陣列中，任一列 `date_anomaly != null`；
>      - 來源 `signals`、`advice`、`leverage`：該 envelope 的 `date_anomaly_rows > 0`。
>      - **前端不得另寫判定。**
>    - 前端揭露元件不得出現 `new Date(`、`Date.now`、時段常數，也不得 import `tradingCalendar.ts`（比照 CS-5）。
>
> 2. **揭露範圍與位置**
>    - **範圍**：以封閉清單 `BARS_DERIVED_BLOCKS: Readonly<Record<BlockId, readonly ("bars"|"signals"|"advice"|"leverage")[]>>` 登記，值是觸發來源：
>
>      | BlockId | 區塊 | 觸發來源 |
>      |---|---|---|
>      | `KeyLevelsPanel` | 關鍵價位，含停損與目標參考 | bars |
>      | `EntryObservationPanel` | 六項觀察條件 | bars、signals、advice |
>      | `DecisionCard` | 收盤、停損、停利格 | bars、advice、signals |
>      | `PriceChart` | K 線圖 | bars、signals（MA 疊圖） |
>      | `TechOneLiner` | 技術分析結論句（`buildTechOneLiner`） | bars |
>      | `KeyLevelsFooterGroup` | 頁尾「關鍵價位參考」（`buildKeyLevelsFooterItems`） | bars |
>      | `EntryFooterGroup` | 頁尾「六項觀察條件」（`buildEntryFooterItems`） | bars |
>      | `IndicatorOverviewChipsRow` | 指標概覽 chips | signals |
>      | `TechnicalIndicatorsPanel` | 指標卡 | signals |
>      | `OperationSummaryPanel` | 操作摘要 | advice |
>      | `AdviceCardView` | 建議卡 | advice |
>      | `LeverageChapterView` | 槓桿專章〔K-14 歸類，待風控確認〕 | leverage |
>
>    - **觸發來源的完整性**：每個區塊登記的來源，必須 ⊇ 它在 `page.tsx` 實際取用的 envelope。
>      - 以 AST 收集該區塊 JSX props 與 builder 參數中引用的 `bars`、`signals`、`advice`、`leverage` query 物件；
>      - `entryLevels` 視為 bars，`entryObservation` 視為 bars＋signals＋advice。
>      - 判斷不了的一律登記全部四個來源。
>    - **位置**：
>      - (a) 原則：每個區塊在同一區塊內渲染揭露，不收合、不放在 `<details>` 內，也不只用 hover 或 tooltip。
>      - (b) **技術分析區段**：`PriceChart`、`TechOneLiner`、`IndicatorOverviewChipsRow`、`TechnicalIndicatorsPanel` 共用一個主視圖揭露。
>        - 觸發來源是四者的聯集，也就是 bars ∪ signals；
>        - 位置在主視圖，緊鄰「資料截至 {MM-DD}」徽章，與圖、結論句同在一區，不在 `<details>` 內；
>        - `TechnicalIndicatorsPanel` 位在 `<details>` 內，它的揭露由這個主視圖揭露承擔，不必在 `<details>` 內重複。
>      - (c) **`AdviceCardView`**：卡片本身收在 `<details>` 內（CEO 2026-09-19）。揭露放在 `<details>` 之前、同一個 `<section>` 內，收合時也看得到。
>      - (d) **頁尾兩組**（`KeyLevelsFooterGroup`、`EntryFooterGroup`）：在各自組內帶揭露。頁尾區本身是 `<details>`，這是唯一允許揭露落在 `<details>` 內的地方，而且不取代 `KeyLevelsPanel`、`EntryObservationPanel` 在主視圖的揭露。
>      - (e) 其餘區塊依 (a)。
>    - **讀取點列舉（K-2）**：
>      - 範圍：`position/[symbol]/` 底下每一個讀取點，包括 `page.tsx` 的行內運算式和 builder 函式的參數。讀取點指：
>        - `bars.data.bars`；
>        - `bars.data.data.last_bar_date`、`bars.data.data.first_bar_date`；
>        - 所有名為 `bars` 的 prop。
>      - 每個讀取點都要歸入 `BARS_DERIVED_BLOCKS` 的某一項，或歸入封閉豁免清單 `BARS_NON_NUMERIC_USES`。沒有歸類，測試就失敗（AST 契約測試）。
>      - 技術分析區段的 bars 日期呈現（徽章與「共 N 根日線」）歸入 `PriceChart`，因為它們描述的是 K 線圖所畫的那份序列。
>      - `BARS_NON_NUMERIC_USES` 在 v1 只有兩項：
>        - `PriceUnitBadge`：只檢查幣別；
>        - `tvExchangeHint`：只讀 `source`。
>      - 要增列豁免，須修訂本條並送風控。
>    - **日期呈現（K-3）**：
>      - 頁面上每一處呈現 bars 日期的地方，該日期所對應的列（`bars` 陣列中 `date` 等於該值的列）如果 `date_anomaly != null`，就不得用正常資料日期的樣式呈現。
>        - 找不到對應列時，同樣不得用正常樣式〔超出條件，收緊〕。
>      - 涵蓋：
>        - compact 徽章；
>        - `DataMetaStatusBadge` 的 `lastBarDate`，主視圖與 `<details>` 內都算；
>        - 「共 N 根日線（first ~ last）」；
>        - `EntryObservationPanel` 的 `dataAsOfDates.bars`；
>        - 關鍵價位面板與頁尾的 `closeDate`。
>      - 「旁邊看得到同一揭露」以主視圖徽章為準。`<details>` 內的呈現不得用正常日期的樣式，但不必另外重複揭露。
>    - **不得反向保證（K-4）**：
>      - 沒有異常列時，不出現揭露；
>      - 也不得出現任何宣稱日期已經過檢查、或資料沒有問題的保證字面（例子見風控 2026-10-17 A-96′ 單項確認 K-4）。
>      - 理由：本條的檢查涵蓋不全（D-6 第 13 點涵蓋限制），這類保證不屬實。
>
> 3. **字面**：
>    - 交 creative-lead 起草、風控逐字審，不得有「仍可參考」之類的弱化語氣；
>    - `sub_reason` 不渲染成字面（同 D-4）；
>    - 字面核可之前，T1-17 不得合併（比照 D-5 末句）。
> 4. **計算不變**：揭露不改變任何計算，也不改變計算的輸入（CS-4 性質測試）。
> 5. **行動計畫鏈的前提**：本條的核可，以「ADR-0027 的行動計畫鏈不會吃進日期異常的價格」為前提〔推論〕。依據是 ADR-0027 FL-25 的 fixture，以及 A-75 (iv) 官方休市日的單一定義（ADR-0027 A-96″ 增補）。

### (5) CS-26 之後新增 CS-27（A-97′，照原文）
> - **CS-27**（A-97′，收緊；風控 2026-10-17 A-97 條件）：個股詳細頁顯示的持股價格與估值狀態，取自 `build_summary` 同一列的輸出（`valuation_state`，以及同一個 `price_date`），用和庫存頁同一個前端狀態元件、同一張 D-5 對應表呈現。
>   - 個股頁不得另外計算狀態，也不得用 bars 的 `last_bar_date` 代替 `reference_date`。
>   - 前端契約測試：同一檔在兩頁的價格、日期、字面 ID 逐位相同（PV-52、AC-B5a-10）。
>   - 非持股（沒有 `build_summary` 列）不顯示估值狀態，維持現行徽章。**這類標的的日期異常由 CS-26 第 1 點的逐列標記涵蓋，不得有沒有檢查的情形。** 契約測試：非持股、bars 含異常列時，渲染 CS-26 的揭露（AC-B5a-13）。
>   - （採用風控 suggested）同一頁上有多顆日期徽章時，每顆都要標明它指的是什麼，例如「日線資料截至」「估值價格日期」，不得出現兩個沒有說明的日期。字面交 creative-lead 起草、風控審。
> - 排入 T1-17，由 dev-lead（`app/api/*`、`close_state.py`）與 frontend-engineer 承接，qa-e2e 驗收。

### (6) 測試要求：CST-9（L378）之後、qa-e2e 行之前新增
> - **CST-10**（K-7、K-8）：`row_date_anomaly` 的性質測試。
>   - **與 D-4 一致**：在 P 不為 None 而且 `price_date > P`，或 `price_date ≥ D` 的輸入上，結果和 D-4 R2～R2‴ 的 `sub_reason` 逐位相同（P 為 None 而且 `price_date < D` 時，D-4 走 R6，不在比較範圍）。
>   - **全定義域**：對任意 `trade_date < D`，結果是 `unconfirmed_session`，若且唯若 `is_session(trade_date)` 為 False；否則為 None。`trade_date == P` 時必為 None。
>   - **結構性質**：`basis_for(trade_date) ≠ official`，而且該平日列也在同一次 `market_session_evidence` 讀取結果內時，`row_date_anomaly` 對該列必為 None〔前提句待風控確認，見第五節〕。
>   - 五個 `sub_reason` 各一個 fixture；歷史週末列（`< P`）→ `unconfirmed_session`。
> - **CST-11**（K-14、K-15）：每個端點的契約測試。
>   - `/api/bars`：
>     - 每一列都有 `date_anomaly` 欄；
>     - `date_anomaly_rows` 等於非 None 的列數；
>     - `anomaly_valid_until` 跨過 VS-2 時，`before_open` 消失。
>   - `/api/signals`、`/api/advice`：`date_anomaly_rows` 等於「對該端點自己載入的列逐列呼叫 `row_date_anomaly`」得到的非 None 列數。
>   - 每個端點、每次請求都只讀一次時鐘，最多一次 evidence 讀取（計數）。
>   - 同一序列在持股與非持股時，結果相同。
>   - `/api/leverage`〔待風控確認〕：計數只含 ETF 列。因為非持股回 404，持股與非持股相同一格不適用。
>   - （採用風控 suggested K-9）早於 D−400、落在證據窗口外的週末列，依週一至週五規則標成 `unconfirmed_session`。
> - **CST-12**：前端契約與 e2e。
>   - `BARS_DERIVED_BLOCKS` 的鍵恰好等於 CS-26 第 2 點的表；`BARS_NON_NUMERIC_USES` 恰好是兩項；
>   - 讀取點 AST 列舉：沒有歸類就失敗；
>   - 觸發來源 ⊇ 實際取用的 envelope（AST）；
>   - 每個來源各一個 fixture：只有該來源有異常時，登記了它的區塊都揭露；
>   - 揭露 DOM 不在 `<details>` 內，只有頁尾兩組例外，那兩組斷言揭露在組內；建議卡的揭露在 `<details>` 之外、同一 `<section>` 內；
>   - 主視圖徽章旁看得到揭露；K-3 列舉的每一處日期呈現，對應列異常時都不是正常樣式；
>   - 沒有異常時不出現揭露，全頁 DOM 也不含 K-4 所指的保證字面（掃描清單由 creative-lead 定稿後寫入測試）；
>   - 非持股含異常列時渲染揭露（CS-27）；
>   - 375 與 1280 寬度實機驗收（AC-B5a-13）。

### (7) 待決事項：在現有各段末尾加
> - **風控**（L404 之後）：（A-96″）`/api/leverage` 的歸類（K-14），以及 CST-10 結構性質的前提句，待確認。個股頁異常揭露與多徽章指涉標籤的字面逐字審。
> - **creative-lead**（新增一段）：CS-26 各區塊的異常揭露字面、CS-27 多徽章的指涉標籤。不得有「仍可參考」，也不得有 K-4 所指的保證字面。
> - **dev-lead**（新增一段）：確認 `load_bars` 回傳的列是否一定已寫入 `price_bars_cache`，也就是是否落在同一次 evidence 讀取內（CST-10 結構性質的前提）。若否，K-16 適用。

### (8) 未查證事項：末尾加
> - （A-96″）「非 official basis 下的平日列一定是 session」是依 D-9 第 4、5 點所做的推論，以 CST-10 釘住；`load_bars` 的列是否一定在 evidence 內，〔未查證〕。

### (9) 修訂紀錄：A-95（L636）之後新增
> ---
>
> > A-96″／A-97′（2026-10-17）依 tech-architect「ADR-0028 A-96″」套用（`work/reviews/2026-10-17-ADR-0028-A96雙撇-tech-architect.md`；風控 `work/reviews/2026-10-17-ADR-0028-A96A97單項確認-風控.md` K-1～K-16）。A-96″ 為不變＋收緊，A-97′ 為收緊，沒有放寬。CS-4 原句、CST-2 原文不變。A-96、A-96′ 的建議版沒有落過檔，不進本紀錄。
>
> **A-96″（D-6 第 13 點）**：新增，無被取代原文；見 §D-6。
> **A-96″（CS-4）**：原句不變，新增子項，無被取代原文；見 §對實作的約束 CS-4。
> **A-96″（CS-26）／A-97′（CS-27）**：新增，無被取代原文。
> **A-96″（CST-10～CST-12）**：新增，無被取代原文。
> **A-96″（檔頭、待決事項、未查證事項）**：新增，無被取代原文。

（轉存路徑如果和上面寫的不同，由 coordinator 改成實際路徑。）

## 三、ADR-0027 另開 commit 條文（以套用 r3＋r3′＋r3″ 之後的條號定位）

這個 commit 和 r3″ 分開；r3″ 的 17 點核對只看 r3″ commit 自己的 diff。

### (1) 檔頭：r3 那一行之後加一行（編修，方向不變）
> - A-96″ 增補：2026-10-17，依 ADR-0028 A-96″（FL-25 fixture；A-75 (iv) 官方休市日表的單一定義）。

### (2) §對實作的約束「銜接」FL-25：本文不變，句末之後加子項
> - （A-96″；依 ADR-0028 A-96′／A-96″，風控 2026-10-17 A-96 CS-26 第 4 點、A-96′ 單項確認 K-13）**fixture**：
>   - **(a)～(e) 五格**：構造 `build_summary` 的輸入，讓 `date_anomaly` 的五個 `sub_reason`（`future_date`、`before_open`、`official_conflict`、`not_a_session`、`unconfirmed_session`）各出現一次。plan 組合價位時，五格都期望價位缺席，並附 `MissingItem(code="E-PRICE-UNUSABLE", source_status="failed_check")`。
>   - plan 端不得讀 `valuation_state`（ADR-0028 CS-4）。fixture 只構造輸入，只斷言 plan 的輸出。
>   - **(f)(g) 週末對抗格**：(f) `not_a_session`（D 是週末，`price_date == D`）；(g) `unconfirmed_session`（`P < price_date < D`，該日是週末）。
>     - 兩格都構造「市場 DB 在該日有定案後的 ok run（`recorded_at ≥ final_after(TW, 該日)`），而且收盤相同」。
>     - 期望：依 A-75 (iv)，該日不成為候選 T；記 `inputs_not_ready`；寫入 `session_calendar_conflict`（`evidence = weekend`、`origin = candidate_t`）；plan 的輸出中沒有任何價位取自該日。
>   - **(h)(i) 官方休市日對抗格（K-13）**：(h) `official_conflict`（D 是官方休市的平日，`price_date == D`）；(i) `unconfirmed_session`（`P < price_date < D`，該日是官方休市的平日）。
>     - 構造方式同 (f)(g)。
>     - 期望同上，但 `evidence = official_holiday`。
>     - 官方休市日一律取自 A-75 (iv) 的單一定義函式。官方表接入之前（T1-13 前），用注入該函式的測試替身構造，不得在測試內另寫一份休市日清單。

（(f)(g) 的 `evidence`／`origin` 欄位是依 RC′-4 的 payload 補明確，屬於收緊方向。）

### (3) D-7.3 A-75：在 (iv) 處理段最後一點「(iv) 的『週末』部分受 A-77 第 9 項（F-8）約束…」之後加三句（K-10～K-12）
> - （A-96″，K-10，補定義（收緊））**官方休市日表的單一定義**：
>   - A-75 (iv) 與 A-77 第 2、4 項所稱的「已接入官方休市日表」，和 ADR-0028 `OfficialSessionCalendar`（T1-13）使用同一份來源、同一個函式定義，涵蓋年度也相同（ADR-0028 VS-5）。超出涵蓋年度時，兩邊同樣視為沒有官方休市日。
>   - 這個函式只定義一次，暫定為 `official_holidays(market, year) -> frozenset[date] | None`。None 表示該年不在涵蓋範圍內，或尚未接入。名稱與所在模組由 T1-13 決定，但要遵守 ADR-0028 CS-1、CS-19、CS-25 的 import 限制。
>   - A-75 (iv)、A-77、`OfficialSessionCalendar` 都只呼叫它；休市日清單不得出現第二份（grep／AST，比照 ADR-0028 CS-21、CS-25）。
> - （K-11）本句只統一休市日清單。A-75 (iv) 的週末部分不受官方日曆影響，仍依 A-77 第 9 項（F-8）處理；不得讀成官方日曆認定的週六補行交易日可以成為候選 T。
> - （K-12）休市日表的內容或涵蓋年度有任何改動，依 ADR-0028 CS-21 通則判斷方向，判斷不了的一律視為放寬。移除休市日或縮小涵蓋年度，必須送風控。

A-75、A-77 已定案的文字一字不改。

### (4) 修訂紀錄：r3／r3″ 區塊之後新增
> ---
>
> > A-96″ 增補（2026-10-17）依 ADR-0028 A-96′／A-96″；風控 2026-10-17 A-96′ 單項確認（K-10～K-13；`work/reviews/2026-10-17-ADR-0028-A96A97單項確認-風控.md`）。本 commit 和 r3″ 分開。
>
> **FL-25**：本文不變；新增 fixture (a)～(i)，無被取代原文；見 §對實作的約束 FL-25。方向：收緊。
> **A-75 (iv)**：新增 K-10～K-12 三句，無被取代原文；A-75、A-77 已定案的文字不改。方向：補定義（收緊）。這三句掛在既有的 A-75 底下，ADR-0027 的方向統計（33 條，19／2／9／1／2）不變。

**落地時點（給 coordinator，不寫進 ADR）**：K-10 寫進 ADR-0027 之前，T1-13 和 A-75 (iv) 官方休市日部分的實作 PR 都不得合併。

## 四、`/api/leverage` 歸類（回送風控）

**結論：納入 `BARS_DERIVED_BLOCKS`（`LeverageChapterView`，觸發來源是 leverage）。不列入 `BARS_NON_NUMERIC_USES`。**

**依據（〔事實〕，唯讀查證）：**
1. `app/api/leverage.py:97` 用 `load_bars` 載入 ETF 列（`loaded.bars`），L100 原樣交給 `build_leverage_chapter`。指數列另由 `load_index_bars` 載入（L98，`app/services/index.py:213`），不是 `load_bars`。
2. **持有期間區塊直接由 ETF 列算出**：`app/leverage/service.py:97-116`。
   - `holding_trading_days = len(held) - 1`，等於逐列計數；
   - `last_bar_date = held[-1]`；
   - `holding_days = (held[-1] - opened_at).days`。
   - 前端 `LeverageChapterView.tsx:101-104` 原樣渲染成「建倉日 … ～ 資料截至 {last_bar_date}，共 N 個交易日（M 曆日）」。
   - 所以一筆週末列會讓「交易日」多算一天；一筆 `future_date` 列會讓曆日數變大，「資料截至」也會顯示成異常日期。
3. **報酬拆解**：
   - `drag.last_bar_date` 取自完整的 ETF 列（`drag.py:183-186`、L326、L490），由 `LeverageChapterView.tsx:186-190` 渲染。
   - `actual_return` 等數字（`drag.py:416` 起，`LeverageChapterView.tsx:126-168`）是在 ETF 與指數同日期的 inner join 上計算（`drag.py:205-222`、L380）。異常 ETF 列只有在指數也有同一天的列時才會進入〔推論〕。
4. **侵蝕情境**只用指數列（`erosion.py:145-200`），不屬於 K-14 的「由 `load_bars` 列計算」。
5. 專章渲染在主視圖，不在 `<details>` 內（`page.tsx:582-584`）。頁尾的專章組只放靜態的 `chapter.disclosure`（`page.tsx:180-188`），不是由列衍生的數字。
6. 只有持股才有專章：沒有持倉時回 404（`leverage.py:88-93`）。所以 CST-11 的「持股與非持股相同」這一格不適用。

**這項歸類連帶的條文，全部標了〔待風控確認〕：**
- D-6 第 13 點的 leverage 子項；
- CS-4 的 grep 範圍加 `app/leverage`（收緊）；
- CS-4「計算不變」性質測試的 leverage 一格；
- CS-26 第 1 點 v1 涵蓋範圍；
- `BARS_DERIVED_BLOCKS` 的 `LeverageChapterView`；
- CST-11 的 leverage 一格。

**如果風控不採用：** 刪掉上列各處，再依 K-14 把 `LeverageChapterView` 列進 `BARS_NON_NUMERIC_USES`，並附風控的理由。這會動到 v1 豁免清單「只有兩項」的條件，所以要風控在裁定時一併說明。

## 五、方向統計與回送項

**ADR-0028**

| 條 | 方向 |
|---|---|
| A-96″ | 不變（D-6 第 13 點、CS-4 澄清）＋收緊（CS-4 grep 範圍、envelope 例外、性質測試，CS-26，CST-10～12） |
| A-97′ | 收緊（CS-27 照原文） |

**ADR-0027**：FL-25 fixture 為收緊；K-10～K-12 為補定義（收緊）。33 條統計 19／2／9／1／2 不變。

**超出條件或需風控過目（都不是放寬）：**
1. leverage 納入（第四節）——**必回送**。
2. CST-10 結構性質加了前提「該列在同一次 evidence 讀取內」。
   - 理由：`load_bars` 的列如果沒寫入快取，R 內的平日會成為 absent，被標成 `unconfirmed_session`，方向是多揭露。沒有這個前提，斷言本身可能不成立。
   - 這會縮小測試的定義域，可能被讀成放寬，所以回送。
   - 估值列取自快取，一定在 evidence 內〔推論〕，所以 FL-25 只需要週末和官方休市對抗格的依據不受影響。
3. 技術分析區段的日期讀取點歸入 `PriceChart`（解讀，知會）。
4. K-3「找不到對應列也不得用正常樣式」（收緊）。
5. 採用 K-9 suggested（收緊）。
6. 觸發條件選 (i)；`DecisionCard` 依 K-15 字面也登記 signals 來源（多揭露）。

**請風控裁定的缺口（沒有寫進條文，各附建議）：**
- **G-1｜K-3 只涵蓋 bars 日期。** 下列日期也出自 `load_bars` 的列，可能就是異常日期：
  - signals／advice 的「資料截至」：`OperationSummaryPanel.tsx:96-105`、`DecisionCard.tsx:374-383`、`AdviceCardView.tsx:111-114`、`page.tsx:290-301`、`page.tsx:430-440`、`TechnicalIndicatorsPanel.tsx:629`；
  - `EntryObservationPanel` 的 `dataAsOfDates.signals`／`advice`（`page.tsx:505-506`）；
  - 頁尾 `asOfStatement`（`lib/operationSummary.ts:281`、L411-413）；
  - 專章的兩個 `last_bar_date`。
  - 建議：各 envelope 加 `last_bar_date_anomaly: bool`，由同一個函式在該端點自己的最後一列上計算；K-3 擴到這些位置。
- **G-2｜指數列不在範圍內。** `load_index_bars` 的指數列（侵蝕情境，以及拆解的指數那一側）不在 K-14 範圍。是否另立指數端點的標記？指數的 market 可能是 US，要用該市場的 calendar。
- **G-3｜K-2 的讀取點種類不含 `bars.data.data.source` 和 meta 欄位。** 例如 `page.tsx:420` 的「資料來源：…」和 `status`、`staleness_minutes`。`tvExchangeHint` 列進豁免清單無害，但它實際的讀取種類（`data.source`）在列舉之外。如果要擴到所有 `bars.data.*`，就需要新增豁免，得修訂 CS-26。
- **G-4｜D-4 R6 對週末 `price_date < P` 的處理**：沿用風控的知會，日後另案評估。

**給 coordinator 的機械核對：**
- 第 3 點應讀成「表列 11 項，加上 `LeverageChapterView`〔待風控確認〕」。
- 第 8 點：K-4 句子刻意不引用保證字面原字串，ADR 內 grep 不到；「仍可參考」保留在 CS-26 第 3 點。

## 六、驗證與下一步

**查證範圍：**
- 風控單項確認全文；我的 A-96′ 原提案；
- ADR-0028 L1-430、L540-637；
- ADR-0027 FL-19／FL-25 附近，以及修訂紀錄結構；
- r3 提案 A-75～A-79；r3′ R3-11。
- 原始碼：
  - backend：`app/api/leverage.py` 全文、`app/api/bars.py` L40-107、`app/leverage/service.py` L75-254、`drag.py`／`erosion.py`／`signals.py`／`advice.py` 的 grep 結果、`services/market.py` L147-199；
  - frontend：`page.tsx` 全文、`LeverageChapterView.tsx` 全文、`KeyLevelsPanel.tsx` L550-585、`DecisionCard.tsx` L270-299、`PriceChart.tsx` L70-89、`PriceUnitBadge.tsx` L36-81，以及各元件、builder、`closeDate`、`<details>` 的 grep 結果。

**沒做的事：** 沒有跑 git、程式或測試；沒有讀 `.env` 或 `*.db`；沒有改任何檔案。這是唯讀的架構文件，Codex 不適用。

**下一步：**
1. 風控：裁定第四節（leverage）、第五節第 2、3 項，以及 G-1～G-4。
2. tech-writer：分別套用 ADR-0028 A-96″ 與 ADR-0027 A-96″ 增補兩個 commit。leverage 相關各處保留〔待風控確認〕標記，等裁定後再定稿。
3. PM：AC-B5a-13 擴大範圍時，要和 CS-26 第 2 點的表一致（含 leverage 的暫定項）。
4. dev-lead：回覆待決的「`load_bars` 的列是否一定在 evidence 內」。
5. T1-13 負責人：K-10 落檔之前不得合併。

**相關檔案：**
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028-A96A97單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3雙撇併入RC與ADR-0028-A96A97修訂-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3prime補正-tech-architect.md
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/apps/stock-desk/backend/app/api/leverage.py
- /home/user/AICompany/apps/stock-desk/backend/app/leverage/service.py
- /home/user/AICompany/apps/stock-desk/backend/app/leverage/drag.py
- /home/user/AICompany/apps/stock-desk/backend/app/leverage/erosion.py
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/page.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/LeverageChapterView.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/KeyLevelsPanel.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/DecisionCard.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/PriceChart.tsx
- /home/user/AICompany/apps/stock-desk/frontend/app/components/PageFooterDisclosures.tsx

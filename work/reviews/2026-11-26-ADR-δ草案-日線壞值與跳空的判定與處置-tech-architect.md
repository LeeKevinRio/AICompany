# ADR-δ 草案：日線壞值與跳空的判定與處置（proposed）

- 審查者：tech-architect
- 日期：2026-11-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. ADR-δ 的 proposed 草案已寫完，全文在下方「發現」的程式碼區塊裡，可以直接轉存到 `work/`。編號照指示暫用「ADR-δ」，狀態寫 `proposed`。
2. 草案的核心決定有五項：
   - **判準以本 ADR 條文為準**：壞值規則 V-1～V-6，跳空規則 G-1～G-5，版本代號 `bars-verdict-v1`。
     - 壞值（V）由前後端各自實作，以一份共用的 golden fixture 加雙邊契約測試對齊。
     - 跳空（G）在登記後只由後端判定，前端改成只讀。
   - **open 納入判準**：要求有限、大於 0，而且落在 [low, high] 之間；等號放行，一字板才不會被誤判。同時把 volume 和重複日期也納入。
   - **後端建議卡**：我建議「逐欄位拒算」（下稱 S2）。日線有壞值時，整批算出來的欄位一律記 skipped 並附原因，只有完全不靠歷史日線的欄位保留。另一個方案是「整張卡回 `insufficient_data`」（S1）。這兩案的取捨要請 CEO 決定。
   - **`data_completeness`**：定義不改，加註說明；`_as_float` 改成會過濾 NaN 和 Infinity；OHLC 檢查改用 `quality.py` 的同一套定義。
   - **前端過渡期**：決策卡標題和操作摘要採「非防禦型的動作標籤改成無判定說明，防禦型保留並加註」（下稱 T2）。建議卡的命中數和完整度那一行，在日線不可用時都不顯示。入場閘門拿掉 `levels !== null` 這個代理判斷，改由共用判定新增的 `"empty"` 狀態直接表示 0 根。
3. 有一項限制在任務說明裡沒提到，起草時發現的：`apps/stock-desk/shared/` 依 RC-721 Q-4 只能放類 0 的檔，所以**登記前不能把 golden fixture 放進 `shared/`**。過渡期先放在 frontend 底下，登記後再搬到 `shared/`。
4. 需要 CEO 決定的只有一題，就是 S1 和 S2 的取捨，白話選項寫在草案第 8 節。其餘未決事項都交給風控、PM、data-engineer 和 dev-lead。

## 發現

### 起草時另外看到、會影響實作的事實

- `quality._check_ohlc_consistency`（`quality.py:167-189`）是有被呼叫的，呼叫它的是 `check_price_bars`（`:61`）。不過 `api/` 底下 grep `check_price_bars|quality` 是 0 筆，這和 dev-lead 說的「沒有接到任何地方」一致。
- 它的條件比「high<low」寬，也包含 open 和 close 是否落在 [low, high]。比較用嚴格不等號，所以等號會放行。草案的 V-3 直接採用這套定義。
- 引擎在 `completeness < 0.5` 而且沒有任何規則命中時，會轉成 `insufficient_data`（`engine.py:372-375`）。所以就算採 S2，在個別情形下，持有卡仍可能落在完整度 ≥ 0.5、0 條命中的 `hold`。
  - 草案因此要求引擎在日線不可用時，關掉「沒命中就是續抱」這條路徑（Decision 3.4）。這點要送風控判定。
- `isBarsGateOpen` 的代理註解（`entryObservation.ts:69-72`）受 RC-882 第 1 點保護。草案要拿掉這個代理，所以把「換成直接訊號的新註解」列為送風控的項目，不是直接刪掉。

### ADR-δ 草案全文

```markdown
# ADR-δ：stock-desk 日線壞值與跳空的判定與處置

- 狀態：proposed
- 日期：2026-11-26
- 決策者：tech-architect（草案）；risk-compliance-officer（第 5 節「前端過渡期」與 RC-882、RC-883 各點的審查，有否決權）；CEO（第 8 節第 1 題，以及本 ADR 轉 accepted）
- 編號：暫用「ADR-δ」，由 tech-writer 落檔時取號，不佔用既有編號。建議檔名 slug：`stock-desk-日線壞值與跳空的判定與處置`
- 適用範圍：只限 product/stock-desk。後端路徑相對於 `apps/stock-desk/backend/`，前端路徑相對於 `apps/stock-desk/frontend/`
- 題名變更：quant 前置定義原題為「公司行動偵測與排除」。本 ADR 把「壞值」和「跳空（疑似公司行動）」合成一套判準。公司行動在回測、事件研究、排程台的處置，不在本 ADR 範圍（見 Decision 7）
- 來源（皆在 `work/` 下）：
  - [Q] `reviews/2026-11-25-ADR-δ-ε前置定義-quant.md`
  - [DL] `reviews/2026-11-26-後端日線壞值行為調查-RC872-RC883-dev-lead.md`
  - [RC88x] `reviews/2026-11-26-PR-β-risk-gate-RC880至RC885-風控.md`
  - [RC87x] `reviews/2026-11-26-PR-α-risk-gate-RC870至RC876-風控.md`
  - [CEO] `dispatch/2026-11-26-CEO決策-高優先問題排程維持原本順序.md`
- 字面規則：本檔只定**行為**（顯示、不顯示、附加說明）和識別名，**不定字面**。字面以 W-n 佔位，由 creative-lead 起草、風控逐字審

## Context（背景）

1. **現況是兩套判準，而且彼此不一致。**
   - 前端：`evaluateDailyBarsUsability`（`app/lib/dailyBarsUsability.ts:41-47`）只要整批中任一根的 close、high、low 非有限或 ≤ 0，就判整批不可用。它不檢查 open、high<low、volume 和日期。
   - 後端：`/api/advice` 只檢查最新一根的收盤價（`app/api/advice.py:207`，`usable_price`），其他日線照常拿去算指標（`:208`）。
   - 後端對 0、負價、high<low 都不擋（[DL]）。`quality._check_ohlc_consistency`（`app/data/quality.py:167-189`）有寫，但它所在的 `check_price_bars` 沒有接進 `api/`。
2. **放心型誤導已經實測重現**（[DL] §2）：
   - 持有、乾淨資料的卡是 `reduce`／high／12/12/2/1.0。
   - 只把第 -30 根的收盤價改成 0，就變成 `hold`／medium／12/12/0/1.0。前端因此顯示「續抱參考」「命中 0 條」「資料完整度 100.00%」。
   - 原因有三：
     - `data_completeness`（`engine.py:364`）只看規則輸入欄位是否為 None；
     - `_as_float`（`context.py:97-101`）不濾 NaN 和 Infinity，和該檔 `:10-12` 的註解不一致；
     - 0 條命中且完整度 ≥ 0.5 時走 `hold`（`engine.py:366-375`），完整度 ≥ 0.8 時信心是 medium（`:292-294`）。
3. **跳空（疑似公司行動）**：[Q] δ-1 定義了門檻 c = 10% + 1%，比較用嚴格大於，套用在相鄰兩根的收盤對收盤。[Q] δ-5 建議偵測到之後逐欄位拒算，記為 skipped 並附原因，不得當成 quiet，也不截斷視窗。
4. **風控要求本 ADR 明定的事**：
   - RC-882 第 4～6 點：gap 時動能、量能、規則三條怎麼處理；入場閘門不得靠 `levels` 為 null 順帶決定；`computeKeyLevels` 的 null 契約任何變動都要送風控。
   - RC-883 第 1 點：決策卡、操作摘要、建議卡 summary 的命中數、建議卡的資料完整度那一節，要逐一決定怎麼處理。
   - RC-883 第 3 點：dev-lead 已證實壞值下完整度會維持 100%。所以前端過渡的期限提前，要在下一支動到 `AdviceCardView.tsx` 或 `page.tsx` 的 PR 之前完成。
5. **時程限制**：
   - CEO 決定（[CEO]）四項 high 問題的後端修正排在正式登記之後；dev-lead 不開登記前的 `app/` 修正。
   - ADR-0030 補充六附記四（RC-721 Q-1～Q-8）：
     - 允許登記前的差異落在 `apps/stock-desk/frontend/`（類 A，不得是 `.py`，也不得是 Q-3 列的檔名）。
     - `apps/stock-desk/` 底下、但不在 backend 或 frontend 底下的路徑，只能屬於類 0（Q-4）。所以 **`apps/stock-desk/shared/` 在登記前不得新增檔案**。
6. **範圍限制**（[Q] 範圍聲明，照錄要點）：
   - 不及於 `code_digest` 範圍：`app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py`，以及被遞移 import 的 `app/data/interface.py`、`app/data/freshness.py`、`app/advice/banned_phrases.py`。
   - 新模組不得 import `app.dirdef`、`app.sectors`，也不得被 `code_digest` 範圍 import。
   - 偵測器不得寫在 `PriceBar` 或 `data/freshness.py`。

## Options（選項比較）

### A. 判準的唯一來源放哪一層

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A1 只有後端判定，前端只讀 | 只有一份實作 | 要等登記後才做得了；`/api/bars` 和 `/api/advice` 是不同請求，各自要帶判定 | 過渡期前端沒有東西可用 |
| A2 規格寫在 ADR，前後端各自實作，以 golden fixture 加雙邊契約測試對齊 | 前端現在就能做；後端修好之後，前端仍保留一層防線（RC-865 第 1 點） | 兩份實作 | 漂移，靠契約測試擋 |
| A3 只做前端 | 改動最少 | 後端 API 照樣輸出放心型結論，警示等其他消費端沒有保護 | 根因不除 |
| **A4（採用）：壞值用 A2；跳空在過渡期用 A2，登記後改成 A1** | 壞值有雙層防線；跳空需要的除權息事件和交易日曆只有後端有，所以登記後收斂成單一來源 | 過渡期前端的跳空判斷比較粗（只用原始價，g = 1） | 過渡期偽陽性比較多，方向是 fail-closed |

### B. 日線不可用時，後端建議卡回什麼

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| S1 整張卡回 `insufficient_data`，`advice=None` | 最簡單；沿用既有的「沒有價格」路徑和前端 `no_price` 分支 | 一根很久以前的壞值，會讓不靠歷史日線的防守訊號（例如依成本算的停損）一併消失 | 偽陽性時收起防守訊號（[Q] δ-4） |
| **S2（建議）逐欄位拒算** | 符合 ADR-0021 的 skipped 語意；不靠歷史的欄位照常評估；完整度會自然下降，不會再出現 100% | 引擎和 api 層的改動比較多；要另外關掉「0 條命中就是 hold」那條路徑 | 規則語意有變動，要風控判定是否需要升 `rules_version` |
| S3 卡片維持 ok，只加註 | 改動最小 | 後端仍會輸出 `hold`／medium／100% | 放心型誤導留在 API 裡；只能當過渡期的現況，不能當終態 |

### C. `data_completeness`

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **D1（採用）定義不改；受影響的欄位改回 None，完整度自然下降；evaluation 加註判定狀態** | 定義穩定；不混入日線品質 | 數字的意思仍然是「輸入欄位可得的比例」 | 低 |
| D2 重新定義成「乘上品質係數」 | 一個數字表達兩件事 | 混淆兩種概念，既有測試和揭露都要改 | 語意漂移 |
| D3 定義不改，也不把欄位改回 None，只另加品質欄位 | 改動小 | 壞資料下仍會顯示 100% | RC-883 指出的放心型誤導 |

### D. 前端過渡期，決策卡標題與操作摘要

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| T1 保留動作標籤，附加說明（決策卡現在的 PR-α 做法） | 改動最小 | 「續抱參考」仍是標題 | 正好是 [DL] 證實會被壞值翻出來的放心型標籤 |
| **T2（建議）非防禦型標籤改成無判定說明；防禦型保留並加註** | 壓掉放心型和建構型標籤；可能真實的防守訊號仍然看得到 | 依方向分流，比較複雜；過渡期留下的防禦型標籤也可能來自壞值 | 不必要的減碼，用加註緩解 |
| T3 所有標籤都改成無判定說明 | 對稱、最簡單 | 真實的防守訊號也會被收起 | 偽陽性時收起防守訊號 |

### E. 入場閘門怎麼表示「0 根」（RC-882 第 6 點三案）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (i) 閘門多收一個 bar 數參數，由 page 傳入 | 共用函式的契約不變 | `page.tsx` 要多傳一個值，閘門有兩個輸入 | 呼叫端可能漏傳 |
| **(ii)（建議）共用判定新增 `"empty"` 狀態** | 判定本身就能回答「能不能用」，代理可以拿掉；技術分析區也能收掉「ok 但 0 根」那一項 | 觸及 RC-872 第 3 點（空陣列的契約），要重送風控 | 低：後端已證實 ok ⇔ 至少一根（[DL] §1） |
| (iii) 擴大 `page.tsx` 的範圍 | — | 判斷散落在頁面 | 違反 RC-767「一個判定」的精神 |

### F. open 要不要納入

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| O1 不納入（現況） | 不變 | K 線圖會畫 open；後端 quality 已經把 open 列入一致性檢查，兩邊不同 | 判準不一致 |
| O2 只要求有限且 > 0 | 簡單 | 抓不到 open 落在區間外 | 中 |
| **O3（採用）有限、> 0，而且落在 [low, high]，等號放行** | 和 `quality._check_ohlc_consistency` 同一套定義 | 如果某個資料源的 open 常落在區間外，會多拒算 | 偽陽性率要由 data-engineer 查證 |

## Decision（決策）

### 1. 單一判準 `bars-verdict-v1`

**1.1 結果狀態**（前後端同名）：
- `usable`
- `unusable`：附原因列表，每筆含 date、field、code
- `gap`：附疑似跳空的相鄰對列表，依日期遞增；每筆含 (d₋, d)、觀測變動、是否有已知事件。字面要用的 `{d}`、`{x}`、`{k}` 依 RC-767 方案 P，取最近一筆
- `empty`：0 根

**1.2 判定順序固定**（RC-767 方案 P）：
1. 先看是否 0 根，是就判 `empty`；
2. 再對整批套用 V 規則，任一根違反就判 `unusable`；
3. 都通過，而且市場是 TW，才套用 G 規則；有疑似跳空就判 `gap`；
4. 否則判 `usable`。
- 非 TW 市場永遠不判 `gap`。

**1.3 欄位層級規則 V（整批判定，任一根違反就是 `unusable`；絕不丟掉壞的那幾根，改用剩下的計算）**：
- **V-1**：close、high、low、open 都必須是有限數。前端用 `Number.parseFloat` 後檢查 `Number.isFinite`；後端除了 pydantic 的 finite 檢查之外，判定模組自己再檢查一次。
- **V-2**：close、high、low、open 都必須 > 0。
- **V-3**：high ≥ low，open 和 close 都落在 [low, high]，**等號放行**（一字漲跌停時 O = H = L = C）。這條和 `quality._check_ohlc_consistency` 是同一套定義。
- **V-4**：volume 必須是有限整數，且 ≥ 0；volume = 0 放行。
- **V-5**：日期嚴格遞增，不得重複。
- **V-6（明定不納入）**：未來日期、幣別不符、資料新鮮度。前兩項已由資料層閘門處理（ADR-0024，以及 `data/service.py` 的未收盤濾除），新鮮度由 ADR-0040 處理，都不在本判準內。

**1.4 跳空規則 G（只限 TW）**：
- **G-1 常數**：c = 10% + 1%，比較用嚴格大於。新模組自己定義這個常數，不 import `app.sectors` 或 `portfolio/price_change.py`；用測試交叉釘住它和 ADR-0016 F7、`sectors/definition.py:69-70` 相等。
- **G-2 精確比較**：對每一對相鄰 bar (d₋, d)，判定 |P(d) − P(d₋)| × 100 > 11 × P(d₋)。用十進位精確運算，後端用 `Decimal`，前端用 BigInt 縮放整數，不經二進位浮點。
- **G-3 過渡期前端版**：只用原始收盤價，g 一律取 1，也就是門檻最嚴；不處理除權息事件。
- **G-4 登記後後端版**：照 [Q] δ-1 第 1～4 步：
  - 已知除權息日而且因子可用，比較參考價；
  - 因子不可用，直接判為疑似；
  - 兩根之間隔了 g ≥ 2 個交易日，用 (1 ± c)^g 換算上下界；
  - 交易日曆查不到時，g 取 1。
  - 交易日曆用 `services/market.py` 的 `TradingCalendarSource`，不直接 import `session_calendar`。
- **G-5 適用與例外**：照 [Q] δ-3。查證之前一律照常套用（fail-closed）。US 和 ^TWII 不適用。

**1.5 唯一來源與對齊方式**：
- 判準的規範來源就是本節條文。
- 參考實作：登記後由後端新模組實作（見 2.1）。
- 前端唯一的實作是 `app/lib/dailyBarsUsability.ts`（RC-767），不得在其他前端檔案另寫一份。
- 對齊方式有四項：
  - (a) **golden fixture**：一份 JSON 表，每筆是（bars、market、預期狀態與原因）。
    - 過渡期放在 `apps/stock-desk/frontend/app/lib/__tests__/fixtures/`，屬類 A。登記前**不得**放進 `apps/stock-desk/shared/`（RC-721 Q-4）。
    - 登記後搬到 `apps/stock-desk/shared/`，前後端都讀同一份檔，並釘住 SHA。
  - (b) 兩端都匯出常數 `BARS_VERDICT_VERSION = "bars-verdict-v1"`，契約測試斷言兩者相等。
  - (c) 判準任何一處變動，版本號就要升，golden fixture 也要同步更新，然後送風控。
  - (d) 登記後，前端最終採用的判定 = 前端 V 判定與後端判定兩者中較嚴的那個。嚴格程度由嚴到寬是 `unusable` ＞ `gap` ＞ `usable`；`gap` 只採後端的結果。

**1.6 `computeKeyLevels` 的 null 契約**（RC-882）：
- 現況：只在空陣列和 `unusable` 兩種情形回 null（`keyLevels.ts:103,108`）。
- 本 ADR 之後：判定狀態 ∈ {`empty`、`unusable`、`gap`} 時回 null，其他狀態絕不回 null。`gap` 這一項是依 RC-804「跳空時關鍵價位不計算」。
- 這個變動、日後任何再變動、以及 V 規則的擴大（因為擴大會改變 `unusable` 的範圍），都要送風控（RC-882 第 2 點）。
- 契約由第 6 節的 F-T2 鎖住。

### 2. 後端處置（登記後才實作，依 [CEO]）

**2.1 判定模組**：
- 新套件，名稱暫定 `app/barverdict/`，提供 `evaluate_daily_bars(bars, *, market, events, calendar) -> DailyBarsVerdict`。
- 不得寫在 `PriceBar`、`data/freshness.py`，不得 import `app.dirdef`、`app.sectors`，不得被 `code_digest` 範圍 import。
- V-3 呼叫 `quality.py` 公開化之後的 OHLC 一致性函式。這個函式就是現有的 `_check_ohlc_consistency`，改名公開，判斷邏輯不變。後端因此只有一份 OHLC 定義。
- `quality.py` 維持「只偵測、只回報」（`quality.py:1-7`），要不要拒算由判定模組決定。
- **前提**：dev-lead 先只讀確認 `app/data/quality.py` 不在 `code_digest` 的遞移 import 內。如果在，就改由判定模組自己實作 V-3，`quality.py` 不動，再用測試交叉比對兩者結果相同。

**2.2 套用位置**：
- 在 api 層呼叫端套用：`api/bars.py`、`api/signals.py`、`api/advice.py`，以及另一支 PR 的 `alerts/snapshot.py`。
- 由同一個函式 `apply_bars_verdict(signals, verdict)` 把受影響的欄位改成 None 並附原因代號。
- **不改 `compute_signals` 本身**。理由：`app/signals/*` 是否在 `code_digest` 的遞移 import 內，尚未查證；在呼叫端套用，不論查證結果如何都成立。

**2.3 各 endpoint**：
- `/api/bars`：維持「`status == "ok"` ⇔ 至少一根」（RC-872）。信封新增 `bars_verdict` 欄位，只是附加，不改原有欄位。壞值時照樣回傳原始 bars，因為這是事實資料，由前端決定怎麼呈現。
- `/api/signals`：信封帶同一個 `bars_verdict`。`unusable` 時，各技術與風險指標回 `insufficient_data` 並附原因代號；`gap` 時依 2.5 逐欄位處理。
- `/api/advice`：在同一批 `loaded.bars` 上算判定，不重新載入，也不讀 `/api/bars` 的結果。回應帶 `bars_verdict`。既有的 F-1 最新收盤價守門（`advice.py:207`）保留。

**2.4 建議卡狀態（S1 或 S2，由 CEO 決定，見第 8 節第 1 題）**。tech-architect 建議 S2，內容如下：
1. `unusable`：整批算出來的欄位一律改成 None，原因代號 `daily_bars_unusable`。「整批算出來的欄位」指 `FIELD_LABELS` 裡除了 `position.*` 以外的全部欄位。
2. `close` 只在最新一根本身通過全部 V 規則時保留；否則改成 None，走既有的 `insufficient_data` 路徑（`advice.py:234-258`）。
3. cap 4 的 ATR 跟著改成 None，走 ADR-0023 的 not_evaluable 路徑。
4. **引擎閘門**：`build_advice` 新增 keyword-only 而且必填的 `bars_verdict` 參數。判定不是 `usable` 時：
   - 「0 條命中、完整度 ≥ 0.5 → `hold`」那條路徑改成 `insufficient_data`；
   - 0 條命中時，不得輸出 medium 信心；
   - 有防禦型規則命中時，照現有的優先順序輸出。
   - 這點會改變引擎的行為，要風控判定是否需要依 ADR-0004 升 `rules_version`。
5. 被跳過的規則，原因代號是 `daily_bars_unusable` 或 `corporate_action_suspected`，不得併入「缺少輸入欄位」。原因的字面是 W-9，交 creative 起草、風控審。
- 如果 CEO 選 S1：判定不是 `usable` 時，整張卡回 `insufficient_data`、`advice=None`，`reason` 帶判定的原因代號；第 2～5 點不適用。

**2.5 跳空的逐欄位時距 H_f**：
- 只有可疑的那一對落在某欄位的有效時距內，該欄位才拒算。不截斷視窗，也不只用事件之後的子視窗。
- H_f 照 [Q] δ-5：
  - 簡單平均類用視窗長度；
  - 回撤用整個觀察視窗；
  - Wilder 平滑和 EMA 用「種子長度 + ⌈ln(0.001) ÷ ln(1 − α)⌉」。
- 數值等 dev-lead 用測試驗證「殘餘影響 < 1%」之後，以本 ADR 補充凍結。凍結之前，遞迴平滑類一律視為受影響。
- `unusable` 不做逐欄位處理，一律整批拒算。理由：壞值代表這批資料不可靠，而且這也是前端已核可的立場（`dailyBarsUsability.ts:11`）。

**2.6 `data_completeness`**：
- 採 D1：定義仍是 evaluated ÷ total（`engine.py:364,445`），不改。
- `evaluation` 新增 `bars_verdict_status`，讓前端不必自己推斷。
- 2.4 或 S1 會把受影響的欄位改成 None，所以壞值下完整度不可能再是 1.0。

**2.7 `_as_float`**：
- 非有限值（NaN、±Infinity）一律回 None（`context.py:97-101`），讓實作和 `:10-12` 的註解一致。
- `signals/frame.py:97-102` 的 `last_defined` 本 ADR 不改。它是否在 `code_digest` 範圍內未查證；有 `_as_float` 這層過濾就足夠了。

### 3. 動能、量能、規則三類的跳空處理（RC-882）

| 類別 | 過渡期（前端，判定 = `gap`） | 登記後（後端判定 + H_f） |
|---|---|---|
| 動能（RSI） | 一律 unavailable。由 `gap` 直接關閉閘門，不得靠 `levels` 為 null 順帶發生 | RSI 只在可疑的那一對落在 H_RSI 內時拒算，指標狀態帶 `corporate_action_suspected`；前端依指標狀態呈現 |
| 量能（volume z） | 一律 unavailable，做法同上 | 可疑的那一對落在 20 根內時拒算；已知的配股或分割日也拒算（股數改變） |
| 規則（防禦型沒有命中） | 一律 unavailable，做法同上 | 規則條件依 `evaluation.skipped_rules` 判斷：只要有任何防禦型規則因為 `daily_bars_unusable` 或 `corporate_action_suspected` 被跳過，就是 unavailable，不得判為成立。方向從卡片的 `direction_weights` 讀，不自行推導 |

- 理由：過渡期的後端用含有跳空的整段原始序列算出 RSI、z 值和規則，前端無從得知哪些欄位受到影響，只能整體關閉。
- 這是 RC-882 第 6 點要求的「明確決定」：閘門在 `gap` 時關閉的依據是本表，不是 `computeKeyLevels` 的實作。

### 4. 入場閘門與共用判定的介面（過渡期）

- 採 E(ii)：`DailyBarsUsability` 新增 `empty`、`gap` 兩種狀態。
- `isBarsGateOpen` 改成只讀判定本身，也就是 `status === "usable"`，**拿掉 `levels` 這個參數**。
- `entryObservation.ts:69-72` 的代理註解換成「`empty` 是直接訊號、`gap` 依 ADR-δ 第 3 節關閉」的新註解。這是 RC-882 第 1 點的變更，要送風控。
- `dailyBarsUsability.ts:13-19` 的註解要更新：
  - 註明入場閘門刻意採用允許清單（RC-882 第 6 點）；
  - `:37-40` 的空陣列契約改寫成 `empty` 狀態，要重送風控（RC-872 第 3 點）。
- 共用函式的簽名改成 `evaluateDailyBarsUsability(bars, market)`。

### 5. 前端過渡期（登記前可做，只動 `apps/stock-desk/frontend/`，符合附記四類 A）

**5.1 呈現矩陣**。表中「不變」表示和現在的 head 逐字、逐結構相同。

| 呈現面 | `usable` | `unusable` | `gap` | `empty`／null（沒載入、錯誤、非 ok） |
|---|---|---|---|---|
| 技術分析區（`page.tsx`） | 不變 | 不變（RC-695 收起，加 `TECHNICAL_SECTION_NO_DATA_STATEMENT`） | K 線保留；指標數值、疊加線、指標卡、一句結論都不顯示；附 W-1（含 `{d}`、`{x}`） | null：不變；`empty`：比照 `unusable` 收起（結案 RC-872 第 2 點的追蹤項，要送風控確認既有句子可以沿用） |
| 關鍵價位（`KeyLevelsPanel`） | 不變 | 不變 | 不計算（RC-804），附 W-2 | 不變 |
| 進場觀察六條 | 不變 | 不變（PR-β） | 六條都是 unavailable；面板用 W-3 的 gap 版本，不得說「無法取得」（避開 RC-802 的回審條件） | 不變 |
| 決策卡標題 | 不變 | T2：卡片動作在 `direction_weights` 裡屬於 defensive，才保留標籤，加上現行第二行；其他情形（含方向未知）標題換成 W-4，第二行也改用和 W-4 對應的版本 | 同 `unusable`，說明改用 gap 版 | 不變（既有的 `no_price` 和長度檢查） |
| 操作摘要（`OperationSummaryPanel`） | 不變 | 同決策卡的 T2，另加 W-6。E-2 的「見上方操作摘要」指向的必須是有附說明的內容 | 同上，gap 版 | 不變 |
| 數量區間（任何顯示 `quantity_range` 的地方） | 不變 | 標題被換掉時，不顯示 | 同左 | 不變 |
| 建議卡 summary 的「命中 N 條」（`page.tsx:580` → `oneLinerWording.ts:36-38`） | 不變 | 不顯示命中數，改顯示 W-7 | 同左，gap 版 | 不變 |
| 建議卡 details 的評估那一行（`AdviceCardView.tsx:254-259`） | 不變 | 整行不顯示，包括規則總數、可評估、命中、資料完整度，改顯示 W-8；候選卡（最高 91.67%）同樣處理 | 同左，gap 版 | 不變 |
| 建議卡其餘內容（命中規則、反方論點、上限檢查、跳過清單） | 不變 | 零差異（殘留風險見 Consequences） | 零差異 | 不變 |

**5.2 動作方向的判斷**：
- 只從卡片自己的 `direction_weights[].actions` 讀，比照 `ruleDirection` 的做法，不自行推導。
- 卡片的 action 沒有出現在任何 defensive 項目裡，就視為非防禦型。例如無命中的 `hold`、被降級的 `hold`，都不會出現在 defensive 項目裡。這是 fail-closed。

**5.3 PR 切分**：
- **F-1**：5.1 表中 `unusable` 欄的四個建議面，加上數量區間。只用現有的 `usable`／`unusable` 判定。
  - 依 RC-883 第 3 點，F-1 必須是下一支動到 `AdviceCardView.tsx` 或 `page.tsx` 的 PR。
  - 決策卡的整卡快照（RC-874）要隨 F-1 一起進來，而且要在改動之前產生基準。
- **F-2**：V-3～V-5、`empty` 狀態、閘門改成直接訊號、RC-873 鎖、RC-882 第 3 點的契約鎖、golden fixture（放在 frontend 路徑）。
- **F-3（就是 PR-γ／H1）**：`gap` 狀態、5.1 表中 `gap` 欄的全部內容、(g) 的測試、`dailyBarsUsability.ts:17-18` 的註解更新。
- F-2 最晚要和 F-3 一起進來（RC-873、RC-882 第 3 點的期限）。

**5.4 預期會改的檔**（以讀到的引用為準，實作前由 frontend-engineer 用 grep 確認）：
- `app/lib/dailyBarsUsability.ts`、`keyLevels.ts`、`entryObservation.ts`、`entryObservationWording.ts`、`oneLinerWording.ts`、`decisionCardWording.ts`、`operationSummary.ts`
- `app/position/[symbol]/page.tsx`、`DecisionCard.tsx`、`OperationSummaryPanel.tsx`、`AdviceCardView.tsx`、`KeyLevelsPanel.tsx`
- 以及對應的測試

**5.5 必須零差異**：
- `app/lib/api.ts`、`queries.ts`、`types.ts`（API 型別要到登記後的 F-4 才改）、`ruleDirection.ts`、`indicatorBands.ts`
- `adviceWording.ts`：`HELD_ACTION_LABELS` 的字面不改。T2 是在呼叫端換掉標題，不是改標籤表
- `apps/stock-desk/shared/`、`apps/stock-desk/backend/`、任何 `.py`
- `__snapshots__/`：沒有風控核可，不得 `-u`（RC-874）

### 6. 測試

**6.1 dev-lead 列的 13 項（[DL]「下一步」），全部放在登記後的後端 PR**：

| # | 內容 | PR | 備註 |
|---|---|---|---|
| 1～3、5、6 | ok ⇔ 有日線、FRESH 加空陣列、無來源／被拒絕／區間外、PriceBar 的 finite 行為、快取 NaN 列 | B-1（先寫特性測試） | `data.status` 是否照抄，本 ADR 不改，只釘住現況。第 6 項少一根會變成 g = 2，在殘留風險裡揭露 |
| 4 | 最新收盤價為 0 時的不對稱 | B-1 先釘住現況，B-2 改成新的預期 | 新預期：`/api/bars` 是 ok 加 `bars_verdict=unusable`；`/api/advice` 是 `insufficient_data` |
| 7、11、13 | 完整度的定義、候選卡最高 11/12、「沒命中就是續抱」的來源 | B-1 釘住；B-2 依 2.4 第 4 點改寫第 13 項的預期 | 前端標籤的對應屬於 vitest（F-T7） |
| 8 | context 出現 NaN／Inf | B-2 | `_as_float` 修好之後，引用這些欄位的規則記 skipped |
| 9、10 | 持有卡由 reduce 翻成 hold；壞值位置 × 欄位的參數化，含 RC-883 第 3 點的兩項（較早一根 close = 0、最新一根 low = 0） | B-2 | 預期值依 CEO 選 S1 或 S2 定，不得出現 `hold`／medium／完整度 1.0 |
| 12 | 同一份資料下 `/api/bars` 和 `/api/advice` 的判定一致 | B-2 的目標測試（現在會紅） | 斷言兩個信封的 `bars_verdict` 相等 |

- 不在登記前加後端特性測試。附記四類 0 第四款雖然允許 `app/` 以外的測試，但這會加重 Q-2 的歸類負擔，也不符合 [CEO] 的意圖。
- 後端另外要有的測試：
  - golden fixture 的契約測試（登記後讀 `shared/` 那一份）；
  - G-1 常數和 F7、sectors 交叉相等；
  - OHLC 函式公開化前後，結果相同；
  - `apply_bars_verdict` 不改動 `compute_signals` 的輸出物件（不可變）；
  - H_f 逐欄位測試（B-4）；
  - 引擎在判定為 `usable` 時，結果和現況逐欄位相同（回歸鎖）。

**6.2 前端過渡 PR（vitest）**：
- **F-T1（RC-873）**：把 RC-808 的九個詞套用到 `dailyBarsUsability.ts` 所有匯出的字串常數，只掃常數值，不掃註解。
- **F-T2（RC-882 第 3 點）**：契約鎖。`computeKeyLevels` 回 null ⇔ 判定 ∈ {`empty`、`unusable`、`gap`}，用 golden fixture 逐筆斷言。
- **F-T3**：V 規則逐條各有正例和反例，含 `"NaN"`、`"Infinity"`、0、−1、high<low、open>high、volume −1、日期重複，以及 O = H = L = C 判為 `usable`。
- **F-T4**：G 規則。
  - 恰為 11% 不判 gap，11.01% 判 gap（字串價 `"100"`→`"111"`、`"111.01"`）；
  - 非 TW 永遠不判 gap；
  - 有壞值的批次判 `unusable`，不是 `gap`（判定順序）。
- **F-T5**：閘門。
  - `gap`、`empty`、`unusable`、null、undefined 和未知狀態都關閉；只有 `usable` 開啟；
  - 簽名裡沒有 `levels`；
  - 補 (g) 的 `gap` 案例（RC-882 第 6 點）；
  - 「ok 加 []」的案例（RC-872 第 1 點）。
- **F-T6**：前端所有 golden fixture 案例都通過；`BARS_VERDICT_VERSION` 的值固定。
- **F-T7**：5.1 矩陣逐格測試。fixture 包含：
  - dev-lead 第 9 項的持有 `hold`／medium／12/12/0/1.0；
  - 候選 `add`／12/11/1；
  - 持有 `reduce`（防禦型，標籤保留並加註）；
  - 被降級的 `hold`（方向未知，標題換掉）。
  - `usable` 時整卡逐字和現況相同。
- **F-T8**：RC-874 決策卡整卡快照，涵蓋四種狀態、日線正常。
- **e2e**：qa-e2e 實機驗收 375 和 1280 兩種寬度，涵蓋 5.1 每一欄。

### 7. 不在本 ADR 範圍

- **排程台**：ADR-0040 的 `is_usable` 簽名逐字固定（QB-5），engine 只有限定範圍的豁免（N172-C3、C-B11）。本判準要套用到排程台，必須另立 ADR 申請豁免。判準本身（第 1 節）適用。
- **回測、事件研究**：處置方式照 [Q] δ-5 的方向，另以本 ADR 的補充定案。
- **含息路徑**：交給 ADR-ε。G-4 第 1 步要用的因子定義，和 ADR-ε 共用 `dividends/models.py`。

### 8. 需要 CEO 決定（由 coordinator 依 RC-726 的格式另行轉送）

1. **某支股票過去的日線裡有一筆明顯錯誤的價格（例如某天收盤價是 0）時，個股頁的建議卡要怎麼處理？**
   - 選項一：整張卡都不出結論，只說資料不足。這樣最單純；代價是連不必看歷史就能判斷的提醒（例如依你的成本算出的停損提醒）也會一起收起來。
   - 選項二：凡是要用到歷史價格的判斷都不出，只保留不必看歷史就能判斷的提醒，並註明其他判斷因為資料有誤而沒有評估。這樣保留了一部分提醒；代價是做法比較複雜，而且卡片上會只剩少數幾條規則。
   - 兩個選項都不會再出現「沒有命中、資料完整度 100%」這種結果。

## Consequences（後果）

**好處**
- 前後端對「日線可不可用」只有一套規範，用 golden fixture 加版本號擋住漂移。
- 「壞資料卻顯示續抱參考、命中 0 條、完整度 100%」這條路徑，前端在登記前就能關掉，後端在登記後根除。
- 入場閘門不再依賴另一支函式的實作細節（RC-882 第 5 點）。
- `_as_float` 的實作和註解恢復一致；OHLC 檢查在後端只有一份定義。

**代價與壞處**
- **過渡期偽陽性**：前端的跳空判斷只用原始價、g = 1，又是整批判定。所以有一次分割或大額除息剛好遇上跌停，個股頁的關鍵價位、三條條件和四個建議面，就會被收起最長約一個回看視窗（約 540 天）。新上市股、國外成分 ETF、槓桿 ETF 的真實大幅波動也會觸發。要等登記後的 B-4 和 F-4 才會收斂成逐欄位處理。PM 要判斷這是否可以接受（[Q] 第 404 行）。
- **open 和 volume 納入（O3、V-4）會讓更多批次被判為不可用**。各資料源 open 落在區間外的頻率還沒查證，偏高的話，要用 `bars-verdict-v2` 放寬，送風控。
- **T2 依動作方向分流**：過渡期留下的防禦型標籤，也可能來自壞值，靠加註緩解。
- 建議卡 details 的其餘內容（命中規則清單等）在過渡期零差異，所以壞值下仍可能列出由壞值觸發的命中規則。這是殘留風險，風控可以擴大範圍。
- S2 要改引擎的閘門，可能牽動 `rules_version`（ADR-0004，待風控判定）。
- 快取跳過 NaN 列之後序列少一根，判定仍可能是 `usable`；G-4 的 g = 2 換算會放寬門檻。殘留漏判照 [Q] δ-4 揭露。

**約束（逐條可檢查，交給 qa-reviewer）**
- K-1：前端只有 `dailyBarsUsability.ts` 一份 V 和 G 的判定，其他前端檔案不得掃描 bar 的值。
- K-2：登記前任何 PR 的 diff 都不得含 `apps/stock-desk/backend/`、`apps/stock-desk/shared/` 或 `.py`。
- K-3：`isBarsGateOpen` 只收判定一個參數，而且是允許清單寫法。
- K-4：`computeKeyLevels` 的 null 條件 = {`empty`、`unusable`、`gap`}，由 F-T2 鎖住；變更要送風控。
- K-5：新的後端模組不 import `app.dirdef`、`app.sectors`、`app.data.session_calendar`，也不被 `code_digest` 範圍 import（用 import 圖測試）。
- K-6：`compute_signals` 零差異；判定只在 api 層呼叫端套用。
- K-7：G-1 的常數由測試交叉釘住，和 F7、sectors 相等；比較是十進位精確運算，用嚴格大於。
- K-8：`/api/bars` 維持 ok ⇔ 至少一根；`bars_verdict` 只是附加欄位。
- K-9：被跳過的規則用原因代號，不併入「缺少輸入欄位」；不得記為 quiet（ADR-0021）。
- K-10：5.5 列的檔案零差異；快照沒有風控核可不得 `-u`。

## 與既有 ADR 的關係

- **ADR-0030 補充六附記四**：
  - 不衝突。前端過渡期的 PR（F-1～F-3）屬於類 A；登記前不新增 `shared/` 檔，也不新增 `.py`。
  - 後端的 B 系列在登記之後才做，不影響 `code_digest`、`lockfile_sha256` 和 harness 雜湊。
- **ADR-0016 F7（accepted）**：
  - 不衝突，F7 不改。門檻數值和比較方向相同。
  - 套用方式不同：F7 把除權息日整列排除；本 ADR 在登記後改用參考價比較。理由見 [Q] δ-2。
  - F7 先量化 pct 再比較，造成的邊界差異可以忽略。
- **ADR-0040（accepted）**：
  - 兩者是不同軸。ADR-0040 的「可用」講的是資料新不新，指 `is_usable(status, source, is_within_ttl)`；本 ADR 的「可用」講的是值本身有沒有問題。
  - 本 ADR 不改 `is_usable`，不在它的簽名加參數，也不沿用 `is_usable` 這個名字。排程台要套用本判準時，另立 ADR（Decision 7）。
- **ADR-0021**：沿用 skipped 不得當成 quiet 的規定。
- **ADR-0023**：cap 4 的 ATR 為 None 時走 not_evaluable 路徑。
- **ADR-0004**：引擎閘門是否需要升版，待判定。
- **ADR-ε（proposed，同批）**：G-4 第 1 步和 ADR-ε 共用因子定義；兩份 ADR 各自決定。
- 以上若和 accepted ADR 有衝突，一律以 accepted ADR 為準。目前沒有發現衝突。

## 未決事項

- **CEO**：Decision 8 第 1 題（S1 或 S2）。
- **risk-compliance-officer**：
  - T1、T2、T3；
  - 技術分析區在 `gap` 時收起指標、在 `empty` 時收合（5.1）；
  - O3 和 V-4、V-5 擴大範圍（null 契約）；
  - `empty` 狀態（RC-872 第 3 點）；
  - 閘門註解改寫（RC-882 第 1 點）；
  - 引擎閘門和 `rules_version`；
  - W-1～W-9 的字面（交 creative-lead 起草）；
  - 建議卡其餘內容的殘留風險。
- **product-manager**：過渡期偽陽性可否接受；F-1～F-3 的排程登記。
- **data-engineer**：
  - 各資料源 OHLC（含 open）不一致的頻率；
  - `PriceBar` 是否驗證 volume ≥ 0；
  - [Q] ε-5 第 1、2、5、6 點（這是 G-4 和 G-5 轉 accepted 的前提）。
- **dev-lead**：
  - `quality.py` 和 `app/signals/*` 是否在 `code_digest` 的遞移 import 內；
  - H_f 的數值驗證；
  - S2 下 `default.yaml` 實際可評估的規則數。
- **tech-architect**：排程台的判準套用 ADR；回測和事件研究的補充。
```

## 驗證

**讀過的檔案**（都在 `/home/user/AICompany/` 底下）

- ADR：
  - `docs/adr/0001-record-architecture-decisions.md`，全文；
  - `docs/adr/0030-…最小記錄器.md`，第 653-677 行（第 6 點 (d)）、第 940-1049 行（補充七附記三之一、補充六附記四）；Grep 補充紀錄；
  - `docs/adr/0016-…fail-closed.md`，Grep F7（第 14、41、106、189、222、269、331、341 行）；
  - `docs/adr/0040-…可用.md`，第 1-80 行，另 Grep `is_usable`、Decision 12、N172-C3。
- 任務指定的四份 work 檔全文：`work/reviews/2026-11-25-ADR-δ-ε前置定義-quant.md`、`work/reviews/2026-11-26-後端日線壞值行為調查-RC872-RC883-dev-lead.md`、`work/reviews/2026-11-26-PR-β-risk-gate-RC880至RC885-風控.md`、`work/dispatch/2026-11-26-CEO決策-高優先問題排程維持原本順序.md`。
- 另外 Grep 了 `work/reviews/2026-11-26-PR-α-risk-gate-RC870至RC876-風控.md` 的 RC-872～RC-875 段落。這份不在必讀清單，因為任務要求補 RC-873 的鎖，所以補讀。
- 前端（主工作樹）：
  - `apps/stock-desk/frontend/app/lib/dailyBarsUsability.ts` 全文；
  - `apps/stock-desk/frontend/app/lib/keyLevels.ts` 全文；
  - `apps/stock-desk/frontend/app/lib/entryObservation.ts` 全文（PR-β 已在主工作樹，閘門在 `:76-78`，代理註解在 `:69-72`）。
- 後端：
  - `apps/stock-desk/backend/app/api/advice.py` 第 150-279 行；
  - `apps/stock-desk/backend/app/advice/context.py` 第 1-167 行；
  - `apps/stock-desk/backend/app/advice/engine.py` 第 1-60、155-454 行，另 Grep；
  - `apps/stock-desk/backend/app/api/bars.py` 全文；
  - `apps/stock-desk/backend/app/data/quality.py` 全文；
  - Grep `apps/stock-desk/backend/app/api/` 底下的 `check_price_bars|quality`，0 筆。

**遵守事項**
- 沒有讀 `.env*`，沒有碰 `backend/data/`。
- 沒有對 `apps/` 用 Glob `**` 或遞迴搜尋；只 Grep 了單一檔案，以及 `backend/app/api` 這一個具體目錄。
- 沒有寫任何檔案，也沒有執行指令。

**沒有查證的事項**
- `quality.py`、`app/signals/*` 是否在 `code_digest` 的遞移 import 內。草案因此寫成前提條件，而且規定判定在呼叫端套用。
- ADR-0004、0021、0023、0024 本文沒有重讀，只依其他文件的引用。
- RC-767 方案 P、RC-804、RC-865、RC-802 的原文沒有讀，依二手引用。`{k}` 的語意沒有確認。
- `OperationSummaryPanel.tsx`、`DecisionCard.tsx`、`AdviceCardView.tsx`、`page.tsx` 沒有讀，5.4 的檔案清單依引用推定。
- `PriceBar` 是否驗證 volume；`take_profit` 屬於哪個方向；`MIN_COMPLETENESS_FOR_ACTION` 的實際值，dev-lead 寫的是 0.5，我沒有讀到常數定義。

## 下一步

1. **coordinator**：
   - 把草案轉存到 `work/`，交 tech-writer 落檔 `docs/adr/` 並取號；
   - 依 RC-726 的格式，把第 8 節第 1 題送 CEO。
2. **risk-compliance-officer**：審第 5 節和「未決事項」列給風控的各項，特別是 T2、`empty` 狀態、閘門註解改寫、null 契約擴大。依 RC-883 第 3 點，F-1 的期限已經提前。
3. **creative-lead**：風控同意行為之後，起草 W-1～W-9。
4. **dev-lead**：只讀查證 `code_digest` 的 import 圖（`quality.py`、`app/signals/*`），結果回報 tech-architect。
5. **frontend-engineer**：風控核可之後，依序開 F-1 → F-2 → F-3。F-1 必須是下一支動到 `AdviceCardView.tsx` 或 `page.tsx` 的 PR。
6. **data-engineer**：查證 OHLC 和 open 的不一致頻率、volume 驗證，以及 [Q] ε-5 第 1、2、5、6 點。
7. **product-manager**：判斷過渡期偽陽性可否接受；登記 F 和 B 系列的排程。

**相關路徑**
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/dailyBarsUsability.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/keyLevels.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/entryObservation.ts
- /home/user/AICompany/apps/stock-desk/backend/app/api/advice.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/context.py
- /home/user/AICompany/apps/stock-desk/backend/app/advice/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/quality.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/bars.py
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/docs/adr/0016-stock-desk-持倉漲跌欄的計算基準與-fail-closed.md
- /home/user/AICompany/docs/adr/0040-stock-desk-排程台以交易日判定為最新的快取日線視為可用.md


# PRD：stock-desk 個股頁「資訊減負與白話導讀」

- 對應頁面：`apps/stock-desk/frontend/app/position/[symbol]/page.tsx` 及其子元件
  （`OperationSummaryPanel.tsx`、`KeyLevelsPanel.tsx`、`TechnicalIndicatorsPanel.tsx`、
  `AdviceCardView.tsx`、`LeverageChapterView.tsx`）
- 派工來源：CEO 原話「文字實在太多，看得眼花撩亂；請給我更清晰的介紹跟解釋。」
- 稽核依據：Playwright 實測（demo 資料，操作摘要／建議卡尚未載入時）——整頁可見文字
  3,656 字；「關鍵價位參考」1,871 字；「技術分析」1,765 字；操作摘要與建議卡載入後另
  再新增大量規則說明、反方論點、失效條件文字。已確認重複句：
  「是否跌破為觀察條件，不是進出指令」×2、「並非本系統對任何族群實際行為的統計…」×2；
  `NON_REALTIME_NOTICE`（約 90 字）於頁面多處重複出現。
- 狀態：draft（待 tech-architect 技術評估、risk-compliance-officer 就本 PRD 揭露句合併
  方向給初步意見後轉 spec）

---

## 背景與目標

### 問題定義

個股頁目前把「結論」「數字」「依據」「揭露」四種性質不同的文字，以近乎相同的視覺權重
（多為 `text-sm` / `text-xs`）攤平在同一畫面裡，導致：

1. **同一組事實被獨立元件各自完整覆誦一次**——最明顯的是「操作摘要」
   （`OperationSummaryPanel.tsx`）與「建議卡」（`AdviceCardView.tsx`）：兩者共用同一個
   `useAdvice` 查詢結果，卻各自完整渲染一次 headline、信心等級、`disclaimer`、
   反面論點、失效條件、建議數量區間——同一份 `advice.data.advice` 在頁面上被讀者看到
   兩次幾乎相同的敘述。
2. **同一面板內，同一條免責語被卡片層與「計算依據」清單層各自完整覆誦一次**——
   `KeyLevelsPanel.tsx` 的 `KEY_LEVELS_PULLBACK_EXPLAIN_NOTE`（拉回觀察卡）與
   `KEY_LEVELS_BASIS_PULLBACK`（計算依據清單）共享完全相同的尾句「是否跌破為觀察條件，
   不是進出指令；並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。」。
3. **系統層級的單一事實（非即時資料）在多個元件各自宣告一次**——`NON_REALTIME_NOTICE`
   同時出現在 `KeyLevelsPanel` 頭部四句常駐區與 `OperationSummaryPanel` 的多個分支
   （`no_price`／`no_action`／`RequiredElementsFooter`），造成同一句 90 字文字在同一次
   頁面渲染中重複出現。
4. **結論、數字、依據、揭露四層沒有視覺分層**——讀者要找「現在該怎麼看」的一句話結論，
   得先掃過大量計算公式與免責句才找得到，或反過來被結論句淹沒在依據句裡。

這些文字**多數是 risk-compliance-officer 逐字核可的鎖定字面**（`KeyLevelsPanel.tsx`、
`TradingViewChartPanel.tsx`、`app/lib/adviceWording.ts` 之 exported 常數），依公司章程
第 0 條第 5 款與既有 ADR／審查紀錄，**字面本身不可由本任務自行改動**，揭露文字也必須
維持「≥text-sm、≥neutral-400、常駐不可摺疊」。因此「減負」的可行手段被限定在：

- 資訊分層與版面精簡（不動文字）；
- 同一句揭露在頁面內去重、只完整呈現一次（**跨元件的去重涉及既有『固定順序揭露清單』
  的邊界，需 risk-compliance-officer 重新核可**，不是 product-manager 或 dev 可自行決定
  的版面調整）；
- 每區新增一句全新的白話導讀（新字面，需 creative-lead 成稿 + risk-compliance-officer
  核可）。

### 量化目標

| 指標 | 現況（Playwright 實測基準） | 目標 |
|---|---|---|
| 「關鍵價位參考」面板可見字數 | 1,871 字 | ≤ 1,777 字（現況的 95%），降幅只能來自去重與新增導讀的淨增減，**不得刪除任一條 `KEY_LEVELS_BASIS_*` 揭露項目** |
| 「技術分析」區塊可見字數 | 1,765 字 | ≤ 1,589 字（現況的 90%），降幅只能來自非鎖定教育性說明文字（`TechnicalIndicatorsPanel` 各卡片 `description`）精簡，不得刪減任何數值卡片或 `insufficient_data` 說明 |
| 頁面內同一句揭露文字重複出現次數 | `NON_REALTIME_NOTICE` ≥ 2 次；「是否跌破為觀察條件…」尾句 ≥ 2 次；操作摘要／建議卡的 disclaimer／反面論點／失效條件各 2 次 | 每句在核准合併範圍內的揭露文字，同一次頁面渲染只完整呈現 **1 次**（未核准合併者維持現況，見「揭露句頁級合併方案」） |
| 每區新增白話導讀字數 | 0（不存在） | ≤ 30 字（含標點）／區塊，且不得含建議、預測、方向性判斷 |
| 揭露句缺席數 | 0（現況全部存在） | 0（任何批次上線後都必須維持 0——這是紅線，不是可優化的分子） |

---

## 使用者與情境

- **主要使用者**：已登入的個人投資者，在自己的持倉或候選標的的個股頁，快速確認「現在
  這檔股票的系統結論是什麼、關鍵數字在哪裡、如果要細看依據要往哪裡找」。
- **情境 A（已持有）**：使用者想先看一句結論（加碼／續抱／減碼／停損參考等），再視需要
  往下看數字與依據；目前的痛點是結論句與免責句、規則明細混在一起，要素被重複兩次。
- **情境 B（未持有，候選評估）**：使用者想知道系統對此標的的候選評估是否支持進場，同
  樣被「候選模式證據不足提示」「規則覆蓋率」等大量必要揭露句包圍，找結論要花更多時間。
- **情境 C（研究槓桿型 ETF 或想細看規則依據的進階使用者）**：需要「計算依據」「命中規則
  明細」「drag／erosion 拆解」等完整內容，**不能因為減負而被拿掉**——這批使用者的需求
  與情境 A/B 的「先給我結論」需求互斥，因此本 PRD 用分層（而非刪除）解決，而不是砍掉進
  階內容。

---

## 範圍內 / 範圍外

### 範圍內

1. `page.tsx` 的區塊順序、視覺分層（三層 IA）。
2. `OperationSummaryPanel.tsx` 與 `AdviceCardView.tsx` 之間重複要素的去重方向決策與落地
   （需先過風控）。
3. `KeyLevelsPanel.tsx` 內卡片層說明與「計算依據」清單層之間的重複句處置（同上，需風控）。
4. `NON_REALTIME_NOTICE` 等系統層級揭露句的頁級合併評估與提案（需風控核准後才落地）。
5. 每個主要區塊新增一句白話導讀（操作摘要、關鍵價位參考、技術分析、建議卡、槓桿專章）。
6. 非鎖定的教育性說明文字精簡（`TechnicalIndicatorsPanel` 各指標卡片的 `description`）。
7. 純版面調整（標題階層、間距、grid 排列、非文字的視覺精簡）。

### 範圍外（non-goals）

1. **不改動任何 risk-compliance-officer 已逐字核可的常數字面**（`KeyLevelsPanel.tsx`、
   `TradingViewChartPanel.tsx`、`app/lib/adviceWording.ts` 之 exported 常數）——本任務
   只處理「這句話出現在哪裡、出現幾次、視覺權重多重」，不處理「這句話寫了什麼」。
2. 不新增或調整任何規則引擎的計算邏輯、風險上限判斷邏輯（`app/advice/engine.py`、
   `app/advice/limits.py` 等 backend 邏輯不動）。
3. 不變更 `TradingViewChartPanel.tsx` 待風控覆核中的兩句改寫案本身（見
   `work/stock-desk-D4-資料來源措辭.md` 第七節）——那是獨立任務，本 PRD 只承接其呈現
   規格慣例（常駐、字級、對比下限），不重新開案。
4. 不處理槓桿專章（`LeverageChapterView.tsx`）內 `<details>` 收合的「假設清單」機制本身
   ——該元件目前的假設清單摺疊是既有設計（非本次稽核點名的重複／過長來源），僅在「三層
   IA」中決定其整體區塊在頁面上的相對位置，內部結構不動。
5. 不做 A/B 測試或使用者行為量測；驗收以本 PRD 的字數與去重指標為準。

---

## 功能需求（逐條編號）

### FR-1　三層資訊架構（一眼結論 / 數字與水位 / 依據與揭露）

頁面由上而下分三層，**同一層內的既有區塊順序原則上不變**，只調整「同一份資料在哪一層
完整出現一次」：

- **第一層「一眼結論」**：H1（symbol／公司名／市場）+「操作摘要」區塊的
  headline／信心等級／`disclaimer`／§2 八要素（原樣位置，FR-C1 既有要求「above the
  fold」不變）。此層新增一句白話導讀（FR-2）。
- **第二層「數字與水位」**：「關鍵價位參考」面板的四張數字卡（位階／拉回觀察／停損／
  停利）、「技術分析」的 K 線圖與技術指標數值卡片。此層每個子區塊新增一句白話導讀。
- **第三層「依據與揭露」**：「關鍵價位參考」的「計算依據」清單、「建議卡」的規則明細
  （命中規則、命中規則方向、資料完整度／被跳過規則）、「槓桿型 ETF 專章」。此層內容
  維持**完整、不摺疊**（風控 R7 等既有裁決不變），只是視覺位置整體置後、字級不再與第
  一層結論句同等搶眼（例如結論句可用較大字重／色塊，依據句維持現行 `text-sm`／
  `text-neutral-400` 不變，不得再更小）。

> 注意：AdviceCardView 目前同時承載「結論重複」（第一層性質的 headline／disclaimer／
> 反面論點／失效條件）與「依據明細」（第三層性質的規則清單、限額檢查）。FR-4 處理前者
> 的去重；去重後 AdviceCardView 定位收斂為純第三層元件。

**Given** 使用者開啟任一有 `advice.status="ok"` 的個股頁
**When** 頁面完整載入
**Then** 「操作摘要」區塊出現在「關鍵價位參考」與「技術分析」之前（現況已是如此，本
需求只是把這個既有順序寫入規格、防止未來改版時無意間打亂），且「建議卡」「槓桿專章」
的規則明細類內容不出現在「操作摘要」之前。

---

### FR-2　每區塊一句白話導讀

- **要說什麼**：用一句話（≤30 字，含標點）說明「這個區塊在呈現什麼性質的資訊」，例如
  「這裡列出系統依固定公式算出的參考價位，數字背後怎麼算，下方逐項寫明」——是**對區塊
  性質的描述**，不是對股票走勢或操作的判斷。
- **不能說什麼**：
  - 不得包含任何方向性判斷、預測、機率、建議動作（不得出現
    `app/lib/adviceWording.ts` 之 `FRONTEND_FORBIDDEN_TERMS` 清單內任何字詞，也不得
    出現「應該」「建議你」「這檔股票」等把系統性描述偷渡成個股判斷的用語）。
  - 不得與既有揭露句字面重複或高度相似（避免變相多造出一句新的「非投資建議」宣告，
    稀釋既有揭露句的辨識度）。
  - 不得替代任何既有必要揭露句——白話導讀是「這個區塊是什麼」，揭露句是「這個數字怎麼
    算、有什麼限制」，兩者功能不同、都要存在。
- **落地位置**：緊接在區塊 `<h2>`／`<h3>` 標題之後，字級與既有卡片標題同級或更明顯，
  但視覺上與下方揭露句／數字明顯區分（例如用不同顏色或字重，而非藏在同一段落）。
- **五個待寫區塊**：操作摘要、關鍵價位參考、技術分析（K 線／技術指標可各自或合併一句）、
  建議卡、槓桿型 ETF 專章。
- **流程**：本 PRD 只定規格；文字本身由 creative-lead 成稿，逐字送
  risk-compliance-officer 核可後才可落地（比照 `work/stock-desk-D4-資料來源措辭.md`
  既有流程）。

**Given** creative-lead 已成稿五句導讀，且 risk-compliance-officer 已逐字核可
**When** 前端將核可字面落地到對應區塊標題下方
**Then** 每句導讀的字數（不含標點以外的可視字元計算方式與現行「字數稽核」腳本一致）
≤ 30 字，且以 `FRONTEND_FORBIDDEN_TERMS` 掃描零命中。

---

### FR-3　`NON_REALTIME_NOTICE` 頁級合併（需風控重審）

- **現況**：同一段 90 字左右的文字，在 `KeyLevelsPanel` 頭部四句常駐區與
  `OperationSummaryPanel` 的多個分支中各自完整渲染，兩者同時存在於同一螢幕範圍內
  （關鍵價位面板在操作摘要之後，載入後兩段文字同時可見）。
- **提案**：在 H1 下方、所有分層區塊之前，新增一個常駐的「本頁資料與計算揭露」區塊，
  收斂目前**分散在多個元件、彼此逐字相同**的系統層級揭露句，`NON_REALTIME_NOTICE`
  是目前唯一確認完全逐字相同、且不依附特定數字（不像「基準價」「停損水位」那樣需要貼
  在對應數字旁）的候選。合併後，原本兩處元件改為不再各自重複渲染這句話。
- **為什麼需要風控重審，而不是純版面調整**：`KeyLevelsPanel` 頭部四句與
  `OperationSummaryPanel` 的 §2 八要素，兩者都是風控**逐項核可、且明訂順序與所屬清單**
  的既有裁決（見 `KeyLevelsPanel.tsx` 檔頭「頭部四句常駐（順序固定）」註解、
  `adviceWording.ts` 檔頭「§2（8 required elements）」註解）。把其中一句抽出頁級共用，
  等於變更兩份既有核可清單各自的「完整性」定義，即使字面本身不變，也需要風控重新確認
  「抽出後，各自清單是否仍算滿足原始要求」。

**Given** risk-compliance-officer 尚未核可頁級合併方案
**When** product-manager 或 dev 逕自將 `NON_REALTIME_NOTICE` 從任一元件的既有渲染路徑
移除
**Then** 視為違規變更（即使目的是去重），須退回、不得上線；本項目在核可前維持現況
（兩處都保留），減字目標暫不計入此句。

**Given** risk-compliance-officer 已核可頁級合併方案
**When** 頁面渲染
**Then** `NON_REALTIME_NOTICE` 全文字串在單次頁面渲染中只完整出現 1 次，且呈現位置
符合原呈現規格下限（≥text-sm、≥neutral-400、常駐、頁面載入即可見、不需捲動到頁尾）。

---

### FR-4　操作摘要／建議卡重複要素去重（需風控重審＋CEO 定調方向）

- **現況重複清單**（同一份 `advice.data.advice` 在兩處各自完整渲染一次）：
  headline（`buildAttributedHeadline`／`CANDIDATE_HEADING_LABEL`）、信心等級與
  `confidenceMeaning`、`disclaimer`、反面論點（`counterarguments`）、失效條件
  （`invalidation_conditions`）、建議數量區間（`quantity_range`／`quantityRangeText`）。
- **提案方向（待 CEO 定調，見開放問題 1）**：
  - **方向 A**：操作摘要維持現有完整內容（第一層結論+ 必要八要素），建議卡收斂為
    「純規則明細」——移除 headline／信心等級／disclaimer／反面論點／失效條件／數量區
    間的重複渲染，改以一句交叉引用銜接（例如「結論、反面論點與失效條件已列於上方操作
    摘要，此處為完整規則明細」），只保留命中規則清單、命中規則方向、風險上限檢查、資
    料完整度。
  - **方向 B**：操作摘要收斂為「一句結論 + 連結／錨點跳轉」，完整八要素與明細都收在建
    議卡，操作摘要不再獨立重複渲染 disclaimer 等要素。
  - 兩個方向都涉及「原本要求某要素必須在特定視覺區位、不可摺疊」的既有裁決是否仍然成
    立（例如 `AdviceCardView.tsx` 的 R3 fix 註解明言 disclaimer 必須與 headline 同視覺
    區域，且以 `OperationSummaryPanel` 的 `DisclaimerBanner` 為對齊標準——若拿掉其中一
    處的 headline，另一處的「同視覺區域」要求要如何滿足需重新界定），**兩個方向皆須
    risk-compliance-officer 逐項覆核**，不是本 PRD 自行拍板。
- **新增的交叉引用句字面**（如方向 A 的銜接句）視為新字面，需 creative-lead 成稿並送
  風控核可，不得由 dev 自行編寫上線。

**Given** CEO 尚未就方向 A／B 定調、風控尚未核可對應方案
**When** 頁面渲染 advice.status="ok" 的任一模式
**Then** 「操作摘要」與「建議卡」維持現況各自完整渲染（不去重），本項目減字效益暫不計
入本批次目標。

**Given** CEO 已定調方向、風控已核可去重方案
**When** 頁面渲染
**Then** disclaimer、反面論點清單、失效條件清單三者的完整文字內容，在單次頁面渲染中
各自只完整呈現 1 次（另一處若有殘留，僅能是核可的交叉引用句，不得是原清單的重複列
舉）。

---

### FR-5　`KeyLevelsPanel` 內部重複句處置（需風控重審）

- 拉回觀察卡的 `KEY_LEVELS_PULLBACK_EXPLAIN_NOTE` 與計算依據清單的
  `KEY_LEVELS_BASIS_PULLBACK` 共享完全相同的尾句。面板內已有先例
  （`KEY_LEVELS_TARGET_ROW_TRAILING_NOTE`：「（與『拉回觀察』卡片的 MA20 為同一數字；
  系統並未另行計算移動停利水位，僅以跌破 MA20 作為觀察條件）」）示範了「用交叉引用取代
  重複列舉」的寫法，本項目提案比照此手法，將計算依據清單中的拉回觀察項目，改寫為指回
  卡片說明的交叉引用句，而非重複完整免責語。
- 這是**改寫既有核可字面**（即使只改一句），必須先送 creative-lead 起草交叉引用句字
  面，再送 risk-compliance-officer 核可，理由與 FR-3／FR-4 相同：`KEY_LEVELS_BASIS_*`
  是「計算依據（常駐清單，不摺疊——風控 R7）」逐項核可的固定清單，抽換其中一項的寫法
  需重新確認清單完整性不受影響。
- `KEY_LEVELS_BASIS_STOP`／`KEY_LEVELS_BASIS_TARGET` 中同樣出現「並非本系統對任何族群
  實際行為的統計，本系統未持有此類統計資料。」尾句（各自對應 −8%／+20% 這兩個不同的固
  定參數），**本 PRD 不建議合併**——這兩處分別揭露兩個不同的硬編碼參數各自的假設限
  制，不是單純的文字重複，去重風險大於效益，列為「維持現狀」，但仍在下方「揭露句頁級
  合併方案」中列出供風控參考裁決。

**Given** risk-compliance-officer 尚未核可拉回觀察句的交叉引用改寫
**When** 頁面渲染關鍵價位參考面板
**Then** 拉回觀察卡與計算依據清單維持現行各自完整文字（不去重）。

**Given** risk-compliance-officer 已核可交叉引用改寫版本
**When** 頁面渲染
**Then** 計算依據清單中的拉回觀察項目改為核可之交叉引用句字面，卡片層的
`KEY_LEVELS_PULLBACK_EXPLAIN_NOTE` 維持不動（因為它離對應數字最近，屬於局部揭露，不
是被去重的一方）。

---

### FR-6　非鎖定教育性說明文字精簡（不需風控重審，仍建議 creative-lead 過目）

`TechnicalIndicatorsPanel.tsx` 各指標卡片（`IndicatorCard`）的 `description` prop
（例如「近 N 日收盤價的簡單平均，用於觀察價格趨勢；三個天期分別各自判斷資料是否足
夠…」）是 dev 自行撰寫的指標定義說明，不是 `adviceWording.ts` 或 `KeyLevelsPanel.tsx`
的鎖定常數，性質上是「名詞解釋」而非「面向使用者的建議類文案」，依公司章程第 0 條第 5
款不強制送風控，但涉及金融名詞，建議 creative-lead 過一次稿以確保用詞精簡、不失真。

**Given** creative-lead 已完成七張指標卡片 description 的精簡版（每則描述精簡後仍保留
指標定義的正確性，不新增任何方向性判斷字眼）
**When** 前端替換現行 description 文字
**Then** 每則 description 字數較現況減少，且掃描結果不含
`FRONTEND_FORBIDDEN_TERMS`（即使不強制送風控，仍以同一份禁用詞清單自我把關），也不新
增任何買賣訊號、機率、預測字樣。

---

### FR-7　揭露句「不缺席」守門（紅線，貫穿所有批次）

任何批次（無論是否需風控重審）上線後，**上線前存在的每一句風控鎖定揭露文字，都必須在
上線後的頁面中仍至少完整出現 1 次**，且呈現樣式不得劣化（不得縮小字級、降低對比、或
被摺入 `<details>`）。這條規則優先於所有減字目標——減字不足額達成可以檢討方案，但揭露
句消失是不可接受的迴歸，必須視為 blocking issue。

**Given** 任一批次上線
**When** qa-reviewer／qa-automation 比對上線前後的頁面文字快照
**Then** 上線前存在的揭露句集合是上線後揭露句集合的子集合（允許新增，不允許減少），
違反者一律 BLOCKING_ISSUES，退回重做。

---

### FR-8　分批交付與 gating

見下方「分批交付建議」；本需求要求：純版面批次的 diff 中**不得**觸碰
`KeyLevelsPanel.tsx`／`TradingViewChartPanel.tsx`／`app/lib/adviceWording.ts` 內任何
exported 常數字面（含標點），以此作為「這個 PR 是否需要重新送風控」的機械判斷依據。

**Given** 一個聲稱屬於「純版面批次」的 PR
**When** qa-reviewer 檢查其 diff
**Then** diff 中對上述三個檔案的變更（若有）僅限 JSX 結構／className／import 順序，
不含任何字串常數的字元變更；若含字元變更，該 PR 必須改標記為「需風控重審批次」，不得
以純版面批次的流程直接進 review。

---

## 驗收條件（Given/When/Then）

> 對應「品質檢查清單」要求：以下為可機械量測的整頁級驗收條件，補充於各 FR 自帶的
> G/W/T 之外，供 qa-reviewer／qa-automation／qa-e2e 直接引用。

**AC-1（NON_REALTIME_NOTICE 去重，批次2）**
Given 頁面已完成風控核准之揭露句頁級合併方案
When 使用者開啟任一個股頁（`bars.status="ok"` 且 `advice` 已載入完成）
Then 全頁 DOM 中 `NON_REALTIME_NOTICE` 全文字串（含標點）僅出現 1 次，且該次呈現位置
符合風控核准之規格（≥text-sm、≥neutral-400、不可摺疊、載入即可見）。

**AC-2（操作摘要／建議卡要素去重，批次2）**
Given 風控已核准操作摘要與建議卡的要素去重方案（方向 A 或 B，依 CEO 定調）
When `advice.status="ok"`（held 或 candidate 模式皆同）且頁面完整載入
Then 「反面論點」清單、「失效條件」清單、`disclaimer` 逐字文本，三者各自在頁面上只完
整呈現 1 次（另一處若有殘留內容，僅能是風控核可的交叉引用句）。

**AC-3（白話導讀規格，批次2/3）**
Given 五個區塊皆已加入風控核可的白話導讀
When 使用者檢視任一區塊標題下方
Then 該導讀文字（不含既有揭露句、不含標題本身）字數 ≤ 30 字（含標點），且以
`FRONTEND_FORBIDDEN_TERMS` 掃描零命中，且不含任何具體股數、價位、漲跌方向字樣。

**AC-4（揭露句不缺席，紅線，貫穿所有批次）**
Given 任一批次（純版面或需重審）已上線
When 比對上線前後的頁面文字快照
Then 上線前存在的每一句風控鎖定揭露文字，在上線後仍至少完整出現 1 次（含標點），且
呈現樣式不劣化；任何缺席一律視為 BLOCKING_ISSUES。

**AC-5（純版面批次可獨立驗收，批次1）**
Given 「批次1：純版面調整」已完成，且宣稱未變更任何鎖定常數字面
When qa-reviewer 檢查該批次 diff
Then diff 對 `KeyLevelsPanel.tsx`、`TradingViewChartPanel.tsx`、
`app/lib/adviceWording.ts` 的變更（若有）不含任何字串常數字元變更，僅涉及
className／JSX 結構順序／非鎖定描述文字（FR-6 範圍內）；符合者不需重新送風控，可直接
進入 qa-reviewer／qa-e2e 驗收。

**AC-6（區塊字數量測，批次2完成後）**
Given Playwright 對 demo 資料的個股頁執行與本次稽核相同的可見文字擷取腳本
When 批次2（去重＋白話導讀）全部上線後重新執行同一腳本
Then 「關鍵價位參考」區塊可見字數 ≤ 1,777 字（現況 1,871 字的 95%），且未刪除任何一
條 `KEY_LEVELS_BASIS_*` 揭露項目；「技術分析」區塊在指標卡片 description 精簡（FR-6）
後可見字數 ≤ 1,589 字（現況 1,765 字的 90%）。

**AC-7（既有守門測試維持綠燈）**
Given `componentWordingScan.test.ts`、`sharedForbiddenTerms.test.ts`、
`test_advice_wording_frontend.test.ts` 等既有逐字／禁用詞守門測試
When 批次2（頁級揭露合併、要素去重、交叉引用改寫）落地後執行既有測試套件
Then 全數維持綠燈；若既有測試斷言的字串因去重呼叫點改變而需要調整斷言位置（而非斷言
內容本身），需同步更新測試並在 PR 說明中列出調整項目，供 qa-reviewer 核對未變更斷言
的「內容」本身。

---

## 揭露句頁級合併方案（分類與需風控重審項目）

| 揭露句 / 重複組 | 現況出現位置 | 分類 | 處置建議 |
|---|---|---|---|
| `NON_REALTIME_NOTICE` | `KeyLevelsPanel` 頭部四句；`OperationSummaryPanel` 的 `no_price`／`no_action`／`RequiredElementsFooter` 分支 | **可考慮頁級合併，需風控重審** | 抽出至頁級「本頁資料與計算揭露」區塊，原兩處不再各自渲染（FR-3） |
| `disclaimer`／headline／信心等級／反面論點／失效條件／建議數量區間 | `OperationSummaryPanel` 與 `AdviceCardView` 各自完整渲染一次 | **需風控重審 + CEO 定調方向** | 依方向 A／B 其一去重，另一處改交叉引用句（FR-4） |
| 拉回觀察免責尾句 | `KEY_LEVELS_PULLBACK_EXPLAIN_NOTE`（卡片層）／`KEY_LEVELS_BASIS_PULLBACK`（計算依據層） | **需風控重審** | 計算依據層改交叉引用句，卡片層維持不動（FR-5） |
| 「並非本系統對任何族群實際行為的統計」尾句 | `KEY_LEVELS_BASIS_STOP`／`KEY_LEVELS_BASIS_TARGET`（各自對應不同的硬編碼參數 −8%／+20%） | **維持現狀，不建議合併**（列出供風控參考） | 兩處各自解釋不同參數的假設限制，非單純文字重複，去重風險大於效益 |
| `KeyLevelsPanel` 頭部四句常駐、`adviceWording.ts` §2 八要素各自的既有排序 | 各自元件內部 | **不動** | 這是既有核可的「清單本身」，不是本次要合併的對象，只是 FR-3／FR-4 抽出其中一項時需要確認不破壞這兩份清單各自的完整性 |
| `TradingViewChartPanel.tsx` 待風控覆核中的兩句改寫案 | 該元件本身 | **範圍外**（獨立任務進行中） | 本 PRD 不重新開案，落地時比照其呈現規格慣例即可 |

---

## 分批交付建議

### 批次1：純版面調整（不需風控重審，可立即排入 build）

- 標題階層、間距、grid 排列、非文字視覺精簡（不動任何文字內容）。
- `TechnicalIndicatorsPanel.tsx` 各指標卡片 `description` 精簡（FR-6，非鎖定文字，建議
  creative-lead 過目但不強制走風控閘門）。
- 三層 IA 的區塊「相對順序」若現況已符合（見 FR-1），本批次只需把順序寫進程式碼註解／
  測試固定下來，防止未來改版打亂，不需搬動既有區塊。
- gating：diff 不得觸碰 `KeyLevelsPanel.tsx`／`TradingViewChartPanel.tsx`／
  `app/lib/adviceWording.ts` 的任何常數字元（AC-5）。

### 批次2：需風控重審的文案／位置變更

- `NON_REALTIME_NOTICE` 頁級合併（FR-3）。
- 操作摘要／建議卡重複要素去重（FR-4）——**前提是 CEO 已定調方向 A 或 B**。
- 拉回觀察句交叉引用改寫（FR-5）。
- 五個區塊的白話導讀新增（FR-2）——文字由 creative-lead 成稿，逐字送風控核可。
- 流程：creative-lead 成稿 → risk-compliance-officer 逐字核可 → 前端落地 → 補逐字守門
  測試（比照 `componentWordingScan.test.ts` 既有模式）→ qa-reviewer／qa-e2e 驗收。

### 批次3：視風控裁決結果的降級備案

- 若批次2部分項目被風控否決（例如認為既有揭露清單的完整性不可被抽出項目破壞），改採
  「不減字數、只做視覺降權（縮小但不降字級對比）」的降級方案，或退回 CEO 重新評估是否
  接受更小的減字幅度。

---

## 風險與依賴

- **風控核可時程不可控**：FR-3／FR-4／FR-5／FR-2 皆需 risk-compliance-officer 逐字核
  可，過去類似案例（`work/stock-desk-D4-資料來源措辭.md`）曾歷經二至三輪修訂，本任務
  的批次2／3 時程應預留同等緩衝，不可承諾固定上線日期。
- **FR-4 的方向選擇會實質改變「建議卡」的產品定位**（從「第二份結論」變成「純規則明
  細」），若 CEO 選擇的方向與現有使用者的既有使用習慣落差過大，可能需要額外的過渡期或
  說明，本 PRD 未涵蓋使用者溝通計畫，需另案評估。
- **依賴 tech-architect 技術評估**：頁級「本頁資料與計算揭露」區塊如何與各子元件的資料
  來源（`useAdvice`／`useBars`／`useSignals` 等各自獨立的 React Query 結果）解耦，避免
  合併後某一查詢失敗連帶影響頁級揭露區塊的渲染，需 tech-architect 確認技術可行性後才能
  進入 build。
- **依賴既有逐字守門測試的維護成本**：任何去重或交叉引用改寫，都需要同步更新
  `componentWordingScan.test.ts`、`app/lib/__tests__/adviceWording.test.ts` 等測試，
  避免文字漂移在未來被誤放行。

---

## 開放問題（待 CEO 或其他部門回答）

1. **【CEO】操作摘要與建議卡的重複要素去重方向**：選擇方向 A（建議卡收斂為純規則明
   細，操作摘要維持完整結論層）或方向 B（操作摘要收斂為一句結論＋錨點跳轉，完整八要
   素與明細集中在建議卡）？此為產品資訊架構的取捨，需 CEO 定調後才能請風控依此方向覆
   核（FR-4）。
2. **【CEO】若批次2的揭露句合併方案被風控否決，是否接受批次3的降級方案**（只做視覺降
   權、不減字數），或要求重新設計更大幅度的替代方案（可能需要更長時程）？
3. **【CEO】交付時程與分次上線的取捨**：白話導讀與去重（批次2）需要 creative-lead 成
   稿＋風控核可，預估會拉長總時程；是否接受先交付批次1（純版面，立即可上線）並同步送
   出批次2的風控重審申請，兩批次分次對外發布，而非等全部批次備齊才一次上線？

其餘技術性開放問題（非 CEO 決策層級，一併列出以便追蹤）：

4. **【tech-architect】** 頁級揭露區塊與各子元件獨立 React Query 結果之間，如何避免「某
   查詢失敗時頁級揭露區塊仍需正確渲染」的耦合問題？
5. **【risk-compliance-officer】** FR-6（技術指標卡片教育性說明文字精簡）是否確實落在
   「非建議類文案」範圍內、可不強制走風控閘門，或風控認為金融名詞說明一律應審查？
   （此問題同時對應開放問題中的 CEO 決策 2，若風控傾向從嚴，批次1的 gating 條件需相應
   收緊）

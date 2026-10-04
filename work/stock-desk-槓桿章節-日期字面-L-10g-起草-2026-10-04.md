# 槓桿章節時間字面（L-10g）——替代字面起草稿

- 日期：2026-10-04
- 起草：creative-lead
- 分支：product/stock-desk
- 依據：`work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md` 末段 L-10g；`work/research/L-10g-槓桿章節時間欄位與日期替代-分析-2026-10-04.md`（dev-lead）
- 狀態：**待 risk-compliance-officer 逐字審**（本稿不得直接進程式碼；後端附加欄位的欄名另由 tech-architect／dev-lead 定）

## 1. 定錨（creative-masters 第 1 步）

- **目標**：把槓桿章節兩行「日線取得時間」（顯示列層 `as_of`，與 ADR-0019 D-5 衝突）換成「日期層級」字面，使用者讀得出每條序列的資料到哪一天，且分得出「序列截至」與「計算截至」。
- **受眾**：持有日度重置型槓桿／反向 ETF 的個人投資人；看到的是中性機制陳述，不是操作指引。
- **限制**（風控裁示）：比照「資料截至」家族；不得含「最新」「即時」「同步」「取得」；不可直接刪（指數日線無其他時間戳）；永遠分列、不收合、不加相等判斷（L-10b）；缺值用「日期不明」，不用「—」（E-3 保留給「無法判定」）；不加條件式提示（L-10b-2）。

## 2. 視角與互評（精簡版；任務是句型小改，只保留會改變決策的部分）

選 Ogilvy＋Young＋Rubin（命名／文案組合）。

| 視角 | 核心提問 | 對本案的貢獻 |
| --- | --- | --- |
| Ogilvy | 讀者三秒內讀到什麼？ | 第三個日期若只寫「計算 10-02」會被當成算式；必須帶「截至」才讀得出是日期。讀者要的是「這組數字算到哪天」，所以標籤用動作結果（計算截至），不用內部詞（window、aligned）。 |
| Young | 這是舊元素的新組合嗎？ | 不另造句型。直接複製已核可的 E-4 骨架「資料截至：{名稱} {日期}｜…」，第三個欄位像 E-4 的「規則評估」一樣，是「非序列本身」的第三個時點。站內另有先例「歷史比例統計截至 {日期}」（`sectorMomentumWording.ts` L544），證明「X 截至」可以用在計算結果上。 |
| Rubin | 還能拿掉什麼？ | 拿掉任何「相同則收合」「若不同則提示」的說明句（風控已否決）；拿掉「ETF／指數」旁的「日線」二字（標題已是「資料截至」）；只留三個日期與三個名詞。 |

Braintrust 互評要點（只列倖存的 note）：

- 「計算截至」← Ogilvy：V-3c 曾因「計算」未查證被否決，這次要附讀碼證據，否則同樣會被擋。（已處理：見 3.2 證據）
- 「資料截至：…｜計算截至 …」← Rubin：標題「資料截至」與第三欄「計算截至」重複「截至」，讀起來略囉嗦。（保留：重複正是對比的記號；備案 W-1b 提供各欄自足版）
- 「共同交易日至」← Young：比「計算截至」精確，但使用者要多讀一步才懂這是 Gap 的終點。（列為備案 W-1c，風控若不接受「計算」才用）
- 收合句 ← 風控 L-10b：已否決，不再提。

## 3. 第一處：L185（Gap 拆解段）

### 3.1 現況與要解的問題

- 現況：`日線取得時間：ETF {formatDateTime(drag.as_of)}／指數 {formatDateTime(drag.index_as_of)}`。
- 新後端欄位：`drag.last_bar_date`（ETF 最後日線日）、`drag.index_last_bar_date`（指數最後日線日）、`drag.window.end_date`（ETF 與指數共同交易日對齊後的終點）。
- **語意風險**：指數來源可能延遲一天，ETF 最後日線 10-02、指數最後日線 10-01 時，Gap 數字只算到共同日 10-01。若只印兩條序列的日期，讀者看不出數字實際用到哪天。所以字面要同時給「序列截至」與「計算截至」三個日期。

### 3.2 「計算截至」的事實依據（回應 V-3c 前例）

V-3c 被否決的是「回應『計算』時間」，因為當時「計算」指的動作與時間點沒查證。本案的「計算」指的是已讀碼確認的事實：

- `backend/app/leverage/drag.py` L202–L213：ETF 與指數收盤價 inner-join 取共同交易日、`dropna()`、再截去建倉日之前；
- 同檔 L380、L392–L393：`end_date = dates[-1]` 寫入 `window.end_date`；
- 同檔 L9「all figures are simple returns over the same aligned window」，L71–L72 使用者可見的假設句已寫「ETF 與標的指數的共同交易日收盤價對齊計算」。

也就是說「計算截至」＝既有假設句所說「對齊計算」的終點，沒有新造主張。仍請風控確認這個讀碼結論；不接受時用 W-1c。

### 3.3 候選字面

| 編號 | 字面（逐字） | 說明 |
| --- | --- | --- |
| **W-1（主案）** | `資料截至：ETF {D_e}｜指數 {D_i}｜計算截至 {D_w}` | 複製 E-4 已核可骨架；前兩欄是兩條序列各自的最後日線日，第三欄是 Gap 數字實際算到的共同日。 |
| W-1b（備案 1） | `ETF 資料截至 {D_e}｜指數資料截至 {D_i}｜計算截至 {D_w}` | 三欄各自成句、不靠標題；與第二處 W-2 的「指數資料截至」同詞。缺點：多 4 個字、「截至」出現 3 次。 |
| W-1c（備案 2） | `資料截至：ETF {D_e}｜指數 {D_i}｜共同交易日至 {D_w}` | 完全不用「計算」；直接引用既有假設句的「共同交易日」。缺點：讀者要多想一步才知道這是 Gap 的終點。 |

推薦 **W-1**。理由：與 E-4 同骨架，使用者在同一頁已見過；第三欄的「計算」有 3.2 證據；W-1c 是風控不接受「計算」時的現成退路。

### 3.4 標點與空格（比照 L-10b 唯一版型）

- 全形「：」後無空格。
- 「ETF」「指數」「計算截至」後各一個半形空格。
- 「｜」全形，前後無空格。
- 不加句號。

### 3.5 日期欄 `{D_x}` 規則（沿用 E-4／L-10b-E4-F）

- 輸入符合 `^\d{4}-\d{2}-\d{2}$` 且為今年 → `MM-DD`。
- 符合格式但非今年 → `YYYY-MM-DD`。
- `null`／`undefined`／空字串／格式不符（含 ISO 時間戳、`2026/10/02`）→ `日期不明`。
- 接線：`{D_e}`＝`drag.last_bar_date`、`{D_i}`＝`drag.index_last_bar_date`、`{D_w}`＝`drag.window.end_date`。
- 實作要求：沿用 `entryObservationWording.ts` 的 `formatDataAsOfDate`（需 export 或抽到共用檔，行為一字不變，E-4 既有測試須維持綠）；前端渲染處以 `?? null` 把 `undefined`（前後端部署錯開、舊後端沒有新欄）當缺值，不得印出 `undefined`。

### 3.6 三個日期都相同時：仍分列

**一律分列，不收合，不加任何「一致」「相同」「同步」類字眼。** 理由與 L-10b 相同：日期相同不等於資料相同，且收合需要比較日期相等，違反 L-10b「不得加回任何相等或收合邏輯」。本處 `LeverageChapterView.tsx` 不得出現對這三個日期的 `===`。

### 3.7 渲染範例（假設今年為 2026）

| 情境 | 輸出 |
| --- | --- |
| 三者相同 | `資料截至：ETF 10-02｜指數 10-02｜計算截至 10-02` |
| 指數延遲一日（本案要分辨的情況） | `資料截至：ETF 10-02｜指數 10-01｜計算截至 10-01` |
| 三者皆非今年 | `資料截至：ETF 2025-12-31｜指數 2025-12-31｜計算截至 2025-12-31` |
| 只缺指數 | `資料截至：ETF 10-02｜指數 日期不明｜計算截至 10-02` |
| 三份皆缺 | `資料截至：ETF 日期不明｜指數 日期不明｜計算截至 日期不明` |
| 後端誤傳 ISO 時間戳 | 該欄印「日期不明」，不會印出時間（故誤接 `as_of` 時畫面會露出錯誤，而不是靜默通過） |

最長句（非今年三欄）49 字、三份皆缺 31 字；為 `<p>` 自然換行，需 qa-e2e 在 390px 確認無橫向溢出。

## 4. 第二處：L243–L244（重置效應／波動估計段）

### 4.1 現況與替代

- 現況：`波動估計視窗：{observations}／{window} 個報酬｜指數日線取得時間：{formatDateTime(erosion.as_of)}`
- **W-2（主案）**：`波動估計視窗：{observations}／{window} 個報酬｜指數資料截至 {D_i}`
- W-2b（備案）：`波動估計視窗：{observations}／{window} 個報酬｜指數日線截至 {D_i}`（沿用 V-6b 已核可的「日線」一詞與 E-4「日線」標籤；缺點是與 W-1 的「指數」「資料截至」用詞不一致）。

推薦 **W-2**。理由：

1. 只動後半句，前半「波動估計視窗：N／M 個報酬」一字不動。
2. 這一段不存在「序列截至」與「計算截至」的分歧：erosion 取的是指數最近 `window` 個交易日報酬（`erosion.py` L192 `returns[-window:]`），視窗終點就是指數最後一根日線，所以只要一個日期，不需第三欄。
3. 「指數資料截至」與 W-1b 同詞，且與 `DataMetaStatusBadge`、`buildDataAsOfBadge` 的「資料截至 {日期}」句式（日期前一個半形空格、無冒號）一致。

標點：「｜」全形前後無空格；「指數資料截至」後一個半形空格。`{D_i}` 規則同 3.5；接線 `erosion.index_last_bar_date`（欄名待 tech-architect 定，dev-lead 分析用 `erosion.last_bar_date` 或 `index_last_bar_date`，字面不受影響）。

### 4.2 範例

- `波動估計視窗：120／120 個報酬｜指數資料截至 10-02`
- 缺值：`波動估計視窗：120／120 個報酬｜指數資料截至 日期不明`
- 非今年：`波動估計視窗：120／120 個報酬｜指數資料截至 2025-12-31`

## 5. 缺值與全缺處理（彙整）

1. 每個日期欄獨立判斷，缺哪欄印哪欄的「日期不明」，其他欄照印。
2. 三份皆缺仍印完整句（W-1 全缺範例）：**不隱藏整行、不改用「—」、不改成單一句「日期不明」**。理由：E-4 先例（L-10b 否決「—」與條件隱藏）；隱藏等於沉默宣稱「沒有時間問題」。
3. 不同欄日期不同時不加任何提示（L-10b-2 同理）；日期並列本身就是揭露。Gap 數字使用共同交易日對齊的說明，已在假設清單既有句（`drag.py` L71–L72）。
4. W-2 只有一個日期，缺值印 `指數資料截至 日期不明`，不隱藏。
5. 兩行只在 `status === "ok"` 分支渲染（現況不變）；非 ok 時沿用既有 `reason`，不印日期行。

## 6. 相鄰問題（供風控決定是否併入本單）

### 6.1 L101「最新日線 {holding.last_bar_date}」

現況：`建倉日 {opened_at} ～ 最新日線 {last_bar_date}，共 {n} 個交易日（{m} 曆日）。`「最新」違反風控「資料時間字眼不得含最新」的既有立場（L-10b-2 附加條件亦列「最新」）。

| 編號 | 字面（逐字，只換「最新日線」） | 說明 |
| --- | --- | --- |
| **W-4（主案）** | `建倉日 {opened_at} ～ 資料截至 {last_bar_date}，共 {n} 個交易日（{m} 曆日）。` | 「資料截至」家族；範圍句讀成「建倉日到資料截至日」。 |
| W-4b（備案） | `建倉日 {opened_at} ～ 日線截至 {last_bar_date}，共 …` | 用 E-4 的「日線」一詞，語感更順；但與 W-1 的「資料截至」家族分岔。 |

- **日期格式不套 E-4 的 `MM-DD`**：同句 `opened_at` 是完整 `YYYY-MM-DD`，範圍兩端必須同格式，否則「2026-01-02 ～ 09-30」會讓人誤判年份。站內已有完整西元日期搭配「資料截至」的先例（`DataMetaStatusBadge` 非今年快取句、`BacktestReportView.tsx` L181）。請風控確認。
- 缺值：只在 `holding.status === "ok"` 分支渲染，後端 `service.py` L109–L118 在 ok 時 `last_bar_date` 必有值；維持現狀不加分支。
- 同畫面兩種格式的差異（L101 印完整日期，W-1 的 ETF 欄印 `MM-DD`）屬同一日期兩種粒度；dev-lead 加一條測試：`holding.last_bar_date` 與 `drag.last_bar_date` 對同一份 ETF bars 相等，避免同頁兩個 ETF 日期互相矛盾。

### 6.2 L252「產生時間：{formatDateTime(chapter.generated_at)}」

這是 `service.py` L185 `datetime.now(UTC)` 的回應產生時間，與 E-4 已撤、V-3A 已拿掉的是同一類；D-5 的理由（印絕對時間會被讀成「資料剛更新」）同樣適用。L-10d 另指其主體不明。

| 編號 | 方案 | 說明 |
| --- | --- | --- |
| **W-5（主案）** | **整行拿掉** | 與 V-3A 一致：章節各段已有各自「資料截至」，稽核由伺服器 log 承擔。同時結案 L-10d。 |
| W-5b（備案，不推薦） | `回應產生時間：{formatDateTime(chapter.generated_at)}` | 沿用 V-7B 曾核可的「回應產生時間」補足主體；但仍保留一個絕對時間戳，重現 D-5 的「剛更新」誤讀風險，且 L-10b 已要求 E-4 兩檔不得再用此詞（本備案是另一檔，須風控另判）。缺值由 `formatDateTime` 印「時間不明」（V-8）。 |

W-5 連帶：`LeverageChapterView.tsx` 的 `formatDateTime` import 在本單落地後再無使用處，須一併移除（否則 lint 失敗）；`generated_at` 欄位與型別保留（機器可讀，不做破壞性 API 變更）。

## 7. 詞彙一致性與撞詞檢查（讀 `leverageWording.ts`、`leverageChapterWording.test.ts`、風控 2026-10-03 兩份核可）

| 既有詞彙 | 來源 | 與新字面的關係 |
| --- | --- | --- |
| 「ETF 收盤價觀測值（未還原）」 | `LEVERAGE_DRAG_OBSERVED_ROW_LABEL` | 新字面的「ETF」是同一實體的簡稱，不重用「觀測值」，不撞詞。 |
| 「Gap（觀測值 − naive）」「Gap 拆解：觀測值與 Naive 期望的差距」 | `LEVERAGE_DRAG_GAP_ROW_LABEL`／`LEVERAGE_DRAG_SECTION_TITLE` | 新字面不含 Gap／觀測值／naive；「計算截至」的對象是同一小節的拆解數字，語意銜接。 |
| 「重置（複利）效應」 | `LEVERAGE_DRAG_RESET_EFFECT_LABEL` | 不重疊。W-2 在「橫盤情境侵蝕推估」小節，與「重置效應」無詞彙交集。 |
| 「Naive 期望（β×指數報酬）」「標的指數：」 | 同檔表格列標／偵測段 | 「指數」一詞沿用，不改成「標的指數」以控制長度；W-1 與 W-2 皆用「指數」。 |
| 「對齊計算」「共同交易日」 | `drag.py` L71–L72 假設句（使用者可見） | W-1「計算截至」與 W-1c「共同交易日至」直接呼應此句。 |
| 「資料截至 {日期}」 | `buildDataAsOfBadge`、`DataMetaStatusBadge`、E-4 | W-1、W-2、W-4 同家族。 |
| 已退字面「實際報酬」「實測」「已發生的報酬拆解」 | `leverageChapterWording.test.ts` L235–L242、`test_leverage_neutrality.py` `RETIRED_ZH` | 全不含。 |

既有測試中沒有任何斷言釘住舊兩行或 L101／L252 字面（只有 `componentWordingScan.test.ts` L2624–L2633，見第 9 節），故新字面不與 `leverageChapterWording.test.ts` 既有釘字衝突；該檔 `makeDrag` fixture 需補欄位。

## 8. 禁語自查

逐一比對主案與備案全部字面（W-1／W-1b／W-1c／W-2／W-2b／W-4／W-4b／W-5b）：

| 清單 | 結果 |
| --- | --- |
| `FRONTEND_FORBIDDEN_TERMS`（`adviceWording.ts` L367–L468：保證性、價格目標、擬人化價位、祈使急迫、部位指令、預測確定性、機率洗白、即時性、行銷、候選模式） | 無命中。含「即時」「實時」「及時」「盤中」「最新報價／股價／行情／成交」「即將」「將會」「有望」「可期」等，皆不在字面內。 |
| `shared/forbidden-terms.json`（guarantee 10 詞、price_target 6 詞） | 無命中。 |
| `test_leverage_neutrality.py` `RETIRED_ZH`（「實際報酬」「實測」「已發生的報酬拆解」）與 `BANNED_ZH`（19 詞，含「建議」「保證」「停損」等） | 無命中。 |
| 本任務指定禁語：「最新」「即時」「同步」「取得」 | 無命中。 |
| L-10b E-4 負向清單：「—」「同步」「最新」「即時」「資料時間」「回應產生時間」「皆」「一致」「相同」「不同」 | 主案無命中。**僅 W-5b 含「回應產生時間」**（該檔不在 L-10b 兩檔限制內，須風控另判）。注意「—」掃描只能掃新字面輸出，不能掃整個 `LeverageChapterView.tsx`（L81 既有 `?? "—"`）。 |
| 現檔其餘字串 | 實查 `LeverageChapterView.tsx` 與 `leverageWording.ts`：「最新」「取得」「產生時間」只出現在 L101、L185、L243、L252（即本單範圍）；「即時」「同步」零出現；`leverageWording.ts` 零出現。落地後整檔去註解可斷言不含「最新」「取得」。 |

字面性質：全為資料日期的中性陳述，不含保證、預測、建議、緊迫或行銷語氣。

## 9. 受影響檔案與測試（依 dev-lead 分析補完）

| 檔案 | 變更 |
| --- | --- |
| `apps/stock-desk/frontend/app/position/[symbol]/LeverageChapterView.tsx` | L185 → W-1；L243–L244 → W-2；L101 → W-4（若併入）；L252 → W-5（若併入）；移除 `formatDateTime` import（W-5 為主案時） |
| `apps/stock-desk/frontend/app/lib/leverageWording.ts` | 建議新增具名建構函式（沿用 2026-10-03 核可條件「字面寫成 lib 具名常數並納入掃描」）：W-1 整句、W-2 後半句各一個；檔頭註解加本稿風控核可紀錄路徑 |
| `apps/stock-desk/frontend/app/lib/entryObservationWording.ts` | `formatDataAsOfDate` 改 export 或抽共用檔，行為不變 |
| `apps/stock-desk/frontend/app/lib/types.ts` | `DragDecomposition` 加 `last_bar_date`、`index_last_bar_date`；`ErosionEstimate` 加一欄（欄名待定）；皆 `string \| null` |
| `apps/stock-desk/backend/app/leverage/drag.py`、`erosion.py`、`signals/frame.py` | 附加欄位（dev-lead 方案，字面不影響） |
| `apps/stock-desk/frontend/app/lib/__tests__/componentWordingScan.test.ts` L2624–L2633 | 「新字面就位」中槓桿章節兩條舊斷言改為新字面；**須在 L-10c（建議卡部分，同段）先合併後處理**；新增 K-13 守門：`LeverageChapterView.tsx` 去註解後不得含「取得」「最新」、`.as_of`、`index_as_of`、`erosion.as_of`；W-5 為主案時另加不得含 `generated_at`、`formatDateTime`、「產生時間」 |
| `apps/stock-desk/frontend/app/lib/__tests__/leverageChapterWording.test.ts` | `makeDrag`（L32–L77）補兩個新欄位；新增渲染測試：三者相同仍分列、指數延遲一日、三者皆缺、單欄缺、ISO 時間戳→日期不明、`2026/10/02`→日期不明、今年／非今年（用 `thisYear`，比照 L-10b 要求 1）；erosion 需新增 fixture（現行 `makeChapter` 的 `erosion: null`）；精確 `toBe` 釘住整行，不得放寬 |
| 同上 | 負向守門（比照 L-10b 要求 3，只掃新字面輸出）：以「資料截至：」開頭、「｜」恰 2、「ETF」「指數」「計算截至」各 1；不含「—」「同步」「最新」「即時」「取得」「資料時間」「皆」「一致」「相同」「不同」；`LeverageChapterView.tsx` 不得對三個日期做 `===` |
| 後端測試（dev-lead 清單） | drag ok 兩日期等於各自最大日期、ETF 與指數日期不同、建倉日截斷不影響、空 bars 為 None；erosion ok／不足；service unmapped 為 None、`drag.index_last_bar_date == erosion.<欄>`；API payload 帶新欄；**新增**：`holding.last_bar_date == drag.last_bar_date`（同一份 ETF bars） |
| 既有、預期不受影響 | `test_leverage_neutrality.py`（新字面皆在前端，不進後端字串掃描）、`sharedForbiddenTerms.test.ts`、`E-4` 相關測試（`formatDataAsOfDate` 行為不變） |
| 不在本稿範圍 | L-10e 對比度（`neutral-600`，art-lead，另案）；兩行 class 若被測試釘字須等 art-lead 定案；`DragDecomposition` 型別落後（`index_basis` 等，dev-lead 分析已列） |

## 10. 待風控逐字核可表

| # | 位置 | 逐字字面 | 備案 | 風控請決定 |
| --- | --- | --- | --- | --- |
| W-1 | `LeverageChapterView.tsx` L185 | `資料截至：ETF {D_e}｜指數 {D_i}｜計算截至 {D_w}` | W-1b；W-1c（若不接受「計算」） | 主案／備案；3.2「計算截至」讀碼證據是否採信 |
| W-2 | 同檔 L243–L244 | `波動估計視窗：{observations}／{window} 個報酬｜指數資料截至 {D_i}` | W-2b | 主案／備案 |
| W-3 | 缺值規則 | 各欄獨立印「日期不明」；三份皆缺仍印完整句；永遠分列；無相等判斷、無提示 | — | 是否核可（5 節、3.6） |
| W-3b | `{D_x}` 格式 | 今年 `MM-DD`、非今年 `YYYY-MM-DD`、null／undefined／空／格式不符 → `日期不明` | — | 是否核可（3.5） |
| W-4 | 同檔 L101（相鄰） | `建倉日 {opened_at} ～ 資料截至 {last_bar_date}，共 {n} 個交易日（{m} 曆日）。` | W-4b | 是否併入本單；日期是否維持完整 `YYYY-MM-DD` |
| W-5 | 同檔 L252（相鄰） | 整行拿掉（連帶移除 `formatDateTime` import） | W-5b `回應產生時間：…` | 拿掉或改名；是否同時結案 L-10d |

落地條件建議（風控可增刪）：(a) W-1／W-2 以 lib 具名函式輸出並 `toBe` 逐字釘住；(b) 後端附加欄位與前端同一輪 qa-reviewer；(c) 兩行不得出現「取得」「最新」及任何列層 `as_of`；(d) qa-e2e 於 390px 確認最長句無橫向溢出；(e) 風控就落地 diff 結案；(f) ADR-0019 改 accepted 前須結案（L-10g 原列管條件）。

## 11. 後續步驟

1. risk-compliance-officer 逐字審 W-1～W-5。
2. tech-architect 定 erosion 新欄欄名，並把 K-13 擴大為「前端任何檔案不得以『取得』字樣顯示 `PriceBar.as_of`／訊號層 `as_of`」。
3. dev-lead 依第 9 節實作後端欄位與測試；frontend 在 L-10c 合併後落地字面。
4. art-lead 另案處理 L-10e 對比度；qa-reviewer、qa-e2e 驗收後回風控結案。

## 12. 自我揭露

- 本稿只用 Read、Grep；未改任何程式碼、未跑 vitest／pytest／tsc。
- 「禁語自查」為逐清單人工比對加 Grep，落地後以實跑 wording scan 結果為準。
- 「計算截至」的語意依據為讀碼（`drag.py` L202–L213、L380、L392–L393），未實測指數延遲情境下的實際輸出；dev-lead 的「ETF 與指數日期不同」後端測試即為此驗證。

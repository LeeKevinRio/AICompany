# 關鍵價位參考面板 — 文案定稿（第二版，待風控逐字覆核）

> 前版遭 risk-compliance-officer VETO（R1–R12、S2–S5）。本稿為 creative-lead 依全部否決事項逐條修正之定稿，
> 格式：每條「常數名 → 定稿字面」。字面即最終建議版本，不附選項；佔位符 `{N}` `{D}` `{X}` 由前端在 render 時代入實際數字，
> **佔位符本身與其後之「（給工程）」備註不是文案字面的一部分，不得原樣顯示在畫面上。**
> 一律全形標點；程式碼識別字（MA20、ATR(14)、2R 等）維持半形英數。

---

## 0. 面板標題

**KEY_LEVELS_PANEL_TITLE**
→ 「關鍵價位參考」

**KEY_LEVELS_CLOSE_LINE**
→ 「收盤 {X}（{D}）」
（給工程：{X} = `levels.close` 格式化字串；{D} = `levels.closeDate`。與頁尾樣本句的 {D} 為同一日期。）

---

## 1. 頭部揭露段（面板頂部，緊接標題與收盤列之後，四句依序常駐、不摺疊）

**KEY_LEVELS_PANEL_DISCLAIMER**
→ 「以下數字皆為本面板依固定算式計算之參考水位，僅供研究與教育用途，非投資建議，亦非任何買賣指示；每個數字的計算方式，包括收盤資料的來源，皆在「計算依據」中逐項揭露。」

**KEY_LEVELS_HEADER_NON_REALTIME_REF**
→ 「本面板之資料時效與非即時說明，沿用 `NON_REALTIME_NOTICE`（`app/lib/adviceWording.ts`，逐字引用、不改寫，見該處）。」
（給工程：render 時直接輸出 `NON_REALTIME_NOTICE` 常數本身，本條僅為出處註記；若要在畫面上呈現，應直接插入 `NON_REALTIME_NOTICE` 的值，而非插入這段中文說明文字。）

**KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE**
→ 「本面板不判斷、也不另行標示所使用的日線資料是否已經過舊。」

**KEY_LEVELS_HEADER_UNADJUSTED_NOTICE**（R12，依 `work/stock-desk-關鍵價位-還原權值說明.md` 查證結論）
→ 「以下所有計算皆以未還原權值之原始收盤價進行；跨除權息日之區間、均線與 ATR(14) 可能因此失真。」

**KEY_LEVELS_HEADER_DASH_NOTICE**
→ 「面板中以「—」呈現的欄位，代表可用日線根數尚未達最低計算門檻，並非數值為零或計算結果為零。」

---

## 2. 位階卡

**KEY_LEVELS_RANGE_CARD_TITLE**
→ 「近 {N} 根日線位階」
（給工程：{N} = `min(bars.length, 252)`，即實際用於計算區間高低的根數；不足 252 根時就是實際根數，最多取 252。）

**KEY_LEVELS_ZONE_LABEL_LOW**（S2 中性化）
→ 「區間下緣」

**KEY_LEVELS_ZONE_LABEL_MID**
→ 「區間中段」

**KEY_LEVELS_ZONE_LABEL_HIGH**
→ 「區間上緣」

**KEY_LEVELS_RANGE_LABEL**
→ 「近 {N} 根區間」
（給工程：{N} 同上，與卡片標題同一數字。）

**KEY_LEVELS_MA60_DEVIATION_LABEL**
→ 「對 MA60 乖離」

**KEY_LEVELS_RANGE_NOT_VALUATION_NOTE**
→ 「位階描述價格相對自身近 {N} 根區間的位置，不等於便宜或昂貴的估值判斷。」

**KEY_LEVELS_RANGE_INSUFFICIENT_REASON**
→ 「日線根數不足，本次無法計算區間位階（僅有 {N} 根，至少需要 60 根）。」
（給工程：此句取代原本「—」的位階卡整體顯示；此處 {N} = 實際可用總根數 `bars.length`，與上兩條的 {N} 意義不同，是「不足」情境下的實際根數，用於解釋原因，非用於區間計算。）

---

## 3. 拉回觀察卡

**KEY_LEVELS_PULLBACK_CARD_TITLE**
→ 「拉回觀察參考」
（原「常見拉回參考價位」之「常見」為對外部普遍作法的斷言，依 R8 移除；標題不再含頻率/普遍性字眼。）

**KEY_LEVELS_PULLBACK_EXPLAIN_NOTE**（R8：自述 + 否定式半句）
→ 「本面板固定以 MA20、MA60、近 60 日低點作為拉回觀察區；是否跌破為觀察條件，不是進出指令；並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。」

**KEY_LEVELS_PULLBACK_ROW_MA20**
→ 「MA20」

**KEY_LEVELS_PULLBACK_ROW_MA60**
→ 「MA60」

**KEY_LEVELS_PULLBACK_ROW_RECENT_LOW60**
→ 「近 60 日低點」

---

## 4. 停損參考卡

**KEY_LEVELS_STOP_CARD_TITLE**
→ 「停損參考」

### 三態基準句（R10/R11，依 `anchoredOnCost` 與持倉狀態三分支擇一顯示於卡片副標）

**KEY_LEVELS_STOP_BASIS_HELD_WITH_COST**（(a) 持有且成本可得）
→ 「本卡以你的持倉平均成本 {X} 為基準計算。」

**KEY_LEVELS_STOP_BASIS_CONFIRMED_NOT_HELD**（(b) 確認未持有）
→ 「未持有此標的，以最新收盤 {X} 試算；此數字不是任何進場暗示。」

**KEY_LEVELS_STOP_BASIS_UNKNOWN**（(c) 持倉狀態尚未確認或成本不可得——不得說「未持有」）
→ 「持倉成本尚未取得，暫以最新收盤 {X} 試算。」

（給工程：三句互斥，同一時間只顯示一句；{X} = `levels.anchorPrice` 格式化字串。系統目前的 `anchoredOnCost` 為布林值，只能表達 (a)/(b) 兩態；若要落地 (c)，需要後端/資料層先能區分「查得未持有」與「持倉狀態未知」，是實作缺口，非文案缺口——本次先把三句字面備齊。）

### 兩種條件句（R9，依 `atr14` 是否可得擇一顯示於卡片大字下方）

**KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE**
→ 「大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。」

**KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE**
→ 「ATR(14) 資料不足，大字僅為 −8% 固定停損。」

**KEY_LEVELS_STOP_ROW_ATR**
→ 「2×ATR(14)」

**KEY_LEVELS_STOP_ROW_FIXED_PCT**
→ 「−8% 固定停損」

**KEY_LEVELS_STOP_S5_NEUTRAL_NOTE**（S5：不加百分比、不加指示的中性陳述）
→ 「停損參考水位與最新收盤的相對高低，因基準價與波動不同而不同，可能高於也可能低於最新收盤。」

---

## 5. 停利參考卡

**KEY_LEVELS_TARGET_CARD_TITLE**
→ 「停利參考」

**KEY_LEVELS_TARGET_ANCHOR_CROSS_REF**
→ 「本卡數字所用之基準價，與「停損參考」卡片相同。」

**KEY_LEVELS_TARGET_STANDING_NOTICE**（R5，常駐句，四要素齊備）
→ 「以下數字皆由固定算式自基準價推得，僅為算式計算結果，不代表價格未來會到達此水位；「2R」所稱賺賠比 2:1，僅描述算式中兩個差值之間的比例關係，不代表任何達成機率。」

**KEY_LEVELS_TARGET_ROW_2R**
→ 「2R（賺賠比 2:1）」

**KEY_LEVELS_TARGET_ROW_FIXED_PCT**
→ 「+20% 固定停利」

**KEY_LEVELS_TARGET_ROW_TRAILING_LABEL**
→ 「移動停利觀察」

**KEY_LEVELS_TARGET_ROW_TRAILING_NOTE**（S4：明示未另行計算）
→ 「（與「拉回觀察」卡片的 MA20 為同一數字；系統並未另行計算移動停利水位，僅以跌破 MA20 作為觀察條件）」

---

## 6. 計算依據（逐項揭露，完整版，對應每一個顯示數字）

**KEY_LEVELS_BASIS_CLOSE**（R1：補齊「收盤取自何處」）
→ 「收盤：本面板所有計算所稱之「收盤」，皆為系統行情資料鏈中該標的最近一根日線的收盤價，與面板頂部「收盤 {X}（{D}）」為同一數字。」

**KEY_LEVELS_BASIS_RANGE**（R2：以 {N} 取代「近一年」）
→ 「位階（近 {N} 根區間）＝（收盤 − 近 {N} 根 K 最低價）÷（近 {N} 根 K 最高價 − 近 {N} 根 K 最低價）×100%；{N} 最多取 252 根，不足 252 根時以實際根數計算，未滿 60 根時不計算位階。」

**KEY_LEVELS_BASIS_ZONE**（S2 中性詞 + S3 門檻無實證附註）
→ 「分類：≤30% 標示為「區間下緣」、≥70% 標示為「區間上緣」，其餘標示為「區間中段」；30%／70% 這兩個門檻為本面板自訂之分類標準，並無實證依據，亦非任何機構或研究之結論。」

**KEY_LEVELS_BASIS_MA**
→ 「MA20／MA60＝最近 20／60 根收盤價之簡單平均；對 MA60 乖離＝收盤 ÷ MA60 − 1，以百分比表示。」

**KEY_LEVELS_BASIS_RECENT_LOW60**（R1：補齊此前遺漏的計算依據）
→ 「近 60 日低點＝最近 60 根日線最低價中的最小值。」

**KEY_LEVELS_BASIS_ATR**
→ 「ATR(14)＝最近 14 根日線真實波幅（TR）的簡單平均；未滿 15 根日線時無法計算，本面板不以其他方式估算或填補。」

**KEY_LEVELS_BASIS_STOP**（R3：改指涉「上方停損參考大字」；R8 自述 + 否定式半句）
→ 「停損參考：若 ATR(14) 可得，大字為「基準價 − 2×ATR(14)」與「基準價 × 0.92（固定 −8% 停損）」兩者中較緊（虧損較小）者；若 ATR(14) 不可得，大字僅為「基準價 × 0.92」。本面板固定採 −8% 作為固定停損比例，僅為本面板自訂之算式參數，並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。」

**KEY_LEVELS_BASIS_TARGET**（R3：2R 改指涉「上方停損參考大字」；R8）
→ 「停利參考：2R＝基準價 +2 ×（基準價 − 上方停損參考大字），此為算式定義下賺賠比 2:1 的計算結果，不代表任何達成機率；固定停利＝基準價 × 1.2（本面板固定採 +20%），同樣僅為本面板自訂之算式參數，並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料；「移動停利觀察」顯示的是 MA20 的同一數字，系統並未另行計算移動停利水位，僅以跌破 MA20 作為觀察條件。」

**KEY_LEVELS_BASIS_ANCHOR**（R10/R11 三態，於計算依據中完整重述一次）
→ 「基準價：若持有此標的且成本可得，為持倉平均成本；若持有此標的但持倉成本尚未取得，暫以最新收盤試算；若確認未持有此標的，以最新收盤試算，此數字不是任何進場暗示。」

**KEY_LEVELS_BASIS_PULLBACK**（R8）
→ 「拉回觀察區（MA20、MA60、近 60 日低點）為本面板固定採用之觀察價位；是否跌破為觀察條件，不是進出指令；並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。」

**KEY_LEVELS_BASIS_UNADJUSTED_XREF**（R12，與頭部揭露互相呼應，避免僅埋在收合區塊裡）
→ 「以上計算皆以未還原權值之原始收盤價進行，跨除權息日可能失真；完整說明見面板頂部揭露。」

---

## 7. 無資料狀態句（R4：僅陳述現況，無未來式承諾）

**KEY_LEVELS_NO_DATA_STATEMENT**
→ 「目前沒有可用的日線資料，本面板無法計算任何關鍵價位。」

（原句「資料到位後這裡會自動顯示」為未來式承諾，依 R4 整句刪除，不以其他承諾語句替代。）

---

## 8. 頁尾樣本句

**KEY_LEVELS_FOOTER_SAMPLE**
→ 「計算樣本：{N} 根日線，最後一根 {D}。本面板僅供研究與教育用途，不構成投資建議。」
（給工程：{N} = `levels.barCount`（實際餵入計算的總根數，可能大於或小於 252，與位階卡的 {N} 是不同概念，此處是「總樣本數」）；{D} = `levels.closeDate`，與頭部收盤列同一日期。）

---

## 9. 組裝順序備忘（非文案字面，給工程）

頭部四句固定順序：`KEY_LEVELS_PANEL_DISCLAIMER` → `NON_REALTIME_NOTICE`（原樣，經 `KEY_LEVELS_HEADER_NON_REALTIME_REF` 出處引用）→ `KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE` → `KEY_LEVELS_HEADER_UNADJUSTED_NOTICE`，`KEY_LEVELS_HEADER_DASH_NOTICE` 置於四句之後、卡片區塊之前；四句字級與對比比照 `TradingViewChartPanel.tsx` 揭露句的落地條件（`text-sm` 以上、`text-neutral-300`/`400` 以上、常駐不摺疊），不得以 `text-xs`/`text-neutral-500` 承載。「計算依據」逐項清單可維持 `<details>` 摺疊，但 §6 開頭應加一句「以上計算所用之收盤資料，均受頭部揭露之非即時與未還原權值限制所及」的等效提示（可直接使用 `KEY_LEVELS_BASIS_UNADJUSTED_XREF` 兼作此提示）。

---

## 10. 第二輪補稿（風控第二輪覆核追加，R15／R17）

**KEY_LEVELS_RANGE_FLAT_REASON**（R15：根數足夠但區間最高價＝最低價，除以零無法定義位階）
→ 「本次採樣的 {N} 根日線中，最高價與最低價相同，位階公式的分母為零，無法定義位階。」
（給工程：此句與 §2 的 `KEY_LEVELS_RANGE_INSUFFICIENT_REASON` 是兩種互斥成因，擇一顯示於位階卡整體，不可共用同一句；判斷邏輯為 `bars.length >= 60` 但 `rangeHigh === rangeLow` 時取本句，`bars.length < 60` 時取原句。此處 {N} = 實際用於計算區間高低的根數，即 `min(bars.length, 252)`，與 §2 `KEY_LEVELS_RANGE_LABEL` 的 {N} 同一數字。）

**KEY_LEVELS_BASIS_SECTION_TITLE**（R17：原硬編碼字面納入成稿，照錄現字面）
→ 「計算依據（逐項揭露）」

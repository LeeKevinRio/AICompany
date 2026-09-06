# 個股頁揭露句下沉頁尾 — CEO 裁定與實作方案（2026-09-06）

## 1. CEO 裁定（書面）

- 2026-09-06，CEO 於審閱「圖形化 1–3」成果後指示：**「做第 4 項 揭露句下沉頁尾」**。
- 第 4 項原文（frontend-engineer 提案）：「所有免責與資料揭露統一縮到頁尾一區、字級降為次要；這是目前字數壓不下去的主因，但要你明確同意改風控規範，我才會請 risk-compliance-officer 重審。」
- 本裁定**推翻**下列既有風控落地條件（僅限個股頁 `/position/[symbol]`）：
  - 揭露句「常駐於所屬區塊、≥ text-sm、≥ neutral-400」（關鍵價位 R7／D4 V4、減負 C1、圖形化落地條件 2）。
  - 頁級揭露區「為操作摘要之後第一個區塊、不得再往下移」（減負 C1，P1 改裁）。
  - 「計算依據」常駐於面板內（關鍵價位 R7）。
- 依章程 §0.5 與風控 2026-09-06 第二輪落地條件 5，本裁定之責任歸屬由 CEO 承擔；risk-compliance-officer 保留否決紀錄，並在本方案內劃定**最低保留線**。

## 2. 新規範（本裁定生效後）

1. 個股頁最底部固定一區 **「本頁揭露與計算依據」**（`PageFooterDisclosures`）：常駐、**不摺疊**（不用 `<details>`／line-clamp）、`text-xs text-neutral-500`、依來源區塊分組（資料來源／操作摘要／關鍵價位參考／技術指標／建議卡／槓桿專章）。
2. 每個被抽走揭露句的區塊，於原位保留**一句**指引句（字面由 creative-lead 起草、風控逐字審），指向頁尾。
3. 所有下沉的句子**一字不改**，只改位置與字級；釘住測試改為釘「頁尾渲染」而非「區塊內渲染」。
4. 「圖不取代字」原則不變：圖形編碼的每個數值在頁面上仍有文字形式（可在頁尾）。

## 3. 逐句分類

### A. 留在原位（最低保留線；風控可加項，不得減項）

| 位置 | 句子／元素 | 理由 |
|---|---|---|
| 操作摘要 | 結論大字旁的 `disclaimer`（R3 三件套之一） | 結論與免責同進同退，是全頁唯一必須與結論同視距的法律句 |
| 操作摘要 | `confidenceMeaning`（已是 xs） | 信心等級的定義句，與徽章同視距 |
| 操作摘要 | 反面論點／失效條件清單 | 是內容不是揭露（§2.5） |
| 全頁 | 資料不足／錯誤／資料過舊警示（`InsufficientPanel`、`StaleDataAlert`、`ErrorPanel`、`DataMetaStatusBadge`） | 功能性狀態，非揭露 |
| 關鍵價位 | 停損卡基準價句（三態：成本／未持有試算／未知試算，含「此數字不是任何進場暗示」） | 是大字的標籤 |
| 關鍵價位 | 停損卡「大字為 2×ATR 與 −8% 較緊者」、停利卡「與『停損參考』卡片相同」 | 是大字的標籤 |
| 各區塊 | 五則導讀（tagline） | 已是一句白話 |
| 建議卡 | `ADVICE_CARD_XREF_TO_SUMMARY`（C5 承載句） | C5 紅線的承載體，一句 |
| 技術指標 | 各指標卡 description（已 xs） | 說明指標是什麼，一句 |

### B. 下沉頁尾（依分組）

| 分組 | 句子 | 原位置 |
|---|---|---|
| 資料來源 | `NON_REALTIME_NOTICE`（整個 `PageDisclosureSection` 移到頁尾成為第一組） | 操作摘要之後 |
| 操作摘要 | `candidateEvidenceNotice`、`coverageStatement`、`notComparableNote`、`asOfStatement`、`rulesStatement` | 摘要卡內 |
| 關鍵價位 | `KEY_LEVELS_PANEL_DISCLAIMER`、`…STALENESS_SELF_NOTICE`、`…UNADJUSTED_NOTICE`、`…DASH_NOTICE`、`buildRangeNotValuationNote`、`KEY_LEVELS_PULLBACK_EXPLAIN_NOTE`、`KEY_LEVELS_STOP_S5_NEUTRAL_NOTE`、`KEY_LEVELS_TARGET_STANDING_NOTICE`、`KEY_LEVELS_TARGET_ROW_TRAILING_NOTE`、`KEY_LEVELS_LADDER_NOTE`、整段「計算依據（逐項揭露）」、`buildFooterSample` | 面板內 |
| 技術指標 | `INDICATOR_OVERVIEW_LEGEND` | 速覽區 |
| 建議卡 | `DIRECTION_SHARE_QUALIFIER`、`context_notes`（風險預算輸入的假設與限制） | 卡內 |
| 槓桿專章 | `chapter.disclosure` | 專章頂部 |

### C. 不在本次範圍

- 總覽頁、設定頁、排程台、回測頁的揭露句（本裁定只及個股頁）。
- 後端回傳的 `advice.disclaimer` 字面本身。

## 4. 實作切法

- 新元件 `app/components/PageFooterDisclosures.tsx`：props 為分組後的字串陣列（`FooterGroup { title; items: (string | BasisItem)[] }`），純呈現。
- 各區塊提供純函式組出自己的 footer 項目（`buildKeyLevelsFooterItems(levels, anchorSource)`、`buildSummaryFooterItems(model)` 等），`page.tsx` 在最底部組裝。
- 各區塊原位改渲染指引句常數（單一常數，全頁共用）。
- `componentWordingScan.test.ts`：既有字面釘住不動；「區塊內渲染」守門改為「頁尾渲染」守門；新增「頁尾不摺疊、不 line-clamp」守門；P1 順序守門改為「操作摘要在最前、頁尾揭露在最後」。

## 5. 風控回覆（2026-09-06 第一輪：ACCEPT_WITH_CONDITIONS）

### 5.1 最低保留線增項（A+1～A+10，required，實作已全數留原位）

| # | 句子 | 留原位理由（摘） |
|---|---|---|
| A+1 | `asOfStatement` | 標題列只有抓取時間，不是評估基準交易日；且與日曆未確認警示同一字串 |
| A+2 | `candidateEvidenceNotice` | 唯一說明「0 股假設部位」的句子 |
| A+3 | `notComparableNote` | 直接修飾同列信心等級徽章 |
| A+4 | `DIRECTION_SHARE_QUALIFIER` | 圖形化 R5 成立要件 |
| A+5 | `KEY_LEVELS_PANEL_DISCLAIMER` | advice 失敗、bars 正常時整頁唯一免責；「非任何買賣指示」唯一針對具體價位 |
| A+6 | `KEY_LEVELS_TARGET_STANDING_NOTICE` | 圖形化 R7 成立要件；擋「賺賠比 2:1」讀成勝率 |
| A+7 | `buildRangeNotValuationNote` | 「區間下緣」≠便宜的更正句 |
| A+8 | `INDICATOR_OVERVIEW_LEGEND` | ○◐● 符號的解碼表 |
| A+9 | `KEY_LEVELS_HEADER_DASH_NOTICE` | 「—」的解碼表，擋讀成 0 |
| A+10 | `KEY_LEVELS_LADDER_NOTE` | 圖形化落地條件三句同進退 |

### 5.2 附條件句的實作選擇

- `KEY_LEVELS_HEADER_UNADJUSTED_NOTICE`：**留原位**（維持 `KEY_LEVELS_BASIS_UNADJUSTED_XREF`「見面板頂部揭露」指涉，不改字面）。
- `KEY_LEVELS_PULLBACK_EXPLAIN_NOTE`：**留原位**（維持 `KEY_LEVELS_BASIS_PULLBACK` qualifier「見上方『拉回觀察參考』卡片」指涉）。
- `KEY_LEVELS_TARGET_ROW_TRAILING_NOTE`：**留原位**（避免新字面「MA20 並列標籤」再送審）。
- `context_notes`：**本批不下沉**（風控前置：需 dev-lead／quant-researcher 提供完整字面清單分類）。列管。
- `PAGE_LEVEL_DISCLOSURE_SECTION_INTRO`：**不再渲染**（尾句「另列於對應區塊」在新架構為假陳述；其角色由頁尾導語取代）。常數保留並釘住，待風控第二輪確認是否可退場。
- `chapter.disclosure` 下沉；`chapter.notes` 與 erosion `nature` 留原位（風控條件）。
- 資料來源組指引句：放在原頁級揭露區的位置（操作摘要正下方，`page.tsx`），非塞進操作摘要卡內。

### 5.3 新規範落地（L1–L6）實作對照

- L1：頁尾 `text-xs text-neutral-400`（否決 neutral-500 已採納）。
- L2：守門掃描禁 details／summary／line-clamp／truncate／max-h／overflow-y／hidden／sr-only／aria-expanded／IntersectionObserver／lazy／Suspense／sticky。
- L3：四組順序寫死於 `page.tsx`（資料來源→操作摘要→關鍵價位參考→槓桿型 ETF 專章）；技術分析與建議卡本批無下沉句，不成組。
- L4：組名全部 import 既有標題常數（新增 `sectionTitles.ts`，各區塊 h2 同步改用）。
- L5：指引句 `buildFooterGuidance(groupTitle)`＝「頁尾「{組名}」載明本區資料來源與計算方式。」（creative-lead 候選 C），text-sm／neutral-300。
- L6：守門測試 1–7 已落地（改列 A 十句原位斷言、頁尾渲染、不摺疊、兩層依賴、順序、組名 import、指引句 wiring、下沉句原區塊不再渲染＋builder 逐條）；L6-8 qa-e2e 實機驗收待補（frontend-engineer 先以 Playwright 自測，數字見審查紀錄）。

### 5.4 風控否決紀錄（原文）

> **風控否決紀錄（risk-compliance-officer，2026-09-06）**
>
> 本人於本案中對下列兩項保留否決意見，該否決未獲採納，依公司章程 §0.5 與本案 §1 第 11 行，責任歸屬由 CEO 承擔；本紀錄為書面留存，不因本次 ACCEPT_WITH_CONDITIONS 而失效。
>
> **否決項一：以「頁尾集中、字級降為次要」作為個股頁揭露句的常態架構。**
> 本人先前的落地條件（揭露句常駐於所屬區塊、≥ text-sm、≥ neutral-400；頁級揭露區不得下移；計算依據常駐面板內）並非版面偏好，而是「揭露必須與其所修飾的數字在同一視距內」這一項原則的具體化。把六個區塊的揭露句集中到單一頁尾區，等於在一個逐項揭露的頁面上建立一個「全部限制條件都在別的地方」的結構：使用者取用數字的成本不變，取用該數字之限制條件的成本則被整體提高。本人認為此結構本身即構成揭露的實質弱化，即使每一句字面一字未改、即使頁尾常駐不摺疊。本人接受此裁定並僅劃定最低保留線，不代表本人認為此結構符合誠實揭露的標準。
>
> **否決項二：頁尾區採用 `text-xs text-neutral-500`。**
> Tailwind `neutral-500`(#737373) 對 `neutral-900`(#171717) 的對比比約 3.8:1、對 `neutral-950`(#0a0a0a) 約 4.2:1，均低於 WCAG AA 的 4.5:1 下限。顏色不影響字數，也不影響裁定所欲達成的視覺降權（降權已由字級承擔），因此此項設定所換得的減字為零，所付出的是一段低於無障礙可讀性下限的免責文字。本人 required 顏色維持 `neutral-400`（7.1:1），並就此保留否決紀錄。
>
> **附記（不屬否決，屬事實記載）：** 本次 §3-A 增列的 10 句中，有 6 句是 2026-09-05 與 2026-09-06 兩批審查甫落地的裁定要件（R1、R5、R6、R7 與 P1 維持條件 (a)(c)）。若這 6 句在後續實作中被以「已納入頁尾」為由移出原位，其效果等同於在無新事證的情況下回復上述兩批審查認定的缺陷；屆時本人將依 FR-7／AC-4 直接判定 `BLOCKING_ISSUES`，不再另行協商。

（否決項二已採納：頁尾字色為 neutral-400。）

### 5.5 風控第一輪「輸入契約缺口」原文與狀態

1. 指引句字面未起草 → creative-lead。（第二輪：已起草，模板一句退回改寫 R1／R2，見 §6）
2. `PAGE_LEVEL_DISCLOSURE_SECTION_INTRO` 尾句在新架構下成為假陳述 → creative-lead 重寫、逐字重審。（第二輪：**准予退場**，不需改寫；補「不得再渲染」守門）
3. `KEY_LEVELS_BASIS_PULLBACK` qualifier 的「上方…本處」、`KEY_LEVELS_BASIS_UNADJUSTED_XREF` 的「面板頂部揭露」指涉落空 → creative-lead。（實作選擇：兩句被指涉的句子留原位，指涉維持成立，不產生新字面；第二輪核可）
4. `context_notes` 完整可能字面清單 → dev-lead／quant-researcher。（未提供；本批不下沉，列管）
5. 「移動停利觀察」列標籤的原位數字標籤改寫 → creative-lead。（實作選擇：`KEY_LEVELS_TARGET_ROW_TRAILING_NOTE` 留原位，不需新字面；第二輪核可）

## 6. 風控第二輪（2026-09-06）：NEEDS_CHANGES → 指引句改寫

- APPROVE：`PAGE_FOOTER_DISCLOSURES_TITLE`、`PAGE_FOOTER_DISCLOSURES_INTRO`、四個組名常數、A+1～A+10 落地、5.2 附條件句、L1–L4、L6-1～L6-7、INTRO 退場。
- R1（required）：指引句模板只承諾「資料來源與計算方式」，漏掉「揭露事項」一類（槓桿專章組唯一內容是免責句）→ creative-lead 改寫。
- R2（required）：資料來源組的指引句不得自稱「本區」，且該組不含計算方式 → 頁級變體。
- 補件：§5.5 缺口原文；「INTRO 不得再渲染」守門。
- 列管：`context_notes` 下沉前置；qa-e2e L6-8 實機驗收；S1 頁尾 h2 與第一組 h3 字面相近；S3 小標以 `<li list-none>` 承載的 a11y 判斷。

# 六項觀察條件 E-4「資料截至」句——L-10b 字面起草

- 日期：2026-10-04
- 起草：creative-lead
- 狀態：**待 risk-compliance-officer 逐字審**（面向使用者文案，未經風控核可不得落地）
- 性質說明：本件為既定範圍內的字面起草（非發想類任務），未走 creative-masters 五步流程；下列「多版」為字面備案，不是方向發想。
- 關聯：
  - `work/reviews/2026-10-04-個股頁-資料時間標籤-風控審查.md`（L-10b；V-7B 過渡案；R-2）
  - `work/stock-desk-進場觀察條件-PRD.md` §4b L54（「E-4 三份查詢的資料時間」）
  - `work/stock-desk-個股頁-資料時間標籤-字面起草-2026-10-04.md`（前案）
- 讀碼基準（2026-10-04 實讀）：`entryObservationWording.ts` L66–84、`EntryObservationPanel.tsx` L88–98／L164、`page.tsx` L509–517、`componentWordingScan.test.ts` L1898–L1902／L1930。

> 注意：實讀時 `buildDataTimesLine` 仍是 V-7B 之前的字面（`資料時間：…（日線／指標／規則評估同步）`），也就是風控已否決的句子目前仍在 repo 內。若 dev-lead 另有未合併的 V-7B 分支，L-10b 請接在其上；V-7B 與 L-10b 若能同批審過，建議直接落 L-10b，不必先落過渡案。

---

## 1. 設計原則（從風控紀錄與 PRD 推出）

1. **回到 PRD 原意**：E-4 要揭露的是三份查詢「各自的資料截至日」，不是回應時間。來源為各 API 回應的 `data.last_bar_date`（日期，無時分、無時區問題）。
2. **沿用已核可的「資料截至」一族**：日期格式與 `buildDataAsOfBadge` 同一套規則（同年 `MM-DD`、跨年 `YYYY-MM-DD`），逐份各自判斷年份。
3. **不得再出現「同步」**（R-2）：三份日期相同只能陳述「日期相同」這件事實，不得暗示取得時間相同或系統同步。
4. **不新增未查證的主張**：不寫「最新」「即時」，不解釋日期為何不同（原因未查證，見 3.3）。
5. **E-4 不得整句拿掉**（V-7A 已被否決）：任何缺值情形都仍要印出這一句。

---

## 2. 字面提案

### 2.1 三份日期相同（三份皆非 null 且日期字串完全相等）

| 編號 | 字面 | 說明 |
|---|---|---|
| **E4-S-A（主案）** | `資料截至 10-02（日線／指標／規則評估）` | 與徽章同句式「資料截至 {日期}」，括號只標明適用範圍；括號內沿用既有三個名稱與「／」。無「同步」「皆」等主張詞。 |
| E4-S-B（備案） | `日線、指標、規則評估三份查詢，資料截至 10-02` | 較口語、把「三份查詢」明說；句式離徽章一族較遠，且稍長。 |
| E4-S-C（備案：不收合） | 相同時也走分列式：`資料截至：日線 10-02｜指標 10-02｜規則評估 10-02` | 程式最單純（不需要相同判斷，也無分支），讀者永遠看到同一版型；代價是相同時略冗長。 |

跨年範例（今年為 2026，三份皆為去年最後一個交易日）：`資料截至 2025-12-31（日線／指標／規則評估）`。

**推薦 E4-S-A。** 理由：與主視圖三個徽章同句式，讀者一眼認得；一句即完成「三份相同」的揭露；不含任何風控已否決的詞。若風控認為括號會被讀成「同步」之類的暗示，退回 E4-S-C（完全不做相同判斷，自然沒有任何類似主張）。

### 2.2 三份日期不同（含任一份相同、另一份不同的情形）

| 編號 | 字面 | 說明 |
|---|---|---|
| **E4-D-A（主案）** | `資料截至：日線 10-02｜指標 10-02｜規則評估 10-01` | 與現行分列式骨架一致（「日線／指標／規則評估」＋「｜」），只把句首換成「資料截至：」、值換成日期。 |
| E4-D-B（備案） | `資料截至 日線 10-02｜指標 10-02｜規則評估 10-01` | 少一個冒號，更貼近徽章「資料截至 {日期}」的空格句式；但「資料截至 日線」讀起來較斷。 |
| E4-D-C（不建議） | `三份查詢的資料截至日不同：日線 10-02｜指標 10-02｜規則評估 10-01` | 多一句「不同」的明示。不建議的原因：紀錄中沒有「為何不同」的查證（見 3.3），加註句容易被讀成異常警示；日期並列本身已足以讓讀者看出差異。 |

跨年混合範例：`資料截至：日線 01-02｜指標 01-02｜規則評估 2025-12-31`（各份各自判斷年份；跨年那份自帶西元年，不會混淆）。

**推薦 E4-D-A。** 理由：句首加冒號與徽章（無冒號）一眼可分——徽章是「單一日期」、本句是「清單」；骨架與現行一致，改動面最小。

### 2.3 任一份 `last_bar_date` 為 null（含查詢尚未載入、失敗、無日線）

| 編號 | 字面 | 說明 |
|---|---|---|
| **E4-N-A（主案）** | 缺的那一份印「—」，其餘照常，**一律走分列式**：`資料截至：日線 10-02｜指標 —｜規則評估 10-02`；三份全缺：`資料截至：日線 —｜指標 —｜規則評估 —` | 沿用現行「—」處理，零新字面。 |
| E4-N-B（備案） | 缺的那一份印「日期不明」：`資料截至：日線 10-02｜指標 日期不明｜規則評估 10-02` | 與 V-8 已核可的「時間不明」同一語感，把「為什麼是空的」說清楚；代價是新增一個字面，須逐字核可，且全缺時整句偏長。 |
| E4-N-C（不建議） | 整段不顯示 | 見下。 |

**推薦 E4-N-A（沿用「—」、不整段隱藏）。理由：**

1. **不得整段隱藏**：E-4 是 PRD 列的風控要求揭露項，V-7A「整句拿掉」已被否決。全缺時整段消失，等於面板失去任何資料日期，與被否決的做法效果相同。
2. **不收合**：只要有一份缺值就走分列式。「三份相同」的前提是三份都有值且相等；缺一份時把另兩份寫成「資料截至 10-02（日線／指標／規則評估）」會把缺的那份也算進去，是錯誤主張。
3. **位置保留**：分列式讓讀者看到「是哪一份缺」，而不是日期憑空少一個。
4. **語意可接受**：同面板 E-3 已說明「—」代表無法判定、不代表數值為零；日期位置的「—」同樣讀作「沒有可標示的日期」，不會被讀成零或未成立。若風控認為日期位置的「—」仍易與 E-3 的「條件無法判定」混淆，退回 E4-N-B。
5. **來源合理**：後端不變式為「規則評估卡有值 ⇒ `last_bar_date` 有值」，null 只出現在無日線（`test_api_advice.py` L250–L293）；前端查詢尚未成功時 `data` 為 undefined，也歸為 null。這些都是「沒有可標示的日期」，與「—」語意相符。

空字串視同 null（與 `buildDataAsOfBadge` 現行對 `""` 的處理一致）。

---

## 3. 與同頁其他「資料截至」徽章的關係（交風控決定）

### 3.1 同頁現有的「資料截至」

| 位置 | 內容 | 資料來源 | 是否在摺疊內 |
|---|---|---|---|
| `DecisionCard.tsx` L363 | `資料截至 MM-DD` | advice `last_bar_date` | 主視圖 |
| `OperationSummaryPanel.tsx` L94 | `資料截至 MM-DD` | advice `last_bar_date` | 主視圖 |
| `page.tsx` L286 | `資料截至 MM-DD`（技術分析標題列，註解稱「本區塊唯一的資料截至徽章」） | bars `last_bar_date` | 主視圖 |
| `AdviceCardView.tsx` L129 | 同一徽章字面 | advice `last_bar_date` | 建議卡摺疊內 |
| `DataMetaStatusBadge.tsx` L35／L41–42 | `…資料截至 {YYYY-MM-DD}…`（僅快取分支的完整版） | 各查詢自己的 `last_bar_date` | 摺疊內 |
| `TechnicalIndicatorsPanel.tsx` L535／L557 | `資料截至 {YYYY-MM-DD}`（回撤） | signals `last_bar_date` | 技術分析詳細 |

### 3.2 會不會重複

- **資訊上不算重複**：上列每一處只對應「它所在區塊」的單一日期；E-4 是唯一把 bars／signals／advice 三份並排的地方，也是唯一能讓讀者看出「三份日期不一致」的地方。signals 的日期在主視圖沒有任何徽章（技術分析標題列的徽章取的是 bars）。
- **字面上會有重複**：三份相同時，E-4（`資料截至 10-02（日線／指標／規則評估）`）會與決策卡、操作摘要、技術分析的徽章同日期並列出現。但 E-4 在「詳細：六條逐項明細」摺疊內（CEO 2026-09-19 第二次裁定），不佔主視圖。
- **E-4 的獨有價值**：日期相同時是確認、日期不同時是唯一的揭露；若只在不同時才顯示（隱藏相同情形），就違反「E-4 為常駐揭露項」的 PRD 要求。

### 3.3 選項（請風控裁示）

| 選項 | 內容 | creative-lead 意見 |
|---|---|---|
| **R-1（推薦）** | 全部保留：E-4 為三份並排揭露，其餘徽章各自綁定所在區塊，互不調整。 | 各處已在先前審查核可，且資訊範圍不同；動它們會牽動多個已釘住的測試與先前裁示。 |
| R-2 | E-4 只在三份不同時顯示。 | 不建議。違反 PRD「E-4 常駐」，且相同時用戶看不到這句，反而不知道三份已被比對過。 |
| R-3 | 拿掉技術分析標題列的徽章（因 E-4 已涵蓋 bars）。 | 不建議。該徽章在主視圖，E-4 在摺疊內，等於把主視圖的 bars 日期降到摺疊內；且該處是 CEO wave3 刻意保留的。 |

補充兩點供風控留意：

1. 日期不同的「原因」目前沒有查證（可能是三個查詢各自重抓、冷卻期、跨日邊界；dev-lead 尚未提供可重現例，見末段清單）。本稿因此不放任何解釋句。
2. E-4 只陳述日期，不陳述「是否為最近交易日」。資料新舊由既有的狀態 chip 與 `StaleDataAlert` 承擔，E-4 不重複、也不暗示。

---

## 4. 現行 REQ-3 同步判斷與釘住測試（讀碼結果）

### 4.1 現行邏輯

- `EntryObservationPanel.tsx` L91–98：把三個 ISO 時間字串各自 `formatDateTime` 成顯示字串；`synchronized` 由**原始 ISO 字串**三者全等判斷（風控 REQ-3：不得用分鐘取整後的顯示字串判斷）。
- `entryObservationWording.ts` L70–84：`synchronized && bars !== null` 時印收合句，否則印分列式；缺值印「—」。
- 呼叫端 `page.tsx` L509–517：傳 `bars.data?.as_of`／`signals.data?.as_of`／`advice.data?.as_of`（皆為回應 `now_iso()`）。

L-10b 之後：REQ-3 的原意（用原始值判斷、不用顯示字串）仍應保留——比較對象改為原始 `last_bar_date`（`YYYY-MM-DD`）。因為日期格式化是單射（同年 `MM-DD`、非同年 `YYYY-MM-DD`），顯示相等與原始相等實務上等價，但仍建議以原始值比較，維持 REQ-3 精神與測試語意。

### 4.2 受影響檔案

| 檔案 | 位置 | 變動 |
|---|---|---|
| `apps/stock-desk/frontend/app/lib/entryObservationWording.ts` | L66–84（函式與 doc comment） | 函式改為吃三份 `last_bar_date`、輸出 2.1／2.2／2.3 字面；doc comment（「full `formatDateTime` output — the year is never dropped」、REQ-3 說明）整段過時，須重寫。 |
| `apps/stock-desk/frontend/app/lib/oneLinerWording.ts` | L47–54 | 建議把日期格式化抽出為共用 helper（回傳 `MM-DD`／`YYYY-MM-DD`／null），`buildDataAsOfBadge` 改用它組句；E-4 與徽章共用同一份年份邏輯，避免兩處漂移。`buildDataAsOfBadge` 輸出不得變。 |
| `apps/stock-desk/frontend/app/position/[symbol]/EntryObservationPanel.tsx` | L17（`formatDateTime` import）、L88–98、L164 及 L125–129 註解 | 刪除 `formatDateTime` 轉換與 `synchronized` 計算（或改為日期比較）；`dataTimes` prop 語意由「as_of 時間戳」改為「last_bar_date」，**建議改名**（例如 `dataAsOfDates`）以免誤接；`formatDateTime` import 若不再使用須移除，避免 lint／tsc 未使用警告。 |
| `apps/stock-desk/frontend/app/position/[symbol]/page.tsx` | L509–517（props）、L281 註解（寫「沿用 `buildDataTimesLine` 既有字面」） | 三個值改接 `*.data?.data.last_bar_date ?? null`；註解同步更新。 |
| `apps/stock-desk/frontend/app/lib/__tests__/componentWordingScan.test.ts` | 見 4.3 | 精確字串與結構斷言全部要換。 |

### 4.3 受影響測試（`componentWordingScan.test.ts`）

| 行 | 現況 | 須改成 |
|---|---|---|
| L177 | import `buildDataTimesLine` | 若函式改名則同步；**建議保留函式名**可少動三處斷言（見 4.4）。 |
| L1829–1831 | `CONSTANTS` 內 `times`／`timesSame`／`timesMissing` 以 `"A"`/`"B"`/`"C"` 呼叫 | 改餵日期字串或改用 E4 新函式；進入 T1／T2 的禁用詞、裸「即時」、組合禁語掃描（L1846–1864）。 |
| **L1898–L1902** | 四組精確輸出（`資料時間：日線 A｜指標 B｜規則評估 C` 等；含 `A,A,A,true`＝「…同步」） | 全數替換為新精確字串（見 5. 的測試案例表）；**不得放寬**（不得改成 `toContain`／regex）。 |
| L1930 | `expect(panelSrc).toContain("dataTimes.bars === dataTimes.signals && dataTimes.signals === dataTimes.advice")` | 原始碼字串釘住，新比較式（或函式內判斷）落地後必須同步改；若判斷移進 wording 函式，此行改為斷言 panel 不再自行判斷，並由函式單元測試覆蓋相同判斷。 |
| L1744、L1931 | 斷言 `{buildDataTimesLine(` 出現在 `<details>` 之後／panel 原始碼內 | 函式改名則同步；位置斷言（只出現在 `<details>` 內）保留。 |
| L1927、L1934–1935、L1739 等註解／標題 | 提到「同步」「資料時間句」 | 註解與 it 標題改述（「同步」一詞不得留在使用者可見字面；測試標題非使用者可見，但建議一併去除以免日後 grep 誤判）。 |
| L2039–2043（`buildDataAsOfBadge` 測試） | 同年／跨年／null | 不變，須維持綠燈（證明抽 helper 沒有改動徽章輸出）。 |
| 新增 | — | (a) 負向守門：E-4 輸出不得含「同步」「最新」「即時」「資料時間：」「回應產生時間」；(b) 逐一測試 5. 的案例表；(c) panel 渲染測試：三份相同／相異／含 null 各一，確認落在 `<details>` 內。 |

### 4.4 命名建議（交 dev-lead 決定）

函式名 `buildDataTimesLine` 與 `dataTimes` 都帶「times」，與新語意（日期）不符。建議改為 `buildDataAsOfLine`／`dataAsOfDates`；若 dev-lead 為縮小改動面保留原名，須在 doc comment 明寫「此處的 times 指日期」，並由風控決定可接受與否。兩種做法都不影響使用者可見字面。

---

## 5. 測試案例表（建議落地斷言；今年以 `thisYear` 變數表示，與 L2039–2043 作法一致）

| # | 輸入（bars, signals, advice） | 預期輸出 |
|---|---|---|
| 1 | `${thisYear}-10-02` ×3 | `資料截至 10-02（日線／指標／規則評估）` |
| 2 | `${thisYear}-10-02`, `${thisYear}-10-02`, `${thisYear}-10-01` | `資料截至：日線 10-02｜指標 10-02｜規則評估 10-01` |
| 3 | `${thisYear - 1}-12-31` ×3 | `資料截至 ${thisYear - 1}-12-31（日線／指標／規則評估）` |
| 4 | `${thisYear}-01-02`, `${thisYear}-01-02`, `${thisYear - 1}-12-31` | `資料截至：日線 01-02｜指標 01-02｜規則評估 ${thisYear - 1}-12-31` |
| 5 | `${thisYear}-10-02`, null, `${thisYear}-10-02` | `資料截至：日線 10-02｜指標 —｜規則評估 10-02`（不收合） |
| 6 | null ×3 | `資料截至：日線 —｜指標 —｜規則評估 —` |
| 7 | `""`, `${thisYear}-10-02`, `${thisYear}-10-02` | `資料截至：日線 —｜指標 10-02｜規則評估 10-02`（空字串視同 null、不收合） |

（以上為主案字面；若風控改選備案，本表隨之替換。）

---

## 6. 禁語自查

依據：`FRONTEND_FORBIDDEN_TERMS`（`apps/stock-desk/frontend/app/lib/adviceWording.ts` L367–L468）、`apps/stock-desk/shared/forbidden-terms.json`（guarantee／price_target 兩類）、T1 組合正則（`componentWordingScan.test.ts` L1847–1853）、`findBareRealtimeClaims`，以及本案額外禁用：「最新」「即時」「同步」。

| 字面 | 命中 FRONTEND_FORBIDDEN_TERMS | 命中 shared JSON | 命中 T1 組合正則 | 「最新」「即時」「同步」 |
|---|---|---|---|---|
| E4-S-A `資料截至 10-02（日線／指標／規則評估）` | 否 | 否 | 否（含「評估」，但組合正則的「評分／得分／等級」等不含此詞） | 無 |
| E4-S-B `日線、指標、規則評估三份查詢，資料截至 10-02` | 否 | 否 | 否 | 無 |
| E4-S-C／E4-D-A `資料截至：日線 10-02｜指標 10-02｜規則評估 10-01` | 否 | 否 | 否 | 無 |
| E4-D-B | 否 | 否 | 否 | 無 |
| E4-D-C `三份查詢的資料截至日不同：…` | 否 | 否 | 否 | 無（但不建議，理由見 2.2） |
| E4-N-A `…指標 —…` | 否 | 否 | 否 | 無 |
| E4-N-B `…指標 日期不明…` | 否 | 否 | 否 | 無 |

自查方法：逐一對照上述清單的每個詞條做子字串比對；「指標」「評估」「截至」「日線」皆不在清單內。最終結果以落地後實跑 wording scan 為準，不以本表為準。

另自查：全文不含「保證」「一定會」「目標價」「立即」「即將」「精準」等任何清單詞；不含「最新」「即時」「同步」「皆」「已更新」等會被讀成新鮮度或同步主張的字眼。

---

## 7. 待風控逐字核可

| 編號 | 位置 | 字面（逐字，含標點） | creative-lead 推薦 | 風控裁示 |
|---|---|---|---|---|
| E4-S-A | `buildDataTimesLine`（或改名後）三份皆有值且日期相同 | `資料截至 10-02（日線／指標／規則評估）`（日期依實際值，格式見 2.1） | 主案 | 待審 |
| E4-S-B | 同上 | `日線、指標、規則評估三份查詢，資料截至 10-02` | 備案 | 待審 |
| E4-S-C | 同上（不收合） | 相同時亦用分列式（字面同 E4-D-A） | 備案（若 E4-S-A 被否決） | 待審 |
| E4-D-A | 三份日期不同，或有任一份缺值 | `資料截至：日線 10-02｜指標 10-02｜規則評估 10-01`（日期依實際值） | 主案 | 待審 |
| E4-D-B | 同上 | `資料截至 日線 10-02｜指標 10-02｜規則評估 10-01` | 備案 | 待審 |
| E4-D-C | 同上 | `三份查詢的資料截至日不同：…` | 不建議 | 待審 |
| E4-N-A | 任一份 `last_bar_date` 為 null（或空字串） | 該份印「—」，一律走分列式，不收合、不整段隱藏 | 主案 | 待審 |
| E4-N-B | 同上 | 該份印「日期不明」 | 備案 | 待審 |
| E4-X | 同頁其他「資料截至」徽章 | 選項 R-1／R-2／R-3（見 3.3） | R-1 | 待審 |
| E4-F | 句首格式 | 日期格式沿用 `buildDataAsOfBadge`（同年 `MM-DD`、跨年 `YYYY-MM-DD`），逐份各自判斷年份 | 沿用 | 待審 |

另請風控確認三件事：

1. L-10b 核可後，V-7B 過渡字面（`回應產生時間：…`）是否直接以 L-10b 取代、不必先落地。
2. E4-S-A 括號「（日線／指標／規則評估）」是否可接受（它只表示「這個日期適用於哪三份」，不含取得時間的主張）。
3. L-10 標 done 的條件是否為：L-10b 落地、wording scan 實跑全綠、負向守門就位。

---

## 8. 待 dev-lead 確認接線

| # | 項目 | 讀碼初判（creative-lead，待 dev-lead 確認） |
|---|---|---|
| W-1 | 三份 `last_bar_date` 是否都能從現有 API 回應取得 | **可以，無須新 API 欄位。** 型別 `DataMeta.last_bar_date: string \| null`（`lib/types.ts` L337），`BarsResponse`／`SignalsResponse`／`AdviceResponse` 皆 `extends EnvelopeBase`（含 `data: DataMeta`）。後端三個端點皆回 `data=data_meta(loaded.meta())`（`api/bars.py` L104、`api/signals.py` L102／L123、`api/advice.py` L213／L235），`last_bar_date` 為載入日線的 `max(bar.date)`（`services/market.py` L88–L102）。前端對應路徑：`bars.data?.data.last_bar_date`、`signals.data?.data.last_bar_date`、`advice.data?.data.last_bar_date`；`page.tsx` L286／L298／L312 與 `OperationSummaryPanel.tsx` L94 已在讀同樣欄位。 |
| W-2 | 三份是否各自獨立載入 | 初判是（三個端點各自 `load_bars`，lookback 預設不同），因此日期可能不一致；請列出真實可重現路徑（冷卻期、REFETCH、跨日邊界），供風控判斷 E4-D 是否需要補充說明。 |
| W-3 | null 的實際成因 | 請確認：(a) 查詢 pending／error 時 `data` 為 undefined（歸 null）；(b) `insufficient_data` 且零根日線時 `last_bar_date` 為 null；(c) 後端不變式「有 advice 卡 ⇒ `last_bar_date` 非 null」仍成立（`test_api_advice.py` L250–L293）。 |
| W-4 | `prop` 改名與函式改名 | `dataTimes`→（建議）`dataAsOfDates`、`buildDataTimesLine`→（建議）`buildDataAsOfLine`；同步更新 `componentWordingScan.test.ts` 的 import 與 L1744／L1829–1831／L1898–1902／L1930／L1931。 |
| W-5 | 日期 helper 抽出 | 從 `buildDataAsOfBadge` 抽共用 helper（見 4.2），並確認 `entryObservationWording.ts` 引用 `oneLinerWording.ts` 不產生循環相依（後者目前無 import）。 |
| W-6 | 與 V-7B 的先後 | 確認 V-7B 是否已在分支內；若已有，L-10b 疊在其上，並保留 V-7B 要求的「落地後實跑 wording scan」。 |
| W-7 | 順手清理 | `EntryObservationPanel.tsx` 的 `formatDateTime` import 若不再使用須移除；`page.tsx` L281 註解、`componentWordingScan.test.ts` 內「同步」字樣的註解與測試標題一併改述。 |
| W-8 | 落地後驗證 | 實跑 `componentWordingScan.test.ts`（含 T1／T2）、`oneLinerWording` 相關測試（L2039–2043 須維持綠）、typecheck；回報測試結果給風控。 |

---

## 9. 後續步驟

1. dev-lead 回覆 W-1～W-3（含 W-2 的可重現例）。
2. 風控逐字核可第 7 節（含四個選項的裁示）。
3. 核可後 frontend 依第 4、5 節落地並跑測試，qa-reviewer 審查（含 Codex 第二意見），再送風控確認 L-10b 結案、L-10 才可標 done。

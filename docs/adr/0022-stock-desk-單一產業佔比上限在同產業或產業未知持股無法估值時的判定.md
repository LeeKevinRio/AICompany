# ADR-0022：stock-desk 單一產業佔比上限在同產業或產業未知持股無法估值時的判定

- 狀態：**proposed**
  - accepted 條件（兩者須同時成立）：(1) W1～W6 字面經 risk-compliance-officer **逐字核可**；(2) 2026-10-07 風控路線裁定未被 CEO 推翻。
  - 目前：W1～W6 **尚未核可**（任務單狀態為「待 W1～W6 字面核可」）；核可前不得實作字面、本 ADR 不得改為 accepted。
- 日期：2026-10-07（tech-architect 評估與風控路線裁定日）
- 決策者：tech-architect（路線 C′ 評估）；risk-compliance-officer（路線裁定：APPROVE 附條件）；CEO 為最終負責人（若對裁定有異議）。
- 適用範圍：僅 product/stock-desk 產品線。
- 來源與版本（B 類轉錄）：
  - 唯一來源：`work/dispatch/2026-10-07-任務單-產業上限對同產業未估值持股的判定與揭露.md` 中兩段——「tech-architect 評估（2026-10-07，HEAD b92cbbd 唯讀；coordinator 轉錄）」與「風控路線裁定（2026-10-07，唯讀讀碼，coordinator 轉錄）」。
  - 本檔為 tech-writer 落檔，**技術內容未增補、結論未改動**；Decision、K-n、required 編號（1-a～6-c）皆沿用來源。
  - 來源內所有 `檔案:行號`（`engine.py:354-363`、`limits.py:868-895`、`book_limits.py:105-120`、`book_limits.py:132` 等）、函式名、常數名、測試名與行號皆為 tech-architect／風控所述，tech-writer 落檔時**未重新對 code 驗證**；行號會隨 commit 漂移，引用時以原文定位。
  - 落檔時的快照：分支 `product/stock-desk`，HEAD `8e8ccb59fe62e2ec4c66a2c28c86ce7c8ff5bded`（tech-writer 讀取 `.git/refs/heads/product/stock-desk`）。tech-architect 評估所用 HEAD 為 `b92cbbd`，兩者不同，此為快照。
  - 編號說明：落檔時 `docs/adr/` 最後一份為 0021；repo 內查無 ADR-0022 或 `0022-` 的引用，故使用 0022。
  - 字面（W1～W6）：本檔**不收錄任何字面**，只記範圍與限制；核可字面以日後風控審查紀錄為準，避免兩處漂移。

---

## 關聯

- ADR-0005 決策五第 1 點（`docs/adr/0005-stock-desk-指數來源與美股額度管理.md` L214）：`app/advice/book.py` 維持純函式、不得 import 任何 adapter。任務單稱「ADR-0005 決策 1」，F-1 任務單稱「ADR-0005 決策 5」；tech-writer 讀 ADR-0005 後確認 book.py 純函式約束位於「決策五」第 1 點，本檔以此為準。
- F-1：`work/dispatch/2026-10-07-任務單-F-1-組合估值對不可用收盤價的防護.md`。本單不與 F-1 同版、不同 PR、不作 F-1 部署前置（見 K-10）。
- S-B2：`work/reviews/2026-10-07-S-B2-風險上限any規則-未評估揭露-字面-風控審查.md`（失效條件 1、4；列管 2）。
- 另開單（本 ADR 不處理）：6-a、6-b；6-c 交 tech-architect（見「Consequences」）。
  - 6-a：`work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md`
  - 6-b：`work/dispatch/2026-10-07-任務單-6-b-總曝險上限帳本不完整但已超標時不擋加碼.md`
- 依據：2026-08-09 `/limits` 路線 (a)（`SECTOR_UNVALUED_EXCLUSION_SUFFIX`，風控核可；來源為任務單所述，本檔未另行查證其審查檔）。

---

## Context（背景）

以下皆為任務單「問題」「tech-architect 評估」所述：

1. 決策卡「單一標的產業佔比上限」（第 2 條，`app/advice/limits.py:868-895`）以**已估值產業市值／已估值總資產**計算。同產業有未估值持股 x 時，算出 (S−x)/(E−x)，比真值 S/E 小，**算出值為下限**，可能**錯誤通過**。此上限擋的是「加碼」，錯誤通過屬危險方向。
2. 同一張卡的 context notes `UNVALUED_POSITIONS_NOTE` 宣稱「比率會因此偏高」。等於在可能偏低的通過判定旁宣稱比率保守。（更正：該常數位於 `app/advice/book.py` 約 L149-168，非 `book_limits.py:105-120`；後者為 `UNVALUED_EXCLUSION_SUFFIX`／`SECTOR_UNVALUED_EXCLUSION_SUFFIX`。）
3. `/api/portfolio/limits` 已有 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`（2026-08-09 路線 (a)，風控核可）揭露「比率可能偏低」；決策卡與警示路徑沒有。
4. 總曝險上限（第 3 條）前例：`_check_gross_exposure` 在帳本有未估值持股時**一律** not_evaluable。
5. `app/advice/engine.py:354-363` 只有 `violated` 擋加碼；`not_evaluable` 不擋。
6. 此為既存問題，F-1 修前即存在；F-1 修後總曝險改 not_evaluable 為淨改善，故不擋 F-1。
7. 底線（風控）：只要有未估值持股屬於（或**可能屬於**）該產業，決策卡與警示的產業上限**不得在附著「偏高」宣稱的情況下回報 passed**。

### 分類與數學方向（對卡片產業 X）

- **same**：與卡片同一標的，或 `u.sector == X` 的未估值持股（含本標的自身未估值批次）。
- **unknown**：`u.sector is None` 的未估值持股，**三子類分列計數**：台股未填產業、ETF、非台股。三子類判定時皆併成 unknown。
- **other**：sector 有值且 ≠ X。

| 未估值持股組成 | 算出值方向 | 結論 |
|---|---|---|
| 只有 other | 偏高 | 保守，「偏高」屬實 |
| 只有 same | 為下限 | passed 不可靠；violated 必成立 |
| same ＋ other／unknown | 方向不定 | passed 不可靠 |
| 只有 unknown | 方向不定 | passed 不可靠 |

---

## Options（選項比較）

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| A 原樣（比照第 3 條） | 有同產業未估值一律 not_evaluable | 與第 3 條一致 | 把**可證明的超標**轉成 not_evaluable；`engine.py:354-363` 只有 violated 擋加碼，會放行加碼 | 危險方向退步，**否決** |
| B | 已知同產業仍 passed，附揭露 | 改動小 | 已知同產業仍 passed；試算仍用偏低的產業市值；警示 quiet 路徑讀不到 detail | **否決** |
| **C′（採用）** | 已知同產業：≥ 上限維持 violated（附 W2），否則 not_evaluable（附 W1）；只有產業未知：passed 附 W3、violated 不變 | 永不以可能偏低比率回 passed；可證明超標照擋 | 與第 3 條不對稱；新增字面 ≥ 3 句 | 見 Consequences |
| 加強版（可選開關） | C′ 且 unknown 的 passed 也改 not_evaluable | 更保守 | 帳本任一 ETF／美股／未填產業未估值即整本降級 | 風控裁定**不採用**（見 Decision 與 Consequences） |

---

## Decision（決策）

選 **路線 C′**（tech-architect 評估；風控 2026-10-07 裁定 APPROVE 附條件）。

1. **分類只做一次、放進 `PortfolioContext` 新欄位。** `build_book_context` 對未估值持股依上述 same／unknown／other 分類一次，結果放入 `PortfolioContext` 新欄位（同產業筆數；產業未知筆數按三子類分列；本標的自身未估值批次數另記）。`book.py` 仍為純函式（ADR-0005 決策五第 1 點、F-1 約束）。
   - 三子類皆算「可能屬於」（風控裁定 5，required 5-a）：新欄位按三子類分列計數，判定時併成 unknown。
   - 「本標的自身未估值批次數」分開記為風控 suggested（裁定 6-a）。
2. **新欄位退路（未設定時）：**`book_fully_valued is True` 視為無重疊；否則視為「**產業未知**」。**不猜「同產業」，也不猜「無重疊」**。
3. **`_check_sector_weight` 分支：**
   - same > 0：算出值 ≥ 上限 → **violated**，detail 附 W2；否則 → **not_evaluable**，detail 附 W1，`observed` 為 None，`threshold` 照舊。
   - same = 0 且 unknown > 0：violated 不變；**passed 附 W3**。
   - 重疊皆 0（或 `book_fully_valued is True`）：status／detail／observed **逐字不變**。
4. **`notional_caps` 排除：**same 或 unknown > 0 時，第 2 條**不放進** `notional_caps`。「第 2 條可否被試算採用」為單一判斷式，與 `_check_sector_weight` 共用。
5. **「比率會因此偏高」依分支條件表收窄**（W4／W5）；W1～W6 的字面由 creative-lead 起草、**風控逐字核可**，核可前不得實作字面。
   - W1：第 2 條 not_evaluable（同產業有未估值）。
   - W2：附 violated 後（會進推播）。
   - W3：附 passed 後（產業未知）。
   - W4／W5：`UNVALUED_POSITIONS_NOTE` 的 live／cache_only 版，依決策卡／`/limits` 兩範圍收窄，方向子句自成因句拆出（動到 cache_only 2026-09-18 三審固定句，須一併送審）。
   - W6：`/limits` 中產業已知（Y）且**不在比較中**的未估值持股排除句。
   - 檢查 `WORST_SECTOR_PREFIX`「帳本內 {count} 個產業」不成立時附 W7。
   - 字面範圍與限制（轉錄自風控補充）：
     - W1 句構三處通用；要講成因（同產業或本標的 N 筆無法估值、分子不完整只會偏低故不計算），不印比率。
     - W2 誠實度（required 2-b）：只有「全部 same」時才是下限；否則方向不定、violated 為保守處理。不得宣稱下限或「實際只會更高」（除專屬變體）；要說明比率只用已估值部分、有同產業持股無法估值、本條以已達上限處理；進推播不得有賣出指示或催促。
     - W3（required 5-b）：主詞、三子類、不帶筆數；**不得說「屬於」，只能說無法判斷**；對 ETF／非台股不得出現「請填產業」類指引（D6 先例）；接 `WORST_SECTOR_PREFIX`。W3 與 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 同義但**不可直接沿用**（「此標的」會指成卡片標的、「本條上限的比較未納入此標的」在決策卡不成立）。
     - W4／W5：cache_only 成因逐字保留；表一 d（本標的自身未估值批次）須明示第 1、5 條偏低、第 4 條方向不定（過渡期 required，見 6-a）。
     - W6 只用於 Y 不在比較中。
     - 通則：無保證字眼、不寫「安全」「暫無問題」、推播不含操作指示。

### 分支條件表（轉錄，不含字面）

**表一：決策卡（標的 X）**

| # | 未估值持股組成 | 第 1 條 | 第 2 條 | 第 4 條 | 第 5 條 | 「偏高」全部成立？ |
|---|---|---|---|---|---|---|
| a | 全是其他標的的 other | 偏高 | 偏高，判定照舊 | 偏高 | 偏高 | 成立 |
| b | 含其他標的的 same，無本標的批次 | 偏高 | 未達上限 not_evaluable（W1）；已達 violated（W2），比率只在「全部 same」時為下限，否則方向不定 | 偏高 | 偏高 | 第 1／4／5 成立；第 2 不適用或不成立 |
| c | 含 unknown，不含 same | 偏高 | 方向不定；passed 接 W3；violated 照舊 | 偏高 | 偏高 | 第 1／4／5 成立；第 2 方向不定 |
| d | 含本標的自身未估值批次（另有 `SYMBOL_UNVALUED_NOTE`；第 2 條依 b） | 偏低 | 同 b | 方向不定 | 偏低 | 不成立 |

**表二：`/limits` notes**：e 一律第 1／4／5 偏高成立；f 被回報產業 Y 無 same 且帳本無 unknown → 第 2 偏高成立；g 帳本有任何 unknown → 第 2 方向不定（排除清單已有 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`）；h Y 有 same → 候選者轉 excluded 或以 violated 留下。

**表三：`SECTOR_UNVALUED_EXCLUSION_SUFFIX`（W6，現行既存失準）**：h 的 sector None → 續用；sector 已知 Y 且 Y 在比較中 → 成立但偏弱；sector 已知 Y 且 Y 不在比較中（**現在就已發生**）→ 字面不成立，需另句。

---

## 與第 3 條（總曝險）的非對稱

風控裁定 2（同意）、required 2-a：理由、與第 3 條的差異、`engine.py:354-363` 依據須寫進本 ADR。

- **第 3 條**（`_check_gross_exposure`）：帳本有未估值持股時**一律** not_evaluable。
- **第 2 條（本 ADR）**：已知同產業時，算出值 ≥ 上限**維持 violated**，只在未達上限時才 not_evaluable。
- **理由**（tech-architect 否決路線 A 的依據）：`engine.py:354-363` 只有 `violated` 擋加碼；若比照第 3 條一律 not_evaluable，會把**可證明的超標**轉成 not_evaluable 而放行加碼（危險方向退步）。分類表：只有 same 時算出值為下限、violated 必成立；same＋other／unknown 時方向不定，violated 為保守處理（W2 不得宣稱下限，見 required 2-b）。
- **差異（需文件化）**：同一帳本狀態下，第 3 條與第 2 條對「已超標但帳本不完整」的處理不同——第 2 條擋、第 3 條不擋。**此差異的第 3 條一側本身是缺口**，另列 6-b（見 Consequences），不在本 ADR 範圍。
- 風控 W2 限制：violated 的比率只在「全部 same」時為下限；其餘為保守處理，字面不得宣稱下限（required 2-b）。

## 對 2026-08-09 `/limits` 路線 (a) 的取代範圍

風控裁定 1（同意）：**只限 same 情境**。

- same：候選者轉 excluded 並以 W1 為由，或 ≥ 上限時以 violated 留下（符合 book_limits 規則 1）。
- **不變**：sector 為 None 的排除句、`EXCLUDED_SUFFIX`、空帳本、`NO_CANDIDATE_DETAIL` 字面照舊；sector None 仍走路線 (a)。
- required 1-a：**W6 與 C′ 判定同一 PR 落地**（C′ 會讓「產業已知 Y、Y 不在比較中」變多）。
- required 1-b：`app/advice/book_limits.py:132` `NO_CANDIDATE_DETAIL` 的**註解**更新（字串不改）。
- required 1-c：`test_advice_book_limits.py:466`「Route (a)」註解寫明 same 走 C′、sector None 仍走路線 (a)。

---

## Consequences（後果）

### 好處

- 決策卡、警示、`/limits` 三路徑一致；永不以可能偏低的比率回 passed；可證明的超標照擋（不退步於現況的擋加碼行為）。
- 「偏高」宣稱依分支收窄，不再與偏低的通過判定並列。
- 重疊皆 0 時第 2 條逐字不變，既有第 2 條測試零修改可作證。

### 代價（照實列）

1. 與第 3 條不對稱，需文件化（見上節）。
2. 新增 ≥ 3 句字面（W1～W3），另 W4／W5 改寫、W6 新增；動到 cache_only 2026-09-18 三審固定句，須一併送審。
3. **W2 經 fired 訊息進推播**，W2 誠實度限制（required 2-b）適用。
4. **只有 unknown 時警示 quiet 路徑讀不到 W3**：S-B2 失效條件 4 禁止把 `snapshot.reason`／`check.detail`／disclosure 接到 quiet reason。結果是 `any` 規則的「其餘已評估的上限皆未違反」會把第 2 條（passed 附 W3）算進去。
   - 風控裁定 4：**接受為殘留，不採加強版**（加強版不改變擋加碼結果、資訊價值大跌；與 AC-12.5 先例一致；reason 目前只在 API JSON）。等級 medium，**併 S-B2 失效條件 1**。
   - **required 4-b：AC-12.5（已估值但未填產業的持股）為同根因**——該情境下第 2 條同樣可能以偏低比率 passed，揭露同樣無法在 quiet 路徑呈現。AC-12.5 揭露於 `apps/stock-desk/backend/app/advice/book.py` 可見（`_unclassified_rollup`、`_sector_unclassified_note`，tech-writer 於 HEAD `8e8ccb5` 讀到其註解與 docstring，行號約 L130、L402-L425，以原文定位；其餘行為未驗證）。
   - required 4-a：S-B2 失效條件 1 重審範圍增列「第 2 條 passed 附 W3 或 AC-12.5 揭露時，『其餘已評估的上限皆未違反』是否需限定」。
5. **只監看 `sector_weight` 的規則**：same 且未達上限時，由 quiet 變 skipped；skipped 句尾「缺少輸入」口徑不精確（再一例；與 S-B2 列管 2 同類）。風控 suggested：併 S-B2 列管 2。
6. **試算排除時**出現既有已核可句「以下上限本次缺少可用資料…」（風控裁定 3：三情境皆適當，**字面一字不改**）。風控 suggested：qa-e2e 抽驗 violated＋reduce 時卡片並列「第 2 條 violated」與「第 2 條未參與計算」，375 寬是否讀得通。
7. **`/limits` 行為變更**：第 2 條在 same 情境取代 2026-08-09 路線 (a)（範圍見上節）。

### 附帶列管（不屬本 ADR 決策，不擋本單）

- **6-a**（high，另開單）：決策卡第 1、5 條在本標的有未估值批次時，可能以偏低比率錯誤通過、不擋加碼（表一 d）。過渡期 required：W4／W5 在表一 d 須明示第 1、5 條偏低、第 4 條方向不定。
- **6-b**（high，另開單，**不作 F-1 部署前置**）：第 3 條帳本不完整但已估值部分已超標時回 not_evaluable，不擋加碼。修法前提交 tech-architect 確認分子單調（無負市值／空頭；F-1 拒收 close ≤ 0 後再確認）。CEO 知悉：F-1 會擴大 6-b 適用範圍；F-3 觸發升級時附上 6-b。
- **6-c**（medium，交 tech-architect）：**AC-12.5（已估值但未填產業的持股）仍讓 `notional_caps` 納入第 2 條**，與本 ADR 對 unknown 的處理（Decision 4：unknown > 0 時不納入）不一致。本 ADR **列出但不擴及**，是否擴及另案。

### 被此決策約束的事

- 本 ADR 與 F-1 不同版、不同 PR；排 F-1 之後最近一個 release；避開 `alerts/engine.py` 進行中變更。
- CEO 知悉清單 3(a)、3(b) 等本單落地才結案。

---

## 對實作的約束（K-1～K-10，qa 逐條核對）

來源為任務單「實作約束 1～10」，依序對應 K-1～K-10，風控 required：照錄，第 8 條（K-8）由 qa 逐條核對。

- **K-1**：重疊分類**只在 `book.py` 做一次**；`limits.py` 只讀新欄位，**不 import `app.portfolio`**。
- **K-2**：`_sector_rollup`／`sector_market_value_twd` 語意**不變**（`test_an_unvalued_holding_is_left_out_of_the_sector_total` 不改）。
- **K-3**：「第 2 條可否被試算採用」**單一判斷式**共用（grep `notional_caps` 無重複條件）。
- **K-4**：重疊皆 0（或 `book_fully_valued is True`）時，第 2 條 status／detail／observed **逐字不變**（既有 `test_advice_limits` 第 2 條測試**零修改**作證）。
- **K-5**：新欄位未設定的退路為「**產業未知**」（不猜同產業、不猜無重疊）。qa 以 `test_book_context_call_sites` 證明此退路在正式路徑走不到（風控 required）。
- **K-6**：not_evaluable 分支 `observed` 為 None，`threshold` 照舊。
- **K-7**：**不改 `alerts/engine.py`**。
- **K-8**：**不得複製或改寫已核可字面**；只能以風控逐字核可的新常數取代，並註明核可日期與審查檔。
- **K-9**：**前端不動**；新欄位比照 `sector_gap`，不同步 `types.ts`。
- **K-10**：**不得與 F-1 同 PR**（兩者都改 `build_book_context`；F-1 約束 7 禁後端繁中字串增加）；F-1 合併後 rebase。

---

## 驗收與既有測試影響（轉錄摘要）

驗收條件（任務單摘要；全文依 tech-architect 原稿）：

1. 帳本 2330（已估值，半導體）＋2303（半導體，未估值；live／cache_only）＋其他產業已估值，另「本標的自身批次未估值」變體；分低於／達到上限。低於 → 第 2 條 not_evaluable、observed None、detail W1、`notional_caps` 無 `sector_weight`、any 規則 `UNEVALUATED_LIMITS_NOTE` 名單含「單一產業佔比上限」；達到 → violated、detail 以 W2 結尾、action add→hold 並出現既有「加碼建議被第 2 條上限（單一產業佔比上限）擋下。」、fired 訊息含 W2；`context_notes` 依分支表 W4／W5。
2. 只有其他產業 → 第 2 條逐字不變、`notional_caps` 含 `sector_weight`；只有產業未知（三子類參數化）→ passed detail 以 W3 結尾、violated 不變、`notional_caps` 不含、加碼區間 basis 含既有 skipped 句並列「單一產業佔比上限」。
3. 多產業帳本（半導體 2330 已估值／2303 未估值、金融 2881 已估值、未估值 ETF 0050）`GET /api/portfolio/limits`：第 2 條彙總不以「半導體業 passed」呈現；2303 與 0050 排除句依 W6／`SECTOR_UNVALUED_EXCLUSION_SUFFIX` 適用條件分別呈現；`notes` 為 `/limits` 範圍版本；`test_advice_limits`、`test_advice_book`、`test_advice_book_limits`、`test_api_advice`、`test_api_portfolio_limits`、`test_alerts_engine`、`test_alerts_snapshot`、`test_book_context_call_sites` 全綠，既有斷言只允許改字面常數引用與 `test_the_sector_cap_discloses_that_an_exclusion_can_understate_it` 的「Route (a)」註解。

既有測試影響（tech-architect 所述）：`test_advice_limits.py` `_ctx` 預設 `book_fully_valued=True`，現有第 2 條測試（L178-376、L1330）預期不變；`test_advice_book.py` L130-153 引用字面常數需跟改、L581 不得改；`test_advice_book_limits.py` L422／L454 單一產業帳本 100% 走 violated 分支，L454「Route (a)」語意改寫。

QA／驗收補充：qa-e2e 抽驗決策卡第 2 條 not_evaluable 與 W3（375／1280）。

---

## 重審與失效條件

- S-B2 失效條件 1（quiet reason 進 UI／推播／feed 或被 F-4「查看略過原因」納入）觸發重審時，併審本 ADR 殘留（見 Consequences 4）。
- 任何讓 `notional_caps` 納入第 2 條的變更（含 6-c 擴及與否的決定），須回頭核對 Decision 4。
- 加強版（unknown 的 passed 也改 not_evaluable）：風控 2026-10-07 裁定不採用；任務單未載明日後改採的程序，待 tech-architect 補充。

## 交接

- W1～W6：creative-lead 起草 → risk-compliance-officer 逐字審；核可後本 ADR 才可改 accepted。
- 實作：dev-lead（F-1 合併後 rebase）→ qa-reviewer（K-1～K-10 逐條，K-8 重點）→ 風控單項核對。
- 6-a、6-b 另開單；6-c 交 tech-architect。
- CEO 知悉：3(a)、3(b) 等本單落地才結案。

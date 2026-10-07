# ADR-0022：stock-desk 單一產業佔比上限在同產業或產業未知持股無法估值時的判定

- 狀態：**proposed**。
  - 字面核可：W1～W7 已於 2026-10-07 經 risk-compliance-officer 逐字核可；W7（取代 `WORST_SECTOR_PREFIX`）納入核可範圍；核可字面以 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`（下稱「風控審查檔」）為準。本 ADR 不收錄 W1～W7 字面（唯一例外：「D-d1 更正註記」一節依 coordinator 指示收錄 D-d1 原字面與新字面作更正紀錄；兩處與審查檔不一致時以審查檔為準）。
  - 改 accepted 的前提（來源：風控審查檔「ADR-0022 改 accepted 前提」(a)～(c)，2026-10-07）：(a) 審查檔已轉錄——完成；(b) coordinator 確認 CEO 未推翻 2026-10-07 路線裁定——**待 CEO 表態**；(c) 本 ADR 註記 W7 納入核可範圍、核可字面以審查檔為準——已於本段完成。(a)(c) 已完成，**(b) 未完成前本 ADR 不得改為 accepted**。
  - 本次整理（2026-10-07）併入風控審查檔「D-d1 更正」節與 6-c／F-1b 裁定（見下「來源與版本」）；其中尚有待補項（`SECTOR_UNCLASSIFIED_NOTE` 中性句，見「交接」）。來源未載這些待補項是否列為 accepted 前提，待 coordinator 確認。
  - 補段落檔（2026-10-07，第二次）：`/limits` 彙總對 mixed 群組的規則（原待補項）已由 tech-architect 寫明、風控裁定，收於 Decision 1 補充段（M-1～M-5）。**W-6m**（M-4 新增字面）已於 2026-10-07 經風控逐字核可修正版（風控審查檔 `work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第三段，下稱「風控第三段」），並依 coordinator 指示收錄於 Decision 1 補充段的「W-6m 字面表」（W-6m 為本 ADR 不收錄字面原則的第二個例外；與風控審查檔不一致時以審查檔為準）。W-6m 的 PR 合併前提見 M-4。
  - 補段落檔（2026-10-07，第三次）：風控對 ADR-0022 PR 衝突 1 的裁定——`/limits` 方向子句優先序更正（Decision 5）、表二 g、M-4 第三點拆分與新字面 **W-6u**（Decision 1 補充）、失效條件 F-11／F-12、驗收摘要。來源：風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u（2026-10-07，風控對 ADR-0022 PR 衝突 1 的裁定，coordinator 轉錄）」段。**依風控裁定直接落檔，tech-architect 未另出補段**（coordinator 定案，CEO 可推翻；理由：裁定文本已逐條指明改法，且風控已讀碼確認「Y 有定義 ⇔ comparable 非空」）。W-6u 列入本 ADR 的 PR 合併前提（見 Decision 1 補充 M-4 與 W-6u 小節；字面核可狀態見下一行）。
  - **W-6u 已核可（2026-10-07）**：risk-compliance-officer 對 W-6u 逐字審，採替代案 W-6u-B（主案否決）；來源：風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「W-6u 逐字審（2026-10-07，risk-compliance-officer 唯讀裁定，coordinator 轉錄）」段。核可字面收錄於 Decision 1 補充「W-6u」小節（W-6u 為本 ADR 不收錄字面原則的第三個例外，沿用 W-6m 先例；與風控審查檔不一致時以審查檔為準）。合併前提改為 **RU-1～RU-8 落地且 qa-reviewer 無 BLOCKING_ISSUES**。本 ADR 狀態維持 proposed。
  - 2026-10-07 PR 實作完成待 commit；e2e 第二十五輪待排（**RM-5 為合併前提**，依風控審查檔第三段第五節；RU-9 的 W-6u 整句渲染為風控單項核對列的 qa-e2e 抽驗項，coordinator 先前誤稱合併前提，此處更正）。qa-reviewer 第一輪審查原文見 `work/reviews/2026-10-07-ADR-0022-PR-qa審查.md`。
- 日期：2026-10-07（tech-architect 評估與風控路線裁定日；本次整理與補段落檔同日）
- 決策者：tech-architect（路線 C′ 評估；6-c 評估）；risk-compliance-officer（路線裁定：APPROVE 附條件；W1～W7 逐字審；6-c 與 F-1b 裁定）；CEO 為最終負責人（若對裁定有異議）。
- 適用範圍：僅 product/stock-desk 產品線。
- 來源與版本（B 類轉錄）：
  - 主要來源：`work/dispatch/2026-10-07-任務單-產業上限對同產業未估值持股的判定與揭露.md` 中三段——「tech-architect 評估（2026-10-07，HEAD b92cbbd 唯讀；coordinator 轉錄）」、「風控路線裁定（2026-10-07，唯讀讀碼，coordinator 轉錄）」、「tech-architect 對 creative-lead 三問與 6-c 的評估」與「風控對 6-c 與 F-1b 的裁定」（兩段皆 2026-10-07，coordinator 轉錄）。
  - 字面與方向子句：風控審查檔（2026-10-07，HEAD d91fa8f 讀碼，coordinator 轉錄），含檔尾「D-d1 更正」節。
  - 附帶列管：`work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md`、`work/dispatch/2026-10-07-任務單-6-b-總曝險上限帳本不完整但已超標時不擋加碼.md`（各含 tech-architect 評估與風控裁定，2026-10-07）。
  - 補段來源（2026-10-07，第二次落檔）：
    - tech-architect 補段：`work/reviews/2026-10-07-tech-architect-D-a3資料流-M段最終版-ADR-0022-0023補段.md`（讀碼基準 `product/stock-desk` HEAD `f25c90d`；coordinator 原文轉錄）——第二段（unknown-only 不進 `notional_caps` 的確認，Decision 4 選填句）、第四段（Decision 1 補充段 M-1～M-5）。
    - 風控審查檔：`work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md`——第二段 B（M-1～M-4 裁定）、第三段（W-6m 修正版核可、排序鍵、RM-1～RM-5、F-8）。
    - tech-architect 補段第四段 M-4 的排序描述（`sorted()` 對字串排序）已被風控第三段 RM-2 取代，以風控第三段為準（補段檔頭「注意」亦明載）。
    - 本次快照：分支 `product/stock-desk`，HEAD `d66183e`（coordinator 任務單所述；tech-writer 未另行以 git 驗證）。
  - 本檔為 tech-writer 落檔與整理，**技術內容未增補、結論未改動**；Decision、K-n、required 編號（1-a～6-c 等）皆沿用來源。第二次落檔（2026-10-07）同樣只轉錄上列補段來源，M-1～M-5、RM-1～RM-5 等編號沿用來源。
  - 來源內所有 `檔案:行號`（`engine.py:354-363`、`limits.py:868-895`、`book_limits.py:105-120`、`book_limits.py:132`、`book.py:397` 等）、函式名、常數名、測試名與行號皆為 tech-architect／風控所述，tech-writer **未重新對 code 驗證**；行號會隨 commit 漂移，引用時以原文定位。
  - 快照：分支 `product/stock-desk`。初次落檔時 HEAD `8e8ccb59fe62e2ec4c66a2c28c86ce7c8ff5bded`；本次整理時 HEAD `331d42d73461c3584d62526fe248109500bfc714`（tech-writer 讀取 `.git/refs/heads/product/stock-desk`）。tech-architect 初評所用 HEAD 為 `b92cbbd`，風控審查檔為 `d91fa8f`，皆不同，此為快照。
  - 編號說明：落檔時 `docs/adr/` 最後一份為 0021；repo 內查無 ADR-0022 或 `0022-` 的引用，故使用 0022。ADR-0023 為本單衍生的通則（見「關聯」）。

---

## 關聯

- ADR-0005 決策五第 1 點（`docs/adr/0005-stock-desk-指數來源與美股額度管理.md` L214）：`app/advice/book.py` 維持純函式、不得 import 任何 adapter。任務單稱「ADR-0005 決策 1」，F-1 任務單稱「ADR-0005 決策 5」；tech-writer 讀 ADR-0005 後確認 book.py 純函式約束位於「決策五」第 1 點，本檔以此為準。
- F-1：`work/dispatch/2026-10-07-任務單-F-1-組合估值對不可用收盤價的防護.md`。本單不與 F-1 同版、不同 PR、不作 F-1 前置（見 K-10）。
- S-B2：`work/reviews/2026-10-07-S-B2-風險上限any規則-未評估揭露-字面-風控審查.md`（失效條件 1、4；列管 2）。
- **ADR-0023**（proposed）：`docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md`。收錄數學通則、非對稱規則與「可否用於試算」單一判斷式涵蓋第 1～5 條、6-a／6-b 適用；本 ADR 的欄位結構（Decision 1）被其引用並細化。
- 另開單（本 ADR 不處理其判定，見 ADR-0023）：6-a、6-b；6-c 已由風控裁定採 C-1，併本單處理（見 Decision 4）。
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

**分類以標的為單位**（見 Decision 1）。

- **same**：與卡片同一標的（含本標的自身未估值批次），或以標的為單位解析後屬 X 的其他標的之未估值持股。X 為 None 時 same 恆為 0，本標的批次不計入 same。
- **unknown**：以標的為單位解析後產業為 None 的未估值持股，**三子類分列計數**：台股未填產業（`tw_unfiled`）、ETF（`etf`）、非台股（`non_tw`）。三子類判定時皆併成 unknown。
- **other**：產業有值且 ≠ X。

| 未估值持股組成 | 算出值方向 | 結論 |
|---|---|---|
| 只有 other | 偏高 | 保守，「偏高」屬實 |
| 只有 same | 為下限 | passed 不可靠；violated 必成立 |
| same ＋ other／unknown | 方向不定 | passed 不可靠 |
| 只有 unknown | 方向不定 | passed 不可靠 |

（通則推導見 ADR-0023「數學通則」；來源：tech-architect 對 creative-lead 三問的評估，2026-10-07。）

---

## Options（選項比較）

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| A 原樣（比照第 3 條） | 有同產業未估值一律 not_evaluable | 與第 3 條一致 | 把**可證明的超標**轉成 not_evaluable；`engine.py:354-363` 只有 violated 擋加碼，會放行加碼 | 危險方向退步，**否決** |
| B | 已知同產業仍 passed，附揭露 | 改動小 | 已知同產業仍 passed；試算仍用偏低的產業市值；警示 quiet 路徑讀不到 detail | **否決** |
| **C′（採用）** | 已知同產業：≥ 上限維持 violated（附 W2），否則 not_evaluable（附 W1）；只有產業未知：passed 附 W3、violated 不變 | 永不以可能偏低比率回 passed；可證明超標照擋 | 與第 3 條不對稱；新增字面 ≥ 3 句 | 見 Consequences |
| 加強版（可選開關） | C′ 且 unknown 的 passed 也改 not_evaluable | 更保守 | 帳本任一 ETF／美股／未填產業未估值即整本降級 | 風控裁定**不採用**（見 Decision 與 Consequences） |

### 6-c 的方案（風控 2026-10-07 裁定採 C-1）

6-c：AC-12.5（已估值但未填產業的持股）仍讓 `notional_caps` 納入第 2 條。tech-architect 評估：`_unclassified_rollup` 只數已估值 sector None 部位（`book.py:402-418`），在分母內不在分子內 → 第 2 條算出值為**嚴格下限**；`notional_caps` 第 2 條（`limits.py:1223-1225`）仍以偏低比率試算、basis「仍為通過」（`:1390`）。

| 方案 | 內容 | 裁定 |
|---|---|---|
| **C-1（採用）** | 擴及：已估值未分類持股存在時，第 2 條不進 `notional_caps`；已估值 ETF／非台股算「可能屬於」 | 風控採；代價見 Consequences 8 |
| C-2 | 只擴及台股未填 | 與風控裁定 5（三子類皆算可能屬於）不一致，不採 |
| C-3 | 保留納入，basis 加尾句 | 需保留偏低額度與新字面，不採 |

---

## Decision（決策）

選 **路線 C′**（tech-architect 評估；風控 2026-10-07 裁定 APPROVE 附條件），並依風控 2026-10-07 對 6-c 的裁定採 **C-1**。

1. **分類以標的為單位、只做一次、放進 `PortfolioContext` 新欄位。**
   - **以標的為單位分類**（取代初稿「`u.sector == X`」逐筆比對；來源：tech-architect 三問評估第 1 點，風控審查檔「D-d1 更正」節確認）：先以 `_resolve_sector` 解析每個 (symbol, market) 群組的產業，再套到該群組每一筆。規則：
     - 群組內產業清單為 [X, None]（X 已填、另有 None 筆）→ 歸 **X**（避免把 None 筆算成 unknown 而回 passed＋W3）。
     - mixed 群組（產業清單有多個值）：**含 X 算 same，否則算 other**（tech-architect 原註「風控可改」；風控審查檔確認此規則）。
     - 只有 None → 算 **unknown**，依三子類計數。
   - **required（共用同一函式）**：未估值分類、`_sector_rollup`（6-c-1，見 K-2）、`_unclassified_rollup` 三者**共用同一個以標的為單位的解析函式**。已估值部位若為 mixed 且含 X，**整檔計入 X**（保守）。
   - `/limits` 彙總對 mixed 群組的同等規則（原「待補」，來源：風控審查檔「D-d1 更正」節）：**已由 tech-architect 寫明、風控 2026-10-07 裁定**，全文見下「Decision 1 補充：mixed 群組的歸類（M-1～M-5）」（置於 Decision 5 之後、「分支條件表」之前）。
   - `build_book_context` 一次分類，結果放入新欄位 `PortfolioContext.unvalued: UnvaluedComposition | None`（來源：tech-architect 三問評估第 1 點），結構如下，分類欄位皆為筆數：
     - `own_lots`：本標的自身未估值批次數（＝`_position_rollup` 的 `skipped`，`book.py:650`，tech-architect 所述）。
     - `same_sector_lots`：**其他標的**且屬 X 的未估值筆數；X 為 None 時恆為 0。
     - `unknown_sector_lots`：`{tw_unfiled, etf, non_tw}` 三子類（風控裁定 5，required 5-a：分列計數、判定時併成 unknown）。
     - `other_sector_lots`：產業有值且 ≠ X。
     - **不變式**：四類加總＝全書 `status != "ok"` 的筆數。
   - W1／W2 的 `{count}` ＝ `own_lots + same_sector_lots`（X 不為 None 時；兩者共用、**不拆版本**，因卡片已有 `SYMBOL_UNVALUED_NOTE`）。
   - D-d1／D-d2 **不需另加欄位**，以分割欄位為唯一來源：**d1 ⇔ `own_lots > 0` 且其餘三類皆 0**；d2 ⇔ `own_lots > 0` 且其餘三類有任一 > 0。qa 須以測試證明 d1 的分割欄位判定與「本標的批次數＝全書無法估值總筆數」等價（風控審查檔 D-d1 更正節）。
   - `book.py` 仍為純函式（ADR-0005 決策五第 1 點、F-1 約束）。
   - 此欄位結構於本 ADR 的 PR 一次建好，ADR-0023 的 6-a 只讀不改 `build_book_context`。
2. **新欄位退路（未設定時）：**`book_fully_valued is True` 視為無重疊；否則視為「**產業未知**」。**不猜「同產業」，也不猜「無重疊」**。（6-a 對第 1、4、5 條另有自己的退路，見 ADR-0023。）
   - **2026-10-07 落地補充**（來源：任務單檔尾「ADR-0022 PR 實作進度與兩個衝突」段 dev-lead 自決點，與「ADR-0022 PR 風控落地單項核對」段風控追認；qa-reviewer 亦建議補註於本 Decision；以下為轉錄，tech-writer 未對 code 驗證）：
     - `PortfolioContext.unvalued` 為 None 且 `book_fully_valued is not True` → 視為「產業未知」（fail-safe，即上述既有規定，無變更）。
     - **`PortfolioContext.valued_unclassified_lots` 為 None → 視為「沒有已估值的未分類持股」（非保守方向）。**
       - 理由：只有手刻 context 會為 None；若改採保守讀法，會改變既有 `test_advice_limits` 的 `notional_caps` 預期（任務單所述為該檔 L1386），違反 K-4「既有測試零修改」。正式路徑（決策卡、`/limits`、警示 snapshot）皆由 builder 設值，並以 spy 測試釘住（K-5；風控所述測試位置為 `tests/test_adr0022_sector_unvalued.py:881-942`）。
       - 決議紀錄：dev-lead 自決、coordinator 接受、**風控追認附條件**（條件為失效條件 F-13，見「重審與失效條件」）。此為非保守退路，與上述 `unvalued` 的保守退路方向相反，兩者不可混讀。
     - 未估值判準為 `valuation.status != "ok"`，與 notes 計數一致，四類加總不變式成立（Decision 1）。`_position_rollup` 另把「status 為 ok 但 `market_value_twd` 為 None」也算 skipped；兩者實務上相等但定義不同（qa low：summary 層應保證 status 為 ok 時 `market_value_twd` 不為 None；風控列為請 qa 以 diff 或實跑補驗項，所述位置為 `book.py:607-609` 與 `:678`，以原文定位）。
3. **`_check_sector_weight` 分支：**
   - **X 為 None（sector_gap）**：`NO_SECTOR_DETAILS[gap]` 分支**排在 C′ 之前**；本標的自身批次**不得計入 same**（否則 `own_lots > 0` 會讓 C′ 把 `NO_SECTOR_DETAILS` 蓋成 W1）。來源：tech-architect 三問評估第 3 點；風控審查檔 d0。
   - same（`own_lots + same_sector_lots`）> 0：算出值 ≥ 上限 → **violated**，detail 附 W2；否則 → **not_evaluable**，detail 附 W1，`observed` 為 None，`threshold` 照舊。
   - same = 0 且 unknown > 0：violated 不變；**passed 附 W3**。
   - 重疊皆 0（或 `book_fully_valued is True`）：status／detail／observed **逐字不變**。
4. **`notional_caps` 排除：**same 或 unknown > 0 時，第 2 條**不放進** `notional_caps`。此含 unknown-only 且第 2 條 passed（附 W3）的情形；判定上為 ADR-0023 非對稱通則的明列例外，試算上屬分子不完整（ADR-0023 KC-2）。（本句為 tech-architect 補段第二段 2026-10-07 之選填句，依 coordinator 指示加入。）「第 2 條可否被試算採用」為單一判斷式，與 `_check_sector_weight` 共用。
   - **C-1 擴及 AC-12.5（6-c，風控 2026-10-07 裁定）**：已估值但未填產業的持股（sector None）存在時，第 2 條同樣不放進 `notional_caps`。已估值 ETF／非台股算「可能屬於」（與裁定 5 一致）。**required**：已估值與未估值**共用同一子類分類函式與同一份子類清單**（tech-architect 架構約束：ETF 不能未估值算「可能屬於」、已估值算「不屬於」）。
   - 全 repo 的「上限可否用於試算」單一判斷式涵蓋第 1～5 條，見 ADR-0023。
5. **「比率會因此偏高」依分支條件表收窄**（W4／W5）；W1～W7 的字面由 creative-lead 起草、風控已逐字核可（見狀態欄；核可字面以風控審查檔為準）。
   - W1：第 2 條 not_evaluable（同產業有未估值）。
   - W2：附 violated 後（會進推播）。
   - W3：附 passed 後（產業未知）。
   - W4／W5：`UNVALUED_POSITIONS_NOTE` 的 live／cache_only 成因句。**組合方式為「{成因}；{方向子句}」成一則 note**；方向子句自成因句拆出，依下列優先序選用 D-a／D-P／D-d1／D-d2，決策卡與 `/limits` 兩範圍不同。**D-a 條件下，組合輸出須與 2026-09-18 兩則既有核可整句（live／cache_only）逐位元組相同**；cache_only 成因逐字保留。cache_only 固定句改為條件式一事，風控已於 2026-10-07 重新核可。
   - W6：`/limits` 中產業已知（Y）且**不在比較中**的未估值持股排除句。取代 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 的範圍只限「Y 有確定值且不在比較中」；Y 在比較中（C′ 下必為 violated）續用現行句；Y 的判定沿 `_resolve_sector`（批次產業不一致或 None 續用現行句）。（2026-10-07 補註：其中「批次產業不一致」即 mixed；mixed 且沒有任何產業在比較中者改用 W-6m，其餘仍續用現行句，見 Decision 1 補充 M-4。2026-10-07 風控 W-6u 段補註：Y 為 None 的 unknown 群組，compared 為空者改用 W-6u，compared 非空仍續用現行句。）
   - W7：`WORST_SECTOR_PREFIX` **無條件替換**（風控 2026-10-07 逐字核可，來源：風控審查檔核定字面總表 W7 列與「逐條」第 6 點）：不再以「帳本內 {count} 個產業不成立時才附」為條件；`{count}` ＝ `len(comparable)`。（任務單來源原述「不成立時附 W7」與審查檔核可範圍不同，以審查檔為準。）`WORST_SYMBOL_PREFIX` 對齊列 suggested 另案。
   - **方向子句優先序（風控 required，來源：風控審查檔「方向子句優先序」節；摘要，不含字面）**：
     - 決策卡：(1) 本標的有自身無法估值批次（`own_lots > 0`）→ d1 條件成立用 D-d1，否則 D-d2；**不受卡片產業 X 是否為 None 影響**（D-d1／D-d2 不被 X 為 None 覆蓋）。(2) X 為 None（且 `own_lots = 0`）→ D-a。(3) same 或 unknown > 0 → D-P。(4) 其餘 → D-a。
     - `/limits`（**2026-10-07 風控更正，取代風控審查檔原「方向子句優先序」節的 `/limits` 列**；來源：風控審查檔檔尾「`/limits` 方向子句優先序更正與 W-6u」段，風控對 ADR-0022 PR 衝突 1 的裁定；第一個符合的就用）：
       1. Y 未定義，即第 2 條 comparable 為空、`reported_sector is None` → D-a。6-b 落地後，第 3 條 violated 用 D-a3，否則用 D-a。
       2. 帳本有任何 unknown，或 Y 有 same（依 M-3／M-5，mixed 群組的 categories 含 Y 也算）→ D-P，target 為「已納入比較的產業」。
       3. 其餘 → D-a。6-b 後同第 1 點，可替換為 D-a3。
       - **更正註記（2026-10-07，風控）**：原優先序為「帳本有任何 unknown 或 Y 有 same → D-P；Y 未定義 → D-a；其餘 → D-a」。原第 (2) 點（Y 未定義 → D-a）置於 D-P 之後為**筆誤（死條款）**（風控所述：排在「有 unknown → D-P」後面，落到原第 (3) 條一樣是 D-a，證明原意是讓它先於 D-P）；風控定性為「更正本席優先序的筆誤」，不算新增例外。風控審查檔「落地 required」第 2 點原文即為無條件的「`/limits` Y 未定義用 D-a」。
       - 理由（風控所述）：comparable 為空時，同一則回應第 2 條的 detail 是 `NO_CANDIDATE_DETAIL`，D-P 的 `/limits` 版卻說有「已納入比較的產業」且其佔比偏低，兩句互相矛盾，並對一個沒印出的佔比做存在宣稱；風控 VETO「有 unknown 一律 D-P」（選項 (a)）。D-a 在此情境為真（第 1、4、5 條 comparable 候選者依規則 3 無自身未估值批次）；第 2 條沒印比率，與 a0 語意相同。
       - D-P 的 `/limits` 版仍會被選到的情況：Y 有定義（⇔ comparable 非空），且「unknown > 0」或「`unvalued_lots_in_sector(Y)` > 0」，此時 target 至少有 Y 可指。
       - 「Y 有定義 ⇔ comparable 非空」：風控讀碼確認，依據 `limits.py:1058`（sector 為 None 一律 not_evaluable，進不了 comparable）、`book_limits.py:548-567`（comparable 為空時不設 `reported_sector`）、`book_limits.py:592`（comparable 非空時 `reported_sector` ＝ worst.sector，必不為 None）；以上行號為風控所述，tech-writer 未重新對 code 驗證，以原文定位。
       - 決策卡經風控核對沒有同型問題（風控所述：`book.py:877-891` 順序為 own>0 → X 為 None → same／unknown → 其餘，與本 ADR 決策卡列一致）。
       - required（風控 R-1）：`book.py` `_book_direction` 先判斷 `reported is None` 成立就回 D-a 常數，再判斷 D-P；只讀 `SectorComparison.reported_sector`，不得在 `book.py` 另算 comparable（單一來源）；docstring 的優先序同步改寫。
   - 字面範圍與限制（轉錄自風控補充；W1～W3 之字面範圍為起草約束，核可字面以審查檔為準）：
     - W1 句構三處通用；要講成因（同產業或本標的 N 筆無法估值、分子不完整只會偏低故不計算），不印比率。
     - W2 誠實度（required 2-b）：只有「全部 same」時才是下限；否則方向不定、violated 為保守處理。不得宣稱下限或「實際只會更高」（除專屬變體）；要說明比率只用已估值部分、有同產業持股無法估值、本條以已達上限處理；進推播不得有賣出指示或催促。
     - W3（required 5-b）：主詞、三子類、不帶筆數；**不得說「屬於」，只能說無法判斷**；對 ETF／非台股不得出現「請填產業」類指引（D6 先例）；接 `WORST_SECTOR_PREFIX`。W3 與 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 同義但**不可直接沿用**（「此標的」會指成卡片標的、「本條上限的比較未納入此標的」在決策卡不成立）。
     - W4／W5：cache_only 成因逐字保留；本標的自身未估值批次須明示——**d1：第 1、4、5 條偏低；d2：三條（第 1、4、5 條）方向不定**（過渡期 required，見 6-a；風控審查檔 D-d1 更正節取代原「第 1、5 條偏低、第 4 條方向不定」）。
     - W6 只用於 Y 不在比較中。
     - 名稱：D-d1／D-d2 的上限名稱一律以 `LIMIT_NAMES` 組字串，不得手打（風控 required）。
     - 通則：無保證字眼、不寫「安全」「暫無問題」、推播不含操作指示。

### Decision 1 補充：mixed 群組的歸類（M-1～M-5）

（tech-architect 2026-10-07 擬，HEAD f25c90d 對照；風控 2026-10-07 裁定，見 `work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第二段 B。本段取代 Decision 1「待補：`/limits` 彙總對 mixed 的同等規則」那一條。M-4 的排序規則與 W-6m 字面依風控第三段（2026-10-07）修訂：tech-architect 補段原文的「`sorted()` 對產業名稱字串排序」已被 RM-2 取代，W-6m 字面為風控修正版。）

**定義**
- 群組 G＝同一 (symbol, market) 的全部批次，不論是否已估值。categories(G)＝G 中所有非 None 產業的集合。
- sector(G)＝`_resolve_sector`（`book.py:351`）的解析結果：categories(G)＝{X} → X（含 [X, None]）；|categories(G)| ≥ 2 → mixed（sector None、`sector_gap="mixed"`）；空集合 → gap 子類（`tw_unfiled`／`etf`／`non_tw`）。

**事實（讀碼）**
- `/limits` 每個候選者都經 `build_book_context`（`book_limits.py:406`），分子與同產業分類自動繼承。
- mixed 候選者的 sector 為 None → 第 2 條 not_evaluable，附 `SECTOR_MIXED_DETAIL`，在 `book_limits.py:445-452` 列入排除，到不了 `_one_per_sector`。
- 未估值群組的排除句目前在 comparable 決定之前就組好（`book_limits.py:438-443`）。M-4 需要改成先算出 comparable（含 `_one_per_sector` 之後）再組排除句，由 dev-lead 調整順序。

**M-1 分子**（修訂 K-2；風控確認不需新揭露）
- 產業 X 的分子＝所有 X ∈ categories(G) 的群組中，全部已估值批次的市值合計。
  - [X, None] 的 None 批次計入 X（6-c-1）。
  - 已估值的 mixed [X, Y] 整檔同時計入 X 與 Y（保守）。
  - 未估值批次仍不進任何產業分子（K-2 前半維持；`test_an_unvalued_holding_is_left_out_of_the_sector_total` 不改）。
  - `_unclassified_rollup` 只計 categories(G) 為空的群組。
- **印出的產業佔比可能因 mixed 整檔計入而高估**：誤差只往高估方向，各產業分子加總可能大於總資產。風控裁定不需新揭露，理由是 mixed 由使用者資料造成、可以修正，且已附 `SECTOR_MIXED_DETAIL` 與指引。CEO 知悉 (vii)：違規推播可能建立在高估的比率上。
- **required**：產品任何地方都不得加總或平均各產業的比率或分子，範圍含後端 API 欄位、前端畫面、推播、匯出。qa 以 grep 加測試釘住；測試用「mixed 全已估值、各產業分子加總大於總資產」的帳本，斷言 `/limits` 與決策卡回應不含任何跨產業的合計或平均值。

**M-2a mixed 候選者**（採用；否決 M-2b）
- mixed 候選者不代表任何產業：只以 `SECTOR_MIXED_DETAIL` 原文列入排除，不計入 W7 的 `{count}`（＝`len(comparable)`）。`/limits` 不得另行合成各產業的判定。
- M-2b 否決：它會形成第二條判定路徑，違反 book_limits 規則 1、2。
- 殘留（風控接受，列管 low）：只透過 mixed 標的持有的產業不會被比較，只由 `SECTOR_MIXED_DETAIL` 揭露。日後補「不計算不代表沒有產業集中風險」這類句子（比照 D8）另案送審，本 PR 不要求新字面。

**M-3 未估值分類**（對決策卡產業 X）
- 本標的自身批次 → own。X 為 None 時亦同，且不計入 same。
- 其他群組中 X ∈ categories(G) → same。
- categories(G) 為空 → unknown（三子類）。
- 其餘 → other。
- mixed 群組永遠不是 unknown，且對它的每一個產業都算 same。四類加總仍等於全書未估值筆數。

**`_one_per_sector` 不變式**：解析產業同為 X 的所有候選者，第 2 條的 status／detail／observed 完全相同（以測試釘住，函式不改）。

**M-4 `/limits` 未估值群組的排除句**（「比較中產業」＝最終 comparable 的 sector 集合）
- sector(G)＝Y 且 Y 不在比較中 → `SYMBOL_UNVALUED_NOTE`＋W6。
- Y 在比較中（C′ 下必為 violated）→ 續用 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`。
- categories(G) 為空（unknown），依 compared 是否為空拆為兩支（2026-10-07 風控裁定，來源：風控審查檔檔尾「`/limits` 方向子句優先序更正與 W-6u」段 R-5；原寫法「categories(G) 為空 → 續用」已被取代）：
  - **compared 非空** → 續用 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`（那時該句為真）。
  - **compared 為空（W-6u）→ `SYMBOL_UNVALUED_NOTE` ＋ W-6u 核可字面**（風控 2026-10-07 逐字核可，核可日 2026-10-07；採替代案 W-6u-B，主案否決——主案的部分否定「不代表所有產業都未超過上限」易讀成「有產業超過上限」，對 not_evaluable 的判定給了方向暗示）。逐字，不改任何字、只能整句照抄，57 字，無變數：
    > 本條上限的比較未納入此標的；此標的沒有產業別資料，本次沒有任何產業納入比較，因此無法確認各產業的佔比是否超過上限。

    詳見「W-6u」小節。原因：此情境下現行句「此標的可能屬於已納入比較的產業，使該產業的佔比被低估」無所指，且與同一則回應第 2 條 detail（`NO_CANDIDATE_DETAIL`）互相矛盾（風控所述；F-1 測試的帳本即會產生這句，該測試只斷言 `startswith(SYMBOL_UNVALUED_NOTE)` 故未抓到）。
  - 「compared」沿用風控用語，對應本節開頭「比較中產業」＝最終 comparable 的 sector 集合。
- mixed 且至少一個產業在比較中 → 續用 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`（逐字不變）。
- **mixed 且沒有任何產業在比較中（含 comparable 為空）→ W-6m 新字面，與 C′、W6 同一 PR**（風控裁定採 (i)，不准續用現行句：現行句「可能屬於已納入比較的產業」在此情境為假，comparable 為空時更無所指）。組法：`SYMBOL_UNVALUED_NOTE` 接 W-6m。
- W-6m 字面約束（風控第二段 B(3)；排序規則依風控第三段 RM-2 修訂）：
  - 比照 W6 句構。
  - 列出該群組 categories(G) 的全部產業，不用「等」、不截斷。
  - **排序規則（RM-2；風控第三段指定由 tech-architect 寫入本 ADR）**：先對 categories(G) 去重；排序鍵為 `TWSE_SECTORS` 索引；不在 `TWSE_SECTORS` 的舊資料值排最後，再依字碼排序；排序鍵必須全序、不得拋例外；以「、」連接，不加「等」、不截斷；排序寫成**獨立單一函式**，不得借用 `_resolve_sector`（`book.py:363`）內部的 `sorted()`。測試釘住。
  - 排序鍵的理由（風控第三段二.3）：`TWSE_SECTORS`（`app/positions/sectors.py:38-80`）即 TWSE 分類順序，為封閉列舉、亦是 `GET /api/positions/sectors` 下拉來源，使用者看到的順序就是這個；中文字碼序對讀者無意義；結果決定性、與平台編碼無關。不用字典序。
  - 寫明這些產業本次沒有任何持倉納入比較。
  - 必須包含「未納入比較不代表這些產業未超過上限」。
  - 不寫「屬於」單一產業，不帶任何指引。
- 流程：creative-lead 起草 → risk-compliance-officer 逐字審。**W-6m 已於 2026-10-07 核可（修正版，風控第三段）**；原「W-6m 字面未經風控逐字核可前，本 ADR 的 PR 不得合併」之條件已滿足，**合併前提改為：RM-1～RM-5 落地、排序鍵已寫入本 ADR（本段）、B(1) required 完成（本段 M-1 required：寫明高估方向，grep＋測試釘住「不得加總或平均各產業比率」）、qa-reviewer 無 BLOCKING_ISSUES（含 Codex 第二意見；環境不可用須註明）、CI 綠燈**（風控第三段五）。
- **合併前提增補（2026-10-07，風控 W-6u 段 R-5 與「交接與 CEO 異議」；coordinator 定案；2026-10-07 依「W-6u 逐字審」段更新）**：W-6u 字面已核可；**ADR-0022 PR 要等 RU-1～RU-8 都落地，且 qa-reviewer 審查通過（沒有 BLOCKING_ISSUES）之後，才可以合併**（風控「W-6u 逐字審」段「合併前提沿用 R-5」）。此條與上列 W-6m 的合併前提並列、同時成立。

**W-6u（2026-10-07 風控裁定新增；2026-10-07 已逐字核可，採替代案 W-6u-B）**

來源：風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u」段（逐條意見 R-5，required，與本 PR 同時落地）與其後「W-6u 逐字審」段（核可字面、RU-1～RU-9、失效條件增補；2026-10-07，coordinator 轉錄）。

**W-6u 字面表**（收錄原因：沿用 W-6m 先例，coordinator 指示寫入核可字面；為「不收錄字面」原則的第三個例外；W1～W7 字面仍不收；與風控審查檔不一致時以審查檔為準）

| 代號 | 逐字核可字面 | 變數 | 顯示條件 | 字數 |
|---|---|---|---|---|
| **W-6u**（替代案 W-6u-B，無修正） | 本條上限的比較未納入此標的；此標的沒有產業別資料，本次沒有任何產業納入比較，因此無法確認各產業的佔比是否超過上限。 | 無 | `/limits` excluded reason。categories(G) 為空，**且** compared 為空（compared 須為驅動第 2 條 detail 的同一集合，單一來源，不得另算）。組法 `SYMBOL_UNVALUED_NOTE` ＋ W-6u。 | 57（含全形標點，14＋11＋13＋19） |

- **核可日**：2026-10-07。核可不帶修正，字面就是 creative-lead 送來的替代案原句，只能整句照抄。
- **主案否決**：主案含「未納入比較不代表所有產業都未超過上限」。風控認為它是部分否定，一般讀法易讀成「有產業超過上限」，而第 2 條在此情境為 not_evaluable、根本沒有計算，等於給了偏向「超過」的方向暗示，屬誘導性表述（與隱藏不確定性同樣違反誠實原則，方向相反）；「所有產業」的範圍也不清楚。主案字面不收錄於本 ADR。
- **採替代案的理由（風控所述）**：直接講出不確定性「無法確認…是否超過上限」，不往超過或未超過偏，對應 not_evaluable；「無法確認」W2 已核可過；擋住「沒被列出 → 已通過」的推論，與 R-5 要求的「同義」成立。
- **共用語**：「此標的沒有產業別資料」對 tw_unfiled／etf／non_tw 三子類皆為真（風控所述：`sector_categories` 回傳 `frozenset(position.sector for … if position.sector)`，categories(G) 為空即每一筆持倉都沒有產業別值）；只講資料狀態，不暗示使用者漏填，不帶「請填」。不採 W3 的「無法判斷其所屬產業」。
- **與 `NO_CANDIDATE_DETAIL` 並列**：風控讀碼確認一致（第 2 條 `compared_sectors` 取自 `_one_per_sector` 之後的 comparable，會丟掉 sector 為 None 的候選，故 compared 為空等於 comparable 為空；此時 detail 一定是 `NO_CANDIDATE_DETAILS["sector_weight"]`，不會是 `EMPTY_BOOK_DETAIL`）。與同回應的 D-a「比率會因此偏高。」不衝突（D-a 講有印出的比率，第 2 條沒印；與 a0 語意相同）。以上函式、變數與行號為風控所述，tech-writer 未重新對 code 驗證。
- **禁詞複核（風控人工逐字比對，仍須依 RU-6 實跑）**：`shared/forbidden-terms.json`、`FRONTEND_FORBIDDEN_TERMS`、`loader.BANNED_PHRASES`、裸「即時」類、R-5 指定詞（「屬於」「可能屬於已納入比較的產業」「被低估」）及「所屬」「等」「涉及」「請」「仍」「通過」「安全」等延伸詞皆 0 命中。

**W-6u 範圍與顯示條件**（風控裁定 5；四個分支涵蓋所有情況）
- categories(G) 為空且 compared 為空 → W-6u。
- unknown 且 compared 非空 → 續用 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`。
- 單一產業 Y 不在比較中 → W6。
- mixed 且沒有交集 → W-6m。
- 第 1、4、5 條不受影響，仍用 `UNVALUED_EXCLUSION_SUFFIX`；已估值但無產業的標的走 `candidate_exclusions`，reason 是 `check.detail`，不會接到 W-6u（風控所述）。

- **處理範圍**：`book_limits.py:596-615` `_sector_unvalued_suffix` 的最後一個分支（行號為風控所述，未重新對 code 驗證）。
- **顯示條件**：categories(G) 為空（unknown），**且** compared 為空。compared 非空時，unknown 續用現行 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`。
- **為何本 PR 一併處理**（風控所述）：C′ 會讓此情境變多。例：2330（半導體，已估值，未達上限）＋2303（半導體，未估值）＋0050（ETF，未估值）——2330 因 W1 被排除後 comparable 為空，0050 就會拿到無所指的現行句。理由與 required 1-a（W6 與 C′ 同 PR）、W-6m（不准續用現行句）同型，依先例須同 PR。
- **流程**：creative-lead 起草 → risk-compliance-officer 逐字審——**已完成，核可替代案 W-6u-B（2026-10-07）**。
- **起草約束（R-5，逐字轉錄；已由核可字面滿足，保留作紀錄與日後重審依據）**：
  - 開頭比照 W6／W-6m「本條上限的比較未納入此標的；」。
  - 寫明本次沒有任何產業納入比較（與 `NO_CANDIDATE_DETAIL` 一致）。
  - 不得出現「屬於」「可能屬於已納入比較的產業」「被低估」。
  - 三子類共用一句，不帶筆數（`SYMBOL_UNVALUED_NOTE` 已經帶了）。
  - 不帶「請填產業」類指引（W3／D6 先例）。
  - 必含與「未納入比較不代表…未超過上限」同義的不確定性表述。
  - 禁詞零命中。
- **落地 required（R-5）**：常數註解附核可日期與審查檔路徑；測試覆蓋三子類（tw_unfiled／etf／non_tw）；加不變式測試「`SECTOR_UNVALUED_EXCLUSION_SUFFIX` 只在 compared 非空時出現」；新句納入既有三份禁詞掃描。具體化為下列 RU-1～RU-9。
- **RU-1～RU-9（風控「W-6u 逐字審」段「落地 required」，2026-10-07，摘要；qa 逐條）**：
  - **RU-1**（常數，required）：`SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX` 型別改 `str`、值為核可字面且逐位元組相同；註解拿掉「PENDING／has not been approved」，換成 `風控核可文案,修改須重新送審(2026-10-07)` 加風控審查檔路徑（W-6u）；比照 W6、W-6m 以英文簡述寫法（no category, nothing compared, states the cap could not be confirmed either way）。
  - **RU-2**（`_sector_unvalued_suffix`，required）：`not categories and not compared` 分支無條件回傳 W-6u；刪掉 `is not None` 判斷、退回 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 的路徑與 TODO；docstring 第三點改成已落地敘述。風控讀碼發現：dev-lead 工作樹目前該常數為 `None` 時退回舊句，只可當未合併分支的暫時狀態，**不得帶進合併**。
  - **RU-3**（三子類測試，required）：tw_unfiled／etf／non_tw 各配 live、cache_only；斷言第 2 條該標的 excluded reason 等於 `SYMBOL_UNVALUED_NOTE.format(count=n) + W-6u`；至少涵蓋 F-1 帳本與 C′ 帳本（2330 半導體已估值未達上限、2303 半導體未估值、0050 ETF 未估值，斷言 0050 拿到 W-6u）；拿掉這些測試的 `xfail(strict=True)`。
  - **RU-4**（不變式測試，required）：第 2 條任何 excluded reason 含 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`（或子字串「可能屬於已納入比較的產業」）⇒ `evaluated_count > 0`；含 W-6u ⇒ `evaluated_count == 0` 且 detail 等於 `NO_CANDIDATE_DETAILS["sector_weight"]`；單元測試 `_sector_unvalued_suffix(frozenset(), frozenset())` 等於 W-6u、`_sector_unvalued_suffix(frozenset(), frozenset({SEMI}))` 等於舊句。
  - **RU-5**（負向測試，required）：第 1、4、5 條 excluded reason 不得含 W-6u；unknown 且 compared 非空時不得出現 W-6u；已估值無產業的標的（`candidate_exclusions`）不得出現 W-6u。
  - **RU-6**（禁詞掃描，required）：W-6u 本身與 `SYMBOL_UNVALUED_NOTE.format(count=2) + W-6u` 整句加進 `test_adr0022_sector_unvalued.py` 的 `_rendered_new_sentences()`，跑過三份禁詞表與 `find_bare_realtime_claims`；另斷言「屬於」「所屬」「被低估」「等」「涉及」不在句中。
  - **RU-7**（既有測試，required）：`test_advice_book_limits.py:447`、`test_adr0022_sector_unvalued.py:610/618/651` 與 F-1 測試皆不改；風控為讀碼推論，dev-lead 實作後以實跑結果確認並回報。
  - **RU-8**（ADR，required）：tech-writer 於本節 M-4 第三點寫入核可字面、日期與主案否決，並將 F-12 增補併入失效條件 10——**本次已完成**。
  - **RU-9**（suggested）：`book_limits.py` 模組 docstring 列出 W-6u 常數；qa-e2e 於 375／1280 抽驗 `/limits` 在 0050 情境下 excluded reason 整句渲染，不得截斷或折疊。
  - 以上 RU 內的檔名、行號與函式名皆為風控所述，tech-writer 未重新對 code 驗證。
- **若 CEO 決定讓 W-6u 延到下一個 PR**：風控保留書面否決紀錄，理由是 C′ 讓無所指句子的出現頻率增加，與 required 1-a、W-6m 的先例不一致；最終責任由 CEO 承擔，並列入 CEO 知悉清單（風控審查檔同段「交接與 CEO 異議」）。

**W-6m 字面表**（風控第三段一，2026-10-07 逐字核可修正版；`{sectors}` 算 1 字。W1～W7 字面不收於本 ADR，見風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`。**收錄原因（coordinator 2026-10-07 確認為「不收錄字面」原則的第二個例外）：風控要求排序鍵與 W-6m 字面進 ADR**，見風控第三段 RM-2 與五）

| 代號 | 逐字核可字面 | 變數 | 顯示條件 | 字數 |
|---|---|---|---|---|
| **W-6m**（修正版） | 本條上限的比較未納入此標的；此標的的持倉所填產業別為 {sectors}，這些產業本次沒有任何持倉納入比較，未納入比較不代表這些產業未超過上限。 | `{sectors}`＝mixed 群組 `categories(G)` 全部產業（規則見 M-4 排序規則 RM-2）；前留一個半形空白、後不留 | `/limits` excluded reason。該標的屬 mixed 未估值群組（`categories(G)` ≥2 產業）且每一產業都不在 comparable 產業集合。組法 `SYMBOL_UNVALUED_NOTE` 接 W-6m。至少一產業在比較中 → 續用現行 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 逐字不變。 | 64（兩產業 73、三產業 80） |

- 修正內容（風控第三段二.2）：「涉及 {sectors} 產業」→「所填產業別為 {sectors}」。理由：「涉及」可能被讀成系統判斷該公司業務橫跨多產業，而 mixed 的事實是同一標的批次被填了不同產業別（資料狀態）；「所填產業別為」與已核可 `SECTOR_MIXED_NOTE`「填了不只一種產業別」（`limits.py:300`）一致；句尾「產業」一併拿掉，避免名單中有不以「業」結尾者（紡織纖維、電機機械、存託憑證）時範圍不清。W-6m-B 風控不採。
- 展開例（TWSE 順序，風控第三段）：
  - 兩產業：「本條上限的比較未納入此標的；此標的的持倉所填產業別為 金融保險業、半導體業，這些產業本次沒有任何持倉納入比較，未納入比較不代表這些產業未超過上限。」
  - 三產業名單：「金融保險業、半導體業、電子零組件業」。
- 禁詞複核（風控第三段二.4）：W-6m 修正版與 `TWSE_SECTORS` 全部 37 個產業名對 `loader.BANNED_PHRASES` 等禁詞表 0 命中（風控所述，tech-writer 未重驗）。

**W-6m 落地 required（風控第三段三，qa 逐條核對）**
- **RM-1**：常數註解「風控核可文案,修改須重新送審(2026-10-07)」＋風控審查檔路徑（`work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md`）。
- **RM-2**：`{sectors}` 組字規則，見上「排序規則」。
- **RM-3**：顯示條件依 M-4，先算 comparable 再組排除句（dev-lead 調整順序）。
- **RM-4**：測試——渲染結果引用常數；兩產業、三產業各一例並斷言排序；斷言不含「屬於」「等」「涉及」；用 `TWSE_SECTORS` 全部名稱渲染一次跑三份禁詞掃描；mixed 且至少一產業在比較中 → 現行句逐位元組不變；mixed 已估值 → 維持 `SECTOR_MIXED_DETAIL` 不受影響。
- **RM-5**：qa-e2e 於 375 與 1280 抽驗三產業 excluded reason，不得截斷或省略（只能折行）。

**M-5**：`/limits` 方向子句中的「回報產業 Y 有 same」依 M-3 判定，未估值 mixed 群組的 categories 含 Y 就算（→ D-P；2026-10-07 風控更正：須先排除「Y 未定義 → D-a」，見 Decision 5 `/limits` 優先序）。D-a 位置的 D-a3 替換見 ADR-0023 Decision 8-1。

**一致性**
- M-1、M-3 只在 `build_book_context` 做一次，與 `_sector_rollup`、`_unclassified_rollup`、未估值分類共用同一個以標的為單位的解析函式（K-1）。`/limits` 經 `_symbol_context` 繼承。
- `/limits` 專屬的規則只有 M-2a、M-4。

**與失效條件 4 的關係**
- 6-c-1 加 M-1 在形式上改變了 `_sector_rollup` 語意。風控裁定「**已涵蓋，不需重審**」，理由如下：
  - W1／W2 的 `{count}` 依 M-3 的保守歸屬仍然成立。
  - W3：mixed 永遠不是 unknown。
  - W6 只用於 Y 有確定值的情形。
  - W7 的 `{count}` 不含 mixed。
  - D-P／D-a 的「可能」「因此偏高」不會因 M-1 的額外高估而變假。
- 失效條件 4 對 M-1／M-3 以外的再變更仍然有效（ADR-0023 F-7，即風控審查檔第一段「四、失效條件增補」之 F-7：M-1 整檔計入或 M-3 分類改變 → 重審 B(1)／B(4)；全文見 ADR-0023「重審與失效條件」）。

**測試**
- T-1：mixed 全已估值時，分子含整檔，且同時計入其每一個產業。
- T-2：只透過 mixed 標的持有的產業不被比較。
- T-3：[半導體, None] 兩筆皆已估值時兩筆都計入。
- T-4：未估值 mixed 的各排除句情境，含 W-6m 與 comparable 為空。
- T-5：同產業兩個候選者的 check 完全相同。
- T-6：不加總、不平均（見 M-1 required）。
- 既有 `test_advice_book_limits`（L155／174／190／201／214／422／454）與 `test_advice_book`（L535／548／581／590）的斷言零修改，L454 只改註解。

### 分支條件表（轉錄，不含字面）

**表一：決策卡（標的 X）**

| # | 未估值持股組成 | 第 1 條 | 第 2 條 | 第 4 條 | 第 5 條 | 「偏高」全部成立？ |
|---|---|---|---|---|---|---|
| a0 | X 為 None、本標的無自身批次（`own_lots = 0`）；採 D-a | 偏高 | 走 `NO_SECTOR_DETAILS`，無比率 | 偏高 | 偏高 | 成立 |
| a | 全是其他標的的 other | 偏高 | 偏高，判定照舊 | 偏高 | 偏高 | 成立 |
| b | 含其他標的的 same，無本標的批次 | 偏高 | 未達上限 not_evaluable（W1）；已達 violated（W2），比率只在「全部 same」時為下限，否則方向不定 | 偏高 | 偏高 | 第 1／4／5 成立；第 2 不適用或不成立 |
| c | 含 unknown，不含 same | 偏高 | 方向不定；passed 接 W3；violated 照舊 | 偏高 | 偏高 | 第 1／4／5 成立；第 2 方向不定 |
| d0 | X 為 None、本標的有自身批次（`own_lots > 0`）；依 d1／d2 | 依 d1／d2 | 維持 `NO_SECTOR_DETAILS[gap]`；本標的批次不計入 same；sector_gap 分支先於 C′ | 依 d1／d2 | 依 d1／d2 | 不成立 |
| d1 | `own_lots > 0` 且其餘三類皆 0（另有 `SYMBOL_UNVALUED_NOTE`；第 2 條依 b） | 偏低 | 同 b | 偏低 | 偏低 | 不成立 |
| d2 | `own_lots > 0` 且其餘三類有任一 > 0（另有 `SYMBOL_UNVALUED_NOTE`；第 2 條依 b） | 方向不定 | 同 b | 方向不定 | 方向不定 | 不成立 |

d1 的第 1、4、5 條偏低是**確定**的下限（風控審查檔 D-d1 更正節；理由見該節）。

**表二：`/limits` notes**：e 一律第 1／4／5 偏高成立；f 被回報產業 Y 無 same 且帳本無 unknown → 第 2 偏高成立；g 帳本有任何 unknown **且 Y 有定義（comparable 非空）** → 第 2 方向不定（排除清單已有 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`）（2026-10-07 風控更正：Y 未定義時先走 Decision 5 `/limits` 第 1 點 → D-a，不屬 g；Y 未定義且有 unknown 時，排除理由見 M-4 的 W-6u）；h Y 有 same → 候選者轉 excluded 或以 violated 留下。

**表三：`SECTOR_UNVALUED_EXCLUSION_SUFFIX`（W6，現行既存失準）**：h 的 sector None → 續用（2026-10-07 補註：unknown 且 compared 為空者改用 W-6u，見 M-4）；sector 已知 Y 且 Y 在比較中 → 成立但偏弱；sector 已知 Y 且 Y 不在比較中（**現在就已發生**）→ 字面不成立，需另句。

---

## D-d1 更正註記

來源：風控審查檔檔尾「D-d1 更正」節（2026-10-07，風控自行更正，coordinator 轉錄；審查檔原表格保留不刪）。此為更正紀錄，字面以審查檔為準。

- **日期**：2026-10-07。
- **原字面**（已被取代）：因本標的自身的持倉無法估值，第 1、5 條上限（單一標的佔比上限、分數 Kelly 部位上限）的比率會偏低，其低於上限的結果也可能建立在偏低的比率上；第 4 條上限（單筆最大可承受虧損）的比率方向不定。
- **新字面**（逐字核可，取代審查檔表內 D-d1 列）：因本標的自身的持倉無法估值，第 1、4、5 條上限（單一標的佔比上限、單筆最大可承受虧損、分數 Kelly 部位上限）的比率會偏低，其低於上限的結果也可能建立在偏低的比率上。
- **理由**（tech-architect 數學更正，風控採認）：`_position_rollup` 只把 ok 批次加進 `quantity`（`book.py:341`），第 4 條 `held_shares` 只算已估值股數，停損距離與估值無關，(q_v+q_u)/(E+q_u·p) ≥ q_v/E ⇔ E ≥ A，市值非負時必然成立 → 第 4 條亦為確定下限；原字面「方向不定」把確定偏低講輕（隱藏不確定性）。**尚未實作，對使用者無影響。**
- **連帶修訂**：本 ADR 原三處「第 1、5 條偏低、第 4 條方向不定」改為「d1：第 1、4、5 條偏低；d2：三條方向不定」，表一 d 拆為 d1／d2（已於本次整理完成）。D-d2 字面不改。
- **required**：名稱一律由 `LIMIT_NAMES` 組字串；qa 以測試確認「本標的跨市場或幣別混雜時第 4 條為 not_evaluable」——這是 tech-architect 的前提，**不成立則 D-d1 不得把第 4 條寫成偏低**。
- **6-a 連動（required，6-a 同一包）**：6-a 落地後 own>0 時第 1、4、5 條不再有 passed，D-d1／D-d2「低於上限的結果…」失去所指；creative-lead 須在 6-a 一併提出 own>0 時方向子句處置（刪除或改寫）送風控逐字審。見 ADR-0023。

---

## 與第 3 條（總曝險）的非對稱

風控裁定 2（同意）、required 2-a：理由、與第 3 條的差異、`engine.py:354-363` 依據須寫進本 ADR。

- **第 3 條**（`_check_gross_exposure`）現況：帳本有未估值持股時**一律** not_evaluable（來源：任務單問題段；6-b 任務單同述）。
- **第 2 條（本 ADR）**：已知同產業時，算出值 ≥ 上限**維持 violated**，只在未達上限時才 not_evaluable。
- **理由**（tech-architect 否決路線 A 的依據）：`engine.py:354-363` 只有 `violated` 擋加碼；若比照第 3 條一律 not_evaluable，會把**可證明的超標**轉成 not_evaluable 而放行加碼（危險方向退步）。分類表：只有 same 時算出值為下限、violated 必成立；same＋other／unknown 時方向不定，violated 為保守處理（W2 不得宣稱下限，見 required 2-b）。
- **差異（需文件化）**：同一帳本狀態下，第 3 條與第 2 條對「已超標但帳本不完整」的處理不同——第 2 條擋、第 3 條不擋。**此差異的第 3 條一側本身是缺口**，另列 6-b。
- **6-b 後續**（2026-10-07）：風控已自行修訂 FR-9 (a-附加)，把第 3 條「一律 not_evaluable」改為非對稱（未達上限 not_evaluable；已達上限 violated 附揭露），依據與適用見 ADR-0023；**code 尚未實作**（6-b 任務單狀態：待 W-b1／D-a3 字面核可）。實作後上述「差異」將消失，但 6-b 須排在本 ADR 之後落地（見 ADR-0023「6-b 與方向子句耦合」）。
- 風控 W2 限制：violated 的比率只在「全部 same」時為下限；其餘為保守處理，字面不得宣稱下限（required 2-b）。

## 對 2026-08-09 `/limits` 路線 (a) 的取代範圍

風控裁定 1（同意）：**只限 same 情境**。

- same：候選者轉 excluded 並以 W1 為由，或 ≥ 上限時以 violated 留下（符合 book_limits 規則 1）。
- **不變**：sector 為 None 的排除句、`EXCLUDED_SUFFIX`、空帳本、`NO_CANDIDATE_DETAIL` 字面照舊；sector None 仍走路線 (a)。（2026-10-07 補註：mixed 未估值群組的 sector 亦為 None；其中「沒有任何產業在比較中」者改用 W-6m，其餘續用現行句，見 Decision 1 補充 M-4。2026-10-07 風控 W-6u 段補註：未估值且完全沒有填產業（unknown）的標的，若 compared 為空，排除理由改用 W-6u；compared 非空仍續用現行句。）
- required 1-a：**W6 與 C′ 判定同一 PR 落地**（C′ 會讓「產業已知 Y、Y 不在比較中」變多）。
- required 1-b：`app/advice/book_limits.py:132` `NO_CANDIDATE_DETAIL` 的**註解**更新（字串不改）；註解內容依風控審查檔逐條第 7 點 (5)：「第 2 條 same 情境改採路線 C′（ADR-0022，風控 2026-10-07 核可）；sector 為 None 仍採路線(a)」。
- required 1-c：`test_advice_book_limits.py:466`「Route (a)」註解寫明 same 走 C′、sector None 仍走路線 (a)。

---

## Consequences（後果）

### 好處

- 決策卡、警示、`/limits` 三路徑一致；永不以可能偏低的比率回 passed；可證明的超標照擋（不退步於現況的擋加碼行為）。
- 「偏高」宣稱依分支收窄，不再與偏低的通過判定並列。
- 重疊皆 0 時第 2 條逐字不變，既有第 2 條測試零修改可作證。

### 代價（照實列）

1. 與第 3 條不對稱，需文件化（見上節）。
2. 新增 ≥ 3 句字面（W1～W3），另 W4／W5 改寫並拆出方向子句（D-a／D-P／D-d1／D-d2）、W6 新增、W7 取代 `WORST_SECTOR_PREFIX`；動到 cache_only 2026-09-18 三審固定句（改為條件式，D-a 條件下須逐位元組相同），風控已於 2026-10-07 重新核可。
3. **W2 經 fired 訊息進推播**，W2 誠實度限制（required 2-b）適用。
4. **只有 unknown 時警示 quiet 路徑讀不到 W3**：S-B2 失效條件 4 禁止把 `snapshot.reason`／`check.detail`／disclosure 接到 quiet reason。結果是 `any` 規則的「其餘已評估的上限皆未違反」會把第 2 條（passed 附 W3）算進去。
   - 風控裁定 4：**接受為殘留，不採加強版**（加強版不改變擋加碼結果、資訊價值大跌；與 AC-12.5 先例一致；reason 目前只在 API JSON）。等級 medium，**併 S-B2 失效條件 1**。
   - **required 4-b：AC-12.5（已估值但未填產業的持股）為同根因**——該情境下第 2 條同樣可能以偏低比率 passed，揭露同樣無法在 quiet 路徑呈現。AC-12.5 揭露於 `apps/stock-desk/backend/app/advice/book.py` 可見（`_unclassified_rollup`、`_sector_unclassified_note`，tech-writer 於 HEAD `8e8ccb5` 讀到其註解與 docstring，行號約 L130、L402-L425，以原文定位；其餘行為未驗證）。C-1 處理的是 `notional_caps` 納入，quiet 路徑揭露的殘留仍在。
   - required 4-a：S-B2 失效條件 1 重審範圍增列「第 2 條 passed 附 W3 或 AC-12.5 揭露時，『其餘已評估的上限皆未違反』是否需限定」。
5. **只監看 `sector_weight` 的規則**：same 且未達上限時，由 quiet 變 skipped；skipped 句尾「缺少輸入」口徑不精確（再一例；與 S-B2 列管 2 同類）。風控 suggested：併 S-B2 列管 2。
6. **試算排除時**出現既有已核可句「以下上限本次缺少可用資料…」（風控裁定 3：三情境皆適當，**字面一字不改**）。風控 suggested：qa-e2e 抽驗 violated＋reduce 時卡片並列「第 2 條 violated」與「第 2 條未參與計算」，375 寬是否讀得通。
7. **`/limits` 行為變更**：第 2 條在 same 情境取代 2026-08-09 路線 (a)（範圍見上節）。
8. **C-1 代價（6-c；風控已列給 CEO）**：帳本有已估值 ETF／美股／未填產業持股時，第 2 條**幾乎永不參與試算**（第 1 條 50% 仍參與、skipped 句揭露）。
9. **`SECTOR_UNCLASSIFIED_NOTE` 措辭（列管 low，creative-lead）**：現行 2026-08-09 核可句對 ETF／美股也寫「未填產業別」，暗示使用者遺漏，與 D6 先例不符；creative-lead 另起草三子類皆成立的中性句送風控審，**改動前現行句照舊**。
10. **6-c-1 改動既有分子計算**：`_sector_rollup` 改以標的為單位後，本標的 [X 已填, None] 兩筆皆已估值時，原本被排除的 None 筆會計入 `sector_market_value_twd`（見 K-2）；這是確定偏低的修正，非字面變更。

### 附帶列管（不屬本 ADR 決策，不擋本單；判定與適用見 ADR-0023）

- **6-a**（high，另開單）：決策卡第 1、4、5 條在本標的有未估值批次時，可能以偏低比率錯誤通過、不擋加碼（表一 d1／d2）。過渡期 required：W4／W5 在 d1 須明示第 1、4、5 條偏低、d2 須明示三條方向不定。6-a 落地後的方向子句處置（D-d1／D-d2 失去所指）由 creative-lead 另提送審。
- **6-b**（high，另開單，**不作 F-1 部署前置**）：第 3 條帳本不完整但已估值部分已超標時回 not_evaluable，不擋加碼。風控已修訂 FR-9 (a-附加)（見 ADR-0023）。CEO 知悉：F-1 會擴大 6-b 適用範圍；F-3 觸發升級時附上 6-b。**6-b 不得先於本 ADR 的 PR 落地**（風控 required）。
- **own>0 加碼降級**（medium，交 tech-architect）：own>0 且 action 為 add 時是否降為 hold 或 insufficient_data（新字面送風控）。見 ADR-0023。
- **F-1b**（匯率 ≤ 0，medium，列入 CEO 知悉）：見 ADR-0023。對本 ADR 的影響：匯率為負時總資產 E 可能小於分子 A，破壞 W1／D-d1「會偏低」前提（即失效條件 5）。
- **6-c**：已由風控裁定採 C-1（見 Decision 4 與 Consequences 8、9），不再屬「另案」。

### 被此決策約束的事

- 本 ADR 與 F-1 不同版、不同 PR；排 F-1 之後最近一個 release；避開 `alerts/engine.py` 進行中變更。
- 6-a、6-b 排本 ADR 之後（見 ADR-0023「排程」）。
- CEO 知悉清單 3(a)、3(b) 等本單落地才結案。
- CEO 知悉增補（風控 2026-10-07，與本 ADR 相關者）：(i) 風控曾核可的 D-d1 含數學錯誤，已在實作前更正，對使用者無影響；(v) C-1 代價（Consequences 8）。其餘增補項見 ADR-0023。

---

## 對實作的約束（K-1～K-11，qa 逐條核對）

K-1～K-10 來源為任務單「實作約束 1～10」，依序對應，風控 required：照錄，第 8 條（K-8）由 qa 逐條核對。K-2 依 6-c-1 修訂；K-11 為風控審查檔補記。

- **K-1**：重疊分類**只在 `book.py` 做一次**；`limits.py` 只讀新欄位，**不 import `app.portfolio`**。分類以標的為單位，與 `_sector_rollup`、`_unclassified_rollup` 共用同一解析函式（Decision 1）。
- **K-2**（6-c-1 修訂，風控 2026-10-07 同意，required）：`_sector_rollup`／`sector_market_value_twd` 的「**未估值持股不計入產業分子**」語意不變（`test_an_unvalued_holding_is_left_out_of_the_sector_total` **不改**）；但 `_sector_rollup` **改以標的為單位**：原本 `book.py:397` 逐筆 `== sector` 把 [X 已填, None] 兩筆中的 None 筆排除於分子，而 `position_market_value_twd` 含它，比率**確定偏低**，且 `others = S − current` 再被壓低。修法依共用的以標的為單位解析函式。
- **K-3**：「第 2 條可否被試算採用」**單一判斷式**共用（grep `notional_caps` 無重複條件）。全 repo 涵蓋第 1～5 條的單一判斷式見 ADR-0023。
- **K-4**：重疊皆 0（或 `book_fully_valued is True`）時，第 2 條 status／detail／observed **逐字不變**（既有 `test_advice_limits` 第 2 條測試**零修改**作證）。
- **K-5**：新欄位未設定的退路為「**產業未知**」（不猜同產業、不猜無重疊）。qa 以 `test_book_context_call_sites` 證明此退路在正式路徑走不到（風控 required）。
- **K-6**：not_evaluable 分支 `observed` 為 None，`threshold` 照舊。
- **K-7**：**不改 `alerts/engine.py`**。
- **K-8**：**不得複製或改寫已核可字面**；只能以風控逐字核可的新常數取代，並註明核可日期與審查檔。
- **K-9**：**前端不動**；新欄位比照 `sector_gap`，不同步 `types.ts`。
- **K-10**：**不得與 F-1 同 PR**（兩者都改 `build_book_context`；F-1 約束 7 禁後端繁中字串增加）；F-1 合併後 rebase。
- **K-11**（補記於 2026-10-07；來源為風控審查檔「落地 required」第 3、4、5 點，非任務單實作約束；qa 逐條核對）：
  - 每個新常數的註解須含「風控核可文案,修改須重新送審(2026-10-07)」與風控審查檔路徑；cache_only／live 方向子句另註明重新核可。
  - D-a 組合輸出須與 2026-09-18 兩則既有核可整句**逐位元組相同**，既有字面 pin 一字不改且通過。
  - D-d1／D-d2 的上限名稱須以 `LIMIT_NAMES` 組字串，不得手打；測試斷言渲染結果等於審查檔字面。

---

## 驗收與既有測試影響（轉錄摘要）

驗收條件（任務單摘要；全文依 tech-architect 原稿）：

1. 帳本 2330（已估值，半導體）＋2303（半導體，未估值；live／cache_only）＋其他產業已估值，另「本標的自身批次未估值」變體；分低於／達到上限。低於 → 第 2 條 not_evaluable、observed None、detail W1、`notional_caps` 無 `sector_weight`、any 規則 `UNEVALUATED_LIMITS_NOTE` 名單含「單一產業佔比上限」；達到 → violated、detail 以 W2 結尾、action add→hold 並出現既有「加碼建議被第 2 條上限（單一產業佔比上限）擋下。」、fired 訊息含 W2；`context_notes` 依分支表 W4／W5。
2. 只有其他產業 → 第 2 條逐字不變、`notional_caps` 含 `sector_weight`；只有產業未知（三子類參數化）→ passed detail 以 W3 結尾、violated 不變、`notional_caps` 不含、加碼區間 basis 含既有 skipped 句並列「單一產業佔比上限」。
3. 多產業帳本（半導體 2330 已估值／2303 未估值、金融 2881 已估值、未估值 ETF 0050）`GET /api/portfolio/limits`：第 2 條彙總不以「半導體業 passed」呈現；2303 與 0050 排除句依 W6／`SECTOR_UNVALUED_EXCLUSION_SUFFIX` 適用條件分別呈現；`notes` 為 `/limits` 範圍版本；`test_advice_limits`、`test_advice_book`、`test_advice_book_limits`、`test_api_advice`、`test_api_portfolio_limits`、`test_alerts_engine`、`test_alerts_snapshot`、`test_book_context_call_sites` 全綠，既有斷言只允許改字面常數引用與 `test_the_sector_cap_discloses_that_an_exclusion_can_understate_it` 的「Route (a)」註解。
4. **6-c C-1 GWT（tech-architect 三問評估所述）**：
   1. 2330 ＋ 已估值未填產業台股（ETF／美股參數化）→ 第 2 條 status／detail 不變、`SECTOR_UNCLASSIFIED_NOTE` 仍附、`notional_caps` 不含 `sector_weight`、basis skipped 句列第 2 條。
   2. 2330 [半導體, None] 兩筆皆已估值 → `sector_market_value_twd` 含兩筆、`test_an_unvalued_holding_is_left_out_of_the_sector_total` 不改。
   3. 無未分類 → 逐字不變。

既有測試影響（tech-architect 所述）：`test_advice_limits.py` `_ctx` 預設 `book_fully_valued=True`，現有第 2 條測試（L178-376、L1330）預期不變；`test_advice_book.py` L130-153 引用字面常數需跟改、L581 不得改；`test_advice_book_limits.py` L422／L454 單一產業帳本 100% 走 violated 分支，L454「Route (a)」語意改寫。

風控審查檔「落地 required」補充（qa 逐條；K-11 已收第 3、4、5 點，其餘如下）：

- 依優先序選方向子句；d1／d2 以本標的批次數比對全書 asked＋not_queried 總數；**參數化測試覆蓋 a、X=None、b、c、d1、d2、「d 且 X=None」**（須得 D-d1／D-d2，非 D-a）。D-d1 更正節進一步要求加「X None 且 own>0」斷言：第 2 條 detail 逐字＝`NO_SECTOR_DETAILS[gap]` 且方向子句為 D-d1／D-d2。
- `/limits` Y 未定義用 D-a，且**Y 未定義優先於 unknown**（2026-10-07 風控更正，見 Decision 5；R-1）；`_book_level_notes` 只加參數、不複製字面。
- 風控 W-6u 段 required（2026-10-07，qa 逐條）：
  - **R-2**：參數化測試「Y 未定義 × unknown 三子類（tw_unfiled／etf／non_tw）× live／cache_only」→ notes 與 2026-09-18 鎖定句逐位元組相同，且不含 `BOOK_TARGET`；加一格「Y 未定義 × 未估值 mixed（W-6m 情境）」→ D-a；等價性釘住：第 2 條 `evaluated_count == 0` 時 notes 不含 `BOOK_TARGET`，`evaluated_count > 0` 時 `reported_sector` 不是 None。
  - **R-3**：F-1 測試 `test_limits_list_the_bad_holding_as_unvalued_and_withhold_gross_exposure` **不改**（它的期望 D-a 整句在新優先序下是正確答案）。
  - **R-4**（suggested）：`test_adr0022_sector_unvalued.py:742-743` docstring「Y undefined, no unknown lot -> D-a」改成反映新優先序（Y 未定義優先於 unknown）；該測試為本 PR 新增，不算既有測試修改。
  - **R-5**：W-6u 與本 PR 同時落地，見 Decision 1 補充「W-6u」。
- **既有測試修改清單：無**（風控 W-6u 段）。F-1 測試不改；既有斷言 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 的四處（`test_advice_book_limits.py:447`——C′ 下 2330 在 100% 時 violated 仍在比較中；`test_adr0022_sector_unvalued.py:610`、`:618`——1101 水泥在比較中；`:651`——2881 在比較中）皆在 compared 非空的帳本上，W-6u 不影響。**這四處是風控讀碼推論、沒有實跑，須由 dev-lead 於實作後以測試結果確認**（tech-writer 未驗證，行號以原文定位）。
- W6 與 C′ 判定同一 PR；「Route (a)」註解依 1-c 改。
- 測試引用常數不得複製字面；新常數納入既有禁詞掃描範圍；審查檔標為不採或否決的句子一律不得實作。
- qa-e2e 375／1280 抽驗：決策卡第 2 條 W1、W3、D-d1 note；W2 在推播／feed 實際訊息。
- suggested（風控 6-c 裁定列管彙總）：qa 確認警示 bare context 在 own>0 時不走 `_inferred_sector_gap`。

QA／驗收補充：qa-e2e 抽驗決策卡第 2 條 not_evaluable 與 W3（375／1280）。

**2026-10-07 PR 驗收結果與實作形狀（轉錄）**

- qa-reviewer 2026-10-07：**PASS**，無 BLOCKING_ISSUES；Codex 第二意見**未執行**，環境不可用（來源：`work/reviews/2026-10-07-ADR-0022-PR-qa審查.md`）。
- 風控單項核對 2026-10-07：**APPROVE 附條件**（HEAD 1265c28 工作樹＝staged），條件 RC-1（D-d1／D-d2 進三份禁詞掃描）、RC-2（D-d1／D-d2 渲染結果以審查檔字面獨立算 sha256 釘住）；兩項**已補**（RC-1／RC-2 已補一事來源為 coordinator 指示；風控審查段原文為「合併前補、qa 確認即可」，tech-writer 未核對測試碼）。追認 `valued_unclassified_lots is None` 的解讀，附失效條件 F-13。來源：任務單檔尾「ADR-0022 PR 風控落地單項核對」段。
- finalizer 形狀：`book_notes(book, *, sector_comparison=None)`。**先不收 `gross_exposure_status`**，6-b 再加（`gross_exposure_status` 只加參數屬 ADR-0023 Decision 8-1 第 5 點「6-b 只加參數」；現在收卻只准 None 會違反 R-IN-1）。**R-IN-1 屬 6-b**。來源：任務單「ADR-0022 PR 實作進度與兩個衝突」段 dev-lead 回報；R-IN-1 的內容本檔未收錄，見 ADR-0023 與風控審查檔。
- 仍待：qa-e2e 第二十五輪（RM-5：`/limits` 三產業 W-6m 排除理由於 375／1280 不得截斷；RU-9 為 W-6u 於 0050 情境的整句渲染）；風控列請 qa 以 diff 補驗之四項（舊 `UNVALUED_POSITIONS_NOTE` 的 sha256、既有測試未改、`alerts/engine.py`／frontend／`RiskBudget`／`LIMIT_NAMES` 不在 diff、summary 層 ok 時市值非 None）是否已完成，來源未載，待查證（向 qa-reviewer 要）。

---

## 重審與失效條件

以下任一觸發，須回送風控重審（來源：風控審查檔「失效條件」節，2026-10-07；與原先分列的 S-B2、`notional_caps` 重審條目合併）：

1. 6-b 修法讓第 3 條在有無法估值部位時算出比率（D-a 會涵蓋偏低的第 3 條）。見 ADR-0023「6-b 與方向子句耦合」。
2. 6-a 修法改變第 1、**4**、5 條對本標的無法估值批次的處理（D-d1／D-d2 重審或撤除）。（2026-10-07 更正：風控審查檔原文僅列「第 1、5 條」，風控於該檔第一段「二、逐條」第 7 點更正為「第 1、4、5 條」；原「待風控確認」已結案。）
3. 6-c 擴及 AC-12.5，或 same／unknown／other 分類變更（如 ETF 穿透）。任何讓 `notional_caps` 納入第 2 條的變更，須回頭核對 Decision 4。（2026-10-07 風控裁定，風控審查檔第一段二.7：「6-c 擴及」**已被 C-1 涵蓋**；分類變更段繼續有效，並加「M-1／M-3 以外的再變更」。原「待風控確認」已結案。）
4. `_sector_rollup` 語意、`book_limits` 規則 3、`_one_per_sector` 變動，或上限編號／名稱／數量變動。（K-2 的以標的為單位改動即屬 `_sector_rollup` 變動，風控已同意。）
5. 允許零或負市值（空頭），或總資產可能小於產業市值。（F-1b 匯率 ≤ 0 的影響見 ADR-0023。）
6. 推播組成改變，使 W2 不再緊接產業句。
7. S-B2 失效條件 1 觸發（quiet reason 進 UI／推播／feed 或被 F-4「查看略過原因」納入）：併審 W3 的 quiet 殘留（見 Consequences 4）。ADR-0010 第 6 列管仍有效。
8. **F-8**（2026-10-07 增補；來源：風控第三段「四、失效條件增補」。此處「F-8」為風控審查檔的失效條件編號，與本 ADR 關聯段的 F-1 任務單無關）：`categories(G)` 改為包含非使用者填寫值（如系統推斷）、None 被算成一個類別、產業別改自由文字，或 `TWSE_SECTORS` 名稱或順序變動 → 重審 W-6m「所填產業別為」與排序。
9. **F-11**（2026-10-07 增補；來源：風控審查檔檔尾「`/limits` 方向子句優先序更正與 W-6u」段「失效條件增補」，逐字；風控建議編號 9、10）：發生以下任一 → 重審 `/limits` 優先序第 1 點與 D-P 的 `/limits` target。
   - 第 2 條在 comparable 為空時改成印出比率或判定。
   - sector 為 None 的候選者可以進入 comparable。
   - `reported_sector` 的定義改變（例如 comparable 非空時也可能是 None，或不再是被回報的那個產業）。
10. **F-12**（同上來源，逐字）：發生以下任一 → 重審 W-6u 的顯示條件與 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 的適用範圍。
    - unknown 子類或分類改變（例如 ETF 穿透）。
    - 「compared 產業集合」的定義改變。
    - `NO_CANDIDATE_DETAIL` 字面改變。
    - （2026-10-07 增補，來源：風控審查檔「W-6u 逐字審」段「失效條件」，沿用 F-12 增補兩點，逐字）第 2 條在 compared 為空時改成會產生任何比率或判定，例如加上帳本層級的備援計算。這時「無法確認…是否超過上限」會變成假句。這點和 F-11 第一點同時觸發。
    - （同上，逐字）「產業別資料」的來源或 `sector_categories` 的定義改變。例如系統自動帶入交易所產業別、空白字串改算成有值，或 W-6u 被接到 `SYMBOL_UNVALUED_NOTE` 以外的 reason 後面（那時就不再有筆數陳述）。
11. **F-13**（2026-10-07 增補；來源：任務單檔尾「ADR-0022 PR 風控落地單項核對」段「風控追認（附條件）」，風控追認 `valued_unclassified_lots is None` 視為「沒有已估值的未分類持股」所附條件，逐字）：任何會呈現給使用者或用於試算的路徑，產生 `valued_unclassified_lots is None` 的 context → 重審。（追認前提：正式路徑皆已被 K-5 測試釘住會設定此欄位。背景見 Decision 2 落地補充。）

其他：

- 加強版（unknown 的 passed 也改 not_evaluable）：風控 2026-10-07 裁定不採用；任務單未載明日後改採的程序，待 tech-architect 補充。

## 交接

- W1～W7：creative-lead 起草 → risk-compliance-officer 逐字審——**已核可（2026-10-07）**；改 accepted 尚待 CEO 未推翻之確認（見狀態欄）。
- 實作：dev-lead（F-1 合併後 rebase）→ qa-reviewer（K-1～K-11 逐條，K-8 重點）→ 風控單項核對。
- W-6m：creative-lead 起草 → 風控逐字審——**已核可修正版（2026-10-07，風控第三段）**；PR 合併前提見 Decision 1 補充 M-4。
- **W-6u（2026-10-07，風控 W-6u 段 R-5）**：creative-lead 起草 → 風控逐字審——**已核可替代案 W-6u-B（2026-10-07，風控「W-6u 逐字審」段）**；字面、RU-1～RU-9 見 Decision 1 補充「W-6u」。**合併前提：RU-1～RU-8 落地且 qa-reviewer 無 BLOCKING_ISSUES。**
- 實作補充（風控 W-6u 段）：dev-lead 照做 R-1～R-4、R-6（R-6 在 ADR-0023 KD-5，屬 6-b 範圍）；實作後以測試結果確認「既有測試修改清單：無」的四處斷言。
- **結案（2026-10-07）**：tech-architect 補寫 `/limits` 彙總對 mixed 產業的同等規則（原待補項）——已於 Decision 1 補充段（M-1～M-5）寫明，風控 2026-10-07 裁定（風控審查檔第二段 B；排序鍵與 W-6m 見第三段）。
- **待補（來源明載，尚未完成）**：
  - creative-lead：`SECTOR_UNCLASSIFIED_NOTE` 三子類皆成立的中性句（low）。
  - creative-lead：6-a 落地後 D-d1／D-d2 的處置（見 ADR-0023）。
- 6-a、6-b 另開單（判定見 ADR-0023）；own>0 加碼降級交 tech-architect；F-1b 交 dev-lead／devops-sre。
- CEO 知悉：3(a)、3(b) 等本單落地才結案。

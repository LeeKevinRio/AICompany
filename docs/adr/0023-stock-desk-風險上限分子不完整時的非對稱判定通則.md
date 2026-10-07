# ADR-0023：stock-desk 風險上限分子不完整時的非對稱判定通則

- 狀態：**proposed**
  - accepted 條件（須同時成立；來源：風控對 6-c 與 F-1b 的裁定「ADR-0023（proposed）同意」，2026-10-07）：**W-a1、W-a2、W-b1、D-a3、6-a 方向子句處置**皆經 risk-compliance-officer 逐字核可，**且** CEO 未推翻相關裁定。
  - **字面核可（2026-10-07，risk-compliance-officer 逐字核可；`work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第一段「核可字面總表」，下稱「風控審查檔」）**：結論為「APPROVE 附 1 處最小逐字修正（W-b1）」。核可日一律 2026-10-07：

    | 代號 | 核可狀態 | 核可日 | 本 ADR 對應處 |
    |---|---|---|---|
    | W-a1 | 核可（採 V1） | 2026-10-07 | Decision 4 |
    | W-a2 | 核可（採 A） | 2026-10-07 | Decision 4 |
    | W-b1 | 核可（修正：「計入無法估值的部位後」→「若計入無法估值的部位」） | 2026-10-07 | Decision 5 |
    | D-a3 | 核可（單一常數、短版） | 2026-10-07 | Decision 8、8-1 |
    | D-d1／D-d2 | 核可（**刪除版**，第二次改動；對應 6-a 方向子句處置） | 2026-10-07 | Decision 4；ADR-0022 D-d1 更正註記 |
    | N1 | 核可（照稿；**另開 PR，不併 6-a／6-b**；核可前現行 2026-08-09 句不動） | 2026-10-07 | 另案（ADR-0022 `SECTOR_UNCLASSIFIED_NOTE` 列管） |

    - 風控審查檔明載**不採**：W-a1-S、W-a1-V2、W-a1-F、W-a2-B、W-b1-A、D-a3 長版、D-d1-R／D-d2-R、N2。
    - **本 ADR 不收錄上列字面**（核可字面以風控審查檔為準；唯一例外為 (A) 降級句，見字面欄與 Consequences 殘留 1）。原「目前：字面尚未核可」之敘述（依據 6-a／6-b 任務單狀態）**已於本次更新移除**；實作前仍須遵守風控審查檔第一段「三、落地 required」R-1～R-11（見本 ADR「風控裁定轉錄」節）。
  - **(A) own>0 加碼降級**：已採；降級句字面風控核可（2026-10-07，風控審查檔第三段）。**(A) 仍不是 accepted 前提**（風控審查檔第一段五.5；第三段五）。詳見 Consequences 殘留 1。
  - **改 accepted 的剩餘前提（風控審查檔第一段五，2026-10-07）**：
    1. 風控審查檔轉錄（完成）。
    2. tech-writer 修 ADR-0023：核可日與審查檔路徑（不收字面）；失效條件 2 改第 1、4、5 條並併 F-1～F-7；結案 D-5 與 unknown-only 待查證；補 6-a 對 S-B2 條數影響（tech-architect 確認）；Consequences 1 改「(A) 落地後消除」——**本次落檔（2026-10-07 第二、三次）已依序處理，見各處標注**。
    3. tech-architect 補 D-a3 資料流與優先序段落——對應 Decision 8-1（tech-architect 2026-10-07；是否滿足由風控／coordinator 確認）。
    4. CEO 未推翻本裁定與 2026-10-07 各裁定，並知悉 (vii) M-1 高估方向、(viii) 降級／擋下原因只在預設收合的卡內可見——**仍待 CEO 表態**。
    5. (A) 新降級句**非** accepted 前提，但 ADR 須記「(A) 已採」（已記）。
- 日期：2026-10-07（6-a／6-b 的 tech-architect 評估與風控裁定日；補段落檔同日）
- 決策者：tech-architect（6-a、6-b 路線評估）；risk-compliance-officer（6-a、6-b 裁定；FR-9 (a-附加) 自行修訂；ADR-0023 同意）；CEO 為最終負責人（若對裁定有異議）。
- 適用範圍：僅 product/stock-desk 產品線。
- 來源與版本（B 類轉錄）：
  - 6-a：`work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md`（「tech-architect 評估（2026-10-07，HEAD d91fa8f 唯讀；coordinator 轉錄）」與「風控裁定（2026-10-07，coordinator 轉錄）」）。
  - 6-b：`work/dispatch/2026-10-07-任務單-6-b-總曝險上限帳本不完整但已超標時不擋加碼.md`（同上兩段）。
  - 數學通則、欄位結構、6-c 與 F-1b：`work/dispatch/2026-10-07-任務單-產業上限對同產業未估值持股的判定與揭露.md` 檔尾「tech-architect 對 creative-lead 三問與 6-c 的評估」與「風控對 6-c 與 F-1b 的裁定」（2026-10-07，coordinator 轉錄）。
  - FR-9 (a-附加) 修訂：`work/stock-desk-phase8-風控定調.md` 檔尾「修訂紀錄：FR-9 (a-附加)」（2026-10-07，風控自行修訂；原文保留於上方）。
  - 本檔為 tech-writer 落檔，**技術內容未增補、結論未改動**。來源內所有 `檔案:行號`、函式名、常數名、測試名皆為 tech-architect／風控所述，tech-writer **未重新對 code 驗證**；行號會隨 commit 漂移，引用時以原文定位。
  - 快照：分支 `product/stock-desk`，HEAD `331d42d73461c3584d62526fe248109500bfc714`（tech-writer 讀取 `.git/refs/heads/product/stock-desk`）；tech-architect 6-a／6-b 評估所用 HEAD 為 `d91fa8f`，兩者不同，此為快照。
  - 編號說明：落檔時 `docs/adr/` 最後一份為 ADR-0022；ADR-0023 係依 6-a 任務單「ADR 安排」新開。
  - 字面：本檔**不收錄 W-a1、W-a2、W-b1、D-a3 與 6-a 方向子句處置的字面**（核可字面以風控審查檔為準）。**唯一例外**：(A) own>0 加碼降級句，依 coordinator 指示逐字收錄於 Consequences 殘留 1（與風控審查檔不一致時以審查檔為準）。
  - 補段來源（2026-10-07，第三次落檔）：風控對 ADR-0022 PR 衝突 1 的裁定，來源為風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`（注意：與下列「風控審查檔」`上限分子不完整-非對稱判定` 為不同檔）檔尾「`/limits` 方向子句優先序更正與 W-6u（2026-10-07）」段。影響本 ADR 三處：Decision 8-1 第 6 點 `/limits` 列順序（Y 未定義改為第 1 點）、KD-5 `/limits`「Y 未定義」一格拆為「無 unknown」「有 unknown」兩格（R-6，6-b 範圍）、失效條件 F-11／F-12 指標（屬 ADR-0022）。**依風控裁定直接落檔，tech-architect 未另出補段**（coordinator 定案，CEO 可推翻）。本 ADR 狀態維持 proposed。ADR-0022 PR 的新增合併前提（W-6u 核可並落地）見 ADR-0022 Decision 1 補充。
  - 補段來源（2026-10-07，第二次落檔）：
    - tech-architect 補段：`work/reviews/2026-10-07-tech-architect-D-a3資料流-M段最終版-ADR-0022-0023補段.md`（讀碼基準 `product/stock-desk` HEAD `f25c90d`；coordinator 原文轉錄）——第一段→Decision 8-1；第二段→Decision 1 最後一點；第三段→Consequences 3。
    - 風控審查檔：第一段（核可字面總表、逐條意見、R-1～R-11、F-1～F-7、剩餘前提）、第二段（A. own>0 加碼降級；B. `/limits` mixed 群組）、第三段（A-降級句核可、RA-1～RA-7、F-9、ADR 狀態）、第四段（D-a3 資料流兩點補裁：R-IN-1／R-IN-2、F-10、RF-1～RF-6；2026-10-07，HEAD d66183e，coordinator 轉錄）。
    - 補段檔尾「建議送風控確認的兩點」已由風控於風控審查檔第四段裁定（皆 accept 附條件），見 Decision 8-1 第 3 點、Consequences 3 (g) 與文末「待確認／開放事項」。
    - 本次快照：分支 `product/stock-desk`，HEAD `d66183e`（coordinator 任務單所述，風控審查檔第四段亦載此 HEAD；tech-writer 未另行以 git 驗證）。補段內所有 `檔案:行號` 皆為 tech-architect（HEAD f25c90d）或風控所述，tech-writer 未重新對 code 驗證。

---

## 關聯

- **ADR-0022**（proposed）：`docs/adr/0022-stock-desk-單一產業佔比上限在同產業或產業未知持股無法估值時的判定.md`。本 ADR 引用其 Decision 1 的欄位結構並細化（見 Decision 3）；其失效條件 1、2、5 與本 ADR 直接相關。
- F-1：`work/dispatch/2026-10-07-任務單-F-1-組合估值對不可用收盤價的防護.md`。本 ADR 的 6-a、6-b 皆不作 F-1 部署前置。
- S-B2：`work/reviews/2026-10-07-S-B2-風險上限any規則-未評估揭露-字面-風控審查.md`（失效條件 6、8 見 Consequences）。
- FR-9 (a-附加)：`work/stock-desk-phase8-風控定調.md`（修訂紀錄，見 Decision「依據」）。
- 風控審查檔：`work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`（D-d1／D-d2 方向子句；「D-d1 更正」節與 6-a 失效條件 2 連動）。

---

## Context（背景）

以下皆為 6-a、6-b 任務單與 tech-architect 評估所述：

1. **6-a**：本標的自身有未估值批次時，決策卡第 1 條（單一標的佔比）與第 5 條（Kelly，observed＝權重）的分子只算已估值批次而**偏低**，可能以偏低比率回報 passed、加碼不被擋（危險方向）；第 4 條亦同（見數學通則與 ADR-0022「D-d1 更正註記」）。`/limits` 依 rule 3 排除有未估值批次的標的，故無此問題。
   - 依據（tech-architect 所述）：第 1 條 `limits.py:837-855`／`:673-679`；第 5 條 observed＝weight `:1126`／`:1153-1165`；第 4 條 `held_shares` `:695-702`／`:989`；`_position_rollup` 只加總 ok（`book.py:334-341`）。
   - **最嚴重情形**：台股某標的所有批次缺價格時 `position_market_value_twd = 0`、`quantity = 0`，與候選標的無法區分 → 第 1 條「佔總資產 0.00%」passed、第 4 條損失 0 passed，加碼不被擋。
2. **6-b**：`_check_gross_exposure` 遇 `book_fully_valued is not True` 一律 not_evaluable（`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` 揭露誠實、無錯誤通過），但 `advice/engine.py:354-363` **只有 `violated` 擋加碼** → 已估值部分已達上限時「能擋卻沒擋」。與 ADR-0022 否決路線 A 的理由同型。
3. 風控原 FR-9 (a-附加) 要求「任一部位估值失敗時，第 3 條一律回 `not_evaluable`」，6-b 評估指出與其牴觸，風控已於 2026-10-07 自行修訂（見 Decision「依據」）。

---

## 數學通則

來源：tech-architect 對 creative-lead 三問的評估（確認 creative-lead 的通則正確；2026-10-07）。

符號：**A**＝已估值分子、**E**＝已估值總資產、**a**＝分子集合**內**的未估值市值、**b**＝分子集合**外**的未估值市值。

| 上限 | 分母 | 真值 | 算出值 | 方向 |
|---|---|---|---|---|
| 第 1、2、4、5 條 | 已估值總資產 E | (A+a)/(E+a+b) | A/E | **b=0**：算出值為**下限**；**a=0**：算出值**偏高**；**a、b 皆>0**：方向**不定** |
| 第 3 條 | 自報淨值 N（與估值無關） | (A+a+b)/N ≥ A/N | A/N | **恆為下限** |

- 因此「**分子漏算只會偏低**」只對**第 3 條**成立；第 1、2、4、5 條在 a、b 皆 > 0 時方向不定。
- 第 4 條在 D-d1（見 ADR-0022）下亦為確定下限：同一 (symbol, market) 未估值批次每股台幣價值相同，(q_v+q_u)/(E+q_u·p) ≥ q_v/E ⇔ E ≥ A，市值非負時必然成立；跨市場幣別混雜時 close／atr 為 None，本就 not_evaluable（tech-architect 所述）。
- 「市值非負」是上述下限結論的前提（見 Consequences 的 F-1b）。

---

## Options（選項比較）

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| A（6-a 否決） | 分子不完整時一律 not_evaluable | 與第 3 條現況一致 | 放行可證明超標：`advice/engine.py:354-363` 只有 violated 擋加碼 | 危險方向退步，**否決** |
| C（6-a 否決） | 以 `quantity × close` 補估未估值批次 | 分子較完整 | 形成第二條估值通道 | **否決** |
| D（6-a 暫不採） | 第 4 條改用全部股數 | — | — | 列日後選項（來源未載優缺點細節） |
| **非對稱（採用）** | 分子不完整時：算出值 ≥ 上限 → violated 附揭露；否則 not_evaluable、observed None；兩者皆不進 `notional_caps` | 可證明超標照擋；不以偏低比率回 passed；比照 ADR-0022 C′ | 同一張卡可並列 violated 與「未參與計算」；與 ADR-0022 的 unknown 處理並存 | 見 Consequences |
| 6-b 原 FR-9 (a-附加)「一律」 | 第 3 條帳本不完整一律 not_evaluable | 揭露誠實、無錯誤通過 | 已達上限時不擋加碼 | 已由風控修訂取代 |

---

## Decision（決策）

選**非對稱規則**，套用於 6-a（第 1、4、5 條）與 6-b（第 3 條）。6-a 評估風控裁定 (1)：C′ 套用第 1、4、5 條**同意**；D-d1 時 violated 可靠，D-d2 時為保守處理。

### 1. 非對稱規則（通則）

當某上限的分子不完整時：

- 以已估值部分算出的值 **≥ 上限** → **violated**，detail 附對應揭露。
- 否則（未達上限）→ **not_evaluable**，**`observed` 為 None**，`threshold` 照舊。
- **第 5 條 D-5 分支**：own>0 時 **`observed` 改為 None**（風控 6-a 裁定 (3)，required）；該分支的 status／detail **不變**。（D-5 分支的判定內容，來源僅以此名稱稱呼，tech-writer 未讀 code 驗證，**待查證**：讀 `app/advice/limits.py` 第 5 條檢查函式。）**〔2026-10-07 結案〕**風控讀碼確認：D-5 分支為 `allowed <= 0` → violated，detail 為 `KELLY_NON_POSITIVE_FRACTION_DETAIL`（`limits.py:1127-1141`）；W-a2 不附於 D-5 分支（來源：風控審查檔第一段二.2；tech-writer 未重新讀 code 驗證）。
- required（風控 6-a 裁定 (3)）：前端 `formatPercent(null)` 顯示「—」；qa 確認警示 snapshot／event 對「violated 且 observed None」不出錯。
- 第 5 條在 own>0 的 not_evaluable 分支，`threshold` 仍為 allowed（tech-architect 所述）。
- 「第 2 條」的對應規則（same、W1／W2）由 ADR-0022 Decision 3 規定。**第 2 條只有 unknown（same＝0、unknown＞0）時 passed 附 W3，是本通則明列的例外**：判定上維持 passed（風控 2026-10-07 不採加強版，見 ADR-0022 Consequences 4）；**試算上屬分子不完整，依 KC-2 不得進 `notional_caps`**。此點 ADR-0022 Decision 4 第一句已規定（unknown＞0 即排除），本 ADR 不另立條文（tech-architect 2026-10-07 確認）。
  - 第 2 條「分子不完整」的判斷式：same（`own_lots + same_sector_lots`，X 不為 None 時）＞0，或 unknown＞0，或已估值未分類持股存在（C-1）。只有 other 時分子完整（算出值偏高），仍可進 `notional_caps`。X 為 None 時第 2 條沒有比率，本來就不進（`limits.py:1223` 閘門）。
  - 因此 own>0 時，第 2 條無論在哪個分支都不進 `notional_caps`，與第 1、4、5 條一致（R-8）。上述條件與第 1、3、4、5 條的條件同屬 KC-2 全 repo 單一判斷式，各條件分列於同一函式。
  - （此條原標「待 tech-architect 確認」，2026-10-07 結案；改寫文來源：tech-architect 補段第二段。）

### 2. 「可否用於試算」單一判斷式

- **全 repo 單一判斷式**，涵蓋**第 1～5 條**；**分子不完整時，即使 violated 也不進 `notional_caps`**；分子完整時逐字不變（來源：tech-architect 三項共用實作約束；風控 6-a 裁定 (1)）。
- 理由：
  - 6-a：第 1 條額度＝上限 − 偏低的 current，會被高估（風控）；否則 `_passes` 在賣出分支會產生假句「把這一檔全部賣出後仍然超標」（tech-architect）。
  - 6-b：否則賣出試算會產生假「仍然超標」。第 3 條 `notional_caps` 閘門（`limits.py:1231-1236`）由 `!= "not_evaluable"` 改為共用判斷式「分子完整（`book_fully_valued is True`）」。
- 判斷式在全 repo 只存一處（6-a 約束：grep `own_lots`）。

### 3. 欄位結構

- 引用 **ADR-0022 Decision 1**：`PortfolioContext.unvalued: UnvaluedComposition | None`（`own_lots`／`same_sector_lots`／`unknown_sector_lots`{`tw_unfiled`／`etf`／`non_tw`}／`other_sector_lots`；不變式：四類加總＝全書 `status != "ok"` 筆數）。欄位在 ADR-0022 的 PR 一次建好；**6-a 只讀不改 `build_book_context`**。
- 本 ADR 的細化（依 6-a 與 6-b 評估整理）：
  - 第 1、4、5 條讀 `own_lots`（own>0 即分子不完整）；D-d1／D-d2 以分割欄位區分，無需新欄位（ADR-0022 Decision 1）。
  - 第 3 條**不讀** `unvalued`，讀 `book_fully_valued`（`is not True` 即分子不完整；6-b 不依賴 ADR-0022 欄位）。
- **退路（欄位 None）**：6-a 的退路為「欄位 `None` 且 `book_fully_valued is True` → 視為 0；否則視為 own>0」。此與 ADR-0022 Decision 2 對第 2 條的退路（否則視為「產業未知」）**並存**。手刻 context 的測試 `book_fully_valued` 預設 `None` 會走退路（tech-architect 所述）。qa 須以 `test_book_context_call_sites` 證明退路在正式路徑走不到（6-a GWT 3）。

### 4. 6-a 適用：第 1、4、5 條（own>0）

- 算出值 ≥ 門檻 → violated，原句後接 **W-a2**；否則 not_evaluable，detail＝**W-a1**，observed None，threshold 照舊。
  - **W-a1、W-a2 已於 2026-10-07 經風控逐字核可**（W-a1 採 V1，W-a2 採 A；風控審查檔第一段二.1、二.2）。風控 required：W-a1 只在比率已算出時使用，缺 ATR、缺總資產、weight None、Kelly 不可用等既有成因維持原 detail；W-a2 不用「上述」，D-5 分支不附。三條同時 violated 推播約 200 字，風控接受（去重屬 alerts/engine 另案 low；去重須保留成因、比率範圍、處理方式三件事並送審），R-9 實測長度。
  - **D-d1／D-d2 刪除版已於 2026-10-07 核可**（第二次改動，風控審查檔第一段二.5）；required：刪除版與 6-a 的 C′ 判定**同一 PR**（ADR-0022 PR 先上帶分句版本，當時第 1、4、5 條仍可能 passed，分句仍成立）；不採 D-d1-R／D-d2-R。**N1** 核可照稿，另開 PR（風控審查檔第一段二.6）。
- 三條**一律不進 `notional_caps`**（即使 violated）。
- W-a1／W-a2**不帶筆數**（卡片已有 `SYMBOL_UNVALUED_NOTE`；退路分支可共用同句）。
- W-a2 進推播（風控 required）：推播無 `SYMBOL_UNVALUED_NOTE`，W-a2 須自述「本標的有持倉無法估值、比率只用已估值部分、以已達上限處理」；同句用於 d1 與 d2，故**不得宣稱下限或「實際只會更高」**，無賣出指示或催促。
- 既有 skipped 句（「缺少可用資料」）延用到「分子不完整而排除」，**字面不改**（風控 6-a 裁定 (4)）；卡片可能並列「第 1 條 violated」與「未參與計算」，qa-e2e 375 抽驗。
- **required（6-a 同一包）**：own>0 時方向子句處置（ADR-0022 的 D-d1／D-d2 因第 1、4、5 條不再有 passed 而失去所指）由 creative-lead 提出，送風控逐字審。suggested：qa 確認警示 bare context 在 own>0 時不會走 `_inferred_sector_gap` 推成 no_position（`limits.py:871-873`）。

### 5. 6-b 適用：第 3 條（`book_fully_valued is not True`）

- A/N ≥ 上限 → **violated**，`observed`＝A/N，detail＝既有 violated 前句（`limits.py:969-970` 句構）＋ **W-b1** ＋ `_net_worth_disclosure`（原三句揭露 required 不變）；**未達上限 → 維持 `limits.py:957-963` 逐字不變**（`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` 字面不改）。
- **W-b1 已於 2026-10-07 經風控逐字核可（採 C 並做一處最小逐字修正：「計入無法估值的部位後」→「若計入無法估值的部位」）**（風控審查檔第一段二.3）。風控意見：「…後」為時間語氣，可能被讀成已計入，「若」為條件句，字數不變；下界宣稱含等於；「上述數字」兩種讀法皆真（真值 ≥ A/N ≥ 門檻）；不受 F-1b 影響（壞匯率只讓 A 更小），前提為未估值部位真實市值 ≥ 0。
- **W-b1 專屬變體**（風控 6-b 裁定 (2)）：概念同意，**逐字「實際曝險只會更高」否決**（真實市值可能接近 0 而排除持平；「實際曝險」還受自報淨值與收盤價時效影響）。允許範圍：方向宣稱限定為「計入無法估值的部位後，比率不會低於上述數字」類句；不得省略限定語；不得操作指示。由 creative-lead 起草送審。
- **與 W-a2 的差異**：第 3 條分母獨立（自報 N），故可宣稱下限方向；W-a2 因 d2 方向不定而不得（tech-architect）。
- **分子單調性確認（tech-architect，與 6-b 任務單原寫法的前提不同）**：決定 violated 可靠的是**每筆未估值部位真實市值 ≥ 0**——`quantity > 0` 有強制（`positions/models.py:100-104`、`190-193`、L295 繼承）、產品無空頭欄位、真實價格 ≥ 0 與匯率 > 0 為經濟事實、分母 N 自報（`limits.py:964`、`book.py:691`）。**close ≤ 0 不影響 violated 可靠性**（壞 close 使已估值項變負只會讓 A 更小、violated 更難成立；破壞的是 passed 方向，屬 F-1）。故 **6-b 數學上不必等 F-1**，F-1 只擴大其適用範圍。

### 6. 退路規則

見 Decision 3「退路」：6-a 為「欄位 `None` 且 `book_fully_valued is True` 視 0，否則視 own>0」；ADR-0022 K-5 為「視為產業未知」。兩者並存（來源：6-a 評估與 ADR-0022 Decision 2）。

### 7. 依據：FR-9 (a-附加) 2026-10-07 修訂

- 風控已自行修訂 FR-9 (a-附加)（`work/stock-desk-phase8-風控定調.md` 檔尾；**原文保留不覆寫**）。修訂文字：
  > required｜任一部位估值失敗時，第 3 條：以已估值部位計算的比率**未達上限** → `not_evaluable`（不得以偏低比率回報通過）；**已達或超過上限** → `violated`，detail 附 W-b1 揭露分子不完整，且不得進入 `notional_caps`。理由不變：分子漏算只會讓比率偏低；已達上限時，偏低只會加強違反的結論（比照 ADR-0022 C′）。三句揭露 required 不變。修訂日 2026-10-07，取代原「一律」字面。
- **ADR-0023 只能引用本修訂為依據，不得代為推翻原裁定**（修訂紀錄原文）。原理由「不得往偏低方向偏」仍成立（tech-architect 所述）。
- 修訂紀錄所依據的任務單：6-b 任務單。

### 8. 6-b 與方向子句耦合；排序

- 6-b 修法會觸發 **ADR-0022 失效條件 1**：D-a「比率會因此偏高」（現行 `UNVALUED_POSITIONS_NOTE` 整句，`book.py:154`／`:167`，風控所述）會涵蓋第 3 條，與 W-b1 矛盾，削弱有效阻擋。
- **D-a3 已於 2026-10-07 經風控逐字核可（單一常數、短版；不採長版）**（風控審查檔第一段二.4）。資料流耦合附條件：(a) 選句須讀**同一回應中第 3 條實際 CheckResult status**（決策卡讀 `evaluate_limits`，`/limits` 讀 baseline 經 `_book_level_check`），不得在 `book.py` 用淨值、門檻再算；(b) 不採「淨值新鮮＋帳本不完整就用 D-a3」；(c) tech-architect 於 ADR-0023 寫明組裝順序與 D-a3 在優先序位置（只在原選 D-a 處替換，D-P／D-d1／D-d2 不動）——accepted 前提之一，見 Decision 8-1。a0 時「第 2 條比率會因此偏高」講未印出的比率，為 D-a 既有語意，不為假。
- **required 新增 D-a3**：方向子句變體，第 3 條帳本不完整下 violated 時使用，**明確排除第 3 條於「偏高」之外**；決策卡與 `/limits` 兩範圍，由 creative-lead 起草。**D-a 原句只在第 3 條 not_evaluable 時使用**，並與 2026-09-18 鎖定句逐位元組相同。（D-a3 在 ADR-0022 方向子句優先序中的位置，來源未載，**待查證**：待 creative-lead／風控提出優先序修訂。）**〔2026-10-07 結案〕**D-a3 的優先序位置與資料流見下 Decision 8-1（tech-architect 2026-10-07；風控審查檔第一段二.4 要求 tech-architect 寫明，為 accepted 前提之一）。
- **required：6-b 不得先於 ADR-0022 PR 落地**（風控 6-b 裁定 (4)）。tech-architect 評估原述「6-b 不依賴 ADR-0022 欄位，可先於 ADR-0022 落地」，風控裁定改為不得先於；以風控裁定為準。理由：不能讓「偏高」與 violated 並陳（CEO 知悉增補 (iv)）。

### 8-1. D-a3 資料流、組裝順序與優先序（tech-architect 2026-10-07，HEAD f25c90d 唯讀讀碼；風控 accepted 前提 3）

（來源：tech-architect 補段第一段，coordinator 原文轉錄；風控 D-a3 資料流耦合條件見風控審查檔第一段二.4。KD-1～KD-6 為 tech-architect 補段的編號。）

**現況（讀碼）**
- 決策卡：`api/advice.py:188-200` 先呼叫 `build_book_context`，notes 在其中組好（`book.py:657` 呼叫 `_book_level_notes`；D-a 槽位在 `book.py:546-549`，常數 `:154-156`、`:166-169`）。第 3 條要到之後的 `build_advice` 才判定（`advice/engine.py:354` `evaluate_limits`），結果以 `limits_check` 放進卡片（`:390`）。回應組裝在 `api/advice.py:241`：`context_notes=[*_book_freshness_notes(summary), *book.notes]`。因此現行 notes 組好時，第 3 條尚未評估。
- `/limits`：`book_limits.py:291` 呼叫 `build_book_level_context`（notes 於 `book.py:578` 組好）→ `:292` baseline → `:308` `_book_level_check`（`:315-341`，只在空帳本時覆寫 status，`:325-337`）→ `:312` `BookLimits(notes=book.notes)`。
- 警示：`alerts/snapshot.py:122-158` 只讀 `book.context`、`book.fx_note`、`book.fx_rate`，不讀 notes；`book_limits._symbol_context`（`:396-416`）只取 `.context`。兩者都不受 D-a3 影響。推播不含 D-a3，第 3 條方向由 W-b1 經 detail 進推播。
- D 槽位出現的條件（`book.py:539` `valued_count < total_count`）與 `book_fully_valued is not True`（`_fully_valued`，`book.py:279-285`；寫入 context 於 `:593`、`:704`）出自同一份 summary，兩者等價。
- 現行方向子句中，只有 D-a 涵蓋第 3 條：D-P 只講第 1、4、5 條與第 2 條；D-d1／D-d2 刪除版只講第 1、4、5 條。因此 D-a3 只需在 D-a 的位置替換。

**決策**
1. **選句只在一處**：`_book_level_notes` 新增 keyword-only 參數 `gross_exposure_status: LimitStatus | None`，不給預設值。D-a3 只在此函式內選用，條件為「依 ADR-0022 優先序原本會選 D-a，且 `gross_exposure_status == "violated"`」。每次呼叫只選一次，live 與 cache_only 兩則 note 共用同一個方向子句（「{成因}；{D-a3}」各自接）。
2. **status 來源（同一回應中實際的第 3 條 CheckResult）**：
   - 決策卡：`card["limits_check"]` 中 `id == "gross_exposure"` 那筆的 `status`，也就是 `advice/engine.py:354` `evaluate_limits` 的結果、回應實際送出的那一筆。
   - `/limits`：`limits` 中 `limit_id == "gross_exposure"` 那筆 `BookLimitCheck` 的 `status`，也就是 `book_limits.py:308` `_book_level_check(index, baseline["gross_exposure"], ...)` 的輸出。不得直接讀 baseline，也不得讀 per-symbol context。
   - 查找不給預設值：已評估的回應中找不到第 3 條屬程式錯誤，直接拋出例外，不得默默退回 D-a。
3. **`None` 的語意**＝「本回應不含第 3 條判定」。只允許用在 `api/advice.py` 的 insufficient_data 分支（`:202-222`：不建卡、不評估上限）。此時維持 D-a；該回應沒有任何第 3 條數字，R-5「D-a 絕不與第 3 條 violated 同現」仍成立。
   - **風控裁定（2026-10-07，風控審查檔第四段，HEAD d66183e）：accept。** 理由（風控所述）：(1) `api/advice.py:202-222` 不建卡、不評估上限；回應雖帶 `context_notes=book.notes`（L219），前端 `page.tsx:543-548` 只渲染 InsufficientPanel，全前端唯一渲染 context_notes 處為 ok 分支 `page.tsx:575-586`，後端無其他讀者（grep `context_notes` 只有 `api/advice.py`）；與 S-B1、S-2「只在 API、頁面不渲染」先例一致。(2) R-5 原規則「D-a 原句只在第 3 條不是 violated 時使用」；insufficient 是「第 3 條沒有判定」的子情形，未擴大語意，「D-a 絕不與第 3 條 violated 同現」仍成立。(3) 同回應 `portfolio_context` 有 `gross_exposure_twd`、`net_worth` 等輸入，但無第 3 條比率或判定，畫面不顯示。
   - **R-IN-1（required）**：insufficient 分支呼叫 finalizer 時明寫 `gross_exposure_status=None`（KD-2）；`None` 只准用在此分支，qa grep 確認。
   - **R-IN-2（required）**：KD-5 的 R-5 負向測試加一格「insufficient 分支」，斷言 D-a 逐位元組相同、不含 D-a3、回應無 `advice`／`limits_check`。
   - **失效條件 F-10**：見本 ADR「重審與失效條件」。
4. **組裝順序（兩個範圍相同）**：①建 context（`build_book_context`／`build_book_level_context`）→ ②評估上限（決策卡：`build_advice` 內的 `evaluate_limits`；`/limits`：baseline、`_aggregate`、`_book_level_check` 全部完成）→ ③以②的實際 status 組 notes → ④組 response。決策卡維持 `[*_book_freshness_notes(summary), *notes]` 的順序（風控 A-6）。
5. **實作形狀**：
   - `BookContext` 保留組 notes 所需的輸入。book.py 新增公開純函式（暫名 `book_notes(book, *, gross_exposure_status)`），回傳 `[*_book_level_notes(...), *個股層 notes]`，順序與現行 `book.notes` 相同。
   - `BookContext.notes` 保留作相容用，定義為 `book_notes(book, gross_exposure_status=None)` 的結果，既有測試因此零修改。但 production code（`app/`）不得再讀 `BookContext.notes`，insufficient_data 分支也改為明寫 `gross_exposure_status=None`。
   - `/limits` 的 D-P 判定需要「回報產業 Y」，Y 要到 `_aggregate` 之後才知道，所以 ADR-0022 PR 本來就必須在評估後才組 `/limits` notes。架構要求 ADR-0022 PR 就建立上述 finalizer，並讓兩個範圍都經過它。6-b 只加 `gross_exposure_status` 參數與 D-a3 常數，並調整 `api/advice.py` 的組裝順序。
6. **優先序（只在原選 D-a 處替換；D-P／D-d1／D-d2 不動）**：
   - 決策卡：(1) `own_lots > 0` → D-d1／D-d2（刪除版）；(2) X 為 None 且 own=0 → 第 3 條 violated 用 D-a3，否則 D-a；(3) same 或 unknown > 0 → D-P；(4) 其餘 → 第 3 條 violated 用 D-a3，否則 D-a。
   - `/limits`（**2026-10-07 風控更正順序**，來源：風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u」段；取代原 tech-architect 補段的順序；第一個符合的就用）：(1) Y 未定義，即第 2 條 comparable 為空、`reported_sector is None` → 第 3 條 violated 用 D-a3，否則 D-a；(2) 帳本有任何 unknown，或 Y 有 same（依 ADR-0022 M-3／M-5，mixed 群組的 categories 含 Y 也算）→ D-P，target 為「已納入比較的產業」；(3) 其餘 → 第 3 條 violated 用 D-a3，否則 D-a。
     - 更正註記（2026-10-07，風控）：原順序為「(1) 有 unknown 或 Y 有 same → D-P；(2) Y 未定義 → D-a／D-a3；(3) 其餘」。原第 (2) 點置於 D-P 之後為筆誤（死條款），風控定性為更正自身優先序的筆誤；詳見 ADR-0022 Decision 5。
     - D-a3 仍只在「原選 D-a」處替換（第 1、3 點）；D-P 不動（第 2 點）。
   - D-P、D-d1、D-d2 不因第 3 條 status 改變。第 3 條 violated 時，W-b1 已在該條 detail 揭露方向。
7. **禁止重算**：book.py 不得接收 `RiskBudget`、不得讀 `max_gross_exposure`、不得 import 或呼叫 `_breaches`／`_check_gross_exposure`，也不得用 `gross_exposure_twd`、`net_worth.amount_twd` 計算任何比率。
8. **不變式**：帳本不完整時，第 3 條 status 只能是 violated 或 not_evaluable（`limits.py:957-963` 由 6-b 拆出 violated 分支）。`_book_level_notes` 不對 passed 做特別處理；一旦出現 passed，即觸發 F-4 重審。
9. **落地與範圍**：
   - D-a3 與 6-b 的 violated 分支必須同一個 PR。若 D-a3 先上，它是死碼；若 6-b 先上，D-a 會與 violated 並陳。
   - **本節修訂 KB-1／KB-3 的範圍**：6-b 可以動 book.py（新參數；D-a3 常數；若 ADR-0022 PR 未建 finalizer，也包含 finalizer）、`api/advice.py`（組裝順序）、`book_limits.py` `evaluate_book_limits` 中組 notes 的那一處（`:312`）。
   - `_book_level_check`、`_aggregate`、`alerts/engine.py`、前端仍然不動。

**Consequences**
- 好處：選句只依同一回應實際送出的第 3 條判定，D-a 與 D-a3 的同現規則可以用測試窮舉。
- 代價：`BookContext` 介面擴充；兩個呼叫端的組裝順序改變；ADR-0022 PR 範圍略增（finalizer）。
- 殘留：insufficient_data 分支維持 D-a。該分支沒有任何上限數字，前端只渲染不足面板（風控 A-8），不擴大既有語意。（風控 2026-10-07 第四段已裁定 accept 附 R-IN-1／R-IN-2、F-10，見第 3 點與「重審與失效條件」。）

**可檢查約束（qa）**
- KD-1：grep D-a3 常數，只出現在 `_book_level_notes` 與測試。
- KD-2：`app/` 內讀 `BookContext.notes` 的次數為 0；兩個回應組裝點都經過 finalizer，並明示 `gross_exposure_status`。insufficient 分支明寫 `gross_exposure_status=None`，`None` 只准用在該分支（風控 R-IN-1，2026-10-07）。
- KD-3：book.py 不出現 `RiskBudget`、`max_gross_exposure`、`_breaches`、`_check_gross_exposure`。
- KD-4：第 3 條 status 的查找不帶預設值（不得有 `next(..., None)` 這類寫法）。
- KD-5：R-5 負向測試範圍＝兩個範圍 × live／cache_only × 兩則 note 並存 × 優先序各分支（決策卡 a0、a、b、c、d1、d2；`/limits` 的 Y 未定義、Y 有 same、有 unknown、其餘）× 第 3 條 status（violated、not_evaluable 的各成因）。**（2026-10-07 風控 R-6，required；來源：風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u」段：`/limits`「Y 未定義」一格拆成「無 unknown」與「有 unknown」兩格；兩格都只在原本會選 D-a 的情況下才可能換成 D-a3。這是 6-b 的範圍，現在先寫進 ADR。）** 只有「原選 D-a 且 violated」得到 D-a3；D-P／D-d1／D-d2 分支在 violated 時逐字不變。**另加一格「insufficient 分支」（風控 R-IN-2，2026-10-07）**：斷言 D-a 逐位元組相同、不含 D-a3、回應無 `advice`／`limits_check`。
- KD-6：參數化測試證明帳本不完整時第 3 條 status 只有 violated 或 not_evaluable（淨值 None／過期／新鮮 × A/N 高於、低於門檻）。

### 9. 排程

- 6-a：部署於 F-1 之後、ADR-0022 PR 之後；不作 F-1 部署前置。
- 6-b：數學上不必等 F-1（風控同意）；排 F-1 後最近一個 release；**不得先於 ADR-0022 PR**；不作 F-1 部署前置。
- **F-3 觸發部署前置升級時，升級資料須附上 6-b**。
- 流程：6-a：creative-lead（W-a1／W-a2／方向子句處置）→ 風控 → ADR-0023 → dev-lead（ADR-0022 PR 後）→ qa → 風控單項核對；qa-e2e 375／1280。6-b：creative-lead（W-b1／D-a3）→ 風控逐字 → dev-lead → qa → 風控單項核對。

---

## Consequences（後果）

### 好處

- 第 1～5 條對分子不完整採同一原則：永不以可能偏低的比率回 passed；可證明的超標照擋。
- 試算判斷式全 repo 單一處，分子不完整時不產生假「仍然超標」句。

### 代價與殘留（照實列）

1. **6-a 加碼殘留（medium）**：own>0 時第 1～5 條常全數無法試算、股數區間為 None，**加碼仍不被擋**（`not_evaluable` 不擋）。風控接受為殘留；**列管 medium 另案交 tech-architect**：own>0 且 action 為 add 時是否降為 hold 或 insufficient_data（新字面送風控）。CEO 知悉增補 (iii)：6-a 修後本標的持倉無法估值時加碼建議仍可能出現（不給股數）。
   - **(A) 已採，降級句字面風控核可（2026-10-07，`work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第三段）**。(A)＝own>0 且 action 為 add 時降為 hold（風控審查檔第二段 A.1「採 (A) 同意；否決 B／B′／C／D」；第三段 RA-3「action 改 hold」）。
   - **(A) 仍不是 accepted 前提**（風控審查檔第一段五.5；第三段五）。**CEO 知悉 (iii) 維持「(A) 落地且 qa 通過後消除」；新殘留 (viii) 仍列**（見下）。**A(5) 照舊**：(A) 與 6-a 同包；字面落後時 6-a 先發；條件為 (A) 排 6-a 之後最近一個 release、不得無限期延後（風控審查檔第二段 A.5；第三段五）。
   - **逐字核可字面**（風控審查檔第三段一，2026-10-07；與風控審查檔不一致時以審查檔為準）：

     | 代號 | 逐字核可字面 | 變數 | 顯示條件 | 字數 |
     |---|---|---|---|---|
     | **A-降級**（own>0 加碼降級句） | 本標的有持倉無法估值，無法用風險上限確認加碼；加碼建議改為觀望。 | 無 | 決策卡 `downgrade_notices`。own>0 用 6-a 同一判斷式；且在防禦型降級（`engine.py:341-352`）與上限擋下（`:354-363`）兩步之後 action 仍為 add。已 insufficient_data、已降級、已擋下的卡不附。 | 32 |

   - **新降級句約束**（風控審查檔第二段 A.3；字面已核可，此為約束紀錄）：成因用語與 W-a1／W-a2 一致「本標的有持倉無法估值」；後果句不得預設部位在範圍內（不得帶「仍」前提），只講「無法用風險上限確認加碼」；不承諾恢復、不寫補資料指示；結尾沿用「加碼建議改為觀望」；已擋下／已降級／已 insufficient_data 的卡不重複附加。
   - **(A) 落地 required（RA-1～RA-7，風控審查檔第三段三，qa 逐條核對）**：
     - **RA-1**：新常數註解「風控核可文案,修改須重新送審(2026-10-07)」＋本審查檔路徑。
     - **RA-2**：own>0 必須用 6-a 同一判斷式，全 repo 只能一處。
     - **RA-3**：位置固定在上限擋下之後、`suggest_quantity_range` 之前；action 改 hold 後才算數量，卡上不得出現加碼數量區間；`blocked_action` 維持 None（這句不是擋下）。
     - **RA-4**：`engine.py:351` 既有句逐位元組不變；若抽「加碼建議改為觀望。」為共用片段，既有句渲染結果必須逐位元組相同、既有測試不改一字。
     - **RA-5**：參數化測試涵蓋：own>0＋add＋無 violated → 卡變 hold、`downgrade_notices` 等於常數、數量為 hold 結果；own>0＋add＋有 violated → 只有擋下句；own>0＋防禦型命中 → 只有既有降級句；own>0＋insufficient_data → 無此句；own=0 → 輸出逐字不變。
     - **RA-6**：新常數納入三份禁詞掃描；風控審查檔第二段 A.2 的 qa-e2e required 照舊（降級卡在操作摘要不顯示信心、依據、數量區間；展開後可讀降級句）。
     - **RA-7**：失效條件 F-1 同樣適用——只要有正式、會呈現給使用者的路徑走到退路分支，「本標的」就是未經驗證的陳述，必須重審。
   - **(viii) 降級／擋下原因只在預設收合的卡內可見**（風控審查檔第一段五.4；第二段 A.2）：`downgrade_notices`／`blocked_notices` 只在 `AdviceCardView` 內，整張建議卡預設收合（`page.tsx:550`，CEO 2026-09-19 裁定），主視圖只見「續抱參考」不見原因。既有缺口不擋 (A)，**新列管 medium**（creative-lead／art-lead／frontend：操作摘要加一行「結論已調整」可見標記，新字面送審）；美股匯率失敗時 own>0 常見會放大缺口（以上為風控所述）。
2. **F-1b（匯率 ≤ 0，medium，列入 CEO 知悉）**：`FxRate.rate` 無驗證器（`providers/fx.py:89`）、台銀解析取買賣中價無正值檢查（`:280-298`）、`valuation.py:393-417` 亦無（tech-architect 所述）；匯率＝0 時外幣持股以 ok 狀態市值 0 出現，總曝險與產業分子被低估而錯誤通過，與 F-1 D2 同型；匯率為負時 E 可能小於 A，破壞 ADR-0022 W1／D-d1「會偏低」前提（ADR-0022 失效條件 5）。**對本 ADR 的影響**：本 ADR 數學通則與 6-b 分子單調前提都依賴「市值非負」與「匯率 > 0 為經濟事實」，F-1b 使此前提在 code 上**沒有強制**。
   - 併入 F-1 的條件：dev-lead 尚未開工且只沿用既有 fx missing token 與字面；否則另開單排同一或下一 release。
   - **required**：F-3 腳本一併掃本機快取匯率 ≤ 0，查到則比照 F-1 升級部署前置；qa 確認本標的匯率 ≤ 0 時 `PortfolioContext.fx_to_twd gt=0` 不會讓卡片或 `/limits` 回 500。
3. **S-B2 條數變動**（依 `alerts/engine.py:271-322` `_limit_outcome` 讀碼，HEAD f25c90d；風控讀碼經 tech-architect 確認並增補；來源：tech-architect 補段第三段，2026-10-07；原「6-a 對條數的影響待查證」於此結案）
   - **6-b**：any 規則「已超標且帳本不完整」由 mixed quiet 改為 fired，**未評估條數少 1**（S-B2 只動條數、字面不變）。
   - **6-a（own>0）**：
     (a) **第 1、4、5 條只有 passed 變 not_evaluable，violated 集合不變。** 三個檢查函式的 passed 只出現在比率算出後的最末分支（`limits.py:850-855`、`:1005-1011`、`:1160-1165`）。violated 仍由同一個 `_breaches`（`:832-834`）比較同一個算出值決定。D-5 分支（`:1127-1141`）的 status 不變。既有的 not_evaluable 成因（缺 ATR、缺總資產、weight None、Kelly 不可用）不變，W-a1 只在比率已算出時使用。因此 fired 的條目（`engine.py:309`）、`violated_limit_ids`、`violated_count`（`:318-321`）都不變，只有 detail 尾端多出 W-a2（經 `:310` 進推播，屬 R-9／F-2）。
     (b) **any 規則（`:280`）在沒有 violated 時，未評估條數增加，最多 +3**（與 6-b 方向相反）。有三種轉變：
         - 原本全部 passed（`:308` 無聲 quiet）：若第 2 或第 3 條仍 passed，轉為 mixed quiet 並附 S-B2 句（`:295-307`）。
         - 原本 mixed：仍是 mixed，`{n}` 增加。
         - 第 2、3 條都不是 passed（例：未自報淨值或淨值過期使第 3 條 not_evaluable，且第 2 條 not_evaluable）：全部 not_evaluable，**由 quiet 變 skipped**（`:288-294`）。
         S-B2 的 `{n}` 範圍 1–4 仍成立，因為 mixed 必須有 passed ≥ 1。
     (c) **只監看第 1、4、5 條其中一條的規則**：原本 passed（無聲 quiet）變成 skipped，句子是「監看的上限（{name}）缺少輸入，無法判定是否違反。」這是改善，不再把可能偏低的比率當成通過。`_limit_cause`（`:325-347`）的尾句只在 `price_cap_cause` 存在時附加，而 `price_cap_cause` 只在 `fx_rate is None` 時設定（`alerts/snapshot.py:158`）。此時第 4 條比率不會算出，走的是原有的 ATR／收盤價成因而不是 W-a1，所以 6-a 不會新增 FX 尾句的情境。
     (d) **不觸發 S-B2 失效條件 1～8**：
         - 1：不新增 quiet reason 的呈現。
         - 2、7：`LIMIT_NAMES`／`LIMIT_IDS` 不變。
         - 3：`LimitStatus` 不變；分支仍用 `_breaches`，門檻語意不變。
         - 4：沒有把 `check.detail`／disclosure 接進 quiet reason。
         - 5：any 語意不變。
         - 6：fired 訊息句構不變，也不對未觸發的上限下結論。
         - 8：skipped 字面不變。
     (e) **S-B2 列管 2 範圍加入「分子不完整」口徑**：own>0 時輸入其實都在，是因為分子不完整才不計算，「缺少輸入」並不精確。與 ADR-0022 Consequences 5 同類，併案處理。字面不改；日後改動須另案送審，並依 S-B2 失效條件 8 與「未評估」核對一致。
     (f) 觀察（不擋 6-a）：F-4「已評估 {E} 條規則」會把 mixed quiet 算成已評估（S-B2 列管觀察），6-a 會讓這類規則變多。依 S-B2 失效條件 1 重審時一併處理。
     (g) **測試面（required，qa 逐條）**：
         - `tests/alerts_helpers.py` 的 `compliant_context`／`breaching_context` 沒有設定 `book_fully_valued`（預設 `None`，`limits.py:644`）。依 Decision 3 的退路，這會被視為 own>0：S-B2 例 (b)（`test_alerts_engine.py:462-471`）會從 quiet 變成 skipped，`breaching_context` 的 fired detail 也會多出 W-a2。
         - 處理方式：兩個 fixture 補 `book_fully_valued=True`（符合它們「完整帳本」的原意）。S-B2 (a)(b)(c) 與 fired／skipped 迴歸測試的**斷言零修改**；fixture 這項改動列入 PR 說明。
         - 另外新增 own>0 測試：any 規則轉 mixed quiet；any 規則轉 skipped；單條第 1 條轉 skipped 且不帶 FX 尾句；violated 時的 fired 條目與 own=0 對照組相同，且 detail 以 W-a2 結尾。
     - **風控裁定（2026-10-07，風控審查檔第四段，HEAD d66183e）：accept，屬「fixture 原意就是完整帳本的修正」，不算「改測試讓它過」，附條件 RF-1～RF-6。** 理由（風控所述）：(1) 原意有證據：`alerts_helpers.py:136`「single-position weight is over the 15% cap」與 `:147`「comfortably inside every evaluable cap」都未模擬無法估值持倉；S-B2 例 (b) 註解（`test_alerts_engine.py:462-463`）寫明未評估只有第 2、3、5 條，前提即第 1、4 條 passed＝完整帳本。(2) 先例：advice 側手刻 fixture 已明設 True（`test_advice_engine.py:62`、`test_advice_limits.py:74`、`test_advice_selection.py:35`、`test_playbook_price_fields.py:47`、`test_advice_wording.py:81`）。(3) 判準：補一個測試主旨本來就依賴、只是沒寫出的輸入，被測行為不變 → 可；修改斷言或放寬退路 → 不可。(4) 讀碼確認：`compliant_context` 有 atr，第 1、4 條算得出且低於門檻；None 退路下兩條轉 not_evaluable，加第 2、3、5 條五條全 not_evaluable，故由 quiet 變 skipped。
     - **RF-1～RF-6（required，qa 逐條；任一未做到，單項核對改判 VETO）**：
       - **RF-1**：`alerts_helpers.py` diff 只能是兩個 fixture 各加 `book_fully_valued=True` 加一句 docstring「完整帳本、無無法估值持倉」，不改其他欄位；使用這兩個 fixture 的測試（`test_alerts_engine.py` L227、243、255、264、273、289、302、314、467、571、603、661、739、768）斷言零修改。
       - **RF-2**：禁止改預設值讓測試過：`PortfolioContext.book_fully_valued` 預設維持 `None`（`limits.py:644`），6-a 退路維持「None 視為 own>0」。
       - **RF-3**：退路另外釘住：用原 fixture 輸入（不設 `book_fully_valued`）走 alerts 路徑新增對照測試：(i) any 規則 → skipped，既有 skipped 字面，不出現 S-B2 句；(ii) 違反帳本 → fired，`violated_limit_ids`／條目與 True 版相同，detail 以 W-a2 結尾。
       - **RF-4**：同時新增 own>0 對照測試（tech-architect 四例：any 轉 mixed quiet；any 轉 skipped；只監看第 1 條轉 skipped 且不帶 FX 尾句；violated 時 fired 條目與 own=0 相同且 detail 以 W-a2 結尾）；own>0 用 `build_book_context` 實際會設定的欄位構成，與 RF-3 的 None 退路分開，不得互相代替。
       - **RF-5**：全面盤點：qa 列出測試中所有未設 `book_fully_valued` 又會走到 `evaluate_limits`／`build_advice`／`suggest_quantity_range` 的手刻 `PortfolioContext`；風控已找到 tech-architect 未列的 **`test_advice_limits.py:1729` `_fractional_ctx`**（docstring「the entire book」，完整帳本原意）；只走 `build_context` 的（`test_advice_engine.py:88/369/598`、`test_observation_window.py:181-182`、`test_drawdown_current_lookahead.py:109`、`test_adr0021_field_evaluability.py:201`）請 qa 確認不受影響。每處歸類：原意完整帳本 → 補 True 列入 PR；不是 → 屬行為變更，斷言修改逐條對照 6-a 裁定寫明理由；期望值改變卻不在清單上 → BLOCKING。
       - **RF-6**：PR 說明逐項列出 RF-1、RF-5 的 fixture 變更與理由。
       - 否決理由：無。若 RF-1～RF-6 任一未落實，第 2 點於單項核對改判 VETO（違反「絕不放行隱藏風險」：放寬退路或拿掉退路測試覆蓋，等於讓「無法確認帳本完整」被當成完整帳本）。
4. **只監看 gross 規則由 skipped 變 fired**：只監看 gross_exposure 的規則在 6-b 條件下由 skipped 改 fired；W-b1 經 `alerts/engine.py:309-310` 進推播（組成 `{symbol} 觸發風險上限：{names}。{details}`，風控審查檔所述 `:310`）；風控接受，不觸發 S-B2 失效條件 6／8（6-b 裁定 (3)）。
5. **W-a2／W-b1 進推播**：誠實度與無操作指示限制適用（見 Decision 4、5）。W-b1 進推播時 6-b GWT 要求 fired 含 W-b1。
6. **卡片觀感**：violated 並列「未參與計算」於 375 寬是否讀得通，qa-e2e 抽驗。
7. **ADR-0022 的 D-d1／D-d2 與 D-a**：6-a／6-b 落地會使 ADR-0022 的 D-d1／D-d2、D-a 失去所指或被涵蓋（失效條件 1、2），須先有 D-a3 與 6-a 方向子句處置的核可字面。
8. **手刻 context 測試**預設 `book_fully_valued=None` 會走退路（tech-architect 所述）。

### 被此決策約束的事

- 6-a、6-b 皆排在 F-1 之後、ADR-0022 PR 之後；不作 F-1 部署前置。
- 6-a、6-b 的字面（W-a1、W-a2、W-b1、D-a3、6-a 方向子句處置）核可前不得實作。
- CEO 知悉增補（風控 2026-10-07）：(i) 曾核可的 D-d1 含數學錯誤、已更正；(ii) 風控修訂自身 FR-9 (a-附加)「一律 not_evaluable」為非對稱判定（更保守）；(iii) 6-a 修後殘留（2026-10-07 風控更新：改為「(A) 落地且 qa 通過後消除」，見 Consequences 殘留 1）；(iv) 6-b 排在 ADR-0022 之後；(v) 6-c 採 C-1 的代價；(vi) F-1b。2026-10-07 風控增補：(vii) ADR-0022 M-1 整檔計入的高估方向，違規推播可能建立在高估的比率上（見 ADR-0022 Decision 1 補充）；(viii) 降級／擋下原因只在預設收合的卡內可見（見 Consequences 殘留 1，仍列殘留）。
- 列管彙總：own>0 加碼降級（(A) 已採，字面風控核可 2026-10-07，待落地；medium，tech-architect）；「結論已調整」操作摘要標記（medium，creative-lead／art-lead／frontend，新字面送審）；F-1b（medium，dev-lead／devops-sre）；`SECTOR_UNCLASSIFIED_NOTE` 措辭（low，creative-lead，見 ADR-0022）。

---

## 對實作的約束（K 不變式）

依 6-a／6-b 任務單與 tech-architect 評估整理。本 ADR 編號為 KC（共通）、KA（6-a）、KB（6-b），以免與 ADR-0022 的 K-1～K-11 混淆。

**KC（共通，tech-architect「三項共用實作約束」）**

- **KC-1**：分類只在 `book.py` 一次；`limits.py` 只讀欄位、**不 import `app.portfolio`**。
- **KC-2**：「上限可否用於試算」全 repo 單一判斷式涵蓋第 1～5 條；分子不完整時即使 violated 也不進試算；分子完整時逐字不變。
- **KC-3**：分子不完整未達上限一律 not_evaluable、observed None；第 1、2、4、5 條只在 D-d1 或「全部 same」才可宣稱下限，第 3 條恆可。
- **KC-4**：X 為 None 時 sector_gap 優先於 C′。
- **KC-5**：退路：`book_fully_valued is True` 視 0，否則走保守分支。
- **KC-6**：不改 `alerts/engine.py`、不複製已核可字面、與 F-1 不同 PR。

**KA（6-a）**

- **KA-1**：範圍＝`limits.py` 三條檢查函式、`notional_caps`、新常數、測試；**不動** `book.py`（只讀欄位）、`book_limits.py`、`alerts/engine.py`、前端、`_position_rollup`／`quantity` 語意。
- **KA-2**：判斷式全 repo 一處（grep `own_lots`）；不複製已核可字面。
- **KA-3**：own=0 → 三條逐字不變、既有測試零修改。

**KB（6-b）**

- **KB-1**：範圍＝`limits.py` `_check_gross_exposure`、`notional_caps` 閘門、新常數 W-b1、註解／docstring、測試；**不動** `book.py` 邏輯、`book_limits.py`、`alerts/engine.py`、前端。**（2026-10-07 修訂，見 Decision 8-1 第 9 點：6-b 可動 `book.py`（新參數、D-a3 常數；若 ADR-0022 PR 未建 finalizer，也包含 finalizer）、`api/advice.py`（組裝順序）、`book_limits.py` `evaluate_book_limits` 中組 notes 的那一處（`:312`）；`_book_level_check`、`_aggregate`、`alerts/engine.py`、前端仍不動。）**
- **KB-2**：`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` **字面不改**，只改英文註解（`limits.py:328-331`）、`book.py` 模組 docstring 規則 3（L28-31）、欄位註解 L641-643（tech-architect 所述行號）。
- **KB-3**：`/limits` 第 3 條經 `_book_level_check`（`book_limits.py:315-341`）原樣 violated（不改 `book_limits.py`）。**（2026-10-07 修訂，見 Decision 8-1 第 9 點：`_book_level_check` 本身仍不動；`book_limits.py` 僅 `evaluate_book_limits` 中組 notes 的那一處（`:312`）可動，改為評估完成後經 finalizer 組裝。）**
- **KB-4**：不得先於 ADR-0022 PR 落地。

---

## 風控裁定轉錄（風控審查檔第一、二段，2026-10-07）

來源：`work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第一、二段（risk-compliance-officer，coordinator 轉錄）。本節逐字轉錄「裁定」「逐條」「落地 required」與第二段 A／B 的裁定文字（僅調整分行與標點排版；原文一處「範圔」誤字改為「範圍」）；**不收錄核可字面總表的字面欄**（見狀態欄核可日表）。與風控審查檔不一致時以審查檔為準。tech-writer 未重新對 code 驗證其中的 `檔案:行號`。

### 第一段：裁定

**APPROVE 附 1 處最小逐字修正（W-b1）**；字面總表即逐字核可版本。不採：W-a1-S、W-a1-V2、W-a1-F、W-a2-B、W-b1-A、D-a3 長版、D-d1-R／D-d2-R、N2。風控審查檔為各常數註解引用之審查檔。

### 第一段：二、逐條

1. W-a1 採 V1（與 W1 同構、說明為何不回 passed；「可能偏低」在 d1／d2 皆成立）；退路分支共用 V1 接受（正式路徑 `api/advice.py:188`、`alerts/snapshot.py:122`、`book_limits.py:406` 皆經 `build_book_context`；惟 `build_book_level_context`（`book.py:586`）的 `/limits` baseline 會走到退路，其第 1、4、5 條 status／detail 不呈現給使用者（`_aggregate` 只借 name／threshold，`book_limits.py:459-472`）→ R-10／F-1）。required：W-a1 只在比率已算出時使用；缺 ATR、缺總資產、weight None、Kelly 不可用等既有成因維持原 detail。
2. W-a2 採 A；不用「上述」同意（第 5 條尾端為勝率揭露）；D-5 分支不附同意（讀碼確認 `allowed <= 0` → violated、detail `KELLY_NON_POSITIVE_FRACTION_DETAIL`，`limits.py:1127-1141`；ADR-0023 D-5 待查證結案）；三條同時 violated 推播約 200 字接受（去重屬 alerts/engine 另案 low；去重須保留成因、比率範圍、處理方式三件事並送審）；R-9 實測長度。
3. W-b1 採 C 修正「計入無法估值的部位後」→「若計入無法估值的部位」（「…後」為時間語氣可能被讀成已計入；「若」為條件句，字數不變）；下界宣稱含等於；「上述數字」兩種讀法皆真（真值 ≥ A/N ≥ 門檻）；不受 F-1b 影響（壞匯率只讓 A 更小），前提為未估值部位真實市值 ≥ 0。
4. D-a3 同意單一常數、短版；同意資料流耦合附條件：(a) 選句須讀**同一回應中第 3 條實際 CheckResult status**（決策卡讀 `evaluate_limits`，`/limits` 讀 baseline 經 `_book_level_check`），不得在 `book.py` 用淨值、門檻再算；(b) 不採「淨值新鮮＋帳本不完整就用 D-a3」；(c) tech-architect 於 ADR-0023 寫明組裝順序與 D-a3 在優先序位置（只在原選 D-a 處替換，D-P／D-d1／D-d2 不動）——accepted 前提之一。a0 時「第 2 條比率會因此偏高」講未印出的比率，為 D-a 既有語意，不為假。
5. D-d1／D-d2 採刪除版（第二次改動，註解寫兩次核可日）；required：刪除版與 6-a C′ 判定**同一 PR**（ADR-0022 PR 先上帶分句版本，當時第 1、4、5 條仍可能 passed 分句仍成立）；不採 R（為例外負責且與 W-a1／W-a2 重複）。
6. N1 直接核可照稿，**另開 PR** 不併 6-a／6-b；核可前現行 2026-08-09 句不動。
7. ADR-0023 待確認：失效條件 2 改「第 1、4、5 條」（更正原審查檔）；失效條件 3「6-c 擴及」已被 C-1 涵蓋，分類變更段繼續有效並加 M-1／M-3 以外再變更；unknown-only 第 2 條 passed 附 W3 為非對稱通則**明列例外**（維持 passed），但**試算上屬分子不完整，依 KC-2 不得進 `notional_caps`**（required，與 C-1 一致，請 tech-architect 確認 ADR-0022 已規定否則補）；6-a 對 S-B2 條數（請 tech-architect 確認）：own>0 時第 1、4、5 條只有 passed 變 not_evaluable、violated 集合不變，any 規則未評估條數**增加**（最多 3 條，與 6-b 相反），只監看其一的規則由無聲 quiet 變 skipped（改善），不觸發 S-B2 失效條件 1～8，S-B2 列管 2 範圍加「分子不完整」口徑。
   - 落檔狀態（tech-writer，2026-10-07）：失效條件 2、3 已於「重審與失效條件」與 ADR-0022 失效條件修訂；unknown-only 見 Decision 1 最後一點；S-B2 條數見 Consequences 3；D-5 見 Decision 1。

### 第一段：三、落地 required（qa 逐條）

- **R-1**：每個新／改常數註解「風控核可文案,修改須重新送審(2026-10-07)」＋本審查檔路徑，D-d1／D-d2 加註第二次核可。
- **R-2**：名稱由 `LIMIT_NAMES` 組字串，測試斷言渲染結果等於本表、只引用常數；新常數納入三份禁詞掃描。
- **R-3**：W-a1 只在比率已算出時；參數化涵蓋 own>0 且 ATR None → 第 4 條維持 ATR detail、own>0 且 Kelly 不可用 → 維持 (g) 表 detail。
- **R-4**：W-a2 直接接完整既有句之後（第 5 條在 disclosures 後）；斷言不含「上述」；D-5 不附、observed None、status／detail 逐字不變。
- **R-5**：D-a3 負向測試兩範圍 × live／cache_only × 兩則 note 並存：D-a 絕不與第 3 條 violated 同現；D-a3 絕不與第 3 條非 violated 同現；D-a 與 2026-09-18 鎖定整句逐位元組相同。（2026-10-07 第四段增補 R-IN-2：加一格 insufficient 分支，見 Decision 8-1。）
- **R-6**：D-d 刪除版與 6-a 同 PR。
- **R-7**：W-b1 在 advice 與 `/limits` 位置相同；未達上限分支逐字不變、既有測試零修改。
- **R-8**：own>0 時第 2 條 unknown-only 與第 1、4、5 條皆不進 `notional_caps`，判斷式全 repo 一處。
- **R-9**：qa 實測最長推播（第 1、4、5 條 W-a2＋Kelly 長揭露＋W-b1＋淨值三句與老化提示＋fx_disclosure）對照 Discord 2000／Telegram 4096 字元，會拒或截斷須上線前回報（推播遺失屬安全問題）。
- **R-10**：`test_book_context_call_sites` 明列 `build_book_level_context` 為唯一走得到退路的正式路徑並釘住其第 1、4、5 條 baseline status／detail 永不呈現，或由 ADR-0022 PR 讓該 context 也填 `unvalued`（二擇一）。
- **R-11**：qa-e2e 375／1280 抽驗：own>0 卡片（三條 W-a1、或 W-a2 與「未參與計算」並列）、第 3 條 violated 附 W-b1 與 D-a3、兩則 note 皆帶 D-a3 觀感。

### 第二段：A. own>0 加碼降級

1. 採 (A) 同意；否決 B／B′／C／D。
2. 標題「續抱參考」可接受附條件：`downgrade_notices`／`blocked_notices` 只在 `AdviceCardView` 內而整張建議卡預設收合（`page.tsx:550`，CEO 2026-09-19 裁定），主視圖只見「續抱參考」不見原因——既有缺口不擋本項，**新列管 medium**（creative-lead／art-lead／frontend：操作摘要加一行「結論已調整」可見標記，新字面送審）；列 CEO 知悉 (viii)；美股匯率失敗時 own>0 常見會放大缺口。required（qa-e2e）：降級卡在操作摘要不顯示信心、依據、數量區間；展開後可讀降級句。
3. 新降級句約束：同意 tech-architect 全部，另加：成因用語與 W-a1／W-a2 一致「本標的有持倉無法估值」；後果句不得預設部位在範圍內（不得「仍在範圍內」類帶「仍」前提，只講「無法用風險上限確認加碼」）；不承諾恢復、不寫補資料指示；結尾**沿用**「加碼建議改為觀望」；建議 ≤ 60 字；creative-lead 起草送逐字審。
4. 已擋下／已降級／已 insufficient_data 不重複附加：同意。
5. 與 6-a 同包、字面落後時 6-a 先發：同意，條件 (A) 排 6-a 之後最近一個 release 不得無限期延後。
6. CEO 知悉 (iii) 改為「(A) 落地且 qa 通過後消除」；新殘留列 (viii)。

（第二段 A 的字面後續已於第三段核可，見 Consequences 殘留 1。）

### 第二段：B. `/limits` mixed 群組

1. **M-1 確認，不需新揭露**（誤差只往高估；mixed 由使用者造成可修正且附 `SECTOR_MIXED_DETAIL` 與指引）。required：產品任何地方不得加總、平均各產業比率或分子（qa grep＋測試釘住）；ADR-0022 Decision 1 補充段明寫「印出的產業佔比可能因 mixed 整檔計入而高估」。列 CEO 知悉 (vii)：違規推播可能建立在高估比率上。
2. **M-2a 殘留接受，列管 low**；日後補「不計算不代表沒有產業集中風險」類句（比照 D8）另案送審；本 PR 不要求新字面。
3. **M-4「mixed 未估值群組且無任何產業在比較中」：採 (i) W-6m 新字面同 PR，不准 (ii)**（現行 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`「可能屬於已納入比較的產業」在此子情境為假；comparable 為空更無所指）。W-6m 約束：比照 W6 句構；列出其所有產業（固定排序、不用「等」、不截斷）；寫明這些產業本次沒有任何持倉納入比較；必含「未納入比較不代表這些產業未超過上限」；不寫「屬於」單一產業、不帶指引。**字面未核可時 ADR-0022 PR 不得合併。**（已由第三段核可修正版；合併前提見 ADR-0022 Decision 1 補充 M-4。）
4. **6-c-1＋M-1 觸發 W1～W7 失效條件 4：裁「已涵蓋，不需重審」**（W1／W2 `{count}` 依 M-3 保守歸屬仍真；W3 mixed 永非 unknown；W6 只用於 Y 有確定值；W7 `{count}` 不含 mixed；D-P／D-a 用語「可能」「因此偏高」不因 M-1 額外高估變假）；條件 4 對 M-1／M-3 以外再變更仍有效（F-7）。

B 的落檔處：ADR-0022 Decision 1 補充（M-1～M-5）、W-6m 字面表與 RM-1～RM-5。若 CEO 對以上裁定有異議，保留風控審查檔的書面紀錄，由 CEO 負最終責任。

---

## 驗收（GWT，轉錄摘要）

**6-a**

1. 2330 一筆已估值一筆未估值（另參數化全部未估值；live／cache_only），算出值低於門檻 → `GET /api/advice/2330` 與警示 snapshot：第 1、4、5 條 not_evaluable、observed None、threshold 照舊、detail W-a1；`notional_caps` 不含三條；basis skipped 句列三條或區間 None。
2. 同上但第 1 條 ≥ 50% → violated、detail 原句＋W-a2、add→hold 出現「加碼建議被第 1 條上限（單一標的佔比上限）擋下。」、fired 含 W-a2、reduce 時不出現「仍然超標」。
3. own=0 → 三條逐字不變、既有測試零修改、`test_book_context_call_sites` 證明退路走不到。

**6-b**

1. 淨值新鮮、帳本 1 筆未估值（live／cache_only）、A/N ≥ 150% → advice 第 3 條 violated、detail 既有前句＋W-b1＋三句揭露、add→hold、fired 含 W-b1、`/limits` 第 3 條 violated、`notional_caps` 不含 `gross_exposure`。
2. A/N < 150% → 維持 not_evaluable 既有 detail 逐字不變、既有測試零修改。
3. 帳本全估值 → passed／violated 與 `notional_caps` 逐字不變；S-B2 (a)(b)(c) 零修改；新增「只監看 gross_exposure 的規則在條件 1 下 fired」測試。

---

## 重審與失效條件

- ADR-0022 失效條件 1（6-b 修法讓第 3 條在有無法估值部位時算出比率）：本 ADR 的 6-b 即屬此條；須有 D-a3 核可字面。
- ADR-0022 失效條件 2（6-a 改變第 1、**4**、5 條對本標的批次處理）：本 ADR 的 6-a 即屬此條；須有 6-a 方向子句處置核可字面。**（2026-10-07 修訂：原寫「第 1、5 條」，風控審查檔第一段二.7 更正為「第 1、4、5 條」；ADR-0022 同條已同步更正。）**
- ADR-0022 失效條件 3（6-c 擴及 AC-12.5，或 same／unknown／other 分類變更）：**「6-c 擴及」已被 C-1 涵蓋**；分類變更段繼續有效，並加「M-1／M-3 以外的再變更」（風控審查檔第一段二.7；M-1／M-3 見 ADR-0022 Decision 1 補充）。
- ADR-0022 失效條件 5（允許零或負市值、或總資產可能小於產業市值）：與 F-1b 直接相關；數學通則的「市值非負」前提不成立時須重審本 ADR。
- 6-a 的「D 方案」（第 4 條改用全部股數）暫不採；日後採用須另案評估。
- 任何修改 FR-9 (a-附加) 的風控裁定，須回頭核對 Decision 7。

**失效條件增補 F-1～F-10（風控審查檔失效條件編號，逐字轉錄；F-11、F-12 屬 ADR-0022，指標列於本節末）**

說明：本節 F-n 是風控審查檔的失效條件編號，與 F-1 任務單（組合估值防護）、Consequences 3 (f) 與 ADR-0022 失效條件 7 提到的 F-4（「已評估 {E} 條規則」「查看略過原因」）屬不同編號，勿混淆。R-1～R-11 見「風控裁定轉錄」節。

- **F-1～F-7**（風控審查檔第一段「四、失效條件增補」，2026-10-07）：
  - **F-1**：任何呈現給使用者的正式路徑走到退路 → 改 W-a1-F 重審或修正路徑。
  - **F-2**：推播組成改變（連接方式、順序、去重）→ 重審 W-a2、W-b1。
  - **F-3**：第 3 條 violated 前句改變 → 重審 W-b1「上述數字」。
  - **F-4**：D-a3 不再讀實際第 3 條判定，或第 3 條在帳本不完整時出現 passed → 重審。
  - **F-5**：own>0 時第 1、4、5 條重新可能 passed → 被刪分句重審是否恢復；D-5 語意或第 5 條 violated 揭露順序改變 → 重審 W-a2 位置。
  - **F-6**：未估值部位可能負真實市值 → W-b1 失效。
  - **F-7**：M-1 整檔計入或 M-3 分類改變 → 重審 B(1)／B(4)。
  - 既有 LIMIT_NAMES／LIMIT_IDS 變動、ADR-0022 失效 1／2／5 維持。
- **F-8**（風控審查檔第三段「四、失效條件增補」，2026-10-07；屬 ADR-0022，已收於其「重審與失效條件」第 8 項）：`categories(G)` 改為包含非使用者填寫值（如系統推斷）、None 被算成一個類別、產業別改自由文字、或 `TWSE_SECTORS` 名稱或順序變動 → 重審 W-6m「所填產業別為」與排序。
- **F-9**（風控審查檔第三段「四、失效條件增補」，2026-10-07）：6-a 的 own>0 判斷式或 engine 降級、擋下順序改變 → 重審 A-降級句顯示條件。
- **F-10**（風控審查檔第四段，2026-10-07；併入 S-2 同類條件，觸發一項即重審 D-a 在本分支的使用）：(a) 前端、推播、匯出或任何畫面開始在 insufficient 狀態顯示 `context_notes`；(b) insufficient 分支開始評估上限或回傳任何第 3 條比率或判定（此時必須改傳實際 status，不得再用 `None`）；(c) `None` 被用在 insufficient 分支以外。
- **F-11、F-12**（2026-10-07，風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u」段「失效條件增補」；**屬 ADR-0022，已逐字收於其「重審與失效條件」第 9、10 項，本 ADR 只列指標、不重抄**）：
  - **F-11**：重審 `/limits` 優先序第 1 點（Y 未定義 → D-a／D-a3，見 Decision 8-1 第 6 點）與 D-P 的 `/limits` target；觸發條件見 ADR-0022 失效條件 9。
  - **F-12**：重審 W-6u 的顯示條件與 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 的適用範圍；觸發條件見 ADR-0022 失效條件 10。

## 交接

- 字面：creative-lead 起草 W-a1、W-a2、6-a 方向子句處置、W-b1、D-a3 → risk-compliance-officer 逐字審；全部核可且 CEO 未推翻後，本 ADR 才可改 accepted。（2026-10-07：字面已由風控逐字核可，見狀態欄更新與風控審查檔；CEO 未推翻仍待表態。）
- 實作：dev-lead（F-1 之後、ADR-0022 PR 之後）→ qa-reviewer → 風控單項核對；qa-e2e 375／1280。
- 另案：own>0 加碼降級（tech-architect）；F-1b（dev-lead／devops-sre；F-3 腳本掃匯率 ≤ 0）。
- 原「待查證」四項（D-5 分支判定內容；D-a3 在方向子句優先序的位置；6-a 對 S-B2 條數的影響；第 2 條只有 unknown 的 passed 是否屬本通則範圍）已於 2026-10-07 全數結案，見下「待確認／開放事項」。

## 待確認／開放事項

2026-10-07 補段落檔時整理（原散見於 Decision 1、Decision 8、Consequences 3 與「交接」的「待查證」）。

**已結案（2026-10-07）**

| 項目 | 結案內容 | 來源 |
|---|---|---|
| D-5 分支判定內容 | `allowed <= 0` → violated，detail 為 `KELLY_NON_POSITIVE_FRACTION_DETAIL`（`limits.py:1127-1141`）；W-a2 不附 | 風控審查檔第一段二.2（風控讀碼；tech-writer 未驗證） |
| D-a3 在方向子句優先序的位置 | 只在原選 D-a 處替換；D-P／D-d1／D-d2 不動 | Decision 8-1 第 6 點（tech-architect 2026-10-07） |
| 6-a 對 S-B2 條數的影響 | any 規則未評估條數增加（最多 +3）；只監看其一者由 quiet 變 skipped；不觸發 S-B2 失效條件 1～8 | Consequences 3（tech-architect 2026-10-07，風控讀碼經確認並增補） |
| 第 2 條只有 unknown 的 passed 是否屬本通則範圍 | 是本通則明列例外：判定維持 passed，試算上屬分子不完整、依 KC-2 不得進 `notional_caps` | Decision 1 最後一點；ADR-0022 Decision 4 第一句（tech-architect 2026-10-07） |
| (A) 降級句字面待審 | 已採，降級句字面風控核可 | 風控審查檔第三段（2026-10-07）；Consequences 殘留 1 |
| 待風控確認 (1)：insufficient_data 分支維持 D-a（`gross_exposure_status=None`） | **accept**；required R-IN-1、R-IN-2；新失效條件 F-10 | 風控審查檔第四段（2026-10-07，HEAD d66183e）；Decision 8-1 第 3 點、KD-2、KD-5、重審與失效條件 |
| 待風控確認 (2)：6-a 退路使手刻 fixture 行為改變，alerts fixture 補 `book_fully_valued=True` | **accept**（屬「fixture 原意就是完整帳本的修正」）；附 RF-1～RF-6，任一未落實改判 VETO；RF-5 增列 `test_advice_limits.py:1729` `_fractional_ctx` | 風控審查檔第四段（2026-10-07）；Consequences 3 (g) |
| 風控審查檔第一、二段轉錄不全（核可日、失效條件 2／3 更正、F-1～F-7、R-1～R-11、(vii)／(viii)、逐條意見） | 已補：狀態欄核可日表與剩餘前提、Decision 4／5／8 標注、「風控裁定轉錄」節、「重審與失效條件」F-1～F-10；ADR-0022 失效條件 2、3 同步更正 | coordinator 2026-10-07 指示（任務單原述「已先前落檔」不成立，tech-writer 核對時發現） |

**仍待處理**

- 前提 4（CEO 未推翻風控與 2026-10-07 各裁定，並知悉 (vii) M-1 高估方向、(viii) 降級／擋下原因只在預設收合的卡內可見）：待 CEO 表態。
- 已核可字面（W-a1／W-a2／W-b1／D-a3／D-d1、D-d2 刪除版／N1）的逐字內容不收於本 ADR（降級句除外），以風控審查檔第一段為準。

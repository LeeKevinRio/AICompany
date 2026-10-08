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
  - 補段來源（2026-10-07，第三次落檔）：風控對 ADR-0022 PR 衝突 1 的裁定，來源為風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`（注意：與下列「風控審查檔」`上限分子不完整-非對稱判定` 為不同檔）檔尾「`/limits` 方向子句優先序更正與 W-6u（2026-10-07）」段。影響本 ADR 三處：Decision 8-1 第 6 點 `/limits` 列順序（Y 未定義改為第 1 點）、KD-5 `/limits`「Y 未定義」一格拆為「無 unknown」「有 unknown」兩格（R-6，6-b 範圍）、失效條件 F-11／F-12 指標（屬 ADR-0022）。**依風控裁定直接落檔，tech-architect 未另出補段**（coordinator 定案，CEO 可推翻）。本 ADR 狀態維持 proposed。ADR-0022 PR 的新增合併前提（W-6u 核可並落地）〔2026-10-07 更新：W-6u 已核可（替代案 B），合併前提改為 RU-1～RU-8 落地且 qa-reviewer 無 BLOCKING_ISSUES，見 ADR-0022〕見 ADR-0022 Decision 1 補充。
  - 補段來源（2026-10-07，第二次落檔）：
    - tech-architect 補段：`work/reviews/2026-10-07-tech-architect-D-a3資料流-M段最終版-ADR-0022-0023補段.md`（讀碼基準 `product/stock-desk` HEAD `f25c90d`；coordinator 原文轉錄）——第一段→Decision 8-1；第二段→Decision 1 最後一點；第三段→Consequences 3。
    - 風控審查檔：第一段（核可字面總表、逐條意見、R-1～R-11、F-1～F-7、剩餘前提）、第二段（A. own>0 加碼降級；B. `/limits` mixed 群組）、第三段（A-降級句核可、RA-1～RA-7、F-9、ADR 狀態）、第四段（D-a3 資料流兩點補裁：R-IN-1／R-IN-2、F-10、RF-1～RF-6；2026-10-07，HEAD d66183e，coordinator 轉錄）。
    - 補段檔尾「建議送風控確認的兩點」已由風控於風控審查檔第四段裁定（皆 accept 附條件），見 Decision 8-1 第 3 點、Consequences 3 (g) 與文末「待確認／開放事項」。
    - 勘誤與「落地」節來源（2026-10-07，第四次落檔，tech-writer）：6-a 任務單檔尾「tech-architect 實作規格」段（讀碼基準工作樹 66a88b3 之後；coordinator 原文轉錄）的前置 P-6、「決策」與「既有測試修改清單」。本次快照：分支 `product/stock-desk`，HEAD `4f19c2d`（coordinator 任務所述；tech-writer 僅讀 `.git/HEAD` 確認分支）。勘誤以「〔2026-10-07 勘誤，tech-architect〕」註記附加於原文處，**原文不刪**；新增「落地」節。狀態維持 proposed。
  - 第五段來源（2026-10-07，第五次落檔，tech-writer）：風控審查檔 `work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第五段（P-3／P-4／P-5／M3 裁定，risk-compliance-officer 唯讀，coordinator 轉錄），含其「是否需要 tech-writer 改 ADR 字句」四點。落檔位置：Decision 4（R-P3-1，PR-1 合併前）、Decision 8-1 第 3、5 點與 KD-2、F-10(c)（PR-3 合併前）、R-11 勘誤、Consequences 3 (g) RF-4（R-RF4）、「被此決策約束的事」CEO 知悉 (ix)(x)(xi)、「落地」節 P 表與 M3。風控所述 `檔案:行號` tech-writer 未驗證。另（2026-10-07，第六次落檔）：KD-2 補強規格來源為 6-b 任務單檔尾「KD-2 補強規格」段（tech-architect，HEAD 4f19c2d 工作樹唯讀；coordinator 原文轉錄），落於 KD-2 與 F-10(c)。
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
  - 〔2026-10-07 勘誤，tech-architect〕上句「改為」不正確，應為「**加上**」：第 3 條閘門**加上**「分子完整（`book_fully_valued is True`，經 `numerator_complete(ctx, "gross_exposure")`）」此條件，**保留**原本的 `!= "not_evaluable"` 判斷；若只改為 `book_fully_valued is True`，淨值過期（第 3 條 not_evaluable）時也會被拿去試算。行號對照：舊 `limits.py:1231-1236` → 現 L1435-1440（讀碼基準 66a88b3 之後）。原文保留不刪。（來源：6-a 任務單檔尾「tech-architect 實作規格」本次結論 3(v)、前置 P-6、6A-03；B 類轉錄。）
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
- **observed 規則（R-P3-1，風控 P-3 裁定，2026-10-07，風控審查檔第五段；PR-1 合併前補入，qa 逐條核）**：
  - own>0 且 not_evaluable → None；
  - own>0 且 D-5 → None，status、detail、threshold（allowed）逐字不變；
  - own>0 且一般 violated → 算出值；
  - own=0 → 不變。
  - **風控 P-3 更正（2026-10-07，第五段）**：審查檔第一段 W-a2 列的「observed None」只指 D-5 分支；源自草稿錯誤引述裁定 (3)、風控核可時未發現（風控自述為審查疏失）。審查檔第一段 W-a2 列已加更正註記。
  - 配套 required（風控第五段）：R-P3-2 測試斷言兩件事——一般 own>0 violated 時第 1、4、5 條 `observed` 等於算出值且 `format_percent(observed)` 字串出現在 detail 中；D-5 在 own>0 時 `observed is None`、`threshold == allowed`。R-P3-3 qa-e2e 375／1280 抽驗：W-a2 卡上的「觀察值」與 detail 印的比率相同；D-5 加 own>0 的卡上觀察值顯示「—」、上限照舊顯示。
  - 草稿 `work/copy/上限分子不完整-非對稱判定-揭露字面草稿-2026-10-07.md` L85「observed 在 own>0 時一律 None（風控裁定 (3)）」為錯誤引述，**已更正，見審查檔第五段 P-3，不得作為期望值**。
  - 本 ADR 位階高於審查檔，上列四行為準（風控第五段「是否需要 tech-writer 改 ADR 字句」第 1 點）。
- 三條**一律不進 `notional_caps`**（即使 violated）。
- W-a1／W-a2**不帶筆數**（卡片已有 `SYMBOL_UNVALUED_NOTE`；退路分支可共用同句）。
- W-a2 進推播（風控 required）：推播無 `SYMBOL_UNVALUED_NOTE`，W-a2 須自述「本標的有持倉無法估值、比率只用已估值部分、以已達上限處理」；同句用於 d1 與 d2，故**不得宣稱下限或「實際只會更高」**，無賣出指示或催促。
- 既有 skipped 句（「缺少可用資料」）延用到「分子不完整而排除」，**字面不改**（風控 6-a 裁定 (4)）；卡片可能並列「第 1 條 violated」與「未參與計算」，qa-e2e 375 抽驗。〔2026-10-07 風控 P-5 更正（審查檔第五段）：**own>0 下此並列不可能出現**——`notional_caps` 必為空、`suggest_quantity_range` 回傳 None、skipped 句不會產生（前提：第 3 條閘門為「加上」，見 Decision 2 勘誤）；並列情境移到 6-b（own=0、帳本不完整、第 3 條 violated，見 R-11 勘誤的 R-P5-2）。原文保留不刪。〕
- **required（6-a 同一包）**：own>0 時方向子句處置（ADR-0022 的 D-d1／D-d2 因第 1、4、5 條不再有 passed 而失去所指）由 creative-lead 提出，送風控逐字審。suggested：qa 確認警示 bare context 在 own>0 時不會走 `_inferred_sector_gap` 推成 no_position（`limits.py:871-873`）。
- **〔2026-10-08 加註（tech-architect 可達性評估）；B 類轉錄，上列原文保留不刪〕W-a2（含第 4 條）在正式路徑可達。**
  - 來源與版本：tech-architect 評估 `work/reviews/2026-10-08-tech-architect-第4條W-a2可達性與F-6修法評估.md`（問題 1，2026-10-08，唯讀、未跑測試、未跑 git；coordinator 轉錄；dev-lead 正在改工作樹，行號可能漂移）；風控裁定 `work/reviews/2026-10-08-風控小項裁定-X-5用語-數量區間文案-R0-7捲動-R-P3-3結案.md` 第 4 項（2026-10-08）。tech-writer 未重新對 code 驗證，其中 `檔案:行號`、函式名、測試名皆為 tech-architect／風控所述。
  - **可達成因**：同一標的有一批 US／USD 持倉的建倉日期空白（`opened_at` 為 None）→ 該批 `fx_open` 缺、估值記為 `insufficient_data`（`missing` 為 `["fx_open"]`）；同標的另一批若有建倉日期且查得到匯率則為 ok。此時 book 層幣別單一、匯率可解析、close 與 ATR 保留、own=1，第 4 條比率算得出來，達上限即 violated 加 W-a2；同一路徑亦可使第 1、5 條出現 W-a2 與 D-5 own>0 分支。tech-architect 所述讀碼依據：`positions/models.py` `opened_at` 可為 None（約 L138-141）、`PositionWriteInput` 不擋（約 L208-226）、`portfolio/valuation.py` 約 L335-350、L438-446。另依 tech-architect 成因表，`fx_open` 缺亦包含「建倉日前 7 天內查不到匯率」。
  - **成因表摘要（tech-architect 對「本標的有批次未估值」各成因能否到 W-a2 的判定）**：`fx_open` 缺 → **可達**；價格缺 → 同 (symbol, market) 批次共用同一次取價、一起失敗，已估值股數為 0，只到 W-a1；close 非正值（F-1）、`fx_now` 缺、幣別混雜、legacy A／B 型、X-3c 不符列 → 皆不可達（close 與 ATR 一併撤下，或整卡 insufficient_data，或不產生 own>0）。另有一項理論可達的退化情形（`max_loss_per_trade` 門檻 ≤ 1e-9），屬既有邊界問題、列管 low、非本案。
  - **更正第二十六輪與測試註解**：第二十六輪 e2e 結論 2「W-a2、D-5 加 own>0 在正式 API 路徑不可達」，以及 `apps/stock-desk/backend/tests/test_adr0023_own_unvalued.py:814-815` 註解（「test client 建不出同標的一批已估值、一批未估值」）所稱「正式 API 建不出」**不精確**。風控已要求更正為「**本輪斷網沙箱不可達**」（風控 2026-10-08 裁定第 4 項）；讀碼推定正式 API 可達，已由 tech-architect 確認。tech-architect 建議註解改為「TW 建不出；US 的 opened_at 留空可以建出」，由 qa-automation 修改。
  - **驗收前提**：(1) USDTWD 要解得出來——tech-architect 所述 FX 目前沒有快取層（`services/fx.py` 約 L313、L325），直寫 DB 補不了匯率，故 e2e 需對外網路，或 devops-sre 核可的 FX stub（不得以放寬唯讀邊界處理）；(2) 兩批持倉須經正式 POST 或 UI 建立；(3) advice 用 cache_only 估值，AAPL 類標的日線須先在 bar cache 內（tech-architect 所述）。
  - **現況缺口**：目前**尚無**經正式路徑的第 4 條 W-a2 測試（既有單元測試用手組 context；既有 API 測試以 monkeypatch 換掉 `build_summary`，且該帳本的第 4 條斷言為 W-a1）。由 qa-automation 補 API 層測試（fixture 見 tech-architect 評估檔「交給 qa-automation 的最小 fixture」，本 ADR 不重抄）。coordinator 定案（CEO 可推翻）：先以 API 層正式路徑測試結案，e2e 實機補驗列為待辦，前提是 devops-sre 提供核可的 FX stub。風控將第 4 條 W-a2 未取證列管 low，不擋 PR-0、PR-1。
  - **失效條件**：若日後改成「沒有建倉日就以 `fx_now` 代替 `fx_open`」，此路徑消失，須重新評估本加註與 W-a2（第 4 條）的驗收做法。
  - **提醒**：此路徑**可達**，不得改寫為「不可達、保留為防禦」。

### 5. 6-b 適用：第 3 條（`book_fully_valued is not True`）

- A/N ≥ 上限 → **violated**，`observed`＝A/N，detail＝既有 violated 前句（`limits.py:969-970` 句構）＋ **W-b1** ＋ `_net_worth_disclosure`（原三句揭露 required 不變）；**未達上限 → 維持 `limits.py:957-963` 逐字不變**（`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` 字面不改）。〔2026-10-07 勘誤，tech-architect：舊 `limits.py:957-963` → 現 L1150-1156（讀碼基準 66a88b3 之後）。〕
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
- `/limits`：`book_limits.py:291` 呼叫 `build_book_level_context`（notes 於 `book.py:578` 組好）→ `:292` baseline → `:308` `_book_level_check`（`:315-341`，只在空帳本時覆寫 status，`:325-337`）→ `:312` `BookLimits(notes=book.notes)`〔2026-10-07 勘誤，tech-architect：舊 `book_limits.py:312` → 現 L400（讀碼基準 66a88b3 之後）〕。
- 警示：`alerts/snapshot.py:122-158` 只讀 `book.context`、`book.fx_note`、`book.fx_rate`，不讀 notes；`book_limits._symbol_context`（`:396-416`）只取 `.context`。兩者都不受 D-a3 影響。推播不含 D-a3，第 3 條方向由 W-b1 經 detail 進推播。
- D 槽位出現的條件（`book.py:539` `valued_count < total_count`）與 `book_fully_valued is not True`（`_fully_valued`，`book.py:279-285`；寫入 context 於 `:593`、`:704`）出自同一份 summary，兩者等價。
- 現行方向子句中，只有 D-a 涵蓋第 3 條：D-P 只講第 1、4、5 條與第 2 條；D-d1／D-d2 刪除版只講第 1、4、5 條。因此 D-a3 只需在 D-a 的位置替換。

**決策**
1. **選句只在一處**：`_book_level_notes` 新增 keyword-only 參數 `gross_exposure_status: LimitStatus | None`，不給預設值。D-a3 只在此函式內選用，條件為「依 ADR-0022 優先序原本會選 D-a，且 `gross_exposure_status == "violated"`」。每次呼叫只選一次，live 與 cache_only 兩則 note 共用同一個方向子句（「{成因}；{D-a3}」各自接）。
2. **status 來源（同一回應中實際的第 3 條 CheckResult）**：
   - 決策卡：`card["limits_check"]` 中 `id == "gross_exposure"` 那筆的 `status`，也就是 `advice/engine.py:354` `evaluate_limits` 的結果、回應實際送出的那一筆。
   - `/limits`：`limits` 中 `limit_id == "gross_exposure"` 那筆 `BookLimitCheck` 的 `status`，也就是 `book_limits.py:308` `_book_level_check(index, baseline["gross_exposure"], ...)` 的輸出。不得直接讀 baseline，也不得讀 per-symbol context。
   - 查找不給預設值：已評估的回應中找不到第 3 條屬程式錯誤，直接拋出例外，不得默默退回 D-a。
3. **`None` 的語意**＝「本回應不含第 3 條判定」。只允許用在 `api/advice.py` 的 insufficient_data 分支（`:202-222`：不建卡、不評估上限）〔2026-10-07 風控 P-4 白名單更正（審查檔第五段；PR-3 合併前補入）：「只允許用在」改為「**只准用在 insufficient 分支與 `BookContext.notes` 相容屬性（只供測試，production 禁讀；風控 P-4 白名單）**」，白名單恰兩處，見 R-P4-1〕。此時維持 D-a；該回應沒有任何第 3 條數字，R-5「D-a 絕不與第 3 條 violated 同現」仍成立。
   - **風控裁定（2026-10-07，風控審查檔第四段，HEAD d66183e）：accept。** 理由（風控所述）：(1) `api/advice.py:202-222` 不建卡、不評估上限；回應雖帶 `context_notes=book.notes`（L219），前端 `page.tsx:543-548` 只渲染 InsufficientPanel，全前端唯一渲染 context_notes 處為 ok 分支 `page.tsx:575-586`，後端無其他讀者（grep `context_notes` 只有 `api/advice.py`）；與 S-B1、S-2「只在 API、頁面不渲染」先例一致。(2) R-5 原規則「D-a 原句只在第 3 條不是 violated 時使用」；insufficient 是「第 3 條沒有判定」的子情形，未擴大語意，「D-a 絕不與第 3 條 violated 同現」仍成立。(3) 同回應 `portfolio_context` 有 `gross_exposure_twd`、`net_worth` 等輸入，但無第 3 條比率或判定，畫面不顯示。
   - **R-IN-1（required）**：insufficient 分支呼叫 finalizer 時明寫 `gross_exposure_status=None`（KD-2）；`None` 只准用在此分支，qa grep 確認。〔2026-10-07 風控 P-4 更正：改為「`None` 只准用在 insufficient 分支與 `BookContext.notes` 相容屬性（只供測試，production 禁讀；風控 P-4 白名單）」；qa grep 結果須正好兩處（R-P4-1）。〕
   - **R-IN-2（required）**：KD-5 的 R-5 負向測試加一格「insufficient 分支」，斷言 D-a 逐位元組相同、不含 D-a3、回應無 `advice`／`limits_check`。
   - **失效條件 F-10**：見本 ADR「重審與失效條件」。
4. **組裝順序（兩個範圍相同）**：①建 context（`build_book_context`／`build_book_level_context`）→ ②評估上限（決策卡：`build_advice` 內的 `evaluate_limits`；`/limits`：baseline、`_aggregate`、`_book_level_check` 全部完成）→ ③以②的實際 status 組 notes → ④組 response。決策卡維持 `[*_book_freshness_notes(summary), *notes]` 的順序（風控 A-6）。
5. **實作形狀**：
   - `BookContext` 保留組 notes 所需的輸入。book.py 新增公開純函式（暫名 `book_notes(book, *, gross_exposure_status)`），回傳 `[*_book_level_notes(...), *個股層 notes]`，順序與現行 `book.notes` 相同。〔2026-10-07 風控 P-4 補（R-P4-2，審查檔第五段）：`book_notes` 的 `gross_exposure_status` 為 **keyword-only、不給預設值**（與第 1 點對 `_book_level_notes` 的要求相同），否則 None 會在呼叫端隱形，R-IN-1 的 grep 失效。〕
   - `BookContext.notes` 保留作相容用，定義為 `book_notes(book, gross_exposure_status=None)` 的結果，既有測試因此零修改。但 production code（`app/`）不得再讀 `BookContext.notes`，insufficient_data 分支也改為明寫 `gross_exposure_status=None`。
   - 〔2026-10-07 風控 P-4 裁定（審查檔第五段）：**准列白名單，附條件**〕此相容屬性傳 `gross_exposure_status=None` 與 R-IN-1／F-10(c) 原字面衝突，風控裁定相容屬性不會進到 production（app/ 內真正組回應的只有 `api/advice.py:219`、`:232` 的 `book_notes`，並有 KD-2 靜態與執行期兩道測試擋著），故 R-IN-1 白名單為「insufficient 分支」與「`BookContext.notes` 相容屬性本體」兩處。條件：
     - **R-P4-1**：白名單**只有兩處**，qa grep 結果必須正好兩處，多出一處即觸發 F-10(c)。
     - **R-P4-2**：見上，`book_notes` 的 `gross_exposure_status` keyword-only、不給預設值。
     - **R-P4-3**：相容屬性的 docstring 寫明三件事：只供測試相容；一律以「本回應不含第 3 條判定」組句（可能是 D-a）；production 禁讀（ADR-0023 KD-2、風控 P-4 白名單）。
     - **R-P4-4**、**R-P4-5**：見 KD-2。
   - `/limits` 的 D-P 判定需要「回報產業 Y」，Y 要到 `_aggregate` 之後才知道，所以 ADR-0022 PR 本來就必須在評估後才組 `/limits` notes。架構要求 ADR-0022 PR 就建立上述 finalizer，並讓兩個範圍都經過它。6-b 只加 `gross_exposure_status` 參數與 D-a3 常數，並調整 `api/advice.py` 的組裝順序。
6. **優先序（只在原選 D-a 處替換；D-P／D-d1／D-d2 不動）**：
   - 決策卡：(1) `own_lots > 0` → D-d1／D-d2（刪除版）；(2) X 為 None 且 own=0 → 第 3 條 violated 用 D-a3，否則 D-a；(3) same 或 unknown > 0 → D-P；(4) 其餘 → 第 3 條 violated 用 D-a3，否則 D-a。
   - `/limits`（**2026-10-07 風控更正順序**，來源：風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u」段；取代原 tech-architect 補段的順序；第一個符合的就用）：(1) Y 未定義，即第 2 條 comparable 為空、`reported_sector is None` → 第 3 條 violated 用 D-a3，否則 D-a；(2) 帳本有任何 unknown，或 Y 有 same（依 ADR-0022 M-3／M-5，mixed 群組的 categories 含 Y 也算）→ D-P，target 為「已納入比較的產業」；(3) 其餘 → 第 3 條 violated 用 D-a3，否則 D-a。
     - 更正註記（2026-10-07，風控）：原順序為「(1) 有 unknown 或 Y 有 same → D-P；(2) Y 未定義 → D-a／D-a3；(3) 其餘」。原第 (2) 點置於 D-P 之後為筆誤（死條款），風控定性為更正自身優先序的筆誤；詳見 ADR-0022 Decision 5。
     - D-a3 仍只在「原選 D-a」處替換（第 1、3 點）；D-P 不動（第 2 點）。
   - D-P、D-d1、D-d2 不因第 3 條 status 改變。第 3 條 violated 時，W-b1 已在該條 detail 揭露方向。
7. **禁止重算**：book.py 不得接收 `RiskBudget`、不得讀 `max_gross_exposure`、不得 import 或呼叫 `_breaches`／`_check_gross_exposure`，也不得用 `gross_exposure_twd`、`net_worth.amount_twd` 計算任何比率。
8. **不變式**：帳本不完整時，第 3 條 status 只能是 violated 或 not_evaluable（`limits.py:957-963` 由 6-b 拆出 violated 分支）〔2026-10-07 勘誤，tech-architect：舊 `limits.py:957-963` → 現 L1150-1156。〕。`_book_level_notes` 不對 passed 做特別處理；一旦出現 passed，即觸發 F-4 重審。
9. **落地與範圍**：
   - D-a3 與 6-b 的 violated 分支必須同一個 PR。若 D-a3 先上，它是死碼；若 6-b 先上，D-a 會與 violated 並陳。
   - **本節修訂 KB-1／KB-3 的範圍**：6-b 可以動 book.py（新參數；D-a3 常數；若 ADR-0022 PR 未建 finalizer，也包含 finalizer）、`api/advice.py`（組裝順序）、`book_limits.py` `evaluate_book_limits` 中組 notes 的那一處（`:312`）。〔2026-10-07 勘誤，tech-architect：舊 `book_limits.py:312` → 現 L400。〕
   - `_book_level_check`、`_aggregate`、`alerts/engine.py`、前端仍然不動。

**Consequences**
- 好處：選句只依同一回應實際送出的第 3 條判定，D-a 與 D-a3 的同現規則可以用測試窮舉。
- 代價：`BookContext` 介面擴充；兩個呼叫端的組裝順序改變；ADR-0022 PR 範圍略增（finalizer）。
- 殘留：insufficient_data 分支維持 D-a。該分支沒有任何上限數字，前端只渲染不足面板（風控 A-8），不擴大既有語意。（風控 2026-10-07 第四段已裁定 accept 附 R-IN-1／R-IN-2、F-10，見第 3 點與「重審與失效條件」。）

**可檢查約束（qa）**
- KD-1：grep D-a3 常數，只出現在 `_book_level_notes` 與測試。
- KD-2：`app/` 內讀 `BookContext.notes` 的次數為 0；兩個回應組裝點都經過 finalizer，並明示 `gross_exposure_status`。insufficient 分支明寫 `gross_exposure_status=None`，`None` 只准用在該分支（風控 R-IN-1，2026-10-07）。
  - 〔2026-10-07 風控 P-4 更正（審查檔第五段；PR-3 合併前補入）〕「`None` 只准用在該分支」改為「**`None` 只准用在 insufficient 分支與 `BookContext.notes` 相容屬性**（只供測試，production 禁讀；風控 P-4 白名單）」，grep 恰兩處（R-P4-1）。並補：
    - **R-P4-4**：白名單的條件是 KD-2 抓得到漏網的讀取。(i) 靜態半邊須攔截**函式參數接收的 `BookContext`**——風控所述現行靜態半邊（`test_adr0022_sector_unvalued.py:900-922`）只認「同檔案內由 builder 指派的名稱」或「直接呼叫」，抓不到以函式參數傳進來的 `BookContext`；實作方式由 tech-architect 決定（風控所述：app/ 目前讀 `.notes` 的只有 9 處，明列 allowlist 也可行；〔tech-architect 2026-10-07 更正：9 處是 AST 層的屬性存取，文字 grep 會命中 10 行，多出的是 `book.py:933` docstring 的 `BookContext.notes`；方案已採封閉式 allowlist，見下 KD-2a～KD-2j〕）。(ii) 在**新檔**新增執行期禁讀格：帳本不完整、第 3 條 violated，在禁讀相容屬性的情況下打 `/api/advice` 與 `/api/portfolio/limits`，斷言含 D-a3、不含 D-a。(iii) 既有 KD-2 測試（L900-1042）一律零修改。
    - **R-P4-5**：qa 盤點既有讀 `.notes` 的測試，找出其 fixture 會讓第 3 條 violated（帳本不完整、淨值新鮮、A/N ≥ 上限）而且斷言了 D-a 的；若有，要嘛改用 `book_notes(..., gross_exposure_status=<實際值>)`，要嘛在 PR 說明逐條註明「此測試驗的是相容檢視，不是 production 輸出」。不得讓測試把 D-a 釘成 violated 情境下的期望值。
  - **〔2026-10-07 KD-2 補強規格（R-P4-4／R-P4-1／R-P4-2 的實作方案），tech-architect；PR-3 合併前併入〕**來源：`work/dispatch/2026-10-07-任務單-6-b-總曝險上限帳本不完整但已超標時不擋加碼.md` 檔尾「KD-2 補強規格」段（讀碼基準 HEAD 4f19c2d 工作樹，唯讀，未跑測試；coordinator 原文轉錄）。B 類摘要，測試名稱、行號、fixture 細節以該段為準，tech-writer 未驗證其 `檔案:行號`。屬 KD-2 的修訂，不另立 ADR。
    - **方案**：靜態半邊改採**封閉式 allowlist**（KD-2a～KD-2e）；R-P4-1／R-P4-2 用 AST 釘死（KD-2f、KD-2g）；執行期半邊加一格（KD-2h）；既有 KD-2 測試零修改（KD-2i）。否決：型別導向 AST 作主方案（開放式，受體換一種取得形式就靜默漏抓）、全套件執行期堆疊檢查版（脆弱、需改 conftest）、拿掉 `BookContext.notes`（要改 19 處以上既有測試、與風控 P-4 理由衝突）。型別導向 AST 只作 KD-2d 輔助。
    - **新增檔案**：`apps/stock-desk/backend/tests/test_book_context_notes_guard.py`（跨功能靜態守門，KD-2a～KD-2g）；`apps/stock-desk/backend/tests/test_adr0023_gross_exposure_incomplete.py`（6B-13 規劃的新檔，KD-2h 放此）。
    - **KD-2a**：掃描 `app/**/*.py` 的 AST，所有 `ast.Attribute(attr="notes")`（Load／Store／Del 都算）以 `(posix 相對路徑, 外圍 qualname, ast.unparse(node.value))`——即（路徑, qualname, 受體）——為鍵計次，須與 `NOTES_ATTRIBUTE_ALLOWLIST` **完全相等**；多一處、少一處、次數不同、過期的 allowlist 項目都失敗。測試名 `test_every_notes_attribute_in_app_is_allowlisted`。
    - **KD-2b**：allowlist 只有 9 項（次數皆為 1），**任何一項的受體都不得是 `BookContext`**；新增項目時 PR 說明寫受體型別與來源函式，由 qa 對照讀碼。9 項（tech-architect 所述現行行號）：
      1. `app/scheduler.py`, `refresh_sector_board`, `result`（`RefreshResult`；:479）
      2. `app/services/index.py`, `LoadedIndexBars.meta`, `self`（`LoadedIndexBars`；:125）
      3. `app/services/index.py`, `LoadedBenchmark.meta`, `self`（`LoadedBenchmark`；:345）
      4. `app/leverage/service.py`, `build_leverage_chapter`, `detection`（`detect_module.detect` 回傳值；:202）
      5. `app/leverage/service.py`, `build_leverage_chapter`, `decomposition`（`drag_module.decompose_drag` 回傳值；:239）
      6. `app/api/portfolio.py`, `portfolio_limits`, `report`（`BookLimits`，其 notes 由 finalizer 在 `book_limits.py` L400 產出；:191）
      7. `app/api/settings.py`, `_response`, `view`（`NetWorthView`；:326）
      8. `app/api/settings.py`, `write_settings`, `review`（`NetWorthReview`；:403）
      9. `app/api/backtest.py`, `execute_backtest`, `dividends`（`_DividendOutcome`；:511）
    - **KD-2c**：`app/` 內禁止動態存取——`getattr`／`hasattr`／`setattr`／`delattr` 第 2 個參數為字串常數 `"notes"`；函式名為 `attrgetter`／`methodcaller` 且參數含字串常數 `"notes"`；`ast.MatchClass` 的 `kwd_attrs` 含 `"notes"`。測試名 `test_no_dynamic_notes_access_in_app`（tech-architect 稱目前為 0）。已知限制：攔不到 `__getattribute__`、以變數字串組成的 `getattr` 這類刻意規避。
    - **KD-2d**：每個 allowlist 項目所在函式不得呼叫 `build_book_context`／`build_book_level_context`，且參數與回傳註記的 AST 中不得出現名稱或字串含 `BookContext` 的節點（防已登記名稱被改綁成 BookContext）。測試名 `test_allowlisted_notes_readers_never_hold_a_book_context`。
    - **KD-2e**：掃描器自我檢驗（防空轉；也是 F-10(c)「攔截函式參數接收能力」的證據）。KD-2a 的掃描函式掃內嵌合成原始碼片段，每段都必須回報違規，**至少七例**：函式參數接收（`def f(b: BookContext): return b.notes`）、`X | None` 註記（`def f(b: "BookContext | None"): return b.notes`）、屬性鏈（`def f(x): return x.book.notes`）、回傳值（`def f(): return make().notes`）、迴圈（`for b in books: b.notes`）、walrus（`if (b := g()): b.notes`）、`getattr(b, "notes")`（走 KD-2c 的函式）。測試名 `test_the_notes_scanner_catches_indirect_receivers`（參數化）。
    - **KD-2f**（R-P4-1 的 AST 釘死）：`app/` 內 `ast.keyword(arg="gross_exposure_status")` 且值為 `ast.Constant(None)` 者**恰兩處**：(`app/api/advice.py`, `get_advice`)×1，以及 (`app/advice/book.py`, `BookContext.notes`)×1。`app/` 內 `book_notes` 的呼叫集合固定為 (`app/advice/book_limits.py`, `evaluate_book_limits`)×1、(`app/api/advice.py`, `get_advice`)×2、(`app/advice/book.py`, `BookContext.notes`)×1；每次呼叫都須明寫 `gross_exposure_status` 關鍵字，**不得用 `**` 展開**。測試名 `test_gross_exposure_status_none_only_at_the_two_whitelisted_sites`。
    - **KD-2g**（R-P4-2）：以 `inspect.signature` 確認 `book_notes` 與 `_book_level_notes` 的 `gross_exposure_status` 參數 `kind is KEYWORD_ONLY` 且 `default is Parameter.empty`。測試名 `test_gross_exposure_status_is_keyword_only_without_default`。
    - **KD-2h**（R-P4-4 (ii) 執行期禁讀格；放 `test_adr0023_gross_exposure_incomplete.py`，fixture `compat_notes_forbidden` 在新檔另寫一份，不從舊檔 import、不移進 conftest，以免修改既有檔案）：2330（`sector="半導體業"`，已估值）＋2881（`sector="金融保險業"`，**不種 bars**，得 1 筆未估值部位）＋淨值設為 valued×0.99（`valued` 取自 `GET /api/portfolio/summary` 的 `totals.market_value_twd`，tech-architect 稱沿用 `test_api_advice.py:164-177` 做法），預設 `max_gross_exposure=1.00` → 第 3 條 violated。斷言：`/api/advice/2330` 的 `context_notes` 與 `/api/portfolio/limits` 的 `notes` **都含 D-a3、不含 D-a**；前置斷言（防空轉）確認 summary 恰有 1 筆非 ok 部位、兩回應的 `gross_exposure` 皆 violated。**未估值部位必須放在其他已知產業**（不得放半導體、不得未填產業），否則會走 D-P，D-a3 不會被選到，這一格就空轉。測試名 `test_incomplete_book_over_cap_notes_carry_d_a3_without_the_compat_view`。tech-architect 稱**未實際驗證**帳本不完整時 `PUT /api/settings` 以 valued×0.99 能存檔，前置斷言會在跑測時現形。
    - **KD-2i**：既有 KD-2 測試（`test_adr0022_sector_unvalued.py` L866-1042）**零修改**。證明方式（qa 只用 `git diff` 與 Grep）：`git diff <PR-3 base>..<PR-3 head> -- apps/stock-desk/backend/tests/test_adr0022_sector_unvalued.py` 輸出為空（PR-3 base 指 PR-1 的頭）；若 R-P4-5 不得不改該檔其他測試，退而要求 `git diff -U0` 的每個 hunk 與 base 版 L866-1042 無交集，且 `_book_context_receivers`、`test_no_production_code_reads_book_context_notes`、`notes_property_forbidden`、`test_both_responses_assemble_their_notes_through_the_finalizer` 與 K-5 三個測試名稱在 head 版仍存在。新測試是嚴格上位集，舊測試保留形成雙重攔截。
    - **KD-2j**：`app/` 內的註解與 docstring **不得出現 `gross_exposure_status=None` 這段字面**（R-P4-3 的 docstring 改用英文敘述，例如 "passes no cap 3 verdict"），好讓 Grep 精確。qa 核對用 Grep（tech-architect 所述）：G1 pattern `gross_exposure_status\s*=\s*None\b`、path `apps/stock-desk/backend/app`、glob `*.py`，結果恰 2 行；G2 `gross_exposure_status\s*:[^=\n]*=`，0 行（簽章不得給預設值）；G3 `book_notes\([^)]*\*\*`，0 行。Grep 為人工交叉核對，以 KD-2f 為準。
    - **兩點更正（tech-architect 2026-10-07）**：(1) `app/` 沒有 `BookLevelContext` 類別，book 範圍也是 `BookContext(scope="book")`（tech-architect 所述 `book.py:345-348`、`:956-1007`）；(2) `.notes` AST 存取 9 處，文字 grep 為 10 行（含 `book.py:933` docstring）；`AdviceCard.notes` 目前在 `app/` 沒有任何讀取（tech-architect 所述）。
    - **代價（tech-architect 所述）**：任何功能新增 `.notes` 讀取都要改 allowlist 並在 PR 說明受體型別；執行期格只覆蓋它構造的情境；「不讓相容檢視進到使用者畫面」仍只靠測試，型別與執行層沒有強制（CEO 知悉 (x) 不變）。
    - qa 在 PR-3 依 KD-2i 的 `git diff`、G1～G3 Grep、allowlist 九項受體型別逐一對照讀碼；風控於 PR-3 合併前做單項核對，確認 KD-2e 自我檢驗涵蓋「函式參數接收」（tech-architect 所述）。
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
         - **〔2026-10-07 更正，風控第六段（C-3，PR-1 合併前；來源：風控審查檔第六段「ADR-0023 是否要 tech-writer 更正」）。上列 (b) 原文保留，以本更正為準〕**
           - 改寫：own>0（production builder 建出的 context）且沒有 violated 時，any 規則**一律 skipped**。
           - 原本是 mixed quiet 的（6-a 前第 1、4、5 條有 passed），轉為 skipped：S-B2 句消失，改用既有 skipped 句列出五條上限。
           - 原本就是 skipped 的，維持不變。
           - 「原本全部 passed → mixed quiet」和「原本 mixed 仍 mixed、`{n}` 增加」兩項**不可能發生**（原文兩條作廢）。理由：own>0 時第 3 條必定不是 passed；有產業時第 2 條也必定不是 passed。
           - 「最多 +3」改為「**未評估條數最多 +3，但對 any 規則只表現為 quiet → skipped，不會表現為 `{n}` 變大**」。
           - `{n}` 範圍 1–4 仍成立，但只出現在 own=0 的情境。
           - 加註：只有手刻 context 的 None 退路下可達 mixed quiet，那不是 production 路徑，由 F-1 把關。
           - **風控自承（來源說明）**：(b) 的錯誤口徑（「any 規則未評估條數增加，最多 +3」及三種轉變的展開）有一部分來自風控審查檔第一段「二、逐條」第 7 點的寫法；tech-architect 展開成三種轉變時，風控沒有發現 own>0 下第 2、3 條不可能 passed，**屬風控疏失**。風控審查檔第一段二.7（本 ADR「風控裁定轉錄」節第 7 點）的相同口徑一併以本更正為準。
           - 依據（風控第六段逐點讀碼，風控所述）：own>0 時第 1、4、5 條沒有任何分支回傳 passed；第 2 條有產業時 `same = own_lots + same_sector_lots ≥ 1`，只會 violated 或 not_evaluable，沒有產業時一定 not_evaluable；第 3 條 passed 需要 `book_fully_valued is True`，builder 的 `_fully_valued` 與 own 計數用同一個「status != ok」，own>0 時必為 False；`_limit_outcome` 的 mixed 分支需要 passed ≥ 1。
           - 對應的 C-4：6A-19 的 PR 說明要照此口徑改寫，不能再寫「any 規則未評估條數最多 +3」。
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
         - 〔2026-10-07 更正，風控第六段〕「缺少輸入」用語不精確這個列管項，適用範圍擴大為「**所有 own>0 且沒有 violated 的 any 規則**」（依上 (b) 更正，這些規則一律 skipped）。字面不改，列管等級不變。
     (f) 觀察（不擋 6-a）：F-4「已評估 {E} 條規則」會把 mixed quiet 算成已評估（S-B2 列管觀察），6-a 會讓這類規則變多。依 S-B2 失效條件 1 重審時一併處理。
         - 〔2026-10-07 更正，風控第六段〕「6-a 會讓這類規則變多」方向相反，改為「**6-a 讓 own>0 的 mixed quiet 減少（轉為 skipped）**」。
     (g) **測試面（required，qa 逐條）**：
         - `tests/alerts_helpers.py` 的 `compliant_context`／`breaching_context` 沒有設定 `book_fully_valued`（預設 `None`，`limits.py:644`〔2026-10-07 勘誤，tech-architect：舊 `:644` → 現 L751〕）。依 Decision 3 的退路，這會被視為 own>0：S-B2 例 (b)（`test_alerts_engine.py:462-471`）會從 quiet 變成 skipped，`breaching_context` 的 fired detail 也會多出 W-a2。
         - 處理方式：兩個 fixture 補 `book_fully_valued=True`（符合它們「完整帳本」的原意）。S-B2 (a)(b)(c) 與 fired／skipped 迴歸測試的**斷言零修改**；fixture 這項改動列入 PR 說明。
         - 另外新增 own>0 測試：any 規則轉 mixed quiet；any 規則轉 skipped；單條第 1 條轉 skipped 且不帶 FX 尾句；violated 時的 fired 條目與 own=0 對照組相同，且 detail 以 W-a2 結尾。
         - 〔2026-10-07 更正，風控第六段〕**第 1 例（any 規則轉 mixed quiet）在 production builder 下不可達；2026-10-07 PR-1 單項核對裁定，改由不可達證據測試取代**（風控所述測試名 `test_any_rule_with_own_lots_cannot_turn_mixed_quiet_from_a_built_book`；C-2：須補「對照組非空洞」前提斷言——同一帳本去掉那筆未估值批次後，sector=SEMI 時第 2 條要 passed、net_worth 有值時第 3 條要 passed、第 1、4、5 條要 passed；cache_only 成因也要參數化跑一次；suggested：同測試內對這些 context 實際跑 any 規則，斷言結果 ∈ {skipped, fired}）。不採「直接刪掉」與「改成 own=0 mixed quiet → own>0 skipped」兩選項。原文保留。
     - **風控裁定（2026-10-07，風控審查檔第四段，HEAD d66183e）：accept，屬「fixture 原意就是完整帳本的修正」，不算「改測試讓它過」，附條件 RF-1～RF-6。** 理由（風控所述）：(1) 原意有證據：`alerts_helpers.py:136`「single-position weight is over the 15% cap」與 `:147`「comfortably inside every evaluable cap」都未模擬無法估值持倉；S-B2 例 (b) 註解（`test_alerts_engine.py:462-463`）寫明未評估只有第 2、3、5 條，前提即第 1、4 條 passed＝完整帳本。(2) 先例：advice 側手刻 fixture 已明設 True（`test_advice_engine.py:62`、`test_advice_limits.py:74`、`test_advice_selection.py:35`、`test_playbook_price_fields.py:47`、`test_advice_wording.py:81`）。(3) 判準：補一個測試主旨本來就依賴、只是沒寫出的輸入，被測行為不變 → 可；修改斷言或放寬退路 → 不可。(4) 讀碼確認：`compliant_context` 有 atr，第 1、4 條算得出且低於門檻；None 退路下兩條轉 not_evaluable，加第 2、3、5 條五條全 not_evaluable，故由 quiet 變 skipped。
     - **RF-1～RF-6（required，qa 逐條；任一未做到，單項核對改判 VETO）**：
       - **RF-1**：`alerts_helpers.py` diff 只能是兩個 fixture 各加 `book_fully_valued=True` 加一句 docstring「完整帳本、無無法估值持倉」，不改其他欄位；使用這兩個 fixture 的測試（`test_alerts_engine.py` L227、243、255、264、273、289、302、314、467、571、603、661、739、768）斷言零修改。
       - **RF-2**：禁止改預設值讓測試過：`PortfolioContext.book_fully_valued` 預設維持 `None`（`limits.py:644`〔2026-10-07 勘誤，tech-architect：舊 `:644` → 現 L751〕），6-a 退路維持「None 視為 own>0」。
       - **RF-3**：退路另外釘住：用原 fixture 輸入（不設 `book_fully_valued`）走 alerts 路徑新增對照測試：(i) any 規則 → skipped，既有 skipped 字面，不出現 S-B2 句；(ii) 違反帳本 → fired，`violated_limit_ids`／條目與 True 版相同，detail 以 W-a2 結尾。
       - **RF-4**：同時新增 own>0 對照測試（tech-architect 四例：any 轉 mixed quiet；any 轉 skipped；只監看第 1 條轉 skipped 且不帶 FX 尾句；violated 時 fired 條目與 own=0 相同且 detail 以 W-a2 結尾）；own>0 用 `build_book_context` 實際會設定的欄位構成，與 RF-3 的 None 退路分開，不得互相代替。
         - 〔2026-10-07 更正，風控第六段（RF-4 第 1 例衝突裁定）〕上列四例的**第 1 例「any 轉 mixed quiet」在 production builder 下不可達；2026-10-07 PR-1 單項核對裁定，改由不可達證據測試取代**（C-2 補對照組前提，見 Consequences 3(g) 更正）。其餘三例照舊。另 RF-1 的 docstring 以英文等義句「A complete book: every position was valued, none is unvalued.」可接受（風控第六段：章程 §0.1 規定程式碼與註解一律英文；RF-1 要求的是把「完整帳本」「無無法估值持倉」兩件事寫明，不是指定語言）。
         - **〔2026-10-07 風控補，R-RF4（審查檔第五段）〕** own>0 的四個對照測試，除了 `UnvaluedComposition(own_lots≥1)` 和 `book_fully_valued=False`，凡是 production builder 會設定的欄位（例如 `valued_unclassified_lots`）都要明設，不得依賴任何其他 None 退路。建議至少一例直接經 `build_book_context` 建構。
       - **RF-5**：全面盤點：qa 列出測試中所有未設 `book_fully_valued` 又會走到 `evaluate_limits`／`build_advice`／`suggest_quantity_range` 的手刻 `PortfolioContext`；風控已找到 tech-architect 未列的 **`test_advice_limits.py:1729` `_fractional_ctx`**（docstring「the entire book」，完整帳本原意）；只走 `build_context` 的（`test_advice_engine.py:88/369/598`、`test_observation_window.py:181-182`、`test_drawdown_current_lookahead.py:109`、`test_adr0021_field_evaluability.py:201`）請 qa 確認不受影響〔2026-10-07 勘誤，tech-architect：上列 `test_advice_engine.py` L88／L369 其實**會**走 `build_advice`，不是只走 `build_context`；但兩者皆為 insufficient_data 且沒有總資產，W-a1 不觸發、(A) 不附加，結果不受影響。此勘誤未提及 L598，該處維持原歸類。〕。每處歸類：原意完整帳本 → 補 True 列入 PR；不是 → 屬行為變更，斷言修改逐條對照 6-a 裁定寫明理由；期望值改變卻不在清單上 → BLOCKING。
       - **RF-6**：PR 說明逐項列出 RF-1、RF-5 的 fixture 變更與理由。
       - 否決理由：無。若 RF-1～RF-6 任一未落實，第 2 點於單項核對改判 VETO（違反「絕不放行隱藏風險」：放寬退路或拿掉退路測試覆蓋，等於讓「無法確認帳本完整」被當成完整帳本）。
4. **只監看 gross 規則由 skipped 變 fired**：只監看 gross_exposure 的規則在 6-b 條件下由 skipped 改 fired；W-b1 經 `alerts/engine.py:309-310` 進推播（組成 `{symbol} 觸發風險上限：{names}。{details}`，風控審查檔所述 `:310`）；風控接受，不觸發 S-B2 失效條件 6／8（6-b 裁定 (3)）。
5. **W-a2／W-b1 進推播**：誠實度與無操作指示限制適用（見 Decision 4、5）。W-b1 進推播時 6-b GWT 要求 fired 含 W-b1。
6. **卡片觀感**：violated 並列「未參與計算」於 375 寬是否讀得通，qa-e2e 抽驗。〔2026-10-07 加註（風控第六段；依第五段 R-P5-2）：own>0 下此並列不可能出現，並列情境**已移到 PR-3（6-b）**，見 R-11 勘誤。〕
7. **ADR-0022 的 D-d1／D-d2 與 D-a**：6-a／6-b 落地會使 ADR-0022 的 D-d1／D-d2、D-a 失去所指或被涵蓋（失效條件 1、2），須先有 D-a3 與 6-a 方向子句處置的核可字面。
8. **手刻 context 測試**預設 `book_fully_valued=None` 會走退路（tech-architect 所述）。

### 被此決策約束的事

- 6-a、6-b 皆排在 F-1 之後、ADR-0022 PR 之後；不作 F-1 部署前置。
- 6-a、6-b 的字面（W-a1、W-a2、W-b1、D-a3、6-a 方向子句處置）核可前不得實作。
- CEO 知悉增補（風控 2026-10-07）：(i) 曾核可的 D-d1 含數學錯誤、已更正；(ii) 風控修訂自身 FR-9 (a-附加)「一律 not_evaluable」為非對稱判定（更保守）；(iii) 6-a 修後殘留（2026-10-07 風控更新：改為「(A) 落地且 qa 通過後消除」，見 Consequences 殘留 1）；(iv) 6-b 排在 ADR-0022 之後；(v) 6-c 採 C-1 的代價；(vi) F-1b。2026-10-07 風控增補：(vii) ADR-0022 M-1 整檔計入的高估方向，違規推播可能建立在高估的比率上（見 ADR-0022 Decision 1 補充）；(viii) 降級／擋下原因只在預設收合的卡內可見（見 Consequences 殘留 1，仍列殘留）。
- CEO 知悉增補（風控審查檔第五段，2026-10-07；逐字自第五段「CEO 知悉增補」）：
  - **(ix)** P-3 更正：審查檔裡「observed None」的歧義，源自 creative-lead 草稿錯誤引述風控裁定 (3)，風控核可時沒有發現，屬於風控的疏失，現已更正。
    - 使用者端的影響：own>0 且 violated 的卡，「觀察值」會顯示只用已估值持倉算出的比率，同一列附 W-a2「實際比率無法確認」。
    - D-d1（只有本標的有無法估值持倉）時，這個數字偏低。D-d2（本標的與其他標的都有）時，這個數字可能偏高也可能偏低，此時的 violated 屬於保守處理。
    - D-5 加 own>0 的卡，觀察值顯示「—」。
  - **(x)** P-4 白名單：相容屬性一律照「沒有第 3 條判定」組 notes，所以第 3 條 violated 時它可能組出 D-a，和 production 實際送出的 notes 不同。「不讓它進到使用者畫面」這件事目前靠 KD-2 測試把關，型別與執行層都沒有強制。
  - **(xi)** own>0 的持有卡**完全不提供數量區間**，連賣出方向也沒有。這不在 (iii) 的範圍內，(A) 落地後也不會消除。
  - 若 CEO 對以上裁定有異議，保留本書面紀錄，由 CEO 負最終責任。
- CEO 知悉增補（風控審查檔第六段，2026-10-07；逐字自第六段「CEO 知悉增補」）：
  - **(xii)** ADR-0023 Consequences 3(b) 的 S-B2 口徑有誤，一部分源自風控第一段第 7 點，是風控的疏失。對使用者的實際效果是：own>0 且沒有超標時，「任一上限」規則一律略過，理由句寫「缺少輸入」（實際原因是分子不完整，用語不精確，已列管）。不會出現「N 條上限未評估」的揭露句。不會產生錯誤放行。
  - **(xiii)** PR-1 必須在 PR-0 之後合併（R0-1）。如果順序顛倒，過渡期 own>0 的第 4 條會用回填的 ATR 和占位匯率算出 W-a1／W-a2：方向一致，但同卡 FX note 的矛盾仍在（PR-0 的 C-1）。
  - **(xiv)** 「同一標的部分估值」的端到端測試用了替身。正式可達路徑只有 legacy 雙幣別資料；「全部無法估值」是一般正式路徑，有無替身的測試。
    - **〔2026-10-08 加註（tech-architect 可達性評估）；原文保留〕** 「正式可達路徑只有 legacy 雙幣別資料」不精確：tech-architect 評估另指出，同標的 US／USD 兩批、其一 `opened_at` 留空（`fx_open` 缺）也能經正式 POST 建出「一批已估值、一批未估值」（own>0）。詳見 Decision 4 末〔2026-10-08 加註〕。
  - 若 CEO 對以上裁定有異議，保留本書面紀錄，由 CEO 負最終責任。
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
  - **〔2026-10-07 勘誤，tech-architect〕KA-1「6-a 不動 `book.py`」範圍補上兩處例外**：(1) `book.py` 的 D-d1／D-d2 常數——由分句版改為刪除版，**常數名不變、內容整句換**；(2) `_symbol_direction` 中 own>0 的判斷，改為呼叫 `symbol_has_unvalued_lots`（一行）。原因：風控 R-6 required「D-d 刪除版與 6-a 同一 PR」，而 D-d 常數位於 `book.py`，與 KA-1 字面衝突；**以 R-6 為準**（任務單檔尾標題載明衝突時 ADR-0023 > ADR-0022 > 風控審查檔 > 本單，本勘誤即為修正 ADR-0023 該處）。其餘（`build_book_context`、`_position_rollup`、`quantity` 語意、`book_limits.py`、`alerts/engine.py`、前端）仍不動。原文保留不刪。（來源：6-a 任務單檔尾「tech-architect 實作規格」本次結論 3(i)、前置 P-6、6A-09、6A-10、6A-11；B 類轉錄。）
- **KA-2**：判斷式全 repo 一處（grep `own_lots`）；不複製已核可字面。
- **KA-3**：own=0 → 三條逐字不變、既有測試零修改。

**KB（6-b）**

- **KB-1**：範圍＝`limits.py` `_check_gross_exposure`、`notional_caps` 閘門、新常數 W-b1、註解／docstring、測試；**不動** `book.py` 邏輯、`book_limits.py`、`alerts/engine.py`、前端。**（2026-10-07 修訂，見 Decision 8-1 第 9 點：6-b 可動 `book.py`（新參數、D-a3 常數；若 ADR-0022 PR 未建 finalizer，也包含 finalizer）、`api/advice.py`（組裝順序）、`book_limits.py` `evaluate_book_limits` 中組 notes 的那一處（`:312`）；`_book_level_check`、`_aggregate`、`alerts/engine.py`、前端仍不動。）**
  - **〔2026-10-07 勘誤，tech-architect〕** (1) 本條「`notional_caps` 閘門」對第 3 條的處理是在原有 `!= "not_evaluable"` 判斷上**加上** `book_fully_valued is True`（經 `numerator_complete(ctx, "gross_exposure")`），**不是**以後者取代前者（見 Decision 2 勘誤）。(2) `book_limits.py:312` → 現 L400。原文保留不刪。
- **KB-2**：`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` **字面不改**，只改英文註解（`limits.py:328-331`）、`book.py` 模組 docstring 規則 3（L28-31）、欄位註解 L641-643（tech-architect 所述行號）。〔2026-10-07 勘誤，tech-architect：舊 `limits.py:328-331` → 現 L376-379；舊欄位註解 `:641-643` → 現 L748-750（讀碼基準 66a88b3 之後）。〕
- **KB-3**：`/limits` 第 3 條經 `_book_level_check`（`book_limits.py:315-341`）原樣 violated（不改 `book_limits.py`）。**（2026-10-07 修訂，見 Decision 8-1 第 9 點：`_book_level_check` 本身仍不動；`book_limits.py` 僅 `evaluate_book_limits` 中組 notes 的那一處（`:312`）可動，改為評估完成後經 finalizer 組裝。）**〔2026-10-07 勘誤，tech-architect：舊 `book_limits.py:312` → 現 L400。〕
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
7. ADR-0023 待確認：失效條件 2 改「第 1、4、5 條」（更正原審查檔）；失效條件 3「6-c 擴及」已被 C-1 涵蓋，分類變更段繼續有效並加 M-1／M-3 以外再變更；unknown-only 第 2 條 passed 附 W3 為非對稱通則**明列例外**（維持 passed），但**試算上屬分子不完整，依 KC-2 不得進 `notional_caps`**（required，與 C-1 一致，請 tech-architect 確認 ADR-0022 已規定否則補）；6-a 對 S-B2 條數（請 tech-architect 確認）：own>0 時第 1、4、5 條只有 passed 變 not_evaluable、violated 集合不變，any 規則未評估條數**增加**（最多 3 條，與 6-b 相反），只監看其一的規則由無聲 quiet 變 skipped（改善），不觸發 S-B2 失效條件 1～8，S-B2 列管 2 範圍加「分子不完整」口徑。〔2026-10-07 更正，風控第六段（C-3）：本點「any 規則未評估條數**增加**（最多 3 條，與 6-b 相反）」口徑有誤，是風控疏失；以 Consequences 3(b) 更正為準——own>0 且無 violated 時 any 規則一律 skipped，「最多 +3」只表現為 quiet → skipped。原文保留。〕
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
  - **〔2026-10-07 風控 P-5 改寫（審查檔第五段；PR-1 合併前補入；own>0 項以此為準，其餘項不變）〕**
    - **R-P5-1**：own>0 卡片（三條 W-a1，或第 1 條 W-a2）要驗證**卡上沒有數量區間、也沒有「未參與計算」句**，並附 R-P3-3（W-a2 卡上的「觀察值」與 detail 印的比率相同；D-5 加 own>0 的卡上觀察值顯示「—」、上限照舊顯示）。原文「W-a2 與『未參與計算』並列」在 own>0 下不可能出現，故取代。
    - **R-P5-2**：並列情境移到 PR-3（6-b）。新檔要有 API 測試：own=0、帳本不完整、第 3 條 violated 附 W-b1、action 為 reduce 或 stop_loss 時，`quantity_range.basis` 的 skipped 句列出「總曝險上限」，而且不出現「仍然超標」。qa-e2e 能構造出此情境的話加抽一張（suggested）。
    - **R-P5-3**：前提是第 3 條閘門為「加上」`numerator_complete`、不是「改為」（見 Decision 2 勘誤）。qa 在 PR-3 驗證：own>0 時 `notional_caps` 為空，且淨值過期時第 3 條不進 `notional_caps`。

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
  - **〔2026-10-07 風控 P-4 更正，F-10(c) 新文（審查檔第五段；PR-3 合併前補入；取代上句）〕(c) `None` 被用在上述兩處以外，或 production 讀取 `BookContext.notes`，或 KD-2 失去攔截函式參數接收的能力。**「上述兩處」＝insufficient 分支與 `BookContext.notes` 相容屬性（風控 P-4 白名單）。原文保留不刪。
  - **F-10(c) 操作化定義（tech-architect 2026-10-07，6-b 任務單檔尾「KD-2 補強規格」段；PR-3 合併前併入）**：**「KD-2a 或 KD-2e 被刪除、被 skip、被 xfail，或 allowlist 出現受體為 `BookContext` 的項目」即屬「KD-2 失去攔截函式參數接收的能力」。**（同段 Consequences 另載「或改回開放式啟發法」；操作化定義以上句為準，該句僅作背景。KD-2a～KD-2j 見 Decision 8-1 KD-2 之下。）
- **F-11、F-12**（2026-10-07，風控審查檔 `work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md` 檔尾「`/limits` 方向子句優先序更正與 W-6u」段「失效條件增補」；**屬 ADR-0022，已逐字收於其「重審與失效條件」第 9、10 項，本 ADR 只列指標、不重抄**）：
  - **F-11**：重審 `/limits` 優先序第 1 點（Y 未定義 → D-a／D-a3，見 Decision 8-1 第 6 點）與 D-P 的 `/limits` target；觸發條件見 ADR-0022 失效條件 9。
  - **F-12**：重審 W-6u 的顯示條件與 `SECTOR_UNVALUED_EXCLUSION_SUFFIX` 的適用範圍；觸發條件見 ADR-0022 失效條件 10。

## 落地（PR 切分、單一判斷式、既有測試修改清單、前置與合併閘門）

〔2026-10-07 追加，tech-writer 落檔；狀態維持 proposed。〕

來源（B 類轉錄）：`work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md` 檔尾「tech-architect 實作規格」段（tech-architect 2026-10-07，讀碼基準工作樹 66a88b3 之後，coordinator 原文轉錄）的「本次結論」「決策（ADR 草案摘要）」「既有測試修改清單」「前置」「需 CEO 決定」。tech-architect 於該段「驗證」明載**未跑任何測試、未用 git 驗證 HEAD 4f19c2d**，行號為其讀到的工作樹狀態；本節所有 `檔案:行號`、函式名、測試名皆為 tech-architect 所述，tech-writer 未逐項對 code 驗證（僅抽查本 ADR 勘誤所列 `limits.py` L376-379、L748-751、L1150-1156、L1435-1440 與 `book_limits.py` L400 於分支 `product/stock-desk` 工作樹存在對應內容；行號會漂移，引用時以原文定位）。該段標題載明：**衝突時 ADR-0023 > ADR-0022 > 風控審查檔 > 本單**。

### 1. PR 切分

- 切四個 PR：**PR-1＝6-a**、**PR-2＝(A) A-降級句**、**PR-3＝6-b**、**PR-4＝N1**。
- 順序 **PR-1 → PR-2 → PR-3**（分 PR、同一 release；**A(5)：(A) 最晚下一個 release**）。PR-2 若延誤，6-a 可先發，但 (A) 必須排在下一個 release。
- (A) 與 6-a 放同一個 PR **不被 A(5) 禁止**，tech-architect 建議分成疊在 PR-1 上的 PR-2、兩者放同一個 release（避免 `engine.py` 審查面與 RA-1～RA-7 和 R-1～R-11 混在一起核）。
- **PR-4（N1）獨立，不得併入其他 PR**（任何時間點皆可，但需在 ADR-0022 PR 之後）。
- 否決「6-a＋6-b 同一個 PR」：diff 大、KA 與 KB 範圍穿插，R-6、R-IN-1 容易漏；理由含 ADR-0022 PR 曾因一個 PR 混多條 ADR 條文而漏列 D-d（tech-architect 所述）。
- 跨 PR 相依：PR-2 依賴 PR-1 的 `symbol_has_unvalued_lots`；若 PR-3 比 PR-2 晚上，PR-3 要補一格測試「own>0＋第 3 條（帳本不完整）violated → 只有擋下句、沒有 A-降級句」。`notional_caps` 第 3 條閘門在 PR-1 先鋪好（6A-03，行為中性），PR-3 才不會漏。

### 2. 單一判斷式（KC-2、KA-2、RA-2 的實作形式）

- 全 repo 唯一的兩個公開函式，皆在 `limits.py`（tech-architect 建議放在 `sector_numerator_gaps` 附近）：
  - `symbol_has_unvalued_lots(ctx) -> bool`＝own>0 判斷。`unvalued is None` 時回 `book_fully_valued is not True`（KC-5 退路），否則回 `own_lots > 0`。
  - `numerator_complete(ctx, limit_id) -> bool`＝KC-2，**涵蓋第 1～5 條**，分條列於同一函式內：第 1、4、5 條為 `not symbol_has_unvalued_lots(ctx)`；第 2 條為 `sector_numerator_gaps(ctx).complete()`；第 3 條為 `book_fully_valued is True`；未知 id 拋例外。
- 現有 `sector_numerator_gaps` 保留，作為第 2 條那一支。
- `engine.py` 的 (A) 與 `book.py` 的 `_symbol_direction` **只呼叫**這兩個函式，不得自行比較 `own_lots`（對應 KA-1 勘誤、6A-10）。
- `notional_caps` 第 1、4、5 條各自以 `numerator_complete` 把關；第 2 條閘門改成呼叫 `numerator_complete`（運算式等價）；第 3 條閘門**加上** `numerator_complete(ctx, "gross_exposure")` 並**保留** `!= "not_evaluable"`（見 Decision 2 勘誤）。
- D-d1／D-d2：**不保留分句版**，常數名稱不變、內容整句換成刪除版（見 KA-1 勘誤）；RC-2 digest 測試改成釘刪除版（見下 M3）。

### 3. 既有測試修改清單（只有以下可以改）

不在清單上的斷言變動一律 BLOCKING，退回 tech-architect，依 RF-5。以下表格與清單**逐字抄自**上列來源「既有測試修改清單」。

| # | PR | 檔案：行 | 改法 | 依據 |
|---|---|---|---|---|
| M1 | PR-1 | `tests/alerts_helpers.py` L135-155 | 兩個 fixture 各加 `book_fully_valued=True`，再加一句 docstring；斷言不改 | RF-1；Consequences 3(g) |
| M2 | PR-1 | `tests/test_advice_limits.py` L1721-1735 `_fractional_ctx` | 加 `book_fully_valued=True`。不加的話 L1760-1763 會失敗（退路下 `notional_caps` 為空），L1766-1780 會變成空過 | RF-5（風控點名；docstring 寫 "the entire book"） |
| M3 | PR-1 | `tests/test_adr0022_sector_unvalued.py` L688-709（RC-2） | 兩個 digest 改成刪除版，用審查檔第一段 D-d1／D-d2 列的字面另行獨立算出；docstring 的來源路徑和字數（87／103 → 66／83）一併更新。RC-1 的掃描（L1183-1189）和 L1203-1284 都以常數名引用，零修改 | R-6；ADR-0022 失效條件 2、D-d1 更正註記「6-a 連動」；ADR-0023 Decision 4 |
| M4 | PR-4 | `test_advice_book.py` L545／557／578 | 改成引用常數 | N1 核可 |
| — | PR-2／PR-3 | 無 | 新測試全部放新檔 | (A) GWT 3；R-7；6-b GWT 2／3 |

- **禁止修改**：
  - S-B2 (a)(b)(c) 和 RF-1 列出的 `test_alerts_engine.py` L227…768 的斷言；
  - D-a digest（L667-685）；
  - W1～W7、W-6m、W-6u 的 digest（L727-773）；
  - K-4、K-5、KD-2 測試（L900-1042）；
  - `test_book_context_call_sites.py`、`test_unusable_close_f1.py`；
  - `PortfolioContext.book_fully_valued` 的預設值；
  - `GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL`、2026-08-09 skipped 句、`engine.py:351` 既有句的字面；
  - `alerts/engine.py`、前端、`_book_level_check`、`_aggregate`。
- tech-architect 另載：已讀碼確認不受影響（不必改）的測試點為 `test_advice_limits.py` L522-533、L631-638；`test_api_advice.py` L201-214；`test_unusable_close_f1.py` L442-465；`test_adr0022` L404-421、L435-464；`test_alerts_snapshot.py` L440-451。該「受影響／不受影響」結論是讀碼推論，**待 dev-lead 跑完整套測試確認**；結果若與 M1～M4 清單不一致，一律退回。
- 上表測試檔行號（L135-155 等）為 tech-architect 所述，tech-writer 未驗證。

### 4. 前置 P-1～P-8（摘要）

| 代號 | 內容 | 負責／擋誰 | 備註（完成與否來源未載，以任務單後續回報為準） |
|---|---|---|---|
| P-1 | 第二十五輪 e2e 結束（RM-5、RU-9），ADR-0022 PR 合併；ADR-0022 L468「風控請 qa 以 diff 補驗的四項」要有結論 | — | — |
| P-2 | F-1 已 release；tech-architect 稱程式碼已有 `usable_price`（`book.py:1068`、`api/advice.py:179`），release 狀態請 devops-sre 確認 | devops-sre | — |
| P-3 | 釐清 W-a2 列「observed None」的意思。tech-architect 解讀：指 D-5（R-4 句型為「D-5 不附、observed None」），一般 violated 保留算出值（observed 規則：own>0 且 not_evaluable → None；own>0 的 D-5 → None；own>0 一般 violated → 仍為算出值；own=0 → 不變）。風控本意不同須於開工前更正 | 風控；**擋 PR-1** | **已回覆（風控審查檔第五段，2026-10-07）**：確認 tech-architect 解讀並更正審查檔第一段 W-a2 列（observed None 只指 D-5）；R-P3-1～3 完成即解除擋關。見 Decision 4 |
| P-4 | Decision 8-1 第 5 點 `BookContext.notes` 相容屬性傳 `gross_exposure_status=None`，與 R-IN-1、F-10(c)「None 只准用在 insufficient 分支」字面衝突。請風控確認這個僅供測試、production 已被兩道測試禁讀的用法可列白名單；否則須改掉 `test_advice_book.py` 等 19 處以上 `.notes` 用法 | 風控；**擋 PR-3** | **已回覆（風控審查檔第五段，2026-10-07）**：准列白名單，附 R-P4-1～R-P4-5；R-P4-1～4 完成即解除擋關。見 Decision 8-1 第 3、5 點、KD-2、F-10(c)。**R-P4-4 補強方案已由 tech-architect 出具（6-b 任務單「KD-2 補強規格」段，2026-10-07；摘要見 KD-2a～KD-2j）** |
| P-5 | R-11 與 6-a 裁定 (4) 的「violated 與『未參與計算』並列」在 own>0 下不可能出現（own>0 → `notional_caps` 必為空、區間為 None），e2e 應驗「卡上沒有區間」 | 風控／qa-e2e 知悉 | **已回覆（風控審查檔第五段，2026-10-07）**：確認 own>0 下並列不可能出現，R-11 改為 R-P5-1；並列情境移到 6-b（R-P5-2）；前提為第 3 條閘門「加上」（R-P5-3）。見 R-11 勘誤 |
| P-6 | ADR-0023 勘誤：KA-1 範圍補 `book.py` 兩處、Decision 2／KB-1「改為」→「加上」、行號對照、RF-5 對 `test_advice_engine.py` L88／369 的歸類（不擋開工） | tech-writer | **本次勘誤處理（見 KA-1、Decision 2、KB-1、KB-2、Decision 8、Decision 8-1、Consequences 3 各處〔2026-10-07 勘誤〕）** |
| P-7 | creative-lead 沒有待辦（字面全部已核可）。W-6m、W-6u、W6、W7 不受影響：6-a 不碰 `/limits`（候選標的依 rule 3 不會有自己的未估值批次 `book_limits.py:463-473`、book-level context 的 own 為 0 `book.py:1003`）；6-b 只動方向子句。qa 只需確認 digest 測試 L727-773 零修改 | creative-lead／qa | creative-lead 無待辦（來源所述） |
| P-8 | S-B2 字面不改，只核對條數（6A-19、6B-16）；落地後由風控做單項核對 | 風控 | — |

- **風控第五段對本節其他項的裁定**（風控審查檔第五段，2026-10-07）：
  - **M3**：**接受**，屬 R-6 字面替換的直接後果、不算「改測試讓它過」；字數 87→66、103→83（差 21／20＝被刪子句）風控已核對。附 **R-M3**：diff 只能改兩個 digest 字串和 docstring（來源路徑改為審查檔第一段 D-d1／D-d2 列，字數改為 66／83），測試名稱、斷言結構、常數名稱都不改；digest 要從審查檔表格字面獨立算出、不能從程式碼常數反算，qa 獨立重算兩個 digest 並確認相同；PR 說明附計算方式與字數差 21／20 的說明；RC-1 掃描（L1183-1189）與 D-a、W1～W7 等 digest 一律零修改。
  - **RF-4**：補 **R-RF4**（見 Consequences 3 (g) RF-4 之下）。
  - **6A-09 grep 精確度**：不能用子字串「低於上限的結果」或「建立在偏低的比率上」grep 分句版（`limits.py:359` 的 W3 與 `book.py:162` 的 `SECTOR_UNCLASSIFIED_NOTE` 是現行有效核可句，會誤判）；測試只比對被刪掉的那兩個完整子句。
  - **R-TR**：風控第五段由 coordinator 轉錄為審查檔，W-a2 列加更正註記並處理草稿 L85，PR-1 送 qa 前完成。
  - 風控第五段「下一步」：tech-architect 負責 R-P4-4 的 KD-2 靜態半邊補強方案（PR-3 範圍）；每個 PR 合併前由風控單項核對，RF-1～RF-6 或第五段 required 任一項沒做到即 VETO。

### 5. 合併閘門

- **PR-1 合併條件 C-1～C-5（風控審查檔第六段，2026-10-07，APPROVE 附條件；C-1～C-5 完成即可合併、不必回風控；任一未完成或 PR-1 早於 PR-0 合併即 VETO）**：
  - **C-1 合併順序**：依 R0-1，**PR-0 要先合併（或同一次合併）**；rebase 到 PR-0 之後，要拿掉 strict xfail 標記（`test_adr0023_own_unvalued.py` 內，風控所述 L420-434），讓測試正常通過，不得刪除或弱化。若 PR-1 帶著該標記合併，表示 PR-0 尚未合併，觸發 PR0-F6（回送風控，適用風控保留的書面否決紀錄）。suggested：xfail 加 `raises=AssertionError`。
  - **C-2 RF-4 衝突**：第 1 例改用 dev-lead 的不可達證據測試，補「對照組非空洞」前提斷言（見 Consequences 3(g) 更正）。
  - **C-3 ADR 更正**：tech-writer 更正本 ADR Consequences 3(b)(e)(f)(g) 與 RF-4、待確認表、Consequences 6 及風控裁定轉錄第 7 點（**已於 2026-10-07 落檔**，見各處〔2026-10-07 更正，風控第六段〕）。
  - **C-4 PR 說明更正**：6A-19 的 PR 說明要照更正後口徑改寫，不能再寫「any 規則未評估條數最多 +3」。
  - **C-5 RF-5 盤點**：qa 要逐處歸類，不能只看全套測試是否通過，結果寫進 RF-6 的 PR 說明。
  - 另（風控第六段）：**RF-1 的英文等義句 docstring 可接受**；6A-14 的「同一標的部分估值」端到端替身接受，條件是 PR 說明寫明「部分估值」的正式可達路徑只有 legacy 雙幣別（列管可達），「全部未估值」才是一般正式路徑（〔2026-10-08 加註，tech-architect 可達性評估：「只有 legacy 雙幣別」不精確，另有 US／USD 同標的一批 `opened_at` 留空的正式路徑，見 Decision 4 末加註；原文保留〕）；`test_adr0022_sector_unvalued.py:1288` docstring 宣稱的 `test_api_advice` T1 須隨 PR-0 存在，不存在就先改掉該句。

- **開工／合併共通**（PR-1、PR-3，tech-architect 所述）：第二十五輪 e2e 結束、ADR-0022 PR（66a88b3）視為可合併（KB-4；本 ADR §9）；F-1 已 release（且不與 F-1 同 PR，KC-6）；P-3（PR-1）／P-4（PR-3）風控已回覆。PR-1 分支從 `product/stock-desk`（含 66a88b3）開出。
- **CEO 表態 ADR-0023 accepted 前提 4（見狀態欄：CEO 未推翻 2026-10-07 各裁定，並知悉 (vii) M-1 高估方向、(viii) 降級／擋下原因只在預設收合的卡內可見；風控第五段另增補 (ix)(x)(xi)，見「被此決策約束的事」）為 PR-1／PR-3 的合併閘門**。此為 **tech-architect 建議、coordinator 採納，CEO 可推翻**。理由（tech-architect 所述）：程式碼會把這些裁定固定下來；開發本身可照 ADR-0022 先例在 proposed 狀態下開工。
- 每個 PR 走 qa-reviewer（含 Codex；環境不可用要註明）→ 風控單項核對（RF 任一項沒做到即 VETO）；PR 說明附本規格編號對照（6A-xx／A-xx／6B-xx）與 M1～M4。最後一個 PR 合併後跑 qa-e2e，涵蓋 R-11、RA-6、R-9。
- **待 CEO 決定**（來源「需 CEO 決定」2、3；tech-architect 建議如括號）：(A) 與 6-a 的包裝（分 PR 同一 release；若 6-a 先發、(A) 晚一個 release，CEO 知悉 (iii) 延到 (A) 落地才關閉）；6-a、(A)、6-b 是否放同一個 release（建議同一個，可合用一輪 e2e 涵蓋 R-11、RA-6、R-9）。F-3 觸發部署前置升級時，升級資料須附上 6-b（本 ADR §9）。

- **〔2026-10-08 落地加註（B 類轉錄；上列原文保留）〕PR-0／PR-1 結案狀態**：
  - **PR-1（6-a）已以 commit `be64f49` 進 `product/stock-desk`**（已 push）。審查：qa-reviewer PASS、風控 APPROVE 附條件；**Codex 第二意見未執行，環境不可用**；RF-4 第 1 例不可達改證據測試已獲風控接受。
  - **上線仍以 CEO 接受本 ADR 前提 4 為閘門（風控 RQ-1）**：commit 已進分支不等於可上線；CEO 若不接受前提 4，可單獨 revert `be64f49`，不影響 PR-0。
  - **PR-0 以 `9f5166e` 先行**（符合 R0-1「PR-0 不晚於 PR-1」；風控 RQ-1：PR-0 不受前提 4 閘門約束，PR-1 受）。**兩者拆為獨立 commit，以便單獨 revert。**
  - 其餘 PR 狀態：PR-2（(A) 降級句）、PR-3（6-b）依規格開工，仍受前提 4 閘門；PR-4（N1）本加註來源未載狀態，待查證（查法：看 `work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md` 後續結案紀錄）。
  - 來源：`work/dispatch/2026-10-07-任務單-6-a-決策卡第1與第5條在本標的有未估值批次時偏低.md` 檔尾「PR-1 結案紀錄（2026-10-08，coordinator）」；`work/dispatch/2026-10-07-任務單-PR-0-決策卡第4條ATR回填繞過book層撤下.md` 檔尾「結案紀錄（2026-10-08，coordinator）」。commit 雜湊為 coordinator 所述，tech-writer 未用 git 驗證（本次環境無法執行 git）。
  - **RF-4 第 1 例不可達改證據測試**：Consequences 3(g) 已反映（「〔2026-10-07 更正，風控第六段〕**第 1 例……在 production builder 下不可達……改由不可達證據測試取代**」及 RF-4 之下同名更正；3(b) 之更正載明不可達的理由）。**不需再加註。**

### 6. 本節未轉錄的部分

- PR-1 的逐項 required 表（6A-01～6A-21）、PR-2 表（A-01～A-07）與 PR-3 的 6B-xx 表，其內容在 6-a／6-b 任務單檔尾「tech-architect 實作規格」，**本 ADR 不重抄**，實作與 qa 以任務單為準；與本 ADR 衝突時依上述優先序（ADR-0023 為先）。

## 交接

- 〔2026-10-07 追加〕實作順序、PR 切分、既有測試修改清單 M1～M4 與合併閘門見上「落地」節；ADR-0023 勘誤（P-6）已落於各處〔2026-10-07 勘誤〕標注。
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
| 6-a 對 S-B2 條數的影響 | any 規則未評估條數增加（最多 +3）；只監看其一者由 quiet 變 skipped；不觸發 S-B2 失效條件 1～8 | Consequences 3（tech-architect 2026-10-07，風控讀碼經確認並增補） 〔2026-10-07 更正，風控第六段：「any 規則未評估條數增加（最多 +3）」口徑有誤，以 Consequences 3(b) 更正為準——own>0 且無 violated 時 any 規則一律 skipped；RF-4 第 1 例在 production builder 下不可達，PR-1 單項核對裁定改由不可達證據測試取代〕 |
| 第 2 條只有 unknown 的 passed 是否屬本通則範圍 | 是本通則明列例外：判定維持 passed，試算上屬分子不完整、依 KC-2 不得進 `notional_caps` | Decision 1 最後一點；ADR-0022 Decision 4 第一句（tech-architect 2026-10-07） |
| (A) 降級句字面待審 | 已採，降級句字面風控核可 | 風控審查檔第三段（2026-10-07）；Consequences 殘留 1 |
| 待風控確認 (1)：insufficient_data 分支維持 D-a（`gross_exposure_status=None`） | **accept**；required R-IN-1、R-IN-2；新失效條件 F-10 | 風控審查檔第四段（2026-10-07，HEAD d66183e）；Decision 8-1 第 3 點、KD-2、KD-5、重審與失效條件 |
| 待風控確認 (2)：6-a 退路使手刻 fixture 行為改變，alerts fixture 補 `book_fully_valued=True` | **accept**（屬「fixture 原意就是完整帳本的修正」）；附 RF-1～RF-6，任一未落實改判 VETO；RF-5 增列 `test_advice_limits.py:1729` `_fractional_ctx` | 風控審查檔第四段（2026-10-07）；Consequences 3 (g) |
| P-6 ADR-0023 勘誤（KA-1 補 `book.py` 兩處、Decision 2／KB-1「改為」→「加上」、行號對照、RF-5 歸類） | 已以〔2026-10-07 勘誤，tech-architect〕附加於各處，並新增「落地」節 | 6-a 任務單檔尾「tech-architect 實作規格」前置 P-6（2026-10-07） |
| 風控審查檔第一、二段轉錄不全（核可日、失效條件 2／3 更正、F-1～F-7、R-1～R-11、(vii)／(viii)、逐條意見） | 已補：狀態欄核可日表與剩餘前提、Decision 4／5／8 標注、「風控裁定轉錄」節、「重審與失效條件」F-1～F-10；ADR-0022 失效條件 2、3 同步更正 | coordinator 2026-10-07 指示（任務單原述「已先前落檔」不成立，tech-writer 核對時發現） |

**仍待處理**

- 前提 4（CEO 未推翻風控與 2026-10-07 各裁定，並知悉 (vii) M-1 高估方向、(viii) 降級／擋下原因只在預設收合的卡內可見）：待 CEO 表態。
- 已核可字面（W-a1／W-a2／W-b1／D-a3／D-d1、D-d2 刪除版／N1）的逐字內容不收於本 ADR（降級句除外），以風控審查檔第一段為準。

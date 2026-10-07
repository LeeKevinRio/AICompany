# ADR-0023：stock-desk 風險上限分子不完整時的非對稱判定通則

- 狀態：**proposed**
  - accepted 條件（須同時成立；來源：風控對 6-c 與 F-1b 的裁定「ADR-0023（proposed）同意」，2026-10-07）：**W-a1、W-a2、W-b1、D-a3、6-a 方向子句處置**皆經 risk-compliance-officer 逐字核可，**且** CEO 未推翻相關裁定。
  - 目前：上列字面**尚未核可**。依據：6-a 任務單狀態「待 creative-lead W-a1／W-a2／方向子句處置 → 風控 → ADR-0023 → dev-lead」；6-b 任務單狀態「待 W-b1／D-a3 → 風控 → ADR-0023 → dev-lead」（皆 2026-10-07 來源；tech-writer 未見其後的核可紀錄）。核可前不得實作字面、本 ADR 不得改為 accepted。
- 日期：2026-10-07（6-a／6-b 的 tech-architect 評估與風控裁定日）
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
  - 字面：本檔**不收錄任何字面**（W-a1、W-a2、W-b1、D-a3 與 6-a 方向子句處置皆待起草或待核可；核可字面以日後風控審查紀錄為準）。

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
- **第 5 條 D-5 分支**：own>0 時 **`observed` 改為 None**（風控 6-a 裁定 (3)，required）；該分支的 status／detail **不變**。（D-5 分支的判定內容，來源僅以此名稱稱呼，tech-writer 未讀 code 驗證，**待查證**：讀 `app/advice/limits.py` 第 5 條檢查函式。）
- required（風控 6-a 裁定 (3)）：前端 `formatPercent(null)` 顯示「—」；qa 確認警示 snapshot／event 對「violated 且 observed None」不出錯。
- 第 5 條在 own>0 的 not_evaluable 分支，`threshold` 仍為 allowed（tech-architect 所述）。
- 「第 2 條」的對應規則（同產業 same、W1／W2）由 ADR-0022 Decision 3 規定；第 2 條「只有 unknown 時 passed 附 W3」亦由 ADR-0022 規定。**該情形是否屬本通則「分子不完整」判定範圍，來源未明載**，以 ADR-0022 為準，待 tech-architect 確認。

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
- 三條**一律不進 `notional_caps`**（即使 violated）。
- W-a1／W-a2**不帶筆數**（卡片已有 `SYMBOL_UNVALUED_NOTE`；退路分支可共用同句）。
- W-a2 進推播（風控 required）：推播無 `SYMBOL_UNVALUED_NOTE`，W-a2 須自述「本標的有持倉無法估值、比率只用已估值部分、以已達上限處理」；同句用於 d1 與 d2，故**不得宣稱下限或「實際只會更高」**，無賣出指示或催促。
- 既有 skipped 句（「缺少可用資料」）延用到「分子不完整而排除」，**字面不改**（風控 6-a 裁定 (4)）；卡片可能並列「第 1 條 violated」與「未參與計算」，qa-e2e 375 抽驗。
- **required（6-a 同一包）**：own>0 時方向子句處置（ADR-0022 的 D-d1／D-d2 因第 1、4、5 條不再有 passed 而失去所指）由 creative-lead 提出，送風控逐字審。suggested：qa 確認警示 bare context 在 own>0 時不會走 `_inferred_sector_gap` 推成 no_position（`limits.py:871-873`）。

### 5. 6-b 適用：第 3 條（`book_fully_valued is not True`）

- A/N ≥ 上限 → **violated**，`observed`＝A/N，detail＝既有 violated 前句（`limits.py:969-970` 句構）＋ **W-b1** ＋ `_net_worth_disclosure`（原三句揭露 required 不變）；**未達上限 → 維持 `limits.py:957-963` 逐字不變**（`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` 字面不改）。
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
- **required 新增 D-a3**：方向子句變體，第 3 條帳本不完整下 violated 時使用，**明確排除第 3 條於「偏高」之外**；決策卡與 `/limits` 兩範圍，由 creative-lead 起草。**D-a 原句只在第 3 條 not_evaluable 時使用**，並與 2026-09-18 鎖定句逐位元組相同。（D-a3 在 ADR-0022 方向子句優先序中的位置，來源未載，**待查證**：待 creative-lead／風控提出優先序修訂。）
- **required：6-b 不得先於 ADR-0022 PR 落地**（風控 6-b 裁定 (4)）。tech-architect 評估原述「6-b 不依賴 ADR-0022 欄位，可先於 ADR-0022 落地」，風控裁定改為不得先於；以風控裁定為準。理由：不能讓「偏高」與 violated 並陳（CEO 知悉增補 (iv)）。

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
2. **F-1b（匯率 ≤ 0，medium，列入 CEO 知悉）**：`FxRate.rate` 無驗證器（`providers/fx.py:89`）、台銀解析取買賣中價無正值檢查（`:280-298`）、`valuation.py:393-417` 亦無（tech-architect 所述）；匯率＝0 時外幣持股以 ok 狀態市值 0 出現，總曝險與產業分子被低估而錯誤通過，與 F-1 D2 同型；匯率為負時 E 可能小於 A，破壞 ADR-0022 W1／D-d1「會偏低」前提（ADR-0022 失效條件 5）。**對本 ADR 的影響**：本 ADR 數學通則與 6-b 分子單調前提都依賴「市值非負」與「匯率 > 0 為經濟事實」，F-1b 使此前提在 code 上**沒有強制**。
   - 併入 F-1 的條件：dev-lead 尚未開工且只沿用既有 fx missing token 與字面；否則另開單排同一或下一 release。
   - **required**：F-3 腳本一併掃本機快取匯率 ≤ 0，查到則比照 F-1 升級部署前置；qa 確認本標的匯率 ≤ 0 時 `PortfolioContext.fx_to_twd gt=0` 不會讓卡片或 `/limits` 回 500。
3. **S-B2 條數變動**：6-b 使 any 規則「已超標且帳本不完整」由 mixed quiet 改 fired、**未評估條數少 1**（S-B2 只動條數、字面不變；6-b 評估所述）。6-a 對條數的影響來源未載，**待查證**：讀 `alerts/engine.py` 的 any 規則與 S-B2 審查檔。
4. **只監看 gross 規則由 skipped 變 fired**：只監看 gross_exposure 的規則在 6-b 條件下由 skipped 改 fired；W-b1 經 `alerts/engine.py:309-310` 進推播（組成 `{symbol} 觸發風險上限：{names}。{details}`，風控審查檔所述 `:310`）；風控接受，不觸發 S-B2 失效條件 6／8（6-b 裁定 (3)）。
5. **W-a2／W-b1 進推播**：誠實度與無操作指示限制適用（見 Decision 4、5）。W-b1 進推播時 6-b GWT 要求 fired 含 W-b1。
6. **卡片觀感**：violated 並列「未參與計算」於 375 寬是否讀得通，qa-e2e 抽驗。
7. **ADR-0022 的 D-d1／D-d2 與 D-a**：6-a／6-b 落地會使 ADR-0022 的 D-d1／D-d2、D-a 失去所指或被涵蓋（失效條件 1、2），須先有 D-a3 與 6-a 方向子句處置的核可字面。
8. **手刻 context 測試**預設 `book_fully_valued=None` 會走退路（tech-architect 所述）。

### 被此決策約束的事

- 6-a、6-b 皆排在 F-1 之後、ADR-0022 PR 之後；不作 F-1 部署前置。
- 6-a、6-b 的字面（W-a1、W-a2、W-b1、D-a3、6-a 方向子句處置）核可前不得實作。
- CEO 知悉增補（風控 2026-10-07）：(i) 曾核可的 D-d1 含數學錯誤、已更正；(ii) 風控修訂自身 FR-9 (a-附加)「一律 not_evaluable」為非對稱判定（更保守）；(iii) 6-a 修後殘留；(iv) 6-b 排在 ADR-0022 之後；(v) 6-c 採 C-1 的代價；(vi) F-1b。
- 列管彙總：own>0 加碼降級（medium，tech-architect）；F-1b（medium，dev-lead／devops-sre）；`SECTOR_UNCLASSIFIED_NOTE` 措辭（low，creative-lead，見 ADR-0022）。

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

- **KB-1**：範圍＝`limits.py` `_check_gross_exposure`、`notional_caps` 閘門、新常數 W-b1、註解／docstring、測試；**不動** `book.py` 邏輯、`book_limits.py`、`alerts/engine.py`、前端。
- **KB-2**：`GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` **字面不改**，只改英文註解（`limits.py:328-331`）、`book.py` 模組 docstring 規則 3（L28-31）、欄位註解 L641-643（tech-architect 所述行號）。
- **KB-3**：`/limits` 第 3 條經 `_book_level_check`（`book_limits.py:315-341`）原樣 violated（不改 `book_limits.py`）。
- **KB-4**：不得先於 ADR-0022 PR 落地。

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
- ADR-0022 失效條件 2（6-a 改變第 1、5 條對本標的批次處理）：本 ADR 的 6-a 即屬此條；須有 6-a 方向子句處置核可字面。
- ADR-0022 失效條件 5（允許零或負市值、或總資產可能小於產業市值）：與 F-1b 直接相關；數學通則的「市值非負」前提不成立時須重審本 ADR。
- 6-a 的「D 方案」（第 4 條改用全部股數）暫不採；日後採用須另案評估。
- 任何修改 FR-9 (a-附加) 的風控裁定，須回頭核對 Decision 7。

## 交接

- 字面：creative-lead 起草 W-a1、W-a2、6-a 方向子句處置、W-b1、D-a3 → risk-compliance-officer 逐字審；全部核可且 CEO 未推翻後，本 ADR 才可改 accepted。
- 實作：dev-lead（F-1 之後、ADR-0022 PR 之後）→ qa-reviewer → 風控單項核對；qa-e2e 375／1280。
- 另案：own>0 加碼降級（tech-architect）；F-1b（dev-lead／devops-sre；F-3 腳本掃匯率 ≤ 0）。
- 待查證：D-5 分支判定內容；D-a3 在方向子句優先序的位置；6-a 對 S-B2 條數的影響；第 2 條只有 unknown 的 passed 是否屬本通則範圍。

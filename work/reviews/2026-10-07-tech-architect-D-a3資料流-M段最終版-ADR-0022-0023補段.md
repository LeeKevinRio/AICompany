# tech-architect 補段：D-a3 資料流與優先序、ADR-0022 試算排除確認、6-a 對 S-B2 條數、M 段最終版（2026-10-07）

- 角色：tech-architect（唯讀）；讀碼基準 `product/stock-desk` HEAD f25c90d；coordinator 原文轉錄，未改內容。
- 用途：tech-writer 落檔 ADR-0022／ADR-0023 的依據（第一段→ADR-0023 Decision 8-1；第二段→ADR-0023 Decision 1 改寫；第三段→ADR-0023 Consequences 3；第四段→ADR-0022 Decision 1 補充段）。
- **注意**：第四段 M-4「固定排序（實作以 `sorted()` 對產業名稱字串排序）」已被風控同日第三段裁定取代：排序鍵為 `TWSE_SECTORS` 索引（不在表內者排最後再依字碼），W-6m 字面已核可修正版，「W-6m 字面未核可前不得合併」條件已滿足；tech-writer 落檔時以 `work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第三段為準。
- 「建議送風控確認的兩點」（insufficient_data 分支維持 D-a；fixture 補 `book_fully_valued=True`）由 coordinator 另送風控，結果補在檔尾。

---

## 評估摘要

讀碼基準是 `product/stock-desk` HEAD `f25c90d`。全程唯讀，沒有改任何檔案。

1. **D-a3 資料流**：選 P1「延後組裝」。
   - `_book_level_notes` 新增 keyword-only 參數 `gross_exposure_status: LimitStatus | None`，不給預設值。
   - notes 一律在上限評估完成之後才組。決策卡讀 `card["limits_check"]` 裡的第 3 條；`/limits` 讀 `_book_level_check` 的輸出。
   - 否決三個方案：呼叫兩次建構函式（P2）、在呼叫端用字串把 D-a 換成 D-a3（P3）、在 book.py 用淨值和門檻重算（P4）。
   - 讀碼新發現：ADR-0022 PR 為了 `/limits` 的「回報產業 Y」，本來就必須在評估後才組 notes。所以 finalizer 應該在 ADR-0022 PR 就建好，6-b 只需要加參數。
   - 這會修訂 ADR-0023 KB-1／KB-3「不動 book.py 邏輯、book_limits.py」的範圍。
2. **ADR-0022 確認**：已涵蓋，不必補 ADR-0022 條文。出處是 **Decision 4** 第一句，不是 Decision 3。Decision 3 只規定判定（passed 附 W3），試算排除寫在 Decision 4。另有驗收 2 與 K-3 佐證。ADR-0023 Decision 1 的「待確認」那一句仍需改寫，補文附在下方。
3. **6-a 對 S-B2 條數的影響**：風控讀碼正確，我補三點。
   - any 規則也可能從 quiet 變成 skipped。
   - `_limit_cause` 的 FX 尾句不會出現新情境。
   - **測試面有衝突**：`tests/alerts_helpers.py` 的 `compliant_context`／`breaching_context` 沒有設定 `book_fully_valued`（預設 `None`）。6-a 的退路會把它當成 own>0，`test_alerts_engine.py:462-471`（S-B2 例 (b)）會從 quiet 變成 skipped。處理方式是 fixture 補上 `book_fully_valued=True`，斷言不改，但必須明列。
4. **M 段最終版**：已依風控裁定整合，全文在第四段。

## 方案比較（D-a3 資料流）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **P1 延後組裝（採用）**：`_book_level_notes` 加參數；book.py 新增公開 finalizer；評估後才組 notes | 選句只在一處；讀的是同一回應實際送出的 status；不重算；grep 可以檢查 | `BookContext` 介面要擴充；要改兩個呼叫端的組裝順序 | 呼叫端漏接 finalizer：靠「app/ 不得讀 `BookContext.notes`」的 grep 加上 R-5 負向測試擋住 |
| P2 建構函式加參數，呼叫端建兩次 | `BookContext` 不變 | 同一回應建兩次 context；第一次的 notes 仍含未定版 D-a，可能被誤用 | 兩次參數不一致時會靜默出錯 |
| P3 呼叫端字串替換 D-a→D-a3 | 改動最小 | 違反 K-8（改寫已核可字面），選句散在各處 | 否決 |
| P4 book.py 用淨值、門檻自行判斷 | 不用動呼叫端 | 違反風控第二節 4(a) | 否決 |

## 決策（四段可直接貼入的文字）

### 第一段：ADR-0023 新增 Decision 8-1「D-a3 資料流、組裝順序與優先序」（建議接在 Decision 8 之後）

```
#### 8-1. D-a3 資料流、組裝順序與優先序（tech-architect 2026-10-07，HEAD f25c90d 唯讀讀碼；風控 accepted 前提 3）

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
4. **組裝順序（兩個範圍相同）**：①建 context（`build_book_context`／`build_book_level_context`）→ ②評估上限（決策卡：`build_advice` 內的 `evaluate_limits`；`/limits`：baseline、`_aggregate`、`_book_level_check` 全部完成）→ ③以②的實際 status 組 notes → ④組 response。決策卡維持 `[*_book_freshness_notes(summary), *notes]` 的順序（風控 A-6）。
5. **實作形狀**：
   - `BookContext` 保留組 notes 所需的輸入。book.py 新增公開純函式（暫名 `book_notes(book, *, gross_exposure_status)`），回傳 `[*_book_level_notes(...), *個股層 notes]`，順序與現行 `book.notes` 相同。
   - `BookContext.notes` 保留作相容用，定義為 `book_notes(book, gross_exposure_status=None)` 的結果，既有測試因此零修改。但 production code（`app/`）不得再讀 `BookContext.notes`，insufficient_data 分支也改為明寫 `gross_exposure_status=None`。
   - `/limits` 的 D-P 判定需要「回報產業 Y」，Y 要到 `_aggregate` 之後才知道，所以 ADR-0022 PR 本來就必須在評估後才組 `/limits` notes。架構要求 ADR-0022 PR 就建立上述 finalizer，並讓兩個範圍都經過它。6-b 只加 `gross_exposure_status` 參數與 D-a3 常數，並調整 `api/advice.py` 的組裝順序。
6. **優先序（只在原選 D-a 處替換；D-P／D-d1／D-d2 不動）**：
   - 決策卡：(1) `own_lots > 0` → D-d1／D-d2（刪除版）；(2) X 為 None 且 own=0 → 第 3 條 violated 用 D-a3，否則 D-a；(3) same 或 unknown > 0 → D-P；(4) 其餘 → 第 3 條 violated 用 D-a3，否則 D-a。
   - `/limits`：(1) 帳本有任何 unknown，或回報產業 Y 有 same（依 ADR-0022 M-3／M-5）→ D-P；(2) 第 2 條無任何可比較產業（Y 未定義）→ 第 3 條 violated 用 D-a3，否則 D-a；(3) 其餘 → 第 3 條 violated 用 D-a3，否則 D-a。
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
- 殘留：insufficient_data 分支維持 D-a。該分支沒有任何上限數字，前端只渲染不足面板（風控 A-8），不擴大既有語意。

**可檢查約束（qa）**
- KD-1：grep D-a3 常數，只出現在 `_book_level_notes` 與測試。
- KD-2：`app/` 內讀 `BookContext.notes` 的次數為 0；兩個回應組裝點都經過 finalizer，並明示 `gross_exposure_status`。
- KD-3：book.py 不出現 `RiskBudget`、`max_gross_exposure`、`_breaches`、`_check_gross_exposure`。
- KD-4：第 3 條 status 的查找不帶預設值（不得有 `next(..., None)` 這類寫法）。
- KD-5：R-5 負向測試範圍＝兩個範圍 × live／cache_only × 兩則 note 並存 × 優先序各分支（決策卡 a0、a、b、c、d1、d2；`/limits` 的 Y 未定義、Y 有 same、有 unknown、其餘）× 第 3 條 status（violated、not_evaluable 的各成因）。只有「原選 D-a 且 violated」得到 D-a3；D-P／D-d1／D-d2 分支在 violated 時逐字不變。
- KD-6：參數化測試證明帳本不完整時第 3 條 status 只有 violated 或 not_evaluable（淨值 None／過期／新鮮 × A/N 高於、低於門檻）。
```

### 第二段：ADR-0022 確認（unknown-only 不進 `notional_caps`）

結論是**已涵蓋**，條文如下：
- **ADR-0022 Decision 4 第一句**：「same 或 unknown > 0 時，第 2 條**不放進** `notional_caps`」。unknown-only（same＝0、unknown＞0）就落在這一句。注意這是 Decision 4，不是 Decision 3。Decision 3 第三點只規定判定「same = 0 且 unknown > 0：violated 不變；passed 附 W3」，沒有提到試算。
- 佐證：驗收 2「只有產業未知（三子類參數化）→ passed detail 以 W3 結尾、violated 不變、`notional_caps` 不含」；K-3 單一判斷式。
- 現行程式碼閘門在 `limits.py:1223-1225`。目前只看 `sector is not None`，所以 ADR-0022 PR 必須依 Decision 4 收緊。

ADR-0022 不用補文。ADR-0023 Decision 1 的最後一點仍寫「待 tech-architect 確認」，請改為下文：

```
- 「第 2 條」的對應規則（same、W1／W2）由 ADR-0022 Decision 3 規定。**第 2 條只有 unknown（same＝0、unknown＞0）時 passed 附 W3，是本通則明列的例外**：判定上維持 passed（風控 2026-10-07 不採加強版，見 ADR-0022 Consequences 4）；**試算上屬分子不完整，依 KC-2 不得進 `notional_caps`**。此點 ADR-0022 Decision 4 第一句已規定（unknown＞0 即排除），本 ADR 不另立條文（tech-architect 2026-10-07 確認）。
  - 第 2 條「分子不完整」的判斷式：same（`own_lots + same_sector_lots`，X 不為 None 時）＞0，或 unknown＞0，或已估值未分類持股存在（C-1）。只有 other 時分子完整（算出值偏高），仍可進 `notional_caps`。X 為 None 時第 2 條沒有比率，本來就不進（`limits.py:1223` 閘門）。
  - 因此 own>0 時，第 2 條無論在哪個分支都不進 `notional_caps`，與第 1、4、5 條一致（R-8）。上述條件與第 1、3、4、5 條的條件同屬 KC-2 全 repo 單一判斷式，各條件分列於同一函式。
```

（選填，非必要）若要讓 ADR-0022 自身更好查，可在 Decision 4 第一句後加一句：「此含 unknown-only 且第 2 條 passed（附 W3）的情形；判定上為 ADR-0023 非對稱通則的明列例外，試算上屬分子不完整（ADR-0023 KC-2）。」

### 第三段：ADR-0023 Consequences 3 改寫（6-a 對 S-B2 條數的影響）

```
3. **S-B2 條數變動**（依 `alerts/engine.py:271-322` `_limit_outcome` 讀碼，HEAD f25c90d；風控讀碼經 tech-architect 確認並增補）
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
```

### 第四段：ADR-0022 Decision 1 補充段（M-1～M-5 最終版全文）

```
#### Decision 1 補充：mixed 群組的歸類（M-1～M-5）

（tech-architect 2026-10-07 擬，HEAD f25c90d 對照；風控 2026-10-07 裁定，見 `work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md` 第二段 B。本段取代 Decision 1「待補：`/limits` 彙總對 mixed 的同等規則」那一條。）

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
- categories(G) 為空（unknown）→ 續用 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`。
- mixed 且至少一個產業在比較中 → 續用 `SECTOR_UNVALUED_EXCLUSION_SUFFIX`。
- **mixed 且沒有任何產業在比較中（含 comparable 為空）→ W-6m 新字面，與 C′、W6 同一 PR**（風控裁定採 (i)，不准續用現行句：現行句「可能屬於已納入比較的產業」在此情境為假，comparable 為空時更無所指）。
- W-6m 字面約束：
  - 比照 W6 句構。
  - 列出該群組 categories(G) 的全部產業，用固定排序（實作以 `sorted()` 對產業名稱字串排序，測試釘住），不用「等」、不截斷。
  - 寫明這些產業本次沒有任何持倉納入比較。
  - 必須包含「未納入比較不代表這些產業未超過上限」。
  - 不寫「屬於」單一產業，不帶任何指引。
- 流程：creative-lead 起草 → risk-compliance-officer 逐字審。**W-6m 字面未經風控逐字核可前，本 ADR 的 PR 不得合併。**

**M-5**：`/limits` 方向子句中的「回報產業 Y 有 same」依 M-3 判定，未估值 mixed 群組的 categories 含 Y 就算（→ D-P）。D-a 位置的 D-a3 替換見 ADR-0023 Decision 8-1。

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
- 失效條件 4 對 M-1／M-3 以外的再變更仍然有效（ADR-0023 F-7）。

**測試**
- T-1：mixed 全已估值時，分子含整檔，且同時計入其每一個產業。
- T-2：只透過 mixed 標的持有的產業不被比較。
- T-3：[半導體, None] 兩筆皆已估值時兩筆都計入。
- T-4：未估值 mixed 的各排除句情境，含 W-6m 與 comparable 為空。
- T-5：同產業兩個候選者的 check 完全相同。
- T-6：不加總、不平均（見 M-1 required）。
- 既有 `test_advice_book_limits`（L155／174／190／201／214／422／454）與 `test_advice_book`（L535／548／581／590）的斷言零修改，L454 只改註解。
```

## 對實作的約束（摘要，逐條可檢查）

1. 第一段的 KD-1～KD-6。
2. 第三段 (g)：兩個 alerts fixture 補 `book_fully_valued=True`，斷言零修改，並在 PR 說明中明列。
3. ADR-0022 PR 建立 notes finalizer，`/limits` 經它組裝；6-b 只加參數。
4. W-6m 字面未核可前，ADR-0022 PR 不得合併。
5. 「不加總、不平均各產業比率或分子」用 grep 加測試釘住。

## 交接與需要知道的事

- 交接：第一段、第三段、ADR-0023 Decision 1 改寫段，以及第四段 M 段 → tech-writer 落檔。約束 → dev-lead。第三段 (g) 與 KD-5 → qa-reviewer。
- **建議送風控確認的兩點**（皆不在原裁定範圍）：
  - insufficient_data 分支維持 D-a（`gross_exposure_status=None`）。
  - 6-a 的退路會改變手刻 fixture 的行為，S-B2 迴歸測試必須靠補 fixture 才能維持斷言零修改。
- 引用到的路徑：
  - /home/user/AICompany/docs/adr/0023-stock-desk-風險上限分子不完整時的非對稱判定通則.md
  - /home/user/AICompany/docs/adr/0022-stock-desk-單一產業佔比上限在同產業或產業未知持股無法估值時的判定.md
  - /home/user/AICompany/work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md
  - /home/user/AICompany/work/reviews/2026-10-07-S-B2-風險上限any規則-未評估揭露-字面-風控審查.md
  - /home/user/AICompany/apps/stock-desk/backend/app/advice/book.py
  - /home/user/AICompany/apps/stock-desk/backend/app/advice/book_limits.py
  - /home/user/AICompany/apps/stock-desk/backend/app/api/advice.py
  - /home/user/AICompany/apps/stock-desk/backend/app/advice/engine.py
  - /home/user/AICompany/apps/stock-desk/backend/app/advice/limits.py
  - /home/user/AICompany/apps/stock-desk/backend/app/alerts/engine.py
  - /home/user/AICompany/apps/stock-desk/backend/app/alerts/snapshot.py
  - /home/user/AICompany/apps/stock-desk/backend/tests/alerts_helpers.py
  - /home/user/AICompany/apps/stock-desk/backend/tests/test_alerts_engine.py
- 補充：dispatch 單（`work/dispatch/2026-10-07-任務單-產業上限對同產業未估值持股的判定與揭露.md` L126-136）只轉錄了 M 段的摘要，沒有前次全文。第四段是依該摘要加上風控裁定重寫的完整版。

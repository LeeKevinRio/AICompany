# ADR-0027 r3 修訂提案 A-54～A-86（含 r2 套用讀法確認；取代 A-54～A-79 版，tech-architect）

- 審查者：tech-architect（唯讀）；基準 commit 9ba01d6
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 r3 修訂提案（A-54～A-86，含 r2 套用讀法確認）：tech-architect（唯讀）

這份報告取代我先前送出的版本。新增的內容有三處：第六節「r2 套用讀法確認」、A-80～A-86 七條更正條文，以及第一、三、四節隨之更新。A-54～A-79 的實質內容和先前一致，只有 A-79 補了一點。我沒有改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有跑程式、測試或 git。

## 一、結論

**共 33 條（A-54～A-86），可以直接交 tech-writer 套用。** 方向：22 條收緊、10 條不變、1 條「有條件放寬，同時收緊」（A-68）。沒有任何一條放寬已核可的風險上限。

**基準。** 條文以 commit 9ba01d6（r2'＋r2'' 已套用）的 ADR 為準，位置用 D-／FL- 條號標示，不用行號。

**coordinator 的兩次更新都已處理：**
- 暫定大盤 bar（風控 r3 確認第四節 R-4 第 1～4 點）寫成 A-75～A-78，定位是「ADR-0027 核可前 required」，**不再標「待確認」**。
- tech-writer 的 3 項「無法套用」、8 項「需確認的讀法」、外部參照是否自足化，以及 ADR-0028 的 A-38～A-40，逐項答覆見第六節。需要更正的部分寫成 A-80～A-86。

**要點：**
1. **風控第六批 TA-6 問「symbol scope 的 `gated` 是否純依樣本數」：答案是否。** 現行來源還有：
   - ADR-0025 D-6.6 的回放審查；
   - CEO #10 (b) 的影子試跑；
   - PRD 記載的風控建議（上線 ≥10 日，而且每個 horizon 至少 1 筆結算）。

   所以 LM-98 要靠新的 `gate` 原因列舉守門（A-57）。
2. **A-27 (a)～(c) 的清單列需要單列狀態片段。** 這是 B-8 的遺漏，已列出語意交 creative-lead（A-63）。
3. **R2（作廢列結算後可否顯示 label）和 r2'' A-36 第 4 點的 fail-closed 互相牽動，我沒有自行裁決**（A-62）。
4. **D_v 前要核可的東西又多了幾項**：S3 的「優於基準」伴隨揭露、清單狀態片段、「已結算＋實際結果」片段、R2 的確認。
5. **G-7 我多收緊了一步**：on-demand 也要 G-1～G-6 全部成立（A-72）。ADR 評估摘要第 6 點原本就寫「不得寫入任何前瞻紀錄」，現行的 G-7 反而和它不一致，A-72 也順帶消除了這個矛盾。
6. **R-4 第 4 點採「消費端加定案下限」。** 根本修法會動到 `pit_snapshot`，屬於 ADR-0012（accepted）的修訂，要 CEO 核可（A-78）。
7. **tech-writer 的讀法大多正確**：11 項確認、7 項需更正。需更正的有：
   - `fail_normal`／`fail_w` 沒有定義；
   - D-12 (v) 舊表述和 FL-32 衝突；
   - G-2 機器部分的細節漏帶；
   - 「七道閘門」的殘留敘述；
   - ADR-0028 漏帶「不設執行期旗標」；
   - 外部參照要自足化；
   - 小節編號。

   L964 的「七條底線」指的是 F-2 的風控底線 1～7，和閘門無關，不必改。

## 二、逐條條文（A-54 起）

### 甲、`surface_not_permitted`（第六批第四節 tech-architect 第 1 點）

**A-54｜D-11.4 第 6 點「`reasons` 的字面對應」：`surface_not_permitted` 子項（整項取代現行「R5-06 依否決方向重送、核可之前，沒有可用的片段，D_v 會被擋住」）**
- 方向：收緊。
- 依據：第六批 §三 LM-94、LM-95；§四 第 1 點 S1、S2、S4。
> - `surface_not_permitted` 依守門對應兩個片段，由後端在產生 plan 時選定：
>   - **S4 選擇規則**：`OutlookView.validation_status = better_than_baseline` → LM-95；其餘三態 → LM-94。
>   - **S1 判定來源**：`OutlookView` 新增欄位 `validation_status`（四態之一），和 `display_state` 取自同一列 T 日 snapshot（FL-54 (e)）。plan 端不得另外讀 snapshot。
>   - **S1 留存**：`plan_record.outlook_display_state[h]` 新增 `validation_status` 與 `reason_fragment_id`。所有 unavailable 原因都要記；只增不改。`reasons_json` 只能用 `reason_fragment_id` 查表渲染，前端與 API 不得重新推斷。
>   - **S2 範圍**：LM-94、LM-95 只在 `scope_kind = symbol` 成立。`REASON_FRAGMENTS[surface_not_permitted]` 的守門含 `scope_kind == symbol`，其他 scope 沒有項目。v0 之後若依第 8 點引用其他 scope，要先有該 scope 的核可片段，否則 FL-52 (c) 失敗。
>   - 任何使用者文件、說明頁、tooltip、API 欄位說明，都不得說明 LM-94 和 LM-95 的差別。

**A-55｜FL-52 新增 (e)～(g)**
- 方向：收緊。
- 依據：第六批 §四 第 1 點 S3、S4。
> - (e) **S3**：四態中的每一態 s，(symbol, symbol_detail) 都要列在 `SURFACE_PERMISSIONS`，而且 `required_disclosures(symbol, symbol_detail, s)` 全部核可。這包括 `better_than_baseline` 時的 D-2 開盤基準句，以及 D-4 的區間、n、期間片段。任何一態不成立，FL-52 就失敗。
> - (f) **「只在」斷言**：除了 `symbol_detail`、`api`，(symbol, 任何其他 surface) 都不得列入。任何一格要開放，LM-94、LM-95 都要先重送。
> - (g) **S4 窮舉表**：`surface_not_permitted` × 四態 × `scope_kind`，每個組合恰好選出一個片段（symbol × BTB → LM-95；symbol × 其餘 → LM-94；非 symbol 沒有項目）。另外斷言 v0 的引用範圍 ⊆ {symbol}。
> - 不得 skip；效力鏈同 FL-45 (c)。

**A-56｜D-11.4 第 6 點：其餘七個原因值與 `pending_triggers`（取代現行「其餘七個值：…同一批送審」）**
- 方向：收緊（補上守門）。
- 依據：第六批 §三 LM-96～LM-103 的條件欄；§二 PD-b。
> - 對應：
>   - `suspended_f3` → LM-96；
>   - `withdrawn_f2` → LM-97（三個 `withdraw_reason` 共用）；
>   - `gated` → LM-98（守門見 A-57）；
>   - `before_dv` → LM-99；
>   - `late` → LM-100（有 R_s 而且 `late=1`）；
>   - `insufficient` → LM-101（有 R_s、`late=0`、PV-4 第四態）；
>   - `voided` → LM-102（觸發時記 WARNING）。
> - LM-96～LM-98 的守門含 `scope_kind == symbol`。
> - LM-99～LM-102 的 `{MM/DD}` 一律取 `data_as_of`（T），套年份規則。
> - LM-99 的「紀錄起算日」要和 LM-84、LM-85、LM-111 一起定案；改詞就要重送。
> - **`pending_triggers`**：`availability = unavailable`，而且 5 日展望條件出現在 `pending_triggers` 時，一律渲染 LM-103（Condition 依 A-70），不得顯示「等待中」；LM-103 和 LM-86 同時出現。
>   - D-11.4 第 7 點與待決事項中的「恢復前這條條件無法成立」，改為引用 LM-103。
> - 不設 `PLAN_PENDING_OUTLOOK_SUSPENDED_OR_WITHDRAWN`。

**A-57｜D-11.4 第 12 點 (iv)：`display_reasons_json` 加 `gate`；LM-98 守門**
- 方向：收緊。
- 依據：第六批 §四 第 6 點；LM-98 的條件欄；ADR-0025 D-6.6；決策包 #10；PRD L33、L548、L624。
> - (iv) 結構改為 `{suspend: [...], withdraw: {...}|null, gate: [...]|null}`。
>   - `gate` 是封閉列舉，可以多值，固定排序。`display_state = gated` 時非空，其他狀態為 null。
>   - v1 候選值：`forward_n_below_min`、`replay_review_pending`、`shadow_run_pending`、`settlement_smoke_pending`。
>   - 實際啟用哪些值，由 #10 的裁示當參數注入；沒有啟用的值不得出現。
> - **LM-98 守門**：`scope_kind == symbol`，而且 `gate == [forward_n_below_min]`。其他組合沒有核可片段，FL-52 (c) 失敗（列入 A-63 第 5 項）。
> - FL-53 加 (f)：每個 `gate` 值各一個 fixture；多值時不得選到 LM-98。

### 乙、FL-45 (b)（第六批第四節第 2 點）

**A-58｜FL-45 (b) 改寫；D-12「逐檢查點判定」第 5、6 點連帶修改**
- 方向：斷言本身不變，只是改成和已核可字面一致；(b3)、(b4) 是收緊。
- 依據：第六批 §三 LM-104；§四 第 2 點。
> - 第 5 點：`LM79_WITHDRAW_REASON_FRAGMENTS` 改為 `LM79_WITHDRAW_REASON_RENDER: Mapping[withdraw_reason, (template_id, reason_fragment_id | None)]`：
>   - `f2_invalid_stop` → (LM-79, LM-75)；
>   - `f2_deadline` → (LM-79, LM-74)；
>   - `f2_invalid_stop_worst_case` → **(LM-104, None)**。LM-87 是 LM-104 核可全文的一部分，不是代入 LM-79 的片段。
> - 第 6 點改為：「已由 LM-104 滿足（第六批 R6-04）」。
> - **FL-45 (b) 新文**：LM-79、LM-81、LM-104 只從各自的對照表取值，另加四項斷言：
>   - (b1) LM-87 不得代入 LM-79 的 `（{下架原因}）`；
>   - (b2) worst_case 只用 LM-104，而且只在前一版 `withdraw_reason = f2_invalid_stop_worst_case` 時使用；
>   - (b3) LM-104 的兩處 `{X}` 都取 `withdrawn_at_n`（用不同的 n 做 fixture）；
>   - (b4) LM-104 內嵌的 LM-87 逐字完整。
> - LM-79 的原有條件同樣適用 LM-104。qa-e2e 在 375 寬度驗收。

### 丙、紀錄清單（第六批第四節第 3～5 點；r2'' 另案第 3、4 點）

**A-59｜D-11.1 用詞定義**
- 方向：不變。
- 依據：第六批 §四 第 5 點。
> - 「主統計」指 E 的成員資格；「n」指在 E 內、依 §4.1 不重疊規則計得的筆數。作廢列不計入 n，但計入 W。證據不足列依 §4.1 與 LM-91 第 5 條（quant 書面確認）。兩個詞不得混用。
> - LM-14、LM-37、LM-80 與 D-7.6、D-7.8 的「不計入主統計」都屬實，不改；LM-38 要重送成「不計入 n」。E 的定義不變。

**A-60｜D-11.4 第 11 點 (f)：不變式與取列範圍**
- 方向：收緊。
- 依據：第六批 §四 第 3 點。
> - **不變式**：清單每一列，`in_eligible_set = false` 若且唯若 `exclusion_reasons` 非空。
> - E 另有兩個條件沒有對應的 exclusion 值，處理方式是這兩類列**不回傳**：
>   - 更正列：清單只回傳 `forecast_record.supersedes_id IS NULL` 的原始列；結算端取更正鏈的最後一筆。
>   - 重放列：清單不讀 `forecast_replay`。`forecast_record` 加 insert trigger，要求 `claim_id` 的 registry `kind` 是 forward；`forecast_replay` 反過來，只收 replay。
>   - 若要列示更正列或重放列，要先擴充列舉並送審。
> - **FL-58**：
>   - (a) 不變式的性質測試；
>   - (b) 不回傳更正列與重放列；
>   - (c) insert trigger 拒絕 replay claim；
>   - (d) `in_eligible_set` 和 validation 呼叫同一個 E 函式（FL-49）。

**A-61｜D-11.4 第 11 點 (f) 之後：字面對應；FL-52 (d) 擴充**
- 方向：收緊。
- 依據：第六批 §三 LM-107～LM-114；§五 第 1、2 點。
> - **`in_eligible_set = true`**：
>   - 一般列 → LM-107；
>   - 證據不足列（`label = insufficient`）→ LM-108；
>   - 作廢列（最新 outcome 的 `status` 為 `unresolvable_missing_data` 或 `excluded_corporate_action`）→ LM-109；
>   - 兩者同時成立時選 LM-109。
> - **`in_eligible_set = false`**：用 LM-110，`{原因}` 只取以下四個：
>   - `before_dv` → LM-111；
>   - `late` → LM-112（只用於排程列）；
>   - `on_demand` → LM-113；
>   - `pit_violation_confirmed` → LM-114（只用於有事件的列）。
>   - 多個原因全部列出：`pit_violation_confirmed` 排第一，其餘照列舉順序，以「；」分隔；不得截斷，也不得寫「等」。
> - **上畫面的前提**：
>   - LM-107～LM-110：LM-84 核可，而且驗證狀態頁已上線；
>   - LM-108：另需 quant 書面確認 LM-91 第 5 條；
>   - LM-109：LM-38 重送核可之前不得上線；在那之前，有作廢列的清單不得渲染任何 `in_eligible_set` 字面；
>   - 最壞情境的結果必須真的渲染。
> - 不再使用 `counts_in_primary` 系列的常數名。
> - **FL-52 (d) 擴充**：`in_eligible_set` × {一般, 證據不足, 作廢}，以及 `exclusion_reasons` 的每個值，窮舉表都恰好選出一個片段。qa-e2e 在 375 寬度驗收 LM-114。

**A-62｜D-11.4 第 11 點 (d)、(d′) 之後：LM-105、LM-106 的守門 R1、R2**
- 方向：收緊。
- 依據：第六批 §四 第 4 點。
> - (d) → LM-105；(d′) → LM-106（紀錄清單與 POST 共用同一個 ID）。依 A-27 的順序，先成立的規則決定用哪一句。
> - **R1**：(b)、(c) 排在 (d)、(d′) 之前，所以 `gated` claim 的列在結構上選不到這兩句。FL-58 加 (e)：選中 LM-105 或 LM-106 的列，所屬 claim 當下的 `display_state ≠ gated`。
> - **R2**：
>   - 建議：作廢列結算後，用 `settled_record` 呈現原本的 label，加上作廢原因片段，標示「已作廢」，不附實際結果。
>   - **這要風控書面確認**，而且同一個決定也適用 A-36 第 4 點的 on-demand 作廢列。
>   - 確認前採 fail-closed，不顯示 label。這時 LM-105、LM-106 對最後作廢的列不實，FL-52 (d) 判失敗。

**A-63｜A-27 (a)～(c) 的單列狀態片段：需要，列為 B-8 遺漏**
- 方向：收緊。
- 依據：第六批 §四 第 4 點；AC-C4-3。
- 理由：沒有 label、也沒有說明的列等於留白。LM-96～LM-98 的核可條件是「接 LM-86」，主詞又限定個股，不能直接拿來用在清單上。
> - A-27 (a)～(c) 成立的列，`status_fragment_id` 必填，不得留白。
> - 交 creative-lead 起草的語意（大盤、族群、個股要各自有主詞）：
>   1. 已下架，結算後列示；
>   2. 暫停顯示，結算後列示；
>   3. 大盤或個股 `gated`、未結算：結算後列示；
>   4. 族群 `gated`：未達 150 前不顯示方向（n／150），不得暗示之後一定會開放；
>   5. A-57 中 `gate` 不只樣本數一項時，用來取代 LM-98 的片段。
> - 核可之前，FL-52 (d) 失敗。

**A-64｜D-11.4 第 11 點新增 (g)：封閉 schema 推廣**
- 方向：收緊。
- 依據：r2'' 第四節第 3 點。
> - 以下所有不顯示 label 的回應列，一律用同一個封閉 schema `MaskedRecordView`（`extra="forbid"`）：A-27 (a)、(b)、(c)、(d)、(d′)；POST 回傳的 `late=1` 排程紀錄；FL-34 下架期間的紀錄回應。
> - **白名單**：A-36 第 1 點 (b) 的清單；排程列用 `late` 取代 `window_started`；`settled` 依實際值；(c) 已結算列可以加 `settlement_date`、`outcome_status`。
> - **不得出現**：
>   - `label`、`range_basis`、天氣、色彩代碼、方向詞、`invalidations_json`、`evidence_json`、`baseline_predictions_json`；
>   - (c) 另外不得出現 `realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`。
> - 白名單要增列欄位，須修訂本點並送風控。
> - **FL-59**：每一種狀態各一組 schema 驗證、全文掃描、標籤互換後逐位相同。

**A-65｜D-11.4 第 11 點新增 (h)：結算後形式推廣到排程紀錄**
- 方向：收緊。
- 依據：r2'' 第四節第 4 點。
> - 已結算、可以顯示 label 的排程列：label 只放在 `settled_record`（和 A-36 第 4 點共用 schema `SettledRecordView`），同一物件帶 `settlement_date` 與結算結果；頂層沒有 `label`；不得當作目前展望呈現。
> - 「已結算＋實際結果」片段的範圍擴及排程紀錄。核可之前不顯示 label，而且這個片段列入 FL-52 (d)。
> - 作廢 outcome 依 A-62 R2。
> - FL-59 加兩個 fixture：resolved 一個、作廢一個。

### 丁、顯示面（顯示面確認第四節第 1～5 點）

**A-66｜D-11.4 第 9 點第 1 點：`first_layer` 改為封閉清單，雙重歸屬取聯集**
- 方向：收緊。
- 依據：顯示面確認 §二 (c)；§四 第 1 點。
> - **`first_layer` 共六項**：
>   1. 市場總覽的天氣區塊；
>   2. 「最需要處理」清單；
>   3. 首頁警示列（同時屬於 `alert`）；
>   4. 族群列表；
>   5. 族群詳細頁；
>   6. 市場總覽的大盤紀錄清單展開區。
> - 市場總覽上的持倉表、摘要卡、風險儀表沒有歸屬（fail-closed）。不在清單內的頁面或元件，一律沒有歸屬。
> - `symbol_detail` ＝ `/position/[symbol]` 整頁。
> - **單一來源**：`PAGE_SURFACES`，前後端共用。元件的 consumer ＝ 它所屬各 surface 的聯集；端點的 `SERVES` 必須 ⊇ 呼叫它的所有元件的 surface 聯集。
> - 適用 AC-S-7、PA-9／PV-40。
> - 2a 的「不在 D-20 列舉內的頁面…（附件 B'-2）」改為「不在本點清單內的頁面或元件」。
> - **FL-60**：
>   - (a) 前端 route／元件列舉；
>   - (b) `SERVES` 涵蓋呼叫它的元件；
>   - (c) `PAGE_SURFACES` 和本點清單逐項相同。

**A-67｜D-11.4 第 9 點：第 2 點初版、第 5 點改寫**
- 方向：收緊。
- 依據：顯示面確認「`SURFACE_PERMISSIONS` v1」；§四 第 2 點。
> - 取代第 2 點中「大盤…族群…個股…（見附件 B-3）」三個子項。
> - **v1 列入的格子恰好六個**：(market, first_layer)、(market, api)、(sector, first_layer)、(sector, api)、(symbol, symbol_detail)、(symbol, api)。其餘一律不列入。
> - **(symbol, first_layer) 在程式碼裡不列入，不得寫成條件格。** 開放路徑只寫在 ADR 文字：優於基準、揭露全部核可、升 `policy_version`、送風控，而且 LM-94、LM-95 要重送。
> - 第 5 點改為：「v1 期間不論驗證狀態為何，個股展望對政策表一律是 `surface_not_permitted`。」
> - FL-54 (d) 加兩項斷言：鍵的集合和六格逐項相同；格子的值不得是 callable。

**A-68｜D-11.4 第 9 點第 4 點：`PLAN_OUTPUT_SURFACES` 初版**
- 方向：**展望可用性放寬（有條件，v1 實效不變）；輸出面收緊。**
- 依據：顯示面確認 §二 (a)；§三。
> - **初版 ＝ {first_layer, symbol_detail, api}。**
> - 適用欄位：`position_action`、`reasons`、`pending_triggers`、`add_conditions`、`entry_conditions`、`outlook_refs`；「最需要處理」的排序與成員、`plan_record` 顯示欄位、API 回應適用同一集合。
> - **`alert`、`export` 移出的前提**：渲染、觸發時機、計數 N 都不依賴這些欄位（A-69）。
> - **登記**：quant 在 v0.10 照實登記方向，在 D_v 前、本 ADR 核可前完成。
> - **加回路徑**：先加回集合、升 `policy_version`、送風控，而且要早於渲染上線。
> - 不得以「plan 實際沒在首頁渲染」為理由移出 `first_layer`。

**A-69｜FL-54 新增 (h)；FL-43 保留提醒 payload 的斷言**
- 方向：收緊。
- 依據：顯示面確認 §二 (a) required 第 2 點。
> - **(h1)**：`app.alerts.*` 與 `EXPORT_MODULES` 不可達 `app.plan.*`，也不讀 `plan_record`。
> - **(h2)**：任意變動 A-68 的適用欄位之後，下列各項逐位相同：提醒 payload、是否觸發與觸發時間、N、匯出檔內容。
> - FL-43 對提醒 payload 的斷言**保留**。D_v 前落地。

**A-70｜D-11.4 第 7 點加上 None 規則；FL-43 擴充**
- 方向：收緊。
- 依據：顯示面確認「D-19 缺口」。
> - **None 規則**：每一種 unavailable 原因下（含 `surface_not_permitted`），凡是評估時用到展望的 `Condition`，`status = unavailable`，`observed`、`threshold` 必為 None。
> - 範圍包括 ADR-0025 D-4.4 的趨勢條件、D-4.5 的 `consider`／`avoid` 展望項，以及持有模式序位 7。
> - 每個 Condition 都宣告 `uses_outlook: bool`，沒有預設值，由 loader 驗證。複合條件整條變成 unavailable。
> - **FL-43 擴充**：
>   - (i) 每一種原因 × 每個 `uses_outlook` 條件，`observed`、`threshold` 都是 None；
>   - (ii) 標籤互換的輸出清單加入 `add_conditions`、`entry_conditions`、`quantity_range`；fixture 要含 `add_conditional`、`consider` 兩條路徑。

**A-71｜D-1、D-7.8 第 8 點、D-11.4 第 11 點：紀錄清單依 scope 拆成三個端點**
- 方向：收緊。
- 依據：顯示面確認 §二 (d)；§四 第 5 點。
> - 三個端點：
>   - `GET /api/forecast/records/market`：`SERVES={first_layer}`；
>   - `/sectors/{sector_key}`：`SERVES={first_layer}`；
>   - `/symbols/{symbol}`：`SERVES={symbol_detail}`。
> - 每個端點只回傳自己的 scope；不設總端點；不採「依參數決定 SERVES」。
> - A-27 與 A-60～A-65 一體適用。不得預設排除作廢列或逾時列。
> - D-7.8 第 8 點與 FL-52b (9) 的「紀錄清單」改指 symbol 端點。D-11.4 第 11 點小標「`GET /api/forecast/records` 同樣經過本閘門」改為「紀錄清單端點同樣經過本閘門」。

### 戊、r2'' 另案

**A-72｜D-14 G-7 改成肯定句**
- 方向：收緊。
- 依據：r2'' 第四節第 1 點；ADR 評估摘要第 6 點（「不得寫入任何前瞻紀錄」）。
> - **G-7 新文**：「on-demand 紀錄的寫入，同樣要 G-1～G-6 全部成立。強制方式和排程紀錄相同（A-33）。on-demand 的寫入路徑和排程呼叫同一個閘門函式。on-demand 紀錄一律不屬於 E。」
> - D-14 首段末句「G-7 是 on-demand 的說明，不是排程紀錄的閘門」改為「G-7 是 on-demand 寫入的閘門」。FL-38 加一項：on-demand 路徑在 G-3、G-4 不成立時拒絕寫入。
> - **只改句型、不改實質的版本（不建議）**：「on-demand 受 G-6 約束；G-1～G-5 不約束 on-demand。」

**A-73｜D-7.8 第 8 點：on-demand 去重**
- 方向：收緊（補上原本沒有的定義）。
- 依據：r2'' 第四節第 2 點。
> - 同一個 (symbol, horizon, T, definition_version, rules_version)，on-demand 原始列只寫一筆（M-6 的唯一索引已含 `trigger`）。
> - POST 的處理依序是：有排程紀錄 → 回傳排程紀錄；否則有既有的 on-demand 列 → 回傳既有列，`window_started` 讀已存值；否則寫一筆。並發撞到 UNIQUE 時重讀，不回 5xx。
> - FL-52b 加 (10)：同 T 重查時回傳同一個 `forecast_id`；兩個並發請求只產生一列。

**A-74｜FL-16 的範圍用 `ENDPOINT_SURFACES` 列舉**
- 方向：收緊。
- 依據：r2'' 第四節第 5 點。
> - `ENDPOINT_SURFACES` 每一項加 `kind ∈ {current_outlook, plan, record_list, on_demand}`，沒有預設值；沒有登記 kind 的 route，測試失敗。
> - **FL-16 新文**：`late=1` 與 on-demand 紀錄，永遠不會出現在 `current_outlook`、`plan` 兩類端點；`outlook_refs` 不得指向它們。`record_list` 依 D-11.4 第 11 點；`on_demand` 依 D-7.8 第 8 點與 A-36。
> - FL-54 (g) 隨之擴充。

### 己、暫定的大盤 bar（風控 r3 確認第四節 R-4；ADR-0027 核可前 required）

**A-75｜D-7.3 決策日 T（整點取代）**
- 方向：收緊。
- 依據：R-4 第 1 點。
> - **候選 T** ＝ 市場 DB 中最新一個有 ok bars run 的 session。候選 T 必須同時滿足：(i) A-78 的 run 下限；(ii) 大盤 T 日 bar 是定案列。
> - **`is_final_bar`** 只有一個定義，放在 `app/data/session_calendar.py`，引用 ADR-0028 CS-17 與 R-1：
>   - `final_after(TW, T) ≤ min(as_of, fetched_at) ≤ now`；
>   - 帶時區；
>   - 非示範資料；
>   - 沒有 `OHLC_INVALID`。
> - **(ii) 不成立時**：經 `app.services.index` 強制重抓一次（寫入仍經 `service.py`）；仍不成立，或 (i) 不成立 → 該 session 記 `inputs_not_ready`；**不得退回更早的 session，也不得使用暫定值。**
> - `app.services.index` 新增逐列回傳 `as_of`、`fetched_at`、`source` 的方法〔事實：`cache.py:109` 現行只帶最舊的 `fetched_at`〕。FL-5 不變。
> - `forecast_input_series.bars_json` 每一列都帶這三欄，並納入雜湊。
> - **FL-61**：(a)～(e)，包含「`as_of` 14:59:58、`fetched_at` 15:00:01」的 fixture，以及「不退回前一 session」。

**A-76｜D-4 新增第 8 點：快取 bar 消費者的封閉列舉**
- 方向：收緊。
- 依據：R-4 第 2 點。
> - **`CACHE_BAR_CONSUMERS`**：
>   1. D-7.3 的大盤 T 日 bar；
>   2. D-4.5 的大盤輸入序列；
>   3. D-9.2 的大盤結算路徑；
>   4. FL-25 的估值價格；
>   5. `plan_outcome` 的觸價價格（另案定義時歸入）。
> - 每一項只能經 `is_final_bar` 篩選後取得。不符合的列視為缺，依各自的既有規則處理。新增消費者要先修訂本點。
> - **FL-62**：呼叫點 ⊆ 列舉；每一項各一個暫定列 fixture。
> - quant 確認這些是否屬於事先宣告的 PIT 輸入；若是，登記為補定義（收緊），D_v 前完成。

**A-77｜D-8.1 觀察日（整點取代）**
- 方向：收緊。
- 依據：R-4 第 3 點。
> - 觀察日 ＝ (i) 聯集 (ii)：
>   - (i) 有 ok bars run、而且該 run 的 `recorded_at ≥ final_after(TW, session)` 的 session；
>   - (ii) 大盤有定案列（排除示範資料）的日期。
> - 不用週一至週五推定。平日既不是觀察日、也不是官方休市日時，記 WARNING。
> - FL-19 加三個 fixture：示範列、暫定列、定案前的 run。

**A-78｜市場 DB 啟動過早的 capture**
- 方向：收緊。
- 依據：R-4 第 4 點。
> - **消費端防護**：對 session s 的 bars，只認 `recorded_at ≥ final_after(TW, s)` 的 ok run 寫入的 bars。適用 D-4.1 PIT 視圖、D-7.3 (i)、D-8.1 (i)、D-9.2 個股與族群成員結算。
> - D-4.1「與 `panel._visible` 位元相同」改為「在 `panel._visible` 之上加定案下限」。不改 `pit_snapshot`。
> - **FL-63「交易日 10:00 啟動」fixture**：期望 D 記 `inputs_not_ready`、D 經 (ii) 成為觀察日（所以會留下缺日列）、10:00 的 bars 不進入任何 PIT 輸入或結算窗。
> - **後果**：之後若沒有定案後的 run 補寫，約 60 個交易日內的紀錄可能是證據不足，或作廢。
> - **根本修法**屬於 ADR-0012 修訂，要 CEO 核可；data-engineer 先查證。

### 庚、收尾

**A-79｜檔頭、與既有 ADR 的關係、Consequences、待決事項、修訂紀錄**
- 方向：不變。
> - 檔頭加「r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-54～A-86」。
> - 與既有 ADR 的關係補兩點：ADR-0028（引用 CS-17、R-1）；ADR-0012（不修訂；A-78 的根本修法另案）。
> - **Consequences**：
>   - 「D-20 的兩面後果」第一子點的「個股展望在『優於基準』之前」改為「v1 期間不論驗證狀態」（配合 A-67）；
>   - 另外新增四點：D_v 前字面增加；交易時段開機的影響；`inputs_not_ready` 的影響；紀錄清單拆成三個端點。
> - 待決事項依第四節更新。
> - 修訂紀錄：被取代的原文逐字保留，其餘各條註明「新增，無被取代原文」。

### 辛、r2 套用的更正（第六節的更正條文）

**A-80｜D-12「逐檢查點判定」第 1 點補上符號定義；補第 2 點的指引行**
- 方向：不變（補回 r2 A-23 已有的定義）。
> - 第 1 點，`fail(c) = …` 之前加：
>   - 「`fail_normal(c)`：一般情境下，模型點估計在共同子集上 ≤ 任一必備基準；
>   - `fail_w(c)`：W 情境下做同一個比較；
>   - 兩者都讀該檢查點 `eval_kind=checkpoint` 列的 `stats_json`，不另外計算。」
> - 第 1 點與第 3 點之間補一行：「2. **原因值與優先序**：見上方『下架原因列舉值』。」這樣編號才連續，A-58 引用的「第 5、6 點」也維持有效。

**A-81｜D-12 共同部分 (v) 改寫**
- 方向：不變（意思一致，消除和 FL-32 的衝突）。
> - 原文：「作廢率 >5% 時，判定取一般情境與 W 之中比較差的那個（底線 3）。」
> - 新文：「(v) 作廢率 >5% 時（底線 3），依『逐檢查點判定』第 1 點的公式逐檢查點套用 W；本 ADR 不另寫第二種表述（FL-32）。」

**A-82｜D-14：補回 G-2 機器部分的細節（r2 A-33，r2' 沒有取代）**
- 方向：不變（恢復 r2 的已審條文）。
> - 在「recorder 執行期強制」一點之後，加一段「G-2 的機器部分」：
>   - `f2_variant: Literal["F2-A", "F2-B"]`，沒有預設值，屬於 `definition_logic_sha256` 的範圍（承接 FL-37）；
>   - `c8_decision_ref` 是 repo 相對路徑；`c8_decision_sha256`；
>   - 缺任何一欄，dirdef 就無法凍結；
>   - recorder 執行時不讀 `docs/`、`work/`；
>   - 這份紀錄是不是 CEO 本人的決定、內容與 `f2_variant` 是否一致，由 qa 核對。
> - tech-writer 加的連接語「各閘門內容（風控第 1 項、底線 7、R-116）：」保留。

**A-83｜「七道閘門」的殘留敘述；評估摘要第 6 點**
- 方向：不變（用詞更正，和 A-33、A-72 一致）。
> - 評估摘要「最大代價」第一點、Consequences 第一點、待決 CEO 第 5 點的「七道閘門」，一律改為「六道閘門（G-1～G-6；on-demand 依 G-7 同樣適用）」。
> - 評估摘要第 6 點補上 G-6，改為：「ADR-0027 核可、C-8 定案、定義凍結、08:30 查證、ADR-0026 的守門與備份、`app/forecast/**` 通過 qa-reviewer 與 Codex，全部完成之前，不得寫入任何前瞻紀錄（含 on-demand）。」
> - 待決「風控」段的「七條底線」指 F-2 的風控底線 1～7，**不改**。

**A-84｜ADR-0028 CS-12：補回「不設執行期旗標」**
- 方向：不變（恢復 r2 A-38「切換方式」的原意；r2' 整條取代時漏帶）。
> - 在 CS-12 observed 子項之後加：「這一列的翻轉只能以 PR 修改對應表與測試落地，不設執行期旗標，也不得用設定值切換。」

**A-85｜外部參照自足化（逐處替換；只動參照，不動實質）**
- 方向：不變。
- 原則：
  - ADR 本文不引用提案檔的「附件 X」編號；
  - 要引用審查依據時，寫出檔案路徑；
  - 「刪除」「改名」這類指令只放在修訂紀錄。
> - D-4 第 7 點「狀態」的「見附件 B-7」→「由 quant 登記（見待決事項 quant）」。
> - D-7.8 第 8 點「風控附件 B 確認 B-3」→「`work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md` B-3」。
> - D-7.8 第 8 點第 2 子點「逐字字面由 creative-lead 起草（…正在風控逐字審）…」→「逐字字面為 LM-106（`work/reviews/2026-10-17-新定位第六批字面逐字審-LM94至LM115-風控.md`）；守門 R1、R2 見 D-11.4 第 11 點」。**狀態更新**：片段已核可，剩 R2 待確認。
> - D-9.3「指數序列見附件 B-6」→「指數序列是否套用分割門檻由 quant 登記（建議只套用個股與族群成員）」。
> - D-11.4 第 6 點刪除「NS-a 刪除。」一行（保留在修訂紀錄）。
> - D-11.4 第 11 點 (f) 刪除「（r2 叫 `counts_in_primary`，改名）」（保留在修訂紀錄）。
> - D-11.4 第 9 點 2a 的「PRD L561、L590」→「PRD AV-13 與 NP-A1／NP-A2 列」，因為 PRD 行號已經漂移。
> - 「附件 B-3」「附件 B'-2」由 A-67、A-66 取代。
> - 待決 creative-lead 段的「依風控附件 B 確認的 B-8 完整清單」→ 寫出上列風控 r2 確認檔的路徑。
> - 待決 PM 段的「未列舉頁面的歸屬（附件 B'-2）」→「已決：D-11.4 第 9 點第 1 點（A-66）」。
> - 修訂紀錄中說明「附件 B-x 指提案檔編號」的那一行保留。

**A-86｜編號整理（只改形式）**
- 方向：不變。
> - FL-52b 原本六種情形編為 (1)～(6)，性質測試不編號。
> - FL-53 前兩點編為 (a)、(b)。
> - 表格以外的 `|S_T|` 不必跳脫。

## 三、方向統計

| 方向 | 條數 | 條號 |
|---|---|---|
| 收緊 | 22 | A-54～A-57、A-60～A-67、A-69～A-78 |
| 不變 | 10 | A-58（b3、b4 是收緊）、A-59、A-79～A-86 |
| 放寬（有條件，v1 實效不變）＋收緊 | 1 | A-68 |

## 四、衝突與待確認（我沒有自行裁決）

- **C-1｜D_v 要等的東西變多**：A-55 (e) 要求「優於基準」狀態的伴隨揭露先核可，否則 D_v 不能開始，即使優於基準預期是好幾年後的事。A-62、A-63、A-65 也一樣卡在 D_v 前。
- **C-2｜風控**：顯示面確認 (e) 第 1 點的並列揭露，LM-94 加上 LM-86 是否已經滿足。
- **C-3｜風控，R2**：作廢列結算後可否顯示 label。這和 A-36 第 4 點的 fail-closed 相牽動。
- **C-4｜風控**：族群可能因為 PIT 違規列被移出 E，n 降回 150 以下而重新變成 `gated`。這時先前已經顯示過「結算後列示」的列會變得不實，請判斷這個殘餘風險能不能接受。
- **C-5｜我自己提案的修改**：A-57 改了 r2' A-28 (iv)「結構固定」；A-78 改了 D-4.1「位元相同」。兩處都要在修訂紀錄中保留原文，不牴觸任何 accepted ADR。
- **C-6｜CEO #10**：決定 A-57 要啟用哪些 `gate` 值；還沒回覆時，A-63 第 5 項要先起草。
- **C-7｜風控**：A-66 的「市場總覽」不包含持倉表、摘要卡、風險儀表。如果你的本意是整頁都算，請指正。
- **C-8｜PM、風控知悉**：A-72 讓臨時查詢也要等全部閘門成立；A-73 讓 08:30 前產生的紀錄在白天照常顯示 label。
- **C-9｜PM**：A-68 的前提是 AC-S-3「N 不依 plan 欄位計數」，以及 NP-A3 第 (5) 項的修訂。
- **C-10｜quant**：起算日用語；LM-91 第 5 條；v0.10 的 D-20 ① 與 None 規則；A-76 的補定義；趨勢條件要不要拆成兩條。
- **C-11｜data-engineer**：A-75 的重抓路徑（`judge()` 在 15:00 後不重抓是轉引，我沒有重讀）；A-78 的查證。
- **確認沒有衝突的部分**：
  - A-54～A-86 都沒有改動 E，不觸發 LM-84 的重送；
  - A-75～A-78 和風控 R-1 一致；
  - R1 由 A-27 的既有順序在結構上保證；
  - A-80～A-86 只補回已審條文或更正用詞，不涉及新的風險取捨。

## 五、需 CEO 知悉事項（白話）

1. 第一版上線期間，個股的 5 日方向一律不拿來算行動建議，即使哪天證明「優於基準」也一樣。要開放，得另外送審。
2. 開始正式記錄預測之前要先核可的文字又多了幾句，包括一些很多年後才會用到的說明，開始記錄的時間可能再往後延。
3. 主機如果在交易日白天才開機，當天可能完全沒有預測紀錄，之後一段時間的紀錄也可能被判成證據不足。根本修法要改 ADR-0012（已核可），屆時會請你核可。
4. 大盤資料必須是收盤定案後才抓到的才能用。重抓失敗的日子會照實記成缺日，不會用暫定值頂替。

## 六、r2 套用讀法確認（逐項回覆 tech-writer 回報第 4 節）

### 6.1 無法套用的 3 項

| # | 項目 | 回覆 |
|---|---|---|
| 1 | R''-6 的附件 B'-1 表 | **確認**。ADR 內沒有對應位置，結論已寫在 D-7.8，記在修訂紀錄即可。 |
| 2 | r2' A-34 的兩處引用改寫 | **確認不改本文**。本文寫「事先宣告 §2.1」這種條號就好，不改成行號（行號會漂移）。修訂紀錄中的 A-34 條目保留。 |
| 3 | 附件 B'-2～B'-5 不在 ADR 內 | **確認**。本文殘留的參照由 A-85 自足化；B'-2 由 A-66 定案。 |

### 6.2 需確認的 8 項讀法

| # | 項目 | 回覆 |
|---|---|---|
| 1a | A-23：只替換兩行，保留 `f2_deadline` 行與 L616-618；第 2 點併入列舉 | **確認** |
| 1b | `fail_normal`／`fail_w` 沒有定義 | **需更正 → A-80**（另補一行第 2 點的指引，讓編號連續） |
| 1c | D-12 (v) 舊表述和 FL-32 衝突 | **需更正 → A-81** |
| 2 | A-35：保留 r2 的兩點，再接 r2'' 的 on-demand 一點 | **確認**。r2'' 的「整條取代」只取代 r2' 加的那一點。第一點的措辭隨 A-67 調整（A-79）。 |
| 3 | A-28：「F-3 恢復後若 F-2 仍下架就顯示下架」已無此句 | **確認**。(v) 的逐筆重新彙整，加上 FL-53 第一、二點，已經完整涵蓋，不必補回。 |
| 4a | A-33：出處標註移到 G 清單前，並加連接語 | **確認** |
| 4b | A-33：`f2_variant` 等細節沒有帶過來 | **需更正 → A-82**。r2' 只取代 D-14 首句，G-2 機器部分的細節應該照 r2 保留。 |
| 4c | 「七道閘門」的殘留敘述 | **需更正 → A-83**。L964 的「七條底線」指 F-2 底線 1～7，不改。 |
| 5a | A-26：保留 r2 的「`api` 這一格在 `shown` 時許可…」 | **確認**。這正是我的本意。同一點的初版子項由 A-67 取代。 |
| 5b | A-26 2a 引用的 PRD 行號（L561 與 L575 不一致） | **需更正 → A-85**，改用 PRD 的條號。 |
| 6 | A-39 CS-12：r2' 的新句作為子項拼接 | **確認** |
| 6′ | r2 A-38「不設執行期旗標」在 r2' 整條取代時漏帶 | **需更正 → A-84** |
| 7a | A-25：「命名理由」沒有帶入 | **確認**。命名理由不是規範性內容，放在修訂紀錄即可。 |
| 7b | A-25：刪除指令沒有寫進條文；保留「plan 讀不到 `voided`」一行 | **確認** |
| 7c | A-25：「NS-a 刪除」這種指令句留在本文 | **需更正 → A-85** |
| 8a | A-40：用提案原話組成一行 | **確認** |
| 8b | A-36：實際插入 r2 的三點，開頭的引導句不寫進條文 | **確認** |
| — | 外部參照是否自足化 | **要自足化 → A-85**（原則見該條） |
| — | 位置由 tech-writer 裁量的 6 項 | **全部確認** |
| — | 小處：FL-52b、FL-53 的編號；`\|S_T\|` 的跳脫 | **A-86** 只做形式整理；表格外不必跳脫 |

### 6.3 ADR-0028（A-38～A-40）

| 項目 | 回覆 |
|---|---|
| A-38 的 D-5 兩列與表後三點 | **確認**。表後三點之後會由 r3 A-48 改寫，「附件 B'-3」那一點屆時換成「依 D-9（r3）」。「不設執行期旗標」補在 CS-12（A-84）。 |
| A-39 的 CS-11、CS-12、CS-15 (b) | **確認**（CS-12 另加 A-84）。 |
| A-40 待決事項三處（L240、L241、L247） | **確認** |

**相關檔案**
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（9ba01d6；D-11.4 L482-581、D-12 L595-635、D-14 L699-714、Consequences L759-777、FL-38～FL-54 L851-920）
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md（D-5 L131-150、CS-11～CS-15 L197-208、待決 L238-247）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028套用r2prime與r2雙撇-tech-writer回報.md（第 4 節）
- /home/user/AICompany/work/reviews/2026-10-17-新定位第六批字面逐字審-LM94至LM115-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-顯示面配置初版單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md（§四 R-1、R-4）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r2雙撇A36增補-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028修訂提案r3觀察日來源-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案A22至A41-tech-architect.md（r2 A-23、A-33、A-38 原文）
- /home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md（D-4 L256-315、D-6.6 L412-414）

這是唯讀的架構文件，Codex 不適用。

# ADR-0027 r3 修訂提案 A-54～A-79（tech-architect）

- 審查者：tech-architect（唯讀）；以 r2→r2'→r2'' 依序套用後的提案文字為基準
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 r3 修訂提案（A-54～A-79）：tech-architect（唯讀）

我沒有改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有跑程式、測試或 git。

## 一、結論

**共 26 條（A-54～A-79），可以直接交 tech-writer 套用。** 方向：22 條收緊、3 條不變、1 條「有條件放寬，同時收緊」（A-68）。沒有任何一條放寬已核可的風險上限。

**基準。** 磁碟上的 ADR-0027 現在還是 r1，本文沒有 `SURFACE_PERMISSIONS`、D-20 等內容。所以我的條文是以「r2 → r2' → r2'' 依序套用後」的提案文字為準，位置用 D-／FL- 條號標示，不用行號。

**coordinator 中途的更新已經併入。** 第 4 項（暫定的大盤 bar）依風控 r3 單項確認第四節 R-4 第 1～4 點，寫成 A-75～A-78，**不再標「待確認」**，定位是「ADR-0027 核可前 required」。

**六個要點：**
1. **風控第六批 TA-6 問「symbol scope 的 `gated` 是否純依樣本數」：答案是否。** 現行來源包括 ADR-0025 D-6.6 的回放審查、CEO #10 (b) 的影子試跑、PRD 記載的風控建議（上線 ≥10 日，而且每個 horizon 至少 1 筆結算）、AC-A2D-1b (ii) 的 n／30。所以 LM-98 要靠新的 `gate` 原因列舉守門（A-57）。
2. **A-27 (a)～(c) 的清單列需要單列狀態片段。** 這是 B-8 的遺漏，已列出語意交 creative-lead（A-63）。
3. **R2（作廢列結算後可否顯示 label）和 r2'' A-36 第 4 點的 fail-closed 互相牽動，我沒有自行裁決。** 我建議顯示，但要風控書面確認（A-62、第四節 C-3）。
4. **D_v 前要核可的東西又多了幾項**：
   - S3 要求「優於基準」狀態的伴隨揭露先核可；
   - 清單狀態片段；
   - 「已結算＋實際結果」片段；
   - R2 的確認。
5. **G-7 改寫時我多收緊了一步**：on-demand 也要 G-1～G-6 全部成立，不只是改成肯定句。只改句型、不改實質的版本也一併附上（A-72）。
6. **R-4 第 4 點我採「消費端加定案下限」。** 根本修法會動到 `pit_snapshot`，屬於 ADR-0012（accepted）的修訂，要 CEO 核可（A-78）。

## 二、逐條條文（A-54 起）

### 甲、`surface_not_permitted`（第六批第四節 tech-architect 第 1 點）

**A-54｜D-11.4 第 6 點「`reasons` 的字面對應」：`surface_not_permitted` 子項（整項取代 r2' A-25 該子項）**
- 方向：收緊。R5-06 解除否決後，補上已核可的片段與守門。
- 依據：第六批 §三 LM-94、LM-95；§四 tech-architect 第 1 點 S1、S2、S4。
> - `surface_not_permitted` 依守門對應兩個片段，由後端在產生 plan 時選定：
>   - **S4 選擇規則**：`OutlookView.validation_status = better_than_baseline` → LM-95；其餘三態 → LM-94。
>   - **S1 判定來源**：`OutlookView` 新增欄位 `validation_status`（四態之一），和 `display_state` 取自同一列 T 日 snapshot（FL-54 (e)，`outlook_view` 只讀一次 snapshot 列）。plan 端不得另外讀 snapshot。
>   - **S1 留存**：`plan_record.outlook_display_state[h]` 新增 `validation_status` 與 `reason_fragment_id`。所有 unavailable 原因都要記，不只這個值；同一次 run 寫入，只增不改。`reasons_json` 只能用 `reason_fragment_id` 查表渲染，前端與 API 不得重新推斷。
>   - **S2 範圍**：LM-94、LM-95 只在 `scope_kind = symbol` 成立。`REASON_FRAGMENTS[surface_not_permitted]` 的守門含 `scope_kind == symbol`，其他 scope 沒有項目。v0 之後若依第 8 點升 `policy_version`、引用其他 scope，要先有該 scope 的核可片段，否則 FL-52 (c) 失敗。
>   - 任何使用者文件、說明頁、tooltip、API 欄位說明，都不得說明 LM-94 和 LM-95 的差別（LM-95 的核可條件）。

**A-55｜FL-52 新增 (e)～(g)**
- 方向：收緊。
- 依據：第六批 §四 tech-architect 第 1 點 S3、S4。
> - (e) **S3 靜態斷言**：四態中的每一態 s，(symbol, symbol_detail) 都要列在 `SURFACE_PERMISSIONS`，而且 `required_disclosures(symbol, symbol_detail, s)` 列的片段全部在核可表內。這包括 `better_than_baseline` 時另加的 D-2 開盤基準句，以及 D-4 的區間、n、期間片段。任何一態不成立，FL-52 就失敗。
> - (f) **「只在」斷言**：除了 `symbol_detail`、`api`，其他每個 surface 的 (symbol, surface) 都不得列入 `SURFACE_PERMISSIONS`。任何一格要開放，LM-94、LM-95 都要先重送。
> - (g) **S4 窮舉表**：`surface_not_permitted` × 四態 × `scope_kind`，每個組合恰好選出一個片段：
>   - symbol × `better_than_baseline` → LM-95；
>   - symbol × 其餘三態 → LM-94；
>   - 非 symbol：沒有項目。另外斷言 v0 的引用範圍 ⊆ {symbol}。
> - 不得 skip；效力鏈同 FL-45 (c)。

**A-56｜D-11.4 第 6 點：其餘七個原因值與 `pending_triggers` 的字面對應（取代 r2' A-25 末項「其餘七個值：…同一批送審」）**
- 方向：收緊（補上守門）。
- 依據：第六批 §三 LM-96～LM-103 的條件欄；§二 PD-b 的說明。
- 這條是連帶修正：來源沒有點名，但 FL-52 (a)(b) 要完整就一定要有。
> - 對應：
>   - `suspended_f3` → LM-96；
>   - `withdrawn_f2` → LM-97（三個 `withdraw_reason` 共用）；
>   - `gated` → LM-98（守門見 A-57）；
>   - `before_dv` → LM-99；
>   - `late` → LM-100，守門：有 R_s 而且 `late=1`；
>   - `insufficient` → LM-101，守門：有 R_s、`late=0`，而且屬於 PV-4 第四態；
>   - `voided` → LM-102，觸發時記 WARNING。
> - LM-96～LM-98 的守門含 `scope_kind == symbol`，同 S2。
> - LM-99～LM-102 的 `{MM/DD}` 一律取該筆的 `data_as_of`（T），套用年份規則；不得用 plan 產生日或今天。
> - LM-99 的「紀錄起算日」用語，要和 LM-84、LM-85、LM-111 一起定案（quant 與 tech-architect）；改詞就要重送。
> - **`pending_triggers`**：`availability = unavailable`，而且 5 日展望條件出現在 `pending_triggers` 時，一律渲染 LM-103。該 `Condition` 依 A-70 處理，不得顯示「等待中」；LM-103 和 LM-86 同時出現。
>   - D-11.4 第 7 點與 r2' A-37 的「恢復前這條條件無法成立」，改為引用 LM-103（風控已撤回「恢復」這個用詞）。
> - 不設 `PLAN_PENDING_OUTLOOK_SUSPENDED_OR_WITHDRAWN`（PD-b 不採用）。

**A-57｜D-11.4 第 12 點 (iv)：`display_reasons_json` 加 `gate`；LM-98 守門（回答第六批 TA-6）**
- 方向：收緊。
- 依據：第六批 §四 tech-architect 第 6 點；LM-98 的條件欄。
- 事實依據：
  - ADR-0025 D-6.6（L412-414）；
  - 決策包 #10（L41）；
  - PRD L33、L548、L624。
- 這條會修改 r2' A-28 (iv)。
> - (iv) 結構改為 `{suspend: [...], withdraw: {...}|null, gate: [...]|null}`。
>   - `gate` 是封閉列舉，可以多值，固定排序。`display_state = gated` 時非空，其他狀態為 null。
>   - v1 候選值：`forward_n_below_min`（前瞻不重疊 n 未達登記門檻，含族群 150）、`replay_review_pending`、`shadow_run_pending`、`settlement_smoke_pending`。
>   - 實際啟用哪些值，由 CEO #10 的裁示當參數注入（D-11.4 原第 4 點）。沒有啟用的值不得出現（測試）。
> - **LM-98 守門**：`scope_kind == symbol`，而且 `gate == [forward_n_below_min]`。其他組合沒有核可片段，FL-52 (c) 失敗（列入 A-63 第 5 項）。
> - FL-53 加 (f)：每個 `gate` 值各一個 fixture；`gate` 多值時，不得選到 LM-98。

### 乙、FL-45 (b)（第六批第四節第 2 點）

**A-58｜FL-45 (b) 改寫；D-12「下架原因列舉值」第 5、6 點連帶修改**
- 方向：斷言本身不變，只是改成和已核可的字面一致；(b3)、(b4) 是收緊。
- 依據：第六批 §三 LM-104；§四 tech-architect 第 2 點。
> - 第 5 點：`LM79_WITHDRAW_REASON_FRAGMENTS` 改為 `LM79_WITHDRAW_REASON_RENDER: Mapping[withdraw_reason, PredecessorRender]`，其中 `PredecessorRender = (template_id, reason_fragment_id | None)`：
>   - `f2_invalid_stop` → (LM-79, LM-75)；
>   - `f2_deadline` → (LM-79, LM-74)；
>   - `f2_invalid_stop_worst_case` → **(LM-104, None)**。LM-87 是 LM-104 核可全文的一部分，不是代入 LM-79 的片段。
> - 第 6 點：「D_v 前 LM-79 的 worst_case 變體必須核可」改為「已由 LM-104 滿足（第六批 R6-04）」。
> - **FL-45 (b) 新文**：LM-79、LM-81、LM-104 只從各自的對照表取值，另加四項斷言：
>   - (b1) LM-87 不得代入 LM-79 的 `（{下架原因}）`；
>   - (b2) worst_case 只用 LM-104，而且只在前一版 `withdraw_reason = f2_invalid_stop_worst_case` 時使用；
>   - (b3) LM-104 的兩處 `{X}` 都取 `withdrawn_at_n` 這一個後端值（fixture 用不同的 n 驗證兩處相同）；
>   - (b4) LM-104 內嵌的 LM-87 逐字完整，不得截斷。
> - LM-79 的原有條件同樣適用 LM-104：和詳細頁同批上線；F-3 恢復時不適用。qa-e2e 在 375 寬度驗收。
> - FL-45 (a)、(c) 不變。

### 丙、紀錄清單（第六批第四節第 3～5 點；r2'' 另案第 3、4 點）

**A-59｜D-11.1 用詞定義（主統計與 n）**
- 方向：不變。
- 依據：第六批 §四 tech-architect 第 5 點。
> - 在 D-11.1 第一點末尾加一段：
>   - 「主統計」指 E 的成員資格；「計入／屬於主統計」就是屬於 E。
>   - 「n」指在 E 內、依事先宣告 §4.1 不重疊規則計得的筆數。作廢列不計入 n，但計入 W。證據不足列是否計入 n，依 §4.1 與 LM-91 第 5 條（quant 書面確認）。
>   - 兩個詞不得混用。
> - 依此：
>   - D-7.6、D-7.8，以及 LM-14、LM-37、LM-80 的「不計入主統計」都屬實，不改；
>   - LM-38 要重送成「不計入 n」（creative-lead）；
>   - E 的定義不變，所以不觸發 LM-84「E 有改動要重送」的條件。

**A-60｜D-11.4 第 11 點 (f)：不變式與清單的取列範圍**
- 方向：收緊。
- 依據：第六批 §四 tech-architect 第 3 點。
> - **不變式**：清單中的每一列，`in_eligible_set = false` 若且唯若 `exclusion_reasons` 非空。
> - E 還有兩個條件沒有對應的 exclusion 值：`supersedes_id IS NULL`，以及 claim 為 forward。處理方式是這兩類列**不回傳**：
>   - (i) 三個紀錄清單端點（A-71）只回傳 `forecast_record.supersedes_id IS NULL` 的原始列；結算端取更正鏈的最後一筆（D-11.1）。
>   - (ii) 清單不讀 `forecast_replay`。`forecast_record` 加 insert trigger：`claim_id` 所指 registry 列的 `kind` 必須是 forward，否則 RAISE；`forecast_replay` 反過來，只收 replay。
>   - 若要列示更正列或重放列，要先擴充 `exclusion_reasons` 列舉並送字面審。
> - **FL-58**：
>   - (a) 不變式的性質測試；
>   - (b) 有更正列與重放列時，清單不回傳它們；
>   - (c) insert trigger 拒絕把 replay claim 寫進 `forecast_record`；
>   - (d) `in_eligible_set` 和 validation 的 E 呼叫同一個函式（FL-49）。

**A-61｜D-11.4 第 11 點 (f) 之後補上字面對應；FL-52 (d) 擴充**
- 方向：收緊。
- 依據：第六批 §三 LM-107～LM-114 的條件欄；§五 第 1、2 點。
> - **`in_eligible_set = true`**：
>   - 一般列 → LM-107；
>   - 證據不足列 → LM-108（必要，取代 LM-107）；
>   - 作廢列 → LM-109（必要，取代 LM-107）。
>   - 作廢指最新 outcome 的 `status ∈ {unresolvable_missing_data, excluded_corporate_action}`；證據不足指 `label = insufficient`。兩者同時成立時選 LM-109（要有 fixture）。
> - **`in_eligible_set = false`**：用 LM-110，`{原因}` 只取以下四個：
>   - `before_dv` → LM-111；
>   - `late` → LM-112，只用於排程列；
>   - `on_demand` → LM-113；
>   - `pit_violation_confirmed` → LM-114，只用於有事件的列。
>   - 多個原因全部列出：`pit_violation_confirmed` 排第一，其餘照列舉順序，以「；」分隔；不得截斷，也不得寫「等」。
> - **上畫面的前提**：
>   - LM-107～LM-110：LM-84 核可，而且驗證狀態頁已上線；
>   - LM-108：另需 quant 書面確認 LM-91 第 5 條；
>   - LM-109：LM-38 重送核可之前不得上線；在那之前，有作廢列的清單不得渲染任何 `in_eligible_set` 字面（前端渲染守門，Phase 4 驗收）；
>   - 最壞情境的結果必須真的渲染。
> - 片段常數不再使用 `counts_in_primary`／`RECORD_COUNTS_IN_PRIMARY_*` 系列。
> - **FL-52 (d) 擴充**：`in_eligible_set` × {一般, 證據不足, 作廢}，以及 `exclusion_reasons` 的每個值，窮舉表都恰好選出一個片段。PIT 列的視覺區隔維持前端契約測試。
> - qa-e2e 在 375 寬度驗收 LM-114。

**A-62｜D-11.4 第 11 點 (d)、(d′) 之後：LM-105、LM-106 的守門 R1、R2**
- 方向：收緊。
- 依據：第六批 §四 tech-architect 第 4 點；r2'' 第五節第 1 點。
> - 片段：(d) → LM-105；(d′) → LM-106，紀錄清單與 POST 共用同一個 ID（A-36 第 2 點）。依 A-27 的順序，先成立的規則決定用哪一句。
> - **R1**：(b)「任何 scope 的 claim 為 `gated` 而且未結算」與 (c)「族群 `gated`」都排在 (d)、(d′) 之前，所以 `gated` claim 的列在結構上選不到這兩句。
>   - FL-58 加 (e)：凡是選中 LM-105 或 LM-106 的列，所屬 claim 當下的 `display_state ≠ gated`。
> - **R2：作廢列結算後怎麼呈現**
>   - 建議：作廢列結算後，用 `settled_record` 呈現原本的 label，加上作廢原因片段（`status_reason`，例如 LM-63），標示「已作廢」，不附實際結果。這樣「結算後列示」對最後作廢的列也屬實。
>   - **這要風控書面確認。** 同一個決定也適用 r2'' A-36 第 4 點的 on-demand 作廢列。
>   - 確認之前採 fail-closed，不顯示 label。這時 LM-105、LM-106 對最後作廢的列不實，FL-52 (d) 判失敗，D_v 會被擋住。

**A-63｜A-27 (a)～(c) 的單列狀態片段（回答第六批第 4 點的附帶確認）：需要，列為 B-8 遺漏**
- 方向：收緊。
- 依據：第六批 §四 tech-architect 第 4 點；AC-C4-3「不留空白」。
- 為什麼需要：
  - 不顯示 label、又沒有狀態說明的列，等於留白，會被讀成資料壞了，或讓使用者自己猜。
  - (d)、(d′) 已經有片段，(a)～(c) 沒有，前後不一致。
  - LM-96～LM-98 的核可條件是「接 LM-86」，主詞又限定個股，不能直接拿來用在清單上。
> - A-27 (a)～(c) 成立、不顯示 label 的列，`status_fragment_id` 必填。可以指向清單層的區塊片段，但不得留白。
> - 交 creative-lead 起草的語意（不是字面）。大盤、族群、個股要各自有主詞：
>   1. (a) `withdrawn_f2`、未結算：已下架，結算後列示；
>   2. (a) `suspended_f3`、未結算：暫停顯示，結算後列示；
>   3. (b) 大盤或個股 `gated`、未結算：結算後列示（結算後會依 (e) 附 PV-45）；
>   4. (c) 族群 `gated`，不論是否結算：未達 150 前不顯示方向（n／150）。不得暗示之後一定會開放；若 AC-C4-3 已有核可字面，可以送風控確認能否擴用。
>   5. A-57 中 `gate` 不只樣本數一項時，用來取代 LM-98 的片段。
> - 核可之前，FL-52 (d) 失敗。

**A-64｜D-11.4 第 11 點新增 (g)：封閉 schema 推廣到所有不顯示 label 的狀態**
- 方向：收緊。
- 依據：r2'' 第四節第 3 點。
> - 以下所有不顯示 label 的回應列，一律用同一個封閉 schema `MaskedRecordView`（`extra="forbid"`）：
>   - A-27 (a)、(b)、(c)、(d)、(d′)；
>   - POST 回傳的 `late=1` 排程紀錄；
>   - FL-34 下架期間的紀錄回應。
> - **白名單**：A-36 第 1 點 (b) 的清單，另外：
>   - 排程列用 `late` 取代 `window_started`；
>   - `settled` 依實際值；
>   - (c) 已結算列可以加 `settlement_date`、`outcome_status`。
> - **不得出現**：
>   - `label`、`range_basis`、`OutlookWeather`、色彩代碼、方向詞、`invalidations_json`、`evidence_json`、`baseline_predictions_json`；
>   - (c) 另外不得出現 `realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`（PA-9、LG-15）。
> - 白名單要增列欄位，須修訂本點並送風控。
> - **FL-59**：每一種不顯示 label 的狀態各一組，比照 FL-52b (9a)～(9c)：schema 驗證、全文掃描（方向詞清單用單一來源）、標籤互換後逐位相同。

**A-65｜D-11.4 第 11 點新增 (h)：結算後的呈現形式推廣到排程紀錄**
- 方向：收緊。
- 依據：r2'' 第四節第 4 點。
> - 清單中已結算、可以顯示 label 的排程列（含 POST 回傳的排程紀錄）：
>   - label 只放在 `settled_record` 內，和 A-36 第 4 點共用 schema `SettledRecordView`；
>   - 同一物件要帶 `settlement_date` 與結算結果；
>   - 頂層沒有 `label`；
>   - 不得出現在任何「目前展望」的欄位或呈現。
> - 「已結算＋實際結果」的片段（r2'' R''-6 給 creative-lead 的項目）範圍擴及排程紀錄。核可之前，已結算的列不顯示 label；這個片段也列入 FL-52 (d)。
> - 作廢 outcome 依 A-62 R2。(e) 的 PV-45 揭露照舊。
> - FL-59 加兩個排程已結算的 fixture：resolved 一個、作廢一個。

### 丁、顯示面（顯示面確認第四節第 1～5 點）

**A-66｜D-11.4 第 9 點第 1 點：`first_layer` 改為封閉清單，雙重歸屬取聯集**
- 方向：收緊。
- 依據：顯示面確認 §二 (c) required 第 1～4 點；§四 tech-architect 第 1 點。
> - 取代 r2 A-26 中 `first_layer` 的說明文字。
> - **`first_layer` 是封閉的元件清單**，共六項：
>   1. 市場總覽的天氣區塊（含大盤展望）；
>   2. 「最需要處理」清單；
>   3. 首頁警示列（同時屬於 `alert`）；
>   4. 族群列表（Phase 4 之前是首頁的 `SectorMomentumCard`）；
>   5. 族群詳細頁整頁；
>   6. 市場總覽的大盤紀錄清單展開區。
> - 市場總覽上的持倉表、摘要卡、風險儀表**沒有歸屬**（fail-closed）。日後要加「動作」欄，須逐元件指定並送審。
> - 不在清單內的頁面或元件，一律沒有歸屬，不得渲染展望 label、天氣或 plan 結論（AC-S-6）。
> - `symbol_detail` ＝ `/position/[symbol]` 整頁。
> - ADR 中的「首層」只指 `first_layer`。
> - **單一來源**：`PAGE_SURFACES`，前後端共用（建議放在 `apps/stock-desk/shared/page-surfaces.json`）。
>   - 元件的 consumer ＝ 它所屬各 surface 的聯集；
>   - 端點的 `SERVES` 必須 ⊇ 呼叫它的所有元件的 surface 聯集。
> - 族群詳細頁的成員列不得出現個股展望或 plan 結論（AC-S-7）。PA-9／PV-40 的排序與篩選禁令同樣適用。
> - **FL-60**：
>   - (a) 前端 route／元件列舉：凡是渲染 `OutlookView` 衍生內容或 plan 欄位的，在 `PAGE_SURFACES` 都要有非空項目；
>   - (b) 端點的 `SERVES` 涵蓋呼叫它的元件（`PAGE_ENDPOINTS` 宣告，加上前端呼叫點 grep 比對）；
>   - (c) `PAGE_SURFACES` 和本點清單逐項相同；增刪都要修訂本點並送風控。

**A-67｜D-11.4 第 9 點：第 2 點初版改寫、第 5 點改寫**
- 方向：收緊（和 r2 草案相比）。
- 依據：顯示面確認「`SURFACE_PERMISSIONS` v1」裁定 required 第 1～3 點；§四第 2 點。
> - 取代 r2 A-26 第 2 點的初版內容。
> - **v1 列入的格子恰好六個**：(market, first_layer)、(market, api)、(sector, first_layer)、(sector, api)、(symbol, symbol_detail)、(symbol, api)。
> - 其餘一律不列入，包括所有 scope 的 `alert`、`export`，以及 (symbol, first_layer)。
> - **(symbol, first_layer) 在 v1 程式碼裡不列入，不得寫成條件格。**
>   - 開放路徑只寫在 ADR 文字：優於基準、required_disclosures 全部核可、升 `policy_version`、送風控，而且 LM-94、LM-95 要重送。
> - 第 5 點改為：「v1 期間不論驗證狀態為何，個股展望對政策表一律是 `surface_not_permitted`。」
> - FL-54 (d) 加兩項斷言：
>   - 鍵的集合和上列六格逐項相同（snapshot）；
>   - 格子的值只能是揭露規格，不得是 callable 或以狀態為條件的值。

**A-68｜D-11.4 第 9 點第 4 點：`PLAN_OUTPUT_SURFACES` 初版**
- 方向：**展望可用性放寬（有條件，v1 實效不變）；輸出面收緊。**
- 依據：顯示面確認 §一 第 1 點；§二 (a) required 第 1～4 點；§三。
> - **初版 ＝ {first_layer, symbol_detail, api}。**
> - 適用欄位：`position_action`、`reasons`、`pending_triggers`、`add_conditions`、`entry_conditions`、`outlook_refs`。
>   - 「最需要處理」的排序與成員、`plan_record` 中會顯示的欄位、API 回應，屬 plan 衍生輸出，適用同一集合。
> - **`alert`、`export` 移出的前提**：它們的渲染、觸發時機與計數都不依賴上列任何欄位（由 A-69 釘住，D_v 前落地）。提醒裡「有 N 則新評估」的 N，不得依 plan 欄位計數。
> - **登記**：quant 在事先宣告 v0.10 修訂 D-20 ①，方向照實寫成「放寬（只在優於基準而且該格送審開放後才可能生效）＋收緊（輸出面）；v1 實效不變」。要在 D_v 前、本 ADR 核可前完成。
> - **加回路徑**：推播或匯出要承載 plan 衍生內容，必須先加回集合、升 `policy_version`、送風控，而且加回要早於渲染上線。
> - 不得以「plan 實際沒在首頁渲染」為理由，把 `first_layer` 移出集合。這等同方案 B，在風控否決範圍內。

**A-69｜FL-54 新增 (h)；FL-43 保留提醒 payload 的斷言**
- 方向：收緊。
- 依據：顯示面確認 §二 (a) required 第 2 點；§四 第 4 點。
> - **(h1) import graph**：`app.alerts.*` 與 `EXPORT_MODULES` 所列的匯出模組都不可達 `app.plan.*`，也不讀 `plan_record`（grep）。新增的匯出模組要列進 `EXPORT_MODULES`。
> - **(h2) 行為測試**：任意變動 A-68 的適用欄位之後，下列各項逐位相同：
>   - 提醒 payload；
>   - 是否觸發、何時觸發；
>   - N；
>   - 匯出的檔案內容。
> - FL-43 對「提醒 payload」的斷言**保留**，當作回歸防線。
> - D_v 前落地（G-6 效力鏈）。

**A-70｜D-11.4 第 7 點加上 None 規則；FL-43 擴充**
- 方向：收緊。
- 依據：顯示面確認「D-19 缺口」；§四 第 3 點。
> - **None 規則**：每一種 unavailable 原因下（含 `surface_not_permitted`），凡是評估時用到展望的 `Condition`：
>   - `status` 固定為 `unavailable`；
>   - `observed`、`threshold` 必為 None。
> - **範圍不只 `category=outlook`**，也包括：
>   - ADR-0025 D-4.4 的趨勢條件；
>   - D-4.5 的 `consider` 條件與 `avoid` 的展望項；
>   - 持有模式序位 7 的展望項。
> - **「用到展望」的判定**：政策表每個 `Condition` 都宣告 `uses_outlook: bool`，沒有預設值。loader 在 D-15 同一層的 validator 中驗證：條件樹引用展望欄位的，必須是 `true`。
> - **複合條件**（例如趨勢條件）整條變成 unavailable，MA60 的觀測值也一併不輸出。要拆成兩條，屬於 quant 的事先登記。
> - **FL-43 擴充**：
>   - (i) 每一種原因 × 每個 `uses_outlook=true` 的 Condition，斷言 `observed`、`threshold` 都是 None；
>   - (ii) 標籤互換的輸出清單加入 `add_conditions`、`entry_conditions`、`quantity_range`；fixture 要含 `add_conditional`、`consider` 兩條路徑。

**A-71｜D-1 模組表、D-7.8 第 8 點、D-11.4 第 11 點：紀錄清單依 scope 拆成三個端點**
- 方向：收緊。
- 依據：顯示面確認 §二 (d) required 第 1～3 點；§四 第 5 點。
> - `GET /api/forecast/records` 改成三個端點：
>   - `/market`：`SERVES={first_layer}`；
>   - `/sectors/{sector_key}`：`SERVES={first_layer}`；
>   - `/symbols/{symbol}`：`SERVES={symbol_detail}`。
> - 每個端點只回傳自己的 scope_kind（測試）。不設跨 scope 的總端點。
> - **不採「單一端點依參數決定 SERVES」**：那會變成執行期判定，違反 r2 A-26 第 6 點與 FL-54 (g)。
> - A-27 (a)～(f)、(d′) 與 A-60～A-65 對三個端點一體適用。
> - 不得有預設會排除作廢列或逾時列的參數。有篩選參數時，預設回傳全部（AC-V5-3b／3d）。
> - D-7.8 第 8 點 r1 的「`GET /api/forecast/records`（帶 `trigger=on_demand`）」改為 `/symbols/{symbol}` 端點。FL-52b (9) 的「紀錄清單」也指這個端點。

### 戊、r2'' 另案（第四節第 1、2、5 點；第 3、4 點已寫成 A-64、A-65）

**A-72｜D-14 G-7 改成肯定句**
- 方向：收緊。這比原本「只改句型」多做了一步，理由見第四節 C-8。
- 依據：r2'' 第四節第 1 點。
> - **G-7 新文**：「on-demand 紀錄的寫入，同樣要 G-1～G-6 全部成立。強制方式和排程紀錄相同（A-33）。on-demand 的寫入路徑和排程呼叫同一個閘門函式。on-demand 紀錄一律不屬於 E。」
> - 理由：
>   - `window_started` 依 VS-6 計算，G-4 不成立時沒有保證，而 A-36 是否顯示 label 就靠它；
>   - FL-27 要求所屬 claim 已凍結，也就是 G-3。
> - A-33 中「G-7 不是排程紀錄的閘門」改為「G-7 是 on-demand 寫入的閘門」。FL-38 加一項：on-demand 路徑在 G-3、G-4 不成立時拒絕寫入。
> - **只改句型、不改實質的版本（不建議）**：「on-demand 受 G-6 約束，G-6 不成立時不得寫入；G-1～G-5 不約束 on-demand。」

**A-73｜D-7.8 第 8 點：on-demand 去重**
- 方向：收緊（補上原本沒有的定義）。
- 依據：r2'' 第四節第 2 點。
> - 同一個 (symbol, horizon, T, definition_version, rules_version)，on-demand 原始列只寫一筆。M-6 的部分唯一索引已經包含 `trigger`，結構上有保證。
> - POST 的處理依序是：
>   1. T 日的排程原始紀錄存在 → 回傳排程紀錄；
>   2. 否則，已有 on-demand 原始列 → 回傳既有列，不寫入，`window_started` 讀已存的值；
>   3. 否則 → 寫一筆。
> - 並發撞到 UNIQUE 時，重讀並回傳既有列，不回 5xx。
> - FL-52b 加 (10)：
>   - 08:29:59 寫入的列，08:30 之後再查，回傳同一個 `forecast_id`，依 A-36 (a) 顯示 label；
>   - 兩個並發請求只產生一列。

**A-74｜FL-16 的範圍用 `ENDPOINT_SURFACES` 列舉**
- 方向：收緊。
- 依據：r2'' 第四節第 5 點。
> - `ENDPOINT_SURFACES` 的每一項加 `kind ∈ {current_outlook, plan, record_list, on_demand}`，沒有預設值。沒有登記 kind 的 route，測試失敗。
> - **FL-16 新文**：
>   - `late=1` 與 on-demand 的紀錄，永遠不會出現在 `current_outlook`、`plan` 兩類端點的回應中；`outlook_refs` 也不得指向它們。
>   - `record_list` 依 D-11.4 第 11 點。
>   - `on_demand`（v1 只有 `POST /api/outlook/symbols/{symbol}`）依 D-7.8 第 8 點與 A-36。
> - FL-54 (g) 加：`current_outlook` 類的 route，用 fixture 驗證不會回傳上述兩類紀錄。

### 己、暫定的大盤 bar（風控 r3 確認第四節 R-4 第 1～4 點；ADR-0027 核可前 required）

**A-75｜D-7.3 決策日 T（整點取代）**
- 方向：收緊。
- 依據：風控 r3 確認 §四 R-4 第 1 點；§二-7。
> - **候選 T** ＝ 市場 DB 中最新一個有 ok bars run 的 session。候選 T 必須同時滿足：
>   - (i) A-78 的 run 下限；
>   - (ii) 大盤 T 日 bar 是定案列。
> - **定案列的判準**：`is_final_bar` 只有一個定義，放在 `app/data/session_calendar.py`，引用 ADR-0028 CS-17 與 r3 補正 R-1：
>   - `final_after(TW, T) ≤ min(as_of, fetched_at) ≤ now`；
>   - 兩個時間都帶時區；
>   - `source ∉ NON_EVIDENCE_SOURCES`；
>   - 沒有 `OHLC_INVALID`。
> - **(ii) 不成立時**：
>   - 經 `app.services.index` 強制重抓一次（寫入仍經 `service.py`，不新增 CS-20 的寫入者）；
>   - 重抓後仍不成立，或 (i) 不成立 → 這次 run 不寫紀錄，該 session 記為 `inputs_not_ready`；
>   - **不得改用更早的 session 當 T，也不得使用暫定值。**
> - **讀取介面**：`app.services.index` 新增逐列回傳 `as_of`、`fetched_at`、`source` 的方法。現行的快取結果只帶最舊的那個 `fetched_at`〔事實：`cache.py:109`〕。FL-5 不變，forecast 仍不得直接碰快取。
> - `forecast_input_series.bars_json` 每一列都帶這三欄，並納入 `content_sha256`。
> - **FL-61**：
>   - (a) `as_of` 14:59:58+08:00、`fetched_at` 15:00:01+08:00 → 不定案，觸發重抓；
>   - (b) 重抓後仍不定案 → `inputs_not_ready`，沒有寫入，不退回前一個 session；
>   - (c) 重抓後定案 → 正常；
>   - (d) 示範資料列不算；
>   - (e) grep：`app/forecast`、`app/outlook` 沒有 `publish_cutoff` 的行內比較。

**A-76｜D-4 新增第 8 點：快取 bar 消費者的封閉列舉**
- 方向：收緊。
- 依據：R-4 第 2 點。
> - **`CACHE_BAR_CONSUMERS`**：
>   1. D-7.3 的大盤 T 日 bar；
>   2. D-4.5 的大盤輸入序列（含基準所用的序列）；
>   3. D-9.2 的大盤結算路徑；
>   4. FL-25 一致性檢查所比對的估值價格；
>   5. `plan_outcome` 的觸價價格（另案定義時，若取自快取，就歸入這一項）。
> - 每一項只能經過以 `is_final_bar` 篩選的讀取方法取得。不符合的列一律視為缺，處理方式：
>   - 第 1 項 → A-75；
>   - 第 2、3 項 → 依既有的 insufficient 或 `missing_bar_after_wait` 規則；
>   - 第 4 項 → `E-PRICE-UNUSABLE`；
>   - 第 5 項 → excluded。
> - 新增消費者，要先修訂本點。
> - **FL-62**：AST／grep 確認呼叫點 ⊆ 列舉；每一項各一個「暫定列」fixture。
> - **quant**：確認第 1～3 項（以及第 5 項）是否屬於事先宣告的 PIT 輸入。若是，就登記為補定義（收緊），D_v 前完成。

**A-77｜D-8.1 觀察日（整點取代）**
- 方向：收緊。
- 依據：R-4 第 3 點。
> - 觀察日 ＝ (i) 聯集 (ii)：
>   - (i) 市場 DB 中，有 ok bars run、而且該 run 的 `recorded_at ≥ final_after(TW, session)` 的 session；
>   - (ii) 大盤有定案列的日期（`is_final_bar`，已排除 `NON_EVIDENCE_SOURCES`）。
> - 不用週一至週五推定。和 ADR-0028 D-9 的 observed 是不同的定義。
> - 平日既不是觀察日、也不是官方休市日時，記 WARNING，但不寫缺日列。
> - FL-19 加三個 fixture，各自不得讓 session 成為觀察日：示範列、暫定列、定案前的 run。

**A-78｜市場 DB 啟動過早的 capture（被 `_already_ok_today` 凍結）**
- 方向：收緊。
- 依據：R-4 第 4 點。
> - **採消費端防護**：ADR-0027 讀市場 DB 的每一處，對 session s 的 bars，只認 `recorded_at ≥ final_after(TW, s)` 的 ok run 寫入的 bars。適用於：
>   - D-4.1 的 PIT 視圖；
>   - D-7.3 (i)；
>   - D-8.1 (i)；
>   - D-9.2 的個股與族群成員結算。
> - D-4.1 原句「與 `panel._visible` 位元相同」改為「在 `panel._visible` 之上加定案下限」，等價測試改成比對交集。
> - 下限函式只有一個，放在 `MarketPanelReader` 的新唯讀方法或 `app/outlook/inputs.py`，引用 `final_after`。不改 `pit_snapshot`、`market_panel` 的寫入。
> - **FL-63「交易日 10:00 啟動」fixture**：10:00 寫入 session D 的 ok run，之後 17:30、19:30、21:30 的 capture 都被跳過。期望：
>   - D 不成為 T，記 `inputs_not_ready`；
>   - D 透過 (ii) 成為觀察日，所以缺日稽核會寫出缺日列；
>   - D 在 10:00 寫入的 bars 不進入任何後續的 PIT 輸入或結算窗。
> - **後果**：D 之後若沒有任何定案後的 run 補寫，後續約 60 個交易日、特徵窗涵蓋 D 的紀錄，可能都是證據不足；結算窗涵蓋 D 的紀錄，可能作廢。
> - **根本修法**：改成 `pit_snapshot` 不把定案前的 run 算成當日已完成。這屬於 ADR-0012（accepted）的修訂，要 CEO 核可。
> - data-engineer 先查證：10:00 的 capture 實際寫入哪一個 session，暖身回補能不能補上。即使查證結果是不會寫入 D，消費端下限仍保留，當作縱深防禦。

### 庚、收尾

**A-79｜檔頭、與既有 ADR 的關係、Consequences、待決事項、修訂紀錄**
- 方向：不變。
> - **檔頭**：「r3 修訂：2026-10-17，依 tech-architect 修訂提案 A-54～A-79」。
> - **與既有 ADR 的關係**：
>   - ADR-0028：定案判準引用 CS-17 與 r3 補正 R-1；依賴方向仍是 forecast → data。
>   - ADR-0012：不修訂；A-78 的根本修法另案處理。
> - **Consequences 新增五點**：
>   1. v1 全期，個股展望對 plan 都不可用，即使已經優於基準；
>   2. D_v 前要核可的字面增加（A-55 (e)、A-62、A-63、A-65）；
>   3. 交易時段開機，可能造成當天缺日，並讓後續一段期間出現證據不足或作廢；
>   4. 晚間重抓大盤失敗的日子，會記成 `inputs_not_ready`；
>   5. 紀錄清單拆成三個端點。
> - **待決事項**：依第四節更新。
> - **修訂紀錄**：被取代的原文要逐字保留，包括：
>   - r2' A-25 的兩個子項；
>   - A-23 第 5、6 點與 FL-45 (b)；
>   - r2 A-26 中 `first_layer` 的說明、第 2 點初版、第 4 點初版值、第 5 點；
>   - A-28 (iv)；
>   - G-7 與 A-33 末句；
>   - FL-16；
>   - D-7.3、D-8.1；
>   - D-4.1 的「位元相同」句；
>   - D-1 的 route 列與 D-7.8 的 r1 文字。
>
>   其餘各條都是新增，沒有被取代的原文。

## 三、方向統計

| 方向 | 條數 | 條號 |
|---|---|---|
| 收緊 | 22 | A-54～A-57、A-60～A-67、A-69～A-78 |
| 不變 | 3 | A-58（其中 b3、b4 是收緊）、A-59、A-79 |
| 放寬（有條件，v1 實效不變）＋收緊 | 1 | A-68（展望可用性放寬；輸出面收緊） |

## 四、衝突與待確認（我沒有自行裁決）

- **C-1（D_v 要等的東西變多）**：A-55 (e) 依風控 S3，要求「優於基準」狀態的伴隨揭露（D-2 開盤基準句，以及 D-4 的區間、n、期間）先核可，否則 D_v 不能開始，即使優於基準預期是好幾年後的事。A-63、A-65 的片段，以及 A-62 的 R2，也一樣卡在 D_v 前。
- **C-2（風控）**：顯示面確認 (e) 第 1 點要求 R5-06 重送時涵蓋「並列揭露」的語意，但第六批已經逐字核可 LM-94。要請風控確認：LM-94 加上 LM-86 是否已經滿足 (e)。
- **C-3（風控，R2）**：r2'' A-36 第 4 點對 on-demand 作廢列採 fail-closed（不顯示 label）。若維持，LM-106、LM-105 對最後作廢的列就不實。我建議作廢列顯示「label＋作廢原因」，但需要風控書面裁定。
- **C-4（風控，殘餘邊界）**：族群可能因為 PIT 違規列被移出 E，n 降回 150 以下而重新變成 `gated`。這時先前已經顯示過「結算後列示」的列，就會變得不實。請風控判斷這個殘餘風險能不能接受。
- **C-5（我自己提案的修改）**：A-57 改了 r2' A-28 (iv)「結構固定」的寫法；A-78 改了 D-4.1「與 `panel._visible` 位元相同」。兩處都是改我自己的提案或本 ADR，不牴觸任何 accepted ADR，但要在修訂紀錄中保留原文。
- **C-6（CEO #10）**：A-57 要啟用哪些 `gate` 值，取決於 #10。#10 還沒回覆時，所有候選值都可能被啟用，A-63 第 5 項就要先起草。
- **C-7（風控）**：A-66 把「市場總覽」讀成六個元件，**不包含**持倉表、摘要卡、風險儀表（fail-closed）。如果風控本意是整頁都算，請指正。
- **C-8（PM、風控知悉）**：A-72 把 on-demand 的寫入閘門從「只要 G-6」收緊為「G-1～G-6」，所以臨時查詢功能也要等全部閘門成立後才能上線。A-73 的去重規則會讓 08:30 之前產生的那筆紀錄在白天照常顯示 label；那筆是在預測期間開始前產生的，所以屬實。這兩點請風控知悉。
- **C-9（PM）**：A-68 採「`alert` 移出集合」這一支，前提是 PM 把「N 不得依 plan 欄位計數」寫進 AC-S-3，並修訂 NP-A3 第 (5) 項。PM 若選另一支，A-68、A-69 要改回去。
- **C-10（quant）**：
  - 「起算日」用語（LM-99、LM-111）；
  - LM-91 第 5 條的書面確認（LM-108 的前提）；
  - v0.10 的 D-20 ①、D-19 None 規則、A-76 的 PIT 補定義；
  - 趨勢條件要不要拆成兩條（A-70）。
- **C-11（data-engineer）**：A-75 的強制重抓走哪條路徑（`judge()` 在 15:00 後不重抓，這是轉引，我沒有重讀程式）；A-78 的查證。
- **確認沒有衝突的部分**：
  - A-54～A-78 都沒有改動 E 的定義，不觸發 LM-84 的重送；
  - A-75～A-78 和風控 r3 確認的 R-1 方向一致（取兩個時間中較早者）；
  - R1 由 A-27 的既有順序在結構上保證，和風控「不得用於 `gated`」不衝突。

## 五、需 CEO 知悉事項（白話）

1. 第一版上線期間，個股的 5 日方向一律不拿來算行動建議，即使哪天證明「優於基準」也一樣。要開放，得另外送審。
2. 開始正式記錄預測之前，要先核可的文字又多了幾句，包括一些很多年後才會用到的「優於基準」說明。開始記錄的時間可能因此再往後延。
3. 主機如果在交易日白天才開機，當天可能完全沒有預測紀錄，之後一段時間的紀錄也可能被判成證據不足。根本的修法要改 ADR-0012（已核可），屆時會請你核可。
4. 為了避免把盤中的暫定大盤收盤寫進不能更正的紀錄帳，大盤資料必須是收盤定案後才抓到的才能用。重抓失敗的日子會照實記成缺日，不會用暫定值頂替。

**相關檔案**
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（現為 r1：D-7.3 L312、D-8.1 L335、D-11.4 L413-435、D-14 L530-543、FL-16 L605、FL-43 L656）
- /home/user/AICompany/work/reviews/2026-10-17-新定位第六批字面逐字審-LM94至LM115-風控.md（§三、§四、§五）
- /home/user/AICompany/work/reviews/2026-10-17-顯示面配置初版單項確認-風控.md（§二、§四）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028-r3單項確認-風控.md（§四 R-1、R-4）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r2雙撇A36增補-tech-architect.md（第四節）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0028修訂提案r3觀察日來源-tech-architect.md（第四節第 5 點）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案r2prime-tech-architect.md（A-23～A-30、A-37）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案A22至A41-tech-architect.md（A-26、A-27）
- /home/user/AICompany/work/reviews/2026-10-17-PLAN_OUTPUT_SURFACES與頁面歸屬-product-manager.md
- /home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md（D-4 L256-315、D-6.6 L412-414）
- /home/user/AICompany/apps/stock-desk/backend/app/data/cache.py（L50-51、L109）

這是唯讀的架構文件，Codex 不適用。

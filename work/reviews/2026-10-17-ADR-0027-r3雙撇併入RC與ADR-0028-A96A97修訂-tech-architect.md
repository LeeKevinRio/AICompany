# ADR-0027 r3″（併入 RC′-1～RC′-9）與 ADR-0028 A-96′／A-97′（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 r3″（併入 RC′-1～RC′-9）與 ADR-0028 A-96′／A-97′（tech-architect，唯讀）

## 一、結論

**ADR-0027 r3″ 已把 RC′-1～RC′-9 全部寫成條文，可以交 tech-writer 一次套用 r3＋r3′＋r3″。** 三版衝突時以 r3″ 為準，其次 r3′，再其次 r3。所有補正都掛在既有的 A 編號底下，沒有新增 A-87 以後的條號。方向統計依 RC′-7 是 19／2／9／1／2。

套用時有四點要注意：
1. **RC′-2 的免除條款不適用。** n 是 `forecast_validation_snapshot` 的欄位（D-11.4 第 2 點，9ba01d6 L467），寫入快照時就定下，查詢時不會重算。所以照風控要求做 fail-closed。比較基準我用 `stats_json.e_read_at`（讀 E 那次 read transaction 的開始時刻），不用 `computed_at`。前者一定不晚於後者，比字面更嚴，也補上「讀 E 之後、寫入之前」發生的事件會漏判的問題。這點列在第五節知會項。
2. **r3′ 的 FL-58 (e) 有一處筆誤，r3″ 一併更正。** r3′ 寫「選中 A-63 第 1～3 項的列，`display_state ≠ gated`」。可是第 3 項本來就是給 `gated` 的大盤和個股用的，照這樣寫，測試在結構上不可能通過。風控 r3 審查 R3-5 的原文限定在「族群列」，r3″ 恢復這個限定。這是回到風控原文，不是放寬。
3. **ADR-0028 A-96′ 附帶的 ADR-0027 FL-25 fixture 不能放進 r3″ 的 commit。** 機械核對第 1 點要求每個 hunk 都對應 RC′ 等編號，第 17 點要求 A-96／A-97 分開處理。這段要和 A-96′ 同一批，另開一個 commit。
4. **T1-17 做得到逐列標記，不必為此回送風控。** 依據有四點：
   - T1-17 的負責人含 dev-lead（PRD L785）；
   - `GET /api/bars` 現在是單純的投影（`apps/stock-desk/backend/app/api/bars.py` L82-106）；
   - 判定所需的時鐘、D 和 `SessionCalendar`，`build_summary` 本來就要建構；
   - ADR-0028 沒有任何約束禁止 `app/api/bars.py` 呼叫 `close_state`／`session_calendar`（CS-1、CS-4、CS-19 都不涵蓋它）。

有 2 項需要回送風控，另有 3 個缺口請風控裁定，見第五節。

## 二、ADR-0027 r3″ 條文

「＞」後面是給 tech-writer 的條文。「定位」用 A 編號和 D-／FL- 條號。被取代的 9ba01d6 原文一律逐字寫進修訂紀錄。r3、r3′ 的中間版文字沒有落過檔，不必進修訂紀錄。

### RC′-1｜A-63（R3-5）：A-27 (c)；A-57 (iv)；FL-58 (e)

**(1) D-11.4 第 11 點 A-27 (c)：整條取代 r3′ R3-5 的 (c) 新文**
> (c) **族群，而且〔`pa9_holds` 為真，或該 claim 當下成立的 `gate` 值集合非空〕，不論 `display_state`**：不論是否結算，都不出現 label（PA-9；ADR-0025 D-6.6）。
> - PA-9 條件 ＝ 該 claim 在 E 內、依 §4.1 計得的不重疊 n < 150。判定只呼叫 `pa9_holds`，其中的落後規則見 RC′-2。
> - 「當下成立的 `gate` 值集合」指查詢時的有效集合 G_eff，定義見 A-57 (iv)。
> - n 讀「判定 `display_state` 的同一列最新 daily snapshot」的 `n`。沒有 snapshot 時，視為 PA-9 成立（fail-closed）。
> - PA-9 條件只有一個判定函式 `pa9_holds`。D-11.4 第 4 點第 1 子項、A-57 族群的 `forward_n_below_min`、本條都呼叫它。
> - **對族群，(c) 先於 (a)、(b) 判斷。** 選用狀態片段時以 (c) 為準，片段依 A-63 第 11 點選用。
> - (c) 不以 `display_state` 的任何值為條件。

**(2) A-57 (iv)：取代 r3 A-57「`display_state = gated` 時非空，其他狀態為 null」一句**
> - (iv) 結構改為 `{suspend: [...], withdraw: {...}|null, gate: [...]}`。
>   - **`gate` 不論 `display_state` 都要計算。** 每一筆 snapshot 都列出當下成立的 `gate` 值，範圍是 `GATE_FIXED` ∪ 已啟用的 `GATE_ADDITIONAL`；封閉列舉、固定排序。
>   - 沒有成立值時寫 `[]`，任何狀態都不得為 null。`suspended_f3`、`withdrawn_f2` 期間照算照寫。
>   - 第 12 點的優先序只決定顯示哪個狀態，不得讓 `gate` 變成 null 或被清空。`display_state = gated`，若且唯若 suspend、withdraw 都不成立，而且 `gate` 非空。
>   - **查詢時的有效集合 G_eff**：G_eff ＝ snapshot 的 `gate`；族群的 `pa9_holds` 依 RC′-2 為真時，再加入 `forward_n_below_min`。
>     - `OutlookView.display_state` 與 `unavailable_reason`，由 snapshot 的 suspend、withdraw 加上 G_eff，依第 12 點優先序彙整。
>     - 這個查詢時調整只可能把族群的 `shown` 變成 `gated`，不得有其他方向（性質測試）。
>     - `validation_status` 仍取 snapshot 原值。FL-54 (e) 的「同一列」只有這一個例外。
>     - v0 的 plan 只引用個股（第 8 點），不受影響。
>   - LM-98 守門維持 `scope_kind == symbol`、`gate == [forward_n_below_min]`，另外要求 `unavailable_reason = gated`。
- D-11.4 第 4 點第 1 子項「族群 n<150 時」改為「族群 `pa9_holds` 為真，或 G_eff 非空時」。

**(3) FL-58 (e)：整條取代 r3′ 的擴充文字（含上述筆誤更正）**
> (e) 選中 LM-105 或 LM-106 的列，所屬 claim 的有效 `display_state ≠ gated`。族群列另外要求：選中 LM-105、LM-106，或 A-63 第 1～3 項時，`pa9_holds` 為 false，而且 G_eff 為空。

**(4) FL-58 fixture：在 r3′ 的 (e1)～(e3) 之後加**
> - (e4) 族群 `suspended_f3`、n≥150、`replay_review_pending` 成立：(c) 成立，`display_reasons_json.gate` 含 `replay_review_pending`（不是 null），結算後也不出現 label，不得選 A-63 第 2 項。
> - (e5) 族群 `withdrawn_f2`、n≥150、`replay_review_pending` 成立：同 (e4)，不得選第 1 項。

### RC′-2｜A-63（R3-5）：`pa9_holds` 在快照落後時 fail-closed

- 定位：A-27 (c) 的 n 子項之後；D-11.4 第 2 點（snapshot）加 `stats_json.e_read_at`。
> - **快照落後時 fail-closed**（風控 2026-10-17 RC′-2）：簽章是 `pa9_holds(claim, snapshot, e_changed_since: bool)`。
>   - `e_changed_since` 只由 `views` 的單一函式 `e_changed_since(snapshot)` 判定：只要有任何一筆「會改變 E 成員或 n 的事件」，時間戳 ≥ 該 snapshot 的 `stats_json.e_read_at`，就為真。
>   - 為真時，`pa9_holds` 一律為真，直到之後產出一筆 `e_read_at` 晚於該事件的 daily snapshot 為止。
>   - **事件封閉清單 `E_CHANGING_EVENTS`**：
>     - `forecast_ledger_events.kind ∈ {pit_violation_confirmed, x2_confirmed_non_session, db_restored}`，依 `recorded_at`；
>     - `forecast_outcome` 中 `supersedes_id IS NOT NULL` 的列，依 `resolved_at`。
>     - 不按 claim 篩選：任一筆成立，所有族群 claim 都適用。
>   - `forecast_ledger_events.kind` 的每個值都必須歸入 `E_CHANGING_EVENTS`，或歸入 `E_NEUTRAL_EVENTS` ＝ {`f3_resume_approved`, `replay_review_approved`, `session_calendar_conflict`}。新值沒有歸類時測試失敗；判斷不了的一律歸入 `E_CHANGING_EVENTS`。
>   - **`e_read_at`**：snapshot 的計算在單一 read transaction 內讀 E，transaction 開始時以 store 時鐘寫入 `stats_json.e_read_at`。比較一律用 `e_read_at`，不用 `computed_at`（`e_read_at ≤ computed_at`）。
>   - 寫入 snapshot、計算 `gate` 的當下，`pa9_holds` 用本筆剛算出的 n，以 `e_changed_since = False` 呼叫。
>   - 依據：n 是 snapshot 寫入時的欄位值，不是查詢當下重算，所以不適用 RC′-2 的免除條款。
- FL-58 加 fixture：
> - (e6) 族群最新 snapshot 的 n＝150；snapshot 之後寫入一筆 `pit_violation_confirmed`。
>   - 下一筆 snapshot 之前：`pa9_holds` 為真、(c) 成立、已結算列不出現 label、片段的涵蓋範圍含 `forward_n_below_min`；
>   - 之後的 snapshot 依它自己的 n 判定。
>   - 另一格：事件時間落在 `e_read_at` 與 `computed_at` 之間，期望同樣 fail-closed。
>   - 再加一格：斷言 `forecast_ledger_events.kind` 列舉的每個值都已歸類。

### RC′-3｜A-63：多個 `gate` 值同時成立時的片段選用

- 定位：A-63 第 7、8 點整點取代 r3′ 的版本；第 10 點之後加第 11 點；FL-52 窮舉擴充。
> 7. 第 4 項的語意是「族群：PA-9 成立時不顯示方向（n／150），不得暗示之後一定會開放」，不論 `display_state`。**第 4 項只涵蓋 `forward_n_below_min`**，只有 G_eff ＝ {`forward_n_below_min`} 時可以單獨使用。
> 8. 族群 (c) 成立時，片段依第 11 點選用，不得寫「結算後列示」。
> 11. **多個 `gate` 值同時成立時的選用規則**（風控 2026-10-17 RC′-3；大盤、族群、個股都適用）：
>    - 不得只呈現其中一個閘門，尤其不得只呈現看起來最快解除的那一個。例如族群在 `forward_n_below_min` 與 `replay_review_pending` 同時成立時，不得只用第 4 項。
>    - `display.py` 定義 `GATE_STATUS_FRAGMENTS: Mapping[(scope_kind, slot), Mapping[frozenset[gate], tuple[fragment_id, ...]]]`，其中 `slot ∈ {record_list, plan_reason}`。每個片段登記 `covers: frozenset[gate]`。
>    - **不變式**：選出片段的 `covers` 聯集恰好等於 G_eff。呈現方式二選一：
>      - 逐值並列：固定排序，在同一區塊同時呈現；
>      - 一個涵蓋全部成立值的變體。
>    - `plan_reason`（LM-86 只有一個 `{原因}`）只能用單一涵蓋變體，tuple 長度為 1。
>    - 適用範圍：第 3 項、第 4 項、第 5 項、LM-98，以及族群 (c) 成立的列。
>      - 第 3 項本身 `covers = ∅`。(b) 成立的大盤或個股列，以第 3 項加上涵蓋 G_eff 的片段呈現。
>    - 表內沒有項目的組合，視為沒有核可片段：不出現 label，FL-52 (c)／(d) 判定失敗。
- **FL-52 窮舉擴充**：
> - 對每個 (scope_kind, slot)，取該 scope 可能出現的 `gate` 值：`GATE_FIXED` ∪ {`shadow_run_pending`, `settlement_smoke_pending`}，quant 有登記時再加 `forward_n_below_min`。
> - 這些值的每一個非空子集，都恰好有一個項目，而且 `covers` 聯集等於該子集。
> - 另加斷言：族群 {`forward_n_below_min`, `replay_review_pending`} 選不到「只有第 4 項」。

### RC′-4｜A-77 第 5 項：整項取代 r3′ 的版本

> 5. **X2 確認的必要條件含 d ∉ (i)**（風控 2026-10-17 單項確認）。d ∈ (i)、又有正面休市證據時，屬於證據矛盾，一律維持異常待查證，不論獨立來源的結果如何。這時 d 仍經 (i) 是觀察日，這一列照原值計分。
>    - 記 WARNING，寫入 `forecast_ledger_events.kind = session_calendar_conflict`，交 data-engineer 查根因。
>      - payload：`session_date`、`evidence ∈ {weekend, official_holiday}`、`origin ∈ {x2_check, candidate_t}`、受檢 bar 的參照。
>    - **查證照跑**：矛盾列照樣走事先宣告 §6.3「查證程序」①～③，每次查詢都照常新增查證紀錄（查不到也記），由 qa 核對涵蓋率。
>      - **但查證結果不改變這一列的狀態**：不得確認 X2，不得移出觀察日，不得寫入 `x2_confirmed_non_session`。
>      - 任何程式路徑都不得依查證紀錄改變 d 的觀察日身分（FL-19 (d) 斷言）。
>    - **揭露**：`session_calendar_conflict` 的筆數（以不同的 `session_date` 計，並依 `origin` 分列）在驗證報告 §4.2 單獨揭露，不得併入其他異常待查證筆數。
>    - **不自動解除**：要解除矛盾，只能修訂本點並送風控。不得依時間經過、查證次數或查證結果自動解除。
>    - 有了這一條，「(ii) 扣除 X2 確認日」就等於「從觀察日移除 X2 確認日」。
- 待決事項 data-engineer 加 suggested：查根因時一併確認，個股與族群成員在 d 的 bars 有沒有進入 PIT 輸入或結算。
- 待決事項 quant 加：§4.2 單獨揭露 `session_calendar_conflict` 筆數。

### RC′-5｜A-75 (iv)；FL-19 (e)

- 定位：A-75 候選 T 的 (iv) 與其後的處理行，整段取代 r3′ 的版本。
> - (iv) T 不是週末，也不是已接入官方休市日表所列的休市日（風控 2026-10-17 單項確認）。
> - (iii) 或 (iv) 不成立 → 該 session 記 `inputs_not_ready`，不得退回前一個 session。依 A-77 第 5 項，(iii) 在結構上不會成立；保留它是縱深防禦，以測試斷言。
> - **(iv) 不成立時**：候選 T 依 (i) 必定 ∈ D-8.1 (i)，所以這必然是 A-77 第 5 項的同一種證據矛盾。
>   - 記 WARNING，寫入 `session_calendar_conflict`（`origin = candidate_t`）；
>   - 一併計入 A-77 第 5 項的揭露與根因查證。
> - (iv) 的「週末」部分受 A-77 第 9 項（F-8）約束：查證若發現週末交易日，(iv) 與 A-77 第 2 項的週末部分同一批修訂，並送風控。
- FL-19 (e) 整格取代：
> - (e) 拆成兩格：
>   - (e)① 候選 T 是 X2 確認日：依 A-77 第 5 項，T ∈ (i) 時結構上不可能，屬縱深防禦。測試注入違反前提的狀態，期望 `inputs_not_ready`，而且不退回前一個 session。
>   - (e)② 候選 T 是週末，而且 T ∈ (i)：期望 `inputs_not_ready`、WARNING、寫入 `session_calendar_conflict`（`origin = candidate_t`），而且不退回前一個 session。
- FL-19 (d) 加斷言：注入「獨立來源沒有 d」的查證結果後，d 仍是觀察日，也沒有寫入 `x2_confirmed_non_session`。
- 這樣 FL-19 仍是 (a)～(g)。原有三個 fixture 保留。

### RC′-6｜A-72（R3-10）：`OnDemandGateClosedView`

- 定位：r3′ R3-10「狀態字面」一點之前加以下各點。
> - `disclosure_fragment_ids` 的型別是封閉列舉 `ON_DEMAND_CLOSED_DISCLOSURES`（`display.py`，`Literal`）。
>   - 清單每一項都要有風控核可的片段，**不得含任何方向衍生片段**。凡是提及、暗示或預告方向、label、天氣、方向色、「結算後列示」的片段都算，包括 LM-94、LM-95、LM-105、LM-106。
>   - 增列要修訂本點並送風控。核可之前清單為空。
> - `status_fragment_id` 也是封閉列舉。v1 只有一個值，就是 R3-10 的新狀態句。
> - FL-52b (9b) 的全文掃描，涵蓋 `status_fragment_id` 與 `disclosure_fragment_ids` 渲染出來的全文，不只掃 JSON 欄位。FL-38 的 schema 斷言另加：清單以外的 ID 驗證失敗。
> - **新狀態句的限制**（交 creative-lead 起草）：不得預告開始記錄的日期，也不得暗示「快要開放」。
> - **前端不得補方向**：渲染 `OnDemandGateClosedView` 的元件，不得引用 `OutlookView` 衍生型別。收到這個回應之後，也不得改從其他端點取得同一檔的 label、天氣或方向色（前端契約測試，比照 FL-60 (d)）。

### RC′-7｜方向標示

- A-62 方向行改為：「**收緊＋有條件放寬（R2，依風控 r3 審查 C-3；片段核可前 fail-closed）**」。
- A-77 方向行改為：「收緊（第 5 項相對事先宣告為補定義（兩面），風控 2026-10-17 單項確認）」。
- ADR 內如有方向統計，改為 19／2／9／1／2（見第四節）。

### RC′-8｜A-63 第 5 項、R3-13、A-57、A-79

**(1) A-63 第 5 項：整項取代**
> 5. A-57 的 G_eff 不只樣本數一項時，用來取代 LM-98 的片段，依第 11 點的涵蓋規則選用。各 scope 的變體另受以下限制（風控 2026-10-17 RC′-8）：
>    - **個股變體**：不得聲稱展望在任何頁面顯示（不得沿用 LM-94「只在個股詳細頁顯示」的寫法），也不得預告開放時點；
>    - **族群變體**：不得暗示到了 150 筆就會開放；
>    - 要在 D_v 前核可。

**(2) R3-13 的 A-54 加註：末尾加一句（逐字）**
> `replay_review_pending` 常駐期間，顯示面確認 (e) 第 1 點改由 LM-86＋A-63 第 5 項（個股變體）承接；該片段不得聲稱展望在本頁或他頁顯示。

**(3) A-57（R3-2）：「`replay_review_pending` 成立，若且唯若…」之後加**
> - **`replay_review_approved` 的寫入前提**（風控 2026-10-17 RC′-8；事先宣告 §4.7、§12）：
>   - payload 必須帶 `replay_claim_id`。寫入函式在同一個交易內驗證四件事：該 claim 在 `forecast_claim_registry` 存在、`kind = replay`、(scope_kind, horizon) 與事件相同、`counts_toward_m = 1`。任一項不成立就拒絕寫入。
>   - payload 另帶回放報告路徑、quant 與 qa 的審查紀錄路徑，以及報告中「已知偏誤揭露」一節的定位。qa 核對報告確實揭露已知偏誤；族群與個股要揭露存活者偏差，以及除權息紀錄的起點。
>   - **不得用一份名目上的回放報告，或已知有偏誤卻沒有揭露的回放報告，來解除閘門。**
>   - 族群與個股另外要先完成事先宣告 §4.7 的修訂並經核可。現行 §4.7 規定這兩類重放「只能當內部研究…不上畫面」，修訂核可之前，不得為族群或個股寫入這個事件。這是把既有約束明列出來，不是另立規則。
- FL-53 (f) 加三個 loader／writer 拒絕的 fixture：claim 不存在或 `kind ≠ replay`；`counts_toward_m = 0`；(scope_kind, horizon) 不符。

**(4) A-79 Consequences：r3′ 新增四點中的第三點，整點改寫（逐字）**
> 個股與族群在 v1 沒有回放計畫（事先宣告 §4.7），所以常駐 `gated`，任何畫面都不顯示其方向；A-63 第 5 項要在 D_v 前核可。
- 「#10 不能關掉固定閘門」不另立一點：A-57 本文和 CEO 說明第 7 點已經涵蓋。
- Consequences「D-20 的兩面後果」第一子點（已依 r3 A-79 改成「v1 期間不論驗證狀態」）的句尾加：「（v1 期間個股與族群的 `unavailable_reason` 實際是 `gated`，因為 `replay_review_pending` 常駐；`gated` 的優先序高於 `surface_not_permitted`）」。這是文字更正，方向不變。

### RC′-9｜A-79 的 CEO 說明（整節，逐字）

以風控 r3 審查第三節為底：第 1、6、7 點換成 RC′-9 的版本，第 2～5 點照 r3 審查原文，另加第 8 點。
> 1. 第一版上線期間，個股的 5 日方向一律不拿來算行動建議。另外，因為個股沒有歷史回放報告，**個股詳細頁也不會顯示 5 日方向**，只會照實寫「5 日展望目前不可用（原因）」並附驗證狀態。要開放，得另外送審。
> 2. 開始正式記錄預測之前，要先核可的文字又多了幾句，包括一些很多年後才會用到的說明，以及作廢紀錄的呈現方式。開始記錄的時間可能再往後延。
> 3. 正式記錄開始之前，臨時查詢個股也不會給出方向，系統也不會「算了但不記帳」。開始之後，早上 8:30 前已經產生的臨時查詢紀錄，白天再查會照常顯示同一筆，因為它是在預測期間開始前就定下的。
> 4. 主機如果在交易日收盤定案前開機，市場資料可能只抓到盤中值；當天如果沒有再抓，那一天會照實記成缺日，不會補造。之後約 60 個交易日內，部分紀錄可能判成證據不足或作廢，作廢的會算進最壞情境。根本修法要改 ADR-0012（已核可），屆時會請你核可。
> 5. 大盤資料必須是收盤定案後才抓到的才能用。重抓失敗的日子照實記成缺日，不會用暫定值頂替，也不會改用前一天的資料。
> 6. 族群因為同樣沒有回放報告，第一版期間不會顯示方向，即使累積到 150 筆也一樣。日後如果開放，若有資料違規讓筆數掉回 150 以下，已經顯示過方向的紀錄會重新隱藏，事件會在驗證報告揭露。
> 7. 閘門條件中的「影子試跑」「上線天數與結算筆數」仍待你在 #10 裁示。但已核可 ADR 規定的條件（族群 150 筆、每個範圍都要有經審查的回放報告）不能用這個裁示關掉。目前只有大盤有回放計畫。
> 8. **待你決定（不急）**：第一版要不要讓個股或族群顯示方向。不決定的話，就維持不顯示；這在風險上是安全的。要開放，只有兩條路：做該範圍的回放（有已知偏誤，要照實揭露），或修訂 ADR-0025 的閘門。兩條路都要再送風控。

### 連帶補漏（掛在 A-57／A-77，方向不變）

- D-3 的 `forecast_ledger_events` 列舉（9ba01d6 L275）改為 `kind ∈ {db_restored, f3_resume_approved, pit_violation_confirmed, replay_review_approved, x2_confirmed_non_session, session_calendar_conflict}`。r3′ 已經引用後三個值，D-3 卻沒有列。原文逐字進修訂紀錄。
- 待決 creative-lead 加：RC′-3 的多閘門片段（每個 (scope_kind, slot) 的涵蓋變體或並列片段），以及 A-63 第 5 項個股與族群變體的 RC′-8 限制。
- 待決 CEO 加：知悉 CEO 說明第 1、6、7 點；第 8 點不急。

## 三、ADR-0028 A-96′／A-97′ 條文

這兩條取代我 r3′ 第六節的 A-96、A-97 建議版，和 PM 的 PRD 修訂同一批送 qa，不併入 ADR-0027 r3″ 的 commit。

### A-96′

**(1) D-6 新增第 13 點（揭露既有限制）**
> 13. （A-96′）個股詳細頁有幾類數字，都由前端以 `/api/bars` 回傳的同一份日線（`computeKeyLevels`）計算，不讀 `valuation_state`：
>     - 關鍵價位；
>     - 六項觀察條件；
>     - 由同一份日線衍生的數字：操作摘要（`DecisionCard`）的收盤、停損、停利，以及關鍵價位面板的停損與目標參考。
>     - 資料列有日期異常時，照樣進入這些計算。本 ADR 不改變計算，只要求揭露（CS-26）。
>     - 這同時適用於持股與「確認未持有」的標的。非持股沒有 `build_summary` 列；CS-26 第 1 點的逐列標記落地之前，非持股完全沒有日期異常的檢查。
>     - 要不要在資料層剔除異常列，屬於第 10 點「寫入側品質閘門另案」，本點不處理。

**(2) CS-4 補充（澄清，方向不變）**
> - CS-4 只約束上列的後端計算模組。前端顯示層可以讀 `valuation_state`，以及 CS-26 的逐列 `date_anomaly` 標記，但只能用來做同區塊揭露，不得改變任何計算或計算的輸入。
> - 這句只是澄清現行範圍，不得被讀成禁止日後改採「附原因、不渲染」的 fail-closed 做法。那屬於顯示面變更，要另外送風控。
> - CS-4 的 grep 範圍擴到 `row_date_anomaly` 與 `/api/bars` 的 `date_anomaly` 欄位：上列模組不得呼叫或讀取。這是落實 CS-26「計算不變」。

**(3) CS-26（收緊；風控 2026-10-17 A-96 條件）**
> - 持股價格區塊在 `valuation_state = date_anomaly` 時渲染 LM-70（PM AC-B5a-10），依 CS-27。
> 1. **觸發條件：逐列標記，涵蓋實際進入計算的日線。**
>    - `close_state.py` 抽出純函式 `row_date_anomaly(trade_date, *, D, phase, calendar) -> sub_reason | None`，其中 D、phase 依 D-4「先定義」，calendar 是同一個 `SessionCalendar`。D-4 的 R2、R2′、R2″、R2‴ 改成呼叫它，輸出不變（CST-2 維持綠燈）。
>    - 判定規則：
>      - `trade_date > D` → `future_date`；
>      - `trade_date == D`、D 是交易日，而且在 `pre_open` → `before_open`；
>      - `trade_date == D`、D 不是交易日 → basis＝official 時為 `official_conflict`，否則為 `not_a_session`；
>      - `trade_date < D`，而且 `is_session(trade_date)` 為 False → `unconfirmed_session`。
>        - 這一項對 `P < trade_date < D` 的列就是 R2‴；對 `trade_date < P` 的歷史列是延伸。
>        - D-4 本身仍只在 `price_date > P` 時套用 R2‴；`price_date < P` 仍走 R6，估值狀態不變。
>    - `GET /api/bars/{symbol}` 的每一列帶 `date_anomaly: Literal["future_date","before_open","official_conflict","not_a_session","unconfirmed_session"] | None`，由後端以 `row_date_anomaly` 逐列計算。
>    - envelope 另帶兩個欄位：
>      - `date_anomaly_rows: int`；
>      - `anomaly_valid_until`：語意同 D-4 的 `state_valid_until`，前端資料層依它重新取得。
>    - 後端計算的約束：
>      - 一次請求只讀一次時鐘，D 由 `now.astimezone(VS-1)` 取得（同 CS-3）；
>      - calendar 和 `build_summary` 用同一個建構函式（官方優先，退回 D-9 觀察日曆），不得另建；
>      - 每個請求最多一次 `market_session_evidence` 讀取，窗口依 D-9 第 6 點，用該序列各列日期的最小值代入。
>    - 持股與非持股一體適用。`/api/bars` 不讀 `valuation_state`，也不依是否持有分流。
>    - **前端不得另寫判定。** 觸發條件只有一個：傳入 `computeKeyLevels` 的那一份 `bars` 陣列中，任一列 `date_anomaly != null`。觸發看整個陣列，所以比實際取用的窗口寬，會多揭露，不會少揭露。
>    - 前端揭露元件不得出現 `new Date(`、`Date.now`、時段常數，也不得 import `tradingCalendar.ts`（比照 CS-5）。
> 2. **揭露範圍與位置**：
>    - 範圍以封閉清單 `BARS_DERIVED_BLOCKS` 登記：
>      - `KeyLevelsPanel`（關鍵價位，含停損與目標參考）；
>      - `EntryObservationPanel`（六項觀察條件）；
>      - `DecisionCard`（收盤、停損、停利格）。
>    - `position/[symbol]/` 底下，凡是接收 `bars` 陣列做數值計算，或呼叫 `computeKeyLevels`、`evaluateEntryObservation` 的元件，都必須在清單內（AST 契約測試）。
>    - 每個區塊都在同一區塊內渲染揭露：不收合、不放在 `<details>` 內，也不只用 hover 或 tooltip。
>    - 「資料截至 {MM-DD}」徽章（bars 的 `last_bar_date`）旁要能看到同一揭露。徽章所指的日期本身是異常列時，徽章不得用正常資料日期的樣式呈現。
>    - 沒有異常列時，不出現揭露。
> 3. **字面**：
>    - 交 creative-lead 起草、風控逐字審，不得有「仍可參考」之類的弱化語氣；
>    - `sub_reason` 不渲染成字面（同 D-4）；
>    - 字面核可之前，T1-17 不得合併（比照 D-5 末句）。
> 4. **計算不變**：揭露不改變任何計算，也不改變計算的輸入。
> 5. **行動計畫鏈的前提**：本條的核可，以「ADR-0027 的行動計畫鏈不會吃進日期異常的價格」為前提〔推論〕，依據是 ADR-0027 FL-25。fixture 見 (5)。

**(4) 測試要求（ADR-0028，從 CST-10 起續編）**
> - **CST-10**：`row_date_anomaly` 的性質測試。
>   - 對任意 `price_date > P` 的輸入，結果和 D-4 R2～R2‴ 的 `sub_reason` 逐位相同；
>   - 五個 `sub_reason` 各一個 fixture；
>   - 歷史週末列（`< P`）→ `unconfirmed_session`。
> - **CST-11**：`/api/bars` 契約。
>   - 每一列都有 `date_anomaly` 欄；
>   - 每個請求只讀一次時鐘、最多一次 evidence 讀取（計數）；
>   - 同一序列在持股與非持股時結果相同；
>   - `anomaly_valid_until` 跨過 VS-2 時，`before_open` 消失。
> - **CST-12**：前端契約與 e2e。
>   - `BARS_DERIVED_BLOCKS` 的 AST 列舉；
>   - 揭露 DOM 不在 `<details>` 內；
>   - 徽章旁可見揭露；
>   - 沒有異常時不出現揭露；
>   - 375 與 1280 寬度實機驗收（AC-B5a-13）。

**(5) ADR-0027 FL-25 增補：和 A-96′ 同一批另開 commit，不放進 r3″ commit；修訂紀錄註明「依 ADR-0028 A-96′（風控 2026-10-17 A-96 CS-26 第 4 點）」**
> - FL-25 加 fixture：構造 `build_summary` 的輸入，使 `date_anomaly` 的五個 `sub_reason`（`future_date`、`before_open`、`official_conflict`、`not_a_session`、`unconfirmed_session`）各出現一次。plan 組合價位時，五格都期望價位缺席，並附 `MissingItem(code="E-PRICE-UNUSABLE", source_status="failed_check")`。
> - plan 端不得讀 `valuation_state`（ADR-0028 CS-4）。fixture 只構造輸入，斷言 plan 的輸出。
> - 另加兩個對抗格：`not_a_session`（週末）與 `unconfirmed_session`（週末），構造「市場 DB 在該日也有定案後 ok run，而且收盤相同」。期望該日依 A-75 (iv) 不會成為候選 T，記 `inputs_not_ready` 與 `session_calendar_conflict`，因此沒有 plan 讀到這個價格。官方休市日的對抗格見第五節第 2 項。

### A-97′

> - **CS-27**（A-97′，收緊；風控 2026-10-17 A-97 條件）：個股詳細頁顯示的持股價格與估值狀態，取自 `build_summary` 同一列的輸出（`valuation_state`，以及同一個 `price_date`），用和庫存頁同一個前端狀態元件、同一張 D-5 對應表呈現。
>   - 個股頁不得另外計算狀態，也不得用 bars 的 `last_bar_date` 代替 `reference_date`。
>   - 前端契約測試：同一檔在兩頁的價格、日期、字面 ID 逐位相同（PV-52、AC-B5a-10）。
>   - 非持股（沒有 `build_summary` 列）不顯示估值狀態，維持現行徽章。**這類標的的日期異常由 CS-26 第 1 點的逐列標記涵蓋，不得有沒有檢查的情形。** 契約測試：非持股、bars 含異常列時，渲染 CS-26 的揭露（AC-B5a-13）。
>   - （採用風控 suggested）同一頁上有多顆日期徽章時，每顆都要標明它指的是什麼，例如「日線資料截至」「估值價格日期」，不得出現兩個沒有說明的日期。字面交 creative-lead 起草、風控審。
> - 排入 T1-17，由 dev-lead（`/api/bars`、`close_state.py`）與 frontend-engineer 承接，qa-e2e 驗收。

**T1-17 能否逐列標記：能。** 依據見第一節第 4 點。做法上要注意兩件事：
- `bars.py` L89 的 `end = date.today()` 是伺服器的本地日期。標記用的 D 不得取這個值，要依 CS-3 取得。窗口本身不在本次範圍內。
- 我沒有讀 `DecisionCard` 的原始碼。它的停損、停利出自 `computeKeyLevels`，這點是依 `page.tsx` L216-219 的註解。

## 四、方向統計

**ADR-0027（A-54～A-86，r3＋r3′＋r3″）**

| 方向 | 條數 | 條號 |
|---|---|---|
| 收緊 | 19 | A-54～A-57、A-60、A-61、A-63～A-67、A-69、A-70、A-72、A-74～A-78 |
| 補定義（兩面） | 2 | A-71、A-73 |
| 不變 | 9 | A-59、A-79～A-86 |
| 不變＋收緊 | 1 | A-58 |
| 含有條件放寬的兩面 | 2 | A-62「收緊＋有條件放寬（R2，依風控 r3 審查 C-3；片段核可前 fail-closed）」；A-68（和 V10-12 逐字相同） |

- 合計 33，寫成「19／2／9／1／2」。A-77 帶第 5 項的加註。
- r3″ 各項掛在哪一條、方向是什麼：

| 項目 | 掛在 | 方向 |
|---|---|---|
| RC′-1、RC′-2、RC′-3 | A-63／A-57 | 收緊 |
| RC′-4 | A-77 | 第 5 項是補定義（兩面），已經風控確認；另外三句是收緊 |
| RC′-5 | A-75 | 收緊 |
| RC′-6 | A-72 | 收緊 |
| RC′-7 | — | 只改標示 |
| RC′-8 | A-63、A-57、A-54 | 收緊 |
| RC′-8 | A-79 | 文字，不變 |
| RC′-9 | A-79 | 文字，不變 |
| D-3 列舉補漏 | — | 不變 |
| FL-58 (e) 筆誤更正 | — | 回到風控 R3-5 原文 |

- 沒有任何一條換類別。

**ADR-0028**

| 條 | 方向 |
|---|---|
| A-96′ | 不變（D-6 第 13 點、CS-4 澄清）＋收緊（CS-4 grep 擴範圍、CS-26、FL-25 fixture） |
| A-97′ | 收緊 |

## 五、需回送風控項

**回送（超出風控條件，方向是收緊）：**
1. **CS-26 第 1 點：歷史列 `trade_date < P` 的延伸。**
   - 風控要求的是「用同一個判定函式」。D-4 的 R2～R2‴ 只處理 `price_date > P` 的位置，照字面套用的話，歷史日線裡的週末或休市列都不會被標記，可是它們照樣進入 `computeKeyLevels`。
   - 我把 `unconfirmed_session` 延伸到所有 `trade_date < D` 而且不是交易日的列，D-4 的輸出不變。
   - 方向：收緊，會多揭露。風控如果不採用，就退回只標 `> P` 的列。
2. **FL-25 前提的缺口：官方休市日要用同一份來源。**
   - 兩個對抗格要成立，前提是 ADR-0027 A-75 (iv)／A-77 的「已接入官方休市日表」，和 ADR-0028 basis＝official 用的官方日曆（T1-13）是同一份來源。〔未查證〕
   - 如果兩者不同，會出現這條路徑：官方休市的平日，市場 DB 又有定案後 run → T 可能就是那一天 → FL-25 的等值檢查通過 → 異常價格進入行動計畫。這會讓風控「行動計畫鏈不吃異常 bar」的推論在 `official_conflict` 和官方休市日的 `unconfirmed_session` 上不成立。
   - 建議 ADR-0027 加一句：「A-75 (iv)、A-77 的官方休市日表，與 ADR-0028 `OfficialSessionCalendar` 使用同一份來源（單一定義）」，再補兩個官方休市日對抗格。
   - 這會動到風控已經定案的 A-75／A-77，所以要風控確認，不放進 r3″。

**請風控裁定的缺口（不在風控條件內，我沒有寫進條文）：**

3. (a) **指標序列。** 六項觀察條件也讀 `/api/signals` 的指標，那些指標由後端用同一份異常列算出來。CS-26 的觸發條件只看 `/api/bars`。是否要 `/api/signals` 也帶 `date_anomaly_rows`，並併入同一個觸發條件？
   (b) **K 線圖。** `PriceChart` 會把異常列畫出來，它不在 `BARS_DERIVED_BLOCKS` 的範圍內。
   (c) **A-27 (e) 和 RC′-1 是同一類遮蔽。** 大盤或個股在 `suspended_f3`／`withdrawn_f2`、G_eff 非空、已結算時，(a) 不擋，label 會出現。可是 (e) 只在 `gated` 時附 PV-45。建議 (e) 改成「大盤或個股，而且 G_eff 非空，不論 `display_state`」。

**知會（我判斷在條件內，coordinator 如果認為超出，就一併回送）：**
- RC′-2 的比較基準用 `e_read_at`，不用 `computed_at`，比字面嚴。另外，`OutlookView` 在快照落後時只會把族群的 `shown` 調成 `gated`，這是 FL-54 (e) 唯一的例外。
- RC′-8：族群與個股寫入 `replay_review_approved`，另外要先修訂事先宣告 §4.7（L886 規定這類重放「不上畫面」）。所以 CEO 說明第 8 點的第一條路（做回放），實際上也要修事先宣告。CEO 說明照風控原文逐字使用，我沒有改動。
- FL-58 (e)：更正 r3′ 的筆誤，恢復風控 R3-5 原文的「族群列」限定。

**其他：** 我沒有改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有跑程式、測試或 git。這是唯讀的架構文件，Codex 不適用。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3prime單項確認含A96A97與ACB5a-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3prime補正-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3提案審查-風控.md（第三節 CEO 說明）
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（D-3 L263-275、D-11.1 L458-465、D-11.2 L466-480、D-11.4 L482-581、FL-25 L817）
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md（D-4 L121-156、D-6 L197-209、D-9 L224-271、CS-4 L288、CST-1～9）
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md（L886、L1130-1151、L1574）
- /home/user/AICompany/apps/stock-desk/backend/app/api/bars.py（L82-106）
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/page.tsx（L137-146、L216-227、L271-273、L484-510）
- /home/user/AICompany/work/stock-desk-新定位-PRD-2026-10-16.md（T1-17，L785）

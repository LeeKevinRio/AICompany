# ADR-0027 r3″ 增補（RC″-1～RC″-5、N-1）與第八批 T-1～T-5（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 r3″ 增補（RC″）＋第八批 T-1～T-5（tech-architect，唯讀）

## 一、結論

**RC″-1～RC″-5、N-1 都已寫成條文，可交 tech-writer 一次套用 r3＋r3′＋r3″＋本增補。** 版本衝突時的優先序是：本增補 > r3″ > r3′ > r3。所有條文都掛在既有 A 編號下，沒有新增 A-87 以後的條號，統計維持 19／2／9／1／2，沒有任何一條換類別。

**RC″-2 擇 (b)：改用單調遞增的事件序號。** 不採 (a)，理由有四：
1. **(a) 單獨用補不起來。** `recorded_at` 是 store 時鐘在 insert 時填的（ADR-0027 D-2 第 3 點，L242）。寫入者可能先在 Python 端取好時間，才拿到寫入鎖。這樣即使 snapshot 在 `BEGIN IMMEDIATE` 拿到鎖之後才記 `e_read_at`，事件的 `recorded_at` 仍可能早於 `e_read_at`、卻晚於 snapshot 才 commit。要補，就得連帶約束兩個 process（L768）裡所有寫 E 相關事件和 supersede outcome 的地方，一律在拿到鎖之後才取時間，這已經超出風控 (a) 的字面。
2. **(a) 依賴牆鐘單調。** 主機會休眠、NTP 也可能把時間往回調。時鐘一倒退，就會漏判，而漏判是不安全的方向。
3. **(a) 寫入鎖要撐過整段 snapshot 計算。** 計算含 bootstrap，耗時多長沒有實測〔推論〕。這段期間 API process 寫 on-demand 紀錄要排隊等 `busy_timeout`，逾時就會寫入失敗。
4. **(b) 符合既有的 store 設計。** ADR-0012 D-2 規定 `run_id INTEGER PRIMARY KEY AUTOINCREMENT` 單調、永不重用，C-50 也用同樣的「序號上界」做法（`run_id ≤ source_run_max`，L849）；ADR-0026 的 `event_id` 同樣是 AUTOINCREMENT。依 SQLite 的單一寫入者語意，序號順序就是 commit 順序。所以這個判定不依賴任何時鐘，與 journal 模式無關，也不必拉長持鎖時間。

**coordinator 加進來的 T-1～T-5 也已處理完：**
- T-1～T-4 都寫成條文。
- T-5 的答覆是：**結構上可能發生，R-5 不能免除**。路徑見第二節。

**超出風控寫法、要明確標出的地方（都是收緊或一致性，詳見第四節）：**
- RC″-1 連帶同步 A-62 R2 第 1 點；
- RC″-2 保留 `e_read_at` 當稽核欄位，另加一格「時鐘倒退」fixture；
- RC″-5 的欄位命名，以及幾項額外的一致性驗證；
- N-1 把 `basis = verified` 也納入偵測，並且不重複寫入；
- T-3 改成不分頁面一律附 LM-120。

## 二、增補條文

「＞」後面是給 tech-writer 的條文。被取代的 9ba01d6 原文一律逐字進修訂紀錄；r3、r3′、r3″ 的中間版沒有落過檔，不進修訂紀錄。

### RC″-1｜A-63／A-65：A-27 (e) 改條件（收緊）

**(1) D-11.4 第 11 點 (e)：整條取代**
> - (e) **大盤或個股，而且 G_eff 非空，不論 `display_state`**：已結算紀錄若顯示 label，回應的 `disclosure_fragment_ids` 要含 PV-45 固定句，在同一區塊呈現（風控 2026-10-17 RC″-1）。
>   - G_eff 的定義見 A-57 (iv)。大盤與個股的 G_eff 就是「判定 `display_state` 的同一列最新 daily snapshot」的 `gate`。
>   - (e) 不以 `display_state` 的任何值為條件；`suspended_f3`、`withdrawn_f2` 期間同樣適用。

- 修訂紀錄逐字保留 9ba01d6 L563 的原文：「(e) 大盤或個股在 `gated` 時，已結算紀錄若顯示 label，回應的 `disclosure_fragment_ids` 要含 PV-45 固定句，在同一區塊呈現；」

**(2) A-65（r3′ S-4 的那一句）：改為**
> (e) PV-45（大盤或個股，而且 G_eff 非空，不論 `display_state`）與 PA-4（依既有規則）照樣適用於已結算的排程列。

**(3) A-62 R2 第 1 點同步〔超出風控字面，屬一致性修正〕：把「大盤或個股在 `gated` 時照樣附 (e) PV-45」改為**
> 大盤或個股依 (e)（G_eff 非空，不論 `display_state`）照樣附 PV-45。

**(4) FL-59 加四格**
> - FL-59 加四格（RC″-1）：大盤 × {`suspended_f3`, `withdrawn_f2`}、個股 × {`suspended_f3`, `withdrawn_f2`}。每一格的 G_eff ＝ {`replay_review_pending`}，紀錄已結算 → 期望出現 label（只在 `settled_record` 內），而且 `disclosure_fragment_ids` 含 PV-45。

- 四格放在 FL-59，不放 FL-58，這樣 FL-58 仍維持 (e1)～(e6)，符合核對第 10 點。

### RC″-2｜A-63（RC′-2）：比較基準改成單調序號（收緊）

**(1) RC′-2 的條文：以下各點整點取代 r3″ 的對應點，其餘不動**
> - `e_changed_since` 只由 `views` 的單一函式 `e_changed_since(snapshot)` 判定：只要有任何一筆「會改變 E 成員或 n 的事件」，序號大於該 snapshot 記下的對應讀取序號，就為真。
> - 為真時，`pa9_holds` 一律為真，直到之後產出一筆讀取序號涵蓋該事件的 daily snapshot 為止。
> - **事件封閉清單 `E_CHANGING_EVENTS`**：
>   - `forecast_ledger_events.kind ∈ {pit_violation_confirmed, x2_confirmed_non_session, db_restored}`，依 `event_id`；
>   - `forecast_outcome` 中 `supersedes_id IS NOT NULL` 的列，依 `outcome_id`；
>   - 不按 claim 篩選：任一筆成立，所有族群 claim 都適用。
> - **比較基準：單調遞增序號，不用時間戳**（風控 2026-10-17 RC″-2，二選一採 (b)）：
>   - `forecast_ledger_events.event_id` 與 `forecast_outcome.outcome_id` 都是 `INTEGER PRIMARY KEY AUTOINCREMENT`：單調遞增、永不重用。遷移與備份還原都不得重編（比照 ADR-0012 D-2 的 `run_id`）。
>   - snapshot 的計算在一個明確開啟的 read transaction 內讀 E，並在同一個 transaction 內讀出兩個值，寫入 `stats_json`：
>     - `e_read_event_seq` ＝ 看得到的 `forecast_ledger_events.event_id` 最大值；
>     - `e_read_outcome_seq` ＝ 看得到的 `supersedes_id IS NOT NULL` 列中，`outcome_id` 的最大值。
>     - 沒有列時記 0。
>   - `e_changed_since(snapshot)` 為真，若且唯若下列兩項任一成立：
>     - 存在 `kind ∈ E_CHANGING_EVENTS`、而且 `event_id > e_read_event_seq` 的事件；
>     - 存在 `supersedes_id IS NOT NULL`、而且 `outcome_id > e_read_outcome_seq` 的列。
>     - 兩個欄位任一缺漏或不是整數，一律為真。
>   - 依據：
>     - SQLite 同一個資料庫同時只有一個寫入交易，不論 journal 模式；AUTOINCREMENT 在寫入交易內配號，所以序號順序就是 commit 順序。
>     - 因此，read transaction 看得到的最大序號是 S 時，當時還沒 commit、或之後才 commit 的列，序號都大於 S。
>     - 這個判定不依賴任何時鐘，也不要求讀 E 和寫入 snapshot 在同一個交易內。
>   - `stats_json.e_read_at`（讀 E 那次 read transaction 開始時的 store 時鐘）保留為稽核欄位，**不作為任何判定的比較基準**。比較一律用序號，不用 `e_read_at`，也不用 `computed_at`。
>   - 不採 (a)（同一個 `BEGIN IMMEDIATE`）的理由：
>     - `recorded_at` 可能在寫入者拿到鎖之前就取好了；
>     - 牆鐘不保證單調；
>     - 持鎖時間會涵蓋整段 snapshot 計算，第二個寫入者（L768）會被擋在 `busy_timeout`。

**(2) D-3（連帶）**
- `forecast_outcome` 的「識別」子項改為：「`outcome_id`（`INTEGER PRIMARY KEY AUTOINCREMENT`，RC″-2）、`forecast_id`」。原文 L264「識別：`outcome_id`、`forecast_id`；」逐字進修訂紀錄。
- `forecast_ledger_events(event_id, …)` 改為 `event_id INTEGER PRIMARY KEY AUTOINCREMENT`。L275 的原文已依 r3″ 進修訂紀錄，不重複。

**(3) FL-58 (e6)：取代 r3″ 的「另一格」，並加兩格**
> - 另一格：事件在 snapshot 讀 E 之後、寫入 snapshot 之前 commit → 期望同樣 fail-closed。
> - **RC″-2 格**：事件交易早於 snapshot 開始（store 時鐘填入的 `recorded_at` 早於該 snapshot 的 `e_read_at`），但晚於 snapshot commit → 期望 fail-closed（`e_changed_since` 為真）。
> - 時鐘無關格〔超出字面，收緊〕：注入倒退的 store 時鐘，判定結果和時鐘正常時逐位相同。

### RC″-3｜A-63：FL-52 窮舉範圍（收緊）＋T-1（不變）

整條取代 r3″ 的「FL-52 窮舉擴充」：
> - 對每一個登記在 `GATE_SLOT_SCOPES`（T-2）的 (scope_kind, slot)，取該 scope 可能出現的 `gate` 值集合 P(scope) ＝ `GATE_FIXED`（該 scope）∪ 已啟用的 `GATE_ADDITIONAL`（風控第八批 T-1）。
>   - `forward_n_below_min`：**族群一律加入 `forward_n_below_min`；大盤與個股在 quant 有登記時才加入**（風控 2026-10-17 RC″-3）。
>   - 未啟用的 `GATE_ADDITIONAL` 值不在窮舉範圍內。
> - P(scope) 的每一個非空子集，都恰好有一個項目，而且 `covers` 聯集等於該子集。
> - 斷言：
>   - 族群 {`forward_n_below_min`, `replay_review_pending`} 選不到「只有第 4 項」；
>   - 族群的 P 不論 quant 是否登記，都含 `forward_n_below_min`。
> - **loader 守門（T-1，掛 A-57 R3-2「#10 只能加」）**：啟用任一 `GATE_ADDITIONAL` 值時，loader 要用和 FL-52 同一個函式 `gate_coverage_gaps(...)`，檢查每個 (scope_kind, slot) 中含該新值的每一個非空子集，是否都有已核可的覆蓋片段。缺任何一個，就拒絕啟用、啟動失敗（fail-closed）。
>   - fixture：在沒有片段的情況下啟用 `shadow_run_pending` → loader 拒絕。

### RC″-4｜A-79：CEO 說明第 8 點（文字，不變）

整點以下文逐字取代：
> 8. **待你決定（不急）**：第一版要不要讓個股或族群顯示方向。不決定的話，就維持不顯示；這在風險上是安全的。要開放，只有兩條路：做該範圍的回放，或修訂 ADR-0025 的閘門。做回放的話，要先修改事先宣告（目前規定個股與族群的回放只能當內部研究、不上畫面），回放結果有已知偏誤，要照實揭露。兩條路都要再送風控。

### RC″-5｜A-77 第 7 項：整項取代（收緊，稽核性）

> 7. **X2 確認的登記**（風控 2026-10-17 RC″-5）：只增不改，寫入 `forecast_ledger_events.kind = x2_confirmed_non_session`。**這筆事件本身就是 X2 的判定紀錄**；`basis = direct` 沒有查證紀錄，以此為準（事先宣告 §6.3 判定紀錄、R-C ④）。
>    - **payload**：
>      - `session_date`；
>      - `basis ∈ {direct, verified}`；
>      - `verification_ref`：查證紀錄的參照；
>      - `trigger ∈ {weekend, official_holiday} | null`；
>      - `checked_bar_ref`：受檢 bar 的參照；
>      - `holiday_table = {version, coverage_start, coverage_end} | null`：`trigger = weekend` 時為 null；`trigger = official_holiday`，以及 `basis = verified` 時，記判定當下已接入的表（尚未接入時為 null）；
>      - `set_i_check = {runs: [{run_id, recorded_at}], final_after}`：判定當下 d 的 ok bars run 清單，以及 `final_after(TW, d)` 的值（ADR-0028 CS-17）。
>    - 判定時間就是事件的 `recorded_at`，不另設欄位。
>    - **寫入函式在同一個交易內驗證**，任一項不成立就拒絕寫入：
>      - `basis = direct` ⇒ `verification_ref` 為 null、`trigger` 非 null，而且重算後 d ∉ D-8.1 (i)。另外，`trigger` 要和 d 相符：`weekend` ⇒ d 是週六或週日，而且 `holiday_table` 為 null；`official_holiday` ⇒ d 在 `holiday_table` 的涵蓋範圍內，而且列為休市日。
>      - `basis = verified` ⇒ `verification_ref` 非 null，指向 `session_date = d`、結果是「來源沒有這一天」的查證紀錄，而且該列只有 X2 偵測的 (iii) 成立。所以 **`trigger` 必須為 null**：d 不是週末，也不是已接入表列的休市日。
>      - `set_i_check` 由寫入函式在重算 (i) 時自行填入，不接受呼叫端傳入（比照 D-2 第 3 點）。
>      - 重算經 `MarketPanelReader`（唯讀）讀市場 DB，在寫入交易持有期間執行。市場 DB 是另一個檔案，所以不構成跨檔原子性；之後 d 才進入 (i) 的情形，見第 12 項。
>    - 觀察日在查詢時排除這些日期。已寫入、日期是 d 的 `forecast_gaps` 等紀錄不刪不改，查詢時一併排除（回覆事先宣告 §9.3 第 18 點 (i) 的註記方式）。

**FL-19 (c) 擴充（不新增字母，仍是 (a)～(g)）**
> - (c)① 原本的直接確認格，另斷言 payload 七個欄位齊全，而且 `set_i_check` 等於重算的結果。
> - (c)② direct 拒絕寫入：寫入當下注入一筆定案後的 ok run，使 d ∈ D-8.1 (i)；或 `verification_ref` 非 null；或 `trigger` 為 null。三種情形各一個子例，都期望拒絕寫入、不寫事件、d 仍是觀察日。
> - (c)③ verified 拒絕寫入：`verification_ref` 為 null；或指向的查證紀錄結果不是「來源沒有這一天」；或 d 是週末（`trigger` 非 null）。三種情形都期望拒絕寫入。

**給 quant 的名稱對照：**
- `trigger`、`set_i_check` 與 v0.11（L1183、L1430）相同。
- 新定名的有 `verification_ref`、`checked_bar_ref`、`holiday_table`。v0.11 用的是描述性文字，不衝突，但建議引用這些名稱，讓 V-7 一致。
- v0.11 L1183 要補「`verified` 時 `trigger` 為 null」，並納入寫入驗證。

### N-1｜A-77 加第 12 項（D_v 前待決；收緊）

> 12. **X2 確認之後，d 才進入 (i)（D_v 前待決；風控 2026-10-17 N-1，比照第 9 項 F-8）**
>     - 情境：`x2_confirmed_non_session` 寫入之後（相關列可能已依第 8 項順延），同一個 d 才出現 `recorded_at ≥ final_after(TW, d)` 的 ok bars run。這時 d 會依第 3 項經 (i) 變回觀察日，和已寫入的事件及 `x2_shift_json` 矛盾。
>     - **偵測**：每日結算排程（事先宣告 §6.3「觸發」）用單一函式，對每一筆 `x2_confirmed_non_session` 檢查 d 是否已經 ∈ D-8.1 (i)。`basis = direct` 和 `verified` 都要檢查。
>     - 成立時：
>       - 記 WARNING；
>       - 寫入 `session_calendar_conflict`，`origin = post_x2_final_run`；
>       - payload 另帶 `x2_event_id`，以及新 run 的 `run_id`、`recorded_at`；
>       - `evidence` 取該 X2 事件的 `trigger`。`verified` 列的 `trigger` 是 null，這時 `evidence = independent_source_absent`；
>       - 同一個 (`session_date`, `origin`) 已有事件時，不重複寫入。
>     - **揭露**：併入第 5 項的 §4.2 單獨揭露（以不同的 `session_date` 計，並依 `origin` 分列）。
>     - **觀察日身分怎麼處理**：由 tech-architect 另案提案，標明方向，送風控審。核可之前不得自動調整任何已寫入的事件或 `x2_shift_json`。D_v 前必須核可。D_v 前沒有前瞻紀錄，所以不擋本批。
- 第 5 項 payload 的 `origin` 改為 `∈ {x2_check, candidate_t, post_x2_final_run}`；`evidence` 改為 `∈ {weekend, official_holiday, independent_source_absent}`，其中最後一個值只用於 `post_x2_final_run`。
- 待決事項 tech-architect 加：N-1 的處理提案。

### T-2｜A-63 第 11 點：擴充 slot（收緊）

> - `slot ∈ {record_list, record_list_header, plan_reason, outlook_block, sector_cell, sector_detail}`（風控第八批 T-2）。
>   - `record_list_header` 是紀錄清單的清單層級標頭；`outlook_block` 是大盤與個股的展望區塊；`sector_cell` 是族群列表的單元格；`sector_detail` 是族群詳細頁。
> - `display.py` 的 `GATE_SLOT_SCOPES` 是封閉登記：
>   - `record_list`、`record_list_header` → {market, sector, symbol}；
>   - `plan_reason` → {symbol}；
>   - `outlook_block` → {market, symbol}；
>   - `sector_cell`、`sector_detail` → {sector}。
>   - 要增列，須修訂本點並送風控。
> - 上述位置的 gate 片段 ID，只能由 `select_gate_fragments(scope_kind, slot, G_eff, e_changed_since)` 產生（route 列舉＋AST 測試，比照 FL-60 (d)）。
> - LM-12、LM-34、LM-73、LM-98 登記為 `covers = {forward_n_below_min}`，分別放在 `outlook_block`、`sector_cell`／`sector_detail`、`plan_reason`。
> - FL-52 加斷言（依第八批 LM-129 ②）：族群 `forward_n_below_min` 的原子片段在 `e_changed_since` 為真時選不到 LM-129。R-6 片段核可之前，這種情形 fail-closed。

### T-3｜A-63 加第 12 點；FL-52 (h)（收緊）

> 12. **claim 層與清單列同時呈現**（風控第八批 2.26.10 第 2 點）：
>     - (1) claim 層（`outlook_block`，或 `record_list_header`）在 `suspended_f3`／`withdrawn_f2` 而且 G_eff 非空時，同時呈現 LM-76（暫停）／LM-81（下架）與 LM-120，`covers` 聯集等於 G_eff。
>     - (2) LM-118、LM-119 的列，在 G_eff 非空時，後面一律接 LM-120〔超出字面：風控只要求「沒有 claim 層的頁面」才接；端點不收頁面參數，前端也不得另寫判定，所以改成一律附〕。
>     - (3) 族群 (c) 優先時，同頁 claim 層（`record_list_header`、`sector_cell`、`sector_detail`）在 `suspended_f3`／`withdrawn_f2` 時要有 LM-76／LM-81。
> - **FL-52 (h)**：對每個 scope × {`suspended_f3`, `withdrawn_f2`} × G_eff（∅／非空）逐格斷言 (1)～(3)，包括渲染出的片段數等於 \|G_eff\|。

### T-4｜A-65：結算日期的語意（不變，定義明確化）

> - `start_price_json`、`end_price_json` 都必須帶 `session_date`：實際取用的那個收盤的交易日。
> - `status = resolved` 的列，寫入時驗證兩件事，不成立就拒絕寫入：
>   - `settlement_date == end_price_json.session_date`，也就是觀察到的 T+h；X2 順延時就是順延後的 T+h；
>   - `start_price_json.session_date == forecast_record.data_as_of`。
> - LM-131 的 `{終點 MM/DD}` 綁定 `end_price_json.session_date`，起點 `{MM/DD}` 綁定 `start_price_json.session_date`。不得代入 `resolved_at` 或任何處理時間。
> - 作廢列的 `settlement_date` 維持 A-62 R2 的「判定作廢的日期」，LM-131 不用在作廢列。

### T-5｜答覆：結構上可能，R-5 不能免除；定義判定謂詞（掛 A-65，收緊）

- **路徑**：
  1. 大盤列在 `replay_review_pending` 期間，依 A-27 (b) 只遮蔽「尚未結算」的列，所以已結算的列會帶 PV-45 列出 LM-131。
  2. 結算當下，X3／X4 的查證結果若是「來源未接入」，依事先宣告 L1166 照原值計分。
  3. 之後，獨立來源接入時的 ③ 回查，或每日的 ② 重查確認收盤有誤，依 L1177 以 supersede 改記 `unresolvable_missing_data`（`index_bar_confirmed_erroneous`）。
  4. 結果：一筆已經列出結果的紀錄被作廢。
- 條文：
> - 「曾列出結算結果」的判定謂詞 `had_listed_result(forecast_id)` ＝ 更正鏈中，有一筆被 supersede 的 `status = resolved` 列。這是保守取法，不追蹤實際有沒有渲染過。
> - 謂詞為真、而且最新 outcome 是 `index_bar_confirmed_erroneous` 時，在 R-5 伴隨句核可之前 fail-closed，不顯示 label。
> - FL-52 的 `status_reason` 窮舉依這個謂詞分成兩條路徑。

## 三、suggested 採用表

| # | 採用 | 條文（定位） | 方向 |
|---|---|---|---|
| S″-1 | 採用 | A-75 RC′-5：「**(iv) 不成立時**」改為「**(i) 成立而且 (iv) 不成立時**」，其餘不動 | 不變（措辭精確化） |
| S″-2 | 採用 | FL-19 (e) 加 (e)③：候選 T 是週末，而且 T ∉ D-8.1 (i) → 記 `inputs_not_ready`，不寫 `session_calendar_conflict`，不退回前一個 session | 收緊（測試） |
| S″-3 | 採用 | A-57 (iv) G_eff 子點加：「`views` 對外回傳的 `display_state` 一律是調整後的值；任何回應 schema 都不得同時帶 snapshot 原始的 `display_state` 與調整後的值，snapshot 原值只留在資料表供稽核」。FL-54 (e) 加一格封閉 schema 斷言 | 收緊 |

**方向統計：維持 19／2／9／1／2。**
- RC″-1、RC″-2、RC″-3、T-2、T-3 掛 A-63／A-65（收緊）；
- A-62 的同步屬一致性，A-62 類別不變；
- T-1 掛 A-57（不變內容，類別不變）；
- T-4、T-5 掛 A-65；
- RC″-5、N-1、S″-1、S″-2 掛 A-77／A-75；
- RC″-4 掛 A-79（不變）；
- S″-3 掛 A-57。

## 四、需回送項

**給 coordinator 的機械核對調整：**
1. 核對第 1 點的 hunk 對照要加 T-1～T-5、S″-1～S″-3；核對第 14 點的掛載清單要加 A-62、A-75 與 D-3。
2. 核對第 10a 點第 3 子項：`stats_json.e_read_at` 和「不用 `computed_at`」都還在，但 `e_read_at` 的語意改成只做稽核。二選一句的關鍵字是「事件序號」。

**回送風控（超出字面，方向都是收緊或一致性）：**
3. RC″-1：同步 A-62 R2 第 1 點。
4. RC″-2：擇 (b)，保留 `e_read_at` 當稽核欄位，另加時鐘倒退格。
5. RC″-5：
   - 命名 `verification_ref`、`checked_bar_ref`、`holiday_table`；
   - `verified` 時 `trigger = null`（回覆 quant 的提問）；
   - `verified` 列也記 `holiday_table`；
   - 加驗證「`trigger` 和 d 相符」；
   - `set_i_check` 由寫入函式自行填入；
   - 註明市場 DB 與主 DB 不構成跨檔原子性。
6. N-1：
   - `origin = post_x2_final_run`；
   - 偵測涵蓋 `verified`，所以新增 `evidence = independent_source_absent`；
   - 不重複寫入；
   - 核可之前不得自動調整已寫入的紀錄。
7. T-3 (2)：LM-118／LM-119 的列一律附 LM-120，不依頁面判斷。
8. T-5：R-5 不能免除；保守的判定謂詞 `had_listed_result`。

**請風控另行注意：**
9. 第八批 LM-131 使用條件 ③「gated 時同區塊附 PV-45」要對齊 RC″-1，改成「G_eff 非空，不論 `display_state`」。
10. X2「結算後才確認」的 supersede（L1180）同樣會改動已經列出的結果，只是改成順延重算，不是作廢。這和 R-5 是同一類「翻案」，是否也需要伴隨句，請風控裁定。我沒有寫進條文。

**範圍：** 我沒有改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有跑程式、測試或 git。snapshot 計算的耗時是推論，沒有實測。這是唯讀的架構文件，Codex 不適用。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3雙撇與v0.11同批最後確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-新定位第八批字面逐字審-LM118至LM141-風控.md（第二節第 2、5 點；第四節 T-1～T-5；LM-129、LM-131、LM-141）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3雙撇併入RC與ADR-0028-A96A97修訂-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3prime補正-tech-architect.md（A-77 第 1～11 項、FL-19、S-4）
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md（A-62～A-65、FL-58、FL-59）
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（L242、L264、L275、L553-568、L768）
- /home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md（L267、L849）
- /home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md（L200）
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md（L1114、L1153-1183）

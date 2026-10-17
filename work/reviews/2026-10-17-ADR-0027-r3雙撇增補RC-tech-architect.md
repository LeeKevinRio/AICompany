# ADR-0027 r3″ 增補（RC″-1～RC″-5、N-1，tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 r3″ 增補（RC″）：tech-architect（唯讀）

## 一、結論

**風控要求的 RC″-1～RC″-5 和 N-1 都已寫成條文（第二節），三項 suggested 全部採用。tech-writer 可以一次套用 r3＋r3′＋r3″＋本增補。** 三版加本增補衝突時，以本增補為準，其次 r3″、r3′、r3。

- **條號與統計**：每一項都掛在既有條號下，沒有 A-87 以後的新條號。方向統計維持 19／2／9／1／2，沒有任何一條換類別。
- **RC″-2 我選 (b) 單調遞增序號，不選 (a) `BEGIN IMMEDIATE`。** 理由有四點：
  1. **(a) 照字面只約束 snapshot 這一側，漏洞還在。** store 時鐘是在 insert 時填入的（L242），時間戳在寫入者拿到鎖之前就可能算好了。順序可以是：寫入者先取 `recorded_at = t1`，然後等鎖；snapshot 拿到鎖，記下 `e_read_at = t2 > t1`，讀 E、commit；寫入者才拿到鎖、insert、commit。這時 `recorded_at < e_read_at`，snapshot 卻看不到這筆。要補上，就得另外規定兩個 process（L768）所有 E 變更事件和 supersede 結果的寫入者，都在拿到鎖之後才讀時鐘。這超出風控的字面。
  2. **(a) 依賴牆上時鐘單調。** 主機時鐘被 NTP 校正或手動往回調時，會出現漏判，而且漏判在不安全的方向。〔推論〕
  3. **(a) 要在持有寫入鎖時跑完整個 snapshot 計算，含 bootstrap。** 這段期間 API 的 on-demand 寫入只能靠 `busy_timeout` 等，等超過就會失敗，等於把計算時間和寫入可用性綁在一起。〔推論，計算耗時沒有實測〕
  4. **(b) 和現有設計相同。** ADR-0012 D-2 的 `run_id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`，規定單調、不重用；C-50 的 `run_id ≤ source_run_max`（ADR-0012 L849）就是同一個做法。ADR-0026 的 `event_id` 也一樣。SQLite 同一時間只有一個寫入交易，序號在寫入交易內配發，所以 read transaction 看不到的列，序號一定比它讀到的最大值大。這跟 journal 模式、時鐘都無關，也不必拉長鎖的持有時間。
  - **(b) 的代價**：D-3 要固定兩個主鍵型別；備份還原不得重編序號。預測帳還沒有實作（`app/forecast/` 不存在），所以沒有遷移成本。
- **超出風控字面的地方都是收緊或保持一致，沒有放寬。** 共 7 處，見第四節。其中 A-62 的同步和 RC″-5 跨 DB 的限制，建議 coordinator 判斷要不要隨這批知會風控。

## 二、增補條文

「＞」後面是給 tech-writer 的條文。被取代的 9ba01d6 原文一律逐字寫進修訂紀錄；r3／r3′／r3″ 的中間版文字沒有落過檔，不必進修訂紀錄。

### RC″-1｜A-63／A-65：A-27 (e) 不以 `display_state` 為條件

**(1) D-11.4 第 11 點 (e)：整條取代 9ba01d6 L563**
> - (e) **大盤或個股，而且 G_eff 非空，不論 `display_state`**：已結算紀錄若顯示 label，回應的 `disclosure_fragment_ids` 要含 PV-45 固定句，在同一區塊呈現（風控 2026-10-17 RC″-1）。
>   - G_eff 的定義見 A-57 (iv)；大盤與個股的 G_eff 就是判定 `display_state` 的同一列最新 daily snapshot 的 `gate`。
>   - (e) 不以 `display_state` 的任何值為條件，`suspended_f3`、`withdrawn_f2` 期間同樣適用。

**(2) A-65：r3′ S-4 那一句改為**
> (e) PV-45（大盤或個股，而且 G_eff 非空，不論 `display_state`）與 PA-4（依既有規則）照樣適用於已結算的排程列。

**(3) A-62 R2 第 1 點的連帶同步（超出字面，見第四節第 1 項）**：「大盤或個股在 `gated` 時照樣附 (e) PV-45」改為
> 大盤或個股依 (e)（G_eff 非空，不論 `display_state`）照樣附 PV-45。

**(4) FL-59 加四格**
> - （RC″-1）大盤 × {`suspended_f3`, `withdrawn_f2`}、個股 × {`suspended_f3`, `withdrawn_f2`}，共四格。每格 G_eff ＝ {`replay_review_pending`}、紀錄已結算 → 期望出現 label（放在 `settled_record`），而且 `disclosure_fragment_ids` 含 PV-45。

**(5) 修訂紀錄（逐字）**
> 9ba01d6 L563 原文：「(e) 大盤或個股在 `gated` 時，已結算紀錄若顯示 label，回應的 `disclosure_fragment_ids` 要含 PV-45 固定句，在同一區塊呈現；」，依風控 2026-10-17 RC″-1 取代（收緊）。

### RC″-2｜A-63（RC′-2）：比較基準改用單調遞增序號（採 (b)）

**(1) RC′-2 條文：r3″ 的第 1、2、3 子點和「`e_read_at`」子點整段取代；`E_NEUTRAL_EVENTS`、「寫入 snapshot 的當下」、「依據」三個子點照 r3″ 保留**
> - **快照落後時 fail-closed**（風控 2026-10-17 RC′-2；比較基準依 RC″-2 採 (b) 單調遞增序號）：簽章是 `pa9_holds(claim, snapshot, e_changed_since: bool)`。
>   - `e_changed_since` 只由 `views` 的單一函式 `e_changed_since(snapshot)` 判定。下列任一項成立就為真：
>     - 有 `kind ∈ E_CHANGING_EVENTS` 的 `forecast_ledger_events` 列，而且 `event_id > snapshot.stats_json.e_read_event_seq`；
>     - 有 `supersedes_id IS NOT NULL` 的 `forecast_outcome` 列，而且 `outcome_id > snapshot.stats_json.e_read_outcome_seq`；
>     - 該 snapshot 缺任一個序號欄位。
>   - 為真時，`pa9_holds` 一律為真，直到之後產出一筆讀取序號涵蓋該事件的 daily snapshot 為止。
>   - **事件封閉清單 `E_CHANGING_EVENTS`**：
>     - `forecast_ledger_events.kind ∈ {pit_violation_confirmed, x2_confirmed_non_session, db_restored}`，依 `event_id`；
>     - `forecast_outcome` 中 `supersedes_id IS NOT NULL` 的列，依 `outcome_id`；
>     - 不按 claim 篩選：任一筆成立，所有族群 claim 都適用。
>   - **讀取序號**（RC″-2 (b)）：snapshot 的計算在單一、明確開啟的 read transaction 內讀 E，並在同一個 transaction 內讀出兩個值，寫進 `stats_json`：
>     - `e_read_event_seq` ＝ 看得到的 `MAX(forecast_ledger_events.event_id)`，沒有列時為 0；
>     - `e_read_outcome_seq` ＝ 看得到的 `forecast_outcome` 列中，`supersedes_id IS NOT NULL` 那些列的 `MAX(outcome_id)`，沒有這種列時為 0。
>   - **序號的前提（規範性要求）**：`forecast_ledger_events.event_id` 與 `forecast_outcome.outcome_id` 都是 `INTEGER PRIMARY KEY AUTOINCREMENT`，單調遞增、永不重用；遷移與備份還原不得重編（比照 ADR-0012 D-2 的 `run_id`）。
>     - 理由：SQLite 同一時間只有一個寫入交易，序號在寫入交易內配發。所以 read transaction 看不到的列，不論當時還沒 commit 或之後才寫，序號一定大於它讀到的最大值。這和 journal 模式、store 時鐘都無關。
>   - 讀 E 和寫入 snapshot 可以是兩個交易：在兩者之間 commit 的事件，序號必然大於讀取序號，由 `e_changed_since` 捕捉。所以不需要把 snapshot 的計算放進寫入交易。
>   - `stats_json.e_read_at` 保留為稽核欄位（讀 E 那個 read transaction 的開始時刻），**不作為任何判定的比較基準**。比較一律用序號，不用 `e_read_at`，也不用 `computed_at`。
>   - 不選 (a)（`BEGIN IMMEDIATE` 內取得寫入鎖後才記 `e_read_at`）的理由：時間戳由 store 時鐘在 insert 時填入（D-2 第 3 點）。寫入者可能在取得鎖之前就算好時間戳，要所有寫入者都另外受約束才能關閉競態。(a) 也依賴牆上時鐘單調，而且要在持有寫入鎖時完成整個 snapshot 計算。

**(2) D-3：在下列兩處各加一個子點（只追加，不改原文）**
> - `forecast_outcome` 識別行之後：（r3″，RC″-2）`outcome_id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`（A-63 RC′-2 的序號前提）。
> - `forecast_ledger_events` 行之後：（r3″，RC″-2）`event_id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`（同上）。

**(3) D-11.4 第 2 點**：r3″ 加的 `stats_json.e_read_at` 之外，再加 `stats_json.e_read_event_seq` 和 `stats_json.e_read_outcome_seq`。`e_read_at` 標註「稽核用，不作比較基準」。

**(4) FL-58 (e6)：整格取代 r3″ 的版本**
> - (e6) 族群最新 snapshot 的 n＝150；snapshot 之後寫入一筆 `pit_violation_confirmed`。
>   - 下一筆 snapshot 之前：`pa9_holds` 為真、(c) 成立、已結算列不出現 label、片段的涵蓋範圍含 `forward_n_below_min`；
>   - 之後的 snapshot 依它自己的 n 判定。
>   - 另一格：事件在 snapshot 讀 E 之後、寫入 snapshot 之前 commit → 期望同樣 fail-closed。
>   - **另一格（RC″-2）**：事件交易早於 snapshot 開始（已取得 `recorded_at`，而且早於 `e_read_at`），但晚於 snapshot commit 才 insert 並 commit → 期望 fail-closed。也就是說，`recorded_at < e_read_at` 不影響判定。
>   - 另一格：注入 store 時鐘倒退，使事件的 `recorded_at` 早於 `e_read_at` → 判定結果和時鐘正常時逐位相同。
>   - 另一格：snapshot 缺 `e_read_event_seq` 或 `e_read_outcome_seq` → `e_changed_since` 為真。
>   - 再加一格：斷言 `forecast_ledger_events.kind` 列舉的每個值都已歸類。
>   - `sqlite_master` 斷言：`event_id`、`outcome_id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`。

### RC″-3｜A-63（RC′-3）：FL-52 窮舉範圍

**FL-52 窮舉擴充的第 1 子點整點取代；第 2、3 子點照 r3″ 保留，另加一個斷言**
> - 對每個 (scope_kind, slot)，取該 scope 可能出現的 `gate` 值：{`replay_review_pending`, `shadow_run_pending`, `settlement_smoke_pending`}，再依 scope 加 `forward_n_below_min`：**族群一律加入 `forward_n_below_min`；大盤與個股在 quant 有登記時才加入**。
>   - 族群一律加入的理由：只要 `pa9_holds` 為真，族群的 G_eff 就含 `forward_n_below_min`（A-57 (iv)；ADR-0025 PA-9），和 quant 有沒有登記無關。
> - 另加斷言：族群的窮舉值集合含 `forward_n_below_min`，不讀 quant 的登記；例如 {`forward_n_below_min`, `replay_review_pending`, `shadow_run_pending`} 恰好有一個項目。

### RC″-4｜A-79：CEO 說明第 8 點（逐字取代）

> 8. **待你決定（不急）**：第一版要不要讓個股或族群顯示方向。不決定的話，就維持不顯示；這在風險上是安全的。要開放，只有兩條路：做該範圍的回放，或修訂 ADR-0025 的閘門。做回放的話，要先修改事先宣告（目前規定個股與族群的回放只能當內部研究、不上畫面），回放結果有已知偏誤，要照實揭露。兩條路都要再送風控。

### RC″-5｜A-77 第 7 項：`x2_confirmed_non_session` 就是判定紀錄

**(1) A-77 第 7 項：整項取代 r3′ 的版本**
> 7. **X2 確認的登記**（風控 2026-10-17 RC″-5）：只增不改，寫入 `forecast_ledger_events.kind = x2_confirmed_non_session`。**這筆事件本身就是 X2 的判定紀錄**，對應事先宣告 §6.3 的判定紀錄與 R-C ④；`basis = direct` 沒有查證紀錄，所以以這筆事件為準。
>    - payload：
>      - `session_date`；
>      - `basis ∈ {direct, verified}`；
>      - `verification_ref`：查證紀錄的參照（`direct` 時為 null）；
>      - `trigger ∈ {weekend, official_holiday}`（`direct` 時必填；`verified` 時為 null，因為該列只有 (iii) 成立）；
>      - `checked_bar_ref`：受檢 bar 的參照；
>      - `holiday_table`：官方休市日表的版本與涵蓋範圍 `{version, coverage_start, coverage_end}`（`trigger = weekend` 時為 null）；
>      - `set_i_check`：判定當下 d 的 ok bars run 清單（每筆 `run_id`、`recorded_at`），以及 `final_after(TW, d)` 的值（ADR-0028 CS-17）。由寫入函式在重算時填入，不接受呼叫端傳入。
>    - 判定時間就是事件的 `recorded_at`，不另設欄位。
>    - **寫入函式在同一個交易內驗證，任一項不成立就拒絕寫入**：
>      - `basis = direct` ⇒ `verification_ref` 為 null、`trigger` 非 null，而且重算後 d ∉ (i)；
>      - `basis = verified` ⇒ `verification_ref` 非 null，指向結果是「來源沒有這一天」的查證紀錄，而且該列只有 (iii) 成立。
>      - (i) 的重算經唯讀的 `MarketPanelReader`，在預測帳寫入交易持有期間執行。市場 DB 是另一個檔案，所以這次讀取和寫入不是同一個原子交易；寫入之後 d 才進入 (i) 的情形依第 12 項處理。
>    - 觀察日在查詢時排除這些日期。已寫入、日期是 d 的 `forecast_gaps` 等紀錄不刪不改，查詢時一併排除（回覆事先宣告 §9.3 第 18 點 (i) 的註記方式）。

**(2) FL-19 (c)：拆成三格，不新增字母（FL-19 仍是 (a)～(g)）**
> - (c)① 原格：週末只有定案前 ok run、有大盤列 → X2 直接確認，d 不是觀察日，T+h 順延，`x2_shift_json` 齊全。另斷言 payload：`basis = direct`、`verification_ref = null`、`trigger = weekend`、`holiday_table = null`、`checked_bar_ref` 非 null、`set_i_check` 列出定案前的 run 和 `final_after(TW, d)`。
> - (c)② **direct 拒絕寫入**：寫入前注入一筆 d 的定案後 ok run，使重算後 d ∈ (i)；或 `trigger = null`；或 `verification_ref` 非 null。三種情形都期望拒絕寫入、沒有事件列、T+h 不順延。
> - (c)③ **verified 拒絕寫入**：`verification_ref` 為 null；或它指向結果是「查詢失敗」的查證紀錄；或 d 有正面休市證據（不只 (iii) 成立）。三種情形都期望拒絕寫入、沒有事件列。

**(3) 修訂紀錄**：本項取代的是 r3′ 的中間版，不必進修訂紀錄。

### N-1｜A-77 第 12 項：D_v 前待決（登記）

**(1) A-77 加第 12 項（比照第 9 項 F-8）**
> 12. **X2 確認之後 d 才進入 (i)（D_v 前待決；風控 2026-10-17 N-1）**
>    - 情境：d 已寫入 `x2_confirmed_non_session`，相關列也已依第 8 項順延；之後同一個 d 才出現 `recorded_at ≥ final_after(TW, d)` 的 ok bars run。依第 3 項，d 會經 (i) 變回觀察日，和已寫入的事件與 `x2_shift_json` 矛盾。
>    - **偵測**：`app/forecast/audit.py`（缺日稽核）每次執行時，對每個 X2 確認日 d 檢查 d ∈ (i)。成立時：
>      - 記 WARNING；
>      - 經 `store.py` 寫入 `forecast_ledger_events.kind = session_calendar_conflict`，`origin = x2_post_confirm`。payload 照第 5 項的欄位（`evidence` 取該 X2 事件的 `trigger`，受檢 bar 的參照取該事件的 `checked_bar_ref`），另帶 `x2_event_id`，以及使 d 進入 (i) 的 run（`run_id`、`recorded_at`）；
>      - 同一個 (`session_date`, `origin = x2_post_confirm`) 只寫一筆。
>      - `app/data/session_calendar.py` 只提供 (i) 的判定，不寫預測帳。
>    - **揭露**：在驗證報告 §4.2 單獨列出，以不同的 `session_date` 計，不得併入其他 `origin` 或其他異常待查證筆數。
>    - **觀察日身分怎麼處理**：由 tech-architect 另案提案、標明方向、送風控審，D_v 前要定案。提案核可之前，不得以程式自動解除這個矛盾，也不得改寫已寫入的事件或 `x2_shift_json`。
>    - 目前沒有前瞻資料，所以不擋本批 commit。

**(2) A-77 第 5 項的 payload 列舉同步**：`origin ∈ {x2_check, candidate_t}` 改為 `origin ∈ {x2_check, candidate_t, x2_post_confirm}`（`x2_post_confirm` 見第 12 項）。

**(3) 待決事項**
- tech-architect：加「A-77 第 12 項，觀察日身分的處理提案，送風控；D_v 前」。
- data-engineer：加「第 12 項的情境是否實際會發生（週末 session 的 run 怎麼產生），併入 F-8 查證」。

## 三、suggested 採用表

| # | 採用 | 條文（定位） | 掛在 | 方向 |
|---|---|---|---|---|
| S″-1 | 採用 | RC′-5 的 A-75 子點「**(iv) 不成立時**：候選 T 依 (i) 必定 ∈ D-8.1 (i)，所以這必然是…」改為：「**(i) 成立而且 (iv) 不成立時**：候選 T ∈ D-8.1 (i)，所以這是 A-77 第 5 項的同一種證據矛盾。」後面另加一句：「(i) 不成立時，不論 (iv)，記 `inputs_not_ready`，不寫 `session_calendar_conflict`。」 | A-75 | 文字更正＋收緊 |
| S″-2 | 採用 | FL-19 (e) 加 (e)③：「候選 T 是週末，而且 T ∉ (i)：期望 `inputs_not_ready`，不寫 `session_calendar_conflict`，不退回前一個 session。」 | A-75 | 收緊 |
| S″-3 | 採用 | A-57 (iv) G_eff 子點加一句：「`views` 對外回傳的 `display_state` 一律是調整後的值。任何回應 schema 都不得同時帶 snapshot 原始的 `display_state` 和調整後的值；原始值只留在 snapshot 列。」FL-54 (e) 加斷言：「回應 schema 列舉中，沒有任何 schema 同時含兩個 `display_state` 欄位。調整後是 `gated` 的族群列，回應裡找不到 `shown`（封閉 schema＋全文掃描）。」 | A-57 | 收緊 |

**方向統計（本增補之後）：19／2／9／1／2，不變**

| 項目 | 掛在 | 方向 | 類別是否變動 |
|---|---|---|---|
| RC″-1 | A-63／A-65（連帶 A-62） | 收緊 | 否（A-62 仍是「收緊＋有條件放寬」） |
| RC″-2 | A-63（含 D-3 的兩個子點） | 收緊 | 否 |
| RC″-3 | A-63 | 收緊 | 否 |
| RC″-4 | A-79 | 文字，不變 | 否 |
| RC″-5 | A-77 | 收緊（稽核性） | 否 |
| N-1 | A-77 | 登記待決，不變；第 5 項列舉擴充 | 否 |
| S″-1、S″-2 | A-75 | 收緊 | 否 |
| S″-3 | A-57 | 收緊 | 否 |

## 四、需回送或知會的項目

以下沒有任何一項是放寬。第 1、3 項建議 coordinator 隨這批知會風控；其他屬於我在風控寫法內的實作選擇，coordinator 若認為超出，就一併回送。

1. **A-62 R2 第 1 點同步（超出風控字面）。** 風控只點名 A-65。可是 A-62 R2 第 1 點也寫著「大盤或個股在 `gated` 時照樣附 (e) PV-45」，不改的話，會和新的 (e) 互相矛盾。我改成引用 (e) 的新條件，方向是收緊。這會使 hunk 也落在 A-62，機械核對第 14 點列的掛條範圍沒有 A-62。
2. **RC″-2 選 (b) 時的細節**（都在 (b) 的範圍內）：
   - D-3 把 `event_id`、`outcome_id` 固定為 `INTEGER PRIMARY KEY AUTOINCREMENT`，並規定不得重編；
   - `e_read_at` 保留為稽核欄位，不作比較基準。所以機械核對 10a 的「有 `stats_json.e_read_at`」「不用 `computed_at`」兩句在字面上都成立，但語意改成「只供稽核」；
   - FL-58 (e6) 多加「時鐘倒退」和「缺序號欄位」兩格。
3. **RC″-5「同一交易內重算 d ∉ (i)」有物理上的限制。** (i) 讀的是市場 DB，它和主 DB 是不同檔案（ADR-0012 v3；ADR-0027 D-2 第 1 點），所以重算和預測帳寫入不可能是同一個原子交易。我把它寫成「在寫入交易持有期間經 `MarketPanelReader` 重算」，剩下的競態明確歸給 N-1（A-77 第 12 項）。另外兩處推得的規則，請風控知悉：
   - `set_i_check` 由寫入函式填入，不接受呼叫端傳入；
   - `verified` 時 `trigger` 為 null，這是從「只有 (iii) 成立」推出來的。
4. **N-1 的實作選擇**（風控交 TA 定的範圍）：
   - `origin = x2_post_confirm`；
   - payload 另帶 `x2_event_id`，以及使 d 進入 (i) 的 run；
   - 偵測放在 `audit.py`，寫入經 `store.py`，data 模組不寫預測帳；
   - 同一個 (session_date, origin) 只寫一筆。
5. **S″-1、S″-2 掛在 A-75，S″-3 掛在 A-57。** 機械核對第 14 點的掛條清單（A-63／A-65／A-57／A-77／A-79）要加上 A-75（suggested）和 A-62（第 1 項）。
6. **FL-19 (c) 拆成 ①②③。** 拒絕寫入的兩格放在 (c) 底下，不新增字母，所以機械核對第 11 點的「(a)～(g)」仍然成立。
7. **要交給 quant 在 v0.11 同步的事**：
   - §4.2 的 `session_calendar_conflict` 依 `origin` 分列，要加 `x2_post_confirm` 一列；
   - L1178 和 §9.3 第 18 點 (i) 引用 RC″-5 的欄位名稱：`verification_ref`、`trigger`、`checked_bar_ref`、`holiday_table`、`set_i_check`；
   - 機械核對 V-7、V-11 會比對這些名稱的拼寫。

**查證範圍**
- 讀過：
  - 風控最後確認全文；
  - 我的 r3″ 全文、r3′ 補正全文；
  - r3 提案 L120-209；
  - ADR-0027 L200-299、L540-579、L755-784，並 grep FL-19／52／54／58／59、`outcome_id`／`event_id`、`stats_json`；
  - grep `docs/adr/` 和 `apps/stock-desk/backend/` 內 `BEGIN IMMEDIATE`／`AUTOINCREMENT`／`busy_timeout` 的既有用法。
- 沒有讀事先宣告本文。
- 〔推論〕兩點：(a) 的時鐘競態，是依 D-2 第 3 點「store 時鐘填入」推得的；snapshot 計算的耗時沒有實測。
- 沒有修改任何檔案，沒有跑 git、程式或測試，沒有讀 `.env` 或 `*.db`。這是唯讀的架構文件，Codex 不適用。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3雙撇與v0.11同批最後確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3雙撇併入RC與ADR-0028-A96A97修訂-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3prime補正-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（L242、L264、L275、L467、L553-568、L768、FL-19 L808、FL-52 L876、FL-54 L912）
- /home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md（D-2 `run_id` L267、C-50 L849）
- /home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md（`event_id` AUTOINCREMENT L200）

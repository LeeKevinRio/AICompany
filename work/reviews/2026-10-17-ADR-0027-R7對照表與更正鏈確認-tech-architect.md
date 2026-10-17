# R-7 更正原因對照表與更正鏈三項確認（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# R-7 對照表與更正鏈三項確認（tech-architect，唯讀）

## 一、本次結論

基準是已套用的 ADR-0027 本文，tech-writer 已把 r3 到 RC‴ 都寫進去：A-65 在 D-11.4 第 11 點 (h)，L850-869；A-77 第 12 項在 L483-495。條文都掛在既有 A 號下。上一份提案 1～5 這次不重複。

**先說查證結果：`correction_reason` 目前沒有任何列舉值，而且它不在結算端。**
- `correction_reason` 只出現在 `forecast_record`，也就是預測端的更正欄位（ADR D-3 L270；事先宣告 §6.1 L1093、§6.4 L1214）。
- `forecast_outcome` 只有 `supersedes_id`、`correction_job_id`（L281），沒有原因欄位。
- ADR 和事先宣告都沒有定義 `correction_job` 的表。可是事先宣告 L1219 要求更正作業記下重查範圍、重查筆數、改變筆數，這些現在沒有地方存。

所以風控要的「`correction_reason` → RR」對照表，現在沒有可以對照的來源。我的提案是：
- 在結算端新增封閉列舉欄位 `forecast_outcome.correction_causes`；
- 新增 `forecast_correction_job` 表；
- 再出 `CORRECTION_REASON_FRAGMENTS` 對照表。

不沿用 `correction_reason` 這個名字，是因為它和預測端的同名欄位語意不同，共用名字容易 join 錯。

**三件事的答案**
- **(a) 會。** 只更正非收盤的診斷欄位時，也會新增 supersede 列。依據有三：outcome 表完全只增不改（D-2 第 2 點有 UPDATE trigger）；事先宣告 L1174、L1185 都寫「依 §6.4 更正」；§6.4 第 3 點規定「有變的筆新增一列」。新增一列之後 `had_listed_result` 為真、最新 outcome 是 `resolved`，又沒有對應的原因片段，所以目前會 fail-closed、遮掉 label。
- **(b) 結構上可能。** 例如同一晚同時有 X2 確認和收盤更正，兩者都和同一筆的結算窗有交集，一次重算就同時反映兩個原因。所以 `correction_causes` 要存成集合，有兩個以上的原因就 fail-closed。並列規則等之後另送。
- **(c)** 重算列照樣受 T-4 的寫入驗證約束。各原因下 `end_price_json.session_date` 的取值見提案 2；`x2_shift_json` 一律記累計值，這點要 quant 確認。

**診斷欄位例外（方向：放寬）**：只有一種情形可以不帶伴隨句，就是更正鏈每一列都是 `resolved`、而且畫面相關欄位逐位相同。預設維持 fail-closed，這項不擋 D_v。

**主統計**：事先宣告 L1220 的「最新的那一筆」就是 ADR D-11.1 的「更正鏈的最後一筆」。兩邊沒有實質差異，我補了對齊條文。但另外發現一個相關的不一致：事先宣告 L706、LG-20 和 ADR L577 都允許 snapshot 被 supersede，ADR 的 snapshot 表卻沒有對應欄位，而且有 UNIQUE。要 quant 和風控裁定。

## 二、逐項提案

### 提案 1｜結算端更正原因與 `CORRECTION_REASON_FRAGMENTS`｜掛 A-65（D-11.4 第 11 點 (h)「翻案伴隨句」之後）＋A-77 第 8 項（D-3 欄位）｜方向：收緊（補定義）

**原因要記在哪裡：比較三個方案**
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A（採用）：每列記原因集合 `correction_causes`，另有作業表 | 逐列可查；能如實表示 (b) 的多原因 | 多一個欄位、一張表 | 低 |
| B：只記在作業層，一個作業一個原因 | 結構簡單 | 重算是依當下的來源資料，作業啟動時其他還沒處理的更正也會被算進去，原因會少記 | 中：可能標錯原因 |
| C：沿用 `forecast_record.correction_reason` | 不加欄位 | 那是預測端欄位；結算端更正不會寫 `forecast_record` | 高：語意錯置 |

**條文**
> - **D-3 `forecast_outcome` 的「更正」子項加**：`correction_causes`，JSON 陣列，封閉列舉、排序固定、不重複。
>   - `supersedes_id IS NULL` 的列必須為 null；`supersedes_id IS NOT NULL` 的列必須非空。由寫入函式驗證；列舉外的值、空陣列、或與 `supersedes_id` 不一致，都拒絕寫入。
>   - 這個欄位和 `forecast_record.correction_reason` 無關，兩者不得互相引用或 join。
> - **D-3 新增 `forecast_correction_job`**：欄位為 `correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT`、`triggers_json`、`recheck_range_json`、`rechecked_count`、`changed_count`、`started_at`、`ended_at`，只增不改。
>   - 這張表落實事先宣告 §6.4 第 2 點「作業要記錄重查範圍、重查筆數、改變筆數」。
>   - `forecast_outcome.correction_job_id` 必須指向這張表。
> - **更正原因的列舉 `OUTCOME_CORRECTION_CAUSES`**，依「被更正的是哪一類資料」分類：
>   1. `x2_session_removed`：X2 結算後才確認，T+h 順延重算（事先宣告 L1180；A-77）。大盤與個股共用觀察日，兩者都適用。
>   2. `settlement_close_corrected`：P(T) 或 P(T+h) 的收盤經更正後重算。大盤指數的依據是 L1175-1177 的獨立來源；個股是收盤本身的來源更正。
>   3. `window_bar_corrected`：結算窗內 T+1～T+h−1 的 bar，或任一 bar 的非收盤欄位經確認有誤（L1174、L1185）。這類更正動到的是 `diag_*`、`mae`、`mfe`、`invalidation_*`；個股與族群另外可能因 `split_or_reduction_suspected`、覆蓋率等規則改變 `status`。
>   4. `dividend_factor_corrected`：除權息因子更正，包括個股與族群成員（§6.4 第 1 點「來源資料」）。
>   - 要增列，須修訂本點並送風控。不屬於上述任何一類的 supersede 不得寫入：寫入函式拒絕，fail-closed。例如作廢之後才補到 bar、改回結算，這條路徑現行條文沒有定義，所以結構上不會發生。
> - **原因怎麼歸屬（確定性規則）**：
>   - 更正作業把啟動當下所有還沒處理的觸發一次讀入，寫進 `triggers_json`。觸發包括 `x2_confirmed_non_session` 事件、收盤更正的查證紀錄、來源修訂、因子修訂。
>   - 對每一筆重查的 outcome，`correction_causes` ＝ 受影響日期和該筆結算窗 [T, T+h] 有交集的所有觸發，所屬類別的集合。
>   - 重算後沒有任何欄位改變的筆不寫入（§6.4 第 3 點）。
>   - 這個歸屬只會多記、不會少記，多記的結果是 fail-closed。
> - **寫入時的一致性驗證**（不成立就拒絕）：
>   - 含 `x2_session_removed` ⇒ `x2_shift_json` 非 null，而且 `x2_event_ids` 包含 `triggers_json` 中與本筆有交集的 X2 事件。
>   - `correction_causes ＝ [window_bar_corrected]`、而且 `status = resolved` ⇒ 新列的 D 欄位和前一列逐位相同（D 欄位的定義見提案 3）。理由：已實現的報酬與標籤只取決於 P(T)、P(T+h) 和因子，這類更正動不到它們，所以不同就表示歸類錯了。
> - **`CORRECTION_REASON_FRAGMENTS`**：封閉對照表，放在 `display.py`，鍵恰好是 `OUTCOME_CORRECTION_CAUSES` 的全部值。
>
> | `correction_causes` | LM-150 的 `{更正原因}` |
> |---|---|
> | `[x2_session_removed]` | LM-151 |
> | `[settlement_close_corrected]` | LM-152 |
> | `[window_bar_corrected]` | FAIL_CLOSED（若風控核可提案 3 的例外，依該條處理） |
> | `[dividend_factor_corrected]` | FAIL_CLOSED（RR-3 核可前） |
> | 兩個以上的值 | FAIL_CLOSED（並列規則核可前） |
>
> - **選用規則**：只在 `had_listed_result` 為真、而且最新 outcome 是 `resolved` 時查表，用最新 outcome 的 `correction_causes`（LM-150 ⑦）。最新 outcome 不是 `resolved` 時走 LM-143，不查表。
> - **FAIL_CLOSED 的列**：用 `MaskedRecordView`（A-64），不出現 label，不渲染 LM-131、LM-146、LM-92。
>
> - **FL 斷言**（FL-22 擴充，加上 FL-52 謂詞路徑表）：
>   - (a) 對照表的鍵集合 ＝ 列舉；每個值恰好對應 LM-151、LM-152、FAIL_CLOSED 三者之一；
>   - (b) 寫入函式拒絕列舉外的值、空陣列，以及與 `supersedes_id` 不一致的組合；
>   - (c) 「謂詞為真 × 最新 outcome 為 `resolved`」路徑中，`correction_causes` 的每一種情形（四個單值、一組雙值）各一格，逐格斷言全文：
>     - LM-151、LM-152 兩格要等於 LM-150 代入後的全文，而且不含「沒有實際結果」、不含日期數字；
>     - FAIL_CLOSED 的格子 schema 中沒有 label、LM-131 的 ID 與 `realized_*`；
>   - (d) 同一晚注入 X2 確認與收盤更正、兩者和同一筆有交集 → 該筆的 `correction_causes` 有兩個值，結果 fail-closed；
>   - (e) 原因為 `window_bar_corrected` 但 D 欄位改變 → 拒絕寫入。

**遮蔽範圍（風控要求「要知道會遮掉多少」）〔推論，沒有實測頻率〕**
- `window_bar_corrected`：主要是大盤。每一個受影響的日期，會影響所有結算窗和它有交集的紀錄，最多約 3＋5＝8 列（兩個 horizon）。個股也可能有。
- `dividend_factor_corrected`：只影響個股與族群。族群在 v1 本來就不顯示已結算的 label；個股的已結算列會被遮掉。

**要風控裁定**：fail-closed 的列目前沒有任何核可的狀態片段，會留白。A-63 的「不得留白」只規範 A-27 (a)～(c)，不涵蓋這條路徑。要接受留白，還是另起一句中性片段？

### 提案 2｜(c) 重算 outcome 的 `end_price_json.session_date`，以及 `x2_shift_json` 的語意｜掛 A-65（T-4 子項）＋A-77 第 8 項｜方向：不變（明確化）

> - **T-4 的寫入驗證適用於更正鏈上的每一筆 `resolved` 列，包括 supersede 列**：
>   - `settlement_date == end_price_json.session_date` ＝ 重算當下的觀察日集合中，T 之後第 h 個觀察日；
>   - `start_price_json.session_date == forecast_record.data_as_of`。
> - **依原因分的取值**：
>   - `x2_session_removed`：`end_price_json.session_date` ＝ `x2_shift_json.shifted_t_plus_h`。必須晚於前一列的 `end_price_json.session_date`，因為移除觀察日只會讓 T+h 往後移。
>   - `settlement_close_corrected`：兩個 `session_date` 都和前一列相同，只有收盤值不同。P(T) 更正時，`start_price_json` 的值取更正後的收盤；`forecast_record.base_close` 不動（預測端一律用原始列，LG-3）。
>   - `window_bar_corrected`、`dividend_factor_corrected`：兩個 `session_date` 都和前一列相同。
> - **`x2_shift_json` 一律記累計值**：
>   - `original_t_plus_h` ＝ 不扣除任何 X2 確認日時的 T+h；
>   - `removed_dates`、`x2_event_ids` ＝ 窗內所有已確認的移除日及其事件；
>   - `shifted_t_plus_h` ＝ 本列的 `end_price_json.session_date`。
>   - 先順延、後來又因其他原因 supersede 的列，同樣帶累計值，不得改成 null。這樣 §4.2 的順延筆數只要讀更正鏈的最後一筆，就能逐列數出（R-C）。
> - LM-131 的日期綁定照 T-4，不變。
> - **FL-59 加三格**：X2 重算、收盤重算、連續兩次 X2 重算（驗證累計語意）。

- 累計語意是我對 A-77 第 8 項的讀法，原文沒有區分「本次移除」和「累計移除」。**要 quant 確認和 R-C ①～④ 一致。**

### 提案 3｜只更正診斷欄位時不帶伴隨句的例外｜掛 A-65（「翻案伴隨句」子項）｜**方向：放寬**，送風控審，可選、不擋 D_v

**比較的方案**
| 方案 | 優點 | 缺點 |
|---|---|---|
| A：不設例外（目前預設） | 最保守 | 結果沒有改變的列也被遮掉，資訊流失 |
| B（建議送審）：只有在更正鏈每一列的畫面相關欄位都逐位相同時才豁免 | 結果沒變的列照常顯示；判定純粹是資料比對 | 使用者看不到「曾有診斷欄位更正」，這是放寬的一面 |
| C：診斷更正改存另一張表，不 supersede outcome | 結構上就不會觸發謂詞 | 要修訂事先宣告 L1174、L1185 與 §6.4，改動大 |

**條文（B）**
> - **D 欄位** ＝ {`status`, `status_reason`, `realized_label`, `hit`, `realized_return`, `realized_log_return`, `realized_z`, `settlement_date`, `start_price_json`, `end_price_json`, `baseline_hits_json`}。比較方式是正規化 JSON 的位元組逐位相同。
> - **例外**：`had_listed_result` 為真時，若同時符合以下兩項，這筆紀錄不帶 LM-150，照一般已結算列呈現（LM-131 → LM-22／LM-132 → LM-146 → LM-92）：
>   - 更正鏈的每一列都是 `status = resolved`，而且 D 欄位都逐位相同；
>   - 每一個 supersede 列的 `correction_causes` 都是 `[window_bar_corrected]`。
> - 任一項不成立，就依提案 1 的對照表處理。更正鏈只要曾經作廢、或曾經有任何其他原因，都不適用例外。
> - 判定只由後端的單一函式 `correction_is_display_neutral(chain)` 產生，前端不得自行判斷。
> - **FL-52 加三格**：
>   - 全鏈中性 → 不出現 LM-150、LM-143，LM-131 照常；
>   - 鏈中有一列 D 欄位不同 → 依對照表；
>   - resolved → 作廢 → resolved 的鏈，即使數值相同也不適用例外。
> - 被豁免的筆數照實揭露在 §4.2（「診斷欄位更正筆數」），由 quant 登記。

- 放寬的一面：使用者不知道診斷欄位曾經更正過。
- 為什麼仍屬實：LM-131、LM-146 顯示的每個數字，都和最初結算時逐位相同。

### 提案 4｜主統計採用更正鏈上哪一筆 outcome｜掛 A-59（D-11.1 用詞定義）｜方向：不變（對齊）

> - 事先宣告 §6.4 L1220「統計改用最新的那一筆」的「最新」，就是 D-11.1 的**更正鏈最後一筆**：`NOT EXISTS (SELECT 1 FROM forecast_outcome o2 WHERE o2.supersedes_id = o.outcome_id)`。
>   - 不是 `resolved_at` 最大的一筆，不是 `settlement_date` 最大的一筆，也不是 `forecast_outcome.supersedes_id IS NULL`。
>   - **不變式**：更正鏈是線性的（`UNIQUE(supersedes_id)`），最後一筆的 `outcome_id` 等於鏈內最大值。只作斷言，不作為取列條件。
> - 每一筆 snapshot 取的是「它讀 E 的那次 read transaction 內看得到的」鏈尾（RC‴-1：先讀序號、再讀 E）。
> - n、命中、基準命中、作廢率與 W，都依鏈尾的 `status`、`realized_label`、`hit`、`baseline_hits_json` 計算。
> - 預測端的 label、`band_def`、`baseline_predictions_json` 一律取原始的 `forecast_record`（LG-3；我前一份提案 4）。
> - 列表上的紀錄（A-61「最新 outcome」）與 LM-131 也用同一個鏈尾，兩者由同一個函式產生（FL-49）。
> - 「更正後命中翻轉」（事先宣告 L687、L1221）比較的是：更正鏈中第一筆 `resolved` 列，對上鏈尾。鏈尾不是 `resolved` 時，另外歸入「改為作廢」。由 quant 確認後登記。
> - **FL-49 加三格**：鏈長 3 時取第三筆；`resolved_at` 被注入成倒序時，結果不變；snapshot 讀序號之後才 commit 的 supersede，這次 snapshot 不採用。

**相關發現（要 quant 與風控裁定，我沒有自行改）**
- 事先宣告 L706 寫「唯一例外是 R-8 的來源資料更正作業：以新增列 supersede」，LG-20 也預設 snapshot 可以有 supersede 列；ADR L577 有「來源資料更正後 supersede 的列，沿用原 seed」。
- 可是 ADR 的 snapshot 表沒有 `supersedes_id`／`correction_job_id`，又有 `UNIQUE(claim_id, computed_for_session, eval_kind)`，A-77 第 11 項還寫「已寫入的 snapshot 不改」。三處互相矛盾。
- **選項 (a)（建議）只往前生效**：
  - 更正只影響之後的 snapshot，已寫入的 snapshot 不 supersede；daily snapshot 只能維持或降級（D-11.3），正面判定要等下一個檢查點。
  - ADR L577 改為「snapshot 不 supersede；來源資料更正只影響之後的 snapshot（A-77 第 11 項）」；事先宣告 L706、LG-20 由 quant 同步。
  - 方向：收緊。不能回頭改寫過去的判定，但過時的正面狀態最多延續到下一筆 daily snapshot。
- **選項 (b) 實作 snapshot supersede**：
  - 要在表上加欄位、把 UNIQUE 改成部分索引、定義 views 讀哪一筆，還要處理和 F-2 期限、檢查點只算一次之間的交互作用。
  - 這會讓過去的下架或升級判定可以被回溯改寫，牽動面大。

## 三、驗證

**讀過的檔案與行號**
- 風控第十批報告：全文。
- ADR-0027 已套用本文：
  - L262-286（D-3，`correction_reason` 在 L270，outcome 的更正欄位在 L281，ledger events 在 L286）；
  - L460-499（A-77 第 6～12 項）；
  - L512-583（D-9、D-11.1、D-11.2，含 L561 鏈尾、L577 snapshot supersede）；
  - L745-869（A-27、A-62～A-65，含 T-4 在 L854-860、RC‴-4 在 L861-868）。
  - 另 grep 了 `correction_job`、`status_reason`、FL-22、FL-49、`had_listed_result`。
- 事先宣告：L1150-1229（含 L1174、L1175-1177、L1180、L1183、L1185-1186、§6.4 L1211-1221）；grep 了 `correction_reason`、`correction_job`、L687、L706、L1093、L1130、L1215、L1718、L1729。

**事實與推論**
- 事實：`correction_reason` 沒有列舉值；`correction_job` 沒有表；outcome 表只增不改（D-2 第 2 點）；snapshot 表沒有 supersede 欄位、有 UNIQUE。
- 推論：(b) 可能發生，是依「作業依當下的來源資料重算」推出來的；遮蔽範圍的估計沒有實測。
- 範圍：沒有修改任何檔案，沒有跑程式、測試或 git，沒有讀 `.env` 或 `*.db`。唯讀架構文件，Codex 不適用。

## 四、下一步

**回送風控**
1. 提案 1：結算端新增 `correction_causes`（名稱不沿用 `correction_reason`）與 `forecast_correction_job`；四值列舉與對照表；「不屬列舉的 supersede 拒絕寫入」；fail-closed 列留白的處理方式。
2. 提案 2：重算列的日期取值；`x2_shift_json` 累計語意。只是明確化，也請 quant 確認。
3. 提案 3：診斷欄位例外，**方向是放寬**，可選、不擋 D_v。
4. 提案 4：主統計就是鏈尾，屬對齊；snapshot supersede 的不一致，選 (a) 或 (b)。

**其他人**
- **quant**：
  - 確認累計語意；
  - 定「更正翻轉數」的比較基準；
  - 若採 (a)，同步修改 L706、LG-20；
  - 若採提案 3，登記「診斷欄位更正筆數」的揭露。
- **creative-lead**（suggested）：
  - RR-3（除權息因子）；
  - 多原因並列的規則；
  - fail-closed 列的中性狀態句（如果風控要求不得留白）。
- **tech-writer**：風控核可後，套進 A-65、A-77 第 8 項、A-59，以及 D-3 的兩處新增。
- **coordinator 核對清單**：加 FL-22 (a)～(e)、FL-52 謂詞路徑的新格、FL-59 三格、FL-49 三格；grep 確認結算端沒有任何地方引用 `correction_reason`。
- **仍待風控審的前一份**：提案 1～5，包括 N-1 甲案。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-新定位第十批字面逐字審-R7-LM150至LM152-風控.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（L270、L274-286、L483-495、L536-561、L577、L850-869）
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md（L687、L706、L1093、L1174-1186、L1211-1221、L1718、L1729）
- /home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md（8.12）

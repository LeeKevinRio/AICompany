# N-27、gap_judged_through 存放處、風控 suggested 兩項與 N21-2 位置（tech-architect）

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-27、`gap_judged_through` 存放處、風控 suggested 兩項，以及 N21-2 位置確認

## 一、本次結論

**N-27 有缺口，兩項都要補，送風控。**

1. **R10-2 會擋。** 「收盤確認有誤、取不到正確值，改記作廢」的 supersede，依 N21-5 會歸類為 `[settlement_close_corrected]`。R10-2 要求「兩個 `session_date` 相同、收盤值至少一個不同」。ADR 沒有定義作廢列的 `start_price_json`／`end_price_json`，所以：
   - 作廢列不帶價格時，`session_date` 比對不成立；
   - 作廢列帶原值時，收盤值相同。
   - 兩種讀法都會拒絕寫入。結果是畫面一直以原值呈現一個收盤已確認有誤的結果，不帶 LM-143。
   - 這也和 ADR 自己的 FL-22 那一格「market 結算後確認 → supersede 列為此值」直接矛盾。
2. **等待：依事先宣告字面，不必等 5 個觀察日。** §6.3「結算後才確認」只寫「取得正確值就重算；取不到就改記」。但 D-9.3 的「等待期間……，或之後的更正作業」有歧義，要明寫「不另等待」。
3. 字面見第二節 A：N27-1～N27-4。

**`gap_judged_through` 的存放處：新增一張只增不改的表 `forecast_gap_audit`。** 每次成功的缺日稽核一列，和同次的 `forecast_gaps` 同一個交易。
- 表數 18→19，M-11 13→14。屬 CEO 知悉，比照待決事項 CEO 段第 12、13 點。
- 順帶補上：`last_gap_audit_at` 現在沒有定義取值來源。

**風控 suggested 兩項：**
- (a) **採納。** 查證列和由它導出的 X2 確認同一個交易；X2 被寫入驗證拒絕時，查證列照寫。
- (b) **這是我上一輪的字面錯誤。** 我把 X2 確認的必要條件「d ∉ (i)」誤抄成 `no_error` 的條件。改為不讀 (i)。

**要改到風控核可字句的地方（字句本身都不改，只加適用範圍或讀法）：**
- N27-1：在風控 R10-2 三項之後，加「只適用於 `status = resolved`」的適用範圍子點。
- N27-2：對風控 Q-1 的 D-9.3 句子，加讀法子點。

這兩項都要送風控。風控 F 段的逐字字句一字未動。

**coordinator 追問 N21-2：** 我的本意是「並列」，也就是 `forecast_correction_job` 的直接子點。移動定位見第二節 D。

## 二、各部門回報（tech-architect）

> 定位字串都是對**目前工作樹**（tech-writer 本批已套用的狀態）用 Grep 確認唯一。

### A. N-27 查證與字面

**查證（事實）：**
- R10-2 的字面是：「`[settlement_close_corrected]` ⇒ 兩個 `session_date` 都和前一列相同；`start_price_json`、`end_price_json` 的收盤值至少有一個不同；`window_factors_json` 和前一列相同」。這條沒有限定 `status`。
- T-4 的兩項寫入驗證只限 `status = resolved`。作廢列只定義了 `settlement_date`（「判定作廢的日期」）。Grep 找不到作廢列價格欄位的定義。
- R10-2 的理由是「LM-151、LM-152 的陳述必須和差異相符」。但最新 outcome 不是 `resolved` 時，依「選用規則」走 LM-143，不查 `CORRECTION_REASON_FRAGMENTS`。所以這個理由對作廢列不適用。
- 同樣的問題也出在 `[x2_session_removed]`：順延後的新 T+h 收盤確認有誤時，也會改記作廢。

**可達路徑：**
- **現行暫定讀法下可達（我稱為「路徑一」）。** 情形是：
  - 結算時用的擷取 B1 正常；
  - 結算後，另一次擷取 B2 觸發 X1「收盤本身不可用」，寫入 `close_erroneous`（`direct`）；
  - B1、B2 構成的 X3 留在待查證集合（獨立來源未接入）；
  - N21-3 規定重算時取 B1。但 C22-1 第 4 處的暫定讀法以交易日為單位：「同日已有 `close_erroneous`、沒有 `correct_close_obtained`」，而 B1 屬於待查證集合，所以 B1 不算取得正確值 → 改記 `index_bar_confirmed_erroneous`。
- **改成「以 bar 為單位」的讀法時，似乎不可達【推論】。** 理由：結算所用的 bar 在結算前的 ③ 已經做過 X1；而經查證寫入的 `close_erroneous` 必定在同一個交易內另寫 `correct_close_obtained`。
- 不論哪一種讀法都必須修，因為事先宣告 §6.3 與 FL-22 都要求這條路徑寫得進去。

**等待：方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **甲（建議）：不另等待，以該次更正作業的判定視圖決定** | 照事先宣告字面；確定性；當晚就改呈現 LM-143 | 作廢依 R10-3 是終局的；之後才取得的正確值只進 `forecast_void_late_diag` | 和「結算前確認」的路徑不對稱，但差別只在一種情形：獨立來源已接入、① 查詢失敗、D_5 之前某次 ② 取得數值【推論】 |
| 乙：等到 D_5 才判 | 和結算前確認的路徑對稱 | 要有依時間經過的啟動條件，違反風控 N21-4「啟動與否只依三類觸發」；要改事先宣告字面；等待期間照原值呈現已確認有誤的結果 | 正是風控 B-1 指出的後果 |
| 丙：先作廢，之後取得正確值再 supersede | 不對稱最小 | 違反 R10-3、V12-20 | **否決** |

**N27-1（R10-2 適用範圍）**
- 定位（唯一）：`` - `[dividend_factor_corrected]` ⇒ 兩個 `session_date` 都和前一列相同，`window_factors_json` 和前一列不同。 ``
- 動作：在這一行之後、「理由：LM-151、LM-152 陳述……」之前，同一層插入。
- 被取代原文：無。
- 字面：
> - （N-27；tech-architect 2026-10-18）**適用範圍**：上三項只適用於新列 `status = resolved`。新列 `status ≠ resolved`（已結算列經更正後改記作廢）時，上三項不適用，改以下列各項驗證，任一項不成立就拒絕寫入：
>   - 前一列 `status = resolved`（作廢列不得被 supersede，R10-3 不變）；
>   - `scope_kind = market`，`status_reason = index_bar_confirmed_erroneous`；
>   - 以本作業的判定視圖（D-9 第 5 點 ④）、經 `scoring.py` 的同一個函式重算，P(T) 或 P(T+h) 至少一根的收盤是 D-3 `forecast_index_check`「判定時怎麼讀」所說的「確認有誤、尚未取得正確值」；
>   - `correction_causes` 不含 `x2_session_removed` 時：`x2_shift_json` 與前一列相同，而且以本作業觀察日導出的 T+h 等於前一列的 `end_price_json.session_date`。含 `x2_session_removed` 時：依上方「寫入時的一致性驗證」第一子點，而且 `x2_shift_json.shifted_t_plus_h` 等於以本作業觀察日導出的 T+h，並晚於前一列的 `end_price_json.session_date`；
>   - `window_factors_json` 和前一列相同。
>
>   其他 scope、其他 `status_reason` 的改記作廢，不屬於本 ADR 已定義的 supersede，一律拒絕（fail-closed，計入 `rejected_count`，記 WARNING）。理由：作廢列依下方「選用規則」走 LM-143，不查 `CORRECTION_REASON_FRAGMENTS`，所以上三項「差異必須和 LM-151、LM-152 的陳述相符」的前提不存在；作廢列也沒有可比較的結算收盤。改以重算依據驗證，事先宣告 §6.3「確認有誤之後」的「結算後才確認：……取不到就改記 `unresolvable_missing_data`」才寫得進去（FL-22「market 結算後確認」一格）。
- 方向：補定義（收緊）。要照實寫明：寫入驗證對作廢列放寬了一格，但效果是讓事先宣告已經規定的作廢寫得進去，畫面從「照原值呈現已確認有誤的結果」改為 LM-143。風控可改標。
- 送風控：**要**（改動風控 R10-2 的適用範圍）。
- CEO：否。

**N27-2（D-9.3：結算後才確認，不另等待）**
- 定位（唯一）：`作廢原因的判定順序中，第五值的位置交 quant 在事先宣告登記` 所在那一行。
- 動作：插在該行之前、同一層，成為 `index_bar_confirmed_erroneous` 這一點的第一個子點。
- 被取代原文：無。
- 字面：
> - （N-27；tech-architect 2026-10-18）**結算後才確認，不另等待**：已結算列的 P(T) 或 P(T+h) 收盤，在更正作業的判定視圖（D-9 第 5 點 ④）中為「確認有誤、尚未取得正確值」時，該次更正作業就以本值改記作廢，supersede 前一列（事先宣告 §6.3「確認有誤之後」：「結算後才確認：……取得正確值就重算；取不到就改記 `unresolvable_missing_data`」）。不等待 5 個觀察交易日，不延到之後的作業，也不看 T+h 之後已有多少觀察日。上句「等待期間……，或之後的更正作業」依此讀：等待只屬於結算前確認（結算評估）；結算後才確認，只看該次更正作業的判定視圖。寫入驗證見 D-11.4 第 11 點 (h) R10-2「適用範圍」。
>   - 理由：(1) 事先宣告「結算後才確認」一支沒有等待；(2) 延後判定需要一個依時間經過的啟動條件，與 D-3「晚到資料的觸發」第 1 點「啟動與否只依本點三類觸發是否存在」不合；(3) 延後期間，已結算列會照原值呈現一個收盤已確認有誤的結果，不帶 LM-143（風控 2026-10-18 C-22 確認 B-1）。
>   - 代價：作廢列依 R10-3 不再 supersede。之後才取得的正確值，只能依 D-3 `forecast_void_late_diag` 記診斷結果，不回到 `resolved`。同一情形若在結算前確認，D_5 之前取得正確值就會照常結算。兩條路徑的差別只取決於確認與結算的先後，不看預測內容或結果；只在獨立來源已接入、① 查詢失敗、而 D_5 之前的某次 ② 取得數值時才會出現【推論】。
>   - `wait_sessions`、`wait_deadline_session` 照抄被 supersede 列（D-3，不變）；D-3「結算評估寫入的列中……⇒ `wait_sessions ≥ 5`」不適用於本路徑（不變）。
>   - 這類作廢依事先宣告 §6.3「以上作廢一律計入作廢率與 W」照常計入。
- 方向：補定義（收緊）。
- 送風控：**要**（風控 Q-1 字句的讀法）。
- CEO：否。

**N27-3（FL-22 加格）**
- 定位（唯一）：`` - `[dividend_factor_corrected]` 而任一 `session_date` 改變、或 `window_factors_json` 沒變 → 拒絕。 ``
- 動作：在這一行之後、同一層插入。
- 字面：
> - （N-27）改記作廢的 supersede：P(T+h) 在更正作業的判定視圖中「確認有誤、尚未取得正確值」→ 寫入 `index_bar_confirmed_erroneous` 作廢列，`correction_causes = [settlement_close_corrected]`，不被 R10-2 拒絕，最新 outcome 走 LM-143。fixture 依 D-3 `forecast_index_check`「判定時怎麼讀」構成；現行暫定讀法下的構成是：結算所用的擷取 B1 正常，結算後另一次擷取 B2 觸發 X1 收盤本身不可用，B1、B2 構成的 X3 仍在待查證集合，獨立來源未接入。quant 依 N-26 登記讀法之後，依登記的讀法重建。同一 fixture 另做五個拒絕子例：`scope_kind ≠ market`；`status_reason ≠ index_bar_confirmed_erroneous`；前一列已作廢；`x2_shift_json` 與前一列不同；重算後收盤並非「確認有誤、尚未取得正確值」。
- 方向：收緊（測試）。

**N27-4（FL-68 (i)）**
- 定位（唯一）：`- (h) 啟動檢查不讀 label、`hit`、結果（AST 列舉 import）；更正作業沒有 CLI 或 API 入口（AST 列舉呼叫點）。`
- 動作：在這一行之後插入。
- 字面：
> - (i)（N-27）更正作業在被重查列的 D_5 之前啟動，判定視圖中 P(T+h) 收盤「確認有誤、尚未取得正確值」→ 當次寫入作廢列，不延後；`wait_sessions`、`wait_deadline_session` 等於被 supersede 列；之後的作業取得 `correct_close_obtained` → 不 supersede 該作廢列，只寫 `forecast_void_late_diag`。
- 方向：收緊（測試）。

### B. `gap_judged_through` 存放處

**方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **甲（建議）：新表 `forecast_gap_audit`，每次成功稽核一列，與 `forecast_gaps` 同一交易** | 稽核失敗時不留列，所以「最近一次成功」是機械的；兩個 status 值出自同一列；可以重算 | 表數 +1 | 低 |
| 乙：`forecast_ledger_events` 新 kind | 不加表 | 動到風控審過的封閉 kind 列舉；E 每天前進，耦合 E 的序號比較與 C9-7 | 耦合，**否決**（同 C-22 的丁案） |
| 丙：在 `forecast_gaps` 寫哨兵列 | 不加表 | 破壞 TG-b、TG-c 的計數與 UNIQUE 的語意 | **否決** |
| 丁：放進 `forecast_validation_snapshot` | 不加表 | 結算失敗時沒有 snapshot，但稽核其實成功了，值會落後 | **否決** |
| 戊：由 `forecast_gaps.detected_at` 或時鐘推算 | — | 沒有缺日時沒有任何痕跡；風控明文禁止 | **否決** |

另外，`forecast_run_end` 在稽核之前就寫入，又只增不改，加不了欄位。

**G-1（D-3 新表）**
- 定位（唯一）：`` - `forecast_gaps(gap_id, session, claim_id, scope_key, reason, detected_at, run_id NULL, UNIQUE(session, claim_id, scope_key))`：`scope_key = '*'` 代表整個 claim。 ``
- 動作：在這一行之後插入。
- 被取代原文：無。
- 字面：
> - **`forecast_gap_audit`**（N-24；tech-architect 2026-10-18；落實風控 2026-10-18 C-22 確認 N24-1「揭露判定進度」）：每次成功的缺日稽核（D-8 第 2 點）一列，記下該次稽核的判定上界。只增不改（D-2 第 2 點）。
>   - **欄位**：
>     - `audit_id INTEGER PRIMARY KEY AUTOINCREMENT`；
>     - `audit_now NOT NULL`：稽核開始、讀任何資料之前讀一次的 store 時鐘；D-8 第 2 點「判定上界」的比較一律用這個值，不另讀時鐘；
>     - `range_json`：[D_reg, 最新觀察日]，`{start, end}`；D_reg 為 None 時為 null；
>     - `judged_through`：本次已判定的觀察日中最晚的一日；沒有時為 null；
>     - `judged_count INTEGER NOT NULL`、`unjudged_count INTEGER NOT NULL`：範圍內已判定、尚未判定的觀察日數；
>     - `gaps_written INTEGER NOT NULL`：本次寫入的 `forecast_gaps` 列數；
>     - `recorded_at`（store 時鐘）。
>   - **寫入者與時機**：只有 `audit.py` 的缺日稽核函式（AST 列舉呼叫點）。與同一次稽核的 `forecast_gaps` 列、A-77 第 10 項的未觀察平日登記在同一個主 DB 寫入交易內，最後寫入、隨該交易 commit。稽核失敗、交易 rollback 時不留任何列，所以本表只記成功的稽核。欄位全部由該函式自行填入，不接受呼叫端傳入（D-2 第 3 點）。
>   - **寫入驗證**（任一項不成立，整個稽核交易都不寫入，記 WARNING）：
>     - `range_json` 為 null ⇒ `judged_through` 為 null，兩個計數與 `gaps_written` 都是 0；
>     - `judged_through` 為 null ⇔ `judged_count = 0`；
>     - `judged_through` 非 null 時，它是本次稽核所讀觀察日集合中、範圍內的一日；而且已判定的日子，恰好是範圍內 ≤ `judged_through` 的全部觀察日：這些日子都有 `late_cutoff_at ≤ audit_now`，晚於它的每一日都有 `late_cutoff_at > audit_now`（`late_cutoff_at` 以 D-7.4 的同一個函式、取 T ＝ S 計算）；
>     - `judged_count + unjudged_count` ＝ 範圍內的觀察日數；
>     - `gaps_written` ＝ 本交易寫入的 `forecast_gaps` 列數，而且每一列的 `session` ≤ `judged_through`；
>     - `judged_through` 早於前一列的值時（例如觀察日集合因 X2 確認而回溯縮小，A-77 第 11 項），記 WARNING，照實寫入，不拒絕。
>   - **讀取**（AST 列舉呼叫點；讀取一律經 `store.py`）：
>     - `views.py`：`GET /api/forecast/status` 的 `last_gap_audit_at` ＝ `audit_id` 最大一列的 `audit_now`，`gap_judged_through` ＝ 同一列的 `judged_through`；沒有任何列時兩者都是 null（D-8 第 5 點）。API route 原樣回傳；`app/api/**` 與前端不得以 `late_cutoff_at`、`forecast_gaps` 或時鐘導出這兩個值（AST）。
>     - `recorder.py` 的編排函式：D-7 第 2 點「本次缺日稽核已 commit」＝ 本次執行的稽核寫入了本表的一列，以稽核函式回傳的 `audit_id` 確認。
>     - `validation.py`：缺日率（失效條件 F-3）與任何以缺日界定的分母，只計 ≤ 所用列 `judged_through` 的觀察日（D-8 第 2 點 N-24「比率不因尚未判定而偏低」）。驗證快照所用的列是本次執行稽核寫入的那一列，它的 `audit_id` 記入該 snapshot 的 `stats_json`（鍵 `gap_audit_id`），以存下的值重算時結果逐位相同。
>     - 稽核工具。
>   - **限制**：不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定；匯出不得讀它。
- 方向：補定義（收緊）。
- 送風控：依風控 A 段的註記不必回送，`gap_judged_through` 的定義沒有改。
- CEO：表數屬知悉（G-5）。

**G-2（D-1 模組表）**
- 定位（唯一）：`| `app/forecast/audit.py` | 缺日稽核 |`
- 被取代原文：同定位字串。
- 字面：`| `app/forecast/audit.py` | 缺日稽核；`forecast_gaps`、缺日稽核所做的未觀察平日登記與 `forecast_gap_audit`（N-24）在同一個主 DB 寫入交易內寫入，`forecast_gap_audit` 只能從這裡寫入（AST） |`
- 方向：不變（模組歸屬）。

**G-3（D-8 第 2 點，風控的子點句末加已決註）**
- 定位（唯一）：`統計只到 `gap_judged_through`，文案另經 creative-lead 起草、風控審查。`
- 動作：在句末接上，風控原句不動。
- 字面：`〔已決：存放於 D-3 `forecast_gap_audit`（N-24；tech-architect 2026-10-18）〕`

**G-4（D-8 第 5 點，取值來源）**
- 定位（唯一）：`這三個值若要在畫面上呈現，文案另經 creative-lead 起草、風控審查。`
- 動作：在該子點之後、同一層插入。
- 字面：
> - （N-24）`last_gap_audit_at`、`gap_judged_through` 都取 D-3 `forecast_gap_audit` 中 `audit_id` 最大的一列（分別是 `audit_now`、`judged_through`），兩個值出自同一列；沒有任何列時都是 null。所以 `last_gap_audit_at` 是最近一次**成功**的缺日稽核的稽核時刻，失敗的嘗試不會讓它前進。
- 方向：補定義。這和 A-77 第 10 項「延到下一次成功執行才登記」的揭露用意一致。
- 送風控：請風控**知悉**。風控若認為 `last_gap_audit_at` 應該包含失敗的嘗試，再回送。

**G-5（表數連帶）**
- `- 表數多（18 張），寫入規則有一部分在 trigger 裡。`：「18 張」改為「19 張」。
- `- 18 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。`：「18 張」改為「19 張」。
- M-11 列有兩處要改：
  - 定位 `新增 13 張表（第九、十批加`：把「新增 13 張表」改為「新增 14 張表」；
  - 定位 `；C-22 加 `forecast_index_check`）並取欄位聯集`：在 `` `forecast_index_check` `` 之後加「；N-24 加 `forecast_gap_audit`」。
  - 注意：只寫「新增 13 張表（」不唯一，修訂紀錄裡也有。
- 待決事項 CEO 段，在 `13. （C-22，知悉）M-11 的表數隨` 那一點之後插入：
  `14. （N-24，知悉）M-11 的表數隨 `forecast_gap_audit` 由 13 張改為 14 張，全部表數由 18 張改為 19 張。`
- 方向：不變，CEO 知悉，比照第 12、13 點。

**G-6（FL-67 (n)）**
- 插在 C 段的 (m) 之後。
- 字面：
> - (n)（N-24 存放處）稽核成功 → `forecast_gap_audit` 恰好一列，與該次的 `forecast_gaps` 列同一交易；稽核在寫入前拋例外 → 兩者都沒有，`last_gap_audit_at`、`gap_judged_through` 不前進；status 回傳值等於最新一列的 `audit_now`、`judged_through`（AST：API route 不 import `late_cutoff_at` 的函式）；驗證快照的 `stats_json.gap_audit_id` 等於本次稽核的 `audit_id`；寫入驗證三種拒絕各一格：已判定的日子不是前綴、`gaps_written` 不符、缺日列的 `session` 晚於 `judged_through`。

### C. 風控 suggested 兩項

**(a) 採納。**

理由：查證列和 X2 確認分成兩個交易時，中途中斷會留下一筆「來源沒有這一天」、卻沒有 X2 確認的查證列。下一次 ② 會再查一次，X2 確認改由較晚的查證列導出，確認時點就隨「有沒有中斷」而不同。

**A-1（C22-1「寫入者與時機」）**
- 定位（唯一）：`**寫入者與時機**（各自一個交易：detection、該次 ① 查證，以及由它導出的 determination 同一交易）：`
- 被取代原文：同定位字串。
- 字面：`**寫入者與時機**（交易邊界：detection、該次 ① 查證，以及由它導出的 determination 或 `x2_confirmed_non_session` 同一交易；② 與 ③ 的每一筆查證列，與由它導出的 determination 或 `x2_confirmed_non_session` 同一交易；不同查證列各自一個交易）：`
- 另外，在 `其他任何程式路徑（API、CLI、更正作業、重放、缺日稽核）都不得寫入本表` 那一行之後、同一層插入：
> - （風控 2026-10-18 C-22 確認 suggested (a)）**由查證列導出的 X2 確認**：`basis = verified` 的 `x2_confirmed_non_session`，只能和它 `verification_ref` 所指的查證列在同一個交易內、由同一個 store 函式寫入：先寫查證列，再寫事件；`verification_ref` 只取該函式剛寫入的 `check_id`，不接受呼叫端傳入（AST 列舉呼叫點）。A-77 第 7 項的寫入驗證在插入事件之前完成；不成立時（例如重算後 d ∈ D-8.1 (i)），查證列照樣寫入，事件不寫，記 WARNING，該 detection 留在待查證集合（事先宣告 §6.3「查證程序」：每次查詢都新增一列，查不到也記）。

**A-2（D-9.2 ③）**
- 定位（唯一）：`查證紀錄與 X2 確認照既有規則寫入，各自一個交易。寫入規則依`
- 被取代原文：只換其中 `查證紀錄與 X2 確認照既有規則寫入，各自一個交易。` 這一句；其後 C22-4 的句子不動。
- 字面：`查證紀錄與 X2 確認照既有規則寫入：每一筆查證紀錄與由它導出的確認判定或 X2 確認同一個交易；不同查證紀錄、直接確認的 X2，各自一個交易（D-3 `forecast_index_check`「寫入者與時機」）。`

**A-3（FL-67 (l)）**
- 定位（唯一）：`- (k) `views`、API route、匯出 import 或呼叫本表的讀取函式 → AST 失敗；C22-1 所列的讀取呼叫點各一格可以讀。`
- 動作：在這一行之後插入。
- 字面：
> - (l)（suggested (a)）查證列與導出的 X2 確認同一交易：在兩次插入之間注入例外 → 兩者都不存在；重算後 d ∈ D-8.1 (i) → 查證列存在、事件不存在、記 WARNING，detection 仍在待查證集合；從其他呼叫點以既有查證列的 `check_id` 寫入 `basis = verified` 的事件 → AST 失敗。

**A-4（suggested，我順帶發現的小缺口，採不採由 coordinator 決定）**
- 問題：③ 部分寫入之後，如果該次評估在 ④ rollback，該 version 已經出現在部分 `source_onboarding` 列，下一次就不會再做完整的 ③。
- 定位（唯一）：`還沒有出現在任何 `source_onboarding` 列時`
- 改為：`還沒有出現在 `check_id` ≤ 前一列 `forecast_settle_eval.index_check_max`（沒有前一列時為 0）的任何 `source_onboarding` 列時`
- 方向：收緊。不必送風控。

**(b) 修正：這是我上一輪的字面錯誤，刪掉「寫入時重算 d ∉ (i)」。**

**B-1（C22-1 寫入驗證）**
- 定位（唯一）：`` - `x2_pending` 只能有 `no_error`，而且只限 `x2_case = set_iii_only`，寫入時重算 d ∉ D-8.1 (i)；`conflict` 寫任何 determination 都拒絕（A-77 第 5 項）。 ``
- 被取代原文：同定位字串。
- 字面：
> - `x2_pending` 只能有 `no_error`，而且只限 `x2_case = set_iii_only`、`basis = verified`、`basis_check_id` 所指查證列 `result = value_obtained`；不讀 D-8.1 (i)，d 已經進入 (i) 也照寫（風控 2026-10-18 C-22 確認 suggested (b)）。`conflict` 寫任何 determination 都拒絕（A-77 第 5 項）。理由：`no_error` 的意思是「獨立來源有 d，d 是交易日，這根 bar 沒有 X2 的錯誤」（事先宣告 §6.3 X2「只有 (iii) 成立」一支）；d ∈ (i) 和它同向，不矛盾。d ∉ (i) 是 X2 確認的必要條件（A-77 第 5 項），不是 `no_error` 的條件；要求它，會讓 d 進入 (i) 之後、獨立來源也確認有 d 的 detection 永遠留在待查證集合。
- 方向：補定義（更正 TA 的錯誤）。計分不變（待查證列與 `no_error` 都照原值計分），只是待查證數減少。
- 送風控：不必，請風控知悉。

**B-2（FL-67 (m)，接在 (l) 之後）**
> - (m)（suggested (b)）`x2_pending`、`set_iii_only` 的 d 在偵測之後進入 D-8.1 (i)，之後的 ② 取得 d 的數值 → 寫入 `no_error`，detection 離開待查證集合；同一情形改為「來源沒有這一天」→ 依 (l) 不寫 X2 確認，detection 留在集合內。

**殘餘情形（不出字面，請列入追蹤）：**
- **候選 N-28（tech-architect → 風控；期限：獨立來源接入前）：** d ∈ (i)，獨立來源卻沒有 d 時，detection 會永遠留在待查證集合，每天被重查。這是一種證據矛盾，但 A-77 第 5 項的矛盾定義要求有正面休市證據，這種情形不在定義內。
- **官方休市日表接入時，併入既有的「同批送風控」重審：**
  - `set_iii_only` 的 d 之後被直接確認 X2 時，待查證集合沒有出口（現行出口只認 `verification_ref`）；
  - detection 的身分不含 `x2_case`，所以 set_iii_only 轉成 conflict 時，conflict 列寫不進去。
  - 這兩種情形都只在休市日表接入時才會出現。

### D. coordinator 追問：N21-2 的位置

**我的本意是並列**，也就是 `forecast_correction_job` 的直接子點。

「不放 `triggers_json`……也不放 `forecast_correction_job_end`（第 5 點的驗證在作業開始時就要做）」那一子點，說明的是 `market_scan_*` 的存放位置，屬於 `market_scan_*` 那一點。「判定視圖欄位」和 `market_scan_*` 都是本表欄位的說明，是並列關係。

移動方式：
1. **移出：** 定位（唯一）`（N-21；tech-architect 2026-10-18）**判定視圖欄位**`。整段移走，包含它的四個子點（from、max、快照等欄位、寫入驗證）。
2. **移入：** 插在 `- 不放 `triggers_json`（它是觸發陣列，不是標頭），也不放 `forecast_correction_job_end`（第 5 點的驗證在作業開始時就要做）。` 那一行之後，以及 `` - `forecast_correction_job_end(correction_job_id PK, rechecked_count, changed_count, rejected_count, void_late_data_count, ended_at)` `` 那一行之前。後者唯一；修訂紀錄裡的舊版不含 `void_late_data_count`。
3. **縮排：**
   - 主點和「（N-4；晚到資料的觸發第 2、5、8 點）`market_scan_from`、`market_scan_to`」同一層，4 個空格加「- 」；
   - 四個子點用 6 個空格。
4. **修訂紀錄：** N21-2 的編輯註記改為「依 tech-architect 確認，與 `market_scan_*` 一點並列」。字句不變，方向不變。

### E. 給 qa-reviewer 的約束（新增 C34～C39，逐條可檢查）

- **C34：** R10-2 的三項只用在 `status = resolved` 的新列；作廢的新列走「適用範圍」的驗證（FL-22 N-27 格，拒絕子例各一格）。
- **C35：** 更正作業對「結算後才確認」不等待、不延後；啟動檢查不讀觀察日數，也不讀時鐘差（AST；FL-68 (i)）。
- **C36：** `basis = verified` 的 X2 事件，只由查證列的寫入函式在同一交易內寫入；`verification_ref` 不接受呼叫端傳入（AST；FL-67 (l)）。
- **C37：** 寫入 `x2_pending` 的 `no_error` 時，不呼叫 `final_sessions()`（spy；FL-67 (m)）。
- **C38：** `forecast_gap_audit` 只由 `audit.py` 寫入，和 `forecast_gaps` 同一交易；status 的兩個值出自同一列；API 與前端不推算；snapshot 的 `stats_json.gap_audit_id` 存在（AST、FL-67 (n)）。
- **C39（A-4 採用時）：** ③ 的判斷以前一列 `forecast_settle_eval.index_check_max` 為界。

### F. 交給其他部門的事項

- **quant（N-26）：** 登記讀法時，請明寫「結算之後才出現、已確認有誤的擷取，是否會讓結算時所用、本身正常的擷取變成『尚未取得正確值』」。
  - 照現行以交易日為單位的暫定讀法：會，這正是 N-27 的路徑一；
  - 改為以 bar 為單位：不會。但相對於暫定讀法是放寬，要送風控。
  - 另外請考慮（suggested）：§4.2 另列「結算後才確認而改記作廢」的筆數。計法是鏈尾作廢、`supersedes_id IS NOT NULL`、`status_reason = index_bar_confirmed_erroneous`，逐列數出，不另存欄位。
- **風控（只是觀察，不出字面）：** 依你的 N21-3 第二個新子點，X2 順延後的新 T+h 不在任何結算快照裡時，該筆會被拒絕寫入。畫面上會繼續呈現順延前的結果，不帶 LM-150 或 LM-143，性質和 B-1 相同。請裁定要不要另開追蹤。

### 送風控與方向彙總

| 項目 | 方向 | 送風控 | CEO |
|---|---|---|---|
| N27-1 R10-2 適用範圍 | 補定義（收緊）；寫入驗證對作廢列放寬一格 | **要** | 否 |
| N27-2 D-9.3 不另等待 | 補定義（收緊） | **要** | 否 |
| N27-3、N27-4 | 收緊（測試） | 隨 N27-1、N27-2 | 否 |
| G-1～G-3、G-6 | 補定義（收緊） | 不必（風控 A 段） | 表數知悉 |
| G-4 `last_gap_audit_at` 取值 | 補定義 | 知悉 | 否 |
| G-5 表數 18→19 | 不變 | — | **知悉** |
| A-1～A-3（suggested (a)） | 補定義（收緊） | 不必 | 否 |
| A-4 | 收緊 | 不必 | 否 |
| B-1、B-2（suggested (b)） | 補定義（更正錯誤），計分不變 | 不必，知悉 | 否 |
| N21-2 位置 | 不變（編排） | 不必 | 否 |

**其他部門**（product-manager、creative-lead、devops-sre、dev-lead、data-engineer、frontend-engineer、qa-reviewer、qa-e2e、art-lead 等）：本次未參與。這是純架構評估，沒有改任何檔案。

## 三、驗證

**讀過的內容：**
- 風控 C-22 確認全文；
- 我上一輪的 C-22 提案全文；
- ADR-0027 目前的工作樹（已含 tech-writer 本批）：
  - D-1、D-3（含 `forecast_index_check`、`forecast_correction_job`、晚到資料的觸發、`forecast_settle_eval`）；
  - D-8 第 1、2、5 點；
  - D-9 第 2、3、5 點；
  - D-11.4 第 11 點 (h)（T-4、R10-2、選用規則）；
  - FL-22、FL-67、FL-68；
  - 修訂紀錄的 C-22 段；
- 事先宣告 §6.3「大盤指數序列」「確認有誤之後」（L1270–L1308）；
- `回報格式.md`。

**用 Grep 確認的事：**
- 本回報的每一個定位字串，在目前工作樹中都唯一；
- 作廢列的價格欄位沒有定義；
- `last_gap_audit_at` 沒有取值來源的定義；
- 「新增 13 張表（」不唯一，所以改用較長的字串。

**屬於推論、未查證的部分：**
- 以 bar 為單位的讀法下，作廢 supersede 不可達；
- 甲方案的不對稱只在 ①失敗、②成功的情形出現；
- `late_cutoff_at` 隨 S 遞增（G-1 的寫入驗證會攔下反例）。

**沒有做的事：** 沒有改任何檔案，沒有讀 `.env` 或 `*.db`，沒有跑程式或 git。

**CEO 要驗證的：** 只有知悉表數 18→19（待決事項 CEO 段第 14 點）。

## 四、下一步

1. **coordinator：**
   - 把 N27-1～N27-4 送風控單項確認，G-4 附上請風控知悉；
   - 其餘（G 段、A 段、B 段、D 段的移動）可以交 tech-writer 另開一批套用，疊在本批之後；
   - 追蹤清單：N-27 改為「TA 已提案，待風控確認」；新增候選 N-28；在 N-26 的描述加上 F 段的 quant 問題；決策包二補遺另加一項表數知悉。
2. **風控：** 確認 N27-1、N27-2，並裁定 F 段那一項觀察要不要另開追蹤。
3. **quant：** N-26 登記時一併處理 F 段的問題。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-18-C22與N21至N24單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-C22存放表與N21更正作業視圖及N22至N24提案-tech-architect.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md

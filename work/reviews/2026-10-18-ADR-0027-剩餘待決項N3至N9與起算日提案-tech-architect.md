# ADR-0027 剩餘待決項 N-3～N-6、N-9 與起算日提案（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

六項都已提案。沒有新增 A 號，方向都是「補定義（收緊）」或「不變」。掛載的 A-56、A-61、A-63、A-75、A-77 原本就屬收緊類，A-65 屬兩面類，A-10 屬 r1，不在 33 條統計內。因此 ADR-0027 的累計統計 18／2／9／1／3 不變。

- **N-9：要補，而且不只補第 10 項。**
  - A-77 第 5、7 項也用到官方休市日表：第 5 項的 `evidence = official_holiday`；第 7 項 `trigger = official_holiday` 的寫入驗證；第 7、10 項 payload 的 `holiday_table`。
  - 另有一個實質缺口：K-10 的 `official_holidays` 回傳 None 時，同時代表「尚未接入」與「不在涵蓋年度」。第 10 項的 `holiday_coverage` 卻要分 `table_absent` 和 `not_covered`，單靠 K-10 的函式分不出來。
  - 提案：把 K-10 前半句改成「凡提及處一律適用」，另加一個同源的中繼資料函式。
- **N-3：計數來源用 `session_calendar_conflict` 新增 `origin = candidate_t_x2`。**
  - 查證發現：direct 基礎的 X2（trigger 是 weekend／official_holiday）時，這類 d 因 (iv) 也不成立，已經會寫 `origin = candidate_t`。真正什麼都沒留下的是 verified 基礎（trigger 為 null）。
  - 新 origin 兩種情形都寫，讓 (h5) 只有一個計數來源。
  - 事先宣告 §4.2 的作廢數列逐一列出了 origin，所以要排入 v0.13。
- **N-4：新增只增不改的表 `forecast_void_late_diag`。**
  - 只由更正作業寫入，指向作廢鏈尾的 `outcome_id`。
  - `void_late_data_count` 必須等於該作業寫入這張表的列數。
  - 另指出一個依賴：T+h bar 晚到算不算「來源修訂」觸發，現行條文沒寫。不寫明的話，這張表和計數都會低報。附建議條文。
- **N-5：查證結果是現行條文沒有 `db_restored` 的撤銷規則。**
  - R10-7 只由更正作業觸發；F-3 只管 PIT 違規。
  - 但題目所說的情形（判定留存、參與判定的列遺失），在現行還原前提下不會發生〔推論〕。
  - 真正的缺口在失落時間線：失落時間線上做過的判定（升級、F-2 下架）會無聲消失；新時間線又會在同一個檢查點再判一次，等於重抽。
  - 提案甲案（建議）：還原後 N_R 以內的檢查點，正面結果不認列，並揭露。
  - 甲案有殘餘風險：失落的 F-2 下架可能被抹掉。乙案交風控裁定。
  - 另附兩條：前提被破壞時的縱深撤銷，以及 D_v 因還原而後移時的揭露。
- **N-6：ADR 端的計數來源不新增欄位。**
  - 用既有 snapshot 的 `e_read_event_seq`／`e_read_outcome_seq`，加上事件與更正列的序號，以單一函式 `mask_episodes` 重建遮蔽期。
  - 遮蔽日數以 `computed_for_session` 與觀察日計。日數 ≥ 2 記 WARNING。
- **起算日：符合 D-14，不改詞，所以不觸發 LM-84 條件 1 的重送。**
  - 對照：LM-84 第 5 條「預測基準日在 {起算日} 當日或之後」對應 E 的「日期 ≥ D_v」；D_v 是該 claim 第一筆 E 紀錄的 T（`data_as_of`）。LM-99、LM-111 對應 `before_dv`，也就是 T < D_v。
  - LM-84、LM-85 裡的 `{起算日}` 是占位符，畫面上顯示的是日期。「紀錄起算日」這個詞只出現在 LM-99、LM-111。
  - D-14 自 r1（A-10）之後沒有被改過；2026-10-16 B-6 的結論仍然成立。
  - 附三條綁定約束：
    1. D_v 由單一函式導出；
    2. D_v 不存在時，LM-84、LM-85 不渲染，`before_dv` 也不成立；
    3. LM-84、LM-85 的一個實例只綁一個 claim。
  - 第 3 條會影響驗證狀態頁的版面。
  - LM-84 條件 1 要求 tech-architect 與 quant 都確認，quant 仍要具名確認。

## 二、逐項條文

### N-9（掛 A-75 的 A-96″ K-10，連帶 A-77；補定義（收緊））

**套用位置**：§D-7 第 3 點 K-10 第一子點（現行 L398），改寫成下面第一段；K-10 下新增第二段。

**被取代原文**：L398 的第一句，從「A-75 (iv) 與 A-77 第 2、4 項所稱的…」到「…兩邊同樣視為沒有官方休市日。」，逐字移入修訂紀錄。

> - （A-96″，K-10；N-9 改寫）本 ADR 凡提及「已接入（而且涵蓋 d 的）官方休市日表」之處，包括 A-75 (iv)，以及 A-77 第 2、4、5、7、10 項（含第 7 項 `trigger = official_holiday` 的寫入驗證、第 7 項與第 10 項 payload 的 `holiday_table`、第 10 項的 `holiday_coverage` 與偵測條件），都和 ADR-0028 `OfficialSessionCalendar`（T1-13）使用同一份來源、同一個函式定義，涵蓋年度也相同（ADR-0028 VS-5）。超出涵蓋年度時，各處同樣視為沒有官方休市日。日後新增的引用處同樣適用；本句的列舉只是提示，不是範圍。
> - （N-9）**表的中繼資料也只有一個來源**：和 `official_holidays` 同一個模組，定義 `official_holiday_table_meta(market) -> {version, coverage_start, coverage_end} | None`（暫定名；名稱與模組由 T1-13 決定，import 限制同上）。
>   - None 表示尚未接入。`coverage_start`、`coverage_end` 是 VS-5 涵蓋年度的第一天與最後一天，由同一份來源導出，不另存第二份。
>   - 不變式（性質測試）：`official_holidays(market, y)` 為 None，若且唯若 meta 為 None，或 y 不在 [`coverage_start.year`, `coverage_end.year`] 內。
>   - A-77 第 7、10 項 payload 的 `holiday_table` 只取自 meta。
>   - 第 10 項 `holiday_coverage` 依序判定：meta 為 None → `table_absent`；`official_holidays(market, d.year)` 為 None → `not_covered`；回傳的集合不含 d → `listed_as_trading_day`。集合含 d 時，d 依定義不是未觀察平日，不得寫入。
>   - grep／AST：寫入 `holiday_table`、`holiday_coverage` 或 `trigger = official_holiday` 的程式，只呼叫這兩個函式，不得另讀來源，也不得另存清單（比照 ADR-0028 CS-21、CS-25）。

**FL-19 (i)**（掛 A-77）加四格：`holiday_coverage` 三個值各一格，fixture 共用同一個假來源；另一格斷言 meta 與 `official_holidays` 的不變式。

### N-3（掛 A-77 第 5 項、第 12 項 (h5)，連帶 A-75 (iii)；補定義（收緊））

**被取代原文**：L487 payload 子點中的 origin 列舉，以及「`independent_source_absent` 只用於 `origin = post_x2_final_run`」一句，逐字移入修訂紀錄。

**A-77 第 5 項 payload（L487）改為：**
> `origin ∈ {x2_check, candidate_t, candidate_t_x2, post_x2_final_run, post_unobserved_backfill}`（`candidate_t_x2` 依 N-3 加入，見 A-75 (iii)）；`independent_source_absent` 只用於 `origin ∈ {post_x2_final_run, candidate_t_x2}`。

**A-75 (iii) 處理句（L392）之後新增：**
> - （N-3；A-77 第 12 項 (h5) 的計數來源）**(i) 成立、(iii) 不成立時：**
>   - (i) 成立時，(iii)、(iv) 都要判定，不得因為其中一項不成立就略過另一項。
>   - 記 WARNING，寫入 `session_calendar_conflict`，`origin = candidate_t_x2`。
>   - payload：
>     - `session_date`、`origin`；
>     - `x2_event_id`：使 (iii) 不成立的那筆 `x2_confirmed_non_session` 事件；
>     - `evidence`：取該 X2 事件的 `trigger`；`trigger` 為 null（`basis = verified`）時為 `independent_source_absent`；
>     - 使 d ∈ (i) 的 ok run 中 `run_id` 最小者的 `run_id`、`recorded_at`（比照第 12 項）；
>     - `detected_by_run_id`：該次 recorder 已寫入 `forecast_run` 時填入，否則為 null。
>   - payload 由寫入函式自行填入，不接受呼叫端傳入。
>   - 寫入函式在同一個交易內驗證，任一項不成立就拒絕寫入：
>     - `x2_event_id` 指向一筆已存在、`kind = x2_confirmed_non_session`、`session_date` 相同的事件；
>     - `evidence` 和該事件的 `trigger` 相符（null ⇔ `independent_source_absent`）；
>     - 重算後 d ∈ `final_sessions()`。
>   - 同一個 (`session_date`, `origin`) 只寫一次；同一個 d 之後再成為候選 T，不另寫。
>   - 和 `origin = candidate_t` 互相獨立：(iv) 也不成立時（`basis = direct`，d 是週末或官方休市日），兩筆都寫。§4.2 依 origin 分列，各自以不同的 `session_date` 計，不跨 origin 去重。
>   - 不寫缺日列（d 不是觀察日），不改 d 的觀察日身分，不觸發 §6.4。歸入 `E_NEUTRAL_EVENTS`（沿用 `session_calendar_conflict` 的歸類）。程式不得把它標為已解決。

**A-77 第 12 項 (h5) 句尾（L575）與待決事項 L1879 加：**
> 〔已決：計數來源為 `session_calendar_conflict`（`origin = candidate_t_x2`），見 A-75 (iii)（N-3）〕

**FL-19 (h5)(h6)（L1484-1485）**：
- (h5) 改為「候選 T＝d → `inputs_not_ready`，而且恰好寫一筆 `origin = candidate_t_x2`，重跑不重複寫入」；
- (h6) 的 verified 格斷言沒有 `origin = candidate_t`；direct 格斷言兩個 origin 各一筆；
- 加一格：`x2_event_id` 指向不同 `session_date` 的事件，或 `evidence` 和 `trigger` 不符，各自拒絕寫入。

### N-4（掛 A-65（R10-3）；補定義（收緊）；A-65 不換類別；無被取代原文）

**D-3，緊接在 `forecast_correction_job_end` 之後新增：**
> - **`forecast_void_late_diag`**（N-4；R10-3、事先宣告 v0.12 V12-20）：記錄作廢之後才補到資料的診斷結果。只增不改（D-2 第 2 點的 trigger 照樣適用），不得寫入 `forecast_outcome`。
>   - **欄位**：`diag_id INTEGER PRIMARY KEY AUTOINCREMENT`、`outcome_id`、`forecast_id`、`correction_job_id`、`supersedes_diag_id NULL`、`late_data_kinds`、`late_data_refs_json`、`diag_start_price_json`、`diag_end_price_json`、`diag_window_factors_json`、`diag_label`、`diag_hit`、`diag_baseline_hits_json`、`computed_at`（store 時鐘）。
>   - **參照**：
>     - `outcome_id` 指向 `status ≠ resolved` 的更正鏈鏈尾列。依 R10-3，作廢列不會再被 supersede，所以鏈尾固定。
>     - `forecast_id` 等於該列的 `forecast_id`；`correction_job_id` 指向 `forecast_correction_job`。
>     - 以上由寫入函式驗證，不成立就拒絕寫入。
>   - **`late_data_kinds`**：JSON 陣列，封閉列舉 `VOID_LATE_DATA_KINDS = {t_plus_h_bar, settlement_close, window_bar, dividend_factor, basket_member}`，排序固定、不重複、非空。
>     - 歸屬比照 `correction_causes` 的確定性規則：只會多記，不會少記。
>     - `late_data_refs_json` 每一項都帶來源參照（`run_id`、查證紀錄 ID，或因子修訂的參照）。
>     - 要增列，須修訂本點並送風控。
>   - **寫入者只有更正作業**（D-9.5）：
>     - 依 R10-3，更正作業不重算作廢列的 outcome。但對重查範圍內 `status ≠ resolved` 的鏈尾列，要以目前可得的資料，經 `scoring.py` 的同一套結算函式算一次診斷結果。
>     - D-9.1 第 2 點的 cutoff 條件不適用，因為補到的資料本來就晚於 cutoff；其餘依 D-9.2、D-9.3。
>     - 診斷結果本身仍落入任一作廢條件時，不寫列。
>   - **鏈**：`UNIQUE(outcome_id) WHERE supersedes_diag_id IS NULL`，以及 `UNIQUE(supersedes_diag_id)`。同一個 `outcome_id` 之後又補到資料時，只在 `diag_*` 和鏈尾不同（正規化 JSON 逐位比較）時才新增一列，並填 `supersedes_diag_id`；相同就不寫。
>   - **計數一致**：`forecast_correction_job_end.void_late_data_count` ＝ 該作業寫入本表的列數，由寫入 job_end 的函式在同一個交易內驗證，不成立就拒絕寫入 job_end。所以 `void_late_data_count` 的操作定義是「補到資料、而且算得出診斷結果」的筆數。
>   - **用途限制**：
>     - 不影響 E、n、W、作廢率、任何 snapshot 欄位或任何狀態判定。本表不屬於 `E_CHANGING_EVENTS`，不在序號比較範圍內，所以不影響 `e_changed_since`。
>     - 只有 `validation.py` 的 §4.2 報表可以讀它：
>       - 「作廢後補到資料的筆數」以不同的 `forecast_id` 計；
>       - 模型與各必備基準的診斷命中率，取每個 `outcome_id` 的鏈尾，只在 E 上計算（D-11.1）。
>     - `views`、任何 API route 與匯出都不得讀它，畫面不顯示（AST 列舉呼叫點）。
>     - 欄位名不得使用 forward return 類識別字（ADR-0012 C-15），計算只在 `scoring.py` 內。
>     - 作廢列的 `status`、`status_reason` 不因本表而改變（V12-20）。

**D-11.4 第 11 點 (h) R10-3 句尾（L1049）與待決事項 L1880 加：**
> 〔已決：存放於 `forecast_void_late_diag`，見 D-3（N-4）〕

**建議條文**（需 data-engineer 確認可行）：
> - （N-4）**晚到資料的觸發**：一筆 ok run 新寫入 session s 的 bars，而且主 DB 有結算窗 [T, T+h] 含 s、`status ≠ resolved` 的鏈尾列時，這筆 run 視為「來源修訂」觸發，帶 `run_id` 納入下一次更正作業的 `triggers_json`。

**FL-59**（掛 A-65）加四格：
1. 作廢列落在重查範圍內，資料已補到 → 本表寫一列，`forecast_outcome` 列數不變，job_end 計數為 1；
2. 同一份資料重跑 → 不新增列；
3. 診斷結果仍是作廢 → 不寫列，計數為 0；
4. `views` 與 route 都不可達本表（AST）。

### N-5（查證，加三段條文）

**查證結果（現行條文）**
- **R10-7（L670）**：撤銷只由「更正作業改變四個欄位」觸發，不含 `db_restored`。
- **F-3（L1182）**：只撤銷 PIT 違規列參與的判定。
- **`db_restored` 現在只有三種效果**：
  - 屬於 `E_CHANGING_EVENTS`（L808），所以會遮蔽，直到下一筆 daily snapshot；
  - 是缺日原因（L584-586）；
  - 有 RC‴-1 第 5 格測試（L1757）與 FLT-4。
- **RC‴-1 的還原前提**：
  - L831：還原以整個主 DB 檔為單位，DB 檔以外保存的 snapshot 或序號不得用於判定；
  - L819：還原不得重編序號；
  - L829：序號大於目前最大值時，`e_changed_since` 為真，並記 WARNING。
- **ADR-0026 D-9**：
  - L342：主 DB 與市場 DB 在同一時點各做一份 `Connection.backup`；
  - L347-351：兩個檔從同一組備份一起還原。
- 結論：沒有撤銷規則。在上述前提下，「判定留存、參與列遺失」不會發生〔推論〕。缺口在失落時間線。

**N5-1（掛 A-63（RC‴-1），連帶 A-77 第 11 項（R10-7）；補定義（收緊）；無被取代原文）**

套用位置：D-11.2 的 R10-7 一點之後新增。
> - （N-5）**整檔還原不另設撤銷**：依 RC‴-1（還原以整個主 DB 檔為單位）與 ADR-0026 D-9.1、D-9.4（主 DB 與市場 DB 取自同一組 `Connection.backup`），留在還原後檔內的 snapshot，它讀到的 outcome 與事件都在它之前 commit，所以也都在檔內〔推論：SQLite 線上備份產生一致的時點快照〕。因此，還原後留存的 `better_than_baseline` 判定不會有參與列遺失；R10-7 不因 `db_restored` 觸發。
> - （N-5）**前提被破壞時撤銷**（縱深防禦）：任何 snapshot 的 `e_read_event_seq` 或 `e_read_outcome_seq` 大於目前看得到的對應最大值時，除了 RC‴-1 已規定的「`e_changed_since` 為真、記 WARNING」，另外：
>   - 該 claim 的有效狀態若是 `better_than_baseline`，在下一筆 daily snapshot 撤銷（降級），到下一個檢查點重判，比照 R10-7；
>   - 記 ERROR，交 devops-sre 依 ADR-0026 D-9.4 查還原程序；
>   - `mark-restored` 在寫入 `db_restored` 的同一個交易內做這項掃描，結果寫入 payload：`seq_check ∈ {ok, failed}`，以及不成立的 snapshot 清單。掃描不成立仍照寫事件，因為缺日原因要留痕；
>   - §4.2 揭露撤銷的日期、claim，以及觸發撤銷的 snapshot。

**N5-2 甲案（建議；掛 A-77 第 11 項，同 R10-7；收緊；統計面須 quant 在 v0.13 登記）**

套用位置：接在 N5-1 之後。
> - （N-5 甲案）**失落時間線的檢查點不得重抽**：
>   - `db_restored` 的 payload 由 `mark-restored` 自行填入，至少含 `backup_set_id`、`backup_taken_at`（取自 manifest）。事件的 `recorded_at` 就是還原時點。
>   - B_s ＝ `backup_taken_at` 當下或之前最新的觀察日；R_s ＝ 事件 `recorded_at` 當下或之前最新的觀察日。
>   - N_R(claim) ＝〔還原後檔內，第 0 相位格點（事先宣告 §4.1）中 ≤ B_s 的個數；D_v 不存在或晚於 B_s 時為 0〕＋ ⌈ |`observed_sessions()` ∩ (B_s, R_s]| ÷ h ⌉。有多筆 `db_restored` 時各自計算，取最大值。〔推論：每個格點最多讓 n 加 1，所以 N_R 是失落時間線在還原當下可能達到的 n 的上限〕
>   - `db_restored` 寫入之後才判定的檢查點，若 `checkpoint_n ≤ N_R`：
>     - 正面結果（升為 `better_than_baseline`、重新上架）不認列；負面結果（降級、F-2 下架）照常生效。
>     - 記法比照 A-28 (ii)：`stats_json.raw_checkpoint_result` 照寫；`suppressed_positive` 加必填欄位 `cause ∈ {suspended_f3, db_restored}`。
>     - 比照 A-28 (iii)：在 n＝150（族群 250）時正面結果不認列，條件二就成立，不得因此延後退出期限。
>   - N_R 只由單一函式 `restore_checkpoint_bound(claim)` 計算。它只讀主 DB 與觀察日函式，不讀 DB 檔以外的任何東西（RC‴-1）。
>   - §4.2 揭露每一筆 `db_restored`：`backup_taken_at`、還原時點、遺失的觀察日數、各 claim 的 N_R，以及因本點而不認列的檢查點。
>   - 本點的統計面規則由 quant 在事先宣告登記（v0.13）；登記之前照本點處理。

**Consequences（照實寫）**：
- 甲案的殘餘：失落時間線若已在 `checkpoint_n ≤ N_R` 的檢查點觸發 F-2 下架，新時間線重判時結果若不再是負面，claim 就不會下架；使用者曾看到的下架會消失。
- **乙案**（交風控裁定）：`checkpoint_n ≤ N_R` 的檢查點，F-2 條件一的 `fail(c)` 一律視為成立。代價是沒有負面證據的 claim 也可能因為還原而下架。
- 我建議甲案加揭露。

**N5-3（掛 A-10（D-14）；補定義（收緊））**

套用位置：D-14 的 D_v 定義下（L1334 之後）新增。
> - （N-5）「一經出現就不會移動」以沒有整檔還原為前提。還原的備份時點早於 D_v 時，D_v 依還原後的檔重新導出，可能晚於失落時間線上的 D_v。這時 §4.2 揭露該 claim「D_v 晚於 B_s，而且有 `db_restored` 事件」。

**FL 加格**：
- FL-58 (e6) 的 RC‴-1 六格之後加兩格：序號大於最大值時撤銷 `better_than_baseline`；還原後 `checkpoint_n ≤ N_R` 的檢查點正面結果不認列、負面結果照常生效。
- N_R 邊界加一格：D_v 晚於 B_s。
- FL-48 加一格：還原到 D_v 之前。

### N-6（掛 A-63（C9-7 甲案）；補定義（收緊）；無被取代原文）

套用位置：A-63 第 11 項 `n_disclosure_masked` 一點（L844）之後新增。
> - （N-6）**遮蔽期的計數來源**：
>   - 不新增欄位。由 `views` 的單一函式 `mask_episodes(claim_id, *, as_of)` 從既有資料重建。它和 `e_changed_since` 放在同一個模組、共用同一個序號比較函式，不用時鐘。
>   - **變動項**：`kind ∉ E_NEUTRAL_EVENTS` 的 `forecast_ledger_events`（依 `event_id`），以及 `supersedes_id IS NOT NULL` 的 `forecast_outcome`（依 `outcome_id`）。
>   - 對 claim c 與變動項 x：
>     - S_cover ＝ c 的 daily snapshot 中，對應讀取序號 ≥ x 的序號、`computed_for_session` 最早的一筆；
>     - S_before ＝ c 的 daily snapshot 中，對應讀取序號 < x 的序號、`computed_for_session` 最晚的一筆；
>     - 讀取序號缺漏、或不是非負整數的 snapshot，視為不涵蓋任何變動項（RC‴-1）。
>   - 同一組 (S_before, S_cover) 的變動項合為一個遮蔽期，`reason = e_changed_since`。
>     - 遮蔽日數 ＝ |`observed_sessions(as_of)` ∩ (S_before.`computed_for_session`, S_cover.`computed_for_session`]|。
>     - 還沒有 S_cover 時，視為進行中，右端取 `as_of` 當下最新的觀察日。
>   - 沒有 S_before（D_v 之後還沒有任何 daily snapshot）時：`reason = no_daily_snapshot`，日數 ＝ |`observed_sessions(as_of)` ∩ [D_v, 第一筆 daily snapshot 的 `computed_for_session`]|。D_v 不存在時不計。
>   - 正常情形下日數是 1：事件在當晚 snapshot 讀 E 之後 commit，由下一個觀察日的 snapshot 涵蓋。
>   - **WARNING**：缺日稽核（D-8.2）每次執行時，對每個已登記的 forward claim 呼叫 `mask_episodes`。有遮蔽日數 ≥ 2 的遮蔽期（進行中或剛結束）就記 WARNING，帶 claim、`reason`、S_before 的 `computed_for_session`，以及變動項的最小序號。
>   - 日數以 `computed_for_session` 與觀察日計，不以牆鐘計（比照 RC″-2）。觀察日集合可能因 X2 確認而回溯縮小（A-77 第 11 項），所以 §4.2 揭露時一併記下 `as_of`。
>   - `mask_episodes` 只供 §4.2 與 WARNING 使用，不得作為 `n_disclosure_masked` 或任何顯示判定的輸入。
>   - §4.2 的揭露項目與格式，由 quant 在事先宣告登記（v0.13）。

**FL-52 大盤與個股的遮蔽 FL**加格：
- 正常情形 → 1 日，不記 WARNING；
- snapshot 漏一天 → 2 日，記 WARNING；
- 序號缺漏的 snapshot 不涵蓋變動項；
- 沒有 snapshot 時自 D_v 起算；
- 注入倒退的時鐘，結果逐位相同。

### 「起算日」（LM-84 條件 1）

**結論：符合 D-14，不改詞。** 依據：
- D_v ＝ 該 claim 第一筆 `trigger=scheduled`、`late=0`、`supersedes_id IS NULL`、forward 紀錄的 T（L1332，r1 A-10），之後各輪沒有修改。
- E 的條件是「日期 ≥ D_v」（L642）。
- LM-84 第 5 條「預測基準日在 {起算日} 當日或之後」逐項對應；LM-99、LM-111 對應 T < D_v。
- 「起算」雖然也出現在 LM-66、LM-20 的「從…收盤起算」，但名詞不同（「紀錄起算日」對「收盤起算」），而且 LM-84、LM-85 只有占位符，畫面上是日期，不會混淆〔推論〕。

**條文（掛 A-10（D-14），連帶 A-56（LM-99）、A-61（LM-111）；補定義（收緊）；無被取代原文）**

套用位置：D-14 的 D_v 定義下新增。
> - （「起算日」用語，LM-84 條件 1）D_v 由單一函式 `claim_dv(claim_id) -> date | None` 導出。它是 store 的唯讀查詢；`validation.py` 判定 E、`views` 填字面，都呼叫它。值是 session 日期（`data_as_of`），不是寫入日期。
> - 字面的 `{起算日}`（LM-84、LM-85）與「紀錄起算日」（LM-99、LM-111）都綁定這個值，日期依年份規則格式化。
> - `claim_dv` 為 None 時：
>   - LM-84、LM-85 不渲染（承接 2026-10-16 B-6）；
>   - `before_dv` 不成立：plan 的 unavailable 原因與紀錄清單的 `exclusion_reasons`，都不得出現 `before_dv`。
>   - 〔推論，已核對 A-60 的不變式：D_v 不存在時，清單回傳的每一列都是 on-demand 或 `late=1` 的排程列，所以 `exclusion_reasons` 照樣非空〕
> - LM-84、LM-85 的一個實例只綁一個 claim 的 D_v。驗證狀態頁的同一區塊涵蓋多個 claim 時，不得用單一個 `{起算日}` 渲染；版面由 creative-lead 與 frontend 依 DV-7 處理。改成頁面層級的寫法（例如不帶日期）屬於改詞，要重送。

**FL-48** 加兩格：
- D_v 為 None → 找不到 LM-84、LM-85，也找不到 `before_dv`；
- 兩個 claim 的 D_v 不同 → 各自渲染自己的日期。

**給 quant 的觀察（不寫進 ADR）**：事先宣告 L1005 寫「第一筆排程紀錄寫入的那天」。它和 D-14 有兩處不同：一是取寫入日、不是 T；二是沒有排除 `late=1`。L702 用的「版本啟用日」也沒有點明是逐 claim 的值。建議在 v0.13 改成引用 D-14，方向「不變（引用）」。

## 三、驗證（讀了哪些檔與行）

- **ADR-0027** `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`：
  - 已讀：L1-60、L230-305（D-1～D-3、correction_job、ledger_events）、L300-499（D-4～D-8 第 7 項，含 A-75、K-10～K-12 在 L397-402）、L500-739（A-77 第 7～12 項、D-8.2/8.3、D-9、D-10、D-11.1～11.4 第 6 點）、L780-899（RC′-2、RC‴-1 在 L804-843、n_disclosure_masked 在 L844）、L955-984（A-60、A-61）、L1020-1159（R10-3 在 L1049）、L1170-1269（F-3 在 L1182、D-12 檢查點）、L1290-1349（D-14 在 L1296-1335）、L1448-1487（FL-61、FL-19）、L1740-1799（RC‴-1 六格、FLT-4）、L1860-1909（待決事項）、L2537-2548（累計統計）；
  - grep：K-10～K-13、`db_restored`、RC‴-1、R10-3、R10-7、D_v、`before_dv`。
- **事先宣告** `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`：
  - 已讀：L698-705、L720-731（§4.2 作廢數列的 origin 列舉、未觀察平日）、L1000-1007、L1270-1294（§6.4、V12-20）；
  - grep：V12-20、D_v、起算、`session_calendar_conflict`。
- **追蹤清單** `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` L60-90。
- **tech-writer 回報** `/home/user/AICompany/work/reviews/2026-10-18-ADR-0027-A96雙撇FL25套用-tech-writer回報.md`：全文（疑義 4 在 L64-67）。
- **字面清單** `/home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md`：
  - 已讀：L1290-1329、L1645-1674（L1662）；
  - grep：「起算」全部出現處、LM-84（L3439）、LM-85（L3440）、LM-99（L3511）、LM-111（L3523）、L3544。
- **TA 2026-10-16 提案** `/home/user/AICompany/work/reviews/2026-10-16-ADR-0027與0028修訂提案A1至A21-tech-architect.md` L250-279（B-6）。
- **ADR-0026** `/home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md`：grep D-9（L338-351、IV-18）。
- **ADR-0028** `/home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md`：grep VS-5（L118）；確認 ADR-0028 沒有「第 2、4 項」或 `holiday_table` 的同步字句。
- **續行派工** `/home/user/AICompany/work/dispatch/2026-10-18-續行派工-CEO繼續工作.md`：全文。
- **沒有做的事**：
  - 沒有讀 `.env` 或 `*.db`，沒有改任何檔。
  - 沒有跑 git，所以 HEAD d7601f7 是依任務單，我沒有自行核對；行號以我讀到的工作目錄為準。
  - SQLite 線上備份的一致性是推論，沒有在本機驗證。

## 四、下一步

**要回送風控的項目**
1. **N-9**：K-10 前半句改寫，另加 meta 函式。K-10 出自風控的 K-10 單項確認，改寫要單項確認。
2. **N-3**：新 origin `candidate_t_x2`、payload 與驗證，以及 (i) 成立時 (iii)、(iv) 不得短路。
3. **N-4**：`forecast_void_late_diag` 的用途限制與計數一致。存放處依 R10-3 由 TA 定，但用途限制與 `VOID_LATE_DATA_KINDS` 屬新約束，建議單項確認。晚到資料觸發的建議條文，先交 data-engineer 確認可行，再一併送。
4. **N-5**：N5-1～N5-3，以及甲案或乙案的裁定（殘餘的 F-2 下架消失風險，請風控明示接受或改採乙案）。
5. **N-6**：遮蔽期的定義、WARNING 門檻（≥ 2 個觀察日）、只供揭露的限制。
6. **起算日**：結論不改詞，不觸發重送，送風控知悉。三條綁定約束建議單項確認，其中「一個 LM-84 實例只綁一個 claim」會影響 DV-7 驗證狀態頁的版面。

**要和事先宣告同批的項目（這一批會動到事先宣告，所以是 v0.13，與 ADR-0027 修訂同一批，任何一份都不得單獨 commit）**
- **N-3**：§4.2 作廢數列的 origin 列舉加 `candidate_t_x2`；(h5) 計數的定義（quant）。
- **N-5 甲案**：還原後 `checkpoint_n ≤ N_R` 時正面結果不認列的統計規則，以及 §4.2 的 `db_restored` 揭露（quant）。
- **N-6**：§4.2 各 claim 的遮蔽期與遮蔽日數揭露（quant；ADR 端計數來源見上）。
- **N-4（建議同批）**：§6.4 V12-20「由 TA 定只增不改的存放處」改為引用 `forecast_void_late_diag`，並登記 `void_late_data_count` 的操作定義「補到資料、而且算得出診斷結果」，方向「不變（引用）」。
- **起算日（建議同批）**：L1005、L702 改為引用 D-14，方向「不變（引用）」；quant 另外要具名確認 LM-84 條件 1。

**不需要動事先宣告的項目**：N-9、N5-1、N5-3。

**落地順序**：風控確認之後，交 tech-writer 套用到 ADR-0027，和 quant 的 v0.13 同批。累計統計維持 18／2／9／1／3，修訂紀錄照例逐字保留被取代原文（N-9 的 L398、N-3 的 L487）。

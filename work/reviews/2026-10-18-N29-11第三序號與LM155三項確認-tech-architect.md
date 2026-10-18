# N29-11 第三序號欄名與 LM-155 三項確認（tech-architect）

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N29-11 第三序號欄名，以及 LM-155 的三項確認

## 一、本次結論

1. **第三序號定名為 `stats_json.e_read_job_end_seq`**。取值是「看得到的 `forecast_correction_job_end` 列中 `correction_job_id` 的最大值，沒有列時記 0」。和前兩個序號同一次讀，在同一個明確 `BEGIN` 的 read transaction 內、讀 E（含待重算集合）之前讀出，寫入時點相同。
   - `correction_job_id` 在作業開始時配號，所以它的順序本來不等於 job_end 的 commit 順序。
   - ADR 既有的 D-3「晚到資料的觸發」第 5 點（L423）已經規定：寫入 job_end 時，若已有 `correction_job_id` 更大、已有 end 列的作業，就拒絕寫入。FL-64 (e) 的 L2172 也已經有對應的測試格。
   - 所以只要這項驗證和 INSERT 在同一個寫入交易內，job_end 就會依 id 遞增的順序 commit，序號比較的依據（L1385～L1386）仍然成立。這一點我寫進下面的字面。
2. **「每一列都算」照風控字面落地，我判斷可以接受**，但有一條會過度遮蔽的路徑，照實寫出來：
   - 條件：有一筆大盤（market）scope 的待重算項一直解不掉（寫入驗證被拒，或快照數值一直對不上），而在當天驗證快照寫入之後，又有一次執行重寫了 `forecast_settle_eval` 列（23:10 重試或啟動補跑；這次重跑會再寫一列，是我的推論）。
   - 結果：第四類觸發會啟動一次什麼都不改的作業，它的 job_end 會讓所有 claim 的徽章遮蔽到隔天的 snapshot。
   - 解法建議用 (γ)：把第四類觸發的大盤子條件改成只認新出現的數值。它同時修正確認 (1) 的邊界，也讓過度遮蔽的路徑消失。
   - 若風控不採 (γ)，備案是 N29-11a 精確判準。它偏離風控字面，需送風控。
3. **另外查到一處衝突**：L1586「這是 `views` 讀取 `forecast_correction_job`、`forecast_correction_job_end` 的唯一呼叫點」。`e_changed_since` 改讀 job_end 之後，這句就不成立，必須同批改字（見第三組 3-g）。
4. **追加三點**：
   - (1) 答案是「否，有邊界」，要回送風控。
   - (2) 答案是「是」，另附一句明文。
   - (3) 同時成立時的取捨，已補定義字面，送風控。

## 二、各部門回報（tech-architect）

### 評估摘要

- 採用：第三序號 `e_read_job_end_seq`，形狀比照 `e_read_event_seq`。snapshot 記全部 job_end 列的最大值，比較端再決定哪些列算數。這樣日後若改採 N29-11a，snapshot 端的欄位不用動。
- 採用：N29-11 照風控字面，每一列都算。
- 建議：(γ) 收緊第四類觸發的大盤子條件，送風控。
- 備案：N29-11a，只在待重算集合改變時才算，送風控。只在 (γ) 被否決時才需要。
- 否決：在 job_end 加 `pending_set_changed` 欄位。這要改 schema，寫入端一判錯就是不遮蔽（fail-open）。N29-11a 用既有欄位就能算出同一件事，不需要這一欄。

### 方案比較（job_end 什麼時候算 `E_CHANGING_EVENTS`）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A：風控字面，每一列都算 | fail-closed；沿用既有的序號比較；不改 schema | 沒改變集合的作業也會遮蔽 | 在上述例外狀態下，遮蔽會長期接近全天 |
| A＋(γ) | 同 A；重跑不再啟動空作業 | 大盤待重算項最多晚一個觀察日重查（每個新觀察日都會重查） | 低 |
| N29-11a：依既有欄位判定集合是否改變 | 不過度遮蔽 | 比較端多一個判定函式；偏離風控字面 | 判定寫錯就會漏遮；設 fail-closed 預設值來緩解 |
| 加 `pending_set_changed` 欄位 | 判定結果可直接讀 | 要改 schema、要加寫入驗證 | 寫入端判錯就漏遮 |

### job_end 在什麼情形下讓 n 改變（另外確認）

- job_end 寫入時，「最近一個已完成作業」換成本作業，待重算集合的 (a)、(b) 兩部分跟著換（L1584～L1585）。
- 會讓 n 改變、卻沒有其他 E 事件的，只有「某筆預測離開或進入待重算集合，而本作業沒有為它寫 supersede 列」：
  1. (b) 裡順延後 T+h 不變的列（週末的 X2；L1595 已寫明會暫時遮蔽）；
  2. 前一個作業的 pending 項，重查後沒有任何欄位改變（L381 第 3 子點）；
  3. 已寫入順延結果的列，因其他類觸發重查、重算含 `x2_session_removed` 又被拒絕，於是新列入 pending。
- 寫了 supersede 列的作業，已經由 `e_read_outcome_seq` 涵蓋。
- **N29-11a 判準（備案）**：job_end J 為真，若且唯若下列任一項成立。J⁻ 指 `correction_job_id` 小於 J、已有 end 列的作業中 id 最大的一個。
  - (i) J 與 J⁻ 的 `pending_json` 中，`(forecast_id, tail_outcome_id)` 組成的集合不同；
  - (ii) 有一筆 `x2_confirmed_non_session`，`event_id` 落在 (J⁻.`ledger_event_max`, J.`ledger_event_max`]；
  - (iii) 任一欄無法解析。
  - J⁻ 不存在時，集合取空、`ledger_event_max` 取 0。
  - 理由：(b) 只會因為這個區間內的事件而不同；(a) 的增減都會反映在上述集合上。

### 決策：可直接貼入的字面

L 號是目前工作樹的行號（已套 N-29 批、尚未 commit）。每個定位字串都已用 Grep 確認在 ADR 內只出現一次。

**第一組：`stats_json` 的第三個序號**

1-a. 定位：`` `stats_json` 另登記 `e_read_event_seq`、`e_read_outcome_seq`（ ``（L1227）。方向：收緊。
- 被取代原文：
  > （r3，A-63；RC′-2、RC″-2、RC‴-1）`stats_json` 另登記 `e_read_event_seq`、`e_read_outcome_seq`（`pa9_holds` 的 `e_changed_since` 比較基準，見第 4 點第 11 項 (c)），以及 `e_read_at`（稽核用，不作比較基準；也不用 `computed_at`）。
- 改為：
  > （r3，A-63；RC′-2、RC″-2、RC‴-1；N29-11）`stats_json` 另登記 `e_read_event_seq`、`e_read_outcome_seq`、`e_read_job_end_seq`（`pa9_holds` 的 `e_changed_since` 比較基準，見第 4 點第 11 項 (c)；第三個依風控 2026-10-18 N-29 單項確認 N29-11 加入），以及 `e_read_at`（稽核用，不作比較基準；也不用 `computed_at`）。

1-b. 定位：`並在同一個 transaction 內讀出兩個值`（L1371）。方向：不變（編排）。
- 「讀出兩個值」改為「讀出三個值」。

1-c. 定位：`` `e_read_outcome_seq` ＝ 看得到的 `supersedes_id IS NOT NULL` 列中 ``（L1373）。方向：收緊。
- 在該行之後、「沒有列時記 0。」之前，同一層插入：
  > - `e_read_job_end_seq` ＝ 看得到的 `forecast_correction_job_end` 列中，`correction_job_id` 的最大值（N29-11；不論 `pending_json` 是否為空）；

**第二組：`e_changed_since` 加第三項比較**

2-a. 定位：`為真，若且唯若下列兩項任一成立`（L1375）。
- 「兩項」改為「三項」。

2-b. 定位：`` 而且 `outcome_id > e_read_outcome_seq` 的列。 ``（L1377）。方向：收緊。
- 在該行之後插入：
  > - 存在 `correction_job_id > e_read_job_end_seq` 的 `forecast_correction_job_end` 列（N29-11）。

2-c. 定位：`兩個欄位任一缺漏或不是整數，一律為真。`（L1378）。
- 「兩個欄位」改為「三個欄位」。

**第三組：其他引用這兩個序號、要同步修改的地方**

3-a. 定位：`` 任何 snapshot 的 `e_read_event_seq` 或 `e_read_outcome_seq` 大於目前看得到的對應最大值時 ``（L1206，前提被破壞時撤銷）。方向：收緊。
- 改為：
  > 任何 snapshot 的 `e_read_event_seq`、`e_read_outcome_seq` 或 `e_read_job_end_seq` 大於目前看得到的對應最大值時
- L1209 的 `mark-restored` 掃描寫的是「這項掃描」，會自動涵蓋，不必改。

3-b. 定位：`` **先讀 `e_read_event_seq`、`e_read_outcome_seq`，再讀 E** ``（L1379）。方向：收緊。
- 改為：
  > **先讀 `e_read_event_seq`、`e_read_outcome_seq`、`e_read_job_end_seq`，再讀 E**（N29-11：這裡的 E 包括事先宣告 N-29 (b) (i) 的待重算集合，由 D-11.4 第 11 點 (g) 的同一個 `store.py` 函式讀取）

3-c. 定位：L1370 那一點（`` 都是 `INTEGER PRIMARY KEY AUTOINCREMENT`：單調遞增、永不重用。 ``）。方向：補定義（收緊）。
- 在該點之後、同一層插入：
  > - （N29-11；tech-architect 2026-10-18）`forecast_correction_job_end` 沒有自己的配號欄，以 `correction_job_id`（`forecast_correction_job` 的 `INTEGER PRIMARY KEY AUTOINCREMENT`，作業開始時配號）比較。作業開始的順序不等於 job_end 的 commit 順序，所以下文「依據」對這個序號不直接成立；改由 D-3「晚到資料的觸發」第 5 點「沒有 `correction_job_id` 大於本作業、已有 end 列的作業」的再驗證保證。這項驗證與 job_end 的 INSERT 在同一個寫入交易內完成，所以已寫入的 job_end 依 `correction_job_id` 遞增的順序 commit：read transaction 看得到的最大值是 S 時，之後才 commit 的 job_end 列，`correction_job_id` 都大於 S。移除或放寬這項再驗證時，須同時修訂本點。

3-d. 定位：`` 寫入函式與 SQL 不得指定 `event_id`、`outcome_id`，由 SQLite 配號 ``（L1383）。方向：收緊。
- 改為：
  > 寫入函式與 SQL 不得指定 `event_id`、`outcome_id`，以及 `forecast_correction_job` 的 `correction_job_id`，由 SQLite 配號

3-e. 定位：`` 以及 `supersedes_id IS NOT NULL` 的 `forecast_outcome`（依 `outcome_id`）。 ``（L1398，`mask_episodes` 的變動項）。方向：收緊（揭露）。
- 改為：
  > 、`supersedes_id IS NOT NULL` 的 `forecast_outcome`（依 `outcome_id`），以及 `forecast_correction_job_end`（依 `correction_job_id`；N29-11）。

3-f. 不必改的地方：L1356、L1357、L1361、L1380（寫的是泛稱「序號欄位」）、L1388、L1205。

3-g. 定位：`` 這是 `views` 讀取 `forecast_correction_job`、`forecast_correction_job_end` 的唯一呼叫點。 ``（L1586）。方向：補定義（不放寬：只多開一個只讀一欄的呼叫點）。
- 改為：
  > 這是 `views` 讀取 `forecast_correction_job`、`forecast_correction_job_end` 的唯一呼叫點；唯一的例外是第 4 點第 11 項 (c) 的序號比較函式（`e_changed_since` 與 `mask_episodes` 共用）。它經 `store.py` 的另一個單一唯讀函式讀取 `forecast_correction_job_end` 的 `correction_job_id`，不讀其他欄位；snapshot 寫入端讀 `e_read_job_end_seq` 也只經這個函式（N29-11；AST 列舉呼叫點）。

**第四組：`E_CHANGING_EVENTS` 加 job_end**

4-a. 定位：`` `forecast_outcome` 中 `supersedes_id IS NOT NULL` 的列，依 `outcome_id`； ``（L1360）。方向：收緊。
- 在該行之後、同一層插入。第一句是風控字面，一字不改；括號內是 TA 補的欄名對應：
  > - （N-29；風控 2026-10-18 N-29 單項確認）`forecast_correction_job_end` 的每一列，依 `correction_job_id`（待重算集合改變驗證統計的成員，事先宣告 N-29 (b) (i)）。（TA 補：snapshot 端對應的讀取序號為 `stats_json.e_read_job_end_seq`，見下文「比較基準」。）
  >   - 依據與範圍（tech-architect 2026-10-18）：job_end 寫入時，「最近一個已完成作業」換成本作業，D-11.4 第 11 點 (g) 的 (a)、(b) 隨之改變。會使 n 改變、卻沒有其他 `E_CHANGING_EVENTS` 的，是某筆預測離開或進入待重算集合、而本作業沒有為它寫入 supersede 列：(b) 中順延後 T+h 不變的列（例如週末的 X2 確認）；前一作業的 pending 項重查後沒有任何欄位改變（D-3 job_end 驗證第 3 子點）；已寫入順延結果的列，經其他類觸發重查後被拒而新列入。是否屬於這幾種，不在序號比較中判斷；依「判斷不了的一律歸入 `E_CHANGING_EVENTS`」，每一列都計。代價：作業沒有改變集合時也會遮蔽，到下一筆 daily snapshot 為止。依 D-7.1 第 2 點的執行順序，作業在驗證快照之前完成，同一次執行的 snapshot 已涵蓋；遮蔽只發生在驗證快照之後才完成的作業。

**第五組：FL 測試格**

FL-68 (j) 末句已經有了，但還不夠。缺的是：第三序號的 RC‴-1 格、需要遮蔽的動機情境、不該遮蔽的對照格，以及 commit 順序的性質測試。

5-a. 定位：`` `sqlite_master` 斷言兩欄都是 `INTEGER PRIMARY KEY AUTOINCREMENT`。 ``（L2538）。方向：收緊（測試）。
- 在該行之後、與 L2539 同一層插入：
  > - （N29-11）RC‴-1 第 1、2、3、5 格對 `e_read_job_end_seq` 各加一格（第 3 格注入的是一筆 job_end commit；第 2 格另斷言依 N-5 撤銷 `better_than_baseline`）；寫入 `forecast_correction_job` 時指定 `correction_job_id` → 拒絕寫入；`sqlite_master` 斷言 `forecast_correction_job.correction_job_id` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`。

5-b. 定位：``驗證統計不計入待重算集合；job_end 寫入後 `e_changed_since` 為真。``（L2273）。方向：收緊（測試）。
- 在句尾接：
  > （N29-11）週末 X2、順延後 T+h 不變：snapshot 在 (b) 期間寫入，之後作業不寫列、寫入 job_end → 到下一筆 snapshot 之前，`e_changed_since` 與 `n_disclosure_masked` 為真；下一筆 snapshot 的 n 含該列；`mask_episodes` 的變動項含該 job_end，日數為 1。對照格：同一次執行中，作業在驗證快照之前寫入 job_end → 該 snapshot 的 `e_read_job_end_seq` 涵蓋它，`e_changed_since` 為假。AST：`views` 讀 `forecast_correction_job_end` 的呼叫點恰好是 D-11.4 第 11 點 (g) 所列的兩個 `store.py` 函式。

5-c. 定位：`兩種情形之後的下一個作業都可以寫入並寫完 job_end，其他觸發不被擋下；`（L2172，FL-64 (e)）。方向：收緊（測試）。
- 在句尾接：
  > 被拒的較小 id 作業沒有 job_end 列；性質測試：任意交錯之下，已寫入 job_end 的 commit 順序與 `correction_job_id` 的順序相同（N29-11 比較基準）。

5-d. 修訂紀錄 L4045、L4086 寫著「N29-11 本批未套用」，要由 tech-writer 改寫。被取代原文照慣例錄存。

### 追加三點（風控 LM-155 第四節）

**(1) 四類觸發是否全部是資料事件：答案為「否，有一個邊界」，需回送風控。**

- 第一類 `source_revision`：市場 DB 新出現的 ok 定案 run，屬於資料。
- 第二類 X2 確認、第三類大盤查證判定：只能由 recorder 與結算評估 ③ 寫入，其他路徑一律禁止，有 AST 列舉（L492～L499）。內容來自 bar、休市日表或獨立來源的查證結果，屬於資料。
  - 附帶情形（照實寫）：部署新的 `INDEX_VERIFICATION_SOURCE` 版本或新的休市日表時，會對全部待查證項重查（L497）。這是人工部署，但是全域性的，不針對個別預測。
- 第四類待重算的三個子條件：
  - 新觀察日：要有定案資料才成立，平時約每個交易日一次；
  - 新的定案 run：屬於資料；
  - **大盤子條件「新的 `forecast_settle_eval` 列的快照含 d 的列」**：每次結算評估都會寫一列（L428「每次結算評估一列」），包括 23:10 重試與啟動補跑。這次重跑會再寫一列，是我的推論，沒有實測。所以 d 的列已經存在、卻一直寫不進去的大盤項，每次執行都會在沒有新資料的情況下被重查。
- 重算是純函式，只讀有上界的視圖，所以結果只在輸入改變時才會不同。不過「重查不依時間經過」這句，對這個子條件只是勉強成立。
- 沒有人工指定的路徑：L419 禁止以操作者指定的觸發、日期或預測啟動更正作業；`mark-restored` 不屬於這四類觸發。啟動補跑本身不產生觸發，但它會寫 `forecast_settle_eval` 列，也會重新掃到中斷作業留下的觸發。
- **修正建議 (γ)**。定位：`` `scope_kind = market`，而且該列的大盤快照含該項 `shifted_t_plus_h` 的列； ``（L414）。方向：補定義（兩面：重查變少；大盤項最多晚一個觀察日重查）。需送風控。
  - 改為：
    > `scope_kind = market`，而且該列的大盤快照含該項 `shifted_t_plus_h` 的列，該列的數值（依 D-9 第 5 點 ④ 的 `checked_values_sha256` 正規化規則）和 `settle_eval_id ≤` W_S 的每一列 `forecast_settle_eval` 大盤快照中同一日的列都不同，或那些快照都沒有同一日的列（tech-architect 2026-10-18；理由：同一個數值已由先前的作業比對過，再出現只是重新讀取，不是新資料）；
  - 依據：W_S 以內的快照，都已經在先前作業開始時被評估過，或已被該作業的重算採用（L1128 只取 `settle_eval_id ≤ settle_eval_max`）。新觀察日子條件仍然每天觸發，所以不會卡死。

**(2) pending 項的原因是否以最近一次作業判定：答案為「是」。**

- L377 規定，重查過的項「以本作業的值取代」，包括 `reason`；沒重查的項原樣帶入。期限是否適用，由每一個作業依它自己的判定視圖決定（L1129、L1136，以及 (乙)）。
- C 項（寫入驗證被拒）每逢新觀察日就會被第四類觸發重查。所以修正之後，最晚下一個觀察日就會重分類；若成為等待資料型，就適用 N-29 (b)。
- 建議把這件事寫成明文。定位：`修正之後，由第四類觸發重查。`（L1136）。方向：補定義（收緊）。送風控，並請 quant 在 N-29 (b) 登記時寫成同一義。
  - 在句尾接：
    > 待重算項的 `reason` 以最近一次重查該項的作業判定（D-3 `pending_json`「以本作業的值取代」）；期限是否適用，只看最近一個已有 `forecast_correction_job_end` 列的作業的 `pending_json` 中該項的 `reason`。`write_validation_failed` 的項重查後成為前三種情形之一時，自該次作業起適用事先宣告 N-29 (b) 的期限；起算依 N-29 (b)，不因曾為 `write_validation_failed` 而重設或延後；該次重查時已到期者，依 D-11.4 第 11 點 (h) (乙) 處理。前三種情形的項重查後成為 `write_validation_failed` 時，自該次作業起不適用期限。
  - 「不重設」的理由：修程式的時點不能用來延長等待。C 期間若資料已經在，修正後會正常結算；只有資料真的不存在時才會作廢。
  - 對 LM-155 的影響：修正後若已經到期，這筆會直接作廢、不經過等待。條件句的前件不成立，整句仍然屬實。

**(3) 同時成立時的取捨：補定義字面，送風控。**

定位：`與 PIT 違規列的標示（LM-110＋LM-114）或 A-27 (c) 同時成立時的取捨，由 tech-architect 在本點補定義，隨待重算片段送風控；補定義之前，同時成立的列不顯示 label 與任何結算結果。`（L1587）。方向：補定義（收緊）。
- 改為：
  > 與其他規則同時成立時（tech-architect 2026-10-18 補定義，送風控；風控確認之前，同時成立的列不顯示 label 與任何結算結果）：
  > - A-27 (a)、(b)、(d)、(d′) 只適用於尚未結算的列，與本路徑（鏈尾 `resolved`）不會同時成立。
  > - 族群列不適用本路徑（LM-155 條件 ⑧）。A-27 (c) 成立時，依 (c) 與第 11 點選用 gate 片段；本路徑的禁止欄位與全域不顯示另外適用，所以 (c) 已結算列可加的 `settlement_date`、`outcome_status` 在這類列不得出現。(c) 不成立時，在族群已結算 label 核可、並經風控確認本路徑擴及族群之前，不顯示 label 與任何結算結果，FL-52 (d) 對該格失敗。
  > - `in_eligible_set = false` 的列（PIT 違規，以及 `before_dv`、`late`、`on_demand`）：狀態行用本路徑的待重算片段；資格標示照 A-61，並列 LM-110 與全部原因片段（PIT 列含 LM-114，排第一），視覺區隔照舊。兩者分屬不同位置，不互相取代；LM-110、LM-114 不在本路徑的禁止清單內。片段中「計入作廢統計」對 E 以外的列是否屬實，以 quant 對 §4.2 作廢數與作廢率涵蓋範圍的書面確認為準；確認為否時，E 以外的列不得用本路徑的片段，改為不顯示 label 與任何結算結果，FL-52 (d) 失敗，回送風控。
  > - PV-45 是否附加，照 A-27 (e) 既有條件，本點不改。
  > - 本路徑與 LM-150、LM-154、「診斷欄位更正的例外」之間的優先序不變。
- 注意：這一點把風控原本只問的 PIT 違規，擴及全部 `in_eligible_set = false` 的列，因為 LM-111～LM-113 的列會遇到同一個問題。

### 對實作的約束（qa-reviewer 可逐條檢查）

1. `e_read_job_end_seq` 和前兩個序號在同一個明確 `BEGIN` 的 read transaction 內，先於 E 與待重算集合讀出；三者任一缺漏、不是非負整數或大於目前最大值，`e_changed_since` 一律為真，並記 WARNING。
2. job_end 的「沒有 id 更大的已完成作業」驗證和 INSERT 必須在同一個寫入交易內。
3. `views` 讀 job_end 只經兩個 `store.py` 函式，有 AST 列舉；序號函式只讀 `correction_job_id`。
4. `mask_episodes` 與 `e_changed_since` 共用同一個比較函式，變動項含 job_end。
5. 若改採 N29-11a，判定函式只讀既有欄位，任一欄無法解析時為真；snapshot 端的欄位不變。

## 三、驗證

- 讀過的內容：
  - ADR-0027：L353～L385、L403～L442、L486～L499、L722～L743、L862～L901、L1120～L1149、L1190～L1239、L1330～L1350、L1350～L1419、L1425～L1493、L1540～L1602、L2167～L2172、L2520～L2543；
  - 風控 N-29 單項確認的相關段落；
  - 風控 LM-155 逐字審全文（L11～L220）；
  - 字面清單中 LM-110、LM-114 兩列。
- 用 Grep 確認的事：
  - 上列定位字串在 ADR 內都只出現一次；
  - `（N-5）RC‴-1 六格之後加兩格` 出現兩次，所以改用 L2538 定位；`job_end 寫入後 ... 為真` 單獨搜也出現兩次（另一處在 L4045），所以改用加長的字串；
  - L423 的再驗證已經存在；
  - FL-64 (e) 的 L2172 已有交錯作業格；
  - `stats_json` 沒有封閉的鍵清單。
- 推論、未查證：
  - 23:10 重試與啟動補跑會再執行結算評估、再寫一列 `forecast_settle_eval`；
  - N-29 (b) 的期限是相對於順延後的 T+h 起算（引用風控的說法，事先宣告尚未登記）。
- 沒有做的事：只用了 Read、Glob、Grep；沒有改任何檔案；沒有讀 `.env` 或 `*.db`；沒有跑測試。

## 四、下一步

1. tech-writer：照第一組到第五組落檔，並改寫修訂紀錄 L4045、L4086（附被取代原文）；交 coordinator 機械核對欄名，見風控 N29-11 列。
2. 送風控（同一份單項確認即可）：
   - 確認 (1) 的邊界與 (γ)；
   - 確認 (2) 的明文；
   - 確認 (3) 的補定義；
   - N29-11a：只在 (γ) 被否決、又認為過度遮蔽不能接受時才需要。
   - 這幾項都不改門檻、常數或風險上限，CEO：否。
3. quant：
   - N-29 (b) 登記時寫明：期限起算不因原因轉換而重設；
   - 回覆風控：「作廢統計」是否涵蓋 E 以外的列。這也是 (3) 第三點的前提。
4. dev-lead、qa-reviewer：依「對實作的約束」與 5-a～5-c 的測試格實作和審查。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-18-N29與plan略過紀錄單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-LM155逐字審-風控.md
- /home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md

# N-23 風控補充項回覆（R-Q7-3、R-Q3-3、R-Q7-5、C6／C25、suggested）

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

風控第四節「tech-architect」的 5 項都已回覆。這份只是提案，我沒有改任何檔案。

1. **R-Q7-3（揭露來源）**：採用風控的做法，並略為加強。`forecast_gap_audit` 加 2 欄：`market_run_now` 每列都填，`market_run_regression_json` 只在守衛成立時非 null。**表數不變，只加欄。** 字面分兩組：
   - 欄位定義與 FL 格與 CEO 的 Q7 裁決無關，風控確認後就可以落檔；
   - L359 子點改寫要跟第二批（CEO 同意 Q7）一起落檔。CEO 若不同意，改用下面的備用句。
2. **R-Q3-3（checkpoint 略過）**：
   - TA 這邊定的機械規則：檢查點只能在「第一筆 n 達到 n_j、而且寫入成功的 daily snapshot」判定。不能提前，也不能延後；不提供任何操作入口；新增 `UNIQUE(claim_id, checkpoint_n) WHERE eval_kind='checkpoint'`。
   - 過渡規則比照 N-5 甲案：發生略過時，正面結果不認列、負面結果照常生效。這樣靠略過不會得到好處。
   - 樣本、seed、同時到期多個 n_j 這三件事要 quant 決定，問題列在第二節。**擋 D_v。**
3. **R-Q7-5（是否鎖存）**：不採用帳內事件鎖存，改為**比對參考 run 的身分**，也就是 `(run_id, recorded_at)`。這樣不存新的狀態、不需要解除用的 CLI；時間線不一致時守衛不會自行解除，`run_id` 重號也能偵測到。這部分併入 N-20 的範圍說明。維持不擋 D_v（前提是 R-Q7-6 先落地）。建議在 D-9 實作前落檔，但不列為阻擋項。
4. **C6：確認**，對應 FL-66 (j)。**C25：更正**：FL-65 (n) 只涵蓋一部分，要補一格。
5. **風控兩則 suggested**：
   - `snapshot_stale` 的時鐘註明句已寫好；
   - Q3「部分 claim 已有、部分沒有」：用 `registered_at` 機械地分成兩種。兩次執行之間新登記的 claim，屬於前置條件不成立，只記 WARNING；其餘情形屬於步驟失敗，發 E-3d。

| 項 | 方向 | 送風控 | CEO | 擋 |
|---|---|---|---|---|
| 1 R-Q7-3 | 收緊（揭露）＋補定義 | 要（風控指定回送確認，知悉級） | 否（表數不變） | D-9（audit.py） |
| 2 R-Q3-3 | 收緊＋補定義 | 要（required 項；過渡規則增列 `cause`，要重看 LM-74） | 知悉（成本見下） | D_v |
| 3 R-Q7-5 | 收緊 | 要（N-20 批，與 ADR-0026 D-9.4 同批） | 否 | 不擋 D_v；建議 D-9 前落檔 |
| 4 C6／C25 | 不變（C6）；收緊（測試，C25） | 知悉 | 否 | D-9（驗收依據） |
| 5a 時鐘註明 | 不變（釐清） | 知悉 | 否 | D_v |
| 5b 部分 claim | 補定義 | 知悉 | 否 | D-9 |

---

## 二、各部門回報（tech-architect）

### 評估摘要

- **採用**：
  - 揭露來源移到 `forecast_gap_audit`，因為守衛期間每次稽核成功都會寫一列；
  - checkpoint「首筆寫入即判定」，加上 partial UNIQUE；
  - 以 run 身分比對取代鎖存；
  - 「部分 claim」依 `registered_at` 分類。
- **否決**：
  - 帳內事件鎖存（理由見第 3 項）；
  - 補寫被略過那天的 T snapshot（不符 PIT，而且 snapshot 不重算，D-11.2）；
  - 「部分 claim」一律當成步驟失敗（新登記 claim 是正常情形，每次都會誤推播）。

### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| R-Q7-3 甲：只加 `market_run_regression_json`（風控原案） | 改動最小 | 守衛自行解除後，該列變回 null，看不出 R 的走勢 | 低報解除後那一段 |
| **R-Q7-3 乙：再加 `market_run_now`（採用）** | 每次稽核都留下 r_now，N-20 可以據此界定受影響的期間 | 多一欄 | 低 |
| R-Q7-5 甲：不鎖存（現況） | 不存狀態 | 會自行解除；還原後 run 數很快追過參考值時，守衛根本偵測不到 | 在不一致的市場資料上寫入永久列 |
| R-Q7-5 乙：帳內事件鎖存 | 不會自行解除 | `forecast_ledger_events` 要增列 kind，還要歸類 E；要有人工解除的 CLI（人工裁量）；照樣偵測不到「重號後才第一次檢查」的情形 | 解除工具被誤用 |
| **R-Q7-5 丙：比對參考 run 身分（採用）** | 不存新狀態；只有參考 run 回來（例如依 D-9.4 整組還原）才會解除；能偵測重號 | 3 欄、1 個唯讀 reader 方法；要 data-engineer 查證 `recorded_at` | 若 `recorded_at` 精度不足以區分不同 run，會漏報 |
| R-Q3-3 甲：checkpoint 在第一筆寫入成功的 snapshot 判定，搭配略過時的過渡規則（採用） | 機械化、沒有可挑選的時點、不改 seed 與 LG-20 | 一天的停擺就可能讓正面結果延到下一個檢查點才認列 | 偏向對模型不利（保守） |
| R-Q3-3 乙：等 quant 定義「前 n_j 筆」截斷與固定 seed 後才定 | 判定和時點完全無關 | 牽涉事先宣告，定案前沒有規則 | D_v 前若沒定案就沒有規則 |

### 決策（ADR 草案）與可貼入字面

#### 1. R-Q7-3：`forecast_gap_audit` 揭露來源

**決策**：加 2 欄。守衛成立時稽核照常寫列，所以守衛期間每次成功的稽核都會留下紀錄。`market_scan_restore_suspected` 保留，作為縱深防禦。

**(1a) D-3 欄位定義**：定位字串 `` `gaps_written INTEGER NOT NULL`：本次寫入的 `forecast_gaps` 列數； ``（唯一）。在其後、`recorded_at` 之前插入：
> - （N-23 Q7；風控 R-Q7-3）`market_run_now INTEGER NOT NULL`：本次稽核讀到的市場 DB `MAX(run_id)`，也就是傳給 D-7 第 2 點「還原疑似時的共同守衛」的 r_now；一次稽核只讀一次；
> - （N-23 Q7；風控 R-Q7-3）`market_run_regression_json`：共同守衛不成立（含沒有參考值）時為 null；成立時為 `{reference_kind, reference_value, reference_id, reference_started_at}`，各鍵與 D-9.2「R 倒退」的例外屬性同義，取自同一次 `market_run_regression()` 的回傳值；

**(1b) 寫入者與時機**：定位字串 `稽核失敗、交易 rollback 時不留任何列，所以本表只記成功的稽核。`（唯一），在句末接：
> （N-23 Q7）`market_run_now` 與 `market_run_regression_json` 由同一函式依同一次守衛判定自行填入，不接受呼叫端傳入；守衛成立時本列照常寫入（D-7 第 2 點 Q7），所以守衛期間每一次成功的稽核都留下一列。

**(1c) 寫入驗證**：定位字串 `` `judged_through` 早於前一列的值時 ``（唯一）。在該子點之前、同一層插入：
> - （N-23 Q7）在本交易內依 D-9.2「R 倒退」的參考值定義重算一次：`market_run_regression_json` 非 null，若且唯若重算的參考值存在、而且 `market_run_now` 小於它；非 null 時各鍵等於重算的值；
> - （N-23 Q7）`market_run_regression_json` 非 null ⇒ 本交易沒有寫入 `kind = unobserved_weekday` 的事件；

**(1d) 讀取**：定位字串 `` `views.py`：`GET /api/forecast/status` 的 `last_gap_audit_at` ``（唯一）。在該子點末尾接：
> （N-23 Q7）`views.py` 與 API route 不讀 `market_run_now`、`market_run_regression_json`，`GET /api/forecast/status` 不回傳這兩欄（schema 測試）。

在「讀取」清單的 `validation.py` 子點末尾接：
> （N-23 Q7）§4.2「可能不完整」的揭露讀這兩欄（D-3 `forecast_correction_job` 的 `market_scan_restore_suspected` 子點）。

**(1e) L359 子點改寫（第二批，與 CEO 同意 Q7 同批）**：定位字串 `` - `market_scan_restore_suspected`：第 8 點成立時為 1 ``（唯一）。整個子點換成下文，並附〔N-23 取代：原寫「…」〕，原文由 tech-writer 逐字引入：
> - `market_scan_restore_suspected`：第 8 點成立時為 1，否則為 0，由寫入函式依同一次掃描自行填入，不接受呼叫端傳入。（N-23 Q7）第 8 點成立時，D-7 第 2 點「還原疑似時的共同守衛」必定成立，本次不啟動更正作業，所以本規則下不會產生值為 1 的列；欄位與 CHECK 保留為縱深防禦。§4.2「可能不完整」的揭露改以 D-3 `forecast_gap_audit` 為資料來源：列出 `market_run_regression_json` 非 null 的每一列（`audit_id`、`audit_now`、`market_run_now`、`reference_kind`、`reference_value`），依 `audit_id` 排序；這一欄為 1 的作業若出現（縱深防禦被觸發），另列（`correction_job_id`、`started_at`、`market_scan_from`）。缺日稽核只在成功時留列，守衛期間稽核失敗或沒有執行的時段不留任何列；共同守衛不存跨執行狀態，市場 DB 還原後新寫入的 run 使 r_now 再度不小於參考值之後，稽核列回到 null，被還原期間遺失的 run 不會因此回來；還原後新寫入、`run_id` 不大於 W 的 run，之後也不會被掃到〔推論：還原後 `run_id` 由還原檔的序號接續〕。所以這些列只是下限，不代表完整的受影響期間；§4.2 照此註明，沒有這類列時照樣註明，不得以「沒有這類列」表示市場 DB 沒有被還原。偵測結果的持久記錄與受影響 run 範圍的界定，列後續追蹤清單 N-20。

**CEO 不同意 Q7 時的備用句**：L359 原句不改，只在「§4.2「可能不完整」的揭露，列出這一欄為 1 的每一個作業（…）。」之後接：
> （N-23 Q7）另列 D-3 `forecast_gap_audit` 中 `market_run_regression_json` 非 null 的每一列（`audit_id`、`audit_now`、`market_run_now`、`reference_kind`、`reference_value`）。

**(1f) 選用，第二批**：D-3「晚到資料的觸發」第 8 點，定位字串 `§4.2 揭露該期間的作廢後補到資料筆數可能不完整`（唯一）。在「可能不完整」之後插入：
> （「該期間」以 D-3 `forecast_gap_audit.market_run_regression_json` 非 null 的稽核列界定，只是下限）

**(1g) FL 格**：
- FL-67 (n)：定位字串 `` 缺日列的 `session` 晚於 `judged_through`。 ``（唯一）。在句末接：
  > （N-23 Q7）`market_run_now` 等於該次稽核讀到的市場 DB `MAX(run_id)`（spy：一次稽核只讀一次），稽核函式簽章沒有這個參數（AST）；守衛不成立、沒有參考值 → `market_run_regression_json` 為 null；假市場 DB 的 `MAX(run_id)` 小於參考值 → 非 null，鍵恰為 `reference_kind`、`reference_value`、`reference_id`、`reference_started_at`，值等於 fixture；參考值取自 `forecast_settle_eval`、取自更正作業各一格；寫入驗證四種拒絕各一格：json 非 null 而本交易寫入了 `unobserved_weekday` 事件、json 非 null 而 `market_run_now ≥ reference_value`、json 各鍵與交易內重算不符、json 為 null 而 `market_run_now` 小於重算的參考值；§4.2「可能不完整」報表逐列列出非 null 的稽核列並帶「只是下限」的註明，沒有這類列時輸出 0 列並帶同一註明（不省略該項）；`GET /api/forecast/status` 的回傳不含這兩欄（schema 測試）。
- FL-71 (l)：定位字串 `守衛不再成立之後的第一次缺日稽核，登記完整的 [D_reg, 最新觀察日]。`（唯一）。在句前插入：
  > 守衛成立時寫入的 `forecast_gap_audit` 列，`market_run_regression_json` 非 null（細格見 FL-67 (n)）。

**表數**：不新增表，只在 `forecast_gap_audit` 加 2 欄。M-11 的「新增 17 張表」、評估摘要與 Consequences 的總表數都不改。

#### 2. R-Q3-3：checkpoint 列遇到略過的處理

**決策**：
- TA 定寫入時點、唯一性和揭露；
- 過渡規則比照 N-5 甲案，先由 ADR 規定；
- 統計面交 quant 在事先宣告 §4.5 登記，登記之前照本點處理。

**(2a) D-11 第 2 點**：定位字串 `` `UNIQUE(claim_id, computed_for_session, eval_kind)`； ``。這個字串命中兩處，以 D-11 第 2 點那一處為準；L2925 是修訂紀錄 A-5 的引文，不改。在其後、同一層插入：
> - （N-23 Q3；風控 R-Q3-3）另加 `UNIQUE(claim_id, checkpoint_n) WHERE eval_kind = 'checkpoint'`：同一檔內，每個 claim 的每個檢查點只判定一次。
> - （N-23 Q3；風控 R-Q3-3）**checkpoint 列何時寫**：
>   - 到期判定只由 `validation.py` 的單一函式 `checkpoints_due(claim_id, n, *, store) -> tuple[int, ...]` 計算（名稱暫定）：回傳該 claim 的檢查點集合（事先宣告 §4.5）中，≤ 本筆 daily 列的 `n`、而且本檔內還沒有同一 `checkpoint_n` 的 checkpoint 列的 n_j，升冪。不接受呼叫端傳入檢查點清單或判定結果（AST）。
>   - 驗證快照寫入 T 的 daily 列時，`checkpoints_due` 回傳非空，就在同一個交易內為回傳值的第一個 n_j 寫一列 checkpoint 列（`checkpoint_n = n_j`，`computed_for_session = T`）；其餘到期的 n_j 依序由之後各筆寫入成功的 daily snapshot 判定（過渡規則，見下文 quant 事項）。寫入驗證：本交易為每個 claim 寫入的 checkpoint 列，與上述規則恰好相符，不符就整個交易 rollback（D-7 第 2 點 Q3 全有或全無）。所以檢查點只在「n 達到 n_j、較小的 n_j 都已判定、而且寫入成功的第一筆 daily snapshot」判定，不能提前，也不能延到之後任何一筆。
>   - 略過：T 的快照沒有寫入（任一前置條件不成立，或交易 rollback）時，T 不留任何 checkpoint 列，之後也不補寫 T 的列；到期的 n_j 由下一筆寫入成功的 daily snapshot 判定。
>   - checkpoint 列的 `stats_json` 另記 `checkpoint_timing = {prev_daily_session, skipped_observed_sessions, n_at_eval}`，由寫入函式自行填入：`prev_daily_session` 是該 claim 在 T 之前最新一筆 daily 列的 `computed_for_session`，沒有時為 null；`skipped_observed_sessions` 是 (`prev_daily_session`, T) 之間的觀察日數（`observed_sessions(as_of=None)`），prev 為 null 時為 null；`n_at_eval` 是本筆 daily 列的 n。
>   - **過渡規則**（quant 登記前，fail-closed，比照 N-5 甲案）：`skipped_observed_sessions` ≥ 1 或為 null 的 checkpoint 列，正面結果（升為 `better_than_baseline`、重新上架）不認列，負面結果（降級、F-2 下架）照常生效。記法比照 A-28 (ii)：`suppressed_positive.cause` 增列 `snapshot_skipped`，同時成立時依 `suspended_f3` → `db_restored` → `snapshot_skipped` 取第一個。比照 A-28 (iii)：在 n＝150（族群 250）時正面結果不認列，F-2 條件二成立，不得因此延後退出期限。理由：略過只會讓判定落在之後的某一筆，過渡規則使延後不能帶來正面結果，所以略過不構成挑選判定時點的手段。
>   - 不得提供以操作者指定的 claim、n_j 或日期，寫入、延後或重判 checkpoint 列的 CLI、API 或參數（grep／AST）。
>   - §4.2 列出 `skipped_observed_sessions` ≥ 1 或為 null、或 `n_at_eval` > `checkpoint_n` 的每一列 checkpoint 列：claim、`checkpoint_n`、`n_at_eval`、`computed_for_session`、`prev_daily_session`、`skipped_observed_sessions`，以及是否依過渡規則不認列。
>   - 統計面（判定所用的樣本、seed、同一筆 snapshot 有多個 n_j 到期）由 quant 在事先宣告 §4.5 登記，D_v 之前完成；登記之前照本點處理。

**(2b) `cause` 列舉**：定位字串 `` cause ∈ {suspended_f3, db_restored}}`（`cause` 必填 ``。改為 `cause ∈ {suspended_f3, db_restored, snapshot_skipped}`。同段「同一個檢查點兩個原因同時成立時，`cause = suspended_f3`」改為「多個原因同時成立時，依 `suspended_f3` → `db_restored` → `snapshot_skipped` 取第一個」。請風控確認 LM-74 在 `cause = snapshot_skipped` 時仍屬實；理由同 `db_restored` 那一句：有效狀態不是 `better_than_baseline`，原始結果另記並在 §4.2 揭露。

**(2c) FL-71 (i)**：定位字串 `任一 claim 的 checkpoint 列寫入失敗 → 該 T 的 daily 與 checkpoint 列全部不寫。`。在句末接：
> R-Q3-3：n 在 T 跨過 30、T 的快照被略過 → T 沒有 checkpoint 列，下一筆寫入成功的 snapshot 寫 `checkpoint_n = 30` 一列，`skipped_observed_sessions = 1`，正面結果不認列、`cause = snapshot_skipped`，負面結果生效；沒有略過的對照格 → 正面認列；同一筆 snapshot 到期 30 與 60 → 只寫 30，下一筆寫 60；同一 claim 第二列 `checkpoint_n = 30` → UNIQUE 拒絕；`checkpoints_due` 不接受呼叫端清單（AST）。

**要 quant 回答的問題**（TA 意見寫在括號內）：
- **Q-a 樣本**：檢查點 n_j 的判定，是用寫入當下的全部 n(S) 筆，還是固定的「前 n_j 筆」？
  - 取前者時，延後判定會改變樣本，負面結果有被延後躲過的空間，過渡規則只擋住正面。
  - 取後者時，請定「前」的順序。TA 建議依更正鏈首列的 `outcome_id` 升冪，因為它由寫入時點決定，不隨判定時點改變。
- **Q-b 同時到期多個 n_j**：維持過渡的「一筆只判最小的一個，其餘順延」，還是改成每個 n_j 各一列？改成各一列要動 `UNIQUE(claim_id, computed_for_session, eval_kind)` 與 LG-20 的字面。不論選哪一個，F-2 的相鄰對都不得因此少一對。
- **Q-c seed**：略過之後才寫的 checkpoint 列，`eval_key` 照現行取寫入那一筆的 `computed_for_session`，還是改成與判定時點無關的值？如果要改，「`eval_kind` 不放進導出式」的原則怎麼維持？另請確認：F-2 條件一只用點估計、不用 bootstrap。
- **Q-d 過渡規則是否保留**：（TA：Q-a 取固定前 n_j 筆、Q-c 取與時點無關的 seed 時，判定就與時點無關，可以撤掉；否則保留。）
- **Q-e `m_at_eval`**：延後判定時，取寫入當下的 m。m 只會變大，所以只會更嚴。請確認。
- **Q-f「略過」的計法**：以 (prev, T) 之間的觀察日數計，prev 為 null 時視同略過。請確認或給更精確的定義。現在無法事後得知被略過那天的 n，所以 TA 採保守計法。

#### 3. R-Q7-5：是否鎖存

**決策**：不另設鎖存，也就是不新增帳內事件、狀態表或解除用 CLI。改為比對參考 run 的身分。理由：
- (i) 真正的不一致是「帳內引用的 run 已不是原來那一筆」。比對身分正好偵測這件事；R 的大小只是近似。
- (ii) 還原後若在下一次 22:10 之前，新 run 的數量就已追過參考值，只比大小完全偵測不到；比對身分偵測得到。
- (iii) 依 ADR-0026 D-9.4 整組還原時，主 DB 也一起回到備份，參考值和身分自然相符，守衛自己解除，不需要人工解除，也就沒有人工裁量。採用非標準的處理方式時，守衛永遠不解除，只能修訂本點，與「處理終點：修訂本點」一致。
- (iv) 帳內事件鎖存要增列 `forecast_ledger_events` 的 kind 並歸類 E，還需要解除工具，卻仍然解決不了 (ii)。

**N-20 範圍說明**（後續追蹤清單 N-20 列，把〔2026-10-18 擴及：…〕整個括號換成）：
> 〔2026-10-18 擴及（風控 R-Q7-5）：Q7 共同守衛不存跨執行狀態、新 run 使 R 追過參考值後自行解除，以及還原後 `run_id` 可能與遺失時間線重號。tech-architect 2026-10-18 裁定：不另設鎖存（不新增帳內事件、狀態表或解除用 CLI），改為比對參考 run 的身分：`forecast_settle_eval` 加 `market_run_max_recorded_at`、`forecast_correction_job` 加 `market_scan_to_recorded_at`，守衛成立若且唯若 r_now < 參考值，或市場 DB 中 `run_id` ＝ 參考值的 run 不存在、或其 `recorded_at` 與參考列所存的值不同；E-2 例外屬性與 `forecast_gap_audit.market_run_regression_json` 加 `regression_kind ∈ {run_regressed, reference_identity_mismatch}`、`reference_recorded_at`、`current_recorded_at`。前提待 data-engineer 查證：市場 DB run 的 `recorded_at` 只增不改，而且精度足以區分不同 run。與 devops-sre 的 ADR-0026 D-9.4 還原程序同批送風控。建議 D-9 實作前落檔，以免事後遷移；晚落時以可為 null 的欄位遷移（D-2 第 5 點），舊列只做序號比較。受影響 run 範圍的界定與 §4.2 維持不擋 D_v，前提是部署手冊「收到 E-2 立即停 scheduler」（R-Q7-6）先落地〕

N-20 落檔時，D-9.2「處理終點」一句的「新寫入的 run 使 R 再度不小於參考值時，本判定不再成立」要同批改成「新寫入的 run 使 R 再度不小於參考值、而且參考 run 的身分相符時，本判定才不再成立」。現在不改。

#### 4. C6、C25 逐格核對

- **C6 → FL-66 (j)：確認。**
  - C6 原文是「P-4 的每一格都通過」，出自 /home/user/AICompany/work/reviews/2026-10-18-未觀察平日登記範圍查核與B3回送-tech-architect.md 的約束清單。
  - P-4 以風控 B-3 回送確認改過的六格為準：原 3 格改寫，再增補 3 格（/home/user/AICompany/work/reviews/2026-10-18-B3回送N21登記範圍單項確認-風控.md 的 P-4 段）。六格在 FL-66 (j) 逐字都在：(1)～(5) 的 fixture 格、只屬於 (ii) 的日期、符合判準而在範圍外的日期、更正作業 `market_scan_to`、休市日表讀取次數、`span_sessions` 拋例外後缺日稽核照常執行。
  - 修訂紀錄的對照表改為：「C6 → FL-66 (j)（P-4 依風控 B-3 回送修訂後的六格；tech-architect 2026-10-18 已逐格核對）」，刪掉〔推論…〕和「待 TA 核對」。
- **C25 → FL-65 (n)：更正，只涵蓋一部分。**
  - C25 有三項：「U 只在 ② 讀一次；⑥ 的判定對象等於 U；`eval_set_sha256` 等於 U 的雜湊」。
  - FL-65 (n) 只用「② 與 ④ 之間注入」間接涵蓋了第一項，並斷言 `eval_set_count`。讀取次數（spy）、⑥ 的判定對象集合、`eval_set_sha256` 都沒有斷言。FL-65 的其他格也沒有。
  - 補格：定位字串 `② 之後 U 的某筆被其他寫入者寫入 outcome → 整個評估不寫入。`（唯一），在句末接：
    > （N-23 C25）`eval_set_count`、`eval_set_sha256` 等於以 ② 讀得的 U 依 D-9.2 ② 的定義重算的值（U 為空時 sha256 取空字串的值）；一次評估中讀評估集合的查詢恰好執行一次（spy）；fixture 的 U 有 3 筆、其中 1 筆在判定視圖中尚未觀察到 T+h → ⑥ 判定的對象集合恰好是這 3 筆（spy），其餘 2 筆寫入 outcome 或列入 `waiting_json`，未到期的 1 筆兩處都不出現。
  - 修訂紀錄的對照表改為：「C25 → FL-65 (n)（含 N-23 C25 補格）」。
- **FL-71 (k) 的但書**：補格和 C6 更正同批落檔時，整句刪掉「；但 C6、C25 在 tech-architect 逐格核對對照表之前，仍以 review 檔原文為驗收依據」。補格晚落時，改成「；但 C25 在 FL-65 (n) 的 N-23 C25 補格落檔之前，仍以 review 檔原文為驗收依據」。

#### 5. 風控 suggested

**(5a) `snapshot_stale` 的時鐘**：定位字串 `當晚的 snapshot 寫入成功時不成立，所以不會每晚遮蔽。`（唯一）。在該子點之後、同一層插入：
> - （N-23 Q2；風控 2026-10-18 suggested）比較用的是判定當下的 store 時鐘（D-2 第 3 點）與已存的 `late_cutoff_at`，不重算截止時間，也不由前端或 API 以其他時鐘推算。store 時鐘偏慢時，遮蔽會比 `late_cutoff_at` 晚成立，晚的長度等於時鐘的偏差；偏快時則提早成立。前者是放寬面，風控已知悉並接受；主機時鐘的準確度由 devops-sre 負責（D-7 第 9 點），不在本點範圍。

**(5b) Q3「部分 claim 已有、部分沒有」**：定位字串 `本次不寫，也不補寫缺少的部分，記 WARNING。`（唯一）。在句末接：
> 缺少 T 快照的每一個 claim，其 `registered_at` 都晚於已有 T 快照中最晚一列的 `computed_at`（兩次執行之間新登記）時，屬於前置條件不成立，不是步驟失敗：只記 WARNING，不發 ADR-0029 E-3d（本點「前置條件不成立而略過的步驟不另發告警」）。不符合這個條件時（缺少的 claim 在既有 T 快照寫入之前就已登記），表示全有或全無的交易被破壞，視為驗證快照步驟失敗：拋 `ValidationSnapshotPartialSetError`（`app/forecast/errors.py`），記 WARNING，發 E-3d（`step = validation_snapshot`）；同樣不寫、不補寫。兩種情形下，T 的 plan 若尚未寫入，都依下一子點不寫，並依 D-3 `plan_coverage_log` 記 `no_snapshot`。

D-1 表的 `errors.py` 一列：定位字串 `` 子類 `UnregisteredUnobservedWeekdayError`、`MarketRunRegressedError` ``（唯一），改為 `` 子類 `UnregisteredUnobservedWeekdayError`、`MarketRunRegressedError`、`ValidationSnapshotPartialSetError`（N-23 Q3） ``。

FL-71 (i) 再接一句：
> Q3 部分 claim：claim 在 22:10 快照寫入之後才登記、23:10 重試 → 不寫、WARNING、推播 0 則；缺少的 claim 早於既有快照登記 → `ValidationSnapshotPartialSetError`，E-3d 一則。

代價：claim 在某一 T 中途登記，而那個 T 的 plan 還沒寫時，該 T 的 plan 不寫。可計數，不靜默。

### 對實作的約束（qa-reviewer 可逐條檢查）

1. `forecast_gap_audit` 的兩欄只由 `audit.py` 的稽核函式填入，簽章沒有這兩個參數（AST）；寫入驗證四種拒絕各一格（FL-67 (n)）。
2. API／views 不回傳這兩欄（schema 測試）。
3. `checkpoints_due` 在 `app/` 內恰好一個定義，只由驗證快照寫入路徑呼叫（AST）；partial UNIQUE 存在（schema 測試）。
4. 沒有任何以操作者指定的 claim、n_j 或日期寫入、延後、重判 checkpoint 的 CLI／API／參數（grep／AST）。
5. `ValidationSnapshotPartialSetError` 是 `ForecastFailClosedError` 的子類，只在驗證快照步驟拋出（AST）。
6. 禁止：新增鎖存用的帳內事件 kind、狀態表、狀態檔，或解除守衛的 CLI。

---

## 三、驗證

- **讀過的檔案**：
  - 風控審查全文；我的 N-23 提案全文；
  - 後續追蹤清單 N-20 列；
  - dev-lead 盤點中 checkpoint【未查證】一段；
  - TA B-3 回送（C1～C8、P-4）；風控 B-3 回送 P-4 段；
  - TA C-22／N-21 提案 L515～L546（C21～C27）；
  - 事先宣告 §4.5 L1035～L1069。
- **ADR-0027 讀過的段落**（工作樹）：
  - D-2；D-3 L320～L369、L405～L466、L630～L711；
  - D-7 L768～L907（含已套用的第一批 N-23 字面）；
  - D-9 L1062～L1110；D-10；D-11 第 2 點；
  - `snapshot_stale` 各處；FL-64～FL-67；FL-71 全條；修訂紀錄的 C 號對照表。
- **定位字串**：用 Grep `-o` 驗過，除下一點外都各自唯一。
  - `` `UNIQUE(claim_id, computed_for_session, eval_kind)`； `` 命中兩處（D-11 第 2 點，以及修訂紀錄 A-5 的引文）。
  - tech-writer 正在套用，行號一直在漂移（例如 FL-64 (g) 從 L2245 移到 L2258），請一律以字串定位。
- **查證結果**：
  - ADR 和事先宣告都沒有「checkpoint 列何時寫入」的定義（grep `checkpoint`、`檢查點` 加上「格點／觸發／達到／跨過」），和 dev-lead、風控的未查證記載一致；
  - `forecast_claim_registry` 有 `registered_at`，而且只增（D-10.3）。
- **未查證**：
  - 市場 DB run 的 `recorded_at` 是否只增不改、精度是否足以區分不同 run（交 data-engineer）；
  - F-2 條件一是否完全不用 bootstrap（交 quant，Q-c）；
  - 個股 claim 的 n 一天能增加多少（影響 Q-b 的發生頻率）；
  - 「還原後 `run_id` 接續還原檔序號」仍然只是推論。
- **沒做的事**：沒有改任何檔案，沒有跑 git 或程式，沒有讀 `.env`，沒有碰 `*.db`，沒有指定任何套件版本。

---

## 四、下一步

1. **風控**：
   - 確認 R-Q7-3 字面 (1a)～(1g)，說明 `market_run_now` 偏離原案的理由；
   - 審 R-Q3-3 的機械規則與過渡規則（含 `cause` 增列與 LM-74）；
   - 知悉 R-Q7-5 的裁定、C25 更正、5a、5b。
2. **quant**：回答 Q-a～Q-f，在事先宣告 §4.5 登記（擋 D_v）。
3. **data-engineer**：查證 run 的 `recorded_at` 只增不改、以及精度（N-20 前提）。
4. **devops-sre**：N-20 的身分比對與 ADR-0026 D-9.4 還原程序同批起草。
5. **tech-writer**（風控確認後）：
   - 現在可以套用：(1a)～(1d)、(1g)、C25 補格與 C6 對照表更正、(k) 但書、5a、5b；
   - 第二批才套用：(1e)、(1f)；
   - quant 登記前也可以套用（風控核可後）：(2a)～(2c)。
6. **coordinator**：
   - N-20 列換成上面的範圍說明；
   - 追蹤清單「TA 與 quant 的 checkpoint 略過規則」一項，註記 TA 部分已提案、等 quant Q-a～Q-f；
   - 機械核對：落檔後 `C6、C25 在 tech-architect` 為 0 筆。
7. **CEO**：知悉 R-Q3-3 的成本：一個觀察日的快照失敗，若剛好遇上檢查點，正面結果就要延到下一個檢查點才認列；遇上 n＝150（族群 250）時，會依退出期限下架。

**相關檔案**：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-18-N23維運告警與Q1至Q9審查-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-N23維運告警與Q1至Q9裁定提案-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-18-未觀察平日登記範圍查核與B3回送-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-18-B3回送N21登記範圍單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-C22存放表與N21更正作業視圖及N22至N24提案-tech-architect.md
- /home/user/AICompany/work/stock-desk-N23排程器結算失敗行為盤點-2026-10-18.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

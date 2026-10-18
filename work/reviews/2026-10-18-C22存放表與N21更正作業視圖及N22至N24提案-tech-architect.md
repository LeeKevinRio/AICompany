# C-22 存放表、N-21 更正作業判定視圖、N-22～N-24 提案（tech-architect）

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 提案：C-22 存放表、N-21 更正作業判定視圖、N-22 查證、風控 suggested 兩項、N-23／N-24（同一包送風控）

## 一、本次結論

六項我都提了可以直接貼入的條文，整包送風控。沒有否決既有決策。CEO 要知悉一項：表數 17→18。另有兩項的面向使用者部分要經 PM／風控（第 5 項 (b)、(f)），其餘不需要 CEO 明示同意。

1. **C-22 存放表：新增一張表 `forecast_index_check`。** 偵測、查證、確認判定三種列共用一個 AUTOINCREMENT 序號，所以 V＝`MAX(check_id)`，`forecast_settle_eval.index_check_max` 這個單一欄位不用改。
   - X2 的判定紀錄照舊是 `x2_confirmed_non_session`，A-77 第 7 項不變；本表只收 X2 待查證的查證列。
   - 表數 17→18，M-11 12→13。
2. **N-21 剩餘部分：更正作業的判定視圖比照 D-9.2，但大盤自己存快照，不沿用 `forecast_settle_eval` 的快照。**
   - 不能沿用的原因：結算快照的起點是「未結算預測的 T 最小值」，更正作業重查的是已結算的舊列，不在範圍內。
   - 快照範圍取 [D_reg, 作業開始當日]，不強制重抓；E、V、休市日表各讀一次並存下。
   - `forecast_correction_job` 新增 9 欄。
   - 查核時另外發現一個缺口：X2 事件與確認判定類的觸發沒有啟動者，現在只有市場 DB 掃描會啟動更正作業。一併補上。
3. **N-22：沒有程式。** `app/forecast/` 不存在；`span_sessions`、`run_settlement_evaluation`、`forecast_replay` 在 `apps/` 下零命中。
   - 依字面，重放沒有理由呼叫 `span_sessions`：它只在 `split_or_reduction_suspected` 裡算 g，而這一值不套用於 `^TWII`。但字面沒有禁止呼叫；D-9.3 的「五個值全部評估、不短路」反而可能被讀成連大盤也要評估。這裡要補禁止句。
   - **另一個發現涉及事先宣告字面（屬推論）：** §4.7 規定重放「X1、X2、X4 照用」，而 X2 的 (iii) 依賴市場 DB 的 D-8.1 (i)。重放期早於市場 DB 的涵蓋範圍（ADR-0012 C-10 不回填），重放期的每一天都會觸發 X2 (iii)。依 N-22 的規則，這部分要改成 dirdef 凍結前的阻擋項，交 quant。
4. **風控 suggested 兩項：**
   - (i) 兩個集合**照現行字面不一定相同**。改成在 ② 讀一次評估集合 U，⑥ 只判定 U，② 之後才寫入的紀錄留給下一次評估。U 為空時另定範圍。
   - (ii) recorder **不屬於**「登記先於使用」的作業。另外發現 P-2 的交集寫法會讓「X2 確認寫入」的登記範圍變成空集合，要明文釐清。
5. **N-23 (a)～(e)：**
   - (a) 要求缺日稽核也成功；(b) 略過，不寫 fail-closed 列；(c) 比照失敗處理。
   - (d) C17 寫進 D-7 第 2 點。C11～C20 併入約束清單，其中 C20 要修改。
   - (e) 採方案 A，D-7.1 不必修訂。不加「剩餘時間檢查」；listener 寫進 ADR，告警規格交 devops-sre。
   - 另外，D-7.2 的五步順序裡沒有更正作業，我補了它的位置。
6. **N-24：** 缺日稽核對觀察日 S，要等到 S 的 `late_cutoff_at` 過了才判定。這是補定義（兩面）。

## 二、各部門回報（tech-architect）

**共通說明**
- 行號是目前工作樹的狀態，請以定位字串為準。
- 標「唯一」的定位字串，我都用 Grep `-o` 確認全檔只命中一次。
- 「被取代原文」寫「無」，表示這一條是插入。

---

### 第 1 項：C-22 存放表

#### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **甲（建議）：單一表 `forecast_index_check`，三種列共用一個序號** | V 只有一個數，`index_check_max` 不改；qa 可以用相鄰兩次評估的 V 區間核對「查證程序」② 的涵蓋 | 欄位依列種而稀疏，CHECK 較多 | 低；靠 BEFORE INSERT trigger 與寫入函式驗證 |
| 乙：偵測登記表＋查證／判定表，兩張 | 欄位較乾淨 | 表數 +2 | 待查證集合要跨表查詢 |
| 丙：三張表，V 改成兩欄以上 | 每張表語意單一 | 要改 `forecast_settle_eval` 已核可的 schema，表數 +3 | 多一個序號，容易漏比 |
| 丁：併入 `forecast_ledger_events` 的新 kind | 不加表 | 每日重查量大，會灌爆事件表；要動 `E_CHANGING`／`NEUTRAL` 的歸類與 C9-7 遮蔽 | 耦合 C9-7，**否決** |

#### C22-1（D-3 新表）
- **定位字串（唯一，L412）：** `` - `forecast_replay`：結構與 `forecast_record` 相同，另加 `freeze_commit`、`replay_session`。永遠不與前瞻紀錄合併。 ``
- **動作：** 插在這一行之前。
- **被取代原文：** 無。
- **字面：**

> - **`forecast_index_check`**（C-22；tech-architect 2026-10-18，與 N-21 同批）：事先宣告 §6.3「大盤指數序列」的偵測紀錄、「查證程序」的查證紀錄，以及 X1、X3、X4 的確認判定紀錄，存在同一張表、共用一個序號。只增不改（D-2 第 2 點）。D-9.2 的 V（`forecast_settle_eval.index_check_max`）與 D-9 第 5 點的 `forecast_correction_job.index_check_max` 都是本表的 `MAX(check_id)`，沒有列時為 0。X2 的判定紀錄仍是 `x2_confirmed_non_session`（A-77 第 7 項），不寫入本表。
>   - **共通欄位**：`check_id INTEGER PRIMARY KEY AUTOINCREMENT`；`entry_kind ∈ {detection, verification, determination}`；`detection_id`（detection 列為 null；其餘列必須指向同表 `entry_kind = detection` 的列）；`session_date`（受檢 bar 的交易日；非 detection 列必須等於所指 detection 列的值）；`written_by ∈ {recorder, settle_eval}`；`recorded_at`（store 時鐘）。以下各組欄位只在對應的 `entry_kind` 非 null，其餘列必須為 null：
>     - **detection**：
>       - `check_item ∈ {x1_close_unusable, x1_close_involved, x1_non_close, x2_pending, x3, x4}`；
>       - `x2_case ∈ {set_iii_only, conflict}`（只限 `x2_pending`；conflict 指 A-77 第 5 項的證據矛盾）；
>       - `checked_bars_json`：受檢 bar 的完整列，每列帶 OHLC、`source`、`as_of`、`fetched_at`；X3 為兩次擷取的同日列，X4 為相鄰兩日的列；
>       - `checked_values_sha256`：只對各列的 (`session_date`, `source`, OHLC) 做正規化後的 sha256，不含 `as_of`、`fetched_at`（快取每次覆寫這兩欄，D-9.2）。
>     - **verification**：
>       - `query_point ∈ {on_detection, daily_recheck, source_onboarding}`（事先宣告 §6.3「查證程序」①～③）；
>       - `queried_at`（查詢前的 store 時鐘）；
>       - `source_name`、`source_version`：`result = source_not_connected` 時兩者為 null，其餘必須非 null；
>       - `result ∈ {value_obtained, source_has_no_day, query_failed, source_not_connected}`；
>       - `source_values_json`、`comparison_json`：只在 `value_obtained` 時非 null，內容是獨立來源的值、官方公布位數，以及逐欄四捨五入後是否相等。
>     - **determination**：
>       - `determination ∈ {close_erroneous, non_close_erroneous, no_error, correct_close_obtained}`；
>       - `basis ∈ {direct, verified}`；
>       - `basis_check_id`：`verified` 時指向同一個 detection、`result = value_obtained` 的查證列；`direct` 時為 null；
>       - `target_bar_json`：判定對象那一根 bar 的列，必須是所指 detection 的 `checked_bars_json` 其中一列；`correct_close_obtained` 另帶取自 `basis_check_id` 的正確收盤。
>   - **唯一性**：
>     - `UNIQUE(session_date, check_item, checked_values_sha256) WHERE entry_kind = 'detection'`：同值的 bar、同一個偵測項只登記一次。來源改寫使數值不同時，視為新的偵測。
>     - `UNIQUE(detection_id, determination) WHERE entry_kind = 'determination'`。
>   - **與事先宣告 §6.3 的對應**：
>
>     | §6.3 情形 | detection | verification | determination |
>     |---|---|---|---|
>     | X1 收盤本身不可用（三種） | `x1_close_unusable` | 不查 | `close_erroneous`、`direct`，與 detection 同一交易 |
>     | X1 不一致而牽涉收盤 | `x1_close_involved` | ①～③ | 收盤不符 → `close_erroneous`，同一交易另寫 `correct_close_obtained`（獨立來源值即正確值）；只有非收盤不符 → `non_close_erroneous`；全部相符 → `no_error`；都是 `verified` |
>     | X1 其餘（只限非收盤欄位） | `x1_non_close` | 不查 | `non_close_erroneous`、`direct` |
>     | X2 只有 (iii) | `x2_pending`、`set_iii_only` | ①～③ | 來源沒有這一天 → 不寫 determination，改寫 `x2_confirmed_non_session`（`basis = verified`，`verification_ref` ＝ 該查證列）；來源有 d → `no_error` |
>     | X2 證據矛盾（A-77 第 5 項） | `x2_pending`、`conflict` | ①～③ 照跑 | 一律不寫 |
>     | X2 直接確認 | 不寫本表 | — | `x2_confirmed_non_session`、`basis = direct`（不變） |
>     | X3、X4 | `x3`、`x4` | ①～③ | 同「X1 不一致而牽涉收盤」 |
>
>   - **待查證集合**：`check_item ∈ {x1_close_involved, x2_pending, x3, x4}` 的 detection 列，同時符合以下兩項：
>     - 沒有 `close_erroneous`、`non_close_erroneous` 或 `no_error` 的 determination；
>     - `x2_pending` 另外沒有 `verification_ref` 指向其查證列的 `x2_confirmed_non_session` 事件。
>
>     `conflict` 列永遠在集合內。
>   - **寫入者與時機**（各自一個交易：detection、該次 ① 查證，以及由它導出的 determination 同一交易）：
>     - **recorder**：大盤 claim 記錄所用的每一根 `^TWII` bar（特徵窗與 T 日），比對偵測項；有觸發而且身分尚未登記時，寫 detection 與 ①（`direct` 項寫 determination）。
>     - **`run_settlement_evaluation()` 的 D-9.2 ③**：
>       - 快照內每一根 bar，處理同上；
>       - 獨立來源已接入時（dirdef 外的 ADR 常數 `INDEX_VERIFICATION_SOURCE` 非 None），對當時全部待查證列各做一次 ②；
>       - 該常數的 `version` 還沒有出現在任何 `source_onboarding` 列時，對全部待查證列做一次 ③，取代當次的 ②。
>       - 都在 ④ 讀 V 之前完成。
>     - 其他任何程式路徑（API、CLI、更正作業、重放、缺日稽核）都不得寫入本表（AST 列舉呼叫點）。查不查、先查哪一筆，都不得依預測、標籤或結果決定。
>   - **判定時怎麼讀**（D-9.2 ⑥、D-9 第 5 點 ④）：
>     - 只讀 `check_id ≤` 視圖的 `index_check_max` 的列。
>     - 判定用到的大盤 bar（P(T)、P(T+h) 收盤，以及窗內 bar 的診斷欄位），依 (`session_date`, `source`, OHLC) 與 `target_bar_json` 比對，套用相符的 determination：
>       - `close_erroneous` 而沒有 `correct_close_obtained` → 該收盤確認有誤、尚未取得正確值；
>       - 有 `correct_close_obtained` → 用其正確收盤，結算列記明來源；
>       - `non_close_erroneous` → 只影響診斷欄位。
>     - 沒有 determination 的待查證 bar 照原值計分。
>   - **寫入驗證**（寫入函式加 BEFORE INSERT trigger；任一項不成立就拒絕寫入）：
>     - 各組欄位的 null 與非 null 規則依上文。
>     - `basis = direct` ⇔ 所指 detection 的 `check_item ∈ {x1_close_unusable, x1_non_close}`；兩者的 determination 分別只能是 `close_erroneous`、`non_close_erroneous`。
>     - `no_error` 與 `close_erroneous`、`non_close_erroneous` 對同一個 detection 互斥。
>     - `correct_close_obtained` 必須已有同一 detection 的 `close_erroneous`，而且 `basis = verified`。
>     - `x2_pending` 只能有 `no_error`，而且只限 `x2_case = set_iii_only`，寫入時重算 d ∉ D-8.1 (i)；`conflict` 寫任何 determination 都拒絕（A-77 第 5 項）。
>   - **用語綁定**：本 ADR 其他位置的「查證紀錄」「查證紀錄 ID」「查證紀錄的參照」，指本表 `entry_kind = verification` 的列與它的 `check_id`。「確認判定紀錄」「收盤更正的查證紀錄」指 `entry_kind = determination` 的列。X2 依 A-77 第 7 項。
>   - **用途限制**：
>     - 不屬於 `E_CHANGING_EVENTS`。
>     - `views`、API route 與匯出不得讀它；只有 `scoring.py` 的判定、`validation.py` 的 §4.2 報表（查證紀錄依 `result` 分列筆數、異常待查證數）與稽核工具可以讀它（AST）。
>   - **重放**：不寫本表（D-9 第 7 點）。

- **方向：** 補定義（收緊）。
- **送風控：要。** 這張表是「查證程序」與「確認有誤」的落地，風控 v0.14 單項確認第 14 項指明「TA 定案時送我」。
- **CEO：** 只需知悉表數（見 C22-6）。

#### C22-2（D-9.2 V 的定義）
- **定位字串（唯一，L743）：** `- V ＝ 查證紀錄與 X1、X3、X4 確認判定紀錄的序號上限。`
- **被取代原文：** 這一整行。
- **字面：**
  > - V ＝ `forecast_index_check` 的 `MAX(check_id)`；查證紀錄與 X1、X3、X4 確認判定紀錄共用這個序號（D-3，C-22）。
- **方向：** 不變（指向）。

#### C22-3（D-9.2 存放表待決句）
- **定位字串（唯一，L745）：** `查證紀錄與確認判定紀錄的存放表，本 ADR 尚未定義（待決事項 tech-architect 段；D-9 結算程式實作前定案）。`
- **被取代原文：** 該行整行（含其後「不論存在哪裡……否則本點的 V 不成立。」）。
- **字面：**
  > - 查證紀錄與確認判定紀錄存於主 DB 的 `forecast_index_check`（D-3；只增不改、以 `INTEGER PRIMARY KEY AUTOINCREMENT` 為序號；C-22 於 2026-10-18 定案）。③ 寫入的列都早於 ④ 讀 V，所以本次評估當場的查證與判定都在判定視圖內。
- **方向：** 不變（定案指向）。

#### C22-4（D-9.2 ③）
- **定位字串（唯一，L753）：** `查證紀錄與 X2 確認照既有規則寫入，各自一個交易。`
- **動作：** 在這一句之後接上。
- **字面：**
  > 寫入規則依 D-3 `forecast_index_check`：快照內每根 bar 的偵測與 ① 查證；獨立來源已接入時，對全部待查證列做 ②；來源版本第一次出現時，以 ③ 取代當次的 ②。
- **方向：** 補定義（收緊）。

#### C22-5（A-77 第 7 項 `verification_ref` 綁定）
- **定位字串（唯一，L640）：** `` - 判定時間就是事件的 `recorded_at`，不另設欄位。 ``
- **動作：** 在這一行之後、同一層插入。
- **字面：**
  > - （C-22）`verification_ref` 是 `forecast_index_check.check_id`。所指的列必須是 `entry_kind = verification`、`result = source_has_no_day`，它的 detection 列 `check_item = x2_pending`、`x2_case = set_iii_only`、`session_date = d`；不成立就拒絕寫入（FL-19 (c)③ 加格）。
- **方向：** 補定義（收緊）。
- **送風控：** 要。

#### C22-6（表數連帶）

| 位置 | 定位字串（都唯一） | 被取代原文 | 新字 |
|---|---|---|---|
| L89 | `- 表數多（17 張），寫入規則有一部分在 trigger 裡。` | 整行 | 「17 張」改「18 張」 |
| L202 | `新增 12 張表（第九、十批加` | 該格 | 「新增 12 張表」改「新增 13 張表」；在 `` `forecast_settle_eval` `` 之後加「；C-22 加 `forecast_index_check`」 |
| L1622 | `- 17 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。` | 整行 | 「17 張」改「18 張」 |
| L2210 之後 | `12. （v0.14，知悉）M-11 的表數隨` | 無（插入） | `13. （C-22，知悉）M-11 的表數隨 forecast_index_check 由 12 張改為 13 張，全部表數由 17 張改為 18 張。` |

- **方向：** 不變（CEO 知悉，單獨一點，比照風控 B-7）。

#### C22-7（待決事項 L2269）
- **定位字串（唯一）：** `X1、X3、X4 確認判定紀錄的存放表`
- **動作：** 在該列句末加：
  > 〔已決：`forecast_index_check`，見 D-3（C-22，tech-architect 2026-10-18；風控待確認）〕
- **方向：** 不變。

---

### 第 2 項：N-21 剩餘部分，更正作業的判定視圖

#### 方案比較（大盤 bar）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 甲：沿用某次 `forecast_settle_eval` 的快照 | 不新增擷取 | 該快照範圍是 [未結算 T 最小值, 當日]，**不涵蓋已結算的舊窗**；X2 順延後的新 T+h 也可能不在範圍內 | 舊窗沒有 (ii) 與收盤可用，重算失真 |
| 乙：只取被 supersede 列當時的評估快照，再疊加修正 | 重算最貼近原判 | 每列各自一份快照，視圖變成多份；順延日期不在舊快照裡 | 複雜，難以逐位重算 |
| **丙（建議）：本作業自存快照，範圍 [D_reg, 作業開始當日]，不強制重抓** | 單一視圖、可存可重算；登記範圍與缺日稽核相同，不必另取交集 | 快照隨紀錄期增長（約每年 250 列） | 更正作業罕見，成本可接受〔推論，未量測〕 |

#### N21-1（`forecast_correction_job` 欄位）
- **定位字串（唯一，L344）：** `market_scan_restore_suspected INTEGER NOT NULL CHECK (market_scan_restore_suspected IN (0,1)), started_at)`
- **被取代原文：** 同定位字串。
- **字面：**
  > `market_scan_restore_suspected INTEGER NOT NULL CHECK (market_scan_restore_suspected IN (0,1)), ledger_event_from INTEGER NOT NULL, ledger_event_max INTEGER NOT NULL, index_check_from INTEGER NOT NULL, index_check_max INTEGER NOT NULL, index_series_sha256 NOT NULL, index_final_now NOT NULL, holiday_table_json, view_range_json, observed_sessions_json, started_at)`
- **方向：** 補定義（收緊）。

#### N21-2（欄位說明子點）
- **定位字串（唯一，L350）：** `` 不放 `triggers_json`（它是觸發陣列，不是標頭） ``
- **動作：** 在該子點之前、同一層插入。
- **字面：**
  > - （N-21；tech-architect 2026-10-18）**判定視圖欄位**：作業開始時與 `triggers_json` 在同一個交易內寫入，由寫入函式自行填入，不接受呼叫端傳入；取得方式見 D-9 第 5 點「更正作業的判定視圖」。
  >   - `ledger_event_from`、`index_check_from` ＝ `correction_job_id` 最大、而且已有 `forecast_correction_job_end` 列的作業的 `ledger_event_max`、`index_check_max`；沒有這樣的作業時為 0（比照 `market_scan_from`）。
  >   - `ledger_event_max`（E）、`index_check_max`（V）＝ 本作業在開始交易內完成未觀察平日登記之後，讀到的 `forecast_ledger_events` 的 `MAX(event_id)` 與 `forecast_index_check` 的 `MAX(check_id)`。
  >   - `index_series_sha256`、`index_final_now`、`holiday_table_json`、`view_range_json`、`observed_sessions_json`：與 `forecast_settle_eval` 的同名欄位同義，界定本作業的大盤快照、休市日表、範圍與觀察日。
  >   - **寫入驗證**：兩個 from 等於上述值；`from ≤ max`；`index_series_sha256` 指向 `series_kind = index_bars` 的既有列。寫入 job_end 時再驗證一次兩個 from 仍等於當下的值；不成立就拒絕寫入 job_end，記 WARNING（比照「晚到資料的觸發」第 5 點）。
- **方向：** 補定義（收緊）。

#### N21-3（D-9 第 5 點：判定視圖本文）
- **定位字串（唯一，L822）：** `` - 有變的筆新增一列並填 `supersedes_id`；結算端改用最新一筆，預測端永遠用原始那一筆。 ``
- **動作：** 在這一行之後、同一層插入。
- **字面：**
  > - **更正作業的判定視圖**（N-21；tech-architect 2026-10-18，比照 D-9.2）：更正作業由 `app/forecast/correction.py` 的單一函式 `run_correction_job()` 執行。重算所讀的一切資料，以本作業的判定視圖為準；界定值存在 `forecast_correction_job`（D-3）。以存下的視圖重算，結果必須逐位相同。執行順序（不得調換）：
  >   ① 依 D-3「晚到資料的觸發」第 2 點掃描，取得 `market_scan_to`。之後不再讀市場 DB 的 `MAX(run_id)`。
  >   ② 以 `ledger_registration_start()` 唯讀導出 D_reg，讀時鐘與大盤列一次，建立本作業的大盤快照：
  >     - 範圍 ＝ [D_reg, 作業開始當日（Asia/Taipei）]，記入 `view_range_json`；
  >     - 只留 `is_final_bar(row, now=…)` 為真的列，寫入 `forecast_input_series`（`series_kind = index_bars`，以內容雜湊去重）；`content_sha256` 記入 `index_series_sha256`，`now` 記入 `index_final_now`；
  >     - 不強制重抓：D-9.2 的強制重抓只屬於結算評估；
  >     - 同一步讀官方休市日表一次（`official_holiday_table_meta` 一次，`official_holidays` 每個涉及的年度各一次；未接入時為 null），meta 記入 `holiday_table_json`；
  >     - 之後本作業不再讀大盤列與休市日表。
  >   ③ 開啟主 DB 寫入交易，依序：
  >     - 重新導出 D_reg；早於 `view_range_json.start` 時不寫入，記 WARNING；
  >     - 依 A-77 第 10 項，以 `market_scan_to` 界定的 (i)、本作業的大盤快照，以及 ② 的休市日表，完成 [D_reg, 最新觀察日] 內的未觀察平日登記；
  >     - 讀 E、V；
  >     - 依 D-11.4 第 11 點 (h)「原因怎麼歸屬」讀入觸發；
  >     - 寫入 `forecast_correction_job`（含 `observed_sessions_json`）；commit。
  >   ④ 重算：
  >     - (i) 只取 `run_id ≤ market_scan_to` 的 run；(ii) 只取本作業的大盤快照；
  >     - X2 確認日與未觀察平日只取 `event_id ≤ ledger_event_max`；確認判定紀錄只取 `check_id ≤ index_check_max`；
  >     - `span_sessions` 使用 ② 的休市日表；
  >     - 之後不再讀 `MAX(event_id)`、`MAX(check_id)`。
  >   - **理由**：
  >     - 重查的是已結算的舊預測，T 可能早於任何一次結算評估的快照範圍，所以不沿用 `forecast_settle_eval` 的快照。
  >     - 範圍取 [D_reg, 作業開始當日]，與缺日稽核的登記範圍相同。
  >     - 不強制重抓：同一次執行的結算評估已處理它自己快照範圍內的缺漏；較早日期的列若已不是定案列，重算結果和前一列不同時，依 R10-2 的差異驗證拒絕寫入、計入 `rejected_count`，不以重抓改變結果。
- **方向：** 補定義（收緊）。
- **送風控：要。** 這一條定義 `index_bar_confirmed_erroneous` 結算後路徑與 X2 順延重算的資料來源。

#### N21-4（啟動者缺口）
- **定位字串（唯一，L379）：** `掃描有命中時，以命中項為觸發啟動更正作業`
- **被取代原文：** `掃描有命中時，以命中項為觸發啟動更正作業；沒有命中時不啟動（D-3「`triggers_json` 必須非空」不變）。`
- **字面：**
  > 掃描有命中時，以命中項為觸發啟動更正作業。同一步另以唯讀查詢檢查兩件事，有任一項就同樣啟動（N-21）：
  > - (W_E, `MAX(event_id)`] 內有沒有 `x2_confirmed_non_session` 事件；
  > - (W_V, `MAX(check_id)`] 內有沒有 `determination ∈ {close_erroneous, non_close_erroneous, correct_close_obtained}` 的確認判定列。
  >
  > W_E、W_V 是最近一個已有 job_end 列的作業的 `ledger_event_max`、`index_check_max`，首次為 0。三類都沒有時不啟動（D-3「`triggers_json` 必須非空」不變）。
- **理由：** 現行字面只有市場 DB 掃描會啟動更正作業。X2 確認在結算之後才寫入（例如 recorder 對特徵窗的確認），或收盤經查證確認有誤時，沒有任何東西會啟動作業，§6.4 規定的 supersede 就不會發生。這和風控 R-11 指出的「沒有起動者」是同一類缺口。
- **方向：** 補定義（收緊）。
- **送風控：** 要。

#### N21-5（觸發的序號界定）
- **定位字串（唯一，L1284）：** `更正作業把啟動當下所有還沒處理的觸發一次讀入`
- **動作：** 在該子點的〔N-17…〕註之後接上。
- **字面：**
  > （N-21）「還沒處理」以序號界定：
  > - `x2_confirmed_non_session` 事件取 `event_id` ∈ (`ledger_event_from`, `ledger_event_max`]；
  > - 確認判定紀錄取 `forecast_index_check` 中 `check_id` ∈ (`index_check_from`, `index_check_max`]、`determination ∈ {close_erroneous, non_close_erroneous, correct_close_obtained}` 的列；`target_bar_json.session_date` 是 T 或 T+h 的收盤類歸 `settlement_close_corrected`，其餘歸 `window_bar_corrected`；
  > - 來源修訂依 D-3「晚到資料的觸發」。
  >
  > 中斷作業不使 from 前進，它的觸發由下一個作業重新讀得。
- **方向：** 補定義（收緊）。

#### N21-6（`forecast_void_late_diag` 的視圖）
- **定位字串（唯一，L366）：** `` 本作業的 `market_scan_to`；其餘依 D-9.2 的 PIT 規則 ``
- **動作：** 在「`market_scan_to`；」與「其餘依」之間插入。
- **字面：**
  > 大盤 bar、X2 確認日、未觀察平日、確認判定紀錄與官方休市日表，依本作業的判定視圖（D-9 第 5 點「更正作業的判定視圖」）；
- **方向：** 補定義（收緊）。

#### N21-7（D-1 模組表）
- **定位字串（唯一，L241）：** `` | `app/forecast/audit.py` | 缺日稽核 | ``
- **動作：** 在這一列之後插入一列。
- **字面：**
  > | `app/forecast/correction.py`（N-21） | 更正作業唯一的寫入端：`run_correction_job(*, store, market_reader, index_service, clock)`。依 D-9 第 5 點建立並存下判定視圖，呼叫 `scoring.py` 的同一套純函式重算，寫入 supersede 列、`forecast_void_late_diag` 與 `forecast_correction_job_end`。簽章不接受觸發、視圖、E、V 或重算結果；`forecast_outcome` 的 supersede 寫入只能從這個函式呼叫（AST） |
- **方向：** 不變（模組歸屬）。

#### N21-8（`observed_sessions(*, view)` 的視圖種類）
- **定位字串（唯一，L244）：** `` `view` 是 D-9.2 的判定視圖； ``
- **被取代原文：** 同定位字串。
- **字面：**
  > `view` 是 D-9.2 的判定視圖，或 D-9 第 5 點更正作業的判定視圖（`market_run_max` 取 `market_scan_to`，其餘取 `forecast_correction_job` 的同名欄位）；判定視圖只由 `settlement.py` 與 `correction.py` 建立；
- **方向：** 補定義（收緊）。

#### N21-9（FL-68，新增）
- **定位字串（唯一，L1881）：** `- **FL-24**：預測端計分永遠使用原始列。`
- **動作：** 插在這一行之前（FL-67 之後）。
- **字面：**
  > - **FL-68**（N-21；D-9 第 5 點、D-3 `forecast_correction_job`）：
  >   - (a) 以存下的 `forecast_correction_job` 重算，supersede 列與 `forecast_void_late_diag` 列逐位相同；作業開始之後注入 `run_id > market_scan_to` 的 run、`event_id > ledger_event_max` 的事件、`check_id > index_check_max` 的判定列，或覆寫 `price_bars_cache` 的大盤列 → 結果不變。
  >   - (b) 一次作業中，`MAX(run_id)`、`MAX(event_id)`、`MAX(check_id)`、大盤列、`official_holiday_table_meta` 各恰好讀一次（spy）；不強制重抓。
  >   - (c) `view_range_json.start` 等於 D_reg；結算窗早於最近一次結算評估快照起點的舊預測，仍能以本作業快照重算。
  >   - (d) 只有 X2 事件觸發（沒有市場 DB 命中）→ 作業啟動；只有確認判定列觸發 → 作業啟動；`no_error` 判定列 → 不啟動。
  >   - (e) 中斷作業之後的下一個作業，兩個 from 等於前一個已完成作業的 max，重新讀得同一批觸發；性質測試：已完成作業的 (from, max] 首尾相接、不重疊（三種序號各一）。
  >   - (f) 簽章沒有觸發、視圖、E、V 參數（AST）；supersede 寫入只從 `run_correction_job()` 呼叫。
- **方向：** 收緊（測試）。

---

### 第 3 項：N-22 查證與提案

#### 查證結果
- **程式：** 沒有程式可查。
  - Glob `apps/stock-desk/backend/app/forecast/**` 零命中。
  - Grep `span_sessions|run_settlement_evaluation|observed_sessions|unobserved_weekday|forecast_replay` 在 `apps/` 下只有 `tests/test_diagnose.py:168` 一處，是無關的函式名。
  - `replay` 的命中都屬於 playbook、sector T9、backtest，和預測帳無關。
- **ADR 字面：**
  - `span_sessions` 只定義在 D-9.3 `split_or_reduction_suspected` 的 g_j（L775）。
  - 這一值不套用於大盤指數序列（L795；FL-66 (h) L1861，但只斷言 `split_suspect_exceeds` 不被呼叫，**沒有斷言 `span_sessions` 不被呼叫**）。
  - D-9.3 L808 寫「五個值全部評估、不短路」，可能被讀成大盤也要評估分割，因而呼叫 `span_sessions`。
  - ADR 沒有任何重放結算的條文：`forecast_replay` 只在 L412 有結構定義，D-1 沒有對應模組，D-9 也沒有重放的判定視圖。
- **事先宣告字面：**
  - v1 重放只做大盤（§4.7 L1015）；重放不套用分割門檻（§4.7 L1030）。所以依字面，重放用不到 g。
  - **另外發現【推論】：** §4.7 L1030 規定「X1、X2、X4 照用」，§6.3 X2 (iii)（L1273）以 D-8.1 (i)（市場 DB 有定案 run 的 session）為準。重放期在市場 DB 的涵蓋之前（ADR-0012 C-10 不回填，ADR L385），所以重放期的每一天都會觸發 X2 (iii)，全部列為異常待查證。這是事先宣告字面的問題，要交 quant。

#### N22-1（D-9 新增第 7 點）
- **定位字串（唯一，L823）：** `6. 逾時與 on-demand 的紀錄也照常結算`
- **動作：** 在該行之後新增。
- **字面：**
  > 7. **重放不走本條的結算路徑**（N-22；tech-architect 2026-10-18 查證）：
  >    - `forecast_replay` 的結算不呼叫 `run_settlement_evaluation()`、`run_correction_job()`、`observed_sessions(*, view)`、`span_sessions`、`unobserved_weekdays` 與 `ledger_registration_start()`；
  >    - 不讀也不寫 `forecast_settle_eval`、`forecast_correction_job`、`forecast_index_check`；
  >    - 不寫 `forecast_ledger_events` 的 `x2_confirmed_non_session`、`unobserved_weekday`、`session_calendar_conflict`；
  >    - 不寫 `forecast_outcome`。
  >
  >    理由：
  >    - v1 重放只限大盤（事先宣告 §4.7）；`split_or_reduction_suspected` 不套用於大盤指數序列（第 3 點；事先宣告 §4.7 B-6），g 沒有用途。
  >    - 重放期在市場 DB 的涵蓋之前〔推論：ADR-0012 C-10 不回填〕。套用前瞻的判定視圖，重放期每個平日假期都會符合 A-77 第 10 項判準。
  >
  >    重放結算的存放、判定視圖、觀察日來源，以及 X2 (iii) 在重放期的對照日曆，在重放結算程式實作前另行定義，送風控；涉及事先宣告 §4.7、§6.3 的字面時，由 quant 登記（後續追蹤清單 N-22）。定義之前不得實作重放結算。
- **方向：** 補定義（收緊）。
- **送風控：要。**
- **N-22 的過渡約束全部遵守：**
  - 不捕捉例外；
  - `forecast_replay` 不進 D_reg（依 L659，不動）；
  - 不為重放期寫 `unobserved_weekday`。

#### N22-2（「全部評估」的範圍）
- **定位字串（唯一，L808）：** `五個值全部評估、不短路，回傳依`
- **動作：** 在該子點之後、同一層插入。
- **字面：**
  > - （N-22）「全部評估」指該 scope 允許集合（D-3 `void_reasons_json`）內的值，不適用的值不評估，這不算短路。`scope_kind = market` 不評估 `split_or_reduction_suspected`、`dividend_factor_unusable`、`basket_coverage_below_90`，不呼叫 `span_sessions` 與 `split_suspect_exceeds`。所以大盤的結算窗不經 D-9.3 B-3 的例外守衛；大盤不使用 g，登記只影響 §4.2 ③ 的計數。
- **方向：** 不變（釐清）。
- **送風控：** 要。
- **quant：** 選用。事先宣告 V13-01「判定時五值全部評估」可以加同義註。

#### N22-3（FL-66 (h)）
- **定位字串（唯一，L1861）：** `` 序列不呼叫 `split_suspect_exceeds` ``
- **動作：** 在 (h) 句末加。
- **字面：**
  > ；`scope_kind = market` 的結算評估與更正作業中，`span_sessions` 呼叫次數為 0（spy）；重放路徑不 import `app.forecast.settlement`、`app.forecast.correction`，不呼叫 `span_sessions`、`unobserved_weekdays`、`ledger_registration_start`（AST，N-22）
- **方向：** 收緊（測試）。

#### N22-4（追蹤清單，交 coordinator）
- N-22 拆成兩項：
  - **N-22a：** ADR 側的禁止句（N22-1～N22-3），送風控。
  - **N-22b：** 重放的判定視圖、觀察日來源，以及 X2 (iii) 在重放期的對照日曆。負責：quant → 風控。期限依 N-22 原規則，改為 **dirdef 凍結前（凍結阻擋）**，理由是涉及事先宣告 §4.7、§6.3 的字面。
- 給 quant 的選項（我不代決）：
  - (a) 重放期 X2 只用 (i)、(ii) 兩項正面證據，(iii) 不適用，並揭露；
  - (b) 以經 ADR 接入的官方日曆作重放期的對照日曆。

---

### 第 4 項：風控 suggested 兩項

#### (i) 快照範圍的未結算集合與 ⑥ 的集合

**結論：照現行字面不一定相同。**
- 快照範圍在 ② 依「全部未結算預測的 T 最小值」決定（L739），⑥ 則在 ④ 開啟的寫入交易內判定「全部未結算的預測」（L756）。
- on-demand POST 屬於另一個 process，不受 `max_instances` 限制（L1626）。它在 ② 與 ④ 之間寫入時，⑥ 的集合會比 ② 大。
- 一般情形下，新紀錄的 T 是候選 T，T+h 還在未來，不會被判定。但有兩個缺口：
  - ② 時集合為空，快照範圍就沒有定義；
  - 市場 DB 落後數個 session、大盤 (ii) 已有後續觀察日時，新紀錄可能已經可以判定，落在快照之外【推論】。
- 處理方式：② 讀一次評估集合 U，⑥ 只判定 U。

**S-1（D-9.2 快照範圍）**
- **定位字串（唯一，L739）：** `快照範圍 ＝ [該次評估全部未結算預測的 T 的最小值`
- **被取代原文：** `` - 快照範圍 ＝ [該次評估全部未結算預測的 T 的最小值, 評估當日（Asia/Taipei）]，記入 `view_range_json`。 ``
- **字面：**
  > - **評估集合與快照範圍**（N-21 風控 suggested；tech-architect 2026-10-18）：
  >   - ② 在讀大盤列之前，以一個主 DB 唯讀查詢讀一次「沒有任何 `forecast_outcome` 列的 `forecast_record`」，得到本次的評估集合 U（不分 `trigger`、`late`）。
  >   - 快照範圍 ＝ [U 的 T 的最小值, 評估當日（Asia/Taipei）]；U 為空時為 [評估當日, 評估當日]。記入 `view_range_json`。U 的筆數、排序後 `forecast_id` 串的 sha256，記入 `eval_set_count`、`eval_set_sha256`。
  >   - ⑥ 恰好判定 U，不在 ④ 另讀未結算集合。② 之後才寫入的紀錄（例如 on-demand POST）不屬於本次評估：不寫 outcome，不列入 `waiting_json`，由下一次評估納入。這依寫入時點機械決定，不看預測內容；等待以觀察日計數，所以不會讓任何預測少等。
  >   - ④ 在寫入交易內驗證：U 的每一筆仍然沒有 outcome 列。不成立時，整個評估不寫入，記 WARNING。
  >   - U 為空時，評估照常執行 ③、④、⑤，寫一列 `forecast_settle_eval`（`waiting_json = []`）。
- **方向：** 補定義（收緊）。對判定結果而言不變；新增的只是邊界與空集合的定義。
- **送風控：** 要。

**S-2（D-9.2 ⑥）**
- **定位字串（唯一，L756）：** `⑥ 對全部未結算的預測判定`
- **被取代原文：** `` ⑥ 對全部未結算的預測判定：結算或作廢的寫入 `forecast_outcome`；等待的記入 `waiting_json`。 ``
- **字面：**
  > ⑥ 對評估集合 U（②）的每一筆判定：結算或作廢的寫入 `forecast_outcome`；等待的記入 `waiting_json`。
- **方向：** 不變（釐清）。

**S-3（`forecast_settle_eval` 欄位）**
- **定位字串（唯一，L398）：** `` `view_range_json = {start, end}`； ``
- **動作：** 在該子點之後插入。
- **字面：**
  > - `eval_set_count INTEGER NOT NULL`、`eval_set_sha256 NOT NULL`（評估集合 U，D-9.2；U 為空時 count 為 0，sha256 取空字串的值）；
- **方向：** 補定義（收緊）。

**S-4（寫入驗證）**
- **定位字串（唯一，L405）：** `` 而且都是判定視圖中 T+h 已觀察到、`valid_until_session` 已過、尚未結算的預測； ``
- **被取代原文：** 同定位字串。
- **字面：**
  > 而且都是判定視圖中 T+h 已觀察到、`valid_until_session` 已過、尚未結算、屬於評估集合 U 的預測；本列寫入的每一筆 outcome 也都屬於 U；
- **方向：** 收緊。

**S-5（FL-65 新增 (n)）**
- **定位字串（唯一，L1855）：** `` R 小於前一列的 `market_run_max` → 記 WARNING，不寫入。 ``
- **動作：** 在 (m) 這一格之後插入。
- **字面：**
  > - (n)（N-21 風控 suggested）② 與 ④ 之間注入 on-demand 紀錄 → 該筆不在 outcome 與 `waiting_json`，`eval_set_count` 不含它，下一次評估納入；U 為空 → 寫一列 `forecast_settle_eval`，`view_range_json` 首尾都是評估當日，`last_settle_eval_at` 前進；② 之後 U 的某筆被其他寫入者寫入 outcome → 整個評估不寫入。

#### (ii) recorder 是否屬於「登記先於使用」的作業

**結論：不屬於，要明文寫出來。**
- 依 A-77 第 10 項，登記當下 d ∉ (i) ∪ (ii)，所以登記與否不改變觀察日集合。recorder 的 σ_d 觀察日（V12-19）不受影響，recorder 也不讀 g。
- recorder 的 `as_of=cutoff(T)` 是過去時點的輸入。用它登記，會把 `as_of` 之後才進入 (i) 或 (ii) 的真交易日永久登記成未觀察平日。這和 G5 是同一種錯誤，依「固定排除」無法回復。
- **連帶發現：** P-2 的「交集」寫法會讓「X2 確認寫入」的登記範圍變成空集合，因為 X2 依 A-77 第 4 項不讀觀察日集合。風控 P-3a 的括號「含其交易內依 A-77 第 10 項的登記」因此變成空話，但無害。建議明寫，不改風控的字。

**S-6（A-77 第 10 項）**
- **定位字串（唯一，L661）：** `**成立時**：`
- **動作：** 插在該子點之前、與「登記先於使用」同一層。
- **字面：**
  > - **登記先於使用的適用範圍**（N-21；tech-architect 2026-10-18）：
  >   - 「該作業讀取觀察日集合的日期範圍」：結算評估為快照範圍（D-9.2 ④）；更正作業為 `view_range_json`（D-9 第 5 點）；缺日稽核為 [D_reg, 最新觀察日]。
  >   - X2 確認寫入本身不讀觀察日集合（第 4 項），依上句交集為空，本身不登記。在結算評估 ③ 寫入時，同一份輸入的登記由 ④ 完成（D-9.2）。
  >   - recorder 以 `observed_sessions(as_of=cutoff(T))` 讀觀察日，不屬於上句的作業，不呼叫 `unobserved_weekdays` 與 `ledger_registration_start()`（AST）。理由：(1) 登記當下 d ∉ (i) ∪ (ii)，觀察日集合不因登記與否改變；(2) `as_of` 視圖是過去時點的輸入，以它登記，會把之後才進入 (i) 或 (ii) 的真交易日永久登記成未觀察平日。
  >   - recorder 寫入的 X2 確認與 `forecast_index_check` 列，依第二子點。
- **方向：** 不變（釐清；第三子點對 recorder 是收緊）。
- **送風控：** 要。這是風控核可條文的適用範圍說明。

---

### 第 5 項：N-23 (a)～(e) 與 N-24 (f)

**裁定**
- **(a) 要求本次缺日稽核也成功。** 理由同 dev-lead：F-3 逾時率要讀缺日，稽核失敗時寫快照，缺日率會偏低，方向是放寬。
- **(b) 略過，不寫 fail-closed 列。** 理由是 UNIQUE 加上只增不改：一次暫時失敗會把 T 永久鎖住。
  - 展望面已有 fail-closed 路徑：沒有 snapshot 時，大盤與個股為 `gated`＋`validation_refresh_pending`（L1359）；snapshot 作業失敗時，遮蔽持續到下一筆成功（L1648）。
  - **plan 面沒有任何「沒有 T 的 plan」的規則**：grep「沒有 plan」等字樣零命中。所以要交 PM／creative-lead／風控。
- **(c) 比照失敗處理。**
- **(d) C17 寫進 D-7 第 2 點（N23-2）。** C11～C20 併入約束清單，其中 C20 修改。
- **(e) 採方案 A，D-7.1 不必修訂。** 理由：順序由呼叫順序保證，一個 `max_instances` 就涵蓋全部步驟，也符合 D-7.1 單一 job 的字面。
  - **不加「剩餘時間檢查」。** 那要估計結算耗時，成為依機器速度而變、測試無法重現的可調參數。結算只能在 D-7.7 的 40 分鐘期限內啟動，已經是確定性的上限。
  - 被吞掉的 23:10 重試，要用 listener 讓它看得見。listener 的存在寫進 ADR，告警規格交 devops-sre（ADR-0026，N-23 (1)）。
- **另外補一處：** D-7.2 的五步順序裡沒有更正作業，D-3 只寫「結算之後」。我把它放在缺日稽核之後、驗證快照之前。這樣當晚的 supersede 會進入當晚的快照（R10-7 的撤銷也以「作業完成後第一筆 daily snapshot」計），而且不動 P-2 引用的「結算 → 缺日稽核」相鄰關係。

#### N23-1（D-7.2 順序）
- **定位字串（唯一，L486）：** `plan（政策表）。T 的 plan 一律使用`
- **被取代原文：** `2. **執行順序**：記錄 → 結算 → 缺日稽核 → 驗證快照 → plan（政策表）。`（只改這一句；同行後半不動；L2341 引用區塊不動）
- **字面：**
  > 2. **執行順序**：記錄 → 結算 → 缺日稽核 → 晚到掃描與更正作業（有觸發時，D-3「晚到資料的觸發」第 1 點）→ 驗證快照 → plan（政策表）。
- **方向：** 補定義（收緊）。
- **送風控：** 要。

#### N23-2（D-7.2 新子點：(a)、(b)、(c)、(e)）
- **定位字串（唯一，L487）：** `結算評估失敗（含 D-9.3`
- **動作：** 插在 P-5 子點之後、同一層。P-5 本句一字不改。
- **字面：**
  > - （N-23；tech-architect 2026-10-18；dev-lead 查證方案 A）**步驟隔離**：
  >   - 各步在單一 job `forecast_record` 內，由 `recorder.py` 的單一編排函式依序呼叫。
  >   - 一步失敗（拋出 `Exception`，或回傳非成功的結果）時，記 WARNING，不中止後續步驟；後續步驟是否執行，只依下一子點的前置條件。
  >   - 結算失敗的例外只在編排函式中、`run_settlement_evaluation()` 呼叫的外面接住；接住時，該函式的主 DB 交易已 rollback（D-9.2 ⑦）。
  >   - 不得拆成多個 APScheduler job（要改動須先修訂 D-7.1）。
  >   - D-7.7 期限已到、結算評估沒有啟動時，視同結算失敗：記 WARNING，缺日稽核照常執行。
  > - （N-23）**前置條件**：
  >   - 缺日稽核與更正作業：不依賴前面任何一步是否成功。
  >   - 驗證快照：本次執行的結算評估已 commit（寫入了 `forecast_settle_eval` 的一列），**而且**本次缺日稽核已 commit。任一項不成立，本次不寫驗證快照，記 WARNING，也不寫任何 fail-closed 列。理由：snapshot 有 UNIQUE 而且不重算（D-11.2），寫入的落後或 gated 列，之後重試成功也蓋不掉；缺日稽核失敗時寫快照，F-3 逾時率會偏低。
  >   - plan：`computed_for_session = T` 的 daily snapshot 存在時才寫；不存在時本次不寫 plan，記 WARNING，不得改用較早的 snapshot。
  >   - 已有同一 T 的快照或 plan 列時，視為略過，不是錯誤。
  >   - 23:10 重試與啟動補跑依同樣的條件補寫。
  > - （N-23）**持續失敗期間**：
  >   - 沒有 T 的 snapshot 時，展望依 D-11.4 既有的「沒有 snapshot」規則處理。
  >   - 沒有 T 的 plan 時，任何面都不得把較早的 plan 當成 T 的 plan 呈現。呈現方式未定義（狀態句、是否並列較早的 plan 與它的資料日期），由 PM 評估、creative-lead 起草、風控審查。核可前，plan 衍生內容不渲染，免責句與時間戳句照常（fail-closed）。
  >   - 這是 plan 渲染上線前的阻擋項（比照後續追蹤清單 C-2）。
- **方向：** 補定義（收緊）。持續失敗時 plan 不可用，屬可用性的代價，不是放寬。
- **送風控：要。** 「持續失敗期間」一點涉及面向使用者的建議內容，同時交 PM。
- **CEO：** 否。

#### N23-3（D-7.1 listener）
- **定位字串（唯一，L485）：** `` trigger 明定 `timezone="Asia/Taipei"` ``
- **動作：** 在該子點之後、同一層插入。
- **字面：**
  > - （N-23）`max_instances=1` 時，前一次執行尚未結束，新的觸發點（含 23:10 重試）會被略過、不排隊。`EVENT_JOB_MAX_INSTANCES`、`EVENT_JOB_MISSED` 都要有 listener 記 WARNING，內容帶被略過的觸發時刻；告警規格依 ADR-0026（devops-sre，後續追蹤清單 N-23 (1)）。結算評估是否啟動只依 D-7.7 期限，不得以剩餘時間的估計決定。
- **方向：** 收緊（揭露）。
- **送風控：** 知悉即可，隨包附上。

#### N24-1（D-8.2 稽核上界）

**方案比較**

| 方案 | 優點 | 缺點 |
|---|---|---|
| **甲（建議）：S 的 `late_cutoff_at` 過了才判定** | 確定性；過了這個時點，S 不可能再出現 `late=0` 的紀錄（D-7.4 `late = created_at ≥ late_cutoff_at`），判定是終局的 | 缺日列晚約一天出現 |
| 乙：先寫，之後補撤銷列 | 即時 | 要為只增不改的 `forecast_gaps` 新增撤銷語意，牽動 TG-b、TG-c、F-3 |
| 丙：只在記錄失敗時延後 | 改動小 | 依情境裁量，不是機械規則 |

- **定位字串（唯一，L712）：** `2. **稽核**：對每個觀察日 S`
- **動作：** 在該點之後新增子點，接在 `reason` 判定清單之前。
- **字面：**
  > - （N-24；tech-architect 2026-10-18）**判定上界**：
  >   - 觀察日 S 只在稽核當下的 store 時鐘 ≥ S 的 `late_cutoff_at` 之後，才判定要不要寫缺日列，`reason` 依當時的狀態判定。`late_cutoff_at` 以 D-7.4 的同一個函式、取 T ＝ S 計算。
  >   - 在這之前不寫，也不寫任何暫定列；這時 S 只是尚未判定，`last_gap_audit_at` 照常前進。
  >   - 理由：S 的 `late=0` 紀錄只可能在 `late_cutoff_at` 之前寫入。過了這個時點，判定才是終局的。例如 22:10 記錄失敗、23:10 重試成功時，S 沒有缺日列。
  >   - A-77 第 10 項的登記不受本點影響。
  >   - 另一面：S 的缺日列晚約一天才出現，所以 F-3 逾時率、TG-b、TG-c 對 S 的反映也晚約一天。
  >   - 殘餘情形：官方日曆在稽核判定之後變動、使 S 的截止線延後時，依 K-12 送風控。
- **方向：** 補定義（兩面）。收緊面：不再有與實際紀錄永久矛盾的 `job_error`。放寬面：缺日與 F-3 逾時率的反映延後約一天。
- **送風控：要。** F-3 是暫停條件，TG-b、TG-c 面向使用者。
- **CEO：** 建議不需要明示同意，因為不改任何門檻，只影響時點；由風控裁定。

**FL-67（新增，接在 FL-66 之後、FL-68 之前；定位同 N21-9，插在 FL-24 之前）**
> - **FL-67**（C-22；D-3 `forecast_index_check`；N-23；N-24）：
>   - (a) 對應表每一列各一格，斷言寫入的列種與欄位。
>   - (b) 同值的 bar 第二晚再偵測，不寫新的 detection，也不寫新的 ① 查證；`fetched_at` 不同、值相同，視為同一身分；值改變則是新身分。
>   - (c) 獨立來源已接入時，每次評估中，`check_id` 落在 (前一列 V, 本列 V] 的 `daily_recheck` 列，涵蓋前一列 V 時的全部待查證列；來源版本第一次出現時是 `source_onboarding`，不另做 `daily_recheck`。
>   - (d) 寫入驗證各一格拒絕：`direct` 用在需查證的項目；`no_error` 與 `close_erroneous` 並存；`correct_close_obtained` 沒有先行的 `close_erroneous`；`conflict` 寫入任何 determination；非 detection 列的 `session_date` ≠ 所指 detection 的值；FL-19 (c)③ 加格：`verification_ref` 指向非 verification 列、`x2_case = conflict` 的列，或其他 `session_date` 的列。
>   - (e) 評估讀 V 之後再插入的判定列不採用（對應 LG-29 (i)）。
>   - (f) 寫入呼叫點只有 recorder 與 D-9.2 ③（AST）。
>   - (g) N-23：結算拋例外、R 倒退、期限已到三種情形各一格 → 缺日稽核寫入、驗證快照與 plan 都不寫、不出現 fail-closed 列；23:10 重試成功 → 補寫兩者；缺日稽核失敗 → 快照不寫。
>   - (h) N-24：S 的 `late_cutoff_at` 之前稽核 → 不寫 S 的缺日列；22:10 記錄失敗、23:10 重試寫入 `late=0` → 隔晚稽核不寫缺日列；只有逾時紀錄 → `late_only`。
- **方向：** 收緊（測試）。

---

### 對實作的約束（給 qa-reviewer，逐條可檢查）

- **沿用：**
  - TA 的 C1～C8；
  - 風控改寫的 C3，以及 C9、C10。
- **dev-lead 的 C11～C20 併入，修改兩處：**
  - C17 改為「依 ADR D-7.2 前置條件子點」；
  - C20 的 listener 由 suggested 改為 required，並刪掉剩餘時間的建議。
- **新增：**
  - **C21：** `forecast_index_check` 的寫入呼叫點只有 recorder 與 D-9.2 ③（AST）；V 在 ④ 完成登記之後讀一次（spy）；判定只讀 `check_id ≤ V` 的列。
  - **C22：** `run_correction_job()` 的 `MAX(run_id)`、`MAX(event_id)`、`MAX(check_id)`、大盤列、休市日表各讀一次（spy）；不呼叫強制重抓；快照範圍起點等於 D_reg。
  - **C23：** 更正作業的啟動檢查涵蓋三類觸發；三種 from 只由已完成作業前進。
  - **C24：** `scope_kind = market` 與重放路徑不呼叫 `span_sessions`（spy、AST）；重放不 import `settlement`、`correction`。
  - **C25：** 評估集合 U 只在 ② 讀一次；⑥ 的判定對象等於 U；`eval_set_sha256` 等於 U 的雜湊。
  - **C26：** recorder 不呼叫 `unobserved_weekdays`、`ledger_registration_start`（AST）。
  - **C27：** 缺日稽核對 S 的判定，以 `late_cutoff_at` 為上界；不得自行比較時刻，只能經 D-7.4 的函式。
- **禁止事項：**
  - 不得新增任何以操作者指定日期或 payload 寫入 `forecast_index_check` 的 CLI 或 API；
  - 不得以估計剩餘時間決定是否啟動結算；
  - 不得在結算失敗時寫入 gated 或落後的驗證快照，或沒有 T 日 snapshot 的 plan。

## 三、驗證

**讀過的內容：**
- 風控 B-3 回送確認全文；
- 風控 v0.14 單項確認 L1～L130、L253、L292；
- 我 B-3 回送原稿全文；
- tech-writer N-21 套用回報與 coordinator 裁定（P-1～P-6 已在 `be8c66a` 落地，D-9 第 6 點在 L823，不是懸空引用）；
- dev-lead N-23 回報全文；
- 追蹤清單全文（含 N-24）。

**ADR-0027 讀過的段落：**
- L1～L479（D-1～D-6，含 D-3 全部新表）；
- L480～L839（D-7～D-10）；
- L840～L880；
- L1240～L1320；
- L1354～L1399；
- L1610～L1651；
- FL-19～FL-66（L1707～L1886）；
- 待決事項（L2190～L2295）。

**事先宣告讀過的段落：**
- §1.4（L509～L525）；
- §4.7（L1013～L1030）；
- §6.3「觸發」至「大盤指數序列」（L1206～L1310）；
- §6.4、§6.5（L1333～L1357）。

**程式查證：**
- `app/forecast/**` 不存在（Glob 零命中）；
- 預測帳識別字在 `apps/` 下零命中，只有 `tests/test_diagnose.py:168` 的同名片段，與本案無關。

**定位字串：** 每一條都用 Grep `-o` 驗證只命中一處。例外與處理：
- `forecast_correction_job(` 在 L344 與 L3219（修訂紀錄）都有，所以改用含 `market_scan_restore_suspected IN (0,1)), started_at)` 的字串，唯一。
- ② 的舊字也出現在 L3391，所以本批不以它定位。

**屬於推論、未查證的部分：**
- 重放期早於市場 DB 的涵蓋範圍；
- 市場 DB 落後時 on-demand 可能已可判定；
- 更正作業快照的成本；
- 官方日曆變動的殘餘情形。

**沒有做的事：** 沒有改任何檔案，沒有讀 `.env` 或 `*.db`，沒有跑程式或 git。

## 四、下一步

1. **coordinator：**
   - 把本包（C22-1～7、N21-1～9、N22-1～3、S-1～6、N23-1～3、N24-1、FL-67）整包送風控。
   - 追蹤清單：N-22 拆成 N-22a、N-22b，N-22b 為凍結阻擋，負責 quant；新增「plan 缺席呈現」一項，負責 PM → creative-lead → 風控，期限為 plan 渲染上線前；N-24 狀態改為「tech-architect 已提案」。
2. **風控：**
   - 逐項裁定。
   - 特別請看三處：N21-4 的啟動者缺口；S-6 的 X2 交集為空，以及它和 P-3a 括號的關係；N24-1 的兩面方向標。
3. **quant：**
   - N-22b（重放期 X2 (iii)）。
   - 另請確認一個讀法【推論】：X3 下，來源修訂值和記錄當下的擷取必然不同，所以「通過 X1～X4 的來源修訂值」實際上要等查證才成立，這和 §6.3「確認有誤之後」的讀法有關。不阻擋本包。
4. **PM、creative-lead：** N23-2 的「plan 缺席」呈現。
5. **devops-sre：** N-23 (1) 告警，含兩個 APScheduler 事件。
6. **tech-writer：** 風控核可後另批套用；被取代原文逐字記入修訂紀錄。
7. **dev-lead：** 方案 A 加 C1～C27；D-9 結算程式仍等 N-17 與本包核可。
8. **CEO：** 知悉表數 17→18（CEO 段第 13 點）。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/work/reviews/2026-10-18-B3回送N21登記範圍單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-ADR-0027-v0.14條文與事先宣告v0.14四項單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-N23排程器失敗行為查證-dev-lead.md
- /home/user/AICompany/work/reviews/2026-10-18-N21結算路徑條文套用回報-tech-writer.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

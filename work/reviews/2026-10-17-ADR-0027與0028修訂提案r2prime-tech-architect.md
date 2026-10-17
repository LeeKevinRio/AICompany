# ADR-0027／0028 r2' 修正提案 — tech-architect

> 轉存：coordinator，2026-10-17，子 agent 回報逐字轉存。依風控 r2 附件 B 確認修正；A-36 待風控單項確認後才交 tech-writer 套用。

---

## 1. 本次結論

**r2' 已改完。** 風控指出比條件寬的 4 處都已收緊，各項 required 也都補進提案。沒有改的條文照 r2 原文。我沒有改 ADR。

另外有三件事要知道：

- **有一項需要風控再確認。** `POST /api/outlook/symbols/{symbol}` 我選「比照紀錄清單，不顯示 label」（A-36）。
- **UNIQUE 直接拿掉 `policy_version`，不走其他做法。** 所以不需要另外送確認。
- **事先宣告的版本已更正為 v0.8（`adca703`）。** 所有「quant 對齊」都改成 v0.9，行號依 v0.8 重查。

data-engineer 2026-10-17 的回報帶出一件事：觀察日集合要用哪個輸入來源，現在還能選，而且這個決定歸我。這要另外出 ADR-0028 r3（附件 B'-3）。在那之前，R4c × observed 維持 LM-71＋LM-26，不會開放 LM-24。

D_v 目前仍被 R5-06 的 VETO 卡住：`surface_not_permitted` 還沒有核可的字面。

**已修正處對照表**

| 風控條件 | 修正的條文 | 怎麼改 |
|---|---|---|
| 比條件寬 1：`not_in_schedule` 的字面守門 | A-25、A-29、A-30（FL-52、FL-52b） | 只對應 LM-88，加兩點守門，其餘用 LM-89；刪除 NS-a。`plan_record` 加 `in_holdings_or_watchlist_at_plan`。FL-52 容許「一個值依守門對應兩個片段」；FL-52b 加「快照之後才加入自選」的 fixture |
| 比條件寬 2：LM-79／LM-81 | A-23 第 5 點、A-24（FL-45） | 拆成兩張對照表：LM-87 只擴入 LM-81；LM-79 等 worst_case 變體核可 |
| 比條件寬 3：UNIQUE | A-29 | 改為 `UNIQUE(symbol, market, data_as_of)` |
| 比條件寬 4：scope 限定 | A-25 | `not_in_schedule` 寫成規則，只在 `scope_kind = symbol` 時成立 |
| B-1：同一份 snapshot | A-30（FL-54 (e)） | 驗證狀態與 `display_state` 取自同一列 T 日 snapshot，加 fixture |
| B-2：FL-32 | A-24 | FL-32 改為直接引用 A-23 的公式與 FL-45b |
| B-2：quant 登記 | A-23 第 7 點、A-37 | quant v0.9 登記，方向標「補定義」 |
| B-3：`SERVES` 非空 | A-26 第 2、3 點，A-30（FL-54 (g)） | route 列舉測試；執行期也 fail-closed |
| B-3：天氣圖示 | A-26 第 2a 點 | 天氣是呈現形式，不是獨立的顯示面；依所在端點的 `SERVES` 判定 |
| B-3：伴隨揭露 | A-26 第 2b 點，A-30（FL-54 (f)） | 揭露字面全部核可，該格才生效 |
| B-4：已存的截止時間 | A-27 (d′)、A-29 | 新增 store 計算的 `window_started`；所有列的 `late_cutoff_at` 都非 NULL |
| B-4：fixture | A-30（FL-52b） | 08:29:59／08:30:00 × 已結算／未結算 |
| B-4：POST 的處理 | A-36 | 選 (ii) 不顯示 label，**送風控確認** |
| B-5：四項 | A-28、A-30（FL-53） | 正面判定不認列；`f2_deadline` 照常；只在下一個檢查點重判；`status` 記有效狀態、`stats_json` 記原始結果、旗標；加兩個 fixture |
| A-27：`voided` 衝突 | A-27 (f) | `voided` 移出 `exclusion_reasons`；欄位改名為 `in_eligible_set` |
| A-33：用詞 | A-33 | 分開寫 recorder 強制、CI 檢查、qa 核對三種方式 |
| A-38：可達性 | A-38、A-39、A-40 | 拿掉「預期不可達」；翻轉 R4c 前，data-engineer 的確認要先送風控單項確認 |
| suggested：小標 | A-22 | 改為「任何時點都不得延後」 |
| suggested：tuple | A-31 第 3d 點 | `PolicyTable` 直接採 tuple |
| 版本 | A-23、A-33、A-34、A-37 | 改為 v0.9；行號依 v0.8 |

## 2. 各部門回報

- **tech-architect（本人）**：唯讀。讀了風控附件 B 確認、第五批逐字審（LM-86～93）、data-engineer 2026-10-17 回報、事先宣告 v0.8 相關行、PRD 中天氣的段落。產出 r2' 修正條文與對照表。
- **risk-compliance-officer**：本次未參與。要他單項確認 A-36 的 POST 處理方式。
- **quant-researcher**：本次未參與。v0.9 待辦見 A-37。
- **creative-lead**：本次未參與。完整起草清單見 A-37。
- **data-engineer**：本次未參與。觀察日的確認回報要送風控；除權息歷史回補的問題見 A-37。
- **product-manager**：本次未參與。要確認：`PLAN_OUTPUT_SURFACES`、`SURFACE_PERMISSIONS` 的初版，以及未列舉頁面的歸屬（附件 B'-2）。
- **其他部門**（dev-lead、frontend-engineer、qa-reviewer、qa-e2e、devops-sre、art-lead、tech-writer 等）：本次未參與。這是唯讀的架構文件，Codex 不適用。

## 3. 驗證

- **查證的事實**：
  - LM-87、LM-88、LM-89 的核可全文與條件（第五批逐字審 L150-153）；
  - `market_trading_days` 只做 DISTINCT〔轉引 data-engineer 回報 L12-23，我沒有重讀 `cache.py`〕；
  - 事先宣告 v0.8 的行號：§2.1 σ_d L402、§4.3 (f) L576、L639、條件一 L643、底線 3 L658、D-19 L849、D-20 L850、§11 L1317、LG-23 L1513、§9.3 第 15、16 點 L1217、L1219；
  - 天氣：PRD L575、L590 寫明天氣映射在後端，大盤天氣在市場總覽。
- **沒做的事**：沒有執行程式、測試或 git，沒有改任何檔案，沒有讀 `.env` 或 `*.db`。
- **需要 CEO 知悉**：若 C-8 已經裁示，A-23 的逐檢查點規則和 A-28 的「暫停期間正面判定不認列」要以知悉項補送（由 coordinator 處理）。沒有需要新裁示的事項。

## 4. 下一步

1. **coordinator**：把 A-36 送風控單項確認。確認後，連同 r2 的其他條文交 tech-writer 套用；套用後用 diff 核對 A-23 第 5 點、A-25、A-29。
2. **quant v0.9、creative-lead、data-engineer、PM**：依 A-37 各自處理。
3. **tech-architect**：觀察日集合的輸入來源，另外出 ADR-0028 r3（附件 B'-3）。

---

## 附件 A：r2' 修正條文（只列有異動的條；未列的 A-32、A-41 照 r2 原文）

**A-22｜D-12 VETO 底線第 2 點（只改小標與排列）**
- **新文**：
  - 不得刪除條件二（風控 VETO）。
  - **任何時點都不得延後：**
    - C-8 定案前，選項集合已經凍結（事先宣告 §4.5），退出期限 n＝150（族群 250）不在可以調整的範圍內；
    - C-8 定案到 D_v 之間，依共同部分 (vii)；
    - D_v 之後，只能往更嚴的方向改（例如提早退出期限），而且要升版、留紀錄。
  - 原本「CEO 書面同意即可延後」的路徑刪除。依據：事先宣告 V6-03。
- **FL-31 補充**：同 r2。

**A-23｜D-12「下架原因列舉值」（整條取代 r2 版）**
1. **逐檢查點判定**。相鄰兩個檢查點記為 (c₀, c₁)，對每個 c：
   - `fail(c) = fail_normal(c) OR (void_rate(c) > 5% AND fail_w(c))`；
   - `void_rate(c)` 讀該檢查點 checkpoint 列的值，定義依事先宣告 §4.3 (f)（v0.8 L576）：作廢列 ÷（已結算列＋作廢列）；
   - 條件一成立，若且唯若 `fail(c₀) AND fail(c₁)`；不要求兩個檢查點的作廢率都 > 5%。
2. **原因值與優先序**：同 r2。
   - `f2_invalid_stop`：`fail_normal(c₀) AND fail_normal(c₁)`；
   - `f2_invalid_stop_worst_case`：條件一成立，但上式不成立；
   - 優先序：`f2_invalid_stop` > `f2_deadline` > `f2_invalid_stop_worst_case`。
3. **`display_reasons_json.withdraw`** 的結構：`{reason, conditions_met, pair: [{n, void_rate, fail_normal, fail_w}, …], positive_suppressed_during_f3: bool}`。最後一個欄位見 A-28。
4. **片段**：
   - `f2_invalid_stop_worst_case` 在 LM-81 中用 LM-87（WC-a，第五批條件核可），要完整渲染，不得截斷。
   - LM-87「其中作廢比例超過 5% 的檢查點，依最不利情境計算」由第 1 點的逐檢查點規則保證屬實，滿足 LM-87 的核可條件，不必重送。
5. **兩張對照表**：
   - `LM81_WITHDRAW_REASON_FRAGMENTS` ＝ {`f2_invalid_stop`: LM-75, `f2_deadline`: LM-74, `f2_invalid_stop_worst_case`: LM-87}；
   - `LM79_WITHDRAW_REASON_FRAGMENTS` ＝ {`f2_invalid_stop`: LM-75, `f2_deadline`: LM-74, `f2_invalid_stop_worst_case`: **LM-79 的 worst_case 變體（待送）**}。
   - **LM-87 不得代入 LM-79**（會出現三層括號）。變體核可之前，這一項空著，FL-45 會失敗。
   - LM-79 讀前一版的原因時，經 `views` 讀前一版 claim 最後一筆 withdrawn snapshot。
6. D_v 前，LM-79 的 worst_case 變體必須核可；否則 FL-45 失敗，不得出貨。
7. **quant v0.9**：把相同文字登記進 §4.5 的條件一（v0.8 L643）與底線 3（L658），方向標「補定義（逐檢查點；比『兩點都 > 5%』嚴）」，在 D_v 前完成。C-8 若已經裁示，以知悉項送 CEO。

**A-24｜FL-45、FL-32**
- **FL-45 新文**：
  - (a) 兩張對照表都完整：每個 `withdraw_reason` 在兩張表都有項目，而且片段 ID 都在風控核可表內。缺任何一個就失敗；不得用 skip、xfail 或暫定字面讓測試通過。
  - (b) LM-79、LM-81 只從各自的對照表取值；另加斷言：LM-87 永遠不會出現在 LM-79 中。
  - (c) 效力鏈同 r2：FL-45 失敗 → G-6 不成立 → 不得寫入排程紀錄。
- **FL-45b**：同 r2。
- **FL-32（改）**：
  - 原文：「作廢率 >5% 時，F-2 的判定取一般情境與 W 之中比較差的那個。」
  - 新文：FL-32（底線 3）：F-2 條件一依 D-12「下架原因列舉值」第 1 點的公式，逐檢查點套用 W，並以 FL-45b 的 fixture 釘住。ADR 內不另外寫第二種表述。

**A-25｜D-11.4 第 6 點（整條取代 r2 版）**
- **優先序**（不變）：`suspended_f3` → `withdrawn_f2` → `gated` → `surface_not_permitted` → `before_dv` → `missing_scheduled` → `not_in_schedule` → `late` → `insufficient` → `voided`。
- **判定**：R_s 指 `trigger=scheduled`、`supersedes_id IS NULL`、`data_as_of=T` 的原始紀錄。
  - `surface_not_permitted`：claim 層的值。判定讀的驗證狀態，與 `display_state` 取自同一列 T 日 snapshot（A-30 FL-54 (e)）。
  - `not_in_schedule`：**只在 `scope_kind = symbol` 時成立**。條件是：沒有 R_s；T 日至少有一個排程 run；每個排程 run 的範圍快照都不含這檔。
  - `missing_scheduled`：沒有 R_s，而且不符合 `not_in_schedule`。大盤或族群沒有 R_s 時，一律是這個值，即使快照漏掉了自己（那屬於系統故障）。
  - `late`：有 R_s，而且 `late=1`。
  - `insufficient`、`voided`：有 R_s，而且 `late=0`。
  - 互斥、窮舉、與 on-demand 無關、快照和 run 同一個交易寫入：同 r2。
- **`reasons` 的字面對應**（經 LM-86 的 `{原因}`，由後端在產生 plan 時選定，前端不推斷）：
  - `not_in_schedule`：
    - `plan_record.in_holdings_or_watchlist_at_plan = false` → **LM-88**；
    - 否則 → **LM-89**。
  - `missing_scheduled` → LM-89。
  - NS-a 刪除。
  - `surface_not_permitted`：R5-06 依否決方向重送、核可之前，沒有可用的片段，D_v 會被擋住。
  - 其餘七個值：與 `pending_triggers` 的「恢復前這條條件無法成立」片段同一批送審（A-37）。

**A-26｜D-11.4 第 9 點（只改第 2、3 點，新增 2a、2b）**
- **第 2 點 `api` 那一格**：
  - 每個對外端點都要在 `ENDPOINT_SURFACES` 登記 `SERVES`，而且 `SERVES` 必須至少含一個 `api` 以外的值；
  - 呼叫時 `consumer = SERVES ∪ {api}`；
  - 沒有登記或 `SERVES` 為空的端點，`outlook_view` 一律回 `surface_not_permitted`（執行期 fail-closed）；
  - 由 FL-54 (g) 用 route 列舉測試釘住。
- **2a 天氣圖示**：`OutlookWeather` 是展望 label 的一種呈現形式，不是獨立的顯示面（映射在後端，PRD L561、L590），依它所在端點的 `SERVES` 判定。
  - 市場總覽的天氣屬於 `first_layer`；
  - 不在 D-20 列舉內的頁面，在列舉修訂並送審之前，不得渲染展望 label 或天氣（附件 B'-2）。
- **2b 許可的前提是伴隨揭露**：
  - 每一格都登記 `required_disclosures`：D-1／D-5 的驗證徽章與 PV-45 固定句；個股另加 PA-4；「優於基準」時另加 D-2 的開盤基準句，以及 D-4 的區間、n、期間。
  - 所列片段全部核可，這一格才生效；否則不許可。大盤與族群的 `alert`、`export` 也一樣。
  - 由 FL-54 (f) 釘住。
  - 初版的矩陣由 PM 與 `PLAN_OUTPUT_SURFACES` 一併確認；之後任何一格要開放，都要送風控。
- **第 3 點補一句**：`consumer` 至少要含一個 `api` 以外的顯示面。

**A-27｜D-11.4 第 11 點（整條取代 r2 版）**
- **不出現 label 的情形**（依序判斷，任一條成立就不出現）：
  - (a)～(d) 同 r2；
  - **(d′) on-demand 紀錄，而且 `window_started = 1`、尚未結算**：不出現 label。
    - 狀態片段的意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」；
    - 判定讀寫入時已存的值，臨界點同 FL-15（08:29:59 顯示，08:30:00 不顯示）。
- **揭露**：
  - (e) 同 r2；
  - **(f)** 每筆紀錄帶 `in_eligible_set: bool`（r2 叫 `counts_in_primary`，改名），值等於該筆是否屬於 E，與 validation 呼叫同一個函式（FL-49）。
    - `exclusion_reasons` 的封閉列舉改為 {`before_dv`, `late`, `on_demand`, `pit_violation_confirmed`}，**`voided` 移出**。
    - 理由：作廢列依 D-11.1 屬於 E（不計入 n，但計入 W）。作廢原因依事先宣告 §4.10 D-12，用 `status_reason` 的既有片段標示（例如 LM-63）。
    - `in_eligible_set` 的真／偽字面不得寫成「計入 n」，因為證據不足與作廢的列屬於 E、但不計入 n（LM-91）。
  - PIT 違規列的標示：同 r2。

**A-28｜D-11.4 第 12 點（整條取代 r2 版）**
- 優先序 `suspended_f3` > `withdrawn_f2` > `gated` > `shown`，不變。
- (i) **`suspended_f3` 期間，負面結果照常生效**：檢查點照常計算；降級與 F-2 下架照常生效，`withdraw_reason`、`withdrawn_at_n` 照寫。
- (ii) **正面結果不認列**：升為 `better_than_baseline`、重新上架，都不認列。
  - snapshot 的 `status` 記不認列之後的有效狀態；
  - 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}}`；
  - 有 `withdraw` 區塊時，設 `positive_suppressed_during_f3 = true`；
  - quant 的檢查點檢討紀錄要揭露這件事。
- (iii) **與 A-22 的交互作用**：暫停期間剛好碰到 n＝150（族群 250），原始結果是正面但不認列時，有效狀態不是 `better_than_baseline`，條件二成立，以 `f2_deadline` 下架。**不得因此延後退出期限。** LM-74 在這種情形下仍然屬實。
- (iv) `display_reasons_json` 的結構固定為 `{suspend: [...], withdraw: {...}|null}`。
- (v) 每一筆 snapshot 都由當下的 (F-3, F-2, 閘門) 各項狀態彙整出 `display_state`，不讀上一筆的 `display_state`。
  - 恢復只代表下一筆 snapshot 重新彙整，**不觸發任何新的判定**；
  - 升級與重新上架，只能在恢復之後的下一個事先宣告的檢查點重判。
- (vi) quant v0.9 登記相同文字。

**A-29｜D-3 資料表（整條取代 r2 版）**
- **`forecast_record`**：
  - 新增 `window_started`：只有 on-demand 列有值，由 store 在寫入時計算 `created_at ≥ late_cutoff_at`；不得由呼叫端傳入，之後也不重算。
  - CHECK：`(trigger='scheduled' AND late IN (0,1) AND window_started IS NULL) OR (trigger='on_demand' AND late IS NULL AND window_started IN (0,1))`。
  - **所有列（含 on-demand）的 `late_cutoff_at`、`late_cutoff_basis` 都必須非 NULL**，依 D-7.4 的規則在寫入時計算。
- **`forecast_run` 與 `forecast_scope_snapshot`**：同一個交易內寫入（同 r2）。
- **`plan_record`**：
  - 加 `data_as_of`，以及 **`UNIQUE(symbol, market, data_as_of)`**，不含 `policy_version`。每個 (symbol, T) 只有一份 plan；升 `policy_version` 只對還沒有 plan 的 T 生效。
  - 加 **`in_holdings_or_watchlist_at_plan BOOLEAN NOT NULL`**：在同一次 run 計算 plan 時，讀庫存與自選的 store 取得。這是 LM-88 守門的唯一來源。
  - `outlook_display_state` 的 `consumer_surfaces`、`restricting_surfaces`：同 r2。
- **`forecast_input_series`**：`series_kind`，同 r2。

**A-30｜FL-52、FL-52b、FL-53、FL-54（FL-44 照 r2）**
- **FL-52（改）**：原因與片段的對照表允許附守門的項目：`REASON_FRAGMENTS: Mapping[reason, tuple[GuardedFragment, ...]]`。測試四點：
  - (a) 每個值至少有一個項目；
  - (b) 所有片段 ID 都已核可；
  - (c) 每個值的守門，對所有輸入組合都恰好選出一個片段（窮舉表）；
  - (d) `exclusion_reasons` 與紀錄清單的兩個狀態片段（逾時；期間已開始）同樣要對應。
  - 不得 skip；效力鏈同 FL-45 (c)。
- **FL-52b（加 fixture）**：
  - (7) 快照之後、產生 plan 之前才加入自選 → `not_in_schedule`，旗標為 true → LM-89；
  - (8) 大盤或族群的快照漏掉自己 → `missing_scheduled`，永遠不會是 `not_in_schedule`；
  - (9) on-demand 的建立時間在 08:29:59／08:30:00，各分成已結算與未結算，同時驗證紀錄清單與 POST 回應（A-27 (d′)、A-36）。
- **FL-53（加 fixture）**：
  - (c) 暫停期間在 n＝100 有正面原始結果 → 恢復後不是 `better_than_baseline`，`stats_json` 保留原始結果，旗標成立；
  - (d) 暫停期間在 n＝150 有正面原始結果 → `withdrawn_f2`，原因 `f2_deadline`；
  - (e) 在兩個檢查點之間恢復 → 到下一個檢查點之前，狀態都不上升。
- **FL-54（改 e，新增 f、g）**：
  - (e) 加一個 fixture：T+1 的 snapshot 升級了，T 的 plan 仍然讀 T 的 snapshot，而且驗證狀態與 `display_state` 出自同一列（`outlook_view` 只讀一次 snapshot 列）；
  - (f) 對每個許可的格子，該顯示面的回應都帶齊 `required_disclosures`；揭露片段還沒核可的格子，判定為不許可；
  - (g) route 列舉測試：每個回應中含 `OutlookView` 衍生欄位的 route，都在 `ENDPOINT_SURFACES` 登記了非空的 `SERVES`；另驗證沒有登記時，結果為 `surface_not_permitted`。

**A-31｜D-15 第 3d 點（拆成兩點）**
- 3d：`PolicyTable` 與它的規則、條件 model 一律用 tuple。這是新程式，沒有遷移成本，所以是 required。
- 3e（suggested）：`RuleSet.rules`、`AllOf.all`、`AnyOf.any` 改用 tuple。

**A-33｜D-14 首句（整條取代 r2 版）**
- **新文**：G-1～G-6 全部成立之前，不得寫入任何 `trigger=scheduled` 的前瞻紀錄。強制方式分三種：
  - **recorder 執行期強制**：G-3、G-4；以及 dirdef 必須含 `f2_variant`、`c8_decision_ref`、`c8_decision_sha256`（G-2 的登記部分）。recorder 不比對雜湊，也不讀決策檔。
  - **CI 檢查**：`c8_decision_sha256` 與 ref 所指的檔案相符。這不是 recorder 執行期的閘門。
  - **qa-reviewer 在 PR 核對**：G-1；G-2 的真偽，以及決策紀錄內容與 `f2_variant` 是否一致；G-5；G-6。
  - G-7 是 on-demand 的說明，不是排程紀錄的閘門。
- **FL-38**：同 r2。
- **連帶**：quant v0.9 把事先宣告 v0.8 L639 改成同樣精確的三分寫法。現行的「不是程式強制的機器閘門」在 r2 套用後會低報。

**A-34｜σ_d 實作位置（只改引用）**
- 「事先宣告 §2.1 定稿條文」改為「v0.8 L402 起」；§9.3 第 15 點改為「v0.8 L1217」。其餘同 r2。

**A-35｜Consequences（加一點）**
- on-demand 查詢從 T+1 08:30 起，到新的 T 進入市場 DB 之前（大致是交易日白天），回應與紀錄清單都不顯示 label，要等結算後才列示（A-36）。這段期間臨時查詢的用途會變小，PM 要知悉。

**A-36｜D-7.8 on-demand（整條取代 r2 版）**
- 原 r2 的三點保留：紀錄清單依 D-11.4 第 11 點；POST 登記 `SERVES={symbol_detail}`；on-demand 永遠不進 policy。另加：
- **`POST /api/outlook/symbols/{symbol}` 的處理採 (ii)：比照紀錄清單。**
  - 回傳的 on-demand 紀錄若 `window_started = 1` 而且尚未結算，回應不含 label，只回狀態片段「查詢時預測期間已開始，結算後列示」；
  - `window_started = 0` 時，照常經過閘門，附 PA-4。
  - 不採 (i)「顯示 label，同區塊附『預測自 {T} 收盤起算，期間已開始』」。理由：
    - 所有顯示面只用一條規則；
    - 與 PA-6、D-10 一致；
    - 不需要多一個揭露片段。
  - **送風控單項確認。**

**A-37｜待決事項（整條取代 r2 版）**
- **風控**：
  - A-36 的 POST 處理；
  - A-38 中 data-engineer 的確認回報（單項確認）。
- **creative-lead**（依風控附件 B 確認的 B-8 完整清單）：
  - R5-06 依否決方向重送（`surface_not_permitted`）；
  - LM-86 `{原因}` 其餘 7 個片段；
  - `pending_triggers` 的「恢復前這條條件無法成立」片段；
  - LM-79 的 worst_case 變體；
  - `exclusion_reasons` 的 4 個片段；
  - 紀錄清單的兩個狀態片段；
  - `in_eligible_set` 的真／偽字面；
  - 只改名、不必重審：LM-88、LM-89 條件欄的原因值名稱；LM-71 的擴用條件。
- **quant v0.9**：
  - A-23 第 7 點；A-28 (vi)；A-33 的 L639；
  - D-19（L849）、§11（L1317）、LG-23（L1513）中的 `no_scheduled_record` 改為新名稱，並寫明：縱深防禦觸發時，原因值依 A-25 的 R_s／快照規則決定（不是 `late`），而且記 WARNING；
  - B-6、B-7（同 r2）。
- **data-engineer**：
  - A-32 的查證；族群成員名單是否有 PIT 儲存；
  - D0 前 60 日窗內的除權息涵蓋：`TWT48U_ALL` 沒有歷史回補，族群可能輸出 `E-ADJ-COVERAGE`〔轉引 data-engineer 回報 L29-34〕；
  - 觀察日的確認回報送風控。
- **PM**：
  - `PLAN_OUTPUT_SURFACES` 與 `SURFACE_PERMISSIONS` 的初版；
  - 未列舉頁面的歸屬（附件 B'-2）。
- **dev-lead**：同 r2。

### ADR-0028

**A-38｜D-5 的兩列（整條取代 r2 版）**

| 狀態／條件 | 市場 | 字面 |
|---|---|---|
| R4b `in_session`，basis＝observed | TW | LM-71＋LM-26 同區塊；不得用 LM-27；`build_summary` 記 WARNING |
| R4c `after_close_pending`，basis＝observed | TW | 確認之前：LM-71＋LM-26；確認之後：LM-24 |

- **R4b 這一列，以現行程式來說是到得了的**：`market_trading_days` 只做 `SELECT DISTINCT trade_date`，沒有排除未定案的 bar〔轉引 data-engineer 2026-10-17 回報 L12-23〕。WARNING 是出現非最終資料的訊號，不是「不可達」的斷言。
- **R4c 的切換**：翻轉這一列的 PR 合併之前，data-engineer 的確認回報（觀察日集合只來自通過品質檢查的最終日線，不含盤中、暫定或占位列）**要先送風控單項確認**；只經 qa 審查不夠。
- 觀察日集合的輸入來源還沒決定（附件 B'-3）。決定之前，R4c × observed 不會切換。

**A-39｜CS-12（只改 observed 的那一段）**
- LM-24 在 `basis=observed`、`sub_reason=after_close_pending` 時渲染，要等翻轉 PR 合併後才生效。合併前，data-engineer 的確認回報要經過風控單項確認，並由 qa 審查。
- CS-11、CS-15 (b)：同 r2。

**A-40｜待決事項（加一點）**
- 風控：data-engineer 觀察日確認回報的單項確認。其餘同 r2。

---

## 附件 B'：本輪新增的確認與待決

| # | 事項 | 建議 | 誰決定 |
|---|---|---|---|
| B'-1 | A-36 的 POST 處理：(ii) 不顯示 label，或 (i) 顯示 label 加揭露 | (ii) | 風控單項確認 |
| B'-2 | D-20 的五個顯示面沒有涵蓋族群列表、族群詳細頁（若它們不屬於首層）。依 fail-closed，列舉修訂之前不得渲染展望 label 或天氣 | 由 PM 依 Phase 4 版面指定歸屬，或新增值後送審 | PM，加風控 |
| B'-3 | 觀察日集合的輸入來源：data-engineer 回報可以選，例如市場 DB 的 ok bars run 加上時段防護，或快取加最終性條件 | 我另外出 ADR-0028 r3 做方案比較；在那之前 R4c × observed 維持 LM-71＋LM-26 | tech-architect 提出，風控、CEO 核可 |
| B'-4 | D_v 被 R5-06 的 VETO 卡住（`surface_not_permitted` 還沒有核可的字面） | creative-lead 優先重送 | creative-lead、風控 |
| B'-5 | C-8 若已經裁示：A-23 的逐檢查點規則與 A-28 的正面判定不認列，以知悉項補送 CEO | — | coordinator |
| r2 的 B-6、B-7 | 指數是否套用分割門檻；B4 的成員時點 | 同 r2 | quant v0.9 |

**相關檔案**
- `/home/user/AICompany/work/reviews/2026-10-17-ADR-r2附件B單項確認-風控.md`
- `/home/user/AICompany/work/reviews/2026-10-17-新定位第五批字面逐字審-LM86至LM93-風控.md`（L150-153）
- `/home/user/AICompany/work/reviews/2026-10-17-探測指令補查項-data-engineer回報.md`（L12-34）
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`
- `/home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md`
- `/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`（v0.8：L402、L576、L639、L643、L658、L849-850、L1217、L1219、L1317、L1513）
- `/home/user/AICompany/work/stock-desk-新定位-PRD-2026-10-16.md`（L561、L575、L590）

# ADR-0027 r2'' 增補：A-36 四項 required（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# A-36 r2'' 增補：補進風控的 4 項 required（tech-architect，唯讀）

## 一、結論

**風控的 4 項 required 和 1 項 suggested 都已寫成可直接套用的條文，共 6 處（R''-1～R''-6）。** 風控已單項確認 A-36 採 (ii)「POST 比照紀錄清單，不顯示 label」。r2' 其他條目一字不動，我沒有修改任何檔案。

- **套用方式**：tech-writer 先套 r2'，再用本增補取代或補充對應位置。r2' 文首（L3）「A-36 待風控單項確認後才交 tech-writer 套用」這個前提，到此已滿足。
- **我做的一個設計決定**：遮蔽狀態的回應改用「封閉白名單」，不用「刪掉指定欄位」的做法。這比風控列的範圍嚴：
  - `evidence_json` 整個不回，不只拿掉裡面的標籤；
  - 另外排除 `range_basis` 和 `baseline_predictions_json`，兩者都會透露方向（後者含基準的方向標籤）。

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **白名單封閉 schema（採用）** | 新增欄位預設不出現（fail-closed）；可用 schema 機械斷言 | 回應資訊較少；要增列欄位須修訂並送審 | 低 |
| 黑名單（只刪風控列的欄位） | 改動最少 | 日後新增的方向欄位會漏出；`evidence_json` 內的指標值仍可能暗示方向 | 違反 B-3「API 本身就是顯示面」 |
| `label: null`（保留鍵、給空值） | 前端型別簡單 | 鍵還在，介於「有欄位」與「沒欄位」之間，不好稽核 | 中 |

## 二、增補條文（逐字）

### R''-1｜A-36 整條取代 r2' 版
- 插入位置：r2' 附件 A 的 A-36（L231-240），整條取代。
- ADR-0027 對應段落：D-7.8 第 8 點 on-demand（L325-331），接在 L331 之後。

> **A-36｜D-7.8 on-demand（整條取代 r2' 版；r2'' 依風控 2026-10-17「追加一」的 4 項 required 修正）**
> - 原 r2 的三點保留：紀錄清單依 D-11.4 第 11 點；POST 登記 `SERVES={symbol_detail}`；on-demand 永遠不進 policy。另加：
> - **`POST /api/outlook/symbols/{symbol}` 的處理採 (ii)：比照紀錄清單**（風控 2026-10-17 單項確認，APPROVE WITH CONDITIONS）。
>   - 不採 (i)「顯示 label，同區塊附『預測自 {T} 收盤起算，期間已開始』」。理由：所有顯示面只用一條規則；與 PA-6、D-10 一致；不需要多一個揭露片段。
> - **1. 回應形狀依紀錄狀態分三種，一律採封閉 schema（白名單）：**
>   - (a) `window_started = 0`、尚未結算：照常經過 D-11.4 第 5 點的閘門；`availability = evaluated` 時帶 label，附 PA-4。
>   - (b) `window_started = 1`、尚未結算（下稱「期間已開始、待結算」）：
>     - **API 回應本體不得含任何帶方向的欄位。** 這是對 API 本身的要求（API 就是顯示面，風控附件 B 確認 B-3），不只是前端不渲染。
>     - 不得出現的欄位與內容，至少包括：
>       - `label`、`range_basis`；
>       - 天氣（`OutlookWeather`），以及任何色彩或色調代碼；
>       - 方向詞；
>       - 以方向表述的失效條件（`invalidations_json`）；
>       - `evidence_json`（整個不回，不只其中的標籤）；
>       - `baseline_predictions_json`（含基準的方向標籤）。
>     - 回應只能含以下白名單欄位，其餘一律不得出現（schema 設 `extra="forbid"`／`additionalProperties: false`）：`forecast_id`、`trigger`、`scope_kind`、`scope_key`、`horizon`、`data_as_of`、`created_at`、`valid_until_session`、`window_started`、`settled`（固定 false）、`availability`（固定 `"unavailable"`）、`status_fragment_id`、`disclosure_fragment_ids`（含 PA-4）、`in_eligible_set`、`exclusion_reasons`。
>     - `label` 這個鍵本身不得出現，不是給 null。
>     - 白名單要增列欄位，須修訂本點並送風控。
>   - (c) 已結算（該 `forecast_id` 有 `forecast_outcome` 列）：依第 4 點。
> - **2. 狀態片段：**
>   - (b) 的狀態片段，意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」。**這句只是語意，不是已核可的字面。**
>   - 逐字字面由 creative-lead 起草（風控附件 B 確認 B-8 第 6 項；目前是第六批 R6-05 的 OS-a 候選，正在風控逐字審），風控核可後才可使用。
>   - POST 回應與紀錄清單用同一個片段 ID（暫定常數 `RECORD_STATUS_ONDEMAND_PENDING`），不另立 POST 專用片段。
>   - **核可之前，FL-52 (d) 失敗**，依 FL-45 (c) 的效力鏈：G-6 不成立 → 不得寫入排程紀錄 → D_v 被擋住。on-demand 依 D-14 的 G-7 同樣受 G-6 約束，也不得寫入。
>   - 不得用暫定字面、placeholder、skip 或 xfail 讓測試通過。
> - **3. 資料日期：**
>   - (b) 的 schema 中 `data_as_of`（T）為必填、非 NULL。
>   - 前端在狀態片段的同一區塊，以既有的「資料截至」徽章呈現；字面沿用 ADR-0009 D-5 的「資料截至 {日期}」家族，日期依年份規則。
>   - 徽章日期取這筆紀錄的 `data_as_of`。不得借用頁面上其他區塊的徽章，也不得取 `price_bars_cache` 的 `last_bar_date`（展望鏈與持倉鏈的資料源不同，見 Consequences）。
> - **4. 結算之後：**
>   - label 只能以「已結算紀錄＋實際結果」的形式出現，不得呈現為目前展望。
>   - 回應中 label 只放在 `settled_record` 物件內。同一物件必須同時帶 `settlement_date` 與結算結果：`status = resolved` 時為 `realized_label`、`hit`。
>   - 頂層不得有 `label`。也不得出現在任何「目前展望」的欄位或呈現，包括天氣、首層展望、當日展望欄位、提醒、匯出。FL-16 照舊。
>   - 前端在同一區塊同時渲染「已結算」標示與實際結果，所用字面必須是已核可片段。核可之前，已結算的 on-demand 紀錄不顯示 label（fail-closed）。
>   - outcome 為 `unresolvable_missing_data` 或 `excluded_corporate_action`（作廢）時，沒有實際結果可以並列。風控確認處理方式之前，不顯示 label，只顯示 `status_reason` 的既有片段。
>   - 本點適用所有已結算的 on-demand 紀錄（`window_started` 為 0 或 1 都一樣），POST 回應與紀錄清單相同。
> - 選 (ii) 的代價見 A-35。

### R''-2｜A-27 (d′) 整點取代 r2' 版（只因 A-36 而改，A-27 其餘不動）
- 插入位置：r2' A-27 的 (d′)（L154-156）。
- ADR-0027 對應段落：D-11.4 第 11 點（L431-434）。

> - **(d′) on-demand 紀錄，而且 `window_started = 1`、尚未結算**：不出現 label。
>   - 狀態片段的意思是「查詢時預測期間已開始，結算後列示」，不得用「逾時」。這句只是語意，逐字字面待風控核可（A-36 第 2 點）。
>   - 判定讀寫入時已存的值，臨界點同 FL-15（08:29:59 顯示，08:30:00 不顯示）。
>   - 回應形狀（封閉 schema、資料日期、結算後的形式）與狀態片段 ID，依 D-7.8 第 8 點（A-36 第 1～4 點）。紀錄清單與 POST 共用同一個 schema 與片段。

### R''-3｜A-30 FL-52 (d) 改文
- 插入位置：r2' A-30 的 FL-52 (d)（L197）。
- ADR-0027 對應段落：「對實作的約束」中的 FL-52（r2 新增，接在 FL-44 L657 之後）。

> - (d) `exclusion_reasons` 與紀錄清單的兩個狀態片段（逾時；期間已開始）同樣要對應到已核可的片段。「期間已開始」片段由紀錄清單與 POST 回應共用同一個 ID（A-36 第 2 點）。風控核可它的逐字字面之前，本項失敗。

### R''-4｜A-30 FL-52b (9) 整點取代
- 插入位置：r2' A-30 的 FL-52b (9)（L202）。
- ADR-0027 對應段落：FL-52b（同上）。

> - (9) on-demand 的建立時間取 08:29:59 與 08:30:00，各分已結算與未結算，共四格。每一格同時驗證紀錄清單與 POST 回應（A-27 (d′)、A-36）：
>   - (9a) **schema 斷言**：每一格的回應 JSON，用 A-36 第 1 點對應狀態的封閉 schema 驗證（`additionalProperties: false`）。08:30:00 × 未結算那一格：`label` 鍵不存在，白名單以外的鍵一個都沒有。
>   - (9b) **全文掃描**：對 08:30:00 × 未結算的回應本體，遞迴走訪所有鍵與字串值，不得出現：
>     - label 列舉值（`bullish`、`range`、`bearish`，以值相等比對）；
>     - `OutlookWeather` 的所有列舉值；
>     - 色彩或色調代碼；
>     - 方向詞清單（單一來源）。
>   - (9c) **標籤互換不變**：比照 FL-43，在 store 層把該筆 label 在 bullish、range、bearish 之間互換，08:30:00 × 未結算的回應必須逐位元相同。
>   - (9d) **資料日期**：08:30:00 × 未結算的回應，`data_as_of` 非 NULL，而且等於該筆紀錄的 T。
>   - (9e) **結算後的形式**：兩個已結算格，label 只出現在 `settled_record` 內，同一物件帶 `settlement_date` 與結算結果，頂層沒有 `label`。另加一格作廢 outcome：不出現 label（A-36 第 4 點）。
>   - (9f) **前端契約測試**：
>     - 08:30:00 × 未結算的區塊，只渲染狀態片段、PA-4、「資料截至 {T}」，不渲染天氣圖示，也沒有方向色彩的 class；
>     - 已結算的區塊，同時渲染已結算標示與實際結果。
>   - 不得 skip；效力鏈同 FL-45 (c)。

### R''-5｜A-35 整條取代 r2' 版
- 插入位置：r2' A-35（L228-229）。
- ADR-0027 對應段落：Consequences「代價與壞處」（L570-579），接在 L579 之後。

> **A-35｜Consequences（加一點）**
> - on-demand 查詢從 T+1 08:30 起，到新的 T 進入市場 DB 之前（大致是交易日白天），POST 回應與紀錄清單都不顯示 label，只顯示狀態片段與資料日期。
> - 要等結算之後，才以「已結算紀錄＋實際結果」列示，不會補成目前展望（A-36）。
> - 影響範圍主要是不在排程範圍內的個股；排程範圍內、T 日排程紀錄已存在的個股，POST 直接回傳排程紀錄。
> - 這段期間臨時查詢的用途會變小，**PM 與 CEO 都要知悉**（風控 2026-10-17「追加一」suggested）。

### R''-6｜A-37 與附件 B'-1 的連帶修改（只改下列子項）
- 插入位置：r2' A-37（L242-266）與附件 B' 表的 B'-1 列（L294）。
- ADR-0027 對應段落：「待決事項」（L684-709）。

> - A-37「風控」段：「A-36 的 POST 處理」改為
>   - 「A-36 狀態片段的逐字字面（R6-05 OS-a 或替代案）」；
>   - 「A-36 第 4 點：作廢 outcome 的 on-demand 紀錄結算後可否顯示 label」。
> - A-37「creative-lead」段：
>   - 「紀錄清單的兩個狀態片段」後面加註：「（『期間已開始』片段同時用於 POST 回應，A-36 第 2 點；R6-05 (b′) 的 PS-a、PS-b 因採 (ii) 已不需要，撤回不審）」；
>   - 新增一項：「已結算 on-demand 紀錄的『已結算＋實際結果』呈現字面（既有核可片段不足時起草，A-36 第 4 點）」。
> - 附件 B'-1：「建議」欄改為「已決：(ii)」；「誰決定」欄改為「風控 2026-10-17 APPROVE WITH CONDITIONS，4 項 required 見 A-36 第 1～4 點」。

套用時請在 ADR-0027「修訂紀錄」的 A-36 條註明依據：`work/reviews/2026-10-17-A-15-事先宣告v0.9核對與A36及B0單項確認-風控.md`「追加一」。

## 三、CEO 白話說明

> 交易日白天（早上 8:30 之後、當天收盤資料進來之前），使用者臨時查一檔不在庫存、自選或排程裡的股票，畫面不會顯示「偏多、震盪、偏空」，只會顯示「預測期間已開始，結算後列示」和資料日期。
> 原因是：這時預測期間已經開始，再給方向等於看了部分結果才下判斷，這筆紀錄就不可信。
> 等期間結束、結算後，它會出現在紀錄裡，呈現方式是「當時的預測＋實際結果」，不會被當成目前的看法。
> 代價是白天臨時查詢的用處變小；晚上收盤資料進來後到隔天 8:30 前查詢，照常顯示（附「不計入主統計」）。

## 四、另案（沒有混入 r2''）

1. **G-7 字面有歧義。** 「on-demand 不受 G-6 以外的限制」容易被讀反。R''-1 第 2 點依賴「on-demand 也受 G-6 約束」這個讀法，建議 D-14 改成肯定句。
2. **on-demand 去重規則沒有定義。** 同一 (symbol, T) 重複查詢時，是回傳既有的 on-demand 紀錄，還是再寫一筆，D-7.8 沒有寫。這會決定白天看到 08:29:59 寫入那筆（顯示 label），還是新寫一筆（不顯示）。建議：同一 (symbol, T) 只寫一筆，之後回傳既有紀錄，讀已存的 `window_started`。
3. **封閉 schema 建議推廣。** A-27 (a)～(d)、POST 回傳 `late=1` 的排程紀錄、FL-34 下架，目前只約束「label 不出現」，沒有約束 `evidence_json`、`invalidations_json`、`baseline_predictions_json`、`range_basis`。依 B-3 同一精神，應統一採用白名單。
4. **結算後形式是否推廣到排程紀錄。** A-36 第 4 點目前只管 on-demand。紀錄清單裡已結算的排程紀錄，是否同樣只能以「已結算＋實際結果」呈現，建議比照。
5. **FL-16 的範圍要界定。** FL-16 說 on-demand「永遠不會出現在當日展望的 API 回應中」，但 POST 本身就回傳 on-demand 的 label。「當日展望 API」要用 `ENDPOINT_SURFACES` 明確列出是哪些端點。
6. ADR-0028 r3（觀察日來源）依指示不在本報告處理。

## 五、待確認事項

1. **風控**：作廢 outcome 的 on-demand 紀錄，結算後可否以「label＋作廢原因片段」呈現。我先採 fail-closed，不顯示 label。
2. **creative-lead、風控**：單筆「已結算＋實際結果」是否已有核可片段。我在字面遷移清單只查到 TV-b（作廢句）與 LM-38，沒有找到 resolved 列的核可字面。若沒有，要起草；核可前已結算的 on-demand 紀錄不顯示 label。
3. **qa-automation、creative-lead**：FL-52b (9b) 方向詞清單的單一來源要指定。既有禁用詞掃描器（FT-15、FT-16）是否涵蓋方向詞，我沒有查證。
4. **風控（確認即可）**：「資料截至 {日期}」改綁這筆紀錄的 `data_as_of`。風控已說「既有徽章即可」，我視為不必另送審；若風控認為換了變數來源就要重審，請指示。

**查證範圍**
- 讀過：風控「追加一」全文；r2' 全文；r2 的 A-27、A-29、A-30、A-35、A-36；ADR-0027 的 D-1（L225-233）、D-3（L243-264）、D-7.8（L325-331）、D-9、D-11.4（L413-435）、D-14（L530-543）、Consequences、FL-38～FL-44、待決；字面遷移清單 R6-05（L1736-1779）；creative-lead 第六批回報；ADR-0009 D-5（L94-95）。
- 沒做：沒有執行程式、測試或 git；沒有讀 `.env` 或 `*.db`；沒有修改任何檔案。

**相關檔案**
- `/home/user/AICompany/work/reviews/2026-10-17-ADR-0027與0028修訂提案r2prime-tech-architect.md`（A-27 L151-163、A-30 L192-210、A-35 L228-229、A-36 L231-240、A-37 L242-266、B'-1 L294）
- `/home/user/AICompany/work/reviews/2026-10-17-A-15-事先宣告v0.9核對與A36及B0單項確認-風控.md`（L111-123）
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`（L325-331、L431-434、L530-538、L570-579、L604-605、L656-657、L684-709）
- `/home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md`（L1736-1779、L2382）
- `/home/user/AICompany/docs/adr/0009-stock-desk-日線快取以交易日判定新鮮度.md`（L94-95）

# V18-04 兩組辨認條件可逐列數出確認

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**可以逐列數出，兩組互斥，合起來剛好涵蓋應涵蓋的列，不漏也不重。不必回送風控。** 有兩點需要說明：
- 「前者」必須和「後者」套用同樣三個欄位條件，只是 `pending_json` 的條件反過來。只寫「曾出現在 `pending_json`」會多數。
- 另有一個時間界限的收緊建議（suggested）。照規格實作時結果一樣，所以不擋 N-29 批。

下面第四節附了可以直接引用的確認字句。

**更正一個編號：** V18-04 改的是 §4.2 作廢數 **(7)** 裡「其中依 N-29 (b) 期限改記作廢的筆數」那一子項，不是 (8)。quant 原文是「V18-04，§4.2 作廢數 (7)」。(8) 是 V17-07，指待重算之後重算為 `resolved` 的列，和本題兩組不重疊：鏈尾一邊是作廢、一邊是 resolved。

## 二、各部門回報（tech-architect）

以下行號以本次讀取為準。tech-writer 仍在寫入，行號會變，定位以字串為準。

**1. 欄位、型別與 JSON 判定方式：都具備**

各條件對應的欄位（全部在 `forecast_outcome`，除非另註）：

| 條件 | 欄位與登記位置 | 判定方式 |
|---|---|---|
| supersede 作廢列 | `supersedes_id`（L348）、`status`（L313） | `supersedes_id IS NOT NULL AND status ≠ 'resolved'` |
| `status_reason ≠ index_bar_confirmed_erroneous` | `status_reason`（L313） | 作廢列一定有值：`void_reasons_json` 非空，而且第一個元素等於 `status_reason`（L316）。所以不會遇到 NULL 比較的問題 |
| `correction_causes` 含 `x2_session_removed` | JSON 陣列，封閉列舉，排序固定、不重複；supersede 列一定非空（L349–350） | 用陣列元素逐值相等判定，例如 `EXISTS (SELECT 1 FROM json_each(correction_causes) WHERE value = 'x2_session_removed')` |
| `void_reasons_json` 含 `missing_bar_after_wait` 或 `basket_coverage_below_90` | JSON 陣列，五值封閉列舉，依 `VOID_REASON_ORDER` 排序、不重複（L314–324） | 同上，逐值相等 |
| 曾出現在 `pending_json` | `forecast_correction_job_end.pending_json`，每項含 `forecast_id`（L371） | `EXISTS (SELECT 1 FROM forecast_correction_job_end e, json_each(e.pending_json) p WHERE json_extract(p.value, '$.forecast_id') = o.forecast_id)` |

- 所有 JSON 判定一律不得用 `LIKE` 或子字串比對。
- `forecast_id` 是 ULID（L280），在 JSON 中照原樣存成字串。

**`pending_json` 的歷史是否完整：完整（限已完成的作業）**
- 兩張作業表都只增不改（L353），並且由 D-2 第 2 點的 `BEFORE UPDATE`／`BEFORE DELETE` trigger 強制（L260）。ADR 裡找不到任何保留期限或清理規則。
- 作業列不會被「取代」。每一列 job_end 都存下該作業結束時完整的待重算集合（L377 是逐作業帶入的快照）。某項從後來的 `pending_json` 消失，早先那幾列照樣查得到。所以「曾出現在任何 `pending_json`」＝ 對所有 job_end 列取聯集，資料完整。
- 中斷的作業沒有 job_end 列，它的待重算判定不留紀錄。這和 (7)「曾經待重算」（L382）、畫面遮蔽 (a)（L1589）用的是同一個來源，三者定義一致，不算缺口。

**2. 互斥、涵蓋與邊界**

- **母集合 ＝ 依 N-29 (b) 期限改記作廢的列，兩者完全相等。**
  - supersede 作廢列只有 (甲)、(乙) 兩支，其餘一律拒絕寫入（L1663）。
  - (甲) 的條件是 `status_reason = index_bar_confirmed_erroneous`，所以「`≠ index_bar_confirmed_erroneous`」就等於 (乙)。(乙) 本身就要求含 `x2_session_removed`；這個條件在本題重複了，但無害，可以保留當防護。
  - (乙) 的寫入驗證規定：`void_reasons_json` 含 `missing_bar_after_wait` 或 `basket_coverage_below_90` 時，必須 N-29 (b) 已登記、而且本作業的判定視圖已到期（L1659）。
  - 待重算只由更正作業重查，所以 N-29 (b) 的到期作廢一定是更正作業寫入的 supersede 列。
- **互斥：** 「曾出現」和「從未出現」是同一個謂詞的兩面，所以兩組互斥，而且合起來剛好等於母集合。
- **同一筆預測多次 supersede：** 不會重複計。作廢列不得再被 supersede（L1636、L1656），加上 `UNIQUE(supersedes_id)`（L352），所以每個 `forecast_id` 在母集合中最多一列，而且一定是鏈尾。鏈上較早的 resolved supersede 列不是作廢列，不會被數到。
- **待重算之後到期作廢：** 歸到前者。依 L381，寫入作廢列那個作業的前一個已完成作業，其 `pending_json` 一定含這筆。作廢那次作業依 L377 把它從本身的 `pending_json` 扣掉，但前面的列仍然查得到。`write_validation_failed` 的項轉為等待資料、然後到期（T-6），也一樣歸到前者。
- **跨段情形（不重數，只是語意要說明）：** 某筆待重算之後重算為 resolved，後來又因新的 X2 順延，重查時已經到期，直接作廢。依「曾出現」它歸到前者，雖然這次到期不是從那一段待重算來的。總數不受影響。如果風控要「這一次的到期是否來自待重算」的精確分法，可以改用：「寫入該作廢列的作業之前、最後一個已完成作業的 `pending_json` 含該 `forecast_id`」。這個條件同樣可以逐列數出。
- **刻意排除、但不是漏數：** 大盤列在到期時，也可能同時成立 `index_bar_confirmed_erroneous`。這種列依判定順序走 (甲)，`void_reasons_json` 是 `[index_bar_confirmed_erroneous, missing_bar_after_wait]`，被條件 `status_reason ≠ index_bar_confirmed_erroneous` 排除在本子項之外。這正是風控加這個條件的用意。這類列已經在 (2)（兩個原因同時成立）和 (5)（結算後才確認、由更正作業改記 `index_bar_confirmed_erroneous`）計入。如果它曾經待重算，也在 (7)「曾經待重算」的總數裡。建議（suggested）在 (7) 這一子項加一句交叉參照。
- **中斷作業寫入的作廢列：** 照樣在母集合，分組依已完成作業的 `pending_json`，前後一致。這一點是推論：ADR 沒寫 ④ 寫入 outcome 和寫入 job_end 是否在同一個交易；但 L3598 已承認中斷作業寫入的 diag 列會留下來。

**3. 時間界限（suggested，收緊）**
- 風控字面「從未出現在任何 `pending_json`」沒有限定時間。照規格實作時，作廢之後這筆不會再進入 `pending_json`：作廢列不再重算，也就不會被拒絕。
- 但有一條防護路徑例外：若有程式錯誤，試圖 supersede 作廢列，寫入函式會拒絕並計入 `rejected_count`。依 L380，`causes` 含 `x2_session_removed` 的被拒項一定要進 `pending_json`。這時這筆會從後者翻到前者，之後重跑報表，分類就會不同。
- 建議加界限：「以 `correction_job_id` 小於該作廢列 `correction_job_id` 的 job_end 為限」。這樣分類在寫入當下就固定，不隨日後的紀錄改變。照規格實作時，加不加界限結果完全相同，所以不擋這一批。

**4. 範圍外的另一個發現（推論，不影響本題分組）**
- L377 只扣掉「本作業已為該 `forecast_id` 寫入 supersede 列的項」。如果中斷作業已經寫入作廢列，而那一筆原本在 `pending_json`，之後的作業會把它原樣帶入、永遠留在 `pending_json`。結果有三個：
  - (7)「目前待重算」多算；
  - `pending_json` 永遠非空，每一個新觀察日都會觸發一次更正作業；
  - 這一項永遠不會到期。
- 畫面遮蔽不受影響：L1589 比對的是鏈尾 `outcome_id`。
- 最小補法，二選一：
  - 寫明 ④ 寫入 outcome 和寫入 job_end 在同一個交易；
  - 或把 L377 的扣除條件改成「該 `forecast_id` 的鏈尾已不是該項的 `tail_outcome_id`」，並在 L381 加對應的一格。
- 這要由我另外提案、送風控。是否和 N-29 批同批，由風控決定。

## 三、驗證

- **讀過：**
  - 風控審查第一～四節全文；
  - ADR-0027：L256–263、L278–431、L1094–1149、L1589–1593、L1620–1669、L3594–3598；
  - 事先宣告：L829（作廢數整格）、L1418–1425；
  - quant 原始輸出：只用 Grep 取出 V18-04 的片段。
- **用 Grep 確認【事實】：**
  - ADR 沒有作業表的保留或清理規則；
  - `tail_outcome_id` 只出現在 L370、L371；
  - ADR 沒有明寫 outcome 寫入和 job_end 是否同一交易。
- **推論、未實測：** 中斷作業寫入的 outcome 列會留下來（比照 L3598 的 diag 列）；第二節第 4 點的卡住路徑。
- **沒有做的事：** 只用了 Read、Glob、Grep，沒有改任何檔案，沒有讀 `.env` 或 `*.db`，沒有跑測試或 SQL。上表的 SQL 只是示意寫法。

## 四、下一步

1. **給風控，可以直接引用的確認字句：**
   > tech-architect 2026-10-18 書面確認（唯讀，依 ADR-0027 工作樹）：事先宣告 V18-04（§4.2 作廢數 (7)「其中依 N-29 (b) 期限改記作廢的筆數」）的兩組可以由已登記的 schema 逐列數出。母集合 ＝ `forecast_outcome` 中 `supersedes_id IS NOT NULL`、`status ≠ resolved`、`status_reason ≠ index_bar_confirmed_erroneous`、`correction_causes` 含 `x2_session_removed`、`void_reasons_json` 含 `missing_bar_after_wait` 或 `basket_coverage_below_90` 的列；依 D-11.4 第 11 點 (h)「適用範圍」(乙) 的寫入驗證，這就是依 N-29 (b) 期限改記作廢的全部 supersede 作廢列。JSON 欄位一律以陣列元素逐值相等判定，不以子字串比對。前者 ＝ 母集合中，`forecast_id` 等於任一 `forecast_correction_job_end.pending_json` 某一項 `forecast_id` 的列；後者 ＝ 母集合中其餘的列。作廢列不得再被 supersede，所以每個 `forecast_id` 在母集合中至多一列；兩組互斥，合起來恰為母集合。「曾列待重算」以已完成作業的 `pending_json` 為準（兩張作業表只增不改，歷史完整），與 (7)「曾經待重算」及畫面遮蔽同一來源。(甲) 支同時含 `missing_bar_after_wait` 的列不在本子項，已計入 (2)、(5)。
2. **suggested，由風控和 quant 決定是否採用，不擋這一批：**
   - 前者的三個欄位條件寫進事先宣告的字面；
   - 加第二節第 3 點的時間界限；
   - 決定跨段情形要不要改用精確的分法；
   - 在 (7) 這一子項加 (甲) 支的交叉參照句。
3. **tech-architect 自己的待辦：** 就第二節第 4 點（中斷作業之後 `pending_json` 殘留）另外出提案、送風控，由風控決定是否和 N-29 批同批。

**相關檔案**
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-18-N29-11與LM155追加及作廢統計單項確認-風控.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/tasks/aa441dd4cd3181102.output（quant 原始輸出，只用 Grep）

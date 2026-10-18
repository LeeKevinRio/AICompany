# N-32 更正作業寫入交易與 pending_json 扣除提案

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- **N-32 成立。** ADR-0027 現有的交易邊界、啟動補跑、中斷復原規則，沒有一條擋得住這條路徑（推論，未實測；逐條依據見第二節 1）。
- **推薦 A、B 並用：**
  - **A 是主修。** 新增 D-9 第 5 點 ⑤：④ 先全部算完，不寫主 DB；之後在一個短的 `BEGIN IMMEDIATE` 交易內寫入 supersede 列、diag 列與 job_end。這樣中斷的作業不會留下任何列，整類問題都消失，包括 L3598 suggested (三) 的 diag 計數不一致。
  - **B 是保險。** 扣除條件加入「鏈尾已不是該項的 `tail_outcome_id`」。成立時照樣扣除並記 WARNING，**不拒絕寫入 job_end**。拒絕的話，同一情形之後每次都成立，所有更正作業會永久卡住。
  - **否決**把 ④ 的寫入直接放進同一個長交易（邊算邊寫）。整段重算期間會一直持鎖，另一個寫入者（API 的 on-demand）會卡在 `busy_timeout`。ADR 已用同樣理由否決過一次（L1394–1397「不採 (a)」）。
- **順帶發現一處既有不一致。** L377 的扣除條件漏了「重查後沒有任何欄位改變」這一格，但 L381 的驗證和 FL-68 (j) 都有這一格（風控已核可那兩處）。本提案改寫 L377 時一併補上，標為屬實性更正。
- **四項判定：**
  - 不擋 dirdef 凍結：n 與 W 不受影響。
  - 擋 dev-lead 實作更正作業：A 改了 `run_correction_job()` 的交易結構。
  - 沒有使用者字面，不必送風控做文案審查。但本提案改到風控已核可的 N-29 條文（L377、L381），依追蹤清單仍要由風控裁定規則。
  - 全部「CEO：否」。

## 二、各部門回報（tech-architect）

### 1. 問題確認（行號以本次讀取為準，定位以字串為準）

**卡住的路徑：**
- L377「扣掉本作業已為該 `forecast_id` 寫入 supersede 列的項，其餘原樣帶入」：只扣「本作業」寫的。
- L1641「更正作業依規則不重算這類列」，以及 L387「作廢列不會再被 supersede，所以鏈尾固定」。中斷作業寫入作廢列之後，後續作業不會重算這一項，所以它既不會落到「重查後仍待重算」，也不會落到「沒有任何欄位改變」。
- L381 的驗證允許「仍在本列 `pending_json`」，所以原樣帶入可以通過驗證，job_end 照寫。
- L417「本類只讀 `pending_json` 的上列欄位、`forecast_settle_eval` 與市場 DB 的 run，不讀 `forecast_record`、`forecast_outcome`」：觸發檢查看不到鏈尾已經作廢。被原樣帶入的項，`observed_through` 永遠不更新，L413「`observed_sessions_json` 含晚於該項 `observed_through` 的日期」在每一個新觀察日都成立，所以每天都會觸發一次。

**為什麼擋不住：**
- **交易邊界：** 只有 ③「寫入 `forecast_correction_job`……；commit」，以及 L378「寫入 job_end 時，在同一交易內驗證」。ADR 沒有任何字句規定 ④ 的 outcome／diag 寫入要和 job_end 同一個交易（已 Grep「同一交易」「同一個交易」確認）。L383 只要求 `correction_job_id` 指向 `forecast_correction_job`，不要求那個作業有 job_end。
- **中斷復原：** L367「由下一個作業完整重跑」，但重跑時作廢鏈尾不會重算（L1641），所以補不回來。
- **另一條同樣的路徑：** 寫入 job_end 時驗證不成立被拒（L366、L423 第 5 點、FL-64 (e) 的交錯），被拒之前已寫的列也會留下。
- **已承認的同類現象：** L3598 (三)「中斷作業（或 job_end 被拒的作業）已經寫入的 `forecast_void_late_diag` 列……」。

**影響範圍：**
- 畫面遮蔽 (a) 不受影響：L1589 比對的是鏈尾 `outcome_id`。
- N-29 (b) (i) 的 n 不受影響：L1591 中，`validation.py` 讀的是同一個以鏈尾為準的集合；作廢列本來就不計入 n，仍照常計入作廢率與 W。
- 受影響的是：§4.2 (7)「目前待重算」多算；每個新觀察日多跑一個作業、多一列 job_end。後者會讓 `e_changed_since` 翻為真（FL-68 (j)「job_end 寫入後 `e_changed_since` 為真」），可能在 `mask_episodes` 多出遮蔽期（推論，取決於作業和驗證快照的先後）。

### 2. 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A：④ 只算、不寫；⑤ 用單一短交易寫入 outcome＋diag＋job_end | 從根本解決：中斷或 job_end 被拒時，三張表都沒有該作業的列；L3598 (三) 與 `changed_count` 對不上表內列數這類問題一起消失；`e_read_outcome_seq` 與 job_end 序號在同一次 commit 變動，快照看不到做一半的更正 | 要在 D-9 第 5 點加一步；中斷時整段重算白做（依 L367 本來就要整段重跑）；非 X2 類更正要等作業做完才一次出現，原本是逐筆出現 | 實作者若改成「邊算邊寫、包在一個交易裡」，會變成長時間持鎖，所以字面明寫 ④ 不寫主 DB、⑤ 內不重算，並加 spy 測試格；寫入函式拒絕單一列時不得回滾整個交易 |
| B：扣除條件改為「鏈尾已不是 `tail_outcome_id`」 | 改動集中在一段；不論交易怎麼實作都不會永久卡住；同時涵蓋 job_end 被拒、並行作業的寫入 | 中斷作業留下的列照舊存在，L3598 (三) 照舊；只修 `pending_json` 這個症狀 | 若改成「不成立就拒絕寫入 job_end」，所有後續作業都會被拒，等於卡死（L3650 有前例），所以必須是扣除加 WARNING |
| A＋B（推薦） | A 讓 B 的條件照規格永遠不成立，B 成立就代表有程式錯誤，有 WARNING 可查；B 再加一條驗證「本列每一項的 `tail_outcome_id` 等於目前鏈尾」，qa 可以檢查 | 條文最多 | 低 |
| 否決：下一個作業重算作廢鏈尾 | — | 違反 R10-3（L1641） | — |

A＋B 之下：已完成的作業實質上依序進行（任一作業完成會推進至少一種 W，與它同起點的作業就會被 L366、L423 拒絕）；結算評估只寫 `supersedes_id IS NULL` 的列。所以 B 的扣除照規格不會發生（推論，依條文字面）。

### 3. 可直接貼入的字面

**(1) N32-1：D-9 第 5 點，新增 ⑤**

定位：④ 最後一個子點「       - 之後不再讀 `MAX(event_id)`、`MAX(check_id)`。」之後、「     - **理由**：」之前，與 ① 同一層插入：
```
     ⑤ （N-32；tech-architect 2026-10-18）寫入：④ 全部算完之後，才開啟主 DB 寫入交易（`BEGIN IMMEDIATE`），在同一個交易內依序寫入本作業的全部 `forecast_outcome` supersede 列與 `forecast_void_late_diag` 列，完成寫入 job_end 的全部驗證（D-3 `forecast_correction_job_end`、`forecast_void_late_diag`「計數一致」、「晚到資料的觸發」第 5 點），再寫入 `forecast_correction_job_end`；commit。
       - ④ 不寫主 DB。本交易內不重算，也不讀判定視圖以外的資料；持鎖時間只涵蓋寫入與驗證（比照 D-11.4 第 11 點 (c)「不採 (a)」的持鎖理由：預測帳有兩個寫入者）。
       - 寫入函式拒絕某一列時，只有該列不寫，列入 `rejected_json`（依 ④「待重算」同時列入 `pending_json`），交易繼續；不得因單列被拒而回滾整個交易。
       - 寫入 job_end 的任一驗證不成立，或交易途中拋例外、程序中斷時，整個交易回滾：本作業的 supersede 列、diag 列與 job_end 都不存在，該作業視為中斷，依 D-3 由下一個作業完整重跑。所以 `forecast_outcome.correction_job_id` 與 `forecast_void_late_diag.correction_job_id` 所指的作業，一定已有 `forecast_correction_job_end` 列。
       - 理由：中斷或 job_end 被拒的作業若已寫入列，D-3 `pending_json` 的扣除會漏掉該項而永久殘留（N-32），`void_late_data_count` 的合計也會少於 diag 表的筆數（本 ADR 修訂紀錄所錄風控 2026-10-18 疑義四項單項確認 suggested (三)）。
```

**(2) N32-2：D-3 `forecast_correction_job_end`，交叉參照**

定位：L367 該點中「qa 核對涵蓋率。」之後接：
```
依 D-9 第 5 點 ⑤（N-32），沒有 end 列的作業不會留下 `forecast_outcome` 或 `forecast_void_late_diag` 列。
```

**(3) N32-3：D-3 `pending_json`「內容 ＝」一點，整點取代**

被取代的原文：
> - 內容 ＝ 前一個已完成作業的 `pending_json`，扣掉本作業已為該 `forecast_id` 寫入 supersede 列的項，其餘原樣帶入；本作業新列入、或重查後仍待重算的項，以本作業的值取代（`since_job_id` 不變）。

新字句：
```
    - 內容 ＝ 前一個已完成作業的 `pending_json` 中，不屬於下列任一情形的項原樣帶入；本作業新列入、或重查後仍待重算的項，以本作業的值取代（`since_job_id` 不變），不適用下列扣除：
      - 本作業已為該 `forecast_id` 寫入 supersede 列；
      - 本作業重查後沒有任何欄位改變（§6.4 第 3 點，不寫列；與下方寫入 job_end 驗證第 3 子點、FL-68 (j) 一致）；
      - （N-32；tech-architect 2026-10-18）本作業沒有重查該項，而且在寫入 job_end 的交易內讀到的該 `forecast_id` 鏈尾已不是該項的 `tail_outcome_id`。依 D-9 第 5 點 ⑤ 這不應發生；發生時照樣扣除，記 WARNING（帶 `forecast_id`、`tail_outcome_id`、目前鏈尾的 `outcome_id` 與其 `correction_job_id`），不拒絕寫入 job_end。理由：鏈尾已換，該項記的 `tail_outcome_id` 不再是畫面與驗證統計所比對的列（D-11.4 第 11 點 (g) (a)）；若改為拒絕寫入 job_end，同一情形之後每次都成立，所有更正作業都會被拒（比照本 ADR 修訂紀錄 FL-64 (e) 的卡死路徑）。
```

**(4) N32-4：寫入 job_end 驗證第 3 子點整行取代，其後同一層新增一子點**

被取代的原文：
> - 前一個已完成作業 `pending_json` 的每一項，恰好落在下列之一：本作業為該 `forecast_id` 寫入 supersede 列；本作業重查後沒有任何欄位改變（§6.4 第 3 點，不寫列）；仍在本列 `pending_json`。

新字句：
```
      - 前一個已完成作業 `pending_json` 的每一項，恰好落在下列之一：本作業為該 `forecast_id` 寫入 supersede 列；本作業重查後沒有任何欄位改變（§6.4 第 3 點，不寫列）；本作業沒有重查、而且該 `forecast_id` 的鏈尾已不是該項的 `tail_outcome_id`（N-32，記 WARNING）；仍在本列 `pending_json`。
      - （N-32）本列 `pending_json` 每一項的 `tail_outcome_id`，都等於在本交易內讀到的該 `forecast_id` 鏈尾的 `outcome_id`。
```

**(5) N32-5：FL-68 (j) 之後新增 (k)**

定位：FL-68 (j) 整行之後、「- **FL-69**」之前：
```
  - (k)（N-32）交易邊界與中斷復原：在 ⑤ 的交易內、已寫入若干 supersede 列與 diag 列、尚未寫入 job_end 時注入例外 → 本作業在 `forecast_outcome`、`forecast_void_late_diag`、`forecast_correction_job_end` 都沒有列，supersede 列的 `outcome_id` 最大值不變；下一個作業完整重跑，寫入的列與沒有中斷時逐位相同（`outcome_id`、`diag_id`、`correction_job_id`、`computed_at` 除外）。寫入 job_end 的驗證不成立（W 已改變、交錯完成各一格）→ 三表同樣都沒有本作業的列。單列被寫入函式拒絕 → 只有該列不寫、列入 `rejected_json`，其他列與 job_end 照寫。④ 期間沒有開啟任何主 DB 寫入交易（spy）；⑤ 的交易內不呼叫重算函式與判定視圖的讀取函式（spy）。性質測試：任意中斷點之下，`correction_job_id` 非 null 的每一列 `forecast_outcome` 與每一列 `forecast_void_late_diag`，所指作業都有 `forecast_correction_job_end` 列。殘留防護：前一個已完成作業的 `pending_json` 只有一項 X，fixture 直接插入一列作廢列，supersede X 的 `tail_outcome_id`，其 `correction_job_id` 指向沒有 end 列的作業（模擬 ⑤ 以外的寫入）→ 下一個作業沒有重查 X 時，X 不在本列 `pending_json`，記 WARNING，job_end 照寫；把 X 原樣帶入的實作 → 拒絕寫入 job_end；之後新觀察日的結算評估不再產生 `pending_resettle` 觸發（spy）。同一 fixture 在下一個 job_end 之前寫 snapshot：X 的作廢列屬於 E 時，計入作廢率與 W，不因 X 仍在最近一列 `pending_json` 而被排除。本列 `pending_json` 某一項的 `tail_outcome_id` 不等於目前鏈尾 → 拒絕寫入 job_end。
```

**(6) 修訂紀錄條目**

定位：修訂紀錄末尾，N-29 批之後，新起一段：
```
**N-32 更正作業的寫入交易與 `pending_json` 扣除（2026-10-18）（D-3 `forecast_correction_job_end`、D-9 第 5 點、FL-68；掛 A-65（R10-3）；方向：逐項標示，見各項）**
- 依據：tech-architect 2026-10-18 N-32 提案（來源：`work/reviews/2026-10-18-V18-04辨認條件逐列可數確認-tech-architect.md` 第二節第 4 點；後續追蹤清單 N-32）；風控 2026-10-18 N-32 裁定〔待填〕。
- N32-1（D-9 第 5 點，④ 最後一個子點「之後不再讀 `MAX(event_id)`、`MAX(check_id)`。」之後、「**理由**」之前，新增 ⑤ 與其四個子點）：無被取代原文。方向：補定義（收緊）。CEO：否。連帶：本修訂紀錄所錄風控 2026-10-18 疑義四項單項確認 suggested (三)（中斷或 job_end 被拒的作業已寫入的 diag 列）自本條起不再發生；該段是歷史紀錄，原文不改。
- N32-2（D-3 `forecast_correction_job_end` 一點「qa 核對涵蓋率。」之後接一句）：無被取代原文。方向：不變（交叉參照）。CEO：否。
- N32-3（D-3 `pending_json`「內容 ＝」一點整點取代）：方向：補定義（不放寬）。新增的「鏈尾已換」扣除，只移除畫面與驗證統計都不再比對到的項；「重查後沒有任何欄位改變」一格是屬實性更正，使本點與同節驗證第 3 子點、FL-68 (j) 一致。CEO：否。被取代的原文——
  > - 內容 ＝ 前一個已完成作業的 `pending_json`，扣掉本作業已為該 `forecast_id` 寫入 supersede 列的項，其餘原樣帶入；本作業新列入、或重查後仍待重算的項，以本作業的值取代（`since_job_id` 不變）。
- N32-4（同節寫入 job_end 驗證第 3 子點整行取代，其後同一層新增一子點）：方向：收緊（驗證）。CEO：否。被取代的原文——
  > - 前一個已完成作業 `pending_json` 的每一項，恰好落在下列之一：本作業為該 `forecast_id` 寫入 supersede 列；本作業重查後沒有任何欄位改變（§6.4 第 3 點，不寫列）；仍在本列 `pending_json`。
- N32-5（FL-68 (j) 之後新增 (k)）：無被取代原文。方向：收緊（測試）。CEO：否。
```

### 4. 連帶影響（交 quant，都不必改字，請書面確認）

- **Q-a §4.2 (7)「目前待重算」：** 字面不改。修正後由最近一列 job_end 的 `pending_json` 數出的值即為正確。V18-04「前者／後者」的辨認條件不受影響。A 之下，我在 V18-04 確認裡寫的「中斷作業寫入的作廢列照樣在母集合」不再會出現。第二節第 3 點的時間界限 suggested 照舊可選。
- **Q-b N-29 (b)「至某次更正作業的判定視圖中」：** A 之下，中斷作業的到期判定不留下任何列，所以實際上只有寫入 job_end 的作業才算數。請確認不需改字。若 quant 要把這一點寫明，屬補定義，隨 N-29 (b) 一起處理，維持「事先宣告 N-29 (b) 版次不早於 ADR 的 N-29 批」。
- **Q-c 風控 suggested (三) 的 §4.2 (iv)：** 「沒有 end 列的作業寫入的 diag 列數」依 N32-1 恆為 0，quant 與風控可決定是否撤下這項 suggested。

### 5. 閘門判定

- **dirdef 凍結：不擋。** 前提是 quant 確認 Q-a、Q-b 都不改字。n 與 W 的計算以鏈尾 `outcome_id` 為準，不受影響。
- **dev-lead 實作更正作業：擋。** 與追蹤清單「dev-lead 實作更正作業前」一致。⑤ 決定 `run_correction_job()` 的交易結構，必須先定案。
- **使用者字面：** 不涉及。LM-155、`RECORD_STATUS_RESETTLE_PENDING` 與任何片段都沒改，creative-lead 不必參與。

## 三、驗證

- **讀過：**
  - ADR-0027：L340–439、L1094–1153、L1370–1399、L1584–1669、L2170–2185、L2273–2285、L3594–3598、L4056–4145；
  - 追蹤清單 N-29～N-32 列；
  - V18-04 TA 確認全文；
  - 事先宣告草案 L76–85、L848（作廢數整格）、L1440（N-29 (b)）。
- **Grep 確認的事實：**
  - ADR 沒有 outcome／diag 寫入與 job_end 同一交易的字句；
  - L377 與 L381、FL-68 (j) 在「沒有任何欄位改變」一格不一致；
  - 修訂紀錄最後一批是 N-29 批（L4062）。
- **推論、未實測：**
  - 卡住路徑與「每日觸發」；
  - mask 遮蔽期是否增加；
  - A＋B 之下 B 照規格不會成立。
- **沒有做的事：** 只用了 Read、Glob、Grep，沒有改任何檔案，沒有讀 `.env` 或 `*.db`，沒有跑測試。

## 四、下一步

1. **coordinator：** 把本提案送風控裁定 N32-1～N32-5，含 N32-3 中的屬實性更正。若風控只採一個方案：只採 B，要保留 N32-3、N32-4、(k) 的殘留防護格，刪 N32-1、N32-2 與 (k) 的交易格；只採 A，則 N32-3 的第三格與 N32-4 的新增子點都要刪，否則沒有防護。
2. **quant：** 對 Q-a～Q-c 書面確認不改字。
3. **風控裁定後：** tech-writer 依第二節 3 從檔尾往前套用。dev-lead 依 ⑤ 與 FL-68 (k) 實作。qa-reviewer 以 (k) 的 spy 格與性質測試驗收。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/reviews/2026-10-18-V18-04辨認條件逐列可數確認-tech-architect.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md

# ADR-0027 套用疑義裁定（tech-architect）

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

五項都已裁定，每項附可直接貼上的字面與定位字串。我沒有改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有跑 git。

1. **疑義 1（表數）**：`forecast_void_late_diag` 要計入。全部表數由 15 改成 16，M-11 的新增表數由 10 改成 11。CEO 待決第 9 點是第九、十批的歷史紀錄，原文不改，另加第 10 點。決策包二補遺另加第 14 項，第 12 項只在句尾加更新註。語意不變，不必送風控。
2. **疑義 2（出處）**：引用「ADR-0016 D-5.2」是錯的，而且錯在架構面。
   - ADR-0016 D-5.2 是持倉鏈的覆蓋判定來源，讀的是主 DB 的 `dividend_sync_runs`。預測鏈依 ADR-0027 D-4 第 2 點，讀的是市場 DB 的 `pit_dividend_announce_rows`；FL-5 也禁止 `app/forecast/**` 出現 `dividend_events`。照這個引用去實作，會越過模組邊界。
   - 這個錯誤出自 data-engineer 查證檔 L108，風控沿用。
   - 正確出處是 D-11.4 第 11 點 (h)：`OUTCOME_CORRECTION_CAUSES` 第 4 類 `dividend_factor_corrected`（L1165），以及同點「原因怎麼歸屬」（L1169）。
   - **另有一個更大的問題**：「因子修訂」觸發在全文都沒有偵測定義。我 Grep「因子修訂」，只出現在 L315、L327、L349、L1169，事先宣告也只有 L762 一處。結果有兩個：
     - R-11 第 6 點說「因子晚到有觸發涵蓋」，目前不屬實；
     - 第 4 類更正原因本身也永遠不會被觸發。
   - 我建議採甲版字面：定義落地前，`dividend_factor` 標「未涵蓋，不計」。這會改變語意，要送風控，而且要和 quant 的 v0.13 V13-08（L762）同批。
3. **疑義 3（存放處）**：採甲案，放在 `forecast_correction_job` 欄位。核心欄位語意不變；另附一個選用欄位，那個會改變語意。
4. **疑義 7（A-28 (ii)）**：要以〔取代〕方式更新 A-28 (ii)（L1226），補上 `cause`。
   - (a) 補欄位只是同步 N5-2，語意不變。
   - (b) 兩個原因同時成立時取哪個值，以及 `positive_suppressed_during_f3` 的適用範圍，屬補定義（收緊），建議併送風控。
5. **疑義 9（FL 格）**：要補，新增 **FL-64**，放在 FL-23 之後。這些格只檢查既有條文，不改變語意。
6. **順便發現**：風控 R-11 第 5 點的去重規則和「中斷作業由下一個作業完整重跑」互相衝突。照字面，作業一旦中斷，後續作業會永久卡住。改法見第二節，這是改風控的逐字字句，必須送風控單項確認。

## 二、各部門回報（tech-architect）

### 第 1 項：表數

**計數口徑**：D-3 列出的每一張主 DB 表（含 `plan_*`），合計 16 張：
- `forecast_run`、`forecast_run_end`、`forecast_scope_snapshot`、`forecast_input_series`
- `forecast_record`、`forecast_outcome`、`forecast_correction_job`、`forecast_correction_job_end`
- `forecast_void_late_diag`、`forecast_replay`、`forecast_gaps`、`forecast_claim_registry`
- `forecast_validation_snapshot`、`forecast_ledger_events`、`plan_record`、`plan_outcome`

M-11 的新增數 ＝ 16 減去 ADR-0025 D-6.1（L377-382）原有的五張，等於 11。這和先例一致：13 張時是新增 8 張，15 張時是新增 10 張。

diag 表必須計入，理由有三：它是 `forecast_*` 主 DB 表；受 D-2 第 2 點的 trigger 管；要以 component `forecast` 走遷移。「代價」那一句講的正是遷移與測試成本。

全文 Grep「張」「表數」，需要改的只有下列四處。L2850-2858 是已 commit 的被取代原文，不動；事先宣告與 work/research 沒有表數敘述。

| 位置（定位字串） | 新字面 |
|---|---|
| L89「`- 表數多（15 張），寫入規則有一部分在 trigger 裡。`」 | `- 表數多（16 張），寫入規則有一部分在 trigger 裡。` |
| L202 M-11 列內「`新增 10 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`）`」 | `新增 11 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`；剩餘待決項 N-4 加 `forecast_void_late_diag`）`（該列其餘不變） |
| L1506「`- 15 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。`」 | `- 16 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。` |
| L1982「`9. （第九、十批，A-79）M-11 的表數隨第九、十批由 8 張改為 10 張（知悉）。`」 | 原文不改，緊接其後新增：`10. （剩餘待決項，N-4）M-11 的表數隨 `forecast_void_late_diag` 由 10 張改為 11 張；全部表數由 15 張改為 16 張（知悉）。` |

**修訂紀錄**：在 N-4 段末新增一條。

```
- 本批（2026-10-18，tech-architect 疑義裁定第 1 項；方向：不變）：表數隨 `forecast_void_late_diag` 加 1。計數口徑：D-3 列出的每一張主 DB 表（含 `plan_*`）；M-11 的新增數為其減去 ADR-0025 D-6.1 原有的五張。評估摘要「最大代價」原文——
  > - 表數多（15 張），寫入規則有一部分在 trigger 裡。

  Consequences「代價與壞處」原文——
  > - 15 張表，加上 trigger 與部分唯一索引，遷移與測試成本高。

  M-11 列原文（修訂清單表）——
  > 〔逐字貼入目前 L202 整列〕

  改為 16 張表；M-11 改為新增 11 張表；CEO 待決事項第 9 點原文不改，另加第 10 點（知悉）。
```

**決策包二補遺**（`/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`）：
- 第 12 項句尾，接在「…第 2 項。」之後加：`〔2026-10-18 更新：剩餘待決項 N-4 再加 1 張，現為 11 張，見第 14 項〕`
- 在第 13 項之後新增：

```
14. **ADR-0027 M-11 的新增表數再由 10 張改為 11 張（知悉）**：剩餘待決項 N-4 為了記錄「作廢之後才補到資料」的診斷結果，加了 `forecast_void_late_diag` 一張只增不改的表。它不影響任何統計、狀態或畫面，只供驗證報告揭露。全部表數由 15 張改為 16 張。來源：`work/reviews/2026-10-18-ADR-0027-剩餘待決項N3至N9與起算日提案-tech-architect.md` N-4；tech-architect 2026-10-18 疑義裁定第 1 項。
```

### 第 2 項：R-11 第 6 點的出處

**定位**：L349 內的「`除權息因子晚到走「因子修訂」觸發（ADR-0016 D-5.2）；`」。全文 Grep「D-5.2」只有這一處。

**甲版（建議；改變語意，要送風控，並和 v0.13 同批）**：整段取代為

```
除權息因子晚到應由「因子修訂」觸發涵蓋（D-11.4 第 11 點 (h)：`OUTCOME_CORRECTION_CAUSES` 第 4 類 `dividend_factor_corrected`，以及同點「原因怎麼歸屬」所列的因子修訂觸發；事件來源依 D-4 第 2 點，是市場 DB 的 `pit_dividend_announce_rows`，不是 ADR-0016 D-5.2 的主 DB 同步紀錄）。該觸發的偵測方式尚未定義（後續追蹤清單 N-17），定義落地之前，`dividend_factor` 視為沒有觸發涵蓋；
```

- **送風控的理由**：把 `dividend_factor` 從「有涵蓋」改成「未涵蓋，不計」。這是改風控的逐字字句，而且 v0.13 V13-08（事先宣告 L762）「以及經因子修訂觸發的除權息因子」要由 quant 同批改：刪掉這句，把 `dividend_factor` 列入不涵蓋清單，並註明「因子修訂觸發的偵測定義落地前」。
- **N-17 建議列**（交 coordinator 加到 `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`）：

```
| N-17 | 「因子修訂」觸發（D-11.4 第 11 點 (h) 第 4 類 `dividend_factor_corrected`）沒有偵測定義：誰偵測、讀哪種 run、怎麼配對、晚到怎麼判定。影響 `dividend_factor` 晚到的涵蓋，以及 resolved 列的因子更正 supersede | data-engineer 先查 `pit_dividend_announce_rows` 的 run 結構 → tech-architect 提案（比照 R-11 的讀端輪詢）→ 風控 | D-9 結算程式實作前；定義前 `dividend_factor` 標「未涵蓋，不計」 | tech-architect 2026-10-18 疑義裁定第 2 項 |
```

**乙版（最小改動；只修出處）**：只把「（ADR-0016 D-5.2）」換成

```
（D-11.4 第 11 點 (h)：`OUTCOME_CORRECTION_CAUSES` 第 4 類 `dividend_factor_corrected`；事件來源依 D-4 第 2 點）
```

- 只換出處本身不改語意。但這是風控逐字字句，照風控第 277 行，仍要單項確認。
- 我不建議採乙版：條文會繼續宣稱一個不存在的觸發有涵蓋。§4.2 的 `dividend_factor` 會因此以 0 呈現，正是 R-11 第 6、7 點要防的情形。

**修訂紀錄**：兩版都要把原括號逐字保留，掛在 N-4 段：

```
- 本批（tech-architect 疑義裁定第 2 項；風控單項確認〔待〕）：「晚到資料的觸發」第 6 點原文——
  > 除權息因子晚到走「因子修訂」觸發（ADR-0016 D-5.2）；

  改為見 §D-3「晚到資料的觸發」第 6 點。理由：ADR-0016 D-5.2 是持倉鏈的覆蓋判定來源（主 DB `dividend_sync_runs`）；預測鏈的除權息事件依 D-4 第 2 點取自市場 DB，FL-5 禁止 `app/forecast/**` 讀主 DB 的 `dividend_events`。〔甲版另加：「因子修訂」觸發在本 ADR 沒有偵測定義，列後續追蹤清單 N-17〕
```

### 第 3 項：`market_scan_from`／`market_scan_to` 存放處

**裁定：採甲案。** 理由：
- 掃描範圍在作業開始時就確定（第 2 點只取一次 `run_max`），第 5 點的鏈接驗證也必須在作業開始時做。
- 乙案不行：`triggers_json` 是觸發陣列，不是標頭。
- 丙案不行：job_end 在作業結束時才寫，作業開始時無從驗證。

**(3a) 語意不變（落實 R-11 第 2、5、8 點既有用語）**

定位一：L315 的「`forecast_correction_job(correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT, triggers_json, recheck_range_json, started_at)`」，取代為

```
`forecast_correction_job(correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT, triggers_json, recheck_range_json, market_scan_from INTEGER NOT NULL, market_scan_to INTEGER NOT NULL, started_at)`
```

定位二：在同一行行末「沒有觸發就拒絕執行。」之後換行，新增子點：

```
    - （N-4；晚到資料的觸發第 2、5、8 點）`market_scan_from`、`market_scan_to`：本作業啟動時 `scan_late_market_bars()` 的掃描範圍 (`market_scan_from`, `market_scan_to`]，以市場 DB 的 `run_id` 表示。作業開始時與 `triggers_json` 在同一個交易內寫入，由寫入函式自行填入，不接受呼叫端傳入。
      - `market_scan_from` ＝ W，也就是 `correction_job_id` 最大、而且已有 `forecast_correction_job_end` 列的作業的 `market_scan_to`；沒有這樣的作業時為 0。
      - `market_scan_to` ＝ 該次掃描取得的 `run_max`；還原保護（第 8 點）成立時，`market_scan_to` ＝ `market_scan_from` ＝ W。
      - 寫入驗證（不成立就拒絕寫入）：`market_scan_from` 等於上述 W；`market_scan_from ≤ market_scan_to`。
      - 不放 `triggers_json`（它是觸發陣列，不是標頭），也不放 `forecast_correction_job_end`（第 5 點的驗證在作業開始時就要做）。
```

**(3b) 選用；改變語意（新增欄位），採用的話併送風控**

不加這一欄的話，第 8 點「§4.2 揭露該期間…可能不完整」的「該期間」只能靠 log 判斷，無法由 DB 逐列數出。

- 欄位清單在 `market_scan_to INTEGER NOT NULL` 之後再加 `, market_scan_restore_suspected INTEGER NOT NULL CHECK (market_scan_restore_suspected IN (0,1))`；
- (3a) 子點末尾加一句：`第 8 點成立時 `market_scan_restore_suspected` ＝ 1，否則為 0；§4.2「可能不完整」的期間，由這一欄為 1 的作業逐列數出。`

**修訂紀錄**：
- L2950「本批沒有套用的 suggested 項目」那句，刪去「；N-4 的 `market_scan_from`／`market_scan_to` 做成 `forecast_correction_job` 的欄位」，句末加：`N-4 的 `market_scan_from`／`market_scan_to` 做成 `forecast_correction_job` 欄位一項，已由 tech-architect 疑義裁定第 3 項採用，見 N-4 段。`
- N-4 段新增一條：`- 本批（tech-architect 疑義裁定第 3 項；採風控 R-11 suggested 的作法；方向：補定義（收緊））：D-3 `forecast_correction_job` 欄位清單原文——> `forecast_correction_job(correction_job_id INTEGER PRIMARY KEY AUTOINCREMENT, triggers_json, recheck_range_json, started_at)` 改為見 §D-3（加 `market_scan_from`、`market_scan_to` 與其子點）。`

**附帶：R-11 第 5 點的衝突（改風控逐字字句，必須送風控單項確認）**

現行字面是「同一個 `(run_id, recorded_at)` 不得出現在兩個作業的 `triggers_json`」。它和兩條規則相撞：
- D-3 L316：中斷作業由下一個作業完整重跑；
- 第 2 點：W 不因中斷作業前進。

結果是：下一個作業必然重新掃到同一批觸發，寫入被拒，以後每個作業都寫不進去，其他觸發也一起被擋。

定位：L348「`同一個 `(run_id, recorded_at)` 不得出現在兩個作業的 `triggers_json`。`」，建議取代為

```
同一個 `(run_id, recorded_at)` 不得出現在兩個已有 `forecast_correction_job_end` 列的作業的 `triggers_json`：作業開始時對照已完成的作業驗證；寫入 job_end 時再驗證一次，不成立就拒絕寫入 job_end（該作業視為中斷，依 D-3 由下一個作業完整重跑）。沒有 end 列的中斷作業的觸發，由下一個作業依第 2 點重新掃得，不受此限。
```

### 第 4 項：A-28 (ii) 與 N5-2 的 `cause`

**裁定：以〔取代〕方式更新 A-28 (ii)。** N5-2 寫「記法比照 A-28 (ii)」，被比照的那一處卻沒有這個欄位，qa 無法逐條核對。

**(4a) 語意不變（同步 N5-2，風控已核可的欄位）**

定位：L1226「`- 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}}`；`」，取代為

```
- 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}, cause ∈ {suspended_f3, db_restored}}`（`cause` 必填；`db_restored` 依 D-11 第 2 點 N-5 甲案）；
```

**(4b) 補定義（收緊），建議併送風控**

定位：上一行之後、L1227「有 `withdraw` 區塊時」之前，新增：

```
- （N-5 甲案；`cause` 的取值）同一個檢查點兩個原因同時成立時，`cause = suspended_f3`（與第 12 點的優先序一致）。`cause` 只供稽核與 quant 的檢查點檢討紀錄使用；§4.2「因本點而不認列的檢查點」（D-11 第 2 點 N-5 甲案）依 `restore_checkpoint_bound` 判定，不依 `cause`，所以兩個原因同時成立的檢查點兩邊都計入。下一點的 `positive_suppressed_during_f3` 只在 `suspended_f3` 成立時設定，不因 `db_restored` 而設定。
```

**修訂紀錄**：N-5 段新增

```
- 本批（tech-architect 疑義裁定第 4 項；方向：(4a) 不變，(4b) 補定義（收緊））：A-28 (ii) 原文——
  > - 計算出來的原始結果放在 `stats_json.raw_checkpoint_result`，另記 `stats_json.suppressed_positive = {checkpoint_n, kind ∈ {upgrade, relist}}`；

  改為見 §D-11 第 4 點第 12 項 (ii)（加 `cause`，並新增取值一點）。
```

### 第 5 項：R-11 觸發本身的 FL 格

**定位**：L1657「`- **FL-23**：更正作業涵蓋所有結算窗與受影響日期有交集的列，不多不少。`」之後新增。目前最大號是 FL-63，所以用 FL-64。這些格只檢查既有條文，不改變語意。(e) 第四格和 (f) 的 `dividend_factor` 取決於第 2、3 項的裁定結果。

```
- **FL-64**（N-4；掛 A-65（R10-3）；D-3「晚到資料的觸發」第 1～8 點）：fixture 用離線的假市場 DB 與主 DB。
  - (a) 誰偵測（第 1 點）：
    - 呼叫點列舉（AST）：`scan_late_market_bars()` 只在每日結算之後與更正作業啟動時被呼叫；
    - 市場 DB 只經 `MarketPanelReader.ok_bars_runs_between` 讀取；`app/forecast/**`、`app/outlook/**` 不另開市場 DB 連線，也不出現它的路徑字串（grep，比照 ADR-0012 T-3）；
    - `pit_snapshot`、`MarketPanelStore` 不 import `app.forecast.*`，也不開主 DB（import graph）；
    - 沒有命中、也沒有其他觸發 → 不寫 `forecast_correction_job`。
  - (b) 掃描範圍（第 2 點）：
    - W 等於 `correction_job_id` 最大、而且有 end 列的作業的 `market_scan_to`；沒有這樣的作業時為 0；
    - 兩端各一格：`run_id = W` 不取，`run_id = run_max` 取；
    - 掃描中注入 `run_id > run_max` 的新 run → 本次不取，下一次取得；
    - 過濾各一格，都不產生觸發：`kind ≠ 'bars'`；`status ≠ 'ok'`；`session_date IS NULL`；`is_final(TW, session_date, recorded_at)` 為假。AST 斷言掃描函式不直接比較 `recorded_at` 與任何時間值。
  - (c) 配對（第 3 點）：
    - 三項都成立 → 恰好一個觸發項；
    - 三項各自不成立各一格，都不產生觸發：鏈尾 `status = resolved`；`session_date` 不在 [T, T+h]；該標的在該 run 沒有 `market_daily_bars` 列；`run_id ≤ settle_source_run_max`（含相等一格）；
    - 族群：成員在該 run 有列 → 觸發；非成員有列 → 不觸發。
  - (d) `settle_source_run_max`（第 4 點）：
    - 寫入函式的簽章沒有這個參數（AST）；
    - 值等於寫入當下假市場 DB 的 `MAX(run_id)`；大盤列為 null，個股與族群列非 null；
    - 注入倒退的 store 時鐘，觸發結果逐位相同。
  - (e) 觸發項與鏈接（第 5 點）：
    - `source_revision` 項恰有 `kind`、`run_id`、`recorded_at`、`session_date` 四鍵；
    - `market_scan_from` ≠ W → 拒絕寫入；
    - 同一個 `(run_id, recorded_at)` 出現在兩個已完成作業 → 拒絕；
    - 中斷作業（沒有 end 列）之後的下一個作業：`market_scan_from` 等於中斷作業之前那個已完成作業的 `market_scan_to`，重新掃得同一批觸發，可以寫入並寫完 job_end。
  - (f) 涵蓋邊界（第 6 點）：
    - 大盤作廢列，注入晚到的指數 T+h bar → 不產生 `source_revision` 觸發；
    - §4.2 報表對沒有觸發涵蓋的組合輸出「未涵蓋，不計」，不輸出 0：大盤 × {`t_plus_h_bar`, `settlement_close`}；三個 scope × `basket_member`；〔第 2 項採甲版時〕三個 scope × `dividend_factor`。即使 `forecast_void_late_diag` 沒有任何列也一樣；
    - 對照格：個股 × `t_plus_h_bar` 沒有列時輸出 0。
  - (g) 還原保護（第 8 點）：W 大於假市場 DB 的 `MAX(run_id)` →
    - 記 WARNING，不產生任何 `source_revision` 觸發；
    - 有其他觸發時作業照常啟動，而且 `market_scan_from = market_scan_to = W`；
    - 下一次掃描的 W 不變；`ok_bars_runs_between` 不被以 0 或目前的 `MAX(run_id)` 為下界呼叫（不重掃）。
  - 第 7 點是預期量，不是規則，不設格；第 9 點（O-1）待 O-1 定案時同批補格。
```

**修訂紀錄**：N-4 段新增 `- 本批（tech-architect 疑義裁定第 5 項；方向：補定義（收緊））：新增 FL-64，無被取代原文。`

### tech-writer 套用與我的提案相比（只列出，不重審）

- N-3、N-4（diag 表）、N-5、N-6、N-9、N-12、起算日：條文都與我的提案逐字相符。位置的差異 coordinator 已裁定接受（疑義 4、8）。
- 與提案不符、或我這次新發現的問題：
  1. L2950「未套用的 suggested」清單：第 3 項採用後，這句就不屬實。字面已在第 3 項給出。
  2. R-11 第 5 點的中斷作業衝突，見第 3 項附帶。這是風控字句，不是 tech-writer 的錯。
  3. 「因子修訂」觸發沒有偵測定義，見第 2 項。這是我原 N-4 提案就有的遺漏：我的 `late_data_refs_json` 寫了「因子修訂的參照」，卻沒有核對這個觸發是否已有定義。
  4. 小事，不擋：
     - 沒有命中時 W 不前進，掃描範圍會隨時間變大。這不影響正確性，因為舊 run 對之後才寫入的作廢列，不滿足 `run_id > settle_source_run_max`。
     - D-7 第 2 點的執行順序（記錄 → 結算 → 缺日稽核 → 驗證快照 → plan）沒有列出掃描與更正作業的位置。建議日後補在「結算」之後、「驗證快照」之前，讓 R10-7「作業完成後的第一筆 daily snapshot」在同一晚生效。

## 三、驗證

- 已讀：
  - ADR-0027 工作樹 L1-370、L370-381、L430-509、L667-710、L740-779、L940-964、L1100-1241、L1440-1464、L1495-1544、L1595-1669、L1680-1691、L1796-1805、L1884-1943、L1970-2049、L2820-3000；
  - ADR-0025 L376-382；ADR-0016 L100-164；
  - tech-writer 套用回報全文；我的兩份提案全文；
  - 風控審查（Grep：R-11、`market_scan`、「因子修訂」）；
  - data-engineer `/home/user/AICompany/work/reviews/2026-10-18-晚到資料觸發與F-8前提查證-data-engineer.md` L60-174（ADR-0016 D-5.2 的引用出自 L108）；
  - 決策包二補遺全文；後續追蹤清單 Grep（目前最大號是 N-16）。
- Grep：
  - ADR-0027 全文的「張」「表數」、`forecast_*`／`plan_*` 識別字、「因子修訂」「因子」、`D-5.2`、`suppressed_positive`、`positive_suppressed_during_f3`、`candidate_t_x2`、`claim_dv`、`mask_episodes`、FL 編號；
  - work/research 的「因子修訂」（只有 L762）。
- 沒有做的事：沒有跑 git 和測試，沒有讀 `.env` 或 `*.db`，沒有改任何檔。`pit_dividend_announce_rows` 的 run 結構沒有查證，列為 N-17 的前置工作，交 data-engineer。

## 四、下一步

1. **送風控單項確認（一包）**：
   - 第 2 項甲版（含 N-17）；
   - R-11 第 5 點的中斷作業修訂；
   - 第 3 項 (3b)，如果採用；
   - 第 4 項 (4b)。
2. **quant**：第 2 項若採甲版，v0.13 V13-08（L762）同批改涵蓋句，否則 ADR 和事先宣告會不一致。
3. **tech-writer**：風控確認之前，可以先套語意不變的部分：第 1 項、第 3 項 (3a) 與 L2950、第 4 項 (4a)、第 5 項 FL-64。第 2 項、R-11 第 5 點、(3b)、(4b) 等風控確認後再套。全部仍和 v0.13 同批，不得單獨 commit。
4. **coordinator**：
   - 決策包二補遺第 12 項加更新註、新增第 14 項；
   - 後續追蹤清單新增 N-17；
   - 同批機械核對時加比對：ADR L349 和 v0.13 L762 的涵蓋清單一致，以及 FL-64 (f) 列出的組合和第 6 點一致。
5. **data-engineer**：N-17 的前置查證，包括 `pit_dividend_announce_rows` 的 run 種類與 `run_id` 序號是否和 bars run 共用 `pit_snapshot_runs`。

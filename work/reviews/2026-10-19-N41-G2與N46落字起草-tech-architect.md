# N-41（G-2 ADR 側）、N-46、N-49 落字起草

- 審查者：tech-architect
- 日期：2026-10-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. **N-41（G-2 的 ADR 側）**：已起草 D-9 第 6 點的子點與 FL-72，字面與事先宣告 v0.22 §6.3 V22-07 一致。起草時發現一個**擋 N-41 的衝突，要同批修**：ADR-0027 D-3 對 `band_def` 的寫入驗證（L287-292）沒有依 label 分開適用。照字面，缺 `sigma_d` 的證據不足預測根本寫不進 `forecast_record`，V22-07 描述的列不會出現，也違反事先宣告 §5.1 第 4 點「證據不足的預測也寫入紀錄帳」。所以 N-41 的落字必須連 D-3 的「適用範圍與缺項」一起改，不能只改 D-9。
2. **N-46（有標籤的預測缺項）**：
   - 現行條文**不能完全排除**這種情形：寫入驗證保證不了 `EPS` 存在，也沒把 `K_h` 釘在 dirdef 常數。
   - 我提的規則分兩道：
     - 寫入端：在 D-3 加驗證，有標籤的列缺項就拒寫，拋新型別 `LabeledThresholdSnapshotIncompleteError`；
     - 結算端與更正端：用同一個判定函式做防禦性斷言，成立時整次評估不寫入（fail-closed）。
   - 告警走 ADR-0029 既有的 E-3d `forecast.step.failed`，不新增事件。使用者面沿用既有的「持續失敗期間」與缺日路徑，不新增文案。
   - 加上寫入端驗證之後，結算端只有在寫入驗證被繞過時才會碰到。證明路徑附在 N-46 段。
3. **N-49（不擋）**：FL-47 的導出式本身會自動跟著 D-11.2 的 `eval_key = n{n}` 走。但括號「（即 LG-20）」已經說得太滿：LG-20 在 v0.22 多了兩句，FL-47 測不到。建議改字，並補兩個 `n{n}` 的對抗格。
4. 全部屬 ADR-0027 字面，**擋 D-9**（N-49 除外），要送風控逐字確認。CEO 層級的建議逐項標在下面，由風控裁定。

---

## 各部門回報（tech-architect）

### 一、N-41：證據不足的預測照常結算

**落字 1-A：D-9 第 6 點加子點**
- 插入點：`6. 逾時與 on-demand 的紀錄也照常結算，供紀錄清單列示。`（全檔 1 處，已 grep 確認）的下一行，作為第 6 點的子點（縮排 3 格加「- 」）。
- 方向：補定義（不變：消除歧義），比照風控對 V22-07 的裁定。CEO：否。擋 D-9。
- 逐字：

```
   - （N-41；G-2；事先宣告 v0.22 V22-07）**證據不足的預測照常結算**：
     - 證據不足（`label = insufficient`）的預測同樣結算：評估集合 U 不依 label 篩選（第 2 點 ②），結算、等待或作廢的判定不讀 label（第 2 點「全量評估」、第 3 點「判定順序」）。`status` 依一般規則記為 `resolved` 或作廢。
     - `threshold_snapshot`（`band_def`）缺項時（`threshold_inputs()` 回傳 None，D-3 `forecast_record` 判定材料「適用範圍與缺項」），`realized_z`、`realized_label`，以及要用到這兩者或同一組門檻的欄位（`hit`、`baseline_hits_json`、`diag_open_based_json`、`diag_last_close`、`index_return_diag`、`diag_basket_with_excluded`）一律記 null；不用門檻的欄位（`realized_log_return`、`realized_return`、`mae`、`mfe` 等）依一般規則照常計算。
     - 不得以結算時重算的 σ_d、其他預測的門檻或任何代入值補上（重算會用到 cutoff(T) 之後的資料，也違反事先宣告 §6.3「σ 用預測當時存下的 σ_d(T)，不重算」）；也不得因缺項而拋出例外或不寫入 outcome 列。結算評估與更正作業都不呼叫 `app/outlook/volatility.py` 的 `sigma_d()`（AST）。
     - `threshold_snapshot` 完整的證據不足預測，照常以該列的 `threshold_snapshot` 計算 `realized_z`、`realized_label`；`hit` 依事先宣告 §6.3 `hit` 列記為 null。
     - 本點不改任何判定。證據不足的預測不計入 n，只計入涵蓋率（事先宣告 §4.1 V9-06），所以這些欄位不是 n、命中率、§4.3 任何判定的輸入；W 對作廢列一律依規則記命中與否（事先宣告 §4.2），也不讀這些欄位。
     - 欄位怎麼填，由 `scoring.py` 建 outcome 列的單一函式依 `threshold_inputs()` 決定。label 只在這個函式（`hit` 與本點的 null 欄位）與下一子點的守衛中讀取；第 2 點的等待判定與第 3 點的 `void_reasons()` 照舊不讀 label（AST）。
     - **只適用於證據不足的預測**：有標籤的預測（`label ≠ insufficient`）不適用本點，不得比照本點記 null 照常寫入（事先宣告 §6.3 v0.22 註末句）；處理見下一子點。
     - `forecast_outcome` 的寫入驗證（結算評估與更正作業的寫入函式都適用；任一項不成立就拒絕寫入）：
       - `label = insufficient`、而且 `threshold_inputs()` 為 None ⇒ 上列八個欄位全部為 null；
       - `label = insufficient` ⇒ `hit` 為 null；
       - `label ≠ insufficient`、而且 `status = resolved` ⇒ `realized_z`、`realized_label`、`hit` 都非 null。
```

- 與 V22-07 的對照：
  - 【事實：讀事先宣告 L1531】V22-07 的括號列的是 `hit`、`baseline_hits`、`diag_open_based`、`diag_last_close`、`index_return_diag`。ADR 依 D-3 的欄位名寫成 `_json` 後綴，屬於名稱對照，語意不變。
  - **差異一處，要風控與 quant 確認**：我多列了 `diag_basket_with_excluded`（就是事先宣告的 `diag_basket_last_close`）。
    - 【事實：讀 L1542】它是「被排除成員放回籃子算出的診斷標籤」，要用同一組門檻；
    - 【推論】它落在 V22-07「要用到……同一組門檻的欄位」的原則內，只是括號沒列。缺 σ_d 時，不補值就算不出來，所以只能是 null。
    - 建議 quant 在 v0.23 把它補進 V22-07 的括號；或由風控裁定，ADR 依原則列入即可。
  - 寫入驗證三項比 V22-07 多做一件事：用驗證把 null 路徑封住，屬收緊。V22-07 原本就禁止有標籤者比照，這三項不改它的語意。

**落字 1-B：D-3 `forecast_record` 寫入驗證，加「適用範圍與缺項」**
- 插入點：`以同一個函式，用同列的 {`K_h`, `sigma_d`, h} 重算，結果逐位相等。`（全檔 1 處）的下一行，和「**寫入驗證**」同一層（縮排 4 格加「- 」）。
- 方向：**補定義（兩面）**。
  - 收緊面：常數比對、有標籤者的完整性（N-46）。
  - 放寬面（照實並陳）：相對 D-3 現行字面，「證據不足而且缺項」的列原本會被拒寫，改為可以寫入，五項不適用。這是相對一個與事先宣告 §5.1 第 4 點、V22-07 衝突的字面讀法而言。
  - CEO：建議知悉，由風控裁定。理由：被取代的讀法會把證據不足的預測變成缺日，這個做法從未核可過，和風控 (b) 裁定「放寬面只相對未核可的設計」同型。
- 擋 D-9（也擋記錄一步的寫入驗證實作）。
- 逐字：

```
    - （N-41、N-46；事先宣告 v0.22 V22-07）**適用範圍與缺項**：
      - 「缺項」與「完整」只由 `app/forecast/band.py` 的單一純函式 `threshold_inputs(band_def) -> ThresholdInputs | None` 判定：`K_h`、`EPS`、`sigma_d` 任一個鍵不存在或值為 null，或 `sigma_d` 不是正的有限值（`math.isfinite(sigma_d) and sigma_d > 0` 不成立）時，回傳 None，稱為缺項；否則回傳 `ThresholdInputs{K_h, EPS, sigma_d}`，稱為完整。這是事先宣告 §6.3 v0.22 註（V22-07）「缺 `K_h`、`EPS`、`sigma_d` 任一項，或 `sigma_d` 不是正的有限值」的唯一實作。
      - 不論 label：`K_h`、`EPS` 非 null 時，必須與該列 `definition_version` 所登記 dirdef 的常數（該 h 的 K、`EPS`）逐位相等。
      - `label ≠ insufficient`：`band.py` 的單一純函式 `labeled_snapshot_violations(band_def, *, horizon, definition)`（`definition` 是該列 `definition_version` 所登記的 dirdef）必須回傳空 tuple，上方五項也必須成立；不成立時拒絕寫入，拋 `LabeledThresholdSnapshotIncompleteError`（D-9 第 6 點 N-46 子點）。違規值是封閉列舉，依序為 `k_h_missing`、`k_h_mismatch`、`eps_missing`、`eps_mismatch`、`sigma_d_missing`、`sigma_d_not_positive_finite`、`sigma_d_below_floor`（`sigma_d` 小於該版 dirdef 的 `SIGMA_FLOOR`）、`valid_returns_below_min`（`valid_returns` 為 null，或小於該版 dirdef 的 `SIGMA_MIN_VALID`）；回傳值依此順序排列、不重複。有標籤的預測不得以缺項寫入，也不得改記 `insufficient` 或補值後寫入。
      - `label = insufficient`、而且完整：上方五項照常適用。
      - `label = insufficient`、而且缺項：上方五項不適用；`up_pct`、`down_pct` 必須同為 null（事先宣告 §5.1 第 3 點：不得以替代估法補資料）；其餘鍵照預測端實際算得的值存，算不出的記 null。
      - 理由：上方五項對缺 `sigma_d` 的列無法成立；照字面不分 label 適用，證據不足的預測會被拒寫，違反事先宣告 §5.1 第 4 點「證據不足的預測也寫入紀錄帳，並計入涵蓋率」，V22-07 也會落空。
```

- 【推論，要 quant 知悉】「證據不足而且缺項時 `up_pct`、`down_pct` 為 null」是 §6.1 `threshold_snapshot` 列的必然結果：沒有 σ_d 就算不出來，又不得補值。這不改事先宣告的定義。

**落字 1-C：D-1 表加一列（模組邊界）**
- 插入點：D-1 表 `| `app/forecast/errors.py`（N-23） | 預測帳的 fail-closed 例外型別` 這一列（全檔 1 處）的下一列。
- 方向：補定義（模組邊界）。CEO：否。擋 D-9。
- 逐字：

```
| `app/forecast/band.py`（N-41、N-46；純函式） | `threshold_inputs(band_def)` 與 `labeled_snapshot_violations(band_def, *, horizon, definition)` 的唯一定義（D-3 `forecast_record` 判定材料「適用範圍與缺項」）。只 import 標準庫與 dirdef 常數；不 import `scoring.py`、`app/outlook/volatility.py`，不讀 DB。`store.py` 的寫入驗證、`scoring.py`、`settlement.py`、`correction.py` 只經這兩個函式判定缺項（AST） |
```

- 理由：寫入端（`store.py`）與結算端（`scoring.py`）必須用同一個判定，證明鏈才能機械成立；放進 `scoring.py` 會讓 `store.py` import 只有 forward return 白名單模組才能出現的識別字（D-1 L240）。

### 二、N-46：有標籤的預測，`threshold_snapshot` 缺項時

**能否發生：證明路徑**
- 【事實：讀 ADR-0027 L2092】D-13 不變式是「`label == "insufficient"` 若且唯若 `missing` 非空」；事先宣告 §5.1 第 2 點（L1416）同義。
- 【事實：讀事先宣告 L833-834、L1428-1429】有效日報酬少於 55 會產生 `E-VOL-SHORT`，σ_d < 0.1% 會產生 `E-VOL-DEGENERATE`，兩者都輸出證據不足。所以照定義，有標籤 ⇒ σ_d 足量、而且不退化。
- 【事實：讀 ADR-0027 L287-292】現行寫入驗證的內容：兩個值都是有限數、0 < `down_pct` < 1、`up_pct` > 0、`up_pct` ≥ `down_pct`、用同列 {`K_h`, `sigma_d`, h} 重算後逐位相等。
- 【推論】由此可以推出 `K_h`、`sigma_d` 這兩個鍵存在，而且 K_h·σ_d 是正的有限數；σ_d 為 NaN 時 `up_pct` 也是 NaN，會被「有限數」擋下。**但推不出兩件事**：
  - (i) `EPS` 存在（重算不用 EPS）；
  - (ii) `K_h` 等於 dirdef 常數、σ_d > 0：K_h 與 σ_d 同為負數時，乘積仍然是正的。
  - 所以照現行條文，有標籤而缺項的情形不能完全排除。
- 【推論】加上落字 1-B 之後，證明鏈如下：
  - 有標籤的列，必須 `labeled_snapshot_violations()` 為空才寫得進去，而它是 `threshold_inputs()` 不為 None 的嚴格上集；
  - `forecast_record` 只增不改（D-2；事先宣告 §6.2）；
  - 結算與更正讀的是原始列（【事實：讀 ADR-0027 L1314、L1560】「預測端的 label、`band_def`……一律取原始的 `forecast_record`」）；
  - 所以結算端不會碰到有標籤而缺項的列。守衛只在寫入驗證被繞過時成立：程式缺陷、直接改 DB，或從沒有本驗證的版本還原。

**落字 2-A：D-9 第 6 點再加一個子點（接在落字 1-A 之後）**
- 方向：收緊。CEO：建議知悉，由風控裁定。理由：守衛成立時，結算評估整體停擺，檢查點也跟著延後；寫入端拒寫的範圍會留下缺日。
- 擋 D-9。
- 逐字：

```
   - （N-46；tech-architect 2026-10-19）**有標籤的預測，`threshold_snapshot` 缺項時**：
     - **寫入端**：依 D-3 `forecast_record` 判定材料「適用範圍與缺項」，有標籤的預測不能以缺項寫入。記錄一步在該範圍的寫入交易內，由 store 的寫入驗證拋 `LabeledThresholdSnapshotIncompleteError`（`source = record`）。記錄一步只接住這個型別：該範圍 rollback、不寫入，其餘範圍照常（D-7.7 每個範圍各自一個交易）；全部範圍結束後，該步的型別化步驟結果標為失敗（D-7 第 2 點 Q8），由編排函式發 ADR-0029 E-3d（`step = record`，`exception_class` 為 None）。這是預測當下、結果未知時的拒寫，不依結果挑選；該範圍依 D-8 第 2 點成為缺日。
     - **結算端與更正端的守衛**（防禦性斷言）：結算評估在 ⑥ 判定 U 的任何一筆之前，更正作業在第 5 點 ④ 重算之前，對 U（更正作業為被重查的列）中每一筆 `label ≠ insufficient` 的原始 `forecast_record`，以 `labeled_snapshot_violations()` 檢查；任一筆非空時，拋 `LabeledThresholdSnapshotIncompleteError`（`source` 為 `settlement` 或 `correction`）。結算評估整個交易不寫入（⑦）；更正作業不開啟 ⑤ 的交易，本作業視為中斷，由下一個作業完整重跑（第 5 點 ⑤）。
     - 本例外是不變式的守衛，不是預期中的營運狀態：依 D-13 不變式、事先宣告 §5.2 `E-VOL-SHORT`／`E-VOL-DEGENERATE`、D-3「適用範圍與缺項」與 D-11 第 1 點「預測端一律取原始的 `forecast_record`」，通過寫入驗證的有標籤列在結算端不會缺項；本例外只在寫入驗證被繞過（程式缺陷、直接改 DB、從沒有本驗證的版本還原）時成立。
     - **不得**：捕捉本例外後繼續寫入；把該筆改記 null、作廢（含新增 `status_reason`）、改 label 或補值；把該筆排除在 U 之外或延後判定，而讓其他預測照常結算。理由：逐筆跳過等於依程式缺陷挑選樣本；改記 null 會讓 null 路徑擴大，蓋掉寫入端的錯誤（風控 2026-10-19 checkpoint 批確認 (c)）。
     - **型別與欄位**：`LabeledThresholdSnapshotIncompleteError`（`app/forecast/errors.py`，`ForecastFailClosedError` 的子類），關鍵字必填的結構化屬性：
       - `source ∈ {record, settlement, correction}`；
       - `violations`：受影響各列違規值的聯集，依 D-3 封閉列舉的順序排列、不重複、非空的 tuple；
       - `affected_forecast_count`：≥ 1（`source = record` 時恆為 1）；
       - `data_as_of_from`、`data_as_of_to`：受影響各列 `data_as_of` 的最小值與最大值（ISO 日期）。
       例外訊息由這些屬性以固定格式產生，不含其他文字；不帶 `forecast_id`、`claim_id`、`scope_key`、代號或 label（FL-71 (f) 推播禁用詞清單 C、E 類）。受影響的列可以由只增不改的 `forecast_record` 以唯讀查詢重現，不需要帶識別資訊。
     - **告警**：沿用 ADR-0029 E-3d `forecast.step.failed`（結算 `step = settlement`、更正 `step = late_scan_correction`，`exception_class = LabeledThresholdSnapshotIncompleteError`；記錄一步依上文）。不新增事件，推播的欄位集合、標籤與模板都不變（ADR-0029 失效條件 5 不觸發）。
     - **使用者面**：不新增文案。結算評估不寫入時，依 D-7 第 2 點「持續失敗期間」與前置條件（驗證快照不寫，D-11.4 `snapshot_stale` 遮蔽）呈現；記錄一步拒寫的範圍，依 D-8 第 2 點與第 5 點以缺日呈現（TG-b）。
     - **處理路徑只有一條**：查出根因，修正程式或本條，送風控。`forecast_record` 只增不改，不得以改寫、刪除或補寫該列代替。
```

- 方案比較：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A（採用）** 寫入端拒寫，結算端以同一函式整次 fail-closed | 錯誤在預測當下就攔住；結算端不挑樣本；沿用 E-3d，不改 ADR-0029 | 守衛被觸發時，結算全面停擺，檢查點延後 | 停擺期間看不到新結算，靠 E-3d 與 `snapshot_stale` 揭露 |
| B 結算端逐筆跳過，留在 U 等待 | 其他預測照常結算 | 依程式缺陷挑選樣本；該筆永遠不會到終局，變成另一種沒有期限的待決項 | 可能藏住未命中 |
| C 比照 V22-07 記 null | 不停擺 | 風控已明文否決（Q-6） | 擴大 null 路徑，蓋掉寫入錯誤 |
| D 改記作廢，新增 `status_reason` | 不停擺；W 會記未命中，方向保守 | 新增列舉值等同改定義（LG-21），要改事先宣告並重送字面審 | 改定義的成本高 |
| E 新增 ADR-0029 事件，帶計數與違規值 | 推播資訊比較多 | 觸發失效條件 5，要送風控確認模板；而守衛照理不會被觸發 | 為一條照理走不到的路徑增加審查面 |

**落字 2-B：D-1 表 `errors.py` 一列改字**
- 插入點：`` `ValidationSnapshotPartialSetError`（N-23 Q3）；另有 ``（全檔 1 處）。
- 改為：`` `ValidationSnapshotPartialSetError`（N-23 Q3）、`LabeledThresholdSnapshotIncompleteError`（N-46）；另有 ``
- 方向：補定義。CEO：否。擋 D-9。被取代的原文由 tech-writer 照例錄存在修訂紀錄。

### 三、FL-72（N-41、N-46 的測試格）

- 插入點：`- **FL-24**：預測端計分永遠使用原始列。`（全檔 1 處）的前一行。FL-71 區塊之後，FL-72 編號未被使用（grep 0 筆）。
- 方向：收緊（測試）。CEO：否。擋 D-9。
- 逐字：

```
- **FL-72**（N-41、N-46；D-9 第 6 點；D-3 `forecast_record` 判定材料「適用範圍與缺項」；對應事先宣告 LG-33 (21)）：fixture 用離線的假市場 DB、假主 DB 與假的 `app.services.index`。
  - (a) 證據不足、`band_def` 缺 `sigma_d` 鍵的一筆，與一筆完整的有標籤預測，同在 U → 兩筆都寫 outcome 列，不拋例外，寫入 `forecast_settle_eval`；證據不足那一筆的 `realized_z`、`realized_label`、`hit`、`baseline_hits_json`、`diag_open_based_json`、`diag_last_close` 為 null，大盤 fixture 的 `index_return_diag`、族群 fixture 的 `diag_basket_with_excluded` 為 null；`realized_log_return`、`realized_return`、`mae`、`mfe` 等於 fixture 的期望值。有標籤那一筆照常算出。
  - (b) 缺項的各種情形各一格，期望同 (a)：`sigma_d` 為 null、0、−0.01、NaN、+inf；`K_h` 鍵不存在；`EPS` 鍵不存在。
  - (c) 證據不足而且缺項、T+h 一直沒有可用資料 → 判定視圖觀察到 D_5 的那次評估記 `missing_bar_after_wait`，`diag_last_close` 為 null，不拋例外。
  - (d) 證據不足、但 `threshold_snapshot` 完整 → `realized_z`、`realized_label` 依該列門檻算出（非 null），`hit` 為 null。
  - (e) 不得補值：同一 scope 另有一筆完整的預測，缺項那一筆仍為 null；結算評估與更正作業期間，`app/outlook/volatility.py` 的 `sigma_d()` 呼叫 0 次（spy）。
  - (f) 判定不讀 label：同一份市場資料與 `band_def`（完整），label 分別為 `insufficient` 與 `bullish` 的兩個 fixture → `status`、`status_reason`、`void_reasons_json`、`settlement_date`、`wait_sessions`、`wait_deadline_session` 逐位相同，只有 `hit` 不同。
  - (g) `forecast_record` 寫入：證據不足而且缺項 → 接受，`up_pct`、`down_pct` 為 null；證據不足而且缺項、`up_pct` 非 null → 拒絕；證據不足而且完整 → 原有五項照常驗證（`up_pct < down_pct` 的一格拒絕）；任一 label 的 `K_h` 或 `EPS` 與該列 `definition_version` 的 dirdef 常數不同 → 拒絕；兩個 `definition_version` 的 K 不同時，各依自己的版本比對。
  - (h) 驗證統計不受影響：E 中加入 (a) 那一筆，n、命中率、各基準命中、§4.3 各值與 `bootstrap_seeds_json` 逐位不變；涵蓋率的計數加 1；§4.2 混淆矩陣「證據不足」列的「其中 `realized_label` 為 null 的筆數」加 1。
  - (i) 寫入端（N-46）：label 為 `bullish`、`range`、`bearish` 各一格，每一種違規值至少一格 → 該範圍的 `forecast_record` 寫入拋 `LabeledThresholdSnapshotIncompleteError`（`source = record`、`affected_forecast_count = 1`、`violations` 等於 fixture 的期望值），該範圍沒有列，同一次執行的其他範圍照常寫入；記錄一步的步驟結果為失敗，E-3d 一則（`step = record`，`exception_class` 為 None）。
  - (j) 結算端守衛：以測試專用的 SQL 繞過寫入驗證，在假主 DB 放一筆缺 `sigma_d` 的有標籤預測 → `run_settlement_evaluation()` 在寫入任何 outcome 之前拋 `LabeledThresholdSnapshotIncompleteError`（`source = settlement`），屬性等於 fixture 的值；例外逃出時 `in_transaction` 為 False，`forecast_outcome`、`forecast_settle_eval` 的列數不變；任何一列都沒有出現「`label ≠ insufficient` 而且 `realized_label` 為 null」；E-3d 一則（`step = settlement`，`exception_class = LabeledThresholdSnapshotIncompleteError`）；缺日稽核照常被呼叫（比照 FL-71 (b)）；下一次評估以同一份 fixture 再拋一次（不存跨執行狀態）。
  - (k) 更正端守衛：被重查的列中有 (j) 那種列 → `run_correction_job()` 在 ④ 拋出（`source = correction`），⑤ 的交易沒有開啟，沒有 supersede 列、diag 列與 `forecast_correction_job_end`。
  - (l) `forecast_outcome` 寫入驗證：有標籤、`status = resolved`、`realized_label` 為 null → 拒絕；證據不足而且缺項、`realized_label` 非 null → 拒絕；證據不足、`hit` 非 null → 拒絕。
  - (m) 例外：`str(exc)` 等於由屬性以固定格式產生的字串；缺任一個必填屬性 → 建構失敗；`violations` 為空或未排序 → 建構失敗；fixture 的 `forecast_id`、`claim_id`、代號哨兵值與 label 字串不出現在例外訊息、`ops alert:` log 行與推播中（沿用 FL-71 (f) E 類）。
  - (n) 單一定義：`threshold_inputs`、`labeled_snapshot_violations` 在 `app/` 內各恰好一個定義，都在 `band.py`；`store.py` 的寫入驗證、`scoring.py`、`settlement.py`、`correction.py` 都經這兩個函式判定（AST、spy）；`band.py` 不 import `scoring.py`、`app/outlook/volatility.py`（import graph）。
```

### 四、N-49：FL-47 改字（不擋）

- 【事實：讀 ADR-0027 L1385-1390】seed 導出式本身沒有改，`eval_key` 改為 `n{n}`：daily 列取該列的 n，checkpoint 列取 n_j。
- 【事實：讀事先宣告 L2316】LG-20 在 v0.22 加了兩句：「同一 n 的 daily 列與 checkpoint 列使用同一組 seed」、「延後判定與準時判定的 checkpoint 列 seed 相同」。
- 【推論】FL-47 寫的是「導出式」，語意自動跟著 D-11.2 走，不會測錯。但有兩個問題：
  - 「（即 LG-20）」宣稱等於整條 LG-20，已經不屬實，那兩句實際由 FL-71 (i) 第 (1)、(12) 格涵蓋；
  - 測試若直接呼叫被測程式算期望值，`eval_key` 用錯也照樣通過。
- 插入點：`- **FL-47**（r1，A-5）：`bootstrap_seeds_json` 的鍵 ⊆ 對照表；每個值等於導出式的結果（即 LG-20）。`（全檔 1 處），整列換成：

```
- **FL-47**（r1，A-5；N-49）：`bootstrap_seeds_json` 的鍵 ⊆ 對照表；每個值等於 D-11 第 2 點「seed 導出式」以該列的 `claim_id` 與 `eval_key` 算出的結果：前瞻列的 `eval_key` 是 `n{n}`（daily 列取該列的 n，checkpoint 列取 n_j），重放用 `freeze_commit`。期望值在測試內以 fixture 的 `claim_id`、n、`purpose`、`block_len` 直接代入導出式計算，不得呼叫被測程式的 seed 函式取得。加兩格：同一 claim、同一 n、`computed_for_session` 不同的兩列 daily → seed 逐位相同；同一 `computed_for_session`、n 不同 → 以 fixture 值算出的 seed 不同。（對應 LG-20「seed 等於 §4.3 導出式的值」一句；LG-20 的「同一 n 的 daily 列與 checkpoint 列使用同一組 seed」「延後判定與準時判定的 checkpoint 列 seed 相同」由 FL-71 (i) 第 (1)、(12) 格涵蓋）〔N-49 取代：原寫「- **FL-47**（r1，A-5）：`bootstrap_seeds_json` 的鍵 ⊆ 對照表；每個值等於導出式的結果（即 LG-20）。」〕
```

- 方向：收緊（測試）。CEO：否。不擋。

### 五、修訂紀錄（給 tech-writer 的骨架；字句由 tech-writer 依慣例整理）

- 段名：「N-41、N-46 批（D-1 表兩處、D-3 `forecast_record` 判定材料、D-9 第 6 點、FL-72；N-49 FL-47）」。
- 逐項列方向、CEO、風控結論，依第一～四節。
- 被取代的原文：D-1 `errors.py` 一列的原句、FL-47 原列（正文已錄）。D-3、D-9 為插入，沒有被取代的原文。
- 待決事項中「G-2 的 ADR 側落字」「有標籤的預測 `threshold_snapshot` 缺項的寫入端規則」兩項，在風控確認後改為已決。

### 六、另外發現（不在本次落字內，請 coordinator 列入追蹤清單）

1. **缺日原因少一個值**（擋記錄一步寫入驗證的實作，不擋本批）：
   - 【事實：讀 ADR-0027 L1077-1083】D-8 第 2 點的 `reason` 只有 `scheduler_down`、`job_error`、`late_only`、`timeout`、`inputs_not_ready`、`db_restored` 六個值。
   - 【推論】run 有 end、但某個範圍被寫入驗證拒寫時，沒有對應的值，而且被拒的事實沒有持久化，稽核分辨不出。
   - 這個缺口在現行 D-3 五項驗證下就已經存在，N-46 不是它的起因。要另案由 TA 定（候選：新增 `write_rejected`，並寫下拒寫紀錄的存放處），送風控。
2. **記錄一步逐範圍的例外處理**：【未查證】D-7 只寫「每個範圍各自一個交易」（L899）。我沒找到記錄一步對範圍內例外的通用規則，落字 2-A 只對新型別定義。請 dev-lead 實作前確認。
3. **重放**：
   - 【事實：讀 ADR-0027 L641】`forecast_replay_outcome` 的驗證是「`diag_last_close` 非 null ⇔ `status ≠ resolved`」。
   - 【推論】重放若可能出現「證據不足、缺項而且作廢」的列，就和 V22-07 的 null 規則衝突。V22-07 只寫在 §6.3 `forecast_outcome`，是否適用重放由 quant 決定。不擋 D-9，重放另有閘門。
4. **證據不足的族群列與翻轉數**：
   - 【事實：讀事先宣告 L1542】`diag_basket_last_close` 與主標籤不一致時，計入翻轉數與 W。
   - 【推論】證據不足的列不在 n，應該也不在 W 的樣本裡，null 就不會進入 W。這點請 quant 和 (d) 一起確認。

---

## 驗證

只用 Read、Grep，沒有改任何檔案，沒有讀 `.env` 或任何 `*.db`。

- **ADR-0027**（`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`）：
  - D-1 表（L234-251）；D-3 `forecast_record`／`forecast_outcome`（L267-326）、`forecast_replay_outcome`（L624-643）；D-7 第 1、2、7 點（L781-835、L898-900）；D-8 第 2、5 點（L1067-1091）；D-9 全節（L1093-1286）；D-11 第 1、2 點（L1304-1391）、L1314、L1560；D-13（L2072-2099）；D-14（L2101-2148）；D-11.4 相關（L1738-1766、L1800-1811、L1880、L1900）；FL-71（L2507-2555）；FL-47（L2581）；修訂紀錄「N-23 checkpoint 批」（L4642-4685）。
  - 用 grep 確認：插入點字串各 1 處；`band_def` 全檔沒有依 label 的例外；FL-72 沒有被使用；`realized_label` 沒有既有的 null 驗證。
- **事先宣告**（`/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`）：§2.1（L811-843）、§5.1、§5.2（L1411-1441）、§6.1 `threshold_snapshot`（L1490）、§6.3 觸發與欄位表（L1512-1544，含 L1531 V22-07、L1533 `hit`、L1542）、§4.3 seed 規則（L1045-1052）、LG-20（L2316）、LG-33 (21)（L2329 片段）、§9.2 TA 項（L1976）、修訂表 L91、L102-123。
  - 任務指示要讀的 §4.2、§9.2 只讀了 grep 命中的行（L1010、L1976），沒有通讀全節。
- **風控確認**（`/home/user/AICompany/work/reviews/2026-10-19-checkpoint批與v0.22逐字確認-風控.md`）：第一節（L16-66）、第二節 D（L92-98）、第四節（L157-305，含 Q-6 L239-240、同批規則 3 L268、追蹤 L294-295）。
- **ADR-0029**（`/home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md`）：D-2（L74-112）、D-3（L114-130）、D-7（L199-226）、D-10（L241-254）、失效條件（L315-325）。
- **TA 先前分析**（`/home/user/AICompany/work/reviews/2026-10-19-N38核對與checkpoint乙案改寫及N20改寫-tech-architect.md`）：L28、L80-104。
- **追蹤清單**（`/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`）：N-41、N-46、N-49 三列（grep）。
- **未查證**：
  - `volatility.py` 在有效日報酬不足時回傳 NaN 還是 None；
  - 產生 `threshold_snapshot` 的函式缺 σ_d 時是省略鍵還是寫 null（`threshold_inputs()` 兩者一律視為缺項，所以不影響規則）；
  - 記錄一步現行的逐範圍例外處理。

## 下一步

1. **coordinator**：把第一～四節送 risk-compliance-officer 逐字確認。要風控裁定的點：
   - (i) 落字 1-B 的放寬面與 CEO 層級（我建議知悉）；
   - (ii) `diag_basket_with_excluded` 依原則列入 null 清單，還是請 quant 先補 V22-07 的括號；
   - (iii) N-46 採方案 A，告警沿用 E-3d、不新增事件；
   - (iv) N-46 的 CEO 層級（我建議知悉）。
2. **quant**（風控確認後，可以併入 v0.23 單項）：
   - V22-07 括號是否補 `diag_basket_last_close`；
   - §9.2「TA：G-2 在 ADR 側的落字……有標籤的預測能否出現缺項」一項改為已決，指向本回覆；
   - 確認第六節第 3、4 點。
3. **tech-writer**：風控確認後依第一～五節落檔，落檔前用 `grep -cF` 確認插入點唯一。N-49 不擋，可以同批或另批。
4. **coordinator 追蹤清單**：新增第六節第 1 點（擋記錄一步寫入驗證的實作；TA 另案）、第 2 點（dev-lead 查證）、第 3 點（quant，不擋 D-9）。N-41、N-46 在風控確認後改為「字面確認，擋 D-9 實作直到落檔」。
5. **dev-lead**：D-9 實作要等本批落檔；`band.py` 是新模組，邊界依落字 1-C。

# 記錄一步批（N-51、N-52、N-63）落字起草

- 審查者：tech-architect
- 日期：2026-10-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

1. **記錄一步批的落字已起草，共 8 段（L-1～L-8）**，涵蓋 N-51、N-52（G-1～G-4）與 N-63 (a)～(d)。全部只用 Read 與 Grep，沒有改任何檔案。每段的插入點都在 ADR-0027 全檔用 Grep 確認只出現 1 次。
2. **我做的決定與否決的方案**（理由見第〇節）：
   - **N-51**：新增缺日 `reason = write_rejected`。拒寫的事實存在 `forecast_run_end` 新增的欄位 `refused_scopes_json`。不新開表，也不放進 `forecast_ledger_events`。
   - **N-52 例外處理**：採 A 案，也就是可接住的型別用封閉清單，清單以外的例外整步中止（fail-closed）。否決 B 案（範圍內寬接 `Exception`）。
   - **N-52 第 4 點（中止後剩下範圍的 `reason`）**：選 (b)，新增 `record_error`。不採 (a) 擴充 `job_error`，原因是要讓 FL-18 和 `job_error`「沒有 end」的意思保持乾淨。
   - **偏離 dev-lead D-6 一處**：記錄一步**逾時**時，`RecordStepResult.failed` 也設為真，會發一則 E-3d（`exception_class` 為 None）。dev-lead 原案是逾時不算失敗。這點列為風控裁定點 (iii)。
   - **N-63**：(a)(b)(c) 照採。(d) 改成「常數序列必須剛好得 0.0、同一輸入重算逐位相同」的性質要求，不指定用哪個函式庫。另外補一條：輸入含 NaN 或 ±inf 時拋 `ValueError`（備選方案見裁定點 (v)）。
3. **對 ADR-0029**：推播的欄位、標籤與模板都不變，失效條件 5 不觸發。唯一的行為變化是「記錄一步逾時」會多出一個發 E-3d 的情形，沿用現有 E-3d 的「型別化結果為失敗」那條觸發，不改 ADR-0029 字面。
4. **和另一位 TA 的 v0.24 同步沒有字面衝突**：本批沒有碰 D-11、D-12、FL-45b、FL-68、FL-72 (h)、FL-73。事先宣告要同步的地方可能和 v0.24 重疊，見第三節。

---

## 各部門回報

### tech-architect

#### 〇、方案比較（事實與推論分開標）

| 題目 | 方案 | 優點 | 缺點／風險 | 結論 |
|---|---|---|---|---|
| N-51 缺日 `reason` | (1) 新增 `write_rejected` | 拒寫可以和其他原因分開 | 事先宣告 §6.3 L1671 的列舉要跟著改 | **採用** |
| | (2) 併入 `job_error` | 列舉不變 | 「沒有 end」和「有 end 但拒寫」混在一起，FL-18 的意思變模糊 | 否決 |
| N-51 存放處 | (A) `forecast_run_end.refused_scopes_json` | 和 end 在同一筆寫入，兩邊一致；不新開表 | end 寫不進去時，拒寫的事實就沒了，退回記 `job_error` | **採用** |
| | (B) 新開逐範圍結果表，每個範圍用獨立交易寫 | 程序崩潰也留得住 | 多一張表、多一種交易，會出現半寫狀態 | 否決 |
| | (C) `forecast_ledger_events` 加一種 kind | 不新開表 | 那張表的事件會被歸入 `E_*` 類別，可能把拒寫帶進 E 的判定 | 否決 |
| N-52 清單外的例外 | A 案：整步中止 | 系統性錯誤不會被逐範圍重複觸發；和 D-9.6「不依程式缺陷逐筆挑選」一致 | 一個範圍的程式缺陷會讓同一次執行的其餘範圍全部變缺日，而且每次執行都重演 | **採用** |
| | B 案：範圍內寬接 `Exception` 後繼續 | 其他範圍照常寫入 | 程式缺陷會變成靜默的逐範圍缺日 | 否決 |
| N-52 第 4 點 | (a) 擴充 `job_error` | 少一個列舉值 | `job_error` 不再等於「沒有 end」 | 否決 |
| | (b) 新增 `record_error` | 有秩序的中止和崩潰分得開；`forecast_gaps.run_id` 可以對回 run_end 的 `error_class` | 多一個列舉值（反正和 N-51 同一批改） | **採用** |
| 記錄一步逾時算不算失敗 | (i) 算失敗，發 E-3d | 逾時讓剩下範圍變缺日，操作者有推播可看；ADR-0029 字面不用改 | 推播次數增加：每次逾時的執行多 1 則 | **建議**（裁定點 iii） |
| | (ii) 不算失敗（dev-lead 原案） | 推播比較少 | 逾時只留在 log 和缺日裡 | 備選 |
| N-63 存不存 σ_d | 證據不足的列記 null（提案 a、b） | 缺項筆數和 W 放回筆數由規格決定 | 族群 W 變嚴（收緊）；退化列改為寫入（有放寬面） | **採用** |
| | 照字面「實際算得的值就存」 | 不用改 | 結果取決於實作；可能存下被禁止的替代估法算出的值；極小的 σ 可能讓整筆被拒寫 | 否決 |

〔事實〕dev-lead 已查證 `app/forecast/`、`app/outlook/` 在所有分支都不存在，所以新增欄位沒有遷移問題。

#### 一、落字

**L-1　D-1 表 `app/outlook/volatility.py` 一列（句末接字）**
- 插入點：`只吃已依 V12-19 取好的日報酬序列，不讀觀察日 |`（L252，全檔 1 處）。
- 換成：
```
只吃已依 V12-19 取好的日報酬序列，不讀觀察日；（N-63）回傳 frozen 的 `SigmaEstimate`，契約見 D-3 `forecast_record` 判定材料「適用範圍與缺項」的 N-63 子點 |
```
- 方向：補定義（模組邊界）。CEO：否。擋 `volatility.py` 的實作。
- 被取代的原文：無。只在句末接字，原字一個不刪。

**L-2　D-3 `forecast_run_end`（插入）**
- 插入點：在含 `scopes_done, scopes_missed, ended_at)`：沒有 end 列就代表程序中途崩潰。` 的那一行（L270，1 處）**之後**另起一行。
```
  - （N-51、N-52；tech-architect 2026-10-21）**新增欄位**：
    - `refused_scopes_json NOT NULL`：本 run 被拒寫的範圍。JSON 陣列，每一項恰為 `{scope_kind, scope_key, exception_class, violations}`，依 (`scope_kind`, `scope_key`) 排序、不重複；沒有時為 `[]`。`exception_class` 是 D-7 第 7 點 N-52 子點 `RECORD_SCOPE_REFUSAL_TYPES` 中被接住的類別名稱；`violations` 是該例外的 `violations` 原值（D-3「適用範圍與缺項」的封閉列舉，依其順序排列、不重複、非空）。不含成本與股數（AV-9）。這是拒寫事實唯一的持久化處：D-8 第 2 點的 `write_rejected` 只依它判定。
    - `error_class NULL`：`outcome = error` 時為中止例外的類別名稱（`type(exc).__name__`；不符 `^[A-Za-z_][A-Za-z0-9_]*$` 或長度超過 128 時記 `invalid_exception_class`，比照 ADR-0029 D-3 第 10 點）；其餘 outcome 為 null。不存例外訊息。
  - **寫入者**：只有 `recorder.py` 的記錄一步（AST 列舉呼叫點），欄位由記錄一步在程序內累積的結果填入。`outcome` 與兩個計數的判定見 D-7 第 7 點 N-52 子點。
  - **寫入驗證**（任一項不成立就拒絕寫入）：
    - `scopes_done` ＝ 本 run 已寫入 `forecast_record` 的相異 (`scope_kind`, `scope_key`) 數；`scopes_done + scopes_missed` ＝ 本 run `forecast_scope_snapshot` 的相異 (`scope_kind`, `scope_key`) 數；
    - `refused_scopes_json` 的每一項都在本 run 的範圍快照內，而且本 run 沒有該範圍的 `forecast_record`；項數 ≤ `scopes_missed`；
    - `outcome = ok` ⇒ `scopes_missed = 0`；`outcome = partial` ⇒ `refused_scopes_json` 非空，而且項數 ＝ `scopes_missed`；`outcome = timeout` ⇒ 項數 < `scopes_missed`；
    - `error_class` 非 null ⇔ `outcome = error`。
  - 不屬於 `E_CHANGING_EVENTS`，不影響 E、n、W 或任何判定。`refused_scopes_json`、`error_class` 只有 `audit.py`（D-8 第 2 點）與稽核工具可以讀；`views`、API route 與匯出不讀（AST）。
```
- 方向：補定義（收緊：新增持久化與寫入驗證）。CEO：否。擋記錄一步的寫入驗證與 `audit.py`。
- 被取代的原文：無（插入）。

**L-3　D-3「適用範圍與缺項」的 N-63 子點（插入）**
- 插入點：以 `      - 理由：上方五項對缺 `sigma_d` 的列無法成立` 開頭的那一行（L300，1 處）**之後**，用同一層縮排另起一項。
```
      - （N-63；tech-architect 2026-10-21；dev-lead 2026-10-21 查證）**σ_d 的回傳契約與證據不足時的存值**：
        - `app/outlook/volatility.py` 的 `sigma_d(log_returns)`：輸入是已依 V12-19 取好的窗內日報酬，每一項為有限的 float，或 None（無效日，由呼叫端依事先宣告 §2.1 判定）；含 NaN 或 ±inf 時拋 `ValueError`（程式缺陷，記錄一步依 D-7 第 7 點 N-52 子點整步中止）。回傳 frozen 的 `SigmaEstimate{value, valid_returns, raw_std, missing_code}`，依序判定：
          - `valid_returns` ＝ 非 None 的項數；
          - `valid_returns` < `SIGMA_MIN_VALID`（含 0）→ `value`、`raw_std` 都是 None，`missing_code = E-VOL-SHORT`；不以現有的筆數計算任何估計值（事先宣告 §5.1 第 3 點）；
          - 否則 `raw_std` ＝ 有效日報酬的樣本標準差（ddof=1，事先宣告 §2.1）；`raw_std` < `SIGMA_FLOOR` → `value` 為 None，`missing_code = E-VOL-DEGENERATE`；
          - 否則 `value = raw_std`，`missing_code` 為 None。
          - 上述情形都不回 NaN、不拋例外。估計式在常數序列上必須恰好得 0.0，同一輸入重算逐位相同；用哪一種實作由 dev-lead 定，`app/` 內只有一個（FL-55）。
        - `band_def.sigma_d` 只取 `SigmaEstimate.value`；`band_def.valid_returns` 取 `SigmaEstimate.valid_returns`。`raw_std` 只寫入 `E-VOL-DEGENERATE` 那一項 `missing_json` 的 `available`（事先宣告 §5.2「σ_d 值」），不得寫入 `band_def`，也不得作為任何判定的輸入（AST）。
        - **寫入驗證**（`label = insufficient` 的列；任一項不成立就拒絕寫入）：
          - `missing_json` 含 `E-VOL-SHORT` 或 `E-VOL-DEGENERATE` ⇒ `band_def` 有 `sigma_d` 鍵、值為 null，`valid_returns` 是非 null 的非負整數；
          - `E-VOL-SHORT` 與 `E-VOL-DEGENERATE` 不同時出現；
          - `valid_returns` 非 null 時：`E-VOL-SHORT` 出現 ⇔ `valid_returns` 小於該列 `definition_version` dirdef 的 `SIGMA_MIN_VALID`；`E-VOL-SHORT` 那一項的 `available` ＝ `valid_returns`；
          - `E-VOL-DEGENERATE` 那一項的 `available` 是有限數，0 ≤ `available` < 該版 dirdef 的 `SIGMA_FLOOR`。
          有標籤的列依本點上方 `label ≠ insufficient` 一項（`sigma_d_below_floor`、`valid_returns_below_min`），不另適用本子點。
        - 理由：用不到 `SIGMA_MIN_VALID` 筆日報酬算出的 σ，是事先宣告 §5.1 第 3 點禁止的替代估法；小於 `SIGMA_FLOOR` 的值存進 `band_def`，`threshold_inputs()` 會判為完整，`up_pct` 可能算成 0.0 而整筆被拒寫（違反事先宣告 §5.1 第 4 點），或在結算時使 z 爆大（事先宣告 §2.1 `SIGMA_FLOOR`）。本子點使缺項筆數與 W 放回筆數由規格決定，不取決於實作；相對本點上一項「算不出的記 null」的字面，是在兩種都合規的實作中選定一種。
        - 另一面（照實並陳）：族群 `E-VOL-SHORT`／`E-VOL-DEGENERATE` 的證據不足列，排除成員非空而 `resolved` 時，兩個籃子標籤都是 null，依事先宣告 §4.3 (f) v0.23（V23-02）一律在 W 中放回，比存值的讀法嚴（收緊）。原本可能因存入極小 σ 而被拒寫的退化列改為寫入、進入 E：作廢時計入作廢率的分子與分母並在 W 中放回；`resolved` 時只計入作廢率的分母，作廢率可能因此下降（事先宣告 V23-01 另一面 ②，放寬面）。大盤與個股的判定不變，只少了 `realized_z`、`realized_label` 與診斷欄位。
```
- 方向：補定義（兩面）。收緊面是族群 W；放寬面是退化列從被拒寫改為寫入後，作廢率的分母變大。
- CEO：建議**知悉**。理由比照 N-41 1-B：被取代的讀法本來就依實作而定，從未核可，而且和 §5.1 第 4 點衝突。
- 擋：`volatility.py` 與記錄一步的寫入驗證。另外需要 quant 確認方向。
- 被取代的原文：無（插入）。

**L-4　D-7 第 7 點的 N-52 子點（插入）**
- 插入點：`   - 逾時後剩下的範圍記為缺日，原因 `timeout`。`（L908，1 處）**之後**。
```
   - （N-52、N-51；tech-architect 2026-10-21；dev-lead 2026-10-19 查證 D 節）**記錄一步範圍內的例外**：
     - **範圍邊界**：記錄一步對每個範圍各包一層 try，只包住該範圍的計算與寫入交易。決定 T、A-25 的 `forecast_run` 與 `forecast_scope_snapshot` 寫入、範圍之間的期限檢查，以及迴圈結束後的 `forecast_run_end` 寫入，都不在範圍的 try 之內。
     - **可接住的型別是封閉清單**：`recorder.py` 的常數 `RECORD_SCOPE_REFUSAL_TYPES`，目前只有 `LabeledThresholdSnapshotIncompleteError`（`source = record`；D-9 第 6 點 N-46 子點）。接住時：該範圍的交易已 rollback，不寫入；記錄一步在程序內記下該範圍的 `scope_kind`、`scope_key`、類別名稱與 `violations`，結束時寫入 `forecast_run_end.refused_scopes_json`（D-3）；期限照常在範圍之間檢查；繼續下一個範圍。不得以 `ForecastFailClosedError`、`Exception` 或清單成員的其他父類別接住。清單增列型別，須修訂本點並送風控。`store.py` 與其他下層不得接住清單內的型別。
     - **清單以外的例外：整步中止（fail-closed）**。範圍內拋出清單以外的 `Exception` 時：
       - 該範圍的交易 rollback；剩下的範圍不跑；
       - 以獨立交易盡力寫入 `forecast_run_end`：`outcome = error`；`scopes_done`、`scopes_missed` 照實；`refused_scopes_json` 為中止之前已拒寫的範圍；`error_class` 為中止例外的類別名稱；
       - 再以不帶參數的 `raise` 拋出原例外，由編排函式依第 2 點「步驟隔離」接住，記錄一步標為失敗，發 ADR-0029 E-3d（`step = record`，`exception_class = type(exc).__name__`）。中止之前已有拒寫時，同樣只發這一則（ADR-0029 D-7「每一步失敗只發一則」）；
       - 中止用的 run_end 寫入本身失敗時，記一行 WARNING，只含兩個例外的類別名稱，仍拋出原例外；該 run 沒有 end，依 D-8 第 2 點記 `job_error`（FL-18），拒寫的事實不另行重建；
       - `KeyboardInterrupt`、`SystemExit` 等不是 `Exception` 的例外不接（比照 FL-71 (b)）；
       - 迴圈結束後正常寫入 `forecast_run_end` 時拋出的例外，不再嘗試寫入，直接往外拋（該 run 沒有 end，記 `job_error`）。
       - 理由：清單以外的例外多半是系統性的（DB、輸入或程式缺陷），逐範圍跳過只會重複失敗，並把程式缺陷變成靜默的逐範圍缺日；與 D-9 第 6 點「不依程式缺陷逐筆挑選」一致。另一面（照實並陳）：單一範圍的程式缺陷會使同一次執行的其餘範圍全部成為缺日，而且每次執行重演，停擺沒有時間上限，可能觸發失效條件 F-3（比照 N-46 的代價）。
     - **`forecast_run_end.outcome` 的判定**，依序取第一個成立者：`error`（依上一子點中止）；`timeout`（期限已到，還有範圍沒有跑）；`partial`（至少一個範圍被拒寫）；`ok`。`scopes_done` ＝ 已寫入的範圍數；`scopes_missed` ＝ 範圍快照中的範圍數減 `scopes_done`，拒寫、逾時與中止的範圍都計入。
     - **型別化步驟結果**（第 2 點 Q8）：記錄一步正常結束時回傳 frozen 的 `RecordStepResult`（名稱暫定），欄位：
       - `t`（date 或 None）、`run_id`（int 或 None）：沒有 T、或沒有寫入 `forecast_run` 時為 None；
       - `run_outcome ∈ {ok, partial, timeout}`，沒有寫入 `forecast_run` 時為 None；`error` 不出現在結果中，中止以例外呈現；
       - `scopes_done`、`scopes_refused`、`scopes_timed_out`；
       - `refused_violations`：各拒寫範圍 `violations` 的聯集，依 D-3 封閉列舉的順序排列、不重複；
       - `failed`：`scopes_refused > 0` 或 `run_outcome = timeout` 時為真，其餘為假。`inputs_not_ready` 不算失敗（ADR-0029 E-3d）。
       `failed` 為真時，編排函式發 E-3d 一則（`step = record`，`exception_class` 為 None），不論拒寫幾個範圍。`forecast record run:` INFO 行的記錄一步部分，帶 `run_outcome`、三個計數與 `refused_violations`，不帶 `scope_key`、代號或 label；範圍明細只在 `refused_scopes_json`。
```
- 方向：補定義（收緊）。逾時算失敗屬於收緊（告警）。
- CEO：建議**知悉**，因為有停擺代價，比照 N-46。
- 擋：記錄一步的實作。
- 被取代的原文：無（插入）。

**L-5　D-8 第 2 點 `reason` 判定（插入）**
- 插入點：含 `標記的區間：`db_restored`` 的那一行（L1091，1 處）**之後**。
```
     - （N-51、N-52；tech-architect 2026-10-21）有 run、有 end，而且該範圍列在該 end 的 `refused_scopes_json`：`write_rejected`
     - （N-52；tech-architect 2026-10-21）有 run、有 end 而 `outcome = error`，該範圍沒有寫入、也不在 `refused_scopes_json`：`record_error`
     - （N-51、N-52）同一個 run 內，`write_rejected` 先於 `timeout`、`record_error` 判定：逾時或中止的 run 裡，先前被拒寫的範圍記 `write_rejected`，其餘沒有寫入的範圍依 `outcome` 記 `timeout` 或 `record_error`。這兩個值的缺日列，`run_id` 填該 run；一個範圍被拒寫或中止時，該範圍的每一個 claim 都記同一個 `reason`。拒寫的事實只依 `forecast_run_end.refused_scopes_json` 判定，不得以 log、告警或 `forecast_record` 是否存在推定；end 沒有寫入時依「有 run、沒有 end」記 `job_error`。
```
- 方向：補定義（收緊：缺日原因分辨得出來）。缺日列數、F-3 與 TG-b 的渲染都不變〔推論，依 D-8 第 5 點字面：只有 `late_only` 分開渲染〕。
- CEO：否。
- 擋：`audit.py` 的 `reason` 判定。事先宣告 L1671 要同步（P-1）。
- 被取代的原文：無（插入，現有六個值的字句不動）。
- 附註〔事實〕：`write_rejected` 和 D-3 `plan_coverage_log.skip_reason`（L707）同名，但屬於不同的表、不同的列舉，意思相近（寫入驗證拒寫）。我判斷可以接受，如果風控偏好改名，候選名是 `record_refused`。

**L-6　D-9 第 6 點 N-46 子點（插入）**
- 插入點：以 `該範圍依 D-8 第 2 點成為缺日。` 結尾的「寫入端」那一行（L1295，1 處）**之後**。
```
     - （N-51、N-52；tech-architect 2026-10-21）寫入端的補充：本子點「只接住這個型別」，即 D-7 第 7 點 N-52 子點封閉清單 `RECORD_SCOPE_REFUSAL_TYPES` 的唯一一項；被拒寫的範圍記入 `forecast_run_end.refused_scopes_json`，缺日的 `reason` 為 `write_rejected`（D-8 第 2 點）；範圍內拋出清單以外的例外時，依 D-7 第 7 點整步中止。
```
- 方向：補定義（不變：對齊）。CEO：否。被取代的原文：無。

**L-7　FL-74（插入）**
- 插入點：`- **FL-18**：` 開頭的那一行（L2303，1 處）**之後**，放在「排程與逾時」組裡。
```
- **FL-74**（N-51、N-52；D-7 第 7 點 N-52 子點；D-3 `forecast_run_end`；D-8 第 2 點；ADR-0029 E-3d）：fixture 用離線的假市場 DB、假主 DB 與假的 `app.services.index`；範圍快照有 A、B、C 三個範圍，各有 h＝3、h＝5 兩個 claim。
  - (a) 封閉清單：`recorder.py` 的 `RECORD_SCOPE_REFUSAL_TYPES` 恰好等於 `(LabeledThresholdSnapshotIncompleteError,)`。
  - (b) 例外接在哪裡（AST）：逐範圍的 try 只出現在 `recorder.py` 記錄一步的單一函式內；範圍迴圈內的 except 只指名 `RECORD_SCOPE_REFUSAL_TYPES` 或其成員，沒有 `except Exception`、`except BaseException`、裸 `except:`、`except ForecastFailClosedError`；同一函式恰好一個 `except Exception`，包住整個範圍迴圈、不包住正常路徑的 run_end 寫入，區塊內只呼叫中止用的 run_end 寫入函式，並以不帶參數的 `raise` 結束；中止用的 run_end 寫入函式只有一個 `except Exception`，區塊只記 WARNING、不 `raise`、不呼叫 `str(exc)`／`repr(exc)`；`store.py` 沒有指名 `LabeledThresholdSnapshotIncompleteError` 或 `ForecastFailClosedError` 的 except。
  - (c) 拒寫一個：B 拋 `LabeledThresholdSnapshotIncompleteError` → A、C 寫入；`forecast_run_end` 為 `outcome = partial`、`scopes_done = 2`、`scopes_missed = 1`、`refused_scopes_json` 恰為 B 一項（`exception_class`、`violations` 等於 fixture），`error_class` 為 null；`RecordStepResult.failed` 為真、`scopes_refused = 1`；E-3d 一則（`step = record`，`exception_class` 為 None）；B 的 `late_cutoff_at` 過後稽核 → B 的兩個 claim 各一列 `reason = write_rejected`，`run_id` 為該 run；A、C 沒有缺日列。
  - (d) 拒寫兩個：A、C 被拒寫、`violations` 不同 → E-3d 仍只一則；`refused_violations` 為兩者聯集，依封閉列舉排序。
  - (e) 第一個範圍就中止：A 拋 `sqlite3.OperationalError` → 沒有任何 `forecast_record`；`outcome = error`、`scopes_done = 0`、`scopes_missed = 3`、`refused_scopes_json = []`、`error_class = OperationalError`；例外到達編排函式，E-3d 一則（`exception_class = OperationalError`）；結算與缺日稽核照常執行（比照 FL-71 (b)）；稽核 → 六個 claim 都記 `record_error`。
  - (f) 中途中止，而且之前有拒寫：A 拒寫、B 拋清單外的 `ForecastFailClosedError` 子類 → 沒有 B、C 的列；`outcome = error`、`refused_scopes_json` 恰為 A；E-3d 只一則，`exception_class` 為 B 的例外類別；稽核 → A 記 `write_rejected`，B、C 記 `record_error`。
  - (g) 拒寫之後逾時：A 拒寫、B 寫入後期限已到 → C 不跑；`outcome = timeout`、`scopes_missed = 2`、`refused_scopes_json` 恰為 A；`failed` 為真，E-3d 一則（`exception_class` 為 None）；稽核 → A 記 `write_rejected`，C 記 `timeout`。只有逾時、沒有拒寫 → 同樣 E-3d 一則。
  - (h) run_end 寫不進去：(e) 的 fixture 再讓中止用的 run_end 寫入拋例外 → E-3d 的 `exception_class` 仍為 `OperationalError`；該 run 沒有 end；WARNING 一行，只含兩個類別名稱，fixture 例外訊息的哨兵字串不出現；稽核 → 六個 claim 都記 `job_error`（FL-18）。
  - (i) 範圍內注入 `KeyboardInterrupt` → 不被記錄一步接住，不寫中止用的 run_end。
  - (j) `forecast_run_end` 寫入驗證：D-3 所列每一項各一格違反 → 拒絕。
  - (k) 全部寫入 → `outcome = ok`，`failed` 為假，E-3d 0 則；`forecast record run:` INFO 行帶記錄一步的 `run_outcome`、三個計數與 `refused_violations`，不含 fixture 的代號、`scope_key` 與 label 哨兵值。
```
- 方向：收緊（測試）。CEO：否。被取代的原文：無。

**L-8　FL-75（插入）**
- 插入點：`- **FL-55**` 開頭的那一行（L2840，1 處）**之後**。
```
- **FL-75**（N-63；D-3「適用範圍與缺項」N-63 子點；D-1 `volatility.py`；對應事先宣告 §2.1、§5.2）：
  - (a) 有效數：`valid_returns` 為 54、0 → `value`、`raw_std` 都是 None，`missing_code = E-VOL-SHORT`，不拋例外；55（非退化）→ `value = raw_std`，為正的有限值，`missing_code` 為 None。輸入含 None 的格，`valid_returns` 不計 None。
  - (b) 常數序列：60 個 0.0、60 個 0.1、55 個 ln(1.01)（其餘為 None）→ `raw_std == 0.0`（逐位），`value` 為 None，`missing_code = E-VOL-DEGENERATE`。
  - (c) 近常數：樣本標準差約 5e-4 的序列 → `value` 為 None、`E-VOL-DEGENERATE`，`raw_std` 為有限值，0 < `raw_std` < `SIGMA_FLOOR`。
  - (d) 輸入含 NaN 或 ±inf → `ValueError`；在記錄一步中依 FL-74 (f) 整步中止。
  - (e) 同一輸入呼叫兩次 → 結果逐位相同。
  - (f) `forecast_record` 寫入驗證：`label = insufficient`、含 `E-VOL-SHORT` 而 `sigma_d` 非 null → 拒絕；`sigma_d` 鍵不存在 → 拒絕；`valid_returns` 為 null → 拒絕；`E-VOL-SHORT` 與 `E-VOL-DEGENERATE` 並存 → 拒絕；`valid_returns` < `SIGMA_MIN_VALID` 而沒有 `E-VOL-SHORT` → 拒絕；`E-VOL-SHORT` 的 `available` ≠ `valid_returns` → 拒絕；`E-VOL-DEGENERATE` 的 `available` ≥ `SIGMA_FLOOR` 或非有限 → 拒絕；合規的兩格 → 接受，`up_pct`、`down_pct`、`sigma_d` 為 null。
  - (g) 記錄一步端到端：大盤 fixture 有效數 54 → 寫入 `label = insufficient` 一列，`band_def.sigma_d` 為 null、`valid_returns = 54`，`missing_json` 含 `E-VOL-SHORT`（`available = 54`），沒有拋 `LabeledThresholdSnapshotIncompleteError`；退化 fixture（60 個 0.0）同樣寫入，不被拒寫。
  - (h) 族群：`E-VOL-SHORT`、排除成員非空、`resolved` → `realized_label`、`diag_basket_with_excluded` 都是 null，依事先宣告 §4.3 (f) v0.23（V23-02）在 W 中放回，n 不變；同一 fixture 排除成員為空陣列 → 不放回。
  - (i) 資料流（AST／spy）：`band_def.sigma_d` 只取自 `SigmaEstimate.value`；`raw_std` 只出現在產生 `E-VOL-DEGENERATE` 缺項的單一函式；`app/` 內 `SigmaEstimate` 恰好一個定義，在 `volatility.py`。
```
- 方向：收緊（測試）。CEO：否。被取代的原文：無。
- 附註：(h) 和 FL-73 (f) 的語意重疊，但不引用 FL-73 的格號，以免另一位 TA 改號後對不上。

#### 二、對 ADR-0029 推播模板與失效條件的影響

| 新增項目 | 會不會進入推播或 `ops alert:` 行 | 失效條件 5 |
|---|---|---|
| `reason = write_rejected`、`record_error` | 不會（只在主 DB 的 `forecast_gaps`） | 不觸發 |
| `refused_scopes_json`、`error_class` | 不會（只在主 DB，`views` 與 API 不讀） | 不觸發 |
| 記錄一步中止 → E-3d，`exception_class` 有值 | 現有欄位，沿用 E-3d「拋出 Exception」那條觸發 | 不觸發 |
| 拒寫 → E-3d，`exception_class` 為 None | 現有欄位，N-46 已採用 | 不觸發 |
| **逾時 → E-3d，`exception_class` 為 None（新的發生情形）** | 現有欄位；ADR-0029 E-3d 的觸發列「型別化步驟結果標為失敗」已涵蓋，不屬於它所列的四種「非失敗」 | 不觸發；但推播次數增加，建議送風控知悉 |

- 每一步失敗只發一則（ADR-0029 D-7 規則）。中止之前有拒寫時，也只發中止那一則。
- `write_outcome` 照 E-3d 固定為 `unspecified`。
- 推播上限「每次執行不超過 7 則」不變。
- `forecast record run:` INFO 行不是 `ops alert:` 行。即使如此，落字也規定它不帶識別資訊。

#### 三、事先宣告需同步之處（只列，不寫；請 quant 判定）

- **P-1** §6.3「缺日」第 1 點（L1671）：`reason` 列舉要加 `write_rejected`、`record_error`。
- **P-2** §2.1 `sigma_d` 一行（L834）與常數表 `SIGMA_MIN_VALID`、`SIGMA_FLOOR`（L850-851）：
  - 有效數不足時不計算任何估計值，所以不評估退化，`E-VOL-SHORT` 優先；
  - floor 用嚴格小於；
  - 常數序列的估計值必須恰好為 0；
  - 無效日由呼叫端標示。
- **P-3** §5.2 `E-VOL-SHORT`、`E-VOL-DEGENERATE` 兩列（L1448-1449）：
  - 「現有」欄分別是 `valid_returns` 和 `raw_std`；
  - 兩個代碼互斥；
  - 退化值不存進 `threshold_snapshot.sigma_d`。
- **P-4** §6.1 `threshold_snapshot` 一列（L1510）：E-VOL 列的 `sigma_d` 為 null；`valid_returns` 一律照實記錄。
- **P-5** §6.3 V22-07 註（L1551）：可加一句「E-VOL 的證據不足列一律走本註的缺項路徑」。
- **P-6** §4.3 (f) V23-02（L1073）與另一面 ③（L1075）：族群 E-VOL 列只要排除成員非空，就一律在 W 中放回。這是收緊面，**要 quant 確認方向**。
- **P-7** §4.2 W 列（L1040）：「因籃子標籤不一致而放回者另列」底下，是否再分列 E-VOL 的筆數，由 quant 決定。
- **P-8** §5.1 第 3 點（L1437）：可補一個例子，「有效日報酬不足 55 個時，用現有筆數算 σ_d」也屬替代估法（quant 檔 L109 已經這樣寫）。
- **P-9** 附錄 C：補上對應 FL-75 的 LG 格。還有哪些 LG 格以缺日 `reason` 列舉為期望值，我沒有查（未查證）。
- **P-10** quant 檔 `work/reviews/2026-10-19-N53重放null規則提案-quant.md` L215 的更正（不屬於事先宣告本體）。
- 〔推論〕以上都沒有新增缺項代碼，也沒有改公式或常數值，依 §5.2 標題不用升版。這點請 quant 確認。

#### 四、與 v0.24 同步的衝突檢查

- 〔事實〕L-1～L-8 的插入點分別在 L252、L270、L300、L908、L1091、L1295、L2303、L2840，都不在 D-11、D-12、FL-45b、FL-68、FL-72 (h)、FL-73 範圍內，所以 ADR 字面沒有衝突。
- 〔推論，未查證 v0.24 內容〕P-5、P-6、P-7 落在 §6.3 V22-07、§4.3 (f)、§4.2 W 列，如果 v0.24 也改這幾行，就會衝突。請 coordinator 先對照 v0.24 稿，再決定 P 項併入 v0.24 還是另開 v0.25。

#### 五、修訂紀錄骨架（交 tech-writer）

- 段名：「記錄一步批（N-51、N-52、N-63；D-1 表一處、D-3 `forecast_run_end` 與『適用範圍與缺項』、D-7 第 7 點、D-8 第 2 點、D-9 第 6 點、FL-74、FL-75）」。
- 逐項的方向、CEO 層級與擋什麼，照第一節。
- 被取代的原文：全部是插入或句末接字，沒有被取代的原文。
- 待決事項：L4786 的 N-51，以及 L4787「還要等 N-51 定案，並由 dev-lead 確認 N-52」，風控確認後在句末加〔已決〕，原文不改。

#### 六、另外發現（不在本批落字內，請列入追蹤清單）

1. **同一個觀察日有多個 run 時，`reason` 依哪一個 run 判定，沒有定義。**
   - 〔事實〕D-8 第 2 點的六個值都是用單一 run 的狀態寫的。22:10、23:10 和啟動補跑可能各自留下一個 run，例如 22:10 拒寫、23:10 中止。
   - 候選規則：取 `run_id` 最大、而且範圍快照含該範圍的那一個 run。這個規則會動到現有的值，要另案送風控。
   - 擋 `audit.py`，不擋記錄一步。
2. **on-demand 寫入遇到 N-46 拒寫時怎麼處理，沒有定義。**〔事實〕D-7.8 的 POST 路徑同樣經過 store 的寫入驗證，但 API 的回應形狀和告警都沒寫。擋 on-demand 的實作，不擋排程。
3. **記錄一步在寫入 `forecast_run` 之前就失敗時，會被誤記成 `scheduler_down`。**〔事實〕D-8.2 規定「該日沒有任何 run：`scheduler_down`」。〔推論〕這種情形實際上是記錄一步失敗。這是現有缺口，本批沒有處理。
4. **`sigma_d()` 用的常數取自哪一版 dirdef，沒有寫。**〔事實〕D-1 只寫「取自 dirdef」，簽章沒有 `definition` 參數。`band.py` 的同類檢查是以參數取該列的版本。多版本並存之前要釘死。

#### 對實作的約束（逐條，qa-reviewer 可以檢查）

1. 記錄一步的範圍迴圈內，只能接 `RECORD_SCOPE_REFUSAL_TYPES` 裡的型別（FL-74 (a)(b)）。
2. 清單以外的例外：整步中止，盡力寫 run_end 後再拋原例外（FL-74 (e)(f)(h)）。
3. `forecast_run_end` 的新欄位與寫入驗證（FL-74 (j)）。
4. 缺日的 `write_rejected`、`record_error` 只依 run_end 判定（FL-74 (c)～(h)）。
5. 逾時與拒寫都只發一則 E-3d（FL-74 (c)(d)(g)）。
6. `SigmaEstimate` 契約，以及 `raw_std` 不得進入 `band_def`（FL-75 (a)～(e)(i)）。
7. E-VOL 列的寫入驗證（FL-75 (f)(g)）。
8. 禁止事項：
   - 以 `ForecastFailClosedError` 或 `Exception` 接住範圍內的例外；
   - `store.py` 接住清單內的型別；
   - 用 log、告警或 `forecast_record` 是否存在來推定拒寫；
   - 把 `raw_std` 寫進 `band_def`。

---

## 驗證

- 只用 Read、Grep。沒有 Edit、Write 或 commit，沒有讀 `.env`，沒有碰任何 `*.db`。
- **ADR-0027**（`/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`）讀過的段落：
  - L227-336：D-1、D-3 前段；
  - L644-733：`forecast_gaps`、`forecast_gap_audit`、`plan_coverage_log`；
  - L789-1100：D-7、D-8；
  - L1270-1321：D-9 第 5～7 點；
  - L2277-2316：FL-1～FL-61；
  - L2545-2626：FL-71～FL-73；
  - L4750-4789：修訂紀錄最後一段。
- **ADR-0027 用 Grep 確認的事**：
  - 章節標題；
  - `N-46`、`N-51/52/63`、`FL-74/75`（未被使用）、`write_rejected`（只在 L707）、`forecast_gaps`、`inputs_not_ready`、`缺日率`、`sigma_d(`／`SIGMA_*`／`E-VOL`；
  - 8 個插入點字串（`-o` 模式下各 1 處）。
- **ADR-0029**（`/home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md`）：讀了 L60-339（D-1 方向限制、D-2～D-10、Consequences、OA、失效條件）。
- **事先宣告**（`/home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md`）：
  - 讀了 §2.1（L828-867）、§4.3 (f)（L1073-1075）、§5.1 與 §5.2（L1429-1476）、§6.1 與 §6.3（L1490-1554）、缺日（L1666-1675）；
  - Grep 過 V22-07、V23-02、缺日 `reason` 列舉。
- **dev-lead 兩份查證**全文：
  - `/home/user/AICompany/work/reviews/2026-10-19-N52記錄一步範圍例外查證-dev-lead.md`
  - `/home/user/AICompany/work/reviews/2026-10-21-N63-sigma_d回傳與存值查證-dev-lead.md`
- **TA 先前回報**：`/home/user/AICompany/work/reviews/2026-10-19-N41-G2與N46落字起草-tech-architect.md` L150-229（含第六節）。
- **未查證**：
  - v0.24 同步稿的內容；
  - 附錄 C 中以缺日 `reason` 為期望值的 LG 格；
  - 程式碼本身（依 dev-lead 查證，記錄一步與 `volatility.py` 都還沒實作）；
  - 估計式在不同函式庫版本上的行為：只要求性質，不指定版本。

## 下一步

1. **coordinator**：把 L-1～L-8 送 risk-compliance-officer 逐字確認。要風控裁定的點：
   - (i) N-51 採新值 `write_rejected`，存放在 `forecast_run_end.refused_scopes_json`；是否接受和 `plan_coverage_log` 同名；
   - (ii) N-52 採 A 案；第 4 點採 `record_error`，不擴充 `job_error`；
   - (iii) 記錄一步逾時算失敗、發 E-3d（我的建議，偏離 dev-lead D-6）；
   - (iv) N-63 的兩面方向，以及 CEO 層級（我建議知悉）；
   - (v) `sigma_d()` 輸入含非有限值時拋 `ValueError`（備選：視為無效日）；
   - (vi) N-52 的 CEO 層級（我建議知悉，有停擺代價）。

   同時把第三節 P-1～P-10 轉給 quant，並對照 v0.24 稿確認 P-5～P-7 有沒有衝突。第六節第 1～4 點請列入追蹤清單。
2. **quant-researcher**：確認 P-6 的收緊方向（族群 W），決定 P 項併入哪一版；更正 quant 檔 L215。
3. **tech-writer**：風控確認後，依第五節骨架落檔。
4. **dev-lead**：定案後依 L-4、L-2、L-5 實作記錄一步、run_end 與稽核的 `reason`，依 L-3 實作 `sigma_d()` 與寫入驗證，FL-74、FL-75 一起交付，送 qa-reviewer 審查（含 Codex 第二意見）。第六節第 1 點定案之前，`audit.py` 遇到多個 run 時的 `reason` 判定先不要實作。

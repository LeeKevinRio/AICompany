# B1 暫定語意裁定（N115-10、N115-11）

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 1. 本次結論

我逐點裁定了 provisional 1～5，也看了第 6、7 項。

| 項 | 裁定 | B1 commit 前要不要修 | 風控 |
|---|---|---|---|
| 1 違規列舉兩份 | **要求改**：只留一份，定義在 `errors.py`，`band.py` 從它 import | **要，commit 前修** | 不觸及 |
| 2 `valid_returns` 為 bool 或非 int | **接受** | 不改程式，只更新 docstring 的出處 | 收緊；跟 N115-10 一起送風控輕量確認 |
| 3 `sigma_d` ≤ 0 記兩項，NaN 只記一項 | **接受**（各違規值各自判定） | 不改程式 | 不觸及（任何違規都拒寫，結果不變） |
| 4 超出 double 範圍的 int 當 ±inf | **接受** | 不改程式 | 不新增放寬。另有一個既有缺口要另立追蹤項，不擋 B1 |
| 5 `MissingItem` 反向條件加 `extra="forbid"` | **接受** | 不改程式，只更新 docstring | 收緊；跟 N115-11 一起送風控輕量確認 |
| 6 `SpanRegistrationGap.session_dates` | 接受，不需要改 ADR | 不改 | 不觸及 |
| 7 ops_alert | `job_id` **要求改**，只接受 `"forecast_record"`；E-2 那一列要更正說法；其餘接受 | `job_id` commit 前修 | 不觸及 |

ADR 的補字我新擬了兩項：**N115-10**（D-1 `band.py` 列、D-3 L345）和 **N115-11**（D-13）。程式先照裁定做，註記沿用 B1 的慣例寫「pending ADR landing」。CEO 層級：否。

## 2. 各部門回報

### tech-architect

#### 評估摘要

1. **第 1 項（單一來源）**
   - N-115 #13 接受「兩份加同表測試」，是因為改成一份要修 ADR-0029 的跨 ADR 邊界。這裡兩份都在 `app/forecast/` 同一個套件裡，沒有這種邊界理由，留兩份只會增加日後走鐘的風險。
   - dev-lead 說「兩者都只准 import 標準庫」，這句只對 `errors.py` 成立。ADR L239 的 `band.py` 本來就允許 import 標準庫以外的東西（「標準庫與 dirdef 常數」）。
   - 所以把唯一定義放在 `errors.py`：它照 L238 維持只 import 標準庫，`band.py` 增列一個窄的例外，從它 import。
2. **第 2～4 項**：讀法都和 D-3 L345 的字面、以及 N115-6 的「非數值當缺項」原則一致，而且都朝 fail-closed 方向。
3. **第 5 項**：D-13 的欄位註解寫了「fetch_failed only」「not_yet_published only」，反向條件只是把它寫明，屬於收緊。

#### 方案比較（第 1 項）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A 兩份加相等測試（現況） | 不必改 ADR | 同一個封閉列舉有兩個定義；之後 `store.py` 的寫入驗證等模組會各自挑一份 import | 有人只改一份時，要等測試抓 |
| **B 定義在 `errors.py`，`band.py` 從它 import（採用）** | 只有一份；`errors.py` 仍只 import 標準庫；`errors.py` 沒有 import 任何東西，不會形成循環 | `band.py` 的 import 範圍多一個例外 | 低，用 AST 把例外釘死在兩個名稱 |
| C 定義在 `band.py`，`errors.py` 反向 import | 列舉和產生它的函式放在一起 | 違反 L238「只 import 標準庫」；例外模組會依賴計算模組，方向顛倒 | 否決 |
| D 另立 `violations.py` 葉模組 | 兩邊對稱 | 多一個模組，要改兩列 D-1 | 過度設計 |

#### 決策（ADR 草案：補進 N-115 第一批）

**N115-10a｜D-1 `band.py` 列（L239）｜句末接字**
old（Grep -o 確認 1 處，L239）：
```text
`app/outlook/volatility.py`，不讀 DB。
```
new：
```text
`app/outlook/volatility.py`，不讀 DB。（N-115）上述 import 範圍的唯一例外：另 import `app.forecast.errors` 的 `ThresholdViolation`、`THRESHOLD_VIOLATION_ORDER`，不 import 該模組的其他名稱；違規值的封閉列舉在 `app/` 內恰有這一個定義（AST、grep）。
```
- 這處 old 和 N113-2 的 old（「只 import 標準庫與 dirdef 常數；不 import」）在「不 import」三個字上相鄰，但不重疊。兩者落檔的先後不影響結果，各自的 old 落檔前後都只有 1 處。

**N115-10b｜D-3「適用範圍與缺項」`label ≠ insufficient` 項（L345）｜句末接字**
old（Grep -o 確認 1 處，L345）：
```text
回傳值依此順序排列、不重複。
```
new：
```text
回傳值依此順序排列、不重複。（N-115）各違規值依括號內的條件各自判定，同一列可以同時記多項：`sigma_d` 為 0、負值或 −inf 時，同時記 `sigma_d_not_positive_finite` 與 `sigma_d_below_floor`；NaN 與 +inf 只記 `sigma_d_not_positive_finite`（NaN 與任何值比較都不成立，+inf 不小於 `SIGMA_FLOOR`）。`valid_returns` 為 `bool`，或不是 `int`（含 `30.0` 這類 `float`）時，與 null 同樣處理，記 `valid_returns_below_min`。超出 IEEE 754 double 範圍的 `int`（`float()` 會拋 `OverflowError` 者）依符號視為 ±inf，不拋例外，`threshold_inputs()` 與本函式都以這個值判定。本列舉（`ThresholdViolation`、`THRESHOLD_VIOLATION_ORDER`）在 `app/` 內只定義在 `app/forecast/errors.py`，`band.py` 與 `LabeledThresholdSnapshotIncompleteError` 的屬性驗證共用這一份（D-1 `band.py` 列）。
```

**N115-11｜D-13 不變式（L2369、L2370）｜兩處取代**
old 1（Grep 計次 1 處，L2369）：
```text
`fetch_failed` 必有 `attempted_at`；
```
new 1：
```text
`attempted_at` 非 None 若且唯若 `source_status` 為 `fetch_failed`（N-115：本節欄位註解「fetch_failed only」的明文化，反向同樣強制）；
```
old 2（Grep -o 確認 1 處，L2370）：
```text
`not_yet_published` 必有 `latest_available`。
```
new 2（第二行是新增的同層項目，縮排比照 L2367-2370 的「  - 」）：
```text
`latest_available` 非 None 若且唯若 `source_status` 為 `not_yet_published`（同上，「not_yet_published only」）。
  - （N-115）後三項由 `app/outlook/missing.py` 的 model validator 強制（FL-39），第一項是整筆紀錄的不變式，不在本型別內判定。`MissingItem` 為 frozen、`extra="forbid"`，每個欄位都沒有預設值；讀回既有的 `missing_json` 時，含未宣告的鍵或違反上列不變式的項目同樣不能載入，不略過、不補值。
```

**修訂紀錄（插在第一批修訂紀錄「逐項」的 N117-8 那一條之後、「本段」之前；文字刻意不含「N-115」字樣）**
```text
  - N115-10 D-1 `band.py` 列的 import 例外與 D-3 違規值的判定細則（B1 provisional 1～4，tech-architect 2026-10-24 裁定）：方向：補定義（不變：違規值的封閉列舉與順序不變，只定唯一定義處；各違規值獨立判定是 L345 括號條件的字面；收緊：`valid_returns` 的非整數算 null）。CEO：否。句末接字，無被取代原文。
  - N115-11 D-13 反向不變式與 `extra="forbid"`（B1 provisional 5）：方向：補定義（收緊：欄位註解「only」改為若且唯若；不接受未宣告的鍵）。CEO：否。被取代的原文——
    > `fetch_failed` 必有 `attempted_at`；
    > `not_yet_published` 必有 `latest_available`。
```
照實並陳要加兩條：
```text
  - N115-10：`threshold_inputs()` 對 `K_h`、`EPS` 只判斷「有沒有、是不是數值」，所以 ±inf、NaN（含由超大 `int` 換算出的 ±inf）的 `K_h`、`EPS` 會被判為完整。這是既有缺口（風控 2026-10-24 對 N115-6 的 suggested），不是本項造成的：經 store 寫入的列，D-3 L344「不論 label 逐位相等」會擋下；有標籤的列由 `labeled_snapshot_violations()` 記 `*_mismatch`、fail-closed。改這一點等於改事先宣告 V22-07 唯一實作的判準，另列後續追蹤，本批不定義。
  - N115-11：`extra="forbid"` 使 D-13 日後刪除或改名欄位時，既有 `missing_json` 讀不回來，必須搭配遷移；D-13 的欄位變動本來就要修訂本節。
```
**計數**：第一批本文的 `N-115` 會增加 4 處（10a、10b、11 各 1 處，11 的第二行再 1 處），修訂紀錄不增加。草稿第三節表格「第一批後 23（本文 20、紀錄 3）」要在 N115-9 改完後的值上再加 4，由 tech-writer 落檔時重算。

#### 逐點裁定

1. **要求改，B1 commit 前修。** 改法見下面約束 C1～C5。不觸及風控。
2. **接受。** D-3 L345 的括號定義是「null 或小於 `SIGMA_MIN_VALID`」，把非 int 當 null 是 N115-6 讀端原則的延伸。結果是多記違規、拒寫，屬於收緊，所以和 N115-10 一起送風控輕量確認。程式不改。
3. **接受。** L345 寫的是「`sigma_d` 小於 `SIGMA_FLOOR`」，0 和負值依字面確實低於下限。改成互斥反而會讓兩個判斷互相牽連。只要有任何一項違規就拒寫，所以這只影響例外屬性的診斷內容。不觸及風控。
4. **接受。** 這和 Python `json` 把 `1e400` 解析成 inf 的語意一致。`sigma_d` 會走缺項，`K_h`、`EPS` 會判成不相符，都是 fail-closed。照實並陳裡那個既有缺口另立追蹤（見第 4 節），不擋 B1。
5. **接受**，依據見上。只是把型別的不變式收緊，沒有新增 `SourceStatus` 的值、也沒有改模板，所以不用送字面審，quant 也不需要同步。
6. **接受。** ADR L1365 只說「它所見的日期」，取什麼名字屬實作裁量，不需要改 ADR。
7. ops_alert：
   - **`job_id`：要求改，B1 commit 前修。** ADR-0029 L193、L205 都寫明只處理 `job_id == "forecast_record"`，其他 job id 不推播。現在檢查「小寫識別字」，等於讓 listener 的過濾一出錯，別的 job id 就能進到推播內文。改成 `JobSkippedPayload` 只接受常數 `"forecast_record"`，其他值拋 `ValueError`，並各補一格測試（`"forecast_record"` 通過、`"forecast_recordx"` 被拒、`"other_job"` 被拒）。這是收緊，不觸及風控。
   - **E-2 `correction`／`deferred`：接受現狀（拒絕，有測試釘住），但「上線那批要反轉」的說法要更正。** 依 ADR-0029 L216-217，只有在 ADR-0027 N-23 第二批經 CEO #42 明示同意並落檔後才能反轉。CEO 不同意時不得反轉，要修訂 ADR-0029 並送風控重審。docstring 已寫對，請在交件和測試註解裡用同樣的條件句。
   - **selftest payload 沒有欄位：接受。** 固定自測欄位要和 render 一起定，並依 ADR-0029 D-10 第 8 項送風控知悉級確認。
   - **兩個 `recorded_at` 只檢查非空：接受。** ADR-0029 L223-224 規定是「存下的原字串」。建議（不擋 B1）：render 批要處理原字串裡的換行和控制字元，避免破壞固定格式的推播行，由 devops-sre 負責。

#### 對實作的約束（qa-reviewer 可以逐條檢查）

- C1：`app/` 內 `ThresholdViolation` 和 `THRESHOLD_VIOLATION_ORDER` 的賦值定義各恰 1 處，都在 `app/forecast/errors.py`（AST 或 grep）。
- C2：`band.py` 對 `app.*` 的 import 恰為 `from app.forecast.errors import ThresholdViolation, THRESHOLD_VIOLATION_ORDER`，沒有其他 `app.*`。`band.py` 不 re-export 這兩個名稱：不用 `X as X`，也不列進 `__all__`。`TYPE_CHECKING` 區塊內的 import 也要納入掃描。
- C3：`test_the_two_copies_of_the_violation_list_are_identical` 改成上面 C1、C2 的格，各自要有會失敗的對照組（teeth）。`test_leaf_modules_import_the_standard_library_only` 對 `band.py` 只放行 C2 那一行，對 `errors.py`、`model.py` 維持只准標準庫。
- C4：測試和其他模組一律從 `app.forecast.errors` import 這兩個名稱。`tests/test_forecast_band.py:21` 現在從 `band` import，要改；`mypy --strict` 的 no-implicit-reexport 本來也會擋。
- C5：`band.py`、`errors.py`、`missing.py` 的 docstring 移除「open question」「this module's own reading」，改成「per tech-architect B1 provisional ruling (N115-10 / N115-11), pending ADR landing」。
- C6：`JobSkippedPayload.job_id` 只接受 `"forecast_record"`（見第 7 項）。
- C7：第 2～5 項的現有行為和測試保留：bool 或非 int 的 `valid_returns`、0／負值／−inf／NaN／+inf 的 `sigma_d` 各一格、超大 int 一格、`MissingItem` 的反向條件和多餘鍵各一格。缺哪一格就補。

## 3. 驗證

- **讀過的檔案**：
  - `/home/user/AICompany/work/reviews/2026-10-24-ADR0027-B1實作-dev-lead.md`
  - `/home/user/AICompany/work/reviews/2026-10-24-N113N114N115澄清起草-tech-architect.md`（全文）
  - `/home/user/AICompany/work/reviews/2026-10-24-N113N115N117第一批輕量確認-風控.md`
  - ADR-0027 L230-257、L338-365、L2347-2389
  - `/home/user/AICompany/apps/stock-desk/backend/app/forecast/band.py`（全文）
  - `/home/user/AICompany/apps/stock-desk/backend/app/forecast/errors.py`（L1-120）
  - `/home/user/AICompany/apps/stock-desk/backend/app/outlook/missing.py`（全文）
  - `/home/user/AICompany/apps/stock-desk/backend/app/ops_alert/model.py`（L15-64、L210-299）
- **用 Grep 查過**：
  - ADR-0029 的 selftest、`job_id`、`recorded_at`、CEO #42 相關列（L193、L205、L216-217、L223-224）。
  - 四個 old 在 ADR-0027 各恰 1 處：L239、L345、L2369、L2370。
  - ADR-0027 的 `N-115` 目前 0 處，所以 N-115 尚未落檔。
  - 待落檔的 N113-1 修訂稿與 N115-9 的 old 都不碰 L345、L2369-2370；L239 和 N113-2 只是相鄰、不重疊。
- **沒有做的事**：沒有實際執行 `float(10**400)`，只依 Python 語意推論；沒有讀 `.env`，沒有碰 `*.db`，沒有寫檔，沒有跑指令。

## 4. 下一步

1. **dev-lead**：在 B1 commit 前依 C1～C6 修改，重跑 ruff、mypy 和 pytest（含覆蓋率），改完的 diff 再交 qa-reviewer。
2. **coordinator**：把 N115-10、N115-11 併進第一批的 N-115 部分，跟方案甲或乙都相容；只把這兩項送風控輕量確認，已核可的 N-115 各項不重審。
3. **tech-writer**：落檔時套用上面的 old→new 和修訂紀錄兩條，並重算 `N-115` 的計次。
4. **追蹤清單新增一項**（編號由 coordinator 給）：「`threshold_inputs()` 對非有限的 `K_h`、`EPS` 的判定」。由我起草，要 quant 同步事先宣告 V22-07、送風控。不擋 B1，但要在 `scoring.py`、`settlement.py` 開始讀 `band_def` 的批次前定案。
5. 第 7 項 E-2 那一列：反轉的前提是 CEO #42 明示同意，加上 ADR-0027 N-23 第二批落檔。這個條件由 coordinator 在排上線批次時核對。

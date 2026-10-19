# ADR-0029 架構審查（M-1～M-14）

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0029 審查結果（tech-architect，2026-10-18，唯讀）

## 一、本次結論

**結論：修改後核可，不否決。** 架構主體成立：中性套件、必填注入、共用傳輸、不存跨執行狀態、不設開關，與 ADR-0027／0026／0002 方向一致。不過【待 TA 確認】各項裡，有 3 項要改，另外查到 4 處實質缺口。下列 M-1～M-14 套用之後，ADR-0029 才可送 CEO（事項 #43），OA-23 也才可實作。

逐項裁定：
1. **`write_outcome` 列舉**：五個值保留，但定義要收緊，並改成逐列的「適用對照」表。
   - `not_written` 原寫「沒有留下列」，這不屬實。E-1 結算時，③ 的查證紀錄與 X2 確認是各自獨立 commit 的；E-1 更正作業時，③ 的 `forecast_correction_job` 開始列與登記也已經 commit（ADR-0027 D-9.2 ③、D-9 第 5 點 ③）。
   - `written_without_registration` 只用在 E-2 `audit`，而且只在缺日稽核 commit 之後發出。
   - `unspecified` 擴大到 E-3d 的全部 step：任意例外是在哪裡拋出的，編排函式無法從型別判定。
   - selftest 的 `write_outcome` 為 None。
2. **`step` 名稱**：七個名稱確認。
3. **`source` 在 E-3b、E-3d 為 None**：確認。E-3c 為 `settlement`，也確認。
4. **E-3b 去重鍵改用被略過的觸發時刻：不採用。** 改為：`execution_started_at` 為 None 的告警一律不去重，也不讀、不改鍵集合。理由：listener 在 scheduler 的派送執行緒上執行；`max_instances` 事件發生時，正好有一次執行在跑。照草案「收到不同執行識別的告警就整個換掉鍵集合」，執行中的那一次之後的告警會被重複推播，而且兩個執行緒會同時改同一個集合。
5. **OA-23**：改寫成「適用對照表逐列一格、表外組合拒絕」，【待 TA 確認】標記拿掉。
6. **`deliver()`／`emit()` 拆分：不違反「實作恰好一個」**，前提有三：`deliver()` 在同一個類別上、不屬於 Protocol、只能由 `sink.py` 與 `selftest.py` 呼叫（AST）。另外，D-1「送出器只在 `scheduler.py` 建立」與 selftest 要自己建立送出器互相矛盾，要改（M-7）。

另外查到的 4 處實質缺口：
- **(a) E-2 `source = correction`／`deferred` 依附的 ADR-0027 字面還不存在。** ADR-0027 第一批只套用了守衛定義與缺日稽核子點。D-3 第 8 點現行字面仍是「其餘觸發照常」，等 CEO #42 同意後的第二批才改。所以這一列要加落檔前提（M-10）。
- **(b) `OpsAlert` 建構失敗時會中止後續步驟。** 建構發生在 `emit` 之外，`ValueError` 會從編排函式的 except 區塊逃出，違反 OA-7（M-5）。
- **(c) `OPS_ALERT_PUSH_MAX_CHARS` 放在哪裡，與 import 規則矛盾。** model 只可以 import 標準庫，push_channels 又不可以 import ops_alert。所以兩個通道的上限只能放在 push_channels，最終上限在 sink 計算，再以參數傳給 render（M-8）。
- **(d) selftest 拿不到時鐘。** `occurred_at` 必填，但 `app/ops_alert/**` 禁止呼叫 `datetime.now`，`selftest.py` 也在這個範圍內（M-2）。

**禁用詞清單的單一來源（裁定，請 dev-lead 確認可行）**：唯一來源就是 ADR-0027 FL-71 (f) 的「推播禁用詞清單」區塊。測試在執行時以起訖錨點從 ADR 讀出，不新增清單檔，也不寫進 `shared/forbidden-terms.json`。

**與 ADR-0027 的一致性**：以下各項都逐字相符：
- `ops_alert_sink`、`app.ops_alert.model.OpsAlertSink`；
- import 限制（L782、D-1 表 L237-239）；
- `forecast.step.failed`、`forecast record run:`、`ops alert:`；
- E-2 例外屬性（L1105）、E-1 屬性（L1130-1134）。

E-2 改名為 `forecast.market_run_regressed` 不會和 ADR-0027 衝突：ADR-0027 全檔沒有出現 E-1、E-2 的事件字串（grep `forecast\.(settle|job|step|market)` 只命中 `forecast.step.failed` 與一個模組路徑）。但 E-1 的 source 同樣含 `correction`，照同一個理由要改名（M-11）。

**字面五的指向成立**：L775 現為「告警規格依 ADR-0029（維運告警通道）」，由 ADR-0029 D-6 與 E-3b 承接。條件是 ADR-0029 不晚於字面五落檔。

**與 ADR-0026、ADR-0002 沒有衝突。** 只有一處引用錯誤：「ADR-0026 D-9.2 第 2 點」應為「D-9 第 2 點（備份組）」。

**補充項 R-Q7-3、R-Q3-3、R-Q7-5、C6／C25**：已在 /home/user/AICompany/work/reviews/2026-10-18-N23風控補充項回覆-tech-architect.md 回覆過，本次略過。為了和 ADR-0029 一致，那份回覆要修兩處（見第二節 C）。

## 二、各部門回報（tech-architect）

### 評估摘要
- **採用**：
  - 逐列的適用對照表；
  - `execution_started_at` 為 None 的告警不去重；
  - 建構點加 try/except；
  - 通道上限常數放在 push_channels，最終上限在 sink 計算；
  - 禁用詞以 ADR-0027 FL-71 (f) 為唯一來源。
- **否決**：
  - 以 `skipped_run_times` 當 E-3b 的去重鍵；
  - 由編排函式對 E-3d 斷言寫入狀態；
  - 新增或擴充 `shared/` 下的清單檔；
  - 在 ADR-0027 第二批落檔前實作 E-2 `correction`。

### 方案比較
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| E-3b 甲：以 `skipped_run_times` 為鍵（devops-sre） | 鍵的形態統一 | 會換掉執行中那一次的鍵集合；兩個執行緒同時改同一個集合 | 重複推播；競態 |
| **E-3b 乙：識別為 None 就不去重、不碰集合（採用）** | 和進行中的執行互不干擾；APScheduler 對同一個觸發時刻只送一次事件 | 理論上可能重複一則 | 低（只多推，不少推） |
| E-3d 甲：依 step 斷言 `not_written` | 推播的資訊比較多 | 例外可能在 commit 之後才拋出，斷言不可證 | 推播內容不屬實 |
| **E-3d 乙：一律 `unspecified`（採用）** | 屬實 | 操作者要自己查 log 與 DB | 低 |
| 禁用詞甲：測試從 ADR 區塊讀取（採用） | 真正單一來源；改清單一定要修 ADR，因而會送風控 | 要寫錨點解析；錨點字串一改就要跟著改測試 | 解析錯誤（以 fail-closed 處理） |
| 禁用詞乙：另建 JSON 作為來源，ADR 只寫指向 | 機器可讀 | 改清單繞過 ADR 與風控鏈；ADR-0027 要再改一次 | 治理變弱 |
| 禁用詞丙：併進 `shared/forbidden-terms.json` | 少一個檔 | 「漲」「跌」「正常」「最新」在使用者面有合法用途（例如持倉漲跌欄，ADR-0016），會誤擋產品文案 | 誤擋產品文案 |

### 決策：給 devops-sre 的照改清單（ADR-0029 逐字字句；定位字串以檔內原文為準）

**M-1｜D-2 `execution_started_at` 列**
- 定位字串：`該次執行的所有告警共用同一個值。E-3b 為 None（沒有執行可言）`
- 改為：
> 該次執行的所有告警共用同一個值。E-3b、`step = orchestrator` 的 E-3d、selftest 為 None：E-3b 沒有執行可言；`step = orchestrator` 由 `scheduler.py` 的 job 包裝發出，拿不到編排函式讀到的值，不另讀時鐘代替

**M-2｜D-2 `occurred_at` 列**
- 定位字串：`UTC ISO8601。取自編排函式持有的 store 時鐘；`
- 從這裡到該格結尾，整格改為：
> UTC ISO8601。編排函式發出的告警，取自它持有的 store 時鐘；E-3b 與 `step = orchestrator` 的 E-3d，取自 `scheduler.py` 組裝時注入 listener 與 job 包裝的同一個 store 時鐘；selftest 為 None。`app/ops_alert/**`（含 `selftest.py`）不呼叫 `datetime.now`／`time.time`（AST）

**M-3｜D-2 三列與規則 4**
- `| `source` |` 列的內容改為：
> 列舉 `settlement`／`audit`／`correction`，或 None；取值依規則 4「適用對照」。E-1、E-2 的值與 ADR-0027 例外屬性或守衛呼叫端的 `source` 逐字相同
- `| `step` |` 列改為：
> 列舉 `record`、`settlement`、`gap_audit`、`late_scan_correction`、`validation_snapshot`、`plan`、`orchestrator`，或 None；前六個依序對應 ADR-0027 D-7 第 2 點的六步。取值依規則 4「適用對照」
- `| `write_outcome` |` 列改為：
> 封閉列舉 `not_written`、`written_without_registration`、`deferred`、`not_started`、`unspecified`，或 None（只限 selftest）；定義與取值依規則 4「適用對照」
- 規則 4（定位字串 `4. `write_outcome` 的列舉、`step` 的名稱與 `source` 的適用對照`）整點換成：
> 4. **適用對照**（tech-architect 2026-10-18 確認）。表外的組合在 model 建構時拒絕（OA-23）：
>
> | 事件 | `source` | `step` | `write_outcome` |
> |---|---|---|---|
> | E-1 | `settlement` | `settlement` | `not_written` |
> | E-1 | `correction` | `late_scan_correction` | `not_written` |
> | E-2 | `settlement` | `settlement` | `not_written` |
> | E-2 | `audit` | `gap_audit` | `written_without_registration` |
> | E-2 | `correction` | `late_scan_correction` | `deferred`（落檔前提見 D-7 規則） |
> | E-3b | None | None | `not_started` |
> | E-3c | `settlement` | `settlement` | `not_started` |
> | E-3d | None | 七個 `step` 值之一 | `unspecified` |
> | `ops_alert.selftest` | None | None | None |
>
> - `not_written`：該步的結果寫入交易已 rollback；`forecast_outcome`、`forecast_settle_eval`、`forecast_correction_job_end`、`forecast_void_late_diag` 沒有新列（ADR-0027 FL-71 (c)）。同一步先前以獨立交易 commit 的列不在此限：結算評估 ③ 的查證紀錄與 X2 確認（①′ 成立時沒有這些列），以及更正作業 ③ 的 `forecast_correction_job` 列與未觀察平日登記。
> - `written_without_registration`：缺日稽核已 commit `forecast_gaps` 與 `forecast_gap_audit`，但沒有做 A-77 第 10 項登記（ADR-0027 D-7 第 2 點 Q7）。只在缺日稽核 commit 之後發出；缺日稽核拋例外時改發 E-3d，不發 E-2。
> - `deferred`：更正作業本次不啟動，四類觸發延後，W、W_E、W_V、W_S 都不前進。
> - `not_started`：該步沒有啟動，沒有寫入。E-3b 指的是整個 job 的該次觸發。
> - `unspecified`：編排函式無法斷言該步留下哪些列。E-3d 一律用這個值，因為任意例外的拋出位置無法由型別判定；各步實際的寫入由 ADR-0027 的 FL 格保證。

**M-4｜D-3 第 2 點的 E-3b 子點**
- 定位字串：`E-3b 沒有 `execution_started_at`，改以被略過的觸發時刻`
- 整個子點換成以下兩點：
> - `execution_started_at` 為 None 的告警（E-3b、`step = orchestrator` 的 E-3d、selftest）不去重，每次 `emit` 都推播，也不讀、不改鍵集合（tech-architect 2026-10-18 裁定）。理由：E-3b 由 scheduler 的派送執行緒呼叫，`max_instances` 事件發生時正有一次執行在跑，若以它換掉鍵集合，執行中的那一次會重複推播；APScheduler 對同一個觸發時刻只送一次事件；`step = orchestrator` 每次 job 呼叫至多一則。
> - 鍵集合的讀寫以 `threading.Lock` 保護。這個鎖只保護行程記憶體內的集合，不構成跨執行狀態。

**M-5｜D-3 新增第 10 點**
- 位置：接在 `9. 同步呼叫，不開執行緒、不建佇列` 那一點之後。
> 10. **建構失敗不中止流程**：`OpsAlert` 在 `emit` 之外建構，建構失敗（D-2 規則 2 的 `ValueError`）不在 `emit` 的保證範圍內。`recorder.py` 與 `scheduler.py` 的每一個建構點，都以 `try/except Exception` 包住建構與 `emit` 呼叫。建構失敗時記一行 ERROR `ops alert build failed: event=<列舉值> error_class=<類別名>`，不含例外字串，不拋、不中止後續步驟。`exception_class` 一律取 `type(exc).__name__`；不符 D-2 規則 1 的格式，或長度超過常數 `OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS`（128）時，以固定值 `invalid_exception_class` 代替，不讓建構失敗。
- 同時改 D-2 規則 1。定位字串 ``並以 `^[A-Za-z_][A-Za-z0-9_.]*$` 驗證。``，改為：
> 並以 `^[A-Za-z_][A-Za-z0-9_]*$` 驗證（取 `type(exc).__name__`，見 D-3 第 10 點）。

**M-6｜D-9 的 deliver 句**
- 定位字串：`（實作可讓 sink 另提供回傳逐通道結果的 `deliver()`，`emit()` 在其上加去重與吞例外；細節由 dev-lead 定）`
- 改為：
> （同一個 sink 類別另提供 `deliver(alert)`，回傳逐通道結果：與 `emit()` 共用同一組 log、render 與送出程式，不去重，同樣不拋例外；逐通道結果只含通道名稱、`sent`／`skipped`／`failed`、`error_class`、`status`。`deliver()` 不屬於 `OpsAlertSink` Protocol；在 `app/` 內只可由 `sink.py` 本身與 `selftest.py` 呼叫（AST）；`app.forecast.*` 與 `scheduler.py` 只呼叫 `emit()`）

**M-7｜D-1 方向限制的最後一點**
- 定位字串：`送出器實作只在 `scheduler.py` 組裝處被建立；`
- 整點改為：
> - 送出器實作只在 `scheduler.py` 組裝處與 `app/ops_alert/selftest.py` 中建立（AST 列舉建構點）。`app/` 內 `OpsAlertSink` 的實作恰好一個：`app/ops_alert/sink.py` 中明示繼承 `OpsAlertSink` 的那一個類別。`app/` 內其他類別不得定義參數註記為 `OpsAlert` 的 `emit`（AST；`logging.Handler.emit` 之類不受影響）。同一類別另有 `deliver()`（D-9），不構成第二個實作。測試用的 fake 放在 `tests/`，不放在 `app/`。
- OA-3 驗證欄後接：`；實作的判定方式依 D-1 最後一點`。

**M-8｜長度常數的位置**
- D-1 model 列，定位字串 `、推播長度常數 |`，改為：
> 、`OPS_ALERT_PUSH_MAX_LIST_ITEMS`、`OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS` |
- push_channels 列內容末尾加：`；兩個通道的單則上限常數，以及其出處網址與查證日的字串常數`。
- sink 列內容末尾加：`；`OPS_ALERT_PUSH_MAX_CHARS`（由 push_channels 的兩個上限與安全餘量常數計算）`。
- render 列內容末尾加：`；推播上限以參數接收`。
- D-4，定位字串 `查證後，兩個通道的數值與出處（網址與查證日）寫入`，整點改為：
> 查證後，兩個通道的數值寫入 `app/push_channels.py` 的常數；出處網址與查證日寫成同一檔內的字串常數，每個通道各一組（名稱由 dev-lead 定）；並補進本 ADR 的修訂紀錄。`OPS_ALERT_PUSH_MAX_CHARS` 定義在 `app/ops_alert/sink.py`，由這兩個常數與 `OPS_ALERT_PUSH_SAFETY_MARGIN_CHARS`（值與理由由 devops-sre 於查證時定）**計算得出**，不另外手打數字。`render` 以參數接收上限，不 import `app.push_channels`（D-1）。
- OA-13 的「兩個通道上限帶官方出處與查證日（缺則測試失敗）」改為：
> 兩個通道上限的出處與查證日字串常數存在且非空（缺則測試失敗）

**M-9｜D-4 的單一來源**
- 定位字串：`該位置是否即為測試讀取的「單一來源」，仍**【待 tech-architect 與 dev-lead 確認】**`
- 整個子點換成：
> - **單一來源**（tech-architect 2026-10-18 裁定；可行性由 dev-lead 確認）：清單的唯一來源是 ADR-0027 FL-71 (f) 的「推播禁用詞清單」區塊。測試在執行時讀取該 ADR 檔，以起訖錨點 `**推播禁用詞清單**`、`**白名單例外**` 截取區塊，從中取出：A、C、D 類的「」詞，A 類的 regex，C 類的英文詞界清單，F 類的反引號字串。B 類照清單所寫，讀 `apps/stock-desk/shared/forbidden-terms.json` 的 `guarantee`、`price_target` 與 `FRONTEND_FORBIDDEN_TERMS`，沿用後端測試既有的讀取函式，不另抄。E 類，以及 F 類的假 token、假 URL、哨兵字串，由 fixture 提供。錨點找不到，或 A～D、F 任一類取出 0 筆時，測試失敗。不新增清單檔，也不把 A、C、D 類加入 `shared/forbidden-terms.json`：該檔是使用者面措辭的共用清單，「漲」「跌」「正常」「最新」等字在使用者面有合法用途。dev-lead 若判定以 ADR 文字為測試來源不可行，退回 tech-architect 改案，不得自行另建第二份清單。
- OA-12，定位字串 `掃描清單讀自單一來源，測試內不手抄`，改為：
> 掃描清單依 D-4「單一來源」一點，於測試執行時讀取，測試內不手抄；錨點找不到或任一類取出 0 筆即失敗

**M-10｜D-7 規則新增三點，並改一處引用**
- 以下三點加在「規則」清單末尾：
> - **E-2 `source = correction` 的落檔前提**：本列（`write_outcome = deferred`）依附 ADR-0027 D-7 第 2 點 Q7 的「更正作業」子點，以及 D-3「晚到資料的觸發」第 8 點的改字，兩者都屬 ADR-0027 第二批，要等 CEO #42 明示同意後才落檔。第二批落檔之前，ADR-0027 現行字面是「其餘觸發照常」，更正作業照常啟動，不符 `deferred`，所以本列與 OA-10 的 `correction` 格在第二批落檔前不得實作（correction.py 本來就擋 D-9）。CEO 不同意時，本列與 OA-10 依 ADR-0027 屆時的字面修訂：本 ADR 仍為 proposed 時原地修訂，已 accepted 時開新 ADR；並送風控知悉。
> - E-2 `source = audit`／`correction` 的欄位，取自 `market_run_regression()` 回傳的 `MarketRunRegression`，屬性 `market_run_current`、`reference_kind`、`reference_value`、`reference_id`、`reference_started_at`，與 `MarketRunRegressedError` 的同名屬性逐字一致；`source` 由呼叫端決定。
> - 後續追蹤清單 N-20 若在 ADR-0027 增列 E-2 的屬性（tech-architect 2026-10-18 補充項回覆第 3 項：`regression_kind`、`reference_recorded_at`、`current_recorded_at`），屬於失效條件 5，與 N-20 同批送風控。
- 引用更正。定位字串 `讓操作者對照 ADR-0026 D-9.2 第 2 點備份 manifest`，改為：
> 讓操作者對照 ADR-0026 D-9 第 2 點（備份組）的 manifest
- 檔頭「與既有 ADR 的關係」第 11 行末尾加：`；E-2 的 `audit`／`correction` 另對應 D-7 第 2 點 Q7 守衛的回傳值 `MarketRunRegression``。

**M-11｜E-1 改名**
- 全檔 `forecast.settle.unregistered_unobserved_weekday` → `forecast.unregistered_unobserved_weekday`（理由同 E-2：source 含 `correction`）。
- 設計稿同步改，舊字留在修訂紀錄。

**M-12｜E-3d 涵蓋「失敗結果」**
- D-7 E-3d 的觸發格，在「任一步拋出 E-1／E-2 以外的 `Exception`」之後插入：
> ，或該步回傳的型別化步驟結果（ADR-0027 D-7 第 2 點 Q8）標為失敗（這時 `exception_class` 為 None；前置條件不成立而略過、沒有觸發而不啟動、`inputs_not_ready`、E-2 守衛成立，都不屬於失敗）
- 同一格的 payload，`（只放類別名，不帶例外字串）` 改為：
> （`type(exc).__name__`，不帶例外字串；失敗結果時為 None）
- 依據：ADR-0027 L780 對「一步失敗」的定義包含「回傳非成功的結果」，不納入的話，這類失敗的推播是靜默的。

**M-13｜OA 修正**
- OA-6 的「欄位只取自 ADR-0027 的例外屬性」改為：
> 欄位只取自 ADR-0027 的例外屬性或 `MarketRunRegression` 的屬性（`unregistered_count` 由 `len(unregistered_session_dates)` 導出）
- OA-11 句末接：
> ；E-3b 與 `step = orchestrator` 不去重：同一個事件物件呼叫兩次 → 推播 2 則；E-3b 發生在一次執行進行中 → 該執行其後的同鍵告警仍只推 1 則（鍵集合不被換掉）
- OA-20 句末接：
> ；回傳失敗結果的步驟 → E-3d 一則、`exception_class` 為 None；前置條件不成立、沒有觸發、`inputs_not_ready` → 0 則；守衛成立後缺日稽核拋例外 → E-3d、不發 E-2
- OA-23 整列換成：
> | OA-23 | D-2 規則 4「適用對照」表逐列一格可建構；表外的 (事件, source, step, write_outcome) 組合與列舉外的值，model 建構時拒絕；D-3 第 10 點：建構失敗 → 記 `ops alert build failed`，後續步驟照常執行（缺日稽核照常寫入）；`exception_class` 不合格 → 代以 `invalid_exception_class` | 單元測試 | D-2、D-3 第 10 點 |
- 建議（不擋）：OA-1 開頭改為「`app/forecast/**` 對 `app.ops_alert` 套件只可 import `app.ops_alert.model`」，避免被讀成整個套件只能 import 這一個模組。

**M-14｜收尾**
- D-2 規則 4 原句「確認前不得進入實作」，以及「未查證與驗證紀錄」中的〔待 tech-architect 確認〕一點，都改為〔tech-architect 2026-10-18 已確認，修改見修訂紀錄〕。
- D-3 第 7 點的「在該步交易 rollback 之後」改為：
> 在該步結束之後（交易已 rollback；E-2 `audit` 為已 commit）
- Consequences 的「每次執行不超過 7 則」句末接：
> ；E-3b 另計，每個被略過的觸發事件一則
- 設計稿 §2.3、§2.7、§5 照 M-3、M-4、M-11、M-12 同步修改，舊字錄入修訂紀錄。

### C. 給 tech-writer 的配套（ADR-0027 工作樹與 TA 補充項回覆）
1. **ADR-0027 第一批補字**（補定義，風控知悉；兩個 ADR 都還沒 commit，可以併入第一批）
   - 定位字串：`結算評估（D-9.2 ①′）、缺日稽核、晚到掃描（D-3「晚到資料的觸發」第 8 點）都只以這個函式判定。`
   - 在句末接：
   > 回傳的 `MarketRunRegression` 是 frozen 型別，屬性為 `market_run_current`（＝ r_now）、`reference_kind`、`reference_value`、`reference_id`、`reference_started_at`，名稱與 D-9.2「R 倒退」的例外屬性逐字一致；結算評估以它加上 `source = settlement` 建構 `MarketRunRegressedError`。缺日稽核與更正作業不拋例外，以型別化的步驟結果把它交給編排函式（本點 Q8），由編排函式發出 ADR-0029 E-2。
2. **TA 補充項回覆 (1a)～(1g) 的自我修正**：欄名 `market_run_now` 一律改為 `market_run_current`，與 E-2 及上一點同一套名稱。風控知悉即可，其他字面不變。
3. FL-71 (f) 清單標題的「單一來源：清單只在此處維護…」與連接語，我確認可以。錨點 `**推播禁用詞清單**`、`**白名單例外**` 從此是測試依賴的字串，改動時要同批改測試。

### 對實作的約束（qa-reviewer 可逐條檢查）
1. 適用對照表外的組合，建構時拒絕（OA-23）。
2. 識別為 None 的告警不讀、不改鍵集合；鍵集合由 `threading.Lock` 保護（OA-11）。
3. 每一個 `OpsAlert` 建構點都有 `try/except Exception`，建構失敗時後續步驟照常執行（OA-23）。
4. `deliver()` 的呼叫點只在 `sink.py` 與 `selftest.py`（AST）；明示繼承 `OpsAlertSink` 的類別恰好一個（AST）。
5. 通道上限常數只在 `app/push_channels.py`；`OPS_ALERT_PUSH_MAX_CHARS` 只在 `sink.py`；`render` 不 import `app.push_channels`（import graph）。
6. 禁用詞清單只在 ADR-0027 FL-71 (f)；`tests/` 與 `shared/` 沒有手抄的 A、C、D 類清單（grep）。
7. E-2 `correction` 格在 ADR-0027 第二批落檔前不實作。

## 三、驗證
- **讀過的檔案**：
  - ADR-0029 全文；devops-sre 起草回報；我的 N-23 提案；風控審查全文；tech-writer 第一批回報；
  - 我的補充項回覆全文（確認 R-Q7-3 等已回覆）；ADR-0001 狀態規則；ADR-0002 全文；
  - ADR-0026 D-9（L338-351）；`app/alerts/notify.py` 的 import 與環境變數段。
- **ADR-0027 工作樹讀過的段落**：
  - L225-249（D-1）；L352-371（correction_job）；L636-697（gap_audit、plan_coverage_log）；
  - L765-809（D-7 第 1、2 點，含已套用的 N-23）；L1080-1149（D-9.2、B-3）；L1200-1239（D-9 第 5 點）；
  - L1280-1324（D-11 第 2 點）；L2400-2454（FL-71 全條）。
- **grep 結果**：
  - ADR-0027 沒有第二批字面：「守衛成立時本次不啟動」0 筆，L432 仍為「其餘觸發照常」，L4384-4386 標明待 CEO #42。
  - ADR-0027 沒有 `market_run_now`、`ValidationSnapshotPartialSetError`、`checkpoints_due`，補充項尚未套用。
  - 後端測試已有讀取 `FRONTEND_FORBIDDEN_TERMS` 的函式（`tests/test_rules_invalidation_wording.py`）。
- **未查證**：
  - 通道字元上限（維持 D-10 第 3 項）；
  - 從 ADR 文字讀取清單是否可行（交 dev-lead）；
  - `OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS` 的 128 是本 ADR 自訂的設計常數，不是外部事實。
- **沒做的事**：沒有改任何檔案，沒有跑 git 或測試，沒有讀 `.env`，沒有碰 `*.db`，沒有指定套件版本。

## 四、下一步
1. **devops-sre**：照改 M-1～M-14，並同步設計稿，再回送給我確認。
2. **dev-lead**：確認 M-9（以 ADR 區塊為測試來源）是否可行；不可行就退回給我，不得自建清單。
3. **tech-writer**：套用第二節 C 的 1、2 項（風控確認之後）。
4. **風控（知悉級）**：M-11 改名、M-12 擴大 E-3d、`market_run_now` 改名。依失效條件 5，推播的欄位集合與標題有變更。
5. **coordinator**：ADR-0029 不晚於 ADR-0027 第一批落檔。E-2 `correction` 列追蹤 CEO #42，CEO 不同意時回送 TA。
6. **CEO**：上述修改完成後，核可 ADR-0029（#43）。

相關檔案：
- /home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/stock-desk-N23結算例外告警設計-2026-10-18.md
- /home/user/AICompany/work/reviews/2026-10-18-N23風控補充項回覆-tech-architect.md
- /home/user/AICompany/apps/stock-desk/backend/tests/test_rules_invalidation_wording.py

# N-23 維運告警 ADR 事項與 Q1～Q9 裁定提案

- 審查者：tech-architect
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

1. **A 部分另立新 ADR（暫編 ADR-0029「stock-desk 維運告警通道」，編號請 coordinator 分配），不併進 ADR-0027。ADR-0027 只收預測帳自己的部分**：例外型別、編排函式介面、R 倒退的位置、FL-71，以及更正一處指向錯誤。
   - 這處指向錯誤是我查到的：ADR-0027 D-7.1 寫「告警規格依 ADR-0026」，但 ADR-0026 全檔沒有任何告警條文（grep「告警」「N-23」都是 0 筆）。
2. **A1～A5 的裁定**：
   - (1) 採用中性套件 `app/ops_alert/`；
   - (2) 採用注入，但送出器參數必填、沒有預設值；
   - (3) R 倒退定為**型別化例外**，而且檢查點要提前到 ① 之後、② 之前（記為 ①′）。這是我查到的實質缺口：照現行字面，③ 的查證紀錄與 X2 確認各自獨立 commit，R 倒退又只在 ⑤ 的寫入驗證擋，所以還原狀態下 ③ 的列會先留下來，和「本次不寫入」矛盾；
   - (4) 推播截斷與 ADR 字面不衝突：推播不是「例外訊息與 WARNING」。我補一句釐清；
   - (5) E-3b 屬 N-23 (1)，必做；E-3a 依 Q7 併入 E-2；E-3c、E-3d 建議納入，E-3d 擴大為「任一步失敗」。
3. **B 部分 Q1～Q9 全部有裁定**：
   - 會改變行為、要送風控的：Q2、Q3、Q4、Q5、Q7；
   - Q7 有兩面（加強登記安全，但更正作業會延後），由風控判方向。風控若判為放寬，就要 CEO 明示同意；
   - Q1、Q6、Q8、Q9 不改變使用者面的行為。
4. **哪些擋住什麼**：
   - **擋 D-9 實作**（dev-lead 動手寫 settlement、recorder 之前就要定案）：A1、A2、A3、Q1、Q3、Q4、Q5、Q7、Q8；
   - **只擋 D_v**：A4、A5、ADR-0029 核可、Q2、Q6；
   - R-1 修補（security-engineer 判 BLOCKING）擋維運告警上線，因此也擋 D_v。

## 二、各部門回報（tech-architect）

### 評估摘要

- **採用**：
  - 新增中性套件 `app/ops_alert/`，推播的底層傳輸抽成 `app/push_channels.py`，與使用者警示共用；
  - 編排函式以必填參數注入送出器；
  - 例外型別與基底類別放在 `app/forecast/errors.py`；
  - 還原守衛統一成單一函式；
  - C11～C33 以新條目 FL-71 收進 ADR。
- **否決**：
  - 用 `AlertEvent`／`app.alerts.notify` 送維運告警；
  - 以 APScheduler 的 `EVENT_JOB_ERROR` 當告警來源（`_guarded` 已經把例外吞掉）；
  - 跨執行的狀態與冷卻；
  - 任何關閉開關，包括 production code 裡的 NullSink；
  - devops-sre 的 `execution=…/cron_2210|retry_2310|startup`。D-7.1 規定是單一 job，job 函式拿不到是哪個觸發點，硬要推算就得從時鐘猜。改用編排函式開始時讀一次的 store 時鐘當執行識別。

### 方案比較

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A. 新 ADR-0029 加 ADR-0027 小修（**採用**） | 告警是跨模組的基礎能力（以後其他 job 也會用），和預測帳的決策分開；改掉指向 ADR-0026 的錯誤；ADR-0029 本身沒有建議類文案，不必走風控長鏈 | 多一份 ADR 要 CEO 核可 | 兩份要同批落檔，否則 D-7.1 的指向會懸空 |
| B. 全部併進 ADR-0027 | 少一份文件 | ADR-0027 已近 4000 行，風控修訂鏈很長；把維運基礎設施綁進預測帳的 G-1（accepted）面 | 之後其他 job 要接告警時，得去引用預測帳的 ADR |
| C. recorder 直接 import `app.alerts.notify` | 改動最少 | `AlertEvent` 必填代號，訊息帶免責句；會吃到使用者的開關與冷卻；`app.forecast` 和 `app.alerts` 在套件層成環（FL-42 允許 alerts→forecast.views） | 違反「不得共用開關」與 D-1 的依賴方向 |
| D. 掛 job 層 `EVENT_JOB_ERROR` listener | 不動編排函式 | `_guarded`（scheduler.py:604-613）吞掉例外，事件不會送出；就算送出也拿不到 B-3 欄位 | 會漏報 |
| R 倒退：型別化例外（**採用**） | 經過交易 context 一定 rollback（C13）；編排層忘了檢查也是 fail-closed；和 `span_sessions` 同一種形態 | 一般 `except Exception` 也會接到程式錯誤，所以要先接特定型別 | 低 |
| R 倒退：型別化回傳結果 | 不必例外流程 | 編排層一漏檢查就變成「成功」；和 D-9.2 ⑦「任一步失敗整個交易不寫入」的寫法不一致 | 會靜默放行 |

### 決策（ADR 草案）

#### A-1、A-2：中性模組與注入（ADR-0029 D-1／D-3；ADR-0027 D-1、D-7.2）

- **方向**：補定義。**送風控**：否（知悉）。**CEO**：要核可 ADR-0029（ADR 慣例）。**擋 D-9**（recorder.py）。

**ADR-0027 字面一：D-1 表**。定位字串 `` | `app/forecast/recorder.py` | 執行編排：範圍快照、run 與 run_end、協作式期限、逾時判定 | ``。這一列整列換成以下第一列，再插入其後兩列：
> | `app/forecast/recorder.py` | `forecast_record` 的單一編排函式（D-7 第 2 點「步驟隔離」）：依序呼叫記錄、結算、缺日稽核、晚到掃描與更正作業、驗證快照、plan；記錄一步的範圍快照、run 與 run_end、協作式期限、逾時判定；以注入的維運告警送出器發出告警（ADR-0029），本身不 import 推播實作 |
> | `app/forecast/errors.py`（N-23） | 預測帳的 fail-closed 例外型別：基底 `ForecastFailClosedError`，子類 `UnregisteredUnobservedWeekdayError`、`MarketRunRegressedError`；另有 `span_sessions` 內部用的 `SpanRegistrationGap`（不是基底的子類）。只 import 標準庫 |
> | `app/ops_alert/`（ADR-0029；不在 `app/forecast/` 底下） | 維運告警通道。`app.forecast.*` 只可以 import `app.ops_alert.model`；送出器實作由 `scheduler.py` 組裝時注入 |

這三列也同時處理 Q9 (a)。

**ADR-0027 字面二：D-7.2**。定位字串 `` 結算失敗的例外只在編排函式中 ``（唯一）。在該子點之後、同一層插入：
> - （N-23；ADR-0029）編排函式以關鍵字參數 `ops_alert_sink` 接收維運告警送出器，型別為 `app.ops_alert.model.OpsAlertSink`，沒有預設值，由 `scheduler.py` 組裝時注入。`app/forecast/**` 只可以 import `app.ops_alert.model`，不得 import `app.ops_alert` 的其他模組、`app.push_channels`、`httpx` 或 `app.alerts.*`；`settlement.py`、`scoring.py`、`correction.py`、`audit.py`、`validation.py`、`store.py` 完全不 import `app.ops_alert.*`（AST）。告警在該步的交易 rollback 之後、下一步開始之前發出。送出器不拋例外，送出失敗不影響後續步驟。前置條件不成立而略過的步驟（例如結算失敗之後的驗證快照）不另發告警。

**ADR-0029 D-1：模組布局與 import 規則**（大綱見本段最後）

- `app.ops_alert.model`：
  - 只 import 標準庫；
  - 內容：`OpsAlert`（frozen）、`OpsAlertSink` Protocol（`emit(alert) -> None`，保證不拋例外）、事件名稱的封閉列舉、每種事件的欄位定義。
- `app.ops_alert.render`：純函式，產生 log 行與推播文字。
- `app.ops_alert.sink`：唯一的 `OpsAlertSink` 實作。
- `app.push_channels`：
  - 由 `app/alerts/notify.py` 抽出的共用傳輸：環境變數名稱、Telegram URL 樣板、POST、R-1 的安全失敗格式；
  - `app.alerts.notify` 和 `app.ops_alert.sink` 都經過它。
- 方向限制：
  - `app.ops_alert.*` 不得 import `app.forecast.*`、`app.alerts.*`、`app.settings.*`、`app.api.*`；
  - `app.alerts.*` 不得 import `app.ops_alert.*`；
  - `app.push_channels` 只 import 標準庫、`httpx`，以及 R-1 修補放的共用遮罩模組。
- 抽 `push_channels` 的時機：在 R-1 合併之後、隨 N-23 實作一起做。不要擾動 `fix/stock-desk-r1-secret-redaction`。

#### A-3：例外型別與欄位；R 倒退定為例外

- **方向**：補定義（收緊）。①′ 讓「本次不寫入」連 ③ 也涵蓋到。
- **送風控**：要（D-9.2、D-9.3 是風控核可過的條文）。**CEO**：否。**擋 D-9**。

**字面三：D-9.2 R 倒退**。定位字串 `**R 倒退**：R 小於前一筆`（唯一）。整個子點換成：
> - **R 倒退**（N-23；ADR-0029 E-2）：① 讀 R 之後、② 之前（記為 ①′），以 D-7 第 2 點「還原疑似時的共同守衛」判定。R 小於參考值時，視為市場 DB 被還原：拋 `MarketRunRegressedError`（`app/forecast/errors.py`），本次不寫入任何列（fail-closed）。
>   - 參考值 ＝ 最後一列 `forecast_settle_eval.market_run_max`，與最近一個已有 `forecast_correction_job_end` 的作業的 `market_scan_to`，兩者取大；沒有列的一方不計，兩方都沒有時不檢查。
>   - ①′ 在 ② 的大盤讀取與強制重抓、③ 的查證紀錄與 X2 確認寫入、④ 的寫入交易之前，所以本次評估不留下任何列，也不觸發強制重抓。
>   - 參考值以一次主 DB 唯讀查詢取得，不讀市場 DB，所以不違反 ①「之後不再讀市場 DB 的 `MAX(run_id)`」。
>   - D-3 `forecast_settle_eval` 的寫入驗證「`market_run_max` ≥ 前一列的值」保留為縱深防禦；不成立時拋同一型別，整個交易 rollback。
>   - 例外屬性（關鍵字必填）：`source`（恆為 `settlement`）、`market_run_current`（R）、`reference_kind ∈ {settle_eval, correction_job}`、`reference_value`、`reference_id`（`settle_eval_id` 或 `correction_job_id`）、`reference_started_at`（UTC ISO8601）。
>   - 處理終點不變：直到 devops-sre 依 ADR-0026 D-9.4 處理並修訂本點（比照 D-3「晚到資料的觸發」第 8 點）。
>
> 〔N-23 取代：原寫「- **R 倒退**：R 小於前一筆 `forecast_settle_eval.market_run_max` 時，視為市場 DB 被還原：記 WARNING，本次不寫入（fail-closed），直到 devops-sre 依 ADR-0026 D-9.4 處理並修訂本點（比照 D-3「晚到資料的觸發」第 8 點）。」〕

**字面四：D-9.3 B-3**。定位字串 `例外訊息與 WARNING 至少帶`（唯一）。在該子點之後、同一層插入：
> - （N-23；ADR-0029）**型別與欄位**：
>   - 結算評估與更正作業以同一型別拋出 `UnregisteredUnobservedWeekdayError`（`app/forecast/errors.py`，`ForecastFailClosedError` 的子類）。
>   - 上句的欄位是關鍵字必填的結構化屬性：
>     - `source ∈ {settlement, correction}`；
>     - `unregistered_session_dates`：升冪、不重複、非空的 tuple；
>     - `affected_forecast_count`：≥ 1；
>     - `d_reg`：可為 None；
>     - `source = settlement` 時填 `snapshot_from`、`snapshot_to`（等於 `view_range_json`）；`source = correction` 時填 `recheck_from`、`recheck_to`、`market_scan_to`；不適用的欄位為 None。
>   - 例外訊息由這些屬性以固定格式產生，不含其他文字。
>   - `span_sessions` 本身拋的是 `SpanRegistrationGap`（只帶它所見的日期）。`run_settlement_evaluation()`、`run_correction_job()` 各自在最外層、交易已 rollback 之後，以唯一一個 `except SpanRegistrationGap` 把它轉成上述型別再拋出：
>     - 完整清單：以同一份判定視圖，經 `scoring.py` 的單一純函式重算判定視圖範圍內「符合 A-77 第 10 項判準、卻沒有 `event_id ≤ ledger_event_max` 登記」的日期。`span_sessions` 的判準檢查也呼叫同一個函式；
>     - 受影響筆數：評估集合 U（更正作業為被重查的列）中，結算窗（T 之後到 T+h，或到判定視圖中最新的觀察日）含清單中任一日的筆數。
>   - 轉換時不讀市場 DB、不寫入，也不繼續判定；本點「不得捕捉本例外後繼續寫入」不變。
>   - 上句所說的 WARNING，指 ADR-0029 的 `ops alert:` log 行，它永遠帶完整清單。推播是另一個通道，清單長度依 ADR-0029 截斷，不屬於本點的「例外訊息與 WARNING」。

最後一段同時處理 A-4。

**字面五：D-7.1**。定位字串 `告警規格依 ADR-0026`（唯一）。改成 `告警規格依 ADR-0029（維運告警通道）`，括號後原文照舊。
- 方向：不變（更正指向）。

#### A-4：推播截斷（ADR-0029 D-4）

- **方向**：不變（釐清）。**送風控**：知悉（字面四的最後一句涉及風控核可的 B-3 句）。**CEO**：否。**只擋 D_v**。
- ADR-0029 D-4 的規格：
  - 推播文字長度 ≤ 常數 `OPS_ALERT_PUSH_MAX_CHARS`，取各通道上限的較小值減去安全餘量；
  - 上限數值由 devops-sre 查官方文件後定；2000 字元是記憶值，devops-sre §7 已標未查證；
  - 清單最多列 20 筆，升冪；
  - 永遠帶 `unregistered_count`、最早一日與最晚一日；
  - 超過時加「另有 N 筆，完整清單見 scheduler log」；
  - 不採分則送出。

#### A-5：附帶事件的歸屬（ADR-0029 D-7 事件目錄）

- **方向**：收緊（揭露）。**送風控**：知悉。**CEO**：知悉即可，沒有新的成本或外部服務。
- 推播量的調整只能是「同一執行內的去重」（同 devops-sre §2.5）。

| 事件 | 歸屬 | 欄位重點 |
|---|---|---|
| E-1 `forecast.settle.unregistered_unobserved_weekday` | 必做 | 照字面四 |
| E-2 `forecast.market_run_regressed` | 必做；source 擴為 {settlement, audit, correction}，吸收 E-3a（見 Q7） | 照字面三，加上 `write_outcome` |
| E-3b `forecast.job.skipped` | **屬 N-23 (1)，必做**（ADR-0027 D-7.1 已要求 listener） | `job_id`、`reason ∈ {max_instances, missed}`、被略過的觸發時刻；只對 `forecast_record` 推播 |
| E-3c `forecast.settle.deadline_not_started` | 建議納入（D-7.2 視同結算失敗） | `deadline_at` |
| E-3d `forecast.step.failed` | 建議納入，擴為任一步失敗，含 `step = orchestrator`（見 Q8） | `step`、`exception_class`，不帶例外字串 |

- 共同欄位：`event`、`severity=WARNING`、`occurred_at`、`execution_started_at`（取代 devops-sre 的 `execution`）、`source`、`write_outcome`。
- 每一步失敗只發一則，取最具體的事件（E-1／E-2 優先於 E-3d）。

#### ADR-0029 草稿大綱

1. **狀態區塊**：
   - proposed；只適用 product/stock-desk；
   - 與 ADR-0027（N-23 消費端）、ADR-0026 D-9.4 的關係；
   - 依賴：R-1 修補先合併（阻擋），O-1 的 `configure_logging()` 擴及 scheduler。
2. **Context**：devops-sre 設計 §1 的事實；security-engineer F-1、F-2。
3. **Options**：上面方案比較表的 A、C、D，再加「只寫 log、靠人工掃描」。
4. **Decision**：
   - D-1：模組與 import 規則；
   - D-2：`OpsAlert` 模型與封閉事件列舉；
   - D-3：送出器行為。log 先寫而且每次都寫；推播以 (event, source, step, `execution_started_at`) 去重，只在同一次執行內去重；不跨執行；沒有冷卻、門檻或開關；不讀 `settings.alerts.*`；送出失敗只記 `channel`、`error_class`、`status`；scheduler 啟動時，若沒有任何通道設定完整，記 ERROR；
   - D-4：推播格式與截斷。標題 `[stock-desk 維運告警] <event>`；不帶免責句或任何建議用字；
   - D-5：安全。沿用 R-1 的固定格式輔助函式與 `redact_url()`；禁止 `str(exc)`、`repr(exc)`、`exc_info`、`logger.exception`；logger 名稱 `app.ops_alert`（O-1 的 `configure_logging()` 下，`app` 是 INFO、root 是 WARNING，所以 WARNING 一定會輸出）；
   - D-6：`forecast_record` 的 skipped listener；
   - D-7：事件目錄（上表）；
   - D-8：不做「已恢復」通知，不存跨執行狀態（要做就另立 ADR）；
   - D-9：自測 `ops_alert.selftest` 只在手動執行時送出。
5. **Consequences**：
   - 好處：第一次發生就推播；與使用者警示完全分離；
   - 壞處：持續失敗時每天最多 3×(事件、source 數) 則；不帶「首次發生時間」；沒有 dead-man's switch（devops-sre R-4，另案，要 CEO 決定外部監控）；R-1 沒修之前不得上線。
6. **對實作的約束** OA-1～OA-n：對應 devops-sre §5 的 1～17 格，加上本段 D-1 的 import graph。
7. **失效條件**：新增跨執行狀態、開關、使用者面內容，或新通道時，重審本 ADR。

### B. Q1～Q9 的裁定

**Q1（G1）C11～C33 進 ADR**
- 方向：收緊（測試）。送風控：否（落實風控已核可的約束）。CEO：否。**擋 D-9**（審查依據）。
- 新增 **FL-71**。定位：插在 `- **FL-24**：預測端計分永遠使用原始列。` 之前（FL-70 之後）。字面：
> - **FL-71**（N-23；D-7 第 1、2 點；D-9.2「R 倒退」；D-9.3 B-3；ADR-0029）：
>   - (a) job 註冊與順序：id 為 `forecast_record`；`CronTrigger` 帶 `timezone="Asia/Taipei"`；`max_instances=1`、`coalesce=True`、`misfire_grace_time=1800`；啟動補跑在啟動後 3 分鐘；六步的呼叫順序以 spy 斷言為記錄 → 結算 → 缺日稽核 → 晚到掃描與更正作業 → 驗證快照 → plan。
>   - (b) 步驟隔離：結算的四種失敗各一格：拋 `UnregisteredUnobservedWeekdayError`、拋 `MarketRunRegressedError`、拋其他 `Exception`、期限已到沒有啟動。每格都斷言：缺日稽核被呼叫，而且寫入一列 `forecast_gap_audit`；`last_gap_audit_at` 前進；`last_settle_eval_at` 不前進，而且等於最後一列 `forecast_settle_eval.started_at`。缺日稽核的簽章不含 R、判定視圖、休市日表物件、`waiting_json`（AST）。step runner 只接 `Exception`，沒有 `except BaseException` 或裸 `except:`（AST）；注入 `KeyboardInterrupt`、`SystemExit` 時會逃出編排函式。
>   - (c) 例外接在哪裡：接住結算失敗的 `try/except` 只出現在 `recorder.py` 的編排函式，而且包住整個 `run_settlement_evaluation()` 呼叫（AST）。`settlement.py`、`scoring.py`、`correction.py` 內，凡是能接到 `SpanRegistrationGap` 或 `ForecastFailClosedError` 的 `except` 都會再拋出；轉換只在 D-9.3 B-3「型別與欄位」所列的唯一位置（AST）。例外逃出 `run_settlement_evaluation()`／`run_correction_job()` 時，連線的 `in_transaction` 為 False；`forecast_outcome`、`forecast_settle_eval`、`forecast_correction_job_end`、`forecast_void_late_diag` 的列數不變。編排層的 except 區塊與它之後的程式不呼叫這些表的寫入函式（AST）。
>   - (d) B-3 欄位：兩種 source 各一格，逐欄斷言 D-9.3「型別與欄位」；清單升冪、不重複；fixture 有兩個未登記日、只有一個落在 `span_sessions` 的相鄰對內 → 清單兩筆；`str(exc)` 等於由屬性以固定格式產生的字串；缺任一個必填屬性 → 建構失敗。
>   - (e) R 倒退：fixture 的參考值大於 R → 在 ② 之前拋 `MarketRunRegressedError`；`app.services.index` 的讀取與強制重抓呼叫 0 次；`forecast_index_check`、`forecast_ledger_events` 沒有新列（spy）；屬性等於 fixture 值；參考值取自更正作業的一格；繞過 ①′、只靠 ⑤ 寫入驗證的一格 → 同型例外，整個交易 rollback；沒有參考值 → 不檢查。
>   - (f) 告警與 import graph（ADR-0029）：E-1、E-2、E-3b～E-3d 各一格，第一次發生就恰好一則推播加一行 `ops alert:` WARNING；同一次執行內重複接住 → 推播 1 則、log 2 行；22:10、23:10、隔日各推 1 則；`settings.alerts.*` 任何值都不改變推播數；送出器拋例外或通道 4xx／5xx／逾時 → 缺日稽核照常寫入；推播在 rollback 之後才送出（spy：送出時沒有開啟中的寫入交易）；`app/` 內 `OpsAlertSink` 的實作恰好一個；D-7 第 2 點「步驟隔離」所列的 import 限制成立（import graph）。
>   - (g) listener：以 APScheduler 的事件物件直接呼叫 listener。`EVENT_JOB_MAX_INSTANCES`、`EVENT_JOB_MISSED` 各一格 → WARNING 帶被略過的觸發時刻，推播一則；其他 job id → 不推播。
>   - (h) 結束方式：任一步失敗時，編排函式正常返回，`_guarded` 不記 ERROR；例外逃出編排函式本身 → `forecast.step.failed`（`step = orchestrator`）一則，`_guarded` 照舊記 ERROR。
>   - (i) 前置條件：驗證快照的三項前置條件各一格（spy）；驗證快照全有或全無，以及 plan 依全部 claim 判定（D-7 第 2 點 Q3）各一格；沒有 T（D-7 第 2 點 Q4）→ 驗證快照與 plan 都不呼叫，`plan_coverage_log` 沒有新列。
>   - (j) 雜項：`app/forecast/**` 沒有存放登記終點的欄位或檔案（grep／AST）；沒有任何以呼叫端指定日期或 payload 寫入 `unobserved_weekday` 的 CLI 或 API；recorder 與 X2 確認寫入函式不呼叫 `unobserved_weekdays`、`ledger_registration_start()`（AST）。
>   - (k) 驗收依據：本條加上 FL-65 (n)、FL-66 (h)(j)、FL-67 (e)～(n)、FL-68、FL-70，涵蓋 review 檔中的 C1～C33（對照表見修訂紀錄本批段）。qa-reviewer 以 FL 為驗收依據，C 號不另外構成驗收依據。
- 對照表（交 tech-writer 放進修訂紀錄）：
  - C1、C3、C4、C5、C8、C9 → FL-66 (j)；
  - C6 → FL-66 (j)〔推論，P-4 格未逐一核對〕；
  - C2、C7、C26、C31 → FL-71 (j)；
  - C10、C11、C14、C15 → FL-71 (b)；C11 另見 FL-67 (g)；
  - C12、C13 → FL-71 (c)；
  - C16 → FL-71 (d)；
  - C17、C29 → FL-67 (g)、FL-71 (i)；
  - C18、C19 → FL-71 (a)（FL-14 只管時區）；
  - C20 → FL-71 (b)(g)；
  - C21 → FL-67 (e)(f)；
  - C22 → FL-68 (b)(c)；
  - C23 → FL-68 (d)(e)；
  - C24 → FL-66 (h)；
  - C25 → FL-65 (n)〔推論，`eval_set_sha256` 格未核對〕；
  - C27、C32 → FL-67 (h)(n)；
  - C28 → FL-68 (g)；
  - C30 → FL-67 (k)；
  - C33 → FL-68 (h)。

**Q2（G2）T 的快照缺漏、較早的快照存在**
- 建議採 (b′)，以 `late_cutoff_at` 為寬限，比 dev-lead 的 (b) 精確。
- 理由：
  - 照現行字面，結算或缺日稽核持續失敗時，畫面一直讀較早的快照，落後天數沒有上限；
  - F-3 暫停等 gate 也跟著停在舊值；
  - (b) 若以「快照的 T 早於當下的 T」判定，每晚 22:10 到快照寫入之間都會遮蔽。
- 方向：收緊。送風控：**要**；`mask_reason` 增列等於要重審 LM-153（D-11.4 明文規定）。CEO：否。只擋 D_v（views）。
- 字面 (1)，定位字串 `若且唯若〔沒有 daily snapshot`（唯一）：把「〔沒有 daily snapshot，或 `e_changed_since(snapshot)` 為真〕」改成「〔沒有 daily snapshot，或 `e_changed_since(snapshot)` 為真，或 `snapshot_stale(snapshot)` 為真〕」。在同一子點後插入：
> - （N-23 Q2）**`snapshot_stale(snapshot)`**：放在 `views`，與 `e_changed_since` 同一個模組，不接受呼叫端傳入 bool（比照 S9-2）。為真，若且唯若存在一個觀察日 S（`observed_sessions(as_of=None)`）同時滿足兩項：S 晚於該 snapshot 的 `computed_for_session`；S 的 `late_cutoff_at`（D-7.4 的同一個函式，取 T ＝ S）≤ 當下的 store 時鐘。
>   - 理由：T 的 snapshot 應該在 T+1 開盤前寫入（D-7 第 2 點）。過了這個時點仍沒有，畫面讀的是更早的一筆，n、徽章與 gate 都落後，而且結算或缺日稽核持續失敗時，落後沒有上限。
>   - 只比較 session 日期與 `late_cutoff_at`，不估計時間差。當晚的 snapshot 寫入成功時不成立，所以不會每晚遮蔽。
- 字面 (2)：`mask_reason: Literal["e_changed_since", "no_daily_snapshot"]` 改成加上 `"snapshot_stale"`；多個原因同時成立時，依 `no_daily_snapshot` → `e_changed_since` → `snapshot_stale` 取第一個。`mask_episodes` 是否分列這個原因，交 quant 登記（後續事項，不擋 D_v）。
- 字面 (3)，定位字串 `展望依 D-11.4 既有的「沒有 snapshot」規則處理`（唯一）。整句換成：
> - 沒有 T 的 snapshot 時，展望與徽章依 D-11.4 讀最新一筆 daily snapshot。T 的 `late_cutoff_at` 已過、仍沒有 T 的 snapshot 時，`n_disclosure_masked` 依 D-11.4 `snapshot_stale` 為真，遮蔽到下一筆 snapshot 寫入為止。D-11.4 的「沒有 snapshot」規則只適用於該 claim 完全沒有 daily snapshot 的情形。
- 風控若不接受 (b′)，退回 (a)：只換字面 (3)，把第二句改成「不因 T 的 snapshot 缺漏而遮蔽；落後期間沒有上限，揭露方式由 creative-lead 起草、風控審查」。

**Q3（G3）驗證快照全有或全無，plan 依全部 claim**
- 方向：補定義（收緊）。送風控：要（plan 面向使用者；`plan_coverage_log` 是 V15-04 核可過的條文）。**擋 D-9**。
- 定位字串 `驗證快照：以下三項都成立才寫`。在該子點末尾加：
> （N-23 Q3）本次的 claim 集合 ＝ 驗證快照步驟開始時，以一次唯讀查詢讀得的全部已登記 forward claim（不論 `display_state`）。全部 claim 的 T 快照在同一個主 DB 寫入交易內寫入；任一 claim 計算或寫入失敗，整個交易 rollback，本次不寫任何 T 快照，記 WARNING。集合中部分 claim 已有 T 的快照、部分沒有時（例如兩次執行之間新登記了 claim），本次不寫，也不補寫缺少的部分，記 WARNING。
- 定位字串 `` plan：`computed_for_session = T` 的 daily snapshot 存在時才寫 ``，改成「plan：plan 作業開始時以一次唯讀查詢讀得的全部已登記 forward claim，每一個都有 `computed_for_session = T` 的 daily snapshot 時才寫」。後半句照舊。
- 定位字串 `` `snapshot_id`：`computed_for_session = T` 的 daily snapshot ``，整句換成：
> `snapshot_ids_json`：已存在的 `computed_for_session = T` daily snapshot，格式 `[{claim_id, snapshot_id}]`，依 `claim_id` 排序，可以是空陣列；`start_outcome = no_snapshot`，若且唯若有任一已登記 forward claim 缺少 T 的快照。
- 代價：一個 claim 出錯會連帶擋住全部 claim 的快照與 T 的 plan。

**Q4（G4）沒有 T**
- 方向：補定義（收緊）。送風控：要。**擋 D-9**。
- 在「前置條件」的 plan 子點之後插入：
> - （N-23 Q4）驗證快照與 plan 都需要本次執行的 T。以下兩種情形，本次執行沒有 T：記錄一步在決定候選 T 之前就失敗；候選 T 依 D-7 第 3 點記為 `inputs_not_ready`。這時不呼叫驗證快照與 plan，記 WARNING，也不寫 `plan_coverage_log`；該觀察日之後若一直沒有 step_start，依 D-3 `plan_coverage_log`「衍生計數」以 T 為單位計。結算、缺日稽核、晚到掃描與更正作業不需要 T，照常執行。記錄一步在決定 T 之後才失敗時，T 照樣存在，快照與 plan 只依本點其他前置條件。

**Q5（G5）期限的效力**
- 方向：補定義。送風控：要（知悉級，涉及 V15-04 的列舉）。**擋 D-9**。
- 在「步驟隔離」的期限子點之後插入：
> - （N-23 Q5）**D-7.7 期限對各步的效力**：期限只決定「是否啟動」。已啟動的步驟一律跑完，不在步驟內檢查期限（D-7.7 記錄的範圍之間除外）。
>   - 記錄依 D-7.7；
>   - 結算依 D-9.2「不切分」，期限已到不啟動；
>   - 缺日稽核、晚到掃描與更正作業、驗證快照不看期限；
>   - plan 期限已到時 `start_outcome = deadline`。
>
>   結算在期限前啟動、期限後才 commit 時，後續各步照本點與前置條件執行。plan 的 `deadline` 與 `no_snapshot` 同時成立時，記 `deadline`：期限在讀取任何 snapshot 之前判定，`snapshot_ids_json` 照實填入。
- 代價：快照在期限之後才寫，會拉長整次執行，可能吞掉 23:10 的重試。E-3b 會讓這件事看得見。

**Q6（G6）listener 的測試格**：已併入 FL-71 (g)。方向：收緊（測試）。不送風控。只擋 D_v。

**Q7（G7）還原時的缺日稽核：不對稱只對「寫缺日列」是刻意的**
- 照我讀條文的推論，在被還原的市場 DB 上，觀察日只會變少，所以缺日列只會少寫，不會寫錯。
- 但 **A-77 第 10 項的登記是永久的**：日期一旦登記成未觀察平日，就固定排除；g 變大、門檻變寬，方向對模型有利。更正作業 ③ 的登記同樣有這個問題。這點是推論，要靠測試確認。
- 方向：兩面。登記與結算收緊；更正作業時效延後，屬放寬面。送風控：要，由風控判方向；判為放寬時要 CEO 明示同意。**擋 D-9**（audit.py、correction.py）。
- 在 D-7.2「步驟隔離」群組之後插入：
> - （N-23 Q7）**還原疑似時的共同守衛**：`market_run_regression(r_now, *, store) -> MarketRunRegression | None`，是 `app/forecast/` 內的單一函式，名稱暫定。r_now 由呼叫端傳入它自己那一次讀到的市場 DB `MAX(run_id)`。參考值依 D-9.2「R 倒退」的定義，以一次主 DB 唯讀查詢取得。結算評估（D-9.2 ①′）、缺日稽核、晚到掃描（D-3「晚到資料的觸發」第 8 點）都只以這個函式判定。
>   - 缺日稽核：守衛成立時照常判定，並寫入 `forecast_gaps` 與 `forecast_gap_audit`，但不做 A-77 第 10 項的登記，記 WARNING（ADR-0029 E-2，`source = audit`）。理由：還原後觀察日只會變少，缺日列只會少寫；登記卻是永久的固定排除。登記範圍每次都是完整的 [D_reg, 最新觀察日]（不存水位），所以還原處理完之後的第一次稽核會補上。
>   - 更正作業：守衛成立時本次不啟動，四類觸發都延後；W、W_E、W_V、W_S 都不前進，所以觸發不會遺失。記 WARNING（E-2，`source = correction`）。
- 同時改 D-3「晚到資料的觸發」第 8 點，定位字串 `本次不產生任何 \`source_revision\` 觸發，W 不前進，其餘觸發照常`：把「其餘觸發照常」改成「其餘觸發也延後，本次不啟動更正作業（D-7 第 2 點 Q7）」。
- 代價（請風控權衡）：還原期間，X2 與收盤更正的 supersede 會延後，紀錄清單上已結算、收盤已確認有誤的列，會更久不帶 LM-143。若風控不接受，備案是更正作業照跑、只略過登記，但這時 `span_sessions` 可能拋 E-1，在告警上被誤歸為程式缺陷。

**Q8（G8）job 怎麼結束**
- 方向：補定義。不送風控。**擋 D-9**。
- 在「步驟隔離」群組末尾插入：
> - （N-23 Q8）**整次執行的結束**：編排函式在全部步驟結束後正常返回，不因任何一步失敗而再拋出。再拋出只會讓 `_guarded` 多記一筆 ERROR，APScheduler 也不會送出 `EVENT_JOB_ERROR`。每一步的結果彙總成型別化的步驟結果，結束時記一行 INFO `forecast record run:`（含每一步的 outcome）。告警只由編排函式依步驟結果、經注入的送出器發出（ADR-0029），不以 job 層事件為來源。例外逃出編排函式本身（步驟隔離以外）時，由 `scheduler.py` 的 job 包裝經同一個送出器發出 `forecast.step.failed`（`step = orchestrator`），之後照 `_guarded` 既有行為記 ERROR。

**Q9（G9）文件同步**
- 方向：不變（釐清）。不送風控。不擋任何一項。
- (a) 已含在 D-1 字面一；
- (b) 定位字串 `依 D-7.1 第 2 點的執行順序`，改成 `依 D-7 第 2 點的執行順序`；
- (c) 定位字串 `每日結算排程在結算之後`，改成 `每日結算排程在缺日稽核之後（D-7 第 2 點的執行順序）`。

### 對實作的約束（qa-reviewer 可逐條檢查）

1. `app/forecast/**` 只 import `app.ops_alert.model`；六個寫入／判定模組不 import `app.ops_alert.*`、`httpx`、`app.alerts.*`（import graph／AST）。
2. `app.ops_alert.*` 與 `app.alerts.*` 互不 import；`app.ops_alert.*` 不 import `app.forecast.*`、`app.settings.*`（import graph）。
3. 編排函式的 `ops_alert_sink` 沒有預設值；`app/` 內只有一個 `OpsAlertSink` 實作；沒有任何環境變數、設定或 API 能關掉維運告警（AST／grep）。
4. 環境變數名稱與 Telegram URL 樣板，在 `app/` 內只出現在 `app/push_channels.py`（grep）。
5. 推播與 log 只由例外的結構化屬性組成；`app/ops_alert/**`、`app/push_channels.py` 沒有 `str(exc)`、`repr(exc)`、`exc_info`、`logger.exception`（AST）。
6. R 倒退在 ② 之前拋出（FL-71 (e)）；E-1 的兩層型別與轉換位置（FL-71 (c)(d)）。
7. 禁止：
   - 跨執行的去重或冷卻；
   - 「已恢復」通知；
   - 新增狀態表或狀態檔；
   - 以時鐘推算觸發點類別；
   - 告警送出失敗時中止後續步驟。
8. FL-71 全部格通過；ADR-0029 的 OA 條款通過。

## 三、驗證

- **讀過的檔案**：
  - devops-sre 告警設計全文；dev-lead 盤點全文；
  - security-engineer R-1 評估全文；O-1 任務單（Grep）；
  - dev-lead 前次查證 §2～§5；
  - TA 提案 L440～L579（含 C21～C27）；
  - 風控單項確認 A、F、G、I 段（C28～C33）；
  - 風控 B-3 回送 G 段（C3 改寫、C9、C10）；
  - TA B-3 回送 C1～C8；
  - `app/alerts/notify.py`、`app/alerts/__init__.py`。
- **ADR-0027 讀過的段落**：
  - 檔頭 L1～L60；D-1 L227～L257；
  - D-3 晚到觸發與 `forecast_settle_eval` L405～L464；`forecast_gap_audit`／`plan_record`／`plan_coverage_log` L640～L711；
  - D-7 L768～L907；D-8 L1020～L1047；D-9 L1048～L1213；
  - D-11.4 L1400～L1479；D-14 L1959～L2007；
  - 對實作的約束 L2093～L2104；FL-66～FL-70 L2288～L2367；FL-42 L2440～L2459。
- **定位字串**：本報告用到的字串都以 Grep `-o` 驗過，在 ADR-0027 各只命中一處。D-3 第 8 點與 FL-24 兩處，我只目視確認，沒有跑 `-o`，落檔前請 tech-writer 再 grep 一次。
- **查證結果**：
  - ADR-0026 全檔 grep「告警」「N-23」是 0 筆，所以 D-7.1 的指向確實懸空；
  - ADR 中 FL-71 以後的號碼都沒有人用；
  - `docs/adr/` 最後一份是 0028，repo 內沒有 ADR-0029 的引用。
- **未查證**：
  - Discord、Telegram 的單則字元上限；
  - LM-153 的字面能否涵蓋 `snapshot_stale`（交風控）；
  - APScheduler 3.11.3 事件物件的屬性名稱（`scheduled_run_time(s)`）；
  - 對照表中 C6、C25 的對應格；
  - Q7「還原後缺日列只會少寫」只是依條文推論，沒有實測；
  - R-1 修補分支的實際內容（我只讀了工作樹）。
- **沒做的事**：沒有改任何檔案、沒有 commit；沒有讀 `.env`；沒有碰 `*.db`；沒有指定任何套件版本。

## 四、下一步

1. **coordinator**：分配 ADR-0029 編號；ADR-0029 與 ADR-0027 本批修訂（字面一～五、Q1～Q9）要同批落檔，避免 D-7.1 的指向懸空。
2. **風控**：
   - 必審：A-3（字面三、四）、Q2（含 LM-153 增列）、Q3、Q4、Q5、Q7（判方向）；
   - 知悉：A-4、A-5、ADR-0029；
   - 另請提供 FL-71 (f) 要用的推播禁用詞清單。
3. **CEO**：
   - 核可 ADR-0029；
   - 風控若判 Q7 為放寬，要明示同意；
   - 知悉 E-3 的範圍；
   - 外部 dead-man's switch（R-4）另案，選項列出後再決定。
4. **devops-sre**：照本裁定改設計稿：
   - `execution` 改成 `execution_started_at`；
   - E-2 欄位改成 `reference_*`，source 擴成三種；
   - E-3a 併入 E-2；
   - 查證通道字元上限；
   - 起草 ADR-0029 的 OA 條款與部署手冊 §5 小節。
5. **tech-writer**：風控核可之後，照字面一～五、FL-71、Q2～Q9 套用，並把 C 號對照表寫進修訂紀錄。
6. **dev-lead**：
   - R-1 照原計畫先合併；
   - 擋 D-9 的各項定案、N-4 與 N-17 解除之後，才實作 `forecast_record`，連同 `push_channels` 一起抽出；
   - 實作期間遵守 FL-71。

相關檔案：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md
- /home/user/AICompany/work/stock-desk-N23結算例外告警設計-2026-10-18.md
- /home/user/AICompany/work/stock-desk-N23排程器結算失敗行為盤點-2026-10-18.md
- /home/user/AICompany/work/reviews/2026-10-18-R1推播token外洩評估-security-engineer.md
- /home/user/AICompany/work/reviews/2026-10-18-C22與N21至N24單項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-C22存放表與N21更正作業視圖及N22至N24提案-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-18-N23排程器失敗行為查證-dev-lead.md
- /home/user/AICompany/apps/stock-desk/backend/app/alerts/notify.py

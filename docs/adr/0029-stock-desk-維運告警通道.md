# ADR-0029：stock-desk 維運告警通道

- 狀態：proposed
- 日期：2026-10-18
- 決策者：devops-sre（草案）；tech-architect 2026-10-18 裁定 A-1～A-5 與 ADR-0029 大綱；待 CEO 核可（CEO 事項 #43）。立案依據：後續追蹤清單 N-23 第 (1) 項；coordinator 分配編號〔事實：`work/reviews/2026-10-18-N23維運告警與Q1至Q9審查-風控.md:14`〕。
- 適用範圍：僅 product/stock-desk。
- 風控審查：2026-10-18 風控對 ADR-0029 大綱的結論為「修改後核可」（5 項 required，知悉級，無否決）。5 項已全部納入，落點對照見本檔「風控 required 落點」。本 ADR 的推播文字屬維運資訊，沒有任何面向使用者的建議類文案；但推播的欄位集合、標籤或模板變更要送風控知悉（見「失效條件」）。
- 與既有 ADR 的關係：
  - **ADR-0027（同批落檔）**：本 ADR 是 ADR-0027 N-23 的消費端規格。ADR-0027 只收預測帳自己的部分（例外型別、編排函式介面、R 倒退的位置、FL-71）。
    - ADR-0027 D-7.1 原文「告警規格依 ADR-0026」是指向錯誤：ADR-0026 全檔沒有告警條文〔事實：tech-architect 2026-10-18 對 ADR-0026 grep「告警」「N-23」各 0 筆；風控同日複查相符〕。ADR-0027 字面五把它改為指向本 ADR。**本 ADR 檔案必須與 ADR-0027 第一批在同一個 commit 落檔，否則該指向懸空。**
    - 本 ADR 的 E-1、E-2 欄位對應 ADR-0027 D-9.3 B-3「型別與欄位」與 D-9.2「R 倒退」的例外屬性；兩邊的屬性名稱必須逐字一致；E-2 的 `audit`／`correction` 另對應 D-7 第 2 點 Q7 守衛的回傳值 `MarketRunRegression`。
  - **ADR-0026 D-9.4**（整檔還原只限操作者手動）：E-2 的處理終點。本 ADR 不放寬 fail-closed，也不決定處理程序。
  - **ADR-0001**：本檔依其模板與狀態規則。
  - 不修訂任何 accepted ADR。
- 依賴：
  - **R-1 修補先合併（阻擋）**：分支 `fix/stock-desk-r1-secret-redaction`（commit `cb4e51a`、`ce56f43`、`91b5429`），提供 `app/logging_setup.py` 的 `configure_logging()`、`redact_url()`、`SecretRedactionFilter`、`describe_failure()`，並讓 `app/alerts/notify.py` 的失敗訊息不再帶例外原文〔事實：本檔起草時讀該分支工作樹；2026-10-18 `git merge-base --is-ancestor` 驗證該分支尚未在 `product/stock-desk` 之中〕。security-engineer 判 R-1 為 BLOCKING，擋維運告警上線。
  - **O-1 的 `configure_logging()` 擴及 scheduler**：R-1 分支已在 `scheduler.py` 的 `main()` 呼叫它〔事實：同上，`app/scheduler.py:785`〕。
  - `app/push_channels.py` 的抽出時機：R-1 合併之後、隨 N-23 實作一起做，不擾動 R-1 分支。
  - CEO 在主機上清查既有 log 是否已含真實祕密並輪換，仍是上線前提（security-engineer R-1 評估第四節）；不屬於本 ADR 的決策。
- 標註約定：〔事實：檔案:行號〕為起草者 2026-10-18 讀到的狀態，行號會漂移；〔推論〕為起草者判斷；【未查證】為尚未以一手來源確認，**不得當作事實或寫死成數值**。路徑相對於 `apps/stock-desk/backend/`，另有標示者除外。

---

## Context（背景）

- **結算程式尚不存在**：`app/` 底下沒有 `forecast/`，`app/scheduler.py` 沒有 `forecast` 字樣〔事實：2026-10-18 `ls app`，`app/forecast`、`app/ops_alert`、`app/push_channels.py` 都不存在〕。所以本 ADR 全部是對規劃中的 `recorder.py` 等模組與 `scheduler.py` 組裝的要求，不是改現有程式。
- **ADR-0027 要求「第一次就告警」**：清單 N-23 (1) 要求第一次觸發就告警、不設連續次數門檻，內容同 D-9.3 B-3 的 WARNING 欄位；涵蓋 `span_sessions` 例外（E-1）與 D-9.2「R 倒退」（E-2）。
- **現有通道只有 log**：只有 Python `logging` 寫 stdout／stderr；排程器的 `_guarded` 包住每個 job，只記 ERROR 與 traceback，不推播，而且把例外吞掉，所以 APScheduler 的 `EVENT_JOB_ERROR` 不會送出〔事實：`app/scheduler.py:604-613`〕。營運現行的「告警」是人工掃 log，而且多數規則是「連續出現超過一次排程週期才算持續」；部署手冊 §5 明說沒有自動告警機制〔事實：`docs/族群動能-主機部署手冊.md:310-357`〕。
- **現有推播通道不能直接用**：`app/alerts/notify.py` 只收 `AlertEvent`（必填 `rule_id`、`symbol`、`market`），格式化會帶「本工具為研究與教育用途，非投資建議。」；使用者告警受 `settings.alerts.enabled`、`notify_webhooks` 控制，並有冷卻〔事實：`notify.py:53-`；`app/scheduler.py:380,420`；`app/alerts/engine.py:375-383`〕。維運告警不可共用開關與冷卻。
- **祕密外洩的既有缺陷（security-engineer F-1、F-2）**：
  - F-1：scheduler 的 `basicConfig(level=INFO)` 讓 httpx 在 INFO 寫出完整請求 URL；Telegram 的 URL 含 bot token，Discord webhook URL 本身就是祕密。
  - F-2：`notify.py` 把 `str(exc)` 寫進 log 與 `DeliveryResult.detail`；`HTTPStatusError` 的字串含完整 URL。devops-sre 以假 token 在 httpx 0.28.1 驗證過〔事實：`Client error '404 Not Found' for url 'https://api.telegram.org/botFAKETOKEN123/sendMessage'`〕。
  - 維運告警一旦走同一條路徑，會把風險放大。R-1 修補即為此而設。
- **APScheduler 版本與事件物件**：3.11.3〔事實：`uv.lock:48-56`；`.venv` 的 `apscheduler-3.11.3.dist-info`〕。已在 `.venv` 原始碼確認：
  - `EVENT_JOB_MAX_INSTANCES` 送出 `JobSubmissionEvent`，屬性是 `scheduled_run_times`（datetime 的 list）。
  - `EVENT_JOB_MISSED` 送出 `JobExecutionEvent`，屬性是 `scheduled_run_time`（單一 datetime）。
  - 兩種事件都在 `_process_jobs` 內收集，於迴圈之後由 `_dispatch_event` 同步呼叫 listener；listener 拋出的任何 `BaseException` 會被 scheduler 以 `logger.exception("Error notifying listener")` 吞掉。
  - 因此 listener 與 scheduler 的派送在同一個執行緒上（見 D-6 的阻塞上限）。tech-architect 提案原把這點列為未查證，此處已補。
- **D-7.2 是單一 job**：`forecast_record` 是一個 cron job（22:10、23:10 重試）加啟動 3 分鐘補跑；job 函式拿不到「這次是哪個觸發點」，硬推要從時鐘猜。所以設計稿原有的 `execution=…/cron_2210|retry_2310|startup` 被否決，改用編排函式開始時讀一次的 store 時鐘（`execution_started_at`）當執行識別。

## Options（選項比較）

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A. 中性套件 `app/ops_alert/` ＋ 注入送出器 ＋ 共用傳輸 `app/push_channels.py`（**採用**） | `app.forecast.*` 只依賴一個型別模組；維運告警與使用者警示共用傳輸、不共用開關；送出器必填，沒有「忘了接線就靜默」的預設；其他 job 日後可重用 | 多一個套件與一次 `notify.py` 重構；要 CEO 核可一份 ADR | 重構 `notify.py` 要等 R-1 合併，否則衝突 |
| C. `recorder.py` 直接 import `app.alerts.notify` | 改動最少 | `AlertEvent` 必填代號且訊息帶免責句；會吃到使用者的開關與冷卻；`app.forecast` 與 `app.alerts` 在套件層成環（FL-42 只允許 alerts→forecast.views） | 違反「不得共用開關」與 ADR-0027 D-1 的依賴方向 |
| D. 掛 job 層 `EVENT_JOB_ERROR` listener | 不動編排函式 | `_guarded` 吞掉例外，事件不會送出；就算送出也拿不到 B-3 欄位 | 會漏報 |
| E. 只寫 log、靠人工掃描 | 零新增程式 | 與 N-23 (1)「第一次就告警」字面不符；人工掃描的口徑在 §5 是「持續出現才算」 | 事件發生後無人察覺，fail-closed 停擺多日 |
| F. 跨執行狀態（冷卻、門檻、已恢復通知） | 推播量較少；可通知恢復 | 要新增狀態表或檔；冷卻與門檻直接違反「第一次就告警」 | 狀態壞了就靜默 |

否決的細項：任何關閉開關（含 production code 裡的 NullSink）、以時鐘推算觸發點類別、以 `AlertEvent` 承載維運告警。

## Decision（決策）

### D-1：模組與 import 規則

| 模組 | 內容 | 可 import |
|---|---|---|
| `app/ops_alert/model.py` | `OpsAlert`（frozen）、`OpsAlertSink` Protocol（`emit(alert) -> None`，保證不拋例外）、事件名稱的封閉列舉、每種事件的 payload 型別、`OPS_ALERT_PUSH_MAX_LIST_ITEMS`、`OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS` | 只有標準庫 |
| `app/ops_alert/render.py` | 純函式：產生 `ops alert:` log 行與推播文字；固定標籤常數；推播上限以參數接收 | `app.ops_alert.model` |
| `app/ops_alert/sink.py` | **唯一**的 `OpsAlertSink` 實作；`OPS_ALERT_PUSH_MAX_CHARS`（由 push_channels 的兩個上限與安全餘量常數計算） | 標準庫、`app.ops_alert.*`、`app.push_channels` |
| `app/ops_alert/selftest.py` | 手動自測進入點（D-9） | `app.ops_alert.*` |
| `app/push_channels.py` | 自 `app/alerts/notify.py` 抽出的共用傳輸：環境變數名稱、Telegram URL 樣板、POST、逾時、R-1 的安全失敗格式；兩個通道的單則上限常數，以及其出處網址與查證日的字串常數 | 標準庫、`httpx`、`app.logging_setup`（R-1 放的共用遮罩模組） |

方向限制：

- `app.forecast.*` **只可以** import `app.ops_alert.model`；不得 import `app.ops_alert` 的其他模組、`app.push_channels`、`httpx`、`app.alerts.*`。
- `settlement.py`、`scoring.py`、`correction.py`、`audit.py`、`validation.py`、`store.py` 完全不 import `app.ops_alert.*`（AST）。
- `app.ops_alert.*` 不得 import `app.forecast.*`、`app.alerts.*`、`app.settings.*`、`app.api.*`。
- `app.alerts.*` 不得 import `app.ops_alert.*`。`app.alerts.notify` 與 `app.ops_alert.sink` 都經過 `app.push_channels` 送出。
- 編排函式以關鍵字參數 `ops_alert_sink: OpsAlertSink` 接收送出器，**沒有預設值**，由 `scheduler.py` 組裝時注入（ADR-0027 D-7.2 字面二）。
- 送出器實作只在 `scheduler.py` 組裝處與 `app/ops_alert/selftest.py` 中建立（AST 列舉建構點）。`app/` 內 `OpsAlertSink` 的實作恰好一個：`app/ops_alert/sink.py` 中明示繼承 `OpsAlertSink` 的那一個類別。`app/` 內其他類別不得定義參數註記為 `OpsAlert` 的 `emit`（AST；`logging.Handler.emit` 之類不受影響）。同一類別另有 `deliver()`（D-9），不構成第二個實作。測試用的 fake 放在 `tests/`，不放在 `app/`。

### D-2：`OpsAlert` 模型與封閉事件列舉

`OpsAlert` 欄位：

| 欄位 | 內容 |
|---|---|
| `event` | 封閉列舉（見 D-7）。全小寫、點分隔，與 log 的 `event=` 及推播標題一致 |
| `severity` | 固定 `WARNING` |
| `occurred_at` | UTC ISO8601。編排函式發出的告警，取自它持有的 store 時鐘；E-3b 與 `step = orchestrator` 的 E-3d，取自 `scheduler.py` 組裝時注入 listener 與 job 包裝的同一個 store 時鐘；selftest 為 None。`app/ops_alert/**`（含 `selftest.py`）不呼叫 `datetime.now`／`time.time`（AST） |
| `execution_started_at` | UTC ISO8601。**編排函式開始時讀一次**的 store 時鐘，該次執行的所有告警共用同一個值。E-3b、`step = orchestrator` 的 E-3d、selftest 為 None：E-3b 沒有執行可言；`step = orchestrator` 由 `scheduler.py` 的 job 包裝發出，拿不到編排函式讀到的值，不另讀時鐘代替 |
| `source` | 列舉 `settlement`／`audit`／`correction`，或 None；取值依規則 4「適用對照」。E-1、E-2 的值與 ADR-0027 例外屬性或守衛呼叫端的 `source` 逐字相同 |
| `step` | 列舉 `record`、`settlement`、`gap_audit`、`late_scan_correction`、`validation_snapshot`、`plan`、`orchestrator`，或 None；前六個依序對應 ADR-0027 D-7 第 2 點的六步。取值依規則 4「適用對照」 |
| `write_outcome` | 封閉列舉 `not_written`、`written_without_registration`、`deferred`、`not_started`、`unspecified`，或 None（只限 selftest）；定義與取值依規則 4「適用對照」 |
| payload | 每種事件一個 frozen payload 型別，欄位定義見 D-7 |

規則：

1. **只收結構化屬性**：`OpsAlert` 的任何欄位不接受「例外原文」。例外類別名稱只放 `exception_class`（E-3d），並以 `^[A-Za-z_][A-Za-z0-9_]*$` 驗證（取 `type(exc).__name__`，見 D-3 第 10 點）。
2. 日期欄位是 ISO8601 字串（日期或 UTC 時間），整數欄位是 `int`，列舉欄位是列舉成員；model 建構時驗證型別，不合法即拋 `ValueError`（建構失敗）。
3. render 不得以 `vars()`、`__dict__`、`dataclasses.asdict` 迭代任意屬性（AST）。每個 payload 欄位在 `render` 都必須有一個登記的標籤常數；測試逐一列舉 dataclass 欄位，缺標籤即失敗（對應 D-4 的正面白名單）。
4. **適用對照**（tech-architect 2026-10-18 確認）。表外的組合在 model 建構時拒絕（OA-23）：

   | 事件 | `source` | `step` | `write_outcome` |
   |---|---|---|---|
   | E-1 | `settlement` | `settlement` | `not_written` |
   | E-1 | `correction` | `late_scan_correction` | `not_written` |
   | E-2 | `settlement` | `settlement` | `not_written` |
   | E-2 | `audit` | `gap_audit` | `written_without_registration` |
   | E-2 | `correction` | `late_scan_correction` | `deferred`（落檔前提見 D-7 規則） |
   | E-3b | None | None | `not_started` |
   | E-3c | `settlement` | `settlement` | `not_started` |
   | E-3d | None | 七個 `step` 值之一 | `unspecified` |
   | `ops_alert.selftest` | None | None | None |

   - `not_written`：該步的結果寫入交易已 rollback；`forecast_outcome`、`forecast_settle_eval`、`forecast_correction_job_end`、`forecast_void_late_diag` 沒有新列（ADR-0027 FL-71 (c)）。同一步先前以獨立交易 commit 的列不在此限：結算評估 ③ 的查證紀錄與 X2 確認（①′ 成立時沒有這些列），以及更正作業 ③ 的 `forecast_correction_job` 列與未觀察平日登記。
   - `written_without_registration`：缺日稽核已 commit `forecast_gaps` 與 `forecast_gap_audit`，但沒有做 A-77 第 10 項登記（ADR-0027 D-7 第 2 點 Q7）。只在缺日稽核 commit 之後發出；缺日稽核拋例外時改發 E-3d，不發 E-2。
   - `deferred`：更正作業本次不啟動，四類觸發延後，W、W_E、W_V、W_S 都不前進。
   - `not_started`：該步沒有啟動，沒有寫入。E-3b 指的是整個 job 的該次觸發。
   - `unspecified`：編排函式無法斷言該步留下哪些列。E-3d 一律用這個值，因為任意例外的拋出位置無法由型別判定；各步實際的寫入由 ADR-0027 的 FL 格保證。

### D-3：送出器行為

1. **log 先寫，而且每次都寫**：每次 `emit` 都寫一行 `ops alert:` WARNING，不去重。log 行永遠帶完整欄位與完整清單。
2. **推播以 (`event`, `source`, `step`, `execution_started_at`) 去重，只在同一次執行內**：
   - `execution_started_at` 為 None 的告警（E-3b、`step = orchestrator` 的 E-3d、selftest）不去重，每次 `emit` 都推播，也不讀、不改鍵集合（tech-architect 2026-10-18 裁定）。理由：E-3b 由 scheduler 的派送執行緒呼叫，`max_instances` 事件發生時正有一次執行在跑，若以它換掉鍵集合，執行中的那一次會重複推播；APScheduler 對同一個觸發時刻只送一次事件；`step = orchestrator` 每次 job 呼叫至多一則。
   - 鍵集合的讀寫以 `threading.Lock` 保護。這個鎖只保護行程記憶體內的集合，不構成跨執行狀態。
   - 送出器只保留「目前這次執行」的鍵集合在**行程記憶體**；收到不同執行識別的告警時，整個集合換掉。不寫檔、不寫資料庫、不跨執行。
   - 行程重啟只會多推一則，不會少推；`execution_started_at` 若因時鐘問題與前一次相同，該次推播會被壓掉但 log 照寫。後一點是殘餘風險，見 Consequences。
3. **沒有冷卻、門檻或開關**：不讀 `settings.alerts.*`（`app.ops_alert.*` 不得 import `app.settings.*`）；沒有環境變數、設定表或 API 能關掉維運告警；production code 沒有 NullSink。
4. **送出失敗不影響流程**：`emit` 內部對 log 與推播各自 `try/except Exception`，永遠不拋；`KeyboardInterrupt`、`SystemExit` 不接（與 ADR-0027 FL-71 (b) 一致）。失敗只記一行 ERROR：
   `ops alert delivery failed: channel=<discord|telegram> error_class=<例外類別名> [status=<HTTP 狀態碼>]`，格式由 `describe_failure()` 產生，**不含例外字串與 URL**。
5. **render 本身出錯**：`emit` 記一行 ERROR `ops alert render failed: event=<列舉值> error_class=<類別名>`，不拋、不阻擋後續步驟，推播不送（沒有可送的文字）。
6. **兩個通道獨立**：依序送 Discord、Telegram；一個失敗不跳過另一個；每次 POST 逾時沿用 `push_channels` 的常數（現為 5 秒，`notify.py` 的 `REQUEST_TIMEOUT_SECONDS`）。
7. **送出時機**：編排函式在該步結束之後（交易已 rollback；E-2 `audit` 為已 commit）、下一步開始之前呼叫（ADR-0027 D-7.2 字面二）；送出器本身不知道交易狀態。
8. **啟動時的通道檢查**：`scheduler.py` 註冊 `forecast_record` 時，以 `push_channels` 的純判定函式（只回傳通道名稱的集合，不回傳任何設定值）檢查是否至少有一個通道設定完整（Discord：URL 非空；Telegram：token 與 chat id 皆非空）。沒有時記一行 ERROR：`ops alert channel not configured; forecast exceptions will only reach the log`。**這只是補強，不能取代 D-10 的自測**：它檢查不出 URL 打錯或 token 失效。
9. 同步呼叫，不開執行緒、不建佇列（避免新增狀態與漏送）。阻塞上限見 Consequences。
10. **建構失敗不中止流程**：`OpsAlert` 在 `emit` 之外建構，建構失敗（D-2 規則 2 的 `ValueError`）不在 `emit` 的保證範圍內。`recorder.py` 與 `scheduler.py` 的每一個建構點，都以 `try/except Exception` 包住建構與 `emit` 呼叫。建構失敗時記一行 ERROR `ops alert build failed: event=<列舉值> error_class=<類別名>`，不含例外字串，不拋、不中止後續步驟。`exception_class` 一律取 `type(exc).__name__`；不符 D-2 規則 1 的格式，或長度超過常數 `OPS_ALERT_EXCEPTION_CLASS_MAX_CHARS`（128）時，以固定值 `invalid_exception_class` 代替，不讓建構失敗。

### D-4：推播格式與截斷

**格式**

- 標題固定 `[stock-desk 維運告警] <event>`（與使用者警示的 `[stock-desk 警示]` 區分）。
- 內文每行 `<標籤>：<欄位值>`，順序固定。**不帶免責句、不帶任何建議或方向用字、不帶處置指示。**
  - 處置指示（例如收到 E-2 要停 scheduler）只寫在部署手冊 §5，不寫在推播裡：「立即」「馬上」等祈使與急迫用字在風控禁用詞清單 B 類，而且推播只該陳述事實。

**正面白名單渲染（第一道防線）**

推播文字**只能**由下列四種成分組成，其餘位置一律不得有自由文字：

1. 標題常數 `[stock-desk 維運告警]`；
2. 事件名稱（`forecast.*`、`ops_alert.selftest`）；
3. `render` 模組登記的固定標籤常數（例如「受影響預測筆數」「最早一日」「最晚一日」，以及截斷提示「另有 N 筆，完整清單見 scheduler log」）；
4. 欄位值（日期、整數、列舉成員、經 D-2 驗證的類別名稱）。

**禁用詞掃描（第二道防線）**

- 適用範圍：每一個事件（E-1、E-2、E-3b～E-3d、selftest）渲染出的推播全文，以及 `ops alert:` log 行。
- 清單**引用 ADR-0027 FL-71 (f)**（同批落檔）：ADR-0027 本批把風控 2026-10-18 審查第二節「FL-71 (f) 推播禁用詞清單」（類別 A～F 與其「白名單例外」）放在 FL-71 (f) 下方的「推播禁用詞清單」〔事實：2026-10-18 讀 ADR-0027 工作樹，`FL-71` 段，行號會漂移〕。本 ADR 不手抄清單，避免兩處不一致。
  - **單一來源**（tech-architect 2026-10-18 裁定；可行性由 dev-lead 確認）：清單的唯一來源是 ADR-0027 FL-71 (f) 的「推播禁用詞清單」區塊。測試在執行時讀取該 ADR 檔，以起訖錨點 `**推播禁用詞清單**`、`**白名單例外**` 截取區塊，從中取出：A、C、D 類的「」詞，A 類的 regex，C 類的英文詞界清單，F 類的反引號字串。B 類照清單所寫，讀 `apps/stock-desk/shared/forbidden-terms.json` 的 `guarantee`、`price_target` 與 `FRONTEND_FORBIDDEN_TERMS`，沿用後端測試既有的讀取函式，不另抄。E 類，以及 F 類的假 token、假 URL、哨兵字串，由 fixture 提供。錨點找不到，或 A～D、F 任一類取出 0 筆時，測試失敗。不新增清單檔，也不把 A、C、D 類加入 `shared/forbidden-terms.json`：該檔是使用者面措辭的共用清單，「漲」「跌」「正常」「最新」等字在使用者面有合法用途。dev-lead 若判定以 ADR 文字為測試來源不可行，退回 tech-architect 改案，不得自行另建第二份清單。
  - **讀取的最小格式要求**（dev-lead 2026-10-18 可行性確認；tech-architect 2026-10-19 確認）。測試依下列格式解析 ADR-0027 FL-71 (f) 的區塊。第 1、2、4 條與第 3 條末句由測試檢查，不成立時測試失敗，不得改以寬鬆解析；第 3 條其餘部分與第 5 條是編寫約定，改動該區塊時由 qa-reviewer 對照：
    1. 錨點是「行首（縮排後）`- ` 緊接 `**推播禁用詞清單**`／`**白名單例外**`」的清單項，在 ADR-0027 全檔各恰好一個，起錨點在前；測試以此行首樣式比對，不以子字串比對。其他位置出現的錨點字串不算錨點。
    2. 類別標題固定為行首（縮排後）`- **X. 名稱**：`，X 為 A～F，在起訖錨點之間各恰好一個。只在各類標題之下、依上一點所列的類別與成分取詞，E 類不取詞；起錨點那一行與 A 類標題之間的文字（含標題括號、「適用範圍」「比對規則」）不取詞。
    3. A、C、D 類的「」只放禁用詞本身，說明一律寫在全形括號或標題裡。B 類的「」只是舉例，不作為掃描來源（B 類的來源見上一點）；測試斷言這些舉例詞都包含在 B 類的讀取結果之內。
    4. A 類 regex 寫成 `` regex `…` ``。C 類英文寫成單一清單項，內容以「英文，詞界：」開頭，以「、」分隔，每個詞只含 ASCII 字母。
    5. F 類的反引號只放字面禁用字串；非字面項（假 token、假 webhook URL、哨兵字串）不加反引號，由 fixture 提供。
    6. 比對語意（英文不分大小寫的範圍、`\b` 的詞界判定）只依 ADR-0027 FL-71 (f)「比對規則」，本 ADR 不另定；測試以 `re.IGNORECASE | re.ASCII` 實作英文項與 A 類 regex 的比對。
    7. 測試以 ADR-0027 的完整檔名常數定位（不用 glob），以 UTF-8 讀取。
- 標籤常數本身也要通過類別 A～D 的掃描。白名單例外只限上列四種位置，其餘位置照樣掃描。
- 類別 E（識別資訊）以哨兵值斷言，不以 regex 猜代號；類別 F（祕密、路徑、例外原文）與 R-1 一致。

**截斷與欄位完整性**

- **推播帶 E-1 的全部欄位；只有 `unregistered_session_dates` 依本點截斷，其餘欄位不截斷、不省略。**（風控 A-4 required）
- `unregistered_session_dates` 在推播中最多列 `OPS_ALERT_PUSH_MAX_LIST_ITEMS` 筆（常數，值為 20），升冪；永遠帶 `unregistered_count`（完整清單的筆數）、最早一日與最晚一日（取自完整清單，不是取自被列出的部分）。
- 超過上限時加一行「另有 N 筆，完整清單見 scheduler log」，N ＝ `unregistered_count` 減去已列出的筆數。log 行永遠是完整清單。
- 不採分則送出：分則會讓同一個去重鍵有多則訊息，而且「完整」只是形式。風控同意。
- **推播文字長度 ≤ 常數 `OPS_ALERT_PUSH_MAX_CHARS`**，定義為「各通道單則上限的較小值，減去安全餘量」。
  - **通道上限的數值【未查證】**：起草者 2026-10-18 嘗試以 `curl` 讀 Telegram 官方 Bot API 文件與 Discord 官方開發者文件，均被 session 的出口代理以 403 擋下（`core.telegram.org`、`discord.com` 不在允許清單）；經 GitHub 取 Discord 官方文件庫同樣被拒。**本 ADR 不寫任何數值**，記憶中的數字不得寫死。待查證的官方出處：
    - Telegram：Bot API 文件 `https://core.telegram.org/bots/api` 的 `sendMessage`，`text` 參數的長度限制，以及該限制是在「實體解析之後」計算還是之前。現行程式送出時不帶 `parse_mode`〔事實：`notify.py` 送 `{"chat_id", "text"}`〕。
    - Discord：開發者文件 `https://discord.com/developers/docs/resources/webhook` 的 Execute Webhook，`content` 的長度限制。現行程式送 `{"content": text}`。
  - 計數單位（code point、UTF-16 code unit 或 bytes）亦【未查證】。緩解：推播文字限定為 BMP 字元（標籤為中文、欄位值為 ASCII 或數字、不使用 emoji），這時 code point 與 UTF-16 code unit 的計數相同〔推論〕；bytes 單位若官方如此規定，須另定常數。
  - 查證後，兩個通道的數值寫入 `app/push_channels.py` 的常數；出處網址與查證日寫成同一檔內的字串常數，每個通道各一組（名稱由 dev-lead 定）；並補進本 ADR 的修訂紀錄。`OPS_ALERT_PUSH_MAX_CHARS` 定義在 `app/ops_alert/sink.py`，由這兩個常數與 `OPS_ALERT_PUSH_SAFETY_MARGIN_CHARS`（值與理由由 devops-sre 於查證時定）**計算得出**，不另外手打數字。`render` 以參數接收上限，不 import `app.push_channels`（D-1）。
  - 查證完成之前，D-10 第 3 項不通過（擋 D_v）。
- `render` 組裝後必須以 `len(text)` 斷言不超過上限；超過時先減少列出的筆數（仍 ≤ 20），固定欄位不得被截。固定欄位本身有界（日期、整數、有長度上限的類別名稱），以最大寬度 fixture 測試。

### D-5：安全

1. 失敗格式一律用 R-1 的 `describe_failure()`（只含類別名與 HTTP 狀態碼）；URL 或含 URL 的文字經 `redact_url()`。
2. `app/ops_alert/**`、`app/push_channels.py` **禁止** `str(exc)`、`repr(exc)`、`exc_info`、`logger.exception`、`traceback`（AST）。
3. 推播與 log 只由 D-2 的結構化屬性組成。例外含敏感字串時（fixture 在例外訊息塞假 token、假路徑）兩者都不得出現。
4. logger 名稱 `app.ops_alert`。在 `configure_logging()` 之下 `app` 是 INFO、root 是 WARNING，所以 WARNING 與 ERROR 一定輸出；測試不得依賴 `SecretRedactionFilter`（pytest 已有 root handler 時 `configure_logging()` 不安裝它），該 filter 只是縱深防禦。
5. 送出前，推播文字與 log 行再經一次 `redact_url()`（縱深，不取代欄位白名單）。
6. 環境變數名稱與 Telegram URL 樣板在 `app/` 內只出現在 `app/push_channels.py`（grep）。憑證由 CEO 自行設定；devops-sre 不碰 `.env`，不新增環境變數，沿用 `ALERT_DISCORD_WEBHOOK_URL`、`ALERT_TELEGRAM_BOT_TOKEN`、`ALERT_TELEGRAM_CHAT_ID`。
7. 自測輸出（D-9）同樣只印通道名稱、狀態與類別名，不印 URL、不印設定值。

### D-6：`forecast_record` 的 skipped listener

- `scheduler.py` 組裝時註冊一個 listener，mask 為 `EVENT_JOB_MAX_INSTANCES | EVENT_JOB_MISSED`，送出器在註冊時注入。
- 只處理 `job_id == "forecast_record"`；其他 job id 不推播、也不寫 `ops alert:` 行（它們現行的行為不變）。
- 事件屬性（3.11.3，已於 Context 驗證）：`EVENT_JOB_MAX_INSTANCES` 取 `scheduled_run_times`（list）、`EVENT_JOB_MISSED` 取 `scheduled_run_time`；統一轉成 UTC ISO8601 升冪的 tuple，放進 E-3b 的 `skipped_run_times`。
- 以 APScheduler 的事件物件直接呼叫 listener 測試，不實際排程。
- listener 在 scheduler 的派送執行緒上同步執行；D-3 第 9 點的阻塞上限適用。送出器不拋例外，所以 scheduler 的 `Error notifying listener` 路徑不應被走到；若走到，該筆 traceback 經 R-1 的 handler filter 遮蔽。
- 不以 `EVENT_JOB_ERROR` 為來源（`_guarded` 吞掉例外，永不送出）。

### D-7：事件目錄

| 事件 | 歸屬 | 觸發 | payload 欄位 |
|---|---|---|---|
| E-1 `forecast.unregistered_unobserved_weekday` | 必做 | 結算評估或更正作業拋出 `UnregisteredUnobservedWeekdayError`（ADR-0027 D-9.3「型別與欄位」） | `unregistered_session_dates`（升冪、不重複、非空）、`unregistered_count`、`affected_forecast_count`、`d_reg`（None 時寫 `none`）；`source = settlement`：`snapshot_from`、`snapshot_to`；`source = correction`：`recheck_from`、`recheck_to`、`market_scan_to`。不適用的欄位不出現 |
| E-2 `forecast.market_run_regressed` | 必做；`source` 為 `settlement`／`audit`／`correction`；**吸收原 E-3a**（晚到掃描的 W 大於市場 DB `MAX(run_id)`，ADR-0027 D-3「晚到資料的觸發」第 8 點） | `MarketRunRegressedError`（結算，D-9.2 ①′），或共同守衛 `market_run_regression` 成立（缺日稽核、更正作業；ADR-0027 D-7 第 2 點 Q7） | `market_run_current`（R）、`regression_kind ∈ {run_regressed, reference_identity_mismatch}`、`reference_kind ∈ {settle_eval, correction_job, gap_audit}`、`reference_value`、`reference_id`（`settle_eval_id`、`correction_job_id` 或 `audit_id`）、`reference_started_at`（UTC ISO8601；`reference_kind = gap_audit` 時為 `audit_now`）、`reference_recorded_at`（參考 run 存下的 `recorded_at`）、`current_recorded_at`（市場 DB 中 `run_id = reference_value` 那一列的 `recorded_at`，不存在時為 None）。`write_outcome`：結算 `not_written`、缺日稽核 `written_without_registration`、更正作業 `deferred` |
| E-3b `forecast.job.skipped` | 必做（屬 N-23 (1)；ADR-0027 D-7.1 已要求 listener） | D-6 的 listener；只對 `forecast_record` 推播 | `job_id`、`reason ∈ {max_instances, missed}`、`skipped_run_times`。`write_outcome = not_started` |
| E-3c `forecast.settle.deadline_not_started` | 建議納入（ADR-0027 D-7.2 視同結算失敗） | D-7.7 期限已到，結算評估沒有啟動 | `deadline_at`。`write_outcome = not_started` |
| E-3d `forecast.step.failed` | 建議納入；擴為「任一步失敗」，含 `step = orchestrator`（ADR-0027 D-7 第 2 點 Q8） | 任一步拋出 E-1／E-2 以外的 `Exception`，或該步回傳的型別化步驟結果（ADR-0027 D-7 第 2 點 Q8）標為失敗（這時 `exception_class` 為 None；前置條件不成立而略過、沒有觸發而不啟動、`inputs_not_ready`、E-2 守衛成立，都不屬於失敗）；或例外逃出編排函式本身（由 `scheduler.py` 的 job 包裝經同一個送出器發出，之後 `_guarded` 照舊記 ERROR） | `exception_class`（`type(exc).__name__`，不帶例外字串；失敗結果時為 None）。`step` 為共同欄位 |
| `ops_alert.selftest` | 手動自測 | D-9 | 固定自測欄位 |

規則：

- **每一步失敗只發一則，取最具體的事件**：E-1、E-2 優先於 E-3c、E-3d。
- 前置條件不成立而略過的步驟（例如結算失敗之後的驗證快照）不另發告警（ADR-0027 D-7.2 字面二）。
- E-2 的 `reference_*` 讓操作者對照 ADR-0026 D-9 第 2-1 點（備份順序與 manifest 檢查）manifest 中的最新市場 DB `run_id`。
- 推播量的調整只能是「同一次執行內的去重」。
- **E-2 `source = correction` 的落檔前提**：本列（`write_outcome = deferred`）依附 ADR-0027 D-7 第 2 點 Q7 的「更正作業」子點，以及 D-3「晚到資料的觸發」第 8 點的改字，兩者都屬 ADR-0027 第二批，要等 CEO #42 明示同意後才落檔。第二批落檔之前，ADR-0027 現行字面是「其餘觸發照常」，更正作業照常啟動，不符 `deferred`，所以本列與 OA-10 的 `correction` 格在第二批落檔前不得實作（correction.py 本來就擋 D-9）。CEO 不同意時，本列與 OA-10 依 ADR-0027 屆時的字面修訂：本 ADR 仍為 proposed 時原地修訂，已 accepted 時開新 ADR；並送風控重審（同下一點）。
- E-2 的 `source = correction`（`write_outcome = deferred`）以 ADR-0027 N-23 第二批（Q7 更正作業一面，待 CEO #42 明示同意）為前提。第二批落檔之前，ADR-0027 D-3「晚到資料的觸發」第 8 點照現行字面（其餘觸發照常），本列不得實作，推播不得以 `deferred` 陳述實際已啟動的更正作業；CEO 不同意時，本列與其 `write_outcome` 送風控重審。
- 上兩點對「CEO 不同意時」的處理一致為送風控重審；「送風控知悉」等較寬讀法不適用（修訂紀錄「合併規則」）。
- E-2 `source = audit`／`correction` 的欄位，取自 `market_run_regression()` 回傳的 `MarketRunRegression`，屬性 `market_run_current`、`regression_kind`、`reference_kind`、`reference_value`、`reference_id`、`reference_started_at`、`reference_recorded_at`、`current_recorded_at`，與 `MarketRunRegressedError` 的同名屬性逐字一致；`source` 由呼叫端決定。
- 後續追蹤清單 N-20 已在 ADR-0027 增列 E-2 的屬性 `regression_kind`、`reference_recorded_at`、`current_recorded_at`（tech-architect 2026-10-18 補充項回覆第 3 項；ADR-0027 N20-1、N20-2 的例外屬性，與本點同批落檔），本 ADR 已同步（見修訂紀錄「風控 2026-10-19 N-20 批裁定後修訂」）。依失效條件 5 已與 N-20 同批送風控，風控 2026-10-19 N-20 批已知悉確認（`work/reviews/2026-10-19-N20批裁定-風控.md`）。
- **render 的三個新標籤：草稿，待風控逐字確認（R-12）；不是定稿，確認之前 render 不得實作這三個標籤**（失效條件 5；風控 R-12 要求逐字送審）。方向（風控 R-12）：`reference_identity_mismatch` 只陳述事實，不得寫成「已確認被還原」；`current_recorded_at` 的標籤要寫清楚是「市場 DB 中同號 run 的 recorded_at」，不是目前最大 run 的，None 時顯示「不存在」、不得省略該行；不得出現禁用詞清單 B 類的急迫用字。草稿如下：
  - `regression_kind`：標籤「判定種類」；欄位值為列舉成員原樣（`run_regressed`、`reference_identity_mismatch`），符合 D-4 正面白名單第 4 項。備選：值改為固定常數「最新 run 編號小於參考 run」「參考 run 身分不符」，這要把這兩句也登記為固定標籤常數（D-4 第 3 項）。甲、乙擇一，請風控裁定。
  - `reference_recorded_at`：標籤「參考 run 的 recorded_at」；值為存下的原字串。
  - `current_recorded_at`：標籤「市場 DB 中同號 run 的 recorded_at」；值為原字串，None 時顯示固定常數「不存在」。
  - 這三組標籤與「不存在」尚未跑 D-4 的禁用詞掃描（類別 A～D），也未經 tech-architect 對照 ADR-0027 FL-71 (f) 清單；以上都不是定稿。
- **render 在「兩個 recorded_at 相等、但 kind 或 session_date 不同」時的處理（風控 suggested，待辦）**：E-2 目前只帶 `recorded_at`，這種情形下操作者會看到「值相同卻說不符」。處理方式二擇一，待 tech-architect 與風控決定：加一句固定常數說明差異在 kind 或 session_date，或 E-2 改帶完整身分（ADR-0027 N20-5 的 `reference_identity`、`current_identity`）。決定前不得實作 render 的這一格；新增的固定句比照 R-12 逐字送風控。

### D-8：不做「已恢復」通知，不存跨執行狀態

- 本版不推播「已恢復」，也不新增狀態表或狀態檔。要做就另立 ADR（需先決定狀態存放處）。
- 恢復的判準由事實檢查，不靠推播：下一次執行的 `forecast record run:` INFO 行（ADR-0027 D-7 第 2 點 Q8，含每一步的 outcome）顯示各步 outcome 為完成、同一次執行沒有 `ops alert:` 行、`last_settle_eval_at` 前進（`GET /api/forecast/status`，尚未實作）。
- 推播不得暗示一切正常（風控禁用詞類別 D：「已恢復」「恢復正常」「正常」「無異常」「成功」等）。

### D-9：自測 `ops_alert.selftest`

- 進入點：`python -m app.ops_alert.selftest`，只在操作者手動執行時送出；scheduler 與 API 都不 import 它，沒有排程、不常駐。
- 內容：固定的自測欄位與標題，走**與正式事件相同的 render 與 sink 路徑**（同一個 sink 類別另提供 `deliver(alert)`，回傳逐通道結果：與 `emit()` 共用同一組 log、render 與送出程式，不去重，同樣不拋例外；逐通道結果只含通道名稱、`sent`／`skipped`／`failed`、`error_class`、`status`。`deliver()` 不屬於 `OpsAlertSink` Protocol；在 `app/` 內只可由 `sink.py` 本身與 `selftest.py` 呼叫（AST）；`app.forecast.*` 與 `scheduler.py` 只呼叫 `emit()`）。事件 `ops_alert.selftest` 只允許在 `selftest.py` 建構（AST）。
- 輸出：逐通道 `sent`／`skipped`／`failed`；`failed` 時只印 `error_class` 與 `status`。結束碼：至少一個通道 `sent` 為 0，否則為 1。
- `sent` 只代表通道回了 2xx。**「確認送達」還需要 CEO 在對應的聊天室看到該則訊息**，並記入 D_v 驗收紀錄。

### D-10：D_v 閘門

D_v（結算程式上線前的驗收點）前，下列項目全部成立，缺一不上線：

1. R-1 修補已合併，且有測試；CEO 已完成主機 log 清查與必要的輪換。
2. **至少一個推播通道由 CEO 設定完整，並以 `python -m app.ops_alert.selftest` 確認送達**（結束碼 0，且 CEO 在聊天室看到該則訊息）。只在啟動時記 ERROR（D-3 第 8 點）不夠。通道的環境變數或憑證變更後，要重跑。
3. 兩個通道的單則字元上限已查證、附官方出處與查證日，`OPS_ALERT_PUSH_MAX_CHARS` 由其計算得出（D-4）。
4. D-3 第 8 點的啟動通道檢查已存在並有測試。
5. 部署手冊 §5 已補齊本 ADR 列出的待補項（含 E-2 立即停 scheduler 與「沒有推播不代表正常」）。
6. ADR-0027 FL-71 全部格與本 ADR 的 OA 條款全部通過；qa-reviewer 審查通過（無 `BLOCKING_ISSUES`）。
7. CEO 已核可本 ADR。
8. `render` 模組初版的標題、固定標籤常數與模板全文（含 `ops_alert.selftest` 的固定自測欄位）已送風控知悉級確認：不含處置指示、建議或狀態宣稱。之後的變更依「失效條件」第 5 點。

dead-man's switch（R-4）**不是**本閘門的項目，另案由 CEO 決定。

## Consequences（後果）

**好處**

- 第一次發生就推播，不設次數門檻、不設冷卻；每次發生都留 log，完整清單永遠在 log。
- 與使用者警示完全分離：不共用開關、冷卻、標題、免責句與 `AlertEvent`。
- `app.forecast.*` 只依賴一個無 I/O 的型別模組；送出器必填，接線遺漏會在建構時失敗，而不是靜默。
- 沒有新依賴（`httpx>=0.28`、`apscheduler>=3.11.3,<4` 為現有）、沒有 schema 變更、沒有新狀態。

**壞處與代價（誠實揭露）**

- **沒有收到推播，不代表排程正常**：scheduler 停止、容器停止或 job 沒有註冊時，不會有任何事件（devops-sre R-4；外部監控另由 CEO 決定）。部署手冊 §5 也要寫同一句。本 ADR 沒有 dead-man's switch。
- **E-2 停止出現，不代表已處理**：共同守衛不存跨執行狀態。市場 DB 被還原後，新寫入的 run 不會使判定解除；只有參考 run 的身分相符（例如依 ADR-0026 D-9 第 4 點整組還原）時才解除（ADR-0027 N-20）；遺失的 run 不會回來，還原後的 `run_id` 也可能與遺失的時間線重號〔推論：還原後 `run_id` 由還原檔的序號接續，ADR-0027 D-3 標為推論〕。所以「直到處理」靠 E-2 推播與 ADR-0026 D-9.4 的操作程序維持，不是程式保證（後續追蹤清單 N-20）。這是 E-2 推播與部署手冊「立即停 scheduler」兩者缺一不可的原因。還原點不早於任何參考 run 時，守衛偵測不到，E-2 不會出現（ADR-0027 D-7 第 2 點殘餘）。
- 持續失敗時每次執行每步至多一則。ADR-0027 D-7 第 2 點有六步加 `orchestrator`；每日兩次例行執行（22:10、23:10）加可能的一次啟動補跑。以 E-2 為例，三個 source 同時成立時每次執行 3 則、每日 6 則；最壞情形（每步各一則）每次執行不超過 7 則；E-3b 另計，每個被略過的觸發事件一則。若 CEO 認為太吵，唯一允許的調整是「同一次執行內的去重」，不得改成跨執行靜默。
- 推播不帶「首次發生時間」或「第幾次」；操作者以 log 的 `execution_started_at` 與 `last_settle_eval_at` 判讀持續天數。
- **同步送出的阻塞**：每次 `emit` 最壞 2 個通道 × 逾時（現為 5 秒）。在編排函式內，這會延後下一步；在 listener 內，會延後 scheduler 派送執行緒（其他 job 的觸發）。以 `forecast_record` 的 `misfire_grace_time=1800` 與其他 job 的間隔相比，我判斷可接受〔推論，未實測〕；若實測不可接受再另提（例如有界佇列），那會新增狀態，須重審本 ADR。
- **去重鍵的殘餘風險**：若 store 時鐘使兩次執行的 `execution_started_at` 相同，第二次的推播會被當成重複壓掉（log 照寫）。屬極低機率的時鐘異常；D-10 不另設閘門。
- 推播與使用者警示共用同一個通道（可能同一個聊天室）。標題區分；推播文字不帶免責句，所以使用者可能把它當成產品警示。標籤與模板變更要依「失效條件」送風控。
- 完整清單只在 scheduler log。容器部署時 `compose.yaml` 沒有設 logging driver 選項，Docker 預設 json-file 沒有大小上限〔推論：依 Docker 文件所述，未在本機驗證〕，長期保存與輪替另行確認（部署手冊待補項）。
- 禁用詞清單以 ADR-0027 文字為測試來源：在 `.github/workflows/stock-desk.yml` 的 paths 涵蓋 ADR-0027 之前，只改清單的 commit 不會觸發後端測試，清單改壞要等下次改到 `apps/stock-desk/**` 才會被發現〔事實：dev-lead 2026-10-18 可行性確認第 1 節〕；paths 由 devops-sre 隨測試實作補上。
- R-1 沒修之前不得上線（D-10 第 1 項）。
- `app/alerts/notify.py` 要重構經 `push_channels`；該重構在 R-1 合併之後，且不得改變使用者警示的行為（既有 `tests/test_alerts_notify.py` 須原樣通過）。

**被此決策約束的事**：對實作的約束見下節 OA。

**回滾方式**

本 ADR 只是文件。落地後若要退回：移除 `app/ops_alert/`、`app/push_channels.py` 的抽出（把函式放回 `notify.py`）與編排函式的 `ops_alert_sink` 參數、`scheduler.py` 的 listener 與通道檢查即可。沒有 schema、沒有狀態檔、沒有新依賴；`ops alert:` log 行與推播消失，但 ADR-0027 D-7.2 原有的 WARNING 與 fail-closed 行為不受影響。ADR 本身不得原地改寫，退回要開新 ADR 取代（ADR-0001）。

## 對實作的約束（OA）

驗證方式欄的「設計稿」指 `work/stock-desk-N23結算例外告警設計-2026-10-18.md` §5 的測試格。tech-architect 約束的編號為其 2026-10-18 提案「對實作的約束」第 1～8 點（記為 TA-1～TA-8）。所有測試不得連網（`httpx.MockTransport`）、不得讀真實環境變數（`monkeypatch`）、不得碰 `apps/stock-desk/backend/data/*.db`。

| 編號 | 條款 | 驗證方式 | 對應 |
|---|---|---|---|
| OA-1 | `app/forecast/**` 對 `app.ops_alert` 套件只可 import `app.ops_alert.model`；`settlement.py`、`scoring.py`、`correction.py`、`audit.py`、`validation.py`、`store.py` 不 import `app.ops_alert.*`、`httpx`、`app.alerts.*`、`app.push_channels` | import graph／AST | TA-1；設計稿格 14、16 |
| OA-2 | `app.ops_alert.*` 與 `app.alerts.*` 互不 import；`app.ops_alert.*` 不 import `app.forecast.*`、`app.settings.*`、`app.api.*`；`app.ops_alert.model` 只 import 標準庫；`app.push_channels` 只 import 標準庫、`httpx`、`app.logging_setup` | import graph | TA-2；格 16 |
| OA-3 | 編排函式的 `ops_alert_sink` 沒有預設值；`app/` 內 `OpsAlertSink` 的實作恰好一個；沒有環境變數、設定、API 或 production NullSink 能關掉維運告警 | AST／grep；實作的判定方式依 D-1 最後一點 | TA-3；格 6、20 |
| OA-4 | 環境變數名稱與 Telegram URL 樣板在 `app/` 內只出現在 `app/push_channels.py`；`app/alerts/notify.py` 的既有測試原樣通過 | grep；既有測試 | TA-4；格 11 |
| OA-5 | 推播與 log 只由 D-2 的結構化屬性組成；`app/ops_alert/**`、`app/push_channels.py` 沒有 `str(exc)`、`repr(exc)`、`exc_info`、`logger.exception`、`traceback`；render 不迭代任意屬性 | AST；例外含假 token 與假路徑的 fixture | TA-5；格 9、11 |
| OA-6 | E-1、E-2 的欄位只取自 ADR-0027 的例外屬性或 `MarketRunRegression` 的屬性（`unregistered_count` 由 `len(unregistered_session_dates)` 導出），不解析例外字串；R 倒退在 ② 之前拋出、E-1 的兩層型別與轉換位置，依 ADR-0027 FL-71 (c)(d)(e) | 逐欄斷言 | TA-6；格 1～3 |
| OA-7 | 禁止：跨執行去重或冷卻；「已恢復」通知；新增狀態表或狀態檔；以時鐘推算觸發點類別；告警送出失敗時中止後續步驟 | `app/ops_alert/**` 無 `sqlite3`、`open(`、`pathlib` 寫入、`datetime.now`（AST）；`cron_2210`、`retry_2310` 全 repo 0 筆（grep）；送出失敗時缺日稽核照常寫入 | TA-7；格 5、6、12、20 |
| OA-8 | ADR-0027 FL-71 全部格通過；本表全部通過 | qa-reviewer 逐條 | TA-8 |
| OA-9 | E-1：第一次發生就恰好 1 則推播加 1 行 `ops alert:` WARNING；欄位逐一斷言（含 `execution_started_at`、`step`、`d_reg = None` 的格）；`source = correction` 的格帶 `recheck_*`、`market_scan_to`，不帶 `snapshot_*` | 單元測試，fixture 的第一次執行即觸發 | 格 1、2、4 |
| OA-10 | E-2：`settlement`、`audit`、`correction` 各一格；`regression_kind`／`reference_kind`／`reference_value`／`reference_id`／`reference_started_at`／`reference_recorded_at`／`current_recorded_at` 與 `write_outcome` 逐欄斷言；參考值取自更正作業的一格；身分不符一格（`regression_kind = reference_identity_mismatch`、R 不小於參考值，`reference_recorded_at` 與 `current_recorded_at` 不同，或市場 DB 無該 run 而 `current_recorded_at` 為 None）；`source = settlement` 時 `forecast_settle_eval`、`forecast_outcome` 無新列 | 單元測試 | 格 3；ADR-0027 FL-71 (e)(l) |
| OA-11 | 去重：同一次執行內同一鍵被接住兩次 → 推播 1 則、log 2 行；22:10、23:10、隔日各推 1 則；`settings.alerts.*`（`enabled`、`notify_webhooks`、`cooldown_minutes`）任何值都不改變推播數；同一次執行 E-1 的兩個 source、E-2 的三個 source 各別推播；E-3b 與 `step = orchestrator` 不去重：同一個事件物件呼叫兩次 → 推播 2 則；E-3b 發生在一次執行進行中 → 該執行其後的同鍵告警仍只推 1 則（鍵集合不被換掉） | 單元測試 | 格 5、6、7；FL-71 (f) |
| OA-12 | 推播與 log 通過 D-4 的禁用詞掃描與正面白名單（每個事件、含 selftest；標籤常數本身也掃；類別 E 以哨兵值斷言）；掃描清單依 D-4「單一來源」一點，於測試執行時讀取，測試內不手抄；錨點找不到或任一類取出 0 筆即失敗 | 單元測試 | 格 8；ADR-0027 FL-71 (f) |
| OA-13 | 截斷：超過 `OPS_ALERT_PUSH_MAX_LIST_ITEMS` 時，推播含 `unregistered_count`、最早一日、最晚一日與「另有 N 筆，完整清單見 scheduler log」，其餘欄位完整，log 行含完整清單；推播長度 ≤ `OPS_ALERT_PUSH_MAX_CHARS`，以最大寬度 fixture 斷言；`OPS_ALERT_PUSH_MAX_CHARS` 由兩個通道上限常數計算得出，且兩個通道上限的出處與查證日字串常數存在且非空（缺則測試失敗） | 單元測試；常數存在性測試 | 格 10；D-4 |
| OA-14 | R-1 修補已合併，且 Telegram 回 404／500 時，log、`DeliveryResult.detail` 與 caplog 全文都不含假 token 與完整 URL；抽出 `push_channels` 後同一組測試仍通過 | R-1 的測試＋重跑 | 格 11 |
| OA-15 | 通道 4xx／5xx／逾時／例外 → `emit` 不拋、記 `ops alert delivery failed`（只含 `channel`、`error_class`、`status`）、缺日稽核照常寫入；render 出錯 → 記 `ops alert render failed`、不拋 | 單元測試；與 ADR-0027 FL-71 (b)(f) 一起跑 | 格 12 |
| OA-16 | 兩個通道都未設定 → 不拋、log 仍寫入；`scheduler.py` 註冊時記一行 ERROR `ops alert channel not configured`；通道檢查函式不回傳任何設定值 | 單元測試 | 格 13 |
| OA-17 | 推播在 rollback 之後才送出（spy：送出時主 DB 沒有開啟中的寫入交易）；`run_settlement_evaluation()`、`run_correction_job()` 內不 import `httpx`、`app.ops_alert`、`app.alerts.*` | spy；AST | 格 14 |
| OA-18 | E-1、E-2 發生時驗證快照與 plan 不寫（沿用 ADR-0027 FL-66 (g) 的 N-23 格與 FL-71 (i)，互相引用，不重複造格） | 引用 | 格 15 |
| OA-19 | listener：`EVENT_JOB_MAX_INSTANCES`（`scheduled_run_times`）、`EVENT_JOB_MISSED`（`scheduled_run_time`）各一格，推播帶被略過的觸發時刻 1 則；其他 job id 不推播、不寫 `ops alert:` 行；listener 不 import `app.alerts.*` | 以事件物件直接呼叫 | 格 17；FL-71 (g) |
| OA-20 | E-3c、E-3d 各一格；`step = orchestrator`（例外逃出編排函式）一格；每一步失敗只發一則、取最具體的事件（E-1／E-2 優先）；E-3d 不帶例外字串；前置條件不成立而略過的步驟不發告警；回傳失敗結果的步驟 → E-3d 一則、`exception_class` 為 None；前置條件不成立、沒有觸發、`inputs_not_ready` → 0 則；守衛成立後缺日稽核拋例外 → E-3d、不發 E-2 | 單元測試 | 格 18；FL-71 (f)(h) |
| OA-21 | 自測：結束碼規則（至少一個 `sent` 為 0）；輸出只含通道、狀態、`error_class`、`status`；`ops_alert.selftest` 只在 `selftest.py` 建構；scheduler 與 API 不 import `selftest`（import graph） | 單元測試；AST | 格 19；D-9 |
| OA-22 | log 行：以 `ops alert: event=` 起頭、單行 `key=value`、logger 名稱 `app.ops_alert`、WARNING；在 `configure_logging()` 之下輸出（caplog 於 `app.ops_alert` 取得）；推播標題為 `[stock-desk 維運告警] <event>` | 單元測試 | 格 21 |
| OA-23 | D-2 規則 4「適用對照」表逐列一格可建構；表外的 (事件, source, step, write_outcome) 組合與列舉外的值，model 建構時拒絕；D-3 第 10 點：建構失敗 → 記 `ops alert build failed`，後續步驟照常執行（缺日稽核照常寫入）；`exception_class` 不合格 → 代以 `invalid_exception_class` | 單元測試 | D-2、D-3 第 10 點 |

## 失效條件

出現下列任一情形，要重審本 ADR（開新 ADR 取代，不原地改寫）：

1. 新增跨執行狀態（冷卻、門檻、已恢復通知、去重的持久化）。
2. 新增關閉開關，或維運告警開始讀 `settings.alerts.*`。
3. 新增使用者面內容（推播開始帶免責句、代號、持倉或任何建議類字句）。
4. 新增通道，或維運告警不再與使用者警示共用同一組環境變數。
5. **推播的欄位集合、標籤或模板有任何變更**，送風控知悉級確認（推播和使用者警示共用同一個通道）。
6. 同步送出被改為佇列或執行緒（會新增狀態）。
7. 上限查證發現通道限制的計算方式與 D-4 的假設不同（例如以 bytes 計）。

## 風控 required 落點

| 風控 2026-10-18 required | 落點 |
|---|---|
| 1. D_v 閘門：至少一個通道設定完整並以 `ops_alert.selftest` 確認送達 | D-9、D-10 第 2 項 |
| 2. Consequences：沒有收到推播不代表排程正常；部署手冊 §5 也要寫 | Consequences 第一項；部署手冊待補項 3 |
| 3. D-4 引用 FL-71 (f) 禁用詞清單；推播文字只由 render 固定標籤加欄位值組成（正面白名單） | D-4；OA-12 |
| 4. 失效條件：推播欄位、標籤或模板變更送風控知悉 | 失效條件第 5 點 |
| 5. A-4：推播帶 E-1 全部欄位，只有清單依本點截斷 | D-4「截斷與欄位完整性」第一點；OA-13 |
| R-Q7-6（擋 D_v）：部署手冊 §5 寫明收到 E-2 立即停 scheduler | D-10 第 5 項；部署手冊待補項 2 |
| 知悉確認需補 1：E-2 `source = correction`（`write_outcome = deferred`）以 ADR-0027 N-23 第二批（待 CEO #42）為前提，第二批前不得實作，推播不得以 `deferred` 陳述實際已啟動的更正作業；CEO 不同意時送風控重審 | D-7「規則」（E-2 `source = correction` 的落檔前提，兩段）；OA-10 |
| 知悉確認需補 2：`render` 初版的標題、固定標籤常數與模板全文（含 `ops_alert.selftest` 固定自測欄位）送風控知悉級確認 | D-10 第 8 項 |

## 部署手冊 §5 待補項（D_v 前由 devops-sre 另做；本 ADR 不改手冊）

目標檔：`apps/stock-desk/docs/族群動能-主機部署手冊.md` §5「監控與告警」。

1. **搜尋字串與處理指引**：固定搜尋字串 `ops alert: event=`；逐事件（E-1、E-2、E-3b～E-3d）列「是什麼、先查什麼」。§5 現行「持續出現才算告警」的口徑**不得**套用在這些事件：第一次出現就要處理。
2. **收到 E-2 立即停 scheduler（R-Q7-6，擋 D_v）**：容器部署用 `docker compose stop scheduler`；主機部署的對應停止寫法，依手冊現行啟動寫法補，補稿時查證，不憑記憶。處理完 ADR-0026 D-9.4（確認備份 manifest 的最新市場 DB `run_id`，與 E-2 的 `reference_*` 對照；決定接受新基準或重建）才可以重啟。計畫性整檔還原本來就要先停 scheduler，還原與 `mark-restored`、X-3a 腳本完成後再啟動，所以不應出現預期內的 E-2；還原後仍出現 E-2 視為真實事件。
3. **「沒有收到推播，不代表排程正常」**：與 Consequences 同一句；並列出人工檢查法：每個交易日 23:30 後看 `forecast record run:` INFO 行是否存在，以及 `last_settle_eval_at`（`GET /api/forecast/status`，尚未實作）是否前進。
4. **E-2 停止出現不代表已處理**：說明守衛只在參考 run 身分相符時解除，處理終點是 ADR-0026 D-9.4 而不是推播消失。
5. **通道設定與自測**：只列三個環境變數的名稱（`ALERT_DISCORD_WEBHOOK_URL`、`ALERT_TELEGRAM_BOT_TOKEN`、`ALERT_TELEGRAM_CHAT_ID`）與設定位置，值由 CEO 自行設定；`python -m app.ops_alert.selftest` 的執行方式、結束碼與「CEO 在聊天室看到訊息」的確認步驟；通道變更後重跑。
6. **恢復判準**：D-8 的事實檢查三條；說明沒有「已恢復」推播。
7. **log 保存**：完整清單只在 scheduler log；容器 log 輪替與保存期間（`compose.yaml` 現無 logging 設定）、主機部署的 `logs\scheduler.log` 輪替。是否改 `compose.yaml` 屬設定變更，另送 qa-reviewer 審查。
8. 更正 §5 末段「沒有自動告警機制」的字樣：這兩類事件（E-1、E-2）與 `forecast_record` 被略過（E-3b）已有推播；排程器存活（dead-man's switch）仍沒有。
9. 推播文字不含處置指示（立即停 scheduler 等只在手冊），手冊要說明這點，避免操作者以為推播沒寫就不必做。

## 未查證與驗證紀錄

- **【未查證】Telegram、Discord 的單則字元上限與計數單位**：官方網址已列於 D-4；2026-10-18 兩個官方網域均被出口代理 403，無法讀取；經 GitHub 取 Discord 官方文件庫亦被拒。數值留給常數，待可連線或 CEO／其他角色提供官方出處後補（D-10 第 3 項）。
- 〔推論〕BMP 字元下 code point 與 UTF-16 code unit 計數相同；同步送出的阻塞可接受；容器 json-file 預設無大小上限；還原後 `run_id` 接續還原檔序號。
- 〔tech-architect 2026-10-18 已確認，修改見修訂紀錄〕D-2 的 `write_outcome` 列舉、`step` 名稱、`source` 適用對照；D-3 第 2 點 E-3b 的去重鍵時間成分；禁用詞清單以 ADR-0027 FL-71 (f) 下方的清單為測試的單一來源（dev-lead 2026-10-18 確認可行；讀取格式見 D-4「讀取的最小格式要求」）。
- 起草時讀過：TA 提案全文、風控審查全文、devops-sre 設計稿全文、ADR-0001、ADR-0026／0028 檔頭、ADR-0027 D-7.1 指向行（L773）、R-1 分支的 `logging_setup.py`、`notify.py` 現況、`.venv` 內 APScheduler 3.11.3 的 `events.py` 與 `schedulers/base.py`、`executors/base.py` 相關段。
- 沒做：沒有改任何程式、沒有改部署手冊、沒有讀 `.env`、沒有碰 `*.db`、沒有 commit／push；沒有跑任何測試。

## 修訂紀錄

（落檔後的修訂依 ADR-0001 慣例追記於此；通道上限查證結果亦記於此。）

### tech-architect 2026-10-18 審查與風控知悉確認後修訂

- 依據：`work/reviews/2026-10-18-ADR0029審查-tech-architect.md` 第二節「給 devops-sre 的照改清單」M-1～M-14；`work/reviews/2026-10-18-ADR0029與FL71及LM153知悉確認-風控.md` 第二節「需補 1」「需補 2」。
- 性質：本 ADR 仍為 proposed 且尚未落檔，以上述意見原地修訂；本節保留被取代的原文（逐字）。
- **合併規則（coordinator 定案，CEO 可推翻）**：
  - 風控需補 1 與 M-10 第一點內容重疊，兩段原字都寫入 D-7「規則」，風控那段逐字放在 M-10 第一點之後，不刪減任一方的字。
  - 兩段不一致之處：M-10 第一點原寫「CEO 不同意時……並送風控知悉」，風控需補 1 寫「CEO 不同意時，本列與其 `write_outcome` 送風控重審」。coordinator 依較嚴者定為送風控重審；tech-architect 2026-10-19 複審同意，並把 M-10 第一點句末改為「並送風控重審（同下一點）」，兩段不再不一致。M-10 第一點的舊字見下方 M-10。
  - 風控需補 2 加為 D-10 第 8 項。M-1～M-14 都沒有增加 D-10 的項目，所以 D-10 原有 7 項，第 8 項直接接續，沒有順延編號。

**M-1｜D-2 `execution_started_at` 列。**

> 舊字（該格後半，格內其餘不變）：該次執行的所有告警共用同一個值。E-3b 為 None（沒有執行可言）

**M-2｜D-2 `occurred_at` 列。**

> 舊字（整格）：UTC ISO8601。取自編排函式持有的 store 時鐘；`app/ops_alert/**` 不呼叫 `datetime.now`／`time.time`（AST）

**M-3｜D-2 `source`、`step`、`write_outcome` 三列與規則 4（改為「適用對照」表）。**

> 舊字（`source` 列內容）：E-1：`settlement`／`correction`。E-2：`settlement`／`audit`／`correction`。E-3c：`settlement`。E-3b、E-3d：None（E-3d 以 `step` 識別）。selftest：None
>
> 舊字（`step` 列內容）：編排函式的步驟：`record`、`settlement`、`gap_audit`、`late_scan_correction`、`validation_snapshot`、`plan`、`orchestrator`。E-1／E-2 的 `step` 是其 `source` 所在的步驟。E-3b、selftest 為 None
>
> 舊字（`write_outcome` 列內容）：封閉列舉：`not_written`（該步交易已 rollback，沒有留下列）、`not_started`（該步沒有啟動）、`deferred`（觸發延後，未前進）、`written_without_registration`（寫入了判定結果，但未做永久登記）、`unspecified`（`step = orchestrator`，無法斷言）
>
> 舊字（規則 4 整點）：4. `write_outcome` 的列舉、`step` 的名稱與 `source` 的適用對照，為 devops-sre 依 ADR-0027 D-7 第 2 點的六步與 TA 裁定草擬，**【待 tech-architect 確認】**；確認前不得進入實作。E-1 的 `not_written` 與 E-2（`source = settlement`）的 `not_written` 沿用設計稿原定。

**M-4｜D-3 第 2 點的 E-3b 子點（改為兩點：None 不去重；鍵集合加鎖）。**

> 舊字：E-3b 沒有 `execution_started_at`，改以被略過的觸發時刻（`skipped_run_times`）作為該鍵的時間成分。〔devops-sre 的補充，**【待 tech-architect 確認】**〕

**M-5｜D-3 新增第 10 點（建構失敗不中止流程）；D-2 規則 1 的類別名稱 regex。**

> 舊字（D-2 規則 1）：並以 `^[A-Za-z_][A-Za-z0-9_.]*$` 驗證。
>
> D-3 第 10 點為新增，無舊字。

**M-6｜D-9 的 `deliver()` 句。**

> 舊字：（實作可讓 sink 另提供回傳逐通道結果的 `deliver()`，`emit()` 在其上加去重與吞例外；細節由 dev-lead 定）

**M-7｜D-1 方向限制最後一點；OA-3 驗證欄。**

> 舊字（D-1 最後一點）：送出器實作只在 `scheduler.py` 組裝處被建立；`app/` 內 `OpsAlertSink` 的實作恰好一個。測試用的 fake 放在 `tests/`，不放 `app/`。
>
> 舊字（OA-3 驗證方式欄）：AST／grep
>
> 新字：OA-3 驗證方式欄接「；實作的判定方式依 D-1 最後一點」。

**M-8｜長度常數的位置（D-1 四列、D-4、OA-13）。**

> 舊字（D-1 model 列）：、推播長度常數 |
>
> D-1 push_channels 列、sink 列、render 列為內容末尾新增，無舊字（新增字：push_channels 列「；兩個通道的單則上限常數，以及其出處網址與查證日的字串常數」；sink 列「；`OPS_ALERT_PUSH_MAX_CHARS`（由 push_channels 的兩個上限與安全餘量常數計算）」；render 列「；推播上限以參數接收」）。
>
> 舊字（D-4 該點）：查證後，兩個通道的數值與出處（網址與查證日）寫入 `push_channels`（或 model）的常數註解，並補進本 ADR 的修訂紀錄。`OPS_ALERT_PUSH_MAX_CHARS` 由這兩個常數**計算得出**，不另外手打數字。
>
> 舊字（OA-13 片段）：兩個通道上限帶官方出處與查證日（缺則測試失敗）

**M-9｜D-4 的單一來源（以 ADR-0027 FL-71 (f) 區塊為測試來源；dev-lead 2026-10-18 確認可行）。**

> 舊字（D-4 子點）：該位置是否即為測試讀取的「單一來源」，仍**【待 tech-architect 與 dev-lead 確認】**：後端現讀 `apps/stock-desk/shared/forbidden-terms.json`，但目前只有 `guarantee`、`price_target` 兩類（風控審查原文：其餘各類放在哪個單一來源，由 TA 和 dev-lead 決定）。確認前，OA-12 的「讀自單一來源」以 ADR-0027 FL-71 (f) 為準。
>
> 舊字（OA-12 片段）：掃描清單讀自單一來源，測試內不手抄

> 追加（dev-lead 2026-10-18 可行性確認；tech-architect 2026-10-19 複審確認）：來源 `work/reviews/2026-10-18-禁用詞以ADR區塊為測試來源可行性-dev-lead.md`「最小格式要求」。第 1～5 條寫成 D-4「讀取的最小格式要求」第 1～5 條，另加第 7 條（完整檔名常數，依同回報第 3 節）；第 6 條屬比對語意，寫入 ADR-0027 FL-71 (f)「比對規則」，本 ADR 第 6 條只指向該處。風控對該補字的知悉，以及 stock-desk.yml 的 paths 觸發（devops-sre 後續），不在本 ADR 範圍。

> 被取代的中間稿（devops-sre 2026-10-18 所寫，tech-architect 2026-10-19 複審改寫）。以下四行逐字錄存（行首縮排省略）：前三行是 devops-sre 原稿（標題行與第 1、2 條；第 2 條原文亦見檔尾「風控 2026-10-19 知悉確認後補字」段的「被取代的原文」），第四行是 coordinator 依風控 2026-10-19 需補 B-2 改寫後的第 2 條。
>
> 舊字（devops-sre 原稿，標題行）：- **讀取的最小格式要求**（dev-lead 2026-10-18 可行性確認；待 tech-architect 確認）：
>
> 舊字（devops-sre 原稿，第 1 條）：1. （dev-lead 第 1 條）錨點是「行首（縮排後）`- ` 緊接 `**推播禁用詞清單**`／`**白名單例外**`」的清單項，在 ADR-0027 全檔各恰好一個，起錨點在前；測試以此行首樣式比對，不以子字串比對。其他地方引用錨點字串（例如 FL-71 (f) 標頭內的反引號引用），不算錨點。
>
> 舊字（devops-sre 原稿，第 2 條）：2. （dev-lead 第 6 條）「比對規則」補兩點：`\b` 以 ASCII 字元判定詞界（英文比對用 `re.I|re.A`，使「建議buy今天」之類中英相接的文字也會被抓到）；「英文不分大小寫」適用全部英文項，含 F 類。
>
> 舊字（coordinator 依風控需補 B-2 改寫後的第 2 條）：2. （dev-lead 第 6 條）`\b` 以 ASCII 字元判定詞界、「英文不分大小寫」適用全部英文項（含 F 類），寫在 ADR-0027 FL-71 (f)「比對規則」；本 ADR 不另寫比對規則，測試依該處實作。
>
> 舊字（本段上方「追加」一段，tech-architect 2026-10-19 複審改寫）：追加（dev-lead 2026-10-18 可行性確認；待 tech-architect 確認）：來源 `work/reviews/2026-10-18-禁用詞以ADR區塊為測試來源可行性-dev-lead.md`「最小格式要求」第 1 條（行首錨點）與第 6 條（`\b` 以 ASCII 詞界判定、「英文不分大小寫」含 F 類），照意寫成 D-4「單一來源」一點末尾的兩個子條。為新增，無舊字。該回報的其餘各條（第 2～5 條）、風控對「比對規則」明文化的確認，以及 stock-desk.yml 的 paths 觸發（devops-sre 後續）不在本次範圍。

**M-10｜D-7 規則新增三點並更正一處引用；檔頭「與既有 ADR 的關係」第 11 行。**

> 舊字（D-7 規則，引用）：E-2 的 `reference_*` 讓操作者對照 ADR-0026 D-9.2 第 2 點備份 manifest 的最新市場 DB `run_id`。
>
> 舊字（檔頭第 11 行末）：本 ADR 的 E-1、E-2 欄位對應 ADR-0027 D-9.3 B-3「型別與欄位」與 D-9.2「R 倒退」的例外屬性；兩邊的屬性名稱必須逐字一致。
>
> 說明：檔頭第 11 行原以句號結尾；M-10 要求在末尾接「；E-2 的 `audit`／`correction` 另對應 D-7 第 2 點 Q7 守衛的回傳值 `MarketRunRegression`」，為使標點連貫，原結尾句號移到新增子句之後。引用更正後讀作「ADR-0026 D-9 第 2 點（備份組）的 manifest 的最新市場 DB `run_id`」，兩個「的」連用是 TA 逐字句與原句尾相接的結果；tech-architect 2026-10-19 複審改為「ADR-0026 D-9 第 2 點（備份組）manifest 中的最新市場 DB `run_id`」。
>
> 舊字（M-10 第一點句末，tech-architect 2026-10-19 複審改）：已 accepted 時開新 ADR；並送風控知悉。
>
> D-7 規則的三個新增點為新增，無舊字。其中第一點之後接風控需補 1 的原字（見下）。

**M-11｜E-1 改名。** 全檔 `forecast.settle.unregistered_unobserved_weekday` 改 `forecast.unregistered_unobserved_weekday`（理由同 E-2：`source` 含 `correction`）。

> 舊字：`forecast.settle.unregistered_unobserved_weekday`（D-7 事件目錄 E-1 列，本檔唯一一處）

**M-12｜E-3d 涵蓋「失敗結果」。**

> 舊字（D-7 E-3d 觸發格片段）：任一步拋出 E-1／E-2 以外的 `Exception`；或例外逃出編排函式本身
>
> 舊字（D-7 E-3d payload 片段）：`exception_class`（只放類別名，不帶例外字串）。

**M-13｜OA 修正。**

> 舊字（OA-1 開頭，TA 建議項、不擋，已採用）：`app/forecast/**` 只可 import `app.ops_alert.model`；
>
> 舊字（OA-6 片段）：E-1、E-2 的欄位只取自 ADR-0027 的例外屬性，不解析例外字串；
>
> OA-11、OA-20 為句末新增，無舊字（OA-11 新增：「；E-3b 與 `step = orchestrator` 不去重：……」；OA-20 新增：「；回傳失敗結果的步驟 → E-3d 一則……」）。
>
> 舊字（OA-12 見 M-9；OA-13 見 M-8）。
>
> 舊字（OA-23 整列）：| OA-23 | `write_outcome`、`step`、`source` 的適用對照與列舉與 D-2 一致；model 建構時拒絕不合法值 | 單元測試 | D-2；**【待 TA 確認後才可實作】** |

**M-14｜收尾。**

> 舊字（D-2 規則 4 原句）：確認前不得進入實作。 → 該句隨 M-3 的規則 4 整點一併移除（新規則 4 已標「tech-architect 2026-10-18 確認」）。
>
> 舊字（「未查證與驗證紀錄」）：〔待 tech-architect 確認〕 → 〔tech-architect 2026-10-18 已確認，修改見修訂紀錄〕。該行最後一項（禁用詞清單的單一來源）TA 已裁定，dev-lead 2026-10-18 已確認可行（見 M-9）；該項括號於 tech-architect 2026-10-19 複審改寫，舊字：（與 dev-lead）。
>
> 舊字（D-3 第 7 點片段）：編排函式在該步交易 rollback 之後、下一步開始之前呼叫
>
> 舊字（Consequences 片段）：每次執行不超過 7 則。若 CEO
>
> 說明：「句末接」放在該句的句號之前（「……不超過 7 則；E-3b 另計，每個被略過的觸發事件一則。」），以保持單句。
>
> 設計稿 §2.3、§2.7、§5 同步 M-3、M-4、M-11、M-12，舊字錄入設計稿檔尾修訂紀錄。

**風控需補 1｜D-7「規則」加一點（E-2 `source = correction` 的前提）。** 與 M-10 第一點重疊，兩段原字都已寫入 D-7「規則」，風控那段緊接在 M-10 第一點之後；不一致處依較嚴者：送風控重審（見本節開頭「合併規則」）。無被取代的舊字。「風控 required 落點」表已補一列。

**風控需補 2｜D-10 加第 8 項。** 原字加為 D-10 第 8 項；D-10 原有 7 項、M-1～M-14 未增加項目，故沒有順延編號。無被取代的舊字。「風控 required 落點」表已補一列。

**待辦與殘餘（本節不改字）**

- M-9 的可行性已由 dev-lead 2026-10-18 確認。`.github/workflows/stock-desk.yml` 的 paths 尚未涵蓋 ADR-0027，只改清單的 commit 不會觸發後端測試；由 devops-sre 隨測試實作補上。
- E-2 `source = correction` 一列在 ADR-0027 第二批（CEO #42）落檔前不得實作；CEO 不同意時依 D-7 規則兩段處理，並送風控重審。
- 部署手冊 §5 待補項、通道上限查證仍為 D_v 前待辦，與本次修訂無關。


---

**風控 2026-10-19 知悉確認後補字（需補 A、B-2；`work/reviews/2026-10-19-ADR0029修訂版知悉確認-風控.md`；coordinator 套用）**
- 需補 A：D-7「規則」中，風控需補 1 那一點之後新增一點（「上兩點對『CEO 不同意時』的處理寫法不同……依較嚴者：送風控重審」）。新增，無舊字。方向：不變（釐清）。CEO：否。因 tech-architect R-4 已使兩段一致，本點改寫；原寫『上兩點對「CEO 不同意時」的處理寫法不同（「並送風控知悉」與「送風控重審」），依較嚴者：送風控重審；「送風控知悉」不得讀成可以不經風控重審（修訂紀錄「合併規則」）。』改寫後的這一點要送風控知悉（由 coordinator 處理）。
- 需補 B-2：D-4「讀取的最小格式要求」第 2 條整條改寫，比對語意移到 ADR-0027 FL-71 (f)「比對規則」唯一一處（單一來源）。方向：不變（位置）。CEO：否。已由 tech-architect R-1 第 6 條承接（該條與第 1～5、7 條整段取代 D-4「讀取的最小格式要求」，中間稿見 M-9）。被取代的原文——
  > 2. （dev-lead 第 6 條）「比對規則」補兩點：`\b` 以 ASCII 字元判定詞界（英文比對用 `re.I|re.A`，使「建議buy今天」之類中英相接的文字也會被抓到）；「英文不分大小寫」適用全部英文項，含 F 類。
- 上方修訂紀錄中 dev-lead「追加」一點所述「照意寫成……兩個子條」，其中第 6 條一子條已依本點改為指向 ADR-0027，原文不改。
---

**tech-architect 2026-10-19 複審後修訂（R-1、R-3～R-6、S-2、S-3；`work/reviews/2026-10-19-ADR0029複審-tech-architect.md`；devops-sre 套用）**

協調規則（coordinator 定案，CEO 可推翻）：R-1 整段取代 D-4「讀取的最小格式要求」（含 coordinator 依風控 B-2 改寫的第 2 條）；R-4 使 D-7 兩段一致，風控需補 A 新增的那一點改為「上兩點對『CEO 不同意時』的處理一致為送風控重審……」。R-2、S-1 屬 ADR-0027（tech-writer），不在本 ADR。S-4 屬設計稿，不動（設計稿第三版已列為未同步，以 ADR 為準）。

- **R-1｜D-4「讀取的最小格式要求」整段取代。** 新字為第 1～7 條（第 1～5 條依 dev-lead 同名條，第 6 條指向 ADR-0027 FL-71 (f)「比對規則」，第 7 條為完整檔名常數）。被取代的中間稿錄存於上方 M-9 之下。
- **R-3｜D-7 規則的 ADR-0026 引用。**
  > 舊字：讓操作者對照 ADR-0026 D-9 第 2 點（備份組）的 manifest 的最新市場 DB
- **R-4｜D-7 規則，M-10 第一點句末。**
  > 舊字：已 accepted 時開新 ADR；並送風控知悉。
  >
  > 連帶（協調規則 2）：D-7 規則中風控需補 A 新增的那一點，整點換為「上兩點對「CEO 不同意時」的處理一致為送風控重審；「送風控知悉」等較寬讀法不適用（修訂紀錄「合併規則」）。」舊字：上兩點對「CEO 不同意時」的處理寫法不同（「並送風控知悉」與「送風控重審」），依較嚴者：送風控重審；「送風控知悉」不得讀成可以不經風控重審（修訂紀錄「合併規則」）。
- **R-5｜「未查證與驗證紀錄」。**
  > 舊字：禁用詞清單是否以 ADR-0027 FL-71 (f) 下方的清單為測試的單一來源（與 dev-lead）。
- **R-6｜修訂紀錄同步。**
  > 舊字（合併規則第二點）：兩段不一致之處：M-10 第一點寫「CEO 不同意時……並送風控知悉」，風控需補 1 寫「CEO 不同意時，本列與其 `write_outcome` 送風控重審」。**依較嚴者：送風控重審。** 兩段原字都保留；實作與流程以「送風控重審」為準，M-10 的「送風控知悉」不得被讀成可以不經風控重審。
  >
  > 舊字（M-9 標題片段）：可行性 dev-lead 確認中，若判定不可行會另行退回
  >
  > 舊字（M-9「追加」一段、讀取格式中間稿）：見 M-9 之下「被取代的中間稿」。
  >
  > 舊字（M-10「說明」段片段）：兩個「的」連用是 TA 逐字句與原句尾「的最新市場 DB」相接的結果，字面照 TA 未動。
  >
  > 舊字（M-14 片段）：dev-lead 的可行性確認仍在進行（見 M-9）。
  >
  > 舊字（「待辦與殘餘」第一點）：M-9 的可行性（以 ADR-0027 FL-71 (f) 區塊為測試來源）由 dev-lead 確認中；判定不可行會退回 tech-architect。
- **S-2｜Consequences 壞處新增一點**（禁用詞清單以 ADR-0027 文字為測試來源的代價：paths 未涵蓋 ADR-0027 前，只改清單的 commit 不觸發後端測試）。新增，無舊字。
- **S-3｜修訂紀錄開頭。**
  > 舊字：（尚無。落檔後的修訂依 ADR-0001 慣例追記於此；通道上限查證結果亦記於此。）→ 拿掉「尚無。」。
- 方向：R-1、R-3、R-5、R-6、S-3 為字句與位置調整，不變；R-4 使 D-7 兩點一致（收緊至風控重審，與先前依較嚴者的裁定相同）；S-2 為揭露。CEO：否。風控：R-4 與改寫後的風控需補 A 那一點送風控知悉（coordinator 處理）。

---

**風控 2026-10-19 N-20 批裁定後修訂（N20-9 與風控 suggested；`work/reviews/2026-10-19-N20批裁定-風控.md`、`work/reviews/2026-10-19-N38核對與checkpoint乙案改寫及N20改寫-tech-architect.md`；devops-sre 套用）**

依據：tech-architect 2026-10-19 回報第二節 4-B 的 N20-9；風控 2026-10-19 N-20 批裁定（N20-9 知悉確認，失效條件 5；R-12；ADR-0029 其餘 suggested 三點，coordinator 定案一併採用）。本 ADR 狀態為 proposed，依 ADR-0001 原地修訂。

- 方向：收緊。CEO：否。風控：N20-9 屬知悉級，已確認；三個 render 新標籤待風控逐字確認（R-12），確認前不得實作。
- 與 ADR-0027 N-20 批（含風控 R-1、R-2）同批落檔。Consequences 的換句「只有參考 run 的身分相符才解除」，以 R-1、R-2 都已套用為前提；沒有套用時該句不屬實（風控）。
- 逐項（被取代的舊字取自修訂前已 commit 的檔案現況，逐字；下列引文含定位字串，屬歷史列，不是現行條文）：
  1. **D-7 事件目錄 E-2 的 payload 欄位。** 加 `regression_kind`、`reference_recorded_at`、`current_recorded_at`；`reference_kind` 加 `gap_audit`；`reference_id` 加 `audit_id`；`reference_started_at` 加 `audit_now`（N20-9）。`current_recorded_at` 的「不存在時為 None」依 ADR-0027 N20-1。舊字——
     > `reference_kind ∈ {settle_eval, correction_job}`、`reference_value`、`reference_id`（`settle_eval_id` 或 `correction_job_id`）、`reference_started_at`（UTC ISO8601）。
  2. **D-7 規則，ADR-0026 引用。** 「ADR-0026 D-9 第 2 點（備份組）」改指「第 2-1 點（備份順序與 manifest 檢查）」（風控 suggested）。舊字——
     > - E-2 的 `reference_*` 讓操作者對照 ADR-0026 D-9 第 2 點（備份組）manifest 中的最新市場 DB `run_id`。
  3. **D-7 規則，屬性清單（原 L219）同步。** 舊字——
     > - E-2 `source = audit`／`correction` 的欄位，取自 `market_run_regression()` 回傳的 `MarketRunRegression`，屬性 `market_run_current`、`reference_kind`、`reference_value`、`reference_id`、`reference_started_at`，與 `MarketRunRegressedError` 的同名屬性逐字一致；`source` 由呼叫端決定。
  4. **D-7 規則，原 L220 換成已完成的敘述。** 舊字——
     > - 後續追蹤清單 N-20 若在 ADR-0027 增列 E-2 的屬性（tech-architect 2026-10-18 補充項回覆第 3 項：`regression_kind`、`reference_recorded_at`、`current_recorded_at`），屬於失效條件 5，與 N-20 同批送風控。
  5. **D-7 規則新增兩點：render 三個新標籤的草稿（標「待風控逐字確認（R-12）」），以及 render 在兩個 `recorded_at` 相等但 `kind` 或 `session_date` 不同時的處理（風控 suggested，待辦）。** 新增，無舊字。標籤草稿不是定稿。
  6. **Consequences「E-2 停止出現，不代表已處理」。** 換句（N20-9），並於該點末尾接殘餘句（風控 suggested）：「還原點不早於任何參考 run 時，守衛偵測不到，E-2 不會出現（ADR-0027 D-7 第 2 點殘餘）。」換句的舊字——
     > 新寫入的 run 使 R 再度不小於參考值時，判定就不再成立，結算評估恢復執行；
     殘餘句為新增，無舊字。
  7. **部署手冊 §5 待補項第 4 點。** 舊字——
     > 4. **E-2 停止出現不代表已處理**：說明守衛會自己解除，處理終點是 ADR-0026 D-9.4 而不是推播消失。
  8. **OA-10。** 加身分不符一格，並把逐欄斷言的屬性清單同步為 E-2 的八個屬性。舊字——
     > E-2：`settlement`、`audit`、`correction` 各一格；`reference_kind`／`reference_value`／`reference_id`／`reference_started_at` 與 `write_outcome` 逐欄斷言；參考值取自更正作業的一格；
- 待辦與殘餘（本節不改字）：
  - render 的三個新標籤：草稿見 D-7 規則，待風控逐字確認（R-12）。確認前 E-2 的 `regression_kind`、`reference_recorded_at`、`current_recorded_at` 不得進入 render 實作；OA-12 的標籤常數掃描要連同這三個一起跑。
  - render 在 `recorded_at` 相等但 `kind` 或 `session_date` 不同時的處理：見 D-7 規則，待 tech-architect 與風控決定。
  - OA-10 沒有另加 `reference_kind = gap_audit` 的獨立格（`reference_id` 為 `audit_id`、`reference_started_at` 為 `audit_now`）；N20-9 只要求加身分不符一格，gap_audit 對應的來源格在 ADR-0027 FL-67 (n)。是否要在本 ADR 補一格，請 tech-architect 決定。

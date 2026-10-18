# R-1 推播 token 外洩影響評估（security-engineer，唯讀）

- 日期：2026-10-18　分支／HEAD：`product/stock-desk` @ `e21a615`
- 依據：`work/stock-desk-N23結算例外告警設計-2026-10-18.md` §3 R-1；`work/reviews/2026-10-18-N23結算例外告警設計-devops-sre.md`
- 範圍：`apps/stock-desk/backend/app`、`apps/stock-desk/scripts`、`compose.yaml`、主機部署手冊、repo 與 git 歷史（僅 pattern 掃描，只看檔名／計數）
- 未做：未讀任何 `.env`（含 `.env.example`，工具亦拒絕）、未碰 `backend/data/*.db`、未用真實憑證、未連外。

---

## 一、本次結論

**第一節重點（祕密處置狀態）**

1. **repo 與 git 歷史（53 個 ref）未發現真實祕密。** 以 Telegram bot token 與 Discord webhook 的格式 regex 對 tracked 工作樹、所有 ref 的樹與 `git log --all -G` 全歷史掃描，命中 0；`work/` 內只有 `FAKETOKEN123` 之類假值。`.env` 已被 `.gitignore:2` 忽略、未被追蹤；`logs/*.log` 被 `.gitignore:34` 忽略。
2. **部署環境的 log 很可能已含真實祕密（無法驗證，需 CEO 在主機檢查）。** 我看不到主機，但程式行為已確定會寫入（見下 F-1、F-2）。這部分的處置請見「四」的檢查位置與輪換判準。報告內不含任何祕密原文，僅用假 token 實測。

**缺陷成立，而且比 R-1 原描述更廣（兩點修正）**

| 項 | R-1 原描述 | 實測結論 |
|---|---|---|
| 觸發條件 | 只有 4xx／5xx（`HTTPStatusError`） | 對。非狀態碼例外（`ConnectError`、`ReadTimeout`、`UnsupportedProtocol`、`InvalidURL`）的字串**不含** URL，不洩漏 |
| 另有一條更大的洩漏面 | 未提 | **httpx 自己的 INFO log 在成功路徑就寫完整 URL**（`httpx/_client.py:1026,1741`：`HTTP Request: POST https://api.telegram.org/bot<token>/sendMessage "HTTP/1.1 200 OK"`）。scheduler 行程 `scheduler.py:782` 是 `logging.basicConfig(level=logging.INFO)`，沒有壓 httpx，所以**每一次成功推播、每一次 FinMind／Alpha Vantage 呼叫都會把祕密寫進 scheduler log**。只修 `notify.py:75-78` 不會關掉這個洩漏 |

- `DeliveryResult.detail` **不入 DB、不經 API、不顯示在前端、不進匯出**（見二之 2）。洩漏面只有 log。
- 洩漏範圍包含：Telegram bot token、Discord webhook URL（本身是祕密）、**FinMind token（`token=` query）、Alpha Vantage API key（`apikey=` query）**。

**Verdict：NEEDS_CHANGES，BLOCKING_ISSUES=true。** N-23 維運告警上線（與「第一次就告警」的 D_v 前驗收清單第 3 項）以前必須完成「四」的修補 1～4；已部署環境依「四」做 log 清查與輪換判準。

---

## 二、各部門回報（security-engineer）

### 掃描摘要

- 環境：Python 3.12.3、httpx 0.28.1（與 `uv.lock` 一致）、backend `.venv`；探針腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/r1_probe.py`（假 token `123456:FAKE-TOKEN-ABC`、假 webhook token；MockTransport 加 127.0.0.1 迴路 socket；以 `python -I` 執行）。
- 靜態搜尋：Grep `str(exc)`、`{exc}`、`%s", exc`、`repr(`、`exc_info`、`logger.exception`、`raise_for_status`、`HTTPStatusError`、`request.url`／`response.url`、`token=`／`apikey`、`basicConfig`／`setLevel`。
- 歷史掃描：Telegram `[0-9]{8,10}:[A-Za-z0-9_-]{35}`、Discord `discord(app)?\.com/api/webhooks/[0-9]{15,}/[A-Za-z0-9_-]{30,}`，對 tracked 樹、53 個 ref、`git log --all -G`。命中 0。限制：只能找「格式像」的值，格式不同的 key（FinMind、Alpha Vantage）靠 pattern 找不到，這兩者另以「是否出現在檔案」人工搜尋（僅見假值 `fixture-test-token-not-real`）。

### 1. 缺陷確認（實測，假憑證）

| 案例 | status | detail 含祕密 | log 含祕密 |
|---|---|---|---|
| Telegram 404／429／500／301（`HTTPStatusError`） | failed | **是** | **是** |
| Discord 404／429／500／301 | failed | **是** | **是** |
| `ConnectError`／`ReadTimeout`／`ConnectTimeout`／`RemoteProtocolError`（MockTransport 拋出） | failed | 否 | 否 |
| 真實 transport 對迴路拒絕連線 | failed | 否（`[Errno 111] Connection refused`） | 否 |
| 真實 transport 讀取逾時 | failed | 否（`timed out`） | 否 |
| webhook 無 scheme／錯 scheme／壞 port／非法字元 | failed | 否（只有通用訊息，如 `Invalid port: 'abc'`） | 否 |

- 洩漏字串樣式：`Client error '404 Not Found' for url 'https://api.telegram.org/bot<TOKEN>/sendMessage'` 加 `For more information check: https://developer.mozilla.org/...`；Discord 為 `.../api/webhooks/<id>/<TOKEN>`。來源 `httpx/_models.py:810,816`。3xx 也會洩漏（httpx 預設不跟隨轉址，`raise_for_status` 對 3xx 同樣拋）。
- 注意：非狀態碼例外目前不洩漏，是「httpx 與 httpcore 的訊息內容」決定的，不是程式保證的；例外類別的訊息文字隨函式庫版本改變，所以修補不得依賴「這類例外訊息是安全的」，要用只取類別名的作法。
- httpx INFO 行（成功路徑，root=INFO 模擬 `basicConfig`）實測輸出（已用假值）：`HTTP Request: POST https://api.telegram.org/bot123456:FAKE-TOKEN-ABC/sendMessage "HTTP/1.1 200 OK"`、`GET https://api.finmindtrade.com/api/v4/data?dataset=d&token=FAKEFINMIND`、`GET https://www.alphavantage.co/query?function=f&apikey=FAKEAVKEY`。
- 未做：未跑完整 scheduler 行程端到端（只模擬同樣的 root INFO 設定）；DNS 解析失敗的真實字串未測。探針中有一個畸形主機名案例（含空白）回報 `timed out`，不能排除它觸發了一次 DNS 查詢（沒有建立連線的證據；沙箱無外連憑證）。

### 2. `DeliveryResult.detail` 的去向

| 問題 | 結論 | 證據 |
|---|---|---|
| 產生處 | `notify.py:72`（skipped 固定字串）、`:78`（failed，`str(exc)`） | `backend/app/alerts/notify.py` |
| 傳遞 | `notify()`／`notify_all()` 回傳 list | `notify.py:82-113,116-131` |
| 唯一的生產端呼叫者 | `scheduler.py:421-422`，只讀 `delivery.channel`、`delivery.status` 寫 INFO log，**`detail` 被丟棄** | `backend/app/scheduler.py:420-422` |
| 寫入 DB | 否。事件在呼叫前已存，`DeliveryResult` 無任何 store 呼叫 | 全 repo `DeliveryResult`／`notify_all` 只有 `notify.py`、`scheduler.py`、測試 |
| 經 API 回傳／前端顯示／匯出 | 否。無 API 路由引用 notify；前端只有 `notify_webhooks` 開關（`frontend/app/lib/types.ts:1279`、`settings/SettingsForm.tsx:264,320`），無 detail 欄位 | Grep 結果 |
| 測試 | 僅 `tests/test_alerts_notify.py:102` 斷言 `results[0].detail` 為真值（修補後需保持非空） | |

→ 目前 detail 本身不是洩漏出口；風險在於「欄位已預備接上」——N-23 設計若把它轉進推播或 DB 就會變成洩漏，所以也要一併修。

### 3. 其他同類洩漏面（全 repo）

發現事項（依 severity）：

- **[high] F-1 httpx INFO 日誌寫完整 URL（成功路徑）**。位置：`scheduler.py:782`（`basicConfig(level=INFO)`，沒有 httpx／httpcore 限制）＋ `httpx/_client.py:1026,1741`。受影響呼叫：Telegram（`notify.py:36,64`）、Discord webhook（`notify.py:64`）、FinMind `token=`（`data/providers/finmind.py:109-117`、`services/pit_snapshot.py:311-319`）、Alpha Vantage `apikey=`（`data/providers/alpha_vantage.py:287-294`）。條件：該環境變數有設、對應呼叫有發生（`notify_webhooks` 預設 `True`，`settings/models.py:109`）。修補見四之 2。
- **[high] F-2 `notify.py:77-78` `str(exc)` 入 log 與 `detail`**（R-1 本身）。失敗路徑；僅 `HTTPStatusError`（含 3xx）洩漏。修補見四之 1。
- **[medium] F-3 API 行程目前不受 F-1 影響，但 O-1 任務單的修法若做錯會新增洩漏面。** `app/main.py` 無 logging 設定（Grep 無 `basicConfig`／`dictConfig`），root 預設 WARNING，httpx INFO 被丟棄。O-1 任務單（`work/dispatch/2026-10-07-任務單-O-1-API行程logging設定.md`）已寫「httpx 保持 WARNING」，並要 security 知會；但該單聲稱 scheduler「不受影響」只對「格式」成立，對 httpx INFO 不成立（F-1）。建議把 O-1 的 `configure_logging()` 同時用在 scheduler（見四之 2）。
- **[low] F-4 第三方回應文字原樣入 log／reason**。`alpha_vantage.py:171-176` 把 `Error Message`／`Note`／`Information` 內容放進 `reason`（`:312` 也寫 WARNING）；`pit_snapshot.py:330` 把 FinMind 回應 `payload!r` 放進錯誤並存 `upsert_backfill_progress(last_error=...)`（`:401`）。這些是供應商的文字，依其公開訊息格式不會回顯我方 key，但**我無法驗證**。建議截斷長度，且不得為了除錯回顯 request URL／params。
- **[low] F-5 `compose.yaml` 把同一份 `./.env` 給 backend、scheduler、frontend 三個容器**（`compose.yaml:9-11,32-34,55-57`）。只有 scheduler 需要 `ALERT_*`；最小權限原則下，backend 與 frontend 不需要。屬縱深防禦，不是洩漏；改法需 devops-sre／tech-architect 評估（compose 的 `environment:` 逐項傳遞），不屬 R-1 修補。
- 已檢查、**無洩漏**（附理由）：
  - `data/http.py:235-241`、`:246-252` 記的是 `url` 參數（相對路徑，不含 params 與 base）與傳輸例外；實測傳輸例外不含 URL。
  - 各 provider 的 `except httpx.TransportError`（`finmind.py:119`、`alpha_vantage.py:296`、`twse.py:123`、`tpex.py:259`、`yfinance.py:292`、`fx.py:206`、`twse_snapshot.py:365,436`、`dividends/providers.py:356`、`directory/providers.py:206,294,404`、`pit_snapshot.py:321`）只處理 `TransportError`，且全 repo `raise_for_status` 只出現在 `notify.py:65`，所以 `HTTPStatusError` 不會從這些路徑冒出來。
  - `logger.exception`／`exc_info=True`（`data/service.py:915`、`fx.py:406`、`engine.py:488`、`scheduler.py:452,503,611,754`、`sector_board.py`、`kelly.py:1334` 等）：traceback 只含例外訊息與程式碼行，不含區域變數；因 `raise_for_status` 只在 notify，沒有 URL 訊息可帶入。**但若修補後的 notify 仍用 `exc_info=True` 或 `logger.exception`，traceback 末行就是含 URL 的 `HTTPStatusError` 字串，不得使用。**
  - `scripts/verify_*.py`：`verify_market_data.py:191`、`verify_sector_data.py:127,379` 的 `{exc}` 僅限 `TransportError`（無 URL）。`verify_intraday_quotes.py:704` 已有 `Redactor.scrub_text`（`:184-211`），可參考作法。
  - 測試與 fixture 的 token 皆為假值（`fixture-test-token-not-real`、`token-123`）。

### 機制建議

1. 在 scheduler 與 API 兩個行程統一呼叫 `configure_logging()`：`httpx`、`httpcore` logger 設 WARNING（O-1 已有此設計，擴及 scheduler）。
2. 加一個 `logging.Filter` 掛在 handler 上，遮蔽 `api.telegram.org/bot<…>`、`/api/webhooks/<id>/<…>`、`(token|apikey|api_key)=<…>`（縱深防禦，防未來新增呼叫又漏）。
3. pre-commit／CI：gitleaks（含自訂規則 Telegram／Discord webhook）；devops-sre 落地。
4. 新增一條 CI 測試：以 `caplog` 全級別跑一輪 notify／FinMind／Alpha Vantage 成功與失敗路徑，斷言假 token 不在任何 record（含 httpx logger）。

---

## 三、驗證

- 實測可重現：`cd /tmp && /home/user/AICompany/apps/stock-desk/backend/.venv/bin/python -I /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/r1_probe.py`（假值、不連外；腳本在 scratchpad，不在 repo）。
- 實測輸出重點：HTTPStatusError 類（404／429／500／301）× Telegram／Discord 全部 `detail_has_secret=True log_has_secret=True`；傳輸類與畸形 URL 類全部 `False`；httpx INFO 行三條（Telegram、FinMind、Alpha Vantage）均含假祕密。
- 推論（未直接驗證）：scheduler 行程端到端的 log 內容；Docker json-file 預設無大小上限（devops-sre 報告同樣標為推論）；供應商錯誤訊息是否回顯 key。
- 我沒有：讀 `.env`／`.env.example`／DB；連外；改任何程式。

---

## 四、下一步

### A. CEO 要做的主機檢查（不貼值，只算命中數）

檢查位置（依部署方式）：
1. Docker：`docker compose logs scheduler backend`；原始檔在 Docker 主機的 `/var/lib/docker/containers/<id>/<id>-json.log`（Docker Desktop 在其 VM 內）。compose 未設 logging driver（`compose.yaml` 無 `logging:`），json-file 預設無輪替，所以**歷史 log 會一直累積，直到容器被移除**（`docker compose restart` 不會清；`down`／重建才會）。
2. 主機部署：`logs\scheduler.log`、`logs\api.log`（手冊 `docs/族群動能-主機部署手冊.md` 的 `*>>` 導向）。
3. 任何把 log 貼出去的地方：聊天紀錄、issue／PR、`work/` 內貼的 log 片段、雲端同步資料夾、備份。

只算命中數的指令（不會印出祕密）：

```
docker compose logs scheduler backend 2>&1 | grep -cE 'api\.telegram\.org/bot|/api/webhooks/[0-9]+/|[?&](token|apikey)='
```

主機部署以 PowerShell 對 `logs\*.log` 用 `Select-String -Pattern 'api\.telegram\.org/bot|/api/webhooks/\d+/|[?&](token|apikey)=' | Measure-Object`。

### B. 是否輪換的判準

| 狀況 | 處置 |
|---|---|
| 命中數 0，且那些變數從未設定過／從未發送過 | 不需輪換。仍須修補（修補前只要設定並發送，就會寫入） |
| 命中數 > 0，log 只在單人使用、自己的磁碟、從未離開該主機（未貼出、未備份、未同步、無他人可登入） | **建議輪換**（成本幾分鐘：Telegram 在 BotFather `/revoke`；Discord 刪除 webhook 並重建；FinMind 於帳號重產 token；Alpha Vantage 依供應商可重發才換），但可排在修補部署後。順序：修補部署 → 清舊 log（重建容器、封存或刪除 `logs\*.log`）→ 輪換 → 確認新 log 乾淨。先輪換再修補，新 token 會再被寫進 log |
| 命中數 > 0，且符合下列任一：log 曾離開主機（貼到聊天／issue／PR／AI 對話／雲端同步／備份／支援包）、主機多人共用、log 轉送到遠端、不確定誰讀過 | **必須輪換**，且視為已外洩：Telegram 檢查 bot 近期對話與 webhook 設定有無異常；Discord 檢查頻道有無非預期貼文 |
| 無法檢查（log 已遺失或容器已清） | 不能證明沒有。若曾設定並發送過 Telegram／Discord，保守起見輪換（成本低於不確定的代價） |

影響面：Telegram bot token 可冒用 bot 發訊息、讀取 bot 的更新；Discord webhook URL 可讓任何人往該頻道發文；FinMind token／Alpha Vantage key 可被他人耗用額度。皆不涉及資金或本系統的 DB，屬中度風險，但仍違反 CLAUDE.md §4。

### C. 給 dev-lead 的修補要求（另案；我不改程式）

1. **`notify.py` `_deliver()`**
   - log 與 `detail` 一律用固定格式，只含：channel、例外類別名（`type(exc).__name__`）、HTTP 狀態碼（僅 `httpx.HTTPStatusError` 時取 `exc.response.status_code`）。例：log `alert webhook delivery failed: channel=%s error_class=%s status=%s`；detail `HTTP 404` 或 `ConnectError`。
   - 禁止：`str(exc)`、`repr(exc)`、`exc_info=True`、`logger.exception`、`raise ... from exc` 後被別處記錄 traceback、把 `exc.request.url`／`exc.response.url` 放進任何字串。
   - 不要靠「過濾 URL 後再放原文」（例外訊息內容隨函式庫版本變）；只取類別名與狀態碼，對任何訊息文字都穩健。
   - `detail` 保持非空（`tests/test_alerts_notify.py:102`）。
2. **關掉 F-1**：在 scheduler 入口（`scheduler.py:782` 的 `main()`）`basicConfig` 之後，把 `httpx`、`httpcore` logger 設為 WARNING；與 O-1 的 `configure_logging()` 合併實作（冪等、放行程入口，不放 import 階段），API 與 scheduler 共用。
3. **URL 遮罩函式**（`redact_url()`，放共用模組）：Telegram 路徑 `/bot<…>/` → `/bot***/`；Discord `/webhooks/<id>/<…>` → `/webhooks/<id>/***`；query 的 `token`／`apikey`／`api_key` 值 → `***`。任何要把 URL 放進 log 或訊息的地方都必須經此函式。另掛一個 `logging.Filter` 做全域遮蔽（縱深防禦）。
4. **測試**（見 D 驗收格），含「敵意例外訊息」：處理器 `raise httpx.ConnectError(f"boom {request.url}")`，證明修補不依賴函式庫的善意。
5. **N-23 維運告警同規則**：設計 §2 已定「不得記例外字串、URL」，實作要沿用同一個固定格式輔助函式，不要各寫各的。
6. **後續（不阻擋）**：F-4 截斷第三方文字；F-5 compose 逐項傳遞環境變數（交 devops-sre／tech-architect）。
7. 變更範圍小、不改契約，不需 ADR；但 `configure_logging()` 與 O-1 合併，請回報 O-1 單負責人。

### D. 給 qa 的驗收格

| # | 驗收項 | 通過條件 |
|---|---|---|
| 1 | Telegram 404／429／500／301 | `caplog` 全文、`DeliveryResult.detail`、`repr(results)` 皆不含假 token，也不含 `api.telegram.org/bot` |
| 2 | Discord 404／500／301 | 皆不含假 webhook token；不含 `/api/webhooks/` 後接祕密的片段 |
| 3 | 敵意例外：`ConnectError`／`ReadTimeout`／`HTTPStatusError`，訊息內嵌完整 URL | log 與 detail 仍不含祕密 |
| 4 | detail／log 格式 | 只有 channel、類別名、狀態碼（如 `error_class=HTTPStatusError status=404`）；`detail` 非空 |
| 5 | 成功路徑 + 實際 scheduler 日誌設定（呼叫 scheduler 入口的日誌設定函式，root=INFO）| `caplog`（含 `httpx` logger）無任何含假祕密的 record；`logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING` |
| 6 | FinMind、Alpha Vantage 成功與失敗路徑（假 token／key）| 同上，log 中無 `token=`／`apikey=` 值 |
| 7 | `redact_url()` 單元測試 | Telegram、Discord、query 三種輸入遮蔽；已遮蔽輸入冪等；非祕密 URL 不變 |
| 8 | 流程不受影響 | 推播失敗仍不拋出、事件仍已存（既有 `test_a_failing_webhook_is_reported_not_raised`、`test_a_transport_error_is_contained` 維持綠）|
| 9 | 靜態檢查 | `notify.py` 無 `str(exc)`、`{exc}`、`exc_info`、`logger.exception`；CI 加 gitleaks 無新增命中 |
| 10 | 實機（devops-sre）| 部署後以假 token 的測試設定觸發一次失敗與一次成功，`docker compose logs scheduler` grep 上述 regex 命中 0 |

### E. 交接與升級

- 修補實作 → dev-lead（C）；logging 與 compose 落地、gitleaks CI → devops-sre；驗收 → qa-reviewer。
- **升級 CEO**：A、B（主機 log 清查與輪換決定）。這是唯一需要人工在主機上做的部分；我無法代為檢查。
- Verdict：NEEDS_CHANGES；BLOCKING_ISSUES=true（阻擋 N-23 維運告警上線與 D_v 前驗收清單第 3 項）。

# 告警通道合併狀態與台銀查證（RC-610 第 3 點、RC-602）— devops-sre

查證時間：2026-11-22 20:47～20:49（台灣時間）。查證基準：`git fetch origin` 後的 `origin/product/stock-desk`，HEAD = `21edb2a`。只用唯讀 git、Read／Grep 與一次 curl；未讀任何 token、webhook URL、設定值，未動 repo。
（註：本 container 的 git 預設輸出為 UTC，下列時間已全部以 TZ=Asia/Taipei 重算。）

## 一、本次結論
1. 第 1 件：**R-1 遮蔽已合併**，並有測試釘住；**ADR-0029 的維運告警通道（Telegram／Discord 的 ops_alert 推播）沒有合併**，只合併了純型別模型（model.py），沒有渲染、送出器、傳輸層、接線。
2. 第 2 件：團隊環境到台銀 `rate.bot.com.tw` **目前仍被擋**（proxy 回 403，沒有取得任何回應內容）。結果只代表團隊環境，不代表 CEO 本機。

## 二、第 1 件：RC-610 第 3 點

### 事實（git 與程式碼）
**A. R-1 修補（httpx INFO 寫出完整 URL 的遮蔽，security-engineer F-1／F-2）：已合併**
| 項目 | 內容 |
|---|---|
| 修補 commits | `cb4e51a`（fix: API 與 scheduler 共用 configure_logging 並遮蔽日誌中的祕密）2026-10-19 05:01；`aa1b2bd`（test: 守門匯入後 root logger 無 handler）2026-10-19 05:17（此二者為 ADR-0029 列的 cb4e51a／ce56f43／91b5429 分支內容，我只逐一核對了 cb4e51a、aa1b2bd 為 product 祖先；ce56f43、91b5429 未逐個核對，但其分支已整條合併） |
| 進 product first-parent | `3903df1`「chore: 合併 R-1 推播祕密遮蔽（fix/stock-desk-r1-secret-redaction）」，**2026-10-26 16:18:47 +0800**；`git merge-base --is-ancestor 3903df1 origin/product/stock-desk` 成立 |
| 同日另有 | `c9401c2` 合併風控整改五項，2026-10-27 00:20:51 +0800（動過 logging_setup／notify 相關檔，非 R-1 本體） |

現行 HEAD（`21edb2a`）上的位置，路徑相對 `apps/stock-desk/backend/`：
- `app/logging_setup.py:102-122` `configure_logging()`；`:104-105` 將 `httpx`、`httpcore`（`QUIET_NAMESPACES`，`:45`）釘在 WARNING，所以 INFO 不再寫出請求 URL。
- `app/logging_setup.py:52-64` `_REDACTIONS`（Telegram `bot<token>`、Discord `/webhooks/<id>/<token>`、`token=`／`apikey=`／`api_key=`）；`:67-76` `redact_url()`；`:79-99` `SecretRedactionFilter`（含 traceback 與 stack_info）；`:118` 裝在 handler 上。
- `app/logging_setup.py:125-134` `describe_failure()`：只留例外類別名與 HTTP 狀態碼，不含訊息文字（對應 F-2）。
- `app/alerts/notify.py:34` 匯入、`:97` `detail = describe_failure(exc)`（失敗訊息不再帶例外原文）。
- 呼叫點：`app/main.py:49`（API lifespan）、`app/scheduler.py:786`（scheduler `main()`）。

測試釘住：`tests/test_r1_secret_redaction.py`，19 個測試函式，涵蓋：
- `:187` HTTP 失敗時兩個通道的祕密不外洩、`:233` 例外文字內含 URL 不外洩、`:250`／`:643` describe_failure 只讀類別與狀態；
- `:262` scheduler 入口讓成功推播時 httpx 靜音（即 INFO 完整 URL 那個場景）、`:288` 安裝遮蔽 handler、`:300` API lifespan 有設定、`:310` 冪等、`:319` 既有 root 時只套 httpx 下限；
- `:381` 匯入 app.main／app.scheduler 後 root 無 handler、`:385` 新程序只裝一個遮蔽 handler；
- `:447`、`:475` FinMind token、Alpha Vantage key 不進 log；`:551`、`:568`、`:572`、`:591` redact_url／filter 單元；`:619`、`:627` notify 不得有禁用的例外渲染（靜態守門）。

**B. ADR-0029 維運告警通道：未合併（僅有型別模型）**
- ADR 檔 `docs/adr/0029-stock-desk-維運告警通道.md` 狀態仍標「proposed」（檔頭第 3 行，為我讀到的現況；是否已有後續核可紀錄我沒有逐檔查）。落檔 commit `9257207`，2026-10-19 20:50:41 +0800，內容為文件。
- 已進 product first-parent 的程式：`ec1dead`（feat: ADR-0027 B1 純葉節點…ops_alert 告警模型），**2026-10-25 23:52:27 +0800**。HEAD 上 `app/ops_alert/` 只有 `__init__.py` 與 `model.py`；`model.py:446-449` 有 `OpsAlertSink` Protocol（`emit(alert) -> None`）。
- `app/ops_alert/__init__.py:5` 自述「entry point and `app.push_channels` come in later batches」。
- HEAD 上**不存在** `app/push_channels.py`、`app/ops_alert/render.py`、任何實作 `OpsAlertSink` 的類別（grep `class .*Sink`、`def emit` 只命中 model.py 的 Protocol）。Telegram／Discord 字樣只出現在既有使用者警示通道 `app/alerts/notify.py`、`app/env_status.py`、`app/alerts/engine.py` 註解與 `logging_setup.py`。
- 即：能推 Telegram／Discord 的只有**既有的使用者警示推播**（`notify.py`，R-1 之後已遮蔽）；ADR-0029 規劃的「維運告警（第一次就告警）」那條**沒有任何可執行程式**。

### 推論
- R-1 的 ADR-0029「先合併（阻擋）」前提已滿足（2026-10-26 16:18 合併，早於 ADR-0029 任何實作），所以現行推播通道在 log 面的外洩缺口（F-1、F-2）已補。
- ADR-0029 通道尚未落地，意味著 ADR-0027 的預測帳結算若失敗，目前仍只會寫 log，不會推播。是否影響 CEO 現在用的功能，取決於預測帳結算功能是否已對外啟用（HEAD 有 `test_forecast_gate_closed.py`，名稱暗示閘門關閉；我未讀內容，屬推論）。

### 未查證
- CEO 主機上既有 log 是否已含真實祕密、是否已輪換（ADR-0029 與 security-engineer 列為上線前提，屬 CEO 主機端，我無法也不應查）。
- R-1 合併後，**實際運行中的 CEO 主機**是否已更新到含 `3903df1` 的版本（我只看 origin 分支）。
- 測試在本次未重跑；上述「有測試釘住」是依測試原始碼內容判斷，不是本次的綠燈證據。
- `ce56f43`、`91b5429` 兩個 commit 未逐個核對祖先關係。

## 三、第 2 件：RC-602 台銀匯率來源

### 事實
來源網址取自 `app/data/providers/fx.py`：`BOT_BASE_URL = "https://rate.bot.com.tw"`（`:68`），路徑 `/xrt/flcsv/0/<YYYY-MM-DD>`（檔頭 `:12`）。

| 項目 | 結果 |
|---|---|
| 測試時間（台灣時間） | 2026-11-22 20:48:03 |
| URL 1 | `https://rate.bot.com.tw/xrt/flcsv/0/2026-11-20` |
| 指令 | `curl -sS -o /dev/null -w '%{http_code} %{size_download}\n' --max-time 20 <URL>` |
| 結果 | `curl: (56) CONNECT tunnel failed, response 403`；`000 0`（無 HTTP 狀態碼、回應大小 0） |
| URL 2（根網址，對照） | `https://rate.bot.com.tw`，20:48:03，同樣 `CONNECT tunnel failed, response 403`、`000 0` |
| proxy 是否擋下 | **是**：失敗發生在 CONNECT 隧道階段（proxy 回 403），請求沒有到達台銀；輸出末端沒有出現 `[agent-proxy]` 行，所以 proxy 沒標明原因，我只能依 CONNECT 403 判定是 proxy 側拒絕（推論，無 proxy 日誌佐證） |
| 回應內容 | 未存、未帶認證 |

### 限定範圍（RC-602 第 3 點）
**此結果只代表團隊環境（本 container 經 agent proxy 的出口），不代表 CEO 本機。** CEO 本機能否連到台銀、是否遇到 Cloudflare 類挑戰頁（`fx.py:136` `_looks_like_challenge_page` 有對應處理），本次沒有也不能驗證。
每月提醒由 coordinator 另行安排，我未設排程。

## 四、下一步
1. （coordinator／風控）RC-610 第 3 點可據此回覆：R-1 已合併且有測試，ADR-0029 通道未合併、僅型別模型。若風控要「測試綠燈」證據，需另派人在乾淨環境跑 `tests/test_r1_secret_redaction.py`（我可做，但需變更性指令許可或在 CI 看紀錄）。
2. （CEO）若要確認主機端：確認主機已更新到含 `3903df1` 的版本，並清查舊 log 與輪換（ADR-0029 前提；屬 CEO 本機動作）。
3. （tech-architect／CEO）ADR-0029 仍 proposed，要不要排後續批次（render／push_channels／接線）需決策。
4. 台銀來源：團隊環境持續被擋；每月複查由 coordinator 排；實際可用性以 CEO 本機為準。

## 回滾方式
本次只讀、無任何 repo 變更，無需回滾。

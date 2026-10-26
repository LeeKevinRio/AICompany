# flight-deals 機票低價監看器

個人用的機票低價監看服務：在本機網頁後台設定監看條件，系統依排程查價、保存價格歷史，
價格符合條件時用 Telegram 推播。規格見 `work/flight-deals-PRD.md`，技術決策見
`docs/adr/0002-flight-deals-技術棧與資料源.md`。

> 價格為查到當下的參考值，實際以航空公司或訂票網站為準。

## 啟動

需要 [uv](https://docs.astral.sh/uv/)（開發時用 0.12.1）與 Python 3.11 以上。

```bash
cd apps/flight-deals
uv sync
uv run flight-deals            # http://127.0.0.1:8795
uv run flight-deals --port 8800 --debug
```

從 repo 根目錄也可以用 `uv run --project apps/flight-deals flight-deals`
（`.claude/launch.json` 的 `flight-deals` 設定就是這個指令）。

### Windows：一鍵啟動

雙擊 `apps\flight-deals\dev-up.bat`（或在任何目錄執行它）。它會依序：

1. 檢查 git、uv 是否已安裝；`.env` 不存在時提示 Telegram 通知會維持關閉（仍會繼續）。
2. 確認沒有未提交的已追蹤檔案變更；若不在 `product/flight-deals` 分支會詢問是否切換；然後 `git pull --ff-only`；
   遠端還沒有這條分支或離線時印 `[SKIP]`，沿用本機程式碼。
3. 若 port 8795 被占用，或已有舊的 flight-deals 程序，列出 PID 並詢問是否結束（避免兩份排程重複掃描）。
4. `uv sync --locked` 安裝依賴，在獨立視窗 `flight-deals` 啟動 `uv run flight-deals`。
5. 最多等 60 秒到首頁回應，印出 `[OK]` 或 `[FAIL]`，成功後自動開啟瀏覽器 `http://127.0.0.1:8795`；逾時則不開瀏覽器，視窗停住讓你看錯誤。

腳本固定用 8795，並以 `--port 8795` 啟動；要改 port 請自行用 `uv run flight-deals --port <port>` 啟動。

停止方式：關閉標題為 `flight-deals` 的視窗。啟動失敗時該視窗不會自動關閉，可直接看錯誤訊息。

服務是單一 process：網頁、排程（APScheduler，單一 worker thread）與 SQLite 都在裡面。
不要用多 worker 或 `--reload` 啟動，否則會出現兩份排程。

## 環境變數

可以寫在 `apps/flight-deals/.env`（已被 `.gitignore`），格式參考 `.env.example`。
真正的環境變數優先於 `.env`。

| 變數 | 用途 | 預設 |
| --- | --- | --- |
| `FLIGHT_DEALS_TELEGRAM_BOT_TOKEN` | Telegram bot token（祕密） | 未設定則不推播 |
| `FLIGHT_DEALS_TELEGRAM_CHAT_ID` | 接收通知的 chat id | 未設定則不推播 |
| `FLIGHT_DEALS_DB_PATH` | SQLite 檔案路徑 | `apps/flight-deals/data/flight-deals.db` |
| `FLIGHT_DEALS_SOURCES` | 資料源，逗號分隔 | `google_flights` |
| `FLIGHT_DEALS_PORT` | 監聽 port | `8795` |

`fixture` 資料源只給測試用，正式啟動時若 `FLIGHT_DEALS_SOURCES` 含 `fixture` 會直接拒絕啟動。

掃描週期、每監看每輪查詢上限、下跌比例門檻、價格過期標示時間、全域每小時查詢上限，
都可以在網頁「設定與健康」頁調整。

## 建立 Telegram bot

1. 在 Telegram 搜尋 **@BotFather**，傳送 `/newbot`，依指示取名，取得 bot token。
2. 先在 Telegram 對你的新 bot 傳一則任意訊息。
3. 用瀏覽器開啟 `https://api.telegram.org/bot<你的 token>/getUpdates`，
   在回應 JSON 的 `message.chat.id` 找到 chat id。
4. 把 token 與 chat id 寫進 `.env` 或環境變數，重新啟動服務。
5. 到「設定與健康」頁按「發送測試訊息」確認。

token 只從環境變數讀取；網頁、log、資料庫都不會出現 token 原文。

## 開發

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest -q                                   # 全程離線，對外連線會被擋
uv run pytest -q -m live tests/test_live_smoke.py  # 手動執行：真的打一次 Google Flights
```

## 使用限制（必讀）

本工具透過非官方、反向工程的 fast-flights 套件讀取 Google Flights 搜尋結果，Google 並未提供或授權此存取方式，使用行為可能牴觸 Google 服務條款。本工具僅限擁有者個人於本機、低頻使用；不得公開部署、提供他人使用、商業化，或散布、轉售所取得的價格資料。遇到封鎖或驗證要求時不得以更換 IP、第三方代抓、自動解驗證等方式規避。價格為查到當下的參考值，可能與實際售價不同，實際以航空公司或訂票網站為準；本工具不提供任何購買建議。以上說明非法律意見。

## 已知限制

- **機器沒開就不會掃描。** 排程跑在服務 process 內，筆電睡眠或關機期間不會查價；
  重新啟動後只補跑已逾期的監看（逐一錯開），補不回當時的價格。
- **fast-flights 是非官方介面，隨時可能壞。** 它反向工程 Google Flights，Google 改版、
  回傳空白頁或封鎖時，查價結果會標成「被擋或格式改變」，連續失敗會觸發斷路器、
  在健康頁顯示「異常」並推一則 Telegram 告警。此時可用詳情頁的「人工查價連結」自行查詢。
- **只綁 127.0.0.1。** 服務沒有登入機制，只接受來自本機、Host 為 `127.0.0.1` 或
  `localhost` 的請求；從其他機器或手機無法連線，這是刻意的設計。要對外開放必須另開需求加上認證。
- 只查取樣到的日期：彈性窗日期組合超過每輪上限時會等距取樣並每輪輪換，
  「最便宜時段」只代表已取樣的日期。
- 不做匯率換算；資料源回傳幣別與監看不一致時照樣記錄，但不參與通知判斷。
- 只支援經濟艙、1 位成人、來回或單程。
- 日期最遠只能設到今天起 365 天，彈性窗長度最多 366 天。
- **通知漏送不會自動補。** Telegram 長時間故障時，同一筆價格重試 3 次仍失敗就不會再通知；
  未設定 Telegram 期間產生的通知會記成「未送出（未設定）」，日後設定好也不會補發。
  請到「通知紀錄」頁查看漏送的價格。

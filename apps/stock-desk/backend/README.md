# Stock Desk Backend

Stock Desk 產品的後端服務。技術棧：Python 3.12 + FastAPI + APScheduler，依賴以 `uv` 管理。

## 需求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## 安裝依賴

```bash
uv sync
```

此指令會依 `uv.lock` 建立 `.venv` 並安裝正式與 dev 依賴。

## 啟動 dev server

```bash
uv run uvicorn app.main:app --reload --port 8000
```

健康檢查：`GET http://127.0.0.1:8000/health`，回傳範例：

```json
{"status": "ok", "service": "backend", "as_of": "2026-07-23T00:00:00+00:00"}
```

## 測試

```bash
uv run pytest
```

## Lint 與型別檢查

```bash
uv run ruff check .
uv run mypy app tests
```

## 資料層（`app/data/`）

市場資料存取一律經 `app.data.service.MarketDataService`（主來源 TWSE/TPEx
→ 備援 FinMind → SQLite 快取 → `unavailable`），不要在應用程式碼直接呼叫
provider adapter。詳見各模組檔頭註解與 `tests/fixtures/README.md`（fixture
來源與實錄/合成狀態說明）。

環境變數：

| 變數 | 用途 | 預設 |
| --- | --- | --- |
| `STOCK_DESK_DB_PATH` | SQLite 檔路徑（快取、持倉、設定、警示共用一個檔） | `./data/stock-desk.db` |
| `FINMIND_API_TOKEN` | FinMind 備援來源的 API token；未設定時該 adapter 明確回傳 `unavailable`，不丟例外 | 無 |
| `ALERT_DISCORD_WEBHOOK_URL` | 警示推播的 Discord webhook；**祕密，只走環境變數 / `.env`**。未設定就跳過該通道 | 無 |
| `ALERT_TELEGRAM_BOT_TOKEN` | 警示推播的 Telegram bot token；**祕密**。與 chat id 兩者都有才會送出 | 無 |
| `ALERT_TELEGRAM_CHAT_ID` | 警示推播的 Telegram chat id | 無 |
| `SCHEDULER_DATA_INTERVAL_MINUTES` | 排程的資料更新間隔（分鐘） | `1440` |
| `SCHEDULER_ALERT_INTERVAL_MINUTES` | 排程的警示評估間隔（分鐘）；未設定時取 `/api/settings` 的 `alerts.evaluation_interval_minutes` | 設定值（預設 60） |

## API 端點

所有回應都帶 `as_of`。**資料不足一律回 200 並帶 `status: "insufficient_data"` 與 `reason`**，
不是 500——「算不出來」是世界的狀態，不是伺服器故障。

| 端點 | 回應主體對應的模組函式 |
| --- | --- |
| `GET /health` | — |
| `GET/POST/PUT/DELETE /api/positions…` | `app.positions.store` |
| `GET /api/portfolio/summary` | `app.portfolio.summary.build_summary` |
| `GET /api/bars/{symbol}?market=` | `bars` = 原始日線（`app.data.service.MarketDataService`）；價格為 Decimal 字串 |
| `GET /api/signals/{symbol}?market=` | `signals` = `app.signals.service.compute_signals` |
| `GET /api/advice/{symbol}?market=` | `advice` = `app.advice.engine.build_advice` |
| `GET /api/leverage/{symbol}?market=` | `chapter` = `app.leverage.service.build_leverage_chapter` |
| `POST /api/backtest` | `report` = `app.backtest.report.walk_forward_report` |
| `GET/PUT /api/settings` | `app.settings.models.AppSettings` |
| `GET/POST/DELETE /api/alerts`、`GET /api/alerts/events`、`POST /api/alerts/events/{id}/ack`、`POST /api/alerts/evaluate` | `app.alerts.*` |

## 離線示範模式（`app/demo/`）

> **警告：這是合成示範資料，不可用於任何真實決策。**
> 所有日線都是本機用固定亂數種子產生的假資料，不是任何市場的實錄。

沒有外網的環境（CI、驗收機、展示用筆電）會從每一個 provider 拿到 `unavailable`，
四個頁面因此整片都是 `insufficient_data`。這支 seed 腳本把合成資料寫進**既有的**
快取層與 store（沒有新 schema、沒有另一套資料表），讓整條鏈路可以離線跑出真實數字。

```bash
# 產生（或更新）示範資料；DB 路徑沿用 STOCK_DESK_DB_PATH
uv run python -m app.demo.seed

# 指定資料庫
uv run python -m app.demo.seed --db-path ./data/demo.db

# 清除示範資料（只刪自己寫的那些列）
uv run python -m app.demo.seed --reset
```

會寫入什麼：

| 項目 | 內容 |
| --- | --- |
| 日線 | 三檔各 520 根（約兩年交易日，結束於今天之前最近的平日）：`2330`（一般台股）、`0050`（作為 `00631L` 標的指數的追蹤標的）、`00631L`（日度重置槓桿 ETF，NAV 由 `0050` 的**單日**報酬套用註冊表中的倍數與費用率逐日複利推導） |
| 走勢 | 依序為盤整暖身 → 上升趨勢 → 回檔 → 均值回歸盤整 → 第二段上升 → 急跌 → 反彈，因此均線黃金／死亡交叉、RSI 高低檔、最大回撤規則都有機會命中 |
| 持倉 | 3 筆（2330 / 0050 / 00631L），建倉日與平均成本直接取自產生出來的某一根 bar，帳面損益因此與圖表一致；示範帳本刻意一賺兩賠 |
| 警示規則 | 3 條，涵蓋 `price_below`、`signal_condition`、`risk_limit_breach` 三種類型 |

**資料來源標示**：每一根 bar 的 `source` 都是 `demo_synthetic`，這個字串會原樣出現在
`/api/bars`、`/api/signals`、`/api/advice` 回應的 `data.source`，以及個股頁「來源：」那一行，
不可能被誤認為 TWSE／TPEx／FinMind 的真實行情。示範持倉與警示規則的 `note` 都帶有
`[demo_synthetic]` 前綴。腳本啟動與結束都會印出上面那段警告。

**冪等**：日線走 `PriceBarCache.put` 的 upsert（主鍵 `symbol, market, trade_date`），
持倉與規則以示範標記加上自身識別比對，已存在就原封不動保留，重跑不會長出第二份。
`--reset` 只刪 `source = demo_synthetic` 的日線與帶示範標記的持倉／規則，
對同一個資料庫裡的真實資料沒有影響；警示**事件**依既有 append-only 設計保留。

其他注意事項：

- 警示事件要呼叫 `POST /api/alerts/evaluate`（或等排程跑）才會產生。
- 離線時每個請求仍會先依序嘗試 TWSE → TPEx → FinMind 才降級到快取，
  每個 provider 有 10 秒 timeout 與 3 次重試，因此**第一次載入會明顯變慢**；
  這是既有降級階梯的行為，seed 腳本不會去繞過它。
- 估值層只往回找 10 天的價格。示範資料是以「執行當天」為終點產生的，
  所以一份放了超過十天的示範資料庫要重跑一次 seed 才會再有估值。
- `GET /api/leverage/{symbol}`（個股頁的槓桿專章）依既有設計仍以 `index_bars=None` 呼叫，
  因為系統還沒有指數資料 adapter。即使 seed 了 `0050`，該章的拆解與情境推估仍會誠實回報
  `insufficient_data`；本模式不會偷偷拿別的標的替代。

## 排程（`app/scheduler.py`）

`python -m app.scheduler`（compose 的 `scheduler` service 指令不變）。兩個 interval job：
`data_refresh`（只抓實際持有的標的，替快取層保鮮）與 `alert_evaluation`（跑
`evaluate_alerts` 並推播）。收到 SIGTERM／SIGINT 時 `wait=True` 乾淨關閉，重複收到訊號
不會變成 traceback。

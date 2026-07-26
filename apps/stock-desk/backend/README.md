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

## 排程（`app/scheduler.py`）

`python -m app.scheduler`（compose 的 `scheduler` service 指令不變）。兩個 interval job：
`data_refresh`（只抓實際持有的標的，替快取層保鮮）與 `alert_evaluation`（跑
`evaluate_alerts` 並推播）。收到 SIGTERM／SIGINT 時 `wait=True` 乾淨關閉，重複收到訊號
不會變成 traceback。

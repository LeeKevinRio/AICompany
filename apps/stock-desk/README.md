# stock-desk — 股票訊號與部位決策輔助台

本機執行的**決策輔助儀表板**:把實際部位、市場訊號、風險上限放在同一畫面,
輸出可解釋、可反駁、附失效條件的行動選項。**非自動下單系統、非預言機**。

> 本工具為研究與教育用途,非投資建議。

技術棧決策與取捨見 [docs/adr/0002](../../docs/adr/0002-stock-desk-tech-stack.md)。

## 快速啟動(Docker,建議)

```bash
cd apps/stock-desk
cp .env.example .env        # Phase 1 可不填任何真值
docker compose up --build
```

- 前端:http://localhost:3000
- 後端 API:http://localhost:8000(健康檢查 `GET /health`)
- 排程:`scheduler` service(APScheduler:每日資料更新 + 警示評估)

## 本機開發(不用 Docker)

後端(Python 3.12 + uv):

```bash
cd apps/stock-desk/backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

前端(Node 22 + npm):

```bash
cd apps/stock-desk/frontend
npm install
npm run dev        # http://localhost:3000
```

## 品質門檻(CI 同步執行,見 .github/workflows/stock-desk.yml)

```bash
# 後端
cd apps/stock-desk/backend
uv run ruff check . && uv run mypy app tests && uv run pytest

# 前端
cd apps/stock-desk/frontend
npm run typecheck && npm run build
```

## 已查證版本(devops-sre,查證日 2026-07-23)

| 套件 | 版本 | 來源 |
| --- | --- | --- |
| Python | 3.12 | 系統 CPython 3.12.3 / Docker python:3.12-slim |
| fastapi | 0.139.2 | PyPI(鎖於 uv.lock) |
| uvicorn | 0.51.0 | PyPI(鎖於 uv.lock) |
| next | 16.2.11 | npm(鎖於 package-lock.json) |
| react | 19.2.8 | npm(鎖於 package-lock.json) |
| typescript | 7.0.2 | npm(鎖於 package-lock.json) |
| tailwindcss | 4.3.3 | npm(鎖於 package-lock.json) |
| @tanstack/react-query | 5.101.4 | npm(鎖於 package-lock.json) |
| apscheduler | 3.11.3 | PyPI(鎖於 uv.lock,Phase 6 進場) |
| lightweight-charts | 5.2.0 | npm(M7 進場) |

## 目錄結構

```
apps/stock-desk/
├── compose.yaml              # Docker Compose 設定；三個 service: backend / scheduler / frontend
├── .env.example              # 環境變數範本（只放假值；實際祕密不進版管）
├── backend/                  # FastAPI 後端（Python 3.12 + uv）
│   ├── app/
│   │   ├── main.py          # FastAPI 應用入口；路由聚合點
│   │   ├── api/             # 端點實作（positions / portfolio / bars / signals / advice / leverage / backtest / settings / alerts）
│   │   ├── data/            # 資料層（provider adapters、cache、service）
│   │   ├── signals/         # 訊號層（技術指標、風險度量）
│   │   ├── advice/          # 建議引擎（規則式；YAML 規則檔 + context + engine + limits）
│   │   ├── leverage/        # 槓桿 ETF 分析（偵測、報酬拆解、情境推估）
│   │   ├── backtest/        # 回測引擎（策略、回測循環、報告、績效指標）
│   │   ├── portfolio/        # 持倉組合摘要與估值
│   │   ├── positions/       # 持倉部位管理（CSV 匯入、存儲）
│   │   ├── alerts/          # 警示系統（規則、引擎、推播、事件存儲）
│   │   ├── settings/        # 設定存儲（風險預算、用戶偏好）
│   │   ├── scheduler.py     # APScheduler 排程（每日資料更新 + 警示評估）
│   │   └── services/        # 交叉切關服務（市場資料服務等）
│   ├── tests/               # 測試套件（契約測試、單元測試、fixtures）
│   ├── pyproject.toml       # 專案設定（uv 依賴宣告）
│   └── README.md            # 後端詳細文件
├── frontend/                 # Next.js 前端（Node 22 + npm）
│   ├── app/
│   │   ├── page.tsx         # 首頁（投資組合總覽）
│   │   ├── position/[symbol]/page.tsx    # 詳情頁（訊號、建議卡、槓桿章、K線圖）
│   │   ├── backtest/page.tsx # 回測頁
│   │   ├── settings/page.tsx # 設定頁（風預算、規則版本、警示規則、推播通道）
│   │   ├── components/      # UI 元件（卡片、表格、圖表、狀態徽章）
│   │   ├── lib/             # 工具函數與型別定義（API 呼叫、查詢、格式化）
│   │   └── layout.tsx       # 版面與導航
│   ├── public/              # 靜態資源（favicon、logo）
│   ├── package.json         # npm 依賴
│   └── tsconfig.json        # TypeScript 設定（strict mode）
└── README.md                # 本檔；快速啟動與概覽
```

## 後端模組概覽

詳細請見 `backend/README.md`；本處僅列主要職責：

| 模組 | 職責 |
| --- | --- |
| `app/data/` | 市場資料存取；降級鏈：主供應商 → 備援 → 快取 → unavailable |
| `app/signals/` | 技術指標計算（MA、RSI、ATR、MACD 等）與風險度量（回撤、波動率等） |
| `app/advice/` | 規則式建議引擎（YAML 規則、Context 構築、規則求值、卡片組裝） |
| `app/leverage/` | 槓桿 ETF 拆解（偵測、報酬衰減分解、情境推估） |
| `app/backtest/` | Walk-forward 回測、績效計算（Sharpe / Sortino / 最大回撤等） |
| `app/portfolio/` | 持倉組合摘要、估值聚合、P&L 計算 |
| `app/positions/` | CRUD 與 CSV 匯入；存儲到 SQLite |
| `app/alerts/` | 警示規則定義、評估引擎、推播（Discord/Telegram） |
| `app/settings/` | 風險預算、規則版本、用戶偏好存儲 |
| `app/scheduler.py` | APScheduler 驅動的定時工作（資料更新、警示評估） |

## 前端頁面概覽

| 頁面 | 路由 | 功能 |
| --- | --- | --- |
| 投資組合總覽 | `/` | 持倉摘要卡、持倉明細表、風險規表、待確認警示面板 |
| 標的詳情 | `/position/[symbol]?market=TW/US` | K線圖（含 MA）、建議卡（規則、權重、上限檢查）、槓桿 ETF 專章（若適用） |
| 回測 | `/backtest` | MA Cross 策略、參數調整、樣本內/外分列報告 |
| 設定 | `/settings` | 風預算調整、規則版本查看、警示規則管理、資料源狀態 |

## 環境變數與配置

詳見 `backend/README.md` 的環境變數表。核心配置：

| 變數 | 用途 | 預設 | 是否必須 |
| --- | --- | --- | --- |
| `STOCK_DESK_DB_PATH` | SQLite 資料庫檔路徑 | `./data/stock-desk.db` | 選用 |
| `FINMIND_API_TOKEN` | FinMind 備援來源的 API token | 無 | 選用（未設定時 FinMind adapter 回 unavailable） |
| `ALERT_DISCORD_WEBHOOK_URL` | Discord 推播 webhook | 無 | 選用 |
| `ALERT_TELEGRAM_BOT_TOKEN` | Telegram bot token | 無 | 選用（需搭配 CHAT_ID） |
| `ALERT_TELEGRAM_CHAT_ID` | Telegram chat id | 無 | 選用（需搭配 BOT_TOKEN） |
| `SCHEDULER_DATA_INTERVAL_MINUTES` | 資料更新間隔 | 1440 (24h) | 選用 |
| `SCHEDULER_ALERT_INTERVAL_MINUTES` | 警示評估間隔 | 60 | 選用 |

所有祕密（token、webhook）**絕不進版管**；僅透過環境變數或 `.env` 檔（已被 `.gitignore`）讀取。

## 離線示範模式（規劃中）

**暫未實現**；dev-lead 正規劃預加載 seed 資料以支援無網路環境演示。預期：

- SQLite 檔案預裝虛擬持倉（台股、槓桿 ETF）與歷史日線（快取），毋須實時連網。
- 前端可正常開啟、瀏覽計算過的訊號、建議卡、回測結果。
- 適合演示場景（售前、工作坊等）。

規劃位置：`backend/fixtures/seed_data.py`（待實作）；詳情洽 dev-lead。

## 資料適配狀態

| 市場/類型 | 資料來源 | 狀態 | 備註 |
| --- | --- | --- | --- |
| **台股 (TW)** | TWSE (官方) → TPEx (OTC) → FinMind (備援) | ✅ 生產就緒 | 無額度限制；24h 快取 TTL |
| **美股 (US)** | Alpha Vantage (規劃) / yfinance (規劃) | ⏳ 實作中 | 見 ADR-0003；當前無 adapter，查詢回 unavailable |
| **指數** | (無) | ⏳ 規劃中 | 槓桿 ETF 情境推估需要，暫無來源 |
| **匯率 (FX)** | (無) | ⏳ 規劃中 | USD/JPY 等轉 TWD；暫無 adapter |
| **產業分類** | (無) | ⏳ 規劃中 | 風控第 2 條上限需要；Position 無 sector 欄位 |

詳見 `work/stock-desk-已知限制與後續.md`（限制清單與解法方向）。

## 文件與交付物

| 文檔 | 對象 | 內容 |
| --- | --- | --- |
| `work/stock-desk-產品說明.md` | 使用者 (CEO) | 四頁使用導覽、欄位讀法、快速啟動、常見問題 |
| `work/stock-desk-已知限制與後續.md` | 開發團隊 | 11 項已知限制、解法方向、優先序、跨團隊協作點 |
| `docs/adr/0004-stock-desk-建議引擎採規則式.md` | 技術決策 | 規則式 vs. ML 比較、架構約束、驗收標準 |
| `backend/README.md` | 開發者 | API 端點表、環境變數、資料層設計、排程 |
| 本檔 (`README.md`) | 快速上手 | 啟動指令、目錄結構、版本查證、環境配置 |

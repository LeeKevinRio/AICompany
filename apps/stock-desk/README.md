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

> **選用步驟**:若要使用代號／公司名稱搜尋功能(前端 combobox),需先在**有網路的機器**
> 執行一次性目錄同步:
> ```bash
> cd apps/stock-desk/backend
> uv run python -m app.directory.sync
> ```
> 這會把 TWSE 上市清單與 TPEx 上櫃清單寫進 `STOCK_DESK_DB_PATH` 指到的 SQLite
> (`backend/app/directory/sync.py:1-37`)。本雲端開發環境對財經網域的 egress 已知被封鎖,
> 此指令必須在有網路的機器(例如 CEO 本機)執行,結果隨資料庫檔案帶到其他環境即可離線查詢
> (`backend/app/directory/sync.py:6-27`)。未同步前搜尋 API 會誠實回報
> `directory_synced: false`,不會把「還沒同步」誤顯示成「查無結果」
> (`backend/app/api/directory.py:93-102`)。

## 資料存放與備份

`backend` 與 `scheduler` 兩個 service 共用同一個具名 volume `stock-desk-data`,
掛載在兩邊容器的 `/app/data`,並各自把 `STOCK_DESK_DB_PATH` 顯式指到
`/app/data/stock-desk.db`(見 `compose.yaml`)。這一顆 SQLite 檔案(WAL 模式)
裝了持倉、風險設定、警示規則/事件與價格快取——**全部使用者資料都在這裡**。

- 兩個 service 指向同一路徑是刻意的:排程寫入的每日資料更新、警示評估結果,
  一定要跟 API 服務讀寫同一份 DB,否則排程形同空跑(見本次修復的部署缺陷)。
- **備份**:直接備份整個 volume,不需要停機(SQLite WAL 支援線上備份):
  ```bash
  docker run --rm -v stock-desk-data:/data -v "$PWD":/backup alpine \
    tar czf /backup/stock-desk-data-$(date +%Y%m%d).tar.gz -C /data .
  ```
  還原時反向操作(`tar xzf ... -C /data`)。
- **危險操作警告**:`docker compose down -v` 或手動 `docker volume rm stock-desk-data`
  會**永久刪除**這顆 volume,連同全部持倉、設定、警示規則與快取。一般重啟/重建
  請只用 `docker compose down`(不帶 `-v`)或 `docker compose restart`。

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
│   │   ├── api/             # 端點實作（positions / portfolio / bars / signals / advice / leverage / backtest / settings / alerts / directory）
│   │   ├── data/            # 資料層（provider adapters、cache、service）
│   │   ├── signals/         # 訊號層（技術指標、風險度量）
│   │   ├── advice/          # 建議引擎（規則式；YAML 規則檔 + context + engine + limits）
│   │   ├── leverage/        # 槓桿 ETF 分析（偵測、報酬拆解、情境推估）
│   │   ├── backtest/        # 回測引擎（策略、回測循環、報告、績效指標）
│   │   ├── portfolio/        # 持倉組合摘要與估值
│   │   ├── positions/       # 持倉部位管理（CSV 匯入、存儲）
│   │   ├── alerts/          # 警示系統（規則、引擎、推播、事件存儲；規則可 PUT/PATCH 編輯）
│   │   ├── directory/       # 證券目錄（代號/公司名稱/市場；CEO 本機同步 CLI + 查詢 API）
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
| `app/backtest/` | Walk-forward 回測、績效計算（Sharpe / Sortino / 最大回撤等）；內建 `ma_cross`、`rsi_reversal`、`breakout` 三種策略 |
| `app/portfolio/` | 持倉組合摘要、估值聚合、P&L 計算 |
| `app/positions/` | CRUD 與 CSV 匯入；存儲到 SQLite；`sector`（台股產業別，封閉清單）欄位與驗證 |
| `app/alerts/` | 警示規則定義、評估引擎、推播（Discord/Telegram）；規則可整條替換（PUT）或部分修改（PATCH），沿用原 id |
| `app/directory/` | 證券目錄：`sync.py`（CEO 本機一鍵同步 TWSE/TPEx 清單 CLI）、`store.py`（SQLite 查詢）、`providers.py` |
| `app/settings/` | 風險預算、規則版本、用戶偏好存儲 |
| `app/scheduler.py` | APScheduler 驅動的定時工作（資料更新、警示評估） |

## 前端頁面概覽

| 頁面 | 路由 | 功能 |
| --- | --- | --- |
| 投資組合總覽 | `/` | 持倉摘要卡、持倉明細表、風險規表、待確認警示面板 |
| 標的詳情 | `/position/[symbol]?market=TW/US` | K線圖（含 MA）、建議卡（規則、權重、上限檢查）、槓桿 ETF 專章（若適用） |
| 回測 | `/backtest` | 三種內建策略（MA Cross、RSI 反轉、突破）、walk-forward 窗口與成本設定、樣本內/外分列報告（`backend/app/backtest/strategies.py:1-60`；策略參數本身固定，不開放使用者調參） |
| 設定 | `/settings` | 風預算調整、規則版本查看、警示規則管理、資料源狀態 |

## 環境變數與配置

詳見 `backend/README.md` 的環境變數表。核心配置：

| 變數 | 用途 | 預設 | 是否必須 |
| --- | --- | --- | --- |
| `STOCK_DESK_DB_PATH` | SQLite 資料庫檔路徑 | `./data/stock-desk.db`(本機直跑);Docker 下由 `compose.yaml` 顯式設為 `/app/data/stock-desk.db`(掛在 `stock-desk-data` volume) | 選用,但 Docker 部署下 backend / scheduler 兩邊務必指向同一路徑,見上方「資料存放與備份」 |
| `FINMIND_API_TOKEN` | FinMind 備援來源的 API token | 無 | 選用（未設定時 FinMind adapter 回 unavailable） |
| `ALERT_DISCORD_WEBHOOK_URL` | Discord 推播 webhook | 無 | 選用 |
| `ALERT_TELEGRAM_BOT_TOKEN` | Telegram bot token | 無 | 選用（需搭配 CHAT_ID） |
| `ALERT_TELEGRAM_CHAT_ID` | Telegram chat id | 無 | 選用（需搭配 BOT_TOKEN） |
| `SCHEDULER_DATA_INTERVAL_MINUTES` | 資料更新間隔 | 1440 (24h) | 選用 |
| `SCHEDULER_ALERT_INTERVAL_MINUTES` | 警示評估間隔 | 60 | 選用 |

所有祕密（token、webhook）**絕不進版管**；僅透過環境變數或 `.env` 檔（已被 `.gitignore`）讀取。

## 離線示範模式（`app/demo/seed.py`）

**已實作**（`backend/app/demo/seed.py:1-588`）；沒有外網的環境會從每個 provider 拿到
`unavailable`，這支 CLI 把合成資料寫進既有的快取層與 store（不新增資料表），讓四個頁面離線也
能跑出真實數字：

```bash
cd apps/stock-desk/backend
uv run python -m app.demo.seed            # 產生（或更新）示範資料
uv run python -m app.demo.seed --reset    # 清除示範資料（只刪自己寫的列）
```

- 寫入三檔標的的合成日線與持倉：`2330`（一般台股）、`0050`（作為 `00631L` 標的指數的代理
  序列）、`00631L`（日度重置槓桿 ETF，NAV 由 `0050` 的單日報酬逐日複利推導）
  （`backend/app/demo/seed.py:104-180`）。
- 每一根 bar 的 `source` 固定為 `demo_synthetic`，示範持倉與警示規則的 `note` 都帶
  `[demo_synthetic]` 前綴，不可能被誤認為真實行情（`backend/app/demo/seed.py:16-20,93-100`）。
- 冪等：已存在的示範資料原封不動保留，重跑不會長出第二份（`backend/app/demo/seed.py:23-34`）。
- 寫入前會檢查目標 DB 是否已有非示範來源的同鍵日線，若有則整次執行拒絕（結束碼 1），
  不覆蓋任何資料（`backend/app/demo/seed.py:36-48`）。
- 警示事件需另外呼叫 `POST /api/alerts/evaluate`（或等排程跑）才會產生。
- 個股頁的槓桿專章（`00631L`）在示範模式下仍會回報 `insufficient_data`：其標的指數
  （臺灣50指數）目前沒有已查證的免費日線代號可查詢，系統不以 `0050` 等追蹤 ETF 代理
  （`backend/app/leverage/index_mapping.py:139-143,265-270`），這與「系統沒有指數 adapter」
  是不同的原因——見下方「資料適配狀態」。

詳細清單（資料筆數、走勢設計、不覆蓋真實資料的機制）見 `backend/README.md` 的「離線示範模式」一節。

## 資料適配狀態

| 市場/類型 | 資料來源 | 狀態 | 備註 |
| --- | --- | --- | --- |
| **台股 (TW)** | TWSE (官方) → TPEx (OTC) → FinMind (備援) | ✅ 生產就緒 | 無額度限制；24h 快取 TTL；`backend/app/api/deps.py:84-88` |
| **美股 (US)** | Alpha Vantage (主) → yfinance (備援) | ⚠️ 已接線，未經真實環境驗證 | `backend/app/api/deps.py:89-94`（ADR-0005 決策四）；需環境變數 `ALPHA_VANTAGE_API_KEY`，未設定時主來源直接跳過不發請求；兩個 adapter 的端點與回應格式皆「依公開文件撰寫、2026-07-23 未對照真實回應查證」（`backend/app/data/providers/alpha_vantage.py:16-20`） |
| **指數** | yfinance（`^NDX`／`^GSPC`／`^TWII` 等） | ⚠️ 部分已對映，未經真實環境驗證 | 17 檔槓桿 ETF 中 12 檔有對映指數代號、5 檔明確聲明 `unmapped`（含 `00631L`，見 `backend/app/leverage/index_mapping.py:168-295`）；對映表本身 `verified=False`（`index_mapping.py:60,112`） |
| **匯率 (FX)** | 台灣銀行牌告匯率（USD/TWD，即期買賣中點） | ⚠️ 已接線，未經真實環境驗證 | 僅 USD/TWD，非 USD/JPY；已接進估值層與風控上限層（`app/portfolio/valuation.py`、經 `/api/advice`、`/api/portfolio/limits` 傳入）；端點與 CSV 欄位格式未對照真實回應查證（`backend/app/data/providers/fx.py:6-25`） |
| **產業分類** | TWSE 產業別（37 類封閉清單） | ✅ 已實作（台股限定） | `Position.sector`（`backend/app/positions/models.py:73`）；清單見 `GET /api/positions/sectors`（`backend/app/api/positions.py:60-61`）；清單本身未對照官方 TWSE 資料查證（`backend/app/positions/sectors.py:17-27`）；美股不可填（`sectors.py:85-89`） |

詳見 `work/stock-desk-已知限制與後續.md`（限制清單與解法方向）。

## 文件與交付物

| 文檔 | 對象 | 內容 |
| --- | --- | --- |
| `work/stock-desk-產品說明.md` | 使用者 (CEO) | 四頁使用導覽、欄位讀法、快速啟動、常見問題 |
| `work/stock-desk-已知限制與後續.md` | 開發團隊 | 11 項已知限制、解法方向、優先序、跨團隊協作點 |
| `docs/adr/0004-stock-desk-建議引擎採規則式.md` | 技術決策 | 規則式 vs. ML 比較、架構約束、驗收標準 |
| `backend/README.md` | 開發者 | API 端點表、環境變數、資料層設計、排程 |
| 本檔 (`README.md`) | 快速上手 | 啟動指令、目錄結構、版本查證、環境配置 |

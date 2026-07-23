# ADR-0002:stock-desk 技術棧決策

- 狀態:accepted
- 日期:2026-07-23
- 決策者:CEO(指定)、tech-architect(評估確認)
- 適用範圍:僅 `product/stock-desk` 產品線(本 ADR 不存在於 main)

## Context(背景)

stock-desk 是**本機執行、單人使用**的股票訊號分析與部位決策輔助網頁:
把實際部位、市場訊號、風險上限放在同一畫面,輸出「可解釋、可反駁、附失效條件」的行動選項。
非自動下單系統、非預言機。核心限制:量化計算生態系要成熟、本機零維運、K 線圖表要專業。

## Options(選項比較)

| 層 | 採用 | 主要替代 | 取捨 |
| --- | --- | --- | --- |
| 後端 | Python 3.12 + FastAPI + uv | Node.js/Express、Django | 量化生態(pandas/numpy/sklearn、回測、指標庫)Python 最成熟;FastAPI 型別友善、async、自帶 OpenAPI;Django 對單人本機工具過重 |
| 儲存 | SQLite(WAL 模式) | PostgreSQL、DuckDB | 本機單人零維運,WAL 允許讀寫並行;PostgreSQL 需要跑服務,過度設計;DuckDB 弱在交易型寫入 |
| 前端 | Next.js(App Router)+ TypeScript strict + TailwindCSS + TanStack Query | Vite+React SPA、SvelteKit | App Router 檔案路由與 RSC 生態成熟;TanStack Query 處理快取/重抓/降級狀態;團隊(agents)對 React 生態最熟 |
| 圖表 | lightweight-charts | ECharts、Chart.js、TradingView 完整版 | 專為 K 線/金融時序設計、極輕量;通用圖表庫做 K 線又重又醜;TradingView 完整版授權與體積過重 |
| 排程 | APScheduler(與後端同進程) | cron、Celery | 本機單人夠用、零外部依賴;Celery 需要 broker,過度設計 |
| 容器化 | docker compose(前端、後端、排程三個 service) | 裸機跑 | 一鍵起停、環境一致;排程與 API 分 service 以隔離故障 |

## Decision(決策)

採用上表「採用」欄全套。依賴版本**不憑記憶**:安裝時由 devops-sre 查證當下 stable 版本,寫進 lockfile(uv.lock / package-lock.json)與 README。

## Consequences(後果)

- 好處:量化模組(訊號、回測、槓桿衰減)全在 Python 單一語言;本機 `docker compose up` 即全套可用;K 線體驗專業。
- 代價:前後端兩套語言與工具鏈,型別要在 API 邊界(OpenAPI schema)對齊;SQLite 天花板是單機——本產品定位即單機,可接受。
- 約束:
  - 所有市場資料存取走 `MarketDataProvider` 抽象介面,任何來源都是可替換 adapter。
  - 建議引擎必須是 YAML 規則式(可解釋、進 git),不得用黑箱模型直接產生建議動作。
  - ML 層只輸出機率與區間並經校準,不輸出價格點位。
  - 除非遇到硬性阻礙,不得偏離本技術棧;要偏離就開新 ADR 取代本則。

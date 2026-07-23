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
- 排程:`scheduler` service(Phase 1 為 heartbeat 佔位,之後換 APScheduler)

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
| apscheduler | 3.11.3 | PyPI(後續 Phase 進場) |
| lightweight-charts | 5.2.0 | npm(M7 進場) |

## 目錄

```
apps/stock-desk/
├── compose.yaml      # 三個 service:backend / scheduler / frontend
├── .env.example      # 環境變數範本(只放假值)
├── backend/          # FastAPI + uv(訊號、建議引擎、回測之後都在這)
└── frontend/         # Next.js App Router + TS strict + Tailwind + TanStack Query
```

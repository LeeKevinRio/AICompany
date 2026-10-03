# stock-desk frontend

Next.js (App Router) + TypeScript strict + TailwindCSS + TanStack Query。
技術棧決策見 `docs/adr/0002-stock-desk-tech-stack.md`（product/stock-desk 分支）。

## 環境

- Node v22、npm 10

## 指令

```bash
npm install          # 安裝依賴
npm run dev           # 本機開發，http://localhost:3000
npm run typecheck     # tsc --noEmit
npm run build          # production build
npm start              # 啟動 production build，port 3000
```

## 目前狀態

Phase 3 M1（部位管理）：總覽頁（`/`）串接 `/health` 與 `/api/portfolio/summary`，
庫存頁（`/positions`）列出全部持倉，可行內修改數量／平均成本／備註（`PATCH /api/positions/{id}`）、
移除、手動新增與 CSV 匯入；舊路徑 `/positions/import` 由 `next.config.ts` 轉址到 `/positions`。
首頁展開列以「到庫存修改」連到 `/positions#pos-{id}`。
`lightweight-charts` 待 M7 再加入。

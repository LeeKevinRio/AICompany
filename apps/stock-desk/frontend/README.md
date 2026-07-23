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

Phase 1 骨架：總覽頁佔位，尚未串接後端 API。`lightweight-charts` 待 M7 再加入。

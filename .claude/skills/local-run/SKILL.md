---
name: local-run
description: CEO 本機啟動/重啟兩個產品(stock-desk、groupbuy)的標準流程,保證 stock-desk 每次都用同一份資料庫。當 CEO 說「重啟」「啟動產品」「跑起來」「開起來測試」時必用:輸出下列固定指令,不得臨場改路徑。
---

# Local Run — CEO 本機啟動/重啟流程

> 目的:CEO 每次在本機啟動產品,stock-desk 的持倉/設定/警示資料**永遠是同一份**,
> 除非 CEO 明說「重置資料」。本 skill 由協調者在對話中執行:把下面的指令原樣給 CEO。

## 執行前提(每次都要遵守)

1. CEO 的環境是 **Windows PowerShell 5.1**:指令**一行一行給**,絕不使用 `&&`。
2. 路徑基準(若 CEO 說路徑不同,先問清楚再替換,不要猜):
   - 股票線 worktree:`D:\AIProject\stock-desk-test`(分支 `product/stock-desk`)
   - 網購線 worktree:`D:\AIProject\groupbuy-test`(分支 `groupbuy`)
   - 股票資料庫**固定絕對路徑**:`D:\AIProject\stock-desk-data\stock-desk.db`
3. 資料持久化的關鍵:`STOCK_DESK_DB_PATH` 一定要設成上面的絕對路徑。
   預設值是相對路徑 `./data/stock-desk.db`,從不同目錄啟動就會生出新的空資料庫——這正是要避免的事。

## 股票 Stock Desk(port:前端 3000、後端 8000)

**終端 1(後端)**——逐行執行:

```powershell
cd D:\AIProject\stock-desk-test\apps\stock-desk\backend
$env:STOCK_DESK_DB_PATH = "D:\AIProject\stock-desk-data\stock-desk.db"
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

**終端 2(前端)**——逐行執行:

```powershell
cd D:\AIProject\stock-desk-test\apps\stock-desk\frontend
npm install
npm run dev
```

開 http://localhost:3000。

Docker 替代(需 Docker Desktop 引擎已啟動、鯨魚圖示變綠):

```powershell
cd D:\AIProject\stock-desk-test\apps\stock-desk
docker compose up --build
```

Docker 模式資料存在具名 volume `stock-desk-data`,與本機模式的 `.db` 檔**不是同一份**;
兩種模式擇一固定使用,不要交替,否則會看到兩套不同的持倉。

## 網購 Groupbuy(port:5173)

```powershell
cd D:\AIProject\groupbuy-test\apps\groupbuy
npm install
npm run dev
```

開 http://localhost:5173。資料存瀏覽器 localStorage:同一台電腦同一個瀏覽器就會保留,
換瀏覽器/無痕模式看不到既有資料——這是預期行為,不是資料遺失。

## 重啟 = 重複上面的啟動指令

重啟前若舊的服務還在跑,先在該終端按 `Ctrl+C` 停掉即可。
資料不受重啟影響:stock-desk 在 `.db` 檔(或 Docker volume)、groupbuy 在 localStorage。

## 重置資料(只有 CEO 明說「重置」才執行,執行前必再確認一次)

- stock-desk(本機模式):刪除 `D:\AIProject\stock-desk-data\stock-desk.db`(連同同目錄的 `-wal`/`-shm` 檔)。
- stock-desk(Docker 模式):`docker compose down -v`(**平常重啟一律不帶 `-v`**)。
- groupbuy:瀏覽器開發者工具清除該站 localStorage,或在 app 內用清除功能(若有)。

## 更新程式碼(拉最新版,資料不動)

```powershell
cd D:\AIProject\stock-desk-test
git pull origin product/stock-desk
```

```powershell
cd D:\AIProject\groupbuy-test
git pull origin groupbuy
```

拉完後照上面的啟動流程重跑;`.db` 與 localStorage 都不會被 git 動到。

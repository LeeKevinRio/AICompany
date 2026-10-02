---
name: local-run
description: CEO 本機啟動/重啟 stock-desk 前後端的標準流程,保證每次都用同一份資料庫。當 CEO 說「重啟」「啟動產品」「跑起來」「開起來測試」時必用:輸出下列固定指令,不得臨場改路徑。
---

# local-run — CEO 本機啟動/重啟標準流程

## 適用時機

CEO 說「重啟」「啟動」「跑起來」「開起來測試」時,直接輸出本文件的固定指令。
**不得臨場改路徑或 port**;指令有變動時先改本文件再回覆。

## 一鍵腳本(建議)

在 repo 根目錄:

```bash
bash apps/stock-desk/dev-up.sh
```

腳本會依序:拉最新 code → 起後端(port 8000)→ 起前端(port 3000)。
按 `Ctrl+C` 會同時停掉前後端。

### Windows(CEO 慣用):雙擊 bat

在檔案總管雙擊 `apps\stock-desk\dev-up.bat`(或在任何目錄的命令列執行它)。
它會依序:檢查 git / uv / npm → 確認分支與工作樹乾淨 → `git pull` →
(若 8000 / 3000 被舊程序占用,詢問後結束)→ `uv sync --locked` / `npm install --no-save`(不改寫 lock 檔)→
各開一個「stock-desk 後端」「stock-desk 前端」視窗 → 後端 `/health` 通過、前端有回應後自動開瀏覽器。

- 停止:關掉兩個 stock-desk 視窗即可。
- 出錯時視窗不會自動關閉,請把視窗內容截圖給我們。
- 已追蹤檔案有未提交改動時 bat 會停止(不會自動 stash 或丟棄);未追蹤檔案不影響。
- `.gitattributes` 讓 bat 在 Windows checkout 時固定為 CRLF 換行。

## 手動指令(腳本不可用時)

### 0. 拉最新 code(repo 根目錄)

```bash
git checkout product/stock-desk
git pull origin product/stock-desk
```

### 1. 後端(終端機 1)

```bash
cd apps/stock-desk/backend
uv run uvicorn app.main:app --reload --port 8000
```

**必須從 `backend/` 目錄啟動**:資料庫走預設 `./data/stock-desk.db`,
從別的目錄啟動會生出第二顆 DB,資料就不連續了。

### 2. 前端(終端機 2)

```bash
cd apps/stock-desk/frontend
npm run dev
```

開 http://localhost:3000。

## 驗收提醒

- 拉完 code 畫面沒變:先硬重新整理(`Ctrl+Shift+R`)排除瀏覽器快取。
- 後端起不來且訊息含 `address already in use`:上一顆還活著,先關掉舊終端機或
  `lsof -ti:8000 | xargs kill`(Windows:`netstat -ano | findstr :8000` 後 `taskkill /PID <pid> /F`)。

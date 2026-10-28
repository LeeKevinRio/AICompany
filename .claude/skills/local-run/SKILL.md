---
name: local-run
description: CEO 本機啟動/重啟 stock-desk 前後端與 scheduler 的標準流程,保證每次都用同一份資料庫。當 CEO 說「重啟」「啟動產品」「跑起來」「開起來測試」時必用:輸出下列固定指令,不得臨場改路徑。
---

# local-run — CEO 本機啟動/重啟標準流程(backend + scheduler + frontend)

## 適用時機

CEO 說「重啟」「啟動」「跑起來」「開起來測試」時,直接輸出本文件的固定指令。
**不得臨場改路徑或 port**;指令有變動時先改本文件再回覆。

## 一鍵腳本(建議)

在 repo 根目錄:

```bash
bash apps/stock-desk/dev-up.sh
```

腳本會依序:拉最新 code → 起後端(port 8000)→ 等 `/health` 回 200 → 起 scheduler → 起前端(port 3000)→ 等前端有回應 →
印出 backend / scheduler / frontend 三行狀態(`[OK]` / `[FAIL]`)。按 `Ctrl+C` 會同時停掉三個程序。

- 拉 code 不再是必成功:不在 `product/stock-desk`、已追蹤檔案有未提交改動、或離線 / 無法 fast-forward 時,
  會印 `[SKIP]` 訊息並用本機現有 code 繼續(與 bat 的差異:bat 遇到未提交改動會停止,sh 只略過 pull)。
  sh 路徑**不做舊程序偵測**:啟動前請自行確認 8000 / 3000 沒被占用、沒有舊的 scheduler 在跑(`lsof -i :8000 -i :3000`、`pgrep -f app.scheduler`)。
- `apps/stock-desk/.env` 存在時,sh 同樣會 export `UV_ENV_FILE` 讓後端與 scheduler 讀取;不存在照常啟動並印一行 `[env]` 提示。
- 後端 60 秒內沒變健康、或前端 90 秒內沒回應、或程序提早結束,會印錯誤並退出(同時停掉已啟動的程序)。
- 三個程序的 log 都在同一個終端機交錯顯示。

### Windows(CEO 慣用):雙擊 bat

在檔案總管雙擊 `apps\stock-desk\dev-up.bat`(或在任何目錄的命令列執行它)。
它會依序:檢查 git / uv / npm → 確認分支與工作樹乾淨 → `git pull` →
(若 8000 / 3000 被舊程序占用、或有舊的 scheduler 還在跑,詢問後結束)→ `uv sync --locked` / `npm install --no-save`(不改寫 lock 檔)→
開「stock-desk backend」視窗 → 等後端 `/health` 通過 → 再開「stock-desk scheduler」「stock-desk frontend」視窗
(訊息為英文,避免中文在 cmd 被讀錯)→ 前端有回應後印出 backend / scheduler / frontend 三行狀態並自動開瀏覽器。

- scheduler 啟動指令為 `uv run python -m app.scheduler`,與後端同在 `backend/` 目錄(共用同一顆主 DB `./data/stock-desk.db`),
  環境變數(`STOCK_DESK_DB_PATH` 等)由父程序繼承。
- **`.env` 載入(本次起)**:若 `apps\stock-desk\.env` 存在,bat 會設定 `UV_ENV_FILE` 指向它(等同 `uv run --env-file`),
  後端與 scheduler 兩個視窗都會讀到;不存在則照常啟動並印一行 `[ENV]` 提示(uv 對不存在的檔案會直接報錯,所以必須先判斷)。
  已在系統環境變數設過的同名變數優先於 `.env`。後端與 scheduler 啟動時各印一行
  「FINMIND token／Alpha Vantage key／Discord webhook／Telegram:已設定／未設定」,只印狀態不印值;
  CEO 填了 `.env` 卻看到「未設定」時,先查檔案位置(`apps\stock-desk\.env`)與變數名稱。
  〔bat 的 `.env` 載入段落未在 Windows 實機驗證。〕
- 啟動前若偵測到舊的 scheduler(兩個同時跑會讓每則警示發兩次),會詢問是否結束舊的。
- 停止:關掉三個 stock-desk 視窗即可。
- 出錯時視窗不會自動關閉,請把視窗內容截圖給我們。
- 已追蹤檔案有未提交改動時 bat 會停止(不會自動 stash 或丟棄);未追蹤檔案不影響。
- `.gitattributes` 讓 bat 在 Windows checkout 時固定為 CRLF 換行。

## 手動指令(腳本不可用時)

順序固定:後端 → 等 `/health` 回 200 → scheduler → 前端。

### 0. 拉最新 code(repo 根目錄)

```bash
git checkout product/stock-desk
git pull origin product/stock-desk
```

### 1. 後端(終端機 1)

```bash
cd apps/stock-desk/backend
uv run --env-file ../.env uvicorn app.main:app --reload --port 8000
```

`--env-file ../.env` 讀 `apps/stock-desk/.env`;**該檔不存在時 uv 會報錯**,沒有 `.env` 就拿掉這個參數。
手動啟動不帶它就讀不到 `.env`(應用程式本身沒有 dotenv 載入)。

**必須從 `backend/` 目錄啟動**:資料庫走預設 `./data/*.db`(主 DB、市場 DB、研究 DB,見下方「資料與備份」),
從別的目錄啟動會在該目錄生出另一組 DB,資料就不連續了。

### 2. Scheduler(終端機 2,後端健康後才開)

```bash
cd apps/stock-desk/backend
uv run --env-file ../.env python -m app.scheduler   # 沒有 .env 時拿掉 --env-file ../.env
```

**同樣必須從 `backend/` 目錄啟動**,才會與後端共用同一顆 DB。同一時間只能開一個。

### 3. 前端(終端機 3)

```bash
cd apps/stock-desk/frontend
npm run dev
```

開 http://localhost:3000。

## 資料與備份(原生路徑)

資料**不是單一一顆 SQLite**。實際 grep 確認,`apps/stock-desk/backend/data/` 底下預設至少有三顆(WAL 模式):

| 檔案 | 內容 | 程式碼位置 |
| --- | --- | --- |
| `stock-desk.db` | 主 DB:持倉、設定、警示、價格快取、證券目錄等 | `backend/app/data/cache.py:28` |
| `stock-desk-market.db` | 市場 DB:全市場日線與 PIT 快照 | `backend/app/data/market_panel.py:95` |
| `stock-desk-research.db` | 研究 DB(可重建;跑過研究 CLI 才會有〔未查證〕) | `backend/app/research/sector_biased/store.py:45` |

- **備份**:先停掉三個程序(關三個視窗或 `Ctrl+C`),再把 `backend/data/` 內所有
  `*.db`、`*.db-wal`、`*.db-shm` 成套複製到帶日期的資料夾。不停機複製不保證一致(WAL 內容與各檔時間點可能對不上)。
- **還原**:先停三個程序,清掉 `backend/data/` 現有的 `*.db`、`*.db-wal`、`*.db-shm`(不要讓舊 `-wal` 留著),
  再把備份的同一套檔案複製回去,重新啟動。
- Docker 版(`docker compose`)的資料在具名 volume,不在 `backend/data/`。直接 `tar` 執行中的 WAL DB 不保證一致快照:
  先 `docker compose stop` 再備份,或改用 `sqlite3 .backup`〔容器內是否有 sqlite3 CLI 未查證〕。細節見 `apps/stock-desk/README.md`「資料存放與備份」。
- 〔以上步驟依 SQLite WAL 行為與檔案配置寫成,尚未在 CEO 的 Windows 機器上演練。〕

## 驗收提醒

- 拉完 code 畫面沒變:先硬重新整理(`Ctrl+Shift+R`)排除瀏覽器快取。
- 後端起不來且訊息含 `address already in use`:上一顆還活著,先關掉舊終端機或
  `lsof -ti:8000 | xargs kill`(Windows:`netstat -ano | findstr :8000` 後 `taskkill /PID <pid> /F`)。

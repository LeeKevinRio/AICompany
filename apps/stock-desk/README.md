# stock-desk — 股票訊號與部位決策輔助台

本機執行的**決策輔助儀表板**:把實際部位、市場訊號、風險上限放在同一畫面,
輸出可解釋、可反駁、附失效條件的行動選項。**非自動下單系統、非預言機**。

> 本工具提供的動作、股數與價位，是依固定規則與固定算式產生的操作參考。規則與價位都還沒用歷史資料驗證過，可能錯誤，照做也可能造成虧損，是否採用由你自行決定。這些參考只用日線收盤資料計算，非即時，不反映最近一次收盤之後的價格變動。

技術棧決策與取捨見 [docs/adr/0002](../../docs/adr/0002-stock-desk-tech-stack.md)。

## 快速啟動(CEO 日常:原生一鍵腳本)

CEO 日常用的是原生路徑:**Windows 雙擊 `apps\stock-desk\dev-up.bat`**(macOS／Linux 用
`bash apps/stock-desk/dev-up.sh`)。腳本會依序更新 code、起後端(:8000)、等 `/health` 通過、
起 scheduler、起前端(:3000),最後印出三行狀態。README 後段的手動指令與工程細節是給工程人員的,
不是您平常的操作;需要其中任何一步時,先告訴 coordinator。

- 前端:http://localhost:3000
- 後端 API:http://localhost:8000(健康檢查 `GET /health`)
- 排程:scheduler 是另一個程序(APScheduler:每日資料更新 + 警示評估),**關掉它的視窗就停止**。
  預測紀錄也由 scheduler 記錄:接線的程式合併、而且用 `dev-up.bat` 重新開啟之後,才會在平日(週一到週五)晚上
  22:10 與 23:10(台北時間)嘗試記錄。scheduler 關著的時候不會記錄;有沒有記下,以狀態報告為準,當晚結束時還沒有記下的,事後補不回來。
- 資料存在 `apps/stock-desk/backend/data/`(多顆 SQLite,見下方「資料存放與備份」)。
- **祕密設定(選用)**:`apps/stock-desk/.env` 裡要設定什麼,請先維持現狀,不要自己新增、修改或刪除任何設定;需要調整時,先告訴 coordinator。
  工程人員建立新環境時,用 `cp apps/stock-desk/.env.example apps/stock-desk/.env` 後填值;複製出來的 `.env` 裡不要有 `STOCK_DESK_DB_PATH` 這個名稱(見下方「環境變數與配置」)。
  bat／sh 從本次起會在啟動後端與 scheduler 時讀取這個檔(`apps/stock-desk/.env`,已被 `.gitignore`);
  沒有這個檔也照常啟動,只是 FinMind 備援與推播不會啟用,腳本會印一行提示。
  後端與 scheduler 啟動時各印一行「FINMIND token／Alpha Vantage key／Discord webhook／Telegram:已設定或未設定」,
  **只印狀態,不印值**。看到「未設定」但您明明填了,請不要自己搬動、改名或修改檔案,先告訴 coordinator。

> **選用步驟**:若要使用代號／公司名稱搜尋功能(前端 combobox),需先在**有網路的機器**
> 執行一次性目錄同步:
> ```bash
> cd apps/stock-desk/backend
> uv run python -m app.directory.sync
> ```
> 這會把 TWSE 上市清單與 TPEx 上櫃清單寫進主資料庫
> (`backend/app/directory/sync.py:1-37`)。沒有設定 `STOCK_DESK_DB_PATH` 時,主資料庫是 `backend/data/stock-desk.db`;
> 請不要為了這個指令去設定它。要執行這個指令之前,請先告訴 coordinator。本雲端開發環境對財經網域的 egress 已知被封鎖,
> 此指令必須在有網路的機器(例如 CEO 本機)執行,結果隨資料庫檔案帶到其他環境即可離線查詢
> (`backend/app/directory/sync.py:6-27`)。把別處的主資料庫檔案帶來覆蓋 CEO 機器上的主資料庫,
> 等於更換資料庫,請不要自己做,先告訴 coordinator。未同步前搜尋 API 會誠實回報
> `directory_synced: false`,不會把「還沒同步」誤顯示成「查無結果」
> (`backend/app/api/directory.py:93-102`)。

## 選用:Docker 啟動

不想裝 Python／Node、或想要開機自動重啟時才需要(`restart: unless-stopped`):

```bash
cd apps/stock-desk
cp .env.example .env        # Phase 1 可不填任何真值
docker compose up --build
```

網址與原生路徑相同(前端 :3000、後端 :8000)。`scheduler` 是獨立的 compose service。
Docker 與原生各有自己的資料(Docker 在具名 volume,原生在 `backend/data/`),兩邊**不會**共用,
切換前請先備份(見下方)。

改用 Docker 啟動時,不會記錄預測紀錄,Docker 裡的資料也是另一份資料庫,不是原生那一份。
要改用 Docker 之前,先告訴 coordinator。

## 網路暴露

後端 API **沒有任何身分驗證**,所以只開在本機迴環介面:

- `compose.yaml` 的 port 寫成 `127.0.0.1:8000:8000`、`127.0.0.1:3000:3000`,
  同一個區網的其他裝置連不到。容器內的 `--host 0.0.0.0` 是容器網路必需,
  實際對外範圍由這裡的 host 端綁定決定。CI 的 compose 檢查會擋下沒綁 `127.0.0.1` 的 port。
- 所有會改資料的請求(POST／PUT／PATCH／DELETE)都必須帶 `X-Stock-Desk-Client` header,
  否則回 403。瀏覽器不會替跨站表單或圖片連結加上自訂 header,這樣其他網頁就無法
  在你不知情時觸發緊急清倉、確認警示或匯入持倉。前端 `lib/api.ts` 已自動帶上。
- 若要用 curl 手動呼叫寫入型 API,記得加 `-H "X-Stock-Desk-Client: 1"`。
- **已知限制**:這個 header 擋得住跨站表單與圖片連結,擋不住 DNS rebinding(攻擊網域 rebind 到
  127.0.0.1 後即與本機同源,可以自己帶 header)。要防這一層需另加 Host 白名單,目前尚未實作。

## 資料存放與備份

**不是一顆 DB,而是多顆 SQLite 檔**(皆為 WAL 模式,執行中旁邊會有 `*.db-wal`、`*.db-shm`)。
以下是實際 grep 程式碼確認的清單,預設都在後端工作目錄的 `./data/` 底下:

| 檔案 | 內容 | 位置(程式碼) | 路徑環境變數 |
| --- | --- | --- | --- |
| `stock-desk.db` 主 DB | 持倉、風險設定、警示規則／事件、價格快取、證券目錄、除權息、Kelly 輸入與嘗試紀錄、API 額度帳本等 | `backend/app/data/cache.py:28` | `STOCK_DESK_DB_PATH` |
| `stock-desk-market.db` 市場 DB | 全市場日線與 point-in-time 快照(族群動能用,只增不改) | `backend/app/data/market_panel.py:95` | `STOCK_DESK_MARKET_DB_PATH` |
| `stock-desk-research.db` 研究 DB | 研究用回填資料與研究結果,可重建;API 程序不開這顆(`backend/app/research/sector_biased/store.py:3-4`) | `backend/app/research/sector_biased/store.py:45` | `STOCK_DESK_RESEARCH_DB_PATH` |

- 持倉、設定、警示等**使用者資料在主 DB**。市場 DB 的 point-in-time 快照依設計只能往前累積,
  遺失的歷史無法事後補(〔未查證:各表能否由資料源完全重建,以 ADR-0012 為準〕)。
  備份時**三顆一起備份**最單純。研究 DB 是否存在取決於有沒有跑過研究 CLI〔未查證〕。
- 主 DB 的 `STOCK_DESK_DB_PATH` 在 Docker 下由 `compose.yaml` 顯式設為 `/app/data/stock-desk.db`;
  市場 DB／研究 DB 在 compose 裡沒有另外設路徑,按預設解析成容器工作目錄 `/app` 下的
  `./data/…`,即同一個 volume `stock-desk-data` 內(依 `backend/Dockerfile` 的 `WORKDIR /app` 推論,
  〔未在實際容器內查證〕)。
- `backend` 與 `scheduler` 兩邊指向同一路徑是刻意的:排程寫入的每日資料更新、警示評估結果,
  一定要跟 API 服務讀寫同一份 DB,否則排程形同空跑。

### 原生路徑(dev-up.bat／dev-up.sh)的備份與還原

資料在 `apps/stock-desk/backend/data/`(必須從 `backend/` 目錄啟動才會是這裡)。
預測紀錄也記在主資料庫 `backend\data\stock-desk.db` 裡。

**備份**:

備份是把 `backend\data\` 裡的資料庫檔複製一份出去;原本的檔案要留在原處,不要搬動、改名或刪除。
照這一段備份時,關掉三個視窗、複製完再用 `dev-up.bat` 重新啟動,是備份步驟的一部分,不算是 coordinator 先前請您
「不要自己重新啟動任何程式」的那種情形。但 coordinator 請您暫時不要執行 `dev-up.bat` 的期間,請不要做備份。

1. **平日(週一到週五)晚上 22:00 到 23:30 之間,不要做備份。**
   這段時間是 scheduler 記錄預測紀錄的時段(見上方「快速啟動」),此時關掉視窗,該次記錄會中斷。
2. **先停掉三個程序**(關掉 stock-desk backend／scheduler／frontend 三個視窗,或在 sh 按 `Ctrl+C`),
   並確認沒有其他 stock-desk 的一鍵檔或指令正在執行(例如 `apps\stock-desk\` 裡的其他 `.bat` 檔、目錄同步)。
   不停機直接複製,WAL 內尚未寫回的資料可能沒跟上,多顆檔案之間也不是同一時間點。
3. 把 `backend/data/` 內**所有** `*.db`、`*.db-wal`、`*.db-shm` 一起複製到帶日期的資料夾,例如
   `backup-2026-10-26\`。三種副檔名要成套複製,不要只複製 `.db`。
   (程序正常關閉後 SQLite 通常會清掉 `-wal`／`-shm`,沒有就不用管;有就一起帶。)
   請用「複製」再「貼上」;不要用「剪下」,也不要用滑鼠拖曳(拖曳有可能變成把檔案搬走)。
4. **複製完請用 `dev-up.bat` 重新啟動。平日(包括週五)在 22:00 之前做的備份,請在 22:00 之前重新啟動。**
   scheduler 關著的時候不會記錄預測紀錄。平日沒能在 22:00 之前重新啟動時,請在方便時重新啟動(仍請避開 22:00 到 23:30 之間),
   並告訴 coordinator 是哪一天,不需要說明原因;那一晚的預測紀錄可能沒有記下,事後補不回來。
5. 備份資料夾請放在存放 stock-desk 程式的資料夾(含有 `apps` 資料夾的那一層,例如 `AICompany`)之外。
   備份檔裡含有您的持倉,放在裡面有被誤提交到版本控制的風險。
6. 團隊替您做的備份(包括正式登記時做的那一份),請不要刪除、搬動或改名;那是團隊留存、供日後核對用的。
7. 備份檔裡含有您的持倉資料,請自己留著,不要傳給別人或放到公開的地方。

**還原**:請不要自己還原,先告訴 coordinator。

原因:用備份檔覆蓋現在的資料庫,會把備份之後才有的內容一併蓋掉,包括預測紀錄,事後補不回來;之後也可能無法再記錄預測紀錄。
要不要還原、怎麼還原,由團隊判斷;還原會讓部分紀錄消失時,要不要這樣做,由您決定。

〔原生路徑的備份步驟為依 SQLite WAL 行為與本專案檔案配置寫成,尚未在 CEO 的 Windows 機器上演練;備份檔是否完整可用,也還沒有驗證過。〕

### Docker 路徑的備份與還原

- `backend` 與 `scheduler` 共用具名 volume `stock-desk-data`,掛在兩邊容器的 `/app/data`。
- **直接 `tar` 一個執行中的 WAL 資料庫,不保證是一致的快照**:tar 逐檔讀取的過程中,
  後端或 scheduler 仍可能寫入,`.db` 與 `-wal` 可能來自不同時間點。因此二擇一:
  1. **先停機再備份(建議)**:

     ```bash
     docker compose stop            # 在 apps/stock-desk;只停,不要 down -v
     docker run --rm -v stock-desk-data:/data -v "$PWD":/backup alpine \
       tar czf /backup/stock-desk-data-$(date +%Y%m%d).tar.gz -C /data .
     docker compose start
     ```

  2. **不停機,用 SQLite 的線上備份**(`sqlite3 <db> ".backup <file>"`),每顆 DB 各做一次。
     〔未查證:`python:3.12-slim` 映像內是否有 `sqlite3` 命令列工具,此處未實際進容器確認。〕
     沒有 CLI 時,可改用 Python 標準庫的 `sqlite3.Connection.backup()`(此 API 已在本機對 WAL 檔實測可備份,
     但「在容器內對 `/app/data` 下的檔案執行」這個組合未實測)。
- 還原:`docker compose stop` 後,用同樣的 `alpine` 容器把 tar 解回 volume(`tar xzf … -C /data`),
  並先清掉 volume 內舊的 `*.db-wal`／`*.db-shm`,理由同原生路徑;再 `docker compose start`。
  〔還原步驟未在實際 volume 上演練〕
  這是工程人員的步驟,而且只針對 Docker 的 volume:Docker 路徑不會記錄預測紀錄,
  請不要用它去覆蓋原生路徑的 `backend/data/`;需要還原任何資料時,先告訴 coordinator。
- **危險操作警告**:`docker compose down -v` 或手動 `docker volume rm stock-desk-data`
  會**永久刪除**這顆 volume,連同全部持倉、設定、警示規則與快取。一般重啟/重建
  請只用 `docker compose down`(不帶 `-v`)或 `docker compose restart`。
- 原生路徑與 Docker 路徑的資料互相獨立。要把原生的資料搬進 Docker(或反過來),
  等於更換資料庫,請不要自己做,先告訴 coordinator。把資料搬到原生路徑,
  會覆蓋原生的主資料庫,裡面的預測紀錄等內容會永久消失,之後也可能無法再記錄預測紀錄。
  工程人員的做法是把整套 `*.db` 檔放進對應位置;此搬移流程〔未查證、未演練〕。

## 本機開發(不用 Docker)

後端(Python 3.12 + uv):

```bash
cd apps/stock-desk/backend
uv sync
uv run --env-file ../.env uvicorn app.main:app --reload --port 8000   # 沒有 .env 時拿掉 --env-file ../.env
```

手動啟動 scheduler 同理(`uv run --env-file ../.env python -m app.scheduler`)。
手動啟動的 scheduler 不要和 `dev-up.bat` 混用:`dev-up.bat` 啟動時會強制結束它,若剛好正在記錄預測紀錄,該次記錄會中斷。
手動啟動時請不要設定 `STOCK_DESK_DB_PATH`。
`uv run --env-file` 對**不存在的檔案會直接報錯**(實測 uv 0.11.32:`error: No environment file found`),
所以 `dev-up.bat`／`dev-up.sh` 會先判斷檔案是否存在,再決定要不要帶(它們用等效的 `UV_ENV_FILE` 環境變數)。

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
├── dev-up.bat / dev-up.sh    # 原生一鍵啟動（CEO 日常用；會讀 .env）
├── compose.yaml              # Docker Compose 設定（選用）；三個 service: backend / scheduler / frontend
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
| `app/backtest/` | Walk-forward 回測、績效計算（Sharpe / Sortino / 最大回撤等）；內建 `ma_cross`、`rsi_reversal`、`breakout`、`five_conditions` 四種策略；`event_study.py` 為五項觀察條件的事件研究（含 CLI，方法論見 `work/stock-desk-五條件回測-方法論.md`） |
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
| `STOCK_DESK_DB_PATH` | SQLite 資料庫檔路徑 | `./data/stock-desk.db`(本機直跑);Docker 下由 `compose.yaml` 顯式設為 `/app/data/stock-desk.db`(掛在 `stock-desk-data` volume) | **原生路徑(`dev-up.bat` 或手動 `uv run`)請不要設定**:不論設在 Windows 環境變數、`.env` 或單一視窗,也不論值是什麼(包括空值),都不會記錄預測紀錄。已經設定過的話,請不要自己刪除或修改,先告訴 coordinator。Docker 由 `compose.yaml` 設定這個變數,所以 Docker 路徑不記錄預測紀錄;Docker 部署下 backend / scheduler 兩邊務必指向同一路徑,見上方「資料存放與備份」 |
| `STOCK_DESK_MARKET_DB_PATH` | 市場 DB(族群動能、PIT 快照)檔路徑 | `./data/stock-desk-market.db` | 不需要設定。API 與 scheduler 若設得不一致,市場資料庫會分成兩份。已經設定過的話,請不要自己刪除或修改,先告訴 coordinator |
| `STOCK_DESK_RESEARCH_DB_PATH` | 研究 DB 檔路徑 | `./data/stock-desk-research.db` | 不需要設定。已經設定過的話,請不要自己刪除或修改,先告訴 coordinator |
| `FINMIND_API_TOKEN` | FinMind 備援來源的 API token | 無 | 選用（未設定時 FinMind adapter 回 unavailable） |
| `ALERT_DISCORD_WEBHOOK_URL` | Discord 推播 webhook | 無 | 選用 |
| `ALERT_TELEGRAM_BOT_TOKEN` | Telegram bot token | 無 | 選用（需搭配 CHAT_ID） |
| `ALERT_TELEGRAM_CHAT_ID` | Telegram chat id | 無 | 選用（需搭配 BOT_TOKEN） |
| `SCHEDULER_DATA_INTERVAL_MINUTES` | 資料預熱改用固定間隔（分鐘）。未設定時預熱於啟動即跑一次，之後平日收盤公布後依 cron 觸發（台股 15:10／16:30／18:30 台北時間；美股紐約時間 18:30 起至 23:30 每 30 分）；值不合法時記一行 warning 並維持 cron | 無（cron） | 選用 |
| `SCHEDULER_ALERT_INTERVAL_MINUTES` | 警示評估間隔 | 60 | 選用 |

所有祕密（token、webhook）**絕不進版管**；僅透過環境變數或 `apps/stock-desk/.env`（已被 `.gitignore`）讀取。
`.env` 實際被讀到的路徑有兩條,其餘情況(例如手動 `uv run uvicorn ...` 不帶 `--env-file`)**讀不到**:

| 啟動方式 | 是否讀 `.env` | 怎麼讀 |
| --- | --- | --- |
| `dev-up.bat`／`dev-up.sh` | 是(本次起;檔案存在才讀,不存在照常啟動並印提示) | 設定 `UV_ENV_FILE`,後端與 scheduler 的 `uv run` 讀取;frontend 不讀 |
| `docker compose` | 是 | `compose.yaml` 的 `env_file`(`required: false`) |
| 手動 `uv run ...` | 只有加 `--env-file ../.env` 才讀 | 見上方「本機開發」 |

應用程式本身不含任何 dotenv 載入程式碼;同名變數若已存在於系統環境,系統環境優先〔此行為只在 Linux(uv 0.11.32)實測過,未在 Windows 實測〕。
啟動時各程序會印一行已設定／未設定狀態(不含值,`backend/app/env_status.py`)。

## 離線示範模式（`app/demo/seed.py`）

**已實作**（`backend/app/demo/seed.py:1-588`）；沒有外網的環境會從每個 provider 拿到
`unavailable`，這支 CLI 把合成資料寫進既有的快取層與 store（不新增資料表），讓四個頁面離線也
能跑出真實數字：

```bash
cd apps/stock-desk/backend
uv run python -m app.demo.seed            # 產生（或更新）示範資料
uv run python -m app.demo.seed --reset    # 清除示範資料（只刪自己寫的列）
```

**請不要在日常用 `dev-up.bat` 的機器上執行這支 CLI**：示範日線、持倉與警示規則會寫進主資料庫（沒有設定 `STOCK_DESK_DB_PATH` 時是 `backend/data/stock-desk.db`）。執行時畫面若建議設定 `STOCK_DESK_DB_PATH`，也請不要照做；需要示範資料時，先告訴 coordinator。

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

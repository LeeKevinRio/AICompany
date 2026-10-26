# stock-desk 全公司產品審視（維運視角）

- 審查者：devops-sre
- 日期：2026-10-26
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## stock-desk 維運視角審視（唯讀；未改檔、未讀 .env、未碰 *.db、未啟動產品）

靜態檢查：`bash -n dev-up.sh` 通過；`dev-up.bat` 為 CRLF，`.gitattributes` 已鎖定 `eol=crlf`。bat 的實際執行流程無法在 Linux 驗證，以下關於 bat 的結論都是讀碼推論，未實機跑過。另外 `apps/stock-desk/.env.example` 被權限規則擋下沒讀到，所以沒有核對範本內容。

### 一、評分（1～5）

| 面向 | 分數 | 依據 |
| --- | --- | --- |
| 合理性 | 3.5 | 架構判斷合理。loopback 綁定、Docker 與原生共用 DB 的防呆、兩個 scheduler 互相排除、cron 對齊收盤時間、job 例外不殺排程，都做得扎實。扣分在三處。第一，維運告警（ADR-0029）只落了 model，沒接進 scheduler，ADR 狀態仍是 proposed，所以「出錯主動通知」目前不存在。第二，CEO 實際走的 Windows 原生路徑有一個會靜默失效的設定缺口（見問題 1）。第三，備份文件只涵蓋 Docker。 |
| 好用性 | 2.5 | 雙擊 bat 到畫面大致順，但有三個摩擦：離線或 pull 失敗就整個起不來；每次啟動都跑 `uv sync` 和 `npm install`；跑的是 `next dev`（首次載入頁面要現場編譯）。出錯的主要管道是 CEO 截圖給 Claude，沒有 UI 層的維運狀態。 |
| 簡易清楚 | 2.5 | 啟動文件有三份（README、local-run skill、產品說明），內容互相矛盾。README 把 Docker 當「建議」，但 CEO 實際用 bat。README 說祕密可走 `.env`，原生路徑其實讀不到。「全部使用者資料在一顆 SQLite」是錯的，實際有兩顆。 |

### 二、最重要的 5 個問題（附證據）

**1. 原生啟動（dev-up.bat）不會讀 `.env`，填了 token 也不生效，而且沒有任何提示。**
- 後端與 scheduler 的 app 程式碼完全沒有 dotenv 載入。`grep dotenv app` 只在測試的「禁止匯入」清單出現；`pyproject.toml` 沒有 dotenv 相關依賴。
- `dev-up.bat:115,131` 與 `dev-up.sh:76,82` 啟動時沒有 `--env-file`。bat 註解 `dev-up.bat:130` 寫「環境變數由父程序繼承」，意思是只吃 Windows 系統環境變數。
- `.env` 只有 `compose.yaml:11-13` 的 `env_file` 會讀（Docker 路徑）。
- 但 `README.md:194` 寫「僅透過環境變數或 `.env` 檔讀取」，`work/stock-desk-產品說明.md:443-444` 叫人 `cp .env.example .env` 再填 token。
- 後果：CEO 照文件在 `.env` 填 FinMind token、Discord webhook 或 Alpha Vantage key，用 bat 啟動後全部無效。FinMind 會靜默回 unavailable（`README.md:187`），推播也靜默不發。這是最可能讓人以為「警示壞了」的陷阱。

**2. Scheduler 掛了或失敗，CEO 看不到。ADR-0029 的維運告警尚未接線。**
- `scheduler.py:604-613`：`_guarded` 只寫 log 和 traceback，不推播，也不留可查的狀態。
- `ops_alert/` 只有 `model.py`，`ops_alert/__init__.py:5-6` 自己寫「until then nothing here is constructed or wired into app.scheduler」。ADR-0029 狀態仍是 proposed。
- 目前 scheduler 掛了的唯一徵兆，是 bat 啟動時印一行 `[FAIL]`（`dev-up.bat:152`），之後無人檢查。
- 前端 `AlertStatusStrip.tsx:42-49` 的 `schedulerEnabled` 只是設定檔上的開關（`alerts.enabled`），不是 scheduler 的存活狀態。`/health`（`main.py:64-75`）只反映後端，不反映 scheduler。
- 後果：scheduler 窗口被關掉、當掉，或每日更新連續失敗，CEO 只會發現「資料怎麼舊了」。分不出是休市、來源掛掉，還是 scheduler 死了。
- log 只在 `cmd /k` 視窗裡，沒有檔案，視窗一關就沒了。

**3. 祕密可能洩進 log（security 已判 BLOCKING 的缺口仍在）。**
- `scheduler.py:782` 的 `main()` 仍是裸的 `logging.basicConfig(level=INFO)`。
- ADR-0029 依賴的 `app/logging_setup.py` 與 `app/push_channels.py` 在這個分支上不存在（`ls` 確認）。ADR 所述的 R-1 修補沒合進 `product/stock-desk`。
- ADR-0029 F-1／F-2 描述的風險：httpx INFO 會把完整 URL 寫進 log，Telegram URL 含 bot token，Discord webhook URL 本身就是祕密。
- CEO 要把截圖貼給 Claude 求助，截到的窗口內容可能含祕密。這是流程性風險，不只是 log 檔問題。

**4. bat 在「pull 失敗」時直接中止；sh 是略過繼續。兩者行為不一致，離線時 CEO 連看舊資料都不行。**
- `dev-up.bat:75-79`：`git pull --ff-only` 失敗就 `goto fail`。離線、網路抖動、分支分歧都會擋住。
- `dev-up.sh:70-72` 的設計是 `[SKIP]` 並用本機 code 繼續。
- `dev-up.bat:51-54` 還規定：只要有已追蹤檔案的未提交改動就停止，訊息是「tell Claude」。CEO 若不小心改到檔案就卡住。
- 每次啟動都跑 `uv sync --locked` 與 `npm install --no-save`（`dev-up.bat:95,104`），沒有「依賴沒變就跳過」。啟動慢，離線時依賴安裝也會失敗。

**5. 備份、還原與升級文件只有 Docker 版，CEO 實際用的原生路徑沒有，且「單一 DB」說法有誤。**
- `README.md:49-66` 的備份指令是 `docker run ... tar` 備份 volume。CEO 用 bat，資料在 `backend/data/`，沒有任何備份或還原說明。
- README 說「這一顆 SQLite 檔案裝了全部使用者資料」，但實際至少兩顆：`stock-desk.db`（`data/cache.py:28`）和 `stock-desk-market.db`（`data/market_panel.py:95`，族群動能用）。Docker 下兩顆都落在 volume（WORKDIR 是 `/app`），但文件沒講。
- 目錄同步（`python -m app.directory.sync`）要 CEO 手動在有網路的機器跑一次。bat 沒做這一步。沒跑時 UI 會誠實顯示 `directory_synced: false`（`README.md:31`），但新手不會知道要去補。
- 升級（`git pull`）本身簡單，bat 已自動做。風險是 pull 後沒有 DB schema 遷移或備份提示。我沒有逐一檢查各 store 的 migration 行為，不做保證。

### 三、其餘事實（回答你的四個問題）

**1. 從零到看到畫面**
- 前置：git、uv、npm（Node 22）、Python 3.12 要自己裝。bat 會檢查並印安裝連結（`dev-up.bat:17-35`）。
- 步驟：clone → 雙擊 `dev-up.bat` → 等 `uv sync` 與 `npm install` → 自動開瀏覽器。理想情況約 3 步。
- 首次最慢的是依賴下載，加上 `next dev` 的首次頁面編譯。
- 最容易卡住（依序）：
  1. 缺 git／uv／npm（有提示，OK）。
  2. 有未提交改動（bat 停止）。
  3. 離線或 pull 失敗（bat 停止）。
  4. port 8000／3000 或舊 scheduler 還在跑（bat 有偵測並詢問，做得好，`dev-up.bat:209-267`）。
  5. 設了 `.env` 卻無效（問題 1）。
  6. 沒做目錄同步所以搜尋沒有結果。
  7. 沒有資料時不知道要跑 demo seed。
- `dev-up.sh` 沒有舊程序偵測（`local-run SKILL.md:26` 已誠實寫明）。CEO 是 Windows，影響小。

**2. 每日自動更新與警示的可靠度**
- 排程設計本身可靠：
  - 每個 job 被包住，例外不會殺排程（`scheduler.py:604`）。
  - `max_instances=1`、`coalesce=True`、misfire 容忍 15 分鐘（`:159`）。
  - 啟動時補跑資料預熱與 PIT capture。
  - SIGINT／SIGTERM 乾淨關閉（`:718-778`）。
  - 台股 15:10／16:30／18:30 重試表合理。
- 結構性弱點：
  - 電腦要開機，而且 scheduler 窗口要開著。關機或睡眠期間的 cron 點會 misfire。資料預熱和 PIT capture 啟動時會補跑；`alert_evaluation` 只是 interval，沒有補跑的概念。
  - 關窗等於停止。bat 的「停止方式」是關三個窗口（`dev-up.bat:159`）。
  - 失敗時 CEO 看不見（問題 2），看得到也不一定看得懂。log 是英文技術訊息（`outcome=error`、`failed_symbols=N`、`scheduled job X failed`），沒有給 CEO 的中文摘要。
  - 美股路徑「未經真實環境驗證」（`README.md:229`），預設在 18:30 起每 30 分鐘打到 23:30。

**3. 備份、還原、升級**
- 升級：`git pull` 已被 bat 自動化，簡單。
- 備份還原：Docker 有指令，原生沒有。原生只要在停機後複製 `backend/data/*.db*`（含 `-wal`、`-shm`）即可，但沒寫在任何文件。
- 回滾：文件沒有「新版壞掉怎麼退回上一版」的說明。

**4. 讓 CEO 覺得不好用的摩擦與最小消除方式**：見下一節。

### 四、5 個具體建議

| # | 建議 | 投入 | 效益 |
| --- | --- | --- | --- |
| 1 | 讓原生啟動讀 `.env`。做法：`dev-up.bat/.sh` 用 `uv run --env-file ../.env`（uv 支援），或在後端啟動時載入。同步改 README 與 local-run 的說法。另外 scheduler 與後端啟動時各印一行「已載入 FINMIND／Discord／Telegram：是或否」，不印值。 | 小（半天，含 bat 實機測） | 高：消除最大的靜默失效陷阱 |
| 2 | 加最小可見的存活狀態。scheduler 每次 job 結束寫一筆 `last_run`／`outcome` 到 DB（或 heartbeat 檔），後端提供 `/api/ops/status`，前端首頁用一條中文紅黃綠帶顯示「每日更新：上次 18:31 成功」「排程：已停止」。這是 ADR-0029 的精簡先行版，不必等完整 sink。 | 中（1～2 天，含前端與測試） | 高：直接回答「出錯 CEO 看得到、看得懂嗎」 |
| 3 | 先補 R-1：把 `logging_setup.py` 的 redaction 合進 `product/stock-desk`，`main()` 改用 `configure_logging()`，並要求 httpx logger 降到 WARNING。順便讓 scheduler log 同時寫到 `backend/data/logs/scheduler.log`（輪替），窗口關了也查得到。 | 小到中（半天到 1 天，視 R-1 分支狀態） | 高：關掉 security 的 BLOCKING 項，也讓截圖求助安全 |
| 4 | 讓 bat 對齊 sh 的容錯。pull 失敗、離線改 `[SKIP]` 後繼續。`uv sync` 與 `npm install` 失敗時若 `.venv`／`node_modules` 已存在則警告後繼續。已追蹤檔案有改動時，改為警告並跳過 pull，不要整個停止。 | 小（2～3 小時，需 Windows 實機驗） | 中高：離線也能看盤，少很多「請把截圖給 Claude」 |
| 5 | 把原生路徑的備份與還原寫進 README 與 local-run。包含停機後複製 `backend/data/` 內的兩顆 DB（含 wal／shm）。再提供 `backup.bat`，一鍵壓縮到帶日期的資料夾。修正「單一 DB」的錯誤說法。把「首次使用清單」寫成一頁：目錄同步、demo seed 與 `--reset`、`.env`、備份。同時把 README 的「Docker 建議」改成「CEO 日常用 bat，Docker 為選用」，消除三份文件的矛盾。 | 小（半天，純文件加一支 bat） | 中高：補上資料遺失的最大風險，並降低認知負擔 |

### 五、需要 CEO 決策的事項

1. **日常運行方式**：維持原生 bat（需開機、需開著三個窗口），還是改用 Docker（`restart: unless-stopped`，開機自動起，可靠度較高，但要裝 Docker Desktop，且 Windows 上有額外資源與啟動時間成本）。這決定建議 1、2、4 的優先序。
2. **ADR-0029 維運告警**：要推進到完整版（Discord 或 Telegram 主動通知「排程失敗」），還是先做建議 2 的畫面狀態帶就好？完整版需要 CEO 核可 ADR，且依賴 R-1 先合併。CEO 在主機上清查既有 log 有沒有真實祕密並輪換，也還沒做（ADR-0029 依賴段落）。
3. **R-1 合併時程**：建議 3 需要確認 `fix/stock-desk-r1-secret-redaction` 分支的現況與誰來合併。
4. **離線時的行為**：同意「pull 失敗就略過、用本機 code 繼續」嗎？風險是 CEO 可能不知道自己跑的是舊版。我建議預設略過，並在狀態列顯示版本與上次 pull 時間。
5. **備份頻率與位置**：要不要在每次 bat 啟動時自動做一次帶日期的備份（保留最近 N 份）？成本是啟動多幾秒、多佔一點磁碟。備份放本機還是雲端同步資料夾，由 CEO 決定。

### 六、不確定與未驗證
- bat 的實際行為（`choice`、`netstat` 解析、`Get-CimInstance` 偵測 scheduler、關窗後子程序是否收乾淨）未在 Windows 實機驗證。
- 關窗時 scheduler 的 `wait=True` 是否會被 CTRL_CLOSE 的短時限截斷，我沒有證據，只是推論有此可能。SQLite WAL 通常可承受，但未驗證。
- Docker 路徑沒有實際 build。`backend/Dockerfile:5` 用 `ghcr.io/astral-sh/uv:latest`，版本沒釘死，違反「版本需查證」原則，建議之後釘版。
- `.env.example` 內容未讀（被權限擋下）。
- CI 查看結果：`.github/workflows/stock-desk.yml` 涵蓋後端 ruff／mypy／pytest（覆蓋率 90%）、compose 驗證與共用 DB 守衛、前端 typecheck／vitest／build，沒有 bat 或 sh 的測試。`validate.yml` 屬員工線。

### 相關檔案（絕對路徑）
- /home/user/AICompany/apps/stock-desk/README.md
- /home/user/AICompany/apps/stock-desk/dev-up.bat
- /home/user/AICompany/apps/stock-desk/dev-up.sh
- /home/user/AICompany/apps/stock-desk/compose.yaml
- /home/user/AICompany/apps/stock-desk/backend/app/scheduler.py
- /home/user/AICompany/apps/stock-desk/backend/app/ops_alert/__init__.py
- /home/user/AICompany/apps/stock-desk/backend/app/main.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/cache.py
- /home/user/AICompany/apps/stock-desk/backend/app/data/market_panel.py
- /home/user/AICompany/apps/stock-desk/frontend/app/components/AlertStatusStrip.tsx
- /home/user/AICompany/.claude/skills/local-run/SKILL.md
- /home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md
- /home/user/AICompany/.github/workflows/stock-desk.yml

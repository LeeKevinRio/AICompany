# export 寫法讓登記預檢漏網、警示手冊維護人、§4 與 ADR-0029、QuickEdit

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 報告：`export` 寫法漏網、警示手冊維護人、§4 與 ADR-0029、QuickEdit（2026-11-21）

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有讀任何 `.env*`，沒有碰 `backend/data/`，也沒有執行 git 或 uv。

## 本次結論

**第一件（最重要）**
- 【事實】漏洞存在：`claims.py` 第 291 行 `_ENV_FILE_KEY = ^\s*STOCK_DESK_DB_PATH\s*=`，比對不到 `export STOCK_DESK_DB_PATH=`。
- 【事實】同一個 regex 還有三份，都在 `scripts/`：
  - `cg2_register.py` 第 103 行，登記一鍵檔的 R-3；
  - `pipeline_acceptance_real.py` 第 289 行；
  - `r2_first_run.py` 第 35 行。
- 【推論】大小寫不同的鍵名在 Windows 上也會漏網，例如 `stock_desk_db_path=`。
- 【裁示】採 (甲)：登記前，在 CG-2 登記分支修 `claims.py` 與 `cg2_register.py` 兩處 regex。
  - 這是讓實作符合 ADR-0030 補充四第 2 點「`.env` 沒有設」的原意，不需要新的 ADR 補充。
  - 依補充六第 6 點 (d)，這個修改是允許的差異，**真實資料管線驗收不會失效**。驗收預期的 `code_digest=a15e910c…7461` 也不會變。
  - (乙) 沒有可以執行的路徑，(丙) 沒有保護效果，兩者都否決。
- 【裁示】驗收照常等待，不用暫停。CG-2 PR 合併與預檢通知，要等修正經 qa PASS 之後才進行。
- 沒有必須由 CEO 決定的事。

**第二件**
- 【裁示】警示評估手冊比照族群手冊，「不維護」，不指定維護人。所以 RC-474 對這份文件沒有工程改寫的例外。

**第三件**
- 【事實】ADR-0029 沒有涵蓋 §4。它只涵蓋 `forecast_record` 的維運告警，事件是封閉列舉，裡面沒有警示評估的載入失敗。
- 【推論】只有選項 B 的「通道要不要沿用」一點，ADR-0029 的原則間接回答了。
- 不擋任何事。

**第四件**
- 【推論，可信度中高，限傳統 conhost】QuickEdit 開著時，在視窗內點選或選取文字，會讓寫入該主控台的程序卡住。scheduler 的 log 是寫到主控台的，所以排程可能被延後，甚至錯過。
- 【建議】列入 devops-sre 的 Windows 實機驗證清單。
- 【裁示】不要在 `dev-up.bat` 裡關 QuickEdit。這類改法會新增指令行，依本日的解釋會觸發 ADR-0012 補充一 (b)(iii)，而且要改使用者的機碼。
- 【事實】R 系列請 CEO 看的三行和 `Done.`，都在 `dev-up.bat` 主視窗，不是 scheduler 視窗。
- 【事實】另有 RC-320 第三條門檻，引導 CEO 去看 scheduler 視窗，要送風控重看。

---

## 各部門回報（tech-architect）

### 第一件：`export STOCK_DESK_DB_PATH=` 讓登記預檢漏網

**1. 事實確認**

`claims.py`（接線版 worktree）：
- 【事實】第 291 行是上述 regex；第 385～390 行 `env_file_sets_db_path` 以 `utf-8-sig`、`errors="ignore"` 開檔後逐行 `match`；第 405～406 行對 `<backend>/../.env` 呼叫它。
- 【事實】測試 `test_4_the_env_file_names_a_database`（`tests/test_forecast_claims_bootstrap.py` 第 324～333 行）只參數化三種寫法：`KEY=x.db`、`  KEY = `、BOM 開頭。
- 【事實】反例測試（第 336～340 行）確認 `# KEY=` 與 `X_STOCK_DESK_DB_PATH=1` 不會被拒絕。
- 【事實】沒有任何測試涵蓋 `export`。

登記一鍵檔：
- 【事實】`cg2-preflight.bat` 與 `cg2-register.bat` 第 11 行都是 `set "UV_ENV_FILE="`，所以登記程序的環境不含 `.env`。這時 `.env` 只能靠上面那個 regex 檢查。
- 【事實】`dev-up.bat` 第 94～96 行設 `UV_ENV_FILE=apps\stock-desk\.env`，第 166 行啟動的 scheduler 繼承它。scheduler 第 699～700 行用 `in os.environ` 判斷，看到的是 uv 實際載入的結果。
- 結論：scheduler 端的判斷本身沒錯，落差只在登記端。

舊紀錄：
- 【事實】qa 在 2026-11-16 已記過這一點（`work/reviews/2026-11-16-CG2登記PR審查-qa-reviewer.md` 第 62 行），當時列為「低／凍結後待辦」。
- 【推論】當時 scheduler 還不會因為變數有設就跳過。這條是 11-19 補充九第 3 點才加的，所以嚴重度要上修。
- 【事實】我 11-21 的裁示有一句要更正：「登記成功本身，就證明登記當時兩處都沒有設」（`work/reviews/2026-11-21-心跳確認書審查與attestation落差裁示與退役測試對應-tech-architect.md` 第 110 行）。
  - 修正落地之前，這句只能讀成「環境變數沒有設，而且 `.env` 裡沒有 regex 認得出來的寫法」。
  - 登記紀錄裡如果要寫這個註記，以修正之後的版本為準。

**其他寫法的盤點**

uv 的 dotenv 解析規則我沒有查證。【推論】我記得 uv 用 `dotenvy` 一類的解析器，但版本和規則都沒有核實。

| 寫法 | uv 會不會載入 | 現行 regex | 方向 |
|---|---|---|---|
| `export KEY=` | 會（【事實】dev-lead 在 Linux 用 uv 0.11.32 實測） | 抓不到 | **漏網** |
| `export<TAB>KEY=`、`export` 後接多個空白 | 【推論】會 | 抓不到 | **漏網** |
| 鍵名小寫或大小寫混合（`stock_desk_db_path=`） | 【推論】會載入成該名稱的變數；Windows 的環境變數名稱不分大小寫，Python 在 Windows 上把 `os.environ` 的鍵轉成大寫，所以 scheduler 會判定「有設」 | 抓不到（regex 分大小寫） | **Windows 上漏網** |
| `EXPORT KEY=` | 不確定（可能解析失敗） | 抓不到 | 可能漏網 |
| 前導空白、`=` 前後空白、空值、BOM | 會 | 抓得到（已有測試） | 一致 |
| 引號、行尾註解 | 和判斷無關：regex 只看到 `=` 為止 | — | 一致 |
| 多行引號值裡出現該鍵、只有 CR 的換行、Unicode 空白 | 【推論】uv 可能不載入 | 可能誤判為有設 | 過嚴（fail-closed，安全） |
| 帶引號的鍵名、一行多個賦值 | 【推論】多半解析失敗 | 抓不到 | 沒有查證 |
| UTF-16 編碼的 `.env` | 【推論】uv 解析失敗、不載入 | 抓不到 | 【推論】不構成落差 |

**2. 嚴重度、版本與處置**

**嚴重度：中（【推論】機率低、後果重）**
- 機率：CEO 用 Windows，`export` 是 Unix shell 的習慣寫法；`.env` 應該是照 `.env.example` 建的，而範本內容團隊讀不到。RC-482 的問句若問到，可以涵蓋範本這一端，但涵蓋不到 CEO 自己改過的 `.env`。
- 後果（推論）：
  - 預檢通過，主 DB 也確實在預設位置時，登記會寫進預設位置的那個檔。
  - 但 `dev-up.bat` 啟動的 backend 和 scheduler 會跟著 `.env` 走：backend 用變數指的檔；scheduler 每晚記一行 WARNING 後跳過，不記錄。
  - 要等接線後的第一份狀態報告或心跳才會發現。這段期間的前瞻紀錄補不回來，登記紀錄裡的證據句也會不實。
  - 不會寫錯資料庫：scheduler 那一端是 fail-closed。

**登記會用到哪一版 `claims.py`，驗收的 `code_digest` 涵蓋哪一版**

`a15e910c…7461` 涵蓋的是 product 上沒有 bootstrap 的版本：
- 【事實】這是前置 PR 合併進 product 時（M = `8b22c114`）算出的值。追蹤清單第 566、567 行寫明，CEO 的驗收回貼應等於它，而且當時 `claims.py` 零差異。
- 【事實】product checkout 的 `claims.py` 裡沒有 `_ENV_FILE_KEY`，也沒有 `bootstrap`，只有 `production_path_refusal`（第 146 行）。
- 所以驗收的 `code_digest` 涵蓋的是「還沒有 bootstrap 和這段 regex」的版本。

登記實際用的是 CG-2 PR 合併時的版本：
- 【事實】`bootstrap`、`env_file_sets_db_path`、`_ENV_FILE_KEY` 都是 CG-2 登記分支第二段新增的（`2026-11-16-CG2登記PR第二段交件-dev-lead.md` 第 39 行）。
- 【事實】依 R-1，`HEAD` 和 CG-2 合併 commit 之間 `app/` 不得有差異，一鍵檔也釘了 `app/` 的 tree id。
- 所以登記時執行的，就是 CG-2 PR（目前 head `9d5bbf48`）裡的 `claims.py`。

接線版與 `9d5bbf48` 的 `claims.py` 是否相同：
- 【推論，證據強，沒有用 git 驗證】相同。
- 依據：歷次接線交件與複審都寫明，相對 `9d5bbf48`，`app/` 只動了 `app/forecast` 四檔加 `scheduler.py`。四檔依各輪紀錄是 `recorder.py`、`store.py`、`report.py`、`__init__.py`。補充九第 2 點也寫明「claims.py 的程式行為不變」。

CG-2 PR 是否還沒合併：
- 【推論】還沒合併。依據有兩點：順序是驗收 → CG-2 合併 → 登記，而驗收還沒貼回；product checkout 也沒有 bootstrap。
- 沒有用 `ls-remote` 查證。

**方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **(甲) 登記前修 `claims.py` 與 `cg2_register.py` 的 regex（採用）** | 登記端的判斷和 uv 實際載入的範圍一致，符合補充四第 2 點的原意；依補充六第 6 點 (d) 屬允許差異（新增的頂層定義），驗收不用重跑；驗收的 `code_digest` 不受影響；CEO 看得到的字面零變動 | CG-2 head 改變：`app/` tree id 要重釘，M-9 要重做（qa、CI、`verify --all`，風控確認 M-2、M-3、M-6 不受影響）；接線分支要再 merge，接線版 `code_digest` `731e09f4…0c2b` 再次作廢、重新記錄 | 驗收先貼回時，CG-2 合併會晚幾天；改動本身極小 |
| (乙) 不改程式，另外確認 CEO 的 `.env` 沒有 `export` 寫法 | 不動已審的 head | 沒有可執行的路徑：不得讀 CEO 的 `.env`，不得叫 CEO 查設定（RC-432 (c)），憑記憶的回答不能當證據（RC-471）；RC-482 只涵蓋範本 | 等於接受漏洞 |
| (丙) 登記後、接線前修 | 不影響登記 | 對登記沒有任何保護（bootstrap 只執行一次，登記後再執行要先修訂 ADR，補充九第 2 點）；只多一次 `code_digest` 變動 | 漏洞照樣在登記時生效 |
| (丁-1) 預檢改成實際讓 uv 載入 `.env`，再看環境變數 | 判斷依據就是 uv 本身 | 會把祕密（token、webhook）載入登記程序和 bootstrap 子程序；兩支 `.bat` 是已經審過、CEO 看得到的檔，要改；和「只掃鍵名」的設計相反 | 安全面倒退。否決 |
| (丁-2) 接受殘餘風險，靠狀態報告或心跳事後發現 | 零工作 | 發現時前瞻紀錄已經缺了；登記紀錄的證據句不實 | 否決 |

**對實作的約束（甲；逐條可查）**
1. 只改兩處：`app/forecast/claims.py` 的 `_ENV_FILE_KEY`，和 `scripts/cg2_register.py` 的 `ENV_KEY_PATTERN`。兩者的 pattern 和 flags 要完全相同，並加一個測試斷言兩者相等。
2. 新 pattern 至少要比對到：
   - `export` 後接一個以上的空白（含 tab）；
   - 鍵名不分大小寫；`EXPORT` 也算；
   - 前導空白、`=` 前空白、空值、BOM（既有的涵蓋不得縮小）。
   - dev-lead 可以再放寬到 token 層級，代價是誤判的機會變多。
3. 新 pattern 不得比對到：
   - 第一個非空白字元是 `#` 的行；
   - `X_STOCK_DESK_DB_PATH=`；
   - `STOCK_DESK_DB_PATH_X=`（新增反例測試）。
4. 只找鍵名，不保留、不輸出值。拒絕字句、結束碼、STOP 代號一律不變，CEO 看得到的字面零變動。`verify_cg2_instruction.py` 要能通過。
5. `claims.py` 除了 `_ENV_FILE_KEY`（必要時加上它的註解或 docstring）之外，所有頂層定義都和 `9d5bbf48` 的 AST 相同。在 `git_head` 已存在、由 harness 遞移呼叫的函式（`register`、`production_path_refusal` 等）也要 AST 相同（補充六第 6 點 (d)）。
6. 以下零差異：
   - `scripts/pipeline_acceptance_real.py`（它的同一個漏洞**不得**修，(d) 要求零差異，而且它要退役）；
   - `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`、`uv.lock`；
   - 兩支 cg2 `.bat`、`work/dispatch` 的登記操作說明、`tests/test_cg2_registration_values.py`；
   - `app/dirdef/`、規則 YAML。
7. 兩個模組都要有參數化的正例：`export`＋空白、`export`＋tab、小寫、大小寫混合、`EXPORT`。也都要有第 3 點的反例。
8. 重釘 `cg2_register.py` 的 `app/` tree id 常數和對應的 values 測試；新的 CG-2 head `code_digest` 寫進交件。M-2～M-5 的 `REAL_PINS` 不得變動。
9. 證據：dev-lead 用 scratchpad 的假 env 檔，重跑一次 uv 探測，涵蓋第 2、3 點與上面盤點表的各種寫法，逐項列出「uv 有沒有載入」和「regex 有沒有比對到」。必須成立的是「有載入就一定比對到」。Windows 上的同一組探測，交 devops-sre 實機驗證，不在 CEO 的電腦上做。
10. 在 `feat/nm5-cg2-registration` 以 fast-forward 推送，不 rebase、不 force push。之後接線分支 merge 新的 head，由 coordinator 作廢 `731e09f4…0c2b` 並記下新值。
11. `r2_first_run.py` 不在這次範圍內，另外列追蹤。

**是否需要 CEO 決定：不需要。**
- 這是讓實作符合已有的 ADR，不改決策、不改 CEO 看得到的內容。
- 若有人提議不修就登記，要先回到 tech-architect 重新裁示，coordinator 不得自行接受這個殘餘風險。

**3. 要不要暫停**
- 【裁示】真實資料管線驗收：不暫停，照常等貼回、照常判讀。
  - 理由：驗收在 product 上執行，那一版沒有 bootstrap；這次修正落在補充六第 6 點 (d) 的允許差異之內。
- 【裁示】登記：預檢還沒有通知，所以不需要任何對 CEO 的字面。CG-2 PR 的合併與預檢通知，排在修正經 qa PASS、CI 綠燈之後。
- 【推論】修正可以和等待驗收同時進行。驗收比修正晚貼回的話，實際不會延後。

### 第二件：警示評估載入失敗檢查手冊的維護人

- 【裁示】不維護，比照族群手冊，性質是「2026-10-07 的工程檢查紀錄」。
- 理由：
  - 唯一的讀者已經改成工程同事，而工程同事可以直接讀程式。
  - 這份手冊重抄了 log 字面（`engine.py`、`scheduler.py`），沒有任何測試釘住，指定維護人也沒有觸發更新的機制，等於一個空的承諾。
  - 維護會讓 RC-474 的例外條款長期產生審查負擔。
- 日後需要「警示評估排障」文件時，另寫一份團隊文件，不復用這份。
- 對 RC-474 的影響：這份文件和族群手冊一樣，沒有工程改寫的例外。
- 檔頭目前寫「供團隊參考」，仍然成立。要不要補「之後不會再更新」由風控決定；要補的話，要在 RC-474 的單項確認之前定案，否則要重審。

### 第三件：手冊 §4 是否已被 ADR-0029 涵蓋（內部紀錄）

- 【事實】沒有涵蓋。
  - ADR-0029 的範圍是 N-23 (1)，也就是預測紀錄帳的維運告警。
  - 事件是封閉列舉（E-1～E-3d 加上 selftest），E-3b 只對 `forecast_record` 推播。
  - `failed_symbols` 不在其中。
  - ADR-0029 目前是 proposed，待 CEO 事項 #43。
- 【推論】部分相關：
  - 選項 B 寫的「沿用警示通知通道」，和 ADR-0029 的原則相衝突。ADR-0029 規定維運告警不得用 `AlertEvent`，不得共用使用者的開關與冷卻，傳輸則經 `app/push_channels.py`。
  - 所以 B 若要做，應該擴充 ADR-0029 的列舉（它還是 proposed，可以原地修訂），或另立新 ADR，不能照手冊的寫法做。
  - 選項 C（外部心跳）不在 ADR-0029。ADR-0030 的心跳是狀態報告的貼回，是另一回事。
  - 選項 A 已經被就地警示 A-5 排除在 CEO 操作之外。
- 【建議】追蹤清單記一列：「警示評估載入失敗的自動告警：未立案；日後立案時，走 ADR-0029 修訂或新 ADR」。目前沒有待 CEO 決定的事。

### 第四件：Windows 主控台 QuickEdit

**(a) 依據與可信度**
- 【推論，可信度中高】傳統 conhost 開著 QuickEdit 時，在視窗內按下滑鼠左鍵就會進入選取模式（標題列會顯示 Select）。直到按 Enter、Esc 或右鍵之前，寫入這個主控台的程序都會卡在寫入呼叫上。這是常見的已知行為。
  - Ctrl+F 尋找會反白相符的文字，【推論】可能同樣進入選取模式。
  - Ctrl+S 也會暫停輸出。
  - 只用滑鼠滾輪捲動，【推論】不會。
  - 點一下還沒有焦點的視窗，只是讓它取得焦點時，會不會開始選取：不確定。
- 【推論】Windows Terminal 選取時不會擋住輸出。CEO 的 `cmd /k` 視窗由哪一個主控台程式承載，要看 Windows 版本和預設終端機設定，沒有查證。

**(b) 對 `forecast_record` 的影響（推論）**
- 【事實】相關設定：
  - `BlockingScheduler`（`scheduler.py` 第 839 行）；
  - `forecast_record` 是 `max_instances=1`、`coalesce=True`，沒有設 `misfire_grace_time`（第 928～936 行）；
  - 程式第 212～213 行的註解自己寫著「沒有明示寬限時，錯過超過 1 秒就不補」。
  - APScheduler 3.11.3 實際的預設值，我沒有查證。
- 【推論】logging 的 handler 鎖是共用的，一個執行緒卡在主控台寫入，其他要寫 log 的執行緒都會一起卡住。可能出現的情形：
  - 工作執行緒卡在寫 log：這次執行被延後到解除選取之後。如果卡在寫入交易中間，其他寫入者會遇到 `database is locked`；這時若關掉視窗，會留下沒有 end 列的執行。
  - 主迴圈在寫 WARNING 時卡住（例如前一次警示評估還卡著，記「已達最大執行數」的那一行）：所有排程都停住。解除時已經超過寬限，22:10 和 23:10 都會被判為錯過，那一晚沒有記錄。
  - 啟動補跑只在啟動時發生，幫不上忙。E-3b 的 listener 還沒有實作。
- 【推論】選取可能無限期地停在那裡（點了之後就離開），所以最壞的情形是好幾晚都沒有記錄，要靠狀態報告或心跳才會發現。

**(c) 驗證清單與 `dev-up.bat`**
- 【建議】列入 devops-sre 的 Windows 實機驗證清單：
  - 用測試機，不用 CEO 的電腦；用暫存 DB 和短間隔的假 job，不用主 DB。
  - 分別測 conhost 和 Windows Terminal。
  - 逐項測：點選取、Ctrl+F、Ctrl+S、滾輪、點擊取得焦點。
  - 每一項記錄三件事：輸出有沒有停、job 有沒有延後、有沒有被判為錯過。
- 【裁示】依本日的解釋，在 `dev-up.bat` 加任何會關 QuickEdit 的指令（`reg add`、改寫第 166 行的 `start` 指令或它的參數、加外層包裝），都是新增或改動指令行，不屬於「只改 `echo`」，**會觸發 (iii)**。
  - `reg add HKCU\Console` 還會長期改動使用者的主控台設定。
  - 所以不採 `dev-up.bat` 這條路。
- 【建議】驗證成立的話，修在 scheduler 程序內。兩個方向，由 dev-lead 與 devops-sre 提案，送 tech-architect 審：
  - ① 啟動時以 `SetConsoleMode` 關掉自己主控台的 QuickEdit。改動最小，但擋不住從選單手動「標記」和 Ctrl+S。
  - ② log 改成不阻塞（`QueueHandler`）。從根本切斷 job 和主控台的關係，但要確認 R-1 的 `SecretRedactionFilter` 掛的位置沒有被繞過。
  - 我傾向 ②。
  - `scheduler.py` 不在 `code_digest` 的涵蓋範圍，但改了會讓登記一鍵檔釘住的 tree id 失效，所以時點最早在登記之後。CEO 看得到的行為改變（例如不能再點選取文字），要送風控知悉。

**(d) CEO 文字**
- 【事實】`dev-up.bat` 第 185～193 行，三行狀態和 `Done.` 都印在使用者雙擊的主視窗。scheduler 是第 166 行用 `start` 另開的主控台。
- 【推論】在主視窗選取文字是無害的：`Done.` 之後主視窗停在第 197 行的 `pause`；就算更早選取，也只會讓主視窗本身變慢，不影響另一個主控台。
- 有兩處和 scheduler 視窗有關：
  - 【事實】RC-320 第三條門檻（「scheduler 視窗的 `forecast_record:` 行連續 2 個平日以上都出現，就告訴 coordinator」，`2026-11-20-兩份CEO文件判定RC313至RC324-風控.md` 第 88 行），會引導 CEO 去看 scheduler 視窗，可能點進去或選取文字。
  - 【事實】`dev-up.bat` 自己的 `[FAIL] scheduler … check the 'stock-desk scheduler' window` 也指向 scheduler 視窗。
- 【建議】查證之前，任何 CEO 文字都不要讓 CEO 在 scheduler 視窗裡點選、選取或複製、搜尋、捲動。RC-320 那條和 S-b 的「截圖也可以」要怎麼處理，由風控決定。

---

## 驗證

**讀過的檔**
- 接線版 `claims.py` 第 280～311、340～459 行；`cg2_register.py`、`pipeline_acceptance_real.py`、`r2_first_run.py` 的 regex 段落；`tests/test_forecast_claims_bootstrap.py` 的相關段落。
- 三支 cg2 和驗收 `.bat` 的 `UV_ENV_FILE` 行；`dev-up.bat` 第 160～209 行；`scheduler.py` 第 205～224、837～955 行。
- product 的 `claims.py`（Grep）。
- ADR-0030 第 480～539、650～671 行；ADR-0029 第 1～70 行加搜尋片段。
- 警示手冊全文；RC-469～RC-486 判定第 1～678 行；dev-lead 本日核對全文；我本日的驗收一鍵檔裁示全文。
- 追蹤清單第 555～567 行；接線各輪交件與複審的搜尋片段。

**沒有查證的事**
- uv 的 dotenv 解析規則和版本差異（盤點表裡除了 dev-lead 實測的 `export` 以外都是推論）；Windows 上的大小寫行為；CEO 的 uv 版本。
- `9d5bbf48` 和接線版的 `claims.py` 是否逐位元組相同（沒有執行 git）。
- CG-2 PR 是否還沒合併，以及遠端各分支目前的 head。
- RC-482 有沒有送出、有沒有回答；RC-320 那份 B 文件有沒有送出。
- 驗收那一端同一個漏洞會不會影響「harness 通過」的判讀。【推論】不會，因為通過條件看的是管線機制。
- QuickEdit 的全部行為、CEO 用的是哪一種主控台、APScheduler 3.11.3 的 `misfire_grace_time` 預設值；以上都沒有在 Windows 上實測。

## 下一步

**要送風控的**
- 第一件：
  - 知悉 (甲) 的裁示，以及「CEO 看得到的字面零變動」這個約束。
  - 決定 M-9 裡 M-2、M-3、M-6 要不要在新 head 重新核對。
  - 知悉我 11-21 那句證據句的更正。
- 第二件：警示手冊「不維護」；檔頭要不要補「之後不會再更新」（在 RC-474 單項確認之前定案）。
- 第三件：知悉 §4 沒有被 ADR-0029 涵蓋（內部紀錄）。
- 第四件：
  - RC-320 第三條門檻，與 S-b「截圖也可以」，在查證之前怎麼處理；
  - `dev-up.bat` 的 `[FAIL] scheduler … check the … window` 字面要不要列入日後改字；
  - 日後 scheduler 程序內修正造成的行為改變，送風控知悉。

**要 dev-lead 做的**
- 依約束 1～10，在 `feat/nm5-cg2-registration` 修正：附 uv 探測證據、新的 tree id、新的 CG-2 `code_digest`，交 qa（有 Codex 就用）。之後 merge 進接線分支。
- 第四件驗證成立後，和 devops-sre 提出方向 ① 或 ②，送 tech-architect 審（時點在登記之後）。

**要 devops-sre 做的**
- 第一件：在 Windows 實機上（不在 CEO 的電腦上）用同一組寫法重跑 uv 探測。
- 第四件：QuickEdit 列入 Windows 實機驗證清單，照 (c) 的項目記錄結果。
- 追蹤：`r2_first_run.py` 的同一個漏洞，在總閘門之前評估要不要修（不屬 ADR-0030）。

**要 coordinator 做的**
- 驗收照常等待。CG-2 合併與預檢通知排在修正 PASS 之後。
- 追蹤清單記下：本件的裁示、證據句的更正、接線版 `code_digest` 屆時再次作廢、§4 未立案。

**有沒有必須由 CEO 決定的事：沒有。**

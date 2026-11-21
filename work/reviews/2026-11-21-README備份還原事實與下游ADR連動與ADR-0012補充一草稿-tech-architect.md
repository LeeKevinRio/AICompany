# README 備份還原事實、下游 ADR 連動（RC-435、RC-436）與 ADR-0012 補充一草稿

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：RC-434～RC-436 的事實與裁示、ADR-0012 補充一草稿

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有讀 `.env` 或 `.env.example`，沒有碰 `apps/stock-desk/backend/data/`。程式行號以接線版工作樹 `agent-a352324c9d164984b` 為準；族群動能相關程式（`sector_attestation.py`、`gate.py` 等）用的是 product 版 `apps/stock-desk/backend/`，另有註明的除外。本報告不含任何面向 CEO 的字面。

---

# A. RC-434：README 的備份與還原

## 本次結論

1. **備份做法本身和預測紀錄相容。** 只是把檔案複製出去，不改主 DB，不屬於 F-8。代價有兩個，都來自「先關掉 scheduler」：
   - 關著的那段時間不會記錄；
   - 剛好在執行中關掉，會留下一筆沒有 end 列的執行。
   （tech-architect 建議）
   - 時段：要避開平日 22:00～23:30，和 R1／R2／R3 同一段。
   - 時間長短：更要緊的是「關掉之後，當晚 24:00（台北）之前用 `dev-up.bat` 重新啟動」。README 的備份段現在**沒有寫要重新啟動**。
2. **還原：帳本建立之後，屬於 F-8 與補充九第 2 點。** CEO 不能自己做，README 第 102～107 行要改。
   - 沒有現成的「只還原持倉與設定、不動帳本」的工具。
   - ADR-0026 的還原點是這個方向的設計，但還是 proposed、沒有實作，而且只涵蓋持倉。
3. **README 第 26、280 行「系統環境優先於 `.env`」：部分查證。** 有 devops-sre 2026-10-26 在 Linux、uv 0.11.32 上的實測紀錄；Windows 沒有實測，uv 官方文件與原始碼我沒有讀到。
   - 這一點對預測紀錄沒有影響：`STOCK_DESK_DB_PATH` 不論設在 Windows 層還是 `.env`，只要存在，記錄就被拒絕，誰優先都一樣。
   - 第 261 行把它寫成「選用」，要改。另外找到 7 處與預測紀錄條件衝突或相關的段落（第 3 點）。

## 各部門回報（tech-architect）

### 1. 備份（README 第 94～100 行）

**(a) 關掉 scheduler 視窗對預測紀錄的影響**
- `forecast_record` 只在週一至週五 22:10、23:10（台北）執行（`scheduler.py` 712～724 行）。scheduler 關著時，這兩次都不會發生。
- 重新啟動後的啟動補跑在啟動後 3 分鐘（`scheduler.py` 926 行）。「啟動時刻加 3 分鐘」若落在平日 [13:30, 22:10)，就不設補跑（補充十第 3 點；`scheduler.py` 727～741 行）。實際的情形如下：

| 何時關、何時重開 | 結果 |
|---|---|
| 22:10 之前關，22:10 之前重開 | 補跑落在不補跑時段，但 22:10 照排程執行，沒有損失 |
| 在 22:00～24:00 之間重開 | 補跑在 22:13 之後，會補跑。t0 不早於 22:10，寫入 `late = 0`；已經寫過就是 `no_new_session`，一般沒有損失。補跑本身失敗時，那一晚漏記，和平常單次失敗一樣 |
| 跨過 22:10、23:10，到隔天 00:00 以後才重開 | 補跑時已過寫入截止（T 的次一日 00:00），T 日的紀錄是 `late = 1`，不進任何統計。實質上這個 session 就遺失了，進 F-2 第一句的分子；落在第 0 相位格點時，也是永久的格點遺失。重開時刻若落在隔天 13:30～22:10，連補跑都沒有 |
| 剛好在執行中關掉 | 推論和 `taskkill` 相同：留下一筆沒有 end 列的執行（`recorder.py` 363、370～392 行）。關閉 `cmd` 視窗時 Python 收到的是 CTRL_CLOSE_EVENT，Windows 上的實際結束方式沒有查證，我以最壞情形推論 |

- 週五晚上也算平日：週五關掉、週六才重開，補跑寫的是 `late = 1`。
- 其他 job 也會停：族群動能的擷取與判定、股利同步。擷取與判定在重啟時會補跑（`scheduler.py` 893、907 行），股利同步沒有補跑。這些屬 ADR-0012、ADR-0016 的範圍，不是預測紀錄。
- 重開本身會 `git pull`（`dev-up.bat` 110 行）。拉到新程式時，D-5 第 6 點的重算照常發生，和備份無關。
- **（tech-architect 建議）要不要避開時段：要，平日 22:00～23:30。**
  - 依據和 RC-441 確認的 R1／R2 相同：這段時間涵蓋兩次執行在正常與一般失敗情形下的進行時間，可以避免「執行中被結束」。
  - 但真正會造成遺失的是「關掉之後沒有在當晚 24:00 前重開」。所以 README 要寫的事實是：備份完成就用 `dev-up.bat` 重新啟動。
- **要送風控的衝突：** 照 README 備份，CEO 必然要自己關掉再重開三個程序；而 R 系列的常設字面寫的是「不要自己……重新啟動任何程式」。兩者怎麼並存，字面歸風控。我的事實判斷：備份引起的重開，對預測紀錄只會造成上表的情形，不會寫出錯誤的紀錄。

**(b) 「成套複製三種副檔名」是否足以得到一致的備份**
- 前提成立時足夠。前提是：所有開著這三顆 DB 的程序都已結束。
  - 不只 backend 與 scheduler，`forecast-status.bat` 等一鍵檔、目錄同步、示範資料、研究 CLI 也都不能在執行中。frontend 不開 DB。
  - 這時每一顆 DB 的 `.db`＋`-wal`（若有）都是同一個時點的完整內容，三顆之間也在同一個時點。
  - 正常關閉時 SQLite 一般會 checkpoint 並刪掉 `-wal`。被強制結束時，`-wal` 會留下來，裡面可能有已 commit 的交易，所以一定要一起複製，README 第 100 行已經這樣寫。`-shm` 不需要，但一起帶沒有害處。
  - 依 SQLite WAL 的一般行為推論，**沒有在 Windows 上演練**（README 第 109 行也這樣寫）。
- 和 CG-3、補充四第 4 點的做法相比，README 的做法沒有 backup API、`integrity_check`，也沒有 sha256。這是事實，不是要求。
- **沒有先關程序就複製時（只列事實）：**
  - `.db` 與 `-wal` 是在不同時刻讀到的。WAL 裡還沒 checkpoint 的交易，可能沒進備份；
  - 複製途中若剛好發生 checkpoint，`.db` 的複本可能前後頁不一致，也就是損毀的備份；
  - 三顆 DB 不在同一個時點。主 DB 的族群統計列與市場 DB 的 run 對不上時，還原後依 ADR-0012 C-50 會整批拒收，卡片顯示 NE-6；
  - 在 Windows 上這種複製多半不會報錯，所以失敗是靜默的（推論，沒有實機驗證）；
  - 原本的 DB 不會因為被讀取複製而受損；
  - 對帳本而言，這份備份可能少了最近幾晚的紀錄。不過帳本建立之後的任何還原本來就屬 F-8（第 2 點）。

**(c) 備份裡含有帳本；放在哪裡、留幾份、定期備份的狀態**
- ADR-0030 對 CEO 自己做的備份，**沒有放置位置或保留份數的規定**。D-8 第 3 點只管還原，不管備份。有關的只有三處：
  - 補充四第 4 點 (2)：登記時那一份備份要放在 git 工作樹之外；
  - 補充九第 6 點：CG-3 備份的 sha256 是稽核證據；
  - ADR-0026 IV-18（proposed）：備份根目錄不得在 DB 檔所在目錄之內。
- **和位置有關的事實（tech-architect 建議 README 寫進去）：**
  - 備份資料夾若放在 repo 工作樹之內、又不在 `backend/` 底下，它就是未被 ignore 的未追蹤檔：`*.db` 只在 `apps/stock-desk/backend/.gitignore` 第 8～11 行被 ignore，根目錄 `.gitignore` 沒有。後果有兩個：
    - 族群動能判定的 `git status --porcelain` 不再為空（`dirty_worktree`，NE-7；`sector_attestation.py` 110～112、248～249 行）。這會讓 D 補充的 (a) 改良也無效。
    - 含有持倉的檔案有被誤 commit 的風險，牴觸章程第 4 節。
  - 結論：備份放在 git 工作樹之外，和補充四第 4 點的登記備份同一個原則。
  - 登記時那一份備份（CG-3）的 sha256 是稽核證據（補充九第 6 點），任何 CEO 文件都不得引導 CEO 清理或刪除它。
- **你們稱的「D-8 定期備份期限」，實際出處在 D-6 CG-3 的末句，以及待決事項 devops-sre 列（ADR-0030 第 193、359 行），不在 D-8。**
  - 性質：建議（風控 R-8 列為 suggested），不是寫入閘門。
  - 責任人：devops-sre。
  - 期限：n̂ 達 ⌈c₁÷2⌉ ＝ ⌈30÷2⌉ ＝ 15，每個 claim 各自判定，實際由 h3 先到。
  - 狀態：我在 `work/` 用 Grep 找「定期備份」，只找到 ADR 原文與引用，**沒有上線紀錄**。接線 PR 是否已合併、D_v 是否已出現，我沒有查證；尚未接線時 n̂ ＝ 0，期限還沒有逼近。
  - 時程推估：h3 的 n̂ 要到 15，大約在 D_v 之後 48 個左右的交易 session（約 10 週），前提是沒有漏記。這是推論。
- **（tech-architect 裁示）README 這套手動備份不算履行 CG-3 末句的「定期備份」。** 理由：
  - 它不是排定、會自動發生的機制，靠的是 CEO 自己記得做；
  - 它必須停掉 scheduler，每次都有上表的漏記風險；
  - 沒有 backup API、`integrity_check`、sha256；
  - 「上線」的責任人是 devops-sre，不是 CEO 的習慣。
  
  它可以作為 CEO 自己額外留的複本並存。
- 定期備份的設計約束，交 devops-sre 起草時遵守：
  - 用線上 backup API（`Connection.backup`），不停 scheduler；
  - 避開平日 22:00～23:30；
  - 放在 git 工作樹之外；
  - 不 import `app.forecast`（K-3）；`scheduler.py` 不在 `code_digest` 範圍內，所以加 job 不會觸發 D-5 第 6 點的重算；
  - 若要在 CEO 本機建立 Windows 排程，比照補充十第 5 點，要取得 CEO 的明確同意。
  - 另外要寫明：**有了定期備份，帳本建立後的還原仍然屬於 F-8**。備份的用途只是在災難時減少損失，不是讓還原變成例行操作。

### 2. 還原（README 第 102～107 行）

**為什麼屬於 F-8 與補充九第 2 點**
- F-8 寫明「主 DB 整檔還原、更換或重建」，任一成立，ADR 就須重審（ADR-0030 第 334 行）。
- D-8 第 3 點：當天要以 commit 在 `work/` 記錄日期、還原點與原因；失去的第 0 相位格點，驗證層要以「模型錯、基準對」放回最不利情境 W（第 230 行）。
- 補充九第 2 點：還原到沒有帳本 schema 的狀態之後，再執行 `bootstrap --production`，視同登記新 claim，須先修訂 ADR 並經風控；任何 CEO 文件都不得指示 CEO 執行 bootstrap。
- 帳本固定在 `backend\data\stock-desk.db`（`scheduler.py` 686～709 行）。README 的還原步驟正好是覆蓋這個檔。

**程式上會發生什麼**
- **(i) 還原成登記之後、但較舊的備份（帳本存在，只是比較短）**
  - 下一次 `forecast_record`：目標核對通過，因為是預設檔、而且是一般檔案；CG-2 核對通過，因為登記表還在（`recorder.py` 474～517 行）。
  - D-5 第 6 點（`recorder.py` 532～559 行）：比對的是還原檔裡最後一次執行的 `code_digest` 與 `runtime_json`。
    - 程式沒變，就不重算；
    - 程式有變（例如重開時 `git pull` 拉到新程式），就重算還原檔裡現存的全部紀錄，一般會一致。
    - 都不會因為還原而 `gate_closed`。
  - 接著照常寫入最新的 T。備份時點之後的紀錄永久消失，因為 recorder 沒有回填路徑（S-6、K-10）。
  - `forecast_run` 是 `INTEGER PRIMARY KEY AUTOINCREMENT`（`schema.py` 127 行）。`sqlite_sequence` 隨檔案一起還原，所以新的 `run_id` 會和已遺失時間線上的編號重複。這和 ADR-0026 N-40 的實測一致；含 WAL 的檔案複製這個組合沒有驗證。
  - `report verify`：只重算現存的紀錄，結果會是「一致」，**看不出紀錄少了**。
  - 登記列還在。`work/` 裡的登記紀錄也還成立，m 不變。
- **(ii) 還原成登記之前的備份（例如 CG-3，沒有 `forecast_` 表）**
  - 目標核對與強制重抓照常進行。
  - `record_forecasts` 的第一個動作 `begin_run` 進入 `_write`，`require_complete_schema` 拋出 `SchemaIncompleteError`（`store.py` 718～729、753～772 行）。
  - 這發生在 try 之外，所以由 `_guarded` 記一行 ERROR「scheduled job forecast_record failed」（`scheduler.py` 825～834 行），不留任何 `forecast_run`。
  - **每一次執行都一樣，直到修訂 ADR 為止。** 程式上再跑 bootstrap 是可以的（claims.py 的行為沒變），但依補充九第 2 點不准。
- 兩種情形都一樣：市場 DB 若也一起還原，備份之後的 PIT 快照永久遺失（ADR-0012 C-10，只增不改、不回填）。只還原其中一顆時，C-50 的來源驗證會整批拒收，卡片顯示 NE-6。

**狀態報告看得出來嗎**
- (i)：補充十三有「計數減少」這個代號，任一具名 outcome 的值或合計比上一份貼回 P 小時記入；記了就當天通知 tech-architect 與 devops-sre，依據是 F-8（補充十三組版檔第 80、139 行）。第二句的 L 增加時，也會記成「漏記（格點遺失）」。
  - **但不保證看得出來**：還原之後新增的執行次數，若多於遺失的次數，計數可能不比 P 小，這時只剩「格點遺失」一個跡象，而它本身不指向還原。
- (ii)：`report status` 讀不到帳本。推論一鍵檔會印 STOP_UNREADABLE 那一句（`forecast_status.py` 113～114、242～243 行），`report.py` 的處理路徑我沒有逐行追。scheduler 視窗每次執行都會出現 ERROR 與 traceback。

**（tech-architect 裁示）帳本建立之後需要還原時的正確程序**
1. CEO 不自己還原，先告訴 coordinator。過渡期用 RC-434 的過渡句。
2. coordinator 當天轉 tech-architect（資料位置與 F-8 的疑慮）與 devops-sre。
3. tech-architect 判斷要不要整檔還原，先考慮不還原的替代：
   - 持倉：用現有的介面重新輸入，或用 CSV 匯入（`POST /api/positions/import`；`positions.py` 72、81 行有範本與匯入）。資料要來自 CEO 自己的紀錄。**沒有從備份檔取出持倉的工具。**
   - 設定、警示規則：用現有的頁面與 API 修改。
   - 只動非帳本表的定向修復：沒有現成工具，要另外設計。方向是 ADR-0026 的還原點（D-4、IV-12：不得改動 `forecast_*`），但它是 proposed、沒有實作，而且只涵蓋持倉。
4. 真的要整檔還原時：
   - 先由 tech-architect 起草 ADR-0030 的補充並送風控，寫明 F-8 的重審結論、遺失格點的揭露方式、還原後記錄是否繼續；還原到沒有 schema 的狀態時，依補充九第 2 點先修訂；
   - 要不要用遺失紀錄去換回持倉與設定，**這個取捨由 CEO 決定**；
   - 由 devops-sre 經 coordinator、以風控定稿的字面引導執行；
   - 依 D-8 第 3 點當天在 `work/` 記錄。
5. 沒有「緊急時 CEO 可以先自己還原」的例外。理由是不還原對帳本是 fail-safe 的：主 DB 損壞時記錄本來就會停止（fail-closed），沒有任何東西在等 CEO 搶時間。

**正式登記之前還原**
- 對預測紀錄帳沒有問題，因為帳本還不存在，也就沒有 F-8 的對象。
- 但仍有三點限制：市場 DB 的 PIT 遺失（ADR-0012）；README 步驟本身沒有演練過；正式登記是否已經完成，我**沒有查證**（`work/` 裡沒有找到登記紀錄檔）。
- README 的字面會一直留著，所以要以「登記已完成」為前提來寫。

**README 這一段應改成的事實內容**（條列；字面歸風控）
- 備份：
  - 仍然可以照現在的方式做；只是複製出去，不影響已經記下的紀錄。
  - 要在三個視窗都關掉，而且沒有其他 stock-desk 一鍵檔在執行時才複製。
  - 避開平日 22:00～23:30；完成後就用 `dev-up.bat` 重新啟動，最好在當晚 24:00 前。
  - 備份資料夾放在 repo（`AICompany`）資料夾之外。
  - 不要刪除團隊登記時做的那一份備份。
  - 備份檔裡含有持倉。
- 還原：
  - 原生路徑刪掉「刪除、覆蓋、重新啟動」三步，改為「不要自己還原，先告訴 coordinator」。
  - 原因只講事實：預測紀錄開始之後，用備份覆蓋資料庫會永久失去備份之後的紀錄，記錄也可能停止；要不要還原、怎麼還原，由團隊判斷，必要時由 CEO 決定。
- Docker 段（第 129～131 行的還原，第 135～136 行的資料搬移）：
  - 把原生資料搬進 Docker，或反過來，等於更換主 DB，同樣不要自己做；
  - Docker 路徑本來就不記錄（compose 顯式設了 `STOCK_DESK_DB_PATH`）。
- 第 109 行「尚未演練」的註記保留。
- **local-run（`.claude/skills/local-run/SKILL.md` 第 108～111 行）：**
  - 屬員工線內部文件，由我和 devops-sre 對齊，不經風控。
  - 還原段加註「帳本建立後不得照此還原，見 ADR-0030 F-8、補充九第 2 點」。
  - 它在 main 上，依章程第 1 節，要從 `chore/agent-*` 分支改。
  - coordinator 不得把它轉述給 CEO（RC-434）。

### 3. README 第 26 行、第 261 行，以及通讀後找到的其他段落

**第 26 行（第 280 行是同一句）**
- 我前兩份報告把它列為「未查證」，這裡更正為**部分查證**。
  - 出處：`work/reviews/2026-10-26-dev-up讀env交件-devops-sre.md` 第 22～33 行。
  - 內容：devops-sre 在本雲端環境（`uv 0.11.32`，x86_64 Linux）實測，同名 shell 變數優先於檔案（`FOO=fromshell` 贏過檔案裡的 `fromfile`）；`UV_ENV_FILE` 設成空字串等同沒設；檔案不存在時 uv 以 exit 2 報錯。
- 還沒有查證的：
  - Windows 上的行為；
  - CEO 本機的 uv 版本。uv 本身不受 `uv.lock` 鎖定，版本取決於 CEO 安裝的是哪一版；
  - uv 官方文件與原始碼（我手上沒有）；
  - `.env` 裡的空值 `STOCK_DESK_DB_PATH=`、`export` 前綴、大小寫不同的名稱，uv 會不會把它們放進程序環境。
- 另一個事實：qa 2026-10-26 指出，這句只對 `.env` 裡的變數成立；`UV_ENV_FILE` 本身會被 bat 覆寫（`dev-up.bat` 96、101 行）。
- **查證方式**：devops-sre 在乾淨的 Windows 環境，用 CEO 本機的 uv 版本實測四件事：
  1. Windows 使用者環境變數 `FOO=fromwin`、`.env` 裡 `FOO=fromfile`，經 `UV_ENV_FILE` 執行 `uv run python -c "import os;print(os.environ.get('FOO'))"`；
  2. `.env` 裡寫 `STOCK_DESK_DB_PATH=`（空值），看程序環境裡有沒有這個名稱；
  3. `export STOCK_DESK_DB_PATH=x` 的寫法；
  4. 名稱大小寫不同的寫法。
  
  結果記在 `work/`。CEO 的 uv 版本要經 coordinator 取得，不得叫 CEO 自己去查設定。
- 對預測紀錄：誰優先都不影響「名稱存在就拒絕」。這句的準確度只影響 FinMind、推播這類變數。

**第 261 行（`STOCK_DESK_DB_PATH` 寫成「選用」），應寫的事實**
- 原生路徑（`dev-up.bat`）：不要設定。不論設成什麼值，包括空值，也不論設在 Windows 環境變數、`.env` 或單一視窗，預測紀錄都不會記錄（補充九第 3 點；`scheduler.py` 699～700 行）。
- Docker：`compose.yaml` 本來就顯式設定它（第 19、43 行），所以 **Docker 路徑不記錄預測紀錄**，這是設計結果。
- 第 262、263 行另外兩個路徑變數：（tech-architect 建議）改為「不需要設定」。它們不會造成拒絕，但 API 與 scheduler 若設得不一致，市場 DB 會分成兩份。

**通讀 README 後，其他與預測紀錄條件衝突或相關的段落**

| 行號 | 內容 | 事實 |
|---|---|---|
| 19 | 「關掉它的視窗就停止」 | 正確；但預測紀錄也一起停止，見第 1 點 |
| 21～23 | `cp .env.example .env` 後填值 | `.env.example` 若有 `STOCK_DESK_DB_PATH` 那一行，照做就會被拒絕。devops-sre 還沒回覆有或無（我前兩份報告的待辦），我讀不到這個檔 |
| 26、280 | 系統環境優先 | 見上 |
| 34～37 | 目錄同步「寫進 `STOCK_DESK_DB_PATH` 指到的 SQLite」「結果隨資料庫檔案帶到其他環境」 | 前一句容易讓人以為要設這個變數；後一句若是把別處的主 DB 帶回 CEO 機器覆蓋，就是更換主 DB，屬 F-8 |
| 41～53 | Docker 選用、「切換前請先備份」 | 改用 Docker 等於不記錄，資料也是另一份 |
| 135～136 | 原生與 Docker 之間搬資料 | 更換主 DB，屬 F-8 |
| 140～150 | 手動 `uv run` 啟動 backend 與 scheduler | 從 `backend` 目錄啟動、沒有這個變數時可以記錄；但和 `dev-up.bat` 混用時，`dev-up.bat` 會以 `taskkill /F /T` 結束手動啟動的 scheduler（`dev-up.bat` 277～302 行），留下沒有 end 列的執行 |
| 289～292 | 示範資料 `app.demo.seed` | 依 README 字面只寫 2330、0050、00631L，不涉及 `^TWII`，和預測紀錄沒有直接衝突（我沒有讀 `seed.py` 驗證）。但它會把示範持倉寫進 CEO 的正式主 DB，這是另一個既有問題，要不要註明不在 CEO 機器上執行，由 creative-lead 與風控判斷 |

## 驗證
- 讀過：
  - README 全文（332 行）；local-run 第 70～114 行；`dev-up.bat` 全文；
  - ADR-0030 第 1～60、180～369、476～537 行；補充九最終版（`2026-11-19-收盤定案時點重新定案與補充十-tech-architect.md` 第 135～233 行）、補充十第 235～294 行；
  - 接線版 `recorder.py` 340～599 行、`store.py` 700～809 行、`scheduler.py` 640～955 行、`schema.py`（Grep）；
  - `forecast_status.py` 1～40 行與 Grep；補充十三組版檔（Grep「減少」）；
  - devops-sre 10-26 交件第 15～44 行、qa 10-26 審查（Grep）；`.gitignore`（Grep）；`positions.py` 路由（Grep）。
- 沒有查證：
  - Windows 上關閉視窗時程序怎麼結束、檔案複製的實際行為；
  - 執行時間的實測；
  - uv 在 Windows 與 CEO 本機版本上的優先順序與空值處理；
  - `.env.example` 的內容；
  - 正式登記與接線 PR 是否已完成、D_v 與 n̂ 的實際值；
  - `report.py` 遇到沒有 schema 時的確切結束碼；
  - `seed.py` 的實際寫入範圍。

## 下一步
1. creative-lead：依第 2 點末的事實條列，起草 README 備份與還原段、第 261～263 行、第 26／280 行，以及第 3 點表中各處；送風控；放進 RC-416 那個只改文件的 PR。
2. devops-sre：回覆 `.env.example` 有沒有 `STOCK_DESK_DB_PATH`；依第 3 點在 Windows 實測 uv；把 CG-3 末句的定期備份照第 1 點 (c) 的約束排入計畫（期限 n̂ 達 15 之前）；和我對齊 local-run 的還原段（走 `chore/agent-*` 分支）。
3. coordinator：追蹤清單加一列「定期備份上線（devops-sre，n̂ 達 15 之前）」；把 R 系列字面與 README 備份要求重開之間的關係轉給風控。
4. **必須由 CEO 決定的事：** 現在沒有。只有日後真的要在帳本建立後整檔還原時，「用遺失紀錄換回持倉與設定」的取捨由 CEO 決定。

---

# B. RC-435：下游 ADR 把要 CEO 執行的處置只寫在手冊

## 本次結論

1. 三份都還**不是 accepted**：ADR-0026 proposed，ADR-0029 proposed，ADR-0027 proposed 而且已依 ADR-0030 D-8 凍結、內文不再修訂。
   - 要 CEO 親手做的處置有：收到 E-2 時停 scheduler 再重啟、設定推播通道並自測、清查主機 log 並輪換祕密、init、整檔還原、手動備份、每季還原演練。
2. （tech-architect 裁示）給 CEO 的處置只寫在一處：**`apps/stock-desk/README.md` 裡專設的 CEO 操作段**。
   - 事實由 devops-sre 維護，字面由 creative-lead 起草、風控定稿；工程程序留在手冊。
   - ADR-0026、ADR-0029 是 proposed，直接改草稿並留修訂紀錄；ADR-0027 已凍結，不改，改由驗證層 ADR 承接。
3. **E-2 在核心期間不可能出現**：它來自 settlement、audit、correction 三步，這幾個模組依 ADR-0030 K-1 不得存在。所以 E-2 上線的前置，必然包括驗證層 ADR 核可並實作。停 scheduler 會一併停掉預測紀錄與 PIT 擷取，代價是兩本帳的永久遺失，而且和「不要自己重新啟動」衝突。所以「立即停 scheduler」要在驗證層 ADR 重新決定。
4. 風控定的觸發時點足夠，但要再加兩個時點（見第 4 點）。現在只需要列追蹤，不必改 ADR。

## 各部門回報（tech-architect）

### 1. 受影響條文與狀態

| ADR | 狀態 | 受影響條文（現行行號） | 要 CEO 親手做的處置 |
|---|---|---|---|
| ADR-0029 | proposed（第 3 行） | 138（D-4：處置只寫在手冊 §5）、249（D-10 第 5 項：D_v 閘門要求手冊 §5 補齊）、267～268（Consequences：「推播與手冊『立即停 scheduler』缺一不可」）、336（風控 required 落點 R-Q7-6）、340～352（手冊 §5 待補項 1～9）；另有 19、245（D-10 第 1 項）、239、246（D-9、D-10 第 2 項） | 收到 E-2 停 scheduler，處理完 ADR-0026 D-9.4 才重啟（待補項 2）；設定推播通道的三個變數，也就是改 `.env`（待補項 5、D-10 第 2 項）；執行 `python -m app.ops_alert.selftest`，並確認在聊天室看到訊息（D-9、D-10 第 2 項）；清查主機 log、輪換祕密（第 19 行、D-10 第 1 項）；每天 23:30 後的人工檢查（待補項 3，執行者沒有寫明） |
| ADR-0027 | proposed，已凍結（第 3 行；ADR-0030 D-8 第 3 點） | 5108（「後續仍待」：手冊 §5 收到 E-2 時立即停 scheduler，R-Q7-6，擋 D_v） | 停 scheduler |
| ADR-0026 | proposed（第 3 行） | 537（待決 devops-sre：手冊 §0.3、§1 init、§4 `Connection.backup`、整檔還原程序與 D-9.4、manifest）、538（每季還原演練）、373～384（D-9.4「整檔還原只限操作者手動執行」，沒有定義「操作者」是誰；第 383 行「操作者立即手動做一組新的備份」） | init；整檔還原；手動備份；還原演練。「操作者」若指 CEO，就和 F-8、補充九第 2 點衝突 |

- ADR-0026 第 590 行是修訂紀錄裡逐字錄存的舊文（檔案自己註明「屬歷史列，不是現行條文」），**不改**。
- ADR-0026 D-9.4 第 377 行寫「遺失的 session 由預測帳的缺日稽核記為 `db_restored`」，依賴的是已凍結的 ADR-0027 驗證層，和 ADR-0030 D-8 第 3 點的現行規定不一致。改草稿時一併對齊；兩者衝突時以 accepted 的 ADR-0030 為準。
- 手冊行號的引用（ADR-0026 的 `:90-94`、`:236-240`、`:242-248`、`:290-306` 等；ADR-0029 的 `:310-357`）：兩份 ADR 的標註約定本來就寫了「行號會漂移」（ADR-0026 第 24 行、ADR-0029 第 20 行），所以不阻擋。改草稿時改用節名定位。

### 2. 寫在哪一份 CEO 文件、由誰維護、ADR 怎麼記（裁示與待辦，不必現在改）

**方案比較**

| 方案 | 優點 | 缺點 |
|---|---|---|
| **(甲) README 專設「給 CEO 的操作」段（採用）** | README 已是 CEO 的日常文件（第 10～15 行），RC-434 也已經把它當 CEO 文件處理；和 `dev-up.bat` 在同一個產品樹；一處維護 | README 同時有工程內容，要靠段落區隔，並比照 RC-430 給這段常設保護 |
| (乙) 各 ADR 各自的操作說明檔 | 和各 ADR 一對一 | 又多出好幾份 CEO 文件，正是 RC-427 要防的「多套 CEO 操作方式」 |
| (丙) `work/stock-desk-產品說明.md` | 檔頭寫明對象是 CEO | `work/` 依章程是放過程文件的地方；和 README 重複 |

- **（tech-architect 裁示）採用甲。** `work/stock-desk-產品說明.md` 若提到這些事，只連結到 README，不另寫一份。
- 這一段的原則：
  - 預設的處置是「告訴 coordinator」，和 RC-428、RC-432 (a) 一致；
  - 需要 CEO 做的任何一步，由 coordinator 依風控定稿的字面引導；
  - 推播本身不帶處置指示（ADR-0029 D-4 不變）。
- 維護分工：事實由 devops-sre 負責；字面由 creative-lead 起草、風控定稿；改動比照 RC-430，要送風控。
- **ADR 上的待辦：**
  - **ADR-0029（proposed，直接改草稿並留修訂紀錄，比照 ADR-0026 第 562 行起的做法）：**
    - 第 138、249、267～268、336 行改為「給 CEO 的處置寫在 README 的 CEO 操作段（風控定稿）；團隊的處置寫在手冊 §5」；
    - 「手冊 §5 待補項」拆成「README（CEO）」與「手冊 §5（工程）」兩張清單；
    - D-10 第 1、2 項的 CEO 動作（log 清查、改 `.env` 設通道、selftest）改為經 coordinator 引導，因為改 `.env` 和 RC-432 的過渡句衝突。
    - 改稿人 devops-sre（原草案作者），我審事實，風控審字面。
  - **ADR-0026（proposed，直接改草稿）：**
    - 第 537 行改為「手冊只放團隊的工程程序；init 與整檔還原不是 CEO 步驟」；
    - D-9.4 把「操作者」定義為「devops-sre，經 coordinator 引導」，並加一句「帳本建立後的整檔還原，依 ADR-0030 F-8、補充九第 2 點，須先修訂 ADR-0030，取捨由 CEO 決定」；
    - 第 377 行改依 ADR-0030 D-8 第 3 點。
    - 改稿人 tech-architect（原草案作者）。
  - **ADR-0027（凍結）：** 不改，也不必在 ADR-0030 另寫 append。第 5108 行的待辦由驗證層 ADR 承接：依 D-8 第 5 點以凍結附錄為底起草時，列為必辦項——「要 CEO 執行的處置不得只寫在手冊」。coordinator 在追蹤清單記下。
  - 三份目前都沒有 accepted 的，不存在要 append 的情形。之後若有任何一份先 accepted 而條文還沒改，就以補充 append 處理，不改原字面。

### 3. 「收到 E-2 立即停 scheduler」、預測紀錄、R 系列「不要自己重新啟動」三者的關係

**事實**
- E-2 的 `source` 只有 settlement、audit、correction 三種（ADR-0029 第 100～102 行），對應 ADR-0027 的驗證層。ADR-0030 K-1 規定核心期間 `settlement`、`audit`、`correction` 這些模組都不得存在。**所以核心期間不會有 E-2。**
- 停 scheduler 停掉的是整個程序：
  - `forecast_record` 停止，進 F-2 分子，第 0 相位格點的遺失是永久的；
  - ADR-0012 的 PIT 擷取也停止，PIT 快照不能回填，也是永久遺失。
- 重啟要等 ADR-0026 D-9.4 處理完（ADR-0029 第 345 行），而 R 系列的常設字面要 CEO「不要自己重新啟動」。所以停下之後，什麼時候重開完全取決於團隊，停機時間會拉長。
- ADR-0029 之所以要停整個 scheduler，是因為守衛不存跨執行狀態（第 268 行）。改成程式內持久的鎖存，又會牴觸 ADR-0029 失效條件第 1 點與 OA-7。

**（tech-architect 裁示）E-2 推播上線的前置**
1. 驗證層 ADR 已核可並實作（E-2 的來源本身）。
2. 驗證層 ADR 重新決定收到 E-2 時怎麼處置，三擇一並寫明代價：
   - (i) 停整個 scheduler：由 CEO 依 coordinator 的指示執行，代價是預測紀錄與 PIT 的遺失；
   - (ii) 把驗證層的 job 拆到另一個程序或 job 群，讓「停」只停驗證步驟，`forecast_record` 與 PIT 擷取照常。這是架構變更，要在 ADR 決定；
   - (iii) 持久化的鎖存：牴觸 ADR-0029 失效條件第 1 點，要另立 ADR。
   
   （tech-architect 傾向，非定案）(ii)，因為它把 CEO 的動作從「停機」縮成「告訴 coordinator」。
3. README 的 CEO 操作段已由風控定稿，寫明收到 `[stock-desk 維運告警]` 時 CEO 要做什麼。預設是告訴 coordinator；只有在採 (i) 時，才寫怎麼停。
4. 若採 (i)：
   - `dev-up.bat` 路徑下的停止方法要先在 Windows 上查證；
   - 重開的請求字面要比照 R3-0／R3，由風控預先定稿，明寫這是對「不要自己重新啟動」的一次性例外。
5. 補充十三的心跳比對要能區分「依 E-2 停機」造成的漏記：coordinator 在紀錄裡註明，避免它被當成原因未明。
6. 以上第 2～5 項列進 ADR-0029 D-10 的閘門。

### 4. 觸發時點夠不夠；現在要不要做什麼

- 風控的觸發是「這幾份 ADR 定稿或改為 accepted 之前，或 E-2 推播上線之前，以先到者為準」。**足夠，但要再加兩個時點，同樣以先到者為準**：
  - (a) 任何 CEO 文件（README、產品說明、`work/dispatch/` 的通知）要引用這幾節手冊或這些處置之前；
  - (b) ADR-0026 D-9 的備份組，或 ADR-0030 CG-3 末句的定期備份，要實作上線之前。這可能早於 ADR-0026 accepted。
- 現在要做的只有追蹤：
  - coordinator 把 B 的第 2、3 點列進追蹤清單，觸發時點照上面；
  - qa 審 RC-416 的 PR 時，確認 README 沒有把 CEO 導向手冊的這些節。
- 不必現在改 ADR：目前沒有任何一項要 CEO 執行的處置已經上線。

## 驗證
- 讀過：ADR-0029 第 1～27、90～149、235～359 行；ADR-0026 第 1～30、360～389、525～594 行；ADR-0026、ADR-0027 的 Grep（狀態、「部署手冊」、IV-12）；ADR-0030 K-1（第 311 行）。
- 沒有查證：
  - ADR-0027 第 5108 行的上下文全段（只讀到該行）；
  - E-2 推播的實際時程；
  - `dev-up.bat` 路徑下停 scheduler 的 Windows 行為；
  - 驗證層 ADR 的起草時點。

## 下一步
1. coordinator：追蹤清單加上 B 第 2 點的三份 ADR 待辦、第 3 點的 E-2 前置、第 4 點的觸發時點。
2. devops-sre：ADR-0029 改稿時照第 2 點（等觸發時點到了再做）。
3. tech-architect：ADR-0026 改稿（等觸發時點到了再做）；把「要 CEO 執行的處置不得只寫在手冊」列進驗證層 ADR 的必辦項。
4. creative-lead 與風控：README CEO 操作段的字面，等觸發時點到了再起草。
5. **必須由 CEO 決定的事：** 現在沒有。驗證層 ADR 若採 B 第 3 點的 (i)，停機的代價要讓 CEO 知悉並由 CEO 核可，因為驗證層 ADR 本來就要 CEO 核可。

---

# C. RC-436：手冊工程內容本身的錯誤

## 本次結論

**（tech-architect 裁示）要改。**
- 由 devops-sre 改（ADR-0012 指派的手冊維護者），我核對事實，qa 核對 RC-430。
- 時點：RC-428／RC-429 那個 PR 合併、而且經風控單項確認之後，在**下一個只改文件的 PR** 處理。
- **不併入** RC-416 那個 PR：RC-430 規定那個 PR 的 diff 只能有三樣東西。
- 也不是接線前置：手冊已不是 CEO 文件，也不在 `code_digest` 範圍內。
- 不把它寫成 ADR-0012 補充的條文；補充一只在第 5 點列為連動待辦。

## 各部門回報（tech-architect）

**要改的內容**（事實依我先前的兩份報告）
- 0.2、0.3 節的「建議顯式指定」三個路徑變數：
  - 改為「記錄期間不得設定 `STOCK_DESK_DB_PATH`（任何值，包括空值，在任何地方設都一樣）；另外兩個不需要設定」；
  - 0.3 的路徑改為 `apps\stock-desk\backend\data\`；
  - 0.2 的 `'User'`／`'Machine'` 永久設定片段移除；
  - `.env` 的位置改為 `apps\stock-desk\.env`。
- 第 1 節第 3 步（載入 `backend\.env`）刪除，或標為不適用；第 6 步「務必也載入同一份環境變數」照事實改寫。
- 第 1 節第 4 步、第 3 節第 3 步的 attestation：改寫為團隊的步驟，和 D 補充一的 (a) 一致。
- §4.4 寫死的 `C:\stock-desk\data\`：
  - 改為上面那個錨定路徑；
  - 備份方法改用 `Connection.backup`（CG-3 允許 backup API 或 `VACUUM INTO`；ADR-0026 D-9 第 3 點（proposed）偏好前者）；
  - 還原段改為「帳本建立後屬 F-8，不在本手冊的程序內，見 ADR-0030 F-8、補充九第 2 點」。
- §5：
  - 註明 `dev-up.bat` 不產生檔案 log（`dev-up.bat` 150、166 行；`logging_setup.py` 只有 stderr）；
  - 預測紀錄的監控以狀態報告與補充十三的心跳比對為準；
  - ADR-0012 第 1150 行要求監控 attestation notes，在 CEO 主機上做不到，這一點併入 D 補充一 (a) 的設計問題。

**守 RC-430**
- 檔頭標註和 9 處警示逐字不動，不移位；
- 不新增任何「由 CEO 執行」「CEO 請……」一類的句子；
- 被改寫的節，原本就有的警示行留在原位；
- qa 逐行確認以上三點；只要動到標註或警示，就送風控。

**觸發時點**（任一先到，之前要完成）
- ADR-0026 或 ADR-0029 改稿，要引用 §4、§5；
- 定期備份上線；
- D 補充一 (a) 的設計交件。

## 驗證
- 依據：我先前兩份報告（手冊全文、`dev-up.bat` 全文）；RC-428～RC-430、RC-436。這一輪沒有重讀手冊全文。
- 沒有查證：改字分支（0.1 節）與 RC-428／RC-429 那個 PR 合併後的實際行號。

## 下一步
1. devops-sre：RC-428／RC-429 那個 PR 確認之後，開文件 PR 處理上列內容；PR 說明逐項對照本節。
2. qa-reviewer：依 RC-430 核對。
3. tech-architect：核對事實。
4. 沒有需要 CEO 決定的事。

---

# D. ADR-0012 補充紀錄草稿

## 本次結論

1. ADR-0012 是 accepted（第 3 行），所以這份是 **append**：
   - 只在檔頭「修訂：」清單末尾加一行，在檔尾（第 1157 行之後）加一節；
   - 既有字面一律不改。
2. 格式說明：**ADR-0012 目前沒有任何「補充」節。** 檔頭唯一的後續修訂寫法，是第 77 行「後續（ADR-0025 部分修訂）：……；本檔原文不改。」。
   - 所以檔頭行比照第 77 行的句式，掛在「修訂：」清單下；
   - 正文編號從「補充一」起算，比照 ADR-0030 的慣例。
3. 草稿全文在下面的區塊內。

## 各部門回報（tech-architect）

<<<ADR-0012 補充開始>>>
  - 補充一（2026-11-21 append）：`dev-up.bat` 路徑下 build attestation 沒有履行（C-52 適用範圍內的部署約束缺口），記為已知缺口並限期補上；列出 NE-7 的全部子原因與 RC-421 待辦；主機部署手冊改判的連動；tech-architect 裁示，釐清與限期，不放寬 C-36、C-52，不改判定行為、使用者可見字面與 API 欄位；改採永久不補須 CEO 決定，其餘 CEO 可推翻；來源 `work/reviews/2026-11-21-心跳確認書審查與attestation落差裁示與退役測試對應-tech-architect.md`（第二件）、`work/reviews/2026-11-21-重啟請求定稿與手冊0.2及0.3節與attestation告知RC407至RC421-風控.md`（RC-419～RC-421）、`work/reviews/2026-11-21-手冊改判處理路徑與重啟請求R3-RC427至RC441-風控.md`（RC-427～RC-433、RC-436），以及本補充起草報告的轉存檔（檔名由 coordinator 確定後替換）；本檔原文不改。

（以下一節接在本檔最後一行之後）

## 補充一：`dev-up.bat` 路徑下 build attestation 的已知缺口、限期、NE-7 子原因與手冊改判的連動（2026-11-21）

- 決策者：tech-architect。來源見檔頭「補充一」那一行。
- 性質：
  - 第 1 點為事實與性質的釐清；第 2、3 點為限期與設計約束（收緊）；第 4 點為釐清；第 5 點為連動。
  - 不改 C-36、C-52、T-22、T-36 與 Options K 的任何字面；不放寬任何判定條件；不改使用者可見字面、API 欄位與判定行為。
  - 本檔為 accepted，本節為 append，不改寫既有任何一行。
  - 第 6 點所列事項須 CEO 決定；其餘 CEO 可推翻。
- 適用範圍：僅 `product/stock-desk`。路徑相對於 `apps/stock-desk/backend/`，另有標示者除外。行號為 2026-11-21 product 版的狀態，會漂移。

1. **事實與性質**
   - (a) `apps/stock-desk/dev-up.bat` 就是 K1 的主機形態：
     - 從同一個 git checkout 的 `backend` 目錄，以 `uv run` 直接啟動 API 與 scheduler（`dev-up.bat` 150、166 行）；
     - 啟動前先停掉舊的程序（119～124 行），再 `uv sync --locked`（130 行）；
     - `git` 可執行、`.git` 可讀、`tests/` 存在。
   - (b) 這個路徑沒有執行 `scripts/attest_sector_gate.py` 的步驟。所以 C-52 第 1 點的「且已在該 checkout 跑過 `scripts/attest_sector_gate.py`」沒有被履行。**這是 C-52 適用範圍內沒有被履行的部署約束，屬於實作與流程的缺口，不是 C-52 範圍之外的部署形態。**
   - (c) K3 只把「NE-7 恆成立」接受為「K1 落地前的 fail-closed 現況」。K1 已經 CEO 2026-09-25 裁定採用，但在 `dev-up.bat` 路徑上還沒有完整落地。本補充只在第 2 點的期限內，援引 K3 對「落地前現況」的接受；過了期限仍未落地，就不得再援引 K3。
   - (d) fail-closed 的鏈條：
     - 判定端讀不到 attestation 檔，就列入 `attestation_missing`（`app/services/sector_attestation.py` 194～207、250～251 行）；
     - 統計列 `selfcheck_passed=false`（`app/backtest/sector_eval.py` 2022～2023 行）；
     - API 程序啟動時自己的檢查也不 ok，`ci_passed_commit` 為 None（`app/services/sector_runtime.py` 47～49 行）；
     - 只要已有統計列，就加入 NE-7（`app/sectors/gate.py` 457～466 行）。
     
     結果只會少列示歷史比例，不會多列。這個路徑上沒有會變成 fail-open 的情形，因為不會產生 attestation 檔。
   - (e) 和 ADR-0030 無關：預測紀錄帳核心不讀市場 DB，也不 import `app.sectors`（ADR-0030 K-2）。本缺口不是正式登記、接線或任何 ADR-0030 閘門的前置；補上時也不得動 ADR-0030 `code_digest` 涵蓋的檔案（第 3 點 (f)）。
   - (f) 釐清：
     - C-52 第 1 點寫的是 `uv sync --frozen`，`dev-up.bat` 用的是 `uv sync --locked`。讀為滿足 C-52 的目的（依鎖檔安裝，不更新鎖檔）：`--locked` 在鎖檔和 `pyproject.toml` 不一致時直接失敗，方向較嚴。〔推論，依 uv 的一般行為，未查證 CEO 本機的 uv 版本〕
     - 「兩個程序都要重新啟動」由 (a) 滿足。
     - D-8「部署期間的預期行為」要求啟動後立即補跑一次判定，由 scheduler 的啟動補跑滿足〔事實：接線版工作樹 `app/scheduler.py` 893、907 行；product 版行號未查證〕。
2. **現行處置：已知缺口，限期補上**
   - (a) 補上之前，`dev-up.bat` 路徑下的判定恆為 NE-7。它被 NE-1～NE-6 中編號較小者遮住，所以目前卡片顯示的是其他原因，那些原因是真的。
   - (b) **觸發條件**（任一先到即觸發）：
     - (i) 累積樣本數 N 達 120；
     - (ii) 任何可能讓 NE-1～NE-6 全部消失的改動合併之前，例如回補路徑、DE-10 費率查證完成；
     - (iii) 因其他原因改寫 `dev-up.bat` 時，一併處理。
   - (c) 觸發時，devops-sre 交出第 3 點的設計 (a)，經 qa-reviewer（含 Codex 第二意見）與風控（只看新增的視窗輸出行）。落地期限：N 達 150 之前。
   - (d) 補上之前與之後，都不得請 CEO 自己執行 attestation、`git status` 或任何指令（RC-420）。
3. **觸發時的設計約束**（設計 (a)：在 `dev-up.bat` 加入 attestation 步驟）
   - (a) attestation 失敗絕不能阻擋啟動：不得 `goto fail`，不得依它的結束碼改變後續流程。否則族群動能的問題會變成預測紀錄的漏記。
   - (b) 位置：排在 `uv sync --locked` 之後、`start "stock-desk scheduler"` 之前。理由：C-36 不綁定已安裝的依賴（Consequences 第 1096 行）。
   - (c) 條件式執行：attestation 檔存在、可讀，而且 `ci_passed_commit` 等於 `git rev-parse HEAD` 時，不執行；其他情形才執行。
   - (d) 要有執行時間上限。上限依實測耗時訂定，超過就視同失敗並照常啟動。耗時目前沒有實測。
   - (e) 不在 repo 工作樹內產生任何未被 ignore 的檔，只寫已被 ignore 的 `app/_build/ci_attestation.json`。理由：判定時的 `git status --porcelain` 涵蓋整個 repo 工作樹，未追蹤檔也算（第 4 點 J2）。
   - (f) 不改 ADR-0030 `code_digest` 涵蓋的檔案（`app/forecast/**`、`app/outlook/**`、`app/dirdef/**`、`app/data/session_calendar.py`）。`app/_build/*.json`、`scripts/`、`tests/` 都不在涵蓋範圍內。
   - (g) C-52 第 3 點不變：`running_commit`、`ci_passed_commit`、`suite_hash` 不得來自環境變數、build arg 或設定檔。
   - (h) 視窗新增的每一行，逐行送風控；不新增任何要 CEO 輸入或回答的提示。
   - (i) 設計要回答一件事：ADR-0012 第 1150 行要求監控 attestation notes，「持續出現即告警」，但 CEO 主機的 `dev-up.bat` 路徑沒有檔案 log，怎麼監控。要不要改監控方式由 tech-architect 裁示，不得以新增 CEO 的操作代替。
   - (j) 已知限制（不改）：本機自我證明（D-8 第 430 行）；即使啟動時 attestation 成功，之後工作樹只要出現未被 ignore 的未追蹤檔，判定時照樣是 `dirty_worktree`。(a) 只能降低 NE-7 的機率，不能保證。
4. **落進 NE-7（`lookahead_tests_failed`）的全部子原因**
   - **判定端**：scheduler 的 `services.sector_board`，統計列寫入 `selfcheck_passed=false`。
     - (J1) `git_unreadable`：`git rev-parse HEAD` 或 `git status --porcelain` 無法執行、非 0 結束或超過 20 秒（`sector_attestation.py` 54、91～112、246～247 行）。
     - (J2) `dirty_worktree`：`git status --porcelain` 非空（110～112、248～249 行）。範圍是整個 repo 工作樹，含未追蹤、未被 ignore 的檔，不限於 `backend/`〔依 git 的一般行為推論，未實機驗證〕。
     - (J3) `attestation_missing`：檔案不存在、讀不到、不是 JSON 物件，或三個欄位任一不是非空字串（194～207、250～251 行）。
     - (J4) `commit_mismatch`：HEAD 不等於 `ci_passed_commit`，只在檔案可讀時判定（253～254 行）。
     - (J5) `suite_hash_mismatch`：NE-7 測試集（使用 marker 的測試檔、`conftest.py`，以及遞移 import 的 `tests.*` 輔助模組）重算出來的雜湊不同（151～186、255～256 行）。
     - (J6) runtime 自檢沒有通過（`sector_eval.py` 1934～1953 行）。依下列子項判斷「是不是檢查結果」：
       - 自檢名稱集合不等於 `SELFCHECK_ORDER`（138 行）：沒有完整執行；
       - 任一項 `fail`：檢查有執行，結果未通過；
       - `vacuous` 出現在 T4、T5、T6 以外（142 行）：沒有完整執行；
       - `skipped_insufficient_n` 出現在 T3a、T8、T8 打亂以外（141 行），或 N 不小於 `skip_allowed_below_samples`（`app/sectors/definition.py` 137 行，現值 30）：沒有完整執行。
   - **讀取端**：API 程序的 `gate.evaluate`，只在已有統計列時（`gate.py` 457 行）。
     - (R1) T8 沒有產出 `delta_real`、`delta_shuffle`（458～460 行，`ERROR_T8_NOT_PRODUCED`）：檢查有執行，但沒有完整產出。
     - (R2) 最新統計列的 `selfcheck_passed=false`，也就是判定當時 J1～J6 任一成立（462 行）。
     - (R3) `ci_passed_commit` 為 None：API 程序啟動時自己的檢查不 ok，也就是 API 程序啟動當下 J1～J5 任一成立（463 行；`sector_runtime.py` 47～49 行）。
     - (R4) 統計列的 `running_commit` 不等於部署的 `ci_passed_commit`（464 行）。包括部署窗口（D-8 部署期間行為），以及判定時讀不到 HEAD 而寫入 `UNKNOWN_COMMIT`（`sector_board.py` 509 行）。
   - **分類**：
     - 「檢查實際執行了，結果未通過」只有 J6 的 `fail`。
     - 「檢查沒有執行、沒有完整執行，或版本無法確認」包括 J1～J5、J6 的其餘子項、R1、R3、R4。
     - R2 依它的來源歸類。
   - 現況：`dev-up.bat` 路徑下 J3 與 R3 恆成立；若之前曾手動執行過 attestation，更新程式後改為 J4。
   - 顯示：NE-7 只在 NE-8 不成立、而且 NE-1～NE-6 都不成立時，才是主要原因（`gate.py` 486～487 行；C 規則第 920 行）。`not_evaluated_reasons` 已含 NE-7，但非測試的 UI 不讀它（依 RC-421 的 Grep）。
   - **RC-421 待辦**（required）：
     - 現行卡片句（`sectorMomentumWording.ts` 第 446～449 行）把上列「沒有執行或版本無法確認」的情形，描述成「未通過資料偏誤檢查」「本次檢查未全部通過」。在第 2 點 (b) 的觸發成立之前，不必改。
     - 觸發時，tech-architect 依本點的清單，逐項標「已執行未通過」或「未執行或無法確認」，裁示二擇一：
       - (甲) 只改字：一句同時涵蓋兩類，不得把未執行寫成未通過；
       - (乙) 拆代碼：例如把 J1～J5、R3、R4 拆成另一個 `NotEvaluatedReason`。這會改 NE 清單、優先序、API 列舉、C-36 與 T-22 的對照，屬於 ADR 修訂，要風控審，並讓 CEO 知悉 NE 清單的變更。
     - （tech-architect 初步傾向，非定案）(乙)。理由：(甲) 的句子會變得含糊，而兩類原因的處理方式不同：一類要補部署步驟，另一類要查方法或資料。
     - 之後由 creative-lead 起草，風控逐字審。禁說照 RC-421。
5. **主機部署手冊改判的連動（RC-427～RC-433、RC-436）**
   - (a) 第 1150 行指派 devops-sre 依 C-52 撰寫的主機部署手冊（`apps/stock-desk/docs/族群動能-主機部署手冊.md`），已改判為團隊的工程參考，不是 CEO 的操作文件。檔頭與 9 處就地警示依 RC-428、RC-429 定稿。
   - (b) C-52 的部署形態與 devops-sre 的維護責任都不變（RC-433）。
   - (c) 手冊第 1 節第 4 步、第 3 節第 3 步原本寫成由 CEO 執行 attestation 並排除問題，都不是 CEO 的步驟。attestation 由第 3 點的設計 (a) 承擔。
   - (d) 手冊的任何修改都守 RC-430 的常設規則：檔頭標註與 9 處警示不得刪除、移位或弱化；不得新增對 CEO 的指示；要動到這兩者，先送風控。
   - (e) 手冊工程內容的更正（0.2、0.3 節的路徑變數、§4.4 寫死的路徑、§5 依賴的檔案 log；RC-436）不屬本 ADR 的條文。由 devops-sre 在另一個只改文件的 PR 處理，追蹤清單列管。本點只記連動。
6. **須 CEO 決定的事**
   - (a) 改採「永久不補」，也就是不設期限，讓 `dev-up.bat` 路徑長期停在 K3。這實質推翻 CEO 2026-09-25 裁定的 K1：N 達 150 之後，卡片永遠不列示歷史比例，「約 3 年」的時程也失去實際意義。問句由 tech-architect 起草，送風控依 RC-263 定稿；RC-420 的字面也隨之作廢。
   - (b) 改採容器部署，或 Options K2：依 C-52 第 2 點與第 1157 行，要另立修訂，並經 CEO 核可。
   - 其餘各點 CEO 可推翻。
7. **送風控的項目**
   - (a) 本補充不含面向 CEO 的字面，只請風控知悉級確認兩件事：本補充沒有新增對 CEO 的字面；RC-420 照舊適用。
   - (b) 設計 (a) 落地時，`dev-up.bat` 視窗新增的每一行（第 3 點 (h)）。
   - (c) RC-421 的新字面，或拆代碼之後的新原因句（第 4 點）。
   - (d) 補上之後給 CEO 的告知（RC-420 的承諾「補上時若需要您做什麼，我會再告訴您」）。
   - (e) 若走第 6 點 (a)，給 CEO 的問句。

- **S-A1（逐條可檢查）**
  - S-A1-1：本補充落檔的 diff，只有檔頭「修訂：」清單末尾新增一行，加上檔尾新增本節；其他行零差異（`git diff` 只有新增行）。
  - S-A1-2：追蹤清單有以下各列：第 2 點 (b) 的三個觸發、N 達 150 的落地期限、RC-421、RC-420 的承諾（補上時告知 CEO）。
  - S-A1-3：設計 (a) 交件時，逐行讀 `dev-up.bat`：attestation 步驟之後沒有 `goto fail`，也沒有依它的 errorlevel 分支；位置在 `uv sync --locked` 之後、`start "stock-desk scheduler"` 之前；有第 3 點 (c) 的條件式；有第 3 點 (d) 的時間上限。
  - S-A1-4：在乾淨的 checkout 上，attestation 步驟跑完之後，`git status --porcelain` 為空。
  - S-A1-5：設計 (a) 的 PR 對 `app/forecast/**`、`app/outlook/**`、`app/dirdef/**`、`app/data/session_calendar.py` 零差異。
  - S-A1-6：`sector_attestation.py`、`sector_runtime.py` 中 Grep `os.environ|getenv|dotenv` 零命中，同 T-36。
  - S-A1-7：Windows 實機，由 devops-sre 記錄：attestation 成功與失敗（刻意讓工作樹不乾淨）兩種情形下，三個視窗都照常啟動，最後出現 `Done.`。
  - S-A1-8：手冊、README 與任何 CEO 文件中，沒有任何把 attestation 寫成 CEO 步驟的句子（Grep `attest`）；手冊的修改符合 RC-430，由 qa 逐行確認。
  - S-A1-9：RC-421 觸發時的裁示，附上第 4 點的清單並逐項標類別。
  - S-A1-10：任何改動都沒有以放寬 C-36、以環境變數或 build arg、或請 CEO 手動執行 attestation 的方式來消除 NE-7（qa 審查項）。
<<<ADR-0012 補充結束>>>

- 起草時的判斷說明（不屬補充正文）：
  - 第 2 點 (b)(ii) 把 RC-421 的觸發 (ii) 也拿來當設計 (a) 的觸發。理由：一旦 NE-1～NE-6 可能全部消失，attestation 的缺口就會直接成為 CEO 看到的原因，期限也應該跟著提前。這比我先前「只看 N 達 120」更嚴。
  - 第 3 點 (c) 把「attestation 檔不存在或讀不到」也算成「commit 不同」。原本的寫法只有「commit 不同時才跑」，照字面在沒有檔案時永遠不會跑，所以要補上。

## 驗證
- 讀過：
  - ADR-0012 第 1～80、221～229、824～863、1140～1157 行，以及 C-36、C-52、NE-7 的 Grep；
  - product 版 `sector_attestation.py` 1～261 行全文；`gate.py` 40～74、380～499 行；`sector_board.py` 470～525 行；`sector_eval.py` 的 `selfchecks_passed` 與 `to_stats_record`（Grep）；`sector_runtime.py`、`definition.py`（Grep）；
  - 接線版 `canonical.py`（Grep `code_digest` 的涵蓋範圍）；
  - 我方先前報告的第二件全文；RC-419～RC-421 全文。
- 沒有查證：
  - `git status` 從子目錄執行時涵蓋整個 repo 這一點，依 git 的一般行為，沒有實機驗證；
  - NE-7 測試集的耗時；
  - `uv sync --locked` 與 `--frozen` 在 CEO 本機版本上的差異；
  - D0 與目前的 N；
  - 前端是否在其他地方顯示次要原因（沿用 RC-421 的 Grep）；
  - `sectorMomentumWording.ts` 的行號（沿用風控的引用，沒有重讀）。

## 下一步
1. coordinator：把區塊內容依原樣 append 進 ADR-0012（檔頭那一行接在第 77 行之後；正文接在第 1157 行之後）。替換來源中的代稱檔名後 commit，送風控做第 7 點 (a) 的知悉確認；追蹤清單依 S-A1-2 加列。
2. devops-sre：觸發時交設計 (a)，同時處理 C 的手冊更正。
3. **必須由 CEO 決定的事：** 只有補充一第 6 點 (a)、(b) 兩種情形。我目前不建議走 (a)。

---

相關路徑：
- `/home/user/AICompany/work/reviews/2026-11-21-手冊改判處理路徑與重啟請求R3-RC427至RC441-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-21-重啟請求定稿與手冊0.2及0.3節與attestation告知RC407至RC421-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-21-心跳確認書審查與attestation落差裁示與退役測試對應-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-21-手冊八項事實與避開時段確認-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-21-心跳確認書修訂版複核與手冊事實清單-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-19-收盤定案時點重新定案與補充十-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十三-待寫入-coordinator組版.md`
- `/home/user/AICompany/work/reviews/2026-10-26-dev-up讀env交件-devops-sre.md`
- `/home/user/AICompany/apps/stock-desk/README.md`
- `/home/user/AICompany/.claude/skills/local-run/SKILL.md`
- `/home/user/AICompany/apps/stock-desk/dev-up.bat`
- `/home/user/AICompany/apps/stock-desk/backend/.gitignore`
- `/home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md`
- `/home/user/AICompany/docs/adr/0026-stock-desk-庫存版本化軟刪除與還原點.md`
- `/home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md`
- `/home/user/AICompany/docs/adr/0029-stock-desk-維運告警通道.md`
- `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/recorder.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/store.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/schema.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/canonical.py`
- `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/backend/scripts/forecast_status.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/sector_attestation.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/sectors/gate.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/sector_board.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/backtest/sector_eval.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/sector_runtime.py`
- `/home/user/AICompany/apps/stock-desk/backend/app/sectors/definition.py`

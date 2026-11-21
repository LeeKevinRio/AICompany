# D-10 確認書審查、dev-up 與 attestation 的落差裁示、退役測試的對應物

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：D-10 確認書審查、dev-up 與 attestation 的落差、退役測試的對應物

三件分開寫，每件都用四段式。全程唯讀（Read／Glob／Grep），沒有寫檔，沒有讀 `.env`，沒有碰 `backend/data/`。

---

# 第一件：D-10 心跳責任確認書

## 本次結論

1. **確認書逐項滿足補充十三第 7 點 (b)**，和第 4、5、6 點以及 RC-360、361、367、368、378 都沒有牴觸。**可以當作第 7 點要求的書面確認，但附條件**：下面 M1～M8 要由 devops-sre 修改，我複核後才算數。修訂版的 commit 一樣要早於接線 PR 的合併 commit（第 7 點 (c)）。
2. **`STOCK_DESK_DB_PATH` 的發現只對了一半，漏掉的那一半比較危險。**
   - 「狀態報告 STOP，所以記錄也停了」：多半成立，但不是必然。
   - 反方向不成立：**`apps/stock-desk/.env` 有這個變數時，scheduler 每晚都會拒絕記錄，但狀態報告不會 STOP，照常印出。** 貼回上看起來只是「漏記」，甚至是「漏記（尚未開始記錄）」。
3. **部署手冊第 0.2、0.3 節建議設定 `STOCK_DESK_DB_PATH`，與補充九第 3 點直接衝突。**（tech-architect 建議）接線前改掉。
4. 兩項自訂規則：
   - 回覆時限同意，但要加一條：當天回覆就要寫明「需不需要 L2」。
   - 「不確定要連續兩次才轉 tech-architect」要調整：「漏記（尚未開始記錄）」這一型，第一次就轉。
5. 重啟：（tech-architect 建議）請風控在接線 PR 合併之前，先定稿一則「請執行一次 `dev-up.bat`」的請求。理由見下面 5.。

## 各部門回報（tech-architect）

### 1. 補充十三第 7 點 (b) 逐項對照

| 第 7 點 (b) 要求 | 確認書位置 | 結果 |
|---|---|---|
| 接下讀法、擔任責任人 | §1 | 符合 |
| 收到第 4 點 (a) 通知後怎麼查明原因 | §2 (三) | 符合 |
| 恢復時要不要重啟 | §2 (五) | 符合，要補 M7 |
| 哪些情形轉 tech-architect | §2 (六) | 符合 |
| 需要 CEO 做的事，經 coordinator、用風控定稿字面 | 檔頭第 12 行；§2 (三)(a)-1 第 4 步；(四) 末段；(五) 首段 | 符合 |
| 知悉第 5 點的不做事項、第 6 點的設計義務 | §3、§4 | 符合 |
| RC-361 (b)：什麼時候需要 L2 | §2 (四) | 符合，要補 M5 |

和第 4、5、6 點與風控條件逐條比過，沒有牴觸：
- (三)(c) 照 RC-378 的先後，先內部升級再送 CEO 訊息；
- (三)(d) 不要求 CEO 說明是否還原過備份；
- §4 的三種觸發與兩條讀取路徑的後果，和第 6 點 (a)(b) 一致，也寫了 RC-368。

只有一處要收緊（M4，RC-364 (b)）。

### 2. 事實抽查（接線版工作樹 `agent-a352324c9d164984b`）

**被跳過的執行：屬實，但不完整。**
- 四種 refusal：`scheduler.py` 668～683、699～709，784～786 行記一行 WARNING 後 `return None`。
- 指數重抓失敗：795～803 行。
- bar 早於本次執行開始：804～806 行。
- 以上都在 `record_forecasts`（810 行）之前結束，所以沒有 `begin_run`（`recorder.py` 363 行），也不留 `forecast_run`。
- 帳本 schema 不完整：`begin_run` 本身拋例外，由 `_guarded`（825～834 行）以 ERROR 記錄，不是 WARNING。確認書寫成「job 錯誤 log」，這是對的。
- **漏列三種**（見 M2、M3）：
  - `get_index_resolver()`（788 行）在任何 try 之外，它拋例外時同樣不留列；
  - 卡在強制重抓（790 行）時同樣不留列；
  - 程序開著、但主機在 22:10／23:10 處於睡眠或休眠。`forecast_record` 沒有設 `misfire_grace_time`（928～936 行，對照 `data_refresh` 有設，863 行），喚醒後很可能不補跑。這一點依 APScheduler 3.x 預設 1 秒寬限推論，**未查證本專案鎖定的版本**。

**`dev-up.bat` 的視窗沒有檔案 log：屬實。**
- `dev-up.bat` 150、166 行用 `cmd /k`，沒有導向。
- `logging_setup.py` 116～119 行只有 `StreamHandler(sys.stderr)`。

**`report status` 不印 `error_class`：屬實。**
- `report.py` 562～597 行只印各 outcome 的計數、「沒有 end 列」與最近一次的 `outcome`。
- 整個 `report.py` 沒有出現 `error_class` 這個字串（Grep 零命中）。

**六種原因在貼回上區分不了：大致屬實，但 E 的分類自相矛盾。**
- 確認書表頭說 A～F「完全相同」，可是 E 那一列自己寫「此時貼回會同時有沒有 end 列」。
- 依程式要分成兩種：
  - 卡在 `begin_run` 之前（強制重抓）：不留列，和 A 區分不了，留在表內；
  - 卡在 `begin_run` 之後（recorder 的 `_fetch`）：最近一次執行持續是「沒有 end 列」，會表現成第 2 點 (f) 的「中斷後沒有後續執行」，不屬於這張表。

**「中斷的執行」一段有一處不精確（M3）。**
- 確認書說「任何 Exception 都會寫 error 的 end 列」。
- 但 `end_run` 寫在 except 區塊裡（`recorder.py` 370～377 行）。`end_run` 本身失敗（例如資料庫被鎖、磁碟滿）時，不會再被接住，那一次就沒有 end 列。
- 也就是說，「沒有 end 列」不只來自 `BaseException` 或程序被結束。

### 3. `STOCK_DESK_DB_PATH`

**依據**
- 補充九第 3 點 (a)（`work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md` 138～145 行）：程序環境變數中有 `STOCK_DESK_DB_PATH`、即使是空字串，`forecast_record` 就不記錄。
- 實作在 `scheduler.py` 699～700 行。

**機制與兩種情形**
- `dev-up.bat` 本身不設這個變數。
- 但 `.env` 存在時，它設 `UV_ENV_FILE=apps\stock-desk\.env`（94～96 行），然後以 `uv run` 啟動 scheduler（166 行），`.env` 的內容就進入 scheduler 的程序環境。
- `forecast-status.bat` 第 11 行刻意清空 `UV_ENV_FILE`；`forecast_status.py` 225 行只看程序環境，不讀 `.env`（11～13 行）。

| 變數設在哪裡 | 狀態報告 | scheduler |
|---|---|---|
| (i) Windows 的使用者或系統環境變數 | STOP | 每次拒絕 |
| (ii) 只在 `.env` | **照常印出** | **每次拒絕** |
| (iii) 只在某個 PowerShell 視窗內暫設 | 不一定 | 不一定 |

- 情形 (iii) 是部署手冊 0.3 節的寫法。從哪個視窗啟動哪支程式，結果就不同；所以確認書「同一個條件也會讓 scheduler 每次拒絕」要改成「多半也會」。
- **情形 (ii) 在貼回上只會表現為「漏記」**（接線後從未記錄時是「漏記（尚未開始記錄）」），而且是**持續性**的，不會自己恢復。
- 我在 11-19 寫的「不讀 `.env`：`resolve_db_path` 只看程序環境變數」（同檔第 52 行），在程式層面正確，但我沒有指出 `dev-up.bat` 會把 `.env` 帶進程序環境。這裡更正。補充九的字面「設了 `STOCK_DESK_DB_PATH` 的部署不記錄」本來就涵蓋 (ii)，所以不需要改 ADR。

**在 CEO 機器上什麼時候會發生**
- 有人（含照手冊操作的 CEO）把它寫進 `apps/stock-desk/.env`，或設成 Windows 環境變數。
- 部署手冊 0.3 節（83～88 行）明文「建議顯式指定」`$env:STOCK_DESK_DB_PATH`，0.2 節表格也列為建議。這是現存的誘因。
- 手冊 0.2 節還說「程式不會自動讀取 `.env`」、`.env` 放在 `backend/`，兩點都和 `dev-up.bat` 現況不符（`dev-up.bat` 讀的是 `apps/stock-desk/.env`）。

**接線前能不能發現**
- 接線前那一次狀態報告的貼回：只能發現 (i)，發現不了 (ii)。
- **正式登記的預檢與 bootstrap 兩者都查**：接線版 `claims.py` 403～406 行同時拒絕 `env_db_path` 和 `env_file_db_path`（補充四第 2 點，ADR-0030 第 490 行）。所以登記成功本身，就證明登記當時兩處都沒有設。
- （tech-architect 建議）
  - 不新增任何工具檢查。補充十三第 5 點與 S-22 要求 `forecast_status.py` 零差異，也不新增 CEO 可見輸出。
  - coordinator 在登記紀錄中註明「登記成功，`env`／`.env` 檢查已通過（補充四第 2 點）」，作為接線前的時點證據。
  - 接線後若出現 (ii)，最慢在第一份有效貼回以「漏記（尚未開始記錄）」浮現，屬 fail-closed：不記錄，不會寫到別的檔案。
  - 部署手冊第 0.2、0.3 節在接線前改正。手冊不在 `code_digest` 涵蓋範圍內；面向 CEO 的字面歸風控。
  - 內部禁止事項：記錄期間，任何部門不得指示 CEO 在環境變數或 `.env` 設定 `STOCK_DESK_DB_PATH`；要改須經 tech-architect。

### 4. 兩項自訂規則

**回覆時限：同意。**
- 「當天回覆；21:00 之後收到者最遲次日 12:00」和 RC-378 的時限結構一致。
- 「書面處置紀錄最遲第 2 個平日」也同意。
- 加一條（M6）：**「是否需要 L2」與「是否需要重啟」，要寫在當天的書面回覆裡。** RC-361 (b) 要求 devops-sre 書面寫明需要 L2，coordinator 才能送；等 2 個平日，CEO 的記憶會更不可靠。
- 轉 tech-architect 的同日轉送附上分類即可，完整紀錄可以後補。

**「不確定」連續兩次才轉：調整（M5）。**
- 「連續」定義為：**下一份有效貼回**又出現列得出交易日、而且仍無法區分的漏記，不論日期是否相同。原字面「同一型態」太含糊。
- 例外，第一次就轉 tech-architect：
  - 「漏記（尚未開始記錄）」：沒有任何證據顯示接線後曾經正常過，而持續性原因（D、`.env` refusal）不會自己恢復；
  - 同一次已觸發第 6 點 (a) 第二項（5 個以上平日）。

### 5. 重啟

技術上確實需要重新執行 `dev-up.bat`（它會先 `git pull`，再停掉舊程序、重新啟動）的情形：

- **D**：舊 scheduler 還在跑。另外兩種會讓舊程序留著的情形也屬於 D：
  - 執行 `dev-up.bat` 時對停止舊 scheduler 的提示回答 N（`dev-up.bat` 283～294 行，`exit /b 1`）；
  - `git pull` 失敗，或工作樹有 tracked 變更而停止（68～73、110～114 行，都在停舊程序之前就 `goto fail`）。
- **E**：執行卡住。重新執行會以 `taskkill /F /T` 結束卡住的那一次（295 行），那一筆留下沒有 end 列。
- **checkout 未更新**：`forecast-status.bat` 不會更新程式（7～8 行）。

重啟無效的情形：
- `gate_closed`（同意確認書 (五) 第 5 點）。
- `.env` 或環境變數的 refusal：要改設定，不是重啟（M7）。
  - 若變數指向的不是預設檔，拿掉它會讓 backend 改用另一顆主 DB。這是資料位置的決定，須經 tech-architect 與風控，必要時由 CEO 決定。

是否列為前置（tech-architect 建議）：
- **列為接線 PR 合併的前置，放在追蹤清單層級，和 RC-381 的 U1～U4 同一層，不改 ADR 字面。**
- 理由：
  - D 是接線後第一週最可預見的失效。給 CEO 的記錄條件通知寫「接線合併之後，您下一次那樣啟動就會開始記錄」（`work/dispatch/2026-11-20-預測記錄條件通知-CEO-草稿.md` 111 行），CEO 若一直開著 stock-desk，就不會有「下一次啟動」。
  - 既有的 H1、H1b、H2、L1、L2 都寫「不要重新啟動任何程式」，臨時起草容易和既有字面衝突。
  - 而前 4 週正是 RC-326 認定的關鍵期。
- 一則定稿可以涵蓋 D、E、checkout 未更新三種情形。要不要寫「出現停止舊程式的提示時回答 Y」，歸風控決定。
- 若風控認為不必預先定稿，就照第 4 點 (f) 在發生時送；因為是 fail-closed，可以接受，代價是漏記的天數。

### 6. 修改清單（由 devops-sre 改，我複核）

- **M1**（§1 第 4 點；§2 (二)「無法比對」；(三)(a)-4；(六) 第 5 項）
  - 改寫成上表的 (i)～(iii)；「同一個條件也會」改為「多半也會」。
  - 補 (ii)：`.env` 有設時，記錄停止、報告正常，表現為漏記。
  - (六) 第 5 項擴大為「判斷可能是 `STOCK_DESK_DB_PATH` refusal 的任何情形」。
- **M2**（§2 (二) 漏記表）
  - E 拆成 `begin_run` 之前與之後兩種。
  - 新增 G：主機睡眠或休眠跨過排程時刻（標「推論，未查證」）。
  - D 補上 `git pull` 失敗與 tracked 變更 STOP。
  - C 分成單次型（重抓失敗、bar 早於開始）與持續型（四種 refusal、schema 不完整）。
  - 在 (四) 的「有開著」處置註明：這個回答排除不了 D、G 與持續型 C。
- **M3**（§2 (二) 中斷的執行）
  - 加上 `end_run` 本身失敗也不留 end 列。
  - 加上 `begin_run` 之前的例外不留列。
- **M4**（§2 (二) F-2、(三)(c) 第 2 步、(七)）
  - 不寫「分子以 a 或 b 為主」，這是由兩個整數導出的新判斷，不在 RC-364 (a) 的範圍內。改為只轉引比對紀錄對 a、b 各自「增加／相同」的結論。
  - (七) 改為「不得寫入任何整數差，含轉引自比對紀錄者」（RC-364 (b)）。
- **M5**：「不確定」規則，照第 4 小節修改。
- **M6**：時限，照第 4 小節加一條。
- **M7**：§2 (五) 第 2 點補上「refusal 不是重啟能解決」與資料位置的但書；第 3 點改為引用預先定稿的請求（若風控定稿）。
- **M8**（§2 (三)(a)-4）
  - (i) 缺「最近一次…」那一行，也可能是貼回不完整，不只是舊版 `report`。
  - (ii) 註明：第二段的 STOP（`STOP_VERIFY`，`forecast_status.py` 130～134、249～251 行）出現在第一段之後，那份貼回仍是有效貼回，不屬於「無法比對」。

## 驗證

- 讀過：確認書全文；交件說明；補充十三組版檔全文；RC-360、361、366～368 全文；RC-378。
- 接線版程式：`scheduler.py` 全文；`recorder.py` 240～429 行；`report.py` 510～599 行；`logging_setup.py`；`claims.py` 286～415 行。
- 狀態工具與啟動檔：`forecast_status.py` 全文、`forecast-status.bat`、product 的 `dev-up.bat`。
- 文件：ADR-0030 478～532 行；補充九裁示 40～149 行；部署手冊全文。
- 沒有查證：
  - uv 的 `--env-file` 會不會把空值 `STOCK_DESK_DB_PATH=` 當成「有設」，以及 `export KEY=` 的寫法；
  - APScheduler 鎖定版本的 misfire 預設；
  - Windows 上的實際行為；
  - CEO 實際有沒有照手冊設過這個變數；
  - 接線版的 `dev-up.bat` 是否與 product 版相同（我讀的是 product 版）。

## 下一步

1. devops-sre 依 M1～M8 修改確認書，送我複核。複核通過後 commit，而且要早於接線 PR 的合併 commit。
2. 風控：決定是否在接線 PR 合併之前預先定稿「請執行一次 `dev-up.bat`」的請求（建議要）；一併確認部署手冊 0.2、0.3 節改正後面向 CEO 的字面。
3. devops-sre：改正部署手冊 0.2、0.3 節，和進行中的 0.1 節改寫一起處理，建議在接線之前完成。
4. coordinator：在登記紀錄中註明 `env`／`.env` 檢查已通過；追蹤清單加上「重啟請求預先定稿」一列。
5. 這一件沒有需要 CEO 決定的事。

---

# 第二件：`dev-up.bat` 與 build attestation（ADR-0012）

## 本次結論

1. **性質：是 C-52 適用範圍內、沒有被履行的部署約束，屬於實作與流程缺口，不在 C-52 範圍之外。**
   - 結果是 fail-closed，安全：只會少列示歷史比例，不會多列。dev-up 路徑上沒有會變成 fail-open 的情形。
2. （tech-architect 建議）
   - **現在採「限期的 (b)」**：寫明這是已知、暫時接受的缺口，並設觸發條件。
   - **到期前落地改良版的 (a)**。
   - **否決 (c)**。
   - 若要採「永久的 (b)」，需要 CEO 決定。
3. 不排在正式登記或接線之前；和 ADR-0030 無關，同意 devops-sre 的說法。
4. 不需要立刻讓 CEO 知悉。

## 各部門回報（tech-architect）

### 1. 性質

**為什麼屬於 C-52 範圍**
- `dev-up.bat` 就是 K1 的主機形態：在同一個 checkout 的 `backend` 目錄以 `uv run` 直接啟動 API 與 scheduler（150、166 行），git 可用，`tests/` 存在。
- C-52（ADR-0012 858 行）要求「且已在該 checkout 跑過 `attest_sector_gate.py`」，`dev-up.bat` 沒有這一步。
- K3（227 行）只把「NE-7 恆成立」接受為「K1 落地前的 fail-closed 現況」。K1 已由 CEO 在 2026-09-25 裁定採用，所以不能援引 K3，說 dev-up 路徑已經被接受。

**fail-closed 的鏈條**
- `read_attestation` 讀不到檔時回 `None`（`sector_attestation.py` 194～199 行）。
- `verify` 因此列入 `attestation_missing`（250～251 行）。
- `check.ok` 為 false，寫入 `selfcheck_passed=false`（`sector_board.py` 481～513 行）。
- `gate.py` 461～466 行加入 NE-7。注意：只在已有統計列（`stats is not None`，457 行）時才加。

**有沒有 fail-open**
- dev-up 路徑不會產生 attestation 檔，所以沒有。
- 理論上的弱點都需要先有 attestation 檔存在，而且都屬 ADR 已揭露的設計限制：
  - 本機自我證明（430 行）；
  - 不綁定已安裝的依賴（1096 行）。
- 所以 (a) 落地時，attestation 一定要排在 `uv sync` 之後。

**一個會影響 (a) 的事實**
- 判定當下，`verify` 也會跑 `git status --porcelain`，連未追蹤檔都算（110～112、246～249 行）。
- 所以即使啟動時 attestation 成功，CEO 機器上只要出現任何沒有被 ignore 的未追蹤檔，之後的判定照樣是 `dirty_worktree`，也就是 NE-7。
- (a) 只能降低 NE-7 的機率，不能保證。

### 2. 三個選項

**(a) `dev-up.bat` 加 attestation 步驟**
- 代價：
  - 每次啟動多跑 `pytest -m sector_ne7`，耗時未實測；
  - 新的失敗點：有未追蹤檔時 exit 2；
  - `dev-up.bat` 視窗新增的固定行，要經風控；
  - 在預測記錄期間改動 CEO 唯一的啟動器。
- 硬性約束：**attestation 失敗絕不能阻擋啟動**，只記錄、照常往下。否則族群動能的問題會變成預測紀錄的漏記。
- 改良：只在 HEAD 與 attestation 的 commit 不同時才跑；排在 `uv sync` 之後、scheduler 啟動之前。
- 需要 qa-reviewer 與風控；不需要 CEO 決定，它履行的正是 CEO 已裁定的 C-52。

**(b) 文件寫明**
- 限期版：寫明「目前 dev-up 路徑下恆為 NE-7，是已知缺口，N 達 120 之前要落地 (a)」。
  - 這仍在 K3「K1 落地前現況」的範圍內，不需要 CEO 決定。
  - 由我起草 ADR-0012 的補充紀錄，手冊同步更新。
- 永久版（不設期限）：等於把 CEO 裁定的 K1 退回 K3，N≥150 之後卡片永遠不列歷史比例，也改變了 CEO 已接受的「約 3 年」時程（1152 行）的實際意義。**必須由 CEO 決定。**

**(c) 修訂 C-52**
- 否決。C-52 本身沒有錯，缺的是履行。放寬 C-36 是 ADR 明文禁止的（71、859 行）。

### 3. 時程

- NE-1、NE-2、NE-3 什麼時候消失：
  - NE-2 要 N≥150 而且 N_eff≥60，內部下限是 D0 之後約 3.1 年（715～717 行），缺日與相依都會再拉長；
  - NE-3 要等 DE-10 的費率查證完成（1122 行）；
  - NE-1 要等 PIT 歷史齊全。
- **NE-7 最早要在 D0 之後約 3.1 年，才可能成為 CEO 看到的主要原因。** D0 是否已發生，我沒有查證。
- 所以觸發條件（tech-architect 建議）：N 達 120 時，devops-sre 交出 (a) 的設計。依每年約 49 個樣本估算，大約提前 7 個月。之前若因為其他原因改寫 `dev-up.bat`，就一併處理。
- 補充：API 的 `not_evaluated_reasons` 清單一定會輸出（655 行），所以現在清單中已含 NE-7。前端會不會顯示次要原因，我只看到測試檔的命中，**沒有查證**。

### 4. 要不要讓 CEO 知悉

- 不需要立刻告知。CEO 現在看到的原因（NE-1／NE-2）是真的。這個缺口在 3 年內不會影響任何畫面，而且在那之前就會修好。
- 該讓 CEO 知道的事實只有一句的內容：「目前的啟動方式少了一步，若不補上，累積期滿後歷史比例也不會列出；團隊預計在那之前補上。」
- 時點：下一次非急迫的總結時；**不要和預測紀錄的通知或 A、B 兩份文件放在一起**，以免混淆。字面歸風控。
- 若團隊選擇永久版 (b)，就變成需要 CEO 決定的事。
- 不得請 CEO 自己手動執行 attestation。

## 驗證

- 讀過：
  - ADR-0012 第 71、225～227、427～430、857～859、1096～1097、1150、1157 行，以及 NE-2／NE-3／DE-10 相關行；
  - `sector_attestation.py` 84～112、150～261 行；
  - `gate.py` 56～66、420～489 行；
  - `sector_board.py` 470～524 行；
  - `attest_sector_gate.py` 的拒絕條件；
  - 部署手冊全文；
  - `dev-up.bat` 全文。
- 沒有查證：
  - `sector_runtime.py`、`sectorMomentumWording.ts`（沿用 devops-sre 的行號，沒有重讀）；
  - NE-7 測試集的耗時；
  - `uv sync --locked` 會不會裝 dev 群組；
  - D0 與目前的 N 值。

## 下一步

1. tech-architect：起草 ADR-0012 的補充，內容是限期 (b) 與 N 達 120 的觸發條件，送風控（只看面向 CEO 的部分）。
2. devops-sre：更新部署手冊（攻擊面與第一件的 0.2、0.3 節一起處理）；在後續追蹤清單第 678 行記下裁示；把 N 達 120 的觸發列入追蹤。
3. 需要 CEO 決定的事：**只有在要採永久版 (b) 時**才需要。理由是它實質推翻 CEO 在 2026-09-25 裁定的 K1。目前我不建議這樣做。

---

# 第三件：退役分支 NOTE 1

## 本次結論

1. **「兩組規則端對端各 21 次全過」在退役後仍有測試守著。** 被刪測試沒有值得搬移的獨有斷言，這不是補充十二第 1 點的規格問題，不需要處置。
2. 更正 qa 的一句：被刪測試**沒有**走真實的 `h3.yaml`／`h5.yaml`，用的是佔位規則 P-0／P-1。所以退役也沒有失去任何「真實規則」的端對端路徑。

## 各部門回報（tech-architect）

**保留的 harness 測試**（`test_forecast_pipeline_harness.py`）
- 128～144 行與 147～159 行都以 `[P0, P1]` 參數化。斷言 `failures == []`、`passed`、21 次全為 `ok`、寫入 42 筆、`(records, verified, insufficient) == (42, 42, 0)`、`labels_checked == 42`、輸出雜湊穩定、D-4 零違規。
- 517～535 行逐行斷言 P-1 的摘要字面，也斷言失敗時的摘要。

**被刪的測試**（flow 測試 1049～1055 行）
- 斷言的是退役工具回貼檔的文字：「管線驗收 P-0／P-1：通過」、`執行次數：ok=21` 出現兩次、`失敗種類：無` 出現兩次、兩行雜湊各兩次。
- 它的結果層級對應物在保留的測試中都有，而且更嚴。
- 唯一沒有字面對應的是 P-0 摘要那一行。但 `render_summary` 是同一個泛用函式，而且退役後它只剩 harness 與它的測試在用（Grep 只有 4 個檔），沒有任何面向 CEO 的使用者。不需要補。

**P-0／P-1 是佔位規則的依據**
- `forecast_pipeline_harness.py` 171～172 行定義 P0、P1 為佔位規則。
- `pipeline_acceptance_real.py` 104～105、249、859 行只用 `(P0, P1)`。

**掃過 flow 測試全部約 95 個測試函式名稱**（304～1728 行），全部屬於退役工具本身：
- STOP 各情境、複本與 WAL 處理、清理、白名單、回貼格式、固定句、例外鉤子、port 檢查、AST 掃描、`.bat` 啟動器。

逐一看過幾個可疑的候選，都隨工具消失：
- 1115 行（兩種標籤分布給出同樣的回貼）：守的是工具回貼對 CEO 不洩漏標籤，對象已不存在。
- 1375 行（snapshot bar 同一物件）：腳本與 app 的耦合。
- 486～531 行（WAL 複本）：工具自己的複本函式。
- 1034 行（回貼值來自程式與 repo）：工具。

## 驗證

- 讀過：harness 測試 100～164、497～560 行與全部函式名稱；flow 測試全部函式名稱與 1040～1120 行；qa 複審全文。
- 沒有逐行讀完 flow 測試的 1745 行，只讀了名稱與可疑段落。

## 下一步

1. qa-reviewer：NOTE 1 可以結案，不需要補測試。
2. 退役分支照 qa 標明的順序合併：登記、一鍵檔退役、本分支。
3. 這一件沒有需要 CEO 決定的事。

---

相關路徑：
- `/home/user/AICompany/work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/recorder.py`
- `/home/user/AICompany/.claude/worktrees/agent-a352324c9d164984b/apps/stock-desk/backend/app/forecast/claims.py`
- `/home/user/AICompany/.claude/worktrees/agent-ab5f1bf75d430b1de/apps/stock-desk/forecast-status.bat`
- `/home/user/AICompany/apps/stock-desk/dev-up.bat`
- `/home/user/AICompany/apps/stock-desk/docs/族群動能-主機部署手冊.md`
- `/home/user/AICompany/apps/stock-desk/backend/app/services/sector_attestation.py`
- `/home/user/AICompany/docs/adr/0012-stock-desk-族群動能與全市場日線.md`
- `/home/user/AICompany/work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_forecast_pipeline_harness.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py`

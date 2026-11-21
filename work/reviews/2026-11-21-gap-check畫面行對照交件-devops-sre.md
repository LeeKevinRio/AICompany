# gap-check 畫面行與 R 系列觸發字樣對照交件（RC-477 第 5 點）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
表已寫好：/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gap_check_screen_lines.md（head 243596c，用 git show 讀 gap-check.bat 與 gap_check.py；沒有 checkout、沒有改檔）。

gap-check 畫面上只會出現下列幾種行：
- **`.bat` 印的方括號行**：
  - `[MISSING] uv ...`（18 行）：屬 RC-342，不屬 R3-0。
  - `[ERROR] Cannot find the backend folder...`（25 行）：屬 R3-0，也屬 RC-342。
  - 這兩種後面各接一行不是方括號的 `Tell the coordinator.`／`Do not move or change...`。
  - 兩種都發生在 `uv run` 之前，沒有啟動 python、沒有寫檔、沒有碰資料庫，也還沒請 CEO 關視窗。之後走 `:fail`：`pause`、`exit /b 1`。
  - `[NOTE] The tool ended with code N`（33 行）：只有結束碼不是 0 才印，不屬任何 R 觸發字樣。
- **`.py` 的 `STOP:` 14 句**：
  - 全部不是方括號，也都不在 R3-0／R3-0C／RC-342 清單裡。
  - 草稿統一放在第十一節（309～322 行）。
  - 結束碼都是 3。
  - 8 句停在 preflight，沒寫檔；5 句發生在複本做出之後，先刪複本才印；另有 1 句是複本刪不掉。
- **`.py` 的 `ERROR:` 2 句**：
  - 這兩句不是 `[ERROR]`，不屬 R3-0。
  - `ERROR: unexpected failure...` 的結束碼是 1，`ERROR: interrupted...` 是 2。
  - 草稿 323、324 行有對應。
- **其他**：
  - 提示語 `Close the stock-desk backend, scheduler and frontend windows, then press Enter.` 只要按 Enter。
  - 成功時印 17 行 `key=value` 結果。
  - 沒有 `[TIMEOUT]`、`[FAILED]`、`[STOP]`、`[FAIL]`，沒有要求重新開機的句子，沒有 `Cancelled.`。
- **單列的三項答案**：
  - 沒有 Y／N 提示；唯一的 Y／N 是 Ctrl+C 時 cmd 自己問的 `Terminate batch job (Y/N)?`，不是檔案印的（草稿 181 已提）。
  - 沒有 `Done.` 或任何結束字樣。
  - 所有出口都 `pause`（34 行與 39 行）。
- **整支工具不關閉也不重啟任何 stock-desk 視窗**，只請 CEO 自己關。

## 各部門回報（devops-sre）
表中每一列都寫了行號（`.bat`／`.py`）、前面已執行與尚未執行的步驟、之後流程、是否屬 R 系列，以及草稿行號。我發現的幾個事實，請風控與 creative-lead 看：
1. **草稿 303 之外，還有四處允許 CEO 自己再執行。**
   - 312：port 8000 那列寫「重新雙擊 gap-check.bat」。
   - 313：第 9 句那列寫「重新雙擊 gap-check.bat 執行一次」。
   - 273：重跑規則第 5 點寫「排除原因後可以再執行」。
   - 256：後半句指向 312、313。
2. **英文固定句本身就含再執行的指示。**
   - port 8000 那句寫「run again」，db_in_use 那句寫「run this again」（`.py` 157～159、173～179 行）。
   - 只改中文欄擋不住畫面上的英文原句，這兩句是已核可字面，改動要風控決定。
3. **兩行連續出現的情形。**
   - preflight 階段停下時，sweep 還沒跑，前一次殘留的複本沒被清；結束前會補印「複本刪不掉」那句，變成兩行。
   - 874 行 `finally` 內刪複本失敗，會蓋掉原本的 STOP，只剩「複本刪不掉」一句。
   - 草稿 328 沒寫「preflight 停下時不會清殘留」。
4. **R3-0 內文套用性。**
   - `[ERROR]`（25 行）發生時，gap-check 什麼都沒動過，也還沒請 CEO 關視窗。
   - R3-0 內文若有「stock-desk 可能沒關著」之類針對 `dev-up.bat` 的敘述，用在這一行是否合適，請風控判斷；我沒有替它歸類。
5. **`uv` 自己的錯誤文字沒涵蓋。** `uv run --no-sync` 失敗時印的行與結束碼由 uv 決定，不在白名單，草稿與這張表都沒涵蓋。

## 驗證
- 讀過：兩個檔全文（`.bat` 40 行、`.py` 972 行）；RC-477 與 R3-0、R3-0C 定稿；我先前寫的 5.2 表；帳外缺日草稿的相關行（167、174、176、181、256、273、299～336）。
- 實際核對：STOP／ERROR 固定句共 16 句，與草稿第十一節表 309～324 行逐列對上。
- 沒有驗證的事：
  - 所有 `.bat`、`.py` 都沒執行過，Windows 實機一律未驗證，包括 `pause` 字面與語系、Ctrl+C 的 Y/N、記事本開啟、檔案鎖定與防毒。
  - Python `finally` 蓋例外、`input()` EOF 等行為只是依原始碼推得。
  - `uv` 失敗時的畫面與結束碼未知。
  - R3-0／R3-0C 只核對觸發字頭，沒有逐字比對內文。
  - 兩支 `.bat` 對主 DB 的「只讀」事實前置（RC-477 第 9 點）屬 tech-architect，我沒查證。
  - `r2-probe.bat` 沒看（RC-477 第 5 點有點名，但本次任務只要求 gap-check）。
  - 沒讀 `.env*`，沒碰 `backend/data/`。

## 下一步
- 風控：依第 3 節與第 5 節，判斷上述 1、2、4 要不要納入 RC-477 第 3 點的修訂範圍。
- creative-lead：等風控裁示後再改草稿；表中草稿行號是目前檔案的行號，改動後會位移。
- tech-architect：補 RC-477 第 9 點的事實前置。
- 若要補 `r2-probe.bat` 的同類表，請另派。

---

## 附件：對照表全文（devops-sre 寫於 scratchpad，coordinator 逐字附上）

# gap-check.bat／gap_check.py 畫面行對照（RC-477 第 5 點；devops-sre 書面）

- 對象：分支 `feat/gap-check-oneclick` head `243596c45616469c35b4b9b7585480cebf614c3b`，以 `git show` 讀 `apps/stock-desk/gap-check.bat`（40 行）與 `apps/stock-desk/backend/scripts/gap_check.py`（972 行）。
- 草稿：`work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md`（第三版，360 行上下；以下「草稿 N」＝該檔第 N 行）。
- 全部依讀原始碼推得，**沒有執行任何 `.bat` 或 `.py`，Windows 實機一律未驗證**。本文件只列事實，不替任何一列做 R 系列以外的歸類，也不下「安全」「沒有影響」之類的判斷。

## 0. 整體順序（先看這個，後面各表才好讀）

1. `.bat` 29 行以前：設 `UV_ENV_FILE` 為空、算路徑、`where uv`（16 行）、`cd /d backend`（23 行）。都沒有寫檔、沒有碰資料庫、沒有關任何視窗。
2. `.bat` 30 行：`uv run --no-sync python -I -X utf8 scripts\gap_check.py`，之後畫面行由 `.py` 印。
3. `.py`：（a）全域 hook 與 import（39～72 行）；（b）印出提示語 `Close the stock-desk backend, scheduler and frontend windows, then press Enter. `（常數 97 行，`wait(PROMPT)` 在 864 行，用 `input()`，**不換行**，等 Enter）；（c）`preflight`（866 行，函式 766～802 行；只讀，不寫檔）；（d）`sweep_residue`（867 行；**可能刪除前幾次留下的複本**）；（e）建立工作資料夾 `<使用者資料夾>\stock-desk-gap-check\<時間戳>`（869 行）；（f）`make_copy`（872 行，函式 576～609 行；建 `copy` 子資料夾並用 SQLite backup API 複製）；（g）`read_trade_dates`（872 行，函式 612～634 行）；（h）`delete_copy`（874 行，在 `finally` 內，**先於任何結果行**）；（i）抓證交所日曆（877 行，最久約 13.7 分鐘，沒有畫面輸出）；（j）比對、算 `script_sha256_lf`（878～880 行）；（k）寫 `paste-back.txt`（882～883 行）；（l）印 17 行結果（884～885 行）；（m）開記事本（887～893 行，失敗只忽略，不印字）；（n）回傳 0。
4. `.bat` 31～35 行：`echo.`、若結束碼不是 0 印 `[NOTE] ...`、`pause`、`exit /b %RC%`。
5. **這支工具從頭到尾沒有關閉、重新啟動任何 stock-desk 視窗或程序**（只有 `input()` 請 CEO 自己關）。`.py` 唯一的外部程序是 `git`（`run_git`，712 行起，唯讀的 `rev-parse`／`status`／`merge-base`）。對主資料庫只用 `mode=ro&immutable=1` 開啟並讀取（548～609 行，原始碼註解與 docstring 所述，沒有實測）。

## 1. `.bat` 自己印的行（4 種）

| 開頭字樣與完整字面 | 哪裡印、第幾行 | 印出時已執行 | 尚未執行 | 之後流程 | 屬於哪個觸發字樣 | 草稿提到 |
|---|---|---|---|---|---|---|
| `[MISSING] uv was not found. Do not install or update anything yourself.`，緊接下一行 `Tell the coordinator.`（這一行不是方括號開頭） | `.bat` 18、19 行 | 只有 `set` 變數與 `where uv`（11～16 行）。**沒有** `cd`、沒有啟動 python，沒有寫任何檔、沒有碰資料庫、也還沒有要求 CEO 關視窗（要求關視窗的提示語在 `.py` 864 行） | 20 行以後：`cd`、`uv run`、整個 `.py` | `goto fail`（20 行）→ 37 行起：`echo.`（空行）→ `pause`（39 行）→ `exit /b 1`（40 行）。**不繼續** | **RC-342**（`[MISSING]`）。不是 R3-0（R3-0 清單沒有 `[MISSING]`）、不是 R3-0C | 草稿 299：「`[MISSING]` 或 `[ERROR]` 開頭的一行（中括號、沒有冒號），表示工具還沒開始執行，沒有讀取您的資料庫」，並叫 CEO 不要自己安裝或更新。**沒有**提到下一行 `Tell the coordinator.` |
| `[ERROR] Cannot find the backend folder next to this file.`，緊接下一行 `Do not move or change any file or folder yourself; tell the coordinator.`（不是方括號開頭） | `.bat` 25、26 行 | 上一列的全部，再加 `where uv` 通過（16 行）；`cd /d "%BACKEND_DIR%"` 失敗（23 行）。仍然沒有啟動 python、沒有寫檔、沒有碰資料庫、還沒要求關視窗 | 30 行以後 | `goto fail`（27 行）→ `echo.`、`pause`、`exit /b 1`，**不繼續** | **R3-0**（`[ERROR]` 開頭）**與 RC-342**（`[ERROR]`）。不是 R3-0C | 草稿 299（同上一列的句子，涵蓋 `[ERROR]`） |
| `[NOTE] The tool ended with code N`（`N` 是 `%RC%`，變數；字面為 `[NOTE] The tool ended with code ` + 數字 + `. Read the messages above.`） | `.bat` 33 行 | 整個 `uv run`（30 行）已結束。`.py` 已印完它要印的行、已做完它的清理（視當時階段而定，見第 2 節） | `pause`（34 行）、`exit /b %RC%`（35 行） | **只有結束碼不是 0 才印**（`if not "%RC%"=="0"`）。印完 `pause`（34 行），`exit /b %RC%`（結束碼 `RC`） | **不屬於任何 R 系列觸發字樣**：不是 R3-0 的五個字頭，也不是 RC-342 的 `[MISSING]`／`[ERROR]` | 草稿 299：「`[NOTE] The tool ended with code` 那一行與『請按任意鍵繼續』是固定的結尾文字，不必理會」；也見草稿 23（備註） |
| （`pause` 自己的提示，Windows 系統文字，不是檔案裡寫的字） | `.bat` 34 行（正常與非 0 結束）、39 行（`:fail`） | 同上 | `exit /b` | 按任意鍵後結束視窗。**每一條路徑都以 `pause` 收尾**，沒有不 pause 的出口 | 不是（不是 `[`、`STOP:`、`ERROR:` 開頭） | 草稿 299 稱之為「請按任意鍵繼續」；實際字面依 Windows 語系，沒有查證 |

結束碼對應（原始碼推得）：`0`＝完成並印出結果；`3`＝`STOP:`（或 `STOP: ... could not be deleted` 補印，見第 2 節）；`2`＝`ERROR: interrupted`；`1`＝`ERROR: unexpected failure`；其他值（例如 uv 自己失敗）是 `uv` 傳回的值，不在這支工具控制內。

## 2. `.py` 印的行

全部經過 `say()`（265～269 行）：不在白名單（227～248 行）、也不是固定句的行，或含非 ASCII 的行，一律不印，改走 `ERROR: unexpected failure`（952 行）。所以畫面上由 `.py` 印出的行只有：提示語 1 行、固定句 16 句（`STOP:` 14 句＋`ERROR:` 2 句）、結果 17 行（全是 `key=value` 形式，開頭不是 `[`、`STOP:`、`ERROR:`）。

### 2.1 提示語（不是 `STOP:`／`ERROR:`／方括號）

| 行 | 位置 | 前面已執行／尚未 | 之後 | R 系列 | 草稿 |
|---|---|---|---|---|---|
| `Close the stock-desk backend, scheduler and frontend windows, then press Enter. `（尾端有空格，沒有換行） | `.py` 常數 97 行，`wait(PROMPT)` 864 行 | 已執行：只有 `.bat` 全部前置與 `.py` 啟動；**尚未** preflight、沒有寫檔、沒有碰資料庫。要 CEO 自己關三個視窗，工具本身不關任何視窗 | 等 CEO 按 Enter 後才往下走；**這是工具唯一等輸入的地方，不是 Y／N**（只要 Enter）。stdin 無法讀時（例如 EOF）會走 `ERROR: unexpected failure` | 不屬於 | 草稿 19（備註）、163～165（第三節步驟 5） |

### 2.2 `STOP:` 開頭的 14 句（全部不是方括號，**全部不在 R3-0／R3-0C／RC-342 的觸發清單裡**）

共同事實：
- 都印在 `main()` 的 `except RunStop`（944～947 行）：先 `say(str(stop))`（945 行），結束碼 `3`，接著走到 954～957 行再做一次 `cleanup`，再到 960～967 行檢查有沒有複本留著（見 2.4）。
- 印完之後：`.py` 回傳 3 → `.bat` 33 行印 `[NOTE] The tool ended with code 3.` → `pause` → `exit /b 3`。**不繼續比對、不產生 `paste-back.txt`、不印任何 `result=` 行**。
- 草稿目前處理方式：統一放在草稿第十一節（297～324 行）。草稿 299 把 `STOP:` 定義為「工具依設計主動停下」；草稿 167、174、176、273 都以 `STOP:`／`ERROR:` 字頭認列；草稿**沒有**把 `STOP:` 與 R3-0 掛鉤（草稿是給 CEO 的文件，本來就不談 R 系列）。
- 「前面已執行」的階段用 P3～P7 代號：P3＝preflight 中；P4＝sweep_residue 中；P5＝建立工作資料夾之後、複製之前；P6＝複製中；P7＝讀複本、刪複本。每一列都不含任何視窗被關閉的動作（工具不關視窗）。

| # | 固定句字面（`STOP:` 開頭；無變數） | 定義行／raise 行 | 階段與前面已執行／尚未執行 | 草稿位置 |
|---|---|---|---|---|
| 1 | `STOP: STOCK_DESK_DB_PATH is set in the environment.` | 154／776 | P3，是 preflight 的第 1 項檢查。已執行：提示語、CEO 已按 Enter。尚未：其他全部。沒有寫檔、沒有複製、沒有建資料夾 | 309 |
| 2 | `STOP: STOCK_DESK_DB_PATH is set in the .env file of the app.` | 155／778 | P3 第 2 項（`env_file_sets_db_path` 讀 `.env`，**只在記憶體內比對鍵名，不印內容**，758～763 行）。沒有寫檔 | 310 |
| 3 | `STOP: stock-desk.db was not found at the default location.` | 156／780 | P3 第 3 項。沒有寫檔 | 311 |
| 4 | `STOP: something is listening on port 8000; close the stock-desk windows and run again.` | 157～159／782 | P3 第 4 項（對 127.0.0.1:8000 連一次，742～750 行）。已執行：前三項檢查通過。尚未：git 檢查、sweep、複製。沒有寫檔。**這句出現代表 CEO 按 Enter 時 8000 埠仍有程式在聽**（通常是 backend 還開著），這是少數 stock-desk 很可能還開著的情形 | 312（含「重新雙擊」） |
| 5 | `STOP: the work folder would be inside a git work tree.` | 160／784 | P3 第 5 項。沒有寫檔 | 314 |
| 6 | `STOP: git could not be used on the code folder.` | 161／787、792、798 | P3 第 6～8 項之一（`rev-parse --show-toplevel`／`status`／`rev-parse HEAD`）。三處都用同一句，所以這句**不能分辨是哪一步** | 315 |
| 7 | `STOP: the code folder has uncommitted changes.` | 162／794 | P3，`git status --porcelain` 在 `app`、`tests`、`scripts`、`uv.lock`、`../gap-check.bat` 發現有改動（93 行）。沒有寫檔 | 316 |
| 8 | `STOP: this code version is not on origin/product/stock-desk.` | 163／801 | P3 最後一項（`merge-base --is-ancestor HEAD origin/product/stock-desk`）。沒有寫檔 | 317 |
| 9 | `STOP: the database may be in use, or it changed while it was being copied, so the check did not continue. Close the stock-desk backend, scheduler and frontend windows, then run this again. Do not delete or change any file yourself; if this line appears again, tell the coordinator and do not run this again.` | 173～179／587、606 | P6。兩種時點：（a）587 行，複製**之前**發現主資料庫旁有 `-wal`／`-journal`，尚未建 `copy`；（b）606 行，備份做完後主資料庫的大小或修改時間變了，或旁邊冒出 side file，此時**已建立 `copy` 並做過備份**，會在 874 行 `finally` 先刪複本再印這句。已執行：preflight 通過、sweep 完成、工作資料夾已建立（869 行）。尚未：讀複本、抓日曆、寫 `paste-back.txt`。這句本身寫「再執行一次」 | 313（草稿把這句的中文欄寫成「重新雙擊 `gap-check.bat` 執行一次」，與 RC-477 第 3 點衝突，見第 5 節） |
| 10 | `STOP: a copy of the database could not be made, so the check did not continue. Do not change any setting or file yourself; tell the coordinator.` | 181～185／591、608 | P6。591 行：取主資料庫大小與時間失敗（此時**尚未**建 `copy`）；608 行：備份失敗但主資料庫未變（此時 `copy` 資料夾已建，會先刪再印）。已執行：同上一列 | 318 |
| 11 | `STOP: the database copy could not be read. Do not change any setting or file yourself; tell the coordinator.` | 187～190／622 | P7。複本已做成，讀 `price_bars_cache` 時 `sqlite3.Error`。複本會在 874 行先刪再印。尚未：抓日曆、寫檔 | 319 |
| 12 | `STOP: the cache copy holds no TWII rows.` | 170／624 | P7。複本讀得出但沒有 `^TWII` 的列。複本先刪再印 | 320 |
| 13 | `STOP: a TWII row of the cache copy cannot be read.` | 171／629、633 | P7。某列日期不是純 `YYYY-MM-DD`。複本先刪再印 | 321 |
| 14 | `STOP: the database copy could not be deleted, so the check did not continue. Remove the whole work folder without opening it, do not send it to anyone, and tell the coordinator.` | 164～168／679（由 `delete_copy` 丟出，被 692、828、874 行呼叫） | 見 2.4。可能發生在 sweep（清前幾次殘留，**此時本次複本尚未做**）、874 行（本次複本刪不掉）、或收尾補印（966 行）。**這句出現時，磁碟上可能留有含持股與現金的資料庫複本**（草稿 332 的處理依據） | 322、332～336（第十二節）、174 |

補充三點：
1. 第 14 句在 874 行 `finally` 內丟出時，會**蓋掉**原本在飛的 `STOP`（例如第 11 句），所以畫面只剩第 14 句（Python `finally` 內再丟例外的行為；依原始碼推得，沒有執行驗證）。
2. 第 1～8 句（P3）之前不會建工作資料夾，也不會動複本；`cleanup` 在 `state.work is None` 時直接返回（825～826 行）。
3. 第 9～13 句在畫面印出時，本次複本已嘗試刪除（874 行 `finally` 在 `say` 之前）；刪不掉就會變成第 14 句，不會印出原句。

### 2.3 `ERROR:` 開頭的 2 句（不是方括號；`ERROR:` 與 R3-0 的 `[ERROR]` **不同**，不在 R3-0 清單裡，也不在 RC-342）

| # | 字面 | 定義／印出行 | 何時印、前面已執行／尚未執行 | 之後 | 草稿 |
|---|---|---|---|---|---|
| 15 | `ERROR: unexpected failure; no paste-back file was made. Tell the coordinator.` | 定義 194；`say(UNEXPECTED)` 在 952 行（`except BaseException`，結束碼 1）；同一字面另由全域 hook 在 41～42 行直接 `sys.stdout.write`（hook 掛在 sys.excepthook、threading.excepthook、sys.unraisablehook，46～48 行） | **任何階段都可能**：`flow()` 裡任何非 `RunStop`、非 `KeyboardInterrupt` 的例外，包含 `input()` 讀不到（提示語之後立刻發生，P2）、建資料夾失敗（869 行）、抓日曆出現非預期例外、`say()` 擋下不合白名單的行（268 行）、寫 `paste-back.txt` 失敗（882 行）等。印之前 `finally`／`cleanup` 已跑：本次複本已嘗試刪、未完成的 `paste-back.txt` 已刪、空的工作資料夾已刪（822～839 行）。**但可能已印出部分結果行**（若例外發生在 884～885 行的迴圈中，實務上不太可能，只是原始碼上不排除），所以草稿才有「ERROR 與 `result=` 同時出現」的段落 | 回傳 1 → `.bat` 印 `[NOTE] ... code 1.`、`pause`。之後可能再補印第 14 句（2.4）。不繼續 | 323、327（表後「畫面上同時有 ERROR 句與 result= 時」段落，草稿約 326 行附近）、167、273 |
| 16 | `ERROR: interrupted; no paste-back file was made.` | 定義 195；印出 949 行（`except KeyboardInterrupt`，結束碼 2） | CEO 按 Ctrl+C（或等同中斷）。**任何階段**，包含提示語等待中。清理同上一列 | 回傳 2 → `[NOTE] ... code 2.`、`pause`。注意：Ctrl+C 時 `cmd` 自己可能先問「Terminate batch job (Y/N)?」（Windows 系統文字，不是這個檔案印的，沒有實機驗證），見草稿 181 | 324、181、50 |

### 2.4 兩行連續出現的情形（草稿 301 所說「有時會連續出現兩行」）

`main()` 960～967 行：`cleanup` 之後再檢查工作根目錄 `stock-desk-gap-check` 底下是否仍有任何一個 `<時間戳>\copy`（695～704 行，**包含前幾次留下的**）。有就補印第 14 句並把結束碼改成 `3`；若最後一句已經是第 14 句就不重複。因此：

| 第一行 | 第二行 | 什麼時候會這樣 |
|---|---|---|
| 第 1～8 句（P3 的 `STOP:`）、第 15 句、第 16 句 | 第 14 句 | 本次還沒走到 sweep（P3 就停了）或中途被中斷／出錯，而**前一次**留下的複本仍在。sweep 在 867 行，晚於 preflight，所以 P3 停下時前次殘留**沒有**被清 |
| 第 9～13 句 | 第 14 句 | 874 行 `finally` 已蓋成第 14 句時只剩一行；若是其他路徑留下別次複本，也會補印 |
| （結果 17 行，之後） | 第 14 句 | 原始碼上可能（例如 `copy_left_behind` 因 `OSError` 失敗，963 行「fail closed」視為仍有複本）；此時記事本可能已經打開。草稿 174、322 已寫這種情形 |

### 2.5 結果行（17 行，不是 `STOP:`／`ERROR:`／方括號）

`gap_check version=1`、`git_head=<40 位 hex>`、`script_sha256_lf=<64 位 hex>`、`calendar_source=twse_mi_5mins_hist`、`period_start=<日期>`、`period_end=<日期>`、`months_checked=<清單或 none>`、`months_unchecked=<清單或 none>`、`cache_range_start=`、`cache_range_end=`、`cache_not_covered_count=<數字>`、`cache_not_covered_dates=`、`official_not_in_cache_count=`、`official_not_in_cache_dates=`、`cache_not_in_official_count=`、`cache_not_in_official_dates=`、`result=<四個代號之一>`（`<...>` 為變數位置）。

- 印在 `.py` 884～885 行；此時已執行：複本已刪（874 行）、日曆已抓完、`paste-back.txt` 已寫入（882～883 行）。尚未：開記事本（887～893 行，在印完之後）。
- 之後：回傳 0，`.bat` 不印 `[NOTE]`，直接 `pause`，結束碼 0。
- 抓日曆失敗**不會**變成 `STOP:`：整月或全部失敗只會讓 `months_unchecked` 有值、`result=calendar_unavailable`（337～384 行）。
- 不屬於任何 R 系列觸發字樣。草稿：第六節（221 行起）、167、174。

## 3. 對照 R 系列觸發字樣的總結

| 觸發清單 | gap-check 對應的行 | 備註 |
|---|---|---|
| R3-0：`[ERROR]` | `.bat` 25 行 `[ERROR] Cannot find the backend folder next to this file.` | 同時屬 RC-342 |
| R3-0：`[TIMEOUT]`、`[FAILED]`、`[STOP]`、`[FAIL]` | **無**。`gap-check.bat` 與 `gap_check.py` 都不會印出這四種字頭 | `STOP:` 不是 `[STOP]` |
| R3-0：要求重新開機的英文句子 | **無**。第 4 句（port 8000）與第 9 句寫的是「關視窗再執行」，不是重新開機 | 若 CEO 轉述時改寫，仍以字面為準 |
| R3-0C：`Cancelled.` 開頭 | **無**。沒有任何 `Cancelled.` | |
| RC-342：`[MISSING]` | `.bat` 18 行 | 不屬 R3-0 |
| RC-342：`[ERROR]` | `.bat` 25 行 | 同時屬 R3-0 |
| 不屬任何觸發清單，但畫面上會出現 | `[NOTE] The tool ended with code N`（33 行）、`STOP:` 14 句、`ERROR:` 2 句、提示語、結果行、`pause` 提示 | `STOP:`／`ERROR:` 都不是方括號字頭；`[NOTE]` 是方括號但不在清單 |

**一個需要風控注意的對照**：R3-0 與 dev-up 一樣用 `[ERROR]` 作觸發字頭，但 25 行這一種發生時，`gap-check.bat` 尚未動任何東西，且尚未請 CEO 關視窗；R3-0 內文若含「stock-desk 可能沒有開著」之類針對 `dev-up.bat` 的敘述，用在這一行是否合適，由風控判斷（我沒有改字，也沒有替它歸類）。又，`STOP:` 第 4 句（port 8000 還在聽）發生時 stock-desk 很可能仍開著，其餘 `STOP:`／`ERROR:` 發生在 CEO 按過 Enter（也就是依提示關過三個視窗）之後，這點與 RC-477 第 2 點的「關掉三個視窗之後的重開」直接相關。

## 4. 單列：CEO 要按的鍵、結束字樣、結尾

| 問題 | 答案（讀原始碼） |
|---|---|
| `gap-check.bat` 有沒有要 CEO 按 `Y`／`N` 的提示 | **沒有**。檔案裡沒有 `set /p`、`choice`，也沒有 `Y/N`、`Stop the old ...` 之類字樣。`.py` 唯一的輸入是 864 行的 `input()`（**只按 Enter**）。唯一可能出現的 Y／N 是 CEO 按 Ctrl+C 時 `cmd` 自己問的「Terminate batch job (Y/N)?」，不是這個檔案印的，Windows 實機未驗證（草稿 181 已提及） |
| 有沒有 `Done.` 或類似結束字樣 | **沒有**。`.bat` 不印 `Done.`；`.py` 結束只印 `result=` 那一行（成功）或 `STOP:`／`ERROR:`（失敗）。正常完成時畫面上沒有任何「完成」字樣，草稿 174 已寫「工具不會另外顯示『已刪除』的訊息」 |
| 結尾是否 `pause` | **是，所有出口都 `pause`**：正常與非 0 結束都在 34 行；`:fail`（`[MISSING]`、`[ERROR]`）在 39 行。沒有任何一條路徑不 `pause` |
| 結束碼 | `0` 完成；`1`／`2`／`3` 見第 1 節；`:fail` 一律 `exit /b 1` |

## 5. 草稿與這張表對不上、或與 RC-477 有關的地方（只列事實，不改檔）

1. 草稿 303：「**停下來之後，可以照平常雙擊 `dev-up.bat` 啟動 stock-desk；要再執行時，先把三個視窗關掉。**」是 RC-477 第 3 點要改的那一行。此外有**其他行也允許 CEO 自己再執行**：312（`STOP:` port 8000 列：「關掉三個 stock-desk 視窗後，重新雙擊 `gap-check.bat`」）、313（第 9 句列：「再重新雙擊 `gap-check.bat` 執行一次」）、273（重跑規則第 5 點：「排除原因後可以再執行」）、256 的後半句（「停在 `STOP:` 開頭的一行時，依第十一節那一句的『您要做的事』處理」，間接指向 312、313）。RC-477 第 3 點只點名 303，這幾處是否一併改，請風控判斷。
2. 第 9 句與第 4 句的**英文固定句本身**就寫了「run this again」「run again」（173～179、157～159 行）。草稿若要拿掉自行再執行的許可，只改中文欄不夠，英文原句畫面上仍會顯示；固定句是風控核可字面（草稿 20～21），改動需風控決定。
3. 草稿 299 說 `[MISSING]`／`[ERROR]`「表示工具還沒開始執行，沒有讀取您的資料庫」，與原始碼相符（`.bat` 18、25 行都在 `uv run` 之前）；但草稿沒有提到緊接的第二行 `Tell the coordinator.`／`Do not move or change any file or folder yourself; tell the coordinator.`。
4. 草稿 301：「有時會連續出現兩行」與 2.4 相符；但 2.4 表第一列顯示：P3 的 `STOP:` 加第 14 句的情形，是因為前一次殘留的複本在本次 sweep 之前沒被清，草稿 328 只說「下一次執行時，工具會嘗試清掉前一次殘留的複本」，沒說「preflight 停下時不會清」。
5. 草稿 167／273 以 `STOP:`／`ERROR:` 字頭認列結束，不會漏掉任何一種 `.py` 固定句；但 **`uv` 自己的錯誤文字**（例如找不到 `.venv`、`uv run --no-sync` 失敗時印的行）不在 `gap_check.py` 白名單內，字面與大小寫由 `uv` 決定，草稿與這張表都沒有涵蓋，結束碼也由 `uv` 決定（`[NOTE]` 會印出該碼）。這一類**我沒有查證**。

## 6. 沒有查證的事

- 所有 `.bat` 與 `.py` 都**沒有執行**；Windows 實機（cmd 的 `pause` 字面與語系、`Terminate batch job (Y/N)?`、`startfile` 開記事本、檔案鎖定、防毒對刪除複本的影響）一律未驗證。
- Python `finally` 內再丟例外會蓋掉原例外、`input()` 的 EOF 行為、`sqlite3` 備份行為、`shutil.rmtree` 在 Windows 的表現：依語言規則與原始碼推得，沒有實跑。
- `uv run --no-sync` 失敗時的畫面字面與結束碼：未知。
- 草稿行號依目前 `work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md` 檔案；其中 `.bat` 以外的 R 系列字面以兩份風控判定檔文末定稿為準（我只核對觸發字頭，沒有逐字比對 R3-0、R3-0C 內文）。
- 沒有讀 `.env*`、沒有碰 `apps/stock-desk/backend/data/`，也沒有核對兩支 `.bat` 對主 DB 是否「只讀不寫」的**事實前置**（RC-477 第 9 點屬 tech-architect）；以上「只讀」只是原始碼註解與呼叫方式所述。
- 沒有看 `r2-probe.bat`（RC-477 第 5 點同時點名，但本次任務只要求 `gap-check.bat`）。
- 沒有 checkout、commit、push。

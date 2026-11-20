# 補充十一：風控替換確認、verify 併入、讀寫鎖裁示

- 審查者：tech-architect
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **A1～A9：全部接受。** 風控推翻「不是 CG-4 阻擋項」的定位有道理：`dev-up.bat` 啟動時就會 `git pull`，靠「CEO 不更新」擋不住。
- **只有 A2 要再收緊一處**：把「之前或同時」改為「之前」。
  - 原因：接線前置清單裡「CEO 本機執行 `verify --all`」那一次，我裁示由這支一鍵檔執行（見第 2 題），所以它必須先於接線 PR 合併。
  - 因此一鍵檔**開在產品線上、先於接線合併**，不採「同一次 push」的做法。需要接線版 `report` 的測試，隨接線 PR 加入。
- **RC-292**：`verify --all` 併入同一支一鍵檔，固定排在 `status` 之後執行，取代補充十一原本的第 4 點。
- **RC-294**：讀程式的結論是主 DB 為 WAL 模式，讀 `status` 不會讓 `forecast_record` 寫入失敗。但 22:10、23:10 執行期間去讀，「最近一次執行」那一行可能顯示「沒有 end 列」，說明文件要請 CEO 避開這兩段時間。

以下「原 → 新」的原句，在組版檔「## 正文」或檔頭行中都只出現一次（我以讀檔核對，請再以腳本確認）。整份補充十一連同這些改動送風控。

## 1. A1～A9 與連帶的字面

- A1、A3～A9：逐字接受。
- **A2 再收緊**（第 28 行）：
  - 原片段：`所以第 2 點的一鍵檔必須在接線 PR 合併之前或同時合併，`
  - 新片段：`所以第 2 點的一鍵檔必須在接線 PR 合併之前合併（接線前的 `verify --all` 也由它執行，見第 4 點），`
- **檔頭行**：
  - 原：`補充十一（CEO 讀取執行狀態的途徑；`
  - 新：`補充十一（CEO 讀取執行狀態與重算核對的途徑；`
  - 原：`收緊：補上 F-2、行動句、最近一次執行與缺日加註的實際讀取途徑；`
  - 新：`收緊：補上 F-2、行動句、最近一次執行與缺日加註的實際讀取途徑，以及 F-3 的發現途徑，並新增接線 PR 合併（CG-4）的前置條件；`
- **標題**：
  - 原：`## 補充十一：CEO 讀取執行狀態的途徑（2026-11-20）`
  - 新：`## 補充十一：CEO 讀取執行狀態與重算核對的途徑（2026-11-20）`
- **性質**：
  - 原：`- 性質：收緊。`
  - 新：`- 性質：收緊。第 1 點新增接線 PR 合併（CG-4）的前置條件；第 4 點把 `report verify --all` 納入同一支一鍵檔。`
- **分支**：一鍵檔開在產品線上，先於接線 PR 合併。
  - 一鍵檔 PR 只放通用測試：兩段輸出與 CLI 逐字相同、各結束碼的處理、各固定句、e2e。這些在舊版 `report` 上也能跑。
  - 需要接線版輸出的那一項（S-21a 第四項：最近一次執行、F-2 兩句、兩行缺日加註），隨接線 PR 加入。

## 2. RC-292：`report verify --all`

**讀程式的結論**（`report.py` 第 20～30、413～469、653～677 行）：
- 它做的是 D-5 第 3 點的重算：用快照、登記表中的規則位元組與定義，重算每一筆紀錄，逐位元比對。
- 每筆紀錄只輸出一行：`claim_id`、T、一致或不一致（不一致時附固定問題代碼，或例外類別名稱）、程式與執行環境是否與寫入時相同。最後一行是結語：「沒有紀錄」「全部一致」或「有不一致（F-3：停止記錄並查明）」。
- **不輸出標籤、基準預測、暫定對照或紀錄的其他欄位。**
- 讀取經 `_read`（`query_only`）。結束碼：0 一致，1 有不一致，3、4 讀取失敗。
- 執行時間會隨紀錄筆數線性增加，實際多長沒有量測過。

**裁示**：併入同一支一鍵檔，在 `status` 之後固定接著跑。
- 不另做一支：CEO 只需要記一個操作，每週的貼回也一定兩段都有。
- 也不開放參數，一鍵檔一次就兩段都跑。

**替換第 4 點**（第 65 行整行）：
- 原：`4. **不在本補充內**：`report verify` 的定期執行（F-3 的發現途徑）另行裁示。該裁示須在接線 PR 合併之前作成；落地不得晚於第一筆 `forecast_run` 之後的第 20 個平日。落地之前，任何 CEO 文件都不得寫成本一鍵檔涵蓋所有失效條件。`
- 新（一行標題加七款）：
```
4. **重算核對（`report verify --all`，F-3 的發現途徑）**
   - 同一支一鍵檔在 `status` 之後，固定接著執行 `report verify --all`（同一個 `--db`）。兩段依序輸出，中間以一行固定分隔句分開，存在同一個 `status.txt`。不接受參數的規定照舊，也不提供只跑其中一段的方式。
   - `verify --all` 是 D-5 第 3 點的重算：每筆紀錄只輸出 `claim_id`、T、一致與否（不一致時附問題代碼）、程式與執行環境是否與寫入時相同，以及一行結語。不輸出標籤、基準預測、暫定對照或紀錄的其他內容。讀取方式與 `status` 相同。
   - 結束碼：`verify` 的 1（有不一致）屬正常完成，照常顯示並存檔；3、4 與其他結束碼依第 2 點改印固定句。
   - 頻率與紀錄同第 3 點，每次執行都含這一段。
   - 接線 PR 合併前置清單中「CEO 本機執行 `report verify --all`」那一次，以本一鍵檔執行（帳內沒有紀錄，預期結語為「verify：沒有紀錄」），貼回依第 3 點保存。本一鍵檔必須在那一次執行之前合併。
   - 看到「不一致」或結語「verify：有不一致（F-3：停止記錄並查明）」時，CEO 只告訴 coordinator，不自己停止程式、刪改資料或設定；停止記錄與查明，由 coordinator 升級 tech-architect 與 devops-sre 處理。這句與分隔句的字面，由 creative-lead 起草，送風控。
   - 執行時間：devops-sre 以合成 ledger 量測紀錄 0、250、500 筆（兩個 claim 合計）時 `verify --all` 的執行時間，寫進交件，供說明文件引用。500 筆時超過 10 分鐘，退回 tech-architect 重議頻率或拆分。
```
- 落地時點因此早於 RC-292 的期限（第一筆 `forecast_run` 之後第 20 個平日）。

**第 2 點「範圍」連動**：
- 原：`     - 只執行 `app.forecast.report` 的 `status`。`--db` 固定為 `<backend>/data/stock-desk.db`，`<backend>` 由腳本位置導出。`
- 新：`     - 只執行 `app.forecast.report` 的 `status`，以及第 4 點的 `verify --all`。`--db` 固定為 `<backend>/data/stock-desk.db`，`<backend>` 由腳本位置導出。`
- 原：`     - 不接受任何參數；不得執行 `records`、`compare`、`verify`。`
- 新：`     - 不接受任何參數；不得執行 `records`、`compare`，也不得以 `--claim-id` 執行 `verify`。`

**S-21a 連動**：
- 原：`  - AST：腳本中唯一的子命令字面是 `status`，不讀 `sys.argv`，不 import harness，不 import `app.forecast.report` 以外的 `app.forecast` 模組。`
- 新：`  - AST：腳本中的子命令字面只有 `status` 與 `verify`，`verify` 只帶 `--all`；不讀 `sys.argv`，不 import harness，不 import `app.forecast.report` 以外的 `app.forecast` 模組。`
- 原：`  - 合成 ledger 上，輸出與 `python -m app.forecast.report status --db` 逐字相同（測試）。`
- 新：`  - 合成 ledger 上，第一段輸出與 `python -m app.forecast.report status --db` 逐字相同，第二段與 `verify --all --db` 逐字相同，兩段之間只有固定分隔句；`verify` 結束碼 1 時照常顯示並存檔，3、4 時只印固定句（測試）。`
- 插在 `  - `app/` 零差異。` 之後的新行：`  - 本一鍵檔 PR 開在產品線上，先於接線 PR 合併；上面第四項中需要接線版 `report` 的測試（最近一次執行、F-2 兩句、兩行缺日加註），隨接線 PR 加入。qa 核對一鍵檔 PR 的合併 commit，早於接線前那一次 `verify --all` 貼回的 commit。`

## 3. RC-294：scheduler 寫入當下有人讀 `status`

**讀程式的結論**：
- **主 DB 是 WAL 模式。**
  - 設定者：`app/data/cache.py` 的 `_init_schema` 呼叫 `sqlite_util.enable_wal`；其他主 DB store 也各自呼叫。WAL 是持久寫在檔案上的屬性。
  - 帳本 store 的 `_open_connection` 不設 journal 模式，沿用檔案本身的 WAL。
  - `busy_timeout` 為 5000 ms。寫入用 `BEGIN IMMEDIATE`（`store._write`）。讀取每次查詢各開一個短連線，設 `query_only`。
- **WAL 下，讀不會讓寫失敗。**
  - 讀者不持有寫鎖。`BEGIN IMMEDIATE` 只和其他寫者互斥。
  - 自動 checkpoint 是 PASSIVE：讀者占著舊快照時，checkpoint 只會做不完，不會讓 commit 失敗。
  - 唯一的副作用是 `-wal` 可能暫時變大。
- **WAL 下，讀者不會讀到半個交易。** 每次查詢看到的都是某一個已 commit 的快照。
  - 但 `status` 由多次查詢組成，跨查詢之間可能落在 recorder 的兩次 commit 之間：`begin_run` 與快照加紀錄、`end_run` 是三個交易。
  - 實際的後果是：執行進行中去讀，「最近一次執行」會顯示「結果 沒有 end 列」，各行之間的計數也可能相差一次執行。
  - 這不是錯誤，不會落到任何固定 STOP 句，但 CEO 可能誤讀成程式中斷。
- **讀者報錯的情形**：WAL 下只有極少數情形會拿到 busy（例如 `-shm` 初始化或復原），而 busy handler 會等 5 秒。超過 5 秒拋出 `sqlite3.Error`，`report` 把它歸為結束碼 3，一鍵檔改印 RC-291「結束碼 3」那一句。
- **非 WAL（rollback journal）時，才會有寫入失敗的可能**：讀者持有 SHARED 鎖時，寫者 commit 要等。單次查詢只要幾毫秒到不到一秒，遠低於 5 秒，所以寫入失敗只是理論上的可能。
  - 萬一真的發生：快照加紀錄那個交易整筆回滾，outcome 記為 `error`。若 `end_run` 也失敗，就沒有 end 列。
  - 那一個 session 會進 F-2 第一句的分子，除非 23:10 那次重試補上。
  - 主 DB 正常情況下不會是非 WAL，因為 app 啟動時就會設定。

**對 CEO 說明的裁示**：需要提醒避開時段，原因是避免誤讀，不是寫入安全。

**第 2 點「讀取方式」末款替換**：
- 原：`     - scheduler 執行中也可以讀。`
- 新：`     - scheduler 執行中也可以讀；主 DB 為 WAL 模式，讀取不會使 `forecast_record` 的寫入失敗。在台北時間 22:00～22:30、23:00～23:30 執行時，最近一次執行可能顯示「沒有 end 列」（執行仍在進行），說明文件須請 CEO 避開這兩段時間；看到這種情形時，30 分鐘後再執行一次，仍是如此就告訴 coordinator。`

**需要 devops-sre 以測試實證的項目**：
- (i) 合成 WAL DB 上，另一個行程以 `query_only` 連續讀取時，`write_run_records` 與 `end_run` 照常 commit，不拋 busy；
- (ii) 讀取發生在 `begin_run` 與 `end_run` 之間時，`status` 顯示「沒有 end 列」，不報錯；
- (iii) rollback journal 模式下的對照：讀者持有鎖期間，寫者的等待時間；
- (iv) CEO 主 DB 的 journal 模式：agent 不得讀，以 `cache._init_schema` 的程式行為推定，不另外查證；
- (v) 一次正常的 `forecast_record` 從開始到 end 列的耗時，用來確認「30 分鐘」這個值夠用。

## 驗證

- 讀了組版檔全文、風控報告的摘要與條件總表（grep）、`report.py` 第 1～75、380～479、632～701 行，以及 `store.py` 的 `_open_connection`、`_write`、`_read`。
- grep 了 `app/` 內的 `journal_mode`、`busy_timeout`、`BEGIN IMMEDIATE`，並讀了 `cache.py` 第 150～174 行。
- 沒有讀 `sqlite_util.enable_wal` 的本體、`recorder.reproduces`（我依 `report.py` 的 AST 聲明推定它不寫入）、`dev-up.bat`、`approved_copy`。
- 執行時間與 rollback 模式下的行為都屬推論，交給 devops-sre 實證。
- 唯讀：沒有改任何檔，沒有讀 `.env`，也沒有碰任何 `.db`。

## 下一步

- **coordinator**：套用上述替換後重組版，整份補充十一送風控。
  - 重點：A2 改為「之前」、新的第 4 點、RC-294 那一款，以及兩句新的 CEO 面字句（分隔句、不一致時的行動句）。
  - 接線 PR 合併的前置清單改為「一鍵檔先合併，然後以它執行接線前的 `verify --all`」。
- **devops-sre**：一鍵檔開在產品線上，依新的第 2、4 點與 S-21a 建置。完成 RC-294 的實證 (i)～(iii)、(v)，以及 `verify` 的時間量測，寫進交件。
- **dev-lead**：在接線 PR 加入 S-21a 第四項中需要接線版 `report` 的那項測試。
- **creative-lead**：說明文件加入避開時段、分隔句、不一致時的行動句，以及 `verify` 的執行時間。

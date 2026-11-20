# CEO 讀取執行狀態的途徑裁示、補充十一、退役 PR 讀法

- 審查者：tech-architect
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **題一**：CEO 目前確實沒有任何途徑看到 `report status`，需要一支只跑 `status` 的一鍵檔。
  - 這件事**不擋接線 PR 合併（CG-4）**。
  - 但它是 RC-246 通知的前置條件：一鍵檔合併、說明文件經風控核可之前，不得送出那份通知，CEO 也不得更新到含接線的程式。那份通知已併入 RC-264、RC-265～RC-267。
  - 我另立**補充十一**來規定這件事。**補充十定稿不改**，照組版檔原樣寫入即可。補充十一整份要送風控。
- **題二**：你的讀法我確認。補充九、補充十都不必增加文字，由退役 PR 的說明記載即可。另外有兩處要注意，見下方。

## 各題裁示

### 題一

**1. 定位**

- 現況：
  - F-2、行動句（RC-250）、「最近一次執行」（RC-259）、兩行缺日加註，都只出現在 `report status`。
  - 心跳是 devops-sre 的職責（ADR 第 275 行：讀 `forecast_run_end`），只負責偵測停機（補充五第 1 點 (h)），不判定 F-2。
  - `app/ops_alert` 暫不使用。
  - 所以現在沒有人看 `report status` 的話，F-2 成立**不會被任何人發現**，而 F-2 規定要「升級 CEO 與 devops-sre」。
- 不列為 CG-4 阻擋項的理由：
  - 「曾否成立」每次都由帳內資料重算，晚看不會遺失。
  - 記錄本身不受影響。
- 但 RC-246 與 RC-264 的通知會叫 CEO 去看一行他看不到的字，所以這支一鍵檔必須在那份通知之前就位。

**2. 一鍵檔：要做，內容見補充十一。要點如下：**

- **範圍：只開放 `status`。**
  - 不開放 `records`、`compare`、`verify`：`records`、`compare` 會顯示標籤或暫定對照，牽涉 #149、#150 與 R-8。
  - `verify` 是 F-3 的發現途徑，另行裁示。
- **讀取方式**：
  - 經 `report.main` 走 `store._read`，直接讀主 DB 本體，連線設 `query_only`，不取複本。
  - WAL 模式下，SQLite 照常建立或更新 `-wal`、`-shm`，這和 backend、scheduler 平時的連線完全相同。
  - 這是 ADR D-1 指定的操作者讀取路徑，所以不適用補充八第 5 點 (c)。那一條管的是帳外工具：要複製含持股與現金的 DB，而且 agent 不得碰主 DB。
  - scheduler 執行中也可以讀，等鎖由 `busy_timeout` 處理。
  - `report.main` 會先確認主 DB 檔案存在，所以不會新建 DB。
- **前置檢查只有一項**：環境變數中有 `STOCK_DESK_DB_PATH` 就 STOP。不做 port 與 git 檢查，因為只是唯讀顯示。
- **輸出：不另設白名單。**
  - 每一行已經受 D-4 與 `d4_violations` 約束。腳本只對每一行再跑一次 `d4_violations` 當作絆線。
  - 比照 RC-158a、RC-162 的做法，畫面不出現 traceback、路徑或例外文字。
- **頻率**：
  - coordinator 每週一次（建議週一）請 CEO 執行並貼回，另外在任何異常通知之後也請一次。
  - CEO 也可以隨時自己執行。
  - 貼回由 coordinator 逐字 commit。
- **讀者**：行動句的第一讀者是 CEO，第二讀者是 coordinator，由 coordinator 負責升級。

**3. 替代做法**（例如只由 coordinator 口頭請 CEO 跑指令）：不採用。CEO 不寫程式，打錯子命令就可能看到 `records` 或 `compare`。

### 題二：退役 PR 的讀法確認，附兩點

- **我確認的讀法**：
  - 「只有刪除」的意思是：那 9 個檔只刪不改；`app/` 與 `tests/test_cg2_registration_values.py` 零差異。
  - 新增一支守門測試，以及清除純粹指向已刪檔的引用，屬於必要的附帶差異。
  - 清除引用時，盡量只刪行。不得不改寫句子的地方，在 PR 說明逐項列出。
- **注意一：守門測試的檔名例外。** 守門測試本身一定含有那四個檔名，所以 S-19a 那條 grep 要把守門測試排除在外。這是讀法，不必增加文字。
- **注意二：有兩個測試名稱不算引用。** 我用 grep 在接線 worktree 查到 `tests/test_dirdef_v1_0_fields.py:94` 與 `tests/test_outlook_rule_files.py:193` 的測試名稱是 `test_cg2_registers_*`。
  - 這只是子字串碰巧相符，不是對退役檔的引用，**不得改名**。
  - grep 要用能區分的樣式，例如 `cg2_register\.py|cg2_register_|cg2-register|cg2-preflight|verify_cg2_instruction`。
  - 退役分支上的實際狀況，由 dev-lead 確認。

## 補充十一（可逐字寫入；整份送風控）

**檔頭補充紀錄行**（加在補充十那一行之後）：

- 補充紀錄：2026-11-20 append 補充十一（CEO 讀取執行狀態的途徑；tech-architect 裁示；收緊：補上 F-2、行動句、最近一次執行與缺日加註的實際讀取途徑；不改本文、補充八至補充十的字面、`app/`、事先宣告 v0.32、規則檔、定義物件與已登記雜湊；新增 CEO 看得到的固定句與說明文件，送風控；CEO 可推翻；來源 〔本次裁示轉存檔〕、〔風控判定報告〕）

**正文**：

## 補充十一：CEO 讀取執行狀態的途徑（2026-11-20）

- 決策者：tech-architect。
- 來源：〔本次裁示轉存檔〕、〔風控判定報告〕。另讀 `feat/nm5-wiring` 的 `app/forecast/report.py`（`_parser`、`run_command`、`main`）、`app/forecast/store.py`（`_open_connection`、`_read`）。
- 性質：收緊。
  - 不改本文、補充八至補充十的字面、`app/`、事先宣告 v0.32、規則檔、定義物件與已登記雜湊。
  - 新增的固定句與 CEO 說明文件送風控。CEO 可推翻。

1. **現況與定位**
   - F-2（兩句）、行動句、最近一次執行、兩行缺日加註，都只出現在 `report status`。
   - devops-sre 的心跳只負責停機偵測（補充五第 1 點 (h)），不判定 F-2；`app/ops_alert` 暫不使用。
   - 沒有人執行 `report status` 時，F-2 成立不會被發現。
   - 本點不是 CG-4 的阻擋項：「曾否成立」每次都由帳內資料重算，晚看不會遺失；記錄本身不受影響。
   - 本點是 RC-246 通知（含併入的 RC-264、RC-265～RC-267）的前置條件。第 2 點的一鍵檔合併、第 3 點的說明文件經風控核可之前，不得送出該通知，CEO 也不得更新到含接線的程式。
2. **狀態報告一鍵檔**
   - 檔案：
     - `apps/stock-desk/forecast-status.bat` 與 `apps/stock-desk/backend/scripts/forecast_status.py`，放在 `app/` 以外。
     - `.bat` 比照既有的一鍵檔：先清除 `UV_ENV_FILE`，再以 `uv run --no-sync python -I -X utf8` 執行。
   - 範圍：
     - 只執行 `app.forecast.report` 的 `status`。`--db` 固定為 `<backend>/data/stock-desk.db`，`<backend>` 由腳本位置導出。
     - 不接受任何參數；不得執行 `records`、`compare`、`verify`。
     - 要開放其他子命令，須修訂本補充並送風控。
   - 讀取方式：
     - 經 `report.main` 與 `ForecastStore._read`（`query_only`）讀主 DB 本體，不取複本。
     - WAL 模式下，SQLite 會照常建立或更新 `-wal`、`-shm`，與 backend、scheduler 平時的連線相同。
     - 這是 D-1 指定的操作者讀取路徑，不適用補充八第 5 點 (c)。
     - scheduler 執行中也可以讀。
   - 前置檢查：
     - 程序環境變數中有 `STOCK_DESK_DB_PATH`（含空字串）時 STOP，不開任何連線。
     - 不讀 `.env`，不做 port 與 git 檢查。
     - 主 DB 不存在或 schema 不完整時，沿用 `report` 既有的拒絕句。
   - 輸出：
     - 不另設白名單。每一行再套一次既有的 `d4_violations`；任一行不為空，就整批不印，只印固定 ERROR 句。
     - 比照 RC-158a、RC-162：攔截 `BaseException`，更換 `sys.excepthook`、`threading.excepthook`、`sys.unraisablehook`，關閉警告。畫面不出現 traceback、路徑或例外文字。
     - 同一份內容另存為 `~/stock-desk-status/<時間>/status.txt`（`utf-8-sig`），以記事本開啟，不覆蓋舊檔。
     - 新增的 STOP、ERROR 與提示語，字面送風控定稿。
   - 不得：在 `apps/stock-desk/` 內寫入任何檔案；import harness；建立排程。
3. **讀者、頻率與紀錄**
   - 讀者：行動句（RC-250）與最近一次執行（RC-259、RC-264 (a)）的第一讀者是 CEO，coordinator 是第二讀者。
   - 頻率：
     - coordinator 每週一次請 CEO 執行並貼回，任何異常通知之後也請一次。
     - CEO 也可以隨時自行執行。
   - 紀錄：
     - 貼回全文由 coordinator 逐字 commit 到 `work/`。
     - 不得與 `report records`、`report compare` 或帳外缺日比對的輸出，放在同一次貼回或同一個檔案（RC-223）。
     - F-2 任一行成立，或「曾否成立」為是時，coordinator 依補充九第 5 點升級，並記錄第一次看到的日期。
   - CEO 說明文件與通知，至少寫明以下各點；字面由 creative-lead 起草，送風控：
     - 這是執行狀態，不是績效，也不代表規則好壞；
     - 看到行動句，或最近一次執行停在較早的時間，就告訴 coordinator；不要自己重抓資料、修改快取或設定；
     - 只執行這支一鍵檔，不要自己輸入 `report` 的其他指令。
4. **不在本補充內**：`report verify` 的定期執行（F-3 的發現途徑）另行裁示。

- **S-21a（逐條可檢查）**
  - AST：腳本中唯一的子命令字面是 `status`，不讀 `sys.argv`，不 import harness，不 import `app.forecast.report` 以外的 `app.forecast` 模組。
  - 設了 `STOCK_DESK_DB_PATH`（含空字串）時 STOP，不開任何連線（測試）。
  - 合成 ledger 上，輸出與 `python -m app.forecast.report status --db` 逐字相同（測試）。
  - 注入任一行 `d4_violations` 不為空時，整批不印，只印固定 ERROR 句（測試）。
  - e2e 擷取 stdout 與 stderr：例外、執行緒例外、警告、注入 `KeyboardInterrupt`，畫面都只有固定句（測試）。
  - `app/` 零差異。
  - qa 核對：RC-246 通知送出的 commit，晚於一鍵檔的合併 commit，也晚於說明文件的風控核可。

## 驗證

- 讀過：
  - `report.py` 第 632～701 行；
  - `store.py` 的 `_open_connection`、`_read`；
  - ADR-0030 中有關心跳、`ops_alert`、F-2 的段落（grep，第 275、328、558～560 行）；
  - 補充十組版檔第 9～12 與 176～244 行。
- 以 grep 查了接線 worktree 中引用退役檔名的檔案：`app/` 沒有命中；兩個 `test_cg2_registers_*` 屬於子字串誤中。
- 沒有讀到或屬推論的：
  - 心跳是否已經實作：`app/` 內找不到它讀 `forecast_run_end` 的程式，我推定尚未建置。
  - `d4_violations` 定義在哪個模組，沒有查證，由 dev-lead 引用既有函式。
  - 退役分支的實際內容沒有讀。
- 沒有改任何檔，沒有讀 `.env`，也沒有碰任何 `.db`。

## 下一步

- **coordinator**：
  - 補充十照組版檔原樣寫入，不必改。
  - 補充十一送風控，連同第 2 點的新固定句與第 3 點的說明文件要點；兩個佔位在送審後換成實際檔名。
  - RC-246 通知等到補充十一第 1 點的條件成立後才送出。
- **devops-sre**：依補充十一第 2 點與 S-21a 建置一鍵檔，固定句送風控。
- **creative-lead**：依第 3 點起草 CEO 說明文件與通知的增補內容。
- **dev-lead**：
  - 退役 PR 照你的讀法進行，在 PR 說明逐項列出非純刪除的差異。
  - S-19a 的 grep 排除守門測試，並使用能區分的樣式；`test_cg2_registers_*` 不改名。

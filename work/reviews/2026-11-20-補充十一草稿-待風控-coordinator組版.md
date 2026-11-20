# 補充十一草稿（待風控判定；coordinator 以腳本組版）

- 組版者：coordinator（腳本逐字替換，沒有手動改字）
- 日期：2026-11-20
- 底稿：`work/reviews/2026-11-20-CEO讀取執行狀態途徑裁示與補充十一-tech-architect.md`「## 補充十一」一節
- 套用：`work/reviews/2026-11-20-補充十一D4檢查位置裁示-tech-architect.md` 的兩組「原 → 新」替換
- 狀態：**尚未經風控判定，不得寫入 ADR。**〔本次裁示轉存檔〕〔風控判定報告〕兩個佔位待風控判定後換成實際檔名。

## 檔頭補充紀錄行

- 補充紀錄：2026-11-20 append 補充十一（CEO 讀取執行狀態的途徑；tech-architect 裁示；收緊：補上 F-2、行動句、最近一次執行與缺日加註的實際讀取途徑；不改本文、補充八至補充十的字面、`app/`、事先宣告 v0.32、規則檔、定義物件與已登記雜湊；新增 CEO 看得到的固定句與說明文件，送風控；CEO 可推翻；來源 〔本次裁示轉存檔〕、〔風控判定報告〕）

## 正文

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
   - 「曾否成立」每次都由帳內資料重算，晚看不會遺失；記錄本身不受影響。但 CEO 更新程式的時點無法另外控制，所以本點列為 CG-4（接線 PR 合併）的前置條件，見下一款。
   - 本點是 RC-246 通知（含併入的 RC-264、RC-265～RC-267）的前置條件。第 2 點的一鍵檔合併、第 3 點的說明文件經風控核可之前，不得送出該通知。CEO 平常以 `dev-up.bat` 啟動時就會更新程式，不能靠「CEO 不更新」來擋，所以第 2 點的一鍵檔必須在接線 PR 合併之前或同時合併，該通知與第 3 點的說明文件也必須在接線 PR 合併之前交給 CEO；三件未完成，接線 PR 不得合併。
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
     - 主 DB 不存在、schema 不完整或讀取失敗時，不顯示 `report` 的拒絕句：腳本攔下 `report` 寫到 stderr 的全部文字，依結束碼改印風控定稿的固定 STOP 句；`report` 的 stderr 內容不得出現在畫面或檔案中。
   - 輸出：
     - 不另設白名單，也不在執行期重做 D-4 檢查：輸出由 `report status` 原樣產生，D-4 合規由既有測試（`tests/test_forecast_report.py` 的 `d4_violations`）把關。腳本對 `report` 的輸出不增刪、不改寫任何一行，不 import `tests`，也不讀 `work/` 下的任何檔案。
     - 比照 RC-158a、RC-162：攔截 `BaseException`，更換 `sys.excepthook`、`threading.excepthook`、`sys.unraisablehook`，關閉警告與 logging。畫面不出現 traceback、路徑或例外文字。`status.txt` 只在取得完整輸出之後才寫入；失敗或中斷時不留下不完整的檔。
     - 同一份內容另存為 `~/stock-desk-status/<時間>/status.txt`（`utf-8-sig`），以記事本開啟，不覆蓋舊檔。該資料夾落在 git 工作樹內時 STOP，不寫檔。
     - 新增的 STOP、ERROR 與提示語，字面送風控定稿。
   - 不得：在 `apps/stock-desk/` 內寫入任何檔案；import harness；建立排程。
3. **讀者、頻率與紀錄**
   - 讀者：行動句（RC-250）與最近一次執行（RC-259、RC-264 (a)）的第一讀者是 CEO，coordinator 是第二讀者。
   - 頻率：
     - coordinator 每週一次請 CEO 執行並貼回，任何異常通知之後也請一次。
     - CEO 也可以隨時自行執行。
   - 紀錄：
     - 貼回全文由 coordinator 逐字 commit 到 `work/`。
     - 不得與 `report records`、`report compare` 或帳外缺日比對的輸出，放在同一次貼回或同一個檔案（RC-223）。每次貼回各存一個檔，不得刪減或只挑一份；未貼回的週次照實記錄為未貼回，不得以之後的輸出補填；commit 時附風控定稿的固定說明行（RC-289）。
     - F-2 任一行成立，或「曾否成立」為是時，coordinator 依補充九第 5 點升級，並記錄第一次看到的日期。
   - CEO 說明文件與通知，至少寫明以下各點；字面由 creative-lead 起草，送風控：
     - 這是執行狀態，不是績效，也不代表規則好壞；
     - 看到行動句，或最近一次執行停在較早的時間，就告訴 coordinator；不要自己重抓資料、修改快取或設定；
     - 只執行這支一鍵檔，不要自己輸入 `report` 的其他指令。
4. **不在本補充內**：`report verify` 的定期執行（F-3 的發現途徑）另行裁示。該裁示須在接線 PR 合併之前作成；落地不得晚於第一筆 `forecast_run` 之後的第 20 個平日。落地之前，任何 CEO 文件都不得寫成本一鍵檔涵蓋所有失效條件。

- **S-21a（逐條可檢查）**
  - AST：腳本中唯一的子命令字面是 `status`，不讀 `sys.argv`，不 import harness，不 import `app.forecast.report` 以外的 `app.forecast` 模組。
  - 設了 `STOCK_DESK_DB_PATH`（含空字串）時 STOP，不開任何連線（測試）。
  - 合成 ledger 上，輸出與 `python -m app.forecast.report status --db` 逐字相同（測試）。
  - AST 確認腳本不 import `tests`、不讀 `work/` 下的任何檔案；以含最近一次執行、F-2 兩句與兩行缺日加註的合成 ledger 執行腳本，輸出經 `tests/test_forecast_report.py` 的 `d4_violations` 檢查為空（測試）。該合成 ledger 另含已過 `valid_until_session_estimate`、帶標籤與基準預測的紀錄，並斷言輸出不含任何標籤值、基準預測值或 `content_hash`（測試）。
  - e2e 擷取 stdout 與 stderr：例外、執行緒例外、警告、注入 `KeyboardInterrupt`，畫面都只有固定句（測試）。
  - `app/` 零差異。
  - qa 核對：RC-246 通知送出的 commit，晚於一鍵檔的合併 commit，也晚於說明文件的風控核可，而且早於接線 PR 的合併 commit。

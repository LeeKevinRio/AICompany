# 補充十一定稿（待寫入 ADR-0030；coordinator 以腳本組版）

- 組版者：coordinator（腳本逐字替換，沒有手動改字）
- 日期：2026-11-20
- 底稿：`work/reviews/2026-11-20-CEO讀取執行狀態途徑裁示與補充十一-tech-architect.md`「## 補充十一」一節
- 套用：`work/reviews/2026-11-20-補充十一D4檢查位置裁示-tech-architect.md` 的兩組「原 → 新」替換
- 狀態：**定稿，待寫入 ADR。** 依風控 RC-284～RC-305 附條件核可（E1 經 RC-305 照原文通過；風控明示現行檔即為定稿）；tech-architect 的 E1～E3 增修已以腳本套用。檔名沿用「草稿」是為了不改動其他文件中的引用路徑。

## 檔頭補充紀錄行

- 補充紀錄：2026-11-20 append 補充十一（CEO 讀取執行狀態與重算核對的途徑；tech-architect 裁示；收緊：補上 F-2、行動句、最近一次執行與缺日加註的實際讀取途徑，以及 F-3 的發現途徑，並新增接線 PR 合併（CG-4）的前置條件，RC-246 通知的時點改為接線 PR 合併之前，取代補充九第 3 點末款；不改本文、補充八至補充十的字面、`app/`、事先宣告 v0.32、規則檔、定義物件與已登記雜湊；依風控 RC-284～RC-302 附條件核可，固定句字面依 RC-291、RC-298、RC-299 定稿，CEO 說明文件與 RC-246 通知另送風控；CEO 可推翻；來源 `work/reviews/2026-11-20-CEO讀取執行狀態途徑裁示與補充十一-tech-architect.md`、`work/reviews/2026-11-20-補充十一D4檢查位置裁示-tech-architect.md`、`work/reviews/2026-11-20-補充十一替換確認與verify及鎖裁示-tech-architect.md`、`work/reviews/2026-11-20-補充十一最後確認-tech-architect.md`、`work/reviews/2026-11-20-補充十一與退役通知判定RC284至RC297-風控.md`、`work/reviews/2026-11-20-補充十一增修確認與三句固定行RC298至RC302-風控.md`）

## 正文

## 補充十一：CEO 讀取執行狀態與重算核對的途徑（2026-11-20）

- 決策者：tech-architect。
- 來源：`work/reviews/2026-11-20-CEO讀取執行狀態途徑裁示與補充十一-tech-architect.md`、`work/reviews/2026-11-20-補充十一D4檢查位置裁示-tech-architect.md`、`work/reviews/2026-11-20-補充十一替換確認與verify及鎖裁示-tech-architect.md`、`work/reviews/2026-11-20-補充十一最後確認-tech-architect.md`、`work/reviews/2026-11-20-補充十一與退役通知判定RC284至RC297-風控.md`、`work/reviews/2026-11-20-補充十一增修確認與三句固定行RC298至RC302-風控.md`。另讀 `feat/nm5-wiring` 的 `app/forecast/report.py`（`_parser`、`run_command`、`main`、`render_verify`）、`app/forecast/store.py`（`_open_connection`、`_read`）。
- 性質：收緊。第 1 點新增接線 PR 合併（CG-4）的前置條件；第 4 點把 `report verify --all` 納入同一支一鍵檔。
  - 不改本文、補充八至補充十的字面、`app/`、事先宣告 v0.32、規則檔、定義物件與已登記雜湊。
  - 依風控 RC-284～RC-302 附條件核可；固定句字面依 RC-291、RC-298、RC-299 定稿。CEO 說明文件與 RC-246 通知的字面另送風控。CEO 可推翻。

1. **現況與定位**
   - F-2（兩句）、行動句、最近一次執行、兩行缺日加註，都只出現在 `report status`。
   - devops-sre 的心跳只負責停機偵測（補充五第 1 點 (h)），不判定 F-2；`app/ops_alert` 暫不使用。
   - 沒有人執行 `report status` 時，F-2 成立不會被發現。
   - 「曾否成立」每次都由帳內資料重算，晚看不會遺失；記錄本身不受影響。但 CEO 更新程式的時點無法另外控制，所以本點列為 CG-4（接線 PR 合併）的前置條件，見下一款。
   - 本點是 RC-246 通知（含併入的 RC-264、RC-265～RC-267）的前置條件。第 2 點的一鍵檔合併、第 3 點的說明文件經風控核可之前，不得送出該通知。CEO 平常以 `dev-up.bat` 啟動時就會更新程式，不能靠「CEO 不更新」來擋，所以第 2 點的一鍵檔必須在接線 PR 合併之前合併（接線前的 `verify --all` 也由它執行，見第 4 點），該通知與第 3 點的說明文件也必須在接線 PR 合併之前交給 CEO；三件未完成，接線 PR 不得合併。
   - 前款的通知時點（接線 PR 合併之前），取代補充九第 3 點末款與風控 RC-246、RC-264 原訂的「接線 PR 合併後、CEO 更新到含接線的程式之前」；依風控 RC-284 裁定，並經 RC-298～RC-302 那一輪確認收緊為「之前」（不含同時）。補充九的字面不改，時點以本款為準。
2. **狀態報告一鍵檔**
   - 檔案：
     - `apps/stock-desk/forecast-status.bat` 與 `apps/stock-desk/backend/scripts/forecast_status.py`，放在 `app/` 以外。
     - `.bat` 比照既有的一鍵檔：先清除 `UV_ENV_FILE`，再以 `uv run --no-sync python -I -X utf8` 執行。
   - 範圍：
     - 只執行 `app.forecast.report` 的 `status`，以及第 4 點的 `verify --all`。`--db` 固定為 `<backend>/data/stock-desk.db`，`<backend>` 由腳本位置導出。
     - 不接受任何參數；不得執行 `records`、`compare`，也不得以 `--claim-id` 執行 `verify`。
     - 要開放其他子命令，須修訂本補充並送風控。
   - 讀取方式：
     - 經 `report.main` 與 `ForecastStore._read`（`query_only`）讀主 DB 本體，不取複本。
     - WAL 模式下，SQLite 會照常建立或更新 `-wal`、`-shm`，與 backend、scheduler 平時的連線相同。本工具若是最後一個關閉的連線，SQLite 會把 `-wal` 的內容 checkpoint 進主 DB 本體並刪除 `-wal`、`-shm`，主 DB 檔的位元組與修改時間因此改變，邏輯內容不變；backend、scheduler 的連線最後關閉時也是如此。這裡的「唯讀」指不經 SQL 寫入任何內容，不指主 DB 檔的位元組不變；不得以主 DB 檔的位元組、雜湊或修改時間判讀帳內內容是否改變。
     - 這是 D-1 指定的操作者讀取路徑，不適用補充八第 5 點 (c)。
     - scheduler 執行中也可以讀；主 DB 為 WAL 模式，讀取不會使 `forecast_record` 的寫入失敗。在台北時間 22:00～22:30、23:00～23:30 執行時，最近一次執行可能顯示「沒有 end 列」（執行仍在進行），說明文件須請 CEO 避開這兩段時間；看到這種情形時，30 分鐘後再執行一次，仍是如此就告訴 coordinator。
   - 前置檢查：
     - 程序環境變數中有 `STOCK_DESK_DB_PATH`（含空字串）時 STOP，不開任何連線。
     - 不讀 `.env`，不做 port 檢查，也不檢查 repo 的 git 狀態；與 git 有關的只有存檔資料夾是否落在 git 工作樹內（見「輸出」）。
     - 主 DB 不存在、schema 不完整或讀取失敗時，不顯示 `report` 的拒絕句：腳本攔下 `report` 寫到 stderr 的全部文字，依結束碼改印風控定稿的固定 STOP 句；`report` 的 stderr 內容不得出現在畫面或檔案中。
   - 輸出：
     - 不另設白名單，也不在執行期重做 D-4 檢查：兩段輸出分別由 `report status`、`report verify --all` 原樣產生，D-4 合規由既有測試（`tests/test_forecast_report.py` 的 `d4_violations`）把關。腳本對 `report` 的輸出不增刪、不改寫任何一行，只在第 4 點規定的位置另加固定行；不 import `tests`，也不讀 `work/` 下的任何檔案。
     - 比照 RC-158a、RC-162：攔截 `BaseException`，更換 `sys.excepthook`、`threading.excepthook`、`sys.unraisablehook`，關閉警告與 logging。畫面不出現 traceback、路徑或例外文字。`status.txt` 只在取得完整輸出之後才寫入；失敗或中斷時不留下不完整的檔。
     - 執行順序：(1) 環境變數檢查；(2) 決定存檔資料夾並做 git 工作樹檢查，此時不建立資料夾；(3) 執行 `status`，stdout 與 stderr 都先攔進記憶體；(4) `status` 回傳 0 時，印出第一段與分隔句，再執行 `verify --all`，同樣攔進記憶體；(5) `verify` 回傳後，印出第二段，結束碼 1 時接著印行動句，3、4 時改印 STOP 句（第 4 點）；(6) 把已印出的內容一次寫入 `status.txt`（先寫暫存檔，完成後再改名），內容與畫面逐字相同，最後以記事本開啟。(1)、(2) 的 STOP 都在開任何連線之前；(3)～(6) 任一步失敗或中斷時，已印出的內容不收回，接著印固定 ERROR 句，不留下 `status.txt` 或暫存檔。但 `status.txt` 改名完成之後，以記事本開啟失敗不算失敗：不印 ERROR 句，也不刪除該檔；記事本沒有打開時怎麼處理，由說明文件交代。
     - 同一份內容另存為 `~/stock-desk-status/<時間>/status.txt`（`utf-8-sig`），以記事本開啟，不覆蓋舊檔。該資料夾落在 git 工作樹內時 STOP，不寫檔。
     - 新增的 STOP、ERROR、提示語與固定行，字面送風控定稿（已定稿者見風控 RC-291、RC-298、RC-299）。
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
4. **重算核對（`report verify --all`，F-3 的發現途徑）**
   - 同一支一鍵檔在 `status` 之後，固定接著執行 `report verify --all`（同一個 `--db`）。兩段依序輸出，中間以一行固定分隔句分開，存在同一個 `status.txt`。不接受參數的規定照舊，也不提供只跑其中一段的方式。
   - `verify --all` 是 D-5 第 3 點的重算：每筆紀錄只輸出 `claim_id`、T、一致與否（不一致時附問題代碼）、程式與執行環境是否與寫入時相同，以及一行結語。不輸出標籤、基準預測、暫定對照或紀錄的其他內容。讀取方式與 `status` 相同。
   - 結束碼：`status` 回傳 0 才算成功。`status` 的結束碼為 3、4 時，只印 RC-291 對應的固定 STOP 句，不執行 `verify`，不寫檔。`status` 成功而 `verify` 的結束碼為 0 或 1 時，兩段照常顯示並存檔；1（有不一致）屬正常完成，並在第二段之後另印風控定稿的固定行動句。`status` 成功而 `verify` 的結束碼為 3、4 時，照常顯示第一段與分隔句，第二段改為風控定稿的固定 STOP 句（RC-299）。這兩種情形的 `status.txt` 都照寫，內容與畫面逐字相同（含行動句或 STOP 句）。其他情形，包括任一段的其他結束碼、`SystemExit`（例如 argparse 的 2）、其他例外、中斷與寫檔失敗，依第 2 點印固定 ERROR 句，不寫檔；已印出的內容不收回。
   - 工具本身的結束碼：`status.txt` 已存檔而且畫面沒有 STOP 或 ERROR 句時為 0（含 `verify` 結束碼 1）；印了 STOP 句時為 3（含 `status` 成功而 `verify` 結束碼 3、4、已存檔的情形）；印 `ERROR: unexpected failure.` 時為 1；印 `ERROR: interrupted.` 時為 2。記事本開啟失敗不改變結束碼。結束碼只供 `.bat` 顯示，任何程式或流程都不得依它判讀帳內內容。
   - 頻率與紀錄同第 3 點，每次執行都含這一段。本一鍵檔只涵蓋 F-2 與 F-3 的發現，不涵蓋其他失效條件；任何 CEO 文件都不得寫成它涵蓋所有失效條件。
   - 接線 PR 合併前置清單中「CEO 本機執行 `report verify --all`」那一次，以本一鍵檔執行（帳內沒有紀錄，預期結語為「verify：沒有紀錄」），貼回依第 3 點保存。本一鍵檔必須在那一次執行之前合併。
   - 看到「不一致」或結語「verify：有不一致（F-3：停止記錄並查明）」時，CEO 只告訴 coordinator，不自己停止程式、刪改資料或設定；停止記錄與查明，由 coordinator 當天升級 tech-architect 與 devops-sre 處理。分隔句、不一致時的行動句，以及第二段的 STOP 句，字面依風控 RC-298、RC-299 定稿；這幾行是腳本另加的固定行，不改寫 `report` 的任何一行。
   - 執行時間：devops-sre 以合成 ledger 量測紀錄 0、250、500 筆（兩個 claim 合計）時 `verify --all` 的執行時間，寫進交件，供說明文件引用。500 筆時超過 10 分鐘，退回 tech-architect 重議頻率或拆分。

- **S-21a（逐條可檢查）**
  - AST：腳本中的子命令字面只有 `status` 與 `verify`，`verify` 只帶 `--all`；不讀 `sys.argv`，不 import harness，不 import `app.forecast.report` 以外的 `app.forecast` 模組。
  - 設了 `STOCK_DESK_DB_PATH`（含空字串）時 STOP，不開任何連線（測試）。
  - 合成 ledger 上，第一段輸出與 `python -m app.forecast.report status --db` 逐字相同，第二段與 `verify --all --db` 逐字相同，兩段之間只有固定分隔句；`verify` 結束碼 1 時照常顯示並存檔，並在第二段之後印固定行動句；`status` 結束碼 3、4 時只印固定句且不執行 `verify`；`status` 成功而 `verify` 結束碼 3、4 時，第一段與分隔句照常顯示並存檔，第二段為固定 STOP 句（測試）。
  - AST 確認腳本不 import `tests`、不讀 `work/` 下的任何檔案；以含最近一次執行、F-2 兩句與兩行缺日加註的合成 ledger 執行腳本，輸出經 `tests/test_forecast_report.py` 的 `d4_violations` 檢查為空（測試）。該合成 ledger 另含已過 `valid_until_session_estimate`、帶標籤與基準預測的紀錄，並斷言兩段輸出與所有固定行都不含任何標籤值、基準預測值或 `content_hash`（測試）。
  - e2e 擷取 stdout 與 stderr：例外、執行緒例外、警告、注入 `KeyboardInterrupt`，注入點涵蓋 `status` 執行中與 `verify` 執行中；畫面除已印出的第一段與分隔句外只有固定句，不出現 traceback、路徑或例外文字，也不留下 `status.txt` 或暫存檔。正常完成與 `verify` 結束碼 1、3、4 時，`status.txt` 與畫面逐字相同（測試）。
  - AST：畫面輸出只經 `sys.stdout.write` 寫字串，不寫 `sys.stdout.buffer`、不呼叫 `reconfigure`；`.bat` 不含 `chcp`。工具結束碼依第 4 點（測試）。Windows 上第一次實際執行（接線前那一次 `verify --all`）視為主控台中文顯示的實機確認：coordinator 核對貼回的畫面與 `status.txt` 相同；畫面為亂碼時退回 devops-sre。
  - `app/` 零差異。
  - 本一鍵檔 PR 開在產品線上，先於接線 PR 合併；上面第四項中需要接線版 `report` 的測試（最近一次執行、F-2 兩句、兩行缺日加註），隨接線 PR 加入。qa 核對一鍵檔 PR 的合併 commit，早於接線前那一次 `verify --all` 貼回的 commit。
  - qa 核對：RC-246 通知送出的 commit，晚於一鍵檔的合併 commit，也晚於說明文件的風控核可，而且早於接線 PR 的合併 commit。
  - qa 核對：本補充 append 進 ADR-0030 的 commit，早於一鍵檔 PR 的合併 commit。

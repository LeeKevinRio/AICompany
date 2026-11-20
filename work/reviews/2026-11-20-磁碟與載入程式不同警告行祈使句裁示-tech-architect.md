# DISK_DIFFERS_WARNING 祈使句的處置裁示（RC-322）

- 審查者：tech-architect
- 日期：2026-11-20
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

建議**改字**：刪掉這行 log 最後的祈使句 `; restart the scheduler process to load them`，這個改動**放進接線 PR**，在它合併之前做。

- **程序**：這行字面沒有被任何 ADR 逐字固定，所以改字不必修 ADR。但它是 CEO 看得到的 log，所以要送風控確認，再由 qa 複審。
- **為什麼放進接線 PR**：在第一筆 `forecast_run` 之前，`code_digest` 改變沒有任何紀錄方面的代價。不影響 CG-3、D-8，也不影響已登記的規則與定義雜湊。唯一的代價是接線 PR 記下的 `code_digest` 期望值要重算。
- **為什麼不另開 PR、也不保持原樣**：另開 PR 若在第一筆紀錄之後才合併，會觸發 D-5 第 6 點的重新核對，`verify` 裡也會出現「程式與執行環境：不同」。不改則只能靠文件擋，和 RC-298 的衝突仍然存在。
- **CEO 什麼時候會看到這一行**：用 `dev-up.bat` 正常啟動時不會出現。只有在 scheduler 開著、而 `code_digest` 涵蓋的原始碼或 `uv.lock` 被改了的時候才會出現。

## 各部門回報（tech-architect）

**1. CEO 什麼時候會在 scheduler 視窗看到這一行：正常使用時看不到，只有在下列例外情形才會出現**

- **觸發條件**：
  - 每次 `forecast_record` 執行時，會重算一次磁碟上的 `code_digest` 與 runtime（`recorder.py` 第 235～253 行，由第 366 行呼叫）。
  - 只比對 `app/forecast`、`app/outlook`、`app/dirdef`、`app/data/session_calendar.py`（`canonical.py` 第 77～78 行），以及 `uv.lock` 的 sha 與 Python／platform 資訊（`recorder.py` 第 182～191 行）。
  - 其他檔案改了不會觸發。
  - 重算時拋出例外，例如 pull 進行中檔案被鎖住，也算作不同（第 249～250 行）。
- **顯示到哪裡**：`main()` 呼叫 `configure_logging()`（`scheduler.py` 第 1021～1024 行），WARNING 會出現在 scheduler 視窗。handler 的細節我沒有讀。
- **會出現的情形**：
  - (a) stock-desk 開著時，有人執行 `git pull`、`git checkout`、`uv sync`，或改了上述範圍內的檔案。
  - (b) 再按一次 `dev-up.bat`：第 110 行先 pull，第 119～124 行才詢問要不要停掉舊的 port 與舊的 scheduler。CEO 若答 N，`dev-up.bat` 就此結束，舊 scheduler 繼續執行，但磁碟上已經是新程式。
  - (c) `ensure_port_free` 那一步答 N，結果同 (b)。
- **頻率**：出現後，每一次執行都會印一行（22:10、23:10，以及啟動補跑），直到 scheduler 重啟為止。
- **接線之前**：recorder 還沒接上 scheduler，不會出現。

**2. 字面沒有被逐字固定**

- ADR-0030 補充三（修訂版）第 2 點只寫：「每次執行都重算一次磁碟上的 digest。與取值時不同時，記一行 WARNING，不含標籤，照常執行。」（ADR 第 443 行，`agent-ab5f1bf75d430b1de` 工作樹）。補充三第 2 點與 S-12a（第 417、424 行）也沒有字面。
- RC-246 的「不含祈使句」原本是針對補充九第 3 點的 scheduler 拒絕原因 log，但它的意旨也適用於這一行。
- 改字的程序：
  - 不修 ADR；
  - dev-lead 在接線 PR 改這個常數，並更新引用它的測試；
  - 風控確認新字面；
  - qa 複審這一處，並核對新的 `code_digest`。
- 除了 RC-313～RC-324 判定，這行字面在 `work/reviews` 下另有兩個檔提到：2026-11-16 一鍵檔 qa 審查與 devops-sre 交件。那兩處只把它當成「固定、不含資料的 WARNING」，沒有把字面當作期望值。

**3. 放進接線 PR**

- `recorder.py` 在 `code_digest` 涵蓋範圍內，改字一定會改到 `code_digest`。
- **CG-3**：備份與 `backup_sha256` 是對主 DB 備份檔取的，和原始碼無關。不受影響。
- **D-8**：第 3 點的還原紀錄、第 4 點的重審觸發，都和這一行無關。不受影響。
- **已登記值**：CG-2 登記的是規則與定義雜湊，`code_digest` 不在已登記雜湊之列。不受影響。登記腳本有沒有額外記 `code_digest`，我沒有逐行查證，請 dev-lead 確認。
- **驗收期望值**：接線版 `code_digest`（e8e0fb63…）會變。PR 說明與前置清單裡所有寫到這個值的地方，都要換成新值；有釘這個值或這行字面的測試，也要一起更新。
- **D-5 第 6 點**：改字發生在第一筆 `forecast_run` 之前，沒有「前一次執行」可以比對，不會觸發。理由與補充十把 `report.py` 的改動放在接線 PR 相同（補充十定稿第 34 行）。
- **規格**：只刪掉 `; restart the scheduler process to load them`，其餘字面不動。新字面由風控確認。

**4. 若不改字（只有在接線排程不容許時才當作暫行做法）**

- 文件層可以暫時擋住。原因是忽略這一行不會損害紀錄：本次執行照常進行，記下的出處是實際執行的程式，所以是正確的（補充三（修訂版）第 2 點）；下次以 `dev-up.bat` 啟動時，就會載入新程式。
- 因此說明文件可以寫成：看到也不要照做，告訴 coordinator，由 coordinator 安排。這和 RC-298 一致。
- 但這樣 log 的祈使句仍然和文件互相矛盾，所以我仍建議改字。字面由風控定稿。

**5. 接線後用 `dev-up.bat` 啟動：這一行不會出現**

- `dev-up.bat` 的順序：
  - 第 110 行 `git pull`
  - 第 119～124 行停掉舊的 port 與舊 scheduler（答 Y 時）
  - 第 130 行 `uv sync --locked`
  - 第 150 行啟動 backend，等 `/health`
  - 第 166 行啟動新的 scheduler
- 新的 scheduler 在模組層 import recorder（補充三（修訂版）第 2 點），這時才取 `LOADED`（`recorder.py` 第 224 行）。取值發生在 pull 與 sync 之後，所以 `LOADED` 等於磁碟上的內容，不會印這一行。
- 例外：
  - 上面第 1 題的 (b)、(c)，也就是有一步答 N；
  - 啟動之後磁碟又被改動。
- `uv sync --locked` 已保證 lock 和程式一致，之後的 `uv run` 不會改寫 `uv.lock`。這是依 uv 的行為推論，沒有在 Windows 實測。

## 驗證

- 讀過的檔：
  - `agent-a36eaaf09f5b7743b` 工作樹的 `recorder.py` 第 50～69、160～259 行，並以搜尋確認呼叫點在第 366 行；
  - 同一工作樹 `canonical.py` 第 74～78、214～246 行；
  - 同一工作樹 `scheduler.py` 第 1021～1024 行；
  - `agent-ab5f1bf75d430b1de` 工作樹的 `dev-up.bat` 全文；
  - ADR-0030 第 411～449 行；
  - 風控 RC-322 段落。
- 行號是接線工作樹的（第 229～232 行），coordinator 提到的產品線行號是第 217～221 行，字面相同。
- 沒有查證：
  - 登記腳本是否記錄 `code_digest`；
  - logging handler 的輸出細節；
  - 有哪些測試或文件釘了 `code_digest` 期望值；
  - Windows 實機。
- 全程唯讀：沒有改檔，沒有讀 `.env`，沒有碰 `.db`。

## 下一步

- **dev-lead**：在接線 PR 刪掉那個祈使分句；更新相關測試；重算 `code_digest`，更新 PR 說明與前置清單中的期望值；確認登記腳本沒有記錄 `code_digest`。
- **風控**：確認新字面，以單項確認處理即可。
- **qa-reviewer**：複審這一處，核對新的 `code_digest`，並核對改動在第一筆 `forecast_run` 之前合併。
- **coordinator**：
  - 通知 B 維持「不列字面、英文提到的操作也不要照做」；
  - 在接線前置清單加一項：「RC-322 改字已併入接線 PR」；
  - 若改字趕不上接線，回報我，改用第 4 題的暫行做法，並另外記錄。

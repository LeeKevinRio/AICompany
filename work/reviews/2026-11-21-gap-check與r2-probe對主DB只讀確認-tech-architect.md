# gap-check 與 r2-probe 對主 DB 只讀不寫的事實確認（RC-477 第 9 點）

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

兩支 `.bat` 都不寫主 DB。範圍是工作樹 `/home/user/AICompany/.claude/worktrees/agent-a0b0b641e871f5272`，也就是 head `243596c`。兩支都沒有 ADR-0030 F-8 所列的動作（整檔還原、更換、重建，或讓核心表列數減少），寫入只落在使用者資料夾下的工作資料夾。

不過兩支的副作用不一樣，說明文字不能共用一句：
- **gap-check**：主 DB 只用 `stat` 檢查，再以 `mode=ro&immutable=1` 開啟。它不取鎖，不建立、不刪除 `-wal`／`-shm`，也不做 checkpoint。所以就這支腳本本身來說，主 DB 的修改時間與大小不會因它而變。
- **RC-306 (b) 那句**（「修改時間與大小可能改變、`-wal`／`-shm` 可能消失」）原本是對狀態報告工具訂的（見 E1，`work/reviews/2026-11-20-補充十一草稿-待風控-coordinator組版.md` 第 40 行）。拿來描述 gap-check 本身不正確。這類變化在步驟中確實可能發生，但來源是「關掉 backend／scheduler 視窗」與「`dev-up.bat` 重開」，屬於應用程式的正常行為（推論）。

## 各部門回報（tech-architect）

### gap-check.bat → `backend/scripts/gap_check.py`（事實）

**啟動**
- `gap-check.bat` 第 11 行清空 `UV_ENV_FILE`。第 30 行只執行 `uv run --no-sync python -I -X utf8 scripts\gap_check.py`，不帶任何參數。
- `[MISSING]`（第 18 行）與 `[ERROR]`（第 25 行）都在 Python 啟動之前印出，這時還沒碰到 DB。`[NOTE]`（第 33 行）在結束後印出。

**前置檢查**：`preflight`（第 766～802 行）依序檢查下列各項，任一項不過就 STOP，都在開任何連線之前：
- 程序環境變數有 `STOCK_DESK_DB_PATH`；
- `.env` 有這個鍵名（只比對鍵名，第 758～763 行）；
- 預設位置沒有 DB；
- port 8000 有程式在聽；
- 工作資料夾落在 git 工作樹內；
- git 狀態不乾淨，或 head 不在 `origin/product/stock-desk` 上。

git 呼叫都帶 `--no-optional-locks`（第 722 行）。

**開啟主 DB**：`make_copy`（第 576～609 行）
- 主 DB 旁有 `-wal` 或 `-journal` 時，直接 STOP `db_in_use`，不開連線也不建複本（第 586～587 行；`has_side_files` 只用 `exists()`，第 564～567 行）。
- 複製前後各取一次 `(st_size, st_mtime_ns)`（第 589、602 行）。
- 來源 URI 固定是 `?mode=ro&immutable=1`（第 548～557 行）。複製用 SQLite backup API：`source.backup(dest)`（第 596～598 行）。
- 複製後若出現 side file，或 signature 改變，就 STOP `db_in_use`（第 602～606 行）。複製失敗但檔案沒變，則 STOP `copy_failed`。
- 整支程式沒有任何對主 DB 的寫入呼叫。DB 連線只有三處（第 596、597、619 行），第 597 行是建立複本本身。

**暫存複本**
- 位置：`%USERPROFILE%\stock-desk-gap-check\<YYYYMMDD-HHMMSS>\copy\stock-desk.db`（第 79、84、861～870 行）。
- 讀取：同樣以 `immutable=1` 開啟複本（第 619 行），只跑一句 `SELECT trade_date FROM price_bars_cache WHERE symbol = '^TWII'`（第 100 行）。

**清理**
- 讀完後在 `finally` 刪除複本（第 873～874 行），連同 `-wal`／`-shm`／`-journal` 與 `copy` 資料夾。這發生在上網與印出結果之前。
- 刪不掉時重試 5 次、每次隔 0.5 秒，仍不行就 STOP `copy_not_deleted`（第 650～679 行）。
- 異常結束時有 `cleanup` 再補刪一次（第 822～839、942～957 行）。下次啟動時，通過前置檢查之後會清掉以前留下的 `copy`（第 682～692、867 行）。
- 成功時，工作資料夾只留 `paste-back.txt`（第 882～883 行）。

**與 scheduler 同時執行**：沒有專門偵測 scheduler 的機制，靠三道間接防線：
1. 主 DB 旁有 `-wal`／`-journal` 就 STOP；
2. 複製前後 signature 不同就 STOP；
3. port 8000 有程式在聽就 STOP（這只抓得到 backend）。

STOP 句是 RC-271 原句（第 173～179 行）。

**推論**
- WAL 模式下只要還有連線開著，`-wal` 就會存在，所以 scheduler 持有連線時應該會命中第 1 道而 STOP。
- 程式碼註解（第 554 行）寫明：`immutable=1` 只在沒有寫入者時才安全，靠上面的 STOP 把關。
- 只有 `-shm`、沒有 `-wal` 時不會 STOP。但 `immutable` 模式會忽略 `-shm`，也不會去動它。

### r2-probe.bat → `backend/scripts/r2_first_run.py`（事實）

**啟動**：`r2-probe.bat` 第 25 行只執行 `scripts\r2_first_run.py`，不帶參數。主工作樹 `/home/user/AICompany/apps/stock-desk/` 的同名兩檔，關鍵行號與內容一致（第 122、264、307、319 行）。

**開啟主 DB**
- 不用 SQLite 開主 DB。`shutil.copyfile` 把 `stock-desk.db`、`-wal`、`-shm` 中存在的檔案逐檔以一般讀檔複製（第 264、305～310 行）。
- 之後 `compare_copy` 再以一般讀檔計算來源的 sha256 做比對（第 219～233 行；`sha256_file` 用 `open(path, "rb")`，第 80～85 行）。
- 對主 DB 沒有寫入，也不建立、不刪除 `-wal`／`-shm`。

**複本**
- 位置：`%USERPROFILE%\stock-desk-n208\<stamp>\backup\` 與 `probe\`，報告放在 `probe-report\`（第 267、299～301、317～319 行）。
- `n208_count` 以 `mode=ro` 加 `PRAGMA query_only=ON` 開啟 `probe` 複本（第 122～124 行）。
- 探測子程序 `n177_n190_backtrack_probe.py` 拿到的 `--db-path` 也是 `probe` 複本（第 324～335 行）。這支探測腳本在 `refusal()` 裡會拒絕指向正式 DB 的路徑（該檔第 2118～2135 行），本身也用 `mode=ro` 加 `query_only`（第 468～470 行）。

**清理**：完全不清理。兩份完整複本與含持股、現金的 report 都保留，結尾文字甚至要求保留資料夾（第 63～71 行，「Keep the work folder … Do not delete it」）。STOP 發生在複製之後的話，`backup\` 也會留著。

**與 scheduler 同時執行**：沒有 `db_in_use` 句。防線只有兩道：
1. port 8000 有程式在聽就 STOP（第 292～295 行）；
2. 複製後雜湊不符或檔案有無不一致，就 STOP「the database changed while copying; a service is still running」（第 314～315 行）。

scheduler 開著但複製期間沒有寫入時，不會被偵測到，程式會照常完成。即使如此，主 DB 仍然沒有被寫入。

### 對照替換稿依賴第 9 點的句子（`work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md`）
- **第 124 行**：與程式碼一致。先偵測使用中的跡象，再複製，複製期間的改動會讓程式 STOP。「不保證抓得到所有情形」這句也誠實。
- **第 125～126 行**：與程式碼一致。先刪複本才上網；SQL 只讀大盤的 `trade_date`。要注意的是，backup API 複製的是整個 DB，所以複本裡有所有表。原稿已寫「複本裡有持股與現金」，沒有矛盾。
- **第 132 行**「不修改您的資料庫，不寫入快取」：事實正確。但字面接近 RC-306 的禁說句「不會改動資料庫」，能不能用由風控決定。可以改用 RC-306 (a) 的寫法「不會新增、修改或刪除任何紀錄」。
- **第 299 行已刪的「沒有讀取您的資料庫」**：就 `gap-check.bat` 自己印的 `[MISSING]`／`[ERROR]` 兩行來說是事實，它們出現在 Python 啟動之前。`uv` 自己印出的錯誤行不在 `.bat` 的控制範圍內，屬 RC-477 第 5 點，由 devops-sre 列出。

## 驗證

讀過的檔（全文）：
- `/home/user/AICompany/.claude/worktrees/agent-a0b0b641e871f5272/apps/stock-desk/gap-check.bat`
- `/home/user/AICompany/.claude/worktrees/agent-a0b0b641e871f5272/apps/stock-desk/backend/scripts/gap_check.py`
- `/home/user/AICompany/.claude/worktrees/agent-a0b0b641e871f5272/apps/stock-desk/r2-probe.bat`
- `/home/user/AICompany/.claude/worktrees/agent-a0b0b641e871f5272/apps/stock-desk/backend/scripts/r2_first_run.py`

讀過的段落（部分）：
- `n177_n190_backtrack_probe.py` 第 2110～2169 行，另以 Grep 查連線與 PRAGMA；
- RC-477 原文；
- ADR-0030 第 334 行（F-8）；
- 補充十一草稿第 40 行（E1）；
- RC-305～312 判定的 RC-306；
- 替換稿第 184～221 行；
- 原草稿第 118～135、294～303 行。

沒有查證的事：
- 沒用 git 確認工作樹 head 是否確實是 `243596c`；也沒確認 `product/stock-desk` 上的 `r2_first_run.py` 是否和工作樹一致（只比對了主工作樹的關鍵行，主工作樹目前是哪個分支也沒確認）。
- 沒有實際執行，也沒在 Windows 上實測。沒查證的點包括：
  - `immutable=1` 在 Windows 上確實不留 side file；
  - 檔案的最後存取時間（atime）會不會變；
  - r2 的 `shutil.copyfile` 持有讀取 handle 時，會不會影響 scheduler 寫入或刪除 `-wal`。
- 沒有確認主 DB 目前是不是 WAL 模式。
- 關三個視窗與 `dev-up.bat` 重開對主 DB 的影響，沿用 R 系列已核可的結論，我沒有重查。
- `uv` 本身印出的畫面行。
- 探測腳本全文只讀了上述片段。

## 下一步

- 轉給 creative-lead：第 132 行改不改字由風控決定。RC-306 (b) 那句不要原樣套到 gap-check 本身。
- devops-sre 交 RC-477 第 5 點時，請一併寫明 `uv` 自身錯誤行的形式。
- 可轉給風控的結論句：

> 兩支 `.bat` 對主 DB 只讀不寫，也沒有 F-8 所列的整檔還原、更換或重建；`gap-check.bat` 以 immutable 唯讀方式複製主 DB，偵測到 `-wal`／`-journal` 或複製期間檔案變動就停下，本身不改變主 DB 的修改時間、大小與 `-wal`／`-shm`，複本在比對前刪除；`r2-probe.bat` 以一般讀檔整檔複製主 DB 及其 `-wal`／`-shm`，不開啟主 DB，但兩份完整複本與報告會留在使用者資料夾的 `stock-desk-n208` 下、不自動刪除；兩者的副作用都只限於使用者資料夾下的工作資料夾，步驟中主 DB 檔的變化來自關閉與重開 stock-desk 本身。

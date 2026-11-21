# 退役分支三件實作選擇確認與合併前 merge-base 核對

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- **表態：RC-401、RC-402 的補字與 RC-406，我沒有異議。**
- 三項實作選擇 (i)、(ii)、(iii) 都**確認**。(i) 不需要在補充十二補讀法，所以不必再送風控。
- 退役分支在規格面**沒有未決事項**，但合併時要照 F10 與下面「排序問題」的做法重做核對。qa 審查另行進行。
- 排序問題：**要重做**。每次 merge product 之後、合併之前，以當時的 merge-base 重做一次。coordinator 記錄，qa 以 `git diff` 核對，記在 F10 的同一筆紀錄裡。

## 二、各部門回報（tech-architect）

### (i) 以基底版本搬移：確認

- 第 1 點 (b)「函式本體逐字不變」的比對對象，是本 PR 合併時 merge-base 上的原函式，不是某個固定時點的 product。
- 依第 3 點 (b)，本 PR 排在 CG-2 一鍵檔退役 PR 之後，屆時 merge-base 必然已含登記分支，原函式就是三行版。
- 如果搬 product 現行的一行版，在合併時的狀態下測試會紅；而且相對 merge-base 而言，等於改了函式本體。這反而違反 (b)。
- 第 65～66 行的英文註解在函式本體內，一起逐字搬過來是對的。
- 第 1 點 (d) 的「`backend/.gitattributes` 零差異」是指 PR 自身的 diff，也就是相對 merge-base 零差異。登記帶進來的 M-7 兩行屬於登記 PR，不屬於本 PR。
- 不另補 ADR 字面的理由：PR diff 本來就以 merge-base 為準，S-21 第 1 點「附 diff」與 (d)「`git diff --stat`」的讀法自然成立；第 3 點 (b) 的順序也已經保證基底一致。再補一句只會多一輪風控，沒有增加可檢查性。
- 這個讀法以本報告為準，qa 照這裡核對即可。

### (ii) 分節註解沒有保留：確認

- 兩行分節註解都不在函式本體內，也不在 (b) 列舉的搬移對象裡。
- 第二行點名的 `check_pinned_eol` 已經刪除，留著反而名不副實。
- 新檔只有五個測試，不需要分節。

### (iii) `PIN` 沒有搬：確認

- 我讀過原檔：`PIN` 只出現在 `real.check_pinned_eol(...)` 的呼叫裡，五個搬移測試中用到它的三行正是 (b) 指定刪除的那三行。
- (b) 的常數清單也不含 `PIN`。搬過來就成了沒人用的常數。
- `typing.Any` 同理。

### 排序問題：合併前以當時的 merge-base 重做

理由：
- F2 寫的是「本退役 PR 的 merge-base」，指的是合併當下的 merge-base。`76e5309a` 只是交件時的狀態。
- 分支每次 merge product，head 與 merge-base 都會前移。依 F10（RC-401），head 一變動就要重新記錄、重新核對，F2 的 merge-base 核對應該一起重做。

做法：
- **coordinator** 在最後一次 merge product 之後、合併之前，在 F10 的同一筆 `work/` 紀錄裡加記兩項：
  - 當時 merge-base 的 40 碼 commit id；
  - `git rev-parse <merge-base>:apps/stock-desk/pipeline-acceptance.bat` 的 blob id。
- **qa** 以 `git diff <G_acc>:apps/stock-desk/pipeline-acceptance.bat <merge-base>:apps/stock-desk/pipeline-acceptance.bat` 的輸出為空來核對。qa 只能下 `git diff`，merge-base 的 id 由 coordinator 提供。
- 不同就停止，不得合併，升級 tech-architect。
- 同一時點，qa 也要以當時的 merge-base 重新核對 (i) 的逐字比對：`git diff <merge-base>:apps/stock-desk/backend/tests/test_pipeline_acceptance_real_eol.py <head>:apps/stock-desk/backend/tests/test_lockfile_eol.py`，差異只能是 (b) 允許的刪除，再加上 import、`PIN`、分節註解、docstring 與未搬的測試。
- 這屬於 F2、F10 的執行細節，不改字面，不必送風控。

### 另提醒 qa

- 看 S-21 第 1 點的檔案清單時，要用 `--no-renames`。凍結檔與 `.bat` 的 blob 相同，git 會顯示成 `R100` 改名，不加這個選項會誤判清單。
- dev-lead 的 (iv)（「CRLF 也一起保留」）已由 F1 處理。

## 三、驗證

- 已讀：
  - dev-lead 交件全文；
  - 新檔 `test_lockfile_eol.py` 全文（108 行）；
  - product 原檔 `test_pipeline_acceptance_real_eol.py` 全文（264 行）。
- 我逐一對照過五個測試的函式本體、`_isolated_git`、`git`、`make_repo` 與四個常數。差異只有三處：第 159～160 行與第 169 行的 `real.` 斷言，以及 `test_the_backend_attribute_file_pins_uv_lock_to_lf` 的一行版換成三行版。三行版就是交件中列出的基底差異。
- 沒有查證（全部轉述自 dev-lead）：
  - 基底 `c559b4af` 上的原函式字面，我沒有讀基底的檔；
  - 所有 blob id 與 commit id；
  - 全套測試結果。
- 新版補充十二與 RC-401～RC-406 報告，我沒有重讀全文，表態是依 coordinator 摘要的兩處補字。
- 唯讀，沒寫檔；沒讀 `.env`，沒碰 `backend/data/`。

## 四、下一步

1. qa-reviewer 審查退役分支：
   - 依上面 (i) 的讀法，以 merge-base 為準核對；
   - 檔案清單用 `--no-renames`；
   - G_acc 核對依 F10。
2. coordinator 依「登記 PR → CG-2 一鍵檔退役 PR → 本退役 PR」的順序推進。本 PR 最後一次 merge product 之後，記錄 merge-base 與 F10 的 blob id，交 qa 核對後才合併。
3. 依 RC-406，三支帶有基準檔的分支都要在登記紀錄 commit 之後才合併。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-21-驗收一鍵檔退役分支交件-dev-lead.md`
- `/home/user/AICompany/.claude/worktrees/agent-a25860c7a058acad0/apps/stock-desk/backend/tests/test_lockfile_eol.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_eol.py`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二F10與F8確認RC401至RC406-風控.md`

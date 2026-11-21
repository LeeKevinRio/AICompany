# local-run 放置位置重判

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **local-run 放置位置**
  - 【裁示】採甲：在 `product/stock-desk` 上直接改，從 product 開 `chore/local-run-referral`。
  - main 側的 `chore/agent-local-run-referral` 作廢，不開 PR，不合併。
  - 原裁示「改版進 main」建立在一個錯誤前提上，就此撤回。
- **更正**
  - 我先前普查報告說「product 的 local-run 可能是 product 合併過來的副本」，這句不成立。
  - 實情是 main 從來沒有這個檔，它是 product 上的 `534eb9d` 新增的。
  - 錯誤原因：我當時沒有用 `git ls-tree origin/main` 核對，就下了結論。
- **流程**
  - 【裁示】維持 P0，要在接線 PR 合併前完成。
  - 由 qa-reviewer 審，含 Codex；Codex 不可用時單家審，並記下原因。
  - 不必送風控。

## 各部門回報（tech-architect）

### 1. 放哪條線：甲

理由：
- (a) 這個 skill 的實質內容只對 stock-desk 有意義。它是產品內容，不是員工能力。章程第 1 節「main 零產品耦合、產品線放產品」的邊界，指向 product。
- (b) 乙等於替 main 新增一個沒有實質內容的 skill。這需要改章程第 5 節的清單和 `.claude/skills/README.md`。product 下次 `merge origin/main` 時還一定會 add/add 衝突（devops-sre 的推論，我同意，未演練）。成本高，卻沒有解決 product 上舊版會自動觸發的問題，因為那還是要等 product 同步。
- (c) 丙（直接刪掉）不採用。刪了以後，新會話遇到「啟動／重啟」時沒有任何轉介規則，coordinator 會回到臨場回答，正是要防的情形。轉介版的價值在「禁止事項」與「去哪裡找定稿字面」，不在指令本身。
- (d) 甲不需要改章程第 5 節。那份清單列的是 main 的員工線 skill，product 不得改 `CLAUDE.md`。
  - 【推論】已知代價：日後如果 main 也新增同名的 `local-run`，product 同步時會衝突。目前沒有這個計畫，不為此改名。
- (e) 「轉介、不輸出指令」這個通用規則要不要日後收進員工線，另案評估，不在本次範圍。

### 2. 轉介版內容

**底稿**
- 【裁示】devops-sre 那份 41 行稿可以當底稿：`/home/user/AICompany/.claude/worktrees/agent-ad1709704c47c91c6/.claude/skills/local-run/SKILL.md`。
- 它要做為 product 上現有 120 行版（`/home/user/AICompany/.claude/skills/local-run/SKILL.md`）的整檔替換。

**放在 product 上之後的必要調整**（逐條可查）：
1. 刪掉第 8～9 行「屬員工線，對產品零耦合」的宣告，因為放在 product 上這句不成立。改寫成「本 skill 只屬 `product/stock-desk`，不 merge 回 main」。
2. 可以直接寫出定稿請求的代號：R1、R2、R3、R3-0、R3-0C、RC-447。
   - 只寫代號，不寫字面，也不摘要成自己的話。
   - 同時寫明「以 `work/dispatch/2026-10-17-後續追蹤清單.md` 為準；本檔和清單不一致時，以清單為準」。
3. 第 4 點的暫時轉介目標，直接指向上面那份追蹤清單。
4. 第 1～6 條禁止事項全數保留，不得刪減。
5. 不得含任何對 CEO 的字面；也不得有任何「設定或檢查 `STOCK_DESK_DB_PATH`」的句子。原因是 `forecast_record` 遇到環境裡有這個變數就會跳過，見我本日 RC-460 報告。

**被刪除的工程內容搬到哪裡**
- 【建議】搬進 product 的一份新工程文件，例如 `apps/stock-desk/docs/本機執行-工程參考.md`。
  - 不放進 `apps/stock-desk/README.md`，因為它可能有 CEO 操作段。
  - 也不塞進 `族群動能-主機部署手冊.md`，因為範圍不同，而且受 RC-430 保護。
- 新文件的要求：
  - 檔頭仿 RC-428 標註「團隊工程參考，不是 CEO 的操作文件」。檔頭字面送風控。
  - 搬過去時要同步更正兩件事：
    - 刪掉「環境變數（`STOCK_DESK_DB_PATH` 等）由父程序繼承」可被讀成「可以設定」的意思，補上「執行預測紀錄的主機不得設定」的事實；
    - 備份／還原要註明主 DB 內含預測紀錄帳，「尚未演練」照實保留。
- 時點：不是 P0，接線 PR 合併後由 devops-sre 處理，可以和 RC-436 的手冊 docs PR 同批。
- 搬移期間內容不會遺失，因為內容在 `534eb9d` 的歷史裡。

### 3. main 側分支

- 【裁示】作廢即可：不開 PR、不合併，追蹤清單記為「作廢（前提錯誤）」，並附 head `8f09d2a7…`。
- 刪除遠端分支不是必要動作，不阻擋任何事。要刪就照 coordinator 的做法先問 CEO；不刪也可以。

### 4. 時點與流程

- 【裁示】維持 P0，在接線 PR 合併前完成。理由不變：product 上舊的 120 行版會在新會話自動觸發，輸出手動指令、`.env`、`taskkill` 等內容。
- 審查：qa-reviewer 加 Codex；Codex 不可用時單家審，並記下原因。qa 要核對：
  - (a) 第 2 點的 1～5 條；
  - (b) Grep `uv run|npm run|git |taskkill|kill|lsof|STOCK_DESK_DB_PATH|\.env`，命中只能出現在禁止事項清單裡；
  - (c) diff 只動 `.claude/skills/local-run/SKILL.md`；
  - (d) 對 `apps/stock-desk/backend/app/` 零差異，不影響登記一鍵檔的 tree id。
- 不必送風控，因為不含對 CEO 的字面。日後那份工程參考文件的檔頭另外送風控。

## 驗證

- 已讀：
  - `/home/user/AICompany/work/reviews/2026-11-21-local-run轉介版交件-devops-sre.md`；
  - 41 行轉介稿全檔；
  - 對 product 版 `.claude/skills/local-run/SKILL.md` 做了 Grep：第 42～44、71～84、104～110 行含 `STOCK_DESK_DB_PATH`、`--env-file`、DB 檔表，以及備份與還原步驟；
  - Glob `apps/stock-desk/{README.md,docs/*.md}` 和 `.claude/skills/*/SKILL.md`。
- main 上沒有這個檔，是 coordinator 以 git 查證的。我沒有自己跑 git，因為唯讀職能可用的指令只限 `codex`、`git diff`。
- 沒有查證：
  - R1、R2、R3、R3-0、R3-0C、RC-447 這六個代號在追蹤清單裡的現行狀態，沒有讀。由 qa 用 Grep 核對。
  - 我沒有核對 product 的 `README.md` 是否已有 CEO 操作段。
  - add/add 衝突的實際情形沒有演練過。

## 下一步

- devops-sre：
  - 從 `product/stock-desk` 開 `chore/local-run-referral`，用 41 行稿照第 2 點調整後整檔替換，然後交 qa。這是 P0。
  - 接線 PR 合併後，另開 PR 新增工程參考文件，檔頭送風控。
- coordinator：在追蹤清單把 main 側分支記為作廢；也記下我更正了「副本」那句說法。
- 送風控：本件沒有；日後工程參考文件的檔頭要送。
- 須 CEO 決定的事：沒有。刪除遠端分支不是必要動作；若要刪，照慣例先問 CEO。

# README 第 10、12 處改字交件（RC-484、RC-485）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
第 10、12 處已換成風控新定稿（RC-485、RC-484），加了一個 commit 並 fast-forward push 到 `docs/readme-backup-restore`。未 amend、未 rebase、未 force，未開 PR。
- 新 head 完整 SHA：`5e6ad3cc1b6a8579b41f6b39bca02d0ea028d2f5`
- 前一個 head：`9f20ad2e476240f0ea225b4bc0b299595748cb4a`
- push 輸出：`9f20ad2..5e6ad3c  docs/readme-backup-restore -> docs/readme-backup-restore`
- worktree：`/home/user/AICompany/.claude/worktrees/agent-a8f22f2289ce5e462`（`git status` 乾淨）
- commit：`docs: README 第 10、12 處依 RC-484、RC-485 改字`，結尾兩行 trailer 如您指定。

## 各部門回報（devops-sre）
- 區塊由腳本從風控檔擷取，不是手打。
- 替換前先確認套用後第 150～154、173～175 行與前一版定稿完全相同。每個變動行的舊文在 README 中恰好出現一次，才替換。
- 兩處各只有區塊的第 2 行不同，所以只換這兩行：套用後第 151 行與第 174 行。
- 沒有判斷歧義，區塊縮排與定稿一致。第 151 行是清單續行，保留兩個空白開頭。

## 驗證
- `git diff 9f20ad2… --stat`：`apps/stock-desk/README.md | 4 ++--`，1 file changed, 2 insertions(+), 2 deletions(-)。
- 完整 diff 的變動內容：
  - hunk 1，第 151 行：`並先清掉 volume 內舊的 *.db-wal／*.db-shm,理由同原生路徑;再 docker compose start。` 換成 `並先清掉 volume 內舊的 *.db-wal／*.db-shm(不要讓舊的 -wal 留在原地,否則它可能被套用到剛還原的 .db 上);再 docker compose start。`
  - hunk 2，第 174 行：`dev-up.bat 啟動時會強制結束它,若剛好…` 換成 `dev-up.bat 啟動時若發現它還在跑,會問 Stop the old scheduler? [Y/N];答 Y 會強制結束它,若剛好正在記錄預測紀錄,該次記錄會中斷;答 N 則 dev-up.bat 不會繼續啟動。`
  - 兩個 hunk 都只有一行 -、一行 +，上下文行不變。
  - 完整 diff 已在這輪工具輸出中，兩個 hunk 的 `@@` 起點分別是 148、171，第一個 `-` 行在其後第 4 行，即第 151、174 行。
- 兩行與定稿逐字比對：腳本是直接把風控檔的區塊字串寫入，兩行逐字相同。
- 行數：361，以換行結尾。
- CR：無。行尾空白：Grep `[ \t]+$` 零命中。
- RC-459 第 4 點 Grep，結果與上一輪完全相同：
  - `local-run`、`attest`、`必要時由您決定`、`手冊`：零命中。
  - `系統環境優先`：只有第 307 行，且帶〔…未在 Windows 實測〕註記。
  - `cp apps/stock-desk/.env.example`：只有第 24 行。

## 下一步
- 交 qa-reviewer 依 RC-486 核對。
- 向風控送單項確認時，head 請用 `5e6ad3cc1b6a8579b41f6b39bca02d0ea028d2f5`。
- 合併仍要等正式登記完成後，由 coordinator 安排。
- 沒有查證的事：
  - `.env.example` 有沒有 `STOCK_DESK_DB_PATH` 仍是「未查證（權限拒讀）」。
  - 前端兩個讀取 README 的 vitest 測試仍未實跑（`frontend/` 沒有 `node_modules`）。`inventoryPage.test.ts` 要求 README 含 `` `/positions` ``，但 base 就沒有，所以那個斷言在 base 已不成立，與本次改動無關。
- 回滾：捨棄分支，或 revert `5e6ad3c`。上一輪 commit `9f20ad2` 不受影響。

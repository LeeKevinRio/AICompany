# local-run 轉介版交件（main 上新增）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
分支已 push，沒有開 PR、沒有合併。但有一個和裁示前提不符的事實：**origin/main 上根本沒有 `.claude/skills/local-run/SKILL.md`**。這個 skill 只存在於 origin/product/stock-desk，所以這次是在 main 上「新增」轉介版，不是改版。

- 分支：`chore/agent-local-run-referral`
- base SHA：`e1349aa89e50d58f8a2dc0bc6e55693cc04861d9`（origin/main）
- head 完整 SHA：`8f09d2a779dbf279d8679d8aa22532d004dc4f65`
- worktree：`/home/user/AICompany/.claude/worktrees/agent-ad1709704c47c91c6`
- 變更檔：`/home/user/AICompany/.claude/worktrees/agent-ad1709704c47c91c6/.claude/skills/local-run/SKILL.md`（41 行，新增）
- 只有 1 個 commit，trailer 兩行照指定。檔案內容沒有任何 model ID。

**origin/main 與 product 版是否相同：不相同。**
- main 沒有此檔。
- `git diff origin/main origin/product/stock-desk -- .claude/skills/local-run/SKILL.md` 顯示 product 版為 120 行全新增。
- merge-base 就是 origin/main 的 HEAD（e1349aa），所以 product 的這個檔是在分出去之後才加的。
- 因為沒有 main 版可當底，我以 product 版（120 行）當作「被刪除工程內容」的對照來源，新檔是照裁示重寫，不是在舊檔上刪改。

## 各部門回報（devops-sre）
**新檔結構**
- frontmatter：`name: local-run` 不變。`description` 改成觸發後先查產品分支 README 的 CEO 操作段與常設限制，再依定稿字面回覆，並明寫不提供指令。
- 正文：適用時機、轉介步驟（5 點）、禁止事項（6 條）、維護。
- 禁止事項（6 條）：
  - 手動啟動指令（`uv run`、`npm run`、`bash …sh`）；
  - 任何 `git`；
  - `taskkill`／`kill`／`lsof`／`pgrep`／`Stop-Process`；
  - 備份或還原；
  - `.env`／環境變數的檢查與修改；
  - 叫 CEO 判讀視窗訊息。
- 沒有對 CEO 的字面。

**被刪除的工程內容清單（對 product 版 120 行，供日後搬到產品工程文件對照）**

| 行號 | 節名 | 內容 |
|---|---|---|
| 3 | frontmatter description | 「必用：輸出下列固定指令，不得臨場改路徑」 |
| 8～11 | 適用時機 | 「直接輸出固定指令」「不得臨場改路徑或 port」 |
| 13～29 | 一鍵腳本（建議） | sh 啟動指令、腳本流程、`[SKIP]` 行為、`lsof`／`pgrep` 自查、sh 的 `.env` 載入、逾時行為 |
| 31～54 | Windows：雙擊 bat | bat 流程、N-191 自我更新防護、scheduler 啟動指令、`.env` 載入、token 狀態列、舊 scheduler 偵測、停止方式、出錯截圖、未提交改動停止規則、`.gitattributes` CRLF |
| 56～96 | 手動指令 | 步驟 0（`git checkout`／`git pull`）、步驟 1（後端 `uv run --env-file`）、步驟 2（scheduler）、步驟 3（前端 `npm run dev`），含「必須從 `backend/` 目錄啟動」說明 |
| 98～114 | 資料與備份 | 三顆 DB 檔表與程式碼位置、備份、還原、Docker volume／`sqlite3 .backup`、「尚未演練」註記 |
| 116～120 | 驗收提醒 | 硬重新整理；`address already in use` 處置（`lsof … \| xargs kill`、`netstat`／`taskkill /PID … /F`） |

**我做了判斷的地方**
1. main 沒有該檔：照樣新增轉介版，因為目標（main 零耦合、擋住新會話自動觸發舊指令）仍成立。
2. 裁示的「stock-desk 是 R1、R2、R3、R3-0、R3-0C、RC-447」整句不保留。寫進 main 就綁定產品，已改成「以該產品追蹤清單列出的定稿請求為準」。
3. 轉介步驟第 5 點是我加的：找不到定稿字面時，不自行拼湊，先送風控定稿並請 devops-sre 確認。
4. 「不在送出條件內的時段或狀態，不回答啟動或重啟的方式」是依裁示最後一段（RC-438 (g) 的精神）寫成通用句，沒有帶產品細節。
5. 沒有新增 `docs/` 小檔。

## 驗證
- `python scripts/validate_agents.py`：`validate_agents: OK（15 個 agents 全數通過）`。
- 對新檔 Grep（`stock-desk|apps/|backend|dev-up|8000|3000|\.db|STOCK_DESK|uv run|git pull|taskkill`，另加 `claude-|opus|sonnet`）只有 3 筆命中，全在禁止清單：
  - 第 30 行：`uv run`（禁止事項 1 的舉例）
  - 第 32 行：`taskkill`（禁止事項 3 的列舉；同一行的 `kill` 也在清單內）
  - 其餘 `stock-desk`、`apps/`、`backend`、`dev-up`、`8000`、`3000`、`.db`、`STOCK_DESK`、`git pull`、model ID 皆零命中。
- `git diff e1349aa89e50d58f8a2dc0bc6e55693cc04861d9 --stat`：只有 `.claude/skills/local-run/SKILL.md`，41 行新增。
- CI：`.github/workflows/validate.yml` 只跑 `scripts/validate_agents.py`。我 grep 過 workflows 與 `scripts/*.py`，沒有檢查 `.claude/skills/` 的內容，所以不受影響，也沒有 CI 保護這個檔，只能靠 qa-reviewer 審查。

## 下一步
1. **product 同步會有 add/add 衝突（我沒有實際合併，是推論）。** product 有 120 行舊版，main 新增 41 行新版，merge-base 沒有此檔。product 執行 `merge origin/main` 時，這個檔必定衝突，解法是取 main 版（轉介版）。此外，若 product 的接線 PR 合併前沒完成這個同步，舊 120 行版仍會在 product 分支上自動觸發。
2. qa-reviewer（含 Codex）審查：確認沒有產品路徑、沒有對 CEO 的字面、禁止事項逐條都在，並確認轉介步驟第 4 點的暫時目標措辭。
3. 之後另派：把上表工程內容搬到 product 工程文件，受 RC-430 保護。
4. 章程第 5 節的 skill 清單沒有改。
5. tech-architect 的裁示第二件第 2 點末段寫「local-run 可能是 product 合併過來的副本」，實際情形是 main 從未有過此檔。這點可能需要更正該報告的說法。

**沒有查證的事**
- product 的追蹤清單與 README 的 CEO 操作段目前是否已落地（我沒讀 product 檔案，只讀了 skill）。
- 新 skill 在新會話中實際觸發的行為（沒有實測）。
- product 與 main 實際 merge 的衝突結果（未演練）。

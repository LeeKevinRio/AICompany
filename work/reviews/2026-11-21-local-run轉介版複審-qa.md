# local-run 轉介版複審（單家審查）

- 審查者：qa-reviewer
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**PASS_WITH_NOTES**（單家審查：Codex 在本環境不可用，依 CEO 決策 #58 未嘗試呼叫；Codex 第二意見缺席，須在追蹤清單記載）。

BLOCKING_ISSUES=false。必要調整 1～5 全數做到，另有 2 項 NOTE，建議補但不擋。

## 各部門回報（qa-reviewer，逐項附證據）

檔案：`/home/user/AICompany/.claude/worktrees/agent-ad1709704c47c91c6/.claude/skills/local-run/SKILL.md`（42 行）。

### 1. tech-architect 必要調整 1～5：全部做到
- (1) 做到。第 8 行寫「本 skill 只屬 `product/stock-desk`，不 merge 回 main。」，沒有「屬員工線、零耦合」的殘句。
- (2) 做到。
  - 第 20 行只列代號 R1、R2、R3、R3-0、R3-0C、RC-447，並註明「只列代號，字面與送出條件以追蹤清單為準」。沒有字面、沒有摘要。
  - 第 24 行：「以 `work/dispatch/2026-10-17-後續追蹤清單.md` 為準；本檔和清單不一致時，以清單為準。」
- (3) 做到。第 23 行，暫時轉介目標為該追蹤清單，操作段落地後改指向該段。
- (4) 六條禁止事項全在，第 31～36 行逐條對應：
  - 第 31 行：手動啟動指令。
  - 第 32 行：任何 `git` 指令。
  - 第 33 行：`taskkill`、`kill`、`lsof`、`pgrep`、`Stop-Process`。
  - 第 34 行：備份或還原。
  - 第 35 行：`.env` 與環境變數的檢查與修改。
  - 第 36 行：請 CEO 判讀視窗或終端機訊息。
- (5) 做到。全檔沒有對 CEO 的字面。第 41 行明寫「本 skill 不寫任何給 CEO 看的字面」，是對 coordinator 的規則，不是字面。全檔沒有任何設定或檢查 `STOCK_DESK_DB_PATH` 的句子（見第 2 項 Grep）。

### 2. Grep `uv run|npm run|git |taskkill|kill|lsof|STOCK_DESK_DB_PATH|\.env`
我多加了 `sh` 擴大範圍，命中如下：
- 第 3、8、40～42 行：命中的是 `skill`、`should` 之類的字串（`skill` 含 `kill`），不算。
- 第 31 行：`uv run`、`npm run`、`bash …sh`，在禁止事項 1 內。
- 第 33 行：`taskkill`、`kill`、`lsof`，在禁止事項 3 內。
- 第 35 行：`.env`，在禁止事項 5 內。
- `git ` 字樣：第 32 行是「`git` 指令」，在禁止事項 2 內。另 `STOCK_DESK_DB_PATH` 零命中。
- 判定：所有實質命中都在禁止事項清單內，沒有越界。

### 3. diff 範圍
- `git diff b1990a4… 0280efd… --stat`：只有 `.claude/skills/local-run/SKILL.md`，28 增 106 刪，與 numstat 相符。
- `--stat -- apps/stock-desk/backend/app`：輸出為空。對 `app/` 零差異，不影響登記一鍵檔的 tree id。

### 4. 六個代號在追蹤清單的存在
Grep `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`（只確認存在，不審字面）：
- R1、R2、R3、R3-0：第 698～700 行有命中，另有 R1 在第 412、693、696、697 行。
- R3-0C：第 702 行，有兩處。
- RC-447：第 702 行，有兩處。
- 第 702 行同列有「R1、R2、R3」並列。
- 第 703 行有 `local-run` 常設規則，第 709 行有放置位置重判紀錄。

### 5. frontmatter
- 第 1～4 行為合法 YAML，`name: local-run` 不變，`description` 為單行。
- description 觸發：涵蓋「啟動、重啟、跑起來、開起來測試」四個詞，與 CEO 常用說法一致，能讓新會話觸發。
- 觸發後第一個動作：「先做兩件事：查 README 的 CEO 操作段，以及有無常設限制」，並寫「本 skill 不提供任何指令，coordinator 不得臨場輸出」。符合「先查定稿字面與常設限制，不輸出指令」。

### 6. 與普查報告「改好之前 coordinator 要遵守的規則」比對（該報告第 309～318 行）
一致或不矛盾的：
- 不輸出指令：新檔第 17、31～36 行。
- 重啟屬重新啟動，照實記錄並轉 devops-sre，不輸出指令：新檔第 22 行。
- 請 CEO 重新執行只走 R1、R2、R3 及其送出條件；畫面行走 R3-0、R3-0C：新檔第 20 行。
- 不在送出條件內的時段或狀態不回答啟動或重啟方式（對應 RC-438 (g)）：新檔第 21 行。
- 找不到定稿句時先送風控：新檔第 25 行。

新檔沒有明寫的兩點，皆判為 **NOTE（不擋）**：
- NOTE-1：普查「CEO 要啟動而 stock-desk 沒開著＝原有習慣（雙擊 `dev-up.bat`），只能用已定稿且提到 `dev-up.bat` 的句子」。
  - 新檔只有一般性的「只轉述已定稿字面」（第 18 行），沒有點名這個情境。
  - 不擋的理由：第 18、23 行已指向追蹤清單，追蹤清單第 703 行有這條常設規則，且清單為準。
  - 風險：新檔不寫 `dev-up.bat`，是有意避免輸出指令，我認為可接受。
- NOTE-2：「預檢到登記完成之間不回答啟動或重啟方式」。
  - 新檔第 21 行以一般形式涵蓋「不在送出條件內的時段或狀態不回答」。
  - 這裡只說在「有常設限制」時成立。若追蹤清單沒有該常設規則，可能有縫隙。
- 另記：普查提到「CEO 主動要求重啟時的回覆字面，目前沒有定稿，要送風控新訂」。新檔第 25 行「找不到定稿字面時不自行拼湊，先送風控」已涵蓋。

### 7. 被刪除的舊內容中，屬防護規則而非指令、新版沒有涵蓋的
列出並判斷影響（皆為 NOTE，不擋）：
- 「必須從 `backend/` 目錄啟動，否則另生一組 DB、資料不連續」（舊第 77～79、87 行）：防護目的是避免資料分叉。新版沒有。
  - 影響：新版不教任何手動啟動，因此這條在新版下不會被觸發。已列在新檔第 40 行「資料位置等工程內容寫在產品工程文件」。
  - 要求：搬進 `apps/stock-desk/docs/本機執行-工程參考.md` 時必須保留這條。
- 「scheduler 同一時間只能開一個，兩個同時跑會讓每則警示發兩次」（舊第 50、87 行）：防護規則。新版未涵蓋。
  - 同樣因為新版不輸出啟動指令而不致越界，但搬移時要保留。
- 「自我更新防護 N-191：改 dev-up.bat／sh 時不要把主流程搬出防護區塊、結尾之後不要加指令」（舊第 39～41 行）：對維護腳本的工程員是防護規則，不是對 CEO 的指令。新版沒有，也不該放在這個 skill（涉及腳本內部）。要求：必須搬到工程參考文件，否則修改腳本者會失去這條提醒。
- 「備份要先停機、不停機複製不保證一致；還原要清掉舊 `-wal`」（舊第 108～111 行）：防護規則，也是備份／還原步驟。新版因禁止事項 4 而不寫，這是 tech-architect 裁示（還原屬 F-8 與補充九第 2 點）。工程文件搬移時，要註明主 DB 內含預測紀錄帳（tech-architect 已要求）。
- 「`.env` 的 `UV_ENV_FILE` 載入、已設系統環境變數優先」與「`STOCK_DESK_DB_PATH` 由父程序繼承」：新版有意不含。tech-architect 要求搬移時更正成「執行預測紀錄的主機不得設定」。
- 判斷：目前沒有任何「防護規則被刪而新版造成實質風險」的情形。因為新版整體禁止輸出指令，這些防護只在有人手動啟動時才有意義，而那已被禁止。唯一風險是搬移期間內容只存在於 `534eb9d` 的歷史，這點 tech-architect 已接受（P1，接線 PR 合併後由 devops-sre 處理）。

### 8. model ID、祕密
全檔無 model ID、無祕密、無 token、無 webhook、無金鑰。

## 驗證
實際執行的指令（皆在 `/home/user/AICompany`，皆為單一 `git diff`）：
1. `git diff b1990a430ae070d4f77497a184d84a45bbc62cea 0280efd41a1270185a929f6f51e5296261c46633 --stat`
2. `git diff b1990a430ae070d4f77497a184d84a45bbc62cea 0280efd41a1270185a929f6f51e5296261c46633 --stat -- apps/stock-desk/backend/app`（空輸出）

另以 Read／Grep 讀取：新檔全文、舊檔全文、tech-architect 重判報告全文、普查報告的相關段落、追蹤清單的 Grep 命中。沒有讀任何 `.env*`，沒有碰 `apps/stock-desk/backend/data/`。

沒有查證的事：
- 沒有跑 `scripts/validate_agents.py`（唯讀權限不含，且這是產品線 skill，不在 agents 驗證範圍）。
- 沒有核對 product 分支 README 目前是否已有「給 CEO 的操作」段（tech-architect 也沒查）。新檔對「尚未落地」有備援（第 23 行），所以不擋。
- 追蹤清單第 703 行常設規則的完整字面（行過長被截斷），我只確認其存在，並對照其可見部分與新檔不矛盾；沒有審六個代號的字面內容。
- 沒有確認 HEAD 的 `git log`、commit 作者與附註（無法使用其他 git 子指令）。
- Codex 第二意見：未執行，原因為環境不可用（CEO 決策 #58）。

唯讀權限判準常數：兩道機械檢查屬未跑到的部分（Bash 只准單一 `git diff`、不得管線），改以 `--stat` 結果替代：diff 只有 `.claude/skills/local-run/SKILL.md`，沒有 `scripts/validate_agents.py`。第二道（grep `READONLY_AGENTS|READONLY_ALLOWED_BASH`）無法用管線執行，但新檔 Grep 零命中，且 diff 只動這一個 skill 檔，故判定未觸及；異動 agent 名單為空，常數值、成員、shadow 定義都沒有被改。

## 下一步
- devops-sre：可進入合併流程（P0，接線 PR 合併前）。合併後另開 PR，新增 `apps/stock-desk/docs/本機執行-工程參考.md`，搬移時必須保留第 7 項列出的防護規則（`backend/` 啟動目錄、單一 scheduler、N-191 腳本自我更新防護、備份／還原須停機），並依 tech-architect 更正 `STOCK_DESK_DB_PATH` 與主 DB 含預測紀錄帳的說明。檔頭送風控。
- coordinator：在追蹤清單記「local-run 轉介版 qa PASS_WITH_NOTES，單家審查，Codex 待環境可用時補跑」。NOTE-1、NOTE-2 可選擇不處理，也可在日後修改本 skill 時加一句「CEO 要啟動而產品沒開著時，只用追蹤清單中已定稿、提到 `dev-up.bat` 的句子」（只要不帶入給 CEO 的字面）。
- 本件不涉及 UI，不需 qa-e2e；也不必送風控（無對 CEO 的字面）。

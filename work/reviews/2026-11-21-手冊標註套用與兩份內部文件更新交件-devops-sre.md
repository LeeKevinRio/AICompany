# 主機部署手冊標註套用、內部安裝引導第 5 節補充、心跳責任確認書引用更新：交件

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- 第一件完成：新分支 `docs/host-manual-ceo-notice` 已 push，手冊只新增 30 行、換 1 行。
- 第二件完成：改字分支已補第 5 節並 push，兩處過時字也已修。
- 第三件未能就地修改：harness 拒絕對主工作目錄的檔案用 Edit（「Edit the worktree copy instead」）。我沒有用 Bash 繞過，改在 scratchpad 做出完整修改版，請 coordinator 核對後覆蓋。
  - 修改版：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/D-10心跳責任確認-devops-sre.md`
  - 目標檔：`/home/user/AICompany/work/reviews/2026-11-21-D-10心跳責任確認-devops-sre.md`，原檔未動，sha256 為 `1fad08cc…712a0d`。
  - 覆蓋用 `cp` 即可，修改版只有下列 7 處 Edit。

最終 head（`git ls-remote` 已確認）：
- `chore/dev-up-missing-tool-wording`：`3ee18ea8d1a141a0d7c996f0329ca7ce9740d5c2`（原 `f4f93a72c2c3caf4df2a2de683af9d52e84137a0`，一般 fast-forward push）。
- `docs/host-manual-ceo-notice`：`9a7bdef52dfe9c0b09f94f38d319500e82869470`。
  - 以 `git merge-base --is-ancestor` 確認包含改字分支最終 head。
  - 第一件的 commit 是 `9c4733cc243ae922b7a398bce484755968950054`。
  - 之後用 `git merge --no-ff` 合併改字分支，沒有 rebase 或 amend。

## 各部門回報（devops-sre）

### 第一件：手冊標註與九處警示

- 遠端 head 與指定值相同（`f4f93a72…`），分支由它開出。
- 用腳本 `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/apply.py` 從風控報告擷取字面套用。
- 套用前先斷言：
  - 標題完整字面與你列的相同，各恰好出現一次。
  - `### 0.2 ` 開頭的標題恰好一個。
  - 原第 3 行與報告的「原」相同。
- 兩個 CEO 警示標題（`### 0.2 ` 與 `### 0.3`）共用同一句 0.2、0.3 用警示。
- `git diff --numstat`：`30 1`。
  - 30 = 檔頭區塊 12 行（含最後的空行）＋ 9 處 × 2 行。
  - 1 = 第 3 行換字。
  - 沒有其他行變動。完整 diff 已在我的執行輸出裡逐段列出：檔頭、第 3 行新字面、九處警示依序在 0.2、0.3、1、2、3、4、4.4、5、7 之後。
- 逐字元證據：套用腳本直接取自報告的區塊，sha256 如下。
  - 檔頭區塊：`761525dd…a7202`。
  - 第 3 行新字面：`ba6528be…98669`。
  - 通用警示：`57c4cfb8f975…`。
  - 0.2、0.3 用警示：`50c8dd040ddd…`。
  - 備份用警示：`47e99f181ab5…`。
  - 從成品檔取出的警示行再算 sha256，結果是通用 ×5（`57c4cfb8f975`）、0.2、0.3 用 ×2（`50c8dd040ddd`）、備份用 ×2（`47e99f181ab5`），與腳本的前綴一致。
- 第 0.1 節（`### 0.1` 到 `### 0.2` 前）：基底與成品的 sha256 同為 `af728417092563c381962e2c51d65680176ba0cf1fe1bca17dcad7923b0729a9`。
- 換行：成品 CR 數為 0，全 LF，檔尾換行保留。
- 手冊引用檢查：Grep `主機部署手冊`、`族群動能-主機` 於 `apps/stock-desk/backend/tests`、`apps/stock-desk/backend/scripts`、`.github/`，都沒有命中，沒有測試或設定讀這份手冊。
- 沒有動 README。
- commit 標題：`docs: 主機部署手冊加上給 CEO 的標註與就地警示（RC-428、RC-429）`。

### 第二件：內部安裝引導文件第 5 節

檔案：`work/dispatch/2026-11-21-缺工具時的安裝引導-內部-devops-sre.md`，改字分支 `3ee18ea8…`，+40／-6。

- 第 5 節拆成 5.1（原三種 `[ERROR]`）、5.2（新增）、5.3（處理要求）。
- 5.2 新增的每一列都依你的要求，寫明前面已執行與尚未執行的步驟。對照 `dev-up.bat` 的行號如下（遠端 head `f4f93a7` 的版本，共 306 行）：

| 列 | `.bat` 行號 |
|---|---|
| `[ERROR] Cannot copy…` | 14 |
| `[ERROR] Not a git repo` | 63／64 |
| `[STOP]` | 72 |
| `[ERROR] git pull failed` | 114 |
| `[FAILED] Port 8000／3000 is still in use` | 270 |
| `[FAILED] Scheduler is still running` | 303 |
| 要求重新開機：`PID 4 is a Windows system process and cannot be stopped. Reboot and try again.` | 256 |
| `[TIMEOUT] Backend`（backend 健康檢查逾時） | 206（由 163 跳入 204） |
| `[TIMEOUT] Frontend` | 211（由 180 跳入 209） |
| `[FAIL]` 三行（backend、scheduler、frontend） | 189、191、193 |

- 重新開機那一句不以 `[` 開頭，容易漏掉，表中已註明。
- 5.2 沒有預先替任何一列歸類 B 或 D。前端逾時算不算 B，依風控報告留給 devops-sre 當日判斷。
- 5.3 新增第 7 點，對應風控的 R3-0、R3：
  - 只引用 RC-437、RC-438、RC-439、RC-340 條件編號與報告檔名，沒有抄訊息字面。
  - 涵蓋四項規則：
    - CEO 回報畫面行時，第一次回覆用 R3-0。
    - 是否請 CEO 再執行，依 RC-438 的四件事、須當天書面寫明才用 R3。
    - `[MISSING]` 照 RC-340，不用 R3-0。
    - 需要 CEO 安裝、更新或刪除任何東西時不得用 R3。
  - 另補兩項：同一次回報至多送一次 R3；`[FAIL]` 與 `Done.` 可能同時出現，不得以 `Done.` 當成功依據。
- 兩處過時字：
  - 第 6 節原「RC-341 不在本文件範圍，由 coordinator 另行處理」已改成反映現況（手冊第 0.1 節已依 RC-385 改寫；整體依 RC-427 改判為不是 CEO 的操作文件，另案處理）。
  - 表中 `git pull` 改為「已成功（112 行；有新 commit 時程式已更新）」。
  - 說明段裡「程式碼已經更新到最新」也順手改成同樣的限定，以免前後不一致。
- 沒有新增任何對 CEO 說的話。
- 補充說明：本地分支 `chore/dev-up-missing-tool-wording` 被另一個工作樹（`agent-a9629b70c09d9bd6a`）佔用，我無法 checkout。所以我在 detached HEAD 上 commit，再 `git push origin HEAD:chore/dev-up-missing-tool-wording`。遠端正確；那個工作樹的本地分支會落後一個 commit，需要它時先 `git pull`。

### 第三件：心跳責任確認書（只在修改版上改了 7 處，原檔未動、未 commit）

1. 檔頭加第三行修訂紀錄（2026-11-21 依風控 RC-437～RC-441 更新 (五) 的引用）。
2. 「依據」清單補風控報告與 tech-architect 避開時段確認兩個出處。
3. (五) 第 2 點 B 的括號句：
   - 不適用風控的 R2。
   - CEO 回報過畫面行、且我當天書面寫明 RC-438 (b) 四件事時，可用 R3。
   - 只從貼回看出、CEO 沒回報過畫面的 B 類，不得用 R2 或 R3，照原因未明處理（RC-439）。
4. (五) 第 4 點補 RC-440，列為 RC-412 (a) 的第四種情形：
   - 不得直接請 CEO 重新執行，不得問有沒有關掉視窗。
   - 只有 L2 回答「有開著」，且 tech-architect 書面判斷重新執行有助於排除仍可能的原因時，才可用 R2。
5. (五) 第 4 點新增 R3-0／R3 一則，並把避開時段改為「已確認照原句可用（出處：`work/reviews/2026-11-21-手冊八項事實與避開時段確認-tech-architect.md` 第三件；風控 RC-441）」。
6. 「中斷的執行」可能原因補一句：重新執行 `dev-up.bat` 遇到執行中的那一次，也會留下沒有 end 列的一筆，可由啟動補跑接手（tech-architect 建議）。
7. 第 6 節 3c 同步更新。

全程未抄任何對 CEO 的訊息字面。

## 驗證

- 第一件：numstat、diff、第 0.1 節 sha256、LF、警示逐字元核對（見上）。
- 第一件、第二件：`git ls-remote` 兩個分支的 head 與上面回報一致。
- 沒有執行 `.bat`，沒有讀 `.env` 或 `.env.example`，沒有碰 `backend/data/`。
- 沒有 push `product/stock-desk`，沒有 rebase、amend 或 force push。
- 檔案內容沒有模型名稱。commit 末尾的 Co-Authored-By 是依系統指示附加的 attribution，不是檔案內容。

## 下一步

1. coordinator：把 scratchpad 修改版覆蓋到主工作目錄原檔，用 `diff` 核對 7 處後自行 commit。
2. qa-reviewer 依 RC-430 核對第一件的 diff 範圍。
3. 兩個 PR 的合併順序：先合改字分支，再合 `docs/host-manual-ceo-notice`。後者目前已包含前者最終 head。
4. README 還原段仍等 tech-architect 補事實、creative-lead 起草、風控定稿，才加進 `docs/host-manual-ceo-notice` 這個 PR。

## 我沒有查證的事

- 沒有在 Windows 實機執行 `dev-up.bat`。5.2 的控制流程與行號是讀 `f4f93a7` 版本的 `.bat` 得出的。`choice`、`taskkill`、`netstat` 的實際行為未驗證。
- B 或 D 的界線，我只依風控報告與確認書引用的 tech-architect R4，沒有重讀 R4 原文。
- 沒有重新讀 tech-architect 的「避開時段確認」原文，只引用風控 RC-441 對它的轉述。
- 沒有實跑任何 CI、也沒有跑 `validate_agents.py`（只動文件）。兩個 PR 合併時是否衝突，我只確認 merge 無衝突，沒有跟 product 分支試合。

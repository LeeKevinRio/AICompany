# R0-2 盤點 git 事實（tech-architect 交辦 6 項）

- 作者：devops-sre
- 日期：2026-11-22
- 範圍：只讀。使用 git log／show／rev-parse／merge-base／branch -r --contains／tag -l／for-each-ref／grep，加 `git fetch origin`（只抓）。未寫 repo、未 commit、未 checkout、未讀 `.env*`、未碰 `backend/data/`、未執行 `.bat`。
- 通用定義與限制
  - 「commit 日期」一律是 committer date（`%ci`，本檔全部換成 UTC 顯示）。
  - 「第一次成為 origin/product/stock-desk first-parent 歷史上祖先的 first-parent commit」的算法：取 `git log origin/product/stock-desk --first-parent --reverse`（共 2143 個），對每個 SHA 在這條線上二分搜尋第一個 `git merge-base --is-ancestor <sha> <fp>` 為真者（祖先關係沿線單調，所以二分成立）。
  - 這是「進入 product 歷史的 commit 時間」，不是「CEO 本機實際 pull 到的時間」，也不是 push 時間。repo 內沒有 push 紀錄或 reflog 可查。

---

## 本次結論

1. `dev-up.bat` 的 `git pull` 自該檔建立的第一個 commit（`f790c3e`，2026-10-02 17:09:57 UTC）就有，2026-10-08 當時的 product 版本也有，所以 tech-architect 的疑慮（10-08 devops-sre 只核對到 `dev-up.sh`）在檔案事實上是「10-08 的 `.bat` 就會 pull」。
2. 22 個指名 commit 全部找到，且全部都是 product first-parent 線上的「直接」commit（本身就在線上，進入日期等於 commit 日期）。F-6／W-38 找到對應 commit，是經 merge 進入。
3. PR-2（(A) 降級句）、PR-3（6-b）、F-2（前端 keyLevels 收盤價 <= 0 守門，即 T-3）：任何遠端分支上都沒有程式 commit。字面只存在於 docs。
4. 主工作樹在 `product/stock-desk`，HEAD `6e6ac35`，等於 `origin/product/stock-desk`。`5a66a4c` 與 `7e54571` 兩種說法都是這條線上的祖先，只是不同時間點的 HEAD。
5. 唯一的 tag 是 `v0.1.0`，屬 flight-deals 產品，不是 stock-desk。沒有 stock-desk 的 release tag、沒有 release commit、沒有部署紀錄 commit。
6. E-9：W-6u 字面在程式裡第一次出現就是 `66a88b3`。

---

## 事實（逐項，附指令與輸出摘要）

### 1. `dev-up.bat` 的 `git pull`

指令：`git log --format='%h %H %ci %s' -S'git pull' -- apps/stock-desk/dev-up.bat`

輸出（只有兩筆）：
- `f790c3e8933556c9375321fb15289801c6f8df38` 2026-10-02 17:09:57 +0000，「feat: 新增 Windows 一鍵更新並啟動 stock-desk 前後端的 dev-up.bat」（檔案新增，count 從 0 變有）
- `a71b6c12c9a7a0b59fd98e400f43d058d16ae8ea` 2026-11-05 11:04:39 +0000，「fix: dev-up 腳本 git pull 更新自己後不再讀到新檔中段而出錯 (N-191)」（只是「git pull」字串次數變動，加了 self-update guard 註解，不是第一次出現）

「git pull」不是只有字串，實際指令行在各版本都存在：
- `f790c3e:apps/stock-desk/dev-up.bat` 第 74-75 行：`echo [1/4] 更新程式碼 git pull`、`git -C "%REPO_ROOT%" pull --ff-only origin %TARGET_BRANCH%`
- `890ed69`（2026-10-03 03:06 UTC，改純 ASCII）第 73-74 行同一指令
- `518b1e5`（2026-10-03 07:54 UTC，起 scheduler）第 74-75 行同一指令

2026-10-08 當時的 product 版本：
- 指令：`git log origin/product/stock-desk --first-parent --until='2026-10-08 23:59:59 +0800' -1` 得 `bda3f2e` 2026-10-08 15:58:49 UTC（以 10-07 結束算則為 `f25c90d` 2026-10-07 15:02:34 UTC）。
- `git show bda3f2e:apps/stock-desk/dev-up.bat` 第 74-75 行：`echo [1/4] Updating code (git pull)` 與 `git -C "%REPO_ROOT%" pull --ff-only origin %TARGET_BRANCH%`。**有**。
- 該版本沒有 N-191 的 self-update guard（grep `self-update` 無結果）；guard 在 2026-11-05 才加。
- `dev-up.bat` 全歷史共 5 個 commit：`f790c3e`（10-02）、`890ed69`（10-03）、`518b1e5`（10-03）、`1a12791`（10-26，讀 `.env`）、`a71b6c1`（11-05）。

### 2. 指名 commit 的日期與進入 product 的 first-parent commit

出處：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/bs.sh`（二分搜尋腳本，只呼叫 `git rev-parse`／`git log -1`／`git merge-base --is-ancestor`）。

「direct = yes」代表該 commit 本身就在 product first-parent 線上，進入日期等於其 commit 日期。

| 項目 | SHA | commit 日期 (UTC) | 進入 product 的 first-parent commit | 進入日期 | direct | first-parent 序號 |
|---|---|---|---|---|---|---|
| C-1 缺陷起點 | 06ea06b | 2026-07-25 05:34:32 | 06ea06b | 2026-07-25 05:34:32 | yes | 29 |
| C-1 缺陷起點 | 09a6833 | 2026-07-26 14:12:32 | 09a6833 | 2026-07-26 14:12:32 | yes | 38 |
| PR-0 | 9f5166e | 2026-10-08 01:23:43 | 9f5166e | 2026-10-08 01:23:43 | yes | 750 |
| PR-1 | be64f49 | 2026-10-08 01:24:47 | be64f49 | 2026-10-08 01:24:47 | yes | 751 |
| R-2-a | 171907e | 2026-10-07 14:07:45 | 171907e | 2026-10-07 14:07:45 | yes | 694 |
| F-1 | f25c90d | 2026-10-07 15:02:34 | f25c90d | 2026-10-07 15:02:34 | yes | 711 |
| ADR-0022 PR | 66a88b3 | 2026-10-07 19:52:30 | 66a88b3 | 2026-10-07 19:52:30 | yes | 729 |
| X-3b | 5124337 | 2026-10-08 02:35:27 | 5124337 | 2026-10-08 02:35:27 | yes | 764 |
| KX-10 | dd3f9da | 2026-10-08 02:35:28 | dd3f9da | 2026-10-08 02:35:28 | yes | 765 |
| PR-RK2 | cf9619e | 2026-10-08 08:20:58 | cf9619e | 2026-10-08 08:20:58 | yes | 785 |
| X-3c | 6a83097 | 2026-10-08 11:12:27 | 6a83097 | 2026-10-08 11:12:27 | yes | 814 |
| RK5a | 910344a | 2026-10-08 11:43:55 | 910344a | 2026-10-08 11:43:55 | yes | 817 |
| RK5c | f3e3508 | 2026-10-08 11:50:33 | f3e3508 | 2026-10-08 11:50:33 | yes | 819 |
| RK5b | 012850b | 2026-10-08 15:09:32 | 012850b | 2026-10-08 15:09:32 | yes | 837 |
| RK4a | a553e6c | 2026-10-08 12:33:52 | a553e6c | 2026-10-08 12:33:52 | yes | 823 |
| RK4b | 2fec1ac | 2026-10-08 13:52:04 | 2fec1ac | 2026-10-08 13:52:04 | yes | 829 |
| RK4c | 58359be | 2026-10-08 16:39:21 | 58359be | 2026-10-08 16:39:21 | yes | 847 |
| RK4c-R3 | 72e227e | 2026-10-08 15:54:57 | 72e227e | 2026-10-08 15:54:57 | yes | 840 |
| RK4c-R3 補 | d57c10b | 2026-10-08 15:58:49 | d57c10b | 2026-10-08 15:58:49 | yes | 841 |
| F-1b | 7fc90b2 | 2026-10-08 18:30:52 | 7fc90b2 | 2026-10-08 18:30:52 | yes | 860 |
| dev-up 起 scheduler | 518b1e5 | 2026-10-03 07:54:18 | 518b1e5 | 2026-10-03 07:54:18 | yes | 547 |
| dividend_sync | 4b47940 | 2026-10-04 15:05:14 | 4b47940 | 2026-10-04 15:05:14 | yes | 596 |

補充（第 1 項用到）：`f790c3e` 2026-10-02 17:09:57，direct，序號 534；`a71b6c1` 2026-11-05 11:04:39，經 `d2a2041` 2026-11-05 11:06:56「chore: 合併 N-191 dev-up 自我覆寫修正」進入（direct = no，序號 1650）。

F-6／W-38 對應 commit（指令：`git log --all --grep='F-6' --grep='F6' --grep='W-38'`，並對照 `docs: F-6 對照 F11-W-38 勾核` 等說明）：
- 修正本體：`666843a` 2026-10-13 12:39:23「fix: 首次向來源取得靜默失敗改以快取回覆時補上失敗揭露句」，經 `667f122` 2026-10-13 12:41:19「fix: 合併 F11-W-38 首次失敗回覆快取補上失敗揭露句」進入 product（direct = no，序號 950）。
- 補件測試：`a1c04fb` 14:00:19「test: F-6 補首次與冷卻期第二次 reason 字面相同的斷言」、`bb860ec` 14:00:19「docs: _fall_back_to_cache 註明唯一呼叫點與須先跑完 ladder」，經 `fd72e20` 2026-10-13 14:01:43「test: 合併 F-6 殘餘補件」進入（direct = no，序號 957）。
- 注意：F11-W-38 的 `667f122`（10-13 12:41）與 R0-2 當天（10-08）之間相差 5 天，所以 D-4 在 R0-2 簽核包寫成時尚未落地。

其他確認：
- `v0.1.0` 不是 product 祖先（見第 5 項）。
- 沒有「找不到的 SHA」：22 個指名 SHA 全部 `rev-parse` 成功且是 `origin/product/stock-desk` 的祖先。

### 3. PR-2、PR-3、F-2、T-3 有沒有 commit

指令與結果：
- `git log --all -F --grep='PR-2'`、`--grep='PR-3'`：零命中。
- `git log --all -F --grep='6-b'`：命中 6 筆，全是 10-07 的 docs commit（`c16eeee`、`3da33f5`、`331d42d`、`deeba07`、`8e8ccb5`）與 2026-08-22 `1b694f6`（無關的 C5 條件編號）。沒有 6-b 的 feat／fix commit。
- (A) 降級句字面 `-S'無法用風險上限確認加碼'`（全部 ref）：4 筆，`4106ba1`、`8951aea`、`d66183e`、`e533762`，都是 2026-10-07 的 docs commit（`e533762` 只改 4 個 `work/`／`docs/` 檔）。限定程式路徑（`apps/stock-desk/backend/app`、`apps/stock-desk/frontend`、`backend/tests`）再跑 `-S`：零命中。`git grep` 於 `origin/product/stock-desk`、`origin/feat/nm5-wiring`、`origin/feat/nm5-cg2-registration` 的 `backend/app` 與 `frontend`：零命中。
- W-b1 字面 `-S'若計入無法估值的部位'`：3 筆（`4106ba1`、`8951aea`、`e533762`），全為 docs；限定程式路徑：零命中。
- F-2：`--grep='F-2'` 有許多命中，但 2026-11-15 之後的都是**另一個 F-2**（預測紀錄帳「F-2 計數視窗」，ADR-0030 補充五，例如 `4144462`、`88faa91`、`2335e3c`），不是 R0-2 的 F-2（前端收盤價 <= 0 守門）。指向 R0-2 那個 F-2 的字面 grep 無命中；見 T-3 條。
- T-3：`--grep='T-3'` 命中的都是別的編號（ADR-0033 T-1～T-6、排程台 T-1～T-5 等），與 `computeKeyLevels` 無關。
- `apps/stock-desk/frontend/app/lib/keyLevels.ts` 全部 ref 的歷史只有 4 個 commit：`66a05bc`（2026-09-01 建立）、`b5ff74a`（10-17 18:25，改用最新收盤）、`0aef9f0`（10-17 18:48）、`9daee65`（10-17 19:12）。`git log --all -G'close\s*<=\s*0'` 對該檔：零命中。
- 逐一檢查全部 `refs/remotes/origin/*` 的 `keyLevels.ts`，含 `<= 0` 的只有一行，位於 `avgCost <= 0`（第 196 行，平均成本，不是收盤價）。`computeKeyLevels` 在 product 上第 99-106 行只擋 `!Number.isFinite`，沒有收盤價 <= 0 的守門。
- 遠端分支名中只有 `origin/test/f2-short-window-carryover`（ADR-0030 的 F-2，不是 R0-2 的 F-2）。沒有名為 PR-2、PR-3、6-b、T-3 的分支。

### 4. 主工作樹分支與 HEAD

- `git -C /home/user/AICompany rev-parse --abbrev-ref HEAD` -> `product/stock-desk`
- `git -C /home/user/AICompany rev-parse HEAD` -> `6e6ac35f54368bd73eeeb7e03bc3308f5dd2cabe`（2026-11-22 12:18:55 UTC，「docs: 存檔除權息揭露三句風控逐字定稿並記入追蹤清單」）
- `git rev-parse origin/product/stock-desk` -> `6e6ac35f54368bd73eeeb7e03bc3308f5dd2cabe`（執行 `git fetch origin` 之後）。`git status -sb` 顯示 `## product/stock-desk...origin/product/stock-desk`，沒有 ahead／behind。唯一未追蹤的是 tech-architect 那份審查檔（`??`），沒動。
- 兩種 HEAD 說法：`5a66a4c`（2026-11-22 11:56:06，序號 2134）與 `7e54571`（2026-11-21 18:22:46，序號 2132）都是 product first-parent 祖先，各是不同時間點的 product HEAD。現在的 HEAD 已更新為 `6e6ac35`（序號 2142，共 2143 個 first-parent commit）。所以「HEAD 到底是哪個」的答案取決於查詢時間，兩個都不是現在的 HEAD。
- 主工作樹確實就在 `product/stock-desk`。
- `origin/main` 與 `origin/product/stock-desk` 的 merge-base：`e1349aa89e50`。

### 5. tag、release、部署紀錄

- `git tag -l -n1`：只有 `v0.1.0`，註解「v0.1.0 — flight-deals 首次定版（FD-1～FD-11）」。
- `git rev-parse v0.1.0^{commit}` -> `6ae7570402d727798db9007626fbd4d981aca26f`（2026-11-01 13:08:32 +0800，「chore: flight-deals 穩定性與技術債收斂，首次定版 v0.1.0」）。`git branch -r --contains` 只有 `origin/product/flight-deals`。`git merge-base --is-ancestor v0.1.0 origin/product/stock-desk` 為否。所以這個 tag 與 stock-desk 無關。
- 沒有任何 stock-desk 的 tag。這與 10-07 `6b3fac5` 的「repo 無 tag 無法判定部署點」一致，且至今沒變。
- `git log --all -i --grep='release' --grep='deploy' --grep='部署'` 命中 60 筆以上，逐筆看 subject：全部是文件、字面、任務單、盤點腳本、手冊，或字句中帶 release／部署／staging（例如 `2445928`「R2 預備合併 N-177a（staging，未部署）」、`9c4733c`／`61c2c1c`「主機部署手冊」、`b3c5924`「N-207 部署前盤點腳本」）。沒有任何一筆是「發版」「部署完成」類的 release commit 或部署紀錄。`product/stock-desk` 祖先上含 release／發版／上線／發布 的 commit 共 57 筆，同樣都是以 docs 為主的字面說明，沒有 release commit。
- 與 D-8 對應：repo 內無法判定任何部署點。`dev-up.bat` 每次啟動執行 `git pull --ff-only`（第 1 項），所以 CEO 本機的版本等於「最後一次 dev-up 當下的 origin/product/stock-desk」，這在 repo 查不到。

### 6. E-9：W-6u 字面的 commit

- ADR-0022 第 8、9 行：W-6u 為 2026-10-07 風控逐字核可（替代案 W-6u-B，57 字）、列入 ADR-0022 PR 合併前提；任務單與 ADR 內有定稿字面。
- 程式內的字面是常數 `SECTOR_UNVALUED_UNKNOWN_OUTSIDE_COMPARISON_SUFFIX`（`app/advice/book_limits.py`，在 product 上第 168-181 行），內容「本條上限的比較未納入此標的；此標的沒有產業別資料，本次沒有任何產業納入比較，因此無法確認各產業的佔比是否超過上限。」，註解標「W-6u」。
- `git log --all --format='%h %ci %s' -S'W-6u' -- apps/stock-desk/backend/app apps/stock-desk/frontend`：只有 `66a88b3`（2026-10-07 19:52:30）。
- `git log --all -S'此標的沒有產業別資料，本次沒有任何產業納入比較' -- apps/stock-desk/backend/app`：只有 `66a88b3`。
- `git show 66a88b3:.../book_limits.py | grep -n W-6u` 第 168、177、620 行有命中。
- 所以：W-6u 字面進入程式的 commit 就是 `66a88b3`，在 product first-parent 線上（序號 729，2026-10-07 19:52:30 UTC）。
- 另外，W-6u 字面在 docs 的出現較早：`fdf56b5`（19:16 草稿）、`9220ad4`（19:20 風控核可）、`1265c28`（19:23 寫入 ADR-0022），都早於 `66a88b3`。
- 這 commit 同時改動 7 個檔，包含 `book.py`、`book_limits.py`、`limits.py`、`api/advice.py`、`tests/test_adr0022_sector_unvalued.py` 等。

---

## 推論（我的判斷，不是 git 直接輸出）

1. 第 1 項：既然 10-08 的 `.bat` 有 `git pull --ff-only`，R0-2（10-08）「部署」概念的前提（需 CEO 手動 pull）在 `.bat` 路徑上早已不成立；CEO 只要用 `dev-up.bat` 啟動，就會自動拿到 product 最新 commit。10-03 手冊叫 CEO 手動 pull 的說法已被 10-02 的 `.bat` 取代。這支持 tech-architect「D-8 部署已不是獨立事件」。但 CEO 實際用不用 `.bat`、用 `.sh` 或手動，repo 看不出來。
2. 第 2 項：D-4 的 F-6／W-38 修正在 10-13 才進 product，所以 R0-2（10-08）寫成時，那一條決定項確實尚未落地；歸類「已被取代」的時點是 10-13，不是更早。
3. 第 2 項：PR-0（9f5166e）與 PR-1（be64f49）只差 64 秒，X-3b 與 KX-10 只差 1 秒，同一批整理後依序 commit，進入時間幾乎同時。CEO 是在同一次 pull 一起拿到或分兩次，取決於他當時有沒有 pull，repo 不能判定。
4. 第 3 項：「PR-2、PR-3、F-2（R0-2 那個）、T-3 沒有程式 commit」成立於 2026-11-22 12:18 UTC 抓到的全部遠端分支。沒有證據顯示有人在本機（未 push）做過。
5. 第 4 項：風控兩種 HEAD 說法不矛盾，是不同時間的快照。

## 未查證

- CEO 本機實際跑的 HEAD、dev-up 啟動次數、有沒有手動 pull 或用 `.sh`：repo 內查不到。
- commit 日期是 committer date，不是 push 時間；遠端沒有 push 時間紀錄可查（未向 GitHub API 查）。
- 本機是否有未 push 的分支或 commit（未檢查本機 refs，只查了 `refs/remotes/origin`）。
- `git log --all` 只涵蓋本機已 fetch 的 refs；GitHub 上 PR 的 head ref（`refs/pull/*`）與已刪除分支不在內。
- 第 3 項的 PR-2／PR-3 是用「字面與編號」判斷，沒有逐一讀 diff 驗證語意；若 PR-2 有用別的措辭實作，可能漏掉。
- `release`／`部署` grep 的 60 多筆我是看 subject 判斷，沒有逐筆讀 diff。
- GitHub 上有無 release 物件（Releases 頁面）未查（需要網路 API，不在本次授權範圍）。

---

## 驗證（指令清單）

- `git fetch origin`（只抓）
- `git rev-parse --abbrev-ref HEAD`、`git rev-parse HEAD`、`git rev-parse origin/product/stock-desk`、`git status -sb`
- `git log -S'git pull' -- apps/stock-desk/dev-up.bat`、`git show <sha>:apps/stock-desk/dev-up.bat`（f790c3e、890ed69、518b1e5、bda3f2e、a71b6c1）
- `git log origin/product/stock-desk --first-parent --reverse` + `git merge-base --is-ancestor`（二分搜尋）
- `git log --all --grep`／`-S`／`-G`、`git grep`（refs 為 `origin/...`）、`git branch -r --contains`、`git for-each-ref`
- `git tag -l -n1`、`git cat-file -t v0.1.0`

## 下一步

- tech-architect：依第 1 至 6 項更新 R0-2 盤點分類（D-4 的取代時點 = 10-13；D-8 的「部署」前提 = `.bat` 自動 pull；E-9 = `66a88b3` 屬實；PR-2／PR-3／F-2／T-3 確認未落地）。
- coordinator：把本檔搬入 `work/reviews/`；轉風控與 tech-architect。
- 若要查 GitHub 上的 Releases 或 PR head ref，需要另行授權（網路 API）。

## 回滾方式

本次只讀，沒有改任何 repo 檔或設定，無需回滾。唯一的副作用是 `git fetch origin` 更新了 `refs/remotes/origin/*`，不影響工作樹、分支或 HEAD。

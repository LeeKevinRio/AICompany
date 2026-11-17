# CG-2 登記一鍵檔六題裁示與補充七附記三草案

- 審查者：tech-architect
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

六題的裁示如下。另有 3 項 blocking，要改完才能請 CEO 執行登記檔。

**Blocking（改完前 CEO 不得執行登記檔）**
- B-1　備份的一致性沒有機械保證。在沒有 `-wal` 時，備份來源連線用了 `immutable=1`，不取任何鎖。這時若有不佔 port 的行程寫入（scheduler 或其他），備份可能是不一致的半新半舊狀態，而 `integrity_check` 不一定抓得到。改法：連續取兩份備份，兩份的 sha256 必須相等。見 Q-2。
- B-2　`review_refs` 會永久寫進登記表，但沒有在執行時核對路徑是否存在。目前只有測試核對。見 Q-3。
- B-3　登記程式啟動後按 Ctrl+C，一鍵檔結束碼是 2，不是 5。程式 `main` 的 `except KeyboardInterrupt` 一律回 `code = 2`，跟「已寫入或不確定就是 5」的設計不一致。

**Q-1　R-1 的「CG-2 合併 commit」**
- 接受等價做法，不要求合併後再填 `CG2_MERGE_COMMIT` 常數、再審一輪。
- 條件是補三件事：
  1. 一鍵檔自己與兩個 `.bat` 加進「工作樹必須乾淨」的檢查範圍。
  2. 加 `git ls-files -v` 的標記檢查，並停用 fsmonitor。
  3. 合併後由 coordinator 做一次字面的 R-1 核對，在核對預檢回貼時做。

**Q-2　主 DB 的連線**
- 三個讀法都確認：
  - 「一鍵檔不開寫入連線」指不對主 DB 開寫入連線；寫入新備份檔的那條連線不在此限。
  - 補充六 (b) 那句只適用於驗收腳本。
  - R-4 與備份來源用 `mode=ro` 開主 DB，不衝突。
- 一致性的缺口依 B-1 修補。
- qa 第 3 點：
  - 鍵入 0／1 之後、啟動子行程之前，重驗一次 port 8000。
  - R-4 不必重驗，因為登記程式在交易內還會判一次。
  - 子行程啟動失敗不得說「可能已寫入」。改用 `Popen`，啟動成功後才設 `late`。

**Q-3　`review_refs` 的清單規則**
- 只放「對被登記內容作出核可或核對判定」的紀錄：事先宣告、C-8 紀錄檔、凍結包（含兩份 YAML）、M-9 的風控核對、M-9 的 qa 最終審查。
- 不放：
  - 工具與流程的審查（Q1Q2 確認、RC-179～184）；
  - 管線驗收的回貼；
  - 交件報告、TA 裁示、ADR。
- 一鍵檔執行時要逐一核對每個路徑在 `HEAD` 存在，否則 STOP（B-2）。

**Q-4　拒絕原因代號**
- 要加：一行封閉集合的代號，來源是 `claims.py` 的兩張拒絕句表。
- devops-sre 對「結束碼 0 但輸出不符」與「登記啟動後例外」的讀法，都與補充七第 5 點、附記二第 4 點一致。
- 腳本結束碼 0、1、2、3、5 與 ADR 不衝突。但 2 只能用在登記程式啟動之前（B-3）。

**Q-5　順序**
- 三項都接受：
  - 禁詞比對放在備份之前；
  - 新增的探針步驟；
  - `-I` 加 editable 安裝的前提。
- 執行前提要寫進操作說明：在這個 `HEAD` 跑過一次 `dev-up.bat`。
- 探針同時要放進預檢。

## 各部門回報（tech-architect）

**Q-1　R-1（併入 qa 第 1、2 點）**
- 依據：
  - 補充四第 5 點 R-1。
  - 補充四第 4 點 (2)：預檢回傳「經 coordinator 核對後」才執行登記檔。
  - 補充七附記二第 8 點：`--frozen-commit` 必須是 R-1 取得的 `HEAD`。
- 「沒有 diff」的語意只指 `app/` 與兩份文件，不擴大到 `pyproject.toml`、`uv.lock` 或 venv。理由：
  - 登記寫入的值是 commit、prereg sha256、definition 與規則的雜湊，都由 M-8 常數或 R-2 釘住。
  - 第三方套件或 lock 的差異，只會造成雜湊不符或 import 失敗，兩者都是 STOP，不會讓錯的值寫進去。
- 要做的修改：
  1. 「工作樹必須乾淨」的範圍加入 `apps/stock-desk/backend/scripts/cg2_register.py`、`apps/stock-desk/cg2-preflight.bat`、`apps/stock-desk/cg2-register.bat`。
  2. 每個 git 呼叫加 `-c core.fsmonitor=false -c core.untrackedCache=false`。
  3. 對 `app/`、兩份文件與上述三檔執行 `git ls-files -v -z`。任一列的標記不是大寫 `H`（例如小寫的 assume-unchanged 或 `S`），就 STOP `git_dirty`，沿用原句。
  4. 不釘 `code_digest` 常數。它在 Windows 上算出的值是否與 Linux 相同，目前沒查證，釘了可能在 CEO 本機誤判停止。
- 對應測試：上述三檔各有一個未 commit 變更的測試；`assume-unchanged` 與 `skip-worktree` 各一個 STOP 測試；`git_dirty` 句不變。
- coordinator 在核對預檢回貼時做四項（字面 R-1 由人工補齊）：
  - `git merge-base --is-ancestor <CG-2 合併 commit> <git_head>` 成立；
  - `git diff --quiet <合併 commit> <git_head> -- apps/stock-desk/backend/app <兩份文件>` 為空；
  - `script_sha256_lf` 等於 `git_head` 上的腳本 blob 經 LF 正規化後的 sha256；
  - `code_digest` 等於在 `git_head` 的乾淨 checkout 用 `canonical.code_digest` 算出的值。
- 登記回貼的 `git_head` 必須等於已核對的預檢 `git_head`。不相等時記為偏差，升級 TA。
- 不要求 `HEAD` 到達前置 PR 合併 commit `8b22c114`。tree id 已涵蓋 `app/` 的內容，到達關係在 PR 層級由 S-15 第 7 點核對。
- 比字面寬或窄：寬於字面的地方是合併 commit 的比對從機械移到人工；窄於字面的地方是加了 tree id、標記檢查與擴大的乾淨範圍。
- 合併前 coordinator 要核對：
  1. `B=$(git merge-base origin/product/stock-desk <PR head>)`，且 `git diff --quiet $B origin/product/stock-desk -- apps/stock-desk/backend/app` 為空，也就是 product 上的 `app/` 自分支最後一次 merge product 之後沒有變動。
  2. dev-lead 的補修交件有沒有改到 `app/`。devops-sre 回報那份補修不在分支上；有改就要重釘 tree id 再審。
  3. 合併後確認 `git rev-parse <M>:apps/stock-desk/backend/app` 等於 `9c157d86…00d7`。
  4. 用 merge commit 合併，不要 squash 或 rebase，讓第 1 項的推理成立。

**Q-2　備份與連線**
- 依據：
  - 補充四第 4 點：「一致備份」「一鍵檔不開寫入連線」。
  - 補充六附記第 2 點（RC-158b）。
  - 補充七附記二第 1 點。
  - RC-181②：備份在呼叫 `bootstrap` 之前完成。
- 三個讀法確認，不寬於字面。
- 一致性的缺口：
  - 主 DB 是 WAL 模式（`app/data/sqlite_util.py`）。沒有 `-wal`，只表示檢查當下沒有連線開著。
  - scheduler 每個工作都開關連線，而且不佔 port。若它在備份期間寫入並在關閉時 checkpoint，備份來源在 `immutable=1` 下不取鎖，可能讀到撕裂的頁面。
- 修法：
  - 備份 A 讀回檢查通過後，用同一規則重新判定 URI，取備份 B（檔名加 `-verify`）。
  - A 與 B 的 sha256 必須相等，否則 STOP `backup_failed`，沿用原句，不新增 CEO 字面。
  - 兩份都不刪除；回貼的 `backup_sha256` 是兩份相同的那個值。
  - 測試：有 `-wal` 與沒有 `-wal`，兩次備份各自相等；兩次之間注入一筆合成寫入時判 STOP。
  - 若測試證明 backup API 的輸出不具決定性，改比兩份各自的 `iterdump` sha256，並回報 TA。
- 替代方案（不採用）：備份來源一律不加 `immutable=1`。代價是主 DB 旁會產生 `-wal`／`-shm`，須重送風控。
- 鍵入等待期間（qa 第 3 點）：
  - 子行程啟動前重驗 port 8000，有監聽就 STOP `port_listening`，結束碼 3；畫面最後仍印 `backup_sha256`。
  - R-4 不重驗。交易內的判定才是準，RC-181① 已由先前的 R-4 滿足。
- `late` 的時點：
  - 改用 `subprocess.Popen` 加 `communicate(timeout=…)`，`Popen` 回傳之後才設 `late=True`。
  - `Popen` 拋 `OSError` 時是 STOP `claims_unreachable`，結束碼 3。
  - 逾時要 kill 子行程，並判 `written_unknown`。

**Q-3　`review_refs`**
- 依據：補充四第 3 點只規定格式。內容規則由本次裁示補上，CEO 可推翻。
- 最終清單：
  1. `work/reviews/2026-11-15-凍結包第2輪單項確認-風控.md`
  2. `work/reviews/2026-11-15-事先宣告v0.32套用單項確認-風控.md`
  3. `work/reviews/2026-11-15-C8決策紀錄檔確認-風控.md`
  4. M-9 的「風控核對 M-2、M-3、M-6」紀錄：若已存在就用原路徑；否則現在固定為 `work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md`。
  5. M-9 的 qa 最終審查：用 coordinator 剛轉來的 `work/reviews/2026-11-17-CG2登記一鍵檔審查-qa.md`。條件是它就是 B-1～B-3 改完後的最終 PASS；否則現在固定為 `work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md`。
- 檔名在進入最終 qa 前寫死在常數裡；實際紀錄必須落在那個路徑，結論必須是 PASS 或風控通過。
- 管線驗收的回貼不放：它是登記的前置條件，不是對登記內容的審查。改由第 4 點 (3) 的 `work/` 紀錄引用它。
- 程式要改兩處：
  - 執行期對每個路徑做 `git cat-file -e HEAD:<path>`，失敗就 STOP，新增 `review_refs_missing`（句子送風控）。
  - 加測試：路徑不含空白；格式符合 `repo_relative_path_ok`。

**Q-4　拒絕原因與結束碼**
- 依據：
  - 補充六第 4 點 (d)：失敗種類屬於執行狀態，可以回貼。
  - 補充四第 4 點：回傳內容不含路徑與代號。代號是固定的程式字，不是識別值。
- 新增一行 `refusal_reason=<key>`，接在 STOP 句之後。
- 值的集合：
  - 結束碼 4 用 `BOOTSTRAP_PATH_REFUSALS` 的 8 個鍵；
  - 結束碼 3 用 `BOOTSTRAP_REFUSALS` 的 10 個鍵；
  - 另加 `unrecognised`。
- 判定方式：子行程 stderr 去掉結尾換行後，必須與該結束碼對應表中的某一句完全相等；否則記為 `unrecognised`。stderr 的其他內容一律不轉出。
- 一鍵檔自己複製這份表，不 import `claims`；用測試核對與 `claims.py` 的兩個 dict 相等。
- 建議（屬 CEO 看得到的內容，送風控）：結束碼 3、4 時也寫回貼檔，內容是已知各行加上 `register_result=REFUSED` 與 `refusal_reason`。
- 結束碼 5 不加代號：只有一種句子，而且例外文字可能含路徑。
- devops-sre 的兩個讀法都確認：
  - 子行程結束碼 0 但 16 行不符，判 `WRITTEN_UNCHECKED`、結束碼 5；
  - 登記程式啟動後的例外與逾時也是 5。
- 中斷照 B-3 修：`late` 時結束碼 5。

**Q-5　順序**
- 依據：補充四第 4 點、RC-181②。
- 字面要求的「備份後禁詞比對」，實際由登記程式在備份之後再比對一次而成立，所以 R-6 放在預檢不放寬。
- 探針是新增的停止條件，窄於字面。
- 修改：
  - 預檢也執行探針，讓 coordinator 核對的預檢涵蓋它。
  - 子行程輸出的兩行 `banned_phrase_scan` 必須等於預檢那兩行（非 blocking，建議做）。
  - 操作說明的執行前提加一條：在本次 `HEAD` 執行過 `dev-up.bat`（`uv sync --locked`），並先 `git fetch`。
  - 不另做機械預檢，探針已涵蓋。

**Q-6　其他發現**
- B-1～B-3 同上，皆為 blocking。
- 非 blocking：
  - `head_published` 依賴本機的 `origin/product/stock-desk` 是否最新，操作說明要寫先 fetch。
  - 子行程結束碼 2（argparse 用法錯誤）判 5，方向保守，維持。

## 驗證
- 讀過：
  - ADR-0030 補充四～七及其所有附記；
  - devops-sre 交件報告；
  - `cg2_register.py` 全文；
  - `cg2-register.bat`；
  - `claims.py` 第 300～600 行；
  - `app/` 中 `sqlite3.connect` 與 `journal_mode` 的用法。
- B-3 的依據：`main` 的 `except KeyboardInterrupt` 一律 `code = 2`，不看 `state.late`。
- 沒有讀 qa 報告全文，以 coordinator 的摘要為準；沒有看 `.bat` 以外的 Windows 行為。
- 沒有執行 git（我沒有 Bash）。tree id `9c157d86…` 與 product 上 `app/` 沒有變動，都要由 coordinator 實際核對。
- Glob 查 dev-lead 補修檔時逾時，所以它是否改到 `app/` 仍待確認。
- backup API 對新建目的檔的輸出是否位元組一致，屬推論，以 B-1 的測試為準。

## 下一步
1. devops-sre 實作：B-1～B-3、Q-1 的三項、Q-2 的 port 重驗與 `Popen`、Q-3 的存在檢查、Q-4 的 `refusal_reason`、Q-5 的預檢探針。之後 qa 複審。
2. 風控審查字面：新增的 `review_refs_missing` 句、`refusal_reason` 行，以及（若採用）`register_result=REFUSED` 回貼。
3. coordinator 做 Q-1 合併前的四項核對；確認 dev-lead 補修的範圍；把附記三逐字 append 到 ADR-0030。

---附記全文（逐字 append）---

## 補充七附記三：CG-2 登記一鍵檔的 R-1 等價核對、備份一致性、review_refs 與拒絕原因（2026-11-17）

- 決策者：tech-architect。來源：`work/reviews/2026-11-17-CG2登記PR第三段一鍵檔交件-devops-sre.md`、`work/reviews/2026-11-17-CG2登記一鍵檔審查-qa.md`；另讀 `feat/nm5-cg2-registration`（`3a3fccbf`）的 `scripts/cg2_register.py`、`cg2-register.bat`、`app/forecast/claims.py`。
- 性質：釐清補充四第 3、4、5 點的讀法，並收緊一鍵檔。第 1 點把 R-1 的合併 commit 比對從機械改為人工核對，窄幅寬於字面，已標明。第 3 點補上 `review_refs` 的內容規則。不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/`。新增的 CEO 可見字面送風控。CEO 可推翻。

1. **R-1（窄幅寬於字面）**：「沒有 diff」只指 `app/` 與兩份文件。一鍵檔以下列各項代替與 CG-2 合併 commit 的機械比對：
   - `HEAD` 可由 `origin/product/stock-desk` 到達；
   - `git rev-parse HEAD:apps/stock-desk/backend/app` 等於 CG-2 PR 的 `app/` tree id 常數；
   - `app/`、兩份文件、一鍵檔與兩個 `.bat` 的工作樹乾淨；
   - 這些路徑的 `git ls-files -v` 標記都是大寫 `H`；
   - git 呼叫停用 `core.fsmonitor` 與 `core.untrackedCache`。

   字面的 R-1 由 coordinator 在核對預檢回貼時完成：合併 commit 是 `git_head` 的祖先；兩者之間 `app/` 與兩份文件的 diff 為空；`script_sha256_lf` 與 `code_digest` 等於在 `git_head` 重算的值。登記回貼的 `git_head` 必須等於已核對的預檢 `git_head`，不相等時升級 tech-architect。`uv.lock`、`pyproject.toml` 與 venv 不釘，因為它們的差異只會造成 M-8 雜湊不符或 import 失敗，兩者都是 STOP。
2. **連線與備份**：補充四第 4 點的「一鍵檔不開寫入連線」讀為不對主 DB 開寫入連線；寫入新備份檔的連線不在此限。補充六第 1 點 (b) 末句只適用於驗收腳本（RC-158b）；R-4 與備份來源的 `mode=ro` 連線不衝突。為保證「一致備份」：
   - 讀回檢查通過後，依同一 URI 規則再取第二份備份，兩份 sha256 必須相等，否則 STOP；兩份都不刪除。
   - 鍵入 0／1 之後、啟動子行程之前，重驗 port 8000。
   - 子行程以 `Popen` 啟動成功後，才進入「可能已寫入」狀態；啟動失敗屬於未寫入的 STOP。
3. **`review_refs`**：只列對被登記內容（事先宣告、C-8 紀錄檔、凍結包與規則檔、definition）作出核可或核對判定的紀錄，即風控對三者的確認，以及 M-9 的風控核對與 qa 最終審查。不列工具或流程的審查、管線驗收回貼、交件報告與裁示；管線驗收回貼由第 4 點 (3) 的 `work/` 紀錄引用。路徑在進入最終 qa 前以常數固定，不含空白。一鍵檔執行時逐一確認路徑在 `HEAD` 存在，否則 STOP。
4. **拒絕原因**：子行程結束碼 3、4 時，一鍵檔加印一行 `refusal_reason=<key>`。key 取自 `claims.py` 兩張拒絕句表的鍵，判定方式是 stderr 與該結束碼對應表中的某一句完全相等；否則為 `unrecognised`。stderr 的其他內容一律不轉出。結束碼 5 不加。
5. **結束碼**：
   - 一鍵檔結束碼 0、1、2、3、5；2 只用於登記程式啟動之前的中斷。
   - 登記程式啟動之後的任何例外、中斷、逾時，以及結束碼 0 但輸出的形狀、順序或值與本次 `HEAD`、M-8 常數、鍵入值不符，一律結束碼 5，並寫 `register_result=WRITTEN_UNCHECKED` 的回貼。
6. **順序**：R-6 放在「重跑全部預檢」中，在備份之前；登記程式在備份之後再比對一次，所以補充四第 4 點的順序成立。探針子行程（不符就 STOP，不備份）屬於收緊，預檢也要執行。執行前提：在本次 `HEAD` 執行過 `dev-up.bat`，並已 `git fetch`。

- **S-15c（逐條可檢查）**：
  - 第 1 點：三個新增監看檔各有一個未 commit 變更的 STOP 測試；`assume-unchanged`、`skip-worktree` 各有一個 STOP 測試。
  - 第 2 點：兩份備份不相等時 STOP（注入寫入）；有、無 `-wal` 各一個相等的測試；鍵入後 port 有監聽時 STOP，且不呼叫子行程；`Popen` 拋 `OSError` 時結束碼 3。
  - 第 3 點：路徑不存在時 STOP，且不呼叫子行程；不含空白的測試。
  - 第 4 點：與 `claims.py` 兩張表相等的測試；每個 key 與 `unrecognised` 各一個測試。
  - 第 5 點：登記中注入 `KeyboardInterrupt` 時結束碼 5。
  - 第 6 點：預檢執行探針的測試。

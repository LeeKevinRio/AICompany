# 接線 PR 四題裁示與補充九定稿

- 審查者：tech-architect
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **Q-1**：自訂方案，接近 (d) 但不讓 PR 帶紅燈合併。另開一支只做退役的 PR，把一鍵檔、兩個 `.bat` 和只測它們的測試一次刪掉。這支 PR 在 coordinator 的登記紀錄 commit 之後才合併。接線 PR 要先 merge 進它，才合併。在那之前，接線分支上 R-1 的失敗照實保留，不 skip、不只刪單一測試、不重釘常數。退役需要 ADR 依據（補充九第 1 點）。日後稽核靠 git 歷史，不需要這些檔留在 HEAD。
- **Q-2**：不要。不加 CI 測試，由 qa 人工核對值的出處（補充九第 6 點）。
- **Q-3**：要。只在 scheduler 加目標限定，recorder 不加（補充九第 3 點，屬收緊，吸收 I-1、I-3）。
- **Q-4**：要。在 `store.py` 導出判定，列為 CG-4 阻擋項，判定的精確定義寫在補充九第 5 點。風控的 (a)～(f) 六個條件都與 ADR 相容。
- **風控第 1 點（分母為 0）**：我改判法。完整視窗分母為 0 時，不論分子大小，此視窗 F-2 都成立（補充九第 4 點，收緊）。RC-238「分母 0」那一行要重送風控。
- **I-1～I-9**：I-7 不同意，改依補充九第 4 點。其餘同意；其中 I-1、I-3 由補充九第 3 點取代並擴充。I-4、I-5、I-6、I-8 要寫進 ADR 才算數（補充九第 7 點）。
- **`ledger_store`** 符合 K-3 與 K-10。**job 設定**與 D-3 第 7 點逐項一致。啟動後 3 分鐘補跑本來就寫在 D-3 第 7 點，也寫在事先宣告 v0.32 第 1020、1032 行，不需要補進 ADR。但它帶出一個本文內部的張力（見「各題裁示」末段），需 CEO 決定，不擋這次合併。
- **qa N-3**：不需要規格層面的要求。

## 各題裁示

**Q-1 一鍵檔退役**
- 退役 PR 刪除這些檔案：
  - `scripts/cg2_register.py`、`scripts/verify_cg2_instruction.py`
  - `apps/stock-desk/cg2-preflight.bat`、`cg2-register.bat`
  - `tests/test_cg2_register_values.py`、`test_cg2_register_flow.py`、`test_cg2_register_addendum3.py`、`cg2_register_world.py`、`cg2_register_loader.py`
- 保留 `tests/test_cg2_registration_values.py`，不得改動。M-2、M-3 的 HEAD blob 雜湊與 M-4～M-6 都由它釘住，刪掉其他檔不會少掉對已登記值的保護。
- 為什麼不選 (a)～(c)：
  - (b) 留下工具卻刪掉它的守門測試，就是在拿掉測試換綠燈。
  - (c) 是公司守則明文禁止的做法。
  - (a) 把退役混進接線 PR，一個 PR 兩個語意，W-7 的零差異證明也要跟著改寫。
- 我的方案為什麼不違反「不得換綠燈」：綠燈來自把測試對象本身移除，而且移除有 ADR 依據；接線分支在那之前維持紅燈，不合併。
- 為什麼需要 ADR：補充四的 S-14a 規定「R-1～R-8 各有對應的 STOP 訊息測試」，補充七附記三的 S-15c、附記三之一的 S-15d 也列了這組測試。字面上沒有期限，刪掉就與字面衝突。另外 `.bat` 是 CEO 看得到的東西，依 #139 不能由實作者自行決定。所以補充九第 1 點限定這些測試存續到退役為止，並標明是窄幅放寬。
- 誤再執行的風險：
  - 登記後、接線 PR 合併前，`app/` 沒變，R-1 會通過。但 R-4（已有 `forecast_` 物件）在備份與 bootstrap 之前就會 STOP；就算漏過，bootstrap 交易內的 `SchemaNotEmptyError` 也會以結束碼 4 拒絕。不會寫入。
  - 接線 PR 合併後，R-1 的 tree id 必然不符，直接 STOP。
  - 真正的殘餘風險是主 DB 被還原成沒有帳本 schema 的狀態（例如還原 CG-3 備份）之後再 bootstrap。這條路徑不只一鍵檔有，`claims bootstrap --production` 也能走。所以補充九第 2 點規定：這種重跑視同 D-1 第 2 點的「登記新 claim」，須先修訂 ADR。退役 PR 則把 CEO 能雙擊的那條捷徑拿掉。
- 稽核：登記回貼的 `git_head` 等於 `frozen_commit`，R-1 保證它可由 `origin/product/stock-desk` 到達。所以一鍵檔與測試都能用 `git show <frozen_commit>:<path>` 取回，git 歷史足夠。條件是 `product/stock-desk` 不得改寫歷史；`work/` 裡的登記紀錄、回貼與 CEO 操作說明不刪、不改。

**Q-2 不加 CI 測試，理由三點**
1. CI 只能驗格式，驗不了值的真偽。sha256 對不對，要拿登記紀錄（補充四第 4 點 (3)）和登記回貼的 `backup_sha256` 比對，這只能由 qa 人工做。
2. 防止提早合併的機械閘門已經有了：退役 PR 合併之前，接線分支的 R-1 必然紅燈。
3. 一份一次性紀錄的測試會永久留在產品線，日後又要退役一次，等於重演 Q-1。

另外，ADR 只要求記路徑與 sha256（CG-3、補充四第 4 點 (4)）。P-2 五行格式中，登記回貼沒有提供出處的值（例如第二份備份的 sha256，我沒有確認回貼裡有沒有），必須照實標「無出處」，不得推得或補填。

**Q-3 要限定**
- 理由：補充四第 2 點規定帳本只能在 `<backend>/data/stock-desk.db` 以 bootstrap 建立。寫入端應該對稱。
- 不限定時有個實際風險：把 `STOCK_DESK_DB_PATH` 指向一份含帳本的主 DB 複本（例如日後的定期備份，或搬到 docker 時複製的檔），scheduler 就會往那份複本寫入。結果是兩本帳分叉，而且 claim_id 相同。這正是 D-8 第 3 點與 F-8 所說的「DB 路徑改變」。
- 限定之後，換位置記錄就必須先修訂 ADR。
- 核對放在 scheduler，不放在 recorder：harness 要用暫存 DB 呼叫同一個 recorder，K-11 不受影響。
- 不讀 `.env`：`resolve_db_path` 只看程序環境變數。

**Q-4 要加，精確定義（補充九第 5 點）**
- 格點用 `phase0_grid`，與 n̂ 同一個函式。
- 分母 G：格點 P 中 `late_cutoff_at(P) ≤ now` 的個數。
- 分子 L：這些格點中，該 claim 沒有 `late = 0` 紀錄的個數。
- 判定：G = 0（含沒有 D_v）時為「無從判定」；否則 L × 5 > G 才成立。恰好 20% 不成立。
- 曾否成立：對每個前綴 j 判 L_j × 5 > j，任一成立就算，不撤銷。
- 自 D_v 起累計，不設視窗，也不設最低格點數。
- 為什麼要「曾否成立」：升級義務是事件性的，報告本身沒有狀態。沒有這一欄，CEO 能不能看到升級訊號，取決於他剛好在什麼時候執行報告。
- 代價：初期只要漏一個格點（例如第 2 個格點遺失，1 × 5 > 2）就會永久顯示「曾成立」。這是字面的直接後果，因為 ADR 沒有設最低格點數。
- 與已定內容的對照：
  - 補充五第 1 點明說第二句「自 D_v 起累計，不受本點影響」，這個定義正是自 D_v 起累計，沒有衝突。
  - 補充八第 2 點 (d)、(f)：格點錯相、與驗證層重算的差異，已由第一行加註「F-2 計數與格點數值可能…不同」涵蓋。新的判定行排在它之前，仍在涵蓋範圍內。請風控在定稿時一併確認這一點。
  - 補充八第 6 點 (b) 只限制兩行加註的內容與位置，不禁止新增執行狀態行。
- 風控條件逐項：(a)、(e)、(f) 相容；(b) 相容，判定在 store 以整數比較；(c) 相容，而且我把「D_v 已有、但其截止時點還沒過」也併入 G = 0 的「無從判定」；(d) 相容，這一行在執行狀態段，所以也會進 harness 完整輸出，補充五第 5 點允許。

**風控第 1 點：分母為 0**
- 現行程式的判法符合補充五第 1 點 (e) 的字面（0 > 0 不成立），(h) 也把整段停機列為已知盲點。所以它不違反 ADR，但會把異常呈現成正常。
- 20 個平日內一個定案 session 都沒有，休市不可能造成（最長的連假也不到 20 個平日），只會是三種情形：整段停機、來源整段缺席、或執行一直沒有存下快照。
- 停機一恢復，下一份快照就會補上那段 session，F-2 之後也必然成立。所以把 0/0 判為成立，只是讓結果提早出現，不改變最終結論。
- 屬收緊，寫在補充九第 4 點。只適用完整視窗，(f) 視窗未滿不變。

**I-1～I-9**
- I-1：同意，由補充九第 3 點擴充為「必須等於預設目標」。
- I-2：同意。
- I-3：同意，併入補充九第 3 點 (b)。它符合補充四第 2 點「遇到 schema 不存在時拒絕寫入，不建表」，而且更保守，因為連空檔都不會建立。
- I-4：同意，須寫進 ADR（補充九第 7 點 (d)）。
- I-5：同意，須寫進 ADR（第 7 點 (a)）。小更正：含 S_c 當日應該說「不寬於」不含的讀法，不是「更嚴」。
- I-6：同意，須寫進 ADR（第 7 點 (b)）。依據是補充五第 1 點 (b)：沒有任何 `forecast_run` 時 S_c 無法定義。
- I-7：不同意，改依補充九第 4 點。分子大於 0、分母為 0 的情形照舊判成立。
- I-8：同意，符合 D-8 第 4 點的字面「每個前瞻 claim 各自判定」，須寫進 ADR（第 7 點 (c)）。已知差異：`report status` 只列記錄中 claim。核心期間兩者相同；日後取代 claim 時要一併定列示範圍。
- I-9：同意，log 只有執行計數，不含標籤（D-4 第 3 點）。

**另外檢查的兩件事**
- `ledger_store(db_path)` 沒有 T、`as_of`、時鐘參數，符合 K-10。scheduler 只 import `app.forecast.recorder`，符合 K-3。它不開連線；schema 核對在 store 的每次寫入。
- job 設定：平日 22:10、23:10 重試、啟動後 3 分鐘補跑、`Asia/Taipei`、`max_instances=1`、`coalesce=True`，與 D-3 第 7 點逐項相符；沒有加 18:10 也正確。

**需 CEO 決定的一項：啟動補跑的時段（不擋接線 PR）**
- 問題：D-3 第 7 點規定，18:10 那一次要等 data-engineer 確認「Yahoo 在 18:00 之前已是最終收盤」才能加。但同一點的啟動補跑沒有時段限制。依 D-3 第 2 點，15:00 之後取得的 bar 就算定案，所以如果 CEO 在平日 15:00～18:00 之間啟動，補跑會用可能還不是最終值的收盤寫下 T 的 `late = 0` 紀錄。帳是 append-only，加上 UNIQUE，這筆寫下就不能改。
- 為什麼不是我能定：啟動補跑同時寫在本文 D-3 第 7 點和已凍結的事先宣告 v0.32「發布」列。要限制它，須修訂本文，經風控與 CEO，不能用補充處理。
- 建議：先請 data-engineer 回答 ADR 待決事項裡那一題（15:00～18:00 的收盤是否已定案）。答案是「可能未定案」時，再由我起草本文修訂。

**qa N-3**：`report` 只用於顯示、不寫入，而且查詢順序是 runs → sessions → on_time，併發寫入不會讓遺失數偏高。不需要規格要求；要合成同一個 `_read` 可以，非必要。

## 可逐字寫入的 ADR 文字

**寫入時點限制**
- 排在補充八之後。補充八還沒 append，所以兩者依序寫入。
- 第 1 點必須在退役 PR 合併之前已在 ADR 中；第 3～5 點必須在接線 PR 合併之前已在 ADR 中。
- 從 CEO 預檢回貼到登記完成之間，不得 push `product/stock-desk`（補充七附記三第 2 點）。
- 建議與補充八一起，在 CG-2 PR 合併後、預檢之前 append；來不及就在登記完成之後。
- 來源中的 qa 報告與 RC-237～RC-243 報告，須在同一個或更早的 commit 進入 `work/reviews/`。

**檔頭補充紀錄行**（加在補充八那一行之後）：

- 補充紀錄：2026-11-19 append 補充九（CG-2 一鍵檔退役、正式登記後的 bootstrap、scheduler 的正式目標、F-2 第一句分母為 0、F-2 第二句的判定、CG-3 紀錄、接線解讀確認；tech-architect 裁示；第 1 點窄幅寬於 S-14a、S-15c、S-15d 字面，第 2～5 點為收緊，第 6、7 點為釐清；不改本文、`N_HAT_NOTE`、規則檔、定義物件、事先宣告與已登記雜湊；第 4、5 點的字面由風控定稿；CEO 可推翻；來源 `work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md`、`work/reviews/2026-11-19-接線PR預先實作交件-dev-lead.md`、`work/reviews/2026-11-19-接線PR審查-qa.md`、`work/reviews/2026-11-19-接線PR-F2視窗字面判定RC237至RC243-風控.md`）

**補充九全文**：

## 補充九：CG-2 一鍵檔退役、scheduler 的正式目標、F-2 分母為 0 與第二句的判定（2026-11-19）

- 決策者：tech-architect。來源：`work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md`（Q-1～Q-4、I-1～I-9）、`work/reviews/2026-11-19-接線PR預先實作交件-dev-lead.md`、`work/reviews/2026-11-19-接線PR審查-qa.md`、`work/reviews/2026-11-19-接線PR-F2視窗字面判定RC237至RC243-風控.md`。另讀 `feat/nm5-wiring`（`d01bd9ee`）的 `app/scheduler.py`、`app/forecast/recorder.py`、`store.py`、`report.py`、`scripts/cg2_register.py`、`tests/test_cg2_register_values.py`。
- 性質：
  - 第 1 點限定補充四 S-14a、補充七附記三 S-15c 與附記三之一 S-15d 所列一鍵檔測試的存續期間，窄幅寬於字面，已標明。
  - 第 2～5 點為收緊；第 6、7 點為釐清。
  - 不改本文、`N_HAT_NOTE`、規則檔、定義物件、事先宣告 v0.32 與已登記雜湊。
  - 第 3～5 點影響寫入條件或 CEO 可見內容；第 4、5 點的使用者面字面由風控定稿。CEO 可推翻。

1. **CG-2 登記一鍵檔的退役**（窄幅寬於 S-14a、S-15c、S-15d 字面）
   - 退役對象：`scripts/cg2_register.py`、`scripts/verify_cg2_instruction.py`、`apps/stock-desk/cg2-preflight.bat`、`apps/stock-desk/cg2-register.bat`，以及只測它們的 `tests/test_cg2_register_values.py`、`tests/test_cg2_register_flow.py`、`tests/test_cg2_register_addendum3.py`、`tests/cg2_register_world.py`、`tests/cg2_register_loader.py`。
   - 不退役：`tests/test_cg2_registration_values.py`。它釘住已登記的值，不是一鍵檔，保留且不得改動。
   - 方式：以獨立 PR 一次刪除，不改 `app/`。不得以 skip、xfail、只刪單一測試或重釘常數代替。
   - 時點：
     - 退役 PR 在補充四第 4 點 (3) 的登記紀錄 commit 之後才合併。
     - 接線 PR 在退役 PR 合併之後，先 merge 進來，再合併。
     - 在此之前，接線分支上 R-1 tree id 測試的失敗照實保留，接線 PR 不因此合併。
   - S-14a 的「R-1～R-8 各有對應的 STOP 訊息測試」、S-15c 與 S-15d，存續到退役 PR 合併為止。放寬處：之後 HEAD 不含這些測試。理由：測試對象同時移除，登記只做一次。
   - 稽核依據是 git 歷史：
     - 登記回貼的 `git_head` 等於 `frozen_commit`，可由 `origin/product/stock-desk` 到達；退役的檔案以 `git show <frozen_commit>:<path>` 取得。
     - `product/stock-desk` 不得改寫歷史。
     - `work/` 中的登記紀錄、回貼與 CEO 操作說明不刪、不改。
2. **正式登記之後的 bootstrap**（收緊）
   - 補充四第 4 點 (3) 的登記紀錄 commit 之後，對正式主 DB 再執行 `bootstrap --production`，視同 D-1 第 2 點的「登記新的前瞻 claim」：須先修訂本 ADR 並經風控審查，並依 D-8 第 3 點在 `work/` 記錄。
   - 主 DB 整檔還原到沒有帳本 schema 的狀態之後（例如還原 CG-3 備份），同樣適用。
   - claims.py 的程式行為不變。
3. **scheduler 的正式目標**（收緊）
   - job `forecast_record` 每次執行，都在建立 store 之前依序核對下列兩項。任一不成立，就不呼叫 recorder，記一行固定英文字面的 WARNING（不含路徑），正常返回：
     - (a) 程序環境變數中沒有 `STOCK_DESK_DB_PATH`；設為空字串也算有設。
     - (b) `<backend>` 由模組位置導出，不取自工作目錄；`resolve_db_path()` 以 `Path.resolve(strict=True)` 解析成功，等於 `<backend>/data/stock-desk.db`，且為一般檔案。
   - 不讀 `apps/stock-desk/.env`。核對不開任何 SQLite 連線，也不建立任何檔案。
   - schema 不存在時，仍依補充四第 2 點由 store 拒絕寫入。
   - 這項核對只在 scheduler；recorder 與 `ledger_store` 不檢查目標，K-11 不變。
   - 設了 `STOCK_DESK_DB_PATH` 的部署（含 docker compose）不記錄。要在其他位置記錄，屬 D-8 第 3 點與 F-8 的 DB 路徑改變，須先修訂本 ADR。
4. **F-2 第一句的分母為 0**（收緊補充五第 1 點 (e)）
   - 完整視窗的分母為 0，即視窗日曆範圍內沒有任何定案 session 時，不論分子，此視窗 F-2 成立。
   - 理由：休市不可能讓 20 個平日內沒有任何交易日。這種情形只出現在整段停機、來源整段缺席，或執行一直沒有存下快照。依 (e) 字面，分子為 0 時判不成立，會把 (h) 的盲點呈現成正常。
   - 本點只適用完整視窗。(f) 不變；(h) 的其餘盲點照舊由心跳負責。
   - 字面由風控重新定稿。
5. **F-2 第二句：第 0 相位格點遺失率的判定**（收緊）
   - 格點：`store.phase0_grid` 的格點，與 n̂ 同一個函式（補充八第 2 點 (f)）。
   - 計入的格點：`late_cutoff_at(P) ≤ now` 的格點 P，依日期排序，個數為 G。`now` 是 `report` 的時鐘。
   - 遺失：計入的格點中，該 claim 沒有 `late = 0` 紀錄的個數，為 L。
   - 判定：
     - G = 0（含沒有 D_v）時為「無從判定」，不得判為未成立。
     - 否則 L × 5 > G 時成立，以整數比較；恰為 20% 不成立。
   - 曾否成立：
     - 對計入格點的每個前綴 j = 1…G，以前綴內的遺失數 L_j 判定 L_j × 5 > j；任一成立即「曾成立」，不撤銷。
     - 一律依目前的格點重算；格點錯相時（補充八第 2 點 (d)），照重算結果顯示。
   - 自 D_v 起累計，不設視窗，也不設最低格點數。
   - 導出：只在 `store.py` 的唯讀查詢；`report.py` 只做格式化。
   - 輸出：
     - 在 `report status` 的執行狀態段依 claim 分列 G、L、判定與曾否成立。
     - 不印百分比；排在 `GAP_DISCLOSURE` 之前；不與任何標籤或對照並列。
     - 屬 D-4 第 5 點的執行狀態，可以出現在 harness 的完整輸出（補充五第 5 點）。
     - 字面由風控定稿。
   - 成立時，依 F-2 第二句升級 CEO 與 devops-sre；coordinator 以 commit 在 `work/` 記錄第一次看到成立的日期。
   - 期限：在接線 PR 落地，列為 CG-4 的阻擋項。
6. **CG-3 紀錄**（釐清）
   - 不加 CI 測試。
   - qa 在接線 PR 合併時核對：備份 sha256 等於補充四第 4 點 (3) 登記紀錄中的值，也等於登記回貼的 `backup_sha256`；路徑用家目錄相對寫法。
   - 只填有出處的值；沒有出處的項目照實標「無出處」，不得推得或補填。
7. **解讀確認**（釐清）
   - (a) 補充五第 1 點 (c) 的「S_c 以後」含 S_c 當日（S_c 為平日時）。
   - (b) 沒有任何 `forecast_run` 時沒有 S_c，不評估：輸出「視窗未滿（尚無執行）」，兩項分子為 0。
   - (c) D-8 第 4 點的 WARNING：
     - 對全部前瞻 claim 判定，含已被取代者。
     - 在任何 outcome 的 end 列寫入之後判定；end 列寫入失敗時不判定。
     - `report status` 只列記錄中 claim。日後依 D-1 第 2 點取代 claim 時，須一併定列示範圍。
   - (d) D-3 第 7 點的 job 不另設 `misfire_grace_time`，沿用 APScheduler 的預設值。錯過的時點由 23:10 重試與啟動補跑涵蓋；啟動補跑不限平日。
   - (e) scheduler 經 `recorder.ledger_store(db_path)` 取得 store（K-3）。該函式沒有時間或時鐘參數，納入 K-10 的簽章測試。

- **S-19a（逐條可檢查）**
  - 第 1 點：
    - 退役 PR 的 diff 只有刪除，`app/` 零差異。
    - `tests/test_cg2_registration_values.py` 零差異。
    - 在 `apps/stock-desk`（`work/` 除外）以 grep 查不到 `cg2_register`、`cg2-register`、`cg2-preflight`、`verify_cg2_instruction`。
    - 有一個測試斷言這四個檔案不存在。
    - PR 說明附上登記紀錄 commit，qa 核對它早於退役 PR 的合併 commit。
  - 第 3 點（測試）：
    - 設了環境變數（含空字串）、目標不同、檔案不存在、目標是目錄，四種情形都不呼叫 recorder，記固定字面，不建立任何檔案。
    - 正常目標時呼叫 recorder。
    - AST 確認 scheduler 不讀 `.env`。
  - 第 4 點（測試）：
    - 完整視窗分母 0、分子 0，判成立，曾否成立為是。
    - 分母 0、分子大於 0，判成立。
  - 第 5 點（測試）：
    - 沒有 D_v 時為無從判定；D_v 的截止時點未過時為無從判定。
    - 1/5 不成立、2/9 成立。
    - 前綴曾成立、之後回落時，曾否成立仍為是。
    - 輸出排在 `GAP_DISCLOSURE` 之前，`d4_violations` 為空。
    - grep 確認 `report.py` 沒有判定運算。

## 驗證

**實際讀過的檔案與段落**
- dev-lead 交件全文。
- worktree 內的範圍清單全文。
- ADR-0030（worktree 版）：
  - 第 100～370 行：D-1～D-11、K-1～K-12、F-1～F-8、待決事項。
  - 第 431～610 行：補充三（修訂版）、補充四、補充五及附記。
  - 第 772～977 行：補充七、附記、附記二、附記三、附記三之一。
- 補充八最終版全文。
- 風控 RC-237～RC-243 報告全文。
- qa 審查報告：以 grep 讀 N-1～N-8 與相關段落，不是全文。
- 程式與測試：
  - `app/scheduler.py` 全文。
  - `recorder.py` 第 255～400 行。
  - `store.py` 第 420～550 行、第 1415～1614 行。
  - `report.py` 第 360～494 行。
  - `scripts/cg2_register.py` 第 1～200 行。
  - `tests/test_cg2_register_values.py` 全文。
  - `tests/test_cg2_registration_values.py` 的測試清單（grep）。
  - `app/data/cache.py` 的 `resolve_db_path`。
  - `cg2` 相關檔案的 Glob 與 grep。
- 事先宣告：以 grep 查第 1020、1032 行（發布列），以及 ADR-0030 定稿報告的 18:10 段。

**沒有讀或無法確認的部分**
- 沒有執行任何測試，結果採信交件與 qa。
- 沒有讀 qa 報告全文、`test_forecast_scheduler_wiring.py`、`test_forecast_f2_window.py`。
- 沒有確認 APScheduler 的預設 misfire 值。
- 沒有確認登記回貼有沒有第二份備份的 sha256。
- 沒有確認 `index` 快取在 15:xx 取得的收盤會不會被 22:10 那次沿用。這與啟動補跑那一項有關，屬 data-engineer 的範圍。

沒有讀 `.env`，沒有碰任何 `.db`，沒有改任何檔案。

## 下一步

**dev-lead：退役 PR**（新分支，從登記紀錄 commit 之後的 `origin/product/stock-desk` 開出）
1. 刪除補充九第 1 點所列的 9 個檔案。
2. 加「四個檔案不存在」的測試。
3. 以 grep 確認 `apps/stock-desk` 沒有殘留引用。
4. 全套測試跑 3.12 與 3.13。
5. PR 說明引用補充九第 1 點與登記紀錄 commit。

**dev-lead：接線 PR**（`feat/nm5-wiring`）
1. `app/scheduler.py`：依補充九第 3 點實作目標核對，取代現行只檢查檔案是否存在的寫法。
   - 給每個拒絕原因一句固定英文 log。
   - 既有用暫存 DB 的 wiring 測試，改以 monkeypatch 目標導出函式來跑；不得在 job 加路徑參數（K-10）。
   - 補上 S-19a 第 3 點的測試。
2. `store.f2_status`：完整視窗分母為 0 時判成立。補上 S-19a 第 4 點的測試，並更新 `test_forecast_f2_window.py` 中原本「0/0 未成立」的預期（若有）。
3. `store.py` 新增第 0 相位格點遺失判定的唯讀查詢，回傳 G、L、判定（三態）、曾否成立；`report.py` 在現有格點行之後、`GAP_DISCLOSURE` 之前輸出。補上 S-19a 第 5 點的測試；`test_forecast_gap_disclosure.py` 的 `_expected_before_the_line` 跟著改。
4. 套用 RC-237、RC-239 定稿。RC-238 分母 0 那一行，等風控依補充九第 4 點重新定稿後再套；第 3 項的新行字面也等風控定稿。RC-240 一併處理。
5. qa 意見：N-6、N-1 合併前處理；N-2、N-4、N-5 同一輪補上；N-3 不需要。
6. 退役 PR 合併後，merge `origin/product/stock-desk`，確認 R-1 失敗消失，再跑一次全套測試（3.12、3.13 各一次）。
7. 範圍清單與 PR 說明：W-7 的零差異清單移除一鍵檔各項，附註「由退役 PR 刪除」；引用補充九。

**coordinator**
- 依時點限制，依序 append 補充八、補充九。
- 把 RC-238 分母 0 那一行，以及第 5 點的新判定行，送風控定稿。
- 第 6 點：依出處填 P-2，沒有出處的值不填。
- 把啟動補跑的時段問題列為 CEO 待決，先請 data-engineer 回答 D-3 第 7 點既有的 18:00 定案題。

**qa**：依 S-19a 與補充九第 6 點核對。

**相關檔案**
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- `/home/user/AICompany/work/reviews/2026-11-19-補充八最終版-併入RC233至RC236-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-19-接線PR-F2視窗字面判定RC237至RC243-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-19-接線PR審查-qa.md`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/scheduler.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/forecast/store.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/forecast/report.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/app/forecast/recorder.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/scripts/cg2_register.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/tests/test_cg2_register_values.py`
- `/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/apps/stock-desk/backend/tests/test_cg2_registration_values.py`

# CG-2 登記一鍵檔裁示定版（併入風控 RC-185～RC-198；取代前一份的 Q-1、Q-4 與附記全文）

- 審查者：tech-architect
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

這份是第二次補充（風控 RC-185～RC-198）併入後的定版，**取代我上一份報告的 Q-1、Q-4 與檔尾附記全文**。附記請用本報告檔尾的版本 append，舊版不要 append。

- **原因代號：要加。** 代號是一行 `refusal_reason=<code>`，全部條件依風控 RC-197 (a)～(f)。代號集合有 18 個，再加 `unknown`，清單見下方，可以直接送風控逐一審。這一行只印在畫面上，不另寫回貼檔。我上一份建議的 `register_result=REFUSED` 撤回。
- **登記程式啟動之後被中斷：結束碼一律 5**（B-3 維持 blocking）。`WRITTEN_UNCHECKED` 依 RC-192 改名為 `UNCONFIRMED`。`.bat` 的 `[NOTE] ... code %RC%` 那一行保留，並請 CEO 回報那個數字（採納 RC-198）。改完之後，coordinator 只看數字就能判讀：5 代表「登記可能已寫入，不得重跑」，其他數字都代表「沒有寫入」。
- **預檢與登記的 HEAD：登記檔要用機械方式綁定。** 登記檔讀取最近一份預檢回貼檔，比對三項：`preflight_result=PASS`、`git_head` 等於本次的 `HEAD`、`script_sha256_lf` 相同。任一項不符就 STOP（新句子，送風控），而且這個檢查在探針與備份之前。另外，coordinator 事後要核對兩份回貼的 `git_head` 是否相等，並留紀錄。

## 各部門回報（tech-architect）

**第 1 點　原因代號（併入 Q-4）**
- 決定加入的理由：結束碼 3 有 10 種拒絕原因。其中 `prereg_blob` 這類情況取決於 CEO 本機的 git 狀態，用合成資料重現不出來。只靠固定句的話，coordinator 無法診斷。
- 依據：補充六第 4 點 (d)，失敗種類屬於執行狀態；RC-197。
- 做法：
  - 判定方式：把子行程的 stderr 去掉結尾換行，跟「該結束碼對應的那張表」裡的每一句做完全比對。對上就印那一句的代號，對不上就印 `unknown`。stderr 原文絕不轉出。
  - 一鍵檔自己保留一份代號與句子的對照表，不 import `claims`。用測試核對這份表與 `claims.py` 的 `BOOTSTRAP_PATH_REFUSALS`、`BOOTSTRAP_REFUSALS` 一致。
  - 子行程結束碼 5 與其他結束碼都不印代號。
- 代號清單：代號照用 `claims.py` 的鍵名，括號內是對應句的要旨。

| 子行程結束碼 | 代號 |
|---|---|
| 4（`BOOTSTRAP_PATH_REFUSALS`） | `db_missing`（不在預設位置）、`db_not_default`（解析到別處）、`db_not_regular`（不是一般檔）、`env_db_path`、`env_file_db_path`、`not_empty`（已有帳本物件）、`horizons`（兩個 claim 的順序）、`replaces`（帶了取代對象） |
| 3（`BOOTSTRAP_REFUSALS`） | `provisional`（鍵入值格式）、`frozen_commit`（commit 格式）、`prereg_path`、`prereg_sha256`（格式）、`prereg_blob`（該 commit 讀不到 blob）、`prereg_mismatch`（blob 與雜湊不符）、`review_refs`（路徑格式）、`unpublished`（版本未發布）、`phrases`（禁詞命中）、`store`（store 拒絕、未寫入） |
| 對不上 | `unknown` |

- 對照 RC-197 (c)：
  - 這些代號都不帶 invalid、bad、wrong 這類評價字，也不含路徑、`claim_id`、規則版本或驗收結果。
  - `unpublished` 對應的原句裡有「or is rejected」，但代號本身不帶評價。
  - `phrases` 描述的是前置條件，不是對規則的評價。
- 說明文件只能用 RC-197 (d) 那一句通用說法。依 RC-191 的架構，結束碼 3、4 時要請 CEO 回報的畫面行加上這一行。
- 範圍：比字面窄，是新增輸出，不放寬任何寫入條件。

**第 2 點　結束碼與 `.bat`**
- 依據：
  - 補充七附記二第 4 點：任何非 0 的結束碼都視為 STOP。
  - RC-191：本節涵蓋「啟動之後被中斷」的情況。
- 程式要改兩處：
  - `main` 的 `except KeyboardInterrupt` 改成：`state.late` 為真時結束碼 5，否則 2。
  - `UNCONFIRMED` 的改名要一併改到白名單、程式、測試與說明。
- 一鍵檔結束碼的定版語意：

| 結束碼 | 意思 |
|---|---|
| 0 | 完成 |
| 1 | 登記前發生非預期錯誤，沒有寫入 |
| 2 | 登記前被中斷，沒有寫入 |
| 3 | STOP，沒有寫入 |
| 5 | 登記已開始，結果無法確認，不得重跑 |

- 測試：每個階段注入 `KeyboardInterrupt`。啟動子行程之前要得到 2；啟動之後要得到 5，並留下 `register_result=UNCONFIRMED` 的回貼檔。
- 上一份裁示已要求改用 `Popen`，在 `Popen` 成功回傳之後才設 `late`，這點不變。

**第 3 點　預檢之後 HEAD 改變（併入 Q-1）**
- 我讀了 `dev-up.bat`，它依序做這些事：
  1. 切換到 `product/stock-desk`；
  2. `git pull --ff-only`，會移動 `HEAD`；
  3. 結束佔用 8000、3000 port 的行程與舊的 scheduler；
  4. `uv sync --locked`；
  5. 開啟 backend、scheduler、frontend 三個視窗。
- 所以 CEO 在預檢與登記之間只要再跑一次 `dev-up.bat`，`HEAD` 就可能改變，scheduler 也會重新啟動。
- 依據：
  - 補充四第 4 點 (2)：「回傳結果經 coordinator 核對後，再執行登記檔」，核對的對象就是那一份預檢。
  - 補充七附記二第 8 點：`frozen_commit` 取 R-1 的 `HEAD`。
  - `frozen_commit` 會永久寫進登記表，只靠事後核對不夠。
- 程式要改的地方：
  - 新增步驟：在探針之前，讀取 `paste-backs` 資料夾中依時間戳排序最新的一份 `preflight-*.txt`。檔案只以文字讀取；每一行都必須 fullmatch 白名單。
  - STOP 條件（新增 `preflight_mismatch`，結束碼 3；句子送風控，句末依 `_TELL` 的寫法）：
    - 找不到預檢回貼檔；
    - 任一行不在白名單上；
    - 沒有 `preflight_result=PASS`；
    - `git_head` 不等於本次 `HEAD`；
    - `script_sha256_lf` 不等於本次腳本。
  - 測試涵蓋上述每一種不符的情況，並斷言它們都不會呼叫探針、不會備份、不會啟動子行程。
- 這個機械檢查保證不了「被讀到的那份預檢，就是 coordinator 核對過的那份」，因為 CEO 可能又跑了一次預檢。這一點由 coordinator 事後核對兩份回貼並留紀錄來補。
- 操作說明要加一句：「預檢之後到登記之前，不要執行 `dev-up.bat`；若已執行，請重跑預檢並回貼。」字面送風控。
- 範圍：比字面窄。

**順帶修正上一份的 B-1**
- `dev-up.bat` 已經有偵測 scheduler 的方法（用 `Get-CimInstance` 查命令列）。可以考慮在 R-3 加入同樣的偵測：發現 scheduler 在跑就 STOP。這項非 blocking，是建議。
- B-1「連續兩份備份的 sha256 必須相等」仍然是 blocking。它不依賴 Windows 的行程查詢，可以在 Linux 上測試。

## 驗證
- 這次讀了：
  - 風控報告中 RC-185～RC-198 的段落，包括 RC-191、RC-192、RC-197 的原文；
  - `apps/stock-desk/dev-up.bat` 全文。
- 代號清單取自 `claims.py` 第 301～323 行。
- KeyboardInterrupt 的問題已在上一份由 `cg2_register.py` 的 `main` 確認：該處一律 `code = 2`。
- 沒有執行任何程式或 git。

## 下一步
1. devops-sre：
   - 套用 B-1～B-3；
   - 實作原因代號、`UNCONFIRMED` 改名、`preflight_mismatch`；
   - 落實上一份 Q-1～Q-5 的其餘要求；
   - 套用 RC-185～RC-196。
   完成後交 qa 複審。
2. coordinator：把代號清單、`preflight_mismatch` 句、`review_refs_missing` 句與操作說明新增的那一句，一次送風控（RC-197 (f)）；append 下面的附記。

---附記全文（逐字 append，取代上一份版本）---

## 補充七附記三：CG-2 登記一鍵檔的 R-1 等價核對、預檢綁定、備份一致性、review_refs、拒絕原因與結束碼（2026-11-17）

- 決策者：tech-architect。來源：`work/reviews/2026-11-17-CG2登記PR第三段一鍵檔交件-devops-sre.md`、`work/reviews/2026-11-17-CG2登記一鍵檔審查-qa.md`、`work/reviews/2026-11-17-正式登記說明與畫面字句判定RC185至RC198-風控.md`；另讀 `feat/nm5-cg2-registration`（`3a3fccbf`）的 `scripts/cg2_register.py`、`cg2-register.bat`、`dev-up.bat`、`app/forecast/claims.py`。
- 性質：釐清補充四第 3、4、5 點的讀法，收緊一鍵檔。第 1 點將 R-1 的合併 commit 比對由機械改為人工，窄幅寬於字面，已標明；其餘各點皆窄於字面或屬釐清。不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/`。新增的 CEO 可見字面送風控（RC-197 (f)）。CEO 可推翻。

1. **R-1（窄幅寬於字面）**：「沒有 diff」只指 `app/` 與兩份文件。一鍵檔以下列各項代替與 CG-2 合併 commit 的機械比對：
   - `HEAD` 可由 `origin/product/stock-desk` 到達；
   - `HEAD:apps/stock-desk/backend/app` 的 tree id 等於常數；
   - `app/`、兩份文件、一鍵檔與兩個 `.bat` 的工作樹乾淨；
   - 這些路徑的 `git ls-files -v` 標記都是大寫 `H`；
   - git 呼叫停用 `core.fsmonitor` 與 `core.untrackedCache`。

   字面的 R-1 由 coordinator 在核對預檢回貼時完成，核對三件事：
   - 合併 commit 是 `git_head` 的祖先；
   - 兩者之間 `app/` 與兩份文件沒有 diff；
   - `script_sha256_lf` 與 `code_digest` 等於在 `git_head` 重算的值。

   `uv.lock`、`pyproject.toml` 與 venv 不釘。理由：它們的差異只會造成 M-8 雜湊不符或 import 失敗，兩者都會停止。
2. **預檢綁定**：登記檔在探針與備份之前，讀取最新一份預檢回貼檔。以下任一成立就 STOP，結束碼 3：
   - 讀不到該檔，或檔內任一行不在白名單上；
   - 沒有 `preflight_result=PASS`；
   - `git_head` 不等於本次 `HEAD`；
   - `script_sha256_lf` 與本次腳本不同。

   coordinator 事後核對登記回貼的 `git_head` 等於已核對的預檢 `git_head`，並以 commit 留紀錄；不相等時升級 tech-architect。操作說明告知 CEO：預檢之後、登記之前不得執行 `dev-up.bat`。
3. **連線與備份**：
   - 補充四第 4 點的「一鍵檔不開寫入連線」讀為「不對主 DB 開寫入連線」，寫入新備份檔的連線不在此限。
   - 補充六第 1 點 (b) 的末句只適用驗收腳本（RC-158b）。
   - 為保證「一致備份」：
     - 讀回檢查通過之後，依同一 URI 規則再取第二份備份；兩份 sha256 必須相等，否則 STOP；兩份都不刪除。
     - 鍵入 0／1 之後、啟動子行程之前，重驗 port 8000。
     - 子行程以 `Popen` 啟動成功後，才進入「登記已開始」的狀態。
4. **`review_refs`**：
   - 只列對被登記內容作出核可或核對判定的紀錄。被登記內容是：事先宣告、C-8 紀錄檔、凍結包與規則檔、definition。具體是風控對三者的確認，以及 M-9 的風控核對與 qa 最終審查。
   - 不列：工具或流程的審查、管線驗收回貼、交件報告與裁示。
   - 路徑在進入最終 qa 前以常數固定，不得含空白。
   - 一鍵檔執行時逐一確認每個路徑在 `HEAD` 存在，否則 STOP。
5. **拒絕原因（依 RC-197）**：
   - 子行程結束碼 3、4 時，畫面加印一行 `refusal_reason=<code>`。
   - `code` 的封閉集合是 `claims.py` 的 `BOOTSTRAP_PATH_REFUSALS`（結束碼 4）與 `BOOTSTRAP_REFUSALS`（結束碼 3）的鍵，以及 `unknown`。
   - 判定方式：stderr 與該結束碼對應表中的一句完全相等時印該句的鍵；否則印 `unknown`。不轉出 stderr。
   - 說明文件只用 RC-197 (d) 的通用句；coordinator 不向 CEO 解釋代號。
6. **結束碼**：
   - 一鍵檔的結束碼：0 完成；1、2、3 都表示沒有寫入，其中 1 與 2 只用於登記開始之前；5 表示登記已開始、結果無法確認。
   - 登記開始之後的任何例外、中斷、逾時，以及結束碼 0 但輸出的形狀、順序或值與本次 `HEAD`、M-8 常數、鍵入值不符，一律結束碼 5，並寫 `register_result=UNCONFIRMED` 的回貼（RC-192）。
   - `.bat` 保留 `[NOTE]` 行，CEO 回報其中的數字。
7. **順序**：
   - R-6 放在「重跑全部預檢」之中，排在備份之前；登記程式在備份之後還會再比對一次，所以補充四第 4 點的順序成立。
   - 探針屬於收緊，預檢也要執行探針。
   - 執行前提：在本次 `HEAD` 執行過 `dev-up.bat` 並已 `git fetch`，然後關閉三個視窗，之後才執行預檢。

- **S-15c（逐條可檢查）**：
  - 第 1 點：三個新增的監看檔各有一個 STOP 測試；`assume-unchanged`、`skip-worktree` 各有一個 STOP 測試。
  - 第 2 點：每一種不符各有一個 STOP 測試，並斷言沒有呼叫探針、沒有備份、沒有啟動子行程。
  - 第 3 點：兩份備份不相等時判 STOP；有、無 `-wal` 各一個「兩份相等」的測試；鍵入之後 port 有監聽時判 STOP；`Popen` 拋 `OSError` 時結束碼 3。
  - 第 4 點：路徑不存在時判 STOP；路徑不含空白（測試）。
  - 第 5 點：代號表與 `claims.py` 兩張表相等；每個代號與 `unknown` 各一個測試；畫面不含 stderr 原文。
  - 第 6 點：注入 `KeyboardInterrupt`，啟動子行程前結束碼為 2，啟動後為 5 並留下 `UNCONFIRMED` 回貼。
  - 第 7 點：預檢會執行探針（測試）。

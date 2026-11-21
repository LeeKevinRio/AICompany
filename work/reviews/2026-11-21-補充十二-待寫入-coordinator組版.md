# 補充十二（待寫入 ADR-0030；coordinator 以腳本組版）

- 組版者：coordinator（腳本逐字抽取，沒有手動改字）
- 日期：2026-11-21
- 底稿：`work/reviews/2026-11-21-補充十二退役全文與心跳裁示-tech-architect.md` 的 `<<<補充十二開始>>>` 到 `<<<補充十二結束>>>` 區塊
- 套用：`work/reviews/2026-11-21-補充十二與退役連帶條件判定RC344至RC356-風控.md` 的替換 B1～B5（腳本逐字替換，每句原文各出現一次）
- 狀態：**風控 RC-344～RC-356 附條件核可，B1～B5 已套用。待 tech-architect 確認 B1～B5 未改動技術意旨後才算定稿；確認前不得寫入 ADR。**

## 檔頭補充紀錄行

- 補充紀錄：2026-11-21 append 補充十二（D-7 真實資料管線驗收一鍵檔的退役：範圍、S-13b～S-13e 的存續期間、時點與順序、稽核與取回條件、兩支新一鍵檔的凍結差異基準、對既定補充的讀法註記；tech-architect 裁示；第 2 點窄幅寬於 S-13b～S-13e 字面，已標明；其餘為收緊或釐清；不改本文、補充六及其附記、補充八～十一的字面，不改事先宣告 v0.32、規則檔、定義物件、已登記雜湊與 `code_digest` 涵蓋的原始檔，不改 `app/`；CEO 可見部分由風控定稿；coordinator 定案，CEO 可推翻；來源 `work/reviews/2026-11-21-驗收一鍵檔登記後去留與修法裁示-tech-architect.md`、`work/reviews/2026-11-21-三支舊一鍵檔缺工具提示定稿RC336至RC343-風控.md`）

## 正文

## 補充十二：D-7 真實資料管線驗收一鍵檔的退役（2026-11-21）

- 決策者：tech-architect。
- 來源：
  - `work/reviews/2026-11-21-驗收一鍵檔登記後去留與修法裁示-tech-architect.md`
  - `work/reviews/2026-11-20-兩份CEO文件單項補審RC325至RC330-風控.md`
  - `work/reviews/2026-11-20-警告行新字面與驗收書面紀錄確認RC331至RC335-風控.md`
  - `work/reviews/2026-11-21-三支舊一鍵檔缺工具提示定稿RC336至RC343-風控.md`
  - 另讀產品線的 `apps/stock-desk/pipeline-acceptance.bat`、`backend/scripts/pipeline_acceptance_real.py`、`backend/tests/test_import_graph.py`、`test_pipeline_acceptance_real_eol.py`、`forecast_pipeline_harness.py`、`test_forecast_pipeline_harness.py`；`feat/forecast-status-oneclick` 的 `tests/test_forecast_status_flow.py`；`feat/gap-check-oneclick` 的 `tests/test_gap_check_flow.py`。
- 性質：
  - 第 2 點限定 S-13b、S-13c、S-13d、S-13e 所列測試的存續期間，窄幅寬於字面，已標明。
  - 第 1、3～5 點為收緊；第 6 點為釐清。
  - 不改本文、補充六與其附記一～三、補充八～十一的字面；不改事先宣告 v0.32、規則檔、定義物件與已登記雜湊。
  - 不改 `app/`，`code_digest` 不變。
  - 依據：真實資料管線驗收的規格要求只綁 CG-2（補充四第 5 點 M-1、第 6 點；補充六第 3、5、6 點；補充七第 7 點）。登記完成之後，本 ADR 與各補充沒有任何條款要求再次執行；CG-4 與 D-5 第 6 點也不以 D-7 為閘門。
  - CEO 看得到的部分（退役通知、說明文件），字面由風控定稿。CEO 可推翻；推翻時改依 RC-335 辦理，RC-338 對這支 .bat 的改字、RC-312 對這支 .bat 的部分與 RC-325 的列名一併恢復適用，並另發經風控定稿的更正通知。

1. **退役範圍與各檔處置**
   - (a) **刪除**（產品線，路徑相對於 `apps/stock-desk/`）：
     - `pipeline-acceptance.bat`
     - `backend/scripts/pipeline_acceptance_real.py`
     - `backend/tests/test_pipeline_acceptance_real_bars.py`
     - `backend/tests/test_pipeline_acceptance_real_flow.py`
     - `backend/tests/pipeline_real_world.py`
     - `backend/tests/pipeline_real_loader.py`
     - `backend/tests/test_pipeline_acceptance_real_eol.py`：刪除前先依 (b) 搬出指定測試。
   - (b) **搬移**：
     - 把 `test_pipeline_acceptance_real_eol.py` 的下列測試搬到新檔 `backend/tests/test_lockfile_eol.py`：
       - `test_the_backend_attribute_file_pins_uv_lock_to_lf`
       - `test_the_root_attribute_file_is_not_changed_by_this_work`
       - `test_git_ls_files_eol_of_the_real_uv_lock_is_lf_lf`
       - `test_with_autocrlf_true_the_attribute_keeps_a_fresh_checkout_lf`
       - `test_control_without_the_attribute_autocrlf_true_writes_crlf`
     - 同時搬移它們需要的 `_isolated_git` fixture、`git`、`make_repo`，以及 `BACKEND`、`ATTRIBUTES`、`LF`、`CRLF` 常數。
     - 函式本體逐字不變，只刪除呼叫 `real.` 的那幾行斷言：
       - `test_with_autocrlf_true_…` 中的 `real.check_pinned_eol(...)` 與 `real.core_autocrlf(...)` 兩行；
       - `test_control_without_…` 中的 `real.check_pinned_eol(...)` 一行。
       - 這兩個測試裡的位元組相等斷言保留。
     - 新檔不得 import `tests.pipeline_real_world` 或任何腳本。模組 docstring 寫明依據是補充六第 7 點與補充十二第 1 點。
     - 理由：這些測試守的是 `uv.lock` 的換行屬性（補充六第 7 點的根治方式），也就守住了 `runtime_json` 中 `lockfile_sha256` 的穩定，從而守住 D-5 第 6 點。這項性質不隨工具退役。
     - 其餘只測 `check_pinned_eol`、`core_autocrlf` 與 preflight 的測試，隨原檔刪除。
   - (c) **修改**：`backend/tests/test_import_graph.py` 第 54 行。
     - 原文 `assert "pipeline_acceptance_real" in names`，改為 `assert names - {"scripts"}`，作用是確認掃描到的腳本不為空。
     - 同檔其他行零差異。第 59～66 行的 `test_the_script_import_scan_has_teeth` 用的是字面名稱集合，不讀實際檔案，保留不改。
     - K-11 與「`app/` 不可達 `scripts/`」照舊成立。
   - (d) **零差異**：
     - `backend/tests/forecast_pipeline_harness.py`、`backend/tests/test_forecast_pipeline_harness.py`、`backend/tests/dirdef_helpers.py`、`backend/tests/outlook_helpers.py`；
     - `backend/.gitattributes`、repo 根目錄的 `.gitattributes`、`backend/uv.lock`；
     - `app/` 全部。
     - 前兩檔中的 `pipeline-acceptance.db`、`pipeline-acceptance-{name}-h{h}`、`frozen_commit="pipeline-acceptance"`，是 harness 的識別字，不是這支工具。
   - (e) **方式**：
     - 以獨立 PR 一次完成 (a)～(c) 與第 5 點的凍結基準檔。不得以 skip、xfail 或只刪部分測試代替。
     - 不得與接線 PR、CG-2 一鍵檔退役 PR，或任何 `app/` 改動放在同一個 PR。
     - PR 附 grep 結果：產品線上除了下列位置，不再有 `pipeline_acceptance_real`、`pipeline-acceptance.bat`、`pipeline_real_` 的引用：
       - (d) 所列的 harness 識別字；
       - `test_import_graph.py` 的字面名稱集合；
       - `gap_check` 測試中工作資料夾名稱的排除集合；
       - 第 5 點的凍結基準檔與引用它的測試；
       - `docs/`、`work/`。
2. **S-13b～S-13e 的存續期間**（窄幅寬於字面）
   - S-13b、S-13c、S-13d、S-13e 列給 `scripts/pipeline_acceptance_real.py` 的測試，存續到本退役 PR 合併為止。放寬處是：之後 HEAD 不再含這些測試。理由是測試對象同時移除。
   - 不受影響、照舊有效：
     - D-9 S-13 與 K-11：harness 的隔離測試；
     - 補充五第 3、5 點：harness 的空轉防護與輸出限制；
     - 第 1 點 (b) 搬移的換行測試。
   - 補充六第 1 點 (b) 的讀法（Q-1）依補充六附記第 2 點（RC-158b），只適用這支腳本。退役後產品線上沒有任何程式可以援引它；任何 tests、scripts 與 `app/` 都不得以它為依據讀取主 DB。
3. **時點與順序**
   - (a) 合併的前提，全部成立才可以合併：
     - 補充六第 6 點 (b)～(d) 的核對已完成，並依補充六第 6 點 (b) 記錄；
     - 補充四第 4 點 (3) 的登記紀錄 commit 已存在；
     - 本補充已 append 進本 ADR；
     - 第 5 點的凍結基準檔，與它在 PR 說明中的 blob id、sha256；以及風控定稿的退役通知已交給 CEO，並由 coordinator 在 work/ 書面記錄 RC-344 的暫存資料夾核對。
   - (b) 排在 CG-2 一鍵檔退役 PR（補充九第 1 點）合併之後。兩者不合併成一個 PR，理由有三：
     - 補充九第 1 點已經定稿並列舉退役對象，併進來就要改它的字面；
     - 那支 PR 已經過審查，又在接線 PR 的關鍵路徑上（接線 PR 要先 merge 它），不應讓本點的審查拖慢它；
     - 兩支 PR 分別對應不同的 ADR 依據。
   - (c) 排在狀態報告一鍵檔 PR（補充十一第 2 點）合併之前，讓 RC-335 不會開始適用。來不及時，期間內任何一次執行都依 RC-335 辦理；依本補充，期間內不應有執行。
   - (d) 從預檢回貼到登記完成之間不得 push 產品線（補充七附記三第 2 點）。本 PR 不得在這段期間合併。
   - (e) 這次驗收若失敗，或依補充六第 3、5、6 點須重跑，本退役等「harness 通過」與登記都完成之後才進行。
4. **稽核與日後取回**
   - (a) 稽核以 git 歷史為準。
     - 本補充所稱的 G_acc，是最後一次「harness 通過」回貼中的 `git_head`（補充六第 6 點 (a)）。
     - 退役的檔案以 `git show <G_acc>:<path>` 取得。`product/stock-desk` 不得改寫歷史。
     - 下列內容不刪、不改：`work/` 中的回貼原文、補充六第 6 點 (b) 的核對紀錄、`work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md`。
   - (b) 取回的條件：只有在本 ADR 修訂後要求再次執行真實資料管線驗收時，才可以取回。
     - 例如：依 D-1 第 2 點、補充九第 2 點登記新 claim；CEO 依 D-7 第 4 點選用候選規則；依 F-5 更換資料源。
     - 不得只為了診斷或「再確認一次」而取回。
   - (c) 取回時必須套用以下設計，取代補充六第 1 點 (a) 原本的逐檔複製與比對。這是補充六第 1 點 (a)「複製前後」的讀法，屬收緊：
     1. 依 `stock-desk.db`、`-wal`、`-shm` 的順序，對三個來源各記存在與否；存在的取 sha256。
     2. 只複製第 1 步判定存在的檔。
     3. 依同一順序，對三個複本記存在與否與 sha256。
     4. 依同一順序，對三個來源再記一次存在與否與 sha256。
     5. 一次比對：每一檔在第 1、3、4 步的存在與否都要相同；存在時，三個 sha256 都要相同。任何一項不符就 STOP `copy_changed`，不印任何一行 `copy_check`，不產生回貼。
     6. `copy_check` 的三行格式、順序與值域依補充六附記三第 1 點，不變；仍要在第一次開啟複本連線之前完成（補充六附記二第 2 點 (c)）。
     - 主 DB 三檔仍然只能以 `"rb"` 開啟（RC-158a）。
     - 測試至少涵蓋下列情形：
       - 注入「複製 `db` 之後、複製 `-wal` 之前，改動來源 `db` 並刪除 `-wal`、`-shm`」時 STOP；
       - P0 之後 `-wal` 出現；
       - P0 之後 `-wal` 消失；
       - 只有 `-shm` 改變；
       - 複製後 `db` 改變；
       - 複本內容不符；
       - 順序 trace：所有 P0 都在第一個複本寫入之前，所有複本寫入都在任一 P1 之前；
       - S-13b～S-13e 照舊全過。
   - (d) 取回時另外必須做到：
     - 版本行不得沿用 `pipeline_acceptance_real version=1`；
     - 來源在讀取中消失時的處理，以及版本行、STOP 句與說明文件的字面，送風控定稿（RC-164 的比照）；
     - 補充六附記第 6 點的四項前提重新成立；
     - 依當時已定稿的缺工具提示字面修正 `.bat`；
     - 取回後的檔案路徑與名稱不得與第 5 點的凍結基準檔相同；給 CEO 的說明文件中「不可同時執行」的列名，依當時風控定稿補回（RC-325 比照），並另發經風控定稿的通知。
5. **兩支新一鍵檔的差異基準**
   - (a) 性質：
     - `feat/forecast-status-oneclick` 的 `tests/test_forecast_status_flow.py`（`PRECEDENT_BAT`、`test_the_bat_differs_from_the_precedent_only_in_the_listed_lines`），以及 `feat/gap-check-oneclick` 的 `tests/test_gap_check_flow.py`（`test_the_bat_matches_the_pipeline_acceptance_launcher_except_its_own_lines`），改用一份凍結的基準檔。
     - 這份基準檔的位元組等於 `git cat-file blob <G_acc>:apps/stock-desk/pipeline-acceptance.bat`，CRLF 也一起保留。
     - 它同時必須等於本退役 PR 的 merge-base 上同一路徑的 blob。兩者不同就停止，升級 tech-architect。
   - (b) 形式：
     - 放在 `backend/tests/` 底下的測試資料資料夾。副檔名不得是 `.bat`、`.cmd`、`.ps1` 或其他可執行副檔名。
     - 同一資料夾放一個 `.gitattributes`，把該檔設為 `-text`。不得改 `backend/.gitattributes`（第 1 點 (b) 的測試釘住了它的內容），也不得改 repo 根目錄的 `.gitattributes`（main 維持零產品耦合）。
     - 全產品線只有一份。兩支分支引用同一個路徑；qa 核對兩支分支內的位元組相同。
     - PR 說明寫明 G_acc、blob id 與 sha256；引用它的測試以常數釘住 sha256。
   - (c) 地位：
     - 這份檔不代表任何現存工具，也不是可以執行的一鍵檔。它的唯一用途，是作為上述差異測試的比對基準。
     - 之後不得更新。
     - 兩支新一鍵檔日後改字時（例如依風控定稿修改），改的是測試中列舉的差異行，不得改基準檔。
     - 不得以它取回工具（取回依第 4 點）。它不是 CEO 會執行的檔，不適用 RC-336、RC-338、RC-339 的改字，也不得為了與現行字面一致而修改它；兩支新一鍵檔中 CEO 看得到的字面一律依風控定稿，不以基準檔的字面為準。
   - (d) `test_forecast_status_flow.py` 中與 `r2-probe.bat` 比對的那項測試，不在本點範圍。`r2-probe.bat` 日後退役時，比照本點處理。
6. **對既定補充的讀法註記**（釐清，不改字面）
   - (a) 補充十一第 2 點的「`.bat` 比照既有的一鍵檔」，自本退役 PR 合併起，讀為比照第 5 點的凍結基準檔。
   - (b) 補充八第 5 點 (c) 所引的 RC-158a、RC-158c、RC-162，是以條件字面被引用，不依賴這支工具存在，照舊有效。同款「不援引補充六第 1 點 (b)」，與第 2 點末款一致。
   - (c) 補充四第 5 點 M-1、補充六第 6 點、補充七第 7 點對「harness 通過」的要求，已由 G_acc 那一次履行。退役不改變這個事實，也不構成重跑的理由。
   - (d) 補充八～十一沒有其他條款點名 `pipeline-acceptance.bat`。

- **S-21（逐條可檢查）**
  - 第 1 點：
    - 退役 PR 的檔案清單恰好是 (a)～(c) 加第 5 點的基準檔與它的 `.gitattributes`；
    - `test_lockfile_eol.py` 恰好含 (b) 所列的五個測試，與原函式的差異只有 (b) 指定刪除的行（附 diff）；
    - `test_import_graph.py` 的 diff 恰好一行；
    - (d) 所列檔零差異（`git diff --stat`）；
    - (e) 的 grep 結果附在 PR 說明。
  - 第 3 點：qa 以 commit 順序核對：
    - 登記紀錄 commit 與本補充的 append commit，都早於本 PR 的合併 commit；
    - CG-2 一鍵檔退役 PR 的合併 commit 早於本 PR 的合併 commit；
    - 本 PR 的合併 commit 早於狀態報告一鍵檔 PR 的合併 commit；退役通知送出紀錄的 commit 早於本 PR 的合併 commit。
  - 第 5 點：
    - 基準檔的 sha256 等於 G_acc 那個 blob 的 sha256，也等於 merge-base 那個 blob 的 sha256；
    - 兩支分支的差異測試讀的是基準檔，不再讀 `pipeline-acceptance.bat`（grep）；
    - 在兩支分支 merge product 之後的狀態下跑全套，結果為綠。

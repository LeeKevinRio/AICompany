# 補充十二（pipeline-acceptance.bat 退役）全文與心跳裁示

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# 補充十二（`pipeline-acceptance.bat` 退役）全文與心跳裁示

- 審查者：tech-architect
- 日期：2026-11-21
- 全程唯讀，沒有改任何檔，沒有讀 `.env`，沒有碰 `backend/data/`。

---

## 本次結論

**一、退役補充**
- 補充十二全文在下面「各部門回報」第一節的區塊裡，可以直接用腳本抽出。
- 退役範圍我逐檔讀過，刪、留、改都已在補充裡寫明，不留給 dev-lead 判斷規格：
  - **刪 6 個檔**：`.bat`、腳本、`test_pipeline_acceptance_real_bars.py`、`test_pipeline_acceptance_real_flow.py`、`pipeline_real_world.py`、`pipeline_real_loader.py`。
  - **整檔刪除，但先搬出 5 個測試**：`test_pipeline_acceptance_real_eol.py`。這 5 個測試守的是 `uv.lock` 的換行屬性，這項屬性不會跟著工具退役。
  - **改 1 行**：`test_import_graph.py` 第 54 行。
  - **零差異**：`forecast_pipeline_harness.py`、`test_forecast_pipeline_harness.py`。它們出現的 `pipeline-acceptance` 字串是 harness 的識別字，跟這支工具無關，而且 harness 屬於補充六第 6 點 (d) 與 K-11 的範圍。
- **（tech-architect 建議）兩個退役 PR 不合併成一個。**
  - CG-2 一鍵檔退役 PR（`c559b4af…`）照補充九先合併，本退役 PR 排在它之後。
  - 兩個 PR 都在登記紀錄 commit 之後；本退役 PR 要在狀態報告一鍵檔合併之前。
- 補充八～十一都沒有點名 `pipeline-acceptance.bat`。只有補充十一第 2 點的「比照既有的一鍵檔」需要加一個讀法註記，已寫在補充十二第 6 點。
- 受影響的風控項目共 12 項，列在第一節最後，請送風控。

**二、心跳**
- (a) **規格沒有寫心跳的落地時點**，CG-1～CG-4 也沒有列它。所以心跳不是接線 PR 的合併前置。
  - （tech-architect 建議）不要為了心跳擋接線 PR。
  - 但心跳要怎麼讀，應該在接線 PR 合併前以補充寫定，讓第一筆 `forecast_run` 起就有人負責、有一套比對方式。
- (b) **在 CEO 的電腦上，停機無法事前偵測，只能事後發現。**
  - （tech-architect 建議）核心期間把「狀態報告一鍵檔＋coordinator 每週比對」讀作 D-10 與補充五 (h) 所說的心跳，用一段補充寫清楚。
  - 這段補充要明寫：它的偵測能力窄於自動心跳，最多會晚一個回報週期才發現。
  - 現在不建議做自動心跳。自動心跳要嘛新增 CEO 看得到的輸出，要嘛要在 CEO 本機排程或對外連線，代價都高於它能帶來的好處。
- (c) **分工**：
  - tech-architect 出釐清補充；
  - devops-sre 確認接下這個讀法，並定義偵測到停機後怎麼處理；
  - 風控管 CEO 面的字面；
  - CEO 只有在要做自動化時才需要決定（本機排程或對外服務）。

## 各部門回報（tech-architect）

### 一、補充十二

**寫入方式**
- 檔頭補充紀錄行加在補充十一那一行之後；正文整節加在補充十一之後。
- 寫入時點：本退役 PR 合併之前（第 3 點 (a)）。

<<<補充十二開始>>>

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
  - CEO 看得到的部分（退役通知、說明文件），字面由風控定稿。CEO 可推翻；推翻時改依 RC-335 辦理。

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
     - 第 5 點的凍結基準檔，與它在 PR 說明中的 blob id、sha256。
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
     - 取回後的檔案路徑與名稱不得與第 5 點的凍結基準檔相同。
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
     - 不得以它取回工具（取回依第 4 點）。
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
    - 本 PR 的合併 commit 早於狀態報告一鍵檔 PR 的合併 commit。
  - 第 5 點：
    - 基準檔的 sha256 等於 G_acc 那個 blob 的 sha256，也等於 merge-base 那個 blob 的 sha256；
    - 兩支分支的差異測試讀的是基準檔，不再讀 `pipeline-acceptance.bat`（grep）；
    - 在兩支分支 merge product 之後的狀態下跑全套，結果為綠。

<<<補充十二結束>>>

**送風控的項目**

| 項目 | 影響 | 要風控判定的事 |
|---|---|---|
| RC-338 | `pipeline-acceptance.bat` 的三行改字作廢。`r2-probe.bat` 的改字仍然要做，但 (a) 的理由之二（`test_pipeline_acceptance_real_flow.py:1425-1434` 的耦合測試）隨檔案刪除而消失。(b) 對 pipeline 基準的差異行更新，改為不需要（基準已凍結）。(d) 不再適用。 | `r2-probe.bat` 能否單獨改字；(c) 的時點要不要維持 |
| RC-312 | 已被 RC-338 取代 | 結案 `pipeline-acceptance.bat` 的部分 |
| RC-325 | 狀態報告說明文件草稿第 108 行逐支列名了這支工具；必說 (a) 的理由「與它同時執行不會 STOP」也隨退役消失 | 說明文件在退役後才送出時，要不要刪掉這支的列名；必說 (a) 的理由要不要改 |
| RC-335 | 如果在狀態工具合併之前退役，RC-335 就不會開始適用 | 附條件結案 |
| RC-342 | 這次執行仍然適用；`r2-probe.bat` 照舊適用 | 退役後刪去其中的 pipeline 部分 |
| RC-339 | 備用字面規定「五支同時換」，名單中有這支 | 名單改為四支 |
| RC-310／RC-318 | 「差異 7 行」的核對對象改成凍結基準 | 確認核對機制等效 |
| RC-297 第 168 行 | 原本說「日後若要退役，另發通知」 | 退役通知的字面；CEO 家目錄下 `stock-desk-pipeline-acceptance` 資料夾怎麼處置 |
| RC-158b | 退役後沒有任何程式可以援引補充六第 1 點 (b) | 確認這個讀法 |
| RC-160a/b、RC-161a/b、RC-164 | 補充六附記第 6 點規定這些條件繼續有效 | 確認退役後它們只約束取回後的工具 |
| RC-334 | 這次驗收的貼回存檔照辦，不受影響 | 不需要判定 |

**說明文件的查核**
- `work/dispatch/2026-11-16-真實資料管線驗收操作說明-CEO.md` 是歷史紀錄，不改。
- 其他 CEO 文件中提到這支工具的地方，由 coordinator 盤點後交風控。

### 二、心跳

**(a) 是不是接線 PR 的前置？**
- 規格只指派了責任，沒有寫時點：
  - D-10 表（ADR 第 275 行）：「心跳由 devops-sre 讀 `forecast_run_end`」；
  - 補充五第 1 點 (h)（第 560 行）：「停機的偵測由 devops-sre 的心跳負責」；
  - 待決事項 devops-sre 列（第 359 行）只寫「心跳」。
- 對照之下，同一列的定期備份有寫期限：n̂ 達 ⌈c₁÷2⌉ 之前。
- CG-1～CG-4（第 186～195 行）都沒有列心跳。所以心跳不是接線 PR 的前置。
- （tech-architect 建議）不加成前置，理由有兩點：
  - 停機只會讓紀錄變少，不會寫出錯誤的紀錄。帳本是 append-only，F-2 會在主機恢復後把漏掉的 session 計進分子（補充五第 1 點 (d)、(h)）。
  - 擋住接線，不會讓停機偵測變好。
- 但 F-2 第二句的格點遺失是永久的（第 328 行；ADR 第 297 行估計 h5 可能連續失去數週到約 3 個月）。所以應在接線 PR 合併前，以補充寫定心跳的讀法，讓第一筆 `forecast_run` 起就有一套比對方式。

**(b) 實際能做到什麼程度**
- 事前偵測不可能：主機關機時，本機什麼都不會跑。
- 能做的只有事後發現，有三種做法：
  1. **下次啟動時**，由 scheduler 比對上一次執行的時間。
     - K-3 規定 scheduler 只能經 recorder 進入核心（第 313 行）；讀取還要經 store 的 `_read()`（補充十第 6 點）。所以要在 recorder 新增唯讀函式，這會改變 `code_digest`。
     - 在第一筆紀錄之後才加，會觸發 D-5 第 6 點的重算。
     - 新增的 log 會出現在 CEO 看得到的 scheduler 視窗，要經風控。
  2. **CEO 本機的 Windows 工作排程**定時檢查：要在 CEO 本機建立排程，比照補充十第 5 點，須以 AskUserQuestion 取得 CEO 明確同意。主機關機時它也一樣不會跑。
  3. **對外的 dead-man 服務**：資料會離開 CEO 的電腦，還會牽涉祕密與費用，屬於另一則 ADR，要 CEO 決定。
- 現況已經有的：
  - 狀態報告一鍵檔讀 `forecast_run`／`forecast_run_end`，會列出最近一次執行（含「沒有 end 列」；補充十第 6 點），以及 F-2 最近完整視窗的分子與分母（補充五第 1 點 (g)）。
  - CEO 每週貼回，由 coordinator 比對。
  - 20 個平日的視窗（約 4 週）長於每週一次的回報間隔。所以只要每週都有貼回，過去 4 週內任何一個漏記的 session，都會出現在某一次的分子裡；停機中或剛恢復時，最近一次執行的日期也會顯示出來。
  - 我的判斷：這套做法已經符合 D-10「讀 `forecast_run_end`」的字面。它的偵測能力是「最多晚一個回報週期」，而且要靠 CEO 每週執行。
- （tech-architect 建議）以補充寫一段釐清。要點如下，全文要另行派工再起草：
  - ① 核心期間，D-10 與補充五 (h) 的「心跳」，讀為「狀態報告一鍵檔＋coordinator 每週比對並在 `work/` 記錄」。性質是釐清，但偵測能力窄於一般所說的自動心跳，要標明。
  - ② 比對項目：
    - 最近一次執行的台北日期，對照最近一個應執行的交易日。休市日由 coordinator 依 TWSE 官方日曆人工判斷，不在 `app/` 內新增日曆（補充八第 3 點 (c)）。
    - F-2 第一句兩項分子相較上一份的變化。
    - 「沒有 end 列」是否持續出現。
    - 超過一定天數沒有貼回，就視為心跳中斷。我建議 8 個日曆日，CEO 可推翻。
  - ③ 升級：
    - 發現漏記、或心跳中斷時，當天通知 devops-sre。
    - F-2 成立，或格點遺失達第 328 行的門檻時，依該條升級 CEO 與 devops-sre。
    - CEO 那一邊照常只貼回；要對 CEO 說什麼，由風控定字面。
  - ④ 不做：自動偵測、本機排程、對外服務，以及新增任何 CEO 可見輸出。
  - ⑤ 重審觸發，任一發生就由 devops-sre 提出做法 1 的設計送審：
    - 連續兩次心跳中斷；
    - 事後發現一段停機持續 5 個平日以上；
    - F-2 第二句成立。
- **沒有查證的**：
  - `app/scheduler.py` 第 192～198、775 行，以及 `forecast_run_end` 的讀寫點，我沒有自己讀，依你查到的事實；
  - RC-320、RC-326 的全文；
  - `F2_SHORT_LINE` 在視窗未滿時會不會印出分子（影響接線後前 4 週的比對能力；我 11-20 的裁示 4 (d) 已指出這段期間「成立」只顯示當下）。

**(c) 分工**
- **tech-architect**：起草 (b) 的釐清補充。編號建議是補充十三，排在補充十二之後、接線 PR 合併之前。
- **devops-sre**：
  - 書面確認接下這個讀法，作為 D-10 心跳的責任人；
  - 定義偵測到停機後的技術處置：查明原因，以及恢復時有沒有需要重啟的程序；
  - 只有在 ⑤ 觸發時，才設計做法 1。
- **coordinator**：執行每週比對與 `work/` 紀錄。
- **風控**：
  - 判定這個釐清有沒有改變已經給 CEO 的承諾，或 RC-246 通知的內容；
  - 定稿心跳中斷時對 CEO 的問句；
  - 判定「窄於自動心跳」要不要讓 CEO 知悉。
- **CEO**：
  - 這個釐清不需要 CEO 事先決定，CEO 可推翻；
  - 只有採用做法 2（本機排程）或做法 3（對外服務）時才要 CEO 決定。原因是前者在 CEO 的電腦上建立排程，後者讓資料離開他的電腦，都超出 coordinator 能定案的範圍；
  - 「主機平日晚上開機的承諾」本來就是 CEO 的待決事項（第 348 行，#9），不因心跳的讀法而改變。

## 驗證

- **讀過的檔**：
  - 產品線：`apps/stock-desk/pipeline-acceptance.bat` 全文；`backend/tests/test_import_graph.py` 全文；`test_pipeline_acceptance_real_eol.py` 第 1～95 行與全部測試名稱；`forecast_pipeline_harness.py`、`test_forecast_pipeline_harness.py`、`pipeline_real_loader.py`、`pipeline_real_world.py`、`test_pipeline_acceptance_real_bars.py` 的相關片段；
  - `feat/forecast-status-oneclick` 工作樹：`test_forecast_status_flow.py` 第 1294～1323 行；
  - `feat/gap-check-oneclick` 工作樹（`agent-acec04b09d9a79ee5`）：`test_gap_check_flow.py` 的相關片段；
  - RC-336～RC-343 全文；
  - ADR-0030 第 186～360 行；
  - 補充八、九、十、十一四份來源，以「pipeline／補充六／S-13／copy_check／真實資料／比照／一鍵檔／.bat」做關鍵字搜尋。
- **grep 範圍**：
  - `apps/stock-desk/` 排除 `backend/tests` 之後，只有 `.bat` 與腳本提到這支工具；
  - `backend/tests/` 共 8 檔提到它（另含 flow 測試）；
  - `.github/` 沒有提到。
- **沒有查證的**：
  - 兩支新分支目前的最新 head 是否與我讀的工作樹相同；
  - `apps/stock-desk/docs`、frontend 有沒有提到這支工具（grep 已涵蓋 `apps/stock-desk/` 全部，沒有命中；但沒有另外確認 `node_modules`、`.venv` 等目錄的排除）；
  - `r2-probe.bat` 改字之後，第 1312 行那項測試是否仍為綠：依程式碼推論仍為綠，沒有實際執行；
  - 心跳相關見 (b) 末段；
  - 以上都沒有在 Windows 實測。

## 下一步

- **coordinator**：
  - 用腳本抽出補充十二，在本退役 PR 合併之前 append；
  - 把上表的項目送風控；
  - 依補充十二第 3 點排定 PR 順序；
  - 盤點提到這支工具的 CEO 文件；
  - 心跳一題：決定要不要請我起草補充十三。
- **devops-sre**：
  - 依第 5 點建立唯一一份凍結基準檔與它的 `.gitattributes`，兩支分支改為讀它；
  - 心跳部分：依 (c) 書面確認接下責任。
- **dev-lead**：依第 1 點 (a)～(e) 做退役 PR。依補充十二第 3 點，等登記完成、CG-2 一鍵檔退役 PR 合併之後才合併。
- **qa-reviewer**：依 S-21 核對（含 Codex 第二意見）。
- **風控**：判定上表各項；定稿退役通知；判定心跳釐清要不要讓 CEO 知悉。

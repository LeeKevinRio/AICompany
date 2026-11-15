# NM-5 第四批解讀確認與 CG-2 正式登記方式裁示（ADR-0030 補充四）

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
- 第 1 題的四處解讀 (a)～(d) 我都接受，(a)、(b) 再收窄範圍。
- 第 2 題可以用一鍵檔，但要分兩段：先跑只讀的預檢檔，再跑登記檔。寫入只能走 CLI 新增的 `bootstrap --production`。建表和兩列登記放在同一個交易裡。
- 第 3 題的順序：第五批（`report.py`＋harness）→ CG-2 登記 PR → CEO 在本機執行 → 接線 PR。
- 要補 ADR-0030 補充四，全文在文末。

## 各部門回報（tech-architect）

**1. 四處解讀**
- **(a) 接受，收窄。**
  - 裁示：只豁免 `app/outlook/missing.py` 裡 `MissingItem` 類別內的 `self.source_status`。
  - 理由：這個欄位是 D-13 的缺項欄位，不是快照的 DataStatus。第四批已有測試：4 種 DataStatus 配同一組 bars，`missing_json` 逐位相同，可以佐證兩者沒有相連。
  - qa 檢查：豁免條件要同時比對模組和類別。牙齒測試：在其他類別或其他模組寫同名屬性，仍然會被抓。
- **(b) 接受，收窄。**
  - 裁示：`try` 只能包住 `compute_outlook` 和 `_record_content`，不能包到帳本讀取或解析，也不能捕捉 `BaseException`。
  - 理由：凡是「目前的程式重算不出來」，都屬於 SemanticsChanged，結果一樣是 fail-closed，下一次執行還是會重算。
  - qa 檢查：AST 確認 handler 內只有這兩個呼叫；帳本端的失敗仍然記 `error`。
- **(c) 接受。**
  - 理由：補充三（修訂版）第 2 點本來就要求這項；`runtime_json` 也納入比對，跟第 1 點的比對基準一致。
  - qa 檢查：三種情形各恰好一行 WARNING，outcome 與 `content_hash` 不變（第四批已有測試）。
- **(d) 接受。**
  - 理由：ADR-0027 D-10 已依 D-8 第 3 點凍結。N-84 管的是「缺日義務從哪天開始算」，屬於驗證層。第 2 題的 bootstrap 規定登記前主 DB 不能有任何 forecast 表，所以第一次登記一定早於任何 `forecast_run`。日後要取代 claim 而修訂 ADR 時，再一併定缺日起點。
  - qa 檢查：程式裡沒有 N-84 拒絕邏輯；FL-78 (i) 的兩項檢查都指向 `app.advice.banned_phrases`。

**2. CG-2 正式登記**
- **(i) 執行者與順序。**
  - 裁示：CG-2 PR 合併後，由 CEO 先雙擊預檢檔（只讀），把結果貼回，經 coordinator 核對；再雙擊登記檔。登記檔依序做：重跑全部預檢 → 用 SQLite backup API 取得主 DB 一致備份（就是 CG-3 要的那份）→ 禁詞比對 → `bootstrap` → 輸出回傳文字。接著 coordinator 當日 commit `work/` 登記紀錄，接線 PR 最後才合併。
  - 理由：R2 一鍵檔只碰副本，這次是第一次寫正式主 DB，所以多一道只讀預檢。一鍵檔本身不開寫入連線，寫入只走 CLI。
  - **已發現的阻擋風險**：`.gitattributes` 沒有為 `.yaml`、`.md` 設 eol。CEO 的 Windows 若開著 autocrlf，工作樹裡的 YAML 會是 CRLF，`get_rules_bytes` 的雜湊核對會失敗。這不只卡登記，日後 recorder 執行時也會一直 `gate_closed`。所以要加 eol 屬性，預檢也要回報 `git ls-files --eol`。
  - qa 檢查：補充四第 5 點的 R-1～R-8 逐條都有測試或 STOP 訊息。
- **(ii) CLI 怎麼開放正式路徑。**
  - 裁示：新增子命令 `bootstrap`，必須帶 `--production`，而且五個條件同時成立：目標是預設路徑的主 DB；沒有設定 `STOCK_DESK_DB_PATH`；主 DB 沒有任何 `forecast_`／`plan_` 開頭的表；一次給齊 h3、h5 兩個 claim；沒有 `replaces_claim_id`。`register` 對正式路徑維持一律拒絕。
  - qa 檢查：每個拒絕條件各一個測試；第二列登記失敗時，主 DB 不留任何 `forecast_` 物件；recorder 遇到沒有 schema 時拒絕執行，不自行建表。
- **(iii) `prereg_doc_path` 格式。**
  - 裁示：採用 dev-lead 的建議，用 repo 相對路徑，以 `/` 分隔，不合格式就拒絕，不自動轉換。另外必填 `--prereg-doc-sha256`，CLI 讀到的位元組必須與它一致。
  - qa 檢查：要有以下拒絕測試：`\`、`..`、`./`、絕對路徑、磁碟代號，以及 sha256 不一致。
- **(iv) 要固定的值與檢查點**：見補充四第 5 點。合併前是 M-1～M-9，登記前是 R-1～R-8。

**3. 剩餘順序**
- 裁示：
  - `report.py` 和 D-7 harness 可以合成同一批。兩者受同一組 D-4 輸出約束，harness 也要用到 `report verify`。
  - CLI 正式路徑、一鍵檔和登記值放在 CG-2 PR，不另拆。
  - 接線 PR 不能和 CG-2 PR 合併，也不能早於 CEO 執行完。原因是 `dev-up.bat` 會 `git pull` 並啟動 scheduler；接線一旦先合併，排程第一次跑時可能先建表，違反 CG-3。
- 理由：登記要排在 harness 通過之後。如果 harness 發現管線缺陷而必須取代 claim，m 會增加（依 RC-155，登記過的 claim 一律計入）。
- qa 檢查：接線 PR 合併時，`work/` 裡已有登記紀錄 commit。

## 驗證
- 讀過的檔案：
  - 第四批交件報告
  - ADR-0030 全文（含補充一～三修訂版）
  - ADR-0027 中 N-84 相關段落
  - 風控 RC-150～RC-157
  - R2 一鍵檔的合併紀錄、腳本、`.bat`、CEO 回傳結果
  - `/home/user/AICompany/.gitattributes`
- 第四批程式在遠端 `c4e0361e`，我沒有讀，以交件報告為準。我沒有 Bash，所以沒有執行任何程式或雜湊計算。沒有讀 `.env`，也沒有碰 `*.db`。

## 下一步
- **需 CEO 1：怎麼執行正式寫入。**
  - A（推薦）：兩段式，先預檢檔、再登記檔。
  - B：單一一鍵檔，執行前要求鍵入確認字。
  - C：依文字步驟手動操作。
- **需 CEO 2：`provisional_results_seen` 的值。**
  - 推薦：登記前不看 harness 輸出，就可以如實填 0。
  - 另一做法：看了就填 1，日後報告照實揭露。
- **需 CEO 3：** 待決 #7 若還沒裁示，推薦 harness 用佔位規則 P-0、P-1。
- tech-writer：把下面的補充四 append 到 `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`，並在檔頭補一行補充紀錄。
- devops-sre：確認 CEO 那台 Windows 的 `core.autocrlf` 設定；如果 YAML 或文件已經是 CRLF，設計另一個獨立的修復步驟，不要放進登記檔。
- dev-lead：第五批做 report＋harness；CG-2 PR 照補充四實作。CG-2 PR 會換成真實的 dirdef-v1.0，現有 `test_the_k2_move_keeps_the_three_hashes` 釘的 G7 替身 definition 雜湊要跟著更新。

---

**ADR-0030 補充四全文（可直接 append）**

## 補充四：第四批解讀確認、正式登記（CG-2／CG-3）的執行方式、剩餘順序（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-NM5第四批交件-dev-lead.md` 下一步第 1、3 點。
- 性質：釐清補充三（修訂版）第 2、5、8 點與 D-6 CG-2、CG-3；收緊正式路徑的寫入條件。不改使用者面字面，不改規則檔與定義物件的雜湊。CEO 可推翻；第 4 點的執行方式須 CEO 同意。

1. **解讀確認**
   - (a) 補充三（修訂版）第 5 點的禁令，對象是快照的 `source_status`。`app/outlook/missing.py` 中 `MissingItem` 類別內的 `self.source_status`（D-13 缺項欄位）不在禁令內；豁免只限這個模組的這個類別。
   - (b) 第 8 點的「目前程式重算失敗」，涵蓋純計算呼叫拋出的任何 `Exception`。`try` 不得包住帳本讀取與解析，也不捕捉 `BaseException`。
   - (c) 第 2 點的磁碟重算涵蓋 `code_digest` 與 `runtime_json`，可以在接線 PR 之前落地；scheduler 的 AST 檢查仍在接線 PR 套用。
   - (d) ADR-0027 D-10 第 3 點（含 N-84 暫行限制）屬 D-8 凍結附錄，不實作。FL-78 (i) 的禁詞來源讀為 `app.advice.banned_phrases`。第一次登記早於任何 `forecast_run`，由第 2 點保證。日後依 D-1 第 2 點修訂本 ADR 以取代 claim 時，須一併定新 claim 缺日義務的起點。
2. **正式路徑**
   - 正式主 DB 唯一的登記路徑是 `python -m app.forecast.claims bootstrap --production`。`register` 對正式路徑維持一律拒絕。
   - `bootstrap` 須同時成立以下條件，任一不成立就以結束碼 4 拒絕，不寫入：
     - 目標是 `<backend>/data/stock-desk.db`；
     - 環境變數與 `apps/stock-desk/.env` 都沒有設 `STOCK_DESK_DB_PATH`；
     - 主 DB 沒有任何 `forecast_`、`plan_` 開頭的表；
     - 一次給齊 D-1 第 1 點的 h3、h5 兩個 claim，依此順序；
     - `replaces_claim_id` 為空。
   - schema 的全部物件與兩列登記放在同一個寫入交易內，任一步失敗就全部回滾。提交後以唯讀連線確認：`schema_status` 完整、登記表恰好 2 列、`forecast_run` 為 0 列。
   - 正式主 DB 上的核心 schema 只能由 `bootstrap` 建立。其他路徑遇到 schema 不存在時拒絕寫入，不建表。
   - 登記表非空之後，正式路徑沒有任何登記方式。
3. **`prereg_doc_path`**
   - 格式：repo 根目錄起算的相對路徑，以 `/` 分隔；不得含 `./`、`..`、`\`、磁碟代號，也不得是絕對路徑。不合格就拒絕，不自動轉換。`review_refs` 用同一格式。
   - `prereg_doc_blob` 是該路徑在 `frozen_commit` 的 git blob 原始位元組。CLI 須核對 `--prereg-doc-sha256`，不一致就拒絕。
4. **執行者與順序**
   - (1) CG-2 登記 PR 合併。
   - (2) CEO 在本機先執行只讀的預檢檔，回傳結果經 coordinator 核對後，再執行登記檔。登記檔重跑全部預檢，然後依序：
     - 以 SQLite backup API 取得主 DB 一致備份：放在 git 工作樹之外，`integrity_check` 為 ok，記下 sha256；
     - 禁詞比對；
     - `bootstrap`；
     - 輸出回傳內容。

     任一步不成立就停止。回傳內容只含固定文字、計數、雜湊、commit 與時間，不含路徑與代號。一鍵檔不開寫入連線。
   - (3) coordinator 當日以 commit 在 `work/` 記錄 `claim_id`、`registered_at`、`frozen_commit` 與備份 sha256。
   - (4) 接線 PR 在 (3) 之後才合併，記下 CG-3 備份路徑（以家目錄相對寫法）與 sha256。
5. **檢查點**
   - 合併前：
     - M-1：第四、五批已 qa PASS 並合併；D-7 harness 已執行。
     - M-2：事先宣告 v0.32 的路徑、blob id、`git cat-file blob <commit>:<path>` 的 sha256 都寫進 PR；RC-153～RC-157 套用之後，此檔沒有任何變更。
     - M-3：C-8 紀錄檔依 RC-152 第 1 點計算，PR 寫出指令與 commit SHA；風控確認之後沒有任何變更。dirdef-v1.0 的 C-8 雜湊欄等於此值。
     - M-4：`dirdef-v1.0` 登記於 `PUBLISHED_DIRECTION_DEFINITIONS`；兩個 definition 雜湊寫進 PR，並以測試釘住。
     - M-5：h3、h5 登記於 `PUBLISHED_RULESETS`，`OUTLOOK_RULE_FIELDS` 已設定；四個規則雜湊以測試釘住。
     - M-6：禁詞比對輸出附在 PR，命中 0。
     - M-7：YAML 與 M-2、M-3 兩份文件加上 `eol=lf` 屬性，PR 附上 `git ls-files --eol` 的輸出。
     - M-8：一鍵檔以常數固定 M-2～M-5 的雜湊；測試涵蓋第 2 點每個拒絕條件、整筆回滾，以及回傳內容不含路徑。
     - M-9：qa PASS（含 Codex）；風控核對 M-2、M-3、M-6；CI 綠燈；`report verify --all` 一致。
   - 登記前（一鍵檔機械核對，任一不成立就停止）：
     - R-1：`HEAD` 可由 `origin/product/stock-desk` 到達；`HEAD` 與 CG-2 合併 commit 之間，`app/` 與兩份文件沒有 diff，且這些路徑的工作樹乾淨。`frozen_commit` 取 `HEAD`。
     - R-2：每個凍結檔的工作樹 sha256 等於 blob 的 sha256，也等於 M-8 的常數。
     - R-3：port 8000 沒有監聽；沒有設 `STOCK_DESK_DB_PATH`；主 DB 存在於預設位置。
     - R-4：主 DB 沒有 `forecast_`、`plan_` 開頭的表。
     - R-5：備份的 `integrity_check` 為 ok，備份內沒有 `forecast_` 表。
     - R-6：禁詞比對命中 0。
     - R-7：`bootstrap` 結束碼 0，提交後的核對成立。
     - R-8：`provisional_results_seen` 由 CEO 鍵入。
6. **剩餘順序**
   - 第五批 `report.py`＋D-7 harness（同一批）→ CG-2 登記 PR（含 CLI 正式路徑、一鍵檔、登記值）→ 第 4 點 (2)、(3) → 接線 PR。
   - CG-2 登記不得早於 harness 通過。接線 PR 不得與 CG-2 PR 合併。

- **S-14a（逐條可檢查）**：第 1 點各款各有 AST 或測試；第 2、3 點每個拒絕條件各一個測試；整筆回滾測試；M-1～M-9 列在 CG-2 PR 說明中；R-1～R-8 各有對應的 STOP 訊息測試；接線 PR 合併時，`work/` 中已有登記紀錄的 commit。

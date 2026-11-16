# CG-2 登記 PR 三點、M-7 與 qa 三項裁示

- 審查者：tech-architect
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

六點加 qa 三項，裁示如下。

1. **接受**不在 `claims.py` 做 `mode=ro` 提早檢查，附記第 3 點的字面要更正。要求改 `store.py` 的方案否決：`store.py` 不在 (d) 允許的差異內，會讓 harness 通過失效、CEO 驗收得重跑，也違反補充七第 7 點「store 改動只在前置 PR」。放寬 K-4 測試同樣否決。
2. **容許**白名單加那一行。限定條件是 diff 恰好一行，而且只能是例外類別，不能是 `create_objects`、`create_schema` 這類可呼叫的寫入入口。
3. **在 (d) 允許範圍內。** harness 只呼叫 `claims.production_path_refusal` 和 `claims.register`（harness 第 195、444 行）；`register` 不會呼叫 `_parser` 或 `main`，所以這兩個不在遞移呼叫集合內。那 5 行就是 (d) 所說的「CLI 分支」。coordinator 說的「既有頂層函式只能新增」比 ADR 嚴，以 ADR 為準。
4. **M-7**：屬性分三處放，都只存在於產品分支，`work/.gitignore` 不必改（寫法見附記第 5 點）。加屬性不改 blob，也不違反 M-2、M-3。
5. **docstring**：允許 CG-2 PR 改，但只限模組 docstring，而且要寫成不依登記狀態的寫法。這比 (d) 字面寬，已標明。
6. **merge commit 沒有署名行**：對 ADR 與各項驗證沒有影響，因為沒有任何核對依賴 commit 訊息。不 amend，在 PR 說明揭露即可。
7. **qa 三項**：
   - 第 1 項：commit 之後的任何 `Exception`，一律轉成固定句加結束碼 5。這是要修的地方，屬 `bootstrap_main` 內的新增，在 (d) 範圍內。
   - 第 2 項：在 `claims.py` 內處理，不交給外層。
   - 第 3 項：CLI 不加檢查，由一鍵檔的 R-1、R-2 負責，但要釘死取值方式。

以上沒有一項動到 `store.py`、`schema.py` 或 harness 那幾個檔，**CEO 的驗收不必重跑**。

## 各部門回報（tech-architect）

**兩處提醒清單矛盾，以下為準**
- 先前清單第 3 項的「預期外例外不捕捉」，只適用 commit 之前（交易回滾、沒有寫入）。
- 自定解讀第 5 項的「核對中任何例外都回 5」，適用 commit 之後。

**比字面寬的讀法（三處）**
- 第 1 點：拒絕時會開一條寫入連線再回滾。主 DB 若殘留 `-wal`，可能在這時被 checkpoint，邏輯內容不變。
- 第 4 點：`.gitattributes` 列入 (d) 允許的差異。
- 第 6 點：(d) 允許改 `claims.py` 的模組 docstring。

三處都不碰使用者面字面、RC 條件或 M-2、M-3、M-6 的值，所以**不需要送風控**。建議 coordinator 告知風控一聲，說明 M-2、M-3 的 blob 不變。

**落檔附記**（交 tech-writer）

檔頭一行：
```
- 補充紀錄：2026-11-16 append 補充七附記二（附記第 3 點 `mode=ro` 字面更正、claims.py 白名單與補充六第 6 點 (d) 範圍的確認、提交後例外、`git_blob` 環境、M-7 屬性位置、claims.py 模組 docstring；tech-architect 裁示，字面更正與釐清，第 1、5、6 點窄幅寬於字面已標明，不改 store.py、schema.py、harness 三檔、使用者面字面、規則檔、定義物件與已登記雜湊；CEO 可推翻；來源 `work/reviews/2026-11-16-CG2登記PR第二段交件-dev-lead.md`、`work/reviews/2026-11-16-CG2登記PR審查-qa-reviewer.md`）。
```

檔尾一章：
```
---

## 補充七附記二：`mode=ro` 字面更正、claims.py 的 (d) 範圍、提交後例外、`git_blob` 環境與 M-7（2026-11-16）

- 決策者：tech-architect。來源：`work/reviews/2026-11-16-CG2登記PR第二段交件-dev-lead.md`、`work/reviews/2026-11-16-CG2登記PR審查-qa-reviewer.md`；另讀 `feat/nm5-cg2-registration`（`2ce29a9c`）的 `app/forecast/claims.py`、`tests/forecast_pipeline_harness.py`、`tests/test_forecast_boundaries.py`、`apps/stock-desk/backend/.gitattributes`、`work/.gitignore`。
- 性質：更正補充七附記第 3 點字面；釐清補充六第 6 點 (d)、補充四 M-7 與 R-2。第 1、5、6 點比原字面窄幅放寬，已逐點標明。與補充七、補充七附記衝突時以本附記為準。CEO 可推翻。

1. **附記第 3 點更正（窄幅寬於字面）**：刪除「檢查 `forecast_`、`plan_` 表時只用 `mode=ro` 的唯讀 URI」。改為：claims.py 不自行開任何 SQLite 連線；這項條件只由交易內的 `create_objects` 判定，拋 `SchemaNotEmptyError` 時結束碼 4。提早停止只由登記一鍵檔的 R-4 做：`mode=ro` 連線，判定規則與補充七第 3 點相同（任何物件的名稱或所屬表，不分大小寫以兩個前綴開頭）。理由：K-4 測試與補充七第 6 點不放寬，store.py 不在 (d) 內；交易外的檢查本來就有 TOCTOU，以交易內為準。放寬處：被拒絕時，claims.py 會在主 DB 上開一次寫入交易再回滾；主 DB 若殘留 `-wal`，可能在這時被 checkpoint，邏輯內容不變。R-4 先執行，補充四第 4 點的備份也先取得，所以接受。「不寫入」讀為沒有任何邏輯寫入。
2. **import 白名單**：`tests/test_forecast_boundaries.py` 的 claims.py import 白名單加列 `app.forecast.schema.SchemaNotEmptyError`，這是補充七第 5 點的直接結果，予以容許；性質同補充七附記第 2 點。限制：diff 恰好一行；只能 import 例外類別；同檔其他斷言不得改動。
3. **(d) 的 claims.py 範圍**：harness 只呼叫 `production_path_refusal` 與 `register`。遞移集合為 `register`、`production_path_refusal`、`_phrase_scan_lines`、`_same_file`、`claim_id`、`count_m`、`m_eff`、`RegistrationRefused`，必須 AST 相同。`_parser` 與 `main` 不在集合內：它們內含的子命令分派屬「CLI 分支」，新增的頂層 import 屬「新增的頂層定義」。限制：`_parser` 只增 `_add_bootstrap_parser(commands)` 一行；`main` 只在 `parse_args` 之後增加 `bootstrap` 的分派；`register` 子命令的既有路徑 AST 不變。
4. **提交後例外**：`store.bootstrap` 回傳之後，到印出成功輸出為止（核對與組輸出都算），任何 `Exception` 一律只印 `POST_COMMIT_CHECK_FAILED` 固定句，以結束碼 5 結束，不重試，不印例外文字。`BaseException` 不捕捉（同補充四第 1 點 (b)）；一鍵檔把任何非 0 結束碼都視為 STOP。commit 之前的預期外例外仍不捕捉，交易已回滾。本點屬 `bootstrap_main` 內的新增，在 (d) 範圍內。
5. **M-7 屬性位置（釐清 (d)）**
   - `apps/stock-desk/backend/.gitattributes` 加兩行：`/app/outlook/rules/h3.yaml text eol=lf`、`/app/outlook/rules/h5.yaml text eol=lf`。`uv.lock` 那一行不動。
   - 新增 `work/research/.gitattributes`，只有一行 `/2026-10-15-3日5日方向判斷-事先宣告草案.md text eol=lf`。新增 `work/dispatch/.gitattributes`，只有一行 `/2026-11-15-C8決策紀錄-F2B.md text eol=lf`。這兩個資料夾已由 `!research/**`、`!dispatch/**` 放行，`work/.gitignore` 不改。
   - repo 根目錄的 `.gitattributes` 不改。上述三檔只存在於產品分支。
   - 四檔目前是 `i/lf`，加屬性不改它們的 blob，所以 M-2、M-3 的「沒有任何變更」仍然成立；`uv.lock` 維持零差異。這三個 `.gitattributes` 列入 (d) 允許的差異。
6. **claims.py 模組 docstring（窄幅寬於 (d) 字面）**：CG-2 PR 可以改 claims.py 的模組 docstring（`tree.body[0]`），改成不依登記狀態的寫法：寫出 `bootstrap --production` 與結束碼 0、2、3、4、5；不寫任何雜湊、`claim_id` 或「已登記／未登記」字樣。理由：前置 PR 依補充七第 7 點要求 claims.py 零差異，所以這份 docstring 沒被一併改正。前置 PR 改過的四個 docstring 仍不得再改。
7. **`git_blob`**：claims.py 呼叫 git 時，傳入的環境要先移除所有以 `GIT_` 開頭的變數，並加 `--no-replace-objects`；`cwd` 維持 `<backend>`。
8. **`--frozen-commit`**：CLI 只驗格式，以及 prereg blob 的 sha256。規則檔位元組與 `frozen_commit` 的綁定，由一鍵檔負責：`--frozen-commit` 必須是同一次執行中 R-1 取得的 `HEAD`；R-2 的凍結檔包含 h3、h5 兩份 YAML。
9. **R-2 的換行證據**：每個凍結檔都要核對三項：工作樹原始位元組 sha256 等於 blob sha256，也等於 M-8 常數；`git ls-files --eol` 為 `i/lf w/lf attr/text eol=lf`；`git check-attr eol` 為 `lf`。任一不符就 STOP，不改 git 設定，也不改檔；補救限 `git checkout HEAD -- <path>`。

- **S-15b（逐條可檢查）**
  - 第 1 點：claims.py 沒有 `connect`、`execute`（既有測試不改）；R-4 判定規則與交易內相同（一鍵檔測試）。
  - 第 2 點：該測試檔對 product 的 diff 只有一行。
  - 第 3 點：PR 附上遞移集合的 AST 比對輸出，以及 `_parser`、`main` 的 diff。
  - 第 4 點：在核對中與組輸出中各注入 `sqlite3.OperationalError` 與 `RuntimeError`，結束碼 5，stderr 恰為固定句，stdout 為空（測試）。
  - 第 5 點：PR 附上四檔加 `uv.lock` 的 `git ls-files --eol` 輸出，以及四檔 blob id 與 M-2、M-3、`git_head` 相同的證據；`git check-ignore` 對兩個新 `.gitattributes` 不命中。
  - 第 6 點：AST 比對中，claims.py 除了第 3 點所列與新增的定義之外，只有 `body[0]` 不同。
  - 第 7 點：設了 `GIT_DIR` 指向另一個 repo 時，`git_blob` 仍取得本 checkout 的 blob（測試）。
  - 第 9 點：一鍵檔的 R-2 在 CRLF 工作樹判 STOP（測試）。
```

**交件中的其他事項**
- 三點都是收緊或局部修正，沒有一點否決 dev-lead 的做法。
- merge commit `cba794b` 沒有署名行，請在 PR 說明揭露。之後同步 product 時，用 `chore: 合併 origin/product/stock-desk` 的訊息加署名行。

## 驗證

- 我只讀檔，沒有執行任何指令。
- 讀過的檔：ADR-0030 的補充四、補充六到補充七附記；`claims.py` 第 1～70、214～269、400～631 行；harness 的 import 段與呼叫點；`tests/test_forecast_boundaries.py` 第 1020～1078 行；兩份 `.gitattributes`；`work/.gitignore`；我先前清單的相關段落。
- 已確認 `claims.py` 第 539 行的 `post_commit_check` 呼叫沒有任何 `try`，和 qa 第 1 項描述的一樣。
- 沒有逐檔核對 `git ls-files --eol`、blob id 和 AST 比對，這些交給 dev-lead 附在 PR 說明，再由 qa 核對。
- 沒有讀 `.env`，也沒有碰任何 `*.db`。

## 下一步

1. tech-writer：把上面兩個區塊落檔進 `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`。
2. dev-lead：在同一分支照附記第 4、5、6、7 點補 commit，並附 S-15b 要求的證據。改完由 qa 複審這幾個 commit（含 Codex）。
3. devops-sre：在一鍵檔落實附記第 1 點的 R-4、第 8 點的 `--frozen-commit` 取值、第 9 點的 R-2。
4. CEO 的驗收照常進行，不必重跑。合併前用 CEO 那一次的 `git_head` 重做 (d) 比對，比對時套用附記第 3、5、6 點。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-16-CG2登記PR第二段交件-dev-lead.md`
- `/home/user/AICompany/work/reviews/2026-11-16-CG2登記PR審查-qa-reviewer.md`
- `/home/user/AICompany/work/reviews/2026-11-16-前置PR字面不符判定與CG2提醒清單-tech-architect.md`
- `/home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/app/forecast/claims.py`

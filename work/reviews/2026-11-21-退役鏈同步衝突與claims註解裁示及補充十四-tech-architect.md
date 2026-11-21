# 登記一鍵檔退役鏈同步衝突、claims.py 註解處理與補充十四草稿

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 裁示：登記一鍵檔退役鏈同步 CG-2 新 head 的衝突（2026-11-21）

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔，沒有執行 git、uv 或 pytest，沒有讀任何 `.env*`，也沒有碰 `backend/data/`。

先更正派工單的一處事實。**CG-2 一鍵檔退役的 ADR 依據是補充九第 1 點和 S-19a，不是補充十一。**
- 補充九的條文在 `work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md` 第 112～203 行。
- 補充十一是「CEO 讀取執行狀態的途徑」，全文沒有提到 CG-2 退役（組版檔 `work/reviews/2026-11-20-補充十一草稿-待風控-coordinator組版.md`）。
- 下面第 4 題照這個事實作答。

---

## 一、本次結論

1. **第 1 題（4 個 modify/delete 衝突）**
   - 【裁示】照退役原意，4 個檔都保留刪除。
   - 【事實】`claims.py` 這一端的保護仍在。`tests/test_forecast_claims_bootstrap.py` 不在退役清單裡，上游加的 +35 行會自動合併進來。
   - 退役後不需要補測試。理由是：消失的那支相等斷言，保護的是「兩份副本相同」；其中一份刪掉以後，這件事本身就不存在了。
2. **第 2 題（`claims.py:293` 的註解）**
   - 【裁示】採 (a)：在退役 PR 裡另開一個 commit，刪掉那一句註解。
   - 這和補充九第 1 點「不改 `app/`」、S-19a「`app/` 零差異」的字面衝突，所以另立**補充十四**做窄幅放寬（全文見下）。
   - (b) 和 (c) 都否決。(c) 不可行：不用 skip 或 xfail 的話，只能在守門測試裡開例外，也就是 (b) 加上之後再清一次。
3. **第 3 題（要不要回頭改 CG-2）**
   - 【裁示】不回頭改。CG-2 的 M-9（qa PASS_WITH_NOTES、風控 RC-507～RC-511）和登記本身都不受影響。
4. **第 4 題（重做 merge 與組版字面）**
   - 【裁示】先重做分支 1：保留刪除，再補一個註解 commit。分支 2 改 merge 分支 1 的新 head，不直接 merge `cc9e302`。
   - 補充十一不用改。補充十二不用改，B1～B5、F1～F10 的字面都不動，所以不必為此送風控。
   - 新增的補充十四要在退役 PR 合併前 append。
5. **第 5 題（失效引用）**
   - 【裁示】歷史紀錄一律不改寫，以追蹤清單為準。追蹤清單第 732 行的處理我確認是對的。
   - 另外要加記一件事：`32725eb8…` 也只是暫定值，退役合併後接線 PR merge product 時還會再變一次。
6. **有沒有必須由 CEO 決定的事：沒有。**

---

## 二、各部門回報（tech-architect）

### 第 1 題：4 個 modify/delete 衝突

**裁示**
- `scripts/cg2_register.py`、`tests/test_cg2_register_addendum3.py`、`tests/test_cg2_register_flow.py`、`tests/test_cg2_register_values.py` 一律以刪除解決。
- 上游 `cc9e302` 對這 4 個檔的修正會隨刪除一起消失，包括：
  - `ENV_KEY_PATTERN` 新 regex；
  - tree id 重釘成 `d631a75a…`；
  - `review_refs` 加的兩條；
  - cg2 端的正反例；
  - `test_r3_the_key_pattern_is_the_one_of_the_claims_module`。

**理由**
- 補充九第 1 點已列舉這些退役對象，並禁止以 skip、xfail、只刪單一測試或重釘常數代替。
- 登記時實際執行的，是 CG-2 合併 commit 上含修正的版本。稽核依補充九第 1 點以 git 歷史為準，可以用 `git show` 取回 `cc9e302` 或 M 上的版本。

**退役後 `claims.py` 的 pattern 還有沒有保護**（【事實】讀自 `.claude/worktrees/agent-a16d399220753e66d/apps/stock-desk/backend/tests/test_forecast_claims_bootstrap.py`）
- 第 323～373 行都保留：
  - `ENV_FILE_KEY_LINES` 共 7 個正例：`export`＋空白、`export`＋tab、前導空白＋`export`＋`=` 前空白＋空值、小寫、大小寫混合、`EXPORT`、`Export`＋混合大小寫。
  - 另有 3 個基本正例：`KEY=`、前後空白、BOM。
  - `ENV_FILE_OTHER_LINES` 共 6 個反例：`# KEY=`、`  # export KEY=`、`X_…=`、`…_X=`、`export X_…=`、`exportSTOCK_…=`。
  - 反例測試除了斷言 `env_file_sets_db_path(...) is False`，也斷言 `main` 回傳 `EXIT_OK`。
  - 第 362 行還有一支「沒有這個鍵就不拒絕」的測試。
- 這些就是 (甲) 約束 2、3、7 在 claims 端的全部要求，退役不會縮小任何一項。
- 【事實】這個測試檔不含任何會被退役守門 regex 或補充十二 (e) grep 命中的字樣（Grep 確認）。
- 【推論】消失的只有 cg2 端的測試和相等斷言。它們保護的是 `cg2_register.py`，不是 `claims.py`。

**還要不要補測試**
- 【裁示】退役 PR 不補任何測試。補了就會擴大退役 PR 的範圍，也沒有填補任何因退役產生的缺口。
- 【建議】有一個本來就存在的小缺口，列進 backlog（low），不擋退役：
  - claims 端沒有「值裡含鍵名」（`OTHER=STOCK_DESK_DB_PATH`）的反例，cg2 端原本有。
  - 【推論】依 regex 結構（`^` 錨定），這種行不會被比對到，所以風險很低。
- 【建議】`scripts/r2_first_run.py` 仍是舊 regex（原本就另列追蹤，devops-sre）。日後修它的時候，在它自己的測試裡加上和 `claims._ENV_FILE_KEY` 相等的斷言。

### 第 2 題：`claims.py:293` 的註解

**事實**
- CG-2 worktree 上，`claims.py` 第 290～294 行如下：
  - 第 292 行結尾是「`… ignore case. The pattern and`」；
  - 第 293 行是「`#: flags equal ``ENV_KEY_PATTERN`` of ``scripts/cg2_register.py`` (a test keeps them equal).`」。
- 守門 regex `cg2_register(?!s)|…` 只排除守門測試本身（`test_the_scan_covers_this_folder_and_excludes_only_this_file` 也釘住這一點），所以第 293 行一定會被掃到。
- 補充九第 1 點寫的是「以獨立 PR 一次刪除，不改 `app/`」。S-19a 第 1 點同時要求兩件事：
  - 「`app/` 零差異」；
  - 「在 `apps/stock-desk`（`work/` 除外）以 grep 查不到」退役檔名。
- 這行註解進來之後，S-19a 的這兩個條件**不可能同時成立**。不論選哪一案，都要動 ADR 的字面或讀法。
- 根本原因在我自己的 (甲) 約束 5 允許「必要時加上它的註解」，卻沒有對照 S-19a 的 grep 條件。這個疏漏由我承擔。

**登記後 `app/forecast` 變動的後果**（(a) 與 (c) 都會遇到）
- 【事實】`claims.py` 沒有存 `code_digest` 或 tree id（Grep 只有 `frozen_commit`）。`tests/test_cg2_registration_values.py` 也不含 `code_digest`、tree 或 `claims.py`。所以已登記的值與雜湊不受影響。
- 【事實】D-5 第 6 點是在 recorder 執行時觸發：本次 `code_digest` 和前一次執行不同，就重算既有紀錄。補充三（修訂版）第 1 點規定，沒有通過執行時視為不同。
- 【推論，證據強】退役 PR 在接線 PR 之前合併，主 DB 裡還沒有任何 `forecast_run`。依據是追蹤清單第 655、662 行，以及 RC-331 那次「第一筆 `forecast_run` 之前改，不觸發 D-5 第 6 點」的前例。所以重算的對象是零筆，不會出現 `gate_closed`。
- 【推論】即使已經有紀錄，只改註解時 AST 完全相同，重算結果應該逐位相同，代價只是下一次執行多做一次重算。
- 【事實】RC-507 (2) 的 tree id 核對只針對 CG-2 合併 commit M，退役之後的 tree id 改變不影響它。
- 【事實】`test_r1_…` 會在同一個退役 PR 裡被刪掉，所以 product 上不會出現 R-1 紅燈。
- 和接線 PR 的 `code_digest` 管理**不衝突**：
  - repo 裡沒有任何程式或測試釘住接線版的值（追蹤清單第 662 行）；
  - 補充九第 1 點本來就要求接線 PR 先 merge 退役、再合併，到時本來就要重算。
  - 差別只是 `32725eb8…` 會再被取代一次。

**方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **(a) 退役 PR 刪掉那一句（採用）** | 讓註解失效的 PR 自己修掉它；守門測試和 S-19a 的 grep 不用開任何例外；產品程式碼裡不會留下不實的說明；AST 相同，可以機械證明「程式行為不變」（補充九第 2 點） | `app/` tree id 和 product `code_digest` 改變；要另立補充十四放寬「不改 `app/`」；接線版 `code_digest` 要多記一次 | 低：發生在第一筆 `forecast_run` 之前，沒有可重算的紀錄 |
| (b1) 守門測試排除註解行 | `app/` 零差異 | 守門測試明顯變弱：任何檔案的註解都可以引用退役檔，而且「註解」在 `.py`、`.bat`、`.md` 裡定義各不相同；S-19a 的 grep 照樣命中，仍要修 ADR | 守門測試失去牙齒 |
| (b2) 守門測試只排除 `claims.py` 這一行 | 範圍窄，可以斷言那一行存在 | 產品程式碼會一直留著一句不實的話（「有測試讓兩者相等」），誤導日後維護的人；例外和那一行綁在一起，日後有人動註解，守門測試就會紅；S-19a 的 grep 照樣命中，仍要修 ADR | 長期技術債 |
| (c) 由接線 PR 修註解 | 接線本來就會改 `app/forecast` | 退役 PR 先合併，合併當下那一行還在；不用 skip 或 xfail，就只能先做 (b2)，再由接線 PR 清掉，等於 (b2) 加二次清理；接線 PR 會多出 `claims.py` 和退役守門測試兩個語意，W-7 和 S-20a 的零差異證明都要改寫；接線版 `code_digest` 一樣會變；順序也不能倒過來（接線要等退役，才能消掉 R-1） | 否決 |
| (d) 回頭改 CG-2 | 退役 PR 維持純刪除，ADR 不用動 | 見第 3 題 | 否決 |

**裁示與約束**（逐條可查）
1. 退役 PR 對 `app/` 只能有這一處變動：
   - `app/forecast/claims.py` 第 292 行刪去行尾的「` The pattern and`」；
   - 刪除第 293 行；
   - 其餘行不動，也不新增任何字。
   - 改完後該段是三行，最後一行是 `#: uv loads ``export KEY=`` lines, and Windows environment names ignore case.`。
2. `claims.py` 全模組的 `ast.dump`，要和 merge-base 上的版本相同（附輸出）。
3. `env_file_sets_db_path` 過時的 docstring（qa 備註 1）**不得**順手修。docstring 屬於 AST，修了第 2 點就不成立。它繼續留在 backlog。
4. `tests/test_oneclick_retirement.py` 零差異，`RETIRED_REFERENCE`、`NOT_A_REFERENCE` 和排除條件都不改，而且要實際跑過、全綠。
5. `tests/test_cg2_registration_values.py`、`tests/test_forecast_claims_bootstrap.py` 對 merge-base 零差異。
6. PR 說明附上新的 `app/` tree id 和新的 product `code_digest`，並寫明「依補充十四」。

**補充十四（可逐字寫入，排在補充十三之後）**

檔頭補充紀錄行：

- 補充紀錄：2026-11-21 append 補充十四（CG-2 一鍵檔退役 PR 對 `app/forecast/claims.py` 一句過時註解的處理；tech-architect 裁示；窄幅寬於補充九第 1 點「不改 `app/`」與 S-19a 第 1 點「`app/` 零差異」的字面，已標明；不改本文、補充八～十三的字面、事先宣告 v0.32、規則檔、定義物件與已登記雜湊；不改任何 CEO 可見字面；CEO 可推翻；來源 `work/reviews/2026-11-21-下游分支同步CG2新head交件-dev-lead.md`、本裁示的轉存檔）

正文：

## 補充十四：CG-2 一鍵檔退役 PR 與 `claims.py` 的過時註解（2026-11-21）

- 決策者：tech-architect。來源：`work/reviews/2026-11-21-下游分支同步CG2新head交件-dev-lead.md`、`work/reviews/2026-11-21-export寫法漏網與警示手冊維護與QuickEdit裁示-tech-architect.md`。
- 性質：第 1 點窄幅寬於補充九第 1 點「不改 `app/`」與 S-19a 第 1 點「`app/` 零差異」的字面，已標明。第 2 點為釐清。不改 CEO 可見字面。
- 背景：CG-2 登記分支依 2026-11-21 (甲) 裁示，在 `_ENV_FILE_KEY` 的 `#:` 註解中點名 `scripts/cg2_register.py`，以及一個相等斷言測試。兩者都由退役 PR 刪除。這句註解若保留，S-19a 第 1 點的 grep 必然命中，內容也不再屬實；所以補充九第 1 點的「不改 `app/`」與 S-19a 的 grep 條件不能同時成立。

1. **退役 PR 對 `app/` 的唯一允許差異**
   - 只限 `app/forecast/claims.py` 中 `_ENV_FILE_KEY` 上方的 `#:` 註解：刪去指向退役檔及其測試的那一句，包括該句在前一行的開頭片段。不新增任何字，其餘行不動。
   - `claims.py` 全模組的 AST 與退役 PR 的 merge-base 相同。補充九第 2 點「claims.py 的程式行為不變」，以此為證。
   - 這處變動會使 `code_digest` 與 `app/` 的 tree id 改變。
     - 退役 PR 在登記紀錄 commit 之後、接線 PR 之前合併，也就是在第一筆 `forecast_run` 之前，所以 D-5 第 6 點沒有可重算的既有紀錄。
     - 登記表不存 `code_digest` 與 tree id，已登記的值與雜湊不受影響。
     - 補充七附記三的 R-1 只在登記時生效，它的測試隨同一個 PR 刪除。
   - 新的 `code_digest` 與 tree id 記在 PR 說明。接線 PR 依補充九第 1 點 merge 退役之後，重算接線版的 `code_digest`。
2. **S-19a 第 1 點的 grep 條件不變**
   - 除守門測試本身以外，不另設例外。

- **S-22（逐條可檢查）**
  - 退役 PR 相對 merge-base，`app/` 的差異只有 `app/forecast/claims.py` 一個檔。該檔的新增行只有一行，內容等於原來那一行刪去行尾 ` The pattern and`；刪除行只有兩行，就是原來那一行和下一行。
  - `claims.py` 的 `ast.dump` 與 merge-base 相同（附輸出）。
  - 守門測試對 merge-base 零差異，而且通過。
  - `tests/test_forecast_claims_bootstrap.py` 零差異，而且通過。
  - PR 說明附上新舊 `code_digest` 與 tree id。
  - 本補充 append 進本 ADR 的 commit，早於退役 PR 的合併 commit。

### 第 3 題：要不要回頭改 CG-2

**裁示：不改。** 理由如下：
1. 【事實】在 CG-2 的狀態下，這句註解是對的：`cg2_register.py` 和相等斷言都在。它要到退役時才變得不實，所以應該由退役那一步修。
2. 【事實】登記不依賴這句註解：
   - 註解沒有任何執行期作用；
   - `claims` 不存 `code_digest` 或 tree id；
   - RC-507 (2) 的 `d631a75a…` 核對，對象是 CG-2 合併 commit M，不是之後的 product。
3. 【事實】RC-511 規定 CG-2 分支若再新增 commit，只能有 `work/reviews/` 的 `A`。改 `claims.py` 會直接違反這一條，風控的 M-9 核可就要重開。代價還包括：
   - tree id 重釘，`code_digest` 再變；
   - `review_refs` 再加紀錄，CG-2 head 至少再變兩次；
   - qa、風控第三輪 M-9；
   - 接線鏈和退役鏈全部重新同步。
   - 而且這些都落在登記的關鍵路徑上。
4. 【推論】回頭改 CG-2 能換到的，只是「退役 PR 維持純刪除」。補充十四只要一個 commit 加一段 ADR 文字就能做到同樣的可查性，而且不在登記的關鍵路徑上。
- 對已完成的 M-9：qa 和風控核對的範圍都不包括退役守門測試。他們核過的事項沒有一項改變，**不需要重做**，只要送風控知悉。

### 第 4 題：重做 merge 與組版字面

**分支 1 `chore/nm5-cg2-oneclick-retire`（`c559b4af` → 新 head，由 dev-lead 執行）**
1. 用 `--no-ff` merge `cc9e30239ad8acbb76706d2bef71b2379b4fac86`。4 個衝突檔以 `git rm` 保留刪除。`claims.py` 和 `test_forecast_claims_bootstrap.py` 照自動合併的結果收下。這個 merge commit 只做解衝突。
2. 檢查 merge commit：`git diff --name-status cc9e302 <merge>` 只能有 9 個 `D`，外加守門測試一個 `A`。
3. 另開一個 commit，依第 2 題約束 1 刪掉那句註解。建議訊息是 `chore: 刪去 claims.py 指向已退役登記腳本的註解句`，一個 commit 只有這一個語意。
4. 驗證：
   - ruff、ruff format、mypy；
   - 全套測試，在 3.12 和 3.13 各跑一次；
   - 守門測試**實際跑過**而且全綠；
   - `claims.py` 的 AST 比對（對 `cc9e302`）；
   - `git diff cc9e302 HEAD -- apps/stock-desk/backend/app` 只有那一處；
   - 新 tree id 和新 `code_digest`（用同一支 `digest.py`）；
   - 用 `git merge-tree --write-tree` 試合併新 head 與 `feat/nm5-wiring` `526201ca…`，確認沒有衝突，並在結果 tree 上用守門 regex 做 `git grep -P`，只能命中守門測試自己。
5. 用 fast-forward 推送，不 rebase、不 force push。
6. 【事實】dev-lead 上次試解時，`git rm` 被權限系統拒絕。這次能不能執行，要看派工授權和權限系統；我不能授權。被拒的話就停下回報，不要改用別的方式繞過。

**分支 2 `chore/pipeline-acceptance-retire`（`d01e068e` → 新 head）**
1. 改為 `--no-ff` merge 分支 1 的**新 head**，不要直接 merge `cc9e302`。這樣解衝突的結果只有一份。
   - 【推論】不會有衝突：分支 2 沒有動那 4 個檔，也沒有動 `app/`。
   - 先用 `merge-tree` 試算；只要有衝突就停下。
2. 驗證：
   - 相對分支 1 新 head，`--no-renames` 的檔案清單恰好符合 S-21 第 1 點；
   - `app/` 零差異；
   - 全套測試在兩個版本各跑一次。
3. head 變了，所以 F10 的 blob 紀錄要重做（coordinator 記錄、qa 核對）。最後一次 merge product 後的 merge-base 核對，照我 11-21 的裁示辦。

**組版字面**
- 補充十一：不改（沒有相關內容）。
- 補充十二：不改。
  - 它的「不改 `app/`」「`code_digest` 不變」「S-21 第 1 點的檔案清單」，說的都是該 PR 相對合併當時 merge-base 的 diff。分支 1 合併後，merge-base 已經包含註解的修改，這些敘述照舊成立。
  - 第 3 點 (b) 的排序理由也不受影響。
  - B1～B5、F1～F10 都不動，**不必送風控**。
- 補充十三：不改（它講「不改 `app/`」只針對它自己）。
- 補充九：條文不改，由補充十四處理。
- append 順序：8、9、10、11、12、13、14。補充十四最晚要在 CG-2 一鍵檔退役 PR 合併之前寫入。

**回覆 dev-lead 的兩個問題**
- 接線鏈單獨推送是對的，兩條鏈互不相依，不需要退回。
- 分支 3、4 只有 merge commit，不必另外送 qa，到接線 PR 最終審查時再一併核對。**分支 1 有新的 `app/` 變動，一定要送 qa**（有 Codex 就用）。

### 第 5 題：失效引用

**裁示**
- `work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md:155` 的 `731e09f4…`，以及各份提到 `9c157d86…` 的歷史紀錄，**都不改寫**，以追蹤清單為準。追蹤清單第 729、732 行已經這樣處理，我確認。
- 【建議】追蹤清單再加記兩件事：
  - 接線版 `32725eb8…b3c6` 是**暫定值**。退役 PR（含補充十四的註解修改）合併後，接線 PR merge product 時會再變；接線 PR 說明裡的值，要在最終 head 上重算，不得從範圍清單或追蹤清單抄。qa 拿重算值核對。
  - 退役 PR 合併以後，product 的 `app/` tree id 不再是 `d631a75a…`，這是預期中的事。RC-507 (2) 只約束 M。
- 範圍清單是「PR 說明用的材料」。它的第 155 行過去曾經就地更新過（第五輪）。要不要在接線最終 head 上由 dev-lead 更新一次，交 coordinator 決定；不更新的話，以追蹤清單為準。

---

## 三、驗證

**讀過的檔**
- dev-lead 同步交件全文。
- 我的 (甲) 裁示全文。
- qa 的 M-9 補充最終審查全文。
- 追蹤清單第 653～668、726～732 行。
- 補充九定稿：第 100～269 行。
- 補充十一組版全文、補充十二組版全文。
- 補充十三組版：用 Grep 看相關行。
- 11-20 退役讀法（題二）第 50～74 行。
- 11-21 退役分支三件確認全文。
- 退役 PR 預先實作交件全文。
- 心跳裁示第三件：用 Grep 看相關段落。
- 退役通知草稿：用 Grep 看相關行。
- 接線範圍清單第 66～160 行。
- ADR-0030 的檔頭和各節標題，確認只寫到補充七附記三之一。
- ADR-0030 中 `code_digest`、D-5 第 6 點、補充三（修訂版）第 1 點的相關行。
- CG-2 worktree（`agent-a16d399220753e66d`）的 `claims.py` 第 280～299 行。
- `test_cg2_register_flow.py` 第 500～579 行，`test_forecast_claims_bootstrap.py` 第 312～386 行，以及兩支測試的 Grep 結果。
- 三份 `test_oneclick_retirement.py`：內容相同。

**沒有查證的事**
- 沒有執行任何 git 指令。下列各項都採信 dev-lead 或 qa 的說法：
  - 各分支的 head 和衝突內容；
  - `agent-a16d399220753e66d` 這個 worktree 確實停在 `cc9e302`。
- 守門測試在合併後會紅，只是靜態推論，dev-lead 和我都沒有實跑。
- 「主 DB 在接線 PR 之前沒有任何 `forecast_run`」是推論，沒有讀 DB。
- 只改註解時，重算結果是否逐位相同，是推論。
- 接線分支在 11-20 試合併之後，有沒有新增指向退役檔的引用：沒有查證。由 dev-lead 用 merge-tree 和 grep 確認。
- `feat/forecast-status-oneclick`、`feat/gap-check-oneclick` 有沒有引用退役檔名，或釘住 `app/` 的 tree id：沒有查證。這兩支都在 CG-2 退役之後才合併，守門測試會在 product 上掃到它們。
- 註解刪減後，ruff 的格式檢查和行長是否通過：沒有實跑。
- 範圍清單是否被 git 追蹤在接線分支上：只在 worktree 裡找到這個檔。
- 補充八、九有沒有單獨的組版檔：沒有找。

---

## 四、下一步

**要送風控的**
1. 補充十四：請知悉，並由風控決定要不要審查。它不碰 CEO 可見字面，但它窄幅放寬的是一段經過 RC-244～RC-254 判定的補充。如果風控要審，退役 PR 要等審完才能合併。
2. 知悉：CG-2 的 M-9（RC-507～RC-511）不重開，CG-2 分支不新增 commit，所以 RC-511 不受影響。
3. 知悉：退役通知草稿（RC-295～RC-297）不受影響。我讀過草稿，裡面沒有「其他程式不變」之類的寫法。

**要 dev-lead 做的**
- 照第 4 題重做分支 1、分支 2，附上：AST 比對、新 tree id、新 product `code_digest`、守門測試的實跑結果、和接線鏈的試合併與 grep。
- 分支 1 送 qa（有 Codex 就用）。
- 接線 PR 最終 merge product 之後，重算接線版 `code_digest`。

**要 devops-sre 做的**
- 用守門 regex `cg2_register(?!s)|cg2-register|cg2-preflight|verify_cg2_instruction`（`git grep -P`），掃 `feat/forecast-status-oneclick`、`feat/gap-check-oneclick` 兩支 head，並查有沒有釘住 `app/` tree id 的常數。有命中就回報 tech-architect。
- `r2_first_run.py` 的 regex 照原追蹤處理；修的時候加上和 `claims._ENV_FILE_KEY` 相等的斷言。

**要 coordinator 做的**
- 組版補充十四，排在補充十三之後，在 CG-2 一鍵檔退役 PR 合併之前 append。
- 追蹤清單記下：
  - `32725eb8…` 是暫定值；
  - 退役後 product 的 tree id 不再是 `d631a75a…`；
  - backlog（low）：claims 端缺「值裡含鍵名」的反例；`env_file_sets_db_path` 的 docstring 過時。
- 分支 2 的 F10 紀錄重做。

**qa**
- 依 S-19a、S-22 審分支 1。分支 2 依 S-21 和 F10。

**有沒有必須由 CEO 決定的事：沒有。**

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-21-下游分支同步CG2新head交件-dev-lead.md`
- `/home/user/AICompany/work/reviews/2026-11-19-接線PR四題裁示與補充九定稿-tech-architect.md`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md`
- `/home/user/AICompany/.claude/worktrees/agent-a16d399220753e66d/apps/stock-desk/backend/app/forecast/claims.py`
- `/home/user/AICompany/.claude/worktrees/agent-a16d399220753e66d/apps/stock-desk/backend/tests/test_forecast_claims_bootstrap.py`
- `/home/user/AICompany/.claude/worktrees/agent-a45c368e7e9a2fc13/apps/stock-desk/backend/tests/test_oneclick_retirement.py`
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md`

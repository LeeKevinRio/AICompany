# 補充十二 B1～B5 確認與 r2-probe.bat 雜湊查證

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

- **B1～B5 都沒有改動技術意旨，也沒有和補充六、補充九、補充十一或 S-21 衝突。** 五處都是收緊，或是在 CEO 推翻、日後取回時補上「恢復適用」的條款，沒有放寬任何既有條件。
- 腳本逐字套用的結果正確。兩份檔逐行對照，除了檔頭多一行「套用」說明，正文只有 B1～B5 這五處不同，其餘一字不差。
- **檔頭補充紀錄行建議補一句**，字面見下方第 2 題。依據是 ADR 第 13 行補充六附記二的前例「經風控審查（RC-167，附條件接受）」。
- **E-6 結論：改 `r2-probe.bat` 的 echo 字面，不會改變任何被記錄或被比對的雜湊，也不影響總閘門「一鍵檔全 0」的判定。**
- **結論一行：補充十二套用 B1～B5、再加上第 2 題的檔頭補字之後，可以視為定稿、可以寫入 ADR；寫入時點仍依補充十二第 3 點。**

## 各部門回報（tech-architect）

### 1. B1～B5 逐項

| 項 | 技術意旨 | 和補充六／九／十一、S-21 的一致性 | 備註 |
|---|---|---|---|
| B1（性質） | 不變。只補上「CEO 推翻時，RC-338、RC-312、RC-325 這三項恢復適用」，再加一份更正通知 | 一致。和風控 RC-345、RC-346、RC-347 寫的恢復條件相同。凍結基準檔依第 5 點 (c) 不受影響（B5 也排除了它） | 無 |
| B2（第 3 點 (a)） | 不變，是收緊：合併前提多了兩項（退役通知已交給 CEO、RC-344 的書面核對） | 一致。不碰補充六第 6 點 (b)～(d)，也不碰補充九第 1 點的順序。時序上：RC-355 要求登記紀錄 commit 與 RC-344 紀錄完成後才發通知，B2 要求通知在合併前交出，兩者不矛盾。和第 3 點 (d) 的「不得 push」期間也不重疊，因為通知在登記完成之後才發 | 兩項新前提用分號接在凍結基準那一條後面，`work/` 也沒加反引號。這只是格式問題，不影響判讀；風控說過任何偏差都要整份重審，所以不建議再改 |
| B3（S-21 第 3 點） | 不變。把 B2 的通知前提變成可以用 commit 順序核對的形式 | 一致。核對方式和同一點既有的「登記紀錄 commit 早於本 PR 合併 commit」相同 | 無 |
| B4（第 4 點 (d)） | 不變，是收緊：只在日後取回時適用 | 一致。和 B1、RC-325、RC-347 對得上；不碰第 4 點 (c) 的技術設計 | 無 |
| B5（第 5 點 (c)） | 不變，是收緊。它重申第 5 點 (c)「之後不得更新」，並排除 RC-336、RC-338、RC-339 的改字 | 一致。第 6 點 (a)「比照凍結基準」從此只能讀成結構上的比照，CEO 看得到的字面依風控定稿，兩者不矛盾。和 RC-350（四支同時換，不含基準檔）也一致 | 無 |

**B2、B3 新增的前提，qa 能不能逐條檢查：都能。**
- (i) **退役通知已交給 CEO**：qa 查 coordinator 在 `work/` 留的發出日期紀錄（RC-355 已要求記錄），以及那筆紀錄的 commit 是否早於本 PR 的合併 commit（B3）。
- (ii) **RC-344 的暫存資料夾核對**：qa 查 `work/` 有沒有這筆紀錄、裡面有沒有 (a)～(d) 四項，以及 devops-sre 的書面確認。限制：qa 只能確認紀錄存在、內容齊全，沒辦法獨立驗證 CEO 每次執行實際怎麼結束，這是 RC-344 本身的設計。
- (iii) **commit 順序**：用 `git merge-base --is-ancestor` 或 commit 順序就能核對，和 S-21 既有各條一樣。
- 一個小缺口，不擋：S-21 沒有明列「RC-344 紀錄的 commit 早於合併 commit」。不過 B2 把它列為合併前提，RC-355 又要求它早於通知、通知早於合併，可以遞推出這個順序。建議 qa 用同一種方法順便核對，不必改字。

### 2. 檔頭補充紀錄行：需要補

理由：B1～B5 加了合併前提，ADR 第 13 行也有前例（「經風控審查（RC-167，附條件接受）」）。用詞依 ADR 前例寫「附條件接受」。原句在 `work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md` 中只出現在第 11 行，恰好一次。

原：`CEO 可見部分由風控定稿；coordinator 定案`
新：`CEO 可見部分由風控定稿；經風控審查（RC-344～RC-356，附條件接受，替換 B1～B5 已併入）；coordinator 定案`

這句只改檔頭，不改正文，所以不必再送風控審 B1～B5。

### 3. E-6：`r2-probe.bat` 的雜湊有沒有被釘住

**結論：沒有。改 echo 字面不會改變任何被記錄或被比對的雜湊。**

- **`r2_first_run.py` 不會對 `.bat` 取雜湊。**
  - 第 80～85 行的 `sha256_file` 只在第 228 行用來比對資料庫和複本。
  - 白名單第 41～46 行裡的雜湊只有兩種：`script_sha256_lf` 和 `db_sha256_before/after`。
- **`script_sha256_lf` 是偵測工具 `.py` 的雜湊，不是 `.bat` 的。** 它來自 `n177_n190_backtrack_probe.py` 第 409～411 行，算的是那支 `.py` 檔本身（`Path(__file__).read_bytes()`）。
- **R2 第一次的證據沒有釘住 `.bat`。**
  - `work/reviews/2026-11-14-R2探測第一次執行結果-CEO回傳.md` 第 41～43、54 行，記下的雜湊只有偵測工具和資料庫兩種；
  - 第 3 行記的是合併 commit `917f8f03…`，屬於歷史紀錄，之後改檔也不會變；
  - `work/reviews/2026-11-13-R2探測一鍵檔合併紀錄-devops-sre.md`、追蹤清單第 488 行也只記 commit id。
- **總閘門的「全 0」比的是計數，不是雜湊。**
  - `work/reviews/2026-11-14-排程台為空後的簡化裁示-風控.md` 第 30 行：4 個計數加 `N208_COUNT_RESULT` 都是 0；
  - 第 39 行：「總閘門那次一鍵檔的結果全部是 0」；
  - 第 82、97 行的判讀依據也是計數，加上偵測工具雜湊和資料庫前後雜湊。這些都不含 `.bat`。
- **`code_digest` 不涵蓋 `.bat`。** 依 ADR 第 135 行，它只涵蓋 `app/` 底下的模組。
- **測試面有兩件事要知道（不是雜湊）。**
  - `backend/tests/test_r2_first_run.py` 第 739～746 行只檢查 `.bat` 裡有沒有某些子字串，不涉及 `After installing` 那一行，改字不會讓它失敗。
  - `backend/tests/test_pipeline_acceptance_real_flow.py` 第 1425～1434 行要求 `pipeline-acceptance.bat` 的每一行指令都要在 `r2-probe.bat` 裡找得到。如果在退役 PR 合併前改 `r2-probe.bat`，這項測試可能會失敗。這支測試會隨退役一起刪除，這也支持 RC-345 (c)「退役 PR 合併之後才改」的時點要求。
  - `test_forecast_status_flow.py` 在另一支分支上，本機看不到，照 RC-345 (b) 交給 qa 處理。
- **限制：**
  - 我只查了本機現有的工作樹，沒有查 `feat/*` 分支和遠端。
  - 總閘門那一次還沒執行，它的紀錄格式只能依 RC-113、RC-114 的字面推定。

## 驗證

- 讀過：
  - 套用前、套用後兩份組版全文，並逐行對照；
  - 風控報告全文；
  - ADR-0030 的檔頭補充紀錄行（第 4～20 行）和 `code_digest` 的定義（第 135 行）；
  - `r2-probe.bat` 全文；
  - `r2_first_run.py` 的雜湊相關段落；
  - `n177_n190_backtrack_probe.py` 第 409～417 行；
  - 兩支測試裡碰到 `r2-probe.bat` 的段落；
  - RC-113～RC-117 原文；
  - R2 第一次的 CEO 回傳和合併紀錄。
- Grep：在 `work/` 裡找 `r2-probe`、`RC-114`、`全 0`，以及 `.bat` 與雜湊同時出現的字樣，沒有找到任何把 `.bat` 雜湊釘住的紀錄。
- 本機的 `docs/adr/0030` 只到補充七附記三之一，補充八～十一的全文不在這份工作樹。所以和補充九、補充十一的對照，是依補充十二本身引用的條號，加上風控報告的轉述。
- 全程只用 Read、Glob、Grep，沒有寫任何檔，沒有讀 `.env`，沒有碰 `apps/stock-desk/backend/data/`。

## 下一步

- **coordinator**：依第 2 題補上檔頭字面後就算定稿；寫入 ADR 的時點依補充十二第 3 點，也就是退役 PR 合併之前 append。
- **qa-reviewer**：S-21 第 3 點核對 B3 時，順便確認 RC-344 紀錄的 commit 早於合併 commit；B2 的兩項前提依上表 (i)、(ii) 核對。
- **devops-sre**：E-6 已由本報告確認，`r2-probe.bat` 改字時不必再查雜湊。改字時點仍依 RC-345 (c)，要等兩支新一鍵檔和退役 PR 都合併之後。如果總閘門那次的紀錄格式之後加入 `.bat` 雜湊，再回報我。
- **風控**：第 2 題的檔頭補字不改正文，不需要再審；如果風控認為要過目，只做這一行的單項確認。

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二草稿-待風控-coordinator組版.md`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二與退役連帶條件判定RC344至RC356-風控.md`
- `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`
- `/home/user/AICompany/apps/stock-desk/r2-probe.bat`
- `/home/user/AICompany/apps/stock-desk/backend/scripts/r2_first_run.py`
- `/home/user/AICompany/apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_r2_first_run.py`
- `/home/user/AICompany/apps/stock-desk/backend/tests/test_pipeline_acceptance_real_flow.py`
- `/home/user/AICompany/work/reviews/2026-11-14-排程台為空後的簡化裁示-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-14-R2探測第一次執行結果-CEO回傳.md`

# gap_check 舊 regex 修正提案裁示

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 裁示：gap_check 舊 regex 提案（2026-11-21）

全程唯讀，只用了 Read、Grep。沒有寫檔，沒有執行 git，沒有讀 `.env*`，也沒有碰 `backend/data/`。

## 一、本次結論

1. **(1) 採用，小幅補件後再 commit。**
   - 【事實】regex 部分和 CG-2 新版 `claims._ENV_FILE_KEY` 展開後的字面、flags 都相同。CG-2 worktree 的 `claims.py:294` 是 `rf"^\s*(?:export\s+)?{DB_PATH_ENV_VAR}\s*=", re.IGNORECASE`。
   - 【裁示】這樣改是讓實作符合補充十「`.env` 沒有設這個鍵」的原意，比照 11-21 claims export 修正的判斷，不需要新的 ADR 補充。
   - 【裁示】測試要補 3 個例子，見第二節。
2. **(2) 相等斷言另案處理**：等 gap-check 合併進 product 之後，由 devops-sre 另開 `test:` PR 補上。不要為了它先把 product merge 進 gap-check 分支。
3. **(3) 重跑時點不變。** 等退役 PR 合併、而且這個 regex commit 也推送之後，在 gap-check 的最終 head 上，F10 紀錄和 RC-399 (d) 的全套測試各做一次。
4. **(4) 不送審，送知悉。** 前例是 RC-495 那次對 export 修正的處理。
5. 沒有必須由 CEO 決定的事。

## 二、各部門回報（tech-architect）

### (1) 要改的地方

**【裁示】必改（成本很小）：補齊 claims 端有、這份提案沒有的例子**
- 正例加兩個：
  - `"export\tSTOCK_DESK_DB_PATH=/x"`（tab）；
  - `"EXPORT STOCK_DESK_DB_PATH="`（空值）。
- 反例加一個：`"  # export STOCK_DESK_DB_PATH=/x"`。

**【建議】BOM 正例改用跳脫寫法**
- 改成 `"﻿STOCK_DESK_DB_PATH=/x"`，不要在原始碼裡放看不見的字元。

**【裁示】commit 的約束（逐條可查）**
1. 一個 commit，一個語意。建議訊息：`fix: gap_check 的 .env 鍵名比對涵蓋 export 寫法與大小寫`。
2. 相對 `1faae4a73636d7d276d3748da10ff2ee9e3311f6`，`--name-status` 只能有 `M scripts/gap_check.py` 和 `M tests/test_gap_check_logic.py` 兩項。
3. `gap_check.py` 只動第 90 行。STOP 字面、`env_file_sets_db_path` 函式本體、`test_ast_the_env_file_is_only_searched_for_the_key_never_read_for_values` 都零差異。
4. `tests/fixtures/` 零差異。
5. 重跑守門 regex 的 grep，結果仍要零命中。
6. 送 qa（有 Codex 就用）。這是行為變更，不能只做單項核對。
7. qa 另外做一次性的人工核對：`gc.ENV_KEY_PATTERN.pattern` 和 `cc9e302` 上 `claims._ENV_FILE_KEY` 展開後的字面、flags 都相同。這一點在第 (2) 題的自動斷言補上之前，用來代替它。

### (2) 相等斷言

**【裁示】另案，排在 gap-check 合併之後**
- 【推論】依合併順序，gap-check 合併的時候，product 上已經有新版 claims。所以合併後就能直接加斷言，不必改動 gap-check 分支的範圍。
- 斷言要寫在測試檔裡，比對兩者的 `pattern` 和 `flags`。`gap_check.py` 本身仍然不得 import `app`，現有測試已經釘住這一點。
- 追蹤清單記一筆（devops-sre，low），寫明觸發條件是「gap-check 合併後」。
- 日後修 `r2_first_run.py` 時，照同樣的方式加斷言。

**否決的替代方案**
- 先 merge product 再加斷言：等於多一個 merge commit，也讓 gap-check PR 的範圍和合併時點綁在一起。換到的只是提早幾天得到自動保護，而第 (1) 題第 7 條已經用人工核對補上了這段空窗。

### (3) 重跑時點

- 【裁示】不變。順序如下：
  1. 補件後推送 regex commit；
  2. 退役 PR 合併；
  3. 在 gap-check 的最終 head 上記 F10，並在含退役的 product 上重跑 RC-399 (d) 的全套測試，交 qa 確認。
- 如果到時候還要 merge product 進 gap-check，就在那次 merge 之後才做，同樣只做一次。
- 【事實】devops-sre 這次只跑了兩個 gap_check 測試檔，全套測試要靠 RC-399 (d) 那次重跑補足。
- F10 紀錄的路徑要寫 `apps/stock-desk/backend/tests/fixtures/.gitattributes`。devops-sre 指出的路徑更正是對的，blob 是 `445bacf6…`。

### (4) 風控

- 【事實】STOP 字面不變。
- 【事實】CEO 說明草稿第 310 行的中文說明是「`.env` 檔裡有指定資料庫位置的設定」。新增會命中的 export 寫法和小寫寫法，也確實是這種設定，所以說明仍然屬實。
- 【推論】對 CEO 的影響只有一種：原本該擋卻沒擋的情況，現在會擋下來。
- 【裁示】送知悉。如果風控要審，gap-check 就等審完才合併。

### 其他

- `r2_first_run.py`：照原本的追蹤處理。
- `pipeline_acceptance_real.py:289`：【建議】coordinator 確認它是否列在退役分支 2 的 S-21 刪除清單裡。在清單裡就不用處理；不在的話，列入追蹤，不併進這次修改。我沒有查證。
- 【建議】devops-sre 說是推送到 `wip/gap-check-comment`。請 coordinator 確認 `origin/feat/gap-check-oneclick` 確實是 `1faae4a7…`；如果不是，先釐清再繼續。

## 三、驗證

**讀過的檔**
- devops-sre 交件全文。
- 提案 diff 全文。
- CG-2 worktree 的 `claims.py:294`。
- gap-check worktree 的 `gap_check.py:758-763`。
- CEO 說明草稿第 303 行與第 310 行。
- ADR-0030 中有 `.env` 的那一行（第 490 行）。

**沒有查證的事**
- 補件後的測試結果。
- 遠端分支的實際 head。
- `pipeline_acceptance_real.py` 的去留。

## 四、下一步

- **要送風控的**：知悉一件，就是 gap-check 的 `.env` 鍵名比對範圍變大，STOP 字面和 CEO 說明都不變。
- **要誰做**
  - devops-sre：補 3 個例子後 commit 並推送，送 qa；之後另案補相等斷言。
  - qa：依第 (1) 題的 7 條約束審查。
  - coordinator：確認遠端 head；記追蹤清單；退役 PR 合併後辦 F10 和 RC-399 (d)。
- **有沒有必須由 CEO 決定的事：沒有。**

相關檔案：
- `/home/user/AICompany/work/reviews/2026-11-21-gap_check註解修改與regex提案交件-devops-sre.md`
- `/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/gap_check_regex_proposal.diff`
- `/home/user/AICompany/.claude/worktrees/agent-a16d399220753e66d/apps/stock-desk/backend/app/forecast/claims.py`
- `/home/user/AICompany/work/dispatch/2026-11-19-帳外缺日比對操作說明-CEO-草稿.md`

# gap-check 分支命中退役守門 regex 的處理

- 審查者：tech-architect
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 裁示：gap-check 分支命中退役守門 regex 的處理（2026-11-21）

全程唯讀，只用了 Read、Glob、Grep。沒有寫檔、沒有執行 git，沒有讀 `.env*`，也沒有碰 `backend/data/`。

## 一、本次結論

1. **處理方式：採 (甲)，(乙) 否決，(丙) 的各種替代都否決。**
   - 【裁示】在 gap-check 分支加一個 commit，只刪掉括號內的 `; replaces the cg2_register.py line`。
   - 改完那一行是 `        # Verbatim from the risk-control report (RC-272, S-3):`。不加任何字，連鄰行的 `, extracted by script` 也不補。
   - 不必送風控審查。
   - 凍結基準的兩個 blob 不受影響。但 F10 紀錄和試合併全套紀錄都綁在分支 head 上，head 一變就必須重做。
2. **時點**
   - 【裁示】現在就改。
   - 但 RC-399 (d) 的試合併全套和 F10 的 blob 紀錄要延後做，等退役 PR 合併進 product 之後，在新 head 上各做**一次**。
3. **其他分支**
   - 【裁示】要掃。範圍不限你列的那幾支：凡是會在退役 PR 之後才合併進 product 的分支，全部都掃。
   - 命中時的處理原則見第二節第 3 題。
4. **順帶發現一件相關的事，不擋本題。** `gap_check.py:90` 用的是舊版 regex，和 `claims.py` 修正前一樣有漏洞（見第二節第 4 點）。
5. 沒有必須由 CEO 決定的事。

## 二、各部門回報（tech-architect）

### 第 1 題：處理方式

**事實**
- 這行只是 `.py` 註解，不會印出來，CEO 看不到。
- 風控的定稿字面在 `copy_failed` 這個字串常數裡。測試 `test_the_three_stops_are_the_risk_control_sentences_verbatim` 會讀風控報告逐字比對，比的是字串，不是註解。
- `scripts/` 不在 `app/` 樹和 `code_digest` 的範圍內。
- `test_gap_check_flow.py` 裡讀原始碼的測試（第 355、387、408 行）都和這行註解無關。
- `gap_check.py` 的 `script_sha256_lf` 會因為這次修改而改變。`work/` 裡沒有任何地方釘住 gap-check 的預期雜湊：CEO 說明草稿第 229 行只寫「同上」，沒有寫值。測試 `test_the_script_hash_is_the_lf_normalised_source_hash` 是即時計算的，不受影響。

**否決的方案**
- (乙) 守門測試開例外：理由同今天 claims.py 第 2 題。另外補充十四第 2 點已經明文規定「除守門測試本身以外，不另設例外」。
- (丙1) 讓 gap-check 先於退役 PR 合併：會推翻補充十二第 3 點 (b) 的排序，而且退役 PR 就得去改 `gap_check.py`，超出 S-21 第 1 點的檔案清單。否決。
- (丙2) 改寫分支歷史（amend、rebase、force push）：否決。

**是否送風控**
- 【裁示】不必送審，因為沒有改動任何 CEO 看得到的字面，也沒有改風控定稿的位元組。
- 【建議】下次送風控時附一句知悉：gap-check 的 head 會變，RC-399 (d) 依它自己的規則重跑。不擋合併。

**qa 要核對的項目（逐條可查）**
1. `git diff --name-status f6aff2ce61bb15dd4d1e5d52b54e6668801eaf3e <新head>` 只有 `M apps/stock-desk/backend/scripts/gap_check.py`。
2. diff 只有一行刪除、一行新增；新行等於舊行刪去 `; replaces the cg2_register.py line`。
3. `gap_check.py` 的 `ast.dump` 和 `f6aff2ce` 上的版本相同（附輸出）。
4. `git diff f6aff2ce <新head> -- apps/stock-desk/backend/tests` 為空。也就是說，基準檔 blob `5b0b271e…`、`.gitattributes` blob `445bacf6…` 都沒變。
5. 用守門 regex 對新 head 的 `apps/stock-desk` 做 `git grep -P`，結果是零命中。
6. ruff、ruff format、mypy 都通過；`test_gap_check_flow.py` 加 `test_gap_check_logic.py` 全綠。
7. 這個 commit 只有一個語意，用 fast-forward 推送。
- Codex 有就用。

**凍結基準與 F10**
- 【事實】兩個 blob 不會變。
- 【事實】補充十二第 5 點 (b) 規定：「分支 head 之後再變動，就重新記錄，並由 qa 重新核對」。F10 紀錄記的是分支 head，所以要用新 head 記錄。如果 F10 還在等 G_acc、還沒記，就直接用新 head 記，沒有額外成本。

**試合併全套紀錄**
- 【事實】那份紀錄的檔頭寫明「任一分支 head 再變動，本紀錄即失效」，RC-399 (d) 也規定「之後任一分支的 head 再變動，就要重跑」。所以 gap-check 那一欄要重做。
- 狀態報告那一欄不受影響。

### 第 2 題：時點

- 【裁示】註解 commit 現在就做。
- 【推論】延後改也省不掉任何一次重跑：只要 head 變動，F10 和 RC-399 (d) 就要重做；合併程序修訂八本來也要求在合併點上重跑。
- 【建議】RC-399 (d) 的重跑，請在一個已經含有退役 PR 合併 commit 的 product 上做。這樣守門測試會真正掃到 gap-check 的內容，證據比在 `5e6a56d` 上做更強。F10 紀錄也在最終 head 上做一次就好。

### 第 3 題：其他分支

**範圍**
- 【裁示】要掃的是集合，不是名單：所有還沒合併、而且合併時點晚於退役 PR 的分支。你列的 8 支都包括在內。
- `feat/nm5-wiring` 已經有 dev-lead 的 merge-tree 加 grep 在做，coordinator 再掃一次也無妨。

**怎麼掃**
- 對各分支 head 的 `apps/stock-desk` 用同一個 regex 做 `git grep -P`。
- 同時查有沒有釘住 `d631a75a`、`9c157d86`、`07b5e1fd95fa` 的常數，或釘住 product `code_digest` 的地方。

**命中時的處理原則**
1. 命中的是該分支自己新增或修改的內容：
   - 在該分支另開一個 commit，只刪去對退役檔的指稱，盡量不加新字；
   - 不開守門例外，不用 skip、xfail；
   - 不改寫歷史。
2. 命中位置在 CEO 看得到的文字裡（README、手冊、`.bat` 輸出、CEO 文件）：改字前先送風控定稿，再提交。
3. 有下列情形之一就停下，升級給 tech-architect：
   - 命中在 `app/` 裡，會牽動 `code_digest` 和補充十四；
   - 命中在位元組被釘住的檔案裡，例如凍結基準、有固定雜湊的腳本、風控逐字字面；
   - 有常數釘住 `app/` tree id 或 `code_digest`。
4. 命中的檔是從退役前的 product 繼承來的，分支本身沒改過：這種情況由「合併含退役的 product」來解決。要用 merge-tree 加 grep 證明結果 tree 只會命中守門測試自己。
5. 修改後 head 會變，所有綁 head 的紀錄（qa 審查、F10、RC-399 (d)）都依各自的規則重做。

### 第 4 點：順帶發現（不擋第 1 題）

- 【事實】`gap_check.py:90` 是 `ENV_KEY_PATTERN: Final = re.compile(r"^\s*STOCK_DESK_DB_PATH\s*=")`。這是舊版 regex：比對不到 `export STOCK_DESK_DB_PATH=`，也不忽略大小寫。
- 我在 11-21 的 export 漏網裡列了三份副本，漏了這一份。原因是當時只盤點了 product 上的 `scripts/`，這支還在功能分支上。
- 【建議】交 devops-sre 評估要不要在 gap-check 合併前修。
  - 要修的話，另開一個 commit，pattern 和 flags 要和 `claims._ENV_FILE_KEY` 相同，並加正例、反例測試。這屬於行為變更，要送 qa。
  - 修好之前先送我裁示具體 diff。
  - **這件事要先決定，再去重跑 RC-399 (d)。** 否則 head 會變兩次，要重跑兩次。

## 三、驗證

**讀過的檔**
- 今天的退役鏈裁示全文。
- 試合併全套紀錄全文。
- 補充十二組版：第 5 點 (b) 與 S-21 的 blob 相關行。
- RC-399 原文。
- gap-check worktree（`.claude/worktrees/agent-acec04b09d9a79ee5`）：`gap_check.py` 第 90～93、165～194 行；`test_gap_check_flow.py` 第 138～148、350～418 行。
- CEO 說明草稿中的雜湊與 `cg2_register` 字樣（Grep）。

**沒有查證的事**
- 那個 worktree 是否確實停在 `f6aff2ce`：沒有執行 git。
- 命中只有一處：採信 coordinator 的說法。
- 刪字後 ruff format 和行長是否通過：沒有實跑。不過行只會變短。
- 風控 RC-271～RC-283 是否另有對註解的規定：只 Grep 了 RC-272，沒有逐條讀。

## 四、下一步

**要送風控的**
- 只送知悉，不送審：gap-check 的 head 會變，RC-399 (d) 會在含退役的 product 上重跑。
- 如果日後 `ENV_KEY_PATTERN` 也要修，那時再一併告知。

**要誰做**
- devops-sre：
  - 做註解 commit（第 1 題）；
  - 評估第 4 點，送我裁示。
- qa：依第 1 題的 7 條核對。
- coordinator：
  - 用同一個 regex 掃第 3 題的分支集合，命中就照原則處理或回報；
  - 退役 PR 合併之後，在 gap-check 的最終 head 上記 F10 紀錄、重跑 RC-399 (d)，交 qa 確認。
- 追蹤清單：記下 `gap_check.py` 的舊 regex（第 4 點）。

**有沒有必須由 CEO 決定的事：沒有。**

相關檔案：
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/scripts/gap_check.py`
- `/home/user/AICompany/.claude/worktrees/agent-acec04b09d9a79ee5/apps/stock-desk/backend/tests/test_gap_check_flow.py`
- `/home/user/AICompany/work/reviews/2026-11-21-兩支一鍵檔改基準後試合併全套紀錄-coordinator.md`
- `/home/user/AICompany/work/reviews/2026-11-21-手冊套用確認與補充十二F系列判定RC393至RC400-風控.md`
- `/home/user/AICompany/work/reviews/2026-11-21-補充十二-待寫入-coordinator組版.md`
- `/home/user/AICompany/work/reviews/2026-11-21-退役鏈同步衝突與claims註解裁示及補充十四-tech-architect.md`

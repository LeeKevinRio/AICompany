# CG-2 登記一鍵檔最後一輪小修交件（J～M，head 9d5bbf4）

- 審查者：devops-sre
- 日期：2026-11-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

最後一輪小修 J～M 已完成，已 fast-forward push 到 `origin/feat/nm5-cg2-registration`。
- head：`9d5bbf480948d3a94fcef0966293bbfca7702089`（`git ls-remote` 與本地相同，工作樹乾淨）。
- 全套 3.12、3.13 各 12619 passed、2 xfailed，**唯一失敗仍是預期的** `tests/test_cg2_register_values.py::test_the_review_refs_all_exist_at_head`（只缺兩個最終審查紀錄路徑）。
- ruff、mypy 全過。
- 「不得動」清單零 diff。
- 畫面字句沒有新增或修改。
- 沒有遇到需要停下回報的衝突。

## 各部門回報（devops-sre）

**Commits（從 `7b3fef0f` 接續）**
- `15c5dee`：merge `origin/product/stock-desk`（取得附記三之一與新報告）。
- `2451444`：J、K、L 的程式與測試。
- `9d5bbf4`：M 的說明文件與驗證腳本。
- 全部是 fast-forward，沒有 rebase、amend、force push。

**J～M 逐項對應**

- **J 「登記已開始」的起點**
  - 呼叫 `claims.start()` 之前先設 `state.late = True`；只有 `start()` 拋 `OSError` 時改回 `False`，STOP `claims_not_started`，結束碼 3，不留回貼。
  - `start()` 期間的其他例外或中斷，以及回傳後到 `finish()` 之前的中斷，一律結束碼 5、留 `register_result=UNCONFIRMED` 回貼。已取得 `Popen` 物件就呼叫新增的 `abort(handle)` kill。
  - 鍵入後重驗 port 那一步仍在設 `late` 之前，中斷仍是 2。
  - 測試（在 `tests/test_cg2_register_addendum3.py`）：
    - `test_p6_an_interrupt_while_the_start_function_runs_is_exit_5_with_an_unconfirmed_paste_back`（原 `test_p6_an_interrupt_while_starting_is_exit_2_with_no_paste_back` 改名並改預期）
    - `test_p3_an_error_that_is_not_oserror_while_starting_is_unconfirmed_exit_5`（原 `..._is_still_before_the_registration` 改名並改預期）
    - `test_p6_an_interrupt_after_start_returned_and_before_the_wait_kills_the_child`
    - `test_p3_popen_that_cannot_start_the_child_is_exit_3_and_not_late`
    - `test_p3_oserror_puts_the_state_back_to_not_started`
    - `test_p3_late_is_set_before_the_start_function_is_called_and_reset_only_by_oserror`
    - `test_p6_an_interrupt_at_the_port_check_after_the_answer_is_exit_2`
    - `test_p6_every_stage_before_the_start_gives_exit_2`
  - 世界 helper 的 `InProcessClaims` 新增 `abort`，並把 `finish` 改為屬性，讓測試能在 `start()` 回傳後、`finish` 之前注入中斷。
- **K 預檢檔名樣式**
  - 新增常數 `STAMP_FORMAT` 與 `PREFLIGHT_NAME_PATTERN`，以及函式 `preflight_file_name(stamp)`。
  - 腳本寫檔與挑最新一份都用這組定義，挑檔前先 `re.fullmatch` 過濾，不符的檔一律不列入。
  - 測試：
    - `test_k_the_file_name_pattern_is_the_one_the_script_writes_with`
    - `test_k_a_file_that_does_not_fit_the_pattern_is_never_chosen`（`preflight-zzz.txt` 等檔排序較後也不會被選中）
    - `test_k_only_files_off_the_pattern_is_a_stop`
- **L kill 之後的等待**
  - `finish` 在 kill 之後的 `communicate()` 加 `timeout=KILL_WAIT_SECONDS`（10 秒），等不到就放棄等待，仍判 `ClaimsTimeout`，結束碼 5、留 `UNCONFIRMED` 回貼。
  - 測試：
    - `test_l_a_child_that_survives_the_kill_does_not_block_and_is_unconfirmed`（兩次等待都有逾時）
    - `test_l_through_the_flow_it_is_exit_5_with_an_unconfirmed_paste_back`
    - `test_l_abort_never_raises`
    - flow 檔既有的 `test_d_a_child_that_runs_too_long_is_killed_and_the_result_is_unknown`
- **M 風控 RC-213～RC-216**
  - 由 `scratchpad/cg2out/build_doc2.py` 從 `work/reviews/2026-11-17-正式登記說明套用後單項確認RC213至RC216-風控.md` 抽出再寫入，沒有手打。
  - 驗證腳本新增 `RC213_REPORT` 與 `FINAL_BLOCKS`（RC-213、RC-214、RC-215、RC-216），逐字核對：
    - RC-209 的核對改為 RC-213；
    - RC-216 的狀態行取代原本寫死的常數；
    - 並檢查舊的「待風控單項確認後才交給 CEO」已不存在。
  - 竄改測試涵蓋被改的 RC-213、RC-214、RC-215、RC-216 與被移除的 RC-213，都會讓驗證失敗（`test_the_verifier_has_teeth`）。

## 驗證

**全套（head `9d5bbf4`，兩個版本同時在背景跑）**

| 環境 | 結果 | 耗時 | 輸出 |
|---|---|---|---|
| Python 3.12.3（專屬 venv `venv312-devops`） | 1 failed、12619 passed、2 xfailed、1 warning | 2104.48s | `scratchpad/cg2out/full2_312.txt` |
| Python 3.13.17（`venv313-devops`） | 1 failed、12619 passed、2 xfailed、34 warnings | 1907.15s | `scratchpad/cg2out/full2_313.txt` |

- 唯一失敗的是 `test_the_review_refs_all_exist_at_head`，失敗內容只列 `work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md` 與 `work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md`。兩個檔落檔後會轉綠。
- 3.13 的 34 個 ResourceWarning 是既有的，與本次無關。
- 兩邊 `ruff check`、`ruff format --check`、`mypy app tests`（542 個檔）皆全過。

**「不得動」零 diff**
- 指令：`git diff --name-only 7b3fef0f HEAD -- <清單>`，輸出為空。
- 清單：`app/`、三個 harness helper、`scripts/pipeline_acceptance_real.py`、`uv.lock`、backend 與 repo 根的 `.gitattributes`、`work/research`、`work/dispatch/.gitattributes`、`pipeline-acceptance.bat`。
- 本輪我自己改的檔：`cg2_register.py`、`verify_cg2_instruction.py`、`cg2_register_world.py`、`test_cg2_register_addendum3.py`、`test_cg2_register_values.py`，與說明文件。其餘差異是 merge 帶進來的 ADR、`work/reviews` 與追蹤清單。
- `app/` tree id 常數不變（`9c157d86…`）。

**驗證腳本輸出（`python scripts/verify_cg2_instruction.py`，結束碼 0，共 35 行 OK，全文在 `scratchpad/cg2out/verify_out2.txt`）**
- 以下列出本輪新增或變動的行，其餘行（RC-182、區塊五、RC-186b、RC-187、RC-195、RC-202～RC-208、RC-210、RC-211、四列 RC-200/201、原有的字面與程式固定句核對）與上一輪相同且全為 OK：
```
OK   RC-213 verbatim, exactly once (1)
OK   RC-214 verbatim, exactly once (1)
OK   RC-215 verbatim, exactly once (1)
OK   RC-216 verbatim, exactly once (1)
OK   the old status wording is gone
OK   the replaced RC-209 block is not named or left in the own text
OK   the backup file names are the ones the script makes
OK   no awaiting-risk marker is left
OK   no guarantee wording in the own text (found [])
```

**說明文件的 diff 摘要**（`git diff 7b3fef0f HEAD -- work/dispatch/2026-11-17-正式登記操作說明-CEO.md`：4 處、5 行新增、3 行刪除）
1. 第 3 行檔頭狀態：「已套用風控 RC-185～RC-211，待風控單項確認後才交給 CEO」→ RC-216 的句子「已套用風控 RC-185～RC-216，風控單項確認通過；M-9 最終審查通過、PR 合併後才交給 CEO」。
2. 第二節最後一行（NSSM 那行）之後新增一行：RC-215「執行預檢之前，也請先看第四節最後一條…」。
3. 第四節第四條：改為 RC-213 的版本（RC-209 的其餘條列文字與 RC-213 相同）。
4. 第八節 `port_listening` 那列的「您要做的事」：改為 RC-214。
- 除此之外沒有改動說明文件的任何其他字。

**新的 `script_sha256_lf`**
- `ee70d11cf0b930075e3adeb747c4e5eea4075d485c190505581ecaefc3be26c0`（`apps/stock-desk/backend/scripts/cg2_register.py` 在 `9d5bbf4` 以 LF 正規化後的 sha256）。上一輪的值已失效，預檢回貼要在這個版本重做。

## 下一步

1. coordinator：兩個最終審查紀錄（`2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md`、`2026-11-17-CG2登記PR-M9最終審查-qa.md`）落檔後，路徑必須與 `REAL_PINS.review_refs` 逐字相同，預期失敗的測試才會轉綠，`review_refs_missing` 也才不再 STOP。
2. coordinator：RC-212 的人工核對（merge commit 是 `git_head` 的祖先、`app/` 與兩份文件沒有 diff、`script_sha256_lf` 與 `code_digest` 在 `git_head` 重算相等）要用新的 `script_sha256_lf` 做。
3. 沒有新增需要風控審的畫面字句或自擬說明字句。Windows 上沒有實測的部分與上一輪相同，另外 Windows 上 `Popen` 的 kill 與 Ctrl+C 傳遞、kill 後 10 秒等待的行為也沒有實測。

相關路徑（皆在 `/home/user/AICompany/.claude/worktrees/agent-a8e9a751d60cca098/` 之下）：
- `apps/stock-desk/backend/scripts/cg2_register.py`
- `apps/stock-desk/backend/scripts/verify_cg2_instruction.py`
- `apps/stock-desk/backend/tests/test_cg2_register_addendum3.py`
- `apps/stock-desk/backend/tests/test_cg2_register_values.py`
- `apps/stock-desk/backend/tests/cg2_register_world.py`
- `work/dispatch/2026-11-17-正式登記操作說明-CEO.md`

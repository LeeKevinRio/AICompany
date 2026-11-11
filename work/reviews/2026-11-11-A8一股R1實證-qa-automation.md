# A8 缺 total_deploy 時 1 股 R1 的測試實證

- 審查者：qa-automation
- 日期：2026-11-11
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
**推論成立，但前提有兩處要補充。** A8（規則集已確認、total_deploy 鍵不存在）下，賣出結算會建立現金鍵，下一次 `evaluate_today` 會 commit 一張 1 股的 R1 買進列，實跑為 `("R1","buy",1,批次1)`。
- 補充一：第一次評估時，賣出被結算之前，現金鍵不存在，買單被現金底線擋掉。這和推論 4 相符。
- 補充二：推論沒提到，要讓賣出能發生，必須先有一個 open 批次。A8 下 app 做不出 open 批次（買進需要現金，A8 沒有現金），所以我用 `store.save_batch` 直接種入。實務上這表示 A8 的前面還需要「某處先出現過 open 批次」，這一步我沒有實證，只能直接種入。
- 補充三：情境的第一版用 S1 停損，結果被 S3 組合熔斷全凍結擋住（`freeze_until` 寫入，R 系列進場全不執行），Thursday 沒有買進列。這是我第一版情境的問題，改成價格上漲觸發賣出後，推論才成立。賣出實際是 **P3（賣 100 股）**，不是 P1，因為價格上漲 20% 時引擎的仲裁結果是 P3。

## 各部門回報
測試檔：`/home/user/AICompany/.claude/worktrees/agent-ad1d10ea47f8916a6/apps/stock-desk/backend/tests/test_a8_td_missing_evidence.py`（共 5 條，只新增測試，未動 `app/`）。

情境：2330 是被賣出的標的，成本 100，持有 300 股，賣出日與結算日價格 120。2317 是進場標的，全程平盤 100，3 個 planned 批次。日期為 TUESDAY 8/11（賣出日）、WEDNESDAY 8/12（結算日）、THURSDAY 8/13（再評估日）。

| 測試 | 斷言的實際值 | 入口 |
|---|---|---|
| `test_a8_precondition_has_no_total_deploy_and_no_cash` | `rule_set_confirmed_at` 存在；`total_deploy`、`cash` 都不存在 | 產品入口：`confirm_rule_set`、`ensure_batches`。用 sqlite 唯讀查 tmp_path 的 db |
| (c) `test_c_a8_settled_sell_creates_cash_key` | 賣出日產生 `[(2330,"P3",100)]`，結算前無 cash 鍵；`settle_pending` 後 `cash` 鍵出現，值 = 12000（120×100）；`total_deploy` 仍不存在 | 產品入口：`evaluate_today`、`settle_pending`。唯一種入：2330#1 open 批次 |
| (a) `test_a_a8_cash_from_sell_then_evaluation_commits_one_share_r1_buy` | 賣出日 2317 買單為空，被現金底線擋下。賣出結算後 THURSDAY 評估，2317 的買進為 `[("R1","buy",1,1)]`，`pending_directives()` 含 `(2317,批次1,1股)`，`total_deploy` 仍不存在 | 產品入口：`evaluate_today`、`settle_pending`、`pending_directives`。唯一種入：2330#1 open 批次 |
| (b) `test_b_a8_without_cash_key_buys_are_all_dropped` | 同樣 A8，但 2330 持平不賣：THURSDAY 評估無任何買進列，`pending_directives()==[]`，`cash` 與 `total_deploy` 都不存在 | 產品入口：`evaluate_today`。唯一種入：2330#1 open 批次 |
| (d) `test_d_control_with_total_deploy_r1_buy_is_sized_from_it` | 同一組行情與批次，先 `set_capital(1,000,000, TD 1,000,000)`：賣出日 2317 批次 1 的 R1 買進 = **666 股**（對比 1 股）；結算後 THURSDAY 為批次 2，也是 666 | 產品入口：`set_capital`、`evaluate_today`、`settle_pending`。唯一種入：2330#1 open 批次 |

(d) 比對的是賣出日的批次 1，因為控制組在賣出日就有現金，批次 1 當天即成交，THURSDAY 已輪到批次 2，批次編號不同於 (a)。

被擋下的位置，依讀碼與實跑的 warning 文字：
- A8 無現金鍵：`engine.py` 的 `_apply_cash_floor`（約 1043 行起）預算 ≤ 0，輸出 `SHRINK_TO_ZERO_NOTE`（實跑 warning 為「鐵律①現金 30%：2317 第 1 批進場後將跌破現金下限，本批不進場。」）。
- S1 版本情境：被 S3 凍結擋下，R 系列進場不執行。這是情境設計問題，不是產品缺陷。
- 1 股的來源：`planned_batch_shares` 在 TD=0 時 `max(1, …)` = 1。

直接 SQL 種入的項目：無寫入，只有唯讀的 `SELECT key,value FROM playbook_state`。未碰 `data/*.db`，未讀 `.env`。

另有一個意外觀察，附帶回報：THURSDAY 的 A8 評估也 commit 了 2330 的 R1 買進 1 股。2330 另有 planned 批次，也同樣用 TD=0 計算。我只斷言 2317，2330 那行只在除錯輸出看到，沒有寫進斷言。

## 驗證
- `ruff check tests/test_a8_td_missing_evidence.py`：All checks passed；`ruff format --check`：1 file already formatted。
- 單檔：`pytest tests/test_a8_td_missing_evidence.py --no-cov`：5 passed。
- 全套：`python -m pytest -q --cov=app --cov-fail-under=90`：**9913 passed, 1 skipped, 2 xfailed, 34 warnings in 773.34s**；TOTAL 覆蓋率 **97.62%**，門檻 90% 達成。
- 環境註記：worktree 沒有自己的 venv，我借用主 checkout 的 `.venv/bin/python` 跑 pytest，匯入的 `app` 路徑確認是 worktree 內的（印出 `app.__file__`）。
- commit：`test: 以實跑驗證 A8 缺 total_deploy 時賣出建立現金鍵後產生 1 股 R1 買進列`，結尾兩行依指示。
- push：`git push -u origin test/a8-td-missing-evidence` 一次成功，無重試。
- **head SHA：d746c7c1088624a43b54f59091534fb976aa22bf**

## 下一步
1. 風控／tech-architect 可據此把 B 段的「可能」改為「實跑確認」。但要注意，第一個前提（A8 下 open 批次從何而來）目前仍是未實證的種入。
2. 此分支目前 `product/stock-desk` 尚無 `td_basis` / `portfolio_and_stamp`（N-210a 未合入），所以評估走的是 `portfolio_state()` 直讀。N-210a 合入後，建議由 qa-reviewer 重跑 (a)，確認 `td_basis` 為 null 的列行為不變。
3. 此測試是在鎖定「現況行為」的證據，不是在宣告它正確。若 CEO 之後選 B2（程式修正，A8 下不出 R 進場），(a) 這條要隨之改為斷言不出單，由實作者連同修正一起改，不是我單獨弱化。
4. 交 qa-reviewer 審查。

---

## coordinator 註記（2026-11-11，依 CEO #139 工作規則）
- 分類：結果與 TA 推論相符（機制成立），依規則第二節第 4 點只登錄，不開新一輪審查。
- 新資訊：A8 下要有賣出，必須先有 open 批次；測試是以 `store.save_batch` 直接種入。「產品入口做不出 A8 加 open 批次」這一點**未實證**，只是這次做不出來。
- coordinator 定案（CEO 可推翻）：
  - 「A8 加 open 批次在產品內是否可達」登錄為凍結後待辦，N-207 部署後再排。
  - 分支 `test/a8-td-missing-evidence`（head `d746c7c1088624a43b54f59091534fb976aa22bf`）暫不合入，留作證據；N-210a 實作 RC-108 條件 3 的測試時可取用同一情境。
  - CEO #138 的 P-8b 方案偏保守，不需更動；風控 RC109-K、ADR-0044 補充一註記 3 的字面（「可能」）仍為真，不改。
- 全套測試數字（9913 passed）是 qa-automation 自行回報，尚無第二人重跑。

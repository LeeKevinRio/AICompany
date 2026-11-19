# 接線 PR 預先實作交件

- 審查者：dev-lead
- 日期：2026-11-19
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

接線 PR 已預先做完，推到 `origin/feat/nm5-wiring`，head 是 `d01bd9eeb89ed97c9dea695a30d7bbf24ee98a7d`。分支依派工建立：從 `9d5bbf48` 開出，之後四次 merge `origin/product/stock-desk`，最後一次取到 `4f72888`。

範圍清單裡不需裁示的項目都已實作，coordinator 中途三次補充也都納入：缺日特性測試、補充八（定稿第二版）、兩行缺日加註（風控 RC-230、RC-233／RC-234 定稿）。

全套測試在 3.12 與 3.13 各跑一次，都是 2 失敗、12698 通過。之後我修好其中一支，再用 3.12 與 3.13 各跑一次預測相關子集：2938 通過，剩 1 支失敗。這一支就是派工預告的 CG-2 一鍵檔 `app/` tree id 測試，退役方式等 TA 裁示（Q-1）。全套在這次修正之後沒有重跑，理由見「驗證」。

這個分支在登記完成前不合併。

## 各部門回報

**dev-lead：commit 一覽（不含 merge）**

| commit | 說明 |
|---|---|
| `3964aa2fd27bf15db785b701bce650184c1de34a` | docs：範圍清單 |
| `4144462c1a3c1471d05bb4af923ccbe3b8661c51` | feat：F-2 視窗（W-4） |
| `8706a2b1db2f69ee7bb61d5c5eb4ee47f7b92a3f` | feat：重審觸發 WARNING（W-5），另含 `ledger_store` |
| `7ad24bd130bc8902e822803dc3cec8d5d7a593d7` | feat：scheduler 註冊 `forecast_record`（W-1～W-3） |
| `8f3b21661f742e62a3067de0fe531f4b1f24ea96` | test：缺日特性測試（W-8） |
| `ba6459f0038d42453099adf1608c7c50f36aae01` | docs：`app/forecast/__init__.py` 說明（W-6） |
| `604398fdca488c4435c8b8d60445a10b824b9e17` | docs：範圍清單補缺日項目 |
| `4a75616b16f5c668e19deb26208a512df4b13e3d` | feat：第一行缺日加註與守門測試（W-9） |
| `cf221fcfee7d9fa467fb29e606a2a49546c97a48` | test：補「缺 T 本身」的特性測試 |
| `d1ac085c2a500f0b7b675a86c15a6a0efc90151b` | docs：範圍清單補補充八 |
| `6069a9768d39d3eef441563be9f3e655a4c86e61` | feat：第二行加註 |
| `cfcd8dd0b75c0a7d7513e03c07a00cee245c4e2d` | docs：範圍清單補第二行 |
| `d01bd9eeb89ed97c9dea695a30d7bbf24ee98a7d` | fix：`f2_status` 改經 `_read`（HEAD） |

**範圍清單逐項狀態**

清單檔：`/home/user/AICompany/.claude/worktrees/agent-a36eaaf09f5b7743b/work/reviews/2026-11-19-接線PR範圍清單-dev-lead.md`（已用 `git show --stat` 確認有進 commit）。

- **W-1 scheduler 註冊 job**：完成。
  - 平日 22:10、23:10（Asia/Taipei），另在啟動後 3 分鐘補跑一次；`max_instances=1`、`coalesce=True`。
  - scheduler 只 import `app.forecast.recorder`。
  - 測試在 `tests/test_forecast_scheduler_wiring.py`：觸發時點、下次觸發時刻、啟動補跑、job 沒有時間參數、K-3 的 import（AST）與可達集合、`load_benchmark is load_market_benchmark`、scheduler 不呼叫 bootstrap 等寫入函式。
  - `tests/test_forecast_recorder.py` 依原本預留的掛鉤改成已接線：`WIRED_REFERRERS={"scheduler.py"}`、`test_the_scheduler_imports_the_recorder_at_module_level`、`test_s4a_the_job_passes_the_index_loader_itself`。
- **W-2 `test_forecast_gate_closed.py`**：已改寫為「只允許 `forecast_record`，仍然沒有 route」。
- **W-3 schema 不存在／登記表為空**：完成。
  - 測試：`test_without_the_ledger_schema_the_run_is_refused_and_nothing_is_created`、`test_a_missing_main_db_file_is_not_created`、`test_an_empty_registry_closes_the_gate_and_records_nothing`、`test_the_guarded_job_logs_the_refusal_and_survives`。
- **W-4 F-2 視窗（補充五第 1 點，C5-3）**：完成。
  - 計數與成立與否只在 `store.f2_status` 導出；`report.f2_window` 已移除。
  - `tests/test_forecast_f2_window.py` 共 26 項，涵蓋 S-10a 第 1 點列出的每一種情形，另有 AST 檢查（平日函式與 T2 共用一個）。
  - `test_forecast_report.py::test_status_counts_the_f2_window` 已改為驗新輸出。
- **W-5 重審觸發 WARNING（補充五第 2 點，C5-4）**：完成。
  - 測試在 `tests/test_forecast_review_warning.py`：四種情形逐一比對 outcome 與 `content_hash` 不變；用真實時鐘走到 T2；沒有 D_v 時不記；判定在 end 列之後；`KeyboardInterrupt` 不被吞。
- **W-6 docstring**：完成。
- **W-7 零差異與雜湊證明**：見「驗證」。
- **W-8 缺日特性測試**：完成，在 `tests/test_forecast_missing_session_characterization.py`，含「中間缺一個 session」與「缺 T 本身」兩組。
  - 守門測試在 `tests/test_forecast_gap_disclosure.py`：`DropReason`、outcome 與 DDL、`session_calendar.py` 頂層只有 `is_final`、休市資料（與 `9d5bbf48` 相同）。
- **W-9 兩行加註**：完成。
  - 字面都用腳本從風控報告抽出寫入常數，沒有手打；測試從同一份報告抽出逐字比對（`tests/approved_copy.py`）。
  - RC-230 的四件事：`test_1`～`test_4`。
  - RC-234 的七項：`test_r1`～`test_r7`，另釘住 `N_HAT_NOTE` 與 `9d5bbf48` 逐字相同。
  - harness 的檢查加在 `tests/test_forecast_pipeline_harness.py`（+6 行）。
- **流程項 P-1～P-8**：不改程式，由 qa 與 coordinator 在合併時核對。P-2（CG-3 備份紀錄）與 P-8（帳外缺日比對）的值由 coordinator 填，我沒有編造。

**harness 與雜湊受加註影響的情形（coordinator 要求逐項列出）**
- `tests/forecast_pipeline_harness.py`（harness 本體）沒有改動。
- harness 的 `result.output` 會多出第一行加註，所以 `output_sha256` 會變。沒有任何測試釘住這個值，`render_summary` 與真實資料一鍵檔的白名單也都不含 output，因此不受影響。
- 第二行加註不進 harness 輸出，有測試證明。
- `code_digest` 改變：`9d5bbf48` 時是多少沒有記錄，目前 HEAD 的值是 `7a200746dfb5dd28c5720c0b0ecd0d1a52df9272052df82b702cf5250f9ed7a6`。這是改動 `app/forecast` 與 scheduler 的預期結果，沒有測試釘住它。
- 已登記的 definition 與 rules 雜湊都沒有變。

## 驗證

**全套測試（含 coverage）**
- 3.12 與 3.13 的結果相同：2 失敗、12698 通過、2 xfailed；coverage 3.12 為 97.71%、3.13 為 97.82%。
- 失敗 1：`test_cg2_register_values.py::test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout`。原因是 `app/` 改了，tree id 不再是 `9c157d86…`，正是派工預告的那一支。
- 失敗 2：`test_forecast_store.py::test_f4_connect_is_opened_only_on_the_write_path`。原因是 `f2_status` 沒有經 `_read` 讀帳。已由 `d01bd9ee` 修正，修法是讓它經 `_read` 讀，既有測試沒有改。
- 修正之後，3.12 與 3.13 各跑一次預測相關子集（`test_forecast_*`、`test_pipeline_acceptance_real*`、`test_cg2_*`、`test_scheduler*`、`test_outlook_*`）：都是 1 失敗、2938 通過，失敗的只有上面那支 R-1。
- 修正之後全套沒有重跑：那個 commit 只改了 store 的讀取方式，而上述子集涵蓋所有用到 store 的測試。

**ruff 與 mypy**
- ruff check、ruff format --check、mypy app tests：3.12 與 3.13 都全過。
- 最後一個修正之後，只對 `app` 補跑了 ruff 與 mypy，都通過。

**「不得動」的檔案**
- 以 `git diff --stat 9d5bbf48 HEAD -- apps/stock-desk` 檢查，只列出 16 個檔：`app/forecast` 四檔、`app/scheduler.py`，其餘都是 tests。
- 因此以下全部零差異：`uv.lock`、所有 `.gitattributes`、`app/dirdef/`、規則 YAML、`app/outlook/**`、`app/data/**`、`app/services/**`、`scripts/`（含 cg2 兩支與 `pipeline_acceptance_real.py`）、三個 `.bat`、cg2 相關測試、harness 三檔。
- `work/research`、`work/dispatch` 的凍結檔（事先宣告、C-8 紀錄、兩份 CEO 操作說明）也是零差異；這兩個資料夾只多了 product 分支 merge 進來的新檔。

**已登記的雜湊**
- 目前的值：`dirdef-v1.0` 為 `2a58bca6…` 與 `4cc1fe80…`；h3 為 `f4f366a5…`；h5 為 `0a385de3…`。
- 這些值與 `scripts/cg2_register.py`、`test_cg2_registration_values.py` 的常數相同。M-4、M-5、RC-163 的測試在兩個 Python 版本都通過。

**測試輸出檔**（scratchpad）：`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/full-312.log`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/full-313.log`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fc-312.log`、`/tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/fc-313.log`。

**鐵則遵守情形**：沒有讀 `.env`、沒有碰 `data/*.db`、沒有執行 `.bat`、沒有 force push、rebase 或 amend。

## 下一步

**待 TA 裁示（每題可以直接回答）**
- **Q-1：CG-2 一鍵檔怎麼退役？** 請選一項：
  - (a) 本 PR 刪除兩支腳本、兩個 `.bat` 與它們的全部測試；
  - (b) 只刪 R-1 tree id 那一支測試；
  - (c) 檔案全部保留，把該測試標成 skip 並附理由；
  - (d) 另開 PR 退役，在那之前接受這一支紅燈。
  另請回答：退役要不要 ADR 依據？裁示前我完全不動這些檔案。
- **Q-2：CG-3 備份紀錄要不要加 CI 測試把關？** 加了之後，本分支在 coordinator 填值前會是紅燈，填值後才轉綠。要或不要？
- **Q-3：scheduler 要不要限定正式目標？** 也就是加上「目標必須是 `<backend>/data/stock-desk.db`，且沒有設 `STOCK_DESK_DB_PATH`」。要或不要？
- **Q-4：F-2 第二句（第 0 相位格點遺失率 > 20%）要不要在 `report status` 加門檻判定？** 加的話會多一句使用者面字面。要或不要？

**自定解讀（I-1～I-9 的全文在範圍清單第三節）**
- 主 DB 用 `resolve_db_path()`。
- scheduler 透過 `recorder.ledger_store` 取得 store（K-3）。
- 主 DB 檔不存在時跳過這次執行，並記一行 WARNING。
- misfire 沿用 APScheduler 預設。
- F-2 的起點含 S_c 當日；沒有任何執行時標「視窗未滿（尚無執行）」；分母為 0 時，只要有 `inputs_not_ready` 日就判成立。
- WARNING 判定全部前瞻 claim，在任何 outcome 的 end 列之後都執行。
- scheduler 每次執行記一行 INFO。
- 另外有一項我自己決定的改動，請 qa 特別看：`test_forecast_report.py` 的 `d4_violations` 只對第二行加註的核可字面，免除「n̂ 必須附固定標示」那一條；其餘規則照查。

**新增的使用者面字面（`report status`，送風控）**
- 段標題：`ADR-0030 失效條件 F-2（每 20 個平日為一個視窗，逐平日滾動；只含執行狀態，不含任何標籤或對照）：`。原擬稿含「連續」，被 D-4 第 5 點的禁詞測試擋下，所以改掉。
- 完整視窗：`  {claim}：最近一個完整視窗 {起}～{迄}，沒有 late = 0 紀錄的定案 session 數 {a}，inputs_not_ready 日數 {b}，分母 {d}，{成立／未成立}；自起點以來曾否成立：{是／否}`
- 視窗未滿：`  {claim}：視窗未滿（自起點以來 {k} 個平日：{起}～{迄}），沒有 late = 0 紀錄的定案 session 數 {a}，inputs_not_ready 日數 {b}，{成立／視窗未滿}`
- `  {claim}：視窗未滿（尚無執行）`
- `  {claim}：視窗未滿`
- 舊的三句 F-2 字面已移除。
- 兩行加註都是風控定稿，不是新擬：RC-230 與 RC-233／RC-234。之後要增修須重送風控。
- log 行（英文，只進 log）有四句，全文列在範圍清單第五節。

**給 coordinator**
- 合併前要補齊三樣：P-2 的 CG-3 備份值（落點與格式見範圍清單）、P-8 的帳外缺日比對 commit 與 CEO 確認紀錄、CEO 本機執行 `report verify --all` 的結果。
- 若 RC-231 的後續又改動加註，請通知我。
- 歸屬標記：commit 結尾我用的是 system reminder 指定的 `Co-Authored-By: Claude Opus 5.5`，沒有用派工訊息寫的 `Claude Fable 5.2`。如果要改，請告知。

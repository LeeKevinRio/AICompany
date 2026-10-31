# 任務單：FD-9 多目的地比價探索＋三項收尾

- 狀態：done
- 發起人：CEO（2026-10-29「繼續下一批」；總經理定題）
- 目前負責：product-manager（PRD 定稿）→ tech-architect（評估）
- 相關文件：`work/flight-deals-FD-9-PRD.md`、`work/flight-deals-FD-6-PRD.md`（探索模式）、`work/tasks/FD-6.md`、`work/tasks/FD-8.md`、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted）、`apps/flight-deals/README.md`

## 目標

1. 多目的地比價：固定一組日期，對 2～8 個目的地各查一次（N 個目的地＝N 次對外查詢），結果依總價由低到高，失敗或未查的目的地顯示原因；單人（固定 1 位成人）、經濟艙預設。
2. 沿用探索的額度保留（`exploration_reserve_for_scans`＝12）、節流、斷路器、24 小時重用、7 天清除；額度不足時依輸入順序部分完成，其餘標未查詢。
3. 結果可一鍵預填新增監看（不自動送出）。
4. 三項收尾：`/scan` 失敗輪次文案改「本輪排定 N 組日期」、詳情頁「所有價格已出發」空狀態文案與「尚未查到價格」區分、`/watch` 最短＝最長時顯示「旅程 N 天」。

範圍外：多人、商務艙優先、多目的地監看、Travelpayouts、LINE、Telegram `/compare`（預設不做）、取消與強制重查、價格預測與建議語氣。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-C、AC-R、AC-S、AC-W、AC-K、AC-F）。摘要：

- 輸入：2～8 個目的地可逐個加入與移除；重複、等於出發地、少於 2、多於 8、日期不合法皆 422；人數固定 1 成人，傳入多人被忽略。
- 執行：N 個目的地恰 N 次查詢；可用額度＝全域剩餘減保留 12，不足時前面的目的地照查、其餘 `skipped`；可用額度 0 不建立比價；失敗不中斷；斷路器轉開或額度耗盡標已中斷；重啟標已中斷。
- 結果：價格由低到高，同價依輸入順序，無價格列在後且顯示原因；每列有 tfs 連結與建立監看；文案無建議／保證語氣（送 risk-compliance-officer）。
- 重用：24 小時同條件不重查（與順序無關），中斷不重用，7 天清除且不傷監看。
- 收尾：三項文案依 AC-F1～F3；其餘既有文案與期望值逐字不變。

## tech-architect 評估關卡需回覆

1. 資料模型：新表或重用 `exploration`／`exploration_cell` 加 `kind`；對探索既有行為的影響（PRD 待 tech-architect 1）。
2. `condition_key` 版本與正規化（目的地集合、日期兩種輸入的正規化）。
3. 每個目的地一格 cell 的映射與 `skipped` 原因存放。
4. 城市代碼與轄下機場的重複判定。
5. 頁面路由、入口（`/explore` 內）與和探索的互斥機制。
6. 額度口徑（全域剩餘減保留 12）與部分完成的計數；排程順延機制是否共用。
7. migration 0007 與 `pre-v7` 備份、清除作業擴充。
8. 進度端點白名單與輪詢上限；是否增補 ADR-0002。
9. 若認為某需求不可行，須退回 product-manager 並附理由；評估通過才可推進至 `build`。

## 待回覆的預設值

CEO（未覆議照預設，不阻擋開工）：
1. 不做 Telegram `/compare`（CEO 尚未建 bot）。
2. 額度不足時部分完成，其餘目的地標「未查詢」，依輸入順序優先（與 FD-6 整體拒絕不同）。
3. 目的地數量 2～8。

其餘：tech-architect 1～9、risk-compliance-officer 10、qa-automation 11、qa-e2e 12（見 PRD 開放問題）。

## 後續關卡（預期）

- spec → build：tech-architect 評估通過；dev-lead 實作（含前端：自動完成多選、進度輪詢、結果表）。
- review：qa-reviewer（含 Codex）。必過項：額度邊界、部分完成、重複與 422、並列排序、重用鍵、探索既有行為不變、不污染監看、三項收尾與既有期望值。
- risk-gate：risk-compliance-officer 審查所有新增使用者文案（FR-S5、AC-S6、三項收尾）。
- UI 實機：qa-e2e（或總經理代跑）；真實 N 次查詢驗收由總經理或實作者實跑附結果；無人值守依 e2e-fallback。

## 交接紀錄

- 2026-10-29 CEO：繼續下一批；總經理定題多目的地比價＋三項收尾
- 2026-10-29 product-manager → tech-architect：FD-9 PRD v0.1 與驗收條件已定。請依上列評估關卡回覆，特別是資料模型（新表或重用探索表）、condition_key 正規化、城市代碼重複判定與 migration 0007；CEO 三項預設值未覆議即照預設。
- 2026-10-29 tech-architect → 總經理：新表 `comparison`／`comparison_cell`（migration 0007 純新增）、`ComparisonService` 平行於探索（只共用 `SourceQuery`／`cell_update`）、共用 `batch_create_lock`＋交叉 active 檢查互斥、獨立子頁 `/explore/compare` 與 `/comparisons/{id}`、三項收尾落點（F1 `command_scan_result_message`、F2 `top_empty_note`、F3 `stay_range_label`）；C-61～C-70 已落 ADR-0002 FD-9 增補。總經理裁：額度不足整體拒絕、TYO＋NRT 算重複、日期下限今天、不做 `/compare`。PM 回填 PRD 五處。狀態 spec → build，dev-lead 與 frontend-engineer 並行。

## 實作紀錄（2026-10-31）

- frontend-engineer → 總經理：`compare.html`、`comparison.html` 新建；`explore.html` 入口卡片與進行中提示；`settings.html`、`base.html` nav、`watch_detail.html`（`top_empty_note`、`stay_label`）；`app.js`（`combo-select` 事件、多選 chip、`collectCompare`、`pollProgress` 抽共用、`data-show-when` 支援逗號 AND）；`app.css`（chip、entry-card、comparison 表）。Jinja2 編譯與 `node --check` 通過；ui-delivery-checklist 逐項自檢過。契約外新增 DOM id 已列報告。
- dev-lead → 總經理：migration 0007、`ComparisonSpec`／`ComparisonTarget`／`validate_comparison`、`ComparisonService`、`ComparisonViewService`、四條路由與 `from_comparison` 預填、排程 `compare:`／`comparison-purge`、三項收尾；新測試 +190（1147 passed）；ruff／format／mypy 全綠。

### C-70 效能原始輸出（FD-6 基準庫 20 監看、5 萬輪，加 50 筆比價×8 格）
```
rows: {'watch': 20, 'scan_run': 50000, 'comparison': 50, 'comparison_cell': 400} sqlite 3.45.1
compare_page: median 6.0 ms  runs=[6.1, 5.9, 5.9, 6.3, 5.5, 5.6, 6.6, 6.1, 6.1, 5.6]
comparison_page(26): median 2.2 ms  runs=[2.2, 2.1, 2.6, 2.1, 2.2, 2.1, 2.3, 2.1, 1.9, 2.4]
```
門檻 <100 ms，通過。8 個目的地真實比價總耗時待總經理 e2e 實測。

### AC-F4
直接斷言三字串的既有期望值：0 項改動。`tests/test_migration_0006.py::build_v5_db` 改 `only_up_to(6)`（harness 釘版本，斷言未動，同 FD-8 前例）。

### 總經理裁決（dev-lead 4 點、frontend 2 點確認）
1. `test_migration_0006` harness 釘版本：接受。
2. 預覽句顯示 `hourly_left` 而非已扣保留的 `available`：交 frontend 修正（PRD FR-C11）。
3. 比價 24h 重用／7 天保留沿用 `exploration_reuse_hours`／`exploration_retention_days`，不加專屬設定：接受。
4. blocked 與 error 共用「被擋或查詢失敗」：接受（PRD FR-S3）。
5. `disclaimer`／`reference_note` 只在 done／failed 顯示：改為任何狀態都顯示（AC-S5），交 frontend。
6. 目的地欄「東京成田 NRT NRT」代碼重複：只渲染 `destination_label`，交 frontend。
已知未做：健康頁「資料維護」各表筆數未列比價表；Telegram `/status` 不提比價（ADR 已列缺口）。偶發 `test_scheduler_jobs_and_next_run_time` 時序競態（既有，單跑 10 次皆過）。
- 2026-10-31 risk-compliance-officer → 總經理：**修改後核可**。文案皆為事實陳述與操作確認，無建議／保證／催促，最低價列無推薦標示，免責常駐。required 1：無價格列需說明「未參與比較，不代表沒有機票或價格較高」（總經理擬 `COMPARISON_NO_PRICE_NOTE`，風控短審）。recommended：r2 no_data 口徑統一「查無航班」、r3 最近比價表「已查 N／共 M」與 24h 標示、r4 結果頁補「只比較這一組日期」、r5 F1 改「本輪排定 N 組日期，未對外查詢」、r6 fallback 字串移入 messages.py。總經理裁：全部本批收掉，dev-lead 與 frontend 並行。重審觸發：結果表新增標記／強調、排序規則變更、新增推播或 Telegram 比價輸出、更動 DISCLAIMER／REFERENCE_NOTE／ORDER_NOTE 語意、縮短 24h 提醒。
- 2026-10-31 risk-compliance-officer 複審 → **APPROVE**：R1 `COMPARISON_NO_PRICE_NOTE` 字句、位置（排序說明後、表格前）、常駐與 static texts 皆合格；r2～r6 全部解決。suggested：`exploration.html` 既有寫死的 stale 備援字串（FD-6）日後比照 r6 移入 messages.py。重審觸發條件追加 `COMPARISON_NO_PRICE_NOTE`、`COMPARISON_SINGLE_DATE_NOTE` 語意變動。
- 2026-10-31 qa-reviewer → 總經理：**PASS，BLOCKING_ISSUES=false**。互斥（單一 `batch_create_lock`、create 全程持鎖、對稱檢查 active）、額度（三表不重疊、每格前重算）、驗證邊界、0007 CHECK 與 C-61 逐條對應、Web 安全（無 innerHTML、status 四欄 no-store、`from_comparison` 嚴格驗證）、三項收尾、UI 清單皆通過。Codex 兩個 high（跨小時歸屬漏計、排隊後額度被掃描用掉）核實後駁回（既有設計／C-63 明定行為）。殘留 low：`idx_comparison_started` 用不到；路徑 int 無上限（既有模式）；`_record()` 的 `isdecimal` 可加 `isascii`；0007 destinations／日期 CHECK 只驗形狀；`schedule` 在鎖外的極短幽靈 active 窗口。唯讀判準常數未觸及。

## 總經理 e2e（2026-10-31，內建瀏覽器＋頁內 JS 驅動；窗格未繪製故以 JS／API 代點）
- 服務重啟套用 0007：`schema_version` 7、`comparison`／`comparison_cell` 存在、`pre-v7` 備份、integrity ok。
- **發現並修正中**：瀏覽器沿用舊版 `app.js` 快取（transferSize 0、無 `initCompareForm`），比價頁 combobox 全未初始化 → 交 dev-lead 加 `?v=<hash>` cache-busting（納入本批）。強制重抓後一切正常。
- C-69 (1) `/explore` 入口卡片「前往多目的地比價」✔；(2) 表單預設 TPE／來回／經濟艙、無人數欄位、固定 1 位成人說明 ✔；(3) 輸入「東」列 TYO／NRT／HND…、「大阪」「首爾」皆有城市＋機場選項；加入 chip 顯示「東京成田 NRT」；重複 NRT 不重加；aria-live「已加入 東京成田 NRT，目前 2 個目的地」✔；(5) 預覽「預計查詢 4 次／本小時可用 47 次（已保留 12 次給排程）」隨 chip 數更新 ✔；(4) TYO＋NRT 送出 → 422「目的地 TYO 與 NRT 重複（城市代碼已包含其機場）」顯示在欄位旁、`aria-invalid` ✔；移除 TYO chip 後送出 3 個目的地 → 導向 `/comparisons/1` ✔。
- (12) 真實比價 TPE → NRT／OSA／SEL 12/20–12/25：OSA TWD 11,056（泰國獅航直飛）、NRT TWD 13,462（台灣虎航直飛）依價排序；第 3 格 SEL 因 devops-sre 同時實測 dev-up.bat 重啟服務而「未查詢（已中斷）」，狀態「已中斷・已查 2／共 3・對外查詢 2 次」、說明「服務重啟，比價中斷；未查的目的地不會自動補查」——中斷恢復路徵意外獲得真實驗證 ✔；可用額度 47 → 45 與 2 次查詢相符 ✔。(7) R1／r4 兩句常駐、免責常駐、排序說明 ✔。status API 四欄、no-store ✔。
- (9) `from_comparison=1&destination=OSA` 預填 TPE→OSA、12/20–12/25、1 成人、提示「已由比價帶入條件，請確認後送出」；SEL（skipped）與 id 999 → 空白表單＋「找不到對應的比價結果，請手動填寫」；watch 筆數不變 ✔。最近比價表顯示「已中斷」「TWD 11,056 大阪 OSA」「已查 2／共 3」✔。
- 2026-10-31 CEO 追加：「啟動時若之前已有實例在跑，要取消前一個」。devops-sre → 總經理：`dev-up.bat` 的 `:ensure_app_free` 改為不詢問、直接 `[REPLACE] taskkill` 舊 flight-deals 程序；`:ensure_port_free` 先處理 app 再處理 port，占用者屬 flight-deals 直接停、非 flight-deals 才保留 Y/N；新增 `--no-pause`、`--skip-pull`；啟動命令改為 `uv run flight-deals --port 8795 --replace`。實測兩次（`cmd /c dev-up.bat --no-pause --skip-pull < NUL`）：舊 PID 被停、新實例 `[OK]`、首頁 200、約 5.6 秒；未實測「非 flight-deals 占用 port」分支。總經理 e2e 的比價 1 即因此次實測重啟而「已中斷」。
- 2026-10-31 總經理 e2e：375px 頁面不橫向捲動、只有 `.table-wrap`（310 → 880）捲動且 `role=region`／tabindex 0 ✔；免責與參考說明常駐於表格前 ✔。
- 2026-10-31 dev-lead → 總經理：cache-busting（`static_version()` sha256 前 12 碼經 `page()` 注入，`base.html` 兩檔加 `?v=`；`tests/test_static_version.py`）與 CLI `--replace`（`take_lock()`：讀鎖檔 pid、ctypes 判存活、taskkill／SIGTERM、每 0.5 秒重試 15 秒；`autostart.py` 命令列加 `--replace`；`tests/test_replace.py`；`test_autostart.py` 期望命令列改含 `--replace`，列 AC-F4 例外）。1161 passed。
- 2026-10-31 qa-reviewer 複審追加 delta → **PASS，BLOCKING_ISSUES=false**。殘留：terminate 例外未納入重試（medium）、殺前比對 image 名（medium）、ctypes `argtypes`／`restype`（low）、dev-up.bat port 判定字串過寬（low–medium）。總經理裁：四項本批收掉。
- 2026-10-31 總經理實測新版 dev-up.bat（`--no-pause --skip-pull < NUL`）：`[REPLACE]` 停掉舊 PID，新實例帶 `--replace`，首頁 200 ✔。
- 2026-10-31 CEO 追加：「每次更新好直接更新上去就好，不用每次再打開網頁，一直跳有點煩」→ devops-sre：dev-up.bat 預設不開瀏覽器、加 `--open` 才開；port 判定改三個精確樣式；實測取代成功、未開瀏覧器。
- 2026-10-31 總經理 e2e（API，無干擾）：缺 header 403；建立 202 → id 2；同條件再送 200 joined；不同條件 409 busy（附 `progress_url=/comparisons/2`）；比價期間送探索 409 busy；3／3 完成「已完成・已查 3／共 3・對外查詢 3 次」：首爾仁川 ICN TWD 9,308（虎航直飛）、大阪關西 KIX TWD 11,056（泰獅航直飛）、東京成田 NRT TWD 13,462（虎航直飛）依價排序；目的地順序不同再送 → 200 reused；可用額度 45 → 43（含 12:38 啟動補跑 1 次滾出一小時窗）✔。C-69 (6) 進度頁自動載入與 (10)(11) 互斥提示以 API 驗；(8)(9)(12) 完成。
- 2026-10-31 dev-lead → 總經理：`--replace` 三項硬化完成（terminate 例外記 log 後續重試、殺前比對 image／cmdline 身分、ctypes argtypes／restype）；新測試 `test_terminate_failure_still_retries_then_refuses_with_exit_2`、`test_foreign_process_is_never_terminated`、`test_identity_check_on_real_processes`；非 Windows 身分檢查路徑無實測。1166 passed。
- 2026-10-31 總經理：最終驗證 ruff／format／mypy／pytest 1166 passed；以新版 dev-up.bat 重啟：`[REPLACE]` 取代舊 PID、「Already-open pages only need a refresh.」、未開瀏覽器、首頁 200。狀態 build → **done**。
  未做／後續：Telegram `/status` 不提比價（ADR 已列）；健康頁各表筆數未列比價表；dev-up.bat「非 flight-deals 占用 8795」詢問分支與 `--open` 未實測；`exploration.html` 既有寫死 stale 字串日後移入 messages.py；QA low 數項（`idx_comparison_started`、路徑 int 上限、`isdecimal`、CHECK 只驗形狀、schedule 鎖外窗口）。

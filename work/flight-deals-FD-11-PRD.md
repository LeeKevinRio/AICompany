# flight-deals FD-11 PRD：穩定性與技術債收斂＋首個版本 v0.1.0

- 版本：v0.1
- 日期：2026-11-01
- 發起：CEO「繼續下一批」；總經理定題

## 背景與目標

FD-1（2026-10-26）至 FD-10（2026-10-31）連續十批功能，`pyproject.toml` 版本仍為 0.1.0、無 `CHANGELOG.md`、無 git tag；各批 QA 留下的 low 項目累積未清。本批**不做新功能**，目標：

1. 收斂 FD-8～FD-10 累積的 low 項目與測試穩定性。
2. 重整 README、新增 CHANGELOG，並以 `v0.1.0` 完成首次定版（依 `.claude/skills/release-flow/SKILL.md`）。

## 使用者與情境

單一使用者（CEO）自用。使用者可感知的變動僅兩處：超大 ID 的路徑由 500 改為 404（或等價的乾淨回應）、探索超量時 422 訊息多帶出實際次數與上限（R5）。其餘皆為內部品質。

## 範圍內 / 範圍外

範圍內：下列工作項 W1～W17、文件與版本。

範圍外（non-goals）：任何新功能；任何面向使用者的新文案（R5 的 422 訊息除外）；Travelpayouts；Telegram 實測（待 CEO 建 bot）；`observations_for_watch` 守門測試的改動（僅記錄）；多人情境。

## 功能需求（工作項清單）

每項：來源、做法、驗收。

### A. 資料與查詢
- **W1**（FD-9）`idx_comparison_started` 用不到：`queries_used_since` 用 `COALESCE(started_at, created_at)`。做法：由 tech-architect 裁定改查詢或移除／改建索引。驗收：以 `EXPLAIN QUERY PLAN` 輸出佐證；查詢結果與額度計算不變。
- **W2**（FD-9）0007 的 `destinations` 與日期 CHECK 只驗形狀（`AAAABBB`、`2026-99-99` 可過）。做法：建議不重建表，改在 domain／service 層驗證（真實 IATA 形狀分隔、`date.fromisoformat`）。驗收：兩種壞值皆在寫入前被拒（422 或 domain 例外），既有資料不受影響。
- **W3**（FD-9）`comparison_views._record()` 用 `str.isdecimal()` 接受 Unicode 十進位數字。做法：加 `isascii()`。驗收：全形／阿拉伯-印度數字輸入被拒，ASCII 行為不變。
- **W4**（FD-9）`ComparisonService.create` 的 `schedule` 在 lock 外，失敗時有極短「幽靈 active」窗口。做法：schedule 失敗時回復狀態為 failed／取消，或移入 lock 內，由 tech-architect 裁定。驗收：以注入 schedule 失敗的測試證明不留 active 比價，額度不被占住。

### B. 路由與輸入
- **W5**（FD-9）`/comparisons/{id}`、`/api/comparisons/{id}/status`、探索對應路由的路徑 `int` 無上限，超大整數在 sqlite 綁定時 `OverflowError` 變 500。做法：路徑參數加上限（值由 tech-architect 定）。驗收：超大整數（如 `2**63`、`10**30`）回 404／422，不得 500；正常 ID 不變。
- **W6**（FD-10）探索預估格數不扣「回程超出可查上限」的日子。做法：伺服端提供的每月各星期可查日數扣除回程超限日，前端沿用加總。驗收：最後一兩個月的預估與伺服端實際格數一致；伺服端仍為準。
- **W7**（FD-10，風控 R5）探索超量 422 訊息帶出實際需要次數與 31 上限（例：「需要 N 次，上限 31，請縮小月份範圍或減少星期」）。做法：service 層訊息帶參數。驗收：訊息含實際次數與 31；經 risk-compliance-officer 審查（唯一新增文案）。

### C. 測試穩定性
- **W8**（FD-10）`tests/test_retention.py::test_scheduler_jobs_and_next_run_time` 偶發失敗（真實時鐘、`cmdscan:42` job 在斷言前執行並移除，伴隨 `JobLookupError`）。做法：改為確定性測試（注入時鐘／不啟動真實 scheduler 或凍結 trigger），改法由 tech-architect 裁定。驗收：該測試單獨連跑 50 次無失敗、無 `JobLookupError` 警告。
- **W9**（FD-10）pytest 全套 1～2 個 warning。做法：查出來源並修正根因，不以 filterwarnings 壓掉。驗收：全套 0 warning。
- **W10**（FD-8）`tests/test_snapshot_read.py` 的 `observations_for_watch` 呼叫端精確清單守門。做法：僅記錄於任務卡與 CHANGELOG 開發備註，不改。驗收：測試檔 diff 為 0。

### D. 啟動腳本
- **W11**（FD-9）`dev-up.bat`「非 flight-deals 程序占用 8795」詢問分支與 `--open` 未實測。做法：實機（或總經理代跑）各跑一次並貼原始輸出；發現缺陷才修。驗收：兩路徑皆有實測紀錄；無法互動則依 `e2e-fallback` 註明。

### E. 文件與版本
- **W12** README 由 tech-writer 對照現況重整：功能清單 FD-1～FD-10、啟動方式（含 `--replace`／`--open`／`--no-pause`／`--skip-pull`）、Telegram 設定、資料保留、備份檔說明（`pre-vN`）。驗收：文件所述指令與參數逐一對照 `dev-up.bat` 與程式實況，無過期描述。
- **W13** 新增 `CHANGELOG.md`：`## [0.1.0] - 2026-11-01`，Added／Changed／Fixed 分類，寫對使用者的影響而非內部實作。驗收：符合 release-flow 格式；涵蓋 FD-1～FD-10 主要能力與本批 Fixed。
- **W14** 版號維持 0.1.0（首次定版）。驗收：`pyproject.toml` 版本與 CHANGELOG 一致；若程式內另有版本字串須一致。
- **W15** `git tag -a v0.1.0`（annotated），指向本批全部合併完成且 qa-reviewer 通過後的 commit。**不 push**，待 CEO 同意。驗收：`git tag -l` 可見、`git ls-remote --tags` 不可見。

## 驗收條件

Given/When/Then：

- W1：Given 含 comparison 資料的 DB，When 執行 `queries_used_since` 的查詢計畫，Then 不再出現與索引設計矛盾（索引被用到或索引已依裁定移除），且額度數值與修改前相同。
- W2：Given 新建比價帶 `AAAABBB` 或 `2026-99-99`，When 呼叫 create，Then 被拒絕且未寫入任何列。
- W3：Given `_record()` 收到 `"１２３"`，When 解析，Then 視為無效；`"123"` 照常。
- W4：Given schedule 會丟例外，When create，Then 不存在 active 比價且額度未被占用。
- W5：Given 路徑 ID 為 `10**30`，When GET 三類路由，Then 回 404／422，非 500。
- W6：Given 探索最後月份含超出可查上限的回程，When 前端估算，Then 預估等於伺服端實際格數。
- W7：Given 探索需 N>31 次，When 送出，Then 422 且訊息含 N 與 31；risk-compliance-officer APPROVE。
- W8：Given 該測試，When 連跑 50 次，Then 全過、無 `JobLookupError`。
- W9：Given 全套，When 執行 pytest，Then 0 warning。
- W10：Given `test_snapshot_read.py`，When 本批結束，Then 檔案 diff 為 0。
- W11：Given 8795 被非 flight-deals 程序占用／帶 `--open`，When 執行 dev-up.bat，Then 行為符合設計，並附原始輸出。
- W12～W14：Given 本批完成，When 對照文件，Then 所述與現況一致；版號與 CHANGELOG 一致。
- W15：Given 全部通過，When 查 tag，Then 本機有 `v0.1.0`、遠端沒有。

## 驗收總則

1. 既有 1357 個測試不改期望值，除與上述工作項直接相關者；每一處修改須在任務卡逐條列出（比照 AC-F4）。
2. pytest 全套**連跑 3 次**無偶發失敗、無 warning；ruff、format、mypy 通過。
3. 既有頁面輸出不變（FD-9／FD-10 快照測試維持綠燈；W7 訊息為唯一允許的文案差異）。
4. migration 不新增，除非 tech-architect 裁定 W1 或 W2 必須用 0009；若新增須附 `pre-v9` 備份與舊資料完整性測試。
5. 無祕密入 commit；`.env` 未被追蹤。

## 風險與依賴

- W1／W2 若走 migration 0009，風險升高（重建 comparison 表）；建議不走。
- W8 的測試改法若動到 scheduler 生產碼，須避免改變實際排程行為。
- README 與 CHANGELOG 依賴 W1～W11 結果，宜最後定稿。
- tag 須在 review 通過、最終 commit 確定後才打，避免 tag 指向過期 commit。

## 開放問題

給 tech-architect：
1. W1：移除索引是否需 migration 0009？或改查詢形式（如條件改寫）讓索引可用而不動 schema？
2. W2：CHECK 強化是否值得重建 comparison 表？PM 建議不重建，改在 domain 守；請確認。
3. W5：路徑參數上限值（建議 SQLite INTEGER 上限 `2**63-1`，或更嚴格如 `2**31-1`）與實作方式（`Path(le=…)` 或統一 helper）。
4. W8：偶發測試改法（注入時鐘、停用特定 job，或改斷言 trigger 定義而非 next_run_time）。
5. W14：「版號 0.1.0」的定義——僅 `pyproject.toml`，還是 app 內另有版本顯示處也要對齊？是否在健康頁顯示版本（若是新功能則不做）。
6. W4：schedule 失敗的補償做法。

## CEO 待決

只有一項：是否同意 push tag `v0.1.0`。**預設不 push**，本批完成後本機保留 tag 等待指示。

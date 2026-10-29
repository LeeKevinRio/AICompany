# PRD：flight-deals FD-8 180 天穩態列表效能

- 版本：v0.1（spec）
- 發起人：CEO（2026-10-29 決定先做列表效能）
- 撰寫：product-manager
- 任務單：`work/tasks/FD-8.md`
- 產品分支：`product/flight-deals`
- 前置文件：`work/tasks/FD-7.md`（「dev-lead 實測紀錄」與結尾後續建議）、`work/flight-deals-FD-7-PRD.md`（FR-R5、FR-R6 數字不變原則、FR-H2）、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted；C-34 列表 SQL 次數、C-49～C-54 保護快照依賴與歷史最低價的清除規則、C-52 列表效能門檻 300 ms）、`apps/flight-deals/README.md`

## 背景與目標

FD-7 實測顯示：FD-6 基準庫（20 監看、5 萬筆 scan_run）列表 23 ms，通過 < 100 ms；但 180 天穩態（20 監看、每天 4 輪、14,400 輪、172,800 筆觀測）列表 1,165 ms，超過 ADR-0002 C-52 的 300 ms 門檻，FD-7 已依 ADR 開後續任務，即本批。

慢因（FD-7 已確認）：列表沿用 C-34 做法，`observations_for_watch(watch_id, revision)` 把每個監看目前 revision 的全部觀測（穩態約 8,640 筆／監看）讀進 Python 再建 `Snapshot`；耗時隨觀測總數成長，與 scan_run 筆數無關。同一條讀取路徑也被每日摘要（`services/digest.py`）、Telegram `/list`／`/watch`／`/scan` 結果（`services/commands.py`）、詳情頁（`services/views.py:522`）使用。

CEO 現況只用單人經濟艙、監看約 4 個，但要撐住 20 個監看、每天 4 輪、180 天保留的穩態。目前尚未感受到慢，本批是在資料長大前把耗時與觀測總數脫鉤。

技術方向（FD-7 建議，供 tech-architect 評估，非規格）：FD-7 已定義「保護集合」（`storage/repository.py` 的 `retention_snapshot_runs`），FR-R6 測試已證明清掉保護集合以外的觀測後，`list_page`、`DigestService.compose`、`/list` 輸出字串完全相同。因此讀取端可改為只向 SQL 取這個保護集合，讓列表、摘要、指令回覆的耗時不隨觀測總數成長。

保護集合（沿用 FD-7，本批不改定義）：
- 目前 revision、每組（出發日, 回程日, price_kind, currency）且未出發：最新 2 筆（快照與「前一輪」）加台北零時前最新 1 筆（摘要「前一日」）。
- 每（price_kind, currency）不限出發日：最低價 1 筆（`min_amount`）。

成功指標（可驗證行為）：
- 對同一資料庫，新舊讀取法的所有使用者可見輸出完全相同。
- 180 天穩態列表 < 300 ms（目標 < 100 ms），摘要組字與 `/list` 亦 < 300 ms。
- 耗時不隨觀測總數成長（同一組保護集合、不同觀測總量下耗時相近）。

## 使用者與情境

- 使用者：CEO 本人，單一使用者，Windows 本機服務，單人經濟艙，網頁與 Telegram 皆用。
- 情境 A：半年後監看增至 20 個，打開網頁列表，頁面仍秒開。
- 情境 B：手機傳 `/list` 或 `/watch 3`，回覆速度不因資料庫變大而變慢。
- 情境 C：每日摘要排程組字時不拖慢同時段的掃描與網頁請求。
- 情境 D：CEO 完全察覺不到任何文案、數字、排版變化（純效能改動）。

## 範圍內 / 範圍外

範圍內：
- 列表頁（`ViewService.list_page`）、每日摘要（`DigestService.compose`）、Telegram `/list`、`/watch`（前 3 組日期）、`/scan` 結果訊息、列表漲跌與摘要漲跌的資料讀取改為只取保護集合。
- 必要時新增索引，或 migration 0006 純新增（不改既有資料）。
- 以 180 天穩態基準庫實測並記入任務單。

範圍外（non-goals）：
- 不改任何使用者可見的頁面與文案（網頁、Telegram 回覆、摘要、通知皆逐字不變）。
- 不改清除規則（保留期、最近 N 輪、保護集合定義、備份、VACUUM 皆不動）。
- 不改 schema 的既有資料；只允許新增索引或 migration 0006 純新增（不刪欄、不改欄型別、不重建既有資料表）。
- 詳情頁的「最近價格紀錄」歷史表與趨勢圖維持讀全部或既有 limit，不在本批範圍。
- 單人以外的多人／艙等／全家情境（CEO 2026-10-29 指示單人優先）。
- 探索模式、掃描寫入路徑、Telegram 輪詢、設定頁的任何變更。
- 技術選型與實作細節（由 tech-architect 與實作者決定）。

## 功能需求（逐條編號）

### 一、讀取端改版（FR-Q）

- FR-Q1 保護集合讀取：列表、每日摘要、`/list`、`/watch`、`/scan` 結果所需的「目前快照」「前一輪」「前一日」「歷史最低價」資料，改為只讀取保護集合範圍內的觀測，不再把目前 revision 的全部觀測載入記憶體。
- FR-Q2 輸出等價：對任一資料庫（不論是否已被清除），新讀取法與舊讀取法（讀全部觀測）產生的 `list_page` 結果、`DigestService.compose` 輸出、`/list`、`/watch` 前 3 組日期、`/scan` 結果訊息、列表漲跌、摘要漲跌必須逐字相同。
- FR-Q3 耗時與觀測總數脫鉤：上述讀取的耗時由「監看數與保護集合大小」決定，不隨單一監看的觀測總筆數成長。
- FR-Q4 多 revision：監看修改條件產生新 revision 後，讀取只對應目前 revision；舊 revision 觀測不得混入快照、漲跌或最低價（與舊讀取法一致）。
- FR-Q5 SQL 次數：列表頁 SQL 次數不得比 FD-7 多（沿用 C-34：1 次加每監看 1 次；若整批一查詢則只會更少）。
- FR-Q6 共用同一資料來源：列表、摘要、指令回覆維持共用同一條讀取路徑，不得產生兩份計算（沿用 FD-7 開放問題 13 精神）。
- FR-Q7 寫入不退步：新增索引（若有）不得使一輪掃描寫入耗時超過 FD-7 的 120%。
- FR-Q8 migration（若有）：採 0006 純新增（索引等），沿用 migration 前 `pre-v<N>` 備份與回復慣例；新資料庫不產生備份。

## 驗收條件（每條需求至少一組 Given/When/Then）

測試通則：自動化測試使用假資料源與假時鐘，不連外網；效能數字須實跑並將原始輸出與環境附於任務單。

- AC-Q1（輸出等價，對應 FR-Q1、Q2）Given 同一份資料庫（複製兩份，或同一庫兩種讀取法並行比對）；When 分別以舊讀取法（讀全部觀測）與新讀取法執行 `list_page`、`DigestService.compose`、`/list`、`/watch` 前 3 組日期、`/scan` 結果訊息；Then 輸出字串／結構完全相同，包含列表漲跌與摘要漲跌。測試情境至少涵蓋：
  - 彈性窗輪換取樣下，某組日期最新觀測落在 N 輪之前；
  - 已出發日期（不應出現在快照，但歷史最低價規則仍依 C-49～C-54）；
  - 他幣別（同一監看同時有多個 currency）；
  - 快取價（price_kind 不同）；
  - 多個 revision（舊 revision 觀測不得混入）；
  - 台北零時前後各有觀測（摘要「前一日」）；
  - 無任何觀測、僅 1 筆觀測、僅單一出發日等邊界；
  - 已被清除過的庫與未清除的庫各一份。
- AC-Q2（revision 隔離，對應 FR-Q4）Given 監看修改條件後有 revision 1 與 2 的觀測，舊 revision 價格較低；When 列表與摘要組字；Then 最低價與漲跌只反映目前 revision，與舊讀取法相同。
- AC-Q3（效能門檻，對應 FR-Q3）Given 180 天穩態基準庫（20 監看、14,400 輪、172,800 筆觀測，沿用 FD-7 `bench_fd7.py` 方法）；When `ViewService.list_page()` 暖機 1 次後取 10 次中位數；Then 中位數 < 300 ms（目標 < 100 ms）。When `DigestService.compose` 組字；Then < 300 ms。When `/list` 指令處理（假 Telegram，不含網路）；Then < 300 ms。When `/watch` 前 3 與 `/scan` 結果訊息組字；Then 各 < 300 ms。
- AC-Q4（不退步，對應 FR-Q3）Given FD-6 基準庫（20 監看、5 萬筆 scan_run、每筆 12 組結果）；When `list_page()` 中位數；Then 仍 < 100 ms（FD-7 為 23.0 ms，不得顯著變差）。
- AC-Q5（與觀測總數脫鉤，對應 FR-Q3）Given 同樣的保護集合內容、觀測總量分別為 1 倍與 3 倍的兩份庫；When 量測列表耗時；Then 兩者差距在量測誤差範圍內（具體容許值由 tech-architect 與 qa-automation 於評估時定，預設 3 倍庫不超過 1 倍庫的 150%）。
- AC-Q6（寫入不退步，對應 FR-Q7）Given 180 天穩態資料；When 一輪掃描寫入（`ScanService.scan_watch` 12 組，FD-7 基準方法）；Then 耗時不超過 FD-7 實測值（v5 121.9 ms）的 120%，約 146 ms，並記入任務單。
- AC-Q7（SQL 次數，對應 FR-Q5）Given 計數 fake repository；When `list_page()` 於 20 個監看；Then SQL 次數不多於 FD-7（1 加每監看 1 次，即 21 次）。
- AC-Q8（單一資料來源，對應 FR-Q6）Given 程式碼檢視與測試；When 檢查列表、摘要、`/list`、`/watch`、`/scan` 結果的快照來源；Then 皆來自同一個讀取函式／服務，無第二份獨立計算。
- AC-Q9（使用者可見不變，對應範圍外）Given 全部網頁頁面與 Telegram 回覆樣板；When 與 FD-7 結束時版本比對；Then 模板、文案、排版逐字不變（既有 snapshot 測試與 FD-7 新樣本比對，全部通過，且既有 922 項測試不因本批修改期望值）。
- AC-Q10（migration，若有，對應 FR-Q8）Given v5 資料庫（含 FD-7 正式庫副本）；When 套用 migration 0006；Then 備份檔 `pre-v6` 產生且可開啟，各表筆數遷移前後不變，`foreign_key_check` 空、`integrity_check` ok，新增索引存在；Given 全新資料庫；Then 不產生備份。Given 無 migration（架構判定只改查詢）；Then 本條不適用，任務單註明。
- AC-Q11（清除相容，對應 FR-Q2）Given 一份穩態庫；When 先以舊讀取法記錄輸出，再執行每日清除，再以新讀取法輸出；Then 三者完全相同（沿用 FD-7 FR-R6 測試並擴充納入新讀取法）。
- AC-Q12（詳情頁不變）Given 詳情頁；When 開啟；Then 最近價格紀錄歷史表與趨勢圖內容與 FD-7 相同，未被誤縮為保護集合。

## 風險與依賴

- 數字漂移風險（高）：新讀取若漏了保護集合的某一類（例如歷史最低價、台北零時前那筆），列表或摘要數字會悄悄不同，且 CEO 不易察覺。因應：AC-Q1 的新舊並行比對與完整情境矩陣；比對測試納入 CI，不可僅看單一固定資料。
- 定義分歧風險（中）：讀取端的保護集合 SQL 與清除端 `retention_snapshot_runs` 若各寫一份，日後改一邊會讓兩者失去等價。見開放問題 2。
- 詳情頁誤改風險（中）：詳情頁與列表共用部分讀取函式，需分清「快照用」與「歷史表用」，避免歷史表被縮短（AC-Q12）。
- migration 風險（低）：若只新增索引風險低，仍須沿用備份慣例。
- 量測風險（低）：效能數字依機器與資料而異；須用與 FD-7 相同腳本與資料方法，原始輸出附任務單。
- 依賴：ADR-0002 C-34、C-49～C-54；`bench_fd7.py` 基準方法（FD-7 dev-lead 紀錄）；若技術方向牴觸 accepted ADR，以 ADR 為準並由 tech-architect 增補。
- 風控閘門：不新增、不修改任何面向使用者文案，原則上不適用章程風險閘門（AC-Q9 保證文案不變）。
- UI 驗收：頁面無變更，qa-e2e 僅需抽驗列表頁與詳情頁載入正常、數字與改前相同；無人值守起不了 dev server 時依 e2e-fallback。

## 開放問題（待 CEO 或其他部門回答）

1. 【tech-architect】查詢粒度：一監看一查詢（維持 C-34 的 1 加每監看 1 次）還是整批一查詢（所有監看一次取回，SQL 次數更少，但 SQL 較複雜）？兩者在 20 監看、穩態資料下的耗時與可維護性比較。
2. 【tech-architect】單一定義原則：讀取端的保護集合 SQL 是否與清除端（`retention_snapshot_runs`）共用同一段定義（同一個函式或同一個 SQL 片段），以保證兩者永遠等價？若不共用，如何以測試鎖住兩者等價？
3. 【tech-architect】索引設計：是否需要新索引（例如針對（revision, 出發日, 回程日, price_kind, currency, 觀測時間）的複合索引，或最低價查詢用索引）？若需要，是否走 migration 0006？對掃描寫入成本的評估（FR-Q7 的 120% 上限）。
4. 【tech-architect】介面：`Snapshot` 介面與其呼叫端是否維持不變，只換資料來源（PM 預期：維持不變，以降低牽動範圍與數字漂移風險）？若不維持，影響哪些呼叫端？
5. 【tech-architect】詳情頁：「快照用」讀取與「歷史表用」讀取如何切開，確保詳情頁歷史不受影響（AC-Q12）？
6. 【tech-architect】AC-Q5 與觀測總數脫鉤的量測方法與容許值是否合理；是否需增補 ADR-0002（預期以增補小節或修訂 C-34、C-52 即可）。
7. 【qa-automation】新舊並行比對測試的資料產生器：如何涵蓋 AC-Q1 的全部情境矩陣，並保留舊讀取法作為測試用的參考實作（reference implementation）。
8. 【CEO，預設：驗收門檻 < 300 ms 為通過，目標 < 100 ms 為努力方向】若架構評估認為 < 100 ms 需明顯增加複雜度，是否接受只達 < 300 ms？
9. 【qa-e2e】列表頁、詳情頁、`/list` 的實機抽驗路徑；180 天穩態基準庫的建置與量測環境。

## 變更紀錄

- 2026-10-29 v0.1 初稿，由 product-manager 依 CEO「先做列表效能」與 FD-7 實測紀錄撰寫。

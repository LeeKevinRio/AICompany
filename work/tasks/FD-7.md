# 任務單：FD-7 Telegram 雙向指令與資料保留／效能

- 狀態：done
- 發起人：總經理（CEO 定調）
- 目前負責：dev-lead、frontend-engineer
- 相關文件：`work/flight-deals-FD-7-PRD.md`、`work/flight-deals-PRD.md`（FD-1，FR-C、FR-E）、`work/flight-deals-FD-4-PRD.md`（每日摘要、telegram-setup）、`work/flight-deals-FD-6-PRD.md`（探索、額度）、`work/tasks/FD-6.md`（底部待辦：scan_run 索引與清除策略）、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted；D-4、D-5、FD-4 增補、C-17、C-34）、`apps/flight-deals/README.md`

## 目標

1. Telegram 雙向指令：服務在 Telegram 已設定且指令功能開啟時，背景長輪詢，只處理設定 chat id 的訊息，其他來源忽略（不回覆、不記錄內容，只計數）。
2. 八個指令：`/help`、`/list`、`/watch <編號>`、`/scan <編號>`（完成後主動回結果）、`/digest`（不受同日限制，記為「手動摘要」）、`/status`、`/pause <編號>`、`/resume <編號>`；未知指令簡短說明，不接受自由文字，不得修改條件。
3. 指令與回覆記入通知紀錄（類型「指令」）；設定頁可關閉（預設開啟）；健康頁顯示「指令輪詢：運作中／已關閉／未設定 Telegram」與最近一次指令時間。
4. 資料保留：掃描與觀測預設 180 天（下限 30）、通知 365 天、探索沿用 7 天；每日自動清除；清除前當日首次備份；每監看至少保留最近 N 輪（預設 10）；清除前後列表與摘要數字不變。
5. 健康頁顯示資料庫大小、各表筆數、上次清除與壓縮結果；VACUUM 預設每週一次於摘要時間之後。
6. 列表補索引：5 萬筆 scan_run 下 `list_page` 中位數 < 100 ms（FD-6 為 200 ms）。

範圍外：群組多人、inline keyboard、語音、LINE、匯出、bot 修改條件、網頁手動清除／還原按鈕。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-P1 至 AC-P10、AC-K1 至 AC-K18、AC-L1 至 AC-L7、AC-R1 至 AC-R11、AC-S1 至 AC-S11、AC-H1 至 AC-H7）。摘要：

- 授權：非授權 chat 零回覆零記錄只計數；重啟不重複執行；積壓指令超過 10 分鐘不執行；輪詢失敗不影響主服務；token 不外洩（含所有錯誤路徑）。
- 指令：每個指令回覆要素齊全；`/scan` 完成後主動回結果；`/digest` 記為手動、不佔排程額度；`/pause`／`/resume` 確認回覆；錯誤格式與未知指令簡短說明；長度不超過推播上限；無禁用字。
- 紀錄與設定：通知紀錄類型「指令」「手動摘要」；關閉後不輪詢；健康頁三種狀態。
- 保留與清除：保留期邊界、最近 N 輪保留、清除前後最低價與漲跌相同、當日備份存在且早於刪除、原子性、去重相容、壓縮週期與條件。
- 效能：列表中位數 < 100 ms、SQL 次數不增、寫入與健康頁不退步。

## tech-architect 評估關卡需回覆

1. 輪詢執行模型：背景長輪詢如何不佔排程 worker、offset 持久化（防重複執行）、逾時與退避、關閉開關後停止、與排程鎖綁定（單一輪詢者）。
2. `telegram-setup` 與服務輪詢的 `getUpdates` 互斥處理（PRD 開放問題 2），並修正 FD-4 SW10「服務執行中也能使用精靈」說法。
3. 資料模型與 migration：新通知類型（指令、手動摘要）的 `notification.kind` 擴充、索引 migration，是否合併，備份與回復慣例；指令紀錄欄位與遮蔽；未授權計數存放。
4. 保留與清除：清除的批次與原子性、與掃描／探索的排程互斥、通知對觀測的外鍵與附屬表（略過事件等）歸屬、去重鍵相容、FR-R6「數字不變」在彈性窗輪換取樣下的額外保留方式（PRD 開放問題 11）。
5. 備份與壓縮：沿用 migration 備份機制或獨立備份檔、保留份數、VACUUM 條件（無掃描／探索、磁碟空間）、週期記錄。
6. 效能：索引設計，達成 100 ms 目標，寫入與健康頁統計成本；統計來源（近似或快取）。
7. 指令資料來源重用 `ViewService` 與摘要組字，避免兩份計算；回覆長度上限。
8. 是否需增補 ADR-0002（預期以增補小節即可；若認為需另開 ADR 請說明）。
9. 評估通過才可推進至 `build`；若認為某需求不可行，須退回 product-manager 並附理由。

## 待回覆的預設值

PRD 開放問題 3（積壓指令超過 10 分鐘不執行）、4（編號 = 監看 id）、5（大小寫不分、接受 @bot 後綴）、6（`/scan` 無單監看冷卻）、7（清除每日、摘要後 30 分鐘；壓縮每週）、8（N=10 可調、下限 3）、9（備份保留 7 份）、10（無網頁手動清除／還原）、14（輪詢失敗不推播告警）。未覆議則照預設。開放問題 1、2、11、13 待 tech-architect；2 亦需總經理確認；12 待 risk-compliance-officer；15 待 qa-e2e。

## 後續關卡（預期）

- spec → build：tech-architect 評估通過；dev-lead 與 frontend-engineer 分工（設定頁、健康頁）。
- review：qa-reviewer（含 Codex）。必過項：非授權零回覆、不重複執行、token 不外洩、禁用字、清除前後數字不變、備份先於刪除、原子性、列表效能數字與 SQL 次數。
- risk-gate：回覆樣板依 C-17 交 risk-compliance-officer，預期「不適用」。
- UI 實機：qa-e2e（或總經理代跑）；真實 Telegram 收發與 5 萬筆效能量測須附實跑結果。

## 交接紀錄

- 2026-10-29 product-manager → tech-architect：FD-7 PRD v0.1 與驗收條件已定（依總經理定調）。PRD 相對定調新增：未授權計數呈現、離線積壓處理、不重複執行、`getUpdates` 與 telegram-setup 互斥風險、`/digest` 不佔排程額度、清除前後數字不變原則、保留期調降提示與歷史縮短揭露、清除原子性與備份份數、壓縮條件式執行、效能量測條件對齊 FD-6 基準。請依上列評估關卡回覆。
- 2026-10-29 tech-architect → 總經理：評估通過，不另開 ADR；增補小節與 C-49～C-54 落進 ADR-0002（daemon thread 長輪詢、授權與最多執行一次、cmdscan 組合 job、manual_digest、migration 0005 重建 notification 並補五個索引、保護快照依賴與歷史最低價的清除規則、每日備份與每週 VACUUM、列表相關子查詢改寫）。
- 2026-10-29 總經理：PM 新增點全部同意；CEO 層開放問題照預設；Q2／Q4／Q9 裁定精靈不確認 update、編號＝監看 id、備份 7 份；與架構落差 14 項全部照架構。狀態 spec → build，dev-lead 與 frontend-engineer 並行。

## dev-lead 實測紀錄（2026-10-29）

環境：Windows 11、Python 3.11.9、SQLite 3.45.1；腳本 `bench_fd7.py`（由 FD-6 `bench_list.py` 改寫，放 scratchpad `fd7/`），原始輸出：

```
python=3.11.9 sqlite=3.45.1 now=2026-10-29T11:49:25+00:00
base DB rows: {'watch': 20, 'scan_run': 50000, 'price_observation': 0}
1. list_page (50k scan_run, FD-7 SQL): median_ms=23.0 min_ms=22.7 max_ms=33.2
1b. old window SQL alone (same DB): median_ms=171.1 min_ms=168.9 max_ms=173.1
1c. new SQL alone (same DB): median_ms=0.3 min_ms=0.3 max_ms=0.3
3. settings_page cold stats (50k): median_ms=131.5 min_ms=130.0 max_ms=134.6
3b. settings_page warm stats (50k): median_ms=129.2 min_ms=127.9 max_ms=134.1
steady DB rows: {'watch': 20, 'scan_run': 14400, 'price_observation': 172800}
4. list_page (180-day steady state): median_ms=1165.5 min_ms=1162.2 max_ms=1177.7
4b. settings_page cold stats (steady): median_ms=50.8 min_ms=49.9 max_ms=51.7
4c. retention plan (steady, nothing old enough): 644 ms, candidates runs=0 notifications=0
2. scan_watch round, 12 pairs, v4 (before): median_ms=142.5 min_ms=126.1 max_ms=619.3
2. scan_watch round, 12 pairs, v5 (after): median_ms=121.9 min_ms=114.9 max_ms=197.4
5. VACUUM base50k.db: 1.09s, 210.9 MB -> 210.2 MB, integrity_ok=True
5. VACUUM steady180.db: 0.53s, 102.8 MB -> 100.3 MB, integrity_ok=True
```

| 項目 | 條件 | 結果 | 門檻 |
| --- | --- | --- | --- |
| 列表 `list_page()` | FD-6 基準（20 監看、5 萬筆 scan_run、每筆 12 組結果），暖機 1 次後 10 次中位數 | 23.0 ms（列表 SQL 本身 0.3 ms；舊 window SQL 同庫 171 ms） | < 100 ms，通過 |
| 一輪掃描寫入 | 180 天穩態資料，`ScanService.scan_watch` 12 組、即時假資料源，30 次中位數 | v4（無新索引）142.5 ms → v5 121.9 ms（86%） | ≤ 120%，通過 |
| 健康頁 `settings_page()` | 5 萬筆庫，統計快取冷／熱 | 131.5／129.2 ms | < 300 ms，通過 |
| 180 天穩態列表 | 20 監看 × 每天 4 輪 × 180 天 = 14,400 輪、172,800 筆觀測 | **1,165 ms** | > 300 ms，依 ADR 開後續 |
| VACUUM | 5 萬筆庫 211 MB／穩態庫 103 MB | 1.09 s／0.53 s，integrity ok | 記錄 |

180 天穩態列表慢的原因：列表沿用 C-34 的「每監看讀出目前 revision 全部觀測再在 Python 建快照」，穩態下每監看約 8,640 筆、合計 17 萬筆進 Python；與 scan_run 筆數無關（本批索引已讓 scan_run 部分降到 0.3 ms）。後續建議另開任務：觀測查詢改成 SQL 端只取每組日期最新 2 筆加台北零時前 1 筆（與清除的保護集合同一規則），讓列表與摘要不隨觀測總數成長。

### Migration 0005 正式 DB 副本演練

來源 `apps/flight-deals/data/flight-deals.db`（唯讀開啟，以 SQLite backup API 複製到 scratchpad `mig5/`，未動正式檔）：

```
copied schema_version: 4
before: {'watch': 4, 'scan_run': 18, 'price_observation': 15, 'alert_state': 0, 'notification': 10, 'notification_item': 6, 'source_health': 1, 'app_setting': 7, 'scheduler_event': 0, 'exploration': 1, 'exploration_cell': 31}
migrate -> 5
after:  （同上，counts equal: True）
foreign_key_check: []
integrity_check: ok
indexes（新增）: notification.ix_notification_created（重建）、ix_notification_observation、notification_item.ix_notification_item_notification、price_observation.ix_price_observation_scan_run、scan_run.ix_scan_run_watch_id、scan_run.ix_scan_run_watch_rev
notification kinds CHECK has command/manual_digest: True
backup: flight-deals.pre-v5.db True schema 4；backup counts equal before: True
```
- 2026-10-29 總經理代跑 e2e（服務重啟套用 0005，pre-v5 備份產生）：健康頁「指令輪詢：未設定 Telegram、本次啟動以來 0 則未授權訊息」、資料維護區塊（168 KB、各表筆數、啟動補跑首次清除 0 筆、首次 VACUUM 168→168 KB、保留期 180／365／10 輪、統計時間每 5 分鐘）；設定頁五個新欄位；`POST /api/settings` 調降 retention_days 60 → notice「下次清除將刪除超過 60 天的資料」、20 → 422、keep_runs 2 → 422；詳情頁「價格紀錄保留最近 180 天」。Telegram 真實收發未驗（CEO 尚未建 bot）。小瑕疵：健康頁「筆數統計時間：統計時間 …」標籤重複（low，交收尾）。
- 2026-10-29 risk-compliance-officer → 總經理：指令回覆模板「修改後核可」（R1 /watch 前 3 名缺 eligible 篩選與查到時間、R2 /scan 結果最低價需附時間與「本輪未更新」註記、R3 /list 缺 stale 與資料過舊標記；r4～r8 建議）；修好前視同否決，修後附新樣本複審。
- 2026-10-29 qa-reviewer → 總經理：FD-7 第一輪 **PASS**（C-49～C-54 全過；Codex 兩個 high 聲稱經核實不採納；1 medium：/scan 例外時待回覆不清除；4 low）。總經理把 ADR 的 C-49 既有例外、索引數量六個、最低價保護不限出發日三處修正落檔。
- 2026-10-29 dev-lead → 總經理：風控 R1～R3／r4～r8 與 QA medium＋4 low 全部修完（新增共用 `services/price_snapshot.cheapest_pairs()`，詳情頁與 `/watch` 同源；`/list`、`/watch`、`/scan` 結果加查到時間、逾時與連續失敗標記、頁尾取樣說明；`_command_scan` 改 try/finally；設定頁徽章 tone、flash notice；零時前保留規則補測試）。922 passed。新樣本重生成。
- 2026-10-29 risk-compliance-officer 複審 → **APPROVE**（R1～R3 已修、無建議／保證／催促語氣；風險閘門仍判「純事實陳述，不適用」）。殘留 recommended：`/scan` 頁尾補時區說明（總經理已補）、失敗輪次「本輪取樣」改「本輪排定」（留）、「旅程 4–4 天」顯示（留 creative-lead／frontend）。重新送審觸發條件 6 項維持。
- 2026-10-29 qa-reviewer 複審 delta → **PASS，BLOCKING_ISSUES=false**（無 critical／high；medium 已修；finally 成功路徑不重複回覆、重拋後 APScheduler 僅記一次錯誤；新測試有實質覆蓋）。殘留 low：`cheapest_pairs` 排序鍵缺第三鍵（總經理已補，與 `snapshot_min` 同序）、詳情頁全部已出發時空狀態文案不精確（留）。
- 2026-10-29 總經理：兩項一行 recommended 補完後重跑 ruff／format／mypy／pytest 922 passed。狀態 build → **done**；Telegram 真實收發與開機自啟登入驗收仍待 CEO 建 bot 後實測；180 天穩態列表 1,165 ms 另開後續任務。

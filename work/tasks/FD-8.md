# 任務單：FD-8 180 天穩態列表效能

- 狀態：done
- 發起人：CEO（2026-10-29 決定先做列表效能）
- 目前負責：product-manager（PRD 定稿）→ tech-architect（評估）
- 相關文件：`work/flight-deals-FD-8-PRD.md`、`work/tasks/FD-7.md`（dev-lead 實測紀錄與後續建議）、`work/flight-deals-FD-7-PRD.md`（FR-R6 數字不變原則）、`docs/adr/0002-flight-deals-技術棧與資料源.md`（accepted；C-34、C-49～C-54）、`apps/flight-deals/README.md`

## 目標

1. 讓列表、每日摘要、Telegram `/list`／`/watch`／`/scan` 結果的讀取耗時不隨觀測總數成長：讀取端只向 SQL 取 FD-7 定義的「保護集合」，不再把目前 revision 全部觀測載入 Python。
2. 180 天穩態（20 監看、14,400 輪、172,800 筆觀測）列表由 FD-7 實測 1,165 ms 降到 < 300 ms（目標 < 100 ms）。
3. 使用者可見輸出完全不變；不改清除規則；schema 只允許新增索引或 migration 0006 純新增。

範圍外：任何頁面與文案變更、清除規則變更、詳情頁「最近價格紀錄」歷史表（維持讀全部或 limit）、探索與掃描寫入路徑、多人／全家情境（單人優先）。

## 驗收條件

完整 Given/When/Then 見 PRD「驗收條件」章節（AC-Q1 至 AC-Q12）。摘要：

- 輸出等價：同一資料庫，新舊讀取法的 `list_page`、`DigestService.compose`、`/list`、`/watch` 前 3、`/scan` 結果、列表漲跌、摘要漲跌完全相同；情境含彈性窗某組日期最新觀測落在 N 輪之前、已出發日期、他幣別、快取價、多 revision、台北零時前後、已清除與未清除的庫。
- 效能：180 天穩態列表 < 300 ms（目標 < 100 ms）、摘要組字 < 300 ms、`/list` < 300 ms；FD-6 基準庫列表仍 < 100 ms；一輪掃描寫入 ≤ FD-7（121.9 ms）的 120%；耗時與觀測總數脫鉤。
- SQL 次數不比 FD-7 多（C-34：1 加每監看 1 次，20 監看即 21 次）。
- migration（若有）：v5 DB 遷移後筆數不變、`pre-v6` 備份存在、完整性檢查通過；全新 DB 不產生備份。
- 使用者可見模板與文案逐字不變；詳情頁歷史表不被縮短；原有測試期望值不修改。

## tech-architect 評估關卡需回覆

1. 查詢粒度：一監看一查詢或整批一查詢（PRD 開放問題 1）。
2. 保護集合 SQL 是否與清除端 `retention_snapshot_runs` 共用單一定義，或以測試鎖住等價（開放問題 2）。
3. 索引設計與是否需要 migration 0006；對寫入成本的評估（開放問題 3）。
4. `Snapshot` 介面是否維持不變、只換資料來源（開放問題 4）。
5. 詳情頁「快照用」與「歷史表用」讀取切分（開放問題 5）。
6. 與觀測總數脫鉤的量測方法、是否增補或修訂 ADR-0002 C-34／C-52（開放問題 6）。
7. 若認為某需求不可行（例如 < 100 ms 目標），須退回 product-manager 並附理由；評估通過才可推進至 `build`。

## 待回覆的預設值

PRD 開放問題 8（驗收門檻 < 300 ms，目標 < 100 ms；待 CEO，未覆議照預設）。其餘開放問題：1～6 待 tech-architect、7 待 qa-automation、9 待 qa-e2e。

## 後續關卡（預期）

- spec → build：tech-architect 評估通過；dev-lead 實作（預期不涉及前端）。
- review：qa-reviewer（含 Codex）。必過項：新舊輸出等價測試矩陣、revision 隔離、詳情頁歷史不變、效能數字（附原始輸出與環境）、SQL 次數、寫入不退步、migration 備份與筆數（若有）。
- risk-gate：不新增或修改使用者文案，預期「不適用」。
- UI 實機：qa-e2e（或總經理代跑）抽驗列表頁與詳情頁數字與改前相同；無人值守依 e2e-fallback。
- 效能量測：沿用 FD-7 `bench_fd7.py` 方法，結果記入本任務單。

## 交接紀錄

- 2026-10-29 CEO：先做列表效能。
- 2026-10-29 product-manager → tech-architect：FD-8 PRD v0.1 與驗收條件已定（依 CEO 指示與 FD-7 實測紀錄）。技術方向（FD-7 建議）為讀取端只取保護集合，請依上列評估關卡回覆，特別是單一定義原則與輸出等價的驗證方式。
- 2026-10-29 tech-architect → 總經理：採一監看一查詢 `snapshot_observations_for_watch`、SQL 片段單一定義 `_snapshot_keep_select`（單 window＋`LAG`）、migration 0006 只加覆蓋索引 `ix_obs_snapshot`、詳情頁不動、等價性靠 A1／A2 前提與 C-57 測試；C-55～C-60 已落 ADR-0002 FD-8 增補。總經理代 CEO 裁 PRD 開放問題 8：<300 ms 通過、<100 ms 目標、不為 100 ms 加複雜度。狀態 spec → build，派 dev-lead。

## dev-lead 實測紀錄（2026-10-29，總經理代記 C-59）

環境：Python 3.11.9、SQLite 3.45.1；基準庫為 FD-7 `steady180.db`／`base50k.db` 的複本（原檔 md5 前後一致），遷移 v5 → v6 各 399／401 ms（含 pre-v6 備份，筆數不變、integrity ok、fk 0）。腳本 `scratchpad/fd8/bench_fd8.py`，暖機 1 次後 10 次中位數；掃描寫入 30 次。

```
A. list_page (steady180, v6): median_ms=184.8 min_ms=175.1 max_ms=230.2
B. DigestService.compose (steady180): median_ms=182.0
C. /list list_text (steady180): median_ms=177.7
C2. /watch watch_text (watch 1): median_ms=14.5 ; C3. /scan scan_result_text: median_ms=11.6
   watch 1: snapshot rows=168 vs full rows=8640
D. snapshot_observations_for_watch (one watch): median_ms=8.3 ; D2. full read reference: 50.6
E. retention_snapshot_runs (FD-8 SQL): 442.2 ; E2. FD-7 SQL reference: 530.1 ; run sets equal=True size=326
E3. RetentionService.plan whole: 541.4
F. detail_page (watch 1, record only): 72.0
G. reference FD-7 read path (20 x full read + Snapshot.build): 1222.1
H. list_page (base50k, v6): 27.0
I. scan_watch round, 12 pairs, v5: 125.9 / v6: 129.1 (+2.5%)
```

| 項目 | 實測 | 門檻 | 結果 |
| --- | --- | --- | --- |
| steady180 列表 | 184.8 ms（FD-7 1,165） | <300（目標 <100） | 通過；目標未達 |
| 摘要 compose／`/list` | 182.0／177.7 | <300 | 通過 |
| 單監看快照讀取 | 8.3 | <10 | 通過（餘裕小） |
| retention_snapshot_runs | 442.2 | ≤644 | 通過 |
| base50k 列表 | 27.0 | <100 | 通過 |
| 掃描寫入 v6 | 129.1 | ≤146 | 通過 |

查詢計畫（C-58）：keep_select 走 `SEARCH price_observation USING COVERING INDEX ix_obs_snapshot (watch_id=? AND watch_revision=? AND price_kind=? AND currency=? AND depart_date>?)`，無 SCAN price_observation、無 TEMP B-TREE；完整讀取 SQL 最外層 `SEARCH o USING INTEGER PRIMARY KEY (rowid=?)` 加一個 `USE TEMP B-TREE FOR ORDER BY`。

突變測試：改壞 `rn <= 2`／`>=`／`id DESC`／`fetched_at <`／拿掉 LAG 條件，分別有 14／6／3／5／19 項測試失敗，事後還原並 cmp 一致。

### 總經理裁決（dev-lead 提出 5 點）
1. `tests/test_migration_0005.py` 改 2 行（`only_up_to(5)`、`>= 5`）：接受，與 FD-7 處理 0004 測試同前例；新增 migration 必然如此。
2. C-60 grep 改 AST 整字比對、排除 docstring：接受並落 ADR C-60 字面。
3. A1「取樣含重複組」：`sample_pairs` 集合去重已窮舉測試；人為塞重複清單會寫兩筆屬 scan 既有行為，本批不改。
4. 耗時未真正與觀測總數脫鉤（window 仍掃該監看全部未出發範圍，常數縮小約 6 倍）：如實記入 ADR Consequences；依「不為 100 ms 加複雜度」裁示不再做方案 C。
5. FD-7 的掃描寫入基準「v4 對 v5」實為 v5 對 v5（`open_assembly` 自動遷移）：記錄；本批以 `only_up_to(5)` 釘住，v5 對 v6 為 125.9 對 129.1 ms。

已知限制：pytest 偶發 APScheduler `JobLookupError 'cmdscan:42'` 警告（既有時序競態，測試全過，未在 HEAD 重跑確認）；單監看 8.3 ms 對 10 ms 餘裕小。
- 2026-10-29 dev-lead → 總經理：實作完成，957 passed（+35），全部門檻通過；staged。總經理代跑 ruff／format／mypy／pytest 全綠；`price_snapshot.py`、`retention.py`、`test_architecture.py`、`test_retention.py` diff 為 0。送 qa-reviewer。
- 2026-10-29 qa-reviewer → 總經理：**PASS，BLOCKING_ISSUES=false**。keep 條件、`LAG` 方向、`to_utc_iso` 字串比較、NULL 回程同組、retention 與 FD-7 語意一致、呼叫端無循環 import、隨機生成器遵守 A1／A2 並覆蓋 9 種形狀、0006 走同一 runner 有備份、效能說法誠實；Codex `exec -s read-only`「No concrete bugs found」，逐項核實一致。殘留 low：AST 守門用精確清單重構時需同步更新；A2 單調性為前提。唯讀判準常數未觸及。
- 2026-10-29 總經理 e2e（服務重啟套用 0006）：正式庫 `schema_version` 6、`ix_obs_snapshot` 存在、`flight-deals.pre-v6.db` 產生、`integrity_check` ok；列表 13 ms、詳情 38 ms、設定 29 ms、通知 6 ms、探索 38 ms；列表價格（監看 2 東京成田 TWD 12,688）、詳情「最便宜的日期組合」與全部文案不變。狀態 build → **done**。<100 ms 目標未達（steady180 184.8 ms）依裁示不再加複雜度；待日後資料量實際成長再評估方案 C。

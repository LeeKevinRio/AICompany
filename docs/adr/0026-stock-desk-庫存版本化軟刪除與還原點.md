# ADR-0026：stock-desk 庫存版本化、軟刪除與還原點

- 狀態：proposed
- 日期：2026-10-16
- 決策者：tech-architect（草案）；待 CEO 核可。立案由 CEO 2026-10-16 核可（`work/dispatch/2026-10-16-CEO決策-ADR-0025核可與五日方向.md` 第 24 行，決策包 #8）。
- 適用範圍：僅 product/stock-desk 產品線。
- 前提：ADR-0002 的單機、單一使用者部署；純自用（ADR-0025 F-1）。前提改變即觸發本 ADR 的 F-1。
- 與既有 ADR 的關係：
  - **部分修訂 ADR-0017（accepted）D-7**：「`DELETE` 維持硬刪除」改為「移入已刪除區（軟刪除）」；「不得 cascade 刪除 `alert_rules`、`kelly_inputs`、`playbook_*`」維持不變。ADR-0017 Consequences 第 99 行「資料表間沒有任何持久化的 position id 引用」不再成立（見本 ADR Consequences）。比照 ADR-0024 對 ADR-0009 的作法，只在 ADR-0017 檔頭加一行修訂指標。**須 CEO 核可。**
  - **回應 ADR-0017 X3-F2**：本 ADR 新增的寫入入口（匯入確認、復原刪除、套用還原點、遷移）逐門列在 D-7。其中兩扇「原樣還原門」依設計不經 `PositionWriteInput`。這是對 ADR-0017 D-4「寫入路徑一律驗證」的明文例外，**須 CEO 核可**。
  - **實作 ADR-0025（accepted）D-12 Phase 2「庫存安全」**，並結案 ADR-0025 附件 R-105（DB 相對路徑）。另有兩處細節修訂，須 CEO 知悉：
    - (a) Phase 2 交付清單中的「schema 版本（`PRAGMA user_version`）」改為 per-component 的 `schema_migrations` 表（D-6）。
    - (b) 驗收條件「還原點往返位元組相同」定義為「庫存正規化內容的 sha256 相同」（D-4.2），而不是整顆 DB 檔位元組相同。
    - 不在本 ADR 範圍的 Phase 2 項目：可用現金自報欄位、對外送出資料的說明。
  - **與 ADR-0025 E1 的交互**：預測帳放在主 DB，所以還原點不得觸及 `forecast_*`、`plan_*`（D-1.3、IV-12）；主 DB 的備份等級上調（D-9）。
  - **相容、不修訂 ADR-0012**：
    - 不改任何 C 條文。
    - 市場 DB 的路徑守門在 `app/data/market_panel.py` 內實作，環境變數字串仍只出現在該檔（C-8）。
    - 整檔還原遵守部署手冊 §4.1「不得重編 `run_id`」。
    - `app.sectors` 的 C-1 白名單不變；`app.sectors.store` 仍只使用 `resolve_db_path`，D-8 只改變它對「缺檔」的行為。
  - **相容、不修訂**：ADR-0002、0006、0010、0016、0024，以及其餘未列者。
- 編號說明：起草時 `docs/adr/` 最後一份為 ADR-0025；0013 為員工線佔用。
- 標註約定：
  - 〔事實：檔案:行號〕為起草者 2026-10-16 讀到的工作目錄狀態，行號會隨 commit 漂移。
  - 〔推論〕為起草者判斷。
  - 路徑相對於 `apps/stock-desk/backend/`，另有標示者除外。

---

## 評估摘要（結論先行）

**採用**
1. **軟刪除採「搬移表」**：刪除時由 `AFTER DELETE` trigger 把整列搬進 `positions_deleted`。所有讀取 `positions` 的程式不改，就碰不到已刪除的持倉。可復原期內可以原樣復原（含原 id），超過期限明確回 410。
2. **修改歷史採 trigger**：每次寫入 `positions` 都由 trigger 寫一筆 `position_events`（前後完整影像）。寫入時沒有設定寫入上下文（actor），trigger 直接拒絕。
3. **還原點是 DB 內的庫存邏輯快照**：快照存於 `restore_points` 與 `restore_point_rows`，不做整顆 DB 檔還原。
   - 匯入確認、套用還原點、遷移之前，以及每日第一次寫入之前，都會自動建立還原點。
   - 套用還原點本身也會先建一個還原點，所以可以再復原。
4. **匯出與匯入**：
   - JSON 匯出帶格式版本、`db_id` 與內容雜湊；CSV 匯出沿用範本欄位，供試算表使用。
   - 匯入採「無狀態預覽 → 帶基準雜湊確認」兩段式：預覽零寫入；確認時基準已變就回 409。
   - 合併模式預設不改既有值；取代模式要明確確認，而且檔內有任何無效列就拒絕取代。
5. **schema 版本採 per-component 的 `schema_migrations` 表**，不用全檔共用的 `PRAGMA user_version`。
   - 遷移前先用 SQLite 線上備份 API 做整檔備份，並驗證完整性與庫存雜湊。
   - 遷移後庫存逐欄比對必須相同，否則 rollback，並拒絕啟動。
6. **DB 路徑守門與 DB 身分**：
   - 環境變數指定的路徑必須是絕對路徑；未設定時，預設路徑錨定在 backend 目錄。
   - 隱式解析下檔案不存在就拒絕建立（只有 init CLI 能建）。
   - `db_identity` 讓 API 與 scheduler 的 DB 一致性看得見。
   - 市場 DB 套用同一規則。
7. **三層保護分工**，不得互相替代：
   - 逐筆的軟刪除與修改歷史
   - 整份庫存的還原點
   - 整檔備份組（主 DB 加市場 DB，放在 DB 目錄與 Docker volume 之外）

**否決**
- `deleted_at` 欄位加上逐一過濾（漏掉一個讀取點，就會把已刪部位算進彙總）。
- 整顆 DB 檔還原當作使用者的「復原」功能（會回捲預測帳與族群統計）。
- 全檔共用的 `PRAGMA user_version`（與 ADR-0012 C-1 的 import 白名單衝突，也讓 12 個 store 互相耦合）。
- 伺服端保存預覽 session（違反「未確認前零寫入」）。
- 現行直接寫入的 `POST /api/positions/import`。

**最大代價**
- 寫入規則有一部分藏在 schema 的 trigger 裡。之後任何重建 `positions` 的遷移，都必須重建 trigger，並通過啟動時的 schema 檢查。
- 「原樣還原門」不驗證，可能把舊的不一致列（例如 TW 配 USD）重新帶回來，只能靠 X-3c 的讀取端處理。
- 首次部署多一個 init 步驟。

---

## Context（背景）

### 1. 現況（事實）

**刪除與匯入**
- 刪除是硬刪除：`DELETE FROM positions WHERE id = ?`〔事實：`app/positions/store.py:380-389`〕，API 回 204〔事實：`app/api/positions.py:128-135`〕。ADR-0017 D-7 明文維持硬刪除〔事實：`docs/adr/0017-…:79`〕。前端確認句寫「此動作無法復原」〔事實：`frontend/app/lib/inventoryWording.ts:38`〕。
- CSV 匯入解析後逐列直接 `store.create`，沒有預覽、沒有重複偵測〔事實：`app/api/positions.py:81-93`〕。逐列檢查在建構 `PositionWriteInput` 之前完成〔事實：`app/positions/csv_io.py:204-224`〕。系統沒有應用程式內的匯出。

**schema 與遷移**
- `positions` 有 12 欄，主鍵是 `INTEGER PRIMARY KEY AUTOINCREMENT`（id 不重用）〔事實：`store.py:31-46,53-66`〕。
- 兩個既有遷移都是 ad hoc，沒有版本紀錄，遷移前也不備份：`_migrate_add_sector`〔事實：`store.py:81-110`〕；`_migrate_opened_at_to_nullable` 會 DROP 加 RENAME 重建表〔事實：`store.py:120-168`〕。
- 遷移在每次啟動時由 `_init_schema` 觸發〔事實：`store.py:188-193`〕。repo 內沒有任何 `user_version`、`schema_version`（grep 無結果）。

**DB 路徑**
- 預設路徑是相對路徑 `./data/stock-desk.db`，由 `resolve_db_path()` 讀環境變數，否則用預設〔事實：`app/data/cache.py:28,99-102`〕。
- 每個 store 在 `db_path=None` 時都會 `mkdir` 並 `sqlite3.connect`，檔案不存在就靜默建立〔事實：`store.py:174-178`、`cache.py:143-147`〕。
- 啟動方式各自依賴不同機制：
  - dev-up.bat 靠「從 backend 目錄啟動」保證兩個 process 用同一顆 DB〔事實：`apps/stock-desk/dev-up.bat:7,115,131`〕。
  - compose 以絕對路徑 `/app/data/stock-desk.db` 指定〔事實：`apps/stock-desk/compose.yaml:14-17,41`〕。
  - `docker compose down -v` 會刪 volume〔事實：`compose.yaml:66-71`〕。
- 部署手冊承認「工作目錄不一致，排程寫的資料 API 讀不到」是既有已知坑〔事實：`apps/stock-desk/docs/族群動能-主機部署手冊.md:90-94`〕。核實腳本同時列出多個候選 DB 路徑〔事實：`apps/stock-desk/scripts/verify_market_data.py:916-921`〕。
- 市場 DB 有同樣的相對預設〔事實：`app/data/market_panel.py:95-96,239-242`〕。

**主 DB 裡不只持倉**
- 持倉、設定、警示、凱利、playbook、族群 board 與統計（append-only，ADR-0012 C-21）、除權息、目錄，以及 ADR-0025 E1 之後的 `forecast_*`、`plan_*`（append-only）〔事實：部署手冊 `:66`、`:250-267`；`docs/adr/0025-…:147,372`〕。

### 2. 讀取 `positions` 的路徑盤點（全部經 `PositionStore.list_all()`，另有一條原生 SQL）

| 消費者 | 位置〔事實〕 |
|---|---|
| 彙總（估值、總額） | `app/portfolio/summary.py:195-207` |
| 經彙總的下游：portfolio API | `app/api/portfolio.py:125,150` |
| 經彙總的下游：advice | `app/api/advice.py:167` |
| 經彙總的下游：settings | `app/api/settings.py:350` |
| 經彙總的下游：警示快照 | `app/alerts/snapshot.py:130` |
| 持倉列表 | `app/api/positions.py:47` |
| leverage 選取部位 | `app/api/leverage.py:61-72` |
| 族群頁「持有代號」 | `app/api/sectors.py:130-131,213-216`（另建一個 `PositionStore` 實例） |
| 排程預熱名單 | `app/scheduler.py:290-292` |
| 產業回填 | `app/directory/sector_backfill.py:88,109` |
| 診斷（含原生 SQL `FROM positions`） | `app/data/diagnose.py:128,433-441` |
| demo seed | `app/demo/seed.py:396,447,492-493` |
| playbook | 不讀持倉（`app/playbook/` 內只 import `Market` 型別，`playbook/service.py:56`） |

**推論**：只要已刪除的列不留在 `positions` 表內，上表所有路徑（含 diagnose 的原生 SQL）都不必修改。

### 3. 需求來源
- PM 總綱 NP-B2（復原、修改歷史、軟刪除不得誤入彙總）、NP-B3（匯出、匯入預覽、合併、還原點、完整還原）、NP-B7（不得靜默建立空 DB、遷移前備份與逐欄比對）、D-10（保留期與保留數）〔事實：`work/stock-desk-新定位-需求總綱與分期-2026-10-15.md:159-180,211-217,707`〕。
- ADR-0025 D-12 Phase 2 的驗收條件〔事實：`docs/adr/0025-…:492`〕。

---

## Options（選項比較）

**A. 軟刪除**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A1 `deleted_at` 欄位，各讀取點加 `WHERE deleted_at IS NULL` | 單表、直覺 | 12 個讀取點全部要改，含原生 SQL；新讀取點容易漏 | 已刪部位誤入估值或風險上限（PM 點名的風險） |
| **A2 `AFTER DELETE` trigger 把整列搬到 `positions_deleted`（採用）** | 讀取點零改動；連原生 `DELETE` 都會變成軟刪除；可原樣復原含原 id | 多一張表；搬移邏輯在 schema 裡 | 重建 `positions` 的遷移會丟失 trigger（以 IV-7 的啟動檢查擋下） |
| A3 事件溯源（`positions` 由事件重算） | 歷史最完整 | 改動面大；讀取路徑效能與正確性都要重驗 | 回歸面過大 |

**B. 還原點**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| B1 整顆 DB 檔複製與還原 | 實作最簡單 | 回捲預測帳、族群統計、警示事件；違反 ADR-0025 append-only 與 ADR-0012 C-21 | 前瞻紀錄被靜默刪除 |
| **B2 DB 內只快照 `positions` 的邏輯內容（採用）** | 只碰庫存；可預覽差異；套用前可自動再建還原點 | 不涵蓋設定、警示、凱利 | 範圍不足時須另案擴充（F-5） |
| B3 由 `position_events` 回放到任一時點 | 不必另存快照 | 回放邏輯要與所有寫入語意一致；baseline 之前的歷史不可得 | 回放錯誤難以察覺 |

**C. 修改歷史的寫入方式**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| C1 store 方法在同一交易內明確寫事件 | 邏輯在 Python、易讀 | 每扇門都要記得寫；原生 SQL 或新入口會漏 | 「Python 層遺漏不是強制邊界」（`market_panel.py:23-27` 所引 ADR-0007 的教訓） |
| **C2 SQLite trigger 寫事件，actor 由單列 `position_write_context` 提供；沒有 context 就 RAISE（採用）** | 任何寫入都留痕；沒宣告 actor 的入口會直接失敗 | trigger 內的 JSON 組裝要隨欄位維護；測試直接寫表時要設 context | 遷移忘記重建 trigger（IV-7 擋下） |

**D. schema 版本**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| D1 `PRAGMA user_version`（全檔一個整數） | SQLite 原生 | 主 DB 由 12 個 store 共用，要有一個中央遷移登記處讓所有 store import；`app.sectors.store` 受 ADR-0012 C-1 限制不能 import | 中央模組變成耦合點 |
| **D2 `schema_migrations(component, version, …)` append-only 表（採用）** | 各 component 自管；可記錄備份路徑與前後雜湊 | 多一張表；其他 component 要各自採用 | sectors 若要採用，須修 ADR-0012 C-1 |
| D3 維持現狀（冪等 DDL，不記版本） | 零成本 | 無法回答「現在是哪一版」；遷移前不備份 | NP-B7 不達標 |

**E. DB 路徑守門**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| E1 一律要求設定絕對路徑環境變數 | 明確 | 本機直跑一定要設環境變數，摩擦大 | 使用者乾脆不設，又回到預設 |
| **E2 環境變數必須是絕對路徑；未設定時錨定 backend 目錄；隱式解析遇缺檔就拒絕建立；加 `db_identity`（採用）** | 換工作目錄也是同一顆 DB；不會靜默生空 DB；兩個 process 的 DB 可以比對 | 首次部署多一個 init 步驟；預設路徑語意改變 | 舊的「從別處啟動」用法會被拒絕（這正是本意） |
| E3 只在啟動時警告 | 零摩擦 | 警告會被忽略 | 照樣出現空 DB |

**F. 匯入流程**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| F1 現行：選檔即寫入 | — | 重複計入（現存缺陷） | 覆寫或重複 |
| F2 伺服端保存預覽 session，確認時引用 session id | 確認時不必重傳檔案 | 預覽本身就寫了 DB，違反「未確認前零寫入」 | session 過期與清理 |
| **F3 無狀態預覽；確認時重傳檔案與 `base_sha256`、`file_sha256`，伺服端重算計畫（採用）** | 預覽真正零寫入；基準被改就回 409 | 確認時要重傳檔案（量級很小） | 無 |

---

## Decision（決策）

### D-1 範圍與三層保護

1. **庫存資料**指 `positions` 表的 12 欄〔事實：`store.py:31-46`〕。`settings`（含 ADR-0025 規劃的可用現金欄位）、`alert_rules`、`kelly_inputs`、`playbook_*` 不在 v1 範圍（F-5）。
2. **三層保護不得互相替代**：
   - (a) 軟刪除與修改歷史：逐筆，DB 內。
   - (b) 還原點：整份庫存的邏輯快照，DB 內，給使用者用。
   - (c) 備份組：主 DB 加市場 DB 的整檔備份，放在 DB 目錄與 Docker volume 之外，只供災難復原，只由操作者執行。
3. (a)、(b) 只讀寫 D-10 所列的庫存 component 各表。**不得**讀寫 `forecast_*`、`plan_*`、`sector_*`、`alert_*`、`kelly_*`、`playbook_*`、`settings*`。

### D-2 軟刪除

1. 新表 `positions_deleted`：`positions` 的 12 欄，加 `deleted_at TEXT NOT NULL`、`delete_batch_id TEXT`，主鍵 `id`。
2. `positions` 上的 `AFTER DELETE` trigger 把 `OLD.*` 寫進 `positions_deleted`。`deleted_at` 與 `delete_batch_id` 取自 `position_write_context`（D-3.2）。任何刪除 `positions` 列的路徑（API、demo seed、套用還原點、取代匯入）都因此成為軟刪除。
3. `DELETE /api/positions/{id}` 的回應維持 204，不 cascade（保留 ADR-0017 D-7 的後半）。
4. **復原**：`POST /api/positions/deleted/{id}/restore`，在 `BEGIN IMMEDIATE` 內執行。
   - 條件：該 id 在 `positions_deleted`，且 `now − deleted_at ≤ SOFT_DELETE_RETENTION`。
   - 動作：以原 12 欄原樣（含 id、`created_at`、`updated_at`）`INSERT INTO positions`，再刪除 `positions_deleted` 的該列，回 200 與 `Position`。
   - 超過期限或已清除：回 410，附固定句（字面交 creative-lead 起草、送風控審）。
   - 兩處都找不到：回 404。
   - AUTOINCREMENT 保證原 id 不會被新列佔用〔事實：`store.py:33`〕。
5. **清除**：`purge_expired_deleted(now)` 刪除超過期限的 `positions_deleted` 列，由 API 啟動時與 scheduler 每日一次呼叫，冪等。`position_events` 不清除（D-3.5）。
6. `GET /api/positions/deleted` 列出可復原項，附 `deleted_at` 與 `restorable_until`。

### D-3 修改歷史

1. 新表 `position_events`，append-only（`BEFORE UPDATE`／`BEFORE DELETE` 一律 `RAISE(ABORT, 'append-only')`，比照 `market_panel.py:227-236`、`sectors/store.py:256-262`）。欄位：
   - `event_id INTEGER PRIMARY KEY AUTOINCREMENT`
   - `occurred_at`
   - `position_id`
   - `op ∈ {insert, update, delete, deleted_row_released}`
   - `actor`
   - `batch_id`
   - `before_json`
   - `after_json`
2. **寫入上下文** `position_write_context`：只有一列（`id=1`），欄位 `actor`、`batch_id`、`at`。
   - 寫入門在同一交易的第一個敘述設定它，最後一個敘述刪除它。
   - SQLite 同時只有一個寫入者，所以交易內的 context 不會被別人穿插〔推論〕。
   - `positions` 的 `BEFORE INSERT`／`UPDATE`／`DELETE` trigger：context 不存在，或 `actor` 是 NULL，就 `RAISE(ABORT, 'position write without context')`。
3. **事件由 trigger 寫入**：
   - `positions` 的 `AFTER INSERT`／`UPDATE`／`DELETE` 寫 `insert`、`update`、`delete`。
   - `positions_deleted` 的 `AFTER DELETE` 寫 `deleted_row_released`（因復原或清除而離開已刪除區）。
   - `before_json`、`after_json` 是 12 欄的 `json_object`。改了哪些欄位，由讀取端的純函式比對得出，不在 trigger 裡算。
4. `actor` 是封閉列舉：`api_post`、`api_put`、`api_patch`、`api_delete`、`api_restore_deleted`、`sector_backfill`、`import_merge`、`import_replace`、`restore_point_apply`、`purge_deleted`、`demo_seed`、`migration_baseline`。新增列舉值視同新增寫入門（D-7、F-3）。
5. **baseline 與保留**：
   - 安裝本表的遷移（D-6.3 的 positions v3），為每一筆既有持倉寫一筆 `actor=migration_baseline` 的 `insert` 事件。在此之前的歷史不存在，要照實揭露。
   - 事件永久保留。超過可復原期後，介面不能再復原，但歷史中仍看得到當時的欄位值。這一點要寫進字面（交 creative-lead、送風控）。
6. `GET /api/positions/{id}/history`：已刪除與現存的 id 都可查。
7. **與 ADR-0017 C2 的關係**：trigger 讀的是 `OLD`、`NEW`，PATCH 仍是只寫被送出欄位的單一 `UPDATE`，不構成「讀出 → 合併 → 整列寫回」〔事實：ADR-0017 C2，`docs/adr/0017-…:112`〕。

### D-4 還原點

1. **資料表**：
   - `restore_points(rp_id TEXT PRIMARY KEY, created_at, reason ∈ {manual, pre_import, pre_restore, pre_migration, daily_first_write}, label, component_version, row_count, content_sha256)`
   - `restore_point_rows(rp_id, position_id, row_json, PRIMARY KEY (rp_id, position_id))`
   - 兩表都以 `BEFORE UPDATE` RAISE 禁止修改。DELETE 只允許由保留期清除，以整個 `rp_id` 為單位刪除（store 測試 IT-9）。
2. **正規化內容雜湊**（唯一實作在 `app/positions/digest.py`，純函式）：
   - `positions` 各列依 id 升冪排列；每列是固定欄序（同 `_COLUMNS`，`store.py:53-66`）的 JSON 陣列，值照原樣保存（TEXT 不做 Decimal 正規化，NULL 寫成 `null`，id 是整數）。
   - 以 `\n` 串接後取 UTF-8 的 sha256。
   - ADR-0025 驗收「還原點往返位元組相同」定義為：套用後 `positions` 的這個雜湊等於還原點的 `content_sha256`。
3. **建立時機**：
   - 手動建立。
   - 自動建立：匯入確認之前、套用還原點之前、positions component 遷移之前（另外還有 D-6 的整檔備份）、每個 Asia/Taipei 日第一次寫入 `positions` 之前。
   - 自動還原點與觸發它的寫入在同一個交易內。自動還原點的內容雜湊若與最新一個還原點相同，就不重建，直接沿用；手動還原點一律新建。
4. **預覽**：`GET /api/restore-points/{rp_id}/diff` 回傳目前內容與還原點的逐列差異，零寫入。
5. **套用**：`POST /api/restore-points/{rp_id}/apply`，body 帶 `base_sha256`。在 `BEGIN IMMEDIATE` 內依序執行：
   1. 重算目前雜湊；與 `base_sha256` 不同就回 409，不寫入。
   2. 建立 `pre_restore` 還原點。
   3. 目前在 `positions`、但不在還原點的 id：`DELETE`（由 trigger 搬入已刪除區，仍可復原）。
   4. 兩邊都有但欄位不同的 id：以影像 `UPDATE` 全部 11 個非 id 欄位。
   5. 在 `positions_deleted` 的 id：先自已刪除區移出，再以影像 `INSERT`。
   6. 哪裡都沒有的 id：以原 id `INSERT` 影像。
   7. 後置檢查：雜湊必須等於還原點的雜湊，否則 ROLLBACK，並記 ERROR。
   - 套用後，任何列若 `currency_matches_market` 為假，記一行 WARNING，訊息前綴與 ADR-0017 X-3b 相同。
6. **保留**：自動還原點保留最新 `N_AUTO` 個，手動還原點保留最新 `N_MANUAL` 個（數字由 CEO 定，見待決 #2），超出時刪除最舊的。

### D-5 匯出與匯入

1. **匯出** `GET /api/positions/export?format=json|csv`：
   - JSON 結構：`{format: "stock-desk.positions", format_version: 1, component_version, db_id, exported_at, row_count, content_sha256, rows: [<12 欄原樣字串>]}`。這是有版本標記、可完整還原的格式。
   - CSV 欄位與範本相同〔事實：`csv_io.py:40-50`〕，沒有 id 也沒有版本，只供試算表使用；字面要說清楚兩者的差別。
2. **預覽** `POST /api/positions/import/preview`（multipart 上傳檔案）：
   - 回傳 `file_kind`、`file_sha256`、`base_sha256`（目前庫存的正規化雜湊），以及逐列 `status ∈ {new, identical, conflict, ambiguous, invalid}`、相符的現存 id、欄位差異、錯誤訊息，另附各狀態計數。
   - **零寫入**：不對任何表做 INSERT、UPDATE 或 DELETE，也不建還原點。
3. **比對鍵**：
   - JSON 且 `db_id` 等於本 DB：依 id 比對。
   - 其他情形：依 `(symbol, market)` 比對。現存有多筆同鍵時標 `ambiguous`。
   - 比對欄位是 9 個使用者欄位（同 CSV 範本）：`quantity`、`avg_cost` 以 Decimal 數值比較；`note` 的空白與 null 視為相同（同 ADR-0017 D-8）。
4. **確認** `POST /api/positions/import/confirm`：
   - 帶檔案、`mode ∈ {merge, replace}`、`base_sha256`、`file_sha256`，以及逐列決定。
   - 伺服端重新解析，並以純函式 `plan_import(current, incoming, mode, decisions)` 重算計畫；任一雜湊不符就回 409，不寫入。
   - 通過後先建 `pre_import` 還原點再套用。回傳 `restore_point_id`，以及新增、覆寫、略過、軟刪除各幾筆。
5. **合併模式的預設處理**：

| 狀態 | 預設 | 可以改成 |
|---|---|---|
| `new` | 新增 | — |
| `identical` | 略過 | — |
| `conflict` | 略過，既有成本與股數不動 | 逐列明確選「覆寫」 |
| `ambiguous` | 略過 | 逐列選「新增為另一筆」或「覆寫 id X」 |
| `invalid` | 一律不寫入 | — |

6. **取代模式**：
   - 必須帶 `confirm_replace=true`。
   - 檔內有任何 `invalid` 列就回 422，整批拒絕：以殘缺的檔案取代，會靜默刪掉持倉。
   - 最終現存集合等於檔內有效列：未相符的現存列軟刪除；相符的以檔案值覆寫；其餘新增（同一 `db_id` 的 JSON 保留原 id，其他情形配發新 id）。
7. **驗證**：CSV 與 JSON 共用同一個逐列檢查函式。這個函式要完整重述 `PositionWriteInput` 的每一條規則，而且先檢查、後建構（延伸 ADR-0017 D-4、C9，`csv_io.py:204-224` 的作法）。
8. **舊端點**：`POST /api/positions/import`（直接寫入）移除，或改回 410 並指向新流程。前端改走預覽 → 確認。ADR-0017 T-14 改寫在 confirm 端點上。

### D-6 schema 版本與遷移

1. **登記表** `schema_migrations(component, version, applied_at, code_commit, backup_path, backup_sha256, pre_digest, post_digest, inferred, PRIMARY KEY (component, version))`，append-only。
2. **component `positions`** 擁有 `positions`、`positions_deleted`、`position_events`、`position_write_context`、`restore_points`、`restore_point_rows`。
3. **版本**：
   - v1 = `sector` 欄〔事實：`store.py:81-110`〕
   - v2 = `opened_at` 可為 NULL〔事實：`store.py:120-168`〕
   - v3 = 本 ADR 的新表、trigger 與 baseline 事件
   - 既有 DB 沒有登記列時，依 `PRAGMA table_info` 推定已套用的版本，以 `inferred=1` 補記。
4. **遷移程序**（只要某版本會修改既有表）：
   1. 以 `sqlite3.Connection.backup` 線上備份整檔到 `<DB 目錄外的備份根目錄>/pre-migration/<component>-v<from>-to-v<to>-<UTC>.db`。
   2. 驗證備份：`PRAGMA integrity_check` 為 `ok`，且備份的庫存雜湊等於現行庫存雜湊。
   3. `BEGIN IMMEDIATE`，在鎖內重查版本（比照 `store.py:146-168` 的序列化作法）。
   4. 套用遷移並重建 trigger。
   5. 後置檢查：既有欄位範圍內的庫存雜湊必須等於 `pre_digest`（欄位保留型），而且 trigger 都在。
   6. 寫入 `schema_migrations`，COMMIT。
   - 任一步失敗：ROLLBACK；API 與 scheduler 都拒絕啟動；ERROR log 附備份路徑。
5. **只允許欄位保留型遷移**：刪欄、改型別、改寫資料的遷移不在本 ADR 授權範圍，須另立 ADR（F-6）。
6. **其他 component**：可依各自的 ADR 採用 `schema_migrations`。`app.sectors.store` 受 ADR-0012 C-1 限制，採用前須先修訂 C-1。Phase 3 的 `forecast_*` 表以 component `forecast` 納入（建議，由 ADR-0027 定案）。
7. **遷移前備份的保留**：每個 component 保留最新 `N_PREMIG` 份（建議 5）。

### D-7 寫入門總表（回應 ADR-0017 X3-F2）

| 寫入門 | 值的來源 | 驗證 | actor |
|---|---|---|---|
| POST、PUT | 使用者輸入 | `PositionWriteInput`（不變） | `api_post`、`api_put` |
| PATCH | 使用者輸入 | `PositionPatch`（不變，ADR-0017 D-1、D-2） | `api_patch` |
| 產業回填 | 目錄 | `fill_sector_if_empty` 的 CAS（不變，`store.py:278-321`） | `sector_backfill` |
| DELETE | 無新值 | 不需要 | `api_delete` |
| 匯入（合併、取代） | 檔案（新值） | 與 `PositionWriteInput` 規則相同的逐列檢查（D-5.7） | `import_merge`、`import_replace` |
| 復原刪除、套用還原點 | 先前已存的影像（原樣） | **不驗證**，以內容雜湊確認是原樣 | `api_restore_deleted`、`restore_point_apply` |
| 遷移 | 既有列 | 欄位保留型加前後雜湊比對 | `migration_baseline` |
| demo seed | demo 規格 | 沿用既有建構（ADR-0017 T-15） | `demo_seed` |

- 「原樣還原門」不驗證是刻意的：驗證可能讓舊的不一致列無法還原，改值又會破壞「逐欄相同」。代價是可能把 TW 配 USD 之類的舊列帶回來，由 X-3c 讀取端處理，D-4.5 的 WARNING 會留痕。
- 新增任何寫入門，必須修訂本表（F-3）。

### D-8 DB 路徑守門與 DB 身分（R-105）

1. `resolve_db_path()`：
   - 設了 `STOCK_DESK_DB_PATH` 但不是絕對路徑：拋 `DatabasePathError`，訊息寫明變數名與值。
   - 沒設：回傳以 `Path(__file__).resolve()` 錨定的 `<backend>/data/stock-desk.db`，不依賴工作目錄。
2. **缺檔**：隱式解析（`db_path=None`）時檔案不存在，拋 `MainDatabaseMissing`，**不建立檔案**。
   - 只有 `python -m app.data.init_db` 能建立新檔並寫入身分。
   - init 若在備份根目錄找到引用某個 `db_id` 的 manifest，表示之前有過 DB，拒絕建立並印出最新備份路徑，除非帶 `--force-new`。
   - 明確傳入 `db_path` 的呼叫端（測試、CLI 的 `--db-path`）維持現行行為。
3. **歧義**：沒設環境變數、`Path.cwd()/data/stock-desk.db` 存在，而且和錨定路徑不是同一個檔，就拒絕啟動並列出兩個路徑。避免改版後靜默換成另一顆 DB。
4. **身分表** `db_identity(singleton INTEGER PRIMARY KEY CHECK (singleton = 1), db_id TEXT NOT NULL, created_at, created_by ∈ {init, adopted})`，append-only。
   - 舊 DB（有 `positions` 表、沒有身分）在第一次守門啟動時寫入身分，`created_by=adopted`。
   - API 與 scheduler 啟動時各記一行 `main_db path=<絕對路徑> db_id=<id>`；`/health` 多回 `main_db_id`（前 8 碼）〔事實：現行 `/health` 只回 status、service、as_of，`app/main.py:59-70`〕。
5. **市場 DB**：同樣的 1～3 項規則，實作在 `app/data/market_panel.py` 內，C-8 不受影響。
   - 寫入端 `MarketPanelStore` 遇缺檔就拒絕建立（首次建立改由 `app.services.pit_snapshot` 的 init 子命令）。
   - 唯讀端 `MarketPanelReader` 維持「缺檔讀為無 run」〔事實：`market_panel.py:1085-1089`〕，但相對路徑的環境變數一樣拋錯。
   - 研究 DB 不受此規則約束（可重建，部署手冊 `:269-274`）。
6. compose 已使用絕對路徑〔事實：`compose.yaml:17,41`〕；新 volume 第一次啟動前要先跑 init（devops-sre 寫進部署步驟）。

### D-9 備份組與備份等級

1. **主 DB 的備份等級上調為「最高」**，與市場 DB 相同。理由：持倉本來就無法重建〔事實：部署手冊 `:256-257`〕；ADR-0025 E1 之後又放著無法重建的前瞻預測帳。
2. **備份組**：
   - 主 DB 與市場 DB 各做一份 `sqlite3.Connection.backup`，先後順序依下面的 2-1 點（先主 DB、後市場 DB，不得並行或顛倒），各自驗 `integrity_check` 與 sha256。
   - 寫一份 manifest：`db_id`、時間、檔案 sha256、庫存雜湊、最新的 `forecast_run`、最新的市場 DB `run_id`。另加記 2-1 點所列各項。
   - 建議每日 23:40（Asia/Taipei，在當日最後一個排程寫入之後）執行；保留每日 14 份、每週 8 份（CEO 定）。
   - 備份根目錄必須在 DB 目錄與 Docker data volume 之外（例如 bind mount 的主機目錄），`docker compose down -v` 不得連帶刪除。

2-1. （ADR-0027 N-20；data-engineer 2026-10-18 查證）兩份備份依序執行：先完成主 DB 的備份，再開始市場 DB 的備份，不得並行或顛倒。理由：主 DB 記下了所讀的市場 DB run（ADR-0027 D-9.2「R 倒退」的參考值）；市場 DB 後備份，才會涵蓋主 DB 備份所引用的每一個 run。順序顛倒時，整組還原後 ADR-0027 的還原疑似守衛可能永久成立〔推論，依 data-engineer 2026-10-18 查證〕。

   本點編號用 2-1，是為了不讓後面各點改號：ADR-0027 等文件已引用 D-9.3、D-9.4。

   - **manifest 加記三項**（風控 2026-10-19）：
     - (a) 主 DB 備份完成時刻、市場 DB 備份開始時刻（UTC ISO8601），供事後核對順序；
     - (b) 每一個值大於 0 的參考候選（種類、值）與它存下的身分 `{recorded_at, kind, session_date}`（主 DB 端的 `*_identity_json` 欄，見下）；三方取值最大者另記為「參考 run」（見下）；
     - (c) 檢查結果：逐候選記下該 run 在市場 DB 備份中是否存在、身分三欄是否與存下的值相等（比對規則見下）。
   - **參考 run 的取法**（與 ADR-0027 D-9.2「R 倒退」的參考候選定義一致，對象是主 DB 的備份檔，不是現行 DB）：
     - 以一次唯讀查詢，取三個參考候選：
       - (i) 最後一列 `forecast_settle_eval` 的 `market_run_max` 與 `market_run_max_identity_json`；
       - (ii) 最近一個已完成更正作業（已有 `forecast_correction_job_end`）的 `market_scan_to` 與 `market_scan_to_identity_json`；
       - (iii) `forecast_gap_audit` 中 `market_run_regression_json` 為 null 的列裡，`market_run_current` 最大的一列（同值時取 `audit_id` 最大者）的 `market_run_current` 與 `market_run_current_identity_json`。守衛成立時寫入的稽核列（`market_run_regression_json` 非 null）不是參考候選：否則市場 DB 單獨還原後，新時間線的同號 run 會經由守衛期間的稽核列成為參考，使守衛自行解除。
     - 沒有列的一方不計。值大於 0 的每一個候選都要通過 (c)：manifest 逐候選記下候選種類、值、存下的身分與檢查結果。三方取值最大者（同值時依 settle_eval → correction_job → gap_audit 取第一個）另記為「參考 run」，只供對照 ADR-0029 E-2，不影響判定。
     - 理由：ADR-0027 D-7 第 2 點的守衛只要任一候選不符就成立。只檢查最大值的組，整組還原後仍可能因為較小的候選身分不符而使守衛成立。每一個值大於 0 的候選都在市場 DB 備份中存在、而且身分相符時，還原後的 `MAX(run_id)` 不小於任何候選，(a)、(b) 都不成立，所以本檢查不另比 r_now〔推論：完整還原程序（含 WAL）未驗證，N-40〕。
     - 沒有任何值大於 0 的候選時，沒有參考 run：manifest 記「無參考 run」，(c) 不適用，不算未通過（與 ADR-0027 同一處理：沒有參考值就不檢查）。
   - **身分與比對規則**（ADR-0027 N-20）：
     - 身分 ＝ `{recorded_at, kind, session_date}`，主 DB 端存在上列三個 `*_identity_json` 欄；欄位名以 ADR-0027 N-20 為準。
     - 比對逐欄比原值：以 `run_id` 查市場 DB 備份的 `pit_snapshot_runs`，三欄都要相等。`session_date` 兩邊都是 null 時算相等，一邊是 null、另一邊不是時不相等。在 Python 比對時用 `==`；在 SQL 比對時用 `IS`，不得用 `=`（`NULL = NULL` 的結果不為真，會把相同的身分判成不符）。主 DB 的 `*_identity_json` 先解碼再逐欄比對，不比對 JSON 字串本身。
     - 不解析、不比較大小、不作為鍵（`recorded_at` 不單調、不唯一，依 data-engineer 2026-10-18 查證）。
   - **檢查沒通過的備份組**：標為不可用於整檔還原（manifest 記 `restore_usable=false`，欄位名暫定，這是本 ADR 自己的 manifest 欄位），並記 WARNING。任一個值大於 0 的候選有下列情形，就算沒通過：
     - 該 run 在市場 DB 備份中不存在；
     - 身分三欄有任一欄不相等；
     - 有參考 run，但主 DB 備份中沒有存下該候選的身分（無法比對，fail-closed）。

3. **用 `Connection.backup`，不用 `VACUUM INTO`**：前者是頁複製，保留所有表的 rowid；後者對沒有 `INTEGER PRIMARY KEY` 的表可能重編 rowid〔推論，依 SQLite 文件所述，未在本機驗證〕。部署手冊 §4.4 目前推薦 `VACUUM INTO`〔事實：`:290-306`〕，由 devops-sre 更新。
4. **整檔還原只限操作者手動執行**，程式內不提供這個功能。要遵守：
   - 主 DB 與市場 DB 從同一組備份一起還原；
   - 不得 VACUUM 或重建（不得重編 `run_id`，部署手冊 `:242-248`）；
   - 還原後重跑 X-3a 腳本（ADR-0017 X3-F4）；
   - 還原會回捲預測帳到備份時點，遺失的 session 由預測帳的缺日稽核（附件 B R-112）記為缺日，原因 `db_restored`。
   - 只用 manifest 檢查通過的備份組整組還原；沒有通過的組不得使用，也不得以手動改寫 DB、刪除參考列或關閉守衛代替（ADR-0027 D-9.2「處理終點」）。
   - 守衛成立時的解除路徑只有一條：用檢查通過的備份組重做，或修訂本點。不得新增解除用的工具或 CLI。
   - **規定落地之前已存在的備份組**（manifest 沒有 2-1 點的順序時刻、參考 run 與檢查結果者，含落地前產生，以及主 DB 備份中已有值大於 0 的候選、卻沒有 `*_identity_json` 欄的組）。「規定落地」指依本點順序與 manifest 檢查的備份實作上線之日，不是本 ADR 文字落檔之日。
     - 一律視為「未檢查」，等同沒通過，不可用於整檔還原，落地時記一次 WARNING。不推定為通過，不補寫 manifest，也不另做事後補檢工具。
     - 舊組依既有保留規則自然過期，不提前刪除。
     - 規定落地當天，操作者依 2-1 點的順序立即手動做一組新的備份，縮短沒有可用組的空窗。
     - 災難發生時若沒有任何通過的組，不得自行改用舊組或未通過的組：升級 CEO 與 devops-sre 決定，決定前不得改動 DB。改用未通過或未檢查的組屬於放寬，要 CEO 書面明示同意，事後送風控審查。不論決定為何，都不得以手動改寫 DB、刪除參考列或關閉守衛代替；整組還原後守衛若成立，依 ADR-0027 D-9.2「處理終點」處理，不另設解除工具。

### D-10 模組邊界與介面

| 模組 | 職責 |
|---|---|
| `app/positions/store.py` | 現存列的 CRUD（簽章不變），每個寫入方法設定與清除寫入上下文 |
| `app/positions/schema.py`（新） | component `positions` 的 DDL、trigger、遷移、啟動時 schema 檢查 |
| `app/positions/digest.py`（新，純函式） | 正規化序列化與 sha256 |
| `app/positions/transfer.py`（新） | CSV、JSON 解析（共用逐列檢查）；純函式 `plan_import` |
| `app/positions/restore.py`（新） | 已刪除列表、復原、清除；還原點的建立、列表、差異、套用、保留期清除 |
| `app/positions/history.py`（新） | 讀取事件 |
| `app/data/cache.py` | `resolve_db_path` 的守門（D-8.1～8.3） |
| `app/data/db_identity.py`（新，只依賴 stdlib 與 `cache`） | 身分的讀取、建立、採用 |
| `app/data/init_db.py`（新，CLI） | 建立新的主 DB |
| `app/api/positions.py`、`app/api/restore_points.py`（新） | 路由 |
| 前端 | 只渲染伺服端給的狀態與差異，不自行比對 |

---

## Consequences（後果）

**好處**
- 已刪除的持倉在結構上就到不了任何估值、警示、風險上限路徑。現有 12 個讀取點、未來新增的讀取點、diagnose 的原生 SQL，全部不必記得過濾。
- 每一次庫存寫入都有前後影像，沒宣告 actor 的入口會直接失敗。ADR-0017 X3-F2 擔心的「新入口繞過規則」，從此至少一定會留痕。
- 還原點可以預覽、可以再復原，而且不碰預測帳與族群統計。
- 改版或遷移有備份與逐欄比對作為硬性關卡；從錯的目錄啟動，不會再看起來像「庫存被重設」。

**代價與壞處**
- 一部分寫入規則（搬移、事件、context 檢查）放在 SQLite trigger 裡，讀 Python 程式碼看不到，要靠 `schema.py` 的說明與啟動時檢查。任何重建 `positions` 的遷移都必須重建 trigger。
- 每次寫入多 2～3 條敘述（設定與清除 context、事件、可能的每日還原點）；量級很小〔推論〕。
- 既有測試若直接以 SQL 寫 `positions`，會因為沒有 context 而失敗，要改用測試輔助函式設定 context。
- 「原樣還原門」不驗證，可能帶回舊的不一致列。
- 永久抹除不存在：事件永久保留，超過可復原期只是不能在介面上復原。
- CSV 匯出沒有 id 與版本，可完整還原的格式只有 JSON。
- 取代模式即使可以復原，仍是高風險操作。
- v1 不涵蓋設定、警示、凱利、playbook。
- 首次部署與新 Docker volume 要先 init；改用錨定的預設路徑後，從其他目錄啟動的舊用法會被拒絕。
- `app.sectors` 暫時無法採用 `schema_migrations`（ADR-0012 C-1）。
- ADR-0017 第 99 行「沒有持久化的 position id 引用」不再成立：`position_events`、`restore_point_rows`、`positions_deleted` 都引用 id（警示與凱利仍以代號為鍵，不受影響）。
- 備份組佔用的磁碟空間是兩顆 DB 大小乘以份數（建議 22 份）；市場 DB 每年約 27 萬列〔事實：`market_panel.py:13-15`〕，檔案大小未實測。
- 前端匯入流程要重做；ADR-0017 T-14 要改寫。

**被此決策約束的事**：見下一節。

---

## 對實作的約束（逐條可檢查）

- **IV-1** `positions_deleted`、`position_events`、`position_write_context`、`restore_points`、`restore_point_rows` 這幾個表名，只能出現在 `app/positions/**` 的非測試檔與 tests 內（grep）。
- **IV-2** 除 `app/positions/**` 外，任何非測試模組不得對 `positions` 下 `INSERT`、`UPDATE`、`DELETE`（grep 加 AST）；讀取不受限。
- **IV-3** `positions` 必須有 `BEFORE INSERT/UPDATE/DELETE` 的 context 檢查 trigger，以及 `AFTER INSERT/UPDATE/DELETE` 的事件與搬移 trigger。啟動時的 schema 檢查以 `sqlite_master` 核對，缺任何一個就拒絕啟動。
- **IV-4** `position_events`、`schema_migrations`、`db_identity` 對 UPDATE 與 DELETE 一律 `RAISE(ABORT)`；`restore_points`、`restore_point_rows` 對 UPDATE 一律 `RAISE(ABORT)`。
- **IV-5** 每扇寫入門設定的 `actor` 屬於 D-3.4 的封閉列舉。表格驅動測試逐門觸發，斷言事件的 actor 正確，且所有 app 入口都沒有 NULL actor。
- **IV-6** 正規化雜湊只有一個實作（`app/positions/digest.py`），還原點、匯出、匯入的 base 檢查、遷移的前後比對都呼叫它（grep 只有一個定義）。
- **IV-7** 遷移只能是欄位保留型；`pre_digest == post_digest`；遷移前備份已存在且 `integrity_check == ok`。任一不成立：ROLLBACK 並拒絕啟動。
- **IV-8** `POST /api/positions/import/preview` 不得寫入：請求連線的 `total_changes` 增量為 0，DB 檔與 WAL 的 sha256 不變（測試）。
- **IV-9** confirm 與 apply 遇到 `base_sha256` 不符一律回 409，零寫入。
- **IV-10** 合併模式下，`conflict` 與 `ambiguous` 列只有在 decisions 明確指定時才寫入；預設不改既有的 `quantity`、`avg_cost`。
- **IV-11** 取代模式遇到任何 `invalid` 列回 422 且零寫入；沒有 `confirm_replace=true` 回 422。
- **IV-12** 套用還原點、復原刪除、匯入不得改動 `forecast_*`、`plan_*`、`sector_*`、`alert_*`、`kelly_*`、`playbook_*`、`settings*` 的任何列（測試：前後各表 count 與內容雜湊不變）。
- **IV-13** CSV 與 JSON 匯入的逐列檢查共用同一個函式，涵蓋 `PositionWriteInput` 的每一條規則。參數化測試比照 ADR-0017 T-16，非法列產生 `RowError`，不出現 500。
- **IV-14** 現行直接寫入的 `POST /api/positions/import` 不再寫入 `positions`（測試：呼叫後 `positions` 不變，回 410 或路由不存在）。
- **IV-15** `resolve_db_path()` 遇到相對路徑的環境變數會拋錯；隱式解析遇缺檔會拋錯且不建立檔案（測試：呼叫後路徑仍不存在）；沒設環境變數時，結果與 `os.getcwd()` 無關。
- **IV-16** API 與 scheduler 啟動時各記一行含 `db_id` 與絕對路徑的 log；`/health` 回應含 `main_db_id`。
- **IV-17** `app/data/market_panel.py` 套用與 IV-15 相同的規則；`STOCK_DESK_MARKET_DB_PATH` 仍只出現在該檔與 tests（ADR-0012 C-8）。
- **IV-18** 整檔備份使用 `sqlite3.Connection.backup`；備份根目錄不得在 DB 檔所在目錄之內（設定檢查）；Docker 部署的備份路徑不得在 `stock-desk-data` volume 之內（部署手冊檢查項）。
- **IV-19** 前端不得計算匯入差異、還原點差異或可復原期限；這些值都由 API 提供（grep 前端非測試檔，不得出現雜湊計算或期限運算）。
- **IV-20** DELETE 仍不 cascade：ADR-0017 T-18 照舊通過，並延伸到「軟刪除後復原，警示規則與凱利輸入仍在且不變」。
- **IV-21** 套用還原點與復原刪除寫回的列，與影像逐欄相同（12 欄，含 `created_at`、`updated_at`）。
- **IV-22** 所有新表與遷移的 store 連線都設 `busy_timeout`（ADR-0012 C-9 的同一原則）；多敘述的寫入一律在 `BEGIN IMMEDIATE` 內。

## 測試要求

- **IT-1 軟刪除隔離**：建立 A、B 兩筆，刪除 B。斷言 `list_all`、`build_summary`、`/api/positions`、警示快照的 book、`_pick_position`、`_held_symbols`、`refresh_market_data` 的預熱名單、diagnose 的持有清單都不含 B；`/api/positions/deleted` 含 B。
- **IT-2 復原**：復原 B，12 欄與刪除前完全相同；在 retention−1 秒與 retention+1 秒兩個臨界點，分別回 200 與 410；清除後回 410；事件仍在。
- **IT-3 事件完整性**：逐門觸發寫入（POST、PUT、PATCH、產業回填、DELETE、復原、合併、取代、套用、demo seed、遷移 baseline），每筆受影響的列恰好一筆事件，actor 正確。在交易中途注入失敗，主表與事件表都沒有殘留。
- **IT-4 context 強制**：不設 context 直接以 SQL 對 `positions` INSERT、UPDATE、DELETE，三者都被拒絕。
- **IT-5 append-only**：對 IV-4 所列各表下 UPDATE 與 DELETE，被拒絕。
- **IT-6 預覽零寫入**：
  - 庫存已有 2330 共 1000 股、均成本 600；匯入含 2330 的 CSV。
  - 預覽標出 `conflict` 或 `identical`，且 IV-8 成立。
- **IT-7 合併**：沒有 decision 時，2330 的成本與股數不變；有 `overwrite` decision 時才改。確認之前已有 `pre_import` 還原點，其雜湊等於匯入前的庫存雜湊。
- **IT-8 取代**：套用後庫存雜湊等於檔內有效列的預期雜湊；被取代的列在已刪除區且可復原；含 invalid 列時回 422 且零寫入。
- **IT-9 還原點往返**：
  - 建立還原點後任意修改庫存，再套用：雜湊等於還原點雜湊。
  - 接著套用自動產生的 `pre_restore`，回到修改後的狀態。
  - 保留期清除以整個 `rp_id` 為單位。
- **IT-10 base 不符**：confirm 與 apply 在 base 改變後回 409，零寫入。
- **IT-11 匯出再匯入**：JSON 與 CSV 匯出後立刻預覽，全部是 `identical`，差異為 0。
- **IT-12 遷移**：
  - 對 v1、v2 狀態的舊 DB fixture 跑到 v3：備份存在、`integrity_check` 為 ok、前後雜湊相等、baseline 事件數等於持倉列數。
  - 注入會改值的假遷移：ROLLBACK、拒絕啟動、資料不變。
  - 兩個 process 同時遷移：只有一方套用。
- **IT-13 路徑守門**：
  - 相對路徑的環境變數會拋錯。
  - 缺檔時不建立檔案。
  - 從兩個不同的工作目錄解析，得到同一個路徑。
  - 歧義情形（cwd 下另有一顆 DB）拒絕啟動。
  - 備份根目錄有 manifest 時，init 拒絕建立新 DB。
- **IT-14 身分**：舊 DB 被採用時寫入一列身分；`/health` 回傳 `main_db_id`；再次啟動不重寫身分。
- **IT-15 原樣還原門**：還原點內含 TW 配 USD 的舊列時，套用成功、欄位不變、記一行 WARNING；`list_all()` 不拋例外（ADR-0017 C4）。
- **IT-16 不觸及他表**：IV-12。
- **IT-17 靜態守門**：IV-1、IV-2、IV-6、IV-17、IV-19 的 grep 與 AST 檢查。
- **IT-18 並發**：同一個 id 同時「復原」與「再刪除」，在 `BEGIN IMMEDIATE` 下序列化，終態一致，事件鏈完整。
- **qa-e2e**：375 與 1280 寬度下，實機驗收刪除後復原、匯入預覽、合併與取代確認、還原點預覽與套用、超過可復原期的提示。

---

## 失效條件（任一成立，本 ADR 須重審）

- **F-1** 超出單機、單一使用者（多裝置同步、多人共用、兩份 DB 副本各自編輯後合併）。身分與比對鍵模型不再成立。
- **F-2** 持倉列數超過 5,000，或單一還原點的影像大小超過 5 MB。全量快照的模型要改成增量。
- **F-3** 新增 D-7 表以外的任何寫入門（含券商同步、自動匯入、新的檔案格式），或 `actor` 列舉需要新增值。
- **F-4** ADR-0017 D-2 的 PATCH 擴及 `symbol`、`market`、`currency`、`sector`、`instrument_type`（與 ADR-0017 X3-F2 連動）。
- **F-5** 設定、警示、凱利或 playbook 需要復原或還原點。須另立 ADR 擴充範圍。
- **F-6** 需要非欄位保留型的遷移（刪欄、改型別、改寫資料）。
- **F-7** 預測帳移出主 DB，或主 DB 拆檔。D-9 的備份組與 IV-12 要重審。
- **F-8** 備份組連續 3 天沒有成功產出（manifest 檢查沒通過、`restore_usable=false` 的組，算沒有成功產出），或任何一次還原演練失敗。這件事升級給 CEO 與 devops-sre。

---

## 待決事項

**CEO**
1. 核可本 ADR，以及對 ADR-0017 D-7 的部分修訂和 D-7「原樣還原門不驗證」的例外。
2. PM D-10 的數字（我的建議值）：
   - 軟刪除可復原期 `SOFT_DELETE_RETENTION`：30 天。
   - 自動還原點 `N_AUTO`：30 個。
   - 手動還原點 `N_MANUAL`：20 個。
   - 遷移前備份 `N_PREMIG`：每個 component 5 份。
   - 理由：每份還原點約 50 列 × 400 位元組 ≈ 20 KB，50 份約 1 MB〔推論，以 50 檔持倉估算〕，儲存成本可以忽略；30 天涵蓋一個月結帳週期〔推論〕。
3. 取代模式是否開放。建議開放，條件是 D-5.6 的三道限制，加上一定先建還原點。
4. 是否每日第一次寫入時自動建立還原點。建議是。
5. 市場 DB 的路徑守門是否與主 DB 同一個 PR 實施。建議是，因為市場 DB 若被靜默換成空檔，前瞻累積會歸零〔事實：部署手冊 `:236-240`〕。
6. 備份組的頻率與保留份數（建議每日 23:40，保留每日 14 份、每週 8 份），以及備份放在哪個主機目錄。
7. 知悉：ADR-0025 D-12 Phase 2 的「`PRAGMA user_version`」改為 `schema_migrations`；「位元組相同」改依 D-4.2 定義。

**風控（risk-compliance-officer）**
- 刪除確認句：取代 `inventoryWording.ts:38` 的「此動作無法復原」。
- 「已超過可復原期」的固定句，以及「歷史仍保留當時的欄位值」的揭露。
- 匯入預覽各狀態，以及合併、取代的說明字面。
- 套用還原點的確認字面。

**PM**
- 修訂庫存頁 PRD 的範圍外聲明（`work/stock-desk-庫存頁-PRD.md:28,85,86,89,164,311`），留變更紀錄並通知下游。
- 補 Given/When/Then：已刪除列表、還原點列表、取代模式。

**creative-lead**：起草上列字面，送風控。

**devops-sre**
- 備份組的實作與排程。
- Docker 的備份目錄放在 volume 之外。
- 部署手冊更新：§0.3 改為錨定的預設路徑；§1 加入 init 步驟；§4 改用 `Connection.backup`，並加入整檔還原程序、D-9.4 的全部規則，以及 D-9 第 2-1 點的備份順序與 manifest 檢查。
- 每季做一次還原演練。

**dev-lead**：實作順序依序為 D-8 → D-6 → D-2、D-3 → D-4 → D-5。前端匯入流程與 ADR-0017 T-14 的改寫。

**qa-reviewer、qa-e2e**：IV 與 IT 全項；UI 部分做實機驗收。

---

## 未查證事項與作者揭露

- 沒有執行任何測試，也沒有讀任何 DB；`positions` 的實際列數與 DB 大小未知。
- `VACUUM INTO` 重編 rowid 的條件、SQLite 單一寫入者下 context 不會被穿插，都依 SQLite 一般行為推論，未在本機驗證。
- 沒有逐檔檢查既有測試中有多少直接以 SQL 寫 `positions`（影響 IV-3 落地時的改測量）。
- **待驗證（N-40，suggested）**：完整還原程序（含 `-wal`、`-shm` 檔的處理）中，`sqlite_sequence` 的序號行為。
  - 已有的實測只涵蓋 `Connection.backup` 到新檔：備份時點 seq=3，整檔換回後新 run 拿到 4，與遺失時間線的 run 4 重號（data-engineer 2026-10-18，scratch 空 DB）。
  - 含 WAL 檔的完整還原程序尚未驗證，所以 D-9 第 2-1 點與 ADR-0027 D-9.2「R 倒退」的「還原後序號由還原檔接續」仍標〔推論〕。
  - 本次只列待驗證，不實測；驗證後把結果回報 data-engineer 與 tech-architect。
- **待辦（N-42）**：D-9 第 2-1 點 manifest 檢查的 IV／IT 測試本次未寫，追蹤項為 N-42（`work/dispatch/2026-10-17-後續追蹤清單.md`）；備份實作前必須補齊，不擋本批文字落檔。
- `demo/seed.py` 的建構模型（`PositionInput` 或 `PositionWriteInput`）沒有逐行確認。

---

## 修訂紀錄

### 2026-10-19 依風控裁定補備份順序與 manifest 檢查（devops-sre 執筆）

- 依據：`work/reviews/2026-10-19-N23補充項與checkpoint乙案裁定-風控.md` 第四節「devops-sre（ADR-0026）」第 1～4 項；`work/reviews/2026-10-18-N20市場DBrun身分查證-data-engineer.md` 第二節 4。
- 本 ADR 狀態為 proposed，依 ADR-0001（只有生效後才不得原地改寫）直接在本檔修訂。
- 與 tech-architect 的 ADR-0027 N-20 改寫同批送風控確認；確認之前不 commit。
- 被取代的原文取自修訂前的檔案現況，逐字錄存如下；下列引文含定位字串，屬歷史列，不是現行條文。

逐項（方向／CEO 欄）：

1. **D-9 新增第 2-1 點：備份順序先主 DB、後市場 DB，不得並行或顛倒。**
   - 方向：收緊。CEO：否。
   - 無被取代原文。字句照風控第四節 devops-sre 第 1 點。
   - 編號用 2-1，不讓後面各點改號（ADR-0027 已引用 D-9.3、D-9.4）。
2. **D-9 第 2-1 點加記 manifest 三項，並寫明參考 run 的取法與檢查未通過的處置。**
   - 方向：收緊。CEO：否。
   - 無被取代原文。條文由 devops-sre 依風控第 2 點的內容起草，風控未給逐字稿。
   - D-9 第 2 點的 manifest 一句，句末接「另加記 2-1 點所列各項。」：原句不變，無被取代原文。
3. **D-9 第 2 點第一子點：移除「同一時點」。**
   - 方向：收緊（一致性改字，避免與 2-1 的「不得並行」互相矛盾）。CEO：否。
   - 風控未逐字給這一句，這是 devops-sre 為消除矛盾所做的最小改動，請風控確認。
   - 被取代的原文——
     > - 主 DB 與市場 DB 在同一時點各做一份 `sqlite3.Connection.backup`，各自驗 `integrity_check` 與 sha256。
4. **D-9 第 4 點：加入「只用檢查通過的組還原」，並寫明解除路徑與規定落地前既有備份組的處理。**
   - 方向：收緊。CEO：知悉（舊組一律不可用於整檔還原；落地到第一組通過的組之間沒有可用組；改用未通過的組需 CEO 書面明示同意）。
   - 無被取代原文。第一條字句照風控第 3 點；解除路徑一條照風控第二節 C「影響二」；舊組處理由 devops-sre 起草（風控只要求寫明，未給逐字稿）。
5. **待決事項 devops-sre 一欄：「四條規則」改指全部規則。**
   - 方向：不變（更正指向，D-9.4 已不止四條）。CEO：否。
   - 被取代的原文——
     > - 部署手冊更新：§0.3 改為錨定的預設路徑；§1 加入 init 步驟；§4 改用 `Connection.backup`，並加入整檔還原程序與 D-9.4 的四條規則。
6. **「未查證事項與作者揭露」新增待驗證一項（N-40，suggested）：完整還原程序（含 WAL）的序號行為。**
   - 方向：不變（揭露）。CEO：否。
   - 無被取代原文。只列待驗證，未實測。

7. **D-9 第 2-1 點對齊 tech-architect 的 N-20 改寫（N20-10、4-C）。**
   - 依據：`work/reviews/2026-10-19-N38核對與checkpoint乙案改寫及N20改寫-tech-architect.md` 第二節 4（N20-10、4-C 第 1、2 點），coordinator 轉達。
   - 方向：收緊。CEO：否。與 ADR-0027 N-20 批同批送風控；風控尚未確認。
   - 改了四件事：
     - (a) (b)、(c) 的身分由單一 `recorded_at` 改為 `{recorded_at, kind, session_date}` 三欄，主 DB 端欄位名用 `market_run_max_identity_json`、`market_scan_to_identity_json`、`market_run_current_identity_json`；比對規則為原字串相等，`session_date` 兩邊都是 null 時算相等。
     - (b) 參考 run 的取法加第三個候選：`forecast_gap_audit` 中 `market_run_current` 最大的一列（同值取 `audit_id` 最大者）。三方沒有列的一方不計，取值最大的候選，同值時依 settle_eval → correction_job → gap_audit 取第一個，與 ADR-0027 D-9.2「R 倒退」的參考候選一致。
     - (c) 「兩者相等」「兩者取大」改為三方。
     - (d) 第 2 項我標為暫定的 N-20 欄位名（`recorded_at` 欄位）改為上述三個 `*_identity_json`。`restore_usable` 仍是本 ADR 自己的 manifest 欄位，維持暫定。
   - 被取代的原文（devops-sre 本日中間稿，未 commit，逐字）——
     > - (b) 參考 run 與它存下的 `recorded_at`；
     > - (c) 檢查結果：這個 run 在市場 DB 備份中是否存在、`recorded_at` 是否原字串相等。
     > - **參考 run 的取法**（與 ADR-0027 D-9.2「R 倒退」的參考值定義一致，對象是主 DB 的備份檔，不是現行 DB）：
     >   - 以一次唯讀查詢，取最後一列 `forecast_settle_eval.market_run_max`，與最近一個已完成更正作業（已有 `forecast_correction_job_end`）的 `market_scan_to`，兩者的較大值；沒有列的一方不計。
     >   - `recorded_at` 取該值所屬那一列所存的原字串（ADR-0027 N-20 新增的欄位，欄位名依 ADR-0027 定案為準）。兩者相等時，兩列各自存下的 `recorded_at` 都記入，而且都要通過 (c)。
     >   - 兩方都沒有列時沒有參考 run：manifest 記「無參考 run」，(c) 不適用，不算未通過（與 ADR-0027 同一處理：沒有參考值就不檢查）。
     > - **(c) 的比對方式**：以 `run_id` 查市場 DB 備份的 `pit_snapshot_runs`；`recorded_at` 以字串原樣相等比對（SQL 的 `=`），不解析、不比較大小、不作為鍵（`recorded_at` 不單調、不唯一，依 data-engineer 2026-10-18 查證）。
     > - **檢查沒通過的備份組**：標為不可用於整檔還原（manifest 記 `restore_usable=false`，欄位名暫定），並記 WARNING。下列情形都算沒通過：
     >   - 該 run 在市場 DB 備份中不存在；
     >   - `recorded_at` 原字串不相等；
     >   - 有參考 run，但主 DB 備份中沒有存下 `recorded_at`（無法比對，fail-closed）。
   - 取三候選最大值、同值各候選都檢查，以及「最大值為 0 視為無參考 run」，是 devops-sre 對 N20-10 的落字，請風控與 tech-architect 確認。

8. **依風控 2026-10-19 N-20 批裁定修訂 D-9 第 2-1 點、第 4 點與 F-8（R-1、R-3、R-4、R-10、R-11；devops-sre 執筆）。**
   - 依據：`work/reviews/2026-10-19-N20批裁定-風控.md` 第二節 R-1、R-3、R-4（L365）、R-10（含 suggested 括號）、R-11（L384、F-8），以及「devops-sre 起草部分的逐點理由」；第四節 devops-sre 第 1、3 點。裁定為 APPROVE（修改後核可），無否決。本項取代項次 7 的「風控尚未確認」，以及項次 7 末行「取三候選最大值、同值各候選都檢查……請風控與 tech-architect 確認」（同值各候選都檢查已被 R-3「所有值大於 0 的候選都要通過」取代）。項次 7 與其餘各項是歷史列，不改字。
   - 方向：收緊（R-1 為補漏洞，收緊；R-5 與 ADR-0027 N20-1 但書屬 ADR-0027，不在本檔）。CEO：否；項次 4 的 CEO 欄改為知悉，見下 (h)。
   - 改了下列各處：
     - (a) R-1：D-9 第 2-1 點參考 run 取法的 (iii)，只取 `market_run_regression_json` 為 null 的稽核列，守衛成立時寫入的稽核列不是參考候選。
     - (b) R-3：參考 run 取法的三個子點換成「值大於 0 的每一個候選都要通過 (c)」「理由」「沒有任何值大於 0 的候選時沒有參考 run」；「檢查沒通過」改為「任一個值大於 0 的候選有下列情形，就算沒通過」。
     - (c) R-4：身分與比對規則的比對子點整句換成逐欄比原值；Python 用 `==`、SQL 用 `IS`、不得用 `=`；`*_identity_json` 解碼後逐欄比對。
     - (d) R-10：D-9 第 4 點「規定落地之前已存在的備份組」，加「規定落地」的定義；並採 suggested，把括號中的「以及落地後、ADR-0027 N-20 欄位存在之前產生的組」改為「以及主 DB 備份中已有值大於 0 的候選、卻沒有 `*_identity_json` 欄的組」（理由：依 R-5 的順序規定，N-20 欄位存在之前不會有候選列，這類組其實是「無參考 run」；照舊字會被判為不可用，空窗不必要地變長）。為了接「規定落地」的定義，括號之後的冒號改為句號（子點內容不變）。
     - (e) R-11：D-9 第 4 點災難一句改為「沒有任何通過的組時，不得自行改用舊組或未通過的組」，補「改用未通過或未檢查的組屬於放寬，要 CEO 書面明示同意，事後送風控審查」與不得以手動改寫 DB、刪除參考列或關閉守衛代替。
     - (f) R-11：F-8 補「manifest 檢查沒通過、`restore_usable=false` 的組，算沒有成功產出」（檢查一直不過，等於連續好幾天沒有可用的組，要升級，不能靜默）。
     - (g) 風控「devops-sre 起草、待風控確認的點」改為「風控 2026-10-19 N-20 批確認」；其下三點的裁定：項次 2 的「無參考 run 不算未通過」「沒有存身分算未通過」核可（fail-closed，與 R-5 一致）；項次 3 的「同一時點」改字核可（本來就與 2-1「不得並行」矛盾，新字只更嚴）；項次 4 的舊組處理核可（只會多擋，不補寫、不補檢，沒有留下可把組「洗白」的工具），災難一句依 R-11 修改，「落地」依 R-10 定義；項次 5 的「四條規則」改字核可（更正指向）。
     - (h) 項次 4 的 CEO 欄由「否」改為「知悉」（風控：空窗是真實成本。規定落地到第一組通過的組之間，沒有可用的整檔還原組，之前所有備份組（含持倉）都不能直接整檔還原；落地當天手動做一組，空窗可縮到幾小時以內〔推論〕）。
     - (i) 「未查證事項與作者揭露」新增一句待辦，指向 N-42（manifest 檢查的 IV／IT 測試，風控第四節 devops-sre 第 2 點）。N-42 擋備份實作，不擋本批文字落檔。無被取代原文。
   - 順序限制（風控 R-10、coordinator）：ADR-0027 的 (b) 身分比對上線，不得早於本點備份實作（順序與 manifest 檢查）上線，而且上線時已有至少一組 manifest 檢查通過的備份組（devops-sre 確認）。
   - 被取代的原文取自修訂前的檔案現況，逐字錄存如下（含定位字串，屬歷史列，不是現行條文）——
     > (a) 參考 run 取法 (iii)：
     > (iii) `forecast_gap_audit` 中 `market_run_current` 最大的一列（同值時取 `audit_id` 最大者）的 `market_run_current` 與 `market_run_current_identity_json`。
     >
     > (b) 參考 run 取法的三個子點：
     > - 沒有列的一方不計；參考 run 取值最大的候選；同值時依 settle_eval → correction_job → gap_audit 的順序取第一個記為參考 run。
     > - 兩個以上候選的值相等時（指向同一個 run），各候選存下的身分都記入 manifest，而且都要通過 (c)。
     > - 三方都沒有列，或取到的最大值為 0 時，沒有參考 run：manifest 記「無參考 run」，(c) 不適用，不算未通過（與 ADR-0027 同一處理：沒有參考值就不檢查）。
     >
     > (b) 檢查沒通過：
     > （manifest 記 `restore_usable=false`，欄位名暫定，這是本 ADR 自己的 manifest 欄位），並記 WARNING。下列情形都算沒通過：
     >
     > (c) 身分與比對規則的比對子點：
     > - 比對只用原字串相等（SQL 的 `=`）：以 `run_id` 查市場 DB 備份的 `pit_snapshot_runs`，三欄都要相等；`session_date` 兩邊都是 null 時算相等。
     >
     > (d) 規定落地之前已存在的備份組：
     > - **規定落地之前已存在的備份組**（manifest 沒有 2-1 點的順序時刻、參考 run 與檢查結果者，含落地前產生，以及落地後、ADR-0027 N-20 欄位存在之前產生的組）：
     >
     > (e) 災難一句：
     > - 災難發生時若沒有任何通過的組，不得自行改用舊組：升級 CEO 與 devops-sre 決定，決定前不得改動 DB。
     >
     > (f) F-8：
     > - **F-8** 備份組連續 3 天沒有成功產出，或任何一次還原演練失敗。
     >
     > (g) 待辦標題：
     > devops-sre 起草、待風控確認的點：
     >
     > (h) 項次 4 的 CEO 欄：
     > - 方向：收緊。CEO：否。
   - 說明：(b) 子點中「(a)、(b) 都不成立」指 ADR-0027 D-7 第 2 點守衛的 (a)、(b)，不是本點 manifest 的 (a)、(b)、(c)；字面照風控 R-3 逐字，未改。

風控 2026-10-19 N-20 批確認（`work/reviews/2026-10-19-N20批裁定-風控.md`）：

- 項次 2 的「無參考 run 不算未通過」「沒有存身分算未通過」。
- 項次 3 的改字。
- 項次 4 的舊組處理：一律視為未檢查、不補檢、自然過期、落地當天手動做新組、災難時沒有通過組則升級 CEO。

- （coordinator 2026-10-19 依風控 N-20 批裁定 R-3 對齊措辭；devops-sre 2026-10-19 回報偏離第 3 點）manifest 加記項 (b)(c) 由單數「參考 run」改為逐候選，與 R-3「值大於 0 的每一個候選都要通過 (c)、manifest 逐候選記下」一致。方向：不變（一致性）。CEO：否。風控：知悉。被取代的原文——
  > - (b) 參考 run 與它存下的身分 `{recorded_at, kind, session_date}`（主 DB 端的 `*_identity_json` 欄，見下）；
  > - (c) 檢查結果：這個 run 在市場 DB 備份中是否存在、身分三欄是否與存下的值相等（比對規則見下）。

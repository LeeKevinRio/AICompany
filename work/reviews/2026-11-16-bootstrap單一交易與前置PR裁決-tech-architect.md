# bootstrap 單一交易與前置 PR 裁決

- 審查者：tech-architect
- 日期：2026-11-16
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

我建議採甲案，同時採 coordinator 的前置 PR，否決乙案。這次決策不放寬補充六第 6 點 (d)、K-4、K-5、K-12 的字面。

- 乙案否決：K-4 原文規定「寫入函式只由 recorder.py 與登記 CLI 呼叫」。`bootstrap` 由 store 提供、由登記 CLI 呼叫，本來就合乎 K-4，不需要放寬。
- 修訂 (d)、把 store.py／schema.py 列入，也否決：harness 會遞移呼叫 `create_schema` 與 `register_claim`，這兩個函式必須重構成共用的內部函式。若要求 AST 相同，就只能在旁邊複製一份，等於有兩個定義。
- 前置 PR 的說法成立。前置 PR 合併後，`app/` 內沒有任何模組呼叫新的建表路徑：
  - `register` 對正式路徑照舊拒絕；
  - recorder 走 `_write()` 的預設分支，仍要求 schema 完整，遇到 schema 不存在就拒絕寫入；
  - report 只用唯讀連線；
  - scheduler 還沒接線；
  - `create_schema` 本來就是公開函式，現在只有 tests 呼叫，這個狀況不變。
- 另有好處：CEO 那一次的 harness 會實際執行重構後的 `create_schema` 與 `register_claim`。

## 各部門回報（tech-architect）

### 1. 介面（交易邊界寫在 ADR 補充七第 1～4 點）
- schema.py：
  - 新增 `create_objects(conn: sqlite3.Connection) -> None`。它在呼叫者已開的交易內執行：先檢查沒有任何帳本物件（沒有就拋 `SchemaNotEmptyError`），再依序執行 `EXPECTED_OBJECTS` 的 5 張表與 15 個 trigger（含補充一）。
  - `create_schema` 的名稱、簽章與行為都不變，內部改為 BEGIN IMMEDIATE → `create_objects` → COMMIT。
- store.py：
  - `ClaimInput`：欄位與 `register_claim` 的參數相同。
  - `_prepare_claim(ClaimInput)`：只做驗證與導出，不讀帳。
  - `ForecastStore._insert_claim(conn, prepared, *, wait_for_later_clock: bool) -> str`：在交易內處理時鐘、登記時序、取代鏈與 INSERT。
  - `_write(*, fresh: bool = False)`。
  - `bootstrap(self, *, claims: Sequence[ClaimInput]) -> tuple[str, str]`。
  - 唯讀查詢 `provisional_results_seen(self) -> list[tuple[str, int]]`。
- 單一交易內的順序：
  1. BEGIN IMMEDIATE；
  2. 確認沒有帳本物件；
  3. 建立全部物件（含補充一的 trigger）；
  4. `require_complete_schema`；
  5. 寫入 h3 列；
  6. 寫入 h5 列；
  7. COMMIT。
- 「主 DB 沒有任何 `forecast_`、`plan_` 表」的檢查：以交易內為準。交易外（一鍵檔 R-4）只用來提早停止，不能取代交易內的檢查，否則兩次檢查之間有空窗。
- 回滾：全部步驟在同一連線、同一交易內。任何 `BaseException` 都先 ROLLBACK 再往外拋；行程中途被殺時，由 SQLite 的 journal／WAL 復原回滾。
- 我自己補的一點：兩列在同一交易內寫入，`registered_at` 可能相同，第二列就會被「必須晚於前一筆」拒絕。我推論 Windows 時鐘解析度較粗，這種情況較容易出現，但沒有查證。所以 bootstrap 遇到時鐘值不晚於前一列時，最多重讀 1 秒，時間仍只取自 store 時鐘（S-2 不變）。

### 2. (d) 的處理
採前置 PR。補充七第 7 點把順序寫明，並規定 CEO 那一次的 `git_head` 必須能到達前置 PR 的合併 commit。

### 3. 前置 PR 合併前要證明的事
- (a) `EXPECTED_OBJECTS` 的 DDL 文字零差異；`create_schema` 與 `register_claim` 的既有測試不改一字就全過。
- (b) AST 檢查：
  - `app/` 內沒有任何模組呼叫 `bootstrap`、`create_schema`；
  - `create_objects` 只有 store.py 呼叫；
  - `_write(fresh=True)` 只出現在 `ForecastStore.bootstrap`；
  - `_connect` 仍只由 `_write` 開啟。
- (c) 以下檔案零差異：`claims.py`、harness 四檔、`scripts/pipeline_acceptance_real.py`、`uv.lock`、規則檔、凍結包。
- (d) store 層測試：
  - 0 與 1 各成功一次；
  - 6 種既有物件各被拒絕，且什麼都沒建：表、trigger、索引、view、`plan_` 表、名稱大小寫不同的物件；
  - 回滾測試至少 3 種：第二列寫入前時鐘拋例外、`KeyboardInterrupt`、`registered_at` 未遞增。回滾後 `sqlite_master` 沒有任何帳本物件，非帳本的表內容不變；
  - 時鐘重讀：先回傳相同值、之後才變晚時，登記成功；
  - 成功後恰好 15 個 trigger。
- (e) `code_digest`：在 PR 寫出新舊兩個值。
  - 它一定會變（covers forecast/、dirdef/）。正式帳還沒建，所以對補充三（修訂版）的比對基準沒有影響。
  - CEO 回貼的 `code_digest` 會是新值，補充六第 6 點 (b) 照常核對。
- (f) qa PASS（含 Codex），CI 綠燈。

### 4. dev-lead 的四項自定解讀
- 第 1、2 項接受。
- 第 3 項接受，附一個條件：抽取規則遇到以下情形一律判失敗：標題出現 0 次或超過 1 次、找不到開頭的 yaml 圍欄、找不到結尾的圍欄。CG-2 合併前，要再以 CEO 那一次的 `git_head` 重跑一次。
- 第 4 項（過時的 docstring）：
  - 改在前置 PR 一次改成不會隨登記狀態過時的寫法。範圍是 registry.py、definitions.py、`dirdef/__init__.py`、definition.py。
  - schema.py 末段「wiring PR 才建表」與 store.py「The store does not create the schema」，依補充四已經過時，也一起改。
  - 前置 PR 之後，到 CG-2 合併為止，不得再改這些 docstring。若前置 PR 沒改，就留到接線 PR。

### 5. 比字面寬的讀法與送風控的問題
- 比字面寬的只有一處：補充四第 6 點寫的順序是「第五批 → CG-2 PR（含 CLI 正式路徑）」，我把 store／schema 的部分拆到前置 PR、排在 CG-2 PR 之前。CLI 分支仍在 CG-2 PR，閘門與 M-1～M-9 都不變。其餘各點都比字面嚴，例如物件檢查涵蓋 trigger、索引與 view。
- 試跑在架構面可行：
  - 補充六第 6 點 (a) 只採計「最後一次執行」，第 5 點本來就預期會重跑。
  - 試跑的 head 沒有前置 PR，依 (d) 不能作為 CG-2 證據，必須標為「試跑」。
  - 附記第 6 點的四項前提對試跑一樣適用。現在 CI 是紅燈，所以現在就不能試跑。
  - 若前置 PR 一兩天內就能合併，我建議跳過試跑。
- 送風控：
  - Q-7a：試跑加正式兩次回貼，對 D-1 第 2 點「看過暫定對照」與 R-8 填 0 有沒有影響？兩次回貼用同一份白名單；兩次的 `bars_sha256` 與各 outcome 執行次數會不同，這種差異算不算新的資訊管道？
  - Q-7b：bootstrap 提交後若核對不成立，以新結束碼 5 結束，而且不能重試（登記表已非空）。這種狀況在說明文件的 STOP 對照表裡要怎麼寫給 CEO？
- 決策點：風控判定 Q-7a 之前，不得試跑。

### ADR 全文（可逐字落檔）

檔頭加一行：

- 補充紀錄：2026-11-16 append 補充七（CG-2 正式登記的 store／schema 介面、單一交易與提交後核對；store／schema 改動以前置 PR 在真實資料那一次之前落地；tech-architect 裁示，釐清與收緊，不放寬補充六第 6 點 (d)、K-4、K-5、K-12，不改使用者面字面、規則檔、定義物件與已登記雜湊；第 8 點待風控 Q-7a；其餘 CEO 可推翻；來源 `work/reviews/2026-11-16-CG2登記PR第一段交件-dev-lead.md`）。

檔尾：

---

## 補充七：CG-2 正式登記的 store／schema 介面與前置 PR（2026-11-16）

- 決策者：tech-architect。來源：`work/reviews/2026-11-16-CG2登記PR第一段交件-dev-lead.md`。另讀 `feat/nm5-cg2-registration`（`c79e8313`）的 `app/forecast/store.py`、`schema.py`、`claims.py`、`canonical.py`、`tests/forecast_pipeline_harness.py`、`tests/test_forecast_boundaries.py`。
- 性質：釐清補充四第 2、6 點與 K-4 的實作方式，收緊 bootstrap 的交易與核對。不放寬補充六第 6 點 (d)、K-4、K-5、K-12。不改使用者面字面、規則檔、定義物件與已登記雜湊。第 8 點待風控 Q-7a；其餘 CEO 可推翻。

1. **schema.py**
   - 新增 `create_objects(conn)`。它只在呼叫者已開的交易內執行：`conn.in_transaction` 為否時拋例外。
   - 執行內容：先確認沒有任何 `_ledger_objects`，有就拋 `SchemaNotEmptyError`；再依序執行 `EXPECTED_OBJECTS`（5 張表、15 個 trigger，含補充一）。
   - 本身不下 BEGIN、COMMIT、ROLLBACK。
   - `create_schema` 改為 BEGIN IMMEDIATE、`create_objects`、COMMIT，失敗時回滾。名稱、簽章、行為不變。
   - `EXPECTED_OBJECTS` 的 DDL 文字零差異。不提供補建缺少物件的方式（K-12）。
2. **store.py**
   - `ClaimInput`：欄位與 `register_claim` 的參數相同。
   - `_prepare_claim`：不讀帳的驗證與導出。
   - `ForecastStore._insert_claim(conn, prepared, *, wait_for_later_clock)`：在交易內處理時鐘、時序、取代鏈與 INSERT。
   - `register_claim` 改走上面兩者，簽章與行為不變。
   - `_write(*, fresh=False)`：`fresh` 為真時，BEGIN IMMEDIATE 之後先執行 `create_objects`，再 `require_complete_schema`。`_connect` 仍只由 `_write` 開啟。
   - `bootstrap(*, claims) -> tuple[str, str]`：
     - 開連線前先驗證：恰好兩個 `ClaimInput`，horizon 依序為 3、5，`replaces_claim_id` 都為空；
     - 在 `_write(fresh=True)` 內依序寫入兩列；
     - 它是唯一以 `fresh=True` 呼叫 `_write` 的方法。
   - 唯讀查詢 `provisional_results_seen() -> list[tuple[str, int]]`：經 `_read()` 執行，依 `registered_at, rowid` 排序；值不是 0 或 1 時拋 `LedgerInconsistentError`。
3. **交易**
   - 同一連線、同一 BEGIN IMMEDIATE，依序：確認沒有帳本物件 → 建立全部物件 → 完整性核對 → h3 列 → h5 列 → COMMIT。
   - 任何 `BaseException` 都先 ROLLBACK 再往外拋。
   - 「沒有 `forecast_`、`plan_` 表」以交易內的檢查為準；交易外的檢查（R-4）只用來提早停止。
   - 只要有任何物件的名稱或所屬表以這兩個前綴開頭（不分大小寫），就判為不成立。
4. **時鐘**
   - 第二列的 `registered_at` 必須晚於第一列。
   - bootstrap 讀到的時鐘值不晚於前一列時，重讀 store 時鐘，最多 1 秒；仍不晚於就拋例外，整筆回滾。
   - `register_claim` 維持立即拒絕。時間只取自 store 時鐘（S-2）。
5. **claims.py（CG-2 PR）**
   - `bootstrap --production` 只呼叫 `store.bootstrap` 與唯讀查詢。
   - 結束碼：
     - 補充四第 2 點的拒絕條件，以及交易內的 `SchemaNotEmptyError`：4；
     - 其他拒絕：3；
     - 以上都不寫入。
   - 提交後的核對：
     - `ledger_schema_status()` 完整；
     - `forward_claims()` 恰好是回傳的兩個 `claim_id`；
     - `runs()` 為空；
     - `provisional_results_seen()` 兩列都等於鍵入值。
   - 核對不成立時，印固定句並以結束碼 5 結束，不重試。一鍵檔隨之 STOP，由 coordinator 升級 tech-architect。
6. **K-4 邊界**
   - 既有的 claims.py 測試不放寬；CG-2 PR 起，另加斷言：`claims.py` 呼叫了 `bootstrap`。
   - 另加以下 AST 斷言：
     - `app/` 中只有 store.py 呼叫 `create_objects`；
     - 沒有任何模組呼叫 `create_schema`；
     - `_write(fresh=True)` 只出現在 `ForecastStore.bootstrap`；
     - 呼叫 `bootstrap` 的模組：前置 PR 時沒有；CG-2 PR 起只有 claims.py；
     - recorder.py 與 report.py 都不呼叫上述任何一個。
   - schema.py 不含 INSERT。
7. **前置 PR 與順序**
   - 第 1～4、6 點的改動不含 claims.py，以獨立 PR 合併。
   - 補充四第 6 點的順序讀為：第五批 → 前置 PR → 真實資料一鍵檔 → CG-2 登記 PR → 第 4 點 (2)、(3) → 接線 PR。
   - 補充六第 6 點 (d) 不變。「harness 通過」的 `git_head`，必須能到達前置 PR 的合併 commit。
   - 前置 PR 中，以下檔案零差異：claims.py、補充六第 6 點 (d) 所列的 harness 三檔與 `scripts/pipeline_acceptance_real.py`、`uv.lock`、規則檔、凍結包。
   - 前置 PR 將 `app/` 內隨登記狀態過時的 docstring，改成不依狀態的寫法；之後到 CG-2 合併為止，不得再改。
8. **試跑**
   - 前置 PR 合併前，CEO 可以用當時的 head 執行一鍵檔一次作為試跑。前提有兩項：補充六附記第 6 點的四項成立，且風控 Q-7a 判定可行。
   - 試跑的回貼依補充六第 6 點 (b) 記錄，並標明「試跑」，不得作為 CG-2 的證據。
   - 試跑失敗依補充六第 5 點處理。

- **S-15（逐條可檢查）**
  - 第 1 點：DDL 零差異（diff）；既有 schema 測試不改就全過。
  - 第 2、3 點：
    - 0 與 1 各登記成功一次；
    - 表、trigger、索引、view、`plan_` 表、名稱大小寫不同的物件，6 種各被拒絕，且沒有建立任何物件；
    - 時鐘拋例外與 `KeyboardInterrupt` 時，回滾後沒有任何帳本物件，非帳本的表內容不變；
    - 成功後恰好 15 個 trigger（以上皆為測試）。
  - 第 4 點：注入時鐘先回傳相同值、之後才變晚時，登記成功；一直相同時，回滾（測試）。
  - 第 5 點：每個結束碼各有一個測試。
  - 第 6 點：各項 AST 斷言。
  - 第 7 點：前置 PR 附零差異清單與新舊 `code_digest`；CG-2 PR 附 `git merge-base --is-ancestor <前置 PR 合併 commit> <git_head>` 的結果。

## 驗證

- 讀過的檔案：
  - 交件報告；
  - ADR-0030 的 K-4、K-5、K-12、補充一、三（修訂版）、四、五附記、六、六附記一至三；
  - worktree `/home/user/AICompany/.claude/worktrees/agent-aa23ba638139de497/apps/stock-desk/backend/app/forecast/` 下的 `store.py`、`schema.py`、`claims.py`、`canonical.py`；
  - `tests/test_forecast_boundaries.py:1055` 起的 K-4 測試。
- 用 grep 確認：
  - `app/` 內沒有任何模組呼叫 `create_schema`；
  - 只有 `tests/forecast_pipeline_harness.py:407` 與 `tests/forecast_ledger_helpers.py` 呼叫它；
  - `code_digest` 涵蓋 `forecast/`、`outlook/`、`dirdef/`。
- 沒有執行任何程式或測試，沒有讀 `.env`，也沒有碰任何 `*.db`。
- Windows 時鐘解析度那一點是推論，沒有查證。

## 下一步

1. 待你決定：是否採用補充七。採用後交 tech-writer 落檔。
2. dev-lead 從 product 另開前置 PR，實作第 1～4、6 點與 docstring 的修改，交 qa（含 Codex）審查。合併後 CI 要綠燈。
3. 送風控 Q-7a、Q-7b。Q-7a 判定之前不得試跑。
4. 前置 PR 合併、CI 綠燈之後，由 coordinator 確認附記第 6 點的四項前提，再請 CEO 執行真實資料那一次。
5. dev-lead 將 `feat/nm5-cg2-registration` 同步到前置 PR 之後的 product。之後以 CEO 那一次的 `git_head` 為基準，重做 (d) 的比對，並實作第 5 點。

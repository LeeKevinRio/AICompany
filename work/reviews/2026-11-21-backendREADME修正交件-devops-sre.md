# backend README 修正交件（docs/backend-readme-db-path）

- 審查者：devops-sre
- 日期：2026-11-21
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
已完成並 push。未開 PR、未合併。
- 分支：`docs/backend-readme-db-path`
- base SHA：`9e0d81c98379b3b98f69b66804215c67824f8cc1`（`origin/product/stock-desk` 最新 head）
- head SHA：`d5789608f04a0bf666b39cf092923cc479105772`
- worktree：`/home/user/AICompany/.claude/worktrees/agent-a2a08a5c2fbafcb22`
- 只改 `apps/stock-desk/backend/README.md` 一個檔，一個 commit，兩行 trailer 如指示。

## 各部門回報（devops-sre）
逐處原／新如下。行號為新檔的行號。

1. 第 54 行，環境變數表 `STOCK_DESK_DB_PATH`
   - 原：只說是 SQLite 檔路徑，預設 `./data/stock-desk.db`，compose 顯式設定。
   - 新（用途欄）：
     - 執行預測紀錄的主機上不得設定，程序環境、空值、`.env` 都不行。
     - 設了，預測紀錄排程（`forecast_record`，接線後）每次都跳過、只記一行 WARNING，正式登記與 bootstrap 也會拒絕。
     - 預測紀錄只寫 `<backend>/data/stock-desk.db`。
     - compose 會顯式設定這個變數，所以 compose 不是會記錄預測的部署形態。
     - 這個變數只適用於不執行預測紀錄的機器（例如 CI、展示機）。
   - 新（預設欄）：補上「相對於 cwd」，其餘不變。
2. 第 109～110 行，示範資料指令的註解
   - 原：「DB 路徑沿用 STOCK_DESK_DB_PATH」。
   - 新：不加 `--db-path` 會寫進預設主 DB（相對於 cwd 的 `./data/stock-desk.db`），和預測紀錄帳是同一個檔，在執行預測紀錄的主機上不得這樣跑。
3. 第 113 行附近，`--db-path` 指令的註解
   - 原：「指定資料庫」。
   - 新：隔離示範資料，路徑相對於 cwd，是正確做法，不需要、也不應該設 `STOCK_DESK_DB_PATH`。
   - 另在第 142～143 行新增一段：要讓 API 讀示範 DB，只能在不執行預測紀錄的機器上、對那一個 API 程序設變數，執行預測紀錄的主機上不要這樣做。
4. 第 150～151 行（原第 142 行）
   - 原：建議改用獨立的 `--db-path` ／ `STOCK_DESK_DB_PATH`。
   - 新：只寫 `--db-path`。另加一句：`seed.py` 目前在衝突時印出的訊息仍會建議設定該環境變數，那句訊息將在正式登記後另行修正，在那之前不要照做。
5. 第 99 節「冪等」段之後，新增「寫進主 DB 的後果」
   - 示範持倉與警示規則寫進主 DB，會進入真實帳本的估值、`data_refresh` 的持有標的清單與警示評估。
   - `[demo_synthetic]` 標記只用來辨識，不會把它們排除。
   - 結論是示範資料一律用 `--db-path` 隔離。

## 驗證
- `git diff 9e0d81c… HEAD --stat`：`apps/stock-desk/backend/README.md | 16 ++++++++++++----`，1 file changed, 12 insertions(+), 4 deletions(-)
- `--numstat`：`12 4 apps/stock-desk/backend/README.md`。只有這一個檔。
- 新檔中 `STOCK_DESK_DB_PATH` 的命中行共 6 行，逐行如下：
  - 第 54 行：已改寫，符合事實 1。
  - 第 64 行：描述 `resolve_db_path()` 讀這個變數，是程式事實，不是建議。
  - 第 66 行：描述 compose 兩個容器都顯式設這個變數，是事實。這兩行屬於「資料持久化（Docker 部署）」段，該段已被第 54 行聲明 compose 不是記錄預測的部署形態，我沒有改。
  - 第 113 行：寫的是「不需要、也不應該設」，符合事實 3。
  - 第 142 行：已限定為「不執行預測紀錄的機器」、對單一 API 程序，符合事實 3。
  - 第 150 行：標示為 seed 訊息的現況，並寫「不要照做」，符合事實 4。
  - 沒有任何未加限定的「建議設定」或「沿用」。
- 測試是否讀 `backend/README.md`：
  - 我 Grep `backend/README|README.md`，範圍是 `backend/tests` 與 `frontend`（排除 node_modules）。
  - 命中的測試只讀 `apps/stock-desk/README.md`（產品 README，`riskRemediationWording.test.ts`、`inventoryPage.test.ts`）。
  - `test_verify_market_data.py` 只在 docstring 提到 `tests/fixtures/README.md`。
  - 沒有測試讀 `backend/README.md`，所以沒有測試要跑。
- 換行字元與編碼：
  - CR 數為 0，與原檔一致（原檔也無 CR，改動前已斷言）。
  - 無行尾空白。
  - `file` 顯示 UTF-8 text。

## 下一步
- 交 qa-reviewer 審查（含 Codex），diff 送風控知悉（RC-460）。
- 由 dev-lead 核對程式事實。
- 需要時再由 coordinator 開 PR。我沒有開。

### 我做了判斷的地方
- 「接線後」的寫法：`forecast_record` 寫成「預測紀錄排程（`forecast_record`，接線後）」，沒有引用任何行號。
- 第 54 行把限制寫進「用途」欄，沒有放進「預設」欄。
- 條列 5 的「後果」段，我多加了一句「所以示範資料一律用 `--db-path` 隔離，不要寫進主 DB」。這是由事實推出的結論，tech-architect 的條列裡沒有這句。
- 條列 3 的「讓 API 讀示範 DB」我另起一段，放在「寫進主 DB 的後果」之後，而不是放在指令區塊旁。這樣程式碼區塊內只留短註解。
- 第 99 節的「資料持久化」兩處（第 64、66 行）沒有改，理由見上。

### 沒有查證的事
- 沒有執行 `seed.py`、任何 `.bat`，也沒有讀 `.env*` 或 `backend/data/`。
- 沒有驗證「`forecast_record` 設了變數就跳過、登記與 bootstrap 拒絕」這些事實本身，僅依 tech-architect 裁示與 RC-460。product 版目前沒有 `forecast_record`，所以無法對照程式確認。
- `seed.py` 第 559 行 `--db-path` 不讀環境變數、預設路徑相對於 cwd，我也只依裁示引用，沒有自己讀 `seed.py` 與 `cache.py`。
- 第 142 行「對那一個 API 程序設變數」也是依裁示字面，沒有查 API 啟動方式。
- 沒有跑 `validate_agents.py`，因為這次沒碰員工線檔案。

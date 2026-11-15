# NM-5 recorder 四題與 f1～f4 裁示（取代前一份）

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
這份裁示**取代我前一份回報**，補充三也以這版全文為準。
- **四題**：維持原裁示。qa 對第 3 題提出 (a) 在 K-2 開例外、(b) 抽出葉模組兩個方案，我採 (b)，否決 (a)。
- **時程改了一處**：K-2 的修正不必放進第三批。這個違反從第一批就存在，不是本批引入的，所以第三批依 qa PASS 結案。修正改為**下一批（claims CLI）開工前的第一個 commit**。
- **f1～f4**：四項都要處理，時限如下。
  - f2、f3、f4：接線 PR 之前完成。
  - f1：第一次 CG-2 登記之前完成，因為登記表 append-only，登記後無法更正。
- **第 2 題 qa 的兩個建議**：採「scheduler 在模組層級 import recorder」，加 WARNING；不採「digest 不同就拒跑」。
- 不需要 CEO 裁決。

## 各部門回報（tech-architect）
**第 1、4 題**：qa 同意，理由與 qa 檢查方式同前一份回報。

**第 2 題 qa 的建議**
- 採 scheduler 在模組層級 import recorder。理由：K-3 規定 scheduler 只能經 recorder 進入核心，recorder 因此是第一個被載入的核心模組。它的依賴在 import 時一次載入，`LOADED` 隨即取值，載入的程式和 digest 就一致。
- 不採拒跑。程序沒重啟時，跑的仍是舊程式，以舊 digest 寫入是真實的出處。拒跑只會造成中斷，並墊高 F-2。改為每次執行重算一次磁碟 digest，與 `LOADED` 不同時記一行 WARNING，提示程序待重啟，照常執行。
- qa 怎麼檢查：
  - `scheduler.py` 對 recorder 的 import 在模組層級（AST）。
  - 有測試：磁碟與 `LOADED` 不同時只記 WARNING，outcome 不變，log 不含標籤。

**第 3 題**：否決 (a)，因為開例外會讓 K-2 的可達性判定失效。修法同前：新增 `app/advice/banned_phrases.py`，loader 再匯出同一物件。已登記的雜湊與字面都不受影響。

**f1 取代關係（low，CG-2 登記前）**
- 裁示：`replaces_claim_id` 必須指向登記較早、`(scope_kind, scope_key, horizon)` 相同的前瞻 claim，每個 claim 至多被取代一次。登記 CLI 拒收不合條件者，recorder 的 CG-2 核對同樣條件。
- 理由：符合這兩條，再加上「其餘 claim 都被指到」，同一個 key 內必然是一條線性鏈，終點就是記錄中 claim。現行做法只查有沒有被指到，跨 horizon 的取代也會放行，會打亂 D-1 第 2 點規定的並列與揭露。
- qa 怎麼檢查：三個反例都要拒收。
  - h3 舊 claim 被 h5 新 claim 取代。
  - 一個 claim 被取代兩次。
  - 指向較晚登記的 claim。

**f2 原子寫入（low，接線前）**
- 裁示：同一次執行的 `put_input_series` 與全部 `write_record` 放在同一個交易內。任一筆失敗就全部回滾，`records_written` 記 0。
- 理由：接線後帳本 append-only，兩個 horizon 一旦各用不同快照寫入就無法修正。現在正式表還沒建，加批次 API 的成本很低。K-4 不變，INSERT 仍只在 `store.py`。
- qa 怎麼檢查：注入第二筆失敗，ledger 列數為 0、end 列 `records_written=0`；批次 API 只由 recorder 呼叫（AST）。

**f3 例外歸類（low，接線前）**
- 裁示：依失敗來源分開記。
  - 帳本端（讀取或解析既有紀錄、快照失敗）：記 `error`，`error_class` 照例外類別。
  - 程式端（目前程式重算失敗，或重算值驗證不過）：維持記 `gate_closed`，`error_class=SemanticsChanged`。
  - 兩者都不算通過執行，所以下次仍會重算，維持 fail-closed。
- 理由：把帳本問題記成 `SemanticsChanged`，會讓人誤以為該登記新 claim，修錯方向。
- qa 怎麼檢查：兩類各一個測試，outcome 與 `error_class` 都不同。

**f4 唯讀連線（low，接線前）**
- 裁示：store 的唯讀查詢一律經 `_read()`（`query_only`）。
- qa 怎麼檢查：AST 確認 `_connect()` 只出現在寫入路徑；測試確認在唯讀查詢的連線上寫入會失敗。

## 驗證
- 我讀了 qa 審查報告全文，加上前一份回報列的檔案。沒有執行程式，f52bff6 不在本機。沒有讀 `.env`，也沒有碰 `.db`。
- **流程提醒**：qa 回報沒有 Codex 第二意見（`codex` 找不到指令）。依章程第 3 節，PR 合併前要補 Codex 第二意見；這不在架構裁示範圍，請 coordinator 追蹤。

## 下一步
1. tech-writer 把下列補充三 append 到 `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`，並在檔頭加一行：「- 補充紀錄：2026-11-15 append 補充三（跨 commit 比對基準、取值時點、K-2 禁詞來源、取代鏈、原子寫入、例外歸類；tech-architect 裁示，收緊與釐清，不改使用者面字面與已登記雜湊，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第三批recorder交件-dev-lead.md`、`work/reviews/2026-11-15-NM5第三批recorder審查-qa-reviewer.md`）。」
2. dev-lead 依序處理：
   - claims CLI 批開工前：先 commit K-2 修正，並補齊第 1、2、4 題的測試。
   - claims CLI 批內：f1。
   - 接線 PR 之前：f2、f3、f4。
   - 接線 PR 內：第 2 題的模組層級 import 與 WARNING。
3. devops-sre：在 runbook 寫明 `git pull`、`uv sync` 之後要重啟排程程序。

---
## 補充三：跨 commit 比對基準、取值時點、K-2 禁詞來源、取代鏈、原子寫入、例外歸類（2026-11-15）

- 決策者：tech-architect。來源：dev-lead 第三批交件「下一步」第 1～4 點；qa 第三批審查 f1～f5。已實證的路徑：`app/advice/loader.py:44` → `context.py:29` → `limits.py:54` → `app.api.kelly_wording`。
- 性質：本補充收緊 D-5 第 6 點、D-6 CG-2、K-2、D-4 第 1 點；釐清 D-2 第 1～2 點與補充二第 2 點。補充本文，不改本文；不改使用者面字面，也不改規則檔與定義物件的雜湊。本補充取代 ADR-0027 N113-1「代價」段所述的可達狀態。CEO 可推翻。

1. **比對基準**：D-5 第 6 點的「前一次執行」讀為下列兩者：
   - (i) run_id 小於本次的最近一次執行；
   - (ii) 最後一次通過執行，即 outcome ∈ {`ok`, `no_new_session`, `inputs_not_ready`} 的執行。
   本次的 `code_digest` 或 `runtime_json` 與 (i)、(ii) 任一不同，就執行 D-5 第 6 點。沒有通過執行時，視為不同。`gate_closed`、`error`，以及沒有 end 列的執行，都不算通過執行。
2. **取值時點**：
   - `code_digest`、`runtime_json`、`code_commit` 在 recorder 模組 import 時取值一次，同一程序內的各次執行都沿用。
   - `code_digest` 涵蓋的原始檔，不得在函式內 import，也不得使用 `importlib`、`__import__`。`app/scheduler.py` 在模組層級 import recorder。
   - 每次執行都重算一次磁碟上的 digest。與取值時不同時，記一行 WARNING，不含標籤，照常執行。
   - 更換程式或依賴之後，須重啟排程程序才生效。
3. **K-2 禁詞來源**：
   - K-2 依可達性判定：`app.forecast.*`、`app.outlook.*` 不得可達 `app.api` 及其子模組。
   - `BANNED_PHRASES` 的唯一定義移到 `app/advice/banned_phrases.py`，該模組不 import 任何模組。
   - `app/advice/loader.py` 以 `from app.advice.banned_phrases import BANNED_PHRASES as BANNED_PHRASES` 再匯出；`app/forecast/definitions.py` 改由 `app.advice.banned_phrases` import。
   - 禁詞的值與順序不變。`app/advice/__init__.py` 不含 import。
   - 從上述兩個套件可達的 `app.advice` 模組，恰好是 `app.advice` 與 `app.advice.banned_phrases`。
4. **沒有定案 bar**：補充二第 2 點 (a) 優先適用。處理後若沒有任何定案 bar，也沒有屬 (a) 的 bar，就記 `inputs_not_ready`，`candidate_t` 為 null，不寫紀錄，並計入 F-2。
5. **`source_status`**：照實記錄，不設拒收規則。它不得作為 recorder 或 `app/outlook/**` 的分支條件，也不影響 T、`label`、`band_def`、`baseline_predictions_json`、`missing_json`。要設拒收規則，須修訂本 ADR。
6. **取代鏈**：
   - `replaces_claim_id` 必須指向登記較早、`(scope_kind, scope_key, horizon)` 相同的前瞻 claim；每個 claim 至多被取代一次。
   - 登記 CLI 拒收不合上述條件者；recorder 的 CG-2 核對同樣的條件。
   - 本點須在第一次 CG-2 登記之前落地。
7. **原子寫入**：同一次執行的 `put_input_series` 與全部 `write_record` 放在同一個交易內。任一筆失敗就全部回滾，`records_written` 記 0。INSERT 仍只在 `store.py`（K-4）。
8. **重算失敗的歸類**：
   - 讀取或解析既有紀錄、快照失敗，記 `error`，`error_class` 照例外類別。
   - 目前程式重算失敗，或重算值驗證不過，記 `gate_closed`，`error_class=SemanticsChanged`。
9. **唯讀連線**：store 的唯讀查詢一律經 `_read()`（`query_only`）。

- **S-12a（逐條可檢查）**：
  - 第 1 點：序列 A ok → B gate_closed → B，第三次仍記 `gate_closed`；改回 A 後會重算並通過；沒有通過執行時會重算（測試）。
  - 第 2 點：AST 確認禁用的 import 形式不存在、scheduler 在模組層級 import recorder；有測試確認 digest 不同時只記 WARNING。
  - 第 3 點：可達集合與 `app.api*` 沒有交集（import graph）；`loader.BANNED_PHRASES is banned_phrases.BANNED_PHRASES`；h3、h5 的三種雜湊都不變（測試）。
  - 第 4 點：只有 (a) bar 時，`candidate_t` 等於最大的 S；沒有任何 bar 時，`candidate_t` 為 null（測試）。
  - 第 5 點：同一組 bars 分別配上 4 種 `DataStatus`，第 5 點所列欄位都逐位相同（測試）。
  - 第 6 點：三個反例（跨 horizon、取代兩次、指向較晚的 claim）都被拒收（測試）。
  - 第 7 點：注入第二筆失敗時，ledger 列數為 0（測試）。
  - 第 8 點：兩類失敗各有一個測試，outcome 不同。
  - 第 9 點：`_connect()` 只出現在寫入路徑（AST）。

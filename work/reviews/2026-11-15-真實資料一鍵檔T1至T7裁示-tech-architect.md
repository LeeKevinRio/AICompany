# 真實資料一鍵檔 T-1～T-7 裁示

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

我讀完了 devops-sre 的提案、ADR-0030 本文（含補充一到五與附記）、凍結令（CEO #139），以及決策包的 #148、#149，也對照了 worktree head `9f45cb2e` 的 harness 與相關原始碼。這次只讀檔，沒有執行任何程式，沒有讀 `.env`，也沒有碰任何 `data/*.db`。

**T-1～T-7 裁示總覽**

| 題 | 裁示 | #139 分類（建議，由 coordinator 定案） |
|---|---|---|
| T-1 取數位置 | **接受，附條件** | 插隊類（涉及正式 DB），本 PR 範圍 |
| T-2 時間戳 | **接受** | 本 PR 範圍 |
| T-3 失敗定位 | **修改**：`where` 一律不給，`vacuous_equality` 也不例外；診斷改走三步路徑 | 插隊類（D-4、#149） |
| T-4 通過證據的有效期 | **修改**：提案的 diff 範圍會誤判，改成明列允許差異加 AST 比對 | 插隊類（登記表、雜湊） |
| T-5 定義物件 | **修改**：「兩個雜湊都相等」在現況必然不成立，改成 logic 雜湊必須相等 | 插隊類（雜湊） |
| T-6 完整輸出 | **接受** | 插隊類（D-4、#149） |
| T-7 lockfile 雜湊 | **否決**，改用 `.gitattributes` 根治 | 不需處理；日後要重提就列「凍結後待辦」 |

**另外三題**
- **(i)** `bars_sha256` 與 `bars_sources` 可以給 CEO 看，也可以回貼。兩者都不構成「結果」，但要加條件：
  - `bars_sha256` 要用 `canonical.content_sha256` 計算。
  - `bars_sources` 改成封閉集，實際上恆為 `yfinance`。
- **(ii)** 「視窗定案 session 數：21」**刪除**。
- **(iii)** 診斷路徑分三步：先用合成 fixture 重現；重現不了，再由 dev-lead 自取公開 `^TWII`，在隔離環境重現；兩步都不行就升級 TA。另外訂定回報禁止清單，所以 coordinator 與 CEO 都看不到標籤。

**比 ADR 或 CEO 字面寬的讀法有兩處，都要送風控**
- **Q-1**：D-7 第 2 點、K-11 的「遇到正式主 DB 路徑就拒絕」，我讀成只管 ledger 與 SQLite 連線的目標。用 `open(rb)` 讀主 DB 的位元組來複製，不算在拒絕範圍內。
- **Q-2**：回貼會經過 CEO 和 coordinator，內容有通過/失敗、失敗種類、執行次數、雜湊。我讀成這些是「執行狀態」，不是 #149 所說的「結果」。這比 #149 的字面「輸出不給 CEO 看」寬。

風控確認前，一鍵檔 PR 可以開發、可以合併，但不得在 CEO 本機執行。需要補充六，全文附在下面。

---

## 各部門回報

### tech-architect：逐題裁示

**T-1 取數位置：接受，附條件**

比較過三種做法：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| **A：主 DB 三檔位元組複製，包裝程式用 `mode=ro` 讀複本，再注入 bars（採用）** | 主 DB 不會被任何 SQLite 連線開啟；harness 本體不用改，AST 守門照舊；符合 D-7 第 6 點「只用目前快取中的值」 | 列轉成 `PriceBar` 的對應，等於另寫了一份 | 對應可能與 `PriceBarCache` 不一致，用測試擋（見約束 C-4） |
| B：把 `STOCK_DESK_DB_PATH` 指向複本，走正式的 `load_market_benchmark` | 與正式取數路徑相同 | 可能上網取數，違反 D-7 第 6 點；`PriceBarCache._connect` 會 CREATE 表、設 WAL，等於寫入；`app.services.index` 可達 portfolio、positions | 結果不再只是快取值 |
| C：用 backup API 取一致複本 | 一致性最好 | 必須對主 DB 開連線，最後一條連線關閉時會 checkpoint，等於寫入 | 碰到正式 DB |

附加條件：
- 包裝程式不得 import `app.services`、`app.data.cache`、`app.data.service`、`app.data.providers`。
- 不得有網路呼叫。
- 無法解析的列一律 STOP。這比快取讀取的「略過」嚴，要在文件寫明。
- 列對應必須和 `PriceBarCache` 的讀取結果逐欄相同（`as_of` 除外）。
- `source` 不是 `yfinance` 就 STOP，因為這是 F-5 的訊號。
- 深度門檻用程式常數 `N_SNAPSHOT + WINDOW_SESSIONS` 導出，不寫字面的 336。

**T-2 時間戳：接受**

- 每根 bar 的 `as_of` 都注入成 session 當日 20:00（台北），與 `synthetic_series` 的規則相同，也合 D-7 第 6 點與補充二第 3 點。
- 我核對過 harness：`acceptance_window` 只取執行日前的 session，loader 只回傳 `as_of ≤ T 22:10` 的 bar。所以當日盤中的 bar 不會進任何快照。
- 剩下的偏差只有一種：歷史上曾在 15:00 前抓取、之後沒被覆寫的 bar，會被當成定案。這屬於 D-7 第 6 點已揭露的限制。
- 附帶一個正式路徑的風險：這種 bar 可能讓正式 recorder 一直停在 `inputs_not_ready`。偵測方式列「凍結後待辦」，交 data-engineer。

**T-3 失敗定位：修改**

- `where` 含 `claim_id` 與 T。「某個 T 失敗」加上 `missing_*` 這類失敗種類，就等於透露那一天的標籤是 insufficient，而 insufficient 本身就是一個標籤值。
- `vacuous_equality` 的 `where` 只有規則集加 horizon，但它代表「該 horizon 全部是 insufficient 或無法對照」，也是標籤資訊，所以同樣不放行。
- 另外兩種診斷做法我比較後否決：
  - 加密回傳完整輸出給 dev-lead：要管金鑰，屬於祕密；CEO 機器上仍有明文。
  - 另做一個輸出標籤的診斷模式：CEO 一定看得到。
- 採用的三步路徑見補充六第 5 點。

**T-4 通過證據的有效期：修改**

- 提案寫的「`app/forecast` 等目錄只有登記表與規則檔新增」不可行。依補充四第 6 點，CG-2 PR 會改 `claims.py`（`bootstrap` CLI）。
- 登記表實際在 `app/dirdef/registry.py:62-63`，不在 `definitions.py`。
- 改成兩部分（見補充六第 6 點 (d)）：
  - 明列允許的差異。`claims.py` 只能新增；harness 會呼叫的 `register`、`production_path_refusal` 及其遞移呼叫的函式，必須與通過時 AST 相同。
  - 其餘 code_digest 範圍、harness 與兩個 helper、包裝程式、`uv.lock` 都必須零差異。
- 另外要求 qa 在 CG-2 PR 交叉核對：在 `git_head` 重算 `code_digest`、`lockfile_sha256` 與兩個 `_lf` 雜湊，都要和回貼相同。

**T-5 定義物件：修改**

- `tests/dirdef_helpers.py` 的 `DIRDEF_V1_0_G7` 含 `**C8_TEST_PLACEHOLDERS`，所以測試替身的 `definition_sha256` 必然和 M-4 登記值不同。提案「兩個雜湊相等才算同一定義」永遠不會成立。
- 改成：`definition_logic_sha256` 必須相等；`definition_sha256` 的差異只能落在 `DEFINITION_NON_LOGIC_FIELDS`，由 CG-2 PR 以測試證明。不成立就重跑。

**T-6 完整輸出：接受**

- 完整輸出不寫檔，比補充五第 5 點嚴。
- 附加約束：包裝程式對 `AcceptanceResult` 只能讀 `passed`，另外呼叫 `render_summary`（用 AST 檢查）。
- 暫存帳含標籤。`cleanup=FAILED` 時，操作說明要寫「不得開啟該資料夾」，而且 CG-2 登記前要先跑出一次 `cleanup=ok`。
- 提案用「3 的 42 次方種組合」論證雜湊不洩漏，這個理由不對：P-0 每筆只有 {range, insufficient} 兩種可能。正確理由是：要驗證這個雜湊，必須先有 bars 和程式，而有了這兩樣本來就能直接算出標籤。所以雜湊不會多給任何標籤資訊。

**T-7 lockfile 雜湊：否決**

- `runtime_info` 本來就含 `platform.platform()` 與 `python_build`（`recorder.py:171-180`）。CEO 機器和 CI 的 `runtime_json` 本來就一定不同，所以「讓它與 CI 一致」的收益是零。
- 改成正規化會帶來三個代價：
  - 改到 `code_digest`；
  - 偏離 D-2 第 1 點「依賴鎖檔 sha256」的字面；
  - 與補充四 R-2「原始位元組對 blob」的比法不一致。
- 根治方式：新增 `apps/stock-desk/backend/.gitattributes`，寫入 `uv.lock text eol=lf`。不要改 repo 根目錄的 `.gitattributes`，否則產品路徑會帶回 main，破壞 main 的零產品耦合。
- 補救步驟只用 `git checkout HEAD -- <path>`，不要求 CEO 改 `core.autocrlf`。

**(i) `bars_sha256` 與 `bars_sources` 能不能回貼：可以**

- 兩者都在呼叫 `run_acceptance` 之前、只由輸入算出，與規則集和 harness 判定無關，P-0、P-1 共用同一個值。
- `^TWII` 是公開資料，它的雜湊給的資訊比看一張行情圖還少。#149 保護的是 harness 的輸出，不是公開行情。
- 條件：
  - `bars_sha256` 一律用 `app.forecast.canonical.content_sha256` 算（K-6，不另寫序列化），只輸出一次。
  - `bars_sources` 改成封閉集，不用 regex；不是 `yfinance` 就 STOP，所以實際上恆為 `yfinance`。
- `bars_sha256` 也有診斷用途：第 5 點 (c) 靠它確認 dev-lead 重現時用的是 CEO 那一次的同一份輸入。

**(ii)「視窗定案 session 數：21」：刪**

- 依建構它恆為 21，資訊量是零；不足 21 時 harness 早就 raise。
- 但字面看起來像計數，CEO 可能誤讀成 n。
- 做法：harness 不改，由包裝程式把這一行列為「已知不輸出」，不計入 `summary_lines_dropped`，所以正常值仍是 0。

**(iii) 失敗後的診斷：見補充六第 5 點**

- 回貼和轉述都只到失敗種類為止。
- 第一步：合成重現。
- 第二步：dev-lead 或 qa-automation 在 `tmp_path` 自取公開 `^TWII` 重現，用 `bars_sha256` 核對輸入；完整輸出不 commit，也不交給任何人。
- 回報禁止清單：不得含標籤、基準或實現標籤、符合與否、T 或日期、`claim_id`、筆數或比例、輸出行。coordinator 會逐字轉存 subagent 的回報，所以這條是 coordinator 與 CEO 看不到標籤的關鍵。
- 兩步都不行就升級 TA；不預先授權任何額外輸出。

### 對實作的約束（逐條可檢查，S-13b 全文在補充六）

- **C-1**：主 DB 路徑只能被 `open(...,"rb")` 讀取，不得被任何 `sqlite3.connect` 開啟；所有 connect 的目標都必須在 {複本, 兩個 ledger} 之內（e2e 監聽測試）。
- **C-2**：包裝程式的 import 集合不得包含 `app.services`、`app.data.cache`、`app.data.service`、`app.data.providers`（AST 加執行期檢查 `sys.modules`）；socket 被替換成會拋例外的替身時，流程仍能完成。
- **C-3**：複本必須在第一次 `run_acceptance` 之前刪除；SELECT 只讀那八欄，不含 `as_of`、`fetched_at`。
- **C-4**：列對應與 `PriceBarCache` 的讀取結果逐欄相同（`as_of` 除外），用 `tmp_path` 合成快取測試。
- **C-5**：包裝程式對 `AcceptanceResult` 只存取 `passed`，另外呼叫 `render_summary`（AST）。
- **C-6**：回貼不得出現 `session 數`、`T=`、`claim_id`，也不得含 `result.output` 的任何一行；毒藥測試沿用提案原樣。
- **C-7**：`bars_sha256` 等於測試獨立算出的 `content_sha256`，P-0、P-1 共用同一個值。
- **C-8**：`apps/stock-desk/backend/.gitattributes` 寫入 `uv.lock text eol=lf`；PR 附上 `git ls-files --eol`，`uv.lock` 要是 `i/lf w/lf`。
- **C-9**：`app/` 不得 import `scripts/` 或 harness（K-11 import graph）。

### 凍結後待辦（建議登錄到 `work/dispatch/2026-10-17-後續追蹤清單.md`）

1. 快取中的歷史 bar 若在 15:00 前取得、之後沒被覆寫，可能讓正式 recorder 卡在 `inputs_not_ready`。偵測方式交 data-engineer。
2. harness 的 `_final_sessions` 在 `tests/` 內重寫了一份 15:00 定案判定，與 K-6「`is_final` 只有一份定義」的精神不合。目前注入的是 20:00，所以無害。
3. 若日後要重提 T-7，走待辦。

---

### 補充六全文（可逐字落檔）

**插入位置一（檔頭）**：放在 `docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md` 第 10 行（補充五附記那一行）之後、第 11 行「- 日期：2026-10-26」之前，新增下面這一行：

```markdown
- 補充紀錄：2026-11-15 append 補充六（D-7 真實資料那一次：取數方式、注入時間戳、完整輸出不落檔、回貼白名單、失敗後的診斷路徑、通過證據與 CG-2 的綁定、`uv.lock` 換行；tech-architect 裁示，釐清與收緊，不改使用者面字面、規則檔、定義物件與已登記雜湊，不改 `app/` 程式；第 1 點 (b) 與第 4 點 (d) 的讀法待風控確認，確認前一鍵檔不得在 CEO 本機執行；其餘 CEO 可推翻；來源 `work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md`）。
```

**插入位置二（檔尾）**：接在檔尾「補充五附記」章節最後一行之後，先空一行，再加 `---` 分隔線，然後放入下面這一章：

```markdown
---

## 補充六：D-7 真實資料那一次的取數、時間戳、回貼內容、診斷路徑與通過證據（2026-11-15）

- 決策者：tech-architect。來源：`work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md` T-1～T-7；CEO #149（`work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md`）。另讀 head `9f45cb2e` 的 `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`app/forecast/canonical.py`、`app/forecast/recorder.py`、`app/data/cache.py`、`app/dirdef/registry.py`。
- 性質：釐清 D-7 第 2、5、6 點、K-11、補充四第 5 點 M-1 與第 6 點、補充五第 3、5 點的讀法；收緊管線驗收輸出的可見範圍與「harness 通過」的效力。補充本文，不改本文；不改使用者面字面、規則檔、定義物件與已登記雜湊；不改 `app/` 任何程式。第 1 點 (b) 與第 4 點 (d) 的讀法送風控確認（Q-1、Q-2），確認前一鍵檔不得在 CEO 本機執行；其餘 CEO 可推翻。

1. **取數**
   - (a) 真實資料那一次的取數由 `scripts/` 內的外層包裝執行：
     - 以位元組複製主 DB 的 `stock-desk.db` 與存在的 `-wal`、`-shm`，複製前後逐檔比對 sha256；
     - 只對複本開 `sqlite3` URI `mode=ro` 連線並設 `query_only`，只 SELECT `price_bars_cache` 中 `symbol = '^TWII'`、`market = 'TW'` 的 `trade_date, open, high, low, close, volume, currency, source`；
     - 轉成 `PriceBar` 後立即刪除複本，再以 `bars` 參數交給 `run_acceptance`。harness 本體不變。
   - (b) 讀法：D-7 第 2 點與 K-11 的「遇到正式主 DB 路徑就拒絕」，對象是 harness 的 ledger 與任何 SQLite 連線的目標。為取得 D-7 第 6 點「目前快取中的值」而以 `open(..., "rb")` 讀主 DB 位元組做複製與雜湊，不在拒絕範圍內。主 DB 不得被任何 SQLite 連線開啟，含唯讀連線與 backup API。（Q-1）
   - (c) 包裝不得 import `app.services`、`app.data.cache`、`app.data.service`、`app.data.providers`；不得有網路呼叫；不得寫入主 DB、複本或任何 `price_bars_cache`。
   - (d) 列到 `PriceBar` 的對應，除 `as_of` 外與 `PriceBarCache` 讀取方法的結果逐欄相同。任一列無法解析就停止，不略過。
   - (e) 以下任一成立就停止，只印固定句，不印任何值或根數：沒有列；任一列無法解析；任一列 `source` 以 `demo` 開頭；任一列 `source` 不是 `yfinance`（F-5 的訊號，由 coordinator 升級 tech-architect）；執行日前的 session 數少於 N_SNAPSHOT 加 `WINDOW_SESSIONS`，兩者都取自程式常數或導出函式。

2. **時間戳**
   - 每根 bar 的 `as_of` 取該 session 當日 20:00 Asia/Taipei，與 `synthetic_series` 的預設相同；快照的 `fetched_at` 依補充二第 3 點等於 `as_of`。不讀快取的 `as_of`、`fetched_at`。answer 的 `reason` 為 `synthetic_timestamps`。
   - 因此，快取中曾在 15:00 前取得、其後未被覆寫的 bar，在 harness 中視為定案。這屬 D-7 第 6 點的限制。任何文件、回貼或報告不得宣稱這一次驗證了真實時序下的 PIT、定案或 `late`。

3. **完整輸出與暫存帳**
   - 補充五第 5 點的「只寫進暫存檔的完整輸出」讀為允許，不是要求。真實資料那一次，`AcceptanceResult.output` 不寫入任何檔案、主控台或 log。包裝對 `AcceptanceResult` 只讀 `passed`，另外呼叫 `render_summary`，不存取其他屬性。
   - 暫存帳在 `finally` 刪除，含 `-wal`、`-shm`、`-journal`；下次啟動先掃除殘留，只掃包裝自己建立、名稱符合格式的子資料夾。全程停用 logging；例外只印固定句，不印例外文字與 traceback。
   - 回貼為 `cleanup=FAILED` 時，操作說明須告知 CEO 不得開啟該資料夾；CG-2 登記前須再執行一次，取得 `cleanup=ok`。

4. **回貼內容**
   - (a) 回貼檔與主控台只輸出白名單行，逐行 fullmatch 固定樣式，其餘丟棄並計入 `summary_lines_dropped`。白名單恰好是：
     - D-7 第 5 點的兩行固定標示；
     - 版本行、`script_sha256_lf`、`harness_sha256_lf`、`git_head`、`git_clean=yes`、`core_autocrlf`、`eol_check=ok`、`code_digest`、`lockfile_sha256`、`definition_sha256`、`definition_logic_sha256`；
     - `db_location=default`、`port_8000_listening=no`、三行 `copy_check`、`refusal_guard=ok`、`cache_depth=sufficient`、`bars_sources`、`bars_sha256`；
     - 每個規則集一組：`render_summary` 的通過或失敗行、執行次數行、失敗種類行、暫存帳 sha256 行、輸出 sha256 行；
     - `acceptance_result`、`cleanup`、`summary_lines_dropped`、`done_at_utc`。
   - (b) 不輸出：
     - `Failure.where`，包括 `vacuous_equality` 的規則集與 horizon；
     - 例外文字、路徑、根數，以及任何筆數或比例。
     - `render_summary` 的「視窗定案 session 數」行明列為已知不輸出，不計入 `summary_lines_dropped`。
   - (c) `bars_sha256` 在呼叫 `run_acceptance` 之前，以 `app.forecast.canonical.content_sha256` 對注入後的整條序列計算，不另寫序列化（K-6）。兩個規則集共用一個值，只輸出一次。`bars_sources` 是封閉集，依第 1 點 (e) 恆為 `yfinance`。兩者都是輸入識別，與規則及 harness 判定無關。
   - (d) 讀法：CEO #149 所稱不得給 CEO 看、也不得經 coordinator 轉述的「結果」，指模型與基準的標籤、暫定對照（含實現標籤與符合與否），以及與它們相關的任何筆數或比例。管線是否通過、失敗種類、各 `outcome` 的執行次數、雜湊與環境檢查，屬 D-4 第 5 點的執行狀態；補充四第 6 點與補充五第 3 點須以它們判定 harness 是否通過，所以可以由 CEO 回貼、經 coordinator 轉交。依此讀法，回貼不構成 D-1 第 2 點「看過暫定對照」，補充四 R-8 填 0 不受影響。（Q-2）

5. **失敗後的診斷**
   - (a) 回貼與任何轉述只到失敗種類為止。
   - (b) 第一步：dev-lead 在隔離 worktree 以合成 fixture 重現該失敗種類，修正後加回歸測試，CEO 在新 head 重跑一鍵檔。
   - (c) 第二步，限合成重現不了時：dev-lead 或 qa-automation 在隔離 worktree 的 `tmp_path`，自行從公開來源取得 `^TWII`，依第 1 點 (d) 與第 2 點的同一規則注入後執行 harness，並以 `bars_sha256` 確認輸入與 CEO 那一次相同。完整輸出與暫存帳只留在該 `tmp_path`，不 commit，不交給 quant、風控、coordinator 或 CEO。
   - (d) dev-lead 與 qa 對 coordinator 的回報（coordinator 逐字轉存）只寫失敗種類、程式層面的原因、修正 commit 與回歸測試名稱。不得含模型、基準或實現標籤，不得含符合與否、T 或任何 session 日期、`claim_id`、任何筆數或比例，也不得含完整輸出的任一行。
   - (e) 兩步都無法定位時，升級 tech-architect。未另修本 ADR 並經風控審查前，不得放行 `where`，不得把完整輸出或暫存帳帶離 CEO 本機，也不得另設會輸出標籤的診斷模式。

6. **通過證據與 CG-2 的綁定**
   - (a) 「harness 通過」成立，指最後一次執行的回貼同時具備：
     - `acceptance_result=PASS`，兩個規則集都通過，失敗種類都是「無」；
     - `refusal_guard=ok`、三行 `copy_check=SAME`、`eol_check=ok`、`git_clean=yes`、`summary_lines_dropped=0`。
     - `cleanup` 不影響通過，依第 3 點處理。補充四第 5 點 M-1 的「D-7 harness 已執行」讀為本款成立。
   - (b) coordinator 當日以 commit 在 `work/` 記錄回貼原文。CG-2 PR 合併前，由 devops-sre 或 dev-lead 執行、qa 判讀，核對下列各項：
     - `git_head` 可由 `origin/product/stock-desk` 到達；
     - 回貼的 `code_digest` 等於在 `git_head` 以 `canonical.code_digest` 算出的值；
     - `lockfile_sha256` 等於 `git cat-file blob <git_head>:apps/stock-desk/backend/uv.lock` 的 sha256；
     - `harness_sha256_lf`、`script_sha256_lf` 等於兩檔在 `git_head` 的 blob 經 LF 正規化後的 sha256。
   - (c) 回貼的 `definition_logic_sha256` 必須等於 M-4 登記的 `dirdef-v1.0` 的同名雜湊。`definition_sha256` 可以不同，因為測試替身的 C-8 欄位是佔位值；但差異只能落在 `DEFINITION_NON_LOGIC_FIELDS`，CG-2 PR 以測試證明。不成立就須重跑。
   - (d) 自 `git_head` 起到 CG-2 PR 合併時的 head 為止，只允許下列差異，其餘任何差異都使通過失效，須在新 head 重跑：
     - `app/dirdef/registry.py` 中 `PUBLISHED_DIRECTION_DEFINITIONS`、`PUBLISHED_RULESETS` 的賦值，以及登記所需的 import 與 `dirdef-v1.0` 物件常數；或 `app/dirdef/` 下只含該物件常數的新檔；
     - `app/outlook/rules/h3.yaml`、`h5.yaml`；
     - `app/forecast/claims.py` 新增的頂層定義與 CLI 分支；在 `git_head` 已存在、且由 harness 遞移呼叫的頂層函式（至少 `register`、`production_path_refusal`）必須 AST 相同；
     - `app/` 以外的登記一鍵檔、文件與測試。但 `tests/forecast_pipeline_harness.py`、`tests/dirdef_helpers.py`、`tests/outlook_helpers.py`、`scripts/pipeline_acceptance_real.py` 與 `uv.lock` 必須零差異。

7. **換行與 lockfile**
   - `runtime_info` 的 `lockfile_sha256` 維持對原始位元組取雜湊，不改走 `normalised_source`。理由有三：`runtime_json` 含平台與 Python 建置資訊，跨機器本來就不同；改了會變動 `code_digest`；也與補充四 R-2「原始位元組對 blob」的比法不一致。
   - 根治方式：在 `apps/stock-desk/backend/.gitattributes` 加 `uv.lock text eol=lf`，不改 repo 根目錄的 `.gitattributes`，main 維持零產品耦合。PR 附上 `git ls-files --eol` 輸出，`uv.lock` 須為 `i/lf w/lf`。補充四 M-7 的屬性位置在 CG-2 PR 決定，同樣不得讓 main 綁定產品路徑。
   - 一鍵檔比對釘住檔案的工作樹原始位元組 sha256 與 blob sha256，並以 `git ls-files --eol` 作為第二證據。不一致時只停止，不改 git 設定，也不改檔。補救由 coordinator 提供，限於 `git checkout HEAD -- <path>`，不要求 CEO 修改 `core.autocrlf`。

8. **風控確認前的限制**
   - Q-1（第 1 點 (b)）與 Q-2（第 4 點 (d)）由風控確認。確認前，一鍵檔 PR 可以開發與合併，但不得在 CEO 本機執行。
   - 風控判定 Q-2 偏離 CEO #149 時，由 coordinator 向 CEO 確認。

- **S-13b（逐條可檢查）**：
  - 第 1 點：
    - e2e 測試以合成的假主 DB 驗證：主 DB 路徑只被 `open(..., "rb")`，從未被 `sqlite3.connect`；所有 connect 的目標都在 {複本, 兩個 ledger} 之內。
    - 包裝的 import 集合不含 (c) 所列模組（AST，以及執行期的 `sys.modules`）。
    - socket 被替換為拋例外的替身時，流程照常完成。
    - 列對應與 `PriceBarCache` 讀取結果逐欄相同（`as_of` 除外；`tmp_path` 合成快取）。
    - (e) 每個停止條件各有一個測試。
    - 複本在第一次呼叫 `run_acceptance` 之前已刪除。
    - `app/` 不可達 `scripts/` 與 harness（import graph）。
  - 第 2 點：注入後每根 bar 的 `as_of` 等於該日 20:00 Asia/Taipei；包裝的 SELECT 不含 `as_of`、`fetched_at`（AST）。
  - 第 3 點：包裝對 `AcceptanceResult` 只存取 `passed`，另外呼叫 `render_summary`（AST）；結束後工作資料夾只剩回貼檔；殘留掃除不動格式不符的資料夾（測試）。
  - 第 4 點：
    - 白名單每一樣式各有一個測試；無關的行被丟棄並計數。
    - 「視窗定案 session 數」不輸出，也不計入丟棄數。
    - 回貼不含 `T=`、`claim_id`、完整輸出的任一行，也不含禁詞清單中的字詞。
    - 以兩組不同標籤分佈的序列執行時，回貼除雜湊、`bars_sha256` 與執行次數外逐行相同。
    - `bars_sha256` 等於測試獨立算出的 `content_sha256`，而且兩個規則集共用同一個值（測試）。
  - 第 5 點：qa 審查清單加一行，逐條核對診斷回報不含 (d) 所列內容。
  - 第 6 點：CG-2 PR 說明列出 (b)～(d) 的核對結果；(d) 附上差異檔清單與 AST 比對輸出。
  - 第 7 點：PR 附 `git ls-files --eol` 輸出；`check_pinned_eol` 在臨時 repo 中，CRLF 工作樹判停止，LF 判 ok（測試）。
```

### 送風控的問題（請 coordinator 逐字轉交 risk-compliance-officer）

- **Q-1**：ADR-0030 D-7 第 2 點與 K-11 寫「harness 遇到正式主 DB 路徑就拒絕」。補充六第 1 點 (b) 讀成：拒絕的對象是 ledger 與任何 SQLite 連線的目標；以 `open(rb)` 讀主 DB 位元組來做複本（目的是取得 D-7 第 6 點要求的「目前快取中的值」），不在拒絕範圍內；主 DB 從不被 SQLite 開啟。請確認這個讀法是釐清，而不是放寬。若判定為放寬，請指明需要的條件。
- **Q-2**：CEO #149 的字面是「30 日管線驗收的輸出只給 qa 與 dev-lead 確認程式流程，不給 CEO 看」。本設計讓 CEO 看到並回貼以下內容：通過/失敗、失敗種類（九個英文字面）、各 outcome 的執行次數、雜湊、環境檢查。不含任何標籤、對照、筆數或日期。完整輸出不落檔，所以連 qa 和 dev-lead 也看不到完整輸出。請確認三件事：
  - (1) 這與 #149 的原意（不看任何標籤、對照或結果）是否一致；
  - (2) 部分失敗種類（例如 `missing_code_not_in_set`、`vacuous_equality`）間接透露「窗內有 insufficient 紀錄」，是否可以接受；
  - (3) R-8 填 0 是否仍然屬實。

  若你判定這偏離 #149，請由 coordinator 向 CEO 提一題 Recommended 確認。

---

## 驗證

- **讀過的文件**：提案全文；ADR-0030 全文（本文、補充一到五、補充五附記）；凍結令全文；決策包 #139、#144、#148、#149。
- **讀過的程式碼（worktree head `9f45cb2e`）**：
  - `tests/forecast_pipeline_harness.py` 全文。
  - `canonical.py:143-249`、`recorder.py:150-219`、`cache.py:536-618`、`session_calendar.py` 全文。
  - `dirdef_helpers.py`：測試替身含 `C8_TEST_PLACEHOLDERS`，這是 T-5 改判的依據。
  - `registry.py:62-63`：登記表的實際位置，這是 T-4 改判的依據。
  - `rules.py:77-89`：`OUTLOOK_RULE_FIELDS` 已設定。
  - `yfinance.py:415`：`source_id = "yfinance"`。
  - `app/` 內沒有 `env_file` 或 `load_dotenv`，所以 import 鏈不會讀 `.env`。
- **我沒有實證、也無法實證的部分**（唯讀，沒有 Bash）：
  - `uv.lock` 的 blob 是否為 `i/lf`。
  - 補上 `eol=lf` 屬性後，`git checkout HEAD -- uv.lock` 能否修正 CRLF 工作樹。這一點已在補充六第 7 點指定由 devops-sre 用臨時 repo 實證。
  - 真實快取裡 `^TWII` 的 `source`、`market` 與深度。
  - 「列對應逐欄相同」目前只是約束，要等 dev-lead 寫測試才能實證。
- 依 #139 第二節，以上屬程式行為的疑點，由 dev-lead 或 devops-sre 實證，TA 只判讀結果。

---

## 下一步

1. **coordinator**：
   - 依我的建議定案 #139 分類：T-1～T-6 屬本 PR 的插隊類，T-7 否決，其餘列凍結後待辦。
   - 把補充六交 tech-writer 落檔。
   - 把 Q-1、Q-2 逐字轉交風控；風控確認前，不要通知 CEO 執行時機。
2. **tech-writer**：依上面兩個插入位置，把補充六逐字落檔到 `docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`，commit 類型用 `docs:`。
3. **devops-sre 與 dev-lead**：依補充六修改設計後開 `feat/nm5-pipeline-acceptance-oneclick`。和原提案的差異有六點：
   - `bars_sources` 改封閉集；
   - `bars_sha256` 改用 `canonical.content_sha256`；
   - 不輸出 session 數那一行；
   - `where` 全部不輸出；
   - `.gitattributes` 放在 `apps/stock-desk/backend/`；
   - 不改 `recorder.py`。

   依約束 C-1～C-9 與 S-13b 補測試，送 qa-reviewer（含 Codex）。
4. **qa-reviewer**：審這個 PR 時，用 S-13b 逐條核對；審查清單加入「診斷回報不得含標籤」一行。CG-2 PR 時再核對補充六第 6 點 (b)～(d)。
5. **風險提示**：如果 CEO 的快取深度不足，一鍵檔會停在 `cache_depth=short`。依 D-7 第 6 點，一鍵檔不得上網補資料，屆時由 coordinator 升級 TA 與 data-engineer 另議。這會擋住 CG-2。

相關檔案：
- /home/user/AICompany/work/reviews/2026-11-15-真實資料管線驗收一鍵檔設計-devops-sre.md
- /home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md
- /home/user/AICompany/work/dispatch/2026-11-11-N207規格凍結與測試實證令-coordinator.md
- /home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/forecast_pipeline_harness.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/tests/dirdef_helpers.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/forecast/recorder.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/forecast/canonical.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/data/cache.py
- /home/user/AICompany/.claude/worktrees/agent-ad78bd45a459a429e/apps/stock-desk/backend/app/dirdef/registry.py

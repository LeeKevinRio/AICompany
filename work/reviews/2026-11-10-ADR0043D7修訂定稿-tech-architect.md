# ADR-0043 D7 修訂定稿（併入 RC-75～RC-79）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：ADR-0043 D7 第 1～3 點修訂定稿（併入風控 RC-75～RC-79）

## 一、本次結論

ADR-0043 D7 修訂定稿寫好了，第二段 A～C 三塊都可以直接貼上，交 tech-writer 併入 ADR-0043。風控列的條件全部併入，不必回送風控，由 qa-reviewer 逐條核對（對照表在第二段 F）。D3 第 7 點的 J/I 條文、D7 第 4～6 點原文都沒有動。

各條件的處理：

1. **RC-75 required-1（解析函式只留一個）**：採用 `parse_high_volatility_flag(raw: object) -> int`。修一檔 N207-C21 的 `high_volatility_marked` 撤回，app/ 內出現次數必須為 0。
   - 不選回傳 bool 的版本，理由是：把 bool 結果再解析一次時，`type(True) is int` 為假，結果會變成 0；回傳 int 則再解析也不變。
   - AST 單一性檢查共 7 條（D7 第 2 點）。
   - N207-C21 的替換全文在第二段 D。
2. **RC-75 required-2（壞 `changed_on`）**：鎖內讀到該檔歷程有無法解析的 `changed_on` 時，標記與取消一律拒絕、零寫入，預覽也拒絕；這個判斷排在冪等判定之前。
   - 拒絕暫時走既有的一般失敗分支，不得用 `ROSTER_RESULT_*`、W-25d～f，也不得寫成「已取消」「已標記」。
   - 另外我加嚴一項：不借用 `ROSTER_REFUSED_PREVIEW_STALE` 與 `ROSTER_REFUSED_TRANSIENT`。這兩句分別引導使用者重新預覽、重試，對永久存在的壞列都不成立。
3. **RC-75 required-3（時鐘落後）**：新增殘留 H-1，寫明方向較寬、偵測不到，並附數值例子。
   - 風控的 suggested（加入 `roster_log.taipei_date` 最大值）**建議採用，已寫進 D7 第 3 點 (d)**。它只會讓標記延後適用，方向較嚴；成本是同一個鎖內多一句 SELECT。它能縮小 H-1 的範圍，但關不掉 H-1。
4. **RC-75 required-4（2-B 連動句）**：已改寫，寫明 L6 方向較寬、L4 方向較嚴，句末為「風控 RC-77 裁示改擬（F2）」。
5. **RC-76（測試表）**：附錄 D7-T 補上 E16a～c（B 為 `'x'`、2、0.5）、W8、L10，以及 suggested 的 E17、L11、E18。
   - 我另外補了 W8b、W9～W12、L12、L13、P3、P4，分別釘住 required-1、required-2 與採用 suggested 後的行為。
6. **RC-79（W25f-2′）**：兩處都改了（第二段 E）：
   - 「方向保守」改為「實際門檻可能較字面所示嚴」，並附上 L11；
   - 「真偽」一段改為「待 RC-77 新子句定稿後核對」。
   - 殘留 H-2「最新一列壞值會被當成取消」已記入 ADR。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 評估摘要

- **採用**：
  - `parse_high_volatility_flag -> int`，再加上單一讀取 helper `_read_high_volatility`；
  - 壞 `changed_on` 時，回內部原因碼，API 層映射到既有的一般失敗分支；
  - 標記時的 `changed_on` 取 `max(today_tpe, L, R)`，R 是 roster_log 中有效 `taipei_date` 的最大值。
- **否決**：
  - `high_volatility_marked -> bool`；
  - 借用 `PREVIEW_STALE`／`TRANSIENT` 字面；
  - 以外部資料日作為下界（與 RC-21、Q-C14 衝突）。

#### 方案比較

| 題目 | 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| 解析函式名 | **(a) `parse_high_volatility_flag -> int`（採）** | 和 E、T 的 `base: int`、`value: int` 型別一致；parse 兩次結果不變 | N207-C21、T30 要改字 | 低 |
| | (b) `high_volatility_marked -> bool` | N207-C21 不必改 | 結果再 parse 一次會得 0，是靜默錯誤；E、T 要另轉型 | 中 |
| 壞 `changed_on` 的拒絕路徑 | **(a) 內部原因碼，API 映射到既有一般失敗分支（採）** | 測試可以斷言原因；不新增字面；符合 RC-75 的暫行規定 | 使用者看不到具體原因，要等專用字面定稿 | 低 |
| | (b) 直接 raise，回 500 | 不必新增分支 | 和程式錯誤分不開，測試無法區分原因 | 中 |
| | (c) 借用 PREVIEW_STALE 或 TRANSIENT | 已有定稿字面 | 引導重新預覽或重試，對永久壞列不成立 | 中 |
| 標記的參考日（RC-75 suggested） | **(a) `max(today_tpe, L, R)`（採）** | 偵測範圍擴大到任何名單寫入記錄過的日期；方向只會變嚴；多一句鎖內 SELECT | 範圍擴大到全部標的：過去某次時鐘跳前寫入的 roster 列，會讓所有標的的標記延後到那一天（較嚴，預覽與 W-25e 的 M/D 看得到） | 低 |
| | (b) 維持 `max(today_tpe, L)` | 不變動 | H-1 範圍較大 | 低（較寬） |
| | (c) 以最新 bar 日期作為真實日期的下界 | 不依賴本機時鐘 | 等於讓名單路徑多一個資料日來源，與 RC-21、Q-C14 衝突，要另立 ADR | 中 |

#### A. D7 標題與第 1～3 點（取代 ADR-0043 現行 D7 標題與第 1～3 點；第 4～6 點原文不改）

````markdown
### D7：高波動標記的接線與生效（併入 N-204；第 1～3 點 2026-11-10 依風控 RC-56（O-2）修訂，風控 2026-11-10 確認（RC-75～RC-80），RC-75、RC-76、RC-79 的條件已併入，由 qa-reviewer 逐條核對；W-25f 第三子句另有閘，見第 2 點）

1. **資料：只能新增的變更歷程**
   - 在 `_SCHEMA` 新增表 `playbook_high_volatility_log`（`CREATE TABLE IF NOT EXISTS`），欄位如下：
     - `id INTEGER PRIMARY KEY AUTOINCREMENT`
     - `symbol TEXT NOT NULL`
     - `value INTEGER NOT NULL CHECK (value IN (0, 1))`
     - `changed_on TEXT NOT NULL CHECK (date(changed_on) IS changed_on)`：Asia/Taipei 日期，ISO 格式，取值見第 3 點
     - `created_at TEXT NOT NULL`：UTC ISO
   - 這張表沒有 UNIQUE 約束，所以 `INSERT OR REPLACE` 不可能取代既有列。
   - 另以 `CREATE TRIGGER IF NOT EXISTS` 擋 UPDATE 與 DELETE（`RAISE(ABORT, …)`），比照 D9 第 3 點。
   - app/ 內對這張表只有第 3 點那一句 INSERT。`INSERT OR REPLACE`、UPDATE、DELETE 計數為 0（grep）。
   - `playbook_symbols.high_volatility` 改稱**基準值 B**：
     - 是部署前就存在的值，app/ 內不寫（現況就沒有寫入者，見 Context 第 1 點）；
     - `playbook_symbols` 沒有該檔的列時，B = 0。
   - **撤回**原第 1 點的 `high_volatility_prev`、`high_volatility_changed_on` 兩欄，不新增。
   - D3 第 7 點 I-4 原文不動：那兩個名稱照樣不得出現在 `engine.py`。新名稱的 engine 檢查見第 2 點。
   - **第 4～6 點的讀法**（原文不改，依此對照）：
     - 「`changed_on`」指該檔歷程中 **id 最大一列**的 `changed_on`；
     - 「`changed_on` 為 NULL」（第 6 點）指該檔在歷程表**沒有任何列**；
     - 「目標值」指第 2 點的 T；
     - 第 4 點的 `effective` 指第 2 點的 E。

2. **解析與判定：單一定義**（與 `entry_gate_open` 同放 `store.py`，每個名稱只有一份定義）
   - `HighVolChange(NamedTuple)`：`id: int`、`value: int`、`changed_on: date`。
   - **解析**（風控 RC-63；RC-75 required-1；RC-56 驗收標準 2）：
     - **`parse_high_volatility_flag(raw: object) -> int`**：本體恰為 `return 1 if type(raw) is int and raw == 1 else 0`。
       - 只有 integer 1 回傳 1；其他值一律回傳 0，包括 2、-1、`'x'`、0.5、None、bool（`type(True)` 是 bool，不是 int）。
       - 適用於基準值 B，也適用於每一筆歷程列的 value。ADR 或規格的任何版本若保留 `high_volatility_prev` 欄位，該欄位也照這條規則解析。
       - 回傳 int、不回傳 bool 的理由：E、T 的 base 與 value 是 int；而且回傳 bool 時，結果若被再解析一次，`type(True) is int` 為假，會得到 0。回傳 int 時，`parse(parse(x)) == parse(x)`。
       - **N-207 規格 N207-C21 原定的 `high_volatility_marked(raw) -> bool` 撤回**，N207-C21 改為引用本函式。app/ 內不得出現 `high_volatility_marked` 這個名稱。
     - **`parse_high_volatility_changed_on(raw: object) -> date | None`**：`type(raw) is str`、`date.fromisoformat(raw)` 不拋例外，而且 `.isoformat() == raw` 時，回傳該日期；否則回傳 None。拒絕範圍與第 1 點的 CHECK 意圖一致：不存在的日期、斜線格式、前後空白、非 TEXT 都拒絕。
   - **單一讀取 helper** `_read_high_volatility(conn, symbols) -> dict[str, HighVolRead]`（接收 conn，與 D4 第 3 點 (a) 的 helper 同一型式）：
     - `HighVolRead(NamedTuple)`：`base: int`、`history: tuple[HighVolChange, ...]`、`history_readable: bool`。
     - 讀取該檔 B 與全部歷程列（依 id 升冪）。B 經 `parse_high_volatility_flag`；每列 value 經 `parse_high_volatility_flag`，changed_on 經 `parse_high_volatility_changed_on`。
     - 任一列的 changed_on 解析為 None 時：`history_readable = False`、`base = 0`、`history = ()`。所以對所有 `on`，T = 0、E = 0。
       - 在 app/ 內，這種情況由 CHECK 約束排除，只可能來自 app 外的寫入（殘留 H-3）。
     - 名單頁標籤（W-25d～f、W-27 旗標）、engine 輸入、第 3 點的寫入路徑，一律只經本 helper 加上 E、T 取值，不得各自解析或另讀原始欄位。
     - 評估路徑與名單頁讀取遇到解析問題時不 raise：只會讓該檔門檻偏嚴（15%），不讓 `/today` 失敗，S 系列的停損賣出照常評估。寫入路徑依第 3 點 (a′) 拒絕。
     - 與 P-4 的一致性：
       - P-4c 等於 0 時，`playbook_symbols.high_volatility` 全部是 integer 0 或 1，P-4a 的 `<> 0` 恰好等於本函式判為 1 的列；
       - P-4c 大於 0 時依 STOP-4 處理，部署通知第二段暫不送出（RC-62）。
   - **生效值** `effective_high_volatility(*, base: int, history: Sequence[HighVolChange], on: date) -> int`，記為 E(on)：
     - 適用列 = `history` 中 `changed_on < on` 的列；
     - 有適用列時，取其中 **id 最大者**的 value；沒有就取 base。
   - **目標值** `target_high_volatility(*, base: int, history: Sequence[HighVolChange]) -> int`，記為 T：
     - `history` 有列時，取 id 最大者的 value；沒有就取 base。
   - 兩個函式都只依 id 排序，不依 `changed_on` 排序。
   - **評估**：`on = data_date`。
     - data_date 都是交易日，所以「`changed_on` 早於 data_date」等價於「變更日之後的第一個交易日起適用」。
     - 依據資料日不晚於變更日的評估，用的是變更前的值（FR-30、AC-65）。
     - 每一筆變更各自從它的 `changed_on` 之後適用，不會覆寫任何較早資料日的生效值。
     - 判定不需要日曆，也不受週一到週五退回判定的影響。
   - **名單頁標籤**：`on = today_tpe`，取值來源與 D1 第 4 點、D8 第 6 點相同。
     - W-25d：T = 1 且 E(today_tpe) = 1；
     - W-25e：T = 1 且 E(today_tpe) = 0；
     - W-25f：T = 0 且 E(today_tpe) = 1；
     - 其餘情形不顯示高波動標籤。
     - W-25e、W-25f 的日期依第 5 點。
     - **W-25f 第三子句：定稿暫停（風控 RC-58；RC-77 採 F2）**。舊字面「今日仍用高波動門檻」不得與本修訂一起進入程式或畫面。新字面由 creative-lead 擬稿、風控逐字定稿：方案 (A) 下是 N-207 的合併閘，方案 (B) 下是 D7 單的合併閘。
   - **讀取**：`symbol_states(on)` 用一個連線、一個讀取交易（`BEGIN`…`COMMIT`），經 `_read_high_volatility` 讀出 `playbook_symbols` 與 `playbook_high_volatility_log`，對每檔呼叫上述函式。
   - **engine 名稱檢查**（補 I-4 的可檢查形式，不改 I-4）：`engine.py` 不出現 `playbook_high_volatility_log`、`HighVolChange`、`HighVolRead`、`effective_high_volatility`、`target_high_volatility`、`parse_high_volatility_flag`、`parse_high_volatility_changed_on`、`_read_high_volatility`。engine 照舊只透過 `build_market_snapshot(high_volatility=…)` 拿到值（第 4 點）。
   - **單一性檢查**（AST，全部 BLOCKING；RC-75 required-1）：
     1. app/ 內名為 `parse_high_volatility_flag`、`parse_high_volatility_changed_on`、`_read_high_volatility` 的函式定義各恰 1 個，都在 `app/playbook/store.py`。
     2. 識別名 `high_volatility_marked` 在 app/ 內的出現次數為 0，包括函式定義、Name、Attribute、字串常數。
     3. **判定式恰出現一次**：app/ 內同時含有 `type(N) is int` 與 `N == 1`（同一個 Name N）的 `BoolOp(And)` 節點恰 1 個，而且位於 `parse_high_volatility_flag` 本體內。
     4. **本體形狀**：`parse_high_volatility_flag` 本體恰為一條 `Return`，值為 `IfExp`：test 是第 3 項的 BoolOp，body 為 `Constant(1)`，orelse 為 `Constant(0)`。本體不得出現 `bool(`、`int(`、`!= 0`、`> 0`，也不得以 raw 做真值判斷。
     5. **呼叫點封閉**：兩個解析函式的呼叫，以及 `HighVolChange(...)` 的建構，只出現在 `_read_high_volatility` 本體內。該本體的 `Compare` 節點只能是 `… is None` 或 `… is not None`。
     6. **原始值讀取封閉**：app/ 內含子字串 `high_volatility` 的非 docstring 字串常數（不分大小寫；f-string 每段各自計算），只能出現在 `store.py` 的 `_SCHEMA`（DDL 與 trigger）、`_read_high_volatility`（SELECT），以及第 3 點寫入函式的那一句 INSERT。
     7. **負例**：把含第二份判定式或第二個解析函式的原始碼字串餵給檢查器，必須判為違規。
   - 測試見附錄 D7-T（E、L、P3、P4）。

3. **寫入：高波動標記操作**（D4 的兩步流程與鎖內流程）
   - (a) **鎖內讀取**：經 `_read_high_volatility` 讀該檔的 `HighVolRead`；另以 `SELECT MAX(taipei_date) FROM playbook_roster_log WHERE date(taipei_date) IS taipei_date` 讀 R，結果再經 `parse_high_volatility_changed_on` 解析。沒有列或解析為 None 時，R 不存在。
   - (a′) **歷程無法解析時拒絕**（風控 RC-75 required-2）：
     - `history_readable` 為 False 時，本次操作一律拒絕、零寫入。標記與取消都一樣，判斷排在 (c) 冪等判定之前。
     - 預覽也以同一個 helper 讀取，遇到同一情形同樣拒絕，不回傳預覽摘要。
     - 預覽通過後才出現的壞列，確認時在鎖內同樣拒絕。
     - 理由：評估端這時已是 E = 0（15%）。拒絕標記，維持 15%；拒絕取消，E 本來就是 0。兩者都不會變寬。
     - **回應**：store 回傳內部原因碼（名稱由 N-207 v3 定，不是使用者可見字面），API 層映射到名單操作既有的一般失敗分支。專用的拒絕字面由 creative-lead 擬、風控定稿；定稿之前：
       - 不得新增使用者可見字面；
       - 不得使用任何 `ROSTER_RESULT_*`、W-25d～f；
       - 不得寫成或渲染成「已取消」「已標記」；
       - 不借用 `ROSTER_REFUSED_PREVIEW_STALE`、`ROSTER_REFUSED_TRANSIENT`。這兩句分別引導重新預覽、重試，對永久存在的壞列不成立。
     - D4 第 4 點的零寫入與 D9 第 2 點的「拒絕不寫稽核列」照常適用。
   - (b) **時鐘**：以 D4 第 3 點 (b) 讀到的時鐘，換算成 Asia/Taipei 日期 `today_tpe`。
   - (c) **冪等**：新值等於 T 時，零寫入，也不寫稽核列（比照 D2 第 5 點）。
   - (d) **`changed_on` 的取值**（併入風控 RC-75 suggested）：
     - 參考日：
       - L = 該檔最新一列（id 最大）的 `changed_on`，沒有歷程時不存在；
       - R = (a) 讀到的 roster 最大有效台北日，可能不存在。
     - 標記（新值 1）：`changed_on = max(today_tpe, L, R)`，不存在的參考日略過。
     - 取消（新值 0）：`changed_on = today_tpe`。
     - 一般情形（L、R 都不晚於 `today_tpe`）兩者都等於 `today_tpe`。
     - **方向**：兩種取法都不比「以 `today_tpe` 寫入」寬：標記只會延後適用；取消不延後，而且因為 id 最大，會蓋過較晚日期的那一列。
     - **限制**：上一句以 `today_tpe` 為比較基準，不能讀成精確保持 FR-30。`today_tpe` 本身落後真實台北日期、而 L、R 都不晚於 `today_tpe` 時，系統偵測不到這種落後，標記會比 FR-30 規定的更早適用，方向較寬（殘留 H-1）。
     - **R 的前提**：`playbook_roster_log.taipei_date` 是 D4 第 3 點 (b) 同一次時鐘讀取換算的 Asia/Taipei 日期（D9 第 1 點）。N-207 v3 若不是這樣，回 TA。
     - 無效的 `taipei_date` 由 WHERE 排除，不因此拒絕寫入。排除只會讓 R 變小或不存在，結果不會早於 `today_tpe`。
   - (e) **INSERT** 一列：symbol、value、changed_on、created_at。
   - (f) **D9 稽核列**照常寫入。`detail_json` 記入本次歷程列的 id、value、changed_on，以及 `today_tpe`、L、R（不存在時為 null）。
   - **預覽摘要**（D4 第 1 點）包含：symbol、目前的 T、最新一列的 id（沒有則為 null）、新值、預覽時算出的 `changed_on`。
     - 確認時在鎖內重算，任一項不同就拒絕、零寫入（FR-22）。
     - 預覽與確認之間跨過台北日期，或 R 改變，都會因 `changed_on` 不同而拒絕，使用者要重新預覽。
   - **性質**（RC-56 驗收標準 1 的論證，由結構保證）：
     - 新增一列，記它的 `changed_on` 為 c。對任何 `on` ≤ c，這一列都不在適用列內，E(on) 不變。
     - (d) 的三種取法，c 都不早於 `today_tpe`。所以任何一次變更，都不改變依據資料日不晚於 c 的評估所用的生效值。
   - **同日來回切換**：同一天寫入的各列，對 `on` 不晚於該日的判定都不適用；對 `on` 晚於該日的判定，只看 id 最大的那一列。所以回到原值時，任何資料日的生效值都不變。
   - **多次變更**：每一筆各自從它的 `changed_on` 之後適用。例：週一標記、週二取消、週三再標記，則依據資料日週一用 0、週二用 1、週三用 0、週四起用 1。
   - 測試見附錄 D7-T（W、P1、P2），全部 BLOCKING。
````

#### B. 連動修訂（和 A 同一次落檔；D3 第 7 點 J-1～J-10、I-1～I-5 一字不動）

- **檔頭變更紀錄**加一行：「2026-11-10 依風控 RC-56（O-2）修訂 D7 第 1～3 點，併入風控 RC-75～RC-79 的條件；連動修訂 D4 第 3、4 點、D9 第 1 點、Consequences『壞處與代價』『被約束』、待決；新增附錄 D7-T（風控 2026-11-10 確認，RC-75～RC-80）」。
- **決策者 → risk-compliance-officer**，句末加：「；D7 第 1～3 點修訂：風控 2026-11-10 確認（RC-75～RC-80，見 work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md），required 併入後不回送，qa-reviewer 核對：{日期與檔名，tech-writer 落檔時填入}」。
- **來源簡稱**加兩項：
  - [風控-D7]：`reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md`（RC-75～RC-83）
  - [TA-D7]：`reviews/2026-11-10-ADR0044定稿與ADR0043D7修訂-tech-architect.md` 交付 2，以及 `reviews/2026-11-10-D7拆單評估與RC63補充-tech-architect.md` 2-F～2-H
- **D4 第 3 點 (a)**，句末加：「；高波動標記操作另經 `_read_high_volatility` 讀該檔的基準值與 `playbook_high_volatility_log` 全部列，並讀 `playbook_roster_log` 有效 `taipei_date` 的最大值（D7 第 3 點 (a)、(d)）」。
- **D4 第 3 點 (d)** 改為：「(d) 寫入只限四處：`playbook_symbols` 的自有欄位 upsert、`playbook_batches` 的新輪 INSERT、`playbook_high_volatility_log` 的 INSERT（只限高波動標記操作，D7 第 3 點）、`playbook_roster_log` 的 INSERT；」
- **D4 第 4 點**：「三張表都逐列不變」改為「四張表（含 `playbook_high_volatility_log`）都逐列不變」。
- **D9 第 1 點**：
  - `taipei_date TEXT NOT NULL` 一行，句末加：「（D4 第 3 點 (b) 同一次時鐘讀取換算的 Asia/Taipei 日期；D7 第 3 點 (d) 以此為前提）」；
  - `detail_json` 的括號內，句末加：「、高波動標記的歷程列 id、value、changed_on，以及 today_tpe 與 D7 第 3 點 (d) 的參考日 L、R」。
- **Consequences「壞處與代價」**加下列各點：
  - 「**高波動改為只能新增的歷程表**（D7 第 1～3 點）：多一張表與兩個 trigger。名單頁標籤依台北日期判定，今日頁依資料日判定；資料落後期間內有多次變更時，兩者的落差有兩種方向：(i) **L6**：標籤寫『尚未適用』，今日頁用 20%，方向較寬，由 W-27 第二句與 W-22 第二行揭露，不新增顯示條件（風控 RC-78）；(ii) **L4**（另見 L11，標記從未適用）：W-25f 第三子句不實，方向較嚴；風控 RC-77 裁示改擬（F2）。」
  - 「**H-1 時鐘落後，偵測不到**（風控 RC-75 required-3；比照 ADR-0044 R-c）：`today_tpe` 落後真實台北日期，而 L 與 R 都不晚於 `today_tpe` 時，標記的 `changed_on` 會早於真實日期。資料日落在 (`today_tpe`, 真實日期] 的評估（包括時鐘校正之後的評估）改用 20%，違反 FR-30『變更當日仍用舊門檻』，**方向較寬，系統偵測不到**。例：真實日期 11-12、時鐘顯示 11-10、最後一次名單寫入也在落後之後 → `changed_on` = 11-10，資料日 11-11、11-12 的評估用 20%；照 FR-30 應從 11-13 起。R（採用 RC-75 suggested）把偵測範圍擴大到任何名單寫入記錄過的較晚日期，但關不掉這項殘留。取消不受影響：提早適用的方向是較嚴。列為殘留，交 CEO 接受或修正。」
  - 「**H-2 最新一列壞值被當成取消**（風控 RC-79）：最新一列若是 app 外寫入的壞 value，會解析為 0，T = 0。名單頁可能出現 W-25f，但使用者沒有做過取消。E 的方向較嚴。」
  - 「**H-3 歷程有壞 `changed_on` 時，該檔永久退回 15%**（2-F、RC-75 required-2；比照 RC-49 條件 4）：這種列只可能來自 app 外的寫入，而且歷程表擋 DELETE，壞列會永久存在。結果是該檔對所有資料日 E = 0、不顯示高波動標籤、標記與取消操作一律拒絕，方向較嚴。修復路徑另案設計並送風控，不得手動改 DB。」
  - 「**H-4 較寬方向的標籤落差**：L6（見上）與 L10（O-1，取消側；風控 RC-55 已裁示揭露。整頁沒有任何標籤時，W-27 不顯示，只剩 W-22 第二行）。`/today` 加事實欄位的新單不列為 N-207 的上線條件（風控 RC-73、RC-78）；app 有第二個使用者時，這張新單轉為 required。」
- **Consequences「被約束」**：
  - 第一點改為：「名單路徑只能寫 `playbook_symbols` 的自有欄位、`playbook_batches` 的新輪 INSERT、`playbook_high_volatility_log` 的 INSERT、`playbook_roster_log` 的 INSERT；」
  - 新增一點：「高波動的原始值只經 D7 第 2 點的 `_read_high_volatility` 與兩個解析函式讀取；`playbook_high_volatility_log` 只能 INSERT。」
- **待決**新增：
  - CEO：
    - D7 拆不拆單（(A)／(B)；選 (B) 時適用風控 RC-82 的前提條件）；
    - 殘留 H-1～H-4 接受或修正；
    - RC-73 的新單是否開立。
  - 風控：
    - W-25f 第三子句新字面的逐字定稿（RC-77，附自查表）；
    - D7 第 3 點 (a′) 專用拒絕字面的定稿（RC-75 required-2）。
  - creative-lead：上述兩句擬稿；W-27 備註依 RC-79 更新。
  - tech-architect：H-3 的修復路徑另案，和 D7 第 6 點「取消」的移除方式（AC-95）一併設計。

#### C. 附錄 D7-T：參數化測試表（放在 ADR-0043 文末；取代交付檔 2-C）

````markdown
## 附錄 D7-T：D7 參數化測試表（RC-56 驗收標準 3；風控 RC-76）

日期採 2026-11：11-09 週一、11-10 週二、11-11 週三、11-12 週四、11-13 週五、11-14 週六、11-15 週日、11-16 週一。E 的測試不依賴日曆；涉及 M/D 的標籤測試用固定的日曆 fixture。標「PRAGMA」的列，以 `PRAGMA ignore_check_constraints = ON` 直接 SQL 種入，模擬 app 外的寫入。全部 BLOCKING。

評估（E）：

| # | 情境 | B | 歷程（依 id；changed_on:value） | on | 期望 E | 說明 |
|---|---|---|---|---|---|---|
| E1 | 沒有歷程 | 0 | — | 11-10 | 0 | |
| E2 | 沒有歷程、既有標記 | 1 | — | 11-10 | 1 | D7 第 6 點：部署當下即適用 |
| E3a | 單次標記，當日 | 0 | 11-10:1 | 11-10 | 0 | AC-65 第一段：當日用舊門檻 |
| E3b | 同上，次一交易日 | 0 | 11-10:1 | 11-11 | 1 | |
| E4a | 單次取消，當日 | 1 | 11-10:0 | 11-10 | 1 | AC-65 第二段 |
| E4b | 同上，次一交易日 | 1 | 11-10:0 | 11-11 | 0 | |
| E5 | O-2 原例，取消前 | 0 | 11-09:1 | 11-09 | 0 | 15% |
| E6a | O-2 原例，取消後 | 0 | 11-09:1, 11-10:0 | 11-09 | 0 | 取消前後都是 15%（驗收標準 1） |
| E6b | 同上 | 0 | 同上 | 11-10 | 1 | 週一的標記從週二資料起適用 |
| E6c | 同上 | 0 | 同上 | 11-11 | 0 | 週二的取消從週三資料起適用 |
| E7a | 週末標記 | 0 | 11-14:1 | 11-13 | 0 | 週五資料在週末評估，用舊值 |
| E7b | 同上 | 0 | 11-14:1 | 11-16 | 1 | |
| E8a | 週末取消 | 1 | 11-15:0 | 11-13 | 1 | |
| E8b | 同上 | 1 | 11-15:0 | 11-16 | 0 | |
| E9a | 同日來回，回到原值 | 0 | 11-10:1, 11-10:0 | 11-10 | 0 | |
| E9b | 同上 | 0 | 同上 | 11-11 | 0 | 生效值不變 |
| E10 | 同日來回（B=1） | 1 | 11-10:0, 11-10:1 | 11-11 | 1 | |
| E11a | 同日三次 | 0 | 11-10:1, 11-10:0, 11-10:1 | 11-10 | 0 | |
| E11b | 同上 | 0 | 同上 | 11-11 | 1 | |
| E12 | 多次變更、逐日 | 0 | 11-09:1, 11-10:0, 11-11:1 | 11-09／11-10／11-11／11-12 | 0／1／0／1 | 舊設計在 on=11-10 得 0（錯，偏嚴）；取消後在 on=11-09 得 1（錯，O-2） |
| E13 | 多次變更跨週末 | 0 | 11-13:1, 11-14:0, 11-16:1 | 11-13／11-16／11-17 | 0／0／1 | 週五標記、週六取消，兩者都從週一起適用；id 較大的取消勝出 |
| E14a | 時鐘倒退後取消（依第 3 點 (d) 寫入） | 0 | 11-12:1, 11-10:0 | 11-10 | 0 | 與寫入前相同 |
| E14b | 同上 | 0 | 同上 | 11-11 | 0 | 與寫入前相同（寫入前沒有適用列，取 B） |
| E14c | 同上 | 0 | 同上 | 11-13 | 0 | 寫入前是 1；取消不延後，偏嚴 |
| E15 | 歷程有壞 `changed_on`（PRAGMA） | 0 | 11-09:1, `'2026/11/10'`:1 | 11-10／11-11 | 0／0；T = 0 | `history_readable` = False；其他列即使可解析為 1，也一律為 0（H-3） |
| E16a | B 是壞值（與 N207-T30 共用 fixture） | `'x'` | — | 11-10 | 0；T = 0 | 不顯示任何標籤 |
| E16b | 同上 | 2 | — | 11-10 | 0；T = 0 | 同上 |
| E16c | 同上 | 0.5 | — | 11-10 | 0；T = 0 | 同上 |
| E17 | W2 寫入後的評估 | 1 | 11-12:0, 11-12:1（後者依 (d) 取 max） | 11-12／11-13 | 1／1 | 寫入前 on=11-13 為 0；on ≤ 11-12 不變 |
| E18 | 最新一列 value 是壞值（PRAGMA） | 0 | 11-09:1, 11-10:`'x'` | 11-10／11-11 | 1／0；T = 0 | 壞值解析為 0，等同取消（H-2）；標籤見 L12 |

寫入（W）：除非另外註明，`playbook_roster_log` 為空，或其 taipei_date 都不晚於 today_tpe。「四張表」指 `playbook_symbols`、`playbook_batches`、`playbook_high_volatility_log`、`playbook_roster_log`。

| # | 情境 | 期望 |
|---|---|---|
| W1 | 一般：最新一列 11-09，today_tpe = 11-10 | `changed_on` = 11-10 |
| W2 | 時鐘倒退標記：最新 11-12:0，today_tpe = 11-10，新值 1 | `changed_on` = 11-12 |
| W3 | 時鐘倒退取消：最新 11-12:1，today_tpe = 11-10，新值 0 | `changed_on` = 11-10 |
| W4 | 冪等：新值等於 T | 歷程表、稽核表列數都不變 |
| W5 | 預覽在台北 11-10 23:59:59，確認在 11-11 00:00:01 | 拒絕，四張表逐列不變 |
| W6 | 對歷程表 UPDATE 或 DELETE | trigger ABORT |
| W7 | 拒絕或失敗的高波動操作 | 四張表逐列不變（FR-39、AC-61） |
| W8 | 歷程有壞 `changed_on`（PRAGMA，同 E15），分別做標記與取消 | 預覽與確認都拒絕；四張表逐列不變；不寫稽核列；回應走既有的一般失敗分支，不是任何 `ROSTER_RESULT_*`；回應與渲染不含「已取消」「已標記」；store 的內部原因碼可以斷言 |
| W8b | 預覽通過後才種入壞列，再確認 | 鎖內拒絕，期望同 W8 |
| W9a | roster 最大有效台北日 R = 11-12；B = 0；沒有歷程；today_tpe = 11-10；標記 | `changed_on` = 11-12（RC-75 suggested） |
| W9b | 同上，但 B = 1；取消 | `changed_on` = 11-10 |
| W10 | roster 有 `'2026-11-09'` 與 `'2026/11/20'` 兩列（直接 SQL）；沒有歷程；today_tpe = 11-10；標記 | `changed_on` = 11-10；壞列被排除，不拒絕。少了 WHERE 時，字典序 MAX 會取到 `'2026/11/20'`，本列因此失敗 |
| W11 | 最新一列 value 是壞值（同 E18，T = 0）；today_tpe = 11-10 | 取消：冪等，零寫入。標記：不拒絕，INSERT `changed_on` = 11-10 |
| W12 | 任一成功寫入 | 稽核列 `detail_json` 含歷程列 id、value、changed_on、today_tpe、L、R（不存在時為 null） |

性質與結構（P）：

- **P1（驗收標準 1，窮舉）**：
  - 範圍：日期取 11-09～11-16 共 8 天；B ∈ {0, 1}；R ∈ {不存在} ∪ 8 天；歷程長度 0～3，依第 3 點規則逐筆寫入，含時鐘倒退；再寫入一筆。
  - 斷言：
    - 對所有 `on` 不晚於新列 `changed_on` 的日期，寫入前後的 E(on) 相同；
    - 新列 `changed_on` 不早於 today_tpe。
  - 以 itertools 窮舉即可，不需要額外套件。
- **P2**：名單頁與評估只呼叫同一組函式（grep：store 與 API 內，`effective_high_volatility` 之外沒有第二份判定）。
- **P3（RC-75 required-1）**：D7 第 2 點「單一性檢查」1～7 項，含負例。
- **P4（解析）**：
  - 對 0、1、2、-1、`'x'`、0.5、None、True、False、`'1'`，`parse_high_volatility_flag` 只有 1 回傳 1；回傳值的 `type` 都是 int；`parse(parse(x)) == parse(x)`。
  - `parse_high_volatility_changed_on`：`'2026-11-10'` 回傳日期；`'2026-13-01'`、`'2026/11/10'`、`'2026-11-10 '`、`'20261110'`、20261110、None 都回傳 None。
  - 同一批字串對第 1 點 CHECK 的接受與拒絕要一致，以檔案 DB 實測。

標籤（L，`on = today_tpe`）：

| # | 歷程 | today_tpe | T | E | 標籤 | 今日頁資料日 → 實際門檻 | 備註 |
|---|---|---|---|---|---|---|---|
| L1 | E3 | 11-10 | 1 | 0 | W-25e，M/D = 11/11 | 11-09 或 11-10 → 15% | 一致 |
| L2 | E3 | 11-11 | 1 | 1 | W-25d | 11-10 → 15% | O-1 型落差，方向保守，與舊設計相同 |
| L3 | E4 | 11-10 | 0 | 1 | W-25f，M/D = 11/11 | 11-09 或 11-10 → 20% | 舊第三子句為真；新子句待 RC-77 |
| L4 | E6（O-2 原例取消後） | 11-10 | 0 | 1 | W-25f，M/D = 11/11 | 11-10 → 20%；11-09 → 15% | 舊第三子句在 11-09 不實，實際門檻較字面嚴（RC-77 採 F2） |
| L5 | E9 | 11-10 | 0 | 0 | 不顯示 | 15% | W25f-1′ 的禁止條款：不得以「T=0 且有歷程」判定 |
| L6 | E12 | 11-11 | 1 | 0 | W-25e，M/D = 11/12 | 11-10 → 20%；11-11 → 15% | 較寬落差：標籤寫「尚未適用」，今日頁（資料日 11-10）用 20%（RC-78、H-4） |
| L7 | E7 | 11-15（週日） | 1 | 1 | W-25d | 11-13 → 15% | O-1 型落差，方向保守，與舊設計相同 |
| L8 | E8 | 11-15（週日） | 0 | 1 | W-25f，M/D = 11/16 | 11-13 → 20% | 舊第三子句為真；新子句待 RC-77 |
| L9 | 任一列帶 W-25d／e／f | — | — | — | W-27 顯示 | — | 條件不變 |
| L10 | B = 1；11-10:0 | 11-11 | 0 | 0 | 不顯示 | 11-10 → 20% | O-1 取消側的較寬落差（RC-55 已裁示）；整頁沒有其他標籤時只剩 W-22 第二行（H-4） |
| L11 | B = 0；11-13:1（週五）, 11-15:0（週日） | 11-15（週日） | 0 | 1 | W-25f，M/D = 11/16 | 資料日最晚 11-13 → E(11-13) = 0 → 15%；11-16 起取消已適用 | 標記從未適用；舊第三子句在任何資料日都不成立（RC-77） |
| L12 | E18 | 11-10 | 0 | 1 | W-25f，M/D = 11/11 | 11-09 → 15%；11-10 → 20% | 使用者沒有取消，W-25f 仍出現（H-2） |
| L13 | E15 | 11-10 | 0 | 0 | 不顯示 | 15% | 壞 `changed_on` 整檔退回（H-3） |
````

#### D. 對實作的約束（交 dev-lead；qa-reviewer 可逐條檢查）

**N207-C21 替換全文**（取代修一檔「修一-4」的 N207-C21；這是 TA 規格，不是 ADR 內文）：

> **N207-C21 `high_volatility` 的執行期解析（BLOCKING）**
> - **單一解析函式**：依 ADR-0043 D7 第 2 點，使用 `app/playbook/store.py` 的 `parse_high_volatility_flag(raw: object) -> int`，本體與 AST 檢查依該點「單一性檢查」1～7 項。原定的 `high_volatility_marked` 撤回，app/ 內出現次數為 0。
> - **解析時點**：`playbook_symbols.high_volatility` 與歷程列的原始值，只在 `_read_high_volatility` 內經解析函式轉為 0 或 1。`SymbolState`（pydantic）不得收到原始值，只能收到解析函式與 E、T 的輸出；欄位型別由 v3 定。
>   - 理由：pydantic 的 bool 遇到 2、'x'、0.5 會 raise，整頁會 500。
>   - `build_market_snapshot(high_volatility=…)`（`models.py:175` 為 bool）由 E 轉入，不得再讀或再解析原始值。
> - **共用**：engine 輸入（N207-C15）、W-25d～f 標籤、W-27 顯示旗標，三者都只讀 store 的同一份結果。讀 `high_volatility` 的 SQL 依 D7 第 2 點第 6 項封閉。
> - **不採 raise**：評估與名單頁讀取讀到異常值不 raise。部署前的異常值由盤點 P-4c 與 STOP-4 處理；寫入路徑依 D7 第 3 點 (a′) 拒絕。

**N207-T30**：最後一點「涉及 `high_volatility_prev` 的情境，依 D7 修訂後補上」改為「歷程表情境依 ADR-0043 附錄 D7-T：E15～E18、W8～W11。種入 B 的 fixture 與 E16 共用」。其餘不變。

**其他約束**（C-D7-1～C-D7-6）：

- **C-D7-1**：D7 第 2 點「單一性檢查」1～7 項都要有測試（P3），而且都是 BLOCKING。
- **C-D7-2**：(a′) 排在 (c) 之前。實作 W8 時，歷程同時有壞 `changed_on`、而且新值等於 T，也必須拒絕，不得回冪等的結果。
- **C-D7-3**：W8 的回應不得新增使用者可見字面。前端與 `wording.py` 對這個原因碼的 grep，計數必須為 0，直到風控定稿專用字面為止。
- **C-D7-4**：R 的 SQL 必須帶 `WHERE date(taipei_date) IS taipei_date`，以 W10 釘住；`taipei_date` 的寫入來源以 D4 第 3 點 (b) 的同一次時鐘讀取為準。
- **C-D7-5**：舊 W-25f 字面「今日仍用高波動門檻」在 app/ 與前端的 grep 計數為 0（RC-77）。
- **C-D7-6**：`engine.py` 的名稱檢查擴到 D7 第 2 點所列 8 個名稱。

#### E. W25f-2′ 替換句（交 creative-lead，取代草稿 W-25 備註的 W25f-2′；W25f-1′、3′ 不變）

- **W25f-2′（參考日與真偽）**：
  - 參考日用 `today_tpe`，來源與 D1 第 4 點、D8 第 6 點相同。一般情形下，只會在 `today_tpe` 等於最新一列 `changed_on` 的當天顯示。
  - **舊第三子句「今日仍用高波動門檻」不恆真**：今日頁的資料日 d 早於 `today_tpe`，而且該檔另有一列（不是最新那一列）的 `changed_on` 落在 [d, `today_tpe`) 時，今日頁可能用一般門檻。
    - 例一（L4，O-2 原例）：週二早上，資料日仍是週一，實際用 15%。
    - 例二（L11）：週五 11-13 標記、週日 11-15 取消，`today_tpe` = 11-15 時顯示 W-25f（M/D = 11/16）。但可能的資料日最晚是 11-13，E(11-13) = 0；從 11-16 起取消已經適用。這個標記從來沒有適用過。
    - 這種情形下，**實際門檻可能較字面所示嚴**。它一定落在「資料日早於台北今日」的範圍內，W-27 第二句已有揭露。
  - **真偽：待 RC-77 新子句定稿後核對。** 舊字面不得進入程式或畫面。
  - **殘留**（ADR-0043 H-2）：最新一列若是 app 外寫入的壞值，會被當成取消；名單頁可能出現 W-25f，但使用者沒有做過取消（L12）。

#### F. 給 qa-reviewer 的核對對照表

| 條件 | 併入位置 |
|---|---|
| RC-75 required-1（單一函式、AST 檢查、N207-C21 改為引用） | A 第 2 點「解析」與「單一性檢查」1～7；D 的 N207-C21 替換全文；附錄 P3、P4 |
| RC-75 required-2（壞 `changed_on`：拒絕、零寫入、預覽也拒絕、字面限制） | A 第 3 點 (a′)；附錄 W8、W8b；C-D7-2、C-D7-3 |
| RC-75 required-3（時鐘落後殘留：方向較寬、偵測不到） | A 第 3 點 (d)「限制」；B 的 H-1 |
| RC-75 suggested（roster_log 參考日） | 採用：A 第 3 點 (a)、(d)；B 的 D4 第 3 點 (a)、D9 第 1 點；附錄 W9、W10、W12、P1 |
| RC-75 required-4（L6 較寬、L4 較嚴，句末為「風控 RC-77 裁示改擬（F2）」） | B 的 Consequences「壞處與代價」第一點 |
| RC-76（E16 的 B=2、0.5，W8，L10，E17，L11，E18） | 附錄 D7-T 對應各列 |
| RC-79（W25f-2′ 兩處修改、壞值當成取消的殘留） | E；B 的 H-2；附錄 L12 |
| RC-77 閘（舊字面不得進程式或畫面） | A 第 2 點「名單頁標籤」；C-D7-5 |
| 沒有改動的內容 | D3 第 7 點；D7 第 4～6 點 |

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - 全文：
    - `/home/user/AICompany/work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md`
    - `/home/user/AICompany/work/reviews/2026-11-10-ADR0044定稿與ADR0043D7修訂-tech-architect.md`（2-0～2-E 在 :436-639）
    - `/home/user/AICompany/work/reviews/2026-11-10-D7拆單評估與RC63補充-tech-architect.md`
  - 部分：
    - `/home/user/AICompany/work/reviews/2026-11-10-N207規格v2補遺修訂一-tech-architect.md`：:100-189，含 N207-C21、T30
    - `/home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md`：:1-30、:225-474，含 D4、D7、D9、Consequences、待決
  - grep：N-207 相關檔的 `ROSTER_REFUSED_*` 清單；dev-lead v2 彙整檔。
- **讀過的程式**（唯讀 grep）：
  - app/ 內的 `high_volatility`：`store.py:124`、`models.py:175`、`engine.py:487`、`:505`、`service.py:155`、`:174`。字串常數只在 `_SCHEMA`，所以單一性檢查第 6 項現況可以成立。
  - app/ 內的 `type(...) is int`：沒有程式碼實例，只有 `yfinance.py:171` 的 docstring，所以第 3 項現況可以成立。`isinstance(..., int)` 散在 forecast、advice 等模組，第 3 項限定為 BoolOp 樣式，不會誤擋這些地方。
- **沒有查證的部分**（沒有 Bash，全部是讀碼與推論）：
  - Python `date.fromisoformat` 的可接受格式依版本不同；改用 round-trip 比對來收斂，由 P4 實測。
  - SQLite `date(x) IS x` 對 roster 壞值的排除效果與字典序 MAX 的行為，由 W10 實測。
  - `playbook_roster_log.taipei_date` 在 N-207 v2／v3 的實際來源沒有找到規格文字，所以寫成前提，不符時回 TA。
  - 既有一般失敗分支的實際名稱，由 dev-lead 在 v3 指認。
- 沒有指定任何套件版本。沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案。

## 四、下一步

1. **qa-reviewer**：依第二段 F 逐條核對 RC-75 required-1～4、RC-76、RC-79 的併入，核對結果寫入核對紀錄。
2. **tech-writer**：qa 核對通過後，把第二段 A 取代 ADR-0043 現行 D7 標題與第 1～3 點，套用 B 的連動修訂，把 C 附在文末。
   - 檔頭寫「風控 2026-11-10 確認（RC-75～RC-80）」，並填入 qa 核對的日期與檔名。
   - D3 第 7 點、D7 第 4～6 點不得改動。
3. **dev-lead**：v3 依 A 與 D 實作：
   - 只保留一個解析函式，`high_volatility_marked` 不得出現；
   - 實作 W8 的拒絕分支，並指認既有一般失敗分支的名稱；
   - 實作 R 的 SQL；
   - 確認 `taipei_date` 的來源；
   - 舊 W-25f 字面不得進程式。
4. **creative-lead**：
   - W-25 備註換成 E 的 W25f-2′；
   - 依 RC-77 擬 W-25f 第三子句，或提議刪除，附自查表（含 L3、L4、L8、L11、L12、E14、多次變更）送風控；
   - 擬 D7 第 3 點 (a′) 的專用拒絕字面送風控；
   - W-27 備註依 RC-79 更新。
5. **coordinator**：把 H-1～H-4 與 L6、L10、L11 例子放進 CEO 決策包，連同 D7 拆單 (A)／(B)（RC-82）、RC-73 的新單是否開立。
6. **tech-architect**（我）：另案設計 H-3 的修復路徑，與 AC-95「取消」的移除方式一起送風控。

相關檔案：
- /home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md（D4 :225-250、D7 :314-331、D9 :373-385、Consequences :407-459、待決 :461-474）
- /home/user/AICompany/work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-ADR0044定稿與ADR0043D7修訂-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-D7拆單評估與RC63補充-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-N207規格v2補遺修訂一-tech-architect.md（N207-C21 :159-170、T30 :172-182）
- /home/user/AICompany/work/stock-desk-N207字面草稿-creative-lead.md（W-25f :384、W-27 備註 :252）

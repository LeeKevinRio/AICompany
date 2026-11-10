# ADR-0043 D7 修訂定稿 v2 全文（含 H2-修正）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

v2 全文整合完成，A～D 四塊可以直接貼上。另外附 E 塊（W25f-2′），是給 creative-lead 的，不貼進 ADR。

- **替換 1～14 都已套用**。其中三項有特別處理：
  - 替換 4（H-2 句末補寫）先套用，接著依 CEO #131 跟著整個 H-2 一起刪除，所以 ADR 裡不會留下這段文字。
  - 替換 9 的「理由」那一行沒有放進 ADR。
  - 替換 10、11 分別在 L3、L8 兩列各改一處。
- **CEO #131（H2-修正）的條件式替換都已套用**：H-2 刪除、H-3 改寫。
  - 第二段 C 只在「代價 3」用敘述交代 `high_volatility_value_valid` 和單一性檢查要加的內容，沒有提供可以直接貼的條文。這部分條文是我補寫的。
- **qa 的三個 low 項都已處理**：
  - 替換 6 句末補上 (B) 分支；
  - `_read_roster_max_date` 已同步進 engine 名稱檢查、C-D7-6 和 P3 負例；
  - :336 那句改寫成 H-3 的事實句，不刪除，因為 creative-lead 需要知道「壞值時不顯示任何標籤」。
- **測試表依 #131 改了六列**：E18、L12、W11、W8、P3、P4。
- **待決 → CEO 改為「已裁示 #128、#130、#131、#132」**。
- **#132 的連動**：H-1、H-3、H-4 句末改為「CEO #132 接受」。這幾處是替換清單沒有涵蓋的增補，都在變更對照表（第二段 F）裡標成「TA 增補」，請 qa-reviewer 逐項核對。
- **RC-86-3 的單點重審處**：新寫法在 D7 第 2 點有兩處，用 ①② 標示，新舊對照放在第二段 G。
- **沒有動到的部分**：D3 第 7 點、D7 第 4～6 點原文。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 評估摘要
- **採用**：完全依照第二段 C 的條件式替換，把「代價 3」寫成可以檢查的條文。單一性檢查維持 7 項，所以 P3、C-D7-1 的「1～7 項」不用改。
- **否決**：
  - 刪除 :336。因為會失去「壞值時不顯示標籤」這個事實。
  - 在第 3 項加上「`type(N) is int` 運算元總數恰為 2」。因為第 5、6 項已經封住原始值的讀取，第二份驗證式拿不到原始輸入，再加這條是過度設計。

| 判斷點 | 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| :336 殘留句 | **改寫為 H-3 的事實句（採）** | 讓 creative-lead 知道壞值時沒有任何標籤 | 多一句 | 低 |
| | 刪除 | 字最少 | 少一個事實，字面擬稿時可能誤判 | 低 |
| 第 3 項的驗證式 | **加一個樣式計數，恰 1 個（採，依 C 代價 3）** | 和現行第 3 項同一型式 | 等價的變體（例如 `0 <= raw <= 1`）不在第 3 項，要靠第 5、6 項封住 | 低 |
| | 再加運算元總數恰 2 | 較嚴 | 檢查器較複雜，和第 5、6 項重複 | 低 |

#### A. D7 標題與第 1～3 點（整段取代 ADR-0043 現行的 D7 標題與第 1～3 點；第 4～6 點原文不改）

````markdown
### D7：高波動標記的接線與生效（併入 N-204；第 1～3 點 2026-11-10 依風控 RC-56（O-2）修訂，風控 2026-11-10 確認（RC-75～RC-80），RC-75、RC-76、RC-79 的條件已併入，由 qa-reviewer 逐條核對；W-25f 第三子句刪除，字面依風控 RC-84 定稿，見第 2 點；歷程壞 value 依 CEO #131（H2-修正）整檔退回，該處改寫待風控單點重審（RC-86-3），見第 2 點）

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
   - **解析**（風控 RC-63；RC-75 required-1；RC-56 驗收標準 2；CEO #131）：
     - **`parse_high_volatility_flag(raw: object) -> int`**：本體恰為 `return 1 if type(raw) is int and raw == 1 else 0`。
       - 只有 integer 1 回傳 1；其他值一律回傳 0，包括 2、-1、`'x'`、0.5、None、bool（`type(True)` 是 bool，不是 int）。
       - 適用於基準值 B，也適用於每一筆歷程列的 value（歷程值須先通過 `high_volatility_value_valid`，否則依 `_read_high_volatility` 整檔退回）。ADR 或規格的任何版本若保留 `high_volatility_prev` 欄位，該欄位也照這條規則解析。
       - 回傳 int、不回傳 bool 的理由：E、T 的 base 與 value 是 int；而且回傳 bool 時，結果若被再解析一次，`type(True) is int` 為假，會得到 0。回傳 int 時，`parse(parse(x)) == parse(x)`。
       - **N-207 規格 N207-C21 原定的 `high_volatility_marked(raw) -> bool` 撤回**，N207-C21 改為引用本函式。app/ 內不得出現 `high_volatility_marked` 這個名稱。
     - **`high_volatility_value_valid(raw: object) -> bool`**（CEO #131，H2-修正）：本體恰為 `return type(raw) is int and raw in (0, 1)`。
       - 只有 integer 0 與 1 回傳 True；2、-1、`'x'`、0.5、None、bool、`'1'` 都回傳 False。
       - 只用於歷程列的 value，不用於基準值 B：B 是壞值時解析為 0，不可能讓 E(today_tpe) = 1，所以不會產生不實的 W-25f（E16 不變）。
     - **`parse_high_volatility_changed_on(raw: object) -> date | None`**：`type(raw) is str`、`date.fromisoformat(raw)` 不拋例外，而且 `.isoformat() == raw` 時，回傳該日期；否則回傳 None。拒絕範圍與第 1 點的 CHECK 意圖一致：不存在的日期、斜線格式、前後空白、非 TEXT 都拒絕。
   - **單一讀取 helper** `_read_high_volatility(conn, symbols) -> dict[str, HighVolRead]`（接收 conn，與 D4 第 3 點 (a) 的 helper 同一型式）：
     - `HighVolRead(NamedTuple)`：`base: int`、`history: tuple[HighVolChange, ...]`、`history_readable: bool`。
     - 讀取該檔 B 與全部歷程列（依 id 升冪）。B 經 `parse_high_volatility_flag`；每列 value 先經 `high_volatility_value_valid`，通過後經 `parse_high_volatility_flag`；changed_on 經 `parse_high_volatility_changed_on`。
     - 任一列的 changed_on 解析為 None，或任一列 value 經 `high_volatility_value_valid` 判為 False 時：`history_readable = False`、`base = 0`、`history = ()`。所以對所有 `on`，T = 0、E = 0。
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
     - **W-25f：第三子句刪除；W-25f 字面依風控 RC-84 定稿**（逐字只放在 `wording.py`）。
       - 舊第三子句「今日仍用高波動門檻」，以及未採用的案 (i)「不受這次取消影響」，都不得進入程式或畫面（C-D7-5）。
       - 原本的定稿暫停（RC-58、RC-77），在以下兩件事都完成後解除（RC-87）：
         - 本修訂與連動修訂落進本 ADR，並經 qa-reviewer 核對；
         - C-D7-5 成立。
       - CEO #128 採方案 (A)，所以這是 N-207 的合併閘；若 CEO 依 #128 轉換條件改走 (B)，改為 D7 單的合併閘。
   - **讀取**：`symbol_states(on)` 用一個連線、一個讀取交易（`BEGIN`…`COMMIT`），經 `_read_high_volatility` 讀出 `playbook_symbols` 與 `playbook_high_volatility_log`，對每檔呼叫上述函式。
   - **engine 名稱檢查**（補 I-4 的可檢查形式，不改 I-4）：`engine.py` 不出現 `playbook_high_volatility_log`、`HighVolChange`、`HighVolRead`、`effective_high_volatility`、`target_high_volatility`、`parse_high_volatility_flag`、`high_volatility_value_valid`、`parse_high_volatility_changed_on`、`_read_high_volatility`、`_read_roster_max_date`。engine 照舊只透過 `build_market_snapshot(high_volatility=…)` 拿到值（第 4 點）。
   - **單一性檢查**（AST，全部 BLOCKING；RC-75 required-1；CEO #131）：
     1. app/ 內名為 `parse_high_volatility_flag`、`high_volatility_value_valid`、`parse_high_volatility_changed_on`、`_read_high_volatility`、`_read_roster_max_date` 的函式定義各恰 1 個，都在 `app/playbook/store.py`。
     2. 識別名 `high_volatility_marked` 在 app/ 內的出現次數為 0，包括函式定義、Name、Attribute、字串常數。
     3. **判定式恰出現一次**：
        - app/ 內同時含有 `type(N) is int` 與 `N == 1`（同一個 Name N）的 `BoolOp(And)` 節點恰 1 個，而且位於 `parse_high_volatility_flag` 本體內；
        - app/ 內同時含有 `type(N) is int` 與 `N in (0, 1)`（同一個 Name N）的 `BoolOp(And)` 節點恰 1 個，而且位於 `high_volatility_value_valid` 本體內。
     4. **本體形狀**：
        - `parse_high_volatility_flag` 本體恰為一條 `Return`，值為 `IfExp`：test 是第 3 項第一個 BoolOp，body 為 `Constant(1)`，orelse 為 `Constant(0)`。
        - `high_volatility_value_valid` 本體恰為一條 `Return`，值為第 3 項第二個 BoolOp。
        - 兩個本體都不得出現 `bool(`、`int(`、`!= 0`、`> 0`，也不得以 raw 做真值判斷。
     5. **呼叫點封閉**：
        - `parse_high_volatility_flag`、`high_volatility_value_valid` 的呼叫，以及 `HighVolChange(...)` 的建構，只出現在 `_read_high_volatility` 本體內。
        - `parse_high_volatility_changed_on` 的呼叫，只出現在 `_read_high_volatility` 與 `_read_roster_max_date` 兩個本體內。
        - `_read_roster_max_date(conn) -> date | None` 本體恰好執行一句 SQL：`SELECT MAX(taipei_date) FROM playbook_roster_log WHERE date(taipei_date) IS taipei_date`，結果只交給 `parse_high_volatility_changed_on`。它的呼叫者只能是第 3 點的寫入函式（預覽與確認）。
        - 兩個 helper 本體內的 `Compare` 節點，只能是 `… is None` 或 `… is not None`。
     6. **原始值讀取封閉**：app/ 內含子字串 `high_volatility` 的非 docstring 字串常數（不分大小寫；f-string 每段各自計算），只能出現在 `store.py` 的 `_SCHEMA`（DDL 與 trigger）、`_read_high_volatility`（SELECT），以及第 3 點寫入函式的那一句 INSERT。
     7. **負例**：下列原始碼字串餵給檢查器，都必須判為違規：
        - 含第二份判定式（第 3 項任一樣式）或第二個解析函式；
        - 含第二個 `high_volatility_value_valid` 定義，或其本體形狀不符第 4 項；
        - 在 `_read_high_volatility` 之外呼叫 `parse_high_volatility_flag` 或 `high_volatility_value_valid`；
        - 在兩個 helper 之外呼叫 `parse_high_volatility_changed_on`；
        - 在第 3 點寫入函式之外呼叫 `_read_roster_max_date`。
   - 測試見附錄 D7-T（E、L、P3、P4）。

3. **寫入：高波動標記操作**（D4 的兩步流程與鎖內流程）
   - (a) **鎖內讀取**：經 `_read_high_volatility` 讀該檔的 `HighVolRead`；另經 `_read_roster_max_date(conn)` 讀 R（SQL 與解析依第 2 點單一性檢查第 5 項）。回傳 None 時，R 不存在。
   - (a′) **歷程無法解析時拒絕**（風控 RC-75 required-2；壞 value 依 CEO #131 同此）：
     - `history_readable` 為 False 時（壞 `changed_on` 或壞 value，第 2 點），本次操作一律拒絕、零寫入。標記與取消都一樣，判斷排在 (c) 冪等判定之前。
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

#### B. 連動段落（和 A 同一次落檔；D3 第 7 點 J-1～J-10、I-1～I-5 一字不動）

- **檔頭變更紀錄**加一行：「2026-11-10 依風控 RC-56（O-2）修訂 D7 第 1～3 點，併入風控 RC-75～RC-79 的條件；再依風控 RC-84、RC-87 與 CEO #128、#131、#132 同步（W-25f 第三子句刪除；H-2 依 #131 由 H-3 吸收，該處待風控單點重審 RC-86-3）；連動修訂 D4 第 3、4 點、D9 第 1 點、Consequences『壞處與代價』『被約束』、待決；新增附錄 D7-T（風控 2026-11-10 確認，RC-75～RC-80）」。
- **決策者 → risk-compliance-officer**，句末加：「；D7 第 1～3 點修訂：風控 2026-11-10 確認（RC-75～RC-80，見 work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md），W-25f 與 H-2 裁示見 work/reviews/2026-11-10-W25f定稿與H2判定-風控.md（RC-84～RC-88），required 併入後不回送；CEO #131 改寫的歷程壞 value 規則待風控單點重審（RC-86-3）；qa-reviewer 核對：work/reviews/2026-11-10-D7與ADR0044併入核對-qa-reviewer.md、work/reviews/2026-11-10-D7替換條文核對-qa-reviewer.md、{v2 全文核對的日期與檔名，tech-writer 落檔時填入}」。
- **決策者 → CEO**，句末加：「；#128（D7 不拆單，方案 (A)，附轉換條件）、#130（N-211）、#131（H-2 採 H2-修正）、#132（H-1、H-3、H-4 接受）於 2026-11-10 裁定」。
- **來源簡稱**：
  - [決策包] 括號改為「（#119～#125、#128～#132 與「#123 知悉事項」列）」；
  - 加入 [風控-D7]：`reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md`（RC-75～RC-83）；
  - 加入 [風控-W25f]：`reviews/2026-11-10-W25f定稿與H2判定-風控.md`（RC-84～RC-88）；
  - 加入 [TA-D7]：`reviews/2026-11-10-ADR0044定稿與ADR0043D7修訂-tech-architect.md` 交付 2、`reviews/2026-11-10-D7拆單評估與RC63補充-tech-architect.md` 2-F～2-H、`reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md`、`reviews/2026-11-10-D7定稿替換條文-tech-architect.md`。
- **D4 第 3 點 (a)**，句末加：「；高波動標記操作另經 `_read_high_volatility` 讀該檔的基準值與 `playbook_high_volatility_log` 全部列，並經 `_read_roster_max_date` 讀 `playbook_roster_log` 有效 `taipei_date` 的最大值（D7 第 3 點 (a)、(d)）」。
- **D4 第 3 點 (d)** 改為：「(d) 寫入只限四處：`playbook_symbols` 的自有欄位 upsert、`playbook_batches` 的新輪 INSERT、`playbook_high_volatility_log` 的 INSERT（只限高波動標記操作，D7 第 3 點）、`playbook_roster_log` 的 INSERT；」
- **D4 第 4 點**：「三張表都逐列不變」改為「四張表（含 `playbook_high_volatility_log`）都逐列不變」。
- **D9 第 1 點**：
  - `taipei_date TEXT NOT NULL` 一行，句末加：「（D4 第 3 點 (b) 同一次時鐘讀取換算的 Asia/Taipei 日期；D7 第 3 點 (d) 以此為前提）」；
  - `detail_json` 的括號內，句末加：「、高波動標記的歷程列 id、value、changed_on，以及 today_tpe 與 D7 第 3 點 (d) 的參考日 L、R」。
- **Consequences「壞處與代價」**加下列各點（沒有 H-2）：
  - 「**高波動改為只能新增的歷程表**（D7 第 1～3 點）：多一張表與兩個 trigger。名單頁標籤依台北日期判定，今日頁依資料日判定；資料落後期間內有多次變更時，兩者的落差有兩種方向：(i) **L6**：標籤寫『尚未適用』，今日頁用 20%，方向較寬，由 W-27 第二句與 W-22 第二行揭露，不新增顯示條件（風控 RC-78）；(ii) **L4**（另見 L11，標記從未適用）：W-25f 第三子句不實，方向較嚴；風控 RC-77 裁示改擬（F2）；RC-84 定稿為刪除第三子句，此落差改由 W-27 第二句揭露。」
  - 「**H-1 時鐘落後，偵測不到**（風控 RC-75 required-3；比照 ADR-0044 R-c）：`today_tpe` 落後真實台北日期，而 L 與 R 都不晚於 `today_tpe` 時，標記的 `changed_on` 會早於真實日期。資料日落在 (`today_tpe`, 真實日期] 的評估（包括時鐘校正之後的評估）改用 20%，違反 FR-30『變更當日仍用舊門檻』，**方向較寬，系統偵測不到**。例：真實日期 11-12、時鐘顯示 11-10、最後一次名單寫入也在落後之後 → `changed_on` = 11-10，資料日 11-11、11-12 的評估用 20%；照 FR-30 應從 11-13 起。R（採用 RC-75 suggested）把偵測範圍擴大到任何名單寫入記錄過的較晚日期，但關不掉這項殘留。取消不受影響：提早適用的方向是較嚴。列為殘留，CEO #132 接受。」
  - 「**H-3 歷程有壞 `changed_on` 或壞 value 時，該檔永久退回 15%**（2-F、RC-75 required-2；比照 RC-49 條件 4；CEO #131 以此吸收原 H-2，H-2 編號保留不重用）：這種列只可能來自 app 外的寫入，而且歷程表擋 DELETE，壞列會永久存在。結果是該檔對所有資料日 E = 0、不顯示高波動標籤、標記與取消操作一律拒絕，方向較嚴；名單頁沒有任何提示，使用者也沒有 app 內的復原路徑（重新標記同樣被拒絕）。app 外的壞列會回溯改變較早資料日的生效值（例：E18 寫入前 E(11-10) = 1，寫入後為 0）。修復路徑另案設計並送風控，不得手動改 DB。CEO #132 接受；修復路徑等真的發生時再另案處理。」
  - 「**H-4 較寬方向的標籤落差**：L6（見上）與 L10（O-1，取消側；風控 RC-55 已裁示揭露。整頁沒有任何標籤時，W-27 不顯示，只剩 W-22 第二行）。`/today` 加事實欄位的新單不列為 N-207 的上線條件（風控 RC-73、RC-78）；app 有第二個使用者時，這張新單轉為 required。CEO #132 接受；這張新單已由 CEO #130 開立為 N-211，排在 D7 之後。」
- **Consequences「被約束」**：
  - 第一點改為：「名單路徑只能寫 `playbook_symbols` 的自有欄位、`playbook_batches` 的新輪 INSERT、`playbook_high_volatility_log` 的 INSERT、`playbook_roster_log` 的 INSERT；」
  - 新增一點：「高波動的原始值只經 D7 第 2 點的 `_read_high_volatility`、`high_volatility_value_valid` 與兩個解析函式讀取；`playbook_high_volatility_log` 只能 INSERT。」
- **待決**新增：
  - CEO：已裁示 #128、#130、#131、#132。
    - #128：採方案 (A)，不拆單。轉換條件兩項：(1) P-4a 大於 0，且 CEO 傾向取消標記；(2) 其他前置都已就緒，只剩 D7 未完成確認。任一成立時，CEO 可以改走 (B)，並須符合風控 RC-82 的前提。
    - #130：開立 RC-73 的新單 N-211，排在 D7 之後，不擋 N-207。
    - #131：H-2 採 H2-修正，由 H-3 吸收。
    - #132：H-1、H-3、H-4 接受。
  - 風控：
    - W-25f 第三子句：**已結**（RC-84，刪除第三子句，W-25f 字面定稿）；
    - D7 第 3 點 (a′) 專用拒絕字面的定稿（RC-75 required-2；涵蓋 CEO #131 的壞 value 情形）；
    - **RC-86-3 單點重審**：CEO #131 改寫了 RC-75 已確認的「value 無法解析時逐列回 0」，歷程值改為整檔退回（D7 第 2 點「解析」與 `_read_high_volatility`）。重審範圍只限這一處，以及附錄 E18、L12、W8、W11、P4。
  - creative-lead：D7 第 3 點 (a′) 專用拒絕字面的擬稿；W-27 備註依 RC-79、RC-87 更新。
  - tech-architect：H-3 的修復路徑依 CEO #132，等真的發生時再另案設計並送風控；D7 第 6 點「取消」路徑（AC-95）仍由 TA 另行設計並送風控，不再和 H-3 綁在一起。

#### C. 附錄 D7-T（放在 ADR-0043 文末）

````markdown
## 附錄 D7-T：D7 參數化測試表（RC-56 驗收標準 3；風控 RC-76；CEO #131 修改 E18、L12、W8、W11、P3、P4）

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
| E18 | 最新一列 value 是壞值（PRAGMA） | 0 | 11-09:1, 11-10:`'x'` | 11-10／11-11 | 0／0；T = 0 | `history_readable` = False；壞 value 整檔退回，與 E15 同型（H-3，CEO #131）。寫入前 E(11-10) = 1，app 外壞列回溯改變較早資料日；標籤見 L12 |

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
| W8 | 歷程有壞 `changed_on`（PRAGMA，同 E15），或有壞 value（PRAGMA；`'x'`、2、0.5 參數化，CEO #131），分別做標記與取消 | 預覽與確認都拒絕；四張表逐列不變；不寫稽核列；回應走既有的一般失敗分支，不是任何 `ROSTER_RESULT_*`；回應與渲染不含「已取消」「已標記」；store 的內部原因碼可以斷言 |
| W8b | 預覽通過後才種入壞列（W8 任一種），再確認 | 鎖內拒絕，期望同 W8 |
| W9a | roster 最大有效台北日 R = 11-12；B = 0；沒有歷程；today_tpe = 11-10；標記 | `changed_on` = 11-12（RC-75 suggested） |
| W9b | 同上，但 B = 1；取消 | `changed_on` = 11-10 |
| W10 | roster 有 `'2026-11-09'` 與 `'2026/11/20'` 兩列（直接 SQL）；沒有歷程；today_tpe = 11-10；標記 | `changed_on` = 11-10；壞列被排除，不拒絕。少了 WHERE 時，字典序 MAX 會取到 `'2026/11/20'`，本列因此失敗 |
| W11 | 最新一列 value 是壞值（同 E18，`history_readable` = False）；today_tpe = 11-10；分別做標記與取消 | 標記與取消都拒絕，期望同 W8；取消不得回冪等結果（C-D7-2） |
| W12 | 任一成功寫入 | 稽核列 `detail_json` 含歷程列 id、value、changed_on、today_tpe、L、R（不存在時為 null） |

性質與結構（P）：

- **P1（驗收標準 1，窮舉）**：
  - 範圍：日期取 11-09～11-16 共 8 天；B ∈ {0, 1}；R ∈ {不存在} ∪ 8 天；歷程長度 0～3，依第 3 點規則逐筆寫入，含時鐘倒退；再寫入一筆。
  - 斷言：
    - 對所有 `on` 不晚於新列 `changed_on` 的日期，寫入前後的 E(on) 相同；
    - 新列 `changed_on` 不早於 today_tpe。
  - 以 itertools 窮舉即可，不需要額外套件。
- **P2**：名單頁與評估只呼叫同一組函式（grep：store 與 API 內，`effective_high_volatility` 之外沒有第二份判定）。
- **P3（RC-75 required-1；CEO #131）**：D7 第 2 點「單一性檢查」1～7 項，含 `_read_roster_max_date` 與 `high_volatility_value_valid` 的定義、樣式、本體形狀、呼叫點，以及第 7 項所列全部負例。
- **P4（解析）**：
  - 對 0、1、2、-1、`'x'`、0.5、None、True、False、`'1'`，`parse_high_volatility_flag` 只有 1 回傳 1；回傳值的 `type` 都是 int；`parse(parse(x)) == parse(x)`。
  - `high_volatility_value_valid`：對 0、1 回傳 True；對 2、-1、`'x'`、0.5、None、True、False、`'1'` 回傳 False；回傳值的 `type` 都是 bool（CEO #131）。
  - `parse_high_volatility_changed_on`：`'2026-11-10'` 回傳日期；`'2026-13-01'`、`'2026/11/10'`、`'2026-11-10 '`、`'20261110'`、20261110、None 都回傳 None。
  - 同一批字串對第 1 點 CHECK 的接受與拒絕要一致，以檔案 DB 實測。

標籤（L，`on = today_tpe`）：

| # | 歷程 | today_tpe | T | E | 標籤 | 今日頁資料日 → 實際門檻 | 備註 |
|---|---|---|---|---|---|---|---|
| L1 | E3 | 11-10 | 1 | 0 | W-25e，M/D = 11/11 | 11-09 或 11-10 → 15% | 一致 |
| L2 | E3 | 11-11 | 1 | 1 | W-25d | 11-10 → 15% | O-1 型落差，方向保守，與舊設計相同 |
| L3 | E4 | 11-10 | 0 | 1 | W-25f，M/D = 11/11 | 11-09 或 11-10 → 20% | 第三子句已刪（RC-84） |
| L4 | E6（O-2 原例取消後） | 11-10 | 0 | 1 | W-25f，M/D = 11/11 | 11-10 → 20%；11-09 → 15% | 舊第三子句在 11-09 不實，實際門檻較字面嚴（RC-77 採 F2） |
| L5 | E9 | 11-10 | 0 | 0 | 不顯示 | 15% | W25f-1′ 的禁止條款：不得以「T=0 且有歷程」判定 |
| L6 | E12 | 11-11 | 1 | 0 | W-25e，M/D = 11/12 | 11-10 → 20%；11-11 → 15% | 較寬落差：標籤寫「尚未適用」，今日頁（資料日 11-10）用 20%（RC-78、H-4） |
| L7 | E7 | 11-15（週日） | 1 | 1 | W-25d | 11-13 → 15% | O-1 型落差，方向保守，與舊設計相同 |
| L8 | E8 | 11-15（週日） | 0 | 1 | W-25f，M/D = 11/16 | 11-13 → 20% | 第三子句已刪（RC-84） |
| L9 | 任一列帶 W-25d／e／f | — | — | — | W-27 顯示 | — | 條件不變 |
| L10 | B = 1；11-10:0 | 11-11 | 0 | 0 | 不顯示 | 11-10 → 20% | O-1 取消側的較寬落差（RC-55 已裁示）；整頁沒有其他標籤時只剩 W-22 第二行（H-4） |
| L11 | B = 0；11-13:1（週五）, 11-15:0（週日） | 11-15（週日） | 0 | 1 | W-25f，M/D = 11/16 | 資料日最晚 11-13 → E(11-13) = 0 → 15%；11-16 起取消已適用 | 標記從未適用；舊第三子句在任何資料日都不成立（RC-77） |
| L12 | E18 | 11-10 | 0 | 0 | 不顯示 | 15% | 壞 value 整檔退回，與 L13 同型；不再出現不實的 W-25f（H-3，CEO #131） |
| L13 | E15 | 11-10 | 0 | 0 | 不顯示 | 15% | 壞 `changed_on` 整檔退回（H-3） |
````

#### D. 對實作的約束（交 dev-lead；qa-reviewer 可以逐條檢查。這是 TA 規格，不是 ADR 內文）

**N207-C21 替換全文**（取代修一檔「修一-4」的 N207-C21；依第二段 C 的判定，H2-修正不影響這一條，原文照用）：

> **N207-C21 `high_volatility` 的執行期解析（BLOCKING）**
> - **單一解析函式**：依 ADR-0043 D7 第 2 點，使用 `app/playbook/store.py` 的 `parse_high_volatility_flag(raw: object) -> int`，本體與 AST 檢查依該點「單一性檢查」1～7 項。原定的 `high_volatility_marked` 撤回，app/ 內出現次數為 0。
> - **解析時點**：`playbook_symbols.high_volatility` 與歷程列的原始值，只在 `_read_high_volatility` 內經解析函式轉為 0 或 1。`SymbolState`（pydantic）不得收到原始值，只能收到解析函式與 E、T 的輸出；欄位型別由 v3 定。
>   - 理由：pydantic 的 bool 遇到 2、'x'、0.5 會 raise，整頁會 500。
>   - `build_market_snapshot(high_volatility=…)`（`models.py:175` 為 bool）由 E 轉入，不得再讀或再解析原始值。
> - **共用**：engine 輸入（N207-C15）、W-25d～f 標籤、W-27 顯示旗標，三者都只讀 store 的同一份結果。讀 `high_volatility` 的 SQL 依 D7 第 2 點第 6 項封閉。
> - **不採 raise**：評估與名單頁讀取讀到異常值不 raise。部署前的異常值由盤點 P-4c 與 STOP-4 處理；寫入路徑依 D7 第 3 點 (a′) 拒絕。

**N207-T30**：最後一點「涉及 `high_volatility_prev` 的情境，依 D7 修訂後補上」改為「歷程表情境依 ADR-0043 附錄 D7-T：E15～E18、W8～W11。種入 B 的 fixture 與 E16 共用」。其餘不變。

**其他約束**（C-D7-1～C-D7-7）：
- **C-D7-1**：D7 第 2 點「單一性檢查」1～7 項都要有測試（P3），而且都是 BLOCKING。
- **C-D7-2**：(a′) 排在 (c) 之前。實作 W8、W11 時，歷程同時有壞 `changed_on` 或壞 value、而且新值等於 T，也必須拒絕，不得回冪等的結果。
- **C-D7-3**：W8 的回應不得新增使用者可見字面。前端與 `wording.py` 對這個原因碼的 grep，計數必須為 0，直到風控定稿專用字面為止。
- **C-D7-4**：R 的 SQL 必須帶 `WHERE date(taipei_date) IS taipei_date`，以 W10 釘住；`taipei_date` 的寫入來源以 D4 第 3 點 (b) 的同一次時鐘讀取為準。
- **C-D7-5**：「今日仍用高波動門檻」與「不受這次取消影響」在 app/ 與前端的 grep 計數都為 0（RC-77、RC-87）。W-25f 只實作 RC-84 全文。
- **C-D7-6**：`engine.py` 的名稱檢查擴到 D7 第 2 點所列 10 個名稱。
- **C-D7-7**（CEO #131）：`high_volatility_value_valid` 只用於歷程列的 value，不用於 B。歷程任一列判為 False 時整檔退回，`parse_high_volatility_flag` 只處理基準值 B 和已經通過驗證的歷程值。這項由 E16（B 是壞值時不整檔退回）、E18、L12、W8、W11 釘住。

#### E. W25f-2′ 替換句（交 creative-lead，不貼進 ADR；取代草稿 W-25 備註的 W25f-2′，W25f-1′、3′ 不變）

- **W25f-2′（參考日與真偽）**：
  - 參考日用 `today_tpe`，來源與 D1 第 4 點、D8 第 6 點相同。一般情形下，只會在 `today_tpe` 等於最新一列 `changed_on` 的當天顯示。
  - **舊第三子句「今日仍用高波動門檻」不恆真**：今日頁的資料日 d 早於 `today_tpe`，而且該檔另有一列（不是最新那一列）的 `changed_on` 落在 [d, `today_tpe`) 時，今日頁可能用一般門檻。
    - 例一（L4，O-2 原例）：週二早上，資料日仍是週一，實際用 15%。
    - 例二（L11）：週五 11-13 標記、週日 11-15 取消，`today_tpe` = 11-15 時顯示 W-25f（M/D = 11/16）。但可能的資料日最晚是 11-13，E(11-13) = 0；從 11-16 起取消已經適用。這個標記從來沒有適用過。
    - 這種情形下，**實際門檻可能較字面所示嚴**。它一定落在「資料日早於台北今日」的範圍內，W-27 第二句已有揭露。
  - **真偽：第三子句已刪（RC-84），沒有需要核對的子句。** 舊第三子句與案 (i)「不受這次取消影響」都不得進入程式或畫面。
  - **壞值**（ADR-0043 H-3，CEO #131）：歷程列有 app 外寫入的壞 value 或壞 `changed_on` 時，該檔整檔退回 15%，不顯示任何高波動標籤，所以不會出現 W-25f（L12、L13）。

#### F. 變更對照表（以定稿檔 `work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md` 為基底；「TA 增補」是替換清單沒有涵蓋、由我補寫的部分，請 qa 逐項核對）

| # | 位置 | 改動 | 依據 |
|---|---|---|---|
| 1 | A 標題括號 | 「W-25f 第三子句另有閘」改為「刪除，字面依 RC-84 定稿」 | 替換 5 |
| 2 | A 標題括號 | 句末加 #131 與 RC-86-3 待重審 | TA 增補（#131；標題寫「風控確認」，要揭示尚未確認的那一處） |
| 3 | A 第 2 點「解析」標頭 | 加「CEO #131」 | TA 增補（#131） |
| 4 | A 第 2 點 parse_flag「也適用於歷程 value」 | 句末加括號 **【重審點 ①】** | 第二段 C 條件式 |
| 5 | A 第 2 點新增 `high_volatility_value_valid` 子彈 | 本體與適用範圍 | 第二段 C 代價 3、做法；TA 增補（寫成條文） |
| 6 | A 第 2 點 `_read_high_volatility`「每列 value 先經 valid」 | 讀取順序 | TA 增補（和 #4 保持一致） |
| 7 | A 第 2 點 `_read_high_volatility`「任一列…時」 | 加「或 value 經 valid 判為 False」 **【重審點 ②】** | 第二段 C 條件式 |
| 8 | A 第 2 點 W-25f 子彈 | 整段換新 | 替換 6 |
| 9 | A 第 2 點 W-25f 子彈末句 | 加 (B) 分支 | qa low 1 |
| 10 | A 第 2 點 engine 名稱檢查 | 加入 `_read_roster_max_date` | qa low 2 |
| 11 | 同上 | 加入 `high_volatility_value_valid` | TA 增補（#131） |
| 12 | A 單一性檢查第 1 項 | 加入 `_read_roster_max_date` | 替換 1 |
| 13 | 同上 | 加入 `high_volatility_value_valid` | 第二段 C 代價 3 |
| 14 | A 單一性檢查第 3、4 項 | 加驗證式樣式和本體形狀 | 第二段 C 代價 3 |
| 15 | A 單一性檢查第 5 項 | 整段換新 | 替換 2 |
| 16 | 同上 | 加 valid 的呼叫點限制 | 第二段 C 代價 3 |
| 17 | A 單一性檢查第 7 項 | 加「在兩個 helper 之外呼叫 `parse_high_volatility_changed_on`」 | qa low 2 |
| 18 | 同上 | 加 valid 的負例 | 第二段 C 的 P3 列 |
| 19 | 同上 | 加 `_read_roster_max_date` 呼叫者的負例 | TA 增補（對應第 5 項） |
| 20 | A 第 3 點 (a) | 改用 `_read_roster_max_date` | 替換 3 |
| 21 | A 第 3 點 (a′) 標頭與第一子彈 | 註明壞 value 同此 | TA 增補（#131） |
| 22 | B 檔頭、決策者、來源簡稱 | 加 RC-84～88、#128～#132、qa 兩份核對檔、v2 核對檔的占位 | TA 增補 |
| 23 | B D4 第 3 點 (a) | 加「經 `_read_roster_max_date`」 | TA 增補（M-1 的連動） |
| 24 | B「壞處與代價」第一點 (ii) | 句末加 RC-84 那句 | 替換 7 |
| 25 | B H-1 句末 | 「交 CEO 接受或修正」改為「CEO #132 接受」 | #132 |
| 26 | B H-2 | 先套替換 4，再整點刪除 | 替換 4 → #131、第二段 C |
| 27 | B H-3 | 標題改寫，句末加回溯改變較早資料日 | 第二段 C |
| 28 | B H-3 | 加「無提示、無 app 內復原路徑」、E18 例子、#132 | TA 增補（第二段 C 代價 1、#132） |
| 29 | B H-4 句末 | 加 #132 接受、N-211 | #132、#130 |
| 30 | B「被約束」新增點 | 加 `high_volatility_value_valid` | TA 增補（#131） |
| 31 | B 待決 → CEO | 改為「已裁示 #128、#130、#131、#132」 | 替換 14 → 任務第 4 項 |
| 32 | B 待決 → 風控 W-25f | 已結 | 替換 8 |
| 33 | B 待決 → 風控 (a′) | 涵蓋壞 value | TA 增補（#131） |
| 34 | B 待決 → 風控 | 新增 RC-86-3 單點重審 | 任務第 5 項 |
| 35 | B 待決 → creative-lead | 照新句，不含「理由」行 | 替換 9 |
| 36 | B 待決 → tech-architect | H-3 延後，AC-95 不再和 H-3 綁在一起 | #132；TA 增補 |
| 37 | C 附錄標頭 | 加 #131 修改列 | TA 增補 |
| 38 | C 的 L3、L8 備註 | 逐列各改一處 | 替換 10、11 |
| 39 | C 的 E18、L12、W8、W11、P3、P4 | 依新期望改寫 | 第二段 C 的測試表、#131 |
| 40 | C 的 W8b | 「壞列」擴到 W8 任一種 | TA 增補（和 W8 保持一致） |
| 41 | D 的 C-D7-2 | 加壞 value 與 W11 | TA 增補（#131；不改會讓 W11 取消落入冪等） |
| 42 | D 的 C-D7-5 | 換新 | 替換 13 |
| 43 | D 的 C-D7-6 | 8 個名稱改為 10 個 | qa low 2、#131 |
| 44 | D 新增 C-D7-7 | 新增 | TA 增補（#131） |
| 45 | D 的 N207-C21、T30 | 不變 | 第二段 C 判定不受影響 |
| 46 | E「真偽」 | 換新 | 替換 12 |
| 47 | E :336 殘留句 | 改寫為 H-3 的壞值句 | qa low 3、#131 |
| — | D3 第 7 點；D7 第 4～6 點 | 沒有動 | 任務限制 |

#### G. RC-86-3 單點重審處（交風控）

- **RC-75 已確認的舊寫法**：
  - 定稿 :93：parse_flag「適用於基準值 B，也適用於每一筆歷程列的 value」；
  - 定稿 :99-100：「每列 value 經 `parse_high_volatility_flag`」；「任一列的 changed_on 解析為 None 時」才整檔退回；
  - 對應風控在 RC-75 的確認句：「value 無法解析時逐列回 0」。
- **H2-修正後的新寫法**：
  - **①** D7 第 2 點「解析」：「適用於基準值 B，也適用於每一筆歷程列的 value（歷程值須先通過 `high_volatility_value_valid`，否則依 `_read_high_volatility` 整檔退回）。」
  - **②** D7 第 2 點 `_read_high_volatility`：「每列 value 先經 `high_volatility_value_valid`，通過後經 `parse_high_volatility_flag`……任一列的 changed_on 解析為 None，或任一列 value 經 `high_volatility_value_valid` 判為 False 時：`history_readable = False`、`base = 0`、`history = ()`。」
- **語意差異，請風控判斷**：
  - 「逐列回 0」改為只適用於 B。歷程值壞掉時整檔 E = 0，對所有 on 都一樣。方向不會變寬，因為 0 對應 15%，是最嚴的值。
  - 但這會回溯改變壞列寫入前已經成立的生效值（E18：E(11-10) 由 1 變成 0）。這只發生在 app 外的寫入，驗收標準 1 只約束 app 內的寫入。
  - 寫入路徑：W11 原本是「取消冪等、標記可寫入」，改為兩者都拒絕。復原路徑只剩 H-3 的另案修復。
  - 對應的測試列：E18、L12、W8、W11、P4。

### 其他部門
本次沒有參與。

## 三、驗證

- **全文讀過**：
  - 定稿檔 `/home/user/AICompany/work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md`
  - 替換條文檔 `/home/user/AICompany/work/reviews/2026-11-10-D7定稿替換條文-tech-architect.md`
  - qa 核對檔 `/home/user/AICompany/work/reviews/2026-11-10-D7替換條文核對-qa-reviewer.md`
- **部分讀過**：
  - 決策包 #128～#134：`/home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` :164-170
  - RC-75 原文：`/home/user/AICompany/work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md` :51-79
  - RC-86 與 RC-87：`/home/user/AICompany/work/reviews/2026-11-10-W25f定稿與H2判定-風控.md` :68-117
  - 第一次 qa 核對的結論與 M-1：`/home/user/AICompany/work/reviews/2026-11-10-D7與ADR0044併入核對-qa-reviewer.md`（grep）
- **ADR 現況比對**：讀了 `/home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md` 的 :1-30、:310-334、:405-475。確認 D7 第 4～6 點在 :324-331，A 沒有碰到這一段；Consequences 和待決的位置也和 B 對得上。
- **手核**：
  - H2-修正下，W-25f 的條件 T = 0 且 E = 1 在壞 value 時不成立，所以 L12 不顯示。
  - 如果 (c) 排在 (a′) 之前，W11 的取消會因為 T = 0 而落入冪等，所以 C-D7-2 一定要擴充。
  - `type(raw) is int and raw in (0, 1)` 一定回傳 bool。
  - 第 3 項的第一個樣式（`N == 1`）不會被 valid 的 BoolOp 命中，所以計數仍是 1。
- **沒有查證**：沒有執行任何 AST 檢查或測試，因為沒有 Bash；這些要等 dev-lead 實作後，由 P3、P4 實測。我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案，也沒有指定任何套件版本。

## 四、下一步

1. **qa-reviewer**：依第二段 F 核對 v2 全文，重點是標「TA 增補」的各列。把核對檔名填進 B 決策者那一行的占位。
2. **風控**：只針對第二段 G 的 ①② 和五個測試列做 RC-86-3 單點重審。
   - coordinator 原本把替換 4「顯示期間精確化」列為風控知悉事項。H-2 已依 #131 刪除，這一項不再需要告知。
3. **tech-writer**：qa 通過後落檔，順序如下：
   - 用 A 整段取代 D7 標題與第 1～3 點；
   - 套用 B；
   - 把 C 附在 ADR 文末。
   - D3 第 7 點、D7 第 4～6 點都不能動；E 和 D 不貼進 ADR。
   - 落檔要排在 W-25f 進程式之前（RC-86-2、RC-87）。
4. **dev-lead**：依 A 與 D 實作，包括 `high_volatility_value_valid`、`_read_roster_max_date`、C-D7-2 的排序，以及 C-D7-7。
   - 第二段 G 的重審通過前，壞 value 的分支不得合併。
5. **creative-lead**：W-25 備註換成 E；(a′) 拒絕字面的擬稿要涵蓋壞 value 的情形。
6. **coordinator 知悉（D7 範圍外，我沒有改）**：ADR 現行的決策者 → CEO「Q-C11 待定」、待決 → CEO 的 Q-C11 一項、Consequences R-12 的「Q-C11 須由 CEO 明示」，CEO #129 已經裁示。是否另外安排 tech-writer 同步，請 coordinator 決定。

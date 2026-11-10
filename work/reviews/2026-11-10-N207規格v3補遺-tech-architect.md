# N-207 規格 v3 補遺（13 項回覆、CEO #127～#130 定案、v3.1 差異清單）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

「N-207 規格 v3 補遺（TA 2026-11-10）」寫好了，全文在第二段，可以直接貼上，dev-lead 據此出 v3.1。

**13 項的處理**
- **依 CEO 裁示或風控 RC 結案，共 5 項**：
  - 第 1 項（RC-75 required-1 與我的 D7 修訂定稿）；
  - 第 6 項（RC-77）；
  - 第 7 項（#127）；
  - 第 12 項（確認 dev-lead 原處理）；
  - 第 13 項（RC-75～RC-83）。
- **由 TA 定案，共 8 項**：第 2、3、4、5、8、9、10、11 項。重點如下：
  - **E、T 的位置**：E、T 留在 `store.py`。store 先把 T、L、R 算好放進新型別 `HighVolFacts`；高波動操作的計畫仍由 `plan_change` 負責。roster.py 新增兩個純函式：`high_volatility_changed_on` 與 `high_volatility_label`。
  - **預覽摘要**：N207-C11 加一個窄例外。`roster_digest` 加上必填的 `hv_changed_on` 參數，理由是它是本次要寫入的值，不是讀取時間。
  - **int 轉 bool**：唯一的轉換點在 `symbol_states` 建構 `SymbolState` 時，寫法是 `effective_high_volatility(...) == 1`。名單頁不呼叫 `symbol_states`，改用新型別 `HighVolStatus` 加上單一讀取交易。
  - **TA-TODO-RC55**：和 C5 沒有衝突。移除是在部署前、app 外進行，C5 只約束 app/。
  - **盤點腳本**：另開「N-207 盤點腳本單」（N-207p），必須先於 N-207 合入，並列入 M1。理由是產品線拉 product 就等於部署，CEO 部署前手上不會有 N-207 的程式。
  - **名稱**：統一為 `portfolio_and_stamp()`。ADR-0044 :89 自己標的是「暫稱」，要在 N-210a 送審前改字。
- **兩種待決標記**：
  - D7 相關的標記全部改成〔D7 定稿：風控 RC-75 確認；qa 核對中〕；
  - W-25f 第三子句標〔待 RC-84 起定稿〕，並新增為 M3 第 (6) 項，是合併閘；
  - 「依 CEO 裁示」的 22 處全部改寫成定案條文；
  - M3 第 (4) 項改為「不適用」，編號保留，不重編。

**新發現一件，請 CEO 確認**
- CEO #129 的字面是「只允許停止新進場」，但 ADR-0043 D4 的矩陣寫「高波動標記：允許（FR-40 未列）」。這一格是我 11-08 自己的推論，PM 和風控都沒有另外裁示過。
- 補遺暫依 #129 字面定案：組合凍結期間，高波動的標記與取消都拒絕。
- 這有方向上的影響：拒絕「取消」會讓門檻維持在 20%。這比 v3 寬，但不比現況寬。已列為送風控知悉，並請 CEO 確認原意（〔TA-v3補-14〕）。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 評估摘要
- **採用**：
  - E、T 留在 store；計畫由 `plan_change` 負責，所需的值由 store 預先算好放進 facts；
  - C11 加窄例外；
  - 唯一的 int 轉 bool 點；
  - 名單頁另用讀取型別；
  - N-207p 先合入；
  - `portfolio_and_stamp()`；
  - N-209c 獨立合入時列入 M1；
  - 依 #129 字面拒絕凍結期間的高波動操作。
- **否決**：
  - 把 E、T 搬到 roster.py：要改 qa 正在核對的 D7 定稿；
  - 由 `RosterOp` 帶入預覽日期：輸入可以偽造，而且鎖內還要再算一次；
  - 盤點 SQL 放進 N-207 PR：CEO 要先 checkout 才拿得到，等於先部署；
  - 以 app 內的「取消」操作代替部署前移除：P-4a 不會歸零，也與 RC-52 第二段選項 2 不符。

#### 方案比較

| 題目 | 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| 第 2 項：E、T 位置 | **(a) 留在 store，facts 帶 T、L、R（採）** | 不改 D7 定稿；roster.py 維持純函式 | facts 多一個型別 | 低 |
| | (b) 移到 roster.py | `plan_change` 直接呼叫 | 改 ADR 草稿，qa 要重新核對 | 中 |
| | (c) 由 store 鎖內自行判定 | 不改簽名 | 判定分散在兩處，偏離 D4 (c) | 中 |
| 第 3 項：摘要含 `changed_on` | **(a) C11 窄例外，`hv_changed_on` 必填（採）** | 單一計算點；跨日拒絕（W5） | C11 多一條例外 | 低 |
| | (b) `RosterOp` 帶預覽日 | C11 不改 | 日期可偽造；比對路徑變成兩條 | 中 |
| | (c) 不放進摘要，鎖內另外比對 | C11 不改 | 第二條比對路徑 | 中 |
| 第 9 項：盤點腳本 | **(a) N-207p 先合入（採）** | CEO 部署前就在 product 上拿得到 | 多一張單，M1 多一條 | 低 |
| | (b) 放在 N-207 PR | 和 T31 同一個 PR | 拿到腳本就等於部署 | 高，否決 |
| #129 對高波動操作的適用 | **(a) 依字面拒絕（採）** | CEO 明示的字面優先於 TA 推論；不增加買進 | 拒絕取消時維持 20% | 低，送風控知悉 |
| | (b) 維持 D4「允許」 | 不改 ADR | 和 CEO 字面不一致 | 中 |

#### 決策（規格補遺全文，可直接貼上）

````markdown
# N-207 規格 v3 補遺（TA 2026-11-10）

- 撰寫：tech-architect（唯讀）
- 對象：`work/reviews/2026-11-10-N207實作規格v3-dev-lead.md`（下稱 v3）
- 性質：回覆 v3「待 TA」13 項；依 CEO #127～#130 與 D7 確認風控檔 RC-75～RC-83，把 v3 的兩種待決標記改寫為定案條文；列出 v3.1 差異清單。本補遺簡稱〔TA-v3補-n〕。
- 疊加：v3.1 的來源表在 v3 第 5 層之後依序加入下列各層，後者覆蓋前者。本補遺若與第 4、4′ 層原文不一致，以原文為準，並回 TA。

| 層 | 簡稱 | 檔案 | 取用範圍 |
|---|---|---|---|
| 3″ | 〔D7定〕 | `work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md` | 第二段 A～F。凡與〔D7修〕2-A～2-C、2-E、〔D7補〕2-F 不同之處，以〔D7定〕為準 |
| 4 | D7 確認風控檔 | `work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md` | RC-75～RC-83（由「未疊加」改列第 4 層） |
| 4′ | 〔CEO-補〕 | `work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md` | #127～#130 |
| 6 | 〔TA-v3補〕 | 本補遺 | 全文 |

## 〔TA-v3補-0〕標記改寫規則與 D7 轉換條款

| v3 標記 | v3.1 改為 | 範圍 |
|---|---|---|
| 〔依 D7 修訂（待風控確認／CEO 拆單裁示）〕 | 〔D7 定稿：風控 RC-75 確認；qa 核對中〕 | 全部 58 處。同一處的來源括號改指〔D7定〕的對應段：2-A 指 A，2-B 指 B，2-C 指 C，2-F 指 A 第 2 點與 D。內容依〔TA-v3補-16〕 |
| 同上，但條文是 W-25f 第三子句 | 〔待 RC-84 起定稿〕 | §6 W-25f、M3 第 (6) 項、§10 commit 6 |
| 〔依 CEO 裁示〕 | 刪除標記，改寫為定案條文，句末標「（CEO #127）」 | 全部 22 處；替換文見〔TA-v3補-7〕、〔TA-v3補-11〕、〔TA-v3補-15〕 |
| 〔若 CEO 決定拆單：依 CEO 裁示改寫〕 | 本節下方的「D7 轉換條款」 | M3 第 (5) 項末點 |

- 檔頭的「待決標記」表整張換成下表：

| 標記 | 意義 | 若條件改變 |
|---|---|---|
| 〔D7 定稿：風控 RC-75 確認；qa 核對中〕 | 依〔D7定〕寫入。風控 RC-75 已確認，required 併入後不回送；qa-reviewer 依〔D7定〕第二段 F 核對中 | qa 核對若要求改動〔D7定〕，以改動後的版本為準，回 TA 核對本檔的對應條文 |
| 〔待 RC-84 起定稿〕 | W-25f 第三子句：風控 RC-77 採 F2，由 creative-lead 擬稿、風控逐字定稿 | 定稿後以風控原檔逐字為準（N207-C16）。定稿前 N-207 不得合併（M3 第 (6) 項） |

- **qa 計數**：v3.1 正文中，「依 D7 修訂（待風控確認」與「依 CEO 裁示」兩個字串的出現次數都必須是 0。附錄 B 引用舊文字時，以「v3 舊標記」代稱。
- **D7 轉換條款**（CEO #128；取代 v3 檔頭表中「CEO 若選 (B)」那一句，以及 M3 第 (5) 項末點）：
  - D7 不拆單，採方案 (A)。
  - 轉換條件，任一成立即可：
    - (1) P-4a 大於 0，而且 CEO 傾向「取消標記」；
    - (2) 其他前置都已就緒，只剩 D7 還沒完成確認（含 W-25f 第三子句定稿）。
  - 轉換**只能由 CEO 啟動**。coordinator 與實作部門不得自行認定已經轉換。
  - 改走 (B) 時，D7 確認風控檔 RC-82 第 1～7 點全部適用。v3.1 不預寫 (B) 版。
  - 轉換條件 (1) 的 P-4a 只回計數（R12），只用來選方案，不取代 §9.3 的部署前盤點（RC-82 第 7 點）。

## 〔TA-v3補-1〕待 TA 第 1 項：解析函式（依 D7 確認風控檔 RC-75 required-1 與〔D7定〕A 第 2 點結案）

- **名稱與本體**：`parse_high_volatility_flag(raw: object) -> int`，本體恰為 `return 1 if type(raw) is int and raw == 1 else 0`。
  - AST 檢查依〔D7定〕A 第 2 點「單一性檢查」1～7 項。
  - `high_volatility_marked` 撤回，app/ 內出現 0 次。
- **int 轉 bool 的唯一轉換點**（TA 新定）：store 的 `symbol_states(on)` 建構 `SymbolState` 時，寫法是 `high_volatility=effective_high_volatility(base=..., history=..., on=on) == 1`。AST 檢查三條：
  - app/ 內帶 `high_volatility=` keyword 的 `SymbolState(...)` 呼叫，只能出現在 `symbol_states` 本體內；
  - 該值必須是 `Compare`：ops 為 `Eq`，left 是對 `effective_high_volatility` 的 `Call`，comparator 是 `Constant(1)`；
  - app/ 內不得出現以 `bool(` 包住 E 或 T 回傳值的運算式。
- **build_market_snapshot**：`build_market_snapshot(high_volatility=...)` 的值只能是同一次 `states` 中該檔的 `.high_volatility`（Attribute）。不得再呼叫 E，也不得解析原始值。
- **替換條文**：
  - N207-C21 整條換成〔D7定〕D 的「N207-C21 替換全文」。其中「欄位型別由 v3 定」改為「`SymbolState.high_volatility: bool`，轉換點依〔TA-v3補-1〕」。
  - N207-T30 最後一點換成〔D7定〕D 的 T30 句。

## 〔TA-v3補-2〕待 TA 第 2 項：E、T 的位置與高波動操作的計畫（TA 定）

- **E、T 的位置**：留在 `store.py`（〔D7定〕A 第 2 點，不改）。roster.py 不 import store，也不呼叫 E、T。
- **計畫的負責者**：高波動操作的計畫由 `plan_change` 負責，和其他操作走同一條路徑（ADR-0043 D4 第 3 點 (c)）。所需的值由 store 先算好，放進 facts：
  - `models.py` 新增 `HighVolFacts(NamedTuple)`，欄位如下：
    - `history_readable: bool`
    - `target: int`：T，經 `target_high_volatility` 算出
    - `latest_id: int | None`
    - `latest_changed_on: date | None`：L
    - `roster_max_date: date | None`：R，依〔D7定〕A 第 3 點 (a) 的 SQL
  - 只在 store 內，由 `_read_high_volatility` 的結果、`target_high_volatility` 與 R 的 SQL 組成。`history_readable` 為 False 時，`target = 0`、`latest_id = None`、`latest_changed_on = None`。
  - `RosterFacts` 新增 `high_volatility: Mapping[str, HighVolFacts]`：高波動操作只含該檔；其他操作是空 mapping。這取代 v3 §2「B 加上該檔在歷程表的全部列」那一句。讀取仍依〔D7定〕B 的 D4 第 3 點 (a)。
- **roster.py 新增兩個純函式**，各只有一份定義：

```python
def high_volatility_changed_on(*, new_value: int, today_tpe: date,
                               latest: date | None, roster_max: date | None) -> date: ...
def high_volatility_label(*, target: int, effective: int) -> Literal["d", "e", "f"] | None: ...
```

  - **`high_volatility_changed_on`**：
    - `new_value == 1` 時，取 `today_tpe`、`latest`、`roster_max` 中非 None 值的最大值；
    - `new_value == 0` 時，取 `today_tpe`；
    - 其他值 raise `ValueError`。
    - 這是〔D7定〕A 第 3 點 (d) 的唯一實作，app/ 內唯一的呼叫點是 `plan_change`。
  - **`high_volatility_label`**：(T, E) 為 (1, 1) 回 `"d"`，(1, 0) 回 `"e"`，(0, 1) 回 `"f"`，其餘回 None。它只收 T、E，結構上就無法以「有歷程列」來判定（W25f-1′ 的禁止條款）。
- **`plan_change` 簽名**：新增 keyword `today_tpe: date`，沒有預設值。來源與 `portfolio_frozen` 的 `today_tpe` 相同：鎖內是 D4 第 3 點 (b)，預覽是 service 注入的時鐘。
- **高波動操作在 `plan_change` 內的判定順序**：
  1. 凍結時，回 `RosterRefusal("portfolio_frozen", until=frozen.until)`（〔TA-v3補-14〕）。
  2. `history_readable` 為 False 時，回 `RosterRefusal("hv_history_unreadable")`（〔D7定〕A 第 3 點 (a′)；排在冪等判定之前，C-D7-2）。
  3. `new_value == target` 時，回零寫入、零稽核列的計畫（(c)）。
  4. 其他情形：計畫一列歷程 INSERT（symbol、value、`changed_on = high_volatility_changed_on(...)`）與一列 D9 稽核；`RosterPlan` 帶 `hv_changed_on`。
- **store 鎖內寫入**：依計畫寫入。歷程列的 id 取 INSERT 的 `lastrowid`，再寫入稽核列的 `detail_json`，內容是 id、value、changed_on、today_tpe、L、R，不存在的值記為 null（〔D7定〕A 第 3 點 (f)）。
- **替換範圍**：v3 §2 :133-143 整段換成本節；§2 的簽名 code block 加入上述兩個函式，並更新 `plan_change`、`roster_digest` 的簽名（〔TA-v3補-3〕）。

## 〔TA-v3補-3〕待 TA 第 3 項：預覽摘要（TA 定；N207-C11 替換全文）

> **N207-C11 預覽摘要**：
> - 所有名單寫入都要先預覽、再確認。
> - 摘要只由 `roster_digest(*, op: RosterOp, facts: RosterFacts, hv_changed_on: date | None) -> str` 產生，三個參數都沒有預設值。
> - 鎖內以鎖內讀到的事實與鎖內的 `today_tpe` 重算；不一致就拒絕（`preview_stale`），零寫入。
> - 摘要不含時間戳記與窗口狀態，**唯一例外**是高波動標記操作的 `hv_changed_on`：
>   - 它是本次要寫入的 `changed_on`（ADR-0043 D7 第 3 點 (d)），屬於寫入內容，不是讀取時間；
>   - 預覽與鎖內都取自同一次 `plan_change` 回傳的計畫，由 `high_volatility_changed_on` 唯一算出；
>   - 高波動操作的這個值必須是 date，其他操作必須是 None，違反時 `roster_digest` raise `ValueError`。
> - AST：app/ 內所有 `roster_digest` 呼叫點都以 keyword 明帶 `hv_changed_on`。
> - 預覽與確認之間跨過台北日期，或 R 改變，都會拒絕。R 也在 facts 內，所以 R 改變但 `changed_on` 不變時同樣拒絕。這比〔D7定〕列的五項嚴，只會多拒絕、零寫入，可以接受。

## 〔TA-v3補-4〕待 TA 第 4 項：`SymbolState` 與名單頁讀取（TA 定）

- **`SymbolState`**：
  - 只保留 `high_volatility: bool`，值是 E(on) == 1（〔TA-v3補-1〕）。
  - 刪除 v2 的 `high_volatility_prev`、`high_volatility_changed_on`，不新增其他高波動欄位。engine 的輸入只有這一欄。
- **名單頁**：不呼叫 `symbol_states(today_tpe)`。
  - `models.py` 新增 `HighVolStatus(NamedTuple)`：`target: int`、`effective: int`（E(on)）、`on: date`、`latest_changed_on: date | None`。
  - store 新增 `roster_read(*, today_tpe: date) -> RosterRead`（名稱 dev-lead 可改）：
    - `RosterRead` 欄位為 `facts: RosterFacts`、`high_volatility: Mapping[str, HighVolStatus]`；
    - 一個連線、一個讀取交易（`BEGIN`…`COMMIT`）；名單事實與全部名單代號的 `_read_high_volatility` 取自同一個快照；E 以 `on = today_tpe` 計算；
    - `roster_facts()` 與它共用同一個內部讀取 helper，不得另寫第二份 SELECT。
  - service 的 `roster_view()`：
    - 標籤 = `high_volatility_label(target=..., effective=...)`；
    - W-25e、W-25f 的 {M}/{D} = `calendar.next_trading_day(latest_changed_on)`，日曆與名單路徑用同一個；
    - W-27 旗標：任一列的標籤不為 None 時為真；
    - API 只負責組句。
- **約束**：
  - `SymbolState` 不得出現 target、latest_changed_on 這類欄位。
  - `HighVolFacts`、`HighVolStatus` 只在 store 內建構（AST）。
  - API 回應中名稱含 `high_volatility` 的欄位，只能是 pydantic 的欄位識別名，不得以字串常數出現（包括 `Field(alias=...)` 與 dict 鍵），否則違反〔D7定〕A 第 2 點單一性檢查第 6 項。建議改用 `hv_` 前綴命名。

## 〔TA-v3補-5〕待 TA 第 5 項：TA-TODO-RC55 與 N207-C5（TA 定：不衝突，寫明範圍）

- **為什麼一定是 app 外工具**：部署通知定稿檔 RC-52 第二段選項 2 寫的是「部署前，先移除……部署後它們的 P3 門檻維持大於 15%」。移除發生在部署前，那時 N-207 還沒上線，app 內沒有高波動操作可以用；所以移除方式只能是 app 外的工具，而且不經歷程表。
- **C5 的範圍**：修訂版 C5「B 在 app/ 內不寫」只約束 app/。它不涵蓋 TA-TODO-RC55 的 app 外移除工具，也不構成對該工具的授權。
- **工具的設計**：只在 CEO 選 2 時另案設計，和 H-3 修復路徑、AC-95 一併處理（〔D7定〕B 待決）。
  - 比照 CEO #85 的離線修復工具：dry-run → CEO 確認 → apply；不 import app；只寫 B。
  - 送風控審執行者、是否可回溯，以及驗證方式（CEO 本機 P-4a = 0 而且 P-4c = 0，D7 確認風控檔 RC-83 (d) 保留）。
  - 不得以手動修改 DB 的方式進行。
- **不得以部署後的 app 內「取消」操作代替**：這樣 P-4a 不會歸零；而且依 FR-30，取消要從 `changed_on` 之後的資料日才適用，與選項 2 的字面不符。要改走這條路，必須回風控改寫驗證句與通知。
- **與 CEO #128 轉換條件 (1) 的關係**：條件 (1) 成立時，CEO 可以改走 (B)；沒有改走時，依本節處理。
- **替換條文**：
  - v3 :910 的末句改為：「修訂版 C5 只約束 app/；移除工具在 app 外、部署前執行，依〔TA-v3補-5〕。」
  - N207-C5 刪去「與 TA-TODO-RC55 的關係見待 TA 第 5 項」，改為：「C5 不涵蓋 TA-TODO-RC55 的 app 外移除工具（〔TA-v3補-5〕）。」

## 〔TA-v3補-6〕待 TA 第 6 項：W-25f 第三子句（依 D7 確認風控檔 RC-77 結案）

- 列為 N207-M3 第 (6) 項，全文見〔TA-v3補-15〕。
- M3 第 (2) 項的 W-25f 狀態行改為：「W-25f：定稿暫停（ADR 確認檔 RC-58；D7 確認風控檔 RC-77），見第 (6) 項。」

## 〔TA-v3補-7〕待 TA 第 7 項：時序（依 CEO #127 結案）

- CEO #127 採時序選項 1：N-210a（含 3A，也就是 (iii-c)）與 N-210b，在 N-207 部署前合入。時序 2 未採，所以 N-210c 不存在；M3 也不需要「N-210c 合入前 R-a 仍是殘留」的書面。
- **守門**：N-210a 必須含 3A。若以不含 3A 的版本合入（等於時序 2），M1 不成立，停下回 TA 與 CEO。
  - 檢查方式：N-210a 的 qa 審查紀錄須載明 C-N210-12～15 在該單內通過；qa-reviewer 審 N-207 時，檢查這份紀錄存在。
- **逐處替換文**（v3 行號）：
  - :68 → 移出「允許」清單，改列為「沿用」：「`portfolio_and_stamp()`：沿用。N-210a 先合入（CEO #127；N207-M1），由 N-210a 定義；N-207 對它的簽名、本體，以及 `portfolio_state()` 的委派，都零 diff（N207-C20）。」
  - :190 → 「`portfolio, stamp = portfolio_and_stamp()`（N-210a 已寫入 base，N-207 零 diff）；交給 `evaluate()` 的 portfolio、交給 `engine_batches` 與 `entry_gate_open` 的 stamp，以及交給 `commit_evaluation(td_basis=...)` 的 stamp（ADR-0044 寫法 A，CEO #127），都來自這一次呼叫的回傳值（N207-C20）；`commit_evaluation(...)` 呼叫的引數零 diff；」
  - :451 → 「擴充：交給 `evaluate()` 的 portfolio、交給 `engine_batches` 與 `entry_gate_open` 的 stamp，以及交給 `commit_evaluation(td_basis=...)` 的 stamp，都是同名變數（CEO #127；延伸 C-N210-12 的同一條 AST）。」
  - :596-599、:610-612、:618、:623、:626、:637、:643、:660 → 見〔TA-v3補-15〕。
  - N207-C3 加一點：「`evaluate_today` 內 `commit_evaluation(...)` 的呼叫引數對 base 零 diff；N-207 在 `store.py` 不新增任何 `td_basis` 出現點（ADR-0044 C-N210-12 白名單）。」

## 〔TA-v3補-8〕待 TA 第 8 項：N-209c（TA 定）

- **M1**：
  - N-209c 獨立合入時，`<M_209c>` 列入 M1 的祖先驗證與回退偵測。
  - 併入 N-209b 時不適用，交件紀錄寫明「N-209c 併入 N-209b，由 `<M_209b>` 涵蓋」，並附 N-209b 的 PR 編號。
  - 理由：N-209 前端以 N-209c 為前提（N-209 PRD AC-20），而 N-207 以 N-209 完整為前提（N207-M4）。〔TA 追加，送風控知悉〕
- **N207-C20**：把 `rule_set_snapshot()` 列入共用 parse helper 的被檢查成員：
  - 它以 `_read_state_map(conn)` 讀一次；portfolio 經 `_portfolio_from_state`，stamp 經 `_total_deploy_stamp`；
  - N-207 對它零 diff；
  - C20「每一個都只呼叫一次 `_state_map()`」對它讀作「只讀一次 state map」。
- **RC-15 的前提單清單不加入 N-209c**：N-209 並發提醒的事實範圍不依賴 N9-08。要加入的話，須回風控。

## 〔TA-v3補-9〕待 TA 第 9 項：盤點 SQL 打包檔（TA 定：另開單，先於 N-207 合入）

- **理由**：產品線拉 product 就等於部署（〔v2修一〕否決 Python import 時已寫明），部署前 CEO 本機不會有 N-207 的程式。盤點要在部署前跑，所以腳本必須先在 product 上。
- **單名與分工**：「N-207 盤點腳本單」，編號由 coordinator 給，下稱 N-207p。
  - data-engineer 撰寫；devops-sre 覆核 SQL 文字；TA 覆核 P-1、P-2、P-3、P-5 的語意；qa-reviewer 審查。
- **路徑**：`apps/stock-desk/backend/scripts/n207_preflight/`。
  - 一個項目一個 SQL 檔，檔名就是項目：`p1.sql`、`p2.sql`、`p3.sql`、`p4a.sql`、`p4c.sql`、`p5.sql`、`p6.sql`、`p7.sql`、`p8.sql`、`d1.sql`（1d）、`d1_2.sql`（1d-2）、`p9a.sql`、`p9b.sql`、`p9c.sql`。
  - P-4b 單獨放在 `p4b_LOCAL_ONLY.sql`，檔頭註明「輸出只留在 CEO 本機畫面，不得貼回對話、work/、紀錄或任何 agent」。runner 不執行這個檔。
- **runner `run_preflight.py`**：
  - 只用標準函式庫；以 `file:<db>?mode=ro` URI 開啟；不 import app；不連網；
  - 只印 `<項目>\t<計數或布林>`；
  - SQL 出錯時印 `<項目>\tERROR`，並以非 0 結束，不得印 0（AC-93、AC-97）。
- **N-207p 自帶的測試**：
  - 唯讀連線上嘗試寫入，必定失敗；
  - 種入代號後，輸出不含任何代號字串；
  - 空表時每一項都回 0；
  - SQL 內的預設值字面常數等於 `RuleParams()` 的預設值（〔TA-v3補-10〕）。
- **與 N-207 的關係**：
  - N-207 對 `scripts/n207_preflight/**` 零 diff；T30、T31 直接讀 base 上的這些檔。
  - T31 若在 N-207 上失敗，先修 N-207p（新的 merge commit），N-207 再 merge 最新 product 並重跑（M2）；不得在 N-207 PR 內改 SQL 檔。
  - 這是 D7 確認風控檔 RC-83 (a)「同一個 PR」在首次落地時的讀法：兩者首次落地分屬兩單，由 T31 釘住等價；兩者都合入 product 之後，任何一方的改動都要在同一個 PR 內一起改另一方。〔TA 解讀，送風控知悉〕
- **M1**：固定清單加 `<M_207p>`，只做祖先驗證，不做回退偵測（N-207p 被回退時，T30、T31 會在 M2 重跑時失敗）。
- **§9.3**：CEO 在 product 上執行，這時 product 已含 N-207p、尚未含 N-207。盤點之後到部署之前，`scripts/n207_preflight/` 若有變動，要重跑盤點。
- 刪除 v3 §0 :90 的〔待 TA 第 9 項〕一行。

## 〔TA-v3補-10〕待 TA 第 10 項：P-1、P-2、P-3、P-5 的 SQL（TA 定：data-engineer 擬稿，併入 N-207p）

約束如下，逐條可檢查：
1. 輸出形狀依 §9.3「輸出形狀」。空表回 0，不回 NULL；`SUM` 一律包 `COALESCE`。
2. bpt 與 n_targets 取「現行參數列」：
   - WHERE 與 ORDER BY 必須與 `store.py` 的 `active_params` 逐字相同（`effective_date <= ? ORDER BY effective_date DESC, version DESC LIMIT 1`）。
   - on_date 是台北今日，寫成 `date('now', '+8 hours')`（台灣沒有日光節約時間）。v3.1 §3 要寫明 N-207 鎖內讀現行參數用的 on_date；若不是台北今日，P-1、P-3 的 on_date 跟著改，並回 TA。
   - 欄位以 `json_extract(payload, '$.<key>')` 讀取，key 依 `RuleParams` 的序列化名稱。
   - 沒有現行列，或 key 不存在時，用 `RuleParams` 的預設值。預設值以字面常數寫在 SQL 內，由 N-207p 的測試釘住。
   - payload 不是合法 JSON 時，`json_extract` 會出錯，輸出 ERROR，視為未完成盤點。
3. P-1、P-2 以 `playbook_batches` 依 symbol 分組。部署前全部是第 1 輪，還沒有 `batch_round` 欄。
4. P-2 另加第五個計數：`typeof(batch_no) <> 'integer'` 的列數，大於 0 → STOP-1。
   - 理由：這種列會讓 `BatchState` 建構失敗，後果與 `batch_no < 1` 相同；而且 MIN、MAX 會判不準。〔TA 追加，送風控知悉〕
5. P-3 依〔修一〕乙 R-14 的定義。
6. P-5 照用下列 SQL：

```sql
-- P-5: status outside the closed set, or NULL (BINARY comparison; non-TEXT values count as exceptions)
SELECT COUNT(*) FROM playbook_batches
WHERE status IS NULL OR status NOT IN ('planned', 'open', 'closed', 'skipped');
```

- 替換 v3 :760：「P-1、P-2、P-3、P-5 由 data-engineer 依〔TA-v3補-10〕擬稿，TA 覆核語意；其餘 SQL 由 TA 給出。全部打包進 N-207p，由 devops-sre 覆核文字。」

## 〔TA-v3補-11〕待 TA 第 11 項：`portfolio_and_stamp()`（TA 定）

- **不是實質衝突**：ADR-0044 :89 自己寫的是「暫稱 `portfolio_with_stamp()`」，:362（C-N210-12）沿用這個暫稱。它的語意與 N207-C20 相同：只做一次 `_state_map()`，同時產生 `PortfolioState` 與 `TotalDeployStamp`，共用同一個建構函式。
- **定名**：`portfolio_and_stamp()`。依 #127，N-210a 先合入，名稱由 N-210a 落地。所以在 **N-210a 送審前**，由 tech-writer 把 ADR-0044 :89、:362 改字。這是純改名、不動語意，不回送風控。
- **N207-C20 第 1、3 點替換文**：「名稱為 `portfolio_and_stamp()`，由 N-210a 定義（CEO #127 時序選項 1）。N-207 沿用，不得另寫、不得改名、不得改本體。base 上的實際名稱若不同，停下回 TA，不得在 N-207 內改名。」
- v3 :384 換成上句。

## 〔TA-v3補-12〕待 TA 第 12 項：確認 dev-lead 的處理

- `until` 的斷言移到 T24；「engine 對任何 data_date ≤ 台北今日都判為凍結」的性質測試留在 T13；刪除推導標記。
- T13 這一點補上依據：「ADR-0043 D8 第 6 點『性質』」。

## 〔TA-v3補-13〕待 TA 第 13 項：吸收 RC-75～RC-83，出 v3.1（依 D7 確認風控檔結案）

- **寫入路徑遇到無法解析的 `changed_on`**：依〔D7定〕A 第 3 點 (a′)，以及 C-D7-2、C-D7-3。
  - 內部原因碼定名為 `"hv_history_unreadable"`。刻意不含 `high_volatility` 子字串，否則會違反單一性檢查第 6 項。
  - API 把它映射到名單操作既有的一般失敗分支，分支名稱由 v3.1 指認。
  - 不得使用 `ROSTER_RESULT_*`、W-25d～f、`ROSTER_REFUSED_PREVIEW_STALE`、`ROSTER_REFUSED_TRANSIENT`。
  - §6「每個原因對應一個 `wording.py` 識別名」對這個原因例外，直到專用字面定稿為止。
- 其餘 RC 的吸收位置見〔TA-v3補-16〕。

## 〔TA-v3補-14〕新發現：CEO #129 對高波動標記操作的適用（TA 定案，送風控知悉、CEO 確認）

- **事實**：
  - FR-40 寫「組合凍結期間，只允許『停止新進場』」。
  - ADR-0043 D4 第 6 點矩陣中，高波動標記一列寫「允許（FR-40 未列）」。這一格是 TA 在 2026-11-08 的推論，理由是 FR-40 的拒絕清單沒有列出高波動；PM 與風控都沒有對這一格另外裁示。
  - CEO #129 的字面是「只允許停止新進場」。
- **定案**：依 #129 字面，組合凍結期間，高波動的標記與取消一律拒絕，回 `RosterRefusal("portfolio_frozen", until=...)`，字面沿用既有的凍結句。CEO 明示的字面，優先於 TA 先前的推論。
- **方向**：
  - 拒絕標記：較嚴。
  - 拒絕取消：門檻維持 20%。這比 v3「允許取消」寬，但不比現況寬，也不增加買進。
  - 風控若認為取消應該放行，那是放寬 CEO #129 的字面，須經 CEO 明示。
- **替換條文**：
  - §2 `plan_change`：「首次設定、重新加入、開新輪、季度提交、高波動標記與取消，在 `frozen.frozen` 為真時回 `RosterRefusal("portfolio_frozen", until=frozen.until)`；只有停止新進場不看 `frozen`（CEO #129；FR-40）。」API 層的快速凍結判定同樣適用於高波動操作。
  - N207-C14 末句：「只有停止新進場在凍結期間允許（CEO #129）。」
  - N207-T13：拒絕清單加入高波動標記與取消。
  - N207-T24「凍結期間，停止新進場與高波動標記都成功」改為：「凍結期間：停止新進場成功；高波動標記與取消都回 `portfolio_frozen`，四張表逐列不變；凍結且歷程無法解析時，回 `portfolio_frozen`（判定順序依〔TA-v3補-2〕）。」
  - ADR-0043 D4 矩陣（tech-writer，送風控知悉後落檔）：高波動標記一列的組合凍結欄改為「拒絕（CEO #129）」。

## 〔TA-v3補-15〕§9.1、N207-M1、N207-M3 整段替換文

**§9.1 前置依賴**（取代 :591-618）：
- **固定項，共 11 條**：N-177a、N-195、N-196、N-197a、N-177b、N-198、N-209b、N-209、N-210a、N-210b、N-207p。
  - N-210a、N-210b：CEO #127 採時序選項 1（情況 A）。N-210a 須含 3A（〔TA-v3補-7〕）。
  - N-207p：〔TA-v3補-9〕。
- **條件項**：N-209c，獨立合入時才列入（〔TA-v3補-8〕）。
- 各單合入的先後依各自規格；M1 只驗證祖先關係。N-209 必須先於 N-207 合入。
- **N-210 的共同條件**：v3 :603-609 的證據鏈 (a)(b) 保留。「CEO 書面三件事」一句改為：「CEO #127 已涵蓋三件事：選修正、寫法 A、時序選項 1。」
- **CEO 事項**：
  - ADR-0043 的核可須明示包含 ADR-0034 補充四（J-9），並明示 D7 殘留 H-1～H-4 接受或修正（〔D7定〕B 待決）。Q-C11 已由 CEO #129 明示。
  - tech-writer 把〔D7定〕併入 ADR-0043（qa 核對通過後）之前，CEO 若先核可 ADR-0043，核可範圍須明示排除 D7 第 1～3 點與〔D7定〕B 的連動句。
  - D7 拆單：依 #128 結案，見〔TA-v3補-0〕。
  - ADR-0044：依 #127 結案。
  - `/today` 事實欄位：依 #130 開 N-211，排在 D7 之後，不擋 N-207；app 有第二位使用者時轉為 required（補遺確認檔 RC-73；D7 確認風控檔 RC-78）。

**N207-M1**：
- :623 改為：「對 §9.1 每一個 `<M_x>`（固定 11 條，加 N-209c 條件項）……」
- :626 改為：「範圍：N-209b、N-210a、N-210b 一律適用；N-209c 獨立合入時也適用。」
- (i) 的 `rev-parse` 改標「D7 確認風控檔 RC-83 (c) 保留」。執行者是 devops-sre；qa-reviewer 只能重跑 R4。
- :637 改為：「N-210a 或 N-210b 在 N-207 合入後被回退時，CEO #127 的前提就消失，必須先回風控，並由 CEO 重新裁示。」

**N207-M3**：合併前必須同時具備：
1. CEO 核可 ADR-0043 的紀錄，明示包含補充四，並明示 H-1～H-4 接受或修正。
2. 風控對 FR-42、D3 第 7 點與補充四的單項確認，以及全部字面的逐字定稿（W-25f 第三子句另見第 (6) 項）。
3. N207-M4。
4. 不適用（CEO #127 時序選項 1）。編號保留，不重編。
5. **ADR-0043 D7 第 1～3 點修訂**〔D7 定稿：風控 RC-75 確認；qa 核對中〕。三件事都具備才成立：
   - (a) qa-reviewer 依〔D7定〕第二段 F 的核對紀錄沒有 BLOCKING；
   - (b) tech-writer 已把〔D7定〕A～C 併入 ADR-0043，檔頭寫「風控 2026-11-10 確認（RC-75～RC-80）」，並填入 qa 紀錄檔名；
   - (c) 第 (1) 項的核可沒有排除 D7 第 1～3 點。
   - 產品線合併即部署，所以這一項也是部署閘。
6. **W-25f 第三子句新字面的風控逐字定稿**〔待 RC-84 起定稿〕（D7 確認風控檔 RC-77；方案 (A) 下這是 N-207 的合併閘）：
   - creative-lead 依 RC-77 擬稿條件 1～7 擬稿（或提議刪除這一子句），附自查表送風控；
   - 定稿前，舊字面不得進入程式或畫面（C-D7-5）。
   - (a′) 的專用拒絕字面不是合併閘；定稿前走既有的一般失敗分支（C-D7-3）。

**M3 狀態**：
- (1)：未完成。
- (2)：W-24、W-05m、W-10、W-22 兩行、W-27、W-19、N9-07 的狀態照 v3；W-25f 見第 (6) 項；W-27 備註由 creative-lead 依 RC-79 更新。
- (4)：不適用。
- (5)：風控 RC-75 確認；qa 核對中。
- (6)：〔待 RC-84 起定稿〕。

## 〔TA-v3補-16〕v3.1 差異清單（dev-lead 依此逐列改；B-3 記錄覆蓋）

| # | v3 位置 | 改法 | 依據 |
|---|---|---|---|
| 1 | 檔頭狀態 :6-13 | ADR-0043：D7 第 1～3 點修訂已由風控 RC-75 確認、qa 核對中，CEO #128 採方案 (A)。ADR-0044：CEO #127（寫法 A、時序選項 1、選修正）。刪除「範圍外的新檔」那一點 | CEO #127、#128；RC-75 |
| 2 | 待決標記表 :14-19 | 換表，加 qa 計數為 0 的規則 | 〔TA-v3補-0〕 |
| 3 | 來源表 :21-53 | 加 3″〔D7定〕、4′〔CEO-補〕、6〔TA-v3補〕；D7 確認風控檔改列第 4 層 | 本補遺檔頭 |
| 4 | §0 store.py :61-70 | 加入 `_read_high_volatility`、`parse_high_volatility_changed_on`、`HighVolChange`、`HighVolRead`、R 的 SQL、`roster_read`；`portfolio_and_stamp()` 改列「沿用」；刪除「見待 TA 第 1、2 項」 | 〔D7定〕A；〔TA-v3補-1、2、4、7〕 |
| 5 | §0 models.py、roster.py、api | models.py 加 `HighVolFacts`、`HighVolStatus`、`RosterFacts.high_volatility`；roster.py 加兩個函式；api 加 `hv_history_unreadable` 的映射 | 〔TA-v3補-2、4、13〕 |
| 6 | §0 零 diff 與 :90 | 加 `scripts/n207_preflight/**` 與 `commit_evaluation` 呼叫引數；刪除 :90 | 〔TA-v3補-7、9〕 |
| 7 | §1 :99-110 | 換標記；`SymbolState` 只留 `high_volatility: bool`；`HighVolChange`、`HighVolRead` 放 store.py；`playbook_roster_log.taipei_date` 寫明取自鎖內 D4 第 3 點 (b) 換算的 `today_tpe`；`detail_json` 加 today_tpe、L、R | 〔D7定〕A、B；〔TA-v3補-4〕 |
| 8 | §2 :120-152 | 簽名 code block 依〔TA-v3補-2、3〕更新；:133-143 換成〔TA-v3補-2〕；:148 依〔TA-v3補-14〕；:152 改為 `HighVolFacts` | 同左 |
| 9 | §3 :170-182 | 寫入流程換成〔D7定〕A 第 3 點 (a)、(a′)、(b)～(f) 與預覽摘要；計畫由 `plan_change` 負責；:182 換成 (a′)；加 `roster_read` | 〔D7定〕A；〔TA-v3補-2、4、13〕 |
| 10 | §4 :190、:195、:202 | :190 依〔TA-v3補-7〕；:195 的值取 `states[sym].high_volatility`；:202 名單頁改用 `roster_read` | 〔TA-v3補-1、4、7〕 |
| 11 | §6 拒絕型別 :212-216 | 加 `hv_history_unreadable` 的例外 | 〔TA-v3補-13〕 |
| 12 | §6 高波動標籤 :233-238 | 標籤由 `high_volatility_label` 判定，日期依 W25f-3′；換標記 | 〔TA-v3補-4〕 |
| 13 | §6 :255 | 「〔D7補〕2-H 的核對」改為「D7 確認風控檔 RC-81 確認三處仍為真（前提 P-4c = 0）」 | RC-81 |
| 14 | §6 W-25f :260-267 | W25f-2′ 換成〔D7定〕E；第三子句標〔待 RC-84 起定稿〕；加 C-D7-5 | RC-77、RC-79 |
| 15 | §6 RC-73 新單的提及 | 改寫為 N-211（#130），不擋 N-207 | #130；RC-78 |
| 16 | N207-C1、C2、C4 | 換標記；C4 另讀 R 的 SQL | 〔D7定〕A 第 3 點 (a) |
| 17 | N207-C3 | 加 `commit_evaluation` 呼叫引數零 diff、不新增 `td_basis` | 〔TA-v3補-7〕 |
| 18 | N207-C5 | 換標記；改寫與 TA-TODO-RC55 的關係 | 〔TA-v3補-5〕 |
| 19 | N207-C11 | 整條換掉 | 〔TA-v3補-3〕 |
| 20 | N207-C14 | 依 #129 | 〔TA-v3補-14〕 |
| 21 | N207-C15 :344 | engine 名稱檢查改為 C-D7-6 的 8 個名稱，另加 `HighVolFacts`、`HighVolStatus`、`high_volatility_changed_on`、`high_volatility_label`，共 12 個〔TA 追加〕 | 〔D7定〕D |
| 22 | N207-C20 | 第 1、3 點依〔TA-v3補-11〕；加 `rule_set_snapshot()` | 〔TA-v3補-8、11〕 |
| 23 | N207-C21 | 整條換成〔D7定〕D 的替換全文，型別句依〔TA-v3補-1〕 | RC-75 required-1 |
| 24 | §7 新增 | C-D7-1～C-D7-6，引用〔D7定〕D 的原文；加〔TA-v3補-1〕int 轉 bool 的 AST、〔TA-v3補-4〕型別建構的 AST | 同左 |
| 25 | N207-T7 :451 | 依〔TA-v3補-7〕 | #127 |
| 26 | N207-T11、T20 | 換標記（四張表） | 〔D7定〕B |
| 27 | N207-T13 | 補依據；拒絕清單加入高波動操作 | 〔TA-v3補-12、14〕 |
| 28 | N207-T14 :473-484 | 改為「依 ADR-0043 附錄 D7-T（〔D7定〕C）全部列：E1～E18（含 E16a～c）、W1～W12（含 W8、W8b、W9a、W9b、W10、W11、W12）、P1～P4、L1～L13；期望值以原表為準，本檔不複寫；門檻邊界照舊」。另加五項：凍結時做高波動操作回 `portfolio_frozen`；凍結且無法解析時回 `portfolio_frozen`；`roster_digest` 的 `hv_changed_on` 與操作種類不符時 raise ValueError；R 在預覽與確認之間改變時回 `preview_stale`；int 轉 bool 的 AST | RC-76；〔TA-v3補-1、3、14〕 |
| 29 | N207-T15 | 加 C-D7-1、擴充後的 C-D7-6 名稱清單、〔TA-v3補-1、4〕的 AST | 同左 |
| 30 | N207-T18 | `detail_json` 加 today_tpe、L、R；斷言 `taipei_date` 等於鎖內的 `today_tpe` | 〔D7定〕A 第 3 點 (f)、C-D7-4 |
| 31 | N207-T24 :536 | 依 #129 | 〔TA-v3補-14〕 |
| 32 | N207-T30 | 末點依〔D7定〕D；「檔案路徑見待 TA 第 9 項」改為 `scripts/n207_preflight/p4a.sql`、`p4c.sql` | 〔TA-v3補-9〕 |
| 33 | N207-T31 | 標明 BLOCKING；P-9a、P-9b、P-9c 分別回報計數；SQL 路徑；跨單的讀法 | RC-83 (a)；〔TA-v3補-9〕 |
| 34 | §9.1、M1、M3 | 整段換掉 | 〔TA-v3補-15〕 |
| 35 | §9.3 :756-760 | SQL 出處；CEO 從含 N-207p 的 product 執行 | 〔TA-v3補-9、10〕 |
| 36 | §9.3 P-2 列與 STOP-1 | 加第五個計數 | 〔TA-v3補-10〕 |
| 37 | §9.3 P-4 判定細節 :883 | 換標記，依據改為 RC-81 | RC-81 |
| 38 | §9.3 STOP-4、P-9b、P-9c 的〔TA 追加〕 | 依序改標「D7 確認風控檔 RC-83 (b) 保留」、「RC-83 (a) 保留」 | RC-83 |
| 39 | §9.3 部署通知 :905 | 分送一句換成 RC-83 (e) 的條件 1～5：兩次都用原標題「N-207 部署通知」、不加銜接語；各段的 `{INVENTORY_AT}` 來源；時限照舊；分別記錄；事實不符時整段回風控 | RC-83 (e) |
| 40 | §9.3 TA-TODO-RC55 :909-910 | 「P-4c 得 0」改標 RC-83 (d) 保留；末句依〔TA-v3補-5〕 | 同左 |
| 41 | §10 | commit 1 含歷程表與 trigger；commit 3 依〔D7定〕A 第 2 點與〔TA-v3補-1〕；commit 4 含高波動操作，依 (a)～(f)、(a′)、〔TA-v3補-2、3〕；commit 6 在 RC-84 定稿前不含 W-25f 第三子句，定稿前 N-207 不得合併 | 同左 |
| 42 | 附錄 B | 新增 B-3，逐列記錄本清單的覆蓋；:1051、:1056、:1104 依〔TA-v3補-0〕改寫 | — |
| 43 | 待 TA 清單 :1113-1144 | 換成一句：「v3 待 TA 13 項已由〔TA-v3補-1～13〕回覆，正文已併入。」 | — |
| 44 | 文件同步待辦 :1146-1152 | 改為下列五點：<br>(1) ADR-0043（tech-writer）：qa 核對通過後併入〔D7定〕A～C；D4 矩陣依〔TA-v3補-14〕修改。<br>(2) ADR-0044（tech-writer）：N-210a 送審前，把 :89、:362 改名為 `portfolio_and_stamp()`；Decision 1、6 已依 #127 改字，不必再改。<br>(3) creative-lead：W-25 備註換成〔D7定〕E；W-25 狀態改為「W-25f 定稿暫停（ADR 確認檔 RC-58；D7 確認風控檔 RC-77）」；依 RC-77 擬第三子句；W-27 備註依 RC-79 更新；擬 (a′) 的專用拒絕字面。<br>(4) PM：FR-47 的 RC-43 檔名、FR-46 與 AC-73 兩項照 v3；RC-80 的兩條新 AC 可選，採納時 Given 要寫明台北日期與資料日；FR-40、AC-59、AC-60 要不要明列高波動操作（〔TA-v3補-14〕）。<br>(5) data-engineer：N-207p | 同左 |
````

#### 對實作的約束（qa-reviewer 可逐條檢查）
補遺中的約束全部 BLOCKING，重點如下：
- **單一定義**：
  - `high_volatility_changed_on`、`high_volatility_label` 在 roster.py 各只有一份定義；
  - `roster_digest` 的三個參數都沒有預設值，所有呼叫點都以 keyword 明帶 `hv_changed_on`。
- **int 轉 bool**：唯一一處，AST 形狀依〔TA-v3補-1〕。
- **型別建構**：`HighVolFacts`、`HighVolStatus` 只在 store 內建構。API 欄位不得以字串常數的形式含有 `high_volatility`。
- **原因碼**：`hv_history_unreadable` 在前端與 `wording.py` 的計數為 0，直到風控定稿專用字面。
- **零 diff**：N-207 對 `scripts/n207_preflight/**`、`portfolio_and_stamp()`、`commit_evaluation` 呼叫引數都零 diff。
- **M1 與 M3**：M1 固定 11 條，加 N-209c 條件項；M3 第 (5)、(6) 兩項都成立才能合併。
- **計數**：兩種舊標記字串在 v3.1 正文中的出現次數為 0。

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - 全文：
    - v3 規格（1153 行）
    - v3 交件說明
    - D7 確認風控檔（RC-75～RC-83）
    - 我的 D7 修訂定稿
    - 決策包補遺（#127～#130）
  - 部分：
    - `docs/adr/0044-…md`：:1-30、:75-214、:300-376。已確認 :8、:206-211、:321 反映了 #127；:89、:362 仍是 `portfolio_with_stamp()`。
    - `docs/adr/0043-…md` D4 :225-254：D4 矩陣「高波動標記：允許（FR-40 未列）」，用 grep 確認這是 TA 自己的推論。
    - PRD FR-40 :276-283
    - D7 修訂交付 3（N-209c，:640-713）
    - 部署通知定稿檔 RC-55 與選項 2 的字面（grep）
    - v2 補遺第 19 點（grep）
    - 修一檔中盤點腳本的寫法，含 :34 的否決理由（grep）
- **讀過的程式**（唯讀 grep）：`store.py` 中 `playbook_rule_params` 的 schema 與現行列的 SELECT（:103-107、:1126-1127）、`RuleParams` 的預設值回落（:820）；`backend/scripts/` 下現有檔案的清單。
- **沒有查證的部分**：
  - app/ 內其他 `SymbolState(` 建構點有沒有傳 `high_volatility=`，由 dev-lead 與 qa 的 AST 處理；
  - `RuleParams` 的 JSON key 名稱；
  - N-207 鎖內讀現行參數時用的 on_date；
  - 名單操作既有一般失敗分支的實際名稱；
  - N-210a、N-209c 落地後的實際方法名。
  - 以上都已寫成「不符時回 TA」。
- 我沒有指定任何套件版本，沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案，也沒有執行 Bash。

## 四、下一步

1. **dev-lead**：依第二段的補遺出 v3.1，逐列套用〔TA-v3補-16〕，並在附錄 B-3 記錄覆蓋；指認一般失敗分支的名稱，寫明鎖內讀現行參數用的 on_date。
2. **qa-reviewer**：依〔D7定〕第二段 F 完成 D7 的核對；v3.1 定稿後檢查兩種舊標記的計數都是 0，並逐條核對 M1、M3。
3. **tech-writer**：
   - N-210a 送審前，把 ADR-0044 :89、:362 改名為 `portfolio_and_stamp()`；
   - qa 核對 D7 通過後，把〔D7定〕A～C 併入 ADR-0043；
   - 風控知悉之後，修改 ADR-0043 D4 矩陣中高波動標記那一格。
4. **risk-compliance-officer**：
   - 知悉四件事：#129 對高波動「取消」的方向；N-209c 列入 M1；RC-83 (a) 在首次落地時的跨單讀法；P-2 的第五個計數。
   - W-25f 第三子句的逐字定稿（RC-84 起）。
5. **creative-lead**：W-25f 第三子句擬稿並附自查表；W-25 狀態與備註；W-27 備註；(a′) 的專用拒絕字面。
6. **data-engineer、devops-sre**：依〔TA-v3補-9、10〕做 N-207p，由 devops-sre 覆核 SQL 文字。
7. **coordinator**：
   - 給 N-207p 編號並派工。
   - 把 H-1～H-4 放進 ADR-0043 的核可問項。
   - 請 CEO 確認一件事：「#129 依字面也會擋凍結期間的高波動標記與取消；如果您原意是凍結期間仍可標記或取消高波動，請明示。」
   - 另外請釐清一點，不擋 N-207：ADR-0044 的 R-f、R-g 在寫法 A 下「不變」，CEO #127 的「選修正」是否要求另立 ADR 來修 R-f。

**相關檔案**：
- /home/user/AICompany/work/reviews/2026-11-10-N207實作規格v3-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-10-N207實作規格v3交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-D7修訂確認與W25f裁示-風控.md
- /home/user/AICompany/work/dispatch/2026-10-17-決策包二補遺-新增CEO事項.md（#127～#130）
- /home/user/AICompany/docs/adr/0044-stock-desk-排程台REBALANCE之後-未結算的R系列買進列如何處置.md（:89、:206-211、:362）
- /home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md（D4 矩陣 :243-250）
- /home/user/AICompany/work/stock-desk-排程台標的設定-PRD.md（FR-40 :278）
- /home/user/AICompany/work/reviews/2026-11-10-ADR0044定稿與ADR0043D7修訂-tech-architect.md（N-209c 交付 3，:640-713）

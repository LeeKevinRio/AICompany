# N-177 規格修訂三與 N-196 spec

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

修訂三寫好了，全文在下面的 markdown 區塊，請原文附到規格檔末。內容只有你指定的三件事：
1. 3.11 改寫為「風控選 (a)」，三個條件分別落成 N177b-C13、T17 的追加斷言、新增的 T22，另修訂 C11 與 T19。全部標為 BLOCKING，擋 N-177b 合併。
2. T21 第 3 點改成「與 base 相比次數不增加」。我 grep 過，service.py 目前的 `"EMERGENCY"` 字面是 :306、:420、:422 三處，和風控說的一致。另外加了 store.py 的計數（:245、:291 兩處）。
3. N-196 spec 完成，包含：方案比較、新的 store 讀取 API `read_rebalance_inputs`、鎖的語意、與 R-α 的關係、約束 N196-C1～C10、測試 N196-T1～T7（BLOCKING）、與 N-195 的先後順序。

有一點要先講：**N-196 的正確性依賴 N-177a 的 R-α。** 一次讀交易只有在「每筆結算的股數與現金在同一個交易內 commit」時，才不會看到結算只完成一半。舊的逐批 sell 是先 commit `set_cash`、再 commit `save_batch`，兩者分開。所以 N196-C8 規定 base 必須同時含 N-177a 與 N-195。這不影響期限，因為 R2 本身就是 N-177a 的 release。

````markdown
## 修訂三（tech-architect，2026-11-07；回應風控 [風控-177R3]）

- 依據：[風控-177R3] `work/reviews/2026-11-07-N177修訂二比對與3.11、5.6裁示-風控.md`（CONDITIONAL APPROVE；3.11 選 (a)；5.6 選 (c)；T21 suggested）。
- 程式依據：同本檔第 6 行的 checkout，只讀，未執行。行號以內容定位。
- 本修訂只取代下面點名的段落，其餘維持修訂二。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀。
- 修改處索引見第 4 節。

### 1. 3.11（取代修訂二 3.11）：EMERGENCY 的 `batch_no` 為 None，風控選 (a)

**1.1 裁示登錄（理由以 [風控-177R3] 第二節第 3 點為準，本檔不轉錄）**
- 接受排除。N2 的字面、`SETTLEMENT_EXIT_ITEM` 與 `exit_items` 的組法都零 diff（N177b-C6 不變），不新增 N2 的項目格式。
- [風控-177R2] B 件實作條件 2「不得出現 None」，以本裁示開一個唯一的、具名的例外，範圍只限 1.2 的組合。
- 以下 1.2～1.5 全部 BLOCKING，擋 N-177b 合併。

**1.2 N177b-C13（新增；條件 1）：具名常數**
- 例外只能以一個具名常數加一個判定函式表達，放在 `tests/` 下，由 T17、T19、T22 共用，只有一份定義。不得放進 `app/`，因為 production 行為沒有例外，例外只存在於測試斷言的範圍。
- 精確限定四個欄位，缺一不可，也不得擴大：
  - `rule_id == "EMERGENCY"`
  - `action == "sell"`
  - `status == "executed"`
  - `batch_no is None`（用 `is None`，不得用 falsy 判斷）
- 參考寫法（名稱可以由 dev-lead 調整，結構不得放寬）：
```python
class C11Exception(NamedTuple):
    """The only combination N177b-C11 does not cover.

    An EMERGENCY sell judged executed whose ``batch_no`` is None: N2 renders its
    item through SETTLEMENT_EXIT_ITEM unchanged, so it reads "第 None 批".
    Unreachable in app/ (RC-8; pinned by N177b-T22). Accepted by the
    risk-compliance ruling of 2026-11-07 on N-177 revision 2, item 3.11,
    option (a), as the single exception to [風控-177R2] B 件 condition 2.
    Must not be widened. If a reachable path is ever found, option (b) is
    required again: go back to tech-architect and risk-compliance.
    """

    rule_id: str
    action: str
    status: str
    batch_no: None


N177B_C11_EXCEPTION: Final = C11Exception(
    rule_id="EMERGENCY", action="sell", status="executed", batch_no=None
)


def is_c11_exception(line: Directive) -> bool:
    return (
        line.rule_id == N177B_C11_EXCEPTION.rule_id
        and line.action == N177B_C11_EXCEPTION.action
        and line.status == N177B_C11_EXCEPTION.status
        and line.batch_no is None
    )
```
- docstring 必須引用 RC-8 與本裁示（[風控-177R3] 3.11 (a)）。
- 回復條款：T22 失敗、或日後發現 `app/` 內有路徑產生 `batch_no` 為 None 的 EMERGENCY 列時：
  - (b)「新增 N2 的無批次項目格式，由 creative-lead 擬稿、風控定稿」回復為 required；
  - 回 TA 與風控；
  - 不得維持排除，也不得以放寬、skip、xfail T22 的方式處理。
- [TA 補] 例外的範圍要被釘住：在 T17 的窮舉網格上，`is_c11_exception` 為真的列，其 `(rule_id, action, status, batch_no)` 去重之後恰好只有一組，就是上面的四欄組合。例如 `(EMERGENCY, buy, executed, None)`、`(EMERGENCY, sell, missed, None)` 都必須為假。

**1.3 N177b-C11（修訂）**
- 第三點「唯一已知的例外見 3.11」改為：唯一的例外是 N177b-C13 的組合，只能由 `is_c11_exception` 排除。其餘文字不變。

**1.4 測試修訂與新增（BLOCKING）**
- **N177b-T17（追加斷言；條件 2）**：網格中符合 `is_c11_exception` 的每一組，除了原有的「只進 N2」之外，對該次結算的 `SettlementResult.warnings` 再斷言：
  - 恰好一個元素含子字串「None」（區分大小寫），而且這個元素就是 N2；
  - 該 N2 元素逐字等於 `SETTLEMENT_EXIT_NOTHING_MOVED_NOTE.format(count=..., exit_items=...)`，其中這一列的項目是 `SETTLEMENT_EXIT_ITEM.format(symbol=..., batch_no=None, execution_date=...)`；
  - 該元素中「None」只出現一次（`count("None") == 1`），而且出現在「第 None 批」裡；
  - 其他元素（SUMMARY、W-B3、unsettled 理由、三句）一律不含「None」。
  - fixture 的 symbol、rule 文字不得含「None」，以免誤判。
- **N177b-T19（修訂）**：
  - 「3.11 的組合不納入，並在測試中以具名常數列出這項排除」改為：排除只能經由 `is_c11_exception`，不得另寫條件或清單；被排除的情境改由 T17 的追加斷言檢查。
  - 其餘不變。
- **N177b-T22（新增；條件 3：「走不到」的前提）**：
  - (a) 行為：`plan_emergency_exit`（service.py:352）在固定 seed、至少 100 組隨機的 `EmergencyExitState` 上（多檔、多批、含 covered 與 stale、含沒有預載日線的標的），產出的每一筆 `rule_id == "EMERGENCY"` 的 directive 都要滿足：
    - `type(batch_no) is int` 且 `batch_no >= 1`；
    - `(symbol, batch_no)` 屬於 `state.open_batches`。
  - (b) [TA 補] 經 `commit_emergency_exit` 實跑一次全部出清後，`directive_log()` 中所有 EMERGENCY 列的 `batch_no` 都是整數。
  - (c) [TA 補] AST：`app/` 內帶有關鍵字 `rule_id="EMERGENCY"` 的 `Directive(...)` 建構恰好一處，在 `plan_emergency_exit` 內（目前是 service.py:414-420），而且 `batch_no=` 的值是 `batch.batch_no`。
  - 失敗時依 1.2 的回復條款處理。
- 修訂二 3.10 的 N177b-T3 不變（仍用 `batch_no` 為整數、批次列不存在的列）。

### 2. N177b-T21 第 3 點（取代；[風控-177R3] suggested，採用）

- 原句：「service.py 除了 `_is_exit_sell`，沒有新增 `"EMERGENCY"` 字面」。改為：
  - service.py 中值恰為 `"EMERGENCY"` 的 `ast.Constant` 個數，與 base 相比不增加。
  - 計數用 `ast.walk`：含 f-string 內嵌運算式，單引號、雙引號都算。`EMERGENCY_EXIT…` 這類較長的字串與識別名不算。
- base 的實測值（本檔 checkout，grep 加讀碼確認）是 3 處：
  - :306，`_is_exit_sell` 的 `directive.rule_id == "EMERGENCY"`；
  - :420，`plan_emergency_exit` 的 `rule_id="EMERGENCY"`；
  - :422，同函式 `rule_summary` 的 f-string 內 `wording.rule_text('EMERGENCY', params)`（單引號）。
- 測試以具名常數 `SERVICE_EMERGENCY_LITERAL_BASELINE = 3` 寫死，註解列出上述三個位置，斷言 `count <= 3`。這個 baseline 只准調低，調高要回 TA。
- N-177a 依修訂一 1.4，service.py 零 diff，所以 N-177b 的 base 應該仍是 3。PR 說明要附上對 base commit 實測的計數；不是 3 時交 qa 判定。
- [TA 補] `_settled_line_note` 函式本體內，`"EMERGENCY"` 常數的個數為 0。
- [TA 補] 同法計數 store.py，不得多於 base 的 2 處：
  - :245 `UNKEYED_RULE_IDS`；
  - :291 `EMERGENCY_RULE_ID`。
  - 這一點落實修訂二 3.3 末句「store.py 中的 `'EMERGENCY'` 字面不因 N-177b 增加」。
- T21 第 1、2 點不變。

### 3. N-196：REBALANCE 的計算輸入改為日線載入後的單一讀交易（修訂二 5.6；風控選 (c)）

**3.1 定位**
- 小單 N-196，負責：dev-lead。
- 期限：比照 N-195。
  - 目標與 R2 同一個 release；最遲與第三包同一個 release，不得更晚。
  - 不擋 N-177a 合併，也不擋 R2 部署。
  - R2 依 RC-9 延後期間，N-196 不得單獨出 release；N-196 不屬於 hotfix。
- 審查（條件 5）：
  - 本 spec 經 coordinator 送風控審，風控核可前不得合併；建議核可後再開工，以免重工。
  - 實作超出本 spec 的範圍就要回 TA 與風控。
- 不另立 ADR：沒有新增寫入路徑，只是把既有的兩次讀取併成一次讀交易。歸屬記在 ADR-0041 Consequences 的 R-3′（{編號} = N-196）。N-196 合入後，由 tech-writer 以補充註記 R-3′ 已修正。

**3.2 程式事實（service.py、store.py；只讀）**
- service.py `rebalance`（:1516 起）：
  - :1535 `batches = self._store.list_batches()`，第一次讀批次，自己開一個連線；
  - :1536 `symbols` 取自全部批次（含 planned）；
  - :1537 `_load_symbol_bars`（:1202-1212，逐檔 `load_bars`，可能跨網路、數秒級）；
  - :1538 `portfolio = self._store.portfolio_state()`，讀現金與 TOTAL_DEPLOY，另開一個連線；
  - :1539 `active_params`，讀 `playbook_rule_params`，不碰 `playbook_state`；
  - :1543-1557 估值迴圈：只計 open 而且 `remaining_shares > 0` 的批次；`loaded.get(batch.symbol, NOTHING_LOADED)`（:1546；`NOTHING_LOADED` 在 :133）。`build_market_snapshot` 遇到沒有任何 bar 時回 None（:147-148），連同 `is_usable` 為假的情況，都進 `missing`（:1555）；
  - :1559-1572：有 `missing` 時回 `insufficient_data`，`previous_total_deploy=portfolio.total_deploy`（:1565），不寫入；
  - :1574 `total_assets = portfolio.cash + deployed`；:1575 `new_total_deploy = total_assets * params.deploy_ratio`；
  - :1612-1616 `set_capital(...)`，N-195 改為 `set_total_deploy(...)`；
  - :1617-1628 `RebalanceResult`。
- store.py：
  - `_connect`（:748-750）：每次呼叫開一個新連線，timeout 為 `BUSY_TIMEOUT_MS`（5000 ms，cache.py:36）；
  - `_init_schema`（:754）以 `enable_wal` 把 DB 檔切成 WAL；
  - `list_batches`（:782-787）：一個連線、一句 `SELECT {_BATCH_SELECT} FROM playbook_batches ORDER BY symbol, batch_no`，轉換用 `_row_to_batch`（:789-826）；
  - `_state_map`（:920-923）：一個連線、`SELECT key, value FROM playbook_state`；
  - `portfolio_state`（:929-943）：`_state_map` 加上轉換，缺鍵時視為 0；
  - 先例 `read_in_flight`（:1379-1402，ADR-0035 補充四 2.3）：一個連線、`BEGIN`（DEFERRED）、多句 SELECT、`COMMIT`；錯誤處理照 C-11。
- 缺口：:1535 與 :1538 分屬兩個連線、兩個時點，中間隔著日線載入。中間若有賣出結算 commit，總資產會重複計算（修訂二 5.6、ADR-0041 R-3′）。

**3.3 方案比較**
| 方案 | 內容 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| N196(i) 單一讀交易 | 日線載入後呼叫新的 store API，在同一個連線、同一個 DEFERRED `BEGIN` 內讀全部批次與 `playbook_state`；估值只用這一份 | 符合條件 1；不取寫鎖、不擋結算；與 `read_in_flight` 同一模式；service diff 只有 :1535-1538 一帶 | store 要新增一個 API，`list_batches`、`portfolio_state` 改成委派 | 低 | **採用** |
| N196(ii) 載入後再各讀一次 | :1538 之後再呼叫一次 `list_batches()`、`portfolio_state()` | store 零 diff | 仍是兩個連線、兩個時點，窗口從秒級縮到毫秒級，但沒有消除；不符合條件 1 | 中 | 否決 |
| N196(iii) `BEGIN IMMEDIATE` 讀 | 同 (i)，但取寫鎖 | 非 WAL 模式下也不必等 | 為唯讀取寫鎖，會與結算互相排隊；在 WAL 下沒有必要；多一個 `BEGIN IMMEDIATE`，容易被誤讀成寫入者 | 中 | 否決 |
| N196(iv) 長讀交易包住載入 | 先 `BEGIN`，讀批次、載入日線、讀現金，再 `COMMIT` | 一個 snapshot 涵蓋全程 | 交易跨網路；非 WAL 時擋住寫入者數秒；WAL 時阻礙 checkpoint；違反「持交易期間不得跨網路、不得呼叫其他 store 方法」的既有模式（C-3） | 高 | 否決 |

**3.4 規格**
- store.py（模組層級 helper；各只有一份定義）：
```python
class RebalanceRead(NamedTuple):
    """What :meth:`PlaybookStore.read_rebalance_inputs` read, in one read transaction (N-196)."""

    #: Every batch row, exactly as :meth:`PlaybookStore.list_batches` returns them.
    batches: list[BatchState]
    #: The portfolio flags, exactly as :meth:`PlaybookStore.portfolio_state` returns them.
    portfolio: PortfolioState


def _read_all_batches(conn: sqlite3.Connection) -> list[BatchState]:
    rows = conn.execute(
        f"SELECT {_BATCH_SELECT} FROM playbook_batches ORDER BY symbol, batch_no"
    ).fetchall()
    return [PlaybookStore._row_to_batch(row) for row in rows]


def _read_state_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM playbook_state").fetchall()
    return {str(key): str(value) for key, value in rows}


def _portfolio_from_state(state: Mapping[str, str]) -> PortfolioState:
    ...  # body moved verbatim from portfolio_state (store.py:932-943)
```
  - `list_batches`：改為 `with closing(self._connect()) as conn: return _read_all_batches(conn)`，行為不變。
  - `_state_map`：改為委派給 `_read_state_map`，行為不變。它在 :931、:975、:1076 的呼叫者都不改。
  - `portfolio_state`：改為 `return _portfolio_from_state(self._state_map())`，行為不變。
  - 新增：
```python
    def read_rebalance_inputs(self) -> RebalanceRead:
        """The batches and the portfolio REBALANCE values, from one snapshot (N-196).

        One connection, one ``BEGIN`` (DEFERRED: no write lock is taken), the
        batch read, then the state read, ``COMMIT`` -- the pattern of
        :meth:`read_in_flight`. Both reads come from the same read transaction,
        so 總資產 never counts shares a settlement already turned into cash.
        SELECT only; nothing else runs while the transaction is open.

        Errors follow :meth:`commit_emergency_exit` (C-11): roll back if SQLite
        has not already, then raise unchanged.
        """
        with closing(self._connect()) as conn:
            conn.execute("BEGIN")
            try:
                batches = _read_all_batches(conn)
                portfolio = _portfolio_from_state(_read_state_map(conn))
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        return RebalanceRead(batches=batches, portfolio=portfolio)
```
  - 讀取順序固定：先批次，後 state（N196-T4 依賴這個順序）。helper 必須是模組層級函式，以名稱呼叫，讓測試可以包裝。
- service.py `rebalance`：只改 :1535-1538 一帶。
```python
        as_of = today or datetime.now(UTC).date()
        listed = self._store.list_batches()
        symbols = sorted({batch.symbol for batch in listed})
        loaded = self._load_symbol_bars(symbols, today=as_of)
        # N-196: value the book from one read taken after the bars are loaded.
        book = self._store.read_rebalance_inputs()
        batches = book.batches
        portfolio = book.portfolio
        params = self._store.active_params(as_of)
```
  - :1539 之後逐字不變。估值迴圈、`missing` 分支、公式、`RebalanceResult`、REBALANCE 指令列，以及 N-195 的 `set_total_deploy` 呼叫，都沿用 `batches`、`portfolio` 這兩個名稱，所以零 diff。
  - 第一次讀取（`listed`）只用來決定要載入哪些標的的日線，不得參與任何計算。

**3.5 鎖的語意，以及與 R-α 的關係**
- 鎖的語意：
  - DEFERRED `BEGIN` 不取寫鎖（RESERVED）。交易內只有兩句 SELECT，沒有網路、沒有其他 `self.*` 呼叫、沒有回呼。
  - WAL（production：`_init_schema` 的 `enable_wal`）：
    - snapshot 在第一句 SELECT（批次）時固定，兩句 SELECT 讀到的是同一份已 commit 的狀態；
    - 並發的寫入者不被阻擋，它們的 commit 對這個交易不可見；
    - 讀取端也不等待寫入者。
  - 非 WAL（例如 `:memory:` 或尚未切換的舊檔）：第一句 SELECT 起持有 SHARED lock，直到 `COMMIT`。寫入者的 commit 最多等兩句 SELECT 的時間（上限是 busy_timeout 5 s）。一致性相同。
  - 不用 `BEGIN IMMEDIATE`，理由見 3.3 (iii)。
- 與 R-α（修訂一 1.3）的關係：
  - **N-196 的正確性以 R-α 為前提。** R-α 讓每一筆動到股數或現金的結算（`_settle_batch_line`、`_settle_s2_fill`），把批次與現金在同一個 `BEGIN IMMEDIATE` 內寫入並一起 commit。所以一個 snapshot 對每筆結算，只會看到「全部」或「全無」。
  - R-α 之前，逐批 sell 是先 commit `set_cash`、再 commit `save_batch`（store.py:1540-1543 一帶，W1、W3），snapshot 仍可能落在兩者之間。因此 N-196 的 base 必須含 N-177a（N196-C8）。
  - N-196 不新增寫入者，不改 R-α 的任何約束（修訂一的 C6、C7、C17 與 T20、T23～T26 不變）。
  - 合起來的效果（範圍比照 4.10 追加句）：REBALANCE 計算用的各批股數、open／closed 狀態與現金，等於依取得寫鎖順序的某一個循序執行中、某兩次結算之間的帳冊狀態。本句只對這三項成立。`trailing_active`、`peak_close` 等欄位不參與 REBALANCE 計算。
- 與 ADR-0035 補充四 2.3 的關係：`read_rebalance_inputs` 與 `read_in_flight` 同一模式、各自獨立，不合併、不共用回傳型別。
- 與 N-195 的關係：
  - N-195 讓 REBALANCE 不再寫 cash（R-1′）；N-196 讓 REBALANCE 的輸入來自一致的 snapshot（R-3′）。兩者合起來，REBALANCE 只寫三個 TOTAL_DEPLOY 鍵，而且計算來自一份一致的讀值。

**3.6 約束 N196-C1～C10（qa-reviewer 逐條檢查）**
- **C1（diff 範圍）**：
  - diff 只含：store.py 中 3.4 的 `RebalanceRead`、三個模組層級 helper、`read_rebalance_inputs`，以及 `list_batches`、`_state_map`、`portfolio_state` 的委派；service.py `rebalance` 的 :1535-1538 一帶；`tests/**`。
  - engine.py、models.py、wording.py、`app/api/**`、`app/data/**`、`app/services/**` 零 diff。
- **C2（單一讀交易；條件 1）**：
  - `read_rebalance_inputs` 只用一個連線、一個 DEFERRED `BEGIN`、兩句 SELECT（先批次後 state）、`COMMIT`；
  - 不得 `BEGIN IMMEDIATE`，不得有任何寫入語句，交易內不得呼叫會另開連線的 `self.*` 方法；
  - 錯誤處理照 C-11。
- **C3（rebalance 的讀取順序與用途；條件 1）**：
  - `rebalance` 內 `list_batches(` 恰好一次，在 `_load_symbol_bars(` 之前，結果只用在 `symbols` 的運算式；
  - `read_rebalance_inputs(` 恰好一次，在 `_load_symbol_bars(` 之後；
  - `rebalance` 內不得呼叫 `portfolio_state(`、`get_batch(`、`_state_map(`；
  - `deployed`、`missing`、`total_assets`、`new_total_deploy`，以及兩個分支的 `previous_total_deploy`，都只來自這一份讀值；
  - 不得第二次載入日線。
- **C4（缺日線；條件 2）**：
  - 重讀後，open 而且 `remaining_shares > 0`、但沒有載入日線的標的，必須經由既有的 `loaded.get(..., NOTHING_LOADED)` 走到 `missing`，回 `insufficient_data`、不寫入；
  - 不得以 0 計入，不得略過，不得為它補載日線；
  - :1543-1572 零 diff。
- **C5（零 diff；條件 4）**：
  - 所有字面（wording.py 零 diff）；
  - TOTAL_DEPLOY 公式（:1574-1575）；
  - `RebalanceResult` 的定義（models.py）與兩個分支的建構；
  - REBALANCE 指令列與 `record_directives` 的呼叫；
  - `active_params` 的呼叫；
  - N-195 的 `set_total_deploy` 呼叫與 store 端實作。
- **C6（store 單一定義）**：
  - 「全部批次的 SELECT」「`playbook_state` 的 SELECT」「state 轉 `PortfolioState`」在 store.py 各只有一份文字定義；
  - `list_batches`、`_state_map`、`portfolio_state` 的回傳值與現行逐值相同（含缺鍵時為 0）。
- **C7（呼叫點）**：
  - `app/` 內 `read_rebalance_inputs(` 只在 `rebalance` 被呼叫；
  - 其他呼叫者（例如觀察 3.9 第 3 點的 `evaluate_today`）要改用它，回 TA。
- **C8（base 與先後）**：
  - PR 的 base 必須同時含 N-177a（R-α）與 N-195；
  - PR 在 N-195 合入 product 之後才開，不得與 N-195 並行修改 `rebalance`（採納風控 suggested，提升為 required；理由見 3.5，以及 C5 對 N-195 部分的零 diff）。
- **C9（PR 形式與 release）**：
  - 獨立 PR，以 merge commit 合入 product；
  - 不得併入 N-177a、N-177b、N-195、N-188、N-189 的 PR；
  - 合入前 merge 最新 product（不得 rebase），之後重跑完整 CI 與 seam；
  - release 位置依 3.1。
- **C10（範圍外禁止；條件 5）**：
  - 不得改動結算的鎖或交易（`_settle_batch_line`、`_settle_s2_fill`、`claim`）；
  - 不得改動 `evaluate_today` 的 :1901-1902 與 `_rule_set_status` 的讀取；
  - 不得改動 `confirm_rules`；
  - 超出就回 TA 與風控。

**3.7 測試 N196-T1～T7（全部 BLOCKING；用真實 `PlaybookStore`、檔案型 DB）**
- **T1（循序）**：
  - `test_playbook_rebalance.py` 的既有斷言零改動、原樣綠燈；
  - N195-T1～T7 零改動、原樣綠燈（N195-T3 的 hook 在第一句寫入 `playbook_state` 之前，仍在重讀之後，所以預期值不變）。
- **T2（決定性交錯；條件 3）**：
  - 設定：
    - 同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B；A 交給 `PlaybookService` 跑 `rebalance`，B 代表並發的結算；
    - 一批 open（remaining 100、cost 已設、收盤 c），現金 C0，有可用的估價；
    - 另一個 planned 批次，供參數 (iii) 使用。
  - 注入點：包住 A 的 `market_resolver` fake。在 `rebalance` 第一次為該標的取 bar 時，先執行 hook 再回傳 bar。這個點在舊碼是 :1535 之後、:1538 之前，在新碼是 `list_batches` 之後、`read_rebalance_inputs` 之前。
  - hook：以 B 跑完一筆結算並 commit（比照 N195-T3 的 harness：先 log、claim，再 `settle`）。參數化為三種：
    - (i) 逐批 sell S1 40 股，開盤價 p；
    - (ii) S2 100 股，把該批關閉；
    - (iii) planned 批次的逐批 buy 100 股。
  - 斷言（預期值由 hook 之後以新的 store 實例讀到的帳冊計算）：
    - `status == "ok"`；
    - `total_assets == cash′ + Σ c × remaining′`，Σ 只計 open 而且 remaining′ > 0 的批次；
    - `deployed_value == Σ c × remaining′`；
    - `new_total_deploy == total_assets × deploy_ratio`，而且存入的 TOTAL_DEPLOY 與它相同；
    - 最終現金 = C0 + 該筆結算的現金異動（N-195）；
    - (i)、(ii) 另外斷言 `new_total_deploy` 嚴格小於舊碼的值 `(C0 + p × moved + c × 100) × deploy_ratio`，也就是不偏高。
  - 效力證明（QB-N196-1）：
    - PR 說明附上本機輸出，顯示把 service.py 暫時換回 :1535 `batches = self._store.list_batches()`、:1538 `portfolio = self._store.portfolio_state()` 時，三個參數全部失敗：(i)、(ii) 偏高，(iii) 偏低；
    - 這份對照不 commit（比照 QB-11）。
- **T3（重讀後缺日線；條件 2）**：
  - 設定同 T2。hook 改為：以 B 寫入一個新標的 X 的 open 批次（remaining > 0）。這是測試 fixture，可以用 `save_batch`。X 在第一次讀取時不存在。fake 價格服務仍然 seed 了 X 的 bar，以證明 X 是「沒有載入」，而不是「拿不到資料」。
  - 斷言：
    - `status == "insufficient_data"`；
    - `message == REBALANCE_BLOCKED.format(symbols=...)`，其中含 X；
    - TOTAL_DEPLOY、set_at、source、`STATE_CASH` 都和 hook 之後的值相同；
    - 沒有新增 REBALANCE 指令列；
    - fake 價格服務沒有收到 X 的請求（沒有二次載入）。
  - 變體：X 是 planned 批次 → 不計入，`status == "ok"`。
  - 效力證明併入 QB-N196-1：換回舊碼時 `status == "ok"`，本測試失敗。
- **T4（同一個讀交易的 snapshot；條件 1）**：
  - 前置斷言：A 的 DB 是 `PRAGMA journal_mode` = `wal`。
  - 注入點：monkeypatch 模組層級的 `_read_all_batches`，呼叫原函式之後執行 hook。也就是在批次 SELECT 之後、state SELECT 之前。
  - hook：以 B 跑完一筆逐批 sell S1 40 股並 commit（R-α 之後是單一 `BEGIN IMMEDIATE`）。斷言 hook 在 1 秒內完成，也就是寫入者沒有被讀交易擋住。
  - 斷言：
    - `read_rebalance_inputs()` 回傳的該批 remaining 是 100，`portfolio.cash` 是 C0，兩者都是結算前的值，一致；
    - 之後以新的連線讀，兩者都是結算後的值。
  - 效力證明併入 QB-N196-1：把 `read_rebalance_inputs` 暫時改成兩個連線（批次仍經 `_read_all_batches`，state 另開連線讀）時，`portfolio.cash` 讀到結算後的值，本測試失敗。
- **T5（SQL trace）**：A 在一次 `rebalance` 中所有連線的語句：
  - 對 `playbook_state` 的 SELECT 恰好一句，與日線載入之後的 `playbook_batches` 全表 SELECT 在同一個連線、同一組 `BEGIN`…`COMMIT` 之間；
  - 該交易內沒有 INSERT、UPDATE、DELETE、REPLACE，也沒有 `BEGIN IMMEDIATE`；
  - 日線載入之前，只有一句 `playbook_batches` 全表 SELECT。
- **T6（AST）**：
  - 逐條檢查 C3 的呼叫次數、先後與用途（`listed` 只出現在 `symbols` 的運算式）；
  - C7 的呼叫點；
  - `read_rebalance_inputs` 本體內沒有 `IMMEDIATE` 字串，也沒有寫入語句字串。
- **T7（store 委派等價）**：
  - 固定 fixture（多檔、多批、含 closed 與 planned）在沒有並發時，`read_rebalance_inputs()` 等於 `RebalanceRead(list_batches(), portfolio_state())`；
  - `STATE_CASH` 等鍵不存在時，`portfolio.cash == Decimal("0")`，`total_deploy == Decimal("0")`；
  - `test_playbook_store.py` 既有斷言原樣綠燈。
- 參數 (ii) 需要 N-177a 的 S2 路徑。依 C8，N-196 的 base 一定含 N-177a，所以不另設歸屬條款。

**3.8 與 N-195 的先後與衝突熱點**
- 順序：N-177a、N-195（目標 R2）合入 product → 開 N-196 PR → 風控核可的 spec 加上 qa 沒有 BLOCKING → 合入 → 搭 R2，最遲第三包。
- N-195 延誤時，N-196 跟著順延，但兩者的期限都不得晚於第三包。若預計趕不上，coordinator 要回報風控。
- 衝突熱點：
| 位置 | N-195 | N-196 | 解法 |
|---|---|---|---|
| service.py `rebalance` :1535-1538 | 零 diff（N195-C5） | 修改 | 不衝突 |
| service.py `rebalance` :1612-1616 | 改成 `set_total_deploy` | 零 diff（C5） | 以 N-195 版本為準 |
| store.py `set_capital`／新 helper（:945 一帶） | `_total_deploy_state`、`set_total_deploy` | 零 diff | 不衝突 |
| store.py `list_batches`／`_state_map`／`portfolio_state`（:782、:920、:929） | 零 diff | 改成委派 | 不衝突；N-177a 的 `roll_peak_closes` 仍呼叫 `list_batches`，行為不變 |
| store.py 模組層級 helper 區 | — | 新增三個 helper | 與 N-177a 的 conn helper（`_add_cash`、單批讀取）各自成段，名稱不重疊 |

**3.9 已知限制（N-196 之後）**
- 第 1 點：snapshot 之後、`set_total_deploy` 寫入之前 commit 的結算，不反映在這次的 TOTAL_DEPLOY 中。這等於循序的「先 REBALANCE、再結算」，不是重複計算，不列為殘留。
- 第 2 點：日線在 snapshot 之前載入。窗口內新變成 open 的批次，以已載入的收盤價估值，與循序執行相同；它的標的沒有載入時，依 C4 拒絕。
- 第 3 點 [觀察，不在 N-196，交風控知悉]：`evaluate_today` 在 :1901 讀批次、:1902 讀現金，也分屬兩個連線。是否另外處理，由風控決定；N-196 不擴充（C10）。
- ADR-0041 的 R-3′ 在 N-196 上線前仍然存在；風控第二節第 5 點的 CEO 內部通知，也維持到 N-196 部署為止。

### 4. 修改處索引（風控比對用）
| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | 3.11 全段（本修訂 1.1） | 取代：[待風控] → 風控選 (a)；N2 零 diff 維持 | [風控-177R3] 二-3 |
| 2 | N177b-C13（1.2） | 新增：具名常數、四欄精確限定、docstring 引用 RC-8 與本裁示、回復條款 | 二-3 條件 1、3 後段 |
| 2′ | 1.2 末點 | [TA 補]：網格上去重之後只有一組 | 二-3 條件 1「不得擴大」 |
| 3 | N177b-C11 第三點（1.3） | 修訂：例外只能經由 C13 | 二-3 書面註記 |
| 4 | N177b-T17（1.4） | 追加斷言：唯一的「None」在 N2「第 None 批」 | 二-3 條件 2 |
| 5 | N177b-T19（1.4） | 修訂：排除只能經由 `is_c11_exception` | 二-3 條件 1、2 |
| 6 | N177b-T22 (a)（1.4） | 新增：`plan_emergency_exit` 產出的 `batch_no` 都是整數 | 二-3 條件 3 |
| 6′ | N177b-T22 (b)、(c) | [TA 補]：端對端與 AST 唯一產生點 | 二-3 理由（grep） |
| 7 | N177b-T21 第 3 點（本修訂 2） | 取代：與 base 相比不增加；baseline 3（:306、:420、:422） | 二-1 第 11 項 suggested |
| 7′ | T21 追加兩點 | [TA 補]：`_settled_line_note` 為 0；store.py baseline 2（:245、:291） | 修訂二 3.3 末句 |
| 8 | N-196 定位、期限、審查（3.1） | 新增 | 二-4 期限、條件 5 |
| 9 | 程式事實、方案比較（3.2、3.3） | 新增 | 二-4 事實核對 |
| 10 | store API 與 service 改法（3.4） | 新增：`read_rebalance_inputs` | 二-4 條件 1 |
| 11 | 鎖的語意、與 R-α 的關係（3.5） | 新增：以 R-α 為前提 | 二-4 條件 1 |
| 12 | N196-C1～C10（3.6） | 新增約束；C8 把 suggested 提升為 required | 二-4 條件 1～5、suggested |
| 13 | N196-T1～T7、QB-N196-1（3.7） | 新增測試（BLOCKING） | 二-4 條件 1～3 |
| 14 | 先後與衝突熱點（3.8） | 新增 | 二-4 suggested |
| 15 | 已知限制與觀察（3.9） | 新增；第 3 點交風控知悉 | 誠實揭露 |

（修訂三由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。N-196 spec 待風控審。）
````

## 二、各部門回報

- **tech-architect（本人，唯讀）**：
  - 依風控裁示寫好修訂三的三件事；
  - T21 的 baseline 用 grep 實測；
  - N-196 比較了 4 個方案，採用 DEFERRED 單一讀交易。
- **risk-compliance-officer**：本輪沒有參與；N-196 spec 等他審（條件 5）。
- **其他部門**（product-manager、dev-lead、qa-reviewer、devops-sre、tech-writer、frontend-engineer 等）：本輪沒有參與。

### 修改處索引
與區塊第 4 節相同，共 15 項，加上 3 個 [TA 補] 子項：

| 風控條件 | 落點 |
|---|---|
| 3.11 條件 1 | N177b-C13 |
| 3.11 條件 2 | T17 的追加斷言 |
| 3.11 條件 3 | T22 (a)，加上 C13 的回復條款 |
| 5.6 條件 1 | N196-C2、C3，T4、T5 |
| 5.6 條件 2 | N196-C4，T3 |
| 5.6 條件 3 | N196-T2，QB-N196-1 |
| 5.6 條件 4 | N196-C5 |
| 5.6 條件 5 | 3.1，C10 |

需要風控特別比對的兩處：
- **C8：** 把「N-196 排在 N-195 之後」從 suggested 提升為 required，並加上「base 必須含 N-177a」。
- **3.9 第 3 點：** 這是新的觀察。`evaluate_today` 在 :1901-1902 讀批次和讀現金也分屬兩個連線，屬於同類問題。本次不擴充處理，交風控決定要不要開單。

## 三、驗證

- **讀過的程式**（`/home/user/AICompany/apps/stock-desk/backend/`，只讀，未執行）：
  - `app/playbook/service.py`：:133-161、:304-306、:352-434、:1202-1260、:1500-1634、:1655-1678、:1885-1906；
  - `app/playbook/store.py`：:245、:291、:340-359、:700-967、:1027-1044、:1250-1402；
  - `app/playbook/models.py`：:201-211；
  - `app/playbook/wording.py`：:940-956；
  - `app/data/sqlite_util.py`：`enable_wal`；
  - `tests/test_playbook_rebalance.py`：:1-80。
- **grep 結果：**
  - service.py 的 `["']EMERGENCY["']` 只有 :306、:420、:422 三處；
  - store.py 只有 :245、:291 兩處；
  - `list_batches(`、`portfolio_state(`、`_state_map(` 的所有呼叫點都看過。
- **讀過的文件：**
  - `/home/user/AICompany/work/reviews/2026-11-07-N177修訂二比對與3.11、5.6裁示-風控.md`：全文；
  - `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md`：:1-18、:344-385、:623-687、:695-805、:945-1007、:1107-1557。
- **未查證：**
  - T4 依賴 WAL 下讀交易不擋寫入者。這是 SQLite 的既有語意，但我沒有實跑；
  - T2、T3 透過包住 fake `market_resolver` 注入，能不能實際接上，要等 dev-lead 確認 `FakePriceService` 的介面；
  - 「AST 計數會涵蓋 f-string 內嵌的 `'EMERGENCY'`」是依 Python 3.12 的 AST 結構推論，沒有實跑；
  - `confirm_rules` 與 REBALANCE 並發時 TOTAL_DEPLOY 的覆寫問題，沒有分析，也不在本修訂內。
- 我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案。
- CEO 本輪不需要親自驗證什麼。

## 四、下一步

1. **coordinator：**
   - 把上面的區塊原文附到規格檔 `/home/user/AICompany/work/reviews/2026-11-07-N177實作規格與偵測回溯工具-tech-architect.md` 末尾；
   - 把修訂三（重點是 N-196 spec 與修改處索引）送風控審；
   - 告訴 tech-writer，ADR-0041 R-3′ 的 {編號} 是 N-196。
2. **dev-lead：**
   - N-177b 依修訂二加上修訂三第 1、2 節開發，C13、T17、T19、T21、T22 都是 BLOCKING；
   - N-196 等風控核可、N-195 合入之後再開 PR。
3. **風控：** 審 N-196 spec，並裁示 3.9 第 3 點（`evaluate_today` 的兩次讀取）要不要另外處理。

# N-177 實作規格（N-177a／N-177b）與 N-177／N-190 唯讀偵測回溯工具規格

- 日期：2026-11-07
- 撰寫：tech-architect（唯讀）
- 性質：實作規格。另附 ADR-0041 草案（proposed），由 tech-writer 落檔。
- 程式位置：`apps/stock-desk/backend/`，以 2026-11-07 的 product/stock-desk checkout 為準（已含 N-168 9253032，未含 N-190）。行號會位移，請以內容定位。全部是讀碼判定，未執行。
- 依據：
  - [TA-177] `work/reviews/2026-11-05-N177修正範圍評估-tech-architect.md`
  - [風控-177] `work/reviews/2026-11-05-N177修復與N190字面裁示-風控.md` A-1～A-5
  - [M1] `work/reviews/2026-11-05-ADR0035補充五修正一-tech-architect.md` M1-2
  - [風控-0040] `work/reviews/2026-11-05-ADR0040與補充五修正一審查-風控.md`；R7 的取代範圍以 M-2 為準
  - ADR-0040（accepted，CEO #110）Decision 13、14
  - CEO #106：回溯檢查用唯讀腳本，由 CEO 本機執行
- 前提狀態：A-1 內部通知已送達 CEO（coordinator 確認）。
- 字面規則：本檔不寫產品字面。N-177b 的句子待 creative-lead 擬稿、風控定稿。

---

## 1. 評估摘要

- 採用：
  - N-177a：S2 在 `store.settle` 內成交動帳，加法稽核表 M2（`playbook_fill_moves`）。
  - N-177b：`settle` 改為回傳結構化結果，加兩句結算揭露。
  - 新增一支唯讀偵測回溯工具，同時涵蓋 N-177 的偵測與 CEO #106 的回溯檢查。
- 否決：
  - 沿用 `save_batch`／`set_cash` 逐次開連線寫入（多批之間會出現半套狀態）；
  - M0（風控支持 M2）；
  - 在 `playbook_directives` 加移動股數欄位；
  - `directive_id` 為 None 時靜默不動帳；
  - 擴充 n172 探針（會改變 CEO #85 證據檔的指紋）；
  - 探針 import engine 做重放（違反 CEO #106）；
  - 探針報告走 stdout 再由 PowerShell 轉存（PowerShell 5.1 會亂碼）。
- 維持 VETO：(D) 改寫既有指令列、(E) 啟動時自動回補。

## 2. 方案比較

| 議題 | 方案 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| S2 寫入方式 | (a) 新 helper，單一 conn、`BEGIN IMMEDIATE`、只 UPDATE `remaining_shares`／`status`／`updated_at` | 原子；欄位不變式可以從 SQL 文字檢查 | 多一個私有 helper | 低 | **採用** |
| | (b) 沿用 `get_batch`／`save_batch`／`set_cash` | 程式碼少 | 每個呼叫各開一個連線，多批之間有半套狀態；`INSERT OR REPLACE` 整列重寫 | 半套狀態、C-B6 欄位被覆寫的疑慮 | 否決 |
| 稽核紀錄 | (a) M2 加法表，含 `source` 欄與零移動 sentinel | N-188 (B2)、(c) 的「沒有稽核紀錄」、群組 B、(B) repair 都能精確判定 | 新表；動到 X-14 的表名斷言 | 低 | **採用**（風控支持） |
| | (b) M0 | 範圍最小 | (B2) 不成立，(c) 判定精度要回審 | 判定脆弱 | 否決 |
| | (c) `playbook_directives` 加移動股數欄 | 不用新表 | 一張 S2 跨多批，一個欄位裝不下；動到 K1 所在的表 | 範圍外溢 | 否決 |
| `directive_id` 為 None 的 S2 | (a) raise `ValueError`，在任何寫入之前 | 不會出現沒有稽核的動帳 | 手動重放 S2 會失敗 | 正式路徑一律帶 id（service.py:1363），無實害 | **採用** |
| | (b) 照舊不動帳 | — | 保留原 bug，而且無聲 | — | 否決 |
| | (c) 動帳但不寫稽核 | — | 違反 C8 | — | 否決 |
| N-177b 的判定來源 | (a) `settle` 回傳結構化結果 | 「找不到批次」只判定一次 | `settle` 簽名做加法 | 低 | **採用** |
| | (b) service 結算前先讀（比照 N2） | `settle` 零 diff | 「找不到批次」會有兩份判定，可能漂移 | 中 | 否決 |
| 偵測工具 | (a) 新的一支，stdlib only | 隔離；符合 CEO #106 | 有一份常數複本，靠測試對齊 | 低 | **採用** |
| | (b) 擴充 n172 探針 | 共用骨架 | 改變 CEO #85 證據檔的指紋與版本 | 證據鏈斷掉 | 否決 |
| | (c) import engine 做重放 | 判定精確 | 違反「不 import app」 | — | 否決 |
| 報告輸出 | (a) `--out-dir` 寫兩個新檔（UTF-8），stdout 只印 ASCII 摘要 | Windows 不亂碼 | 會寫兩個報告檔（不是 DB） | 低 | **採用** |
| | (b) stdout，由 PowerShell 轉存 | 零寫入 | PS 5.1 管線與主控台編碼會讓中文亂碼 | CEO 讀不到 | 否決 |

## 3. ADR 草案：ADR-0041（proposed）stock-desk 排程台 S2 成交動帳與成交移動稽核表

**Context**
1. `store.settle` 對 S2（`batch_no` 為 NULL）只 `_mark_schedule` 就 return。列已經被 claim 為 executed，但股數沒減、現金沒入帳，所以 S2 每天重發（F8／N-177）。
2. S2 是整檔層級的單，跨多個批次移動股數。逐批重放（ADR-0039 Decision 10）推不出它在每一批移動了多少股。
3. ADR-0035 Decision 6、N172-C8 寫明 `settle()` 零 diff。這是 N-172a 為了避開與 N-168（C-B6）並行修改而設的範圍約束。

**Decision**
1. `settle` 新增 S2 分支，規格見本檔第 4 節（N177-C1～C16）。
2. 新增加法稽核表 `playbook_fill_moves`。只有 S2 寫入；逐批列繼續走重放。
3. 共用常數只有一份定義，由 N-177a 定義，N-188 引用。
4. ADR-0035 Decision 6／6′、Consequences 中「`settle()` 零 diff」的各句、N172-C8，判定為 N-172a 的範圍約束（第 4.7 節），原文不改。
5. ADR-0039 Decision 10 要在群組 B 開工前補充修訂（第 4.9 節）。
6. 既有資料只能用離線工具處理；啟動時自動遷移 VETO。

**Consequences**
- 好處：
  - S2 回到「出清整檔、成交即動帳」的既有語意；每天重發與黑名單往後推，只剩真正在途的情況；
  - 「哪張 S2 移動了哪批多少股」成為落檔事實。
- 壞處：
  - store 有第二份「合格批次」述詞，用 parity 測試綁住；
  - 新表會動到 X-14 的表名斷言；
  - claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169），所以 claim 之後當機會留下「executed 但沒有稽核」的列，判定為未動帳（多報方向）；
  - N-188 上線前，S2 成交是兩次評估之間帳冊變動的新來源，沒有揭露（風控 A-3 已書面接受，期限第三包）；
  - 群組 A 的 P-5(c) 殘留會更常發生。
- 不取代任何 ADR；補充 ADR-0035、0039，與 0034 無衝突（C-B6、C-B11 維持）。

---

## 4. N-177a 規格

### 4.1 範圍
- 分支：`fix/stock-desk-n177a-s2-fill`，從 product 開出。
- 程式改動只在 `app/playbook/store.py`，測試另計。範圍見 C3。

### 4.2 共用常數（只有一份定義；放在 store.py 模組層級的常數區，緊接 `BATCH_LEFT_PLANNED_SQL` 之後）
- 位置的解讀：M1-2「緊接在 `def settle` 之前」對模組層級常數照字面做不到，改讀為「同一個常數區、彼此相鄰、`#:` 註解指向 `PlaybookStore.settle`」。N-188 的 `BOOK_MOVING_SETTLEMENT_SQL` 也放在同一區，緊鄰這幾個常數。

```python
class S2FillEntry(NamedTuple):
    status: str
    action: str
    rule_id: str

#: N177-C4 / ADR-0035 補充五修正一 M1-2: the one definition of "an S2 judged
#: executed", which moves the book across batches in PlaybookStore.settle.
#: ``batch_no IS NULL`` is part of the entry. Both is_s2_fill and
#: s2_fill_entry_sql derive from it; no other literal may restate it.
S2_FILL_ENTRY = S2FillEntry(status="executed", action="sell", rule_id="S2")

def s2_fill_entry_sql(alias: str) -> str: ...
    # returns exactly:
    # f"{alias}.status = 'executed' AND {alias}.action = 'sell' AND "
    # f"{alias}.rule_id = 'S2' AND {alias}.batch_no IS NULL"
    # built from S2_FILL_ENTRY fields; assert alias.isidentifier()

def is_s2_fill(directive: Directive) -> bool: ...
    # status/action/rule_id equal S2_FILL_ENTRY fields and batch_no is None

#: N177-C5: same predicate as engine._symbol_average_cost (engine.py:213), alias b.
S2_ELIGIBLE_BATCH_SQL = "b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL"

FILL_MOVES_TABLE = "playbook_fill_moves"
FILL_MOVE_SOURCE_SETTLE = "settle"
FILL_MOVE_SOURCE_REPAIR = "repair"
```

- 表名的時限：dev-lead 若要改表名，必須在 N-177a PR 開出前通知 data-engineer，同步改探針常數。改名之後只能改這一處。

### 4.3 `settle` 的 S2 分支
- 只插入一個分支，位置在既有 missed 區塊之後、`if directive.status != "executed" or directive.batch_no is None:` 之前。
- 價格規則抽成私有 `_settle_price(directive, fill_price) -> Decimal`。表示式從現行 :1525-1526 逐字搬移（`fill_price` → `reference_price` → `Decimal("0")`），既有分支與 S2 分支共用，不得各寫一份。

```python
if is_s2_fill(directive):
    if directive_id is None:
        raise ValueError(...)   # before any write (N177-C8)
    self._settle_s2_fill(directive, price=_settle_price(directive, fill_price),
                         directive_id=directive_id)
    self._mark_schedule(directive)
    return
```

- `_settle_s2_fill` 的步驟（寫法比照 `commit_evaluation`，錯誤處理照 C-11）：
  1. `with closing(self._connect()) as conn`，`BEGIN IMMEDIATE`。
  2. 讀合格批次：`SELECT b.batch_no, b.remaining_shares FROM playbook_batches AS b WHERE b.symbol = ? AND {S2_ELIGIBLE_BATCH_SQL} ORDER BY b.batch_no ASC`。
  3. 分配，見 4.4。每一批以 `UPDATE playbook_batches SET remaining_shares = ?, status = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?` 寫入，新值在 Python 端算好。
  4. 現金，見 4.5。
  5. 寫稽核列，見 4.6。
  6. `COMMIT`。例外時 `if conn.in_transaction: ROLLBACK`，然後原樣 raise。
- `_mark_schedule` 在 commit 之後另開連線執行，與現行各分支相同（schedule 不屬帳冊）。

### 4.4 股數分配
- `left = directive.shares`。依 `batch_no` 遞增，每一批 `moved = min(remaining, left)`，`left -= moved`；`left == 0` 就停止。
- 新的 remaining 為 0 時，`status = 'closed'`；否則維持 `'open'`。
- 恆等式：Σmoved ≤ `directive.shares`，而且 Σmoved ≤ 合格批次合計。
- 不動的欄位：`shares`、`cost`、`entry_date`、`peak_close`、`p1_done`、`p2_done`、`p3_last_date`、`trailing_active`、`defer_count`、`missed_count`、`scheduled_date`、`entry_before_exit_on`。
- engine 的 `batch_closed` effect 繼續不使用（`FILL_DEPENDENT_EFFECTS`）。它的目標集合不檢查 cost，和 C5 在「cost 為 NULL 的 open 批次」上不同。N-177a 以股數定義（C5）為準，這是刻意的。

### 4.5 現金
- 只有 Σmoved > 0 時才寫：在同一個 conn 讀 `playbook_state` 的 `STATE_CASH`（沒有這個鍵時視為 `Decimal("0")`，與 `portfolio_state` 相同），以 `_write_state(conn, {STATE_CASH: str(cash + price × Σmoved)})` 寫回。
- 不新增 state 鍵。

### 4.6 稽核表 schema（`_SCHEMA` 末尾追加一條；DDL 以 f-string 由 4.2 的常數組成）

```sql
CREATE TABLE IF NOT EXISTS playbook_fill_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    directive_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    batch_no INTEGER,
    shares_moved INTEGER NOT NULL,
    price TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('settle', 'repair')),
    created_at TEXT NOT NULL,
    CHECK ((batch_no IS NULL AND shares_moved = 0)
        OR (batch_no IS NOT NULL AND shares_moved > 0))
)
```

- 每移動一批寫一列（`source='settle'`）。一股都沒移動時，寫恰好一列 `(batch_no NULL, shares_moved 0)`。
- 不設 UNIQUE、INDEX、TRIGGER，也不加 FK 宣告（N172-C9；`test_the_schema_has_no_unique_index` 會檢查 `_SCHEMA`）。重複寫入由 claim 防止。
- 時間欄名用 `created_at`，所以 `test_api_playbook_cap1_disclosure._playbook_tables` 的時間遮罩會自動涵蓋。
- `price` 存 `str(Decimal)`。`source='repair'` 只給離線工具用（第 6.9 節）。
- N-188 只讀 `directive_id`、`batch_no`、`shares_moved` 三欄（M1-2 第 1 點）。

### 4.7 ADR-0035 Decision 6／N172-C8 的範圍判定（交 tech-writer 以補充落檔，原文不改）
- 涉及的條文：Decision 6「`settle()` 零 diff（避開 0034 的 C-B6）」、6′「G1 不得改 `settle()`」、Consequences :183 與 :205、N172-C8（[TA2] 修訂版）。
- 判定：這些條文設的理由是 N-172a 當時與 N-168 並行修改 `settle` 的範圍與衝突問題，屬於 **N-172a 的範圍約束**，不是 `settle` 永久不得修改的架構決策。先例是補充四把 N172-C8 對 `settle_pending` 的限制判為 N-172a 範圍。
- 仍然有效、N-177a 必須遵守的不變式：
  - 不新增 `DirectiveStatus`；
  - 不做批次層級 claim，claim 仍逐列由 `claim_directive` 進行；
  - G1 的 SQL 零 diff；
  - 不寫 `missed`；
  - 帳冊只在 claim 成功之後才動；
  - C-B6 的 buy 行為零改動。
  由 N177-C2、C9 檢查。
- qa-reviewer 依本判定審 N-177a，不以 N172-C8 判 BLOCKING。

### 4.8 與 ADR-0040 Decision 13、14 的關係
- **Decision 13**：N-177a 必須是 N-190 release 之後的**下一個** release；中間不得夾其他功能 release，hotfix 除外。沒趕上時，(c) 依風控 A-2 條件一回復為 required，並觸發 [風控-N168] T3(b)。偵測閘門不變。
- **Decision 14 第 2 點**「不得新增任何改動 `playbook_batches` 股數或 cash 的路徑」：
  - 這一點出自 M1-3 第 5 點「給 ADR-0040 起草者的約束」，適用對象是 ADR-0040／N-190 的 build；目的是守住 X-3 的前提「帳冊股數只由 `settle` 改變」。
  - M1-2 第 5.1 點修正後的前提，已經明文把 N-177a 的 S2 分支與它的私有 helper 納入 `settle`。所以 N-177a 是在既有寫入者內修正，不是 Decision 14 第 2 點所說的新路徑。
  - 由此產生的約束：
    - (i) N-177a 的所有新寫入只能在 `_settle_s2_fill` 內（C3、T19）；
    - (ii) N-177a 不得併入 N-190。併入後 N-190 的 build 會照字面違反 Decision 14 第 2 點，所以這也是 C14 的理由之一；
    - (iii) 離線修復工具不在 app 內，由 C15、[風控-0040] M-1、(a-3) 規範。
- **Decision 14 第 3 點**：`_settle_pending` 零 diff。N-177a 本來就不改 service，不衝突。

### 4.9 ADR-0039 Decision 10 的修訂需求（群組 B 開工前，由 TA 出補充、tech-writer 落檔）
1. 「`batch_no` 為 NULL 的列不計（與 `settle()` 一致）」改為：
   - 第 k 批的事件 = (i) `batch_no = k` 的已成交逐批賣出，照 min／max 重放（不變），加上 (ii) `playbook_fill_moves` 中 `batch_no = k` 的列，股數照 `shares_moved` 套用，不重算。
   - 修正前的 S2 列沒有稽核列，計 0。這是事實，因為它們當時沒有動帳。
2. 排序鍵：(ii) 以所屬 S2 指令列的 `(settled_at, id)` 與 (i) 合併排序。`source='repair'` 的列以它自己的 `created_at` 排序；(B) 的誤判防護保證這些列之後沒有同批的已成交賣單，所以不會有次序歧義。
3. Options :83 的否決理由要重新論證：
   - 被否決的方案是「`settle()` 對所有賣出記錄移動股數」；M2 只記 S2 的跨批移動，逐批仍走重放，每一種事件只有一個來源；
   - C-B6 衝突已不存在：N-168 已合併，N-177a 不碰 buy 分支。
4. 群組 B 在 `_read_pending_exits` 的同一個 transaction 讀稽核表，QB-7 白名單由群組 B 的補充擴充（M1-4 第 2 點）。
5. 互動：S2 先關閉批次時，之後在途的 EMERGENCY 判定成交會是零移動（N2），群組 B 依「減少股數大於 0」排除它，與 P-5(c) 一致。

### 4.10 讀碼證明（回應風控 A-1 條件 2：批次被關閉後，在途的逐批 sell 結算會不會扣成負數或重複入帳）
- 依據 `store.py:1541-1556`（逐批 sell 分支）：
  - `moved = min(batch.remaining_shares, directive.shares)`：remaining 為 0 時 moved = 0，現金 +0；
  - `remaining = max(0, remaining − shares)`：結果為 0，不會是負數；
  - `status`：remaining 為 0 時是 closed，維持關閉。
  - 所以**不會扣成負數，也不會重複入帳**。
- 唯一副作用：P1／P2／P3 會在已關閉的批次上設 `p1_done`、`p2_done`、`trailing_active`、`p3_last_date`。這不影響股數或現金；engine 也只對 open 批次評估 S/P（engine.py:420），所以不會再發單。
- EMERGENCY 走同一個分支，service 會出 N2（service.py:1357-1362）。
- 殘留：非 EMERGENCY 的 S/P 在「批次存在但已沒有股數」時零移動、無聲。這是既有行為；N-177a 會讓它更常發生（S2 關閉批次時有在途 S/P）。列為送風控的 Q-c。
- 本證明成立與否由風控裁示。風控確認前，偵測工具把它當成誤判防護 G-c（一律列為需人工判讀）。

### 4.11 約束 N177-C1～C16（qa-reviewer 逐條檢查）

- **C1**：`app/playbook/engine.py` 零 diff。`<base>` 是 N-177a 最後一次 merge 進來的 product commit。
- **C2**：指令列：
  - 除 claim 既有的 UPDATE 外，不 UPDATE、不 DELETE；
  - 不新增 `DirectiveStatus`；
  - `claim_directive`、`BATCH_LEFT_PLANNED_SQL`、`batch_blocking_claim`、`_insert_directives` 零 diff；
  - 不新增 `pending_directives` 呼叫點（QB-7）。
- **C3**：改動範圍：
  - 只限 store.py 的以下部分：
    - (a) 模組 docstring（表的數量與清單）；
    - (b) 4.2 的常數與兩個函式；
    - (c) `_SCHEMA` 末尾追加一條 DDL；
    - (d) `settle`：抽出 `_settle_price`、插入 S2 分支、docstring；
    - (e) 新私有 helper `_settle_s2_fill`。
  - store.py 其餘函式零 diff，特別是 `commit_evaluation`、`_read_logged`、`read_in_flight`、`_read_exit_state`、`apply_effects`、`blacklist`、`save_batch`、`set_cash`、`get_batch`、`_mark_schedule`、`_MIGRATIONS`、`_init_schema` 本體。
  - service.py（含 `_lines`、`_settle_pending`）、wording.py、models.py、`app/api/**`、`app/data/**`、`app/services/**`：零 diff。
  - 對 `playbook_batches` 股數與 cash 的新寫入，只出現在 `_settle_s2_fill`。
- **C4**：進入條件就是 `S2_FILL_ENTRY`，SQL 形式逐字等於 `status='executed' AND action='sell' AND rule_id='S2' AND batch_no IS NULL`（含 alias 的版本由 `s2_fill_entry_sql` 產生）。
  - `settle` 的判斷只用 `is_s2_fill`；store.py 其他地方不得再寫 `'S2'`、`'executed'` 的條件字面（QB-18.5、18.14）。
  - 其他 `batch_no` 為 NULL 的列行為不變，含 missed S2。
- **C5**：合格批次 = 同 symbol 加上 `S2_ELIGIBLE_BATCH_SQL`（逐字 `b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL`），`ORDER BY b.batch_no ASC`。由 parity 測試 T7 綁住 `engine._symbol_average_cost`；store 不 import engine。
- **C6**：分配依 4.4，現金依 4.5，價格只走 `_settle_price`。只寫 `remaining_shares`、`status`、`updated_at`；不得用 `INSERT OR REPLACE` 或 `save_batch`。
- **C7**：同一筆 S2 的合格讀取、批次更新、現金讀改寫、稽核寫入，都在同一個 conn 的單一 `BEGIN IMMEDIATE` 內完成，錯誤處理照 C-11。持鎖期間沒有任何其他 I/O。
- **C8**：稽核表依 4.6：
  - `CREATE TABLE IF NOT EXISTS`；
  - 每一張修正後結算的 executed S2 至少寫一列，零移動也要寫 sentinel；
  - 其他規則不寫；
  - `_init_schema` 不回填舊 S2；
  - S2 的 `directive_id` 為 None 時，在任何寫入之前 raise `ValueError`。
- **C9**：既有行為與既有測試：
  - buy 分支的 C-B6 行為零改動；N-168、G1、N2、W-B3 的既有測試斷言零改動；
  - `test_a_missing_batch_row_is_not_refused` 的 (i)～(iii) 不改；
  - 既有測試只允許兩處修改：
    - (1) `test_playbook_exit_idempotency.py::test_the_exit_adds_no_column_table_or_state_key` 新增具名常數 `N177A_TABLES = frozenset({"playbook_fill_moves"})`，names 斷言改成聯集加上它；`PRE_N166_*` 與 `ADR0034_COLUMNS` 零 diff；
    - (2) 有 S2 成交的既有情境，若斷言原本釘住「S2 不動帳」的 bug，要逐條列在 PR 說明，交 qa 判定。
- **C10**：`settle` 的回傳型別不變（None），N-177b 才做加法；N2 的判斷與字面零 diff。
- **C11**：store.py 的 import 清單不新增 `app.playbook.engine`、`app.playbook.wording`。
- **C12**：零新字面，wording.py 零 diff。
- **C13**：SEAM golden 不得重錄；有差異依釐清二登記到 `tests/golden/seam/approved/<owner>.json`。
- **C14**：PR 與合併：
  - 獨立 PR，不得併入 N-190、N-188、N-189 的 PR（另見 4.8 (ii)）；
  - 若在 N-190 合併前開分支，合入 product 前必須 merge 含 N-190 的最新 product（merge，不得 rebase），之後重跑完整 CI 與 seam golden，由 qa 審 merge commit 的衝突解法；
  - 以 merge commit 合入 product；
  - release 位置依 4.8。
- **C15**：既有資料：
  - 偵測是部署閘門（風控 A-1 條件 1）：第 6 節的工具在 R2 停機時跑最後一次，結果附在 release 紀錄；
  - 結果大於 0 檔時，CEO 的逐檔選擇與 (B) apply 要在同一次停機內完成，新版開始服務之前；
  - 只能用離線工具（6.9）；(D)、(E) VETO；黑名單預設不改（A-5）。
- **C16**：第 4.12 節的 T1～T22 全部存在且綠燈（BLOCKING）。

### 4.12 測試清單 N177-T1～T22（全部 BLOCKING；用真實 `PlaybookStore`；property 測試用固定 seed，因為 repo 沒有 hypothesis）
- **T1**：單批 S2 成交：該批 remaining 為 0、closed；現金 += 開盤價 × 股數；一列稽核（`source=settle`，價格與股數正確）。
- **T2**：多批：依 `batch_no` 遞增全部關閉；現金一次入帳，等於 price × Σ；每批一列稽核。
- **T3**：價格連續 5 個交易日低於門檻，跑真實 service 流程（evaluate → settle，逐日）：
  - 日誌中只有一張 S2；
  - 第 2 天起，該檔沒有 S/P/S2 列；
  - 黑名單 `triggered_on` 等於第一張 S2 的資料日。
- **T4**：列股數小於合格合計（評估後有新批進場）：舊批先減，最新批不動或部分減；整檔合計 = 原合計 − shares；部分減股的批維持 open。
- **T5**：列股數大於合格合計（評估後較早批被 S1 減股）：Σmoved = 合格合計，現金只入 Σmoved。
- **T6**：同一次結算有 S1 與 S2，兩種 id 順序都測：
  - 不出現負數；
  - 現金 = Σ(各自實際移動股數 × 各自價格)；
  - S2 在前時，S1 移動 0 股、現金 +0。
- **T7**：parity：至少 500 組隨機 book（status ∈ planned／open／closed／skipped；cost ∈ None／0／正數；remaining 0..N；多個 symbol）：
  - 合格查詢的 Σremaining 等於 `engine._symbol_average_cost(該 symbol 的批次)[1]`；
  - 納入的批次集合與該函式計入的集合相同。
- **T8**：cost 為 NULL、planned、skipped、closed、remaining 為 0 的批次都不動，也不寫稽核。
- **T9**：交易中途注入失敗（測試 DB 加 `BEFORE INSERT ON playbook_fill_moves` 的 RAISE trigger）：
  - 批次、cash、稽核三者都不變，例外原樣拋出；
  - 該列維持 `settled=1／executed`（F2 殘留釘住，歸 N-169）。
- **T10**：重跑結算：第二次不 claim、不動帳、不增稽核列。
- **T11**：`/today` 與 `POST /settle` 的帳冊、cash、稽核列結果相同。
- **T12**：零移動：結算時已沒有合格批次 → 恰好一列 sentinel；cash 不變；`playbook_state` 的鍵集合不變。
- **T13**：S2 的 `directive_id` 為 None → `ValueError`，DB 全部不變。
- **T14**：schema：
  - 表存在；沒有 UNIQUE、INDEX、TRIGGER；
  - CHECK 會拒絕 `(NULL, 5)`、`(1, 0)` 與 `source='x'`；
  - `_init_schema` 執行兩次結果相同；
  - 已含 executed S2 的舊 DB 開啟後，稽核表為 0 列。
- **T15**：被移動的批次只有 remaining、status、updated_at 改變，4.4 列出的欄位都不變（含 `entry_before_exit_on`：C-B6 標示持續到 closed）。
- **T16**：有在途 EMERGENCY 時 S2 成交：之後 EMERGENCY 判定成交出 N2，N-171 區塊不再列出該批（P-5(c) 路徑釘住）。
- **T17**：較早的 S2 在兩次評估之間成交時，較晚的 S2 列不渲染 W-B2LS 家族。這是風控 A-3 釘住測試的前半，後半（出現 N-188 note）由 N-188 的 PR 擴充。
- **T18**：常數：
  - `s2_fill_entry_sql("s")` 逐字等於 C4 的文字（帶 alias s）；
  - `S2_ELIGIBLE_BATCH_SQL` 逐字等於 C5 的文字；
  - AST 檢查：store.py 中 `"S2"` 字面只出現在 `S2_FILL_ENTRY` 的定義。
- **T19**：寫入點（N188-T15 的前身）：`app/` 內新增的 `UPDATE playbook_batches` 與 `INSERT INTO playbook_fill_moves` 只出現在 `_settle_s2_fill`；`STATE_CASH` 的寫入只在 `set_cash`、`set_capital`、`_settle_s2_fill`。
- **T20**：SQL trace（比照 `test_playbook_settlement_g1._trace`）：S2 分支的所有寫入，都夾在同一條連線的 `BEGIN IMMEDIATE` 與 `COMMIT` 之間；沒有 `INSERT OR REPLACE INTO playbook_batches`。
- **T21**：qa-automation 的 F8 重現測試，expected 轉綠。N-177 補的重現測試在 N-177a 不變，屬 N-177b。
- **T22**：回歸：C9 列出的既有測試原樣綠燈。

### 4.13 QB（qa-reviewer，BLOCKING）
- **QB-1**：`git diff <base>..HEAD --stat` 只含 `app/playbook/store.py` 與 `tests/**`。
- **QB-2**：store.py 的 hunk 逐一對照 C3 的 (a)～(e)；列名的函式零 diff。
- **QB-3**：單一定義：
  - `'S2'`、`"S2"` 在 store.py 只有一處；
  - `remaining_shares > 0 AND b.cost IS NOT NULL` 只有一處；
  - `S2_FILL_ENTRY`、`S2_ELIGIBLE_BATCH_SQL`、`FILL_MOVES_TABLE` 在 `app/` 內只出現在常數區、`_SCHEMA`、`settle` 與它的 helper（M1-4 第 2 點白名單中 N-177a 的部分）。
- **QB-4**：T1～T22 存在且綠燈；T7 的 seed 固定、案例數至少 500。
- **QB-5**：既有測試的修改只限 C9。
- **QB-6**：SEAM golden 沒有重錄。
- **QB-7**：PR 說明寫明 4.7 的判定、4.8 的關係、release 位置、偵測閘門，並聲明不含 N-190 的程式碼。
- **QB-8**：合併方式依 C14；merge 之後跑完整 CI 與 seam；merge commit 的衝突解法經過審查。
- **QB-9**：Codex 第二意見（公司規定）。
- **QB-10**（release gate，devops-sre 負責，不在 PR 階段）：
  - 閘門探針結果附在 release 紀錄；
  - 大於 0 檔時，另附 CEO 逐檔裁示與 (B) apply 的時間（[風控-0040] M-1）。

### 4.14 已知殘留
- F2：claim 與 settle 分屬兩個 transaction（歸 N-169）。
- 舊的逐批 sell 分支：`set_cash` 與 `save_batch` 各開連線，並發時現金有遺失更新的可能。這是既有問題，不在本單（C3）。
- 4.10 的零移動 S/P 無聲（Q-c）。
- N-188 上線前的揭露缺口（A-3，期限第三包）。

---

## 5. N-177b 規格：找不到批次列時的結構化揭露

- **範圍**：store.py 的 `settle` 回傳值，service.py 的 `_settle_pending` 與結算 warnings，wording.py 加兩個常數。在 N-177a 合併之後開工。
- **行為**：
  - 帳冊行為不變：claim 成功、不動帳。
  - 補充一 S-1 不變：不拒絕 claim，不列入 unsettled。
- **判定**（只在 store 判定一次）：`settle` 改為回傳 `SettleOutcome(NamedTuple)`，欄位 `missing_batch_row: bool`，日後只能再做加法。
  - 為真的條件：`status == 'executed'`，而且 `action in ORDER_ACTIONS`，而且 `not is_s2_fill(directive)`，而且（`batch_no is None` 或 `get_batch` 回 None）。
  - 其他情況一律為假（含 S2 零移動、missed、非下單列）。
- **service**：
  - 收集 `missing_batch_row` 為真的列，依 action 分成 buy 與逐批 sell；
  - `rule_id == 'EMERGENCY'` 的列排除，因為 N2 已經揭露（service.py:1357-1362），不重複揭露（送風控 Q-b）。
- **位置**：結算 warnings 中，排在 SUMMARY → W-B3 → N2 之後，順序 buy 句 → sell 句。最終順序隨字面由風控確認。
- **字面**：**待 creative-lead 擬稿、風控定稿**。
  - 識別名暫定 `SETTLEMENT_UNBOOKED_BUY_NOTE`、`SETTLEMENT_UNBOOKED_SELL_NOTE`，另加一個項目格式常數。只放在 `wording.py`。
  - 可用的結構化欄位：symbol、batch_no（可能為 None）、shares、execution_date、rule_id。
  - 風控約束（A-2）：
    - buy 與逐批 sell 分開寫；
    - 只陳述「帳冊找不到所屬批次的紀錄，股數與現金都未因本筆變動」這個事實；
    - buy 那一支要說明：若在券商已成交，這些股數不在 S/P 評估範圍內，全部出清也不涵蓋；
    - 必含「本系統不下單」與「實際持股以你的券商回報為準」。
- **約束 N177b-C1～C8**：
  - C1：帳冊與 claim 的行為零改動；`claim_directive`、G1 零 diff；N188-T9 的絆線保持綠燈。
  - C2：`settle` 的回傳只做加法；既有呼叫點忽略回傳值也不受影響。
  - C3：`_settle_pending` 的 diff 只限接收回傳值與追加 warnings；取開盤價的方式零 diff（ADR-0040 Decision 14 第 3 點的目的仍然成立）。
  - C4：store 不 import wording。
  - C5：字面在風控逐字定稿前不得合併；PR 用程式從風控原檔逐字比對。
  - C6：N2、W-B3、SUMMARY 的字面與判斷零 diff。
  - C7：SEAM golden 依 approved 登記，不重錄。
  - C8：獨立 PR，以 merge commit 合併；可以搭 R2 上線，但不得延後 N-177a。
- **測試 N177b-T1～T8**：
  - T1：buy 的批次列不存在（`batch_no` 為整數，以及為 None）：句子恰好一次，帳冊不變；`test_a_missing_batch_row_is_not_refused` 的 (i)～(iii) 不改，只追加斷言。
  - T2：逐批 sell（S1、P1）找不到批次 → sell 句。
  - T3：EMERGENCY 找不到批次 → 只有 N2，沒有本句。
  - T4：S2（含零移動）永遠不觸發。
  - T5：missed 列永遠不觸發。
  - T6：同一次結算 buy 與 sell 都有：順序正確。
  - T7：重跑結算：不重複出現。
  - T8：`/today` 與 `POST /settle` 結果相同。

---

## 6. 唯讀偵測與回溯工具規格

### 6.1 定位
- 檔案：`apps/stock-desk/backend/scripts/n177_n190_backtrack_probe.py`；測試：`tests/test_n177_n190_backtrack_probe.py`。
- 負責：data-engineer。SQL 對照本規格由 TA 抽查。
- 用途：
  - (1) N-177：偵測與部署閘門（風控 A-1）；
  - (2) CEO #106：N-190 期間的回溯清單（風控 B-5 的範圍建議、ADR-0040 R-8）。
  - 輸出只有事實，不給結論，也不給建議。
- 不修改 `scripts/n172_duplicate_probe.py`。它是 CEO #85 的證據檔。
- PR 只動 `scripts/` 與 `tests/`，與 N-190、N-177a 都沒有程式衝突，可以隨時審查合併。

### 6.2 CLI
- `--db-path PATH`：必填，沒有預設值，也不讀環境變數當預設。必須是 DB **複本**。
- `--out-dir DIR`：必填，而且必須已存在。工具在裡面寫 `report.md` 與 `report.json`，以 `open(..., "x")` 建檔，檔案已存在就拒絕執行。
- `--since YYYY-MM-DD`：選填，只套用在 N-190 類別。預設是所有批次中最早的 `entry_date`；coordinator 可以依 devops-sre 查到的 ADR-0009 D-4 上線日，給 CEO 建議值。
- `--until YYYY-MM-DD`：選填，預設本機日期。
- `--previous-json PATH`：選填。與前一次的 `report.json` 逐檔比對，用於 R2 停機時的閘門那次執行。
- stdout 只印 ASCII 摘要：版本、閘門檔數、兩個輸出檔的路徑。
- exit code：
  - 0：完成（不論列數多少）；
  - 2：無法讀取 DB 或 DB 被鎖住；
  - 3：執行前後 DB 雜湊不同；
  - 4：拒絕執行（指向正式 DB、輸出檔已存在、out-dir 是正式資料夾）。

### 6.3 安全約束 S1～S11（全部要有測試）
- **S1**：以 `file:<path>?mode=ro` URI 開啟，加上 `PRAGMA query_only=ON`，timeout 5 秒；檔案不存在時拒絕，不建立。
- **S2**：只送 SELECT。所有 SQL 都是模組常數，以 SELECT 或 WITH 開頭，只用參數綁定。AST 檢查沒有 `executescript`、`commit`、`ATTACH`、`PRAGMA` 寫入（除 S1 那一句）。
- **S3**：只用 stdlib，不 import app。import 白名單：argparse、hashlib、json、os、sqlite3、sys、io、re、dataclasses、datetime、decimal、pathlib、collections.abc、contextlib、typing。測試在暫存 cwd 以 `python -I` 的 subprocess 實跑。
- **S4**：不連網：AST 確認沒有 socket、ssl、http、urllib、asyncio、subprocess 等模組。
- **S5**：執行前後各算一次 DB 檔的 SHA-256，兩次都寫進報告；不一致就 exit 3。
- **S6**：拒絕正式路徑：`--db-path` 與 `<backend>/data/stock-desk.db`，或與環境變數 `STOCK_DESK_DB_PATH` 的值（只讀來比對）是同一個檔案（samefile）時，exit 4。`--out-dir` 是正式 data 資料夾時，同樣 exit 4。
- **S7**：只寫 `--out-dir` 裡的兩個新檔，沒有其他寫入。
- **S8**：只有事實：報告不得含「建議」「應」「務必」「盡快」「否則」「安全」「對應」。唯一例外是沿用 n172 的固定標籤「需人工判讀」。用測試掃描輸出。
- **S9**：不讀 `.env`，不印任何環境變數的值。
- **S10**：決定性：同一個 DB 產出相同報告（`run_at` 除外）；JSON 用 sorted keys，金額以字串表示。
- **S11**：常數複本必須有對齊測試，測試可以 import app：
  - `INDEX_GAP_MARKER` 等於 `wording.INDEX_GAP_DEFER_NOTE.split("{status}")[0]`；
  - S2、合格批次、`FILL_MOVES_TABLE` 等於 store 的常數；
  - 參數預設值（s1_ratio、s1_defense_ratio、s2_ratio）等於 `RuleParams` 的預設；
  - `DEMO_SOURCE` 等於 engine 的常數。

### 6.4 輸出格式
- `report.md`：
  - 標頭：版本、腳本 SHA-256（LF 正規化）、db_path、執行前後的 DB 雜湊、run_at_utc、since／until、各表是否存在（`playbook_fill_moves` 存在，表示這個 DB 已被 N-177a 版本開啟過）；
  - 摘要表：每一類的筆數；
  - 「N-177 部署閘門：受影響標的 X 檔（X > 0 時需要 CEO 逐檔裁示）」；
  - 各類別的 Markdown 表，中文欄名，就是下面各類列的欄位。
- `report.json`：
  - `{schema_version: 1, meta, gate: {n177_affected_symbols, ceo_decision_required}, n177: {affected, blacklist, missing_batch_rows, pending_s2, inflight_on_affected}, n190: {stop_loss_candidates, held_summary, m1_unevaluated_days, defer_counts, skipped_batches}, limitations: [代碼], diff_vs_previous}`；
  - 每一筆都帶 id，方便 TA 與風控追查。

### 6.5 類別與判定

共用 SQL：
```sql
-- eligible batches now (= S2_ELIGIBLE_BATCH_SQL)
SELECT symbol, batch_no, entry_date, cost, remaining_shares FROM playbook_batches AS b
WHERE b.status = 'open' AND b.remaining_shares > 0 AND b.cost IS NOT NULL
ORDER BY symbol, batch_no;
-- executed S2 rows without audit (NOT EXISTS clause only when the table exists)
SELECT d.id, d.symbol, d.shares, d.data_date, d.execution_date, d.created_at,
       d.settled_at, d.settled_open_price
FROM playbook_directives AS d
WHERE d.status = 'executed' AND d.action = 'sell' AND d.rule_id = 'S2'
  AND d.batch_no IS NULL AND d.settled = 1
  AND NOT EXISTS (SELECT 1 FROM playbook_fill_moves AS m WHERE m.directive_id = d.id)
ORDER BY d.symbol, d.execution_date, d.id;
```

**N177-A 受影響標的（部署閘門）**
- 判定：一張無稽核的 executed S2 列 s，若該 symbol 現在有合格批次滿足 `entry_date IS NULL OR entry_date < s.execution_date`（L 述詞），則 s 成立。標的至少有一張成立的 S2，就算受影響。
- 「第一張 S2」= 成立的 S2 中 `(execution_date, id)` 最小的那一張。
- 欄位：
  - 標的；
  - 第一張 S2 的 id、依據資料日、預定執行日、股數、成交判定價、settled_at；
  - 之後的 executed S2 張數；
  - 待結算的 S2 張數；
  - 合格批次（批次：剩餘股數）與合計；
  - 判讀（「可試算」或「需人工判讀：理由」）；
  - 試算分配（批次 → 股數）與「試算回補現金 = 價格 × Σ」。試算用 N-177a 的分配規則（4.4）。
- 誤判防護（任一條成立，就不給金額）：
  - **G-a**：同 symbol 有其他已成交的 buy 或 sell，`execution_date >= 第一張 S2.execution_date`，而且不是 S2 進入條件的列：
    ```sql
    SELECT id, rule_id, action, batch_no, shares, execution_date FROM playbook_directives
    WHERE symbol = ? AND settled = 1 AND status = 'executed' AND action IN ('buy','sell')
      AND id <> ? AND execution_date >= ?
      AND NOT (rule_id = 'S2' AND action = 'sell' AND batch_no IS NULL)
    ```
  - **G-b**：`total_deploy_set_at` 不存在、無法解析，或晚於第一張 S2 的 settled_at（之後跑過 REBALANCE 或重設資金）。
  - **G-c**（風控 A-1 條件 2，required）：合格批次上還有未結算的逐批賣單：
    ```sql
    SELECT id, rule_id, batch_no, shares, execution_date FROM playbook_directives
    WHERE symbol = ? AND settled = 0 AND status = 'pending' AND action = 'sell'
      AND batch_no IS NOT NULL AND rule_id <> 'S2'
    ```
    篩選 `batch_no` 屬於合格批次的列。風控接受 4.10 的證明之前，這一條一律成立就是誤判防護；接受之後改成只當事實欄，要另提 PR。
  - **G-d**：第一張 S2 的 `settled_open_price` 缺漏、無法解析，或不是有限值。
  - **G-e**：有合格批次的 `entry_date` 為 NULL。
  - **G-f**：第一張 S2 的股數不等於「合格批次中 `entry_date` 早於它的批次」的合計（保守處理）。
  - **G-g**：該 symbol 已經有任何稽核列，表示 N-177a 已在這個 DB 上運作過。
- 黑名單只列出，不改（A-5）。

**N177-B 重發次數**：每檔 executed S2 與 pending S2 的張數，以及最早、最晚的預定執行日。併在 A 的表內，未受影響的標的另列一張表。

**N177-C 黑名單**
- 讀 `SELECT symbol, triggered_on, until, rule_id FROM playbook_blacklist`，對照第一張 S2 的依據資料日。
- 「相差交易日數」用快取中 `^TWII`（market TW）的 bar 日期計數，屬近似值。快取沒有指數時，改用所有 TW 標的 bar 日期的聯集，並標明。

**N177-D 帳冊找不到所屬批次的成交列**（N-177b 類，不算閘門）：
```sql
SELECT d.id, d.symbol, d.batch_no, d.rule_id, d.action, d.shares, d.execution_date,
       d.settled_open_price FROM playbook_directives AS d
WHERE d.status = 'executed' AND d.settled = 1 AND d.action IN ('buy','sell')
  AND NOT (d.rule_id = 'S2' AND d.action = 'sell' AND d.batch_no IS NULL)
  AND (d.batch_no IS NULL OR NOT EXISTS (SELECT 1 FROM playbook_batches AS b
       WHERE b.symbol = d.symbol AND b.batch_no = d.batch_no))
ORDER BY d.id
```
- 欄位包含「股數 × 價（未入帳）」。EMERGENCY 列標註「N2 已揭露」。

**N177-E 待結算的 S2**：`rule_id='S2' AND action='sell' AND settled=0 AND status='pending'`。
- 事實註記：N-177a 上線後，這些列會依新邏輯結算。若 (B) 已經關閉幻影批次，它們會是零移動。

**N177-F 受影響批次上的在途賣單**：G-c 的明細。

**N190-A 停損未評估的候選日**（範圍 since～until）
- 持有判定：批次在日期 D 被帳冊視為持有，條件是 `entry_date <= D`，而且「批次股數減去 `execution_date <= D` 的已成交逐批賣出（照 min／max 重放）與 S2 稽核移動」之後大於 0。修正前的 S2 不計。
- 收盤價：`price_bars_cache` 中 `market='TW'`、symbol 在 D 的 close；`source` 是 demo 的 bar 排除並計數。
- 參數：與 `active_params` 同一個選取規則（`effective_date <= D` 中，`effective_date DESC, version DESC` 的第一筆），解析 payload 的 s1_ratio、s1_defense_ratio、s2_ratio；沒有任何列時用複本預設值（S11）。
- 指令列事實：
  - `SELECT symbol, batch_no, rule_id, action, data_date, MIN(created_at) FROM playbook_directives WHERE data_date BETWEEN ? AND ? GROUP BY symbol, batch_no, rule_id, action, data_date`；
  - 當日系統有評估寫入：存在任一列 `data_date = D`，EMERGENCY 與 REBALANCE 除外；
  - 當日第一次寫入時間 = 這些列的 MIN(created_at)。
- 快取事實：該 bar 的 `fetched_at <= 當日第一次寫入時間` 時，記為「評估時快取已有這根 bar」；否則記為「無法判定」（bar 列會被覆寫，fetched_at 可能較晚）。時間都以 UTC aware datetime 比較；無法解析就記為無法判定。
- 列入條件（只列事實，不寫「應觸發」）：
  - 「低於 S1 一般門檻」：close < cost × s1_ratio，而且當日沒有本批的 S1 列，也沒有本檔的 S2 列；
  - 「僅低於 S1 防守門檻」：cost × s1_ratio ≤ close < cost × s1_defense_ratio，而且當日沒有同樣的列；附註「當日防守狀態無法回溯」；
  - 「低於 S2 門檻」（整檔）：close < 持有合格批次在 D 的加權均成本 × s2_ratio，而且當日沒有本檔 S2 列。
- 欄位：標的、批次（S2 時寫「整檔」）、資料日、收盤、成本或均成本、收盤 ÷ 成本、門檻值、列入類別、當日本檔有無任何指令列、當日系統有無評估寫入、評估時快取是否已有這根 bar、參數版本。
- 另附 held_summary：每檔的帳冊持有交易日數、有本檔指令列的日數、沒有本檔指令列的日數。

**N190-B M1 未評估的日子**
```sql
SELECT id, symbol, batch_no, rule_id, action, data_date, execution_date, created_at, rule_summary
FROM playbook_directives
WHERE (rule_id = 'M1' AND action = 'defer')
   OR (rule_id = 'R3' AND action = 'skip' AND instr(rule_summary, ?) > 0)   -- ? = INDEX_GAP_MARKER
```
- 指數狀態：從 rule_summary 中 marker 之後到「）」為止截取。
- 依 data_date 分組。欄位：資料日、預定執行日、指數狀態、順延批次數、跳過批次數（重複 K1 以不同的 `(symbol, batch_no, execution_date)` 去重）、評估時快取是否已有 `^TWII` 在 D 的 bar（fetched_at 對照當日第一次寫入時間）。
- 另印 `playbook_state` 的 `fast_market_measured_on`、`defense_active`、`defense_since` 現值。

**N190-C 累計的 R 順延次數**
- 每批：狀態、`defer_count` 現值；M1 順延列數（以不同的 execution_date 計），其中指數狀態為 cached_stale 的數量；R2 順延列數；R3 跳過列。
- 「M1 順延佔比」= M1 順延 ÷（M1 + R2）。

**N190-D 被跳過的批次**
- `playbook_batches.status='skipped'`，配對該批的 R3 跳過列。
- 原因類別：rule_summary 含 marker 時是「指數缺漏順延累計」，否則是「其他（R2 不追價順延或 T+1 未成交累計）」。
- 另列該批的 M1 順延數，以及其中 cached_stale 的數量。

**diff_vs_previous**（有 `--previous-json` 時）
- 以 `(symbol, 第一張 S2 id)` 為鍵，比對判讀、誤判防護與試算。
- 不同的列標「與前次不同」，CEO 前次的選擇不沿用到這些列。

### 6.6 已知限制（報告中以代碼列出）
- **L1**：N-190 修正前沒有逐次評估紀錄，warnings 也不落檔。「評估了但沒有規則命中」與「沒有評估」無法區分；只有「已越過門檻、但當日沒有列」能強烈推定未評估（或當天沒開 `/today`）。
- **L2**：P 系列（停利、移動停利）與 R1 進場不重算，所以不列。
- **L3**：當日防守狀態無法回溯，S1 只能分成「一般門檻」與「僅防守門檻」兩種。
- **L4**：指數狀態只記在 M1 順延列上，也就是排程日、正常模式、該檔有 planned 批次的日子。其他日子 M1 是否評估無法回溯。
- **L5**：`price_bars_cache` 每根 bar 只留最新一版，fetched_at 會被覆寫，所以「評估時快取已有」只能單向證明。
- **L6**：持有區間是以已成交賣單重放推算的；N-166 之前的重複列會造成扭曲，請搭配 n172 探針一起看。
- **L7**：黑名單相差的交易日數是用快取 bar 日期近似計算。
- **L8**：複本只反映複製當下的狀態，部署閘門以 R2 停機時的那次執行為準。
- **L9**：試算回補假設使用者已照第一張 S2 在券商賣出（R10）。是否屬實只有券商對帳單能確認。
- **L10**：demo 來源的 bar 不計入，只計數。
- **L11**：時區：created_at、settled_at、fetched_at 是 UTC ISO；data_date 是台北交易日。只比較時間先後，不換算日界。

### 6.7 測試（data-engineer）
- fixture DB 用真實的 `PlaybookStore` 與 `PriceBarCache` 寫入（測試可以 import app），涵蓋：
  - 每一類的正例與反例；
  - G-a～G-g 各一例；
  - 有、沒有 `playbook_fill_moves` 兩種 DB；
  - 沒有 `^TWII` 時的退回處理。
- 也要測：S1～S11、exit code 2、3、4、`-I` 實跑、`report.json` 的 schema、決定性（跑兩次比對）、`--previous-json` 的 diff。

### 6.8 給 CEO 的執行步驟（Windows PowerShell；原生 dev-up 路徑）

第一次（現在，給 CEO 先看）與第二次（N-177a 上線停機時，是部署閘門）步驟相同。第二次由 coordinator 通知時間。

```powershell
# 1. Stop stock-desk: close the backend, scheduler and frontend windows opened by dev-up.bat.
# 2. Make a copy (copy .db and, if present, -wal / -shm together)
cd C:\path\to\AICompany\apps\stock-desk\backend
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$dst = "$HOME\stock-desk-probe\$stamp"
New-Item -ItemType Directory -Path $dst | Out-Null
Copy-Item .\data\stock-desk.db $dst\
Get-Item .\data\stock-desk.db-wal, .\data\stock-desk.db-shm -ErrorAction SilentlyContinue |
  Copy-Item -Destination $dst\
# 3. (First run only) dev-up.bat may be started again now; the copy is independent.
#    (Gate run at the N-177a release) keep the service stopped until coordinator says so.
# 4. Run against the copy
uv run --no-sync python -I -X utf8 scripts\n177_n190_backtrack_probe.py `
  --db-path "$dst\stock-desk.db" --out-dir "$dst"
#    gate run: add  --previous-json "<first run folder>\report.json"
# 5. Read the report
notepad "$dst\report.md"
```

- Docker 路徑：在 `apps\stock-desk` 執行 `docker compose stop`，再執行
  `docker run --rm -v stock-desk-data:/data -v "${dst}:/backup" alpine sh -c "cp /data/stock-desk.db* /backup/"`；
  第一次執行可以接著 `docker compose start`，然後照第 4 步。
- 報告內含持股與現金，屬私人資料：
  - 留在 CEO 本機，不 commit 進 repo；
  - CEO 把 `report.md` 交給 coordinator，轉 TA 與風控；
  - `work/` 只記摘要筆數，除非 CEO 同意記更多。
- 錯誤處理：
  - exit 2：DB 被鎖住，請確認服務已停止；
  - exit 4：指向正式 DB，請改指向複本；
  - 其他情況把畫面截給 coordinator。

### 6.9 (B) apply 工具的預定約束（只在閘門大於 0、且 CEO 對至少一檔選 (B) 時，才由 TA 另出 spec）
- 離線、服務已停止；先備份；以 dry-run 對複本執行，結果必須與閘門報告的試算一致（指紋相同）；CEO 逐檔書面確認（symbol、第一張 S2 id、金額）之後才 apply。
- 單一 `BEGIN IMMEDIATE`：
  - 依 4.4 關閉批次、現金加上試算金額；
  - 稽核列 `source='repair'`，`directive_id` 為第一張 S2 的 id；
  - 不動任何指令列（R16，(D) VETO）；
  - 黑名單除非 CEO 逐檔明確核可，否則不改（A-5）。
- 稽核表必須由新版 store 的 `_init_schema` 建立（單一 DDL）：停舊版 → 備份 → 一次性建立新版 schema、不提供服務 → apply → 啟動新版。
- 工具是否可以 import `app.playbook.store`（共用常數與 DDL），在該 spec 決定。傾向只允許這一個模組。
- 冪等：該 `directive_id` 已有稽核列時拒絕；誤判防護與探針相同。
- release 紀錄要寫 apply 的時間（[風控-0040] M-1）。不得放進 `_init_schema` 或啟動流程（(E) VETO）。

---

## 7. 時序、合併順序與衝突熱點

**順序**
1. **現在**：
   - data-engineer 做偵測工具（只動 scripts 與 tests），審查通過後就可以合入 product，CEO 跑第一次；
   - dev-lead 可以另開 N-177a 分支，但不得把 N-177a 放進 `fix/stock-desk-n190-usable-cache`；
   - qa-automation 做 F8 與 N-177 補的重現。
2. **N-190**：P-A 與 P-B 同一次 merge 進 product → release R1（Decision 11、13 的前置通知照常）。
3. **N-177a**：merge 含 N-190 的最新 product（merge，不 rebase）→ 完整 CI 與 seam → 審查 → 以 merge commit 合入 → release **R2**，必須是 R1 的下一個 release。
4. **R2 停機**：
   - 跑閘門探針；
   - 0 檔：直接部署；
   - 大於 0 檔：CEO 逐檔裁示 → (B) apply → 部署；選 (A) 的標的，(c) 必須在下一個 release 上線，在那之前以探針清單當過渡。
5. **N-177b**：字面定稿後合併，可以搭 R2，也可以更晚，不擋 N-177a。
6. **第三包**（N-188、N-189 D1／D2、W-B2LS 回審、B-3 的 EMERGENCY 缺口）：緊接 R2。N-188 引用 N-177a 的常數（M1-2 第 4 點「N-177a 先合」那一支）。
7. **群組 B**：開工前先落檔 4.9 的補充。
8. **tech-writer**：ADR-0041（或 ADR-0035 補充）、ADR-0035 的 4.7 判定、ADR-0034 補充三第六節 Consequences 的補充（A-4 (a)）。

**與 N-190 的衝突熱點**
- 依 ADR-0040 Decision 9 推定。N-190 worktree 目前的 store.py 還沒有記號表，實際 diff 尚未看到。

| 檔案／位置 | N-190 | N-177a | 解法 |
|---|---|---|---|
| store.py `_SCHEMA` 末尾 | 新增記號表 | 新增 `playbook_fill_moves` | 兩條都保留，N-190 在前 |
| store.py 模組 docstring 的表清單 | 可能修改 | 修改 | 兩個表都列進去 |
| store.py 常數區 | 記號的 kind、表名常數 | 4.2 的常數 | 各自成段，不交錯 |
| `test_playbook_exit_idempotency.py` names 斷言 | 加記號表 | 加 `N177A_TABLES` | 各用具名常數做聯集；`PRE_N166_*` 零 diff |
| `test_the_schema_has_no_unique_index` | 不得有 UNIQUE | 不得有 UNIQUE | 兩邊都要遵守 |
| `tests/golden/seam/approved/<owner>.json` | 登記 | 可能登記 | 條目取聯集，不重錄 |
| `commit_evaluation`、`EvaluationCommit`、`_read_logged` | 修改 | 零 diff | 不衝突 |
| engine.py | `is_usable` 加 5 個呼叫點 | 零 diff | 不衝突；T7 只用 `_symbol_average_cost` |
| service.py `_settle_pending` | 零 diff（D14.3） | 零 diff | 不衝突；N-177b 在 R1 之後才改 |

---

## 8. CEO 決策點
- **D-1（唯一必要）**：R2 停機時，閘門偵測大於 0 檔，就要逐檔在 (B)（依第一張 S2 回補、用券商對帳單確認）與 (A)（只對未來生效，掛 (c) 揭露）之間選。沒有預設選項（風控 A-1）。
  - 標為「需人工判讀」的標的，沒有試算金額：CEO 可以選 (A)，或提供券商資訊，由 TA 逐案評估。
  - G-b 的情況，另外決定是否重跑 TOTAL_DEPLOY。
- **不需要決策的項目**：
  - 修正本身；
  - 偵測為 0 檔的情況；
  - 黑名單預設不改。只有 CEO 主動要求縮短時，才需要逐檔書面核可（A-5）；
  - N-190 回溯清單預設不修復（R-8）。CEO 若要處理任何一項，另外開單。

## 9. 送風控確認
- **Q-a**：4.10 的讀碼證明是否成立，A-1 條件 2 的例外能不能適用。確認前，G-c 維持誤判防護。
- **Q-b**：N-177b 的 sell 句排除 EMERGENCY，以 N2 為準，避免重複揭露。
- **Q-c**：非 EMERGENCY 的 S/P 在「批次存在但已沒有股數」時零移動、無聲。這是既有行為，N-177a 會讓它更常發生。要擴入 N-177b，還是併入第三包的 D1？
- **Q-d**：探針的固定欄名與標籤屬內部營運工具的事實欄位，請確認不需要逐字定稿；「需人工判讀」沿用 n172 的例外。
- **Q-e**：A-3 的期限「第三包緊接 N-177 之後」，讀作「緊接 N-177a 之後」，N-177b 不擋第三包。
- **Q-f**：G-f（股數不一致就列為人工判讀）是保守方向，請確認接受。

## 10. 交接
- dev-lead：N-177a（第 4 節）；N-177a 合併、字面定稿之後做 N-177b（第 5 節）。
- data-engineer：偵測工具（第 6 節），現在開工。
- qa-reviewer：N177-C1～C16、QB-1～QB-10、N177b-C1～C8；Codex 第二意見。
- qa-automation：F8 與 N-177 補的重現。
- devops-sre：R2 的停機順序（6.8、6.9）、release 紀錄（QB-10、M-1）。
- tech-writer：ADR-0041 落檔、4.7 的判定、A-4 (a) 的 Consequences 補充；群組 B 的補充等 TA 出稿。
- creative-lead → 風控：N-177b 的兩句。

---
（coordinator 2026-11-07 落檔：tech-architect 回報 code block 逐字轉存。coordinator 定案（CEO 可推翻）：第 3 節草案另立 ADR-0041（proposed），由 tech-writer 落檔。）

## 修訂一（tech-architect，2026-11-07；回應風控 RC-1～RC-10）

- 依據：[風控-177R] `work/reviews/2026-11-07-N177實作規格審查與C6至C10確認-風控.md`
- 程式依據：product/stock-desk checkout（同本檔第 6 行），只讀，未執行。行號以內容定位。
- 本修訂取代本檔對應段落；沒提到的段落維持原文。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀；標 [待風控] 的需要風控再審。

### 1. RC-1：並發結算的機制（擋 N-177a 合併）

#### 1.1 盤點：會以過時讀值覆寫批次或現金的寫入者
讀碼盤點 store.py 對 `playbook_batches` 與 `STATE_CASH` 的所有寫入（`app/` 內沒有其他模組寫這兩者）：

| # | 寫入者 | 讀寫方式 | 會碰到 S2 動過的批次嗎 | 並發下的結果 |
|---|---|---|---|---|
| W1 | `settle` 逐批 sell（`get_batch` → `set_cash(portfolio_state()…)` → `save_batch`） | 三個呼叫各開連線；整列 `INSERT OR REPLACE` | 會（open 批次） | RC-1：批次復活；現金重複入帳，或抹掉別筆入帳 |
| W2 | `settle` missed 區塊（`get_batch` → `save_batch(missed_count+1)`） | 同上，整列 | 會（S／P／EMERGENCY 的 missed 列，所屬批次是 open） | 批次復活 [TA 補] |
| W3 | `settle` 逐批 buy（`get_batch` → `_exit_stamp` → `set_cash` → `save_batch`） | 同上 | 批次不會（G1 保證 buy 只動 planned，S2 只動 open）；現金會 | 抹掉並發 S2 的入帳（現金少記）[TA 補] |
| W4 | `roll_peak_closes`（`list_batches` → 逐批 `save_batch`），`/today` 結算後執行 | 整列 | 會（只處理 open） | 批次復活 [TA 補] |
| W5 | `apply_effects` → `_update_batch`（`trailing_on`） | `get_batch` → 整列 | 會（engine 只對 open 批次發 trailing_on，engine.py:596、:610） | 批次復活 [TA 補] |
| W6 | `apply_effects` 的 `defer_reset`（`list_batches` → `save_batch`） | 整列 | 會（buy 成交不會把 `defer_count` 歸零，open 批次可能非 0） | 批次復活 [TA 補] |
| W7 | `apply_effects` → `_update_batch`（`defer_increment`、`batch_skipped`） | 整列 | `/today` 走不到：service 先濾掉 `LINE_BOUND_EFFECTS`，改在鎖內由 `_apply_bound_effects` 欄位化寫入 | 一併欄位化，不留整列寫入點 |
| W8 | `rebalance` → `set_capital(cash=portfolio.cash, …)`（service.py:1538 讀、:1612 寫） | 鎖外讀現金、整值寫回 | 現金會 | 抹掉並發結算的入帳或扣款（R-1′，見 1.6） |
| W9 | `confirm_rules` → `set_capital(cash=capital)` | 使用者宣告資金，覆寫就是它的語意 | — | 不屬競態（見 1.6） |
| — | `_apply_bound_effects`、`commit_emergency_exit` | 鎖內、欄位化 | — | 沒有問題 |

結論：W1 不是唯一一處。W2、W4～W6 會造成同樣的實害（被 S2 關閉的批次復活），W3 會抹掉 S2 的入帳。只修 W1 不滿足 RC-1 第 1 點的「結果」。

#### 1.2 方案比較

| 方案 | 內容 | 改動範圍 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|---|
| R-α | (i) `settle` 的逐批 buy／sell 改成：同一 conn、單一 `BEGIN IMMEDIATE` 內「讀批次 → 讀現金 → 計算 → 只 UPDATE 本分支的欄位 → 現金讀改寫」；missed 改成單一句 `missed_count = missed_count + 1`。(ii) W4～W7 改成欄位化 UPDATE，不再整列寫入 | 只有 store.py；service、engine 零 diff | SQLite 寫鎖跨執行緒、也跨行程；與 `commit_evaluation`、`commit_emergency_exit`、`_settle_s2_fill` 同一模式；可以用 SQL trace 檢查 | 動到 buy 分支的實作（C-B6 行為不變，程式碼要改）；C3 擴大；`/today` 有成交時多幾個短交易 | 中低：行為等價由 T27 差分測試綁住 | **採用** |
| R-α′ | 只修 W1 | 最小 | diff 最小 | W2、W4～W6 仍會復活批次；W3 仍會抹掉 S2 入帳 | 不滿足 RC-1 第 1 點 | 否決 |
| R-β | store 模組層級的 `threading.Lock`：`settle` 全程、`roll_peak_closes`、`apply_effects` 都持鎖 | store.py，各函式外面包一層 | 舊分支本體可以零 diff | 只在單一行程內有效。現況 uvicorn 是單 worker（compose、Dockerfile、dev-up 都沒有 `--workers`），scheduler 也不碰 playbook，但這只是部署假設，沒有東西強制；在鎖外新增呼叫點就破功；SQL 層看不出來，qa 無法從 trace 檢查 | 中 | 否決 |
| R-γ | service 層序列化（`_settle_pending` 整段，或 `evaluate_today`／`settle_on_request` 整段持鎖） | service.py | 概念簡單 | 違反 ADR-0040 Decision 14 第 3 點與 C3；鎖會跨過網路載入 bars，`/today` 互相排隊；同樣只限單一行程；結算以外的 W4～W6 沒蓋到 | 高 | 否決 |
| R-δ | 樂觀並發：`save_batch` 帶版本（`updated_at`）比對，失敗就重試 | models.py（`BatchState` 沒有 updated_at）、store 的所有呼叫者 | 不持鎖 | 要動 models 與所有呼叫者；重試邏輯要逐一設計；超出範圍 | 高 | 否決 |
| R-ε | 用 SQLite trigger 擋「closed → open」 | `_SCHEMA` | 不動程式 | `INSERT OR REPLACE` 是先刪再插，UPDATE trigger 抓不到；N172-C9／T14 不准 trigger；擋不住現金重複 | 高 | 否決 |

結論：N-177a 範圍內做得到（只動 store.py），所以不提出殘留分析。1.6 的 R-1′、R-2′ 是 RC-1 以外的相鄰問題，另附分析。

#### 1.3 R-α 規格

**(1) `settle` 的結構（修訂 4.3）**
```python
if is_s2_fill(directive):
    ...                                    # unchanged from 4.3
if directive.status == "missed" and directive.batch_no is not None:
    self._count_missed(directive)          # one UPDATE, no read
if directive.status != "executed" or directive.batch_no is None:
    self._mark_schedule(directive)
    return
self._settle_batch_line(directive, price=_settle_price(directive, fill_price),
                        directive_id=directive_id)
self._mark_schedule(directive)
```
- `_count_missed`：`UPDATE playbook_batches SET missed_count = missed_count + 1, updated_at = ? WHERE symbol = ? AND batch_no = ?`。
  - 批次不存在時影響 0 列，等同現行的 `if batch is not None`。
  - 不寫 `entry_before_exit_on`（C-B6「MISSED 不加標示」）。

**(2) `_settle_batch_line`（新私有 helper；寫法比照 `_settle_s2_fill`／`commit_evaluation`，錯誤處理照 C-11）**
1. `with closing(self._connect()) as conn`，執行 `BEGIN IMMEDIATE`。
2. 在這個 conn 上讀批次：與 `get_batch` 同一句 SELECT，透過接收 conn 的私有讀取 helper。讀不到時 `COMMIT` 並 return，`settle` 照舊只做 `_mark_schedule`。
3. buy：
   - 在同一個 conn 讀 L4 戳記（與 `_exit_stamp` 同一句 SELECT）；`directive_id` 為 None 時不讀，與現行相同。
   - 新值與現行 :1529-1539 逐字相同：`status='open'`、`entry_date`、`cost=price`、`shares`、`remaining_shares=directive.shares`、`peak_close=price`、`entry_before_exit_on`（戳記為 None 時沿用鎖內讀到的值）。
   - 寫入：`UPDATE playbook_batches SET status = ?, entry_date = ?, cost = ?, shares = ?, remaining_shares = ?, peak_close = ?, entry_before_exit_on = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?`。
   - 現金：`_add_cash(conn, -(price × directive.shares))`。
4. sell：
   - `moved = min(鎖內 remaining, directive.shares)`；`remaining = max(0, 鎖內 remaining − directive.shares)`；`status` 與 P1／P2／P3 的標記和現行 :1542-1555 逐字相同。
   - 寫入：`UPDATE playbook_batches SET remaining_shares = ?, status = ?, p1_done = ?, p2_done = ?, trailing_active = ?, p3_last_date = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?`。值取自鎖內讀值再套上變更，所以沒變的欄位，寫回的就是鎖內當下的值。
   - 現金：`_add_cash(conn, price × moved)`。
5. 其他 action：不寫。這條路徑走不到，因為非下單列寫入時就已是 settled（見 `record_directives`）。現行在這裡會整列重寫一次（只改 updated_at），這是全案唯一不等價的地方。
6. `COMMIT`。例外時先 `if conn.in_transaction: ROLLBACK`，再原樣 raise。
- 持鎖期間不得呼叫任何會另開連線的 `self.*` 方法：`get_batch`、`portfolio_state`、`_exit_stamp`、`set_cash`、`save_batch`。

**(3) 共用的 conn helper（模組層級或私有方法，各只有一份定義）**
- 接收 conn 的批次讀取：`SELECT {_BATCH_SELECT} … WHERE symbol = ? AND batch_no = ?`，轉換沿用既有的 `_row_to_batch`。`get_batch` 可以改成委派給它（行為不變），但不得另寫第二份 SELECT。
- `_add_cash(conn, delta)`：在 conn 上讀 `STATE_CASH`（沒有這個鍵時視為 `Decimal("0")`，與 `portfolio_state` 相同），再以 `_write_state(conn, {STATE_CASH: str(cash + delta)})` 寫回。`_settle_s2_fill`（4.5）與 `_settle_batch_line` 共用。
- 寫入次數要與現行等價：
  - buy／sell 一律呼叫 `_add_cash`，delta 為 0 也要寫，因為現行的 `set_cash` 每次都寫，鍵會因此被建立；
  - S2 依 4.5，只在 Σmoved > 0 時呼叫（T12）。

**(4) 結算以外的批次寫入者改成欄位化（W4～W7）**
- `roll_peak_closes`：讀取照舊用 `self.list_batches()`，比較邏輯不變。寫入改為同一個 conn（`with closing(...) as conn, conn:`，不加 `BEGIN IMMEDIATE`），逐批執行 `UPDATE playbook_batches SET peak_close = ?, updated_at = ? WHERE symbol = ? AND batch_no = ? AND status = 'open'`。
- `defer_reset`：`UPDATE playbook_batches SET defer_count = 0, updated_at = ? WHERE symbol = ? AND defer_count <> 0`。
- `_update_batch`：不讀，直接 `UPDATE playbook_batches SET <欄> = ?, updated_at = ? WHERE symbol = ? AND batch_no = ?`。
  - 欄名只能來自白名單 `defer_count`、`status`、`trailing_active`，也就是現有三個呼叫者用到的三個欄位；其他欄名 raise `ValueError`。
  - 布林值轉成 int，與 `save_batch` 相同。
- 這幾處**不得**加 `BEGIN IMMEDIATE`。
  - 理由：`test_playbook_same_day_race.py` 的 T14（`(begin,) = …`）與 `_writes_inside`（取第一個 `BEGIN IMMEDIATE`），都假設沒有結算成交的 `/today` 只有一個 `BEGIN IMMEDIATE`，也就是 `commit_evaluation` 那一個。
  - 單句 UPDATE 本身就是原子的；改成欄位化之後，就算讀值過時，也覆寫不到股數或 status。

**(5) 為什麼這樣滿足 RC-1 第 1 點**
- 所有改動股數或現金的寫入（`_settle_s2_fill`、`_settle_batch_line`），都在 SQLite 寫鎖內讀、在同一個寫鎖內寫。SQLite 同時只允許一個寫交易，所以兩個結算請求的動帳結果，等於依取得寫鎖順序的某一個循序執行。4.10 的三點在每一種循序順序下都成立（T6 測了兩種順序）。
- 結算以外的寫入者只寫自己的欄位（peak_close、defer_count、trailing_active、status='skipped'），不寫 `remaining_shares`、`shares`，也不寫 open／closed 的 status，所以不會讓 S2 關閉的批次復活。
  - `batch_skipped` 只由 engine 對 planned 批次發出；在 `/today` 中，它由鎖內的 `_apply_bound_effects` 寫入。
- `app/` 內不再有任何 `save_batch` 呼叫點。`INSERT OR REPLACE INTO playbook_batches` 只留在 `save_batch` 的定義裡，給測試建 fixture 用。
- 不改的地方：claim 與 settle 仍分屬兩個 transaction（F2，歸 N-169）。這不影響上面的結論：claim 只決定誰處理哪一列，帳冊結果只取決於動帳交易的先後。

#### 1.4 改動範圍的判定（回答 RC-1 的三個問題）
- **舊分支是不是 C-B6／N-168 守護的範圍？**
  - buy 分支與 missed 區塊是：C-B6 規定「buy 成交時把戳記複製到批次標示；MISSED 不加標示」。
  - sell 分支不是 C-B6 的條文本身，但與 buy 同在 `settle` 本體內。
  - 判定：C-B6 是**行為**約束，不是程式碼凍結。R-α 寫入的值與 C-B6 的行為逐值相同，由三項守住：N-168 既有測試斷言零改動（C9）、T27 差分測試、C18。
  - 4.9 第 3 點「N-177a 不碰 buy 分支」由本修訂更正為「N-177a 改寫 buy 分支的讀寫方式（鎖內讀、欄位化寫），值與 C-B6 行為不變」。
  - 改寫 buy 分支屬於「改動 `settle` 的動帳實作」。依 A-2，由 ADR-0041 承載並送風控。
- **`save_batch` 的其他呼叫者會不會受影響？**
  - `save_batch` 本體零 diff。
  - app 內原有的呼叫者（W1、W2、W4、W6、W7）全部改走欄位化寫入，行為等價；`test_playbook_store.py` 中 roll_peak／apply_effects 的既有測試應原樣綠燈。
  - 測試 fixture 照舊可以用 `save_batch`。
  - `get_batch` 只讀，`service._batch_of`（N2、W-B3）照舊使用。
- **與 C3 的關係**：C3 要擴充，見 1.5。service.py、engine.py、models.py、wording.py 仍然零 diff。

#### 1.5 約束與測試的修訂（取代 4.11、4.12 的對應條文）

- **C3（取代）**：改動範圍只限 store.py 的以下部分：
  - (a) 模組 docstring；
  - (b) 4.2 的常數與兩個函式；
  - (c) `_SCHEMA` 末尾追加一條 DDL；
  - (d) `settle`：抽出 `_settle_price`、插入 S2 分支、missed 區塊改呼叫 `_count_missed`、逐批分支改呼叫 `_settle_batch_line`、更新 docstring；
  - (e) `_settle_s2_fill`；
  - (f) `_settle_batch_line`、`_count_missed`；
  - (g) 1.3(3) 的 conn helper；`get_batch`、`_exit_stamp` 只允許改成委派（行為不變）；
  - (h) `roll_peak_closes` 的寫入；
  - (i) `apply_effects` 的 `defer_reset` 分支；
  - (j) `_update_batch`。
  - 其餘零 diff，特別是：`commit_evaluation`、`_read_logged`、`read_in_flight`、`_read_exit_state`、`_apply_bound_effects`、`commit_emergency_exit`、`claim_directive`、`batch_blocking_claim`、`_insert_directives`、`BATCH_LEFT_PLANNED_SQL`、`blacklist`、`save_batch`、`set_cash`、`set_capital`、`portfolio_state`、`list_batches`、`_mark_schedule`、`_MIGRATIONS`、`_init_schema` 本體。
  - 以下零 diff：service.py（含 `_lines`、`_settle_pending`、`rebalance`）、wording.py、models.py、`app/api/**`、`app/data/**`、`app/services/**`。
  - 改動 `playbook_batches` 股數（`shares`、`remaining_shares`）或 cash 的寫入，只出現在 `_settle_s2_fill`、`_settle_batch_line`（經 `_add_cash`）。
- **C6（取代）**：
  - S2 依 4.4、4.5；逐批 buy／sell 依 1.3(2)；價格只走 `_settle_price`。
  - `settle` 的任何分支都不得呼叫 `save_batch`、`set_cash`、`portfolio_state`、`get_batch`、`_exit_stamp`，也不得產生 `INSERT OR REPLACE INTO playbook_batches`。
- **C7（取代）**：
  - 同一筆 S2 的合格讀取、批次更新、現金讀改寫、稽核寫入，都在同一 conn 的單一 `BEGIN IMMEDIATE` 內完成。
  - 同一筆逐批 buy／sell 的批次讀取、戳記讀取（buy）、批次更新、現金讀改寫，同樣在同一 conn 的單一 `BEGIN IMMEDIATE` 內完成。
  - 錯誤處理照 C-11；持鎖期間沒有其他 I/O，也不另開連線。
- **C9（追加第 (3) 點）**：既有測試中以 trace 取「第一個」或「唯一一個」`BEGIN IMMEDIATE` 的斷言，若涵蓋的流程含有結算成交：
  - PR 要逐條列出，並說明修訂一之後，斷言指到的仍是原本那個交易；
  - 不得弱化既有斷言；需要修改的，列入第 (2) 點交 qa 判定；
  - 已知位置：`test_playbook_same_day_race.py::_writes_inside`、同檔 T14 的 `(begin,) =`、`test_playbook_exit_race.py` :376、`test_playbook_entry_before_exit.py` :546、:562。後兩處是 emergency_exit，預期不受影響。
- **C16（取代）**：4.12 與本節的 T1～T29 全部存在且綠燈（BLOCKING）。
- **C17（新增）**：結算以外的批次寫入者（`roll_peak_closes`、`defer_reset`、`_update_batch`）只用欄位化 UPDATE：
  - 不寫 `shares`、`remaining_shares`；
  - 不寫 `status`，唯一例外是 `_update_batch` 的 `status='skipped'`；
  - 不加 `BEGIN IMMEDIATE`。
- **C18（新增）**：行為等價。
  - 循序執行時，逐批 buy／sell／missed 寫出的批次各欄（`updated_at` 除外）與現金，都和修訂前逐值相同；
  - buy／sell 一律寫現金，delta 為 0 也寫；
  - 唯一不等價的是 1.3(2) 第 5 步那條走不到的路徑。
- **4.8 (i)（取代）**：
  - N-177a 改動股數與現金的寫入程式，只在 `_settle_s2_fill`、`_settle_batch_line`，兩者都是 `settle` 的私有 helper；後者取代既有寫入，不是新路徑。
  - X-3 的前提「帳冊股數只在 claim 之後由 `settle` 改變」維持（T19）。
  - C17 的寫入者不碰股數與 cash，不屬於 Decision 14 第 2 點規範的對象。

**測試（追加 T23～T29；T19、T20 取代）**
- **T19（取代）**：
  - `app/` 內寫 `remaining_shares` 或 `shares` 的 `UPDATE playbook_batches`，只出現在 `_settle_s2_fill`、`_settle_batch_line`；
  - `INSERT INTO playbook_fill_moves` 只出現在 `_settle_s2_fill`；
  - `STATE_CASH` 的寫入只在 `set_cash`、`set_capital`、`_add_cash`，而 `_add_cash` 只被上述兩個 helper 呼叫；
  - `INSERT OR REPLACE INTO playbook_batches` 只在 `save_batch` 的定義內；
  - AST 檢查：`app/` 內沒有 `save_batch(`、`set_cash(` 的呼叫點。
- **T20（取代）**：SQL trace。
  - S2 分支與逐批 buy／sell 的批次 SELECT、現金 SELECT 與所有寫入，都夾在同一條連線的 `BEGIN IMMEDIATE` 與 `COMMIT` 之間；
  - missed 只有一句 `missed_count = missed_count + 1` 的 UPDATE。
- **T23（RC-1 決定性交錯：逐批先進入讀寫窗口）**：
  - 設定：同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B，等同兩個請求，也等同兩個行程。一批 open、remaining=100、cost 已設；待結算 S1（該批，參數化 40 股與 100 股）與 S2（100 股）。A claim S1，B claim S2。
  - 注入點：把 A 的 `_connect` 換成自訂 `Connection` factory，`execute` 在 A **第一句寫入 `playbook_batches` 或 `playbook_state`** 的 SQL 送出之前執行 hook。修訂前，這個點就是舊分支「`get_batch` 讀完之後、`set_cash`／`save_batch` 寫入之前」；修訂後，是鎖內讀完之後、寫入之前。
  - hook：另開執行緒跑 `B.settle(S2, …)`，最多等它 0.5 秒，然後放行 A；A 結束後 join B。BUSY_TIMEOUT 是 5 秒，B 不會逾時失敗。
  - 斷言（與時序無關）：
    - 該批 closed、remaining 0；
    - 現金 = 初值 + p1 × 40 + p2 × 60（100 股版本：初值 + p1 × 100）；
    - S2 稽核列 = 該批 60 股（100 股版本：sentinel 一列）；
    - 不出現 open 且 remaining > 0 的該批。
- **T24（RC-1 原情境：S2 先進入讀寫窗口）**：
  - 與 T23 角色互換：hook 掛在 B 的第一句寫入之前，在 hook 中另開執行緒跑 `A.settle(S1, …)`。
  - 斷言：該批 closed、remaining 0；現金 = 初值 + p2 × 100（S1 入帳 0）；S2 稽核列 = 該批 100 股。
  - 這就是 RC-1 描述的「A 讀到 remaining=100、B 關閉批次」的交錯；修訂後，A 的讀取一定發生在 B commit 之後。
- **T23／T24 的效力證明**：PR 說明附上本機輸出，顯示把 `_settle_batch_line` 暫時換回修訂前的逐批分支本體時，T23、T24 會失敗（批次復活，或現金不符）。這份對照不 commit。
- **T25（結構）**：用 spy 包住 `get_batch`、`save_batch`、`set_cash`、`portfolio_state`、`_exit_stamp`、`list_batches`。對以下各情況各跑一次 `settle`，上述方法的呼叫次數都是 0：
  - executed buy；
  - executed sell（S1、P1、P2、P3、EMERGENCY）；
  - missed sell、missed buy；
  - executed S2。
- **T26（結算以外的寫入者）**：
  - (i) S2 先關閉某批後，把 `list_batches` monkeypatch 成回傳關閉前（open、100 股）的過時清單，再以較高收盤呼叫 `roll_peak_closes`：DB 中該批仍是 closed、remaining 0。
  - (ii) 對 closed 批次套用 `trailing_on`、`defer_reset`：remaining 與 status 不變。
  - (iii) SQL trace：`roll_peak_closes`、`defer_reset`、`_update_batch` 只送出 C17 允許的 UPDATE，沒有 `BEGIN IMMEDIATE`，也沒有 `INSERT OR REPLACE`。
  - (iv) `_update_batch` 收到白名單以外的欄名時 raise `ValueError`。
- **T27（行為等價的差分測試）**：
  - 測試檔內放一份修訂前逐批分支與 missed 區塊的參考實作，只供比對。
  - 固定 seed，至少 300 組：隨機 book；隨機 buy／sell（S1、S2 以外的 S、P1～P3、EMERGENCY）／missed 列；涵蓋批次不存在、remaining 0、`directive_id` 為 None、有／無 L4 戳記。
  - 循序執行時，新舊兩者的批次各欄（`updated_at` 除外）與現金完全相同，`playbook_state` 的鍵集合也相同。
- **T28（`/today` 的交易數）**：以合入 N-190 後的 head 為準。
  - 沒有結算成交時，`evaluate_today` 的 trace 恰好一個 `BEGIN IMMEDIATE`；
  - 有 k 筆 executed 逐批列（含批次不存在）、m 筆 executed S2 時，恰好 1 + k + m 個。
- **T29（逐批動帳中途失敗）**：
  - 注入 `_add_cash` 拋例外：該批各欄與現金都不變，例外原樣拋出，沒有留下未關閉的交易；
  - 該列維持 `settled=1／executed`（F2 殘留釘住，歸 N-169，同 T9）。

**QB 追加**
- QB-2：hunk 逐一對照 C3 的 (a)～(j)。
- QB-3 追加：`INSERT OR REPLACE INTO playbook_batches` 在 `app/` 內只有一處。
- QB-4：改為 T1～T29；T7 至少 500 組、T27 至少 300 組，seed 都固定。
- QB-11（新增）：T23、T24 的效力證明附在 PR 說明。
- QB-12（新增）：N-168 的 T-B 系列、`test_playbook_settlement*.py`、`test_playbook_store.py` 原樣綠燈；C9 第 (3) 點的清單完整。

#### 1.6 RC-1 以外的相鄰問題（不擋 N-177a；[待風控] 裁示）

**R-1′：REBALANCE 以鎖外讀值寫回現金（W8）**
- 程式事實：`rebalance` 在 service.py:1538 讀 `portfolio_state()`，在 :1612 以 `set_capital(cash=portfolio.cash, …)` 整值寫回，中間只有純計算。
- 實害：
  - 若中間有並發結算 commit，那一筆的現金異動會被抹掉。
  - 修訂前就存在：buy 扣款與 sell 入帳都會被抹掉；抹掉 buy 扣款時現金多記，方向不保守。
  - N-177a 新增的只有「S2 入帳被抹掉」，現金少記，方向保守。
- 頻率：極低。REBALANCE 是手動、季末才跑，而且要與另一分頁的結算成交落在同一個毫秒級窗口。
- 可偵測性：現金是單一 KV、沒有異動歷史（ADR-0035 Decision 9），偵測工具判定不了。
- 歸類：ADR-0035 Consequences 的「結算時現金的讀改寫競態」原本歸 N-169。R-α 已消除結算內部的那一部分，REBALANCE 是剩下的唯一一處。
- 修法（不在 N-177a）：store 新增只寫 TOTAL_DEPLOY 三個鍵的方法，`rebalance` 改用它。service.py 只動 `rebalance` 一處，不是 N-190 的熱點。
- 請風控二選一：(a) 接受為歸 N-169 的殘留；(b) 另開小單，在 R2 之前或與 R2 同一個 release 上線。
- `confirm_rules` 的 `set_capital(cash=capital)` 是使用者宣告資金，覆寫就是它的語意，不列為競態。

**R-2′：N2 的鎖外預讀**
- 程式事實：N2 在 service.py:1360 先讀批次，之後才呼叫 `settle`。並發時，另一個請求的 S2 可能在這兩步之間關閉該批。
- 結果：EMERGENCY 實際移動 0 股，但 N2 沒有出現。帳冊正確，只是少揭露一次。
  - 反方向不會發生：closed 批次不會回到 open，因為 buy 只動 planned，而批次不會回到 planned。
- 頻率：低。要同一批同時有在途 EMERGENCY 與 S2，而且兩個結算請求並發。
- 修法：N-177b 的 `SettleOutcome` 已經有鎖內讀值，可以讓 N2 改依回傳值判定，字面不變。但 N177b-C6 規定 N2 的判斷零 diff，所以列為 **Q-g** 送風控。同意的話，N177b-C6 改為「N2 字面零 diff；判斷來源改為 `SettleOutcome`，判斷條件等價」。

**不處理（說明）**：
- `evaluate_today` 在 :1901 讀的 book，在並發下可能早於另一個請求的 S2，engine 可能因此對已關閉的批次再出 S/P。
- 這些列結算時零移動（4.10），由 N-177b 的 Q-c 句揭露。
- 這屬於 N-182 E-2 同類的「評估輸入過時」問題，帳冊不會因此出錯。

### 2. 4.10、4.14 的修訂（RC-1 第 3 點）

**4.10**：在第一個子彈前加入：
- 前提：以上在結算循序執行時成立；並發的處理見 RC-1。

並追加（[待風控]）：
- 修訂一：依 1.3，每一筆動帳的讀、算、寫都在同一個 `BEGIN IMMEDIATE` 內，並發結算在帳冊上的結果等於某一個循序順序，所以上述三點在並發下也成立（T23、T24）。

末兩個子彈改為：
- 殘留：非 EMERGENCY 的 S/P 在「批次存在但已沒有股數」時零移動、無聲。依 RC-7 歸 N-177b，期限見第 5 節。
- 風控已確認循序前提下成立（2026-11-07 A-1）。偵測工具的 G-c 依 RC-2 改為事實欄，另設 G-c′（第 6 節）。

**4.14 第 2 點（取代）**：
- 舊的逐批分支（buy、sell、missed），以及 `roll_peak_closes`、`trailing_on`、`defer_reset`，原本先在各自的連線讀批次與現金，再以整列 `INSERT OR REPLACE` 與整值寫回。並發時會：
  - (i) 以過時讀值覆寫已被 S2 關閉或減少的批次，股數與 status 一起復活；
  - (ii) 讓同一批股數的現金入帳兩次；
  - (iii) 抹掉其他結算的現金異動。
- 其中 (i)、(ii) 是 N-177a 新增的交錯（RC-1）。N-177a 依修訂一 R-α 一併修正，不列為殘留。
- 修正後剩下的相鄰問題是 R-1′（REBALANCE 寫回現金）與 R-2′（N2 鎖外預讀），見修訂一 1.6，待風控裁示。

**4.14 第 3 點（取代）**：4.10 的零移動 S/P 無聲：歸 N-177b（RC-7），最遲與第三包同一個 release。

**4.9 第 3 點第 2 子彈（更正）**：C-B6 衝突已不存在，因為 N-168 已合併。N-177a 改寫 buy 分支的讀寫方式（修訂一 1.3），寫入值與 C-B6 行為不變。

### 3. 第 5 節（N-177b）的修訂（RC-7、RC-8）

**範圍（取代）**：
- store.py：`settle` 的回傳值，由 `_settle_batch_line` 的鎖內讀值決定；
- service.py：`_settle_pending` 與結算 warnings；
- wording.py：加三個常數與項目格式。
- 在 N-177a 合併之後開工。

**判定（取代）**：`SettleOutcome(NamedTuple)` 有兩個欄位，日後只能再做加法。
- `missing_batch_row: bool`：同時滿足以下條件時為真。
  - `status == 'executed'`；
  - `action in ORDER_ACTIONS`；
  - `not is_s2_fill(directive)`；
  - `batch_no is None`，或 `_settle_batch_line` 在鎖內讀不到批次。
- `empty_batch_sell: bool`（Q-c，RC-7）：同時滿足以下條件時為真。
  - `status == 'executed'`、`action == 'sell'`；
  - `not is_s2_fill(directive)`、`rule_id != 'EMERGENCY'`；
  - 批次在鎖內讀得到，而且鎖內讀到的 `remaining_shares == 0`。
- 其他情況一律為假，包括：S2（含零移動 sentinel）、missed、非下單列，以及部分移動（0 < remaining < shares）。
- 兩個欄位都取自鎖內讀值，所以並發時也與實際動帳一致（修訂一 1.3）。不得在 service 另讀一次。

**service（追加）**：收集 `empty_batch_sell` 為真的列。EMERGENCY 在判定時已排除，由 N2 揭露。

**位置（取代）**：在結算 warnings 中依序為 SUMMARY → W-B3 → N2 → buy 句 → sell 句 → Q-c 句（暫定）。最終順序隨字面定稿一併決定。

**字面（追加 Q-c 句）**：
- 識別名暫定 `SETTLEMENT_EMPTY_BATCH_SELL_NOTE`，只放在 `wording.py`；creative-lead 擬稿，風控逐字定稿。
- 只陳述「判定時該批次在帳冊已無持股，股數與現金都未因本筆變動」這個事實。
- 必含「本系統不下單」與「實際持股以你的券商回報為準」；不推測使用者是否已賣出。
- 禁用詞同 RC-3：「需」「應」「建議」「務必」「盡快」「否則」「安全」「對應」。
- 可用欄位：symbol、batch_no（此句一定是整數）、shares、execution_date、rule_id。

**期限（取代第 7 節第 5 步，以及 N177b-C8 的「可以更晚」）**：
- N-177b（含 Q-c 句）最遲與第三包同一個 release 上線；可以更早，不得更晚。
- 依 Q-e，「第三包」是 R2 之後的下一個 release，所以 N-177b 只能搭 R2，或搭第三包的那個 release。

**EMERGENCY 找不到批次時「走不到」的論證（RC-8，寫入本規格）**：
- 現況核對：
  - EMERGENCY 找不到批次列時，N2 第二句「帳冊中這幾批只依另一筆賣出指令減少一次股數」不為真；
  - `SETTLEMENT_EXIT_ITEM` 遇到 `batch_no` 為 None 時，會印出「第 None 批」。
- 這條路徑走不到，理由：
  1. EMERGENCY 列只從當下存在的批次產生（service.py:414-420），`batch_no=batch.batch_no` 一定是整數。
  2. `app/` 內沒有任何 `DELETE FROM playbook_batches`（grep 的結果只有 positions、alerts、playbook_state、cache、kelly）。
  3. 批次列只由 `ensure_batches` 的 `INSERT OR IGNORE` 建立；`save_batch` 的 `INSERT OR REPLACE` 是刪除後立即在同一句插回，而且修訂一之後 app 內已沒有 `save_batch` 呼叫點。
  4. 所以 EMERGENCY 列所屬的批次列一旦存在，就不會消失。
- 論證不涵蓋手動改 DB；RC-9 第 4 點禁止手動改 DB。
- N177b-T3 保留為釘住測試。
- 日後若發現走得到的路徑，要回 TA 與風控，不得以 N2 代替揭露。

**約束修訂**：
- N177b-C3：`_settle_pending` 的 diff 只限接收回傳值與追加 warnings。
- N177b-C6：維持「N2 的判斷與字面零 diff」；若風控同意 Q-g，依 1.6 改寫。
- N177b-C9（新增）：兩個判定欄位只由 store 在鎖內決定，service 不得另讀批次來判定。
- N177b-C8：維持「可以搭 R2 上線，但不得延後 N-177a」，並加上本節的期限。

**測試追加**：
- N177b-T9：非 EMERGENCY 的 S1、P1 在 remaining 0 的批次上判定成交 → Q-c 句恰好一次，帳冊與現金不變。
- N177b-T10：EMERGENCY 在 remaining 0 的批次上 → 只有 N2，沒有 Q-c 句。
- N177b-T11：部分移動（0 < remaining < shares）→ 沒有 Q-c 句。
- N177b-T12：用 T24 的設定（S2 先關閉批次，並發的 S1 隨後結算）→ S1 那一次的結果含 Q-c 句。
- N177b-T13：S2 零移動 sentinel → 沒有 Q-c 句。
- N177b-T14：Q-c 句與 buy 句、sell 句同時出現時，順序正確。

### 4. 第 6 節（偵測工具）的修訂（RC-2、RC-3、RC-5、RC-6）

data-engineer 已依風控原文實作 RC-2～RC-6，以下內容與風控原文一致。標 [TA 補] 的是 TA 的解讀或新增；若與已完成的實作不同，請在 PR 說明列出，交 TA 判定，不視為 BLOCKING。

**6.2 exit code 4（取代）**：以下情況拒絕執行：
- 指向正式 DB；
- 輸出檔已存在；
- out-dir 是正式資料夾；
- **`--out-dir` 位於 repo 工作樹內**（RC-5）：解析成實際路徑後，自身或任一上層目錄存在 `.git`。目錄或檔案都算，worktree 的 `.git` 是檔案 [TA 補]。

**6.3 S8（取代）**：
- 報告不得含「需」「建議」「應」「務必」「盡快」「否則」「安全」「對應」。
- 唯一例外是逐字的固定標籤「需人工判讀」：掃描前先移除這個標籤字串，再掃其餘內容；標籤後的理由文字照樣要掃。
- 掃描兩層：
  - (i) 腳本中所有字串常數（AST，含 f-string 的常數部分）；
  - (ii) 用 fixture 實跑後的 `report.md` 與 `report.json`。
- 報告不得原樣輸出 DB 裡的自由文字欄位，例如 `rule_summary`、`limit_note`、各種理由句；只能輸出截取後的 token，例如 N190-B 的指數狀態（RC-3）。
- [TA 補] 枚舉欄位（rule_id、action、status、source）只在值屬於已知集合時原樣輸出；否則輸出固定字樣「（非預期值）」並計數，避免 DB 內容進入報告。

**6.3 S12（新增）**：RC-5 的 repo 工作樹判定要有測試：
- out-dir 在含 `.git` 目錄的暫存樹內 → exit 4；
- 在含 `.git` 檔案的暫存樹內 → exit 4；
- 在樹外 → 正常執行。

**6.4（取代閘門行，新增兩句）**：三句都逐字取自 [風控-177R] RC-4，放在模組常數；測試從該檔的「」逐字抽取比對。
- 閘門行，取代原本的「N-177 部署閘門：受影響標的 X 檔（X > 0 時需要 CEO 逐檔裁示）」：
  「N-177 部署閘門：受影響標的 {n} 檔。依風控 A-1 條件 1，這個數字大於 0 時，N-177a 部署前由 CEO 逐檔在 (A)、(B) 之間選擇；本報告不預設任何一個選項。」
- 每張試算表的上方各出現一次：
  「試算回補現金 = 第一張 S2 的成交判定價 × 試算分配股數合計。這個數字假設你已依第一張 S2 在券商賣出且成交（L9），按 N-177a 的分配規則算出，不一定等於你實際成交的金額；實際成交的股數與價格，只有你的券商對帳單能確認。」
- 放在判讀圖例區：
  「可試算：本檔沒有觸發本報告列出的任何一條誤判防護，所以列出試算；這不表示試算結果與你的券商紀錄一致。」
- `{n}` 是唯一的佔位符；`report.json` 的 `gate` 欄位不變。
- 修訂一 R-α 不改變 4.4 的分配規則，所以第二句中的「N-177a 的分配規則」仍然指 4.4。

**6.5 G-c（取代）與 G-c′（新增）（RC-2）**：
- G-c 不再是誤判防護，改成事實欄，明細就是 N177-F。查詢沿用原文 SQL，篩選 `batch_no` 屬於該 symbol 現在的合格批次的列。
- **G-c′**（誤判防護）：N177-F 的列中（含 EMERGENCY），只要有任一張 `execution_date <= 第一張 S2.execution_date`，該標的就列為「需人工判讀」。
- [TA 補] 「受影響批次」讀作該 symbol 現在的全部合格批次，與 N177-F 是同一個集合。這比「只算試算分配股數大於 0 的批次」寬，方向保守。
- 工具第一版就照這個最終形式實作；原文「風控接受之後……要另提 PR」刪除。
- (B) 的可試算範圍因此擴大：受影響批次上有在途賣單、但都晚於第一張 S2 的標的，只要沒有觸發其他防護，就可以試算。
- 6.7 追加以下測試：
  - G-c′ 正例：在途單的 `execution_date` 等於或早於第一張 S2；
  - 反例：只有晚於的在途單 → 可試算，F 欄列出；
  - EMERGENCY 在途單觸發 G-c′。

**6.8 私人資料（取代「報告內含持股與現金」那一段）（RC-6）**：
- 報告留在 CEO 本機，不 commit 進 repo；`--out-dir` 在 repo 內時，工具拒絕執行（RC-5）。
- CEO 把 `report.md` 交給 coordinator，轉給 TA 與風控。收到報告的 agent（coordinator、TA、風控）在回報與審查檔中，只引用 id 與筆數，不轉錄報告內容。
- `work/`、`docs/` 與 release 紀錄（QB-10、M-1）只能記錄：
  - 閘門檔數與各類筆數；
  - 腳本 SHA-256；
  - 執行前後的 DB 雜湊、run_at；
  - 每檔以「第一張 S2 的 directive id」識別的 CEO 選擇（A 或 B），以及 apply 的時間。
- 不得記錄 symbol、股數、價格、現金金額，除非 CEO 書面同意。
- CEO 依 6.9 做的逐檔書面確認（symbol、id、金額），原件留在 CEO 本機；repo 只引用 id。
- [TA 補] (B) dry-run 的指紋不寫進 repo，只記「指紋與閘門報告一致：是／否」。理由：指紋是 (symbol, id, 金額) 的雜湊，id 已知時可以窮舉還原。
- [TA 補，待風控] RC-9 第 4 點的「TA 逐案評估書面」含股數與金額，同樣屬私人資料：不落檔進 repo，由 coordinator 直接轉交 CEO；repo 只記「id、已評估、評估日期」。這是 RC-6 與 RC-9 第 4 點同時適用時的解法。

**6.9（追加）**：
- 指紋以**閘門那次**的報告為準（RC-9 第 3 點）。
- 需人工判讀的標的，dry-run 的比對對象是「閘門報告該列的事實欄 + TA 逐案評估書面中的分配與金額」，使用同一個 apply 工具、同一套指紋檢查（RC-9 第 4 點）。
- 不得手動改 DB。

### 5. 第 8 節（CEO 決策點）的修訂（RC-9）

**D-1（取代）**：R2 停機時，閘門偵測大於 0 檔，就要逐檔在 (B) 與 (A) 之間選擇，沒有預設選項（風控 A-1）：
- (B)：依第一張 S2 回補，用券商對帳單確認；
- (A)：只對未來生效，掛 (c) 揭露。

**不得替 CEO 預設 (A)**：
- 不得因停機時間的壓力，替 CEO 預設 (A)。
- 以下任一情況，R2 延後、舊版（R1 build）恢復服務，下一次停機重跑閘門，並附 `--previous-json`：
  - (B) apply 工具尚未審查通過；
  - 需人工判讀的案子尚未評估完。
- 延後後的 R2 仍然算「R1 的下一個 release」（ADR-0040 Decision 13），(c) 不因此回復為 required。
- 延後期間不得出其他功能 release，hotfix 除外。

**閘門那次的確認**：
- CEO 以**一份**書面確認涵蓋完整清單；沿用前次選擇的列，也要列入。
- `diff_vs_previous` 標「與前次不同」的列，不沿用前次的選擇。
- (B) dry-run 的指紋必須與**閘門那次**的報告一致。

**需人工判讀的標的**：
- CEO 可以選 (A)，或提供券商資訊，由 TA 逐案評估。
- 評估結果寫成書面，依 6.8 不落檔進 repo。
- 經 CEO 依 6.9 逐檔確認後，才能用同一個 apply 工具、同樣的指紋檢查寫入。
- 不得手動改 DB。

**G-b 的情況**：預設**不重跑** REBALANCE，因為 TOTAL_DEPLOY 會跟著變大；只有 CEO 明確決定時才重跑。這與 ADR-0035 Decision 9 末段一致。

**流程（新增）**：
- 第一次執行若大於 0 檔：
  - TA 立刻起草 6.9 的 spec，讓工具在 R2 之前完成審查；
  - creative-lead 同時開始擬 (c) 的字面（suggested），以免選 (A) 時趕不上下一個 release。
- 「不需要決策的項目」：原文的「G-b 另外決定是否重跑」刪除，改為上面的預設不重跑；其餘不變。
- 第 7 節第 4 步依本節改寫為：「大於 0 檔：CEO 逐檔裁示 → (B) apply → 部署；任一前提未滿足時，依 D-1 延後 R2」。

（修訂一由 coordinator 2026-11-07 附加；原文與 ADR-0041、補充六草案見 `work/reviews/2026-11-07-N177規格修訂一與ADR0041草案-tech-architect.md`。風控再審 A～G 前，N-177a 不得合併，ADR-0041 與補充六不落檔。）

## 修訂二（tech-architect，2026-11-07；回應風控再審 [風控-177R2]）

- 依據：[風控-177R2] `work/reviews/2026-11-07-N177修訂一再審與N177b定稿-風控.md`（A：CONDITIONAL APPROVE；B：CONDITIONAL APPROVE）。
- 程式依據：同本檔第 6 行的 checkout，只讀，未執行。行號以內容定位。
- 本修訂取代本檔與修訂一的對應段落；沒提到的段落維持原文。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀；標 [待風控] 的需要風控裁示。
- 修改處索引見第 7 節；依風控指示，Q-g 與 ADR-0041 只比對修改處。

### 0. 風控再審結果的登錄（不改判斷）
- R-α（修訂一第 1 節）：APPROVE。RC-1 以修正結案，不列為殘留。
- N-177a 依修訂一第 1 節開發。合併前提：
  - ADR-0035 補充六已生效（已依 G 項定稿落檔）；
  - ADR-0041（proposed）依 F 項修正後落檔；
  - QB-11 的效力證明；
  - qa 沒有 BLOCKING。
- 修訂一 1.6 的兩項，以本節取代「[待風控] 裁示」：
  - R-1′：選 (b)，另開小單 N-195（本修訂第 5 節）。
  - R-2′／Q-g：同意，附條件，擋 N-177b 合併（本修訂第 3 節）。

### 1. 4.10 追加句（取代修訂一第 2 節「並追加（[待風控]）」的那一句）
- 修訂一：依 1.3，每一筆改動股數或現金的動帳，讀、算、寫都在同一個 `BEGIN IMMEDIATE` 內；並發結算在各批股數、open／closed 狀態與現金上的結果，等於依取得寫鎖順序的某一個循序執行，所以上述三點在並發下也成立。這個結論以 C6、C7、C17 成立為前提，由 T20、T23～T26 檢查。
- 範圍說明（不屬於追加句本身）：
  - 結算以外的寫入者在鎖外，可能把 `trailing_active`、`defer_count` 寫到剛被關閉的批次上。
  - 這不影響股數、狀態與現金，但整本帳冊的狀態不一定等於任何一個循序順序。
  - 所以本句只對這三項成立，不得改寫成「帳冊結果」。

**1′. 修訂一 1.3(5) 第一點的用語同步 [TA 補]**
- 「所以兩個結算請求的動帳結果，等於依取得寫鎖順序的某一個循序執行」改為：
- 「所以兩個結算請求在各批股數、open／closed 狀態與現金上的結果，等於依取得寫鎖順序的某一個循序執行」。
- 理由同 1。

### 2. 4.14 第 2 點（取代修訂一第 2 節的版本）
- 修訂前，以下寫入者都先在各自的連線讀批次與現金，再以整列 `INSERT OR REPLACE` 與整值寫回：
  - 舊的逐批分支（buy、sell、missed）；
  - `roll_peak_closes`、`trailing_on`、`defer_reset`。
- 並發時可能：
  - (i) 以過時讀值整列覆寫已被關閉或減少的批次，股數與 status 一起復活；
  - (ii) 讓同一批股數的現金入帳兩次；
  - (iii) 抹掉其他結算的現金異動。
- (i)、(ii) 不是 N-177a 新增的交錯。同樣的整列覆寫與重複入帳，在 N-177a 之前就存在於：
  - 逐批賣出之間：兩個請求並發結算同一批的兩張逐批 sell，各自讀到同一個 remaining；
  - 逐批賣出與 `roll_peak_closes`／`trailing_on`／`defer_reset` 之間：例如 `/today` 的 `roll_peak_closes` 讀完批次之後，並發的 `POST /settle` 賣出同一批，`roll_peak_closes` 再以讀到的舊列整列寫回。
- N-177a 新增的是 S2 也加入這些交錯（RC-1），頻率因此提高。
- (iii) 就是 ADR-0035 Consequences 已接受、歸 N-169 的「結算時現金的讀改寫競態」。
- R-α（修訂一 1.3）把 (i)～(iii) 在結算內部一併消除，不列為殘留（[風控-177R2] A 項與書面紀錄）。
- 剩下的相鄰問題：
  - R-1′（REBALANCE 寫回現金）→ N-195（本修訂第 5 節）；
  - R-2′（N2 鎖外預讀）→ Q-g，併入 N-177b（本修訂第 3 節）。
- 已知限制：
  - R-α 之前的歷史資料，沒有任何工具檢查過這類交錯；
  - 現金是單一 KV、沒有異動歷史，所以偵測不到；
  - 頻率低，不列為 N-177a 的殘留；
  - 第 6 節的偵測工具不涵蓋這一類，也不因本條擴充。

### 3. Q-g：N2 改依鎖內結果判定（擋 N-177b 合併；取代修訂一第 3 節的對應段落）

#### 3.1 缺口（[風控-177R2] B 項 R-2′／Q-g 第 1 點）
- 修訂一的 `SettleOutcome` 中：
  - `missing_batch_row` 涵蓋「EMERGENCY 找不到批次列」；
  - `empty_batch_sell` 依定義排除 EMERGENCY。
- 所以「EMERGENCY 在鎖內讀到 remaining 0」這個情況，兩個欄位都表達不出，N2 無法只靠回傳值判定。

#### 3.2 方案比較
| 方案 | 內容 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| Q-g(i) 加欄位 | 新增第三個欄位，例如 `exit_nothing_held`：EMERGENCY，而且鎖內讀不到批次或 remaining ≤ 0；兩個既有欄位不變 | 只做加法；既有欄位的語意不變 | store 要自行判斷「這是 EMERGENCY」，與 service 的 `_is_exit_sell` 形成第二份定義，日後可能漂移；EMERGENCY 找不到批次時，`missing_batch_row` 與新欄位同時為真，語意重疊，service 還要再排除一次 | 中 | 否決 |
| Q-g(ii) 拿掉排除，service 分流 | `empty_batch_sell` 不再排除 EMERGENCY；store 只回報兩個與規則無關的事實；service 以既有的 `_is_exit_sell` 在單一函式內分流 | store 不帶任何規則判斷；「EMERGENCY 賣出」仍然只有 `_is_exit_sell` 一份定義；兩個欄位互斥；四句的分流集中在一處，可以窮舉測試 | `empty_batch_sell` 的定義與 C 項接受的版本有兩處不同，要再比對；service 必須正確分流（由 T17 綁住） | 低 | **採用** |

#### 3.3 判定（取代修訂一第 3 節「判定（取代）」中的 `empty_batch_sell` 一項）
- `SettleOutcome(NamedTuple)` 仍然只有兩個欄位，日後只能再做加法。
- `missing_batch_row: bool`：定義不變。同時滿足以下條件時為真：
  - `status == 'executed'`；
  - `action in ORDER_ACTIONS`；
  - `not is_s2_fill(directive)`；
  - `batch_no is None`，或鎖內讀不到批次。
- `empty_batch_sell: bool`（取代）：同時滿足以下條件時為真：
  - `status == 'executed'`、`action == 'sell'`；
  - `not is_s2_fill(directive)`；
  - 批次在鎖內讀得到，而且鎖內讀到的 `remaining_shares <= 0`。
- 與修訂一版本只差兩處：
  - (1) 拿掉 `rule_id != 'EMERGENCY'`；
  - (2) `== 0` 改為 `<= 0`，與現行 N2 的 `held.remaining_shares <= 0` 逐字對應。app 內 remaining 不會是負數（逐批 sell 用 `max(0, …)`，S2 用 `min`），所以在走得到的範圍內，(2) 不改變結果。
- 兩個欄位互斥：`missing_batch_row` 為真時，鎖內沒有讀到批次，`empty_batch_sell` 必為假。
- 其他情況一律為假，與修訂一相同：S2（含零移動 sentinel）、missed、非下單列、部分移動。
- store 的判定不引用任何 `rule_id`。store.py 中的 `'EMERGENCY'` 字面不因 N-177b 增加。

#### 3.4 store 端
- `_settle_batch_line` 把鎖內讀取的結果交回 `settle`：有沒有讀到批次、鎖內的 remaining。`settle` 據此組出 `SettleOutcome`。
- 判定用的值，必須是同一個 `BEGIN IMMEDIATE` 內、寫入之前讀到的值。
- 各情況的回傳值：
  - `batch_no is None` 的 executed 下單列：沿用現行的提前 return，不讀 DB，回 `missing_batch_row=True`；
  - missed、S2、非下單列：兩個欄位都是 False。

#### 3.5 service 端：四句的分流（單一函式）
```python
_N2 = "exit_nothing_held"               # SETTLEMENT_EXIT_NOTHING_MOVED_NOTE
_UNBOOKED_BUY = "unbooked_buy"          # SETTLEMENT_UNBOOKED_BUY_NOTE
_UNBOOKED_SELL = "unbooked_sell"        # SETTLEMENT_UNBOOKED_SELL_NOTE
_EMPTY_BATCH_SELL = "empty_batch_sell"  # SETTLEMENT_EMPTY_BATCH_SELL_NOTE


def _settled_line_note(line: Directive, booked: SettleOutcome) -> str | None:
    """The one place that routes a settled line to N2 or an N-177b note (N177b-C10)."""
    if line.status != "executed":
        return None
    if _is_exit_sell(line):
        return _N2 if (booked.missing_batch_row or booked.empty_batch_sell) else None
    if booked.missing_batch_row:
        return _UNBOOKED_BUY if line.action == "buy" else _UNBOOKED_SELL
    if booked.empty_batch_sell:
        return _EMPTY_BATCH_SELL
    return None
```
- 名稱可以由 dev-lead 調整（Enum、Literal 都可以），但必須是單一函式；`_settle_pending` 只依它的回傳值，把該列放進對應的清單。
- `_settle_pending` 迴圈中的流程：
  - claim 成功之後，`booked = self._store.settle(...)`；
  - 呼叫 `_settled_line_note(outcome, booked)`；
  - 依回傳值 append 到四個清單之一。
- 刪除 N2 原本在 `settle` 之前的 `_batch_of` 預讀（service.py:1357-1362）。W-B3 在 `settle` 之後的 `_batch_of`（:1367）不變。
- 四個清單都依迴圈順序 append，也就是 `pending_directives` 的 id 遞增順序。這與現行 N2 `moved_nothing` 的順序相同，對應 [風控-177R2] B 件實作條件 3「排序比照 N2」。

#### 3.6 N2 的判定與現行等價，而且只有一個來源（N177b-C9）
- 現行條件：
  - `_is_exit_sell(outcome) and outcome.status == "executed"`；
  - 而且 `held is None or held.remaining_shares <= 0`；
  - `held = _batch_of(outcome)`：`batch_no` 為 None 時是 None，否則是 `get_batch` 的結果。
- 新條件：
  - `_is_exit_sell(line) and line.status == "executed"`；
  - 而且 `missing_batch_row or empty_batch_sell`。
- EMERGENCY 賣出列的 `action == 'sell'`，屬於 `ORDER_ACTIONS`（store.py:229）；`rule_id != 'S2'`，所以 `is_s2_fill` 為假。因此：
  - `missing_batch_row` ⇔ `batch_no is None` 或鎖內讀不到批次 ⇔ 現行的 `held is None`；
  - `empty_batch_sell` ⇔ 鎖內讀到批次，而且 `remaining_shares <= 0` ⇔ 現行的 `held is not None and held.remaining_shares <= 0`。
- 條件逐項相同，差別只在讀取時點：
  - 現行是在 `settle` 之前另開連線讀；新的是在 `settle` 的動帳交易內、寫入之前讀。
  - 循序執行時，兩者讀到同一個值（同一迴圈中較早的列都已 commit），所以結果相同。
  - 並發時，新的判定與實際動帳一致，這就是 R-2′ 的修正。
- 判斷來源只有 `SettleOutcome` 一個。service 不得為 N2、buy 句、sell 句、Q-c 句另讀批次。

#### 3.7 字面、項目格式與順序（[風控-177R2] B 件）
- 字面：
  - 五段字面以 [風控-177R2]「B 件：N-177b 字面」的「逐字定稿」為準：`SETTLEMENT_UNBOOKED_BUY_NOTE`、`SETTLEMENT_UNBOOKED_SELL_NOTE`、`SETTLEMENT_EMPTY_BATCH_SELL_NOTE`、`SETTLEMENT_UNBOOKED_ITEM`、`SETTLEMENT_UNBOOKED_ITEM_NO_BATCH`。
  - 只放在 `wording.py`。測試從該檔各識別名之後的第一個「」逐字抽取比對（N177b-C5）。
  - 本規格不轉錄字面，以免出現第二份。
- 項目格式：
  - buy 句、sell 句的每一項依 `batch_no is None` 選用：None 用 `SETTLEMENT_UNBOOKED_ITEM_NO_BATCH`，否則用 `SETTLEMENT_UNBOOKED_ITEM`。
  - Q-c 句只用 `SETTLEMENT_UNBOOKED_ITEM`。`empty_batch_sell` 為真時一定讀到了批次，`batch_no` 是整數。
  - 欄位：symbol、batch_no（只有 `SETTLEMENT_UNBOOKED_ITEM` 用）、shares（指令股數）、rule_id、execution_date（ISO 格式，與 N2 相同）。
  - `{items}` 以「、」連接，順序依 3.5 最後一點。
- 順序定稿：SUMMARY → W-B3 → N2 → buy 句 → sell 句 → Q-c 句。這取代修訂一第 3 節「位置（取代）」中的「（暫定）」。
- N2 的字面、`SETTLEMENT_EXIT_ITEM` 與 `exit_items` 的組法零 diff。

#### 3.8 RC-8「走不到」論證的前提補充（[風控-177R2] C 項）
- 修訂一第 3 節論證第 3、4 點，前提是「沒有任何寫入者刪除或整列重寫批次列」。
  - 在 `app/` 內，由 T19 保證；
  - 在 `app/` 外，由 6.9 工具的約束保證（本修訂第 4 節 A1、A4、AT-1～AT-3）。
- 論證其餘文字不變。「日後若發現走得到的路徑，要回 TA 與風控，不得以 N2 代替揭露」維持。
- EMERGENCY 找不到批次時進 N2、不進 sell 句：這是 Q-b 已接受的既有分流（[風控-177R2] B 項第 2 點），不是以 N2 代替揭露的新路徑。

#### 3.9 約束修訂
- **N177b-C3（取代）**：`_settle_pending` 的 diff 只限：
  - 接收 `settle` 的回傳值；
  - 以 `_settled_line_note` 取代 N2 的預讀判定：刪除 :1357-1362 的預讀，N2 的 append 移到 `settle` 之後；
  - 追加三句 warnings。
  - 取開盤價的方式、claim、G1、W-B3、N1／N1b、SUMMARY 的組法零 diff。
- **N177b-C5（補充）**：逐字比對的來源是 [風控-177R2] 的「逐字定稿」。
- **N177b-C6（取代，依修訂一 1.6）**：
  - N2、W-B3、SUMMARY 的字面零 diff；
  - W-B3、SUMMARY 的判斷零 diff；
  - N2 的判斷來源改為 `SettleOutcome`，條件與現行 `held is None or held.remaining_shares <= 0` 等價（3.6）；
  - N2 的既有測試斷言零改動。
- **N177b-C9（取代）**：
  - `missing_batch_row`、`empty_batch_sell` 只由 store 依 `settle` 動帳交易內、寫入之前讀到的值決定；
  - service 不得為 N2 與三句另讀批次；
  - `_settle_pending` 內的 `_batch_of` 只剩 W-B3 那一處，而且在 `settle` 之後。
- **N177b-C10（新增）**：
  - N2、buy 句、sell 句、Q-c 句的分流只在 `_settled_line_note` 一處，每一列至多進入其中一句；
  - 「EMERGENCY 賣出」只用 `_is_exit_sell` 判斷，不得另寫 `rule_id == "EMERGENCY"`。
- **N177b-C11（新增）**：
  - 所有結算 warnings 的渲染結果都不得含子字串「None」，比對區分大小寫。範圍是 `SettlementResult.warnings` 的每一個元素，含 unsettled 理由、SUMMARY、W-B3、N2 與三句。
  - 既有的來源代碼 `none`（`NOTHING_LOADED`）是小寫，不在此限。
  - 唯一已知的例外見 3.11。
- **N177b-C12（新增）**：項目格式依 3.7 選用；`{items}` 的連接與排序依 3.7。

#### 3.10 測試修訂與追加（全部 BLOCKING）
- **N177b-T3（修訂）**：EMERGENCY 找不到批次。
  - 用 `batch_no` 為整數、批次列不存在的列；不得用 `batch_no` 為 None 的列（見 3.11）。
  - 斷言：只有 N2，沒有 buy 句、sell 句、Q-c 句；帳冊與現金不變。
- **N177b-T15（T24 的設定，S1 換成 EMERGENCY）**：
  - 設定同 T24：
    - 同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B；
    - 一批 open、remaining=100、cost 已設；
    - B 待結算 S2（100 股），已 claim；
    - T24 的 S1 換成同一批的 EMERGENCY 賣出；
    - A 側經 `PlaybookService` 的結算流程（`_settle_pending`）執行，使用 fake 日線，開盤價為 p1。
  - 注入點與 T24 相同：
    - hook 掛在 B 第一句寫入之前；
    - hook 中另開執行緒跑 A 的結算，最多等 0.5 秒後放行 B；
    - B 完成後 join A。
  - 斷言：
    - N2 恰好出現一次，項目是該批；
    - 沒有 sell 句、Q-c 句；
    - 該批 closed、remaining 0；
    - 現金 = 初值 + p2 × 100（EMERGENCY 入帳 0）；
    - S2 稽核列 = 該批 100 股。
  - 說明：A 的 claim 是寫入，會等 B commit 之後才執行，所以在這個設定下，舊的預讀也會讀到 0，N2 本來就會出現。本測試釘住「S2 先 commit 時 N2 不漏」，不證明 Q-g 的效力；效力由 T16 證明。
- **N177b-T16（R-2′ 的決定性交錯，證明 Q-g 的效力）**：
  - 設定同 T15。
  - 注入點改為：包住 A 的 store 的 `settle`，在它被呼叫時、委派給真實 `settle` 之前執行 hook。這是 R-2′ 的窗口：A 已經 claim（舊碼也已經預讀），但 A 的動帳交易還沒開始。
  - hook：以 B 跑完 `settle(S2)` 並 commit。此時 A 不持有寫鎖。
  - 斷言：N2 與帳冊的斷言同 T15。
  - 效力證明：PR 說明附上本機輸出，顯示把 N2 暫時換回「`settle` 之前以 `_batch_of` 預讀」的判定時，T16 會失敗（N2 沒有出現）。這份對照不 commit（比照 QB-11）。
- **N177b-T17（四句互斥與 N2 等價）**：
  - 窮舉：每一組實跑一次結算。組合如下：
    - action ∈ {buy, sell}；
    - rule_id ∈ {一個既有的 buy 規則, S1, P1, EMERGENCY, S2}；
    - status ∈ {executed, missed}；
    - `batch_no` ∈ {整數, None}；
    - 批次 ∈ {不存在, remaining 0, 0 < remaining < shares, remaining ≥ shares}。
  - 每一組的斷言：
    - 該列至多出現在 N2、buy 句、sell 句、Q-c 句其中一句；
    - 出現在哪一句（或都不出現），與 3.5 的分流結果相同。
    - 本項測的是分流，不是走不走得到，所以 app 走不到的組合也要跑。
  - 差分：
    - 固定 seed，至少 300 組隨機 book 與待結算列，循序執行；
    - 測試檔內放一份現行 N2 判定的參考實作：`settle` 之前以 `get_batch` 讀取，條件 `held is None or held.remaining_shares <= 0`；
    - 新舊兩者的 N2 項目集合與順序必須完全相同。
- **N177b-T18（四句同時出現）**：一次結算同時有 W-B3、N2、buy 句、sell 句、Q-c 句。斷言：
  - 順序是 SUMMARY → W-B3 → N2 → buy 句 → sell 句 → Q-c 句；
  - 每一列只出現一次；
  - `{items}` 以「、」連接，依 id 遞增。
- **N177b-T19（不得出現「None」）**：
  - 適用範圍：T1～T18 的每一個情境，加上專設的一組：buy 與逐批 sell 的 `batch_no` 為 None；EMERGENCY 的 `batch_no` 為整數而批次列不存在；G1 拒絕；沒有開盤價。
  - 斷言：`warnings` 的每個元素都不含「None」。
  - 3.11 的組合不納入，並在測試中以具名常數列出這項排除。
- **N177b-T20（項目格式的選用）**：
  - `batch_no` 為 None → `SETTLEMENT_UNBOOKED_ITEM_NO_BATCH`；
  - `batch_no` 為整數 → `SETTLEMENT_UNBOOKED_ITEM`；
  - Q-c 句一律用 `SETTLEMENT_UNBOOKED_ITEM`。
- **N177b-T21（單一來源，靜態檢查）**：AST 檢查以下各點：
  - `_settle_pending` 中 `_batch_of` 只出現一次，而且在 `self._store.settle(` 之後；
  - N2 與三句的清單只依 `_settled_line_note` 的回傳值 append；
  - service.py 除了 `_is_exit_sell`，沒有新增 `"EMERGENCY"` 字面。
- 修訂一的 N177b-T1～T14，除 T3 外都維持。T10、T12 不變。

#### 3.11 [待風控] EMERGENCY 的 `batch_no` 為 None，與 C11 的交集
- 依 3.6，EMERGENCY 的 `batch_no` 為 None 時，`missing_batch_row` 為真，進 N2，與現行相同。N2 的項目用 `SETTLEMENT_EXIT_ITEM`，會印出「第 None 批」（風控 RC-8 已核對）。
- 以下三條要求，在這個組合上無法同時成立：
  - 「所有結算 warnings 都不得出現『None』」（B 件實作條件 2）；
  - 「N2 的字面零 diff」（B 項 Q-g 第 4 點）；
  - 「EMERGENCY 找不到批次時只進 N2」（B 項 Q-g 第 2 點）。
- TA 的處理：
  - 依 RC-8，這個組合在 app 內走不到：EMERGENCY 列只從現存的批次產生，`batch_no` 一定是整數（service.py:414-420）。
  - 所以 C11 與 T19 排除這個組合，並以具名常數列出。
  - 不改 N2 的字面，也不新增 N2 的項目格式。
- 替代方案：為 N2 新增一個不含批次編號的項目格式，`batch_no` 為 None 時選用。這需要新字面，也會改動 N2 的組法，牴觸 N177b-C6。
- 請風控二選一：
  - (a) 接受上述排除；
  - (b) 要求新增項目格式，由 creative-lead 擬稿、風控定稿。

### 4. 6.9 (B) apply 工具的追加約束（擋 6.9 工具審查；[風控-177R2] C 項追加條件、D-13 第 3 點）
適用於 TA 日後另出的 6.9 spec；該 spec 不得放寬本節。

**4.1 寫入形式**
- **A1 `playbook_batches`**：
  - 只能 `UPDATE`。SET 只限 `remaining_shares`、`status`、`updated_at`，與 4.4、C6 是同一組欄位；WHERE 以 `symbol`、`batch_no` 定位。
  - 不得 `DELETE`，不得 `INSERT OR REPLACE`／`REPLACE INTO`。
  - [TA 補] 任何形式的 `INSERT` 都不得使用，含 `INSERT OR IGNORE`：工具不建立批次列。
- **A2 `playbook_fill_moves`**：只能用一般 `INSERT`，`source='repair'`；不得 UPDATE、DELETE。
- **A3 `playbook_state`**：
  - 只寫 `STATE_CASH`，形式與 `_write_state` 的 upsert 相同；
  - 值不得為 None，因為 `_write_state` 收到 None 會 DELETE 該鍵。
- **A4 `playbook_directives` 與其他表**：
  - 零寫入；
  - 任何表都不得 `DELETE`、`DROP`、`ALTER`；
  - schema 由新版 `_init_schema` 在 6.9 第 3 點的步驟中建立，不由工具建立。
- **A5 工具若 import `app.playbook.store`**：
  - 不得呼叫 `save_batch`、`set_cash`、`set_capital`、`ensure_batches`；
  - 不得以 None 值呼叫 `_write_state`／`_set_state`；
  - 可用的符號以 6.9 spec 的白名單為準。
- 理由：
  - 修訂一第 3 節 RC-8 論證第 4 點「批次列一旦存在就不會消失」，前提是沒有寫入者刪除或整列重寫批次列。
  - T19 的 AST 檢查只涵蓋 `app/`，而 6.9 工具在 `app/` 之外。

**4.2 輸入檔路徑**
- **A6**：
  - 適用的輸入檔：含金額的 CEO 確認、TA 逐案評估的分配與金額等。
  - 輸入檔路徑解析成實際路徑後，自身或任一上層目錄存在 `.git`（目錄或檔案都算）時，工具以 exit 4 拒絕執行。
  - 判定方式與 6.2 的 RC-5 相同：兩者共用同一份實作，或以同一組測試案例參數化。
- **A7**：拒絕必須發生在開啟 DB、建立備份、讀取輸入檔內容之前。
- **A8 [TA 補]**：備份目的地與 dry-run 的輸出檔，同樣不得位於 repo 工作樹內（判定同 A6），因為內容是帳冊複本。

**4.3 測試（BLOCKING；6.9 spec 的測試清單必須包含）**
- **AT-1 靜態**：掃描工具原始碼中所有字串常數（AST，含 f-string 的常數部分）：
  - 不含 `DELETE`、`INSERT OR REPLACE`、`REPLACE INTO`、`DROP`、`ALTER`，不分大小寫；
  - 以 `INSERT` 開頭的語句，只指向 `playbook_fill_moves` 與 A3 的 `playbook_state` upsert；
  - 沒有 A5 禁用方法的呼叫點。
- **AT-2 SQL trace**：對 fixture（含多批、部分關閉）實跑 apply：
  - 所有碰到 `playbook_batches` 的語句都是 `UPDATE`，SET 只含 A1 的三欄；
  - 沒有任何 DELETE。
- **AT-3 結果**：apply 前後：
  - `playbook_batches` 的列數與 `(symbol, batch_no)` 集合相同；
  - A1 三欄以外的欄位逐值相同；
  - `playbook_directives` 逐列相同。
- **AT-4 路徑**：
  - 輸入檔在含 `.git` 目錄的暫存樹內 → exit 4；
  - 在含 `.git` 檔案的暫存樹內 → exit 4；
  - 以 symlink 指向樹內 → exit 4；
  - 在樹外 → 正常執行；
  - exit 4 時，DB 檔雜湊不變，也沒有產生備份。
- **AT-5 [TA 補]**：備份目的地或輸出檔在樹內 → exit 4。

### 5. N-195：REBALANCE 不再寫 cash（R-1′；[風控-177R2] B 項選 (b)）

**5.1 定位**
- 小單 N-195（追蹤清單已開，P1），負責：dev-lead。
- 期限：
  - 目標與 R2 同一個 release；
  - 最遲與第三包同一個 release，不得更晚；
  - 不擋 N-177a 合併，也不擋 R2 部署。
- release 位置的推論：
  - 依 Q-e，第三包是 R2 之後的下一個 release，所以 N-195 只能搭 R2，或搭第三包的那個 release。
  - [TA 補] R2 依 RC-9 延後期間，N-195 不得單獨出 release。N-195 不屬於 hotfix。
- 範圍只限「REBALANCE 不再寫 cash」，依風控 B 項不必回風控；超出這個範圍就要回風控（含 5.6）。
- 不另立 ADR：這是移除一處既有的現金寫入，不是新增寫入路徑。歸屬記在 ADR-0041 的 Consequences 與「與其他 ADR 的關係」。

**5.2 程式事實**
- `rebalance` 的讀寫順序：
  - service.py:1535 讀批次（`list_batches`）；
  - :1537 載入日線；
  - :1538 讀 `portfolio_state()`；
  - :1612 寫入 `set_capital(cash=portfolio.cash, total_deploy=new_total_deploy, source=REBALANCE_SOURCE)`。
- `set_capital`（store.py:945-967）以一次 `_set_state` 寫四個鍵：`STATE_CASH`、`STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE`。
- REBALANCE 寫回的 cash，就是 :1538 讀到的值，本身不改變現金。寫它的唯一效果，是並發時把中間 commit 的結算現金異動蓋掉。

**5.3 規格**
- store.py：
  - 新增私有 helper `_total_deploy_state(total_deploy, source, at) -> dict[str, str]`，回傳 `STATE_TOTAL_DEPLOY`、`STATE_TOTAL_DEPLOY_SET_AT`、`STATE_TOTAL_DEPLOY_SOURCE` 三個鍵。值的格式與現行 `set_capital` 逐字相同：`str(total_deploy)`、`(at or datetime.now(UTC)).isoformat()`、`source`。
  - 新增 `set_total_deploy(*, total_deploy: Decimal, source: str, at: datetime | None = None) -> None`：內容是 `self._set_state(_total_deploy_state(...))`，只寫這三個鍵。docstring 註明 D-2 與 N-195。
  - `set_capital` 只允許改成 `self._set_state({STATE_CASH: str(cash), **_total_deploy_state(...)})`，寫入的鍵與值不變。
- service.py：
  - `rebalance` 只改 :1612 這一個呼叫，改為 `self._store.set_total_deploy(total_deploy=new_total_deploy, source=REBALANCE_SOURCE)`。
  - 其餘零 diff，包括：:1535、:1538 的讀取，總資產與 TOTAL_DEPLOY 的計算，`RebalanceResult`，REBALANCE 指令列，所有字面。

**5.4 約束 N195-C1～C8（qa-reviewer 逐條檢查）**
- **C1**：
  - diff 只含：store.py 中 5.3 的 helper、`set_total_deploy`、`set_capital` 的委派；service.py `rebalance` 中的那一個呼叫；`tests/**`。
  - engine.py、models.py、wording.py、`app/api/**`、`app/data/**`、`app/services/**` 零 diff。
- **C2**：
  - `rebalance` 不呼叫 `set_capital`、`set_cash`，也不寫 `STATE_CASH`；
  - `set_total_deploy` 不寫 `STATE_CASH`。
- **C3**：`confirm_rules` 的 `set_capital(cash=capital, …)`（W9）零 diff，仍然寫 cash（使用者宣告資金）。
- **C4**：三個鍵在同一個連線、同一個交易中寫入（`_set_state` 的 `with conn:`）。不加 `BEGIN IMMEDIATE`，不改 `_write_state`。
- **C5**：不得順手修改 TOTAL_DEPLOY 的計算輸入或讀取時點（見 5.6）；要改就回 TA 與風控。
- **C6**：
  - 狀態鍵的差異只有一處：`STATE_CASH` 鍵原本不存在時，REBALANCE 不再建立它。
  - `portfolio_state()` 對缺鍵回 `Decimal("0")`，所以讀到的值不變。
  - 既有測試若斷言 REBALANCE 之後的鍵集合，要逐條列在 PR 說明，交 qa 判定。
- **C7**：
  - 獨立 PR，以 merge commit 合入 product；
  - 不得併入 N-177a、N-190、N-188、N-189 的 PR；
  - 合入前 merge 最新 product（不得 rebase），之後重跑完整 CI 與 seam。
- **C8**：release 位置依 5.1。

**5.5 測試 N195-T1～T7（全部 BLOCKING）**
- **T1（循序）**：
  - REBALANCE 之後，TOTAL_DEPLOY、set_at、source 與現行相同；
  - `STATE_CASH` 的值與 REBALANCE 前逐字相同；
  - `test_playbook_rebalance.py` 的既有斷言原樣綠燈。
- **T2（SQL trace）**：
  - REBALANCE 對 `playbook_state` 的寫入，只有三句 upsert，鍵就是三個 TOTAL_DEPLOY 鍵；
  - 任何一句的參數都不含 `STATE_CASH`。
  - overshoot 時既有的指令列寫入不受影響。
- **T3（決定性交錯：並發結算的現金異動不會被 REBALANCE 蓋掉）**：
  - 設定：
    - 同一個 DB 檔開兩個 `PlaybookStore` 實例 A、B；
    - A 交給 `PlaybookService` 跑 `rebalance`；B 代表並發的結算請求；
    - 一批 open（remaining 100、cost 已設），有可用的估價。
  - 注入點：
    - 把 A 的 `_connect` 換成自訂 `Connection` factory；
    - 在 A **第一句寫入 `playbook_state`** 的 SQL 送出之前，執行 hook；
    - 修訂前，這個點是 `set_capital` 寫入之前；修訂後，是 `set_total_deploy` 寫入之前。兩者都在 :1538 讀取之後。
  - hook：以 B 跑完一筆結算並 commit。A 此時不持有寫鎖，所以 B 不必等待。結算參數化為三種：
    - 逐批 sell S1 40 股：入帳 p × 40；
    - 另一批 planned 的逐批 buy 100 股：扣款 p × 100；
    - N-177a 已在 base 時，加上 S2 100 股：入帳 p × Σmoved。
  - 斷言（與時序無關）：
    - 最終現金 = 初值 + 該筆結算的現金異動；
    - TOTAL_DEPLOY = A 依 :1538 讀值算出的值；
    - source = `REBALANCE_SOURCE`。
- **T3 的效力證明**：
  - PR 說明附上本機輸出，顯示把 :1612 暫時換回 `set_capital(cash=portfolio.cash, …)` 時，T3 的每一個參數都失敗（現金等於初值）。
  - 這份對照不 commit。
- **T4**：`confirm_rules` 仍然寫 cash。既有測試原樣綠燈；沒有涵蓋時補一則。
- **T5**：`set_capital` 改成委派之後，固定 `at`，寫入的四個鍵與值和修訂前逐字相同。
- **T6（AST）**：
  - `app/` 內 `set_capital(` 的呼叫點只在 `confirm_rules`；
  - `rebalance` 內恰好一個 `set_total_deploy(` 呼叫，沒有 `cash=` 關鍵字引數。
- **T7**：`STATE_CASH` 鍵不存在時跑 REBALANCE：鍵仍不存在，`portfolio_state().cash == Decimal("0")`。
- S2 參數的歸屬 [TA 補]：N-195 先於 N-177a 合併時，由 N-177a 的 PR 在 T3 追加 S2 參數，並列入 N-177a 的 QB-12 清單。

**5.6 觀察 [待風控]（不在 N-195 範圍）：REBALANCE 的總資產取自兩個不同時點的讀取**
- 程式事實：:1535 讀批次，:1537 載入日線（可能跨網路、數秒級），:1538 才讀現金。
- 兩次讀取之間如果有結算 commit：
  - 逐批 sell 或 S2：批次仍以舊股數計入市值，現金卻已含入帳。總資產重複計算，TOTAL_DEPLOY 偏高，方向不保守。
  - buy：現金已扣款，批次仍是 planned、不計入市值。總資產偏低，方向保守。
- 性質與範圍：
  - 這是修訂前就存在的「評估輸入過時」，不是寫入覆蓋；
  - N-195 只移除寫回，不改這一點；
  - N-177a 讓 S2 也加入這個窗口。
- 頻率：極低。REBALANCE 是手動、季末才跑；但窗口是日線載入期間，比 R-1′ 的毫秒級窗口寬。
- 可偵測性：
  - REBALANCE 的總資產、新舊 TOTAL_DEPLOY 會出現在回傳值與字面中；
  - 但現金沒有異動歷史，事後無法回推。
- 可能的修法（不在 N-195）：日線載入後，在同一個讀交易中重讀批次與現金，再計算。這會改變 REBALANCE 計算輸入的讀取時點，超出「不再寫 cash」，依風控 B 項要回風控。
- 請風控裁示：
  - (a) 接受為既有殘留；
  - (b) 併入 N-195，N-195 因此要回風控審查；
  - (c) 另開小單。
- TA 建議 (c)，期限比照 N-195。理由是讓 N-195 維持不必回審的範圍，趕上 R2。

### 6. 其他風控附條件的登錄（不改判斷；逐字以 [風控-177R2] 為準）
- 6.3 S8 的「（非預期值）」附 D-9：非預期值出現在某檔判定或試算用到的列時，該檔列為「需人工判讀」，不給試算金額（data-engineer）。
- 6.8 的 TA 逐案評估附 D-13 四點。第 3 點已寫入本修訂第 4 節 A6。
- 第 8 節的 R2 延後附 E 的三點條件（coordinator）。
- suggested：
  - 「service 不把 `LINE_BOUND_EFFECTS` 傳給 `apply_effects`」已由 `test_playbook_same_day_idempotency.py::test_evaluate_today_hands_no_line_bound_effect_to_apply_effects` 釘住；
  - buy 並發雙扣款記進 N-169；
  - R-1′ 修好前，以內部通知告知 CEO。

### 7. 修改處索引（風控比對用）
| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | 4.10 追加句（本修訂 1） | 取代，逐字採用 | B 項 4.10 |
| 1′ | 修訂一 1.3(5) 第一點 | 用語同步 [TA 補] | B 項理由 |
| 2 | 4.14 第 2 點（本修訂 2） | 取代 | B 項 4.14 |
| 3 | 修訂一 1.6 的狀態（本修訂 0） | 登錄 | A、B 項 |
| 4 | 第 5 節 `empty_batch_sell` 的定義（3.3） | 取代：拿掉 EMERGENCY 排除；`== 0` 改 `<= 0` | Q-g 第 1、2 點 |
| 5 | store 端回傳（3.4） | 新增 | Q-g |
| 6 | service 分流函式（3.5） | 新增 | Q-g 第 1、2 點 |
| 7 | 等價論證（3.6） | 新增 | Q-g 第 2 點、N177b-C9 |
| 8 | 字面、項目格式、順序（3.7） | 取代「暫定」 | B 件、實作條件 1～3 |
| 9 | RC-8 論證的前提（3.8） | 補充 | C 項追加條件 |
| 10 | N177b-C3、C5、C6、C9 取代；C10～C12 新增（3.9） | 約束 | Q-g 第 2、4 點、實作條件 2 |
| 11 | N177b-T3 修訂；T15～T21 新增（3.10） | 測試 | Q-g 第 3 點、實作條件 1、2 |
| 12 | 3.11 | [待風控] | 實作條件 2 與 Q-g 第 2、4 點的交集 |
| 13 | 6.9 的 A1～A8、AT-1～AT-5（本修訂 4） | 新增約束 | C 項、D-13 第 3 點 |
| 14 | N-195 spec（本修訂 5.1～5.5） | 新增 | B 項 R-1′ |
| 15 | 5.6 | [待風控] 觀察 | 新發現 |
| 16 | 本修訂 6 | 登錄 | D-9、D-13、E、suggested |

（修訂二由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。3.11、5.6 待風控裁示；ADR-0041 依 F 修正並經風控確認後才落檔。）

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

## 修訂四（tech-architect，2026-11-07；回應風控 [風控-196]）

- 依據：[風控-196] `work/reviews/2026-11-07-N177修訂三比對與N196spec審查-風控.md`。結論是 CONDITIONAL APPROVE：N-196 spec 核可，附三項 required；3.9 第 3 點接受為 R-4′；`confirm_rules` 的交錯要 TA 分析。
- 程式依據：同本檔第 6 行的 checkout，只讀，未執行。行號以內容定位。前端只用 grep 查證事實，沒有改動。
- 本修訂只取代或新增下面點名的段落，其餘維持修訂三。
- 標 [TA 補] 的是風控原文以外，TA 新增的約束或解讀；標 [待風控] 的需要風控裁示。
- 修改處索引見第 6 節。

### 0. 風控審查結果的登錄（不改判斷）
- N-196 spec 已核可，附三項 required，見第 1 節。C8 由 suggested 提升為 required，風控確認這是條件 1 能夠生效的前提。
- 3.9 第 3 點不另開單，接受為已知殘留。tech-writer 已落檔為 ADR-0041 R-4′（ADR-0041:107）。我目視比對過，與風控原文一致。
- CEO 通知的補充句由 coordinator 送達，最遲在下一次 REBALANCE 之前，本修訂不轉錄。前端名稱的事實見 3.6。

### 1. N-196 的修訂（required 與 suggested）

**1.1 3.9（第 3 點取代；新增第 4～6 點；第 1、2 點與末點不變）**
- 第 3 點（取代）：`evaluate_today` 在 :1901 讀批次、在 :1902 讀現金，分屬兩個連線。風控 2026-11-07 裁示接受為已知殘留、不另開單，已落檔為 ADR-0041 R-4′，含失效條款。N-196 不擴充（C10）。`evaluate_today` 日後若改用單一讀交易，依 C7 回 TA，並回風控審。
- 第 4 點（新增；逐字照 [風控-196] 第二節 2(e) 第 3 項）：「若 N-177a 的 R-α 被回退，而 N-196 保留，R-3′ 回到未修正狀態：coordinator 要通知風控，風控第二節第 5 點的 CEO 內部通知也恢復有效。」
- 第 5 點（新增；[風控-196] 2(f) suggested，採用）：
  - T3 的競態路徑（重讀後才出現、沒有載入日線的標的）會回 `REBALANCE_BLOCKED`。字面寫的是「{symbols} 沒有可用收盤價」，但在這條路徑上，資料其實有，只是這一輪沒有載入，所以字面不完全精確。
  - 方向是拒絕、不寫入，重跑一次就會恢復，沒有隱藏風險。依 C5，字面維持不改，列為已知限制。
- 第 6 點（新增）[TA 補]：
  - 第 1 點說「snapshot 之後、寫入之前 commit 的結算，等於循序」，這只適用於結算。
  - 同一個窗口內若有 `confirm_rules` 的 `set_capital` commit，結果不等於任何循序執行，見本修訂第 3 節。
  - N-196 不處理這一點（C10），由 N-197a 處理。修好之前，以風控補充的 CEO 通知揭露。

**1.2 N196-C8（取代；可檢查）**
- 實質要求不變：
  - PR 的 base 必須同時含 N-177a（R-α）與 N-195；
  - PR 在 N-195 合入 product 之後才開，不得與 N-195 並行修改 `rebalance`。
- `<base>` 的定義：以 qa 審查當下的 PR head 為準，`<base>` = `git merge-base <product 分支> <N-196 PR head>`。如果合入前又 merge 了最新的 product（C9），就以新的 head 重新計算。
- PR 說明必須列出：
  - N-177a、N-195 在 product 上的 merge commit，完整 40 碼 SHA，附 PR 編號；
  - `<base>` 的 SHA。
- 驗證條件，兩項都要成立：
  - `git merge-base --is-ancestor <N-177a merge commit> <base>` 的 exit code 為 0；
  - `git merge-base --is-ancestor <N-195 merge commit> <base>` 的 exit code 為 0。
- [TA 補，待風控確認執行方式] 執行與判斷分離：
  - 依 CLAUDE.md §4 與 `scripts/validate_agents.py` 的 `READONLY_ALLOWED_BASH`，qa-reviewer 目前只能執行 `codex` 與 `git diff`，不能執行 `git merge-base`。
  - **執行**：
    - (i) dev-lead 在 PR 說明附上兩條指令、stdout 與 exit code；
    - (ii) coordinator（或 devops-sre）在自己的 checkout 上獨立重跑，把輸出記在本案的審查紀錄（`work/reviews/`）。
  - **判斷**：qa-reviewer 比對 (i) 與 (ii) 的 SHA 和 exit code，再用 `git diff` 做內容旁證：
    - `git diff <N-177a merge commit> <base> -- apps/stock-desk/backend/app/playbook/store.py` 不得出現刪除 `_settle_batch_line`、`_settle_s2_fill`，或 `playbook_fill_moves` DDL 的 hunk；
    - `git diff <N-195 merge commit> <base> -- apps/stock-desk/backend/app/playbook/` 不得出現刪除 `set_total_deploy` 的 hunk。
  - 兩份輸出缺任何一份、彼此不一致，或旁證不成立，都判 BLOCKING。
  - 若要改由 qa 直接執行 `git merge-base`，要把它加進 `READONLY_ALLOWED_BASH`，這需要 TA 出 ADR、CEO 核可。本修訂不提出。
- **QB-N196-2（新增，BLOCKING）**：C8 的 SHA、兩份輸出與 `git diff` 旁證都要齊備，而且都成立。

**1.3 ADR-0041 R-3′「已修正」註記（交 tech-writer；時點受限）**
- 時點：N-196 以 merge commit 合入 product 之後才能落檔，由 coordinator 確認 merge commit 後通知 tech-writer。合入之前不得落檔。
- 位置：ADR-0041 Consequences 的 R-3′ 那一點（ADR-0041:106）末尾，作為補註。
- 逐字（照 [風控-196] 第二節 2(e) 第 2 項）：「R-3′ 由 N-196 修正；此修正以 N-177a 的 R-α（每筆結算的股數與現金在同一交易內 commit）為前提。」
- 時點要分清楚：
  - 這則註記在**合入**時落檔；
  - 風控第二節第 5 點的 CEO 內部通知，依 3.9 末點，維持到 N-196 **部署**為止。
- [TA 補] N-196 本身若被回退，coordinator 要請 tech-writer 撤回這則註記，並通知風控。R-α 被回退的情況，依 3.9 第 4 點處理。

**1.4 N196-T4（修訂；[風控-196] 2(f) suggested，採用）**
- 包裝 `_read_all_batches` 的 wrapper 改為：
  - 先呼叫原函式。
  - 只有在「hook 尚未觸發，而且 `conn.in_transaction` 為真」時，才執行 hook。後者表示這次呼叫位在 `read_rebalance_inputs` 的 DEFERRED 讀交易內；`list_batches` 的自動提交讀取不會觸發。
  - 先設旗標、再執行 hook。hook 執行期間如果有重入的呼叫（例如 B 端或 fixture 經由 `list_batches`），一律直接走原函式，不再觸發。
- 測試結束時斷言 hook 恰好觸發一次。觸發次數為 0 或大於 1，都算失敗。
- 其餘斷言不變，效力證明併入 QB-N196-1，也不變。

### 2. N-177b 的 suggested（[風控-196] 第二節第 1 點第 4、6 項；採用）

**2.1 N177b-T17 追加斷言第 3 點（取代）**
- 原句「該元素中『None』只出現一次（`count("None") == 1`），而且出現在『第 None 批』裡」，改為：
  - 設 n 為該次結算中 `is_c11_exception` 為真的列數（n ≥ 1）；
  - 斷言 N2 元素滿足 `count("None") == n`，而且 `count("第 None 批") == n`。
  - 兩者相等，就表示每一次「None」都出現在「第 None 批」裡。依據是 wording.py:956 的 `SETTLEMENT_EXIT_ITEM` 會組出「第 {batch_no} 批」。
- [TA 補] 網格至少要有一次結算的 n ≥ 2，也就是兩筆 `batch_no` 為 None 的 EMERGENCY executed sell，symbol 或預定執行日不同，讓泛化後的斷言真的被執行到。
- 其他斷言不變：恰好一個元素含「None」，而且它就是 N2；逐字等於格式化結果；其他元素不含「None」；fixture 不得含「None」。

**2.2 N177b-T22（追加 (c′)；(a)(b)(c) 不變）**
- 掃描範圍：`app/playbook/**`，以及 `app/` 內任何 import 了 `Directive` 的模組（以 AST 的 import 判定，不寫死清單）。
- (c′-1) EMERGENCY 名稱集合：範圍內模組層級以 Assign 或 AnnAssign 綁定到 `ast.Constant("EMERGENCY")` 的名稱，由測試計算，不寫死。現況只有 store.py:291 的 `EMERGENCY_RULE_ID`。
  - `Directive(...)` 的 `rule_id=` 值符合以下任一種，就算作 EMERGENCY 建構：
    - `ast.Constant("EMERGENCY")`；
    - `ast.Name`，id 屬於上述集合；
    - `ast.Attribute`，attr 屬於上述集合。
  - 範圍內的總數恰好一處，就是 (c) 的那一處。
- (c′-2) `X.model_copy(update=<Dict 字面>)` 的 Dict 中，含鍵 `"batch_no"` 或 `"rule_id"` 的呼叫，數量為 0。
  - 現況我 grep 過：`app/` 內 `"batch_no":` 為 0 處；`"rule_id":` 只有 `app/api/alerts.py:261` 一處，是回應用的 dict，不是 `model_copy`。
  - `"rule_id"` 是我加的 [TA 補]：把別的 Directive 複製成 EMERGENCY，也是同一種繞過。
- (c′-3) 無法靜態判讀的形式，以 baseline 釘住，只准調低：
  - `Directive(...)` 帶 `**` 展開，或 `rule_id=` 的值不是 Constant、Name、Attribute；
  - `model_copy(update=...)` 的 update 不是 Dict 字面，或 Dict 帶 `**` 展開。
  - 以具名常數列出 (檔案, 函式, 計數)，PR 附上對 N-177b base 的實測值，比照 T21。N-177a 的 R-α 會改寫 store.py 的 `_update_batch` 與 settle 的 sell 分支，所以 base 的計數要實測，不能沿用本 checkout。
  - 調高要回 TA。
- 失敗時，依 N177b-C13 的回復條款處理。

### 3. N-197 (a)：`confirm_rules` 與 REBALANCE 並發（[風控-196] 第二節第 4 點）

**3.1 程式事實（只讀）**
- REBALANCE（`service.rebalance`，:1516 起）的步驟：
  - R1：:1535 `list_batches`，只用來決定 symbols；
  - 載入日線，數秒級；
  - **R_s**：snapshot 讀取。N-196 之前是 :1538 `portfolio_state()`；N-196 之後是 `read_rebalance_inputs()`。讀到現金 C0、持股，以及 TOTAL_DEPLOY 的三個鍵；
  - R_p：:1539 `active_params(as_of)`，獨立連線；
  - 純計算：TA = C0 + D，TD′ = TA·r；
  - **R_w**：寫入。N-195 之前是 :1612 `set_capital(cash=C0, total_deploy=TD′, source=REBALANCE_SOURCE)`，四個鍵；N-195 之後是 `set_total_deploy`，三個鍵。
  - R_s 到 R_w 之間沒有網路，窗口是毫秒級。
- `confirm_rules`（:1722-1739）的步驟，每一步各開連線、各自一個交易：
  - C_a：`rule_set_authorship`。
  - 尚未確認過時，另外執行：
    - `active_params`，這時回的是 `system_default_params`（store.py:724-732，`RuleParams(effective_date=on_date)`）；
    - `next_version`；
    - `_evaluation_data_date`：`list_batches` 加上日線與指數載入，數秒級；
    - **C_α**：`confirm_rule_set`。交易 α 以 `INSERT OR REPLACE` 寫 params 列；交易 β 由 `_set_state` 寫 confirmed_at 與 version（store.py:1098-1123）。
  - **C_p**：:1733 `active_params(as_of)`。
  - **C_w**：:1734 `set_capital(cash=X, total_deploy=X·r, source=CONFIRMATION_SOURCE)`，單一交易寫四個鍵（store.py:945-967、:925-927）。
  - `_rule_set_status`：回應中的 portfolio 在 C_w 之後讀取。
- 符號定義：C0 是 R_s 讀到的現金；X 是使用者送出的資金；D 是 R_s 讀到的持股以收盤估值；r 是 deploy_ratio；t_r、t_c 是兩者的寫入時刻。
- 循序結果：
  - S1（先確認、再 REBALANCE）：現金 X，TD = (X + D)·r，source 為 rebalance，set_at 為 t_r。
  - S2（先 REBALANCE、再確認）：現金 X，TD = X·r，source 為 user_confirmation，set_at 為 t_c。

**3.2 交錯表：N-195 之前（現行 production）**

| # | C_w 的位置 | 可能的起始先後 | 最終現金 | 最終 TD | source／set_at | 等於 | 偏差 |
|---|---|---|---|---|---|---|---|
| 1 | C_w < R_s | confirm 先開始；或 REBALANCE 先開始，但還在載入日線 | X | (X+D)·r | rebalance／t_r | S1 | 無 |
| 2 | R_s < C_w < R_w | 兩邊都可能先開始。首次確認在 C_w 之前也有數秒的日線載入，所以「confirm 先開始」也可能落在這一列 | **C0**（X 被蓋回） | (C0+D)·r | rebalance／t_r | 都不是，等同「這次確認沒有發生」 | 使用者剛填的資金無聲消失。confirm 回應若在 R_w 之前讀 portfolio，會顯示 X。X < C0 時，現金與 TD 都偏高，鐵律①的 budget 也以 C0 計算，方向不保守；X > C0 時兩者都偏低 |
| 3 | R_w < C_w | REBALANCE 先開始 | X | X·r | user_confirmation／t_c | S2 | 無 |

- 第 1、3 列仍有 R-1′（REBALANCE 寫回現金，蓋掉並發結算），那是另一件事，由 N-195 修正。

**3.3 交錯表：N-195 之後（N-196 前後相同，只差 R_s 的位置）**

| # | C_w 的位置 | 最終現金 | 最終 TD | source／set_at | 等於 | 偏差 |
|---|---|---|---|---|---|---|
| 1 | C_w < R_s | X | (X+D)·r | rebalance／t_r | S1 | 無 |
| 2 | R_s < C_w < R_w | X | **(C0+D)·r** | rebalance／t_r | 都不是 | TD 與 S1 相差 (C0 − X)·r，見 3.5 |
| 3 | R_w < C_w | X | X·r | user_confirmation／t_c | S2 | 無 |

**3.4 `confirm_rules` 自身的非原子序列，以及與 R_p 的版本交錯**
- 首次確認的路徑：
  - 尚未確認時，`playbook_rule_params` 一定是空的。`rule_set_authorship` 只要有任何一列 params，就判定為已確認（store.py:1085-1088）。
  - 所以 C_α 寫入的 payload，是 `system_default_params` 的複本，只改了 version 與 effective_date（service.py:1724-1731）。
  - R_p 落在交易 α 之前，讀到系統預設；落在 α 之後，讀到新列。兩者的 deploy_ratio 相同，所以 TD 不受影響。
  - R_s 是否看得到交易 β 的 confirmed_at／version 鍵，REBALANCE 都不使用。
- 已確認過的路徑：`confirm_rules` 不寫 params，C_p 和 R_p 都是單句 SELECT。
- 第三方的參數變更：鐵律④規定變更在下一個交易日才生效，所以同一個 as_of 讀不到。
- 唯一的例外是兩次呼叫跨過 UTC 日界，as_of 不同。這時兩邊各自採用自己當天生效的版本，與循序執行相同，不產生新的偏差類型。
- 結論：
  - 版本交錯不產生額外偏差，偏差只來自 C_w 的位置（第 2 列）。
  - N196-C5 讓 `active_params` 留在 snapshot 之外，這個安排是安全的。
  - [TA 補，範圍外] 兩次首次確認並發時，兩邊會取到同一個 `next_version`，`INSERT OR REPLACE` 之後只會留下一列，不影響 REBALANCE。

**3.5 偏差方向與影響面（第 2 列，N-195 之後）**
- TD − max(S1, S2) = (C0 − X)·r。理由是 D ≥ 0，所以 S1 ≥ S2。
  - X < C0（調降資金）：TD 高於兩種循序結果，方向不保守，而且鎖定到下一次 REBALANCE 或下一次 `confirm_rules`。
  - X > C0：TD 低於 S1。若 C0 + D < X，也低於 S2，偏保守；否則介於兩者之間。
- 影響途徑：TD 只進入 `planned_batch_shares`（engine.py:176-205，每批金額 = TD ÷ n_targets ÷ 3），也就是 R1 的每批股數會偏大。
- N-195 之後，鐵律①（engine.py:1021-1027，`budget = cash − 0.3 × 總資產`）用的是正確的現金 X，所以 30% 現金底線仍然成立。偏差只放大每批股數，最多放大到底線為止。N-195 之前，底線本身就以錯誤的 C0 計算。
- 首次確認的情況：確認前 C0 = 0（`STATE_CASH` 只由 `set_capital` 建立；REBALANCE 寫回的也是 0），D = 0（確認前沒有 R1，不可能有 open 批次）。
  - N-195 之後：TD = 0，偏保守。但 R1 的每批股數會因為 `max(1, …)` 變成 1 股，直到下一次 REBALANCE 為止。
  - N-195 之前：現金被寫回 0，所有買單都依 `SHRINK_TO_ZERO_NOTE` 被剔除，使用者看得到。
  - 這兩種情況在前端都沒有自行修正的入口，見 3.6。

**3.6 頻率（讀碼與前端 grep 的事實）**
- 前端沒有任何呼叫 `POST /api/playbook/rebalance` 的 client。frontend/ 內 grep「rebalance」為 0；「REBALANCE」只出現在 `types.ts:1699` 的 rule id 型別。所以 REBALANCE 目前只能由使用者直接呼叫 API。
- 資金輸入的 UI（`RuleSetConfirmPanel.tsx`，按鈕「確認規則集並設定資本額」）只在 `mode === "unconfirmed"` 時渲染（`playbookView.ts:322-324`、`page.tsx:204`）。確認之後再改資金，也只能直接呼叫 API。
- 所以只用 UI 時，首次確認的 X ≥ C0 = 0，走不到不保守的分支。不保守的分支需要「已確認之後，以 API 調降資金」，同時「以 API 執行 REBALANCE」，而且寫入要落在毫秒級的窗口內。
- 判定：頻率極低。依風控 5.6 的同一理由，頻率低不構成免修的理由。
- 給 coordinator：CEO 通知中「資金確認」與「執行 REBALANCE」的對應名稱，以上事實可供參考。若因為沒有 UI 入口而無法只改名稱，依風控規定回風控，不得改意思。

**3.7 可偵測性**
- N-195 之後的第 2 列，與第 1 列的狀態形狀相同：source 都是 rebalance，set_at 都是 t_r，現金都是 X，只有 TD 的值不同。要區分兩者，需要 R_s 當時的 C0 與 D。
  - 現金沒有異動歷史（ADR-0035 Decision 9）；
  - D 只出現在 REBALANCE 的回應裡，只有超額時才落成指令列的 rule_summary；
  - `confirm_rules` 的 set_at／source 被 R_w 覆寫。已確認過的再次確認不留其他落檔紀錄：`STATE_RULE_SET_CONFIRMED_AT` 與 params 的 `submitted_at` 只在首次確認時寫入。
- 判定：`set_at`、`source` **不足以事後辨識**，DB 內沒有可以回推的資料。N-195 之前的第 2 列，只有使用者自己記得填過的金額時，才可能察覺。

**3.8 候選修法比較**

| 方案 | 內容 | 優點 | 缺點 | 風險 | 判定 |
|---|---|---|---|---|---|
| F-a 戳記比對（風控方向，TA 強化） | `set_total_deploy` 在單一 `BEGIN IMMEDIATE` 內，讀取 TOTAL_DEPLOY 三個鍵的原始字串，與 N-196 snapshot 讀到的值比對；相同才寫入，不同就不寫入，並揭露 | 加法，不動 N-196 的讀交易；結算不寫這三個鍵，所以不會誤拒，3.9 第 1 點的語意維持；結果一定等於某一個循序執行，或「REBALANCE 未執行」 | 新增一個拒絕狀態與一句字面（creative-lead 擬稿、風控逐字）；models 的 Literal 做加法；局部取代 N195-C4 | 低 | **採用**，另開 N-197a |
| F-a′ 戳記比對加自動重試 | 拒絕寫入後重讀、重算一次 | 使用者不必重跑 | 等於替使用者無聲選定 S1 的順序 | 中 | 否決 |
| F-b 單一寫交易 | REBALANCE 的讀、算、寫都在一個 `BEGIN IMMEDIATE` 內（`commit_emergency_exit` 的模式） | 永遠等於某一個循序執行；沒有拒絕路徑，也沒有新字面 | 推翻已核可的 N-196（C2 規定 DEFERRED、T4「寫入者不被擋」、T5）；估值要在寫鎖內做；要重送風控，N-196 可能趕不上 R2 | 中 | 現在否決，保留為日後方向 |
| F-c confirm 端偵測 | confirm 寫入前，檢查是否有 REBALANCE 正在進行 | — | 沒有「進行中」的標記，要新增 state 鍵與清除邏輯；當機時標記會殘留 | 中高 | 否決 |
| F-d 行程內鎖 | service 層用 `threading.Lock` 包住兩者 | 簡單 | 只在單一行程內有效（R-β 先例）；SQL trace 看不到，qa 無法檢查 | 中 | 否決 |
| F-e 接受為殘留 | 只靠 CEO 通知 | 零改動 | TD 是風險上限，偏差不保守、鎖定一季；事後偵測不到 | 中 | 不建議；若 CEO 決定採用，風控已表示會書面保留不同意見 |

- 對風控方向的評估：方向成立，TA 做三點強化。
  - (1) 比對三個鍵（TD、set_at、source）的原始字串，不只比 set_at，也不比解析後的值。這樣可以避免時間戳解析度造成的 ABA；Windows 上 `datetime.now` 的解析度我沒有查證。三個值完全相同，就表示資金宣告等價，不會造成實害。
  - (2) 比對與寫入必須在同一個寫鎖交易內，否則「先檢查再寫入」本身又是一個競態。
  - (3) 戳記取自讀取現金的同一個 snapshot，N-196 的 state 讀取本來就含這三個鍵。
- 為什麼戳記就夠：
  - N-195 之後，結算以外的現金寫入者只剩 `set_capital`。依 N177a-T19，`set_cash` 在 `app/` 內沒有呼叫點；依 N195-T6，`set_capital` 只在 `confirm_rules` 被呼叫。
  - `set_capital` 在同一個交易內寫戳記（N195-C4）。
  - 所以「戳記不變」等價於「snapshot 之後沒有資金宣告寫入」。

**3.9 N-197a spec 草案（暫定編號，coordinator 登錄時可改；送風控審）**
- 定位：
  - 小單，負責 dev-lead。base 必須含 N-195 與 N-196，以 N196-C8 的同一種方法驗證。
  - 期限：最遲與第三包同一個 release。R2 延後期間不得單獨出 release，也不屬於 hotfix。
  - 不擋 N-196，也不擋 R2。
  - 在 N-197a 上線之前，第 2 列是殘留，以風控補充的 CEO 通知揭露，並登錄 ADR-0041 R-5′（第 5 節草稿）。
- store.py（各只有一份定義）：
```python
class TotalDeployStamp(NamedTuple):
    """The three TOTAL_DEPLOY keys exactly as stored; None where a key is absent (N-197a)."""

    total_deploy: str | None
    set_at: str | None
    source: str | None


class TotalDeployWrite(NamedTuple):
    """What :meth:`PlaybookStore.set_total_deploy` found under the lock, and whether it wrote."""

    written: bool
    found: TotalDeployStamp


def _total_deploy_stamp(state: Mapping[str, str]) -> TotalDeployStamp: ...
    # the three keys STATE_TOTAL_DEPLOY / _SET_AT / _SOURCE, raw, None if absent


def _read_total_deploy_stamp(conn: sqlite3.Connection) -> TotalDeployStamp: ...
    # one SELECT key, value FROM playbook_state WHERE key IN (?, ?, ?); then _total_deploy_stamp
```
  - `RebalanceRead` 加法新增 `stamp: TotalDeployStamp`。`read_rebalance_inputs` 內只讀一次 `state = _read_state_map(conn)`，同時交給 `_portfolio_from_state` 與 `_total_deploy_stamp`。仍然只有兩句 SELECT，N196-C2 不變。
  - `set_total_deploy` 取代 N-195 5.3 的簽名，`expected` 是必填，沒有預設值：
```python
    def set_total_deploy(
        self, *, total_deploy: Decimal, source: str, expected: TotalDeployStamp,
        at: datetime | None = None,
    ) -> TotalDeployWrite:
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                found = _read_total_deploy_stamp(conn)
                written = found == expected
                if written:
                    _write_state(conn, _total_deploy_state(total_deploy, source, at))
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        return TotalDeployWrite(written=written, found=found)
```
- service.py `rebalance`：只改 N-195 那一個呼叫，並新增拒絕分支：
```python
        write = self._store.set_total_deploy(
            total_deploy=new_total_deploy, source=REBALANCE_SOURCE, expected=book.stamp
        )
        if not write.written:
            message = wording.REBALANCE_SUPERSEDED.format(...)  # fields below
            return RebalanceResult(
                executed_at=as_of, status="superseded", total_assets=None,
                previous_total_deploy=Decimal(write.found.total_deploy or "0"),
                new_total_deploy=None, deployed_value=None, overshoot=None,
                directives=[], message=message, warnings=[message],
            )
```
- models.py：`RebalanceResult.status` 改為 `Literal["ok", "insufficient_data", "superseded"]`，只做加法。
  - `app/api/playbook.py:189` 的 `RebalanceResponse.status` 是 `str`，零 diff。
  - 前端沒有使用這個回應（3.6），零 diff。
- 字面：識別名暫定 `REBALANCE_SUPERSEDED`，只放在 wording.py，由 creative-lead 擬稿、風控逐字定稿。
  - 可用欄位：`found.total_deploy`（格式 .2f）、`found.set_at`。
  - 只陳述事實：本次 REBALANCE 執行期間，TOTAL_DEPLOY 已被另一項操作改寫；本次沒有寫入任何值；目前的 TOTAL_DEPLOY 是多少；要以目前的資金重算，需要再執行一次 REBALANCE。
- 約束 N197a-C1～C10（qa-reviewer 逐條檢查）：
  - **C1 diff 範圍**：
    - store.py：上面兩個型別、兩個 helper、`RebalanceRead` 的欄位、`read_rebalance_inputs` 內共用 state map、`set_total_deploy`；
    - service.py `rebalance`：只有該呼叫與拒絕分支；
    - models.py：Literal 加法；
    - wording.py：一個常數；
    - `tests/**`。
    - engine.py、`app/api/**`、`app/data/**`、`app/services/**`、frontend 零 diff。
  - **C2 交易**：
    - 一個連線、一個 `BEGIN IMMEDIATE`；
    - 對 `playbook_state` 恰好一句 SELECT，只限三個鍵；
    - 接著 0 句或 3 句 upsert（經 `_write_state`），然後 `COMMIT`；
    - 沒有其他語句，不呼叫其他 `self.*`，沒有網路；錯誤處理照 C-11。
  - **C3 比對**：三個原始字串（鍵不存在為 None）全部相等才寫入。不比對現金，不比對解析後的值。
  - **C4 rebalance**：
    - `set_total_deploy(` 恰好一次，`expected=` 只能是 `book.stamp`，`book` 是同一次 `read_rebalance_inputs()` 的結果；
    - 不重試、不重讀；
    - 拒絕時不呼叫 `record_directives`，也沒有其他寫入。
  - **C5**：`set_capital`、`confirm_rules` 零 diff。confirm 維持無條件寫入，也就是後寫者為準（W9）。
  - **C6 不變式**：`app/` 內結算 helper 以外，任何寫 `STATE_CASH` 的函式，都必須在同一個交易內寫入三個 TOTAL_DEPLOY 鍵（現況只有 `set_capital`）。新增這類寫入者時，要回 TA 與風控。
  - **C7**：N196-C2、C3、T4、T5 不變。N195-C4「不加 `BEGIN IMMEDIATE`」只對 `set_total_deploy` 失效；`_set_state`、`_write_state`、`set_capital` 不變。
  - **C8**：base 與先後依 N196-C8 的同一種方法驗證，對象改為 N-195、N-196 的 merge commit。
  - **C9**：獨立 PR，以 merge commit 合入；不得併入其他單；合入前 merge 最新的 product（不得 rebase），之後重跑完整 CI 與 seam。
  - **C10**：字面在風控逐字定稿之前不得合併，PR 以程式從風控原檔逐字比對。
- 測試 N197a-T1～T9（全部 BLOCKING；用真實 `PlaybookStore`、檔案型 DB）：
  - **T1 循序**：N195-T1～T7、N196-T1～T7 原樣綠燈。只有直接釘住 N195-C4 的斷言可以修改，要逐條列在 PR 說明，交 qa 判定。
  - **T2 決定性交錯**：
    - A 跑 `rebalance`。把 A 的 `_connect` 換成自訂 factory，在 `set_total_deploy` 的 `BEGIN IMMEDIATE` 送出之前，以另一個 store／service 實例 B 完成 `confirm_rules(capital=X)`。
    - 參數化 X < C0、X > C0、X = C0。X = C0 時 set_at 不同，仍然要拒絕。
    - 斷言：`status == "superseded"`；最終四個鍵逐字等於 B 寫入的值；沒有 REBALANCE 指令列；`message` 逐字等於格式化後的字面。
  - **T2 的效力證明**：PR 說明附上本機輸出，顯示把比對暫時拿掉、改成無條件寫入時，三個參數都失敗，TD 變成 (C0 + D)·r。這份對照不 commit（比照 QB-11）。
  - **T3**：同一個注入點改為由 B 完成一筆逐批 S1 結算 → `status == "ok"`，寫入成功，最終現金 = C0 + 該筆入帳。這證明結算不會造成誤拒。
  - **T4**：同一個注入點改為由 B 完整跑一次 REBALANCE → A 被拒，最終狀態等於 B 寫入的值。
  - **T5（寫鎖序列化）**：在 A 的比對 SELECT 之後、upsert 之前，另開執行緒跑 B 的 `confirm_rules`。B 的 `set_capital` 要等到 A commit 之後才完成，而且在 busy_timeout 內完成。最終結果等於 S2。
  - **T6 SQL trace**：比對交易的語句序列，依 C2。三個 upsert 的參數都不含 `STATE_CASH`。
  - **T7 AST**：
    - `set_total_deploy` 的 `expected` 沒有預設值；
    - `app/` 內 `set_total_deploy(` 只出現在 `rebalance`；
    - `expected=` 的運算式是 `book.stamp`。
  - **T8**：snapshot 時三個鍵都不存在、寫入時仍然不存在 → 寫入成功。snapshot 時不存在、窗口內 B 完成首次確認 → 拒絕。
  - **T9**：字面逐字比對風控原檔。
- QB-N197a-1：T2 的效力證明附在 PR 說明。

### 4. N-197 (b)：兩個 `/today` 並發時的重複 buy（[風控-196] 第二節第 3 點「另外的觀察」）

**4.1 路徑走得到嗎：走得到（讀碼推論，未實跑）**
1. A、B 兩個請求都已確認規則，同時 `GET /today`。API 是同步的 `def`（`app/api/playbook.py:582`），在 threadpool 中並行，沒有任何鎖。
2. 有一筆到期的 R1 buy r：批次 k 是 planned，預定執行日 E ≤ as_of，E 的開盤 bar 已存在。
3. B 執行 `claim_directive(r)` 並 commit（store.py:1453-1460，單句 UPDATE；r 變成 settled=1、executed）。
4. A 跳過 r，有兩種情形：
   - A 的 `pending_directives` 在第 3 步之後才讀，r 不在清單內；
   - 或 A 的 claim 回 False，`batch_blocking_claim` 回 None（因為 settled=1），A 執行 `continue`（service.py:1339-1356）。
5. B 的 `settle(r)` 尚未 commit：
   - N-177a 之前，要到 `save_batch` 才把 k 改成 open（store.py:1521-1557，五個連線）；
   - N-177a 之後，要到 `_settle_batch_line` 的 COMMIT。
6. A 執行 :1861 `read_in_flight` → :1862 `list_batches` → :1864-1865 載入日線與指數 → :1898 `roll_peak_closes` → **:1901 `list_batches`，讀到 k 仍是 planned**。
   - 只有 :1901 會進入 engine。:1862 只決定要載入哪些 symbol，而且本來就包含 planned 批次。
   - 所以 B 的 commit 若落在 :1862 與 :1901 之間，A 會讀到 open，等同循序執行，沒有問題。
7. engine 這邊：若 data_date 是排程日（週二或週四，而且是交易日；`calendar.py:52`、`:87-89`），而且 `entries_allowed`（正常模式、指數可用；engine.py:1168），`_next_planned_batch`（engine.py:722-734）會選中 k。若 k 沒有被 R2／R3 處理，就產出 R1 buy，預定執行日 E_A = next_trading_day(data_date) > E。
8. A 執行 `commit_evaluation`：K1 是 `(s, k, R1, buy, E_A)`，K2 是 `(s, E_A)`，都是新的鍵，所以這張 buy 會寫入。
- data_date 是排程日的情況：使用者在 E 當天沒有開 `/today`，到之後的排程日才開；或休市讓 E 落在週二或週四。依日常用法，這不罕見。
- 窄的條件在第 5、6 步之間：B 從 claim commit 到動帳 commit 只有毫秒級，A 卻要經過兩次日線載入（即使命中快取，也比 B 的窗口長）。B 必須停頓得比這段更久，例如等寫鎖（busy_timeout 5 秒）、執行緒排程，或磁碟慢。
- **[TA 補] 失敗變體**：B 在 claim 之後動帳失敗，例如 `database is locked`、行程終止，或 N-177a 之前在 `set_cash` 與 `save_batch` 之間失敗。這時 k 會一直停在 planned，**不需要並發**，之後的排程日也會對 k 再出 R1。而且這時 G1 不會擋（k 仍是 planned），帳冊只記一次成交。

**4.2 現有機制是否涵蓋**

| 機制 | 涵蓋嗎 | 理由 |
|---|---|---|
| in-flight 讀取（:1861） | 否 | 只讀 settled=0 的列，而 r 在第 3 步之後是 settled=1；而且 in-flight 不是 engine 的輸入，engine 的批次來自 :1901 |
| K1／K2（`commit_evaluation`） | 否 | 鍵含預定執行日。E 的開盤 bar 存在，所以 E ≤ data_date < E_A，鍵不同 |
| N-182 E-2 | 否 | E-2 處理的是揭露：前提是同一批已經有兩筆買單，ENTRY／A 誤述其中一筆。本路徑是**產生**那第二筆買單。產生之後，A 的回應有可能觸發 E-2 那一種誤述：`blocked` 取自 :1861，當時 k 仍是 planned。這一點是讀碼推論，我沒有逐字核對 `same_day_warnings` 的觸發條件 |
| G1（ADR-0035 Decision 6′） | 部分 | 只保護帳冊：E_A 的結算會被 G1 拒絕（k 已是 open），列入 unsettled，附 `SETTLEMENT_BATCH_ALREADY_FILLED_NOTE`（wording.py:963-969，已寫明「若已買進且成交，你在券商的這檔持股可能多於帳冊所記」），之後每次結算都會再列出。但這是事後揭露，指令已經送到使用者手上。失敗變體不受 G1 保護 |
| F2／N-169 | 根源 | 這是 claim 與動帳分屬兩個交易時，被並發讀取者看到的那個窗口。追蹤清單 N-169 只把 F2 登錄為 low，沒有寫出「對同一批再出 R1」這個後果。我只核對了追蹤清單第 264 列與 ADR-0041:112、:127 |

**4.3 影響**
- 使用者可能在券商多買一批，股數 ≈ TD ÷ n_targets ÷ 3 ÷ 收盤價，帳冊不會記錄。
- 循序執行時，同一個排程日本來就會對 k+1 出 R1。並發時改成對 k 出單，之後的排程日 k+1 照樣會出單。結果是券商持股比帳冊多一批，該檔的配置超出一批。
- 若 k 是最後一批，循序執行時根本不會出單，並發時則多出一張。
- 若 A 的 :1902 也早於 B 的 commit，鐵律①的 budget 會以扣款前的現金計算，比實際寬鬆 r 的成本。
- 可偵測性：
  - 並發變體：DB 中同一批有一筆 executed buy 與一筆被 G1 拒絕的 pending buy，可以查得到；使用者也會看到 G1 的句子。
  - 失敗變體：DB 中有 executed buy，但批次仍是 planned，可以查得到；但使用者看不到任何揭露。

**4.4 修法選項與歸屬**

| 方案 | 內容 | 優點 | 缺點 | 判定 |
|---|---|---|---|---|
| (b-i) 合併 claim 與動帳 | claim 與動帳在同一個 `BEGIN IMMEDIATE` 內（N-169 的 F2 修法） | 根治兩種變體：失敗時兩者都不發生，列維持 pending，之後重試 | 會動到 `claim_directive`／G1 的結構與 `_settle_pending`（ADR-0040 Decision 14 第 3 點、N177a-C2 的零 diff 約束）；要另立 ADR | **TA 建議作為 N-169 的修法方向** |
| (b-ii) 鎖內 G0 守衛 | 在 `commit_evaluation` 的 `_new_decisions` 中，若 (s, k) 已有 settled=1 且 executed 的 buy 列，就不寫這次新的 R1 | 在鎖內判斷是可靠的：第 3 步的 claim 一定已經 commit；不變式「批次是 planned，卻有 executed buy 列」只會出現在 F2 窗口或失敗後 | 動到 ADR-0035 擁有的 K 邏輯；並發變體會讓當天少出單；失敗變體會讓 k 永久停住，需要新的揭露字面 | 只在風控認為 N-169 落地之前不能接受時，才作為過渡方案 |
| (b-iii) 書面殘留 | 登錄 ADR-0041 R-6′ 與 N-169，依靠 G1 的事後揭露 | 零改動 | 並發變體只有事後揭露；失敗變體沒有揭露 | TA 建議現在先採 (b-iii)，修法方向是 (b-i)；要不要補揭露、要不要提高 N-169 的優先度，由風控決定 [待風控] |

- 不動 `rebalance` 或 `set_total_deploy`，所以 N-196 spec 不修訂，也不另開 N-196 的小單。

### 5. ADR-0041 殘留登錄草稿（[待風控]：風控定稿後交 tech-writer，放在 Consequences 的 R-4′ 之後）
- R-5′ 草稿：「R-5′：REBALANCE 讀取 snapshot 之後、寫入 TOTAL_DEPLOY 之前，若 `confirm_rules` 寫入資金，最終現金是新填的資金，TOTAL_DEPLOY 卻依舊現金算出，不等於任何循序結果；使用者調降資金時偏高（N-195 之前，新填的資金還會被蓋回舊值）。事後無法從帳冊辨識。處理：N-197a 在寫入時比對 snapshot 的 TOTAL_DEPLOY 戳記，不一致就拒寫並揭露；期限最遲第三包；修好之前，這個交錯仍在（[TA-177S] 修訂四第 3 節）。」
- R-6′ 草稿：「R-6′：claim 與動帳分屬兩個交易（F2）。並發的 `/today` 若在另一請求 claim 某筆買進之後、動帳 commit 之前讀到批次，會把該批看成仍待買進，排程日可能對同一批再出一張 R1 買進指令；帳冊由 G1 擋下並在之後的結算揭露，但使用者可能已在券商下單。claim 之後動帳失敗時，該批會停在待買進，之後的排程日不需並發也會再出單，G1 不會擋，也沒有揭露。歸 N-169（[TA-177S] 修訂四第 4 節）。」

### 6. 修改處索引（風控比對用）
| # | 位置 | 性質 | 依據 |
|---|---|---|---|
| 1 | N-196 3.9 第 3 點（1.1） | 取代：登錄 R-4′ | [風控-196] 二-3 條件 1 |
| 2 | 3.9 第 4 點（1.1） | 新增，逐字 | 二-2(e) 第 3 項 |
| 3 | 3.9 第 5 點（1.1） | 新增：REBALANCE_BLOCKED 的字面不精確 | 二-2(f) suggested，採用 |
| 4 | 3.9 第 6 點（1.1） | [TA 補]：confirm 的交錯不屬於第 1 點 | 二-4、本修訂第 3 節 |
| 5 | N196-C8（1.2） | 取代：列出 SHA、`--is-ancestor` 兩項 exit code 為 0 | 二-2(e) 第 1 項 |
| 5′ | C8 執行與判斷分離（1.2） | [TA 補，待風控確認執行方式]：qa 不能執行 `git merge-base`，改由 dev-lead 與 coordinator 執行，qa 判斷，加 `git diff` 旁證 | CLAUDE.md §4、`READONLY_ALLOWED_BASH` |
| 6 | QB-N196-2（1.2） | 新增 | 二-2(e) 第 1 項 |
| 7 | R-3′「已修正」註記（1.3） | 逐字；合入後才落檔 | 二-2(e) 第 2 項 |
| 7′ | 1.3 末點 | [TA 補]：N-196 被回退時撤回註記 | 同上 |
| 8 | N196-T4（1.4） | 修訂：只觸發一次、只在讀交易內觸發、重入直接放行 | 二-2(f) suggested，採用 |
| 9 | N177b-T17（2.1） | 取代：`count("None")` 與 `count("第 None 批")` 都等於 n；網格加 n ≥ 2 | 二-1 第 4 項 suggested，採用 |
| 10 | N177b-T22 (c′)（2.2） | 新增：具名常數、`model_copy` 的鍵（含 rule_id）、不可判讀形式以 baseline 釘住 | 二-1 第 6 項 suggested，採用 |
| 11 | N-197 (a) 分析（3.1～3.7） | 新增：兩份交錯表、版本交錯、方向、頻率、可偵測性 | 二-4 |
| 12 | 修法比較與 N-197a spec 草案（3.8、3.9） | 新增：採用 F-a 並強化三點；送風控審 | 二-4 候選修法 |
| 13 | N-197 (b) 分析（4.1～4.4） | 新增：走得到；涵蓋表；失敗變體；修法選項 | 二-3 另外的觀察 |
| 14 | ADR-0041 R-5′、R-6′ 草稿（5） | [待風控] | 二-3、二-4 |
| 15 | `evaluate_today` 改成單一讀交易 | 登錄，不處理（日後改動時順手做，仍回風控審） | 二-3 條件 3 suggested |

（修訂四由 coordinator 2026-11-07 附加；原文見 tech-architect 回報。N-197a spec 與第 5 節草稿待風控審。）

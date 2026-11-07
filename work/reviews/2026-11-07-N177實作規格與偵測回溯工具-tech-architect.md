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

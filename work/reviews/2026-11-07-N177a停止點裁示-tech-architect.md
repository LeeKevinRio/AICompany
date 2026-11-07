# N-177a 停止點 S-1～S-5 裁示（修訂五）

- 審查者：tech-architect
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

五個停止點都已裁示，push 前要再補一個 commit。這個 commit 只加在 `a7481e1` 之後，不 amend：改 store.py 一行，加上 tests 的幾處調整，重跑 CI 後就可以 push。

- **S-1：選 (a)**，接受具名例外，C3 不改。把 `rule_id="S2"` 改成引用 `S2_FILL_ENTRY`，本身就違反 QB-3 第三點與 M1 的 QB-7 白名單。T18 與 QB-3 要改寫，並把例外的位置釘得更精確。這個選擇**不需要回風控**。
- **S-2：接受**現在的擺法，4.2 的位置條文照實修訂。
- **S-3：有條件接受**。T21 要補現金斷言，並附效力證明。
- **S-5：保留** `directive.status != "executed"`。C4 改寫為「S2 成交進入條件的字面」，T18 另外加一項 `"executed"` 的精確計數。
- **`_update_batch` 的 status 守衛：接受**，並補進 1.3(4) 與 T26(iv)。
- **`assert alias.isidentifier()`：要改寫**成 `raise ValueError`。

另外發現一個交件沒提的合併風險（S-1 延伸）：N-190 在 store.py 定義了 `SETTLED_SINCE_RULE_IDS = ("S1", "S2", "P1", "P2", "P3")`。依 C14 merge 含 N-190 的 product 之後，T18 的精確計數會轉紅。本裁示預先核可這個例外，處理方式見第四節。

## 二、各部門回報

### tech-architect（本人，唯讀）
讀了交件、規格 4.x、修訂一～四、ADR-0035 補充五修正一 QB-18.5／18.14，以及 N-190 停止點裁示 E-3。比對了 worktree 的 store.py 與 tests，主 checkout 的 store.py（已含 N-190，未含 N-177a）用來看合併後的狀態。沒有執行任何指令。

#### S-1：裁示 (a)
**理由：**
1. `apply_effects` 的 `rule_id="S2"` 是黑名單列的**來源紀錄**，記的是「這筆黑名單由哪條規則寫入」，寫入 `playbook_blacklist.rule_id`。`S2_FILL_ENTRY` 定義的是「settle 判定為 S2 成交的進入條件」。兩者語意不同。綁在一起之後，日後進入條件若調整（例如規則拆分或改名），黑名單來源會跟著無聲改變，這是不合理的耦合。
2. (b) 會讓 `S2_FILL_ENTRY` 出現在 `apply_effects`。這違反 QB-3 第三點（「只出現在常數區、`_SCHEMA`、`settle` 與它的 helper」），也違反 M1 的 QB-7 白名單；這份白名單經過 [風控-0040] 審查。所以 (b) 不是「改一行」而已，它同時要改 C3 與已審的白名單。
3. C4 與 QB-18.5 的本意是「不得另寫 `'executed'`、`'S2'` 的**條件字面**」。T18 與 QB-3 寫成「`"S2"` 只有一處」，是我寫得過寬，錯在規格，不在實作。

**不需要回風控：** (a) 不改 C3、不改 QB-7 白名單、不改任何行為或揭露；T18 與 QB-3 是 TA 自己的測試條款，不是風控附條件。修改處登錄在下面的修訂五索引，供風控下次比對參考，不擋合併。如果選 (b)，就要回風控。

**修訂文字（修訂五，取代 4.12 T18 第 3 點，並追加兩點）：**
- **T18（取代第 3 點）**：AST 檢查 store.py：
  - 值為 `"S2"` 的字串常數，只能出現在以下具名清單的位置，每處恰好一次：
    - (i) `S2_FILL_ENTRY` 的定義；
    - (ii) `apply_effects` 內 `self.blacklist(...)` 呼叫的 `rule_id=` 關鍵字引數。這是黑名單列的來源紀錄，N-177a 之前就有，C3 規定零 diff；
    - (iii) 合入 N-190 之後，再加上 `SETTLED_SINCE_RULE_IDS` 的定義（N-190 停止點裁示 E-3，S/P 賣單序列唯一的一份定義）。
  - (ii)、(iii) 不屬 C4 的條件字面，不得改寫成引用 `S2_FILL_ENTRY`。
  - 含 `'S2'` 的 SQL 字串常數為 0 個；`remaining_shares > 0 AND b.cost IS NOT NULL` 只出現在 `S2_ELIGIBLE_BATCH_SQL`。
- **T18（追加）**：值為 `"executed"` 的字串常數恰好兩處：`S2_FILL_ENTRY` 的定義，以及 `settle` 的逐批閘 `directive.status != "executed"`。
- **T18（追加）**：`s2_fill_entry_sql` 收到不是 identifier 的 alias 時 raise `ValueError`。
- **QB-3 第一點（取代）**：作為 S2 成交進入條件的 `'S2'`、`"S2"`，在 store.py 只有 `S2_FILL_ENTRY` 一處。其他 `"S2"` 只限 T18 (ii)、(iii) 的具名清單，逐處檢查位置與次數。
- **C3**：不修訂。

#### S-2：接受
`_SCHEMA` 是模組層級的 tuple，import 時就會求值 f-string，所以表名與 source 常數必須先定義。其他做法都更差：
- 把 `_SCHEMA` 往下搬，違反 C3(c)「只准末尾追加」；
- DDL 改寫字面表名，會出現第二份表名，違反 QB-3 與 QB-18.14；
- 整組常數搬到 `_SCHEMA` 上方，會離開 `BATCH_LEFT_PLANNED_SQL`，也違反 4.2 與 N-188 要求的相鄰關係。

**4.2 位置條文（修訂五，取代）**：
- `FILL_MOVES_TABLE`、`FILL_MOVE_SOURCE_SETTLE`、`FILL_MOVE_SOURCE_REPAIR` 放在 `_SCHEMA` 正上方（理由是 4.6 的 f-string 在 import 時求值），以 `#:` 註解指向其餘 4.2 常數；
- `S2FillEntry`、`S2_FILL_ENTRY`、`s2_fill_entry_sql`、`is_s2_fill`、`S2_ELIGIBLE_BATCH_SQL` 緊接 `BATCH_LEFT_PLANNED_SQL`；
- 各常數仍然只有一份定義。

現在 store.py :67-73 的註解已經符合，不用改。與 N-190 不會打架：主 checkout 裡 N-190 的記號表 DDL 用字面表名，`MARK_KIND_*` 在 :450 附近，`_SCHEMA` 上方沒有 N-190 的常數。

#### S-3：有條件接受
F8 的原始定義（`2026-10-31-N172修法與資料修復評估-tech-architect.md`:96-100）有兩半：成交後帳冊不減股、也不入帳；以及 S2 每天重發。現在的 T21 只驗了股數與不重發，**沒有驗現金**。

**T21（修訂五，取代）**：
- qa-automation 的 F8 重現不存在，改由 `test_playbook_s2_fill.py::test_t21_f8_an_executed_s2_is_not_issued_again_the_next_day` 承擔。
- 以真實 service 流程（evaluate，然後次日 evaluate）斷言：
  - (i) 次日該檔沒有 S/P/S2 列，日誌只有一張 S2；
  - (ii) 批次 remaining 合計為 0，現金 = 初值 + 開盤價 × 股數。
- 效力證明：暫時移除 `settle` 的 `if is_s2_fill(directive):` 區塊（等於回到 base 對 S2 的行為）時，T21 必須失敗；還原後轉綠。輸出附在 PR 說明，不 commit。
- 日後 qa-automation 若補 F8 重現，屬於追加，不取代 T21。

#### S-5：保留 `directive.status != "executed"`
這是 N-177a 之前就有的通用狀態閘（主 checkout :1613 也有），1.3(1) 明文保留，不是在重述 S2 成交條件。`"missed"` 同理。

**C4 第二點（修訂五，取代）**：
- `settle` 對 S2 成交的判斷只用 `is_s2_fill`。
- store.py 其他地方不得用 `'S2'`、`'executed'` 字面重述 S2 成交的進入條件，或它的任何子集（QB-18.5、18.14）。
- `settle` 既有的通用狀態閘 `directive.status == "missed"`、`directive.status != "executed"` 不受此限，字面次數由 T18 釘住。

#### 範圍外第一點：`_update_batch` 拒絕 `status != 'skipped'`，接受
- 這是 C17「唯一例外是 `status='skipped'`」的執行面。
- 現有三個呼叫者只會送 `'skipped'`、`defer_count`、`trailing_active`，所以行為等價。
- 驗證放在 `batch_no is None` 的提早 return 之前，屬於 fail-closed，也接受。
- T26(iv) 已經涵蓋 `status` 為 open／closed 的情況。

**1.3(4) `_update_batch`（修訂五，追加）**：`status` 只接受 `'skipped'`，其他值 raise `ValueError`。欄名與值的驗證都在任何寫入、以及 `batch_no is None` 的 return 之前。

**T26(iv)（修訂五，取代）**：白名單以外的欄名，或 `status` 不是 `'skipped'`，都 raise `ValueError`，DB 不變。

#### 範圍外第二點：`assert alias.isidentifier()`，要改寫
- 這個檢查守的是 SQL 字串內插，屬於生產環境也必須成立的守衛，不應該在 `-O` 下消失。
- 雖然目前 app 內沒有呼叫點，部署也沒用 `-O`，但 N-188 會引用這個函式，而且 store.py 其他守衛一律用 `ValueError`。
- 這個改動在 C3(b) 的範圍內，`s2_fill_entry_sql("d")` 的輸出不變，所以偵測工具的比對不受影響。

**4.2 程式註解（修訂五，取代）**：`# built from S2_FILL_ENTRY fields; raise ValueError unless alias.isidentifier()`

#### 修訂五索引（供風控比對參考，不擋合併）
| # | 位置 | 性質 |
|---|---|---|
| 1 | T18 第 3 點，追加兩點 | 取代、追加：具名例外與 `"executed"` 計數 |
| 2 | QB-3 第一點 | 取代：限定為條件字面 |
| 3 | C4 第二點 | 取代：限定為 S2 成交條件 |
| 4 | 4.2 位置條文、程式註解 | 取代：常數分兩段；assert 改成 ValueError |
| 5 | T21 | 取代：自寫版，加現金斷言與效力證明 |
| 6 | 1.3(4)、T26(iv) | 追加：status 守衛 |

C3、C17、QB-7 白名單與 ADR-0041 都不變。

### 其他部門
- dev-lead、qa-reviewer：等本裁示，見第四節。
- risk-compliance-officer：本次不需要經手，理由見 S-1。
- 其餘部門：本次沒有參與（純架構裁示）。

## 三、驗證

- 本裁示是讀碼判定，沒有執行任何指令。關鍵依據：
  - worktree store.py:302（`S2_FILL_ENTRY`）、:307（assert）、:1291（`rule_id="S2"`）、:1329（status 守衛）、:1665（`"executed"`）；
  - 主 checkout `/home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py`:262（`SETTLED_SINCE_RULE_IDS` 含 `"S2"`）、:1267、:1613，`'S2'` 的 SQL 字串為 0。這份 checkout 是哪個分支我沒有查證，從內容看已含 N-190、未含 N-177a；
  - 現在的 T18 測試在 `tests/test_playbook_s2_fill.py`:700-722。
- dev-lead 補完 commit 後，以這幾項確認：
  - 完整 CI 全綠；
  - T18 新增的兩項斷言都存在；
  - T21 的效力證明輸出：暫時移除 S2 分支時失敗，還原後綠燈；
  - `git diff a7481e1..HEAD -- app/` 只有 `s2_fill_entry_sql` 那一處。
- 不需要 CEO 親自驗證。

## 四、下一步

**1. dev-lead：在 `a7481e1` 之後加一個 commit，重跑完整 CI，再 push。**

- **(1) store.py `s2_fill_entry_sql`**：把第 307 行
  ```python
  assert alias.isidentifier()
  ```
  改成
  ```python
  if not alias.isidentifier():
      raise ValueError(f"s2_fill_entry_sql needs an SQL identifier alias, got {alias!r}")
  ```
- **(2) `tests/test_playbook_s2_fill.py` 的 T18：**
  - (a) `pytest.raises(AssertionError)` 改成 `pytest.raises(ValueError)`；
  - (b) `PRE_N177A_S2_VALUES` 的註解刪掉「停止點／until tech-architect rules」，改為引用本裁示（修訂五 S-1 (a)），說明那是黑名單來源紀錄、不屬條件字面；
  - (c) 例外收緊：另外斷言 `apply_effects` 內的那個 `"S2"`，是 `func.attr == "blacklist"` 的 Call 上、`rule_id` 關鍵字的值，而且恰好一個；
  - (d) 新增斷言：值為 `"executed"` 的 Constant，所在位置排序後等於 `["S2_FILL_ENTRY", "settle"]`。
- **(3) T21**：加上現金斷言（初值 + 開盤價 × 股數）。照 S-3 的做法做效力證明，輸出附在 PR 說明，不 commit。
- **(4) PR 說明**：加入本裁示的修訂五索引。

**2. 合併前（C14），merge 含 N-190 的 product 時，在 merge commit 裡一併處理以下語意衝突，並在 PR 說明逐條列出，交 qa 審：**
- T18 的 `"S2"` 例外清單加入 `SETTLED_SINCE_RULE_IDS`（T18 (iii)，本裁示已預先核可），它的值與位置零 diff；
- 模組 docstring 的表數量與清單，要同時列入兩張新表；
- `_SCHEMA` 末尾 N-190 在前；
- 在合入後的 head 上重跑 T28（S-4，照原規格）。

**3. coordinator：**
- 把本報告轉存到 `work/reviews/`，修訂五由 tech-writer 或 coordinator 附進規格檔；
- 把追蹤清單上「qa-automation 重現 F8」那一項標為由 N-177a T21 承擔；
- 之後交 qa-reviewer，依 C1～C18、QB-1～QB-12 加修訂五審查，含 Codex 第二意見。

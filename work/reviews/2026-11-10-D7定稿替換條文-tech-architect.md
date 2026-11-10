# ADR-0043 D7 定稿替換條文（M-1、RC-86-1、RC-87、RC-86-3）

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：ADR-0043 D7 定稿的替換條文（qa M-1 ＋ 風控 RC-86-1、RC-87、RC-86-3）

## 一、本次結論

替換條文都寫好了，可以直接貼上。每處都以舊句、新句對照，套用在 `work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md`（以下稱「定稿檔」）上。除下列各處外，其他內容都沒有動。

1. **M-1**：採修法 (1)，新增專用 helper `_read_roster_max_date`，列入單一性檢查第 5 項的允許名單。共改三處（替換 1～3），內容與上一則回報相同。
   - 不併入 `_read_high_volatility`，原因是那個 helper 也是 `symbol_states` 的讀取路徑。併進去之後，評估與名單頁每次讀取都會多一句用不到的 roster 查詢。
2. **RC-86-1**：H-2 句末補上不實字面的說明（替換 4）。
   - **有一處要請 coordinator 決定是否轉風控知悉**：風控的等義句寫「只會在 today_tpe 等於該列 `changed_on` 時顯示」，這句不精確。壞值列的 `changed_on` 晚於 today_tpe 時，W-25f 會從 today_tpe 一路顯示到該日。這種情形發生在 app 外寫入未來日期，或時鐘落後時。
   - 新句寫成「一般情形只在等於的那天；晚於時延長到該日」。方向沒有變寬，只是顯示期間的事實更精確。依 RC-87「語意有變更才回我」，我判斷這不算語意變更，但這屬於事實前提，所以請 coordinator 決定。
3. **RC-87**：全部連動都改了，共九處（替換 5～13），包括：
   - D7 第 2 點與標題括號；
   - Consequences 第一點 (ii) 的句末補上 RC-84 那句，L4、L11 的落差描述保留；
   - 待決項中的 W-25f 標為已結；
   - 附錄 L3、L8 的備註；
   - W25f-2′ 的「真偽」一段；
   - C-D7-5 加入「不受這次取消影響」。
   - 依 CEO #128（方案 (A)）：「方案 (B) 下是 D7 單合併閘」的分支已刪除，閘明確寫為 N-207 的合併閘。
4. **RC-86-3**：寫成 CEO 的選項「H2-修正」，代價、要改的測試列、條件式的替換條文都列在第二段 C。TA 稍偏向修正，風控不偏好任一方，由 CEO 決定。
5. **另外建議同步一處（不在 RC-87 要求內）**：CEO #128、#130 已經裁示，定稿檔待決 → CEO 裡的「D7 拆不拆單」「RC-73 新單是否開立」已經過時。替換 14 提供改寫版，請 coordinator 確認後再交 tech-writer。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### A. M-1（qa-reviewer）

**替換 1：D7 第 2 點「單一性檢查」第 1 項**
- 舊句：
  > 1. app/ 內名為 `parse_high_volatility_flag`、`parse_high_volatility_changed_on`、`_read_high_volatility` 的函式定義各恰 1 個，都在 `app/playbook/store.py`。
- 新句：
  > 1. app/ 內名為 `parse_high_volatility_flag`、`parse_high_volatility_changed_on`、`_read_high_volatility`、`_read_roster_max_date` 的函式定義各恰 1 個，都在 `app/playbook/store.py`。

**替換 2：D7 第 2 點「單一性檢查」第 5 項**
- 舊句：
  > 5. **呼叫點封閉**：兩個解析函式的呼叫，以及 `HighVolChange(...)` 的建構，只出現在 `_read_high_volatility` 本體內。該本體的 `Compare` 節點只能是 `… is None` 或 `… is not None`。
- 新句：
  > 5. **呼叫點封閉**：
  >    - `parse_high_volatility_flag` 的呼叫與 `HighVolChange(...)` 的建構，只出現在 `_read_high_volatility` 本體內。
  >    - `parse_high_volatility_changed_on` 的呼叫，只出現在 `_read_high_volatility` 與 `_read_roster_max_date` 兩個本體內。
  >    - `_read_roster_max_date(conn) -> date | None` 本體恰好執行一句 SQL：`SELECT MAX(taipei_date) FROM playbook_roster_log WHERE date(taipei_date) IS taipei_date`，結果只交給 `parse_high_volatility_changed_on`。它的呼叫者只能是第 3 點的寫入函式（預覽與確認）。
  >    - 兩個 helper 本體內的 `Compare` 節點，只能是 `… is None` 或 `… is not None`。

**替換 3：D7 第 3 點 (a)**
- 舊句：
  > - (a) **鎖內讀取**：經 `_read_high_volatility` 讀該檔的 `HighVolRead`；另以 `SELECT MAX(taipei_date) FROM playbook_roster_log WHERE date(taipei_date) IS taipei_date` 讀 R，結果再經 `parse_high_volatility_changed_on` 解析。沒有列或解析為 None 時，R 不存在。
- 新句：
  > - (a) **鎖內讀取**：經 `_read_high_volatility` 讀該檔的 `HighVolRead`；另經 `_read_roster_max_date(conn)` 讀 R（SQL 與解析依第 2 點單一性檢查第 5 項）。回傳 None 時，R 不存在。

#### B. RC-86-1 與 RC-87（風控；不回送，由 qa-reviewer 核對）

**替換 4：定稿檔第二段 B，Consequences「H-2」整點（RC-86-1）**
- 舊句：
  > 「**H-2 最新一列壞值被當成取消**（風控 RC-79）：最新一列若是 app 外寫入的壞 value，會解析為 0，T = 0。名單頁可能出現 W-25f，但使用者沒有做過取消。E 的方向較嚴。」
- 新句：
  > 「**H-2 最新一列壞值被當成取消**（風控 RC-79、RC-86）：最新一列若是 app 外寫入的壞 value，會解析為 0，T = 0。名單頁可能出現 W-25f，但使用者沒有做過取消。E 的方向較嚴。**W-25f 前段「高波動標記已取消」在此情形與事實不符，只有「M/D 起適用」對 E 為真。** 這個標籤一般只會在 today_tpe 等於該列 `changed_on` 的那天顯示（L12）；該列 `changed_on` 晚於 today_tpe 時（app 外寫入未來日期，或時鐘落後），會從 today_tpe 一路顯示到該日。使用者可以經 W11 重新標記來覆蓋。修正選項見 RC-86-3，由 CEO 決定接受或修正。」

**替換 5：D7 標題括號**
- 舊句：
  > W-25f 第三子句另有閘，見第 2 點）
- 新句：
  > W-25f 第三子句刪除，字面依風控 RC-84 定稿，見第 2 點）

**替換 6：D7 第 2 點「名單頁標籤」下的 W-25f 子彈**
- 舊句：
  > - **W-25f 第三子句：定稿暫停（風控 RC-58；RC-77 採 F2）**。舊字面「今日仍用高波動門檻」不得與本修訂一起進入程式或畫面。新字面由 creative-lead 擬稿、風控逐字定稿：方案 (A) 下是 N-207 的合併閘，方案 (B) 下是 D7 單的合併閘。
- 新句：
  > - **W-25f：第三子句刪除；W-25f 字面依風控 RC-84 定稿**（逐字只放在 `wording.py`）。
  >   - 舊第三子句「今日仍用高波動門檻」，以及未採用的案 (i)「不受這次取消影響」，都不得進入程式或畫面（C-D7-5）。
  >   - 原本的定稿暫停（RC-58、RC-77），在以下兩件事都完成後解除（RC-87）：
  >     - 本修訂與連動修訂（含 H-2）落進本 ADR，並經 qa-reviewer 核對；
  >     - C-D7-5 成立。
  >   - CEO #128 採方案 (A)，所以這是 N-207 的合併閘。

**替換 7：定稿檔第二段 B，Consequences「壞處與代價」第一點的 (ii)**
- 舊句：
  > (ii) **L4**（另見 L11，標記從未適用）：W-25f 第三子句不實，方向較嚴；風控 RC-77 裁示改擬（F2）。」
- 新句：
  > (ii) **L4**（另見 L11，標記從未適用）：W-25f 第三子句不實，方向較嚴；風控 RC-77 裁示改擬（F2）；RC-84 定稿為刪除第三子句，此落差改由 W-27 第二句揭露。」

**替換 8：定稿檔第二段 B，待決 → 風控**
- 舊句：
  > W-25f 第三子句新字面的逐字定稿（RC-77，附自查表）；
- 新句：
  > W-25f 第三子句：**已結**（RC-84，刪除第三子句，W-25f 字面定稿）；

**替換 9：定稿檔第二段 B，待決 → creative-lead**
- 舊句：
  > - creative-lead：上述兩句擬稿；W-27 備註依 RC-79 更新。
- 新句：
  > - creative-lead：D7 第 3 點 (a′) 專用拒絕字面的擬稿；W-27 備註依 RC-79、RC-87 更新。

  理由：W-25f 擬稿已經結案，這一點是連動修改。

**替換 10：附錄 D7-T，L3 備註**
- 舊句：`舊第三子句為真；新子句待 RC-77`
- 新句：`第三子句已刪（RC-84）`

**替換 11：附錄 D7-T，L8 備註**
- 舊句：`舊第三子句為真；新子句待 RC-77`
- 新句：`第三子句已刪（RC-84）`

（L4、L11 的備註依 RC-87 保留，不改。）

**替換 12：定稿檔第二段 E，W25f-2′「真偽」一段**
- 舊句：
  > - **真偽：待 RC-77 新子句定稿後核對。** 舊字面不得進入程式或畫面。
- 新句：
  > - **真偽：第三子句已刪（RC-84），沒有需要核對的子句。** 舊第三子句與案 (i)「不受這次取消影響」都不得進入程式或畫面。

（「舊第三子句不恆真」一段依 RC-87 保留，作為刪除的依據。）

**替換 13：定稿檔第二段 D，C-D7-5**
- 舊句：
  > - **C-D7-5**：舊 W-25f 字面「今日仍用高波動門檻」在 app/ 與前端的 grep 計數為 0（RC-77）。
- 新句：
  > - **C-D7-5**：「今日仍用高波動門檻」與「不受這次取消影響」在 app/ 與前端的 grep 計數都為 0（RC-77、RC-87）。W-25f 只實作 RC-84 全文。

**替換 14（建議同步，不在 RC-87 要求內；請 coordinator 確認）：定稿檔第二段 B，待決 → CEO**
- 舊句：
  > - CEO：
  >   - D7 拆不拆單（(A)／(B)；選 (B) 時適用風控 RC-82 的前提條件）；
  >   - 殘留 H-1～H-4 接受或修正；
  >   - RC-73 的新單是否開立。
- 新句：
  > - CEO：
  >   - 殘留 H-1～H-4 接受或修正。H-2 的修正選項見 RC-86-3（TA 評估「H2-修正」）。
  >   - 已裁示：#128 採方案 (A)，不拆單，附轉換條件；#130 開立 RC-73 的新單 N-211，排在 D7 之後。

#### C. RC-86-3：H-2 的修正選項「H2-修正」（交 CEO 決策包）

**做法**
- `_read_high_volatility` 讀到的任一歷程列，只要 value 原始值不是 integer 0 或 1，就比照 H-3，令 `history_readable = False`、`base = 0`、`history = ()`。
- 基準值 B 不在這條規則內。B 是壞值時，解析結果為 0，不可能讓 E(today_tpe) = 1，所以不會產生不實的 W-25f（E16 不變）。

**方案比較**

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 接受（維持現行，H-2 列為殘留） | 壞列之後的日子，該檔照常運作，使用者可以經 W11 重新標記；不必改程式或測試 | W-25f 前段「已取消」在 L12 不實，而 CEO 要接受的就是這一句（RC-86-1） | 低：只在 app 外繞過 CHECK 寫入時發生 |
| **H2-修正** | 不實的 W-25f 消失；壞 value 與壞 `changed_on` 用同一條規則，H-2 併入 H-3；方向更嚴，整檔 E = 0 | 見下方代價 | 低 |

**H2-修正的代價**
1. **操作面**：
   - 該檔的標記、取消一律拒絕（W8 的分支），而且歷程表擋 DELETE，壞列會永久存在，要等 H-3 的修復路徑才能恢復。現行做法下的 W11 重新標記這條復原路徑會消失。
   - 名單頁上這一檔不顯示任何高波動標籤，評估一律 15%，畫面上沒有任何提示。這和 H-3 相同。
2. **評估值改變**：
   - E18 的 E(11-10) 由 1 改為 0，也就是資料日 11-10 的評估由 20% 改為 15%，方向較嚴。
   - 但這也會改變壞列寫入前已成立的生效值：E18 中，寫入前 E(11-10) = 1。驗收標準 1「變更不改變較早資料日的生效值」只約束 app 內的寫入，所以不受影響；不過要在 H-3 寫明：app 外的壞列會回溯改變較早資料日。現行 H-3 對壞 `changed_on` 本來就是這樣。
3. **程式面**：
   - 新增一個判定函式 `high_volatility_value_valid(raw: object) -> bool`，本體恰為 `return type(raw) is int and raw in (0, 1)`。
   - 單一性檢查要加上：第 1 項加入這個名稱、第 3 項加一個樣式計數（恰 1 個）、第 4 項加本體形狀、第 5 項加呼叫點只在 `_read_high_volatility`。
   - `parse_high_volatility_flag` 仍保留，用於 B，以及已通過驗證的歷程值。
   - 不新增讀取，也不新增交易。
4. **審查面**：RC-75 已確認的「value 逐列回 0」要改寫，對歷程值不再適用，需要風控重審（RC-86-3 已指出）。N207-C21、T30 只涉及 B，不受影響。

**要修改的測試列（附錄 D7-T）**

| 列 | 現行期望 | H2-修正後期望 |
|---|---|---|
| E18 | on 11-10／11-11 → 1／0；T = 0 | 0／0；T = 0；`history_readable` = False |
| L12 | W-25f，M/D = 11/11；11-09 → 15%，11-10 → 20% | 不顯示；15%（與 L13 同型） |
| W11 | 取消：冪等，零寫入；標記：INSERT | 標記與取消都拒絕，期望同 W8 |
| W8 | 只有壞 `changed_on` | 參數化加入壞 value（`'x'`、2、0.5；PRAGMA） |
| P3 | 單一性檢查 1～7 | 加入 `high_volatility_value_valid` 的定義、樣式、本體形狀、呼叫點，以及負例 |
| P4 | 只測解析 | 新增：`high_volatility_value_valid` 對 0、1 為 True；對 2、-1、`'x'`、0.5、None、True、False、`'1'` 為 False |

**CEO 選 H2-修正時的條件式替換（選「接受」時都不套用）**
- D7 第 2 點 `_read_high_volatility` 子彈：
  - 舊句：「任一列的 changed_on 解析為 None 時：」
  - 新句：「任一列的 changed_on 解析為 None，或任一列 value 經 `high_volatility_value_valid` 判為 False 時：」
- D7 第 2 點「解析」：`parse_high_volatility_flag` 的「也適用於每一筆歷程列的 value」一句，句末加「（歷程值須先通過 `high_volatility_value_valid`，否則依 `_read_high_volatility` 整檔退回）」。
- Consequences：
  - 刪除 H-2；
  - H-3 標題改為「歷程有壞 `changed_on` 或壞 value 時，該檔永久退回 15%」，並在句末加「app 外的壞列會回溯改變較早資料日的生效值」。
- 「壞處與代價」第一點、L4、L11 不受影響。

**TA 意見**：稍偏向 H2-修正。理由有兩點：消除系統中僅剩的一句不實字面；壞資料只用一條規則處理，H-3 的修復路徑本來就必須設計。H2-修正的代價只在 app 外破壞資料完整性時才會出現。風控已表示兩種做法在法遵上都可以接受，由 CEO 決定。

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - 全文：`/home/user/AICompany/work/reviews/2026-11-10-W25f定稿與H2判定-風控.md`
  - 部分：`/home/user/AICompany/work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md` :1-20，確認是我的定稿逐字轉存。
  - 各處舊句依我交出的定稿原文比對，沒有重讀全檔。
- **手核**：
  - L12 顯示期間：W-25f 的條件是 T = 0 且 E(today_tpe) = 1。today_tpe 晚於壞列 `changed_on` 時，壞列適用而且 id 最大，所以 E = 0，標籤消失；today_tpe 不晚於壞列 `changed_on` 時，E 由較早的列決定，可能為 1。這就是替換 4 的精確化依據。
  - W11 重新標記後：`changed_on` = max(today_tpe, L, R)；T = 1，標籤改為 W-25d 或 W-25e，可以覆蓋 W-25f。
  - H2-修正下，B 的壞值不會產生不實的 W-25f，因為 parse(B) = 0 不可能讓 E = 1。
- **沒有讀**：qa 核對紀錄全文（M-1 依 coordinator 轉述）、決策包 #128／#130 原文（依 coordinator 註記），以及 creative-lead 草稿（RC-87 對草稿的修改不是 TA 的工作）。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案。

## 四、下一步

1. **coordinator**：
   - 決定替換 4 的「顯示期間精確化」是否轉風控知悉；
   - 確認替換 14 後交給 tech-writer；
   - 把 H-2（含 RC-86-1 補寫的不實字面說明）與第二段 C 的 H2-修正選項放進 CEO 決策包，與 H-1、H-3、H-4 並列。
2. **qa-reviewer**：
   - 核對替換 1～3，關閉 M-1；
   - 核對替換 4～13，對應 RC-86-1、RC-86-2、RC-87、C-D7-5。
3. **tech-writer**：qa 通過後，把定稿檔套用上述替換，再落進 ADR-0043，H-2 一併落檔。落檔要排在 W-25f 進程式之前（RC-86-2）。CEO 選 H2-修正時，再套用第二段 C 的條件式替換。
4. **dev-lead**：
   - 依替換 2 實作 `_read_roster_max_date`，P3 負例加上「在兩個 helper 之外呼叫 `parse_high_volatility_changed_on`」；
   - W-25f 只實作 RC-84 全文，RC-87 的閘解除前不得合併；
   - CEO 若選 H2-修正，依第二段 C 改寫並更新測試。
5. **risk-compliance-officer**：只有 CEO 選 H2-修正時，才要重審「歷程值逐列回 0」的改寫。

相關檔案：
- /home/user/AICompany/work/reviews/2026-11-10-ADR0043D7修訂定稿-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-10-W25f定稿與H2判定-風控.md
- /home/user/AICompany/work/reviews/2026-11-10-D7與ADR0044併入核對-qa-reviewer.md
- /home/user/AICompany/docs/adr/0043-stock-desk-排程台標的名單的表達-批次輪次與輪內股數-名單寫入交易-新標的戳記閘與季度窗口.md

---

## coordinator 定案（2026-11-10，CEO 可推翻）

1. **替換 14 採用**：依 CEO #128、#130，同步改寫待決 → CEO 一項。
2. **替換 4「顯示期間精確化」**：屬於事實更精確，方向沒有變寬，可以先落檔。這一項列為風控知悉事項，在下一次送風控時一併告知，不另外回審。

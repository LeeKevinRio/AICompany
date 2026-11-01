# ADR-0035 補充一（G1 拒絕條件範圍、N172-C12 字面定位）

- 審查者：tech-architect
- 日期：2026-11-01
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

**(a) dev-lead 的寫法正確，ADR-0035 Decision 6′ 的 SQL 字面要修。** G1 只在「批次列存在、而且 `status <> 'planned'`」時拒絕。找不到批次列的 buy 不屬於 G1，照 G1 之前的既有路徑處理。

依 ADR 原寫法 `EXISTS(... status='planned')`，這種列會被拒絕，卻沒有對應的理由句可以渲染。這違反 6′ 自己寫的「不得默默略過」，也違反風控 R5。而且這種列本來就沒有 G1 要防的危害：讀碼判定，現行 `settle()` 遇到找不到批次的列，只更新 schedule，不動現金也不動股數（`store.py:1068-1074`）。

處理方式是補充，不原地改寫：用「ADR-0035 補充一」修正 6′ 的 SQL 字面，條文見下方「可直接貼上的補充條文」。`test_a_missing_batch_row_is_not_refused` 就作為補充一的守門測試。

**(d) 可以接受，但要附條件。** Decision 5 禁止的是「拿字串來做判斷」。用同一個常數、同一組值重新渲染全文，再做整句相等比對，屬於呈現層的定位，不是判斷，所以不違反 Decision 5。

不過這個做法很脆弱：一旦重算的值和 engine 實際用的值不同，就會定位失敗。因此補充一新增 **N172-C12**，限定以下四點：
- 只能整句比對。
- 重算值的輸入必須和該次評估用的是同一份快照。
- 錨點找不到時，揭露句不得因此遺失。
- 必須有往返測試。

另外要把這件事記成技術債：它是「engine 零 diff」（C-B11、N172-C3）的代價。

## 各部門回報

### tech-architect（本人，唯讀）

#### (a) G1 的 SQL：兩種寫法的判定

兩種寫法只在一種情況下結果不同：buy 列找不到對應的批次列。這種列包含兩類：`batch_no` 為 NULL，以及批次列不存在。

| 寫法 | 找不到批次列時的結果 | 是否動帳 | 使用者看得到什麼 | 判定 |
|---|---|---|---|---|
| ADR 原文 `AND EXISTS(... status='planned')` | 拒絕 claim，該列永遠 pending。`SETTLEMENT_BATCH_STATES` 沒有對應的值，渲染不出理由句 | 不動 | 什麼都看不到。每天被重試、每天被默默略過 | **不採**。違反 6′「區分兩種 rowcount 0、不得默默 continue」與風控 R5 |
| dev-lead 實作「批次存在且 `status <> 'planned'` 才拒絕」 | claim 成功，交回既有的 `settle()` 路徑。`batch_no is None` 或 `batch is None` 都只會 `_mark_schedule` 後 return（`store.py:1068-1074`） | 不動 | 照舊出現在 settlement | **採用** |

理由：
1. **G1 要防的是重複扣款。** 只有批次已經 open、closed 或 skipped，才可能被重複扣款。找不到批次列時，`settle()` 走不到 `set_cash`，不存在 G1 要防的危害。
2. **正常程式路徑碰不到這種情況。** `ensure_batches` 只用 `INSERT OR IGNORE`（`store.py:450-457`），grep `DELETE FROM playbook_batches` 結果為 0。R1 的 `batch_no` 一定來自批次列。只有手動改 DB 或測試 seed 才會遇到。
3. **不加第四種理由句，可以省一輪風控字面審查。** 而且不擴大 Decision 6′ 的範圍。

附帶觀察（範圍外，不在補充一處理）：找不到批次列的列會被記成 executed，實際上卻沒有動帳。這和 F8（S2 的 `batch_no=None` 不動帳）同一個根因，建議併入 F8 追蹤。

#### (d) 用同一模板重新渲染來定位：架構判定

- **可以接受的理由**：
  - 觸發條件全部來自結構化資料。dev-lead 自述如此，qa-reviewer 要實查。
  - 重新渲染時，engine 輸出和 service 比對用的是同一個 `wording.py` 常數，兩邊同源。日後改字，兩邊會一起變，不會像寫死的字串那樣悄悄失效。
  - 把 FROZEN_NOTE 當成插入位置的錨點，是決定「放在哪裡」，不是決定「要不要揭露」，不違反 Decision 5。
- **脆弱點**：
  - 縮量句的 planned 股數是 service 用 `planned_batch_shares` 重算的。如果輸入快照和 engine 當次用的不同，例如 commit 之後才重讀批次，重新渲染出來的句子就和實際的句子不相等。結果是該移除的句子沒被移除。
  - 錨點找不到時，若程式直接放棄插入，揭露句就會遺失。
- **限制條件**寫在補充一的 N172-C12。

#### 可直接貼上的補充條文（比照 ADR-0037 補充一的做法）

**A. 檔頭補充行**（貼在 ADR-0035 檔頭「狀態」行之後；本檔其餘原文不改）

```
- 補充一（tech-architect 2026-11-01，回應 `work/reviews/2026-11-01-N172a實作交件-dev-lead.md`「下一步」2(a)、2(d)）：Decision 6′「原子化」項的 SQL 寫法以補充一 S-1 為準；新增 N172-C12（字面定位）與 N172-T22。全文見 `work/reviews/2026-11-01-ADR0035補充一-tech-architect.md` 第「B. 補充一全文」節；本檔原文不改（比照 ADR-0033、ADR-0037 補充先例，CEO 可推翻改為另立取代 ADR）。
```

**B. 補充一全文**（放在上面連結指向的位置）

```
# ADR-0035 補充一：G1 拒絕條件的精確範圍、以同一模板重新渲染定位字句

- 日期：2026-11-01
- 決策者：tech-architect
- 性質：補充 ADR-0035，不取代。ADR-0035 原文不改。
- 觸發：N-172a 交件「下一步」2(a)、2(d)。

## S-1 G1 的拒絕條件（取代 Decision 6′「原子化」項中的 SQL 字面；6′ 其餘各項不變）

### 背景
Decision 6′ 寫的是：buy 列加上 `AND EXISTS (SELECT 1 FROM playbook_batches WHERE symbol=? AND batch_no=? AND status='planned')`。照這個寫法，找不到批次列的 buy（批次列不存在，或 `batch_no` 為 NULL）也會被拒絕；但 `SETTLEMENT_BATCH_STATES` 沒有對應的值，渲染不出理由句。結果是該列每天被默默略過，違反 6′「區分兩種 rowcount 0、不得默默 continue」與風控 R5。

### 決策
1. **G1 拒絕 claim，若且唯若**：該列 `action='buy'`，**而且**存在 (symbol, batch_no) 相同的批次列，**而且**該批次列的 `status <> 'planned'`。
2. **原子化不變**：上述條件必須寫在 `claim_directive` 的**同一條 UPDATE** 內，與 `id=? AND settled=0` 同列，例如 `AND NOT (action='buy' AND EXISTS (SELECT 1 FROM playbook_batches b WHERE b.symbol=playbook_directives.symbol AND b.batch_no=playbook_directives.batch_no AND b.status <> 'planned'))`。等價寫法都可以，但不得拆成「先 SELECT 再 UPDATE」。
3. **找不到批次列的 buy 不屬於 G1**：照 G1 之前的既有路徑處理，也就是 claim 成功後交給 `settle()`，由它的 `batch_no is None`／`batch is None` 分支處理，不動現金與股數。不新增理由句，`SETTLEMENT_BATCH_STATES` 不加值。
4. **是否動帳只由那條 UPDATE 的 rowcount 決定。** 用來區分「已被別人結算」與「批次已成交」的讀取（例如 `batch_blocking_claim`），只能拿來挑選理由句，不得參與「是否動帳」的判斷。
5. sell 列不受 G1 影響（不變）。

### 理由
- G1 要防的是重複扣款，而找不到批次列時 `settle()` 不會走到 `set_cash`，所以這種列沒有 G1 要防的危害。
- 正常程式路徑不會產生這種列：`ensure_batches` 只 `INSERT OR IGNORE`，全 repo 沒有 `DELETE FROM playbook_batches`，R1 的 batch_no 一定來自批次列。只有手改 DB 或測試 seed 才會遇到。
- 原寫法會造成靜默略過，與 6′ 自己的要求矛盾。

### 後果
- 好處：沒有靜默路徑；不新增字面，不必另送風控；與 G1 之前的行為一致。
- 壞處（範圍外，不在本補充處理）：找不到批次列的 buy 會被記為 executed，卻沒有動帳。這與 F8（S2 `batch_no=None` 不動帳）同根，併入 F8 追蹤。

### 測試
- **N172-T21 擴充**：`test_a_missing_batch_row_is_not_refused` 是本條的守門測試，要斷言 (i) claim 成功、(ii) 現金與所有批次列不變、(iii) `unsettled` 不出現 G1 理由句。另外補一個 `batch_no` 為 NULL 的 buy 案例，斷言相同。
- G1 的 SQL trace 測試要斷言：拒絕條件出現在 claim 的同一條 UPDATE 內。

## S-2 以同一模板重新渲染定位字句（新增 N172-C12）

### 背景
Decision 5 規定「不得改用比對 `FROZEN_NOTE` 字串來判斷」。N-172a 的觸發條件都用結構化資料判斷，但要移除縮量句、或以 FROZEN_NOTE／DATA_GAP 句為錨點插入揭露句時，做法是用同一模板、同一組值重新渲染全文後比對。

### 決策
- Decision 5 禁止的是「拿字串做判斷」（要不要揭露、要不要動帳）。用來**定位或移除**的整句比對屬於呈現層，可以接受，但必須符合 N172-C12。
- **N172-C12**：
  - (a) 只能對 `warnings` 清單元素做**整句 `==`**。不得用 substring、`in`、`startswith`、regex，也不得從句子裡解析出數值。
  - (b) 重新渲染只能用 `wording.py` 的同一常數，不得複製字面。重算值的輸入必須是傳給該次 `evaluate()` 的**同一份快照**（batches、portfolio、params、markets），不得在 commit 之後重讀。需要重算時，用 engine 公開的純函式（例如 `planned_batch_shares`），不得在 service 另寫一份算式。
  - (c) 失敗方向：錨點找不到時，風控要求的揭露句**仍然必須出現**（附加在清單末端），不得因此遺失。要移除的句子找不到時，不得報錯，也不得改用模糊比對。
  - (d) 判斷是否揭露、是否動帳，一律不得讀取 `warnings` 的內容。
- **N172-T22**：
  - 往返測試：凡是 service 會定位或移除的模板，每個至少一組 fixture，斷言「service 重新渲染的字串 == engine 實際輸出的那一句」，縮量句要涵蓋。
  - 錨點缺席測試：拿掉 FROZEN_NOTE 或 DATA_GAP 錨點時，揭露句仍然存在。

### 後果
- 這是 engine 零 diff（0034 C-B11、本 ADR N172-C3）的代價，記為技術債。日後若有 ADR 允許改 engine，應改成 engine 輸出帶 `(kind, symbol, batch_no)` 標記的 warning，再移除重新渲染的做法。
```

### 應經手但尚未經手
- **qa-reviewer**：依 S-1 的第 2、4 點與 N172-C12 的 (a) 到 (d) 實查分支程式碼。我讀不到 `origin/fix/stock-desk-same-day-idempotency` 的內容，見「驗證」。
- **tech-writer／coordinator**：A 段貼進 ADR-0035 檔頭；B 段存成 `work/reviews/2026-11-01-ADR0035補充一-tech-architect.md`。
- **dev-lead**：補 `batch_no` 為 NULL 的案例與 N172-T22。若現有程式不符合 C-12 的 (b) 或 (c)，就要修改。
- **risk-compliance-officer**：知會即可。S-1 沒有新增字面；C-12 (c) 保證揭露句不會因錨點找不到而遺失。

## 驗證

- 讀過：
  - `work/reviews/2026-11-01-N172a實作交件-dev-lead.md` 全文
  - ADR-0035 的 1-12 行、120-149 行，以及 grep 全檔的 G1 相關段落
  - ADR-0037 補充一的檔頭行，以及 `work/reviews/2026-11-01-ADR0037補充一-tech-architect.md` 的結構
- 讀碼，對象是工作樹 `product/stock-desk`。N-166 已在線上，N-172a 不在：
  - `store.py:1068-1074`：`settle()` 遇到 `batch_no is None`／`batch is None` 不動帳
  - `store.py:1065-1067`：MISSED 時找不到批次就不加計數
  - `store.py:450-457`：`ensure_batches` 只用 `INSERT OR IGNORE`
  - grep `DELETE FROM playbook_batches`：0 筆
- **限制**：我只能讀工作樹，**沒有讀到 N-172a 分支的 `claim_directive`、`batch_blocking_claim`、重新渲染的程式碼**。對 dev-lead 寫法的判定，是依交件文件描述的語意做的。條件是否真的寫在同一條 UPDATE 內、重算值是否用同一份快照，交 qa-reviewer 實查。
- 沒有執行任何程式，沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 下一步

1. coordinator：依 A、B 兩段落檔補充一。這個做法比照 0033、0037 的補充先例；CEO 若認為應該另立取代 ADR，請指示。
2. qa-reviewer：把 S-1 的第 2、4 點與 N172-C12 的 (a) 到 (d) 列為 BLOCKING 實查項目。
3. dev-lead：補測試（N172-T21 擴充、N172-T22）。若實查發現重算值在 commit 之後才讀，或錨點找不到時揭露句會遺失，就要修改。
4. coordinator：在 F8 追蹤項下補註「找不到批次列的 buy 被記為 executed 卻沒有動帳」，與 F8 同根。
5. 需要 CEO 裁示：無。S-1 是收窄規格、不新增字面，C-12 是實作約束，都在架構權責內。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-01-N172a實作交件-dev-lead.md
- /home/user/AICompany/docs/adr/0035-stock-desk-排程台同一預定執行日重複評估的決策冪等.md
- /home/user/AICompany/docs/adr/0037-stock-desk-排程台出清流程的狀態擁有層.md
- /home/user/AICompany/work/reviews/2026-11-01-ADR0037補充一-tech-architect.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py

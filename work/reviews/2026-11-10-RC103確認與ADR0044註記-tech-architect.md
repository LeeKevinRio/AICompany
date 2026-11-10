# RC-103 第 1 點確認與 ADR-0044 註記判定

- 審查者：tech-architect
- 日期：2026-11-10
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：RC-103 第 1 點 (a)～(c) 確認，及第 2 點兩則 ADR-0044 註記判定

## 一、本次結論

- **(a) 有條件成立，有 1 個例外要回風控。**
  - recorded 判定的 yes 無條件蘊含「評估讀取 TD 早於最近一次 TD 寫入的 commit」，前提是 4 項既有約束都落實。
  - time_order 判定的 yes 要再加一個前提：時鐘沒有倒退。時鐘先快後被校回時，可能出現假的 yes。這是 R-c 的另一個方向，ADR-0044 的 R-c 只寫了「標示消失」那一邊。範圍只有 `td_basis` 為 NULL 的舊列，方向是多標。
  - 依 RC-103「任一點不符時相關句子不得上線」，要風控裁示，我推薦以補記 R-c 的方式接受。
- **(b) 可能發生，回送風控。**（讀碼推論，沒有實跑。）
  - 條件是 A8（規則集已確認，但 TD 從未寫入），再加上結算賣出建立了只含賣出所得的現金鍵，而且現金底線預算大於 0。
  - 這時 `total_deploy` 會以 "0" 代入，`max(1, …)` 算出 1 股，R1 buy 可以 commit。N10-01 對這種列不精確。
  - 推薦方案不改程式：新增盤點項目 P-8b，順帶補上 P-8 自承偵測不到的「賣出現金鍵」殘留。
- **(c) 可以滿足，而且不增加 N-207 的關鍵路徑。** 兩條相依鏈不互相依賴，沒有循環；N-198 本來就在 N-207 的 M1 前置清單內。但 M1 只驗證祖先關係、不規定兩者的先後，所以要給 N-210b 加一道它自己的祖先閘。
- **第 2 點的兩則註記不改變 Decision，不需要 CEO。** CEO #127 的三項選擇（寫法 A、時序選項 1、選擇修正）都不變。兩則都是事實前提的更正，外加一條屬加嚴的合併順序約束。可直接 append 的全文在第二段 D。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### A. (a)：兩種判定依據的 yes，是否都蘊含「評估讀取 TD 早於最近一次 TD 寫入的 commit」

**recorded：成立。**
- yes 表示 `td_basis` 與現行戳記在字面上不同。`td_basis` 是評估當次 `portfolio_and_stamp()` 從已 commit 的狀態讀到的快照 S0。現行戳記是 `/today` 在讀出該列之後才讀的快照 S1（C-N210-3）。
- S1 晚於該列的 commit，該列的 commit 又晚於 S0。三個鍵在 S0 到 S1 之間有改變，就表示有一次 TD 寫入在評估讀取之後 commit，而「最近一次」寫入不會早於它。
- 每次寫入都會寫新的 set_at，所以 TD 值相同（same_value）時，同樣代表發生過寫入。
- **成立前提**，這 4 項都必須落實，qa 照既有條款檢查：
  1. Decision 7 第 1、2 款：三個鍵只由 TD 寫入函式寫；
  2. Decision 7 第 4 款：DELETE 路徑不會收到這三個鍵；
  3. C-N210-12：交給 `evaluate()` 的 portfolio 與交給 `commit_evaluation` 的 stamp，來自同一次 `portfolio_and_stamp()`，所以算股數用的 TD 就是 `td_basis` 記下的 TD；
  4. **（新增，要補測試）** `td_basis` 的 encode／decode 能逐字還原：對任意戳記，包括各鍵為 null 的情形，`decode(encode(s)) == s`，以性質測試釘住。只要不能還原，就會出現假的 yes。

  另外，app 外對這三個鍵的寫入不在保證範圍內。

**time_order：在「時鐘不倒退」的前提下成立。**
- 時間順序：
  - 評估在 `service.py:2200` 讀 TD，晚於 `store.py:1372` 取 `created_at`；這個順序在 N-210a 之前的舊程式碼上也成立。
  - 最近一次寫入的 set_at，不論新舊寫法，都在它自己 commit 之前取值。
  - 所以 set_at 晚於 created_at，可以推得：讀取早於 created_at，created_at 早於 set_at，set_at 早於 commit。
- 舊程式碼上 set_at 可能往回走（Context 第 6 點），但那只會造成假的 no，不會造成假的 yes。
- **例外（要回風控）**：
  - 情境：TD 寫入當時時鐘偏快（set_at 偏晚），之後時鐘被校回；評估在寫入 commit 之後才讀 TD，但它的 created_at 仍早於 set_at，於是判為 yes。這時 N10-01 不成立。
  - 範圍：只限 `td_basis` 為 NULL 的列，也就是 N-210a 部署前已落檔的列，以及回退期間寫入的列。屬過渡性質。
  - 方向：多標，不會漏標。
  - 根因與 R-c 相同。推薦：風控以「R-c 補記」接受，條文見 D 段的條件性註記 3。
  - 時間相等時判 unknown（Decision 7 第 5 款），不在這個例外內。

#### B. (b)：app/ 內是否可能在 TD 鍵不存在時 commit R1 buy 列

**結論：可能。**（讀碼推論，沒有實跑。）

推導鏈：
1. `portfolio_state()`：`cash` 與 `total_deploy` 缺鍵時都以 "0" 代入（`store.py:1022-1023`）。
2. `planned_batch_shares`：TD = 0 時，`max(1, int(per_batch // close))` 或 `max(1, … − already)` 都得 1（`engine.py:209`、`:215`）。
3. `_apply_cash_floor`：預算 = cash − cash_floor_ratio × 總資產（`engine.py:1043`）。現金鍵也不存在時預算不大於 0，買單全部被丟掉，這時不會 commit。
4. 現金鍵可以在 TD 不存在時出現：結算會以 `set_cash` 寫現金（`store.py:1635`、`:1638`），在原本沒有現金鍵時就會建立「只含賣出所得」的現金鍵。這正是 P-8 自承偵測不到的殘留（v3.1 §9.3 P-8 列）。
5. 「已確認但 TD 從未寫入」的來源：`confirm_rules` 先 commit `confirm_rule_set`，再另一個交易做 `set_capital`（`service.py:2021-2034`），兩者之間行程中止就會停在這個狀態，即 A8（CEO #134 已接受）。其他路徑：
   - `request_rule_change` 在 app/ 內沒有呼叫者；
   - Decision 7 第 4 款保證 TD 寫入之後不會被刪除；
   - 所以 TD 不存在只可能是 A8，或 app 外的寫入。

**實際條件**：A8，加上持有中的批次經 S／P／EMERGENCY 賣出並結算，建立現金鍵；之後持股減少，使預算大於 0；某個 planned 批次的 R1 條件成立。這時會 commit 一張 1 股的 R1 buy，`td_basis` 記的 TD 為 null。之後 CEO 依 #134 以 API 重送資金確認寫入 TD，這一列在 recorded 下判為 yes，顯示 N10-01。但這一列並沒有「取得」任何 TD 值，股數是以 0 代入算出來的，所以句子不精確。

**給風控的選項**：

| 方案 | 內容 | 優點 | 缺點 | 需誰裁 |
|---|---|---|---|---|
| B1（推薦） | 列為 A8 殘留的延伸（#134 已接受 A8）。另在 N-212 新增 `p8b.sql`：已確認 × TD 鍵不存在，只回 0／1；為真時比照 P-8，等 CEO 書面裁示才可部署 | 不改程式；部署前就能抓到「已確認、TD 不存在、現金鍵存在」，順帶關掉 P-8 的「賣出現金鍵」偵測缺口 | 部署後若再次發生 A8（兩個交易之間中止），仍可能出現這種列 | 風控；PM 要改 FR-47／AC-93 |
| B2 | 程式修正：已確認路徑上，TD 鍵不存在時不產生 R 系列進場 | 根治 | 這是行為變更，與 #134「不改程式」衝突；而且是在 engine 外過濾輸入，要走 ADR-0043 補充四的 J-6、J-8 程序 | **需 CEO** |
| B3 | 讓 N10-01 對這種列換句 | — | 違反 RC-96 的統一句與 C-N210-15，不可行 | — |

採用 B1 時，P-8b 的 SQL 是：
```sql
SELECT CASE WHEN
  (EXISTS (SELECT 1 FROM playbook_state WHERE key = 'rule_set_confirmed_at')
   OR EXISTS (SELECT 1 FROM playbook_rule_params))
  AND NOT EXISTS (SELECT 1 FROM playbook_state WHERE key = 'total_deploy')
THEN 1 ELSE 0 END;
```

#### C. (c)：N-198 與 N-210b 的合併順序能否滿足 RC-99

**結論：可以滿足。**
- **相依關係**：
  - N-198 的前置是 N-177a、N-177b、N-199（ADR-0042 :23、N198-C7）。
  - N-210b 的前置是 N-209b（ADR-0044 Decision 6）；它也依賴 N-209 前端，因為 RC-102 第 4 點要求 N9-06 同畫面顯示。
  - N-197a 是 N-209b 與 N-210a 的前置，與 N-198 無關。
  - 兩條鏈都不依賴對方，所以 N-198 先於 N-210b 沒有循環。
- **時程**：
  - N-198 已在 N-207 的 M1 固定清單內（固定 11 條），CEO #127 時序選項 1 也要求 N-210b 在 N-207 部署前合入。所以 N-198 先於 N-210b，只可能讓 N-210b 等 N-198，不會延後 N-207。
  - 風險：N-198 若因 N-177b、N-199 延誤，N-210b 會跟著延誤。依 RC-99 不得改用其他字面，只能等。
- **M1 不夠**：M1 只驗證兩者都是 N-207 的祖先，不規定兩者的先後，所以 N-210b 要有自己的閘：
  - **N210b-M**：N-210b 合併前，由 devops-sre 執行 `git merge-base --is-ancestor <M_198> <N-210b 的 base>; echo "exit=$?"`，必須是 `exit=0`。`<M_198>` 是 N-198 在 product 上的 merge commit，完整 40 碼。輸出原樣附在 PR 說明。qa-reviewer 只判讀，不自行執行；不是 `exit=0` 就判 BLOCKING。
  - N-210b 以 merge commit 合入，合入前要 merge 最新的 product（比照 N207-M2），所以 base 等於合入時的 product。
  - 連動：N-210b 合入後若 N-198 被回退，N10-03b 不成立，先回風控。
- **登錄**：coordinator 在追蹤清單的 N-210a／N-210b 列加上「N-210b 相依 N-198（RC-99）、N-209（RC-102 第 4 點）」。

#### D. RC-103 第 2 點：兩則註記是否改變 Decision，與註記全文

**判定：不改變 Decision，不需要 CEO。**
- **註記 1**：新句陳述的事實，在 time_order 列上被原本的事實 1、2 蘊含，範圍比原文小，仍在 Decision 5「只限三件事實」的上限內；「不分版」的規定也不變。
- **註記 2**：更正 Context 的事實前提。
  - Decision 5 (iv)「寫明只會有一筆成交」改照定稿句讀，是讓字面更精確，不是放寬。
  - 新增「N-210b 在 N-198 之後」，屬加嚴的時序約束，不改 CEO #127 的任何選擇。
- **落檔方式**：tech-writer 以 append 的方式加在 ADR-0044 文末，不改動既有條文。
- **另一處小問題**：ADR-0044 :153 的標題仍寫「Decision（決策，proposed）」，與檔頭的 accepted 不一致，請 tech-writer 在改狀態時一併改字。

**可直接 append 的全文**：

```markdown
## 補充一：N-210 字面定稿後的事實註記（2026-11-10；風控 RC-96～RC-103；tech-architect 確認；不改 Decision）

### 註記 1（Decision 5 第一點；風控 RC-96）
- Decision 5 第一點所列 yes 標示句的前兩件事實——「本列在 TOTAL_DEPLOY 最近一次重新設定之前產生」「股數依產生當時的值計算」——只在 `td_flag_basis = "time_order"` 的列上成立。寫法 A 下 `td_flag_basis = "recorded"` 的 yes 列，可能是評估先讀到舊戳記（Context 第 7 點的 R-a 窗口），REBALANCE 接著 commit，之後 `commit_evaluation` 才取 `created_at`；這時列的產生時間晚於重新設定，前兩件事實不成立。
- 兩種判定依據的 yes 共同蘊含的事實是：評估讀取 TOTAL_DEPLOY 的時點，早於最近一次 TOTAL_DEPLOY 寫入的 commit（tech-architect 2026-11-10 確認）。成立前提：
  - (i) Decision 7 第 1、2、4 款（寫入者封閉、DELETE 不收 TD 三鍵）；
  - (ii) C-N210-12：交給 `evaluate()` 的 portfolio 與交給 `commit_evaluation` 的 stamp 來自同一次 `portfolio_and_stamp()`；
  - (iii) `td_basis` 的 encode／decode 逐字可還原（性質測試釘住）；
  - (iv) time_order 列另以時鐘不倒退為前提（R-c）。
- 風控 RC-96 依此定稿 yes 句（N10-01），以「本列股數依 TOTAL_DEPLOY 最近一次重新設定之前取得的值計算」取代前兩件事實；第三件事實（帳冊子句，與 N9-05 同一套限定）逐字不變。此事實在 time_order 列上被原前兩件事實蘊含，範圍不比原文大，仍在本點「只限三件事實」的上限內。
- 「yes 句與 unknown 句不依 `td_flag_basis`、`td_change` 分版」不變。字面全文以 `work/reviews/2026-11-10-N210字面定稿-風控.md` 為準，本 ADR 不複寫。

### 註記 2（Context 第 3 點；風控 RC-99，更正 RC-47）
- Context 第 3 點末句「同一批次可能有多張列，但最多只有一張成交入帳」，以 N-198（ADR-0042：claim 與動帳併入同一寫鎖交易）已合入為前提。N-198 合入前，claim 與動帳分屬不同交易，兩個結算並發時，同一批次的兩張 buy 都可能在批次改為 open 之前通過 G1 而動帳（ADR-0042 Context；屬 ADR-0042 的 R-6′，不在本 ADR 的 R-g 內）。
- 「成交」發生在券商端，系統無從保證（ADR-0035 R10）；系統保證的是「至多一張計入帳冊」，被跳過或 missed 時為零張。Decision 5 第 4 子點「寫明同一批次只會有一筆成交」依此讀為風控 RC-99 定稿的 N10-03b，字面全文以上列風控檔為準。
- 連帶約束（加嚴；不改 CEO #127 的時序選項 1）：
  - N-210b 的 base 必須含 N-198 的 merge commit。合併前由 devops-sre 執行 `git merge-base --is-ancestor <M_198> <N-210b 的 base>`，必須是 `exit=0`；qa-reviewer 只判讀，不是 `exit=0` 就判 BLOCKING。
  - N-210b 合入後若 N-198 被回退，N10-03b 不成立，先回風控。
  - N-198 本來就在 N-207 合入閘 M1 的前置清單內，本約束不延後 N-207。
```

**條件性註記 3**：等風控對 (a) 的例外與 (b) 裁示後才落檔；風控若不採我的推薦，就不落這一則。

```markdown
### 註記 3（R-c 與 A8 的補記；風控 RC-1xx 裁示後落檔）
- R-c 另有一個方向：TD 寫入時時鐘偏快、之後被校回，`td_basis` 為 NULL 的列可能判為 yes，而評估實際上是在該次寫入 commit 之後才讀取 TD。方向是多標，只限 N-210a 部署前落檔與回退期間寫入的列。
- A8 狀態（規則集已確認、TD 鍵從未寫入）下，若結算建立了現金鍵，評估可能以 TD = 0 算出 1 股的 R1 並落檔，`td_basis` 的 TD 為 null；之後 TD 寫入時，這種列會判為 yes，N10-01 的「取得的值」對它不精確。依 CEO #134 列為 A8 殘留；部署前以 N-207 §9.3 P-8b（已確認 × TD 鍵不存在）偵測。
```

#### 對實作的約束（qa 可逐條檢查）
1. N-210a 補一條 `td_basis` encode／decode 的逐字還原性質測試，含各鍵為 null 的情形。
2. N-210b 合併前，附上 N210b-M 的 `exit=0` 原樣輸出。
3. N-210b 的 base 也必須含 N-209（RC-102 第 4 點）。
4. 風控對 (a) 的例外或 (b) 裁示之前，N10-01 不上線（RC-103 第 1 點）。N-210a 後端可以照常開發，不受影響。

### 其他部門
本次沒有參與。

## 三、驗證

- **已讀**：
  - 風控 `work/reviews/2026-11-10-N210字面定稿-風控.md` 全文 RC-96～RC-103；
  - ADR-0044 全文至 C-N210-17，包括 Context 第 1～7 點、(iii-c) 評估、Decision 1～8、Consequences；
  - ADR-0042 的前提與 N198-C7；
  - 追蹤清單的 N-197a、N-198、N-209b、N-210a／b 列。
- **讀碼**：
  - `store.py:1008-1055`（`portfolio_state`、`set_capital`）、`:1096-1097`（`set_cash`），以及 `:1635`、`:1638` 的結算寫現金；
  - `engine.py:204-215`（`planned_batch_shares`）、`:1020-1083`（`_apply_cash_floor`）；
  - `service.py:2018-2035`（`confirm_rules` 的兩個交易）；
  - grep 確認 app/ 內寫現金鍵的只有 `set_capital` 與 `set_cash`，而 `set_cash` 只由結算呼叫。
- **沒有做**：
  - 沒有實跑任何程式或測試。(b) 是讀碼推論，沒有種入 A8 加上賣出現金鍵的情境去實證；qa 或 dev-lead 可以加一條 tmp DB 測試佐證。
  - 沒有用 git 查合併狀態，(c) 的「N-198 尚未合入」引用自風控的 grep 結果。
  - 沒有改任何檔案；沒有讀 `.env`；沒有碰 `data/*.db`。

## 四、下一步

1. **risk-compliance-officer**：
   - 裁示 (a) 的 time_order 例外是否以 R-c 補記接受（推薦接受）；
   - 裁示 (b) 選 B1 或 B2（推薦 B1；選 B2 就轉 CEO，因為與 #134「不改程式」衝突）。
2. **tech-writer**：把註記 1、2 append 進 ADR-0044，順手修正 :153 標題的「proposed」。註記 3 等風控裁示後才落。
3. **dev-lead**：
   - N-210a 補 encode／decode 的逐字還原性質測試；
   - N-210b 依 N210b-M 排在 N-198 與 N-209 之後合併。
4. **devops-sre**：N-210b 合併前執行 N210b-M。
5. **coordinator**：在追蹤清單登錄 N-210b 相依 N-198、N-209；風控若選 B1，派 PM（FR-47、AC-93 加 P-8b）與 data-engineer（N-212 加 `p8b.sql`）。
6. **CEO**：目前沒有待裁事項；只有風控選 B2 時才會送 CEO。

**相關檔案**：
- /home/user/AICompany/work/reviews/2026-11-10-N210字面定稿-風控.md
- /home/user/AICompany/docs/adr/0044-stock-desk-排程台REBALANCE之後-未結算的R系列買進列如何處置.md
- /home/user/AICompany/docs/adr/0042-stock-desk-排程台結算的claim與動帳併入同一寫鎖交易.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/engine.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md

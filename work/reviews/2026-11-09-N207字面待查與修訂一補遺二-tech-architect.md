# N-207 字面待查項（T-02～T-24）與 ADR-0043 修訂一補遺二

- 審查者：tech-architect
- 日期：2026-11-09
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# tech-architect 回報：N-207 待查清單（T-02～T-24），以及修訂一補遺二

## 一、本次結論

全程唯讀，沒有改任何檔案，沒有執行任何指令。沒有讀 `.env`，沒有碰 `data/*.db`。

**T-xx 各項結論：**
- **T-05：取兩者中較晚的日期。** 名單入口的凍結判定是「任一個截止日不晚於今日就凍結」，所以截止日要取兩個非 None 值的最大值。兩者並存時取較晚者。
  - ADR 原文沒寫這一點，我補成約束：由 `portfolio_frozen` 直接回傳截止日，判定與字面共用同一個來源。
- **T-09：FR-24 的空表邊界存在，但不會讓閘卡死。**
  - 首次設定一完成，批次表就不是空的，FR-24 的空表條件不再成立。
  - 真正的邊界在 **authorship（規則集是否已確認）**，不在戳記。設定名單時規則集若已確認，畫面上就沒有資金確認入口，**唯一能從畫面解開的路徑是 REBALANCE（N-209）**。
  - 因此 W-09c、W-12b 的「資金確認」那一句，要依後端給的 authorship 旗標決定是否出現。
- **T-13：四類不互斥。**
  - 「待生效」與「本輪無待進場批次」彼此互斥。
  - S1、S2 和這兩類都可能同時成立。
  - 我建議用多標記計數：每類各自計數，加總可能大於差額。差額由後端另外直接給。
- **T-19：照現行 N207-C17，API 層拿不到。** `later_round_keys` 不帶輪次，範圍也可能不完整。
  - 另外發現 C17 的一個缺陷：`later_round_keys` 只取 engine 輸入裡的批次，比 ADR D3 第 6 點窄，會漏掉「已停止標的的第 2 輪批次仍有指令」這種情況。改法是從 `book` 算，並加一個輪次區間欄位。
- **T-20：建議依「coordinator 擬稿、風控定稿、CEO 確認收到」的模式。**
  - 部署通知只在 P-4 大於 0 而且 CEO 選擇保留時才設計，不預先實作。
  - app 內的一次性通知：已關閉的紀錄存在後端，要列的代號由資料條件推出，不另存快照。
  - 能不能只用 app 外的通知代替，要由風控裁示。
- **T-22：建議常駐**，搭配 B 版字面。
  - 要做到「只在殘留成立時顯示」，名單讀取路徑必須多一個資料日來源（需要網路讀取或新增落檔欄位）。
  - 決定由 PM 與風控做。
- **T-24：以「最新一輪」判斷要不要揭露，揭露句寫明是第幾輪。**
  - 各輪的批數可能不同。W-11、W-19 的「每輪 {bpt} 批」在 bpt 改過之後會不實，要改用該輪實際批數。
- **T-10：現有程式裡沒有可以直接沿用的台股代號正向規則。**
  - 現有兩條規則都會放行 `2330.TW`，資料層准入連空字串也放行。
  - 另外，AC-04 寫「非數字代號」要拒絕，這與 B、L、R、U 後綴的合法台股代號衝突。
- **T-02：「在途」在前後端的使用者字面中零命中。** 現有用詞是「已產生、尚未結算的…指令」與狀態「待結算」。建議改用現有用詞。

**追加範圍（修訂一補遺二）：** 全部寫在第二節「交付 B」，可以直接貼上。
- **RC-11**：影響範圍已補完，`get_batch` 的呼叫點已窮舉。結論：結算路徑只有在「到期未結算的指令列指向 `batch_no` 小於 1 的批次列」時才會失敗。app/ 內不會產生這種列。這是推論，已標明。
- **RC-14、RC-15**：補遺-4 的判斷規則與末條都已改寫。
- **RC-17**：事實成立。
  - 已落檔的 R1 列，股數不會被任何路徑改寫。
  - 結算也照舊股數成交（store.py:1629-1630）。這比「畫面上不更新」更重：舊股數會實際進到帳冊。
- **N-209b**：共通條款寫入 RC-18、RC-20；另外分列「若 CEO 採甲」（RC-19）與「若 CEO 採乙」（風控的四項最低條件）兩段。
  - 新發現一點，交風控：「總資產 0.00」由「現金鍵不存在、以 0 代入」造成。即使採甲，這種狀況在 confirm_rules 的兩步驟競態中仍可能出現。RC-18 沒有涵蓋到它。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### 交付 A：T-xx 逐項回答

**T-05 凍結截止日的來源**
- **事實**：
  - 兩個鍵都是「含當日」的截止日（models.py:269-273 註解 `end date, inclusive`），由 `portfolio_state` 讀出（store.py:1026、:1028）。
  - ADR D8 第 6 點的判定：任一個不為 None 而且 `today_tpe <= until`，就判為凍結（ADR-0043 :337-338）。
  - 所以「名單入口最後一天被擋的台北日期」等於兩個非 None 值中**較晚的那一個**。只有一個在效期內時，取最大值得到的就是它；過期的舊值比較早，取最大值時不會被選到。
  - engine 的顯示順序不同：EMERGENCY 優先，接著才是 S3（engine.py:397-409）。所以兩者並存、而且 `freeze_until` 比較晚時，`/today` 的 mode_reason 寫的是 emergency 的日期，名單入口寫的是較晚的日期。兩者都是真的，但使用者可能讀成矛盾。這一點交風控在字面處理，例如寫成「名單變更的凍結截止日」。
- **ADR 狀態**：沒有規定（D8 第 6 點只寫判定）。下列約束建議由 tech-writer 補進 D8 第 6 點：
  - C-T05-1：`portfolio_frozen` 改為回傳 `(frozen: bool, until: date | None)`。`until` = 兩個非 None 值的最大值，只在 `frozen` 為真時有值。W-05c′ 的截止日只能取這個回傳值，API 預檢與鎖內共用同一個函式。
  - C-T05-2：截止日含當日，名單入口從截止日的下一個**台北日曆日**起放行。字面若寫「截止日」，請風控決定要不要加「（含）」。
  - C-T05-3：依 ADR-0033 C-9，這個判定不落檔。

**T-09 已有戳記時設定名單，與 FR-24 的邊界**
- **FR-24 的空表邊界**（PRD :178、AC-30 :303）存在，但只在首次設定**之前**有作用：
  - 未確認而且空表時，confirm 被拒（W-15a）。使用者的路徑是：首次設定 → confirm → 戳記改變 → 閘解開（AC-79，PRD :349；ADR D6 第 2 點）。
  - 首次設定讓批次表變成非空，空表條件就不再成立。超額條件也不會因首次設定而成立，因為首次設定要求恰好 n_targets 檔（FR-4）。所以**不會卡死**。
- **真正的邊界是 authorship，不是戳記**：
  - 畫面上的資金確認入口只依 mode 判斷：`shouldRenderRuleSetConfirm` 只在 `mode === "unconfirmed"` 時為真（playbookView.ts:322-324）。
  - mode 由 `rule_set_authorship` 決定（service.py:2150-2152）。authorship 有兩種紀錄：確認旗標，或已提交的參數版本（store.py:1164-1176），不看 TD 戳記。
  - 在 app/ 內，取得 authorship 的唯一 API 路徑是 `confirm_rules`，而它同一次呼叫就寫 `set_capital`（service.py:2019-2034）。`request_rule_change` 在 `app/api/` 內沒有呼叫點（grep 無結果）。所以「已確認」幾乎等於「有戳記」。
  - 反過來，「有戳記但未確認」也存在：未確認時 REBALANCE 會寫 TD=0（service.py:1908-1912，N-209 PRD :62）。

| 設定名單當下的狀態 | 解開閘的畫面路徑 | 說明 |
|---|---|---|
| 未確認、沒有戳記 | 資金確認（畫面有入口）；Q-7 乙時 REBALANCE 也可以 | AC-79 的正常情形 |
| 未確認、有戳記（先前未確認時跑過 REBALANCE） | 同上 | confirm 會再改一次戳記，照樣解開 |
| **已確認（必有戳記）** | **只有 REBALANCE（N-209）** | 畫面沒有確認入口。API 重送資金確認技術上也會解開，但依 D6 第 8 點（R-10）不得寫成解開方式 |

- **使用者只能靠 REBALANCE 解開的情形（從畫面操作而言）**：
  1. 首次設定時規則集已確認。
     - 怎麼會出現：現況 `confirm_rules` 不檢查批次表（service.py:1987-2035），而 `ensure_batches` 在 app/ 內沒有呼叫點（ADR Context 第 1 點）。所以 N-207 部署前「已確認、批次表為空」的 DB 就處於這個狀態。N-207 之後，FR-24 擋住新的發生。
     - CEO 的 DB 是不是這樣：**不明**。§9 P-3 只數檔數，不看 authorship。建議 §9 增列 P-6：「authorship 已確認 × 批次表為空」，只回布林值。
  2. 季度提交的新增組，以及開新輪 (iii)(iv)：設計上就是如此（FR-21，PRD :166-169）。
  3. AC-56：先 REBALANCE、後提交名單，要再跑一次 REBALANCE。
  4. AC-57：REBALANCE 失敗或被擋下後，要重跑 REBALANCE。
- **與 N-209 的依賴**：
  - 上面四種情形的畫面路徑都是 N-209 的入口。N207-M4 保證 N-209 先合入。N-209 FR-2 要求入口常駐，不依名單狀態啟用或停用（N-209 PRD :62）。
  - N-207 合入後，N-209 不得單獨回退（補遺-4 連動規則）。否則第 1～4 種情形在畫面上就沒有解法。
  - Q-7 的影響：
    - 採甲時，未確認狀態下 REBALANCE 被擋，所以未確認時只有資金確認能解開，與 W-12b「首次設定時」的說法一致。
    - 採乙時，未確認狀態下 REBALANCE 寫入 TD=0 也會解開閘。因為未確認的評估不產生任何指令（service.py:2150-2152），這不構成買進風險。
- **對字面的約束**：
  - C-T09-1：名單 API 回傳 `first_confirmation_pending: bool`，定義為 `not rule_set_authorship(台北今日).user_authored`，與決定 mode 的判斷相同。前端不得自行推斷。
  - C-T09-2：W-09c「在資金確認前為待生效」以及 W-12b 中「首次資金確認也會解開」那一句，只在這個旗標為真時出現。旗標為假時用只寫 REBALANCE 的變體句，由 creative-lead 擬稿、風控定稿。

**T-13 差額四類是否互斥**
- **ADR 定義**：今日可進場 = 啟用、不在 S1、不在 S2，而且在 engine 輸入中至少有一筆 planned（ADR-0043 :84）。差額是啟用但不在可進場清單裡的標的。
- **事實**：
  - **待生效 ⟂ 本輪無待進場批次**（互斥）。同一輪各批的戳記相同（D6 第 1 點，:254）。最大輪的 planned 只有兩種可能：閘開就在輸入內，閘未開就是待生效。最大輪沒有 planned，就是「本輪無待進場批次」。
  - **S1、S2 和其他類可以同時成立**。暫停（`playbook_symbols.paused`）與黑名單（`playbook_blacklist`）是兩張表，各自讀取（store.py:968-987），不互斥。
  - **涵蓋性成立**：差額中的任一檔，至少屬於四類之一。
  - D3 第 6 點的「每列恰好一類」講的是被排除的**批次**；W-13 數的是**標的**。兩者是不同的物件，不要混用。
- **方案比較**：

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| (A) 依序判定，一檔只算一類 | 加總等於差額 | 要訂一個優先順序並說明理由；第二個原因被藏起來（例如 S1 恢復後，使用者才發現它仍是待生效） | 中 |
| **(B) 多標記，各類各自計數（建議）** | 每個數字都是可以直接驗證的謂詞計數；不需要優先順序；不藏原因 | 加總可能大於差額，字面要寫明「同一檔可能同時屬於多類」 | 低 |

- **約束**：
  - C-T13-1：後端回傳 X、W 與各類計數。差額由後端另外給（X−W），前端不得以加總代替。
  - C-T13-2：每類的謂詞定義：
    - S1 = `paused`；
    - S2 = 黑名單在效期內；
    - 待生效 = 最大輪有 planned 而且閘未開；
    - 無待進場 = 最大輪沒有 planned。
    - 全部限啟用標的，直接沿用 `engine_batches` 與 `entry_gate_open`。
- **ADR 漏洞，不明**：名單頁上 S2 要以哪一天判定，ADR 沒寫。`symbol_states(on_date)` 的黑名單條件是 `until >= on_date`（store.py:974），`/today` 用的是 data_date（service.py:2208）。
  - TA 提議：名單頁用台北今日，與 D8 第 6 點的 `today_tpe` 同源。
  - 代價：資料落後的那幾天，名單頁的 W 可能比 `/today` 實際評估時大，屬於 R-12 同類的殘留。
  - 這一點請風控確認，再由 tech-writer 補進 D1 第 4 點。

**T-19 API 層能不能取得輪次與批次範圍**
- **不能。**
  - API 只收到 `PlaybookEvaluation`。`BatchSnapshot` 沒有 `batch_round`（models.py:397-421），而且依 N207-C3 不得修改。`Directive` 也沒有 `batch_round`（models.py:349-350）。
  - C17 的 `later_round_keys` 只是「engine 輸入中、第 2 輪以後的 `(symbol, batch_no)` 集合」（修訂一檔 :635），不帶輪次 k。已停止的標的在輸入中只剩 open 批次，範圍會不完整。
- **規格缺陷（C17 比 ADR 窄，依章程以 ADR 為準）**：
  - ADR D3 第 6 點寫的是「任何指令指向第 2 輪以後的批次」都要附輪次說明（:182）。
  - 反例：先評估後停止（FR-10），第 4 批的 R1 仍列在當日指令或 entry_before_exit 清單裡，但第 4 批是已停止的 planned，不在輸入內，所以不在 `later_round_keys` 裡，輪次說明不會出現。
- **需要的修改（交 dev-lead 修 C17）**：
  - C-T19-1：`later_round_keys` 改從 `book` 算，也就是帳冊全表，取 `batch_round ≥ 2` 的全部鍵。`book` 是 :2199 的讀取，晚於 in-flight 的讀取（:2157）；批次列從不刪除，所以 `book` 一定涵蓋所有指令指向的批次。
  - C-T19-2：`EngineExclusions` 新增加法欄位 `round_spans: tuple[RoundSpan, ...]`，`RoundSpan = (symbol, batch_round, first_batch_no, last_batch_no, batch_count)`。由 service 內的純函式從同一個 `book` 算出，只列出 `/today` 有引用的 (symbol, round)。engine 不讀。
  - C-T19-3：N207-T22 斷言 5 增列一個情境：已停止標的的第 2 輪 planned 批次，帶一筆未結算 R1，輪次說明要出現。
  - 有了 `round_spans`，W-19 就可以改寫成含具體範圍的版本，由 creative-lead 擬稿。

**T-20 高波動部署通知（STOP-3）**
- **現況**：ADR 只寫成停止條件（D7 第 6 點，:308-313；§9 P-4，修訂一檔 :610）。依修訂一第 7 點，P-4 大於 0 時才補設計，不預先實作。
- **STOP-3 觸發後告知 CEO 的通道**，比照 N-209 FR-17／RC-8（N-209 PRD :94）：
  1. CEO 在本機跑 P-4 的唯讀 SQL，結果由 coordinator 記入交件紀錄。部署暫停。
  2. coordinator 擬 CEO 通知，內容包括：列數與代號、P3 門檻 BIAS25 由 15% 變為 20%、這屬於放寬賣出規則、部署已暫停、要請 CEO 在保留與取消之間二選一。風控逐字定稿。CEO 以書面確認收到並裁示。裁示之前不部署。
  3. 選擇取消：TA 另行設計取消路徑，送風控，不得手動改 DB。
  4. 選擇保留：同一則或下一則 CEO 通知寫明「自部署起適用」，並依下列方案準備 app 內通知。
- **app 內通知方案**：

| 方案 | 內容 | 優點 | 缺點 | 風險 |
|---|---|---|---|---|
| 甲 | 不做 app 內通知，以 app 外的 CEO 通知（有收到確認）加上名單列的常駐標籤 W-25d「高波動：已適用」代替 | 零新增狀態與端點；單一使用者，收到確認有書面紀錄 | 要風控修改 R-13、AC-73 | 低（需風控同意） |
| **乙（若風控維持 AC-73）** | 要列的代號由 `high_volatility=1 AND high_volatility_changed_on IS NULL` 推出，不存快照。「已關閉」記在後端新的僅新增表，以一般 INSERT 加 `ON CONFLICT DO NOTHING` 寫入 | 列數為 0 時自動不顯示；使用者之後經新路徑改過標記的代號會自然退出清單 | 新增一張表、一個 POST、前端元件；屬 ADR 層的變更 | 低 |
| 丙 | 「已關閉」存在前端 localStorage | 不必改後端 | 換瀏覽器或清除資料就重新出現，也沒有稽核紀錄 | 中，否決 |

- **建議**：先請風控裁示甲是否足夠。風控若維持 AC-73，就採乙，並由 TA 出 ADR-0043 補遺（新表不屬於 D4 名單路徑的寫入範圍，要另外列明）。乙的約束：
  - GET 不寫入；
  - 通知字面放在 `wording.py`，代號升冪；
  - 不得用 `INSERT OR REPLACE`；
  - 已關閉的狀態不放進 `playbook_state`。
- **ADR 措辭不一致**：D7 第 6 點寫「自部署起生效」（:311），FR-46、AC-73 與 W-20 用的是「自部署起適用」（FR-49）。建議 tech-writer 把 ADR 改成「適用」。

**T-22 凍結說明句的顯示條件**
- **ADR 沒有規定條件**（D8 第 6 點，:344，只寫「交 PM 與 creative-lead」）。
- **事實**：
  - 判斷殘留是否成立，需要 data_date。條件是 `until < 台北今日` 而且 `data_date ≤ until`。
  - 名單讀取路徑目前沒有 data_date。唯一落檔的類似值是快市狀態的 `measured_on`（service.py:2218、store.py:1072）。**TA 否決**拿它來用，因為那會把名單判定耦合到另一個功能的狀態。
  - 兩個 until 鍵過期後不會被清掉（engine.py:1156 以比較日期判斷），所以「鍵存在」不能拿來當顯示條件。

| 方案 | 優點 | 缺點 |
|---|---|---|
| **甲 常駐（建議，搭配 B 版字面）** | B 版是一條規則陳述，任何時候都為真；不依賴任何狀態；不違反「不以日期或狀態高亮」 | 從來沒凍結過的使用者也會看到 |
| 乙 只在殘留成立時顯示 | 只在相關的時候出現 | 名單讀取路徑要多讀日線（網路），或新增落檔欄位；這個 data_date 可能與 `/today` 那次讀到的不同，句子會忽隱忽現（第二個定義來源） |

- 由 PM 決定、風控裁示。若選乙，回 TA 補資料日的單一來源設計。

**T-24「每輪 {actual} 批」的口徑**
- **事實**：
  - 新一輪依鎖內讀到的現行 bpt 編號（D3 第 2 點，:100）。bpt 一旦改過，各輪的批數就可能不同。
  - engine 只計算最大輪（D3 第 6 點）。末批分支用的是**現行** bpt，判斷式是 `batch_no - offset < params.batches_per_target`（ADR :133）。所以最大輪批數不等於 bpt 時，末批的判定會改變。舊輪已全部終結，不再被計算。
- **決策（TA）**：
  - C-T24-1：W-24 只依**最新一輪**判斷是否揭露，句子寫明是第幾輪：「{symbol} 第 {k} 輪 {actual} 批，與現行 bpt 不一致」。數字由後端從帳冊依 (symbol, batch_round) 計數。
  - C-T24-2：W-11 的「（每輪 {bpt} 批）」改為該輪的實際批數。W-19 的「每輪 {bpt} 批」在任一輪批數不等於 bpt 時會不實，要改寫或拿掉。兩者都交 creative-lead 與風控。
  - 補充交風控：最大輪批數不等於 bpt 時，末批補足的行為會改變。這是 FR-27 另案的範圍，W-24 只揭露不一致，沒有寫出後果。要不要寫後果，請風控裁示。

**T-10 台股代號的形狀規則（N207-C12）**
- **現有程式中的規則，沒有一條符合 FR-5：**
  - `TW_SYMBOL_RULE` 是黑名單，只拒絕 `[0-9]+[Kk]`，其餘一律放行（admission.py:125-136；以 fullmatch 判定、未命中即放行，:158-162；設計說明 :37-43）。所以 `2330.TW`、空字串都放行。狀態是 `verified=False`。
  - `SYMBOL_PATTERN = r"^[A-Za-z0-9.-]+$"`（api/event_study.py:118-121），前端 `ALLOWED_SYMBOL_PATTERN`（tradingViewSymbol.ts:43）與它相同。兩者都放行 `2330.TW`。
  - `leverage/detect.py:50-51` 會剝除 `.TW`、`.TWO`、`.US` 後綴，屬於正規化，FR-5 禁止這樣做，**不得沿用**。
- **結論**：正向的形狀規則**不存在，具體內容不明**，要由 data-engineer 新訂。依 ADR「與其他 ADR 的關係」中的 ADR-0024 列（:380），這條規則放在名單模組，不放進資料層准入。現行的 K 後綴准入仍會在取日線時生效，屬於確定性失敗。
- **新發現的衝突**：AC-04 寫「非數字代號」要拒絕（PRD :255），但 B、L、R、U 後綴是合法的台幣計價代號（admission.py:39-41）。要請 data-engineer 與 PM 改寫 AC-04。

**T-02「在途指令」與現有用詞**
- **事實**：
  - 「在途」在 `backend/app/**` 與 `frontend/app/**`（不含 `__tests__`）都是 0 筆。程式碼的 `read_in_flight`（store.py:1474）是英文識別名，不面向使用者。
  - 現有用詞：
    - 「已產生、尚未結算的 R 系列買進指令」（wording.py:384、:428、:468、:483）；
    - 「尚未結算的賣出指令」（wording.py:607、:621、:804）；
    - 指令狀態標籤「待結算」（playbookView.ts:206；wording.py:891）。
- **建議**：W-02 把「在途指令」改為「已產生、尚未結算的指令」，與 W-02 自己的通用句一致。筆數取自同一次 `read_in_flight` 讀取，不另讀一次。

#### 交付 B：修訂一補遺二（可直接貼上）

````markdown
# ADR-0043 修訂一補遺二（tech-architect 2026-11-09，依風控 `work/reviews/2026-11-09-補遺確認RC7結案與Q7意見-風控.md` RC-11、RC-14、RC-15、RC-17～RC-20）

## 補遺二-1（RC-11）：取代補遺-5b、5c 的「舊資料異常」子彈、5d

### 1a：取代補遺-5b（N-207 規格 乙、§9「說明」新增的一點）
  - `batch_no` 小於 1 的列不是靜默沿用，而是讀到就失敗。這是現況就有的行為，不是 N-207 引入的。
    - 驗證規則：`BatchState.batch_no` 是 `Field(ge=1)`（`models.py:213`），schema 沒有 CHECK（`store.py:72`）。建構點是 `_row_to_batch`（`store.py:878-914`）。
    - **讀全表**（`list_batches`，`store.py:870-875`）：表內只要有一列，以下呼叫點全部 raise。
      - `service.py:1828`，`rebalance`：`/rebalance` 回 500，不寫入。
      - `service.py:1962`，`_evaluation_data_date`：由未確認時的 `confirm_rules`（`:2025`）呼叫。`/confirm-rules` 回 500，`confirm_rule_set` 與 `set_capital` 都沒有執行。已確認時不走這條，`/confirm-rules` 不受影響。
      - `service.py:2062`，未確認路徑的 `/today`：回 500，零寫入。
      - `service.py:2158`、`:2199`，已確認路徑的 `/today`：回 500。
      - `service.py:2323`，全部出清，在取寫鎖之前：`/emergency-exit` 回 500，零寫入。
      - `store.py:959`（`roll_peak_closes`）、`:1282`（`apply_effects` 的 defer_reset）只在 `/today` 的 `:2158` 之後被呼叫，執行不到。
    - **只讀 open 而且 remaining > 0 的列**：`_read_exit_state`（`store.py:1455-1472`，建構點 `:1469`）。
      - 呼叫者：`_read_pending_exits`（`:378-380`）←`read_in_flight`（`:1474-1497`）←`service.py:2073`（未確認 `/today`）、`:2157`（已確認 `/today`）；以及 `commit_emergency_exit` 的鎖內讀取（`store.py:1434`）。
      - 不良列是 open 時，已確認的 `/today` 在 `:2157` 就失敗，早於 `:2158`。全部出清已經在 `:2323` 先失敗，到不了 `:1434`。
    - **已確認的 `/today` 在失敗之前已經跑過結算**（`:2153`）。每一筆 claim（`store.py:1548-1555`）與動帳（`save_batch`、`set_cash`）都各自 commit，所以失敗前已結算的列都已落檔，不會回滾。
    - **結算路徑本身**（`_settle_pending`，`service.py:1553-1707`）不讀全表：
      - 它先讀 `pending_directives`（`store.py:1505-1529`）。`Directive.batch_no` 沒有下限（`models.py:350`），所以這一步不會失敗。
      - 接著以 `get_batch`（`store.py:949-955`）逐筆讀指令指向的那一列。
      - `get_batch` 呼叫點窮舉：
        - `store.py:1293`（`_update_batch`）←`apply_effects` 的 `:1278`、`:1286`、`:1288`。`effect.batch_no` 來自 engine，engine 只收 `BatchState`，所以一定 ≥ 1；而且在 `/today` 中，`apply_effects`（`service.py:2213`）晚於 `:2158`。**不會失敗。**
        - `store.py:1306`（`record_schedule`）：app/ 內沒有呼叫點（grep 只有定義本身）。**執行不到。**
        - `store.py:1610`（MISSED）、`:1616`（executed），在 `settle` 中，←`service.py:1656`：位於 claim 已 commit 之後。
        - `service.py:1712`（`_batch_of`）←`:1653`（出清賣單成交，claim 之後）、`:1660`（買單成交，`settle` 之後）、`:1732`（G1 擋下的說明句，該筆沒有 claim）、`:1783`（出清賣單的過期說明）。
      - **結論（讀碼推論，未實跑）**：
        - 結算只會在「到期、未結算的買賣指令列，其 (symbol, batch_no) 指向 `batch_no` 小於 1 的批次列」時失敗。
        - 失敗點在 `:1610`、`:1616`、`:1653`、`:1660` 時，該筆已 claim 但未動帳（R-6′ 的失敗變體）。在 `:1732`、`:1783` 時，該筆沒有 claim，但同一輪先前各筆已經落檔。
        - app/ 內產生指令的路徑都以 `BatchState` 為來源（engine、`plan_emergency_exit` 的 open_batches）；REBALANCE 列的 `batch_no` 為 None。所以 app/ 不會產生這種指令列，它只可能來自 app/ 以外的寫入。
        - 沒有查 git 歷史，無法確認 `ge=1` 是否一向存在。
        - `POST /settle`（`api/playbook.py:613-627`）只走這條路徑；沒有上述指令列時不受影響。
    - **使用者面向的後果**：排程台頁無法載入（`/today` 兩條路徑都回 500），全部出清無法使用，REBALANCE 無法使用，規則集未確認時也無法確認規則集。
    - P-2 以 SQL 直接讀表，不經 `BatchState`，看得到這種列。

### 1b：取代補遺-5c 中「舊資料異常（風控 R-1）」子彈的第 4、5 點
     - `batch_no` 小於 1 的列到不了 engine：讀取時就 raise。`/today`（含未確認路徑）、`/rebalance`、全部出清、未確認時的資金確認都回 500；排程台頁無法載入，全部出清無法使用。已確認的 `/today` 在失敗之前可能已經 commit 結算。這是現況就有的行為，完整範圍見 N-207 規格 §9「說明」。
     - 部署前唯讀盤點發現第 1 輪批數不等於 bpt、`batch_no` 最大值大於 bpt、最小值不等於 1，或有斷號時，停止部署，回報 TA 與風控（N-207 §9 STOP-1）。

### 1c：取代補遺-5d（Consequences「舊資料異常（R-1）」一點）
  - **舊資料異常（R-1）**：
    - 斷號、批數多於 bpt 的舊資料原樣沿用舊算法，可能沒有末批補足，或每批只買 1 股。
    - `batch_no` 小於 1 的列在讀取時就 raise：`/today`（含未確認路徑）、`/rebalance`、全部出清、未確認時的資金確認都回 500，也就是排程台頁無法載入、全部出清無法使用；已確認的 `/today` 在失敗前可能已經 commit 結算。這是現況就有的行為，不是 N-207 引入的。
    - 部署前盤點發現就停止部署，不以揭露代替（N-207 §9 STOP-1；回報內容依 RC-12）。

### 1d〔TA 追加，風控可刪〕：N-207 規格 乙、§9 表 P-2 列，「盤點項目」欄末尾增列
；另計 `playbook_directives` 中 `settled = 0` 而且 `batch_no < 1` 的列數。大於 0 → **STOP-1**（理由：結算路徑只會因這種列而失敗，見「說明」）

## 補遺二-2（RC-14、RC-15）：補遺-4 修改

### 2a：取代補遺-4「判斷者」子彈的 BLOCKING 條件清單
      - R1 不是 `exit=0`；
      - **R2 不是 `exit=0`，或沒有輸出**（例如 `<M_209>` 不是有兩個 parent 的 merge commit）。此時回 TA 定義替代的 S，不得自行補 S；
      - R3 任一條不是 `exit=0`〔TA 追加〕；
      - R3 的任一條 `--grep=<s>` 有輸出；
      - R3 的 revert 掃描有輸出，經判讀與 S 相關；
      - R4 不是 `exit=0`〔TA 追加〕，或 R4 有輸出；
      - **R5 任一條沒有輸出、`exit` 不是 0，或計數為 0**。說明：`git grep -c` 零命中時不會印出 0，而是沒有輸出並回 exit 1。
      判讀不了就回 TA。檢查綁定 qa 審查的那一個 commit；head 一變動，全部重做。

### 2b：取代補遺-4「連動規則」末條
      - 〔風控 2026-11-09 保留〕N-209 的前提單（N-177a、N-195、N-196、N-197a、**N-209b**）任一被回退時，N-209 並發提醒的事實範圍（風控 2026-11-09 F-1～F-3 與 X-1 的排除）就失去前提。採甲案時，authorship 閘就在 N-209b 內。觸發時：
        1. N-209 的並發提醒，在入口下一次被使用之前，要撤下或更新。因為合併就是部署，撤下或更新必須和該次回退在同一次 push。更新後的事實範圍要先經風控逐字定稿；定稿之前只能撤下。〔TA 建議：撤下提醒時，同時停用入口，由風控裁示是否必要。〕
        2. 依 RC-8 (1)(2) 通知 CEO：R-α（N-177a、N-195、N-196）被回退時，11-07 第一則通知恢復有效；N-197a 被回退時，更正版恢復有效。由 coordinator 擬稿、風控逐字定稿，CEO 確認收到；最遲在入口下一次被使用之前送達。
        3. 採甲案時，若被回退的是 N-209b，等於 authorship 閘消失、回到乙案的狀態。此時風控 2026-11-09 對乙案的立場適用：「確認規則集並設定資本額」按鈕一項必須列入並發提醒，乙案的四項最低條件也必須成立。不成立時，依第 1 點撤下。
        4. 回退一律以 revert commit 進行（同前述連動規則）。
        5. 本條同時寫入 N-209 PRD（AC-14 附近），因為它約束 N-209 本身，與 N-207 是否合入無關。由 product-manager 落文。

## 補遺二-3（RC-17）：事實確認（供 creative-lead 擬 N-209 結果畫面 ok 分支字面）

- **成立。** 今日指令表已列的指令，不會因 REBALANCE 而重算或改寫：
  - R1 股數由 `planned_batch_shares` 以評估當下的 `portfolio.total_deploy` 算出（`engine.py:200-215`；`service.py:2200`、`:2207-2209`）。
  - 指令列落檔後不 UPDATE、不 DELETE（N172-C11）。claim 只改 `settled`、`settled_at`、`settled_open_price`、`status`（`store.py:1549-1553`），不改股數。
  - `/today` 列出的是該預定執行日已落檔的列（`_read_logged`，`store.py:617-628`；`service.py:2259`）。
  - 同一個預定執行日再評估時，K1（`store.py:488-496`），以及 R 系列的 K2（同一檔、同一預定執行日只能有一列 R 系列，`store.py:501-507`），讓新算出的股數不會再落檔。
- **比「畫面上不更新」更重的一點**：結算以落檔列的 `directive.shares` 成交並扣現金（`store.py:1629-1635`）。TD 調降時，舊股數會實際進到帳冊。
- **新 TD 從哪裡開始適用**：
  - 之後新產生的指令，也就是預定執行日不同的評估，或同一日中該檔還沒有 R 系列列時的再評估；
  - 由於 N-209 依 F-6′ 不觸發 `/today`，使用者要在下一次讀取 `/today` 時才會看到新產生的列；
  - S、P 系列不依 TD 計算。

## 補遺二-4：N-209b 規格（RC-18、RC-20；甲／乙分段）

### 共通（兩案都適用）
- **N209b-C1 範圍**：後端 `app/playbook/{service,models,wording}.py`、`app/api/playbook.py`。排在 N-197a 合入之後、N-209 前端之前，獨立 PR。`set_total_deploy(` 在 `rebalance` 內仍然恰好出現一次（N197a-T7）。N197a-C1 屬於 N-197a 自身的範圍，不重開。
- **N209b-C2 `RebalanceResponse` 加法欄位**（既有欄位的型別與值不變）：
  - `previous_total_deploy_recorded: bool`：「TD 鍵存在」，不是「值不為 0」（RC-20）。讀取時點與 `previous_total_deploy` 相同：ok 與 insufficient_data 取 snapshot，superseded 取鎖內讀取。`Field(description=…)` 要寫明「描述 `previous_total_deploy` 是否來自紀錄」；`previous_total_deploy` 本身也加 description，寫明鍵不存在時以 "0" 代入。
  - `previous_total_deploy_2f: str | None`：鍵不存在時為 None。
  - `new_total_deploy_2f`、`total_assets_2f: str | None`。
  - `written_at_taipei: str | None`：只有 ok 有值。由 service 產生 `at`，傳給 `set_total_deploy(at=…)` 後原樣格式化。
- **N209b-C3 `RuleSetResponse` 加法欄位**：`total_deploy_recorded: bool`（同樣定義為鍵存在）、`total_deploy_2f: str | None`、`total_deploy_set_at_taipei: str | None`。
- **N209b-C4 單一格式化步驟（RC-20）**：
  - `.2f` 金額只能經同一個函式產生，沿用現行 `f"{x:.2f}"` 的語意，不改捨入方式（`service.py:1873-1875`）。
  - `message` 內的金額與 `*_2f` 欄位要取同一個字串物件。測試斷言：每個非 None 的 `*_2f` 欄位，都以子字串形式逐字出現在 `message` 中（訊息有該金額時）。
  - 時間一律以 `taipei_wall_time` 格式化（N-197a 規格名，以實際合入為準），格式 `YYYY-MM-DD HH:MM:SS 台北時間`，與 `REBALANCE_SUPERSEDED` 的 `{set_at}` 相同。
- **N209b-C5 RC-18**：
  - ok 而且 `previous_total_deploy_recorded` 為假時，`message` 改用新識別名 `REBALANCE_RESULT_NO_PREVIOUS`。這句不得含 `{previous}`，要寫明「先前沒有紀錄」，由風控逐字定稿。
  - insufficient_data 的 `previous_total_deploy_2f` 在鍵不存在時為 None（`REBALANCE_BLOCKED` 本身不含金額，`wording.py:1057-1060`）。
  - 前端只顯示 `*_2f` 與 `message`，不得顯示原始的 `previous_total_deploy`（F-8 加強）。
  - 新字面在 N-209b 合併前定稿。
- **N209b-T1**：
  - 參數化三種情境：鍵存在、鍵不存在、值為 "0" 但鍵存在。驗證 recorded 旗標、`*_2f` 欄位與 `message` 用了哪一個識別名。
  - 加一個情境：「已確認、但 TD 鍵不存在」（`confirm_rule_set` 已 commit、`set_capital` 尚未執行，`service.py:2021`→`:2030`）。這時 REBALANCE 回 ok，並使用 `_NO_PREVIOUS`。
- **〔TA 新發現，交風控裁示〕現金鍵不存在**：
  - 現金鍵不存在時，`portfolio_state` 以 0 代入（`store.py:1022`），ok 訊息的「總資產」就是代入值。
  - 即使採甲，上述兩步驟競態中，這種狀況仍可能出現。RC-18 只涵蓋 TD。
  - 可選：(a) 增 `cash_recorded` 與「總資產」變體句；(b) 現金鍵不存在時拒寫，回新 status。請風控裁示，TA 再補規格。

### 若 CEO 採甲（RC-19）
- **N209b-A1 閘的位置**：
  - `rebalance` 的第一個 store 呼叫是 `rule_set_authorship(as_of)`，比照 `settle_on_request`（`service.py:1543-1550`）。
  - 未確認時立即回傳 `status="unauthored"`。在任何 `list_batches`、日線載入、`set_total_deploy`、`record_directives` 之前返回。cash、TD、set_at、source 都不寫，也不寫指令列。
  - AST 測試：authorship 讀取是 `rebalance` 內的第一個 store 呼叫。
- **N209b-A2 型別**：`RebalanceResult.status` 的 Literal 加入 `"unauthored"`。
  - 回應中 `total_assets`、`new_total_deploy`、`deployed_value`、`overshoot` 以及所有 `*_2f`、`written_at_taipei` 都為 None，`directives=[]`。
  - `previous_total_deploy`（型別仍是 str）可以照常由唯讀的 `portfolio_state()` 填入，但畫面不得呈現它。
- **N209b-A3 字面**：新識別名 `REBALANCE_UNAUTHORED`，風控逐字定稿，N-209b 合併前完成。內容限於：
  - 未執行；
  - 沒有寫入任何值；
  - 原因是規則集尚未確認；
  - 指向「確認規則集並設定資本額」。
  - 不得有任何金額（含 0.00），不得有「已執行」「重算」，不得有時機建議。
- **N209b-A4 F-4 改寫**：封閉集合改為 `{ok, insufficient_data, superseded, unauthored}`；unauthored 分支只顯示 `message`。
- **N209b-A5 B-1 改寫**：「N-209b 不再只做加法」。`rebalance` 新增一個提前返回，加上 Literal 擴值。其他分支的行為與字面不變；ok、insufficient_data、superseded 三個分支的既有欄位值逐值不變（差分測試）。
- **N209b-A6 測試**：
  - unauthored 前後，`playbook_state` 四個鍵逐位元相同；
  - 指令列數不變；
  - 日線 loader 的 spy 呼叫次數為 0。
- **連帶**：
  - 並發提醒不列入 F-1 的按鈕一項（風控 2026-11-09）。
  - 與 ADR-0043 D6 一致：未確認時只有資金確認能解開首次設定的閘（見 T-09）。
  - S-5（未確認模式下停用入口並附原因）是否與 N-209 FR-2 相容，由 PM 判定。後端的閘仍然必須存在。

### 若 CEO 採乙（風控 2026-11-09 的四項最低條件；未全部做到，風控將否決 N-209 字面）
- **N209b-B1**（i）：同 N209b-C5。
- **N209b-B2**（ii）：增 `cash_recorded: bool`。現金鍵不存在時，`message` 改用不含「總資產 {assets}」的變體句（風控定稿），`total_assets_2f` 為 None。
- **N209b-B3**（iii）：`RebalanceResponse` 增 `user_authored: bool` 與 `deploy_ratio_pct: str`。未確認時，確認畫面與結果都要寫明「規則集尚未確認，本次用的是系統預設比例」（風控定稿）。
- **N209b-B4**（iv）：`RuleSetResponse` 增 `total_deploy_written_before_confirmation: bool`，定義為 `not user_authored and total_deploy_recorded`。
  - 理由：在 app/ 內，未確認期間唯一的 TD 寫入者是 REBALANCE，因為 `confirm_rules` 先取得 authorship 再寫 `set_capital`（`service.py:2019-2034`）；`request_rule_change` 在 `app/api/` 內沒有呼叫點。
  - 若日後新增別的 authorship 來源，要回 TA。
  - 讀到這筆 TD 時，要標明是在規則集確認前由 REBALANCE 寫入（風控定稿）。
- **N209b-B5**：並發提醒必須列入「確認規則集並設定資本額」按鈕一項，並寫明它就是一次資金確認，適用 F-2、F-3。
- 乙案下 B-1 維持「只做加法」。
````

#### 對實作的約束（彙整，qa-reviewer 可以逐條檢查）

C-T05-1～3、C-T09-1～2、C-T13-1～2、C-T19-1～3、C-T24-1～2 的內容見交付 A；N209b-C1～C5、A1～A6、B1～B5 見交付 B。禁止事項：
- 前端不得自行計數，也不得自行判斷 authorship 或輪次；
- 名單判定不得讀快市狀態的 `measured_on`；
- 代號處理不得沿用 `leverage/detect.py` 的後綴剝除。

### 其他部門
本次沒有參與。

## 三、驗證

- **讀過的文件**：
  - N-207 字面草稿全文；
  - ADR-0043 落檔版全文；
  - 修訂一檔全文（含 N-207 規格修訂 :567-686）；
  - 補遺檔全文；
  - PRD v3 :120-249 與 grep 結果；
  - N-209 PRD（grep FR、Q-7）；
  - N-209 Q3Q4 評估 :40-174；
  - 風控第二輪全文；
  - 風控 R-12、R-13 段（grep）。
- **讀過的程式**（只讀；行號依目前 checkout）：
  - `service.py`：:1516-1553、:1553-1807、:1809-2081、:2123-2272、:2290-2334、:2410-2453；
  - `store.py`：:255-287、:488-536、:612-636、:866-1074、:1150-1189、:1268-1322、:1338-1377、:1395-1497、:1505-1679；
  - `models.py`：:207-226、:255-276、:338-351、:372-421、:627-695；
  - `engine.py`：:380-413、:1140-1199；
  - `wording.py`：:378-393、:1040-1063；
  - `api/playbook.py`：:183-263、:575-715；
  - `data/admission.py` 全文；
  - `api/event_study.py`：:112-133；
  - 前端 `playbookView.ts`：:196-211、:305-324；
  - 以 grep 查過：「在途」與「結算」相關用詞、`get_batch` 與 `list_batches` 的呼叫點、`record_schedule` 的呼叫點、`batches_per_target`、`SYMBOL_PATTERN`、`/settle` 的前端呼叫者（無）。
- **沒有查證的部分**：
  - 沒有 Bash，所以 RC-11 的失敗路徑、RC-17、R1～R5 的 git 行為都沒有實跑，屬讀碼推論。`git grep -c` 零命中的行為採風控的陳述。
  - 沒有查 git 歷史，無法確認 `ge=1` 是否一向存在，也無法確認有沒有 app/ 以外的寫入。
  - 前端在 `/today` 回 500 時，是否仍顯示全部出清按鈕。
  - N-195、N-196、N-197a、N-209、N-209b 都尚未合入；`taipei_wall_time`、`set_total_deploy` 只是規格名稱。
  - CEO 本機 DB 的 authorship、批次數、`batch_no < 1` 的列，都不明。
- **需要 CEO 親自確認**：Q-7 甲或乙；若 STOP-3 觸發，要裁示保留或取消。

## 四、下一步

1. **risk-compliance-officer**：
   - 裁示 T-13 的計數方案 (B)，以及名單頁 S2 的判定日期；
   - T-20 甲是否足夠；
   - T-24 要不要揭露後果；
   - T-05 截止日的字面；
   - N-209b 的現金鍵不存在問題；
   - 補遺二-1d、2a 的〔TA 追加〕條款要保留或刪除；
   - 2b 第 1 點的 TA 建議。
2. **tech-writer**：
   - 補遺二-1a～1c 依 RC-11 可以併入，「事實與下列不符才回風控」；
   - 把 T-05、T-13 的約束補進 D8 第 6 點與 D1 第 4 點（風控確認後）；
   - 把 D7 第 6 點的「生效」改為「適用」。
3. **dev-lead**：
   - C17 依 C-T19-1～3 修正（`later_round_keys` 改從 `book` 算，加 `round_spans`）；
   - 名單 API 加 C-T09-1、C-T13-1、C-T24-1 的欄位；
   - §9 增列 P-6 與 1d（若風控保留）；
   - 併入補遺二-2a。
4. **creative-lead**：
   - W-02 改用「已產生、尚未結算的指令」；
   - 依 C-T09-2 擬已確認時的變體句；
   - W-11、W-19 依 C-T24-2 改寫；
   - W-19 可依 `round_spans` 改寫成含具體範圍的版本；
   - 擬 RC-17、RC-18 的變體句；採甲時再擬 `REBALANCE_UNAUTHORED`。
5. **data-engineer 與 PM**：
   - data-engineer 依 T-10 新訂正向的形狀規則；
   - 兩方共同改寫 AC-04 的「非數字代號」。
6. **product-manager**：
   - 裁定 T-22（TA 建議常駐）；
   - 依補遺二-2b 第 5 點，把前提失效條款寫入 N-209 PRD；
   - 判定 S-5 與 FR-2 是否相容。
7. **coordinator**：
   - Q-7 送 CEO 裁決時，附上 N209b 甲、乙兩段的規格代價；
   - P-4 大於 0 時，依 T-20 的通道啟動 CEO 通知流程。

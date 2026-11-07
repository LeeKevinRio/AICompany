# 修訂六、ADR-0042、N-199 審查與 REBALANCE_SUPERSEDED 定稿

- 審查者：risk-compliance-officer
- 日期：2026-11-07
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# 風控審查：修訂六比對、ADR-0042 草案、N-199 spec、`REBALANCE_SUPERSEDED` 定稿、N-197 (b) 通知補充（risk-compliance-officer，唯讀）

## 一、本次結論

**整體結論：CONDITIONAL APPROVE。** 本輪沒有新的否決，先前對 (D)、(E) 的 VETO 維持不變。

- **修訂六第 6 節索引第 1～13 項：都符合。**
  - 1.5 第 2 點「`<tip>` 可以不同」成立。安全性其實不靠「product 只往前長」這個前提：`<base>` 必須相同才算通過，前提一旦不成立，`<base>` 就會不同，判為要重做，方向是安全的。這個前提只是用來說明，正常情況下不會被誤判成要重做。
  - 2.2「鍵不存在就視為不變式違反，依 C-11 失敗」：接受。我讀碼核對過不變式的三個依據，都成立。
- **ADR-0042：決策 P1 我核可，但有四項文字上的 required**，見第二節第 2 點：
  - 「E-2 不消除」的判定成立。
  - ADR-0041:114 的補註，草稿要換成我的定稿。
  - 和 N-177b 的先後我接受，附條件。
  - 草案內部有一處矛盾：N198-T9 要用 N-199 的工具，「先後與相依」第 4 點卻寫 N-199「不相依」。
- **N-199：N199-C 列為 required。** 第 5 節的隱私與命中回報有兩項 required：
  - 拿掉「coordinator 以 repo 以外的方式轉給 CEO」這條路徑；
  - N199-B 有命中時，也要請 CEO 核對券商紀錄。
- **`REBALANCE_SUPERSEDED`：定稿用候選 A，逐字照錄**，見第二節第 4 點。
- **N-197 (b) CEO 通知：要補。** 要附一則補充，把「全部出清」和直接呼叫 `/settle` 兩條並發路徑補進去，並且明說不要因此延後出清。逐字全文見第二節第 5 點。
- **修訂五（N-177a 停止點）：我同意不必送我審。** 理由見第二節第 6 點。

## 二、各部門回報

### risk-compliance-officer（本人，唯讀）

#### 1. 修訂六第 6 節索引比對

| # | 結論 | 說明 |
|---|---|---|
| 1 | 符合 | 我上一輪五項 required 的對應：<br>• 第 1 項（獨立計算並列出 40 碼）→ 1.3<br>• 第 2 項（每條指令印出 `exit=`）→ 1.2、1.3<br>• 第 3 項（執行者獨立）→ 1.3、1.4，另外加上「不是 `<base>..<head>` 任何 commit 的作者，也不是 Co-Authored-By」，比我的要求更嚴<br>• 第 4 項（綁定 qa 審的 commit）→ 1.5 第 2、4 點<br>• 第 5 項（head 變動就重做）→ 1.7<br>作者端用 `git rev-parse HEAD`。本機若有沒 push 的 commit，`<head>` 會和 (ii) 的 `origin/<PR>` 不同，結果是判 BLOCKING，方向安全。 |
| 2 | 符合 | 推導：head 不變（1.7 保證），product 新增的 commit 又都不在 head 的祖先裡時，兩邊的共同祖先集合不變，所以 `<base>` 不變。<br>若有人 force push product，或把 PR 分支的中間 commit 先合進 product，`<base>` 可能改變，會被「`<base>` 必須相同」擋下，判為要重做。<br>放寬的只有 tip，ancestry 的判定對象 `<base>` 沒有放寬。C8 管的是先後順序；「合入前要 merge 最新 product」由 C9 管，不受這一點影響。 |
| 3 | 符合，附 suggested S1 | 錨點涵蓋了我的 suggested，加上 f-string DDL 與常數定義行，是正確的擴充。「只比錨點、不比參數」符合我要的「合法改簽名不誤判」。<br>刪掉函式本體、卻保留 def 行的情況，錨點抓不到。但 1.6 末句已要求 qa 讀完整份 diff，所以可以接受。 |
| 4 | 符合 | N197a-C8 的 `<M_1>`、`<M_2>` 是 N-195、N-196；QB-N197a-2 是 BLOCKING。 |
| 5 | 符合 | 我核對了三點：<br>• `_write_state`（store.py:690-700）只有收到 None 才刪鍵；<br>• `set_capital`（:1033-1055）以單一 `_set_state` 交易寫入四個鍵；<br>• app 內兩個 `set_capital` 呼叫點（service.py:1908、:2030）都不傳 `at`，所以 set_at 一定是 `datetime.now(UTC).isoformat()`，帶時區。<br>拒絕路徑上缺鍵、或 set_at 沒有時區，確實只會在不變式被破壞時發生。<br>`from None`、T11 斷言「例外訊息不含鍵值」，符合隱私要求。<br>500 由 `server_error.py` 回固定的 `Internal Server Error`，不帶任何值。<br>不捏造數字、不猜時區、不寫入，fail closed，方向保守。另見 S4。 |
| 6 | 符合 | 我驗算了 T12 的兩組值：03:04:05.678901 UTC → 11:04:05 台北時間；16:30 UTC → 次日 00:30。<br>「微秒截去、不四捨五入」「台灣沒有日光節約時間」都正確。<br>精確到秒的理由成立。 |
| 7 | 符合，附 suggested S3 | docstring 的語意正確：superseded 時是「鎖內讀到、別的操作寫入的目前值」，不是「本次之前的值」。 |
| 8 | 符合 | T10 (a)～(e) 涵蓋了我要的「新增寫入者就讓測試失敗」，另外補了原始 SQL 與無法靜態判讀的呼叫。<br>「W 少了成員就自己更新常數」：方向是寫入者變少，可以接受。 |
| 9 | 符合 | C1 的範圍與 2.1～2.4 的程式位置一致。 |
| 10 | 符合 | 比我的 suggested 更寬，刻意過度涵蓋，寧可誤報，方向正確。 |
| 11 | 符合 | 兩處指涉都已改成更正版。 |
| 12 | 符合 | 我抽查四項，和現在的 checkout 一致：<br>• `set_capital` :1033-1055<br>• `EMERGENCY_RULE_ID` :313<br>• `UNKEYED_RULE_IDS` :267<br>• `claim_directive` :1531 |
| 13 | 符合 | 我獨立核對了 uvicorn 與 middleware 的論證，邏輯成立：`server_error.py` 只包住 `self.app`，沒有讀 `receive`。 |

#### 2. ADR-0042 草案

**(a) 「E-2（:314）不消除」：判定成立。**
- E-2 的原文在 `2026-11-04-N182解讀點2與3裁示-tech-architect.md` E-2 第 2 點。觸發條件是：本請求 `read_in_flight` 之後、commit 之前，另一個請求的結算讓同一批的另一筆買進成交。
- N-198 讓另一個請求的 claim 與動帳一起 commit，但不改本請求的讀取時點。整筆結算在窗口內 commit，正是 E-2 的形狀。
- 前提「同一批有不只一筆待結算買進」的來源有：R-6′ 的兩種變體、ADR-0035 V4 的跨日重發、N-172a 之前的重複。N-198 只拿掉第一項。
- 所以我在 [風控-1104] 第 11 點接受的殘留繼續有效，條件 (a)～(d) 照舊；修法方向仍是 (iv)。
- **required R5**：coordinator 在追蹤清單 :314 註明「E-2 不因 N-198（F2）合入而結案，仍歸 N-169，N-169 落地時回審」，避免有人把 F2 結案誤讀成 E-2 結案。
- **suggested S5**：Consequences「E-2 的觸發頻率會下降」沒有量測依據，改成事實陳述：「E-2 的前提少了 R-6′ 這一個來源；實際頻率未量測」。

**(b) ADR-0041:114 補註：草稿不採用，改用以下定稿（required R3）。**

改的理由：
- 原稿的「N-198 之前寫入的列」分不清是合入前還是部署前；
- 原稿只講當機，漏了 `database is locked` 這類失敗；
- 原稿沒有交代我在 R-6′ 對本點的但書，對舊資料仍然有效。

定稿全文（N-198 以 merge commit 合入 product 之後才落檔，時點比照 R-6′ 的已修正註記；CEO 通知維持到 N-198 部署為止）：

「補註：本點由 ADR-0042（N-198）修正：claim 與動帳在同一交易內 commit，claim 之後任一步失敗或行程終止時，claim 與動帳都不會留下。本點，以及 R-6′ 對本點「判定為未動帳（多報方向）」適用範圍的說明，仍適用於 N-198 部署之前已被 claim 的列；這些列以 N-199 偵測回溯工具事後檢查。」

**(c) 和 N-177b 的先後：接受「N-177a 必須先合入、N-177b 預設先合入」，附條件（required R4）。**
- 若改走 N-198 先合入的路線，TA 的補充（Q-g、N177b-C6／C9 改為從 `claim_and_settle` 的回傳取值）必須在 **N-198 的 PR 開出之前**送到我這裡，不能事後補。同一份補充也要一併修改 N198-C7，因為現行的 `<M_2>` 寫死是 N-177b。
- N-177b 延誤，不構成 N-198 延到第三包之後的理由。期限照舊：延期需要 CEO 書面同意，我會書面保留不同意見。

**(d) 草案內部的矛盾（required R1）。**
- N198-T9 是 BLOCKING，要對 T1～T3 產生的 DB 執行 N-199 的工具；但「先後與相依」第 4 點寫「N-199：不相依」。
- 改法：明列「N-199 必須在 N-198 合入之前已經在 product 上」。N-199 的期限是 R2，本來就比第三包早，所以不會延到 N-198。
- N198-C7 的 ancestry 驗證也要加上 N-199 的 merge commit。

**(e) 缺少一項揭露（required R2）。**
- 在 Decision 5 的失敗語意下，一列若是**確定性**失敗，該列每次都會回滾、留在 pending，每一次 `/today` 都依 C-11 失敗。確定性失敗例如 Decision 2 的 `ClaimInvariantError`、資料格式錯誤，重試也不會成功。
- 結果是今日頁面持續無法使用，直到修好為止。這段期間，S/P 系列的賣出指令也不會出現。
- N-198 之前：claim 已經留下，同樣的錯誤只會失敗一次，之後就被靜默吞掉（帳冊少記）。所以這是行為變更：從「隱藏的帳冊落差」變成「看得見、但會持續的停擺」。
- 方向我接受，因為不再隱藏。但 Consequences 必須照實寫出：「確定性失敗會讓每一次今日頁面讀取都失敗，期間不會顯示任何指令，包括停損停利」。不得只寫「那一列下次重試」。
- 這一項只改 ADR 文字，不要求改程式。

其餘部分我讀過，沒有意見：
- Options 的否決理由；
- Decision 2 不違反「批次是否 planned 的 SQL 只在 `BATCH_LEFT_PLANNED_SQL`」；
- C1～C8、T1～T9；
- Context 第 4 點的並發路徑分析，回答了我上一輪列為未查證的那一項。

#### 3. N-199 spec

**(a) N199-C 列為 required（qa 列為 BLOCKING）。** 理由：
- 失敗變體之後，若第二張 R1 成交而且結算成功，批次會變成 open。這時 A（planned／skipped）與 B（pending）都抓不到。
- 但這正是 N-197 (b) 要找的、方向不保守而且被隱藏的後果：使用者兩張都下單時，券商持股比帳冊多一批。
- 我讀碼確認，N-177a 之前的 buy 是先 `set_cash`、再 `save_batch`（store.py:1635、:1652），L12 的事實陳述正確。所以 C 也涵蓋了「現金可能扣了兩次」的情況。
- C 還一併涵蓋 :382。

**(b) 第 5 節：方向正確，附兩項 required。**
- **R7**：刪掉「或由 coordinator 以 repo 以外的方式轉給 CEO」。
  - coordinator 是 agent，它經手的任何內容都會進到對話紀錄，和同節「不得貼進任何對話紀錄」直接衝突。
  - 改為：逐檔明細只由 CEO 在本機讀；任何 agent 都不得讀 `report.md`、`report.json`。
  - 回報進 `work/` 的內容只能有三個計數、腳本與 DB 的雜湊、執行時間，照原文。
- **R8**：N199-B 有命中時，也要請 CEO 核對券商紀錄。
  - 並發變體的特徵是：第二張指令已經顯示給使用者，帳冊雖然擋下了，使用者可能已經在券商下單（R-6′）。只核對 A、C 不夠。
  - 改為：「N199-A、N199-C 的列，請 CEO 以券商對帳單核對該批的實際持股；N199-B 的列，請 CEO 核對是否曾依該待結算列（`pending.id` 對應的指令）在券商下單。這是事實核對的請求，不是處置建議；處置另行裁示。」
- 其餘照准：
  - 命中不改變 exit code；
  - L12～L14 只陳述事實；
  - S8 涵蓋新增的固定文字；
  - 「N-198 部署之後再跑一次」。

#### 4. `REBALANCE_SUPERSEDED` 逐字定稿：採用候選 A

「季末 REBALANCE 未執行：執行期間 TOTAL_DEPLOY 已被另一項操作改寫，本次沒有寫入任何值，TOTAL_DEPLOY 與現金都沒有被本次變更。目前的 TOTAL_DEPLOY 為 {total_deploy}，寫入時間 {set_at}。若要以目前的資金與持股重算，請再執行一次 REBALANCE。」

- 我逐條對照 3(c)，都符合。
- 代入修訂六 2.3 的格式後，讀起來是「寫入時間 2026-11-07 11:04:05 台北時間。」，時區只出現一次，和 C12 相容。creative-lead 的例子多了「（UTC+8）」，這不影響字面本身。
- 不採 B：「請再執行一次」已經表示要由使用者手動執行；多一句行為陳述，日後要多維護一處。
- 不採 C：「不是本次重算的結果」會引來「那是依什麼算的」的追問，而 `found` 沒有來源欄位可以回答。「本次沒有寫入任何值」已經足以避免使用者把它當成剛算出來的數字。
- 佔位只有 `{total_deploy}`（.2f）與 `{set_at}`，沒有其他花括號。
- qa 依 C10 逐字比對 wording.py 的常數與本定稿。比對前允許的空白正規化，只限 Python 字串分行串接造成的差異。
- C10 解除，條件是：字面落進 wording.py 時和本定稿逐字一致。

#### 5. N-197 (b) CEO 通知：要補，逐字全文如下

**判斷：**
- 「全部出清」按鈕在每一個畫面狀態都會出現，包括讀取中（`ExitTriggerButton.tsx:12-15`）。
- 出清的 `onSettled` 不論成功或失敗都會執行（queries.ts:473-475、:522-525）。
- 所以 CEO 照通知的建議只開一個分頁、讀取中不重新整理，仍然可能因為在讀取中出清而造成並發。避免方式列得不完整，就會誤導，這和我上一輪更正補充句是同一個理由。
- 但出清是緊急動作。為了一個低頻率的重複指令，讓使用者延後出清，這個交換方向錯誤。所以補充必須明說：不要因此延後出清，改用事後核對。
- 前端沒有呼叫 `/settle` 的地方（grep 零筆），但 API 可以直接呼叫，所以一併列入。
- 「資金確認的 `onSuccess`」不列入：舊請求走 unauthored 路徑，不會結算（TA Context 第 4 點），和 F2 無關。

**補充全文（新送，原通知不撤回；送出後要確認 CEO 收到；最遲在下一個排程日使用今日頁面之前送達）：**

「補充（風控，2026-11-07，N-197 (b) 內部通知）：前一則通知第一種情況所舉的例子不完整。在今日頁面讀取中送出「全部出清」時，不論出清成功或失敗，排程台頁面（仍開著時）都會再送出一次今日頁面的讀取，原本那一次仍會在後端跑完，兩次同時執行；直接呼叫 `POST /api/playbook/settle` 時，若同時有今日頁面的讀取在執行，也是同樣情況。需要出清時，請不要因為這一點延後或放棄出清；出清之後，前一則通知的核對方式照樣適用：若今日頁面出現你已在券商買進過的同一檔、同一批（「第 N 批」）的買進指令，請不要依該指令下單，先以券商回報核對持股，並告知 coordinator。本補充與前一則通知一樣，在 claim 與動帳合併的修正（F2）上線前有效。」

- 授權範圍：只准刪字，不准改寫。若事實和本文不符，例如出清失敗時不會觸發 `onSettled`，就回我。

#### 6. 修訂五（N-177a 停止點）：我同意不必送我審

- 我讀過全文。它不改以下任何一項：
  - 面向使用者的字面或揭露；
  - 風險上限；
  - C3、C17；
  - 經 [風控-0040] 審過的 QB-7 白名單；
  - ADR-0041。
- T21 加現金斷言、`_update_batch` 的 status 守衛、assert 改成 `ValueError`，都是收緊。
- T18／QB-3 的放寬只限於 N-177a 之前就存在的具名位置，而且這些位置不是條件字面，屬於 TA 自己的測試條款。
- 條件（照修訂五原文）：若改選 (b)，或 merge N-190 之後出現具名清單以外的 `"S2"`，要回 TA；凡是動到 QB-7 白名單或 C3 的，都要回我。

#### suggested（不擋）
- **S1**：1.6 表格 regex 裡的 `\|` 是 markdown 的跳脫。spec 要註明實際 regex 是 `|`，避免 qa 照抄之後變成比對字面的 `\|`。
- **S2**：1.5 第 4 點之外，qa 另外以 PR 頁面的 head SHA 對照紀錄裡的 `<head>`。這一步是讀頁面，不需要 Bash。`git diff --stat` 為空只代表 tree 相同，不代表是同一個 commit。
- **S3**：`RebalanceResponse` 的 `previous_total_deploy` 加上 `Field(description=...)`。這要把 C1 擴大到 `app/api/playbook.py`，由 TA 決定。我不列為 required，因為 `message` 已經以「目前的 TOTAL_DEPLOY 為…」說明。
- **S4**：`set_capital(at=...)` 接受沒有時區的 datetime。app 內目前沒有傳入 `at` 的呼叫點，但它是 C11 不變式的潛在破口。建議日後另開單加守衛，不在 N-197a 的範圍內。
- **S5**：見第 2(a) 點。

### 審查結論、逐條意見、否決理由（輸出契約）

**審查結論：** CONDITIONAL APPROVE。

**逐條意見（required，qa 列為 BLOCKING；文字項由 TA／tech-writer 修改後回我確認）：**
- [ADR-0042 先後與相依第 4 點／N198-T9／C7] **R1**：N-199 要在 N-198 合入之前上 product，並納入 C7 的 ancestry 驗證。
- [ADR-0042 Consequences] **R2**：照實揭露「確定性失敗會讓今日頁面每一次都失敗，期間不會顯示任何指令，包括停損停利」。
- [ADR-0041:114] **R3**：補註改用第 2(b) 點的定稿，N-198 合入之後才落檔。
- [ADR-0042 先後與相依第 2 點] **R4**：N-198 先合入的路線，補充要在 PR 開出之前送到我這裡，並一併修改 C7；N-177b 延誤不構成 N-198 延期的理由。
- [追蹤清單 :314] **R5**：註明 E-2 不因 N-198 結案。
- [N-199] **R6**：N199-C 列為 required。
- [N-199 第 5 節] **R7**：刪掉 coordinator 轉交明細的路徑；任何 agent 都不得讀報告檔。
- [N-199 第 5 節] **R8**：N199-B 有命中時，也要請 CEO 核對券商紀錄（文字見第 3(b) 點）。
- [N-197a C10] `REBALANCE_SUPERSEDED` 依第 4 點逐字落進 wording.py。
- [CEO 通知] 第 5 點的補充要新送，並確認 CEO 收到。

**suggested：** S1～S5。

**否決理由：** 本輪沒有新的否決。

### 其他部門
- tech-architect：產出了本輪審查的修訂六、ADR-0042、N-199，以及前提 (1) 的確認。
- creative-lead：提出 `REBALANCE_SUPERSEDED` 的候選，採用 A。
- coordinator：已送出 N-197 (b) 原通知，前提 (2) 已以 grep 確認。
- 其餘部門：本輪沒有參與。

## 三、驗證

**讀過的文件：**
- `/home/user/AICompany/work/reviews/2026-11-07-N177規格修訂六與ADR0042草案與N199spec-tech-architect.md`，全文。
- `/home/user/AICompany/work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md`，我上一輪的原文，作為比對基準。
- `/home/user/AICompany/work/reviews/2026-11-07-REBALANCE_SUPERSEDED候選-creative-lead.md`，全文。
- `/home/user/AICompany/work/reviews/2026-11-07-N177a停止點裁示-tech-architect.md`，全文。
- `/home/user/AICompany/work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md` 的 E-2 節。
- `/home/user/AICompany/work/reviews/2026-11-04-ADR0039v2回審與N182字面-風控.md` 第 11 點。
- `/home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md` 的 :312-315、:380-383。
- `/home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md` 的 :114。

**讀過的程式（只讀，未執行）：**
- `apps/stock-desk/backend/app/playbook/store.py`：
  - `_write_state`（:690-700）；
  - `_set_state`、`portfolio_state`、`set_capital`（:1013-1055）；
  - `batch_blocking_claim`、`settle`（:1557-1653）；
  - `EMERGENCY_RULE_ID`、`UNKEYED_RULE_IDS` 的行號。
- `apps/stock-desk/backend/app/playbook/service.py`：`set_capital` 的兩個呼叫點（grep）。
- `apps/stock-desk/backend/app/playbook/wording.py`：`REBALANCE_*`（:1045-1060）。
- `apps/stock-desk/backend/app/api/server_error.py`：全文。
- `apps/stock-desk/frontend/app/lib/queries.ts`：:430-539。
- `apps/stock-desk/frontend/app/playbook/ExitTriggerButton.tsx`：全文。
- frontend 內 grep `/settle`：零筆。

**未查證：**
- 「全部出清」成功之後是 emergency_frozen，新的那一次請求不會出 R1（engine.py:11、:397）。我沒有逐步推演舊請求在這個交錯下的所有路徑，所以補充寫的是「可能同時執行」，不宣稱一定會重複出單。
- 偵測工具在 product 上的實際狀態。TA 指出主 checkout 沒有這個檔，請 coordinator 確認。
- N-177a／N-177b／N-195／N-196／N-197a／N-198／N-199 都還沒實作，本輪依規格審查。

我沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改或新增任何檔案，也沒有執行任何指令。

**CEO 要親自確認的事：**
- 收到第 5 點的通知補充。
- ADR-0042 的核可。

## 四、下一步

1. **coordinator：**
   - 把本檔逐字轉存到 `work/reviews/`。
   - 把第 5 點的補充送給 CEO，並確認收到。
   - 追蹤清單 :314 依 R5 註記。
   - 確認偵測工具在 product 上的狀態。
2. **tech-architect：**
   - ADR-0042 依 R1、R2、R4 修改，回我確認；
   - N-199 spec 依 R6～R8 修改，回我確認；
   - suggested S1～S5 自行評估。
3. **tech-writer：**
   - ADR-0042 在 R1、R2、R4 補完、我確認之後落檔，狀態維持 proposed；
   - ADR-0041:114 的補註（R3），以及 R-6′ 的已修正註記，等 N-198 合入之後才落檔。
4. **dev-lead：**
   - N-197a 的 `REBALANCE_SUPERSEDED` 依第 4 點逐字落進 wording.py，C10 解除。N-197a 仍然要等 N-196 合入之後才開工。
   - N-198 等 N-177a、N-199（以及預設的 N-177b）都合入之後才開工。
5. **data-engineer：** 依修改後的 N-199 spec 實作；N199-C 是 required。
6. **qa-reviewer：** 本檔的 required 項目列為 BLOCKING；C10 依第 4 點逐字比對。
7. **CEO：** 收下通知補充；核可 ADR-0042。延期條款照舊，延期需要 CEO 書面同意。

### 書面紀錄
- 本人核可修訂六第 1～13 項。
- 本人核可 ADR-0042 的 P1 決策，附 R1～R4。
- 本人裁示 N199-C 列為 required，第 5 節附 R7、R8。
- 本人定稿 `REBALANCE_SUPERSEDED`，採用候選 A。
- 本人裁示 N-197 (b) 通知要補送一則補充：補上出清與 `/settle` 兩條路徑，並明示不得因此延後出清。
- 本人同意修訂五不必送風控審。

**相關檔案：**
- /home/user/AICompany/work/reviews/2026-11-07-N177規格修訂六與ADR0042草案與N199spec-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-07-REBALANCE_SUPERSEDED候選-creative-lead.md
- /home/user/AICompany/work/reviews/2026-11-07-N177a停止點裁示-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-07-N177修訂四比對與N197裁示-風控.md
- /home/user/AICompany/work/reviews/2026-11-04-N182解讀點2與3裁示-tech-architect.md
- /home/user/AICompany/docs/adr/0041-stock-desk-排程台S2成交動帳-成交移動稽核表與結算動帳的鎖內讀改寫.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/wording.py
- /home/user/AICompany/apps/stock-desk/backend/app/api/server_error.py
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/queries.ts
- /home/user/AICompany/apps/stock-desk/frontend/app/playbook/ExitTriggerButton.tsx

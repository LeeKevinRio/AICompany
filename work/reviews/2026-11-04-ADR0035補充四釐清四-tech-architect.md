# ADR-0035 補充四釐清四（N-171-A commit 順序、NB-6 原子單位、固定項註解、merge N-182）

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

三點都裁定了，不需要 CEO 裁示。

1. **commit 順序：可以接受，不需要改。** 釐清二要求機制 commit 排在前面，是為了讓機制在「還沒有任何切面項目被填入」的程式狀態上建立和驗收。`0f02cf3` 和 `909899b` 都不會改變 golden 情境的任何回應，所以不算 E-10 所指的 feat commit。接受附條件，條件是 qa 用 `git diff` 可以核對的 (a)～(e)。另外，E-10 第 3 點的本文其實沒有寫 commit 順序。順序要求來自第 2 點「機制先合進 product」的意旨，以及轉知時的措辭。
2. **NB-6 原子性：不要求合併成一個 commit。** Decision 13 要求放在同一個 commit 的，是 NB-6 第 2 段的四件東西：後端常數、前端鏡射、逐字守門測試、字面絆線測試。區塊本體不在這四件裡。`460413d` 上前後端都還是第一版，彼此一致。
   - 真正的風險在另一個方向。第二版的字面指向區塊（含 `PENDING_EXIT_BLOCK_TITLE`），但從 `508a976` 到前端元件完成之前，區塊根本不會渲染。
   - 所以約束放在 PR 層級：元件必須進同一條分支、同一個 PR；在 S-A～S-D 與風控書面終核完成前，不得合進 product，也不得部署；以 merge commit 合併，不 squash。
3. **固定項上的舊註解：改註解不算違反 S-3。** S-3 管的是名稱、型別、預設值、簽名和呼叫次數。註解則必須和 accepted ADR 一致。
   - 由 N-171-A 的 PR 改，用一個只改註解的 `docs:` commit。範圍只有 `models.py` 和 `types.ts` 中 `pending_exit_directives` 的擁有者行，要在交給 frontend-engineer 之前完成。
   - 交件的說法有兩處不準：
     - `api/playbook.py` 的擁有者行只寫了 "Owner N-171 (ADR-0039 Decision 1)."，沒有「仍涵蓋」，不必改。
     - `types.ts` 的 "No view renders them yet." 是三個清單共用的句子。對 `pending_exit_directives` 來說這句永遠成立（C22），所以 N-171-A 不改它；等 N-168 的畫面真的渲染它的清單時，由 N-168 改。
   - 這是依 product 工作樹讀到的內容；dev-lead 說這幾行在分支上沒改，所以應該相同。

**merge N-182 的風險。** 我預見三個，都已寫進釐清四 E-16：
- `store.py` 裡 N-171 擁有的 `PendingExitRead`、N-182 改過的 `EntryBeforeExitRead`、固定的 `InFlightRead` 交錯排列，衝突區塊可能跨過固定項。
- merge 之後 `_read_entry_before_exit` 會真的執行 SELECT，SEAM-T4 可能受影響。
- 兩邊的字面整檔掃描測試會互相掃到對方新增的常數。

## 二、各部門回報

- **tech-architect（本人，唯讀）**
  - 讀了以下文件：交件全文、ADR-0039（v2 加補充一）、補充四全文（含釐清一至三）、`回報格式.md`。
  - 讀了 product 工作樹的程式（HEAD 是 `product/stock-desk`，已含 N-182）：
    - `models.py:582-592`
    - `api/playbook.py:271-279`
    - `types.ts:1886-1895`
    - `store.py:240-345` 與 `:1266-1309`
    - `service.py:417-606`、`:642-662`、`:735-846`
    - 對 `read_in_flight` 呼叫點、`in_flight` 用法、`N-182` 標記的 grep 結果
    - golden 的情境與回應清單：9 個回應裡沒有 `POST /settle`，所以 C17′ 不在 golden 情境內。
  - 讀碼確認 N-182 沒有改 `_settle_pending` 的 `loaded`，也沒有改 `_read_exit_state`，所以不影響 N-171 用結算序列做分類的前提。
  - 產出下方的「釐清四」，可以直接附到補充四檔末。
- **dev-lead**：要補兩件事：釐清四 E-13 第 3 點 (e) 的逐 commit 測試紀錄，以及 E-15 的註解 commit。
- **qa-reviewer**：新增 QB-14，見釐清四 E-17。
- **risk-compliance-officer**：解讀點 3 和 6 由風控確認，不在本次裁示範圍。
  - 架構面補一句意見：ADR-0039 補充一 S-7 第 2 點「第一版在 grep 中為 0」的本意是「不得有任何常數或鏡射單獨以第一版作為第 2 段」。dev-lead 的替代口徑符合這個本意，最終以風控為準。
- **其他部門**（product-manager、frontend-engineer、qa-e2e、devops-sre、tech-writer 等）：本次未參與（純裁示）。

## 三、驗證

- **沒驗證到的事**
  - 我沒有 Bash，無法 checkout 或看 N-171-A 分支的逐 commit diff。所以各 commit 只改了哪些檔案、`508a976` 有沒有包含字面絆線測試，都是轉述交件內容，要由 qa-reviewer 用 `git diff` 依釐清四逐項核對。
  - 依自訂的唯讀規則，qa 只能跑 `git diff` 和 `codex`，不能 checkout 舊 commit 跑測試。所以逐 commit 的測試由 dev-lead 執行，qa 只核對紀錄。
- **CEO 不需要親自驗證。** 需要 CEO 知悉的一點是：N-171-A 分支在前端元件完成前不得合併或部署。
- 沒有讀 `.env`，沒有碰 `data/*.db`，沒有改任何檔案。

## 四、下一步

1. **coordinator**：把下面的「釐清四」附到 `/home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 檔末，並把 E-17（QB-14）轉給 qa-reviewer。
2. **dev-lead**：
   - 在 `feat/stock-desk-pending-exit-block` 上，追加 E-15 的 `docs:` 註解 commit；
   - 依 E-16 完成 merge N-182 product，並在 merge 後的 head 上跑完整 CI；
   - 補交 E-13 第 3 點 (e) 的測試紀錄；
   - 若 N-168 要先合併，依 E-13 第 5 點把機制 commit cherry-pick 出去，單獨開 PR。
3. **frontend-engineer**：等註解 commit 落地後才開工；元件要 commit 在同一條分支（E-14 第 2 點 (c)）。

---

```
（coordinator 2026-11-04 附加：釐清四原文，tech-architect 回應 `work/reviews/2026-11-04-N171A後端交件-dev-lead.md` 解讀點 1、2、7）

## 釐清四（tech-architect 2026-11-04，N-171-A 後端交件的 commit 順序、NB-6 原子單位、固定項註解與 merge N-182）

- 性質：釐清 S-3、S-6 的 R-5、S-7 的 QB-6，以及釐清二 E-10 第 2、3 點；E-14 另外釐清 ADR-0039 v2 Decision 13 的原子單位。不改任何固定項，不改 S-6 的判準本身，不改 golden。
- 依據：`work/reviews/2026-11-04-N171A後端交件-dev-lead.md` 解讀點 1、2、7；ADR-0039 v2 Decision 1、11、13 與補充一 S-1 第 4 點、S-7 第 2 點；釐清二 E-6、E-9、E-10、E-11。
- 程式位置：2026-11-04 工作樹 `product/stock-desk`（已含 N-182）；N-171-A 分支的 commit 依交件所列，由 qa-reviewer 以 `git diff` 核對。

### E-13 機制 commit 的位置（E-10 第 2、3 點）
1. E-10 要求機制先合，或以獨立 commit 先行建立，目的是：機制要在擁有者尚未填入任何切面期項目、也尚未新增任何回應鍵的程式狀態上建立和驗收。這樣「登記為空時與改寫前等價」與變異測試才有意義，機制也不會被寫成遷就本案的填入值。
2. 因此，「N-171-A 的 feat commit」指會改變 golden 情境中任何回應的 commit，也就是：填入 2.2(a) 的清單、填入 `InFlightRead` 的任一部分、新增回應鍵，或改變既有欄位值。只改動 golden 情境以外路徑的 commit，或行為零差異的 commit，不在此列。
3. N-171-A 分支的順序 `0f02cf3`（refactor）→ `909899b`（C17′）→ `01e99cb`（機制）→ `460413d`（區塊），依第 2 點可以接受。以下條件由 qa-reviewer 列為 BLOCKING：
 - (a) `git diff 0f02cf3^ 909899b -- apps/stock-desk/backend/tests/test_playbook_today_seam.py apps/stock-desk/backend/tests/seam_helpers.py apps/stock-desk/backend/tests/golden/` 為空。
 - (b) `git diff --stat 909899b 01e99cb` 只列出 E-10 第 1 點的三個路徑；`app/` 與 golden 零 diff。
 - (c) `approved/n171a.json` 首次出現在 `460413d`。
 - (d) `909899b` 沒有改 `POST /settle` 既有測試的斷言（SEAM-T6、E-9 第 2 點末項）。golden 的 9 個回應中沒有 `POST /settle`，C17′ 不在 golden 情境內。
 - (e) dev-lead 在 `0f02cf3`、`909899b`、`01e99cb` 上各跑一次 SEAM-T1～T7，結果附在 PR 說明；qa-reviewer 只核對紀錄與 diff。
4. 不得以 rebase、互動式改寫或 force push 調整已推送的順序。
5. 機制在 N-171-A 的 PR 內，N-168 的合併因此依賴 N-171-A 先合。若 N-168 先通過自己的閘門：
 - dev-lead 從 `origin/product/stock-desk` 開新分支，`git cherry-pick 01e99cb`，以單獨的 test-only PR 先合，等同回到 E-10 第 2 點的原路徑；N-171-A 之後再 merge product。
 - cherry-pick 到新分支不是 rebase，也不改動任何已推送的分支。
 - N-168 不得自帶一份機制。

### E-14 NB-6 的原子單位（ADR-0039 Decision 13）
1. Decision 13 要求放在同一個 commit 的，是 NB-6 第 2 段的四件東西：後端常數、前端鏡射、逐字守門測試、字面絆線測試。目的是在任何一個 commit 上，前後端的第 2 段都不會是不同版本。區塊本體不在這個單位內；區塊與 NB-6 的關係，由「在 N-171 的同一個 PR 內」約束。
2. 區塊 `460413d` 與 NB-6 `508a976` 分成兩個相鄰的 commit，可以接受，不要求合併。以下條件列為 BLOCKING：
 - (a) `508a976` 同時含有：`wording.py` 的 `EXIT_RESULT_UNCONFIRMED_BADGE`、`playbookView.ts` 的 `EXIT_FAILURE_WORDING.body[1]`、後端守門測試、`exitWordingMirror.test.ts`、字面絆線測試。
 - (b) `git diff 0f02cf3^ 460413d` 沒有動到上列常數與鏡射。也就是說，`460413d` 上前後端都是第一版，彼此一致。
 - (c) 第二版指向區塊。從 `508a976` 起到前端元件 commit 之前，分支上的字面指向一個尚未渲染的區塊。因此：
   - 前端區塊元件必須 commit 在同一條分支，進同一個 PR（Decision 11）；
   - 在元件完成、S-A～S-D 完成、風控書面終核完成之前，分支不得合進 product，也不得部署。
 - (d) PR 以 merge commit 合進 product。不 squash，因為 squash 會抹掉 E-13 要求的獨立機制 commit；也不 cherry-pick 個別 commit 進 product 或任何部署分支。
3. 不採的做法：若要讓每個 commit 都同時含區塊與第二版，在不 rebase、不 force push 的前提下，唯一的做法是從 `01e99cb` 另開新分支，以 `git cherry-pick --no-commit 460413d 508a976` 合成一個 commit，再重做 merge 與整個審查，舊分支棄用。成本高，安全上沒有增益，不採。

### E-15 固定項上的註解（S-3、QB-6、2.2(d)）
1. S-3 的固定項約束的是契約：名稱、型別、預設值、簽名、呼叫次數，以及 2.2(d) 要求的「註解寫明擁有者與 ADR 條號」。描述欄位內容的註解文字不屬於契約，但必須與 accepted ADR 一致。QB-6「固定項零 diff」依以下口徑判定：
 - 在 `git diff 5c2d3e1 <head>` 中，落在固定項宣告上的每一個 `-`／`+` 行，去掉前導空白後都以 `#`（Python）或 `//`（TypeScript）開頭；
 - 名稱、型別、預設值、簽名零 diff；
 - 擁有者與 ADR 條號仍然寫在註解裡。
2. 誰可以改：
 - 固定欄位的擁有者行，也就是緊接在該欄位宣告上方、寫 `Owner ...` 的那幾行：由該欄位的擁有者修改，只能改成 accepted ADR 已寫明的語意，不得新增語意。
 - 三個清單共用的說明段，也就是第一個 `Owner` 行之前的那段：由讓它變得不正確的那個 PR 修改。
 - 他方欄位的擁有者行：一律不改。
3. 本次裁定：
 - (a) `models.py` 與 `types.ts` 中，`pending_exit_directives` 的擁有者行寫的是「unsettled EMERGENCY sells that still cover」。這和 ADR-0039 v2 Decision 1「三類都含」不符，是 v1 的殘留，**要改**。
   - 在 N-171-A 的 PR 內，以一個只改註解的 `docs:` commit 落地，並在交給 frontend-engineer 之前完成。
   - 改後要寫明：三類都含；只限 open 批次；排序；這是原始資料，不得用來渲染文字（ADR-0039 補充一 S-1 第 4 點、C22）。
 - (b) `api/playbook.py` 的擁有者行只寫「Owner N-171 (ADR-0039 Decision 1).」，沒有不符的描述，不改。
 - (c) `types.ts` 共用說明段的 "No view renders them yet." 描述的是三個清單。對 `pending_exit_directives` 來說這句永遠成立，所以 N-171-A 不改，改由 (a) 的擁有者行寫明「不渲染」是永久的。日後 N-168 的 PR 若讓畫面渲染它的任一清單，由 N-168 改這一句。
4. 建議文字（英文；可依行寬換行，語意不得增減；`types.ts` 用 `//:`，內容相同）：
       #: Owner N-171 (ADR-0039 Decision 1): every unsettled EMERGENCY sell on an open
       #: batch -- covering, stale and unclassified alike -- by symbol, batch_no,
       #: execution_date, id. Raw data: no view renders text from it (補充一 S-1 第 4 點).
5. 合併衝突：各擁有者改各自的擁有者行，相鄰行在 merge 時可能產生文字衝突。
 - 不構成 S-6 的 R-5：衝突區塊裡只有註解行有差異；或固定項的程式行兩邊都沒改，只是落在衝突區塊之內。解法是：固定項的程式行與 `5c2d3e1` 逐位元相同，各擁有者行取自各自的分支，並在 PR 說明列出。
 - 構成 R-5：任一邊改到了固定項的程式行。

### E-16 N-171-A merge 含 N-182 的 product（S-5 第 3 點的具體檢查）
1. 固定項
 - N-182 在 `app/` 的改動位置：
   - `store.py`：`BATCH_LEFT_PLANNED_SQL`、`EntryBeforeExitRead.blocked`、`_read_entry_before_exit`、claim 路徑；
   - `service.py`：`g1_blocked_entries`、`same_day_warnings`、`evaluate_today` 傳入 `blocked`；
   - `wording.py`：W-B6b。
   N-182 沒有碰 `models.py`、`api/playbook.py`、`types.ts` 的固定宣告。
 - `store.py` 中，`PendingExitRead`（N-171）、`EntryBeforeExitRead`（N-168／N-182）、`InFlightRead`（固定）、`_read_pending_exits`、`_read_entry_before_exit` 交錯排列，衝突區塊可能跨過 `InFlightRead`。依 E-15 第 5 點處理：`InFlightRead` 與 `read_in_flight` 必須與 `5c2d3e1` 逐位元相同。
2. 單一讀取點
 - 兩條路徑各只有一處 `self._store.read_in_flight()`。
 - N-171 的區塊只讀 `in_flight.exits`，N-182 的 `blocked` 只讀 `in_flight.entries`，兩者用的是同一個 `in_flight`。
 - SEAM-T3 綠燈。
3. SEAM-T4
 - merge 之後，`_read_entry_before_exit` 會實際執行 SELECT。對沒有登記在 `filled.in_flight` 的 `entries`，T4 仍斷言為預設值。
 - 若轉紅，視為 merge 引入的回歸。不得把 `entries` 加進 `n171a.json` 的 `filled`：E-6 第 1 點規定只能改自己的登記檔，而 `entries` 也不屬於 N-171。停住，送 tech-architect。
4. SEAM-T2：登記檔只有 `n171a.json`（`deltas: []`）時，必須綠燈。轉紅時依 E-9 第 4 點末項處理，不得以登記差異解決。
5. 字面掃描
 - merge 之後，N-171-A 的整檔掃描（`test_c6_*`、`test_i_*`、「應」的豁免）與 N-182 的守門測試，會互相掃到對方新增的常數。
 - 任一條轉紅時，停住：字面問題送風控，掃描範圍問題送 tech-architect。
 - 不得改對方的字面，不得改對方測試的斷言（`tests/test_playbook_pending_entry_blocked.py` 受 E-1 第 3 點保護），也不得自行收窄掃描範圍或放寬白名單。
6. E-11／QB-13
 - `_read_exit_state` 的三個查詢，與 `5c2d3e1` 零 diff；
 - `_read_pending_exits` 不讀買單，也不引用 `BATCH_LEFT_PLANNED_SQL`；
 - QB-7：`app/` 內的 `pending_directives(` 只有釐清三白名單上的兩處；`settle_on_request` 不直接呼叫它。
7. merge 之後的 head
 - 重跑 S-5 第 3 點的全部 job；
 - qa-reviewer（含 Codex）重審 merge commit 的衝突處理，以及 S-7、QB-12、QB-13、QB-14。

### E-17 S-7 增列檢查項
- QB-14（N-171-A 的 PR）：
 - E-13 第 3 點 (a)～(e)；
 - E-14 第 2 點 (a)～(d)；
 - E-15 第 1、3、5 點；
 - E-16 全部。
```

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-04-N171A後端交件-dev-lead.md
- /home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md
- /home/user/AICompany/docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/models.py（:585）
- /home/user/AICompany/apps/stock-desk/frontend/app/lib/types.ts（:1889-1890）
- /home/user/AICompany/apps/stock-desk/backend/app/api/playbook.py（:274）
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/store.py（:298-344、:1267-1309）
- /home/user/AICompany/apps/stock-desk/backend/app/playbook/service.py（:1208、:1287、:1358-1399）

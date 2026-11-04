# N-171-A 結算句 golden 差異核准（N171A-D1～D3）與補充四釐清五

- 審查者：tech-architect
- 日期：2026-11-04
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

**三點都裁定了，不需要 CEO 裁示。**

1. **擁有者檔：採 (a)，登記在 `approved/n171a.json`。** 這不算違反 E-9 第 2 點，而是走 E-9 第 2 點本來就寫好的路徑：「出現任何差異，依 E-7 第 3 點停住」。三筆的 id 為 `N171A-D1`～`D3`，全部是 `replace`，路徑都是 `["settlement","warnings",0]`。
   - (b) 否決。理由：機制 commit `01e99cb` 目前還在 N-171-A 的 PR 裡。若另開先行 PR，就得依序走三個 PR：先 cherry-pick 出機制 PR（E-13 第 5 點），再合字面 PR，最後 N-171-A 再 merge 一次 product 並重跑 E-16。T2 守的仍是同一組差異，安全上沒有任何增益。
2. **書面核准：本報告第二段 B 即為核准。** 請 coordinator 逐字轉存到 `work/reviews/2026-11-04-N171A結算句golden差異核准-tech-architect.md`，`approval` 欄就寫這個路徑；檔名若有更動，以實際路徑為準。
   - 這是**附條件核准**：`after` 必須逐字等於風控核可的定稿，而且是**單一靜態字串、不含佔位符**。
   - 依 E-7 第 3 點，風控的逐字核可檔必須寫明「同時確認 golden 上 D1～D3 三處既有揭露的改變」，才算補齊風控那一半的確認。
3. **需要釐清五**，全文在第二段 C，可以直接貼到補充四檔末。重點有三：
   - 新字面只能是靜態常數，不得改動 `_settle_pending`；
   - 測試上「字面替換的連動」的處理規則（E-20）；
   - 新增 QB-15。

**`POST /settle` 的測試：既有斷言一條都不用改。**
- SEAM-T6 所指的既有測試在 `test_api_playbook.py:360-395`，都沒有斷言 `warnings`。
- N-171-A 新增的 `test_playbook_settle_on_request.py:111`、`:214` 用識別名引用常數，替換值之後自動跟著變，不算改斷言。
- 目前寫死這句字面的只有 golden 那 3 處。

## 二、各部門回報

### tech-architect（本人，唯讀）

#### A. 方案比較

| 方案 | 優點 | 缺點 | 風險 | 結論 |
|---|---|---|---|---|
| (a) 登記在 `n171a.json`，經 E-7 第 3 點逐筆核准 | 這次改寫是 N-171 的合併條件（不改就 VETO），擁有權因果清楚；機制已在同一個 PR；風控允許同 PR；E-9 第 2 點原文已預留 E-7 第 3 點的路徑 | `n171a.json` 不再是純加法；擁有者名稱涵蓋一句結算共用字面 | 被當成先例，在 N-171-A 夾帶其他差異。對策：釐清五寫死恰好 3 筆 | **採用** |
| (b) 另立 `settlement_wording.json`，由獨立 PR 先合 | E-9 第 2 點保持字面為空；字面可以單獨審 | 三個 PR 串行；N-171-A 要再 merge product、重跑 E-16 與 merge 審查；E-6 第 1 點沒有「非功能擁有者」這種類別，要另外釐清 | 機制被 cherry-pick 兩次，增加 merge 衝突面 | 否決 |
| (c) 另立擁有者檔，但放進 N-171-A 的 PR | E-9 第 2 點表面上為空 | 違反 E-6 第 1 點「PR 只改自己的檔」，其實就是 (a) 換個檔名 | 規則被名目繞過 | 否決 |
| (d) 重錄或手改 golden | — | 違反 E-5 | T2 變成自己比自己 | **VETO** |

**三筆差異所在的情境與回應**（行號為 golden 檔內行號，已讀檔確認）：

| id | golden 行 | scenario | body | 情境內容 | 為什麼這句不實或不精確 |
|---|---|---|---|---|---|
| N171A-D1 | 192 | `after_exit` | `today` | `as_of` 為 2026-08-11、緊急出清凍結中；批次 2、3 的 EMERGENCY 賣單在 8/12 執行，另有批次 1 的 R1 買單在 8/12 執行，都還沒到 | **正是風控 S-A 的同頁矛盾**：同一個回應的 `pending_exit_block` 列出批次 2、3（`n171a.json` 的 `filled` 已登記） |
| N171A-D2 | 488 | `authored` | `today` | 正常模式；R1 買單在 8/12 執行，還沒到；沒有出清 | 風控指出「在預定執行日未到的 R 系列買單上本來也不精確」 |
| N171A-D3 | 607 | `authored` | `today_again` | 同日重新整理，同上 | 同上 |

不受影響的回應：
- `after_exit.today_next_day`：走 SUMMARY 支；
- `after_exit.exit`、`exit_repeat`：沒有 `settlement`；
- `unauthored.*`：`settlement` 為 null，或是出清回應。

如果出現第 4 處差異，就屬於本核准以外，PR 停住。

#### B. 書面核准（E-7 第 3 點；本段即 `approval` 所指內容）

tech-architect 依補充四釐清二 E-7 第 3 點，逐一 id 核准 N171A-D1、N171A-D2、N171A-D3，條件如下：

1. `after` 逐字等於風控核可的 `SETTLEMENT_NOTHING_PENDING` 定稿。它必須是單一字串、不含 `{…}` 佔位符，在 `settlement.warnings` 中仍然只佔 1 個元素。不符合任何一項，本核准就不涵蓋。
2. 渲染條件不變：仍然只在 `_settle_pending` 的 `pending_directives(on_or_before=as_of)` 為空時輸出。`service.py` 零 diff。
3. 風控的逐字核可檔要另外寫明「確認 D1～D3 三處既有揭露的改變」（E-7 第 3 點後半）。
4. 依釐清五 E-19 第 2 點，以原子 commit 落地。

登記內容如下（三筆只有 `id`、`scenario`、`body` 不同）：

```json
 "deltas": [
  {
   "id": "N171A-D1",
   "source": "風控 2026-11-04 N-171-A 最終字面終核 required（work/reviews/2026-11-04-N171A最終字面終核-風控.md 第二節逐條意見第 1 項）；SETTLEMENT_NOTHING_PENDING 逐字定稿：<<風控逐字核可檔路徑，定稿後填入>>；渲染條件不變（_settle_pending：pending_directives(on_or_before=as_of) 為空）",
   "approval": "work/reviews/2026-11-04-N171A結算句golden差異核准-tech-architect.md",
   "scenario": "after_exit",
   "body": "today",
   "path": ["settlement", "warnings", 0],
   "op": "replace",
   "before": "T+1 結算：目前沒有待結算指令。",
   "after": "<<SETTLEMENT_NOTHING_PENDING 定稿，風控逐字核可後填入>>"
  },
  { "id": "N171A-D2", …同上…, "scenario": "authored", "body": "today", … },
  { "id": "N171A-D3", …同上…, "scenario": "authored", "body": "today_again", … }
 ]
```

- `before` 必須逐字照抄，含全形「：」與「。」。
- 佔位符只能存在於本草稿和 PR 說明草稿中，**不得 commit**（見 E-19 第 2 點）。
- 我讀過 `seam_helpers.py` 的 `parse_registration`／`expected_bodies`：上面的鍵集合符合機制要求。三筆不在同一個 list 上，也和 N168-D5（`after_exit.today_next_day.settlement.warnings[1]`）不同 list，不會觸發 E-6 第 4 點的同 list 檢查。

#### C. 釐清五全文（附在補充四檔末、釐清四之後）

```
## 釐清五（tech-architect 2026-11-04，`SETTLEMENT_NOTHING_PENDING` 改寫在 SEAM golden 上的差異登記與字面替換連動）

- 性質：釐清 E-6、E-7 第 3 點、E-9 第 2 點、E-11 第 5 點與 E-12 QB-12；E-20 訂定「字面替換的連動」處理規則，適用切面之後每一個 PR。不改任何固定項，不改 S-6 判準，不改 golden，不授權重錄。
- 依據：`work/reviews/2026-11-04-N171A最終字面終核-風控.md` 第二節逐條意見第 1 項（required）與第四節第 2 點；ADR-0039 Decision 17、附錄 A C18、附錄 B T21、補充一 S-3 第 3、4 點；補充四 SEAM-T6；釐清二 E-5～E-9、E-11；釐清三；釐清四 E-13、E-14。
- 核准檔：`work/reviews/2026-11-04-N171A結算句golden差異核准-tech-architect.md`。

### E-18 擁有者與範圍
1. `SETTLEMENT_NOTHING_PENDING` 的改寫是 N-171-A 的合併條件，差異登記在 `approved/n171a.json`，不另立擁有者檔。
2. E-9 第 2 點「`deltas` 必須為空」改為：`n171a.json` 的 `deltas` 恰好是 N171A-D1～D3 三筆，經 E-7 第 3 點核准。出現第四筆時，仍依 E-9 第 2 點停住。
3. 範圍只限 `wording.py` 中這一個常數的值：
 - 常數名不改；
 - 新值是一個不含佔位符的靜態字串，在 `settlement.warnings` 中仍只佔一個元素；
 - `_settle_pending`（含輸出這句的分支與其條件）、`settle_pending`、`settle_on_request` 零 diff；
 - 不新增讀取、分支或日期判斷。
 若定稿需要佔位符、條件變體、拆成多個元素，或需要知道「有沒有未到期的列」，就超出本釐清：PR 停住，送 tech-architect。這類需求會觸及補充一 S-3 第 3 點、SEAM-T6 與釐清三。
4. 與既有條文不衝突：
 - ADR-0039 Decision 17、C18、T21 所稱的 `warnings`，是 `/today` 頂層的 `TodayResponse.warnings`，不含 `settlement.warnings`。頂層 `warnings` 仍須零 diff。
 - 補充一 S-3 第 3 點與 E-11 第 5 點約束的是 `_settle_pending` 的程式與新增句子。替換既有常數的值，只在本條範圍內例外；N-171-A 不得以此為由，在結算 warnings 上新增、移除或重排任何句子。
 - 補充一 S-3 第 4 點「不得同時有 `SETTLEMENT_NOTHING_PENDING`」以識別名約束，改值之後照樣成立。
5. 不採獨立先行 PR：機制 `01e99cb` 在 N-171-A 的 PR 內。先行 PR 須先走 E-13 第 5 點，三個 PR 串行，安全上沒有增益。

### E-19 三筆差異與落地方式
1. 三筆差異如下：

 | id | scenario | body | path | op | before |
 |---|---|---|---|---|---|
 | N171A-D1 | after_exit | today | ["settlement","warnings",0] | replace | "T+1 結算：目前沒有待結算指令。" |
 | N171A-D2 | authored | today | ["settlement","warnings",0] | replace | 同上 |
 | N171A-D3 | authored | today_again | ["settlement","warnings",0] | replace | 同上 |

 - `after` 為風控逐字核可的定稿，三筆相同。
 - `source` 寫風控終核與逐字核可檔的路徑。
 - `approval` 寫核准檔的路徑。
2. 原子單位：只在風控逐字核可檔存在之後，以**一個 commit** 同時落地以下三件：
 - (a) `wording.py` 該常數的值，以及它的 `#:` 註解；註解寫明輸出條件與風控出處；
 - (b) `n171a.json` 的三筆 `deltas`：`after` 逐字等於定稿，`source` 已填入核可檔路徑；
 - (c) `tests/test_playbook_wording.py` 新增這個常數的逐字守門測試。
 該 commit 上 SEAM-T1～T8 全綠。`approved/` 下不得留有任何佔位符。不得 rebase、不得 force push；PR 仍以 merge commit 合併（E-14 第 2 點 (d)）。
3. 預期不受影響：`after_exit.today_next_day`、`after_exit.exit`、`after_exit.exit_repeat`、`unauthored` 的三個回應。實際 diff 多出或少掉任何一處，PR 停住。
4. 與 N-168 的關係：N168-D5 在 `after_exit.today_next_day.settlement.warnings`，與 D1～D3 不在同一個 list。N-168 若在 D1～D3 所在的 list 上出現差異，依 E-6 第 4 點停住，由 tech-architect 裁定。

### E-20 字面替換的連動（測試）
1. 以識別名引用常數的斷言：零 diff，自動跟著變，不算斷言改動。
2. 該常數本身的逐字守門測試（斷言常數等於某個字面）：新增，或只把字串字面整條換掉，都屬於字面替換的連動，不算 SEAM-T6 或 E-4 所指的斷言改動。要放在 E-19 第 2 點的同一個 commit，並在 PR 說明列出。
3. 其他測試若以完整字面寫死舊句：只准把舊字串整條換成新定稿。斷言的欄位、運算子、位置與筆數都不得改。放在同一個 commit，並在 PR 說明逐條列出。
4. 以子字串、前綴、關鍵詞或否定式（例如 `in`、`not in`、`startswith`）斷言舊句內容的，屬於語意斷言，不得當成連動處理，依 E-7 第 3 點送核。
5. golden 不適用本條，只能依 E-6 登記。
6. 前端目前沒有這句的鏡射，`SettlementPanel` 原樣渲染。以識別名指涉的註解不必改。日後若新增鏡射，比照 Decision 13 的原子單位。
7. 字面整檔掃描與禁用詞測試（含 `test_c6_*`、`test_i_*`）若轉紅：停住送風控，不得收窄掃描範圍或放寬白名單。

### E-21 `POST /settle` 現況（讀碼）
- SEAM-T6 所指的既有測試（`test_api_playbook.py` 的 settle 三條，以及 `/today` 結算那一條）都不斷言 `warnings`，零 diff。
- N-171-A 新增的 `test_playbook_settle_on_request.py` 以識別名引用（`:111`、`:214`），零 diff。
- `:376-381` 是 `SETTLEMENT_UNAUTHORED_NOTE` 的逐字守門測試，不是本句，不改。
- 寫死本句的地方只有 golden 那 3 處。

### E-22 S-7 增列檢查項
- QB-15（N-171-A 的 PR）：
 - `n171a.json` 的 `deltas` 恰好是 N171A-D1～D3，內容與 E-19 第 1 點逐欄一致；`after` 與風控核可檔逐字相同；`approved/` 下 grep `<<` 為 0。
 - E-19 第 2 點的三件東西在同一個 commit。
 - `service.py` 中 `_settle_pending`、`settle_pending`、`settle_on_request` 零 diff。該 commit 的 `wording.py` diff 只有這個常數與它的註解。常數名不變，`app/` 內 grep `SETTLEMENT_NOTHING_PENDING` 的命中數與改動前相同。
 - golden 零 diff，`GOLDEN_SHA256` 未改；頂層 `warnings` 零 diff（C18）。
 - 測試 diff 只有 E-20 第 2、3 點所允許的部分；`test_api_playbook.py` 零 diff。
 - PR 說明列出 D1～D3 與 E-20 的每一處連動。
```

#### D. 對實作的約束（qa 依 QB-15 逐條檢查）
- 常數名 `SETTLEMENT_NOTHING_PENDING` 不改名。ADR-0039 S-3 第 4 點、PRD AC、`types.ts` 與 `SettlementPanel.tsx` 的註解都以這個識別名指涉，改名會牽動 accepted ADR 的條文。
- 新字面要做成靜態、單一字串，不點名區塊，也不依賴台北日期或 UTC 日期。這是架構面的上限，請 creative-lead 現在就在這個框架內擬稿。
- 建議（不擋）：保留「T+1 結算：」前綴，與 SUMMARY、UNAUTHORED_NOTE 一致，也能避開既有前綴斷言的連動風險。

### 給風控的兩點（判斷權在風控，我不裁）
1. `SETTLEMENT_UNAUTHORED_NOTE` 定稿裡有「不代表目前沒有待結算指令」，引用的正是舊句的說法。舊句改寫之後，這句仍然為真，但前後呼應的對象不見了。要不要同步調整由風控決定。若要改，就是另一次逐字變更：不涉及 golden（`POST /settle` 不在 golden 裡，unauthored 的 `/today` `settlement` 為 null），守門測試 `:376-381` 依 E-20 第 2 點處理。
2. 觀察：`SETTLEMENT_SUMMARY` 的「未結算 {pending} 筆」只計入這次已到期的列。若同一天既有已到期的列被結算，又有預定執行日較晚的出清列留在區塊裡，就可能出現「未結算 0 筆」和「尚未結算的賣出指令」同頁。這比 NOTHING_PENDING 輕，因為句子前面有「依…開盤價判定」限定範圍，但結構相似，請風控判斷要不要一併看。不在本次核准範圍內，我這邊不擋。

### 其他部門
本次未參與，屬純裁示；需要經手的見第四段。

## 三、驗證

**我讀過的檔案**
- 風控終核全文；
- 釐清二、三、四全文；
- 補充四中 SEAM-T6 的定義；
- ADR-0039 的 Decision 12、13、17、附錄 A／B、補充一 S-1～S-8；
- 主工作樹（`product/stock-desk`）上的 golden：第 113-237、280-410、478-647 行，以及全檔的鍵結構；
- 主工作樹的 `test_api_playbook.py:310-414`；
- N-171-A 分支工作樹 `scratchpad/wt_n171b`（detached HEAD `346d5cb`）中的以下檔案：
  - `approved/n171a.json`（`deltas: []`）；
  - `seam_helpers.py:120-328`（登記格式與套用邏輯）；
  - `test_playbook_settle_on_request.py:1-230`；
  - `wording.py:722-750`；
  - `service.py:1025-1049`；
  - `types.ts:1760-1775`；
  - `TodaySeamFixture.test.ts`：讀 golden 當 fixture，不斷言這句。

**grep 結果**
- 主工作樹與 `wt_n171b` 的 `apps/stock-desk` 下，以字面寫死這句的只有 golden 的 3 處。
- 測試中以識別名引用的只有 `test_playbook_settle_on_request.py:111`、`:214`。
- 前端沒有鏡射。

**沒驗證到的事**
- `wt_n171b` 的 HEAD 是 `346d5cb`，不一定等於分支最新的 head（風控審的是 `5e7c31c`）。最新 head 上有沒有別的測試寫死這句，要由 qa-reviewer 在實際 head 上用 `git diff` 加 grep，依 QB-15 確認。
- N-168 分支的測試我看不到。它 merge 時若遇到寫死舊句的測試，依 E-20 處理。
- 對 `scratchpad` 整體的 grep 曾逾時，結果不完整；`wt_n171b/apps/stock-desk` 的 grep 是完整的。

**本次限制**：沒有執行任何程式或測試，沒有使用 git，沒有讀 `.env`，沒有碰 `data/*.db`，沒有修改任何檔案。

**CEO 不需要親自驗證。**

## 四、下一步

1. **coordinator**：
   - 把本報告逐字轉存到 `/home/user/AICompany/work/reviews/2026-11-04-N171A結算句golden差異核准-tech-architect.md`；
   - 把第二段 C 的釐清五附到 `/home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md` 檔末，ADR-0035 檔頭的註記改為「另見補充四釐清一至五」；
   - 把 E-18 第 3 點（靜態、單一字串、無佔位符）轉知 creative-lead，作為擬稿的上限。
2. **risk-compliance-officer**：逐字核可時，在同一份核可檔中：
   - 寫明確認 D1～D3 三處既有揭露的改變；
   - 裁示上面「給風控的兩點」。
3. **dev-lead**：拿到風控核可檔之後，依 E-19 第 2 點做一個原子 commit。之後依序：
   - qa-reviewer（含 Codex）以 QB-12～QB-15 審查；
   - qa-automation 代跑、qa-e2e 重新擷取 S-A 與 S-D；
   - 風控書面複核；
   - 以上都完成才可合併。

### 相關檔案
- /home/user/AICompany/work/reviews/2026-11-04-N171A最終字面終核-風控.md
- /home/user/AICompany/work/reviews/2026-11-04-ADR0035補充四釐清二-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-04-ADR0035補充四釐清四-tech-architect.md
- /home/user/AICompany/work/reviews/2026-11-03-ADR0035補充四與N171評估-tech-architect.md
- /home/user/AICompany/docs/adr/0039-stock-desk-today常駐揭露待執行與近期已結算的出清指令.md
- /home/user/AICompany/apps/stock-desk/backend/tests/golden/seam/pre_seam_responses.json（:192、:488、:607）
- /home/user/AICompany/apps/stock-desk/backend/tests/test_api_playbook.py（:360-414）
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n171b/apps/stock-desk/backend/tests/golden/seam/approved/n171a.json
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n171b/apps/stock-desk/backend/tests/seam_helpers.py
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n171b/apps/stock-desk/backend/tests/test_playbook_settle_on_request.py（:111、:214、:376-381）
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n171b/apps/stock-desk/backend/app/playbook/wording.py（:734）
- /tmp/claude-0/-home-user-AICompany/3f76d891-50d3-55e1-b39d-925b8a90241a/scratchpad/wt_n171b/apps/stock-desk/backend/app/playbook/service.py（:1033-1043）

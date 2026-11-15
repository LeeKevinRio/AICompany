# NM-5 第五批 F-2 視窗與 WARNING 裁示

- 審查者：tech-architect
- 日期：2026-11-15
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論

三題都已裁示。我的讀法沒有一處比 quant 寬，所以這三題不需要送風控。另外我讀碼時發現一個會違反 D-4 第 5 點的輸出問題，依 CEO #139 屬於插隊類，要在第五批合併前修正（見第 4 點）。

1. **F-2 計數視窗：採用 quant 的 (a)～(f) 作為補充解讀，但有兩處比 quant 更嚴。**
   - 分母：用 min（20，窗內定案 session 數），不用固定 20。
     - 理由：F-2 要量的是「可記錄的日子裡遺失了多少」。固定 20 時，休市日等於自動算作正常，假期多的窗會被稀釋。
     - 取 min 的作用：分母永遠不會大於 20，所以不會比字面讀法（固定 20）寬。
   - 分子中的「定案 session」：取「全部快照定案 session 的聯集」，與 n̂ 共用同一個查詢，不只看最新快照。
     - 理由：最新快照只涵蓋約 315 根 bar。較舊的視窗如果只看最新快照，那段 session 會掉出範圍，計數歸零，等於變寬。聯集包含最新快照的全部 session，所以只會更嚴。
   - 另補一個已知盲點，知悉、不處理：主機整段停機期間沒有新快照，F-2 會偏低。停機的偵測由 devops-sre 的心跳負責（D-10）。
2. **D-8 第 4 點 WARNING：三項都同意。**
   - 「成立期間每次執行都記一次」可以，已涵蓋首次。
   - log 只寫 `claim_id` 與 T1／T2，正確。我再收緊一點：c₁、d₁、D_v、任何計數或日期都不寫。
   - 排進接線 PR、列為 CG-4 阻擋項，可以。
   - 另外規定：判定在 `forecast_run_end` 寫入之後進行，不得影響 outcome 或任何紀錄；判定拋出例外時，只記一行固定字面的 WARNING。
3. **quant 第 1 點 (a)～(c)：與 D-7 相容，要入 ADR。**
   - D-7 第 4 點「每一筆」照字面無法滿足。理由：engine 的第 (0) 步排在規則前面（D-3 第 6 點），insufficient 紀錄不可能等於 B6。所以讀成「每一筆非 insufficient 紀錄」，insufficient 的情形依同點後句交給合成 fixture 驗證。
   - (a) 我加嚴一款：每組至少要有 1 筆非 insufficient 紀錄的暫定對照有結果，否則第二個斷言同樣會空轉。
4. **插隊項（新發現）：harness 的完整輸出含有 n̂。**
   - 位置：`tests/forecast_pipeline_harness.py` 第 422～428 行，`result.output` 收進了 `report.render_status`；該段第 426～428 行列出 n̂、T1、T2。
   - 違反的條文：D-4 第 5 點把「管線驗收 harness」與「操作者報告」分開列，n̂ 的唯一例外只給操作者報告。
   - 實際外洩風險很低：真實資料那次的完整輸出只寫進暫存檔，事後刪除。但字面上已經違規，所以屬插隊類，須在第五批合併前修。
5. ADR 補充五的全文在下方，可逐字落檔。

## 各部門回報

**tech-architect：方案比較**

F-2 分母

| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| 固定 20（quant 建議） | 照字面，實作最簡單 | 休市日被當成正常，假期多的窗會被稀釋 | 春節等長假期間的遺失看不出來 |
| 窗內定案 session 數 s | 最符合「遺失率」的本意 | 補班日若有交易，s 可能大於 20，理論上比字面寬 | 要說明理由才能自證不寬 |
| **min（20，s）（採用）** | 永遠不寬於字面；休市日多時更嚴 | 實作多一步 | 窗內 session 都不在快照裡時 s＝0，有任何 `inputs_not_ready` 就成立（屬 fail-closed，接受） |

F-2 起點

| 方案 | 結論 |
|---|---|
| 登記日（第五批現行做法） | 否決。登記到接線之間的空窗會全部算成缺漏，接線後馬上誤觸發。 |
| D_v | 否決。初期的失敗被排除在外，比較寬，要送風控。 |
| **max（登記日，第一筆 `forecast_run` 的日期）（採用，與 quant 相同）** | 正式 claim 的登記一定早於任何 run，所以實際上等於第一筆 run 的日期。日後換 claim 時，新 claim 自然改用它自己的登記日，順帶滿足補充四第 1 點 (d)。 |

D-8 第 4 點 WARNING

| 方案 | 結論 |
|---|---|
| 記住「首次」 | 否決。要新增狀態欄或表，K-5、K-12 不允許。 |
| **成立期間每次執行都記一次（採用）** | 一天最多記 2～3 次，可以接受。 |

**依 CEO #139 的分類**（coordinator 定案，CEO 可推翻）

| 項目 | 分類 | 期限或閘門 |
|---|---|---|
| 補充五第 5 點：harness 輸出含 n̂ | **插隊**（輸出違反 D-4） | 第五批合併前，qa 列 BLOCKING |
| 補充五第 3 點：空轉防護 | 不插隊，綁閘門 | 真實資料一鍵檔執行前；沒有它，harness 不算通過，CG-2 也就擋住了 |
| 補充五第 1 點：F-2 | 不插隊，綁閘門 | 接線 PR，列 CG-4 阻擋項。理由：接線前不會有正式資料，現行定義不會誤導任何人 |
| 補充五第 2 點：WARNING | 不插隊，綁閘門 | 接線 PR，列 CG-4 阻擋項 |
| quant 第 5 點：「未驗證」防回歸測試 | 凍結後待辦 | 不擋件 |
| `z = r / (σ·√h)` 同時寫在 `app/outlook/baselines.py:73` 與 `app/forecast/scoring.py:176`（運算順序相同） | 凍結後待辦 | qa 判斷 K-6 是否要求抽成單一函式。兩處不一致時才升為插隊 |

**對實作的約束（qa 可逐條檢查）**
- C5-1：harness 的完整輸出與 `render_summary` 都不含「n̂」、n̂ 的固定標示，以及 T1／T2 的判定列；`report status` 照常列出。
- C5-2：`render_summary` 不得列 `insufficient`、`labels_checked`、`compared` 這類筆數。
- C5-3：F-2 的計數與成立與否只在 `store.py` 導出；平日函式與 T2 共用一個；`report.py` 現行的 `f2_window`（自己用 `weekday() < 5` 判斷平日）要移除。
- C5-4：WARNING 不在寫入交易內執行，不改變 outcome 或 `content_hash`；只捕捉 `Exception`。
- C5-5：空轉防護 (a)～(c) 只輸出通過／失敗與失敗種類。

**ADR-0030 補充五全文**（由 coordinator 落檔，只能追加）

區塊一：插在檔頭第 8 行（補充四那一行）之後。

```
- 補充紀錄：2026-11-15 append 補充五（第五批解讀確認、失效條件 F-2 的計數視窗、D-8 第 4 點 WARNING、管線驗收的斷言範圍與空轉防護、harness 輸出不含 n̂；tech-architect 裁示，釐清與收緊，沒有放寬，不改使用者面字面與已登記雜湊，CEO 可推翻；來源 `work/reviews/2026-11-15-NM5第五批交件-dev-lead.md`、`work/reviews/2026-11-15-NM5第五批五點解讀確認-quant.md`）。
```

區塊二：追加在檔尾，接在補充四的 S-14a 之後。

```
---

## 補充五：第五批解讀確認、F-2 計數視窗、D-8 第 4 點 WARNING、管線驗收的空轉防護（2026-11-15）

- 決策者：tech-architect。來源：dev-lead 第五批交件「已知限制與解讀」五點；quant 第五批五點解讀確認第 1、3、4 點。另讀 `feat/nm5-forecast-storage`（518046f9）的 `tests/forecast_pipeline_harness.py`：`run_acceptance` 的輸出含 `report.render_status`，該段列出 n̂（第 5 點）。
- 性質：釐清失效條件 F-2、D-7 第 4 點與 D-8 第 4 點的讀法；收緊 F-2 的計數，以及 D-4 第 5 點在 harness 輸出上的適用。補充本文，不改本文；沒有放寬；不改使用者面字面，也不改規則檔、定義物件與已登記雜湊。CEO 可推翻。

1. **F-2 的計數視窗**：只適用 F-2 第一句；第二句的第 0 相位格點遺失率自 D_v 起累計，不受本點影響。報告標題寫「ADR-0030 失效條件 F-2」，與事先宣告的下架規則 F-2 區分。
   - (a) 平日與日期：平日指週一至週五，不扣休市日，與 D-8 第 4 點 T2 使用同一個函式。日期一律以 Asia/Taipei 計。平日 D 要等 D 的 `late_cutoff_at` 已過，才進入視窗，所以當天不計入。
   - (b) 起點：claim c 的起點 S_c ＝ max（c 的 `registered_at` 日期，第一筆 `forecast_run` 的 `started_at` 日期）。不以 D_v 為起點。
   - (c) 視窗與滾動：
     - S_c 以後每連續 20 個平日為一個視窗，逐平日滾動。
     - 視窗的日曆範圍是它的第一個到最後一個平日，含其間的週末。
     - 逐一評估 S_c 以來每一個完整的視窗，任一視窗成立，F-2 就成立；之後的視窗不成立，也不撤銷。
   - (d) 分子：每個 claim 各自計算，等於下列兩項照字面相加，重複的部分不扣除。
     - 視窗日曆範圍內的定案 session 中，該 claim 沒有 `late = 0` 紀錄的 session 數。定案 session 取至今全部快照中定案 session 的聯集，與 n̂ 用同一個查詢。這個集合包含最新快照中的 session，所以不寬於字面。
     - 視窗日曆範圍內，有任一次執行 outcome 為 `inputs_not_ready` 的日數，以 `started_at` 的日期計。同一天多次只算一天；同一天另有 `ok`，也照樣計入。
   - (e) 分母與門檻：分母 ＝ min（20，視窗日曆範圍內的定案 session 數）。分子大於分母的 30% 就成立。分母不會大於 20，所以不寬於「固定 20」的字面讀法；休市日多的視窗會比較嚴。
   - (f) 視窗未滿：S_c 以來不足 20 個平日時，分子大於 6 就成立；否則標示「視窗未滿」。
   - (g) 導出與輸出：
     - 計數與是否成立，只由 `store.py` 的唯讀查詢導出。
     - `report status` 每次輸出：最近一個完整視窗的起迄日、兩項分子、分母、是否成立，以及「自起點以來曾否成立」。
     - 這些屬 D-4 第 5 點的執行狀態：可以依 claim 分列；不得與標籤或對照並列，也不得依標籤、基準或暫定對照分列。
   - (h) 已知盲點（知悉，不處理）：主機整段停機時沒有新快照，停機期間的 session 要等下一次執行的快照出現，才進入分子；停機中執行 `report`，F-2 會偏低。停機的偵測由 devops-sre 的心跳負責（D-10）。
   - 期限：在接線 PR 落地，列為 CG-4 的阻擋項。
2. **D-8 第 4 點的 WARNING**
   - 讀法：「首次成立時 recorder 記 WARNING」讀為「T1 或 T2 成立期間，recorder 每次執行各記一次」，因此涵蓋首次。recorder 不保存「已記過」的狀態，也不新增欄位或表。
   - 內容：每個成立的 claim 記一行，只含固定的英文字面、`claim_id`，以及成立的是 T1、T2 或兩者。不含 n̂、c₁、d₁、D_v、任何計數或日期，也不含標籤。
   - 判定方式：
     - 經 `store.py` 的唯讀查詢判定，「今天」取 store 時鐘的台北日期，在 `forecast_run_end` 寫入之後進行。
     - 判定不得改變 outcome、`records_written`、`error_class` 或任何紀錄。
     - 判定拋出 `Exception` 時，改記一行固定字面的 WARNING，照常結束；不捕捉 `BaseException`。
     - 沒有 D_v 時，T1、T2 都不成立，不記。
   - 期限：在接線 PR 落地，列為 CG-4 的阻擋項。
3. **D-7 第 4 點的斷言範圍與空轉防護**
   - 讀法：「harness 斷言每一筆的模型標籤與對應基準逐筆相同」讀為「每一筆不是 `insufficient` 的紀錄都相同」。
     - 理由：engine 的第 (0) 步排在規則之前（D-3 第 6 點），所以 insufficient 紀錄在字面上不可能等於 B6。這類紀錄依同點後句，以合成 fixture 驗證。
     - D-7 第 1、6 點不變：harness 仍不得宣稱真實時序已驗證。
   - 為免斷言空轉，harness 另加三項，任一不成立就判失敗：
     - (a) P-0、P-1 各自的 h3、h5 claim，都至少有 1 筆非 insufficient 紀錄，而且其中至少 1 筆的暫定對照有結果（不是「無法對照」）。不成立時，失敗種類為 `vacuous_equality`。
     - (b) 模型不是 insufficient、對應基準卻是 `unavailable` 時，判失敗，不跳過。
     - (c) insufficient 紀錄的 missing code 只能是凍結包 §2.5 表內的四類；`missing` 非空 ⇔ `label = insufficient`。
   - 三項都只輸出通過或失敗，以及失敗種類，不輸出筆數。
   - 期限：在真實資料一鍵檔執行之前落地。缺少時，真實資料的 harness 不算通過，依補充四第 6 點也不得進行 CG-2 登記。
4. **暫定對照的實現標籤**：依事先宣告 §2.1，用紀錄自己的 `K_h`、`EPS`、`sigma_d`，以 `app.outlook.volatility.log_return` 與 `app.outlook.baselines.threshold_label` 計算，不另寫（K-6）。不套用 `f2_variant`：C-8 是驗證層的下架規則，隨 D-8 凍結。
5. **harness 輸出中的 n̂**
   - D-4 第 5 點對 n̂ 的唯一例外，只限操作者報告（`report` CLI）。
   - 管線驗收 harness 的輸出，包括只寫進暫存檔的完整輸出與 `render_summary`，都不得含 n̂、T1／T2 的判定列，或 n̂ 的固定標示。F-2 計數與各 outcome 的次數屬執行狀態，可以列。
   - `render_summary` 不得列非 insufficient 的筆數、可對照的筆數，或任何與符合與否有關的計數。
   - 期限：在第五批合併前落地。

- **S-10a、S-13a（逐條可檢查）**：
  - 第 1 點：
    - 以合成帳的測試涵蓋：起點早於第一筆 `forecast_run` 時，那段期間不計入；同一天兩次 `inputs_not_ready` 只算一天；一個 session 未定案且一直沒有紀錄時計入 2；休市日多的視窗以 min（20，s）為分母；只有較早的視窗成立時，「曾否成立」仍為成立；視窗未滿的兩種情形；當天不計入。
    - 平日函式與 T2 相同（AST 或 import）；F-2 計數只在 `store.py` 導出（grep）。
  - 第 2 點：以下四種情形各有測試，outcome 與 `content_hash` 都不變，log 行符合固定格式：不成立時不記；只有 T1；T1 與 T2 同時成立；判定拋出例外時記固定字面的 WARNING。
  - 第 3 點：(a)～(c) 各有一個會判失敗的反例 fixture，例如全部紀錄都是 insufficient 時判 `vacuous_equality`。
  - 第 5 點：harness 的完整輸出與 `render_summary` 都不含「n̂」與 n̂ 的固定標示；`report status` 照常列出 n̂（測試）。
```

**風控**
- 我的讀法沒有比 quant 寬，不需要送審。
- 要揭露的一點：補充五第 3 點把 D-7 第 4 點的斷言範圍縮小到非 insufficient 紀錄。這是因為字面不可能滿足，並以 (a)～(c) 補償。harness 不是使用者面文字，也不是證據，所以我判定不需要送審。coordinator 若認為仍要知會，可以附上這一點。

## 驗證

- 讀過的文件：
  - `/home/user/AICompany/work/reviews/2026-11-15-NM5第五批五點解讀確認-quant.md`
  - `/home/user/AICompany/work/reviews/2026-11-15-NM5第五批交件-dev-lead.md`
  - `/home/user/AICompany/docs/adr/0030-stock-desk-預測紀錄帳核心-最小記錄器.md`（全文 524 行，含補充一～四與補充三修訂版）
  - `/home/user/AICompany/work/dispatch/2026-11-11-N207規格凍結與測試實證令-coordinator.md`
  - `/home/user/AICompany/work/research/2026-11-14-NM5凍結包-大盤h3h5-quant.md` 的 §2.4～2.10、V32-06～V32-10
- 程式碼：你說本機沒有，但其實有。
  - `/home/user/AICompany/.claude/worktrees/agent-ac6740f4f9f9cd706/` 的分支 ref `nm5-batch5` 指向 `518046f9ca317d61f9859beedd67b8066199f92d`，與交件 head 相同。工作樹是否乾淨，我沒有核對。
  - 讀了以下幾處，其中 harness 的部分是第 4 點插隊項的依據：
    - `app/forecast/report.py` 第 354～430 行：F-2 用最新快照、以登記日為起點、只看最近 20 個平日，而且沒有判定成立與否。
    - `app/forecast/store.py` 第 396～459、1197～1282 行。
    - `tests/forecast_pipeline_harness.py` 第 336～506 行。
    - `app/forecast/scoring.py` 的 import 段與第 173～177 行：確實重用 `log_return` 與 `threshold_label`。這是讀碼初判，K-6 仍交 qa 正式核對。
- 未實證：以上都是讀碼推論，我沒有執行任何測試或程式。
- 補充五事先宣告的閾值與 Taiwan 補班日是否開市：我沒有查證，只用 min 的設計讓結論不依賴這件事。
- 沒有讀 `.env`、沒有碰任何 `*.db`、沒有改檔、沒有 commit。

## 下一步

1. **coordinator**：
   - 依上方兩個區塊把補充五落檔到 ADR-0030。
   - 把本回報轉存為 `work/reviews/2026-11-15-NM5第五批F2視窗與WARNING裁示-tech-architect.md`。
   - 依 #139 確認上表的分類，並把兩項凍結後待辦登錄到後續追蹤清單。
2. **dev-lead**：
   - 第五批合併前：修補充五第 5 點（harness 輸出不得含 n̂）。
   - 真實資料一鍵檔之前：補第 3 點 (a)～(c)。
   - 接線 PR：做第 1、2 點，並在 PR 說明列為 CG-4 阻擋項。
3. **qa-reviewer**：
   - 審 `c4e0361..518046f` 時，把「harness 輸出含 n̂」列為 BLOCKING。
   - 依 quant 的要求核對 K-6，並判斷 `baselines.py:73` 與 `scoring.py:176` 重複的 z 算式是否構成 K-6 違規。
   - 確認 `518046f` 的 AST 守門確實擋住正式 DB 路徑比對。
4. **devops-sre**：一鍵檔的 `render_summary` 依約束 C5-2 設計。主機停機的偵測由心跳負責，承接補充五第 1 點 (h) 的盲點。
5. **風控**：不需要介入。

# ADR-0027 r3′ 補正（R3-1～R3-13、suggested、X2 同一定義；附 ADR-0028 A-96／A-97 建議，tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 r3′ 補正（R3-1～R3-13、suggested、X2 同一定義；附 ADR-0028 兩題）：tech-architect（唯讀）

基準是我的 r3 提案和 commit 9ba01d6 的 ADR-0027。X2 依據兩份風控文件：r3 審查（R3-11 第 1～4 點），以及風控單項確認 `2026-10-17-A-15-事先宣告v0.10修正單項確認含R3-11一致性-風控.md` 的 R-A、R-B、F-8，後者以較新者為準。我沒有改任何檔案，沒有讀 `.env` 或 `*.db`，也沒有跑程式、測試或 git。

## 一、結論

**R3-1～R3-13 全部採用。** 補正都掛在既有的 A 編號底下，不新增 A-87 以後的 ADR-0027 條號，所以方向統計維持 20／2／9／1／1。

**A-84 已經落地，tech-writer 不要再插入。** ADR-0028 CS-12 L301 已有「不設執行期旗標」（commit 1d69acd），修訂紀錄 L574 也登記了。機械核對第 12 點的期望是「恰好一次」。

**有 4 處超出風控底線的字面，請 coordinator 回送風控做單項確認。** 其中 3 處是收緊，1 處兩面：

1. **R3-5（A-27 (c)）：我寫成「PA-9 成立，或 `display_state = gated`」，不只寫「PA-9 成立」。**
   - 方向：收緊。
   - 理由：照底線字面把 (c) 換成只看 PA-9，族群在 n≥150 但因 `replay_review_pending` 仍是 `gated` 時，結算後就會顯示 label。現行 (c) 會擋住這種情形，所以照字面改等於放寬。我取兩者的聯集，避免放寬。
2. **R3-11（A-77）：X2 確認以「d 不在 D-8.1 (i)」為必要條件。**
   - 方向：補定義（兩面）。
   - 理由：風控定案的式子是「觀察日 ＝ (i) ∪〔(ii) − X2 確認日〕」，只從 (ii) 扣除。可是事先宣告的查證路徑允許「d 在 (i)、又有週末或休市證據、獨立來源也沒有 d 的資料」時確認 X2，然後把 d「從觀察日移除」。這種 d 在 ADR 的式子裡仍然經 (i) 成為觀察日，兩份文件會出現兩個定義。
   - 我的補法：這種情形一律維持異常待查證，交 data-engineer 查根因。這樣風控的式子、A-75 的排除和事先宣告的「從觀察日移除」三者就會等價。
   - 替代方案：觀察日 ＝ ((i) ∪ (ii)) − X2 確認日。但這會動到 (i)，偏離風控的字面。
3. **R3-11（A-75）：候選 T 落在週末或已接入的官方休市日時，記 `inputs_not_ready`。**
   - 方向：收緊。
   - 理由：這時市場 DB 和日曆證據互相矛盾，不該寫出前瞻紀錄。
4. **R3-10（A-72）：拒絕寫入時，POST 的回應用新的封閉 schema `OnDemandGateClosedView`，HTTP 200。狀態字面建議新起草。**
   - 方向：收緊。
   - 這是落在底線之內的選擇，列出來供風控知悉。

**另有 1 處方向標示供風控裁定：A-62。**
- R3-7 把 R2「作廢列結算後可以列示原本的 label」寫成採用，相對現行 A-36 第 4 點的 fail-closed，多了一面「有條件放寬（依風控 C-3）」。
- 依風控處理 A-71、A-73 的同一標準，A-62 應該標「收緊＋有條件放寬」。
- 我依 R3-12 維持 20／2／9／1／1；如果風控要改標，統計會變成 19／2／9／1／1／1（見第四節）。

**新浮出的後果，需要 PM 與 CEO 知悉（R3-2 的連帶）。**
- ADR-0025 D-6.6 是固定閘門：沒有經審查的回放報告，該 scope 就常駐 `gated`。
- 依 ADR-0027 D-10.4「大盤重放執行後 m 為 8」，目前只有大盤有回放計畫。個股與族群若沒有回放報告，會一直是 `gated`。
- 連帶的結果：個股 plan 的 `reasons` 選不到 LM-98，必須用 A-63 第 5 項。這個片段核可前，FL-52 (c) 失敗，D_v 會被擋住。我把這點寫進 A-79 的 Consequences。

## 二、補正條文

以下的「＞」是給 tech-writer 的條文；「定位」用 A 編號和 D-／FL- 條號。被取代的原文一律逐字進修訂紀錄。

### R3-1｜A-56（LM-97 守門）

- 定位：A-56「對應」第 2 子項，以及「LM-96～LM-98 的守門」一行。
> - `withdrawn_f2` → LM-97（三個 `withdraw_reason` 共用）。守門是 `scope_kind == symbol`，**而且 dirdef 的 `f2_variant == "F2-B"`**（D-14 G-2 機器部分，A-82）。
> - LM-96～LM-98 的守門都含 `scope_kind == symbol`；LM-97 另外含 `f2_variant == "F2-B"`。
> - `f2_variant = "F2-A"` 時，`withdrawn_f2` 沒有核可片段，FL-52 (c) 失敗。如果 C-8 選 F2-A，LM-97 的替代片段要和 D-12「CEO 若選 F2-A，列舉值…另外定」同一批另送。
- FL-52 (g) 的窮舉表加一個維度：`withdrawn_f2` × `f2_variant` × `scope_kind`，只有 (symbol, F2-B) 選到 LM-97，其他組合都沒有項目。

### R3-2｜A-57（gate 的固定項）；D-11.4 第 4 點

- 定位：A-57 (iv) 的「v1 候選值」和「實際啟用哪些值…不得出現」兩行，整段取代。
> - **`gate` 的值分成兩類：**
>   - **固定啟用**：來源是 accepted ADR 或風控底線，不受 #10 參數關閉。
>   - **#10 可加**：只能由 #10 的裁示加入。
>
> | `gate` 值 | 大盤 | 族群 | 個股 | 類別與來源 |
> |---|---|---|---|---|
> | `forward_n_below_min` | 若 quant 有登記前瞻門檻就固定；沒有登記就不適用 | **固定**（PA-9：E 內 n<150，判定用 `pa9_holds`，見 R3-5） | 同大盤 | 族群：PA-9／LG-15。大盤與個股：〔未查證〕quant 是否登記，交 quant 確認 |
> | `replay_review_pending` | **固定** | **固定** | **固定** | ADR-0025 D-6.6 |
> | `shadow_run_pending` | #10 可加 | #10 可加 | #10 可加 | 決策包 #10 (b) |
> | `settlement_smoke_pending` | #10 可加 | #10 可加 | #10 可加 | PRD 記載的風控建議 |
>
> - `replay_review_pending` 成立，若且唯若該 claim 的 (scope_kind, horizon) 在 `forecast_ledger_events` 沒有 `kind = replay_review_approved` 事件。
>   - 事件要附回放報告路徑，以及 quant 與 qa 的審查紀錄路徑；真偽由 qa 核對。
>   - 回放若以更細的單位做（例如 scope_key），以較細者為準，這只會更嚴。
>   - 某個 scope 沒有回放報告時，這個值會常駐，LM-98 選不到，改用 A-63 第 5 項。
> - **#10 只能加，不能減。** `display.py` 定義 `GATE_FIXED`（依上表逐 scope 列出）。#10 的參數只接受 `GATE_ADDITIONAL: frozenset`，而且必須 ⊆ {`shadow_run_pending`, `settlement_smoke_pending`}。
>   - 參數含有其他值、含有任何停用或覆寫固定項的鍵，或試圖把固定項設成 false，loader 都拒絕，啟動失敗。
>   - #10 可加的值沒有被加入時，不得出現在 `gate`。
>   - 要關掉任何固定項，須修訂本 ADR、經 CEO 核可、送風控。
- D-11.4 第 4 點第 4 子項「CEO #10 的結果作為參數注入」後面加：「（只能加入 A-57 列為『#10 可加』的 `gate` 值，不得關閉固定項）」。
- FL-53 (f) 加三個 fixture：
  - 參數試圖關掉 `replay_review_pending` → loader 拒絕；
  - 參數試圖關掉族群的 `forward_n_below_min` → loader 拒絕；
  - 參數含不在可加清單的值 → loader 拒絕。

### R3-3｜A-59、A-61（LM-38 狀態更新）

- A-59 第 2 子點的「LM-38 要重送成『不計入 n』」改為：
  > LM-38「不計入 n」版已於 2026-10-17 經風控單項確認核可（`work/reviews/2026-10-17-LM38與B16註記及B0頁尾單項確認-風控.md` 第 1 項）。LM-38 的適用範圍依 A-62 R2 第 3 點，只用於 E 內的作廢列。
- A-61「上畫面的前提」中，整行「LM-109：LM-38 重送核可之前不得上線；在那之前，有作廢列的清單不得渲染任何 `in_eligible_set` 字面」改為：
  > LM-109：LM-38 的前置條件已經解除（2026-10-17 風控單項確認），其餘條件不變。
- 機械核對第 4 點：「LM-38 重送核可之前」「LM-38 要重送」在本文應為 0。

### R3-4｜A-61 連帶：D-11.4 第 11 點的 PIT 標示句

- 定位：D-11.4 第 11 點 (f) 之後的「PIT 違規列的標示」一行（9ba01d6 L568）。
- 新文：
  > PIT 違規列的標示：已確認的 PIT 違規列以 LM-110＋LM-114 呈現（A-61）。視覺上不得和 E 內的紀錄相同（前端契約測試）。
- 原文逐字進修訂紀錄。機械核對：「不計入主統計（原因）」應為 0。

### R3-5｜A-63 增補：A-27 (c) 改寫、族群 (c) 優先

- 定位：D-11.4 第 11 點 A-27 的 (c) 整條取代；A-63 加第 6～8 點；A-62 R1 和 FL-58 (e) 擴充。
- A-27 (c) 新文：
  > (c) **族群，而且〔PA-9 條件成立，或 `display_state = gated`〕**：不論 `display_state` 為何、不論是否結算，都不出現 label（PA-9）。
  > - PA-9 條件 ＝ 該 claim 在 E 內、依 §4.1 計得的不重疊 n < 150。
  > - n 讀「判定 `display_state` 的同一列最新 daily snapshot」的 `n`。沒有 snapshot 時，視為 PA-9 成立（fail-closed）。
  > - PA-9 條件只有一個判定函式 `pa9_holds(claim, snapshot)`。D-11.4 第 4 點第 1 子項、A-57 族群的 `forward_n_below_min`、本條都呼叫它。
  > - **對族群，(c) 先於 (a)、(b) 判斷。** 選用狀態片段時以 (c) 為準。
- A-63 增補：
  > 6. A-63 第 1、2 項（已下架／暫停顯示，結算後列示）不得用在 (c) 成立的族群列。
  > 7. 第 4 項的語意改為「族群：PA-9 成立時不顯示方向（n／150），不得暗示之後一定會開放」，不論 `display_state`。
  > 8. 族群 (c) 成立、但 PA-9 不成立（因其他 `gate` 值而 `gated`）時，用第 5 項的族群變體，同樣不得寫「結算後列示」。
- A-62 R1 後面加：「族群另由 (c) 的優先序保證：(c) 成立的列，選不到 LM-105、LM-106，也選不到第 1～3 項。」
- **FL-58 (e) 擴充**：
  > 選中 LM-105、LM-106，或 A-63 第 1～3 項的列，所屬 claim 當下的 `display_state ≠ gated`。如果是族群列，`pa9_holds` 還必須為 false。
- **fixture**：
  - (e1) 族群 `suspended_f3`、n<150、已下架或未下架 → 選 (c)、第 4 項，不得選第 2 項；
  - (e2) 族群先 `shown`（n≥150），列已經顯示過 LM-105；PIT 違規列移出 E 後 n<150 → 同一列改選第 4 項，結算後的列也不出現 label；
  - (e3) 族群 n≥150，只因 `replay_review_pending` 而 `gated` → (c) 成立、第 5 項族群變體、結算後也不出現 label。

### R3-6｜A-63 增補（C-4）

- 定位：接在 R3-5 的第 8 點之後。
> 9. **不設遲滯。** 每次回應都依當下的 `pa9_holds` 判定，不得以「曾經顯示過」維持顯示。重新變成 PA-9 成立後，這些列改用第 4 項，不得繼續寫「結算後列示」。
> 10. quant 在驗證報告揭露兩件事：族群重新變成 PA-9 成立的事件（日期、claim、原因事件的參照），以及受影響的列數。這項列入「待決事項 quant」。
- FL-58 加 (f) 性質測試：任意的「顯示 → 移出 → n<150」序列，輸出只依當下狀態決定，和歷史無關。

### R3-7｜A-62 R2、A-65、A-36 第 4 點（作廢列的 R2）

**(1) A-62 的 R2 整段取代：**
> - **R2（風控 2026-10-17 C-3 附條件核可）**：作廢列結算後，以「原本的 label＋作廢原因片段＋已作廢標示，不附實際結果」呈現。同一個決定適用 A-36 第 4 點的 on-demand 作廢列。條件如下：
>   1. 只適用於 A-27 (a)～(c) 沒有擋下的列。族群 (c) 成立時照樣不出現；大盤或個股在 `gated` 時照樣附 (e) PV-45。
>   2. **形狀**：
>      - label 只放在 `SettledRecordView.settled_record`；
>      - 同一物件帶 `settlement_date`（判定作廢的日期）和作廢的 `status`／`status_reason`；
>      - 不得出現 `realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`，也不得出現任何部分窗口的報酬；
>      - 不用天氣圖示，也不用方向色；
>      - 不進入 `current_outlook`、`plan` 兩類端點（A-74）。
>   3. **字面**：
>      - **LM-38 只能用在 `in_eligible_set = true` 的作廢列**，搭配 LM-109。
>      - E 以外的作廢列（逾時、on-demand、起算日前、PIT 違規）用不帶最壞情境子句的作廢變體，搭配 LM-110。變體由 creative-lead 起草、風控核可。
>      - 「原本的預測（已作廢）」的呈現框架，由 creative-lead 起草，和「已結算＋實際結果」片段同一批送風控逐字審。
>   4. `status_reason` 的每一個值（含 D-9.3 對齊事先宣告 v0.10 V10-03 後的第五值 `index_bar_confirmed_erroneous`）都要有核可片段。沒有核可片段的值，這類列一律不顯示 label。FL-52 的窮舉表要涵蓋 `status_reason` 的全部值。
>   5. 只要渲染了 LM-38 或 LM-109，最壞情境的結果就必須真的渲染。
>   6. **第 3、4 點的片段核可之前，採 fail-closed（不顯示 label），而且 FL-52 (d) 判定失敗。** 本核可只解決設計層，不會讓 D_v 提前。

**(2) A-65 中「作廢 outcome 依 A-62 R2」改為：**
> - 作廢 outcome 依 A-62 R2 第 1～6 點。
> - FL-59 的作廢 fixture 分成 E 內、E 外兩格：E 內選 LM-38＋LM-109；E 外選無 W 子句的變體＋LM-110。另斷言 E 外的格子不出現 LM-38。

**(3) D-7.8 第 8 點第 4 子點（A-36 第 4 點）中的作廢一行：**
- 原文：「outcome 為 `unresolvable_missing_data` 或 `excluded_corporate_action`（作廢）時，沒有實際結果可以並列。風控確認處理方式之前，不顯示 label，只顯示 `status_reason` 的既有片段。」
- 新文：
  > outcome 為作廢時，依 D-11.4 第 11 點 A-62 R2（風控 2026-10-17 C-3）。on-demand 紀錄一律不屬於 E，所以**不得用 LM-38**，改用不帶 W 子句的作廢變體＋LM-110。變體與「原本的預測（已作廢）」框架核可之前，不顯示 label，FL-52 (d) 失敗。

**(4) FL-52b (9e) 的「另加一格作廢 outcome：不出現 label（A-36 第 4 點）」改為：**
> 另加一格作廢 outcome：期望值依片段核可表決定。核可前不出現 label；核可後依 A-62 R2 第 2 點的形狀，而且不出現 LM-38。

### R3-8｜A-66（沒有歸屬的元件與 plan 欄位）

- 定位：A-66「市場總覽上的持倉表…（fail-closed）」一行之後加三點，並改寫 2a。
> - **沒有歸屬的頁面或元件**，不得渲染任何 `OutlookView` 衍生內容（label、天氣、方向色），也不得渲染 A-68 的適用欄位（`position_action`、`reasons`、`pending_triggers`、`add_conditions`、`entry_conditions`、`outlook_refs`）。
> - 首頁持倉表、摘要卡、風險儀表要顯示這類內容，必須先修訂本點、指定歸屬、送風控。
> - 回應中含 A-68 適用欄位的 route，`ENDPOINT_SURFACES` 的 kind 必須是 `plan`，而且 `SERVES ⊆ PLAN_OUTPUT_SURFACES`、`SERVES ⊇ 呼叫它的各元件的歸屬聯集`。
- 2a 新文（取代 A-66 對 2a 的改寫）：「不在本點清單內的頁面或元件，在清單修訂並送審之前，不得渲染展望 label、天氣、方向色，也不得渲染 A-68 的適用欄位。」
- **FL-60 加 (d)**：
  > - 前端元件列舉中，沒有歸屬的元件不得引用 `OutlookView` 衍生型別，也不得引用 A-68 欄位（型別或 AST 檢查）；
  > - 含 A-68 欄位的 route，kind 必須是 `plan`，而且兩個集合關係都成立。

### R3-9｜A-68（fail-closed 句）

- 定位：A-68「`alert`、`export` 移出的前提」一點之後加：
> - 把 `PLAN_OUTPUT_SURFACES` 改成三項的 PR，必須同時包含 FL-54 (h)，而且 CI 綠燈。
> - **前提未成立時 fail-closed**：D_v 前上述前提任一項未成立（包括契約測試尚未落地），`alert` 與 `export` 就留在 `PLAN_OUTPUT_SURFACES` 內，不得先行縮窄。
- 第二點和事先宣告 v0.10 D-20 ①（L963）的句子在實質字面上一致（風控項 5 要求對照）。
- A-68 的方向行改成和 V10-12 逐字相同（機械核對第 8 點）：
  > 放寬（展望可用性；只在優於基準且該格送審開放後才可能生效）＋收緊（輸出面）；v1 實效不變
- 註：r3 原文「展望可用性放寬（有條件，v1 實效不變）；輸出面收緊」不是逐字相同，所以一併更正。

### R3-10｜A-72（拒絕寫入時的 POST）

- 定位：A-72「G-7 新文」之後加：
> - **寫入被閘門拒絕時**（G-1～G-6 任一不成立）：
>   - `POST /api/outlook/symbols/{symbol}` 先評估閘門。拒絕時，不呼叫展望計算，也不計算、不回傳任何 label 或方向衍生欄位。
>   - 回應用封閉 schema `OnDemandGateClosedView`（`extra="forbid"`），HTTP 200。白名單只有：`symbol`、`trigger`（固定 `on_demand`）、`recorded`（固定 false）、`availability`（固定 `unavailable`）、`status_fragment_id`、`disclosure_fragment_ids`。不帶 `forecast_id`、`data_as_of`、`label`。
>   - 不得有任何 route 計算 on-demand 展望卻不經過寫入閘門（不得「算了但不落帳」）。kind 為 `on_demand` 的 route 都要呼叫同一個閘門函式（A-74）。
>   - **狀態字面**：建議新句，語意是「正式記錄開始前，臨時查詢不提供方向」，交 creative-lead 起草、風控逐字審。若改用既有片段，要先經風控單項確認。核可之前，FL-52 (d) 失敗。
> - **FL-38 加斷言**：拒絕寫入的回應要通過 `OnDemandGateClosedView` 的 schema 驗證，也要通過 FL-52b (9b) 的全文掃描；以 spy 斷言展望計算函式沒有被呼叫；route 列舉中所有 kind 為 `on_demand` 的 route 都經過閘門函式。

### R3-11｜A-77（整點取代）、A-75 增補、FL-19；與事先宣告的同一定義

**(1) A-77 新文（D-8.1 觀察日，整點取代 r3 A-77）：**
> 1. **定案後 session 集合 (i)**：有 ok bars run、而且該 run 的 `recorded_at ≥ final_after(TW, d)`（ADR-0028 CS-17）的 session d（A-78）。本 ADR 與事先宣告都只引用這一個定義，由 `app/data/session_calendar.py` 的單一函式提供。不得另寫時點比較。
> 2. **大盤定案列日期 (ii)**：大盤有 `is_final_bar` 列（A-75，排除示範資料）的日期，**扣除週末與已接入官方休市日表所列的休市日**。週末或官方休市日的大盤列，一律不得經 (ii) 成為觀察日。
> 3. **觀察日 ＝ (i) ∪〔(ii) − X2 確認日〕。** 不用週一至週五推定。
> 4. **X2 的單一定義在事先宣告 §6.3「大盤指數序列」第 2 點。** 本點只規定 X2 能用的輸入：
>    - X2 的對照日曆 ＝ 本點第 1 項的 (i)，加上正面休市證據（週末；已接入、而且 d 在其涵蓋範圍內的官方休市日表）。
>    - 不含任何指數 bar，也不含受檢的那根 bar；不讀本點第 3 項的觀察日，也不讀 ADR-0028 `ObservedSessionCalendar`。
>    - 官方休市日表的接入屬於 ADR 決策（事先宣告 §9.3 第 18 點 (e)、(i)）；接入之前，正面證據只有週末。
> 5. **X2 確認的必要條件含 d ∉ (i)**〔超出底線，待風控單項確認〕。d ∈ (i)、又有正面休市證據時，屬於證據矛盾，一律維持異常待查證，不論獨立來源的結果如何。這時 d 仍經 (i) 是觀察日。
>    - 記 WARNING，寫入 `forecast_ledger_events.kind = session_calendar_conflict`，交 data-engineer 查根因。
>    - 要改變這類日期的處理，須修訂本點並送風控。
>    - 有了這一條，「(ii) 扣除 X2 確認日」就等於「從觀察日移除 X2 確認日」。
> 6. **平日 d 只出現在 (ii)、不在 (i)**（例如自己的排程停擺，或只有定案前的 run）：X2 只有 (iii) 成立，不得直接確認，列為異常待查證，查證路徑依事先宣告 §6.3「查證程序」。待查證期間 d 照常是觀察日。
> 7. **X2 確認的登記**：只增不改，寫入 `forecast_ledger_events.kind = x2_confirmed_non_session`，欄位是 `session_date`、`basis ∈ {direct, verified}`、查證紀錄的參照。觀察日在查詢時排除這些日期。已寫入、日期是 d 的 `forecast_gaps` 等紀錄不刪不改，查詢時一併排除（回覆事先宣告 §9.3 第 18 點 (i) 的註記方式）。
> 8. **順延的稽核欄位**（對應事先宣告 R-C）：每一筆順延的結算列，以及結算後才確認、以 supersede 新增的列，`forecast_outcome` 都要帶 `x2_shift_json = {original_t_plus_h, removed_dates, shifted_t_plus_h, x2_event_ids}`，可為 null，只增不改。
> 9. **F-8（凍結前，待 data-engineer 查證）**：「週末」作為正面休市證據，前提是前瞻期與重放期都沒有週末交易日。
>    - 查證若發現週末交易日：官方日曆列為交易日的週末，不構成正面休市證據；官方表沒有涵蓋的期間，週末的大盤列只能列為異常待查證。這時第 2 項「週末一律不得經 (ii) 成為觀察日」的週末部分要和事先宣告同批修訂，並送風控。
>    - 查證若沒有發現：把查證依據與涵蓋期間寫進本點與事先宣告。
> 10. 平日既不是觀察日、也不是官方休市日時，記 WARNING（沿用 r3）。
> 11. 觀察日集合可能因為後來的 X2 確認而回溯縮小。已寫入的 snapshot 不改；之後的 snapshot（含 F-3 逾時率的 60 日窗）用新集合。結算端依事先宣告 §6.4 supersede。

**(2) A-75 增補（候選 T）：**
- 「候選 T 必須同時滿足」改為四項：
> - (i) A-78 的 run 下限，也就是 T ∈ D-8.1 (i)；
> - (ii) 大盤 T 日 bar 是定案列；
> - (iii) **T 不是 X2 確認日**；
> - (iv) T 不是週末，也不是已接入官方休市日表所列的休市日〔超出底線，收緊〕。
> - (iii) 或 (iv) 不成立 → 該 session 記 `inputs_not_ready`，(iv) 另記 WARNING。依 A-77 第 5 項，(iii) 在結構上不會成立；保留它是縱深防禦，以測試斷言。

**(3) FL-19 增補（fixture）：**
> - (a) 週末的定案大盤列不成為觀察日（R3-11、R-B 指定）；
> - (b) 平日只有定案前 ok run、有定案大盤列 → X2 列為異常待查證，d 仍是觀察日；
> - (c) 週末只有定案前 ok run、有大盤列 → X2 直接確認，d 不是觀察日，T+h 順延，`x2_shift_json` 齊全；
> - (d) 週末 d ∈ (i) → 證據矛盾、維持待查證、d 經 (i) 是觀察日、寫入 `session_calendar_conflict`；
> - (e) 候選 T 是 X2 確認日，或是週末 → `inputs_not_ready`，不退回前一個 session；
> - (f) 官方休市日表尚未接入時，平日的官方休市日只有 (iii) 成立 → 列待查證；
> - (g) X2 判定函式的簽章不接受觀察日集合，也不接受任何指數 bar 序列（和事先宣告 LG-25 (f) 對齊）。
- 原有三個 fixture（示範列、暫定列、定案前的 run）保留。

**(4) 同批落地：**
- ADR-0027 的 r3／r3′ 套用，和事先宣告 v0.10（含 R-A～R-C）在同一批交付。
- coordinator 機械核對第 11 點：雙方 X2 的「市場 DB」一律指 D-8.1 (i)；觀察日公式只寫在 ADR D-8.1，事先宣告只引用條號，不寫行號。
- 兩份都核可後才各自 commit，次序由 coordinator 排定，但不得只落地其中一份。

### R3-12｜方向標示

- A-71：「補定義（兩面；依風控顯示面確認 (d)）」。
- A-73：「補定義（兩面）」。
- A-58：「不變＋收緊」。
- 統計見第四節。

### R3-13｜A-54 加註

- A-54 末尾加：
> 顯示面確認 (e) 第 1 點由 LM-86＋LM-94／LM-95 滿足（風控 r3 審查 C-2）。(e) 第 2～4 點（不做視覺連結、揭露放在 plan 卡內不收合、375 寬度驗收）由 PM、frontend-engineer、qa-e2e 承接，仍是 required。

### 收尾：A-79、A-84、待決事項

**A-79：**
- r3 提案第五節「CEO 白話說明」整節由風控 r3 審查第三節（7 點）取代。
- Consequences 在 r3 新增的四點之外，再加四點：
  - 正式記錄前，臨時查詢不給方向，也不會「算了不記帳」（R3-10）；
  - 族群可能重新隱藏方向（R3-6）；
  - #10 不能關掉固定閘門。沒有回放報告的 scope 常駐 `gated`；個股與族群若沒有回放計畫，A-63 第 5 項要在 D_v 前核可（R3-2）；
  - 觀察日可能因為 X2 回溯縮小（R3-11）。
- 待決事項：
  - creative-lead 加四項：A-63 第 5 項（含族群變體）；無 W 子句的作廢變體；「原本的預測（已作廢）」框架；R3-10 狀態句。
  - quant 加兩項：大盤與個股的 `forward_n_below_min` 是否有登記門檻；R3-6 的揭露項。
  - data-engineer 加一項：F-8，以及 `session_calendar_conflict` 的根因流程。

**A-84：** ADR-0028 已在 commit 1d69acd 落地（CS-12 L301；修訂紀錄 L574）。r3′ 註記「A-84 已落地，不重複插入」。

**仍未處理、不在本次範圍：** D-9.3／FL-22 對齊第五個 `status_reason` 值（事先宣告 §9.3 第 18 點 (b)）。FL-22 現行寫「四值」，和事先宣告的五值不一致，要另外開一次提案。R3-7 第 4 點已經先讓第五值 fail-closed。

## 三、suggested 採用表

| # | 採用 | 條文（定位） | 方向 |
|---|---|---|---|
| S-1 | 採用 | A-85 的 D-9.3「指數序列見附件 B-6」改為「`split_or_reduction_suspected` 不套用於大盤指數序列（事先宣告 v0.10 V10-01）」，取代 r3 的「由 quant 登記（建議…）」 | 不變（引用已登記的定義） |
| S-2 | 採用 | A-85 的 D-4 第 7 點「見附件 B-7」改為「B4『該股所屬族群』以 T−h 的 PIT classification 快照判定，也就是建立 S_{T−h} 的同一份快照（事先宣告 v0.10 V10-05）」，取代 r3 的「由 quant 登記」 | 不變 |
| S-3 | 採用 | D-11.4 (d′)「這句只是語意，逐字字面待風控核可（A-36 第 2 點）」改為「逐字字面為 LM-106；守門 R1、R2 見 A-62」。D-7.8 第 8 點第 2 子點的「這句只是語意，不是已核可的字面。」刪除，次行依 A-85 改為 LM-106 的引用（兩條合併套用） | 不變 |
| S-4 | 採用 | A-65 加：「(e) PV-45（大盤或個股 `gated` 時）與 PA-4（依既有規則）照樣適用於已結算的排程列」 | 不變（明列既有規則） |
| S-5 | 併入 R3-11 | A-75 (iii) | 收緊 |
| S-6 | 採用 | A-60 加：「驗證狀態頁揭露清單沒有回傳的更正列筆數。字面交 creative-lead 起草、風控審；上線條件同 LM-107，不列為 D_v 的前提」 | 收緊（揭露） |

## 四、方向統計（R3-12）

| 方向 | 條數 | 條號 |
|---|---|---|
| 收緊 | 20 | A-54～A-57、A-60～A-67、A-69、A-70、A-72、A-74～A-78 |
| 補定義（兩面） | 2 | A-71、A-73 |
| 不變 | 9 | A-59、A-79～A-86 |
| 不變＋收緊 | 1 | A-58 |
| 有條件放寬＋收緊 | 1 | A-68 |

- 合計 20＋2＋9＋1＋1＝33。
- r3′ 的補正都掛在原條上，沒有改變任何一條的類別。
- A-77 相對 r3 原文只會減少觀察日，或維持不變，所以維持「收緊」。它的第 5 項相對事先宣告是兩面，見第五節。
- 待風控裁定：A-62 在 R3-7 之後含一面「有條件放寬（C-3）」。如果要改標「收緊＋有條件放寬」，統計會變成 19／2／9／1／1＋1。

## 五、與事先宣告 X2 的差異（供 quant 對齊）

風控項 7 判定「不一致」，現況以 quant 的工作樹為準。

| # | 位置 | quant 現行文字 | ADR r3′ | 要 quant 做的事 |
|---|---|---|---|---|
| 1 | L1118 (iii) 與「只用市場 DB 的 ok session 集合」；L1123 三處；L1143；L74；L1382 (i)；L1383 ③ | 「市場 DB 在 d 有／沒有 ok（bars 的）session」 | D-8.1 (i)：有 `recorded_at ≥ final_after(TW, d)` 的 ok bars run | 依風控 R-A 改字（quant 已在改） |
| 2 | L1123 查證、L1138「從觀察交易日中移除」 | 證據矛盾（d ∈ (i)＋週末或休市）可以經獨立來源確認，之後從觀察日移除 | A-77 第 5 項：d ∈ (i) 時永遠不確認，維持待查證，d 經 (i) 是觀察日 | **待風控單項確認。** 若風控採我的寫法，quant 在 L1123 加「d 在 D-8.1 (i) 時不得確認，見 ADR-0027 A-77 第 5 項」；若風控改採 ((i) ∪ (ii)) − X2，ADR 改寫 A-77 第 3 項 |
| 3 | L1123「待查證期間…照常算觀察交易日」 | 不分平日週末 | 只有 d ∈ (i)，或 d 是平日而且不是官方休市日時，才是觀察日 | 改成引用 D-8.1；做完第 1 項後，實際上已經一致 |
| 4 | L1138 引用方式 | 「ADR-0027 D-8.1 的聯集排除 d」 | 公式只在 D-8.1；X2 只在 §6.3 | 改成「依 ADR-0027 D-8.1（A-77 第 3 項），d 不再是觀察日」；不寫行號 |
| 5 | R-C 的逐列四欄 | 欄位名稱未定 | `forecast_outcome.x2_shift_json` | 引用欄位名稱 |
| 6 | §9.3 第 18 點 (i) 的註記方式 | 交 TA 決定 | `forecast_ledger_events.kind = x2_confirmed_non_session`，查詢時排除 | 引用 |
| 7 | F-8 | 凍結前，§9.5 ④ | A-77 第 9 項，採同一處理 | 查證後兩邊同批修訂 |
| 8 | LG-25 (f) | R-A 要求加兩個定案前 run 的 fixture | FL-19 (b)、(c) 是同樣的情境 | 兩邊的 fixture 名稱對照 |

R3-9 的 fail-closed 句和 L963 實質一致；ADR 多了「改三項的 PR 須含 FL-54 (h)」，這是實作規則，quant 不必跟著改。

## 六、PM 的兩個問題（ADR-0028）

### (a) CS-4 與 `date_anomaly` 的 bar 進入關鍵價位、行動計畫

**結論：CS-4 的意思是「狀態只用於顯示，不得成為計算的切換條件」。它不是「其他區塊遇到異常可以不標示」。** 行動計畫和關鍵價位要分開看。

**行動計畫（ADR-0027 的鏈）不會默默吃進異常 bar。**
- 它讀市場 DB 的 PIT 視圖，大盤 T 日 bar 要經 `is_final_bar`（A-75、A-76）。
- 對估值價格，FL-25 要求市場 DB 的原始收盤[T] 等於估值所用的價格與日期；不一致時價位缺席，附 `E-PRICE-UNUSABLE`。
- 〔推論〕`date_anomaly` 的 `price_date` 幾乎都不等於 T：`future_date`、`before_open` 不可能等於 T；`not_a_session`、`unconfirmed_session` 只有在市場 DB 也在非交易日有 session 時才可能相等，而那屬於 A-77 第 5 項的矛盾路徑。所以實際上會落到「缺席＋原因」。

**關鍵價位有缺口。**
- 〔事實〕現行 `KeyLevelsPanel` 由前端 `computeKeyLevels(bars.data.bars, …)` 在 `/api/bars` 的日線上計算（`apps/stock-desk/frontend/app/position/[symbol]/page.tsx` L138-139）。
- 頁面上只有「資料截至 {MM-DD}」徽章（L271-273），所以異常 bar 會進入計算，也沒有異常標示。
- 這不是 CS-4 的設計目的。

**建議（ADR-0028 新增 A-96，待 PM 與風控確認）：**
> - **D-6 加第 13 點**（揭露既有限制）：個股詳細頁的關鍵價位，在前端以 `/api/bars` 的日線計算，不讀 `valuation_state`。資料列有日期異常時，照樣進入計算。
> - **CS-4 加一句**（澄清，方向不變）：CS-4 只約束列出的後端計算模組。前端顯示層可以讀 `valuation_state`，但只能用來做同區塊揭露，不得改變任何計算或計算的輸入。
> - **CS-26**（收緊）：個股詳細頁的持股價格區塊，`valuation_state = date_anomaly` 時渲染 LM-70（PM AC-B5a-10）。關鍵價位區塊同時渲染一句指向該異常的揭露，字面交 creative-lead 起草、風控逐字審；計算不變。
> - 要不要在資料層剔除異常列，屬於 D-6 第 10 點「寫入側品質閘門另案」，本條不處理。
- 方向：不變（D-6 第 13 點、CS-4 澄清）＋收緊（CS-26 揭露）。

### (b) 個股詳細頁的價格是否和庫存頁共用同一個估值狀態元件

**〔事實〕現在沒有共用。**
- 估值字面模組 `valuationWording`／`valuationBasis` 只被 `PositionsTable.tsx`、`SummaryCards.tsx` 引用；`position/[symbol]/` 底下沒有任何檔案讀 valuation 或估值狀態。
- 個股頁的價格日期來自 advice、signals、bars 各自的 `last_bar_date` 徽章。
- ADR-0028 沒有規定個股頁要怎麼呈現。

**建議（ADR-0028 新增 A-97）：**
> - **CS-27**：個股詳細頁顯示的持股價格與估值狀態，取自 `build_summary` 同一列的輸出（`valuation_state`，以及同一個 `price_date`），以和庫存頁同一個前端狀態元件、同一張 D-5 對應表呈現。
>   - 個股頁不得另外計算狀態，也不得用 bars 的 `last_bar_date` 代替 `reference_date`。
>   - 前端契約測試：同一檔在兩頁的價格、日期、字面 ID 逐位相同（PV-52、AC-B5a-10）。
>   - 不是持股的標的（沒有 `build_summary` 列）不顯示估值狀態，維持現行徽章。
- 方向：收緊。
- 要排入 T1-17 的範圍，交 frontend-engineer。
- A-96、A-97 都牽涉風控，建議和 PM 的 AC-B5a-7～12 同一批送風控。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3提案審查-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-A-15-事先宣告v0.10修正單項確認含R3-11一致性-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md（D-7.3 L334、D-7.8 第 8 點 L347-391、D-8.1 L395、D-11.4 L482-581、D-14 L699-719、FL-19 L808、FL-52 L876-905）
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md（D-4 L121-156、D-6 L197-209、CS-4 L288、CS-12 L297-303、修訂紀錄 L574）
- /home/user/AICompany/docs/adr/0025-stock-desk-產品定位改為提供投資建議.md（D-6.6 L412-414）
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md（L963、L1118、L1123、L1138-1144、L1382-1383）
- /home/user/AICompany/work/reviews/2026-10-17-A-15-事先宣告v0.10風控required修正-quant回報.md
- /home/user/AICompany/work/reviews/2026-10-17-LM70但書PM側確認-product-manager.md
- /home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md（2.24 節 L1888-1902；LM-97、LM-98 L2509-2510）
- /home/user/AICompany/apps/stock-desk/frontend/app/position/[symbol]/page.tsx（L138-139、L271-273）

這是唯讀的架構文件，Codex 不適用。

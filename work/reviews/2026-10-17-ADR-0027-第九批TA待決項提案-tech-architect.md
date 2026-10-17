# ADR-0027 第九批衍生待決項提案 1～5（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# ADR-0027 第九批 TA 待決項提案（tech-architect，唯讀）

## 一、本次結論

依 coordinator 指示，本份以風控第九批**最終版**（`work/reviews/2026-10-17-新定位第九批字面逐字審最終版-納入quant回答-風控.md`）為準；前一份已被取代，不再引用。基準條文是「r3＋r3′＋r3″＋增補＋RC‴-1～RC‴-4 套用後」的 ADR-0027。所有條文都掛在既有 A 號下，沒有新增 A 號，方向統計維持 19／2／9／1／2。

1. **FL-52「恰好一個」**：同意風控的傾向，{fwd} 選 LM-12，其餘子集選 LM-120。另外加一個收緊條件：LM-12 只在 `display_state = gated` 時可選。在 `suspended_f3`／`withdrawn_f2` 時，即使 G_eff＝{fwd}，也改用 LM-120 並列 LM-76／LM-81，否則和 T-3 (1) 衝突。selector 簽章要改成帶 `display_state`、`n_masked`。T-2 登記整段改寫：刪 LM-34、LM-73，登記 LM-127／LM-126，並把 LM-144 原子登記在 `record_list`、`sector_cell`、`sector_detail`。
2. **LM-32 的 n 和閘門是同一來源**，所以徽章要一併遮。遮法是用封閉 schema `ValidationBadgeMasked`，不帶任何 n 衍生值，也不帶狀態片段 ID。同一個判定函式 `n_disclosure_masked` 同時供 selector 與徽章使用。有兩點要風控裁定：LM-31 頁尾引用「各展望旁的驗證徽章」的問題，以及 `withdrawn_at_n` 這類歷史 n 要不要遮。
3. **N-1**：提出甲、乙、丙三案，**推薦甲「X2 確認優先、固定排除」**。甲案不寫入、不修改任何已寫入的事件或 `x2_shift_json`，衝突永不由程式解除。
4. **`forecast_record` 的 supersede 不會改變 E，也不會改變 n**，所以不必另設序號。但現行條文有一個漏洞：`pit_violation_confirmed` 若指向更正列，原始列會留在 E 裡。我補了四條寫入／讀取約束把這點堵住。
5. **`band_def`**：明訂 `up_pct`／`down_pct` 單位是比值，不改名，加寫入驗證。顯示字串由後端單一函式產生：精確 Decimal ×100、兩位小數、遠離零。view 不回傳原始比值。LM-146、LM-92、LM-147、LM-148 的片段 ID 由後端決定。

## 二、逐項提案

### 提案 1｜A-63 第 11 點（T-2）整段改寫；FL-52 擴充｜方向：收緊

**不同意之處：沒有。只補一個條件。** 加 `display_state = gated` 的理由是：T-3 (1) 已規定 claim 層在 `suspended_f3`／`withdrawn_f2`、而且 G_eff 非空時，要呈現 LM-76／LM-81＋LM-120。如果 G_eff＝{fwd} 時改選 LM-12，同一格就會有兩個項目。而且 LM-12 的「暫」是在 gated 的前提下才核可的。

**比較的方案**
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A（採用）：{fwd}＋gated 選 LM-12，其餘選 LM-120 | 照風控傾向；保留 LM-12 的「需要 {n_min}」資訊 | 兩套字面並存，selector 要多一個維度 | 低，FL-52 逐格斷言 |
| B：撤回 LM-12 在 `outlook_block` 的登記，全部改用 LM-120＋LM-128 | 只有一套組合規則，和 R9-04 的族群處理對稱 | 失去門檻數字；推翻第八批裁定 | 低，但要風控改裁 |
| C：依 scope 分（大盤選 LM-12、個股選 LM-120） | 無 | 沒有實質理由 | 中，規則任意 |

**條文（取代 T-2 的「LM-12、LM-34、LM-73、LM-98 登記為…」這一子點，以及 T-2 的 FL-52 斷言子點）**
> - 上述位置的 gate 片段 ID，只能由 `select_gate_fragments(scope_kind, slot, G_eff, display_state, n_masked)` 產生（取代 `(scope_kind, slot, G_eff, e_changed_since)`）。`n_masked` 只能由 `views.n_disclosure_masked(...)` 產生（A-63 RC′-2，見提案 2），不得由呼叫端自行計算。
> - **閘門片段登記 `GATE_FRAGMENT_REGISTRY`**：封閉登記，放在 `display.py`。要增列，須修訂本點並送風控。
>   - **原子片段**：只能代入組合句，本身不是 slot 項目。
>     - LM-128：`covers = {forward_n_below_min}`，scope 為 market、symbol。只在 quant 登記了該 scope 的前瞻門檻時，才進入 P(scope)。
>     - LM-129：`covers = {forward_n_below_min}`，scope 為 sector，限 `n_masked = false`。
>     - LM-144：`covers = {forward_n_below_min}`，scope 為 sector，限 `n_masked = true`。LM-129 與 LM-144 互斥，GR 順序都排第一。
>     - LM-130：`covers = {replay_review_pending}`，各 scope 都可用。
>   - **slot 項目**：
>     - `outlook_block`（market、symbol）：
>       - LM-12：只在 G_eff ＝ {`forward_n_below_min`}，**而且** `display_state = gated` 時選用。
>       - LM-120（`{G 並列}` 取 LM-128、LM-130，依 GR 組裝）：用於其餘所有非空子集。`display_state ∈ {suspended_f3, withdrawn_f2}` 時一律用 LM-120（含 G_eff ＝ {fwd}），並與 LM-76／LM-81 並列（A-63 第 12 點 (1)）。
>     - `record_list_header`（market、symbol）：只用 LM-120，不登記 LM-12。
>     - `plan_reason`（symbol）：LM-98 {fwd}、LM-124 {replay}、LM-125 {fwd, replay}，不變。
>     - `sector_cell`、`sector_detail`（sector）：k＝1 用 LM-127，`{G 單項}` ∈ {LM-129 或 LM-144, LM-130}；k≥2 用 LM-126。
>     - `record_list`（sector）：k＝1 用 LM-122，k≥2 用 LM-123，原子選法同上。
>     - 其餘 (scope_kind, slot) 的現行登記不變。
>   - **LM-34、LM-73 撤回**（風控第九批 R9-04）：不得出現在登記、常數、測試或 golden。
> - **FL-52 擴充**：
>   - 列舉範圍：每一個已登記的 (scope_kind, slot) × `display_state` ∈ {`gated`, `suspended_f3`, `withdrawn_f2`} × P(scope) 的每一個非空子集；族群另外 × `n_masked` ∈ {真, 假}。
>   - 每一格都恰好選出一個 slot 項目，而且 `covers` 聯集等於該子集。
>   - 斷言：
>     - (1) `outlook_block`、G_eff＝{fwd}、`gated` → 選 LM-12，不選 LM-120；
>     - (2) 同上但 `suspended_f3`／`withdrawn_f2` → 選 LM-120，不選 LM-12；
>     - (3) \|G_eff\|≥2 時，任何 slot 都選不到 LM-12；
>     - (4) quant 沒有登記前瞻門檻的 scope，LM-12 與 LM-128 都選不到；
>     - (5) 族群 `n_masked = true` 時選不到 LM-129，渲染全文不含該 claim 的 n 字串；
>     - (6) 登記內沒有 LM-34、LM-73。
>   - 原文「R-6 片段核可之前，這種情形 fail-closed」刪除，改為「這種情形選 LM-144」。

- 對風控 LM-144 ④「渲染出的全文不含數字」的讀法：LM-126、LM-127 的字面本身含「5 個交易日」，所以「全文不含任何數字」無法成立。我把它讀成兩件事：一是全文不含該 claim 的 n 值，二是 LM-144 片段本身不含數字。**這個讀法需要風控確認。**
- `apps/` 下 grep `select_gate_fragments`、`GATE_SLOT_SCOPES`、`OUTLOOK_HIDDEN_UNVERIFIED_TEMPLATE`，命中都是 0，所以改簽章沒有落地成本。

### 提案 2｜LM-144 ③／④：徽章同源遮蔽｜掛 A-63（RC′-2 子點，並引用 A-57 (iv)）｜方向：收緊

**確認：同源。**
- n 是 `forecast_validation_snapshot.n`，寫入 snapshot 時就定下（D-11.4 第 2 點，ADR L467）。
- 閘門判定讀「判定 `display_state` 的同一列最新 daily snapshot」（A-63 (c)，r3″）。
- LM-32 的條件是「n 為不重疊計數，與閘門同一種」。
- 不過 ADR 原文沒有明定徽章讀哪一列，下面第一條把它釘死。〔推論：現況沒有寫明，不是已知的不一致〕

**徽章遮法的比較**
| 方案 | 優點 | 缺點 | 風險 |
|---|---|---|---|
| A（採用）：整顆徽章改成封閉的遮蔽 schema，不帶數值、不帶狀態詞 | fail-closed；不需要新字面 | 頁面上沒有徽章，LM-31「各展望旁的驗證徽章」會局部落空 | 低（見待裁 a） |
| B：只省略數字行，保留狀態詞 | 保留狀態 | 狀態也來自可能落後的 snapshot；LM-03 本身含 n，沒有不含 n 的已核可「未驗證」字面 | 中 |
| C：徽章裡改放 LM-144 | 有可見說明 | LM-144 沒登記 `validation_badge` slot，要新核可 | 要送審 |

**條文**
> - **`n_disclosure_masked(claim, snapshot, e_changed_since) -> bool`**：放在 `views`，是唯一的判定函式。為真，若且唯若 `scope_kind = sector`，而且〔沒有 daily snapshot，或 `e_changed_since(snapshot)` 為真〕。gate selector、驗證徽章，以及任何帶該 claim n 的片段，都呼叫這個函式。`e_changed_since` 不按 claim 篩選，所以同一個回應裡的族群 claim 會一起遮蔽。
> - **徽章資料來源**：LM-03、LM-32、LM-33 的 `{n}`、`{k}`、`{k_i}`、`{n_eff}`、`{lo}`／`{hi}`、`{lo_i}`／`{hi_i}`、`{起}～{迄}`，以及徽章的狀態，一律取判定 `display_state` 的同一列最新 daily snapshot（與 A-63 (c)、A-57 (iv) 同一列），不得另查，也不得跨列混用。
> - **遮蔽時的回應**：`n_disclosure_masked` 為真時，該 claim 的徽章在這次回應中是 `ValidationBadgeMasked{claim_id, masked: true, mask_reason ∈ {e_changed_since, no_daily_snapshot}}`，封閉 schema，`extra="forbid"`。
>   - 不帶上一條列出的任何數值；
>   - 不帶 LM-03、LM-04、LM-32、LM-33 的片段 ID；
>   - 前端不渲染徽章的狀態詞與數字行；
>   - 同一區塊經 LM-122／LM-123／LM-126／LM-127 代入 LM-144，交代筆數待彙整。
> - 整個回應（JSON 與渲染結果）都不得含該 claim 的 snapshot n 及其衍生值（API 本身就是顯示面）。
> - **FL-52／FL-59 加格**：族群 × {`e_changed_since` 為真, 沒有 snapshot}：
>   - 徽章通過 `ValidationBadgeMasked` 的 schema 驗證；
>   - 回應裡找不到 LM-03、LM-04、LM-32、LM-33 的 ID；
>   - 全文掃描找不到 n 的字串；
>   - `n_masked = false` 時，徽章照常渲染。

**要風控裁定的兩點：**
- (a) **LM-31 的問題**：遮蔽時頁面上沒有族群的徽章，LM-31「以各展望旁的驗證徽章為準」會局部落空。D_v 前族群可能根本沒有 snapshot，所以上線初期遮蔽反而是常態。兩個選項：接受現狀；或請 creative-lead 起草不含 n 的徽章變體（語意例如「驗證狀態待彙整」），在族群頁上線前核可。我傾向後者，但不擋 D_v。
- (b) **歷史 n 要不要遮**：`withdrawn_at_n`、`checkpoint_n`（LM-75、LM-79、LM-81、LM-104 的 `{X0}`／`{X}`）是下架事件當時記下的值，不是 claim 的現值 n。我建議**不遮**，理由是：遮掉就無法渲染下架告知，等於隱藏負面資訊。若風控認為也屬「該 claim 的 n」，這類告知句要另送不含 n 的變體。
- 知會：大盤與個股不適用 `e_changed_since`，snapshot 的 n 在 E 變動事件之後、下一筆 snapshot 之前會落後。這是既有設計，本次不提案。

### 提案 3｜N-1 處理提案｜掛 A-77 第 12 項（連帶第 3、11 項與 A-75 註記）

**情境**：X2 確認時 d ∉ (i)（第 5 項）。之後 d 出現定案後的 ok run，進入 (i)。依現行第 3 項「(i) ∪〔(ii) − X2〕」，d 會自動回到觀察日，和已寫入的 X2 事件、`x2_shift_json` 矛盾。

| 方案 | 內容 | 優點 | 缺點／風險 |
|---|---|---|---|
| **甲（推薦）X2 確認優先、固定排除** | 第 3 項改為〔(i) ∪ (ii)〕− X2。確認之後 d 不回到觀察日；不動任何紀錄；衝突持續揭露；只能修訂條文來解除 | 不新增寫入路徑；沒有第二次翻案（不觸發新的 R-7）；確認當下和現行公式等價；可測 | **兩面**：d 若其實是交易日，受影響紀錄的 T+h 會多跨一個實際交易日，偏差留在統計中，直到人工修訂為止。以揭露與 F-8 查證緩解 |
| 乙 (i) 優先、自動回復 | d 回到觀察日，並自動依 §6.4 supersede 回原本的 T+h | 定義最忠實（如果 d 真的是交易日） | 自動調整已寫入的結果；產生翻案鏈（R-7）；X2 事件仍然矛盾；違反「不得以程式自動解除」，除非另立撤回事件與核可流程 |
| 丙 隔離 | 新增 F-3 類暫停原因 `session_calendar_conflict`，受影響 claim 暫停到根因核可為止 | 對畫面最保守 | 要修改事先宣告 F-3 的列舉與上限登記；一次資料作業失誤就會讓大盤 claim 暫停；牽動面大 |

**甲的條文**
> - **A-77 第 3 項改為**：觀察日 ＝〔(i) ∪ (ii)〕− X2 確認日。
>   - 第 1 項的 (i) 本身不扣除 X2 確認日。X2 判定（第 4、5 項）、第 12 項的偵測、A-75 (i)，都讀未扣除的 (i)。
>   - 單一函式：未扣除的 (i) 由 `session_calendar.py` 的 `final_sessions()` 提供，觀察日由 `observed_sessions()` 提供，兩者不得混用。
>   - 依第 5 項，X2 確認當下 d ∉ (i)，所以新公式在確認當下和原公式相同，只在第 12 項的情形下不同。
> - **A-77 第 12 項「觀察日身分怎麼處理」整點取代**（RC‴-3 的偵測條文不動）：
>   - **X2 確認優先，固定排除**：d 一經 `x2_confirmed_non_session` 確認，就不再是觀察日；之後 d 進入 (i)，也不改變這一點。
>   - 不新增、不修改任何事件。`x2_confirmed_non_session`、`x2_shift_json`，以及已順延或已 supersede 的 outcome，一律不動；不因此觸發 §6.4 更正作業；不寫任何撤回類事件。
>   - `session_calendar_conflict`（`origin = post_x2_final_run`）寫入後，程式不得把它標為已解決，也不得因時間經過、run 數或查證結果解除。§4.2 依 origin 分列，持續揭露。
>   - §4.2 另外揭露「`x2_event_ids` 含該 X2 事件的 outcome 筆數」。這個數字由 `x2_shift_json` 逐列數出，不另存欄位。
>   - 根因由 data-engineer 查證（沿用 A-79 待決事項的 `session_calendar_conflict` 根因流程）。任何改變 d 的身分、或回復原 T+h 的做法，都只能修訂本項並送風控，不得由程式或操作者逕行處理。
>   - **下游一致**：
>     - 缺日稽核不對 d 補寫缺日列；
>     - F-3 逾時率的 60 日窗不含 d；
>     - 結算窗計數不含 d；
>     - A-75 (iii) 因此可能成立（T＝d 時記 `inputs_not_ready`，不退回前一個 session）。A-75 原註「(iii) 在結構上不會成立」改為「只在 A-77 第 12 項的情形下成立」。
> - **第 11 項句尾加**：「觀察日集合不因第 12 項的情形而回復。」
> - **FL-19 加 (h)**：X2 確認之後，注入 d 的定案後 ok run。
>   - (h1) d 不是觀察日；
>   - (h2) 只寫一筆 `session_calendar_conflict`，payload 帶 `x2_event_id` 與最小的 `run_id`；重跑偵測不重複寫入；
>   - (h3) X2 事件、`x2_shift_json`、`forecast_outcome` 的列數與內容，前後雜湊逐位相同；
>   - (h4) 不產生 `correction_job_id`；
>   - (h5) 候選 T＝d → `inputs_not_ready`；
>   - (h6) direct 與 verified 各一格。

- **方向**：
  - 相對套用後的條文，觀察日只減不增，也沒有新增寫入路徑 → **收緊**。A-77 的類別維持「收緊」。
  - 但「定義忠實度」是兩面的（見表內甲的缺點），已照實揭露。**請風控確認歸類。**
- **連帶**：quant 的 v0.11 §9.2 N-1（L1399-1402）照 Q-3 保留的揭露句「d 會自動回到觀察日」，在甲案下不實，要改成「d 不回到觀察日（ADR-0027 A-77 第 3 項）」。
- 〔推論，非本提案範圍〕個股序列若在 d 有 bar，σ_d 的窗會把 d 算進去。特徵窗要不要排除 X2 確認日，交 quant 判斷，不擋 D_v。

### 提案 4｜`forecast_record` 的 supersede 與 E／n｜掛 A-63（RC′-2 子點）｜方向：不變（明確化）＋收緊（寫入驗證）

**結論：不會改變 E，也不會改變 n。**
- E 只取 `forecast_record.supersedes_id IS NULL` 的原始列（D-11.1，ADR L459-460）。
- 原始列只增不改，有了更正列也不會離開 E；更正列本身永遠不屬於 E。
- 預測端一律用原始列（D-9.5、事先宣告 §6.4 L1213-1216）。
- 所以 ULID 不單調不影響判定，不必另設序號。

| 方案 | 優點 | 缺點 |
|---|---|---|
| A（採用）：釘住不變式，加寫入驗證與測試 | 沒有新的表或欄位 | 日後若改語意，要記得修訂（已列為失效條件） |
| B：另設 AUTOINCREMENT 更正序號，納入 RC′-2 | 防禦性 | 會讓 `e_changed_since` 在不改變 E 的事件上為真，族群多 fail-closed；多一張表 |
| C：每次更正寫一筆中性 ledger 事件 | 稽核性 | 多一條寫入路徑；中性分類要另外維護 |

**條文**
> - `forecast_record` 的更正不改變 E 的成員，也不改變 n，所以不列入 `e_changed_since` 的判定，不另設序號。為使這一點成立，加四條約束：
>   1. `forecast_outcome.forecast_id` 必須指向 `supersedes_id IS NULL` 的 `forecast_record`，由寫入函式驗證，不成立就拒絕寫入。更正列不結算。
>   2. 結算與 validation 讀 `label`、`band_def`、`base_close`、`baseline_predictions_json` 時，一律取更正鏈的根，也就是原始列。
>   3. `pit_violation_confirmed` 的 `payload.forecast_id` 必須是原始列，由寫入函式驗證；否則 E 的排除條件會漏掉原始列。
>   4. `forecast_record` 的更正路徑不得寫入 `forecast_outcome`，也不得觸發 §6.4 結算端更正作業。
> - **失效條件**：日後若要讓 `forecast_record` 的更正影響 E 或 n，須修訂 RC′-2，另設 `INTEGER PRIMARY KEY AUTOINCREMENT` 的更正序號，並納入 `e_changed_since`。
> - **FL-49 加三格**：
>   - 對 E 內的原始列寫一筆更正 → E 的成員、n、`e_changed_since` 逐位不變；
>   - outcome 指向更正列 → 拒絕寫入；
>   - `pit_violation_confirmed` 指向更正列 → 拒絕寫入。

### 提案 5｜`band_def` 單位與顯示字串介面｜掛 A-65（與 T-4 同條）｜方向：收緊

比較過的替代方案：
- 欄位改名為 `up_ratio`：會破壞和事先宣告 L1083 名稱的 V-7 對齊，不採。
- 前端自行捨入：JS `toFixed` 的捨入規則和後端不一致，風控已禁止，不採。

**條文 A（D-3 `forecast_record` 判定材料子項加）**
> - `band_def.up_pct`、`band_def.down_pct` 的單位是**比值**，例如 0.0107 代表 1.07%，不是百分數。欄位名裡的 `pct` 沿用事先宣告 L1083 的名稱，不改名。`forecast_outcome.realized_return` 同樣是比值。
> - 存值是未四捨五入的 IEEE 754 double，由產生 `threshold_snapshot` 的單一函式依事先宣告 L505-506 計算寫入。
> - **寫入驗證**（任一項不成立就拒絕）：
>   - 兩個值都是有限數；
>   - 0 < `down_pct` < 1；
>   - `up_pct` > 0；
>   - `up_pct` ≥ `down_pct`；
>   - 以同一個函式，用同列的 {`K_h`, `sigma_d`, h} 重算，結果逐位相等。

**條文 B（顯示字串介面，D-11.4 第 11 點 (h) 之後）**
> - **單一函式 `format_ratio_as_pct(ratio, *, signed) -> str`**：放在 `app/forecast/display.py`，是純函式。
>   - 計算：`Decimal(float(ratio))` 精確轉換 ×100，再 `quantize(Decimal("0.01"), ROUND_HALF_UP)`。Python decimal 的 ROUND_HALF_UP 就是遠離零。不經 str 中間值。
>   - `signed=True`：正數加「+」，負數加「−」（U+2212）；捨入後為零時輸出「0.00」，不帶正負號〔超出字面，請風控確認〕。
>   - `signed=False`：要求 ratio > 0。
>   - 非有限值一律拋出例外。
>   - 輸出不含「%」。
> - **回應欄位**：
>   - 凡是渲染 `label` 或 LM-131 的紀錄列，以及單筆展望區塊（LM-93／LM-115），都帶 `threshold_display = {down, up}`（不帶正負號）；
>   - 有 LM-131 的列，另帶 `realized_return_display`（帶正負號）；
>   - 這三個字串由同一個函式產生。
> - **封閉 schema**：`SettledRecordView`、紀錄列 view、`OutlookView` 都不得帶 `up_pct`、`down_pct`、`realized_return`、`realized_log_return`、`realized_z` 的原始數值。前端只把字串原樣代入，不得對它們呼叫 `toFixed`、`Intl.NumberFormat`、`Math.round`、`parseFloat`（前端 AST 測試）。
> - **片段 ID 由後端決定**：
>   - 列的 `disclosure_fragment_ids` 含 LM-146，若且唯若該列渲染 `label` 或 LM-131；作廢列與沒有 label 的列不含。
>   - 含 LM-92，若且唯若該列有 LM-131。
>   - `record_list_header` 含 LM-147，若且唯若至少一個大盤列含 LM-146；含 LM-148，若且唯若至少一個個股列含 LM-146。
>   - 族群列若需要 LM-146、但族群變體尚未核可 → 該列不顯示 label（fail-closed）。
> - 判定一律用未四捨五入的值（事先宣告 L507、L514）。`scoring.py`、`validation.py` 不得可達 `format_ratio_as_pct`。
> - **FL-59 加測試**：
>   - 性質測試：單調；對稱，即 fmt(−x) ＝ 「−」＋fmt(x)；R > th ⇒ disp(R) ≥ disp(th)；R ≤ th ⇒ disp(R) ≤ disp(th)；負號那一側同樣要測；
>   - 邊界 fixture；
>   - schema 中沒有原始比值欄位；
>   - 清單標頭 LM-147／LM-148 的選用。

## 三、驗證

**讀過的檔案與行號**
- 風控第九批最終版：全文。舊版只在 coordinator 通知前讀過，已被取代、不採用。
- 風控 RC″ 回送確認：全文，含 RC‴-1～RC‴-4。
- 我的增補檔 `…r3雙撇增補RC雙撇與T1至T5-tech-architect.md`：全文。
- quant 三題回答：全文。
- ADR-0027 本文：L213-591（D-1～D-11.4 第 12 點、D-3 L253-271、D-9.5 L436-439、D-11.1 L458-465）。另 grep 了 supersede、`band_def`、徽章等相關字。
- r3 提案：L80-339（A-57～A-78）。
- r3′ 補正：L185-294（A-77 第 1～11 項、A-75、FL-19）。
- r3″ 併入 RC：grep 了 A-63 (c) 的「沒有 snapshot」一句（L34-40）。
- 事先宣告草案：L1150-1229（X1～X4、X2 確認之後、§6.4）。
- 字面清單：LM-03、04、11、12、31～34、73～81、98、104、118～131 各列，以及 L387-395 的 H1～H3。

**其他**
- `apps/` 下 grep `OUTLOOK_HIDDEN_UNVERIFIED_TEMPLATE`、`VALIDATION_NUMBERS_LINE_TEMPLATE`、`select_gate_fragments`、`GATE_SLOT_SCOPES`：命中都是 0，以上提案都沒有落地成本。
- tech-writer 還在套用，所以 ADR 本文仍是套用前的版本。我以各提案檔的條文推定套用後的內容，A 號與項次以提案檔為準〔未查證套用結果〕。
- 範圍：沒有修改任何檔案，沒有跑程式、測試或 git，沒有讀 `.env` 或 `*.db`。這是唯讀的架構文件，Codex 不適用。

## 四、下一步

**回送風控（都需要單項確認）**
1. 提案 1：加上 `display_state = gated` 條件；selector 簽章改變；T-2 登記整段改寫；LM-144 ④「全文不含數字」的讀法。
2. 提案 2：`ValidationBadgeMasked` 的遮法；待裁 (a) LM-31 與不含 n 的徽章變體；待裁 (b) 歷史 n（`withdrawn_at_n`、`checkpoint_n`）不遮。
3. 提案 3：N-1 選甲；A-77 第 3 項改公式；兩面歸類維持「收緊」；新增的揭露筆數；FL-19 (h)。**D_v 前必須核可。**
4. 提案 4：「不變」的結論，以及四條寫入／讀取約束。
5. 提案 5：零值不帶正負號；view 不帶原始比值；族群列需 LM-146 時 fail-closed。

**其他人**
- **tech-writer**：風控核可後，把提案 1～5 套進 ADR-0027，A 號與方向依上文。
- **quant**：若風控採甲案，v0.11 §9.2 N-1 改寫「d 不回到觀察日」；L1083 加註單位是比值；判斷特徵窗要不要排除 X2 確認日（不擋 D_v）。
- **coordinator**：
  - 核對第 10 點加：`GATE_FRAGMENT_REGISTRY`、FL-52 斷言 (1)～(6)、`n_disclosure_masked`、徽章遮蔽格。
  - 核對第 11 點加：第 3 項的新公式、第 12 項全文、FL-19 (h)；A-75 的註記改字。
  - 新增核對：FL-49 的三格、A-65 的兩段條文。
  - 掛載 A 號清單不變（A-63、A-65、A-75、A-77）。
- **creative-lead**：若風控選待裁 (a) 的後者，起草不含 n 的族群徽章變體。

**相關檔案**
- /home/user/AICompany/work/reviews/2026-10-17-新定位第九批字面逐字審最終版-納入quant回答-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-RC雙撇增補回送項確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3雙撇增補RC雙撇與T1至T5-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-第九批字面三個量化問題回答-quant回報.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-r3prime補正-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027修訂提案r3-A54至A86含r2讀法確認-tech-architect.md
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md

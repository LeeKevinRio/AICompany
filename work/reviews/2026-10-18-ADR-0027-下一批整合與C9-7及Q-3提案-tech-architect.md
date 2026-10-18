# ADR-0027 下一批整合清單、LM-153／LM-154 條文、C9-7 與 Q-3 提案（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- 這份可以直接交 tech-writer 一次套用。所有條文都掛在既有 A 號下，沒有新增 A 號。這一批會動到的 A 號有：A-23、A-57、A-59、A-63、A-65、A-75、A-77、A-78、A-79。
- **第 1、2 項（LM-153、LM-154）**：照風控第十一、十二批第五節寫成條文，方向都是收緊。整合時發現一處矛盾：R10-4 讓 FAIL_CLOSED 列的白名單「比照 (c) 已結算列」，(c) 已結算列允許帶 `settlement_date`、`outcome_status`；但這兩個欄位屬於 R10-6 的 D 欄位，LM-154 條件 ⑤ 明文禁止 D 欄位。我以較晚、也較嚴的 ⑤ 為準：這條路徑不帶這兩欄。
- **第 3 項（C9-7）**：給三個選項，**推薦甲**。甲是把遮蔽擴及大盤與個股，並在查詢時加一個閘門值 `validation_refresh_pending`，讓 `shown` 改成 `gated`；字面沿用 LM-144、LM-153，不需要新字面。要回送風控，D_v 前核可。
- **第 4 項（Q-3）**：給三個選項，**推薦 A**：偵測這類日期、寫入事件留痕、固定排除在觀察日之外、在 §4.2 分列揭露。A 會改動 A-77 第 3 項的公式，所以它的 ADR commit 必須和某一版事先宣告同批。要回送風控，D_v 前核可。
- **第 5 項（三條 suggested）**：三條都採用。
  - `now` 改由 store 時鐘注入。
  - 族群的 `replay_review_approved` 只能出現在測試 fixture。
  - `final_after` 的呼叫位置：ADR-0027 這一側照寫。但 `set_i_check` 要記錄 `final_after` 的值，現行 ADR-0028 CS-17 的 grep 規則（「`final_after(` 只能在 `is_final` 內被呼叫」）不允許這樣做。要另開一個 ADR-0028 commit 修訂 CS-17、送風控；修訂落地前，X2 寫入函式不得實作。
  - 我另外發現兩個架構限制：一是 ADR-0028 CS-19 規定 `session_calendar.py` 不能讀市場 DB；二是依賴方向只能是 forecast → data。所以 `final_sessions()` 只能是純函式，而 `observed_sessions()` 要讀 X2 事件，必須放在 `app/forecast/`。
- **第 6 項（整合清單）**：另外發現四處要一併處理，條文都附在第 6 項：
  1. 第九批提案 1 的登記漏列了 (market／symbol, `record_list`)。C9-2 把登記改成封閉寫法之後，FL-52 會在這兩格必然失敗。補登既有已核可的 LM-121、LM-118、LM-119 即可。
  2. 甲案改了 A-77 第 3 項之後，第 12 項的「情境」句、D-7.3 L370、FL-19 (e)① 都不再屬實，要連帶改寫。
  3. A-65 的翻案伴隨句仍寫「R-5」「R-7」，要換成已核可的 LM-143、LM-150、LM-154。
  4. R-7 提案 3 是放寬，A-65 的類別因此要從「收緊」改成「含有條件放寬的兩面」。累計方向統計由 19／2／9／1／2 變成 **18／2／9／1／3**。

## 二、逐項條文

### 第 1 項｜LM-153（掛 A-63，RC′-2 子點，接在第九批提案 2 條文之後；方向：收緊）

**1-1　取代第九批提案 2「遮蔽時的回應」的第一子點**
> - **遮蔽時的回應**：`n_disclosure_masked(claim, snapshot)` 為真時，該 claim 的徽章在這次回應中是 `ValidationBadgeMasked`，封閉 schema（`extra="forbid"`），欄位恰好四個：
>   - `claim_id`；
>   - `masked: Literal[True]`；
>   - `mask_reason: Literal["e_changed_since", "no_daily_snapshot"]`：封閉列舉，schema 拒絕列舉外的值；要增列，須送風控重審 LM-153 是否仍屬實；
>   - `badge_fragment_id: Literal["LM-153"]`：值只能是 LM-153（風控第十一批 LM-153 條件 ⑬）。
> - 前端只依 `badge_fragment_id` 渲染釘字常數，不得自行持有、拼接或改寫字串，不得渲染 `mask_reason`。
> - 徽章字面登記在 `BADGE_FRAGMENTS`，和 `GATE_FRAGMENT_REGISTRY` 分開。LM-153 不登記 `covers`，不進 gate 登記（條件 ⑩）。
> - 只有 `scope_kind = sector` 的 claim 會產生 `ValidationBadgeMasked`（條件 ⑥）。大盤與個股的處理依待決 C9-7。
> - 第九批提案 2「遮蔽時的回應」其餘子點（不帶數值、不帶 LM-03／LM-04／LM-32／LM-33 的 ID、前端不渲染狀態詞與數字行、同區塊經 LM-122／LM-123／LM-126／LM-127 代入 LM-144）照舊。
> - **遮蔽只遮徽章**（條件 ⑫）：LM-76、LM-81，以及 C9-4 例外的歷史值（LM-75、LM-79、LM-81、LM-104 的 `{X0}`／`{X}`，取事件當時寫定的欄位），照各自的條件渲染。產生這些片段的函式不得呼叫 `n_disclosure_masked`。
> - **遮蔽與方向互斥**（條件 ⑪）：`views` 在任何回應（`OutlookView`、紀錄列、`settled_record`）帶出族群 claim 的 label 之前，要另外確認 `n_disclosure_masked` 為假；為真時不帶 label，並記 WARNING。這是 `pa9_holds` 之外的獨立檢查。依 RC′-2，遮蔽成立時 `pa9_holds` 必然為真，所以這一條是縱深防禦。
> - **同頁一致**（條件 ⑭）：
>   - 同一次回應中，每個族群 claim 只判定一次（同一個 read transaction），只產生一個徽章物件，`sector_cell`、`sector_detail` 的所有徽章位置都引用它。
>   - 同一頁的族群徽章只能來自同一個回應。前端不得為同一個 claim 從兩個端點取徽章。

**1-2　FL（取代第九批提案 2「FL-52／FL-59 加格」子點）**
> - **FL-59 徽章遮蔽格**（條件 ⑨）：族群 × `mask_reason` 兩值，各一格。fixture 的 snapshot n 取 137（不出現在任何已核可字面的固定文字中）。逐格斷言：
>   - (m1) 徽章通過 `ValidationBadgeMasked` 的 schema 驗證。`badge_fragment_id` 為其他值、`mask_reason` 未列舉、多出欄位，都驗證失敗。
>   - (m2) 徽章位置渲染出的字串，逐字等於 LM-153；兩格的渲染結果逐位相同。
>   - (m3) 回應中找不到 LM-03、LM-04、LM-32、LM-33 的 ID。
>   - (m4) 回應 JSON 與渲染全文都找不到「137」（照 C9-3）。
>   - (m5) 對照格 `masked = false`：徽章照常渲染，而且全文找不到 LM-153 的字串。
>   - (m6) 同一回應中，同一個族群 claim 出現在多個徽章位置時，所有位置都是同一個物件（全遮或全不遮）。另加前端契約測試：族群徽章元件只從所屬頁面的單一端點回應取值。
> - **FL-59 歷史值格**（條件 ⑫，併入 C9-4 那一格）：遮蔽中 × {`suspended_f3`, `withdrawn_f2`}。
>   - LM-76、LM-81 照常渲染。
>   - LM-75、LM-79、LM-81、LM-104 的 `{X0}`／`{X}` 等於事件欄位（`withdrawn_at_n`、`checkpoint_n`、`predecessor_withdrawn_at_n`），fixture 中這些值都 ≠ 137。
>   - 同一個 fixture 把 `masked` 切成假，這些片段的渲染逐位相同。
> - **FL-52 斷言 (8)**（條件 ⑪）：
>   - 族群 × 兩種遮蔽情形 × `display_state` ∈ {`gated`, `suspended_f3`, `withdrawn_f2`} × {已結算, 未結算}：任何回應都沒有該 claim 的 label。
>   - 另一格：fixture 強制 `pa9_holds` 回傳假，而 `n_disclosure_masked` 為真 → 仍然沒有 label，並有 WARNING。

### 第 2 項｜LM-154（掛 A-65，「FAIL_CLOSED 的列」子點，也就是 R10-4 的位置；連帶 A-64 的 `MaskedRecordView`；方向：收緊）

> - **FAIL_CLOSED 路徑的狀態片段**：同時滿足以下三點的列，以 `MaskedRecordView` 回傳，`status_fragment_id` 必填，值只能是 LM-154（風控第十二批 LM-154 條件 ③）：
>   - `had_listed_result` 為真；
>   - 最新 outcome 是 `resolved`；
>   - 依 `CORRECTION_REASON_FRAGMENTS` 判為 FAIL_CLOSED。
>   - 這是雙向規則：LM-154 也只能出現在這條路徑。
>   - 判定只由 `display.py` 的單一函式 `record_status_fragment(row)` 產生。
>   - FAIL_CLOSED 的情形是封閉的，只有以下四種：兩個以上的原因；`[dividend_factor_corrected]`；`[window_bar_corrected]` 但 `correction_is_display_neutral(chain)` 為假；`[settlement_close_corrected]`、P(T) 收盤有變（`start_price_json` 的收盤和前一列不同），而且 quant 還沒有書面確認 R10-5。
> - **白名單**（R10-4 與 LM-154 條件 ⑤ 合併；兩者不一致時以 ⑤ 為準）：
>   - 可帶：A-36 第 1 點 (b) 的清單；排程列用 `late` 取代 `window_started`；`settled = true`。
>   - 不帶 `settlement_date`、`outcome_status`：兩者都屬於 R10-6 的 D 欄位，在本路徑不適用 (c) 已結算列的那兩欄。
>   - 不得出現：A-64 (g) 的全部禁止欄位；`label`、`realized_label`、`hit`、`realized_return`、`realized_z`、`realized_log_return`；R10-6 的任何 D 欄位（含 `realized_return_display`、`invalidation_*`、`mae`、`mfe`、`diag_*`）；`threshold_display`；`resolved_at`；`correction_causes`。
>   - `disclosure_fragment_ids` 不得含 LM-131、LM-132、LM-146、LM-92、LM-133、LM-143、LM-150。大盤列不得含 LM-22。
> - **全域不顯示**（條件 ⑥）：這筆紀錄更正後的結果，不得出現在任何回應或匯出，包括驗證狀態頁的逐筆明細、匯出、展開處。所有含紀錄明細的 route 與 `EXPORT_MODULES`，都經過同一個 `record_status_fragment` 判定。
> - **§4.2 的計數來源**（條件 ⑫，TA 這一側）：依 LM-154 不顯示結果、但仍計入主統計（鏈尾，D-11.1）的列數，依鏈尾的 `correction_causes` 分列（多原因另列一類）。由同一個判定逐列數出，不另存欄位。quant 在事先宣告 v0.12 §4.2 登記。
> - **FL-22 (c) 的 FAIL_CLOSED 格**（取代 R-7 提案 1 FL (c) 的第二子點；條件 ③⑤⑩）：
>   - 四格：除權息因子；兩個以上原因；未豁免的診斷更正；R10-5 確認前、P(T) 收盤有變的收盤更正。每格斷言：
>     - schema 驗證通過，`status_fragment_id == LM-154`；
>     - 狀態行逐字等於 LM-154；全文不含日期數字，不含「作廢」「撤回」「沒有實際結果」，也不含 LM-143、LM-150 的 ID；
>     - 沒有白名單以外的鍵；`disclosure_fragment_ids` 不含上列 ID；大盤格不含 LM-22。
>   - 對照格：`[x2_session_removed]`；P(T) 不變（或 R10-5 已確認）的 `[settlement_close_corrected]`；豁免成立的 `[window_bar_corrected]`。這三格都找不到 LM-154。
> - **FL-52 謂詞路徑表**：
>   - 謂詞為真 × 最新 outcome 是 `resolved` × `correction_causes` 的全部情形：每格恰好落在 {LM-150, LM-154, 豁免（不帶伴隨句）} 其中之一。
>   - 謂詞為真 × 最新 outcome 不是 `resolved` → LM-143。
>   - 謂詞為假 → 三句都不出現。
>   - 性質測試：同一列 LM-143、LM-150、LM-154 至多出現一句。
> - **FL-52 條件 ⑥ 格**：
>   - FAIL_CLOSED fixture 的鏈尾 `realized_return` 取 0.0137，`end_price_json.session_date` 取其他 fixture 列沒有用到的日期。
>   - 列舉所有 route（比照 FL-54 (g)）與 `EXPORT_MODULES`：帶該 `forecast_id` 的物件都沒有 D 欄位的鍵；全文找不到「1.37」，也找不到該日期的 MM/DD 字串。

### 第 3 項｜C9-7 提案（D_v 前；掛 A-63 RC′-2 子點與 A-57 (iv)；要回送風控）

**落後是怎麼發生的〔事實＋推論〕**
- E 變動事件只有四類：PIT 違規移出、X2 移除觀察日、整檔還原、outcome supersede。R10-3 又拒絕「作廢後改回結算」。所以在落後期間，n 只會不變或減少：snapshot 的 n、k、區間、狀態只會偏向樂觀，不會偏向保守。
- 正常的排程路徑是「結算 → 缺日稽核 → 驗證快照」，事件在快照之前寫入，落後只有幾分鐘。真正會落後的是排程以外的寫入，例如稽核作業、更正作業、mark-restored。〔推論，沒有實測頻率〕

| 方案 | 內容 | 優點 | 缺點／風險 |
|---|---|---|---|
| **甲（推薦）全 scope 遮蔽＋查詢時閘門** | 遮蔽擴及大盤與個股；加 `validation_refresh_pending`，查詢時讓 `shown` 改成 `gated` | 和族群對稱；LM-153 條件 ⑪「遮蔽與方向互斥」在三個 scope 都成立；不需要新字面 | `e_changed_since` 不按 claim 篩選，一筆事件會遮掉全部 claim，直到下一筆 snapshot；要風控擴大 LM-144、LM-153 的使用 scope |
| 乙　只遮數字與狀態 | 徽章遮蔽、LM-12 不可選；方向照 snapshot | 改動小 | 違反條件 ⑪，要另開例外；PIT 違規之後到下一筆 snapshot 之前，F-3 暫停還沒生效，方向照常顯示 |
| 丙　事件後立即補一筆 snapshot | 新增 `eval_kind = interim` | 落後最短 | 和 `UNIQUE(claim_id, computed_for_session, eval_kind)`、「每個（claim, 評估日）只算一次」、R10-7 的「snapshot 不 supersede」都衝突；補算完成之前仍然要遮蔽 |

可以和任何一案搭配：把排程內的 E 變動寫入者（X2 確認、更正作業、PIT 稽核）都限定在當晚的「驗證快照」步驟之前執行，縮短窗口。屬收緊，可選。

**甲案條文**
> - `n_disclosure_masked(claim, snapshot)` 去掉 `scope_kind = sector` 的條件：任何 scope，只要沒有 daily snapshot，或 `e_changed_since(snapshot)` 為真，就為真。
> - **查詢時閘門 `validation_refresh_pending`**：列入大盤與個股的 `GATE_FIXED`；族群不用這個值，族群依 RC′-2 加入 `forward_n_below_min`。
>   - 成立，若且唯若 `n_disclosure_masked` 為真。只在查詢時加入 G_eff。snapshot 寫入時依 A-63 以 `e_changed_since = False` 計算，所以 snapshot 的 `gate` 永遠不含它。
>   - 效果是 `shown` 變成 `gated`；`suspended_f3`、`withdrawn_f2` 照 snapshot。A-57 (iv)「查詢時調整只可能把 `shown` 變成 `gated`」的性質測試，擴及三個 scope。
>   - 沒有 snapshot 時：`display_state = gated`。G_eff ＝ {`validation_refresh_pending`} ∪ 可在查詢時判定而且成立的固定值（例如 `replay_review_pending`）；quant 有登記門檻時，另加 `forward_n_below_min`（n 未知，比照 RC′-9 fail-closed）。
>   - `plan_reason` 不登記這個值：plan 在 snapshot 之後讀 T 日 snapshot 計算（A-4）。v1 的個股常駐 `replay_review_pending`，plan 不受影響。日後依 §4.7 開放個股之前，要先補一句涵蓋這個值的 `plan_reason` 片段。FL-52 的 P(symbol, `plan_reason`) 不含這個值。
> - **原子片段**：`validation_refresh_pending` 用 LM-144「前瞻紀錄筆數待彙整」，`covers = {validation_refresh_pending}`，scope 為大盤、個股。
> - **徽章**：大盤與個股遮蔽時同樣回 `ValidationBadgeMasked`（LM-153）。
> - **LM-12**：遮蔽時選不到。`outlook_block` 改用 LM-120，原子依 GR 取 LM-128（`forward_n_below_min` ∈ G_eff 時）、LM-130、LM-144。
>   - LM-128「樣本不足」在落後期間仍然屬實，因為 n 只減不增。
>   - 失效條件：R10-3 的規則日後若允許作廢改回結算，本點要重審。
> - **FL**：
>   - (a) 大盤、個股 × {`e_changed_since`, 沒有 snapshot} × snapshot `display_state` 四態：`shown` 變成 `gated`；徽章是 LM-153；找不到 LM-03、LM-04、LM-32、LM-33、LM-12；fixture 的 n 取 137，全文找不到。
>   - (b) 性質測試：調整只會把 `shown` 變成 `gated`。
>   - (c) FL-52 窮舉納入新值；`plan_reason` 的窮舉不含新值。
>   - (d) 性質測試：任一種 E 變動事件前後，n 不增。

**要風控裁定**
- (a) LM-153 條件 ⑥、LM-144 條件 ① 的 scope 擴及大盤、個股（字面不動）。
- (b) 大盤與個股適用條件 ⑪ 時，讀作「不得渲染目前展望的 label」。已結算紀錄列讀的是即時的鏈尾、不讀 snapshot，label 照舊。
- (c) 方向歸類：收緊。

### 第 4 項｜Q-3 提案（D_v 前；掛 A-77 第 10 項、第 3 項，連帶 D-3 `forecast_ledger_events` 的列舉；要回送風控）

**現況**
- A-77 第 10 項只規定「記 WARNING」，沒有定義偵測範圍、沒有留痕、也沒有揭露。
- 官方休市日表接入之前，週一至週五的國定假日都會落入這一類，估計每年約 15～20 天〔推論〕。
- 另外有兩種日子：候選 T 被記 `inputs_not_ready`，但當天不是觀察日，所以沒有缺日列可記（甲案 (h5) 也是這樣）。這類日子現在沒有任何持久紀錄可以計數。

| 方案 | 內容 | 優點 | 缺點／風險 |
|---|---|---|---|
| **A（推薦）偵測留痕＋固定排除＋分列揭露** | 寫入 `unobserved_weekday` 事件；登記之後，d 不再因補寫資料而回到觀察日 | 和甲案同一套邏輯；觀察日只減不增；沒有新的更正路徑；可以逐列計數 | 第 3 項的公式要再加一項，事先宣告 §9.3 第 18 點 (i)、第 19 點 ③ 要同批對齊；定義忠實度是兩面的（d 若其實是交易日，T+h 會多跨一天） |
| B　偵測留痕＋揭露，不固定排除 | 公式不變；之後補到資料，d 就成為觀察日 | 不改公式 | 補寫之後，已結算列的 T+h 和觀察日集合對不上。現行列舉沒有對應的更正原因，所以會無聲地留下不一致 |
| C　平日推定為觀察日，寫缺日列 | 新增缺日原因 | 缺日數完整 | 違反「不用週一至週五推定」；接入官方表之前會把國定假日記成缺日，T+h 與 F-3 都會失真 |

可以和 A 搭配：把官方休市日表接入列為 D_v 前置，減少誤報。

**A 案條文**
> - **A-77 第 10 項整點取代**：
>   - **未觀察平日（Q-3 日）**：d 同時滿足以下各項：是平日（Asia/Taipei 週一至週五）；不是已接入、而且涵蓋 d 的官方休市日表所列的休市日；d ∉ (i)；d ∉ (ii)；而且已經有晚於 d 的觀察日。
>   - **偵測**：缺日稽核以單一函式 `unobserved_weekdays(start, end)`，逐日檢查 [D_v, 最新觀察日] 內的平日。這裡列舉平日只是為了產生候選，不得用來推定觀察日（FL-19 不變）。
>   - **成立時**：
>     - 記 WARNING。
>     - 寫一筆 `forecast_ledger_events.kind = unobserved_weekday`，歸入 `E_NEUTRAL_EVENTS`。
>     - payload：`session_date`；`holiday_table = {version, coverage_start, coverage_end} | null`；`holiday_coverage ∈ {table_absent, not_covered, listed_as_trading_day}`；`run_evidence = {prefinal_ok_runs: [{run_id, recorded_at}], any_run}`；`index_evidence ∈ {no_row, not_final, demo_only, ohlc_invalid}`；`detected_by_run_id`。
>     - payload 由寫入函式自行填入，不接受呼叫端傳入。同一個 `session_date` 只寫一次。
>   - **固定排除**：第 3 項改為「觀察日 ＝〔(i) ∪ (ii)〕− X2 確認日 − 已登記的 Q-3 日」。
>     - 登記當下 d ∉ (i) ∪ (ii)，所以新公式在登記當下和原公式相同。
>     - 登記之後，d 即使因補寫進入 (i) 或 (ii)，也不回到觀察日。這時寫 `session_calendar_conflict`，新增 `origin = post_unobserved_backfill`；程式不得自動解除。
>     - 不寫缺日列，不觸發 §6.4 更正，不改任何已寫入的紀錄。
>   - **§4.2 揭露**（quant 登記）：
>     - ① Q-3 日數，依 `holiday_coverage` 分列，日期全部列出；
>     - ② 其中有定案前 ok run 的日數，也就是候選 T 曾被拒、但沒有缺日列的日子（同時涵蓋 S9-3）；
>     - ③ 結算窗 [T, T+h] 跨越 Q-3 日的 outcome 筆數（鏈尾，逐列數出）；
>     - ④ `post_unobserved_backfill` 的日數。
>     - 以上都不得併入缺日數，也不得併入 `session_calendar_conflict` 其他 origin 的筆數。
> - **FL-19 加 (i)**：
>   - 平日沒有 run、也沒有大盤列 → 只寫一筆事件，d 不是觀察日，沒有缺日列，重跑不重複寫入；
>   - 表列休市日、週末、d 是最新日期 → 都不寫事件；
>   - 登記之後補寫 run → d 仍然不是觀察日，衝突事件只寫一筆；
>   - outcome 與缺日列的雜湊前後相同。

- 方向：收緊（偵測與揭露；觀察日只減不增）。定義忠實度是兩面的，比照 C9-8 的字句並陳。

### 第 5 項｜風控 suggested 三條（全部採用）

**(a) `now` 改為可注入的 store 時鐘**（掛 A-75；收緊；照寫）
> - D-7.3 L365 的子點下加：
>   - `now` 是 store 時鐘（D-2 第 3 點）的讀值，由 recorder 以參數傳入：`is_final_bar(row, *, now)`，沒有預設值。
>   - `session_calendar.py` 不讀任何時鐘（grep 不得出現 `datetime.now`、`date.today`、`time.time`），也不 import `app.forecast.*`。
>   - 每一次判定候選 T，讀一次時鐘；(ii) 經強制重抓之後重讀一次。
> - FL-61 (a) 加兩格：
>   - 注入的 `now` 早於 `fetched_at` 一秒 → False；
>   - AST 檢查 `is_final_bar` 沒有預設的 `now`。

**(b) `final_after` 的呼叫位置符合 CS-17**（ADR-0027 這一側：A-78、A-77；方向不變；照寫）
> - D-4.1 L300：「`recorded_at ≥ final_after(TW, s)`」改為「`is_final(TW, s, recorded_at)` 為真」。
> - A-77 第 1 項 L444：改為「`is_final(TW, d, run.recorded_at)` 為真的 session d」，並加三點：
>   - 由 `app/data/session_calendar.py` 的純函式 `final_sessions(run_stamps, *, market)` 提供；
>   - `run_stamps` 由呼叫端經 `MarketPanelReader` 讀出，函式本身不讀市場 DB（ADR-0028 CS-19）；
>   - 不得在 `is_final` 以外呼叫 `final_after(`。
> - 甲案提到的 `observed_sessions()` 放在 `app/forecast/observed_days.py`，D-1 加一列。理由：它要讀 X2 事件，放在 `app/data` 會違反「forecast → data」的依賴方向。
> - A-77 第 7 項 L469 的 `set_i_check`：
>   - 改由 `session_calendar.py` 的純函式 `final_session_evidence(run_stamps, d, *, market)` 產生；寫入函式不得自行呼叫 `final_after(`。
>   - **ADR-0028 CS-17 現行的 grep 規則只允許在 `is_final` 內呼叫 `final_after(`。** 要先修訂 CS-17：另開 ADR-0028 commit，送風控單項確認。修訂落地前，不得合併 `final_session_evidence` 與 X2 寫入函式的程式。
> - A-77 第 12 項 L484：同第 1 項的改法；偵測改呼叫 `final_sessions()`（未扣除的 (i)）。
- ADR-0028 那一側的建議字句：
  > 「`final_after(` 只能在 `session_calendar.py` 內被呼叫，恰好兩處：`is_final`，以及只把值寫進稽核 payload、不作任何判定的 `final_session_evidence`（grep 加 AST）。」
- 我把這一條歸為「不變」：它不會讓任何日子變成定案。但 ADR-0028 CS-21 通則規定方向判斷不了的一律視為放寬，所以交風控定奪。

**(c) 族群的 `replay_review_approved` 只能出現在測試 fixture**（掛 A-57 的 RC′-8 寫入前提＋A-63 的 FL-58；收緊；照寫）
> - 事先宣告 §4.7 的修訂核可之前，以下各點成立：
>   - 寫入函式另外驗證 claim 的 `scope_kind` ∈ `REPLAY_APPROVAL_SCOPES`。`display.py` 定義 `REPLAY_APPROVAL_SCOPES: Final = frozenset({"market"})`，不得由參數、設定檔或環境變數改變（比照 ADR-0028 CS-12）。
>   - 啟動時檢查：主 DB 若已有 scope 不在這個集合內的 `replay_review_approved` 事件，拒絕啟動。
>   - FL-58 (e1) 第二格與 (e2) 用到的事件，由測試 fixture 以 SQL 直接插入暫存 DB，不經寫入函式。這兩格另外斷言：同一筆 payload 經寫入函式會被拒絕。
>   - grep／AST：`app/` 下沒有以 sector 或 symbol 建構這個事件的程式碼。

### 第 6 項｜整合清單（給 tech-writer 一次套用）

**6-1　來源**
- 只取來源檔中以「>」引用的條文區塊。比較表、推論、「要風控裁定」等敘述不進 ADR。

| 代號 | 檔案（都在 `work/reviews/`） | 取用的節與條 |
|---|---|---|
| S1 | `2026-10-17-ADR-0027-第九批TA待決項提案-tech-architect.md` | 第二節，提案 1～5 |
| S2 | `2026-10-17-ADR-0027-第九批TA提案確認-風控.md` | 第二節 C9-1～C9-10；S9-1、S9-2、S9-4（TA 建議採用；S9-3 併入第 4 項） |
| S3 | `2026-10-17-ADR-0027-R7對照表與更正鏈確認-tech-architect.md` | 第二節，提案 1～4 |
| S4 | `2026-10-17-ADR-0027-R7對照表與更正鏈提案確認-風控.md` | 第二節 R10-1～R10-7 |
| S5 | `2026-10-17-ADR-0027與v0.11同批最終裁定-風控.md` | 第二節第 4 項（L974）、第 1 項 suggested（L1366） |
| S6 | `2026-10-17-新定位第十一批字面逐字審-LM153-風控.md` | 第三節 LM-153 條件 ①～⑭；第五節 |
| S7 | `2026-10-17-新定位第十二批字面逐字審-LM154-風控.md` | 第三節 LM-154 條件 ①～⑫；第五節 |
| S8 | `2026-10-17-ADR-0027-疑義裁定回送四項確認-風控.md` | 第二節回送第 1 項 suggested、第 4 項 suggested |
| S9 | 本份 | 第 1、2、5 項 |

**6-2　衝突時的優先序**
- 由高到低：**S7 > S6 > S4 > S3 > S2 > S1**。
- 同一份風控檔內，指名「取代」的條文優先於被取代的條文。
- 風控逐字條文（「給 tech-writer 照寫」）優先於 TA 條文。
- S5、S8 和其他來源不重疊。
- S9 是 S6～S8 的落地條文，地位等同各自的來源；和風控逐字文衝突時，以風控逐字文為準。
- 仍有疑義時，取較嚴（fail-closed）的一方，並回報 coordinator，不得自行折衷。

**6-3　整合後的 selector 簽章**（取代 L797）
> - 上述位置的 gate 片段 ID，只能由 `select_gate_fragments(scope_kind, slot, G_eff, display_state, validation_status, n_masked)` 產生（route 列舉＋AST 測試，比照 FL-60 (d)）。
>   - `display_state` 取 `views` 調整後的值。
>   - `validation_status` 取判定 `display_state` 的同一列最新 daily snapshot 的 `status`（A-57 (iv) 規定取原值）。沒有 snapshot 時為 None；None 一律不選 LM-12。
>   - `n_masked` 只能由 `views.n_disclosure_masked(claim, snapshot)` 產生。這個函式在內部自行呼叫 `e_changed_since(snapshot)`，不接受呼叫端傳入的 bool（S9-2，AST 測試）。
> - 輸入 `display_state = shown` 而 G_eff 非空時，函式 raise。另加性質測試：`views` 永遠不會產生這個組合（S9-1，FL-52 斷言 (9)）。

**6-4　逐處套用**（行號為現行版；建議由檔尾往前套，避免行號位移）

| # | 位置 | 動作 | 來源 | A 號 | 方向 |
|---|---|---|---|---|---|
| 1 | 檔頭 L10-18 之後 | 加一行：本批名稱、來源 S1～S9、與事先宣告 v0.12 同批、優先序見修訂紀錄 | S9 | A-79 | 不變 |
| 2 | D-1 模組表 | 加 `app/forecast/observed_days.py` | 第 5 項 (b) | A-77 | 不變 |
| 3 | D-3 `forecast_record` 判定材料（L267） | `band_def` 單位是比值，加寫入驗證 | S1 提案 5 條文 A | A-65 | 收緊 |
| 4 | D-3 `forecast_outcome` 的更正子項（L281） | 加 `correction_causes` | S3 提案 1 | A-65、A-77 第 8 項 | 收緊 |
| 5 | D-3 L282 之後 | 新增 `forecast_correction_job`／`_end` | R10-1（取代 S3 的該子點） | A-65 | 收緊 |
| 6 | D-4.1 L300 | 改成 `is_final` | 第 5 項 (b) | A-78 | 不變 |
| 7 | D-7.3 L365 | 加 `now` 子點 | 第 5 項 (a) | A-75 | 收緊 |
| 8 | D-7.3 L370 | 「(iii) 在結構上不會成立」改為「(iii) 只在 A-77 第 12 項的情形下成立（d 經 X2 確認之後才進入 (i)，又成為候選 T）；其餘情形保留為縱深防禦，以測試斷言」 | S1 提案 3 | A-75 | 收緊 |
| 9 | A-77 第 1 項（L444） | 見第 5 項 (b) | 第 5 項 (b) | A-77 | 不變 |
| 10 | 第 3 項（L446） | 新公式＋三個子點 | S1 提案 3 | A-77 | 收緊 |
| 11 | 第 5 項句尾（L459） | 照 C9-8 改寫 | C9-8 | A-77 | 不變 |
| 12 | 第 7 項 `set_i_check`（L469） | 見第 5 項 (b) | 第 5 項 (b) | A-77 | 不變 |
| 13 | 第 8 項（L477） | 加 `x2_shift_json` 累計語意；R10-5 第二句（`shifted_t_plus_h == end_price_json.session_date`） | S3 提案 2＋R10-5 | A-77 | 收緊 |
| 14 | 第 11 項句尾（L482） | 加「觀察日集合不因第 12 項的情形而回復。」 | S1 提案 3 | A-77 | 收緊 |
| 15 | 第 12 項（L483-495） | 見 6-5 第 3 點 | S1 提案 3＋本份 | A-77 | 收緊 |
| 16 | D-11.1 L563 之後 | 主統計就是鏈尾（含 FL-49 三格的指引） | S3 提案 4 | A-59 | 不變 |
| 17 | D-11.2 L579 | 取代「沿用原 seed」句，加撤銷規則 | R10-7 | A-77（連帶第 11 項） | 收緊 |
| 18 | D-11.4 (c) RC′-2，`E_CHANGING_EVENTS`（L716-720）之後 | `forecast_record` 的更正不改變 E：四條約束＋失效條件；第 2 條改為「結算與 validation 讀 `label`、`band_def`、`baseline_predictions_json` 時取原始列；`base_close` 只供預測端與稽核比對，結算的 P(T) 取 `start_price_json`（R10-5）」 | S1 提案 4＋R10-5 | A-63 | 不變＋收緊 |
| 19 | (c) RC′-2 L746 之後 | `n_disclosure_masked`（S9-2 簽章）；徽章資料來源（C9-6 加 LM-12 的 `{n}`）；遮蔽時的回應（第 1 項 1-1）；整個回應的例外（C9-4）；上線限制（C9-5，加註〔已決：LM-153〕） | S1 提案 2＋C9-4～C9-6＋第 1 項 | A-63 | 收緊 |
| 20 | 第 11 點 L789 | `GATE_STATUS_FRAGMENTS` 改為「`GATE_FRAGMENT_REGISTRY` 是唯一的登記，選用一律經 selector」；舊型別無法表達 `display_state` 等條件 | 本份 | A-63 | 不變 |
| 21 | L797-801 | 換成 6-3 的簽章＋提案 1 的整段登記（含 C9-1 的 LM-12 條件、C9-2 的 sector `record_list_header` 與封閉寫法、6-5 第 1 點的補登）。L800、L801 移入修訂紀錄，另保留一句「FL-52 任一格失敗，不得以 skip、xfail、placeholder 或暫定字面讓測試通過」 | S1 提案 1＋C9-1、C9-2 | A-63 | 收緊 |
| 22 | (g) L848-854 | 加第 2 項的 LM-154 路徑與白名單 | R10-4＋S7＋第 2 項 | A-65（A-64 的 schema） | 收緊 |
| 23 | (h) T-4（L859-865） | 鏈上每一列都適用 T-4，依原因分別取值；加 R10-5 第一句 | S3 提案 2＋R10-5 | A-65 | 收緊 |
| 24 | (h) 翻案伴隨句（L866-873） | 見 6-5 第 4 點；之後接 S3 提案 1 的列舉、歸屬、一致性驗證（另加 R10-2）、R10-3、對照表；再接 S3 提案 3（D 欄位定義後加 R10-6） | S3 提案 1、3＋R10-1～R10-4、R10-6＋S7 | A-65 | 收緊＋有條件放寬 |
| 25 | (h) 之後（L874） | 提案 5 條文 B；對稱性那一句、LM-146 的若且唯若句換成 C9-10 的兩句 | S1 提案 5＋C9-10 | A-65 | 收緊 |
| 26 | 第 12 點 (iv) L908-912 | 加 `REPLAY_APPROVAL_SCOPES` | 第 5 項 (c) | A-57 | 收緊 |
| 27 | D-12 L974 | 見 6-5 第 6 點 | S5 第 4 項 | A-23 | 不變 |
| 28 | FL-19 | (e)① 的「依 A-77 第 5 項，T ∈ (i) 時結構上不可能，屬縱深防禦」改為「除 A-77 第 12 項的情形（見 (h5)）外，屬縱深防禦」；加 (h1)～(h6) | S1 提案 3＋本份 | A-77 | 收緊 |
| 29 | FL-22 | 加 (a)～(e)；R10-2 的三種拒絕；(c) 的 FAIL_CLOSED 格依第 2 項 | S3 提案 1＋R10-2、R10-4＋第 2 項 | A-65 | 收緊 |
| 30 | FL-49 | 加：提案 4 三格（A-63）；R-7 提案 4 三格（A-59）；R10-7 一格（A-77） | S1、S3、S4 | 分列 | 收緊／不變 |
| 31 | FL-52 | L1325 換成提案 1 的斷言 (1)～(7)，其中 (5) 照 C9-3；加 (8)（第 1 項）、(9)（S9-1）；登記與 `GATE_SLOT_SCOPES` 一一對應（C9-2）；加謂詞路徑表與條件 ⑥ 格（第 2 項）；加 R-7 提案 3 的三格與 R10-6 的 schema 斷言 | S1、C9-1～C9-3、S3、R10-6、第 1、2 項 | A-63、A-65 | 收緊 |
| 32 | FL-53 (f) L1366 | 改為「→ loader 拒絕（增補 T-1；與 FL-52 同一個 `gate_coverage_gaps`）。」 | S5 第 1 項 suggested | A-57 | 不變 |
| 33 | FL-58 (e1) 第二格、(e2) | 句尾加「（事件由測試 fixture 直接插入；寫入函式對同一 payload 拒絕，見 A-57 `REPLAY_APPROVAL_SCOPES`）」 | 第 5 項 (c) | A-63 | 收緊 |
| 34 | FL-59 | 加徽章遮蔽格、歷史值格（第 1 項＋C9-4）；提案 5 的性質測試、邊界、schema、LM-147／LM-148 的選用；R-7 提案 2 的三格 | S1 提案 2、5＋C9-4＋S3 提案 2＋第 1 項 | A-63、A-65 | 收緊 |
| 35 | FL-61 (a) | 加 `now` 兩格 | 第 5 項 (a) | A-75 | 收緊 |
| 36 | Consequences L1153 之後（建議） | 加四點：甲案的兩面後果（取 C9-8 字句）；診斷欄位更正例外屬揭露面放寬；LM-154 列看不到結果、但計入主統計；族群徽章在上線初期以遮蔽為常態 | 本份 | A-79 | 不變 |
| 37 | 待決事項 | 見 6-5 第 7 點 | 多來源 | A-79 | 不變 |
| 38 | 修訂紀錄 L2145 之後 | 新開一段，見 6-6 | — | — | — |

**6-5　整合時發現的補登與不一致**（條文附在各點）
1. **補登 (market／symbol, `record_list`)**：C9-2 把登記改成封閉之後，這兩格沒有列出，FL-52 會失敗。照既有核可條件補登：
   > - `record_list`（market、symbol）：A-27 (b) 成立、未結算的列用 LM-121（`{G 並列句}` ＝ LM-120 全文，原子同 `outlook_block` 的 LM-120）；A-27 (a) 的列用 LM-118／LM-119（`covers = ∅`），G_eff 非空時後接 LM-120（A-63 第 12 點 (2)）。
2. **FAIL_CLOSED 列的白名單**：以 LM-154 條件 ⑤ 為準，不帶 `settlement_date`、`outcome_status`。條文已寫在第 2 項。
3. **A-77 第 12 項**：
   - 標題改為「（風控 2026-10-17 N-1；第九批提案 3 甲案）」。
   - 「情境」末句改為：「這時 d 屬於未扣除的 (i)，和已寫入的事件及 `x2_shift_json` 的前提（d ∉ (i)）矛盾；依第 3 項，d 不回到觀察日。」
   - 「觀察日身分怎麼處理」整點換成甲案全文，並加 §4.2 的 outcome 筆數揭露。
   - L494、L495 兩點由甲案取代，移入修訂紀錄。
   - 另註一句：(h5) 的 `inputs_not_ready` 不寫缺日列（d 不是觀察日），計數來源併入 Q-3 提案處理。
4. **翻案伴隨句**：「用 R-5」改為「用 LM-143」；「用 R-7」改為「依 `CORRECTION_REASON_FRAGMENTS` 用 LM-150（代入 LM-151／LM-152）或 LM-154」。「對應的伴隨句核可之前…」與「R-5、R-7 列入 D_v 前置…」兩句加註〔已決：R-5＝LM-143（第九批）；R-7＝LM-150～LM-152（第十批）；FAIL_CLOSED＝LM-154（第十二批）〕。對照表整合如下：
   > | `correction_causes` | 呈現 |
   > |---|---|
   > | `[x2_session_removed]` | LM-150＋LM-151 |
   > | `[settlement_close_corrected]` | LM-150＋LM-152；P(T) 收盤有變、而且 quant 尚未書面確認 R10-5 → FAIL_CLOSED |
   > | `[window_bar_corrected]` | `correction_is_display_neutral(chain)` 為真 → 不帶伴隨句；否則 FAIL_CLOSED |
   > | `[dividend_factor_corrected]` | FAIL_CLOSED |
   > | 兩個以上 | FAIL_CLOSED |
   > FAIL_CLOSED 的列以 `MaskedRecordView` 回傳，狀態句是 LM-154。`display.py` 的常數 `PT_CORRECTION_CONFIRMED: Final = False`，改成 True 的 PR 必須附 quant 書面確認的路徑，由 coordinator 核對。
5. **`n_disclosure_masked` 簽章**：採 S9-2，改為 `(claim, snapshot)`，取代提案 2 的三參數版。
6. **L974**：引文換成字面清單 L3442 的全文：
   > - LM-87「連續兩個檢查點（n＝{X0}、n＝{X}）的結果都不高於基準；其中作廢比例超過 5% 的檢查點，依最不利情境（作廢的預測全數視為不符）計算」由第 1 點的逐檢查點規則保證屬實，滿足 LM-87 的核可條件，不必重送。
7. **待決事項**：
   - 標〔已決〕：tech-architect 的 N-1 與 A-63 第 11 點；風控的 N-1；D_v 前置中的 N-1、R-5、R-7。
   - 新增 tech-architect：C9-7（照寫 C9-7 原句）；ADR-0028 CS-17 的同步修訂。
   - 新增 quant：C9-9（dirdef 凍結前）；R10-3 的補 bar 規則（凍結前）；R10-5 書面確認；`x2_shift_json` 累計語意書面確認；「更正翻轉」的比較基準；§4.2 的新揭露項。
   - D_v 前置加：C9-7、quant 的 R10-5 確認。
   - CEO 加一點：知悉 A-65 診斷欄位更正例外，屬揭露面放寬，已經風控核可。

**6-6　修訂紀錄與方向**
- 新段的開頭，寫明以下各點：
  - 來源 S1～S9 與優先序；
  - 和事先宣告 v0.12 同批；
  - 被取代的是 commit fd87063 的原文，逐字保留；
  - A-77 第 3 項的修訂紀錄逐字放 C9-8 的方向句。
- 本批各 A 號的方向：

| 方向 | A 號 |
|---|---|
| 不變 | A-23、A-59、A-78、A-79 |
| 收緊 | A-57、A-63、A-75、A-77（定義忠實度兩面，用 C9-8 字句） |
| 收緊＋有條件放寬 | A-65（R-7 提案 3，風控核可、CEO 知悉） |

- 累計方向統計：A-65 由「收緊」移到「含有條件放寬的兩面」，統計改為 **18／2／9／1／3**。

## 三、驗證

**讀過的檔案**
- 全文：S1、S2、S3、S4、S5、S6、S7、S8，以及我的 `2026-10-17-ADR-0027-r3系列套用疑義裁定-tech-architect.md`。
- ADR-0027 現行本文：L1-1599、L1647-1686、L1758-1877、L1940-2146。
- ADR-0028：L350-374（CS-17～CS-24）；另 grep 了 SE-2、`now`。
- 字面清單：LM-03、LM-04、LM-12（L3180、H2 L394）、LM-31～LM-33、LM-87（L3442）、LM-118～LM-130、LM-141、LM-143、LM-144～LM-146、LM-150～LM-152。
- 事先宣告：§4.2（L665-688）；另 grep 了 `session_calendar_conflict`。

**事實**
- ADR 本文目前還沒有 `ValidationBadgeMasked`、`n_disclosure_masked`、`correction_causes`；L797 仍是舊的 selector 簽章。
- CS-17 規定「`final_after(` 只能在 `is_final` 內被呼叫」；CS-19 規定 `session_calendar.py` 不可達 `app.data.market_panel`。
- 字面清單已經有 C9-2 與第十二批的連帶註記。

**推論**
- 落後窗口的長短、Q-3 日的年頻率、「n 只減不增」，都是依條文推出的，沒有實測。
- 甲案 (h5) 與 Q-3 日的 `inputs_not_ready` 沒有持久紀錄，是讀條文得出的缺口。

**範圍**：沒有修改任何檔案，沒有跑程式、測試或 git，沒有讀 `.env` 或 `*.db`。這是唯讀的架構文件，Codex 不適用。

## 四、下一步

**必須回送風控**
1. 第 3 項 C9-7：甲、乙、丙三案（推薦甲），以及待裁 (a)～(c)。D_v 前核可。
2. 第 4 項 Q-3：A、B、C 三案（推薦 A）。A 案改了第 3 項的公式，ADR 必須和一版事先宣告同批；並新增 `unobserved_weekday` 這個 kind 與 `post_unobserved_backfill` 這個 origin。D_v 前核可。
3. 第 5 項 (b) 的 ADR-0028 CS-17 同步修訂：另開 ADR-0028 commit，依 CS-21 通則送單項確認。
4. 知會即可：6-5 第 1 點的補登、第 2 點的白名單、A-65 改類與累計統計。都是收緊或記帳，風控若有異議再處理。

**屬收緊或照寫、不必回送的項目**
- 第 1 項全部：`ValidationBadgeMasked` 帶 `badge_fragment_id`（只能是 LM-153）；條件 ⑨⑪⑫⑭ 的條文與 FL。
- 第 2 項全部：`status_fragment_id` 釘為 LM-154；條件 ⑤⑥⑩ 的 FL；⑫ 的計數來源。
- 第 5 項 (a) `now` 注入；(b) ADR-0027 這一側的改寫；(c) 族群事件只限 fixture。
- S9-1、S9-2、S9-4 的採用。

**其他人**
- **tech-writer**：依第 6 項一次套用，和事先宣告 v0.12 同批落地，任何一份都不得單獨 commit。
- **quant（v0.12 同批）**：
  - 甲案相關：§9.3 第 18 點 (i)、第 19 點 ③、§9.2 N-1、§6.3；
  - L706、LG-20；R10-7 的撤銷規則；「更正翻轉」的比較基準；§6.4 第 2 點；
  - §4.2 新增揭露：X2 事件的 outcome 筆數、診斷欄位更正筆數、`rejected_count`、撤銷事件、LM-154 列數；
  - 兩項書面確認（累計語意、R10-5）；L1083 加註單位是比值。
- **coordinator**：
  - 核對清單加：6-4 的 38 處；
  - grep 檢查：`select_gate_fragments(` 只剩新簽章；LM-34、LM-73 只出現在修訂紀錄；結算端沒有引用 `correction_reason`；L974 和 L3442 逐字相同；L1366 含「與 FL-52 同一個 `gate_coverage_gaps`」；「沿用原 seed」只出現在修訂紀錄。

**相關檔案**
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-第九批TA待決項提案-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-第九批TA提案確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-R7對照表與更正鏈確認-tech-architect.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-R7對照表與更正鏈提案確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027與v0.11同批最終裁定-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-新定位第十一批字面逐字審-LM153-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-新定位第十二批字面逐字審-LM154-風控.md
- /home/user/AICompany/work/reviews/2026-10-17-ADR-0027-疑義裁定回送四項確認-風控.md
- /home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md

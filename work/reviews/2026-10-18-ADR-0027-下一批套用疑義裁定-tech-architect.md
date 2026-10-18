# ADR-0027 下一批套用疑義 1～27 裁定（tech-architect）

- 審查者：tech-architect（唯讀）
- 日期：2026-10-18
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 一、本次結論

- 27 項都已裁定，第 1～8 項附逐字字句，tech-writer 照改即可。
- **只有一項要回送風控**：第 8 項。我在 `session_calendar_conflict.evidence` 這個封閉列舉裡新增一個值，並定義 `post_unobserved_backfill` 的 payload。屬補定義，方向不變，只影響稽核欄位，不影響觀察日、顯示或計數。請風控做單項確認，可以和本批同批落地。
- **知會風控即可、不必回送（三項）**：
  - 第 3 項：我把 Q12-1 的計數單位也套到「順延筆數」。計得只會更多，方向是收緊。
  - 第 4 項：R10-5 已由 V12-12 確認，ADR 改寫成已生效。依據是風控 v0.12 審查第一節：「實際生效要等 v0.12 和下一批 ADR 同批 commit」。字面清單 LM-154 條件 ①、⑩ 的「R10-5 確認前」那一格要加註失效，字面不動。
  - 第 2 項：M-11 的「新增 8 張表」要改成 10 張。M-11 是 CEO 核可項，所以知會 CEO。
- **其餘各項都是一致性更正或照寫，不必回送。** 其中第 5、6、7、12 項，是讓 ADR 和風控已核可的 C9-1、C7-1～C7-6、Q3-1、CS-17 字句一致，沒有改變語意。
- **兩份文件的名稱與公式對照結果**：
  - 觀察日最終式：ADR L470 和 v0.12 L1461、L1497、L1498 逐字相同。
  - 九個名稱拼寫一致：`final_sessions()`、`observed_sessions()`、`unobserved_weekday`、`post_unobserved_backfill`、`holiday_coverage`、`listed_as_trading_day`、`run_evidence.prefinal_ok_runs`、`void_late_data_count`、`correction_causes`。
  - 有一處寫法不同：v0.12 L1497、L1498 把 (i) 寫成「`recorded_at ≥ final_after(TW, d)`」，ADR A-77 第 1 項已改成「`is_final(TW, d, run.recorded_at)` 為真」。兩式等價，但逐字比對會判成核對失敗，請 quant 同批補一個括號註（見「下一步」）。
- **另外有四個附帶發現**（附帶 A～D，見第二節末）。最重要的是附帶 A：工作樹的 D-1 讓 `app/outlook/inputs.py` 呼叫 `app/forecast` 裡的 `observed_sessions()`。recorder 本來就呼叫 outlook，這樣會形成 forecast 與 outlook 的循環依賴，要改成由呼叫端以參數傳入。

## 二、逐項裁定

行號都是工作樹的編輯後行號。被取代的原文一律逐字進修訂紀錄新段，掛在括號所列的 A 號下。

**第 1 項｜N-1 的 L559**：採 tech-writer 的做法 (a)。只把括號改成下面這樣，和 v0.12 的「N-1 不再擋 D_v」對齊（A-77；不變）：
> 〔已決：甲案已核可（風控 2026-10-17 第九批 TA 提案確認；風控 2026-10-18 v0.12 審查第四節），N-1 不再擋 D_v〕

L1868 的 N-1 括號也換成同一句。

**第 2 項｜`void_late_data_count` 與表數**（一致性更正；R10-3（Q12-4）是風控逐字文，R10-1 的欄位列表必須和它一致）
- L298 改為（A-65）：
  > - `forecast_correction_job_end(correction_job_id PK, rechecked_count, changed_count, rejected_count, void_late_data_count, ended_at)`：作業結束時寫入。沒有 end 列代表作業中斷；這時該作業的 `recheck_range_json` 由下一個作業完整重跑，qa 核對涵蓋率。`void_late_data_count` 是作廢之後才補到資料的筆數（見 D-11.4 第 11 點 (h)「作廢列不因之後補到的資料而 supersede」；事先宣告 v0.12 V12-20），不屬於 `rejected_count`。
- 表數：D-3 現在是 15 張表（原 13 張，加 `forecast_correction_job`、`forecast_correction_job_end`）。
  - L87 的「表數多（13 張）」改為「表數多（15 張）」；
  - L1363 的「13 張表」改為「15 張表」；
  - M-11（L200）的「新增 8 張表」改為「新增 10 張表（第九、十批加 `forecast_correction_job`、`forecast_correction_job_end`）」。
  - 這三處掛 A-79，方向不變。M-11 在 CEO 待決清單第 1 點，所以 CEO 待決加一句：「M-11 的表數隨第九、十批由 8 張改為 10 張（知悉）」。

**第 3 項｜X2 筆數的計數單位**：要對齊 Q12-1。理由：鏈尾如果是後來作廢的列，可能不帶 `x2_shift_json`，只讀鏈尾會少算。
- L551 句尾改為（和 v0.12 L1463 逐字相同；A-77；不變）：
  > 這個數字由 `x2_shift_json` 逐列數出，不另存欄位；每筆預測只計一次：更正鏈中任一列的 `x2_shift_json.x2_event_ids` 含該 X2 事件，就計入（事先宣告 v0.12 V12-04；風控 v0.12 確認 Q12-1）。
- L511 末句改為（A-77；收緊）：
  > - 先順延、後來又因其他原因 supersede 的列，同樣帶累計值，不得改成 null。§4.2 的順延筆數依同一計數單位：每筆預測只計一次，更正鏈中任一列的 `x2_shift_json` 非 null 就計入（比照風控 v0.12 確認 Q12-1）。
- v0.12 §4.2 的「X2 確認後順延的結算筆數」沒有寫計數單位，所以兩份不矛盾。建議 quant 補上同一個單位，屬 suggested。

**第 4 項｜R10-5 已確認**：採讀法 (b)，因為兩份同批生效。若留著 `PT_CORRECTION_CONFIRMED = False`，commit 當下就會和 V12-12「不再一律 fail-closed」矛盾。以下都掛 A-65，方向依風控 R10-5 附條件核可。
- L988 改為：
  > - FAIL_CLOSED 的情形是封閉的，只有以下三種：兩個以上的原因；`[dividend_factor_corrected]`；`[window_bar_corrected]` 但 `correction_is_display_neutral(chain)` 為假。`[settlement_close_corrected]`（含 P(T) 收盤有變）依對照表用 LM-150＋LM-152，不屬 FAIL_CLOSED（R10-5 依事先宣告 v0.12 V12-12 書面確認，與本 ADR 同批生效）。
- L1051 改為：
  > | `[settlement_close_corrected]` | LM-150＋LM-152（P(T)、P(T+h) 的收盤更正都適用；R10-5 依事先宣告 v0.12 V12-12 書面確認，與本 ADR 同批生效） |
- L1056 改為：
  > FAIL_CLOSED 的列以 `MaskedRecordView` 回傳，狀態句是 LM-154。不設 P(T) 更正的確認旗標或常數：R10-5 的確認與本表同批生效；日後若撤回 V12-12 的確認，須修訂本表並送風控。
- FL-22 (c)，L1487：「四格——…；R10-5 確認前、P(T) 收盤有變的收盤更正。」改為「三格——除權息因子；兩個以上原因；未豁免的診斷更正。」
- FL-22 (c)，L1491 改為：
  > - 對照格：`[x2_session_removed]`；`[settlement_close_corrected]`，P(T) 收盤有變、P(T+h) 收盤有變各一格；豁免成立的 `[window_bar_corrected]`。這四格都找不到 LM-154；兩個收盤更正格的狀態行等於 LM-150 代入 LM-152 的全文。
- coordinator 在字面清單 LM-154 的條件 ①、⑩ 行尾加註：
  > 〔R10-5 已依事先宣告 v0.12 V12-12 確認，與 ADR 下一批同批生效：① 的「quant 確認 R10-5 之前 P(T) 的 `settlement_close_corrected`」與 ⑩ 的第四格不再適用；字面不動〕

**第 5 項｜FL-52 斷言 (1) 與 (7)**：以 C9-1 為準，(1) 補上條件。這是一致性更正（A-63）。
- L1601 改為：
  > - (1) `outlook_block`、G_eff＝{`forward_n_below_min`}、`display_state = gated`、同一列 snapshot 的 `status` 是 `unverified`（未驗證），而且 `n_masked` 為假 → 選 LM-12，不選 LM-120；
- L1607 改為：
  > - (7) G_eff＝{`forward_n_below_min`}、`gated`、`status` ≠ 未驗證，或 `status` 為 None（沒有 snapshot）→ 選 LM-120，不選 LM-12；
- L1597 的「`outlook_block` 的列舉再 × `status` 四態。」改為「`outlook_block` 的列舉再 × `status` ∈ 四態 ∪ {None}。」

**第 6 項｜甲案擴及三個 scope 後，仍只寫族群的句子**：都改。依據是 C7-1、C7-4、C7-6，屬一致性更正（A-63、A-57）。
- L793 改為：
  > - 不按 claim 篩選：任一筆成立，所有族群 claim 的 `pa9_holds` 都適用；`n_disclosure_masked`（以及由它決定的 `ValidationBadgeMasked`、`validation_refresh_pending`）對大盤、族群、個股的所有 claim 都適用（C9-7 甲案）。
- L841 改為：
  > - 同一區塊的閘門句代入 LM-144，交代筆數待彙整：族群經 LM-122／LM-123／LM-126／LM-127（`covers = {forward_n_below_min}`）；大盤與個股經 LM-120／LM-121（`covers = {validation_refresh_pending}`，風控 2026-10-18 C7-4）。
- L843 句首加「（族群）」，句尾加「大盤與個股的讀法見下一點（C7-6）。」
- L944 改為：
  > - G_eff 的定義見 A-57 (iv)。大盤與個股的 G_eff ＝「判定 `display_state` 的同一列最新 daily snapshot」的 `gate`；`n_disclosure_masked` 為真時再加入 `validation_refresh_pending`；沒有 snapshot 時依 A-57 (iv)「查詢時閘門」的「沒有 snapshot」子點。
- L1099 改為：
  > - **查詢時的有效集合 G_eff**：G_eff ＝ snapshot 的 `gate`；族群的 `pa9_holds` 依 RC′-2 為真時，再加入 `forward_n_below_min`；大盤與個股的 `n_disclosure_masked` 為真時，再加入 `validation_refresh_pending`（見下方「查詢時閘門」）。沒有 snapshot 的大盤與個股依該條的「沒有 snapshot」子點。
- L1101 改為：
  > - 這個查詢時調整只可能把 `shown` 變成 `gated`（族群經 `forward_n_below_min`；大盤與個股經 `validation_refresh_pending`），不得有其他方向（性質測試，三個 scope）。
- L1107 後半句改為「性質測試見上方『查詢時的有效集合 G_eff』一點。」這一改同時處理第 24 項的自我引用。
- L1597 的「族群另外 × `n_masked` ∈ {真, 假}」改為「× `n_masked` ∈ {真, 假}（三個 scope 都適用；C9-7 甲案）」。
- L1605 的斷言 (5) 句首加「（族群）」，句尾加「大盤與個股的對應斷言見下方『大盤與個股的遮蔽 FL』(a)。」

**第 7 項｜A-77 第 3 項第三子點與第 10 項的「原公式」**：都改成精確寫法（A-77；不變）。
- L473 改為：
  > - 依第 5 項，X2 確認當下 d ∉ (i)，所以就 X2 確認日這一項而言，上式在確認當下與 fd87063 版（事先宣告 v0.11）的「(i) ∪〔(ii) − X2 確認日〕」相同，只在第 12 項的情形下不同。未觀察平日那一項見第 10 項：登記當下與不扣除未觀察平日的式子相同，只在登記之後 d 因補寫進入 (i) 或 (ii) 的情形下不同。
- L525 改為（「原公式」換成 v0.12 L1497 的用語）：
  > - 登記當下 d ∉ (i) ∪ (ii)，所以上式在登記當下與不扣除未觀察平日的式子「〔(i) ∪ (ii)〕− X2 確認日」相同；只在登記之後 d 因補寫進入 (i) 或 (ii) 的情形下不同。
- v0.12 L1497 的「上式在確認當下與 v0.11 的公式相同」也有同樣的不精確，建議 quant 同批加「就 X2 確認日這一項而言」，不必回送。

**第 8 項｜`post_unobserved_backfill` 的 payload**（A-77；補定義、方向不變；**要回送風控單項確認**）
- L480 的 `evidence` 列舉改為「`evidence ∈ {weekend, official_holiday, independent_source_absent, registered_unobserved_weekday}`」，句尾加：「`registered_unobserved_weekday` 只用於 `origin = post_unobserved_backfill`（見第 10 項）。」
- 第 10 項「固定排除」第二子點之後加一點：
  > - **`post_unobserved_backfill` 的 payload**：`session_date`；`origin`；`evidence = registered_unobserved_weekday`；`unobserved_event_id`（登記該日的 `unobserved_weekday` 事件）；`backfill_via ⊆ {set_i, set_ii}`，非空；
  >   - 進入 (i) 時，帶使 d ∈ (i) 的 ok run 中 `run_id` 最小者的 `run_id`、`recorded_at`（比照第 12 項）；
  >   - 進入 (ii) 時，受檢 bar 的參照指使 d ∈ (ii) 的大盤 `is_final_bar` 列（`source`、`as_of`、`fetched_at`，比照第 7 項的 `checked_bar_ref`）；只進入 (i) 時為 null。
  >   - payload 由寫入函式自行填入，不接受呼叫端傳入；偵測在第 10 項「登記先於使用」的同一個交易內完成。
  >   - 同一個 (`session_date`, `origin`) 只寫一次；之後 d 再經另一個集合進入，也不另寫。§4.2 ④ 以日數計。
- FL-19 (i) 加一格：分別只進入 (i)、只進入 (ii)、兩者都進入，`backfill_via` 與參照欄位都正確，而且只寫一筆。

**第 9 項**：維持放在第 10 項底下（L535），不另立 F-10。這條是局部的重審條件，和 v0.12 L722 同一列並陳；另立一個 F 號會變成兩處定義。
**第 10 項**：
- 〔已決〕的標註都可以保留，但每一處括號都要寫明依據的檔案或 V 號。查過的都有依據：風控 C9-7／Q-3 確認、v0.12 審查、V12-08、V12-11、V12-12、V12-19、V12-20。
- L1868 的「Q-3（平日、非休市日、既不在 D-8.1 (i) 也不在 (ii) 的日期）」改為「未觀察平日（風控 2026-10-17 疑義裁定回送 Q-3）」，避免和事先宣告 §7.2 的 Q-3 撞號（Q3-1）。
- ADR-0028 CS-17 那一行的〔已決〕，前提是兩個 commit 同一次 push、ADR-0028 在前；否則先拿掉。
**第 11 項**：
- D-11.1 的「由 quant 確認後登記」改為「已由 quant 登記（事先宣告 v0.12 V12-08）」。
- L1017 的「第九批提案 4 第 2 條的『結算…讀 `base_close`』」改為「A-63 RC′-2 子點第 2 條約束的 `base_close`」。
- 方向不變。
**第 12 項**：L498 整句換掉（A-77；不變）：
> - `final_after(` 的呼叫位置依 ADR-0028 CS-17（風控 2026-10-18 單項確認）：`final_session_evidence` 只把 `final_after` 的回傳值原樣寫入稽核 payload，不參與任何判定；X2 寫入函式判定「d ∉ (i)」只經 `final_sessions()`，不得拿 `set_i_check.final_after` 比較時戳。本項依賴 ADR-0028 CS-17 的同步修訂；兩者同一次 push，ADR-0028 的 commit 在前。

條件：如果 coordinator 不能讓兩者同一次 push，就保留原句（原句在那種情況下仍然屬實）。待決事項 TA 的「CS-17 同步修訂」一行，依同一條件標〔已決〕。
**第 13 項**：r3 系列段落不改寫。只在 L2118 句尾加：
> 〔第九、十批更新：A-77 標註與累計統計（18／2／9／1／3）見修訂紀錄第九、十批段〕
**第 14 項**：以 C9-10 為準（S2 優先於 S1）。「回應欄位」那一句改為：
> 凡依下方 LM-146 條件帶 LM-146 的紀錄列，以及單筆展望區塊（LM-93／LM-115），都帶 `threshold_display`

方向是收緊。
**第 15 項**：連同附帶 A 一起處理，見本節末。
**第 16 項**：接受。另加一點 Q-3 的兩面後果（A-79；不變）：
> - （未觀察平日 A 案）**未觀察平日固定排除**：登記之後即使補到資料也不回到觀察日。另一面：這一天若其實是交易日，跨越它的紀錄 T+h 會多跨一個實際交易日，偏差留在統計中，以 §4.2 的四項揭露與 data-engineer 根因查證緩解（Q3-5）。
**第 17 項**：接受。v0.11 行號是引用當時的文字，保留並標「v0.11」，不改成 v0.12 行號。
**第 18 項**：全部接受，語意不變。
**第 19 項**：接受。字面已核可，限制已經解除，不必擴大 scope。
**第 20 項**：接受。
**第 21 項**：照寫三格子例：
> - `[x2_session_removed]` 而新列的 `end_price_json.session_date` 不晚於前一列，或 ≠ `shifted_t_plus_h` → 拒絕；
> - `[settlement_close_corrected]` 而任一 `session_date` 改變、兩個收盤值都沒變、或 `window_factors_json` 改變 → 拒絕（各一個子例）；
> - `[dividend_factor_corrected]` 而任一 `session_date` 改變、或 `window_factors_json` 沒變 → 拒絕。
**第 22 項**：接受。
**第 23 項**：接受。
**第 24 項**：已在第 6 項處理。
**第 25 項**：接受。這是風控核對項的落地。
**第 26 項**：A-34 的方向標「不變（引用）＋收緊（附帶 A 的 import 限制）」。A-34 是 r2 的條號，不影響 r3 的累計統計。
**第 27 項**：接受。

**附帶發現（tech-writer 照改，都不必回送）**
- **A｜循環依賴**（A-34；收緊）：
  - L242（`inputs.py` 列）的句子改為：
    > σ_d 序列的觀察日由呼叫端（recorder）以參數傳入：`observed_sessions(as_of=cutoff(T))` 的結果（事先宣告 v0.12 V12-19）。`app.outlook.*` 不得 import `app.forecast.*`（recorder 呼叫 outlook，反向會形成循環）。
  - L243（`volatility.py` 列）的句子改為「只吃已依 V12-19 取好的日報酬序列，不讀觀察日」。
  - L241 加：「`observed_sessions(*, as_of)`：`as_of` 之後才寫入的 run、X2 事件、未觀察平日登記都不計入；`as_of` 為 None 時取當下。」
  - FL-41c 加一條 import graph：`app.outlook.*` 不可達 `app.forecast.*`。
- **B｜重複句**：L465 的「由 `app/data/session_calendar.py` 的單一函式提供。」和下一子點重複，刪掉，只留子點。
- **C｜FL-52 L1631**：句尾加「（依 R10-3／V12-20，寫入函式會拒絕這種鏈；本格以 fixture 直接插入，並另斷言寫入函式拒絕）」。
- **D｜FL-22 (a)**：L1483 改為「每個值恰好對應 LM-151、LM-152、FAIL_CLOSED、豁免（只限 `[window_bar_corrected]`，依 `correction_is_display_neutral`）四者之一」。
- **另外**：待決事項 TA 加一條：「(h5) 候選 T＝d 記 `inputs_not_ready` 的計數來源（風控第九批 S9-3，suggested；不擋 D_v）」。L558 已引用這一條，但待決清單裡沒有。

## 三、驗證

**讀過的檔案**
- 全文：tech-writer 回報、風控 C9-7／Q-3／CS-17 確認、風控 v0.12 審查、quant v0.12 併入 Q-3 回報。
- ADR-0027 工作樹：L236-247、L440-569、L786-855、L895-934、L975-1069、L1092-1131、L1478-1493、L1590-1637；另 grep 了表數、`PT_CORRECTION_CONFIRMED`、N-1、S9-3、M-11、方向統計。
- ADR-0028 工作樹：grep 了 CS-17 L355-357 的 `final_session_evidence` 三子點，確認和風控逐字文一致。
- 事先宣告 v0.12 工作樹：L55-85（修訂列）、L712-722（§4.2）、L1162、L1280、L1460-1467、L1497-1498；另 grep 了 `independent_source_absent`、`evidence`、順延筆數。

**事實**
- 公式與九個名稱兩份一致。v0.12 沒有定義 `post_unobserved_backfill` 的 payload，也沒有列出 `evidence` 的值，所以第 8 項只動 ADR。
- v0.12 L1497、L1498 的 (i) 寫法和 ADR 不同（等價）。
- D-3 共 15 張表。

**推論與範圍**
- 附帶 A 的循環依賴是依 D-1 的職責推出的，`apps/` 還沒有實作，沒有程式可以查。
- 沒有修改任何檔案，沒有跑 git，沒有讀 `.env` 或 `*.db`。我沒有用 git 核對 6313632 和工作樹是否一致。

## 四、下一步

**回送風控**
1. 第 8 項：`evidence` 新增 `registered_unobserved_weekday`，以及 `post_unobserved_backfill` 的 payload。請做單項確認，方向不變，可以和本批同批。

**知會（不必回送）**
- 風控：
  - 第 3 項：L511 套用 Q12-1 的計數單位（收緊）；
  - 第 4 項：R10-5 同批生效的改寫，以及 LM-154 條件 ①、⑩ 的加註。
- CEO：M-11 由 8 張改為 10 張。

**tech-writer**：照第二節改第 1～8、10～14、16、21、24、26 項與附帶 A～D。被取代的原文進修訂紀錄新段。

**quant（v0.12 同批，方向都是不變，不必回送）**
1. L1497、L1498 的 (i) 加括號註：
   > 「（判定經 ADR-0028 CS-17 的 `is_final(TW, d, recorded_at)`，與 `recorded_at ≥ final_after(TW, d)` 等價；ADR-0027 A-77 第 1 項）」
2. L1497 的「上式在確認當下與 v0.11 的公式相同」加「就 X2 確認日這一項而言」。
3. suggested：§4.2 的「X2 確認後順延的結算筆數」補 Q12-1 的計數單位。

**coordinator**
- 核對清單加：
  - L298 有 `void_late_data_count`；
  - grep「13 張」＝0、「新增 8 張表」＝0；
  - grep `PT_CORRECTION_CONFIRMED`＝0（修訂紀錄除外），「尚未書面確認 R10-5」＝0；
  - FL-52 (1) 含 `unverified` 與 `n_masked` 為假；
  - grep「只可能把族群的」＝0、「所有族群 claim 都適用。」＝0；
  - L480 的 `evidence` 列舉有新值；
  - L498 是新句，ADR-0028 commit 排在前面，兩者同一次 push；
  - `app.outlook.*` 不可達 `app.forecast.*` 的 FL 在。
- 等第 8 項風控確認之後，再同批 commit ADR-0027、事先宣告 v0.12 與 ADR-0028 CS-17。

**相關檔案**
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/work/reviews/2026-10-18-ADR-0027-下一批套用-tech-writer回報.md
- /home/user/AICompany/work/reviews/2026-10-18-ADR-0027-C9-7與Q-3及CS-17提案確認-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-事先宣告v0.12草稿審查-風控.md
- /home/user/AICompany/work/reviews/2026-10-18-事先宣告v0.12併入Q-3未觀察平日-quant回報.md
- /home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md

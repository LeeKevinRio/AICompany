# LM-70 但書 PM 側確認與 date_anomaly 驗收條件草案（product-manager）

- 審查者：product-manager（只讀，未改檔）
- 日期：2026-10-17
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

## 本次結論
PM 側表態：成立。`date_anomaly` 時，庫存頁與個股頁價格照常顯示，估值與總額照常計入，LM-70「只在異常時仍顯示價格才成立」的但書可以解除。但 PRD 對此缺驗收條件，總額需要同區塊揭露，這兩點要補。我沒有發現 PRD 有條文與此衝突。

理由有三點，皆為 PM 判斷：
1. PRD §1.3 成功指標寫「任何價格旁有明確的估值狀態」。價格存在、日期不確定，用標籤把日期不確定講明，比把價格換成「—」更符合這條。「—」是 `no_data` 的語意（AV-16），日期異常不是缺價。
2. PV-6 要求缺資料就缺席、不得用替代估法補。這裡價格本身存在，我們沒有替代或補值，只是如實標示，所以不違反。
3. 隱藏價格會讓該部位整個掉出總額，結果是 `partial` 的涵蓋範圍變了，卻沒有原因可說明。這比「照常計入加揭露」更難讓使用者看懂。

以上是 PM 的產品判斷。風險控制面的接受度由風控確認，我不替風控定。

## 各部門回報
**PRD 對照**

| 項目 | 結果 |
|---|---|
| 與 `date_anomaly` 衝突的 AC | 無。AC-F9b2-1 管幣別／代號不符，走未估值路徑，與日期異常無關。AC-B4b-1 只管 `no_data`，不涵蓋日期異常。 |
| 缺漏 1 | NP-B5a 只列四種狀態（收盤、盤後、休市、前一收盤參考）。`lagging`、`provisional_today`、`date_anomaly`、`session_unconfirmed`、`pre_open` 在 PRD 全文找不到，所以沒有任何 AC 規定異常時價格與總額怎麼處理。AC-B5a-6 只管「同區塊可見日線收盤揭露」。 |
| 缺漏 2 | AC-B4b-2 寫「總額只含可估值部位」。`date_anomaly` 算不算「可估值」，PRD 沒說。ADR-0028 D-4 補充說算（CS-2、CS-4），PRD 要同步。 |
| 缺漏 3 | PRD 的 NP-B5a 寫「持股現價旁」，沒有明寫個股詳細頁的價格要不要帶估值狀態。我查不到個股頁現有的價格呈現，不替它下結論。 |
| 缺漏 4 | ADR-0028 D-4 補充寫明「`date_anomaly` 的總額揭露字面由 PM 與 creative-lead 另案處理」。PM 的立場：比照 LM-69 的做法（用到暫定價的總額，同區塊要可見），總額區塊要有揭露。字面由 creative-lead 起草、風控逐字審，我不寫字面。 |
| 視覺規範 | `work/stock-desk-新定位-視覺規範-2026-10-16.md` 沒有估值狀態標籤的位置或樣式規則，也沒有與此衝突之處。第 2.5 節規定系統狀態不得用紅綠，所以 LM-70 標籤須用中性樣式。價格數字本身仍可依價格方向用漲跌色。日期格式用 `MM/DD`，與 LM-70 的 `{MM/DD}` 一致。 |

**需要別人回答的事**
- **tech-architect**：CS-4 規定 advice、plan、outlook、keylevels 不讀 `valuation_state`。這表示 `date_anomaly` 的那根 bar 照樣進入個股頁的關鍵價位與行動計畫，而且該處沒有異常標示。請確認這是設計如此，還是要在個股頁加一個標示。這牽涉風控的關心範圍，建議一併送風控。
- **tech-architect**：個股詳細頁的價格是否與庫存頁共用同一個估值狀態元件。

## 驗證
讀了 PRD §1.3、§3、§4、Phase 1（NP-B4／B4b／B5a、F-9b2）、字面清單 L2365、L2389、ADR-0028 D-4、D-5、CS-2、CS-4、CS-16，以及視覺規範的色彩規則。PRD 第 348 至 878 行我只用關鍵字搜尋，沒有逐行讀，所以「PRD 全文找不到新狀態」這句只靠關鍵字搜尋成立。未讀 `.env` 或 `.db`，未改任何檔案。

**驗收條件草案（草案，待風控確認；編號暫定，接在 AC-B5a-6 之後）**
- AC-B5a-7（庫存頁價格）：Given 某持股的價格狀態為 `date_anomaly`（任一 `sub_reason`）；When 在 375 與 1280 寬度開啟庫存頁；Then 該價格照常顯示，旁邊逐字顯示 LM-70（含該價格的 `{MM/DD}`），不顯示「—」，不標為「收盤價」，不同時出現其他估值狀態字面；該持股的市值與損益以此價計算。
- AC-B5a-8（總額計入與揭露）：Given 庫存中至少一檔為 `date_anomaly`，其餘為其他狀態；When 查看總額區塊；Then 總額包含該部位，`status` 依既有規則為 `partial` 或 `complete`；總額同區塊可見一句揭露（字面待 creative-lead 起草、風控逐字審），揭露不可收合；沒有任何 `date_anomaly` 時不出現該揭露。
- AC-B5a-9（全部持股皆異常）：Given 所有持股皆為 `date_anomaly`；When 查看總額；Then 總額照常計入、不為 null、`status` 不是 `no_data`，揭露照 AC-B5a-8。
- AC-B5a-10（個股頁一致）：Given 個股詳細頁顯示某標的價格，且其狀態為 `date_anomaly`；When 開啟該頁；Then 價格與 LM-70 同區塊、不必展開即可見，價格與日期和庫存頁一致（PV-52）。
- AC-B5a-11（字面不洩漏原因）：Given `date_anomaly` 的任一 `sub_reason`（`future_date`、`before_open`、`official_conflict`、`not_a_session`、`unconfirmed_session`）；When 檢視畫面；Then 字面一律是 LM-70，不出現 `sub_reason` 的名稱或原因（對應 ADR-0028 D-4）。
- AC-B5a-12（樣式）：Given 任一 `date_anomaly` 標籤；When 檢視；Then 標籤不使用漲跌色，樣式遵守視覺規範第 2.5 節。

## 下一步
1. **tech-architect**：回答上面兩個問題（CS-4 對個股頁關鍵價位的影響、個股頁是否共用元件）。
2. **風控**：確認上列 AC 草案，特別是 AC-B5a-8 的總額揭露必要性，以及 CS-4 的標示問題。
3. **creative-lead**：起草總額區塊的 `date_anomaly` 揭露字面，送風控逐字審。
4. **PM（我）**：待風控確認後，在 PRD 的 NP-B5a 補列新增狀態與 AC-B5a-7～12，並修訂 AC-B4b-2 對「可估值部位」的定義。因為你要求只回報不改檔，我尚未動 PRD，並留變更紀錄通知下游。LM-70 的但書狀態可標為「PM 側成立，待風控確認 AC」。

相關檔案（皆為絕對路徑）：
- `/home/user/AICompany/work/stock-desk-新定位-PRD-2026-10-16.md`（NP-B5a L253-269、NP-B4b L226-235）
- `/home/user/AICompany/work/stock-desk-新定位-字面遷移清單-2026-10-16.md`（L2365、L2389）
- `/home/user/AICompany/docs/adr/0028-stock-desk-估值狀態判定與交易所時段參數.md`（D-4 補充 L155-156、D-5 L175、CS-2、CS-4、CS-16）
- `/home/user/AICompany/work/stock-desk-新定位-視覺規範-2026-10-16.md`（第 2.5 節）

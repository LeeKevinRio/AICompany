# N-17 因子修訂觸發提案

- 審查者：tech-architect
- 日期：2026-10-24
- 轉存：coordinator，逐字轉存 subagent 最終回報

---

# N-17 因子修訂觸發提案（tech-architect，2026-10-24）

我沒有寫檔、沒有跑指令、沒有 commit。下面的行號是我今天讀到的 working tree 版本。我沒有跑 git，所以無法確認它與 HEAD 是否相同；檔尾已含 N-109、N-110 小批的修訂紀錄段（行 5480-5506）。每一處 old 都用 Grep `-o` 確認恰好 1 處。

## 一、本次結論

1. **提案完成，要送風控單項確認，不需要 CEO 裁決。** 做法是比照 R-11 的讀端輪詢，新增「晚到資料的觸發」第 10 點。兩者共用同一個 W、`run_max`、`market_scan_to` 和還原保護，寫端不動。
2. **判定時版本**：取「Ω 中含此 key、`run_id` 最大的 ok run」的那一列，不取聯集。除息日前被後續 run 漏列的事件，視為撤銷。這條規則寫進 D-4 第 2 點，結算、更正、診斷都依它；預測端是否適用，待 quant 確認。
3. **歸屬只看鏈尾 `status`，不看變化類別。** 鏈尾 `resolved` 歸 `dividend_factor_corrected`；鏈尾作廢只進 `forecast_void_late_diag`（`dividend_factor`）。所以「空白到有值」在現行模型下幾乎都走診斷。
4. **限制 f**：新增 (丙) 支，不採「不 supersede、只揭露」，因為那會抵觸 §6.4 與第 6 點原文的禁止。**限制 d**：擴充第 3 點的配對窗，加入 `prev_close_session`。
5. **限制 a、b 不升 CEO 裁決，列 CEO 知悉，以揭露處理。** 限制 c 是撤銷規則的前提，設為 D-9 實作前的查證閘門（N-117 暫）。
6. **預期量**：現行管線下本觸發的命中預期接近 0【推論】。理由是除息日前的修訂幾乎都在結算判定視圖建立之前就已擷取。所以 N-17 主要是補齊 §6.4 的機制與揭露；實際的資料缺口集中在 a、b 兩項，而這兩項都不是觸發能補的。
7. **事先宣告必須同步**：§4.2 (iv) 原文寫著「修訂本點之前一律標『未涵蓋，不計』」，所以 ADR 這批要和事先宣告 v0.30（暫）同一個 commit 落檔。

## 二、各部門回報

### tech-architect（本人）

#### A. 評估摘要
- **採用**：讀端輪詢，共用 W。版本取最新含 key 的 run，除息日前消失視為撤銷。比較基準是「前一版 run」。歸屬依鏈尾 `status`。新增 (丙)。限制 d 用 `prev_close_session` 擴充配對。`window_factors_json` 只存數值投影。
- **否決**：聯集語意；把消失改記成因子不可用；不 supersede、只揭露；把 (丙) 走待重算路徑；在 N-17 內改冪等略過或另接資料源。

#### B. 方案比較

| 議題 | 方案 | 優點 | 缺點 | 風險 | 裁定 |
|---|---|---|---|---|---|
| 偵測架構 | A1 讀端輪詢，與 R-11 共用 W | 不另起水位；首尾相接、還原保護都沿用 | 要讀兩份列內容 | 低 | **採** |
| | A2 寫端在 pit_snapshot 記 diff | 讀端簡單 | 違反「寫端不動」、牽動 ADR-0012 | 中 | 否 |
| | A3 每次結算全量重算比較 | 不用掃描 | `triggers_json` 沒有來源參照，違反 §6.4 第 2 點 | 高 | 否 |
| (i) 判定時版本 | B1 聯集（現行 `ex_dividend_announcements`） | 已有程式 | 撤銷或改期的舊事件會留下；同 key 多版沒有取捨規則 | 高 | 否 |
| | **B2 Ω 內含 key 的最大 `run_id` 那一列，加撤銷規則** | 可重現（只比序號）；改期自然處理 | 撤銷規則依賴限制 c | 中（設查證閘門） | **採** |
| | B3 最早版本 | 穩定 | 會忽略判定視圖內已知的修訂 | 高 | 否 |
| 消失怎麼處理 | C1 除息日前消失視為撤銷 | 照「最新快照」字面；不改作廢定義 | 來源單批回應不完整時，會少套一個因子【推論】 | 中（WARNING 加逐筆揭露） | **採** |
| | C2 改記因子不可用 | fail-closed | 改變作廢定義（要事先宣告登記）；c 不成立時會大量作廢 | 高 | 否 |
| | C3 保留最後版本 | 不會漏套 | 改期會讓同一事件被套兩次 | 高 | 否 |
| 比較基準 | **D1 對前一版 run** | 一次掃描；完備（見照實並陳） | 會多記 | 低（多記的筆重算後不寫） | **採** |
| | D2 逐列對該列的判定時版本 | 精確 | 每列都要建一次視圖，結果與 D1 相同 | 低 | 否 |
| (iv) 限制 f | **F1 新增 (丙)** | 符合 §6.4 第 3 點「有變的筆新增一列」 | 放寬 N-27 的拒絕 | 中 | **採** |
| | F2 不 supersede，只揭露 | 改動小 | 抵觸第 6 點「不得以揭露代替」 | 高 | 否 |
| | F3 列入待重算 | 有重查路徑 | `pending_json` 必含 `x2_session_removed`，改動大 | 中 | 否 |
| (iii) 限制 d | d1 把因子窗改為 (T, T+h] | 數學上正確，缺口消失 | 要改事先宣告「窗內」的意義（可能有放寬面） | 中 | 不採，改成問 quant |
| | **d2 第 3 點配對加 `prev_close_session`** | 不改任何定義；只會多記 | 要求 `window_factors_json` 記前收 session | 低 | **採** |
| | d3 不涵蓋，只揭露 | 最省事 | 留下缺口 | 中 | 否 |
| (v) 限制 a | 改冪等略過（ADR-0012、N-16） | 解析度提高 | 跨 ADR、要 CEO；而且同 session 首筆之後的修訂多半根本沒擷取，這不是觸發問題 | 中 | 不在 N-17 內做；N-16 改變時重查 |
| (v) 限制 b | 另接除息日後的資料源 | 能涵蓋事後更正 | `TWT49U` 不存在、`t187ap45_L` 沒有除息日【事實：`providers.py:5-22`】，沒有已知的免費 OpenAPI 來源 | 成本未知 | 不做；列 CEO 知悉、N-118（暫） |
| 限制 e | 寫端改 key | 根治 | 改寫端，要另出 ADR | 中 | 另案 N-119（暫） |
| | **讀端做 run 層 `stored_row_count` 對 `row_count`** | 不動寫端 | 只能發現，不能定位到哪一檔 | 低 | **採**（口徑先查證） |

#### C. 逐項裁定

**(i) 判定時版本**：寫進 D-4 第 2 點（落字稿 E7）。
- Ω 由各自的界定值決定：結算評估是 `run_id ≤ R`；更正作業與診斷是 `run_id ≤ market_scan_to`；預測端是 D-4.1 的可見性規則。
- 版本 ＝ Ω 中含此 key、`run_id` 最大的 run 的那一列。不取聯集，也不取最早一列。
- 撤銷 ＝ 有一筆更晚、`session_date` 早於 `ex_date`、而且不含此 key 的 run。
- 過期 ＝ `session_date` 不早於 `ex_date` 的 run 不含此 key，不影響事件存在與版本。
- 版本與觸發的完備性：任一鏈尾列的判定時版本若與目前視圖不同，必有某筆 `run_id > settle_source_run_max` 的 run 與它的前一版不同。所以用「對前一版比較」產生的觸發不會漏列，只會多記。

**(ii) 各類變化的歸屬**

| 變化 | `change` | 受影響日期 | 鏈尾 `resolved` | 鏈尾作廢 |
|---|---|---|---|---|
| 同 key 的因子投影不同（含空白↔有值、配股比新增或移除、可解析↔拒絕） | `factor_changed` | `ex_date` | `dividend_factor_corrected`（重算；可能仍是 resolved，或依 (丙) 改記作廢） | 診斷 `dividend_factor`，不 supersede |
| 新事件 | `key_added` | `ex_date` | 同上 | 同上 |
| 除息日前消失（撤銷，或改期的舊 key） | `key_removed` | 舊 `ex_date` | 同上 | 同上 |
| 改期 | 不另立類別 ＝ 舊 key 的 `key_removed` ＋ 新 key 的 `key_added`；不推定兩者是同一事件 | 兩個日期 | 同上 | 同上 |
| `session_date` 不早於除息日時消失 | 不觸發（過期） | — | — | — |
| `content_hash` 相同，或投影相同（例如只改了 `Name`） | 不觸發 | — | — | — |

「空白到有值」：空白時現金股利按 0 處理，`distributed ≤ 0` 使因子為 None【事實：`models.py:182-184`】。所以窗內含這類事件的列，結算時就已作廢，事後補到值只進診斷。鏈尾是 `resolved` 時（事件當時不影響可用性）歸 `dividend_factor_corrected`。規則只看鏈尾 `status`。

**(iii) 限制 d**：採 d2。對 ex_date ∈ (T, T+h] 的事件，前收落在 [T, T+h−1]，第 3 點既有的配對已涵蓋；只有 ex_date ＝ T 的事件，前收在 T 之前。擴充只影響作廢列，因為已結算列的 bar 晚到本來就不在任何觸發內，這是第 3 點既有的邊界。「窗內是否含 ex_date ＝ T」原文沒有規定，交 quant 確認（見 G-Q4）。

**(iv) 限制 f**：新增 (丙)。條件如下：
- `correction_causes` 含 `dividend_factor_corrected`，而且不含 `x2_session_removed`（含者屬 (乙)）；`scope_kind ∈ {symbol, sector}`。
- 重算後五個欄位與新列逐位相同。
- `status_reason` 限三值：`dividend_factor_unusable`、`split_or_reduction_suspected`、`basket_coverage_below_90`。
- `window_factors_json` 與前一列不同。
- `basket_coverage_below_90` 另須本作業的觀察日已含 D_5；未含時拒絕（`failed_check = dividend_basket_wait_not_due`）。這是殘餘缺口，列 N-120（暫）。

**(v) 限制 a、b**：都不升 CEO 裁決，列 CEO 知悉。
- a：不改冪等略過；N-16 改變冪等略過時重查第 10 點。
- b：除息日後的更正，來源本身沒有發布，不在 §6.4「來源資料的更正」可觀察的範圍內，以揭露處理。另接第二來源是選型決策，CEO 若要求涵蓋，再由 data-engineer 列方案與成本。

**(vi) §4.2 解析度揭露**：只寫義務，見 E6 第 10 點 (11)。事先宣告的字句建議見 G；使用者面文案交 creative-lead。

**限制 c**：撤銷規則的前提是「來源在除息日前的每一個交易日都列出該事件」。由 data-engineer 用既有市場 DB 的內容唯讀查證（在副本上做），列為 N-117（暫），是 D-9 實作前的閘門。查證不成立時，第 10 點與 D-4 第 2 點須退回修訂。

**限制 e**：讀端做 run 層對照（`stored_row_count ≠ row_count` 時記 WARNING 並揭露）。`row_count` 是否包含未寫入的列，與 c 一起查證。寫端修正另案（N-119 暫）。

**限制 g**：非 ok 的 run 不計入，也不構成撤銷；連續失敗造成的缺日由既有機制處理。

#### D. ADR-0027 落字稿（old 皆為 Grep `-o` 恰 1 處）

**E1（N17-1）D-1 表，行 256。** new ＝ old 之後換行接新的一列：
- old：`| `app/dividends/adjust.py::adjust_series_pit` | `AdjustedSeries`（R-108） |`
- 接續新列：
`| `app/dividends/announce_view.py`（N-17；純函式） | `factor_projection`、`dividend_event_view`、`dividend_revisions` 的唯一定義（D-4 第 2 點、D-3「晚到資料的觸發」第 10 點）。不讀 DB、不讀時鐘；欄位解析只經 `app/dividends/providers.py::parse_dividend_row`；不 import `app.dividends.store`、`app.dividends.adjust`、`app.forecast.*`、`app.outlook.*` |`

**E2（N17-2）D-3 晚到第 1 點，行 496。** new ＝ old 加句末接字：
- old：`讀市場 DB（一條 SQL，回傳 `run_id`、`session_date`、`recorded_at`、`source`）。`
- 句末接：`（N-17）它在第 2 點取得 `run_max` 與 W 之後，於同一次呼叫內呼叫第 10 點的 `scan_dividend_factor_revisions()`，沿用同一個 `run_max` 與 W；兩者的命中項合併回傳，同屬本點的第一類觸發（「四類」不變）。`scan_dividend_factor_revisions()` 只由它呼叫（AST），市場 DB 只經第 10 點的兩個唯讀方法讀取。`

**E3（N17-3）第 3 點，行 508。**
- old：`而且結算窗 [T, T+h] 含 `session_date`；該列的標的`
- new：`而且結算窗 [T, T+h] 含 `session_date`，或（N-17）`session_date` 等於該列 `window_factors_json` 任一項的 `prev_close_session`（第 10 點 (7)；除息日為 T 時，前收在 T 之前）；該列的標的`

**E4（N17-4）第 6 點，行 511。**
- old：`該觸發的偵測方式（誰偵測、讀哪種 run、怎麼配對、晚到怎麼判定）尚未定義（後續追蹤清單 N-17）；定義落地並經風控確認、修訂本點之前，`dividend_factor` 視為沒有觸發涵蓋。同一個缺口也使第 4 類 `dividend_factor_corrected` 沒有觸發來源，已結算列不會因除權息因子更正而 supersede；這一面是事先宣告 §6.4 既有規則的實作缺口，N-17 是 D-9 結算程式實作前的阻擋項，不得以本點的「未涵蓋，不計」揭露代替；`
- new：`該觸發的偵測方式見第 10 點（N-17）：已結算列的因子更正依同點 (6) 與 D-11.4 第 11 點 (h) supersede，作廢列只進 `forecast_void_late_diag`；同點 (10) 所列的涵蓋邊界依同點 (11) 揭露，不以「未涵蓋，不計」代替〔N-17 取代：原寫「該觸發的偵測方式（誰偵測、讀哪種 run、怎麼配對、晚到怎麼判定）尚未定義（後續追蹤清單 N-17）；定義落地並經風控確認、修訂本點之前，`dividend_factor` 視為沒有觸發涵蓋。同一個缺口也使第 4 類 `dividend_factor_corrected` 沒有觸發來源，已結算列不會因除權息因子更正而 supersede；這一面是事先宣告 §6.4 既有規則的實作缺口，N-17 是 D-9 結算程式實作前的阻擋項，不得以本點的「未涵蓋，不計」揭露代替；」〕；`

**E5（N17-5）第 8 點，行 513。**
- old：`本次不產生任何 `source_revision` 觸發，W 不前進，其餘觸發照常；`
- new：`本次不產生任何 `source_revision` 觸發，也不產生第 10 點的 `dividend_factor_revision` 觸發（N-17），W 不前進，其餘觸發照常；`

**E6（N17-6）新增第 10 點，接在行 514 之後。** new ＝ old 之後換行接以下全文：
- old：`原寫「9. 與 O-1 的關係：等待期間才寫入、在作廢寫入前已存在的 run，不屬於本點的晚到；這類 bar 的歸屬依 O-1 定案（後續追蹤清單 N-13）。」〕`
- 接續全文：
```
  10. （N-17；tech-architect 2026-10-24；data-engineer 2026-10-24 查證 `work/reviews/2026-10-24-N17因子修訂觸發查證-data-engineer.md`；風控〔待填〕）**因子修訂觸發**（讀端輪詢、寫端不動；D-11.4 第 11 點 (h) 第 4 類 `dividend_factor_corrected` 的觸發來源）：
     - (1) **誰偵測**：`scan_dividend_factor_revisions()`，與 `scan_late_market_bars()` 同一模組，呼叫點與共用的 `run_max`、W 見第 1 點（N-17 句）。`pit_snapshot`、`MarketPanelStore` 的寫入不動。市場 DB 只經 `MarketPanelReader` 新增的兩個唯讀方法讀取，各一條 SQL，不另開連線：
       - `ok_dividend_runs_between(run_id_exclusive, run_id_inclusive)`：條件 `kind = 'dividend_announce'`、`status = 'ok'`、`content_hash IS NOT NULL`、`session_date IS NOT NULL`，依 `run_id` 遞增回傳 `run_id`、`session_date`、`recorded_at`、`content_hash`、`row_count`，以及 `stored_row_count`（該 `content_hash` 在 `pit_dividend_announce_rows` 的列數）；
       - `dividend_announce_rows_for_hashes(content_hashes, symbols)`：回傳 `content_hash`、`key`、`symbol`、`ex_date`、`raw_json`；兩個集合以 `json_each` 帶入，參數數量固定（比照 `_ANNOUNCE_OBSERVATIONS_SQL`）。
       比較與事件視圖只由 `app/dividends/announce_view.py` 的純函式計算（D-1；D-4 第 2 點）。本點不讀 label、`hit`、基準命中或任何驗證統計（AST，比照第 1 點）。
     - (2) **掃描範圍**：以 `ok_dividend_runs_between(0, run_max)` 讀一次 run 清單，候選 run 為其中 `run_id ∈ (W, run_max]` 者。候選 run r 的前一版 p ＝ 清單中 `run_id` 小於 r 的最大者（可以不大於 W）；沒有 p 時以空集合比較。`r.content_hash = p.content_hash` 時不讀列，不產生觸發。只比較序號，不拿 `recorded_at` 與任何時刻比較。`status ≠ 'ok'` 的 run（含整批失敗、`session_date` 為 null 者）不計入，也不構成撤銷；連續失敗造成的缺日由既有機制處理，不屬本點。
     - (3) **比較**（r 對 p，逐 key）：
       - 因子投影 ＝ 該列經 `parse_dividend_row` 同一套解析後，`DividendEvent.adjustment_factor` 除 `previous_close` 之外讀取的全部欄位，數值以 Decimal 比較；解析被拒時，投影為「拒絕」一值，與任何可解析的投影都不同。不比較 `raw_json` 字串；`Name` 與認購相關欄位不在投影內。
       - `factor_changed`：同一 key 兩邊都有，投影不同（含空白 ↔ 有值、配股比新增或移除、可解析 ↔ 拒絕）；
       - `key_added`：p 沒有、r 有；
       - `key_removed`：p 有、r 沒有，而且 `r.session_date` 早於該列（取 p 的列）的 `ex_date`。`r.session_date` 不早於 `ex_date` 時屬於過期，不產生觸發；
       - 改期不另立類別，即舊 key 的 `key_removed` 加上新 key 的 `key_added`，不推定兩者是同一事件；
       - `ex_date` 為 null 的列不比較，列數記 WARNING，並依 (11) 揭露。
     - (4) **配對**（兩項都成立才算觸發）：主 DB 有 `scope_kind ∈ {symbol, sector}` 的鏈尾列（不限 `status`），其標的（個股，或族群 S_T 的成員）等於該項的 `symbol`，而且結算窗 [T, T+h]（待重算項取順延後的 T+h）含該項的 `ex_date`；r 的 `run_id` 大於該鏈尾列的 `settle_source_run_max`。大盤列不配對（不套用因子，事先宣告 §6.3）。
     - (5) **觸發項**：`{kind: dividend_factor_revision, run_id, recorded_at, session_date, prev_run_id, event_key, symbol, ex_date, change}` 寫入 `triggers_json`；`prev_run_id` 是 p 的 `run_id`，沒有 p 時為 null；`change ∈ {factor_changed, key_added, key_removed}`。同一 run 可有多項，以 `event_key` 區分。第 5 點以 `(run_id, recorded_at)` 為身分的驗證與首尾相接同樣適用（bars 與除權息的 run 共用序號，不會撞號）。`forecast_void_late_diag.late_data_refs_json` 對這類觸發記 `{kind, run_id, recorded_at, event_key}`。
     - (6) **歸屬**：依 D-11.4 第 11 點 (h)「原因怎麼歸屬」，受影響日期為該項的 `ex_date`（單日），類別為 `dividend_factor_corrected`。鏈尾 `resolved` 的列依 D-9 第 5 點 ④ 重算，除權息事件依 D-4 第 2 點以 `market_scan_to` 界定；重算後沒有任何欄位改變的筆不寫入（§6.4 第 3 點）；改記作廢依 D-11.4 第 11 點 (h)「適用範圍」(丙)。鏈尾作廢的列依 R10-3 不重算，只依本節 `forecast_void_late_diag` 算診斷，`late_data_kinds` 記 `dividend_factor`。歸屬只看鏈尾的 `status`，不看 `change`：「空白到有值」使結算當下因子不可用、鏈尾已作廢時，只進診斷，不 supersede；鏈尾是 `resolved` 時歸 `dividend_factor_corrected`。
     - (7) **`window_factors_json` 的內容**：`scope_kind ∈ {symbol, sector}` 的每一筆 outcome（含作廢列）都非 null，為該列判定視圖中，除息日落在結算窗 [T, T+h] 的每個事件各一項的陣列（族群含 S_T 的全部成員；沒有事件時為 `[]`）。每項恰有 `{symbol, event_key, ex_date, prev_close_session, cash_dividend, stock_dividend_ratio, factor}`：數值是正規化十進位字串或 null；`factor` 在因子不可用時為 null；`prev_close_session` 是計算前收所取的 session，取不到前收時仍記應取的 session。依 (`symbol`, `ex_date`, `event_key`) 排序。不含 `run_id`、`content_hash` 或任何時戳，所以版本 run 改變而數值相同時逐位相同。大盤列為 null。寫入驗證：鍵集合、排序、非 null 條件，不成立就拒絕寫入。
     - (8) **前收 bar（限制 d）**：前收 bar 晚到屬於第 3 點的 `source_revision`；第 3 點的配對另含 `prev_close_session`（N-17 句），涵蓋除息日為 T、前收在 T 之前的情形。這類診斷的 `late_data_kinds` 記 `dividend_factor`。已結算列的 bar 晚到不在任何觸發內，與第 3 點相同。
     - (9) **還原保護**：第 8 點成立時，本點不產生任何觸發，W 不前進（第 8 點 N-17 句）。
     - (10) **涵蓋邊界與預期量**：
       - (a) 每個 session 只留第一筆 ok 的 `dividend_announce` run（`pit_snapshot.py:151-153,160-161` 的冪等略過），同一 session 內、第一筆之後的修訂看不到。本點不改冪等略過（ADR-0012）；後續追蹤清單 N-16 改變冪等略過時，重查本點。
       - (b) 來源 `TWT48U_ALL` 只列未來的除權息事件（`app/dividends/coverage.py:11-13`），除息日之後的更正不在來源內，本點不涵蓋。另接來源屬資料源選型（後續追蹤清單 N-118（暫），CEO 知悉）。
       - (c) D-4 第 2 點的撤銷判定，以「來源在除息日之前的每一個交易日都列出該事件」為前提（推論；data-engineer 查證，後續追蹤清單 N-117（暫），D-9 結算程式實作前）。查證不成立時，本點與 D-4 第 2 點須修訂，不得照用。
       - (e) 同一批內 key 重複時後者覆蓋前者（`market_panel.py:597-611`），無法逐列偵測。`stored_row_count ≠ row_count` 的 run 記 WARNING，依 (11) 揭露（`row_count` 是否含未寫入的列，data-engineer 查證，同 (c)）；寫端修正另案（後續追蹤清單 N-119（暫））。
       - 預期量〔推論〕：除息日前的修訂，多半在結算判定視圖建立之前就已擷取（擷取順序 `dividend_announce` 先於 bars，`pit_snapshot.py:116-132`；結算在 T+h 的 bars 之後，而窗內事件的除息日不晚於 T+h），所以本點的觸發與 `dividend_factor` 診斷預期接近 0。這是預期，不是驗收門檻；0 不得當成「沒有因子修訂」的證據。失效條件：新增任何回填路徑，或 (a) 的冪等略過改變時，重查本子點。
     - (11) **§4.2 揭露義務**（項目由 quant 在事先宣告 §4.2「更正作業揭露」(iv) 登記；使用者面字面由 creative-lead 起草、送風控）：
       - 個股與族群 × `dividend_factor` 照實計數，沒有列時列 0，並註明 0 不構成「沒有因子修訂」的證據；大盤 × `dividend_factor` 維持「未涵蓋，不計」；
       - 解析度與不涵蓋：每個 session 一份（第一筆 ok run），以及 (10) 的 (a)、(b) 兩項；
       - 觸發項數，依 `change` 分列；
       - 依 D-4 第 2 點視為撤銷的事件，逐筆列出 `symbol`、`event_key` 與第一筆不含它的 `run_id`，另列其中 `ex_date` 落在任一鏈尾列結算窗內的筆數；
       - 因因子修訂寫入的 supersede 列，依新列 `status` 分列（`resolved`；依 (丙) 改記作廢），以及 (丙) 因 D_5 未到而被拒的筆數；
       - `stored_row_count ≠ row_count` 的 run 數與 `run_id`；因 `ex_date` 為 null 而未比較的列數；
       - 第 8 點成立期間可能不完整，沿用第 8 點的揭露。
```

**E7（N17-7）D-4 第 2 點，行 873。** new ＝ old 之後換行接以下子點：
- old：`2. **還原用的除權息事件**：取 `pit_dividend_announce_rows` 的 PIT 視圖，不讀主 DB 的 `dividend_events`（upsert）。`
- 接續子點：
```
   - （N-17；tech-architect 2026-10-24）**事件與版本的取法**（不取聯集）：以該次讀取所界定的 ok run 集合 Ω 為準（結算評估：`run_id ≤ R`，D-9.2；更正作業與 `forecast_void_late_diag`：`run_id ≤ market_scan_to`，D-9 第 5 點 ④；預測端：D-4.1 的可見性規則），只取 `kind = 'dividend_announce'`、`status = 'ok'`、`content_hash` 與 `session_date` 都非 null 的 run。事件身分是列的 `key`（`symbol|原始 Date 字串`）。
     - 版本：Ω 中含該 key、`run_id` 最大的 run 的那一列。不取聯集，也不取最早的一列；同一 key 在不同 run 的列不合併。
     - 撤銷：Ω 中有 run 的 `run_id` 大於版本所在的 run、`session_date` 早於該事件的 `ex_date`、而且不含該 key 時，該事件視為已撤銷，不進事件集合。改期即舊 key 撤銷、新 key 新增，不另行配對。`session_date` 不早於 `ex_date` 的 run 不含該 key，屬於過期，不影響存在與版本。本子點的前提見 D-3「晚到資料的觸發」第 10 點 (10) (c)。
     - `ex_date` 為 null 的列不進事件集合（與現行 `_load_dividend_frame` 相同）。
     - 因子欄位一律經 `parse_dividend_row` 的同一套解析；解析被拒的列，事件照樣存在，因子視為不可用（fail-closed）。
     - 判定只由 `app/dividends/announce_view.py` 的 `dividend_event_view()` 產生。`app/forecast/**`、`app/outlook/**` 不得經 `app.data.panel` 的 `ex_dividend_announcements()` 或其他聯集語意的路徑取得除權息事件（AST）。
     - 理由：聯集會留下已撤銷或改期的舊事件，同一 key 的不同版本也沒有取捨規則（data-engineer 2026-10-24 查證第二節第 4 點）；以序號界定，結算與更正重算逐位可重現。預測端的適用待 quant 確認（修訂紀錄 N-17 批）；確認前，預測端的 `adjust_series_pit` 不實作。
```

**E8（N17-8）D-11.4 (h)，行 2115。**
- old：`〔N-17：因子修訂觸發的偵測方式尚未定義，定義落地前不會產生這類觸發，見 D-3「晚到資料的觸發」第 6 點〕`
- new：`〔N-17 取代：原註為「N-17：因子修訂觸發的偵測方式尚未定義，定義落地前不會產生這類觸發，見 D-3「晚到資料的觸發」第 6 點」。偵測方式見 D-3「晚到資料的觸發」第 10 點〕`

**E9（N17-9）行 2118。** new ＝ old 之後換行，接一行（行首 15 個空格）：
- old：`- 來源修訂依 D-3「晚到資料的觸發」。`
- 接續：`               - （N-17）因子修訂（`dividend_factor_revision`）依 D-3「晚到資料的觸發」第 10 點：受影響日期 ＝ 該項的 `ex_date`（單日），類別為 `dividend_factor_corrected`；鏈尾作廢的列依 R10-3 不重算，只依 D-3 `forecast_void_late_diag` 算診斷（同點 (6)）。`

**E10（N17-10a）行 2134。**
- old：`屬於下列兩種之一：`
- new：`屬於下列三種之一（(丙) 為 N-17）：`

**E11（N17-10b）行 2136 句末。** new ＝ old 之後換行，接一行（行首 19 個空格）：
- old：`登記之前，這兩種情形依 D-9 第 5 點「待重算」處理，不寫作廢列。`
- 接續：`                   - **(丙)**（N-17）`correction_causes` 含 `dividend_factor_corrected`、不含 `x2_session_removed`（含者屬 (乙)），`scope_kind ∈ {symbol, sector}`；以本作業的判定視圖、經 `scoring.py` 的同一套函式重算（五值全部評估，D-9.3「判定順序」），得到的 `status`、`status_reason`、`void_reasons_json`、`basket_excluded_members_json`、`window_factors_json` 與新列逐位相同；`status_reason ∈ {dividend_factor_unusable, split_or_reduction_suspected, basket_coverage_below_90}`（仍受 D-3 `void_reasons_json` 依 scope 的允許集合限制）；`window_factors_json` 與前一列不同。`status_reason = basket_coverage_below_90` 時，另須本作業的 `observed_sessions_json` 含該列 T+h 之後第 5 個觀察交易日 D_5；不含時拒絕寫入（`write_validation_failed`，`failed_check = dividend_basket_wait_not_due`），記 WARNING，處理路徑列後續追蹤清單 N-120（暫）。理由：事先宣告 §6.4 結算端第 3 點「有變的筆新增一列」與 §6.3「結算窗內有除權息但因子不可用」；因子更正不改變 T+h，所以不經待重算。`

**E12（N17-10c）行 2138。**
- old：`(甲)：`window_factors_json` 和前一列相同（(乙) 依該支的逐位相同驗證；窗延長後可能與前一列不同）。`
- new：`(甲)：`window_factors_json` 和前一列相同（(乙) 依該支的逐位相同驗證；窗延長後可能與前一列不同；(丙) 依該支，與前一列不同）。`

**E13（N17-10d）行 2140。**
- old：`(甲)、(乙) 以外的改記作廢，不屬於本 ADR 已定義的 supersede，一律拒絕`
- new：`(甲)、(乙)、(丙) 以外的改記作廢，不屬於本 ADR 已定義的 supersede，一律拒絕`

**E14（N17-11）FL-22，行 2650。** new ＝ old 之後換行，接一行（行首 6 個空格）：
- old：`(甲) 列的 `window_factors_json` 與前一列不同 → 拒絕。`
- 接續：`      - （N-17）(丙)：個股已結算列，結算之後的因子修訂使窗內事件新增配股比 → 更正作業寫入 `dividend_factor_unusable` 作廢列，`correction_causes = [dividend_factor_corrected]`，不被拒絕，最新 outcome 走 LM-143；拒絕子例各一格：重算結果與新列任一欄不同；`window_factors_json` 與前一列相同；前一列已作廢；`scope_kind = market`；`status_reason` 不在三值內。`correction_causes` 同時含 `x2_session_removed` → 依 (乙) 驗證，不依 (丙)。因子修訂使還原後序列符合分割判準 → 寫入 `split_or_reduction_suspected` 作廢列，不被拒絕。族群成員的因子變為不可用、排除後覆蓋 < 90%：本作業 `observed_sessions_json` 含 D_5 → 寫入 `basket_coverage_below_90` 作廢列；不含 → 拒絕，`failed_check = dividend_basket_wait_not_due`，記 WARNING，不列入 `pending_json`。對照格：因子修訂後重算仍為 `resolved`、`window_factors_json` 與報酬不同 → 依 R10-2 `[dividend_factor_corrected]` 寫入，呈現 FAIL_CLOSED（LM-154）。`

**E15（N17-12a）FL-64 首句，行 2680。**
- old：`D-3「晚到資料的觸發」第 1～9 點（第 9 點 v0.14 V14-01 加））`
- new：`D-3「晚到資料的觸發」第 1～10 點（第 9 點 v0.14 V14-01 加；第 10 點 N-17 加））`

**E16（N17-12b）FL-64 (a)，行 2683。**
- old：`市場 DB 只經 `MarketPanelReader.ok_bars_runs_between` 讀取；`
- new：`市場 DB 只經 `MarketPanelReader.ok_bars_runs_between` 讀取（N-17：`scan_dividend_factor_revisions()` 只經 `ok_dividend_runs_between`、`dividend_announce_rows_for_hashes` 讀取，而且只由 `scan_late_market_bars()` 呼叫）；`

**E17（N17-12c）FL-64 (f)，行 2708。**
- old：`三個 scope × `dividend_factor`（N-17 定義落地前）。`
- new：`大盤 × `dividend_factor`（N-17：大盤不套用因子；個股與族群 × `dividend_factor` 依 D-3「晚到資料的觸發」第 10 點照實計數，沒有列時輸出 0，見 (i10)）。`

**E18（N17-12d）FL-64 末行，行 2719。**
- old：`  - 第 7 點是預期量，不是規則，不設格。`
- new：
```
  - (i)（N-17；第 10 點、D-4 第 2 點）fixture 用離線的假市場 DB（`pit_snapshot_runs`、`pit_dividend_announce_rows`）與主 DB：
    - (i1) 事件與版本（`dividend_event_view`，表格驅動）：同一 key 兩版 → 只取 `run_id` 較大的一版，事件只出現一次（不取聯集）；Ω 的界定值介於兩版之間 → 取較早的一版；除息日前的後續 run 不含該 key → 撤銷，不進事件集合；`session_date` 等於、晚於除息日的 run 不含該 key → 不影響（兩格）；撤銷後又出現 → 取再出現的一版；改期 → 只有新 key 的事件；`ex_date` 為 null → 不進事件集合；解析被拒的列 → 事件存在、`factor` 為 null。AST：`app/forecast/**`、`app/outlook/**` 不呼叫 `ex_dividend_announcements`。
    - (i2) 比較：`content_hash` 相同 → 不呼叫 `dividend_announce_rows_for_hashes`（spy）；只有 `Name` 或認購欄位改變、`"3.000000"` 對 `"3"`、空白值 `""`／`-`／`--`／`N/A` 互換 → 各一格，不觸發；`CashDividend` 改變、空白 → 有值、`StockDividendRatio` 新增、可解析 → 被拒 → 各一格 `factor_changed`；新 key → `key_added`；除息日前一個 session 的 run 少了該 key → `key_removed`；`session_date` 等於除息日的 run 少了該 key → 不觸發；沒有前一版 → 全部為 `key_added`。
    - (i3) 掃描範圍：p 的 `run_id` 不大於 W 時仍作為比較基準；`run_id = W` 不取、`run_id = run_max` 取；`kind ≠ 'dividend_announce'`、`status ≠ 'ok'`、`session_date` 為 null、`content_hash` 為 null 各一格，不產生觸發；整批失敗的 session 不構成撤銷；AST：`scan_dividend_factor_revisions` 不讀 `MAX(run_id)`、不比較 `recorded_at`；注入倒退的 store 時鐘 → 結果逐位相同。
    - (i4) 配對：個股鏈尾 `resolved`、`ex_date` 在 [T, T+h]、`run_id` 大於 `settle_source_run_max` → 恰好一項觸發，重算後歸 `dividend_factor_corrected`；鏈尾作廢 → 只寫診斷（`late_data_kinds` 含 `dividend_factor`），不寫 supersede 列；`ex_date` 不在窗內、`run_id ≤ settle_source_run_max`（含相等）、大盤列 → 各一格，不觸發；族群成員 → 觸發，非成員 → 不觸發；待重算項以順延後的 T+h 配對。
    - (i5) 觸發項：恰有 `kind`、`run_id`、`recorded_at`、`session_date`、`prev_run_id`、`event_key`、`symbol`、`ex_date`、`change` 九鍵；同一 run 兩個 key → 同一作業兩項；同一 `(run_id, recorded_at)` 出現在兩個已完成作業 → 拒絕（與 (e) 共用驗證）；重算後沒有任何欄位改變 → 不寫列。
    - (i6) `window_factors_json`：個股與族群的 `resolved` 列與作廢列都非 null，窗內沒有事件時為 `[]`，大盤列為 null；版本 run 改變、數值相同 → 逐位相同；排序錯誤、多出鍵（例如 `run_id`）→ 拒絕寫入。
    - (i7) 前收 bar：作廢列的除息日為 T，前收 session 的定案 run 晚到 → 依第 3 點產生 `source_revision` 觸發，診斷的 `late_data_kinds` 含 `dividend_factor`；該 run 的 `session_date` 在窗外、也不是任何 `prev_close_session` → 不觸發。
    - (i8) 還原保護：第 8 點成立 → 不產生 `dividend_factor_revision`，W 不前進（與 (g) 共用 fixture）。
    - (i9) 已知限制（文件化格）：同一 session 第二次擷取到不同內容 → 不寫第二筆 run，不產生觸發；同一批兩列同 key → `stored_row_count < row_count`，記 WARNING，§4.2 列出該 run〔`row_count` 口徑依後續追蹤清單 N-117（暫）查證後定格〕。
    - (i10) §4.2：個股、族群 × `dividend_factor` 沒有列時輸出 0；大盤 × `dividend_factor` 輸出「未涵蓋，不計」；撤銷事件清單與依 `change` 分列的計數，與 fixture 逐項相同。
  - 第 7 點與第 10 點 (10) 的預期量不是規則，不設格。
```

**E19 修訂紀錄段：接在檔尾。** 前面加一行空行、`---`、再一行空行。全文見 F。

**動到的段落與協調**：
- D-1 表行 256（插入一列）。
- D-3「晚到資料的觸發」行 496、508、511、513、514（後接新增的第 10 點）。
- D-4 行 873。
- D-11.4 第 11 點 (h) 行 2115、2118、2134、2136、2138、2140。
- FL-22 行 2650；FL-64 行 2680、2683、2708、2719。
- 修訂紀錄檔尾。

與其他批的關係：
- **N-109、N-110**（D-3 `forecast_record`、D-7 第 7 點、FL-76、FL-77）：沒有重疊；它的修訂紀錄段已在我讀到的檔尾。
- **N-113**（dirdef 模組位置）、**N-115 #12**（未分配模組的函式）：可能也改 D-1 表。只要不改 `adjust_series_pit` 那一列，就與 E1 不衝突。第 10 點 (1) 寫的是「與 `scan_late_market_bars()` 同一模組」，不論 N-115 把它分到哪個模組都成立。
- **N-114**（缺日稽核）：沒有重疊。
- 落檔順序：錨點都是唯一字串，與 N-113～N-115 的先後無關；修訂紀錄段最後落，接在當時的檔尾。

#### E. 給 data-engineer 的唯讀方法與函式介面

```python
# app/data/market_panel.py :: MarketPanelReader  (read-only; one SQL each; no new connection)
@dataclass(frozen=True)
class DividendAnnounceRun:
    run_id: int
    session_date: date
    recorded_at: str            # as stored (store clock, UTC ISO8601); never compared to a time
    content_hash: str
    row_count: int | None
    stored_row_count: int       # COUNT(*) of pit_dividend_announce_rows for content_hash

@dataclass(frozen=True)
class DividendAnnounceRow:
    content_hash: str
    key: str                    # "{symbol}|{raw Date}"
    symbol: str
    ex_date: date | None
    raw_json: str

def ok_dividend_runs_between(self, run_id_exclusive: int, run_id_inclusive: int) -> tuple[DividendAnnounceRun, ...]: ...
def dividend_announce_rows_for_hashes(self, content_hashes: Sequence[str], symbols: Sequence[str]) -> tuple[DividendAnnounceRow, ...]: ...

# app/dividends/announce_view.py  (pure; no DB, no clock)
@dataclass(frozen=True)
class FactorProjection:
    refused: str | None                         # UnparseableRowError class name, else None
    fields: tuple[tuple[str, str | None], ...]  # fields read by adjustment_factor except previous_close; normalized decimal str

def factor_projection(row: DividendAnnounceRow) -> FactorProjection: ...   # via parse_dividend_row; source/as_of fixed, not projected

@dataclass(frozen=True)
class EventVersion:
    event_key: str; symbol: str; ex_date: date
    version_run_id: int
    projection: FactorProjection
    event: DividendEvent | None                 # None when refused

@dataclass(frozen=True)
class WithdrawnEvent:
    event_key: str; symbol: str; ex_date: date
    last_seen_run_id: int; first_missing_run_id: int

@dataclass(frozen=True)
class DividendEventView:
    events: tuple[EventVersion, ...]            # sorted by (symbol, ex_date, event_key)
    withdrawn: tuple[WithdrawnEvent, ...]
    null_ex_date_rows: int
    row_count_mismatch_run_ids: tuple[int, ...]

def dividend_event_view(runs: Sequence[DividendAnnounceRun], rows: Sequence[DividendAnnounceRow], *, symbols: frozenset[str]) -> DividendEventView: ...
# runs is already Omega; raise ValueError if run_id not strictly increasing

@dataclass(frozen=True)
class DividendRevision:
    run_id: int; recorded_at: str; session_date: date; prev_run_id: int | None
    event_key: str; symbol: str; ex_date: date
    change: Literal["factor_changed", "key_added", "key_removed"]

def dividend_revisions(runs: Sequence[DividendAnnounceRun], rows: Sequence[DividendAnnounceRow], *, scan_from_exclusive: int, scan_to_inclusive: int, symbols: frozenset[str]) -> tuple[DividendRevision, ...]: ...

# same module as scan_late_market_bars(); called only from it
def scan_dividend_factor_revisions(bounds: ScanBounds, *, market_reader: MarketPanelReader, store: ForecastStore) -> tuple[TriggerItem, ...]: ...
# ScanBounds(w, run_max) is frozen and constructed only inside scan_late_market_bars()
```
`app/dividends/providers.py` 會 import `httpx` 與 `app.data.http`【事實：:120-122】。若 FL 的 import 檢查不允許 announce_view 經 providers 可達這兩個模組，就把 `parse_dividend_row` 與 `_cell` 移到不做 I/O 的模組，行為逐位相同，並補等價測試。

#### F. 修訂紀錄段（E19 全文）

```
**N-17 因子修訂觸發批（後續追蹤清單 N-17；D-1 表一列、D-3「晚到資料的觸發」第 1、3、6、8 點與新增第 10 點、D-4 第 2 點、D-11.4 第 11 點 (h)「原因怎麼歸屬」與 R10-2「適用範圍」、FL-22、FL-64；方向：逐項標示，見各項）**
- 來源與套用範圍：
  - data-engineer 2026-10-24 查證：`work/reviews/2026-10-24-N17因子修訂觸發查證-data-engineer.md`。
  - tech-architect 2026-10-24 提案：`work/reviews/2026-10-24-N17因子修訂觸發提案-tech-architect.md`。
  - 風控〔待填：確認檔路徑與日期；風控改字之處以風控為準〕。
  - CEO：否；第 10 點 (10) 的 (a)、(b) 兩項列 CEO 知悉。
  - 與事先宣告〔v0.30（暫）〕的 §4.2「更正作業揭露」(iv) 同步同一個 commit，不適用相鄰 commit 寬限。
- 逐項（被取代的原文：判準同 v0.25 同步批段）：
  - N17-1 D-1 表加 `app/dividends/announce_view.py` 一列：方向：補定義（模組邊界）。CEO：否。插入，無被取代原文。
  - N17-2 D-3「晚到資料的觸發」第 1 點：方向：補定義（收緊：呼叫點唯一，不另讀 `run_max`）。CEO：否。句末接字，無被取代原文。
  - N17-3 同節第 3 點配對加前收 session：方向：收緊（觸發只會多記）。CEO：否。被取代的原文——
    > 而且結算窗 [T, T+h] 含 `session_date`；該列的標的
  - N17-4 同節第 6 點：方向：補定義（收緊：已結算列的因子更正有觸發來源）。CEO：否。被取代的原文已在原處以〔N-17 取代〕逐字錄存。
  - N17-5 同節第 8 點：方向：收緊。CEO：否。被取代的原文——
    > 本次不產生任何 `source_revision` 觸發，W 不前進，其餘觸發照常；
  - N17-6 同節新增第 10 點：方向：補定義（兩面）。收緊面：新的觸發來源、`window_factors_json` 的內容與寫入驗證、§4.2 揭露義務；另一面：(10) 的 (a)、(b)、(e) 三項不涵蓋，以揭露處理。CEO：否（(a)、(b) 知悉）。插入，無被取代原文。
  - N17-7 D-4 第 2 點：方向：補定義（消除歧義：版本取最新含該 key 的 run、不取聯集；除息日前消失視為撤銷）。CEO：否。句末接子點，無被取代原文。
  - N17-8 D-11.4 第 11 點 (h)「原因怎麼歸屬」第一個子點的 N-17 註：方向：不變（註）。CEO：否。被取代的原文已在原處以〔N-17 取代〕逐字錄存。
  - N17-9 同處加因子修訂一子點：方向：補定義。CEO：否。插入，無被取代原文。
  - N17-10 R10-2「適用範圍」加第三支：方向：補定義（兩面）。放寬面：已結算列經因子更正後應改記作廢者，原本被拒，改為寫入；另一面：只有逐位重算相同、原因限三值、族群覆蓋類須 D_5 已觀察的作廢寫得進去，作廢計入作廢率與 W。CEO：否。被取代的原文——
    > 屬於下列兩種之一：
    > (甲)：`window_factors_json` 和前一列相同（(乙) 依該支的逐位相同驗證；窗延長後可能與前一列不同）。
    > (甲)、(乙) 以外的改記作廢，不屬於本 ADR 已定義的 supersede，一律拒絕
  - N17-11 FL-22 加第三支的格：方向：收緊（測試）。CEO：否。插入，無被取代原文。
  - N17-12 FL-64 首句、(a)、(f)、新增 (i)、末行：方向：收緊（測試）。CEO：否。被取代的原文——
    > D-3「晚到資料的觸發」第 1～9 點（第 9 點 v0.14 V14-01 加））
    > 市場 DB 只經 `MarketPanelReader.ok_bars_runs_between` 讀取；
    > 三個 scope × `dividend_factor`（N-17 定義落地前）。
    > - 第 7 點是預期量，不是規則，不設格。
  - N17-13 本段。
- 照實並陳：
  - 版本不取聯集：聯集會讓已撤銷或改期的舊事件留在還原之中；取最早一版則忽略判定視圖內已知的修訂。
  - 除息日前消失視為撤銷，不改記因子不可用：後者會把撤銷與資料異常都變成作廢，屬於改變作廢定義，須事先宣告登記；前者在來源的單批回應不完整時會少套一個因子【推論】，所以以 WARNING 與 §4.2 逐筆揭露，並以第 10 點 (10) (c) 的查證為前提。
  - 比較以前一版 run 為基準，不逐列對判定時版本：任一鏈尾列的判定時版本與目前視圖不同，必有一筆 `run_id` 大於其 `settle_source_run_max` 的 run 與它的前一版不同，所以兩者觸發同一批列；差別只在多記，多記的列重算後不寫入。
  - 第三支不採「不 supersede、只揭露」：事先宣告 §6.4 結算端第 3 點規定有變的筆新增一列，第 6 點原文也禁止以揭露代替。第三支不採待重算路徑：因子更正不改變 T+h，`pending_json` 必含 `x2_session_removed`。代價：族群覆蓋類在 D_5 之前到達的修訂，該次被拒，畫面照原值呈現已結算列，之後沒有自動重查的觸發，處理路徑列後續追蹤清單 N-120（暫）。
  - 前收 bar 的配對擴充只涵蓋作廢列；已結算列的 bar 晚到不在任何觸發內，這是第 3 點既有的邊界，本批不改。
  - 結算窗內「除息日為 T 的事件」是否計入因子判定，原文沒有規定；本批照 [T, T+h] 字面處理，交 quant 確認。
- 待決事項與同批規則：
  - 本批內部不拆開；N17-6、N17-7、N17-10 必須同一個 commit。修訂紀錄（本段）最後落檔。
  - 落檔後的閘門：D-9 結算程式與更正作業的因子路徑，在後續追蹤清單 N-117（暫）查證完成之前不實作；查證不成立時回 tech-architect 修訂第 10 點與 D-4 第 2 點。
```

#### G. 事先宣告是否需同步：需要（給 quant 的字句建議）

- **G-Q1（必要，§4.2「更正作業揭露」(iv)）**
  - 被取代的原文：「涵蓋邊界：只涵蓋個股與族群成員的 bars；大盤的 T+h bar 與收盤、`basket_member`，以及除權息因子不涵蓋，標「未涵蓋，不計」，不以 0 呈現。除權息因子的晚到應由「因子修訂」觸發涵蓋，但該觸發的偵測方式尚未定義（ADR-0027 後續追蹤清單 N-17）；定義落地並經風控確認、修訂本點之前，一律標「未涵蓋，不計」。」
  - 建議新字：「涵蓋邊界：涵蓋個股與族群成員的 bars，以及個股與族群的除權息因子（ADR-0027 D-3「晚到資料的觸發」第 10 點，N-17）；大盤的 T+h bar 與收盤、`basket_member`，以及大盤的除權息因子（大盤不套用因子）不涵蓋，標「未涵蓋，不計」，不以 0 呈現。除權息因子的涵蓋只到來源預告表仍列出該事件的期間：每個交易日只取第一筆成功擷取，同一日之內的修訂看不到；除息日之後的更正，來源不發布，不涵蓋。另列：因子修訂觸發項數，依變化類別（同一事件的因子欄位改變、新事件、除息日前消失）分列；除息日前從來源消失、視為撤銷的事件，逐筆列出，並列其中除息日落在任一結算窗內的筆數；因因子修訂而新增的更正列，依新列狀態分列，以及其中因族群覆蓋的等待期限未到而被拒的筆數；來源單批列數與寫入列數不符的擷取次數；除息日無法解析而未比較的列數。」
  - 原文以〔v0.30 取代〕逐字保留。方向：收緊（揭露），另一面是 a、b 兩項明寫不涵蓋。
- **G-Q2（強烈建議，§6.4 結算端第 1 點加註）**：「〔v0.30 註（ADR-0027 N-17）：除權息因子的「來源資料」是 `TWT48U_ALL` 預告表在判定視圖中的最新版本（ADR-0027 D-4 第 2 點）；除息日之前的修訂依本節更正；除息日之後、或同一交易日第一筆擷取之後的更正，來源沒有可觀察的紀錄，不在本點的範圍，依 §4.2「更正作業揭露」(iv) 揭露。本點原文不改〕」方向：補定義（另一面：這兩類更正不會 supersede）。
- **G-Q3（建議，§4.2 作廢數加一項）**：「(9) 結算之後因除權息因子更正而改記作廢的筆數：鏈尾是作廢列、`supersedes_id` 非 null、`correction_causes` 含 `dividend_factor_corrected`、不含 `x2_session_removed`，依 `status_reason` 分列，逐列數出；另依是否屬於 E 分列，不屬於 E 的列照樣計入，但不計入作廢率與 W。」
- **G-Q4（提問）**：「結算窗內有除權息」是否包含除息日 ＝ T 的事件？這種事件數學上不影響 P(T)→P(T+h)。若 quant 登記為 (T, T+h]，E3 的擴充仍無害，可以保留。
- **G-Q5（提問）**：D-4 第 2 點的版本與撤銷規則，對預測端（特徵窗還原、`E-ADJ-UNUSABLE`、族群 `E-ADJ-COVERAGE`）是否適用？若適用，建議在事先宣告行 878「`pit_dividend_announce_rows` 的 PIT 視圖」後加〔v0.30 註：PIT 視圖中同一事件的版本與撤銷依 ADR-0027 D-4 第 2 點（N-17），不取聯集。本點原文不改〕。

#### H. 方向與 CEO 層級
- 整批方向：補定義（兩面）。
  - 收緊：新觸發來源、`window_factors_json` 的寫入驗證、配對擴充、揭露。
  - 放寬面：(丙) 讓原本被拒的改記作廢寫得進去，但作廢計入作廢率與 W，對模型更嚴。
  - 另一面：除息日前消失視為撤銷；a、b、e 三項以揭露處理。
- CEO：否（比照 N29-6）。a、b 兩項列 CEO 知悉。只有在風控要求涵蓋 b 時，才變成 CEO 的資料源選型決策。

#### I. 是否送風控：是
N-17 原鏈規定送風控，第 6 點原文也寫「經風控確認」。請風控單項確認以下四點：
- **R-Q1**：a、b、e 三項的「不可觀察部分以揭露處理」，是否符合第 6 點「不得以未涵蓋代替」的本意？我的論據是：可觀察的修訂都會 supersede，剩下的部分來源本身沒有紀錄。
- **R-Q2**：撤銷規則採 C1，不採 fail-closed 的 C2。
- **R-Q3**：(丙) 的族群 D_5 殘餘缺口（N-120 暫）。
- **R-Q4**：d2 的配對擴充。

#### J. 對實作的約束（qa 可逐條檢查）
1. `scan_dividend_factor_revisions()` 只由 `scan_late_market_bars()` 呼叫（AST），不讀 `MAX(run_id)`，也不比較 `recorded_at`（AST）。
2. 市場 DB 只經 `ok_bars_runs_between`、`ok_dividend_runs_between`、`dividend_announce_rows_for_hashes` 讀取：各一條 SQL，`json_each` 的參數數量固定，不開新連線；`app/forecast/**` 不出現市場 DB 的路徑字串。
3. `announce_view.py` 不讀 DB、不讀時鐘；不 import `app.dividends.store`、`app.dividends.adjust`、`app.forecast.*`、`app.outlook.*`。
4. 因子投影只經 `parse_dividend_row`，不比較 `raw_json` 字串。
5. `app/forecast/**`、`app/outlook/**` 不呼叫 `ex_dividend_announcements()`（AST）。
6. 本批不改 `pit_snapshot`、`MarketPanelStore`、`_write_dividend_content` 的寫入行為。
7. 觸發項恰有九鍵；`window_factors_json` 的鍵集合、排序、非 null 條件有寫入驗證。
8. (丙) 的寫入驗證依 E11。
9. 不新增任何以人工指定觸發或日期的 CLI、API（沿用第 1 點）。
10. N-117（暫）查證完成之前，D-9 結算與更正的因子路徑不實作；預測端的 `adjust_series_pit` 在 G-Q5 確認之前不實作。

## 三、驗證

- **我做過的事**：
  - Read 以下檔案的相關段落：data-engineer 查證檔全文；ADR-0027 行 228-267、440-529、862-911、1280-1449、2085-2164、2630-2719、5450-5506；事先宣告 §4.2（行 1136-1165）、§6.3（1716-1729）、§6.4（1881-1897）；追蹤清單 N-17、N-111～N-116；`dividends/models.py:140-189`、`dividends/providers.py:1-124`、`dividends/coverage.py:1-30`。
  - Grep 確認 E1～E18 的 old 與檔尾錨點各恰 1 處。
  - 新 token 目前在 ADR 的命中數為 0：`dividend_factor_revision`、`scan_dividend`、`ok_dividend_runs_between`、`dividend_announce_rows_for_hashes`、`announce_view`、`prev_close_session`、`dividend_event_view`、`(丙)`、`N17-`。
- **沒做的事**：沒有跑 git，所以 HEAD 與 working tree 是否相同未確認；沒有看市場 DB 內容；限制 c 與 `row_count` 口徑都是【推論】，待查。
- **落檔後的預期值**（整檔、Grep `-o`；前提是本批之外沒有其他批引入同名 token）：

| 檢查項 | 預期 |
|---|---|
| `scan_dividend_factor_revisions` | 5 |
| `dividend_factor_revision`（不加反引號，含上一列的子字串） | 9 |
| `` `dividend_factor_revision` ``（加反引號） | 3 |
| `ok_dividend_runs_between` | 3 |
| `dividend_announce_rows_for_hashes` | 3 |
| `prev_close_session` | 5 |
| `announce_view.py` | 4 |
| `dividend_event_view` | 3 |
| `(丙)` | 9 |
| `dividend_basket_wait_not_due` | 2 |
| `〔N-17 取代` | 4 |
| `N17-` | 16 |
| `N-17 定義落地前` | 2（由 2 變 2：行 4348 加上新修訂紀錄段的引文；正文為 0） |
| E3、E5、E10、E12、E13、E15、E16、E17 的 old | 各 1（只剩修訂紀錄的引文；正文為 0） |
| E4 的 old | 1（在〔N-17 取代〕內） |
| E8 的 old（以「〔N-17：」開頭） | 0 |
| `  - 第 7 點是預期量，不是規則，不設格。`（含行首兩個空格與「- 」） | 0 |
| E1、E2、E6、E7、E9、E11、E14 的 old（new ＝ old 加接續） | 各 1 |

- 本批沒有改 agent 定義，`validate_agents.py` 不受影響。
- **CEO 需要親自確認的事**：只有限制 b 的知悉——「除息日後的事後更正不涵蓋，目前沒有已知的免費 OpenAPI 第二來源」是否可以接受。

## 四、下一步

1. **coordinator**：
   - 把本報告轉存為 `work/reviews/2026-10-24-N17因子修訂觸發提案-tech-architect.md`，送風控單項確認 R-Q1～R-Q4。
   - 同時把 G-Q1～G-Q5 交給 quant。
   - 追蹤清單更新：N-17 改為「提案完成，待風控」；新增 N-117（限制 c 與 `row_count` 口徑查證，data-engineer，D-9 實作前，阻擋）、N-118（除息日後更正的第二來源，CEO 知悉，非阻擋）、N-119（key 撞號的寫端修正，data-engineer → TA，D_v 前）、N-120（(丙) 族群 D_5 未到的被拒列，TA → 風控，D_v 前）。編號由 coordinator 正式指派。
2. **風控確認、quant 完成 v0.30（暫）之後**：tech-writer 依 E1～E19 落檔，和事先宣告同一個 commit，再送 qa-reviewer（含 Codex）審查。
3. **data-engineer**：先做 N-117 的唯讀查證；定案之後，再依 E 段介面與 FL-64 (i) 起草唯讀方法與離線 fixture 測試。

涉及檔案（絕對路徑）：
- /home/user/AICompany/docs/adr/0027-stock-desk-預測紀錄帳-儲存-PIT輸入-排程與定義登記.md
- /home/user/AICompany/work/research/2026-10-15-3日5日方向判斷-事先宣告草案.md
- /home/user/AICompany/work/reviews/2026-10-24-N17因子修訂觸發查證-data-engineer.md
- /home/user/AICompany/work/dispatch/2026-10-17-後續追蹤清單.md
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/models.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/providers.py
- /home/user/AICompany/apps/stock-desk/backend/app/dividends/coverage.py

### 其他部門
data-engineer 是本鏈第一步，已完成查證，本次未再參與。風控、quant、tech-writer、qa-reviewer 本次未參與，等提案轉交。CEO 只需知悉限制 a、b。其他部門（product-manager、frontend-engineer、devops-sre、creative-lead 等）本次未參與（純架構提案）。
